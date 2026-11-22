# Ánh xạ kiểu thời gian và định dạng ngày tùy chỉnh

Trong Elasticsearch, ngày giờ là một kiểu dữ liệu có mapping riêng. Spring Data Elasticsearch cho phép khai báo field ngày giờ trên entity Java bằng `@Field`, đồng thời chuyển đổi các kiểu thời gian như `Instant`, `LocalDate`, `LocalDateTime`, `OffsetDateTime` hoặc `Date` sang định dạng mà Elasticsearch hiểu được.

Khi tích hợp hai hệ thống, vấn đề thường không chỉ là chọn một kiểu Java. Ứng dụng còn phải thống nhất ý nghĩa múi giờ, độ chính xác thời gian, định dạng chuỗi được gửi lên, cách Elasticsearch parse dữ liệu và cách API trả ngày giờ cho client. Nếu các lớp này dùng quy ước khác nhau, một giá trị có thể bị lệch giờ, mất phần mili giây hoặc bị từ chối khi lập chỉ mục.

Bài học này giải thích kiểu `date` và `date_nanos`, cách ánh xạ kiểu thời gian Java, cách cấu hình `format` và `pattern` tùy chỉnh, cách xử lý timezone và cách phân biệt định dạng của Elasticsearch với định dạng JSON do Jackson quản lý.

## 1. Elasticsearch biểu diễn ngày giờ như thế nào?

Elasticsearch có kiểu field `date` để lưu ngày hoặc thời điểm. Khi lập chỉ mục, giá trị ngày được chuẩn hóa thành số nguyên biểu diễn thời gian tính từ Unix epoch (1970-01-01T00:00:00Z). Với kiểu `date`, đơn vị nội bộ là millisecond. Nhờ đó, Elasticsearch có thể sắp xếp, lọc theo khoảng thời gian, thực hiện date math và aggregation trên dữ liệu ngày giờ.

Một field `date` có thể nhận dữ liệu đầu vào dưới dạng:

- Chuỗi ngày giờ theo một trong các format được mapping cho phép.
- Số nguyên biểu diễn epoch milliseconds.
- Một giá trị ngày giờ có timezone/offset, nếu format hỗ trợ phần đó.

Ví dụ document:

```json
{
  "eventName": "OrderCreated",
  "occurredAt": "2026-11-13T09:30:00Z"
}
```

Mapping:

```json
{
  "properties": {
    "occurredAt": {
      "type": "date"
    }
  }
}
```

Elasticsearch parse chuỗi theo format của field rồi chuẩn hóa giá trị để lập chỉ mục. `_source` thường vẫn giữ dạng JSON được gửi ban đầu, trong khi giá trị dùng cho sort, range query và các thao tác trên field date được xử lý theo kiểu ngày giờ của Elasticsearch.

### 1.1. `date` và `date_nanos`

Elasticsearch có hai kiểu thời gian phổ biến:

| Kiểu | Độ chính xác | Trường hợp sử dụng |
|---|---|---|
| `date` | Mili giây | Thời điểm tạo/cập nhật, ngày nghiệp vụ, lịch hẹn, log thông thường |
| `date_nanos` | Nano giây | Sự kiện có yêu cầu độ chính xác rất cao, telemetry hoặc dữ liệu giao dịch cần phân biệt thời điểm gần nhau |

`date_nanos` lưu thời gian với độ chính xác nano giây nhưng có phạm vi biểu diễn hẹp hơn `date` (xấp xỉ từ năm 1970 đến năm 2262). Không nên chọn `date_nanos` chỉ vì kiểu Java có nanosecond; hãy chọn khi hệ thống thực sự cần độ chính xác đó và tất cả thành phần liên quan hỗ trợ.

Độ chính xác của field Elasticsearch cũng không đảm bảo ứng dụng giữ được toàn bộ độ chính xác. Nếu converter, kiểu Java, JSON serializer hoặc nguồn dữ liệu chỉ cung cấp mili giây, phần nano giây đã mất trước khi Elasticsearch nhận request.

## 2. Chọn kiểu thời gian Java phù hợp

Java Time API cung cấp nhiều kiểu biểu diễn thời gian. Chọn kiểu dựa trên ý nghĩa nghiệp vụ, không chỉ dựa vào định dạng chuỗi.

| Kiểu Java | Ý nghĩa | Dùng khi |
|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên dòng thời gian UTC | Event, log, thời điểm tạo/cập nhật, timestamp hệ thống |
| `OffsetDateTime` | Ngày giờ kèm UTC offset cụ thể | API cần giữ offset mà client cung cấp |
| `ZonedDateTime` | Ngày giờ gắn với một timezone ID, ví dụ `Asia/Ho_Chi_Minh` | Lịch hoặc quy tắc phụ thuộc múi giờ địa lý |
| `LocalDateTime` | Ngày giờ địa phương không có offset/timezone | Thời gian trên đồng hồ địa phương, khi nghiệp vụ tự quy định timezone bên ngoài |
| `LocalDate` | Ngày lịch không có thời điểm trong ngày | Ngày sinh, ngày hóa đơn, ngày hiệu lực theo lịch |
| `LocalTime` | Giờ trong ngày không có ngày | Giờ mở cửa hoặc giờ lặp lại hằng ngày; không phải một timestamp độc lập |
| `java.util.Date` | Một thời điểm tính theo epoch milliseconds | Tích hợp mã Java cũ |
| `Calendar` | Thời điểm cùng các quy tắc lịch/timezone | Mã legacy cần tương thích API cũ |

Đối với event xảy ra tại một thời điểm cụ thể, `Instant` thường là lựa chọn rõ ràng nhất. Nó không mang timezone hiển thị của người dùng; nó biểu diễn một thời điểm duy nhất. Có thể chuyển `Instant` sang múi giờ địa phương khi hiển thị.

`LocalDateTime` không chứa timezone hoặc offset. Giá trị `2026-11-13T09:30:00` tự nó không cho biết đó là 09:30 ở Việt Nam, London hay UTC. Nếu nghiệp vụ dùng `LocalDateTime`, cần xác định timezone ở một lớp khác và chuyển đổi rõ ràng trước khi so sánh với thời điểm tuyệt đối.

Với ngày lịch như ngày sinh, không nên tự biến nó thành nửa đêm UTC nếu nghiệp vụ không yêu cầu. Dùng `LocalDate` giúp giữ đúng ý nghĩa ngày mà không tạo ra sai lệch khi người dùng ở múi giờ khác.

## 3. Ánh xạ field date bằng `@Field`

Trong Spring Data Elasticsearch, `@Field` mô tả kiểu dữ liệu của thuộc tính trong Elasticsearch mapping. Ví dụ entity có timestamp tạo đơn hàng:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters and setters
}
```

`FieldType.Date` tạo mapping field Elasticsearch kiểu `date`. Spring Data Elasticsearch sử dụng mapping metadata và conversion infrastructure để chuyển giá trị Java sang giá trị phù hợp khi ghi và đọc.

Mapping tương ứng về mặt khái niệm:

```json
{
  "properties": {
    "status": {
      "type": "keyword"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
```

Nếu không chỉ định format riêng, Elasticsearch dùng format mặc định của kiểu `date`, thường là `strict_date_optional_time||epoch_millis`. Điều đó cho phép nhận chuỗi ngày giờ theo ISO phù hợp hoặc epoch milliseconds. Khi làm việc với format mặc định, nên ưu tiên chuỗi ISO-8601 có `Z` hoặc offset rõ ràng cho các timestamp tuyệt đối.

Các kiểu Java Time được hỗ trợ và cách chuyển đổi cụ thể phụ thuộc phiên bản Spring Data Elasticsearch cùng cấu hình conversions. Với các kiểu phổ biến, Spring Data cung cấp chuyển đổi sẵn; nếu dùng kiểu tự định nghĩa hoặc quy tắc biểu diễn đặc biệt, có thể cần custom converter.

## 4. Dùng `DateFormat` và `pattern` cho định dạng tùy chỉnh

Khi hệ thống nguồn gửi ngày giờ theo định dạng riêng, có thể khai báo format cho field. Spring Data Elasticsearch cung cấp `format` và `pattern` trên `@Field`.

Ví dụ, hệ thống legacy gửi chuỗi `2026-11-13 16:45:30`:

```java
import java.time.LocalDateTime;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.DateFormat;

@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "yyyy-MM-dd HH:mm:ss"
)
private LocalDateTime importedAt;
```

`DateFormat.custom` cho biết field sử dụng pattern tùy chỉnh. `pattern` mô tả định dạng mà Elasticsearch dùng để parse ngày giờ. Spring Data dùng metadata mapping này khi tạo index và chuyển đổi dữ liệu.

Mapping tương ứng trong Elasticsearch có dạng:

```json
{
  "properties": {
    "importedAt": {
      "type": "date",
      "format": "yyyy-MM-dd HH:mm:ss"
    }
  }
}
```

Nếu muốn chấp nhận nhiều định dạng đầu vào, Elasticsearch hỗ trợ nối các format bằng `||`. Ví dụ:

```java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd'T'HH:mm:ssXXX||epoch_millis"
)
private Instant occurredAt;
```

Mapping cho phép các giá trị theo một trong các định dạng đã khai báo. Hãy chỉ chấp nhận những format nguồn thực sự cần hỗ trợ. Danh sách format quá rộng làm dữ liệu đầu vào khó dự đoán và có thể khiến các hệ thống gửi cùng một trường theo nhiều quy ước khác nhau.

### 4.1. Phân biệt `format` và `pattern`

- `format` trong annotation là danh sách các định dạng có sẵn của Elasticsearch, được biểu diễn bằng `DateFormat`.
- `pattern` cung cấp mẫu định dạng tùy chỉnh. Khi dùng pattern tùy chỉnh, thường khai báo `format = DateFormat.custom`.

Các giá trị enum và mẫu format khả dụng phụ thuộc phiên bản Spring Data Elasticsearch/Elasticsearch. Hãy đối chiếu API của dependency đang dùng nếu cần một format cụ thể. Tránh tự tạo enum hoặc tên format không có trong phiên bản thư viện.

### 4.2. Dùng format ISO-8601

Đối với timestamp có offset, có thể khai báo pattern nhận chuỗi ISO-8601 phù hợp:

```java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"
)
private OffsetDateTime receivedAt;
```

Ví dụ dữ liệu:

```json
{
  "receivedAt": "2026-11-13T16:45:30.123+07:00"
}
```

`XXX` biểu diễn offset theo dạng như `+07:00`. Nhờ có offset, Elasticsearch có thể xác định một thời điểm tuyệt đối. Với ứng dụng Java, `OffsetDateTime` thể hiện rõ rằng giá trị có offset.

Nếu hệ thống chuẩn hóa tất cả timestamp sang UTC, có thể dùng chuỗi kết thúc bằng `Z` và kiểu `Instant`. Cần bảo đảm pattern và converter thực tế thống nhất với dạng chuỗi mà ứng dụng gửi.

## 5. Timezone và UTC

Timezone là một trong những nguyên nhân phổ biến gây sai lệch thời gian khi tích hợp ứng dụng với Elasticsearch.

Một timestamp như `2026-11-13T16:45:30+07:00` và `2026-11-13T09:45:30Z` biểu diễn cùng một thời điểm. Offset `+07:00` cho biết giờ địa phương nhanh hơn UTC bảy tiếng. Khi Elasticsearch parse được offset, nó chuẩn hóa về một thời điểm tương ứng.

Ngược lại, chuỗi `2026-11-13 16:45:30` không có offset. Nó chỉ là ngày giờ theo một quy ước ngầm. Nếu ứng dụng, Elasticsearch và hệ thống nguồn hiểu timezone khác nhau, cùng chuỗi có thể bị diễn giải thành những thời điểm khác nhau.

### 5.1. Quy ước lưu timestamp tuyệt đối

Với thời điểm tạo event, thời điểm thanh toán hoặc thời điểm đồng bộ, nên thống nhất lưu timestamp tuyệt đối theo UTC:

```java
Instant now = Instant.now();
```

Khi serialize theo ISO-8601, giá trị có thể có dạng:

```text
2026-11-13T09:45:30Z
```

Khi hiển thị cho người dùng, chuyển sang timezone phù hợp:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

String localText = DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
        now.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
             .toOffsetDateTime());
```

Lưu UTC giúp việc so sánh, sort và truy vấn khoảng thời gian nhất quán. Việc hiển thị giờ địa phương là trách nhiệm của lớp trình bày hoặc API theo hợp đồng đã thống nhất.

### 5.2. Khi nào dùng `LocalDateTime`?

`LocalDateTime` phù hợp khi giá trị mang ý nghĩa giờ trên đồng hồ địa phương, ví dụ “cửa hàng mở cửa lúc 09:00” hoặc “cuộc hẹn bắt đầu lúc 14:30” trong một timezone đã biết từ địa điểm.

Nếu cần chuyển `LocalDateTime` thành một thời điểm tuyệt đối, phải cung cấp `ZoneId`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDateTime localTime = LocalDateTime.of(2026, 11, 13, 16, 45);
Instant instant = localTime
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
```

Không nên dùng `ZoneId.systemDefault()` một cách ngầm định trong logic nghiệp vụ chạy trên nhiều máy chủ. Múi giờ hệ điều hành có thể khác giữa máy developer, container và production. Hãy dùng timezone được xác định bởi nghiệp vụ hoặc lưu timezone ID riêng khi cần tái hiện lịch địa phương.

### 5.3. Offset và timezone ID không giống nhau

`OffsetDateTime` giữ offset tại một thời điểm, ví dụ `+07:00`. `ZonedDateTime` giữ timezone ID như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`, bao gồm quy tắc lịch sử và daylight saving time của vùng đó.

Một offset không đủ để tái hiện quy tắc timezone trong tương lai. Nếu ứng dụng quản lý lịch họp hoặc lịch mở cửa, có thể cần lưu cả ngày giờ địa phương và timezone ID. Nếu chỉ cần biết một event đã xảy ra lúc nào, `Instant` thường đơn giản và chắc chắn hơn.

## 6. Kiểu ngày lịch và kiểu thời điểm

Không phải mọi dữ liệu “ngày” đều là timestamp.

Ví dụ ngày sinh:

```java
import java.time.LocalDate;

@Field(type = FieldType.Date, format = DateFormat.date)
private LocalDate birthDate;
```

Giá trị như `1995-08-21` là ngày lịch, không cần giờ hoặc timezone. Nếu chuyển nó thành `Instant` ở nửa đêm UTC, khi hiển thị tại timezone khác có thể rơi vào ngày trước đó. Vì vậy, hãy giữ `LocalDate` khi nghiệp vụ chỉ quan tâm ngày.

Ví dụ timestamp sự kiện:

```java
import java.time.Instant;

@Field(type = FieldType.Date)
private Instant eventTime;
```

Giá trị này xác định một thời điểm tuyệt đối. Khi gửi qua API, nên dùng ISO-8601 với `Z` hoặc offset.

`LocalTime` cũng không phải một timestamp hoàn chỉnh. Nếu cần lưu giờ mở cửa, có thể lưu dạng `keyword` hoặc date/time representation phù hợp với hợp đồng dữ liệu, nhưng không nên coi nó là thời điểm trên timeline khi chưa có ngày và timezone.

## 7. Dùng `date_nanos` khi cần độ chính xác nano giây

Nếu nghiệp vụ cần phân biệt sự kiện có thời gian cách nhau dưới một mili giây, có thể dùng Elasticsearch `date_nanos`.

Ví dụ mapping bằng Elasticsearch DSL:

```http
PUT telemetry
{
  "mappings": {
    "properties": {
      "capturedAt": {
        "type": "date_nanos"
      }
    }
  }
}
```

Trong Spring Data Elasticsearch, phiên bản thư viện hỗ trợ `FieldType.Date_Nanos` có thể khai báo:

```java
import java.time.Instant;

@Field(type = FieldType.Date_Nanos)
private Instant capturedAt;
```

Hãy xác nhận `FieldType.Date_Nanos` có trong phiên bản Spring Data Elasticsearch mà dự án sử dụng. Nếu phiên bản không hỗ trợ annotation này, có thể phải quản lý mapping bằng index settings/template hoặc nâng cấp dependency train tương thích.

Ví dụ giá trị có phần nano giây:

```json
{
  "capturedAt": "2026-11-13T09:45:30.123456789Z"
}
```

Chỉ chọn `date_nanos` khi dữ liệu nguồn và các kiểu chuyển đổi giữ được độ chính xác cần thiết. `Instant` có thể biểu diễn nano giây, nhưng một converter hoặc kiểu `Date` truyền thống có thể chỉ giữ mili giây.

## 8. Tạo mapping ngày giờ bằng Spring Data Elasticsearch

Spring Data có thể tạo mapping dựa trên metadata của entity. Ví dụ đầy đủ:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Date)
    private Instant occurredAt;

    @Field(type = FieldType.Date, format = DateFormat.date)
    private LocalDate eventDate;

    @Field(
        type = FieldType.Date,
        format = DateFormat.custom,
        pattern = "yyyy-MM-dd HH:mm:ss"
    )
    private LocalDateTime importedAt;

    @Field(
        type = FieldType.Date,
        format = DateFormat.custom,
        pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"
    )
    private OffsetDateTime sourceTimestamp;

    // Constructors, getters and setters
}
```

Entity minh họa bốn ý nghĩa:

- `occurredAt`: thời điểm tuyệt đối.
- `eventDate`: ngày lịch.
- `importedAt`: chuỗi ngày giờ legacy không có timezone; timezone của nó phải được thống nhất ở tầng nghiệp vụ.
- `sourceTimestamp`: ngày giờ có offset được thể hiện ngay trong chuỗi.

Khi dùng annotation để tạo index, hãy bảo đảm format và pattern tương thích với dữ liệu converter gửi. Nếu index đã tồn tại, thay đổi annotation không tự động sửa mapping hiện tại.

### 8.1. Khai báo settings và mapping riêng

Nếu cần custom analyzer, mapping phức tạp hoặc quản lý index theo version, có thể tạo index bằng settings/mapping riêng rồi dùng entity để ánh xạ document. Ví dụ mapping date bằng DSL:

```http
PUT events-v1
{
  "mappings": {
    "properties": {
      "occurredAt": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      },
      "importedAt": {
        "type": "date",
        "format": "yyyy-MM-dd HH:mm:ss||epoch_millis"
      }
    }
  }
}
```

Spring Data entity cần mô tả tương thích với mapping này. Nếu mapping được quản lý bằng file hoặc index template, hãy tránh để auto-create index tạo một mapping khác với mapping đã được chuẩn bị.

## 9. Truy vấn ngày giờ

Sau khi field đã được mapping thành `date`, có thể dùng range query để lọc khoảng thời gian.

Ví dụ tìm event trong một ngày theo UTC:

```http
GET events/_search
{
  "query": {
    "range": {
      "occurredAt": {
        "gte": "2026-11-13T00:00:00Z",
        "lt": "2026-11-14T00:00:00Z"
      }
    }
  }
}
```

Dùng `gte` và `lt` thường giúp tạo khoảng nửa mở `[start, end)`, tránh việc phải đoán mili giây cuối cùng của ngày. Nếu nghiệp vụ xác định ngày theo timezone địa phương, hãy chuyển thời điểm đầu ngày và đầu ngày kế tiếp của timezone đó sang UTC trước khi gửi query.

Elasticsearch cũng hỗ trợ date math:

```http
GET events/_search
{
  "query": {
    "range": {
      "occurredAt": {
        "gte": "now-24h",
        "lte": "now"
      }
    }
  }
}
```

`now` được Elasticsearch đánh giá tại thời điểm thực thi query. Có thể dùng timezone trong range query khi làm việc với các biểu thức ngày lịch và định nghĩa khoảng thời gian theo múi giờ, nhưng cần xác định rõ ý nghĩa của `now`, `time_zone`, `gte`, `lt` và định dạng đầu vào.

### 9.1. Truy vấn ngày lịch theo timezone địa phương

Giả sử cần lấy các sự kiện trong ngày 13/11/2026 theo giờ Việt Nam. Không nên giả định ngày đó bắt đầu lúc `00:00Z`. Hãy tạo khoảng thời gian địa phương rồi chuyển sang UTC:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

LocalDate date = LocalDate.of(2026, 11, 13);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
```

Sau đó dùng `from` làm `gte` và `until` làm `lt`. Cách này cũng xử lý đúng ngày có thay đổi daylight saving time ở các timezone có quy tắc đó, vì độ dài một ngày địa phương không phải lúc nào cũng đúng 24 giờ.

## 10. Phân biệt Elasticsearch date format với định dạng JSON của Jackson

Một ứng dụng Spring Boot thường có ít nhất hai lớp chuyển đổi ngày giờ:

1. **Spring Data Elasticsearch mapping converter** chuyển entity Java thành document gửi tới Elasticsearch và ngược lại.
2. **Jackson HTTP message converter** chuyển object Java thành JSON của REST API và ngược lại.

`@Field(format = ..., pattern = ...)` điều khiển mapping ngày giờ của Elasticsearch. Nó không tự quyết định chuỗi JSON mà Spring MVC trả về client.

Ngược lại, `@JsonFormat` điều khiển cách Jackson serialize/deserialize JSON. Nó không tự thay đổi mapping field trong Elasticsearch.

Ví dụ:

```java
import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(type = FieldType.Date)
@JsonFormat(shape = JsonFormat.Shape.STRING)
private Instant createdAt;
```

Ở đây `@Field` mô tả kiểu field trong Elasticsearch; `@JsonFormat` mô tả biểu diễn JSON qua Jackson. Nếu cần một pattern cụ thể cho API, có thể khai báo pattern và timezone trên `@JsonFormat` theo hợp đồng API. Không dùng `@JsonFormat` để thay cho `@Field(pattern = ...)` khi mục tiêu là cấu hình Elasticsearch mapping.

Tách biệt hai lớp giúp tránh lỗi kiểu “REST trả ISO-8601 nhưng Elasticsearch từ chối chuỗi” hoặc “Elasticsearch lưu đúng nhưng API hiển thị sai múi giờ”. Khi debug, kiểm tra riêng JSON HTTP request, object Java sau Jackson, document được Spring Data tạo và `_source` thực tế trong Elasticsearch.

## 11. Custom converter khi kiểu Java hoặc quy tắc nghiệp vụ đặc biệt

Các kiểu Java phổ biến thường đã có converter trong Spring Data Elasticsearch. Nếu ứng dụng dùng một kiểu riêng hoặc cần chuyển đổi theo quy tắc không thể biểu diễn bằng mapping date thông thường, có thể đăng ký custom converter.

Ví dụ, hệ thống legacy biểu diễn thời gian bằng một class riêng:

```java
public record LegacyTimestamp(long epochMillis) {
}
```

Có thể định nghĩa converter đọc và ghi giữa kiểu đó với một kiểu thời gian mà Spring Data hỗ trợ. Ví dụ minh họa chiều chuyển đổi:

```java
import java.time.Instant;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class LegacyTimestampWriteConverter
        implements Converter<LegacyTimestamp, Instant> {

    @Override
    public Instant convert(LegacyTimestamp source) {
        return Instant.ofEpochMilli(source.epochMillis());
    }
}
```

Converter đọc có thể chuyển `Instant` trở lại `LegacyTimestamp`:

```java
import java.time.Instant;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class LegacyTimestampReadConverter
        implements Converter<Instant, LegacyTimestamp> {

    @Override
    public LegacyTimestamp convert(Instant source) {
        return new LegacyTimestamp(source.toEpochMilli());
    }
}
```

Đây là ví dụ về ý tưởng chuyển đổi. Kiểu trung gian và cách Spring Data chọn converter phụ thuộc mapping context, loại dữ liệu trong document và các converter đã đăng ký. Với date field, hãy bảo đảm converter tạo ra giá trị mà Elasticsearch date mapping có thể nhận. Nếu chuyển thành chuỗi, chuỗi đó phải khớp format của field; nếu chuyển thành epoch number, phải thống nhất đơn vị milliseconds hay seconds.

Các converter cần được đăng ký trong `ElasticsearchCustomConversions` và đưa vào cấu hình Spring Data Elasticsearch phù hợp với phiên bản đang dùng. Ví dụ cấu hình ở mức khái niệm:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConversionConfig {

    @Bean
    ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(List.of(
                new LegacyTimestampWriteConverter(),
                new LegacyTimestampReadConverter()
        ));
    }
}
```

Tên package, constructor và cơ chế đăng ký custom conversions có thể thay đổi theo release train. Hãy đối chiếu API của phiên bản Spring Data Elasticsearch đang dùng. Không đăng ký converter rộng cho `String` hoặc `Long` nếu nó có thể làm thay đổi cách chuyển đổi các field khác trong toàn ứng dụng.

## 12. Những lỗi thường gặp khi ánh xạ ngày giờ

### Chuỗi ngày giờ không khớp mapping format

Nếu mapping chấp nhận `yyyy-MM-dd HH:mm:ss` nhưng ứng dụng gửi `2026-11-13T16:45:30Z`, Elasticsearch có thể từ chối document vì chuỗi không khớp format. Kiểm tra mapping và chuỗi thực tế được gửi; điều chỉnh pattern hoặc chuẩn hóa đầu vào theo một quy ước thống nhất.

### Dùng `LocalDateTime` nhưng không xác định timezone

`LocalDateTime` không có offset. Nếu hệ thống coi nó là UTC nhưng ứng dụng hiểu là giờ Việt Nam, thời điểm có thể lệch bảy tiếng. Dùng `Instant`/`OffsetDateTime` cho thời điểm tuyệt đối hoặc xác định `ZoneId` rõ ràng khi chuyển đổi.

### Dùng epoch seconds thay cho epoch milliseconds

Elasticsearch date mặc định hiểu số nguyên là epoch milliseconds. Nếu nguồn gửi epoch seconds mà mapping không khai báo format tương ứng hoặc converter không nhân đúng hệ số, thời điểm có thể rơi vào năm 1970 hoặc một ngày không mong đợi. Xác định rõ đơn vị ở API và converter.

### Mất độ chính xác nano giây

Field `date` chỉ có độ chính xác mili giây. Nếu cần phần nano giây, dùng `date_nanos` và kiểm tra toàn bộ đường chuyển đổi có giữ được độ chính xác.

### Thay annotation nhưng mapping cũ không đổi

Mapping của index hiện hữu không tự cập nhật mọi thay đổi trong entity. Kiểm tra `_mapping`; nếu cần thay kiểu date hoặc format không tương thích, tạo index mới và reindex dữ liệu theo quy trình migration.

### Nhầm `@JsonFormat` với `@Field(pattern = ...)`

`@JsonFormat` tác động tới JSON của Jackson; `@Field` tác động tới Elasticsearch mapping/conversion. Khi API và Elasticsearch có format khác nhau, hãy cấu hình cả hai lớp một cách nhất quán.

### Lưu ngày lịch thành timestamp UTC

Ngày sinh hoặc ngày hóa đơn không nhất thiết là một thời điểm. Nếu chuyển `LocalDate` thành nửa đêm UTC rồi hiển thị ở timezone khác, ngày có thể bị lùi hoặc tiến. Giữ `LocalDate` khi nghiệp vụ chỉ quan tâm ngày lịch.

## 13. Kiểm tra mapping và document thực tế

Khi ứng dụng đã tạo index, hãy kiểm tra mapping:

```http
GET events/_mapping
```

Kiểm tra document trong `_source`:

```http
GET events/_doc/event-100
```

Thử truy vấn khoảng ngày:

```http
GET events/_search
{
  "query": {
    "range": {
      "occurredAt": {
        "gte": "2026-11-13T00:00:00Z",
        "lt": "2026-11-14T00:00:00Z"
      }
    }
  }
}
```

Nếu mapping cho phép nhiều format, thử từng định dạng đầu vào trong môi trường kiểm thử để xác nhận Elasticsearch parse đúng. Đồng thời kiểm tra document do Spring Data thực sự ghi, không chỉ kiểm tra giá trị trong object Java trước khi gọi `save`.

Khi cần xem giá trị date dưới dạng field được format bởi Elasticsearch, có thể dùng `fields` hoặc `docvalue_fields` trong Search API với format mong muốn, tùy loại field và yêu cầu truy vấn. Kết quả `fields` được format không đồng nghĩa `_source` đã bị thay đổi; hai phần này phục vụ mục đích khác nhau.

## 14. Quy trình thiết kế và triển khai

Khi thêm field thời gian vào entity Spring Data Elasticsearch, hãy đi theo quy trình:

1. Xác định dữ liệu là ngày lịch, giờ địa phương hay thời điểm tuyệt đối.
2. Chọn kiểu Java phản ánh đúng ý nghĩa: `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` hoặc kiểu khác.
3. Chọn Elasticsearch field type: `date` cho độ chính xác mili giây thông thường hoặc `date_nanos` khi thực sự cần nano giây.
4. Thống nhất timezone và đơn vị epoch giữa nguồn dữ liệu, ứng dụng và Elasticsearch.
5. Dùng format mặc định ISO-8601 nếu có thể; chỉ khai báo `DateFormat.custom` và `pattern` khi phải tương thích định dạng riêng.
6. Kiểm tra mapping được tạo bằng `GET index/_mapping`.
7. Kiểm tra JSON và document thực tế, sau đó thử range query với các mốc thời gian đại diện.
8. Cấu hình `@JsonFormat` riêng nếu REST API có hợp đồng định dạng khác với Elasticsearch.
9. Dùng custom converter khi kiểu dữ liệu hoặc quy tắc chuyển đổi vượt quá khả năng mapping mặc định.
10. Khi thay đổi mapping không tương thích, tạo index mới và reindex thay vì kỳ vọng annotation sửa index cũ.

Ánh xạ ngày giờ chính xác đòi hỏi thống nhất ý nghĩa thời gian trước khi chọn format. `@Field` và mapping Elasticsearch xác định cách lưu, parse và truy vấn field; Java Time API thể hiện ý nghĩa ngày giờ trong ứng dụng; Jackson định dạng JSON của API. Giữ rõ ranh giới giữa ba lớp này giúp tránh lỗi lệch timezone, mất độ chính xác và sai định dạng khi Spring Data Elasticsearch chuyển đổi object.
