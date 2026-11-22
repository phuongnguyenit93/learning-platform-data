# Ánh xạ số, `BigDecimal`, `UUID`, `Instant` và kiểu ngày giờ trong Java Driver Cassandra

## 1. Mục tiêu và bối cảnh

Trong Apache Cassandra, ứng dụng Java gửi CQL qua **Java Driver** tới coordinator; dữ liệu được lưu theo **partition key**, sao chép lên các replica theo **replication factor (RF)** và được đọc/ghi theo **consistency level (CL)**. Bên cạnh thiết kế bảng theo truy vấn và bảo đảm nhất quán, việc ánh xạ **đúng kiểu CQL ↔ Java** quyết định một request có giữ nguyên ý nghĩa dữ liệu hay không.

Ví dụ hệ thống thanh toán ghi `total_amount` bằng số thập phân, `event_id` bằng UUID và `occurred_at` bằng timestamp. Ba lỗi phổ biến:

- Chuyển `decimal` sang `double` rồi tính tiền, làm sai phần thập phân.
- Đưa `UUID.randomUUID()` vào cột `timeuuid`, vốn yêu cầu UUID dựa trên thời gian.
- Dùng `LocalDateTime` như một thời điểm tuyệt đối mà không chỉ định timezone, làm lệch ngày/giờ khi đọc ở DC khác.

Bài này sử dụng **API Java Driver 4.x** với namespace `com.datastax.oss.driver.api.core` và kiểu Java 8+ `java.time`. Cú pháp, artifact dependency, API mức thấp và ma trận tương thích có thể thay đổi theo **bản driver/bản phân phối Cassandra**; vì vậy cần kiểm tra release được dùng trong dự án trước khi triển khai production.

### Sau bài học, bạn cần làm được

1. Chọn Java type phù hợp với các kiểu số `tinyint`, `smallint`, `int`, `bigint`, `varint`, `decimal`, `float`, `double` và `counter`.
2. Hiểu `BigDecimal`, `BigInteger`, scale, precision, rounding và nguy cơ overflow.
3. Phân biệt `uuid`, `timeuuid` và UUID ngẫu nhiên hay dựa trên thời gian.
4. Ánh xạ `timestamp` ↔ `Instant`, `date` ↔ `LocalDate`, `time` ↔ `LocalTime`, `duration` ↔ `CqlDuration`.
5. Bind/đọc dữ liệu đúng cách với `PreparedStatement`, xử lý `null` và `UNSET`.
6. Viết test round-trip để chứng minh kiểu dữ liệu, độ chính xác và timezone không bị thay đổi ngoài ý muốn.

## 2. Bảng ánh xạ CQL ↔ Java Driver 4.x

Các mapping mặc định thường gặp:

| Kiểu CQL | Kiểu Java | Đọc từ `Row` | Điểm cần nhớ |
| --- | --- | --- | --- |
| `tinyint` | `byte` / `Byte` | `getByte(...)` | Số nguyên có dấu 8 bit |
| `smallint` | `short` / `Short` | `getShort(...)` | Số nguyên có dấu 16 bit |
| `int` | `int` / `Integer` | `getInt(...)` | Số nguyên có dấu 32 bit |
| `bigint` | `long` / `Long` | `getLong(...)` | Số nguyên có dấu 64 bit |
| `varint` | `BigInteger` | `getBigInteger(...)` | Số nguyên có độ dài biến đổi |
| `decimal` | `BigDecimal` | `getBigDecimal(...)` | Số thập phân chính xác tùy ý trong giới hạn tài nguyên |
| `float` | `float` / `Float` | `getFloat(...)` | IEEE 754, 32 bit, có sai số biểu diễn |
| `double` | `double` / `Double` | `getDouble(...)` | IEEE 754, 64 bit, vẫn có sai số |
| `counter` | `long` / `Long` | `getLong(...)` | Giá trị đọc là long; mutation counter có semantics riêng |
| `uuid` | `UUID` | `getUuid(...)` | Định danh, không tự có thứ tự thời gian |
| `timeuuid` | `UUID` | `getUuid(...)` | UUID version 1, chứa thành phần timestamp |
| `timestamp` | `Instant` | `getInstant(...)` | Mốc thời gian tuyệt đối, lưu độ chính xác mili-giây |
| `date` | `LocalDate` | `getLocalDate(...)` | Ngày lịch, không chứa giờ/múi giờ |
| `time` | `LocalTime` | `getLocalTime(...)` | Giờ trong ngày, độ chính xác nano-giây |
| `duration` | `CqlDuration` | `getCqlDuration(...)` | Months + days + nanoseconds; không mặc định là `Duration` |

**Điểm quan trọng:** `float`/`double` và `decimal` là những kiểu khác nhau; `bigint` và `varint` cũng vậy. Việc `Row` có những getter tiện lợi **không đồng nghĩa** driver sẽ âm thầm chuyển đổi mọi cột sang kiểu Java bất kỳ mà không mất dữ liệu. Getter, codec và kiểu CQL phải tương thích.

Với cột nullable, hãy **kiểm tra `row.isNull("column")` trước khi gọi getter số nguyên primitive**. Giá trị `0` không phải đại diện an toàn cho việc chưa có dữ liệu.

## 3. Kiểu số nguyên: chọn theo miền giá trị, không theo tên biến

Các kiểu nguyên có dấu thông thường:

| CQL | Số bit | Min | Max | Java |
| --- | ---: | ---: | ---: | --- |
| `tinyint` | 8 | -128 | 127 | `byte` |
| `smallint` | 16 | -32.768 | 32.767 | `short` |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 | `int` |
| `bigint` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | `long` |
| `varint` | Độ dài biến đổi | Không giới hạn cố định theo 8/16/32/64 bit | Giới hạn thực tế bởi tài nguyên/hệ thống | `BigInteger` |

Ví dụ:

```java
byte priority = 3;
short sensorNumber = 240;
int sampleCount = 1_000_000;
long sequenceNumber = 9_000_000_000L;
java.math.BigInteger veryLargeCount =
    new java.math.BigInteger("123456789012345678901234567890");
```

**Không chọn `int` chỉ vì số đếm hôm nay còn nhỏ**, nếu nghiệp vụ có thể vượt ~2,1 tỷ. Nhưng cũng không thay mọi cột bằng `varint`: số lớn không giới hạn 64 bit cần thêm chi phí serialization, lưu trữ, tính toán và kiểm thử; chọn schema dựa trên miền giá trị thực.

### Overflow ở Java xảy ra trước khi Cassandra nhìn thấy dữ liệu

```java
int oldValue = Integer.MAX_VALUE;
int wrong = oldValue + 1;  // Tràn số: trở thành số âm.

long safeSum = Math.addExact((long) oldValue, 1L);
```

Nếu tính toán đã overflow trong Java, bind sang cột `bigint` cũng **không khôi phục được giá trị đúng**. Dùng `Math.addExact`, kiểm tra phạm vi đầu vào hoặc `BigInteger` khi thực sự cần.

### `bigint` khác `varint`

`bigint` là số nguyên 64 bit; `varint` là số nguyên có độ dài biến đổi. Trong Java Driver 4.x:

```java
long fixed64 = 10_000_000_000L;
java.math.BigInteger variablePrecision =
    new java.math.BigInteger("1000000000000000000000000000000");
```

Không bind `BigInteger` vào `bigint` rồi kỳ vọng tự cắt xuống `long`. Nếu muốn chuyển có kiểm soát:

```java
long converted = variablePrecision.longValueExact();
// Ném ArithmeticException nếu giá trị nằm ngoài miền long.
```

Tương tự, `BigInteger.intValue()` có thể mất dữ liệu mà không báo lỗi; ưu tiên `intValueExact()` nếu nghiệp vụ yêu cầu kiểm tra chính xác.

## 4. `decimal` và `BigDecimal`: tiền tệ, thuế và độ chính xác

`decimal` là kiểu thập phân có độ chính xác tùy ý, phù hợp nhiều trường hợp tính tiền, tỷ lệ tài chính và dữ liệu cần giữ chữ số thập phân. Trong Java, kiểu tương ứng là `java.math.BigDecimal`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("129.95");
BigDecimal taxRate = new BigDecimal("0.08");

BigDecimal gross = price.multiply(BigDecimal.ONE.add(taxRate));
BigDecimal payable = gross.setScale(2, RoundingMode.HALF_EVEN);
```

**Tránh:**

```java
BigDecimal fragile = new BigDecimal(0.1);
// Chuyển đúng giá trị nhị phân double, không phải ý nghĩa "0.1" mong muốn.

double money = 0.1 + 0.2;
// double không biểu diễn chính xác mọi phân số thập phân.
```

**Ưu tiên** `new BigDecimal("0.1")` cho literal thập phân, hoặc `BigDecimal.valueOf(doubleValue)` khi đã nhận một double và chấp nhận ý nghĩa chuyển qua biểu diễn chuỗi của nó. Nếu giá trị nguồn là JSON số tiền, tốt hơn là parse trực tiếp thành `BigDecimal` thay vì trung gian `double`.

### Precision và scale

Một `BigDecimal` có **unscaled integer** và **scale**:

```java
BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("12.3");

System.out.println(a.scale());        // 2
System.out.println(b.scale());        // 1
System.out.println(a.compareTo(b));   // 0: cùng giá trị số học
System.out.println(a.equals(b));      // false: khác scale
```

Với giá tiền, cần quy tắc rõ về **đơn vị tiền, số chữ số thập phân, cách làm tròn và scale hợp lệ**. Cassandra `decimal` không tự ép mọi số về scale 2 theo quy tắc nghiệp vụ của hệ thống; nếu muốn giới hạn, **validate tại ranh giới ứng dụng**.

### Khi nào dùng `bigint` thay vì `decimal` cho tiền?

Nhiều hệ thống chọn `bigint total_cents` để lưu **đơn vị nhỏ nhất** (ví dụ cents) và tránh phép tính số thực. Cách này phù hợp khi:

- Đơn vị nhỏ nhất của tiền tệ đã được xác định chính xác.
- Tổng tiền luôn là số nguyên của đơn vị đó.
- Miền giá trị không vượt `long`.

Nếu cần số thập phân có scale linh hoạt, tỷ giá hoặc đơn vị đo có nhiều chữ số, `decimal`/`BigDecimal` thường thể hiện ý nghĩa trực tiếp hơn. **Không thể chọn đúng chỉ từ việc tên field có chữ “amount”**.

## 5. `float` và `double`: dùng cho số đo, không mặc nhiên cho tiền

`float` là số thực IEEE 754 32 bit; `double` là 64 bit. Cả hai lưu giá trị **xấp xỉ**, phù hợp nhiều số đo/cảm biến/điểm xác suất khi chấp nhận sai số. Chúng không đảm bảo phép cộng decimal chính xác.

```java
float signalStrength = 0.875f;
double confidence = 0.99d;

double sum = 0.1d + 0.2d;
System.out.println(sum);  // Có thể hiển thị 0.30000000000000004
```

So sánh số thực cần hiểu tolerance và miền dữ liệu; `==` không phù hợp cho mọi phép so sánh sau nhiều phép tính. Các giá trị đặc biệt như NaN/Infinity, tính hợp lệ của việc lưu/bind và thứ tự so sánh nên kiểm tra theo policy của dữ liệu và driver phiên bản đang dùng.

**Hãy chọn một đơn vị đo có tên rõ:** `temperature_celsius`, `distance_meters`, `ratio`. Không trộn dữ liệu float “đang là phần trăm 0–100” với double “đang là tỷ lệ 0–1” rồi đổ lỗi cho Java Driver.

## 6. `counter` đọc như `long` nhưng ghi rất khác `bigint`

Một cột CQL `counter` cũng đọc qua `Row.getLong(...)`, nhưng không phải cột `bigint` thông thường.

Ví dụ bảng counter riêng:

```sql
CREATE TABLE IF NOT EXISTS driver_types_lab.views_by_tenant_day (
    tenant_id text,
    bucket_day date,
    views counter,
    PRIMARY KEY ((tenant_id), bucket_day)
);

UPDATE driver_types_lab.views_by_tenant_day
SET views = views + 1
WHERE tenant_id = 'tenant-01'
  AND bucket_day = '2026-11-20';
```

Các lưu ý:

- Không `INSERT` hay ghi đè giá trị counter bằng phép `SET views = 100` như cột `bigint`.
- Mutation counter **không idempotent theo nghĩa retry cùng increment có thể tăng nhiều lần**. Không đặt `setIdempotent(true)` cho increment hoặc retry mù sau timeout.
- Counter có ràng buộc về schema, TTL và các thao tác CQL; đừng trộn chúng với cột dữ liệu thông thường trong cùng bảng theo giả định chung.
- Nếu nghiệp vụ cần “đúng một lần” cho phép cộng, phải thiết kế cơ chế chống trùng ở tầng nghiệp vụ, không dựa vào việc Java getter là `long`.

`counter` là ví dụ điển hình cho việc **kiểu Java giống nhau nhưng semantics dữ liệu khác nhau**.

## 7. `uuid` và `timeuuid`: cùng Java `UUID`, khác ý nghĩa

Java có `java.util.UUID`, phù hợp với cả CQL `uuid` và `timeuuid` ở phần đọc/bind, **nhưng Cassandra đặt ràng buộc khác lên giá trị**:

| CQL | Mục đích thường gặp | Java | Lưu ý |
| --- | --- | --- | --- |
| `uuid` | Định danh ngẫu nhiên hoặc do hệ thống cấp | `UUID` | UUID v4 thường dùng, không suy ra thứ tự tạo |
| `timeuuid` | UUID version 1 gắn yếu tố thời gian | `UUID` | Không bind UUID v4 vào `timeuuid` |

```java
import java.util.UUID;

UUID orderId = UUID.randomUUID();        // Thường là UUID v4.
UUID parsed = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

System.out.println(orderId.version());  // Thường trả 4.
System.out.println(parsed.version());   // 4 với literal minh họa.
```

Để tạo `timeuuid` trong Java Driver 4.x, các bản driver thường cung cấp tiện ích `Uuids.timeBased()`:

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.uuid.Uuids;

UUID eventTimeId = Uuids.timeBased();
if (eventTimeId.version() != 1) {
    throw new IllegalStateException("Expected a version-1 timeuuid");
}
```

Kiểm tra artifact/package thực tế của driver 4.x mà dự án dùng. Trong CQL, hàm `now()` trả một `timeuuid` được tạo ở phía server; **đừng dùng `now()` để thay ID ổn định trong một phép retry mà nghiệp vụ yêu cầu idempotent**.

### Có nên dùng UUID v4 làm clustering key để lấy sự kiện mới nhất?

UUID v4 là định danh ngẫu nhiên, **không sắp xếp theo thời gian tạo**. Nếu truy vấn cần các sự kiện mới nhất:

- Dùng `timestamp`/`created_at` làm clustering key phù hợp, kèm `event_id` để chống trùng; hoặc
- Dùng `timeuuid` trong thiết kế có query shape phù hợp và đã hiểu các giới hạn thời gian/clock.

`timeuuid` chứa dấu vết thời gian, **không bảo đảm thứ tự tuyệt đối giữa mọi sự kiện phân tán** khi clock lệch, retry hoặc tạo ID ở nhiều node. Nếu cần thứ tự nghiệp vụ nghiêm ngặt, phải dùng sequence/logic riêng.

### `minTimeuuid` / `maxTimeuuid`

Các hàm CQL như `minTimeuuid(...)` và `maxTimeuuid(...)` có thể giúp tạo ranh giới để tìm **timeuuid clustering keys theo khoảng thời gian**, trong query và phiên bản được hỗ trợ. Chúng tạo **giới hạn truy vấn**, không phải UUID sự kiện thực tế để ghi làm ID nghiệp vụ.

## 8. `timestamp` ↔ `Instant`: thời điểm tuyệt đối, không chứa timezone

CQL `timestamp` biểu diễn một **instant** theo số mili-giây kể từ Unix epoch. Java Driver 4.x ánh xạ tự nhiên sang `java.time.Instant`.

```java
import java.time.Instant;

Instant occurredAt = Instant.parse("2026-11-20T14:35:12.123Z");
// Z biểu thị UTC.
```

**Không được nhầm `timestamp` Cassandra với `timestamp with timezone` của một số hệ quản trị quan hệ.** Cassandra không lưu một trường “Asia/Ho_Chi_Minh” hay “Europe/Paris” bên trong giá trị `timestamp`. Khi cùng một instant được hiển thị theo timezone khác nhau, **giờ trên đồng hồ** thay đổi nhưng thời điểm thực không đổi.

### Mili-giây ở Cassandra, nano-giây ở Java

`Instant` giữ độ chính xác đến nano-giây, nhưng CQL `timestamp` có độ phân giải **mili-giây**. Ví dụ:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant original = Instant.parse("2026-11-20T14:35:12.123456789Z");
Instant normalized = original.truncatedTo(ChronoUnit.MILLIS);

System.out.println(normalized);
// 2026-11-20T14:35:12.123Z
```

Khi bind `original` xuống `timestamp` rồi đọc lại, **không kỳ vọng nano-giây 456789 được bảo tồn**. Trong test round-trip nên so với `normalized` hoặc yêu cầu độ chính xác mili-giây ngay từ đầu.

### Đừng nhầm `timestamp` với `USING TIMESTAMP`

Hai cú pháp có tên giống nhau nhưng ý nghĩa khác:

```sql
-- Cột timestamp: giá trị thời gian nghiệp vụ, độ phân giải mili-giây.
INSERT INTO driver_types_lab.measurements_by_id (
    tenant_id, business_day, event_id, occurred_at
) VALUES (
    'tenant-01', '2026-11-20',
    11111111-1111-4111-8111-111111111111,
    '2026-11-20T14:35:12.123Z'
);
```

Còn `USING TIMESTAMP 1795185312123456` (ví dụ số microsecond) là **timestamp của mutation dùng để hòa giải ghi theo cơ chế Cassandra**, không phải bắt buộc giá trị của cột `occurred_at`. Không tự động dùng cùng số mili-giây của `Instant.toEpochMilli()` làm `USING TIMESTAMP`, vì write timestamp có đơn vị **microsecond**.

Ví dụ CQL trên giả định keyspace/table được tạo ở mục 12; nếu thực hành tuần tự, hãy tạo schema đó trước.

## 9. `date` ↔ `LocalDate`: ngày lịch không có giờ

CQL `date` được ánh xạ sang `java.time.LocalDate`. Giá trị này chỉ biểu diễn **ngày trên lịch**, không lưu giờ phút hay offset.

```java
import java.time.LocalDate;

LocalDate businessDay = LocalDate.parse("2026-11-20");
LocalDate nextDay = businessDay.plusDays(1);
```

Trường hợp phù hợp:

- Ngày sinh (khi không cần thời điểm sinh chính xác).
- Ngày kinh doanh dùng làm **bucket partition**.
- Ngày đến hạn/đóng sổ theo một timezone nghiệp vụ đã xác định.

**Không tính ngày kinh doanh bằng cách lấy luôn `LocalDate.now()` trên máy ứng dụng mà không có timezone policy.** Hai JVM ở các khu vực khác nhau có thể đang thuộc hai ngày lịch khác nhau tại cùng một instant.

Ví dụ an toàn hơn:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = Instant.parse("2026-11-20T18:30:00Z");

LocalDate businessDay = instant.atZone(businessZone).toLocalDate();
// Ngày lịch tại vùng thời gian nghiệp vụ có thể khác UTC.
```

Trong Cassandra, `date` không tự chuyển đổi theo timezone khi lưu. **Phép chuyển timezone phải xảy ra tại biên ứng dụng có policy rõ ràng**.

## 10. `time` ↔ `LocalTime`: giờ trong ngày không phải thời điểm

CQL `time` lưu một thời điểm trong **ngày lịch** theo độ phân giải nano-giây, không gắn ngày hoặc timezone; Java Driver 4.x ánh xạ sang `LocalTime`.

```java
import java.time.LocalTime;

LocalTime scheduledHour = LocalTime.of(14, 35, 12, 123_456_789);
// 14:35:12.123456789, không nói ngày nào hoặc timezone nào.
```

Ví dụ phù hợp: giờ cửa hàng mở cửa, thời điểm chạy lịch theo ngày sau khi đã xác định **ZoneId** và quy tắc DST. Không dùng `LocalTime` để lưu thời điểm khách hàng click một nút: chỉ một giờ trong ngày không đủ phân biệt hai ngày khác nhau.

### Nếu cần mốc thời gian địa phương?

Một event có thể lưu:

- `occurred_at timestamp` → `Instant`, mốc UTC tuyệt đối.
- `business_day date` → `LocalDate`, bucket đã tính bằng business zone.
- `wall_time time` → `LocalTime`, giờ địa phương phục vụ hiển thị/lịch.
- `zone_id text` → `ZoneId` string trong ứng dụng nếu cần giữ timezone gốc.

Không ghép `LocalDate` + `LocalTime` thành một `Instant` bằng cách mặc định UTC nếu nghiệp vụ thực ra dùng vùng khác; với vùng có DST phải xử lý giờ không tồn tại hoặc giờ lặp.

## 11. `duration` ↔ `CqlDuration`: months, days và nanoseconds

CQL `duration` dùng ba thành phần: **months**, **days** và **nanoseconds**. Java Driver 4.x biểu diễn bằng `com.datastax.oss.driver.api.core.data.CqlDuration`, **không mặc định ánh xạ trực tiếp** sang `java.time.Duration` hay `Period`.

Ví dụ:

```java
import java.util.concurrent.TimeUnit;
import com.datastax.oss.driver.api.core.data.CqlDuration;

CqlDuration retentionWindow = CqlDuration.newInstance(
    1,                           // 1 tháng
    2,                           // 2 ngày
    TimeUnit.HOURS.toNanos(3)    // 3 giờ
);
```

**Vì sao không thay bằng `Duration.ofDays(32)`?** Tháng có độ dài thay đổi theo tháng lịch, ngày có thể bị ảnh hưởng bởi timezone/DST khi áp dụng cho mốc địa phương, còn `Duration` chỉ biểu diễn một khoảng thời gian tính bằng giây/nano-giây. Nếu cần cộng khoảng thời gian CQL vào một thời điểm, phải xác định rõ **ZoneId, thứ tự cộng tháng/ngày/nano và policy lịch**.

Các hạn chế thường gặp của `duration`:

- Các thành phần âm/dương phải tuân theo quy tắc nhất quán của CQL; không tự kết hợp tùy tiện tháng dương, ngày âm.
- Không dùng kiểu `duration` làm clustering key và kỳ vọng một thứ tự tổng quát có ý nghĩa cho mọi giá trị.
- Không chuyển `duration` thành một số mili-giây cố định nếu có tháng/ngày lịch mà chưa có mốc và timezone.
- Với TTL nghiệp vụ, hãy phân biệt `TTL` CQL đếm **giây** với giá trị `duration` được lưu ở một cột.

## 12. CQL lab: tạo bảng có đủ các kiểu số và thời gian

Thực hành trên **cluster Cassandra lab** có DC `dc1` và đủ replica cho RF3. Nếu chỉ có một node, hãy chỉnh RF và CL cho phù hợp; `LOCAL_QUORUM` với RF3 mà không đủ replica sẽ không hoạt động.

### Bước 1 — Tạo keyspace

```sql
CREATE KEYSPACE IF NOT EXISTS driver_types_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
```

### Bước 2 — Tạo bảng theo một mẫu đọc cụ thể

```sql
CREATE TABLE IF NOT EXISTS driver_types_lab.measurements_by_id (
    tenant_id text,
    business_day date,
    event_id uuid,
    priority tinyint,
    sensor_number smallint,
    sample_count int,
    sequence_number bigint,
    huge_quantity varint,
    total_amount decimal,
    signal_strength float,
    confidence double,
    occurred_at timestamp,
    wall_time time,
    event_time_id timeuuid,
    retention_window duration,
    PRIMARY KEY ((tenant_id, business_day), event_id)
);
```

**Partition key** là `(tenant_id, business_day)`, giúp giới hạn dữ liệu theo tenant/ngày; `event_id` là clustering key. Vì `event_id` được tạo ngẫu nhiên, bảng này **không bảo đảm thứ tự thời gian sự kiện**. Nếu API cần đọc 20 sự kiện mới nhất, phải thiết kế lại clustering key theo query shape, không “sửa” bằng codec của Java.

### Bước 3 — Ghi một hàng mẫu trong CQL

```sql
INSERT INTO driver_types_lab.measurements_by_id (
    tenant_id, business_day, event_id,
    priority, sensor_number, sample_count, sequence_number,
    huge_quantity, total_amount, signal_strength, confidence,
    occurred_at, wall_time, event_time_id
) VALUES (
    'tenant-01',
    '2026-11-20',
    11111111-1111-4111-8111-111111111111,
    3, 240, 150, 9000000000,
    123456789012345678901234567890,
    129.95, 0.875, 0.99,
    '2026-11-20T14:35:12.123Z',
    '14:35:12.123456789',
    now()
);
```

`retention_window` được bỏ qua có chủ ý và sẽ là null cho hàng này. Trong cqlsh, `now()` tạo `timeuuid`; **không dùng hàm đó trong một write cần retry idempotent mà giá trị ID phải ổn định**.

### Bước 4 — Đọc theo đủ partition key

```text
CONSISTENCY LOCAL_QUORUM;
```

```sql
SELECT priority, sensor_number, sample_count, sequence_number,
       huge_quantity, total_amount, signal_strength, confidence,
       occurred_at, business_day, wall_time, event_time_id,
       retention_window
FROM driver_types_lab.measurements_by_id
WHERE tenant_id = 'tenant-01'
  AND business_day = '2026-11-20'
  AND event_id = 11111111-1111-4111-8111-111111111111;
```

Đọc đúng partition không cần `ALLOW FILTERING`. Mọi kết quả chỉ có ý nghĩa trong CL đã chọn; thành công ở `LOCAL_QUORUM` không chứng minh mọi replica trong các DC khác đồng bộ ngay lập tức.

## 13. Java Driver 4.x: ghi các kiểu bằng `PreparedStatement`

Ví dụ repository dưới đây có thể biên dịch sau khi dự án thêm dependency Java Driver 4.x phù hợp và đã tạo schema ở mục 12. Nó minh họa **cùng một phương thức bind nhiều kiểu Java**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.data.CqlDuration;
import com.datastax.oss.driver.api.core.uuid.Uuids;

public final class MeasurementWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public MeasurementWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO driver_types_lab.measurements_by_id (" +
            "tenant_id, business_day, event_id, priority, sensor_number, " +
            "sample_count, sequence_number, huge_quantity, total_amount, " +
            "signal_strength, confidence, occurred_at, wall_time, " +
            "event_time_id, retention_window) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public UUID writeSample(String tenantId, LocalDate businessDay) {
        // Tạo ID một lần; trong code production, caller nên cấp
        // ID ổn định để xử lý outcome unknown và retry.
        UUID eventId = UUID.randomUUID();
        UUID timeUuid = Uuids.timeBased();
        Instant occurredAt = Instant.parse(
            "2026-11-20T14:35:12.123456789Z")
            .truncatedTo(ChronoUnit.MILLIS);

        BigDecimal amount = new BigDecimal("129.95");
        BigInteger hugeQuantity =
            new BigInteger("123456789012345678901234567890");
        CqlDuration duration = CqlDuration.newInstance(
            1, 2, TimeUnit.HOURS.toNanos(3));

        BoundStatement statement = insert.bind(
            tenantId,
            businessDay,
            eventId,
            (byte) 3,
            (short) 240,
            150,
            9_000_000_000L,
            hugeQuantity,
            amount,
            0.875f,
            0.99d,
            occurredAt,
            LocalTime.of(14, 35, 12, 123_456_789),
            timeUuid,
            duration
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        // Không tự đánh dấu mọi write idempotent.
        session.execute(statement);
        return eventId;
    }
}
```

### Giải thích các giá trị được bind

| Java value | Cột CQL | Ý nghĩa |
| --- | --- | --- |
| `(byte) 3` | `priority tinyint` | Tránh bind nhầm `Integer` cho `tinyint` |
| `(short) 240` | `sensor_number smallint` | Rõ phạm vi 16 bit |
| `150` | `sample_count int` | Kiểu nguyên 32 bit |
| `9_000_000_000L` | `sequence_number bigint` | Hậu tố `L` cho `long` |
| `BigInteger` | `huge_quantity varint` | Không ép xuống `long` |
| `BigDecimal` | `total_amount decimal` | Không qua `double` |
| `0.875f` và `0.99d` | `float`, `double` | Phân biệt chính xác kiểu Java |
| `Instant` | `occurred_at timestamp` | Đã chuẩn hóa mili-giây |
| `LocalDate` | `business_day date` | Không chứa timezone |
| `LocalTime` | `wall_time time` | Nano-giây của giờ trong ngày |
| `Uuids.timeBased()` | `event_time_id timeuuid` | UUID version 1 |
| `CqlDuration` | `retention_window duration` | Tháng + ngày + nano-giây |

**Không tạo UUID mới mỗi lần retry của cùng logical write.** Nếu request timeout, mutation có thể đã được áp dụng nhưng ACK bị mất. Khi caller lặp lại phương thức và nhận một `eventId` khác, hệ thống sẽ có **hai event** thay vì một lần ghi được phục hồi.

Trong ứng dụng thật, nên nhận ID/operation ID từ caller, định nghĩa chính sách idempotency, timestamp và xử lý outcome unknown. Với counter và LWT, quy tắc retry còn khác nữa.

## 14. Java Driver 4.x: đọc lại bằng getter đúng kiểu

Ví dụ phương thức đọc từ cùng bảng, lưu ý xác định **đầy đủ partition key và clustering key**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlDuration;

public final class MeasurementReader {
    private final CqlSession session;
    private final PreparedStatement select;

    public MeasurementReader(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT priority, sensor_number, sample_count, " +
            "sequence_number, huge_quantity, total_amount, " +
            "signal_strength, confidence, occurred_at, " +
            "business_day, wall_time, event_time_id, retention_window " +
            "FROM driver_types_lab.measurements_by_id " +
            "WHERE tenant_id = ? AND business_day = ? AND event_id = ?"
        );
    }

    public void inspect(String tenantId, LocalDate day, UUID eventId) {
        BoundStatement statement = select.bind(tenantId, day, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        Row row = session.execute(statement).one();
        if (row == null) {
            throw new IllegalStateException("Event not found");
        }

        byte priority = row.getByte("priority");
        short sensor = row.getShort("sensor_number");
        int samples = row.getInt("sample_count");
        long sequence = row.getLong("sequence_number");
        BigInteger hugeQuantity = row.getBigInteger("huge_quantity");
        BigDecimal amount = row.getBigDecimal("total_amount");
        float strength = row.getFloat("signal_strength");
        double confidence = row.getDouble("confidence");
        Instant occurred = row.getInstant("occurred_at");
        LocalDate businessDay = row.getLocalDate("business_day");
        LocalTime wallTime = row.getLocalTime("wall_time");
        UUID timeId = row.getUuid("event_time_id");

        CqlDuration retention = row.isNull("retention_window")
            ? null : row.getCqlDuration("retention_window");

        // Dùng các giá trị để tạo DTO/kiểm thử; không cần log dữ liệu
        // nghiệp vụ hoặc raw partition keys trong production.
        if (timeId != null && timeId.version() != 1) {
            throw new IllegalStateException("Unexpected timeuuid version");
        }
    }
}
```

Trong đoạn code này, các local variables chủ yếu để minh họa getter. Một ứng dụng hoàn chỉnh sẽ tạo DTO immutable, validate business invariants và trả kết quả cho service. **Đừng bỏ qua kiểm tra `row.isNull(...)` cho cột nullable**, đặc biệt nếu dùng primitive numeric getters mà giá trị 0 có ý nghĩa khác “chưa có”.

### Tại sao nên tránh `SELECT *` trong repository?

`SELECT *` có thể trả cột mới sau schema migration; mapper cứng hoặc codec custom có thể bất ngờ nhận cấu trúc khác. Dùng danh sách cột tường minh giúp:

- Chỉ fetch dữ liệu cần thiết.
- Giữ contract giữa database và ứng dụng dễ kiểm soát.
- Giảm payload và rủi ro biến động khi schema tiến hóa.
- Viết test rõ từng kiểu CQL/Java.

## 15. `null` và `UNSET`: khác nhau ở đường ghi

Một bảng Cassandra có thể có cột chưa từng được ghi. Ở đường đọc, `row.isNull("column")` giúp phân biệt **không có giá trị** với giá trị thật; ở đường ghi, **NULL và UNSET khác nhau**.

| Tình huống | Ý nghĩa thực tế |
| --- | --- |
| Bind một giá trị hợp lệ | Ghi mutation mới cho cột |
| `statement.setToNull("col")` | Yêu cầu đặt cột thành null/xóa giá trị theo semantics CQL, có thể sinh tombstone |
| `statement.unset("col")` | Bỏ qua assignment của cột đó trong mutation hỗ trợ UNSET |
| Không SELECT cột | Không có dữ liệu trả về cho cột đó trong `Row`; không được gọi getter tùy ý |
| Cột SELECT có null | `row.isNull("col") == true` |

Một ví dụ cập nhật có điều kiện ứng dụng:

```java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement prepared = session.prepare(
    "UPDATE driver_types_lab.measurements_by_id " +
    "SET total_amount = ?, confidence = ? " +
    "WHERE tenant_id = ? AND business_day = ? AND event_id = ?"
);

BoundStatement statement = prepared.bind(
    new java.math.BigDecimal("99.50"),
    0.95d, tenantId, businessDay, eventId
);

// Giữ nguyên confidence hiện có: không ghi lại cột này.
statement = statement.unset(1);

// Tránh statement.setToNull(1) nếu mục đích là "không thay đổi".
session.execute(statement);
```

Đây là **trích đoạn đặt trong method** đã có `session`, `tenantId`, `businessDay` và `eventId`. `unset(1)` ở ví dụ là marker thứ hai (index 0-based). Trong ứng dụng thật, nên dùng tên marker nhất quán và kiểm tra chính xác bound variable definitions, tránh lệch vị trí khi sửa câu CQL.

**UNSET không phải giải pháp mặc định cho mọi thứ:** tính hỗ trợ phụ thuộc statement/protocol, và việc bỏ qua cột có thể làm logic “PATCH” khác “REPLACE”. Đặc biệt không dùng `null` để đại diện “không thay đổi” trong update một cách vô thức.

## 16. Đơn vị thời gian: mili-giây, micro-giây và nano-giây

Đây là một trong những lỗi ánh xạ gây hậu quả khó phát hiện nhất.

| Đại lượng | Đơn vị/ý nghĩa | Java/CQL |
| --- | --- | --- |
| `timestamp` column | Mili-giây tính từ epoch | `Instant` qua `getInstant` |
| `USING TIMESTAMP` | Micro-giây dùng làm write timestamp | `long` trong CQL statement |
| `time` column | Nano-giây tính từ 00:00 của một ngày | `LocalTime` |
| `duration` nanoseconds component | Nano-giây thuộc một duration có thể thêm tháng/ngày | `CqlDuration` |
| `System.nanoTime()` | Đồng hồ đơn điệu phù hợp đo khoảng thời gian trong JVM | Không phải Unix timestamp |
| `System.currentTimeMillis()` | Mili-giây UTC epoch theo clock hệ thống | Có thể chuyển sang `Instant` |

Ví dụ:

```java
import java.time.Instant;

Instant now = Instant.now();
long epochMillis = now.toEpochMilli();

// Chỉ minh họa đổi đơn vị: không mặc định dùng giá trị này
// làm write timestamp trong production không có concurrency policy.
long epochMicros = Math.multiplyExact(epochMillis, 1_000L);
```

Việc nhân `1.000` từ mili-giây thành micro-giây **không khôi phục những microsecond đã mất**; nó đặt phần microsecond thấp bằng 0. Nếu hệ thống cần write timestamp với độ phân giải cao hơn, phải có nguồn và cơ chế đồng bộ được thiết kế đúng.

### Timezone không phải phép cộng cố định giờ

`Asia/Ho_Chi_Minh` có offset thông dụng +07:00 hiện nay, nhưng quy tắc timezone lịch sử hoặc vùng khác có DST. **Không viết `epoch + 7h` thủ công** để chuyển một `Instant` thành giờ địa phương. Hãy dùng `ZoneId` và `ZonedDateTime`.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-20T18:30:00Z");
ZonedDateTime businessTime = instant.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh"));
```

## 17. Kiểm thử round-trip và tương thích schema

Một test round-trip ghi một giá trị từ Java xuống Cassandra, đọc lại, rồi so sánh theo **semantics của từng kiểu**:

| Kiểu | Assertion đúng | Assertion dễ sai |
| --- | --- | --- |
| `decimal` | `stored.compareTo(expected) == 0` nếu chỉ quan tâm số học | `equals` khi scale khác mà business không quan tâm |
| `varint` | `stored.equals(expectedBigInteger)` | Ép sang `long` rồi so |
| `float`/`double` | So theo tolerance/độ chính xác yêu cầu | So trực tiếp với kết quả tính toán thập phân lý tưởng |
| `uuid` | `stored.equals(expectedUuid)` | Mong UUID v4 được sắp theo thời gian |
| `timeuuid` | Giá trị UUID hợp lệ version 1, ổn định theo operation | Tạo một UUID mới mỗi retry và mong cùng ID |
| `timestamp` | So với `Instant` đã chuẩn hóa mili-giây | So nanosecond ban đầu nguyên vẹn |
| `date` | `LocalDate.equals` trong business timezone đã xác định | So `Instant` với ngày mà không có zone |
| `time` | `LocalTime.equals` nếu data được lưu hợp lệ | Suy ra ngày/zone từ riêng `LocalTime` |
| `duration` | So ba thành phần tháng/ngày/nanosecond | Đổi mọi tháng thành 30 ngày |

Test nên có dữ liệu biên:

- `tinyint` = -128, 0, 127; `smallint` biên ±32.767 và các giá trị âm hợp lệ.
- `int`/`bigint` ở gần giá trị cực đại, test overflow trước bind.
- `varint` lớn hơn 64 bit và `decimal` có scale khác nhau.
- `float`/`double` có sai số biểu diễn, giá trị âm và zero.
- `timestamp` trước và sau epoch, giá trị có sub-millisecond.
- Ngày cuối tháng, cuối năm, năm nhuận, DST tại vùng có thay đổi offset.
- Cột nullable, prepared statement có `UNSET`, retry và timeout.

### Schema evolution có thể làm codec sai cách

Nếu một cột đổi từ `int` thành `bigint` hoặc từ `text` thành `decimal`, **không đổi type tại chỗ một cách tùy tiện** chỉ vì Java có thể ép kiểu. Nhiều thay đổi type bị giới hạn hoặc phá vỡ hợp đồng đã prepare.

Quy trình an toàn thường là tạo `amount_v2 decimal`, deploy reader/writer tương thích, backfill, đối soát, rồi chuyển hẳn. Test cả ứng dụng cũ/mới, metadata driver, CL và giá trị null.

## 18. Chẩn đoán lỗi type mapping trong ứng dụng Java

| Dấu hiệu | Khả năng thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Codec exception hoặc invalid type | Bind/getter Java không khớp CQL type | `system_schema.columns`, metadata prepared, Java type |
| `ArithmeticException` khi chuyển số | `BigInteger` vượt `long`, `BigDecimal` rounding exact thất bại | Range, precision/scale, business constraints |
| Tiền sai vài đơn vị nhỏ | `double` được dùng thay `BigDecimal` | Nguồn số, phép tính, policy rounding |
| `timeuuid` bị từ chối | UUID v4 được bind vào CQL `timeuuid` | `UUID.version()` và cách tạo |
| Timestamp chênh vài giờ | LocalDateTime/zone/offset bị hiểu sai | `Instant`, `ZoneId`, timezone lúc parse |
| Timestamp lệch micro/nano | Cassandra `timestamp` chỉ mili-giây | Normalize/test độ phân giải |
| Ngày bucket lệch giữa DC | Tính `LocalDate.now()` theo timezone máy chủ | Business timezone cố định |
| Số trả về 0 thay vì null | Getter primitive không kiểm tra null | `row.isNull(...)` |
| UPDATE vô tình xóa trường | Bind null thay vì UNSET | Semantics PATCH/REPLACE và tombstone |
| Một sự kiện xuất hiện hai lần | Tạo UUID mới khi retry write outcome unknown | ID ổn định và idempotency |
| `Unavailable` hoặc timeout | RF/CL, node/replica/network thay vì Java codec | `nodetool status`, driver errors, CL, p99 |

Phân biệt **type/codec failure** và **distributed-system failure**: Java Driver không thể chuyển `BigDecimal` sang cột sai kiểu là lỗi dữ liệu/schema; request timeout với `LOCAL_QUORUM` có thể là vấn đề replica, disk, network hoặc deadline.

Một số lệnh chẩn đoán an toàn trong lab:

```bash
nodetool status
nodetool tablestats driver_types_lab.measurements_by_id
nodetool tablehistograms driver_types_lab measurements_by_id
nodetool tpstats
```

Thông số `nodetool` là **node-local**, không trực tiếp cho biết exception xảy ra trong Java codec. Kết hợp với logs driver đã loại dữ liệu nhạy cảm, metadata query, version và test input cụ thể.

## 19. Bài tập áp dụng

### Tình huống A — Tiền bị lệch 0,01

Service ghi tổng tiền bằng `double`, sau đó dùng `new BigDecimal(double)` và làm tròn. Một số hóa đơn sai một cent sau nhiều phép tính. Sửa ở đâu?

**Đáp án định hướng:** Dùng `decimal`/`BigDecimal` xuyên suốt hoặc `bigint` của đơn vị tiền nhỏ nhất; parse trực tiếp từ decimal string và thống nhất rounding/scale. Không chỉ đổi getter ở cuối.

### Tình huống B — `event_id` ngẫu nhiên nhưng muốn lấy mới nhất

Schema `PRIMARY KEY ((tenant_id, day), event_id uuid)` và code dùng `UUID.randomUUID()`. API gọi `LIMIT 20` rồi gọi đó là 20 sự kiện mới nhất. Sai gì?

**Đáp án định hướng:** Clustering trên UUID v4 không sắp theo thời gian. Thiết kế clustering theo `occurred_at` cộng ID hoặc dùng timeuuid phù hợp với query shape; `LIMIT` không tạo thứ tự thời gian từ UUID v4.

### Tình huống C — Đồng hồ Java có nano-giây

`Instant.parse("2026-11-20T14:35:12.123456789Z")` được bind vào `timestamp`. Đọc lại còn `.123Z`, test `equals` thất bại. Cassandra làm mất dữ liệu?

**Đáp án định hướng:** `timestamp` lưu mili-giây. Đây là giới hạn độ phân giải cần được xác định trước; normalize hoặc dùng mô hình lưu trữ khác khi cần nanosecond chính xác.

### Tình huống D — Sai ngày khi đặt bucket

Service ở hai timezone tính `LocalDate.now()` rồi ghi cùng một sự kiện UTC. Một service ghi bucket ngày 20, service kia ngày 21. Có nên dùng `date` khác không?

**Đáp án định hướng:** Kiểu `date` đúng nếu bucket là ngày nghiệp vụ; lỗi nằm ở **timezone policy**. Tính `businessDay = instant.atZone(businessZone).toLocalDate()` thống nhất, không dùng timezone mặc định của JVM.

### Tình huống E — `duration` một tháng

Người học đổi `1mo` thành `Duration.ofDays(30)` rồi áp dụng cho ngày 31/01. Có đúng với mọi lịch không?

**Đáp án định hướng:** Không. Tháng có số ngày khác nhau; cần xử lý tháng/ngày theo calendar, zone và quy tắc nghiệp vụ, không mặc định 30 ngày.

### Tình huống F — Không phân biệt null và zero

Một cột `sample_count int` được thêm sau migration. Repository dùng `getInt` mà không kiểm tra null; dashboard hiển thị 0 cho hàng lịch sử. Vì sao nguy hiểm?

**Đáp án định hướng:** “Chưa có dữ liệu” khác “có đúng 0 mẫu”. Đọc `row.isNull` trước rồi map về `Integer`/`OptionalInt` hoặc trạng thái domain thích hợp.

### Tình huống G — Retry counter

Ứng dụng gửi `UPDATE ... SET views = views + 1`, bị timeout rồi retry tự động hai lần vì nghĩ `counter` chỉ là `long`. Kết quả có thể là bao nhiêu?

**Đáp án định hướng:** Outcome chưa xác định; increment có thể đã áp dụng trước timeout và retry có thể cộng thêm. Không dùng retry idempotent cho mutation counter; nếu cần chính xác từng event phải thiết kế chống trùng riêng.

### Tình huống H — `BigDecimal.equals` báo khác

Hai hàng đọc được `12.30` và `12.3`, so `equals` thấy khác dù giá trị tiền bằng nhau. Driver bị lỗi?

**Đáp án định hướng:** Không nhất thiết. `BigDecimal.equals` xét cả scale; `compareTo` xét giá trị số học. Ứng dụng phải có quy tắc scale/currency trước khi so.

## 20. Checklist production

**Schema và kiểu**

- [ ] Chọn đúng `tinyint`/`smallint`/`int`/`bigint` theo miền giá trị; dùng `varint` khi cần vượt 64 bit.
- [ ] Dùng `decimal` + `BigDecimal` cho giá trị yêu cầu số thập phân chính xác; định nghĩa scale/rounding và đơn vị.
- [ ] Không lẫn `counter` với `bigint` dù cùng Java getter `long`.
- [ ] Dùng `UUID` cho `uuid` và UUID version 1 cho `timeuuid`; không coi UUID v4 có thứ tự thời gian.
- [ ] Dùng `Instant` cho `timestamp` và ghi rõ độ chính xác **mili-giây**.
- [ ] Dùng `LocalDate` cho `date`, `LocalTime` cho `time`, `CqlDuration` cho `duration`.
- [ ] Dùng một `ZoneId` nghiệp vụ rõ ràng để tính bucket/ngày, không dựa vào timezone mặc định JVM.

**Java Driver và đường dữ liệu**

- [ ] Dùng lại `CqlSession`, chuẩn bị `PreparedStatement` và bind kiểu chính xác.
- [ ] Gọi getter tương ứng, kiểm tra `row == null` và `row.isNull`.
- [ ] Phân biệt `setToNull` với `unset` trong update/PATCH.
- [ ] Không tạo ID mới cho retry của cùng logical operation; xem outcome unknown và idempotency.
- [ ] Giữ RF/CL đúng nghiệp vụ; không dùng thay đổi CL để che lỗi codec.
- [ ] Bật TLS/auth, cấu hình local DC/contact points và bảo vệ secret theo môi trường.
- [ ] Tránh `SELECT *` nếu mapper/schema cần contract ổn định.

**Kiểm thử, vận hành và migration**

- [ ] Có round-trip test cho số lớn, số âm, decimals nhiều scale, null, UUID/timeuuid và ngày giờ biên.
- [ ] So `Instant` sau khi chuẩn hóa độ chính xác, không yêu cầu nano-giây từ CQL `timestamp`.
- [ ] Test timezone và DST theo vùng mà nghiệp vụ hỗ trợ.
- [ ] Test schema migration trên dữ liệu cũ, codec cũ/mới và nhiều bản ứng dụng.
- [ ] Đo p95/p99, timeout, retries và lỗi codec riêng; không gộp mọi lỗi thành “database chậm”.
- [ ] Xác minh API Java Driver 4.x và Cassandra version/distribution sử dụng thực tế trước production.

**Ghi nhớ:** Ánh xạ kiểu Cassandra sang Java là **hợp đồng về độ chính xác và ý nghĩa**. `decimal` dùng `BigDecimal`, `varint` dùng `BigInteger`, `uuid`/`timeuuid` dùng `UUID` nhưng khác ràng buộc, `timestamp` dùng `Instant` với độ chính xác mili-giây, `date` dùng `LocalDate`, `time` dùng `LocalTime` và `duration` dùng `CqlDuration`. Khi kết hợp `PreparedStatement`, kiểm tra null/UNSET, timezone, retry và thiết kế partition theo truy vấn, ứng dụng Java mới giữ được dữ liệu đúng trong một cluster Cassandra phân tán.
