# Phân biệt mã băm của khóa với chỉ số ô trong bảng

## 1. Một khóa đi qua hai bước tính toán

Trong **bảng băm (hash table)**, chương trình thường nhận một **khóa** có ý nghĩa với bài toán, chẳng hạn mã sinh viên `"SV120"`, tên tài khoản `"minh"` hoặc mã đơn hàng `"DH42"`. Tuy nhiên, bộ nhớ lưu trữ của bảng được tổ chức thành các ô hoặc **ngăn** (bucket) có chỉ số nguyên. Muốn tìm nhanh dữ liệu gắn với khóa, ta cần chuyển từ khóa sang nơi có thể bắt đầu tra cứu.

Quá trình thường được chia thành hai bước:

1. **Tính mã băm (hash code):** áp dụng hàm băm `H` lên khóa `k` để tạo ra một giá trị số `H(k)`.
2. **Tính chỉ số trong bảng (bucket index):** chuyển mã băm về phạm vi chỉ số của mảng nền có `m` ngăn, thường dùng phép lấy phần dư `H(k) mod m`.

```text
             Bước 1: băm khóa                 Bước 2: chọn ngăn
Khóa k  ---------------------------->  Mã băm H(k)  ---------------->  Chỉ số i
         phụ thuộc hàm băm và khóa                   phụ thuộc cả m

                                                           |
                                                           v
                                             Bảng có m ngăn: 0 ... m-1
```

Với hàm băm cho ra số nguyên không âm, cách rút gọn đơn giản là:

\[
\text{hashCode} = H(k), \qquad
\text{bucketIndex} = H(k) \bmod m \quad (m > 0).
\]

**Mã băm không phải là chỉ số ô.** Mã băm có thể là số rất lớn, trong khi chỉ số hợp lệ của bảng chỉ nằm trong khoảng từ `0` đến `m - 1`. Một số cách cài đặt thực tế còn trộn các bit của mã băm trước khi tính chỉ số hoặc dùng phép `& (m - 1)` khi `m` là lũy thừa của 2; tư tưởng hai bước vẫn giữ nguyên.

## 2. So sánh trực tiếp hai khái niệm

| Đặc điểm | Mã băm của khóa | Chỉ số ô/ngăn trong bảng |
| --- | --- | --- |
| Câu hỏi được trả lời | “Hàm băm biến khóa này thành số nào?” | “Với dung lượng hiện tại, bắt đầu tìm khóa ở đâu?” |
| Đầu vào chính | Khóa và quy tắc của hàm băm | Mã băm và số ngăn `m` (có thể thêm bước trộn bit) |
| Miền giá trị | Theo thiết kế của hàm băm, ví dụ số nguyên 32 bit | `0, 1, ..., m - 1` |
| Khi đổi số ngăn | Thường giữ nguyên nếu vẫn dùng cùng hàm băm và cùng tham số | **Có thể thay đổi** vì `m` thay đổi |
| Có nhận diện duy nhất khóa không? | Không: hai khóa khác nhau có thể cùng mã băm | Không: nhiều mã băm có thể cùng chỉ số |
| Vai trò | Đại diện số cho khóa để phục vụ định vị | Giới hạn vị trí về bảng lưu trữ cụ thể |

Ví dụ: cho `H(26) = 26`. Với bảng có 8 ngăn, `26 mod 8 = 2`; với bảng có 16 ngăn, `26 mod 16 = 10`. **Mã băm vẫn là 26**, nhưng **chỉ số chuyển từ 2 sang 10**. Điều này chứng minh chỉ số không phải một thuộc tính cố định của khóa.

## 3. Ví dụ số cụ thể: nhiều mã băm cùng một chỉ số

Giả sử bảng có `m = 8` ngăn, đánh số từ 0 đến 7. Ta đã tính được mã băm của một số khóa như sau:

| Khóa | Mã băm `H(k)` | `H(k) mod 8` | Ngăn bắt đầu tra cứu |
| --- | ---: | ---: | ---: |
| `"A"` | 18 | 2 | 2 |
| `"B"` | 26 | 2 | 2 |
| `"C"` | 19 | 3 | 3 |
| `"D"` | 34 | 2 | 2 |

Các mã băm 18, 26 và 34 **khác nhau** nhưng đều có số dư 2 khi chia cho 8:

```text
H("A") = 18 ----┐
H("B") = 26 ----+---->  mod 8  ---->  ngăn 2
H("D") = 34 ----┘
H("C") = 19 ----------------------->  ngăn 3
```

Ở đây các giá trị 18, 26, 19 và 34 được **giả định là đầu ra của hàm băm** để tập trung vào bước chọn ngăn; chúng không phải mã băm mặc định của chuỗi trong một ngôn ngữ lập trình cụ thể.

Hiện tượng nhiều khóa hướng đến cùng ngăn gọi là **va chạm tại ngăn**. Bảng băm phải có cách phân biệt các khóa đó, chẳng hạn:

- **Nối chuỗi (separate chaining):** ngăn 2 lưu nhiều cặp `(khóa, giá trị)`, sau đó tìm bằng phép so sánh khóa.
- **Địa chỉ mở (open addressing):** chỉ số 2 là vị trí thử đầu tiên; nếu ô đó chứa khóa khác, chương trình tiếp tục thử các vị trí theo quy tắc thăm dò. **Ô lưu thực tế có thể khác chỉ số ban đầu.**

Vì vậy, trong bảng dùng địa chỉ mở, cần phân biệt thêm **chỉ số thăm dò đầu tiên** và **ô thực sự chứa bản ghi** sau xử lý va chạm.

### Hai tình huống dễ bị nhầm

**Tình huống A — mã băm khác nhau, chỉ số trùng nhau:**

```text
H(k1) = 18, H(k2) = 26, m = 8
18 != 26, nhưng 18 mod 8 = 26 mod 8 = 2
```

**Tình huống B — hai khóa khác nhau có cùng mã băm:**

```text
k1 != k2, nhưng H(k1) = H(k2) = 18
Khi m = 8, cả hai có chỉ số 18 mod 8 = 2
```

Tình huống B là **va chạm mã băm (hash collision)**; nó tất yếu kéo theo cùng chỉ số nếu cùng một quy tắc rút gọn. Ngược lại, **cùng chỉ số không chứng minh hai mã băm bằng nhau** như tình huống A. Trong thực tế, từ “va chạm” thường được dùng chung cho trường hợp các khóa cạnh tranh cùng ngăn, nên cần nhìn rõ bước tính toán đang nói tới.

## 4. Tính mã băm chuỗi rồi đổi sang chỉ số ô

Để quan sát cả hai bước với dữ liệu đầu vào thực sự, hãy dùng một hàm băm chuỗi đơn giản. Bắt đầu từ 0, với mỗi ký tự, nhân giá trị hiện tại với 31 rồi cộng mã Unicode của ký tự. Sau mỗi bước, giữ lại 32 bit thấp của kết quả:

```text
h = 0
cho mỗi ký tự c trong khóa:
    h = (31 × h + mã_Unicode(c)) mod 2^32
trả về h
```

Ví dụ đối với hai khóa `"ab"` và `"ba"`:

```text
H("ab") = 31 × 97 + 98 = 3105
H("ba") = 31 × 98 + 97 = 3135
```

Hai mã băm khác nhau. Nếu bảng có 5 ngăn, `3105 mod 5 = 0` và `3135 mod 5 = 0`; chúng cùng đến ngăn 0. Nhưng nếu bảng có 8 ngăn, `3105 mod 8 = 1` và `3135 mod 8 = 7`; chúng đi vào hai ngăn khác nhau.

### Chạy thử bằng Python

```python
def ma_bam(chuoi: str) -> int:
    h = 0
    for ky_tu in chuoi:
        h = (31 * h + ord(ky_tu)) % (2**32)
    return h


def chi_so_ngan(chuoi: str, so_ngan: int) -> int:
    if so_ngan <= 0:
        raise ValueError("Số ngăn phải lớn hơn 0")
    return ma_bam(chuoi) % so_ngan


for khoa in ("ab", "ba"):
    h = ma_bam(khoa)
    print(khoa, "hash =", h,
          "index(m=5) =", chi_so_ngan(khoa, 5),
          "index(m=8) =", chi_so_ngan(khoa, 8))
```

Kết quả:

```text
ab hash = 3105 index(m=5) = 0 index(m=8) = 1
ba hash = 3135 index(m=5) = 0 index(m=8) = 7
```

Điểm đáng chú ý là khi chỉ đổi `so_ngan`, hàm `ma_bam` vẫn cho cùng kết quả, còn hàm `chi_so_ngan` có thể trả về chỉ số khác. Việc tách hai hàm cũng giúp kiểm tra từng bước dễ dàng.

Hàm trên được viết cho mục đích học tập. Không nên dùng nó làm hàm băm mật mã hoặc giả định nó luôn phân bố tốt với mọi tập dữ liệu. Ngoài ra, `hash(chuoi)` dựng sẵn của Python có thể dùng giá trị khởi tạo ngẫu nhiên giữa các lần chạy chương trình; vì vậy ví dụ dùng hàm băm riêng để kết quả minh họa ổn định.

## 5. Khi bảng mở rộng, điều gì thay đổi?

Nhiều bảng băm tăng số ngăn khi lượng dữ liệu lớn lên. Gọi `m_{cũ}` là số ngăn cũ và `m_{mới}` là số ngăn mới. Với cùng khóa `k` và cùng hàm băm:

\[
i_{\text{cũ}} = H(k) \bmod m_{\text{cũ}}, \qquad
i_{\text{mới}} = H(k) \bmod m_{\text{mới}}.
\]

Chẳng hạn, với mã băm 26:

```text
Trước mở rộng: m =  8  -->  26 mod  8 =  2
Sau mở rộng:   m = 16  -->  26 mod 16 = 10
```

Để thao tác tìm kiếm vẫn định vị đúng, bảng phải **phân bố lại các bản ghi** theo số ngăn mới (rehashing/redistribution). “Rehashing” trong tài liệu về bảng băm đôi khi có nghĩa tính lại vị trí từ mã băm đã lưu, đôi khi còn bao gồm tính lại mã băm; điều bắt buộc là vị trí phù hợp với cấu trúc và quy tắc hiện tại. Không nên hiểu từ này theo nghĩa lúc nào cũng phải thay đổi bản thân mã băm.

Mặt khác, một bảng băm có thể trộn bit hoặc dùng hạt giống (seed) khi tính mã băm. Trong các trường hợp đó, mã băm có thể khác giữa các tiến trình hoặc các phiên khởi tạo. Câu “mã băm không đổi khi mở rộng” chỉ đúng khi **hàm băm, seed và quy tắc tính mã băm giữ nguyên** trong quá trình mở rộng bảng.

## 6. Lưu ý khi biến mã băm thành chỉ số

**Dung lượng phải hợp lệ.** Phép `H(k) mod m` cần `m > 0`. Bảng không thể dùng `m = 0` làm số ngăn cho phép lấy phần dư.

**Mã băm có thể âm.** Nhiều ngôn ngữ dùng kiểu số nguyên có dấu cho mã băm. Không thể lấy một kết quả âm làm chỉ số mảng trực tiếp. Cần dùng quy tắc chuyển chỉ số bảo đảm `0 <= i < m`. Chẳng hạn, Python cho `-7 % 8 == 1`, còn toán tử `%` trong Java cho `-7 % 8 == -7`; với Java có thể dùng `Math.floorMod(hash, m)` nếu muốn chỉ số không âm.

**Một chỉ số không khôi phục được mã băm hoặc khóa.** Nếu chỉ biết ngăn 2 của bảng có 8 ngăn, ta không thể suy ra mã băm là 18 hay 26 hay 34; càng không thể suy ra chính xác khóa. Vì vậy bảng phải giữ thông tin khóa để so sánh khi tìm kiếm và cập nhật.

**Hai khóa bằng nhau phải được đối xử nhất quán.** Nếu `k1 == k2` theo quy tắc so sánh khóa của cấu trúc thì hàm băm phải cho giá trị phù hợp để chúng được định vị như cùng một khóa. Nhưng `H(k1) == H(k2)` không đủ để kết luận `k1 == k2`.

**Giữ khóa ổn định.** Khi các trường dữ liệu tham gia tính mã băm bị sửa trong lúc khóa đã nằm trong bảng, thao tác tìm theo khóa có thể tính ra chỉ số khác. Các kiểu khóa bất biến giúp bảo vệ bất biến tra cứu.

## 7. Bài tập tự kiểm tra

**Bài 1.** Cho `H("x") = 41` và `m = 10`. Mã băm và chỉ số ô là bao nhiêu?

**Đáp án:** Mã băm là **41**; chỉ số ô là `41 mod 10 = 1`. Không được gọi số 1 là mã băm của khóa.

**Bài 2.** Hai khóa khác nhau có mã băm 13 và 29. Bảng có 8 ngăn. Chúng có cùng mã băm và/hoặc cùng chỉ số không?

**Đáp án:** Mã băm **khác nhau**. Chỉ số đều là 5 vì `13 mod 8 = 5` và `29 mod 8 = 5`; cần xử lý va chạm tại ngăn.

**Bài 3.** Một khóa có mã băm 27. Bảng tăng từ 8 lên 16 ngăn mà không thay đổi hàm băm. Khóa sẽ được định vị ở đâu trước và sau khi mở rộng?

**Đáp án:** Trước khi mở rộng: `27 mod 8 = 3`. Sau khi mở rộng: `27 mod 16 = 11`. Mã băm vẫn là 27; chỉ số đổi từ 3 sang 11.

**Bài 4.** Vì sao chỉ lưu mã băm của một khóa, không lưu khóa, có thể khiến bảng băm trả về sai giá trị?

**Đáp án:** Vì hai khóa khác nhau có thể tạo ra cùng mã băm. Nếu chỉ so mã băm, bảng có thể nhầm hai khóa thành một và trả về bản ghi sai. Cần so sánh khóa theo đúng định nghĩa bằng nhau của cấu trúc.

**Ghi nhớ:** `khóa → mã băm → chỉ số ngăn → xác định đúng khóa trong ngăn`. **Mã băm** là kết quả biến đổi khóa; **chỉ số ngăn** là nơi bắt đầu tìm trong bảng có dung lượng cụ thể. Tách bạch hai giá trị giúp hiểu va chạm, mở rộng bảng và tính đúng đắn của thao tác tra cứu.
