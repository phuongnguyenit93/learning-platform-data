# Cài đặt cơ bản bằng mảng cha

Một hệ thống quản lý tám máy tính cần duy trì các nhóm máy đang có thể liên lạc với nhau. Ban đầu mỗi máy là một nhóm riêng. Khi thêm liên kết vô hướng giữa hai máy, hệ thống **hợp hai nhóm**; khi nhận câu hỏi “hai máy có cùng nhóm không?”, hệ thống cần trả lời dựa trên những liên kết đã thêm.

Có thể lưu nhãn nhóm cho mọi máy và cập nhật hàng loạt sau mỗi lần hợp. Tuy nhiên, một cách thường hiệu quả và dễ mở rộng hơn là **Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, dùng **mảng cha** `parent` để biểu diễn mỗi nhóm thành một cây có gốc.

Bài này nằm trong chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trọng tâm là **tự cài đặt phiên bản DSU cơ bản bằng mảng cha**, hiểu chính xác hàm `find`, `union`, bất biến rừng cây, mô phỏng từng phép cập nhật và phân tích độ phức tạp thời gian/bộ nhớ. Cuối bài sẽ nhận diện hạn chế của bản cơ bản và định hướng các tối ưu như **hợp theo kích thước** và **nén đường đi**.

## 1. Xác định bài toán trước khi chọn cấu trúc dữ liệu

Giả sử miền phần tử được đánh số liên tục:

\[
U = \{0,1,\ldots,n-1\}.
\]

Tại một thời điểm, `U` được chia thành những nhóm `G₁, G₂, …, G_c` sao cho:

1. Không nhóm nào rỗng.
2. Hai nhóm khác nhau **không giao nhau**.
3. Hợp của các nhóm bằng toàn bộ `U`.

Đây là một **phân hoạch (partition)**. Mỗi phần tử thuộc **đúng một nhóm**.

Ví dụ:

```text
Miền U = {0,1,2,3,4,5,6,7}

Ban đầu:
{0} {1} {2} {3} {4} {5} {6} {7}

Sau khi nối các cặp (0,1), (2,3), (1,2):
{0,1,2,3} {4} {5} {6} {7}
```

Trong cách hiểu **thành phần liên thông vô hướng**, cặp `(1,2)` kết nối **hai nhóm đang chứa** 1 và 2, không chỉ ghi riêng một quan hệ giữa hai nút đó.

Các thao tác ta cần gồm:

| Thao tác | Ý nghĩa |
|---|---|
| `initialize(n)` | Tạo `n` nhóm đơn |
| `find(x)` | Tìm đại diện của nhóm chứa `x` |
| `union(x,y)` | Hợp toàn bộ nhóm chứa `x` với nhóm chứa `y` |
| `same(x,y)` | Kiểm tra hai phần tử có cùng nhóm |
| `component_count()` | Đếm tổng số nhóm nếu duy trì biến đếm |
| `members(x)` | Liệt kê thành viên nhóm chứa `x` nếu thật sự cần |

DSU cơ bản đặc biệt phù hợp nếu bài toán chủ yếu có **hợp dần các nhóm** và **truy vấn cùng nhóm**. Nếu yêu cầu tách nhóm hoặc xóa cạnh làm thay đổi liên thông, DSU thông thường chưa đủ.

## 2. Mảng `parent` biểu diễn điều gì?

Thay vì lưu một danh sách thành viên bên trong mỗi nhóm, ta lưu một mảng:

```text
parent[x] = chỉ số nút cha của x
```

Nếu một nút là **gốc**, ta quy định:

```text
parent[root] = root
```

Đường đi theo cha từ bất kỳ phần tử nào phải kết thúc ở **một gốc duy nhất**. Những phần tử đi tới cùng gốc thuộc cùng nhóm.

Ví dụ:

```text
          0                 4          7
        /   \               |
       1     2              5
             |
             3

Nhóm {0,1,2,3}          Nhóm {4,5}    Nhóm {7}
```

Ta có thể ghi mảng:

```text
Chỉ số x:   0 1 2 3 4 5 6 7
parent[x]:  0 0 0 2 4 4 6 7
```

Ở đây thực tế có **bốn nhóm**: `{0,1,2,3}`, `{4,5}`, `{6}` và `{7}`. Nút `6` tự trỏ vì là gốc của nhóm đơn; sơ đồ trên chủ ý chưa vẽ nhóm đơn `{6}`.

Muốn biết `3` thuộc nhóm nào, lần theo đường:

```text
3 → parent[3]=2 → parent[2]=0 → parent[0]=0
                                               ^
                                               Gốc
```

Vì vậy:

```text
find(3) = 0
find(1) = 0
find(5) = 4
find(7) = 7
```

**Điểm quan trọng:** `parent[3] = 2` **không** có nghĩa `3` thuộc nhóm có đại diện 2. Số `2` chỉ là **cha trực tiếp** của 3. Đại diện thật sự là `find(3)=0`.

### Rừng cây cha không nhất thiết là cạnh của đồ thị gốc

Nếu đang dùng DSU để quản lý liên thông, các liên kết `parent[x]` là **liên kết nội bộ của cấu trúc dữ liệu**. Chúng không bắt buộc trùng với các cạnh thật được thêm vào đồ thị. Vì thế không thể lấy mảng cha để dựng trực tiếp đường đi thực tế giữa hai đỉnh.

## 3. Bất biến bắt buộc của rừng cha

Một cài đặt đúng phải giữ những bất biến sau:

**Bất biến 1 — Cha nằm trong miền.** Với mọi `x` từ `0` đến `n-1`:

\[
0 \leq \mathrm{parent}[x] < n.
\]

**Bất biến 2 — Mỗi nhóm có đúng một gốc.** Một gốc `r` thỏa `parent[r] == r`.

**Bất biến 3 — Không có chu trình cha sai quy tắc.** Khi đi theo `parent`, mỗi nút cuối cùng tới một gốc. Vòng tự trỏ tại gốc là quy ước dừng; chu trình `0→1→0` hoặc `1→2→3→1` là **không hợp lệ**.

**Bất biến 4 — Đại diện xác định nhóm.**

\[
x\text{ cùng nhóm }y
\iff
\operatorname{find}(x)=\operatorname{find}(y).
\]

**Bất biến 5 — Mọi phần tử xuất hiện đúng một lần trong rừng.** Các cây rời nhau và bao phủ `U`.

Nếu lưu thêm biến `components`:

\[
\mathrm{components}=\#\{x \mid \mathrm{parent}[x]=x\}.
\]

Điều kiện trên đúng khi mảng cha hợp lệ. Mỗi lần hợp **hai gốc khác nhau** làm giảm số gốc và số nhóm đúng một.

### Hợp đồng xử lý chỉ số

Bản cài đặt bên dưới nhận phần tử có chỉ số nguyên `0 ≤ x < n`. Chỉ số âm hoặc quá lớn **không hợp lệ**. Đặc biệt trong Python, `parent[-1]` sẽ truy cập phần tử cuối nếu không kiểm tra; đó không phải cách quản lý nhóm mong muốn.

## 4. Khởi tạo bằng mảng: mỗi phần tử một nhóm

Phiên bản cơ bản khởi tạo bằng cách đặt cha của mỗi phần tử bằng chính nó:

```text
initialize(n):
    parent = new array of n integers

    for x from 0 to n-1:
        parent[x] = x

    components = n
```

Với `n=8`:

```text
x:          0 1 2 3 4 5 6 7
parent[x]:  0 1 2 3 4 5 6 7
```

Mỗi vị trí tự trỏ, nên có tám gốc và tám nhóm đơn.

**Độ phức tạp:** phải ghi `n` phần tử, nên khởi tạo là **`Θ(n)` thời gian** và mảng cha cần **`Θ(n)` phần tử bộ nhớ**. Nếu lưu một biến đếm số nhóm, nó chỉ tốn thêm `O(1)` bộ nhớ.

### Liên hệ với `make-set`

Đối với miền đã biết trước, constructor `initialize(n)` tương đương gọi `make_set(x)` một lần cho mọi `x∈U`. Trong cài đặt mảng kích thước cố định, không cần một hàm `make_set(x)` riêng để tạo phần tử động.

Nếu bài toán thêm ID mới trong khi chạy, ta có thể dùng mảng động `append` hoặc bảng ánh xạ ID ngoài sang chỉ số liên tục. Đây là một quyết định thiết kế khác; không nên tự gán lại `parent[x]=x` cho phần tử đã nằm trong nhóm.

## 5. Hàm `find(x)`: đi theo cha tới gốc

Thuật toán không tối ưu hóa đường đi có thể viết:

```text
find(x):
    require 0 <= x < n

    while parent[x] != x:
        x = parent[x]

    return x
```

Khi gặp `parent[x] == x`, ta đã tới gốc và trả về đại diện.

Ví dụ:

```text
parent = [0,0,0,2,4,4,6,7]

find(3):
    x = 3 → parent[3] = 2
    x = 2 → parent[2] = 0
    x = 0 → parent[0] = 0, dừng
    kết quả = 0

find(5):
    x = 5 → parent[5] = 4
    x = 4 → parent[4] = 4, dừng
    kết quả = 4
```

Bản `find` cơ bản này **chỉ đọc** mảng cha; nó chưa thực hiện **path compression**.

### Phân tích thời gian

Gọi `h` là chiều cao của cây chứa x, tính bằng số cạnh cha trên đường dài nhất từ một nút tới gốc. `find(x)` đi theo tối đa `h` cạnh, do đó có thời gian:

\[
T_{\mathrm{find}}(x)=O(h).
\]

- Cây chỉ có một nút: `h=0`, một lần kiểm tra và trả về.
- Cây hình sao: `h=1`.
- Cây dạng chuỗi `n` nút: `h=n-1`, nên thời gian xấu nhất **`O(n)`**.

Đọc `parent[x]` riêng lẻ là `O(1)`, nhưng **tìm gốc không mặc nhiên `O(1)`**, vì phải đi qua nhiều vị trí của mảng.

### Tại sao thuật toán dừng?

Nếu rừng thỏa bất biến, mọi chuỗi liên kết cha từ x kết thúc ở một gốc tự trỏ. Vòng lặp dừng tại gốc ấy. Nếu mảng cha bị hỏng, ví dụ:

```text
parent[0] = 1
parent[1] = 0
```

thì `find(0)` sẽ đi `0→1→0→1→...` không dừng. Bảo đảm cấu trúc rừng hợp lệ là **tiền đề** của hàm `find`.

## 6. Hàm `union(x,y)`: nối hai gốc, không nối hai nút bất kỳ

Để hợp **hai nhóm chứa x và y**, thuật toán bắt buộc tìm đại diện của cả hai:

```text
union(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    parent[ry] = rx
    components -= 1
    return true
```

Quy tắc `parent[ry] = rx` ở đây là một quyết định đơn giản để minh họa. Nó gắn **gốc của nhóm y** làm con của **gốc nhóm x**. Vì hai gốc khác nhau thuộc hai cây rời nhau, thao tác này hợp toàn bộ hai nhóm và không tạo chu trình.

### Ví dụ: gộp trọn hai nhóm

Trước:

```text
Nhóm A: {0,1}         Nhóm B: {2,3}

parent:
x:       0 1 2 3
value:   0 0 2 2
```

Gọi `union(1,3)`:

```text
rx = find(1) = 0
ry = find(3) = 2

parent[2] = 0

Mảng sau:
x:       0 1 2 3
value:   0 0 0 2
```

Nút 3 vẫn có cha trực tiếp 2, nhưng giờ đường của nó là `3→2→0`. Vậy cả bốn phần tử thuộc **một nhóm**, và `components` giảm từ 2 xuống 1.

### Vì sao `parent[y] = x` là sai?

Nếu thay bằng `parent[3] = 1`:

```text
parent mới: [0,0,2,1]
```

Khi đó `3` nhập nhóm `{0,1}`, còn `2` vẫn là một gốc riêng. Ta đã làm vỡ nhóm `{2,3}` thay vì hợp cả hai nhóm. Nếu gán tùy ý trong cùng một cây, còn có thể tạo chu trình cha.

**Bài học:** gọi `find` lấy hai gốc trước khi sửa `parent` là điều kiện để giữ bất biến phân hoạch.

### Khi hai phần tử đã cùng nhóm

Nếu `find(x) == find(y)`, việc hợp không thay đổi phân hoạch. Không được giảm `components` và không được nối con trỏ khác.

```text
union(0,3) lần đầu: có thể hợp hai nhóm → true
union(0,3) lần sau: đã cùng nhóm → false
```

Trong bài này, `union` trả `true` nếu **thật sự giảm số nhóm**, trả `false` nếu đã cùng nhóm. Điều kiện này giúp kiểm tra thuật toán và phát hiện cạnh tạo chu trình.

## 7. Hàm `same(x,y)` và biến đếm số nhóm

Hai phần tử cùng nhóm khi đại diện của chúng bằng nhau:

```text
same(x, y):
    return find(x) == find(y)
```

Ta có thể duy trì `components` từ khi khởi tạo:

- Ban đầu: `components = n`.
- Mỗi lần `union` trả `true`: `components -= 1`.
- Mỗi lần `union` trả `false`: `components` giữ nguyên.

Một lời gọi `component_count()` chỉ đọc biến này, nên **`O(1)`**.

Nếu không muốn lưu metadata, ta có thể đếm số gốc bằng cách quét mảng:

```text
count_roots(parent):
    count = 0
    for x in 0..n-1:
        if parent[x] == x:
            count += 1
    return count
```

Cách này mất **`O(n)` thời gian** mỗi lần hỏi nhưng không có nguy cơ biến đếm bị cập nhật sai khi viết `union`. Dù dùng cách nào, số gốc và số nhóm phải nhất quán.

## 8. Mô phỏng chi tiết: tám phần tử, sáu lần gộp

Ta dùng `union(x,y)` cơ bản, luôn cho **gốc nhóm chứa y** trỏ tới **gốc nhóm chứa x**, không hợp theo kích thước và không nén đường đi.

Trạng thái ban đầu:

```text
parent = [0,1,2,3,4,5,6,7]
components = 8
```

Thực hiện chuỗi:

```text
union(0,1)
union(2,3)
union(4,5)
union(1,2)
union(6,7)
union(5,6)
```

| Bước | Thao tác | `parent` sau thao tác | Số nhóm |
|---:|---|---|---:|
| 0 | Khởi tạo | `[0,1,2,3,4,5,6,7]` | 8 |
| 1 | `union(0,1)` | `[0,0,2,3,4,5,6,7]` | 7 |
| 2 | `union(2,3)` | `[0,0,2,2,4,5,6,7]` | 6 |
| 3 | `union(4,5)` | `[0,0,2,2,4,4,6,7]` | 5 |
| 4 | `union(1,2)` | `[0,0,0,2,4,4,6,7]` | 4 |
| 5 | `union(6,7)` | `[0,0,0,2,4,4,6,6]` | 3 |
| 6 | `union(5,6)` | `[0,0,0,2,4,4,4,6]` | 2 |

Giải thích hai bước dễ nhầm:

**Bước 4 — `union(1,2)`.** `find(1)=0` và `find(2)=2`, nên ta gán `parent[2]=0`. Nút 3 vẫn trỏ tới 2, tạo đường `3→2→0`, không phải tự động đổi `parent[3]`.

**Bước 6 — `union(5,6)`.** `find(5)=4` và `find(6)=6`, nên ta gán `parent[6]=4`. Nút 7 vẫn trỏ tới 6 và tìm được gốc 4 bằng đường `7→6→4`.

Trạng thái cuối:

```text
Nhóm A: {0,1,2,3}  (gốc 0)
Nhóm B: {4,5,6,7}  (gốc 4)

find(3) = 0
find(7) = 4
same(1,3) = true
same(3,7) = false
components = 2
```

Nếu gọi tiếp `union(3,0)`, hai gốc đều bằng 0. Hàm trả `false` và `components` vẫn bằng 2.

## 9. Cài đặt Python tối thiểu: đúng ba thao tác cơ bản

Dưới đây là một cài đặt đầy đủ với mảng `parent`. Để giữ rõ **phiên bản cơ bản**, hàm `find` **không nén đường đi** và `union` **chưa dùng size/rank**.

```python
class ParentArrayDSU:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("Số phần tử phải không âm")
        self.parent = list(range(n))
        self.components = n

    def _check_index(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền DSU")

    def find(self, x: int) -> int:
        self._check_index(x)
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        self.parent[ry] = rx
        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_count(self) -> int:
        return self.components

    def members(self, x: int) -> list[int]:
        # Bản cơ bản không lưu sẵn danh sách thành viên.
        root = self.find(x)
        return [
            i for i in range(len(self.parent))
            if self.find(i) == root
        ]


dsu = ParentArrayDSU(8)
for a, b in ((0, 1), (2, 3), (4, 5),
             (1, 2), (6, 7), (5, 6)):
    assert dsu.union(a, b)

assert dsu.parent == [0, 0, 0, 2, 4, 4, 4, 6]
assert dsu.component_count() == 2
assert dsu.same(1, 3)
assert not dsu.same(3, 7)

assert dsu.members(3) == [0, 1, 2, 3]
assert dsu.members(7) == [4, 5, 6, 7]

assert dsu.union(3, 0) is False
assert dsu.component_count() == 2

print(dsu.parent)    # [0, 0, 0, 2, 4, 4, 4, 6]
print(dsu.members(7)) # [4, 5, 6, 7]
```

### Những gì lớp này bảo đảm

- `__init__` tạo `n` cây đơn.
- `_check_index` từ chối chỉ số âm, vượt phạm vi, không phải số nguyên và cả `bool` (Python xem `bool` là lớp con của `int`).
- `find` trả gốc hiện tại và không thay đổi mảng.
- `union` chỉ nối **hai gốc khác nhau**, giảm số nhóm đúng một.
- `same` dựa trên đại diện, không so sánh trực tiếp `parent[x]` với `parent[y]`.
- `members` minh họa cách lấy thành viên khi chưa có chỉ mục riêng: phải **quét toàn bộ miền**.

### Hạn chế của việc công khai `parent`

Ví dụ để `parent` có thể truy cập từ ngoài nhằm hỗ trợ học và quan sát. Trong phần mềm thực tế nên coi đây là **trạng thái nội bộ**. Nếu mã bên ngoài tùy tiện thực hiện `dsu.parent[0] = 1`, nó có thể phá bất biến hoặc tạo vòng cha.

Có thể dùng quy ước `_parent` và API chỉ đọc, hoặc đóng gói trong lớp C++ với trường `private`. Dù vậy, quy ước đóng gói của ngôn ngữ chỉ giảm rủi ro; tính đúng đắn vẫn phụ thuộc các hàm duy trì bất biến.

## 10. Viết bằng C với mảng nguyên cố định

Trong C, ý tưởng DSU có thể triển khai rất trực tiếp. Ví dụ sau chỉ nhận `N=8` phần tử, và giả định hàm nội bộ `find_root` được gọi với chỉ số hợp lệ. Hàm `unite` kiểm tra chỉ số để không truy cập ngoài mảng.

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

enum { N = 8 };

typedef struct {
    size_t parent[N];
    size_t components;
} DSU;

static void dsu_init(DSU *dsu) {
    dsu->components = N;
    for (size_t i = 0; i < N; ++i) {
        dsu->parent[i] = i;
    }
}

// Điều kiện: x < N và dsu trỏ đến đối tượng hợp lệ.
static size_t find_root(const DSU *dsu, size_t x) {
    while (dsu->parent[x] != x) {
        x = dsu->parent[x];
    }
    return x;
}

static bool dsu_union(DSU *dsu, size_t a, size_t b) {
    if (a >= N || b >= N) return false;

    size_t root_a = find_root(dsu, a);
    size_t root_b = find_root(dsu, b);
    if (root_a == root_b) return false;

    dsu->parent[root_b] = root_a;
    --dsu->components;
    return true;
}

static bool dsu_same(const DSU *dsu, size_t a, size_t b,
                     bool *result) {
    if (a >= N || b >= N || result == NULL) return false;
    *result = find_root(dsu, a) == find_root(dsu, b);
    return true;
}

int main(void) {
    DSU dsu;
    dsu_init(&dsu);

    dsu_union(&dsu, 0, 1);
    dsu_union(&dsu, 2, 3);
    dsu_union(&dsu, 1, 2);

    bool connected = false;
    if (dsu_same(&dsu, 0, 3, &connected)) {
        printf("0 va 3 cung nhom: %d\n", (int)connected); // 1
    }

    printf("so nhom: %zu\n", dsu.components); // 5
    printf("hop trung: %d\n",
           (int)dsu_union(&dsu, 0, 3)); // 0

    return 0;
}
```

**Giải thích kỹ về kết quả `false` của `dsu_union`:** hàm tối giản trên trả `false` cả khi **chỉ số sai** lẫn khi **hai phần tử đã cùng nhóm**. Đây là một lựa chọn giao diện đơn giản để minh họa mảng cha; ở API sản xuất, nên tách mã lỗi khỏi trạng thái “không gộp thêm” để người gọi không hiểu sai.

Tương tự, hàm `find_root` là hàm nội bộ, không kiểm tra chỉ số và con trỏ vì đã có điều kiện tiền đề. Khi xuất nó thành API công khai, cần báo lỗi rõ ràng nếu `x` sai hoặc đối tượng `DSU` không hợp lệ.

### Cài đặt C có khác Python về độ phức tạp?

Không khác về bậc trong mô hình RAM:

- Khởi tạo: `O(n)`.
- Một lần `find`: `O(h)` với chiều cao hiện tại.
- Một lần `union`: hai `find` cộng một phép gán cha; `O(h)`.
- Bộ nhớ: `O(n)`.

C có thể có hằng số nhỏ hơn vì lưu mảng số nguyên liên tiếp, nhưng điều đó **không** thay đổi Big-O và cũng không bảo đảm mọi môi trường/kiểu dữ liệu đều chạy nhanh hơn Python ở mọi kích thước. Khi hiệu năng quan trọng, cần benchmark theo workload.

## 11. Cài đặt C++ với `std::vector` và kiểm tra biên

Nếu số phần tử `n` chỉ biết tại thời điểm chạy, có thể dùng `std::vector<std::size_t>` thay vì mảng C với `N` cố định. Ví dụ C++17:

```cpp
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class DSU {
public:
    explicit DSU(std::size_t n)
        : parent_(n), components_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) const {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }
        while (parent_[x] != x) {
            x = parent_[x];
        }
        return x;
    }

    bool unite(std::size_t x, std::size_t y) {
        const auto rx = find(x);
        const auto ry = find(y);
        if (rx == ry) return false;

        parent_[ry] = rx;
        --components_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) const {
        return find(x) == find(y);
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    std::vector<std::size_t> parent_;
    std::size_t components_;
};

int main() {
    DSU dsu(5);
    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(1, 2);

    std::cout << dsu.same(0, 3) << '\n';   // 1
    std::cout << dsu.same(0, 4) << '\n';   // 0
    std::cout << dsu.component_count() << '\n'; // 2
}
```

Điểm khác biệt so với Python:

- `std::size_t` là kiểu không dấu nên không nhận chỉ số âm như một số nguyên âm hợp lệ; nếu một giá trị âm bị chuyển sang `size_t`, nó thành một số không dấu lớn và thường bị kiểm tra biên từ chối.
- `find` được khai báo `const` vì bản cơ bản **không sửa** mảng cha. Khi bổ sung path compression, hàm cần được thiết kế lại theo chính sách khả biến và an toàn đồng thời của lớp.
- `parent_` là trạng thái `private`, hạn chế mã ngoài tự tạo vòng cha.
- Số nhóm vẫn được quản lý riêng và chỉ giảm khi hai gốc khác nhau.

**Không nên** đánh đồng việc dùng `std::vector` với việc hỗ trợ đăng ký động phần tử mới. Ví dụ này khởi tạo một miền cố định `0..n-1`; nếu muốn thêm phần tử, phải bổ sung API `add_element()` đồng bộ cả `parent_` và `components_`.

## 12. Phân tích hình dạng cây và trường hợp xấu nhất

Vì `union` cơ bản chỉ gắn gốc thứ hai dưới gốc thứ nhất **không xét kích thước**, cách gọi có thể tạo cây rất sâu.

### Trường hợp thuận lợi: cây hình sao

Với `n=6`:

```text
union(0,1)
union(0,2)
union(0,3)
union(0,4)
union(0,5)

Kết quả:

      0
   / /|\ \
  1 2 3 4 5

parent = [0,0,0,0,0,0]
```

Mọi phần tử có khoảng cách tới gốc không quá 1. `find` rất nhanh dù không nén đường đi.

### Trường hợp bất lợi: cây dạng chuỗi

Xét chuỗi sau trên 6 phần tử:

```text
union(1,0)
union(2,1)
union(3,2)
union(4,3)
union(5,4)

Kết quả:
0 → 1 → 2 → 3 → 4 → 5
                        ^ gốc

parent = [1,2,3,4,5,5]
```

Truy vấn `find(0)` đi qua **5 cạnh**. Với `n` phần tử được ghép theo cách tương tự, độ dài đường có thể là `n-1`:

\[
T_{\mathrm{find}}=\Theta(n)\quad\text{ở trường hợp xấu}.
\]

Nếu có `m` truy vấn find trên các nút ở đáy của một cây dài như vậy, tổng thời gian có thể lên tới **`O(mn)`**, ngoài chi phí khởi tạo và các phép hợp đã thực hiện. Đây là nhược điểm quan trọng của bản cài đặt cơ bản.

### Tại sao đường dài không làm sai kết quả?

Cây dài vẫn thỏa bất biến rừng: mọi nút có đường đi tới một gốc, không có chu trình cha. Vấn đề là **hiệu năng**, không phải tính đúng đắn logic. Hai rừng khác hình dạng có thể mã hóa cùng một phân hoạch.

## 13. So sánh với mảng nhãn nhóm (quick-find)

Một cách khác là lưu:

```text
group[x] = nhãn nhóm chứa x
```

Khi đó truy vấn cùng nhóm chỉ cần so sánh hai ô `group`:

```text
same(x, y) = (group[x] == group[y])
```

Thời gian là **`O(1)`**. Nhưng khi `union(x,y)`, phải đổi **toàn bộ nhãn** của các phần tử thuộc nhóm cũ. Cách đơn giản nhất quét toàn mảng `n` phần tử, nên một lần hợp có thể **`O(n)`**.

DSU dạng **quick-union bằng mảng cha** đảo đánh đổi:

| Biểu diễn | `find/same` | `union` | Điểm cần lưu ý |
|---|---|---|---|
| Mảng nhãn `group`, cập nhật bằng quét toàn miền | `O(1)` | `O(n)` | Nhiều lần hợp có thể tốn công quét |
| Mảng cha cơ bản, không tối ưu | `O(h)`, xấu nhất `O(n)` | `O(h)` | Không phải cập nhật mọi thành viên khi hợp |
| Mảng cha + union by size | `O(log n)` xấu nhất | `O(log n)` | Cần thêm `size[root]` |
| Mảng cha + union by size + path compression | Gần `O(α(n))` khấu hao | Gần `O(α(n))` khấu hao | Khấu hao tính trên chuỗi thao tác |

Bảng giả định `n` phần tử đã có và truy cập mảng trực tiếp `O(1)`. `h` là chiều cao cây. Với mã cơ bản, một phép `union` cần hai lần tìm gốc, sau đó mới gắn cha.

**Không có cấu trúc tốt nhất cho mọi kịch bản.** Nếu chỉ có ít phần tử và rất ít lần hợp, mảng nhãn dễ giải thích có thể đủ. Khi số lượng hợp/truy vấn lớn, DSU có tối ưu chuẩn thường phù hợp hơn.

## 14. Nâng cấp 1 — Hợp theo kích thước `union by size`

Để hạn chế cây dạng chuỗi, thêm một mảng `size`:

```text
size[root] = số thành viên của nhóm có đại diện root
```

Ban đầu mọi `size[x]=1`. Khi `union` hai gốc khác nhau, giữ gốc của nhóm lớn hơn và gắn gốc nhỏ hơn dưới nó:

```text
union_by_size(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if size[rx] < size[ry]:
        swap(rx, ry)

    parent[ry] = rx
    size[rx] += size[ry]
    components -= 1
    return true
```

Ví dụ:

```text
Nhóm A: {0,1,2,3}, gốc 0, size[0]=4
Nhóm B: {4,5},     gốc 4, size[4]=2

union_by_size(3,5):
  rx=0, ry=4
  parent[4] = 0
  size[0] = 6
```

**Bất biến metadata:** chỉ được tin `size[r]` khi `r` là **gốc hiện tại**. Các phần tử không phải gốc có thể giữ giá trị `size` cũ. Muốn hỏi kích thước nhóm chứa x, dùng:

```text
component_size(x) = size[find(x)]
```

### Vì sao chiều cao được chặn bởi `O(log n)`?

Mỗi lần độ sâu của một nút tăng vì cây chứa nó bị gắn dưới cây khác, cây ấy phải là cây nhỏ hơn hoặc bằng. Nhóm mới chứa nút có kích thước ít nhất **gấp đôi** nhóm trước đó. Sau `t` lần tăng độ sâu, nhóm chứa nút có ít nhất `2^t` phần tử. Vì tổng số phần tử không vượt `n`, suy ra `t ≤ log₂ n`.

Vậy union by size **không cần** nén đường đi vẫn bảo đảm chiều cao `O(log n)` và `find/union` có chặn xấu nhất `O(log n)`.

## 15. Nâng cấp 2 — Nén đường đi `path compression`

Bản `find` cơ bản chỉ đọc `parent`. **Path compression** cập nhật những nút đã đi qua để chúng trỏ **trực tiếp tới gốc**, giúp các lần tìm sau ngắn hơn.

Ví dụ:

```text
Trước find(0):

0 → 1 → 2 → 3 → 4 (root)

Sau find(0) với full compression:

0 ─┐
1 ─┤
2 ─┼→ 4 (root)
3 ─┘
```

Giả mã đệ quy:

```text
find_compressed(x):
    if parent[x] != x:
        parent[x] = find_compressed(parent[x])
    return parent[x]
```

Giả mã lặp hai lượt tránh phụ thuộc vào độ sâu đệ quy:

```text
find_compressed_iterative(x):
    root = x
    while parent[root] != root:
        root = parent[root]

    while parent[x] != x:
        next_x = parent[x]
        parent[x] = root
        x = next_x

    return root
```

Lượt đầu xác định gốc. Lượt sau **lưu cha cũ trước khi cập nhật**, rồi đặt cha của mỗi nút trên đường thành gốc.

### Nén đường đi có thay đổi nhóm không?

Không. Mỗi nút được nén vẫn trỏ tới **gốc vốn đã thuộc cùng cây**, nên phân hoạch không đổi. Số nhóm và kích thước các nhóm cũng không đổi.

**Nhưng `find` có nén không còn là hàm chỉ đọc.** Nếu nhiều luồng cùng thao tác trên một DSU, mọi hàm có thể ghi `parent` cần một cơ chế đồng bộ phù hợp; không được mặc định thread-safe.

### Độ phức tạp khi dùng cả hai nâng cấp

Với **union by size/rank** kết hợp **path compression**, một chuỗi `m` thao tác tìm/hợp có chi phí rất nhỏ theo **khấu hao**, thường viết khoảng `O(α(n))` cho mỗi thao tác trong cách trình bày phổ biến, với `α` là **hàm Ackermann ngược** tăng cực kỳ chậm.

Phát biểu cần hiểu đúng:

- Đây là **chặn khấu hao cho chuỗi thao tác**, không bảo đảm mọi lời gọi `find` riêng lẻ mất đúng `O(1)` trong trường hợp xấu.
- Chi phí tổng đầy đủ còn gồm `O(n)` khởi tạo và có thể được phát biểu theo cả `n`, `m`.
- Nếu chỉ dùng union by size mà chưa nén đường đi, ta đã có chặn `O(log n)` xấu nhất.

Bài 004 giữ mã minh họa chính ở **phiên bản cơ bản**, còn hai nâng cấp ở đây cho thấy cách phát triển tiếp mà không thay đổi ngữ nghĩa của `find` và `union`.

## 16. Cách kiểm tra tính đúng đắn của mảng cha

Một bộ kiểm tra có thể dựng lại phân hoạch bằng cách gọi `find` cho từng phần tử và nhóm các phần tử theo gốc.

```python
def check_partition(dsu: ParentArrayDSU) -> None:
    n = len(dsu.parent)

    # Cha của từng phần tử phải nằm trong miền.
    assert all(0 <= p < n for p in dsu.parent)

    groups = {}
    for i in range(n):
        root = dsu.find(i)
        assert dsu.parent[root] == root
        groups.setdefault(root, []).append(i)

    # Số gốc đúng bằng số nhóm đã đếm.
    roots = [i for i, p in enumerate(dsu.parent) if i == p]
    assert len(roots) == len(groups) == dsu.component_count()
    assert sum(len(members) for members in groups.values()) == n


check = ParentArrayDSU(6)
check.union(0, 1)
check.union(2, 3)
check.union(1, 2)
check_partition(check)
```

**Giới hạn của phép kiểm tra này:** nó **giả định mảng cha đã là rừng có đường đi kết thúc**, vì `find` thông thường sẽ lặp mãi nếu có chu trình sai. Khi kiểm tra dữ liệu bên ngoài có thể bị hỏng, cần trước hết dùng một trình phát hiện chu trình riêng hoặc giới hạn số bước để không bị kẹt.

### Đếm và kiểm tra chu trình an toàn khi dữ liệu có thể hỏng

Đối với từng nút x, có thể:

1. Đi theo các con trỏ cha.
2. Đưa từng nút đang xét vào một tập `seen`.
3. Nếu tới nút `r` với `parent[r]=r`, đường hợp lệ.
4. Nếu gặp lại một nút **chưa phải gốc** đã nằm trong `seen`, có chu trình không hợp lệ.
5. Nếu cha nằm ngoài miền, dữ liệu không hợp lệ.

Một bộ kiểm tra toàn rừng hiệu quả hơn có thể dùng trạng thái đánh dấu cho từng nút để tránh duyệt lại đường nhiều lần. Tuy nhiên, **không cần** chạy trình kiểm tra toàn `O(n)` sau mỗi phép `union` nếu chỉ thay đổi cấu trúc qua các hàm đã được chứng minh duy trì bất biến.

## 17. Dùng DSU mảng cha trong bài toán đồ thị

Với đồ thị **vô hướng**, hai đỉnh cùng thành phần liên thông khi tồn tại một đường đi giữa chúng.

Ta có thể khởi tạo mỗi đỉnh thành nhóm riêng rồi gọi `union(u,v)` với từng cạnh được thêm:

```text
for each vertex v:
    make-set(v)

for each undirected edge (u, v) added:
    union(u, v)

connected(u, v):
    return find(u) == find(v)
```

Ví dụ:

```text
Đỉnh:       0 1 2 3 4 5
Cạnh mới:   (0,1), (2,3), (1,2)

Sau khi hợp:
{0,1,2,3}, {4}, {5}
```

### Phát hiện chu trình khi xây rừng cạnh

Nếu đang chọn các cạnh để xây **rừng không chu trình**:

- `find(u) != find(v)`: cạnh nối hai cây khác nhau; có thể thêm cạnh rồi `union(u,v)`.
- `find(u) == find(v)`: đã tồn tại đường đi giữa u và v trong rừng; thêm cạnh sẽ tạo chu trình.

Đây là thành phần DSU trong **Kruskal**, thuật toán tìm cây khung nhỏ nhất. Kruskal còn phải sắp xếp các cạnh theo trọng số, vì thế tổng thời gian không chỉ là chi phí `find/union`.

### DSU không tự giải bài toán nào?

- **Tìm đường đi cụ thể:** cần đồ thị và BFS/DFS hoặc thuật toán đường đi phù hợp.
- **Xóa cạnh hoặc tách nhóm:** DSU chuẩn không có `split`.
- **Đồ thị có hướng:** “có đường đi có hướng từ u đến v” không phải quan hệ tương đương đối xứng; không dùng DSU đơn giản để thay thế bài toán đường đi có hướng.
- **Tập nhóm chồng lấn:** không phù hợp với phân hoạch mỗi phần tử thuộc đúng một nhóm.

Một ứng dụng có thể dùng **danh sách kề** để lưu các cạnh, **queue/stack** cho BFS/DFS, và **mảng `parent` DSU** cho các truy vấn liên thông khi thêm cạnh. Đó là cách kết hợp các cấu trúc dữ liệu theo đúng vai trò.

## 18. Những lỗi rất thường gặp khi viết DSU lần đầu

| Lỗi | Biểu hiện | Cách phòng tránh |
|---|---|---|
| Không khởi tạo `parent[i]=i` | `find` có thể chạy sai hoặc vô hạn | Khởi tạo mọi nhóm đơn trước khi truy vấn |
| Trả `parent[x]` thay vì đi tới gốc | Nhầm cha trực tiếp với đại diện | `find` phải lặp tới nút tự trỏ |
| Trong `union` đặt `parent[y]=x` | Có thể làm vỡ nhóm cũ của y | Nối **hai gốc** `find(x)`, `find(y)` |
| Không kiểm tra hai gốc bằng nhau | Giảm nhầm số nhóm hoặc tạo vòng cha | Nếu cùng gốc, trả `false`/no-op |
| Giảm `components` ở mọi lần gọi union | Tổng số nhóm sai | Chỉ giảm khi hai gốc khác nhau |
| Cho chỉ số âm đi vào list Python | Truy cập phần tử cuối ngoài ý muốn | Kiểm tra `0 ≤ x < n` |
| Giả định `find` luôn `O(1)` | Bỏ qua cây dạng chuỗi | Phân tích theo chiều cao `h` |
| Thêm path compression nhưng vẫn coi `find` chỉ đọc | Rủi ro đồng thời và bất biến API | Thiết kế tính khả biến rõ ràng |
| Dùng `parent[x]` làm ID nhóm bền vững | Root có thể thay đổi sau union | Tách ID nghiệp vụ khỏi root |
| Xóa cạnh mà không cập nhật DSU | Kết quả liên thông có thể sai | Dựng lại hoặc dùng dynamic connectivity |
| Gọi `component_size` mà không lưu size hay quét | Không có số thành viên trong parent đơn thuần | Thêm `size[root]` hoặc quét toàn miền |
| Lưu con trỏ/địa chỉ tới một phần tử của mảng động sau khi mở rộng | Có thể bị vô hiệu hóa bởi cấp phát lại | Dùng chỉ số ổn định và API quản lý dung lượng |

### Lỗi về kỳ vọng cấu trúc dữ liệu

Một mảng cha có dạng:

```text
parent = [0,0,0,2]
```

và mảng cha khác:

```text
parent = [0,0,0,0]
```

đều có thể là kết quả **đúng**, vì mọi phần tử vẫn có gốc 0. Khi kiểm thử một thuật toán có union by rank/size hoặc path compression, nên kiểm tra **phân hoạch và kết quả truy vấn**, không nhất thiết ép mọi byte mảng cha trùng khớp một hình dạng duy nhất.

Riêng lớp `ParentArrayDSU` đơn giản trong bài **có quy tắc nối xác định**, nên việc đối chiếu mảng cha trong ví dụ là hữu ích để hiểu các bước; không nên biến nó thành yêu cầu chung cho mọi DSU.

## 19. Các tình huống biên cần thử nghiệm

### Dãy rỗng (`n=0`)

```python
empty = ParentArrayDSU(0)
assert empty.parent == []
assert empty.component_count() == 0
```

Không có phần tử để gọi `find` hoặc `union`. Một lời gọi `find(0)` phải báo `IndexError`, không đọc phần tử ngoài mảng.

### Một phần tử (`n=1`)

```python
one = ParentArrayDSU(1)
assert one.find(0) == 0
assert one.same(0, 0) is True
assert one.union(0, 0) is False
assert one.component_count() == 1
```

### Hợp trùng nhiều lần

```python
a = ParentArrayDSU(3)
assert a.union(0, 1) is True
assert a.union(0, 1) is False
assert a.union(1, 0) is False
assert a.component_count() == 2
```

### Chỉ số ngoài phạm vi

```python
a = ParentArrayDSU(2)

try:
    a.find(-1)
except IndexError:
    print("Chặn chỉ số âm")

try:
    a.union(0, 2)
except IndexError:
    print("Chặn chỉ số quá lớn")
```

Trong C và C++, một bản cài đặt cần kiểm tra tương đương để tránh truy cập ngoài vùng nhớ. Với các API dùng số nguyên không dấu, giá trị âm chuyển kiểu có thể thành số rất lớn; kiểm tra `x >= n` vẫn rất quan trọng.

### Nhiều truy vấn trên cây dài

```python
n = 10
long_chain = ParentArrayDSU(n)
for i in range(1, n):
    long_chain.union(i, i - 1)

assert long_chain.parent == [1,2,3,4,5,6,7,8,9,9]
assert long_chain.find(0) == 9
assert long_chain.component_count() == 1
```

Trường hợp này vừa cho thấy **cài đặt cơ bản trả kết quả đúng**, vừa phơi bày lý do cần nâng cấp hiệu năng bằng union by size hoặc path compression.

## 20. Bảng quyết định khi thiết kế API

| Câu hỏi | Nếu trả lời “có” | Hướng thiết kế |
|---|---|---|
| ID liên tục và biết trước `0..n-1`? | Có | Dùng mảng cha trực tiếp |
| Nhiều `union/find` trên miền lớn? | Có | Nâng cấp union by size/rank và path compression |
| Cần số nhóm liên tục? | Có | Duy trì `components` với điều kiện cập nhật đúng |
| Cần số thành viên mỗi nhóm? | Có | Duy trì `size[root]` hoặc quét khi truy vấn hiếm |
| Cần ID kiểu chuỗi/số cực lớn? | Có | Remapping hoặc DSU dựa vào bảng băm |
| Cần liệt kê mọi thành viên của nhóm liên tục? | Có | Thêm chỉ mục thành viên; `parent` đơn thuần chưa đủ |
| Cần xoá/tách nhóm? | Có | Chọn thuật toán dynamic connectivity/rollback phù hợp |
| Cần ID nhóm bền vững? | Có | Lưu metadata định danh tách biệt với root |
| Có nhiều luồng cùng thay đổi cấu trúc? | Có | Đồng bộ hoặc concurrent DSU chuyên dụng |

Mảng cha là biểu diễn **đơn giản và có chi phí bộ nhớ `O(n)`** khi các phần tử có thể đánh số liên tục. Nhưng lựa chọn chiến lược hợp, kiểu ID và API phụ phải theo đúng **thao tác chủ đạo** của bài toán.

## 21. Bài tập tự kiểm tra có lời giải

**Câu 1.** Với `n=5`, mảng `parent` ngay sau khởi tạo là gì? Có bao nhiêu nhóm?

**Đáp án:** `parent=[0,1,2,3,4]` và có 5 nhóm đơn.

**Câu 2.** Cho `parent=[0,0,0,2,4,4,6,7]`. Hãy xác định `find(3)` và `find(5)`.

**Đáp án:** `find(3)=0` theo đường `3→2→0`; `find(5)=4` theo đường `5→4`.

**Câu 3.** Tại sao không thể kiểm tra cùng nhóm bằng `parent[x] == parent[y]` trong mọi trường hợp?

**Đáp án:** Hai phần tử có thể ở các nhánh khác nhau và có **cha trực tiếp khác nhau** dù cùng gốc. Phải so sánh `find(x) == find(y)`.

**Câu 4.** Hai nhóm có gốc 0 và 2, với `parent=[0,0,2,2]`. Sau `union(1,3)` theo quy tắc cơ bản, mảng cha là gì?

**Đáp án:** `find(1)=0`, `find(3)=2`, nên gán `parent[2]=0`. Kết quả `[0,0,0,2]`; số nhóm giảm từ 2 xuống 1.

**Câu 5.** Vì sao gán trực tiếp `parent[3]=1` ở câu 4 không phải phép hợp đúng?

**Đáp án:** Chỉ nút 3 được chuyển sang cây của 1; nút 2 vẫn là gốc riêng. Ta đã tách nhóm `{2,3}` thay vì hợp toàn nhóm.

**Câu 6.** Ban đầu có 8 nhóm. Sau 6 phép `union` đều nối hai gốc khác nhau, còn mấy nhóm?

**Đáp án:** `8−6=2` nhóm.

**Câu 7.** Sau `union(0,1)`, gọi lại `union(1,0)` có phải giảm số nhóm lần nữa không?

**Đáp án:** Không. Hai phần tử đã có cùng gốc, nên hàm trả `false` và số nhóm giữ nguyên.

**Câu 8.** Trong mảng cha `[1,2,3,4,5,5]`, `find(0)` đi qua bao nhiêu cạnh?

**Đáp án:** Năm cạnh `0→1→2→3→4→5`. Trên chuỗi `n` nút, thời gian tìm gốc có thể là `Θ(n)`.

**Câu 9.** Tại sao `union by size` giúp hạn chế chiều cao cây?

**Đáp án:** Mỗi khi cây chứa một nút bị nối dưới cây khác, kích thước nhóm mới ít nhất gấp đôi. Độ sâu không tăng quá `O(log n)` lần theo lập luận gấp đôi kích thước.

**Câu 10.** `find` có path compression có thay đổi phân hoạch không?

**Đáp án:** Không. Nó chỉ cho các nút trỏ ngắn hơn tới **gốc cũ trong cùng cây**, không làm thay đổi thành viên nhóm.

**Câu 11.** Nếu cần `component_size(x)` nhưng chỉ lưu `parent` và `components`, làm sao biết kích thước nhóm?

**Đáp án:** Có thể quét mọi phần tử i và đếm những i có `find(i) == find(x)`. Nếu cần trả lời thường xuyên, nên lưu thêm `size[root]` và cập nhật khi hợp.

**Câu 12.** Với hai cây cha `{0,1}` và `{2,3}`, vì sao nối hai **gốc khác nhau** không tạo chu trình?

**Đáp án:** Trước khi nối, các cây rời nhau nên không có đường cha từ gốc này tới gốc kia. Gắn một gốc dưới gốc còn lại tạo một cây chung và không có đường quay lại gốc cũ.

**Câu 13.** DSU có thể dùng trực tiếp để tìm đường đi cụ thể giữa hai đỉnh liên thông không?

**Đáp án:** Không. Mảng cha mô tả quan hệ đại diện, không nhất thiết là các cạnh đồ thị. Cần lưu đồ thị và dùng BFS/DFS hoặc thuật toán đường đi phù hợp.

**Câu 14.** Nếu trong Python không kiểm tra chỉ số âm, `find(-1)` có thể sai ở đâu?

**Đáp án:** Python cho phép chỉ số `-1` để truy cập phần tử cuối của list. Nó sẽ bị hiểu nhầm thành một phần tử hợp lệ khác, gây kết quả sai ý nghĩa. Phải kiểm tra `0 ≤ x < n`.

**Câu 15.** Một DSU có 100.000 phần tử và thường xuyên hợp nhóm. Nên dùng cài đặt cơ bản không tối ưu mãi hay nâng cấp?

**Đáp án:** Nên xem xét union by size/rank và path compression. Bản cơ bản có thể tạo đường cha dài, khiến `find` xấu nhất `O(n)`; hai tối ưu đem lại chi phí gần hằng số **khấu hao** trên chuỗi thao tác.

**Câu 16.** Một lần `find` với path compression đã đưa mọi nút trên đường về gốc. Có thể nói nó luôn `O(1)` trong trường hợp xấu ngay từ lần gọi đầu tiên không?

**Đáp án:** Không. Lần gọi đầu vẫn phải **đi tới gốc**, có thể qua nhiều cạnh; cải thiện đến từ những lần truy vấn sau và phân tích khấu hao toàn chuỗi.

## Ghi nhớ

- **Mảng cha** lưu `parent[x]` cho mỗi phần tử. Một gốc thỏa `parent[root]=root`; các đường cha tạo một **rừng cây** biểu diễn phân hoạch các nhóm không giao nhau.
- **Khởi tạo:** `parent[i]=i` cho mọi i, tốn `O(n)` thời gian và `O(n)` bộ nhớ.
- **`find(x)`:** đi theo cha tới gốc. **`union(x,y)`:** tìm hai gốc và nối **gốc với gốc** nếu khác nhau; một phép hợp thành công giảm số nhóm đúng 1.
- **`same(x,y)`:** so sánh `find(x)` và `find(y)`, không so sánh hai cha trực tiếp. Mảng `parent` cơ bản không lưu sẵn danh sách thành viên hoặc kích thước nhóm.
- **Cài đặt cơ bản** có chi phí `O(h)` cho `find` và `union`, với `h` là chiều cao cây; trường hợp xấu `h=Θ(n)`. **Union by size** và **path compression** cải thiện hiệu năng nhưng vẫn giữ nguyên ngữ nghĩa phân hoạch.
- Khi triển khai, luôn **kiểm tra chỉ số, bảo vệ bất biến rừng, xử lý hợp trùng và phân biệt root kỹ thuật với ID nhóm nghiệp vụ**. DSU phù hợp với gộp dần và truy vấn liên thông, không trực tiếp hỗ trợ tách nhóm, xóa cạnh hay trả đường đi cụ thể.
