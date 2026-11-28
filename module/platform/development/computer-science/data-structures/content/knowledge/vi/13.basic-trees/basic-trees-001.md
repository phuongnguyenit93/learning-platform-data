# Cây như quan hệ phân cấp và cây như đồ thị liên thông không chu trình

## 1. Hai cách nhìn về một cấu trúc cây

Trong học phần **Cấu trúc dữ liệu**, cây (*tree*) xuất hiện khi dữ liệu được tổ chức theo cấp bậc: thư mục chứa thư mục con, một mục trong danh mục có các mục con, hay một biểu thức gồm nhiều biểu thức thành phần. Ta thường vẽ một **gốc (root)** ở trên cùng và các **nút con (children)** ở các cấp phía dưới.

Nhưng trong lý thuyết đồ thị, cây còn có một định nghĩa không cần gốc:

> **Cây vô hướng là một đồ thị liên thông và không có chu trình.**

Hai cách nhìn bổ sung cho nhau:

- **Cây phân cấp/cây có gốc (rooted tree):** làm rõ quan hệ cha–con, tổ tiên–hậu duệ, độ sâu và cây con.
- **Cây như đồ thị vô hướng (undirected tree):** làm rõ sự liên thông, đường đi duy nhất, sự vắng mặt chu trình và tính chất số cạnh.

Ta có thể chọn một đỉnh bất kỳ của cây vô hướng làm gốc, rồi định hướng mỗi cạnh **từ cha tới con**. Khi đó có được cách nhìn phân cấp mà không làm thay đổi cấu trúc liên kết bên dưới.

Mục tiêu của bài là hiểu chính xác **khi nào một cấu trúc là cây**, cách chuyển giữa hai góc nhìn, các **bất biến** cần duy trì, và chi phí **thời gian–bộ nhớ** của các thao tác cơ bản. Đây là nền tảng trước khi học sâu hơn về cây nhị phân, cây tìm kiếm, heap và duyệt đồ thị.

## 2. Định nghĩa cây theo lý thuyết đồ thị

### 2.1. Đỉnh, cạnh, đường đi và chu trình

Một **đồ thị** được ký hiệu `G = (V, E)`, trong đó:

- `V` là tập **đỉnh** (*vertices*); với cây, ta thường gọi chúng là **nút** (*nodes*).
- `E` là tập **cạnh** (*edges*) nối các cặp đỉnh.
- Trong bài này, nếu không nói khác đi, ta xét **đồ thị hữu hạn, vô hướng, đơn**: cạnh `{u,v}` không có hướng, không có cạnh khuyên `{u,u}`, và không có các cạnh song song trùng nhau.

**Đường đi (path)** từ `u` đến `v` là một dãy đỉnh mà hai đỉnh liên tiếp được nối bằng cạnh. **Đường đi đơn (simple path)** không lặp lại đỉnh. Độ dài đường đi được tính bằng **số cạnh** của nó.

**Liên thông (connected)** nghĩa là mọi cặp đỉnh đều có đường đi nối chúng. **Chu trình (cycle)** là một đường khép kín đi qua các đỉnh khác nhau, ngoại trừ đỉnh đầu và cuối trùng nhau; trong đồ thị đơn vô hướng, chu trình có ít nhất ba cạnh.

Một đồ thị có thể:

- Liên thông nhưng có chu trình.
- Không có chu trình nhưng bị chia thành nhiều thành phần.
- Vừa liên thông vừa không có chu trình: **đó chính là cây**.

### 2.2. Ví dụ một cây vô hướng

```text
          A
         / \
        B   C
       / \   \
      D   E   F

V = {A, B, C, D, E, F}

E = { {A,B}, {A,C}, {B,D}, {B,E}, {C,F} }
```

Đồ thị có `6` đỉnh và `5` cạnh. Từ bất kỳ đỉnh nào cũng đi được tới các đỉnh còn lại, và không có đường khép kín nào dùng các cạnh của đồ thị.

Ví dụ, đường đi đơn từ `D` tới `F` là:

```text
D — B — A — C — F
```

Trong cây, **không có đường đi đơn thứ hai khác** nối hai đỉnh đó. Ta sẽ chứng minh tính chất này ở phần sau.

### 2.3. Các trường hợp biên

- **Một đỉnh, không cạnh:** đồ thị `V = {A}`, `E = ∅` là một cây hợp lệ. Đường đi từ `A` đến chính nó có độ dài `0`.
- **Không đỉnh:** một số API cho phép biểu diễn *cây rỗng* để làm giá trị nền, chẳng hạn `root = None`. Trong định nghĩa đồ thị ở bài này, ta dùng quy ước **cây có ít nhất một đỉnh**; trường hợp `n = 0` được xử lý riêng.
- **Nhiều thành phần không có chu trình:** đó là **rừng (forest)**, không phải một cây liên thông duy nhất.

Việc nêu rõ quy ước cây rỗng và loại đồ thị đang xét giúp tránh nhầm lẫn khi áp dụng công thức số cạnh hoặc viết hàm kiểm tra tính hợp lệ.

## 3. Cây dưới góc nhìn quan hệ phân cấp

Khi chọn `A` làm gốc của ví dụ trên, ta có thể biểu diễn cây bằng các quan hệ **cha–con**:

```text
                 A           ← root, depth = 0
               /   \
              B     C        ← depth = 1
             / \     \
            D   E     F      ← depth = 2
```

### Những thuật ngữ cơ bản

| Thuật ngữ | Ý nghĩa | Trong ví dụ |
|---|---|---|
| **Nút gốc (root)** | Nút được chọn làm điểm bắt đầu của quan hệ phân cấp; không có cha | `A` |
| **Cha (parent)** | Nút trực tiếp phía trên một nút trong cách định gốc | Cha của `E` là `B` |
| **Con (child)** | Nút có cha trực tiếp là nút đang xét | `B` có con `D, E` |
| **Anh chị em (siblings)** | Các nút có cùng một cha | `D` và `E` |
| **Tổ tiên (ancestor)** | Nút nằm trên đường từ gốc đến nút đang xét, không tính chính nó theo quy ước bài này | Tổ tiên của `E` là `B, A` |
| **Hậu duệ (descendant)** | Nút nằm phía dưới trong cây phân cấp, không tính chính nút đang xét | `D` và `E` là hậu duệ của `B` |
| **Nút lá (leaf)** | Nút **không có con** | `D, E, F` |
| **Nút trong (internal node)** | Nút có ít nhất một con | `A, B, C` |
| **Cây con (subtree)** | Một nút và toàn bộ hậu duệ của nó | Cây con gốc `B` gồm `B, D, E` |
| **Độ sâu (depth)** | Số cạnh từ gốc tới nút | `depth(E) = 2` |
| **Chiều cao (height)** | Số cạnh trên đường dài nhất từ nút xuống một lá trong cây có gốc | `height(B) = 1` |

Trong bài này, **độ sâu của gốc là `0`**, **chiều cao của một lá là `0`**, và **chiều cao của cả cây** bằng chiều cao của gốc. Một số tài liệu đếm theo **số nút** thay vì số cạnh nên cho kết quả chênh nhau `1` với cây không rỗng; khi giải bài toán, luôn làm rõ quy ước.

### Tính độ sâu và chiều cao trên ví dụ

- `depth(A) = 0`.
- `depth(B) = depth(C) = 1`.
- `depth(D) = depth(E) = depth(F) = 2`.
- `height(D) = height(E) = height(F) = 0`.
- `height(B) = height(C) = 1`.
- `height(A) = 2`.

Độ sâu đo **khoảng cách từ gốc xuống nút**; chiều cao đo **đường xa nhất từ nút xuống một lá**. Chúng là hai khái niệm khác nhau, dù có cùng giá trị ở vài trường hợp.

### Mỗi nút có bao nhiêu cha?

Trong một cây có gốc hợp lệ:

1. **Gốc có đúng `0` cha**.
2. **Mỗi nút không phải gốc có đúng `1` cha**.
3. Một nút có thể có **`0, 1, 2` hoặc nhiều con**, trừ khi bài toán đặt thêm giới hạn về số con.
4. Mọi nút đều đi tới được từ gốc thông qua một chuỗi cạnh cha–con.
5. Không được có vòng cha–con, chẳng hạn `A` là cha của `B`, `B` là cha của `C`, rồi `C` lại là cha của `A`.

Các điều kiện này là **bất biến của quan hệ phân cấp**. Chúng khiến mỗi nút có một vị trí duy nhất trong cây có gốc.

**Đừng nhầm cây nói chung với cây nhị phân.** Cây nhị phân giới hạn mỗi nút tối đa **hai con có vai trò trái/phải**; cây tổng quát có thể có nhiều con và không bắt buộc phân biệt thứ tự các con.

## 4. Từ cây vô hướng đến cây có gốc

Một cây vô hướng ban đầu **không có cha, con, tổ tiên hay độ sâu**. Các khái niệm đó chỉ xuất hiện sau khi chọn một đỉnh làm **gốc**.

Xét lại tập cạnh:

```text
A—B, A—C, B—D, B—E, C—F
```

Nếu chọn `A` làm gốc, `A` là cha của `B` và `C`. Nhưng nếu chọn `D` làm gốc, quan hệ thay đổi:

```text
                  D
                  |
                  B
                 / \
                A   E
                |
                C
                |
                F
```

Lúc này:

- `D` không có cha; `B` là con của `D`.
- `A` và `E` là con của `B`.
- `C` là con của `A`; `F` là con của `C`.
- `depth(F) = 4` thay vì `2` khi chọn gốc `A`.

**Tập đỉnh và tập cạnh không thay đổi**, nên tính liên thông, việc không có chu trình và số cạnh vẫn giữ nguyên. Nhưng **cha–con, tổ tiên–hậu duệ, độ sâu và chiều cao** đều có thể thay đổi theo gốc.

### Quy tắc chuyển đổi

Cho một cây vô hướng `T = (V,E)` và chọn gốc `r`:

1. Đặt `parent[r] = None` và `depth[r] = 0`.
2. Duyệt cây bằng BFS hoặc DFS bắt đầu từ `r`.
3. Khi lần đầu đi từ nút `u` sang nút `v` chưa thăm, đặt `parent[v] = u` và `depth[v] = depth[u] + 1`.
4. Coi cạnh `{u,v}` được **định hướng từ `u` tới `v`** trong biểu diễn phân cấp.

Vì cây có **đúng một đường đi đơn** từ gốc tới mỗi đỉnh, việc gán cha theo cách này là nhất quán: không có hai đường đi khác nhau cùng tranh quyền xác định cha của một nút.

### Cây có gốc như một đồ thị có hướng

Khi hướng các cạnh từ cha sang con, ta có một đồ thị có hướng dạng cây phân nhánh ra (*out-arborescence*):

- Gốc có bậc vào `0`.
- Mọi nút khác có bậc vào `1`.
- Mọi nút đều tới được từ gốc bằng đường có hướng.
- Không có chu trình có hướng.

Chiều ngược lại cũng có ích: một cấu trúc có các cạnh cha–con, trong đó **một gốc duy nhất** có bậc vào `0`, mọi nút khác có bậc vào `1` và **tất cả nút đều tới được từ gốc**, sẽ có cấu trúc cây có gốc. Bỏ hướng các cạnh sẽ thu được cây vô hướng.

**Cảnh báo:** chỉ kiểm tra “mỗi nút nhiều nhất một cha” vẫn **chưa đủ**. Một thành phần khác có thể tạo chu trình hoặc không nối với gốc. Điều kiện toàn bộ nút đều thuộc cùng phân cấp là bắt buộc.

## 5. Những tính chất nhận diện cây

Trong phần này, giả sử `G = (V,E)` là đồ thị **hữu hạn, vô hướng, đơn** và có `n = |V| \ge 1` đỉnh.

### 5.1. Giữa hai đỉnh có đúng một đường đi đơn

**Mệnh đề:** `G` là cây khi và chỉ khi giữa **mọi cặp đỉnh khác nhau** tồn tại đúng **một đường đi đơn**.

**Chiều từ cây sang đường đi duy nhất:**

- Vì cây **liên thông**, giữa `u` và `v` có ít nhất một đường đi.
- Giả sử có hai đường đi đơn khác nhau nối `u` với `v`. Theo hai đường đi đó, có một đoạn rẽ nhánh rồi gặp lại nhau, tạo ra một **chu trình**.
- Điều này mâu thuẫn với giả thiết cây không có chu trình. Vậy đường đi đơn là duy nhất.

**Chiều ngược lại:**

- Có đường đi giữa mọi cặp nên đồ thị liên thông.
- Nếu đồ thị có chu trình, lấy hai đỉnh phân biệt trên chu trình sẽ có hai đường đi đơn khác nhau dọc theo hai phía của chu trình.
- Mâu thuẫn với điều kiện đường đi duy nhất; vậy đồ thị không có chu trình và do đó là cây.

Tính chất này giải thích vì sao trong một cây có gốc, mỗi nút không phải gốc có thể nhận **một cha duy nhất**: đó là đỉnh đứng ngay trước nó trên đường đi duy nhất từ gốc.

### 5.2. Cây có đúng `n - 1` cạnh

Với cây có `n \ge 1` đỉnh:

\[
|E| = n - 1.
\]

Ví dụ:

| Số đỉnh `n` | Số cạnh của cây `n - 1` | Hình dạng có thể gặp |
|---:|---:|---|
| 1 | 0 | Một nút đứng riêng |
| 2 | 1 | Hai nút nối nhau |
| 4 | 3 | Một đường thẳng hoặc hình sao |
| 6 | 5 | Cây ví dụ `A, B, C, D, E, F` |
| 10 | 9 | Bất kỳ cây nào gồm 10 đỉnh |

Một cách chứng minh là **quy nạp theo số đỉnh**:

- Với `n = 1`, cây chỉ có một đỉnh, không có cạnh, nên đúng `0 = 1 - 1`.
- Mọi cây hữu hạn có ít nhất hai đỉnh đều có **ít nhất một nút bậc `1`** (một lá theo nghĩa đồ thị vô hướng).
- Bỏ nút lá này cùng cạnh nối nó với cây sẽ để lại một cây có `n - 1` đỉnh. Theo giả thiết quy nạp, cây còn lại có `n - 2` cạnh.
- Thêm lại nút lá và cạnh của nó được `(n - 2) + 1 = n - 1` cạnh.

**Lưu ý quan trọng:** chỉ có `n - 1` cạnh **chưa đủ** kết luận là cây. Ví dụ, đồ thị có bốn đỉnh `A, B, C, D` và ba cạnh `AB, BC, CA` có đúng `4 - 1 = 3` cạnh nhưng `A, B, C` tạo chu trình còn `D` bị cô lập. Đồ thị này **không liên thông**, nên không phải cây.

Để kết luận là cây, có thể dùng một trong các cặp điều kiện tương đương:

- **Liên thông** và **không có chu trình**.
- **Liên thông** và có đúng **`n - 1` cạnh**.
- **Không có chu trình** và có đúng **`n - 1` cạnh**.

Các kết luận trên áp dụng cho đồ thị hữu hạn vô hướng đơn có ít nhất một đỉnh.

### 5.3. Xóa một cạnh bất kỳ làm cây mất liên thông

**Mệnh đề:** Mỗi cạnh của cây là một **cầu (bridge)**: bỏ cạnh ấy sẽ chia cây thành đúng hai thành phần liên thông.

Giải thích: giả sử bỏ cạnh `{u,v}` mà vẫn có một đường đi khác nối `u` và `v`. Khi thêm cạnh `{u,v}` trở lại, ta tạo thành một chu trình, mâu thuẫn với tính không chu trình của cây. Do đó không còn đường nối hai phía.

Ví dụ, xóa cạnh `A—B` trong cây mẫu làm tách thành hai thành phần:

```text
Thành phần 1:   A—C—F
Thành phần 2:   D—B—E
```

Các cạnh khác của cây không bị thay đổi. Một cây **liên thông vừa đủ**: bỏ một cạnh thì mất liên thông.

### 5.4. Thêm cạnh giữa hai đỉnh chưa kề nhau tạo đúng một chu trình

Giả sử `u` và `v` là hai đỉnh **khác nhau, chưa có cạnh nối trực tiếp** trong cây. Trong cây đã có đúng một đường đi đơn từ `u` tới `v`. Khi thêm cạnh `{u,v}`, đường đi cũ cộng cạnh mới tạo thành một chu trình.

Vì trước đó không có chu trình và chỉ thêm một cạnh, **đó là chu trình đơn duy nhất** được tạo ra.

Ví dụ, thêm cạnh `D—F` vào cây mẫu tạo chu trình:

```text
D — B — A — C — F — D
```

Tính chất này giải thích vì sao các thuật toán xây cây khung phải từ chối thêm cạnh nối hai đỉnh vốn đã cùng một thành phần liên thông.

## 6. Cây, rừng, đồ thị có chu trình và DAG khác nhau ở đâu?

| Cấu trúc | Liên thông (theo đồ thị vô hướng)? | Có chu trình? | Có phải cây vô hướng? |
|---|---|---|---|
| `A—B—C` | Có | Không | Có |
| Tam giác `A—B—C—A` | Có | Có | Không |
| `A—B` và `C—D` tách biệt | Không | Không | Không; đây là rừng |
| Tam giác `A—B—C—A` và `D` cô lập | Không | Có | Không |
| Một đỉnh `A` không cạnh | Có theo quy ước liên thông của đồ thị một đỉnh | Không | Có |

Một **rừng** là đồ thị vô hướng không có chu trình; mỗi **thành phần liên thông** của rừng là một cây. Nếu rừng có `n` đỉnh và `c` thành phần liên thông, số cạnh là:

\[
|E| = n - c.
\]

Khi `c = 1`, công thức trở về `|E| = n - 1` của một cây.

### DAG không nhất thiết là cây

**DAG (Directed Acyclic Graph)** là đồ thị có hướng không chu trình. Nó có thể biểu diễn phụ thuộc công việc và có những nút được đi tới từ **nhiều cha**.

Ví dụ:

```text
       A
      / \
     B   C
      \ /
       D

Các cạnh có hướng: A→B, A→C, B→D, C→D
```

Đây là DAG nếu các mũi tên đều hướng xuống, nhưng **không phải cây phân cấp**: `D` có hai cha là `B` và `C`. Nếu bỏ hướng, các cạnh tạo thành chu trình `A—B—D—C—A`.

Vì vậy, “không có chu trình **có hướng**” không đồng nghĩa “đồ thị vô hướng tương ứng không có chu trình”. Không nên coi mọi DAG là cây.

### Cây có gốc không nhất thiết là cây nhị phân

Một cây phân cấp mà nút `A` có bốn con vẫn là cây hợp lệ, miễn là mỗi con chỉ có một cha, mọi nút thuộc cùng một cây, và không có chu trình. **Cây nhị phân** là một biến thể có ràng buộc thêm: mỗi nút tối đa hai con với vai trò trái/phải.

## 7. Hai cách lưu trữ cấu trúc cây

Cách lưu trữ được chọn phụ thuộc thao tác cần thực hiện. Với một cây có `n` nút và `n - 1` cạnh, cả hai mô hình dưới đây có thể sử dụng **`O(n)` bộ nhớ**.

### 7.1. Danh sách kề (adjacency list): nhìn theo đồ thị vô hướng

Với cây mẫu có các cạnh `A—B, A—C, B—D, B—E, C—F`:

```text
A: [B, C]
B: [A, D, E]
C: [A, F]
D: [B]
E: [B]
F: [C]
```

Mỗi cạnh vô hướng được lưu trong danh sách kề của **cả hai đầu mút**, nên có tổng cộng `2(n - 1)` mục kề.

**Ưu điểm:** phù hợp khi cần kiểm tra liên thông, tìm đường đi, gán gốc tùy chọn hoặc thực hiện DFS/BFS trên đồ thị. **Nhược điểm:** chưa có sẵn cha/con; khi muốn biểu diễn phân cấp, phải chọn gốc và suy ra cha từ quá trình duyệt.

### 7.2. Mảng cha và danh sách con: nhìn theo phân cấp

Nếu nút được đánh số `0..n-1` và chọn `0` làm gốc, ta có thể lưu:

```text
parent[0] = None
parent[1] = 0
parent[2] = 0
parent[3] = 1
parent[4] = 1
parent[5] = 2

children[0] = [1, 2]
children[1] = [3, 4]
children[2] = [5]
children[3] = []
children[4] = []
children[5] = []
```

Mảng `parent` cho phép biết **cha trực tiếp** của một nút trong `O(1)` thời gian. Danh sách `children[u]` cho phép duyệt các con trực tiếp trong thời gian tỉ lệ với số con.

Nếu mỗi nút không phải gốc lưu đúng một tham chiếu tới cha, tổng số tham chiếu cha khác `None` là `n - 1`. Nếu cũng lưu danh sách con, sẽ có thêm `n - 1` mục con, vì mỗi cạnh cha–con xuất hiện đúng một lần.

**Thứ tự con cần được định nghĩa riêng.** Trong cây vô hướng tổng quát, không có “con trái nhất” tự nhiên. Nếu ứng dụng là cây thư mục sắp xếp theo tên hoặc cây cú pháp có thứ tự, thứ tự các con trở thành một phần của mô hình dữ liệu; nếu không, nó có thể chỉ là thứ tự do thuật toán duyệt tạo ra.

## 8. Cài đặt Python: kiểm tra một đồ thị có phải cây không

Ta nhận đầu vào gồm:

- `n`: số đỉnh, được đánh số `0, 1, ..., n - 1`.
- `edges`: danh sách các cặp `(u, v)` biểu diễn cạnh vô hướng.

**Quy ước:** đồ thị cần là **đơn** và có **ít nhất một đỉnh**. Hàm dưới đây từ chối cạnh khuyên, cạnh trùng và đỉnh nằm ngoài phạm vi. Để nhận diện cây, dùng tính chất:

> Một đồ thị vô hướng đơn có `n \ge 1` đỉnh là cây khi và chỉ khi nó **liên thông** và có đúng **`n - 1` cạnh**.

```python
def is_undirected_tree(n, edges):
    if n < 1:
        return False

    # Điều kiện cần về số cạnh.
    if len(edges) != n - 1:
        return False

    adjacency = [[] for _ in range(n)]
    seen_edges = set()

    for u, v in edges:
        # Bài toán giả định u, v là các số nguyên.
        if not (0 <= u < n and 0 <= v < n):
            return False
        if u == v:
            return False  # Cạnh khuyên

        # {u, v} và {v, u} là cùng một cạnh vô hướng.
        edge = (min(u, v), max(u, v))
        if edge in seen_edges:
            return False
        seen_edges.add(edge)

        adjacency[u].append(v)
        adjacency[v].append(u)

    # DFS chỉ để kiểm tra mọi đỉnh có tới được từ 0 không.
    visited = {0}
    pending = [0]

    while pending:
        u = pending.pop()
        for v in adjacency[u]:
            if v not in visited:
                visited.add(v)
                pending.append(v)

    return len(visited) == n


print(is_undirected_tree(1, []))  # True
print(is_undirected_tree(4, [(0, 1), (1, 2), (1, 3)]))
# True: liên thông, ba cạnh, không chu trình

print(is_undirected_tree(4, [(0, 1), (1, 2), (2, 0)]))
# False: tam giác và đỉnh 3 cô lập

print(is_undirected_tree(4, [(0, 1), (2, 3)]))
# False: rừng có hai thành phần

print(is_undirected_tree(3, [(0, 1), (1, 0)]))
# False: cạnh trùng trong đồ thị vô hướng đơn
```

### Vì sao hai bước kiểm tra là đủ?

1. **Đúng `n - 1` cạnh** là điều kiện cần của cây.
2. **DFS từ `0` thăm được tất cả `n` đỉnh** chứng tỏ đồ thị liên thông.
3. Theo định lý ở phần 5, một đồ thị vô hướng đơn vừa liên thông vừa có `n - 1` cạnh **không thể có chu trình**. Do đó nó là cây.

Việc kiểm tra `seen_edges` có vai trò bảo vệ **hợp đồng đồ thị đơn**. Nếu đầu vào cho phép cạnh trùng hoặc cạnh khuyên mà không xử lý, có thể xuất hiện sai lệch giữa số cạnh được báo cáo và cấu trúc đồ thị được hiểu trong chứng minh.

### Độ phức tạp

Gọi `n = |V|`, `m = |E|`:

- Xây danh sách kề mất `O(n + m)` thời gian, nếu phép thêm và tra cứu tập cạnh có chi phí trung bình `O(1)`.
- DFS duyệt tối đa `n` đỉnh và `2m` mục kề, mất `O(n + m)` thời gian.
- Danh sách kề, tập cạnh và tập đã thăm dùng `O(n + m)` bộ nhớ.
- Với một **ứng viên** vượt qua kiểm tra `m = n - 1`, các chi phí này rút gọn thành **`O(n)`**.

Trong mã có sử dụng cấu trúc băm `set`; thời gian trung bình giả định phép băm hoạt động thông thường. Phần kiểm tra chấp nhận `n \ge 1` và giả định định danh đỉnh là số nguyên; một thư viện tổng quát có thể kiểm tra kiểu đầu vào chặt chẽ hơn.

## 9. Cài đặt Python: chọn gốc và dựng quan hệ cha–con

Khi đã xác nhận đầu vào là cây vô hướng, có thể chọn bất kỳ đỉnh nào làm gốc và dùng **BFS (Breadth-First Search)** để dựng mảng cha, danh sách con và độ sâu.

Ví dụ dưới đây dùng lại hàm `is_undirected_tree` vừa định nghĩa:

```python
from collections import deque


def root_undirected_tree(n, edges, root=0):
    if not is_undirected_tree(n, edges):
        raise ValueError("Đầu vào không phải cây vô hướng đơn")
    if not 0 <= root < n:
        raise ValueError("Gốc nằm ngoài phạm vi")

    adjacency = [[] for _ in range(n)]
    for u, v in edges:
        adjacency[u].append(v)
        adjacency[v].append(u)

    parent = [None] * n
    children = [[] for _ in range(n)]
    depth = [-1] * n

    depth[root] = 0
    pending = deque([root])

    while pending:
        u = pending.popleft()
        for v in adjacency[u]:
            if depth[v] != -1:
                continue

            parent[v] = u
            children[u].append(v)
            depth[v] = depth[u] + 1
            pending.append(v)

    return parent, children, depth


edges = [(0, 1), (0, 2), (1, 3), (1, 4), (2, 5)]

parent, children, depth = root_undirected_tree(
    6, edges, root=0
)

print(parent)
# [None, 0, 0, 1, 1, 2]

print(children)
# [[1, 2], [3, 4], [5], [], [], []]

print(depth)
# [0, 1, 1, 2, 2, 2]
```

### Bất biến trong BFS

- `depth[root] = 0` và `parent[root] = None`.
- Mỗi nút chỉ được phát hiện một lần, vì trước khi thêm vào hàng đợi ta đã gán `depth[v]` khác `-1`.
- Khi phát hiện `v` từ `u`, đặt `parent[v] = u` và `depth[v] = depth[u] + 1`.
- Với đầu vào đã là cây, có **đúng một đường đi** từ gốc đến `v`, nên `parent[v]` chính là cha của `v` trên đường đi đó.

BFS thường dùng **queue (FIFO)** để thăm theo từng lớp. DFS dùng **stack (LIFO)** cũng dựng được cùng quan hệ cha–con khi đầu vào là cây; vì mỗi nút có đường đi duy nhất từ gốc, lựa chọn BFS hay DFS không làm thay đổi cha của nút khi chọn cùng một gốc. Thứ tự duyệt các nút có thể khác.

**Chi phí:** xây dựng và duyệt cây có `n` nút mất **`O(n)` thời gian** và **`O(n)` bộ nhớ phụ** trong trường hợp xấu nhất, bao gồm danh sách kề, hàng đợi và các mảng cha/con/độ sâu.

## 10. Duyệt cây và vai trò của stack, queue

Trong cây, ta thường cần duyệt mọi nút để tính tổng, tìm một nút, thống kê số lá hoặc xuất cấu trúc phân cấp.

### Duyệt theo chiều sâu (DFS)

**DFS** đi sâu theo một nhánh trước khi quay lại các nhánh còn lại. Nếu biểu diễn bằng danh sách con, ta có thể dùng stack tường minh:

```python
def dfs_preorder(children, root):
    result = []
    stack = [root]

    while stack:
        u = stack.pop()
        result.append(u)

        # Đảo thứ tự push để xử lý con đứng trước trước.
        for v in reversed(children[u]):
            stack.append(v)

    return result


print(dfs_preorder(children, 0))
# [0, 1, 3, 4, 2, 5]
```

Với cây có gốc hợp lệ, mỗi nút có đúng một cha nên chỉ được đưa vào stack một lần khi duyệt từ gốc. Nếu áp dụng mã này cho một **đồ thị có chu trình**, ta phải bổ sung tập `visited` để tránh duyệt lặp.

### Duyệt theo chiều rộng (BFS)

**BFS** xử lý tất cả các nút ở độ sâu hiện tại trước khi sang độ sâu tiếp theo:

```python
from collections import deque


def bfs_order(children, root):
    result = []
    pending = deque([root])

    while pending:
        u = pending.popleft()
        result.append(u)
        pending.extend(children[u])

    return result


print(bfs_order(children, 0))
# [0, 1, 2, 3, 4, 5]
```

Trên cây `n` nút:

| Phương pháp | Cấu trúc công việc | Thời gian | Bộ nhớ phụ cho công việc chờ |
|---|---|---|---|
| DFS lặp | Stack | `O(n)` | Tối đa `O(n)` |
| BFS lặp | Queue | `O(n)` | Tối đa `O(n)` |
| DFS đệ quy | Call stack | `O(n)` | `O(h)` với `h` là chiều cao tính theo số cạnh, tới `O(n)` |

Danh sách kết quả của hai hàm ở trên lưu thêm `n` phần tử, tốn **`O(n)` bộ nhớ**. Nếu chỉ cần xử lý từng nút ngay khi duyệt, có thể tránh việc tạo danh sách kết quả này.

Với cây rộng, BFS có thể cần lưu nhiều nút cùng một tầng. Với cây sâu và lệch, DFS đệ quy có thể tạo chuỗi lời gọi rất sâu; khi đó DFS bằng stack tường minh thường tránh được giới hạn đệ quy của runtime.

## 11. Các thao tác thay đổi cạnh và bất biến cây

Định nghĩa **liên thông và không chu trình** đặt ra yêu cầu cho mọi thao tác chỉnh sửa cấu trúc.

### 11.1. Thêm một nút lá

Nếu thêm một **đỉnh mới** `x` cùng **một cạnh** nối `x` với một đỉnh `u` đang thuộc cây:

- Đồ thị vẫn liên thông vì `x` nối với `u`.
- Không thể tạo chu trình vì `x` chỉ có một cạnh.
- Số đỉnh từ `n` thành `n + 1`, số cạnh từ `n - 1` thành `n`; vẫn thỏa `(n + 1) - 1`.

Vì vậy, **gắn một lá mới vào một đỉnh bất kỳ** luôn tạo một cây mới hợp lệ.

### 11.2. Xóa một cạnh

Trong cây vô hướng, xóa bất kỳ cạnh nào làm cây tách thành **hai thành phần**. Đây là kết quả tất yếu của tính chất “mọi cạnh là cầu”.

Nếu muốn **xóa một cây con** trong cây có gốc, ta cần quyết định rõ có xóa toàn bộ các nút hậu duệ khỏi tập dữ liệu không, hay chỉ tách cây con thành một cây riêng. Việc chỉ xóa cạnh cha–con tạo ra **một rừng**, không phải một cây duy nhất trên toàn bộ tập nút cũ.

### 11.3. Đổi cha của một nút

Giả sử muốn chuyển cây con gốc `u` sang một cha mới `v`:

1. Không được chọn `v` nằm **trong chính cây con của `u`**; nếu vậy sẽ tạo quan hệ cha–con vòng.
2. Bỏ cạnh nối `u` với cha cũ, nếu `u` không phải gốc.
3. Thêm cạnh mới nối `v` với `u` để gắn lại cây con.
4. Cập nhật mảng cha, danh sách con và các thông tin phụ thuộc gốc như độ sâu/chiều cao.

Nếu thực hiện không cẩn thận, ta có thể tạo **chu trình**, **nhiều cha cho một nút** hoặc để lại các thành phần **mất liên thông**. Một API sửa cây nên kiểm tra điều kiện trước và cập nhật cấu trúc một cách nhất quán.

### 11.4. Thêm cạnh giữa hai nút đang có

Nếu thêm một cạnh giữa hai đỉnh chưa kề nhau của cùng cây, đồ thị sẽ có một chu trình. Vì vậy nếu mục tiêu là giữ dữ liệu dạng cây, **không thể tự ý thêm cạnh như trong đồ thị tổng quát**.

Nếu ứng dụng cần thêm quan hệ giữa hai nút đang có mà không phải quan hệ cha–con, có thể cần **mô hình đồ thị** thay vì cố ép mọi liên hệ vào một cây.

## 12. Khi nào nên dùng mô hình cây và khi nào nên dùng đồ thị?

### Cấu trúc phù hợp với cây

- **Cây phân tích cú pháp (syntax tree):** một biểu thức có các biểu thức con; mỗi nút thuộc một vị trí cha nhất định trong cấu trúc.
- **Cấu trúc menu phân cấp:** một mục thuộc đúng một mục cha trong phạm vi một cây menu.
- **Cây trò chơi hoặc cây tìm kiếm:** mỗi nút biểu diễn một trạng thái trong một đường mở rộng; khi **không gộp các trạng thái trùng nhau**, cấu trúc tìm kiếm có thể có dạng cây.
- **Cây phân loại có một cha:** mỗi mục có duy nhất một nhóm cha và toàn bộ danh mục có một gốc.

### Khi cây không đủ

- **Một tài liệu thuộc nhiều danh mục cha:** cấu trúc có thể là DAG hoặc đồ thị, không phải cây phân cấp cha duy nhất.
- **Phụ thuộc công việc:** một tác vụ phụ thuộc vào nhiều tác vụ khác; thường biểu diễn bằng DAG.
- **Mạng đường đi có nhiều tuyến thay thế:** có nhiều đường đi giữa hai địa điểm, nên thường có chu trình và cần mô hình đồ thị.
- **Tổ chức có quan hệ báo cáo ma trận:** một người có thể có nhiều cấp quản lý theo vai trò khác nhau.
- **Hệ thống tệp có liên kết:** hình ảnh thư mục thông thường gợi cây, nhưng **symlink**, liên kết cứng hoặc cơ chế gắn kết có thể làm quan hệ tham chiếu phức tạp hơn một cây lý tưởng.

Điều cốt lõi không nằm ở việc dữ liệu *trông có vẻ phân cấp*, mà ở các điều kiện có thật: **mỗi nút có một cha hay không, mọi nút có thuộc cùng một gốc hay không, và có tồn tại chu trình hay không**.

## 13. Những nhầm lẫn phổ biến

1. **Cho rằng cây bắt buộc có gốc trong định nghĩa đồ thị.** Cây vô hướng không cần chọn gốc; gốc là cách bổ sung quan hệ phân cấp.
2. **Nhầm liên thông với không chu trình.** Một tam giác vẫn liên thông nhưng không phải cây.
3. **Chỉ đếm `n - 1` cạnh.** Đồ thị có thể vừa có chu trình vừa bị ngắt thành phần, dù tổng cạnh bằng `n - 1`.
4. **Nghĩ cây phải có hai con ở mỗi nút.** Cây tổng quát cho phép số con bất kỳ; cây nhị phân mới giới hạn tối đa hai.
5. **Nhầm số con với bậc của đỉnh vô hướng.** Ở một nút không phải gốc, bậc vô hướng bằng **số con cộng một cạnh tới cha**; ở gốc, bậc bằng số con.
6. **Nhầm độ sâu và chiều cao.** Độ sâu đi từ gốc đến nút; chiều cao đi từ nút đến lá xa nhất.
7. **Cho rằng đổi gốc sẽ đổi số cạnh.** Chọn gốc chỉ định hướng lại quan hệ cha–con, không làm thay đổi đồ thị vô hướng.
8. **Xem mọi DAG như cây.** DAG có thể có nút nhiều cha và đồ thị vô hướng nền có chu trình.
9. **Dùng DFS trên đồ thị bất kỳ mà không đánh dấu đã thăm.** Chu trình có thể khiến thuật toán lặp vô hạn; trong cây hợp lệ, mỗi nút không phải gốc có một cha.
10. **Bỏ qua quy ước cây rỗng.** Trong API có thể tồn tại `root = None`, nhưng định lý `n - 1` cạnh ở đây giả định `n \ge 1`.
11. **Nhầm thứ tự các con là đặc trưng của mọi cây.** Chỉ cây có thứ tự (ordered tree) hoặc một bài toán cụ thể mới đòi thứ tự con.
12. **Gắn cây con vào chính hậu duệ của nó.** Thao tác đó tạo chu trình trong quan hệ cha–con và phá bất biến.

## 14. Bài tập luyện tập có đáp án

### Bài 1. Nhận diện cây từ danh sách cạnh

Có `5` đỉnh `{0,1,2,3,4}` và các cạnh `{(0,1), (1,2), (1,3), (3,4)}`. Đây có phải cây không?

**Đáp án:** Có. Đồ thị liên thông, không có chu trình và có `5 - 1 = 4` cạnh.

### Bài 2. Vì sao chỉ đếm số cạnh là không đủ?

Có `4` đỉnh và các cạnh `{(0,1), (1,2), (2,0)}`. Số cạnh bằng `n - 1`. Vì sao đồ thị vẫn không phải cây?

**Đáp án:** Ba đỉnh `0,1,2` tạo chu trình và đỉnh `3` bị cô lập. Đồ thị không liên thông. Số cạnh `n - 1` chỉ là điều kiện cần nếu không kiểm tra liên thông hoặc không có chu trình.

### Bài 3. Đổi gốc

Trong cây có các cạnh `A—B, A—C, B—D`, nếu chọn `D` làm gốc, cha của `A` là ai và `depth(C)` bằng bao nhiêu?

**Đáp án:** Đường từ `D` tới `A` là `D—B—A`, nên cha của `A` là `B`. Đường `D—B—A—C` có `3` cạnh, nên `depth(C) = 3`.

### Bài 4. Đường đi duy nhất

Trong cây ví dụ `A, B, C, D, E, F`, hãy tìm đường đi đơn từ `E` đến `F`. Có thể tồn tại đường đi đơn thứ hai không?

**Đáp án:** `E—B—A—C—F`. Không thể có đường đi đơn khác, vì hai đường khác nhau sẽ tạo chu trình, trái với định nghĩa cây.

### Bài 5. Một cạnh bị xóa

Một cây có `10` đỉnh. Nếu xóa một cạnh bất kỳ nhưng giữ nguyên tất cả đỉnh, còn bao nhiêu thành phần liên thông? Nếu không thêm cạnh lại, cấu trúc mới còn là cây không?

**Đáp án:** Có đúng **hai thành phần liên thông**. Cấu trúc mới là rừng, không còn là một cây liên thông trên toàn bộ 10 đỉnh.

### Bài 6. Thêm một cạnh

Một cây vô hướng có `6` đỉnh và `5` cạnh. Nếu thêm cạnh giữa hai đỉnh chưa kề nhau, điều gì xảy ra?

**Đáp án:** Số cạnh thành `6`, đồng thời tạo **đúng một chu trình đơn mới** do đường đi duy nhất cũ giữa hai đỉnh kết hợp với cạnh mới. Đồ thị không còn là cây.

### Bài 7. Số cạnh của rừng

Một rừng có `n = 12` đỉnh và `c = 3` thành phần liên thông. Có bao nhiêu cạnh?

**Đáp án:** `n - c = 12 - 3 = 9` cạnh.

### Bài 8. Phân biệt depth và height

Cho cây có gốc:

```text
      R
     / \
    X   Y
       /
      Z
```

Tính `depth(Z)`, `height(Y)` và `height(R)` theo quy ước đếm số cạnh.

**Đáp án:** `depth(Z) = 2`, `height(Y) = 1` và `height(R) = 2`. `X` và `Z` là lá, có chiều cao `0`.

### Bài 9. Cây có gốc và nhiều cha

Một cấu trúc có các cạnh có hướng `A→B, A→C, B→D, C→D`. Có thể coi đó là một cây phân cấp với gốc `A` không?

**Đáp án:** Không, vì `D` có hai cha `B` và `C`. Cấu trúc là một DAG có hướng, nhưng không phải cây phân cấp mỗi nút chỉ có một cha.

### Bài 10. Chọn cấu trúc phù hợp

Một ứng dụng cần quản lý các mục thư mục thông thường với mỗi mục có đúng một thư mục cha, nhưng cũng muốn hỗ trợ “tài liệu thuộc nhiều thư mục khác nhau” bằng các liên kết tham chiếu. Nên hiểu toàn bộ quan hệ dữ liệu là cây hay đồ thị?

**Đáp án:** Quan hệ **chứa trực tiếp** có thể được tổ chức thành cây có gốc. Nhưng nếu tính cả các **liên kết tham chiếu** cho phép một tài liệu được truy cập từ nhiều vị trí, toàn bộ quan hệ có thể cần mô hình đồ thị/DAG hoặc phân biệt rõ hai loại cạnh, thay vì coi tất cả là cạnh cha–con của một cây duy nhất.

## 15. Tổng kết

**Cây** có hai góc nhìn chặt chẽ và bổ trợ:

- Theo **đồ thị vô hướng**, cây là đồ thị **liên thông và không có chu trình**; với `n \ge 1` đỉnh, cây có **`n - 1` cạnh**, có **đúng một đường đi đơn** giữa mỗi cặp đỉnh, và việc xóa một cạnh bất kỳ sẽ làm đồ thị mất liên thông.
- Theo **quan hệ phân cấp**, sau khi chọn một gốc, mỗi nút không phải gốc có **đúng một cha**, gốc không có cha, và mọi nút đều đi tới được từ gốc. Các khái niệm **con, tổ tiên, hậu duệ, độ sâu, chiều cao và cây con** phát sinh từ lựa chọn gốc đó.

Để cài đặt, ta có thể dùng **danh sách kề** khi muốn làm việc với cây như đồ thị, hoặc **mảng cha và danh sách con** khi ưu tiên thao tác phân cấp. DFS/BFS duyệt cây `n` nút trong **`O(n)` thời gian**; bộ nhớ lưu liên kết cũng là **`O(n)`**. Khi lựa chọn cấu trúc, hãy kiểm tra dữ liệu có thật sự có **một đường liên kết duy nhất và một quan hệ cha duy nhất** hay không. Nếu xuất hiện nhiều cha, chu trình hoặc các quan hệ chéo, cần mô hình đồ thị phù hợp thay vì ép dữ liệu vào cây.
