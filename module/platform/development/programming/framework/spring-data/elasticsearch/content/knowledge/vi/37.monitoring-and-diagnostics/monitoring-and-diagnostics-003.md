# Lỗi chuyển đổi kiểu, ngày tháng và tên trường

Trong Spring Data Elasticsearch, entity Java được chuyển thành document JSON theo mapping metadata và converter của Spring Data. Elasticsearch lại lưu và truy vấn dữ liệu theo mapping của index. Nếu hai phía mô tả khác nhau, lỗi có thể xuất hiện khi ghi document, đọc response, lọc theo field hoặc chuyển đổi ngày tháng.

Ba nhóm lỗi thường gặp:

- **Type conversion:** giá trị Java không chuyển được sang kiểu field trong Elasticsearch hoặc ngược lại.
- **Date/time conversion:** chuỗi ngày không khớp format, timezone không rõ, timestamp sai đơn vị hoặc mất precision.
- **Field naming:** tên property Java, tên trong JSON _source, tên field trong mapping và tên field của Query DSL không đồng nhất.

Cách xử lý đúng là kiểm tra cả entity mapping, converter, mapping thực tế của index và dữ liệu đã được index. Sửa một annotation Java không tự thay đổi mapping type của index đã tồn tại.

## 1. Luồng chuyển đổi dữ liệu trong Spring Data Elasticsearch

Khi ứng dụng lưu một entity qua ElasticsearchOperations hoặc repository, Spring Data dùng MappingElasticsearchConverter cùng mapping metadata để chuyển entity thành document. Khi đọc, converter thực hiện chiều ngược lại.

~~~text
Java entity
    |
    v
Mapping metadata
(@Document, @Id, @Field, custom conversions)
    |
    v
MappingElasticsearchConverter
    |
    v
JSON document
    |
    v
Elasticsearch mapping
    |
    v
Inverted index / doc values / _source
~~~

Khi đọc:

~~~text
Elasticsearch response
    |
    v
JSON _source + metadata
    |
    v
MappingElasticsearchConverter
    |
    v
Java entity
~~~

Cần phân biệt ba lớp:

1. **Java type:** kiểu property trong entity, ví dụ String, Long, BigDecimal, Instant hoặc LocalDate.
2. **Elasticsearch field type:** kiểu trong mapping, ví dụ keyword, text, long, scaled_float, date hoặc date_nanos.
3. **JSON representation:** giá trị thực tế trong _source, ví dụ chuỗi ISO-8601, số epoch millis hoặc object lồng nhau.

Một giá trị có thể là chuỗi trong _source nhưng được Elasticsearch parse và index như date. Ngược lại, một property Java kiểu Instant không bảo đảm index hiện tại đã có mapping date tương ứng.

Repository không tự sửa mapping đã tồn tại chỉ vì entity đổi kiểu. Mapping Elasticsearch là hợp đồng lưu trữ độc lập và cần được kiểm soát.

## 2. Những dấu hiệu cho thấy lỗi conversion hoặc mapping

Các lỗi thường xuất hiện ở nhiều thời điểm:

| Thời điểm | Dấu hiệu | Nhóm nguyên nhân thường gặp |
| --- | --- | --- |
| Lưu document | mapper_parsing_exception, document_parsing_exception | Giá trị JSON không hợp lệ với mapping field. |
| Lưu document | failed to parse field [created_at] | Date format, timezone hoặc kiểu dữ liệu sai. |
| Đọc document | ConversionException hoặc lỗi converter | JSON value không chuyển được sang property Java. |
| Search | Field không tìm thấy, query trả rỗng | Dùng sai field name, field path hoặc mapping. |
| Search qua alias | field_caps báo nhiều type | Các index phía sau alias có mapping không đồng nhất. |
| Sort/aggregation | Fielddata hoặc incompatible field type | Dùng text thay vì keyword/numeric/date phù hợp. |
| Startup/index creation | Mapping conflict hoặc index đã tồn tại | Entity mapping khác mapping hiện hành. |

Không nên kết luận chỉ từ message ngoài cùng. Hãy đọc root cause, tên index, tên field, giá trị đầu vào và mapping thực tế. Một lỗi ở tầng converter có thể xuất phát từ source cũ, mapping động hoặc một custom converter.

## 3. Kiểm tra mapping thực tế trước khi sửa code

Bước đầu tiên khi có lỗi là kiểm tra Elasticsearch đang hiểu field như thế nào.

Lấy mapping của index:

~~~http
GET /products/_mapping
~~~

Lấy mapping của một field cụ thể:

~~~http
GET /products/_mapping/field/created_at
~~~

Lấy dữ liệu document:

~~~http
GET /products/_doc/P-100
~~~

Nếu chỉ cần kiểm tra _source:

~~~http
GET /products/_doc/P-100?_source_includes=name,price,created_at
~~~

Các câu hỏi cần trả lời:

- Field có tồn tại trong mapping không?
- Type hiện tại là keyword, text, long, double, date hay type khác?
- Có format date nào được khai báo?
- Field có nằm dưới object hoặc nested path không?
- Document có giá trị null, chuỗi rỗng hoặc kiểu không đồng nhất không?
- Index được truy vấn là index nào khi request đi qua alias?

Không lấy entity class làm bằng chứng duy nhất về mapping. Index có thể được tạo từ template, migration hoặc một phiên bản ứng dụng cũ.

### 3.1. So sánh field capabilities giữa nhiều index

Nếu search qua alias hoặc wildcard, các index có thể định nghĩa cùng tên field với type khác nhau.

Dùng Field Capabilities API:

~~~http
GET /products-*/_field_caps?fields=price,created_at,tenantId
~~~

Response cho biết field có type nào trong các index được chọn và index nào có mapping tương ứng. Ví dụ một nhóm index có price là long, nhóm khác lại là keyword. Search, sort hoặc aggregation trên alias có thể gặp lỗi vì type conflict.

Nếu thấy mapping không đồng nhất, cần xử lý index cũ bằng migration/reindex hoặc tách alias theo schema version. Đổi entity Java không hợp nhất được mapping của các index hiện hữu.

## 4. Type conversion giữa Java và Elasticsearch

Spring Data Elasticsearch hỗ trợ chuyển đổi các kiểu Java phổ biến sang kiểu JSON và mapping tương ứng. Tuy nhiên, kiểu property nên phản ánh đúng ý nghĩa dữ liệu và Elasticsearch field type.

| Java property | Elasticsearch type thường dùng | Ghi chú |
| --- | --- | --- |
| String dùng exact match | keyword | Dùng term, sort và aggregation. |
| String dùng full-text search | text | Có analyzer; không dùng trực tiếp cho aggregation thông thường. |
| Integer | integer | Phạm vi số nguyên 32-bit. |
| Long | long | Phạm vi số nguyên 64-bit. |
| Double | double | Số thực dấu phẩy động. |
| BigDecimal cho tiền | scaled_float hoặc long | Chọn theo độ chính xác và cách biểu diễn. |
| Boolean | boolean | Tránh gửi chuỗi "true"/"false" không nhất quán. |
| Instant / Date | date | Thống nhất format và timezone. |
| Instant cần precision cao | date_nanos | Có giới hạn precision/range và chi phí khác date. |
| Enum | keyword | Quy định rõ lưu enum name hay code nghiệp vụ. |

Không chọn field type chỉ vì nó dễ serialize. Hãy chọn theo cách field được tìm kiếm, sắp xếp, aggregation và yêu cầu độ chính xác.

### 4.1. Phân biệt text và keyword

Một lỗi phổ biến là khai báo property tên hoặc trạng thái thành text nhưng lại dùng term query hoặc aggregation như field keyword.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Entity Spring Data:

~~~java
@Field(type = FieldType.Text)
private String name;

@Field(type = FieldType.Keyword)
private String status;
~~~

Khi cần exact match, sort hoặc aggregation trên name, dùng multi-field name.keyword nếu mapping có khai báo. Không đổi query sang name.keyword nếu mapping thực tế chưa có subfield đó.

### 4.2. String không đồng nghĩa mọi field đều là keyword

Một property Java kiểu String có thể ánh xạ thành text hoặc keyword. Cần khai báo rõ:

~~~java
@Field(type = FieldType.Keyword)
private String sku;

@Field(type = FieldType.Text)
private String description;
~~~

Nếu để dynamic mapping quyết định, Elasticsearch thường suy luận type theo giá trị đầu tiên. Một chuỗi có thể được map thành text kèm keyword subfield theo dynamic template mặc định, nhưng không nên phụ thuộc vào hành vi mặc định cho schema quan trọng.

### 4.3. Số nguyên và số thực

Một số lỗi thường gặp:

- Java Long nhưng index field được map thành integer.
- Giá trị có phần thập phân được gửi vào field integer.
- Chuỗi chứa dấu phân cách hàng nghìn hoặc dấu phẩy thập phân không phải định dạng JSON number hợp lệ.
- Một số document gửi null, một số gửi chuỗi, số khác gửi number.
- Dùng Double cho số tiền và gặp sai số biểu diễn nhị phân.

Ví dụ JSON number hợp lệ:

~~~json
{
  "quantity": 12,
  "price": 19.95
}
~~~

Không gửi giá trị số dưới dạng chuỗi nếu mapping và contract của ứng dụng yêu cầu numeric:

~~~json
{
  "quantity": "12",
  "price": "19,95"
}
~~~

Elasticsearch có thể hỗ trợ coercion trong một số tình huống, nhưng không nên dựa vào coercion để che dữ liệu không nhất quán. Định dạng số theo locale như 19,95 cần được parse ở tầng ứng dụng thành kiểu số trước khi gửi.

### 4.4. Tiền tệ và BigDecimal

Double có thể biểu diễn một số thập phân gần đúng. Với tiền, cân nhắc:

- Dùng long lưu đơn vị nhỏ nhất, ví dụ số cent.
- Dùng scaled_float với scaling_factor đã xác định.
- Giữ BigDecimal ở domain layer và chuyển sang biểu diễn index đã thống nhất.

Ví dụ scaled_float:

~~~json
{
  "properties": {
    "price": {
      "type": "scaled_float",
      "scaling_factor": 100
    }
  }
}
~~~

Entity:

~~~java
@Field(type = FieldType.Scaled_Float, scalingFactor = 100)
private BigDecimal price;
~~~

Tên enum và thuộc tính annotation cần khớp phiên bản Spring Data đang dùng. Nếu ứng dụng cần độ chính xác tài chính tuyệt đối, hãy xác định rõ quy tắc làm tròn và đơn vị lưu trữ; scaled_float có semantics lượng tử hóa theo scaling factor.

### 4.5. Enum và giá trị lưu trữ

Nếu lưu enum bằng tên:

~~~java
public enum OrderStatus {
    PENDING,
    PROCESSING,
    COMPLETED
}
~~~

Giá trị _source thường là chuỗi như PENDING, mapping thường là keyword. Cách này dễ đọc nhưng đổi tên enum có thể làm dữ liệu cũ không chuyển đổi được.

Nếu enum có code nghiệp vụ ổn định, có thể dùng custom converter để lưu code như P, R, C. Cần bảo đảm converter đọc được cả dữ liệu cũ trong giai đoạn migration.

Không thay đổi enum name hoặc code mà không có chiến lược tương thích ngược.

## 5. Dynamic mapping và lỗi do document đầu tiên

Nếu index chưa có mapping tường minh cho field, dynamic mapping có thể suy luận type từ document đầu tiên chứa field đó.

Ví dụ document đầu tiên:

~~~json
{
  "price": "19.95"
}
~~~

Nếu field được suy luận là text/keyword, một document sau gửi số:

~~~json
{
  "price": 19.95
}
~~~

có thể gây xung đột hoặc bị xử lý không như mong đợi.

Một trường hợp tương tự xảy ra khi field date đầu tiên chứa chuỗi không giống ngày tháng. Elasticsearch có thể map field thành text thay vì date. Khi document hợp lệ theo ngày được gửi sau đó, ứng dụng có thể gặp mapping conflict.

Cách phòng tránh:

- Tạo index với mapping tường minh trước khi ingest.
- Dùng index template cho index được tạo theo pattern.
- Dùng dynamic templates có quy tắc rõ ràng.
- Không để document đầu tiên của một field quyết định schema production.
- Kiểm tra mapping sau khi tạo index.
- Dùng strict dynamic mapping nếu nghiệp vụ cần phát hiện field ngoài schema.

Ví dụ dynamic mapping strict:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "created_at": {
        "type": "date"
      }
    }
  }
}
~~~

Với strict mapping, field không được khai báo sẽ bị từ chối. Điều này giúp phát hiện typo sớm nhưng yêu cầu schema và quy trình deploy phải đầy đủ.

## 6. Lỗi ngày tháng: format và kiểu Java

Ngày tháng là nhóm lỗi conversion phổ biến vì có nhiều cách biểu diễn cùng một thời điểm:

- ISO-8601 có timezone, ví dụ 2026-11-13T08:30:00Z.
- Chuỗi không có timezone, ví dụ 2026-11-13 15:30:00.
- Epoch milliseconds, ví dụ 1794558600000.
- Epoch seconds, ví dụ 1794558600.
- Ngày lịch không có thời gian, ví dụ 2026-11-13.

Elasticsearch date field lưu thời điểm dưới dạng số và hỗ trợ parse các format được khai báo. Elasticsearch không giữ lại timezone gốc của chuỗi như một thuộc tính độc lập. Nếu nghiệp vụ cần biết múi giờ ban đầu, lưu zone ID riêng.

### 6.1. Chọn kiểu Java theo ý nghĩa thời gian

| Java type | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| Instant | Một thời điểm trên timeline UTC. | Event time, createdAt, updatedAt. |
| OffsetDateTime | Thời điểm cùng offset UTC cụ thể. | API nhận timestamp có offset. |
| ZonedDateTime | Thời điểm cùng vùng timezone. | Nghiệp vụ cần zone rules, ví dụ Europe/Paris. |
| LocalDate | Ngày lịch, không có giờ. | Ngày sinh, ngày hiệu lực, ngày nghỉ. |
| LocalDateTime | Ngày và giờ địa phương, không có zone. | Chỉ dùng khi domain thực sự lưu giờ địa phương và có quy tắc zone bên ngoài. |
| java.util.Date | Thời điểm với precision milliseconds. | Code legacy hoặc API cũ. |

Với timestamp sự kiện, Instant thường là lựa chọn rõ ràng vì không mang ý nghĩa timezone ngầm. Với ngày lịch, LocalDate phù hợp hơn; không tự chuyển nó thành một thời điểm UTC nếu domain không yêu cầu.

LocalDateTime không cho biết đó là 09:00 ở Ho Chi Minh City, London hay Tokyo. Trước khi lưu thành Elasticsearch date, ứng dụng cần xác định zone và chuyển thành Instant hoặc dùng một contract ngày giờ rõ ràng.

### 6.2. Mapping date tường minh

Ví dụ entity lưu thời điểm tạo dưới dạng Instant:

~~~java
import java.time.Instant;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(
    name = "created_at",
    type = FieldType.Date,
    format = DateFormat.date_optional_time
)
private Instant createdAt;
~~~

Mapping Elasticsearch tương ứng có thể khai báo:

~~~json
{
  "properties": {
    "created_at": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Format cụ thể được sinh ra phụ thuộc annotation và phiên bản Spring Data. Hãy kiểm tra mapping thật sau khi tạo index. Đừng giả định annotation và mapping được tạo thủ công đã giống nhau.

### 6.3. Custom date pattern

Nếu hệ thống nguồn gửi chuỗi theo format riêng, có thể khai báo custom pattern:

~~~java
@Field(
    name = "created_at",
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "uuuu-MM-dd HH:mm:ss"
)
private String legacyCreatedAt;
~~~

Ví dụ này giữ chuỗi legacy nguyên dạng để minh họa cách Elasticsearch parse một format riêng. Trong domain model mới, nên chuẩn hóa chuỗi thành Instant sau khi xác định timezone, thay vì để String đại diện cho thời điểm. Mapping tương ứng cần hỗ trợ chính xác format mà dữ liệu gửi lên sử dụng. Nếu cần chấp nhận nhiều format, Elasticsearch date format có thể kết hợp nhiều format bằng dấu phân cách hai pipe, nhưng phải kiểm tra cú pháp và pattern của từng format.

Ví dụ mapping:

~~~json
{
  "properties": {
    "created_at": {
      "type": "date",
      "format": "uuuu-MM-dd HH:mm:ss||strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Không thêm hàng loạt format để che dữ liệu không nhất quán. Tốt hơn là chuẩn hóa input ở tầng API/ingestion và chỉ hỗ trợ các format thực sự cần.

### 6.4. Epoch seconds và epoch milliseconds

Một lỗi rất phổ biến là nhầm epoch seconds với epoch milliseconds.

Ví dụ:

- Epoch seconds: 1794558600
- Epoch milliseconds: 1794558600000

Hai giá trị chênh nhau 1.000 lần. Nếu field format mong epoch milliseconds nhưng ứng dụng gửi seconds, ngày có thể rơi vào năm 1970 hoặc thời điểm hoàn toàn sai.

Chuyển đổi Java:

~~~java
Instant fromSeconds = Instant.ofEpochSecond(epochSeconds);
Instant fromMillis = Instant.ofEpochMilli(epochMillis);
~~~

Không nhân/chia 1.000 một cách tùy tiện ở nhiều tầng. Chọn một đơn vị contract và ghi rõ trong DTO/API.

### 6.5. Timezone và UTC

Ví dụ một timestamp có offset:

~~~text
2026-11-13T15:30:00+07:00
~~~

Đây là cùng thời điểm với:

~~~text
2026-11-13T08:30:00Z
~~~

Elasticsearch chuẩn hóa thời điểm khi index date. Nếu ứng dụng cần hiển thị giờ địa phương, hãy chuyển Instant sang ZoneId ở tầng trình bày.

Ví dụ:

~~~java
Instant eventTime = Instant.parse("2026-11-13T08:30:00Z");

ZonedDateTime localTime = eventTime.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Không lưu LocalDateTime không timezone rồi mặc định mọi consumer đều hiểu cùng một zone. Nếu dữ liệu được tạo ở nhiều khu vực, cần một quy ước rõ ràng và test cả thời điểm có daylight-saving transition.

### 6.6. Ngày lịch không phải timestamp

Một ngày sinh 1995-06-12 không nhất thiết là một thời điểm lúc nửa đêm UTC. Nếu domain là ngày lịch, dùng LocalDate và mapping format chỉ chứa ngày:

~~~java
@Field(
    name = "birth_date",
    type = FieldType.Date,
    format = DateFormat.year_month_day
)
private LocalDate birthDate;
~~~

Mapping có thể dùng format strict_date hoặc pattern ngày phù hợp. Xác nhận mapping được sinh ra và test round-trip trên đúng version.

Nếu chuyển ngày lịch sang Instant, phải quyết định zone dùng để diễn giải ngày đó. Nếu không, người dùng ở timezone khác có thể nhìn thấy ngày lệch một ngày khi chuyển đổi.

### 6.7. Precision: date và date_nanos

Elasticsearch date lưu precision tới milliseconds. Nếu ứng dụng cần giữ độ chính xác nanoseconds, có thể cân nhắc date_nanos.

Ví dụ:

~~~java
@Field(
    name = "event_time",
    type = FieldType.Date_Nanos,
    format = DateFormat.date_optional_time
)
private Instant eventTime;
~~~

date_nanos có giới hạn range và đặc điểm lưu trữ khác date. Chỉ dùng khi độ chính xác đó có giá trị nghiệp vụ và đã kiểm tra hỗ trợ của Spring Data/client/version. Không mặc định rằng Java Instant giữ nanoseconds thì Elasticsearch date cũng giữ nguyên precision đó.

## 7. Lỗi tên trường giữa Java, JSON và Elasticsearch

Một property Java có thể mang tên khác trong mapping:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Tên trong Query DSL phải là created_at, không phải createdAt.

Ví dụ query đúng:

~~~json
{
  "query": {
    "range": {
      "created_at": {
        "gte": "2026-11-01T00:00:00Z"
      }
    }
  }
}
~~~

Nếu query dùng createdAt, Elasticsearch có thể không tìm thấy field hoặc trả kết quả rỗng, dù entity property có tên đó.

### 7.1. @Field(name = ...)

Dùng @Field(name = "...") để ánh xạ property sang tên field cụ thể:

~~~java
@Field(name = "customer_id", type = FieldType.Keyword)
private String customerId;

@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Tên field phải nhất quán trong:

- Mapping JSON.
- Query DSL và NativeQuery.
- Sort và aggregation.
- Script truy cập doc['field'].
- Ingest pipeline.
- Data export/import.
- Dashboard và các service khác.

Không giả định Spring Data tự chuyển camelCase thành snake_case nếu chưa cấu hình FieldNamingStrategy tương ứng.

### 7.2. FieldNamingStrategy

Spring Data Elasticsearch có thể dùng FieldNamingStrategy để chuyển tên property theo quy tắc chung. Cách cấu hình phụ thuộc version và configuration class đang dùng.

Ví dụ mục tiêu:

| Property Java | Tên field |
| --- | --- |
| customerId | customer_id |
| createdAt | created_at |
| billingAddress | billing_address |

Nếu dùng naming strategy, hãy kiểm tra mapping được tạo và thống nhất với mọi query được viết thủ công. @Field(name = "...") hữu ích khi cần một tên cụ thể hoặc muốn tránh phụ thuộc vào quy tắc toàn cục.

Không thay đổi naming strategy giữa các phiên bản ứng dụng khi index cũ vẫn đang được dùng. Việc đó có thể khiến entity mới ghi field dưới tên khác trong khi query vẫn tìm tên cũ.

### 7.3. @Id và _id

Property đánh dấu @Id ánh xạ tới metadata _id của Elasticsearch. Nó không giống một field business thông thường trong mapping properties.

Ví dụ:

~~~java
@Id
private String id;
~~~

Truy vấn theo ID có thể dùng Get API hoặc term query trên _id, tùy mục tiêu. Không tạo thêm field id trong mapping rồi cho rằng nó tự đồng nhất với _id.

Nếu nghiệp vụ cần tìm kiếm theo mã sản phẩm, hãy khai báo một property riêng như sku với type keyword. _id là định danh document; sku là dữ liệu domain.

### 7.4. Object và nested path

Với object lồng nhau:

~~~java
public class Address {
    @Field(type = FieldType.Keyword)
    private String city;
}

@Field(type = FieldType.Object)
private Address address;
~~~

Field path có thể là address.city. Nếu mapping dùng nested type thay vì object, query cần nested query đúng path.

Lỗi phổ biến là entity có cấu trúc object nhưng query lại dùng sai path hoặc giả định object và nested có cùng query semantics.

Mapping ví dụ:

~~~json
{
  "properties": {
    "address": {
      "type": "object",
      "properties": {
        "city": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Nếu cần nested semantics:

~~~json
{
  "properties": {
    "items": {
      "type": "nested",
      "properties": {
        "sku": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Nested query phải chỉ rõ path items. Chỉ đổi Java collection thành List không tự bảo đảm Elasticsearch mapping là nested; cần khai báo đúng type.

## 8. @Field, @Transient và mapping metadata

Các annotation ảnh hưởng tới mapping cần được sử dụng nhất quán:

| Annotation | Tác dụng |
| --- | --- |
| @Document | Khai báo entity được quản lý và index mặc định. |
| @Id | Đánh dấu ID của document. |
| @Field | Khai báo field type, tên, format và các thuộc tính mapping. |
| @MultiField | Khai báo field chính cùng các subfield. |
| @InnerField | Khai báo subfield trong multi-field. |
| @Transient | Bỏ qua property khỏi mapping/conversion persistence. |
| @WriteOnlyProperty | Chỉ ghi property, không đọc lại như field thông thường. |
| @ReadOnlyProperty | Chỉ đọc property, không ghi theo cơ chế tương ứng. |

Tên và semantics annotation có thể thay đổi giữa các version. Kiểm tra Javadoc của dependency đang dùng nếu dựa vào thuộc tính nâng cao.

### 8.1. @JsonProperty không thay thế @Field

Spring Data Elasticsearch dùng MappingElasticsearchConverter cho mapping entity. Jackson annotation như @JsonProperty không tự động thay thế metadata của Spring Data trong mọi đường ghi/đọc.

Nếu cùng entity được dùng bởi REST controller và Elasticsearch, có thể tồn tại hai quy tắc serialization khác nhau:

- Jackson serialize DTO/entity cho HTTP JSON.
- MappingElasticsearchConverter serialize entity thành Elasticsearch document.

Đừng giả định đổi @JsonProperty("created_at") sẽ làm mọi query và mapping của Spring Data tự đổi tên. Dùng @Field(name = "created_at") cho Elasticsearch mapping hoặc tạo DTO riêng nếu contract HTTP khác contract persistence.

Khi gọi Elasticsearch Java API Client trực tiếp, JsonpMapper chịu trách nhiệm serialize/deserialize model của Java Client. Đó cũng là một đường conversion riêng với MappingElasticsearchConverter.

## 9. Custom conversions cho kiểu dữ liệu riêng

Khi property dùng kiểu domain riêng hoặc format legacy, có thể đăng ký custom converter.

Ví dụ domain có LegacyLocalTime, nhưng muốn lưu thành Instant UTC:

~~~java
public record LegacyLocalTime(LocalDateTime value) {
}
~~~

Converter ghi:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class LegacyLocalTimeToInstantConverter
        implements Converter<LegacyLocalTime, Instant> {

    @Override
    public Instant convert(LegacyLocalTime source) {
        return source.value().toInstant(ZoneOffset.UTC);
    }
}
~~~

Converter đọc:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class InstantToLegacyLocalTimeConverter
        implements Converter<Instant, LegacyLocalTime> {

    @Override
    public LegacyLocalTime convert(Instant source) {
        return new LegacyLocalTime(
                LocalDateTime.ofInstant(source, ZoneOffset.UTC)
        );
    }
}
~~~

Đây là quy tắc cụ thể: LocalDateTime được hiểu là UTC. Nếu dữ liệu thực tế thuộc một zone nghiệp vụ khác, phải thay ZoneOffset.UTC bằng ZoneId đã xác định. Không dùng converter này nếu domain không thể bảo đảm quy tắc đó.

Đăng ký converter qua ElasticsearchCustomConversions trong configuration:

~~~java
@Bean
@Override
public ElasticsearchCustomConversions elasticsearchCustomConversions() {
    return new ElasticsearchCustomConversions(List.of(
            new LegacyLocalTimeToInstantConverter(),
            new InstantToLegacyLocalTimeConverter()
    ));
}
~~~

Method hook cụ thể có thể khác theo configuration base class và phiên bản Spring Data. Có thể đăng ký bean ElasticsearchCustomConversions nếu cấu hình hiện tại hỗ trợ bean đó. Sau khi đăng ký, kiểm thử cả chiều ghi và đọc; một converter chỉ hoạt động một chiều có thể làm dữ liệu lưu được nhưng đọc lại thất bại.

### 9.1. Phân biệt reading converter và writing converter

- @WritingConverter áp dụng khi chuyển từ kiểu domain sang kiểu lưu trữ.
- @ReadingConverter áp dụng khi chuyển từ kiểu lưu trữ sang kiểu domain.

Đánh dấu rõ chiều chuyển đổi giúp Spring Data chọn converter đúng khi có nhiều kiểu có thể chuyển qua lại.

Tránh đăng ký converter quá tổng quát, ví dụ String sang Object hoặc Number sang String, vì nó có thể ảnh hưởng nhiều property ngoài dự kiến. Ưu tiên converter cho kiểu domain cụ thể.

### 9.2. Converter không thay thế mapping type

Converter quyết định giá trị được serialize/deserialize. Mapping Elasticsearch quyết định field được index như keyword, date, numeric hoặc type khác.

Ví dụ converter chuyển LocalDateTime thành chuỗi ISO không tự làm field thành date. Field mapping vẫn phải khai báo type date với format chấp nhận chuỗi đó.

## 10. Field name sai trong query, sort và aggregation

Một entity có thể lưu đúng nhưng query vẫn trả kết quả sai nếu field path không khớp mapping.

Ví dụ entity:

~~~java
@Field(name = "order_status", type = FieldType.Keyword)
private String status;
~~~

Query phải dùng order_status:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("order_status")
                .value("PAID")
        ))
        .build();
~~~

Các lỗi thường gặp:

- Dùng status thay vì order_status.
- Dùng createdAt thay vì created_at.
- Aggregate trên name kiểu text thay vì name.keyword.
- Dùng address.city trong khi mapping field thực tế có tên khác.
- Dùng nested query cho object field hoặc ngược lại.
- Script đọc doc['price'] trong khi field thật là unit_price.

Query builder không tự suy luận mọi field name từ property Java khi caller truyền chuỗi field name. Hãy giữ constants hoặc central field definitions để giảm lỗi typo.

Ví dụ:

~~~java
public final class ProductFields {

    private ProductFields() {
    }

    public static final String CREATED_AT = "created_at";
    public static final String ORDER_STATUS = "order_status";
    public static final String UNIT_PRICE = "unit_price";
}
~~~

Dùng constants không thay thế kiểm tra mapping, nhưng giúp các query trong codebase dùng cùng một tên field.

## 11. Mapping type đã tồn tại không thể đổi trực tiếp

Giả sử field price ban đầu được map thành keyword, sau đó entity đổi thành BigDecimal và annotation khai báo scaled_float. Elasticsearch không thể đổi type field hiện hữu trong cùng index theo cách sửa mapping thông thường.

Request cập nhật mapping với type khác sẽ bị từ chối. Cách xử lý đúng là tạo index mới với mapping mong muốn rồi reindex dữ liệu.

Quy trình:

1. Tạo index mới với mapping/schema version mới.
2. Chuyển đổi dữ liệu cũ theo quy tắc đã xác định.
3. Reindex hoặc backfill từ nguồn phù hợp.
4. Kiểm tra document lỗi và giá trị không parse được.
5. So sánh count, sample values và query results.
6. Đồng bộ các thay đổi phát sinh trong lúc migration.
7. Chuyển alias đọc/ghi sang index mới.
8. Giữ index cũ trong khoảng rollback được kiểm soát.
9. Xóa index cũ khi đã xác nhận không còn caller.

Ví dụ tạo index mới:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "created_at": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      }
    }
  }
}
~~~

Không dùng update mapping để cố đổi keyword thành date hoặc text thành numeric. Đổi type cần reindex hoặc tạo lại dữ liệu trong index mới.

### 11.1. Chuyển đổi dữ liệu lỗi trong reindex

Nếu source cũ có giá trị không nhất quán, không thể giả định reindex sẽ tự sửa được. Có thể cần ingest pipeline, script hoặc job ETL để chuẩn hóa:

- Chuỗi số có dấu phẩy/dấu chấm theo locale.
- Ngày theo format legacy.
- Giá trị null hoặc chuỗi rỗng.
- Enum cũ đã đổi tên.
- Field cũ có nhiều cách viết.
- Document có field lồng nhau khác schema.

Hãy lưu riêng các document thất bại để xử lý và không bỏ qua lỗi chuyển đổi mà không có thống kê.

## 12. Kiểm tra dữ liệu ở ba lớp

Khi một field không hoạt động như mong đợi, so sánh ba lớp:

| Lớp | Cách kiểm tra | Câu hỏi |
| --- | --- | --- |
| Entity Java | Xem type, annotation, getter/setter và custom converter. | Property có đúng kiểu và đúng tên không? |
| Elasticsearch mapping | GET /index/_mapping hoặc _field_caps. | Field có đúng type, format và path không? |
| Document source | GET /index/_doc/id. | Giá trị thực tế là number, string, null hay object? |

Ví dụ property Java là Instant, mapping là date, nhưng _source chứa chuỗi ngày không có timezone. Khi đọc, converter có thể parse được nhưng ứng dụng vẫn diễn giải sai giờ vì timezone không được xác định.

Một ví dụ khác: Java property là createdAt, mapping là created_at, nhưng NativeQuery tìm createdAt. Mapping và conversion có thể đều đúng; lỗi nằm ở query field name.

Đừng sửa converter khi nguyên nhân thật là query dùng sai tên field. Chẩn đoán theo lớp giúp tránh thay đổi không liên quan.

## 13. Quy trình điều tra một lỗi conversion

Khi nhận lỗi từ production hoặc integration test, hãy thu thập:

1. Request type: index, bulk, update, get hay search.
2. Concrete index thực tế, không chỉ alias.
3. Document ID hoặc request item ID.
4. Tên field được báo lỗi.
5. Giá trị đầu vào đã được che dữ liệu nhạy cảm.
6. Java property type và annotation.
7. Mapping thực tế của field.
8. Source hiện tại của document nếu có.
9. Root cause và error type trong response.
10. Phiên bản Spring Data Elasticsearch, Java API Client và cluster.

Sau đó phân loại:

- Type mismatch: so sánh JSON value với mapping type.
- Date parse: so sánh input với date format và timezone.
- Conversion exception: kiểm tra custom converter và kiểu Java đích.
- Field not found: kiểm tra naming strategy, @Field(name) và nested path.
- Alias conflict: dùng field capabilities để xác định index nào có schema khác.
- Mapping conflict: xác định index được tạo từ template hoặc schema version nào.

## 14. Các API hữu ích để chẩn đoán

### 14.1. Mapping

~~~http
GET /products/_mapping
~~~

Xem toàn bộ type và format field.

### 14.2. Field mapping

~~~http
GET /products/_mapping/field/created_at,price
~~~

Xem mapping của một số field cụ thể.

### 14.3. Field capabilities

~~~http
GET /products-*/_field_caps?fields=created_at,price,status
~~~

Tìm mapping conflict giữa nhiều index.

### 14.4. Document source

~~~http
GET /products/_doc/P-100
~~~

So sánh giá trị thực tế với Java property.

### 14.5. Validate query

~~~http
POST /products/_validate/query?explain=true
Content-Type: application/json

{
  "query": {
    "range": {
      "created_at": {
        "gte": "2026-11-01T00:00:00Z"
      }
    }
  }
}
~~~

Validate query giúp kiểm tra query có hợp lệ về cú pháp và mapping trong phạm vi được hỗ trợ. Nó không chứng minh query trả đúng dữ liệu nghiệp vụ.

### 14.6. Ingest pipeline simulation

Nếu date được parse trong ingest pipeline, có thể mô phỏng pipeline:

~~~http
POST /_ingest/pipeline/_simulate
Content-Type: application/json

{
  "pipeline": {
    "processors": [
      {
        "date": {
          "field": "legacy_created_at",
          "formats": ["yyyy-MM-dd HH:mm:ss"],
          "timezone": "Asia/Ho_Chi_Minh",
          "target_field": "created_at"
        }
      }
    ]
  },
  "docs": [
    {
      "_source": {
        "legacy_created_at": "2026-11-13 15:30:00"
      }
    }
  ]
}
~~~

Simulation giúp kiểm tra processor date và timezone trước khi áp dụng lên dữ liệu thật. Ingest pipeline conversion khác với Spring Data converter; hãy xác định rõ tầng nào chịu trách nhiệm chuẩn hóa.

## 15. Logging và observability

Để điều tra conversion issue, log đủ metadata nhưng tránh log toàn bộ document hoặc thông tin cá nhân.

Nên ghi:

- Index/alias và concrete index nếu biết.
- Document ID hoặc correlation ID.
- Tên field.
- Operation type.
- Error type/status.
- Schema/mapping version.
- Converter name nếu custom conversion thất bại.
- Request ID và timestamp.
- Phiên bản ứng dụng.

Không ghi password, API key, token, dữ liệu thanh toán hoặc toàn bộ _source vào log lỗi.

Trong môi trường development/test, có thể tăng log level cho package Spring Data Elasticsearch hoặc Elasticsearch client để xem request/response. Không bật TRACE rộng trong production vì payload có thể lớn và chứa dữ liệu nhạy cảm.

Theo dõi metric:

- Số document write failure theo error type.
- Số date parse failure.
- Số conversion exception.
- Tỷ lệ search không có kết quả bất thường sau migration.
- Mapping conflict giữa index version.
- Số document bị loại khỏi pipeline hoặc dead-letter queue.

## 16. Các anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ sửa Java type mà không tạo lại index | Mapping cũ vẫn giữ type cũ. | Tạo index mới và reindex. |
| Để dynamic mapping quyết định field quan trọng | Document đầu tiên có thể định nghĩa type sai. | Explicit mapping và index template. |
| Dùng LocalDateTime như một instant | Timezone ngầm và lệch giờ. | Dùng Instant hoặc quy tắc ZoneId rõ ràng. |
| Nhầm epoch seconds với milliseconds | Thời điểm sai rất xa. | Chuẩn hóa đơn vị timestamp. |
| Dùng Double cho tiền mà không có quy tắc precision | Sai số làm tròn. | BigDecimal ở domain và scaled_float/long theo contract. |
| Dùng text cho exact match/aggregation | Query hoặc aggregation không phù hợp. | Keyword hoặc multi-field. |
| Dùng tên Java property trong query thủ công | Field path không khớp mapping. | Dùng tên Elasticsearch từ @Field(name). |
| Nghĩ @JsonProperty điều khiển Spring Data mapping | JSON HTTP và document Elasticsearch có thể khác nhau. | Dùng @Field hoặc converter đúng tầng. |
| Custom converter quá tổng quát | Ảnh hưởng nhiều property ngoài dự kiến. | Converter cho domain type cụ thể. |
| Thêm nhiều date format để che input lỗi | Dữ liệu tiếp tục không nhất quán. | Chuẩn hóa đầu vào và giới hạn format được hỗ trợ. |
| Bỏ qua bulk item errors | Một phần dữ liệu không được ghi. | Kiểm tra từng item và lưu lỗi. |
| Sửa mapping trên alias mà không kiểm tra các index | Các index có type khác nhau. | Dùng _field_caps và migration đồng bộ. |
| Đọc source qua Java API Client rồi giả định Spring converter đã chạy | Entity có thể khác mapping mong muốn. | Phân biệt JsonpMapper và MappingElasticsearchConverter. |

## 17. Checklist phòng ngừa

Trước khi phát hành entity hoặc mapping mới:

1. Property Java có kiểu phản ánh đúng domain không?
2. @Field(type = ...) có được khai báo rõ cho field quan trọng không?
3. Tên field có thống nhất giữa @Field(name), mapping và Query DSL không?
4. ID có được phân biệt với field business không?
5. Date format có khớp input thực tế không?
6. Timestamp dùng seconds hay milliseconds?
7. Timezone có được xác định rõ không?
8. LocalDate, LocalDateTime và Instant có được dùng đúng ngữ nghĩa không?
9. Date precision cần milliseconds hay nanoseconds?
10. BigDecimal/money có quy tắc scale và rounding không?
11. Enum có contract lưu trữ ổn định không?
12. Custom converter có đánh dấu reading/writing đúng chiều không?
13. Mapping được tạo trước khi ingest document không?
14. Các index trong cùng alias có mapping đồng nhất không?
15. Có test round-trip ghi/đọc và test query theo field name không?
16. Có kế hoạch reindex khi cần đổi field type không?

## 18. Tài liệu tham khảo

- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Mapping Annotations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/annotated-entities.html)
- [Spring Data Elasticsearch — Custom Conversions](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/custom-conversions.html)
- [Spring Data Elasticsearch — Field Naming Strategy](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Date field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/date.html)
- [Elasticsearch — Date nanos field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/date_nanos.html)
- [Elasticsearch — Field capabilities API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-field-caps.html)
- [Elasticsearch — Get mapping API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-get-mapping.html)
- [Elasticsearch — Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html)

Lỗi conversion thường bắt nguồn từ sự lệch nhau giữa Java property type, JSON value và Elasticsearch mapping. Với ngày tháng, phải thống nhất format, đơn vị epoch, timezone và precision. Với tên field, dùng mapping name thực tế trong query thay vì mặc định property Java và field JSON giống nhau. Khi mapping type của index đã sai, hãy tạo index mới và reindex theo quy tắc chuyển đổi rõ ràng; thay annotation không sửa được schema đã tồn tại.

