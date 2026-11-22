# Bitfield và thao tác trên các trường số trong chuỗi nhị phân

Redis thường được giới thiệu là kho key–value với các kiểu String, Hash, List, Set và Sorted Set. Nhưng **Redis String không chỉ chứa văn bản**: về bản chất, value có thể là một dãy byte nhị phân. Redis cung cấp lệnh **`BITFIELD`** để coi dãy byte đó như một vùng nhớ chứa nhiều **trường số nguyên (integer field) có độ rộng bit tùy chọn** rồi đọc, ghi hoặc tăng/giảm trực tiếp từng trường.

Ví dụ, một ứng dụng lưu 100 bộ đếm, mỗi bộ đếm chỉ cần giá trị từ 0 đến 15. Nếu dùng mỗi giá trị một key riêng, hệ thống phải trả chi phí key và metadata cho nhiều phần tử. Với Bitfield, mỗi bộ đếm chiếm **4 bit**, vì vậy dữ liệu thô của 100 bộ đếm chỉ cần khoảng **50 byte**, chưa tính chi phí Redis key, Redis object, allocator và những thành phần khác.

Trong **Spring Data Redis**, API trung tâm cho khả năng này là:

```java
stringRedisTemplate.opsForValue().bitField(key, subCommands);
```

Nó nhận một đối tượng `BitFieldSubCommands` mô tả chuỗi thao tác `GET`, `SET`, `INCRBY` và chính sách overflow. Bài học giải thích cách tổ chức dữ liệu nhị phân, ánh xạ bit sang số, gọi lệnh ở Redis CLI và Java, thiết kế giới hạn hợp lệ, tính nguyên tử, đồng thời cũng như các rủi ro khi áp dụng cho dữ liệu thật.

## 1. Khi nào Bitfield hữu ích?

Giả sử ta có nhiều con số nhỏ và độc lập, cần truy cập dựa trên **vị trí đã biết**:

- Một tập các chỉ số từ 0 đến 15, dùng 4 bit cho mỗi phần tử.
- Bộ đếm số lần xảy ra sự kiện trong từng ô thời gian, dùng 8 hoặc 16 bit.
- Một số trạng thái dạng mã nguyên trong khoảng giới hạn, ví dụ 0–7 cho mỗi vị trí.
- Lưới ô vuông trong game, mỗi ô giữ một mã loại địa hình hoặc điểm số nhỏ.
- Dữ liệu thống kê tạm có nhiều bucket được đánh số cố định.

Một Redis String có thể chứa các trường số này liền nhau:

```text
Redis key: demo:metrics:packed

bit 0                             bit 31
  |                                  |
  v                                  v
+--------+--------+--------+--------+
|  u8 #0 |  u8 #1 |  u8 #2 |  u8 #3 |
+--------+--------+--------+--------+
|  00010 |  00025 |  00200 |  00000 |  ← giá trị diễn giải
+--------+--------+--------+--------+
```

Mỗi trường `u8` có 8 bit và biểu diễn số nguyên không dấu từ **0 đến 255**. Bốn trường cùng nằm trong một Redis String, không phải bốn Redis key.

### 1.1. Bitfield khác gì Redis Hash?

Redis Hash:

```text
stats:42
    views    -> "120"
    likes    -> "15"
    shares   -> "7"
```

Redis Bitfield:

```text
stats:42:packed
    u16 tại bit 0  -> views
    u16 tại bit 16 -> likes
    u8  tại bit 32 -> shares
```

Hash sử dụng **field name có ý nghĩa nghiệp vụ**, thuận tiện khi schema thay đổi hoặc cần đọc theo tên. Bitfield dùng **offset + width**, phù hợp khi tập field đã được xác định trước và muốn biểu diễn rất gọn.

| Tiêu chí | Hash | Bitfield trong String |
|---|---|---|
| Định danh thuộc tính | Tên field như `views` | Bit offset và độ rộng |
| Cập nhật một thuộc tính | `HSET`, `HINCRBY` | `BITFIELD SET`, `INCRBY` |
| Khả năng đọc trực tiếp bằng CLI | Dễ hiểu | Cần nhớ encoding và offset |
| Tính linh hoạt của schema | Cao hơn | Cần quản lý layout nghiêm ngặt |
| Số lượng rất nhiều trường nguyên nhỏ | Có overhead field | Có thể rất tiết kiệm byte |
| Giá trị tùy ý/chuỗi dài/JSON | Phù hợp tùy field | Không phù hợp |
| Field-level TTL | Phụ thuộc Redis/API và thiết kế | Không có TTL riêng cho mỗi đoạn bit |
| Bảo trì khi thêm/đổi field | Dễ hơn | Có thể đòi hỏi migration |

**Không chọn Bitfield chỉ vì muốn dùng ít RAM hơn.** Nếu dữ liệu ít field, cần đọc theo tên, có schema thay đổi thường xuyên hoặc cần debug thủ công, Hash thường đơn giản và ít rủi ro hơn.

## 2. Redis String là vùng byte, không mặc định là chuỗi UTF-8

Lệnh Redis:

```redis
SET demo:text "hello"
```

tạo một Redis String chứa byte của chữ `hello`. Redis cũng cho phép giá trị của String là byte nhị phân không biểu diễn thành văn bản hợp lệ.

Khi dùng:

```redis
BITFIELD demo:packed SET u8 0 255
```

key `demo:packed` chứa một byte `11111111` (`0xFF`). Byte này **không phải** một chuỗi văn bản `"255"` gồm ba ký tự ASCII.

Sự khác biệt:

```text
SET demo:number "255"
    → các byte ASCII: 0x32 0x35 0x35

BITFIELD demo:packed SET u8 0 255
    → byte nhị phân: 0xFF
```

Vì vậy, sau khi ghi bằng `BITFIELD`, không nên làm:

```java
String text = redis.opsForValue().get("demo:packed");
```

rồi kỳ vọng nhận chuỗi `"255"`. Với `StringRedisTemplate`, serializer value được thiết kế cho chuỗi UTF-8, trong khi giá trị thật có thể chứa byte không hợp lệ với văn bản. Cách đọc đúng là **tiếp tục sử dụng thao tác bitfield**, có độ rộng và offset tương ứng.

`StringRedisTemplate` vẫn phù hợp để thực thi `bitField(...)` nhờ key serializer chuỗi. Việc thao tác bitfield sử dụng lệnh Redis trên byte nội bộ; nó không có nghĩa value nhị phân đã trở thành một String Java có nội dung dễ đọc.

### 2.1. Kiểu Redis nhìn từ server vẫn là `string`

```redis
TYPE demo:packed
```

Khi key tồn tại, kết quả là:

```text
string
```

Không có kiểu Redis mang tên `bitfield` tách khỏi String. `BITFIELD`, `GETBIT`, `SETBIT`, `BITCOUNT` và một số lệnh bitmap đều thao tác trên **cùng nhóm dữ liệu Redis String**.

## 3. Bit, byte và vị trí của một trường số

Một byte có 8 bit:

```text
Byte 0:
+---+---+---+---+---+---+---+---+
| 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |  ← trọng số bit
+---+---+---+---+---+---+---+---+
  ^                               ^
  |                               |
offset 0                       offset 7
```

Trong cú pháp `BITFIELD`, offset **0 là bit có trọng số lớn nhất (most significant bit) của byte đầu tiên**, không phải bit thấp nhất.

Giả sử lưu:

```redis
BITFIELD demo:byte SET u8 0 165
```

165 ở dạng nhị phân 8 bit là:

```text
165 decimal = 10100101 binary

Bit offset:   0 1 2 3 4 5 6 7
Bit value:    1 0 1 0 0 1 0 1
```

Đọc:

```redis
BITFIELD demo:byte GET u8 0
```

trả 165.

Các lệnh bit đơn:

```redis
GETBIT demo:byte 0
GETBIT demo:byte 1
GETBIT demo:byte 2
```

lần lượt trả 1, 0, 1.

### 3.1. Vị trí bắt đầu được tính theo bit, không phải byte

Lệnh:

```redis
BITFIELD demo:packed SET u8 16 42
```

nghĩa là ghi **8 bit bắt đầu từ bit offset 16**, tức byte thứ ba (đánh số byte từ 0). Nó không có nghĩa ghi ở byte offset 16.

Công thức cho một dãy trường có độ rộng cố định `w`:

\[
\text{bitOffset}(i) = i \times w
\]

Trong đó `i` là chỉ số trường từ 0.

Ví dụ `u4`:

| Chỉ số | Offset bit | Các bit chiếm dụng |
|---|---:|---|
| 0 | 0 | 0–3 |
| 1 | 4 | 4–7 |
| 2 | 8 | 8–11 |
| 3 | 12 | 12–15 |

Nếu chọn offset sai một bit, các trường có thể chồng lấn và việc ghi một trường sẽ sửa một phần trường khác.

### 3.2. Trường số có thể không nằm gọn trong một byte

Ví dụ:

```redis
BITFIELD demo:unaligned SET u5 3 23
```

Một trường `u5` bắt đầu tại bit 3 sẽ chiếm bit offset 3–7, vẫn nằm ở byte đầu. Nếu bắt đầu tại offset 7, 5 bit kéo dài qua ranh giới giữa byte đầu và byte thứ hai.

Redis tự xử lý các vị trí không căn chỉnh theo ranh giới byte. Đây là điểm khác với nhiều thư viện binary protocol vốn yêu cầu field có kích thước 8, 16 hoặc 32 bit.

## 4. Encoding: số có dấu `iN` và không dấu `uN`

Redis BITFIELD dùng encoding:

```text
uN → unsigned integer, N bit
iN → signed integer, N bit, biểu diễn bù hai
```

Các ví dụ:

| Encoding | Độ rộng | Khoảng giá trị hợp lệ |
|---|---:|---:|
| `u1` | 1 bit | 0 … 1 |
| `u2` | 2 bit | 0 … 3 |
| `u4` | 4 bit | 0 … 15 |
| `u8` | 8 bit | 0 … 255 |
| `u16` | 16 bit | 0 … 65.535 |
| `i4` | 4 bit | -8 … 7 |
| `i8` | 8 bit | -128 … 127 |
| `i16` | 16 bit | -32.768 … 32.767 |
| `i32` | 32 bit | -2.147.483.648 … 2.147.483.647 |

Redis hỗ trợ **signed từ 1 đến 64 bit** và **unsigned từ 1 đến 63 bit** cho lệnh BITFIELD. Không nên sử dụng `u64` trong ví dụ thực thi, vì Redis BITFIELD không hỗ trợ trường unsigned 64 bit với trả lời nguyên theo giao thức hiện hành.

Công thức tổng quát:

\[
uN: \quad 0 \le x \le 2^N - 1
\]

\[
iN: \quad -2^{N-1} \le x \le 2^{N-1} - 1
\]

Chọn loại không dấu khi **giá trị luôn không âm**; chọn có dấu khi cần biểu diễn số âm. Nếu cần dung lượng lớn hơn phạm vi đã chọn, phải nâng chiều rộng field hoặc thay đổi thiết kế.

### 4.1. Cùng một chuỗi bit có thể được hiểu khác nhau

Ví dụ một byte là `11111111`:

```redis
DEL demo:signed
BITFIELD demo:signed SET u8 0 255
BITFIELD demo:signed GET u8 0 GET i8 0
```

Kết quả hai GET:

```text
u8 → 255
i8 → -1
```

Byte vật lý không đổi; cách giải mã bằng encoding khác nhau tạo giá trị khác nhau. **Schema cần lưu cả width và signedness**, không chỉ lưu offset.

### 4.2. Vì sao số âm dùng bù hai?

Trong mã hóa signed bù hai, bit cao nhất thể hiện phần dấu và giá trị số được giải mã theo hai's complement. Chẳng hạn:

```text
i8 -1   → 11111111
i8 -128 → 10000000
i8 127  → 01111111
```

Điều đó giải thích vì sao khi signed 8 bit tràn khỏi 127 theo chế độ WRAP, kết quả có thể quay về -128.

## 5. Lệnh `BITFIELD`: cú pháp và cấu trúc trả về

Dạng tổng quát:

```redis
BITFIELD key
  [GET encoding offset]
  [SET encoding offset value]
  [INCRBY encoding offset increment]
  [OVERFLOW WRAP|SAT|FAIL]
  ...
```

Một lần gọi có thể chứa **nhiều subcommand**. Redis thực thi các subcommand theo thứ tự và trả một mảng kết quả tương ứng với các phép đọc/ghi/tăng.

Ví dụ:

```redis
DEL demo:fields
BITFIELD demo:fields SET u8 0 12 SET u8 8 25 GET u8 0 GET u8 8
```

Kết quả mong đợi:

```text
1) (integer) 0     # SET thứ nhất trả giá trị cũ
2) (integer) 0     # SET thứ hai trả giá trị cũ
3) (integer) 12    # GET trường đầu
4) (integer) 25    # GET trường sau
```

Trong cùng một command, subcommand phía sau nhìn thấy kết quả ghi của subcommand phía trước.

| Subcommand | Công việc | Kết quả |
|---|---|---|
| `GET type offset` | Đọc trường số | Giá trị hiện tại |
| `SET type offset value` | Thay giá trị trường số | **Giá trị cũ** |
| `INCRBY type offset delta` | Tăng/giảm một trường số | **Giá trị mới** |
| `OVERFLOW policy` | Đổi quy tắc xử lý tràn cho các thao tác tiếp theo | Không tạo phần tử kết quả riêng |

**Sai lầm rất hay gặp:** tưởng kết quả `SET` là giá trị mới. Hãy nhớ Redis trả giá trị trước khi ghi ở subcommand `SET`, còn `INCRBY` trả giá trị sau khi tăng.

### 5.1. GET trên key chưa tồn tại

```redis
DEL demo:empty
BITFIELD demo:empty GET u8 0 GET i8 8
```

Trả các giá trị 0. Khi đọc vùng nằm ngoài phần String đang có, Redis diễn giải các bit thiếu như **bit 0**.

Việc GET trả 0 **không chứng minh rằng dữ liệu đã được tạo trước đó**. Với schema có ý nghĩa nghiệp vụ, cần một cờ khởi tạo, metadata/version hoặc dùng `EXISTS` riêng nếu phải phân biệt “chưa tạo” với “đã có giá trị 0”.

### 5.2. SET/INCRBY có thể mở rộng String

```redis
DEL demo:grow
BITFIELD demo:grow SET u8 80 1
STRLEN demo:grow
```

Do trường 8 bit nằm ở offset 80–87, String cần ít nhất 11 byte. Redis mở rộng và đệm các bit chưa được ghi bằng 0.

**Cảnh báo:** một offset nhầm thành hàng tỷ có thể buộc Redis cố cấp phát một String rất lớn, làm tăng độ trễ, RAM và thậm chí khiến lệnh lỗi. Offset nên được tính từ index **đã validate và có giới hạn** trước khi gửi đến Redis.

## 6. Offset trực tiếp và offset dạng `#index`

Redis có hai cách viết vị trí:

```redis
BITFIELD key GET u8 16
```

Đọc `u8` bắt đầu ở **bit thứ 16**.

```redis
BITFIELD key GET u8 #2
```

Ở đây `#2` nghĩa là **phần tử thứ hai theo bề rộng 8 bit**, tức:

\[
\text{offset} = 2 \times 8 = 16
\]

Hai lệnh trên tương đương khi encoding là `u8`.

Ví dụ:

```redis
DEL demo:array
BITFIELD demo:array SET u8 #0 10 SET u8 #1 20 SET u8 #2 30
BITFIELD demo:array GET u8 #0 GET u8 #1 GET u8 #2
```

Kết quả đọc lần lượt là 10, 20, 30.

### 6.1. `#index` phụ thuộc độ rộng của từng subcommand

```redis
BITFIELD demo:array GET u8 #2
```

sử dụng offset `2 × 8 = 16`.

Nhưng:

```redis
BITFIELD demo:array GET u16 #2
```

sử dụng offset `2 × 16 = 32`.

**Cùng `#2` nhưng khác encoding sẽ trỏ tới vị trí bit khác nhau.** Với một schema chứa nhiều loại field có độ rộng khác nhau, dùng offset bit rõ ràng thường dễ bảo trì hơn.

### 6.2. Ví dụ đóng gói hai giá trị 4 bit trong một byte

```redis
DEL demo:nibbles
BITFIELD demo:nibbles SET u4 0 10 SET u4 4 11
BITFIELD demo:nibbles GET u8 0
```

Kết quả GET là **171**, vì:

```text
10 decimal → 1010 (4 bit)
11 decimal → 1011 (4 bit)

Nối hai trường:
1010 1011 = 0xAB = 171 decimal
```

Đây là minh họa rõ việc Bitfield **không lưu số dưới dạng chuỗi thập phân**. Toàn bộ hai số nhỏ được ghép thành đúng một byte dữ liệu nhị phân.

## 7. Tăng hoặc giảm field bằng `INCRBY`

Một bộ đếm có thể nằm trong một trường số:

```redis
DEL demo:counter
BITFIELD demo:counter INCRBY u8 0 1
BITFIELD demo:counter INCRBY u8 0 1
BITFIELD demo:counter GET u8 0
```

Các kết quả tăng lần lượt là 1, 2, và GET trả 2.

Giảm bằng increment âm:

```redis
BITFIELD demo:counter INCRBY u8 0 -1
```

Sau khi đang ở giá trị 2, kết quả là 1.

`INCRBY` trên một field được Redis thực hiện như một thao tác nguyên tử ở phía server, tránh race của kiểu:

```text
Client A GET → cộng → SET
Client B GET → cộng → SET
```

Hai client cùng gửi `BITFIELD ... INCRBY ...` trên một field sẽ có kết quả tương ứng với thứ tự Redis thực thi các lệnh.

### 7.1. Một lệnh có thể tăng nhiều field

```redis
BITFIELD demo:stats INCRBY u8 0 1 INCRBY u8 8 2 INCRBY u8 16 3
```

Các subcommand được thực hiện trong **một lệnh Redis**. Điều này giúp giảm round-trip, đồng thời tránh việc một lệnh từ client khác chen vào giữa chuỗi subcommand của chính lệnh đó.

Tuy nhiên, nếu một subcommand gặp `OVERFLOW FAIL` và trả nil, những subcommand khác **không tự rollback**. Đừng coi `BITFIELD` là một transaction “tất cả thành công hoặc tất cả thất bại” chỉ vì có nhiều subcommand trong một lệnh.

## 8. Overflow: hành vi khi giá trị vượt phạm vi bit

Một số nguyên 4 bit không dấu `u4` chỉ lưu được từ 0 đến 15. Nếu đang là 15 rồi tăng 1, chuyện gì xảy ra?

Redis cho phép chọn chính sách:

- `WRAP` — vòng về phía đầu đối diện của khoảng giá trị, **mặc định**.
- `SAT` — bão hòa tại min/max; không vượt giới hạn.
- `FAIL` — không sửa field khi tràn, trả `nil` ở kết quả subcommand đó.

### 8.1. `WRAP`: quay vòng

```redis
DEL demo:wrap
BITFIELD demo:wrap SET u4 0 15
BITFIELD demo:wrap INCRBY u4 0 1
BITFIELD demo:wrap GET u4 0
```

Kết quả sau khi tăng là **0**, vì:

```text
u4: 0 … 15
15 + 1 → 0 (WRAP)
```

Signed cũng có vòng theo bù hai:

```redis
DEL demo:wrap-signed
BITFIELD demo:wrap-signed SET i8 0 127
BITFIELD demo:wrap-signed INCRBY i8 0 1
```

Kết quả `-128`.

`WRAP` phù hợp với một số bộ đếm tuần hoàn hoặc thuật toán số học modulo. Nó **nguy hiểm** nếu số 0 sau khi tràn bị hiểu là “chưa có lượt truy cập” hoặc “quota đã reset”.

### 8.2. `SAT`: giữ tại giới hạn

```redis
DEL demo:sat
BITFIELD demo:sat SET u4 0 15
BITFIELD demo:sat OVERFLOW SAT INCRBY u4 0 1
BITFIELD demo:sat GET u4 0
```

Kết quả tăng và kết quả GET đều là **15**.

Nếu giá trị đang là 14 và tăng 5 với SAT, kết quả cũng là 15. Khi giảm dưới 0, giá trị dừng ở 0.

Dùng SAT khi muốn số đo bị chặn trong một khoảng và ứng dụng **chấp nhận mất thông tin về phần vượt giới hạn**. Chẳng hạn “mức độ 0–15” có thể bão hòa ở 15.

### 8.3. `FAIL`: từ chối thao tác vượt giới hạn

```redis
DEL demo:fail
BITFIELD demo:fail SET u4 0 15
BITFIELD demo:fail OVERFLOW FAIL INCRBY u4 0 1
BITFIELD demo:fail GET u4 0
```

Kết quả của `INCRBY` là `nil` và field vẫn bằng 15.

`FAIL` hữu ích khi ứng dụng phải **biết việc tăng không được chấp nhận** vì đã tới giới hạn.

Cần phân biệt `nil` do `OVERFLOW FAIL` với các tình huống Java/Spring trả `null` khi dùng pipeline/transaction hoặc gặp vấn đề ở lớp API. Không suy luận mọi `null` đều là overflow mà thiếu ngữ cảnh.

### 8.4. Chính sách `OVERFLOW` áp dụng từ chỗ khai báo trở đi

```redis
BITFIELD demo:mixed \
  OVERFLOW SAT INCRBY u4 0 1 \
  OVERFLOW FAIL INCRBY u4 4 1
```

`SAT` tác động lên thao tác sau nó cho đến khi gặp `OVERFLOW` khác; `FAIL` tác động lên các thao tác phía sau tương tự. `GET` không dùng overflow vì đó là phép đọc.

Nếu một `BITFIELD` có nhiều subcommand và một subcommand `FAIL`, các kết quả còn lại vẫn có thể xuất hiện và thay đổi dữ liệu. Không dùng một mảng kết quả toàn bộ để giả định commit/rollback đa trường.

### 8.5. Overflow cũng liên quan tới `SET`

Không chỉ `INCRBY`, subcommand `SET` cũng chịu policy overflow đã được chỉ định. Nếu ghi một số vượt phạm vi biểu diễn mà không dùng `FAIL` hoặc `SAT`, giá trị có thể bị cắt/vòng theo quy tắc số học được chọn.

**Luôn validate input ở phía Java**, đặc biệt khi `SET` được gọi từ dữ liệu không tin cậy. `OVERFLOW FAIL` là một lớp bảo vệ tại Redis, không thay thế validation của DTO/API.

## 9. `BITFIELD_RO`: chỉ đọc những trường số

Redis có lệnh riêng **`BITFIELD_RO`** cho thao tác read-only:

```redis
BITFIELD_RO demo:array GET u8 #0 GET u8 #1
```

Lệnh này chỉ cho phép các subcommand GET, không cho phép `SET`, `INCRBY` hay `OVERFLOW` thay đổi dữ liệu.

Nó hữu ích khi cần:

- Chỉ đọc trên connection/replica hoặc môi trường có phân quyền read-only phù hợp.
- Làm rõ ý định rằng request không sửa Redis.
- Dễ phân tích và tách quyền giữa đường đọc với đường ghi.

`BITFIELD_RO` đã có trên các phiên bản Redis hiện đại; cần kiểm tra version server trong dự án. Không mặc định rằng `ValueOperations.bitField(...)` của mọi phiên bản Spring Data Redis sẽ tự dùng `BITFIELD_RO` nếu bạn chỉ thêm subcommand GET. API này thường ánh xạ đến khả năng `BITFIELD`; nếu read-only routing/ACL là yêu cầu bắt buộc, hãy xác minh driver và lệnh thực tế hoặc dùng API thấp hơn hỗ trợ `BITFIELD_RO` tương ứng.

## 10. BITFIELD so với `SETBIT`, `GETBIT`, `BITCOUNT`

Các lệnh dễ bị nhầm:

| Lệnh | Ý nghĩa | Ví dụ |
|---|---|---|
| `GETBIT key offset` | Đọc một bit 0/1 | Cờ đã hoàn thành |
| `SETBIT key offset bit` | Ghi một bit 0/1 | Đánh dấu thành viên |
| `BITCOUNT key` | Đếm số bit có giá trị 1 | Đếm số ngày hoạt động trong bitmap |
| `BITFIELD key GET u4 0` | Diễn giải nhiều bit thành số nguyên | Đọc mức độ từ 0–15 |
| `BITFIELD key SET u4 0 9` | Ghi nhiều bit thành một số nguyên | Ghi mã trạng thái |
| `BITFIELD key INCRBY u4 0 1` | Tăng số nguyên nằm trong vài bit | Bộ đếm nhỏ |

Nếu mỗi vị trí chỉ cần **true/false**, `SETBIT`/`GETBIT` hoặc một Set là đơn giản hơn. Nếu mỗi vị trí cần giá trị 0–15, phải dùng nhiều bit; `BITFIELD` diễn đạt trực tiếp hơn việc tự `GETBIT` bốn lần và kết hợp thành số ở Java.

Ví dụ hỗn hợp:

```redis
DEL demo:flags
SETBIT demo:flags 0 1
SETBIT demo:flags 3 1
BITFIELD demo:flags GET u4 0
```

Các bit đầu là `1001`, nên `u4` tại offset 0 có giá trị 9.

Cần nhớ: những lệnh này **cùng thao tác trên byte của một String**. Nếu một service coi bit 0 là cờ Boolean, còn service khác `BITFIELD SET u4 0 ...`, thao tác sau có thể vô tình làm thay đổi cờ của service trước. Phải có sơ đồ layout và ownership rõ ràng.

## 11. Chuẩn bị ứng dụng Spring Boot

Sử dụng Redis server local để thử nghiệm, chẳng hạn một Redis container hoặc Redis dành riêng cho development.

Với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ `application.yml` cho Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:127.0.0.1}
      port: ${REDIS_PORT:6379}
      timeout: 2s
```

Spring Boot thường tự cấu hình `RedisConnectionFactory` và `StringRedisTemplate` khi có starter và driver phù hợp.

Để kiểm tra Redis:

```redis
PING
```

Phản hồi mong đợi:

```text
PONG
```

Nếu Redis đang chạy trong Docker Compose và Spring Boot chạy trên **host**, thường kết nối bằng `127.0.0.1` và host port đã publish. Nếu Spring Boot chạy ở container khác trong cùng Compose network, host là tên Redis service (ví dụ `redis`), không phải `localhost`.

## 12. Java: đọc/ghi các trường số bằng `BitFieldSubCommands`

Spring Data Redis cung cấp:

```java
List<Long> bitField(
        K key,
        BitFieldSubCommands subCommands
);
```

`BitFieldSubCommands` được xây dựng theo kiểu fluent builder. Các kiểu con thường dùng:

```java
BitFieldSubCommands.BitFieldType.unsigned(8);
BitFieldSubCommands.BitFieldType.signed(16);
```

`valueAt(long)` dùng bit offset tuyệt đối.

### 12.1. Ví dụ thiết lập, đọc và tăng hai bộ đếm `u8`

```java
package example.redis;

import java.util.List;

import org.springframework.data.redis.connection.BitFieldSubCommands;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PackedMetricsService {

    private static final String KEY = "demo:metrics:packed";

    private final StringRedisTemplate redis;

    public PackedMetricsService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Long> initializeAndRead() {

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .set(BitFieldType.unsigned(8)).valueAt(0).to(12)
                .set(BitFieldType.unsigned(8)).valueAt(8).to(25)
                .get(BitFieldType.unsigned(8)).valueAt(0)
                .get(BitFieldType.unsigned(8)).valueAt(8);

        return redis.opsForValue().bitField(KEY, commands);
    }

    public Long incrementSecond() {

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .incr(BitFieldType.unsigned(8)).valueAt(8).by(1);

        List<Long> results = redis.opsForValue().bitField(KEY, commands);

        return results == null || results.isEmpty() ? null : results.get(0);
    }
}
```

Khi gọi `initializeAndRead()` trên key chưa có dữ liệu, kết quả thường là:

```text
[0, 0, 12, 25]
```

Hai vị trí đầu là **giá trị cũ** do `SET` trả về; hai vị trí sau là kết quả GET. Nếu gọi method lần thứ hai, giá trị cũ trả về sẽ khác, vì key đã có dữ liệu.

Ở lời gọi `incrementSecond()`, subcommand `INCRBY` trả **giá trị sau khi tăng**. Nếu chưa đổi chính sách overflow, Redis mặc định dùng WRAP: giá trị 255 tăng 1 sẽ quay về 0.

### 12.2. Vì sao `List<Long>` có thể chứa `null`?

Một lệnh BITFIELD có nhiều subcommand sinh nhiều kết quả; API Java trả `List<Long>` tương ứng. Nếu `OVERFLOW FAIL` làm một phép tăng không thể thực hiện, phần tử kết quả đó có thể là `null` vì Redis trả nil.

Ngoài ra, khi template được dùng trong pipeline/transaction, method ở thời điểm xếp lệnh có thể trả `null` thay vì một danh sách kết quả thực. Cần phân biệt **null cho cả danh sách** với **null tại một vị trí của danh sách**.

Không tự viết:

```java
long current = results.get(0);
```

nếu chưa kiểm tra kết quả vắng mặt trong một luồng có khả năng overflow hoặc pipeline. Java có thể ném `NullPointerException` khi unbox một phần tử `Long` null.

### 12.3. Đọc mà không viết

```java
public Long readFirst() {

    BitFieldSubCommands commands = BitFieldSubCommands.create()
            .get(BitFieldType.unsigned(8)).valueAt(0);

    List<Long> values = redis.opsForValue()
            .bitField("demo:metrics:packed", commands);

    return values == null || values.isEmpty() ? null : values.get(0);
}
```

Đây là ví dụ **API Spring** thực hiện yêu cầu GET bitfield. Như đã lưu ý, không đồng nhất nó với câu lệnh `BITFIELD_RO` về mặt định tuyến replica và ACL nếu chưa xác minh lệnh driver thực sự gửi.

## 13. Java: `#index` bằng `Offset.multipliedByTypeLength()`

Để xây dựng một dãy các trường số có cùng độ rộng, Spring Data Redis hỗ trợ offset dựa trên index:

```java
import org.springframework.data.redis.connection.BitFieldSubCommands.Offset;
```

Tạo offset kiểu `#3`:

```java
Offset fieldIndex3 = Offset.offset(3).multipliedByTypeLength();
```

Sử dụng với `u8`:

```java
BitFieldSubCommands commands = BitFieldSubCommands.create()
        .get(BitFieldType.unsigned(8))
        .valueAt(Offset.offset(3).multipliedByTypeLength());
```

Tương đương Redis CLI:

```redis
BITFIELD demo:metrics:packed GET u8 #3
```

Tức là đọc bit 24–31.

Nếu dùng `.valueAt(3)` với cùng `u8`, đó là **bit offset 3**, không phải field thứ ba. Hai cách đọc sẽ khác nhau:

```java
// Bit offset tuyệt đối 3:
.get(BitFieldType.unsigned(8)).valueAt(3)

// Field index 3, vì 3 * 8 = 24:
.get(BitFieldType.unsigned(8))
    .valueAt(Offset.offset(3).multipliedByTypeLength())
```

Khi có nhiều field với độ rộng khác nhau, `.multipliedByTypeLength()` dùng bề rộng của subcommand tương ứng. Vì vậy các field hỗn hợp nên dùng layout có offset tuyệt đối cố định để tránh hiểu nhầm.

## 14. Java: chọn overflow SAT và FAIL

Spring Data Redis cho phép cấu hình overflow của phép tăng qua builder.

```java
import org.springframework.data.redis.connection.BitFieldSubCommands;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldType;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldIncrBy.Overflow;
```

### 14.1. Bộ đếm bão hòa `u4`

```java
public Long addAtMost15(StringRedisTemplate redis, String key) {

    BitFieldSubCommands commands = BitFieldSubCommands.create()
            .incr(BitFieldType.unsigned(4))
            .valueAt(0)
            .overflow(Overflow.SAT)
            .by(1);

    List<Long> values = redis.opsForValue().bitField(key, commands);

    return values == null || values.isEmpty() ? null : values.get(0);
}
```

Khi field đạt 15, tăng nữa vẫn trả 15. Điều này phù hợp với một mức hiển thị đã giới hạn, nhưng **không cho biết lần tăng đã được chấp thuận hay đã bão hòa** nếu chỉ nhìn con số 15. Nghiệp vụ cần quyết định cách hiểu kết quả này.

### 14.2. Bộ đếm từ chối khi đã đạt 255

```java
public boolean tryIncrementU8(StringRedisTemplate redis, String key) {

    BitFieldSubCommands commands = BitFieldSubCommands.create()
            .incr(BitFieldType.unsigned(8))
            .valueAt(0)
            .overflow(Overflow.FAIL)
            .by(1);

    List<Long> values = redis.opsForValue().bitField(key, commands);

    if (values == null || values.size() != 1) {
        throw new IllegalStateException("BITFIELD did not return one result");
    }

    // null tại vị trí 0 nghĩa là phép tăng bị từ chối vì overflow.
    return values.get(0) != null;
}
```

`OVERFLOW FAIL` ngăn tăng khỏi phạm vi `u8`. Nếu field đã bằng 255, Redis trả nil và field giữ nguyên.

**Giới hạn nghiệp vụ:** hàm chỉ đảm bảo “giá trị tại field không vượt 255 trong phép tăng này”; nó không tự bảo đảm mỗi request chỉ tăng một lần, không tự đặt TTL và không giải quyết việc đếm lại sau timeout.

## 15. Thiết kế một mảng counter có độ rộng cố định

Giả sử dashboard lưu số lần xảy ra một loại sự kiện cho 24 khung giờ. Mỗi giờ là `u16`, chứa được 0–65.535.

Một key theo ngày:

```text
metrics:events:2026-11-12
    hour 0  → u16 #0
    hour 1  → u16 #1
    ...
    hour 23 → u16 #23
```

Dữ liệu thô tối thiểu:

\[
24 \times 16 = 384 \text{ bit} = 48 \text{ byte}
\]

Kích thước này **không tính** chi phí Redis key và allocator, nhưng minh họa lợi ích đóng gói nhiều trường nhỏ.

### 15.1. Service minh họa cho hourly counter

```java
package example.redis;

import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;

import org.springframework.data.redis.connection.BitFieldSubCommands;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldType;
import org.springframework.data.redis.connection.BitFieldSubCommands.BitFieldIncrBy.Overflow;
import org.springframework.data.redis.connection.BitFieldSubCommands.Offset;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class HourlyPackedCounter {

    private static final int HOURS = 24;
    private static final int BITS_PER_HOUR = 16;

    private final StringRedisTemplate redis;

    public HourlyPackedCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(LocalDate date, int hour) {
        validateHour(hour);

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .incr(BitFieldType.unsigned(BITS_PER_HOUR))
                .valueAt(Offset.offset(hour).multipliedByTypeLength())
                .overflow(Overflow.FAIL)
                .by(1);

        List<Long> result =
                redis.opsForValue().bitField(key(date), commands);

        if (result == null || result.size() != 1) {
            throw new IllegalStateException("Unexpected BITFIELD response");
        }

        // null: counter đã đạt 65535, không được tăng.
        return result.get(0);
    }

    public Long read(LocalDate date, int hour) {
        validateHour(hour);

        BitFieldSubCommands commands = BitFieldSubCommands.create()
                .get(BitFieldType.unsigned(BITS_PER_HOUR))
                .valueAt(Offset.offset(hour).multipliedByTypeLength());

        List<Long> result =
                redis.opsForValue().bitField(key(date), commands);

        return result == null || result.isEmpty()
                ? null
                : result.get(0);
    }

    public Boolean expireDay(LocalDate date, Duration ttl) {
        return redis.expire(key(date), ttl);
    }

    private static void validateHour(int hour) {
        if (hour < 0 || hour >= HOURS) {
            throw new IllegalArgumentException("hour must be 0..23");
        }
    }

    private static String key(LocalDate date) {
        return "metrics:events:" +
                date.format(DateTimeFormatter.ISO_LOCAL_DATE);
    }
}
```

Ở ví dụ này:

- Chỉ số `hour` được giới hạn trong `[0, 23]`, tránh ghi vượt vùng 48 byte dự kiến.
- `u16` giới hạn giá trị ở 65.535; `Overflow.FAIL` trả null khi không thể tăng.
- Mỗi ngày dùng một key khác nhau; không tạo một String khổng lồ chứa dữ liệu vô hạn nhiều năm.
- `LocalDate` chỉ là ngày theo timezone mà ứng dụng lựa chọn. Cần thống nhất UTC hoặc timezone nghiệp vụ giữa producer và dashboard.
- `expireDay` là thao tác riêng, không mặc nhiên được gọi sau `increment`; nên thiết kế policy TTL/retention phù hợp nếu các key chỉ cần giữ trong thời gian hữu hạn.

### 15.2. TTL trong mô hình này cần chú ý gì?

`BITFIELD INCRBY` **không tự tạo TTL** cho String. Nếu key mới được tạo bằng một lệnh tăng, nó có thể tồn tại vô thời hạn trừ khi có chính sách expire hoặc eviction phù hợp.

Ví dụ:

```java
redis.expire("metrics:events:2026-11-12", Duration.ofDays(30));
```

Lệnh này áp dụng TTL cho **toàn bộ String chứa 24 field**, không phải cho từng giờ riêng lẻ.

Nếu quy định “ngày cũ phải tự biến mất” là bất biến cứng, việc tăng rồi gọi `EXPIRE` bằng hai lệnh có khoảng lỗi giữa chúng. Có thể dùng Lua script hoặc quy trình ghi/expire được thiết kế nguyên tử nếu bắt buộc. Cần xem tác động đến các writer đồng thời và quy tắc refresh TTL, không đơn thuần đặt lại TTL mỗi lần tăng nếu ý định là hết hạn theo một ngày cố định.

## 16. Kết hợp nhiều field trong một key và layout rõ ràng

Bitfield không có tên field. Ứng dụng phải có một **bản mô tả layout**, ví dụ:

| Field | Encoding | Offset bit | Khoảng giá trị | Ý nghĩa |
|---|---|---:|---:|---|
| `status` | `u3` | 0 | 0–7 | Mã trạng thái |
| `priority` | `u5` | 3 | 0–31 | Ưu tiên |
| `attempts` | `u8` | 8 | 0–255 | Số lần thử |
| `delta` | `i16` | 16 | -32.768…32.767 | Giá trị có dấu |

Tổng bề rộng là 32 bit (4 byte):

```text
bit offset:
0       3       8                16                         32
|-------|-------|----------------|--------------------------|
| u3    | u5    | u8             | i16                      |
|status |priority| attempts      | delta                    |
```

Lệnh Redis:

```redis
DEL demo:layout
BITFIELD demo:layout SET u3 0 5 SET u5 3 17 SET u8 8 9 SET i16 16 -12
BITFIELD demo:layout GET u3 0 GET u5 3 GET u8 8 GET i16 16
```

Kết quả GET lần lượt là 5, 17, 9, -12.

### 16.1. Vì sao schema nhị phân phải được version hóa?

Nếu phiên bản A coi bit 0–2 là `status` và bit 3–7 là `priority`, nhưng phiên bản B đổi thành `status u4` bắt đầu ở 0, hai phiên bản sẽ hiểu **cùng 4 byte** theo hai cách khác nhau. Điều đó có thể tạo dữ liệu sai mà Redis vẫn trả lời bình thường.

Một số chiến lược:

- Ghi rõ layout trong code và tài liệu.
- Đặt **version trong key**, ví dụ `job:packed:v1:42` và `job:packed:v2:42`.
- Nếu cần, dự trữ vài bit trong layout cho `schemaVersion`, nhưng phải cân nhắc phạm vi và quy tắc nâng cấp.
- Khi chuyển version, dùng dual-read hoặc migration rõ ràng, tránh hai bản ứng dụng cùng ghi một key dưới layout khác nhau.

Version theo key thường đơn giản hơn nếu đã có cache TTL và dữ liệu có thể tái tạo từ nguồn khác.

### 16.2. Field bị chồng lấn

Nếu dùng:

```redis
BITFIELD demo:overlap SET u8 0 255
BITFIELD demo:overlap SET u8 4 0
```

trường thứ hai bắt đầu từ bit 4 và kéo dài tới bit 11, nên **ghi đè một phần bit của trường đầu**. Redis không biết hai trường đó vốn được developer kỳ vọng độc lập; Redis chỉ nhận offset/width.

Nên tập trung cách tính offset trong một lớp/hàm duy nhất, có validation chặt, và không cho mỗi endpoint tự cộng offset theo công thức riêng.

## 17. Độ phức tạp và tiết kiệm bộ nhớ

Với mỗi subcommand BITFIELD, Redis thường xử lý thao tác trên một vùng bit nhỏ với chi phí gần O(1) theo giới hạn width, không cần parse JSON hay duyệt toàn bộ một Hash. Nhưng hiệu năng end-to-end phụ thuộc thêm:

- Số subcommand trong một lệnh.
- Kích thước Redis String và việc có phải cấp phát/mở rộng hay không.
- Serializer, network, round-trip, pipeline, độ trễ ứng dụng.
- Lượng contention do nhiều client cùng sửa một key.
- Redis persistence, replication và memory pressure.

### 17.1. Công thức ước lượng kích thước thô

Với `N` field cùng width `w`, nếu đóng gói liên tiếp từ offset 0:

\[
\text{rawBytes} = \left\lceil \frac{N \times w}{8} \right\rceil
\]

Ví dụ:

| Số field | Width | Dung lượng bit | Byte dữ liệu thô |
|---:|---:|---:|---:|
| 100 | 4 | 400 | 50 |
| 1.000 | 8 | 8.000 | 1.000 |
| 24 | 16 | 384 | 48 |
| 10.000 | 2 | 20.000 | 2.500 |

Đây là **dung lượng của byte String**, chưa phải `MEMORY USAGE` của cả Redis key. Redis còn có overhead object, allocator, metadata và key name. Nếu quá ít field, lợi ích lưu trữ có thể không đáng kể so với độ phức tạp layout.

### 17.2. Không nhầm “gọn” với “rẻ trong mọi tình huống”

Giả sử có một triệu field `u8` trong cùng một String. Dữ liệu thô khoảng một MB, có thể chấp nhận được về RAM, nhưng nếu mọi request chỉ tăng cùng một field trên cùng key, key đó vẫn có thể thành **Hot Key**. Trong Redis Cluster, một key chỉ thuộc **một hash slot**, nên không tự được chia ra nhiều node.

Nếu muốn scale theo tenant, ngày hoặc nhóm thống kê, chia theo nhiều key:

```text
metrics:tenant:42:2026-11-10
metrics:tenant:42:2026-11-11
metrics:tenant:42:2026-11-12
```

Không gom toàn bộ lịch sử nhiều năm vào một String duy nhất. Một key được ghi ở offset rất xa có thể trở thành Big Key dù chỉ có vài field thực sự được sử dụng.

## 18. Kiểm soát offset và giới hạn dữ liệu đầu vào

Bit offset có thể tính từ user ID hoặc chỉ số vị trí. Nếu index đến từ request, phải giới hạn trước khi gửi Redis.

Mẫu nguy hiểm:

```java
// KHÔNG KHUYẾN NGHỊ: index chưa có giới hạn.
long offset = userProvidedIndex * 16L;
redis.opsForValue().bitField(
        key,
        BitFieldSubCommands.create()
                .set(BitFieldType.unsigned(16))
                .valueAt(offset)
                .to(value)
);
```

Các vấn đề:

1. Index âm không hợp lệ.
2. Index lớn có thể khiến String bị mở rộng đột biến.
3. Phép nhân có thể overflow `long` trong Java.
4. Value có thể nằm ngoài phạm vi 16 bit.
5. Key do request đưa vào có thể truy cập nhầm namespace.
6. Không có giới hạn tổng dung lượng của một key.

Mẫu tốt hơn:

```java
private static final int FIELD_WIDTH = 16;
private static final int MAX_FIELDS = 1024;

private static long bitOffset(int index) {
    if (index < 0 || index >= MAX_FIELDS) {
        throw new IllegalArgumentException("index out of range");
    }

    return Math.multiplyExact((long) index, FIELD_WIDTH);
}

private static long requireU16(long value) {
    if (value < 0 || value > 65_535) {
        throw new IllegalArgumentException("value must fit u16");
    }
    return value;
}
```

Với `MAX_FIELDS = 1024`, String chứa `u16` liên tiếp sẽ có vùng dữ liệu thô tối đa khoảng 2.048 byte. Việc giới hạn này làm cho bộ nhớ có thể dự đoán hơn.

Ở Redis Cluster, số node/shard và key distribution vẫn phải được thiết kế theo access pattern; giới hạn byte không loại bỏ nguy cơ Hot Key.

## 19. Tính nguyên tử, nhiều luồng và kết quả không chắc chắn

### 19.1. Một subcommand tăng là nguyên tử ở phía Redis

Khi hai Spring Boot instance cùng gửi:

```redis
BITFIELD metrics:today INCRBY u16 0 1
```

Redis xử lý lệnh theo thứ tự tại node chứa key; tránh lost update của quy trình Java đọc rồi ghi lại.

Điều này hữu ích cho counter nhỏ. Nhưng **atomicity của lệnh không đồng nghĩa mỗi nghiệp vụ chỉ xảy ra một lần**.

### 19.2. Timeout rồi retry có thể tăng trùng

Ví dụ:

```text
T1: Spring Boot gửi INCRBY u16 0 1
T2: Redis tăng từ 10 lên 11
T3: Mạng lỗi trước khi Spring Boot nhận phản hồi
T4: Client retry
T5: Redis tăng từ 11 lên 12
```

Một yêu cầu nghiệp vụ đã làm counter tăng hai lần. `INCRBY` nguyên tử cho **mỗi lần chạy**, nhưng không idempotent.

Nếu cần chống trùng, có thể phải lưu `requestId`/business event ID và xử lý điều kiện duy nhất tại nơi phù hợp, hoặc dùng một script kết hợp kiểm tra idempotency key với tăng counter. Khi dùng nhiều Redis key, Redis Cluster có thể yêu cầu chúng cùng slot; còn dữ liệu quan trọng liên quan database cần chiến lược nhất quán riêng.

### 19.3. Nhiều field trong cùng một `BITFIELD`

```redis
BITFIELD metrics:today INCRBY u8 0 1 INCRBY u8 8 1
```

Hai phép tăng nằm trong cùng một lệnh và được thực hiện theo thứ tự, không bị lệnh khác chen giữa. Nhưng khi `OVERFLOW FAIL` áp dụng và một phép tăng bị từ chối, các phép tăng khác có thể vẫn thành công.

Nếu yêu cầu nghiệp vụ là **hoặc cả hai counter cùng tăng hoặc không counter nào tăng**, cần kiểm tra điều kiện của cả hai trước khi sửa, ví dụ qua Lua script được thiết kế đúng; đừng coi `BITFIELD` với hai INCRBY và FAIL là một transaction rollback.

### 19.4. Spring Data Redis có thể dùng chung template giữa nhiều thread

`StringRedisTemplate` đã cấu hình có thể được inject vào singleton service và dùng từ nhiều request/worker. Không nên giữ một `RedisConnection` low-level trong field dùng chung giữa các luồng.

Mỗi lời gọi `bitField` được template thực thi theo cơ chế Spring Data Redis. Nếu cần pipeline hoặc transaction, dùng callback/session được Spring quản lý, không tự chuyển connection giữa thread.

## 20. Pipeline, transaction và `BITFIELD` ghép lệnh

Có thể giảm round-trip bằng cách gom **nhiều thao tác trên cùng một key** vào một BITFIELD, thay vì gọi `bitField()` riêng lẻ cho từng field.

Ví dụ:

```java
BitFieldSubCommands commands = BitFieldSubCommands.create()
        .get(BitFieldType.unsigned(8)).valueAt(0)
        .get(BitFieldType.unsigned(8)).valueAt(8)
        .get(BitFieldType.unsigned(8)).valueAt(16);

List<Long> values = redis.opsForValue().bitField("demo:packed", commands);
```

Một lần gọi Redis trả một danh sách ba giá trị.

### 20.1. Có cần dùng Redis Pipeline không?

Khi cập nhật **nhiều key khác nhau**, pipeline có thể giảm round-trip trong một số workload. Nhưng nếu chỉ có vài field cùng một key, một BITFIELD nhiều subcommand đã tương đối gọn.

Lưu ý:

- Pipelining **không** làm những lệnh độc lập thành một transaction nguyên tử.
- Trong pipeline/transaction, API có thể trả null ngay khi xếp lệnh; kết quả được thu thập ở đầu ra của pipeline/`EXEC` theo semantics Spring Data Redis.
- Chọn serializer phù hợp khi kết quả pipeline chứa byte hoặc kiểu trả về đặc biệt.
- Dùng BITFIELD theo layout cố định, không xếp hàng nghìn subcommand không giới hạn từ input người dùng.

### 20.2. Dùng Redis transaction khi nào?

`MULTI`/`EXEC` có thể nhóm các lệnh Redis theo transaction Redis, nhưng không có rollback như database quan hệ đối với mọi loại lỗi, cũng không kết hợp tự động với transaction SQL. Những bài toán cần điều kiện trên nhiều field thường dễ biểu đạt bằng **Lua script nhỏ**, trong đó điều kiện được kiểm tra trước khi cập nhật.

Nếu script thao tác nhiều key trong Redis Cluster, phải lưu ý hash slot và khả năng thực thi theo topology.

## 21. BITFIELD và Redis TTL

TTL luôn áp dụng cho **Redis key chứa toàn bộ chuỗi byte**, không có TTL riêng cho `u8 #2` hay `i16 16`.

```redis
BITFIELD demo:packed SET u8 #0 10 SET u8 #1 20
EXPIRE demo:packed 300
TTL demo:packed
```

Sau thời gian TTL, toàn bộ key biến mất; mọi field được đọc sẽ trở về 0 theo quy tắc đọc key không tồn tại nếu ứng dụng không phân biệt existence.

Trong Spring Data Redis:

```java
redis.expire("demo:packed", Duration.ofMinutes(5));
```

Nếu nhiều field yêu cầu vòng đời khác nhau, nên tách các nhóm thành **nhiều key** theo ngày, tenant, phiên hoặc loại dữ liệu.

### 21.1. `INCRBY` không tự reset theo ngày

Một counter theo ngày cần key chứa ngày đã được xác định chuẩn:

```text
metrics:views:2026-11-12
metrics:views:2026-11-13
```

Nếu dùng **một key cố định** và kỳ vọng `INCRBY` tự reset lúc nửa đêm thì đó là sai thiết kế. Có thể tạo key theo ngày và đặt TTL dài hơn khoảng giữ dữ liệu để các ngày cũ được dọn dẹp.

Với dữ liệu thống kê quan trọng, xác định độ bền Redis và nguồn dữ liệu bền vững trước khi phụ thuộc hoàn toàn vào bộ đếm bitfield.

## 22. BITFIELD với Spring Cache và Redis Repository

`BITFIELD` là lệnh dữ liệu mức thấp trên byte của một Redis String. Nó khác với cache một object bằng `@Cacheable`.

Ví dụ khi dùng Spring Cache:

```java
@Cacheable(cacheNames = "productById", key = "#id")
public Product getProduct(long id) { ... }
```

Cache abstraction sẽ serialize value theo cấu hình `RedisCacheManager` và quản lý key/TTL riêng. Nó không tự cung cấp layout bit cho từng thuộc tính.

Tương tự, Redis Repository với `@RedisHash` làm việc với object mapping và metadata theo cơ chế repository, không tự lưu entity dưới dạng packed integer Bitfield.

**Không để nhiều lớp abstraction ghi cùng một Redis key với định dạng khác nhau.** Nếu cache manager ghi JSON/Java serialization vào key `metrics:today` trong khi Bitfield service thao tác trên key đó, dữ liệu sẽ bị ghi đè hoặc giải mã sai.

Nên dùng namespace rõ ràng:

```text
app:cache:product:42        → object cache
app:hash:user:42            → Redis Hash
app:bitfield:daily:2026-11-12 → packed binary counters
```

## 23. Quan sát dữ liệu nhị phân trong Redis

Sau khi tạo:

```redis
BITFIELD demo:packed SET u8 0 10 SET u8 8 20
```

Các lệnh chẩn đoán hữu ích:

```redis
TYPE demo:packed
STRLEN demo:packed
BITFIELD demo:packed GET u8 0 GET u8 8
BITCOUNT demo:packed
TTL demo:packed
MEMORY USAGE demo:packed
```

Ý nghĩa:

| Lệnh | Điều quan sát |
|---|---|
| `TYPE` | Kiểu vẫn là `string` |
| `STRLEN` | Độ dài **byte** của Redis String |
| `BITFIELD GET` | Giá trị số của field theo layout |
| `BITCOUNT` | Số bit 1, **không phải** tổng giá trị các field |
| `TTL` | Thời hạn tồn tại của **toàn key** |
| `MEMORY USAGE` | Ước lượng bộ nhớ Redis cho key, gồm overhead |

`BITCOUNT` trên `u8` có giá trị 10 (`00001010`) trả số bit 1 là 2, **không phải 10**. Vì vậy nó không dùng thay cho phép cộng các bộ đếm.

### 23.1. Vì sao không dùng `GET` để debug?

`GET` có thể trả byte không in được và làm terminal hiển thị khó đọc hoặc gây lỗi giải mã. Dùng `BITFIELD GET` với đúng width/offset sẽ minh bạch hơn.

Trong môi trường development, một số công cụ có thể hiển thị byte ở dạng hex, nhưng cần tránh in dữ liệu nhị phân/nhạy cảm vào log production.

### 23.2. Tránh quét toàn keyspace để tìm packed counters

Key nên được xác định trực tiếp bằng nghiệp vụ, ví dụ ngày và tenant. Không viết endpoint `KEYS app:bitfield:*` trên Redis production rồi duyệt mọi String để tổng hợp dữ liệu. Nếu cần tổng hợp qua nhiều key, duy trì danh sách phân vùng hoặc dùng hệ thống analytics phù hợp. `SCAN` có thể phục vụ tác vụ bảo trì có kiểm soát nhưng không thay query engine.

## 24. Khi nào không nên dùng Bitfield?

Bitfield không phải lựa chọn tốt cho tất cả các counter.

| Yêu cầu | Cấu trúc nên cân nhắc | Vì sao |
|---|---|---|
| Một counter số nguyên không giới hạn nhỏ | Redis String với `INCRBY` | Đơn giản, không cần tự quản lý width |
| Vài thuộc tính có tên thay đổi | Redis Hash | `HGET`/`HSET` theo tên, dễ bảo trì |
| Nhiều Boolean theo ID ổn định | Bitmap/`SETBIT` | Mỗi phần tử chỉ cần 1 bit |
| Nhiều số nguyên nhỏ theo index | Bitfield | Đóng gói tiết kiệm |
| Counter cần quá phạm vi 63/64 bit | Mô hình khác hoặc chia dữ liệu | BITFIELD bị giới hạn độ rộng |
| Giá trị tiền tệ hoặc giao dịch quan trọng | Database/transaction và representation phù hợp | Đòi hỏi consistency/durability mạnh |
| Query theo thuộc tính trên hàng triệu đối tượng | Database/search/index phù hợp | Bitfield không có truy vấn theo tên field |
| Field cần TTL riêng | Nhiều key hoặc data model khác | TTL của Redis String áp dụng toàn key |
| Schema thay đổi thường xuyên | Hash hoặc document JSON | Layout bit khó migration hơn |
| Một field ghi cực nhiều trên Redis Cluster | Chia tải theo thiết kế nghiệp vụ | Một key vẫn thuộc một slot |

Nếu bài toán chỉ là một bộ đếm đơn giản, dùng:

```java
redis.opsForValue().increment("views:article:42");
```

có thể rõ ràng hơn rất nhiều so với tự thiết kế `u16` tại offset 0 rồi xử lý tràn. Chỉ chọn Bitfield khi nhu cầu đóng gói nhiều số nhỏ thực sự xứng đáng với chi phí thiết kế schema.

## 25. Rủi ro vận hành và bảo mật

### 25.1. Offset lớn có thể gây cấp phát lớn

Một trường ở bit offset rất xa buộc Redis mở rộng String tới vùng cần ghi, kể cả tất cả bit trước đó đều bằng 0. Phải validate chỉ số đầu vào và giới hạn kích thước tối đa trước khi tạo lệnh.

Ngoài ra, Redis String có giới hạn kích thước do server/protocol/driver quy định; đừng thiết kế mảng số lớn với giả định chỉ cần một key là có thể lưu vô hạn.

### 25.2. Hot Key trong Redis Cluster

Một String chứa hàng trăm nghìn field vẫn là **một key trên một slot**. Nếu mọi request ghi cùng key, shard chủ quản có thể nghẽn. Cách giảm tải là partition theo tenant, ngày, danh mục hoặc phân vùng ổn định khi nghiệp vụ cho phép.

### 25.3. Tránh lộ thông tin theo vị trí bit

Nếu user có thể đoán `userId` hoặc index và đọc chung một bitmap chứa trạng thái của người khác, API có thể vô tình tiết lộ dữ liệu. Redis key layout phải đi kèm authorization ở tầng ứng dụng, network isolation và ACL phù hợp. Không coi Bitfield là kỹ thuật mã hóa bảo mật; nó chỉ là **mã hóa dữ liệu compact**.

### 25.4. Persistence và failover

BITFIELD cập nhật String trong Redis, nhưng khả năng giữ được ghi sau Redis crash/failover còn phụ thuộc AOF/RDB, replication, chính sách đồng bộ và hạ tầng lưu trữ. Redis không tự biến một bit counter thành bản ghi giao dịch bền vững.

Nếu counter là dữ liệu có giá trị nghiệp vụ, cần phương án kiểm kê, replay, outbox hoặc nguồn dữ liệu bền vững khác tùy RPO/RTO.

### 25.5. Script, transaction và quản trị schema

Khi nhiều service cùng đọc/ghi một layout, chỉ cần một service đổi width hoặc offset là dữ liệu có thể bị hỏng logic. Nên đặt cấu hình layout/kiểu dữ liệu tại một thư viện hoặc service sở hữu dữ liệu, có schema version và migration plan.

Đối với thay đổi không tương thích, tạo key version mới là lựa chọn an toàn hơn sửa âm thầm schema đang được tất cả instance sử dụng.

## 26. Những lỗi dễ gặp

**Nhầm `BITFIELD` là một kiểu dữ liệu Redis riêng.** Thực tế nó thao tác trên Redis String chứa byte; `TYPE` vẫn là `string`.

**Nhầm offset là byte index.** Redis dùng **bit offset**; `u8` ở offset 16 bắt đầu từ byte thứ ba.

**Nhầm `#3` luôn là bit offset 3.** `#3` được nhân với độ rộng của trường số đang truy cập; với `u8` là bit 24.

**Gọi `GET` rồi đọc kết quả `SET` là giá trị mới.** `SET` trả **giá trị cũ**, còn `INCRBY` trả **giá trị mới**.

**Không đặt overflow policy.** Mặc định là WRAP; tăng `u8` từ 255 có thể trở về 0, gây bug bộ đếm.

**Dùng `SAT` rồi coi kết quả bằng max là tăng thành công.** Khi đã bão hòa, SAT giữ nguyên max; nếu cần biết bị từ chối, dùng FAIL và đọc kết quả.

**Dùng `FAIL` rồi tin rằng mọi subcommand rollback.** Không; FAIL từ chối subcommand tràn, những subcommand khác trong cùng BITFIELD vẫn có thể được thực thi.

**Dùng `u64` vì Java có `long` 64 bit.** Redis BITFIELD hỗ trợ unsigned tối đa 63 bit; Java `long` là signed 64 bit.

**Dùng `StringRedisTemplate.opsForValue().get()` để đọc packed bytes.** Value có thể không phải UTF-8; dùng `bitField` với đúng layout.

**Không validate index.** Offset cực lớn có thể làm Redis cố cấp phát vùng byte lớn, gây RAM spike.

**Không quản lý TTL.** BITFIELD không tự gắn TTL cho một String mới hoặc từng field; cần chính sách retention rõ.

**Giữ một key quá lớn/hot.** Đóng gói tốt không loại bỏ giới hạn slot, CPU, network và contention.

**Cho nhiều code path cùng ghi một key theo schema khác.** Redis không có metadata field name/width để phát hiện sai layout; cần owner và version thống nhất.

## 27. Bài thực hành bằng `redis-cli`

Thực hành trên Redis development với các key tiền tố `demo:`. Không chạy các lệnh xóa trên namespace chứa dữ liệu ứng dụng khác.

### Bước 1. Ghi hai trường 4 bit

```redis
DEL demo:lab:packed
BITFIELD demo:lab:packed SET u4 0 7 SET u4 4 12
BITFIELD demo:lab:packed GET u4 0 GET u4 4 GET u8 0
```

Dự kiến:

```text
u4 #0 = 7
u4 #1 = 12
u8 #0 = 124 (0x7C)
```

Vì:

```text
7  → 0111
12 → 1100

01111100 → 124
```

### Bước 2. So sánh offset tuyệt đối và `#index`

```redis
BITFIELD demo:lab:packed GET u4 4 GET u4 #1
```

Cả hai cùng đọc trường thứ hai có giá trị 12.

### Bước 3. Thử WRAP, SAT và FAIL

```redis
DEL demo:lab:overflow
BITFIELD demo:lab:overflow SET u4 0 15
BITFIELD demo:lab:overflow INCRBY u4 0 1
BITFIELD demo:lab:overflow GET u4 0
```

Mặc định WRAP, kết quả 0.

```redis
BITFIELD demo:lab:overflow SET u4 0 15
BITFIELD demo:lab:overflow OVERFLOW SAT INCRBY u4 0 1
BITFIELD demo:lab:overflow GET u4 0
```

SAT giữ 15.

```redis
BITFIELD demo:lab:overflow OVERFLOW FAIL INCRBY u4 0 1
BITFIELD demo:lab:overflow GET u4 0
```

FAIL trả nil cho phép tăng, còn GET vẫn trả 15.

### Bước 4. Signed interpretation

```redis
DEL demo:lab:signed
BITFIELD demo:lab:signed SET u8 0 255
BITFIELD demo:lab:signed GET u8 0 GET i8 0
```

Kết quả 255 và -1 cho cùng dãy bit.

### Bước 5. Quan sát kích thước và TTL

```redis
TYPE demo:lab:packed
STRLEN demo:lab:packed
MEMORY USAGE demo:lab:packed
EXPIRE demo:lab:packed 120
TTL demo:lab:packed
```

`STRLEN` thể hiện số byte nhị phân đang lưu, còn `MEMORY USAGE` tính cả chi phí cấu trúc của Redis object. Sau khi TTL hết, đọc field trên key không tồn tại sẽ được diễn giải như các bit 0.

### Bước 6. Dọn dữ liệu thực hành

```redis
UNLINK demo:lab:packed demo:lab:overflow demo:lab:signed
```

Chỉ xóa những key demo vừa tạo. Không dùng `FLUSHALL` để dọn một bài thực hành nếu Redis instance còn phục vụ nhiệm vụ khác.

## 28. Tài liệu kỹ thuật để tra cứu

- Redis Commands — `BITFIELD`: https://redis.io/docs/latest/commands/bitfield/
- Redis Commands — `BITFIELD_RO`: https://redis.io/docs/latest/commands/bitfield_ro/
- Redis Commands — `GETBIT`: https://redis.io/docs/latest/commands/getbit/
- Redis Commands — `SETBIT`: https://redis.io/docs/latest/commands/setbit/
- Spring Data Redis API — `ValueOperations.bitField(...)`: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/core/ValueOperations.html
- Spring Data Redis API — `BitFieldSubCommands`: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/connection/BitFieldSubCommands.html
- Spring Data Redis API — `BitFieldSubCommands.Offset`: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/connection/BitFieldSubCommands.Offset.html

Chi tiết API có thể thay đổi theo phiên bản Redis server, Spring Data Redis và driver đang dùng; khi triển khai hãy đối chiếu tài liệu của phiên bản thực tế thay vì áp dụng mù quáng một ví dụ cho mọi hệ thống.

## Kết luận

`BITFIELD` cho phép xem **Redis String như một vùng bit chứa nhiều trường số nguyên** có độ rộng tùy chọn. Các subcommand `GET`, `SET`, `INCRBY` cung cấp cách đọc, ghi và tăng trường số theo bit offset hoặc `#index`, trong khi `OVERFLOW WRAP|SAT|FAIL` quy định phản ứng khi kết quả vượt khoảng biểu diễn. Với Spring Data Redis, bạn có thể dùng `StringRedisTemplate.opsForValue().bitField()` cùng `BitFieldSubCommands` để thể hiện các thao tác đó trong Java.

Bitfield phù hợp khi cần **nhiều số nhỏ, layout ổn định, giới hạn index rõ ràng và tiết kiệm dung lượng**. Để sử dụng an toàn, phải xác định schema bit/encoding, quản lý TTL toàn key, kiểm soát overflow, tránh offset khổng lồ, cân nhắc Hot Key/Redis Cluster và xử lý retry/idempotency theo nghiệp vụ. Khi tính linh hoạt và khả năng bảo trì quan trọng hơn độ nén, `String` số nguyên thông thường hoặc Redis `Hash` thường là lựa chọn đơn giản hơn.

