# Cú pháp so sánh và toán tử logic theo tập con SQL trong JMS Message Selector

> **Chủ đề:** Lọc thông điệp trong Spring Framework JMS (Jakarta Messaging).  
> **Mục tiêu:** Viết được selector dùng toán tử so sánh `=`, `<>`, `<`, `<=`, `>`, `>=`; toán tử logic `AND`, `OR`, `NOT`; dấu ngoặc, logic ba giá trị, `IS NULL`, `BETWEEN`, `IN` và `LIKE`. Hiểu giới hạn của cú pháp SQL92 subset và áp dụng đúng qua `JmsTemplate` hoặc `@JmsListener`.

**Phiên bản ví dụ:** Java 17+, Spring Framework 6.x, Spring Boot 3.5.x, Jakarta Messaging 3.1 (`jakarta.jms`) và Apache ActiveMQ Artemis. Bài tập trung vào **JMS message selector**, không phải JDBC, Spring Data JPA hay một truy vấn SQL chạy trên database.

## 1. Message selector lọc điều gì?

JMS cho phép consumer chỉ nhận những message mà biểu thức lọc trên **JMS headers và JMS message properties** đánh giá thành **TRUE**. Chẳng hạn:

~~~sql
region = 'APAC' AND score >= 8 AND urgent = TRUE
~~~

Một message có `region='APAC'`, `score=9`, `urgent=true` sẽ khớp. Nếu `region='EU'` hoặc `score=4`, message không khớp. Đặc biệt, nếu property không có, selector có thể cho **UNKNOWN**, cũng **không khớp**.

~~~text
 Producer gửi TextMessage + JMS properties
                |
                v
         Queue / Topic broker
                |
        Message selector
        +----------------+
        | TRUE?          |
        +-------+--------+
           YES  |   NO (FALSE/UNKNOWN)
                |
     Consumer phù hợp
~~~

**Không nhầm các lớp dữ liệu:**
- **JMS header:** ví dụ `JMSPriority`, `JMSType`, `JMSCorrelationID`.
- **JMS property:** ví dụ `region`, `score`, `urgent`, do producer đặt bằng `setStringProperty`, `setIntProperty`, `setBooleanProperty`.
- **Message body:** JSON/XML/String/object bytes; **selector chuẩn không phân tích body**.

Ví dụ, body JSON:

~~~json
{"region":"APAC","score":9,"urgent":true}
~~~

**không đủ** để selector `region = 'APAC'` hoạt động. Producer còn phải đặt các JMS properties tương ứng, hoặc ứng dụng phải chọn routing topology/consumer-side parsing phù hợp.

### Producer đặt property

~~~java
// Mảnh code Java trong callback MessageCreator có jakarta.jms.Session.
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-7\"}");
message.setStringProperty("region", "APAC");
message.setIntProperty("score", 9);
message.setBooleanProperty("urgent", true);
return message;
~~~

Đoạn trên minh họa API, chưa phải file Java độc lập; `session` do Spring/JMS cung cấp khi tạo message.

**Ý nghĩa đúng:** chỉ message khớp được giao cho **consumer đang dùng selector đó**. Một message không khớp không tự bị xóa khỏi queue; nó vẫn có thể chờ consumer phù hợp hoặc bị ảnh hưởng bởi TTL, retention và các consumer khác. Với Topic, chính sách subscription/durability còn quyết định có giữ lại message hay không.

## 2. Tại sao cú pháp giống SQL nhưng không phải SQL đầy đủ?

Jakarta Messaging định nghĩa selector là một `String` có cú pháp dựa trên **tập con SQL92 conditional expressions**. Không có các cấu phần của một câu truy vấn database như `SELECT`, `FROM`, `JOIN`, subquery, `ORDER BY` hoặc hàm JSON/regex chung.

Một selector đúng:

~~~sql
(orderState = 'READY' AND amountMinor >= 10000)
OR (urgent = TRUE AND region = 'VN')
~~~

Một câu `SELECT * FROM ... WHERE ...` **không** phải selector đúng. JMS provider kiểm tra cú pháp selector khi consumer đăng ký; syntax sai phải gây lỗi JMS (Spring thường bọc thành `JmsException`). Tuy nhiên, selector **đúng cú pháp** nhưng tên property sai hoặc giá trị sai kiểu có thể chỉ không khớp, không báo exception.

### Các thành phần

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Identifier | `region`, `amountMinor`, `JMSPriority` | Tham chiếu header/property |
| String literal | `'APAC'`, `'READY'` | Chuỗi cần so sánh |
| Numeric literal | `8`, `-10`, `2.5` | Số nguyên hoặc gần đúng |
| Boolean literal | `TRUE`, `FALSE` | Giá trị logic |
| Comparison | `=`, `<>`, `>`, `>=`, `<`, `<=` | Tạo kết quả điều kiện |
| Logic | `NOT`, `AND`, `OR` | Kết hợp hoặc phủ định điều kiện |
| Grouping | `( ... )` | Quy định thứ tự |
| Special predicates | `IS NULL`, `BETWEEN`, `IN`, `LIKE` | Các phép so sánh mở rộng |

### Phân biệt hoa/thường

- Các từ khóa `AND`, `OR`, `NOT`, `TRUE`, `FALSE`, `LIKE`... **không phân biệt** chữ hoa/thường.
- **Tên property/identifier có phân biệt**: `Region` khác `region`.
- **Chuỗi literal có phân biệt**: `'APAC'` khác `'apac'`, `'US'` khác `'US '`.

Thống nhất property name và kiểu/giá trị trong contract giữa producer–consumer, không đoán qua tên message body.

## 3. Các literal và quy tắc đặt tên

### 3.1. Chuỗi trong dấu nháy đơn

~~~sql
region = 'APAC'
eventType = 'InvoiceCreated'
customerName = 'O''Reilly'
~~~

JMS dùng **nháy đơn** cho String. Dấu nháy đơn bên trong được escape bằng **hai dấu nháy đơn**: `'O''Reilly'` có giá trị là `O'Reilly`.

Khi viết Java String:

~~~java
String selector = "region = 'APAC' AND urgent = TRUE";
String withQuote = "customerName = 'O''Reilly'";
~~~

Không dùng `"APAC"` để viết String literal theo JMS selector chuẩn. Java escaping và SQL-style literal escaping là **hai tầng khác nhau**.

### 3.2. Numeric literals

~~~sql
quantity >= 10
temperature <= -2.5
totalMinor > 100000
delta <> 0
~~~

Số nguyên chính xác không có dấu thập phân, trong phạm vi `long`; số gần đúng có dấu thập phân hoặc scientific notation (`7E3`). So sánh giữa các kiểu số áp dụng numeric promotion Java theo đặc tả. JMS **không** có loại fixed SQL DECIMAL trong selector; nếu giá tiền quan trọng, nên dùng property kiểu `long` ở minor units, đồng nhất đơn vị và giới hạn tràn số.

### 3.3. Boolean literals

~~~sql
urgent = TRUE
enabled <> FALSE
NOT (active = FALSE)
~~~

`TRUE` là Boolean, không phải chuỗi `'true'`. Producer đúng kiểu:

~~~java
message.setBooleanProperty("urgent", true);
message.setIntProperty("score", 9);
message.setStringProperty("region", "APAC");
~~~

Nếu producer dùng `setStringProperty("urgent","true")`, so sánh `urgent = TRUE` **không tự convert** thành Boolean. Phải sửa type của property hoặc hợp đồng selector.

### 3.4. NULL

Property chưa được đặt được xem là `NULL` trong selector. `NULL` không giống String `'NULL'`, chuỗi rỗng `''` hay Boolean `FALSE`. So sánh thông thường với NULL tạo **UNKNOWN**, không phải TRUE hoặc FALSE. Để kiểm tra thiếu property, dùng:

~~~sql
region IS NULL
region IS NOT NULL
~~~

### 3.5. Identifier và từ dành riêng

Tên property thường phải theo quy tắc identifier kiểu Java, ví dụ `region`, `orderId`, `tenantId`, `_type`. Tránh tên có dấu gạch ngang/dấu cách hoặc từ khóa `NOT`, `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`, `IS`, `ESCAPE`, `NULL`, `TRUE`, `FALSE`.

Các prefix `JMSX` được dành cho JMS-defined properties, `JMS_` dành cho provider-specific properties. Application properties nên có namespace/naming convention rõ, không lạm dụng các prefix dành riêng.

## 4. Sáu toán tử so sánh

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=` | Bằng | `region = 'VN'` |
| `<>` | Khác | `state <> 'DONE'` |
| `>` | Lớn hơn | `score > 8` |
| `>=` | Lớn hơn hoặc bằng | `score >= 8` |
| `<` | Nhỏ hơn | `attempts < 3` |
| `<=` | Nhỏ hơn hoặc bằng | `amountMinor <= 100000` |

**Dùng `<>` thay `!=`** khi muốn selector portable. Một broker có thể hỗ trợ `!=` như extension; đặc tả JMS không yêu cầu.

**Hạn chế kiểu:** String và Boolean chỉ hỗ trợ `=` và `<>`, không so sánh thứ tự bằng `>` hoặc `<`. So sánh String dựa trên chuỗi ký tự chính xác; đừng dựa vào thứ tự từ vựng kiểu SQL collation.

### Sai kiểu thường gặp

~~~java
message.setStringProperty("score", "9"); // String, không phải int
~~~

Selector:

~~~sql
score >= 8
~~~

không khớp theo semantics chuẩn. Dù một số getter JMS có khả năng chuyển String thành số, **những chuyển đổi của property getter không được áp dụng trong selector**. So sánh không cùng kiểu tạo FALSE; nếu một vế là NULL thì UNKNOWN.

Ví dụ cần test để tránh sai lệch:
- `setIntProperty("score",9)` khớp `score >= 8`.
- `setStringProperty("score","9")` không khớp `score >= 8`.
- `setStringProperty("region","APAC")` khớp `region = 'APAC'`.
- `setBooleanProperty("active",true)` khớp `active = TRUE`.
- `setStringProperty("active","true")` không khớp `active = TRUE`.

**Lưu ý với phủ định:** Khi mismatch kiểu tạo FALSE, việc bọc `NOT(...)` có thể biến FALSE thành TRUE. Đừng dựa vào selector một mình để validate schema; consumer cần kiểm tra message properties/schema ở tầng ứng dụng nữa.

## 5. AND, OR và NOT

### AND — cả hai điều kiện đều đúng

~~~sql
region = 'APAC' AND score >= 8
~~~

Nếu region đúng nhưng score thấp, kết quả FALSE. Dùng AND cho quy tắc nhiều ràng buộc cùng bắt buộc.

### OR — ít nhất một điều kiện đúng

~~~sql
region = 'APAC' OR region = 'EU'
~~~

Một trong hai đúng sẽ khiến toàn biểu thức TRUE. Cẩn thận khi OR kết hợp AND: nếu không có ngoặc, có thể lọc **rộng hơn** hợp đồng.

### NOT — phủ định điều kiện

~~~sql
NOT (state = 'DONE')
~~~

Với state READY, kết quả TRUE. Với DONE, FALSE. Nhưng với property state **không tồn tại**, `state = 'DONE'` là UNKNOWN, và `NOT UNKNOWN` vẫn UNKNOWN — message không được chọn.

Muốn chọn cả message thiếu state:

~~~sql
state IS NULL OR state <> 'DONE'
~~~

Không viết `state != 'DONE'` nếu bạn cần tương thích giữa các broker. Không nghĩ `NOT` biến NULL thành TRUE.

## 6. Thứ tự ưu tiên và dấu ngoặc

Mức ưu tiên của toán tử logic (cao đến thấp):

1. `NOT`
2. `AND`
3. `OR`

Các toán tử so sánh tạo ra điều kiện để logic kết hợp. Những phần ở cùng mức ưu tiên được xử lý từ trái sang phải theo cú pháp chuẩn. **Cách an toàn là viết dấu ngoặc tường minh** cho mọi điều kiện có cả AND lẫn OR.

Ví dụ thiếu ngoặc:

~~~sql
region = 'APAC' AND score >= 8 OR urgent = TRUE
~~~

được hiểu:

~~~sql
(region = 'APAC' AND score >= 8) OR urgent = TRUE
~~~

Vậy một message `region='EU', urgent=TRUE` vẫn khớp. Nếu yêu cầu là “chỉ APAC và (điểm cao hoặc khẩn)”, viết:

~~~sql
region = 'APAC' AND (score >= 8 OR urgent = TRUE)
~~~

| region | score | urgent | Không ngoặc | Có ngoặc |
| --- | ---: | --- | --- | --- |
| APAC | 9 | FALSE | TRUE | TRUE |
| APAC | 3 | TRUE | TRUE | TRUE |
| EU | 9 | TRUE | **TRUE** | **FALSE** |
| EU | 9 | FALSE | FALSE | FALSE |

Đây là lỗi **hợp đồng**, không phải syntax error: provider vẫn chấp nhận và consumer có thể nhận message ngoài phạm vi ý định.

### NOT trên một nhóm

~~~sql
NOT (region = 'APAC' OR region = 'EU')
~~~

khác với:

~~~sql
NOT (region = 'APAC') OR region = 'EU'
~~~

Tương tự, `a = 1 AND (b = 2 OR c = 3)` khác `(a = 1 AND b = 2) OR c = 3`. Test các tổ hợp quan trọng, nhất là khi một property có thể thiếu.

## 7. Logic ba giá trị: TRUE, FALSE và UNKNOWN

JMS dùng logic kiểu SQL92 trên giá trị NULL. Một biểu thức có thể cho **TRUE (T)**, **FALSE (F)** hoặc **UNKNOWN (U)**. JMS **chỉ chọn message khi toàn bộ selector là TRUE**; FALSE và UNKNOWN đều không khớp.

### 7.1. Bảng AND

| AND | T | F | U |
| --- | --- | --- | --- |
| T | T | F | U |
| F | F | F | F |
| U | U | F | U |

Nếu `region` thiếu, `score=3`:
- `region = 'APAC'` là U.
- `score >= 8` là F.
- `U AND F` thành **F**.

### 7.2. Bảng OR

| OR | T | F | U |
| --- | --- | --- | --- |
| T | T | T | T |
| F | T | F | U |
| U | T | U | U |

Nếu region thiếu nhưng urgent=TRUE:
- `region = 'APAC'` là U.
- `urgent = TRUE` là T.
- `U OR T` thành **T**, nên message vẫn được chọn.

### 7.3. Bảng NOT

| A | NOT A |
| --- | --- |
| T | F |
| F | T |
| U | U |

`NOT (region = 'APAC')` không chọn message thiếu region vì `NOT U = U`. Dùng `region IS NULL OR region <> 'APAC'` nếu hợp đồng muốn bao gồm trường hợp thiếu.

### 7.4. Ma trận ứng dụng

| Dữ liệu | Selector | Kết quả | Khớp? |
| --- | --- | --- | --- |
| state=DONE | `state <> 'DONE'` | F | Không |
| state=READY | `state <> 'DONE'` | T | Có |
| state thiếu | `state <> 'DONE'` | U | Không |
| state thiếu | `NOT (state = 'DONE')` | U | Không |
| state thiếu | `state IS NULL` | T | Có |
| state thiếu | `state IS NOT NULL` | F | Không |
| state thiếu, urgent=true | `state = 'READY' OR urgent = TRUE` | T | Có |
| state thiếu, urgent=false | `state = 'READY' OR urgent = TRUE` | U | Không |

**Bài học:** Đừng viết điều kiện dạng phủ định rồi mặc định mọi message thiếu field được chọn. NULL phải được xử lý **có chủ đích**.

## 8. IS NULL và IS NOT NULL

~~~sql
trackingId IS NULL
trackingId IS NOT NULL
region IS NULL OR region = 'APAC'
~~~

`IS NULL` cho TRUE nếu property thiếu/NULL; `IS NOT NULL` cho TRUE khi hiện diện và không NULL.

Nếu producer gửi `setStringProperty("region", "")`, region là **chuỗi rỗng**, không phải NULL. Muốn lọc cả rỗng:

~~~sql
region IS NULL OR region = ''
~~~

Ví dụ contract versioning: message v1 không có `schemaVersion`; message v2 có. **Chỉ khi hợp đồng v1 quy định thiếu version là v1**, selector mới nên viết:

~~~sql
schemaVersion IS NULL OR schemaVersion = 1
~~~

Nếu thiếu version là sai giao thức, đừng tự diễn giải là v1: hãy dùng validator và quarantine/DLQ.

## 9. BETWEEN và NOT BETWEEN

`BETWEEN` kiểm tra **khoảng số đóng hai đầu**:

~~~sql
score BETWEEN 5 AND 9
~~~

Tương đương:

~~~sql
score >= 5 AND score <= 9
~~~

Giá trị 5 và 9 **đều** khớp. `NOT BETWEEN` chọn các giá trị ngoài khoảng:

~~~sql
score NOT BETWEEN 5 AND 9
~~~

có ý nghĩa tương tự `score < 5 OR score > 9`. Nếu score thiếu, phép so sánh có UNKNOWN; muốn bao gồm thiếu, cần:

~~~sql
score IS NULL OR score NOT BETWEEN 5 AND 9
~~~

Không dùng BETWEEN để xếp thứ tự String theo chữ cái: String comparisons portable chỉ có `=` và `<>`.

Các mốc thời gian có thể biểu diễn như property numeric `eventTimeMillis` với kiểu `long`, rồi dùng range. Đó là số milliseconds từ epoch theo contract, **không phải** literal `DATE '2026-10-30'` của SQL database.

## 10. IN và NOT IN: danh sách chuỗi

Trong JMS selector chuẩn, `IN` được định nghĩa với một String identifier (hoặc NULL) và một **danh sách String literals**:

~~~sql
region IN ('VN', 'TH', 'SG')
state NOT IN ('DONE', 'CANCELLED')
~~~

`region IN ('VN','TH','SG')` tương đương các phép OR equality trên region.

**Không portable:**

~~~text
score IN (1, 2, 3)  // JMS IN không hỗ trợ danh sách số
region IN ()        // Danh sách rỗng không hợp lệ
region IN ('VN', 2)  // Không trộn String và số
~~~

Thay numeric IN bằng:

~~~sql
score = 1 OR score = 2 OR score = 3
~~~

Nếu region thiếu, `region IN (...)` và `region NOT IN (...)` đều cho UNKNOWN, không tự chọn. Với hợp đồng cho phép thiếu region:

~~~sql
region IS NULL OR region NOT IN ('VN', 'TH', 'SG')
~~~

## 11. LIKE, NOT LIKE và ESCAPE

`LIKE` áp dụng cho String property; pattern dùng:

- `%` — khớp **0 hoặc nhiều** ký tự.
- `_` — khớp **đúng 1** ký tự.

~~~sql
eventType LIKE 'Invoice%'
clientId LIKE 'web_'
correlationId NOT LIKE 'test-%'
~~~

| Giá trị | Điều kiện | Kết quả |
| --- | --- | --- |
| InvoiceCreated | `eventType LIKE 'Invoice%'` | TRUE |
| Invoice | `eventType LIKE 'Invoice%'` | TRUE vì % có thể rỗng |
| InvoiceX | `eventType LIKE 'Invoice_'` | TRUE |
| InvoiceXY | `eventType LIKE 'Invoice_'` | FALSE |
| web1 | `clientId LIKE 'web_'` | TRUE |
| web12 | `clientId LIKE 'web_'` | FALSE |

Để tìm một dấu `_` thực sự, dùng `ESCAPE`:

~~~sql
clientId LIKE 'A!_%' ESCAPE '!'
~~~

Ý nghĩa: prefix literal `A_`, sau đó là bất kỳ chuỗi nào. Message `clientId='A_blue'` khớp, `clientId='Ablue'` không. Chọn `!` thay vì backslash giúp tránh sự chồng chéo giữa escaping của Java String và selector.

`LIKE` **không phải** Java regex: `.*`, `[0-9]`, `^`, lookahead không có ý nghĩa regex tại đây. `LIKE '%suffix'` trên backlog lớn có thể tốn công đánh giá, tùy broker/index. Nếu property thiếu thì `LIKE`/`NOT LIKE` thành UNKNOWN.

## 12. Số học và những giới hạn của SQL subset

Selector hỗ trợ toán tử số học:

~~~sql
(quantity * unitPriceMinor) >= 100000
temperature + offset < 40
(score - penalty) >= 7
~~~

Độ ưu tiên trong số học: `+`/`-` đơn ngôi, rồi `*`/`/`, rồi `+`/`-` nhị ngôi. Dùng dấu ngoặc để tránh hiểu sai; numeric promotion dùng quy tắc Java. Tránh dựa vào behavior ở trường hợp overflow, chia cho 0, độ chính xác thập phân hoặc giá trị property thiếu.

Các biểu thức **không** thuộc chuẩn JMS selector:

~~~text
SELECT * FROM messages WHERE region = 'VN'
WHERE region = 'VN'
score != 8
LOWER(region) = 'vn'
CAST(score AS INTEGER) > 8
JSON_VALUE(body, '$.region') = 'VN'
ORDER BY score DESC
score > 8 -- SQL comment
~~~

Một số vendor có extensions riêng cho XPath/JSON hoặc string conversion, nhưng **không được giả định là tính năng chuẩn**. Khi cần portable behavior, chỉ dùng JMS selector grammar đã định nghĩa.

## 13. Các JMS headers được phép tham chiếu

Theo Jakarta Messaging 3.1, bộ header tham chiếu trực tiếp trong selector chỉ bao gồm:

| Header | Ví dụ |
| --- | --- |
| `JMSDeliveryMode` | `JMSDeliveryMode = 'PERSISTENT'` |
| `JMSPriority` | `JMSPriority >= 7` |
| `JMSMessageID` | `JMSMessageID = 'ID:...'` |
| `JMSTimestamp` | `JMSTimestamp >= 1761868800000` |
| `JMSCorrelationID` | `JMSCorrelationID = 'req-123'` |
| `JMSType` | `JMSType = 'OrderPlaced'` |

Cảnh báo:
- `JMSDeliveryMode` ở **selector** được xem như String `'PERSISTENT'` hoặc `'NON_PERSISTENT'`, **không** dùng `JMSDeliveryMode=2` dù Java API có enum/hằng số số nguyên.
- `JMSPriority` so sánh như số.
- `JMSMessageID`, `JMSCorrelationID` và `JMSType` có thể NULL.
- `JMSRedelivered` và `JMSExpiration` **không thuộc sáu header selector chuẩn**. Broker có thể có extension nhưng không portable.
- `JMSXGroupID`/`JMSXDeliveryCount` là properties theo quy tắc riêng, không phải JMS header có thể so sánh tùy ý; provider-defined receive-time properties có hạn chế portability.

Thông thường, lọc nghiệp vụ nên dùng application properties như `eventType`, `region`, `tenantId` thay vì khóa cứng vào những giá trị message IDs do provider sinh ra.

## 14. Áp dụng với Spring JmsTemplate

Spring `JmsTemplate` cung cấp `receiveSelected` và `receiveSelectedAndConvert`:

~~~java
// Mảnh code Java trong Spring bean có JmsTemplate template.
template.setReceiveTimeout(2_000L);

Message raw = template.receiveSelected(
        "orders.in",
        "region = 'APAC' AND score >= 8");

Object payload = template.receiveSelectedAndConvert(
        "orders.in",
        "region = 'EU' AND urgent = TRUE");
~~~

Hai lời gọi trên **là hai lần nhận riêng**, không phải hai cách đọc cùng một message. `receiveSelected` trả `jakarta.jms.Message` hoặc `null`; `receiveSelectedAndConvert` gọi converter để trả Java object (thường String với `TextMessage` và `SimpleMessageConverter` mặc định).

**Đều là blocking receive:** với queue còn message không khớp, consumer vẫn có thể đợi tới timeout rồi trả null. Mặc định cấu hình nhận có thể chờ vô thời hạn nếu không đặt timeout. Không dùng polling loop không nghỉ hoặc request HTTP đồng bộ không deadline.

### @JmsListener(selector=...)

~~~java
@Component
public class RegionalListener {

    @JmsListener(
        destination = "orders.in",
        selector = "region = 'APAC' AND score >= 8")
    public void process(String orderId) {
        System.out.println("APAC=" + orderId);
    }
}
~~~

Đây là mảnh Spring class; cần import `@Component`, `@JmsListener`, có listener infrastructure/connection factory đã cấu hình và consumer không bị tranh chấp ngoài ý muốn. Khi dùng `@JmsListener`, selector được gắn vào listener container; Spring quản lý tạo JMS consumer, transaction/retry/lifecycle.

### Jakarta Messaging API trực tiếp

~~~java
String selector = "region = 'APAC' AND score >= 8";
MessageConsumer consumer =
        session.createConsumer(destination, selector);
~~~

Đây là mảnh code; cần `jakarta.jms.Session`, `Destination`, `MessageConsumer` và đóng tài nguyên đúng chủ sở hữu. Đặc tả yêu cầu provider xác minh syntax khi consumer được tạo; với Spring, lỗi checked JMS thường được chuyển thành Spring `JmsException`.

### Queue và Topic cần hiểu khác nhau

Với **Queue**, một message được giao cho một consumer phù hợp; nếu có nhiều consumer cạnh tranh (kể cả consumer không selector), không có cơ chế broadcast mỗi nhóm một bản. Với **Topic**, selector thuộc về subscription; các subscriber khác nhau có thể nhận bản riêng nếu topology và thời điểm subscription phù hợp. Durable subscription và message retention/TTL quyết định khả năng nhận khi subscriber offline.

**Một selector không phải cơ chế cấp quyền:** nếu cần cách ly tenant, vẫn phải có broker ACL, identity, destination policy và kiểm tra tenant ở business layer.

## 15. Lab chạy được: Spring Boot 3.5 + Java 17 + Artemis

Mục tiêu: gửi bốn message vào queue `selector.demo`, dùng các biểu thức khác nhau để lần lượt nhận **đúng một message**, quan sát `IS NULL`, numeric/Boolean property types, và sự khác nhau giữa `receiveSelected`/`receiveSelectedAndConvert`.

### 15.1. Khởi tạo project

Tại https://start.spring.io/ chọn:
- Maven, Java 17, Spring Boot **3.5.x**.
- Group `com.example`, artifact `jms-selector-lab`.
- Package `com.example.jmsselector`.
- Dependency `spring-boot-starter-artemis` (Spring for Apache ActiveMQ Artemis).

Thêm broker nhúng vào `pom.xml` có Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Đây là một dependency **bổ sung**, không phải `pom.xml` độc lập. Dùng version Artemis do BOM của Boot quản lý.

### 15.2. Cấu hình

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-selector-lab
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=selector.demo
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Vì lab **không có `@JmsListener`**, không cần `@EnableJms`; Boot cung cấp `JmsTemplate` khi starter và broker embedded được cấu hình thành công.

### 15.3. Java code hoàn chỉnh

File `src/main/java/com/example/jmsselector/JmsSelectorLabApplication.java`:

~~~java
package com.example.jmsselector;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsSelectorLabApplication {

    private static final String QUEUE = "selector.demo";

    public static void main(String[] args) {
        SpringApplication.run(JmsSelectorLabApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(JmsTemplate template) {
        return args -> {
            template.setReceiveTimeout(1_500L);

            send(template, "APAC-HIGH", "APAC", 9, true);
            send(template, "EU-HIGH", "EU", 9, true);
            send(template, "APAC-LOW", "APAC", 4, false);
            send(template, "NO-REGION", null, 9, true);

            System.out.println("HIGH=" + receiveText(
                    template,
                    "region = 'APAC' AND score >= 8 AND urgent = TRUE"));

            System.out.println("MISSING=" + receiveText(
                    template,
                    "region IS NULL"));

            System.out.println("EU=" + receiveText(
                    template,
                    "region = 'EU'"));

            Object low = template.receiveSelectedAndConvert(
                    QUEUE, "region = 'APAC' AND score < 8");
            System.out.println("LOW=" + low);

            System.out.println("EMPTY=" + receiveText(
                    template,
                    "score >= 0"));
        };
    }

    private static void send(
            JmsTemplate template,
            String body,
            String region,
            int score,
            boolean urgent) {

        template.send(QUEUE, session -> {
            TextMessage message = session.createTextMessage(body);
            if (region != null) {
                message.setStringProperty("region", region);
            }
            message.setIntProperty("score", score);
            message.setBooleanProperty("urgent", urgent);
            return message;
        });
    }

    private static String receiveText(
            JmsTemplate template,
            String selector) throws JMSException {

        Message message = template.receiveSelected(QUEUE, selector);
        if (message == null) {
            return "null";
        }
        if (!(message instanceof TextMessage text)) {
            throw new IllegalStateException(
                    "Expected TextMessage");
        }
        return text.getText();
    }
}
~~~

**Vì sao output được kiểm soát?**
- `APAC-HIGH` là message duy nhất có `region='APAC', score>=8, urgent=TRUE`.
- `NO-REGION` là message duy nhất thiếu property `region`, nên khớp `region IS NULL`.
- `EU-HIGH` khớp `region='EU'`.
- `APAC-LOW` còn lại khớp `region='APAC' AND score<8`.
- Queue sau đó trống; gọi `receiveSelected` thêm lần nữa chờ tối đa khoảng 1,5 giây rồi trả `null`.
- Không có listener cạnh tranh, không dựa trên thứ tự FIFO giữa các messages với selector khác nhau.
- Converter mặc định của `JmsTemplate` trả String cho TextMessage qua `receiveSelectedAndConvert`; lab không đăng ký custom converter.

### 15.4. Chạy

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Bỏ qua log framework/broker, các dòng do ứng dụng in theo thứ tự:

~~~text
HIGH=APAC-HIGH
MISSING=NO-REGION
EU=EU-HIGH
LOW=APAC-LOW
EMPTY=null
~~~

**Điều lab chứng minh:** filter trên properties và logic `IS NULL`, cách sử dụng Spring JmsTemplate. **Điều chưa chứng minh:** exactly-once business effect, redelivery, broker persistence/HA, độ trễ selector tải lớn, durable Topic subscription. Nếu có broker khác hoặc consumer khác cạnh tranh, cần dùng môi trường test mới và xác minh broker metrics.

### 15.5. Các thay đổi để tự thử

1. Đổi `setIntProperty("score",score)` thành `setStringProperty("score", Integer.toString(score))` và quan sát `score >= 8` không còn khớp.
2. Chọn riêng `NOT (region = 'APAC')` đối với NO-REGION: kết quả UNKNOWN. Dùng `region IS NULL OR region <> 'APAC'` để chọn cả thiếu.
3. Thêm message region EU, score 2, urgent true. So sánh `region='APAC' AND score>=8 OR urgent=TRUE` với `region='APAC' AND (score>=8 OR urgent=TRUE)`; biểu thức thiếu ngoặc có thể chọn EU.
4. Dùng `clientId LIKE 'A!_%' ESCAPE '!'` với các message `A_blue`/`Ablue` để kiểm tra wildcard literal.
5. Thử một selector sai syntax trong queue test; ghi nhận lỗi khi consumer được tạo, không gửi nó lên môi trường chung.

Không thử hai selector nối tiếp trên **cùng một message duy nhất** rồi coi kết quả thứ hai là kiểm tra độc lập: lần nhận thành công đầu đã tiêu thụ message đó.

## 16. Tạo selector động: chống thay đổi biểu thức ngoài ý muốn

JMS selector là một String. API JMS không có prepared statement và parameter binding như JDBC. Nối thẳng input không tin cậy vào biểu thức có thể gây **selector injection** hoặc làm phạm vi lọc sai:

~~~java
// Phản ví dụ: region có thể chứa dấu nháy đơn và toán tử khác.
String selector = "region = '" + region + "'";
~~~

Phương án chắc chắn là chỉ nhận giá trị đã cho phép hoặc một mô hình tạo biểu thức bằng code tin cậy.

### Java 17 standalone: builder có allowlist

File `SelectorBuilder.java`:

~~~java
import java.util.Set;

public final class SelectorBuilder {

    private static final Set<String> REGIONS =
            Set.of("APAC", "EU", "US");

    private SelectorBuilder() {}

    public static String forRegionAndScore(
            String region, int minScore) {

        if (!REGIONS.contains(region)) {
            throw new IllegalArgumentException("Unknown region");
        }
        if (minScore < 0 || minScore > 100) {
            throw new IllegalArgumentException("Invalid score");
        }

        return "region = '" + region
                + "' AND score >= " + minScore;
    }

    public static void main(String[] args) {
        System.out.println(forRegionAndScore("APAC", 8));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac SelectorBuilder.java
java SelectorBuilder
~~~

Stdout chính xác:

~~~text
region = 'APAC' AND score >= 8
~~~

Nếu ứng dụng buộc phải nhận chuỗi tự do, escape dấu nháy đơn thành hai dấu nháy đơn (`'` → `''`), giới hạn length/character policy và test dữ liệu nguy hiểm. **Escaping không thay thế authorization**. Với multi-tenant, broker ACL và business authorization phải độc lập với selector.

## 17. Cách chẩn đoán selector không khớp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Queue có message nhưng `receiveSelected` trả null | Không message nào khớp, hoặc timeout | Kiểm tra headers/properties thực tế, selector, queue depth |
| `score >= 8` không chọn score “9” | Score gửi dạng String | Xem setter property type, không chỉ text value |
| `region='VN'` không khớp | Property đặt tên `Region` hoặc value `vn` | Kiểm tra hoa/thường của identifier và literal |
| `NOT(state='DONE')` không lấy message thiếu state | NOT UNKNOWN = UNKNOWN | Thêm `state IS NULL` nếu contract cho phép |
| `region IN ('VN','TH')` không chọn | Region thiếu, khác String hoặc sai case | Kiểm tra type/null |
| Dùng `score IN (1,2)` | `IN` trong JMS chỉ dùng String literals | Dùng OR với phép so sánh số |
| `JMSDeliveryMode=2` không khớp | JMS selector xem header này là String | Dùng `'PERSISTENT'` hoặc `'NON_PERSISTENT'` |
| Một consumer nhận message không đúng vùng | OR không có ngoặc | Dùng nhóm `region='APAC' AND (...)` |
| Dùng `JSON_VALUE` hoặc lọc JSON body | Không thuộc selector portable | Đặt JMS properties cần thiết |
| Lỗi ngay khi tạo consumer | Syntax sai, dấu nháy/ngoặc thiếu | Đọc root cause `JMSException`/Spring `JmsException` |
| Consumer khác “lấy mất” message | Nhiều consumer cùng queue | Kiểm tra selector/concurrency/topology |
| Topic không nhận event cũ | Subscription/retention, không phải cú pháp | Kiểm tra durable subscription và thời điểm đăng ký |
| LIKE chậm | Pattern rộng, nhiều matches, backlog lớn | Benchmark broker, đơn giản hóa condition |
| Selector lọc rộng tenant | Input ghép trực tiếp hoặc sai ngoặc | Builder allowlist, ACL và integration tests |

**Phân biệt lỗi cú pháp và lỗi logic:**
- Provider bắt buộc kiểm tra tính hợp lệ cú pháp lúc selector được cung cấp; sai có thể ném `JMSException`.
- Kiểu property không đúng, property thiếu hoặc giá trị sai case thường cho **FALSE/UNKNOWN** âm thầm.
- `null` từ `receiveSelected` có thể chỉ nghĩa là **không có message khớp trong thời gian chờ**, không khẳng định queue trống.

## 18. Hiệu năng, bảo mật và vòng đời subscription

Selector hoạt động ở tầng JMS provider/broker, nhưng tiêu chuẩn **không hứa** cơ chế index, tối ưu thực thi hay độ trễ cụ thể. Một số broker có index properties; nơi khác phải đánh giá điều kiện trên nhiều message.

Lời khuyên thực tế:
- Dùng equality/range rõ ràng thay vì chuỗi quá dài hoặc `LIKE '%keyword%'` nếu throughput quan trọng.
- Đừng nhân đôi JMS properties không cần thiết; metadata cũng có chi phí truyền/lưu.
- Đừng dùng vòng lặp `receiveNoWait` không backoff để bù cho selector không khớp.
- Theo dõi queue depth, oldest message age, matched deliveries, TTL/expiry, redelivery/DLQ và consumer count.
- Với nhiều business groups cần bản sao độc lập, thiết kế Topic/subscriptions hoặc routing riêng, không dùng một queue có nhiều selectors rồi mong broadcast.
- Thay selector của durable Topic subscription cần kiểm tra lifecycle, khả năng resubscribe và broker policy. Một selector mới không có nghĩa message cũ từ trước khi subscription tồn tại sẽ được replay.
- Selector không là security boundary: vẫn cần broker authentication/TLS/ACL và business tenant validation.
- Contract producer–consumer cần nói rõ property names, types, optional/required, selectors và versioning; rolling deploy thay property đột ngột sẽ khiến messages im lặng không khớp.

### Khi nào không dùng selector?

Nếu việc chọn dữ liệu phụ thuộc sâu vào JSON body và nhiều phép chuyển đổi nghiệp vụ, có thể:
- Đưa một số **thuộc tính định tuyến tối thiểu** thành JMS properties do producer chịu trách nhiệm.
- Tách destination/queue/topic theo nhóm nghiệp vụ.
- Nhận rồi validate/route bên trong service nhưng phải chấp nhận rằng message đã được phân phối/ACK tùy transaction.
- Sử dụng broker-specific filter extension **chỉ khi** tổ chức chấp nhận lock-in và có integration tests.

Tránh viết selector như một SQL query phức tạp chứa mọi business condition; nó nên chỉ là bộ lọc metadata có hợp đồng rõ.

## 19. Checklist go-live

- Producer đặt đúng JMS properties, không chỉ JSON body?
- Property names/literals thống nhất chữ hoa và kiểu?
- String literal escape dấu apostrophe bằng `''` đúng không?
- Toán tử so sánh dùng `<>` thay `!=` khi cần portability?
- Phép String/Boolean chỉ dùng `=` và `<>`?
- Selector có cả AND/OR đã có dấu ngoặc để tránh lọc quá rộng?
- Có test TRUE/FALSE/UNKNOWN cho properties thiếu?
- Dùng `IS NULL`/`IS NOT NULL` khi hợp đồng cần thiếu property?
- `IN` chỉ nhận String list, `BETWEEN` dùng số, `LIKE` wildcard/ESCAPE đúng?
- JMS headers đã được kiểm tra đúng danh sách cho phép?
- `JMSDeliveryMode` được so sánh bằng String, không phải int?
- `receiveSelected` có timeout có kiểm soát?
- Queue/topic, consumer cạnh tranh, subscription durability và TTL được hiểu đúng?
- Selector builder có allowlist/escaping và tenant ACL độc lập?
- Có integration tests với broker thật cho selector và property types?
- Có đo queue backlog/latency khi thay đổi selector trong production?
- Có runbook cho trường hợp message không khớp, poison message, DLQ và rollout version mới?

## 20. Bài tập tự luyện

1. Với region APAC, score=8, urgent=FALSE, tính kết quả `region='APAC' AND (score>8 OR urgent=TRUE)`.
2. Tìm một message khiến `a=1 AND b=2 OR c=3` khác `a=1 AND (b=2 OR c=3)`.
3. State bị thiếu: vì sao `NOT(state='DONE')` không khớp nhưng `state IS NULL OR state <> 'DONE'` lại khớp?
4. Viết selector chọn `status` READY/RETRY và `attempts < 4`.
5. Thử `setStringProperty("score","9")` và giải thích vì sao `score >= 8` không chọn được.
6. Chuyển `score IN (1,2,3)` thành phép `OR` trên so sánh số.
7. Viết selector cho property `clientId` bắt đầu bằng literal `A_`, không phải A + bất kỳ ký tự nào.
8. Viết String literal cho tên `O'Reilly` và phân biệt escaping trong Java String với JMS selector.
9. Vì sao `JMSDeliveryMode='PERSISTENT'` đúng nhưng `JMSDeliveryMode=2` không portable?
10. Với Queue có 2 consumer dùng 2 selectors, có bảo đảm cả hai nhận cùng một message không? Khi nào nên dùng Topic?
11. Dùng `SelectorBuilder`, thử region chứa dấu nháy và từ khóa OR, kiểm tra được từ chối trước khi tạo consumer.
12. Với message thiếu region, tính `region='APAC' OR urgent=TRUE` khi urgent TRUE và khi FALSE; giải thích logic UNKNOWN.
13. Mô tả một bài integration test nhận ra thay đổi producer `Region` thành `region` gây mất match.
14. Nêu vì sao `LIKE '%suffix'` trên queue lớn có thể có chi phí, đề xuất thiết kế property routing phù hợp.
15. Viết kế hoạch rollout khi thêm một property bắt buộc mới mà consumer cũ vẫn còn đang chạy.

## Nguồn chính thức

- Jakarta Messaging 3.1, **`jakarta.jms.Message` — Message Selectors:** https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta Messaging 3.1 Specification, **3.8 Message Selection:** https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta EE Tutorial — **Message Selectors:** https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html
- Spring Framework 6.2 — **JmsTemplate.receiveSelected / receiveSelectedAndConvert API:** https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — **@JmsListener selector:** https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework 6.2 — **Receiving a Message:** https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — **JMS and Artemis configuration:** https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
