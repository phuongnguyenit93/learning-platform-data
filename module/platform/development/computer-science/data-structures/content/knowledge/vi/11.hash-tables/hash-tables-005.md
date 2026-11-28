# Va chạm và giải quyết bằng chuỗi liên kết

## 1. Va chạm là điều không thể tránh khỏi

Trong **bảng băm (hash table)**, ta lưu dữ liệu dưới dạng cặp **khóa–giá trị** và dùng hàm băm để định vị khóa nhanh. Giả sử mảng nền có `m > 0` ngăn (bucket), với chỉ số từ `0` đến `m - 1`. Một cách ánh xạ đơn giản là:

\[
i(k) = h(k) \bmod m
\]

trong đó `h(k)` là mã băm của khóa `k`, còn `i(k)` là **chỉ số ngăn**. Vì số ngăn hữu hạn, các khóa khác nhau hoàn toàn có thể cho cùng chỉ số. Đây là **va chạm tại ngăn (bucket collision)**.

Ví dụ, cho bảng có **5 ngăn** và các khóa nguyên không âm dùng `h(k) = k`:

| Khóa `k` | Mã băm `h(k)` | `h(k) mod 5` | Ngăn |
| ---: | ---: | ---: | ---: |
| 11 | 11 | 1 | 1 |
| 16 | 16 | 1 | 1 |
| 21 | 21 | 1 | 1 |
| 32 | 32 | 2 | 2 |

Ba khóa `11`, `16`, `21` khác nhau, mã băm cũng khác nhau, nhưng cùng đi vào ngăn 1. Nếu chỉ lưu một cặp trên mỗi ngăn và ghi đè khi có va chạm, ta sẽ làm mất dữ liệu. Bảng băm phải có **chiến lược giải quyết va chạm** để giữ đủ các cặp và tìm lại đúng khóa.

**Chuỗi liên kết (separate chaining)** là một chiến lược trực quan: mỗi ngăn không trực tiếp chứa duy nhất một cặp, mà giữ một **chuỗi các cặp khóa–giá trị**. Một cách cài đặt phổ biến là dùng **danh sách liên kết đơn**.

## 2. Cấu trúc của một ngăn có chuỗi liên kết

Trong cách cài đặt dùng danh sách liên kết, mỗi ô của mảng nền lưu **tham chiếu đến nút đầu** (head) của một chuỗi. Mỗi nút trong chuỗi gồm:

- `key`: khóa của bản ghi;
- `value`: giá trị ứng với khóa;
- `next`: tham chiếu tới nút kế tiếp, hoặc `None/null` nếu đây là nút cuối.

Với ví dụ `m = 5`, bảng có thể trông như sau sau khi thêm các cặp `(11, "A")`, `(16, "B")`, `(21, "C")` và `(32, "D")`:

```text
Mảng các ngăn          Chuỗi liên kết trong từng ngăn

   [0]  ─────────────>  None
   [1]  ─────────────>  (21, "C") ──> (16, "B") ──> (11, "A") ──> None
   [2]  ─────────────>  (32, "D") ──> None
   [3]  ─────────────>  None
   [4]  ─────────────>  None
```

Ở đây các khóa mới được **chèn vào đầu chuỗi**, nên `21` đứng trước `16` và `11`. Đây là lựa chọn cài đặt để chèn nút nhanh; một bảng băm khác có thể đặt nút mới ở cuối hoặc dùng một cấu trúc khác trong từng ngăn.

Điều cần phân biệt:

- **Ngăn số 1** chỉ cho biết nơi bắt đầu tìm kiếm. Nó không nói ngăn chứa bao nhiêu khóa và không đại diện cho một khóa duy nhất.
- **Nút của chuỗi** chứa cặp khóa–giá trị thật. Cần so sánh `key` trong nút khi tìm, sửa hoặc xóa.
- **Danh sách liên kết** cho phép thêm/xóa nút bằng thay đổi tham chiếu. Tuy nhiên, muốn tìm một khóa trong chuỗi thì vẫn phải duyệt các nút cần thiết.

## 3. Ba thao tác chính trên chuỗi

Giả sử `i = h(k) mod m`. Mọi thao tác bắt đầu bằng việc tính ngăn `i`, sau đó làm việc trong **chuỗi của ngăn đó**.

### 3.1. Thêm hoặc cập nhật: `put(k, v)`

Đối với cấu trúc map, mỗi **khóa logic** chỉ có một giá trị đang hiệu lực. Vì vậy, thêm khóa phải kiểm tra xem khóa đã có chưa:

1. Tính chỉ số ngăn `i`.
2. Duyệt chuỗi tại `buckets[i]`, so sánh khóa của từng nút với `k`.
3. Nếu gặp nút có khóa bằng `k`, **cập nhật `value`** của nút đó và dừng.
4. Nếu duyệt hết mà chưa thấy `k`, tạo nút `(k, v)` mới và liên kết nó vào chuỗi; có thể chèn ở đầu.

Ví dụ, sau khi đã có `(11, "A")` và `(16, "B")` tại ngăn 1, gọi `put(16, "B2")` phải làm giá trị của khóa 16 thành `"B2"`, **không tạo nút 16 thứ hai**.

```text
Trước: (16, "B")  ──> (11, "A") ──> None
Sau:   (16, "B2") ──> (11, "A") ──> None
```

Nếu chỉ muốn lưu tập khóa (hash set), thao tác thêm cũng cần kiểm tra khóa đã tồn tại để không tạo bản sao logic.

### 3.2. Tìm kiếm: `get(k)`

1. Tính ngăn của `k`.
2. Duyệt từ nút đầu của ngăn đó.
3. Khi thấy nút có `node.key == k`, trả về `node.value`.
4. Nếu đến cuối chuỗi mà không có khóa phù hợp, kết luận khóa không tồn tại.

Ví dụ, tìm `16` trong chuỗi `21 → 16 → 11` phải kiểm tra nút 21 trước, rồi đến nút 16. Không được trả kết quả chỉ vì các nút cùng nằm ở ngăn 1.

Khi khóa có thể ánh xạ vào cùng ngăn, **mã băm bằng nhau hoặc chỉ số bằng nhau không đủ chứng minh hai khóa bằng nhau**. Bước kiểm tra `node.key == k` là bắt buộc để chọn đúng bản ghi.

### 3.3. Xóa: `remove(k)`

Để xóa đúng nút trong danh sách liên kết đơn, cần theo dõi **nút hiện tại** (`current`) và **nút đứng trước** (`previous`):

- Nếu nút cần xóa là **đầu chuỗi**, cập nhật `buckets[i] = current.next`.
- Nếu nó ở **giữa hoặc cuối chuỗi**, cập nhật `previous.next = current.next`.
- Nếu không tìm thấy khóa, không thay đổi cấu trúc; API có thể trả về trạng thái không tìm thấy hoặc phát sinh ngoại lệ.

Ví dụ xóa khóa `21` (nút đầu) khỏi chuỗi:

```text
Trước: head ──> (21, "C") ──> (16, "B") ──> (11, "A") ──> None
Sau:   head ─────────────────> (16, "B") ──> (11, "A") ──> None
```

Nếu sau đó xóa khóa `11` (nút cuối), ta đặt `next` của nút 16 về `None`. Xóa nút duy nhất trong chuỗi phải làm tham chiếu đầu ngăn trở thành `None`.

## 4. Cài đặt Python với danh sách liên kết thật

Ví dụ dưới đây dùng khóa nguyên `int` với phép tính chỉ số `k % so_ngan`. Python luôn cho `k % m` nằm trong `0..m-1` khi `m` dương, kể cả nếu `k` âm. Để tập trung vào **cách giải quyết va chạm**, ví dụ giữ dung lượng cố định và chưa tự mở rộng bảng.

```python
class Nut:
    def __init__(self, khoa: int, gia_tri, nut_sau=None):
        self.khoa = khoa
        self.gia_tri = gia_tri
        self.nut_sau = nut_sau


class BangBamNoiChuoi:
    def __init__(self, so_ngan=5):
        if so_ngan <= 0:
            raise ValueError("Số ngăn phải lớn hơn 0")
        self.ngan = [None] * so_ngan
        self.so_phan_tu = 0

    def _chi_so(self, khoa: int) -> int:
        return khoa % len(self.ngan)

    def gan(self, khoa: int, gia_tri):
        i = self._chi_so(khoa)
        nut = self.ngan[i]
        while nut is not None:
            if nut.khoa == khoa:
                nut.gia_tri = gia_tri   # Khóa đã có: cập nhật
                return
            nut = nut.nut_sau

        # Khóa mới: chèn nút vào đầu chuỗi tại ngăn i.
        self.ngan[i] = Nut(khoa, gia_tri, self.ngan[i])
        self.so_phan_tu += 1

    def lay(self, khoa: int):
        nut = self.ngan[self._chi_so(khoa)]
        while nut is not None:
            if nut.khoa == khoa:
                return nut.gia_tri
            nut = nut.nut_sau
        raise KeyError(khoa)

    def xoa(self, khoa: int):
        i = self._chi_so(khoa)
        truoc = None
        hien_tai = self.ngan[i]
        while hien_tai is not None:
            if hien_tai.khoa == khoa:
                if truoc is None:  # Xóa nút đầu
                    self.ngan[i] = hien_tai.nut_sau
                else:             # Xóa nút giữa hoặc cuối
                    truoc.nut_sau = hien_tai.nut_sau
                self.so_phan_tu -= 1
                return hien_tai.gia_tri
            truoc = hien_tai
            hien_tai = hien_tai.nut_sau
        raise KeyError(khoa)

    def xem_ngan(self, i: int):
        ket_qua = []
        nut = self.ngan[i]
        while nut is not None:
            ket_qua.append((nut.khoa, nut.gia_tri))
            nut = nut.nut_sau
        return ket_qua


bang = BangBamNoiChu(5)
bang.gan(11, "A")
bang.gan(16, "B")
bang.gan(21, "C")
print(bang.xem_ngan(1))
# [(21, 'C'), (16, 'B'), (11, 'A')]

print(bang.lay(16))  # B
bang.gan(16, "B2")
print(bang.xem_ngan(1))
# [(21, 'C'), (16, 'B2'), (11, 'A')]

print(bang.xoa(21))  # C: xóa nút đầu
print(bang.xoa(11))  # A: xóa nút cuối
print(bang.xem_ngan(1))
# [(16, 'B2')]
print(bang.so_phan_tu)  # 1
```

Nếu gọi `bang.lay(21)` sau khi đã xóa khóa 21, phương thức sẽ phát sinh `KeyError(21)`. Đó là cách API minh họa biểu diễn “khóa không tồn tại”; các thư viện có thể chọn cách trả giá trị mặc định khác.

Đoạn mã không dùng danh sách Python để **lưu các cặp trong ngăn**: mỗi ngăn giữ tham chiếu đến `Nut` đầu, các `Nut` nối với nhau qua `nut_sau`. Danh sách Python mà `xem_ngan` trả về chỉ phục vụ quan sát chuỗi trong ví dụ.

## 5. Những bất biến giữ cho thao tác đúng

Một cài đặt dùng chuỗi liên kết phải bảo đảm các **bất biến** sau sau mỗi thao tác:

1. **Đúng ngăn:** Mọi nút có khóa `k` đều nằm trong chuỗi mà phép định vị của `k` dẫn đến, tính theo dung lượng và hàm băm hiện tại.
2. **Không trùng khóa logic:** Với map, mỗi khóa logic có nhiều nhất một nút. Khi gán lại khóa đã tồn tại, thay đổi giá trị của nút đó.
3. **Nhất quán băm và so sánh:** Hai khóa được xem là bằng nhau phải có mã băm nhất quán để dẫn đến cùng ngăn; khóa khác nhau có thể cùng ngăn.
4. **Liên kết không bị đứt:** Chèn hoặc xóa chỉ sửa các con trỏ cần thiết; những nút còn lại trong chuỗi vẫn truy cập được từ `head`.
5. **Đếm phần tử chính xác:** Chỉ tăng số phần tử khi thêm khóa mới; chỉ giảm khi thực sự xóa được khóa, và không đổi khi cập nhật giá trị.
6. **Khóa ổn định:** Những thuộc tính dùng để so sánh và băm không bị thay đổi ngoài ý muốn trong khi khóa đang nằm trong bảng.

Sai lầm thường gặp là viết thao tác `gan` luôn chèn ở đầu mà không kiểm tra khóa cũ. Khi đó, một map có thể chứa nhiều nút cho cùng khóa và `lay` trả về giá trị của nút gặp trước, tạo ra hành vi khó dự đoán sau các lần cập nhật hoặc xóa.

Một lỗi khác là xóa nút đầu bằng `truoc.nut_sau = hien_tai.nut_sau` khi `truoc` vẫn là `None`. Trường hợp này phải cập nhật trực tiếp tham chiếu `head` trong mảng ngăn.

## 6. Độ phức tạp phụ thuộc độ dài chuỗi

Gọi:

- `n` là tổng số cặp khóa–giá trị trong bảng;
- `m` là số ngăn;
- `α = n/m` là **hệ số tải** (load factor);
- `ℓ_i` là số nút trong chuỗi của ngăn `i`.

Tính chỉ số ngăn cho khóa nguyên có thể xem là `O(1)`; phần còn lại tốn thời gian tỷ lệ với số nút cần duyệt trong chuỗi liên quan:

| Thao tác | Nếu chuỗi có `ℓ` nút | Trung bình kỳ vọng dưới giả định phân bố đều | Trường hợp xấu nhất |
| --- | --- | --- | --- |
| `lay(k)`, có hoặc không có khóa | `O(1 + ℓ)` | `O(1 + α)` | `O(n)` |
| `gan(k, v)` có kiểm tra khóa cũ | `O(1 + ℓ)` | `O(1 + α)` | `O(n)` |
| `xoa(k)` phải tìm đúng nút | `O(1 + ℓ)` | `O(1 + α)` | `O(n)` |
| Chèn một nút mới **khi đã biết khóa chưa tồn tại** vào đầu chuỗi | `O(1)` | `O(1)` | `O(1)` |

**Giả định phân bố đều** nghĩa là các khóa được phân vào ngăn đủ đồng đều theo một mô hình xác suất; trong mô hình băm đều đơn giản, số khóa kỳ vọng trong một ngăn là `n/m = α`. Không phải mọi hàm băm thực tế hay mọi tập khóa đều đáp ứng mô hình ấy.

Nếu `α` được giữ ở mức hằng số nhờ tăng dung lượng hợp lý, các thao tác tra cứu/cập nhật/xóa có **thời gian kỳ vọng `O(1)`** khi coi việc băm và so sánh khóa là hằng số. Tuy nhiên, trường hợp xấu nhất vẫn là **`O(n)`** nếu tất cả `n` khóa dồn về một ngăn.

Nếu khóa là chuỗi dài `L` ký tự, tính mã băm từ đầu thường cần `O(L)`; các lần so sánh khóa có thể tốn thêm thời gian. Vì vậy, phát biểu `O(1)` thường nói đến chi phí định vị và xử lý chuỗi **theo giả định chi phí băm và so sánh khóa là hằng số**, hoặc tách riêng chi phí của khóa dài.

**Bộ nhớ:** mảng các đầu ngăn chiếm `O(m)`; các nút chiếm `O(n)`. Tổng bộ nhớ phụ trợ là `O(m+n)`, chưa tính kích thước dữ liệu khóa/giá trị và chi tiết cấp phát. Mỗi nút cần thêm tham chiếu `next`, nên có chi phí bộ nhớ và cấp phát nút.

## 7. Hệ số tải và mở rộng bảng khi chuỗi quá dài

Một ưu điểm của separate chaining là **`α` có thể lớn hơn 1**: bảng 5 ngăn vẫn có thể lưu 20 khóa, vì mỗi ngăn được phép giữ nhiều nút. Tuy vậy, `α = 20/5 = 4` cho thấy mỗi ngăn có trung bình 4 khóa; nếu phân bố không tốt, một số chuỗi có thể còn dài hơn.

Khi số khóa tăng, bảng thường mở rộng số ngăn `m` và **phân bố lại (rehash) các nút** theo số ngăn mới:

```text
Khóa 11: 11 mod 5  = 1
         11 mod 10 = 1

Khóa 16: 16 mod 5  = 1
         16 mod 10 = 6

Khóa 21: 21 mod 5  = 1
         21 mod 10 = 1
```

Ở bảng 5 ngăn, cả ba khóa cùng chuỗi ngăn 1. Khi có 10 ngăn, khóa 16 chuyển sang ngăn 6. Nếu chỉ tạo thêm ô rỗng mà **không chuyển những nút cần chuyển**, thao tác tìm `16` theo số ngăn mới sẽ không tìm thấy bản ghi cũ.

Một đợt mở rộng phải duyệt các bản ghi và phân bố lại theo chỉ số hiện hành; chi phí có thể là `O(n + m_{mới})` để phân phối `n` nút và chuẩn bị bảng mới. Khi tăng kích thước theo cấp số nhân, chi phí của các lần mở rộng có thể được **phân bổ (amortized)** trên nhiều lần thêm. Phân tích `O(1)` kỳ vọng, phân bổ cho thao tác thêm còn phụ thuộc quy tắc mở rộng, phân bố khóa và chi phí băm.

Không nên chỉ nhìn `α` rồi kết luận các chuỗi đang ngắn. Ví dụ hai bảng đều có `n = 10` và `m = 10` nên `α = 1`; bảng thứ nhất có mỗi ngăn đúng một khóa, bảng thứ hai có một ngăn chứa 10 khóa và chín ngăn rỗng. Chất lượng hàm băm quyết định sự khác biệt này.

## 8. Khi nào phù hợp với chuỗi liên kết?

| Khía cạnh | Giải quyết bằng chuỗi liên kết | So sánh với địa chỉ mở (open addressing) |
| --- | --- | --- |
| Nơi đặt phần tử | Các nút nằm trong chuỗi của một ngăn | Các phần tử nằm trong chính các ô của bảng, tìm ô thay thế khi va chạm |
| Số phần tử so với số ngăn | Có thể nhiều hơn số ngăn (`α > 1`) | Cần có ô trống để thêm khóa mới (`α < 1` ở bảng đang hoạt động) |
| Xóa | Gỡ nút và nối lại chuỗi | Phải giữ quy tắc thăm dò hợp lệ, đôi khi cần dấu đã xóa |
| Chi phí bộ nhớ | Mảng ngăn cộng nút và các liên kết | Có thể ít chi phí con trỏ hơn, nhưng cần quản lý ô trống/ô đã xóa |
| Truy cập bộ nhớ | Duyệt các nút có thể nằm rải rác, bất lợi cho locality | Dữ liệu trong mảng thường có locality tốt hơn |

Chuỗi liên kết thích hợp khi muốn cài đặt cơ chế va chạm đơn giản, việc xóa phổ biến hoặc số phần tử thay đổi trong phạm vi rộng. Chi phí cấp phát nút và truy cập bộ nhớ rời rạc có thể khiến nó kém hiệu quả trong một số ứng dụng; cần đánh giá bằng đặc tính dữ liệu và yêu cầu cụ thể.

Thư viện thực tế không bắt buộc dùng danh sách liên kết đơn cho mọi ngăn: có thể dùng mảng động, cấu trúc cân bằng hoặc chiến lược đặc biệt khi chuỗi dài. Ở bài này, **danh sách liên kết đơn** là một cách học rõ ràng nhất về nguyên lý separate chaining.

## 9. Tự kiểm tra

**Câu 1.** Bảng có `m = 7`, lấy `h(k) = k` với khóa nguyên không âm. Các khóa `8`, `15`, `22` thuộc ngăn nào? Cần phân biệt chúng ra sao?

**Đáp án:** Cả ba thuộc ngăn 1 vì có cùng số dư 1 khi chia 7. Có thể giữ ba nút trong cùng chuỗi, mỗi nút lưu khóa đầy đủ. Khi tìm phải so sánh khóa, không thể chỉ nhìn chỉ số ngăn.

**Câu 2.** Chuỗi ngăn 2 là `(12, "A") → (22, "B") → None`. Gọi `put(22, "C")` trên map đúng chuẩn sẽ cho kết quả nào?

**Đáp án:** Nút khóa 22 được cập nhật thành `(22, "C")`, số khóa không đổi. Không thêm nút 22 thứ hai.

**Câu 3.** Chuỗi đang là `A → B → C → None`. Khi xóa nút `B`, cần sửa tham chiếu nào? Khi xóa `A` thì sao?

**Đáp án:** Xóa `B`: đặt `A.next = C`. Xóa `A`: cập nhật `head = B` (trong chuỗi ban đầu). Cả hai thao tác đều phải giữ các nút còn lại truy cập được từ head.

**Câu 4.** Một bảng có `n = 24` khóa và `m = 8` ngăn, xử lý va chạm bằng nối chuỗi. `α` là bao nhiêu? Bảng có lưu được 24 khóa không?

**Đáp án:** `α = 24/8 = 3`. Vẫn lưu được, vì mỗi ngăn có thể chứa nhiều nút; nhưng số nút trung bình mỗi ngăn là 3 và việc tìm kiếm có thể tốn nhiều phép so sánh hơn.

**Câu 5.** Vì sao việc mở rộng bảng từ 5 lên 10 ngăn phải xét lại vị trí các nút?

**Đáp án:** Chỉ số tính bằng `h(k) mod m` phụ thuộc `m`. Ví dụ khóa 16 chuyển từ ngăn 1 sang ngăn 6; nếu không chuyển nó, tra cứu sẽ đến sai chuỗi.

**Ghi nhớ:** Va chạm là nhiều khóa hướng đến cùng ngăn; **nối chuỗi** giữ các bản ghi đó trong một danh sách liên kết của ngăn. Chương trình tính đúng ngăn rồi **duyệt và so sánh khóa**, cập nhật thay vì tạo trùng, nối lại liên kết khi xóa, và phân bố lại nút khi đổi dung lượng. Với phân bố khóa phù hợp và hệ số tải được kiểm soát, thao tác có thời gian kỳ vọng tốt dù va chạm vẫn xảy ra.
