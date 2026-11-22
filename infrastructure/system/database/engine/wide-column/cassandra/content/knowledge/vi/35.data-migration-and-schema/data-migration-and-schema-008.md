# Đối chiếu encoding, kiểu số, UUID, timestamp và timezone khi nhập

## Mục tiêu và ngữ cảnh

Trong một dự án **di chuyển dữ liệu vào Apache Cassandra**, việc một câu `INSERT` trả thành công mới chứng minh Cassandra đã nhận một mutation ở consistency level được yêu cầu. Nó **không chứng minh dữ liệu được diễn giải đúng** từ CSV, JSON, cơ sở dữ liệu nguồn hoặc API. Ví dụ, một số tiền có thể bị làm tròn khi đi qua `double`; một UUID có thể bị đổi định dạng; một timestamp không ghi offset có thể bị hiểu theo múi giờ của máy ETL; hoặc chuỗi tiếng Việt bị hỏng encoding nhưng vẫn được lưu như một giá trị `text` hợp lệ.

Bài này thuộc chương **Di chuyển và schema** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Chủ đề gắn với mô hình wide-column, khóa phân vùng, thiết kế bảng theo truy vấn, CQL, replication, mức nhất quán đọc/ghi, repair/compaction, xử lý lỗi và kết nối Java Driver 4.x.

Sau khi hoàn thành, bạn có thể:

1. Xây dựng **hợp đồng kiểu dữ liệu** trước khi import, xác định encoding nguồn, chuẩn Unicode, kiểu đích và cách xử lý lỗi.
2. Phân biệt `text`/`varchar` với `ascii`, mã hóa UTF-8, Unicode normalization và các lỗi CSV/JSON/BOM.
3. Chọn đúng `int`, `bigint`, `varint`, `decimal`, `float` và `double` mà không đánh mất độ chính xác khi chuyển kiểu.
4. Xác thực UUID canonical; phân biệt `uuid` với `timeuuid` và không dùng UUID như timestamp khi thiếu điều kiện.
5. Chuyển timestamp có **offset rõ ràng** thành instant, giữ thông tin timezone nghiệp vụ ở cột riêng khi cần, tránh nhầm `date`/`time` với thời điểm UTC.
6. Viết luồng ETL **parse → validate → normalize → bind → ghi → đối soát**, phân biệt lỗi đầu vào với write timeout.
7. Thực hành CQL và Java Driver để xác minh giá trị sau import theo primary key và manifest đáng tin cậy.

> **An toàn dữ liệu:** chỉ import ví dụ trong keyspace lab. Trong hệ thống thật, phải sao lưu và thử phục hồi, định nghĩa rollback/backfill, giới hạn tải lên Cassandra, bảo vệ PII/secret và kiểm chứng các mẫu biên trước khi chạy toàn bộ dữ liệu. Không sửa trực tiếp SSTable hay bỏ qua lỗi parse để “đủ số hàng”.

## 1. Vì sao migration phải bắt đầu từ hợp đồng dữ liệu?

Một pipeline thường đi qua nhiều ranh giới biểu diễn:

~~~mermaid
flowchart LR
    S["Nguồn: CSV / JSON / RDBMS"] --> B["Byte + encoding"]
    B --> P["CSV/JSON parser"]
    P --> V["Kiểm tra schema và giá trị"]
    V --> N["Chuẩn hóa có quy tắc"]
    N --> T["CQL typed binding"]
    T --> C["Cassandra replicas"]
    C --> R["Đọc đối soát"]
    M["Manifest / log nguồn độc lập"] -.-> R
    V -. "Không hợp lệ" .-> Q["Quarantine có mã lỗi"]
    T -. "Timeout / không xác định" .-> U["UNKNOWN_WRITE để xác minh"]
~~~

Mỗi ranh giới có một loại lỗi khác nhau:

| Ranh giới | Ví dụ lỗi | Phát hiện đúng |
| --- | --- | --- |
| Byte → ký tự | File Windows-1258 được đọc như UTF-8 | Decoder báo lỗi hoặc ký tự không khớp dữ liệu nguồn |
| Ký tự → trường | CSV có dấu phẩy nằm trong cặp dấu ngoặc kép | Parser đúng chuẩn CSV và kiểm tra số cột |
| Chuỗi → số | `9007199254740993` đi qua JavaScript `Number` | Giá trị đã bị mất chính xác trước khi tới Java |
| Chuỗi → UUID | `timeuuid` nhận UUID phiên bản 4 | Kiểm tra phiên bản UUID và hợp đồng schema |
| Chuỗi → thời điểm | `2026-11-21 16:30:00` không có zone | Không thể xác định UTC instant nếu thiếu quy tắc nguồn |
| Giá trị đã parse → Cassandra | Binding sai cột, null PK, CL timeout | Prepared statement typed, validation và ACK/UNKNOWN |
| Cassandra → ứng dụng đọc | Query nhìn thấy một phiên bản cũ | Đọc theo CL, đối soát nguồn, kiểm repair và thời điểm |

**Quy tắc:** dữ liệu **không rõ nghĩa** phải được đánh dấu và đưa vào hàng đợi kiểm tra (*quarantine*) thay vì đoán. Đặc biệt với ngày giờ và tiền, một phép chuyển đổi “đoán cho hợp lệ” có thể tạo sai lệch nghiệp vụ không thể phát hiện bằng `COUNT(*)`.

### Mẫu hợp đồng nhập

| Trường nguồn | Kiểu/định dạng nguồn | Kiểu Cassandra đích | Quy tắc bắt buộc |
| --- | --- | --- | --- |
| `event_id` | UUID canonical | `uuid` | Đúng 36 ký tự dạng 8-4-4-4-12, không tự sinh lại khi retry |
| `display_name` | UTF-8 | `text` | Decode strict, NFC nếu hợp đồng cho phép |
| `sku_code` | ASCII | `ascii` | Chỉ ký tự U+0000..U+007F theo chính sách mã |
| `quantity` | Số nguyên dạng chuỗi | `int` | Kiểm khoảng 32-bit |
| `total_minor` | Số nguyên đơn vị nhỏ nhất | `bigint` | Kiểm khoảng 64-bit, không qua `double` |
| `amount` | Số thập phân dạng chuỗi | `decimal` | `BigDecimal` và giới hạn scale theo nghiệp vụ |
| `sequence_no` | Số nguyên lớn | `varint` | `BigInteger`, kiểm kích thước hợp lý |
| `occurred_at` | ISO-8601 có offset | `timestamp` | Chuyển về instant, kiểm độ chính xác millisecond |
| `business_date` | `YYYY-MM-DD` | `date` | Lịch địa phương, không tự đổi sang UTC |
| `local_clock` | `HH:mm:ss[.fraction]` | `time` | Giờ trong ngày, không tự gắn timezone |
| `source_zone` | Tên IANA như `Asia/Ho_Chi_Minh` | `text` | Giữ zone ID riêng để tái dựng ngữ nghĩa |

Hợp đồng cũng cần nêu: cột nào nullable, hành vi khi chuỗi rỗng, đơn vị tiền, precision/scale, timestamp nguồn do ai tạo, timezone mặc định **nếu được chứng minh**, quyền sở hữu primary key và chiến lược xung đột khi import lại.

## 2. Encoding: `text`, `varchar`, `ascii` và Unicode

### 2.1. Cassandra lưu text như thế nào?

Trong CQL, `text` và `varchar` là các tên cho dữ liệu chuỗi **UTF-8**; `ascii` dành cho dữ liệu giới hạn ở ASCII. Cả ba đều là kiểu chuỗi, nhưng **không thể hoán đổi** khi nguồn có dấu tiếng Việt, emoji hoặc ký tự ngoài ASCII.

| Giá trị | CQL `text`/`varchar` | CQL `ascii` |
| --- | --- | --- |
| `HELLO-123` | Hợp lệ | Hợp lệ |
| `Cà phê sữa` | Hợp lệ khi encoding đúng | Không phù hợp, có ký tự ngoài ASCII |
| `Đơn hàng số 1` | Hợp lệ | Không phù hợp |
| `📦` | Hợp lệ với UTF-8 đúng | Không phù hợp |

Không chọn `ascii` chỉ vì dữ liệu “thường là chữ tiếng Anh”. Mã sản phẩm có thể được quy định ASCII, nhưng tên khách hàng, địa chỉ, ghi chú và nội dung tự do thường cần `text`.

### 2.2. Các lỗi thường gặp trước khi Cassandra nhận dữ liệu

- **Sai charset nguồn:** một tệp được ghi bằng Windows code page được decode như UTF-8. Nếu decoder thay byte lỗi bằng ký tự thay thế, Cassandra vẫn có thể lưu chuỗi đã hỏng.
- **UTF-8 BOM:** ba byte `EF BB BF` ở đầu file có thể bị xem là phần của tên cột đầu tiên nếu parser không xử lý.
- **CSV quoting:** chuỗi `"Cà phê, rang xay"` chứa dấu phẩy bên trong trường, không được cắt bằng `split(",")`.
- **Newline trong trường:** CSV cho phép xuống dòng nằm trong cặp quote; đọc từng dòng đơn giản có thể chia một bản ghi thành hai.
- **Unicode normalization:** hai chuỗi hiển thị giống nhau có thể dùng chuỗi code point khác nhau (dạng dựng sẵn NFC và dạng tổ hợp NFD), cho kết quả so byte/khóa khác nhau.
- **Trim/case-fold không có chính sách:** tự động bỏ khoảng trắng hoặc lower-case mã định danh có thể làm hai khóa nguồn khác nhau bị nhập thành một khóa.

Ví dụ một bản ghi CSV hợp lệ có dấu phẩy trong tên:

~~~csv
event_id,display_name,sku_code,amount,occurred_at
11111111-1111-4111-8111-111111111111,"Cà phê, rang xay",SKU-001,123.4500,2026-11-21T16:30:00.123+07:00
~~~

**Không import CSV bằng cách `line.split(",")`**. Sử dụng parser CSV hỗ trợ quote/escape/newline, xác định charset bằng hợp đồng nguồn và **decode ở chế độ báo lỗi** nếu byte không hợp lệ.

### 2.3. Chuẩn Unicode NFC có nên dùng không?

NFC giúp chuẩn hóa một số biểu diễn Unicode tương đương, hỗ trợ so sánh khóa và tìm kiếm văn bản khi hệ thống có nhiều nguồn. Nhưng đây phải là **quyết định ở cấp hợp đồng**:

- Với `display_name`, chuẩn hóa NFC thường hợp lý nếu mục tiêu là biểu diễn văn bản nhất quán.
- Với **external ID, chữ ký số, token, byte payload** hoặc khóa do hệ thống khác cấp, thay đổi mã hóa/normalization có thể làm hỏng định danh hoặc checksum.
- Giữ **hash của byte gốc** riêng và ghi phiên bản thuật toán normalize để có thể chứng minh dữ liệu đầu vào.

Java:

~~~java
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

var decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

// rawBytes là byte nhận trực tiếp từ một bản ghi/file nguồn hợp lệ.
String original = decoder.decode(
    java.nio.ByteBuffer.wrap(rawBytes)).toString();
String normalized = Normalizer.normalize(
    original, Normalizer.Form.NFC);
~~~

Code ví dụ chỉ minh họa bước **decode strict + normalize**. Với file CSV lớn, decoder/parser cần xử lý theo luồng và quote đúng; không decode một file nhiều GiB thành một chuỗi trong heap. `CharacterCodingException` phải chuyển thành lỗi import có vị trí/record ID, không nuốt lỗi rồi tiếp tục ghi chuỗi rác.

## 3. Kiểu số: chính xác quan trọng hơn “parse được”

Cassandra có các kiểu số nguyên và số thực với khả năng biểu diễn khác nhau. Khi thiết kế migration, chọn kiểu theo **miền giá trị thực**, không chỉ theo vài mẫu đầu tiên.

### 3.1. Số nguyên

| CQL type | Phạm vi/ý nghĩa | Kiểu Java Driver 4.x thường dùng |
| --- | --- | --- |
| `tinyint` | Số nguyên có dấu 8-bit | `byte`/`Byte` |
| `smallint` | Số nguyên có dấu 16-bit | `short`/`Short` |
| `int` | Số nguyên có dấu 32-bit | `int`/`Integer` |
| `bigint` | Số nguyên có dấu 64-bit | `long`/`Long` |
| `varint` | Số nguyên độ dài biến đổi, giới hạn thực tế bởi tài nguyên và hệ thống | `java.math.BigInteger` |
| `counter` | Bộ đếm cộng/trừ theo cơ chế riêng | Không import như một cột `bigint` thông thường |

Ví dụ:

~~~text
int:
    min = -2147483648
    max =  2147483647

bigint:
    min = -9223372036854775808
    max =  9223372036854775807

Giá trị: 9007199254740993
    vẫn vừa bigint,
    nhưng lớn hơn giới hạn nguyên an toàn 2^53 - 1 của
    JavaScript Number; nếu đã qua Number, có thể bị làm tròn.
~~~

Một lỗi thường gặp là xuất số nguyên rất lớn từ Excel/JavaScript sang JSON dưới dạng `number`, sau đó import `bigint`. Tới lúc Cassandra nhận được chuỗi `9007199254740992` thay vì `9007199254740993`, driver không thể tự khôi phục chữ số đã mất. **Cần giữ số lớn dạng string hoặc kiểu số nguyên chính xác từ nguồn đến đích.**

Không dùng `counter` cho mã ID tuần tự hay tổng số tiền được import: counter có quy tắc update đặc biệt, không là phép gán tuyệt đối thông thường và retry thiếu idempotency có rủi ro nhân đôi. Dữ liệu tổng hợp nên được lưu như `bigint`/`varint` hoặc tái tính theo quy trình có kiểm soát, tùy nghiệp vụ.

### 3.2. Số thập phân và số thực nhị phân

| CQL type | Tính chất | Dùng khi |
| --- | --- | --- |
| `decimal` | Thập phân chính xác theo unscaled integer + scale | Tiền tệ, tỷ lệ cần biểu diễn thập phân chính xác |
| `float` | Floating point nhị phân 32-bit | Đo đạc/telemetry chấp nhận sai số |
| `double` | Floating point nhị phân 64-bit | Đo đạc, tính toán gần đúng có giới hạn sai số |

Ví dụ số thập phân `0.1` không có biểu diễn nhị phân hữu hạn chính xác trong `float`/`double`. Đừng tính `amount` bằng `double` rồi chuyển sang `decimal` với kỳ vọng mọi chữ số trở lại đúng như nguồn.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

BigDecimal exactAmount = new BigDecimal("123.4500");
BigInteger exactSequence =
    new BigInteger("123456789012345678901234567890");
long exactMinor = Long.parseLong("9007199254740993");

// Tránh nếu nguồn yêu cầu giá trị thập phân chính xác:
// new BigDecimal(0.1)  // mang sai số của double
~~~

**Scale là một phần của hợp đồng.** `123.45` và `123.4500` có cùng giá trị số nhưng có thể khác scale ở `BigDecimal`. `BigDecimal.equals()` kiểm cả scale, còn `compareTo()` so giá trị số. Khi đối soát, quyết định rõ cần so **giá trị số** hay **định dạng/scale gốc**.

Ví dụ quy tắc nghiệp vụ cho `amount`: tối đa bốn chữ số sau dấu chấm, precision không quá 18 chữ số và không cho số âm. Đây là **chính sách của ứng dụng**, không phải giới hạn chung của kiểu `decimal` trong Cassandra.

### 3.3. Phân biệt dấu thập phân và dấu phân nhóm

Giá trị `1,234` có thể là **một nghìn hai trăm ba mươi bốn** hoặc **một phẩy hai ba bốn**, tùy locale. Khi định nghĩa file exchange, hãy chọn format machine-readable thống nhất, ví dụ:

~~~text
quantity:    "1234"
total_minor: "123400"
amount:      "1234.00"
ratio:       "0.125"
~~~

Không dùng `NumberFormat` theo locale hệ điều hành một cách ngầm định. Không âm thầm thay tất cả dấu phẩy thành dấu chấm vì có thể làm `1,234.56` thành chuỗi sai. Giá trị không khớp format đã công bố phải được reject hoặc đưa vào quarantine để sửa từ nguồn.

## 4. UUID: định danh và thứ tự thời gian là hai việc khác nhau

### 4.1. Kiểu `uuid`

Cassandra `uuid` lưu định danh UUID. Một biểu diễn text canonical phổ biến:

~~~text
11111111-1111-4111-8111-111111111111
xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx
~~~

Trong định dạng minh họa, `M` thể hiện phiên bản UUID, `N` chứa các bit variant. `uuid` không có nghĩa “phải là UUID version 4”; ứng dụng có thể sử dụng những phiên bản UUID phù hợp với hợp đồng dữ liệu.

Khi nhập:

1. Kiểm tra chuỗi canonical theo dạng 8-4-4-4-12 nếu nguồn cam kết dạng đó.
2. Parse bằng `UUID.fromString(...)` và kiểm lại chính sách version/variant nếu nghiệp vụ yêu cầu.
3. Giữ ID **ổn định khi retry**: không tự `UUID.randomUUID()` lần nữa cho cùng một source record.
4. Không coi toàn số 0 là `null` nếu nguồn thực sự gửi UUID nil; quy tắc missing phải tách riêng.
5. Không so chữ hoa/chữ thường ở dạng text một cách tùy tiện; sau parse, dùng kiểu UUID và canonical serialization.

**Vì sao phải giữ ID ổn định?** Nếu ETL retry một event nhưng tự sinh UUID mới, Cassandra nhìn thấy **hai primary key khác nhau**. Tăng `LOCAL_QUORUM` cũng không thể tự gộp chúng.

### 4.2. Kiểu `timeuuid`

`timeuuid` của Cassandra dành cho **UUID phiên bản 1 có thành phần thời gian**. Nó có thể dùng trong thiết kế một số bảng sắp xếp theo thời gian, nhưng:

- **UUIDv4** không thể thay thế trực tiếp `timeuuid`.
- UUID phiên bản khác, như UUIDv7, **không tự là `timeuuid`** theo cách hiểu của Cassandra.
- `timeuuid` không mang toàn bộ timezone nghiệp vụ. Thời gian từ UUID phải được diễn giải theo định dạng/phiên bản phù hợp.
- Nhiều sự kiện có cùng hoặc gần thời điểm vẫn cần quy tắc định danh/thứ tự rõ ràng; không coi mỗi `timeuuid` là bảo đảm thứ tự toàn cục giữa hệ thống phân tán.

Ví dụ bảng riêng nếu nguồn thực sự có timeuuid hợp lệ:

~~~sql
CREATE TABLE IF NOT EXISTS migration_lab.events_by_time (
    run_id text,
    event_time_id timeuuid,
    marker text,
    PRIMARY KEY ((run_id), event_time_id)
) WITH CLUSTERING ORDER BY (event_time_id DESC);
~~~

Cassandra có các hàm CQL liên quan `timeuuid` như `now()`, `toTimestamp(...)` và các hàm tạo biên theo thời gian trên các phiên bản hỗ trợ. **Không tạo UUIDv1 tại thời điểm import rồi dùng làm bằng chứng “đây là thời điểm event xảy ra”**: đó có thể chỉ là thời điểm ETL xử lý.

## 5. Timestamp, date và time: ba ngữ nghĩa khác nhau

### 5.1. `timestamp` là một instant, không lưu timezone gốc

Trong Cassandra, `timestamp` được biểu diễn như số millisecond kể từ Unix epoch UTC. Các chuỗi thời gian có **offset khác nhau nhưng chỉ đến cùng một instant** phải được hiểu là cùng thời điểm:

~~~text
2026-11-21T16:30:00.123+07:00
2026-11-21T09:30:00.123Z

Hai biểu diễn trên cùng một instant.
Khi lưu vào CQL timestamp, thông tin "+07:00"
không được giữ như timezone gốc trong chính cột timestamp.
~~~

Trong `cqlsh`, múi giờ hiển thị và format có thể phụ thuộc client/session. Việc đọc ra một chuỗi `09:30Z` thay vì `16:30+07:00` **không phải mất bảy giờ**, nếu hai giá trị chỉ cùng instant.

**Độ chính xác:** CQL `timestamp` có độ phân giải **millisecond**. Nếu nguồn chứa microsecond hoặc nanosecond, cần quyết định từ trước sẽ **reject**, **làm tròn** hay **cắt bớt** theo chính sách. Không để driver/serializer giảm độ chính xác âm thầm và vẫn báo dữ liệu khớp 100%.

### 5.2. `date` không phải midnight UTC

CQL `date` là một **ngày trong lịch**, không tự mang múi giờ hay thời điểm trong ngày. Ví dụ `2026-11-21` có thể là ngày kinh doanh của cửa hàng tại Việt Nam. Nó **không phải** timestamp `2026-11-21T00:00:00Z`.

Nếu ngày kinh doanh được tính ở `Asia/Ho_Chi_Minh`:

~~~text
instant UTC:      2026-11-20T18:30:00Z
theo +07:00:      2026-11-21T01:30:00+07:00
business_date:    2026-11-21
~~~

Khi lấy `instant.atZone(zone).toLocalDate()`, ngày có thể khác ngày UTC. Nếu `business_date` là **giá trị nghiệp vụ do nguồn công bố** (ví dụ ngày chốt sổ có cutoff 05:00), không tự tính lại bằng chuyển timezone thuần túy; phải giữ đúng quy tắc cutoff đó.

### 5.3. `time` không mang date hoặc timezone

CQL `time` là **giờ trong ngày** với độ chính xác tới nanosecond; trong Java Driver thường dùng `java.time.LocalTime`. Một giá trị `16:30:00.123000000` **không xác định một instant** nếu chưa có ngày và timezone/offset.

Do đó:

| Cột | Lưu được | Không lưu được |
| --- | --- | --- |
| `timestamp` | Một instant ở độ phân giải millisecond | IANA zone ID gốc, local calendar context |
| `date` | Ngày lịch | Thời điểm UTC, offset, giờ |
| `time` | Giờ trong ngày | Ngày, offset, timezone |
| `source_zone text` | Ví dụ `Asia/Ho_Chi_Minh` | Bản thân giá trị này chưa có instant |

Nếu nghiệp vụ cần hiển thị “lúc 16:30 giờ Hà Nội” và còn phải xử lý lịch sử các vùng có DST, nên lưu **instant** cộng với **zone ID** và các thuộc tính nghiệp vụ cần thiết, chứ không chỉ cột timestamp.

## 6. Offset không giống IANA timezone

**Offset** là độ lệch UTC tại một thời điểm, ví dụ `+07:00`. **Timezone** dạng IANA, như `Asia/Ho_Chi_Minh`, bao gồm quy tắc lịch sử và có thể có thay đổi offset theo mùa/năm.

| Đầu vào | Có thể xác định instant? | Điều cần lưu ý |
| --- | --- | --- |
| `2026-11-21T16:30:00+07:00` | Có | Offset rõ ràng, parse thành `OffsetDateTime` rồi `Instant` |
| `2026-11-21T09:30:00Z` | Có | `Z` nghĩa là UTC |
| `2026-11-21 16:30:00` | **Chưa chắc** | Thiếu offset/zone; phải dùng quy tắc nguồn đã xác minh |
| `2026-11-21 16:30:00 + Asia/Ho_Chi_Minh` | Có, với quy tắc zone hợp lệ | Phải parse đúng local date/time và ZoneId |
| `2026-11-01 01:30:00 + zone có DST` | Có thể **mơ hồ** | Một số giờ lặp lại; cần offset hoặc quy tắc disambiguation |

Khi địa phương chuyển sang giờ mùa hè, có thể có **giờ không tồn tại** hoặc **giờ xuất hiện hai lần**. `LocalDateTime.atZone(...)` có thể áp dụng chiến lược mặc định của thư viện; không nên dùng nó âm thầm cho migration tài chính hoặc audit. Nếu nguồn ghi cả offset và zone, cần xác minh **offset hợp lệ cho zone tại instant đó**.

### Mẫu kiểm tra Java

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

OffsetDateTime input =
    OffsetDateTime.parse("2026-11-21T16:30:00.123+07:00");
Instant instant = input.toInstant();
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime atBusinessZone = instant.atZone(businessZone);

if (!input.getOffset().equals(atBusinessZone.getOffset())) {
    throw new IllegalArgumentException(
        "Offset không phù hợp với timezone đã khai báo");
}
~~~

Với nguồn chỉ có local time mà không có zone/offset, pipeline nên yêu cầu nguồn bổ sung metadata hoặc có **quy tắc chuyển đổi được duyệt**. Tùy tiện dùng timezone của máy chạy ETL tạo kết quả khác nhau giữa container, laptop và server.

## 7. Null, chuỗi rỗng, trường thiếu và timestamp ghi nội bộ

### 7.1. Cùng một “ô trống” có thể có nhiều nghĩa

| Trường hợp nguồn | Ý nghĩa có thể | Cách xử lý |
| --- | --- | --- |
| Field không xuất hiện trong JSON | Không được cung cấp | Tách khỏi `null`, xác định update hay insert |
| `null` trong JSON | Giá trị không có | Chỉ ghi null nếu hợp đồng cho phép |
| `""` | Chuỗi rỗng thực sự | Không tự đổi thành null |
| `"NULL"` trong CSV | Có thể là văn bản `NULL` hoặc sentinel | Cần quy tắc escaping/CSV null marker |
| Một cột số chứa `""` | Thiếu/sai định dạng | Reject hoặc chính sách missing rõ ràng |
| UUID nil `00000000-0000-0000-0000-000000000000` | Một UUID có thể parse | Không tự coi là null nếu chưa được quy định |

Trong Cassandra, **các thành phần primary key không được null**. Với non-key column, ghi `null` có thể tạo **tombstone**; còn driver hỗ trợ **UNSET** với ngữ nghĩa không cập nhật cột tương ứng trong các trường hợp được phép. Không xem `NULL` và `UNSET` là một. Tránh biến hàng nghìn giá trị thiếu thành hàng nghìn tombstone ngoài ý muốn.

### 7.2. `writetime` khác `occurred_at`

Cột nghiệp vụ `occurred_at timestamp` biểu diễn **lúc sự kiện xảy ra**. Cassandra còn có **write timestamp nội bộ** (độ phân giải microsecond) dùng để hòa giải cell:

~~~sql
SELECT event_id, occurred_at, WRITETIME(amount)
FROM migration_lab.import_events_by_run
WHERE run_id = 'migration-demo-01'
  AND event_id = 11111111-1111-4111-8111-111111111111;
~~~

`WRITETIME(amount)` trả write timestamp của cell `amount`, **không tự bằng** `occurred_at` và không bảo đảm đó là thời điểm client nhận ACK. Nếu import một event cũ trong ngày hôm nay mà dùng server-generated write timestamp, hai thời điểm đương nhiên khác.

Khi cần replay/dual-write/idempotency, phải thiết kế **chính sách timestamp ghi ổn định**, quyền sở hữu key và quy tắc xung đột. `USING TIMESTAMP` trong CQL dùng timestamp microsecond; không truyền trực tiếp số millisecond vào đó rồi hiểu nhầm đơn vị.

## 8. Thiết kế schema lab cho một lượt import

Giả sử nguồn có ID UUID, text tiếng Việt, mã ASCII, số nguyên 32/64-bit, số nguyên lớn, thập phân, timestamp có offset và ngày/giờ nghiệp vụ. Bảng lab chọn partition key theo **run ID** để đối soát số event nhỏ trong một lượt thử:

~~~sql
CREATE KEYSPACE IF NOT EXISTS migration_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS migration_lab.import_events_by_run (
    run_id text,
    event_id uuid,
    source_id text,
    customer_id uuid,
    display_name text,
    sku_code ascii,
    quantity int,
    total_minor bigint,
    amount decimal,
    sequence_no varint,
    metric double,
    occurred_at timestamp,
    business_date date,
    local_clock time,
    source_zone text,
    raw_sha256 text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

**Lưu ý:**

- `(run_id)` là partition key, `event_id` là clustering key. Mỗi bài thực hành dùng một `run_id` mới.
- Schema này dành cho **ít record lab**, không phải đề xuất lưu hàng triệu sự kiện production trong một partition theo run ID. Với workload thật, phải bucket theo tenant/thời gian/shard và truy vấn phổ biến.
- `source_id` giữ mã định danh từ hệ thống nguồn; nếu mapping nhiều nguồn, thêm `source_system`/namespace vào hợp đồng để tránh trùng ID.
- `raw_sha256` có thể lưu hash **byte nguồn của record** hoặc bản canonical được định nghĩa; phải ghi rõ lựa chọn. Hash không thay mã hóa/quyền truy cập và có thể lộ thông tin nếu input có miền nhỏ.
- `IF NOT EXISTS` không thay đổi bảng/keyspace đã tồn tại. Trước khi tính `LOCAL_QUORUM`, xác minh RF và tên datacenter thật.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'migration_lab';

SELECT data_center, release_version, host_id
FROM system.local;
~~~

`system.local` chỉ nói về **node đang trả lời CQL**; muốn kiểm tra topology nhiều node, dùng thêm `nodetool status` từ nơi quản trị phù hợp. Nếu lab chỉ có một node, cần chỉnh RF/CL phù hợp thay vì giả định có ba replica thật.

## 9. Thực hành CQL: nhập một bản ghi nhiều kiểu

### 9.1. Nguồn kỳ vọng

~~~text
run_id:          migration-demo-01
event_id:        11111111-1111-4111-8111-111111111111
source_id:       invoice-0001
customer_id:     22222222-2222-4222-8222-222222222222
display_name:    Cà phê rang
sku_code:        SKU-001
quantity:        2
total_minor:     9007199254740993
amount:          123.4500
sequence_no:     123456789012345678901234567890
metric:          0.125
occurred_at:     2026-11-21T16:30:00.123+07:00
business_date:   2026-11-21
local_clock:     16:30:00.123000000
source_zone:     Asia/Ho_Chi_Minh
~~~

Ở `cqlsh`, chọn consistency phù hợp với cluster lab. Trong một DC có RF=3 và đủ node khỏe, ví dụ:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO migration_lab.import_events_by_run (
    run_id, event_id, source_id, customer_id, display_name,
    sku_code, quantity, total_minor, amount, sequence_no,
    metric, occurred_at, business_date, local_clock, source_zone
) VALUES (
    'migration-demo-01',
    11111111-1111-4111-8111-111111111111,
    'invoice-0001',
    22222222-2222-4222-8222-222222222222,
    'Cà phê rang',
    'SKU-001',
    2,
    9007199254740993,
    123.4500,
    123456789012345678901234567890,
    0.125,
    '2026-11-21T16:30:00.123+0700',
    '2026-11-21',
    '16:30:00.123000000',
    'Asia/Ho_Chi_Minh'
);
~~~

`CONSISTENCY` là lệnh **cqlsh**, không phải cú pháp CQL cho Java Driver. Đoạn `INSERT` không ghi `raw_sha256` vì hash cần được tính từ byte nguồn thực tế, không nên điền một checksum giả.

### 9.2. Đọc để đối soát

~~~sql
SELECT event_id, source_id, customer_id, display_name,
       sku_code, quantity, total_minor, amount, sequence_no,
       metric, occurred_at, business_date, local_clock, source_zone
FROM migration_lab.import_events_by_run
WHERE run_id = 'migration-demo-01'
  AND event_id = 11111111-1111-4111-8111-111111111111;
~~~

Đừng đối soát timestamp bằng **chuỗi hiển thị** nếu client dùng múi giờ khác: so giá trị instant hoặc epoch milliseconds. Với `amount`, so theo hợp đồng: `compareTo()` nếu cần giá trị số hoặc so scale/canonical string nếu cần giữ biểu diễn. Với text, so kết quả Unicode normalization được quy định, **không tự lower-case tên người**.

Kiểm tra số lượng chỉ trong partition nhỏ của lab có thể hữu ích, nhưng **không dùng `COUNT(*)` toàn bảng production** để chứng minh import đầy đủ. Hai tập record khác ID vẫn có thể có cùng số lượng.

### 9.3. Ca lỗi có chủ đích, nhưng không ghi rác

| Dữ liệu nguồn sai | Bước cần phát hiện | Cách xử lý |
| --- | --- | --- |
| `display_name` chứa byte UTF-8 bị cắt giữa ký tự | Decoder | `ENCODING_ERROR`, quarantine |
| `sku_code = "ĐƠN-01"` nhưng cột `ascii` | Validation ASCII | `TYPE_ERROR`, không ép mất dấu |
| `quantity = 2147483648` | Parse/range kiểm `int` | `OUT_OF_RANGE` |
| `total_minor = 9223372036854775808` | Parse/range `bigint` | `OUT_OF_RANGE` hoặc đổi schema có kế hoạch |
| `amount = "1,234.56"` không có quy tắc locale | Parse decimal | `FORMAT_AMBIGUOUS` |
| `event_id = "not-an-uuid"` | UUID parser | `INVALID_UUID` |
| `occurred_at = "2026-11-21 16:30:00"` | Timestamp parser | `MISSING_OFFSET_OR_ZONE` |
| `2026-11-21T16:30:00.123456+07:00` | Precision policy | Reject hoặc round/truncate **theo hợp đồng** |
| `source_zone` không hợp lệ | ZoneId/zone rules | `INVALID_TIMEZONE` |

**Không nhầm lỗi đầu vào với lỗi replication:** một record sai kiểu phải bị dừng trước khi gửi đến Cassandra. Một record hợp lệ nhưng `WriteTimeout` có trạng thái **UNKNOWN_WRITE**, cần đối soát theo khóa ổn định trước khi retry.

## 10. Java Driver 4.x: parse và bind theo kiểu mạnh

Ví dụ sau áp dụng cho **Cassandra Java Driver 4.x** và Java 17. Mục tiêu là tránh truyền tất cả dữ liệu thành chuỗi để CQL tự đoán, không dùng `double` cho tiền và không dựa vào timezone mặc định của JVM.

### 10.1. Hàm kiểm tra dữ liệu nguồn

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.UUID;
import java.util.regex.Pattern;

public final class ImportTypes {
    private static final Pattern UUID_CANONICAL = Pattern.compile(
        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
        "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    private static final Pattern AMOUNT_FORMAT = Pattern.compile(
        "-?[0-9]+(\\.[0-9]{1,4})?");

    public record Raw(
        String eventId, String sourceId, String customerId,
        String displayName, String skuCode, String quantity,
        String totalMinor, String amount, String sequenceNo,
        String metric, String occurredAt, String businessDate,
        String zoneId) {}

    public record Parsed(
        UUID eventId, String sourceId, UUID customerId,
        String displayName, String skuCode, int quantity,
        long totalMinor, BigDecimal amount, BigInteger sequenceNo,
        double metric, Instant occurredAt, LocalDate businessDate,
        LocalTime localClock, String sourceZone) {}

    private static UUID parseUuid(String text) {
        if (text == null || !UUID_CANONICAL.matcher(text).matches()) {
            throw new IllegalArgumentException("UUID không canonical");
        }
        return UUID.fromString(text);
    }

    public static Parsed parse(Raw raw) {
        UUID eventId = parseUuid(raw.eventId());
        UUID customerId = parseUuid(raw.customerId());

        // Không đổi external key, nhưng cho phép NFC ở display field.
        String display = Normalizer.normalize(
            raw.displayName(), Normalizer.Form.NFC);
        if (!StandardCharsets.US_ASCII.newEncoder()
                .canEncode(raw.skuCode())) {
            throw new IllegalArgumentException("skuCode không là ASCII");
        }

        int quantity = Integer.parseInt(raw.quantity());
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
        long minor = Long.parseLong(raw.totalMinor());
        BigInteger sequence = new BigInteger(raw.sequenceNo());

        if (raw.amount() == null ||
                !AMOUNT_FORMAT.matcher(raw.amount()).matches()) {
            throw new IllegalArgumentException("amount sai format");
        }
        BigDecimal amount = new BigDecimal(raw.amount());
        if (amount.precision() > 18 || amount.signum() < 0) {
            throw new IllegalArgumentException("amount ngoài hợp đồng");
        }

        double metric = Double.parseDouble(raw.metric());
        if (!Double.isFinite(metric)) {
            throw new IllegalArgumentException("metric không hữu hạn");
        }

        OffsetDateTime fromSource =
            OffsetDateTime.parse(raw.occurredAt());
        Instant instant = fromSource.toInstant();
        if (instant.getNano() % 1_000_000 != 0) {
            throw new IllegalArgumentException(
                "timestamp có độ chính xác dưới millisecond");
        }

        ZoneId zone = ZoneId.of(raw.zoneId());
        ZonedDateTime local = instant.atZone(zone);
        if (!local.getOffset().equals(fromSource.getOffset())) {
            throw new IllegalArgumentException(
                "offset không phù hợp với timezone nguồn");
        }

        LocalDate businessDate = LocalDate.parse(raw.businessDate());
        // Ví dụ hợp đồng: business_date bằng ngày dân sự của zone.
        // Nếu có cutoff nghiệp vụ khác, phải thay điều kiện này.
        if (!businessDate.equals(local.toLocalDate())) {
            throw new IllegalArgumentException(
                "businessDate khác ngày ở source_zone");
        }

        return new Parsed(
            eventId, raw.sourceId(), customerId,
            display, raw.skuCode(), quantity,
            minor, amount, sequence, metric, instant,
            businessDate, local.toLocalTime(), zone.getId());
    }
}
~~~

**Giới hạn rõ ràng của ví dụ:**

- Dữ liệu đã được **decode từ bytes bằng UTF-8 strict** và parse CSV/JSON đúng chuẩn trước khi vào `Raw`. Đoạn mã này không tự bảo đảm file nguồn có encoding chính xác.
- `Integer.parseInt`/`Long.parseLong` ném lỗi nếu vượt khoảng; không tự cắt sang 32/64-bit.
- `AMOUNT_FORMAT` cấm dấu nhóm, notation `e` và hơn bốn chữ số thập phân theo **hợp đồng ví dụ**, không phải giới hạn của Cassandra `decimal`.
- `source_zone` và offset được đối chiếu để ngăn dùng một zone ID không phù hợp. Một `business_date` theo lịch chốt sổ khác với ngày dân sự sẽ cần validation riêng.
- `LocalTime` giữ giờ địa phương theo zone, còn `Instant` giữ thời điểm chuẩn; hai giá trị không nên dùng thay nhau.
- Những cột nullable, policy độ dài chuỗi và giới hạn `BigInteger` nên bổ sung trước production để tránh payload quá lớn.

### 10.2. Bind CQL theo kiểu Java chính xác

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TypedImporter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public TypedImporter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO migration_lab.import_events_by_run (" +
            "run_id, event_id, source_id, customer_id, display_name, " +
            "sku_code, quantity, total_minor, amount, sequence_no, " +
            "metric, occurred_at, business_date, local_clock, " +
            "source_zone, raw_sha256) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
    }

    public void write(String runId, ImportTypes.Parsed row,
                      String originalSha256) {
        BoundStatement statement = insert.bind(
                runId, row.eventId(), row.sourceId(), row.customerId(),
                row.displayName(), row.skuCode(), row.quantity(),
                row.totalMinor(), row.amount(), row.sequenceNo(),
                row.metric(), row.occurredAt(), row.businessDate(),
                row.localClock(), row.sourceZone(), originalSha256)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            // Chưa công nhận idempotent nếu chưa có chính sách
            // timestamp cố định và writer ownership rõ ràng.
            .setIdempotence(false);
        session.execute(statement);
    }
}
~~~

`CqlSession` và `PreparedStatement` phải được tái sử dụng. `bind(...)` đặt giá trị vào cột **đúng kiểu**: `UUID`, `int`, `long`, `BigDecimal`, `BigInteger`, `Instant`, `LocalDate`, `LocalTime`. Không cần nối literal số/timestamp vào query string và không tự thêm quote.

Với write timeout, phương thức `write` có thể ném exception dù một số replica đã lưu mutation. Pipeline nên ghi:

~~~text
PARSE_FAILED    -> chưa gửi đến Cassandra; quarantine có mã lỗi
VALIDATED       -> đã qua parse/range/timezone nhưng chưa nhận ACK
ACKNOWLEDGED    -> execute thành công ở CL đã cấu hình
UNKNOWN_WRITE   -> timeout/lỗi sau khi gửi; chưa rõ bao nhiêu replica ghi
READ_MISSING    -> đọc thành công nhưng không thấy row theo khóa/CL
READ_MATCH      -> đọc thành công, dữ liệu khớp manifest
READ_MISMATCH   -> đọc thành công nhưng ít nhất một trường không khớp
READ_ERROR      -> đọc không hoàn tất; không tính là dữ liệu thiếu
~~~

**Không retry bừa một mutation chưa có idempotency contract.** Muốn reimport an toàn, cần xác định primary key bất biến, cùng normalized values, chính sách timestamp/TTL ổn định, không có writer tranh chấp và cách tra kết quả UNKNOWN. Đặt `setIdempotence(true)` chỉ khi đã chứng minh các điều kiện đó; nó không biến lệnh ghi thành giao dịch exactly-once.

## 11. Write timestamp và replay có kiểm soát

Một lỗi migration nguy hiểm là retry cùng primary key với giá trị có vẻ giống nhau nhưng **write timestamp khác**; trong lúc đó một writer khác đã cập nhật dữ liệu mới. Cassandra reconciliation dùng timestamp/tombstone, nên việc reimport vô điều kiện có thể ghi đè dữ liệu hợp lệ.

Với luồng import một lần có ownership rõ ràng, có thể cân nhắc **mutation timestamp cố định** được lưu trong manifest và dùng cho mọi retry của cùng mutation:

~~~sql
-- Chỉ minh họa cú pháp cho insert trong lab:
INSERT INTO migration_lab.import_events_by_run
    (run_id, event_id, source_id)
VALUES (
    'migration-demo-02',
    33333333-3333-4333-8333-333333333333,
    'invoice-0002'
) USING TIMESTAMP 1795250000000000;
~~~

Số sau `USING TIMESTAMP` là **microsecond kể từ epoch** cho write timestamp nội bộ, **không** phải literal CQL `timestamp` ở độ phân giải millisecond. Con số trên chỉ mang tính minh họa, không được dùng như nguồn thời gian thật. Nếu nhập thiếu các cột còn lại, ví dụ này chỉ là một mutation có một giá trị dữ liệu; không phải bản import hoàn chỉnh.

**Cẩn trọng:** chọn timestamp ghi tùy tiện hoặc dùng thời điểm event đã xảy ra nhiều năm trước có thể làm mutation mới **thua** dữ liệu/tombstone đã có do timestamp cao hơn. Cần chính sách xung đột rõ ràng và cân nhắc TTL/tombstone, bulk load, migration hai chiều. Đừng tự dùng `USING TIMESTAMP` để “bắt Cassandra lưu timezone của event”; hai khái niệm không liên quan.

Nếu thiết kế nguồn có operation ID bất biến và outbox/event log, dùng nó để:

1. Nhận diện cùng event qua nhiều lần chạy.
2. Lưu version mapping/schema và các giá trị sau normalize.
3. Đối soát kết quả trước retry khi client trả UNKNOWN.
4. Phát hiện hai bản nguồn khác giá trị nhưng cùng primary key.
5. Chặn writer không được phép cập nhật partition trong quá trình backfill.

## 12. Đối soát sau nhập: đúng kiểu, đúng giá trị, đúng dữ liệu

Một migration đáng tin phải đối chiếu **các khóa kỳ vọng từ nguồn độc lập**, không tạo expected set bằng chính câu SELECT từ Cassandra đích.

### 12.1. Manifest nên chứa gì?

| Trường manifest | Ý nghĩa |
| --- | --- |
| `import_run_id` và `source_system` | Xác định phạm vi/ràng buộc namespace |
| `source_record_id`, `event_id` | Khóa ổn định giúp idempotent readback |
| `source_bytes_sha256` | Băm byte gốc để xác minh file đầu vào |
| `normalized_payload_sha256` | Băm trên canonical representation được định nghĩa rõ |
| `encoding`, `normalization_version` | Biết đã decode và biến đổi thế nào |
| `numeric_contract_version` | Scale, unit, range, rounding policy |
| `timestamp_contract_version` | Timezone/offset, DST và precision policy |
| `write_outcome`, `ack_time`, `CL` | Phân biệt ACK với UNKNOWN hoặc reject |
| `target_key`, `read_result` | Đối soát theo khóa và CL ở Cassandra |
| `error_category` | Quyết định quarantine, retry hay điều tra |

### 12.2. So từng loại trường

- **Text:** so Unicode code point sau normalization đã được quy định; lưu thêm hash byte nguồn khi cần kiểm toán.
- **ASCII:** so đúng giá trị và quy tắc mã; không so kết quả đã bị transliteration tự động.
- **Integer:** so `BigInteger` hoặc kiểu nguyên chính xác; không đưa vào `double` để tạo report.
- **Decimal:** so `BigDecimal` theo numerical value/scale đúng hợp đồng.
- **UUID:** so bằng kiểu `UUID` sau parse canonical; kiểm version đối với `timeuuid`.
- **Timestamp:** so `Instant` hoặc epoch milliseconds; nếu nguồn có micro/nanos, ghi nhận policy precision.
- **Date/time/zone:** so riêng `LocalDate`, `LocalTime` và `ZoneId`; không suy zone từ CQL timestamp.
- **Null/missing:** so riêng `null`, chuỗi rỗng, field không được gửi và giá trị đã xóa.

### 12.3. Các kiểu báo cáo

~~~text
source_records_seen         = ...
decode_parse_valid          = ...
quarantined_input           = ...
target_writes_acked         = ...
target_writes_unknown       = ...
target_reads_match          = ...
target_reads_missing        = ...
target_reads_mismatch       = ...
target_reads_error          = ...
duplicate_source_ids        = ...
conflicting_same_target_pk  = ...
~~~

**Không cộng `READ_ERROR` vào `MISSING`.** Nếu `LOCAL_QUORUM` timeout, không biết event có tồn tại trên replica khác hay không. Phải ghi bối cảnh node/DC/RF/CL, repair/compaction, thời điểm và retry có giới hạn để phân loại lại.

## 13. Thiết kế pipeline vận hành an toàn

### Bước 1 — Khóa định nghĩa nguồn

Lấy mẫu **bao gồm giá trị biên**: tiếng Việt có dấu và emoji, byte không hợp lệ, CSV chứa quote/newline, UUID sai, số sát min/max, tiền nhiều chữ số, ngày DST, timestamp không offset, null và duplicate ID. Chốt phiên bản contract và mapping source → Cassandra.

### Bước 2 — Chọn schema theo truy vấn

Đừng dùng một partition `run_id` chứa hàng chục triệu record để thuận tiện import. Với ứng dụng thật, partition key phải hỗ trợ truy vấn chính và tránh hot partition; có thể cần tenant/customer + bucket thời gian hoặc shard có giới hạn. Dữ liệu được ghi nhiều bảng theo truy vấn có rủi ro lệch giữa bảng; cần idempotency/đối soát.

### Bước 3 — Pilot và chuẩn bị rollback

Chạy pilot nhỏ với giá trị biên và so kết quả CQL/Java. Đảm bảo có backup/restore test và kế hoạch rollback hoặc tiếp tục forward-fix. Không giả định `TRUNCATE` hoặc `DROP TABLE` là phương pháp rollback production an toàn.

### Bước 4 — Parse/validate trước khi mở tải

Đọc input theo encoding rõ, parser đúng định dạng và cho sai trường vào quarantine có thông tin:

~~~text
source_file_id
record_offset_or_line
source_record_id (không chứa PII nếu log không bảo vệ)
error_code
field_name
raw_bytes_hash
contract_version
~~~

Giữ byte nguồn ở vùng bảo mật phù hợp nếu cần điều tra, **không** in raw payload nhạy cảm ra stdout hoặc gửi vào công cụ phân tích công khai.

### Bước 5 — Ghi theo prepared statements, có giới hạn

Sử dụng CL phù hợp RF/local DC; `LOCAL_QUORUM` ở RF3 đòi hai replica local phản hồi. Đặt giới hạn số request đồng thời, rate limit, backpressure và metrics. **Không dùng một logged batch rất lớn trên nhiều partition để “import nhanh hơn”**: Cassandra batch không phải công cụ bulk throughput tự động, có thể tạo bottleneck batchlog.

Khi write timeout, lưu **UNKNOWN_WRITE**. Khi lỗi parse/validation, lưu **QUARANTINED** mà không gửi. Việc lỗi một bản ghi không cho phép âm thầm bỏ qua rồi công bố “100% dữ liệu đã chuyển”.

### Bước 6 — Kiểm tra ACK và readback có giới hạn

Đối chiếu theo primary key/bucket; không dùng full table scan `ALLOW FILTERING` hoặc `COUNT(*)` như bằng chứng duy nhất. Với sample lớn, lấy mẫu có phân tầng theo loại dữ liệu, có thêm đối soát toàn bộ ID ở nguồn độc lập khi khả thi.

### Bước 7 — Cutover và theo dõi

Chỉ chuyển ứng dụng khi schema agreement, RF/CL, kết quả đối soát và error budget đạt điều kiện. Đọc/ghi thử qua Java Driver local DC đúng; kiểm p95/p99, retry, timeout và replica health. Với dual-write, có cơ chế ownership/fencing và reconcile để tránh mutation cũ ghi đè dữ liệu mới.

## 14. Trường hợp lỗi thực tế và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hành động kiểm tra |
| --- | --- | --- |
| Tên `Cà phê` thành ký tự lạ | Decode sai charset, replacement characters | So byte nguồn, kiểm UTF-8 strict và Unicode |
| Hai ID nhìn giống nhau nhưng không tìm được bằng khóa | NFC/NFD hoặc trim khác nhau trong partition key text | So code point, chuẩn normalize trước tạo khóa |
| Mã ASCII có dấu bị từ chối | Cột `ascii` không hỗ trợ ký tự ngoài ASCII | Xác minh hợp đồng; đổi schema có migration nếu cần |
| Giá trị `9007199254740993` thành `9007199254740992` | Số đã qua IEEE-754 double/JavaScript Number | Sửa pipeline ở nguồn; giữ integer exact dưới dạng string |
| `0.1 + 0.2` không bằng `0.3` | Dùng float/double cho tiền | Chuyển `BigDecimal` từ string, đặt precision/scale |
| `123.4500` so `123.45` bị báo mismatch | `BigDecimal.equals` kiểm scale | Chọn compareTo hoặc canonical scale theo contract |
| CQL báo UUID không hợp lệ | Chuỗi sai/copy mất dấu `-`, version không phù hợp `timeuuid` | Validate canonical và type/version |
| Timestamp lệch 7 giờ khi in từ client khác | Cùng instant được hiển thị ở UTC vs +07 | So epoch milliseconds/Instant, lưu source zone riêng |
| Ngày `2026-11-21` thành `2026-11-20` | Tính ngày theo UTC thay vì local business zone | So offset và quy tắc cutoff nguồn |
| Một giờ DST bị tự dịch | Parse local time không chỉ rõ offset/ambiguity policy | Reject hoặc áp dụng disambiguation được duyệt |
| Timestamp mất phần microsecond | CQL `timestamp` chỉ millisecond | Kiểm precision, reject/truncate theo contract |
| Reimport tạo hàng trùng | Mỗi lần retry dùng UUID mới | Dùng event ID nguồn bất biến làm key |
| Reimport làm mất update mới | Write timestamp/tombstone và writer cạnh tranh | Ownership, replay timestamp policy, đối soát |
| `SELECT` timeout sau import | CL/replica/network hoặc tải import/repair | Ghi READ_ERROR, kiểm node/CL, không kết luận MISSING |
| Các replica khác giá trị | Mutation chưa hội tụ, tombstone/repair, timestamp | Kiểm write outcomes, repair/trace có kiểm soát |

## 15. Bài thực hành và câu hỏi tự kiểm tra

**Bài 1 — UTF-8 và NFC.** Chuẩn bị hai chuỗi tiếng Việt hiển thị giống nhau nhưng mã hóa theo NFC/NFD; nhập vào cột `text` và so code point/bytes. Nếu chuỗi là partition key, tại sao cần thống nhất normalization trước khi hash token?

**Bài 2 — CSV.** Một file chứa `"Cà phê, rang xay"` và một field nhiều dòng. Giải thích vì sao `split(",")` và đọc từng dòng riêng là sai. Thiết kế cách ghi error code khi gặp byte UTF-8 không hợp lệ hoặc BOM ở header.

**Bài 3 — Số nguyên lớn.** Nguồn gửi `9007199254740993`. Chuyển thử qua `double` rồi qua `long`; so với `Long.parseLong` từ chuỗi gốc. Vì sao chuyển qua floating point có thể gây mất ID hoặc số tiền?

**Bài 4 — Decimal.** Nhập `123.4500` vào cột `decimal`. So `BigDecimal.compareTo` và `BigDecimal.equals` với `123.45`. Khi nghiệp vụ cần đúng hai chữ số thập phân, nên chuẩn hóa scale ở đâu và xử lý làm tròn như thế nào?

**Bài 5 — UUID/timeuuid.** Tạo một UUIDv4 và thử dùng nó làm giá trị `timeuuid` trong lab. Vì sao schema dùng `uuid` sẽ khác? Khi event ID đến từ hệ thống nguồn, có nên sinh UUID mới mỗi lần retry không?

**Bài 6 — UTC/offset.** Cho `2026-11-21T16:30:00.123+07:00` và `2026-11-21T09:30:00.123Z`. Chứng minh chúng bằng nhau khi so `Instant`. CQL `timestamp` có giữ string `Asia/Ho_Chi_Minh` không?

**Bài 7 — Date/time và DST.** Một bản ghi chỉ có `2026-11-01 01:30:00` và zone có DST. Vì sao có thể tồn tại hai instant? Nêu thông tin tối thiểu cần bổ sung để chuyển đổi an toàn.

**Bài 8 — Null/UNSET.** Nguồn JSON không có trường `display_name`, nhưng record khác có `"display_name": null` và record thứ ba có `""`. Hãy chỉ ra vì sao ba trường hợp không mặc nhiên được chuyển thành cùng một mutation trong Cassandra.

**Bài 9 — CQL và Java.** Tạo schema `migration_lab.import_events_by_run`, ghi record mẫu bằng CQL và Java Driver, đọc lại kiểu `UUID`, `BigDecimal`, `BigInteger`, `Instant`, `LocalDate` và `LocalTime`. So thêm `WRITETIME(amount)` với `occurred_at`; tại sao khác nhau?

**Bài 10 — Quarantine/timeout.** Một file có 1.000 record: 20 lỗi parse, 970 ghi ACK, 10 write timeout. Có được báo đã nhập thành công 980 record không? Hãy phân loại `QUARANTINED`, `ACKNOWLEDGED` và `UNKNOWN_WRITE` trước khi xác minh lại 10 khóa.

**Bài 11 — Thay đổi schema.** Trước đây `total_minor` là `int`, nguồn mới cần hơn 2,1 tỷ. Vì sao không nên tự ép số và âm thầm overwrite? Đề xuất bảng mới với `bigint`, backfill, dual-read/cutover và đối soát theo ID.

**Bài 12 — Chuyển vùng.** Import vào `dc_a` bằng `LOCAL_QUORUM` trong cluster RF3+3 rồi ứng dụng đọc ngay ở `dc_b`. Vì sao đọc remote có thể chưa thấy một số event ACK? Thiết kế bước đối soát trước failover, không đánh đồng read timeout với missing.

## Ghi nhớ

**Migration Cassandra thành công không chỉ là `INSERT` thành công mà là dữ liệu đúng nghĩa sau mọi phép chuyển đổi.** Xác định charset và Unicode normalization trước khi nhập; giữ số nguyên/số tiền bằng kiểu chính xác; dùng UUID ổn định; tách `timestamp` là instant khỏi `date`, `time` và IANA timezone; luôn chỉ rõ offset hoặc quy tắc chuyển đổi được xác minh. Ghi CQL qua prepared statement với kiểu Java phù hợp, cách ly dữ liệu sai, quản lý `UNKNOWN_WRITE`, và **đối soát theo primary key/marker độc lập** trước khi cutover. Đây là nền tảng để thiết kế bảng theo truy vấn, replication, repair và phục hồi đáng tin cậy.
