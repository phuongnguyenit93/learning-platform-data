# Count-Min Sketch cho ước lượng tần suất phần tử

## 1. Bài toán: đếm trên luồng dữ liệu lớn

Một hệ thống nhận hàng triệu sự kiện mỗi phút: lượt xem sản phẩm, truy vấn tìm kiếm, địa chỉ IP gửi yêu cầu hoặc mã lỗi. Hệ thống cần trả lời nhanh câu hỏi **“Phần tử `x` đã xuất hiện bao nhiêu lần?”**

Giải pháp chính xác là dùng bảng băm lưu `key -> count`. Tuy nhiên, bộ nhớ của bảng tăng theo số **khóa phân biệt**. Nếu luồng có hàng chục triệu khóa, việc lưu cả khóa lẫn số đếm có thể vượt ngân sách RAM.

**Count-Min Sketch (CMS)** là một cấu trúc dữ liệu xác suất (*probabilistic data structure*) giúp ước lượng tần suất khóa từ một bảng đếm kích thước cố định. Đổi lại lợi thế bộ nhớ, CMS chấp nhận **đếm dư** do va chạm băm. Bài học này mở rộng cách chọn cấu trúc dữ liệu phù hợp với thao tác và chi phí bộ nhớ: bảng băm cho kết quả chính xác, còn CMS dành cho việc thống kê tần suất gần đúng trên luồng lớn.

Sau bài này, bạn sẽ hiểu cách cập nhật, tra cứu bằng phép `min`, ý nghĩa sai số `εN`, cách chọn kích thước và những giới hạn khi tìm khóa phổ biến hoặc xóa dữ liệu.

## 2. Cấu trúc bảng và các hàm băm

CMS cơ bản gồm một bảng `d` hàng và `w` cột, ban đầu mỗi ô chứa bộ đếm `0`. Hàng `i` sử dụng hàm băm `h_i(x)` để chọn cột từ `0` đến `w−1`. Các hàng dùng các phép băm khác nhau nhằm giảm nguy cơ cùng bị va chạm lớn.

```text
Khóa x
   |
   +── h_0(x) ───► C[0][h_0(x)]       hàng 0
   +── h_1(x) ───► C[1][h_1(x)]       hàng 1
   +── h_2(x) ───► C[2][h_2(x)]       hàng 2
   ...
   +── h_(d-1)(x) ► C[d-1][h_(d-1)(x)]
```

| Ký hiệu | Ý nghĩa |
|---|---|
| `f(x)` | Tần suất thực của khóa `x` |
| `C[i][j]` | Bộ đếm ở hàng `i`, cột `j` |
| `w` | Số cột mỗi hàng (*width*) |
| `d` | Số hàng (*depth*) |
| `N` | Tổng số lượt cập nhật, tính cả trọng số: `N = Σ_x f(x)` |
| `f̂(x)` | Tần suất ước lượng |
| `ε` | Tham số giới hạn sai số cộng |
| `δ` | Tham số xác suất vượt quá giới hạn |

CMS **không lưu khóa**. Những khóa khác nhau có thể rơi vào cùng ô của một hàng: mỗi ô chứa tổng lượng cập nhật của mọi khóa được băm vào đó.

## 3. Hai thao tác cốt lõi

### Cập nhật: tăng đúng một ô trên mỗi hàng

Khi xuất hiện khóa `x` với trọng số nguyên dương `c`, tăng `c` ở vị trí ứng với `x` trên **tất cả** các hàng:

```text
add(x, c):
    yêu cầu c > 0
    for i = 0 .. d-1:
        C[i][h_i(x)] += c
```

Ví dụ `add("táo", 5)` tương đương với năm lần `add("táo", 1)`. Ta có thể xử lý từng sự kiện khi nó đến mà không giữ toàn bộ luồng.

### Truy vấn: lấy số nhỏ nhất

Truy vấn khóa `x` chỉ cần đọc một ô trên mỗi hàng:

```text
estimate(x):
    return min(C[i][h_i(x)] for i = 0 .. d-1)
```

Tại một hàng bất kỳ, ô chứa số đếm của `x` có thể còn chứa số đếm của những khóa khác:

```text
C[i][h_i(x)] = f(x) + (tổng tần suất khóa khác va chạm ở ô này)
             >= f(x)
```

Vì các số đếm nhiễu không âm, **từng hàng luôn đếm bằng hoặc lớn hơn thực tế**. Lấy giá trị nhỏ nhất chọn ra hàng có ít nhiễu nhất. Trong mô hình chỉ thêm và không tràn bộ đếm, CMS **không đếm thiếu** nhưng có thể đếm dư. Lấy tổng, trung bình hoặc giá trị lớn nhất không có lợi thế tương tự trong việc giảm đếm dư.

## 4. Minh họa va chạm bằng một ví dụ tính tay

Cho CMS với `d = 3` hàng, `w = 6` cột. Luồng có `A` xuất hiện 5 lần, `B` xuất hiện 3 lần và `C` xuất hiện 2 lần. Giả sử các vị trí do hàm băm trả về là:

| Khóa | `h_0` | `h_1` | `h_2` | Số lần thật |
|---|---:|---:|---:|---:|
| `A` | 1 | 2 | 0 | 5 |
| `B` | 1 | 4 | 3 | 3 |
| `C` | 4 | 2 | 5 | 2 |

Sau khi cập nhật đủ `N = 10` lượt, bảng có dạng:

```text
                 CỘT
HÀNG          0   1   2   3   4   5
  0          [0,  8,  0,  0,  2,  0]   A và B va chạm ở cột 1
  1          [0,  0,  7,  0,  3,  0]   A và C va chạm ở cột 2
  2          [5,  0,  0,  3,  0,  2]   A, B, C nằm ở các ô riêng
```

Khi đó:

- `f̂(A) = min(8, 7, 5) = 5`: chính xác.
- `f̂(B) = min(8, 3, 3) = 3`: chính xác.
- `f̂(C) = min(2, 7, 2) = 2`: chính xác.

Giả sử một khóa `D` chưa từng xuất hiện nhưng được băm lần lượt vào các cột `(1, 2, 0)`. Ta vẫn có `f̂(D) = min(8, 7, 5) = 5`, trong khi `f(D) = 0`. Cả ba hàng đều bị nhiễu tại vị trí của `D`; đây là **ước lượng dư**. Nếu ít nhất một vị trí của `D` có bộ đếm `0`, truy vấn sẽ trả về `0`. Kết quả `estimate(x) > 0` không chứng minh rằng khóa đã từng xuất hiện.

## 5. Giới hạn sai số xác suất

Giả sử các hàm băm có xác suất va chạm đủ tốt và các hàng độc lập theo yêu cầu của phân tích, CMS có bảo đảm cho **một khóa truy vấn cố định `x`**:

```text
f(x) ≤ f̂(x) ≤ f(x) + εN       với xác suất ít nhất 1 − δ
```

Trong đó `N` là tổng trọng số các lượt cập nhật dương. Một cấu hình thường dùng:

```text
w = ceil(e / ε)               với e ≈ 2,71828
d = ceil(ln(1 / δ))
```

**Vì sao hiệu quả?** Nếu hai khóa có xác suất băm vào cùng cột là khoảng `1/w`, lượng nhiễu kỳ vọng trên một hàng không vượt quá `(N − f(x))/w`. Bất đẳng thức Markov cho xác suất nhiễu vượt `εN` không quá `1/(wε)`. Chọn `w ≥ e/ε` đưa mức này xuống không quá `1/e`. Với `d` hàng độc lập, xác suất **cả `d` hàng đều nhiễu lớn** không quá `e^(−d) ≤ δ`; lấy `min` giữa các hàng hoàn tất lập luận.

Cần hiểu đúng ba giới hạn:

1. **Sai số cộng, không phải sai số tương đối.** Nếu `ε = 0,01`, biên sai số là `1%` của **tổng số lượt `N`**, không phải `1%` của `f(x)`. Khóa hiếm có thể bị ước lượng dư rất nhiều so với tần suất thực.
2. **Giới hạn theo xác suất.** Không có cam kết mọi khóa và mọi lượt truy vấn đều đồng thời đạt giới hạn. Nếu cần bảo đảm cho `K` khóa cố định, có thể dùng *union bound* với mức thất bại khoảng `δ/K` cho từng khóa; truy vấn được chọn thích nghi theo sketch cần phân tích riêng.
3. **Phụ thuộc hàm băm.** Công thức dựa trên các giả định về va chạm và độc lập; một hàm băm yếu hoặc khóa do tác nhân đối kháng lựa chọn có thể làm sai lệch tỷ lệ thực tế.

### Ví dụ chọn tham số

Muốn sai số cộng không vượt khoảng `1%` tổng lượt cập nhật với độ tin cậy `99%` cho một khóa, lấy `ε = 0,01` và `δ = 0,01`:

```text
w = ceil(2,71828 / 0,01) = 272 cột
d = ceil(ln(100))        = 5 hàng
số bộ đếm                  = 272 × 5 = 1.360
```

Nếu mỗi ô đếm là số nguyên 4 byte, bảng cần `1.360 × 4 = 5.440` byte, xấp xỉ **5,31 KiB** (chưa tính chi phí cấu trúc phụ). Với `N = 1.000.000` sự kiện, biên sai số là `εN = 10.000` lượt. Nếu cần ước lượng một khóa xuất hiện chỉ vài lần, biên sai số này có thể quá rộng; khi đó phải chọn `ε` nhỏ hơn hoặc lưu chính xác các khóa cần theo dõi.

| Mong muốn | Thay đổi | Chi phí |
|---|---|---|
| Giảm đếm dư | Giảm `ε`, tăng `w` | Nhiều bộ đếm hơn |
| Tăng độ tin cậy | Giảm `δ`, tăng `d` | Nhiều bộ đếm và lần băm hơn |
| Giữ RAM không đổi khi số khóa tăng | Giữ `w, d` cố định | Biên `εN` tăng theo tổng lượt cập nhật |
| Tránh mất độ chính xác vì tràn | Dùng kiểu đếm đủ rộng | Tăng số byte trên bộ đếm |

## 6. Cài đặt bằng Python

Ví dụ dưới đây cài đặt CMS đơn giản, dùng `blake2b` để tạo hash tái lập được từ khóa UTF-8 và chỉ số hàng. Mã chỉ nhận **khóa chuỗi**, cập nhật **số nguyên dương** và số đếm Python không giới hạn kích thước cố định. Hash ở đây phù hợp minh họa, nhưng không tự chứng minh những giả định độc lập toán học ở phần sai số.

```python
from hashlib import blake2b
from math import ceil, e, log


class CountMinSketch:
    def __init__(self, width, depth):
        if not isinstance(width, int) or width <= 0:
            raise ValueError("width phai la so nguyen duong")
        if not isinstance(depth, int) or depth <= 0:
            raise ValueError("depth phai la so nguyen duong")
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self.total = 0

    def _columns(self, key):
        if not isinstance(key, str):
            raise TypeError("key phai la chuoi")
        raw_key = key.encode("utf-8")
        for row in range(self.depth):
            data = row.to_bytes(8, "little") + raw_key
            digest = blake2b(data, digest_size=8).digest()
            yield int.from_bytes(digest, "little") % self.width

    def add(self, key, count=1):
        if not isinstance(count, int) or count <= 0:
            raise ValueError("count phai la so nguyen duong")
        for row, col in enumerate(self._columns(key)):
            self.table[row][col] += count
        self.total += count

    def estimate(self, key):
        return min(
            self.table[row][col]
            for row, col in enumerate(self._columns(key))
        )

    def merge(self, other):
        if self.width != other.width or self.depth != other.depth:
            raise ValueError("kich thuoc khong tuong thich")
        # Chi gop khi hash, seed va cach ma hoa khoa giong nhau.
        for row in range(self.depth):
            for col in range(self.width):
                self.table[row][col] += other.table[row][col]
        self.total += other.total


epsilon, delta = 0.01, 0.01
cms = CountMinSketch(
    width=ceil(e / epsilon),
    depth=ceil(log(1 / delta))
)
cms.add("tao", 5)
cms.add("cam", 3)
cms.add("le", 2)

print(cms.estimate("tao"))      # >= 5
print(cms.estimate("cam"))      # >= 3
print(cms.estimate("le"))       # >= 2
print(cms.estimate("chua-co"))  # co the > 0 do va cham
print(cms.total)                # 10
```

`merge` chỉ kiểm tra kích thước trong ví dụ; quy ước chung về hash/seed/mã hóa khóa phải được hệ thống bảo đảm. Nếu một bên chuẩn hóa Unicode hoặc dùng seed khác, phép cộng bảng sẽ cho kết quả sai về ý nghĩa. Trong triển khai thực tế, metadata phiên bản hash nên được lưu kèm sketch để kiểm tra tương thích trước khi gộp.

Vì Python lưu các phần tử `int` và `list` dưới dạng đối tượng, mức RAM của ví dụ **cao hơn đáng kể** so với `4wd` byte. Cấu trúc sản xuất thường dùng mảng số nguyên liên tiếp, lưu dữ liệu theo dạng nén và kiểm soát tràn bộ đếm.

### Độ phức tạp

| Thao tác | Thời gian | Giải thích |
|---|---|---|
| `add(x)` | `O(d)` | Một lần băm và tăng bộ đếm ở mỗi hàng |
| `estimate(x)` | `O(d)` | Một lần băm và đọc bộ đếm ở mỗi hàng |
| `merge(other)` | `O(dw)` | Cộng tất cả các bộ đếm |
| Bộ nhớ | `O(dw)` | Không tăng theo số khóa phân biệt |

Khi `ε` và `δ` cố định, `w` và `d` cũng cố định nên chi phí mỗi lượt cập nhật không tăng theo kích thước luồng. Tuy nhiên, giá trị các bộ đếm vẫn tăng theo tổng số lượt đã quan sát.

## 7. Gộp thống kê và cửa sổ thời gian

Nếu hai máy xử lý hai phần luồng và dùng cùng tham số, hàm băm, seed và quy tắc mã hóa khóa, có thể tính bảng gộp:

```text
C_gộp[i][j] = C_máy_1[i][j] + C_máy_2[i][j]
N_gộp       = N_máy_1 + N_máy_2
```

Kết quả tương đương việc đưa tất cả sự kiện vào một CMS cùng cấu hình. Tính chất này hữu ích cho thống kê phân tán hoặc tổng hợp dữ liệu theo ngày. **Không** thể gộp chỉ vì hai sketch cùng kích thước: nếu vị trí hash khác nhau, một khóa được cộng vào những ô không tương ứng.

CMS cơ bản đếm **từ lúc khởi tạo**; nó không tự quên sự kiện cũ. Khi cần tần suất trong 60 phút gần nhất, có thể giữ một sketch cho mỗi cửa sổ 5 phút, chỉ gộp các cửa sổ còn hiệu lực. Phương án này tiêu tốn thêm RAM và chỉ chính xác đến độ phân giải của cửa sổ. Hệ thống phải quy định cách xử lý sự kiện đến muộn và thời điểm ranh giới giữa các cửa sổ.

## 8. Khi nào dùng và những giới hạn cần nhớ?

Ứng dụng phù hợp gồm ước lượng tần suất mã lỗi, lượt xem sản phẩm, truy vấn tìm kiếm, endpoint được gọi nhiều và thống kê phân tán. Có thể dùng CMS để **sàng lọc** các khóa có khả năng xuất hiện nhiều, sau đó kiểm tra bằng dữ liệu chính xác nếu quyết định mang tính quan trọng.

| Bài toán | Lựa chọn hợp lý |
|---|---|
| Cần số đếm chính xác cho từng khóa | Bảng băm `key -> count` |
| Cần tần suất gần đúng với RAM giới hạn | Count-Min Sketch |
| Cần kiểm tra khóa có thể tồn tại không | Bloom filter (kiểm tra thành viên gần đúng) |
| Cần đếm số khóa phân biệt | HyperLogLog (ước lượng cardinality) |

**Không tự liệt kê heavy hitters:** CMS không lưu tên khóa. Nó chỉ ước lượng khi được đưa một khóa cụ thể. Để tìm top-K, phải có một cách giữ **tập ứng viên** từ luồng, chẳng hạn thuật toán Space-Saving hoặc một bộ đệm khóa ứng viên, rồi mới dùng CMS để đánh giá tần suất của những khóa đó.

**Không tự ý giảm bộ đếm:** nếu chỉ vì `estimate(x) > 0` mà gọi phép cập nhật âm để “xóa” `x`, ta có thể giảm số đếm của những khóa khác đang va chạm. Những mô hình luồng có cập nhật âm được kiểm soát và tần suất cuối không âm (*strict turnstile*) có biến thể hoặc phân tích riêng; cài đặt trong bài cố ý giới hạn ở mô hình **chỉ thêm** (*insertion-only*).

**Cần kiểm soát tính nhất quán:** cập nhật đồng thời không được làm mất lượt tăng; bộ đếm cố định phải có chính sách chống tràn; dữ liệu đầu vào cần chuẩn hóa và tuần tự hóa nhất quán; không thay đổi hash/seed khi vẫn đang sử dụng bảng cũ. Nếu tác nhân có thể chọn khóa để tạo nhiều va chạm, phải cân nhắc hash có khóa bí mật hoặc cơ chế bảo vệ thích hợp.

## 9. Bài tập tự kiểm tra

**Câu 1.** Với `d = 3`, ba bộ đếm ứng với khóa `x` là `(12, 7, 10)`. Ước lượng bằng bao nhiêu? Vì sao không lấy `12`?

**Đáp án:** `f̂(x) = min(12, 7, 10) = 7`. Các số lớn hơn có thể chứa tần suất của khóa khác do va chạm.

**Câu 2.** Chọn kích thước theo công thức chuẩn cho `ε = 0,005` và `δ = 0,05`.

**Đáp án:** `w = ceil(e/0,005) = 544`, `d = ceil(ln(20)) = 3`. Có `1.632` bộ đếm; nếu mỗi bộ đếm chiếm 8 byte thì bảng cần `13.056` byte.

**Câu 3.** Với `N = 200.000` lượt và `ε = 0,01`, khóa `x` xuất hiện thực `40` lần. Trong sự kiện bảo đảm sai số có hiệu lực, `f̂(x)` nằm trong khoảng nào?

**Đáp án:** `εN = 2.000`, nên `40 ≤ f̂(x) ≤ 2.040`. Không thể kết luận ước lượng của khóa hiếm luôn gần `40`.

**Câu 4.** Hai sketch có cùng `w, d` nhưng seed hash khác nhau. Có thể gộp từng ô không?

**Đáp án:** Không. Cùng khóa có thể nằm ở các cột khác nhau trên hai bảng; phải thống nhất phép băm, seed và mã hóa khóa.

**Câu 5.** Vì sao CMS không thể tự trả về “10 khóa xuất hiện nhiều nhất”?

**Đáp án:** Nó không lưu tên khóa; chỉ có thể trả về ước lượng khi đã biết khóa cần truy vấn. Cần một cơ chế giữ ứng viên riêng.

Khi thiết kế CMS, hãy xác định **tổng số lượt `N` dự kiến** và **sai số tuyệt đối chấp nhận được**, rồi mới chọn `ε`, `δ` để tính `w` và `d`. Bên cạnh bộ nhớ và thời gian, cần thiết kế rõ cách đồng bộ, gộp, hết hạn dữ liệu và điều kiện nào buộc phải kiểm tra số đếm chính xác.
