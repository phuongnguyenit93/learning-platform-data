# Đo bộ nhớ theo bit và giới hạn thông tin tối thiểu

Một triệu giá trị Boolean có nhất thiết phải chiếm một triệu byte? Một dãy gồm một nghìn số nguyên trong miền 0–999 có nhất thiết phải dùng bốn nghìn byte? Và nếu cần lưu chính xác một tập gồm ba phần tử được chọn từ mười sáu phần tử, phải dành bao nhiêu bit để phân biệt mọi khả năng?

Những câu hỏi ấy dẫn tới hai cách nhìn khác nhau về bộ nhớ:

1. **Mức thông tin tối thiểu:** có bao nhiêu trạng thái phân biệt cần biểu diễn? Từ đó suy ra số bit ít nhất trong một mô hình mã hóa cụ thể.
2. **Chi phí biểu diễn thực tế:** chương trình dùng kiểu dữ liệu, khối cấp phát, địa chỉ, độ căn chỉnh và cấu trúc hỗ trợ nào để lưu, đọc, ghi và cập nhật trạng thái đó?

Một biểu diễn gọn thường tiết kiệm bộ nhớ bằng cách tiến gần giới hạn thông tin, nhưng có thể phải đổi lấy **thời gian giải mã**, **khả năng truy cập ngẫu nhiên**, **chi phí cập nhật** hoặc **độ phức tạp cài đặt**. Ngược lại, cấu trúc dư bit có thể cố ý dành không gian để thao tác nhanh.

Đây là bài đầu của chương **Biểu diễn gọn** trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, nhằm xây dựng nền tảng cấu trúc dữ liệu, bất biến, thao tác và phân tích độ phức tạp thời gian/bộ nhớ. Bài tập trung vào **đo bộ nhớ theo bit và giới hạn thông tin tối thiểu**, từ các phép đếm trạng thái đến cách đo một cấu trúc đang chạy trong máy.

## 1. Mục tiêu và quy ước

Sau bài này, bạn có thể:

1. Phân biệt **bit, byte, KB, KiB, MB và MiB**, cũng như kích thước logic với kích thước cấp phát.
2. Suy ra chặn dưới `⌈log₂N⌉` bit từ số lượng trạng thái N trong mô hình **mã có độ dài cố định**.
3. Tính số bit cần thiết cho một số nguyên trong miền, dãy giá trị độc lập, tập con, hoán vị và đồ thị.
4. Phân biệt **chi phí mã hóa từng phần tử** với **chi phí mã hóa cả khối**.
5. Giải thích vì sao **entropy Shannon** nói về số bit trung bình của một nguồn xác suất, không phải số bit tối thiểu worst-case cho mọi giá trị.
6. Nhận diện bộ nhớ bổ sung từ metadata, padding, alignment, con trỏ, độ dài/capacity và cấu trúc chỉ mục.
7. Cài đặt một mảng số nguyên **đóng gói bit** an toàn trong Python và một bit vector theo từ máy trong C++17.
8. So sánh cách biểu diễn theo **dung lượng, thời gian truy cập, thao tác cập nhật và tính khả thi**.
9. Kiểm thử các trường hợp biên, nhất là giá trị bằng 0, miền một trạng thái và ranh giới byte/từ máy.

Trong bài:

- `n`: số phần tử hoặc đối tượng.
- `N`: số trạng thái **có thể phân biệt** của đối tượng cần lưu.
- `b`: số bit cho một mã có độ dài cố định.
- `w`: số bit của một từ máy hoặc đơn vị lưu trữ được xét.
- `⌈x⌉`: làm tròn **lên**; `⌊x⌋`: làm tròn **xuống**.
- `log₂`: logarit cơ số hai.

Các giới hạn tính toán chỉ đúng khi đã xác định **chính xác những trạng thái nào hợp lệ** và **thông tin nào đã được biết sẵn từ bên ngoài**.

## 2. Bit là đơn vị của khả năng phân biệt

Một **bit** có hai giá trị, thường ký hiệu:

```text
0
1
```

Một dãy b bit có đúng:

\[
2^b
\]

mã khác nhau khi **mọi dãy bit cùng độ dài b** đều có thể dùng.

Ví dụ:

| Số bit | Số mã nhị phân có thể biểu diễn |
|---:|---:|
| 0 | 1 mã rỗng |
| 1 | 2 |
| 2 | 4 |
| 3 | 8 |
| 4 | 16 |
| 8 | 256 |
| 10 | 1.024 |
| 16 | 65.536 |
| 20 | 1.048.576 |

Với ba bit, các mã là:

```text
000 001 010 011 100 101 110 111
```

Có tám mã, nên ba bit đủ để nhận diện một trong tám trạng thái. Hai bit chỉ có bốn mã, không đủ.

### Vì sao không phải cứ b bit là b giá trị?

Bit là **đơn vị lựa chọn nhị phân**. Mỗi bit nhân đôi số cấu hình có thể biểu diễn. Do vậy số trạng thái tăng **theo lũy thừa** `2^b`, chứ không tăng tuyến tính theo b.

Khi đảo câu hỏi “cần bao nhiêu bit để chứa N trạng thái?”, ta nhận logarit cơ số hai.

## 3. Đổi đơn vị: bit, byte và bội số thập phân/nhị phân

Một **byte (B)** hiện đại trong những môi trường lập trình thông dụng chứa **8 bit**. Để đổi từ bit thành số byte lưu trữ tối thiểu theo từng byte:

\[
B_{\mathrm{payload}}
=
\left\lceil\frac{\text{bitCount}}8\right\rceil.
\]

Nếu có 17 bit dữ liệu, phải cấp ít nhất:

\[
\left\lceil\frac{17}{8}\right\rceil=3\text{ byte}
\]

trong bộ nhớ chỉ có thể cấp phát theo byte. Ba byte chứa 24 bit, nên có **7 bit cuối chưa dùng**.

### Bảng đơn vị

| Ký hiệu | Giá trị theo byte | Nhận xét |
|---|---:|---|
| 1 B | 8 bit | Byte |
| 1 kB | 1.000 B | Bội số thập phân |
| 1 KiB | 1.024 B | Bội số nhị phân |
| 1 MB | 1.000.000 B | Thập phân |
| 1 MiB | 1.048.576 B | Nhị phân |
| 1 GB | 1.000.000.000 B | Thập phân |
| 1 GiB | 1.073.741.824 B | Nhị phân |

**Không được nhầm chữ `b` viết thường (bit) với `B` viết hoa (byte)**. Khi tài liệu ghi “1 MB”, hãy kiểm tra nó dùng đúng chuẩn thập phân hay đang dùng từ cũ theo nghĩa 1 MiB.

### Ví dụ một triệu bit

Một triệu bit cần ít nhất:

\[
\frac{1.000.000}{8}=125.000\text{ B}
\]

khi đóng gói liên tục, tương đương:

\[
\frac{125.000}{1.024}\approx122{,}07\text{ KiB}.
\]

Nếu lưu một triệu cờ trong một mảng mà mỗi cờ chiếm một byte, riêng vùng payload đã cần **1.000.000 B**, gấp tám lần phần bit đóng gói.

Kích thước thực có thể lớn hơn hai con số này vì container, metadata và cơ chế cấp phát.

## 4. Định lý đếm trạng thái: giới hạn tối thiểu của mã cố định

Giả sử một đối tượng có **N trạng thái hợp lệ phân biệt**, và ta muốn mỗi trạng thái được mã hóa bằng **đúng b bit**, cho phép giải mã không mất thông tin.

Vì có nhiều nhất `2^b` chuỗi bit khác nhau, điều kiện cần là:

\[
2^b\ge N.
\]

Lấy logarit hai vế:

\[
b\ge\log_2 N.
\]

Số bit nguyên nhỏ nhất là:

\[
\boxed{
b_{\min}
=\left\lceil\log_2N\right\rceil,
\quad N\ge1.
}
\]

**Chứng minh bằng nguyên lý chuồng bồ câu:** nếu `2^b<N`, có nhiều trạng thái hơn mã. Ít nhất hai trạng thái phải nhận cùng mã, nên không thể giải mã phân biệt chúng. Ngược lại, với `2^b≥N`, ta có thể đánh số N trạng thái từ 0 đến N−1 và gán mỗi số một mã b bit. Vậy chặn là **đạt được về mặt mã hóa cố định**.

### Trường hợp N=1

Nếu chỉ tồn tại đúng **một** trạng thái và bộ giải mã đã biết quy ước này, không cần bit payload để phân biệt:

\[
\lceil\log_2 1\rceil=0.
\]

Điều đó **không có nghĩa** một file hay một đối tượng chạy trong máy chiếm 0 byte. File có thể cần header, chiều dài và cơ chế nhận biết ranh giới; một đối tượng còn có overhead quản lý.

### Vì sao phải nói “mã có độ dài cố định”?

Nếu cho phép mã có độ dài thay đổi, người nhận cần biết **ranh giới thông điệp**, chẳng hạn qua mã prefix-free, độ dài truyền riêng hoặc quy tắc kết thúc. Đếm mọi chuỗi có độ dài từ 0 đến b khác với đếm chuỗi có **đúng b bit**. Vì thế công thức trên phải đi cùng mô hình **độ dài cố định hoặc yêu cầu ranh giới/khả năng giải mã tương đương**; không được áp bừa cho mọi mã biến độ dài mà bỏ chi phí mô tả biên.

## 5. Công thức tính chặn dưới mà không dùng số thực

Trong lập trình, không nhất thiết tính `log₂` bằng số thực rồi làm tròn, vì tại các lũy thừa của hai có thể phát sinh lỗi làm tròn.

Với `N≥1` nguyên, công thức chính xác là:

\[
\boxed{
\lceil\log_2 N\rceil
=\operatorname{bitLength}(N-1).
}
\]

Trong Python, `int.bit_length()` cho số bit cần biểu diễn trị tuyệt đối của số nguyên dương, và bằng 0 với số 0.

```python
def minimum_fixed_bits(number_of_states: int) -> int:
    if (
        not isinstance(number_of_states, int)
        or isinstance(number_of_states, bool)
    ):
        raise TypeError("Số trạng thái phải là số nguyên")
    if number_of_states < 1:
        raise ValueError("Phải có ít nhất một trạng thái")

    return (number_of_states - 1).bit_length()


assert minimum_fixed_bits(1) == 0
assert minimum_fixed_bits(2) == 1
assert minimum_fixed_bits(3) == 2
assert minimum_fixed_bits(8) == 3
assert minimum_fixed_bits(9) == 4
assert minimum_fixed_bits(256) == 8
assert minimum_fixed_bits(257) == 9
```

### Phân biệt `bit_length(N)` và `bit_length(N−1)`

Nếu cần mã hóa **một trong N trạng thái**, trạng thái đánh số `0..N−1`. Với N=8, ba bit đủ vì mã lớn nhất là 7 (`111₂`).

- `bit_length(8)=4`: số bit để biểu diễn **chính số 8**.
- `bit_length(8−1)=3`: số bit để mã hóa một trong **8 trạng thái**.

Nhầm hai số này gây lãng phí một bit ở mọi ngưỡng là lũy thừa của hai.

## 6. Số nguyên trong một miền hữu hạn

Giả sử một biến x chỉ nhận giá trị nguyên trong đoạn **bao gồm cả hai đầu mút**:

\[
L\le x\le R.
\]

Số trạng thái hợp lệ là:

\[
N=R-L+1.
\]

Do đó, giới hạn tối thiểu của mã cố định là:

\[
\boxed{
b_{\min}
=\left\lceil\log_2(R-L+1)\right\rceil.
}
\]

Ta có thể **dịch miền** bằng cách lưu:

\[
y=x-L.
\]

Khi ấy y thuộc `0..N−1` và có thể lưu trong `b_{\min}` bit.

### Ví dụ

| Miền giá trị | N | Số bit tối thiểu |
|---|---:|---:|
| `0..0` | 1 | 0 |
| `0..1` | 2 | 1 |
| `0..2` | 3 | 2 |
| `0..7` | 8 | 3 |
| `0..8` | 9 | 4 |
| `0..255` | 256 | 8 |
| `0..256` | 257 | 9 |
| `−5..5` | 11 | 4 |
| `100..999` | 900 | 10 |
| `0..999.999` | 1.000.000 | 20 |

Ví dụ miền `−5..5` có 11 giá trị, nên cần `⌈log₂11⌉=4` bit. Không nhất thiết dùng biểu diễn số nguyên dấu hai như một biến máy riêng, nếu ta có thể lưu `x+5` trong 4 bit và biết quy tắc giải mã.

### Đừng quên giá trị đặc biệt

Nếu ngoài miền `0..255` còn cần thêm trạng thái “không có dữ liệu”, số trạng thái là 257, nên cần **9 bit** trong mã cố định.

Một byte là vừa đủ cho 256 giá trị, **không đủ để mã hóa thêm một sentinel phân biệt** nếu không có quy ước bên ngoài.

## 7. Dãy giá trị: chặn của toàn bộ dãy và của từng ô

Cho dãy độ dài n, mỗi vị trí độc lập có thể nhận một trong q ký hiệu. Nếu **mọi tổ hợp đều hợp lệ**, số dãy khác nhau là:

\[
N=q^n.
\]

Một mã cố định cho **toàn dãy** cần ít nhất:

\[
\boxed{
\left\lceil\log_2(q^n)\right\rceil
=\left\lceil n\log_2 q\right\rceil
}
\]

bit.

Nếu từng phần tử được cấp một trường cố định riêng, mỗi trường cần `⌈log₂q⌉` bit và tổng là:

\[
\boxed{
n\left\lceil\log_2q\right\rceil.
}
\]

Hai giá trị **có thể khác nhau** vì việc làm tròn diễn ra trước hay sau khi nhân n.

### Ví dụ năm chữ số thập phân

Mỗi vị trí có 10 khả năng (`0..9`), n=5:

\[
N=10^5=100.000.
\]

Mã hóa toàn bộ như một số nguyên từ 0 đến 99.999:

\[
\lceil\log_2 100.000\rceil=17\text{ bit}.
\]

Còn dùng **4 bit cho mỗi chữ số** cần:

\[
5\cdot4=20\text{ bit}.
\]

Ba bit chênh lệch là chi phí của việc **làm tròn mỗi trường độc lập** thay vì đóng gói cả khối theo hệ cơ số mười.

### Đánh đổi truy cập

- Mã hóa từng chữ số vào trường 4 bit: truy cập chữ số thứ i bằng phép dịch và mask tương đối thuận tiện.
- Mã hóa cả dãy thành số cơ số mười: tiết kiệm bit hơn, nhưng truy cập/chỉnh sửa một chữ số cần phép chia/lấy dư hoặc xử lý bổ sung.

Không được tự suy rằng cách dùng ít bit nhất cũng có thời gian cập nhật tốt nhất.

## 8. Ví dụ thực tế: một nghìn giá trị trong miền 0–999

Giả sử cần lưu n=1.000 số nguyên, mỗi số nằm trong `0..999`.

Mỗi số có 1.000 trạng thái:

\[
b=\lceil\log_2 1000\rceil=10.
\]

Nếu mã hóa từng số cố định bằng 10 bit:

\[
1.000\cdot10=10.000\text{ bit}.
\]

Vì 10.000 chia hết cho 8, vùng payload nhỏ nhất là:

\[
10.000/8=1.250\text{ B}.
\]

Nếu lưu bằng mảng các phần tử 32 bit:

\[
1.000\cdot32/8=4.000\text{ B}.
\]

**So sánh chỉ phần payload:**

| Phương án | Dung lượng |
|---|---:|
| 32 bit mỗi số | 4.000 B |
| 16 bit mỗi số | 2.000 B |
| 10 bit mỗi số đóng gói | 1.250 B |
| Chặn lý thuyết cho cả dãy | `⌈1000 log₂1000⌉` = 9.966 bit = 1.246 B sau làm tròn byte |

**Điểm cần chú ý:** 10 bit/phần tử là **tối thiểu cho một trường độc lập có độ dài cố định**, nhưng chưa phải chặn tuyệt đối cho **toàn bộ dãy**. Chặn mã cố định của toàn dãy chỉ là 9.966 bit, do có thể mã hóa trong cơ số 1.000. Đổi lại, giải mã/truy cập một vị trí có thể khó hơn.

Bảng không tính header, chiều dài, địa chỉ, container và phần đệm căn chỉnh.

## 9. Mảng Boolean và bitset

Một dãy n Boolean độc lập có:

\[
N=2^n
\]

trạng thái khác nhau. Do đó:

\[
b_{\min}
=\lceil\log_2(2^n)\rceil=n.
\]

**n bit là chặn dưới chính xác** để lưu mọi dãy Boolean độ dài n, khi n và thứ tự bit đã được biết.

Ví dụ:

```text
n = 12

Cờ:
1 0 0 1 0 1 1 0 0 0 1 1

Payload lý thuyết: 12 bit
Cấp phát theo byte: ceil(12/8) = 2 byte
```

### Khi lưu theo từ máy

Nếu dùng từ 64 bit và gói n bit vào một mảng các từ:

\[
\mathrm{words}
=\left\lceil\frac{n}{64}\right\rceil.
\]

Dung lượng vùng từ máy:

\[
64\left\lceil\frac{n}{64}\right\rceil\text{ bit}.
\]

Với n=130:

\[
\lceil130/64\rceil=3\text{ từ},
\]

nghĩa là **192 bit = 24 byte** vùng từ máy, dù payload logic chỉ 130 bit và mức làm tròn theo byte chỉ cần 17 byte.

Sự lãng phí tối đa do **làm tròn theo từ 64 bit** là 63 bit ở từ cuối, chưa kể overhead của vector.

### Mảng byte so với bitset

Lưu n cờ bằng n byte cần 8n bit payload. Lưu bitset cần n bit, nên về vùng payload có thể tiết kiệm gần **8 lần**. Tuy nhiên, trong một số workload, mảng byte có thể cho truy cập/ghi đơn giản hơn hoặc tránh chi phí read-modify-write của bitset.

## 10. Kỹ thuật đóng gói: bit offset, mask và ranh giới byte

Nếu mỗi phần tử chiếm w bit, phần tử thứ i (đánh số từ 0) bắt đầu tại:

\[
\mathrm{bitOffset}(i)=i\cdot w.
\]

Để tìm byte chứa bit đầu:

\[
\mathrm{byteIndex}
=\left\lfloor\frac{i\,w}{8}\right\rfloor,
\]

và vị trí bit bên trong byte:

\[
\mathrm{bitInByte}
=(i\,w)\bmod8.
\]

Ví dụ ba giá trị 3 bit:

```text
value[0] = 5 = 101₂
value[1] = 2 = 010₂
value[2] = 7 = 111₂
```

Nếu dùng quy ước **bit thấp trước trong dòng bit**, ta có các trường:

```text
Trường 0: bit 0..2
Trường 1: bit 3..5
Trường 2: bit 6..8
```

Trường thứ ba **bắt đầu ở bit 6 của byte đầu và tràn sang byte thứ hai**. Điều này minh họa tại sao truy cập một trường đóng gói có thể cần đọc nhiều byte/từ máy.

### Những thông tin mà bộ giải mã phải biết

- w: mỗi trường có bao nhiêu bit.
- n: có bao nhiêu trường.
- Thứ tự bit bên trong byte/từ máy.
- Cách xử lý các bit đệm cuối.
- Quy tắc mã hóa có dấu hay miền đã dịch.
- Phiên bản định dạng nếu layout có thể thay đổi.

Nếu các tham số đó được cung cấp bởi giao thức hoặc schema, không nhất thiết ghi lại trong từng khối payload. Nếu không, **metadata giải mã cũng là một phần chi phí lưu trữ thực tế**.

## 11. Python: mảng số nguyên đóng gói bit

Ví dụ này xây dựng một container học thuật có độ rộng trường `width` bất kỳ không âm, lưu trong một `bytearray`. Từng phần tử là số nguyên **không dấu** từ 0 đến `2^width−1`.

Để tránh phụ thuộc cách máy tính lưu số nguyên nhiều byte, ta quy định **little-endian theo byte** cho khối tạm khi đọc và ghi. Trong một byte, bit ở vị trí thấp có giá trị `2^0`.

```python
class PackedUnsigned:
    def __init__(self, length: int, width: int):
        if (
            not isinstance(length, int)
            or isinstance(length, bool)
            or not isinstance(width, int)
            or isinstance(width, bool)
        ):
            raise TypeError("length và width phải là số nguyên")
        if length < 0 or width < 0:
            raise ValueError("length và width phải không âm")

        self.length = length
        self.width = width
        self.payload = bytearray((length * width + 7) // 8)
        self.mask = (1 << width) - 1

    def __len__(self) -> int:
        return self.length

    def _check_index(self, i: int) -> None:
        if not isinstance(i, int) or isinstance(i, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= i < self.length:
            raise IndexError("Chỉ số ngoài miền")

    def get(self, i: int) -> int:
        self._check_index(i)

        # Miền chỉ có 1 giá trị (0), không cần bit payload.
        if self.width == 0:
            return 0

        bit_offset = i * self.width
        byte_index = bit_offset // 8
        shift = bit_offset % 8

        # Số byte chạm tới trường hiện tại.
        span = (shift + self.width + 7) // 8
        chunk = int.from_bytes(
            self.payload[byte_index:byte_index + span],
            "little",
        )
        return (chunk >> shift) & self.mask

    def set(self, i: int, value: int) -> None:
        self._check_index(i)

        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("Giá trị phải là số nguyên")
        if not 0 <= value <= self.mask:
            raise ValueError("Giá trị vượt độ rộng đã khai báo")

        if self.width == 0:
            return   # Giá trị hợp lệ duy nhất là 0.

        bit_offset = i * self.width
        byte_index = bit_offset // 8
        shift = bit_offset % 8
        span = (shift + self.width + 7) // 8

        chunk = int.from_bytes(
            self.payload[byte_index:byte_index + span],
            "little",
        )

        # Xóa đúng các bit của trường này, giữ bit lân cận.
        field_mask = self.mask << shift
        chunk = (chunk & ~field_mask) | (value << shift)

        self.payload[byte_index:byte_index + span] = (
            chunk.to_bytes(span, "little")
        )


values = [5, 2, 7, 0, 1, 6]
packed = PackedUnsigned(len(values), width=3)

for i, value in enumerate(values):
    packed.set(i, value)

assert [packed.get(i) for i in range(len(packed))] == values
assert len(packed.payload) == 3     # 6 * 3 = 18 bit.
assert len(packed.payload) * 8 == 24

# Ghi đè một trường không làm thay đổi các trường khác.
packed.set(2, 3)
assert [packed.get(i) for i in range(6)] == [
    5, 2, 3, 0, 1, 6
]

# Một trường không chứa bit vẫn mã hóa được miền {0}.
zero_width = PackedUnsigned(length=10, width=0)
assert len(zero_width.payload) == 0
zero_width.set(4, 0)
assert zero_width.get(4) == 0

# Phải báo lỗi với giá trị vượt miền 3 bit.
try:
    packed.set(0, 8)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối số 8 trong 3 bit")
```

### Phân tích

- Vùng `bytearray` có chính xác `⌈n·w/8⌉` byte dữ liệu.
- `get`/`set` đọc hoặc ghi tối đa `⌈(w+7)/8⌉` byte kèm dịch bit.
- Nếu w là một **hằng số nhỏ** phù hợp từ máy, thao tác có thể xem là `O(1)` trong mô hình RAM.
- Với w rất lớn, số byte đọc/ghi và các phép toán số nguyên lớn phụ thuộc w; không được mặc định `O(1)` độc lập với độ rộng.
- `bytearray` bản thân vẫn có header đối tượng Python; `len(payload)` chỉ báo **độ dài vùng dữ liệu**, không báo tổng dung lượng của toàn đối tượng `PackedUnsigned`.

Mã ưu tiên **đúng đắn và rõ bit offset**, chưa tối ưu tốc độ. Nó không dùng phép đọc ngoài biên; các byte không thuộc trường được giữ nguyên nhờ `field_mask`.

## 12. C++17: bit vector bằng từ 64 bit

Một biểu diễn khác là đóng các cờ vào `std::vector<std::uint64_t>`. Mỗi từ chứa 64 bit; truy cập một cờ chỉ cần tính chỉ số từ, dịch bit và dùng mask.

```cpp
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

class BitVector {
public:
    explicit BitVector(std::size_t n)
        : n_(n),
          words_(n / 64 + (n % 64 != 0), std::uint64_t{0}) {}

    std::size_t size() const {
        return n_;
    }

    std::size_t payload_bytes() const {
        return words_.size() * sizeof(std::uint64_t);
    }

    bool test(std::size_t i) const {
        check(i);
        const std::size_t word = i / 64;
        const unsigned offset = static_cast<unsigned>(i % 64);
        return ((words_[word] >> offset) & 1ULL) != 0;
    }

    void set(std::size_t i, bool value) {
        check(i);
        const std::size_t word = i / 64;
        const unsigned offset = static_cast<unsigned>(i % 64);
        const std::uint64_t mask = std::uint64_t{1} << offset;

        if (value) {
            words_[word] |= mask;
        } else {
            words_[word] &= ~mask;
        }
    }

private:
    void check(std::size_t i) const {
        if (i >= n_) {
            throw std::out_of_range("Bit index out of range");
        }
    }

    std::size_t n_;
    std::vector<std::uint64_t> words_;
};

int main() {
    BitVector flags(130);
    flags.set(0, true);
    flags.set(63, true);
    flags.set(64, true);
    flags.set(129, true);

    assert(flags.test(0));
    assert(flags.test(63));
    assert(flags.test(64));
    assert(flags.test(129));
    assert(!flags.test(128));

    flags.set(64, false);
    assert(!flags.test(64));

    std::cout << "logical bits = " << flags.size() << '\n';
    std::cout << "allocated word bytes = "
              << flags.payload_bytes() << '\n';
    // Với std::uint64_t 8 byte:
    // 130 bit logic; 3 từ; 24 byte vùng word.
}
```

### Tại sao không dịch 1 thêm 64 vị trí?

Ở C++, dịch một giá trị 64 bit với số vị trí **bằng hoặc lớn hơn 64** là không hợp lệ. Ví dụ phải dùng:

```cpp
const unsigned offset = static_cast<unsigned>(i % 64);
const std::uint64_t mask = std::uint64_t{1} << offset;
```

vì `offset` luôn nằm trong `0..63`. Việc dùng **kiểu không dấu** cũng tránh các vấn đề phép dịch bit dấu trong nhiều trường hợp.

### `std::vector<bool>` có phải thay thế trực tiếp?

Trong C++, `std::vector<bool>` là một chuyên biệt có thể đóng gói các giá trị Boolean. Nhưng:

- Truy cập phần tử thường qua **proxy reference**, không giống một `bool&` thông thường.
- Cách lưu, capacity và overhead là chi tiết của triển khai.
- Không nên mặc định số byte đúng bằng `⌈n/8⌉` trên mọi thư viện.
- Một `std::bitset<N>` có độ dài xác định tại thời điểm biên dịch, khác với vector động.

Vì vậy khi cần đo chính xác định dạng hoặc giao tiếp qua file/network, hãy định nghĩa **layout bit** rõ ràng thay vì giả định container chuẩn có cùng bố cục ở mọi môi trường.

## 13. Tập con: bitset và mã tổ hợp

Cho miền `U={0,1,\ldots,n-1}`. Một tập con S của U có thể được biểu diễn bằng **bitset n bit**:

```text
bit i = 1  nếu i thuộc S
bit i = 0  nếu i không thuộc S
```

Nếu mọi tập con đều hợp lệ, số trạng thái là:

\[
N=2^n,
\]

nên **n bit là chặn dưới đúng**.

### Khi biết tập luôn có đúng k phần tử

Nếu chỉ xét các tập con có chính xác k phần tử:

\[
N=\binom nk.
\]

Chặn dưới của mã cố định là:

\[
\boxed{
b_{\min}
=\left\lceil\log_2\binom nk\right\rceil.
}
\]

Ví dụ n=16 và k=3:

\[
\binom{16}{3}=560.
\]

Vì `2^9=512<560≤1024=2^{10}`, nên **10 bit đủ** về mặt thông tin. Trong khi:

- Bitset chung cần **16 bit**.
- Lưu ba chỉ số riêng trong miền `0..15` cần `3·4=12 bit`.
- Mã hóa **thứ hạng của tổ hợp** có thể chỉ cần **10 bit**.

Đây là ví dụ cho thấy biết thêm **ràng buộc “đúng k phần tử”** giúp giảm số trạng thái hợp lệ, từ đó giảm chặn dưới thông tin.

### Không phải biểu diễn nào cũng có cùng thời gian thao tác

Bitset 16 bit kiểm tra phần tử i có thuộc tập hay không bằng một phép mask. Mã xếp hạng tổ hợp 10 bit cần **giải mã hoặc tính toán thêm** để truy cập một phần tử cụ thể.

Khi k thay đổi sau mỗi lần thêm/xóa phần tử, còn phải cập nhật cách mã hóa và có thể cả độ rộng cần thiết. Một chặn dưới đẹp không tự tạo ra cấu trúc dữ liệu cập nhật nhanh.

## 14. Mã hóa tổ hợp bằng thứ hạng: ví dụ nhỏ

Với một tập gồm k chỉ số đã sắp tăng:

\[
0\le s_1<s_2<\cdots<s_k<n,
\]

một cách đánh số các tập con k phần tử là **combinatorial number system** (thứ tự colex):

\[
\operatorname{rank}(S)
=
\sum_{j=1}^{k}\binom{s_j}{j}.
\]

Giá trị rank nằm trong:

\[
0\le\operatorname{rank}(S)<\binom nk.
\]

Vì thế có thể lưu rank bằng đúng `⌈log₂C(n,k)⌉` bit, nếu n và k đã được biết.

### Ví dụ

Cho `n=8`, `k=3` và `S={1,4,6}`:

\[
\operatorname{rank}(S)
=
\binom11+\binom42+\binom63
=1+6+20=27.
\]

Có:

\[
\binom83=56
\]

tập ba phần tử, nên rank từ 0 tới 55 cần **6 bit**. Cách bitset cần 8 bit, còn ba chỉ số tách biệt cần 9 bit.

```python
from math import comb


def rank_fixed_size_subset(n: int, members: list[int]) -> int:
    if n < 0 or any(
        x < 0 or x >= n for x in members
    ):
        raise ValueError("Thành viên ngoài miền")

    if members != sorted(set(members)):
        raise ValueError("Phải tăng nghiêm ngặt và không trùng")

    return sum(
        comb(x, j)
        for j, x in enumerate(members, start=1)
    )


S = [1, 4, 6]
rank = rank_fixed_size_subset(8, S)
assert rank == 27
assert 0 <= rank < comb(8, len(S))

bits = minimum_fixed_bits(comb(8, len(S)))
assert bits == 6
```

Giá phải trả là thuật toán **xếp hạng/giải xếp hạng** tổ hợp. Nếu cần kiểm tra thành viên hay gộp các tập rất thường xuyên, bitset lớn hơn một chút có thể tiện và nhanh hơn.

## 15. Hoán vị và các trạng thái có ràng buộc

Giả sử cần lưu một **hoán vị của n phần tử phân biệt**. Nếu mọi hoán vị đều hợp lệ, số trạng thái không phải `n^n`, vì các giá trị không được lặp. Nó là:

\[
N=n!.
\]

Chặn dưới của một mã cố định:

\[
\boxed{
b_{\min}=\lceil\log_2(n!)\rceil.
}
\]

Ví dụ với n=4:

\[
4!=24.
\]

Cần:

\[
\lceil\log_2 24\rceil=5\text{ bit}.
\]

Trong khi lưu bốn chỉ số riêng, mỗi chỉ số thuộc miền `0..3`, cần `4·2=8 bit`, dù phần lớn trong `4^4=256` dãy số đó **không phải hoán vị hợp lệ**.

### Tại sao liên quan đến cấu trúc dữ liệu?

Nếu ràng buộc bài toán loại bỏ nhiều trạng thái không hợp lệ, mã hóa thông minh có thể chỉ lưu **số thứ tự trong không gian trạng thái hợp lệ**.

Tuy nhiên:

- Xếp hạng và giải hoán vị thường đòi tính toán bổ sung.
- Việc thay đổi một vị trí có thể ảnh hưởng mã của toàn hoán vị.
- Các phép toán phần mềm có thể cần cấu trúc chỉ mục hoặc bộ nhớ tạm.

Chặn dưới theo n! giúp định lượng cơ hội nén, nhưng không đảm bảo truy cập `O(1)` hay cập nhật `O(1)`.

## 16. Đồ thị: số trạng thái quyết định chặn dưới

Một ví dụ quan trọng khác là **đồ thị vô hướng đơn**, có n đỉnh đã gắn nhãn, không khuyên và không cạnh song song.

Có thể có một cạnh giữa mỗi cặp đỉnh phân biệt. Số cặp là:

\[
M=\binom n2=\frac{n(n-1)}2.
\]

Mỗi cặp **có cạnh hoặc không có cạnh** độc lập, nên có:

\[
N=2^M
\]

đồ thị khác nhau. Chặn dưới cố định để biểu diễn mọi đồ thị thuộc lớp này là:

\[
\boxed{
b_{\min}=M=\frac{n(n-1)}2\text{ bit}.
}
\]

### Ma trận kề và nửa tam giác

Ma trận kề n×n dùng `n^2` ô Boolean. Với đồ thị vô hướng đơn:

- Đường chéo luôn 0 vì không có khuyên.
- Ma trận đối xứng: `A[u][v]=A[v][u]`.
- Chỉ cần lưu **nửa tam giác trên hoặc dưới, không tính đường chéo**.

Số bit cần cho nửa tam giác đúng bằng:

\[
\frac{n(n-1)}2.
\]

Như vậy, **nửa ma trận kề bit-packed chạm chặn thông tin** cho lớp đồ thị này, khi n được biết và không có yêu cầu phụ.

### Ví dụ n=5

Có:

\[
M=5\cdot4/2=10
\]

cặp đỉnh, nên có `2^{10}=1024` đồ thị đơn vô hướng gắn nhãn khác nhau. Mã 10 bit có thể cho biết chính xác cạnh nào hiện diện.

### Nếu đồ thị thưa

Nếu biết đồ thị có **đúng m cạnh**, số trạng thái chỉ còn:

\[
N=\binom{M}{m},
\]

và chặn dưới là `⌈log₂C(M,m)⌉` bit. Với m rất nhỏ so với M, thấp hơn đáng kể M bit.

Đổi lại, biểu diễn danh sách cạnh hay dạng nén có thể thuận lợi hơn cho thao tác duyệt láng giềng; không có một phương án luôn tốt nhất cho mọi cấu trúc và workload.

## 17. Dữ liệu có xác suất: entropy khác chặn worst-case

Đến đây ta chỉ đếm **các trạng thái hợp lệ**, không quan tâm trạng thái nào thường gặp. Nếu các giá trị không xuất hiện đồng đều, có thể tiết kiệm số bit **trung bình** nhờ mã hóa biến độ dài.

Với biến ngẫu nhiên X nhận các giá trị có xác suất `p_1,\ldots,p_q`, entropy Shannon là:

\[
\boxed{
H(X)
=-\sum_{i:p_i>0}p_i\log_2p_i
}
\]

đơn vị **bit trên một ký hiệu**.

Entropy thỏa:

\[
0\le H(X)\le\log_2q.
\]

Dấu bằng phía trên xuất hiện với phân phối đều trên q ký hiệu. Entropy càng thấp khi một số giá trị xuất hiện thường xuyên hơn.

### Ví dụ bốn ký hiệu nhưng không đồng đều

Cho:

| Ký hiệu | Xác suất | Một mã prefix-free |
|---|---:|---|
| A | 1/2 | `0` |
| B | 1/4 | `10` |
| C | 1/8 | `110` |
| D | 1/8 | `111` |

Mã có độ dài lần lượt 1, 2, 3, 3 bit. Độ dài trung bình:

\[
\begin{aligned}
L
&=\frac12\cdot1
+\frac14\cdot2
+\frac18\cdot3
+\frac18\cdot3\\
&=1{,}75\text{ bit/ký hiệu}.
\end{aligned}
\]

Entropy của phân phối này cũng là:

\[
H(X)=1{,}75.
\]

Nếu dùng mã cố định cho một trong bốn ký hiệu, mỗi ký hiệu phải có **2 bit**. Mã biến độ dài nêu trên tiết kiệm trung bình, nhưng ký hiệu C và D **mất 3 bit**, lớn hơn mã cố định.

### Điều gì không được suy ra từ entropy?

- `H(X)=1{,}75` **không** có nghĩa mọi ký hiệu đều lưu trong 1,75 bit.
- Không có “1,75 bit” cho **một ký hiệu đơn lẻ** trong mã nhị phân độ dài nguyên thông thường; đó là **giá trị kỳ vọng** trên nhiều lần xuất hiện.
- Muốn giải mã một chuỗi phải biết **ranh giới mã**, bảng mã/phân phối và đôi khi có header hoặc metadata bổ sung.
- Với dữ liệu có tương quan theo thời gian, **entropy trên mỗi phần tử độc lập** không nhất thiết mô tả tốt cả nguồn; có thể xét entropy có điều kiện và entropy rate.

**Kết luận:** `⌈log₂N⌉` là chặn dưới cho **mọi trạng thái** bằng mã cố định, còn entropy là chặn thông tin **trung bình** dưới một mô hình xác suất và quy ước giải mã nhất định.

## 18. Phân biệt lossless, lossy và thông tin phụ

**Mã hóa không mất thông tin (lossless)** đòi bộ giải mã khôi phục **chính xác trạng thái ban đầu**.

Nếu ta loại bỏ một số thông tin, chẳng hạn làm tròn nhiệt độ từ ba chữ số thập phân xuống một chữ số, số trạng thái cần phân biệt giảm đi; nhưng đó là **lossy compression**. Không thể dùng chặn dưới sau khi làm tròn để tuyên bố đã lưu nguyên vẹn dữ liệu ban đầu.

### “Biết trước” là điều kiện quyết định

Giả sử một bộ mã luôn lưu **dãy đúng 100 Boolean**. Nếu bộ giải mã đã biết số lượng 100 từ giao thức, payload nén theo bit cần **100 bit**.

Nhưng nếu dãy có thể dài tùy ý và không có thông tin độ dài từ bên ngoài, bộ giải mã cần biết **dãy kết thúc ở đâu**. Có thể phải lưu:

- Chiều dài n.
- Byte kết thúc hoặc một ký hiệu canh gác.
- Quy tắc prefix-free hoặc framing ở giao thức.
- Một chỉ mục ranh giới nếu các bản ghi được ghép nhiều lần.

Không nên so sánh “100 bit dữ liệu” với một file độc lập mà quên chi phí **tự mô tả**.

### Payload và metadata

Ta có thể viết mô hình khái niệm:

\[
\text{TotalStorage}
=
\text{Payload}
+\text{Metadata}
+\text{Padding}
+\text{AllocationOverhead}.
\]

Các hạng không nhất thiết cộng tuyến tính ở mọi hệ thống vì metadata có thể được chia sẻ hoặc đóng gói chung, nhưng đây là cách kiểm kê giúp tránh bỏ sót chi phí.

## 19. Alignment và padding: vì sao tổng số bit không bằng `sizeof`?

Nhiều CPU truy cập dữ liệu hiệu quả hơn khi giá trị nằm ở địa chỉ được **căn chỉnh (alignment)** theo các bội số nhất định. Trình biên dịch có thể thêm byte đệm giữa các trường và ở cuối một cấu trúc.

Ví dụ C++:

```cpp
#include <cstdint>

struct Record {
    std::uint8_t flag;
    std::uint32_t id;
};
```

Về mặt **dữ liệu thuần**, flag cần 8 bit và id cần 32 bit, cộng thành 40 bit = **5 byte**.

Nhưng trên **nhiều ABI phổ biến**, `id` được căn chỉnh theo 4 byte, nên có thể có layout:

```text
byte 0: flag
byte 1: padding
byte 2: padding
byte 3: padding
byte 4..7: id
```

`sizeof(Record)` khi ấy bằng **8 byte**, không phải 5. Điều này **không được chuẩn C++ bảo đảm giống nhau** trên mọi compiler/ABI.

### Các yếu tố gây chênh lệch

- **Padding giữa các trường** và padding ở cuối cấu trúc.
- **Alignment** của kiểu giá trị.
- **Độ rộng con trỏ** và kiểu `size_t` phụ thuộc nền tảng.
- **Header của đối tượng** ở ngôn ngữ quản lý bộ nhớ như Python.
- **Capacity dư** của vector/list để hỗ trợ mở rộng nhanh.
- **Allocator overhead** và kích thước cấp phát được làm tròn theo lớp.
- **Metadata của container**: length, capacity, pointer, vtable, bảng băm, v.v.
- **Các đối tượng được chia sẻ**: cùng một đối tượng có thể được nhiều cấu trúc tham chiếu.

Do đó, cộng `sizeof` của các trường hay chỉ nhân `n×bitWidth` **không luôn cho dung lượng heap thực tế**.

## 20. Con trỏ và chỉ số cũng mang chi phí thông tin

Một cấu trúc liên kết thường lưu **con trỏ tới nút kế tiếp**. Trên môi trường có con trỏ 64 bit, một con trỏ có thể chiếm 8 byte; nhưng kích thước thật phải kiểm tra bằng `sizeof(void*)` hoặc API tương ứng, không suy từ tên hệ điều hành.

Nếu các nút nằm trong một mảng có n vị trí liên tục, ta có thể lưu **chỉ số** thay cho con trỏ:

\[
\text{IndexBits}
=\lceil\log_2n\rceil
\]

để biểu diễn một trong n vị trí khi `n≥1`.

Tuy nhiên, nếu cần thêm giá trị **“không có nút tiếp theo”**, số trạng thái là n+1:

\[
\boxed{
\text{IndexOrNullBits}
=\lceil\log_2(n+1)\rceil.
}
\]

### Ví dụ

Một mảng có đúng 1.000 nút:

- Chỉ số `0..999` cần **10 bit**.
- Thêm sentinel “null” cho mỗi liên kết: 1.001 trạng thái, vẫn cần **10 bit**.
- Nhưng nếu n=1.024, riêng chỉ số cần 10 bit, còn thêm null tạo 1.025 trạng thái, cần **11 bit**.

Chi phí bit có thể thay đổi đột ngột khi vượt một ngưỡng lũy thừa của hai.

### Các đánh đổi

Thay con trỏ bằng chỉ số có thể tiết kiệm bộ nhớ và giúp dữ liệu liên tục hơn, nhưng cần:

- Quản lý vùng mảng/buffer và tái phân bổ.
- Giới hạn số nút theo độ rộng chỉ số đã chọn.
- Quy định sentinel rõ ràng.
- Chuyển chỉ số thành địa chỉ khi truy cập.
- Cân nhắc xóa/chèn nút và tính ổn định của chỉ số.

Không được tự kết luận “mảng chỉ số luôn nhanh và nhỏ hơn” mà chưa đo yêu cầu thao tác.

## 21. Địa chỉ bộ nhớ không phải giới hạn thông tin của payload

Một thông tin dễ gây nhầm lẫn:

> “Máy 64 bit nên mỗi giá trị cần 64 bit”.

Sai. Độ rộng từ máy hoặc con trỏ **không** nói một Boolean hay một giá trị trong miền `0..999` mang 64 bit thông tin.

Ta cần phân biệt:

- **Độ rộng địa chỉ:** cách biểu diễn vị trí bộ nhớ.
- **Độ rộng từ máy:** số bit CPU thường xử lý trong một thao tác.
- **Độ rộng trường dữ liệu:** số bit thực sự cấp cho một giá trị.
- **Số bit thông tin tối thiểu:** số trạng thái hợp lệ cần phân biệt.

Một số nguyên trong `0..999` có đúng 1.000 khả năng, nên cần 10 bit theo mã cố định. Dù chương trình lưu nó trong một `uint32_t` 32 bit hay `uint64_t` 64 bit, **nội dung khả dĩ của nó vẫn chỉ cần 10 bit** nếu miền được bảo đảm.

### Tại sao vẫn dùng `uint32_t`?

Vì:

- Dễ đọc/ghi trực tiếp.
- Dễ căn chỉnh và truy cập ngẫu nhiên.
- Có thể hỗ trợ phép toán nhanh trên CPU.
- Không phải thao tác dịch/mask để giải từng trường.
- Cho phép dữ liệu mở rộng miền giá trị mà không đổi layout.

Việc bỏ trống một số bit có thể là một quyết định kỹ thuật hợp lý.

## 22. Đánh đổi giữa tiết kiệm bit và hiệu năng thao tác

Không có “định dạng nhỏ nhất” tối ưu cho mọi workload.

| Biểu diễn | Dung lượng điển hình | Truy cập phần tử | Cập nhật | Điểm cần chú ý |
|---|---|---|---|---|
| Mảng số 32 bit | 32n bit payload | Thuận tiện `O(1)` | Thuận tiện `O(1)` | Có thể lãng phí khi miền nhỏ |
| Mảng w bit đóng gói | `⌈nw/8⌉` byte | Dịch/mask; thường `O(1)` với w cố định | Có thể read-modify-write | Trường có thể cắt qua byte |
| Bitset n Boolean | n bit logic | Truy cập bit nhanh | Bitwise update | Làm tròn theo byte/từ |
| Mã toàn khối | Gần `⌈log₂N⌉` bit | Có thể cần giải mã một phần hoặc toàn khối | Có thể rất đắt | Thích hợp dữ liệu bất biến |
| Mã biến độ dài | Gần entropy trung bình trong mô hình phù hợp | Cần tìm ranh giới mã | Có thể dịch vị trí phần sau | Header, bảng mã, chỉ mục |
| Danh sách chỉ số phần tử bật | Phụ thuộc số phần tử bật | Tra cứu phụ thuộc cấu trúc | Thêm/xóa có thể linh hoạt | Tốt khi miền rất thưa |
| Ma trận kề bit-packed | `Θ(n²)` bit | Kiểm tra cạnh nhanh | Cập nhật cạnh nhanh | Tốn bộ nhớ cho đồ thị thưa |
| Danh sách kề | `Θ(n+m)` đơn vị phần tử/edge record | Duyệt láng giềng tốt | Phụ thuộc container | Có overhead con trỏ/allocator |

### Ví dụ: tra cứu cờ thành viên

Với một tập các ID trong miền 0..1.000.000:

- Nếu số lượng phần tử bật lớn, bitset thường hiệu quả và cho phép phép AND/OR hàng loạt.
- Nếu chỉ có khoảng 100 phần tử bật, lưu các chỉ số trong một mảng đã sắp xếp có thể tiết kiệm hơn rất nhiều so với bitset dài một triệu bit.

Tuy nhiên, danh sách chỉ số cần thuật toán tìm kiếm hoặc hash, còn bitset cho phép kiểm tra một bit rất trực tiếp. **Mật độ dữ liệu và thao tác yêu cầu** quyết định lựa chọn.

## 23. Succinct và compact: dùng từ cho chính xác

Trong nghiên cứu cấu trúc dữ liệu, có những thuật ngữ gần nhau nhưng không hoàn toàn đồng nghĩa:

- **Compact representation:** cách biểu diễn tiết kiệm bộ nhớ so với một cách thông thường, nhưng không nhất thiết đạt chặn dưới thông tin.
- **Succinct data structure:** cấu trúc tiệm cận sát chặn thông tin của lớp đối tượng, đồng thời giữ được một số truy vấn hiệu quả.
- **Compressed data structure:** khai thác tính lặp, phân phối hoặc quy luật dữ liệu cụ thể để giảm chỗ, có thể phục vụ trực tiếp truy vấn trên dạng nén.

Một mục tiêu thường gặp của cấu trúc succinct là:

\[
\text{InformationLowerBound}+o(\text{InformationLowerBound})
\]

bit, dưới các giả định và tập thao tác cụ thể.

Ví dụ với một bit vector n bit, có thể muốn hỗ trợ:

```text
access(i): bit ở vị trí i?
rank1(i): có bao nhiêu bit 1 trước hoặc tới vị trí i?
select1(k): vị trí của bit 1 thứ k?
```

Một bitset n bit thuần đã chạm chặn dữ liệu cho **mọi dãy Boolean n bit**, nhưng để trả `rank` và `select` rất nhanh, có thể cần thêm **cấu trúc chỉ mục**. Trong các thiết kế succinct, mục tiêu là giữ overhead của chỉ mục thấp, thường sublinear theo n, trong khi đạt thời gian truy vấn mong muốn.

**Chạm chặn payload không đồng nghĩa đã có mọi phép truy vấn nhanh.** Các chỉ mục hỗ trợ cũng tiêu tốn bit và phải được đưa vào tổng bộ nhớ.

## 24. Đo thực tế: vùng dữ liệu, capacity và toàn bộ đối tượng

Giả sử bạn đã tính được chặn thông tin là 10.000 bit, tương đương 1.250 byte. Cách xác nhận một triển khai có thực sự gọn không?

Hãy đo nhiều lớp thay vì một con số mơ hồ.

### Các lớp đo

1. **Logical information:** chặn dưới `⌈log₂N⌉` hoặc entropy khi có mô hình xác suất.
2. **Payload allocated:** số byte chứa trực tiếp các bit/giá trị.
3. **Capacity:** vùng đã cấp phát nhưng chưa sử dụng.
4. **Container/object overhead:** header, độ dài, con trỏ, bảng băm, allocator.
5. **Total live memory:** tất cả các khối sống liên quan đến cấu trúc.
6. **Peak memory:** mức bộ nhớ cao nhất trong quá trình xây dựng, chuyển đổi hoặc giải mã.

### Python: `len` khác `sys.getsizeof`

```python
import sys

raw = bytearray(1250)

print(len(raw))          # 1250 byte dữ liệu.
print(sys.getsizeof(raw))  # Phụ thuộc phiên bản/triển khai.

numbers = [0] * 1000
print(sys.getsizeof(numbers))  # Kích thước nông của list.
```

**Chú ý:** `sys.getsizeof(numbers)` không cộng đệ quy kích thước của mọi đối tượng được tham chiếu trong list. Với `[0] * 1000`, các phần tử tham chiếu cùng một đối tượng số 0 trong nhiều triển khai; cộng kích thước từng tham chiếu như các đối tượng độc lập có thể đếm trùng.

Để đo cả quá trình cấp phát Python, có thể dùng `tracemalloc` với phạm vi đo được định nghĩa rõ, hoặc công cụ profiler thích hợp. Các con số thực tế phụ thuộc phiên bản, allocator và môi trường chạy.

### C++: `sizeof` và `capacity`

```cpp
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <vector>

int main() {
    std::vector<std::uint32_t> ids;
    ids.reserve(1000);

    std::cout << "vector object = "
              << sizeof(ids) << " bytes\n";

    std::cout << "allocated element slots = "
              << ids.capacity() << '\n';

    std::cout << "element-capacity bytes = "
              << ids.capacity() * sizeof(std::uint32_t)
              << '\n';
}
```

`sizeof(ids)` chỉ đo **bản thân đối tượng vector**, không cộng vùng heap chứa phần tử. `capacity()×sizeof(T)` là ước lượng payload slots của vùng phần tử, **không** bao gồm metadata/overhead allocator. Từ đó không thể suy ra chính xác tổng RAM của tiến trình.

### Quy tắc benchmark

So sánh cùng workload và môi trường, ghi:

- Số phần tử và miền giá trị thực tế.
- Tỷ lệ đọc/ghi và kiểu truy vấn.
- Dung lượng payload và bộ nhớ tổng.
- Thời gian khởi tạo, truy cập tuần tự, truy cập ngẫu nhiên, cập nhật.
- Peak memory khi nén/giải nén.
- Ngôn ngữ, phiên bản, compiler/ABI và tùy chọn build.

Đừng kết luận một cấu trúc “tốt hơn” chỉ dựa trên số byte thấp nhất mà bỏ qua thao tác quan trọng của ứng dụng.

## 25. Các bẫy thường gặp

| Nhầm lẫn | Vì sao sai? | Cách sửa |
|---|---|---|
| “Một bit chiếm một byte” | Bit là 1/8 byte trong mô hình byte 8 bit; có thể đóng gói | Phân biệt payload logic và cấp phát theo byte |
| “10 trạng thái cần 10 bit” | Chỉ cần `⌈log₂10⌉=4` bit cố định | Đếm trạng thái, không đếm bit bằng số trạng thái |
| “N trạng thái cần `bit_length(N)`” | Dư một bit ở N là lũy thừa của hai | Dùng `(N−1).bit_length()` |
| “Giới hạn thông tin bằng `sizeof`” | Padding, header, con trỏ có thể làm lớn hơn | Đo payload và toàn bộ cấp phát riêng |
| “1 KB luôn bằng 1.024 B” | KB thập phân khác KiB nhị phân | Dùng đúng kB/KiB |
| “Một mã 17 bit cấp đúng 17/8 byte” | Bộ nhớ cấp theo byte cần làm tròn lên | `⌈17/8⌉=3 B` |
| “Dãy q giá trị dùng n lần `⌈log₂q⌉` là chặn tuyệt đối” | Mã toàn khối có thể làm tròn một lần | Phân biệt per-field và whole-block |
| “Biết tập có k phần tử không giúp nén” | Chỉ có `C(n,k)` khả năng | Dùng chặn `⌈log₂C(n,k)⌉` |
| “Bitset 1 triệu bit luôn tốn đúng 125.000 B RAM” | Còn alignment, vector và allocator | Chỉ tuyên bố về payload logic/byte-packed |
| “Entropy là số bit mỗi giá trị” | Entropy là lượng tin trung bình theo phân phối | Phân biệt expected và worst-case |
| “Mã biến độ dài không cần biết biên” | Có thể không giải mã được chuỗi ghép | Chọn prefix-free/length/framing |
| “Mã càng gọn, update càng nhanh” | Giải mã/chỉnh sửa có thể phải động tới cả khối | Đo thao tác cần thiết |
| “Chỉ số n vị trí cần đúng `log₂n` bit” | Số bit là nguyên và cần làm tròn lên | `⌈log₂n⌉` |
| “Có null sentinel vẫn cần bấy nhiêu bit” | Số trạng thái tăng từ n lên n+1 | Kiểm tra ngưỡng lũy thừa của hai |
| “`vector<bool>` có layout chuẩn cố định” | Triển khai/overhead không được cố định như giao thức | Định nghĩa serialization riêng |
| “Kiểu số thực cộng luôn kết hợp chính xác” | Floating-point có sai số và thứ tự gộp ảnh hưởng kết quả | Chọn định dạng và yêu cầu độ chính xác |
| “Một biểu diễn chạm chặn payload đã tối ưu hoàn toàn” | Rank/select/updates có thể cần chỉ mục | Cộng overhead của phép toán hỗ trợ |
| “Đồ thị vô hướng phải dùng n² bit” | Nửa ma trận đối xứng đủ với đồ thị đơn | `n(n−1)/2` bit nếu n đã biết |

## 26. Quy trình thiết kế một biểu diễn gọn

Khi chọn cách lưu dữ liệu, hãy đi theo trình tự:

1. **Xác định đối tượng và trạng thái hợp lệ.** Có phải mọi dãy đều hợp lệ, hay chỉ tập con kích thước k, hoán vị, đồ thị thưa?
2. **Đếm số trạng thái N.** Dùng miền `R−L+1`, `q^n`, `C(n,k)`, `n!` hoặc công thức tương ứng.
3. **Tính chặn dưới cố định.** `b_min=⌈log₂N⌉`; dùng số nguyên chính xác khi có thể.
4. **Xác định thông tin bên ngoài.** Bộ giải mã có biết n, q, schema, thứ tự bit và phiên bản không?
5. **Đề xuất vài layout thực tế.** Ví dụ mảng 32 bit, fixed-width packed, bitset, danh sách chỉ số hoặc mã toàn khối.
6. **Tính padding/metadata/capacity.** Đừng chỉ so sánh bit payload.
7. **Liệt kê thao tác bắt buộc.** Access, update, rank/select, thêm/xóa, duyệt tuần tự, xuất dữ liệu.
8. **Ước lượng chi phí thời gian và bộ nhớ.** Mã hóa/giải mã, điểm truy cập ngẫu nhiên, xây chỉ mục, peak memory.
9. **Kiểm thử tại ranh giới.** N=1, N là lũy thừa hai, trường cắt qua byte, giá trị tối đa, độ dài 0, độ dài không chia hết cho w.
10. **Benchmark bằng workload thật.** Chọn phương án phù hợp mục tiêu tổng thể.

**Không có một chuẩn tiết kiệm bit nào cho phép bỏ qua hoàn toàn các đánh đổi thuật toán.** Giới hạn thông tin cho ta một **mốc đối chiếu**; cấu trúc dữ liệu tốt là cấu trúc đạt mức bộ nhớ phù hợp trong khi vẫn đáp ứng thao tác cần thiết.

## 27. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một byte hiện đại thường có bao nhiêu bit?

**Đáp án:** **8 bit**. Một vùng 17 bit cần ít nhất `⌈17/8⌉=3` byte nếu cấp phát theo byte.

**Câu 2.** 1 KiB bằng bao nhiêu byte? 1 kB bằng bao nhiêu byte?

**Đáp án:** **1 KiB = 1.024 B**; **1 kB = 1.000 B**.

**Câu 3.** Vì sao b bit mã cố định có tối đa `2^b` trạng thái?

**Đáp án:** Mỗi vị trí có hai khả năng độc lập, nên theo quy tắc nhân, b vị trí có `2·2·...·2=2^b` chuỗi.

**Câu 4.** Với N=1 trạng thái cố định đã biết, chặn payload lý thuyết bằng bao nhiêu bit?

**Đáp án:** **0 bit**. Không cần phân biệt các khả năng khác; một đối tượng/file thực vẫn có thể cần metadata.

**Câu 5.** Có 13 trạng thái hợp lệ. Cần bao nhiêu bit trong mã độ dài cố định?

**Đáp án:** `⌈log₂13⌉=4` bit, vì 3 bit chỉ có 8 mã còn 4 bit có 16 mã.

**Câu 6.** Miền nguyên từ -5 đến 5 **bao gồm hai đầu** có bao nhiêu trạng thái và cần bao nhiêu bit?

**Đáp án:** `5−(−5)+1=11` trạng thái, cần **4 bit** cố định.

**Câu 7.** Miền `0..255` cần bao nhiêu bit? Nếu thêm “không có dữ liệu” thì sao?

**Đáp án:** 256 trạng thái cần **8 bit**. Thêm sentinel thành 257 trạng thái, cần **9 bit**.

**Câu 8.** Tại sao `(N−1).bit_length()` chính xác hơn `N.bit_length()` để đếm bit mã hóa một trong N trạng thái?

**Đáp án:** Giá trị lớn nhất cần mã hóa là **N−1**. Với N=8, 7 cần 3 bit, còn bản thân 8 cần 4 bit.

**Câu 9.** Một dãy có 5 chữ số thập phân độc lập. Mã toàn dãy tối thiểu bao nhiêu bit? Mã cố định 4 bit/chữ số cần bao nhiêu?

**Đáp án:** Toàn dãy có `10^5` trạng thái, cần **17 bit**. Mã theo từng chữ số cần **20 bit**.

**Câu 10.** Một nghìn số nguyên trong `0..999` cần bao nhiêu bit nếu mỗi trường cố định 10 bit?

**Đáp án:** `1.000·10=10.000` bit, tức **1.250 byte** payload. Điều đó chưa tính container và metadata.

**Câu 11.** Một triệu Boolean đóng gói bit cần bao nhiêu byte payload?

**Đáp án:** `1.000.000/8=125.000` byte, khoảng **122,07 KiB**.

**Câu 12.** Dãy Boolean dài 130 được lưu trong từ 64 bit. Cần bao nhiêu từ và bao nhiêu byte vùng từ?

**Đáp án:** `⌈130/64⌉=3` từ, mỗi từ 8 byte nên **24 byte**. Phần dữ liệu logic chỉ có 130 bit.

**Câu 13.** Với n=16 và tập con có đúng k=3 phần tử, có bao nhiêu tập và cần bao nhiêu bit mã cố định tối thiểu?

**Đáp án:** `C(16,3)=560` tập, cần **10 bit**. Bitset tổng quát cần 16 bit.

**Câu 14.** Với n=8, k=3 và tập `{1,4,6}`, rank tổ hợp theo công thức của bài bằng bao nhiêu?

**Đáp án:** `C(1,1)+C(4,2)+C(6,3)=1+6+20=27`.

**Câu 15.** Có bao nhiêu hoán vị của 4 phần tử và cần bao nhiêu bit mã cố định?

**Đáp án:** `4!=24` hoán vị; cần **5 bit**.

**Câu 16.** Đồ thị vô hướng đơn gắn nhãn n=5 đỉnh có bao nhiêu cặp cạnh có thể xuất hiện và cần bao nhiêu bit để mã hóa mọi đồ thị?

**Đáp án:** `5·4/2=10` cặp, nên có `2^{10}` đồ thị và cần **10 bit** trong mã cố định.

**Câu 17.** Entropy 1,75 bit/ký hiệu có nghĩa mọi ký hiệu được lưu trong đúng 1,75 bit không?

**Đáp án:** **Không.** Đó là số bit **trung bình kỳ vọng** của nguồn dưới phân phối xác suất và mô hình mã tương ứng; từng mã nhị phân thông thường có độ dài nguyên.

**Câu 18.** Với mã `A=0, B=10, C=110, D=111` và xác suất `1/2,1/4,1/8,1/8`, độ dài trung bình là bao nhiêu?

**Đáp án:** `1/2·1+1/4·2+1/8·3+1/8·3=1,75` bit/ký hiệu.

**Câu 19.** Vì sao không thể dùng entropy thấp của dữ liệu đã làm tròn để tuyên bố nén lossless dữ liệu gốc?

**Đáp án:** Làm tròn đã **bỏ thông tin**, giảm tập trạng thái cần phân biệt. Nếu không khôi phục đúng giá trị ban đầu thì không phải lossless.

**Câu 20.** Một cấu trúc có một trường `uint8_t` và một trường `uint32_t`; tại sao `sizeof` có thể là 8 byte thay vì 5?

**Đáp án:** Compiler/ABI có thể thêm **padding để căn chỉnh** trường 32 bit. Kích thước cụ thể phụ thuộc môi trường.

**Câu 21.** Mảng có đúng 1.024 phần tử. Chỉ số cần bao nhiêu bit? Nếu phải có thêm sentinel null?

**Đáp án:** 1.024 chỉ số cần **10 bit**. Thêm null thành 1.025 trạng thái, cần **11 bit**.

**Câu 22.** Mã hóa trong bytearray có thể tiết kiệm số bit nhưng cần đọc hai byte cho một phần tử không?

**Đáp án:** **Có.** Trường có thể bắt đầu gần cuối một byte và kéo dài qua byte kế tiếp. Phải tính bit offset và số byte chạm tới.

**Câu 23.** Chặn `⌈log₂N⌉` bit có bảo đảm một cấu trúc hỗ trợ truy cập ngẫu nhiên `O(1)` và cập nhật `O(1)` không?

**Đáp án:** **Không.** Đây là chặn **khả năng biểu diễn** của mã cố định; thao tác hiệu quả có thể yêu cầu thêm chỉ mục hoặc bit dư.

**Câu 24.** `sys.getsizeof(list)` trong Python có đếm đệ quy mọi đối tượng được list tham chiếu không?

**Đáp án:** **Không.** Nó đo kích thước nông của list, không tự cộng mọi đối tượng được trỏ tới; còn có thể có đối tượng chia sẻ.

**Câu 25.** Khi đánh giá hai biểu diễn, vì sao phải đo thêm peak memory thay vì chỉ dung lượng sau khi xây?

**Đáp án:** Quá trình nén, sắp xếp, tái cấp phát hoặc xây chỉ mục có thể cần bộ nhớ tạm lớn hơn dữ liệu cuối. Peak memory có thể quyết định liệu chương trình có chạy được hay không.

**Câu 26.** Khi nào danh sách phần tử bật có thể tiết kiệm hơn bitset?

**Đáp án:** Khi **miền rất lớn nhưng số phần tử được chọn rất ít**. Cần đổi lại chi phí tra cứu/chèn/xóa khác với kiểm tra bit trực tiếp.

**Câu 27.** Một biểu diễn chỉ tốn n bit để lưu mọi Boolean có tự hỗ trợ `rank/select` `O(1)` mà không thêm gì không?

**Đáp án:** **Không tự động.** Các chỉ mục hỗ trợ rank/select nhanh có thể tiêu tốn bit bổ sung; thiết kế succinct tìm cách giới hạn overhead ấy.

**Câu 28.** Quy tắc tổng quát đầu tiên trước khi tối ưu bộ nhớ là gì?

**Đáp án:** **Xác định tập trạng thái hợp lệ và thông tin đã biết trước**, rồi đếm N. Sau đó mới tính chặn `⌈log₂N⌉` và đánh giá thời gian/bộ nhớ thực tế.

## Ghi nhớ

- **Một mã nhị phân cố định b bit phân biệt tối đa `2^b` trạng thái**. Với N trạng thái hợp lệ, giới hạn thông tin là **`⌈log₂N⌉` bit**; tính chính xác bằng `(N−1).bit_length()` khi N là số nguyên dương.
- **Bit và byte không giống nhau**: 1 byte thường có 8 bit. Payload P bit cần `⌈P/8⌉` byte nếu cấp theo byte; từ máy và alignment có thể làm dung lượng cấp phát lớn hơn nữa.
- **Ràng buộc làm giảm số trạng thái**: dãy q ký hiệu có `q^n` khả năng; tập con đúng k phần tử có `C(n,k)` khả năng; hoán vị n phần tử có `n!` khả năng; đồ thị vô hướng đơn n đỉnh có `2^{n(n−1)/2}` khả năng.
- **Đóng gói trường độc lập** có thể dùng nhiều bit hơn mã hóa cả khối nhưng thường dễ truy cập/cập nhật hơn. Bitset tốt cho nhiều cờ; mã tổ hợp hoặc mã biến độ dài thích hợp khi có cấu trúc/ràng buộc đặc biệt.
- **Entropy** mô tả chặn thông tin **trung bình** theo mô hình xác suất, không thay thế chặn worst-case của mã cố định. Mã lossless phải khôi phục chính xác dữ liệu, kể cả phần metadata cần để giải mã.
- **Bộ nhớ thực tế** còn bao gồm padding, alignment, con trỏ, header, capacity, allocator và chỉ mục. Phải đo payload, tổng cấp phát, peak memory và thời gian thao tác trước khi chọn cách biểu diễn.
- **Đạt chặn thông tin không có nghĩa tối ưu thuật toán**. Một cấu trúc dữ liệu tốt cân đối giữa dung lượng và các thao tác thật sự quan trọng: truy cập, cập nhật, duyệt, truy vấn và khả năng mở rộng.
