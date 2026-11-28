# Đóng gói trường dữ liệu và đánh đổi chi phí giải mã

Một thiết bị ghi một bản ghi ngắn gồm **mã cảm biến**, **chế độ hoạt động**, **cờ cảnh báo** và **điểm chất lượng**. Nếu khai báo từng trường bằng kiểu nguyên và Boolean thông dụng, chương trình có thể dùng nhiều byte cho các giá trị chỉ có một số ít trạng thái hợp lệ. Ta có thể đặt các trường sát nhau ở cấp **bit** để giảm dung lượng. Nhưng khi ấy, để lấy một trường, chương trình phải biết chính xác **vị trí bit**, **độ rộng**, **thứ tự bit**, **cách xử lý dấu** và **quy tắc kiểm tra mã không hợp lệ**.

**Đóng gói trường dữ liệu (bit-field packing)** là cách biểu diễn nhiều giá trị có miền hẹp trong một hoặc vài từ/byte bằng phép dịch, mask và tổ chức bố cục bit tường minh. Nó đặc biệt hữu ích với bản ghi số lượng lớn, giao thức nhị phân, cờ trạng thái, dữ liệu cảm biến và các chỉ mục gọn. Đổi lại, các thao tác đọc/ghi có thể phải **trích bit**, **ghép nhiều byte**, **giải mã miền giá trị**, **đọc–sửa–ghi** và đôi khi cần thêm chỉ mục hoặc metadata.

Bài thuộc chương **Biểu diễn gọn** trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là học cách xác lập bất biến của một bố cục bit, tính đúng chi phí bộ nhớ, cài đặt thao tác an toàn bằng Python/C++17, rồi lựa chọn cấu trúc dữ liệu dựa trên **cả bộ nhớ lẫn thời gian thao tác**, thay vì chỉ nhìn vào dung lượng payload.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Từ miền giá trị, tính số bit tối thiểu của từng **trường có độ rộng cố định**.
2. Xây dựng bảng bố cục trường gồm **offset, width, mask và thứ tự byte**.
3. Mã hóa, giải mã và sửa trường bằng phép **dịch bit, AND, OR và NOT**.
4. Phân biệt **bit offset**, **byte offset** và **bit padding**.
5. Tính kích thước hai kiểu lưu: **mỗi bản ghi căn theo byte** và **luồng bản ghi ghép sát bit**.
6. Giải thích tại sao mã hóa gọn có thể làm tăng chi phí truy cập, cập nhật, căn chỉnh và xử lý song song.
7. Thực hiện mã hóa bản ghi trong Python, C++17, và mảng bản ghi đóng gói xuyên qua ranh giới byte trong Python.
8. Thiết kế quy tắc cho **giá trị có dấu, enum, cờ hợp lệ, sentinel và mã dự phòng**.
9. Nhận diện rủi ro của **C/C++ bit-field**, layout phụ thuộc ABI và việc cast bộ nhớ thô sang struct.
10. Xây bộ kiểm thử round-trip, ranh giới, mã lỗi và benchmark tổng bộ nhớ/thời gian.

Các ví dụ giả định byte chứa 8 bit và mô tả **layout nhị phân độc lập với ABI**. Trong mã nguồn, `bit 0` luôn là bit ít quan trọng nhất của một giá trị không dấu.

## 2. Một trường dữ liệu thực sự cần bao nhiêu bit?

Giả sử trường `x` chỉ có N trạng thái hợp lệ phân biệt. Với mã **độ dài cố định**, cần ít nhất:

\[
b=\lceil\log_2N\rceil
\]

bit để mã hóa tất cả trạng thái, với `N\ge1`.

Ví dụ:

| Trường | Miền giá trị | Số trạng thái N | Bit cần |
|---|---|---:|---:|
| Cờ bật/tắt | `false,true` | 2 | 1 |
| Chế độ | `0..5` | 6 | 3 |
| Điểm | `0..15` | 16 | 4 |
| ID cảm biến | `0..1023` | 1.024 | 10 |
| Nhiệt độ nguyên | `−40..87` | 128 | 7 |
| Mức từ 0 đến 100 | `0..100` | 101 | 7 |

Với miền liên tiếp `L..R` gồm cả hai đầu, số trạng thái:

\[
N=R-L+1.
\]

Có thể lưu giá trị dịch miền `y=x-L` để y thuộc `0..N-1`, rồi giải mã bằng `x=y+L`.

### Số 0 bit có nghĩa gì?

Nếu một trường có **đúng một trạng thái** và giá trị đó đã được quy định trong schema, nó không cần bit payload: `\lceil\log_2 1\rceil=0`. Tuy nhiên schema hoặc giao thức phải cho bộ giải mã biết trạng thái cố định ấy.

### Có trạng thái bổ sung không?

Một trường `0..15` cần 4 bit. Nếu còn cần biểu diễn riêng **“không có dữ liệu”**, ta có 17 trạng thái và phải dùng **5 bit**, hoặc thêm một cờ hợp lệ, hoặc đặt trạng thái vắng mặt ở cấu trúc bên ngoài.

**Không được dùng một mã 4 bit đã có 16 giá trị hợp lệ làm sentinel thứ 17** mà không làm mất khả năng biểu diễn một giá trị gốc.

## 3. Ví dụ xuyên suốt: bản ghi cảm biến gồm bốn trường

Xét một bản ghi:

```text
sensor_id : 0..1023    10 bit
mode      : 0..5        3 bit
alarm     : false/true  1 bit
score     : 0..15       4 bit
```

Tổng chiều rộng trường là:

\[
W=10+3+1+4=18\text{ bit}.
\]

Nếu lưu **mỗi bản ghi ở ranh giới byte**, ta cần:

\[
\left\lceil\frac{18}{8}\right\rceil=3\text{ byte/bản ghi}.
\]

Ba byte có 24 bit, nên **6 bit cuối có thể là bit đệm**.

### Giới hạn thông tin của cả bản ghi

Số trạng thái hợp lệ là:

\[
N=1024\cdot6\cdot2\cdot16=196608.
\]

Vì:

\[
2^{17}=131072<196608\le262144=2^{18},
\]

nên:

\[
\lceil\log_2N\rceil=18\text{ bit}.
\]

Cách ghép các trường thành 18 bit **đạt đúng chặn dưới mã cố định cho một bản ghi**, dù trong trường `mode` ba bit có hai mã `6,7` không hợp lệ.

Đây là chặn **cho một bản ghi cố định**. Nếu mã hóa chung hàng nghìn bản ghi như một đối tượng duy nhất, có thể khai thác thêm những tổ hợp bit không dùng, nhưng giải mã sẽ phức tạp hơn.

## 4. Thiết kế bảng bố cục bit

Ta chọn quy tắc **trường đầu tiên nằm ở các bit thấp** của một số không dấu:

| Trường | Miền | Width | Offset bit | Các bit trong từ |
|---|---|---:|---:|---|
| `sensor_id` | `0..1023` | 10 | 0 | 0..9 |
| `mode` | `0..5` | 3 | 10 | 10..12 |
| `alarm` | `0..1` | 1 | 13 | 13 |
| `score` | `0..15` | 4 | 14 | 14..17 |
| **Tổng** | | **18** | | 0..17 |

Với các trường theo thứ tự `f_0,f_1,\ldots,f_{k-1}` và độ rộng `w_i`, offset trường i được xác định:

\[
o_0=0,\qquad o_i=\sum_{j=0}^{i-1}w_j.
\]

Tổng width:

\[
W=\sum_{i=0}^{k-1}w_i.
\]

### Sơ đồ bit

```text
Bit 17 .............. 14 13 12 ..... 10 9 ............... 0
    +-----------------+--+-----------+------------------+
    | score (4 bit)   |A | mode (3)  | sensor_id (10)   |
    +-----------------+--+-----------+------------------+
                         alarm (1 bit)

bit 0 là bit ít quan trọng nhất.
```

Đây là **layout tự thiết kế**, không phụ thuộc vào cách trình biên dịch sắp xếp bit-field trong `struct`.

### Bất biến layout

- Các đoạn bit của các trường **không chồng lấn**.
- Offset cùng width không vượt quá tổng số bit được cấp.
- Giá trị mỗi trường **nằm trong miền hợp lệ**.
- Các bit padding/reserved có quy tắc tường minh (ví dụ **bắt buộc bằng 0**).
- Cả encoder và decoder dùng **đúng cùng một bảng layout**.

Nếu chỉ một trong các bất biến bị vi phạm, dữ liệu có thể bị giải mã thành giá trị sai mà không hề báo lỗi chương trình.

## 5. Phép mask và dịch dùng như thế nào?

Một trường có width w và bắt đầu ở offset o có **mask chưa dịch**:

\[
m=(1\ll w)-1
\]

và **mask tại vị trí thật**:

\[
M=m\ll o.
\]

Với số nguyên không dấu `packed`, đọc giá trị trường:

\[
\boxed{
value=(packed\gg o)\ \&\ ((1\ll w)-1).
}
\]

Đặt giá trị `v` của trường vào bản ghi ban đầu bằng 0:

\[
packed\leftarrow packed\ \mathrm{OR}\ (v\ll o),
\]

trong đó ký hiệu lập trình `packed |= (v << o)` có nghĩa OR với các bit mới.

### Ví dụ trường mode

`mode` rộng 3 bit, offset 10:

```text
mask không dịch = (1 << 3) - 1 = 0b111 = 7
mask đã dịch    = 0b111 << 10
```

Nếu mode bằng 5:

```text
mode = 0b101
mode << 10 = 0b1010000000000
```

Đọc lại:

```text
mode = (packed >> 10) & 7
```

### Tại sao phải AND sau khi dịch?

Dịch phải đưa các bit của trường về đáy, nhưng **những bit của trường cao hơn vẫn có thể còn lại**. Mask xóa chúng. Với trường 3 bit:

```text
(packed >> 10) & 0b111
```

chỉ giữ ba bit đúng vị trí.

## 6. Truy vết mã hóa một bản ghi cụ thể

Lấy bản ghi:

```text
sensor_id = 513
mode      = 5
alarm     = true
score     = 9
```

Theo bảng layout:

\[
\begin{aligned}
packed
&=513\\
&\quad|(5\ll10)\\
&\quad|(1\ll13)\\
&\quad|(9\ll14).
\end{aligned}
\]

Vì các trường không chồng bit:

```text
sensor_id             = 513
mode      = 5 * 1024  = 5120
alarm     = 1 * 8192  = 8192
score     = 9 * 16384 = 147456
--------------------------------
packed                = 161281
                     = 0x27601
```

Vùng 18 bit có thể hiển thị thành **ba byte** theo little-endian:

```text
word = 0x027601

byte 0 = 0x01
byte 1 = 0x76
byte 2 = 0x02

Wire bytes: 01 76 02
```

### Giải mã lại

```text
sensor_id = (0x27601 >> 0)  & 0x3FF = 513
mode      = (0x27601 >> 10) & 0x007 = 5
alarm     = (0x27601 >> 13) & 0x001 = 1
score     = (0x27601 >> 14) & 0x00F = 9
```

Bộ giải mã phải trả chính xác bốn trường ban đầu.

### Bit dự phòng trong byte cuối

18 bit dữ liệu dùng các bit 0..17. Nếu serialize thành ba byte, bit 18..23 là **6 bit padding**. Trong ví dụ chúng bằng 0. Một định dạng canonical có thể yêu cầu những bit này **luôn bằng 0**, để tránh hai dãy byte khác nhau cùng mô tả một bản ghi.

## 7. Endianness và bit order: phải quy định hai tầng

Một định dạng bit rõ ràng cần phân biệt:

1. **Ý nghĩa của bit trong số nguyên:** bit 0 mang trọng số `2^0`.
2. **Thứ tự byte khi ghi ra file/buffer:** byte thấp trước (little-endian) hay byte cao trước (big-endian).
3. **Quy tắc đánh số bit trong từng byte:** trong bài, bit số 0 của byte là bit có trọng số `2^0`.

Với `packed=0x027601`:

| Quy tắc serialize số 24 bit | Các byte |
|---|---|
| Little-endian | `01 76 02` |
| Big-endian | `02 76 01` |

Cả hai đều có thể biểu diễn cùng một giá trị số nguyên, nhưng **bộ giải mã phải biết quy tắc nào được dùng**.

### Từ máy và định dạng dây không giống nhau

Một CPU có byte order khác không có nghĩa file của bạn phải đổi cách giải mã. Nếu serialize một cách tường minh bằng dịch và mask, ta có thể tạo cùng một chuỗi byte trên các nền tảng.

Đừng ghi thẳng vùng nhớ của một `struct` C++ rồi mặc định nó là định dạng mạng cố định. Bố cục, padding và endian có thể khác giữa compiler/ABI.

## 8. Byte-aligned records và dense bit stream

Có ít nhất hai cách bố trí nhiều bản ghi cùng schema 18 bit.

### Phương án A: căn mỗi bản ghi theo byte

Mỗi bản ghi dùng 3 byte:

```text
Record 0: [byte0 byte1 byte2]   18 bit dữ liệu + 6 bit pad
Record 1: [byte0 byte1 byte2]   18 bit dữ liệu + 6 bit pad
Record 2: [byte0 byte1 byte2]   18 bit dữ liệu + 6 bit pad
```

Với n bản ghi:

\[
B_{\mathrm{byteAligned}}=3n\text{ byte}.
\]

Ưu điểm:

- Tìm bản ghi i trực tiếp từ `byteOffset=3i`.
- Mỗi bản ghi tự bắt đầu tại byte mới.
- Dễ serialize và cập nhật tại chỗ, miễn độ rộng không đổi.
- Dễ cắt/ghép từng bản ghi.

Nhược điểm: lãng phí **6 bit mỗi bản ghi**.

### Phương án B: ghép sát 18 bit cho mọi bản ghi

```text
Record 0: bits  0..17
Record 1: bits 18..35
Record 2: bits 36..53
Record 3: bits 54..71
...
```

Chỉ có **padding ở cuối toàn bộ luồng**:

\[
B_{\mathrm{dense}}
=\left\lceil\frac{18n}{8}\right\rceil\text{ byte}.
\]

Với n=1.000:

| Cách lưu | Byte payload |
|---|---:|
| Căn theo byte, 3 byte/bản ghi | 3.000 |
| Ghép sát 18 bit/bản ghi | 2.250 |
| Nếu một `struct` thực tế chiếm 6 byte | 6.000 |

Như vậy dense bitstream tiết kiệm **750 byte** so với các bản ghi tự căn byte, tương đương 25% vùng payload của phương án đó.

**Dòng struct 6 byte chỉ là giả thiết ví dụ**, không phải kích thước được C++ bảo đảm cho mọi compiler/ABI. Hãy đo `sizeof` trên môi trường mục tiêu.

## 9. Tính offset khi một bản ghi cắt qua nhiều byte

Trong luồng dense, bản ghi i bắt đầu tại:

\[
\boxed{
\mathrm{bitOffset}(i)=iW
}
\]

với `W=18`.

Vị trí byte và bit nội bộ:

\[
\mathrm{byteIndex}(i)
=\left\lfloor\frac{iW}{8}\right\rfloor,
\qquad
\mathrm{bitInByte}(i)
=(iW)\bmod8.
\]

Ví dụ:

| Bản ghi i | Bit offset | Byte đầu | Bit trong byte |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1 | 18 | 2 | 2 |
| 2 | 36 | 4 | 4 |
| 3 | 54 | 6 | 6 |
| 4 | 72 | 9 | 0 |

Bản ghi thứ 3 (i=3) bắt đầu tại bit 6 của byte số 6; 18 bit của nó trải qua **3 byte** (byte 6, 7 và 8).

### Số byte cần đọc một bản ghi

Nếu bit đầu ở vị trí s trong byte, với độ rộng W:

\[
\boxed{
\mathrm{spanBytes}
=\left\lceil\frac{s+W}{8}\right\rceil.
}
\]

Với W=18, `s=6`:

\[
\lceil(6+18)/8\rceil=3\text{ byte}.
\]

**Kiểm tra biên:** bản ghi i=3 chiếm các bit 54..71, tức byte 6 từ bit 6 tới 7, byte 7 toàn phần và byte 8 toàn phần. Bản ghi i=1, `s=2`, cần `\lceil20/8\rceil=3` byte. Nếu `s=7` với W=18 thì sẽ cần 4 byte, nhưng với bước nhảy 18 bit, offset modulo 8 chỉ nhận `0,2,4,6`, nên **mỗi bản ghi 18 bit ở layout này chạm tối đa 3 byte**.

Đây là ví dụ vì sao nên dùng **công thức**, không đoán số byte dựa trên số bit.

## 10. Tại sao thao tác đọc phải dùng mask?

Giả sử bản ghi bắt đầu ở bit 4 của byte b. Ta đọc một cửa sổ byte thành số không dấu little-endian:

```text
window = bytes_to_integer(buffer[b : b + span])
```

Nội dung window có thể gồm:

- Bit còn lại của **bản ghi trước** nằm ở đầu byte.
- Toàn bộ bit của **bản ghi hiện tại**.
- Một phần của **bản ghi sau** nằm ở cuối byte.

Vì thế phải:

1. Dịch phải `shift = bitOffset % 8` để đưa trường hiện tại về bit thấp.
2. Mask đúng W bit để bỏ mọi bit của bản ghi sau.

Giả mã:

```text
recordWord =
    (window >> shift) & ((1 << W) - 1)
```

Nếu chỉ dịch mà không mask, các bit của bản ghi kế tiếp có thể làm thay đổi giá trị bản ghi hiện tại.

### Cập nhật khó hơn đọc

Muốn sửa bản ghi i mà không phá hàng xóm, không được ghi đè thẳng toàn bộ các byte của cửa sổ. Phải:

```text
mask = ((1 << W) - 1) << shift

newWindow =
    (oldWindow & ~mask)
    | (newRecordWord << shift)
```

Phép AND với mask đảo giữ nguyên các bit nằm ngoài bản ghi; OR chèn giá trị mới vào đúng vị trí.

## 11. Python: mã hóa một bản ghi 18 bit

Ta xây lớp bất biến `SensorRecord` cùng hai hàm mã hóa/giải mã giá trị từ.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorRecord:
    sensor_id: int
    mode: int
    alarm: bool
    score: int


RECORD_BITS = 18
RECORD_MASK = (1 << RECORD_BITS) - 1


def _valid_uint(value: int, lower: int, upper: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and lower <= value <= upper
    )


def encode_word(record: SensorRecord) -> int:
    if not isinstance(record, SensorRecord):
        raise TypeError("record phải là SensorRecord")
    if not _valid_uint(record.sensor_id, 0, 1023):
        raise ValueError("sensor_id phải thuộc 0..1023")
    if not _valid_uint(record.mode, 0, 5):
        raise ValueError("mode phải thuộc 0..5")
    if not isinstance(record.alarm, bool):
        raise TypeError("alarm phải là bool")
    if not _valid_uint(record.score, 0, 15):
        raise ValueError("score phải thuộc 0..15")

    return (
        record.sensor_id
        | (record.mode << 10)
        | (int(record.alarm) << 13)
        | (record.score << 14)
    )


def decode_word(word: int) -> SensorRecord:
    if not _valid_uint(word, 0, RECORD_MASK):
        raise ValueError("Bản ghi không phải 18-bit unsigned")

    sensor_id = (word >> 0) & 0x3FF
    mode = (word >> 10) & 0x7
    alarm = ((word >> 13) & 1) != 0
    score = (word >> 14) & 0xF

    if mode > 5:
        raise ValueError("mode chứa mã dự phòng không hợp lệ")

    return SensorRecord(sensor_id, mode, alarm, score)


record = SensorRecord(513, 5, True, 9)
word = encode_word(record)

assert word == 0x27601
assert decode_word(word) == record
assert (word & RECORD_MASK) == word

# Một mode ngoài miền bị từ chối khi encode.
try:
    encode_word(SensorRecord(513, 7, True, 9))
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối mode 7")
```

### Vì sao kiểm tra miền trước khi dịch?

Mã hóa `mode=7` trong 3 bit vẫn có thể về mặt bit, nhưng schema chỉ cho phép `0..5`. Nếu chấp nhận 7, ta đã tạo ra một trạng thái **không hợp lệ về nghiệp vụ**. Trên các định dạng có mã dự phòng cho phiên bản tương lai, việc chấp nhận tùy tiện có thể gây hiểu nhầm dữ liệu mới là dữ liệu cũ.

### Vì sao `bool` cần kiểm tra riêng trong Python?

Trong Python, `bool` là lớp con của `int`. Nếu chỉ dùng `isinstance(x,int)`, giá trị `True` có thể vô tình được chấp nhận làm ID 1. Mã ví dụ phân biệt cờ Boolean với số nguyên nhằm giữ hợp đồng schema rõ ràng.

## 12. Python: tuần tự hóa đúng ba byte

Ta quy ước little-endian trên giá trị từ 18 bit:

```python
def encode_three_bytes(record: SensorRecord) -> bytes:
    word = encode_word(record)
    return word.to_bytes(3, byteorder="little")


def decode_three_bytes(data: bytes) -> SensorRecord:
    if not isinstance(data, bytes) or len(data) != 3:
        raise ValueError("Bản ghi phải có đúng 3 byte")

    word = int.from_bytes(data, byteorder="little")
    if word > RECORD_MASK:
        raise ValueError("Padding ở sáu bit cao phải bằng 0")

    return decode_word(word)


record = SensorRecord(513, 5, True, 9)

assert encode_three_bytes(record) == bytes.fromhex("01 76 02")
assert decode_three_bytes(bytes.fromhex("01 76 02")) == record

# Mã mode=7 nằm trong 18 bit nhưng không hợp lệ.
invalid_mode = (513 | (7 << 10) | (1 << 13) | (9 << 14))
try:
    decode_three_bytes(invalid_mode.to_bytes(3, "little"))
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối mode dự phòng")

# Bit 23 là padding và phải bằng 0.
try:
    decode_three_bytes(bytes.fromhex("01 76 82"))
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối bit padding khác 0")
```

### Vì sao mã dự phòng và padding khác nhau?

- **Mode 6,7:** các mã bit nằm trong trường hợp lệ về độ rộng, nhưng **chưa được gán ý nghĩa** trong schema phiên bản này.
- **Padding bit 18..23:** hoàn toàn không thuộc trường nào trong bản ghi 18 bit.

Bộ giải mã có thể quy định cả hai đều phải từ chối, hoặc trong một giao thức có versioning có thể cho phép một số mã dự phòng với ý nghĩa tương lai. Điều quan trọng là phải **quy định rõ**, không suy đoán.

## 13. Python: nhiều bản ghi ghép sát qua ranh giới byte

Nếu ghi 3 byte riêng cho từng bản ghi, mỗi bản ghi mang 6 bit padding. Để tiết kiệm hơn, ta lưu liên tiếp các **từ 18 bit** vào một bytearray.

Lớp sau hỗ trợ:

- `append` thêm bản ghi ở cuối.
- `get` đọc bản ghi thứ i.
- `set` ghi đè bản ghi thứ i nhưng không làm thay đổi bit của hàng xóm.
- `payload_bytes` trả số byte dữ liệu đã dùng.
- Các thao tác chấp nhận cùng schema `SensorRecord` như ở phần trước.

```python
class DenseSensorArray:
    def __init__(self):
        self.payload = bytearray()
        self.count = 0

    def __len__(self) -> int:
        return self.count

    def _check_index(self, index: int) -> None:
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < self.count
        ):
            raise IndexError("Bản ghi ngoài miền")

    def _bit_window(self, index: int) -> tuple[int, int, int]:
        bit_offset = index * RECORD_BITS
        byte_index = bit_offset // 8
        shift = bit_offset % 8
        span = (shift + RECORD_BITS + 7) // 8
        return byte_index, shift, span

    def _write_word(self, index: int, word: int) -> None:
        byte_index, shift, span = self._bit_window(index)

        old = int.from_bytes(
            self.payload[byte_index:byte_index + span],
            "little",
        )

        shifted_mask = RECORD_MASK << shift
        new = (
            (old & ~shifted_mask)
            | (word << shift)
        )

        self.payload[byte_index:byte_index + span] = (
            new.to_bytes(span, "little")
        )

    def append(self, record: SensorRecord) -> None:
        word = encode_word(record)

        # Mở rộng tới đúng số byte đủ chứa thêm 18 bit.
        new_end_bits = (self.count + 1) * RECORD_BITS
        needed = (new_end_bits + 7) // 8

        if needed > len(self.payload):
            self.payload.extend(
                bytes(needed - len(self.payload))
            )

        self._write_word(self.count, word)
        self.count += 1

    def get(self, index: int) -> SensorRecord:
        self._check_index(index)
        byte_index, shift, span = self._bit_window(index)

        raw = int.from_bytes(
            self.payload[byte_index:byte_index + span],
            "little",
        )

        word = (raw >> shift) & RECORD_MASK
        return decode_word(word)

    def set(self, index: int, record: SensorRecord) -> None:
        self._check_index(index)
        word = encode_word(record)
        self._write_word(index, word)

    def payload_bytes(self) -> int:
        return len(self.payload)


first = SensorRecord(513, 5, True, 9)
many = DenseSensorArray()

many.append(first)
assert many.payload == bytes.fromhex("01 76 02")
assert many.get(0) == first

records = [
    SensorRecord(1, 0, False, 0),
    SensorRecord(100, 2, True, 10),
    SensorRecord(1023, 5, False, 15),
    SensorRecord(9, 1, True, 3),
]

for record in records:
    many.append(record)

assert len(many) == 5
assert many.payload_bytes() == 12  # ceil(5*18/8).
assert [many.get(i) for i in range(5)] == [first] + records

previous = many.get(1)
following = many.get(3)

replacement = SensorRecord(777, 4, True, 8)
many.set(2, replacement)

assert many.get(2) == replacement
assert many.get(1) == previous
assert many.get(3) == following

empty = DenseSensorArray()
assert len(empty) == 0
assert empty.payload_bytes() == 0
```

### Giải thích tính đúng của `set`

Trong `_write_word`:

1. Đọc byte window chứa các bit của bản ghi muốn sửa.
2. Tạo mask cho đúng `RECORD_BITS` bit tại `shift`.
3. AND với mask đảo để xóa các bit thuộc bản ghi cũ.
4. OR với từ mới đã dịch đúng offset.
5. Ghi trả byte window, **giữ nguyên các bit nằm ngoài mask**.

Vì vậy nếu hai bản ghi chia sẻ một byte, `set` không làm hỏng bản ghi bên cạnh. Đây là bất biến quan trọng nhất của cấu trúc đóng gói liên tục.

### Độ phức tạp

Với `RECORD_BITS=18` cố định:

- `get` và `set` đọc/ghi cửa sổ tối đa **3 byte**, nên `O(1)` theo mô hình từ máy cố định.
- `append` phải mở rộng `bytearray` khi cần. Nó có chi phí **khấu hao phụ thuộc triển khai cấp phát**, không nên tuyên bố mọi lần append có worst-case `O(1)`.
- Với n bản ghi, vùng payload đúng `\lceil18n/8\rceil` byte.
- Lớp Python, `bytearray`, các biến `count`/`payload` và allocator vẫn dùng bộ nhớ ngoài payload.

Nếu width thay đổi theo từng bản ghi hoặc rất lớn, công thức truy cập và chi phí không còn giống như bản fixed-layout này.

## 14. C++17: layout tường minh, không phụ thuộc bit-field ABI

Một ví dụ C++ tương đương, nhưng mỗi bản ghi được serialize thành **đúng ba byte** theo little-endian.

```cpp
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <stdexcept>

struct SensorRecord {
    std::uint16_t sensor_id;
    std::uint8_t mode;
    bool alarm;
    std::uint8_t score;
};

constexpr std::uint32_t RECORD_BITS = 18;
constexpr std::uint32_t RECORD_MASK =
    (std::uint32_t{1} << RECORD_BITS) - 1;

std::uint32_t encode_word(const SensorRecord& r) {
    if (r.sensor_id > 1023 ||
        r.mode > 5 ||
        r.score > 15) {
        throw std::out_of_range("Invalid sensor fields");
    }

    return (
        std::uint32_t{r.sensor_id}
        | (std::uint32_t{r.mode} << 10)
        | (std::uint32_t{r.alarm ? 1U : 0U} << 13)
        | (std::uint32_t{r.score} << 14)
    );
}

SensorRecord decode_word(std::uint32_t word) {
    if (word > RECORD_MASK) {
        throw std::invalid_argument("Nonzero padding");
    }

    SensorRecord r{
        static_cast<std::uint16_t>((word >> 0) & 0x3FFU),
        static_cast<std::uint8_t>((word >> 10) & 0x7U),
        ((word >> 13) & 1U) != 0,
        static_cast<std::uint8_t>((word >> 14) & 0xFU),
    };

    if (r.mode > 5) {
        throw std::invalid_argument("Reserved mode code");
    }
    return r;
}

std::array<std::uint8_t, 3> encode_bytes(
    const SensorRecord& r
) {
    const std::uint32_t word = encode_word(r);

    return {
        static_cast<std::uint8_t>(word & 0xFFU),
        static_cast<std::uint8_t>((word >> 8) & 0xFFU),
        static_cast<std::uint8_t>((word >> 16) & 0xFFU),
    };
}

SensorRecord decode_bytes(
    const std::array<std::uint8_t, 3>& bytes
) {
    const std::uint32_t word =
        std::uint32_t{bytes[0]}
        | (std::uint32_t{bytes[1]} << 8)
        | (std::uint32_t{bytes[2]} << 16);

    return decode_word(word);
}

int main() {
    const SensorRecord original{513, 5, true, 9};

    const auto bytes = encode_bytes(original);
    assert(bytes[0] == 0x01U);
    assert(bytes[1] == 0x76U);
    assert(bytes[2] == 0x02U);

    const auto restored = decode_bytes(bytes);
    assert(restored.sensor_id == original.sensor_id);
    assert(restored.mode == original.mode);
    assert(restored.alarm == original.alarm);
    assert(restored.score == original.score);

    std::cout << "wire bytes: 3\n";
}
```

### Tại sao không serialize bằng `memcpy(&r, sizeof(r))`?

Cấu trúc `SensorRecord` có thể chứa:

- Byte padding giữa các trường.
- Byte padding cuối cấu trúc.
- Cách biểu diễn `bool` phụ thuộc ABI.
- Cách lưu byte của `uint16_t` phụ thuộc endianness máy.

Do vậy `sizeof(SensorRecord)` có thể **khác 3**, và `memcpy` toàn struct không đảm bảo tạo ra `01 76 02`.

Mã trên tự xác định từng bit của định dạng dây, nên cùng một `SensorRecord` hợp lệ sẽ tạo **cùng ba byte** trên các nền tảng hỗ trợ các kiểu `uint8_t`/`uint16_t`/`uint32_t` tương ứng.

## 15. Vì sao C/C++ bit-field không phải định dạng file chuẩn?

C++ cho phép khai báo bit-field:

```cpp
struct NativeBits {
    unsigned sensor_id : 10;
    unsigned mode      : 3;
    unsigned alarm     : 1;
    unsigned score     : 4;
};
```

Cách viết ngắn, nhưng **không nên mặc định** `sizeof(NativeBits)==3` hoặc trật tự bit trong bộ nhớ giống sơ đồ của bài.

Các yếu tố có thể phụ thuộc trình biên dịch, ABI hoặc quy tắc của ngôn ngữ:

- Thứ tự phân bổ bit-field trong đơn vị lưu trữ.
- Cách tràn qua ranh giới đơn vị lưu trữ.
- Padding và alignment của struct.
- Kiểu nền của bit-field.
- Khả năng lấy địa chỉ và cách tham chiếu tới bit-field.

**Bit-field tốt cho một số cấu trúc nội bộ được kiểm soát môi trường**, nhưng giao thức nhị phân bền vững nên dùng **dịch và mask tường minh**, hoặc một thư viện serialization có đặc tả layout được kiểm chứng.

### `#pragma pack` có giải quyết mọi thứ?

Không. `#pragma pack` không phải một chuẩn portable để quy định thứ tự bit. Nó còn có thể tạo truy cập **không căn chỉnh**, ảnh hưởng hiệu năng hoặc tính hợp lệ trên nền tảng khác.

Việc nén byte của struct không đồng nghĩa các trường bit đã được đặt đúng theo đặc tả dây.

## 16. Bit số 0, bit trong byte và quy ước mạng

Có thể thiết kế cùng bốn trường theo **bit cao trước** thay vì bit thấp trước. Khi ấy offset và phép shift đổi hoàn toàn. Không có quy tắc “đúng tuyệt đối” cho mọi ứng dụng; có **quy tắc đã được các bên thống nhất**.

### Bài chọn LSB-first

- Bit đầu của bản ghi nằm ở bit thấp nhất của byte đầu.
- Bit kế tiếp có trọng số tiếp theo trong cùng byte.
- Sau bit 7 chuyển sang bit 0 của byte kế tiếp.
- Bản ghi liên tục có thể bắt đầu giữa byte.

Ví dụ dense 18 bit, bản ghi 1 bắt đầu ở bit 2 của byte số 2.

### Một giao thức khác có thể chọn MSB-first

Khi dùng MSB-first, byte đầu có thể chứa bit cao của trường đầu tiên. Công thức encode/decode khác và byte đầu ra cũng khác. Vì thế mỗi wire format cần nêu rõ:

- Thứ tự **các trường**.
- Thứ tự **bit trong trường**.
- Thứ tự **byte** của vùng dữ liệu nhiều byte.
- Thứ tự **bit khi liên tục qua byte**.

Nếu thiếu một trong những thông tin đó, hai hệ thống có thể đều “dùng 18 bit” nhưng không đọc được dữ liệu của nhau.

## 17. Mã hóa số âm trong trường có độ rộng cố định

Giả sử cần lưu nhiệt độ nguyên trong miền:

\[
-40\le t\le87.
\]

Có đúng 128 giá trị, nên 7 bit đủ.

Một cách đơn giản là **mã dịch miền**:

\[
code=t+40.
\]

Khi đó:

\[
0\le code\le127.
\]

Giải mã:

\[
t=code-40.
\]

### Python

```python
def encode_temperature(t: int) -> int:
    if not isinstance(t, int) or isinstance(t, bool):
        raise TypeError("Nhiệt độ phải là số nguyên")
    if not -40 <= t <= 87:
        raise ValueError("Nhiệt độ ngoài miền")

    return t + 40


def decode_temperature(code: int) -> int:
    if not isinstance(code, int) or isinstance(code, bool):
        raise TypeError("Mã phải là số nguyên")
    if not 0 <= code <= 127:
        raise ValueError("Mã 7 bit không hợp lệ")

    return code - 40


assert encode_temperature(-40) == 0
assert encode_temperature(0) == 40
assert encode_temperature(87) == 127
assert decode_temperature(127) == 87
```

### Có thể dùng two's complement không?

Có thể, nhưng cần chọn miền tương thích. **Số nguyên 7 bit có dấu theo bù hai** biểu diễn `−64..63`, không biểu diễn được 87. Vì vậy với miền `−40..87`, mã dịch miền là lựa chọn dễ hiểu hơn.

Nếu trường thực sự có miền `−64..63`, bù hai 7 bit có thể phù hợp. Cách giải mã cần quy định đúng sign extension, tránh hiểu bit cao như cờ không hợp lệ.

### Sentinel cho giá trị vắng mặt

Miền `−40..87` đã dùng **toàn bộ 128 mã 7 bit**. Muốn thêm “không có nhiệt độ”:

- Dành 8 bit cho 129 trạng thái; hoặc
- Có một bit `valid` riêng; hoặc
- Thay đổi miền giá trị để dành một mã; hoặc
- Dùng metadata ngoài trường.

Không thể vừa giữ nguyên 128 giá trị vừa thêm trạng thái thứ 129 trong chỉ 7 bit.

## 18. Enum, reserved và versioning

Trường `mode` có 3 bit nên biểu diễn các mã `0..7`, nhưng phiên bản hiện tại chỉ định nghĩa `0..5`.

Hai mã `6` và `7` là **mã dự phòng**, không phải bất kỳ giá trị hợp lệ mới nào nếu bộ giải mã chưa hiểu chúng.

### Chiến lược xử lý

| Cách xử lý | Khi nào phù hợp | Rủi ro |
|---|---|---|
| Từ chối mọi mã chưa biết | Giao thức chặt, an toàn | Bản cũ không đọc được bản mới |
| Bỏ qua mã chưa biết kèm cảnh báo | Nếu schema định nghĩa rõ fallback | Có thể mất ý nghĩa trạng thái |
| Cho phép opaque unknown value | Khi cần chuyển tiếp dữ liệu | Ứng dụng có thể không xử lý ý nghĩa |
| Thêm trường version | Khi layout có nhiều phiên bản | Tốn metadata và logic |
| Tạo định dạng mới | Thay đổi phá tương thích | Cần migration |

Nếu schema có thể mở rộng số chế độ từ 6 lên 9, **3 bit không còn đủ** vì mã chỉ có 8 khả năng. Phải tăng width, chuyển định dạng hoặc dùng mã mở rộng đã được quy định trước.

### Dùng padding làm chỗ mở rộng?

Có thể dành trước một số bit cho phiên bản tương lai, nhưng:

- Bản đọc cũ phải có chính sách rõ đối với bit dự phòng khác 0.
- Thay đổi ý nghĩa bit cũ có thể phá tương thích.
- Bit padding trong định dạng canonical không tự trở thành trường hợp lệ ở một phiên bản mới nếu chưa có cơ chế phân biệt phiên bản.

Một định dạng nhỏ cần được thiết kế cùng **vòng đời schema**, không chỉ cho dữ liệu hôm nay.

## 19. Truy xuất một trường so với giải mã toàn bản ghi

Một lợi ích của bit packing theo **trường cố định** là có thể lấy trực tiếp một trường mà không cần dựng đối tượng đầy đủ.

Ví dụ chỉ cần biết `alarm`:

```python
def alarm_from_word(word: int) -> bool:
    return ((word >> 13) & 1) != 0
```

Đối với mảng mỗi bản ghi 3 byte, có thể:

1. Xác định byte offset `3i`.
2. Đọc đủ byte chứa bit 13.
3. Dịch/mask để lấy bit alarm.

Nếu chỉ cần cờ và không cần ba trường còn lại, không nhất thiết tạo `SensorRecord` cho mỗi bản ghi.

### Nhưng mảng đóng gói dense có thể khác

Khi bản ghi bắt đầu ở bit không chia hết cho 8, vị trí bit thực của alarm là:

\[
18i+13.
\]

Byte chứa cờ:

\[
\left\lfloor\frac{18i+13}{8}\right\rfloor.
\]

Vị trí bit trong byte:

\[
(18i+13)\bmod8.
\]

Vì alarm chỉ rộng **một bit**, truy vấn riêng cờ có thể chỉ cần đọc **một byte**, dù toàn bản ghi cần 3 byte. Dạng layout ảnh hưởng trực tiếp tới số thao tác cần dùng.

### Cân nhắc dữ liệu theo cột

Nếu phần lớn truy vấn chỉ quét `alarm` trên mọi bản ghi, có thể lưu **cả cột alarm như bitset riêng**:

```text
sensor_id[]   : 10 bit mỗi giá trị
mode[]        : 3 bit mỗi giá trị
alarm_bits[]  : 1 bit mỗi giá trị
score[]       : 4 bit mỗi giá trị
```

Tổng payload lý thuyết vẫn gần `18n` bit, nhưng việc duyệt riêng một cột có thể có tính cục bộ bộ nhớ tốt hơn. Ngược lại, truy cập mọi trường của một bản ghi theo hàng có thể phải đọc nhiều vùng.

Đây là sự khác nhau giữa **Array of Structures (AoS)** và **Structure of Arrays (SoA)** ở mức bố cục, ngoài câu chuyện bit packing.

## 20. Chi phí giải mã thực tế gồm những gì?

So với đọc trực tiếp một số nguyên đúng độ rộng, giải mã trường đóng gói thường cần thêm:

1. Tính `bitOffset` hoặc `byteOffset`.
2. Xác định số byte/từ máy cần đọc.
3. Ghép các byte thành một giá trị không dấu.
4. Dịch và mask.
5. Chuyển mã về miền giá trị thực (ví dụ cộng/trừ bias).
6. Kiểm tra mã enum, mã dự phòng và bit padding.
7. Tạo đối tượng kết quả nếu API yêu cầu.

Với width cố định nhỏ, các phép trên thường là **`O(1)`** theo mô hình RAM. Nhưng `O(1)` không có nghĩa chúng có cùng tốc độ với một phép load `uint32_t`.

### Chi phí có thể nổi trội

- **Nhiều phép dịch/AND/OR** và phép tính offset.
- **Đọc qua ranh giới byte/từ** hoặc dùng nhiều load.
- **Branch** khi kiểm tra mode, version và dữ liệu lỗi.
- **Read-modify-write** khi cập nhật một trường chia sẻ byte với các trường khác.
- **Mất vectorization** nếu trình biên dịch khó nhận diện quy luật.
- **Bộ nhớ tạm** khi giải nén thành một mảng rộng trước khi tính toán.
- **Cache pressure** có thể giảm vì payload nhỏ hơn, đôi khi bù được chi phí decode.

Không có quy tắc chung rằng bit packing luôn chậm hơn hoặc luôn nhanh hơn: kết quả phụ thuộc CPU, bộ nhớ, dữ liệu và workload.

## 21. Vì sao bộ nhớ nhỏ đôi khi lại làm chương trình nhanh hơn?

Giả sử một thuật toán đọc hàng trăm triệu bản ghi theo thứ tự. Nếu cấu trúc rộng 8 byte/bản ghi, việc tải dữ liệu từ RAM có thể là nút thắt.

Nếu chuyển sang 3 byte/bản ghi:

- Giảm số byte truyền từ RAM/cache.
- Tăng số bản ghi nằm trong cùng một cache line.
- Có thể giảm lỗi cache và TLB.
- Có thể giảm I/O khi đọc file hoặc truyền mạng.

Khi đó, dù mỗi bản ghi cần thêm vài phép dịch và mask, **tổng thời gian có thể tốt hơn** vì ít phải chờ bộ nhớ.

### Ngược lại, khi nào có thể chậm hơn?

- Dữ liệu đã vừa trong cache và CPU bị giới hạn bởi giải mã.
- Ứng dụng liên tục sửa ngẫu nhiên một trường.
- Truy cập không tuần tự khiến việc ghép bit kém hiệu quả.
- Code giải mã tạo nhiều đối tượng trung gian.
- Compiler không thể vectorize như với mảng số nguyên trực tiếp.

Vì vậy benchmark phải đo **cả thông lượng đọc và cập nhật**, thay vì chỉ nhìn vào thời gian của một hàm `get` đơn lẻ.

## 22. Cập nhật một trường: thao tác đọc–sửa–ghi

Giả sử cần đổi riêng `mode` từ 5 thành 2 trong từ 18 bit.

Mask trường:

\[
M=((1\ll3)-1)\ll10.
\]

Công thức sửa:

\[
\boxed{
newWord
=(oldWord\ \&\ \sim M)\ |\ (newMode\ll10).
}
\]

### Python

```python
def replace_mode(word: int, new_mode: int) -> int:
    if not _valid_uint(word, 0, RECORD_MASK):
        raise ValueError("word không hợp lệ")
    if not _valid_uint(new_mode, 0, 5):
        raise ValueError("new_mode ngoài miền")

    mask = 0x7 << 10
    updated = (word & ~mask) | (new_mode << 10)

    # Có thể dùng decode_word để kiểm tra cả bản ghi.
    decode_word(updated)
    return updated


word = encode_word(SensorRecord(513, 5, True, 9))
changed = replace_mode(word, 2)

assert decode_word(changed) == SensorRecord(513, 2, True, 9)
assert (word & ~(0x7 << 10)) == (changed & ~(0x7 << 10))
```

### Cập nhật khi trường chia sẻ byte

Nếu hai trường cùng nằm trên một byte, cập nhật một trường thường thực hiện:

1. Đọc byte/từ hiện tại.
2. Xóa các bit của trường.
3. Chèn giá trị mới.
4. Ghi trả byte/từ.

Trong môi trường nhiều luồng, hai thao tác đọc–sửa–ghi không đồng bộ vào hai trường khác nhau **vẫn có thể ghi đè lẫn nhau** nếu chúng chia sẻ cùng đơn vị lưu trữ.

**Không được coi “hai trường không chồng bit” là đủ để cập nhật đồng thời an toàn.** Cần khóa, thao tác nguyên tử phù hợp hoặc tách layout theo đơn vị ghi độc lập. Tính nguyên tử phụ thuộc vào kích thước, căn chỉnh và kiểu thao tác thực tế.

## 23. Kích thước sau khi chỉnh sửa và khả năng cập nhật tại chỗ

Một ưu điểm của đóng gói fixed-width là khi thay `mode` từ 0 sang 5, **độ rộng vẫn 3 bit**. Bản ghi không phải thay đổi chiều dài.

So với mã độ dài thay đổi:

```text
127 → 1 byte ULEB128
128 → 2 byte ULEB128
```

Một cập nhật varint có thể làm thay đổi offset của mọi phần tử sau nếu lưu trong một buffer nối sát.

### Nhưng fixed-width vẫn có giới hạn

Nếu schema quyết định nâng `sensor_id` từ `0..1023` lên `0..2047`, số bit ID phải tăng từ **10 lên 11**. Tổng bản ghi từ **18 lên 19 bit**. Trong dense bitstream, đổi width toàn bộ có thể đòi **mã hóa lại cả tập dữ liệu**.

Bởi vậy cần cân nhắc:

- Chọn trước dư một số bit nếu miền sẽ tăng.
- Versioning để phân biệt layout mới/cũ.
- Chia dữ liệu thành block để migration cục bộ.
- Chấp nhận định dạng rộng hơn nếu cập nhật/khả năng mở rộng quan trọng.

Dư bit có thể là **dự phòng kỹ thuật**, không nhất thiết là lãng phí vô ích.

## 24. So sánh bit packing với mã hóa biến độ dài

Hai kỹ thuật đều nhằm tiết kiệm bộ nhớ, nhưng có tính chất khác nhau.

| Tiêu chí | Fixed-width bit packing | Varint/delta |
|---|---|---|
| Độ rộng mỗi trường | Cố định theo schema | Phụ thuộc giá trị hoặc chênh lệch |
| Offset phần tử i | Tính từ `i·W` | Thường cần quét hoặc chỉ mục |
| Truy cập ngẫu nhiên | Thuận tiện hơn | Có thể cần checkpoint |
| Cập nhật cùng miền | Không đổi kích thước | Có thể làm đổi số byte |
| Mã hóa số rất nhỏ | Có thể vẫn dùng W bit | Thường dùng ít byte |
| Xử lý ranh giới | Trường có thể cắt byte/từ | Byte continuation và ranh giới mã |
| Metadata | Layout, width, count | Framing, count, block/index |
| Cơ hội SIMD | Có nhưng phụ thuộc layout | Phụ thuộc bộ mã và decoder |
| Trường enum/nullable | Cần mã hợp lệ rõ ràng | Cần mã dấu/sentinel rõ ràng |

### Ví dụ

- Một triệu giá trị trong miền `0..15`: trường cố định 4 bit có thể đóng gói **2 giá trị/byte**. ULEB128 thông thường dùng **1 byte/giá trị**, gấp đôi payload.
- Một triệu giá trị `uint64` nhưng phần lớn bằng 0 và vài số rất lớn: fixed-width 64 bit dùng 8 byte/giá trị, varint có thể tiết kiệm đáng kể.
- Danh sách ID tăng với gap nhỏ: delta+varint có thể vượt fixed-width packing của ID tuyệt đối, nhưng đánh đổi truy cập ngẫu nhiên.

**Cần chọn bằng dữ liệu và truy vấn thực**, không chọn vì kỹ thuật nào “nén hơn” trên lý thuyết chung.

## 25. Chia block để cân bằng bộ nhớ và giải mã

Một chiến lược thực tế là lưu một **block** gồm B bản ghi với cùng schema hoặc cùng độ rộng cục bộ.

Mỗi block có thể có header:

```text
version
record_count
field_widths / schema_id
payload_length
optional checksum
```

Ưu điểm:

- Chỉ cần giải mã block được truy cập.
- Có thể kiểm tra lỗi ở phạm vi block.
- Cập nhật/migration được giới hạn trong một block.
- Có thể tối ưu độ rộng khác nhau giữa các block nếu dữ liệu biến thiên.

Nhược điểm:

- Mỗi block có header và có thể padding.
- Block càng nhỏ, metadata/record càng lớn.
- Block càng lớn, giải mã hoặc cập nhật một phần nhỏ càng có thể đắt.

### Công thức kiểm kê

Nếu mỗi block có header H byte, n bản ghi tổng cộng, mỗi bản ghi dùng W bit, block chứa tối đa B bản ghi và padding theo byte ở cuối từng block:

\[
B_{\mathrm{total}}
=\sum_{j=1}^{\lceil n/B\rceil}
\left(
H+\left\lceil\frac{W\,n_j}{8}\right\rceil
\right),
\]

trong đó `n_j` là số bản ghi của block thứ j.

So sánh với một dense bitstream toàn bộ:

\[
B_{\mathrm{dense}}
=\left\lceil\frac{Wn}{8}\right\rceil.
\]

Tổng block có thể lớn hơn, nhưng cung cấp **tính cục bộ truy cập và khả năng phục hồi**.

## 26. Nhu cầu truy vấn có thể quyết định bố cục

Xét ba kiểu truy vấn:

1. Lấy **toàn bộ bản ghi** theo ID.
2. Quét **cờ alarm** của nhiều bản ghi.
3. Tính trung bình **score** của cả tập.

### Layout theo hàng (AoS)

```text
[id, mode, alarm, score]
[id, mode, alarm, score]
[id, mode, alarm, score]
```

Thuận lợi khi mỗi lần đọc cần **mọi trường của một bản ghi**. Với dense fixed-width, mỗi lần truy cập tính offset theo `18i`.

### Layout theo cột (SoA)

```text
sensor_id: [id0, id1, id2, ...]
mode:      [m0,  m1,  m2,  ...]
alarm:     [a0,  a1,  a2,  ...]
score:     [s0,  s1,  s2,  ...]
```

Thuận lợi khi quét riêng `alarm` hoặc `score`. Một cột alarm có thể là bitset, giúp kiểm tra hàng loạt bit bằng phép bitwise.

### Bố cục kết hợp

Có thể lưu:

- ID và mode trong một cấu trúc theo hàng.
- Alarm dưới dạng bitset theo cột.
- Score dưới dạng mảng 4 bit theo cột.

Lựa chọn phù hợp phụ thuộc:

- Tỷ lệ truy vấn theo hàng/cột.
- Tần suất cập nhật từng trường.
- Khả năng vectorization.
- Overhead chỉ mục.
- Tính cục bộ cache.

**Tổng số bit trường bằng nhau không có nghĩa hai bố cục có cùng hiệu năng.**

## 27. Hiệu ứng cache, SIMD và giải mã theo lô

Trong một hệ thống thực tế, giải mã từng bản ghi bằng hàm Python có thể chậm hơn xử lý theo lô trong C++ hoặc SIMD.

Các hướng tối ưu:

- Dùng phép dịch/mask trên **từ 32/64 bit** chứa nhiều trường.
- Dùng **lookup table** cho một số pattern nhỏ.
- Chia block để giải mã nhiều bản ghi liên tiếp.
- Với layout cho phép, dùng SIMD để tải và trích nhiều trường cùng lúc.
- Tách kiểm tra dữ liệu lỗi khỏi vòng lặp nóng sau khi xác thực block, nếu yêu cầu an toàn cho phép.
- Giảm phân bổ đối tượng trung gian bằng cách xử lý trực tiếp dữ liệu packed.

### Không nên giả định SIMD miễn phí

Một trường cắt qua ranh giới từ có thể cần thao tác ghép nhiều lane. Các lệnh dịch/hoán vị byte có chi phí. Một schema có độ rộng thay đổi cũng có thể hạn chế vectorization.

Thậm chí một bố cục **rộng hơn nhưng byte-aligned** có thể giải mã nhanh hơn dense bitstream trên CPU cụ thể. Chỉ benchmark mới xác nhận được.

### Cache có thể thay đổi kết quả

Bit packing giảm tổng byte cần truy cập; với bài toán **memory-bound**, ít dữ liệu phải chuyển từ RAM có thể là lợi thế rất lớn. Với bài toán **compute-bound**, phép giải mã bổ sung có thể làm chậm.

Hai tác động này ngược chiều nhau, nên cần đo trên workload gần với sản xuất.

## 28. Chi phí bộ nhớ: payload, container, padding và peak

Chỉ nhìn `Wn` bit là chưa đủ để đánh giá tổng RAM.

Một mô hình kế toán:

\[
\text{Total}
=
\text{Payload}
+\text{Padding}
+\text{Metadata}
+\text{Index}
+\text{AllocationOverhead}.
\]

### Ví dụ 1.000 bản ghi

Với W=18:

```text
Logical information in field layout:
  1000 * 18 = 18000 bit = 2250 byte

Record-by-record 3-byte layout:
  1000 * 3 = 3000 byte

Dense stream:
  ceil(18000 / 8) = 2250 byte
```

Nhưng nếu lưu danh sách gồm **1.000 đối tượng Python `SensorRecord`**, bộ nhớ thực tế còn gồm object header, tham chiếu, danh sách và các giá trị Python. Không thể lấy `2250` byte làm số RAM của cách lưu đối tượng này.

### Đo gì?

- `len(bytearray)`: byte dữ liệu đang có.
- `sys.getsizeof(bytearray)`: kích thước nông của object Python, tùy triển khai.
- `sizeof(T)`: kích thước đối tượng C++ T, gồm padding nhưng không gồm vùng heap của vector.
- `vector.capacity()*sizeof(T)`: vùng phần tử được cấp cho vector, chưa tính allocator overhead.
- Trình profiler: peak memory khi **giải nén toàn bộ**, tạo index hoặc chuyển đổi schema.

Một cấu trúc đóng gói có thể tiết kiệm dung lượng lưu trữ lâu dài nhưng tạm thời dùng rất nhiều RAM khi chuyển sang dạng rộng để tính toán.

## 29. Truy cập không căn chỉnh và vùng nhớ an toàn

Có hai khái niệm thường bị lẫn:

1. **Trường không căn theo byte:** một bản ghi 18 bit bắt đầu giữa byte.
2. **Tải nguyên một số 32/64 bit từ địa chỉ không căn chỉnh:** phụ thuộc quy tắc kiến trúc CPU và ngôn ngữ.

Cách truy cập bit trong `bytearray` Python ở bài dùng `int.from_bytes` trên một slice đúng kích thước. Nó không làm một phép cast con trỏ không căn chỉnh.

Trong C++, không nên làm:

```cpp
// Ví dụ nguy hiểm — không dùng làm giao thức portable:
// const std::uint32_t value =
//     *reinterpret_cast<const std::uint32_t*>(raw + offset);
```

để đọc từ một buffer bất kỳ, vì:

- Có thể vi phạm yêu cầu alignment.
- Có thể vi phạm quy tắc truy cập đối tượng/aliasing.
- Có thể đọc **quá số byte còn lại**.
- Kết quả phụ thuộc endianness.

Cách an toàn là **đọc các byte có kiểm tra phạm vi** và ghép bằng dịch/OR, hoặc dùng `memcpy` vào một đối tượng đúng kiểu khi phù hợp rồi chuyển endian theo định dạng.

## 30. Dữ liệu đồng thời và vấn đề false sharing

Giả sử một luồng cần sửa alarm của bản ghi i, luồng khác sửa score của bản ghi i+1. Trong dense bitstream, hai trường có thể nằm ở **cùng byte hoặc cùng từ máy**.

Một thao tác cập nhật có thể là:

```text
read byte
clear target bits
set new bits
write byte
```

Nếu hai luồng cùng làm không có đồng bộ, một phép ghi có thể **mất** cập nhật của luồng kia.

### Ba mức cần phân biệt

- **Không chồng trường ở cấp bit:** đúng về layout.
- **Không chồng đơn vị bộ nhớ được ghi:** chưa chắc đúng.
- **Không có data race:** chỉ đúng khi tuân thủ quy tắc đồng bộ/nguyên tử của môi trường chạy.

### Phương án xử lý

- Dùng khóa ở cấp block hoặc bản ghi.
- Dùng đơn vị lưu trữ nguyên tử phù hợp và cập nhật bằng thao tác atomically read-modify-write.
- Chọn layout tránh hai tác vụ cùng ghi vào một đơn vị lưu trữ.
- Gom cập nhật tuần tự rồi publish một snapshot bất biến.

Đóng gói theo bit có thể làm **đơn vị chia sẻ ghi** lớn hơn một trường logic; vì vậy yêu cầu concurrent update là một tiêu chí quan trọng khi chọn layout.

## 31. Bảo toàn tính chính xác và canonical form

Một bộ mã hóa/giải mã tốt cần thỏa:

\[
\operatorname{decode}(\operatorname{encode}(r))=r
\]

với mọi bản ghi hợp lệ r.

Ngoài ra:

- `encode` phải từ chối giá trị vượt miền.
- `decode` phải từ chối mã enum không hợp lệ.
- `decode` phải từ chối padding bit khác 0 nếu giao thức yêu cầu canonical.
- Khi sửa một trường, các trường khác không thay đổi.
- Nếu dữ liệu chứa n bản ghi với width W, số byte buffer phải đúng hoặc đủ theo quy tắc framing.
- Bit padding cuối buffer có giá trị xác định khi cần kiểm tra tính duy nhất của biểu diễn.

### Khi nào phải lưu số bản ghi?

Với dense 18 bit, một buffer có 9 byte chứa 72 bit có thể tương ứng **bốn bản ghi** chính xác (`4*18=72`). Nhưng khi số bit không chia hết cho 8, byte cuối có padding; chỉ từ số byte **chưa chắc biết được số bản ghi hợp lệ** nếu format còn loại dữ liệu khác hoặc chưa quy định framing.

Bộ giải mã nên biết `record_count` từ schema/header hoặc một quy tắc ranh giới rõ ràng.

### Tại sao canonical quan trọng?

Nếu padding tự do mang giá trị bất kỳ, hai byte stream có thể biểu diễn cùng dữ liệu logic. Điều đó gây rắc rối cho:

- Hash và chữ ký số của dạng serialized.
- So sánh byte để kiểm tra bằng nhau.
- Cache key và deduplication.
- Kiểm thử liên nền tảng.

Đặt padding về 0 và kiểm tra khi đọc là cách phổ biến để có biểu diễn nhất quán.

## 32. Kiểm thử ranh giới và ví dụ tính tay

Các trường hợp nên có trong unit test:

- Giá trị nhỏ nhất/lớn nhất của mọi trường.
- ID `0` và `1023`.
- Mode `0`, `5` và mode `6,7` (phải từ chối).
- Alarm `false` và `true`.
- Score `0` và `15`.
- Bản ghi chứa mọi trường bằng 0.
- Bản ghi ví dụ `513,5,true,9` tạo `01 76 02`.
- Buffer 3 byte có bit padding cao khác 0.
- Mảng dense rỗng, một bản ghi, hai bản ghi, bốn bản ghi, năm bản ghi.
- Đọc/ghi bản ghi ở bit offset `0,2,4,6` trong byte.
- Thay bản ghi i, chứng minh bản ghi i−1 và i+1 không đổi.
- Kiểm tra buffer không ghi vượt vùng đã cấp.
- Thử truy cập chỉ số âm và chỉ số ≥n.
- Trường có dấu ở hai đầu miền, sentinel/null.
- Cùng dữ liệu trên Python và C++ phải tạo **cùng bytes** theo schema.

### Python: kiểm tra nhiều bản ghi tự động

```python
import random

rng = random.Random(2026)

samples = [
    SensorRecord(
        sensor_id=rng.randint(0, 1023),
        mode=rng.randint(0, 5),
        alarm=bool(rng.getrandbits(1)),
        score=rng.randint(0, 15),
    )
    for _ in range(100)
]

dense = DenseSensorArray()
for r in samples:
    dense.append(r)

assert dense.payload_bytes() == (100 * 18 + 7) // 8

for i, expected in enumerate(samples):
    assert dense.get(i) == expected

for i in range(0, 100, 7):
    updated = SensorRecord(1023, 5, True, 15)
    dense.set(i, updated)
    samples[i] = updated

assert [dense.get(i) for i in range(100)] == samples
```

Đây là kiểm thử round-trip theo dữ liệu pseudo-random có seed cố định. Nó kiểm tra nhiều tổ hợp mà không phải viết thủ công từng bản ghi. Tuy nhiên nó **không thay thế kiểm thử đầu vào không hợp lệ** và kiểm thử hiệu năng trên dữ liệu thật.

## 33. Bảng lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Không tính số trạng thái trước khi chọn width | Tràn miền hoặc lãng phí bit | Dùng `⌈log₂N⌉` |
| Nhầm offset tính bằng bit với offset tính bằng byte | Đọc/ghi sai trường | Quy định đơn vị cho mọi offset |
| Không mask sau khi dịch phải | Lẫn bit trường cao hơn | `(word>>offset)&mask` |
| Ghi trường mới bằng OR mà không xóa trường cũ | Bit 1 cũ không thể đổi thành 0 | Dùng read–clear–set |
| Quên kiểm tra giá trị vượt width | Tràn sang trường kế bên | Kiểm tra miền trước khi shift |
| Quên kiểm tra enum chưa dùng | Chấp nhận trạng thái vô nghĩa | Từ chối/fallback theo schema |
| Đọc padding như dữ liệu | Giải mã không canonical | Kiểm tra reserved bits |
| Nhầm little-endian với MSB-first | Byte không tương thích | Ghi rõ cả byte và bit order |
| Coi `sizeof(struct)` bằng tổng width/8 | Bỏ qua padding/alignment | Đo `sizeof` và serialize tường minh |
| Dùng C++ native bit-field làm wire format | Phụ thuộc ABI/compiler | Tự shift/mask hoặc thư viện có đặc tả |
| Cập nhật chung byte mà không giữ bit hàng xóm | Làm hỏng bản ghi khác | Mask đúng bit đích |
| Truy cập buffer không kiểm tra biên | Đọc/ghi ngoài vùng | Kiểm tra length/count/span |
| Ghi dữ liệu từ nhiều luồng không đồng bộ | Lost update hoặc data race | Khóa/atomic/layout riêng |
| Tuyên bố dense 18 bit luôn chỉ chạm 2 byte | Có thể cắt qua ranh giới | Dùng `⌈(shift+W)/8⌉` |
| Không tính metadata/header/index | Đánh giá RAM thấp giả | Kiểm kê toàn bộ layout |
| Không tính thời gian decode | Chọn layout chậm cho workload | Benchmark đọc/ghi thực tế |
| Coi mọi width mở rộng được mà không migration | Đọc dữ liệu cũ sai | Dùng versioned schema |
| Cố tạo sentinel khi đã dùng hết mã | Mất một giá trị hợp lệ | Thêm validity bit/tăng width |
| Cho bit padding thay đổi tùy ý | Byte serialization không duy nhất | Canonical padding = 0 |
| Quên độ dài số bản ghi trong dense stream | Không biết phần nào là padding | Định nghĩa count/framing |

## 34. Quy trình thiết kế và đánh giá một layout bit

Khi thiết kế một cấu trúc packed cho dữ liệu thực tế:

1. **Liệt kê trường và miền hợp lệ.** Phân biệt số nguyên, enum, Boolean, nullable và sentinel.
2. **Đếm trạng thái.** Tính width tối thiểu của từng trường; cân nhắc chặn cho cả bản ghi.
3. **Chọn thứ tự trường và offset.** Tạo bảng layout, không chỉ viết code.
4. **Chọn byte/bit order.** Đảm bảo encoder và decoder thống nhất.
5. **Chọn đơn vị lưu.** Bản ghi byte-aligned, dense bitstream, theo block hay theo cột.
6. **Quy định versioning và mã lỗi.** Đặc biệt mode dự phòng và padding.
7. **Viết encoder/decoder rõ ràng.** Kiểm tra range trước khi ghi và hợp đồng khi đọc.
8. **Kiểm thử round-trip và biên.** Bao gồm ranh giới byte, cập nhật một trường và dữ liệu hỏng.
9. **Tính tổng bộ nhớ.** Payload, padding, container, header, index, capacity và peak.
10. **Đo thao tác thực.** Truy cập ngẫu nhiên, quét tuần tự, decode cả khối, update theo trường, khả năng SIMD.
11. **Kiểm tra yêu cầu đồng thời.** Hai trường có thể chia sẻ byte/từ và gây data race.
12. **Chọn layout theo workload.** Mục tiêu là tổng thể hiệu quả, không phải chỉ giảm được nhiều bit nhất.

Bước cuối cùng rất quan trọng: một định dạng tiết kiệm 30% payload nhưng khiến truy vấn thường xuyên chậm gấp nhiều lần **có thể không phải lựa chọn tốt**, nhất là khi dữ liệu đã nằm trong cache.

## 35. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một trường có sáu giá trị hợp lệ cần ít nhất bao nhiêu bit trong mã cố định?

**Đáp án:** **3 bit**, vì `2²=4<6≤8=2³`.

**Câu 2.** Trường ID `0..1023` cần mấy bit?

**Đáp án:** **10 bit**, vì có 1.024 giá trị, đúng `2^{10}`.

**Câu 3.** Bản ghi gồm ID 10 bit, mode 3 bit, alarm 1 bit và score 4 bit cần tổng bao nhiêu bit?

**Đáp án:** **18 bit**.

**Câu 4.** Nếu căn mỗi bản ghi ở ranh giới byte, cần bao nhiêu byte và bao nhiêu bit padding?

**Đáp án:** **3 byte**, tức 24 bit; **6 bit padding**.

**Câu 5.** Với 1.000 bản ghi rộng 18 bit, dense bitstream dùng bao nhiêu byte payload?

**Đáp án:** `⌈1000·18/8⌉=2.250` byte.

**Câu 6.** Lưu 1.000 bản ghi theo từng gói 3 byte cần bao nhiêu byte payload?

**Đáp án:** **3.000 byte**, chưa tính metadata.

**Câu 7.** Trong layout của bài, `mode` có offset và width nào?

**Đáp án:** Offset **10 bit**, width **3 bit**.

**Câu 8.** Công thức đọc một trường width w, offset o từ packed word là gì?

**Đáp án:** `(word >> o) & ((1 << w) - 1)`.

**Câu 9.** Vì sao cần mask khi đọc sau khi dịch phải?

**Đáp án:** Dịch phải đưa trường về các bit thấp nhưng vẫn có thể còn các bit của trường cao hơn; mask chỉ giữ đúng width.

**Câu 10.** Mã hóa `sensor_id=513`, `mode=5`, `alarm=true`, `score=9` cho word nào?

**Đáp án:** **`0x27601`**, tương đương 161.281 thập phân.

**Câu 11.** Ba byte little-endian của `0x027601` là gì?

**Đáp án:** **`01 76 02`**.

**Câu 12.** Nếu dùng big-endian cho cùng số 24 bit thì ba byte là gì?

**Đáp án:** **`02 76 01`**. Hai cách khác nhau và phải được quy định trong schema.

**Câu 13.** Bản ghi i=1 rộng 18 bit bắt đầu ở bit offset nào và tại bit nào trong byte?

**Đáp án:** Bit offset **18**; bắt đầu ở **byte 2, bit 2** vì `18//8=2` và `18%8=2`.

**Câu 14.** Bản ghi i=3 nằm trong những byte nào khi dữ liệu được đóng liên tục 18 bit?

**Đáp án:** Bit offset 54..71, nằm ở **byte 6, 7 và 8**, tức 3 byte.

**Câu 15.** Công thức chung tính số byte cửa sổ khi trường width W bắt đầu ở bit s trong byte là gì?

**Đáp án:** `⌈(s+W)/8⌉`.

**Câu 16.** Vì sao sửa mode chỉ bằng `word |= (newMode<<10)` là sai?

**Đáp án:** OR chỉ đặt bit 1, không xóa được bit 1 cũ. Phải xóa mask trường cũ rồi chèn giá trị mới.

**Câu 17.** Hai bản ghi chia sẻ byte có thể cập nhật độc lập không?

**Đáp án:** **Có nếu có cơ chế đúng**, nhưng thao tác cập nhật phải giữ nguyên bit ngoài trường; cập nhật đồng thời còn cần đồng bộ hoặc atomic thích hợp.

**Câu 18.** Một nhiệt độ nguyên `−40..87` cần mấy bit và cách mã dịch miền là gì?

**Đáp án:** Có 128 giá trị, cần **7 bit**. Lưu `code=t+40` và khôi phục `t=code−40`.

**Câu 19.** Với miền nhiệt độ ở câu 18, thêm trạng thái null có còn đủ 7 bit không?

**Đáp án:** **Không.** Có 129 trạng thái, cần 8 bit hoặc một bit validity/metadata ngoài.

**Câu 20.** Vì sao enum mode=7 là giá trị không hợp lệ dù fit trong 3 bit?

**Đáp án:** Schema chỉ cho phép mode `0..5`. Fit độ rộng không đồng nghĩa hợp lệ về ngữ nghĩa.

**Câu 21.** Tại sao không nên ghi thẳng `sizeof(struct)` byte của C++ struct làm giao thức?

**Đáp án:** Struct có thể chứa padding, căn chỉnh và endian phụ thuộc ABI; byte layout không được đảm bảo giống bảng trường của giao thức.

**Câu 22.** `std::vector<bool>` hoặc C++ bit-field có đảm bảo một wire layout cố định trên mọi compiler không?

**Đáp án:** **Không.** Muốn có định dạng ổn định, cần đặc tả và serialize tường minh.

**Câu 23.** Truy vấn chỉ bit alarm của bản ghi thứ i trong dense stream có bit offset toàn cục nào?

**Đáp án:** **`18i+13`**, vì bản ghi bắt đầu ở `18i` và alarm ở offset 13.

**Câu 24.** Vì sao bố cục theo cột (SoA) có thể nhanh hơn khi chỉ quét alarm?

**Đáp án:** Các cờ alarm nằm liên tiếp trong một bitset, thuận tiện quét và dùng phép bitwise, ít phải giải những trường khác.

**Câu 25.** Vì sao dense bit packing có thể cải thiện thông lượng dù cần thêm phép dịch/mask?

**Đáp án:** Nó giảm byte phải tải từ bộ nhớ, có thể tăng hiệu quả cache và giảm băng thông RAM khi bài toán memory-bound.

**Câu 26.** Khi nào byte-aligned records có thể đáng chọn dù dùng nhiều bộ nhớ hơn?

**Đáp án:** Khi ứng dụng cần truy cập/cập nhật bản ghi độc lập, SIMD, giao tiếp đơn giản hoặc tối ưu tốc độ giải mã trên nền tảng cụ thể.

**Câu 27.** Một bit padding khác 0 có thể gây vấn đề gì?

**Đáp án:** Tạo nhiều byte stream khác nhau cho cùng dữ liệu, ảnh hưởng so sánh byte, hash, chữ ký và tương thích; nên có chính sách canonical.

**Câu 28.** Vì sao hai trường không chồng bit vẫn có thể gây lỗi cập nhật trong chương trình đa luồng?

**Đáp án:** Chúng có thể chia sẻ cùng byte/từ của một thao tác read–modify–write, dẫn tới data race hoặc lost update nếu không đồng bộ.

**Câu 29.** Với n bản ghi, width W và header H byte mỗi block B bản ghi, chi phí nào phải tính ngoài payload `Wn`?

**Đáp án:** Các header theo số block, padding ở cuối từng block, index/offset, allocator/container overhead và có thể peak memory khi decode.

**Câu 30.** Vì sao `O(1)` cho `get` của bản ghi fixed-width không chứng minh nó nhanh bằng đọc một `uint32_t`?

**Đáp án:** `O(1)` chỉ nói số bước bị chặn theo n; giải mã vẫn có phép tính offset, nhiều load, shift, mask, kiểm tra enum và các hằng số thời gian khác.

## Ghi nhớ

- **Đóng gói trường cố định** dùng một bố cục tường minh gồm **miền giá trị, width, offset và mask**. Muốn giải mã đúng phải thống nhất cả **byte order** và **bit order**.
- Một bản ghi cảm biến gồm ID 10 bit, mode 3 bit, alarm 1 bit và score 4 bit cần **18 bit**. Nếu căn theo byte là **3 byte/bản ghi**, còn ghép sát n bản ghi cần **`⌈18n/8⌉` byte payload**.
- Đọc trường bằng **`(word>>offset)&mask`**. Cập nhật phải **xóa đúng bit cũ rồi chèn bit mới**, giữ nguyên bit hàng xóm.
- **Mã có đúng độ rộng chưa chắc hợp lệ về ngữ nghĩa**: enum có mã dự phòng, trường có dấu cần quy tắc riêng, sentinel có thể làm tăng số trạng thái; padding cần chính sách canonical.
- **Native C/C++ bit-field và `sizeof(struct)` không phải định dạng dây portable**. Dùng shift/mask tường minh hoặc serializer có đặc tả rõ để tránh phụ thuộc padding, ABI và endian.
- Đóng gói bit giảm byte truyền và có thể tăng hiệu quả cache, nhưng thêm chi phí **decode, read–modify–write, truy cập không căn chỉnh, đồng bộ và versioning**.
- **Bố cục đúng là bố cục hợp với truy vấn.** AoS thuận tiện đọc toàn bản ghi; SoA thuận tiện quét riêng trường; block và index có thể đổi dung lượng lấy tốc độ/cập nhật.
- Khi đánh giá, đo **payload + padding + metadata + capacity + peak memory**, cùng thời gian đọc, ghi và giải mã trên workload thực. Mục tiêu không phải ít bit nhất bằng mọi giá, mà là hiệu quả toàn hệ thống.
