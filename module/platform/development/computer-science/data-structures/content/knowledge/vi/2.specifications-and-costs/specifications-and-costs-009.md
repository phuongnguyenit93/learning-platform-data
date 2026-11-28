# Chi phí xây dựng ban đầu và chi phí cập nhật về sau

> **Chương:** Đặc tả và chi phí · **Bài học:** Chi phí xây dựng ban đầu và chi phí cập nhật về sau

Một ứng dụng có 100.000 hồ sơ và thường xuyên tìm theo mã học viên. Ta có thể duyệt mảng mỗi lần, sắp xếp mảng để tìm nhị phân, hoặc xây bảng băm để tra theo khóa. Nếu chỉ nhìn độ phức tạp của **một lần tìm**, bảng băm có vẻ hấp dẫn. Nhưng việc xây bảng băm tiêu tốn thời gian và bộ nhớ; nếu hồ sơ thường xuyên thay đổi, ứng dụng còn phải duy trì cấu trúc ấy sau mỗi lần cập nhật.

Vì vậy, để chọn cấu trúc dữ liệu phù hợp, cần đánh giá **cả vòng đời sử dụng**: tạo cấu trúc từ dữ liệu ban đầu, thực hiện truy vấn, chèn/xóa/sửa phần tử, duy trì bất biến, và đôi khi xây dựng lại hoặc xuất dữ liệu. Bài học này tập trung vào sự khác biệt giữa **chi phí xây dựng ban đầu** (*construction/build cost*) và **chi phí cập nhật về sau** (*maintenance/update cost*).

Đây là một phần của mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`): học cách chọn mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị dựa trên thao tác, bất biến, độ phức tạp thời gian và bộ nhớ.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt chi phí tạo cấu trúc ban đầu, truy vấn, cập nhật, duyệt và xây dựng lại.
2. Viết mô hình tổng chi phí khi có `n` phần tử ban đầu, `q` truy vấn và `u` lần cập nhật.
3. Giải thích vì sao xây một cấu trúc hàng loạt (*bulk build*) có thể rẻ hơn việc chèn từng phần tử.
4. Phân tích mảng sắp xếp, mảng động, danh sách liên kết, bảng băm, cây cân bằng, heap và đồ thị dưới tải sử dụng khác nhau.
5. Nhận ra chi phí ẩn như mở rộng vùng đệm, tái băm, đồng bộ chỉ mục, thay đổi định danh và cấp phát bộ nhớ.
6. Chọn cấu trúc theo tần suất sử dụng, yêu cầu thứ tự, giới hạn bộ nhớ và khả năng bảo đảm độ trễ.

## 2. Mô hình chi phí của toàn bộ vòng đời

Ta ký hiệu:

- `n₀`: số phần tử trong dữ liệu ban đầu.
- `n_t`: số phần tử hiện có tại thời điểm `t`, có thể tăng hoặc giảm.
- `q`: số truy vấn tra cứu hoặc đọc dữ liệu.
- `u`: số thao tác cập nhật, gồm chèn, xóa và sửa.
- `r`: số lượt duyệt, tổng hợp hoặc xuất toàn bộ dữ liệu.
- `B(n₀)`: chi phí xây dựng cấu trúc từ dữ liệu ban đầu.
- `Q(n_t)`: chi phí một truy vấn ở trạng thái thứ `t`.
- `U(n_t)`: chi phí một cập nhật ở trạng thái thứ `t`.
- `D(n_t)`: chi phí một lần duyệt hoặc xuất dữ liệu.

Mô hình tổng quát là:

\[
T_{\text{total}}
=B(n_0)
+\sum_{\text{truy vấn }t}Q(n_t)
+\sum_{\text{cập nhật }t}U(n_t)
+\sum_{\text{duyệt }t}D(n_t).
\]

Ở đây **`U` đã bao gồm** việc duy trì cấu trúc như dịch phần tử, cân bằng cây, mở rộng mảng hoặc tái băm khi các công việc ấy do thao tác cập nhật kích hoạt. Không được cộng lại cùng một lần tái băm vào tổng chi phí hai lần.

Nếu kích thước tương đối ổn định và chỉ cần dự toán bậc tăng trưởng, ta có thể viết gần đúng:

\[
T_{\text{total}}\approx B(n_0)+q\,Q(n)+u\,U(n)+r\,D(n).
\]

Công thức thứ hai chỉ là **mô hình đơn giản hóa**; khi `n_t` thay đổi mạnh hoặc các thao tác cập nhật khác nhau, nên dùng tổng theo từng thao tác.

### 2.1. “Xây dựng” và “cập nhật” có ranh giới rõ

| Giai đoạn | Ví dụ | Điều cần tính |
| --- | --- | --- |
| **Xây dựng ban đầu** | Đọc 100.000 bản ghi và tạo Hash Map | Đọc dữ liệu, tính hash, cấp phát bucket, xử lý khóa trùng |
| **Truy vấn** | Tìm hồ sơ theo mã | Tra khóa, so sánh, xuất kết quả |
| **Cập nhật** | Thêm/xóa/sửa hồ sơ | Định vị phần tử và thay đổi trạng thái |
| **Bảo trì cấu trúc** | Rehash, mở rộng mảng, quay cây | Tính vào thao tác gây ra hoặc khoản bảo trì tách riêng |
| **Duyệt/xuất** | Liệt kê hồ sơ theo mã tăng dần | Duyệt, sắp xếp nếu cần, tạo kết quả |
| **Xây lại** | Nạp mới toàn bộ chỉ mục từ bản ghi nguồn | Quét nguồn, cấp phát lại, thời gian gián đoạn hoặc chuyển đổi |

Phải nêu rõ *xây dựng từ cái gì*: dữ liệu đã nằm trong bộ nhớ, một tệp trên đĩa hay dòng sự kiện. Khi so sánh hai cấu trúc từ **cùng một nguồn trong bộ nhớ**, ta có thể tách riêng chi phí đọc dữ liệu chung. Nếu xử lý đầu vào từ đĩa hoặc mạng, I/O có thể chi phối tổng thời gian và cần được đưa vào bài toán thực tế.

### 2.2. Bất biến quyết định chi phí cập nhật

Một cập nhật có thể phải duy trì các quy tắc:

- Mảng đã sắp xếp phải giữ thứ tự tăng dần.
- Danh sách liên kết phải giữ con trỏ đầu/đuôi và số nút nhất quán.
- Bảng băm phải bảo đảm tra cứu được đúng khóa dù đã thay bucket.
- Cây cân bằng phải giữ thứ tự khóa và giới hạn chiều cao.
- Heap phải giữ quan hệ ưu tiên giữa cha và con.
- Đồ thị phải giữ sự nhất quán của danh sách kề hai phía nếu là vô hướng.

Một cách cài đặt bỏ qua những việc này có thể chạy nhanh trên giấy nhưng **không còn đúng hợp đồng** của cấu trúc dữ liệu.

## 3. Giả định khi so sánh độ phức tạp

Trong bài này, trừ khi ghi khác:

- Đọc/ghi một ô mảng và cập nhật một tham chiếu được xem là O(1).
- So sánh hoặc băm một khóa kích thước vừa một từ máy tốn O(1).
- Cấp phát một nút đơn lẻ được xem có chi phí O(1) theo mô hình thông dụng.
- `n` là số phần tử hoặc số khóa **đang có** trong cấu trúc ở thời điểm xét.
- Các cấu trúc được cài đặt đúng và đầu vào tuân hợp đồng.

Khi khóa là chuỗi dài `k` ký tự, việc băm hoặc so sánh có thể cần O(k). Khi xét thời gian thực tế còn có cấp phát, cache CPU, thu gom rác, ổ đĩa và đồng bộ luồng.

**Lưu ý:** O(1) kỳ vọng, O(1) khấu hao và O(1) trong trường hợp xấu nhất là các loại bảo đảm khác nhau. Ví dụ, Hash Map thường có tra cứu O(1) kỳ vọng khi phân bố băm phù hợp, còn thao tác thêm của mảng động tăng gấp đôi là O(1) khấu hao trên một chuỗi thao tác.

## 4. Mảng chưa sắp xếp: xây rẻ, tìm lặp lại có thể đắt

Nếu đã có một dãy `n` phần tử, có thể dùng nó trực tiếp như mảng chưa sắp xếp. Nếu cần tạo bản sao thành mảng mới, ta thường phải sao chép `n` phần tử, tốn Θ(n) thời gian và Θ(n) vùng chứa đầu ra.

| Công việc | Chi phí thường gặp | Giả định |
| --- | --- | --- |
| Dùng mảng có sẵn | O(1) để nhận tham chiếu | Không sao chép và không đổi quyền sở hữu |
| Tạo bản sao mảng có `n` phần tử | Θ(n) | Sao chép từng phần tử |
| Truy cập `a[i]` | O(1) | Chỉ số hợp lệ |
| Tìm một giá trị | O(n) xấu nhất | Không có chỉ mục bổ sung |
| Thêm cuối mảng động | O(1) khấu hao | Tăng sức chứa theo hệ số phù hợp |
| Chèn/xóa giữa và giữ thứ tự | O(n) xấu nhất | Có thể phải dịch nhiều phần tử |
| Duyệt tất cả | Θ(n) | Mỗi phần tử xử lý O(1) |

### 4.1. Mảng phù hợp khi nào?

Mảng thuận lợi khi ứng dụng cần:

- Đọc theo **chỉ số** nhiều lần.
- Duyệt tuần tự, tận dụng tính liên tục của bộ nhớ.
- Chủ yếu thêm cuối thay vì chèn/xóa ở giữa.
- Giữ nguyên thứ tự đầu vào mà không cần tra khóa ngẫu nhiên thường xuyên.

Tuy vậy, nếu cần tìm một khóa trong 100.000 phần tử với hàng nghìn truy vấn, chi phí tìm tuyến tính O(n) mỗi lần có thể trở thành phần chi phối.

### 4.2. Xóa không giữ thứ tự có thể rẻ hơn

Nếu ứng dụng không yêu cầu giữ thứ tự, ta có thể xóa phần tử ở chỉ số `i` bằng cách **thay nó bằng phần tử cuối**, rồi bỏ phần tử cuối. Khi đã biết chỉ số `i`, cách này tốn O(1):

```python
def remove_unordered_at(values, index):
    if not 0 <= index < len(values):
        raise IndexError("invalid index")

    removed = values[index]
    values[index] = values[-1]
    values.pop()
    return removed


data = ["A", "B", "C", "D"]
assert remove_unordered_at(data, 1) == "B"
assert data == ["A", "D", "C"]
```

Phép xóa này thay đổi thứ tự. Nếu hợp đồng yêu cầu các phần tử còn lại giữ thứ tự ban đầu, ta **không được** áp dụng nó. Nếu chỉ biết khóa/giá trị và phải tìm `i` trước, tổng chi phí vẫn có thể O(n).

## 5. Mảng đã sắp xếp: đầu tư ban đầu để tìm nhanh

Giả sử dữ liệu là mảng chưa sắp xếp. Ta có thể sắp xếp một lần rồi tìm kiếm nhị phân:

\[
B(n)=O(n\log n), \qquad Q(n)=O(\log n).
\]

Nếu dữ liệu **đã sắp xếp đúng thứ tự cần dùng**, ta có thể bỏ chi phí sắp xếp; nếu cần sao chép vào vùng mới thì chi phí sao chép thường là Θ(n).

### 5.1. Tổng chi phí cho `q` truy vấn và `u` cập nhật

Nếu mỗi lần chèn/xóa cần giữ mảng sắp xếp, việc tìm vị trí có thể O(log n) nhưng dịch phần tử có thể O(n). Trong mô hình kích thước gần `n`:

\[
T_{\text{sorted-array}}
=O(n\log n+q\log n+un).
\]

Nếu chỉ đọc và không cập nhật (`u=0`), một lần sắp xếp có thể được “thu hồi vốn” qua nhiều truy vấn. Nếu cập nhật thường xuyên ở vị trí tùy ý, chi phí `un` có thể khiến lựa chọn kém hấp dẫn.

### 5.2. Khi nào chi phí chuẩn bị đáng trả?

So sánh hai phương án **chỉ về tìm kiếm**:

- Không sắp: `T_A(q)=O(qn)` trong trường hợp xấu nhất.
- Sắp một lần: `T_B(q)=O(n\log n+q\log n)`.

Nếu muốn xác định điểm hòa vốn theo **thời gian thực**, cần dùng các hằng số chi phí đo được hoặc ước lượng:

\[
B_{\text{sort}}+q\,Q_{\text{binary}}
<q\,Q_{\text{linear}}.
\]

Khi `Q_{\text{linear}}>Q_{\text{binary}}`, điều kiện tương đương:

\[
q>\frac{B_{\text{sort}}}{Q_{\text{linear}}-Q_{\text{binary}}}.
\]

Ký hiệu Big-O **không tự cung cấp giá trị số của `q`** vì nó ẩn hằng số, điều kiện bộ nhớ và phân bố dữ liệu. Khi ra quyết định, cần ước lượng số truy vấn dự kiến và đo trên tải tiêu biểu.

### 5.3. Ví dụ với Python

```python
from bisect import bisect_left, insort

records = [8, 2, 11, 5]
ordered = sorted(records)         # Tạo bản sao đã sắp xếp
assert ordered == [2, 5, 8, 11]

position = bisect_left(ordered, 8)
assert position < len(ordered) and ordered[position] == 8

insort(ordered, 7)                 # Giữ thứ tự, nhưng phải dịch phần tử
assert ordered == [2, 5, 7, 8, 11]
```

`bisect_left` tìm vị trí theo kiểu tìm kiếm nhị phân trong O(log n) phép so sánh. `insort` vẫn có thể phải dịch Θ(n) phần tử trên `list` của Python. **Nhanh khi tìm vị trí** không đồng nghĩa **nhanh khi chèn xong**.

## 6. Bảng băm và chỉ mục: xây một lần, cập nhật liên tục

Một Hash Map hoặc Hash Set thường là lựa chọn cho tra cứu **theo khóa**. Nếu có `n` bản ghi, có thể xây chỉ mục ánh xạ mã định danh → bản ghi hoặc vị trí bản ghi.

| Công việc | Chi phí thông dụng | Điều kiện |
| --- | --- | --- |
| Xây chỉ mục từ `n` bản ghi | O(n) kỳ vọng | Hash/so sánh khóa O(1), tải và phân bố phù hợp |
| Tra cứu theo khóa | O(1) kỳ vọng | Va chạm được kiểm soát |
| Thêm khóa mới | O(1) kỳ vọng, O(1) khấu hao cho resize trong điều kiện thích hợp | Có thể có một lần tái băm O(n) |
| Xóa khóa | O(1) kỳ vọng | Giữ đúng quy tắc xử lý va chạm |
| Duyệt mọi mục | O(n+b) với `b` bucket | Nếu `b=O(n)` thì thường O(n) |
| Trả mọi khóa theo thứ tự tăng | Thường O(n log n) nếu cần sắp xếp riêng | Không mặc định có thứ tự tăng |

**Phân biệt hai lý do có lần thao tác đắt:** Va chạm ảnh hưởng chi phí kỳ vọng theo phân bố băm; mở rộng bảng khiến một lần `put` có thể tái băm toàn bộ khóa, cần phân tích khấu hao. Một lời gọi cụ thể không được bảo đảm O(1) trong mọi trường hợp.

### 6.1. Mã xây chỉ mục và cập nhật

```python
def build_score_index(records):
    index = {}
    for student_id, score in records:
        index[student_id] = score  # Mã trùng: giá trị sau ghi đè giá trị trước
    return index


def update_score(index, student_id, score):
    if student_id not in index:
        raise KeyError(student_id)
    index[student_id] = score


records = [("HV01", 7), ("HV02", 9), ("HV01", 8)]
index = build_score_index(records)
assert len(index) == 2
assert index["HV01"] == 8

update_score(index, "HV02", 10)
assert index["HV02"] == 10
```

Hợp đồng ở đây lựa chọn **khóa trùng ghi đè giá trị**. Nếu ứng dụng cần giữ cả hai bản ghi cùng mã, Map đơn giản không đáp ứng hợp đồng và phải chọn cấu trúc lưu nhiều giá trị trên một khóa hoặc đổi quy tắc xử lý.

### 6.2. Chỉ mục phụ phải được đồng bộ

Giả sử hệ thống giữ đồng thời:

- Một danh sách bản ghi theo thứ tự nhập.
- Một bảng băm `id -> vị trí trong danh sách` để tra cứu nhanh.

Khi thêm bản ghi cuối danh sách, ta cần cập nhật cả bảng chỉ mục. Nếu xóa giữa danh sách và dồn các phần tử còn lại, **vị trí của nhiều bản ghi đổi**; chỉ cập nhật khóa vừa xóa là chưa đủ. Các khóa khác trong chỉ mục có thể trỏ nhầm vị trí.

Có thể dùng định danh ổn định, đối tượng bản ghi có tham chiếu riêng, ô trống đánh dấu xóa hoặc xây lại chỉ mục. Mỗi lựa chọn có chi phí và bất biến riêng.

**Lợi ích của chỉ mục chỉ có giá trị nếu nó luôn phản ánh đúng dữ liệu gốc.** Đừng kết luận cập nhật O(1) khi thực tế cần sửa `n` vị trí chỉ mục sau mỗi lần xóa.

### 6.3. Độ dài khóa và bộ nhớ

Nếu khóa là chuỗi dài `k` ký tự, tính hash có thể mất O(k). Xây chỉ mục từ `n` khóa có thể cần tính thêm tổng độ dài các khóa, không chỉ đếm `n`.

Bảng băm cũng giữ vùng bucket và thông tin khóa/giá trị nên tiêu tốn bộ nhớ bổ sung. Khi rehash, bảng cũ và bảng mới có thể tạm cùng tồn tại, khiến **bộ nhớ đỉnh** lớn hơn bộ nhớ sau khi cập nhật.

## 7. Cây tìm kiếm cân bằng: ưu thế khi cần cả tìm và sửa có thứ tự

Một cây tìm kiếm cân bằng (ví dụ AVL hoặc cây đỏ-đen) giữ chiều cao O(log n). Khi tính so sánh khóa là O(1), các phép tìm, chèn và xóa theo khóa đều có chặn O(log n) **trường hợp xấu nhất**.

Điều này thuận lợi khi dữ liệu có thay đổi và ứng dụng vẫn cần duyệt khóa có thứ tự hoặc tìm khóa theo khoảng.

### 7.1. Xây cây bằng cách chèn từng phần tử

Nếu bắt đầu từ cây rỗng và chèn lần lượt `n` khóa:

\[
B_{\text{incremental}}(n)=O(n\log n).
\]

Đây là chặn trên khi mỗi lần chèn vào cây cân bằng tốn O(log n). Với một cây tìm kiếm nhị phân **không tự cân bằng**, chuỗi khóa tăng dần có thể tạo cây lệch, khiến thời gian xây bằng chèn từng phần tử lên đến Θ(n²).

### 7.2. Xây hàng loạt từ dữ liệu đã sắp

Nếu `n` khóa đã được sắp theo thứ tự cần dùng, có thể xây **cây nhị phân tìm kiếm cân bằng về chiều cao** bằng cách chọn phần tử giữa làm gốc, rồi xây đệ quy hai nửa:

```python
class Node:
    def __init__(self, key, left=None, right=None):
        self.key = key
        self.left = left
        self.right = right


def balanced_bst_from_sorted(keys, lo=0, hi=None):
    if hi is None:
        hi = len(keys)
    if lo >= hi:
        return None

    mid = (lo + hi) // 2
    left = balanced_bst_from_sorted(keys, lo, mid)
    right = balanced_bst_from_sorted(keys, mid + 1, hi)
    return Node(keys[mid], left, right)


root = balanced_bst_from_sorted([1, 2, 3, 4, 5, 6, 7])
assert root.key == 4
```

Mỗi khóa được chuyển thành một nút đúng một lần, nên thời gian xây là Θ(n), bộ nhớ lưu cây Θ(n); stack đệ quy phụ O(log n) với cây gần cân bằng. Ví dụ này giả định các khóa **phân biệt** và danh sách đầu vào **đã sắp**.

Nếu dữ liệu ban đầu chưa sắp và cần sắp bằng thuật toán so sánh O(n log n), tổng xây cây từ đầu vẫn là O(n log n). Nếu cần một cấu trúc AVL/đỏ-đen với metadata hoặc màu nút cụ thể, quá trình xây còn phải thiết lập những trường ấy để duy trì bất biến của cài đặt.

### 7.3. Thêm, xóa sau khi xây

Xây một cây cân bằng ban đầu trong O(n) không đồng nghĩa mỗi lần cập nhật O(1). Về sau, một lần chèn hoặc xóa theo khóa vẫn cần tìm đường đi và duy trì cân bằng, thường O(log n).

Tổng chi phí với `q` tra cứu và `u` cập nhật, khi kích thước gần `n`:

| Dữ liệu ban đầu | Chi phí xây | Truy vấn và cập nhật |
| --- | --- | --- |
| Chưa sắp, chèn lần lượt vào cây cân bằng | O(n log n) | O((q+u) log n) |
| Chưa sắp, sắp rồi xây cây cân bằng | O(n log n) | O((q+u) log n) |
| Đã sắp và dùng xây hàng loạt | O(n) | O((q+u) log n) |

Đừng đồng nhất **chi phí xây** với **chi phí thao tác về sau**: chúng có thể được cải thiện bằng các kỹ thuật khác nhau.

## 8. Heap: xây hàng loạt O(n), chèn lần lượt O(n log n)

Đây là ví dụ đặc biệt rõ về sự khác biệt giữa xây dựng và cập nhật.

Một **min-heap** lưu phần tử theo bất biến: khóa ở nút cha không lớn hơn khóa tại các nút con. Nó hỗ trợ đọc phần tử nhỏ nhất ở gốc O(1), chèn và lấy phần tử nhỏ nhất O(log n) trường hợp xấu nhất.

Có hai cách tạo heap từ `n` phần tử:

1. Bắt đầu với heap rỗng và `insert` từng phần tử: chặn trên O(n log n).
2. Đặt toàn bộ phần tử vào mảng, rồi dùng **bottom-up heapify**: Θ(n).

### 8.1. Vì sao heapify là tuyến tính?

Với heap nhị phân lưu bằng mảng, ta điều chỉnh các nút trong từ dưới lên. Nút ở gần lá có chiều cao nhỏ và chi phí đẩy xuống rất ít. Chỉ có ít nút ở gần gốc có thể cần đi xa.

Số nút có chiều cao ít nhất `h` giảm xấp xỉ theo lũy thừa của 2; số nút ở mức chiều cao `h` bị chặn bởi khoảng `n/2^{h+1}`. Tổng công việc có dạng:

\[
T(n)\leq
O\left(n\sum_{h=0}^{\lfloor\log_2 n\rfloor}\frac{h}{2^h}\right)
=O(n),
\]

vì tổng vô hạn `\sum_{h=0}^{\infty}h/2^h` hội tụ và bằng 2. Mặt khác, thao tác phải xử lý dữ liệu đầu vào gồm `n` phần tử, nên thời gian xây heap chuẩn bằng **Θ(n)**.

Đây là một chặn tổng theo **nút và chiều cao của chúng**, không phải do mỗi lần đẩy xuống đều O(1). Những nút ở gần gốc có thể phải thực hiện O(log n) bước.

### 8.2. Minh họa bằng Python

```python
import heapq


def build_heap_bulk(values):
    heap = list(values)   # Tạo bản sao O(n)
    heapq.heapify(heap)   # Xây heap tại chỗ O(n)
    return heap


def build_heap_incrementally(values):
    heap = []
    for value in values:
        heapq.heappush(heap, value)  # O(log n) xấu nhất mỗi lần
    return heap


bulk = build_heap_bulk([8, 2, 10, 1, 7, 5])
stepwise = build_heap_incrementally([8, 2, 10, 1, 7, 5])

assert heapq.heappop(bulk) == 1
assert heapq.heappop(stepwise) == 1
```

Hai heap có thể có **mảng nội bộ khác nhau** nhưng vẫn đáp ứng cùng hợp đồng priority queue. Không nên kiểm thử bằng cách đòi hai mảng heap giống hệt nhau; hãy kiểm tra quy tắc ưu tiên và chuỗi phần tử lấy ra.

### 8.3. Xây nhanh không khiến mọi cập nhật nhanh

| Công việc | Heap nhị phân |
| --- | --- |
| Xây heap từ `n` phần tử có sẵn bằng bottom-up heapify | Θ(n) |
| Thêm một phần tử | O(log n) xấu nhất |
| Xem phần tử nhỏ nhất | O(1) |
| Lấy và xóa phần tử nhỏ nhất | O(log n) xấu nhất |
| Tìm một phần tử bất kỳ theo giá trị | O(n) xấu nhất nếu không có chỉ mục bổ sung |

Heap rất phù hợp cho hàng đợi ưu tiên, nhưng không thay thế trực tiếp bảng băm nếu thao tác chủ yếu là tìm theo mã định danh.

## 9. Danh sách liên kết: cách xây quyết định chi phí

Giả sử có `n` giá trị ban đầu cần lưu vào danh sách liên kết đơn.

Nếu **giữ con trỏ tới nút cuối** và nối mỗi phần tử vào đuôi, xây danh sách tốn Θ(n): mỗi phần tử được tạo thành một nút và cập nhật một số hằng số liên kết.

Nếu mỗi lần thêm cuối lại **duyệt từ đầu để tìm đuôi**, chi phí các lần thêm lần lượt tăng xấp xỉ `0,1,2,\ldots,n-1` bước, tổng:

\[
\sum_{i=0}^{n-1}i=\frac{n(n-1)}{2}=\Theta(n^2).
\]

Cùng là “xây danh sách liên kết từ `n` phần tử” nhưng việc có giữ `tail` hay không làm khác biệt lớn.

### 9.1. Sau khi xây

| Phép toán | Danh sách liên kết đơn với `head, tail` | Điều kiện |
| --- | --- | --- |
| Đọc phần tử đầu | O(1) | Có `head` |
| Thêm đầu | O(1) | Cập nhật `head` |
| Thêm cuối | O(1) | Cập nhật `tail` |
| Tìm phần tử có giá trị `x` | O(n) xấu nhất | Duyệt từ đầu |
| Chèn sau nút đã biết | O(1) | Có tham chiếu đến nút |
| Xóa nút không phải đầu | O(1) nếu đã có nút trước; có thể O(n) nếu phải tìm | Danh sách liên kết đơn không đi ngược |
| Duyệt tất cả | Θ(n) | Mỗi nút xử lý O(1) |

Một danh sách liên kết đôi có thể xóa nút bất kỳ O(1) khi đã có tham chiếu tới nút và các liên kết `prev/next` hợp lệ, đổi lại mỗi nút tốn thêm bộ nhớ.

### 9.2. Chi phí duy trì con trỏ và bất biến

Nếu lưu `head, tail, size`, ta phải cập nhật chúng đúng khi thêm phần tử đầu tiên, xóa phần tử cuối cùng hoặc chuyển sang trạng thái rỗng. Nếu quên đặt `tail=None` khi danh sách trống, lần thêm sau có thể làm hỏng dữ liệu.

Những cập nhật này chỉ tốn O(1) nhưng **là điều kiện bắt buộc để cài đặt đúng**, không được bỏ qua khi phân tích hoặc viết mã.

## 10. Stack và Queue: chi phí khởi tạo có thể nhỏ nhưng vẫn có lần cập nhật đắt

Một Stack hoặc Queue mới thường có thể khởi tạo trạng thái rỗng trong O(1) nếu chỉ tạo vài tham chiếu/biến đếm. Nếu triển khai cấp phát trước một vùng đệm dài `C` và khởi tạo từng ô, có thể cần O(C) thời gian và bộ nhớ ngay từ đầu.

| ADT, biểu diễn | Xây từ `n` phần tử ban đầu | Thêm về sau | Lấy về sau |
| --- | --- | --- | --- |
| Stack bằng mảng động | Θ(n) khi chép `n` giá trị | O(1) khấu hao, O(n) khi resize | O(1) nếu không thu nhỏ |
| Stack liên kết, thêm ở đầu | Θ(n) để tạo `n` nút (cần xây đúng thứ tự LIFO) | O(1) | O(1) |
| Queue bằng mảng vòng | Θ(n) khi chép `n` giá trị vào vùng đủ chứa | O(1) khấu hao nếu tự mở rộng | O(1) |
| Queue liên kết có đầu/đuôi | Θ(n) khi nối bằng `tail` | O(1) | O(1) |
| Queue hai Stack | Θ(n) khi nạp `n` phần tử | O(1) khấu hao | O(1) khấu hao; có lần O(n) để chuyển |

Đối với Queue hai Stack, một `dequeue` có thể phải chuyển tất cả `n` phần tử từ stack đầu vào sang stack đầu ra. Tuy vậy, mỗi phần tử chỉ bị chuyển một lần, nên tổng chi phí trên một chuỗi hợp lệ có thể được chặn tuyến tính theo số thao tác và số phần tử ban đầu.

**Điểm cần phân biệt:** chi phí xây `n` phần tử ban đầu Θ(n), chi phí một lần lấy có thể O(n), nhưng chi phí khấu hao của các lần lấy trên một chuỗi vẫn O(1) trong điều kiện phân tích phù hợp. Khi nạp sẵn `n` phần tử, phải tính cả `n` công việc ban đầu trong tổng vòng đời.

## 11. Đồ thị: xây danh sách kề và ma trận kề có chi phí khác nhau

Đồ thị có `V` đỉnh và `E` cạnh có thể lưu bằng danh sách kề hoặc ma trận kề. Với đồ thị thưa, hai cách có sự khác biệt lớn ngay từ giai đoạn xây dựng.

### 11.1. Danh sách kề

Nếu tạo một danh sách láng giềng rỗng cho mỗi đỉnh, rồi đọc từng cạnh để thêm vào danh sách của đỉnh nguồn, ta có:

\[
B_{\text{adj-list}}(V,E)=O(V+E).
\]

Với đồ thị vô hướng, mỗi cạnh được thêm vào danh sách của cả hai đầu, chỉ nhân hệ số hằng. Bộ nhớ lưu dữ liệu cũng O(V+E).

Nếu yêu cầu **không có cạnh trùng**, thêm cạnh vào danh sách thông thường có thể cần kiểm tra các láng giềng hiện có, tốn O(deg(u)) mỗi lần. Khi dữ liệu đầu vào đã được bảo đảm không trùng, có thể nối trực tiếp; khi cần loại trùng hiệu quả, ta có thể dùng tập băm cho từng đỉnh, với điều kiện kỳ vọng của hash.

### 11.2. Ma trận kề

Ma trận kề chứa một ô cho mỗi cặp đỉnh. Khởi tạo ma trận `V×V` với giá trị “không có cạnh” đã cần:

\[
B_{\text{matrix}}(V,E)=\Theta(V^2+E)=\Theta(V^2)
\]

đối với đồ thị đơn nơi `E=O(V²)` và truy cập chỉ số O(1). Bộ nhớ là Θ(V²), kể cả khi đồ thị không có cạnh nào.

Khi các đỉnh đã được ánh xạ sang chỉ số cố định:

- Thêm hoặc xóa một **cạnh** bằng việc sửa một (có hướng) hoặc hai (vô hướng) ô là O(1).
- Kiểm tra tồn tại cạnh `(u,v)` là O(1).
- Liệt kê toàn bộ láng giềng của một đỉnh bằng cách quét hàng là O(V).

### 11.3. Cập nhật đỉnh khác cập nhật cạnh

Nếu muốn **thêm một đỉnh mới** vào ma trận kề được lưu dưới dạng mảng đặc kích thước cố định, có thể phải cấp phát ma trận lớn hơn và sao chép Θ(V²) ô. Một thiết kế có **sức chứa đỉnh dự phòng** hoặc định danh ổn định có thể có chiến lược khác.

Với danh sách kề, thêm một đỉnh mới thường chỉ cần tạo danh sách kề rỗng cho nó, O(1) kỳ vọng theo cơ chế lưu ánh xạ đỉnh. Nhưng **xóa đỉnh** có thể cần đi qua nhiều danh sách để xóa các cạnh đi vào nếu không giữ chỉ mục ngược, lên tới O(V+E).

Do đó, câu “đồ thị cập nhật O(1)” là thiếu thông tin. Phải chỉ rõ đang **thêm/xóa cạnh hay đỉnh**, biểu diễn nào và các ràng buộc về cạnh trùng/định danh.

### 11.4. Bảng theo vòng đời

| Công việc | Danh sách kề | Ma trận kề |
| --- | --- | --- |
| Xây từ `V` đỉnh và `E` cạnh không trùng | Θ(V+E) | Θ(V²) |
| Lưu đồ thị | O(V+E) | Θ(V²) |
| Thêm một cạnh khi đã biết đỉnh, không cần dò trùng | O(1) khấu hao nếu nối vào mảng động | O(1) |
| Kiểm tra cạnh | O(deg(u)+1) nếu danh sách không có chỉ mục | O(1) |
| Duyệt tất cả các thành phần bằng BFS | O(V+E) | O(V²) khi quét hàng |
| Thêm đỉnh | O(1) kỳ vọng với cấu trúc ánh xạ linh hoạt | Có thể Θ(V²) nếu cần xây lại ma trận đặc |

Bảng giả định mỗi thao tác với định danh đỉnh có thể truy cập cấu trúc kề tương ứng hiệu quả, và không tính chi phí chuỗi định danh dài. Đồ thị dùng tập kề băm có thể đổi lại chi phí kiểm tra cạnh thành O(1) kỳ vọng nhưng tăng bộ nhớ và chi phí quản lý bucket.

## 12. Xây mới toàn bộ hay cập nhật từng phần?

Không phải lúc nào cập nhật nhỏ cũng rẻ hơn xây lại. Điều này phụ thuộc cấu trúc, số cập nhật và cách gom công việc.

Ví dụ, một báo cáo giữ **bản sao mảng đã sắp** của các bản ghi:

- Nếu dữ liệu có một ít thay đổi, cập nhật từng lần bằng chèn/xóa trong mảng có thể tốn O(n) mỗi lần.
- Nếu có rất nhiều bản ghi thay đổi trong một đợt, gom thay đổi rồi **xây lại bản sắp xếp** bằng O(n log n) có thể hợp lý hơn việc thực hiện hàng nghìn lần dịch phần tử O(n).
- Nếu dữ liệu đã được sắp và các cập nhật được gom thành dãy đã sắp, có thể dùng thuật toán trộn để tạo bản mới trong thời gian tuyến tính theo tổng số phần tử (với quy tắc xử lý khóa trùng rõ ràng).

### 12.1. Ví dụ so sánh theo số lần cập nhật

Giả sử dữ liệu gần như luôn có `n` phần tử. Đơn giản hóa:

- Phương án A: sau mỗi lần cập nhật, chèn/xóa và dịch phần tử trong mảng sắp, O(n). Tổng `u` lần cập nhật: O(un).
- Phương án B: thu thập thay đổi vào vùng riêng, rồi sắp xếp lại toàn bộ `n+u` mục một lần theo cách tổng quát: O((n+u)log(n+u)).

Nếu `u` lớn và không cần bản sắp mới ngay sau **từng** cập nhật, phương án B có thể có tổng chi phí tốt hơn. Nhưng nếu ứng dụng cần tra cứu đúng dữ liệu **ngay sau mỗi thay đổi**, ta phải giữ truy vấn nhất quán trong thời gian chờ gộp.

### 12.2. Lựa chọn theo tần suất đồng bộ

| Cách cập nhật | Ưu điểm | Chi phí/ràng buộc |
| --- | --- | --- |
| Cập nhật ngay từng thao tác | Dữ liệu truy vấn luôn thấy bản mới sau khi thao tác hoàn tất | Có thể trả nhiều lần chi phí duy trì chỉ mục |
| Gom theo lô (*batch*) | Giảm số lần sắp xếp hoặc tái cấu trúc lớn | Cần định nghĩa khi nào thay đổi có hiệu lực với truy vấn |
| Xây bản mới rồi thay thế | Cho phép tạo trạng thái nhất quán trước khi chuyển sang bản mới | Cần thêm bộ nhớ, có thể tăng bộ nhớ đỉnh |
| Chỉ mục nền cập nhật định kỳ | Truy vấn có thể nhanh trên dữ liệu ổn định | Phải xử lý các thay đổi mới chưa vào chỉ mục |

Trong bài toán nhiều luồng hoặc có giao dịch, việc chuyển đổi từ bản cũ sang bản mới phải giữ tính nguyên tử/nhất quán theo hợp đồng. **Tổng thời gian tốt hơn** không tự động có nghĩa hành vi ứng dụng vẫn đúng.

## 13. Tổng chi phí theo tần suất thao tác: một ví dụ ra quyết định

Giả sử hệ thống có `n₀=100.000` hồ sơ, phần lớn giữ nguyên trong kỳ xử lý. Nhiệm vụ:

- Tra cứu theo mã hồ sơ `q` lần.
- Thêm/xóa/sửa hồ sơ `u` lần.
- Xuất danh sách theo mã tăng dần `r` lần.

Có thể phác thảo ba lựa chọn:

| Cấu trúc | Xây ban đầu | Tra theo mã | Cập nhật | Xuất khóa tăng dần |
| --- | --- | --- | --- | --- |
| Mảng sắp theo mã | O(n log n) | O(log n) | O(n) nếu chèn/xóa cần dịch | Θ(n) |
| Hash Map | O(n) kỳ vọng | O(1) kỳ vọng | O(1) kỳ vọng/khấu hao với giả định phù hợp | O(n log n) nếu lấy khóa ra sắp mỗi lần |
| Cây tìm kiếm cân bằng | O(n log n) nếu chèn từng mục | O(log n) xấu nhất | O(log n) xấu nhất | Θ(n) bằng duyệt trung thứ tự |

**Không có đáp án tốt nhất cho mọi giá trị `q,u,r`.**

### 13.1. Trường hợp truy vấn rất nhiều, cập nhật ít

Khi `q` lớn còn `u` và `r` nhỏ, chi phí xây Hash Map có thể được bù lại nhờ các lần tra khóa O(1) kỳ vọng. Nếu yêu cầu định kỳ xuất có thứ tự nhưng ít lần, có thể sắp khóa riêng khi cần.

### 13.2. Trường hợp cập nhật nhiều và vẫn phải duyệt có thứ tự

Khi `u` lớn và có nhiều truy vấn khoảng hoặc duyệt thứ tự, cây cân bằng có thể phù hợp hơn mảng sắp vì một lần cập nhật thường O(log n) thay vì phải dịch O(n) phần tử.

### 13.3. Trường hợp dữ liệu chỉ dùng một lần

Nếu chỉ cần một lần quét để cộng tổng, tìm giá trị lớn nhất hoặc kiểm tra một điều kiện, xây Hash Map hay cây cân bằng có thể là **chi phí thừa**. Mảng hiện có hoặc một vòng lặp tuyến tính đáp ứng đúng yêu cầu với ít bộ nhớ bổ sung.

### 13.4. Đặt công thức hòa vốn khi so sánh

Với hai phương án A và B, một mô hình giản lược là:

\[
T_A=B_A+qQ_A+uU_A+rD_A,
\quad
T_B=B_B+qQ_B+uU_B+rD_B.
\]

Nếu B tốn thêm `\Delta B=B_B-B_A` để xây, B chỉ có lợi về tổng thời gian khi:

\[
\Delta B < q(Q_A-Q_B)+u(U_A-U_B)+r(D_A-D_B).
\]

Các chi phí trong bất đẳng thức này cần là **ước lượng thời gian hoặc số bước nhất quán**; không được thay trực tiếp biểu thức Big-O vào để suy ra một điểm hòa vốn số học chính xác.

Với khối lượng dữ liệu biến động lớn, hãy tính trên từng thời điểm `n_t` hoặc đo bằng tải mô phỏng thay vì coi mọi thao tác có cùng `n`.

## 14. Thời gian và bộ nhớ: đừng bỏ qua chi phí ban đầu của bộ nhớ

Một cấu trúc có thể giảm thời gian truy vấn nhưng tăng bộ nhớ lưu trữ và bộ nhớ đỉnh khi xây hoặc cập nhật.

| Cấu trúc | Bộ nhớ lưu dữ liệu/chỉ mục | Bộ nhớ bổ sung đáng chú ý |
| --- | --- | --- |
| Mảng động | O(C) theo sức chứa `C` | Khi tăng từ `C` lên `2C` có thể cùng giữ hai vùng, xấp xỉ `3C` ô ở đỉnh |
| Danh sách liên kết | O(n) nút | Tham chiếu `next`, có thể thêm `prev`, metadata cấp phát mỗi nút |
| Hash Map | O(n+b) theo mục và bucket | Có thể cùng giữ bảng cũ/mới lúc rehash |
| Cây cân bằng | O(n) nút | Liên kết và thông tin chiều cao/màu; stack duyệt phụ thuộc chiều cao |
| Heap bằng mảng | O(n) vùng chứa | Bản sao đầu vào thêm O(n) nếu không xây tại chỗ |
| Danh sách kề đồ thị | O(V+E) | Chỉ mục băm và dữ liệu kề bổ sung nếu cần |
| Ma trận kề | Θ(V²) | Có thể tăng mạnh khi cần cấp phát ma trận lớn hơn |

Khái niệm cần phân biệt:

- **Bộ nhớ đầu vào:** dữ liệu nguồn đã tồn tại trước khi xây.
- **Bộ nhớ cấu trúc mới:** các nút, bucket, vùng đệm hoặc ma trận tạo ra.
- **Bộ nhớ phụ của thao tác:** vùng nhớ tạm để sắp, sao chép hoặc cập nhật.
- **Bộ nhớ đỉnh:** lượng bộ nhớ tối đa đồng thời tồn tại trong quá trình chuyển đổi.

Nếu ứng dụng đã có mảng 100.000 bản ghi, xây thêm Hash Map không làm mảng cũ tự biến mất. Cần quyết định có giữ cả hai biểu diễn hay chuyển quyền sở hữu dữ liệu sang cấu trúc mới.

### 14.1. Chi phí xây lại có thể làm tăng bộ nhớ đỉnh

Một hệ thống xây lại chỉ mục song song với chỉ mục cũ để duy trì khả năng phục vụ truy vấn. Trước khi chuyển sang chỉ mục mới, **cả hai bản** có thể cùng tồn tại, tốn gần gấp đôi không gian chỉ mục theo số phần tử (cộng chi phí tạm).

Bù lại, có thể giảm thời gian ứng dụng không phục vụ được yêu cầu. Đây là đánh đổi giữa **thời gian chuyển đổi, bộ nhớ và tính nhất quán**, chứ không chỉ phép tính Big-O của một thao tác.

## 15. Ví dụ về lỗi phổ biến khi chỉ nhìn chi phí một thao tác

| Nhận định | Vấn đề bị bỏ qua | Cách phân tích đầy đủ hơn |
| --- | --- | --- |
| “Tìm nhị phân O(log n), nên luôn tốt hơn duyệt tuyến tính.” | Cần sắp trước; dữ liệu có thể chỉ có một truy vấn | Cộng chi phí xây O(n log n) và số truy vấn `q` |
| “Hash Map tra khóa O(1), nên không mất chi phí.” | Phải xây, có va chạm, hash khóa dài, rehash, bộ nhớ | Ghi O(1) kỳ vọng cùng giả định và chi phí `B(n)` |
| “Chèn cây cân bằng O(log n), nên xây cây O(log n).” | Xây gồm `n` lần chèn hoặc thuật toán hàng loạt | Xây lặp O(n log n), từ dữ liệu đã sắp có thể O(n) |
| “Heap chèn O(log n), nên xây heap bắt buộc O(n log n).” | Bottom-up heapify xây trong Θ(n) | Phân biệt bulk build và chèn từng phần tử |
| “Thêm cuối danh sách liên kết O(1).” | Nếu không giữ `tail`, phải đi từ đầu mỗi lần | Có `tail`: xây Θ(n); không có `tail`: xây có thể Θ(n²) |
| “Ma trận kề thêm cạnh O(1), nên xây đồ thị O(E).” | Phải khởi tạo `V²` ô | Xây và bộ nhớ Θ(V²) với ma trận đặc |
| “Xóa bản ghi khỏi mảng rồi cập nhật Hash Map là O(1).” | Nếu Map lưu chỉ số, nhiều chỉ số thay đổi khi dịch mảng | Tính chi phí duy trì toàn bộ chỉ mục |
| “Gom cập nhật theo lô luôn tốt hơn.” | Truy vấn có thể nhìn dữ liệu cũ hoặc thiếu bản cập nhật | Nêu hợp đồng nhất quán và thời điểm công bố dữ liệu |
| “O(n) bộ nhớ của hai cách cài đặt là như nhau.” | Hệ số nút, bucket, dung lượng dư và bộ nhớ đỉnh khác | Đo số byte thực tế với tải đại diện |
| “Cấu trúc đã xây xong thì chi phí về sau cố định.” | Dữ liệu lớn lên, phân bố khóa và tỷ lệ thao tác thay đổi | Dùng `n_t` và đo lại theo các giai đoạn |

## 16. Cách thực hành chọn cấu trúc dữ liệu

Có thể dùng quy trình sau cho mỗi chức năng:

1. **Viết hợp đồng thao tác.** Cần tra theo khóa, truy cập chỉ số, chèn đầu/cuối, xóa theo khóa, duyệt có thứ tự, hay lấy ưu tiên?
2. **Đo trạng thái ban đầu.** Có `n₀` phần tử, dữ liệu đã sắp chưa, khóa có trùng không, đồ thị có `V,E` ra sao?
3. **Ước lượng tải về sau.** Bao nhiêu `q` truy vấn, `u` cập nhật, `r` lần duyệt? Tỷ lệ nào chi phối?
4. **Liệt kê ứng viên và cách xây.** Chèn dần, heapify, sắp rồi dựng cây, nạp vào bảng băm, tạo danh sách/ma trận kề.
5. **Tính thời gian tổng.** Bao gồm xây, duy trì bất biến, tìm, cập nhật, xuất và khả năng xây lại.
6. **Tính bộ nhớ và rủi ro độ trễ.** Cân nhắc cấp phát ban đầu, bộ nhớ đỉnh, thao tác resize và yêu cầu đáp ứng thời gian.
7. **Kiểm thử tính đúng.** Thay biểu diễn không được làm sai thứ tự, xử lý khóa trùng, tính nhất quán chỉ mục và trường hợp rỗng.
8. **Đo thực nghiệm khi cần.** So sánh trên kích thước đầu vào và phân bố thao tác gần với thực tế.

### 16.1. Minh họa quy trình bằng bảng công việc

| Nhu cầu thực tế | Cấu trúc nên cân nhắc | Điều cần xác nhận |
| --- | --- | --- |
| Tập dữ liệu cố định, rất nhiều tra khóa | Hash Map hoặc mảng đã sắp | Có cần thứ tự? Chi phí xây? Bộ nhớ cho chỉ mục? |
| Cần tìm/chèn/xóa theo khóa và duyệt tăng dần | Cây cân bằng | Quan hệ thứ tự và chi phí nút |
| Chủ yếu thêm cuối và đọc theo chỉ số | Mảng động | Resize và sức chứa dư |
| Xử lý FIFO theo thời gian đến | Queue mảng vòng hoặc liên kết có đầu/đuôi | Thao tác lấy đầu có O(1) trong cài đặt không? |
| Từ tập tác vụ ban đầu, liên tục lấy nhiệm vụ ưu tiên nhất | Heap xây bằng heapify | Θ(n) để xây, O(log n) mỗi lần lấy |
| Đồ thị thưa, thường duyệt láng giềng | Danh sách kề | Có cạnh trùng không, chi phí xóa đỉnh |
| Đồ thị có số đỉnh ổn định, kiểm tra cạnh thường xuyên | Ma trận kề | Chấp nhận Θ(V²) bộ nhớ và chi phí khởi tạo không? |

## 17. Bài tập vận dụng có đáp án gợi ý

### Bài 1 — Xây Hash Map có đáng không?

Một danh sách chứa `n` bản ghi, ứng dụng cần tra cứu theo mã `q` lần và không cần duyệt có thứ tự. Hãy viết chi phí của hai lựa chọn: duyệt tuyến tính mỗi lần; xây Hash Map rồi tra cứu.

**Gợi ý:** Duyệt tuyến tính O(qn) trường hợp xấu. Xây bảng băm O(n) kỳ vọng, tra `q` lần O(q) kỳ vọng, tổng O(n+q) theo giả định hash/so sánh khóa O(1) và phân bố phù hợp. Tính thêm O(n) bộ nhớ chỉ mục. Với `q` rất nhỏ, cần so sánh hằng số và chi phí tạo bảng thực tế.

### Bài 2 — Xây cây từ dữ liệu đã sắp

Có 127 khóa phân biệt **đã sắp tăng**, cần tạo cây tìm kiếm cân bằng rồi thực hiện các thao tác `find`.

**Câu hỏi:** Xây bằng chọn giữa từng đoạn tốn bao nhiêu? Sau đó tìm khóa có chặn xấu nhất thế nào?

**Gợi ý:** Mỗi khóa được tạo thành một nút đúng một lần, nên xây Θ(n), stack đệ quy O(log n). Cây gần cân bằng có chiều cao O(log n), nên `find` O(log n) xấu nhất; con số 127 chỉ minh họa.

### Bài 3 — Heap từ 50.000 phần tử

Bạn đã có sẵn một mảng 50.000 độ ưu tiên. So sánh `heappush` từng phần tử với `heapify` một lần.

**Gợi ý:** Chèn lặp có chặn trên O(n log n), còn bottom-up heapify Θ(n). Sau khi xây, cả hai heap đều hỗ trợ `peek_min` O(1), `heappush` và `heappop` O(log n) xấu nhất. Hai mảng nội bộ không bắt buộc giống nhau.

### Bài 4 — Vì sao xây danh sách lại Θ(n²)?

Một hàm xây danh sách liên kết đơn cứ mỗi lần thêm cuối lại đi từ `head` để tìm nút cuối. Có `n` phần tử đầu vào.

**Gợi ý:** Lần thêm thứ `i` có thể đi qua gần `i` nút. Tổng số lần đi qua liên kết là `0+1+\cdots+(n-1)=n(n-1)/2`, bậc Θ(n²). Giữ `tail` và cập nhật nó đúng sẽ giảm tổng chi phí xây xuống Θ(n).

### Bài 5 — Chỉ mục vị trí bị sai sau khi xóa

Dữ liệu là `[A,B,C,D]`, Hash Map lưu `A→0, B→1, C→2, D→3`. Bạn xóa `B` bằng cách dồn các phần tử giữ thứ tự, tạo `[A,C,D]`. Map chỉ xóa khóa `B`.

**Gợi ý:** Chỉ mục còn lưu `C→2`, `D→3` nên không đúng nữa. Cần cập nhật lại vị trí của `C` và `D` hoặc dùng định danh/tham chiếu ổn định. Xóa có thể phải xử lý O(n) bản ghi/chỉ mục, không còn O(1) theo kỳ vọng của Hash Map đơn lẻ.

### Bài 6 — Chọn biểu diễn đồ thị

Có `V=20.000` đỉnh và `E=30.000` cạnh. Hệ thống thường duyệt láng giềng, ít kiểm tra cạnh bất kỳ.

**Gợi ý:** Danh sách kề cần O(V+E) bộ nhớ và xây O(V+E) nếu dữ liệu cạnh không trùng; ma trận kề cần Θ(V²) bộ nhớ và khởi tạo. Với đồ thị thưa, danh sách kề thường phù hợp hơn. Nếu cần tránh cạnh trùng, phải tính thêm bước kiểm tra hoặc dùng tập kề.

### Bài 7 — Chọn cập nhật từng phần hay xây lại

Một mảng sắp có `n` phần tử, mỗi lần chèn ở giữa mất O(n). Có `u` bản cập nhật có thể hoãn đến cuối một đợt; sau đó mới cần công bố dữ liệu sắp cho các truy vấn.

**Gợi ý:** Cập nhật từng lần tốn O(un) theo kích thước gần ổn định. Nếu hợp đồng cho phép gom, có thể hợp nhất thay đổi rồi sắp lại hoặc trộn hai dãy đã sắp. Phải tính chi phí tạo vùng trung gian và đảm bảo truy vấn không đọc dữ liệu lỗi thời trái hợp đồng.

### Bài 8 — Điểm hòa vốn

Giả sử đo được chi phí xây chỉ mục là 1.000 đơn vị; một truy vấn không chỉ mục tốn 20 đơn vị, còn có chỉ mục tốn 2 đơn vị. Không có cập nhật và không tính thêm bộ nhớ. Từ bao nhiêu truy vấn thì dùng chỉ mục tiết kiệm **thời gian tổng**?

**Gợi ý:** So `T_{\text{no-index}}=20q` với `T_{\text{index}}=1000+2q`. Chỉ mục nhanh hơn khi `1000+2q<20q`, tức `q>1000/18≈55,56`. Với `q` là số nguyên, từ **56 truy vấn**. Đây là ví dụ theo số đo giả định, không suy trực tiếp ra từ Big-O.

### Bài 9 — Bộ nhớ đỉnh khi xây lại

Một chỉ mục cũ chiếm `M` byte, chỉ mục mới cũng chiếm khoảng `M` byte. Để phục vụ truy vấn liên tục, hệ thống chỉ xóa bản cũ sau khi xây và chuyển sang bản mới.

**Gợi ý:** Trong giai đoạn chuyển đổi, riêng hai chỉ mục có thể đồng thời chiếm khoảng `2M` byte, chưa kể mảng tạm và dữ liệu nguồn. Phải dự toán theo **bộ nhớ đỉnh**, không chỉ bộ nhớ sau khi hoàn thành.

### Bài 10 — Trường hợp xóa đỉnh trong đồ thị

Một ứng dụng dùng danh sách kề hướng ra cho đồ thị có hướng và chỉ giữ các cạnh đi ra. Xóa đỉnh `v` có những bước nào? Có luôn O(deg(v)) không?

**Gợi ý:** Cần xóa chính đỉnh và các cạnh đi ra của `v`, đồng thời loại các cạnh từ **đỉnh khác đi vào `v`**. Nếu không có chỉ mục ngược, có thể phải quét danh sách kề của nhiều đỉnh, lên tới O(V+E). Không thể chỉ nhìn bậc ra của `v`.

## 18. Mẫu phân tích chi phí từ lúc tạo đến khi thay đổi

Khi lựa chọn một cấu trúc dữ liệu, hãy điền đầy đủ:

```text
Bài toán và hợp đồng thao tác:
Dữ liệu ban đầu:
  n0 = ?; đã sắp hay chưa?
  Khóa trùng/không trùng? Kiểu và độ dài khóa?
Tải sử dụng:
  q = số truy vấn
  u = số cập nhật; chèn/xóa/sửa chiếm bao nhiêu?
  r = số lần duyệt/xuất; có cần thứ tự không?
  Kích thước dự kiến thay đổi theo thời gian ra sao?

Cách triển khai A / B / C:
  Cách xây từ dữ liệu có sẵn:
  Chi phí xây B(n0):
  Chi phí truy vấn Q(nt):
  Chi phí cập nhật U(nt), gồm bảo trì:
  Chi phí duyệt/xuất D(nt):
  Tổng chi phí trên các giai đoạn:
  Cần xây lại theo lô hoặc cập nhật liên tục?

Bất biến và khả năng quan sát:
  Chỉ mục có nhất quán sau xóa/chèn?
  Thứ tự, khóa trùng, ưu tiên và định danh có được giữ?
  Truy vấn có cần thấy cập nhật ngay không?

Bộ nhớ:
  Bộ nhớ lưu cấu trúc:
  Bộ nhớ bổ sung cho chỉ mục:
  Bộ nhớ đỉnh khi resize, rehash hoặc xây lại:

Loại bảo đảm:
  Xấu nhất, trung bình, kỳ vọng hay khấu hao?
  Giả định mô hình chi phí và phân bố đầu vào?
  Có giới hạn độ trễ từng thao tác không?

Kết luận và trường hợp khiến lựa chọn phải xem lại:
```

**Chi phí xây dựng ban đầu là khoản đầu tư**, còn chi phí truy vấn và cập nhật là khoản phải trả suốt thời gian cấu trúc được sử dụng. Mảng có thể phù hợp khi dữ liệu ít thay đổi và cần truy cập chỉ số; Hash Map đáng cân nhắc khi phải tra theo khóa nhiều lần; cây cân bằng giúp vừa tìm vừa cập nhật có thứ tự; heapify xây priority queue nhanh từ dữ liệu sẵn có; danh sách kề tiết kiệm khi đồ thị thưa. Đánh giá toàn bộ vòng đời cùng các bất biến và giới hạn bộ nhớ sẽ giúp lựa chọn cấu trúc đúng cho từng bài toán.
