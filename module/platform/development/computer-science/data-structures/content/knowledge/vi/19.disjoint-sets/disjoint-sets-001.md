# Bài toán quản lý các nhóm không giao nhau

Một ứng dụng có tám người, ban đầu mỗi người thuộc một nhóm riêng. Khi hai người được xác nhận có liên hệ, ứng dụng **gộp hai nhóm** chứa họ. Sau một loạt lần gộp, ứng dụng cần trả lời nhanh: “Người 0 và người 3 có cùng nhóm không?”, “Hiện còn bao nhiêu nhóm?” và “Nhóm chứa người 6 có bao nhiêu thành viên?”.

Bài toán xuất hiện ở nhiều nơi: theo dõi các thành phần liên thông của mạng khi thêm cạnh, gom những tài khoản được xác định là cùng chủ sở hữu, quản lý cụm phần tử, hoặc phát hiện cạnh tạo chu trình khi xây cây khung nhỏ nhất. Điểm chung là các **nhóm không giao nhau**: tại một thời điểm, mỗi phần tử thuộc đúng một nhóm.

Bài học thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, nơi học viên xây dựng nền tảng cấu trúc dữ liệu, nghiên cứu **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để chọn cấu trúc phù hợp. Ta sẽ mô hình hóa yêu cầu trước, sau đó tìm hiểu cấu trúc **Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, dùng để quản lý các nhóm được hợp nhất dần.

## 1. Từ nhóm thành viên đến phân hoạch của một tập

Gọi tập phần tử đang quản lý là:

\[
U = \{0,1,\ldots,n-1\}.
\]

Tại mọi thời điểm, hệ thống chia `U` thành các tập con không rỗng:

\[
P = \{G_1,G_2,\ldots,G_c\}.
\]

Để `P` là một **phân hoạch (partition)**, nó phải thỏa ba điều kiện:

1. Mọi nhóm đều không rỗng: `G_j ≠ ∅`.
2. Hai nhóm khác nhau **không có phần tử chung**: với `i ≠ j`, `G_i ∩ G_j = ∅`.
3. Hợp tất cả nhóm bằng toàn bộ miền: `G_1 ∪ \cdots ∪ G_c = U`.

Từ đó suy ra: **mỗi phần tử thuộc đúng một nhóm**. Số nhóm `c` nằm trong khoảng `0 ≤ c ≤ n`; nếu `n > 0` thì `1 ≤ c ≤ n`, còn `n=0` thì `c=0`.

### Minh họa bằng tám phần tử

Ban đầu, tám phần tử thuộc tám nhóm:

```text
U = {0,1,2,3,4,5,6,7}

P0 = {{0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}}
```

Sau khi lần lượt gộp nhóm của `0` với `1`, nhóm của `2` với `3`, rồi nhóm chứa `1` với nhóm chứa `2`:

```text
P1 = {{0,1}, {2,3}, {4}, {5}, {6}, {7}}
P2 = {{0,1,2,3}, {4}, {5}, {6}, {7}}
```

Nếu tiếp tục gộp `5` với `6` rồi `6` với `7`:

```text
P3 = {{0,1,2,3}, {4}, {5,6,7}}
```

Giờ chỉ còn **3 nhóm**. Mặc dù chưa từng gộp trực tiếp `0` với `3`, chúng vẫn cùng nhóm vì chuỗi quan hệ nối các phần tử lại với nhau.

### Vì sao phải “không giao nhau”?

Nếu cho phép một phần tử đồng thời thuộc nhiều nhóm (ví dụ cùng tham gia câu lạc bộ cờ vua và bóng đá), đó là bài toán quan hệ **nhiều-nhiều**, không phải một phân hoạch. DSU không phù hợp để lưu trực tiếp những nhóm có thể chồng lấn như vậy.

DSU mô hình hóa **một phân hoạch duy nhất** của miền tại mỗi thời điểm. Cần xác định ý nghĩa của phép gộp trước khi chọn cấu trúc.

## 2. Nhìn bài toán qua quan hệ tương đương

Có thể định nghĩa quan hệ `x ~ y` với ý nghĩa “`x` và `y` thuộc cùng một nhóm”. Quan hệ này có ba tính chất:

- **Phản xạ:** `x ~ x`.
- **Đối xứng:** nếu `x ~ y` thì `y ~ x`.
- **Bắc cầu:** nếu `x ~ y` và `y ~ z` thì `x ~ z`.

Đây là một **quan hệ tương đương**. Mỗi nhóm trong phân hoạch chính là một lớp tương đương: tập các phần tử tương đương với nhau.

Sự bắc cầu giải thích vì sao một thao tác gộp có thể làm nhiều cặp phần tử trở thành “cùng nhóm” dù chưa có quan hệ trực tiếp:

```text
0 --- 1     2 --- 3

Gộp nhóm chứa 1 với nhóm chứa 2:

0 --- 1 --- 2 --- 3

Cùng nhóm: (0,3), (0,2), (1,3), ...
```

**Phân biệt quan hệ trực tiếp với quan hệ cùng nhóm.** Khi dùng các cạnh vô hướng làm dữ liệu, “`x` nối trực tiếp với `y`” là quan hệ có cạnh giữa hai đỉnh; “`x` và `y` cùng thành phần liên thông” là quan hệ tồn tại một đường đi. DSU quản lý quan hệ thứ hai, tức **bao đóng bắc cầu** của các liên kết được thêm.

### Khi nào không được dùng tính bắc cầu?

Nếu `A` theo dõi `B` trên mạng xã hội, quan hệ “theo dõi” không nhất thiết đối xứng hoặc bắc cầu. Chỉ vì `A` theo dõi `B` và `B` theo dõi `C`, không thể kết luận `A` theo dõi `C`. Không nên dùng DSU để biến quan hệ có hướng này thành các nhóm tương đương, trừ khi bài toán cố ý lấy **liên thông vô hướng** của một mạng đã chuyển đổi.

## 3. Những thao tác mà hệ thống thực sự cần

Bài toán quản lý các nhóm rời nhau thường xuất hiện dưới dạng một chuỗi thao tác:

| Thao tác | Ý nghĩa | Ví dụ |
|---|---|---|
| `make_set(x)` | Tạo nhóm riêng cho phần tử mới `x`, nếu hệ thống hỗ trợ thêm động | Thêm người dùng mới |
| `find(x)` | Trả về **đại diện** của nhóm chứa `x` | Xác định nhóm của người 3 |
| `union(x,y)` | Hợp **hai nhóm chứa** `x` và `y` | Xác nhận hai nhóm có liên hệ |
| `same(x,y)` / `connected(x,y)` | Kiểm tra `x` và `y` có cùng nhóm không | “0 và 3 đã liên thông?” |
| `component_size(x)` | Số phần tử trong nhóm chứa `x` | “Nhóm của 6 có bao nhiêu người?” |
| `component_count()` | Tổng số nhóm hiện tại | “Còn mấy cụm độc lập?” |

Không phải mọi triển khai DSU đều cung cấp `component_size` hoặc `component_count`; hai thao tác này có thể được bổ sung bằng metadata rất nhỏ nếu cần.

**Thao tác quan trọng nhất là gộp cả nhóm chứ không chỉ ghi một cặp liên hệ.** Nếu `0` cùng nhóm `1` và `2` cùng nhóm `3`, lời gọi `union(1,2)` phải làm cho cả bốn phần tử thuộc **một nhóm**.

### Đặc điểm của mô hình gộp dần

Trong phiên bản DSU kinh điển:

- Ban đầu mỗi phần tử thuộc nhóm riêng, hoặc các nhóm ban đầu đã được xác định.
- Các nhóm chỉ có thể **hợp nhất**.
- Một phép hợp thành công giảm số nhóm đi đúng 1.
- Nếu hai phần tử đã cùng nhóm, gọi `union` thêm lần nữa **không đổi phân hoạch**.

Đây là mô hình **monotone**: khi hai phần tử đã thuộc cùng nhóm, chúng tiếp tục cùng nhóm cho tới hết quá trình nếu không có thao tác tách.

Không nên nhầm phép `union(x,y)` với phép hợp hai tập tạo bản sao mới trong đại số tập hợp: ở đây thao tác **thay đổi trạng thái phân hoạch** đang được quản lý.

## 4. Mô phỏng một loạt truy vấn

Với miền `U={0,1,2,3,4,5,6,7}`, xét chuỗi thao tác:

| Bước | Thao tác | Kết quả hoặc số nhóm |
|---:|---|---|
| 0 | Khởi tạo 8 phần tử | `c = 8` |
| 1 | `union(0,1)` | `c = 7` |
| 2 | `union(2,3)` | `c = 6` |
| 3 | `same(0,3)` | `false` |
| 4 | `union(1,2)` | `c = 5` |
| 5 | `same(0,3)` | `true` |
| 6 | `union(0,3)` | Không đổi; `c = 5` |
| 7 | `union(5,6)` | `c = 4` |
| 8 | `union(6,7)` | `c = 3` |
| 9 | `component_size(6)` | `3` |
| 10 | `same(4,7)` | `false` |

Trạng thái cuối:

```text
Nhóm A: {0,1,2,3}
Nhóm B: {4}
Nhóm C: {5,6,7}

Số nhóm = 3
Kích thước nhóm chứa 0 = 4
Kích thước nhóm chứa 4 = 1
Kích thước nhóm chứa 6 = 3
```

Điểm dễ sai: `union(0,3)` ở bước 6 không được giảm số nhóm từ 5 xuống 4, vì `0` và `3` **đã** cùng nhóm. Điều kiện này phải được kiểm tra trong bất kỳ hiện thực nào.

## 5. Có thể quản lý nhóm bằng mảng nhãn không?

Trước khi học DSU, ta thử một biểu diễn đơn giản: với mỗi phần tử `x`, lưu `group[x]` là mã nhóm.

Ban đầu:

```text
x:        0  1  2  3  4  5  6  7
group[x]: 0  1  2  3  4  5  6  7
```

Sau khi hợp `0` và `1`, gán nhãn của nhóm `1` thành nhãn `0`:

```text
x:        0  1  2  3  4  5  6  7
group[x]: 0  0  2  3  4  5  6  7
```

Để gộp hai nhóm theo cách đơn giản nhất, ta quét toàn mảng và thay **mọi nhãn** của nhóm cũ bằng nhãn mới.

```text
union(x, y):
    old = group[y]
    new = group[x]

    if old == new:
        return false

    for every element i:
        if group[i] == old:
            group[i] = new

    return true
```

### Ưu điểm

- Kiểm tra `same(x,y)` chỉ cần so sánh `group[x] == group[y]`: **`O(1)`**.
- Tìm mã nhóm trực tiếp: **`O(1)`**.
- Dữ liệu dễ quan sát; mảng nhãn chứa đúng một giá trị cho mỗi phần tử.

### Nhược điểm

- Mỗi lần hợp nhóm có thể phải quét đủ `n` phần tử: **`O(n)`**, kể cả khi chỉ có ít phần tử phải đổi nhãn.
- Nếu có gần `n` lần hợp thành công, tổng công quét có thể **`O(n²)`**.
- Khi liên tục cập nhật quan hệ và hỏi cùng nhóm, chi phí cập nhật trở thành điểm nghẽn.

Đối với một tập rất nhỏ hoặc hiếm khi gộp, mảng nhãn vẫn có thể là lựa chọn hợp lý. Nhưng nếu có hàng trăm nghìn hoặc hàng triệu lần hợp nhóm, ta cần tổ chức thông tin nhóm theo cách tránh cập nhật mọi phần tử sau mỗi lần hợp.

### Có cải tiến bằng cách di chuyển nhóm nhỏ không?

Có. Nếu mỗi nhóm lưu danh sách thành viên và mỗi phần tử biết đại diện hiện tại, khi hợp nhóm ta có thể **di chuyển các thành viên của nhóm nhỏ sang nhóm lớn**, chỉ cập nhật nhãn của nhóm nhỏ.

Một phần tử chỉ bị chuyển từ nhóm nhỏ sang nhóm lớn một số lần có giới hạn \(O(\log n)\), vì sau mỗi lần chuyển, kích thước nhóm chứa nó ít nhất gấp đôi. Nhờ vậy tổng số lần cập nhật nhãn qua các phép hợp có thể là \(O(n\log n)\) trong mô hình thích hợp.

Tuy nhiên, cần duy trì danh sách thành viên và metadata nhóm. Một hướng phổ biến và đơn giản hơn cho truy vấn “cùng nhóm” là **rừng các cây đại diện**, tức Union–Find.

## 6. Ý tưởng của Disjoint Set Union (Union–Find)

DSU không nhất thiết lưu danh sách thành viên của từng nhóm. Thay vào đó, mỗi phần tử có một **con trỏ cha**:

```text
parent[x] = phần tử cha của x
```

Mỗi nhóm được biểu diễn bằng **một cây có gốc**, và gốc đóng vai trò **đại diện (representative)** của nhóm.

Ví dụ hai nhóm:

```text
Nhóm 1:         Nhóm 2:

    0              5
   / \            / \
  1   2          6   7
      |
      3
```

Dạng mảng cha tương ứng:

```text
parent[0] = 0
parent[1] = 0
parent[2] = 0
parent[3] = 2

parent[5] = 5
parent[6] = 5
parent[7] = 5
```

Gốc có tính chất `parent[root] == root`. Để biết phần tử `x` thuộc nhóm nào, ta lần theo các con trỏ cha tới gốc. Ví dụ `3 → 2 → 0`, nên `find(3) = 0`.

**Đại diện chỉ là một ID kỹ thuật**, không bắt buộc là phần tử nhỏ nhất, phần tử đầu tiên hay một mã nhóm có ý nghĩa nghiệp vụ. Nó có thể thay đổi sau phép hợp. Không nên dùng kết quả `find(x)` như ID bền vững của một tổ chức hoặc khách hàng nếu hệ thống cần ID không đổi.

### Bất biến cốt lõi của rừng DSU

1. Với mọi `x` hợp lệ, `parent[x]` là một phần tử hợp lệ của miền.
2. Mỗi cây có **đúng một gốc** với `parent[root] = root`.
3. Đi theo con trỏ cha từ một nút cuối cùng phải tới gốc; **không có chu trình cha** khác vòng tự trỏ tại gốc.
4. Hai phần tử thuộc **cùng nhóm khi và chỉ khi** chúng có cùng gốc.
5. Các cây khác nhau không chia sẻ nút, nên những tập phần tử tương ứng không giao nhau.
6. Mọi phần tử nằm trong đúng một cây; các cây tạo thành phân hoạch của `U`.

Nhờ biểu diễn này, hợp hai nhóm chỉ cần **nối một gốc vào gốc còn lại** thay vì sửa toàn bộ phần tử của nhóm.

## 7. Ba thao tác nền tảng: MakeSet, Find, Union

### 7.1. MakeSet: tạo nhóm đơn

Khởi tạo `n` phần tử theo cách:

```text
for x in 0..n-1:
    parent[x] = x
    size[x] = 1

componentCount = n
```

Mỗi phần tử là một gốc riêng, tương ứng nhóm đơn `{x}`. Việc khởi tạo có thời gian **`O(n)`** và bộ nhớ **`O(n)`**.

Nếu hệ thống nhận ID rời rạc hoặc ID kiểu chuỗi, có thể dùng ánh xạ `ID → chỉ số 0..n-1` hoặc DSU dựa trên dictionary; không nhất thiết buộc giá trị ID bên ngoài phải là chỉ số mảng.

### 7.2. Find: truy tìm đại diện

Giả mã cơ bản:

```text
find(x):
    while parent[x] != x:
        x = parent[x]
    return x
```

Nếu cây cao `h`, thao tác này mất `O(h)` thời gian. Nếu cấu trúc cây quá dài, `h` có thể gần bằng `n` khi không có quy tắc hợp tốt.

### 7.3. Union: hợp hai nhóm

Gọi đại diện của hai phần tử:

```text
union(x, y):
    rootX = find(x)
    rootY = find(y)

    if rootX == rootY:
        return false  // Đã cùng nhóm; không thay đổi

    parent[rootY] = rootX
    componentCount -= 1
    return true
```

Phần quan trọng là gắn **gốc vào gốc**, không gắn tùy tiện `parent[y] = x` khi `x` hoặc `y` là nút bất kỳ. Gắn sai có thể làm hỏng thông tin nhóm hoặc tạo vòng lặp cha nếu không kiểm tra.

Một phép `union` thành công **gộp hai cây**, giảm số nhóm đúng 1. Nếu hai gốc trùng nhau, không gắn gì và số nhóm giữ nguyên.

### Kiểm tra cùng nhóm

```text
same(x, y):
    return find(x) == find(y)
```

Vì `find` trả về đại diện hiện tại của nhóm, phép kiểm tra này đúng ngay cả khi hai phần tử không liên hệ trực tiếp.

## 8. Cải thiện hiệu năng: hợp theo kích thước và nén đường đi

Một DSU dùng mảng cha mà gộp tùy ý có thể tạo cây rất sâu. Hai tối ưu chuẩn giúp tránh tình trạng đó.

### 8.1. Union by size: gắn cây nhỏ dưới cây lớn

Mỗi gốc `r` lưu `size[r]` là số phần tử thuộc nhóm của nó. Khi hợp hai gốc khác nhau:

1. So sánh `size[rootX]` và `size[rootY]`.
2. Cho gốc của nhóm nhỏ hơn trỏ tới gốc của nhóm lớn hơn.
3. Cộng kích thước nhóm nhỏ vào kích thước tại gốc mới.
4. Giảm `componentCount` đi 1.

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
    componentCount -= 1
    return true
```

**Bất biến metadata:** `size[r]` chỉ được dùng làm kích thước nhóm khi `r` là **gốc hiện tại**. Giá trị `size` ở các nút đã thành con có thể cũ, không được lấy trực tiếp làm kích thước nhóm. Để hỏi kích thước nhóm của `x`, phải dùng `size[find(x)]`.

Với union by size và **chưa** dùng nén đường đi, chiều cao của mọi cây được chặn bởi `O(log n)`: mỗi khi độ sâu của một nút tăng vì cây của nó bị gắn dưới cây khác, nhóm mới chứa nó có kích thước ít nhất **gấp đôi**. Một phần tử không thể trải qua quá `O(log n)` lần tăng độ sâu như vậy.

### 8.2. Path compression: rút ngắn đường tìm gốc

Trong quá trình `find(x)`, ta có thể cập nhật `parent` của các nút đã đi qua để chúng trỏ trực tiếp đến gốc:

```text
Trước find(3):          Sau find(3):

    0                        0
    |                      / | \
    2                     2  3  ...
    |
    3
```

Giả mã đệ quy phổ biến:

```text
find(x):
    if parent[x] != x:
        parent[x] = find(parent[x])
    return parent[x]
```

Nén đường đi không đổi **nhóm logic** của phần tử; nó chỉ thay đổi hình dạng cây bên trong cùng một nhóm. Các lần truy vấn sau thường đi qua ít nút hơn.

Trong ngôn ngữ có giới hạn ngăn xếp đệ quy hoặc nhận dữ liệu cấu trúc đã tồn tại, có thể dùng `find` lặp để tránh tràn ngăn xếp. Ví dụ Python ở phần sau sử dụng phương pháp lặp hai lượt.

### 8.3. Độ phức tạp khi kết hợp cả hai tối ưu

Với union by size (hoặc union by rank) **và** path compression, một chuỗi dài các thao tác `find`/`union` có chi phí **gần như hằng số khấu hao trên mỗi thao tác**. Thường viết là `O(α(n))` khấu hao trong những phát biểu tiêu chuẩn về Union–Find; `α` là hàm Ackermann ngược, tăng cực kỳ chậm.

Cần đọc đúng phát biểu:

- **Khấu hao** là bảo đảm cho **tổng** chi phí của một chuỗi thao tác, không nói mọi lần `find` đều mất `O(1)` trong trường hợp xấu.
- Kết quả lý thuyết chính xác có thể được diễn đạt theo cả số phần tử `n` và số thao tác `m`; ký hiệu `O(α(n))` là dạng đơn giản thường dùng khi mô tả cấu trúc này.
- Trong thực tế đối với các kích thước dữ liệu thông thường, `α(n)` rất nhỏ. Không nên vì thế gọi một phép tìm đơn lẻ là “thời gian hằng số tuyệt đối”.

Nếu chỉ dùng union by size mà không nén đường đi, `find` và `union` có chặn trên **`O(log n)`** trong trường hợp xấu.

## 9. Triển khai Python đầy đủ

Đoạn mã sau xây dựng DSU cho các chỉ số `0..n-1`, hỗ trợ hợp nhóm, kiểm tra cùng nhóm, kích thước nhóm và số nhóm. Mỗi lời gọi có kiểm tra chỉ số. `find` dùng vòng lặp để nén đường đi, không phụ thuộc độ sâu đệ quy.

```python
class DisjointSetUnion:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("Số phần tử phải không âm")

        self.parent = list(range(n))
        self.size = [1] * n
        self.component_count = n

    def _check(self, x: int) -> None:
        if not 0 <= x < len(self.parent):
            raise IndexError("Phần tử ngoài miền quản lý")

    def find(self, x: int) -> int:
        self._check(x)

        # Lượt 1: tìm gốc của nhóm.
        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        # Lượt 2: nén toàn bộ đường đi về gốc.
        while self.parent[x] != x:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x

        return root

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False  # Không hợp thêm lần nữa.

        # Đảm bảo rx là gốc của nhóm lớn hơn hoặc bằng.
        if self.size[rx] < self.size[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        self.component_count -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]

    def groups(self) -> list[list[int]]:
        # Dựng danh sách thành viên khi thực sự cần.
        by_root: dict[int, list[int]] = {}
        for x in range(len(self.parent)):
            root = self.find(x)
            by_root.setdefault(root, []).append(x)
        return list(by_root.values())


dsu = DisjointSetUnion(8)
assert dsu.component_count == 8

assert dsu.union(0, 1) is True
assert dsu.union(2, 3) is True
assert dsu.same(0, 3) is False

assert dsu.union(1, 2) is True
assert dsu.same(0, 3) is True
assert dsu.union(0, 3) is False  # Gộp trùng.

assert dsu.union(5, 6) is True
assert dsu.union(6, 7) is True

assert dsu.component_count == 3
assert dsu.component_size(6) == 3
assert dsu.component_size(4) == 1

print(dsu.groups())  # [[0, 1, 2, 3], [4], [5, 6, 7]]
```

### Vì sao vòng nén đường đi lặp đúng?

Giả sử đường từ `x` tới gốc là `x → p₁ → p₂ → ... → root`. Lượt 1 tìm đúng gốc trước khi thay đổi cấu trúc. Ở lượt 2:

1. Lưu `next_x = parent[x]`.
2. Gán `parent[x] = root`.
3. Chuyển sang `next_x` đã lưu.

Nhờ lưu nút tiếp theo **trước** khi cập nhật, thuật toán không mất đường tới các nút cũ. Mọi nút trên đường vẫn có chung gốc, nên phân hoạch không thay đổi.

### Chi phí của `groups()`

DSU được tối ưu cho **hỏi đại diện và hợp nhóm**, không mặc định duy trì danh sách thành viên. Hàm `groups()` phải duyệt tất cả `n` phần tử và gọi `find`, nên mất khoảng `O(nα(n))` khấu hao theo mô hình chuẩn, cộng công tạo danh sách đầu ra. Bộ nhớ mới cho các danh sách thành viên là `O(n)`.

Nếu ứng dụng thường xuyên cần duyệt toàn bộ thành viên của một nhóm, có thể lưu thêm danh sách thành viên hoặc chọn một cấu trúc khác; điều đó tạo thêm công cập nhật khi hợp nhóm.

## 10. Tại sao DSU luôn giữ được các nhóm không giao nhau?

Ta có thể lập luận bằng **quy nạp theo số phép hợp thành công**.

**Ban đầu:** mỗi phần tử tạo một cây đơn `{x}`; các cây không có nút chung, và hợp tất cả các cây là `U`.

**Giả sử:** trước một phép `union(x,y)`, các cây đang tạo thành phân hoạch.

Xét hai trường hợp:

1. `find(x) == find(y)`: hai phần tử đã ở cùng cây. Thuật toán không thay đổi rừng, nên bất biến phân hoạch tiếp tục đúng.
2. `find(x) != find(y)`: hai gốc thuộc **hai cây khác nhau, không giao nhau**. Gắn gốc cây này làm con của gốc cây kia sẽ hợp **toàn bộ hai tập phần tử** thành một cây. Không phần tử nào bị mất hoặc nhân đôi, các cây còn lại không thay đổi.

Do đó sau mỗi phép hợp, rừng vẫn tương ứng một phân hoạch. Nén đường đi chỉ đổi cạnh cha **bên trong một cây**, không chuyển phần tử sang cây khác; vì vậy nó cũng giữ nguyên phân hoạch.

### Các đại lượng giúp kiểm tra tính đúng đắn

Nếu `component_count = c` và các gốc hiện tại là `r₁,...,r_c`, thì:

\[
\sum_{j=1}^{c}\operatorname{size}[r_j]=n.
\]

Mỗi phần tử xuất hiện trong đúng một nhóm. Mỗi lần hợp hai gốc khác nhau:

\[
c_{\text{sau}} = c_{\text{trước}} - 1,
\]

còn khi hợp hai phần tử đã cùng gốc:

\[
c_{\text{sau}} = c_{\text{trước}}.
\]

Các bất biến này giúp phát hiện lỗi như giảm số nhóm hai lần, cộng sai kích thước hoặc gắn không đúng gốc.

## 11. So sánh các cách quản lý nhóm

Giả sử có `n` phần tử, các thao tác hợp và kiểm tra cùng nhóm xuất hiện nhiều lần. Bảng sau nêu giới hạn điển hình theo giả định của từng cách:

| Cấu trúc | Kiểm tra cùng nhóm | Hợp hai nhóm | Bộ nhớ phụ chính |
|---|---|---|---|
| Mảng nhãn, hợp bằng cách quét cả mảng | `O(1)` | `O(n)` mỗi lần hợp khác nhãn | `O(n)` |
| Mảng nhãn + danh sách thành viên, luôn chuyển nhóm nhỏ | `O(1)` | Có thể tốn `O(k_{\text{nhỏ}})` một lần; tổng cập nhật nhãn `O(n\log n)` trên các phép hợp thành công | `O(n)` |
| Rừng DSU, gắn gốc tùy ý | `O(h)` cho `find`, `h` có thể tới `O(n)` | `O(h)` cho các lần tìm gốc | `O(n)` |
| DSU + union by size, không path compression | `O(log n)` trong trường hợp xấu | `O(log n)` | `O(n)` |
| DSU + union by size + path compression | Gần `O(α(n))` **khấu hao** | Gần `O(α(n))` **khấu hao** | `O(n)` |

Các dòng so sánh không bao gồm chi phí lưu và xử lý dữ liệu nghiệp vụ ngoài cấu trúc nhóm. Nếu nhóm rất nhỏ hoặc ít lần hợp, cách đơn giản vẫn có thể đủ nhanh và dễ bảo trì. Nếu cần hàng triệu phép hợp/kiểm tra, DSU thường là lựa chọn hợp lý.

### DSU không có đầy đủ tính năng của một tập hợp tùy ý

Tên “disjoint sets” dễ gây hiểu nhầm rằng DSU hỗ trợ mọi phép toán trên tập. Cấu trúc kinh điển **không tự cung cấp**:

- Xóa một phần tử khỏi một nhóm rồi đưa vào nhóm khác.
- Tách một nhóm đã hợp thành hai nhóm.
- Liệt kê tức thì toàn bộ thành viên của nhóm.
- Kiểm tra hai nút có cạnh trực tiếp hoặc tìm đường đi giữa chúng.
- Trả về thứ tự phần tử, trọng số đường đi, hoặc quan hệ có hướng.

DSU giải quyết **bài toán phân hoạch với các phép hợp nhóm và truy vấn đại diện**. Cần yêu cầu nào khác thì phải bổ sung dữ liệu hoặc chọn cấu trúc thích hợp.

## 12. Ứng dụng 1: thành phần liên thông khi thêm cạnh

Với một đồ thị vô hướng `G=(V,E)` có `n` đỉnh, hai đỉnh `u` và `v` liên thông khi có đường đi vô hướng giữa chúng.

Ta có thể khởi tạo `n` nhóm đơn, rồi khi có cạnh mới `(u,v)`:

```text
add_edge(u, v):
    union(u, v)

connected(u, v):
    return find(u) == find(v)
```

Ví dụ:

```text
Các cạnh được thêm:
(0,1), (2,3), (1,2), (5,6), (6,7)

Thành phần liên thông cuối:
{0,1,2,3}, {4}, {5,6,7}
```

Mỗi lần thêm cạnh có thể làm hai thành phần hợp nhất, hoặc không thay đổi nếu hai đầu cạnh vốn đã liên thông. Với DSU có hai tối ưu chuẩn, việc xử lý chuỗi thêm cạnh và truy vấn liên thông rất hiệu quả về mặt khấu hao.

### Phân biệt “có đường đi” và “đường đi cụ thể”

DSU trả lời **có hay không** về liên thông. Nó **không lưu đường đi** qua các cạnh gốc để trả lời “đi từ `u` tới `v` qua những đỉnh nào?”. Nếu cần đường đi cụ thể, BFS/DFS hoặc các cấu trúc đồ thị tương ứng vẫn cần thiết.

### Tại sao xóa cạnh là một bài toán khác?

Nếu xóa cạnh `(u,v)`, hai đỉnh có thể vẫn liên thông qua đường khác hoặc có thể bị tách thành hai thành phần. DSU kinh điển **không có thao tác split** để quyết định và cập nhật đúng một cách trực tiếp.

Nếu chỉ có một số lần xóa và đồ thị nhỏ, có thể dựng lại DSU từ các cạnh còn lại. Nếu cần cập nhật động cả thêm và xóa cạnh ở quy mô lớn, đó là bài toán **dynamic connectivity** phức tạp hơn, có thể dùng thuật toán offline hoặc cấu trúc dữ liệu chuyên biệt.

## 13. Ứng dụng 2: phát hiện cạnh tạo chu trình

Khi duyệt các cạnh của đồ thị vô hướng và xây một **rừng** (forest) từ các cạnh được chấp nhận:

1. Kiểm tra hai đầu cạnh `u` và `v` có cùng nhóm hay không.
2. Nếu **khác nhóm**, cạnh nối hai thành phần, có thể thêm vào rừng và gọi `union(u,v)`.
3. Nếu **cùng nhóm**, đã có đường đi trong rừng giữa `u` và `v`; thêm cạnh sẽ tạo chu trình, nên có thể bỏ qua.

```text
for each undirected edge (u, v):
    if find(u) != find(v):
        accept(edge)
        union(u, v)
    else:
        reject(edge)  // Tạo chu trình nếu thêm vào rừng hiện tại.
```

Quy tắc này chính là nền tảng kiểm tra chu trình trong **thuật toán Kruskal** tìm cây khung nhỏ nhất. Kruskal sắp xếp các cạnh theo trọng số tăng dần rồi dùng DSU để chọn cạnh nối hai thành phần khác nhau.

Với `V` đỉnh và `E` cạnh, phần thao tác DSU có chi phí khấu hao gần `O(Eα(V))` sau khởi tạo; việc sắp xếp cạnh thường chiếm `O(E log E)` theo phương pháp sắp xếp so sánh thông thường. **Không nên nhầm tổng chi phí Kruskal với riêng chi phí DSU.**

### Một lưu ý về cạnh khuyên và cạnh trùng

Nếu cạnh có hai đầu trùng nhau `(u,u)`, `find(u) == find(u)` nên không được hợp thêm. Nếu có nhiều cạnh trùng giữa hai đỉnh, cạnh đầu có thể hợp nhóm; những cạnh sau gặp hai đầu đã cùng nhóm sẽ không làm giảm số thành phần. Đây là hành vi hợp lệ và là một tính chất hữu ích của Union–Find.

## 14. Ứng dụng 3: gom tài khoản hoặc đối tượng theo bằng chứng liên hệ

Giả sử các bản ghi có mã khách hàng và ứng dụng thu thập bằng chứng một số cặp bản ghi thuộc cùng chủ thể. Nếu quy tắc nghiệp vụ khẳng định rằng quan hệ “cùng chủ thể” là **tương đương**, có thể:

1. Gán mỗi bản ghi một chỉ số.
2. Với mỗi cặp được xác nhận `(a,b)`, gọi `union(a,b)`.
3. Với mỗi bản ghi, dùng `find` để lấy nhóm hiện tại.
4. Duyệt các bản ghi và nhóm lại theo đại diện nếu cần xuất danh sách.

Tuy nhiên, cần cẩn trọng: một phép gộp sai có thể **lan theo bắc cầu** và gộp nhiều bản ghi không mong muốn. DSU thông thường không thể tách nhóm trở lại khi bằng chứng được rút lại.

Vì vậy, trong hệ thống định danh thực tế, **quy tắc xác nhận liên kết, lịch sử gộp, khả năng sửa sai và kiểm toán** cũng quan trọng như tốc độ của cấu trúc dữ liệu. Khi gộp nhầm phải hoàn tác, có thể cần lưu sự kiện và dựng lại, hoặc dùng phiên bản DSU có hỗ trợ rollback theo những điều kiện cụ thể; không nên mặc định DSU thông thường có undo.

### Điều không phù hợp

Nếu một người có thể thuộc đồng thời nhiều nhóm sở thích, công ty hoặc dự án, quan hệ thành viên **không tạo phân hoạch**. Cần biểu diễn nhóm bằng những tập độc lập, bảng quan hệ nhiều-nhiều, hoặc đồ thị hai phía thay vì dùng một DSU duy nhất.

## 15. Bài toán có ID ngoài không liên tiếp

Các ví dụ dùng chỉ số `0..n-1` vì mảng `parent` truy cập nhanh và đơn giản. Thực tế có thể nhận ID dạng chuỗi như `"acct-A"`, `"acct-B"` hoặc số nguyên rất lớn.

Một cách an toàn là dùng bảng ánh xạ:

```text
External ID  →  Dense index

"acct-A"     →     0
"acct-B"     →     1
"acct-C"     →     2

DSU quản lý các chỉ số: 0, 1, 2
```

Cần bảo đảm mỗi ID bên ngoài ánh xạ **ổn định và duy nhất** tới một chỉ số trong thời gian DSU hoạt động. Có thể dùng hash map để cấp chỉ số mới khi ID lần đầu xuất hiện, rồi thêm một nút đơn vào DSU.

Chi phí tổng thể khi đó gồm cả tra cứu hash map (thường `O(1)` kỳ vọng) và thao tác DSU. Để trả danh sách ID gốc, cần lưu ánh xạ ngược `index → external ID` hoặc tham chiếu thích hợp.

**Không dùng giá trị ID rất lớn làm chỉ số trực tiếp** nếu việc đó buộc cấp phát mảng hàng tỷ phần tử chỉ cho vài bản ghi.

## 16. Xử lý dữ liệu lỗi, tác vụ đồng thời và vòng đời trạng thái

### 16.1. Kiểm tra miền và khởi tạo

Mọi `find(x)` hoặc `union(x,y)` phải nhận phần tử **đã được đăng ký**. Với mảng dài `n`, điều kiện là `0 ≤ x,y < n`. Phần tử âm trong Python dễ gây lỗi ngữ nghĩa vì chỉ số âm mặc định trỏ từ cuối danh sách; ví dụ `parent[-1]` có thể truy cập phần tử cuối thay vì báo lỗi.

Hàm `_check` trong ví dụ Python cố ý từ chối chỉ số âm và chỉ số vượt miền.

### 16.2. Truy vấn lặp và tự hợp

`union(x,x)` và `union(x,y)` khi hai phần tử đã cùng gốc phải **không thay đổi** phân hoạch. Nếu lưu `component_count` hoặc `size`, không được trừ số nhóm/cộng kích thước trong trường hợp này.

### 16.3. Truy cập đồng thời

`find` có **path compression** là một thao tác có thể **ghi** vào mảng `parent`, ngay cả khi người gọi chỉ hỏi cùng nhóm. Vì thế không được mặc định hai luồng gọi `find`/`union` đồng thời là an toàn trên cùng một DSU.

Triển khai đa luồng cần đồng bộ phù hợp, hoặc lựa chọn cấu trúc Union–Find concurrent chuyên dụng. Chỉ thêm khóa ngoài khi thực sự hiểu yêu cầu hiệu năng và tính nhất quán; những ví dụ đơn luồng không tự bảo đảm an toàn luồng.

### 16.4. Khi nào cần lưu lịch sử?

Nếu bài toán có yêu cầu quay lại một trạng thái cũ, DSU có thể được mở rộng theo một số mô hình như **rollback Union–Find**; nhưng path compression thay đổi nhiều con trỏ nên việc undo không còn đơn giản. Đây là một vấn đề thiết kế khác với DSU kinh điển chỉ có hợp nhóm.

Nếu cần xóa, tách, tái cấu trúc nhóm hoặc duy trì thành phần liên thông của đồ thị thay đổi liên tục, phải đánh giá đúng yêu cầu thay vì cố ép tất cả vào ba hàm `find`/`union`/`same`.

## 17. Những lỗi tư duy và triển khai thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
|---|---|---|
| Cho rằng một phần tử có thể thuộc nhiều nhóm trong cùng một DSU | Mâu thuẫn với bất biến phân hoạch | Dùng quan hệ nhiều-nhiều hoặc nhiều cấu trúc khác nhau |
| Gắn `parent[y] = x` tùy ý trong `union` | Có thể không gộp đúng hai cây, thậm chí tạo vòng cha | Tìm hai **gốc** rồi mới nối |
| Giảm `component_count` sau mọi lời gọi `union` | Hợp hai phần tử đã cùng nhóm không giảm số nhóm | Chỉ giảm khi hai gốc khác nhau |
| Dùng `size[x]` làm kích thước nhóm khi `x` không phải gốc | Metadata tại nút con có thể cũ | Đọc `size[find(x)]` |
| Đòi `find(x)` luôn trả phần tử nhỏ nhất nhóm | Đại diện do chiến lược hợp quyết định | Không gắn ý nghĩa nghiệp vụ vào root |
| Dùng DSU để truy vấn cạnh trực tiếp | DSU chỉ lưu lớp liên thông, không giữ đủ cạnh | Dùng cấu trúc đồ thị cho cạnh/đường đi |
| Xóa cạnh nhưng giữ nguyên DSU | Quan hệ liên thông có thể bị tách | Dựng lại hoặc dùng thuật toán dynamic connectivity |
| Dùng DSU cho quan hệ có hướng không đối xứng | Không phải quan hệ tương đương | Xác định lại mô hình quan hệ |
| Quên giới hạn chỉ số | Truy cập sai phần tử hoặc lỗi bộ nhớ | Kiểm tra miền, đặc biệt chỉ số âm |
| Coi `find` nén đường đi là thao tác chỉ đọc | Hàm có thể sửa `parent` | Thiết kế đồng bộ khi chạy đồng thời |
| Gọi DSU là `O(1)` worst-case trong mọi trường hợp | Chặn chuẩn là **khấu hao**, phụ thuộc tối ưu | Phân biệt chi phí một lần và toàn chuỗi |
| Lưu root như ID nhóm bền vững | Root có thể thay đổi sau lần hợp | Duy trì mã nhóm nghiệp vụ riêng nếu cần |

## 18. Quy trình lựa chọn cấu trúc dữ liệu

Trước khi triển khai, nên tự hỏi:

1. **Các nhóm có tạo thành phân hoạch không?** Mỗi phần tử có đúng một nhóm tại một thời điểm?
2. **Các quan hệ có ý nghĩa tương đương hoặc liên thông vô hướng không?** Có phản xạ, đối xứng, bắc cầu ở cấp “cùng nhóm”?
3. **Thao tác chủ đạo là gì?** Nhiều lần hợp và hỏi cùng nhóm, hay thường xuyên cần duyệt thành viên?
4. **Có cần tách nhóm, xóa liên kết hoặc hoàn tác không?** Nếu có, DSU chuẩn có thể không đủ.
5. **Miền ID có liên tục và biết trước không?** Có cần bảng ánh xạ ngoài?
6. **Độ lớn `n` và số truy vấn `m` là bao nhiêu?** Mảng nhãn đơn giản có đủ hay cần DSU gần hằng số khấu hao?
7. **Cần metadata nào?** Số thành viên từng nhóm, số nhóm, tên nhóm nghiệp vụ, dữ liệu kết hợp khác?
8. **Có truy cập đồng thời không?** Path compression và union đều có thể ghi vào trạng thái chung.

Khi đáp án chủ yếu là **“gộp dần và kiểm tra hai phần tử có cùng nhóm”**, DSU với union by size và path compression là một lựa chọn điển hình.

## 19. Bài tập tự kiểm tra có lời giải

**Câu 1.** Cho `U={0,1,2,3,4,5}` và `P={{0,2},{1,3},{4},{5}}`. Đây có phải phân hoạch hợp lệ không?

**Lời giải:** Có. Mọi nhóm không rỗng, từng phần tử xuất hiện đúng một lần và hợp các nhóm bằng `U`. Có 4 nhóm.

**Câu 2.** Trong phân hoạch ở câu 1, gọi `union(0,3)` thì các nhóm thay đổi ra sao?

**Lời giải:** Nhóm chứa `0` là `{0,2}`, nhóm chứa `3` là `{1,3}`. Sau hợp thành `{0,1,2,3}`; các nhóm `{4}` và `{5}` giữ nguyên. Số nhóm giảm từ 4 xuống 3.

**Câu 3.** Nếu `same(0,3)` đã bằng `true`, gọi `union(0,3)` thêm lần nữa có làm số nhóm giảm không?

**Lời giải:** Không. Hai phần tử đã cùng nhóm nên không có hai nhóm khác nhau để hợp.

**Câu 4.** Với `n=8` ban đầu có 8 nhóm, thực hiện năm phép hợp **thành công**. Cuối cùng còn mấy nhóm?

**Lời giải:** `8 - 5 = 3` nhóm. Phép hợp không thành công vì hai đầu đã cùng nhóm không được tính.

**Câu 5.** Vì sao phép `union` đúng phải nối hai **gốc**, không đơn thuần nối hai nút tùy ý?

**Lời giải:** Gốc đại diện cho **toàn bộ nhóm**. Nối hai gốc khác nhau làm hợp trọn vẹn hai cây. Nối nút tùy ý có thể phá cấu trúc cha, làm sai nhóm hoặc tạo chu trình.

**Câu 6.** Mảng nhãn `group[x]` cho phép `same` `O(1)`. Vì sao vẫn muốn dùng DSU?

**Lời giải:** Khi hợp nhóm bằng cách thay mọi nhãn cũ, một lần hợp có thể quét `O(n)` phần tử. DSU chỉ nối gốc và tìm đại diện với chi phí khấu hao rất thấp khi dùng các tối ưu chuẩn.

**Câu 7.** Nếu dùng union by size mà **không** nén đường đi, độ cao cây có thể là bao nhiêu?

**Lời giải:** `O(log n)`. Khi một cây nhỏ bị nối dưới cây lớn hơn hoặc bằng, số thành viên của nhóm chứa các nút trong cây nhỏ ít nhất tăng gấp đôi; một nút không thể bị tăng độ sâu quá `O(log n)` lần.

**Câu 8.** `find(x)` có path compression có giữ nguyên các nhóm không?

**Lời giải:** Có. Nó chỉ đổi cha của các nút trên đường tìm gốc thành chính gốc của **cùng một cây**, không chuyển bất kỳ phần tử nào sang cây khác.

**Câu 9.** Với các cạnh vô hướng `(0,1), (1,2), (3,4)`, có bao nhiêu thành phần liên thông trên năm đỉnh `{0,1,2,3,4}`?

**Lời giải:** Có 2 thành phần: `{0,1,2}` và `{3,4}`. DSU tạo được chúng bằng ba phép hợp thành công.

**Câu 10.** Nếu xóa cạnh `(1,2)` sau câu 9, DSU hiện tại có tự cập nhật đúng hai thành phần mới không?

**Lời giải:** Không. DSU kinh điển chỉ hợp nhóm, không tách nhóm khi xóa cạnh. Nếu không còn đường thay thế, đồ thị có thể tách thành `{0,1}`, `{2}`, `{3,4}`; cần dựng lại hoặc dùng thuật toán phù hợp với xóa cạnh.

**Câu 11.** Một đồ thị có cạnh `(u,v)` sắp được thêm vào rừng hiện tại. Điều kiện nào cho biết cạnh tạo chu trình?

**Lời giải:** Nếu `find(u) == find(v)`, hai đỉnh đã có đường đi trong cùng cây của rừng. Thêm cạnh nối chúng tạo chu trình; nếu hai gốc khác nhau, cạnh nối hai thành phần mà không tạo chu trình.

**Câu 12.** DSU có thể quản lý trực tiếp một người đồng thời ở câu lạc bộ A và câu lạc bộ B như hai nhóm giao nhau không?

**Lời giải:** Không, nếu yêu cầu là giữ nguyên hai câu lạc bộ riêng biệt và có người ở cả hai. DSU biểu diễn phân hoạch, nên mỗi phần tử chỉ có một nhóm tại một thời điểm. Cần cấu trúc quan hệ nhiều-nhiều.

**Câu 13.** Sau một loạt phép hợp, các gốc hiện tại có kích thước lần lượt `4`, `1` và `3`. Có thể suy ra gì nếu miền có 8 phần tử?

**Lời giải:** Tổng `4+1+3=8` bằng số phần tử của miền và có 3 nhóm. Đây là điều kiện cần để metadata phù hợp với phân hoạch; còn phải kiểm tra các cây thật sự rời nhau và mọi nút có gốc hợp lệ.

## Ghi nhớ

- **Bài toán quản lý nhóm không giao nhau** là duy trì một **phân hoạch** của miền: mỗi phần tử thuộc đúng một nhóm; các nhóm không giao nhau và hợp của chúng bằng toàn miền.
- Quan hệ “cùng nhóm” phải có tính **phản xạ, đối xứng, bắc cầu**. Gộp nhóm tạo quan hệ liên thông/tương đương, không chỉ ghi một cặp liên hệ trực tiếp.
- **DSU / Union–Find** hỗ trợ `find(x)` lấy đại diện và `union(x,y)` hợp hai nhóm; kiểm tra cùng nhóm bằng `find(x) == find(y)`. Một phép hợp thành công giảm số nhóm đúng 1.
- Trong biểu diễn **rừng cha**, mỗi nhóm là một cây có gốc `parent[root] = root`. **Union by size** giới hạn chiều cao, **path compression** rút ngắn đường truy vấn; kết hợp cho chi phí **gần hằng số khấu hao** trong chuỗi thao tác.
- DSU phù hợp với **thêm liên kết và kiểm tra liên thông**, phát hiện cạnh tạo chu trình trong Kruskal, và gom các phần tử theo quan hệ tương đương.
- DSU kinh điển **không tự hỗ trợ xóa liên kết, tách nhóm, đường đi cụ thể hoặc quan hệ nhóm chồng lấn**. Cần chọn cấu trúc khác hoặc bổ sung thuật toán khi yêu cầu vượt khỏi mô hình chỉ hợp nhóm.
