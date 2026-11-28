# Tuần tự hóa đồ thị có chu trình và bảo toàn danh tính nút

## 1. Vấn đề: làm sao lưu một đồ thị rồi khôi phục đúng đối tượng?

Một ứng dụng quản lý lộ trình học có các tài nguyên A, B và C. Mỗi tài nguyên có thể trỏ đến tài nguyên khác; ví dụ A liên kết tới B, B tới C, còn C lại liên kết về A. Khi ứng dụng khởi động lại, ta muốn đọc một tệp JSON và khôi phục **đúng ba nút cùng ba liên kết**, không tạo thêm nút giả hoặc rơi vào vòng lặp vô hạn.

Có ba vấn đề dễ bị nhầm:

- **Chu trình (cycle):** lần theo tham chiếu có thể quay lại đối tượng đã gặp.
- **Tham chiếu dùng chung (shared reference / aliasing):** nhiều cạnh trỏ về **cùng một nút**, không phải nhiều bản sao của nút đó.
- **Danh tính (identity):** nút có một ID ổn định để các cạnh tham chiếu tới, độc lập với nhãn hiển thị hay vị trí trong bộ nhớ.

**Tuần tự hóa (serialization)** biến trạng thái đồ thị thành dữ liệu có thể ghi ra tệp hoặc truyền qua mạng. **Giải tuần tự hóa (deserialization)** đọc dữ liệu đó và khôi phục một đồ thị trong bộ nhớ.

Mục tiêu đúng không phải là giữ nguyên **địa chỉ RAM** hay đối tượng Python cũ sau khi tắt chương trình. Mục tiêu là giữ **danh tính logic của nút** và quan hệ tham chiếu: trong đồ thị vừa khôi phục, mọi liên kết có đích ID B đều trỏ tới **cùng một đối tượng B mới**.

Bài học thuộc chủ đề **Biểu diễn đồ thị**: cách chọn cấu trúc dữ liệu quyết định một đồ thị có thể được lưu, trao đổi và tái dựng **không mất thông tin** hay không.

## 2. Những khái niệm cần phân biệt

Cho đồ thị `G=(V,E)`, trong đó `V` gồm `n` đỉnh và `E` gồm `m` cạnh/cung.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **ID nút** | Đây là nút logic nào? | `"course-A"` |
| **Nhãn/thuộc tính** | Nút hiển thị gì? | `"Nhập môn"` |
| **Tham chiếu đối tượng** | Trong tiến trình hiện tại, biến trỏ vào đối tượng nào? | `node_a.next is node_b` |
| **ID cạnh** | Đây là liên kết cụ thể nào? | `"edge-17"` |
| **Đầu mút cạnh** | Cạnh nối nút nào với nút nào? | `A → B` |
| **Biểu diễn lưu trữ** | Dữ liệu được ghi ra tệp bằng cách nào? | Bảng nút và bảng cạnh trong JSON |

Hai nút có thể có **cùng nhãn**, nhưng **ID khác nhau**:

```text
Nút A: id="a", label="Giới thiệu"
Nút B: id="b", label="Giới thiệu"

A và B là hai nút khác nhau, dù label giống hệt.
```

Ngược lại, một nút C có thể được tham chiếu từ nhiều nơi:

```text
A ───────┐
         ▼
         C
         ▲
B ───────┘

A.next và B.next có thể trỏ tới chính cùng một đối tượng C.
```

Khi phục hồi, không được tạo một bản sao C riêng cho từng cạnh; phải tra bảng `id → object` và dùng chung đối tượng tương ứng.

**Đẳng thức giá trị** (các thuộc tính giống nhau) không đồng nghĩa với **cùng danh tính đối tượng**. Trong Python, `a == b` phụ thuộc cách định nghĩa phép so sánh, còn `a is b` kiểm tra hai biến có trỏ vào **chính một đối tượng** trong bộ nhớ hiện tại hay không.

## 3. Tại sao không nên lưu bằng cách lồng đệ quy mọi nút?

Một cách triển khai tưởng đơn giản:

```python
def chuyen_nut_thanh_dict(nut):
    return {
        "id": nut.id,
        "neighbors": [
            chuyen_nut_thanh_dict(v) for v in nut.neighbors
        ],
    }
```

Nếu có chu trình `A → B → C → A`, hàm sẽ làm:

```text
convert(A)
  convert(B)
    convert(C)
      convert(A)
        convert(B)
          convert(C)
            ...
```

Không có điều kiện dừng theo **nút đã xuất hiện**, nên mã có thể vượt giới hạn đệ quy hoặc không kết thúc.

Ngay cả khi **không có chu trình**, đồ thị dạng hình thoi cũng nguy hiểm cho danh tính:

```text
A → B → D
└ → C → D
```

Nếu chèn toàn bộ nội dung của D vào cả nhánh B và nhánh C, một bộ giải mã ngây thơ có thể tạo **hai đối tượng D**, trong khi đồ thị gốc chỉ có **một**.

Thêm một vấn đề nữa: `json.dumps(node)` **không tự biết** phải xử lý một lớp đối tượng Python tùy biến như thế nào. Nếu ta tự viết bộ mã hóa đệ quy mà không quản lý danh tính, sẽ gặp những lỗi trên.

**Giải pháp nền tảng:** chỉ lưu **mỗi nút đúng một lần**, gán một ID ổn định, và lưu các liên kết bằng **ID đầu mút** thay vì mở rộng lại toàn bộ đối tượng đích.

## 4. Ví dụ xuyên suốt: chu trình, khuyên, cạnh song song và đỉnh cô lập

Xét **đa đồ thị có hướng có trọng số**, với `V={A,B,C,D}` và năm cung:

| Edge ID | Nguồn | Đích | Trọng số | Vai trò |
| --- | --- | --- | ---: | --- |
| `e0` | A | B | 4 | A liên kết tới B |
| `e1` | B | C | 1 | B liên kết tới C |
| `e2` | C | A | 2 | Khép chu trình A→B→C→A |
| `e3` | A | B | 7 | Cung A→B thứ hai, khác ID |
| `e4` | B | B | 0 | Khuyên B→B; trọng số 0 vẫn là cung |

```text
       e0, e3
   A =========> B ------> C
   ^             ↺ e4     |
   |                      |
   +----------------------+
             e2

   D (đỉnh cô lập, không có cung vào/ra)
```

Các tính chất quan trọng:

- Có **4 đỉnh**, gồm D dù D không có cạnh nào.
- Có **5 cung**, dù có hai cung nối cùng cặp đầu mút A→B.
- Có một **chu trình ba đỉnh** A→B→C→A và một **khuyên** B→B.
- B có `indeg(B)=3` (e0, e3, e4) và `outdeg(B)=2` (e1, e4).
- Tổng bậc vào và tổng bậc ra đều bằng `m=5`.

Nếu xuất dữ liệu thành **một bản ghi cho mỗi nút và một bản ghi cho mỗi cung**, ta có thể bảo toàn đầy đủ thông tin này.

## 5. Định dạng JSON: bảng nút + bảng cạnh tham chiếu bằng ID

Một cấu trúc dễ kiểm tra và trung lập với ngôn ngữ lập trình:

```json
{
  "schema_version": 1,
  "directed": true,
  "allow_parallel": true,
  "allow_self_loops": true,
  "vertices": [
    {"id": "A", "label": "Tài nguyên"},
    {"id": "B", "label": "Tài nguyên"},
    {"id": "C", "label": "Nhánh C"},
    {"id": "D", "label": "Cô lập"}
  ],
  "edges": [
    {"id": "e0", "source": "A", "target": "B", "weight": 4},
    {"id": "e1", "source": "B", "target": "C", "weight": 1},
    {"id": "e2", "source": "C", "target": "A", "weight": 2},
    {"id": "e3", "source": "A", "target": "B", "weight": 7},
    {"id": "e4", "source": "B", "target": "B", "weight": 0}
  ]
}
```

**Các quyết định thiết kế trong schema này:**

1. `vertices` là danh sách đối tượng nút. Mỗi phần tử có **ID duy nhất**, nhãn chỉ là thuộc tính hiển thị.
2. `edges` là danh sách **liên kết độc lập**, mỗi liên kết có **edge ID riêng**.
3. `source` và `target` là **tham chiếu ID**, không phải các nút được nhúng đệ quy.
4. `directed` quy định cạnh có phân biệt hướng hay không.
5. `allow_parallel` và `allow_self_loops` quy định những trường hợp mô hình chấp nhận.
6. `schema_version` cho phép trình đọc nhận biết định dạng và từ chối hoặc chuyển đổi phiên bản không hỗ trợ.

JSON là **cây các giá trị**, nên không trực tiếp có khái niệm con trỏ tới **cùng một đối tượng** ở hai vị trí. Các trường `source/target` cùng với bảng `id → node` cung cấp cơ chế tham chiếu **ở cấp ứng dụng**.

**Điều không nên làm:** dùng `label` làm ID, vì A và B ở ví dụ có cùng nhãn. Cũng không nên dùng địa chỉ RAM như `0x...` làm khóa dữ liệu vì địa chỉ có thể thay đổi giữa các lần chạy.

## 6. Quy trình tuần tự hóa: duyệt mỗi đối tượng và phát tham chiếu

Nếu chương trình đã lưu `vertices` và `edges` dạng bảng chuẩn, việc ghi khá trực tiếp:

1. Duyệt mỗi đỉnh và tạo bản ghi `{"id": ..., "label": ...}` **một lần**.
2. Duyệt mỗi cạnh/cung và tạo bản ghi `{"id": ..., "source": source.id, "target": target.id, ...}` **một lần**.
3. Ghi metadata của mô hình và phiên bản schema.
4. Mã hóa cấu trúc thành JSON, rồi ghi ra tệp với UTF-8.

Đồ thị có thể chứa bao nhiêu chu trình tùy ý mà quá trình này **không bao giờ phải theo tham chiếu từ nút này sang nút khác một cách vô hạn**: nội dung cung chỉ ghi ID nguồn và ID đích.

### Nếu dữ liệu đầu vào chỉ là các đối tượng liên kết bằng con trỏ?

Khi chưa có bảng đỉnh/cạnh, cần phát hiện và thu thập các đối tượng đã gặp:

```text
worklist = [root]
seen_nodes = tập danh tính đối tượng đã gặp

while worklist không rỗng:
    u = lấy một đối tượng từ worklist
    if u đã thuộc seen_nodes:
        continue

    đánh dấu u bằng danh tính đối tượng trong tiến trình
    gán/kiểm tra ID ổn định cho u
    xuất đúng một bản ghi nút u

    for mỗi liên kết e có nguồn u:
        xuất bản ghi e theo ID của hai đầu mút
        đưa đối tượng đích vào worklist nếu chưa gặp
```

Bảng `seen_nodes` giúp tránh chu trình và giữ nút dùng chung. **Nhưng còn một giới hạn quan trọng:** chỉ duyệt từ `root` sẽ bỏ mất các đỉnh **không tới được từ root**, như D cô lập trong ví dụ. Muốn lưu **toàn bộ đồ thị**, phải có danh mục đầy đủ `V` hoặc khởi tạo công việc từ tất cả nút đã biết.

Với **đồ thị vô hướng**, cùng một cạnh có thể xuất hiện trong hai danh sách kề; cần đánh dấu **edge ID đã xuất** để không ghi cùng một cạnh thành hai bản ghi. Với **đa đồ thị**, không được đánh dấu cạnh chỉ bằng cặp đầu mút: e0 và e3 cùng A→B nhưng phải được lưu **cả hai**.

## 7. Khôi phục đúng bằng hai pha: tạo nút trước, nối cạnh sau

Khi đọc dữ liệu, lỗi thường gặp là lập tức tạo đối tượng đích mới mỗi khi gặp tham chiếu cạnh. Cách đúng là **khôi phục theo hai pha**.

### Pha 1 — tạo đủ các nút

Đọc toàn bộ `vertices`, tạo **một đối tượng cho mỗi ID**, rồi lưu vào bảng tra:

```text
nodes_by_id = {}

for record in vertices:
    kiểm tra ID chưa trùng
    nodes_by_id[record.id] = Node(record.id, record.label)
```

Sau pha này đã có A, B, C, D, kể cả D cô lập. Chưa cần tạo bất kỳ liên kết nào, nên **không gặp vấn đề thứ tự khai báo**: cạnh C→A vẫn sẽ tìm thấy A dù bản ghi cạnh đến sau hoặc trước các cạnh khác.

### Pha 2 — tạo liên kết giữa các nút đã tồn tại

```text
for record in edges:
    kiểm tra edge ID chưa trùng
    source_node = nodes_by_id[record.source]
    target_node = nodes_by_id[record.target]
    edge = Edge(record.id, source_node, target_node, record.weight)
    thêm edge vào bảng cạnh và chỉ mục kề
```

Tại đây, **không tạo thêm nút A/B/C/D**. Nếu hai cung khác nhau có đích B, chúng đều nhận **cùng con trỏ tới đối tượng B** từ `nodes_by_id["B"]`.

Ví dụ các kiểm tra danh tính trong bộ nhớ sau khi khôi phục:

```python
assert graph.nodes["B"] is graph.edges["e0"].target
assert graph.edges["e0"].target is graph.edges["e3"].target
assert graph.nodes["A"] is graph.edges["e2"].target
assert graph.edges["e4"].source is graph.edges["e4"].target
```

Các kiểm tra này chứng minh **bảo toàn quan hệ tham chiếu ở đồ thị đã khôi phục**. Chúng **không** chứng minh `graph_moi.nodes["A"] is graph_cu.nodes["A"]`; điều đó sẽ sai nếu ta đã tạo một bộ đối tượng mới, và **không phải yêu cầu** của serialization.

## 8. Cấu trúc bản ghi và cài đặt Python minh họa

Ví dụ đầy đủ sau dùng:

- `Node` đại diện **một đối tượng nút**. `@dataclass(eq=False)` tránh đồng nhất hai nút chỉ vì các trường dữ liệu giống nhau; phép `is` dùng để kiểm tra danh tính trong ví dụ.
- `Edge` giữ **tham chiếu trực tiếp tới hai đối tượng Node**.
- `Graph` giữ bảng `nodes` và `edges` theo ID; đồng thời có chỉ mục cung ra/vào cho đồ thị có hướng hoặc tập cạnh liên quan cho đồ thị vô hướng.
- `serialize_graph` xuất ID/thuộc tính, **không mở rộng nội dung đối tượng đích**.
- `deserialize_graph` kiểm tra schema và dựng nút **trước khi** dựng các liên kết.

Mẫu cho phép đồ thị **có hướng hoặc vô hướng**, chặn ID trùng, và làm rõ chính sách **khuyên/cạnh song song**. Mọi trọng số trong mẫu là số hữu hạn; các ứng dụng thực tế cần kiểm tra thêm miền giá trị và đơn vị.

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import isfinite


@dataclass(eq=False)
class Node:
    id: str
    label: str
    outgoing: list[Edge] = field(default_factory=list)
    incoming: list[Edge] = field(default_factory=list)
    incident: list[Edge] = field(default_factory=list)


@dataclass(eq=False)
class Edge:
    id: str
    source: Node
    target: Node
    weight: float


class Graph:
    def __init__(self, directed=True,
                 allow_parallel=True, allow_self_loops=True):
        self.directed = directed
        self.allow_parallel = allow_parallel
        self.allow_self_loops = allow_self_loops
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}

    @staticmethod
    def _check_id(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("ID phải là chuỗi không rỗng")

    def add_node(self, node_id: str, label: str):
        self._check_id(node_id)
        if type(label) is not str:
            raise TypeError("label phải là chuỗi")
        if node_id in self.nodes:
            raise ValueError("ID nút trùng")
        node = Node(node_id, label)
        self.nodes[node_id] = node
        return node

    def add_edge(self, edge_id, source_id, target_id, weight):
        self._check_id(edge_id)
        self._check_id(source_id)
        self._check_id(target_id)
        if edge_id in self.edges:
            raise ValueError("ID cạnh trùng")
        if source_id not in self.nodes or target_id not in self.nodes:
            raise ValueError("Cạnh tham chiếu đỉnh không tồn tại")
        if type(weight) not in (int, float) or not isfinite(weight):
            raise ValueError("Trọng số phải là số hữu hạn")

        source = self.nodes[source_id]
        target = self.nodes[target_id]
        if source is target and not self.allow_self_loops:
            raise ValueError("Không cho phép khuyên")

        if not self.allow_parallel:
            # Bản đơn giản: dò O(m) khi kiểm tra trùng.
            for e in self.edges.values():
                same_way = e.source is source and e.target is target
                reverse = e.source is target and e.target is source
                if same_way or (not self.directed and reverse):
                    raise ValueError("Cặp đầu mút đã có cạnh")

        edge = Edge(edge_id, source, target, weight)
        self.edges[edge_id] = edge

        if self.directed:
            source.outgoing.append(edge)
            target.incoming.append(edge)
        else:
            source.incident.append(edge)
            if target is not source:
                target.incident.append(edge)
        return edge


def serialize_graph(graph: Graph) -> str:
    payload = {
        "schema_version": 1,
        "directed": graph.directed,
        "allow_parallel": graph.allow_parallel,
        "allow_self_loops": graph.allow_self_loops,
        "vertices": [
            {"id": n.id, "label": n.label}
            for n in sorted(graph.nodes.values(), key=lambda n: n.id)
        ],
        "edges": [
            {"id": e.id, "source": e.source.id,
             "target": e.target.id, "weight": e.weight}
            for e in sorted(graph.edges.values(), key=lambda e: e.id)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2,
                      allow_nan=False)


def deserialize_graph(text: str) -> Graph:
    # Từ chối JSON object có khóa trùng (parser mặc định có thể ghi đè).
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Trùng khóa JSON: " + key)
            result[key] = value
        return result

    def reject_nonfinite(token):
        raise ValueError("Hằng số JSON không hợp lệ: " + token)

    data = json.loads(text, object_pairs_hook=reject_duplicate_keys,
                      parse_constant=reject_nonfinite)

    expected = {
        "schema_version", "directed", "allow_parallel",
        "allow_self_loops", "vertices", "edges",
    }
    if type(data) is not dict or set(data) != expected:
        raise ValueError("Schema cấp cao không hợp lệ")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Phiên bản schema không hỗ trợ")
    for name in ("directed", "allow_parallel", "allow_self_loops"):
        if type(data[name]) is not bool:
            raise ValueError(name + " phải là Boolean")
    if type(data["vertices"]) is not list or type(data["edges"]) is not list:
        raise ValueError("vertices và edges phải là mảng")

    graph = Graph(
        data["directed"], data["allow_parallel"],
        data["allow_self_loops"],
    )

    # Pha 1: tạo MỘT Node cho mỗi ID, giữ cả đỉnh cô lập.
    for record in data["vertices"]:
        if type(record) is not dict or set(record) != {"id", "label"}:
            raise ValueError("Bản ghi nút không hợp lệ")
        graph.add_node(record["id"], record["label"])

    # Pha 2: ánh xạ ID đầu mút về cùng các đối tượng Node vừa tạo.
    for record in data["edges"]:
        required = {"id", "source", "target", "weight"}
        if type(record) is not dict or set(record) != required:
            raise ValueError("Bản ghi cạnh không hợp lệ")
        graph.add_edge(
            record["id"], record["source"],
            record["target"], record["weight"],
        )

    return graph


# Chuẩn bị đúng mô hình ví dụ: chu trình, song song, khuyên, cô lập.
g = Graph(directed=True, allow_parallel=True, allow_self_loops=True)
g.add_node("A", "Tài nguyên")
g.add_node("B", "Tài nguyên")  # Nhãn giống A; ID khác.
g.add_node("C", "Nhánh C")
g.add_node("D", "Cô lập")

g.add_edge("e0", "A", "B", 4)
g.add_edge("e1", "B", "C", 1)
g.add_edge("e2", "C", "A", 2)
g.add_edge("e3", "A", "B", 7)
g.add_edge("e4", "B", "B", 0)

text_json = serialize_graph(g)
restored = deserialize_graph(text_json)

assert len(restored.nodes) == 4
assert len(restored.edges) == 5
assert restored.nodes["A"].label == restored.nodes["B"].label
assert restored.nodes["A"] is not restored.nodes["B"]
assert restored.edges["e0"].target is restored.nodes["B"]
assert restored.edges["e0"].target is restored.edges["e3"].target
assert restored.edges["e2"].target is restored.nodes["A"]
assert restored.edges["e4"].source is restored.edges["e4"].target
assert len(restored.nodes["D"].outgoing) == 0
assert len(restored.nodes["B"].incoming) == 3
assert len(restored.nodes["B"].outgoing) == 2

# Đối tượng mới không phải đối tượng cũ trong bộ nhớ:
assert restored.nodes["A"] is not g.nodes["A"]

# Hai bản JSON được chuẩn hóa cùng thứ tự theo ID:
assert serialize_graph(restored) == text_json
print("ROUND_TRIP_OK")  # ROUND_TRIP_OK
```

### Đọc đúng những kiểm tra cuối

- `restored.edges["e0"].target is restored.edges["e3"].target` xác minh rằng hai cung song song **cùng trỏ tới một đối tượng B**, chứ không có hai bản sao B.
- `restored.edges["e4"].source is restored.edges["e4"].target` xác minh khuyên B→B tham chiếu **cùng đối tượng ở hai đầu**.
- `len(restored.nodes)==4` giữ cả D cô lập.
- `serialize_graph(restored)==text_json` kiểm tra tính ổn định của **định dạng đã chuẩn hóa**, không kiểm tra địa chỉ RAM.
- Mẫu dùng `sorted` theo ID nên thuận tiện tạo đầu ra ổn định; **chi phí sắp xếp** phải được cộng khi phân tích thời gian xuất dữ liệu.

**Giới hạn của mã minh họa:** các danh sách chỉ mục và bảng cạnh là thuộc tính công khai; chương trình khác có thể sửa trực tiếp và phá bất biến. Ngoài ra, `add_edge` khi `allow_parallel=False` dò mọi cạnh đã có, khiến thời gian dựng có thể cao hơn tuyến tính. Trong hệ thống lớn cần chỉ mục khóa cặp đầu mút và giao diện cập nhật có kiểm soát.

## 9. Tự kiểm tra sự nhất quán sau khi giải mã

Giải mã thành công về mặt cú pháp **không** chứng minh dữ liệu đúng. Ít nhất phải kiểm tra:

| Bất biến | Điều cần xác minh |
| --- | --- |
| Định danh nút | Mỗi ID trong `vertices` xuất hiện đúng một lần |
| Định danh cạnh | Mỗi `edge.id` duy nhất |
| Đầu mút | `source` và `target` là ID có thật trong bảng nút |
| Hướng | Đồ thị có hướng không tự thêm cung ngược |
| Khuyên | Tuân thủ `allow_self_loops` |
| Cạnh song song | Tuân thủ `allow_parallel` và không gộp các ID hợp lệ |
| Trọng số | Đúng kiểu số và miền giá trị; phân biệt 0 với vắng cạnh |
| Chỉ mục | Mỗi edge ID chỉ xuất hiện đúng ở những nút/chiều tương ứng |
| Đỉnh cô lập | Vẫn tồn tại dù không được cạnh nào nhắc tới |
| Phiên bản | `schema_version` được nhận diện và xử lý đúng |

Với đồ thị có hướng, sau giải mã phải có:

\[
\sum_{v\in V}\operatorname{indeg}(v)
=\sum_{v\in V}\operatorname{outdeg}(v)
=m.
\]

Với đồ thị vô hướng, mỗi cạnh không khuyên có hai đầu mút và khuyên được tính hai lần vào bậc:

\[
\sum_{v\in V}\deg(v)=2m.
\]

Trong mã ví dụ, `outgoing`/`incoming` của đồ thị có hướng và `incident` của đồ thị vô hướng đều được **xây từ bảng cạnh**, thay vì tin một chỉ mục kề được lưu lại từ tệp. Điều đó hạn chế nguy cơ **dữ liệu trùng lặp nhưng lệch nhau**.

**Quan trọng:** chỉ kiểm tra tổng bậc vẫn chưa đủ. Hai cung có thể bị nối sai đầu mút nhưng tổng bậc không thay đổi. Cần kiểm tra **theo từng ID và từng đầu mút**.

## 10. Đồ thị vô hướng và quy tắc bảo toàn một cạnh

Đối với đồ thị vô hướng, cạnh `{u,v}` **không phân biệt thứ tự đầu mút**. Nếu lưu danh sách kề, cạnh A–B thường xuất hiện hai lần: B trong kề của A, A trong kề của B. Nhưng khi ghi **bảng cạnh**, chỉ xuất **một bản ghi cho một edge ID**.

```json
{
  "schema_version": 1,
  "directed": false,
  "allow_parallel": true,
  "allow_self_loops": true,
  "vertices": [
    {"id": "A", "label": "A"},
    {"id": "B", "label": "B"}
  ],
  "edges": [
    {"id": "e0", "source": "A", "target": "B", "weight": 2},
    {"id": "e1", "source": "B", "target": "A", "weight": 5},
    {"id": "e2", "source": "B", "target": "B", "weight": 0}
  ]
}
```

Vì `directed=false`, e0 và e1 là **hai cạnh song song**, không phải hai hướng đi khác nhau. `allow_parallel=true` cho phép chúng cùng tồn tại.

Khi giải mã:

- `incident[A]` chứa e0, e1.
- `incident[B]` chứa e0, e1, e2.
- Khuyên e2 chỉ có **một bản ghi**, được lưu **một ID** trong tập/danh sách incidence của B theo quy ước của mã.
- `deg(A)=2`, `deg(B)=4` vì khuyên đóng góp hai vào bậc B; tổng bậc `6=2m`.

**Không được khử trùng chỉ bằng cặp đầu mút** trong đa đồ thị: e0 và e1 là hai cạnh độc lập. Ngược lại, khi chỉ lưu **đồ thị đơn**, có thể chuẩn hóa cặp ID để nhận biết trùng, nhưng phải xử lý khuyên theo chính sách đã nêu.

Khi cần đầu ra JSON **chuẩn hóa duy nhất** cho một cạnh vô hướng, một chính sách là sắp hai đầu mút theo một thứ tự ID cố định trước khi ghi. Đây là **chuẩn hóa biểu diễn**, không phải đổi hướng của cạnh vì cạnh vô hướng vốn không có hướng. Nếu edge ID là khóa danh tính, việc chuẩn hóa cặp đầu mút **không được gộp** hai edge ID song song.

## 11. Đối tượng dùng chung, bản sao dữ liệu và điều gì không được bảo toàn

Giả sử trong bộ nhớ:

```text
p = Node(id="P")
q = Node(id="Q")
r = Node(id="R")

p -> r
q -> r
```

Sau giải mã đúng:

```python
assert restored_p_edge.target is restored_q_edge.target
```

Điều được giữ là **cùng danh tính logic R** và việc hai tham chiếu cùng dẫn tới **một đối tượng R trong đồ thị mới**.

Nhưng không nên nhầm những loại trạng thái sau:

1. **Địa chỉ bộ nhớ:** không có nghĩa vụ giữ nguyên giữa hai tiến trình.
2. **Đối tượng đồng bộ hoặc handle hệ điều hành:** khóa, socket, tệp đang mở, thread không nên được “khôi phục” như một con trỏ JSON.
3. **Bộ nhớ đệm thuật toán:** `visited`, `parent`, khoảng cách BFS/DFS có thể là kết quả của **một snapshot cũ**, không nên tùy ý xem là thuộc tính bền vững của đồ thị.
4. **Thuộc tính dẫn xuất:** bậc vào/ra, chỉ mục kề hoặc ma trận thường có thể **dựng lại** từ các bản ghi cạnh.
5. **Thứ tự duyệt:** nếu schema không cam kết thứ tự cạnh/láng giềng, các lần khôi phục có thể tạo thứ tự BFS/DFS khác dù quan hệ kề tương đương.

Một định dạng tốt phải nói rõ **những gì thuộc dữ liệu gốc** và **những gì được tính lại**. Không nên ghi tất cả đối tượng nội bộ rồi hy vọng bộ đọc tự phân biệt dữ liệu bền vững với trạng thái tạm thời.

## 12. ID ổn định, phiên bản schema và thứ tự đầu ra

### ID và tên miền định danh

Mỗi ID phải có phạm vi rõ ràng: trong một đồ thị, trong một kho dữ liệu hay trên toàn hệ thống. Nếu gộp hai đồ thị có cùng ID A nhưng là hai nút khác nhau, ta phải giải quyết xung đột bằng **namespace** hoặc quy tắc đổi ID có kiểm soát, đồng thời cập nhật các tham chiếu cạnh.

**Không đổi ID chỉ vì nhãn thay đổi.** Đổi tên khóa học từ “Cấu trúc dữ liệu I” sang “Cấu trúc dữ liệu cơ bản” không có nghĩa là tạo một nút mới, nếu nó vẫn là cùng thực thể.

Nếu ID có thể bị tái sử dụng sau khi xóa nút, một tham chiếu cũ lưu trong tệp có thể bất ngờ trỏ tới nút mới. Có thể dùng ID sinh không tái sử dụng, hoặc thêm **phiên bản/generation** vào khóa tham chiếu nếu bài toán yêu cầu.

### Schema version

`schema_version` giúp bên đọc biết phải hiểu các trường như thế nào. Ví dụ, phiên bản sau có thể tách `weight` thành `distance_km` và `time_min`; khi ấy phải có quy tắc chuyển đổi dữ liệu cũ, không lặng lẽ giả định mọi số đều có cùng đơn vị.

Đối với phiên bản không hỗ trợ, lựa chọn an toàn là **báo lỗi** hoặc chạy một bước migration được định nghĩa rõ. Không nên tự đoán ý nghĩa những trường mới hoặc bị thiếu.

### Đầu ra ổn định và chuẩn hóa

Nếu cần so sánh bản ghi bằng diff, cache hoặc hash:

- Sắp `vertices` theo ID nút.
- Sắp `edges` theo edge ID.
- Quy định cách biểu diễn ID, kiểu trọng số, Unicode và thứ tự khóa JSON.
- Với cạnh vô hướng, có thể chuẩn hóa thứ tự cặp đầu mút.
- Phân biệt **so sánh ngữ nghĩa đồ thị** với **so sánh chuỗi JSON**.

Hai tệp JSON có thể khác thứ tự bản ghi nhưng mô tả **cùng một đồ thị**. Một trình đọc đúng không nên dựa vào thứ tự bản ghi cạnh để quyết định sự tồn tại của đỉnh: tất cả các nút được tạo ở pha đầu trước khi nối các cạnh.

## 13. Chi phí thời gian và bộ nhớ

Giả định mỗi ID/thuộc tính có kích thước hằng số hoặc tính riêng chi phí xử lý chuỗi; gọi `B` là tổng độ dài dữ liệu văn bản/thuộc tính được mã hóa.

| Công việc | Thời gian điển hình | Bộ nhớ |
| --- | --- | --- |
| Xuất `n` nút và `m` cung **không sắp xếp** | `O(n+m+B)` | `O(n+m+B)` cho cấu trúc/chuỗi JSON được tạo |
| Khôi phục hai pha bằng `dict` và chỉ mục cạnh | `O(n+m+B)` **kỳ vọng**, khi xử lý mỗi cung hằng số | `O(n+m+B)` tính cả dữ liệu nhập và đồ thị |
| Dựng danh sách kề/chỉ mục `in/out` từ bảng cung | `O(n+m)` | `O(n+m)` |
| Sắp `n` nút và `m` cung theo ID | `O(n log n + m log m)` phép so sánh | Phụ thuộc thuật toán sắp xếp |
| Dò trùng cặp đầu mút bằng cách quét mọi cạnh đã thêm | Có thể `O(m²)` cho m lần thêm | Không cần chỉ mục phụ |
| Xác thực toàn bộ đầu mút/ID bằng bảng tra băm | `O(n+m)` kỳ vọng | `O(n+m)` cho bảng/chỉ mục |

**Giải thích:** vòng lặp đệ quy ngây thơ không có cận hữu ích khi gặp chu trình vì nó có thể **không kết thúc**. Thiết kế theo bảng nút và bảng cạnh đảm bảo mỗi bản ghi được xét **một số lần hữu hạn**.

Mã `serialize_graph` ở mục 8 **có sắp xếp** theo ID, nên chi phí của nó là khoảng `O(n log n + m log m + B)` với giả định phép so sánh ID đủ rẻ. Khi `allow_parallel=False`, `Graph.add_edge` minh họa bằng cách quét mọi cạnh để kiểm tra cặp trùng, nên tổng thời gian giải mã có thể tăng tới **`O(m²)`**; để đạt `O(n+m)` kỳ vọng, hãy duy trì thêm chỉ mục cặp đầu mút.

Bộ nhớ đồ thị sau khôi phục là `O(n+m)` về số bản ghi: một đối tượng cho mỗi nút, một đối tượng cho mỗi cạnh và các mục chỉ mục kề. Cách lưu đối tượng Python có overhead khác xa một mảng số nguyên nén; **Big-O không dự đoán số byte chính xác**.

## 14. Dữ liệu không tin cậy và lỗi đầu vào

Đọc đồ thị từ tệp của người dùng hay dịch vụ ngoài là một **ranh giới tin cậy**. Những trường hợp cần xử lý gồm:

- **ID nút trùng:** hai bản ghi khác nhau dùng cùng ID, khiến cạnh không rõ trỏ đến thực thể nào.
- **Edge ID trùng:** không thể xác định một cạnh riêng biệt để cập nhật/xóa.
- **Cạnh mồ côi:** `source/target` không tồn tại trong bảng nút.
- **Kiểu dữ liệu sai:** `vertices` không phải mảng, `directed` không phải Boolean, trọng số không phải số hợp lệ.
- **Trọng số đặc biệt:** NaN/Infinity không thuộc JSON chuẩn; nếu dữ liệu từ thư viện chấp nhận các giá trị đó, phải từ chối hoặc có quy tắc riêng.
- **Chuỗi hoặc số quá lớn:** có thể gây tốn RAM/CPU, hoặc vượt giới hạn lưu trữ/chuyển đổi.
- **Tệp khổng lồ:** có thể khai báo hàng triệu nút/cung, cần giới hạn kích thước, số bản ghi và tài nguyên xử lý.
- **Trường JSON trùng tên:** nhiều parser có thể lấy giá trị cuối, làm kiểm tra trở nên khó dự đoán.
- **Phiên bản schema lạ:** không được diễn giải bằng quy tắc của phiên bản khác một cách ngẫu nhiên.
- **Bản ghi cạnh/đỉnh bổ sung không hợp lệ:** không được bỏ qua các trường ảnh hưởng tới danh tính hoặc ngữ nghĩa liên kết khi chưa có quy tắc.

Mẫu Python sử dụng bộ đọc JSON từ thư viện chuẩn, từ chối **khóa JSON trùng**, từ chối phiên bản lạ và chỉ nhận một tập trường cố định. Trong hệ thống sản xuất, nên **giới hạn kích thước dữ liệu trước khi nạp**, kiểm soát lỗi hết tài nguyên, và có chính sách rõ ràng cho phiên bản schema mới.

**Không giải tuần tự hóa `pickle` từ nguồn không tin cậy**: định dạng ấy có thể tái tạo các kiểu đối tượng Python nhưng có rủi ro thực thi mã khi nạp dữ liệu. Một định dạng dữ liệu như JSON cùng bước xác thực ID, kiểu, cạnh và thuộc tính thường phù hợp hơn để trao đổi giữa hệ thống.

## 15. Cập nhật đồ thị và snapshot đã lưu

Giả sử đồ thị đã được xuất ra tệp tại thời điểm T1. Sau đó ứng dụng:

1. Xóa cạnh e2 của chu trình.
2. Thêm nút E.
3. Đổi nhãn của nút A.

Bản JSON từ T1 vẫn mô tả **trạng thái cũ**: còn e2, chưa có E và nhãn A cũ. Đọc lại nó không phải “đồng bộ tự động” với đồ thị đang chạy.

Nếu cần lưu liên tục, hệ thống có thể chọn:

- **Snapshot toàn bộ:** định kỳ xuất lại bảng nút và bảng cạnh của một phiên bản nhất quán.
- **Nhật ký sự kiện (event log):** lưu thao tác thêm/xóa/đổi thuộc tính kèm ID và thứ tự áp dụng; khi khôi phục, nạp snapshot rồi phát lại các thay đổi hợp lệ.
- **Giao dịch:** cập nhật bảng nút, bảng cạnh và những chỉ mục liên quan như một đơn vị nhất quán.
- **Version/revision:** đính kèm số phiên bản của snapshot để tránh ghép bảng nút T1 với bảng cạnh T2.

Nếu một luồng sửa cạnh trong lúc luồng khác xuất bảng nút/cạnh, tệp có thể chứa cạnh trỏ tới nút đã bị xóa hoặc bỏ sót thay đổi. Cần một **snapshot nhất quán** hoặc cơ chế khóa/giao dịch tương đương.

Trên dữ liệu đã khôi phục, các chỉ mục `outgoing/incoming` hoặc `incident` cần được cập nhật nhất quán khi có thêm/xóa cạnh. Không nên tự sửa `edges` nhưng quên xóa ID trong danh sách kề, vì từ đó cả thuật toán BFS/DFS lẫn lần xuất tiếp theo có thể không phản ánh cùng một đồ thị.

## 16. Các lỗi thường gặp

1. **Lưu toàn bộ nút đích lồng trong nút nguồn.** Chu trình có thể dẫn tới đệ quy vô hạn; dùng ID tham chiếu.
2. **Tạo một nút mới cho mỗi lần đọc cạnh.** Hai cạnh cùng trỏ tới B trở thành hai đối tượng B sai danh tính.
3. **Dùng nhãn làm định danh.** Hai nút khác nhau nhưng nhãn giống nhau có thể bị gộp.
4. **Dùng địa chỉ RAM làm ID bền vững.** Địa chỉ không ổn định giữa phiên chạy.
5. **Chỉ duyệt từ một root rồi tuyên bố đã lưu toàn bộ đồ thị.** Các đỉnh cô lập và thành phần không tới được có thể mất.
6. **Nhập cạnh trước khi dựng bảng đỉnh và tự tạo nút đích.** Có thể tạo sai hoặc tạo trùng đối tượng; hãy dựng hai pha.
7. **Khử trùng cạnh bằng cặp đầu mút trong đa đồ thị.** Các edge ID song song bị gộp mất.
8. **Ghi cả hai mục kề của một cạnh vô hướng thành hai cạnh thật.** Sai số cạnh và có thể tạo đa cạnh không mong muốn.
9. **Bỏ khuyên vì source bằng target.** Khuyên là liên kết có thật nếu mô hình cho phép.
10. **Xem trọng số 0 là không có cạnh.** 0 là một giá trị hợp lệ cần lưu riêng với sự tồn tại của cạnh.
11. **Giữ chỉ mục kề trong tệp nhưng không kiểm tra sự phù hợp với bảng cạnh.** Có thể khôi phục trạng thái mâu thuẫn.
12. **Dùng `a == b` như bằng chứng rằng hai biến trỏ cùng một nút.** Cần hiểu định nghĩa bình đẳng; dùng `is` để kiểm tra đồng nhất đối tượng trong Python.
13. **Đòi đồ thị sau giải mã dùng cùng địa chỉ RAM với đồ thị trước đó.** Chỉ cần giữ danh tính logic và các tham chiếu dùng chung trong đồ thị mới.
14. **Tin rằng đầu ra JSON khác thứ tự nghĩa là đồ thị khác.** Cần so sánh ID/cạnh/thuộc tính theo ngữ nghĩa.
15. **Bỏ qua tham chiếu đỉnh không tồn tại.** Cạnh mồ côi phá tính đúng đắn; phải báo lỗi hoặc có chính sách sửa rõ ràng.
16. **Nạp dữ liệu Python tùy ý từ nguồn không tin cậy bằng pickle.** Có rủi ro thực thi mã; dùng định dạng dữ liệu và xác thực phù hợp.
17. **Lưu snapshot không nhất quán khi có cập nhật đồng thời.** Bảng nút và bảng cạnh có thể lệch phiên bản.
18. **Quên độ phức tạp kiểm tra trùng khi cấm cạnh song song.** Dò từng cạnh đã có có thể khiến dựng toàn bộ tăng lên `O(m²)`.

## 17. Tự kiểm tra

**Câu 1.** Với chu trình A→B→C→A, vì sao hàm tự gọi đệ quy lên mọi nút kề có thể không kết thúc?

**Đáp án:** Vì hàm từ C quay lại A rồi lại B, C... mà không có bảng đánh dấu đối tượng đã xử lý. Dùng `seen` hoặc lưu cạnh bằng ID sẽ chặn việc mở rộng lặp vô hạn.

**Câu 2.** Hai nút có cùng nhãn `"Giới thiệu"`, nhưng ID lần lượt `"A"` và `"B"`. Khi giải mã có được gộp chúng không?

**Đáp án:** Không. **ID là danh tính logic**, nhãn chỉ là thuộc tính hiển thị. Phải tạo hai đối tượng riêng cho A và B.

**Câu 3.** Hai cạnh e0 và e3 cùng có đích B. Sau giải mã, phép kiểm tra danh tính nào thể hiện đã dùng chung nút B?

**Đáp án:** `graph.edges["e0"].target is graph.edges["e3"].target` phải là `True`; cả hai cạnh trỏ về đúng một đối tượng B trong đồ thị đã phục hồi.

**Câu 4.** Trong quy trình hai pha, vì sao phải tạo các nút trước khi nối cạnh?

**Đáp án:** Để mọi tham chiếu `source/target` đều có một đối tượng đích đã biết trong bảng `id → object`. Nhờ đó tránh tạo trùng nút và không phụ thuộc thứ tự bản ghi cạnh.

**Câu 5.** Đồ thị ví dụ có bao nhiêu nút, bao nhiêu cung và bao nhiêu cung đi vào B?

**Đáp án:** **4 nút**, **5 cung** (tính cả e0, e3 song song và e4 khuyên), và **3 cung đi vào B** (e0, e3, e4).

**Câu 6.** Nếu chỉ xuất các nút tới được từ A, nút nào trong ví dụ sẽ bị bỏ sót?

**Đáp án:** **D** là đỉnh cô lập. Muốn lưu toàn đồ thị phải có danh mục V độc lập với việc duyệt từ một nguồn.

**Câu 7.** Khi đồ thị vô hướng lưu một cạnh e0={A,B} trong cả danh sách kề A và B, bảng cạnh JSON nên có mấy bản ghi cho e0?

**Đáp án:** **Một** bản ghi cạnh e0. Hai mục kề chỉ là hai chỉ mục của **cùng một cạnh toán học**.

**Câu 8.** Đồ thị vô hướng có hai cạnh e0 và e1 cùng nối A–B. Vì sao không thể khử trùng bản ghi theo cặp đầu mút?

**Đáp án:** Vì e0 và e1 là hai **liên kết độc lập** trong đa đồ thị, có thể có trọng số/thuộc tính khác nhau. Cần giữ cả hai edge ID.

**Câu 9.** Khi khôi phục khuyên B→B, hai trường `source` và `target` phải được ánh xạ tới mấy đối tượng nút?

**Đáp án:** **Một** đối tượng B được dùng cho cả hai đầu mút, không phải hai bản sao của B.

**Câu 10.** Vì sao `restored.nodes["A"] is original.nodes["A"]` thường là `False` sau một lần giải mã độc lập, dù round-trip đúng?

**Đáp án:** Vì deserialization tạo **đối tượng mới**. Nó bảo toàn ID A và cấu trúc tham chiếu **bên trong đồ thị mới**, không bảo toàn con trỏ hay địa chỉ RAM của phiên cũ.

**Câu 11.** Nếu dữ liệu JSON có cạnh `{"source":"A","target":"X"}` nhưng không có đỉnh X, trình đọc nên làm gì?

**Đáp án:** **Từ chối hoặc báo lỗi dữ liệu không nhất quán** theo hợp đồng schema. Không âm thầm tạo đối tượng X ngoài danh mục V nếu mô hình yêu cầu đỉnh khai báo tường minh.

**Câu 12.** Mã xuất dữ liệu có sắp n nút và m cạnh theo ID. Chi phí sắp xếp cần cộng vào là gì?

**Đáp án:** Khoảng `O(n log n + m log m)` phép so sánh ID, ngoài thời gian xử lý và mã hóa nội dung `O(n+m+B)`.

**Câu 13.** Một bản JSON được lưu trước khi xóa một cạnh. Có thể dùng bản đó như trạng thái mới của đồ thị sau thao tác xóa không?

**Đáp án:** Không. Nó là **snapshot cũ**; phải xuất lại snapshot nhất quán hoặc áp dụng nhật ký cập nhật đã được xác thực.

**Câu 14.** Muốn vừa giữ chu trình, vừa bảo toàn danh tính nút, hai quyết định cấu trúc quan trọng nhất là gì?

**Đáp án:** (1) Lưu mỗi nút **một lần theo ID duy nhất**; (2) lưu các cung/cạnh bằng **ID đầu mút**, rồi giải mã bằng **hai pha: tạo nút trước, nối cạnh sau**.

**Ghi nhớ:** Tuần tự hóa đồ thị **không nên mở rộng đệ quy đối tượng đích**. Hãy lưu **bảng nút với ID ổn định** và **bảng cạnh với edge ID cùng ID hai đầu mút**. Khi giải mã, **tạo mỗi nút đúng một lần**, rồi nối các cạnh thông qua bảng `id → object`. Cách này xử lý chu trình, tham chiếu dùng chung, khuyên, cạnh song song và đỉnh cô lập mà không mất danh tính logic. Cần xác thực đầu mút, ID, chính sách hướng/đa cạnh và phiên bản schema, quản lý snapshot khi cập nhật, đồng thời phân biệt **danh tính logic được bảo toàn** với **địa chỉ bộ nhớ không được bảo toàn**.
