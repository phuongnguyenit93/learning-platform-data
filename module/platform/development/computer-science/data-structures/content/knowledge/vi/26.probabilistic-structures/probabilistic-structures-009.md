# HyperLogLog cho ước lượng số phần tử phân biệt

## 1. Bài toán: bao nhiêu khóa *khác nhau* đã xuất hiện?

Một hệ thống xử lý luồng sự kiện liên tục: một triệu lượt xem trang có thể đến từ 70.000 người dùng, còn 500.000 truy vấn có thể chỉ chứa 12.000 từ khóa khác nhau. Số lượt và số khóa phân biệt là hai đại lượng khác nhau.

Ví dụ, luồng `[A, B, A, C, B, A]` có **6 lượt xuất hiện** nhưng chỉ **3 phần tử phân biệt**: `{A, B, C}`. Kích thước tập các khóa đã gặp được gọi là **cardinality**, ký hiệu `D = |S|`. Nếu dùng `set` hoặc bảng băm, ta có thể đếm chính xác `D` bằng cách lưu toàn bộ khóa. Tuy nhiên, dung lượng bộ nhớ sẽ tăng theo số khóa khác nhau, có thể lên hàng chục triệu.

**HyperLogLog (HLL)** là một **cấu trúc dữ liệu xác suất** dùng số lượng rất nhỏ các bộ đếm để ước lượng cardinality mà không giữ lại các khóa. Nó phù hợp với các yêu cầu như “ước lượng số người dùng duy nhất trong ngày”, “số địa chỉ IP phân biệt” hoặc “số mã sản phẩm từng được xem”.

Trong hệ thống cấu trúc dữ liệu, HLL thể hiện một lựa chọn đánh đổi: thay vì tập hợp chính xác với bộ nhớ tăng theo `D`, ta giữ một mảng nhỏ có kích thước định trước, chấp nhận **sai số thống kê có thể đo được** để tiết kiệm RAM.

Sau bài này, bạn sẽ hiểu nguyên lý các bit 0 đầu của giá trị băm, cách cập nhật các thanh ghi, công thức ước lượng và sai số tương đối, cách gộp HLL giữa các máy cũng như những thao tác HLL không hỗ trợ.

## 2. Tại sao các bit 0 đứng đầu giúp đo số phần tử?

Giả sử mỗi khóa được băm thành một chuỗi bit phân bố gần đều. Trong một chuỗi bit ngẫu nhiên, xác suất có ít nhất `k` bit 0 liên tiếp ở đầu xấp xỉ `2^(−k)`:

| Tiền tố của chuỗi bit | Xác suất |
|---|---:|
| Bắt đầu bằng `0` | `1/2` |
| Bắt đầu bằng `00` | `1/4` |
| Bắt đầu bằng `000` | `1/8` |
| Bắt đầu bằng `0000` | `1/16` |

Trong ít mẫu ngẫu nhiên, khả năng thấy một chuỗi có rất nhiều bit 0 đầu khá thấp. Khi quan sát nhiều giá trị băm **khác nhau**, cơ hội thấy một chuỗi hiếm như vậy tăng lên. Nếu xuất hiện một chuỗi có 10 bit 0 đầu, điều đó gợi ý luồng có quy mô khoảng `2^10` mẫu, nhưng **một giá trị cực đại đơn lẻ rất nhiễu**.

HLL xử lý nhiễu bằng cách chia các giá trị băm vào nhiều nhóm, ghi lại độ dài tiền tố 0 lớn nhất của từng nhóm, rồi tổng hợp các nhóm. Nó **không đếm số lượt sự kiện**: nếu cùng một khóa được gửi thêm 1.000 lần, giá trị băm của khóa vẫn không đổi và thông tin trong sketch không tăng thêm.

## 3. Cấu trúc: mảng thanh ghi thay vì tập khóa

Chọn số nguyên `p` biểu thị số bit dùng để chọn nhóm, từ đó có:

```text
m = 2^p                 // số thanh ghi (register)
L = số bit của hash     // ví dụ L = 64
q = L - p               // số bit còn lại để tính độ dài tiền tố 0
```

Một HLL cơ bản chứa mảng `M[0..m−1]` gồm `m` thanh ghi nguyên nhỏ, ban đầu đều bằng `0`.

Đối với khóa `x`:

1. Tính giá trị băm `h(x)` gồm `L` bit.
2. Lấy `p` bit đầu để xác định chỉ số thanh ghi `j`.
3. Trên `q` bit còn lại, tính `ρ`: **vị trí bit 1 đầu tiên**, đếm từ 1. Nếu toàn bộ `q` bit đều bằng 0 thì quy ước `ρ = q + 1`.
4. Cập nhật thanh ghi theo quy tắc `M[j] = max(M[j], ρ)`.

```text
        Giá trị băm L = 64 bit
        ┌─────────────┬──────────────────────────────────┐
 h(x):  │  p bit đầu  │           q = 64 - p bit         │
        └──────┬──────┴───────────────┬──────────────────┘
               │                      │
          j = chỉ số                 ρ = vị trí bit 1 đầu tiên
               │                      │
               └──────────┬───────────┘
                          ▼
                  M[j] = max(M[j], ρ)
```

Ví dụ có `p = 4` thì `m = 16` thanh ghi. Nếu giá trị băm bắt đầu bằng `1010`, ta chọn thanh ghi có chỉ số `10`. Phần còn lại bắt đầu `000100...` thì `ρ = 4`, vì bit 1 đầu tiên ở vị trí thứ tư. Thanh ghi `M[10]` được cập nhật thành `max(M[10], 4)`.

**Bất biến quan trọng:** `M[j]` luôn là giá trị `ρ` lớn nhất từng quan sát ở nhóm `j`. Vì dùng phép `max`, thêm lại cùng khóa sẽ không thay đổi trạng thái. Các thanh ghi chỉ có thể giữ nguyên hoặc tăng, miễn là không đặt lại sketch.

### Ví dụ 8 bit để tính tay

Để dễ nhìn, giả sử băm chỉ có `L = 8` bit và dùng `p = 2` bit đầu; khi đó `m = 4` và mỗi phần đuôi có `q = 6` bit:

| Sự kiện | Hash dạng `chỉ_số \| phần_đuôi` | Thanh ghi `j` | `ρ` | Trạng thái sau cập nhật |
|---|---|---:|---:|---|
| Thêm `A` | `00 \| 001000` | 0 | 3 | `[3, 0, 0, 0]` |
| Thêm `B` | `01 \| 010000` | 1 | 2 | `[3, 2, 0, 0]` |
| Thêm lại `A` | `00 \| 001000` | 0 | 3 | `[3, 2, 0, 0]` |
| Thêm `C` | `00 \| 000100` | 0 | 4 | `[4, 2, 0, 0]` |
| Thêm `D` | `10 \| 100000` | 2 | 1 | `[4, 2, 1, 0]` |

Đã thêm 5 lượt nhưng có đúng 4 khóa phân biệt: `A, B, C, D`. Hai khóa khác nhau `A` và `C` rơi vào cùng thanh ghi, nhưng HLL chỉ giữ độ dài lớn nhất `4`. Từ mảng `[4, 2, 1, 0]` **không thể khôi phục danh sách khóa gốc** hay số lần xuất hiện của từng khóa.

Đây chỉ là mô hình trực quan với `m = 4`, quá nhỏ cho yêu cầu chính xác thực tế. Cài đặt bên dưới dùng hàm băm 64 bit và nhiều thanh ghi hơn.

## 4. Công thức ước lượng cardinality

Chỉ lấy thanh ghi có giá trị lớn nhất sẽ dễ bị ảnh hưởng bởi một chuỗi bit hiếm. HLL kết hợp **toàn bộ** thanh ghi qua một dạng trung bình điều hòa:

```text
Z       = 1 / ( Σ[j=0..m-1] 2^(-M[j]) )
E_raw   = α_m × m^2 × Z
        = α_m × m^2 / Σ[j=0..m-1] 2^(-M[j])
```

Ở đây `α_m` là hằng số hiệu chỉnh độ lệch phụ thuộc số thanh ghi. Một lựa chọn thường dùng:

```text
α_16 = 0,673
α_32 = 0,697
α_64 = 0,709
α_m  = 0,7213 / (1 + 1,079/m)    nếu m >= 128
```

**Trực giác của mẫu số:** khi một nhóm quan sát được các tiền tố 0 dài hơn thì `M[j]` lớn, khiến `2^(−M[j])` nhỏ đi; mẫu số giảm và ước lượng `E_raw` tăng. Trung bình điều hòa giúp hạn chế việc một thanh ghi rất lớn chi phối kết quả.

### Hiệu chỉnh khi số khóa còn ít

Nếu số khóa phân biệt còn nhỏ so với số thanh ghi, nhiều ô trong `M` vẫn bằng `0`. Khi đó công thức thô có thể đếm dư đáng kể; một phương pháp phổ biến là dùng **linear counting**.

Gọi `V` là số thanh ghi bằng 0, với `V > 0`:

```text
E_small = m × ln(m / V)
```

Trong phiên bản HLL cơ bản, quy tắc minh họa thường dùng là:

```text
Nếu E_raw <= 2,5m và V > 0: ước lượng = m × ln(m/V)
Ngược lại:                    ước lượng = E_raw
```

Với ví dụ `M = [4, 2, 1, 0]`, ta có `V = 1`, `m = 4` nên `E_small = 4 ln(4/1) ≈ 5,55`, trong khi số khóa thật bằng `4`. Kết quả không chính xác vì `m` chỉ có bốn thanh ghi. Đây là **ước lượng**, không phải một phép đếm chính xác; độ lệch giảm khi cấu hình đủ lớn và mô hình băm phù hợp.

Các triển khai thực tế như **HyperLogLog++** có thể dùng cơ chế sửa sai lệch (*bias correction*) và biểu diễn thưa cho số khóa nhỏ, đồng thời cần xem xét giới hạn miền giá trị băm khi cardinality rất lớn. Công thức hai nhánh bên trên nhằm giải thích bản chất, chưa thay thế mọi kỹ thuật hiệu chỉnh của thư viện sản xuất.

## 5. Độ chính xác và bộ nhớ

Với hash phân bố gần đều và cardinality nằm trong vùng hoạt động phù hợp, **độ lệch chuẩn tương đối** (*relative standard error*, RSE) thường được xấp xỉ:

```text
RSE ≈ 1,04 / sqrt(m)
    = 1,04 / sqrt(2^p)
```

RSE là thước đo độ phân tán thống kê của ước lượng giữa các lựa chọn hash/luồng phù hợp, **không phải cam kết sai số tối đa trong mọi lần chạy**. Chẳng hạn RSE khoảng `0,81%` không có nghĩa mọi kết quả đều nằm trong ±`0,81%` của giá trị thật. Vùng cardinality rất nhỏ, rất lớn, cách hash và phương pháp hiệu chỉnh có thể làm độ chính xác khác công thức gần đúng.

| `p` | `m = 2^p` thanh ghi | RSE xấp xỉ | Bộ nhớ với 1 byte/thanh ghi |
|---:|---:|---:|---:|
| 10 | 1.024 | 3,25% | 1 KiB |
| 12 | 4.096 | 1,63% | 4 KiB |
| 14 | 16.384 | 0,81% | 16 KiB |
| 16 | 65.536 | 0,41% | 64 KiB |

Ví dụ, chọn `p = 14` cho `m = 16.384` thanh ghi, RSE xấp xỉ `1,04/128 = 0,8125%`. Với hash 64 bit thì `q = 50` và `ρ` lớn nhất bằng `51`; một thanh ghi **6 bit** là đủ biểu diễn `0..51`. Do đó dữ liệu thanh ghi có thể nén lý thuyết xuống `16.384 × 6 / 8 = 12.288` byte = **12 KiB** (chưa tính metadata, đóng gói hoặc biểu diễn thưa). Một mảng byte đơn giản cần **16 KiB** và dễ thao tác hơn.

Nếu muốn giảm RSE khoảng một nửa, cần **gấp bốn lần** số thanh ghi, vì sai số tỷ lệ nghịch với `√m`. Số phần tử đã thấy không quyết định số ô trong HLL: mức dùng RAM phụ thuộc chủ yếu vào `p`, định dạng bộ đếm và phần lưu bổ sung.

Không được suy ra rằng thuật toán đếm đúng mọi quy mô với bộ nhớ cố định: số bit băm hữu hạn gây va chạm giữa các khóa khác nhau; khi cardinality tiến gần giới hạn miền hash, ước lượng cần xử lý và hiệu chỉnh đặc biệt.

## 6. Cài đặt Python minh họa

Đây là một bản HLL nhỏ để thấy rõ mảng thanh ghi, cách tách hash, quy tắc `max` và ước lượng. Mã sử dụng `blake2b` để sinh **64 bit hash ổn định**, nhận khóa chuỗi, lưu một byte cho mỗi thanh ghi và có hiệu chỉnh linear counting. Nó **không** bao gồm hiệu chỉnh sai lệch nâng cao, biểu diễn thưa hay cơ chế đồng bộ cập nhật, nên phù hợp cho học thuật và thử nghiệm hơn là sử dụng như thư viện sản xuất.

```python
from hashlib import blake2b
from math import log


class HyperLogLog:
    def __init__(self, precision=14):
        if not isinstance(precision, int) or not (4 <= precision <= 16):
            raise ValueError("precision phai la so nguyen trong [4, 16]")
        self.p = precision
        self.m = 1 << precision
        self.q = 64 - precision
        self.registers = bytearray(self.m)

    @staticmethod
    def _hash64(key):
        if not isinstance(key, str):
            raise TypeError("key phai la chuoi")
        data = b"hll-v1:" + key.encode("utf-8")
        digest = blake2b(data, digest_size=8).digest()
        return int.from_bytes(digest, "big")

    def add(self, key):
        value = self._hash64(key)
        index = value >> self.q  # p bit cao nhat
        suffix = value & ((1 << self.q) - 1)
        if suffix == 0:
            rank = self.q + 1
        else:
            rank = self.q - suffix.bit_length() + 1
        if rank > self.registers[index]:
            self.registers[index] = rank

    def estimate(self):
        m = self.m
        if m == 16:
            alpha = 0.673
        elif m == 32:
            alpha = 0.697
        elif m == 64:
            alpha = 0.709
        else:
            alpha = 0.7213 / (1 + 1.079 / m)

        denominator = sum(2.0 ** (-r) for r in self.registers)
        raw = alpha * m * m / denominator
        empty = self.registers.count(0)
        if raw <= 2.5 * m and empty > 0:
            return m * log(m / empty)  # linear counting
        return raw

    def merge(self, other):
        if not isinstance(other, HyperLogLog) or self.p != other.p:
            raise ValueError("hai HLL phai cung precision va quy uoc hash")
        for i in range(self.m):
            if other.registers[i] > self.registers[i]:
                self.registers[i] = other.registers[i]


left = HyperLogLog(precision=12)
right = HyperLogLog(precision=12)

for key in ("A", "B", "A", "C"):
    left.add(key)
for key in ("B", "D", "D"):
    right.add(key)

print("Tap 1, uoc luong:", left.estimate())   # gan 3
print("Tap 2, uoc luong:", right.estimate())  # gan 2
left.merge(right)
print("Hop hai tap, uoc luong:", left.estimate())  # gan 4
```

**Giải thích mã:** `value >> q` lấy `p` bit đầu làm chỉ số, còn phép `& ((1 << q) - 1)` lấy `q` bit cuối. Với suffix khác 0, `bit_length()` cho vị trí bit 1 cao nhất, từ đó tính số bit 0 đứng đầu cộng một. Nếu suffix bằng 0, ta dùng `q+1` để có một giá trị hữu hạn. Phép `merge` lấy `max` tại mỗi chỉ số, đúng với bất biến thanh ghi.

Mã không có khái niệm “đã thêm khóa chưa”, vì HLL không lưu khóa. Thêm trùng sẽ không làm thay đổi giá trị thanh ghi. Hàm `estimate()` trả về **số thực gần đúng**, không dùng làm số đếm chính xác để quyết định thanh toán, giới hạn lượt sử dụng hoặc xác minh danh tính.

## 7. Gộp HLL giữa các máy và các khoảng thời gian

Một tính chất hữu ích của HLL là **có thể gộp trực tiếp**. Nếu hai máy xử lý các tập `A` và `B` và cả hai sketch có cùng `p`, độ dài hash, cách mã hóa khóa và hàm băm/seed, ta xác định:

```text
M_A∪B[j] = max(M_A[j], M_B[j])    với mọi j = 0..m-1
```

Từng thanh ghi của bản gộp giữ cực đại quan sát được khi xử lý **hợp** `A ∪ B`. Do đó ước lượng sau khi gộp biểu diễn số khóa phân biệt trong hợp, **không phải tổng của hai ước lượng**. Nếu cùng một khóa xuất hiện trên cả hai máy, nó vẫn chỉ ảnh hưởng một giá trị băm và không bị đếm hai lần như tổng lượt.

Ví dụ:

```text
A = {A, B, C}        |A| = 3
B = {B, D}           |B| = 2
A ∪ B = {A,B,C,D}   |A ∪ B| = 4
```

HLL gộp sẽ cố gắng ước lượng khoảng `4`, chứ không cộng `3 + 2 = 5`. Các thao tác gộp tương ứng với phép `max` theo từng ô, nên có tính **giao hoán, kết hợp và lũy đẳng**: gộp cùng một sketch nhiều lần không làm số thanh ghi tăng thêm.

Để ước lượng số người dùng duy nhất trong một tháng, có thể tạo mỗi ngày một HLL có cùng cấu hình rồi gộp các sketch ngày. Nếu cần **30 ngày gần nhất**, chỉ giữ các sketch ngày thuộc cửa sổ rồi gộp lại khi truy vấn. Một sketch đơn lẻ đã gộp không thể tự loại bỏ đóng góp của ngày cũ; HLL cơ bản không hỗ trợ xóa phần tử.

Ước lượng giao hai tập đôi khi được tính bằng công thức bao hàm–loại trừ:

```text
|A ∩ B| = |A| + |B| − |A ∪ B|
```

Nhưng khi thay các số đếm bằng **ước lượng HLL**, sai số từ ba ước lượng có thể cộng dồn, đặc biệt khi phần giao rất nhỏ so với hai tập. Kết quả thậm chí có thể âm nếu không chặn lại; HLL cơ bản không phải cấu trúc tối ưu để ước lượng giao chính xác.

## 8. Chi phí và giới hạn trong thực tế

| Thao tác | Độ phức tạp | Ghi chú |
|---|---|---|
| Thêm một khóa `add(x)` | `O(1)` thao tác thanh ghi sau khi hash | Băm khóa còn tốn `O(|x|)` theo độ dài khóa |
| Ước lượng `estimate()` | `O(m)` | Duyệt tất cả `m` thanh ghi |
| Gộp hai HLL | `O(m)` | Từng thanh ghi lấy `max` |
| Bộ nhớ | `O(m)` | Phụ thuộc `p`, không tăng tuyến tính theo số khóa |

**Những điều HLL không trả lời được:**

- “Khóa `x` có chắc đã xuất hiện?” HLL không kiểm tra thành viên; nên dùng tập hợp chính xác hoặc bộ lọc thành viên phù hợp.
- “`x` xuất hiện bao nhiêu lần?” HLL không ước lượng tần suất từng khóa; bài toán đó phù hợp với bảng băm đếm hoặc Count-Min Sketch.
- “Những khóa cụ thể nào đã xuất hiện?” HLL không giữ và không khôi phục danh sách khóa.
- “Hãy xóa riêng `x` khỏi sketch.” Phép `max` làm mất thông tin về các giá trị trước đó; không thể đảo cập nhật một cách an toàn.
- “Luồng có chính xác bao nhiêu khóa?” HLL chỉ cho kết quả gần đúng, nên không dùng thay cơ chế chính xác khi kiểm toán hoặc tính tiền.

### Đối chiếu nhanh các cấu trúc

| Cấu trúc | Trả lời tốt nhất | Tính chất |
|---|---|---|
| `set` / bảng băm | Số khóa phân biệt **chính xác**, kiểm tra tồn tại | Lưu khóa; bộ nhớ tăng theo số khóa |
| Bloom filter | Khóa **có thể** đã tồn tại chưa? | Kiểm tra thành viên gần đúng |
| Count-Min Sketch | Khóa `x` xuất hiện **khoảng bao nhiêu lần**? | Ước lượng tần suất từng khóa |
| HyperLogLog | Có **khoảng bao nhiêu khóa phân biệt**? | Ước lượng cardinality; gộp hiệu quả |

**Các lưu ý triển khai:** chất lượng và tính ổn định của hash rất quan trọng; hai hệ thống chỉ gộp được sketch nếu mã hóa khóa, seed, độ dài hash, `p` và định dạng thanh ghi tương thích. Dữ liệu đầu vào có thể bị điều khiển để tạo va chạm thì cần đánh giá giải pháp hash có khóa bí mật. Khi nhiều luồng cùng cập nhật, phải đồng bộ thao tác `max` hoặc dùng thanh ghi nguyên tử thích hợp. Các triển khai thực tế nên dùng thư viện HLL/HLL++ đã được kiểm thử, hỗ trợ serialization, hiệu chỉnh sai lệch và phiên bản định dạng rõ ràng.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Luồng `[5, 7, 5, 9, 7, 5]` có bao nhiêu sự kiện và bao nhiêu phần tử phân biệt? HLL ước lượng đại lượng nào?

**Đáp án:** Có 6 sự kiện, 3 giá trị phân biệt `{5, 7, 9}`. HLL ước lượng **3** (cardinality), không ước lượng số lượt `6`.

**Câu 2.** Với `L = 8` và `p = 2`, hash `11|000100` cập nhật thanh ghi nào và giá trị `ρ` bằng bao nhiêu?

**Đáp án:** Hai bit đầu `11` biểu diễn chỉ số `3`; phần đuôi `000100` có ba bit 0 trước bit 1 đầu tiên, nên `ρ = 4`. Thao tác là `M[3] = max(M[3], 4)`.

**Câu 3.** HLL có `m = 4.096` thanh ghi. Ước tính RSE theo công thức thường dùng.

**Đáp án:** `1,04 / sqrt(4.096) = 1,04/64 = 0,01625`, tương đương khoảng **1,63%**. Đây là độ lệch chuẩn tương đối xấp xỉ, không phải giới hạn sai số tuyệt đối.

**Câu 4.** Hai máy có các tập người dùng `A = {u1, u2, u3}` và `B = {u2, u3, u4}`. Có thể cộng hai kết quả đếm HLL để tìm số duy nhất toàn hệ thống không?

**Đáp án:** Không. Hợp của hai tập có `4` người dùng; nếu cộng `3 + 3` sẽ tính trùng `u2, u3`. Cần **gộp từng thanh ghi bằng `max`**, rồi mới lấy ước lượng.

**Câu 5.** Tại sao không thể xóa một người dùng khỏi HLL sau khi đã thêm?

**Đáp án:** Thanh ghi chỉ giữ giá trị `ρ` lớn nhất của nhiều khóa. HLL không biết khóa nào tạo ra giá trị hiện tại hoặc giá trị lớn thứ hai để phục hồi khi xóa.

Khi lựa chọn HyperLogLog, hãy bắt đầu từ yêu cầu **đếm số phần tử phân biệt** và sai số tương đối có thể chấp nhận. Từ đó xác định `p`, số thanh ghi `m`, kích thước hash và cơ chế gộp; đồng thời giữ nguồn dữ liệu chính xác khi cần đối soát hoặc xây lại các sketch của cửa sổ thời gian.
