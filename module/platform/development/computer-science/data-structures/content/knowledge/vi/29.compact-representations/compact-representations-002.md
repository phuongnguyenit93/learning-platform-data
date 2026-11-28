# Mã hóa số nguyên có độ dài thay đổi và mã hóa chênh lệch

Một danh sách ID tài liệu đã sắp xếp gồm các giá trị:

```text
1000, 1004, 1011, 1011, 1020, 1100
```

Nếu lưu mỗi ID bằng số nguyên 32 bit, sáu ID cần **24 byte** payload. Nếu dùng mã số nguyên có độ dài thay đổi, mỗi giá trị trên dùng **2 byte**, tổng **12 byte**. Nhưng nếu lưu giá trị **chênh lệch so với phần tử trước**:

```text
1000, 4, 7, 0, 9, 80
```

và mã hóa các chênh lệch bằng cùng định dạng, toàn bộ dãy chỉ cần **7 byte** payload.

Sự tiết kiệm không đến từ “nén thần kỳ”. Nó đến từ hai nhận xét: **giá trị nhỏ có thể dùng ít byte hơn** và **một dãy có thứ tự thường chứa nhiều chênh lệch nhỏ dù giá trị tuyệt đối lớn**. Để khai thác được hai nhận xét này mà vẫn giải mã chính xác, ta phải quy định rõ định dạng bit, dấu kết thúc, số nguyên có dấu, mốc khởi đầu, miền giá trị và cách xử lý dữ liệu hỏng.

Bài học thuộc chương **Biểu diễn gọn** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Học phần hướng tới lựa chọn cấu trúc dữ liệu thông qua bất biến, thao tác và chi phí thời gian/bộ nhớ. Trọng tâm của bài là **mã hóa số nguyên có độ dài thay đổi (variable-length integer encoding)** và **mã hóa chênh lệch (delta/gap encoding)**, từ nguyên lý đến mã Python, C++17, kiểm thử và đánh đổi với truy cập ngẫu nhiên.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt cách lưu số nguyên **độ rộng cố định** với **độ dài thay đổi**.
2. Đọc và tạo mã **unsigned LEB128 / base-128 varint** ở mức từng byte.
3. Giải thích vai trò **7 bit payload và 1 bit continuation**, mốc 127/128, 16.383/16.384.
4. Viết bộ mã hóa/giải mã kiểm tra **truncated input, overlong/non-canonical encoding và tràn 64 bit**.
5. Mã hóa số nguyên âm bằng **ZigZag + unsigned varint** và phân biệt với **signed LEB128**.
6. Biến một dãy **không giảm** thành các **delta không âm**, rồi khôi phục bằng prefix sum.
7. Biết khi nào mã hóa chênh lệch làm nhỏ dữ liệu và khi nào không.
8. Phân tích việc tiết kiệm bộ nhớ đổi lấy **giải mã tuần tự, chỉ mục, checkpoint và khó khăn khi cập nhật**.
9. Phân biệt mã hóa chênh lệch với **delta-of-delta**, **run-length encoding** và **frame of reference**.
10. Tính đúng kích thước payload, kiểm thử ranh giới và lựa chọn biểu diễn theo workload.

### Thuật ngữ và ký hiệu

- `x`: giá trị nguyên cần mã hóa.
- `n`: số phần tử của dãy.
- `d_i`: độ chênh lệch của phần tử i so với phần tử liền trước.
- `b`: số **bit dữ liệu** trong một nhóm mã; với ULEB128, `b=7`.
- `L(x)`: số byte dùng để mã hóa x.
- `B`: tổng số byte payload của cả luồng.
- `M`: giá trị nguyên không dấu lớn nhất được phép trong định dạng.

Trừ khi nêu khác, ví dụ varint dùng **số nguyên không dấu tối đa 64 bit** và **byte có 8 bit**. Python có số nguyên độ chính xác tùy ý, nên các ví dụ Python chủ động đặt giới hạn 64 bit để bảo đảm tương thích với C++.

## 2. Vì sao độ rộng cố định có thể lãng phí?

Một `uint32` lưu mỗi giá trị trong **32 bit = 4 byte**, bất kể giá trị là:

```text
0
1
7
127
128
1000
4.000.000.000
```

Cách này có nhiều lợi ích:

- Đọc vị trí thứ i bằng địa chỉ `base + 4*i`.
- Dễ chỉnh sửa một phần tử mà không dịch các byte phía sau.
- Thường thuận lợi cho căn chỉnh và xử lý theo từ máy.
- Kích thước chính xác dễ tính: `4n` byte payload.

Nhưng nếu phần lớn giá trị chỉ quanh `0..100`, vùng 32 bit có nhiều bit cao bằng 0, lặp lại ở mỗi phần tử.

### Ý tưởng của mã độ dài thay đổi

Ta không buộc mọi số dùng bốn byte. Thay vào đó:

```text
Số nhỏ          → ít byte
Số lớn          → nhiều byte
```

Chẳng hạn với varint base-128:

| Giá trị | Số byte mã hóa |
|---:|---:|
| 0 | 1 |
| 1 | 1 |
| 127 | 1 |
| 128 | 2 |
| 255 | 2 |
| 16.383 | 2 |
| 16.384 | 3 |
| 1.000.000 | 3 |

Đây là **mã không mất thông tin**: giải mã phải trả về đúng từng giá trị, không làm tròn hay bỏ chữ số.

**Cần phân biệt:** varint không phải lúc nào cũng nhỏ hơn mã cố định. Nếu mọi giá trị đều nằm trong `0..255`, một byte `uint8` đã đủ; ULEB128 lại dùng **hai byte** cho các giá trị từ 128 đến 255. Lựa chọn định dạng phải dựa vào **phân phối giá trị thực tế**.

## 3. ULEB128 là một định dạng varint cụ thể

Từ **varint** là tên chung cho các mã số nguyên có độ dài thay đổi. Có nhiều định dạng khác nhau: các biến thể base-128, signed LEB128, mã tiền tố trên bit, mã theo block, v.v.

Trong bài, **ULEB128 (Unsigned Little Endian Base 128)** được dùng làm định dạng mẫu:

- Mỗi byte có **8 bit**.
- **7 bit thấp** chứa dữ liệu.
- **Bit cao nhất** `0x80` là cờ **continuation**:
  - `1`: **còn byte phía sau**.
  - `0`: **byte cuối** của số nguyên.
- Các nhóm 7 bit được lưu từ **ít quan trọng nhất đến quan trọng nhất**.

Sơ đồ một byte:

```text
Bit số:   7  6 5 4 3 2 1 0
          ┬  ───────────
          │       │
          │       └── payload 7 bit (0..127)
          └────────── continuation flag
```

Giá trị của byte:

\[
\text{payload}=\text{byte}\ \&\ 0x7F.
\]

Ký hiệu `&` là AND bit, còn `0x7F=127`.

### Lưu ý về tên gọi

“Little endian” ở đây nói về **thứ tự các nhóm 7 bit**: nhóm thấp trước, nhóm cao sau. Nó **không đồng nghĩa** với việc đọc nguyên một vùng nhiều byte theo endianness của kiểu `uint32_t` hoặc `uint64_t` của CPU.

Một số hệ thống dùng bit cao để đánh dấu **byte cuối**, ngược với ULEB128. Không thể chỉ nhìn chữ “varint” rồi cho rằng hai định dạng tương thích. Phải xem đặc tả bit.

## 4. Đọc ULEB128 từ byte và kết thúc ở đâu?

Giả sử các byte của một số nguyên là:

```text
AC 02
```

Viết nhị phân:

```text
AC = 1010 1100
02 = 0000 0010

     ↑          ↑
   có tiếp    kết thúc
```

Tách payload:

```text
AC & 7F = 2C = 44
02 & 7F = 02 = 2
```

Nhóm đầu đặt ở các bit 0..6, nhóm hai đặt ở các bit 7..13:

\[
44 + 2\cdot 2^7
=44+256
=300.
\]

Vậy:

\[
\boxed{\texttt{AC 02}\longleftrightarrow 300}.
\]

### Cách đọc một luồng nhiều số

Giả sử luồng:

```text
7F 80 01 AC 02 00
```

Ta duyệt từ trái sang phải:

1. `7F` có bit cao 0 → kết thúc số đầu: **127**.
2. `80` có bit cao 1, `01` có bit cao 0 → hai byte cho **128**.
3. `AC` có bit cao 1, `02` có bit cao 0 → hai byte cho **300**.
4. `00` có bit cao 0 → số **0**.

Kết quả giải mã:

```text
[127, 128, 300, 0]
```

Điểm quan trọng: **không cần dấu phẩy giữa các số** vì bit continuation xác định ranh giới từng mã. Tuy nhiên, nếu một file chứa cả nhiều loại trường, bộ giải mã vẫn cần biết **số lượng và thứ tự trường** từ schema hoặc metadata.

## 5. Thuật toán mã hóa ULEB128 từng bước

Với một số không âm x:

1. Lấy 7 bit thấp bằng `x & 0x7F`.
2. Bỏ 7 bit đó khỏi x bằng phép dịch phải `x >>= 7`.
3. Nếu x còn khác 0, đặt bit cao của byte vừa lấy bằng `| 0x80`.
4. Ghi byte.
5. Lặp lại cho tới khi không còn nhóm cao.

Giả mã:

```text
encode_uvarint(x):
    require 0 <= x <= MAX_VALUE

    repeat:
        payload = x & 0x7F
        x = x >> 7

        if x != 0:
            output(payload | 0x80)
        else:
            output(payload)
            stop
```

### Mã hóa 300

```text
x = 300
payload0 = 300 & 127 = 44 = 0x2C
x >>= 7  → 2
còn byte → 0x2C | 0x80 = 0xAC

payload1 = 2 & 127 = 2 = 0x02
x >>= 7  → 0
byte cuối → 0x02

Kết quả: AC 02
```

### Mã hóa 16.384

```text
16.384 = 2^14

Nhóm 7 bit thấp: 0 → 80
Nhóm tiếp theo:   0 → 80
Nhóm cuối:        1 → 01

Kết quả: 80 80 01
```

**Không được bỏ byte cuối `01`**: hai byte `80 80` đều đặt bit continuation, nên nếu luồng dừng ở đó, mã chưa hoàn thành.

## 6. Các mốc ranh giới quan trọng

Một byte ULEB128 lưu **7 bit dữ liệu**, hai byte lưu tối đa 14 bit, ba byte lưu tối đa 21 bit, v.v.

Với x không âm:

\[
L(x)=
\begin{cases}
1,&x=0,\\[4pt]
\left\lceil\frac{\operatorname{bitLength}(x)}7\right\rceil,&x>0.
\end{cases}
\]

Tương đương, số x nằm trong `[0,2^7−1]` thì dùng một byte; `[2^7,2^{14}−1]` thì hai byte.

| x (thập phân) | Hex ULEB128 | Số byte |
|---:|---|---:|
| 0 | `00` | 1 |
| 1 | `01` | 1 |
| 63 | `3F` | 1 |
| 127 | `7F` | 1 |
| 128 | `80 01` | 2 |
| 129 | `81 01` | 2 |
| 255 | `FF 01` | 2 |
| 300 | `AC 02` | 2 |
| 16.383 | `FF 7F` | 2 |
| 16.384 | `80 80 01` | 3 |
| 1.000.000 | `C0 84 3D` | 3 |

### Tại ngưỡng, kích thước nhảy một byte

Chênh lệch từ **127 lên 128 chỉ là 1 về giá trị**, nhưng kích thước tăng từ 1 byte lên 2 byte. Tương tự, từ **16.383 lên 16.384** tăng từ 2 lên 3 byte.

Điều này sẽ ảnh hưởng trực tiếp đến tính toán chi phí và quyết định có nên chia dữ liệu theo block hay không.

### Giới hạn của số không dấu 64 bit

`uint64` có miền:

\[
0\le x\le 2^{64}-1.
\]

ULEB128 dùng tối đa:

\[
\left\lceil\frac{64}{7}\right\rceil=10
\]

byte cho `uint64`. Nhưng byte thứ mười **chỉ có thể chứa đúng một bit payload có nghĩa**, vì chín byte đầu đã chứa 63 bit.

Đối với **mã canonical** của một số `uint64` có đúng mười byte, byte cuối phải là `01`. Nếu nó là `02` hoặc có bit continuation, luồng không biểu diễn một số `uint64` hợp lệ.

## 7. Giải mã ULEB128 bằng cộng các nhóm 7 bit

Bộ giải mã giữ một biến `value` và biến độ dịch `shift`, ban đầu đều bằng 0.

Mỗi lần đọc byte:

```text
payload = byte & 0x7F
value |= payload << shift
shift += 7

if byte & 0x80 == 0:
    return value
```

Bất biến sau khi đọc k nhóm payload:

\[
\text{value}
=\sum_{j=0}^{k-1}p_j\,2^{7j},
\quad 0\le p_j<128.
\]

Khi gặp byte có bit cao 0, ta biết đã đọc đủ mọi nhóm 7 bit của số hiện tại.

### Điều kiện kết thúc

Luồng `00` biểu diễn **số 0** hợp lệ. Một luồng **rỗng** không phải một mã cho 0; nó là **không có số nào để đọc**.

Luồng `80` là **mã bị cắt ngang**. Bit cao của byte đầu yêu cầu phải có byte tiếp theo nhưng đầu vào đã hết.

Luồng `80 00` có thể cho cùng giá trị toán học với `00` nếu bộ giải mã chấp nhận mã dài không cần thiết. Tuy nhiên, nó **không canonical**. Một bộ giải mã nghiêm ngặt nên từ chối nó để tránh nhiều biểu diễn khác nhau cho cùng một số.

## 8. Mã canonical và lỗi dữ liệu đầu vào

**Mã canonical** nghĩa là mỗi giá trị có **một biểu diễn hợp lệ duy nhất**, thường là biểu diễn ngắn nhất.

Với ULEB128, các quy tắc chính:

- 0 được viết bằng đúng `00`.
- Không ghi thêm nhóm 7 bit cao bằng 0 không cần thiết.
- Mọi byte trừ byte cuối có continuation bit bằng 1.
- Byte cuối có continuation bit bằng 0.
- Số byte và payload phải nằm trong giới hạn của kiểu số được chọn.

### Các tình huống cần xử lý

| Byte đầu vào | Kết quả mong muốn với bộ giải mã uint64 nghiêm ngặt |
|---|---|
| `00` | Hợp lệ, trả 0 |
| `7F` | Hợp lệ, trả 127 |
| `80 01` | Hợp lệ, trả 128 |
| `AC 02` | Hợp lệ, trả 300 |
| `80` | Lỗi **truncated** |
| `80 00` | Lỗi **non-canonical / overlong** |
| `81 00` | Lỗi **non-canonical / overlong** |
| `FF ... FF 02` với 10 byte | Lỗi **tràn uint64** |
| 10 byte đều có bit cao 1 | Lỗi **quá dài/chưa kết thúc** |
| Luồng rỗng khi yêu cầu giải một số | Lỗi không có byte để đọc |

Không phải mọi API đều từ chối overlong; một số bộ giải mã chỉ kiểm tra giá trị kết quả. Với dữ liệu không tin cậy, định dạng nên có quy ước rõ để tránh **mã hóa không duy nhất**, lỗi tương thích, đọc quá biên hoặc cơ hội gây tiêu hao tài nguyên.

**Đừng đọc vượt phần còn lại của buffer** chỉ vì một byte có bit continuation. Bộ giải mã phải kiểm tra byte kế tiếp tồn tại.

## 9. Python: mã hóa và giải mã uint64 ULEB128 nghiêm ngặt

Mã sau có thể xử lý một số tại vị trí `offset`, trả cả **giá trị và vị trí byte sau mã**. Điều đó cho phép ghép các số vào một luồng.

```python
MAX_U64 = (1 << 64) - 1


def encode_u64(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("Giá trị phải là số nguyên")
    if not 0 <= value <= MAX_U64:
        raise ValueError("Giá trị ngoài miền uint64")

    out = bytearray()
    while value >= 128:
        out.append((value & 0x7F) | 0x80)
        value >>= 7

    out.append(value)
    return bytes(out)


def decode_u64(
    data: bytes | bytearray, offset: int = 0
) -> tuple[int, int]:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data phải là bytes hoặc bytearray")
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise TypeError("offset phải là số nguyên")
    if not 0 <= offset <= len(data):
        raise ValueError("offset ngoài phạm vi")

    result = 0

    for group in range(10):  # uint64 cần tối đa 10 byte.
        at = offset + group
        if at >= len(data):
            raise ValueError("Mã ULEB128 bị cắt ngang")

        byte = data[at]
        payload = byte & 0x7F

        # Sau 9 nhóm có 63 bit. Byte thứ 10 chỉ
        # được mang 0 hoặc 1, và không được tiếp diễn.
        if group == 9 and byte > 1:
            raise ValueError("Mã vượt miền uint64")

        result |= payload << (7 * group)

        if (byte & 0x80) == 0:
            # Nhóm cao nhất bằng 0 là không canonical
            # nếu trước đó đã dùng byte khác.
            if group > 0 and payload == 0:
                raise ValueError("Mã overlong, không canonical")

            return result, at + 1

    raise ValueError("Mã quá dài")


def decode_all_u64(data: bytes) -> list[int]:
    result = []
    offset = 0

    while offset < len(data):
        number, offset = decode_u64(data, offset)
        result.append(number)

    return result


examples = [0, 1, 127, 128, 255, 300, 16383, 16384]
encoded = b"".join(encode_u64(x) for x in examples)

assert decode_all_u64(encoded) == examples
assert encode_u64(300) == bytes.fromhex("AC 02")
assert encode_u64(16384) == bytes.fromhex("80 80 01")

number, next_offset = decode_u64(bytes.fromhex("7F AC 02"), 1)
assert number == 300 and next_offset == 3

# Biên chính xác 64 bit.
assert decode_u64(encode_u64(MAX_U64))[0] == MAX_U64
assert len(encode_u64(MAX_U64)) == 10

for malformed in [
    bytes.fromhex("80"),        # Còn thiếu byte kết thúc.
    bytes.fromhex("80 00"),     # Overlong cho 0.
    bytes.fromhex("81 00"),     # Overlong cho 1.
    bytes.fromhex("FF FF FF FF FF FF FF FF FF 02"),
]:
    try:
        decode_u64(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError("Đã chấp nhận một mã lỗi")
```

### Vì sao không dùng vòng lặp vô hạn?

Mã đọc tối đa 10 nhóm cho `uint64`. Nếu đầu vào cố tình chứa hàng triệu byte `0x80`, bộ giải mã **không** được quét vô hạn trước khi báo lỗi. Chặn độ dài là một phần bảo vệ an toàn khi đọc file, mạng hoặc dữ liệu từ bên ngoài.

### Độ phức tạp

Gọi `L` là số byte của mã:

- `encode_u64`: `Θ(L)` bước, tạo đúng L byte.
- `decode_u64`: `Θ(L)` bước nếu hợp lệ, và **tối đa 10 byte** trong thiết kế giới hạn uint64.
- Với uint64, `L≤10` nên trên mô hình từ máy cố định có thể xem là `O(1)`.
- Với số nguyên có độ chính xác tùy ý, L tăng theo số bit của giá trị, và chi phí phép toán số nguyên lớn cũng cần được tính.

**Không dùng giới hạn 10 byte** nếu định dạng thực tế cho phép số nguyên dài hơn 64 bit mà không thay hợp đồng.

## 10. Kích thước luồng varint và cách so với fixed width

Với dãy `x_0,\ldots,x_{n-1}`, tổng byte ULEB128 là:

\[
\boxed{
B_{\mathrm{varint}}
=\sum_{i=0}^{n-1}L(x_i).
}
\]

Nếu mỗi số dùng `w` bit cố định và w chia hết cho 8:

\[
B_{\mathrm{fixed}}
=n\cdot\frac{w}{8}.
\]

### Ví dụ các số nhỏ

Dãy:

```text
[1, 5, 20, 127, 100, 0]
```

Mọi giá trị đều nhỏ hơn 128, nên varint cần **6 byte**. Với `uint32`, dãy cần **24 byte**. Trong phạm vi chỉ xét payload, varint tiết kiệm 75%.

### Ví dụ varint lại lớn hơn

Dãy:

```text
[128, 200, 255]
```

Mỗi giá trị dùng **2 byte ULEB128**, tổng **6 byte**. Nếu miền đã biết là `0..255`, ba byte `uint8` chỉ cần **3 byte**.

**Kết luận:** mã độ dài thay đổi không đồng nghĩa luôn tiết kiệm. Nó giúp khi dữ liệu có **nhiều số đủ nhỏ** so với kiểu fixed-width đang dùng.

### Overhead bên ngoài luồng

Một file thực có thể còn:

- Số phần tử hoặc kích thước luồng.
- ID phiên bản định dạng, schema và phương pháp mã hóa.
- Offset tới từng block để truy cập ngẫu nhiên.
- Checksum hoặc metadata kiểm tra dữ liệu.
- Padding và alignment của block/buffer.

Khi so sánh tổng bộ nhớ, phải cộng các phần đó; bảng “số byte varint” thường chỉ mô tả **payload**.

## 11. Giá trị âm: không dùng ULEB128 trực tiếp

ULEB128 là mã **không dấu**. Với số âm như `−1`, thao tác dịch trên số có dấu và gán vào các nhóm 7 bit phải tuân theo **một quy tắc riêng**.

Không nên làm:

```text
encode_uvarint(-1)
```

mà không có hợp đồng. Một số ngôn ngữ dịch phải số âm theo cách giữ bit dấu, có thể khiến vòng lặp không kết thúc như mong muốn; ép một `int64` âm thành `uint64` rồi mã hóa sẽ biến `−1` thành `2^64−1`, cần **10 byte**.

Có hai họ giải pháp thông dụng nhưng **khác nhau**:

1. **SLEB128 (signed LEB128):** mã có dấu, dùng quy tắc dừng dựa trên việc bit dấu đã được mở rộng đúng.
2. **ZigZag + ULEB128:** đổi số có dấu thành số không dấu, rồi dùng ULEB128 đã định nghĩa.

Bài này triển khai **ZigZag + ULEB128** vì dễ giải thích, đơn giản và đặc biệt phù hợp khi số âm/dương nhỏ xuất hiện nhiều.

## 12. ZigZag: cho các số gần 0 có mã gần 0

ZigZag ánh xạ:

```text
 0 → 0
-1 → 1
 1 → 2
-2 → 3
 2 → 4
-3 → 5
 3 → 6
...
```

Công thức toán học:

\[
Z(x)=
\begin{cases}
2x,&x\ge0,\\
-2x-1,&x<0.
\end{cases}
\]

Hàm nghịch đảo:

\[
Z^{-1}(u)=
\begin{cases}
u/2,&u\text{ chẵn},\\
-(u+1)/2,&u\text{ lẻ}.
\end{cases}
\]

**Tại sao hữu ích?** Những số có trị tuyệt đối nhỏ, dù âm hay dương, được chuyển thành **giá trị không dấu nhỏ**. ULEB128 sẽ dùng một byte cho các giá trị không dấu `0..127`.

### Bảng giá trị

| Số có dấu x | ZigZag Z(x) | Byte ULEB128 |
|---:|---:|---|
| 0 | 0 | `00` |
| −1 | 1 | `01` |
| 1 | 2 | `02` |
| −2 | 3 | `03` |
| 2 | 4 | `04` |
| −3 | 5 | `05` |
| 63 | 126 | `7E` |
| −64 | 127 | `7F` |
| 64 | 128 | `80 01` |
| −65 | 129 | `81 01` |

Như vậy mọi số nguyên có dấu trong `[−64,63]` được mã hóa bằng **một byte** theo ZigZag+ULEB128.

### ZigZag khác SLEB128

Với số `−1`:

- ZigZag+ULEB128: `01`.
- SLEB128 điển hình: `7F`.

Cả hai là một byte, nhưng **byte khác nhau**. Bộ giải mã của định dạng này không thể thay thế bộ giải mã của định dạng kia nếu giao thức không ghi rõ.

## 13. Python: ZigZag cho miền signed 64 bit

Với `int64` có miền:

\[
-2^{63}\le x\le2^{63}-1,
\]

ZigZag ánh xạ chính xác sang:

\[
0\le Z(x)\le2^{64}-1.
\]

Mã dưới dùng phép toán số nguyên Python để tránh phụ thuộc hành vi dịch phải trên số nguyên âm trong các ngôn ngữ khác.

```python
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1


def zigzag_encode_i64(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("Phải là số nguyên")
    if not MIN_I64 <= value <= MAX_I64:
        raise ValueError("Giá trị ngoài miền int64")

    return 2 * value if value >= 0 else -2 * value - 1


def zigzag_decode_i64(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("Phải là số nguyên")
    if not 0 <= value <= MAX_U64:
        raise ValueError("Giá trị ngoài miền uint64")

    return (value >> 1) if (value & 1) == 0 else -((value >> 1) + 1)


def encode_i64(value: int) -> bytes:
    return encode_u64(zigzag_encode_i64(value))


def decode_i64(
    data: bytes | bytearray, offset: int = 0
) -> tuple[int, int]:
    unsigned, next_offset = decode_u64(data, offset)
    return zigzag_decode_i64(unsigned), next_offset


for number in [0, -1, 1, -2, 2, -64, 63, 64, -65]:
    encoded = encode_i64(number)
    decoded, end = decode_i64(encoded)
    assert decoded == number and end == len(encoded)

assert encode_i64(-1) == b"\x01"
assert encode_i64(-64) == b"\x7f"
assert encode_i64(64) == bytes.fromhex("80 01")
assert decode_i64(encode_i64(MIN_I64))[0] == MIN_I64
assert decode_i64(encode_i64(MAX_I64))[0] == MAX_I64
assert len(encode_i64(MIN_I64)) == 10
```

### Biên âm nhỏ nhất

Trong một số ngôn ngữ, tính trực tiếp `-INT64_MIN` có thể **tràn số nguyên có dấu** vì trị tuyệt đối `2^63` không nằm trong miền `int64` dương. Python không gặp lỗi đó do số nguyên tùy ý, nhưng khi chuyển công thức sang C++ cần dùng số học **không dấu** hoặc kiểm tra giới hạn cẩn thận.

## 14. C++17: ULEB128 và ZigZag an toàn cho 64 bit

Mã dưới dùng `std::uint64_t` để ghép các bit. Khi mã hóa ZigZag, nó chuyển số có dấu sang số không dấu trước khi dịch, tránh tràn số nguyên có dấu khi xử lý `INT64_MIN`.

```cpp
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

std::vector<std::uint8_t> encode_u64(std::uint64_t x) {
    std::vector<std::uint8_t> out;

    while (x >= 128) {
        out.push_back(static_cast<std::uint8_t>(
            (x & 0x7FULL) | 0x80ULL
        ));
        x >>= 7;
    }

    out.push_back(static_cast<std::uint8_t>(x));
    return out;
}

std::pair<std::uint64_t, std::size_t> decode_u64(
    const std::vector<std::uint8_t>& data,
    std::size_t offset = 0
) {
    std::uint64_t result = 0;

    for (unsigned group = 0; group < 10; ++group) {
        if (offset >= data.size()) {
            throw std::invalid_argument("Truncated varint");
        }

        const std::uint8_t byte = data[offset++];

        // Byte thứ 10 chỉ được là 0 hoặc 1.
        if (group == 9 && byte > 1) {
            throw std::invalid_argument("uint64 overflow");
        }

        const std::uint64_t payload = byte & 0x7FU;
        result |= payload << (7 * group);

        if ((byte & 0x80U) == 0) {
            if (group > 0 && payload == 0) {
                throw std::invalid_argument("Overlong varint");
            }
            return {result, offset};
        }
    }

    throw std::invalid_argument("Varint too long");
}

std::uint64_t zigzag_encode(std::int64_t value) {
    const std::uint64_t u =
        static_cast<std::uint64_t>(value);

    const std::uint64_t sign_mask = value < 0
        ? std::numeric_limits<std::uint64_t>::max()
        : std::uint64_t{0};

    return (u << 1) ^ sign_mask;
}

std::int64_t zigzag_decode(std::uint64_t value) {
    const std::int64_t half =
        static_cast<std::int64_t>(value >> 1);

    // half nằm trong [0, INT64_MAX], chuyển kiểu an toàn.
    if ((value & 1U) == 0) {
        return half;
    }
    return -half - 1;  // Xử lý được cả INT64_MIN.
}

int main() {
    for (std::uint64_t x :
         {0ULL, 127ULL, 128ULL, 300ULL, 16384ULL}) {
        const auto bytes = encode_u64(x);
        const auto decoded = decode_u64(bytes);
        assert(decoded.first == x);
        assert(decoded.second == bytes.size());
    }

    const auto max_u64 =
        std::numeric_limits<std::uint64_t>::max();
    assert(decode_u64(encode_u64(max_u64)).first == max_u64);
    assert(encode_u64(max_u64).size() == 10);

    for (std::int64_t x :
         {0LL, -1LL, 1LL, -64LL, 63LL, 64LL}) {
        const std::uint64_t u = zigzag_encode(x);
        assert(zigzag_decode(u) == x);
    }

    const auto min_i64 =
        std::numeric_limits<std::int64_t>::min();
    assert(zigzag_decode(zigzag_encode(min_i64)) == min_i64);

    std::cout << "ULEB128 and ZigZag OK\n";
}
```

### Những điểm cài đặt dễ bỏ sót

- `payload << (7*group)` chỉ an toàn khi shift hợp lệ. Vòng lặp có `group≤9`, nên shift tối đa 63.
- Ở nhóm thứ 10, byte có thể là `01` nếu số đạt bit 63. Giá trị từ `02` trở lên là tràn hoặc mã sai.
- Trả về **offset mới** để có thể giải mã tiếp số kế tiếp trong buffer.
- Nếu cần tương thích với một định dạng cụ thể, cả hai bên phải thống nhất quy tắc **canonical, kích thước 64 bit và ZigZag**.
- Bộ mã hóa ZigZag không dùng `-value` trên số âm trong C++, tránh lỗi với `INT64_MIN`.
- `std::vector<std::uint8_t>` có overhead container và capacity; kích thước payload mã hóa là `bytes.size()`, không phải toàn bộ heap đã cấp phát.

## 15. Delta encoding là gì?

**Mã hóa chênh lệch** không mã hóa trực tiếp mỗi phần tử, mà lưu **mức thay đổi so với phần tử trước**.

Với dãy:

\[
x_0,x_1,\ldots,x_{n-1},
\]

chọn mốc `x_{-1}=0` rồi đặt:

\[
\boxed{
d_0=x_0,\qquad
d_i=x_i-x_{i-1}\quad(i\ge1).
}
\]

Dãy gốc được khôi phục bằng **tổng tiền tố**:

\[
\boxed{
x_i=\sum_{j=0}^{i}d_j.
}
\]

Nếu dãy ban đầu **không giảm** và tất cả `x_i≥0`, ta có `d_i≥0`. Khi ấy các delta có thể được mã hóa trực tiếp bằng **unsigned varint**.

### Ví dụ nhỏ

```text
Giá trị gốc:
100, 103, 103, 130, 500

Delta:
100, 3, 0, 27, 370

Khôi phục:
100
100+3 = 103
103+0 = 103
103+27 = 130
130+370 = 500
```

Lưu ý `delta=0` là **hợp lệ khi hai giá trị liên tiếp bằng nhau**. Nếu dãy **tăng nghiêm ngặt**, mọi delta từ `d_1` trở đi phải dương.

**Delta encoding không tự giảm số bit.** Nó chỉ biến dữ liệu sang một dạng có thể chứa nhiều **số nhỏ hơn**, thuận tiện cho bước mã hóa tiếp theo như varint, bit packing hoặc mã entropy.

## 16. Vì sao dãy đã sắp xếp thường nén tốt bằng delta?

Với danh sách ID đã sắp xếp:

```text
1000, 1004, 1011, 1011, 1020, 1100
```

Delta với mốc 0:

```text
1000, 4, 7, 0, 9, 80
```

Ta dùng unsigned ULEB128:

| Vị trí | ID gốc | Delta | ULEB128 của ID | ULEB128 của delta |
|---:|---:|---:|---|---|
| 0 | 1.000 | 1.000 | `E8 07` | `E8 07` |
| 1 | 1.004 | 4 | `EC 07` | `04` |
| 2 | 1.011 | 7 | `F3 07` | `07` |
| 3 | 1.011 | 0 | `F3 07` | `00` |
| 4 | 1.020 | 9 | `FC 07` | `09` |
| 5 | 1.100 | 80 | `CC 08` | `50` |

Luồng mã hóa delta:

```text
E8 07 04 07 00 09 50
```

Tổng **7 byte**, trong khi mã hóa trực tiếp sáu ID bằng ULEB128 cần **12 byte**. Lưu bằng `uint32` cần **24 byte** payload.

**So sánh payload, chưa tính metadata:**

| Biểu diễn | Số byte |
|---|---:|
| 6 ID dưới dạng `uint32` | 24 |
| 6 ID ULEB128 trực tiếp | 12 |
| 6 delta ULEB128 | 7 |
| 6 trường 11 bit đóng gói (ID tối đa 1.100) | `⌈66/8⌉=9` |

Với đúng dãy này, delta+varint là cách nhỏ nhất trong bốn phương án vừa so. Nhưng **không** được suy rằng nó luôn nhỏ nhất cho mọi dãy.

### Vì sao số đầu còn dùng hai byte?

Vì ta chọn mốc `0`, nên `d_0=x_0=1000`. Nó không phải khoảng cách tới một ID trước đó gần hơn.

Nếu có **mốc chung của block** như 1.000 được lưu ở header, ta có thể mã hóa offset từ mốc ấy, nhưng phải **cộng chi phí header** khi so tổng bộ nhớ.

## 17. Bất biến của delta trên dãy không giảm

Để dùng **unsigned** delta, quy tắc tối thiểu là:

\[
0\le x_0\le x_1\le\cdots\le x_{n-1}.
\]

Khi đó:

- `d_0=x_0≥0`.
- `d_i=x_i−x_{i−1}≥0` với `i≥1`.
- Tổng tiền tố của các delta luôn bằng phần tử gốc tương ứng.
- Nếu mỗi `x_i≤M`, tổng tiền tố khi giải mã cũng không được vượt M.

### Khác với dãy tăng nghiêm ngặt

Dãy **không giảm** cho phép trùng:

```text
[10, 10, 11]
delta = [10, 0, 1]
```

Dãy **tăng nghiêm ngặt** không cho trùng:

```text
[10, 11, 13]
delta = [10, 1, 2]
```

Nếu định dạng biết chắc các phần tử tăng nghiêm ngặt, có thể mã hóa `gap−1` cho các khoảng từ phần tử thứ hai trở đi. Điều đó khiến khoảng cách 1 được mã hóa thành 0. Nhưng khi giải mã phải **cộng lại 1**, đồng thời phải định nghĩa quy tắc riêng cho phần tử đầu.

**Không áp `gap−1` cho dãy có trùng**, vì một delta bằng 0 sẽ thành `−1` và không thể mã hóa như số không dấu.

## 18. Python: mã hóa và giải mã dãy delta ULEB128

Đoạn mã sau dùng lại `encode_u64` và `decode_u64` ở phần 9. Nó chấp nhận dãy các giá trị `uint64` **không giảm**, mốc ban đầu bằng 0.

```python
def encode_deltas(values: list[int]) -> bytes:
    previous = 0
    out = bytearray()

    for value in values:
        # encode_u64 kiểm tra kiểu và miền uint64.
        encode_u64(value)

        if value < previous:
            raise ValueError("Dãy phải không giảm")

        gap = value - previous
        out.extend(encode_u64(gap))
        previous = value

    return bytes(out)


def decode_deltas(
    data: bytes | bytearray,
    expected_count: int | None = None,
) -> list[int]:
    if expected_count is not None:
        if (
            not isinstance(expected_count, int)
            or isinstance(expected_count, bool)
            or expected_count < 0
        ):
            raise ValueError("expected_count phải không âm")

    previous = 0
    result = []
    offset = 0

    while offset < len(data):
        gap, offset = decode_u64(data, offset)

        # Chống tràn uint64 khi cộng prefix sum.
        if gap > MAX_U64 - previous:
            raise ValueError("Prefix sum vượt uint64")

        previous += gap
        result.append(previous)

        if (
            expected_count is not None
            and len(result) > expected_count
        ):
            raise ValueError("Có nhiều phần tử hơn dự kiến")

    if (
        expected_count is not None
        and len(result) != expected_count
    ):
        raise ValueError("Số lượng phần tử không khớp")

    return result


ids = [1000, 1004, 1011, 1011, 1020, 1100]
payload = encode_deltas(ids)

assert payload == bytes.fromhex("E8 07 04 07 00 09 50")
assert len(payload) == 7
assert decode_deltas(payload, expected_count=6) == ids

assert encode_deltas([]) == b""
assert decode_deltas(b"", expected_count=0) == []
assert decode_deltas(encode_deltas([0, 0])) == [0, 0]

for wrong in [
    [10, 9],                 # Không tăng.
    [0, -1],                 # Số âm.
    [0, (1 << 64)],          # Vượt uint64.
]:
    try:
        encode_deltas(wrong)
    except ValueError:
        pass
    else:
        raise AssertionError("Phải từ chối dữ liệu sai")
```

### Giải mã tại sao không cần toàn bộ mảng trước?

Vì mỗi delta hoàn thành tại một byte có continuation bit bằng 0, bộ giải mã có thể:

1. Đọc một varint.
2. Cộng vào giá trị trước.
3. Trả phần tử vừa giải mã.
4. Lặp tiếp.

Đây là một quy trình **streaming**. Nếu ứng dụng cần trả từng phần tử ngay, có thể viết generator để tránh tạo mảng kết quả toàn bộ.

### Cần biết số phần tử không?

Nếu luồng bytes chỉ chứa **một dãy delta** và ranh giới luồng đã biết, có thể giải mã cho tới hết byte. Nhưng nếu file gồm **nhiều block hoặc nhiều trường**, cần framing: số phần tử, số byte, offset cuối block hoặc thông tin giao thức tương đương.

Với `expected_count`, ví dụ còn kiểm tra số phần tử giải mã đúng như metadata, giúp phát hiện việc đọc thiếu hoặc thừa dữ liệu.

## 19. Nếu dãy chưa sắp xếp thì sao?

Xét dãy không đơn điệu:

```text
[100, 105, 98, 103]
```

Delta với mốc đầu bằng 0:

```text
[100, +5, -7, +5]
```

Hai delta âm/dương không thể được mã hóa trực tiếp bằng ULEB128. Một cách giải quyết là:

- Mã hóa **giá trị đầu** bằng một định dạng có dấu hoặc lưu anchor phù hợp.
- Áp **ZigZag** lên các delta có dấu.
- Mã hóa kết quả ZigZag bằng ULEB128.

Với ví dụ trên, nếu coi mọi delta đều có dấu trong miền `int64`:

```text
Delta:  [100, 5, -7, 5]
ZigZag: [200, 10, 13, 10]
ULEB:   [C8 01, 0A, 0D, 0A]
```

Payload tổng là **5 byte**. Điều này có thể hữu ích nếu dãy dao động nhỏ quanh một mốc tương đối ổn định.

### Chú ý đến tràn khi trừ hai số nguyên có dấu

Với hai giá trị `int64` hợp lệ, hiệu `x_i−x_{i−1}` **không nhất thiết** nằm trong `int64`. Ví dụ:

\[
(2^{63}-1)-(-2^{63})=2^{64}-1.
\]

Hiệu này vượt `INT64_MAX`. Nếu định dạng dùng ZigZag 64 bit cho delta, phải **giới hạn khoảng chênh lệch**, dùng kiểu rộng hơn hoặc thiết kế mã hóa khác.

Không được phép trừ hai `int64_t` trong C++ rồi mới kiểm tra overflow, vì phép trừ có thể đã gây hành vi không xác định.

## 20. Delta encoding không phải lúc nào cũng nén tốt

Delta giúp khi chênh lệch thường **nhỏ hơn các giá trị gốc**. Điều đó không luôn xảy ra.

### Trường hợp khoảng cách lớn

Dãy:

```text
[100, 1000000000, 2000000000]
```

Delta:

```text
[100, 999999900, 1000000000]
```

Hai delta sau vẫn rất lớn, nên có thể cần nhiều byte ULEB128. Mức tiết kiệm so với mã hóa trực tiếp hoặc fixed-width có thể không đáng kể.

### Trường hợp số nhỏ nhưng dao động mạnh

Dãy:

```text
[0, 127, 0, 127, 0]
```

Mã hóa trực tiếp unsigned ULEB128 chỉ cần **5 byte** (mỗi số một byte).

Delta:

```text
[0, +127, -127, +127, -127]
```

Nếu dùng ZigZag cho mọi delta:

```text
[0, 254, 253, 254, 253]
```

Các giá trị `253` và `254` cần hai byte ULEB128, tổng:

\[
1+2+2+2+2=9\text{ byte}.
\]

**Delta+ZigZag+varint ở đây tệ hơn trực tiếp varint.**

Điều quan trọng là chọn biến đổi theo **quy luật dữ liệu**, không phải cứ áp nhiều lớp mã hóa là chắc chắn nhỏ hơn.

### Trường hợp dữ liệu đã tối ưu fixed-width

Nếu mọi giá trị trong `0..255` và truy cập ngẫu nhiên thường xuyên, mảng byte có thể vừa nhỏ vừa nhanh. Varint có thể tăng chi phí vì nửa trên miền `128..255` dùng hai byte.

## 21. Delta-of-delta: mã hóa thay đổi của khoảng cách

Trong dữ liệu thời gian hoặc chuỗi chỉ số gần đều, bản thân các delta có thể gần nhau.

Cho dãy:

```text
100, 110, 120, 130, 140
```

Delta với mốc ban đầu 0:

```text
100, 10, 10, 10, 10
```

Nếu tiếp tục lấy chênh lệch của các khoảng liên tiếp:

```text
delta-of-delta:
100, 10, 0, 0, 0
```

Một cách định nghĩa rõ ràng:

\[
d_0=x_0,\quad
d_i=x_i-x_{i-1}\;(i\ge1),
\]

và:

\[
e_0=d_0,\quad
e_i=d_i-d_{i-1}\;(i\ge1).
\]

Sau đó mã hóa `e_i` bằng **một mã cho số có dấu**, chẳng hạn ZigZag+ULEB128, hoặc một mã đặc biệt tối ưu cho nhiều giá trị 0.

### Dùng cho dữ liệu thời gian

Nếu các dấu thời gian tăng gần đều mỗi 100 mili giây:

```text
1000, 1100, 1200, 1301, 1401
```

thì:

```text
Delta:          1000, 100, 100, 101, 100
Delta-of-delta: 1000, -900, 0, 1, -1
```

Phần tử đầu gây một khoảng bất thường vì mốc `0`. Một định dạng thực tế thường **lưu timestamp gốc và delta đầu tiên dưới dạng anchor**, rồi mới mã hóa những delta-of-delta về sau; như vậy chuỗi phần lớn có giá trị gần 0.

**Không nhầm delta-of-delta với delta thông thường.** Bộ giải mã cần **hai biến trạng thái**: giá trị trước và delta trước.

## 22. Delta-of-delta và dữ liệu đã biết mốc

Khi có một mốc ngoài luồng, ví dụ:

```text
base = 1000
interval = 100
```

dãy:

```text
1000, 1100, 1200, 1301, 1401
```

có thể biểu diễn bằng các sai lệch so với mô hình:

```text
index:             0    1    2    3    4
expected:        1000 1100 1200 1300 1400
actual:          1000 1100 1200 1301 1401
residual:           0    0    0    1    1
```

Các residual nhỏ có thể được mã hóa gọn. Tuy nhiên, **base** và **interval** là metadata bắt buộc để giải mã đúng.

Đây là một nhắc nhở quan trọng: nhiều kỹ thuật “nén delta” thực chất là **chọn mô hình dự đoán** rồi lưu **sai lệch**. Tổng chi phí phải bao gồm thông tin mô hình.

### Chọn mô hình có phù hợp không?

- Dữ liệu gần như không đổi: delta nhỏ.
- Dữ liệu gần tuyến tính theo thời gian: delta-of-delta hoặc residual theo xu hướng có thể nhỏ.
- Dữ liệu không có tương quan: cả hai phép biến đổi có thể không giúp.
- Dữ liệu có nhiều chuỗi giá trị bằng nhau: run-length encoding có thể tốt.

Không có một biến đổi duy nhất tối ưu với mọi phân phối.

## 23. Mã theo block và frame of reference

Thay vì mã hóa từng giá trị độc lập trên toàn bộ dãy, ta có thể chia thành **block** có kích thước cố định hoặc gần cố định.

Với một block có giá trị không giảm:

```text
[1000, 1002, 1005, 1007]
```

Lấy **base=1000**:

```text
offsets = [0, 2, 5, 7]
```

Offset lớn nhất là 7, nên mỗi offset chỉ cần **3 bit** nếu đóng gói theo độ rộng cố định. Payload offset:

\[
4\cdot3=12\text{ bit},
\]

cần 2 byte sau làm tròn theo byte, **cộng chi phí lưu base và metadata**.

Cách này gọi chung là **frame of reference (FOR)**.

### FOR khác delta tuần tự

- **Delta tuần tự:** phần tử i được khôi phục từ giá trị i−1 và gap.
- **FOR:** phần tử i được khôi phục từ cùng một base của block và offset thứ i.
- FOR có thể cho **truy cập cục bộ thuận tiện hơn** vì không cần cộng tất cả gap phía trước, miễn đã biết vị trí offset và độ rộng bit.

### Chọn độ rộng block

Block quá lớn:

- Có thể xuất hiện một offset lớn, buộc mọi trường dùng nhiều bit.
- Có thể làm giảm hiệu quả nếu các giá trị trải rộng.

Block quá nhỏ:

- Mỗi block phải lưu base, độ rộng, số lượng và có thể cả offset/index.
- Metadata chiếm tỷ lệ lớn.

Kích thước block cần được benchmark trên dữ liệu thực tế.

## 24. Varint, bit packing, RLE và mã entropy: chọn thế nào?

| Kỹ thuật | Phù hợp khi | Hạn chế chính |
|---|---|---|
| ULEB128 trực tiếp | Nhiều giá trị nhỏ; luồng thêm dần | Mỗi số tối thiểu 1 byte, branch/đọc tuần tự |
| ZigZag+ULEB128 | Số có dấu quanh 0 | Giá trị lớn vẫn dùng nhiều byte |
| Delta+ULEB128 | Dãy số không giảm, khoảng cách nhỏ | Truy cập giá trị thứ i cần tổng tiền tố |
| Delta-of-delta | Khoảng cách thay đổi ít | Cần trạng thái khôi phục nhiều mức |
| Frame of reference + bit packing | Block có miền offset hẹp | Header và độ rộng block |
| Run-length encoding (RLE) | Nhiều giá trị lặp liên tiếp | Dữ liệu không lặp có thể phình |
| Mã entropy/prefix | Phân phối ký hiệu lệch rõ | Cần từ điển/bảng mã, giải mã phức tạp |
| Mảng fixed-width | Miền hẹp, truy cập ngẫu nhiên nhiều | Có thể dư bit nếu chọn kiểu quá rộng |

### RLE và delta có thể kết hợp

Nếu một dãy không giảm có nhiều phần tử trùng:

```text
[10,10,10,10,15,15,20]
```

Delta:

```text
[10,0,0,0,5,0,5]
```

Dãy delta chứa nhiều số 0 liên tiếp. Ta có thể **RLE các số 0**, lưu cặp như “0 lặp 3 lần”. Nhưng phải cộng số byte để lưu kiểu run và độ dài run. Với run rất ngắn, RLE có thể lớn hơn.

**Đo payload hoàn chỉnh thay vì đánh giá chỉ từ việc có nhiều số 0.**

## 25. Truy cập ngẫu nhiên: mặt trái của chuỗi delta

Mảng fixed-width có thể lấy phần tử thứ i mà không giải mã phần tử trước:

```text
address(i) = base + i * item_width
```

Với varint, các mã có độ dài khác nhau, nên **offset byte của phần tử thứ i** không bằng `i·constant`. Nếu không có chỉ mục, cần quét từ đầu để tìm ranh giới các số.

Với delta, còn có phụ thuộc giá trị:

\[
x_i=d_0+d_1+\cdots+d_i.
\]

Vì vậy khi hỏi “ID thứ 900.000 là gì?”, nếu chỉ có một luồng delta varint duy nhất, ta có thể phải giải mã **toàn bộ 900.001 delta đầu**.

### Chỉ mục checkpoint

Một cách giải quyết là lưu **mốc khôi phục định kỳ**, ví dụ mỗi k phần tử:

```text
checkpoint:
    itemIndex
    byteOffset
    previousAbsoluteValue
```

Khi truy cập vị trí i:

1. Tìm checkpoint có `itemIndex≤i` gần nhất.
2. Nhảy tới `byteOffset` của mốc.
3. Bắt đầu từ `previousAbsoluteValue` đã biết.
4. Giải mã tối đa khoảng k delta để tới i.

Nếu checkpoint được lưu mỗi k phần tử và có bảng chỉ số truy cập trực tiếp, phần giải mã sau checkpoint tốn **`O(k)` số phần tử** trong trường hợp xấu, thay vì `O(n)`.

### Đổi không gian lấy thời gian

Số checkpoint là khoảng:

\[
\left\lceil\frac nk\right\rceil.
\]

Mỗi checkpoint cần lưu ít nhất offset và giá trị khởi đầu, đôi khi cả chỉ số/độ dài. Đặt k nhỏ:

- Tốn nhiều metadata hơn.
- Truy cập ngẫu nhiên nhanh hơn.

Đặt k lớn:

- Ít metadata hơn.
- Phải giải mã nhiều delta khi truy cập ngẫu nhiên.

Đây là một đánh đổi điển hình của **cấu trúc dữ liệu gọn**, không chỉ của thuật toán mã hóa.

## 26. Cập nhật, chèn và xóa phần tử trong luồng nén

Khi một phần tử được cập nhật, số byte ULEB128 của nó có thể đổi.

Ví dụ:

```text
127 → 7F       (1 byte)
128 → 80 01    (2 byte)
```

Thay 127 bằng 128 trong một luồng nối sát các mã có thể **làm dịch offset của mọi mã phía sau**, nếu lưu trong một buffer liên tục.

### Thay giá trị trong dãy delta còn khó hơn

Với:

```text
x = [100,105,110]
d = [100,5,5]
```

Nếu đổi phần tử giữa từ 105 thành 108, giữ các giá trị khác:

```text
x' = [100,108,110]
d' = [100,8,2]
```

Phải sửa **ít nhất hai delta lân cận**. Nếu chỉnh sửa khiến dãy mất thứ tự, định dạng unsigned delta không còn hợp lệ.

Khi chèn hoặc xóa phần tử giữa dãy, phải cập nhật gap liên quan, ranh giới byte và có thể cả checkpoint của những phần tử phía sau.

### Các cách hạn chế chi phí cập nhật

- Lưu theo **block độc lập** để chỉ viết lại block liên quan.
- Dành **capacity trống** hoặc dùng buffer linh hoạt.
- Dùng cấu trúc cây/chỉ mục để quản lý block hoặc độ dài biến thiên.
- Nếu dữ liệu chủ yếu **append-only**, giữ một buffer cuối có thể ghi thêm.
- Nếu dữ liệu thay đổi liên tục theo vị trí, cân nhắc fixed-width hoặc cấu trúc khác thay vì một luồng delta dài.

Chặn dung lượng tốt không tự bảo đảm cập nhật `O(1)`.

## 27. Chi phí giải mã theo byte, block và bộ nhớ

Với n số unsigned ULEB128:

\[
B=\sum_{i=0}^{n-1}L(x_i)
\]

là số byte của luồng mã hóa, không tính metadata.

### Mã hóa/giải mã toàn bộ

Mỗi byte được xử lý một lần trong bộ mã/giải mã tuần tự. Do đó:

\[
T_{\mathrm{encode}}=\Theta(B),\qquad
T_{\mathrm{decode}}=\Theta(B)
\]

trên mô hình mỗi byte/từ máy xử lý trong thời gian hằng số, không tính phân bổ bộ nhớ và phép toán big integer nếu dùng số nguyên tùy ý.

Với giới hạn `uint64`, `1≤L(x_i)≤10`, nên:

\[
n\le B\le10n
\]

với n số được mã hóa độc lập.

### Bất biến delta

Trong mã hóa delta của n số không giảm, số delta vẫn là n:

\[
d_0=x_0,\qquad d_i=x_i-x_{i-1}.
\]

Payload cũng thỏa:

\[
B_{\mathrm{delta}}
=\sum_{i=0}^{n-1}L(d_i).
\]

Phép tạo/chuyển đổi delta dùng `O(n)` phép trừ/cộng; trong môi trường `uint64`, chi phí đó không thay đổi bậc `Θ(B)` của toàn luồng (vì `B≥n`).

### Giải mã một phần tử bất kỳ

Không có checkpoint:

- Tìm byte đầu của số thứ i có thể tốn `O(i)` số mã.
- Khôi phục `x_i` của luồng delta cũng cần cộng các delta từ mốc trước tới i.

Có checkpoint mỗi k phần tử:

- Phần giải mã cục bộ tối đa khoảng `O(k)` số.
- Thêm `O(n/k)` bản ghi chỉ mục.

### Bộ nhớ bộ giải mã

Một bộ giải mã streaming chỉ cần trạng thái:

```text
current_varint
shift
previous_absolute
current_offset
```

và có thể trả các phần tử từng cái một, dùng **`O(1)` biến trạng thái** với số nguyên độ rộng cố định. Nếu thu toàn bộ n kết quả vào list/vector, bộ nhớ kết quả là `O(n)` phần tử, **không phải chi phí bắt buộc của định dạng nén**.

## 28. Chặn thông tin và varint có mâu thuẫn không?

Với N trạng thái phân biệt và mã có độ dài cố định, chặn dưới là:

\[
\lceil\log_2 N\rceil\text{ bit}.
\]

Với một số nguyên không dấu trong `0..127`, có N=128 trạng thái nên chỉ cần **7 bit** về mặt thông tin. Nhưng ULEB128 vẫn dùng **8 bit** cho mỗi số nhỏ vì **một bit dùng làm dấu kết thúc**.

Đây không phải mâu thuẫn:

- Chặn thông tin mô tả **khả năng phân biệt trạng thái** dưới giả thiết định dạng/ranh giới thích hợp.
- ULEB128 là một **thiết kế tự phân định mã** theo byte, cần continuation bit và làm tròn theo byte.
- Nó đánh đổi một phần dung lượng để có thể nối nhiều số mà vẫn xác định được **mỗi mã kết thúc ở đâu**.

### Phân phối ảnh hưởng lợi ích trung bình

Nếu 90% số nằm trong `0..127` và 10% số dùng hai byte, kích thước trung bình là:

\[
0{,}9\cdot1+0{,}1\cdot2
=1{,}1\text{ byte/giá trị}.
\]

Tức khoảng 8,8 bit payload/giá trị, chưa tính metadata. Nếu toàn bộ số đều dùng 2 byte, bình quân là 16 bit/giá trị.

Vì vậy cần khảo sát **histogram độ dài mã**, chứ không chỉ xem giá trị lớn nhất hoặc số lượng phần tử.

### Cẩn thận với entropy

Độ dài varint không nhất thiết đạt entropy Shannon của dữ liệu. Các mã theo byte có mốc 7 bit, không tối ưu cho mọi phân phối. Muốn tiến gần entropy hơn, có thể dùng mã entropy hoặc mã theo block, nhưng thường phải trả giá ở giải mã, chỉ mục hoặc khả năng cập nhật.

## 29. Kiểm thử bộ mã hóa và các trường hợp biên

Với mã không mất thông tin, thuộc tính quan trọng nhất là:

\[
\operatorname{decode}(\operatorname{encode}(x))=x.
\]

Với dãy delta:

\[
\operatorname{decodeDeltas}(\operatorname{encodeDeltas}(X))=X
\]

cho mọi X trong miền cho phép.

### Kiểm thử xác định

Những giá trị nên luôn kiểm thử:

```text
0
1
127
128
129
255
16383
16384
2^32 - 1
2^32
2^63 - 1
2^63
2^64 - 1
```

Với ZigZag:

```text
-2^63
-65
-64
-1
0
1
63
64
2^63 - 1
```

Với delta:

```text
[]
[0]
[0,0,0]
[1,1,2,2,3]
[127,128,16383,16384]
[2^64-1,2^64-1]
```

Và những trường hợp phải từ chối:

```text
[-1]                   // Unsigned âm.
[10,9]                 // Không giảm bị vi phạm.
[0,2^64]               // Ngoài uint64.
80                     // Byte continuation nhưng thiếu phần sau.
80 00                  // Mã không canonical.
FF FF FF FF FF FF FF FF FF 02
                       // Nhóm cao vượt 64 bit.
```

### Ví dụ Python kiểm thử round-trip

```python
boundary_values = [
    0, 1, 127, 128, 129, 255, 16383, 16384,
    (1 << 32) - 1, 1 << 32,
    (1 << 63) - 1, 1 << 63, MAX_U64,
]

for x in boundary_values:
    encoded = encode_u64(x)
    decoded, consumed = decode_u64(encoded)
    assert decoded == x
    assert consumed == len(encoded)

for x in [
    MIN_I64, -65, -64, -1, 0, 1, 63, 64, MAX_I64
]:
    decoded, consumed = decode_i64(encode_i64(x))
    assert decoded == x
    assert consumed == len(encode_i64(x))

delta_cases = [
    [], [0], [0, 0, 0], [1, 1, 2, 2, 3],
    [127, 128, 16383, 16384],
    [MAX_U64, MAX_U64],
]
for seq in delta_cases:
    stream = encode_deltas(seq)
    assert decode_deltas(stream, len(seq)) == seq
```

### Vì sao cần kiểm thử dữ liệu hỏng?

Chỉ kiểm tra encode→decode trên dữ liệu hợp lệ **không chứng minh** bộ giải mã xử lý đầu vào bên ngoài an toàn. Cần kiểm thử riêng:

- Chuỗi dừng giữa số.
- Quá 10 byte cho uint64.
- Byte thứ mười sai.
- Mã overlong.
- Offset ngoài buffer.
- Prefix sum tràn giới hạn.
- Header khai báo số phần tử khác số thực tế.

Một bộ mã hóa có thể đúng nhưng bộ giải mã vẫn chứa lỗi đọc ngoài biên hoặc chấp nhận hai mã cho cùng một giá trị.

## 30. Ví dụ ứng dụng trong cấu trúc dữ liệu

### 30.1. Danh sách vị trí trong chỉ mục tìm kiếm

Một từ xuất hiện trong các tài liệu có ID:

```text
[1000, 1004, 1011, 1011, 1020, 1100]
```

Nếu lưu danh sách đã sắp xếp, delta+varint giúp nhiều gap nhỏ. Trong chỉ mục tìm kiếm thực tế, nếu mỗi docID chỉ xuất hiện một lần trong một posting list, dãy thường **tăng nghiêm ngặt** thay vì không giảm, và có thể mã hóa gap−1 nếu giao thức cho phép.

### 30.2. Dấu thời gian sự kiện

Một dòng log có timestamp tăng dần:

```text
[1000000, 1000005, 1000010, 1000025]
```

Delta:

```text
[1000000, 5, 5, 15]
```

Giá trị đầu lớn, các gap sau nhỏ. Nếu lưu block theo thời gian với một base, có thể giảm thêm dung lượng.

### 30.3. Offset trong file hoặc cột dữ liệu

Danh sách offset tăng dần:

```text
[0, 12, 30, 31, 50]
```

Delta:

```text
[0, 12, 18, 1, 19]
```

Đây là một trường hợp tự nhiên của mã gap vì offset giữa các bản ghi thường nhỏ hơn tổng offset tuyệt đối.

### 30.4. Graph adjacency list

Nếu danh sách láng giềng của mỗi đỉnh được **sắp xếp theo ID**, ta có thể delta-encode ID láng giềng trong từng danh sách.

Nhưng phải biết **ranh giới của từng danh sách kề**. Có thể lưu:

- Số láng giềng của từng đỉnh.
- Offset byte đầu danh sách tương ứng.
- Hoặc một cấu trúc phân ranh giới khác.

Nếu chỉ nối tất cả gap vào một luồng mà không lưu ranh giới, có thể không biết một danh sách kết thúc ở đâu và danh sách kế tiếp bắt đầu ở đâu.

### 30.5. Truyền dữ liệu qua mạng

Mã varint thuận tiện khi gửi nhiều trường số nguyên mà phần lớn nhỏ. Nhưng cần xác định chính xác:

- Biến thể mã hóa (ULEB128, ZigZag hay loại khác).
- Giới hạn số byte mỗi trường.
- Cách phân biệt lỗi với kết thúc luồng.
- Schema và thứ tự trường.
- Chính sách từ chối mã không canonical.

**Không tự giả định mọi giao thức ghi “varint” đều có cùng byte đầu ra.**

## 31. Sai lầm thường gặp và cách tránh

| Nhầm lẫn | Hậu quả | Cách sửa |
|---|---|---|
| Coi mọi varint đều là ULEB128 | Dữ liệu không tương thích giữa hệ thống | Nêu rõ bit continuation và thứ tự nhóm |
| Chỉ lấy 7 bit thấp nhưng quên bit `0x80` | Bộ giải mã kết thúc quá sớm | Đặt continuation ở mọi byte trừ byte cuối |
| Nhầm `0x80` thành số 128 hoàn chỉnh | Thiếu byte kết thúc, đọc sai luồng | `80` chỉ có payload 0 và báo còn tiếp |
| Dùng `bit_length(x)/8` để tính số byte ULEB128 | Bỏ qua 1 bit cờ trong mỗi byte | Chia số bit cho **7**, làm tròn lên |
| Lấy `ceil(log₂x)` cho một số thay vì số trạng thái | Sai tại mốc lũy thừa | Dùng đúng miền và công thức |
| Mã hóa `−1` bằng ULEB128 không có quy ước dấu | Có thể lặp vô hạn/cho mã không mong muốn | Dùng ZigZag+ULEB128 hoặc SLEB128 |
| Nghĩ ZigZag và SLEB128 là cùng định dạng | Byte âm khác nhau | Ghi rõ phương pháp |
| Dịch/trừ `INT64_MIN` bằng phép toán signed không an toàn | Có thể tràn | Dùng unsigned hoặc số học rộng |
| Cho mã hơn 10 byte trên uint64 | Tốn tài nguyên và nguy cơ overflow | Giới hạn số nhóm |
| Không kiểm tra byte thứ mười | Có thể chấp nhận số vượt 64 bit | Chỉ chấp nhận payload hợp lệ |
| Chấp nhận `80 00` như cách viết số 0 | Không canonical, nhiều mã cho một giá trị | Từ chối overlong nếu định dạng yêu cầu |
| Tính delta trên dãy chưa sắp xếp rồi dùng unsigned | Xuất hiện gap âm | Kiểm tra không giảm hoặc mã signed gap |
| Quên mốc ban đầu của delta | Không khôi phục được giá trị tuyệt đối | Lưu base/anchor hoặc quy ước 0 |
| Tưởng delta không giảm nghĩa các gap đều dương | Dãy có thể trùng giá trị | Cho phép gap 0 |
| Thay giá trị giữa dãy nhưng chỉ cập nhật một gap | Những phần tử sau bị sai | Cập nhật các gap lân cận |
| Tưởng delta+varint luôn ít byte hơn varint trực tiếp | Dãy dao động có thể phình | So sánh bằng đo dữ liệu |
| Giải mã delta không kiểm tra prefix sum | Tràn kiểu số | Chặn `gap≤MAX−previous` |
| Không lưu ranh giới block/danh sách | Giải mã khó phân biệt dữ liệu | Lưu count, byte length hoặc offset |
| Gọi varint là truy cập ngẫu nhiên `O(1)` không chỉ mục | Không biết byte đầu phần tử i | Dùng checkpoint/index |
| Chỉ đo payload, bỏ qua index/header | Đánh giá tiết kiệm sai | Tính tổng dung lượng của layout |
| Coi ZigZag làm dữ liệu nhỏ hơn về trị tuyệt đối với mọi x | ZigZag có thể nhân đôi số dương | Dùng cho dữ liệu signed gần 0 |
| Áp `gap−1` cho dãy có giá trị trùng | Delta 0 thành số âm | Chỉ áp nếu tăng nghiêm ngặt |
| So sánh thời gian với `O(1)` nhưng dùng big integer không giới hạn | Bỏ qua chi phí theo số bit | Đặt giới hạn kiểu và mô hình chi phí |

## 32. Quy trình lựa chọn định dạng lưu số nguyên

Khi thiết kế cấu trúc dữ liệu gọn, hãy xác định trước:

1. **Miền giá trị:** unsigned 32/64 bit, signed 64 bit hay số nguyên lớn tùy ý?
2. **Tính phân bố:** phần lớn số nhỏ, số lớn, hay gần đồng đều?
3. **Thứ tự dữ liệu:** có không giảm, tăng nghiêm ngặt hoặc gần tuyến tính không?
4. **Kiểu truy vấn:** duyệt tuần tự, tìm kiếm nhị phân, truy cập phần tử bất kỳ, hay cập nhật giữa mảng?
5. **Chính sách metadata:** có cần count, block base, byte offset, checkpoint, checksum không?
6. **Khả năng tương thích:** đúng ULEB128/ZigZag/SLEB128 hay định dạng khác?
7. **An toàn dữ liệu:** giới hạn byte, canonical, overflow, dữ liệu hỏng và vùng nhớ.
8. **Độ phức tạp:** tính cả mã hóa, giải mã, build index và cập nhật.
9. **Benchmark:** đo tổng byte, tốc độ giải mã, khả năng truy cập ngẫu nhiên và peak memory.
10. **Kiểm thử:** đặc biệt ở các ngưỡng 127/128, 16.383/16.384, `INT64_MIN` và giá trị lớn nhất.

Một lựa chọn thường hợp lý:

- **Mảng fixed-width:** khi cần truy cập/cập nhật trực tiếp rất thường xuyên.
- **ULEB128:** khi luồng chủ yếu chứa số nguyên không âm nhỏ.
- **ZigZag + ULEB128:** khi cần số có dấu gần 0.
- **Delta + ULEB128:** khi lưu danh sách tăng dần và truy cập tuần tự.
- **Block FOR/bit packing:** khi cần cả dung lượng gọn và truy cập cục bộ.
- **Delta-of-delta:** khi khoảng cách giữa các giá trị có xu hướng ổn định.

Không có một biến thể mã hóa tối ưu đồng thời cho mọi phân phối và mọi loại thao tác.

## 33. Bài tập tự kiểm tra có lời giải

**Câu 1.** Trong ULEB128, mỗi byte chứa bao nhiêu bit dữ liệu và bit cao nhất dùng để làm gì?

**Đáp án:** **7 bit thấp** là payload; bit cao `0x80` cho biết **còn byte tiếp theo** hay đây là byte cuối.

**Câu 2.** Vì sao số 127 chỉ cần một byte nhưng 128 cần hai byte ULEB128?

**Đáp án:** Một byte chỉ có **7 bit payload**, biểu diễn `0..127`. Số 128 cần nhóm thứ hai: `80 01`.

**Câu 3.** Giải mã `AC 02` cho kết quả nào?

**Đáp án:** `0x2C+2·128=44+256=300`.

**Câu 4.** `80 80 01` là mã của số nào?

**Đáp án:** `1·2^{14}=16.384`.

**Câu 5.** Số 16.383 cần bao nhiêu byte ULEB128 và mã hex là gì?

**Đáp án:** **2 byte**: `FF 7F`.

**Câu 6.** Vì sao `80` đơn lẻ không phải mã số 0 hợp lệ?

**Đáp án:** Bit cao của byte này bằng 1, nên nó báo **phải có byte tiếp theo**. Số 0 canonical phải là `00`.

**Câu 7.** Có nên chấp nhận `80 00` làm cách mã hóa số 0 trong bộ giải mã canonical không?

**Đáp án:** **Không**. Đó là mã overlong; số 0 phải dùng đúng `00`.

**Câu 8.** Một `uint64` ULEB128 cần nhiều nhất bao nhiêu byte?

**Đáp án:** **10 byte**, vì `⌈64/7⌉=10`.

**Câu 9.** Trong byte thứ mười của ULEB128 canonical cho `uint64`, byte hợp lệ có thể là gì?

**Đáp án:** Nếu mã thực sự dài tới byte thứ mười, byte cuối phải là **`01`**, vì chỉ còn một bit cao có nghĩa và không thể có nhóm 0 thừa.

**Câu 10.** Tại sao ép `int64(-1)` sang `uint64` rồi mã hóa không phải cách gọn cho số âm gần 0?

**Đáp án:** Nó trở thành `2^{64}−1` và cần **10 byte**; ZigZag ánh xạ `−1→1`, chỉ cần **1 byte**.

**Câu 11.** ZigZag ánh xạ `−2` và `3` thành gì?

**Đáp án:** `−2→3` và `3→6`.

**Câu 12.** `−64` dùng mấy byte khi áp ZigZag rồi ULEB128?

**Đáp án:** ZigZag `−64→127`, nên dùng **1 byte `7F`**.

**Câu 13.** ZigZag+ULEB128 và SLEB128 có phải cùng định dạng không?

**Đáp án:** **Không**. Cả hai hỗ trợ số có dấu nhưng cách mã hóa khác; chẳng hạn `−1` thành `01` theo ZigZag+ULEB128 và thường là `7F` theo SLEB128.

**Câu 14.** Dãy `[100,103,103,130,500]` có delta với mốc 0 là gì?

**Đáp án:** `[100,3,0,27,370]`.

**Câu 15.** Với các delta `[100,3,0,27,370]`, khôi phục phần tử cuối bằng cách nào?

**Đáp án:** Cộng tất cả delta: `100+3+0+27+370=500`.

**Câu 16.** Vì sao delta 0 không phải dữ liệu lỗi trong một dãy không giảm?

**Đáp án:** Hai giá trị liên tiếp có thể **bằng nhau**. Delta 0 biểu thị một phần tử trùng giá trị trước.

**Câu 17.** Dãy `[1000,1004,1011,1011,1020,1100]` sau delta+ULEB128 cần bao nhiêu byte?

**Đáp án:** **7 byte** với luồng `E8 07 04 07 00 09 50`.

**Câu 18.** Nếu mã hóa trực tiếp sáu ID ở câu 17 bằng ULEB128, cần bao nhiêu byte?

**Đáp án:** **12 byte** vì cả sáu ID đều nằm trong khoảng cần hai byte.

**Câu 19.** Với dãy `[0,127,0,127,0]`, delta+ZigZag+ULEB128 có chắc nhỏ hơn ULEB128 trực tiếp không?

**Đáp án:** **Không.** ULEB128 trực tiếp dùng **5 byte**; delta+ZigZag tạo `[0,254,253,254,253]`, dùng **9 byte**.

**Câu 20.** Nếu dãy đã sắp tăng nghiêm ngặt, có thể tối ưu các gap từ phần tử thứ hai như thế nào?

**Đáp án:** Có thể lưu `gap−1` vì mỗi gap ấy ít nhất 1; lúc giải mã phải cộng lại 1. Không áp dụng cho dãy cho phép trùng.

**Câu 21.** Hai số `int64` hợp lệ có đảm bảo hiệu của chúng vẫn thuộc `int64` không?

**Đáp án:** **Không.** Hiệu giữa `INT64_MAX` và `INT64_MIN` là `2^{64}−1`, vượt miền signed 64 bit.

**Câu 22.** Delta-of-delta là gì?

**Đáp án:** Là **chênh lệch giữa các delta liên tiếp**. Nó giúp khi những khoảng cách giữa các giá trị gần bằng nhau, thường gặp ở timestamp gần đều.

**Câu 23.** Với block `[1000,1002,1005,1007]` và base 1000, các offset FOR là gì và mỗi offset cần bao nhiêu bit?

**Đáp án:** `[0,2,5,7]`, mỗi offset cần **3 bit**, vì giá trị lớn nhất là 7. Phải cộng thêm byte chứa base và metadata block.

**Câu 24.** Vì sao varint khó truy cập ngẫu nhiên phần tử thứ i?

**Đáp án:** **Độ dài mã khác nhau** nên offset byte không bằng `i·constant`; phải quét từ đầu hoặc dùng chỉ mục/checkpoint.

**Câu 25.** Vì sao delta làm việc truy cập phần tử thứ i còn khó hơn varint trực tiếp?

**Đáp án:** Ngoài xác định offset byte, còn phải cộng các delta từ **mốc tuyệt đối gần nhất** tới i để khôi phục giá trị.

**Câu 26.** Nếu lưu checkpoint mỗi k phần tử, số checkpoint khoảng bao nhiêu và tối đa cần giải mã bao nhiêu delta sau mốc?

**Đáp án:** Khoảng `⌈n/k⌉` checkpoint; giải mã **`O(k)` phần tử** từ mốc gần nhất trong trường hợp xấu.

**Câu 27.** Khi sửa phần tử giữa của `[100,105,110]` thành 108, dãy delta biến thành gì?

**Đáp án:** Dãy mới `[100,108,110]` có delta `[100,8,2]`. Hai khoảng lân cận phải đổi.

**Câu 28.** Vì sao ULEB128 cho các giá trị `0..127` dùng 8 bit dù giới hạn thông tin cho 128 trạng thái chỉ cần 7 bit?

**Đáp án:** Byte ULEB128 dùng **một bit làm cờ kết thúc**, giúp nối các mã vào luồng và xác định ranh giới; bit thứ tám không phải payload.

**Câu 29.** Mã hóa n giá trị uint64 thành ULEB128 có tổng byte B nằm trong khoảng nào?

**Đáp án:** `n≤B≤10n` vì mỗi số cần từ 1 đến 10 byte. Đây chỉ là payload của các số, không tính metadata.

**Câu 30.** Vì sao không nên chỉ kiểm tra `decode(encode(x))==x` mà bỏ qua đầu vào hỏng?

**Đáp án:** Round-trip hợp lệ không kiểm tra được lỗi **truncated, overlong, tràn 64 bit, offset sai hoặc lạm dụng độ dài đầu vào**. Cần test các mã bị cố tình làm hỏng.

## Ghi nhớ

- **Varint** lưu số nhỏ trong ít byte hơn số lớn. Bài dùng **ULEB128**: mỗi byte có **7 bit payload**, bit `0x80` báo còn byte sau, các nhóm thấp được ghi trước. Số 127 dùng `7F`, số 128 dùng `80 01`.
- ULEB128 cho số `uint64` cần từ **1 đến 10 byte**. Bộ giải mã nghiêm ngặt phải phát hiện **mã bị cắt ngang, overlong/non-canonical, số vượt 64 bit và byte tiếp diễn quá giới hạn**.
- **ZigZag** chuyển số có dấu gần 0 thành số không dấu gần 0: `0→0`, `−1→1`, `1→2`. ZigZag+ULEB128 **không phải** signed LEB128; phải ghi rõ định dạng khi trao đổi dữ liệu.
- **Delta encoding** lưu `d_0=x_0` và `d_i=x_i−x_{i−1}`. Dãy không âm **không giảm** có delta không âm, giải mã bằng **tổng tiền tố**. Các ID tăng dần có nhiều khoảng cách nhỏ thường nén tốt bằng **delta+varint**.
- Delta không phải thuốc chữa mọi dữ liệu: dãy dao động mạnh, số nhỏ đã dùng 1 byte hoặc yêu cầu cập nhật ngẫu nhiên có thể khiến mã delta **lớn hơn hoặc chậm hơn** biểu diễn trực tiếp.
- **Truy cập ngẫu nhiên** vào varint/delta cần biết byte offset; delta còn cần **mốc tuyệt đối**. Checkpoint theo block đổi bộ nhớ metadata lấy khả năng truy cập nhanh hơn.
- **Delta-of-delta**, frame of reference, bit packing và run-length là những kỹ thuật liên quan, phù hợp với quy luật khác nhau. Khi so sánh, tính **payload + metadata + index + chi phí giải mã/cập nhật**.
- Một biểu diễn gọn tốt không chỉ chiếm ít byte. Nó phải có **hợp đồng mã hóa chính xác, bất biến rõ ràng, xử lý dữ liệu lỗi an toàn và chi phí thao tác phù hợp nhu cầu thực tế**.
