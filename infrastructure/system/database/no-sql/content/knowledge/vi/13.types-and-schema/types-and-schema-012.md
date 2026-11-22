# Serialization, deserialization và ánh xạ sang kiểu Java

Trong một hệ thống Java dùng NoSQL, dữ liệu đi qua nhiều hình dạng trước khi tới nơi lưu trữ: request HTTP có thể mang **JSON**, đối tượng trong bộ nhớ là **record/class Java**, driver chuyển nó thành **BSON**, **AttributeValue**, **cột CQL** hoặc **byte array**, rồi khi đọc ứng dụng lại dựng đối tượng Java từ dữ liệu đã lưu.

Nếu các bước chuyển đổi không được quy định rõ, lỗi có thể rất khó phát hiện: giá tiền **1.390.000** bị biến thành số thực thiếu chính xác; trường **expiresAt** bị mất múi giờ; một trường vắng mặt bị hiểu nhầm là **null**; tài liệu phiên bản cũ không còn đọc được; hay một thao tác đọc–sửa–ghi khiến các trường mới trong database bị xóa mất.

**Serialization** là quá trình biến đối tượng/trạng thái thành một biểu diễn có thể truyền hoặc lưu. **Deserialization** là quá trình đọc biểu diễn đó và khôi phục thành kiểu dữ liệu trong chương trình. **Mapping** bổ sung hợp đồng về trường, kiểu, định danh, quan hệ, phiên bản schema và hành vi khi dữ liệu không đúng kỳ vọng.

Trong chủ đề **Database No SQL → Kiểu dữ liệu và schema**, ta sẽ đi từ cách thiết kế hợp đồng dữ liệu tới ví dụ Java với Jackson, MongoDB BSON, DynamoDB, Redis và Cassandra; sau đó xử lý các vấn đề null/missing, thời gian, số tiền, migration, bảo mật và kiểm thử.

> **Phạm vi:** Ví dụ Java sử dụng những kiểu và API phổ biến để minh họa đường dữ liệu. Driver/framework và phiên bản có thể có quy tắc codec hoặc annotation riêng. Các đoạn code độc lập không phải cấu hình production hoàn chỉnh và không khẳng định một mapper hoạt động giống nhau trên mọi NoSQL.

## 1. Phân biệt serialization, deserialization, mapping và validation

Một dữ liệu sản phẩm có thể bắt đầu ở JSON:

~~~json
{
  "productId": "P-42",
  "name": "Bàn làm việc",
  "priceMinor": 1390000,
  "currency": "VND",
  "createdAt": "2026-11-14T08:00:00Z",
  "active": true
}
~~~

Sau khi API nhận request, Java có thể dựng record:

~~~java
import java.time.Instant;

public record Product(
        String productId,
        String name,
        long priceMinor,
        String currency,
        Instant createdAt,
        boolean active
) {}
~~~

Khi lưu vào NoSQL, các giá trị không nhất thiết được ghi theo cùng một kiểu:

- **MongoDB:** ngày tháng có thể là **BSON Date**, số 64-bit là **BSON Int64**, định danh mặc định của document là trường **_id**.
- **DynamoDB:** một thuộc tính số được biểu diễn dưới kiểu **N** với giá trị dạng chuỗi số trong API, timestamp thường do ứng dụng chọn biểu diễn.
- **Redis:** giá trị có thể là chuỗi hoặc chuỗi byte tùy lệnh và serializer; Redis không tự biết một byte array là Java record.
- **Cassandra:** các cột được khai báo theo kiểu **CQL**, ví dụ text, bigint, timestamp, uuid, decimal.

Tất cả đều có thể biểu diễn cùng **ý nghĩa nghiệp vụ** nhưng không có cùng hình dạng vật lý.

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **Serialization** | Đối tượng → JSON/BSON/bytes/AttributeValue | Product → tài liệu BSON |
| **Deserialization** | JSON/BSON/bytes/AttributeValue → đối tượng | BSON Date → Instant |
| **Mapping** | Quy định trường nào tương ứng với thuộc tính nào, kiểu/phiên bản ra sao | product_id → productId, price_minor → long |
| **Validation** | Xác minh dữ liệu có hợp lệ về cấu trúc và nghiệp vụ không | priceMinor ≥ 0, currency không rỗng |
| **Migration/Upcasting** | Chuyển dữ liệu schema cũ thành hình dạng mới có kiểm soát | V1 priceVnd → V2 priceMinor + currency |

Serializer có thể chuyển một giá trị **không hợp lệ về nghiệp vụ** thành bytes hoàn toàn hợp lệ. Vì thế “serialize thành công” không có nghĩa “dữ liệu đúng”.

## 2. Hình dung đường đi dữ liệu end-to-end

~~~mermaid
flowchart TD
    C["HTTP client / event producer"] --> J["JSON / message payload"]
    J --> D["Deserialize thành DTO Java"]
    D --> V["Validate input và domain"]
    V --> M["Map sang persistence model"]
    M --> S["Driver codec / serializer"]
    S --> N[("NoSQL store")]
    N --> R["Driver decode"]
    R --> P["Persistence model"]
    P --> U["Map sang domain / response DTO"]
    U --> O["Serialize JSON / event"]
    O --> C
~~~

Những mũi tên này đại diện cho **các ranh giới hợp đồng**:

1. **External contract:** client gửi JSON như thế nào, có dùng snake_case không, timestamp định dạng gì?
2. **Domain contract:** giá, trạng thái, định danh và bất biến có ý nghĩa ra sao trong Java?
3. **Persistence contract:** document/column có tên và kiểu gì, index dùng trường nào?
4. **Message contract:** event gửi cho hệ khác có thể được đọc bởi consumer phiên bản cũ không?

Không nhất thiết phải tạo một lớp Java riêng cho mọi mũi tên trong một ứng dụng nhỏ. Nhưng khi hợp đồng giữa API, domain và database **tiến hóa khác nhau**, việc dùng chung một class có thể làm thay đổi ở một lớp phá vỡ lớp còn lại.

### 2.1. Phân biệt DTO và mô hình lưu trữ

Một request tạo sản phẩm **không nên tự quyết định tất cả trường được lưu**:

~~~json
{
  "name": "Bàn làm việc",
  "priceMinor": 1390000,
  "currency": "VND"
}
~~~

Ứng dụng có thể bổ sung:

~~~text
productId      ← server tạo
createdAt      ← server ghi nhận
version        ← khởi tạo 1
active         ← false theo workflow
tenantId       ← từ thông tin người gọi đã xác thực
~~~

Nếu deserialize request trực tiếp thành persistence entity rồi ghi nguyên object, client có thể vô tình hoặc cố ý gửi **tenantId, status, isAdmin, version** mà không có quyền điều khiển. Nên chọn rõ tập field được phép nhận và **map có chủ đích**.

## 3. JSON không đồng nhất với hệ kiểu Java

JSON chuẩn có các dạng cơ bản:

- Object.
- Array.
- String.
- Number.
- Boolean.
- Null.

JSON **không có kiểu gốc** cho UUID, Instant, Decimal128, binary data, số nguyên 64-bit phân biệt số thực, hoặc kiểu enum của Java. Những ý nghĩa này phải được truyền bằng **quy ước dữ liệu** và mapping.

Ví dụ:

~~~json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "createdAt": "2026-11-14T08:00:00Z",
  "amount": 1390000.25,
  "contentBase64": "AQIDBA=="
}
~~~

Đây vẫn chỉ là **hai chuỗi, một number và một chuỗi khác** ở mức JSON. Chương trình Java có thể quyết định:

~~~text
id            → java.util.UUID
createdAt     → java.time.Instant
amount        → java.math.BigDecimal
contentBase64 → byte[]
~~~

Quy ước khác nhau giữa hai service có thể khiến cùng một payload được hiểu khác nhau. Ví dụ timestamp không kèm offset có thể bị coi là UTC ở service A nhưng theo múi giờ server ở service B.

### 3.1. Java Map<String, Object> không phải schema ổn định

Nếu parse JSON vào **Map<String, Object>**, một thư viện có thể chọn **Integer**, **Long**, **Double**, **BigDecimal**, **List**, **Map** tùy cách cấu hình và số thực tế.

~~~java
Map<String, Object> payload = ...;
Object amount = payload.get("amount");
~~~

Code ép kiểu trực tiếp:

~~~java
long amount = (Long) payload.get("amount");
~~~

có thể ném **ClassCastException** nếu parser dựng **Integer**, dù JSON đầu vào là một number hoàn toàn bình thường. Khi payload có hợp đồng rõ, hãy dùng DTO có **kiểu xác định** hoặc dùng **JsonNode** và chuyển kiểu có kiểm soát.

Với dữ liệu cần thao tác động, Map vẫn hữu ích, nhưng nên xác định cách xử lý số nguyên, số thực, trường thiếu và đối tượng lồng nhau; không coi Map là cách tránh mọi vấn đề schema.

## 4. Bảng ánh xạ kiểu dữ liệu thường gặp

| Khái niệm nghiệp vụ | Kiểu Java nên cân nhắc | JSON API | MongoDB BSON | DynamoDB / Redis / Cassandra |
| --- | --- | --- | --- | --- |
| Mã định danh | String hoặc UUID | String | String/Binary UUID tùy codec | S/B, bytes, uuid/text |
| Số lượng nhỏ | int/Integer | Number | Int32/Int64 tùy mapping | N, string/bytes, int |
| Số lượng lớn | long/Long | Number | Int64 | N, string/bytes, bigint |
| Tiền theo đơn vị nhỏ nhất | long hoặc BigInteger khi thật cần | Number hoặc String theo contract | Int64/Decimal128 tùy miền | N, string/bytes, bigint/decimal |
| Số thập phân chính xác | BigDecimal | Number hoặc String theo contract | Decimal128 | N, string có quy ước, decimal |
| Số đo gần đúng | double/Double | Number | Double | N, string/bytes, double |
| Thời điểm tuyệt đối | Instant | ISO 8601 có offset | Date (mili giây) | S/N do app chọn, bytes, timestamp |
| Ngày lịch không có giờ | LocalDate | YYYY-MM-DD | String/Date theo quy ước | S, string, date |
| Cờ trạng thái | boolean/Boolean | Boolean | Boolean | BOOL, chuỗi/bytes, boolean |
| Giá trị hữu hạn | enum | String | String | S, string, text |
| Dữ liệu nhị phân | byte[] / ByteBuffer | Base64 nếu JSON | Binary | B, bytes, blob |
| Danh sách | List<T> | Array | Array | L, JSON/bytes, list<T> |
| Cấu trúc lồng nhau | record/class/Map | Object | Embedded document | M, JSON/bytes, UDT/map tùy schema |

**Bảng là ánh xạ khái niệm, không phải chuyển đổi tự động.** Ví dụ DynamoDB không có kiểu ngày thời điểm gốc tương ứng **Instant**; ứng dụng thường lưu chuỗi ISO 8601 hoặc epoch theo quy ước. Trong khi đó Cassandra có kiểu timestamp, nhưng mức chính xác và cách driver encode cần được kiểm tra.

Các lựa chọn **String hay UUID**, **long hay BigDecimal**, **Instant hay LocalDate** phải dựa trên ý nghĩa dữ liệu, khả năng truy vấn/index và yêu cầu tương thích.

## 5. Ánh xạ số: tránh lỗi chính xác và vượt giới hạn

### 5.1. Tiền không nên dùng double một cách tùy tiện

Số thực nhị phân không biểu diễn chính xác mọi số thập phân. Ví dụ:

~~~java
double a = 0.1;
double b = 0.2;
System.out.println(a + b == 0.3); // false
~~~

Với tiền tệ và số liệu cần chính xác, có hai chiến lược phổ biến:

**A. Số nguyên theo đơn vị nhỏ nhất**

~~~java
long priceMinor = 1_390_000L; // VND theo hợp đồng ở ví dụ
long subtotalMinor = Math.multiplyExact(priceMinor, 3);
~~~

Tính toán dùng số nguyên, dễ so sánh và ghi. Tuy nhiên phải **xác định đơn vị**, tỷ giá/quy tắc làm tròn và xử lý overflow. Không thể giả định mọi loại tiền đều có cùng số chữ số phần thập phân.

**B. BigDecimal**

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("1390000.25");
BigDecimal quantity = new BigDecimal("3");
BigDecimal subtotal = unitPrice.multiply(quantity);
BigDecimal rounded = subtotal.setScale(2, RoundingMode.HALF_UP);
~~~

Nên tạo BigDecimal từ **chuỗi thập phân** hoặc dữ liệu có biểu diễn chính xác tương đương, không dùng **new BigDecimal(0.1)** nếu định giữ đúng giá trị thập phân “0.1”.

### 5.2. BigDecimal khác Decimal128

**BigDecimal của Java** có phạm vi precision/scale chịu những giới hạn khác với kiểu **BSON Decimal128**. Chuyển từ BigDecimal sang Decimal128 có thể thất bại nếu giá trị không biểu diễn được. Tương tự DynamoDB số N cũng có giới hạn độ chính xác và độ lớn theo dịch vụ.

Ví dụ MongoDB Java driver:

~~~java
import java.math.BigDecimal;
import org.bson.types.Decimal128;

BigDecimal amount = new BigDecimal("1390000.25");
Decimal128 bsonAmount = new Decimal128(amount);
BigDecimal restored = bsonAmount.bigDecimalValue();
~~~

**Không phải mọi BigDecimal đều ánh xạ được thành Decimal128.** Kiểm tra miền giá trị và cách làm tròn trước khi ghi; đừng để driver tự thu hẹp độ chính xác mà ứng dụng không biết.

### 5.3. JSON number và giới hạn JavaScript

Một **long** của Java có thể vượt phạm vi số nguyên được biểu diễn chính xác bằng **Number** của JavaScript. Nếu API cần truyền ID số lớn hoặc giá trị nguyên lớn cho frontend, có thể dùng **chuỗi thập phân** trong JSON theo hợp đồng, thay vì buộc client parse thành Number.

Ví dụ:

~~~json
{
  "eventId": "9223372036854775807",
  "count": 120
}
~~~

**eventId** là chuỗi định danh, không phải số lượng để tính toán. Việc chuyển sang chuỗi phải được áp dụng **nhất quán** ở API, event và database mapping; đổi từ number sang string không phải thay đổi tương thích với mọi consumer.

## 6. Ánh xạ thời gian: Instant, LocalDate và múi giờ

Một trường tên **createdAt** thường diễn đạt **một thời điểm tuyệt đối** trên trục UTC; trong Java, **Instant** là kiểu phù hợp.

Một trường tên **checkInDate** có thể chỉ là **ngày lịch tại nơi lưu trú**; **LocalDate** phù hợp hơn. Một lịch hẹn 09:00 theo múi giờ thành phố lại cần **LocalDateTime + ZoneId** hoặc biểu diễn đầy đủ quy tắc múi giờ.

| Câu hỏi | Kiểu thường hợp lý |
| --- | --- |
| Sự kiện được server commit khi nào? | Instant |
| Sinh nhật hoặc ngày check-in là ngày nào? | LocalDate |
| Cuộc họp lúc 09:00 theo múi giờ cụ thể? | ZonedDateTime hoặc LocalDateTime cùng ZoneId |
| Thời điểm có offset trong API? | OffsetDateTime hoặc Instant sau khi chuẩn hóa |
| Khoảng thời lượng? | Duration |

Ví dụ:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant createdAt = Instant.parse("2026-11-14T08:00:00Z");
LocalDate checkInDate = LocalDate.parse("2026-12-01");

ZonedDateTime localDisplay =
        createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

### 6.1. MongoDB BSON Date và độ chính xác

**BSON Date** biểu diễn thời điểm theo **mili giây kể từ Unix epoch**. **Instant** hỗ trợ độ chính xác nanosecond trong Java; khi chuyển sang BSON Date, phần nhỏ hơn mili giây không được giữ nguyên.

~~~java
import java.time.Instant;
import java.util.Date;

Instant input = Instant.parse("2026-11-14T08:00:00.123456789Z");
Date bsonDateRepresentation = Date.from(input);
Instant restored = bsonDateRepresentation.toInstant();
// restored thường ở độ phân giải mili giây:
// 2026-11-14T08:00:00.123Z
~~~

**Round-trip không bảo đảm khôi phục đủ nanosecond** nếu định dạng đích chỉ giữ mili giây. Đây là khác biệt có thể ảnh hưởng khóa sự kiện, sắp xếp, deduplication hoặc phép đo latency cực nhỏ.

### 6.2. Không dùng LocalDateTime để lưu thời điểm tuyệt đối nếu thiếu múi giờ

~~~text
2026-11-14T08:00:00
~~~

Chuỗi này **không cho biết** 08:00 UTC, giờ Việt Nam hay giờ của server khác. Nếu một service tự mặc định UTC và service khác mặc định timezone máy, dữ liệu sẽ lệch nhiều giờ.

Nên:

- Gửi **ISO 8601 có offset hoặc Z** cho thời điểm tuyệt đối.
- Lưu **Instant** ở domain khi thích hợp.
- Định nghĩa timezone của lịch nghiệp vụ riêng.
- Không dùng timestamp từ client không đáng tin làm thời điểm commit bảo mật/giao dịch.
- Kiểm tra precision khi đi qua JSON, BSON, CQL và API.

### 6.3. Phân biệt thời gian sự kiện và thời gian lưu

~~~text
eventTime        : cảm biến đo lúc 09:00
serverAcceptedAt : server nhận lúc 09:30
committedAt      : ghi thành công lúc 09:30:01
expiresAt        : thời điểm hết hiệu lực theo nghiệp vụ
~~~

Những trường này có nghĩa khác nhau. Nếu trộn chúng khi serialization hoặc tự suy ra expiresAt từ eventTime mà không có hợp đồng, TTL/retention có thể sai, đặc biệt với dữ liệu đến muộn.

## 7. UUID, ID và binary encoding

Java có kiểu **UUID**:

~~~java
import java.util.UUID;

UUID id = UUID.fromString(
    "550e8400-e29b-41d4-a716-446655440000"
);
String text = id.toString();
~~~

UUID là giá trị **128 bit**, có dạng văn bản canonical 36 ký tự. Khi lưu trong một NoSQL, ta có thể chọn:

- **String**: dễ đọc, dễ hiển thị và trao đổi qua JSON.
- **Binary/UUID native**: tiết kiệm byte và thuận tiện cho một số index/driver.

Nhưng lựa chọn binary cần xác định **thứ tự byte, UUID representation, endian và codec**. Hai hệ cùng nhận 16 byte chưa chắc dựng về cùng UUID nếu chúng dùng quy tắc byte order khác nhau.

Với MongoDB Java driver, **UUID representation** và BSON binary subtype là chi tiết cấu hình quan trọng khi đọc dữ liệu cũ hoặc dữ liệu do client khác ghi. Không nên tự thay encoding rồi đổi thẳng ở production mà không thử round-trip từ **bản ghi lịch sử**.

### 7.1. ID từ API có thể không là khóa lưu trữ

Ví dụ API trả:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Nhưng kho có thể lưu:

~~~text
partitionKey = "TENANT#shop-42"
sortKey      = "ORDER#550e8400-e29b-41d4-a716-446655440000"
~~~

**ID công khai**, **partition key** và **sort key** không nhất thiết cùng một kiểu hoặc cùng một trường. Mapper có thể phải xây dựng/giải mã khóa tổng hợp dựa trên nhiều thuộc tính.

Hãy giữ hợp đồng **ID bất biến** khi thay cấu trúc lưu trữ; nếu mapper làm lộ khóa vật lý vào API, một đợt migration có thể buộc đổi tất cả client.

## 8. Null, missing và giá trị mặc định

Document NoSQL có thể phân biệt ba trạng thái:

~~~json
{ "productId": "P-42" }
~~~

~~~json
{ "productId": "P-42", "description": null }
~~~

~~~json
{ "productId": "P-42", "description": "" }
~~~

Ở ví dụ trên:

- **Missing**: trường không tồn tại.
- **Null**: trường tồn tại với giá trị null.
- **Empty string**: có một chuỗi hợp lệ nhưng rỗng.

Các trạng thái có thể mang nghĩa khác nhau trong API PATCH:

~~~json
{}
~~~

có thể có nghĩa **không đổi gì**;

~~~json
{ "description": null }
~~~

có thể có nghĩa **xóa giá trị mô tả**;

~~~json
{ "description": "" }
~~~

có thể có nghĩa **đặt mô tả thành chuỗi rỗng**.

**Không được giả định mapper luôn giữ nguyên phân biệt missing/null.** Một record Java với trường **String description** có thể có giá trị null trong cả hai trường hợp missing và explicit null, nếu không lưu thêm thông tin.

### 8.1. Primitive và wrapper khác nhau

~~~java
record ProductA(boolean active, long stock) {}
record ProductB(Boolean active, Long stock) {}
~~~

Primitive **boolean** và **long** không biểu diễn null; chúng có giá trị mặc định false và 0 ở những ngữ cảnh khởi tạo tương ứng. Wrapper **Boolean** và **Long** có thể null.

Nếu một bản ghi cũ **không có trường active**, việc map ngầm thành false có thể làm sản phẩm đang bán bị coi là ngừng bán. Đây là thay đổi nghiệp vụ, không chỉ là chi tiết kỹ thuật.

Lựa chọn hợp lý:

- Với field **bắt buộc**, kiểm tra presence ở database/DTO và từ chối khi thiếu.
- Với field **có default hợp lệ theo nghiệp vụ**, định nghĩa rõ default và thời điểm áp dụng.
- Với **PATCH**, dùng kiểu biểu diễn có thể phân biệt **absent/null/value** (ví dụ JSON tree, patch operation hoặc wrapper riêng), không suy luận từ một nullable property đơn giản.
- Với dữ liệu lịch sử, viết **upcaster/migration** để chuyển từ schema cũ sang schema mới có kiểm soát.

### 8.2. Optional không tự giải quyết mọi trường hợp

**Optional<T>** hữu ích để diễn đạt khả năng không có giá trị ở một số API Java, nhưng không mặc nhiên phân biệt **field absent** và **field có JSON null**. Tùy mapper còn cần module/hướng dẫn riêng để serialize Optional đúng cách.

Trong persistence model hoặc DTO cập nhật, hãy chọn biểu diễn phù hợp với hợp đồng, thay vì dùng Optional ở mọi field như giải pháp tổng quát.

## 9. Ví dụ thực hành với Jackson và Java 21

**Jackson** là thư viện phổ biến để chuyển giữa JSON và Java object. Ví dụ bên dưới dùng **record** và **java.time.Instant**.

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.time.Instant;

public class JacksonProductExample {

    public record ProductDto(
            String productId,
            String name,
            long priceMinor,
            String currency,
            Instant createdAt
    ) {}

    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        String json = """
                {
                  "productId": "P-42",
                  "name": "Bàn làm việc",
                  "priceMinor": 1390000,
                  "currency": "VND",
                  "createdAt": "2026-11-14T08:00:00Z"
                }
                """;

        ProductDto product = mapper.readValue(json, ProductDto.class);
        String serializedAgain = mapper.writeValueAsString(product);

        System.out.println(product.priceMinor());
        System.out.println(serializedAgain);
    }
}
~~~

**Điểm cần hiểu:**

- **JavaTimeModule** giúp Jackson xử lý nhiều kiểu thuộc **java.time**, trong đó có Instant. Dependency tương ứng phải có trong project.
- **WRITE_DATES_AS_TIMESTAMPS = false** đưa ngày/giờ về dạng chuỗi ISO phù hợp, thay vì một dạng timestamp số/array do cấu hình khác quyết định.
- **FAIL_ON_UNKNOWN_PROPERTIES** giúp từ chối field bất ngờ ở một số hợp đồng chặt, nhưng có thể không phù hợp với event cần tương thích mở rộng trường mới.
- **ObjectMapper** có thể tái sử dụng sau khi cấu hình xong; không nhất thiết tạo mới cho mỗi request.

Đoạn ví dụ chỉ thực hiện parse/serialize. Nó **chưa kiểm tra** priceMinor âm, currency nằm trong tập cho phép, hay người gửi có quyền ghi productId.

### 9.1. Đặt tên field khác nhau giữa JSON và Java

Nếu API dùng **snake_case**:

~~~json
{
  "product_id": "P-42",
  "price_minor": 1390000
}
~~~

có thể dùng annotation:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record ProductApiDto(
        @JsonProperty("product_id") String productId,
        @JsonProperty("price_minor") long priceMinor
) {}
~~~

Hoặc cấu hình naming strategy thống nhất cho toàn API nếu hợp đồng yêu cầu. **Không trộn ngẫu nhiên naming strategy** giữa API và database model; tên index/query trong NoSQL phải khớp trường thật được lưu.

### 9.2. Khi nào nên bỏ qua unknown fields?

Đối với event có nhiều consumer, một field mới trong payload:

~~~json
{
  "productId": "P-42",
  "priceMinor": 1390000,
  "promotionBadge": "SALE"
}
~~~

có thể khiến consumer cũ lỗi nếu nó từ chối field chưa biết. Để hỗ trợ **forward compatibility**, có thể cho phép **ignore unknown** ở lớp event/DTO thích hợp:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProductUpdatedEvent(
        String productId,
        long priceMinor
) {}
~~~

Nhưng **ignore unknown cũng có rủi ro**: nếu client gửi sai chính tả **priceMnor**, mapper có thể bỏ trường lỗi và tạo ra giá trị mặc định **priceMinor=0**. Vì vậy:

- **API ghi từ client không tin cậy:** thường cần validate chặt, phát hiện field lạ khi hợp đồng yêu cầu.
- **Event giữa các service:** có thể dùng quy tắc tương thích mềm hơn, nhưng vẫn phải validate field bắt buộc và schemaVersion.
- **Dữ liệu database lịch sử:** có thể cần upcaster thay vì âm thầm bỏ thông tin.

Không có một cấu hình unknown-field đúng cho mọi ranh giới.

### 9.3. JsonNode hữu ích khi cần phân biệt missing/null

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(
        "{\"description\": null}"
);

boolean present = root.has("description"); // true với explicit null
boolean isNull = root.path("description").isNull(); // true
boolean missing = root.path("other").isMissingNode(); // true
~~~

Đây là cách giữ thông tin **presence** khi xử lý PATCH hoặc dữ liệu nhiều phiên bản. Sau đó vẫn cần **chuyển kiểu có kiểm soát** và kiểm tra dữ liệu trước khi lưu, tránh đi thẳng từ JsonNode không tin cậy tới một lệnh cập nhật database.

## 10. MongoDB: Java object, Document, BSON và POJO codec

MongoDB lưu **BSON document**, không phải JSON text nguyên xi. BSON có các kiểu gốc như **ObjectId, Int32, Int64, Double, Decimal128, Date, Binary, Boolean, Array, Embedded Document**.

### 10.1. Mapping thủ công giúp thấy rõ kiểu

Ví dụ tạo một **Document** trong Java:

~~~java
import org.bson.Document;
import org.bson.types.Decimal128;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

Instant now = Instant.parse("2026-11-14T08:00:00Z");

Document stored = new Document("_id", "P-42")
        .append("name", "Bàn làm việc")
        .append("price", new Decimal128(new BigDecimal("1390000.25")))
        .append("currency", "VND")
        .append("createdAt", Date.from(now))
        .append("schemaVersion", 2);

String id = stored.getString("_id");
BigDecimal price =
        stored.get("price", Decimal128.class).bigDecimalValue();
Instant createdAt = stored.getDate("createdAt").toInstant();
~~~

**Lưu ý:** Document là một đối tượng Java để biểu diễn document. Khi driver ghi nó, **codec** chuyển kiểu Java sang BSON; khi đọc, codec chuyển BSON thành các giá trị Java. Việc tạo Document trong bộ nhớ **chưa chứng minh** document đã được lưu hoặc mọi trường có đúng kiểu trong database. Test tích hợp cần xác nhận round-trip qua driver và server.

### 10.2. ObjectId không đồng nghĩa với String

MongoDB thường dùng **_id** kiểu ObjectId nếu ứng dụng không chỉ định ID riêng. Trong Java:

~~~java
import org.bson.types.ObjectId;

ObjectId id = new ObjectId();
String textId = id.toHexString();
ObjectId restored = new ObjectId(textId);
~~~

Nếu API nhận ID ở dạng chuỗi hex nhưng document lưu **ObjectId**, truy vấn theo String có thể **không khớp** vì BSON String khác ObjectId. Mapper phải chuyển đúng kiểu **trước khi xây query**. Ngược lại, nếu ứng dụng chủ động lưu _id là String thì không được tự ép mọi ID thành ObjectId.

### 10.3. POJO codec và framework mapping

Có thể dùng **MongoDB POJO codec** hoặc framework như **Spring Data MongoDB** để map class/record ↔ document theo annotation/convention. Những công cụ này giảm code lặp, nhưng phải xác nhận:

- Tên trường và mapping **_id**.
- Kiểu BSON của số, ngày/giờ, UUID và decimal.
- Cách dựng immutable class/record qua constructor.
- Polymorphism, enum và kiểu collection lồng nhau.
- Hành vi khi field thiếu/null, field đổi tên hoặc dữ liệu cũ sai kiểu.
- Giá trị mặc định và converter tùy biến.

Đừng mặc định một annotation ở **Jackson JSON layer** sẽ tự điều khiển tên trường của **MongoDB document codec**. Mỗi hệ mapping có annotation và quy tắc riêng; cần nêu ranh giới rõ trong project.

### 10.4. Thay thế toàn bộ document có thể làm mất trường

Giả sử service V2 lưu:

~~~json
{
  "_id": "P-42",
  "name": "Bàn làm việc",
  "priceMinor": 1390000,
  "searchBoost": 12
}
~~~

Service V1 chỉ biết **_id, name, priceMinor**, đọc rồi **replaceOne** bằng đối tượng V1. Nếu serializer không giữ trường chưa biết, **searchBoost có thể biến mất**.

Giải pháp theo ngữ cảnh:

- Với thao tác chỉ sửa giá, dùng **$set** đúng field thay đổi thay vì replace cả document.
- Dùng **version/optimistic concurrency** để tránh ghi đè khi có writer cạnh tranh.
- Thiết kế rollout schema để writer cũ không xóa field mới.
- Nếu cần đọc–sửa–ghi toàn bộ, có thể dùng mô hình giữ field mở rộng có chủ đích và validate dữ liệu.

**Serializer không phải công cụ hòa giải cập nhật đồng thời.** Một round-trip object thành công vẫn có thể làm mất dữ liệu khi object không chứa đầy đủ trường của bản ghi hiện hành.

## 11. DynamoDB: AttributeValue và ánh xạ kiểu Java

AWS DynamoDB dùng **AttributeValue** với những kiểu như **S, N, B, BOOL, NULL, L, M** và các kiểu set. Ở SDK Java v2, ví dụ tạo item với low-level API:

~~~java
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import java.util.Map;

Map<String, AttributeValue> item = Map.of(
        "PK", AttributeValue.builder().s("PRODUCT#P-42").build(),
        "SK", AttributeValue.builder().s("PROFILE").build(),
        "name", AttributeValue.builder().s("Bàn làm việc").build(),
        "priceMinor", AttributeValue.builder().n("1390000").build(),
        "active", AttributeValue.builder().bool(true).build(),
        "createdAt",
        AttributeValue.builder().s("2026-11-14T08:00:00Z").build()
);
~~~

**Điểm dễ nhầm:**

- Kiểu **N** nhận giá trị số dưới dạng **chuỗi thập phân trong API**, nhưng đó là **số DynamoDB**, không phải thuộc tính String S.
- **S("1390000")** và **N("1390000")** khác nhau khi so sánh và xử lý dữ liệu.
- Không có kiểu **Instant** gốc; lưu timestamp dưới S hoặc N cần quy ước thống nhất.
- **PK/SK** là khóa truy cập vật lý, không nhất thiết giống object ID công khai.
- Không tự cho rằng các field có Java **null** được lưu thành AttributeValue NULL; tùy mapper, chúng có thể bị bỏ qua, xóa hoặc ghi NULL theo cấu hình.

Ví dụ đọc:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

String name = item.get("name").s();
long priceMinor = Long.parseLong(item.get("priceMinor").n());
Instant createdAt = Instant.parse(item.get("createdAt").s());

// Nếu dùng số thập phân có phần lẻ:
BigDecimal amount = new BigDecimal("1390000.25");
String dynamoNumber = amount.toPlainString();
~~~

Khi item có thể thiếu **priceMinor**, cần kiểm tra **item.get("priceMinor") != null** trước khi gọi **n()** và xử lý theo schema. Đoạn ví dụ giả định item hợp lệ.

### 11.1. Enhanced Client hoặc mapper tự động

Trong ứng dụng lớn, **DynamoDB Enhanced Client** và các bean/table schema có thể giảm thao tác xây Map AttributeValue thủ công. Nhưng mapper vẫn cần định nghĩa:

- **Partition key/sort key** và các thuộc tính/index.
- Converters cho **Instant, UUID, enum, Decimal/BigDecimal** theo chính sách đã chọn.
- Hành vi khi **field null** trong PutItem/UpdateItem.
- Mapping object lồng nhau và schema version.
- Điều kiện ghi (conditional write) khi cần bảo vệ version và tính duy nhất.

Không nên suy luận rằng một property **Long** luôn serialize thành N có cùng cách xử lý overflow trên mọi phiên bản SDK. Dùng round-trip test theo đúng converter được triển khai.

### 11.2. Timestamp dạng chuỗi chỉ sắp đúng khi có quy tắc

Nếu lưu timestamp dạng ISO 8601 để dùng trong **sort key**, phải thống nhất:

- Múi giờ (thường dùng UTC).
- Độ dài, số chữ số phần giây và quy ước biểu diễn.
- Cách escape các thành phần khóa ghép.

Ví dụ các chuỗi cùng diễn đạt thời điểm nhưng khác offset:

~~~text
2026-11-14T08:00:00Z
2026-11-14T15:00:00+07:00
~~~

Chúng không có cùng thứ tự từ điển theo mọi so sánh string dù trùng thời điểm. Nếu muốn sort theo thời gian, nên chuẩn hóa representation, hoặc dùng epoch được encode theo quy tắc bảo toàn thứ tự.

## 12. Redis: giá trị bytes không tự có kiểu domain

Một ứng dụng Java có thể lưu cùng sản phẩm vào Redis bằng nhiều cách:

~~~text
SET product:P-42 "{...JSON...}"
SET product:P-42 <binary codec output>
HSET product:P-42 name "Bàn làm việc" priceMinor "1390000"
~~~

Redis hỗ trợ các cấu trúc dữ liệu như string, hash, list, set và sorted set, nhưng **ý nghĩa Java object và cách encode field do ứng dụng chọn**. Với một giá trị string/blob:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = ...; // cấu hình thống nhất

byte[] bytes = mapper.writeValueAsBytes(productDto);
// redisClient.set(keyBytes, bytes); // minh họa transport

ProductDto restored =
        mapper.readValue(bytes, ProductDto.class);
~~~

Đây là **đường JSON ↔ byte[]**, không phải ví dụ về một thư viện Redis cụ thể. Khi dùng Spring Data Redis, Lettuce, Jedis hoặc client khác, cần chọn serializer cho **key và value** và bảo đảm mọi service đọc cùng một định dạng.

### 12.1. Không đổi serializer âm thầm

Nếu trước đây key lưu JSON UTF-8, sau deploy mới ứng dụng đọc bằng codec nhị phân khác, dữ liệu cache cũ có thể gây exception khi deserialize. Một số cách triển khai:

- **Versioned key**: product:v1:P-42, product:v2:P-42.
- **Version trong payload** và reader hỗ trợ phiên bản cũ.
- Xóa cache cũ có kiểm soát khi dữ liệu có thể tái tạo, kèm warm-up/rate limit.
- Dual-read trong giai đoạn chuyển đổi nếu cần.

Với dữ liệu **không phải cache có thể tái tạo**, không được coi việc xóa hàng loạt key là phương pháp migration an toàn.

### 12.2. TTL không nằm trong JSON nếu không được thiết kế

Khi Redis key có TTL 300 giây, deadline hết hạn là **metadata của key**, không nhất thiết xuất hiện trong JSON value.

~~~text
key: product:P-42
value: {"productId":"P-42","priceMinor":1390000}
TTL: 300 giây
~~~

Nếu ứng dụng chỉ deserialize value, nó không tự biết TTL còn lại. Nếu cần hạn dùng nghiệp vụ như **tokenExpiresAt**, hãy lưu/kiểm tra trường đó theo hợp đồng riêng; đừng dựa vào việc một key tồn tại để suy ra quyền còn hiệu lực trong mọi đường đọc hoặc mọi bản cache.

### 12.3. Dữ liệu nhị phân và codec nội bộ

Các codec như JSON, MessagePack, CBOR, Protobuf hoặc serializer tùy biến có mức độ gọn, nhanh, dễ đọc và tương thích khác nhau. Dữ liệu nén/nhị phân có thể giảm payload nhưng:

- Khó debug bằng cách nhìn trực tiếp.
- Yêu cầu versioning/định nghĩa schema chính xác.
- Phụ thuộc thư viện/codec và cách xử lý unknown fields.
- Có nguy cơ khó migration nếu format gắn với class Java nội bộ.

Không nên dùng **Java native Object Serialization** làm hợp đồng chia sẻ dài hạn giữa nhiều service chỉ vì nó tự lưu object; nó có các vấn đề về bảo mật khi deserialize đầu vào không tin cậy, tính tương thích class và khả năng vận hành.

## 13. Cassandra CQL và HBase: ánh xạ cột/byte

### 13.1. Cassandra có các kiểu được khai báo

Ví dụ bảng CQL:

~~~sql
CREATE TABLE telemetry.events_by_device (
    device_id text,
    event_time timestamp,
    event_id uuid,
    amount decimal,
    PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

Ứng dụng dùng driver Cassandra có thể map:

~~~text
device_id  text      ↔ String
event_time timestamp ↔ Instant
event_id   uuid      ↔ UUID
amount     decimal   ↔ BigDecimal
~~~

Ví dụ Java driver (giả sử **session** đã được cấu hình):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

CqlSession session = ...;

PreparedStatement prepared = session.prepare("""
        INSERT INTO telemetry.events_by_device
        (device_id, event_time, event_id, amount)
        VALUES (?, ?, ?, ?)
        """);

BoundStatement bound = prepared.bind(
        "device-42",
        Instant.parse("2026-11-14T08:00:00Z"),
        UUID.fromString("550e8400-e29b-41d4-a716-446655440000"),
        new BigDecimal("1390000.25")
);

session.execute(bound);
~~~

Điểm quan trọng:

- **CQL timestamp** có semantics và độ phân giải riêng; cần kiểm tra khi mapping Instant có nanosecond.
- **CQL decimal** hỗ trợ số thập phân có quy tắc khác BSON Decimal128; không suy ra hai định dạng có cùng giới hạn.
- **CQL list/set/map/UDT** đòi kiểu phần tử chính xác; Java generic và codec phải phù hợp.
- Trường trong primary key và clustering key phải giữ đúng kiểu và định dạng để query route tới partition mong muốn.

Không map mọi cột thành **String** chỉ để tránh viết codec, đặc biệt khi cần so sánh số, range query hoặc sắp xếp timestamp. Chuỗi **"100"** và **"20"** có thứ tự từ điển khác thứ tự số.

### 13.2. HBase cần quy tắc bytes rõ ràng

Trong HBase, row key, family, qualifier và value cuối cùng được biểu diễn dưới dạng byte sequence. Ứng dụng cần hợp đồng:

~~~text
Row key: deviceId + day + reverseTime + eventId
Family:  m
Qualifier: temperature
Value:   24.3 được encode bằng codec đã thống nhất
~~~

Hàm chuyển từ số sang byte phải giữ đúng cách đọc/so sánh của hệ thống. Ví dụ:

- Giá trị 64-bit có byte order cụ thể.
- Row key ghép cần độ dài từng đoạn hoặc ký tự phân cách không gây nhập nhằng.
- Nếu muốn scan theo thời gian bằng thứ tự byte, encode timestamp sao cho **lexicographic order** bảo toàn thứ tự mong muốn.
- Thay đổi encoding row key thường kéo theo migration, không chỉ thay một Java class.

**Điều quan trọng hơn lựa chọn library** là mọi producer/consumer của bảng dùng cùng một quy ước encode–decode và có test trên byte thực.

## 14. Tách domain model và persistence model khi có lợi

Một mô hình domain có thể được viết như:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record Product(
        ProductId id,
        ProductName name,
        Money price,
        Instant createdAt
) {}

public record ProductId(String value) {}
public record ProductName(String value) {}
public record Money(BigDecimal amount, String currency) {}
~~~

Domain model dùng **value object** để diễn đạt nghĩa của ID, tên và tiền. MongoDB hoặc DynamoDB không mặc nhiên biết cách lưu các kiểu này.

Một persistence document có thể đơn giản hơn:

~~~java
public record ProductDocumentV2(
        String id,
        String name,
        String amountDecimal,
        String currency,
        String createdAt,
        int schemaVersion
) {}
~~~

Ở đây lưu **amountDecimal** và **createdAt** thành String là **một lựa chọn ví dụ**, không phải khuyến nghị chung: nếu database cần query/sort/range theo giá và thời gian, kiểu native Decimal128/Date/N có thể phù hợp hơn. Hãy chọn representation dựa trên truy vấn, độ chính xác và driver.

Mapper có trách nhiệm chuyển đổi có kiểm soát:

~~~text
Domain Product
  ProductId("P-42")         → document.id = "P-42"
  Money(1390000.25, "VND")  → document.amountDecimal = "1390000.25"
  Instant(createdAt)       → document.createdAt = ISO-8601 UTC

Khi đọc:
  document.schemaVersion → chọn đường decode
  parse money và timestamp
  validate domain invariant
  dựng Product
~~~

Tách model giúp:

- Domain không phụ thuộc annotation hoặc codec của một database.
- API có thể đổi tên trường mà không phải đổi cột/index.
- Dữ liệu lịch sử có thể được upcast trước khi dựng domain.
- Phần lưu trữ biết rõ key, TTL và các trường kỹ thuật.

Đánh đổi là thêm code chuyển đổi và nhiều lớp; ứng dụng nhỏ có thể chọn mapping trực tiếp nhưng phải nắm rõ coupling.

## 15. Serialization schema là hợp đồng có phiên bản

Hệ NoSQL thường giữ dữ liệu **lâu hơn một lần deploy**. Một document được ghi bởi bản Java V1 có thể được đọc bởi V5 sau nhiều tháng. Consumer có thể chạy chậm hơn producer một hoặc vài phiên bản.

Ví dụ schema V1:

~~~json
{
  "schemaVersion": 1,
  "productId": "P-42",
  "priceVnd": 1390000
}
~~~

Schema V2:

~~~json
{
  "schemaVersion": 2,
  "productId": "P-42",
  "priceMinor": 1390000,
  "currency": "VND"
}
~~~

Đổi từ **priceVnd** sang **priceMinor + currency** là thay đổi có ngữ nghĩa. Không nên đọc V1 bằng lớp V2 rồi mặc định currency của mọi bản ghi là VND nếu thực tế dữ liệu cũ có nhiều loại tiền.

### 15.1. Ba chiến lược migration

**Read old/write new (upcaster):**

- Reader biết cách đọc V1 và V2.
- Khi nạp vào domain, chuyển V1 thành mô hình chung.
- Mọi ghi mới dùng V2.
- Có thể backfill sau để loại bỏ nợ dữ liệu cũ.

**Backfill dữ liệu trong database:**

- Duyệt các document cũ theo batch.
- Đổi schema khi có đủ bằng chứng.
- Ghi checkpoint/idempotency và theo dõi lỗi.
- Bật validator chặt khi đã xử lý dữ liệu và writer cũ.

**Dual-read/dual-write có thời hạn:**

- Hữu ích khi nhiều phiên bản reader/writer cùng tồn tại.
- Nhưng có nguy cơ hai field bất đồng; phải định nghĩa **field nào là nguồn quyết định** và cách kết thúc giai đoạn chuyển tiếp.

### 15.2. Bảng tương thích khi tiến hóa schema

| Thay đổi | Reader cũ có đọc được không? | Rủi ro |
| --- | --- | --- |
| Thêm optional field | Có thể, nếu reader cho phép field lạ | Reader strict từ chối |
| Thêm required field | Reader mới có thể không đọc dữ liệu cũ | Cần default hợp lệ hoặc migration |
| Đổi tên field | Thường là breaking nếu không alias/upcast | Reader không tìm thấy giá trị |
| Đổi kiểu number → string | Có thể breaking | Query/index và parse thay đổi |
| Đổi đơn vị VND → cent | Breaking ngữ nghĩa | Tính tiền sai dù parse thành công |
| Bổ sung enum value | Consumer cũ có thể không biết | Enum parser ném lỗi hoặc mapping sai |
| Bỏ field | Reader cũ có thể phụ thuộc field | Trường bắt buộc thành missing |
| Đổi encoding UUID/row key | Có thể không tìm lại dữ liệu | Migration hoặc dual lookup cần thiết |

Một cách làm có trách nhiệm là lưu **schemaVersion** khi cần, kiểm tra tính tương thích của **reader và writer** trước rollout, và có chiến lược đọc dữ liệu lịch sử.

## 16. Upcasting dữ liệu cũ: ví dụ Java

Giả sử hệ thống đã xác minh rằng **toàn bộ Product V1** dùng VND và không có trường tiền khác. Có thể chuyển V1 sang mô hình mới:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;

public record ProductCurrent(
        String productId,
        BigDecimal amount,
        String currency
) {}

public final class ProductUpcaster {
    public static ProductCurrent read(JsonNode node) {
        int version = node.path("schemaVersion").asInt(-1);
        String id = requiredText(node, "productId");

        return switch (version) {
            case 1 -> {
                if (!node.path("priceVnd").isIntegralNumber()) {
                    throw new IllegalArgumentException("invalid V1 price");
                }
                yield new ProductCurrent(
                        id,
                        new BigDecimal(node.get("priceVnd").asText()),
                        "VND"
                );
            }
            case 2 -> {
                if (!node.path("priceMinor").isIntegralNumber()) {
                    throw new IllegalArgumentException("invalid V2 price");
                }
                yield new ProductCurrent(
                        id,
                        new BigDecimal(node.get("priceMinor").asText()),
                        requiredText(node, "currency")
                );
            }
            default -> throw new IllegalArgumentException(
                    "unsupported schemaVersion: " + version
            );
        };
    }

    private static String requiredText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual() || value.asText().isBlank()) {
            throw new IllegalArgumentException("missing/invalid " + field);
        }
        return value.asText();
    }
}
~~~

Ở ví dụ này, **currency=VND** cho V1 là một **giả định đã được xác minh**. Nếu không chứng minh được, việc gán mặc định như vậy có thể làm dữ liệu sai ngữ nghĩa. Đồng thời, việc parse số qua **asText()** chỉ an toàn nếu đã kiểm tra kiểu và miền số theo hợp đồng; một upcaster production còn cần giới hạn giá trị, currency và kiểm tra nghiệp vụ.

### 16.1. Unknown schema version phải có hành vi rõ

Khi consumer V2 nhận **schemaVersion=3**:

- Có thể **từ chối và đưa vào DLQ** nếu không hiểu nghĩa.
- Có thể **tiếp tục đọc** nếu format đã được thiết kế và chứng minh tương thích.
- Có thể cần **triển khai reader mới trước khi producer phát V3**.

Không nên âm thầm map một event V3 thành đối tượng V2 nếu điều đó có thể làm mất trường quan trọng hoặc đổi nghĩa giá trị.

## 17. Schema của event khác schema của tài liệu đang lưu

Một hệ có thể dùng event để cập nhật bản sao:

~~~json
{
  "eventId": "evt-091",
  "eventType": "ProductPriceChanged",
  "schemaVersion": 2,
  "aggregateId": "P-42",
  "aggregateVersion": 18,
  "payload": {
    "newPriceMinor": 1390000,
    "currency": "VND"
  }
}
~~~

Có ít nhất ba loại version:

1. **Event schemaVersion:** format của thông điệp có những trường gì, kiểu gì.
2. **AggregateVersion:** thứ tự thay đổi của sản phẩm để xử lý duplicate/reorder.
3. **Persistence schemaVersion:** format của document trong database.

Ba phiên bản này **không nhất thiết giống nhau**. Một event schema V2 có thể mô tả Product aggregate version 18 và được lưu vào document schema V3.

### 17.1. Full-state và delta event có mapping khác nhau

**Full-state event** mang toàn bộ trạng thái cần thiết cho projection. Nếu version 18 đến trước 17, consumer có thể dùng **conditional upsert-if-newer** trong một số thiết kế và bỏ qua 17.

**Delta event** chỉ mang thay đổi:

~~~json
{
  "aggregateId": "inventory:SKU-8",
  "aggregateVersion": 18,
  "quantityDelta": -2
}
~~~

Nếu version 17 chưa tới, consumer **không thể nhảy thẳng** từ trạng thái 16 lên 18 trong mọi trường hợp vì có thể mất delta 17. Cần checkpoint, phát hiện gap, replay hoặc tải snapshot.

Serializer/deserializer không tự giải quyết **idempotency, thứ tự và atomicity**. Hợp đồng mapping event phải gắn với chiến lược tiêu thụ sự kiện.

## 18. Type conversion phải được kiểm soát tại ranh giới

Một số thư viện hỗ trợ **coercion** tự động:

~~~json
{
  "stock": "10",
  "active": "true",
  "priceMinor": 1390000.5
}
~~~

Những field này có thể được chuyển thành số/boolean theo cấu hình, nhưng sự tiện lợi có rủi ro:

- Chuỗi **"10"** hợp lệ ở input không có nghĩa database muốn giữ String.
- **1390000.5** không nên bị âm thầm cắt thành long 1390000 nếu đây là tiền.
- **"true"** và boolean **true** là hai kiểu JSON khác nhau.
- Một enum viết sai có thể bị đổi sang null/default và gây trạng thái không mong muốn.

Hãy xác định rõ:

- Chấp nhận coercion nào và ở API nào?
- Field nào phải đúng kiểu tuyệt đối?
- Mất precision hoặc overflow sẽ **bị từ chối** hay làm tròn theo luật nghiệp vụ?
- Có cần ghi warning/metric khi dữ liệu cũ cần chuyển kiểu?

**“Dữ liệu parse được” không tương đương “đúng kiểu và đúng nghĩa”.**

### 18.1. Enum không nên dựa vào ordinal

~~~java
enum OrderStatus {
    PENDING, CONFIRMED, CANCELLED
}
~~~

Nếu lưu enum theo **ordinal 0/1/2**, thêm một giá trị mới vào giữa có thể làm dữ liệu cũ bị hiểu thành trạng thái khác. Thường nên lưu **mã ổn định dạng chuỗi** hoặc một mã số được quản lý độc lập với thứ tự khai báo Java enum.

Khi reader gặp trạng thái mới:

- Với thao tác cần tính đúng nghiệp vụ, nên **từ chối hoặc xử lý trạng thái chưa biết** rõ ràng.
- Với UI hiển thị không quan trọng, có thể có trạng thái UNKNOWN theo hợp đồng.
- Không tự map mọi giá trị lạ thành PENDING hoặc CANCELLED.

## 19. Generic collections và nested types trong Java

Một danh sách item:

~~~json
[
  {"sku": "BOOK-1", "quantity": 2},
  {"sku": "PEN-3", "quantity": 1}
]
~~~

Khi deserialize từ JSON sang **List<OrderLine>**, cần giữ thông tin generic type, vì Java có **type erasure**:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

public record OrderLine(String sku, int quantity) {}

ObjectMapper mapper = new ObjectMapper();
String json = """
    [
      {"sku": "BOOK-1", "quantity": 2},
      {"sku": "PEN-3", "quantity": 1}
    ]
    """;

List<OrderLine> lines = mapper.readValue(
        json,
        new TypeReference<List<OrderLine>>() {}
);
~~~

Nếu parse vào raw **List.class**, bạn có thể nhận **List<Map<String,Object>>** thay vì List<OrderLine>. Sau đó phép ép kiểu thành OrderLine có thể lỗi ở runtime.

Đối với document lồng nhau, cần kiểm tra:

- Phần tử null có được phép không?
- Mảng rỗng và trường mảng missing khác nhau thế nào?
- Có giới hạn số lượng phần tử hoặc kích thước document không?
- Map key có phải String và có thể chứa ký tự đặc biệt gây khó query/index?
- Có thể phát sinh object graph đệ quy quá sâu không?

Giữ schema cho dữ liệu nested quan trọng, đừng cho rằng “document linh hoạt” có nghĩa mọi mảng/Map đều không cần validation.

## 20. Serialization và schema ảnh hưởng trực tiếp tới query/index

Hai document nhìn giống nhau trong UI nhưng khác kiểu lưu:

~~~json
{ "price": 100 }
~~~

~~~json
{ "price": "100" }
~~~

Khi truy vấn **price > 90** hoặc sort theo giá, hệ thống có thể xử lý khác nhau theo kiểu và quy tắc so sánh của engine. Dùng String cho số dễ gây thứ tự:

~~~text
"100" < "20" theo thứ tự chuỗi từ điển
100 > 20 theo thứ tự số
~~~

Với timestamp:

~~~text
"2026-11-14T08:00:00Z"
"2026-11-14T15:00:00+07:00"
~~~

cùng một thời điểm nhưng không cùng chuỗi. Nếu lưu thời điểm dưới String làm sort key, phải định nghĩa **format canonical**.

Với **partition/shard key**, serializer còn ảnh hưởng **định tuyến**:

- Hash trên bytes khác nhau có thể ra shard khác.
- **tenantId=42** dạng number khác **tenantId="42"** dạng String nếu ứng dụng/engine phân biệt.
- Một trường ngày được đổi từ chuỗi ngày sang epoch number có thể thay đổi key và phạm vi query.
- UUID binary được encode khác nhau có thể làm dữ liệu không thể tìm lại bằng ID cũ.

Vì vậy, mọi thay đổi serializer trên **field được index hoặc làm khóa** phải được xem như thay đổi **mô hình dữ liệu**, có migration và benchmark nếu cần.

## 21. Đảm bảo tính nguyên tử và tránh lost update khi mapping

Giả sử có hai writer:

~~~text
Writer A (bản cũ) đọc Product v7: id, name, price
Writer B (bản mới) thêm Product v8: searchBoost=12
Writer A serialize toàn bộ Product cũ rồi replace document
=> searchBoost biến mất dù A chỉ muốn sửa name
~~~

Đây là lỗi do **round-trip của object không đầy đủ**, không phải lỗi JSON syntax. Các biện pháp:

1. **Partial update:** chỉ sửa field cần thay đổi.
2. **Optimistic version:** cập nhật với điều kiện version vẫn đúng.
3. **Schema migration có kiểm soát:** writer cũ và mới tương thích trong rollout.
4. **Domain validation/database validation:** không chấp nhận trạng thái thiếu field bắt buộc.
5. **Quyền sở hữu field:** mỗi service chỉ được thay đổi phần dữ liệu được giao.

Ví dụ logic:

~~~text
update Product
where productId = "P-42"
  and version = 7
set name = "Bàn A", version = 8

Nếu không match → conflict/retry theo nghiệp vụ
~~~

**Không coi serializer là hệ quản lý giao dịch.** Việc chuyển một object có đúng field không ngăn hai request cùng ghi đè nhau; cần hàng rào ở điểm ghi.

## 22. Bảo mật khi deserialization dữ liệu không tin cậy

Deserialization là một ranh giới tấn công: một payload do client gửi có thể cố làm chương trình:

- Tạo object ngoài kiểu được phép.
- Cấp phát cấu trúc lồng nhau quá lớn, gây cạn RAM/CPU.
- Ghi đè field đặc quyền như **role**, **tenantId**, **balance**.
- Chấp nhận số âm, overflow hoặc chuỗi rất dài.
- Chèn trường được parser/mapper xử lý bất ngờ.

### 22.1. Không bật polymorphic deserialization tùy ý

Một số cơ chế ánh xạ kiểu đa hình cho phép payload chỉ định tên Java class cụ thể. Nếu bật **default typing** hoặc nhận class name từ JSON không tin cậy mà không có allowlist và cấu hình an toàn, hệ thống có thể phơi bày nguy cơ deserialization nghiêm trọng tùy thư viện và classpath.

Ưu tiên:

- DTO cụ thể cho từng endpoint.
- Enum/type discriminator **được phép** và mapper rõ ràng.
- Không cho payload client chọn arbitrary Java class.
- Theo dõi bản vá và phiên bản thư viện serialization.

Không dùng **ObjectInputStream** trên byte do người dùng không tin cậy cung cấp như một cách parse dữ liệu API.

### 22.2. Giới hạn tài nguyên và dữ liệu

Áp dụng giới hạn tại các lớp phù hợp:

- Kích thước request/message và kích thước document.
- Độ sâu JSON và số phần tử trong array.
- Độ dài chuỗi, regex, số lượng nhãn/field động.
- Số lớn quá phạm vi, decimal có scale/precision bất thường.
- Thời gian parse, số lượng phép chuyển đổi, decompression ratio nếu payload nén.
- Ghi log lỗi **không lộ token, mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân**.

Một deserializer trả đối tượng thành công vẫn cần **authentication, authorization và validation nghiệp vụ** trước khi ghi. Không tin một giá trị tenantId trong JSON chỉ vì nó đã map thành String hợp lệ.

## 23. Hiệu năng: không chỉ là chọn format nhỏ nhất

Serialization có chi phí CPU, cấp phát bộ nhớ, garbage collection, payload qua mạng và kích thước lưu trữ/index. Mỗi lựa chọn có đánh đổi:

| Hình thức | Ưu điểm | Chi phí cần cân nhắc |
| --- | --- | --- |
| JSON text | Dễ đọc, debug, tương thích nhiều ngôn ngữ | Key lặp, parse/allocations, schema yếu nếu không kiểm soát |
| BSON | Kiểu dữ liệu riêng cho document, thuận lợi cho MongoDB | Có kiểu/codec đặc thù; không phải thay thế mọi JSON API |
| Protobuf/Avro | Có schema, format gọn trong nhiều workload | Cần quản lý schema evolution và codegen/registry phù hợp |
| CBOR/MessagePack | Binary tree format gọn, hỗ trợ nhiều kiểu | Khó debug trực quan; schema thường vẫn cần ứng dụng quản lý |
| CQL typed columns | Type/query phù hợp storage engine | Gắn với schema và giới hạn Cassandra |
| Redis raw bytes | Linh hoạt, có thể rất gọn | Ứng dụng phải tự giữ codec/version |

Khi đo hiệu năng, đừng chỉ benchmark **ObjectMapper.writeValueAsString** trong một vòng lặp rồi kết luận API sẽ nhanh hơn:

- Bao nhiêu thời gian là network/database, bao nhiêu là serialize/deserialize?
- Dữ liệu có field dài/mảng lớn không?
- Có nén hay TLS không, và nén có tăng CPU?
- Một request serialize bao nhiêu object?
- Có tạo mapper/codec mới mỗi lần không?
- Có reflection/codegen, cache metadata hoặc allocation nhiều không?
- Có phải decode toàn bộ document khi chỉ cần vài field?

Các tối ưu thường có giá trị là **giữ payload vừa đủ, tái sử dụng mapper được cấu hình ổn định, giới hạn schema và truy vấn đúng projection**, rồi đo CPU/GC/p99 thực tế.

### 23.1. Canonicalization khi hash hoặc ký dữ liệu

Hai JSON biểu diễn cùng nội dung có thể khác chuỗi bytes:

~~~json
{"a":1,"b":2}
~~~

~~~json
{"b":2,"a":1}
~~~

Nếu hệ thống **hash raw JSON bytes** để chống trùng hoặc ký chữ ký số, hai chuỗi có thể cho hash khác nhau dù object có cùng trường và giá trị. Khi cần chữ ký hoặc hash theo nội dung, phải định nghĩa:

- Canonical serialization (thứ tự field, cách encode số/chuỗi, normalization).
- Phiên bản thuật toán và format.
- Quy tắc với field không quan trọng, null/missing và timestamp.
- Khác biệt giữa **hash nội dung** và **idempotency key** có nghĩa nghiệp vụ.

Không dựa vào thứ tự field ngẫu nhiên của Map hoặc serializer để làm hợp đồng bảo mật/hệ phân tán.

## 24. Kiểm thử round-trip và tương thích schema

Một bài test serialization cần trả lời hai câu hỏi khác nhau:

1. **Round-trip:** Giá trị Java → định dạng lưu → Java có giữ đúng nghĩa không?
2. **Compatibility:** Reader mới có đọc được dữ liệu do writer cũ ghi không, và ngược lại theo hợp đồng?

### 24.1. Bộ trường hợp kiểm thử

| Nhóm | Đầu vào | Điều phải xác minh |
| --- | --- | --- |
| Số tiền | 0, số lớn, số thập phân cần scale, số âm | Không mất precision/overflow; domain chặn sai |
| Date/time | UTC, offset khác, nano/milli boundary | Đúng instant; ghi nhận precision bị giới hạn |
| ID | UUID string/binary, ObjectId, ID dạng số lớn | Không đổi byte representation; query bằng đúng kiểu |
| Missing/null | Field vắng, null, chuỗi rỗng | Đúng hợp đồng trong DTO/PATCH |
| Enum | Giá trị cũ/mới/không biết | Không map nhầm vào trạng thái hợp lệ |
| Nested array | Rỗng, phần tử null, nhiều phần tử | Không mất kiểu generic và quy tắc phần tử |
| Unknown fields | Event chứa field mới | Chấp nhận/từ chối theo quy tắc tương thích |
| Schema V1/V2 | Bản ghi lịch sử và hiện tại | Upcaster tạo đúng domain object |
| JSON → BSON → JSON | Giá, ngày, UUID, binary | Không ngầm đổi type/precision |
| Data update | Writer cũ đọc–ghi lại document mới | Không xóa field mới ngoài dự kiến |
| Invalid payload | Quá sâu, quá lớn, sai type, số không hợp lệ | Lỗi có kiểm soát, không gây cạn tài nguyên |
| Cross-language | Java và JS/Go/Python | Cùng schema, units, timezone, byte order |

### 24.2. Ví dụ kiểm tra Jackson round-trip

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProductJsonTest {
    record Price(BigDecimal amount, String currency) {}
    record Product(String id, Price price, Instant createdAt) {}

    @Test
    void roundTripPreservesDomainValues() throws Exception {
        ObjectMapper mapper = new ObjectMapper()
                .registerModule(new JavaTimeModule());

        Product original = new Product(
                "P-42",
                new Price(new BigDecimal("1390000.25"), "VND"),
                Instant.parse("2026-11-14T08:00:00Z")
        );

        byte[] json = mapper.writeValueAsBytes(original);
        Product restored = mapper.readValue(json, Product.class);

        assertEquals(original.id(), restored.id());
        assertEquals(original.price(), restored.price());
        assertEquals(original.createdAt(), restored.createdAt());
    }
}
~~~

Đây là **unit test cho JSON/Jackson**, không chứng minh BSON Date, DynamoDB N hay CQL decimal giữ đúng kiểu khi lưu. Cần **integration test qua driver và database thật** cho những quy tắc phụ thuộc storage/codec, nhất là precision, index và kiểu ID.

### 24.3. Golden fixtures và migration tests

Giữ một bộ dữ liệu thực tế đã ẩn danh hoặc tự tạo:

~~~text
fixtures/
  product-v1.json
  product-v2.json
  event-v1.json
  event-v2.json
~~~

Mỗi lần đổi serializer/schema:

1. Reader mới phải đọc được những phiên bản cũ còn được hỗ trợ.
2. Writer mới tạo đúng format của phiên bản đã công bố.
3. Những field bắt buộc không bị rơi mất.
4. Các giá trị biên về tiền, ngày/giờ, Unicode, nhị phân và ID vẫn đúng.
5. Nếu có format mới không tương thích, phải có kế hoạch rollout/migration rõ ràng.

Golden fixture là **bằng chứng tương thích dữ liệu**, không chỉ là test code nội bộ. Đừng cập nhật tất cả fixture cùng một lúc mà bỏ mất khả năng kiểm tra bản ghi lịch sử.

## 25. Quy trình thiết kế mapping cho một entity NoSQL

Khi thêm một entity mới, có thể làm theo trình tự:

1. **Xác định nghĩa dữ liệu:** ID, giá trị, trạng thái, mốc thời gian, tiền tệ, quyền sở hữu.
2. **Liệt kê truy vấn:** đọc theo ID, range theo thời gian, lọc số, tìm kiếm, TTL.
3. **Chọn kiểu Java domain:** Instant, BigDecimal/long, UUID/String, enum, value object.
4. **Chọn kiểu và cấu trúc NoSQL:** BSON Date/Decimal128, DynamoDB N/S, CQL timestamp/decimal, Redis codec.
5. **Định nghĩa schema có phiên bản:** tên trường, required/optional, null/missing, default hợp lệ, nested structure.
6. **Tách DTO nếu cần:** chỉ nhận field client có quyền gửi; domain sở hữu field hệ thống.
7. **Thiết kế serializer/converter:** mapping không ngầm mất precision, timezone, ID representation.
8. **Xác định hành vi dữ liệu lịch sử:** alias, upcaster, backfill và unknown version.
9. **Thiết kế cập nhật an toàn:** partial update, conditional version, không replace mù.
10. **Kiểm thử round-trip và compatibility:** JSON, database driver, cache và event nếu có.
11. **Quan sát lỗi mapping:** theo dõi deserialization failure, incompatible schema, bad data và migration lag.
12. **Đo hiệu năng:** CPU, payload bytes, p95/p99 API, GC, query/index và chi phí lưu trữ.

### 25.1. Một mẫu hợp đồng dữ liệu

~~~yaml
entity: Product
schemaVersion: 2
externalApi:
  productId: string
  priceMinor: integer
  createdAt: iso8601_utc
domainJava:
  productId: ProductId
  price: Money
  createdAt: Instant
persistence:
  id: native_id_or_string_by_contract
  priceMinor: numeric_type_by_database
  createdAt: native_timestamp_or_canonical_string
fields:
  required:
    - productId
    - priceMinor
    - currency
    - createdAt
  nullable: []
compatibility:
  reads:
    - 1
    - 2
  writes: 2
  unknownFieldPolicy: define_per_boundary
concurrency:
  versionField: version
  fullReplaceAllowed: false
~~~

Đây là **tài liệu hợp đồng minh họa**, không phải một schema tool có thể chạy trực tiếp. Những placeholder như **numeric_type_by_database** phải được thay bằng kiểu và converter thật trước khi triển khai.

## 26. Bài tập thực hành: lưu và đọc đơn hàng qua NoSQL

Một hệ thống đặt hàng sử dụng Java 21 và MongoDB cho Order Store, Redis để cache chi tiết đơn, DynamoDB cho một read model theo khách hàng. API nhận:

~~~json
{
  "customerId": "C-17",
  "currency": "VND",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "unitPriceMinor": 79000},
    {"sku": "PEN-3", "quantity": 1, "unitPriceMinor": 12000}
  ],
  "requestedAt": "2026-11-14T08:00:00+00:00"
}
~~~

Yêu cầu:

- **orderId** do server tạo và không thay đổi qua retry của cùng thao tác.
- **requestedAt** là thời gian client đề nghị; **createdAt** do server chốt.
- **quantity** là số nguyên dương; **unitPriceMinor** không âm.
- Tổng tiền được tính chính xác theo đơn vị nhỏ nhất; không dùng double.
- Order có **schemaVersion** và **version** để hỗ trợ migration và concurrency.
- Cache có TTL, nhưng không được dùng cache stale làm nguồn quyết định thanh toán.
- Trong tương lai có thể thêm **discountMinor** và **taxMinor**.

### Phần A — Thiết kế Java DTO và domain

Hãy đề xuất:

~~~text
CreateOrderRequest:
    customerId, currency, items, requestedAt

OrderItem:
    sku, quantity, unitPriceMinor

Order:
    orderId, customerId, createdAt, requestedAt,
    items, totalMinor, status, version
~~~

Chọn kiểu Java cho từng trường. Tại sao **createdAt** nên dùng Instant? Tại sao không nên cho client điền **totalMinor, status, version** rồi ghi trực tiếp mà không kiểm tra?

### Phần B — Mapping sang MongoDB

Đề xuất document:

~~~json
{
  "_id": "O-901",
  "schemaVersion": 2,
  "version": 1,
  "customerId": "C-17",
  "currency": "VND",
  "createdAt": "<BSON Date>",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "unitPriceMinor": 79000},
    {"sku": "PEN-3", "quantity": 1, "unitPriceMinor": 12000}
  ],
  "totalMinor": 170000,
  "status": "PENDING"
}
~~~

Chuỗi **<BSON Date>** ở đây là ký hiệu minh họa: JSON thuần không biểu diễn trực tiếp kiểu BSON Date, và document thực cần lưu giá trị có kiểu date do driver serialize. Hãy chỉ ra bộ quy tắc validator/type tương ứng và một thao tác update có điều kiện theo version.

### Phần C — Cache và read model

Đề xuất khóa Redis chứa version hoặc payload có **schemaVersion**:

~~~text
redis key: order:v2:O-901
value: JSON bytes với schemaVersion=2
TTL: 300 giây
~~~

Đọc từ Redis cần thực hiện những bước nào nếu JSON sai kiểu hoặc thuộc schemaVersion chưa hỗ trợ? Khi chuyển codec cache từ JSON sang binary, làm thế nào để tránh reader V2 đọc nhầm bytes V1?

Với DynamoDB read model theo customer:

~~~text
PK = CUSTOMER#C-17
SK = ORDER#2026-11-14T08:00:00.000Z#O-901
~~~

Hãy giải thích cách đảm bảo **thời gian được encode nhất quán**, vì sao ID khách hàng và orderId trong khóa phải có quy ước escape và vì sao read model có thể trễ sau khi Order Store commit.

### Phần D — Schema evolution

Order V1 chưa có discountMinor. Order V2 thêm discountMinor và taxMinor. Hãy:

1. Xác định khi nào **default=0** là hợp lệ về nghiệp vụ.
2. Viết một upcaster đọc V1 và V2.
3. Giải thích cách reader cũ xử lý field mới.
4. Chỉ ra rủi ro khi writer V1 **replace** toàn bộ Order V2.
5. Phác thảo kế hoạch **Expand → Migrate → Enforce**.

### Phần E — Kiểm thử

Lập test matrix cho:

- Tổng tiền có nhiều item, overflow và số âm.
- Instant có offset, thời gian sát biên mili giây.
- Missing/null/empty và field không biết.
- Đọc record V1 qua reader V2.
- Lưu BSON rồi đọc lại, kiểm tra kiểu date và số.
- Decode Redis bytes cũ/bytes sai.
- Retry cùng operationId không tạo hai đơn.
- Hai writer cạnh tranh cùng version không ghi đè nhau.

**Gợi ý hướng giải:** DTO chỉ chứa field được client phép nhập; domain tính **2 × 79.000 + 1 × 12.000 = 170.000** bằng phép toán nguyên an toàn, kiểm tra quantity và lưu snapshot giá đã chốt. MongoDB lưu kiểu BSON được khai báo rõ; Redis lưu payload có version hoặc version trong key; DynamoDB read model dùng AttributeValue và sort key theo quy tắc thời gian nhất quán. Khi đọc, decoder có thể xử lý schema cũ qua upcaster, nhưng quyết định thanh toán và chống ghi đè vẫn cần **điểm ghi có thẩm quyền, cập nhật có điều kiện và idempotency**.

**Kết luận:** Serialization và deserialization trong NoSQL không chỉ là chuyển JSON thành Java object rồi chuyển ngược lại. Chúng là phần thực thi của **hợp đồng dữ liệu xuyên API, domain, database, cache và event**. Mapping tốt phải giữ **ý nghĩa, kiểu, độ chính xác, thời gian, định danh, null/missing, phiên bản schema và điều kiện cập nhật**. Chọn format nào cũng cần kiểm thử round-trip với dữ liệu lịch sử và driver thực tế, đồng thời bảo vệ ranh giới đầu vào để hệ thống **đọc được dữ liệu cũ mà không âm thầm làm sai dữ liệu mới**.
