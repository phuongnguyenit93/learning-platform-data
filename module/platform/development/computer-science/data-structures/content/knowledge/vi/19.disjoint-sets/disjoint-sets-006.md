# Nén đường đi, chia đôi đường đi và cập nhật cha

Trong **Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, mỗi nhóm phần tử được biểu diễn bằng một cây có gốc. Để biết phần tử `x` thuộc nhóm nào, hàm `find(x)` đi theo các liên kết cha đến gốc. Nếu một cây có đường cha rất dài, việc truy tìm đại diện nhiều lần sẽ tốn thời gian, dù kết quả vẫn đúng.

Có ba cách phổ biến để **rút ngắn đường cha trong lúc tìm gốc**:

- **Nén đường đi đầy đủ (full path compression):** sau khi biết gốc, cho các nút trên đường từ `x` tới gốc trỏ trực tiếp về gốc.
- **Chia đôi đường đi (path halving):** trong lúc đi lên, cho nút hiện tại trỏ đến **ông/bà** của nó rồi di chuyển đến nút vừa cập nhật; như vậy thường bỏ qua một nút sau mỗi vòng.
- **Tách đường đi (path splitting):** cũng cho nút đang xét trỏ đến ông/bà, nhưng di chuyển đến **cha cũ**, nên lần lượt xử lý mọi nút trên đường ban đầu.

Bài này thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là hiểu bản chất việc **cập nhật `parent`**, tự triển khai và kiểm chứng ba biến thể, phân tích chi phí thời gian/bộ nhớ, đồng thời biết khi nào cần kết hợp chúng với **hợp theo kích thước hoặc theo hạng**.

## 1. Vì sao cần tối ưu phép tìm gốc?

Xét mảng cha sau:

```text
x:          0 1 2 3 4 5
parent[x]:  0 0 1 2 3 4
```

Nó tạo một cây dạng chuỗi:

```text
5 → 4 → 3 → 2 → 1 → 0
                    ^ root
```

Mọi phần tử từ 0 đến 5 đều thuộc **một nhóm**, vì mọi đường cha kết thúc tại 0. Nhưng `find(5)` phải đi qua năm liên kết cha để trả về 0. Nếu ứng dụng liên tục hỏi đại diện của 5, việc lặp lại năm bước đó là không cần thiết.

Một ý tưởng là: **ngay trong lần tìm đầu tiên, hãy sửa đường cha để các lần tìm sau ngắn hơn**.

Ví dụ, sau full path compression của `find(5)`:

```text
         0
       / | \ \ \
      1  2  3 4  5

parent = [0,0,0,0,0,0]
```

Giờ `find(5)` chỉ đi qua một cạnh `5→0`.

**Điểm cần ghi nhớ:** thao tác này không hợp nhóm mới, không thay đổi thành viên và không thay đổi gốc logic. Nó chỉ **đổi hình dạng cây bên trong cùng một nhóm**.

## 2. Bất biến của rừng cha phải giữ nguyên

DSU quản lý một phân hoạch của tập phần tử `U={0,1,\ldots,n-1}`: mỗi phần tử thuộc đúng một nhóm, các nhóm khác nhau không giao nhau.

Mảng `parent` biểu diễn các nhóm bằng rừng cây với các bất biến sau:

1. Với mọi phần tử hợp lệ `x`, `parent[x]` là một chỉ số hợp lệ thuộc `[0,n)`.
2. Mỗi nhóm có đúng một gốc `r` thỏa `parent[r]=r`.
3. Từ mỗi phần tử, đi theo cha cuối cùng phải đến một gốc; không có chu trình cha dài hơn một nút.
4. Hai phần tử cùng nhóm **khi và chỉ khi** chúng có cùng gốc:

\[
\mathrm{same}(x,y)
\iff
\mathrm{find}(x)=\mathrm{find}(y).
\]

5. Các cây rời nhau và bao phủ toàn bộ miền.

Nếu lưu metadata `size` hoặc `rank`, giá trị dùng để mô tả một nhóm phải được đọc ở **gốc hiện tại**. Nếu lưu `componentCount`, biến này bằng số gốc.

**Quy tắc an toàn nhất của các thuật toán rút ngắn đường:** chỉ thay cha của một nút bằng **một tổ tiên của chính nó trong cùng cây**, đặc biệt là gốc hoặc ông/bà. Như vậy nút không bị chuyển sang nhóm khác.

### Cần phân biệt cha trực tiếp và đại diện

Với:

```text
parent = [0,0,1,2,3,4]
```

ta có `parent[5]=4` nhưng `find(5)=0`. Con trỏ cha trực tiếp **không phải lúc nào cũng là đại diện**.

Sau khi sửa `parent[5]=3`, đại diện vẫn là 0. Một cấu trúc có nhiều hình dạng rừng khác nhau có thể biểu diễn chính xác **cùng một phân hoạch**.

## 3. Phiên bản cơ bản: `find` không cập nhật cha

Trước khi học các phép sửa, xét tìm gốc không nén đường:

```text
find_basic(x):
    require x nằm trong miền
    while parent[x] != x:
        x = parent[x]
    return x
```

Thuật toán thực hiện:

1. Đọc `parent[x]`.
2. Nếu `parent[x]==x`, x là gốc; trả về.
3. Nếu không, di chuyển tới cha và lặp lại.

Với đường:

```text
5 → 4 → 3 → 2 → 1 → 0
```

`find_basic(5)` lần lượt thăm `5,4,3,2,1,0`, trả về 0 và giữ nguyên mảng `parent`.

Nếu chiều cao của cây là `h`, chi phí một lần tìm gốc là **`O(h)`**, vì có thể đi qua `h` cạnh. Khi hợp gốc tùy ý, cây có thể cao `Θ(n)`. Nếu dùng **union by size/rank**, chiều cao được chặn `O(log n)` ngay cả trước khi nén.

Các biến thể tiếp theo cải thiện đường đi bằng cách **ghi lại giá trị `parent` trong quá trình tìm**, không thay đổi điều kiện để một phần tử được xem là gốc.

## 4. Nén đường đi đầy đủ bằng hai lượt

**Full path compression** rút ngắn toàn bộ đường từ x đến gốc r bằng cách đặt cha của từng nút trên đường thành r.

Có thể triển khai lặp với **hai lượt**.

### Giả mã

```text
find_full(x):
    require x nằm trong miền

    root = x

    // Lượt 1: tìm gốc, chưa thay dữ liệu.
    while parent[root] != root:
        root = parent[root]

    // Lượt 2: sửa cha từng nút trên đường cũ.
    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = root
        x = old_parent

    return root
```

**Tại sao phải lưu `old_parent` trước khi sửa?** Khi ghi `parent[x]=root`, liên kết tới cha cũ bị thay thế. Nếu sau đó di chuyển bằng `x=parent[x]`, chương trình sẽ nhảy ngay tới gốc và **bỏ qua các nút trung gian chưa nén**.

### Truy vết cụ thể

Với `parent=[0,0,1,2,3,4]`, gọi `find_full(5)`.

Lượt 1:

```text
root: 5 → 4 → 3 → 2 → 1 → 0
Gốc tìm được: 0
```

Lượt 2:

| `x` đang xét | Cha cũ | Cập nhật |
|---:|---:|---|
| 5 | 4 | `parent[5]=0` |
| 4 | 3 | `parent[4]=0` |
| 3 | 2 | `parent[3]=0` |
| 2 | 1 | `parent[2]=0` |
| 1 | 0 | `parent[1]=0` |

Mảng sau:

```text
parent = [0,0,0,0,0,0]
```

Các lần tìm từ 1, 2, 3, 4, 5 tới gốc đều rất ngắn. Tuy nhiên, **lần tìm đầu tiên vẫn phải đọc đường cũ tới gốc**, nên không thể xem lần đầu này là `O(1)` trong trường hợp xấu.

### Phiên bản đệ quy

Một cách viết ngắn gọn:

```text
find_full_recursive(x):
    if parent[x] != x:
        parent[x] = find_full_recursive(parent[x])
    return parent[x]
```

Khi các lời gọi sâu hơn trả về gốc, mỗi lời gọi đặt cha của nút đang xét thành gốc. Cách này dễ nhớ nhưng ngăn xếp lời gọi có thể dùng **`O(h)` bộ nhớ phụ** và có nguy cơ vượt giới hạn đệ quy nếu cây rất sâu. Cách lặp hai lượt chỉ cần vài biến cục bộ, tức **`O(1)` bộ nhớ phụ**.

## 5. Chia đôi đường đi: `path halving`

**Path halving** cập nhật cha ngay trong khi đang lần theo đường tới gốc. Tại nút x:

1. Đọc cha của x, gọi là p.
2. Đọc cha của p, gọi là g (ông/bà của x).
3. Đặt `parent[x]=g`.
4. Di chuyển `x=g` — tức **nhảy tới ông/bà**.

Giả mã thường thấy:

```text
find_halving(x):
    require x nằm trong miền

    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]

    return x
```

Nếu cha của x đã là gốc, `parent[parent[x]]` vẫn chính là gốc vì gốc tự trỏ. Vòng lặp vẫn tiến tới gốc và dừng.

### Truy vết từng bước

Cho:

```text
5 → 4 → 3 → 2 → 1 → 0
```

Gọi `find_halving(5)`:

| Lượt | x trước cập nhật | Cha cũ p | Ông/bà g | Gán | x tiếp theo |
|---:|---:|---:|---:|---|---:|
| 1 | 5 | 4 | 3 | `parent[5]=3` | 3 |
| 2 | 3 | 2 | 1 | `parent[3]=1` | 1 |
| 3 | 1 | 0 | 0 | `parent[1]=0` | 0 |

Kết quả trả về vẫn là 0. Mảng sau:

```text
parent = [0,0,1,1,3,3]
```

Lúc này đường đi từ 5 là:

```text
5 → 3 → 1 → 0
```

Độ dài giảm từ **5 cạnh xuống 3 cạnh** sau một lần gọi, nhưng **không phải mọi nút đều trỏ thẳng về gốc**. Những lần tìm sau có thể tiếp tục chia đôi đường.

### Chính xác “chia đôi” nghĩa là gì?

Thuật toán thường chỉ xử lý **một số nút xen kẽ trên đường cũ**, vì sau cập nhật nó nhảy qua cha cũ và đứng ở ông/bà. Kết quả xấp xỉ rút ngắn số cạnh của đường đang tìm, nhưng không có nghĩa số cạnh trong mọi cây luôn bị chia đúng hai bằng số học sau một lần gọi.

Điểm khác với full compression: path halving thường **chỉ cần một lượt duyệt** và không cần đi tới gốc trước khi bắt đầu cập nhật.

## 6. Tách đường đi: `path splitting`

**Path splitting** cũng cập nhật một nút trỏ tới ông/bà nhưng **khác ở bước di chuyển**: sau khi cập nhật, nó tiếp tục tới **cha cũ**, không nhảy tới ông/bà.

Giả mã:

```text
find_splitting(x):
    require x nằm trong miền

    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = parent[old_parent]
        x = old_parent

    return x
```

Vì `x=old_parent`, thuật toán lần lượt xử lý **từng nút trên đường cũ** (trừ gốc). Những đường cha của các nút này được thay bằng liên kết nhảy một bậc.

### Truy vết trên cùng cây

Với đường ban đầu:

```text
5 → 4 → 3 → 2 → 1 → 0
```

`find_splitting(5)` thực hiện:

| Lượt | x trước cập nhật | Cha cũ | Ông/bà | Gán | x tiếp theo |
|---:|---:|---:|---:|---|---:|
| 1 | 5 | 4 | 3 | `parent[5]=3` | 4 |
| 2 | 4 | 3 | 2 | `parent[4]=2` | 3 |
| 3 | 3 | 2 | 1 | `parent[3]=1` | 2 |
| 4 | 2 | 1 | 0 | `parent[2]=0` | 1 |
| 5 | 1 | 0 | 0 | `parent[1]=0` | 0 |

Kết quả:

```text
parent = [0,0,0,1,2,3]
```

Đường từ 5 bây giờ là:

```text
5 → 3 → 1 → 0
```

Đây **cũng là một đường ngắn hơn**, nhưng hình dạng mảng khác với path halving và full compression.

### Vì sao `old_parent` rất quan trọng?

Nếu thay:

```text
x = old_parent
```

bằng:

```text
x = parent[x]
```

sau phép gán, ta sẽ **di chuyển tới ông/bà vừa ghi**, và thuật toán trở thành một dạng path halving. Hai cách vẫn có thể tìm đúng gốc nhưng khác số nút được cập nhật và hiệu năng ở các mẫu truy vấn cụ thể.

## 7. Đối chiếu cả ba biến thể trên cùng một đường

Ta lấy một rừng có tám nút:

```text
parent ban đầu = [0,0,1,2,3,4,6,6]

Nhóm A: {0,1,2,3,4,5}
  5 → 4 → 3 → 2 → 1 → 0

Nhóm B: {6,7}
  7 → 6
```

Trên ba **bản sao độc lập** của mảng ban đầu, đều gọi `find(5)` một lần:

| Thuật toán | Mảng `parent` sau `find(5)` | Gốc trả về |
|---|---|---:|
| Không nén | `[0,0,1,2,3,4,6,6]` | 0 |
| Full compression | `[0,0,0,0,0,0,6,6]` | 0 |
| Path halving | `[0,0,1,1,3,3,6,6]` | 0 |
| Path splitting | `[0,0,0,1,2,3,6,6]` | 0 |

**Những điều không thay đổi ở cả bốn trường hợp:**

- Gốc của mọi phần tử trong nhóm A vẫn là 0.
- Gốc của nhóm B vẫn là 6; `parent[6]=6` và `parent[7]=6` không đổi.
- Số nhóm vẫn bằng 2.
- Tổng số thành viên trong các nhóm vẫn là 8.
- `find(5)` đều trả về 0.

Nhưng các mảng `parent` **không giống nhau**, vì ba chiến lược có chính sách cập nhật khác nhau. Vì vậy khi kiểm thử một DSU tổng quát, không nên khăng khăng đòi mọi phiên bản phải tạo ra **cùng mảng cha**.

### Lần tìm tiếp theo thay đổi thế nào?

- **Full compression:** từ 5 đi thẳng tới 0 qua một cạnh.
- **Halving sau một lần:** từ 5 đi `5→3→1→0`.
- **Splitting sau một lần:** từ 5 cũng đi `5→3→1→0`.

Hai biến thể một lượt có thể tiếp tục làm ngắn đường khi tìm lại, và chúng cũng có thể tạo những cải thiện khác nhau cho các nút không nằm trên đường truy vấn tiếp theo.

**Không suy từ ví dụ này rằng halving và splitting luôn nhanh bằng nhau.** Số lần đọc/ghi, cache, độ sâu cây và thứ tự truy vấn có thể làm chúng khác nhau.

## 8. Chứng minh cập nhật cha không làm đổi nhóm

Các biến thể đều dựa trên nguyên lý **đi tắt theo tổ tiên**.

Giả sử tại một thời điểm, phần tử x thuộc cây có gốc r. Trên đường lên r, ta có:

```text
x → p → g → ... → r
```

Trong đó p là cha, g là ông/bà của x.

### 8.1. Một bước cập nhật hợp lệ

Nếu đặt `parent[x]=g`, đường mới là:

```text
x → g → ... → r
```

Ta chỉ **bỏ qua p** trên đường từ x tới r:

- x vẫn đi tới r.
- p không mất khỏi cây; nó vẫn có đường đi riêng tới r.
- Không có nút nào chuyển sang cây khác.
- Không tạo chu trình mới vì g là **tổ tiên của x**, không phải hậu duệ.

Nếu đặt `parent[x]=r` theo full compression, lập luận tương tự: r cũng là tổ tiên của x.

### 8.2. Áp dụng lặp nhiều bước

Một phép `find` chỉ gồm những bước đi tắt hợp lệ bên trong cùng cây, nên tất cả thao tác cập nhật vẫn giữ nguyên gốc của từng nút. Do đó:

\[
\forall x:\ \mathrm{root}_{\mathrm{after}}(x)
=\mathrm{root}_{\mathrm{before}}(x).
\]

Suy ra:

\[
\mathrm{same}_{\mathrm{after}}(x,y)
=\mathrm{same}_{\mathrm{before}}(x,y).
\]

Không cần cập nhật `componentCount`, không cần cộng `size` và không cần tăng `rank` chỉ vì một lần `find` đã làm ngắn đường.

### 8.3. Điều kiện tiền đề không được bỏ qua

Lập luận trên dựa vào việc **mảng cha ban đầu là một rừng hợp lệ**. Nếu `parent` đã chứa chu trình như `0→1→0`, khái niệm gốc và tổ tiên không còn đúng. Một vòng lặp `find` thông thường có thể không dừng.

Ngoài ra, ví dụ đơn luồng giả định **không có thao tác khác đang thay đổi đường cha trong lúc tìm**. Khi có cập nhật đồng thời, cần quy tắc đồng bộ/thuật toán chuyên biệt để những phép đọc và ghi vẫn nhất quán.

## 9. Cài đặt Python: ba hàm `find` trên cùng giao diện

Đầu tiên, ta dùng các hàm thao tác trực tiếp trên **một mảng cha hợp lệ**, không phụ thuộc metadata `size` hay `rank`. Mỗi hàm kiểm tra chỉ số đầu vào rồi trả về gốc.

```python
def check_index(parent: list[int], x: int) -> None:
    if not isinstance(x, int) or isinstance(x, bool):
        raise TypeError("Chỉ số phải là số nguyên")
    if not 0 <= x < len(parent):
        raise IndexError("Chỉ số ngoài miền DSU")


def find_basic(parent: list[int], x: int) -> int:
    check_index(parent, x)
    while parent[x] != x:
        x = parent[x]
    return x


def find_full(parent: list[int], x: int) -> int:
    check_index(parent, x)

    root = x
    while parent[root] != root:
        root = parent[root]

    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = root
        x = old_parent

    return root


def find_halving(parent: list[int], x: int) -> int:
    check_index(parent, x)

    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]

    return x


def find_splitting(parent: list[int], x: int) -> int:
    check_index(parent, x)

    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = parent[old_parent]
        x = old_parent

    return x


initial = [0, 0, 1, 2, 3, 4, 6, 6]

tests = [
    (find_basic, [0, 0, 1, 2, 3, 4, 6, 6]),
    (find_full, [0, 0, 0, 0, 0, 0, 6, 6]),
    (find_halving, [0, 0, 1, 1, 3, 3, 6, 6]),
    (find_splitting, [0, 0, 0, 1, 2, 3, 6, 6]),
]

for algorithm, expected_parent in tests:
    parent = initial.copy()

    assert algorithm(parent, 5) == 0
    assert parent == expected_parent

    # Hỏi các thành viên trong hai nhóm; mọi root vẫn đúng.
    assert all(find_basic(parent, i) == 0 for i in range(6))
    assert find_basic(parent, 6) == 6
    assert find_basic(parent, 7) == 6

print("Cả bốn cách đều tìm đúng gốc và giữ phân hoạch.")
```

### Những gì ví dụ kiểm tra được

- Cả bốn hàm đều **trả gốc 0** khi tìm từ 5.
- Chỉ các biến thể có nén mới sửa `parent`.
- Mảng cuối phù hợp với quy tắc cập nhật **từng biến thể**.
- Những phần tử không thuộc đường đang xử lý, ví dụ 6 và 7, giữ nguyên quan hệ cha.
- Không hàm nào làm thay đổi **quan hệ cùng nhóm**.

Mã này nhận `parent` như một đối số để dễ thử nghiệm. Trong ứng dụng thực tế, nên **đóng gói mảng cha** trong đối tượng DSU và chỉ sửa nó qua những thao tác đã được thiết kế đúng; không cho mã ngoài tùy tiện tạo chu trình.

## 10. Kết hợp `find` có rút ngắn đường với `union by size`

Nén đường đi là một tối ưu cho **find**. Để DSU nhanh trên chuỗi thao tác, ta còn nên kiểm soát **cách nối hai cây trong union**.

**Union by size** duy trì:

```text
size[root] = số thành viên của cây có gốc root
```

Khi hợp hai nhóm khác nhau, cho gốc cây nhỏ hơn trỏ tới gốc cây lớn hơn. Nếu hai cây bằng kích thước, chọn gốc nào cũng hợp lệ.

### Mã Python hoàn chỉnh dùng path halving

```python
class DSU:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("n phải không âm")
        self.parent = list(range(n))
        self.size = [1] * n
        self.components = n

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        # Path halving: đọc cha và ông/bà, rồi nhảy lên.
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        if self.size[rx] < self.size[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]


dsu = DSU(8)
assert dsu.components == 8

for u, v in [(0, 1), (2, 3), (1, 2), (5, 6), (6, 7)]:
    assert dsu.union(u, v)

assert dsu.components == 3
assert dsu.same(0, 3) is True
assert dsu.same(0, 7) is False
assert dsu.component_size(3) == 4
assert dsu.component_size(7) == 3

# Lặp lại union trong cùng nhóm là no-op.
assert dsu.union(0, 3) is False
assert dsu.components == 3
```

### Vì sao không cập nhật `size` trong `find`?

`find` có path halving có thể thay các liên kết cha, nhưng **không thêm hoặc bớt phần tử nào khỏi nhóm**. Vì vậy `size[root]` không thay đổi. Chỉ `union` giữa **hai gốc khác nhau** mới cộng kích thước và giảm số nhóm.

Đọc `size[x]` khi `x` không phải gốc có thể lấy dữ liệu cũ. Luôn dùng `size[find(x)]`.

## 11. C++17: lựa chọn biến thể `find` mà không đổi `union`

Trong C++, mảng `parent` thường được giữ bằng `std::vector<std::size_t>`. Dưới đây là một lớp minh họa **cả ba cách find** cùng một chiến lược union by size.

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class DSU {
public:
    explicit DSU(std::size_t n)
        : parent_(n), size_(n, 1), components_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find_full(std::size_t x) {
        validate(x);
        std::size_t root = x;

        while (parent_[root] != root) {
            root = parent_[root];
        }

        while (parent_[x] != x) {
            const std::size_t old_parent = parent_[x];
            parent_[x] = root;
            x = old_parent;
        }

        return root;
    }

    std::size_t find_halving(std::size_t x) {
        validate(x);

        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }

        return x;
    }

    std::size_t find_splitting(std::size_t x) {
        validate(x);

        while (parent_[x] != x) {
            const std::size_t old_parent = parent_[x];
            parent_[x] = parent_[old_parent];
            x = old_parent;
        }

        return x;
    }

    bool unite(std::size_t x, std::size_t y) {
        std::size_t rx = find_halving(x);
        std::size_t ry = find_halving(y);
        if (rx == ry) return false;

        if (size_[rx] < size_[ry]) std::swap(rx, ry);

        parent_[ry] = rx;
        size_[rx] += size_[ry];
        --components_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) {
        return find_halving(x) == find_halving(y);
    }

    std::size_t component_size(std::size_t x) {
        return size_[find_halving(x)];
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    void validate(std::size_t x) const {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }
    }

    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::size_t components_;
};

int main() {
    DSU dsu(6);

    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(1, 2);

    std::cout << dsu.same(0, 3) << '\n';       // 1
    std::cout << dsu.same(0, 5) << '\n';       // 0
    std::cout << dsu.component_size(3) << '\n'; // 4
    std::cout << dsu.component_count() << '\n'; // 3
}
```

### Giải thích sự lựa chọn

Trong `unite` và `same`, lớp dùng `find_halving` làm mặc định. Nếu đổi sang `find_full` hoặc `find_splitting`, **ngữ nghĩa DSU không đổi**: hai phần tử vẫn cùng nhóm khi cùng gốc, và union chỉ nối hai gốc khác nhau.

Ba phương thức `find_*` là **phép toán có thể ghi vào `parent_`**, nên chúng không được khai báo `const`. Khi ứng dụng có yêu cầu “truy vấn thuần chỉ đọc”, phải suy nghĩ lại về hợp đồng, khả năng chia sẻ dữ liệu và đồng bộ.

**Trong C++, không được truyền chỉ số ngoài phạm vi**, nhất là khi giá trị âm bị chuyển sang kiểu không dấu `std::size_t`. Hàm `validate` kiểm tra `x>=n` và báo ngoại lệ. Cũng cần đảm bảo rằng `parent_` chỉ được sửa qua những phương thức giữ bất biến.

## 12. Đếm số lần đọc/ghi `parent` trong một lần tìm

Các thuật toán đều đúng về đại diện, nhưng số phép đọc/ghi nội bộ khác nhau.

Giả sử đường từ x tới gốc có `h` cạnh.

| Thuật toán | Cách đi | Những nút có thể được cập nhật | Bộ nhớ phụ nếu viết lặp |
|---|---|---|---|
| Tìm gốc cơ bản | Đi từ x qua từng cha tới gốc | Không nút nào | `O(1)` |
| Full compression hai lượt | Tìm gốc rồi trở lại theo đường cũ | Mọi nút trên đường cũ trừ gốc | `O(1)` |
| Path halving | Gán cha thành ông/bà, rồi nhảy lên ông/bà | Khoảng mỗi nút thứ hai trên đường được đi | `O(1)` |
| Path splitting | Gán cha thành ông/bà, rồi tới cha cũ | Mọi nút được thăm trên đường cũ trừ gốc | `O(1)` |

**Chú ý:** một phép gán `parent[x] = parent[parent[x]]` có thể gán lại **đúng cùng giá trị** khi cha đã là gốc. Việc code chạy một lệnh ghi không có nghĩa đường cha luôn thay đổi về mặt logic.

### Độ phức tạp một lần gọi

Với độ cao hiện tại `h`:

- `find_basic`: `O(h)` thời gian, `O(1)` bộ nhớ phụ.
- `find_full` lặp hai lượt: `O(h)` thời gian, `O(1)` bộ nhớ phụ.
- `find_halving`: `O(h)` thời gian, `O(1)` bộ nhớ phụ.
- `find_splitting`: `O(h)` thời gian, `O(1)` bộ nhớ phụ.
- `find_full_recursive`: `O(h)` thời gian, **`O(h)` bộ nhớ ngăn xếp** trong trường hợp đi qua h cạnh.

Dù path halving có thể đi qua xấp xỉ một nửa số nút so với đường cũ, nó vẫn có chi phí **`O(h)` cho một lần gọi** theo phân tích độ dài đường. Cải thiện lớn xuất hiện khi xét **nhiều truy vấn trên cùng những cây được cập nhật**.

### Không so sánh thời gian chỉ bằng số phép gán

Full compression đi qua đường hai lượt nhưng tạo đường đi rất ngắn ngay sau lần đầu. Halving thường ít vòng lặp hơn trên đường dài; splitting xử lý nhiều nút của đường cũ hơn, nhưng có thể cải thiện nhiều truy vấn ở các nút khác. Tốc độ thực tế phụ thuộc:

- Độ sâu ban đầu của rừng.
- Thứ tự các lần `find` và `union`.
- Truy cập bộ nhớ, cache, branch prediction.
- Mức tối ưu của trình biên dịch và kiến trúc máy.
- Chi phí gọi hàm/đệ quy và độ lớn tập dữ liệu.

Không có một phép so sánh đơn giản kiểu “splitting luôn nhanh hơn halving” hay “nén đầy đủ luôn nhanh nhất”. Hãy chọn cách **dễ kiểm chứng và phù hợp workload** trước, rồi đo đạc khi thực sự cần.

## 13. Kết hợp với union by size hoặc union by rank

Path compression, halving và splitting chủ yếu **rút ngắn đường sau khi cây đã được tạo**. Nếu `union` luôn nối gốc tùy ý, có thể sinh những cây dài liên tục.

**Union by size** giữ gốc nhóm có số phần tử lớn hơn. **Union by rank** giữ gốc có hạng cao hơn; khi hai rank bằng nhau thì tăng rank gốc mới một đơn vị.

Hai heuristic có tác dụng **chủ động hạn chế chiều cao khi hợp**. Khi chỉ dùng một trong hai, ngay cả khi không nén đường đi, ta đã có:

\[
h=O(\log n).
\]

Khi kết hợp heuristic hợp chuẩn với một biến thể nén đường đi thích hợp, DSU đạt hiệu năng **gần hằng số khấu hao** trên chuỗi thao tác.

### Bảng so sánh bậc độ phức tạp

| Cài đặt | `find`/`union` xấu nhất khi chưa nén | Khi có nén đường và xét chuỗi thao tác |
|---|---|---|
| Nối gốc tùy ý | Có thể `O(n)` | Không tự suy ra chặn Ackermann ngược chuẩn nếu thiếu quy tắc hợp thích hợp |
| Union by size | `O(log n)` | `O(α(n))` khấu hao trong dạng phát biểu quen dùng |
| Union by rank | `O(log n)` | `O(α(n))` khấu hao trong dạng phát biểu quen dùng |

Ở đây `α` là **hàm Ackermann ngược** tăng cực kỳ chậm. Một phát biểu tổng quát cho `n` phần tử, khởi tạo rồi thực hiện `m` thao tác `find`/`union`, thường được viết với tổng chi phí gần:

\[
O\bigl(n+m\,\alpha(n+m)\bigr)
\]

trong cách mô tả đơn giản theo mô hình RAM chuẩn; các kết quả chặt hơn có thể phụ thuộc cả `m` và `n`. Với các biến thể nén tiêu chuẩn và quy tắc hợp theo size/rank, các chặn khấu hao kinh điển có cùng bậc gần tuyến tính.

**Không được hiểu `O(α(n))` khấu hao là mỗi lời gọi `find` chắc chắn mất `O(1)` trong trường hợp xấu.** Một lần truy vấn trước khi đường được nén vẫn có thể đi qua `O(log n)` cạnh ngay cả khi dùng union by size/rank.

### Metadata size/rank sau khi nén

Nén đường, halving và splitting đều chỉ thay cạnh cha **bên trong nhóm**:

- `size[root]` không thay đổi, vì số phần tử nhóm vẫn vậy.
- `rank[root]` không cần thay đổi. Sau khi đường đi bị rút ngắn, rank có thể **lớn hơn chiều cao thực tế** nhưng vẫn là thông tin của heuristic.
- `componentCount` không thay đổi, vì số cây không đổi.

Đừng gán `rank[root]` bằng chiều cao vừa quan sát sau một lần nén; làm vậy sẽ phá quy tắc rank của thuật toán.

## 14. Truy vết rank để thấy nén đường không phải union

Xét một cây hình thành qua union by rank:

```text
        0             rank[0] = 3
       / \
      2   4
     /     \
    3       6
             \
              7
```

Ví dụ đường từ `7` tới gốc có thể là:

```text
7 → 6 → 4 → 0
```

Gọi `find_full(7)` sẽ cho:

```text
parent[7] = 0
parent[6] = 0
parent[4] = 0
```

Nhưng `rank[0]` **không giảm từ 3** chỉ vì đường 7 đã ngắn hơn, và `size[0]` (nếu có) không thay đổi.

### Lỗi rất dễ mắc

```text
find(x):
    ...
    parent[x] = root
    size[root] += 1       // SAI
    rank[root] += 1       // SAI
```

Hai dòng sau làm hỏng metadata:

- Tăng `size` mỗi lần truy vấn sẽ “đếm lại” phần tử đã có.
- Tăng `rank` trong `find` phá quy tắc chỉ tăng khi **union hai gốc có rank bằng nhau**.

Chỉ bản thân đường cha được cập nhật khi nén.

## 15. Kiểm tra tự động: so sánh phân hoạch, không chỉ so mảng cha

Để kiểm tra ba biến thể, ta có thể nhóm các phần tử theo kết quả `find_basic` sau khi nén. Cách này dùng một hàm tìm gốc **không ghi** để quan sát phân hoạch.

```python
def partition(parent: list[int]) -> list[tuple[int, ...]]:
    groups: dict[int, list[int]] = {}

    for x in range(len(parent)):
        root = find_basic(parent, x)
        groups.setdefault(root, []).append(x)

    return sorted(tuple(members) for members in groups.values())


initial = [0, 0, 1, 2, 3, 4, 6, 6]
before = partition(initial)

for algorithm in (find_full, find_halving, find_splitting):
    parent = initial.copy()

    for x in (5, 4, 3, 2, 1, 0, 7, 6):
        algorithm(parent, x)
        assert partition(parent) == before

print(before)  # [(0, 1, 2, 3, 4, 5), (6, 7)]
```

Đây là **kiểm thử bất biến**: sau bất kỳ lần nén nào, mọi thành viên vẫn thuộc nhóm cũ. Nếu chỉ so sánh `parent` trước và sau, phép nén hợp lệ sẽ bị nhầm là “sửa sai dữ liệu” dù phân hoạch không đổi.

### Kiểm thử các trường hợp biên

| Tình huống | Kết quả đúng |
|---|---|
| Miền rỗng `n=0` | Không có phần tử để `find`; mọi chỉ số đều bị từ chối |
| Một phần tử `parent=[0]` | Mọi biến thể trả 0; không đổi rừng |
| Truy vấn ngay tại gốc `x=r` | Trả r, không đi vào vòng lặp |
| Một nút là con trực tiếp của gốc | Trả gốc; phép gán có thể giữ nguyên cha |
| Đường dài | Trả gốc đúng và rút ngắn đường theo biến thể |
| Chỉ số âm hoặc `x=n` | Báo lỗi, không dùng cách đánh chỉ số âm của Python |
| `union(x,x)` | Không nối, không đổi size/count |
| `find` nhiều lần | Mọi lần đều trả cùng gốc nếu không có `union` mới |
| Hai cây khác nhau | Nén trong cây A không chuyển phần tử sang cây B |

Nếu nhận mảng `parent` không đáng tin từ bên ngoài, phải kiểm tra riêng xem các cha hợp lệ và **không có chu trình** trước khi chạy `find` chuẩn.

## 16. Cập nhật cha sai có thể phá cả rừng

Hàm `find` chỉ nên cập nhật cha theo **tổ tiên hợp lệ**. Một số lỗi thường gặp:

### 16.1. Gán cha bằng một nút ở cây khác

```text
Cây A: 0 ← 1 ← 2
Cây B: 3 ← 4

Sai trong find(2):
parent[2] = 3
```

Nút 2 bị chuyển khỏi nhóm A sang nhóm B dù **không có phép union**. Bất biến phân hoạch và dữ liệu metadata có thể sai.

### 16.2. Gán cha về hậu duệ

```text
parent[0] = 0
parent[1] = 0

Sai:
parent[0] = 1
```

Ta tạo chu trình `0→1→0`. Lúc này `find` không dừng.

### 16.3. Bỏ quên cha cũ trong full compression

```text
// Sai khi muốn nén TẤT CẢ các nút trên đường cũ:
while parent[x] != x:
    parent[x] = root
    x = parent[x]
```

Sau lần gán đầu, `x` nhảy thẳng tới gốc. Những nút trung gian vẫn giữ cha cũ. Để **nén đầy đủ**, phải lưu `old_parent` trước khi ghi.

### 16.4. Nhầm thứ tự trong path splitting

```text
// Muốn splitting nhưng thực tế đang đi theo cha MỚI:
parent[x] = parent[parent[x]]
x = parent[x]
```

Đây là **path halving**, không phải splitting. Để splitting, lưu `old_parent` trước, cập nhật rồi đi tới `old_parent`.

### 16.5. Cập nhật `parent[root]` tùy tiện

Gốc phải tự trỏ trừ khi nó đang **trở thành nút con trong một phép union hợp lệ với gốc khác**. Trong `find` của chính nhóm đó, không được đổi gốc sang một nút không được bảo đảm là gốc cùng nhóm.

## 17. Cẩn trọng với vùng nhớ, đệ quy và đồng thời

### 17.1. Đệ quy có thể gây tràn ngăn xếp

Đoạn `find_full_recursive` ngắn nhưng có thể sinh **h` lời gọi lồng nhau khi đường cha dài `h`. Với rừng xấu chưa được tối ưu, `h` có thể lớn. Giải pháp lặp hai lượt, halving hoặc splitting dùng **`O(1)` bộ nhớ phụ**, nên hữu ích khi muốn tránh phụ thuộc giới hạn stack.

### 17.2. Path compression làm `find` thành thao tác ghi

Trong một DSU đơn luồng, việc `find` âm thầm tối ưu cây là bình thường. Nhưng nếu nhiều luồng cùng truy vấn:

- Hai `find` có nén có thể **cùng ghi** vào một số ô `parent`.
- `find` có thể đọc trong lúc `union` sửa con trỏ gốc.
- Mã đọc/ghi mảng thường **không có bảo đảm atomic hoặc đồng bộ** mặc định.

Đặc biệt trong C++, truy cập đồng thời tới cùng vùng nhớ mà ít nhất một bên ghi và không đồng bộ đúng có thể tạo **data race** và hành vi không xác định. Không thể suy rằng “các phép ghi chỉ làm ngắn đường nên không cần khóa”.

Có thể chọn một trong các cách:

- Dùng khóa thích hợp bao quanh các thao tác DSU.
- Chia dữ liệu thành các DSU riêng rồi hợp kết quả theo một giai đoạn xác định.
- Dùng **concurrent Union–Find** chuyên dụng với các thao tác atomic và lập luận tính đúng đắn phù hợp.

Chọn cách nào còn tùy tần suất cập nhật và yêu cầu hiệu năng; mã ví dụ ở đây là **đơn luồng**.

### 17.3. Quan sát mảng `parent` khi đang bị sửa

Nếu thành phần khác đang đọc toàn bộ `parent` để lập báo cáo, nó có thể nhìn thấy **một trạng thái đang nén dở** hoặc đang hợp dở nếu không đồng bộ. Dù trạng thái sau cùng hợp lệ, người quan sát không được giả định nhiều lần đọc rời rạc tạo một snapshot nhất quán.

### 17.4. Định danh gốc có thể thay đổi bởi union

Nén đường **không tự đổi gốc hiện tại**, nhưng một lần `union` với quy tắc size/rank có thể chọn gốc khác làm đại diện. Vì vậy **giá trị `find(x)` không phải ID nhóm nghiệp vụ bền vững**. Nếu cần mã nhóm cố định, phải duy trì cơ chế định danh riêng.

## 18. Khi nào nên dùng biến thể nào?

| Yêu cầu | Cách nên cân nhắc | Giải thích |
|---|---|---|
| Ưu tiên dễ hiểu từng thay đổi của đường cha | **Full compression hai lượt** | Thuật toán tìm gốc rồi nối thẳng các nút về gốc |
| Muốn mã lặp ngắn, chỉ một lượt | **Path halving** | Mỗi vòng nhảy lên ông/bà |
| Muốn cập nhật từng nút đã duyệt trên đường cũ trong một lượt | **Path splitting** | Dùng cha cũ làm điểm di chuyển |
| Tránh dùng ngăn xếp đệ quy | Cả ba phiên bản **lặp** | Chỉ cần `O(1)` biến tạm |
| Nhiều `find` và `union` trên tập lớn | Một biến thể nén + **union by size/rank** | Chi phí rất nhỏ theo khấu hao |
| Cần đọc được số phần tử nhóm | Union by **size** và `size[find(x)]` | Rank không thay cho size |
| Cần một truy vấn đúng nghĩa chỉ đọc `parent` | `find_basic` hoặc thiết kế riêng | Biến thể nén đều có thể ghi |
| Có nhiều luồng | Đồng bộ hoặc concurrent DSU | Nén và union có thể ghi chung |

Không cần cùng lúc áp dụng **full compression, halving và splitting trên một lần `find`**. Chọn **một chiến lược nhất quán** là đủ. Các biến thể này đều là những cách thực hiện cùng một ý tưởng **rút ngắn đường cha**.

## 19. Ứng dụng trong duyệt đồ thị và Kruskal

DSU thường dùng để duy trì **thành phần liên thông của đồ thị vô hướng khi thêm cạnh**:

```text
initialize(n): tạo n nhóm đơn

add_edge(u, v):
    union(u, v)

connected(u, v):
    return find(u) == find(v)
```

Mỗi lần `find` trong các thao tác trên có thể rút ngắn đường cha theo một trong ba biến thể, khiến những lần tìm về sau nhanh hơn.

### Kruskal và phát hiện cạnh tạo chu trình

Khi đang xây một rừng cạnh được chấp nhận:

```text
for each edge (u, v) theo trọng số tăng dần:
    if find(u) != find(v):
        chọn cạnh (u, v)
        union(u, v)
    else:
        bỏ qua cạnh vì nó sẽ tạo chu trình trong rừng
```

Union by size/rank kết hợp path compression giúp giảm chi phí xử lý nhiều cạnh. Tuy nhiên, tổng thời gian Kruskal còn có bước **sắp xếp cạnh**, thường mất `O(E log E)` với thuật toán so sánh thông dụng, không phải chỉ có chi phí DSU.

### Không dùng DSU như một cây đường đi thật

Rừng cha của DSU **không nhất thiết tương ứng với các cạnh đồ thị gốc**, nhất là sau khi path compression đổi liên kết cha. Vì thế, nó chỉ trả lời “hai đỉnh có cùng thành phần không?”, không trả về **đường đi cụ thể**. Nếu cần đường đi, BFS/DFS trên cấu trúc đồ thị là công cụ phù hợp.

DSU chuẩn cũng không tự hỗ trợ **xóa cạnh** làm hai thành phần tách ra. Những biến thể nén chỉ tối ưu `find`, **không bổ sung thao tác split**.

## 20. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Coi `parent[x]` luôn là đại diện của x | Có thể chỉ là cha trung gian | Dùng `find(x)` |
| Full compression quên lưu cha cũ | Chỉ nén nút đầu, bỏ nút trung gian | Lưu `old_parent` rồi mới ghi |
| Path splitting đi tới cha mới | Trở thành halving, không còn đúng biến thể định triển khai | Di chuyển đến `old_parent` |
| Cập nhật cha tới nút ngoài cây | Đổi nhóm mà không union | Chỉ trỏ tới tổ tiên cùng cây |
| Gán gốc vào hậu duệ | Tạo chu trình, `find` không kết thúc | Giữ gốc tự trỏ, trừ khi union hai gốc khác nhau |
| `find` tăng `size` | Đếm trùng thành viên | Chỉ cập nhật size khi union thành công |
| `find` tăng hoặc giảm `rank` | Phá quy tắc union by rank | Chỉ union hai gốc rank bằng mới tăng rank |
| Tưởng nén đường luôn `O(1)` worst-case | Phân tích sai chi phí lần đầu | Tính `O(h)` cho một lần gọi |
| Tưởng halving/splitting nén thẳng mọi nút về gốc | Sai cấu trúc sau một lần gọi | Dùng bảng truy vết theo đúng biến thể |
| Tin rằng `find` có nén là truy vấn chỉ đọc | Dễ có data race khi dùng chung | Đồng bộ hoặc concurrent DSU |
| Không kiểm tra chỉ số âm trong Python | Truy cập cuối list ngoài ý nghĩa DSU | Kiểm tra `0≤x<n` |
| Dùng `find` trên mảng đã có chu trình | Vòng lặp vô hạn | Kiểm tra cấu trúc trước nếu nguồn không đáng tin |
| Đòi các biến thể có cùng `parent` sau tìm | Đánh trượt triển khai đúng | So sánh gốc, phân hoạch và bất biến |

## 21. Bài tập tự kiểm tra có lời giải

**Câu 1.** Với `parent=[0,0,1,2,3,4]`, `find_basic(5)` trả gì và có sửa mảng không?

**Đáp án:** Trả **0**, đi qua đường `5→4→3→2→1→0`. Phiên bản cơ bản không sửa mảng cha.

**Câu 2.** Trên cùng mảng, sau `find_full(5)` dạng nén đầy đủ, giá trị `parent` là gì?

**Đáp án:** `[0,0,0,0,0,0]`, vì mọi nút trên đường cũ từ 5 tới trước gốc đều được cho trỏ trực tiếp tới 0.

**Câu 3.** Sau một lần `find_halving(5)` với cùng mảng ban đầu, mảng nào đúng?

**Đáp án:** `[0,0,1,1,3,3]`. Thuật toán sửa lần lượt `parent[5]=3`, `parent[3]=1` và `parent[1]=0`.

**Câu 4.** Sau một lần `find_splitting(5)` với mảng ban đầu, mảng nào đúng?

**Đáp án:** `[0,0,0,1,2,3]`. Thuật toán sửa cha của các nút 5, 4, 3, 2 và 1 theo ông/bà, luôn di chuyển tới **cha cũ**.

**Câu 5.** Điểm khác quan trọng giữa halving và splitting nằm ở đâu?

**Đáp án:** Cả hai đều cập nhật cha thành ông/bà. Halving di chuyển tới **ông/bà mới** (`x=parent[x]` sau cập nhật), còn splitting di chuyển tới **cha cũ** (`x=old_parent`).

**Câu 6.** Full compression dạng lặp hai lượt phải lưu biến nào trước khi gán `parent[x]=root`?

**Đáp án:** Phải lưu **`old_parent=parent[x]`**. Nhờ đó vòng thứ hai tiếp tục đi qua đường cũ thay vì nhảy thẳng tới gốc sau phép gán.

**Câu 7.** Tại sao các phép nén, halving và splitting không thay đổi số nhóm?

**Đáp án:** Chúng chỉ đổi cha của một nút thành **tổ tiên trong cùng cây**. Mọi nút vẫn tới cùng gốc như trước, nên phân hoạch và số gốc giữ nguyên.

**Câu 8.** Có nên cộng `size[root]` khi `find(x)` sửa cha của x thành root không?

**Đáp án:** Không. x đã là thành viên của nhóm đó từ trước. Cộng size sẽ đếm trùng. `size` chỉ thay đổi khi `union` hợp **hai nhóm khác nhau**.

**Câu 9.** Có nên giảm `rank[root]` khi path compression làm chiều cao thực tế giảm không?

**Đáp án:** Không. Rank được duy trì theo quy tắc union by rank; sau nén, nó có thể là **chặn trên** chứ không bằng chiều cao hiện tại.

**Câu 10.** Với đường cha dài `h`, một lần `find_halving` hoặc `find_splitting` có thời gian `O(1)` không?

**Đáp án:** Không. Cả hai có chi phí **`O(h)`** ở một lần gọi, dù thường làm đường ngắn đi. Lợi ích lớn thể hiện khi xét nhiều truy vấn tiếp theo.

**Câu 11.** Nếu dùng full compression đệ quy, bộ nhớ ngăn xếp phụ có thể lên tới bao nhiêu?

**Đáp án:** **`O(h)`**, với `h` là độ dài đường cha sâu nhất được duyệt. Bản lặp hai lượt dùng **`O(1)` bộ nhớ phụ**.

**Câu 12.** Kết hợp union by size với path compression thường có độ phức tạp khấu hao nào?

**Đáp án:** Gần **`O(α(n))` trên mỗi thao tác** theo phát biểu thường dùng cho chuỗi thao tác; `α` là hàm Ackermann ngược. Đây không phải chặn `O(1)` worst-case cho mỗi lần gọi.

**Câu 13.** Một rừng có `parent[0]=1` và `parent[1]=0`. Có thể chạy `find` thường để chờ tự nén hết chu trình không?

**Đáp án:** Không. Đây là chu trình `0→1→0` không có gốc; các hàm `find` chuẩn có thể không dừng. Phải kiểm tra và sửa cấu trúc trước.

**Câu 14.** Tại sao không thể lấy `parent[x]` sau path compression làm cạnh của đồ thị đầu vào?

**Đáp án:** Liên kết cha chỉ là **liên kết đại diện nội bộ** và có thể bị thay đổi khi tìm gốc. Nó không nhất thiết là cạnh thật giữa hai đỉnh của đồ thị.

**Câu 15.** Trong C++, hai luồng cùng gọi `find` có compression trên một DSU thông thường không khóa có luôn an toàn không?

**Đáp án:** Không. `find` có thể ghi vào cùng các ô `parent`, gây **data race** khi thiếu đồng bộ. Cần khóa hoặc thuật toán concurrent Union–Find được thiết kế đúng.

**Câu 16.** Một DSU có `n=8` gồm hai nhóm `{0,1,2,3,4,5}` và `{6,7}`. Sau khi chạy `find_splitting(5)`, có thể `find(7)` trở thành 0 không?

**Đáp án:** Không. Splitting chỉ cập nhật các liên kết trong cây chứa 5, giữ nguyên phân hoạch. Gốc của 7 vẫn là 6 nếu không có `union` nối hai nhóm.

**Câu 17.** Nếu hai phiên bản `find` cho ra mảng `parent` khác nhau nhưng mọi cặp phần tử có cùng trạng thái `same(x,y)`, có chắc một phiên bản sai không?

**Đáp án:** Không. Nhiều rừng khác nhau có thể biểu diễn **cùng phân hoạch**. Cần kiểm tra thêm không có chu trình, mọi cha hợp lệ, đại diện đúng, metadata gốc nhất quán và các yêu cầu cụ thể của biến thể.

## Ghi nhớ

- **Full path compression** tìm gốc rồi cho **mọi nút trên đường cũ** trỏ trực tiếp về gốc; khi viết dạng lặp hai lượt phải lưu **cha cũ** trước khi cập nhật.
- **Path halving** cho nút hiện tại trỏ tới **ông/bà**, sau đó **nhảy tới ông/bà**. **Path splitting** cũng trỏ tới ông/bà nhưng **tiếp tục từ cha cũ**.
- Các cập nhật cha hợp lệ chỉ **đi tắt theo tổ tiên trong cùng cây**, nên không thay đổi gốc, thành viên nhóm, `size[root]` hay `componentCount`.
- Một lần `find` trên đường cao `h` vẫn có chi phí **`O(h)`**; bản lặp dùng **`O(1)` bộ nhớ phụ**, còn bản đệ quy có thể dùng **`O(h)` ngăn xếp**.
- **Union by size/rank** chủ động giữ cây thấp; kết hợp các biến thể nén đường giúp Union–Find có hiệu năng gần hằng số **khấu hao**, thường biểu diễn qua hàm `α(n)`.
- Khi kiểm thử, so sánh **phân hoạch và bất biến**, không đòi mảng cha của các biến thể giống nhau. Không dùng `find` có nén trên cấu trúc dùng chung nhiều luồng mà thiếu đồng bộ, và không coi rừng cha là các cạnh thật của đồ thị.
