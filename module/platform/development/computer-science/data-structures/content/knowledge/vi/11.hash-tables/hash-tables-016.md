# Vì sao bảng băm thông thường không hỗ trợ hiệu quả truy vấn thứ tự

## 1. Tra cứu theo khóa khác với truy vấn theo thứ tự

**Bảng băm (hash table)** được thiết kế trước hết cho bài toán **tra cứu chính xác theo khóa** (*exact-match lookup*): với khóa `k`, tìm giá trị `v` của cặp `(k,v)`. Bảng dùng hàm băm để chọn ngăn hoặc điểm bắt đầu một dãy thăm dò, nên dưới giả định phân bố băm tốt và hệ số tải được kiểm soát, các thao tác `get(k)`, `put(k,v)`, `remove(k)` có thể đạt **thời gian kỳ vọng `O(1)`**.

Nhiều bài toán lại hỏi về **quan hệ thứ tự giữa các khóa**:

- Các mã số nằm trong khoảng `[a,b]` là những mã nào?
- Khóa nhỏ nhất, lớn nhất, khóa đứng ngay trước/sau `x` là gì?
- Có bao nhiêu khóa nhỏ hơn `x` (*rank*)?
- Khóa nhỏ thứ `r` (*select*) là khóa nào?
- Hãy duyệt các bản ghi theo thứ tự tăng dần của khóa.

Những câu hỏi này cần biết **khóa nào lớn hơn hoặc nhỏ hơn khóa nào**, không chỉ biết `hash(k)` hoặc `hash(k) mod m`. Một bảng băm thông thường **không duy trì thứ tự đã sắp xếp của các khóa**, vì vậy không thể tự động tận dụng `O(1)` của tra cứu chính xác cho các truy vấn trên.

> **Thông điệp chính:** Hàm băm giúp xác định *nơi có thể tìm một khóa đã biết*, chứ không cung cấp *vị trí của khóa đó trong thứ tự tăng dần*.

## 2. Hàm băm không phải ánh xạ bảo toàn thứ tự

Giả sử bảng có `m=7` ngăn và dùng công thức đơn giản `i(k)=k\bmod7` với khóa nguyên không âm. Chèn lần lượt các khóa `10,3,17,8,12`, dùng **nối chuỗi (separate chaining)**:

| Khóa | `k mod 7` | Ngăn |
| ---: | ---: | ---: |
| 10 | 3 | 3 |
| 3 | 3 | 3 |
| 17 | 3 | 3 |
| 8 | 1 | 1 |
| 12 | 5 | 5 |

```text
Chỉ số ngăn    Danh sách khóa theo thứ tự chèn trong ngăn
     0         -
     1         8
     2         -
     3         10 -> 3 -> 17
     4         -
     5         12
     6         -

Đọc ngăn từ 0 đến 6:  8, 10, 3, 17, 12
Thứ tự khóa tăng dần: 3,  8, 10, 12, 17
```

Đọc các ngăn theo chỉ số tăng dần **không tạo ra thứ tự tăng dần của khóa**. Ngay cả trong một ngăn, các khóa `10,3,17` cũng không nhất thiết được lưu theo thứ tự giá trị.

Sự mất thứ tự bắt nguồn từ cách băm: phép lấy dư đưa cả các khóa rất khác nhau vào cùng ngăn (`3,10,17`), còn khóa nhỏ hơn có thể nằm ở ngăn có chỉ số lớn hơn khóa khác. Một hàm băm phân bố tốt thậm chí **chủ động làm phân tán** những khóa có cấu trúc gần giống nhau để giảm va chạm; nó không phải phép biến đổi đơn điệu theo quan hệ `<`.

**Phản ví dụ trực tiếp:** `8<10`, nhưng `i(8)=1<i(10)=3`; trong khi `3<8`, lại có `i(3)=3>i(8)=1`. Chỉ số ngăn không thể dùng làm thứ tự khóa.

Đối với **địa chỉ mở (open addressing)**, va chạm còn khiến khóa nằm ở ô khác với chỉ số băm ban đầu. Linear probing, quadratic probing hoặc double hashing tối ưu cách tìm ô phù hợp, **không duy trì thứ tự số học hay từ điển của các khóa**.

## 3. Truy vấn khoảng phải làm gì với bảng băm thông thường?

Hãy tìm tất cả khóa thuộc khoảng đóng `[8,12]` trong bảng vừa xây dựng. Kết quả theo thứ tự tăng là:

```text
8, 10, 12
```

Nhưng bảng không có chỉ mục cho biết những khóa nào có thể nằm trong khoảng này. Một cách làm tổng quát, đúng cho bảng băm thông thường là:

1. Duyệt các bản ghi đang hoạt động.
2. So sánh từng khóa `k` với hai biên: `8 <= k <= 12`.
3. Thu thập các khóa thỏa điều kiện.
4. Nếu người dùng muốn kết quả **được sắp xếp**, sắp xếp thêm tập kết quả.

Giả sử `n` là số bản ghi và `r` là số kết quả trong khoảng:

- **Lọc khoảng:** phải kiểm tra `n` khóa trong mô hình bảng băm thông thường không có chỉ mục thứ tự, nên cần `O(n)` lần kiểm tra khóa. Nếu quét trực tiếp toàn bộ mảng `m` ngăn/ô, thời gian duyệt cấu trúc là `O(m+n)` đối với nối chuỗi hoặc `O(m)` với địa chỉ mở.
- **Sắp xếp `r` kết quả:** tốn thêm `O(r\log r)` với thuật toán sắp xếp so sánh thông thường; ghi ra `r` kết quả vốn đã có cận dưới `\Omega(r)`.
- **Chỉ đếm các khóa thuộc khoảng:** không cần sắp xếp nhưng vẫn cần quét các khóa nếu không có chỉ mục thứ tự phụ trợ.

Nếu có nhiều truy vấn khoảng, việc quét lặp lại toàn bộ bảng có thể rất tốn kém. Ví dụ, `q` truy vấn khoảng độc lập trên bảng có `n` khóa có thể cần `O(qn)` lần kiểm tra khóa, chưa kể sắp xếp kết quả.

**Lưu ý về mô hình chi phí:** nhiều API `dict` có iterator cho các phần tử, nên người dùng thường thấy duyệt `n` bản ghi theo chi phí `O(n)`. Nếu cài đặt thủ công quét cả mảng kích thước `m`, cần tính cả những ô/ngăn trống; vì vậy `O(m+n)` là cách phát biểu thận trọng hơn khi `m` không bị ràng buộc cùng bậc với `n`.

## 4. Min, max, predecessor, successor, rank, select

Trên tập khóa `S=\{3,8,10,12,17\}`:

| Truy vấn | Ý nghĩa | Kết quả |
| --- | --- | --- |
| `min(S)` | Khóa nhỏ nhất | `3` |
| `max(S)` | Khóa lớn nhất | `17` |
| `predecessor(11)` | Khóa lớn nhất **nhỏ hơn** 11 | `10` |
| `successor(11)` | Khóa nhỏ nhất **lớn hơn** 11 | `12` |
| `rank(11)` | Số khóa **nhỏ hơn** 11 | `3` (`3,8,10`) |
| `select(2)` | Khóa ở chỉ số 2 của danh sách tăng dần, đánh số từ 0 | `10` |

Đối với một bảng băm **chỉ có tra cứu theo khóa**, các truy vấn trên thường buộc phải xem nhiều khóa:

**Min/max:** duyệt các khóa để tìm giá trị nhỏ nhất/lớn nhất, mất `O(n)` phép so sánh nếu có iterator các khóa. Với bảng trống, phải trả trạng thái “không có phần tử”.

**Predecessor/successor:** duyệt và giữ ứng viên tốt nhất nhỏ hơn/lớn hơn `x`, mất `O(n)` phép so sánh. Không thể suy ra kết quả từ ngăn `hash(x) mod m`.

**Rank:** đếm bao nhiêu khóa nhỏ hơn `x`; nếu không có thông tin phụ, phải duyệt `O(n)` khóa.

**Select:** có thể sắp xếp tất cả `n` khóa rồi truy cập phần tử thứ `r` trong `O(n\log n)` thời gian, hoặc dùng thuật toán chọn phần tử có thời gian tuyến tính thích hợp; không có cơ sở cho `O(1)` chỉ nhờ vào hashing. Thuật toán chọn cụ thể có thể cho `O(n)` kỳ vọng hoặc `O(n)` xấu nhất với kỹ thuật phù hợp và giả định so sánh.

Điểm chung là hash map không lưu những thông tin như **khóa nhỏ nhất**, **phần tử kề trong thứ tự** hoặc **số phần tử nhỏ hơn một khóa**. Muốn các truy vấn ấy nhanh, cần thêm cấu trúc dữ liệu hoặc ràng buộc chuyên biệt.

## 5. Trật tự duyệt không đồng nghĩa trật tự theo khóa

Ba khái niệm dễ bị lẫn:

1. **Thứ tự theo giá trị khóa (sorted-key order):** `3,8,10,12,17`.
2. **Thứ tự chèn (insertion order):** `10,3,17,8,12`.
3. **Thứ tự duyệt nội bộ (iteration order):** phụ thuộc API và cấu trúc; ví dụ quét ngăn có thể cho `8,10,3,17,12`.

Chúng không bắt buộc giống nhau.

Chẳng hạn, `dict` trong Python hiện đại duy trì **thứ tự chèn** khi duyệt, nhưng **không sắp xếp khóa**:

```python
bang = {}
for k in [10, 3, 17, 8, 12]:
    bang[k] = f"Giá trị {k}"

print(list(bang))
# [10, 3, 17, 8, 12]  -- thứ tự chèn

print(sorted(bang))
# [3, 8, 10, 12, 17]  -- thứ tự tăng theo khóa
```

Một số thư viện map có bảo đảm **thứ tự chèn**, số khác không bảo đảm thứ tự duyệt hoặc có thể thay đổi thứ tự sau resize/rehash. Dù có bảo đảm thứ tự chèn, nó vẫn không suy ra `predecessor`, `rank` hay truy vấn khoảng theo **thứ tự khóa** được xử lý nhanh hơn.

Nếu ứng dụng muốn danh sách khóa tăng dần, `sorted(bang)` trong ví dụ phải **tạo và sắp xếp** danh sách khóa, thường mất `O(n\log n)` thời gian với cách so sánh tổng quát. Lặp lại thao tác này sau mỗi lần thêm sẽ đắt.

## 6. Bảng băm là công cụ mạnh cho những truy vấn nào?

Không nên hiểu “không hỗ trợ truy vấn thứ tự hiệu quả” thành “bảng băm không phù hợp với dữ liệu số hoặc chuỗi”. Hash map thường rất phù hợp nếu bài toán có thao tác chính như:

- `get("SV022")`: lấy hồ sơ theo **mã chính xác**.
- `contains(email)`: kiểm tra một email **có nằm trong tập** không.
- `put(order_id, status)`: cập nhật trạng thái theo **ID đã biết**.
- `remove(session_id)`: thu hồi một phiên theo **khóa chính xác**.
- Đếm tần suất xuất hiện của từng khóa hoặc đối chiếu hai tập khóa.

Lúc này việc không sắp xếp khóa có thể là **lợi thế**: cấu trúc tránh công việc duy trì thứ tự sau mỗi lần thêm/xóa. Dưới giả định phân bố hash tốt và tải được kiểm soát, truy cập chính xác thường có **thời gian kỳ vọng `O(1)`**.

Ngược lại, nếu bài toán thường hỏi “mọi đơn hàng có mã nằm từ A đến B” hoặc “100 bản ghi đầu tiên theo khóa tăng dần”, hash map không phải chỉ mục lý tưởng **khi đứng một mình**.

## 7. Mô phỏng Python: lọc khoảng từ bảng băm và tìm trên mảng đã sắp xếp

Đoạn mã sau xây dựng một hash map nhỏ bằng **nối chuỗi** với khóa nguyên. Để nhìn rõ công việc phải làm, ví dụ ghi nhận **số bản ghi được xem xét** khi lọc khoảng.

```python
from bisect import bisect_left, bisect_right


class BangBamMinhHoa:
    def __init__(self, so_ngan=7):
        if so_ngan <= 0:
            raise ValueError("Số ngăn phải dương")
        self.ngan = [[] for _ in range(so_ngan)]
        self.so_khoa = 0

    def gan(self, khoa: int, gia_tri):
        chuoi = self.ngan[khoa % len(self.ngan)]
        for i, (k_cu, _) in enumerate(chuoi):
            if k_cu == khoa:
                chuoi[i] = (khoa, gia_tri)
                return
        chuoi.append((khoa, gia_tri))
        self.so_khoa += 1

    def lay(self, khoa: int):
        for k_cu, gia_tri in self.ngan[khoa % len(self.ngan)]:
            if k_cu == khoa:
                return gia_tri
        raise KeyError(khoa)

    def ban_ghi(self):
        for chuoi in self.ngan:
            for khoa, gia_tri in chuoi:
                yield khoa, gia_tri

    def trong_khoang(self, trai: int, phai: int):
        if trai > phai:
            return [], 0
        da_xem = 0
        ket_qua = []
        for khoa, gia_tri in self.ban_ghi():
            da_xem += 1
            if trai <= khoa <= phai:
                ket_qua.append((khoa, gia_tri))
        return ket_qua, da_xem


bang = BangBamMinhHoa(7)
for k in [10, 3, 17, 8, 12]:
    bang.gan(k, f"Giá trị {k}")

print(bang.lay(10))  # Giá trị 10
print([[k for k, _ in chuoi] for chuoi in bang.ngan])
# [[], [8], [], [10, 3, 17], [], [12], []]

ket_qua, so_da_xem = bang.trong_khoang(8, 12)
print(so_da_xem)  # 5: đã kiểm tra cả năm khóa
print(sorted(k for k, _ in ket_qua))  # [8, 10, 12]

# Nếu cần nhiều truy vấn khoảng mà tập khóa ít thay đổi:
khoa_tang = sorted(k for k, _ in bang.ban_ghi())
trai = bisect_left(khoa_tang, 8)
phai = bisect_right(khoa_tang, 12)
print(khoa_tang)  # [3, 8, 10, 12, 17]
print(khoa_tang[trai:phai])  # [8, 10, 12]
print(phai - trai)  # 3: số khóa trong khoảng đóng [8, 12]
```

Trong ví dụ:

- Hash map tra khóa chính xác `10` thông qua ngăn `3`.
- Khi lọc `[8,12]`, ví dụ phải xem cả năm khóa trước khi biết ba khóa phù hợp.
- Sau khi tạo **mảng khóa đã sắp xếp**, `bisect_left`/`bisect_right` tìm hai biên trong `O(\log n)` phép so sánh; lấy danh sách gồm `r` kết quả tốn thêm `O(r)`. Nhưng chi phí **xây dựng mảng tăng dần ban đầu** là `O(n\log n)`.

Mã trên chưa duy trì tự động mảng đã sắp xếp khi thêm hoặc xóa. Nếu thêm một khóa vào danh sách Python bằng `list.insert` tại vị trí do `bisect` tìm ra, việc **dời các phần tử trong mảng** có thể tốn `O(n)` dù tìm vị trí chỉ mất `O(\log n)`.

## 8. So sánh với những cấu trúc duy trì thứ tự

Nếu truy vấn thứ tự là trọng tâm, nên cân nhắc một cấu trúc **có thông tin thứ tự**. Bảng sau giả sử các khóa so sánh được với chi phí `O(1)`, có `n` phần tử và truy vấn khoảng trả `r` kết quả:

| Cấu trúc | Tra cứu chính xác | Thêm/xóa | Truy vấn khoảng có thứ tự | Ghi chú |
| --- | --- | --- | --- | --- |
| **Hash map thông thường** | Kỳ vọng `O(1)` | Kỳ vọng `O(1)` khi quản lý tải và resize phù hợp | Thường phải quét `O(n)` khóa, có thể cần sắp xếp kết quả | Không duy trì thứ tự khóa |
| **Cây tìm kiếm nhị phân cân bằng** (AVL, Red–Black Tree) | `O(\log n)` xấu nhất | `O(\log n)` xấu nhất | `O(\log n+r)` | Duyệt trung thứ tự có khóa tăng dần |
| **Mảng khóa đã sắp xếp** | `O(\log n)` bằng tìm nhị phân | Thường `O(n)` do phải dời phần tử | `O(\log n+r)` | Hợp với dữ liệu ít thay đổi |
| **B-tree/B+tree** | Thường `O(\log n)` bước nút trong mô hình RAM | Thường `O(\log n)` bước nút | Tìm biên rồi duyệt các mục liên tiếp hiệu quả | Phù hợp lưu trữ theo khối, cơ sở dữ liệu |
| **Skip list có thứ tự** | Kỳ vọng `O(\log n)` | Kỳ vọng `O(\log n)` | Kỳ vọng `O(\log n+r)` | Ngẫu nhiên hóa các mức liên kết |

Với B-tree/B+tree trên ổ đĩa, phân tích còn xét số lần **đọc/ghi khối**; cơ số phân nhánh lớn làm chiều cao thấp. Không nên đồng nhất ngay số bước nút với độ trễ thực tế của mọi hệ thống lưu trữ.

Một số chi tiết bổ sung:

- **`min/max` trong cây cân bằng:** đi theo nhánh trái nhất/phải nhất, thường `O(\log n)` xấu nhất; có thể đạt `O(1)` nếu duy trì con trỏ đến cực trị.
- **`predecessor/successor`:** trong cây cân bằng thường `O(\log n)`; với mảng tăng dần, dùng tìm nhị phân cũng `O(\log n)`.
- **`rank/select`:** cây cân bằng thông thường **không tự động** có cận `O(\log n)` cho cả hai. Nếu mỗi nút lưu thêm **số phần tử trong cây con** (*subtree size*) và cập nhật đúng sau xoay/chèn/xóa, có thể thực hiện `rank` và `select` trong `O(\log n)`.
- **`rank/select` trên mảng tăng dần:** `rank(x)` dùng tìm nhị phân `O(\log n)`; `select(r)` là truy cập chỉ số `O(1)` nếu chỉ số hợp lệ.

Lựa chọn phụ thuộc tỷ lệ truy vấn theo khóa chính xác so với truy vấn thứ tự, tần suất cập nhật, yêu cầu bộ nhớ và môi trường lưu trữ.

## 9. Có thể kết hợp hash map với chỉ mục thứ tự không?

Có. Một hệ thống có thể đồng thời duy trì:

1. **Hash map:** từ khóa đến bản ghi, phục vụ tra cứu chính xác nhanh theo kỳ vọng.
2. **Chỉ mục có thứ tự:** từ khóa tăng dần đến bản ghi hoặc tham chiếu, phục vụ truy vấn khoảng, predecessor/successor.

```text
                         +-------------------------+
get(k) ----------------> | Hash map: k -> record   |
                         +-------------------------+
                                      ^
                                      | cùng tập bản ghi
                                      v
range(a,b) ------------> +-------------------------+
                         | Ordered index of keys   |
                         | 3 - 8 - 10 - 12 - 17   |
                         +-------------------------+
```

**Đánh đổi:** duy trì thêm chỉ mục cần bộ nhớ `O(n)` và chi phí chèn/xóa cập nhật cả hai cấu trúc. Nếu chỉ mục là cây cân bằng, một lần thay đổi thường cần thêm `O(\log n)` để cập nhật cây; vì vậy không còn thể nói thao tác cập nhật **toàn hệ thống** có chi phí `O(1)`.

Hai chỉ mục cũng phải **nhất quán**. Nếu chèn vào hash map thành công nhưng chưa thêm khóa vào cây, tra cứu chính xác sẽ thấy bản ghi còn truy vấn khoảng lại bỏ sót nó. Một thiết kế thực tế cần quy định cơ chế cập nhật nguyên tử, phục hồi khi có lỗi, hoặc quy trình đồng bộ có kiểm soát.

Đối với hệ thống có rất ít cập nhật nhưng nhiều truy vấn khoảng, có thể chọn mảng khóa tăng dần được làm mới theo lô. Đối với hệ thống có nhiều cập nhật và cần truy vấn khoảng tức thời, một cấu trúc chỉ mục thứ tự cập nhật động (như cây cân bằng hoặc B+tree) thường phù hợp hơn.

## 10. Ngoại lệ và cấu trúc chuyên biệt

Không nên phát biểu quá mức rằng **mọi** cấu trúc dựa trên hashing đều hoàn toàn không thể trả lời truy vấn có thứ tự. Một số hệ thống kết hợp nhiều chỉ mục hoặc duy trì các thống kê bổ sung; một số trường hợp khóa có miền nhỏ, dày đặc còn có thể dùng:

- **Mảng đánh dấu hoặc direct addressing:** dùng chính khóa nguyên trong miền `[0,U)` làm chỉ số, sau đó quét miền hoặc duy trì bitset để hỗ trợ thao tác khác. Đổi lại, bộ nhớ có thể phụ thuộc `U` thay vì `n`.
- **Bitset/cây Fenwick/cây đoạn:** nếu khóa nằm trong miền nguyên hữu hạn có thể ánh xạ ổn định, các cấu trúc hỗ trợ đếm tiền tố, tìm phần tử thứ `r` và truy vấn đoạn tùy biến. Chúng có ràng buộc và độ phức tạp riêng.
- **Hash map có ordered index bổ sung:** không còn là hash map đơn thuần; hiệu năng truy vấn thứ tự đến từ **chỉ mục thứ tự bổ sung**.

Vì vậy, kết luận chính xác là: **bảng băm thông thường không hỗ trợ hiệu quả truy vấn thứ tự chỉ nhờ phép băm**. Nếu truy vấn ấy là yêu cầu cốt lõi, cần thiết kế một cấu trúc duy trì quan hệ thứ tự hoặc dùng giải pháp kết hợp.

## 11. Bất biến và các ngộ nhận thường gặp

Khi chọn và triển khai cấu trúc dữ liệu, hãy kiểm tra:

1. **Hàm băm không phải hàm xếp hạng:** `hash(k)` không cho biết bao nhiêu khóa nhỏ hơn `k`.
2. **Chỉ số ngăn không phải thứ tự khóa:** quét các ngăn từ 0 đến `m-1` không sinh danh sách khóa tăng dần.
3. **Thứ tự chèn không phải thứ tự sắp xếp:** map bảo toàn insertion order vẫn không hỗ trợ `lower_bound` chỉ từ hashing.
4. **`O(1)` kỳ vọng của tìm khóa không chuyển sang truy vấn khoảng:** truy vấn khoảng đòi hỏi biết quan hệ giữa các khóa chưa cho trước.
5. **Đầu ra `r` phần tử cần ít nhất `\Omega(r)` công ghi kết quả:** ngay cả chỉ mục tốt cũng không thể trả danh sách dài mà hoàn toàn `O(1)`.
6. **Thêm chỉ mục đồng nghĩa thêm chi phí duy trì:** không chỉ đo thời gian `get` rồi bỏ qua thời gian cập nhật, bộ nhớ và tính nhất quán.
7. **Khóa phải có quan hệ thứ tự rõ ràng:** cây cân bằng cần phép so sánh tạo thứ tự hợp lệ; hash map chỉ cần hợp đồng `hash/equality` phù hợp.
8. **Tải và va chạm vẫn quan trọng:** ngay cả cho tra cứu chính xác, `O(1)` là kỳ vọng dưới giả định phân bố tốt, không phải bảo đảm xấu nhất.

## 12. Tự kiểm tra

**Câu 1.** Vì sao hai khóa `3` và `10` cùng nằm ở ngăn `3` trong bảng `m=7` không có nghĩa chúng đứng cạnh nhau trong thứ tự tăng dần?

**Đáp án:** Ngăn được xác định bằng `k mod 7`, không theo quan hệ `<`. Có thể còn các khóa như `8` nằm giữa `3` và `10` trong thứ tự tăng dần nhưng lại thuộc ngăn khác.

**Câu 2.** Hash map chứa `n=1000` khóa, cần trả tất cả khóa trong `[200,300]`. Nếu không có chỉ mục thứ tự phụ, vì sao thường phải quét toàn bộ các khóa?

**Đáp án:** Hash không cho biết khóa nào thuộc khoảng dựa trên chỉ số ngăn; phải kiểm tra điều kiện khoảng cho từng khóa. Nếu quét các bản ghi, cần `O(n)` phép kiểm tra, chưa tính sắp xếp kết quả.

**Câu 3.** Một `dict` Python duyệt theo thứ tự chèn. Điều đó có đủ để tìm `predecessor(50)` trong `O(1)` không?

**Đáp án:** Không. Insertion order không phải sorted-key order; cần quét, tạo chỉ mục được sắp xếp hoặc dùng cấu trúc duy trì thứ tự.

**Câu 4.** Cho `S=\{3,8,10,12,17\}`. Tính `rank(11)`, `predecessor(11)`, `successor(11)` và `select(2)` với chỉ số bắt đầu từ 0.

**Đáp án:** `rank(11)=3`; predecessor là `10`; successor là `12`; `select(2)=10`.

**Câu 5.** Vì sao cây tìm kiếm nhị phân cân bằng có thể trả `r` khóa trong một khoảng với độ phức tạp `O(\log n+r)`, còn hash map thông thường thường phải xem nhiều khóa hơn?

**Đáp án:** Cây dùng quan hệ thứ tự để tìm biên của khoảng trong `O(\log n)`, rồi duyệt liên tiếp những khóa hợp lệ; hash map không có cấu trúc phân nhánh theo `<` để bỏ qua toàn bộ các khóa nằm ngoài khoảng.

**Câu 6.** Mảng khóa đã sắp xếp cho truy vấn khoảng nhanh. Vì sao không mặc nhiên dùng mảng này cho mọi ứng dụng có thêm/xóa liên tục?

**Đáp án:** Tìm vị trí bằng binary search chỉ tốn `O(\log n)`, nhưng chèn/xóa trong mảng thường phải dời `O(n)` phần tử, làm cập nhật đắt.

**Câu 7.** Một hệ thống dùng cả hash map và cây cân bằng. `get(k)` có thể kỳ vọng `O(1)`; có thể khẳng định `put` cập nhật cả hai cấu trúc cũng kỳ vọng `O(1)` không?

**Đáp án:** Không. Cần duy trì thêm chỉ mục cây trong `O(\log n)` và giữ hai chỉ mục nhất quán, nên chi phí thao tác cập nhật toàn hệ thống khác với chi phí riêng hash map.

**Ghi nhớ:** **Bảng băm tối ưu tra cứu chính xác theo khóa, không duy trì trật tự tăng dần của khóa**. Vì thế `min/max`, `predecessor/successor`, `rank/select` và truy vấn khoảng thường đòi hỏi quét nhiều phần tử hoặc tạo thêm chỉ mục. Nếu cần truy vấn theo thứ tự thường xuyên, hãy chọn **cây tìm kiếm cân bằng, B+tree, mảng sắp xếp** hoặc **kết hợp hash map với chỉ mục thứ tự**, và tính cả chi phí cập nhật, bộ nhớ, tính nhất quán.
