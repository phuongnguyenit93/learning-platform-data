# Giới hạn đối với việc tách nhóm hoặc xóa liên kết

**Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, rất hiệu quả khi các nhóm chỉ được **hợp lại**. Nếu hai đỉnh của một đồ thị vô hướng được nối bởi một cạnh mới, ta có thể dùng `union(u,v)` để gộp hai thành phần. Tuy nhiên, nếu một cạnh cũ bị xóa, hai đỉnh trước đây liên thông **có thể** vẫn liên thông qua đường khác, **hoặc** có thể thuộc hai thành phần mới. DSU cơ bản không biết trường hợp nào xảy ra.

Đây là giới hạn mang tính **mô hình**, không phải chỉ do cài đặt `find` chưa đủ nhanh. Rừng cha của DSU chỉ lưu **đại diện của các nhóm hiện tại**, không lưu đầy đủ các cạnh hay quan hệ cần thiết để chia lại nhóm. Nén đường đi và hợp theo kích thước/hạng giúp giảm chi phí truy vấn, nhưng **không bổ sung phép tách tập hợp**.

Bài học thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Học phần xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời học bất biến, thao tác, độ phức tạp thời gian và bộ nhớ để chọn cấu trúc phù hợp. Trọng tâm ở đây là hiểu **vì sao DSU chuẩn không hỗ trợ xóa liên kết**, phân biệt bài toán tách nhóm với xóa cạnh đồ thị, và chọn giải pháp phù hợp như **xây lại bằng BFS/DFS**, **xử lý ngược thời gian**, **rollback DSU** hoặc **liên thông động**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả chính xác hợp đồng của `make_set`, `find`, `union` và những thao tác mà DSU chuẩn **không** cung cấp.
2. Giải thích vì sao một đường nối bị xóa có thể là **cầu (bridge)** hoặc **không phải cầu**, và vì sao hai trường hợp cần xử lý khác nhau.
3. Phân biệt **xóa cạnh của đồ thị** với **hoàn tác một phép hợp** và với **tách một tập hợp theo yêu cầu nghiệp vụ**.
4. Chỉ ra thông tin nào đã bị “quên” sau các phép `union`, nhất là khi dùng **path compression**.
5. Triển khai cách xây lại thành phần sau khi xóa cạnh bằng **BFS/DFS** và so sánh với DSU.
6. Hiểu khi nào có thể **đảo thời gian** để biến một loạt thao tác xóa thành thêm.
7. Cài đặt **rollback DSU không nén đường**, dùng snapshot/rollback đúng kiểu LIFO.
8. Nắm được ý tưởng **cây đoạn trên trục thời gian** kết hợp rollback DSU cho truy vấn liên thông offline.
9. Phân tích độ phức tạp và lựa chọn cách tiếp cận theo đặc điểm workload.

Các ví dụ chủ yếu xét **đồ thị vô hướng**. Trong đồ thị có hướng, quan hệ đi tới được không phải quan hệ tương đương; DSU không tự giải bài toán đường đi có hướng hoặc thành phần liên thông mạnh.

## 2. DSU biểu diễn một phân hoạch chứ không biểu diễn toàn bộ đồ thị

Cho tập phần tử:

\[
U=\{0,1,\ldots,n-1\}.
\]

Một **phân hoạch** là họ nhóm `G_1,\ldots,G_c` thỏa:

- Mỗi nhóm khác rỗng.
- Các nhóm đôi một không giao nhau.
- Hợp tất cả nhóm bằng U.

DSU lưu phân hoạch này dưới dạng **rừng cha**:

```text
parent[x] = nút cha của x
parent[root] = root

find(x) = gốc của cây chứa x
same(x,y) = (find(x) == find(y))
```

Ví dụ:

```text
Đồ thị thực:
0 — 1 — 2 — 3

Một rừng cha DSU hợp lệ:
      0
    / | \
   1  2  3

parent = [0,0,0,0]
```

Cây cha không cần trùng với các cạnh đồ thị. Trong ví dụ, `parent[3]=0` **không chứng minh đồ thị có cạnh trực tiếp `(0,3)`**.

### Bất biến DSU chuẩn

Với mọi phần tử:

1. `parent[x]` là một chỉ số hợp lệ.
2. Mỗi cây có đúng một gốc r tự trỏ `parent[r]=r`.
3. Không có chu trình cha dài hơn một nút.
4. `find(x)==find(y)` khi và chỉ khi x, y thuộc cùng nhóm.
5. Nếu lưu `size[r]`, chỉ `size` ở gốc hiện tại mới mang nghĩa **số thành viên của nhóm**.
6. Một phép `union` thành công nối đúng **hai gốc khác nhau**, giảm số nhóm đúng một.

Các bất biến này **không chứa danh sách cạnh đầu vào**. Nếu ứng dụng xóa cạnh, chỉ nhìn vào `parent` chưa đủ để xác định phân hoạch liên thông mới.

## 3. Những thao tác DSU chuẩn làm được

Giao diện điển hình:

```text
make_set(x)       Tạo nhóm đơn chứa x.
find(x)           Trả về đại diện của nhóm chứa x.
same(x, y)        Kiểm tra hai phần tử cùng nhóm.
union(x, y)       Hợp hai nhóm chứa x và y.
component_size(x) Trả kích thước nhóm chứa x, nếu có metadata size.
component_count() Trả số nhóm, nếu có biến đếm.
```

Sau `union(x,y)`, quan hệ cùng nhóm tăng theo nghĩa:

> Những cặp trước đây cùng nhóm vẫn cùng nhóm; có thể có thêm những cặp ở hai nhóm vừa được hợp.

Không có phép hợp chuẩn nào làm **một nhóm đang có thành viên mất thành viên**.

### Tính đơn điệu

Nếu `P_t` là phân hoạch sau t phép hợp, thì `P_{t+1}` là phân hoạch **thô hơn hoặc bằng** `P_t`: các nhóm có thể nhập lại, không tự chia nhỏ ra.

Ví dụ:

```text
Ban đầu:
{0} {1} {2} {3}

union(0,1):
{0,1} {2} {3}

union(2,3):
{0,1} {2,3}

union(1,2):
{0,1,2,3}
```

Sau ba lần hợp, DSU không ghi nhớ đầy đủ **vì sao** một nhóm có bốn phần tử được hình thành. Nhiều lịch sử khác nhau có thể dẫn tới cùng một phân hoạch và thậm chí cùng mảng `parent`.

## 4. Phản ví dụ cơ bản: xóa một cạnh có thể tách nhóm

Xét đồ thị vô hướng dạng đường:

```text
0 — 1 — 2 — 3
```

Sau khi lần lượt thêm:

```text
add_edge(0,1)
add_edge(1,2)
add_edge(2,3)
```

DSU có đúng một nhóm:

\[
\{0,1,2,3\}.
\]

Giờ xóa cạnh `(1,2)`.

Đồ thị mới:

```text
0 — 1      2 — 3
```

Có **hai thành phần**:

\[
\{0,1\},\quad\{2,3\}.
\]

Nhưng DSU cũ vẫn có thể lưu:

```text
parent = [0,0,0,0]
size[0] = 4
components = 1
```

Nếu không tái cấu trúc, nó sẽ trả:

```text
same(0,3) = true    // SAI so với đồ thị sau xóa.
```

Vấn đề không thể khắc phục chỉ bằng cách giảm `size[0]` hay tăng `components`: phải quyết định **những phần tử cụ thể nào** thuộc mỗi nhóm mới và dựng lại quan hệ gốc của chúng.

## 5. Xóa một cạnh cũng có thể KHÔNG tách nhóm

Xét tam giác:

```text
   0
  / \
 1 — 2
```

Các cạnh:

```text
(0,1), (1,2), (2,0)
```

Xóa cạnh `(1,2)`, đồ thị còn:

```text
1 — 0 — 2
```

Cả ba đỉnh vẫn liên thông qua 0. Số thành phần vẫn bằng một.

### Khái niệm cầu (bridge)

Một **cầu** của đồ thị vô hướng là cạnh mà việc xóa nó **làm tăng số thành phần liên thông**.

- Trong đường `0—1—2—3`, mọi cạnh đều là cầu.
- Trong tam giác, không cạnh nào là cầu.
- Cạnh nằm trên một chu trình **không phải cầu**.
- Với đa đồ thị, hai cạnh song song khác nhau nối cùng hai đỉnh thường khiến từng cạnh riêng lẻ không phải cầu nếu cả hai đang tồn tại.

Do đó, một lệnh `remove_edge(u,v)` có ít nhất hai khả năng:

| Cạnh bị xóa | Số thành phần sau xóa | Điều phải làm |
|---|---|---|
| Không phải cầu | Không đổi | Nhóm liên thông giữ nguyên; metadata cạnh có thể cần giảm |
| Là cầu | Tăng đúng 1 với một lần xóa một cạnh vô hướng | Tách một thành phần thành hai thành phần mới |

**DSU không lưu đủ thông tin để tự kiểm tra một cạnh có phải cầu hay không**. Nó chỉ biết hai đầu có cùng gốc; trong một thành phần liên thông, điều đó luôn đúng, kể cả cạnh là cầu hay không.

## 6. Cùng phân hoạch, khác phản ứng khi xóa cạnh

Có thể có hai đồ thị cùng số đỉnh, số cạnh, phân hoạch và kích thước thành phần, nhưng **hành vi khi xóa cạnh khác nhau**.

Đồ thị A — chu trình bốn đỉnh:

```text
0 — 1
|   |
3 — 2

Cạnh: (0,1), (1,2), (2,3), (3,0)
```

Đồ thị B — tam giác kèm một nhánh:

```text
0 — 1
 \ /
  2 — 3

Cạnh: (0,1), (1,2), (2,0), (2,3)
```

Cả hai đều có:

```text
n = 4
m = 4
components = 1
component_size = 4
cycle_rank = m - n + components = 1
```

Nhưng:

- Trong đồ thị A, xóa `(0,1)` **không** làm mất liên thông.
- Trong đồ thị B, xóa `(2,3)` **làm tách đỉnh 3** khỏi nhóm còn lại.

Ngay cả metadata `size` và `edgeCount` ở gốc cũng không đủ để quyết định tác dụng của xóa cạnh. Muốn xử lý xóa đúng, phải có **thông tin cấu trúc đồ thị**, **lịch sử có thể khôi phục** hoặc một thuật toán động mạnh hơn.

## 7. Vì sao “đảo lại một lệnh union” không phải phép xóa cạnh?

Một hiểu nhầm phổ biến: đã thêm cạnh `(u,v)` thì DSU từng gọi `union(u,v)`; vậy lúc xóa cạnh chỉ cần “undo union tương ứng”.

Điều này **không đúng tổng quát**.

Xét:

```text
add_edge(0,1)
add_edge(1,2)
add_edge(0,2)
```

Hai cạnh đầu được dùng để hợp các nhóm. Khi cạnh `(0,2)` đến, hai đầu đã cùng nhóm nên `union(0,2)` là **no-op**.

Nếu xóa `(1,2)` sau khi cả ba cạnh đã có, đồ thị vẫn liên thông nhờ `(0,2)`:

```text
0 — 1
 \
  2
```

Nếu “hoàn tác” riêng phép `union(1,2)` của thời điểm thêm cạnh thứ hai, ta có thể **chia nhóm sai** vì không xét cạnh thứ ba đã được thêm sau đó.

### Ba loại thao tác khác nhau

1. **Xóa một cạnh đồ thị:** thay đổi tập cạnh; phải tính lại các đường đi có thể tồn tại.
2. **Hoàn tác một thay đổi DSU đã ghi:** phục hồi một **trạng thái lịch sử** của rừng cha theo thứ tự hoàn tác.
3. **Tách nhóm theo một phân hoạch cho trước:** yêu cầu gán một tập thành viên thành hai hoặc nhiều nhóm; có thể không liên quan cạnh đồ thị nào.

Rollback chỉ giải quyết mục 2 theo những điều kiện nhất định. Không được đồng nhất nó với mục 1 hoặc mục 3.

## 8. Nén đường đi khiến việc hoàn tác phức tạp hơn

DSU tối ưu thường sử dụng:

- **Union by size/rank:** nối gốc nhỏ/thấp dưới gốc lớn/cao.
- **Path compression:** trong `find`, cho các nút trên đường tới gốc trỏ thẳng về gốc.
- Hoặc **path halving/path splitting:** cập nhật cha để rút ngắn đường.

Ví dụ ban đầu:

```text
3 → 2 → 1 → 0
```

Gọi `find(3)` với full path compression có thể sửa:

```text
parent[3] = 0
parent[2] = 0
```

Một lần `find` có thể sửa **nhiều ô** `parent`, không chỉ một liên kết của phép `union`.

Nếu muốn quay lại trạng thái trước đó, phải biết **giá trị cũ của từng ô đã bị thay** hoặc dùng một chiến lược lưu trạng thái riêng. Chỉ lưu “đã nối gốc rB dưới gốc rA” có thể không đủ để hoàn tác tất cả thay đổi do các lần `find` xen kẽ.

### Vì sao rollback DSU thường không nén đường?

Nếu **không** path compression:

- `find` chỉ đọc, không thay mảng cha.
- Một `union` thành công chỉ sửa một cha, một `size` ở gốc giữ lại và biến số nhóm (nếu có).
- Ta có thể ghi lại những giá trị cũ rồi phục hồi chúng bằng một lần pop khỏi ngăn xếp.

Vì vậy rollback DSU cổ điển thường **hợp theo kích thước hoặc hạng nhưng không nén đường**, đổi chặn Ackermann ngược khấu hao của DSU chuẩn lấy **khả năng hoàn tác gọn và dễ chứng minh**.

## 9. Giải pháp đơn giản nhất: giữ đồ thị thật và tìm lại bằng BFS/DFS

Khi n, m nhỏ hoặc số lần xóa hiếm, cách đáng tin cậy là:

1. Lưu **tập cạnh đang hoạt động** của đồ thị.
2. Khi xóa cạnh, xóa nó khỏi cấu trúc đồ thị thật.
3. Dùng **BFS hoặc DFS** trên đồ thị hiện tại để tìm thành phần liên thông hoặc kiểm tra đường đi.
4. Nếu cần một DSU để trả các truy vấn sau, có thể **xây lại toàn bộ DSU** từ các cạnh còn hoạt động.

### Ví dụ đường và tam giác

**Đường:**

```text
(0,1), (1,2), (2,3)

remove_edge(1,2)
reachable(0,3) = false
```

**Tam giác:**

```text
(0,1), (1,2), (2,0)

remove_edge(1,2)
reachable(0,2) = true
reachable(1,2) = true   // Đi qua 1→0→2.
```

BFS/DFS dùng **cạnh thật**, nên thấy được đường thay thế mà mảng cha DSU không lưu.

### Phân tích

Với n đỉnh và m cạnh hoạt động:

- Nếu dùng danh sách kề, một lần BFS/DFS tìm liên thông có chặn **`O(n+m)`** worst-case, thường duyệt ít hơn nếu gặp đích sớm.
- Đếm **toàn bộ thành phần** bằng một lần duyệt tất cả đỉnh/cạnh cũng là **`O(n+m)`**.
- Xây lại DSU từ n nhóm đơn và m cạnh hiện hành dùng **`O(n+m\alpha(n))` khấu hao** nếu gộp bằng DSU tối ưu và tính chi phí đọc cạnh; có thể diễn đạt an toàn là `O(n+m\log n)` với union by size không nén.
- Bộ nhớ cho đồ thị thật và cấu trúc hỗ trợ là **`O(n+m)`**.

Nếu sau **mỗi lần xóa** lại xây toàn bộ, tổng chi phí có thể lớn. Nhưng với dữ liệu nhỏ hoặc ít sự kiện xóa, đây vẫn là thiết kế đơn giản và dễ kiểm chứng.

## 10. Python: đồ thị vô hướng có thêm/xóa cạnh theo ID và BFS

Để phân biệt **cạnh song song** và tránh xóa nhầm, ta cấp một **ID riêng** cho mỗi cạnh. Trong ví dụ này, hai cạnh có cùng đầu mút vẫn là hai cạnh vật lý khác nhau.

Duy trì:

- `edges[id]=(u,v)` cho các cạnh còn hoạt động.
- `adj[u][v]` là **số cạnh hoạt động** nối u và v; nếu `u!=v`, số lượng được lưu đối xứng.
- `add_edge` thêm cạnh và trả ID.
- `remove_edge` xóa **đúng cạnh ID đó**.
- `connected` dùng BFS; không dựa vào DSU cũ.

```python
from collections import deque


class MutableUndirectedGraph:
    def __init__(self, n: int):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n không được âm")

        self.n = n
        self.next_edge_id = 0
        self.edges: dict[int, tuple[int, int]] = {}
        self.adj: list[dict[int, int]] = [
            {} for _ in range(n)
        ]

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("ID đỉnh phải là số nguyên")
        if not 0 <= x < self.n:
            raise IndexError("ID đỉnh ngoài miền")

    def _change_count(self, u: int, v: int, delta: int) -> None:
        old = self.adj[u].get(v, 0)
        new = old + delta
        if new < 0:
            raise AssertionError("Số cạnh kề bị âm")
        if new == 0:
            self.adj[u].pop(v, None)
        else:
            self.adj[u][v] = new

    def add_edge(self, u: int, v: int) -> int:
        self._check(u)
        self._check(v)

        eid = self.next_edge_id
        self.next_edge_id += 1
        self.edges[eid] = (u, v)

        self._change_count(u, v, +1)
        if u != v:
            self._change_count(v, u, +1)
        return eid

    def remove_edge(self, eid: int) -> None:
        # KeyError nếu ID không có trong tập cạnh đang hoạt động.
        u, v = self.edges.pop(eid)
        self._change_count(u, v, -1)
        if u != v:
            self._change_count(v, u, -1)

    def connected(self, start: int, target: int) -> bool:
        self._check(start)
        self._check(target)

        if start == target:
            return True

        seen = {start}
        queue = deque([start])

        while queue:
            u = queue.popleft()
            for v in self.adj[u]:
                if v == target:
                    return True
                if v not in seen:
                    seen.add(v)
                    queue.append(v)
        return False

    def component_count(self) -> int:
        seen = set()
        count = 0

        for start in range(self.n):
            if start in seen:
                continue
            count += 1
            seen.add(start)
            queue = deque([start])

            while queue:
                u = queue.popleft()
                for v in self.adj[u]:
                    if v not in seen:
                        seen.add(v)
                        queue.append(v)

        return count


g = MutableUndirectedGraph(4)
a = g.add_edge(0, 1)
b = g.add_edge(1, 2)
c = g.add_edge(2, 3)

assert g.connected(0, 3)
assert g.component_count() == 1

g.remove_edge(b)              # Xóa cầu (1,2).
assert not g.connected(0, 3)
assert g.component_count() == 2

d = g.add_edge(0, 2)          # Đường nối thay thế.
assert g.connected(0, 3)
assert g.component_count() == 1

g.remove_edge(a)
assert not g.connected(1, 3)  # Đỉnh 1 bị cô lập.

# Hai cạnh song song khác ID: xóa một vẫn còn cạnh kia.
e1 = g.add_edge(1, 3)
e2 = g.add_edge(1, 3)
g.remove_edge(e1)
assert g.connected(1, 3)
assert e2 in g.edges
```

### Điều đã được giải quyết và chưa được giải quyết

Mã này **giải đúng xóa cạnh vô hướng** vì giữ các cạnh thật. Nhưng mỗi truy vấn liên thông có thể mất `O(n+m)`, không phải chặn DSU gần hằng số. Đó là đánh đổi hợp lý khi các phép xóa không nhiều và yêu cầu đơn giản.

Nếu phải liên tục truy vấn trên đồ thị rất lớn sau hàng triệu sự kiện thêm/xóa, cần cấu trúc **liên thông động** chuyên dụng hoặc xử lý **offline** khi biết trước chuỗi thao tác.

## 11. Nếu vẫn muốn dùng DSU: xây lại từ cạnh còn hoạt động

Sau khi sửa danh sách cạnh thật, ta có thể bỏ trạng thái DSU cũ và xây một DSU mới:

```text
rebuild_components(n, activeEdges):
    newDSU = DSU(n)

    for each active edge (u,v):
        newDSU.union(u,v)

    return newDSU
```

Bất biến của DSU mới đúng vì mỗi cạnh hoạt động nối hai đỉnh cần cùng thành phần; tất cả cạnh đang tồn tại đều được xét.

### Cẩn trọng với metadata

Nếu DSU duy trì thêm:

```text
size[root]
totalWeight[root]
minimum[root]
edgeCount[root]
```

thì khi xây lại:

- `size` khởi tạo bằng 1 và cộng khi hợp.
- Tổng trọng số đỉnh phải khởi tạo từ thuộc tính hiện hành của **từng đỉnh**.
- `minimum`/`maximum` cũng phải tính lại theo các nhóm mới.
- `edgeCount` phải tính **mọi cạnh hoạt động**, kể cả cạnh nội bộ tạo chu trình, không chỉ cạnh khiến `union` thành công.

Nếu chỉ đổi `parent` mà giữ `size`/metadata cũ, các truy vấn sẽ **không nhất quán**, đặc biệt khi một nhóm bị chia thành hai.

### Không dùng `parent` hiện tại để suy ra cạnh đã bị xóa

Rừng cha sau path compression có thể trỏ thẳng nhiều nút tới gốc. Các cạnh cha không phải cạnh thật, nên **xóa một cạnh thật không đồng nghĩa xóa một liên kết tương ứng trong mảng parent**.

Bản dựng lại phải dựa vào **tập cạnh hiện hành của đồ thị**, không dựa vào danh sách cặp `(x,parent[x])`.

## 12. Trường hợp đặc biệt: biết trước toàn bộ thao tác xóa

Nếu chuỗi truy vấn được biết **trước khi trả lời**, ta có thể xử lý **offline**. Một thủ thuật mạnh với bài toán **chỉ xóa cạnh** là **đảo ngược thời gian**:

- Trong thời gian tiến, sự kiện là **xóa cạnh**.
- Khi đảo thời gian, mỗi sự kiện xóa trở thành **thêm lại cạnh**, chính là thao tác `union` mà DSU hỗ trợ.

### Mô hình deletion-only

Ban đầu có đồ thị `G_0=(V,E_0)` với các cạnh có ID riêng. Chuỗi gồm:

```text
remove_edge(edgeID)
query_connected(u,v)
```

Giả định:

- Mọi cạnh bị xóa **đang tồn tại** tại thời điểm xóa.
- Mỗi ID cạnh bị xóa tối đa một lần (hoặc cần quy ước đếm trạng thái riêng).
- **Không có thêm cạnh mới trong thời gian tiến**.
- Toàn bộ chuỗi thao tác đã biết trước khi xử lý.

### Quy trình đảo thời gian

1. Xác định tập cạnh **còn sống ở cuối chuỗi**.
2. Khởi tạo DSU từ các cạnh cuối cùng đó.
3. Duyệt thao tác từ **cuối về đầu**:
   - Gặp truy vấn: trả lời bằng DSU hiện tại.
   - Gặp lệnh xóa cạnh ID trong thời gian tiến: **thêm lại** cạnh ấy bằng `union(u,v)`.
4. Đảo ngược danh sách câu trả lời để khôi phục thứ tự truy vấn ban đầu.

**Thời điểm trả lời phải nhất quán:** truy vấn `query_connected` hỏi về đồ thị **tại chính vị trí của truy vấn sau các thao tác đứng trước nó**. Khi duyệt ngược, trạng thái DSU trước khi đảo lệnh xóa là trạng thái **sau khi xóa**, đúng với các truy vấn nằm sau lệnh xóa trong thời gian tiến.

## 13. Truy vết đảo thời gian trên tam giác

Ban đầu đồ thị có:

```text
a = (0,1)
b = (1,2)
c = (0,2)
```

Chuỗi thao tác:

```text
1. query(0,2)      → true
2. remove(b)
3. query(0,2)      → true, vẫn có cạnh c.
4. remove(c)
5. query(0,2)      → false, còn mỗi cạnh a.
```

Tại **cuối chuỗi**, chỉ cạnh a còn hoạt động. Khởi tạo DSU từ a:

```text
{0,1}, {2}
```

Duyệt ngược:

| Bước ngược | Thao tác gốc | Thao tác trên DSU ngược | Kết quả |
|---:|---|---|---|
| 5 | `query(0,2)` | Đọc hai gốc | `false` |
| 4 | `remove(c)` | Thêm lại `c=(0,2)` | Nhóm `{0,1,2}` |
| 3 | `query(0,2)` | Đọc hai gốc | `true` |
| 2 | `remove(b)` | Thêm lại `b=(1,2)` | Vẫn một nhóm |
| 1 | `query(0,2)` | Đọc hai gốc | `true` |

Đảo thứ tự ba câu trả lời ta được:

```text
[true, true, false]
```

**Lưu ý quan trọng:** cách này **không xóa trong DSU**. Nó thay bài toán “chỉ xóa” thành “chỉ thêm” nhờ xử lý ngược thời gian.

### Khi nào không thể áp dụng trực tiếp?

- Cần trả lời ngay sau mỗi sự kiện, không thể đợi toàn bộ chuỗi.
- Luồng có cả **thêm và xóa** tùy ý.
- Không biết tập cạnh cuối cùng hoặc trạng thái ban đầu.
- Không biết ID cạnh nào bị xóa, nhất là khi có cạnh song song.
- Truy vấn không chỉ hỏi cùng thành phần mà còn cần đường đi chứng cứ hoặc thông tin khác chưa được duy trì.

Các bài toán offline tổng quát hơn thường cần kỹ thuật mạnh hơn đảo thời gian đơn giản.

## 14. Python: giải truy vấn chỉ xóa bằng xử lý ngược

Mã sau dùng cạnh có ID riêng và một DSU tối ưu thông thường. Nó khởi tạo từ **đồ thị cuối**, đi ngược các lệnh xóa và trả câu hỏi theo thứ tự ban đầu.

```python
class SimpleDSU:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[x] != x:
            old_parent = self.parent[x]
            self.parent[x] = root
            x = old_parent

        return root

    def union(self, x: int, y: int) -> bool:
        a = self.find(x)
        b = self.find(y)
        if a == b:
            return False
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)


def solve_deletions_offline(
    n: int,
    initial_edges: dict[str, tuple[int, int]],
    operations: list[tuple],
) -> list[bool]:
    # Mỗi cạnh có ID riêng; ở đây mỗi ID xóa tối đa một lần.
    deleted: set[str] = set()

    for op in operations:
        if op[0] == "remove":
            edge_id = op[1]
            if edge_id not in initial_edges or edge_id in deleted:
                raise ValueError("Lệnh xóa cạnh không hợp lệ")
            deleted.add(edge_id)

    dsu = SimpleDSU(n)

    # Trạng thái cuối: chỉ những cạnh chưa bị xóa.
    for edge_id, (u, v) in initial_edges.items():
        if edge_id not in deleted:
            dsu.union(u, v)

    reversed_answers = []

    for op in reversed(operations):
        if op[0] == "query":
            _, u, v = op
            reversed_answers.append(dsu.same(u, v))

        elif op[0] == "remove":
            edge_id = op[1]
            u, v = initial_edges[edge_id]
            dsu.union(u, v)  # Thêm lại trong thời gian ngược.

        else:
            raise ValueError("Loại thao tác không hợp lệ")

    return list(reversed(reversed_answers))


edges = {
    "a": (0, 1),
    "b": (1, 2),
    "c": (0, 2),
}

ops = [
    ("query", 0, 2),
    ("remove", "b"),
    ("query", 0, 2),
    ("remove", "c"),
    ("query", 0, 2),
]

assert solve_deletions_offline(3, edges, ops) == [
    True, True, False
]
```

**Hợp đồng của ví dụ:** `n` và các đầu mút cạnh phải hợp lệ; mã tập trung minh họa cách đảo thời gian, không triển khai đầy đủ lớp nhập liệu/kiểm tra kiểu. Trong chương trình thực tế, phải kiểm tra ID đỉnh và cả loại truy vấn, nhất là tránh chỉ số âm của Python.

Với n đỉnh, m cạnh ban đầu và q thao tác, phần DSU có tổng chi phí gần:

\[
O\bigl(n+(m+q)\alpha(n)\bigr)
\]

theo cách phát biểu khấu hao thông dụng, cộng chi phí quét lưu các lệnh. Cách này **không** đáp ứng truy vấn trực tuyến, vì cần nhìn trước tương lai.

## 15. Rollback DSU: hoàn tác trạng thái theo ngăn xếp

**Rollback DSU** bổ sung khả năng khôi phục **một snapshot trước đó** bằng cách ghi lại những thay đổi cấu trúc đã thực hiện sau snapshot.

Ý tưởng:

```text
checkpoint = snapshot()
union(a,b)
union(c,d)
...
rollback(checkpoint)
```

Sau rollback, DSU quay lại cùng **phân hoạch và metadata** như lúc chụp checkpoint (nếu đã ghi nhật ký đầy đủ).

### Hạn chế quan trọng

Rollback DSU **không phải** một phép `remove_edge(u,v)` tùy ý.

Nó chỉ hoàn tác các thay đổi theo thứ tự **ngược (LIFO)**, tức phục hồi một trạng thái **trước một đoạn thao tác gần nhất**.

Nếu cạnh a được thêm trước b và c, không thể chỉ “gỡ a” mà giữ nguyên b/c bằng cách pop riêng một bản ghi cũ ở giữa stack; các thay đổi phụ thuộc vào nhau. Để giải bài toán xóa bất kỳ, cần **sắp xếp lại các phép hợp theo trục thời gian hoặc truy vấn offline**.

### Vì sao bỏ path compression?

Nếu chỉ union by size không compression:

```text
find(x):
    while parent[x] != x:
        x = parent[x]
    return x
```

`find` **không ghi**. Mỗi union thành công sửa:

1. `parent[childRoot]`.
2. `size[parentRoot]`.
3. `components`.

Ta lưu các giá trị cũ của những mục đó rồi phục hồi khi rollback. Việc không nén giữ chiều cao `O(log n)` nhờ union by size, nên `find` vẫn hiệu quả.

## 16. Python: cài đặt rollback DSU không nén

```python
class RollbackDSU:
    def __init__(self, n: int):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n không được âm")

        self.parent = list(range(n))
        self.size = [1] * n
        self.components = n

        # Mỗi bản ghi: (gốc trở thành con, gốc được giữ,
        #              size gốc được giữ trước hợp).
        self.history: list[tuple[int, int, int]] = []

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("ID đỉnh phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("ID ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        # KHÔNG path compression.
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]

    def snapshot(self) -> int:
        return len(self.history)

    def union(self, x: int, y: int) -> bool:
        a = self.find(x)
        b = self.find(y)
        if a == b:
            return False  # Không đổi gì, không thêm log.

        if self.size[a] < self.size[b]:
            a, b = b, a

        self.history.append((b, a, self.size[a]))
        self.parent[b] = a
        self.size[a] += self.size[b]
        self.components -= 1
        return True

    def rollback(self, checkpoint: int) -> None:
        if not isinstance(checkpoint, int):
            raise TypeError("checkpoint phải là số nguyên")
        if not 0 <= checkpoint <= len(self.history):
            raise ValueError("checkpoint ngoài lịch sử hiện có")

        while len(self.history) > checkpoint:
            child_root, parent_root, old_size = self.history.pop()

            self.parent[child_root] = child_root
            self.size[parent_root] = old_size
            self.components += 1


d = RollbackDSU(4)

assert d.union(0, 1)
checkpoint = d.snapshot()   # Lịch sử có một phép hợp.

assert d.union(1, 2)
assert d.same(0, 2)
assert d.component_size(0) == 3
assert d.components == 2

d.rollback(checkpoint)
assert d.same(0, 1)
assert not d.same(0, 2)
assert d.component_size(0) == 2
assert d.components == 3

# Có thể tiếp tục trên một nhánh lịch sử mới.
assert d.union(2, 3)
assert d.same(2, 3)
assert not d.same(0, 3)

# Hợp trùng không tạo bản ghi vì không sửa cấu trúc.
before = d.snapshot()
assert d.union(0, 1) is False
assert d.snapshot() == before
```

### Vì sao ba trường trong log đủ?

Khi union thành công:

- `b` là gốc của cây bị treo, nên trước đó `parent[b]=b`.
- `a` là gốc được giữ, nên `size[a]` trước hợp cần được lưu.
- `components` giảm đúng một và có thể khôi phục bằng cộng một.

Khi rollback theo thứ tự ngược, những phép hợp đã thực hiện **sau** phép hợp đang khôi phục đã được hoàn tác trước. Vì thế a và b lại có cấu trúc thích hợp để khôi phục bản ghi này.

### Điều kiện sử dụng snapshot

`snapshot()` trả **độ dài stack lịch sử hiện tại**, không phải ID bất biến xuyên mọi nhánh thực thi. Sau khi rollback về một checkpoint rồi tạo các phép hợp mới, những checkpoint cũ thuộc **nhánh lịch sử đã bị bỏ** không còn đại diện cho trạng thái mong muốn.

Để dùng đúng, giữ checkpoint theo **ngăn xếp lời gọi hoặc cây duyệt có thứ tự**, rollback trước khi rời nhánh. Các thuật toán offline trên cây đoạn thường thực hiện chính xác quy tắc này.

## 17. Độ phức tạp và giới hạn của rollback DSU

Với **union by size không compression** trên n phần tử:

| Thao tác | Thời gian | Ghi chú |
|---|---|---|
| Khởi tạo | `O(n)` | Tạo n nhóm đơn |
| `find(x)` | `O(log n)` worst-case | Không nén đường |
| `same(x,y)` | `O(log n)` worst-case | Hai lần find |
| `union(x,y)` | `O(log n)` worst-case | Hai find, thêm tối đa một bản ghi |
| `snapshot()` | `O(1)` | Đọc kích thước stack |
| Hoàn tác **một phép hợp thành công** | `O(1)` | Pop và phục hồi vài ô |
| `rollback(cp)` | `O(k)` | k là số bản ghi thành công bị pop |
| Bộ nhớ | `O(n+H)` | H là số bản ghi đang lưu |

Nhờ union by size, **mỗi lần độ sâu một nút tăng thì kích thước nhóm của nó ít nhất gấp đôi**, nên chiều cao cây không vượt `O(log n)` trong những trạng thái hợp lệ.

Nếu một hệ thống yêu cầu `union` luôn có chặn gần `O(α(n))` khấu hao **và** hỗ trợ undo, phải phân tích riêng thiết kế của hệ thống đó. Không áp trực tiếp kết quả của DSU chuẩn có path compression cho bản rollback không nén.

### Metadata cũng phải được rollback

Nếu lưu thêm:

```text
total[root]
min[root]
max[root]
edgeCount[root]
```

thì khi hợp phải ghi lại **giá trị cũ của mọi trường được sửa**. Nếu rollback chỉ khôi phục `parent` và `size` nhưng quên `total`, DSU có thể trả đúng liên thông mà trả sai tổng trọng số nhóm.

Cùng nguyên tắc với `components`, bộ đếm số cạnh, số nhóm có chu trình hoặc bất kỳ trạng thái phụ nào liên quan tới một phép hợp.

## 18. Offline với thêm và xóa tùy ý: khoảng sống của cạnh

Xử lý đảo thời gian đơn giản không đủ khi một cạnh có thể **được thêm rồi xóa**, và các loại sự kiện trộn lẫn.

Một kỹ thuật offline tiêu chuẩn là xác định **khoảng thời gian tồn tại của từng cạnh**.

Giả sử có T sự kiện, đánh chỉ số:

\[
0,1,\ldots,T-1.
\]

Mỗi cạnh có **ID riêng** và một hoặc nhiều lần hoạt động không chồng lên nhau, tạo các khoảng:

\[
[l,r),
\]

nghĩa là cạnh tồn tại ở các thời điểm `l,l+1,\ldots,r-1` và không tồn tại từ r trở đi.

Ví dụ:

```text
time 0: add a=(0,1)
time 1: add b=(1,2)
time 2: query(0,2)        // true
time 3: remove b
time 4: query(0,2)        // false
time 5: add c=(0,2)
time 6: query(1,2)        // true
time 7: remove a
time 8: query(1,2)        // false
```

Khoảng hoạt động:

```text
a=(0,1): [0,7)
b=(1,2): [1,3)
c=(0,2): [5,9)
```

Tại truy vấn ở time 6, `a` và `c` còn hoạt động nên 1 đi tới 2 qua 0. Tại time 8, chỉ `c` còn hoạt động, nên 1 bị tách khỏi thành phần chứa 0 và 2.

### Tại sao biểu diễn bằng khoảng?

Để trả lời truy vấn tại thời điểm t, cần một DSU có **đúng những cạnh đang hoạt động ở t**. Ta không muốn xóa trực tiếp cạnh khỏi DSU; thay vào đó, xây các trạng thái bằng cách **hợp cạnh trong một nhánh thời gian**, trả lời truy vấn, rồi **rollback** để thử nhánh khác.

## 19. Cây đoạn trên trục thời gian kết hợp rollback

Xây một **segment tree** trên các thời điểm `[0,T)`. Mỗi nút của cây đại diện một khoảng thời gian.

Đối với cạnh hoạt động trong `[l,r)`, gán nó vào **một tập nút** của cây đoạn sao cho hợp các khoảng nút ấy đúng bằng `[l,r)`. Một khoảng được phân tách thành **`O(log T)` nút**.

Khi duyệt cây đoạn theo DFS:

1. Ghi `checkpoint=dsu.snapshot()`.
2. Hợp tất cả cạnh được gán tại nút hiện tại.
3. Nếu đến lá ứng với thời điểm t, trả lời những truy vấn ở t.
4. Nếu là nút trong, đệ quy tới các con.
5. Trước khi rời nút, gọi `dsu.rollback(checkpoint)`.

### Vì sao đúng?

Mỗi lá t nằm dưới **đúng một nút mang mỗi cạnh đang hoạt động tại t**, vì các nút gán của khoảng sống phân tách `[l,r)` mà không chồng lặp trên cùng một đường gốc-lá. Cạnh không hoạt động tại t không nằm trên đường duyệt tới lá t.

Do đó, ngay khi tới lá t, các phép `union` dọc đường gốc-lá đã mô tả **chính xác các cạnh đang tồn tại** tại thời điểm đó. Những phép hợp thừa về mặt liên thông có thể là no-op, nhưng không làm sai kết quả.

Rollback khi rời nhánh bảo đảm các cạnh chỉ dùng cho nhánh đó **không bị giữ nhầm** ở thời điểm khác.

### Độ phức tạp

Đặt:

- `T`: tổng số sự kiện theo thời gian.
- `K`: số **khoảng hoạt động cạnh**.
- `Q`: số truy vấn liên thông.
- `n`: số đỉnh.

Mỗi khoảng sống được gán vào `O(log T)` nút nên có `O(K\log T)` lần hợp cạnh trong quá trình duyệt, dù nhiều phép hợp có thể là no-op.

Với rollback DSU dùng union by size **không nén**, mỗi `union`/`same` tốn `O(log n)` worst-case:

\[
O\bigl(T+(K\log T+Q)\log n+n\bigr).
\]

Bộ nhớ gồm cây sự kiện và các bucket cạnh; với cách lưu đơn giản:

\[
O(n+T+K\log T)
\]

cho DSU, cây đoạn, các danh sách gán cạnh và lịch sử rollback trong quá trình duyệt.

Các biểu thức này là chặn theo **mô hình cài đặt đã mô tả**; nếu cần trả đường đi, giữ các cấu trúc khác hoặc có phép tổng hợp metadata lớn, phải cộng thêm chi phí tương ứng.

## 20. Python: offline dynamic connectivity với segment tree và rollback

Mã minh họa dưới đây dùng:

- `add_edge(edge_id,u,v)`: thêm một cạnh có ID.
- `remove_edge(edge_id)`: xóa cạnh đang hoạt động có ID đó.
- `ask(u,v)`: ghi một truy vấn liên thông và trả ID kết quả.
- `solve()`: trả lời toàn bộ các truy vấn theo thứ tự đã đăng ký.

**Hợp đồng:** chuỗi sự kiện đã biết trước khi gọi `solve`; mỗi ID cạnh được thêm nhiều nhất một lần trong ví dụ, chỉ được xóa khi đang hoạt động, và các đầu mút trong miền `0..n-1`. Đồ thị vô hướng có thể có nhiều cạnh song song nếu chúng mang **ID khác nhau**.

```python
class OfflineDynamicConnectivity:
    def __init__(self, n: int):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n không được âm")

        self.n = n
        self.events: list[tuple] = []
        self.query_count = 0

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Đỉnh phải là số nguyên")
        if not 0 <= x < self.n:
            raise IndexError("Đỉnh ngoài miền")

    def add_edge(self, edge_id: str, u: int, v: int) -> None:
        self._check(u)
        self._check(v)
        self.events.append(("add", edge_id, u, v))

    def remove_edge(self, edge_id: str) -> None:
        self.events.append(("remove", edge_id))

    def ask(self, u: int, v: int) -> int:
        self._check(u)
        self._check(v)
        idx = self.query_count
        self.query_count += 1
        self.events.append(("query", idx, u, v))
        return idx

    def solve(self) -> list[bool]:
        t_count = len(self.events)
        answers = [False] * self.query_count
        if t_count == 0:
            return answers

        opened: dict[str, tuple[int, int, int]] = {}
        used_ids: set[str] = set()
        intervals: list[tuple[int, int, int, int]] = []

        # Bước 1: chuyển sự kiện thành khoảng sống [l,r).
        for t, event in enumerate(self.events):
            kind = event[0]

            if kind == "add":
                _, eid, u, v = event
                if eid in used_ids:
                    raise ValueError("ID cạnh được dùng lại")
                used_ids.add(eid)
                opened[eid] = (t, u, v)

            elif kind == "remove":
                _, eid = event
                if eid not in opened:
                    raise ValueError("Xóa cạnh không hoạt động")
                start, u, v = opened.pop(eid)
                intervals.append((start, t, u, v))

            elif kind != "query":
                raise ValueError("Sự kiện không hợp lệ")

        # Cạnh còn sống tới hết chuỗi.
        for start, u, v in opened.values():
            intervals.append((start, t_count, u, v))

        # Bước 2: cây đoạn thời gian, mỗi bucket là các cạnh.
        buckets: list[list[tuple[int, int]]] = [
            [] for _ in range(4 * t_count)
        ]

        def insert(
            node: int, left: int, right: int,
            ql: int, qr: int, edge: tuple[int, int]
        ) -> None:
            if qr <= left or right <= ql:
                return

            if ql <= left and right <= qr:
                buckets[node].append(edge)
                return

            middle = (left + right) // 2
            insert(node * 2, left, middle, ql, qr, edge)
            insert(node * 2 + 1, middle, right, ql, qr, edge)

        for start, end, u, v in intervals:
            if start < end:
                insert(1, 0, t_count, start, end, (u, v))

        # Bước 3: DFS và rollback theo nhánh thời gian.
        dsu = RollbackDSU(self.n)

        def traverse(node: int, left: int, right: int) -> None:
            checkpoint = dsu.snapshot()

            for u, v in buckets[node]:
                dsu.union(u, v)

            if right - left == 1:
                event = self.events[left]
                if event[0] == "query":
                    _, idx, u, v = event
                    answers[idx] = dsu.same(u, v)

            else:
                middle = (left + right) // 2
                traverse(node * 2, left, middle)
                traverse(node * 2 + 1, middle, right)

            dsu.rollback(checkpoint)

        traverse(1, 0, t_count)
        return answers


offline = OfflineDynamicConnectivity(4)
offline.add_edge("a", 0, 1)
offline.add_edge("b", 1, 2)
offline.ask(0, 2)                # True
offline.remove_edge("b")
offline.ask(0, 2)                # False
offline.add_edge("c", 0, 2)
offline.ask(1, 2)                # True qua 1—0—2.
offline.remove_edge("a")
offline.ask(1, 2)                # False

assert offline.solve() == [True, False, True, False]
```

### Phân biệt thông tin đúng và ví dụ chưa bao phủ

- Chương trình xử lý **thêm và xóa cạnh tùy ý theo thứ tự thời gian**, nhưng **trả lời offline sau khi đã ghi toàn bộ sự kiện**.
- Mỗi ID được dùng một lần. Nếu cần tái sử dụng cùng ID sau khi xóa, phải thay đổi hợp đồng và xây nhiều khoảng sống tương ứng.
- Truy vấn được đăng ký bằng sự kiện riêng, nên trạng thái tại truy vấn là sau mọi sự kiện **đứng trước** nó.
- Không có path compression trong `RollbackDSU`, vì chính các bản ghi `history` sẽ được hoàn tác khi DFS rời nhánh.
- Cạnh song song khác ID được gán khoảng sống riêng; một cạnh hết hiệu lực trong khi cạnh khác còn sống thì tính liên thông vẫn đúng.

Trong ứng dụng thực tế, nên bổ sung kiểm thử độc lập trên đồ thị nhỏ, kiểm soát giới hạn bộ nhớ khi T/K lớn và cơ chế quản lý lịch sử nếu thêm metadata bên cạnh kích thước nhóm.

## 21. Vấn đề tách tập hợp độc lập với xóa cạnh

Không phải mọi yêu cầu “tách nhóm” đều đến từ đồ thị.

Ví dụ, một hệ thống quản lý đội nhóm có:

```text
Team A = {0,1,2,3,4}
```

Người dùng muốn chuyển thành:

```text
Team B = {0,1,4}
Team C = {2,3}
```

DSU chuẩn không có `split(A,B,C)` vì nó không lưu danh sách thành viên theo nhóm và không hỗ trợ thay đổi quan hệ cùng nhóm từ **true** thành **false**.

### Nếu tập phần tử của mỗi nhóm mới đã biết

Có thể:

1. Định nghĩa lại nhãn nhóm cho từng phần tử (nếu chỉ cần truy vấn nhãn).
2. Dựng lại DSU cho các nhóm mới từ phân hoạch được cung cấp.
3. Duy trì một cấu trúc thành viên khác, ví dụ tập hợp hoặc danh sách có thể cập nhật.

Nếu bài toán cho phép chuyển một phần tử giữa nhóm thường xuyên, một **map `member→groupID`** với quản lý tập thành viên có thể tự nhiên hơn DSU. Truy vấn “cùng nhóm” chỉ cần so hai ID, nhưng thao tác hợp hai nhóm có thể cần đổi ID cho nhiều thành viên, tùy cấu trúc.

### Khi nào DSU vẫn phù hợp?

- Khi các nhóm chỉ **hợp dần**.
- Khi thao tác tách hiếm và có thể **xây lại toàn bộ**.
- Khi cần xử lý **offline** theo thứ tự và có thể biến các khoảng thời gian thành nhiều phép hợp rồi rollback.

**Không nên chọn DSU chỉ vì nó có tên “tập hợp”**, nếu nghiệp vụ chủ yếu là thêm/bớt thành viên tùy ý.

## 22. Persistent DSU và truy vấn lịch sử khác với xóa cạnh

Có các biến thể **persistent DSU** duy trì nhiều phiên bản của phân hoạch để hỏi về **thời điểm quá khứ** hoặc rẽ nhánh lịch sử.

Nhưng cần phân biệt:

- **Persistent:** có thể truy cập một hoặc nhiều trạng thái cũ theo hợp đồng của cấu trúc.
- **Rollback:** hoàn tác các thay đổi gần nhất theo thứ tự stack, thường dùng trong DFS offline.
- **Xóa cạnh động:** cập nhật cấu trúc theo việc cạnh thật biến mất và xác định các thành phần mới.

Một persistent DSU có nhiều phiên bản sau các phép hợp **không tự động trả đúng trạng thái sau khi xóa một cạnh cũ**; phiên bản trước khi cạnh ấy được thêm cũng có thể **thiếu nhiều cạnh khác** đã được thêm sau đó.

Ví dụ:

```text
add a=(0,1)
add b=(1,2)
add c=(0,2)
remove b
```

Trạng thái sau `remove b` vẫn có các cạnh a và c; nó **không giống** trạng thái trước khi b được thêm (chỉ có a).

Muốn giải xóa cạnh tùy ý, persistent DSU chỉ là một công cụ khả dĩ bên trong thiết kế lớn hơn; cần mô hình hóa chính xác tập cạnh hoạt động của từng phiên bản.

## 23. Liên thông động trực tuyến: khi phải xử lý thật sự khó

Bài toán **fully dynamic connectivity** cho đồ thị vô hướng hỗ trợ:

```text
insert_edge(u, v)
delete_edge(edge_id)
connected(u, v)
```

theo thứ tự **trực tuyến**, tức trả truy vấn mà không biết trước những sự kiện tương lai.

Khi xóa cạnh của một rừng khung, hệ thống cần biết liệu có **cạnh thay thế** nối hai phần vừa tách hay không. Việc tìm cạnh thay thế là phần khó mà DSU chuẩn không thực hiện.

Các họ giải pháp chuyên dụng có thể sử dụng:

- **Dynamic forest** với các cấu trúc hỗ trợ thay đổi liên kết (ví dụ Euler tour tree hoặc cấu trúc dynamic tree).
- Các tầng/cấp cạnh và cơ chế tìm **replacement edge** sau khi xóa cạnh trong rừng.
- Thuật toán randomized hoặc deterministic cho fully dynamic connectivity với các bảo đảm khác nhau.
- Thuật toán offline nếu tất cả thao tác đã biết trước.

**Cảnh báo về thuật ngữ:** Link–cut tree là một cấu trúc mạnh cho **rừng động**, nhưng một bài toán đồ thị tổng quát có chu trình còn cần xử lý **cạnh ngoài rừng và cạnh thay thế**. Chỉ triển khai link–cut tree đơn lẻ **không lập tức giải** fully dynamic connectivity trong mọi đồ thị.

Bậc độ phức tạp cụ thể phụ thuộc rất mạnh vào thuật toán, mô hình và bảo đảm randomization/amortized/worst-case. Không nên suy ra `O(\log n)` cho mọi thao tác từ việc “dùng một cây động”.

## 24. Cách chọn giải pháp phù hợp

| Dạng bài toán | Giải pháp thường phù hợp | Đánh đổi chính |
|---|---|---|
| Chỉ **thêm cạnh**, hỏi liên thông | DSU chuẩn với size/rank + compression | Rất nhanh, bộ nhớ `O(n)` ngoài cạnh nếu không cần lưu |
| Thêm cạnh và hiếm khi xóa, đồ thị nhỏ | Lưu cạnh thật, BFS/DFS hoặc xây lại DSU | Dễ kiểm chứng; xóa/truy vấn có thể `O(n+m)` |
| Chỉ **xóa cạnh**, toàn bộ truy vấn biết trước | Đảo thời gian + DSU | Cần offline và biết đồ thị ban đầu |
| Thêm/xóa bất kỳ, toàn bộ sự kiện biết trước | Cây đoạn thời gian + rollback DSU | Offline, tốn thêm `O(K\log T)` vị trí cạnh |
| Duyệt nhiều nhánh giả định và cần quay lại checkpoint | Rollback DSU không compression | Chỉ hoàn tác theo stack, `find O(\log n)` |
| Hỏi phân hoạch ở những thời điểm lịch sử | Persistent DSU hoặc lưu phiên bản thích hợp | Không thay thế giải bài toán xóa cạnh |
| Thêm/xóa và hỏi liên thông **trực tuyến** trên đồ thị lớn | Fully dynamic connectivity chuyên dụng | Phức tạp và cần quản lý cạnh thay thế |
| Chia nhóm do nghiệp vụ, biết rõ thành viên từng nhóm | Quản lý nhãn/tập thành viên, dựng lại DSU nếu cần | Chi phí có thể phụ thuộc số thành viên bị chuyển |

### Quy trình ra quyết định

1. **Có xóa cạnh hoặc tách nhóm không?** Nếu không, DSU chuẩn là ứng viên mạnh.
2. **Các thao tác có biết trước không?** Nếu có, xét đảo thời gian hoặc segment tree + rollback.
3. **Có cần trả lời trực tuyến không?** Nếu có nhiều lần xóa, nên nghiên cứu dynamic connectivity.
4. **Có cần chính xác cạnh nào bị xóa không?** Dùng ID cạnh, đặc biệt khi có cạnh song song.
5. **Truy vấn chỉ hỏi same hay cần đường đi/chu trình?** Nếu cần chứng cứ, phải lưu thêm cấu trúc đồ thị.
6. **Có metadata nhóm không?** Bảo đảm cập nhật hoặc rollback mọi trường, không chỉ `parent`.
7. **Cần phép tách do nghiệp vụ, không phải xóa cạnh?** Cân nhắc cấu trúc nhãn và tập thành viên trước khi chọn DSU.

## 25. Sai lầm thường gặp và cách tránh

| Sai lầm | Vấn đề | Cách sửa |
|---|---|---|
| Gọi `union` ngược để “xóa cạnh” | Một phép hợp có thể không tương ứng duy nhất với cạnh đang xóa | Giữ đồ thị thật, xử lý lại liên thông |
| Coi mọi cạnh xóa đều làm tăng số thành phần | Sai khi cạnh thuộc chu trình | Kiểm tra cầu/đường thay thế |
| Coi mọi cạnh xóa đều không làm thay đổi phân hoạch | Sai khi xóa cầu | Rebuild/BFS/dynamic connectivity |
| Dựa vào `parent` để biết cạnh nào tồn tại | Con trỏ cha không phải cạnh thật | Lưu cạnh đầu vào riêng |
| Chỉ sửa `components` khi xóa cầu | Thành viên vẫn cùng root cũ | Cần tạo lại hai nhóm tương ứng |
| Xóa một cạnh song song nhưng xóa luôn toàn bộ cặp đầu mút | Đánh mất cạnh khác đang hoạt động | Quản lý bằng ID hoặc multiplicity |
| Rollback một bản ghi cũ ở giữa stack | Các phép hợp sau phụ thuộc trạng thái trước | Chỉ rollback theo checkpoint LIFO |
| Dùng path compression nhưng log chỉ thay đổi của union | Không khôi phục được các sửa đổi do `find` | Không nén trong rollback hoặc ghi đầy đủ và chứng minh lại |
| Dùng rank làm số thành viên sau tách | Rank không phải size | Duy trì metadata tại gốc theo thiết kế |
| Hoàn tác parent mà không hoàn tác size/tổng | Kết quả truy vấn metadata sai | Ghi lại mọi trường được cập nhật |
| Đảo thời gian cho luồng có thêm/xóa lẫn nhau mà không xử lý khoảng sống | Trạng thái ngược không phản ánh đúng tập cạnh | Segment tree thời gian hoặc thuật toán khác |
| Nghĩ persistent DSU tự hỗ trợ delete | Phiên bản cũ có thể thiếu các cạnh được thêm về sau | Mô hình hóa đầy đủ trạng thái cạnh |
| Dùng DSU cho chu trình có hướng | Quan hệ đi tới không đối xứng | Dùng DFS/topo hoặc thuật toán riêng |
| Tưởng DSU hoàn tác có `O(α(n))` tự động | Bản rollback thường không nén đường | Phân tích `O(\log n)` cho find/union |
| Không xác định truy vấn trước hay sau sự kiện xóa | Lỗi lệch thời gian/off-by-one | Dùng định nghĩa `[l,r)` và test ở ranh giới |
| Dùng snapshot của nhánh lịch sử đã bỏ | Checkpoint không còn nghĩa cũ | Chỉ dùng checkpoint còn hợp lệ trên stack |

## 26. Kiểm thử biên và các bất biến

Để kiểm thử thuật toán thêm/xóa, đừng chỉ xét đường đơn. Cần ít nhất:

- **Cầu:** đường `0—1—2`, xóa `(1,2)` làm tách đỉnh 2.
- **Cạnh không phải cầu:** tam giác `0—1—2—0`, xóa một cạnh vẫn liên thông.
- **Hai cạnh song song:** xóa một cạnh không tách nhóm nếu cạnh kia còn.
- **Khuyên:** thêm/xóa `(u,u)` không thay đổi liên thông giữa các đỉnh khác.
- **Đỉnh cô lập:** một đỉnh không có cạnh vẫn là một thành phần riêng.
- **Nhiều lần xóa trùng ID:** phải báo lỗi hoặc bỏ qua theo hợp đồng, không âm thầm xóa nhiều cạnh.
- **Xóa cầu rồi thêm đường thay thế:** hai thành phần có thể hợp lại.
- **Rollback với hợp trùng:** `union` no-op không được làm sai lịch sử khôi phục.
- **Rollback qua nhiều checkpoint lồng nhau:** khôi phục đúng cả `parent`, `size` và `components`.
- **Truy vấn ngay sát thời điểm add/remove:** kiểm tra quy ước cạnh sống trong `[l,r)`.
- **Đồ thị rỗng:** `n=0`, không có ID đỉnh hợp lệ.
- **Đồ thị một đỉnh:** mọi truy vấn `same(0,0)` đều true; khuyên không làm tách/hợp nhóm.

### Đối chiếu với lời giải chậm nhưng độc lập

Với n nhỏ và chuỗi thao tác ngắn, có thể:

1. Lưu cạnh đang hoạt động bằng ID.
2. Sau mỗi sự kiện, dựng danh sách kề.
3. Chạy BFS/DFS để tính các thành phần.
4. So sánh mọi cặp `connected(u,v)` với kết quả offline/dynamic connectivity.
5. Khi dùng rollback, lưu một bản sao phân hoạch ở checkpoint nhỏ và đối chiếu sau khi phục hồi.

Việc kiểm tra toàn bộ cặp phần tử có thể tốn `O(n^2)`, nhưng phù hợp làm **unit test** với n nhỏ. Nó giúp phát hiện lỗi sai ở những ranh giới thời gian mà mã vẫn biên dịch bình thường.

## 27. Bài tập tự kiểm tra có lời giải

**Câu 1.** DSU chuẩn hỗ trợ những thao tác nền tảng nào?

**Đáp án:** Tạo nhóm đơn, `find` tìm đại diện, `same` so cùng nhóm và `union` hợp hai nhóm. Nó không tự có `split` hoặc `delete_edge` duy trì liên thông.

**Câu 2.** Trong đồ thị đường `0—1—2—3`, xóa `(1,2)` tạo bao nhiêu thành phần?

**Đáp án:** **Hai** thành phần: `{0,1}` và `{2,3}`.

**Câu 3.** Trong tam giác `0—1—2—0`, xóa `(1,2)` làm tăng số thành phần không?

**Đáp án:** **Không**. Còn đường `1—0—2` nối hai đầu.

**Câu 4.** Cạnh nào được gọi là cầu trong đồ thị vô hướng?

**Đáp án:** Cạnh mà việc xóa nó **làm tăng số thành phần liên thông**.

**Câu 5.** Hai đồ thị có cùng một thành phần và cùng số cạnh có chắc phản ứng giống nhau khi xóa một cạnh bất kỳ không?

**Đáp án:** **Không**. Một đồ thị có thể xóa cạnh nằm trong chu trình, đồ thị kia xóa cầu. Metadata tổng hợp như số cạnh/kích thước không mô tả đủ cấu trúc đường thay thế.

**Câu 6.** Vì sao không thể tìm cạnh bị xóa bằng cách duyệt các liên kết `parent` của DSU?

**Đáp án:** Liên kết cha là **cạnh nội bộ của biểu diễn phân hoạch**, không nhất thiết là cạnh thật của đồ thị; path compression còn có thể đổi chúng.

**Câu 7.** Nếu xóa cạnh nhưng số thành phần thực không đổi, có cần tách nhóm trong DSU không?

**Đáp án:** **Không**, phân hoạch liên thông vẫn đúng. Tuy nhiên nếu lưu metadata số cạnh thì phải cập nhật số cạnh cho đúng; cần một cách biết chắc việc xóa không tách nhóm.

**Câu 8.** “Hoàn tác union” có tương đương xóa cạnh bất kỳ không?

**Đáp án:** **Không**. Một cạnh có thể đã dẫn đến union no-op vì hai đầu cùng nhóm; hoặc các cạnh khác được thêm sau khiến việc bỏ một cạnh không tách nhóm.

**Câu 9.** Path compression gây khó khăn gì khi muốn rollback?

**Đáp án:** Một lời gọi `find` có thể sửa **nhiều liên kết cha**, nên muốn khôi phục trạng thái cũ phải ghi lại mọi thay đổi; log chỉ một phép nối gốc là chưa đủ.

**Câu 10.** Rollback DSU thường tránh tối ưu nào?

**Đáp án:** **Path compression** (kể cả các biến thể sửa cha trong find) để mỗi `find` chỉ đọc và mỗi union thành công ghi số lượng trường hằng số.

**Câu 11.** Khi dùng rollback DSU với union by size, `find` có chặn thời gian nào?

**Đáp án:** **`O(log n)` worst-case** nhờ hợp cây nhỏ dưới cây lớn, dù không nén đường.

**Câu 12.** `snapshot()` của lớp RollbackDSU trả gì?

**Đáp án:** Kích thước **stack lịch sử các union thành công** tại thời điểm chụp; `rollback(checkpoint)` pop các thay đổi sau đó để phục hồi trạng thái.

**Câu 13.** Nếu `union(x,y)` là no-op vì đã cùng gốc, có cần thêm bản ghi vào `history` ở ví dụ không?

**Đáp án:** **Không**, vì không có thay đổi cần hoàn tác. Snapshot theo kích thước lịch sử vẫn chính xác. Một API rollback khác có thể dùng sentinel cho no-op nếu yêu cầu undo theo số lệnh, nhưng phải nhất quán.

**Câu 14.** Tại sao rollback không thể bỏ một bản ghi bất kỳ ở giữa ngăn xếp và giữ nguyên phần còn lại?

**Đáp án:** Các phép hợp sau được tính trên **trạng thái do phép hợp trước tạo ra**. Bỏ bản ghi cũ ở giữa có thể làm các gốc, size và metadata của bản ghi sau không còn hợp lệ.

**Câu 15.** Bài toán chỉ xóa cạnh, biết toàn bộ thao tác trước, có thể biến thành bài toán nào?

**Đáp án:** Duyệt **ngược thời gian** để biến mỗi phép xóa thành **thêm lại cạnh**, từ đó dùng DSU chỉ hỗ trợ union.

**Câu 16.** Trong tam giác a=(0,1), b=(1,2), c=(0,2), xóa b rồi c. Kết quả truy vấn `connected(0,2)` trước xóa, sau xóa b, sau xóa c là gì?

**Đáp án:** `[true, true, false]`.

**Câu 17.** Trong thuật toán offline segment tree, một cạnh hoạt động ở `[l,r)` có hiện diện tại thời điểm r không?

**Đáp án:** **Không**. Nó có mặt tại `l,l+1,\ldots,r-1` và hết hiệu lực kể từ r.

**Câu 18.** Tại sao phải rollback sau khi rời một nhánh của cây đoạn thời gian?

**Đáp án:** Để những cạnh chỉ hoạt động trong nhánh vừa xử lý **không bị giữ nhầm** khi duyệt nhánh thời gian khác.

**Câu 19.** Với K khoảng sống cạnh và T thời điểm, mỗi khoảng được gán tới bao nhiêu nút segment tree?

**Đáp án:** **`O(log T)`** nút trong phép phân tách khoảng tiêu chuẩn.

**Câu 20.** Khi dùng segment tree + rollback DSU không nén, chi phí một lần union là bao nhiêu?

**Đáp án:** **`O(log n)` worst-case** do phải tìm hai gốc; việc pop một thay đổi đã ghi chỉ tốn `O(1)`.

**Câu 21.** Nếu một cạnh vật lý có hai bản sao song song với ID khác nhau và xóa một bản sao, có nhất thiết tách thành phần không?

**Đáp án:** **Không**. Bản sao còn lại vẫn nối cùng hai đỉnh; cần quản lý cạnh theo ID hoặc bộ đếm số lượng.

**Câu 22.** Persistent DSU có tự giải được mọi truy vấn xóa cạnh không?

**Đáp án:** **Không**. Một phiên bản trước lúc thêm cạnh bị xóa có thể thiếu các cạnh được thêm sau đó; xóa cạnh tùy ý cần mô hình hóa tập cạnh hiện hoạt.

**Câu 23.** Vì sao chỉ có link–cut tree không mặc nhiên giải xóa cạnh trong đồ thị tổng quát?

**Đáp án:** Link–cut tree quản lý **rừng động**, còn đồ thị tổng quát có **cạnh ngoài rừng** cần được xét làm cạnh thay thế khi một cạnh rừng bị xóa.

**Câu 24.** Nếu một ứng dụng thường xuyên chia nhân viên giữa các đội theo danh sách thành viên rõ ràng, DSU chuẩn có phải lựa chọn hiển nhiên không?

**Đáp án:** **Không**. Nên cân nhắc quản lý `member→groupID` cùng danh sách/tập thành viên, vì thao tác chính là **tách/chuyển thành viên**, không chỉ hợp.

**Câu 25.** Cách đơn giản và dễ kiểm chứng nhất để trả đúng liên thông sau xóa cạnh trên đồ thị nhỏ là gì?

**Đáp án:** **Lưu cạnh thật** rồi dùng **BFS/DFS** trên đồ thị hiện tại, hoặc dựng lại DSU từ các cạnh còn hoạt động.

**Câu 26.** Có thể giữ nguyên `total[root]` và `size[root]` khi một nhóm thật sự bị tách do xóa cầu không?

**Đáp án:** **Không**. Phải xác định thành viên từng thành phần mới và tính lại hoặc chuyển metadata phù hợp; giữ metadata cũ sẽ cho kết quả sai.

## Ghi nhớ

- **DSU chuẩn là cấu trúc để hợp nhóm**, không phải cấu trúc hỗ trợ chia nhóm tùy ý. `parent` mô tả phân hoạch, **không** lưu đủ các cạnh đồ thị để quyết định xóa cạnh nào làm tách nhóm.
- Trong đồ thị vô hướng, xóa **cầu** làm tăng số thành phần; xóa cạnh nằm trên chu trình có thể **không** làm tăng số thành phần. Chỉ nhìn `find`/`size`/`edgeCount` không đủ để biết.
- **Xóa cạnh khác hoàn tác union.** Một phép hợp có thể là no-op và những cạnh đến sau có thể tạo đường thay thế. Nén đường đi càng làm việc phục hồi cấu trúc cũ phức tạp.
- Với dữ liệu nhỏ hoặc ít xóa, giữ **cạnh thật** và dùng **BFS/DFS hoặc xây lại DSU** là cách rõ ràng, dễ kiểm thử.
- Nếu **biết trước các thao tác chỉ xóa**, có thể **đảo thời gian** để đổi xóa thành thêm và dùng DSU chuẩn. Nếu thêm/xóa xen kẽ được biết trước, dùng **cây đoạn thời gian + rollback DSU** là một kỹ thuật offline tiêu biểu.
- **Rollback DSU thường không nén đường**, dùng union by size/rank và stack ghi thay đổi; `find`/`union` có chặn `O(log n)` worst-case, còn rollback một bản ghi thành công tốn `O(1)`. Snapshot chỉ phù hợp khi khôi phục theo nhánh lịch sử hợp lệ.
- Với xóa cạnh trực tuyến thường xuyên ở đồ thị lớn, cần xem xét **fully dynamic connectivity** chuyên dụng. Nếu yêu cầu là **tách/chuyển thành viên theo nghiệp vụ**, một cấu trúc quản lý nhãn và tập thành viên có thể phù hợp hơn DSU.
