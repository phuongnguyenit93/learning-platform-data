# So sánh lưu đối tượng đỉnh với các mảng chỉ số liên tiếp

## 1. Hai cách lưu cùng một đồ thị

Giả sử nền tảng học tập cần lưu hàng chục nghìn tài nguyên, mỗi tài nguyên có một số liên kết tới tài nguyên khác. Khi viết chương trình, có ít nhất hai lựa chọn phổ biến:

- **Đồ thị bằng đối tượng (object graph):** mỗi đỉnh là một đối tượng `Vertex`; liên kết lưu tham chiếu tới những đối tượng đỉnh hoặc đối tượng `Edge` tương ứng.
- **Đồ thị dựa trên chỉ số (index-based graph):** ánh xạ ID nghiệp vụ thành số nguyên `0,1,...,n-1`; liên kết được lưu bằng **chỉ số đỉnh** trong các mảng, có thể nén thành CSR.

Ví dụ cùng một cung `A → B`:

```text
Cách 1: đối tượng và tham chiếu

  object_A.outgoing ───► edge_e0 ───► object_B
                              target

Cách 2: chỉ số và mảng

  id_to_index["A"] = 0          id_to_index["B"] = 1
  offset[0]:offset[1] ───► destination[k] = 1
```

Hai cách lưu có thể biểu diễn **cùng tập đỉnh, cùng tập cạnh và cùng kết quả thuật toán**, nhưng khác nhau ở:

1. Cách giữ **danh tính của đỉnh**.
2. Chi phí cấp phát và số lượng đối tượng trong bộ nhớ.
3. Mức độ **liên tiếp trong bộ nhớ** và khả năng tận dụng cache CPU.
4. Chi phí truy cập theo ID, thêm/xóa đỉnh hoặc cạnh.
5. Sự thuận tiện khi chuyển dữ liệu cho thuật toán, thư viện số, tệp hoặc thiết bị khác.

**Mục tiêu bài học:** hiểu đúng những đánh đổi này, không nhầm **chỉ số mảng** với **ID ổn định**, và biết vì sao hai biểu diễn cùng có cận `O(n+m)` khi BFS/DFS nhưng có thể khác đáng kể về bộ nhớ và hiệu năng thực tế.

## 2. Ba dạng danh tính không được nhầm lẫn

Cho đồ thị `G=(V,E)`, với `n=|V|` và `m=|E|`.

### 2.1. ID logic của đỉnh

Một đỉnh có thể được nhận diện bởi mã nghiệp vụ như `"course-A"`. ID này thường phải **ổn định** khi:

- Đổi nhãn hiển thị.
- Chuyển dữ liệu sang một máy khác.
- Nạp lại đồ thị từ tệp.
- Thay đổi cách đánh số chỉ số mảng.

Hai đỉnh có nhãn giống nhau nhưng ID khác nhau vẫn là **hai đỉnh khác nhau**.

### 2.2. Danh tính đối tượng trong tiến trình

Trong một ngôn ngữ có đối tượng, hai cạnh có thể tham chiếu **cùng một đối tượng đỉnh**:

```python
assert edge0.target is edge2.target
```

Trong Python, `is` kiểm tra **đồng nhất đối tượng** tại thời điểm chạy; `==` có thể chỉ so sánh giá trị, tùy lớp định nghĩa phép so sánh ra sao.

Địa chỉ/danh tính đối tượng trong RAM **không phải** ID bền vững sau khi đóng và mở lại chương trình.

### 2.3. Chỉ số mảng

Nếu đã tạo ánh xạ:

```text
id_to_index = {"A":0, "B":1, "C":2, "D":3, "E":4, "F":5}
index_to_id = ["A", "B", "C", "D", "E", "F"]
```

thì cung `A→B` có thể lưu thành hai chỉ số `(0,1)`.

**Chỉ số 1 chỉ có ý nghĩa trong phiên bản ánh xạ này.** Nếu xóa đỉnh hoặc nén lại các mảng, B có thể được gán chỉ số khác ở snapshot tiếp theo, dù ID `"B"` không đổi.

Bất biến hai chiều:

\[
\operatorname{index\_to\_id}[\operatorname{id\_to\_index}[u]]=u
\]

đối với mọi ID đang hoạt động `u`. Mỗi chỉ số hợp lệ phải ứng với **đúng một đỉnh**, và mỗi ID có **đúng một chỉ số** trong snapshot đó.

## 3. Ví dụ chung: sáu đỉnh, tám cung

Ta dùng **đa đồ thị có hướng**, cho phép cung song song và khuyên, để kiểm tra rằng hai cách lưu không làm mất thông tin:

```text
V = {A, B, C, D, E, F}

A --e0(4)--> B      A --e1(2)--> C
A --e2(7)--> B      B --e3(3)--> D
C --e4(6)--> D      D --e5(1)--> E
E --e6(0)--> E      E --e7(5)--> A

F: đỉnh cô lập
```

| Edge ID | Nguồn | Đích | Trọng số | Ý nghĩa |
| --- | --- | --- | ---: | --- |
| `e0` | A | B | 4 | Cung A→B thứ nhất |
| `e1` | A | C | 2 | Một cung khác từ A |
| `e2` | A | B | 7 | Song song với e0 |
| `e3` | B | D | 3 | |
| `e4` | C | D | 6 | |
| `e5` | D | E | 1 | |
| `e6` | E | E | 0 | Khuyên trọng số 0 |
| `e7` | E | A | 5 | Tạo chu trình A→B→D→E→A |

Các danh sách cung đi ra theo thứ tự thêm:

```text
out[A] = [(B,e0), (C,e1), (B,e2)]
out[B] = [(D,e3)]
out[C] = [(D,e4)]
out[D] = [(E,e5)]
out[E] = [(E,e6), (A,e7)]
out[F] = []
```

Có `n=6`, `m=8`. Bậc ra là `[3,1,1,1,2,0]`; bậc vào là `[1,2,1,2,2,0]`, tổng mỗi loại bằng 8.

BFS theo **hướng cung đi ra** từ A, xét láng giềng theo thứ tự trên, cho thứ tự `A,B,C,D,E`. F không tới được.

Những điều phải giữ qua cả hai biểu diễn:

- `e0` và `e2` đều nối A→B nhưng là **hai cung có ID và trọng số khác nhau**.
- Khuyên `e6=E→E` vẫn là **một cung**, không biến mất vì trọng số 0.
- Cung `e7=E→A` không cho phép tự thêm cung A→E.
- F tồn tại dù không tham gia cung nào.
- B là **một đỉnh logic**, bất kể có bao nhiêu cạnh trỏ tới nó.

## 4. Cách 1: mỗi đỉnh và mỗi cạnh là một đối tượng

Một cách cài đặt trực tiếp:

```python
from dataclasses import dataclass, field

@dataclass(eq=False)
class Vertex:
    id: str
    outgoing: list["Edge"] = field(default_factory=list)

@dataclass(eq=False)
class Edge:
    id: int
    source: Vertex
    target: Vertex
    weight: float
```

`Vertex` có danh sách các đối tượng `Edge` đi ra. Mỗi `Edge` tham chiếu tới một đối tượng nguồn và một đối tượng đích.

**Khi nào cách này thuận tiện?**

- Mô hình nghiệp vụ có nhiều hành vi hoặc thuộc tính riêng của nút: tên học phần, quyền truy cập, trạng thái hiển thị.
- Cần thao tác trực tiếp với các đối tượng đã có trong nhiều thành phần của chương trình.
- Đồ thị được cập nhật theo từng thực thể, mỗi đỉnh có danh sách kề có thể mở rộng.
- Dễ gắn phương thức, quy tắc kiểm tra và điều kiện nghiệp vụ vào lớp đối tượng.

**Nhưng có các chi phí cần tính:**

- Mỗi đối tượng thường có phần quản lý riêng: header, kiểu, trạng thái tham chiếu, các trường và đôi khi từ điển thuộc tính.
- Mỗi `list` có phần metadata và có thể dự phòng dung lượng.
- Khi duyệt từ A tới B, CPU có thể phải lần theo nhiều tham chiếu: danh sách → `Edge` → `Vertex`.
- Các đối tượng có thể nằm ở nhiều vùng nhớ khác nhau, khó bảo đảm tính cục bộ bộ nhớ.
- Khi dùng Python hoặc môi trường có garbage collector, nhiều đối tượng sống lâu và nhiều tham chiếu có thể phát sinh thêm chi phí quản lý bộ nhớ.

Một **đồ thị bằng đối tượng** không nhất thiết là “xấu”: với dữ liệu vừa phải, khả năng thiết kế dễ hiểu và cập nhật thuận tiện có thể quan trọng hơn tối ưu vài byte. Một lớp dùng `__slots__`, cấu trúc đối tượng gọn, bộ cấp phát chuyên dụng hoặc một bảng tra kề phụ cũng có thể cải thiện hiệu năng.

### Cùng đích nghĩa là cùng đối tượng

Với hai cung song song `e0` và `e2` cùng A→B, phiên bản bằng đối tượng phải bảo đảm:

```python
assert edge0.target is edge2.target
```

Không được tạo một bản sao đối tượng B mới cho mỗi cung. Nếu có chu trình, việc lưu trực tiếp tham chiếu vẫn có thể mô tả đồ thị chính xác trong RAM, nhưng khi **tuần tự hóa**, cần dùng bảng ID nút và bảng cạnh, không mở rộng đệ quy toàn bộ đối tượng đích.

## 5. Cách 2: mảng chỉ số, bảng ánh xạ và các đoạn CSR

Với ID đỉnh là chuỗi, trước tiên tạo một ánh xạ sang các chỉ số liên tiếp:

```text
index_to_id = [A, B, C, D, E, F]
id_to_index[A] = 0
id_to_index[B] = 1
...
id_to_index[F] = 5
```

Một cách lưu là danh sách kề dạng chỉ số: `adj[0]=[1,2,1]`, `adj[1]=[3]`, v.v.

Nếu muốn đặt mọi cung vào **một mảng liên tiếp**, có thể dùng **CSR (Compressed Sparse Row)**:

- `row_ptr`: `n+1` offset; đoạn của đỉnh `u` nằm trong `[row_ptr[u], row_ptr[u+1])`.
- `col_idx`: chỉ số **đích** của mỗi cung.
- `edge_id`: ID của từng cung; không gộp các cung song song.
- `weight`: trọng số tại **cùng vị trí** với `col_idx` và `edge_id`.

Với ví dụ sáu đỉnh, tám cung:

```text
index_to_id = [A, B, C, D, E, F]

row_ptr   = [0, 3, 4, 5, 6, 8, 8]
vị trí k       0  1  2  3  4  5  6  7
col_idx   =  [1, 2, 1, 3, 3, 4, 4, 0]
edge_id   =  [0, 1, 2, 3, 4, 5, 6, 7]
weight    =  [4, 2, 7, 3, 6, 1, 0, 5]
```

Kiểm tra:

- A (chỉ số 0) có đoạn `[0,3)`, nên cung ra có các chỉ số đích `[1,2,1]`.
- D (chỉ số 3) có đoạn `[5,6)`: một cung tới E.
- E (chỉ số 4) có đoạn `[6,8)`, chứa cung khuyên `4→4` và cung `4→0`.
- F (chỉ số 5) có đoạn `[8,8)`, rỗng nhưng vẫn giữ vị trí trong tập V.
- Mỗi cung vẫn có một ID và một trọng số riêng.

Bất biến:

\[
\begin{aligned}
&len(row\_ptr)=n+1,\\
&row\_ptr[0]=0,\quad row\_ptr[n]=m,\\
&row\_ptr[u]\le row\_ptr[u+1],\\
&len(col\_idx)=len(edge\_id)=len(weight)=m.
\end{aligned}
\]

Trong **đồ thị có hướng**, CSR thường nhóm cung **đi ra**. Nếu cần liệt kê nhanh cung **đi vào**, có thể thêm CSC hoặc chỉ mục ngược. Với đồ thị vô hướng, mỗi cạnh không khuyên thường được biểu diễn thành **hai mục kề đối ứng**, dù vẫn là **một cạnh toán học**.

## 6. Mảng chỉ số có thật sự nằm liên tiếp trong bộ nhớ?

Điểm cần phân biệt: `list` của Python và **mảng số nguyên đóng gói** không giống nhau.

```python
neighbors_as_list = [1, 2, 1]
# list thường giữ các tham chiếu tới đối tượng int.

from array import array
neighbors_packed = array("I", [1, 2, 1])
# array giữ các giá trị số nguyên theo một kiểu máy liên tiếp.
```

Một `list[int]` của Python có các **ô tham chiếu** liên tiếp nhưng các đối tượng `int` không nhất thiết nằm liền nhau. Vì thế, chỉ đổi ID từ chuỗi sang số nguyên mà vẫn lưu bằng vô số đối tượng Python **chưa đạt tối đa lợi ích bộ nhớ** của mảng số được đóng gói.

Trong các thư viện mảng typed array, NumPy hoặc ngôn ngữ biên dịch, các phần tử có thể chiếm kích thước cố định và nằm sát nhau. Khi đó, CPU có thể đọc các đoạn `col_idx` liên tiếp hiệu quả hơn.

**Cẩn thận với kích thước kiểu:** `array("I")` là số nguyên không dấu, nhưng số byte thực phụ thuộc nền tảng và có thể kiểm tra bằng `array("I").itemsize`. Nếu số đỉnh/cung vượt miền biểu diễn của chỉ số đang chọn, phải dùng kiểu rộng hơn. Không nên tự động giả định mọi `"I"` luôn là 4 byte trên mọi hệ thống.

### AoS và SoA

Hai cách tổ chức thường được nhắc tới:

- **AoS (Array of Structures):** một dãy bản ghi, mỗi bản ghi giữ cùng nhau `(target, edge_id, weight)`.
- **SoA (Structure of Arrays):** các trường được tách thành mảng `col_idx[k]`, `edge_id[k]`, `weight[k]`.

```text
AoS: [(B,e0,4), (C,e1,2), (B,e2,7), ...]
SoA: target = [B, C, B, ...]
     id     = [e0,e1,e2,...]
     weight = [4, 2, 7, ...]
```

CSR thường được cài theo hướng **SoA**, nhưng **CSR** là cách nhóm và đánh dấu đoạn hàng; còn **AoS/SoA** là cách sắp xếp các trường dữ liệu. Chúng là **hai chiều lựa chọn có liên quan nhưng không đồng nhất**.

Nếu thuật toán chỉ cần **đích** để duyệt BFS, có thể đọc riêng `col_idx` mà không kéo toàn bộ trọng số vào cache. Nếu thuật toán cần **cả ID và trọng số mỗi lần**, lợi thế có thể khác. Không có cấu hình tốt nhất cho mọi workload.

## 7. Bộ nhớ: cùng Big-O nhưng khác hệ số hằng

Với `n` đỉnh, `m` cung và các ID số nguyên có kích thước cố định, hai kiểu cài cơ bản đều có thể dùng `O(n+m)` phần tử:

- **Đồ thị bằng đối tượng:** `n` đối tượng nút, `m` đối tượng cung, các tham chiếu trong danh sách kề và bảng ID.
- **CSR đóng gói:** `n+1` offset, `m` chỉ số đích, có thể thêm `m` ID cung và `m` trọng số, cùng ánh xạ ID nghiệp vụ.

Nhưng **Big-O không cho biết chính xác số byte**.

### Một phép tính dung lượng thô

Giả sử đồ thị có hướng có:

\[
n=100\,000,\qquad m=300\,000.
\]

Giả định tất cả phần tử ở các mảng kết quả dùng:

- `row_ptr`: **4 byte/offset**.
- `col_idx`: **4 byte/chỉ số đích**.
- `edge_id`: **4 byte/ID cung**.
- `weight`: **8 byte/trọng số**.

Dung lượng **thô** của bốn mảng CSR là:

\[
\begin{aligned}
B&=4(n+1)+4m+4m+8m\\
 &=4(100\,001)+16(300\,000)\\
 &=5\,200\,004\text{ byte}\approx5{,}2\text{ MB}.
\end{aligned}
\]

Đây là **MB thập phân** và **chưa tính** ID chuỗi, `id_to_index`, bảng danh tính, metadata, overhead đối tượng, cấp phát dự phòng và bản sao trong quá trình chuyển đổi. Nếu không cần lưu `edge_id` hoặc `weight`, dữ liệu thô có thể nhỏ hơn. Nếu phải dùng offset 8 byte hoặc chỉ số 8 byte, dung lượng tăng.

Ở phiên bản **đối tượng**, mỗi `Vertex`/`Edge` có thể cần vùng cấp phát riêng, tham chiếu và metadata. Không thể kết luận chính xác “gấp bao nhiêu lần” chỉ từ `n,m`; phải đo với **runtime, lớp đối tượng, loại collection và dữ liệu thực tế**.

**Điểm mấu chốt:** mảng đóng gói giúp ta kiểm soát trực tiếp số byte trên mỗi phần tử, nhưng không tự bỏ được nhu cầu quản lý **ID nghiệp vụ, thuộc tính linh hoạt và phiên bản đồ thị**.

## 8. Truy cập và tính cục bộ bộ nhớ

Hãy hình dung BFS xử lý đỉnh `u`, rồi duyệt các cung ra:

**Với đối tượng:**

```text
object u
   │
   ▼
list outgoing ──► pointer Edge0 ──► Edge0.target ──► object v
              └─► pointer Edge1 ──► Edge1.target ──► object w
```

**Với CSR:**

```text
u là index
offset[u], offset[u+1]
          │
          ▼
col_idx[k], col_idx[k+1], col_idx[k+2], ...
          │
          ▼
visited[index] / parent[index] / distance[index]
```

Đối với CSR, **các đích của cùng một đỉnh** nằm liên tiếp trong bộ nhớ nếu được lưu bằng mảng đóng gói. CPU có thể tận dụng **cache line, prefetching và truy cập tuần tự** tốt hơn so với nhiều bước lần theo con trỏ.

Tuy nhiên, một đồ thị vẫn có liên kết không đều: từ đỉnh `u` ta có thể nhảy sang các đỉnh với chỉ số ở rất xa nhau. Do đó:

- **Vùng mảng cung** có thể rất liên tiếp.
- **Trạng thái `visited`/`parent` theo chỉ số đích** vẫn có thể bị truy cập rải rác.
- Hiệu quả cache còn phụ thuộc phân bố bậc, thứ tự ID, phần cứng, cách cài đặt queue, kiểu dữ liệu và độ lớn đồ thị.

Mảng chỉ số **không bảo đảm BFS luôn nhanh hơn** biểu diễn đối tượng trong mọi trường hợp. Chuyển đổi ID, xây CSR, cấp phát snapshot hoặc truy vấn thuộc tính nút có thể chiếm chi phí lớn. Khi tính đúng quan trọng hơn vài phần trăm thời gian, mô hình đối tượng rõ ràng có thể là lựa chọn tốt.

## 9. So sánh độ phức tạp thao tác

Giả sử:

- Đồ thị có hướng, `d^+(u)` là số **cung đi ra** từ `u` (tính cả cung song song).
- Phiên bản đối tượng dùng một `list` cạnh đi ra, bảng đỉnh `dict` theo ID và bảng cung theo ID nếu cần.
- Phiên bản mảng dùng **CSR đóng gói**, `row_ptr` và `col_idx`; bảng `id_to_index` dùng băm.
- Với CSR, việc chèn/xóa trực tiếp phải giữ các đoạn liên tiếp, không có lớp delta.
- Phép băm ID và thao tác truy cập mảng được xem là `O(1)` theo mô hình phù hợp; với hash là **kỳ vọng**.

| Thao tác | Đối tượng + list cung ra | Chỉ số + CSR đóng gói |
| --- | --- | --- |
| Lấy đỉnh theo ID | `O(1)` kỳ vọng qua `dict` | `O(1)` kỳ vọng qua `id_to_index` |
| Lấy cung ra từ u | `\Theta(d^+(u))` | `\Theta(d^+(u))` |
| Lấy bậc ra | `O(1)` nếu `len(outgoing)` | `O(1)` từ hiệu hai offset |
| Kiểm tra có cung u→v | `O(d^+(u))` nếu quét list | `O(d^+(u))` nếu đoạn chưa sắp |
| BFS/DFS toàn đồ thị | `O(n+m)` | `O(n+m)` |
| Thêm cung vào cuối list của nguồn | `O(1)` phân bổ, nếu đã kiểm tra ID/chính sách | Có thể `O(n+m)` khi cần dời mảng và offset |
| Xóa cung theo ID | Tùy chỉ mục: lọc list có thể `O(d^+(u))` | Có thể `O(n+m)` khi nén lại |
| Thêm đỉnh cô lập | Thường `O(1)` kỳ vọng/phân bổ cho bảng đối tượng | Rẻ nếu nối cuối, đắt nếu đổi chỉ số/nén lại |
| Xóa đỉnh | Phải dọn **cả cung vào và cung ra**; tùy chỉ mục | Thường phải sửa ánh xạ và tái cấu trúc mảng |
| Đọc thuộc tính phức tạp của nút | Thuận tiện qua đối tượng | Có thể cần tra bảng phụ theo chỉ số/ID |

**Hai điểm không nên suy diễn:**

1. Nếu biểu diễn bằng đối tượng có thêm **hash set láng giềng** hoặc chỉ mục `(u,v)`, kiểm tra tồn tại cung có thể nhanh hơn `O(d^+(u))` theo kỳ vọng. Không phải mọi object graph đều dùng list tuyến tính.
2. Một CSR **có delta, khoảng trống hoặc cập nhật theo lô** có thể cập nhật rẻ hơn cách chèn trực tiếp nêu ở bảng. Cận `O(n+m)` mô tả **trường hợp xấu của mảng packed truyền thống**, không phải mọi biến thể.

### BFS/DFS vẫn cần cấu trúc trạng thái

Với object graph, có thể đánh dấu đối tượng bằng một `set` hoặc lưu bảng `visited[id]`. Với mảng chỉ số, có thể dùng:

```text
visited = bytearray(n)
parent = [-1] * n
distance = [-1] * n
```

Đánh dấu theo chỉ số giúp vùng trạng thái có kích thước và bố cục dễ dự đoán. Cần lưu lại `index_to_id` để **trả kết quả cho người dùng bằng ID gốc**, không trả một chỉ số snapshot không có ngữ cảnh.

## 10. Python: cùng dữ liệu, hai biểu diễn và một kết quả BFS

Chương trình hoàn chỉnh sau xây đồ thị bằng đối tượng trước, sau đó **xuất một snapshot CSR** gồm các mảng kiểu số. Đây là minh họa trong Python 3.10+ sử dụng `dataclass(slots=True)`.

Để công bằng về **ngữ nghĩa**, hai lượt BFS:

- Duyệt cung đi ra theo cùng thứ tự trong từng đỉnh.
- Đánh dấu một đỉnh ngay khi đưa vào queue.
- Trả về ID nghiệp vụ và bảng cha, không chỉ chỉ số nội bộ.

**Không sử dụng mã này để khẳng định tốc độ thực tế:** tạo snapshot và đo các loại đối tượng Python có thêm overhead; phần so sánh ở đây kiểm chứng **tính đúng của dữ liệu và truy vấn**, không phải benchmark.

```python
from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass, field
from math import isfinite


@dataclass(eq=False, slots=True)
class Dinh:
    ma: str
    canh_ra: list[Cung] = field(default_factory=list)


@dataclass(eq=False, slots=True)
class Cung:
    eid: int
    nguon: Dinh
    dich: Dinh
    trong_so: float


class DoThiDoiTuong:
    def __init__(self):
        self.dinh: dict[str, Dinh] = {}
        self.cung: list[Cung] = []

    def them_dinh(self, ma: str) -> Dinh:
        if not isinstance(ma, str) or not ma:
            raise ValueError("ID đỉnh phải là chuỗi không rỗng")
        if ma in self.dinh:
            raise ValueError("Đỉnh đã tồn tại")
        v = Dinh(ma)
        self.dinh[ma] = v
        return v

    def them_cung(self, u: str, v: str, trong_so=1) -> Cung:
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Nguồn hoặc đích không tồn tại")
        if type(trong_so) not in (int, float) or not isfinite(trong_so):
            raise ValueError("Trọng số phải là số hữu hạn")

        # Cấp ID liên tục cho ví dụ; cho phép cung song song và khuyên.
        e = Cung(
            eid=len(self.cung),
            nguon=self.dinh[u],
            dich=self.dinh[v],
            trong_so=float(trong_so),
        )
        self.cung.append(e)
        e.nguon.canh_ra.append(e)
        return e


@dataclass(slots=True)
class CSRSnapshot:
    index_to_id: list[str]
    id_to_index: dict[str, int]
    row_ptr: array
    col_idx: array
    edge_id: array
    weight: array


def tao_csr(g: DoThiDoiTuong) -> CSRSnapshot:
    # Thứ tự theo ID ổn định trong snapshot.
    ids = sorted(g.dinh)
    pos = {ma: i for i, ma in enumerate(ids)}
    n = len(ids)
    m = len(g.cung)

    # Pass 1: bậc ra -> tổng tiền tố -> offset.
    row_ptr = array("I", [0])
    for ma in ids:
        row_ptr.append(row_ptr[-1] + len(g.dinh[ma].canh_ra))
    if row_ptr[-1] != m:
        raise ValueError("Chỉ mục cung ra không khớp bảng cung")

    # Pass 2: rải đích, ID và trọng số vào cùng vị trí.
    col_idx = array("I", [0]) * m
    edge_id = array("I", [0]) * m
    weight = array("d", [0.0]) * m
    cursor = list(row_ptr[:-1])

    for ma in ids:
        u = pos[ma]
        for edge in g.dinh[ma].canh_ra:
            if edge.nguon is not g.dinh[ma]:
                raise ValueError("Chỉ mục cung đi ra sai nguồn")
            k = cursor[u]
            cursor[u] += 1
            col_idx[k] = pos[edge.dich.ma]
            edge_id[k] = edge.eid
            weight[k] = edge.trong_so

    if any(cursor[i] != row_ptr[i + 1] for i in range(n)):
        raise ValueError("Dữ liệu CSR không nhất quán")

    return CSRSnapshot(ids, pos, row_ptr, col_idx, edge_id, weight)


def bfs_doi_tuong(g: DoThiDoiTuong, start_id: str):
    start = g.dinh[start_id]
    seen = {start}           # eq=False: kiểm tra chính đối tượng
    parent = {start: None}
    queue = deque([start])
    order = []

    while queue:
        u = queue.popleft()
        order.append(u.ma)
        for edge in u.canh_ra:
            v = edge.dich
            if v not in seen:
                seen.add(v)  # Đánh dấu khi enqueue
                parent[v] = u
                queue.append(v)

    return order, {
        v.ma: (p.ma if p is not None else None)
        for v, p in parent.items()
    }


def bfs_csr(g: CSRSnapshot, start_id: str):
    n = len(g.index_to_id)
    start = g.id_to_index[start_id]
    seen = bytearray(n)
    seen[start] = 1
    parent = [-1] * n
    queue = deque([start])
    order = []

    while queue:
        u = queue.popleft()
        order.append(u)
        for k in range(g.row_ptr[u], g.row_ptr[u + 1]):
            v = g.col_idx[k]
            if not seen[v]:
                seen[v] = 1
                parent[v] = u
                queue.append(v)

    return (
        [g.index_to_id[i] for i in order],
        {
            g.index_to_id[i]: (
                None if parent[i] == -1
                else g.index_to_id[parent[i]]
            )
            for i in order
        },
    )


g = DoThiDoiTuong()
for ma in "ABCDEF":
    g.them_dinh(ma)

for u, v, w in [
    ("A", "B", 4),  # e0
    ("A", "C", 2),  # e1
    ("A", "B", 7),  # e2: song song e0
    ("B", "D", 3),  # e3
    ("C", "D", 6),  # e4
    ("D", "E", 1),  # e5
    ("E", "E", 0),  # e6: khuyên có trọng số 0
    ("E", "A", 5),  # e7: tạo chu trình
]:
    g.them_cung(u, v, w)

csr = tao_csr(g)
print(csr.index_to_id)          # ['A', 'B', 'C', 'D', 'E', 'F']
print(list(csr.row_ptr))        # [0, 3, 4, 5, 6, 8, 8]
print(list(csr.col_idx))        # [1, 2, 1, 3, 3, 4, 4, 0]
print(list(csr.edge_id))        # [0, 1, 2, 3, 4, 5, 6, 7]
print(list(csr.weight))         # [4.0, 2.0, 7.0, 3.0, 6.0, 1.0, 0.0, 5.0]

print(g.cung[0].dich is g.cung[2].dich)  # True: dùng chung B
print(g.cung[6].nguon is g.cung[6].dich)  # True: khuyên E->E
print(g.cung[7].dich is g.dinh["A"])      # True: chu trình về A
print(len(g.dinh["F"].canh_ra))           # 0: đỉnh cô lập

print(bfs_doi_tuong(g, "A"))
# (['A', 'B', 'C', 'D', 'E'],
#  {'A': None, 'B': 'A', 'C': 'A', 'D': 'B', 'E': 'D'})

print(bfs_csr(csr, "A"))
# (['A', 'B', 'C', 'D', 'E'],
#  {'A': None, 'B': 'A', 'C': 'A', 'D': 'B', 'E': 'D'})

print(bfs_doi_tuong(g, "F")[0])  # ['F']
print(bfs_csr(csr, "F")[0])      # ['F']
print(csr.col_idx.itemsize, csr.weight.itemsize)
# Kích thước phần tử thực tế theo nền tảng, thường là 4 và 8 byte.
```

### Vì sao các kết quả phải giống nhau?

Từ A, cả hai cách lưu đều duyệt các cung theo thứ tự `A→B, A→C, A→B`. B được đánh dấu ở lần gặp đầu tiên, cung song song không làm B vào queue lần nữa.

Từ B, chương trình phát hiện D; từ C, cung tới D đã được phát hiện; từ D phát hiện E. Cung khuyên E→E và cung E→A không tạo thêm đỉnh mới. F không được phát hiện từ A, nhưng BFS **bắt đầu tại F** vẫn trả `["F"]`.

Cây cha tương ứng:

```text
        A
       / \
      B   C
      |
      D
      |
      E

F: chưa tới được từ A
```

Trong bản CSR, mỗi `Edge` trở thành **một vị trí `k` trong các mảng song song**. Vì có `edge_id[k]`, ta vẫn biết hai vị trí cùng đích B là hai cung riêng e0 và e2. Nếu bỏ mảng ID, BFS vẫn tìm đúng **tập đỉnh tới được**, nhưng không còn xác định từng cung gốc khi có song song.

**Giới hạn mã:** ví dụ chỉ xây snapshot một chiều (cung đi ra), chưa hỗ trợ xóa cạnh/đỉnh, chưa có chỉ mục cung đi vào và chưa xử lý dữ liệu đồng thời. `array("I")` yêu cầu chỉ số/ID không âm nằm trong miền kiểu máy; nếu đồ thị vượt giới hạn phải đổi kiểu. Mã `tao_csr` cũng **sắp xếp ID đỉnh**, nên chi phí dựng gồm thêm sắp xếp, không chỉ tổng tiền tố.

## 11. Cách thêm/xóa đỉnh làm thay đổi đánh đổi

### 11.1. Đồ thị bằng đối tượng

Thêm một đỉnh thường gồm tạo đối tượng mới và đưa vào bảng `nodes[id]`; với dictionary, chi phí tra/chèn thường `O(1)` kỳ vọng.

Thêm một cung thường gồm tạo đối tượng cạnh và `append` vào danh sách của nguồn, `O(1)` phân bổ nếu không phải dò trùng hoặc cập nhật nhiều chỉ mục.

Nhưng **xóa đỉnh** phải xử lý **cả cung đi ra và cung đi vào**, không chỉ xóa đối tượng khỏi bảng đỉnh. Nếu còn đối tượng cạnh giữ tham chiếu tới nút đã “xóa”, nút có thể vẫn sống trong RAM và dữ liệu đồ thị bị mâu thuẫn. Một chỉ mục `incoming` hoặc `edge_id→edge` có thể giúp truy tìm nhanh các cạnh cần xóa.

Nếu cạnh/cung song song tồn tại, xóa phải theo **edge ID** để không xóa nhầm toàn bộ các cung có cùng cặp đầu mút.

### 11.2. CSR đóng gói

Một cung mới phải được đặt đúng đoạn nguồn trong `col_idx` và các mảng song song. Trong một mảng packed không có khoảng trống, có thể phải **dịch chuyển `O(m)` mục** và sửa `O(n)` offset, nên thao tác chèn/xóa có thể có cận **`O(n+m)` trường hợp xấu**.

Thêm đỉnh cô lập **ở cuối** một snapshot có thể đơn giản là thêm một offset cuối bằng offset trước, nếu không cần thay đổi ánh xạ. Nhưng thêm đỉnh vào giữa thứ tự chỉ số, xóa đỉnh, hoặc đổi ánh xạ có thể buộc tái tạo nhiều phần dữ liệu.

CSR thường phù hợp để **đọc nhiều, cập nhật ít**. Một hệ thống có thể lưu **đồ thị đối tượng hoặc bảng cạnh động** làm bản chuẩn, rồi xuất snapshot CSR cho các lần phân tích lớn.

## 12. Xóa đỉnh và nguy cơ chỉ số cũ trỏ sai đối tượng

Giả sử đang có:

```text
index_to_id = [A, B, C, D]
               0  1  2  3
```

Nếu xóa B rồi **dồn mảng sang trái**, kết quả là:

```text
index_to_id = [A, C, D]
               0  1  2
```

Lúc này C đổi từ chỉ số **2 sang 1**, D đổi từ **3 sang 2**. Bất kỳ cấu trúc `parent`, `visited`, `distance` hay `col_idx` cũ nào giữ những chỉ số này có thể bị đọc sai.

Không thể chỉ `del index_to_id[1]` rồi mặc kệ `col_idx` và `id_to_index`. Cần có một trong các chính sách:

1. **Tái lập chỉ số:** xây lại toàn bộ ánh xạ và những mục chỉ số liên kết, thường cùng việc tái dựng CSR.
2. **Giữ chỗ trống (tombstone):** không tái sử dụng chỉ số ngay; duy trì cờ hoạt động và lọc những đỉnh/cung đã bị xóa.
3. **Thay bằng phần tử cuối (swap-delete):** tránh dồn cả mảng đỉnh nhưng phải cập nhật **mọi tham chiếu tới phần tử được đổi vị trí**.
4. **Chỉ số kèm thế hệ (generation handle):** lưu `(index,generation)` để phát hiện tham chiếu cũ khi tái sử dụng slot; cần hỗ trợ kiểm tra generation ở nơi tra cứu.

**Không nhầm ID ổn định với index.** Một API công khai thường nên trả về **ID nghiệp vụ**, hoặc một handle có kiểm soát phiên bản, thay vì làm lộ số chỉ mục nội bộ của snapshot.

Đối tượng cũng có vấn đề tham chiếu cũ: xóa B khỏi bảng `nodes` không tự vô hiệu hóa một biến Python nơi khác đang giữ `object_B`. Đây là lý do cần **quản lý vòng đời và quy tắc tính hợp lệ**, bất kể chọn đối tượng hay mảng.

## 13. Snapshot, cập nhật và mô hình kết hợp

Trong ứng dụng thực, một kiến trúc cân bằng có thể là:

```text
Bản chuẩn động
  ├─ vertices_by_id
  ├─ edges_by_id
  └─ chỉ mục kề để thêm/xóa và kiểm tra hợp lệ
          │
          │ build snapshot
          ▼
Snapshot phân tích
  ├─ index_to_id + id_to_index
  ├─ CSR row_ptr + col_idx
  ├─ edge_id + weight
  └─ BFS/DFS/Dijkstra trên mảng số
```

Lợi ích:

- **Thêm/xóa** được xử lý trên cấu trúc có giao diện cập nhật rõ ràng.
- **Duyệt hàng loạt** chạy trên CSR ít overhead hơn ở một số workload.
- Mỗi snapshot có một **mapping ID–index cố định**, giúp tái lập kết quả.
- Có thể xây snapshot mới rồi **công bố** khi hoàn chỉnh, tránh truy vấn đọc dữ liệu cập nhật dở.

Đổi lại:

- Dựng snapshot tốn thời gian và thêm bộ nhớ trong giai đoạn chuyển đổi.
- Snapshot trở nên **cũ** sau khi bản chuẩn đổi; cần version và thời điểm tái dựng.
- Nếu đồng thời giữ đối tượng, bảng cạnh và hai chỉ mục CSR/CSC, phải xác định **nguồn dữ liệu chuẩn**, không để nhiều bản sao cùng tự nhận là dữ liệu đúng.
- Khi thay đổi ID hoặc nhãn, phải làm rõ trường nào ổn định và trường nào được lập lại.

Một cách khác là **CSR nền + delta**: giữ phần đồ thị nén ổn định, còn các cung thêm/xóa được ghi ở cấu trúc động; khi đọc phải hợp nhất và lọc tombstone. Cách này tiết kiệm chi phí dịch mảng cho từng cập nhật nhưng làm truy vấn và đồng bộ phức tạp hơn.

## 14. Hướng cung, trọng số, khuyên và đa cạnh

Hai biểu diễn phải có cùng ngữ nghĩa đồ thị:

### Có hướng và vô hướng

Đồ thị **có hướng** lưu cung `u→v` tại phía nguồn `u`. Muốn duyệt cung đi vào `v` cần chỉ mục bổ sung hoặc quét những nguồn; trong biểu diễn nén, **CSC** thường nhóm theo đích.

Đồ thị **vô hướng** có cạnh `{u,v}`, không được coi hai mục kề đối ứng là hai cạnh thật. Với object graph, một đối tượng `Edge` có thể nằm ở danh sách incidence của cả hai đầu mút; với CSR thường ghi hai mục đích, và có thể giữ **cùng một edge ID** trong hai mục đó.

### Trọng số

Cung `u→v` với trọng số `0` vẫn là cung tồn tại. Với đối tượng, `edge.weight=0`; với CSR, tại vị trí `k` có `col_idx[k]=v` và `weight[k]=0`. Không được dùng điều kiện `if weight[k]` để xác định có cung hay không.

### Khuyên

Trong đồ thị có hướng, cung khuyên `u→u` đóng góp **1 vào bậc ra và 1 vào bậc vào**. Trong đồ thị vô hướng, khuyên đóng góp **2 vào bậc** theo quy ước chuẩn, dù một bảng incidence theo edge ID có thể chỉ giữ một mục cho nó.

### Cạnh/cung song song

Một danh sách đối tượng `Edge` cho phép hai đối tượng cạnh khác ID cùng trỏ đến `u` và `v`. CSR cũng cho phép hai mục có **cùng col_idx nhưng edge_id khác nhau**. Nếu thay cả hai bằng `set(neighbor)` hoặc ma trận Boolean, ta sẽ mất số lượng cung/cạnh song song và thuộc tính riêng.

### Đỉnh cô lập

Đỉnh cô lập phải tồn tại trong `nodes_by_id` của biểu diễn đối tượng. Với CSR, nó cần có ID trong `index_to_id` và **đoạn offset rỗng**, không được biến mất chỉ vì không có cạnh.

## 15. Cách lựa chọn khi thiết kế hệ thống

| Tình huống | Cân nhắc đầu tiên | Lý do |
| --- | --- | --- |
| Mô hình nghiệp vụ giàu thuộc tính, thay đổi thường xuyên | **Đối tượng nút/cạnh và chỉ mục động** | Dễ tổ chức hành vi, cập nhật và quy tắc nghiệp vụ |
| Đồ thị lớn, chủ yếu chạy nhiều lượt BFS/DFS | **CSR hoặc danh sách kề nén** | Duyệt tuần tự đoạn kề, bộ nhớ gọn |
| Cần trao đổi qua tệp/hệ thống khác | **Bảng đỉnh/cạnh với ID ổn định** | Không phụ thuộc con trỏ hay chỉ số snapshot |
| Cần cập nhật nhanh và vẫn phân tích theo lô | **Bản chuẩn động + snapshot CSR** | Tách chi phí ghi và chi phí duyệt |
| Đồ thị rất dày, hỏi quan hệ giữa cặp đỉnh liên tục | **Ma trận kề/bitset** cũng đáng cân nhắc | Kiểm tra ô nhanh theo chỉ số |
| Phải truy vấn đồng thời cung ra và cung vào | **Hai chỉ mục**: outgoing/incoming hoặc CSR/CSC | Không quét toàn bộ cạnh mỗi lần |
| Chạy trên thiết bị/thư viện yêu cầu dữ liệu liên tiếp | **Mảng typed/CSR theo định dạng hỗ trợ** | Dễ chuyển dữ liệu, SIMD/GPU tùy thuật toán |

**Đo trên workload thật** trước khi quyết định cuối cùng. Với cùng dữ liệu và kết quả mong đợi, nên đo riêng:

- Thời gian dựng đối tượng, tạo ánh xạ và xuất CSR.
- Bộ nhớ đỉnh, cạnh, chỉ mục và trạng thái thuật toán.
- Chi phí một lượt BFS/DFS, truy vấn cung vào, kiểm tra cạnh.
- Chi phí thêm/xóa đỉnh/cung và tái dựng snapshot.
- Tác động của thứ tự đỉnh/cung, loại trọng số và tỷ lệ đỉnh cô lập.

Một bài benchmark chỉ đo riêng **lượt BFS sau khi CSR đã dựng** sẽ bỏ qua chi phí xây snapshot; một benchmark chỉ đo **thêm cạnh** lại bỏ qua lợi ích đọc nhiều lần. Cần so đúng **vòng đời sử dụng dữ liệu**.

## 16. Những ngộ nhận thường gặp

1. **“Dùng chỉ số nguyên là dữ liệu tự nằm liên tiếp.”** Không hẳn: `list[int]` Python giữ tham chiếu; typed array mới đóng gói giá trị theo kiểu.
2. **“ID nghiệp vụ chính là index CSR.”** Sai: index là vị trí trong một snapshot, có thể đổi khi sắp/xóa/nén.
3. **“Object graph luôn có độ phức tạp BFS tệ hơn.”** Sai: cả object graph với danh sách kề và CSR đều thường `O(n+m)`; chi phí hằng có thể khác.
4. **“CSR luôn nhanh hơn object graph.”** Không có bảo đảm tuyệt đối; còn mapping, locality thực, độ lớn đồ thị và ngôn ngữ.
5. **“Một nút được nhiều cạnh tham chiếu thì phải có nhiều đối tượng nút.”** Sai: các cạnh cùng đích phải trỏ tới **một đối tượng tương ứng ID**.
6. **“Xóa nút khỏi dict tự xóa mọi cạnh trỏ tới nút.”** Sai: phải dọn những liên kết trong bảng cạnh và các chỉ mục.
7. **“Xóa một index không ảnh hưởng tới cạnh.”** Sai nếu nén/dồn mảng; các chỉ số sau vị trí xóa có thể đổi.
8. **“CSR thêm cạnh `O(1)` vì truy cập mảng nhanh.”** Sai trong thiết kế packed, chèn giữa có thể dịch nhiều phần tử và sửa offset.
9. **“Mảng CSR không cần bảng ID.”** Nếu bên ngoài dùng ID chuỗi/UUID, vẫn cần ánh xạ hoặc cơ chế nhận diện tương ứng.
10. **“Không cần giữ edge ID vì đã có col_idx.”** Sai với đa đồ thị khi hai cung có cùng nguồn/đích nhưng khác trọng số/thuộc tính.
11. **“Trọng số 0 nghĩa là không có cung.”** Sai: vị trí liên kết xác định sự tồn tại, trọng số là dữ liệu riêng.
12. **“CSR tự giữ thứ tự tăng của từng danh sách kề.”** Sai: các mục chỉ được nhóm theo nguồn, chưa chắc sắp đích.
13. **“Mỗi bản snapshot dùng lại chỉ số cũ được ngay.”** Sai nếu mapping đã thay; kết quả parent/distance phải được gắn với đúng phiên bản.
14. **“Có hai mục kề ở đồ thị vô hướng nghĩa là có hai cạnh.”** Thường sai: đó là hai tham chiếu của một cạnh toán học.
15. **“Tính số byte chỉ bằng `O(n+m)` là đủ.”** Chưa đủ: phải biết kích thước index, trọng số, ID, metadata và overhead.
16. **“Có thể tuần tự hóa trực tiếp mọi con trỏ trong đồ thị đối tượng.”** Không nên: dùng ID nút/cạnh và khôi phục tham chiếu theo bảng ID.
17. **“Một benchmark chỉ đo thời gian duyệt là đủ chọn cấu trúc.”** Chưa đủ nếu ứng dụng thường xuyên cập nhật hoặc phải dựng snapshot nhiều lần.

## 17. Tự kiểm tra

**Câu 1.** Đồ thị có ID `"A"` nhưng được lưu tại chỉ số 3 của một snapshot. Khi tạo snapshot khác, có bắt buộc A vẫn là chỉ số 3 không?

**Đáp án:** Không. ID `"A"` là danh tính logic; chỉ số 3 chỉ có ý nghĩa trong mapping của snapshot cũ. Khi đổi mapping phải đổi mọi tham chiếu theo chỉ số.

**Câu 2.** Hai cạnh e0 và e2 cùng A→B. Trong object graph, điều gì phải đúng với đối tượng đích của chúng?

**Đáp án:** Chúng có thể là hai đối tượng `Edge` khác nhau nhưng phải dùng chung đối tượng đỉnh B: `e0.target is e2.target` là `True` trong cùng đồ thị.

**Câu 3.** Với CSR `row_ptr=[0,3,4,5,6,8,8]` và `col_idx=[1,2,1,3,3,4,4,0]`, đỉnh index 4 có các cung đi ra tới chỉ số nào?

**Đáp án:** Đoạn `[row_ptr[4],row_ptr[5])=[6,8)`, nên có các đích `[4,0]`: một khuyên và một cung về đỉnh index 0.

**Câu 4.** Vì sao đỉnh F cô lập vẫn phải có ID trong bảng `index_to_id` và một cặp offset bằng nhau?

**Đáp án:** Vì F thuộc V dù không có cung nào. Cặp offset bằng nhau cho biết đoạn cung ra rỗng, chứ không có nghĩa F không tồn tại.

**Câu 5.** Với CSR có `n=100.000, m=300.000`, offset/đích/edge ID lần lượt 4 byte, trọng số 8 byte, phần dữ liệu thô bốn mảng khoảng bao nhiêu?

**Đáp án:** `4(n+1)+16m=5.200.004` byte, xấp xỉ **5,2 MB thập phân**, chưa tính mapping/metadata/overhead.

**Câu 6.** Vì sao `list[int]` Python không hoàn toàn tương đương mảng đóng gói `array("I")`?

**Đáp án:** List lưu các tham chiếu tới đối tượng số nguyên; typed array lưu các **giá trị số theo kiểu cố định** liên tiếp, nên có kích thước mỗi phần tử dễ dự đoán hơn.

**Câu 7.** BFS toàn đồ thị dùng danh sách kề đối tượng và CSR có nhất thiết khác Big-O không?

**Đáp án:** Không. Trong mô hình thao tác hiệu quả, cả hai đều **`O(n+m)` thời gian**; sự khác nhau thường ở hằng số, locality, overhead và chi phí chuẩn bị dữ liệu.

**Câu 8.** Xóa B khỏi mapping `[A,B,C,D]` bằng cách dồn hàng/cột gây nguy cơ gì?

**Đáp án:** Chỉ số C và D thay đổi. Nếu `col_idx`, `parent` hoặc cache vẫn giữ index cũ, chúng có thể trỏ tới sai đỉnh; cần remap hoặc tái dựng đồng bộ.

**Câu 9.** Khi ứng dụng thêm/xóa cạnh hàng nghìn lần nhưng chỉ phân tích định kỳ, nên cân nhắc cách kết hợp nào?

**Đáp án:** Giữ bản chuẩn động (đối tượng/bảng cạnh và chỉ mục), rồi dựng snapshot CSR/CSC khi chạy phân tích hoặc theo lô; quản lý phiên bản snapshot.

**Câu 10.** Có cung khuyên E→E trọng số 0 trong ví dụ. CSR và object graph phải xử lý ra sao?

**Đáp án:** Object graph lưu một đối tượng cung có nguồn và đích cùng là E; CSR có một mục đích index 4 với weight 0 và edge ID riêng. Không bỏ cung vì trọng số bằng 0.

**Câu 11.** Nếu chỉ cần liệt kê mọi cung đi vào B mà đang có CSR theo nguồn, có thể xem ngay một đoạn liên tiếp theo B không?

**Đáp án:** Không, CSR theo nguồn nhóm cung **đi ra**. Muốn cung vào nhanh, dùng chỉ mục incoming/CSC hoặc quét toàn bộ cung.

**Câu 12.** Nếu biểu diễn đối tượng chỉ có danh sách kề đi ra, khi xóa đỉnh B phải chú ý những liên kết nào?

**Đáp án:** Cả cung xuất phát từ B và **mọi cung từ đỉnh khác đi vào B**. Nếu không có chỉ mục đi vào, có thể phải quét những đỉnh/cạnh còn lại.

**Câu 13.** Trong một snapshot, `id_to_index["C"]=2`. Có thể ghi chỉ số 2 ra file rồi giả định nó là danh tính bền vững của C trên mọi phiên bản không?

**Đáp án:** Không. Phải lưu ID logic `"C"` hoặc kèm một mapping/phiên bản chính xác để giải mã số 2; index tự nó không phải ID ổn định.

**Câu 14.** Hai biểu diễn trả cùng thứ tự BFS từ A, nhưng một biểu diễn dùng nhiều RAM hơn. Có thể kết luận biểu diễn ít RAM sẽ luôn chạy nhanh hơn không?

**Đáp án:** Không. Hiệu năng còn tùy cấu trúc dữ liệu, số lần ánh xạ ID, cache, chi phí cấp phát và loại truy vấn. Cần benchmark trên toàn bộ workload.

**Ghi nhớ:** Lưu đồ thị bằng **đối tượng đỉnh/cạnh** đem lại mô hình trực tiếp và thuận tiện cho thuộc tính, tham chiếu, cập nhật; lưu bằng **mảng chỉ số liên tiếp** như CSR giúp kiểm soát bố cục dữ liệu và có thể giảm overhead, tận dụng truy cập tuần tự. Cả hai có thể hỗ trợ BFS/DFS trong **`O(n+m)`** nhưng khác nhau về hằng số, bộ nhớ và chi phí thay đổi cấu trúc. Luôn tách **ID logic ổn định**, **danh tính đối tượng trong RAM** và **chỉ số snapshot**, bảo toàn khuyên/cạnh song song/đỉnh cô lập, đồng bộ các tham chiếu khi xóa hoặc đánh lại chỉ số, và lựa chọn theo **tần suất đọc–ghi, yêu cầu nghiệp vụ và dữ liệu thực**.
