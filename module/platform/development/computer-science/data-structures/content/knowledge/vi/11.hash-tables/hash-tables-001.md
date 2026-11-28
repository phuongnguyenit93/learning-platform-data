# Ý tưởng ánh xạ khóa vào vị trí lưu trữ bằng hàm băm

## 1. Từ chỉ số mảng đến khóa có ý nghĩa

Một **mảng** cho phép truy cập nhanh phần tử khi đã biết chỉ số: `a[3]` lấy phần tử ở vị trí số 3. Nhưng trong nhiều bài toán, thứ ta có lại là một **khóa** như mã sinh viên `"SV1024"`, tên người dùng `"lan"` hoặc mã đơn hàng `"DH-57"`. Ta muốn hỏi: *Giá trị gắn với khóa này đang ở đâu?*

Có thể lưu các cặp `(khóa, giá trị)` vào danh sách rồi dò lần lượt; cách này phải xem tới `n` phần tử trong trường hợp xấu nhất, tức `O(n)`. Nếu ánh xạ trực tiếp mã số thành chỉ số mảng, khóa lớn hoặc thưa (chẳng hạn `1000000007`) lại gây lãng phí không gian. **Bảng băm (hash table)** giải quyết vấn đề bằng cách tính vị trí lưu trữ từ khóa, thay vì phải dò toàn bộ danh sách.

Ví dụ về dữ liệu thường đưa vào bảng băm:

| Khóa | Giá trị đi kèm | Nhu cầu tra cứu |
| --- | --- | --- |
| `"SV1024"` | Hồ sơ sinh viên | Tìm hồ sơ theo mã |
| `"lan"` | Thông tin tài khoản | Tìm người dùng theo tên đăng nhập |
| `"cau_truc_du_lieu"` | Số lần xuất hiện | Đếm tần suất từ khóa |

Đích đến là một cấu trúc dạng `khóa → giá trị` (map/dictionary). Nếu chỉ cần ghi nhận sự tồn tại của khóa, ta có thể dùng tập hợp dựa trên băm (hash set); ý tưởng định vị khóa vẫn tương tự.

## 2. Đường đi từ khóa đến ngăn lưu trữ

Giả sử bảng có `m` **ngăn** (bucket), được đánh số `0, 1, ..., m-1`, với `m > 0`. Một **hàm băm** `h` nhận khóa `k` và tạo ra giá trị băm. Ta chuyển giá trị đó thành chỉ số ngăn, thường bằng phép lấy phần dư:

```text
Khóa k  ──>  Hàm băm h(k)  ──>  h(k) mod m  ──>  Ngăn trong bảng
                         giá trị băm       chỉ số 0..m-1
```

Viết ngắn gọn:

\[
\operatorname{index}(k) = h(k) \bmod m
\]

Phân biệt ba thứ quan trọng:

- **Khóa** là định danh mà chương trình dùng để tìm dữ liệu, ví dụ `"SV1024"`.
- **Giá trị băm** là số do `h(k)` tính ra; số này có thể rất lớn.
- **Chỉ số ngăn** là vị trí trong mảng nền có `m` ngăn, sau khi đưa giá trị băm vào phạm vi `0..m-1`.

Vì thế, hàm băm không nhất thiết trả về địa chỉ bộ nhớ, và `h(k)` không nhất thiết chính là chỉ số mảng. Phép ánh xạ giúp **thu hẹp phạm vi cần tìm**: với một khóa đã biết, chương trình đến ngay ngăn tương ứng, rồi xác định cặp khóa–giá trị cần lấy trong ngăn đó.

### Ví dụ từng bước với khóa số

Xét một bảng có `m = 8` ngăn. Để minh họa, lấy `h(k) = k` cho khóa là số nguyên không âm:

- Khóa `27`: `index(27) = 27 mod 8 = 3`.
- Khóa `35`: `index(35) = 35 mod 8 = 3`.

Cả hai khóa đều hướng đến ngăn số 3:

```text
Chỉ số ngăn   Nội dung minh họa
     0        [ ]
     1        [ ]
     2        [ ]
     3        [(27, "A"), (35, "B")]
     4        [ ]
     5        [ ]
     6        [ ]
     7        [ ]
```

Khi tìm khóa `35`, ta tính được ngăn 3, nhưng vẫn phải **so sánh khóa** trong ngăn để phân biệt `(35, "B")` với `(27, "A")`. Đây chính là lý do bảng băm cần cơ chế xử lý va chạm.

## 3. Hàm băm cần đáp ứng điều gì?

Hàm băm biến dữ liệu khóa thành giá trị có thể dùng để định vị. Với khóa dạng văn bản, một cách minh họa là duyệt từng ký tự, kết hợp mã ký tự vào giá trị tích lũy:

```text
h = 0
với mỗi ký tự c của khóa:
    h = (31 * h + mã_số(c)) mod 2^32
chỉ_số = h mod số_ngăn
```

Hệ số `31` giúp vị trí ký tự ảnh hưởng đến kết quả: `"ma"` và `"am"` thường tạo ra **giá trị băm** khác nhau, thay vì đơn thuần cộng mã ký tự. Tuy nhiên, chúng vẫn có thể rơi vào cùng **ngăn** sau phép lấy phần dư. Công thức trên chỉ dùng để học cơ chế; hệ thống thực tế chọn hàm băm phù hợp với kiểu khóa, chất lượng phân bố và yêu cầu an toàn.

Một hàm băm hữu dụng trong bảng băm nên có các tính chất sau:

1. **Nhất quán:** cùng khóa, khi được xử lý trong cùng điều kiện, cho cùng giá trị băm. Nếu hai khóa được xem là bằng nhau thì chúng bắt buộc phải có giá trị băm giống nhau.
2. **Phân bố tương đối đều:** các khóa thường gặp không dồn quá nhiều vào một vài ngăn; điều này hạn chế số phần tử cần kiểm tra sau khi định vị.
3. **Tính toán hiệu quả:** thời gian băm không được quá đắt so với lợi ích tra cứu; đối với chuỗi dài `L` ký tự, việc đọc chuỗi để băm thường mất `O(L)`.

**Không có yêu cầu khóa khác nhau phải có giá trị băm khác nhau.** Vì số ngăn là hữu hạn nhưng tập khóa có thể rất lớn, sẽ tồn tại trường hợp nhiều khóa cùng một ngăn (nguyên lý chuồng bồ câu). Giá trị băm cũng không phải bằng chứng hai khóa bằng nhau: `h(a) = h(b)` **không** suy ra `a = b`.

## 4. Va chạm: hai khóa cùng một vị trí

**Va chạm (collision)** xảy ra khi hai khóa khác nhau được ánh xạ vào cùng ngăn. Trong ví dụ trước, `27` và `35` va chạm tại chỉ số 3. Va chạm là hiện tượng bình thường, không phải lỗi tính toán.

Hai hướng xử lý phổ biến là:

| Cách xử lý | Ý tưởng | Khi tìm kiếm |
| --- | --- | --- |
| **Nối chuỗi (separate chaining)** | Mỗi ngăn lưu một nhóm các cặp khóa–giá trị, ví dụ một danh sách | Tính ngăn rồi so sánh khóa trong nhóm đó |
| **Địa chỉ mở (open addressing)** | Mỗi ô chứa một phần tử; nếu ô dự kiến đã có khóa khác, tìm ô khác theo quy tắc thăm dò | Lặp lại đúng quy tắc thăm dò cho đến khi tìm thấy khóa hoặc biết khóa vắng mặt |

Trong cả hai cách, bảng băm phải giữ được **khóa đầy đủ** (hoặc thông tin đủ để kiểm tra tương đương khóa), vì chỉ số ngăn và giá trị băm không đủ để nhận diện duy nhất một khóa.

Các thao tác được hiểu như sau:

- **Thêm/gán `put(k, v)`:** tính ngăn của `k`, tìm xem khóa đã tồn tại chưa; nếu có thì cập nhật `v`, nếu chưa thì lưu cặp mới theo quy tắc xử lý va chạm.
- **Tìm `get(k)`:** tính lại cùng ngăn của `k`, sau đó kiểm tra khóa để lấy đúng giá trị hoặc kết luận không có khóa.
- **Xóa `remove(k)`:** định vị và loại bỏ đúng cặp có khóa `k`; cách giữ cấu trúc hợp lệ khi xóa tùy cơ chế xử lý va chạm.

## 5. Ví dụ Python: quan sát ánh xạ và va chạm

Đoạn mã sau dùng bảng gồm 8 ngăn, hàm băm văn bản minh họa ở trên, và **nối chuỗi** để giữ các cặp cùng ngăn. Nó cố ý đơn giản, chỉ hỗ trợ khóa kiểu `str` và chưa tự tăng kích thước.

```python
class BangBamDonGian:
    def __init__(self, so_ngan=8):
        if so_ngan <= 0:
            raise ValueError("Số ngăn phải dương")
        self.ngan = [[] for _ in range(so_ngan)]

    def _bam(self, khoa: str) -> int:
        h = 0
        for ky_tu in khoa:
            h = (31 * h + ord(ky_tu)) % (2**32)
        return h

    def chi_so(self, khoa: str) -> int:
        return self._bam(khoa) % len(self.ngan)

    def gan(self, khoa: str, gia_tri):
        nhom = self.ngan[self.chi_so(khoa)]
        for i, (khoa_cu, _) in enumerate(nhom):
            if khoa_cu == khoa:
                nhom[i] = (khoa, gia_tri)  # Cập nhật khóa đã có
                return
        nhom.append((khoa, gia_tri))  # Khóa mới

    def lay(self, khoa: str):
        nhom = self.ngan[self.chi_so(khoa)]
        for khoa_cu, gia_tri in nhom:
            if khoa_cu == khoa:
                return gia_tri
        raise KeyError(khoa)


bang = BangBamDonGian(8)
bang.gan("ma", 2)
bang.gan("am", 3)
bang.gan("ma", 5)

print(bang.chi_so("ma"), bang.chi_so("am"))  # 4 4
print(bang.lay("ma"), bang.lay("am"))        # 5 3
print(bang.ngan[4])                          # [('ma', 5), ('am', 3)]
```

Với chuỗi ngắn trong ví dụ:

```text
h("ma") = 109 * 31 + 97  = 3476;  3476 mod 8 = 4
h("am") =  97 * 31 + 109 = 3116;  3116 mod 8 = 4
```

Hai khóa có **giá trị băm khác nhau** nhưng vẫn cùng **chỉ số ngăn**. Khi gán lại `"ma"`, chương trình cập nhật giá trị từ `2` thành `5`, không thêm một bản ghi `"ma"` thứ hai. Khi đọc, phép so sánh `khoa_cu == khoa` bảo đảm `"ma"` và `"am"` không bị nhầm lẫn.

## 6. Vì sao số ngăn ảnh hưởng đến hiệu năng?

Gọi `n` là số cặp khóa–giá trị đang lưu và `m` là số ngăn. **Hệ số tải (load factor)** thường được định nghĩa:

\[
\alpha = \frac{n}{m}
\]

Ví dụ, với `n = 6` và `m = 8`, ta có `α = 0,75`. Với nối chuỗi, khi `n` tăng còn `m` giữ nguyên, số phần tử trung bình trong mỗi ngăn có xu hướng tăng, khiến việc so sánh khóa lâu hơn. Khi đó, bảng băm thực tế có thể **mở rộng bảng và phân bố lại các khóa** (rehashing).

Việc đổi số ngăn có thể làm đổi chỉ số của một khóa: `27 mod 8 = 3`, nhưng `27 mod 16 = 11`. Vì vậy, không thể chỉ kéo dài mảng rồi giữ nguyên mọi phần tử ở ngăn cũ; phải tính lại vị trí theo kích thước bảng mới. Ngưỡng tải và quy tắc tăng kích thước tùy từng cách cài đặt.

Với giả định hàm băm phân bố tốt, hệ số tải được kiểm soát và chi phí băm/so sánh khóa được xem là hằng số:

| Thao tác | Trung bình kỳ vọng | Trường hợp xấu nhất |
| --- | --- | --- |
| Tìm theo khóa | `O(1)` | `O(n)` |
| Thêm/cập nhật theo khóa | `O(1)` | `O(n)` |
| Xóa theo khóa | `O(1)` | `O(n)` |

Các độ phức tạp trên mô tả chi phí **định vị và xử lý va chạm**. Với khóa chuỗi dài `L`, riêng việc tính băm từ đầu đã thường tốn `O(L)`; so sánh các chuỗi khi va chạm cũng tốn thêm thời gian. Với nối chuỗi, bộ nhớ gồm mảng `m` ngăn và `n` bản ghi là `O(m + n)` (chưa tính dữ liệu mà các giá trị trỏ tới). Trong ví dụ Python chưa có mở rộng bảng, nên hiệu năng sẽ giảm nếu thêm quá nhiều khóa vào 8 ngăn cố định.

## 7. Những bất biến và nhầm lẫn cần nhớ

Để `get(k)` tìm thấy đúng giá trị đã lưu bởi `put(k, v)`, bảng băm phải luôn giữ một số **bất biến**:

1. Cặp có khóa `k` phải nằm ở vị trí mà quy tắc băm và xử lý va chạm sẽ tìm đến được, tính theo **kích thước bảng hiện tại**.
2. Hai khóa được xem là bằng nhau phải có kết quả băm phù hợp với cùng quy tắc định vị. Cách xác định khóa bằng nhau phải nhất quán trong cả thao tác gán, tìm và xóa.
3. Mỗi khóa logic chỉ có một giá trị đang hiệu lực trong một map; gán lại cùng khóa là cập nhật, không tạo thêm khóa trùng.
4. Nếu kích thước bảng thay đổi, phải sắp xếp lại các phần tử theo quy tắc ánh xạ mới.

Các lỗi tư duy thường gặp:

- **“Khóa khác nhau phải ở ô khác nhau”:** sai, vì va chạm luôn có thể xảy ra.
- **“Hai khóa có cùng hash là cùng một khóa”:** sai, phải kiểm tra phép so sánh khóa.
- **“Thay đổi nội dung khóa sau khi thêm không ảnh hưởng gì”:** sai với các kiểu khóa có thể biến đổi; thay đổi dữ liệu tham gia tính hash có thể khiến việc tra cứu không còn tìm đến vị trí cũ. Nên dùng khóa ổn định/bất biến trong thời gian lưu.
- **“Hash table luôn `O(1)`”:** không tuyệt đối; đó là kỳ vọng dưới các giả định về phân bố, tải và chi phí xử lý khóa.
- **“Hàm băm dùng cho bảng băm đồng nghĩa với hàm băm mật mã”:** sai; hàm băm mật mã có yêu cầu an toàn khác. Hàm băm minh họa trong bài không thích hợp cho mục đích bảo mật.

## 8. Tự kiểm tra

**Câu 1.** Bảng có `m = 10`, dùng `h(k) = k` với khóa nguyên không âm. Khóa `42` và `72` có được đưa vào cùng ngăn không?

**Đáp án:** Có. `42 mod 10 = 2` và `72 mod 10 = 2`. Cần xử lý va chạm để vẫn phân biệt được hai khóa.

**Câu 2.** Nếu lưu `(k, 10)` rồi gán tiếp `(k, 20)` vào một map, điều gì nên xảy ra?

**Đáp án:** Giá trị ứng với khóa `k` được cập nhật thành `20`; map vẫn chỉ chứa một khóa `k`.

**Câu 3.** Vì sao tăng số ngăn từ 8 lên 16 có thể yêu cầu di chuyển các bản ghi dù khóa không đổi?

**Đáp án:** Vì `h(k) mod 8` có thể khác `h(k) mod 16`; cần tính lại chỉ số ngăn để thao tác tìm về sau vẫn đến đúng nơi lưu.

**Điểm cần nắm:** Bảng băm dùng hàm băm để đưa một khóa về **ngăn có thể tìm kiếm nhanh**, sau đó dùng cơ chế xử lý va chạm và so sánh khóa để xác định **đúng bản ghi**. Hiệu quả của cách làm phụ thuộc vào hàm băm, số ngăn, hệ số tải và việc duy trì các bất biến trong mọi thao tác.
