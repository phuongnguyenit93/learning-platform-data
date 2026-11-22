# Thao tác trên khoảng byte và nối chuỗi trong Spring Data Redis

Redis có kiểu dữ liệu **String**, nhưng “string” ở đây là **một dãy byte**, không nhất thiết là văn bản. Một Redis String có thể chứa chữ UTF-8, số dạng chuỗi, JSON, dữ liệu nhị phân hoặc một đoạn payload do ứng dụng tự định nghĩa. Vì vậy, Redis cung cấp các lệnh thao tác trên **một phần dãy byte** hoặc **nối thêm byte** mà không yêu cầu ứng dụng đọc toàn bộ giá trị rồi ghi lại.

Trong Spring Data Redis, các thao tác tương ứng thường nằm ở `ValueOperations` của `RedisTemplate` hoặc `StringRedisTemplate`. Bốn lệnh cần nắm là:

| Redis command | Ý nghĩa | API thường dùng của Spring Data Redis |
|---|---|---|
| `GETRANGE key start end` | Đọc đoạn byte theo khoảng chỉ số | `opsForValue().get(key, start, end)` |
| `SETRANGE key offset value` | Ghi đè một đoạn byte bắt đầu tại offset | `opsForValue().set(key, value, offset)` |
| `APPEND key value` | Nối byte vào cuối giá trị hiện tại | `opsForValue().append(key, value)` |
| `STRLEN key` | Đo độ dài giá trị theo **byte** | `opsForValue().size(key)` |

Mục tiêu của bài học là hiểu ngữ nghĩa các offset, tính nguyên tử của từng lệnh, tác động của UTF-8/serializer, hành vi với TTL và cách sử dụng đúng trong Spring Data Redis.

## 1. Redis String là byte sequence, không phải Java String

Xét giá trị ASCII:

```text
SET demo:text "HELLO"

Byte (UTF-8/ASCII):    48 45 4C 4C 4F     (hex)
Chỉ số byte:            0  1  2  3  4
Ký tự hiển thị:          H  E  L  L  O
```

Với ASCII, mỗi ký tự chiếm đúng một byte, nên vị trí byte và vị trí ký tự trông giống nhau. Với Unicode, điều đó không còn đúng:

```text
SET demo:utf8 "AéB"

UTF-8 (hex):           41 C3 A9 42
Chỉ số byte:            0  1  2  3
Ký tự Unicode:          A    é    B
                            └─ 2 byte ─┘
```

Giá trị `AéB` có ba ký tự hiển thị theo cách đếm thông thường, nhưng `STRLEN` trả về **4** vì Redis đo byte. Chữ tiếng Việt có dấu, emoji và các ký tự Unicode khác cũng có thể cần nhiều byte. Một ký tự hiển thị phức tạp thậm chí có thể gồm nhiều Unicode code point.

### Phân biệt ba lớp độ dài

| Cách nhìn | Ví dụ `AéB` | Ý nghĩa |
|---|---:|---|
| Java `String.length()` | 3 | Số đơn vị UTF-16 của chuỗi Java; không luôn bằng số ký tự hiển thị |
| UTF-8 `getBytes(UTF_8).length` | 4 | Số byte sau khi mã hóa |
| Redis `STRLEN` | 4 | Số byte Redis lưu ở value |

Với emoji ngoài Basic Multilingual Plane, `String.length()` của Java còn có thể là 2 cho một code point vì UTF-16 dùng surrogate pair. Do đó, **không dùng chỉ số trong Java String để suy luận vị trí byte Redis**, trừ khi đã bảo đảm dữ liệu thuộc bảng mã một byte phù hợp hoặc có một giao thức mã hóa rõ ràng.

## 2. Đọc một khoảng byte bằng `GETRANGE`

### 2.1. Cú pháp và nguyên tắc chỉ số

```redis
GETRANGE key start end
```

Trong Redis:

- `start` và `end` là **chỉ số byte**, bắt đầu từ `0`.
- **Cả hai đầu mút đều được tính** (inclusive): `GETRANGE key 0 3` lấy tối đa bốn byte.
- Chỉ số âm được tính từ cuối giá trị: `-1` là byte cuối, `-2` là byte kế cuối.
- Khoảng vượt giới hạn được Redis thu hẹp trong phạm vi dữ liệu hiện có; không phải lỗi chỉ vì `end` lớn hơn độ dài.
- Nếu khóa không tồn tại, lệnh trả về chuỗi byte rỗng. Nếu khóa đang chứa kiểu Redis không phù hợp (ví dụ List hoặc Hash), Redis báo lỗi kiểu dữ liệu.

Ví dụ:

```redis
SET demo:range "HELLO WORLD"

GETRANGE demo:range 0 4
# "HELLO"

GETRANGE demo:range 6 10
# "WORLD"

GETRANGE demo:range -5 -1
# "WORLD"

GETRANGE demo:range 0 -1
# "HELLO WORLD" — đọc toàn bộ giá trị

GETRANGE demo:range 100 200
# "" — khoảng không giao với dữ liệu
```

Sơ đồ:

```text
Giá trị:     H E L L O   W O R L D
Chỉ số:      0 1 2 3 4 5 6 7 8 9 10

GETRANGE 0 4   └─────────┘         => HELLO
GETRANGE 6 10              └──────┘ => WORLD
GETRANGE -5 -1             └──────┘ => WORLD
```

**Lưu ý:** `GETRANGE key 0 -1` không phải một lệnh phân trang hiệu quả cho dữ liệu lớn; đó là yêu cầu đọc **toàn bộ** giá trị. Khi chỉ cần phần đầu, phần cuối hoặc một đoạn cố định, nên chỉ định phạm vi nhỏ.

### 2.2. Đọc một “header” và một phần payload

Giả sử ứng dụng có giao thức lưu dữ liệu với đoạn header dài cố định bốn byte:

```text
V 1 0 0 | D A T A - 1 2 3
0 1 2 3   4 5 ...
```

Có thể đọc header mà không phải yêu cầu trả về cả value:

```redis
SET demo:packet "V100DATA-123"
GETRANGE demo:packet 0 3
# "V100"

GETRANGE demo:packet 4 -1
# "DATA-123"
```

Kiểu truy cập này phù hợp khi định dạng lưu trữ định nghĩa **vị trí byte cố định**. Nếu dữ liệu là JSON, CSV hoặc văn bản Unicode không có khung byte cố định, dùng `GETRANGE` theo chỉ số tùy ý rất dễ cắt giữa một trường hoặc một ký tự.

## 3. Ghi đè một khoảng byte bằng `SETRANGE`

### 3.1. `SETRANGE` thay byte tại vị trí, không chèn ký tự

Cú pháp:

```redis
SETRANGE key offset value
```

Lệnh ghi chuỗi byte `value` vào giá trị đang có, **bắt đầu từ byte ở chỉ số `offset`**. Những byte nằm trong phần bị ghi đè được thay thế; các byte sau đó vẫn ở vị trí cũ nếu không nằm trong đoạn ghi. Đây là thao tác **overwrite**, không phải `StringBuilder.insert()`.

Ví dụ:

```redis
SET demo:patch "Hello"
SETRANGE demo:patch 1 "it"
# (integer) 5 — độ dài hiện tại của Redis String tính bằng byte

GET demo:patch
# "Hitlo"
```

Giải thích:

```text
Trước:   H e l l o
Index:   0 1 2 3 4

SETRANGE offset=1 value="it"
         ↓ ↓
Sau:    H i t l o
```

Nếu kỳ vọng “Hitello” hay “Hito” thì đã nhầm `SETRANGE` với thao tác chèn hoặc thay cả chuỗi. Để thay đổi cấu trúc văn bản phức tạp, cần dùng định dạng lưu phù hợp hơn hoặc xử lý ở tầng ứng dụng với chiến lược đồng thời rõ ràng.

### 3.2. Ghi ngay sau byte cuối

Khi offset bằng độ dài hiện tại, phần mới nằm sau đoạn cũ:

```redis
SET demo:patch "Hello"
SETRANGE demo:patch 5 "!"
# (integer) 6

GET demo:patch
# "Hello!"
```

Trường hợp này nhìn giống append, nhưng phải biết **đúng offset theo byte**. Nếu nhiều client đồng thời thay đổi cùng key, lấy `STRLEN` rồi `SETRANGE` là **hai lệnh tách biệt**; offset vừa đọc có thể đã cũ. Để nối thêm một đoạn không phụ thuộc vị trí, `APPEND` thường thích hợp hơn.

### 3.3. Offset vượt quá độ dài hiện tại: Redis đệm byte zero

Nếu offset lớn hơn số byte đang có, Redis tạo phần khoảng trống bằng các byte `0x00` để nối tới vị trí mới:

```redis
SET demo:gap "AB"
SETRANGE demo:gap 5 "Z"
# (integer) 6

STRLEN demo:gap
# (integer) 6
```

Biểu diễn chính xác theo byte:

```text
Index:  0    1    2    3    4    5
Byte:   41   42   00   00   00   5A
Text:    A    B   NUL  NUL  NUL   Z
```

Đừng kết luận Redis tự thêm dấu cách hoặc ký tự `'0'`; nó thêm **byte zero**, có thể gây vấn đề nếu ứng dụng xem value là văn bản thông thường. Với `StringRedisTemplate`, đọc và in chuỗi có byte NUL có thể gây nhầm lẫn khi hiển thị log; nên xem dữ liệu theo hex khi điều tra.

**Rủi ro bộ nhớ:** Không gọi `SETRANGE` với offset khổng lồ lấy trực tiếp từ input chưa kiểm soát. Redis có thể phải cấp phát một vùng byte lớn để lấp khoảng trống, làm tăng tiêu thụ bộ nhớ hoặc dẫn đến lỗi vì giới hạn kích thước/`maxmemory`. Phải có giới hạn offset và chiều dài payload theo hợp đồng dữ liệu.

### 3.4. Khóa chưa tồn tại

Khi dùng `SETRANGE` với một giá trị không rỗng trên key chưa tồn tại, Redis có thể tạo key mới; những byte trước offset được điền zero nếu offset lớn hơn 0. Key mới không tự có TTL, trừ khi ứng dụng thiết lập TTL riêng.

Ví dụ:

```redis
DEL demo:new-range
SETRANGE demo:new-range 3 "X"
STRLEN demo:new-range
# (integer) 4
```

Value nhận được tương ứng `00 00 00 58` (hex), không phải chuỗi chỉ có một ký tự `X`. Offset phải không âm; các giá trị âm không phải vị trí ghi hợp lệ cho `SETRANGE`.

## 4. Nối thêm bằng `APPEND`

### 4.1. Cú pháp và giá trị trả về

```redis
APPEND key value
```

`APPEND` nối dãy byte mới vào **cuối** value hiện tại. Redis trả về **độ dài mới theo byte**.

```redis
SET demo:append "Hello"
APPEND demo:append " "
# (integer) 6

APPEND demo:append "Redis"
# (integer) 11

GET demo:append
# "Hello Redis"

STRLEN demo:append
# (integer) 11
```

Nếu key không tồn tại, `APPEND` tạo một Redis String với giá trị được truyền vào:

```redis
DEL demo:append-new
APPEND demo:append-new "first"
# (integer) 5

GET demo:append-new
# "first"
```

Nếu key đang chứa một Redis Hash, List hay kiểu không tương thích, lệnh báo `WRONGTYPE` thay vì tự chuyển sang String.

### 4.2. Một `APPEND` là thao tác nguyên tử

Redis thực thi một lệnh `APPEND` như một thao tác riêng lẻ. Nếu nhiều client đồng thời gọi:

```redis
APPEND demo:messages "A"
APPEND demo:messages "B"
```

Redis xử lý từng lệnh, nên byte của **một payload `APPEND` không bị một payload khác chen vào giữa**. Nhưng thứ tự nhận và xử lý lệnh từ nhiều client không phải thứ tự nghiệp vụ được bảo đảm. Kết quả có thể là `AB` hoặc `BA` tùy thứ tự Redis xử lý.

Tính nguyên tử của một lệnh **không** tự mang đến:

- Chống ghi trùng khi client retry sau timeout.
- Sắp xếp theo timestamp nghiệp vụ giữa nhiều producer.
- Chỉ append khi thỏa một điều kiện đã kiểm tra từ lệnh trước.
- Giao dịch nhiều key.
- Đóng gói record, metadata, khả năng tiêu thụ riêng từng record.

Muốn lưu hàng đợi, bản ghi sự kiện hay chuỗi message có nhiều consumer, nên đánh giá **Redis Stream (`XADD`/consumer groups)** hoặc List (`LPUSH`/`RPUSH`) thay vì dùng một String `APPEND` lớn dần không giới hạn.

### 4.3. `APPEND` khác đọc–nối–ghi

Mẫu nguy hiểm khi có nhiều request:

```java
// Tránh khi nhiều client cập nhật cùng key:
String old = redis.opsForValue().get(key);
redis.opsForValue().set(key, (old == null ? "" : old) + suffix);
```

Giữa `get()` và `set()`, client khác có thể đã cập nhật key. Lệnh `set()` sau đó có thể ghi đè toàn bộ dữ liệu mới. Ngoài ra, `SET` thông thường có thể làm mất TTL hiện tại nếu không dùng cơ chế giữ lại thời hạn.

Khi mục tiêu chỉ là nối byte, dùng:

```java
redis.opsForValue().append(key, suffix);
```

Cách này giao việc nối cho Redis xử lý bằng một lệnh, tránh read-modify-write hai bước tại ứng dụng. Nếu cần **append có điều kiện** (ví dụ kiểm tra version trước khi ghi), cần một giao thức đồng thời như Lua script/Redis Functions hoặc `WATCH`/`MULTI`/`EXEC` phù hợp.

## 5. Đo kích thước bằng `STRLEN`

`STRLEN key` trả về số byte của value tại key:

```redis
SET demo:length "ABC"
STRLEN demo:length
# (integer) 3

APPEND demo:length "DEF"
STRLEN demo:length
# (integer) 6
```

Với key không tồn tại, `STRLEN` trả về `0`. Với key thuộc kiểu dữ liệu Redis khác String, lệnh có thể báo lỗi `WRONGTYPE`.

`STRLEN` hữu ích để kiểm tra giới hạn kích thước payload và xác định offset trong giao thức nhị phân; nhưng cần lưu ý:

1. Chỉ số này là **số byte**, không phải số chữ, số Unicode code point hay số ký tự người dùng nhìn thấy.
2. Kết quả là độ dài tại **thời điểm Redis thực hiện lệnh**, có thể thay đổi ngay sau đó nếu các client khác đang ghi.
3. Không có `STRLEN` nào tự bảo đảm hai lệnh `STRLEN` rồi `SETRANGE` được thực hiện như một thao tác atomic.

## 6. Phân biệt đọc, ghi đè và nối: ví dụ tổng hợp

Giả sử key chứa `"012345"`:

```redis
SET demo:all "012345"

GETRANGE demo:all 1 3
# "123" — chỉ đọc; giá trị gốc không đổi

SETRANGE demo:all 2 "AB"
# (integer) 6

GET demo:all
# "01AB45" — thay thế hai byte tại vị trí 2 và 3

APPEND demo:all "Z"
# (integer) 7

GET demo:all
# "01AB45Z"

STRLEN demo:all
# (integer) 7
```

| Lệnh | Có thay đổi value? | Làm gì với byte cũ? | Kết quả đặc trưng |
|---|---|---|---|
| `GETRANGE` | Không | Đọc một khoảng byte | Dãy byte được đọc |
| `SETRANGE` | Có | Ghi đè từ offset; có thể kéo dài value | Độ dài mới tính bằng byte |
| `APPEND` | Có | Giữ byte cũ, nối byte mới ở cuối | Độ dài mới tính bằng byte |
| `STRLEN` | Không | Chỉ đo | Số byte |

Một câu hỏi thực hành thường gặp: “Muốn sửa byte thứ 4 của một header cố định?” Dùng `SETRANGE` với offset tương ứng. “Muốn lấy 12 byte cuối?” Dùng `GETRANGE key -12 -1`. “Muốn nối một marker ở cuối?” Dùng `APPEND`. “Muốn biết số ký tự Unicode trong nội dung?” `STRLEN` **không** trả lời đúng câu hỏi đó.

## 7. Tương ứng trong `StringRedisTemplate`

Với Spring Boot sử dụng Spring Data Redis, cấu hình kết nối Redis ví dụ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

`StringRedisTemplate` dùng các serializer dành cho chuỗi, thường mã hóa key/value dưới dạng UTF-8. Nó phù hợp với **văn bản hoặc dữ liệu ASCII** mà ứng dụng có thể biểu diễn an toàn thành Java `String`.

### 7.1. Ví dụ service thao tác range và append

```java
package com.example.redis.string;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.stereotype.Service;

@Service
public class TextSegmentService {

    private final StringRedisTemplate template;

    public TextSegmentService(StringRedisTemplate template) {
        this.template = template;
    }

    public void create(String key, String value, Duration ttl) {
        template.opsForValue().set(key, value, ttl);
    }

    public String readBytes(String key, long start, long end) {
        // start/end là BYTE offset ở Redis, không phải Java char index.
        return template.opsForValue().get(key, start, end);
    }

    public void overwriteBytes(String key, String fragment, long offset) {
        template.opsForValue().set(key, fragment, offset);
    }

    public Integer append(String key, String suffix) {
        return template.opsForValue().append(key, suffix);
    }

    public Long byteLength(String key) {
        return template.opsForValue().size(key);
    }

    public String readAll(String key) {
        return template.opsForValue().get(key);
    }
}
```

Ở đây:

- `create()` ghi toàn bộ value và gắn TTL qua `Duration`.
- `readBytes()` sử dụng `ValueOperations.get(K key, long start, long end)` để gọi cơ chế đọc khoảng của Redis; kết quả là `String` được deserialize từ byte.
- `overwriteBytes()` gọi overload `set(K key, V value, long offset)` để sửa byte từ offset.
- `append()` nối suffix và trả độ dài mới nếu operation có kết quả.
- `byteLength()` đo kích thước Redis String theo byte.

**Quan trọng:** Tên `readBytes` chỉ nhấn mạnh **offset tính theo byte**; kiểu trả về thực tế của `StringRedisTemplate` vẫn là Java `String`. Nếu khoảng byte cắt ngang một ký tự UTF-8 hoặc value chứa byte nhị phân tùy ý, đường deserialize sang `String` có thể không tái tạo byte gốc đúng ý. Khi cần bảo toàn byte, dùng API raw bytes ở phần sau.

### 7.2. Gọi service trong một luồng đơn giản

```java
service.create("demo:profile:header", "USER0001", Duration.ofMinutes(5));

String prefix = service.readBytes("demo:profile:header", 0, 3);
// "USER"

service.overwriteBytes("demo:profile:header", "99", 4);
// USER9901

Integer length = service.append("demo:profile:header", "-OK");
// 11 byte

String full = service.readAll("demo:profile:header");
// "USER9901-OK"
```

Với các giá trị ASCII ở đây, 1 ký tự = 1 byte nên có thể so sánh kết quả trực quan. Nếu thay bằng ký tự Unicode, offset cần tính lại theo **mảng byte sau serialization**.

### 7.3. Không mặc định `RedisTemplate` nào cũng là UTF-8

`RedisTemplate<String, MyObject>` có thể dùng `JdkSerializationRedisSerializer`, JSON serializer hoặc serializer tự cấu hình. Nếu code gọi `getRange()` hoặc `set(..., offset)` trên value đã được tuần tự hóa thành cấu trúc nhị phân phức tạp, đoạn byte có thể nằm trong **header của serializer** hoặc bên giữa object, không phải “phần text” ứng dụng mong đợi.

Ví dụ:

```text
Java object ──JDK serializer──► [binary header][class metadata][data]
                                  ↑
                      Offset 0 không phải ký tự đầu của field name
```

**Không dùng `SETRANGE` để sửa một vài byte trong payload JDK-serialized, JSON hay nén nếu không sở hữu và hiểu rõ wire format.** Phần dữ liệu sau khi sửa có thể không giải mã được. Với entity, cache object hoặc hash do Redis Repository quản lý, nên cập nhật qua API ánh xạ phù hợp.

## 8. Truy cập raw bytes khi cần xử lý nhị phân chính xác

Giả sử ứng dụng lưu một payload nhị phân hoặc cần kiểm tra chính xác byte UTF-8. Thay vì nhận `String` đã được decode, hãy lấy `byte[]` trực tiếp thông qua `RedisCallback`.

```java
package com.example.redis.string;

import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RawByteRangeReader {

    private final StringRedisTemplate redis;

    public RawByteRangeReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public byte[] readExactBytes(String key, long start, long end) {
        byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);

        return redis.execute(
            (RedisCallback<byte[]>) connection ->
                connection.stringCommands().getRange(rawKey, start, end)
        );
    }
}
```

Đoạn mã dùng Redis connection abstraction của Spring nhưng đọc **mảng byte nguyên trạng** do Redis trả về. Cần dùng đúng key serializer: ví dụ đang dùng `StringRedisTemplate` với key UTF-8 nên mã hóa key qua `StandardCharsets.UTF_8`. Nếu Redis key do một serializer khác tạo, ghép key bằng UTF-8 thủ công có thể truy vấn sai tên vật lý.

Để xử lý kết quả:

```java
byte[] fragment = reader.readExactBytes("demo:utf8", 1, 1);
System.out.println(java.util.HexFormat.of().formatHex(fragment));
// Có thể là "c3" nếu giá trị Redis là "AéB" được mã hóa UTF-8.
```

Ở ví dụ trên, `0xC3` chỉ là **byte đầu tiên** của ký tự `é`, nên chưa tạo thành một chuỗi UTF-8 hoàn chỉnh. Raw bytes cho phép ứng dụng phân biệt chính xác điều này; nếu lập tức chuyển nó thành Java String, bộ giải mã có thể xử lý byte không hợp lệ bằng ký tự thay thế hoặc báo lỗi, tùy cấu hình.

Nếu ứng dụng chủ yếu làm việc với binary, có thể cấu hình riêng một `RedisTemplate<String, byte[]>` và serializer byte-array tương ứng. Điều quan trọng là **không trộn serializer text và binary trên cùng keyspace một cách tình cờ**.

## 9. Cắt UTF-8 giữa một ký tự: lỗi dễ bỏ sót

Ví dụ `AéB` có byte `41 C3 A9 42`. Các khoảng khác nhau:

| Lệnh | Byte trả về (hex) | Diễn giải |
|---|---|---|
| `GETRANGE key 0 0` | `41` | Chuỗi `A` hợp lệ |
| `GETRANGE key 1 1` | `C3` | Byte đầu của `é`, chưa đủ để giải mã UTF-8 |
| `GETRANGE key 1 2` | `C3 A9` | Chuỗi `é` hợp lệ |
| `GETRANGE key 3 3` | `42` | Chuỗi `B` hợp lệ |
| `GETRANGE key 0 -1` | `41 C3 A9 42` | Toàn bộ `AéB` |

Thử:

```redis
SET demo:utf8 "AéB"
STRLEN demo:utf8
# (integer) 4

GETRANGE demo:utf8 1 2
# "é" nếu terminal/redis-cli hiển thị UTF-8 đúng
```

Với `GETRANGE demo:utf8 1 1`, đừng dựa vào ký tự in trên terminal làm bằng chứng byte; terminal có thể hiển thị ký tự lỗi hoặc escape sequence. Hãy kiểm tra dạng hex khi cần chẩn đoán.

### 9.1. `SETRANGE` có thể làm hỏng UTF-8 hợp lệ

Giả sử ban đầu là `AéB` (hex `41 C3 A9 42`):

```redis
SETRANGE demo:utf8 1 "Z"
```

Sau lệnh, byte có thể thành `41 5A A9 42`. Byte `A9` bị bỏ lại phía sau là một byte continuation của UTF-8 không có byte dẫn phù hợp. Value Redis vẫn là một dãy byte hợp lệ đối với Redis, **nhưng không còn là văn bản UTF-8 hợp lệ**.

Đó là lý do thao tác range phù hợp với:

- Payload nhị phân có cấu trúc và offset cố định.
- Chuỗi ASCII có hợp đồng dữ liệu rõ.
- Header/segment có quy định byte length.
- Trường hợp quan sát/cắt một đoạn byte có chủ đích.

Không phù hợp để chỉnh “ký tự thứ N” trong văn bản tiếng Việt hoặc Unicode mà không tính đúng ranh giới mã hóa.

### 9.2. Muốn lấy ký tự Unicode, làm thế nào?

Nếu cần cắt theo ký tự của văn bản:

1. Đọc chuỗi theo serializer văn bản đang dùng, không cắt byte Redis tùy ý.
2. Xử lý dựa trên code point hoặc grapheme cluster nếu yêu cầu theo ký tự người dùng nhìn thấy.
3. Ghi lại giá trị theo cách có kiểm soát đồng thời.

Nếu văn bản lớn và cần chỉnh sửa từng đoạn thường xuyên, thiết kế một Redis String duy nhất có thể không phù hợp; cân nhắc chia dữ liệu thành các phần độc lập hoặc lưu cấu trúc trong storage thích hợp.

## 10. TTL khi đọc range, ghi range và append

Thời hạn của key tồn tại độc lập với ý nghĩa của khoảng byte. `GETRANGE` và `STRLEN` là lệnh đọc nên không đặt lại TTL.

`APPEND` và `SETRANGE` khi **chỉnh sửa key đã tồn tại** thường giữ nguyên thời hạn hiện có; chúng không tự làm mới TTL như thao tác ghi đè toàn bộ bằng `SET` thông thường.

Ví dụ:

```redis
SET demo:ttl "ABCD" EX 120
TTL demo:ttl
# Gần 120 (tùy thời gian đã trôi)

APPEND demo:ttl "E"
TTL demo:ttl
# Tiếp tục đếm xuống, không tự quay về 120

SETRANGE demo:ttl 0 "Z"
TTL demo:ttl
# Vẫn là TTL còn lại của key

GET demo:ttl
# "ZBCDE"
```

So sánh với:

```redis
SET demo:ttl "new-value"
TTL demo:ttl
# -1 — SET thông thường làm mất TTL cũ
```

Redis có tùy chọn `KEEPTTL` với `SET` khi muốn thay toàn bộ value nhưng giữ TTL hiện tại. Spring Data Redis cung cấp các overload và API quản lý TTL tương ứng; khi dùng template, phải kiểm tra chính thao tác ghi đang gọi có ngữ nghĩa bảo toàn TTL hay không.

Hai trường hợp cần phân biệt:

| Trường hợp | Hành vi |
|---|---|
| `APPEND` hoặc `SETRANGE` trên key **đã có TTL** | Chỉnh sửa value, TTL cũ vẫn tiếp tục |
| `APPEND` hoặc `SETRANGE` tạo **key mới** | Key mới không tự có TTL; cần `EXPIRE` hoặc cơ chế thiết lập thời hạn |

Nếu cần bảo đảm khóa mới vừa được tạo phải có TTL ngay cả khi nhiều client cùng thao tác, phải thiết kế giao thức atomic phù hợp (ví dụ Lua/Redis Function). Gọi `APPEND` rồi `EXPIRE` thành hai lệnh riêng có một khoảng thời gian giữa chúng; không mặc định đó là một transaction.

### Khi key biến mất giữa hai thao tác

`TTL = -2` hoặc `GETRANGE` trả rỗng có thể xuất phát từ expiration, eviction, thao tác xóa hoặc key chưa từng tồn tại. Một byte-range read không cung cấp metadata về lý do mất key. Nếu logic cần phân biệt các trường hợp, ứng dụng phải kết hợp thiết kế state, metrics hoặc event quan sát thích hợp.

## 11. Tính nguyên tử và các tình huống truy cập đồng thời

Redis thực thi **mỗi lệnh** `GETRANGE`, `SETRANGE`, `APPEND`, `STRLEN` như một thao tác Redis riêng. Điều này khác với bảo đảm của một **chuỗi nhiều lệnh**.

### 11.1. Hai `SETRANGE` cùng sửa một đoạn

Ví dụ:

```text
Giá trị ban đầu: "abcdefgh"

Client A: SETRANGE key 2 "XXX"
Client B: SETRANGE key 3 "YYY"
```

Cả hai lệnh đều atomic theo từng lệnh, nhưng chúng ghi đè những byte có giao nhau. Kết quả cuối cùng phụ thuộc thứ tự Redis thực thi; không có cơ chế phát hiện xung đột mặc định.

Nếu những đoạn cần cập nhật bởi nhiều worker:

- Phân chia vùng byte không giao nhau nếu giao thức cho phép.
- Dùng version và kiểm tra điều kiện cập nhật khi thực sự cần tính nhất quán.
- Dùng script hoặc transaction với cơ chế optimistic locking, khi tính đúng đắn đòi hỏi nhiều thao tác phải đi cùng nhau.

### 11.2. `STRLEN` rồi `SETRANGE` không tương đương `APPEND`

```text
Client A: STRLEN key → 5
Client B: APPEND key "B" → key dài 6
Client A: SETRANGE key 5 "A"
```

Client A có thể **ghi đè** byte do B vừa nối ở offset 5. Nếu mục tiêu là nối thêm dữ liệu, dùng `APPEND` thay vì một chuỗi lệnh tự tính offset.

### 11.3. Dùng `APPEND` để ghi record có giới hạn

Một Redis String được nối mãi sẽ tăng kích thước. Nếu nối JSON object liên tiếp:

```text
{"event":1}{"event":2}{"event":3}
```

không có dấu phân tách rõ ràng, người đọc khó xác định ranh giới record và khó đọc tiếp từ vị trí hợp lệ. Ngay cả khi thêm newline, các yêu cầu khác như retry, thứ tự, retention, multi-consumer và ack vẫn không tự được giải quyết.

Khi mục tiêu là:

- **Bộ đếm số lần**: dùng `INCR`/`INCRBY` thay vì nối ký tự `"1"`.
- **Queue đơn giản**: đánh giá Redis List.
- **Event log hoặc message có consumer groups**: đánh giá Redis Streams.
- **Cập nhật object một phần**: cân nhắc Redis Hash nếu các field độc lập.
- **Payload nhị phân có layout cố định**: `SETRANGE`/`GETRANGE` có thể phù hợp nếu schema được kiểm soát.

## 12. Kiểm thử hành vi trong Spring Data Redis

Một bài kiểm thử tích hợp có thể dùng `StringRedisTemplate` và Redis thử nghiệm để quan sát đúng hành vi lệnh. Ví dụ dưới đây viết ở mức JUnit 5 với context Spring Boot đã cấu hình kết nối Redis; chỉ chạy trên Redis dành riêng cho test.

```java
package com.example.redis.string;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisByteRangeIntegrationTest {

    private static final String KEY = "test:range:demo";

    @Autowired
    private StringRedisTemplate redis;

    @AfterEach
    void cleanup() {
        redis.delete(KEY);
    }

    @Test
    void getRangeUsesInclusiveByteIndexes() {
        redis.opsForValue().set(KEY, "HELLO");

        assertEquals("HEL", redis.opsForValue().get(KEY, 0, 2));
        assertEquals("LO", redis.opsForValue().get(KEY, -2, -1));
        assertEquals(5L, redis.opsForValue().size(KEY));
    }

    @Test
    void setRangeOverwritesInsteadOfInserting() {
        redis.opsForValue().set(KEY, "Hello");
        redis.opsForValue().set(KEY, "it", 1);

        assertEquals("Hitlo", redis.opsForValue().get(KEY));
    }

    @Test
    void appendAddsBytesAndReturnsNewLength() {
        redis.opsForValue().set(KEY, "AB");
        Integer newLength = redis.opsForValue().append(KEY, "CD");

        assertEquals(4, newLength);
        assertEquals("ABCD", redis.opsForValue().get(KEY));
    }

    @Test
    void appendAndSetRangePreserveExistingTtl() {
        redis.opsForValue().set(KEY, "AB", Duration.ofMinutes(2));
        redis.opsForValue().append(KEY, "C");
        redis.opsForValue().set(KEY, "Z", 0);

        Long ttl = redis.getExpire(KEY);
        assertTrue(ttl != null && ttl > 0);
        assertEquals("ZBC", redis.opsForValue().get(KEY));
    }
}
```

Điều kiện quan trọng của ví dụ:

- Redis phục vụ test phải riêng, không được trỏ vào Redis production.
- `@SpringBootTest` phải tìm được cấu hình kết nối Redis trong môi trường chạy test.
- Test phải dọn chính key nó sở hữu; nếu test chạy song song trên cùng Redis, nên dùng prefix/ID riêng cho từng test.
- Test TTL không so bằng đúng giá trị ban đầu vì thời gian thực đã trôi; nó chỉ kiểm tra TTL vẫn còn dương sau các thao tác.

### Kiểm tra chính xác byte UTF-8

Khi test dữ liệu đa byte, có thể xác minh raw range bằng byte array:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;

redis.opsForValue().set(KEY, "AéB");

byte[] keyBytes = KEY.getBytes(StandardCharsets.UTF_8);
byte[] firstByteOfEAcute = redis.execute(
    (RedisCallback<byte[]>) connection ->
        connection.stringCommands().getRange(keyBytes, 1, 1)
);

assertArrayEquals(new byte[] {(byte) 0xC3}, firstByteOfEAcute);
```

Ví dụ này đo đúng dữ liệu trả về ở tầng Redis, không phụ thuộc Java `String` hiển thị byte UTF-8 không hoàn chỉnh như thế nào.

## 13. Tình huống sử dụng thực tế

### 13.1. Đọc header của payload nhị phân

Một service lưu key với format do nhóm tự định nghĩa:

```text
[4 byte magic][1 byte version][payload bytes...]
```

Thay vì đọc hàng megabyte payload chỉ để xác minh version:

```redis
GETRANGE payload:123 0 4
```

Ứng dụng cần tự kiểm tra đủ 5 byte và diễn giải đúng schema. `GETRANGE` giúp giảm số byte truyền về client nhưng không tự hiểu cấu trúc header.

### 13.2. Vá một trường cố định trong dữ liệu ASCII

Giả sử format là `STATUS=0;COUNT=0010` và offset của byte trạng thái đã được định nghĩa:

```redis
SET demo:fixed "STATUS=0;COUNT=0010"
SETRANGE demo:fixed 7 "1"
GET demo:fixed
# "STATUS=1;COUNT=0010"
```

Cách này chỉ phù hợp khi layout cố định và application kiểm soát việc cập nhật. Nếu một field có thể dài/ngắn tùy ý, việc ghi byte theo offset sẽ làm sai layout.

### 13.3. Nối suffix vào một giá trị ASCII

```redis
SET demo:trace "job-123"
APPEND demo:trace ":done"
GET demo:trace
# "job-123:done"
```

Với dữ liệu nhỏ và mỗi lần nối độc lập, `APPEND` đơn giản. Nếu phải thu thập log sự kiện dài hạn, có nhiều consumer hoặc cần replay, nên chọn cấu trúc dữ liệu khác để tránh một String không giới hạn kích thước.

### 13.4. Cắt một đoạn văn bản Unicode

Yêu cầu “lấy 10 ký tự đầu trong một đoạn tiếng Việt” **không nên** triển khai bằng `GETRANGE key 0 9`. Đây là 10 **byte**, có thể cắt ngang ký tự Unicode. Phải đọc và xử lý chuỗi ở mức text phù hợp, hoặc thiết kế index/offset theo byte và bảo đảm ranh giới UTF-8 ngay từ lúc ghi.

## 14. Lưu ý về hiệu năng và giới hạn

### 14.1. Giá trị lớn và chi phí mạng

`GETRANGE` chỉ trả về phần byte được yêu cầu, nên giảm lượng dữ liệu truyền đi khi chỉ cần một đoạn nhỏ. Tuy nhiên, Redis vẫn lưu cả value trong bộ nhớ; `GETRANGE` **không biến Redis String thành một hệ thống chunk storage**.

`APPEND` và `SETRANGE` làm value thay đổi kích thước có thể dẫn đến cấp phát thêm bộ nhớ. Một key có giá trị rất lớn có thể gây áp lực:

- RAM Redis và cơ chế eviction.
- Băng thông mạng khi đọc toàn bộ.
- Chi phí sao chép/replication/persistence tùy cấu hình.
- Độ trễ của thao tác xử lý value lớn.
- Khả năng khôi phục hoặc di chuyển dữ liệu giữa các node.

Đặt giới hạn kích thước ở lớp ứng dụng và đo Redis memory/latency; đừng dùng `APPEND` không giới hạn như một file log dài vô hạn.

### 14.2. `SETRANGE` không phải ghi ngẫu nhiên trên đĩa

Redis là kho dữ liệu chủ yếu trong bộ nhớ. `SETRANGE` cho phép truy cập byte theo vị trí trong một **Redis String**, nhưng không có nghĩa mỗi lệnh là một bản cập nhật cố định tại một block trên disk. Redis vẫn phải quản lý cấu trúc dữ liệu trong RAM và cơ chế lưu bền vững theo cấu hình server.

### 14.3. Quản lý key và serializer

Khi triển khai Spring Data Redis:

- Dùng namespace key rõ ràng, ví dụ `shop:prod:v1:segment:123`, để tránh một service đọc nhầm key của service khác.
- Thống nhất serializer ở **mọi** đường đọc/ghi tới cùng key.
- Chỉ dùng `SETRANGE` trên dữ liệu mà ứng dụng biết chính xác wire format và offset.
- Khi có nhiều service/phiên bản cùng truy cập, xem xét tương thích định dạng và đồng thời.
- Kiểm tra `TYPE key` và `STRLEN key` trong môi trường quan sát nếu xảy ra `WRONGTYPE` hoặc nghi ngờ sai định dạng.

### 14.4. Các sai lầm hay gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Tưởng `end` của `GETRANGE` là exclusive | Đọc thiếu hoặc dư một byte | Nhớ `start` và `end` đều inclusive |
| Dùng Java char index làm Redis offset | Cắt giữa byte của UTF-8 | Tính offset theo encoding; dùng raw bytes khi cần |
| Nghĩ `SETRANGE` chèn byte | Ghi đè dữ liệu sau offset | Dùng đúng thao tác hoặc thiết kế lại format |
| Ghi `SETRANGE` với offset rất lớn | Tạo vùng zero padding, dùng nhiều RAM | Giới hạn offset và payload |
| Dùng `STRLEN + SETRANGE` để append | Race condition khi đồng thời | Dùng `APPEND` |
| Dùng `GET + SET` để append | Lost update; có thể mất TTL | Dùng `APPEND` hoặc cơ chế atomic phù hợp |
| Dùng `APPEND` làm event queue vô hạn | Value phình to, thiếu semantics message | Dùng List/Stream theo nhu cầu |
| Dùng `SETRANGE` sửa object serializer nhị phân | Dữ liệu không deserialize được | Cập nhật qua serializer/mapping đúng |
| Kỳ vọng `APPEND` tự refresh TTL | Key vẫn hết hạn theo thời hạn cũ | Đặt lại TTL có chủ đích khi cần |
| Gộp nhiều lệnh và nghĩ chúng atomic | Các client khác chen vào giữa | Dùng transaction/script/Function khi cần |

## 15. Bài thực hành từng bước với Redis CLI

Thử trên Redis riêng để học tập. Mục tiêu là nhìn thấy sự khác biệt giữa khoảng byte và nối chuỗi.

**Bước 1 — Đọc một đoạn:**

```redis
SET lab:bytes "0123456789"
GETRANGE lab:bytes 2 5
# "2345"

GETRANGE lab:bytes -3 -1
# "789"

STRLEN lab:bytes
# (integer) 10
```

**Bước 2 — Ghi đè tại offset:**

```redis
SETRANGE lab:bytes 3 "ABC"
# (integer) 10

GET lab:bytes
# "012ABC6789"
```

**Bước 3 — Nối vào cuối:**

```redis
APPEND lab:bytes "!"
# (integer) 11

GET lab:bytes
# "012ABC6789!"
```

**Bước 4 — Kiểm tra zero padding:**

```redis
DEL lab:gap
SETRANGE lab:gap 4 "X"
# (integer) 5

STRLEN lab:gap
# (integer) 5
```

Value có 4 byte `0x00` trước chữ `X`. Hãy quan sát bằng công cụ hiển thị hex để tránh nhầm chuỗi trống với byte zero.

**Bước 5 — Quan sát TTL không được làm mới:**

```redis
SET lab:ttl "A" EX 60
APPEND lab:ttl "B"
SETRANGE lab:ttl 0 "Z"
TTL lab:ttl
# Giá trị vẫn đếm xuống từ thời điểm SET ban đầu

GET lab:ttl
# "ZB" nếu key chưa hết hạn
```

**Bước 6 — So sánh byte và Unicode:**

```redis
SET lab:utf8 "AéB"
STRLEN lab:utf8
# (integer) 4

GETRANGE lab:utf8 1 2
# "é" nếu console giải mã UTF-8 đúng
```

Đối với `GETRANGE lab:utf8 1 1`, kết quả là một byte `0xC3`: không cố coi nó là ký tự Unicode hoàn chỉnh.

## 16. Câu hỏi tự kiểm tra

**1. `GETRANGE k 0 4` đọc tối đa bao nhiêu byte?**  
Năm byte vì `start` và `end` đều inclusive.

**2. `GETRANGE k -1 -1` có nghĩa gì?**  
Đọc byte cuối cùng nếu key có dữ liệu.

**3. Với `SET k "HELLO"`, kết quả của `SETRANGE k 1 "AB"` là gì?**  
`"HABLO"`. Hai byte ở vị trí 1 và 2 được ghi đè; các byte còn lại giữ nguyên.

**4. Vì sao `SETRANGE k 1000000 "X"` có thể nguy hiểm dù chỉ ghi một ký tự?**  
Redis có thể phải tạo phần đệm bằng byte zero từ độ dài cũ tới offset mới, khiến value trở nên rất lớn và tiêu tốn bộ nhớ.

**5. Hai request đồng thời muốn nối suffix. Nên dùng `STRLEN` rồi `SETRANGE` hay `APPEND`?**  
`APPEND` vì việc nối diễn ra trong một lệnh Redis; chuỗi `STRLEN` rồi `SETRANGE` có thể bị race.

**6. Redis `STRLEN` của `"AéB"` là bao nhiêu nếu giá trị được mã hóa UTF-8?**  
Bốn byte: `41 C3 A9 42`. Điều này khác số ký tự hiển thị.

**7. Vì sao không nên dùng `GETRANGE` theo offset byte để lấy “10 ký tự đầu” của tiếng Việt?**  
Vì ký tự UTF-8 có thể dài nhiều byte, một khoảng 10 byte có thể cắt giữa một ký tự.

**8. `APPEND` vào key có TTL 30 giây có tự đưa TTL về 30 giây không?**  
Không. TTL hiện có tiếp tục đếm xuống; muốn làm mới hạn phải có thao tác đặt TTL phù hợp.

**9. Khi nào cần dùng RedisCallback trả `byte[]` thay vì `StringRedisTemplate.get(key, start, end)`?**  
Khi cần bảo toàn chính xác payload binary hoặc phần range có thể chứa byte UTF-8 không hoàn chỉnh.

**10. Vì sao `APPEND` không tự thay thế Redis Streams cho hệ thống event?**  
Vì một dãy byte được nối không tự có ID message, consumer group, acknowledgment, phân phối theo consumer hay chiến lược retention.

## 17. Những điểm cần ghi nhớ

- **`GETRANGE` đọc một khoảng byte** với chỉ số từ 0, hai đầu mút inclusive và hỗ trợ chỉ số âm.
- **`SETRANGE` ghi đè byte từ offset**, không chèn ký tự; offset vượt độ dài làm phát sinh byte zero.
- **`APPEND` nối byte vào cuối** bằng một lệnh atomic và trả độ dài mới.
- **`STRLEN` đếm byte**, không đếm ký tự Unicode hoặc đơn vị `char` trong Java.
- Trong Spring Data Redis, `StringRedisTemplate.opsForValue()` cung cấp các API tương ứng, nhưng **offset vẫn luôn là byte offset** theo dữ liệu đã serialize.
- Với văn bản UTF-8 hoặc giá trị nhị phân, phải kiểm soát ranh giới mã hóa; sử dụng raw byte API khi cần giữ nguyên byte.
- Thao tác sửa range hoặc append trên key có TTL đang tồn tại **không tự refresh thời hạn**; key tạo mới cần chính sách TTL riêng.
- Một lệnh Redis atomic không làm cho cả chuỗi nhiều lệnh tự atomic. Cần thiết kế đồng thời theo ý nghĩa nghiệp vụ.

Hiểu chính xác **byte range**, **overwrite** và **append** giúp tận dụng Redis String hiệu quả cho dữ liệu có cấu trúc cố định, tránh lỗi Unicode và sử dụng đúng abstraction của Spring Data Redis khi nhiều request cùng cập nhật một khóa.
