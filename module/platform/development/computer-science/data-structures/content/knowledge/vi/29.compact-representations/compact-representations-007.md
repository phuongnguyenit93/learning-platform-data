# Biểu diễn cây theo tầng LOUDS ở mức nguyên lý

## 1. Bài toán và mục tiêu học tập

Trong các cấu trúc cây thông thường, mỗi nút thường chứa con trỏ đến các nút con, danh sách con hoặc con trỏ đến nút cha. Cách này thuận tiện khi cập nhật cây, nhưng có thể tốn nhiều bộ nhớ cho địa chỉ, thông tin cấp phát và các đối tượng nhỏ. Khi cần lưu một cây lớn, ít thay đổi (ví dụ trie từ điển, cây phân loại hay chỉ mục tĩnh), ta có thể muốn **lưu hình dạng cây bằng bit**, đồng thời vẫn tìm được cha và các con.

**LOUDS** là viết tắt của *Level-Order Unary Degree Sequence*: biểu diễn số con của từng nút theo **thứ tự duyệt theo tầng** (breadth-first search, BFS), dùng mã unary. Nó thuộc nhóm *succinct data structures* — các cấu trúc hỗ trợ truy vấn trên biểu diễn rất gọn.

Sau bài này, người học có thể:

- Tự mã hóa hình dạng một cây có gốc, với thứ tự các con được xác định, thành dãy bit LOUDS.
- Giải thích được vì sao một cây có `n` nút cần đúng `2n - 1` bit trong quy ước cơ bản dùng ở đây.
- Tính số con, tìm các con và cha bằng thao tác `rank`/`select` trên dãy bit.
- Phân biệt chi phí lưu **hình dạng cây** với chi phí lưu nhãn, dữ liệu nút và chỉ mục truy vấn.
- Nhận ra tình huống phù hợp và các giới hạn của LOUDS so với cây dùng con trỏ.

> Phạm vi: giải thích nguyên lý của LOUDS cho **một cây có gốc, các con có thứ tự, không rỗng và chủ yếu được đọc**. Chưa đi vào các biến thể tối ưu hóa bit-vector hay thuật toán cập nhật động.

## 2. Ý tưởng mã hóa: BFS + số con bằng mã unary

Giả sử duyệt các nút bằng BFS từ gốc; với mỗi nút có `d` con, ghi:

```text
1 lặp d lần, sau đó 0
```

Ví dụ:

| Số con `d` | Đoạn bit của nút | Ý nghĩa |
|---:|:---:|---|
| 0 | `0` | Nút lá |
| 1 | `10` | Một con |
| 2 | `110` | Hai con |
| 3 | `1110` | Ba con |

Ghép nối các đoạn bit theo đúng thứ tự BFS. **Bit `1` biểu diễn một cạnh từ nút đang xét đến một nút con; bit `0` kết thúc danh sách con của nút đó.** Không cần ghi địa chỉ nút con: thứ tự các bit `1` quyết định thứ tự xuất hiện của các nút con trong BFS.

### Ví dụ xuyên suốt

Xét cây có thứ tự con từ trái sang phải:

```text
        A
      / | \
     B  C  D
    / \     \
   E   F     G
```

BFS lần lượt đi qua `A, B, C, D, E, F, G`. Đánh số nút từ `1` theo thứ tự này:

| Số nút (BFS) | Nhãn | Các con | Bậc ra `d` | Đoạn LOUDS | Vị trí bit (đánh từ 1) |
|---:|:---:|:---|---:|:---:|:---:|
| 1 | A | B, C, D | 3 | `1110` | 1–4 |
| 2 | B | E, F | 2 | `110` | 5–7 |
| 3 | C | Không có | 0 | `0` | 8 |
| 4 | D | G | 1 | `10` | 9–10 |
| 5 | E | Không có | 0 | `0` | 11 |
| 6 | F | Không có | 0 | `0` | 12 |
| 7 | G | Không có | 0 | `0` | 13 |

Đặt các đoạn cạnh nhau:

```text
Nút:     A    B   C  D  E F G
Đoạn:   1110 110  0 10  0 0 0
LOUDS:  1110110010000

Vị trí:  1 2 3 4 5 6 7 8 9 10 11 12 13
Bit:     1 1 1 0 1 1 0 0 1  0  0  0  0
```

Dãy `1110110010000` có **6 bit `1`** (ứng với 6 cạnh) và **7 bit `0`** (mỗi nút kết thúc bằng một `0`). Do cây có `n` nút luôn có `n - 1` cạnh, tổng độ dài là:

\[
(n - 1) + n = 2n - 1 \text{ bit}.
\]

Với cây chỉ có một nút gốc, dãy LOUDS là `0`. Với cây rỗng, phải quy ước biểu diễn riêng (chẳng hạn dãy rỗng và lưu thêm trạng thái “không có gốc”).

**Điểm cần nhớ:** dãy bit chỉ mô tả **hình dạng và thứ tự các con**. Nó không tự lưu các nhãn `A`, `B`, ... hoặc giá trị của nút. Nếu cần nhãn, có thể lưu thêm mảng nhãn theo đúng thứ tự BFS: `[A, B, C, D, E, F, G]`.

## 3. Vì sao dãy bit có thể khôi phục được cây?

Hãy hình dung một hàng đợi BFS chứa gốc chưa xử lý.

1. Lấy nút ở đầu hàng đợi.
2. Đọc liên tiếp các bit `1` của nút đó: mỗi `1` tạo một nút con mới, gắn vào nút hiện tại và thêm vào cuối hàng đợi, theo thứ tự đọc.
3. Gặp `0` thì kết thúc danh sách con, chuyển sang nút tiếp theo trong hàng đợi.
4. Tiếp tục đến khi hết dãy bit và hàng đợi trống.

Trong ví dụ, `1110` cho biết gốc có ba con mới `B, C, D`; ngay sau đó `110` cho biết `B` có hai con `E, F`; `0` cho biết `C` không có con; `10` cho biết `D` có một con `G`. Các đoạn còn lại là những nút lá.

Một cách kiểm tra tính hợp lệ của dãy LOUDS cho **một cây không rỗng** là: số bit `0` phải hơn số bit `1` đúng một, và ở mọi tiền tố chưa kết thúc, số bit `0` không được vượt số bit `1`. Lý do là số nút đã được tạo nhưng chưa xử lý sau một tiền tố bằng:

\[
1 + \#1 - \#0.
\]

Đại lượng này phải dương trước khi kết thúc và bằng `0` ở cuối. Đây là điều kiện kiểm tra *hình dạng mã hóa*, còn nhãn hoặc nội dung nút vẫn là dữ liệu riêng.

## 4. Điều hướng bằng rank và select

Để không phải giải mã lại từ đầu mỗi lần truy vấn, LOUDS thường đi cùng hai phép toán trên dãy bit `S`. Trong bài này, **vị trí bit và số thứ tự nút đều bắt đầu từ 1**:

- `rank_b(i)`: số bit mang giá trị `b` trong `S[1..i]`, tính cả vị trí `i`. Quy ước `rank_b(0) = 0`.
- `select_b(k)`: vị trí của bit mang giá trị `b` thứ `k` trong `S`, với `k \ge 1`.

Ví dụ trên `S = 1110110010000`:

- `select_0(1) = 4`; `select_0(2) = 7`; `select_0(4) = 10`.
- `select_1(1) = 1`; `select_1(4) = 5`; `select_1(6) = 9`.
- `rank_1(7) = 5`; `rank_0(9) = 3`.

Mỗi bit `0` đóng một đoạn của một nút, nên **bit `0` thứ `v` ứng với nút BFS số `v`**. Mỗi bit `1` phát sinh một nút con, nên **bit `1` thứ `k` ứng với nút BFS số `k + 1`** (gốc không phải là con của ai).

Để viết công thức thống nhất cho cả gốc, ta quy ước thêm `select_0(0) = 0` như một ranh giới *giả* đứng trước dãy bit. Đây không phải là bit `0` thực có trong dãy.

### 4.1. Số con của nút `v`

Đoạn của nút `v` nằm ngay sau bit `0` kết thúc nút `v - 1` và kết thúc tại bit `0` thứ `v`:

\[
L = select_0(v - 1) + 1,\qquad R = select_0(v).
\]

Giữa `L` và `R - 1` chỉ có bit `1`, do đó:

\[
degree(v) = select_0(v) - select_0(v - 1) - 1.
\]

Ví dụ nút `B` có số BFS `v=2`: `select_0(2)=7`, `select_0(1)=4`; vậy `degree(2)=7-4-1=2`.

### 4.2. Liệt kê các con của nút `v`

Nếu `degree(v)=0` thì nút không có con. Nếu có con, các nút con của cùng một cha được **đánh số BFS liên tiếp** (vì được đưa vào cuối hàng đợi cùng lúc). Nút con đầu tiên có số:

\[
firstChild(v) = rank_1(select_0(v-1)) + 2.
\]

Các con của `v` là các nút có số thứ tự:

\[
firstChild(v),\ firstChild(v)+1,\ \ldots,\ firstChild(v)+degree(v)-1.
\]

Giải thích hằng số `+2`: `rank_1` tại ranh giới trước đoạn cho biết đã tạo bao nhiêu nút *con* trước đó; số BFS của nút con mới kế tiếp bằng số ấy cộng `2`, vì nút số `1` là gốc.

Ví dụ:

- Với `A` (`v=1`): `rank_1(0)=0` nên con đầu tiên là nút `2`; có 3 con: `2,3,4` = `B,C,D`.
- Với `B` (`v=2`): `rank_1(4)=3` nên con đầu tiên là nút `5`; có 2 con: `5,6` = `E,F`.
- Với `D` (`v=4`): `rank_1(8)=5` nên con đầu tiên là nút `7` = `G`.
- Với `C` (`v=3`): `degree(3)=0`, nên không gọi công thức tìm con để coi một số nút bất kỳ là con.

### 4.3. Tìm cha của nút `v`

Gốc `v=1` không có cha. Với `v \ge 2`, nút đó được tạo bởi **bit `1` thứ `v-1`**. Gọi `p = select_1(v - 1)` là vị trí bit này. Số bit `0` trước `p` chính là số nút đã xử lý xong trước khi tạo ra `v`, nên cha của `v` có số BFS:

\[
parent(v) = rank_0(select_1(v-1)) + 1,\qquad v\ge 2.
\]

Ví dụ để tìm cha của `G` (`v=7`), lấy `select_1(6)=9`; trước hoặc tại vị trí `9` có 3 bit `0`, nên `parent(7)=3+1=4` = `D`.

Tương tự, `E` có `v=5`: `select_1(4)=5`, `rank_0(5)=1`, nên `parent(5)=2` = `B`.

Vì `rank_0(p)=p-rank_1(p)`, có thể dùng một chỉ mục `rank_1` để tính `rank_0` nếu cần.

### Tóm tắt các truy vấn

| Truy vấn | Công thức trong quy ước bài này | Lưu ý |
|---|---|---|
| Số con của `v` | `select_0(v)-select_0(v-1)-1` | `select_0(0)=0` |
| Con đầu tiên | `rank_1(select_0(v-1))+2` | Chỉ khi số con lớn hơn 0 |
| Toàn bộ con | `firstChild(v)` đến `firstChild(v)+degree(v)-1` | Khoảng số BFS liên tiếp |
| Cha của `v` | `rank_0(select_1(v-1))+1` | Chỉ với `v>1` |

**Chú ý quy ước:** một số tài liệu thêm *gốc giả* hoặc một tiền tố bit đặc biệt, hoặc đánh số từ `0`. Khi đó độ dài bit và công thức dịch chỉ số sẽ khác. Không nên trộn công thức của các biến thể nếu chưa xác định rõ quy ước mã hóa.

## 5. Cài đặt Python minh họa

Đoạn chương trình sau nhận **danh sách số con theo BFS**, dựng LOUDS và hỗ trợ các truy vấn trên. Để dễ kiểm chứng, mã dùng mảng chứa vị trí các bit `0`/`1` và mảng tổng tích lũy `rank_1`. Đây là **bản minh họa thuật toán**, chưa phải cài đặt tiết kiệm bit để dùng trong sản phẩm.

~~~python
class SimpleLOUDS:
    def __init__(self, degrees):
        # Các bậc phải mô tả chính xác một cây không rỗng
        # theo thứ tự BFS.
        if not degrees or any(type(d) is not int or d < 0 for d in degrees):
            raise ValueError("Cần danh sách số con nguyên, không âm")

        pending = 1  # Ban đầu có một gốc chưa được xử lý
        for degree in degrees:
            if pending == 0:
                raise ValueError("Có nút xuất hiện sau khi cây đã kết thúc")
            pending += degree - 1
        if pending != 0:
            raise ValueError("Số con không tạo thành một cây hoàn chỉnh")

        self.n = len(degrees)
        self.bits = "".join("1" * d + "0" for d in degrees)

        # Số 0 đầu tiên là lính canh cho select_0(0).
        # Tương tự, phần tử đầu của ones chỉ để đánh số từ 1.
        self.zeros = [0]
        self.ones = [0]
        self.rank1 = [0]  # rank1[p]: số bit 1 trong S[1..p]

        for pos, bit in enumerate(self.bits, start=1):
            self.rank1.append(self.rank1[-1] + (bit == "1"))
            if bit == "0":
                self.zeros.append(pos)
            else:
                self.ones.append(pos)

    def _check_node(self, v):
        if not 1 <= v <= self.n:
            raise IndexError("Số nút nằm ngoài phạm vi BFS")

    def degree(self, v):
        self._check_node(v)
        return self.zeros[v] - self.zeros[v - 1] - 1

    def children(self, v):
        self._check_node(v)
        count = self.degree(v)
        first = self.rank1[self.zeros[v - 1]] + 2
        return list(range(first, first + count))

    def parent(self, v):
        self._check_node(v)
        if v == 1:
            return None
        p = self.ones[v - 1]         # select_1(v - 1)
        rank0 = p - self.rank1[p]
        return rank0 + 1


tree = SimpleLOUDS([3, 2, 0, 1, 0, 0, 0])
names = ["A", "B", "C", "D", "E", "F", "G"]

print(tree.bits)                     # 1110110010000
print(tree.degree(2))                # 2 (B có hai con)
print(tree.children(2))              # [5, 6] (E và F)
print(tree.parent(7))                # 4 (cha G là D)
print([names[v - 1] for v in tree.children(1)])
# ['B', 'C', 'D']
~~~

Dãy `degrees` trong chương trình phải là số con **đã biết theo BFS**, chẳng hạn được tạo từ một lần duyệt cây đầu vào. Việc kiểm tra biến `pending` bảo đảm không sinh nút sau khi hàng đợi đã rỗng và sau khi đọc hết phải xử lý đủ số nút. Với dữ liệu xây dựng không hợp lệ, chương trình báo lỗi.

Trong mã này, truy vấn `degree` và `parent` có thời gian `O(1)` nhờ những **mảng phụ tuyến tính theo số nút**, còn `children` cần `O(d)` thời gian để xuất ra `d` con. Các mảng Python dùng nhiều byte trên mỗi phần tử, vì vậy **không thể lấy kích thước bộ nhớ của chương trình minh họa làm chi phí của LOUDS succinct**.

## 6. Không gian lưu trữ và thời gian truy vấn

Cần tách hai lớp:

1. **Chuỗi LOUDS thô:** một cây `n` nút có đúng `2n - 1` bit cho cấu trúc trong quy ước này, không tính dữ liệu của nút.
2. **Cấu trúc hỗ trợ truy vấn:** muốn tính `rank` và `select` nhanh mà không quét toàn bộ chuỗi, thường cần thêm một chỉ mục trên bit-vector.

Trong lý thuyết cấu trúc dữ liệu gọn, có thể hỗ trợ `rank/select` trong thời gian hằng số với phần phụ trợ `o(n)` bit trên bit-vector, theo những mô hình tính toán và giả thiết phù hợp. Khi đó **hình dạng cây và chỉ mục** chiếm `2n + o(n)` bit (bỏ qua hằng số âm một bit). Cài đặt thực tế có thể chọn chỉ mục khác để đổi thêm bộ nhớ lấy tốc độ.

| Phép toán / thành phần | Chi phí điển hình |
|---|---|
| Chuỗi bit hình dạng cây | `2n - 1` bit |
| Dựng chuỗi từ số con BFS | `O(n)` thời gian |
| `degree(v)` | `O(1)` nếu `select` nhanh |
| `firstChild(v)` | `O(1)` nếu `rank/select` nhanh |
| `parent(v)` | `O(1)` nếu `rank/select` nhanh |
| Liệt kê tất cả `d` con | `O(d)` thời gian để xuất kết quả |
| Dùng cách quét tuyến tính thay `rank/select` | Có thể tốn `O(n)` mỗi truy vấn |
| Nhãn, trọng số, dữ liệu nút | Lưu riêng, phụ thuộc kiểu dữ liệu |

Bảng nói về **mô hình truy vấn trên cấu trúc đã xây xong**; không ngụ ý rằng các bảng `rank/select` ngây thơ như trong Python sử dụng `o(n)` bit. Nếu lưu từng vị trí bit dưới dạng số nguyên máy, riêng các bảng vị trí đã tiêu tốn `O(n)` *từ máy*.

Ví dụ, một cây một triệu nút chỉ cần `1.999.999` bit cho chuỗi LOUDS thô, tức xấp xỉ `250.000` byte (tính theo 8 bit/byte), trước khi tính chỉ mục truy vấn, nhãn và chi phí đóng gói. Đó là lợi thế tiềm năng khi so với việc cấp phát một triệu đối tượng nút kèm các con trỏ.

## 7. LOUDS phù hợp khi nào?

LOUDS đặc biệt phù hợp khi:

- Cây **lớn, gần như bất biến** và cần giảm chi phí bộ nhớ cho liên kết giữa các nút.
- Ứng dụng cần nhiều phép tìm **cha, số con, các con**, ví dụ các chỉ mục từ vựng/trie tĩnh hoặc cấu trúc phân cấp đã được xây dựng.
- Dữ liệu dạng bit-vector liên tục thuận tiện cho lưu trữ tuần tự, nạp từ tệp hoặc xử lý với cache hiệu quả hơn nhiều đối tượng rải rác trong bộ nhớ.

Tuy nhiên cũng có các giới hạn:

- **Chèn/xóa và thay đổi cấu trúc cây** có thể buộc sửa nhiều vị trí bit, dịch các chỉ số BFS và cập nhật các cấu trúc `rank/select`. Cây con trỏ thường thuận lợi hơn khi cần sửa liên tục.
- **Toàn bộ hậu duệ của một nút không nhất thiết tạo thành một đoạn BFS liên tiếp.** Chỉ các *con trực tiếp* của một nút được đánh số liền nhau. Vì vậy truy vấn cây con, duyệt DFS hoặc thao tác theo khoảng cây con có thể cần cấu trúc bổ sung; các biểu diễn theo thứ tự ngoặc cân bằng (*balanced parentheses*) thường được cân nhắc cho nhóm tác vụ này.
- LOUDS không mang theo nhãn hay giá trị của nút. Nếu cần tra con theo một ký tự bất kỳ, chỉ biết danh sách các con là chưa đủ: phải có cách lưu và tra **nhãn cạnh/nút** theo thứ tự tương ứng.
- Kích thước cuối cùng phụ thuộc phần mềm triển khai bit-vector, chỉ mục và cách lưu dữ liệu đi kèm; không nên đồng nhất `2n - 1` bit lý thuyết với tổng RAM ứng dụng.

### So với cây con trỏ

| Tiêu chí | Cây con trỏ/danh sách con | LOUDS trên bit-vector |
|---|---|---|
| Lưu liên kết | Địa chỉ hoặc danh sách con tại mỗi nút | Mã unary bậc nút theo BFS |
| Bộ nhớ cho hình dạng | Thường nhiều byte cho mỗi liên kết/đối tượng | `2n - 1` bit thô, cộng chỉ mục |
| Tìm cha/con | Phụ thuộc các con trỏ được lưu | Dựa trên `rank/select` |
| Sửa cấu trúc | Thường dễ ở phạm vi nút liên quan | Phức tạp vì thay đổi thứ tự/bit |
| Dữ liệu nút | Thường nằm trong đối tượng nút | Nên lưu ở mảng hoặc lớp dữ liệu riêng |

## 8. Các lỗi dễ gặp khi học và cài đặt

1. **Nhầm BFS với DFS:** LOUDS mã hóa các đoạn theo tầng. Nếu dùng bậc nút theo DFS thì các công thức cha/con phía trên không còn đúng.
2. **Nhầm `1` là một nút:** theo quy ước đã chọn, `1` đại diện cho một nút **con được sinh ra** hay một cạnh; `0` kết thúc một nút được duyệt.
3. **Quên nút lá:** nút lá vẫn phải có một bit `0`; nếu bỏ qua, các ranh giới nút bị lệch.
4. **Nhầm chỉ số bit và chỉ số nút:** vị trí `select_1` là một vị trí trong chuỗi; số nút con bằng thứ tự xuất hiện bit `1` cộng 1.
5. **Gọi `firstChild` ở nút lá rồi xem kết quả là con:** luôn kiểm tra `degree(v)>0` trước khi sử dụng kết quả.
6. **Trộn quy ước gốc giả hoặc đánh số từ 0:** khi đọc công thức của nguồn khác, cần xác định bit tiền tố và các quy tắc `rank/select`.
7. **Cho rằng cài đặt dùng mảng số nguyên là succinct:** công thức có thể đúng và nhanh nhưng muốn tiết kiệm bit thực sự phải dùng bit-vector và chỉ mục `rank/select` được thiết kế phù hợp.

## 9. Tự luyện tập và đối chiếu

**Bài 1.** Cây gồm ba nút dạng chuỗi `A → B → C`, trong đó `A` là gốc. Viết dãy LOUDS, số bit `1` và số bit `0`.

**Bài 2.** Với chuỗi `S=1110110010000` trong ví dụ, hãy tìm `degree(4)`, các con của nút `4` và cha của nút `6`. Đừng nhìn hình cây khi tính.

**Bài 3.** Một cây có `n=10.000` nút. Hỏi phần bit LOUDS thô dài bao nhiêu bit? Việc này đã đủ để xác định dung lượng RAM thật của ứng dụng chưa?

**Bài 4.** Vì sao các con trực tiếp của một nút liên tiếp theo thứ tự BFS, nhưng tất cả hậu duệ của một nút có thể không liên tiếp? Dùng cây ví dụ để giải thích.

<details>
<summary>Gợi ý đáp án</summary>

- **Bài 1:** Bậc theo BFS là `1,1,0`, nên LOUDS bằng `10 10 0` = `10100`. Có 2 bit `1`, 3 bit `0`.
- **Bài 2:** `degree(4)=select_0(4)-select_0(3)-1=10-8-1=1`. Con đầu tiên là `rank_1(8)+2=5+2=7`, nên nút `4` có một con là nút `7`. Với nút `6`: `select_1(5)=6`; `rank_0(6)=1`, do đó `parent(6)=2`.
- **Bài 3:** `2n-1=19.999` bit, chưa tính index `rank/select`, dữ liệu nút, căn chỉnh bộ nhớ hoặc overhead của chương trình.
- **Bài 4:** Các con của `B` là `E`, `F`, số BFS `5` và `6` liên tiếp. Nhưng tập hậu duệ của `A` tất nhiên gồm toàn cây, còn xét `B` sâu hơn trong cây lớn có thể xen giữa những hậu duệ của các nút khác theo từng tầng. Trong ví dụ hiện tại, các con `E,F` liền nhau, song nếu thêm con cho `E` và cho `D` thì các cháu của `B` ở tầng tiếp theo có thể đứng sau các nút thuộc nhánh `D`. Tính liên tiếp chỉ được bảo đảm cho các con trực tiếp.

</details>

## 10. Ghi nhớ

LOUDS mã hóa cây có gốc, các con có thứ tự bằng cách đi qua từng nút theo **BFS** và ghi `1^d0` cho nút có `d` con. Theo quy ước không thêm gốc giả, cây `n` nút có `n` bit `0` và `n-1` bit `1`; nút BFS số `v` tương ứng với bit `0` thứ `v`, còn nút con BFS số `v \ge 2` tương ứng với bit `1` thứ `v-1`. Các phép `rank/select` biến các quan hệ đó thành công thức tìm số con, cha và các con mà không cần cấp phát một đối tượng con trỏ cho từng nút.
