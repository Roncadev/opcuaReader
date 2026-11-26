import { defineComponent, h, type PropType, type VNode } from 'vue'

export interface TNode {
  node_id: string
  display_name: string
  browse_name: string
  node_class: string
  has_children: boolean
  children: TNode[]
  expanded: boolean
  loading: boolean
  loaded: boolean
  data_type?: string
}

const spinnerSvg = (): VNode =>
  h('svg', { class: 'w-3 h-3 animate-spin', fill: 'none', viewBox: '0 0 24 24' }, [
    h('circle', { class: 'opacity-25', cx: 12, cy: 12, r: 10, stroke: 'currentColor', 'stroke-width': 4 }),
    h('path', { class: 'opacity-75', fill: 'currentColor', d: 'M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z' })
  ])

const addIconSvg = (): VNode =>
  h('svg', { class: 'w-3.5 h-3.5', fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
    h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': 2, d: 'M12 4v16m8-8H4' })
  ])

export const NodeTreeItem = defineComponent({
  name: 'NodeTreeItem',
  props: {
    node: { type: Object as PropType<TNode>, required: true },
    depth: { type: Number, default: 0 }
  },
  emits: ['toggle', 'add'],
  setup(props, { emit }) {
    const render = (): VNode => {
      const n = props.node
      const indent = props.depth * 16

      const toggle = (): VNode =>
        h('button', {
          class: 'w-4 h-4 flex items-center justify-center text-slate-500 hover:text-slate-200 transition-colors shrink-0',
          onClick: () => emit('toggle', n)
        }, n.has_children
          ? (n.loading ? spinnerSvg() : h('span', {
              class: 'transition-transform inline-block',
              style: { transform: n.expanded ? 'rotate(90deg)' : '' }
            }, '▶'))
          : h('span', { class: 'text-slate-700' }, '·')
        )

      const addBtn = (): VNode =>
        h('button', {
          class: 'ml-1 w-5 h-5 flex items-center justify-center text-slate-600 hover:text-emerald-400 transition-colors shrink-0',
          title: 'Aggiungi ai nodi monitorati',
          onClick: () => emit('add', n)
        }, addIconSvg())

      const row = h('div', {
        class: 'flex items-center gap-1 py-0.5 px-1 hover:bg-slate-700/40 rounded group',
        style: { paddingLeft: `${indent + 4}px` }
      }, [
        toggle(),
        h('span', {
          class: n.node_class === 'Variable'
            ? 'text-blue-300 flex-1 truncate cursor-default'
            : 'text-slate-300 flex-1 truncate cursor-default'
        }, n.display_name || n.browse_name),
        h('span', { class: 'text-slate-600 text-[10px] shrink-0 hidden group-hover:inline' }, n.node_class),
        n.node_class === 'Variable' ? addBtn() : null
      ])

      const children = n.expanded && n.children.length > 0
        ? h('div', {}, n.children.map((child: TNode) =>
            h(NodeTreeItem, {
              key: child.node_id,
              node: child,
              depth: props.depth + 1,
              onToggle: (c: TNode) => emit('toggle', c),
              onAdd: (c: TNode) => emit('add', c)
            })
          ))
        : null

      return h('div', {}, [row, children])
    }

    return render
  }
})
