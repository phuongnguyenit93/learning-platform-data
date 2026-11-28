# Hàm băm tốt, phân bố đều và giả định dùng trong phân tích

## 1. “Hàm băm tốt” có nghĩa gì đối với bảng băm?

Bảng băm (hash table) hỗ trợ tra cứu theo khóa, chẳng hạn tìm hồ sơ từ mã sinh viên hoặc đếm số lần xuất hiện của một từ. Hàm băm `h(k)` nhận khóa `k` và tạo ra **mã băm**; từ đó bảng tính **chỉ số ngăn** để bắt đầu tìm cặp khóa–giá trị. Với cách ánh xạ đơn giản, `i = h(k) mod m`, trong đó `m > 0` là số ngăn.

Trong một bảng có `m` ngăn, nhiều khóa có thể đi vào cùng ngăn. Đây là **va chạm (collision)** và bảng phải xử lý được nó. Mục tiêu của hàm băm tốt là làm cho số lượng va chạm **thấp và khó bị tập trung** đối với những khóa mà hệ thống thực sự gặp, nhờ đó việc thêm, tìm và xóa thường nhanh.

Một hàm băm không thể bảo đảm các khóa khác nhau luôn có chỉ số khác nhau nếu số khóa có thể xuất hiện lớn hơn số ngăn. Vì vậy, “tốt” không có nghĩa “không bao giờ va chạm”; nó nói về **chất lượng phân bố**, chi phí tính toán, tính nhất quán và độ phù hợp với tập khóa.

## 2. Phân bố đều là phân bố của *khóa thực tế*

Giả sử ta lưu `n` khóa vào `m` ngăn. Gọi `X_i` là số khóa đi vào ngăn `i`. Phân bố tương đối đều nghĩa là các `X_i` không chênh lệch quá lớn một cách có hệ thống; có thể có ngăn rỗng và ngăn chứa nhiều khóa.

Để nhìn rõ sự khác biệt, xét sáu khóa nguyên không âm:

```text
10, 18, 26, 34, 42, 50
```

Với bảng 8 ngăn, hai cách tính chỉ số dưới đây cho kết quả rất khác:

| Khóa `k` | `k mod 8` | `(k XOR (k >> 3)) mod 8` |
| ---: | ---: | ---: |
| 10 | 2 | 3 |
| 18 | 2 | 0 |
| 26 | 2 | 1 |
| 34 | 2 | 6 |
| 42 | 2 | 7 |
| 50 | 2 | 4 |

Ở cột đầu, mọi khóa đều va chạm tại ngăn 2. Ở cột sau, phép XOR với giá trị dịch phải 3 bit đưa thêm thông tin từ các bit cao vào các bit thấp; **riêng sáu khóa này** được trải ra sáu ngăn khác nhau:

```text
Ngăn             0  1  2  3  4  5  6  7
Chỉ dùng k mod 8 0  0  6  0  0  0  0  0
Có trộn bit       1  1  0  1  1  0  1  1
```

Ví dụ chứng minh rằng **cách chọn hàm băm và cách rút gọn về chỉ số** có thể gây khác biệt lớn. Phép trộn XOR ở đây chỉ dùng để minh họa: nó không được bảo đảm phân bố đều với mọi tập khóa và không phải thuật toán băm khuyến nghị cho hệ thống thực tế.

Điểm dễ nhầm là đánh giá hàm băm chỉ bằng việc nó tạo số lớn, có nhiều chữ số, hay “trông ngẫu nhiên”. Mã băm có vẻ đa dạng nhưng **những bit dùng để chọn ngăn** vẫn có thể lặp lại. Ví dụ bảng có 8 ngăn và dùng `hash & 7` sẽ phụ thuộc vào ba bit thấp; nếu ba bit này thường giống nhau, nhiều khóa sẽ cùng ngăn.

## 3. Những tính chất cần có của một hàm băm hữu dụng

| Tính chất | Vì sao cần? | Dấu hiệu vấn đề |
| --- | --- | --- |
| **Nhất quán** | Cùng khóa trong cùng điều kiện phải cho cùng mã băm; hai khóa bằng nhau phải có mã băm bằng nhau | Lưu được bằng `a` nhưng không tìm thấy bằng `b` dù `a == b` |
| **Phân bố phù hợp với dữ liệu** | Tránh dồn khóa vào vài ngăn, giảm số phần tử hoặc số ô phải thăm dò | Một số ngăn rất dài hoặc xuất hiện cụm va chạm lớn |
| **Nhạy với các phần của khóa** | Nhiều trường hợp khóa chỉ khác ở một vài ký tự hoặc bit; các phần đó vẫn cần góp phần vào việc định vị | Các mã chung tiền tố/hậu tố luôn tập trung |
| **Tính toán nhanh** | Chi phí băm không nên lấn át thời gian tra cứu | Hàm băm phải xử lý lại dữ liệu quá đắt |
| **Phù hợp mức độ tin cậy của đầu vào** | Khóa do bên ngoài điều khiển có thể được chọn có chủ đích để gây va chạm | Rất nhiều khóa không trùng nhau nhưng cùng ngăn theo một quy luật |

Hiệu ứng *avalanche* (thay đổi nhỏ ở đầu vào làm nhiều bit đầu ra thay đổi) thường là một dấu hiệu hữu ích của khả năng trộn bit, nhưng **không tự chứng minh** rằng mã băm phân bố đều trên tập khóa thực tế. Đặc biệt, hàm băm tốt cho dữ liệu thông thường chưa chắc chống được người tấn công chủ động chọn khóa.

Với chuỗi dài `L` ký tự, phải đọc các ký tự để tính băm từ đầu nên chi phí thường là `O(L)`. Khi phân tích thao tác `O(1)` của bảng băm, người ta thường **giả định việc băm và so sánh khóa có chi phí hằng số**, hoặc xét riêng chi phí xử lý khóa.

## 4. “Phân bố đều” trong phân tích lý thuyết là một giả định xác suất

Một hàm băm **cố định** cho một tập khóa cố định tạo ra kết quả cố định, không tự có yếu tố ngẫu nhiên. Để tính **thời gian kỳ vọng**, ta thường dùng một mô hình xác suất, chẳng hạn chọn ngẫu nhiên hàm băm từ một họ hàm, hoặc giả định phân bố của khóa đầu vào. Phải nói rõ nguồn ngẫu nhiên này; không thể từ việc thấy bảng có 8 ngăn mà kết luận mỗi khóa bất kỳ chắc chắn phân bố đều.

### Giả định băm đều đơn giản (simple uniform hashing)

Đối với phương pháp **nối chuỗi (separate chaining)**, mô hình lý tưởng thường giả định mỗi khóa được ánh xạ độc lập và đồng đều vào một trong `m` ngăn, tức xác suất rơi vào từng ngăn là `1/m`. Với `n` khóa:

\[
\alpha = \frac{n}{m}
\]

là **hệ số tải (load factor)**. Nếu `X_i` là số khóa trong ngăn `i` thì:

\[
\mathbb{E}[X_i] = \frac{n}{m} = \alpha.
\]

Với một khóa cố định `k`, dưới giả định các vị trí được chọn độc lập và đồng đều, số **khóa khác** có cùng ngăn với `k` có kỳ vọng là `(n - 1)/m`. Số **cặp khóa khác nhau** cùng ngăn, tính trên cả bảng, có kỳ vọng:

\[
\mathbb{E}[C] = \frac{\binom{n}{2}}{m}
= \frac{n(n-1)}{2m}.
\]

Ví dụ `n = 6`, `m = 8`: hệ số tải là `0,75`, số cặp va chạm kỳ vọng là `15/8 = 1,875`. Con số 1,875 là **trung bình qua các lần gán ngẫu nhiên**, không có nghĩa một bảng cụ thể chứa 1,875 cặp va chạm; số cặp va chạm quan sát được luôn là số nguyên.

Các kết quả kỳ vọng giúp ước lượng hiệu năng và so sánh thiết kế, nhưng **không là cam kết cho từng trường hợp**. Một hàm băm phân bố tốt vẫn có thể xuất hiện ngăn đông do ngẫu nhiên.

### Hàm băm phổ dụng (universal hashing)

Một cách để thay giả định “mọi khóa tự phân bố tốt” bằng một cơ chế rõ ràng là **chọn ngẫu nhiên hàm băm từ một họ hàm băm phổ dụng**. Với hai khóa phân biệt `x != y`, họ phổ dụng bảo đảm xác suất chúng rơi vào cùng ngăn (theo lựa chọn hàm ngẫu nhiên) không quá `1/m`.

Ý nghĩa: với **bất kỳ tập khóa cố định nào được chọn trước khi chọn hàm**, có thể kiểm soát số va chạm kỳ vọng theo xác suất của việc chọn hàm băm. Kết quả đó không bảo đảm một hàm đã được rút ra sẽ tốt cho mọi tập khóa, và cũng không ngăn được đối thủ tìm va chạm nếu họ biết đủ về hàm đã chọn.

Trong thư viện thực tế còn có các chiến lược trộn bit, dùng seed ngẫu nhiên hoặc hàm băm có khóa bí mật; mỗi chiến lược đáp ứng những mục tiêu và giả định khác nhau. Không cần dùng hàm băm mật mã cho mọi bảng băm, nhưng với đầu vào không đáng tin cậy cần cân nhắc khả năng gây **hash-flooding**.

## 5. Giả định phân bố đều dẫn đến thời gian kỳ vọng như thế nào?

### Nối chuỗi (separate chaining)

Mỗi ngăn lưu một nhóm các cặp khóa–giá trị. Khi `get(k)`, bảng tính chỉ số ngăn rồi so sánh khóa với các phần tử trong nhóm đó. Dưới mô hình băm đều đơn giản và nếu phép băm, so sánh khóa có chi phí hằng số:

| Thao tác | Thời gian kỳ vọng | Trường hợp xấu nhất |
| --- | --- | --- |
| Tìm thấy khóa | `O(1 + α)` | `O(n)` |
| Tìm không thấy khóa | `O(1 + α)` | `O(n)` |
| Thêm hoặc cập nhật, có kiểm tra khóa đã tồn tại | `O(1 + α)` | `O(n)` |
| Xóa khóa | `O(1 + α)` | `O(n)` |

Trong trường hợp xấu, toàn bộ `n` khóa có thể nằm trong cùng một ngăn. Nếu giữ `α = n/m` không vượt quá một hằng số nhờ mở rộng bảng hợp lý, **thời gian kỳ vọng của các thao tác trên là `O(1)`**, nhưng thời gian xấu nhất vẫn có thể là `O(n)`.

Trong mô hình nối chuỗi với cấu trúc nhóm là danh sách, bộ nhớ gồm `m` ngăn và `n` bản ghi có bậc `O(m+n)` (chưa tính vùng dữ liệu mà giá trị tham chiếu đến).

### Địa chỉ mở (open addressing)

Địa chỉ mở lưu bản ghi trực tiếp trong các ô của bảng. Nếu ô thử đầu tiên đã có khóa khác, bảng phải **thăm dò các ô kế tiếp** theo quy tắc nhất định. Vì mỗi khóa phải chiếm ô riêng, cần `n < m` để còn chỗ trống, tức `α < 1`.

Một giả định lý tưởng thường dùng trong phân tích địa chỉ mở là **uniform hashing**: mỗi khóa có một thứ tự thăm dò ngẫu nhiên, phân bố đều trên các hoán vị của `m` ô, độc lập với các khóa khác. Đây là giả định mạnh hơn việc chỉ chọn ngăn đầu tiên đồng đều; các cách thăm dò thực tế như **linear probing** không tự đáp ứng giả định lý tưởng này.

Khi không xét thao tác xóa và dùng mô hình thăm dò đều, các cận trên quen thuộc cho **số ô cần kiểm tra kỳ vọng** là:

\[
\begin{aligned}
\mathbb{E}[\text{thăm dò khi tìm thất bại}] &\leq \frac{1}{1-\alpha},\\
\mathbb{E}[\text{thăm dò khi tìm thành công}] &\leq
\frac{1}{\alpha}\ln\frac{1}{1-\alpha} \quad (0 < \alpha < 1).
\end{aligned}
\]

| Hệ số tải `α` | Cận trên khi tìm không thấy | Cận trên khi tìm thấy |
| ---: | ---: | ---: |
| 0,50 | 2,00 lần thăm dò | xấp xỉ 1,39 |
| 0,75 | 4,00 lần thăm dò | xấp xỉ 1,85 |
| 0,90 | 10,00 lần thăm dò | xấp xỉ 2,56 |

Các số này **không phải số đo thực nghiệm** hoặc bảo đảm của mọi cách cài đặt. Chúng áp dụng dưới giả định thăm dò đều nói trên, khi xây dựng bảng theo cùng mô hình và không có xóa làm thay đổi cách tra cứu. Khi `α` tiến sát 1, tìm không thành công hoặc thêm phần tử mới có thể rất đắt, vì ít ô trống.

## 6. Hệ số tải nhỏ chưa đủ nếu hàm băm phân bố kém

Với sáu khóa và tám ngăn ở ví dụ đầu bài, **cả hai cách băm đều có**:

\[
\alpha = \frac{6}{8} = 0{,}75.
\]

Nhưng ở cách `k mod 8`, nối chuỗi tạo một ngăn có 6 khóa; ở cách trộn bit, mỗi ngăn được sử dụng chứa đúng 1 khóa. Vì vậy:

1. **Hệ số tải** mô tả số phần tử trung bình theo số ngăn, không nói trực tiếp về sự lệch của các ngăn.
2. **Hàm băm** quyết định khóa nào được xếp chung với nhau; nếu phân bố lệch, một `α` nhỏ vẫn có thể đi kèm ngăn rất đông.
3. **Cơ chế va chạm** quyết định chi phí khi ngăn đông: danh sách dài khi nối chuỗi hoặc chuỗi thăm dò dài khi địa chỉ mở.
4. **Mở rộng bảng** giúp giảm hệ số tải, nhưng không tự chữa mọi điểm yếu. Nếu khóa luôn là bội của một số và hàm chỉ dùng vài bit thấp, tăng số ngăn theo lũy thừa hai vẫn có thể giữ lại các cụm va chạm.

Một bảng băm mở rộng có thể phải phân bố lại `n` bản ghi theo `m` ngăn mới, tốn `O(n+m)` cho lần mở rộng đó. Nếu dung lượng được tăng theo cấp số nhân, các lần mở rộng có thể được phân bổ chi phí để đạt **chi phí thêm kỳ vọng, phân bổ (amortized expected)** gần `O(1)` khi các giả định khác vẫn thỏa mãn.

## 7. Thực hành: đếm số khóa tại từng ngăn

Đoạn mã Python sau chỉ minh họa số lượng khóa theo ngăn, không cài đặt một bảng băm đầy đủ. Hai hàm đều nhận khóa nguyên **không âm** và dung lượng là lũy thừa hai trong ví dụ:

```python
keys = [10, 18, 26, 34, 42, 50]
bucket_count = 8


def index_simple(k: int, m: int) -> int:
    return k % m


def index_mixed(k: int, m: int) -> int:
    return (k ^ (k >> 3)) % m


def bucket_histogram(items, m, index_fn):
    counts = [0] * m
    for key in items:
        counts[index_fn(key, m)] += 1
    return counts


print(bucket_histogram(keys, bucket_count, index_simple))
print(bucket_histogram(keys, bucket_count, index_mixed))
```

Kết quả:

```text
[0, 0, 6, 0, 0, 0, 0, 0]
[1, 1, 0, 1, 1, 0, 1, 1]
```

Khi đánh giá chất lượng phân bố với dữ liệu thực tế, có thể thống kê **số lượng phần tử trong mỗi ngăn**, **chiều dài nhóm lớn nhất**, **số va chạm**, và **thời gian hoặc số lần so sánh/thăm dò** khi thêm, tìm, xóa. Nên dùng nhiều loại tập khóa: khóa liên tiếp, khóa cùng tiền tố, khóa có cấu trúc đặc biệt, khóa gần ngẫu nhiên và các mẫu có thể xảy ra trong ứng dụng. Không kết luận một hàm băm “tốt nói chung” chỉ từ một ví dụ nhỏ.

## 8. Tự kiểm tra

**Câu 1.** Một bảng có `n=100` khóa và `m=200` ngăn. Nếu giả định băm đều đơn giản, hệ số tải và số khóa kỳ vọng trong mỗi ngăn là bao nhiêu?

**Đáp án:** `α = n/m = 0,5`, và `E[X_i] = 0,5` khóa/ngăn. Đây là giá trị kỳ vọng; từng ngăn thực tế chứa số nguyên khóa, có thể bằng 0, 1 hoặc lớn hơn.

**Câu 2.** Vì sao `h(k) = k mod 8` kém hiệu quả với tập `{10,18,26,34,42,50}`?

**Đáp án:** Mọi khóa cùng có số dư 2 khi chia cho 8, nên cả sáu dồn vào ngăn 2. Hàm không trộn được khác biệt ở các bit cao của các khóa đó vào phần chỉ số cần dùng.

**Câu 3.** Nếu bảng có 75 phần tử và 100 ngăn, có thể chắc chắn thao tác tra cứu mất `O(1)` chỉ từ `α = 0,75` không?

**Đáp án:** Không. Chỉ hệ số tải không bảo đảm phân bố đều. Kết luận thời gian **kỳ vọng** `O(1)` cần thêm giả định về phân bố băm, xử lý va chạm và chi phí xử lý khóa; trường hợp xấu vẫn có thể chậm.

**Câu 4.** Đối với địa chỉ mở, chỉ số ô đầu tiên được chọn đồng đều có đủ để áp dụng trực tiếp cận trên của mô hình thăm dò đều không?

**Đáp án:** Không. Mô hình thăm dò đều giả định cả **thứ tự thử các ô** có phân bố thích hợp, không chỉ ô đầu tiên. Linear probing có thể xuất hiện các cụm khóa ngay cả khi nhiều chỉ số đầu tiên có vẻ phân bố khá đều.

**Câu 5.** Một thuật toán băm phân bố đều trên khóa do hệ thống tự tạo. Có thể mặc định nó an toàn nếu người ngoài được gửi hàng triệu khóa tự chọn không?

**Đáp án:** Không. Tập khóa có thể bị chọn có chủ đích để gây va chạm. Cần xem xét mối đe dọa thực tế, khả năng làm ngập ngăn, cơ chế chọn seed/hàm và các biện pháp giới hạn tài nguyên.

**Ghi nhớ:** Phân tích bảng băm dựa trên hai yếu tố riêng biệt: **cơ chế cài đặt** (ngăn, va chạm, mở rộng) và **giả định về cách khóa phân bố**. Dưới giả định phù hợp và với hệ số tải được kiểm soát, tra cứu có thời gian kỳ vọng tốt; nhưng một hàm băm phân bố lệch có thể phá vỡ hiệu năng dù bảng vẫn đúng về mặt chức năng.
