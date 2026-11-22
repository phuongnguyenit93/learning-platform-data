# BETWEEN, IN, LIKE và IS NULL trong JMS Message Selectors (Spring Framework JMS)

## 1. Tại sao phải lọc thông điệp trước khi consumer nhận?

Hãy hình dung queue orders.events chứa nhiều message do các ứng dụng khác nhau gửi:

- Đơn hàng có TotalAmount từ 100 đến 500 cần chuyển sang nhóm kiểm tra ưu đãi.
- Những sự kiện có EventType thuộc tập "ORDER_CREATED", "ORDER_PAID" cần một consumer xử lý.
- Những thông điệp có CorrelationKey bắt đầu bằng "ORD-" cần đi tới một luồng nghiệp vụ.
- Các message chưa gắn Region cần được một consumer riêng phát hiện và xử lý theo chính sách dữ liệu thiếu.

Nếu consumer nhận tất cả message rồi mới dùng if/else loại bỏ, nó vừa tốn băng thông và thời gian chuyển giao vừa có nguy cơ **acknowledge/commit một message vốn dành cho consumer khác**. JMS đưa ra cơ chế **message selector** để consumer khai báo tiêu chí quan tâm ngay khi tạo consumer hoặc subscription.

Selector là một biểu thức String theo **một tập con của cú pháp điều kiện SQL-92**. JMS provider dùng **header và message properties** để đánh giá biểu thức; chỉ khi kết quả là **TRUE**, message mới phù hợp để deliver cho consumer đã gắn selector.

Các toán tử trọng tâm bài học:

| Toán tử | Ví dụ | Khi nào dùng? |
| --- | --- | --- |
| BETWEEN | AmountMinor BETWEEN 1000 AND 5000 | Khoảng số có cả hai đầu mút. |
| NOT BETWEEN | PriorityScore NOT BETWEEN 1 AND 3 | Những giá trị số nằm ngoài khoảng. |
| IN | EventType IN ('CREATE', 'UPDATE') | Thuộc một danh sách **chuỗi** được liệt kê. |
| NOT IN | Region NOT IN ('VN', 'SG') | Chuỗi không nằm trong tập đã liệt kê. |
| LIKE | CorrelationKey LIKE 'ORD-%' | So khớp mẫu chuỗi với ký tự đại diện. |
| NOT LIKE | CorrelationKey NOT LIKE 'TMP-%' | Loại các chuỗi khớp mẫu. |
| IS NULL | Region IS NULL | Property không tồn tại hoặc header hỗ trợ có giá trị null. |
| IS NOT NULL | Region IS NOT NULL | Property tồn tại và không null. |

**Quan trọng:** selector không phải truy vấn SQL vào cơ sở dữ liệu, không thể trực tiếp đọc JSON body, không hỗ trợ đầy đủ SQL, và không tự tạo consumer group hay phân chia quyền truy cập. Đây là một **bộ lọc tại tầng JMS delivery**; tính năng và hiệu năng lưu trữ/đánh chỉ mục cụ thể phụ thuộc broker.

## 2. Phân biệt body, headers và message properties

Một message JMS gồm ba khu vực:

~~~mermaid
flowchart LR
  P["Producer"] --> M["JMS Message"]
  M --> H["Standard headers: JMSType, JMSPriority..."]
  M --> R["Properties: EventType, AmountMinor, Region..."]
  M --> B["Body: TextMessage JSON / MapMessage / BytesMessage"]
  H --> S["JMS selector"]
  R --> S
  B --> X["Không đọc được trực tiếp bằng selector chuẩn"]
  S --> C["Matching consumer/subscription"]
~~~

Ví dụ producer gửi TextMessage có body JSON:

~~~json
{
  "orderId": "O-42",
  "amountMinor": 2500,
  "region": "VN"
}
~~~

Nếu chỉ có body này, selector "AmountMinor BETWEEN 1000 AND 5000" **không thể** tìm field amountMinor trong JSON. Phải gắn property JMS ngoài body:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        "{\"orderId\":\"O-42\",\"amountMinor\":2500,\"region\":\"VN\"}",
        message -> {
            message.setIntProperty("AmountMinor", 2500);
            message.setStringProperty("Region", "VN");
            message.setStringProperty("EventType", "ORDER_CREATED");
            return message;
        });
~~~

Đây là **snippet** trong một ứng dụng đã inject JmsTemplate; nó không có main() độc lập. MessagePostProcessor nhận jakarta.jms.Message sau khi converter tạo message, rồi gắn đúng property type.

Lúc này selector có thể dùng AmountMinor, Region, EventType mà **không phải parse body**. Consumer vẫn cần parse và validate JSON sau khi nhận; bộ lọc JMS không thay thế kiểm tra contract nghiệp vụ.

### 2.1. Các tên selector truy cập được

Đặc tả Jakarta Messaging 3.1 giới hạn tham chiếu header chuẩn trong selector vào các tên: **JMSDeliveryMode, JMSPriority, JMSMessageID, JMSTimestamp, JMSCorrelationID, JMSType**. Ngoài ra có thể truy cập message properties có tên hợp lệ. **Không giả định mọi JMS header đều có thể viết làm selector**, chẳng hạn việc JMSExpiration hoặc JMSDeliveryTime là header không có nghĩa chúng là tên selector chuẩn.

Các message property do ứng dụng đặt nên có tên đơn giản, ổn định và hợp lệ theo quy tắc định danh Java:

~~~text
EventType
AmountMinor
CustomerTier
Region
CorrelationKey
SchemaVersion
~~~

Tránh đặt property theo JSON path như order.amount, tên có khoảng trắng, hoặc keyword SQL làm identifier. Property names phân biệt chữ hoa/chữ thường: EventType **khác** eventType. Các tên bắt đầu JMSX là nhóm chuẩn JMSX, JMS_ là namespace dành cho provider; không dùng chúng bừa bãi cho contract của ứng dụng.

### 2.2. Đánh giá trên giá trị kiểu thật, không phải chuỗi hiển thị

~~~java
message.setIntProperty("AmountMinor", 2500);       // Numeric.
message.setStringProperty("EventType", "CREATE");   // String.
message.setBooleanProperty("Urgent", true);         // Boolean.
~~~

Selector nhìn thấy các kiểu tương ứng đã đặt. Nó **không tự áp dụng các phép chuyển String sang Number** mà phương thức đọc property có thể hỗ trợ.

~~~sql
AmountMinor BETWEEN 1000 AND 5000
EventType IN ('CREATE', 'UPDATE')
Urgent = TRUE
~~~

Cú pháp ở trên là các biểu thức JMS selector, không phải câu lệnh SELECT SQL đầy đủ. Trong code Java, truyền từng biểu thức dưới dạng String.

## 3. BETWEEN: so khớp khoảng số có cả hai đầu mút

Cú pháp theo đặc tả:

~~~sql
arithmetic_expression BETWEEN lower_expression AND upper_expression
arithmetic_expression NOT BETWEEN lower_expression AND upper_expression
~~~

Ý nghĩa:

~~~text
X BETWEEN A AND B
        tương đương
(X >= A) AND (X <= B)

X NOT BETWEEN A AND B
        tương đương
(X < A) OR (X > B)
~~~

BETWEEN **bao gồm** cả cận dưới và cận trên. Đây không phải khoảng nửa mở như A <= X < B.

Ví dụ:

~~~sql
AmountMinor BETWEEN 1000 AND 5000
~~~

| AmountMinor được gắn | Kết quả |
| --- | --- |
| 999 | FALSE |
| 1000 | TRUE — đúng cận dưới |
| 2500 | TRUE |
| 5000 | TRUE — đúng cận trên |
| 5001 | FALSE |
| Missing | UNKNOWN, không match |

Ở đây AmountMinor nên được đặt bằng setIntProperty hoặc setLongProperty. Nếu sender dùng setStringProperty("AmountMinor", "2500"), **không được** mong BETWEEN tự chuyển "2500" thành số 2500.

### 3.1. Numeric types và độ chính xác

Jakarta Messaging hỗ trợ numeric literals kiểu integer chính xác hoặc floating approximate và áp dụng quy tắc Java numeric promotion khi so sánh. Các phép so sánh giữa số chính xác và số gần đúng có thể cần promotion, nên với **số tiền**, nên dùng integer minor units theo contract:

~~~java
message.setLongProperty("AmountMinor", 125_000L);
~~~

~~~sql
AmountMinor BETWEEN 100000 AND 200000
~~~

Khi dùng đơn vị nhỏ nhất, contract phải định nghĩa currency, scale và phạm vi long. Tránh đẩy tiền dưới dạng double property rồi giả định so sánh thập phân sẽ có độ chính xác tuyệt đối.

### 3.2. BETWEEN có hỗ trợ ngày giờ không?

Selector JMS không có kiểu SQL DATE/TIMESTAMP chuẩn với hàm NOW(), DATE_TRUNC() hay chuỗi ngày được tự parse. Đặc tả gợi ý diễn đạt thời gian bằng **Java long milliseconds**. Ví dụ gửi:

~~~java
message.setLongProperty(
        "OccurredAtEpochMs",
        java.time.Instant.parse(
                "2026-10-30T10:00:00Z").toEpochMilli());
~~~

Khi thiết kế selector, tính cận trong Java:

~~~java
long from = java.time.Instant.parse(
        "2026-10-30T00:00:00Z").toEpochMilli();
long to = java.time.Instant.parse(
        "2026-10-31T00:00:00Z").toEpochMilli();

String selector = "OccurredAtEpochMs >= " + from
        + " AND OccurredAtEpochMs < " + to;
~~~

Cả hai là **snippet**, không phải file main riêng. Ở ví dụ khoảng thời gian, dùng **cận trên loại trừ** để biểu diễn một ngày UTC và tránh việc phải đoán “mili-giây cuối ngày”. Nếu dùng BETWEEN, cận trên sẽ được **bao gồm**, không phù hợp khi có nhiều khoảng thời gian liền kề phải không chồng lấn.

### 3.3. Khi nào dùng NOT BETWEEN?

~~~sql
PriorityScore NOT BETWEEN 1 AND 3
~~~

Với property numeric tồn tại, những giá trị nhỏ hơn 1 hoặc lớn hơn 3 match. Nếu PriorityScore không tồn tại, phép so sánh không thể kết luận, nên kết quả **UNKNOWN**, không tự coi missing là “nằm ngoài khoảng”.

Muốn nhận cả message thiếu score, dùng:

~~~sql
PriorityScore IS NULL
OR PriorityScore NOT BETWEEN 1 AND 3
~~~

Đây là yêu cầu nghiệp vụ khác; phải chủ động thêm nhánh missing, đừng tự mở rộng lọc nếu không có yêu cầu.

### 3.4. Lỗi thường gặp với BETWEEN

- Cho rằng BETWEEN loại trừ cận trên; thực tế **bao gồm** cả hai cận.
- Viết tổng tiền dưới dạng String property rồi áp numeric BETWEEN.
- Dùng decimal approximate cho tiền cần tính chính xác.
- Dùng date literal kiểu SQL chuẩn trong selector JMS; nên dùng epoch milliseconds.
- Đổi timezone trước khi tính khoảng ngày làm message lọt sang ngày khác.
- Viết BETWEEN 5000 AND 1000 rồi tưởng provider sẽ tự hoán đổi hai cận.
- Cho rằng NOT BETWEEN tự chọn message có property thiếu; nó nhận UNKNOWN.
- Không kiểm soát giá trị âm/range ở sender và consumer.

## 4. IN: so khớp một danh sách các String literal

Cú pháp JMS:

~~~sql
property_name IN ('VALUE_A', 'VALUE_B', 'VALUE_C')
property_name NOT IN ('VALUE_A', 'VALUE_B', 'VALUE_C')
~~~

Theo Jakarta Messaging, **IN dùng identifier có kiểu String hoặc NULL và một danh sách string literals**. Đây không phải SQL IN tổng quát có subquery, expression list bất kỳ hay numeric literal list.

Ví dụ:

~~~sql
EventType IN ('ORDER_CREATED', 'ORDER_PAID', 'ORDER_CANCELLED')
~~~

gần tương đương:

~~~sql
EventType = 'ORDER_CREATED'
OR EventType = 'ORDER_PAID'
OR EventType = 'ORDER_CANCELLED'
~~~

| EventType | Kết quả của IN |
| --- | --- |
| "ORDER_CREATED" | TRUE |
| "ORDER_PAID" | TRUE |
| "ORDER_SHIPPED" | FALSE |
| "order_created" | FALSE với giá trị String khác case |
| Không có property | UNKNOWN |

### 4.1. IN không dùng để liệt kê số theo cú pháp chuẩn

Đừng viết:

~~~sql
AmountMinor IN (100, 200, 300)
~~~

Dạng này không thuộc cú pháp IN chuẩn Jakarta Messaging vì các phần tử phải là string literals. Nếu AmountMinor numeric và tập số nhỏ, biểu diễn bằng so sánh:

~~~sql
AmountMinor = 100 OR AmountMinor = 200 OR AmountMinor = 300
~~~

Còn nếu dữ liệu thực sự là enum/routing label, tốt hơn dùng String property:

~~~java
message.setStringProperty("CustomerTier", "GOLD");
~~~

~~~sql
CustomerTier IN ('GOLD', 'PLATINUM')
~~~

### 4.2. Case sensitivity và khác biệt với SQL database

Selector keywords như IN, AND, LIKE có thể viết hoa hay viết thường. Nhưng **property name** và **String values** cần được so khớp đúng định danh/chuỗi. Đừng mong có SQL collation của database tự biến "vn" thành "VN".

Producer nên chuẩn hóa enum trước khi gắn property (theo contract). Ví dụ quy ước Region luôn là mã ISO uppercase. Consumer không nên tạo biểu thức case-insensitive bằng các hàm UPPER()/LOWER() kiểu SQL vì những hàm đó không thuộc JMS selector chuẩn.

### 4.3. NOT IN và missing

~~~sql
Region NOT IN ('VN', 'SG')
~~~

Với Region="US", điều kiện TRUE. Với Region="VN", FALSE. Nếu **Region không được đặt**, kết quả là UNKNOWN chứ không phải TRUE.

Nếu mục đích là “không thuộc VN/SG, **kể cả không khai báo vùng**”:

~~~sql
Region IS NULL OR Region NOT IN ('VN', 'SG')
~~~

Phải phân biệt mục đích kinh doanh: message thiếu Region có thể cần quarantine thay vì chuyển vào cùng workflow như các quốc gia khác.

### 4.4. Chuỗi có dấu nháy đơn

JMS string literal được đặt trong single quotes. Dấu nháy đơn nằm bên trong được biểu diễn bằng cách **viết hai dấu single quote liên tiếp**, không phải chèn backslash như Java.

~~~sql
OwnerName IN ('O''Reilly', 'D''Angelo')
~~~

Đây là cú pháp JMS selector. Trong Java String double-quoted:

~~~java
String selector =
        "OwnerName IN ('O''Reilly', 'D''Angelo')";
~~~

Không dùng double quotes quanh chuỗi literal trong JMS selector. Ví dụ này còn nhắc tới việc không lắp selector trực tiếp từ input tùy ý mà không escape và whitelist.

## 5. LIKE: so khớp mẫu String với % và _

LIKE xử lý pattern String, **không phải** regular expression và không phải Java String.matches(...).

| Ký hiệu trong pattern | Nghĩa |
| --- | --- |
| % | Bất kỳ chuỗi ký tự nào, kể cả chuỗi rỗng. |
| _ | Chính xác **một** ký tự bất kỳ. |
| Các ký tự khác | Khớp chính ký tự ấy. |
| ESCAPE | Đặt một ký tự escape để % hoặc _ được hiểu theo nghĩa literal. |

Ví dụ:

~~~sql
CorrelationKey LIKE 'ORD-%'
~~~

Khớp "ORD-1", "ORD-ABC" và cả "ORD-" vì % có thể là chuỗi rỗng. Không khớp "INV-1" hoặc "ord-1" theo so sánh ký tự thông thường.

~~~sql
RegionCode LIKE 'V_'
~~~

Khớp "VN", "VA" hoặc hai ký tự bắt đầu bằng V, nhưng không khớp "V" hay "VNA".

### 5.1. Phân biệt % với _

| Giá trị | Pattern 'AB%' | Pattern 'AB_' |
| --- | --- | --- |
| "AB" | TRUE | FALSE |
| "ABC" | TRUE | TRUE |
| "ABCD" | TRUE | FALSE |
| "AB-123" | TRUE | FALSE |
| "ACD" | FALSE | FALSE |
| Missing property | UNKNOWN | UNKNOWN |

Nếu muốn đúng ba ký tự, dấu _ phù hợp; nếu muốn bất kỳ hậu tố, dùng %.

### 5.2. ESCAPE cho dấu % và _ có nghĩa literal

Giả sử property Code chứa "ORD_2026". Khi viết:

~~~sql
Code LIKE 'ORD_%'
~~~

dấu _ được hiểu là **một ký tự bất kỳ**, nên "ORDX2026" cũng match. Muốn yêu cầu **dấu gạch dưới thật**, chọn ký tự escape chẳng hạn !:

~~~sql
Code LIKE 'ORD!_%' ESCAPE '!'
~~~

Pattern "ORD!_%" có nghĩa: chữ "ORD", tiếp theo một dấu _ literal, sau đó là bất kỳ hậu tố nào. Nó match "ORD_2026" và "ORD_", không match "ORDX2026".

Muốn tìm literal %:

~~~sql
Code LIKE 'DISCOUNT!%%' ESCAPE '!'
~~~

Giải thích: "DISCOUNT", tiếp theo ký tự % literal do !% tạo ra, tiếp đến % cuối là wildcard. Vì vậy pattern match "DISCOUNT%10" hoặc "DISCOUNT%". Nếu yêu cầu **so khớp đúng 100% một chuỗi**, thường dùng operator = dễ đọc và ít rủi ro hơn LIKE.

### 5.3. ESCAPE trong Java String

~~~java
String selector =
        "Code LIKE 'ORD!_%' ESCAPE '!'";
~~~

Đây là String Java hợp lệ; dấu ! không cần escape ở tầng Java. Chọn một ký tự escape rõ ràng giúp code tránh sai khi phải dùng dấu backslash trong chuỗi Java, SQL literal và config file cùng lúc.

Nếu payload cần chứa chính ký tự escape hoặc pattern được sinh từ input bên ngoài, phải định nghĩa chiến lược escape đầy đủ cho provider đang dùng; không ghép bừa một chuỗi LIKE rồi mong mọi ký tự đều literal.

### 5.4. NOT LIKE và UNKNOWN

~~~sql
CorrelationKey NOT LIKE 'TMP-%'
~~~

Chỉ match các String **không khớp** mẫu. Nếu CorrelationKey bị thiếu, kết quả của LIKE là UNKNOWN; NOT UNKNOWN vẫn là UNKNOWN, nên message không match.

Muốn nhận cả những message thiếu CorrelationKey:

~~~sql
CorrelationKey IS NULL
OR CorrelationKey NOT LIKE 'TMP-%'
~~~

Điều này có thể mở rộng phạm vi rất nhiều, nên nên có test và review contract trước khi thay đổi.

### 5.5. LIKE không phải regex hay full-text search

Những biểu thức sau **không** phải JMS selector portable:

~~~text
Name REGEXP '^ORD-[0-9]+$'
Name ILIKE 'ord-%'
LOWER(Name) LIKE 'ord-%'
JSON_VALUE(Payload, '$.type') LIKE 'ORDER%'
~~~

Một số provider có extension riêng, nhưng không được lấy extension thành kiến thức áp dụng cho tất cả JMS brokers. Nếu cần regex/phân tích JSON sâu, cân nhắc đưa nhãn routing cần thiết ra message properties và thực hiện validation sau khi nhận.

## 6. IS NULL và IS NOT NULL: xử lý property không tồn tại

Một property có thể **không được producer gửi**. Selector coi giá trị một property không tồn tại là NULL theo logic SQL-92, và cho phép kiểm tra:

~~~sql
Region IS NULL
Region IS NOT NULL
~~~

| Trường hợp | Region IS NULL | Region IS NOT NULL |
| --- | --- | --- |
| Không có property Region | TRUE | FALSE |
| Region="VN" | FALSE | TRUE |
| Region="" | FALSE | TRUE |
| Region="UNKNOWN" | FALSE | TRUE |
| Header được phép tham chiếu có giá trị null | TRUE | FALSE |

**IS NULL không có nghĩa String chứa chữ "null".** Nếu producer gắn setStringProperty("Region", "null"), đó vẫn là String có giá trị, nên Region IS NOT NULL là TRUE.

### 6.1. Null, empty và missing là ba trạng thái khác nhau

~~~java
// Message A: không gọi setStringProperty("Region", ...).
// Message B:
message.setStringProperty("Region", "");
// Message C:
message.setStringProperty("Region", "VN");
~~~

Snippet minh họa ba message khác nhau, không phải ba lệnh chạy trên cùng một message. Với selector "Region IS NULL", chỉ message A không có property match theo logic missing. Message B là chuỗi rỗng, **không phải** NULL.

JMS property APIs có những quy tắc riêng về null và kiểu dữ liệu; không dùng JSON field null trong TextMessage body để suy ra **message property Region bị null**. Khi cần phân biệt explicit null trong JSON, consumer phải parse body bằng converter/parser phù hợp.

### 6.2. Vì sao Region = NULL là sai?

~~~sql
Region = NULL
Region <> NULL
~~~

Những phép so sánh bình thường với NULL không trả TRUE: theo logic ba giá trị, chúng trả UNKNOWN. Để kiểm tra một property thiếu, dùng:

~~~sql
Region IS NULL
~~~

Với property tồn tại:

~~~sql
Region IS NOT NULL
~~~

Đây là toán tử đặc biệt chuyển giá trị NULL/UNKNOWN thành TRUE hoặc FALSE. Một quy tắc tương tự áp dụng cho các header chuẩn được phép xuất hiện trong selector khi header ấy có giá trị null.

### 6.3. IS NULL dùng để lọc message chưa có metadata

Một consumer chuyên xử lý trường hợp producer chưa cấp Region có thể tạo selector:

~~~sql
Region IS NULL AND EventType = 'ORDER_CREATED'
~~~

Nó chỉ match event ORDER_CREATED không có property Region. Dù lọc được, message thiếu thông tin có thể là lỗi hợp đồng dữ liệu; consumer cần định rõ reject/quarantine, không tự suy Region="VN" hoặc dùng timezone server như nguồn sự thật.

## 7. Logic ba giá trị TRUE, FALSE, UNKNOWN

Đây là điểm khác biệt dễ gây sai nhất với các bộ lọc viết bằng if/else trong Java. Selector chỉ match khi **kết quả cuối cùng TRUE**. Cả FALSE và UNKNOWN đều **không match**.

Giả sử:

~~~sql
AmountMinor BETWEEN 1000 AND 5000
~~~

Nếu AmountMinor chưa được gắn, toán hạng là NULL, so sánh ra UNKNOWN. Việc viết thêm NOT phía ngoài **không** tạo thành TRUE:

~~~sql
NOT (AmountMinor BETWEEN 1000 AND 5000)
~~~

Khi AmountMinor missing, NOT UNKNOWN = UNKNOWN.

### 7.1. Bảng chân trị AND

| AND | TRUE | FALSE | UNKNOWN |
| --- | --- | --- | --- |
| TRUE | TRUE | FALSE | UNKNOWN |
| FALSE | FALSE | FALSE | FALSE |
| UNKNOWN | UNKNOWN | FALSE | UNKNOWN |

### 7.2. Bảng chân trị OR

| OR | TRUE | FALSE | UNKNOWN |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| FALSE | TRUE | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | UNKNOWN |

### 7.3. Bảng chân trị NOT

| Biểu thức | NOT |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Ví dụ:

~~~sql
Region = 'VN' OR AmountMinor BETWEEN 1000 AND 5000
~~~

Message không có Region nhưng AmountMinor=2500: trái UNKNOWN, phải TRUE, nên UNKNOWN OR TRUE = **TRUE** và message match.

Message không có Region, AmountMinor=100: trái UNKNOWN, phải FALSE, nên UNKNOWN OR FALSE = **UNKNOWN** và không match.

Message có Region="SG", AmountMinor=100: FALSE OR FALSE = FALSE; không match.

### 7.4. Null-check có thể thay đổi toàn bộ logic

So sánh:

~~~sql
Region <> 'VN'
~~~

và:

~~~sql
Region IS NULL OR Region <> 'VN'
~~~

Câu đầu **không** nhận message thiếu Region. Câu thứ hai **có** nhận. Cả hai đều hợp lệ nhưng thể hiện chính sách nghiệp vụ khác nhau.

Nếu mục tiêu là chỉ nhận dữ liệu có Region hợp lệ và không phải VN:

~~~sql
Region IS NOT NULL AND Region <> 'VN'
~~~

### 7.5. AND, OR, NOT và dấu ngoặc

Selector ưu tiên logical operators: NOT cao hơn AND, AND cao hơn OR. Để người bảo trì không phải đoán, nên dùng dấu ngoặc khi trộn nhiều điều kiện.

~~~sql
EventType = 'ORDER_CREATED'
AND (Region = 'VN' OR Region = 'SG')
~~~

Không viết thiếu ngoặc nếu mục tiêu là như trên:

~~~sql
EventType = 'ORDER_CREATED'
AND Region = 'VN'
OR Region = 'SG'
~~~

Theo precedence, câu thứ hai còn chọn **mọi** message Region='SG' ngay cả khi EventType khác ORDER_CREATED.

BETWEEN có một AND riêng **bên trong cú pháp khoảng**, vì vậy khi trộn BETWEEN với OR, càng nên đặt ngoặc:

~~~sql
(EventType = 'ORDER_CREATED'
 AND AmountMinor BETWEEN 1000 AND 5000)
OR (EventType = 'RETRY' AND Region = 'VN')
~~~

### 7.6. Bảng tổng hợp hành vi khi property bị thiếu

| Điều kiện | Property missing | Có match không? |
| --- | --- | --- |
| Score BETWEEN 1 AND 5 | UNKNOWN | Không |
| Score NOT BETWEEN 1 AND 5 | UNKNOWN | Không |
| Region IN ('VN','SG') | UNKNOWN | Không |
| Region NOT IN ('VN','SG') | UNKNOWN | Không |
| Code LIKE 'ORD-%' | UNKNOWN | Không |
| Code NOT LIKE 'ORD-%' | UNKNOWN | Không |
| Region IS NULL | TRUE | Có |
| Region IS NOT NULL | FALSE | Không |
| Region = NULL | UNKNOWN | Không |
| Region IS NULL OR Region = 'VN' | TRUE | Có |

## 8. Loại dữ liệu, identifier và syntax: những quy tắc cần thuộc

### 8.1. Kiểu được selector nhận

Các property kiểu boolean, byte, short, int, long, float, double và String có thể tham gia vào biểu thức tùy operator; chuẩn không cho phép lấy arbitrary Java DTO, BigDecimal hoặc Instant làm giá trị property có thể lọc trực tiếp. Phải chuẩn hóa metadata trước khi gửi.

~~~java
message.setIntProperty("Age", 20);
message.setStringProperty("Region", "VN");
message.setBooleanProperty("Approved", true);
~~~

~~~sql
Age BETWEEN 18 AND 65
Region IN ('VN', 'SG')
Approved = TRUE
~~~

**Không** đổi String "20" thành int 20 khi filter; các conversion thuận tiện của getter không áp dụng vào selector.

### 8.2. Chuỗi và số là hai loại literal khác nhau

~~~sql
Age BETWEEN 18 AND 65
~~~

khác với:

~~~sql
Age BETWEEN '18' AND '65'
~~~

Câu thứ hai không phải cách chuẩn để so numeric property. Trong một hệ thống định tuyến nghiêm túc, sender cần gắn đúng property type (setIntProperty/setLongProperty), và consumer dùng numeric literals.

### 8.3. Identifiers hợp lệ và reserved words

- Tên property có thể bắt đầu bằng chữ cái Java, dấu _ hoặc $, và phần tiếp theo theo Java identifier part.
- Property name **phân biệt case**.
- Không dùng NOT, AND, OR, BETWEEN, LIKE, IN, IS, ESCAPE, TRUE, FALSE, NULL làm tên identifier.
- Chuỗi literal dùng single quote, dấu single quote nội bộ gấp đôi: 'O''Brien'.
- Keywords và từ khóa phép toán không phân biệt case; giá trị String được so theo chuỗi ký tự và không tự thành uppercase.
- Có thể dùng ngoặc tròn để xác định rõ grouping.
- Dấu = so sánh bằng, <> so sánh khác; đừng dùng == hoặc != như Java.

### 8.4. Selector không phải SQL database

Những ý tưởng sau không thuộc selector chuẩn:

~~~text
SELECT * FROM orders WHERE Region='VN'
JSON_EXTRACT(body, '$.region') = 'VN'
AmountMinor IN (100, 200, 300)
Region ILIKE 'vn%'
ORDER BY JMSTimestamp DESC
LIMIT 10
~~~

Selector chỉ là **conditional expression**, không có SELECT, FROM, ORDER BY, LIMIT hoặc JOIN. Một số broker có extension riêng nhưng làm mất portability. Hãy bắt đầu với bộ cú pháp được Jakarta Messaging quy định.

### 8.5. Invalid selector vs selector hợp lệ nhưng không match

Hai tình huống khác nhau:

- **Invalid syntax:** câu như "Region IN (" hoặc dấu nháy không cân bằng. Jakarta Messaging provider phải phát hiện khi selector được cung cấp và ném InvalidSelectorException.
- **Hợp lệ về syntax, sai dữ liệu:** ví dụ "Age BETWEEN 18 AND 65" nhưng sender dùng setStringProperty("Age","20"). Selector có thể hoàn toàn hợp lệ nhưng không match như mong muốn.

Provider không thể kiểm tra đầy đủ kiểu của mọi property ở thời điểm tạo consumer vì còn chưa biết message tương lai. Do đó đừng coi “khởi động listener không lỗi” là bằng chứng selector đang hoạt động đúng.

## 9. Cách Spring JMS áp dụng selector

### 9.1. JmsTemplate.receiveSelected(...)

Spring JmsTemplate có overload nhận selector:

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.events",
        "AmountMinor BETWEEN 1000 AND 5000");
~~~

Đây là snippet trong Spring bean, cần import jakarta.jms.Message. Method tạo consumer thích hợp với destination và selector, chờ message rồi trả về Message hoặc null khi timeout.

Khi chỉ cần String payload đã được MessageConverter chuyển:

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "orders.events",
        "EventType IN ('ORDER_CREATED','ORDER_PAID')");
~~~

Method nhận Message theo selector rồi chuyển bằng MessageConverter. Nếu default SimpleMessageConverter và body là TextMessage, payload thường là String. Nếu message converter tùy chỉnh thì type khác; selector vẫn chỉ nhìn JMS headers/properties.

**Lưu ý:** receiveSelected là synchronous/blocking. Hãy đặt receiveTimeout hữu hạn, tránh vô tình giữ thread rất lâu:

~~~java
jmsTemplate.setReceiveTimeout(2_000L); // Hai giây.
~~~

Nếu không có message khớp, receive có thể trả null dù queue có nhiều message **không khớp**. Null chỉ nghĩa là lần nhận này không lấy được message phù hợp trong thời gian chờ, không chứng minh queue rỗng.

### 9.2. @JmsListener(selector = "...")

Với xử lý bất đồng bộ, dùng annotation:

~~~java
@Component
class OrderListener {

    @JmsListener(
        destination = "orders.events",
        selector =
            "EventType IN ('ORDER_CREATED','ORDER_PAID') "
            + "AND AmountMinor BETWEEN 1000 AND 5000")
    public void process(String payload) {
        // Validate JSON payload và xử lý nghiệp vụ.
    }
}
~~~

Đây là **snippet** trong ứng dụng có JMS listener infrastructure, không phải class main độc lập. Cần import org.springframework.stereotype.Component và org.springframework.jms.annotation.JmsListener. Với text message, converter phù hợp giúp bind payload thành String.

Trong @JmsListener, selector là thuộc tính của endpoint/consumer được container tạo. Nếu bạn muốn đổi selector theo tenant hoặc runtime config, phải có cơ chế cấu hình và tái tạo/restart consumer phù hợp; không kỳ vọng sửa một biến Java bên ngoài sẽ thay selector đã đăng ký.

### 9.3. Cấu hình listener factory nhất quán

Một ứng dụng cần tự kiểm soát transaction, concurrency, domain, error handling và recovery có thể định nghĩa factory:

~~~java
@Configuration
@EnableJms
class JmsListenerConfig {

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory factory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Snippet trên cần import jakarta.jms.ConnectionFactory, các annotation của Spring và DefaultJmsListenerContainerFactory. Với transaction thật, phải cấu hình provider/ConnectionFactory và error handling tương ứng. Không dùng mẫu rút gọn này như bộ cấu hình production đầy đủ.

### 9.4. Dùng JMS API thuần

Có thể tạo consumer trực tiếp:

~~~java
Queue queue = session.createQueue("orders.events");
String selector =
        "Region IN ('VN','SG') "
        + "AND AmountMinor BETWEEN 1000 AND 5000";

try (MessageConsumer consumer =
             session.createConsumer(queue, selector)) {

    Message message = consumer.receive(2_000L);
    // Consumer phải ở trên Connection đã start.
}
~~~

Đây là snippet trong bối cảnh có JMS Session và Connection đã start. Nếu Session thuộc JmsTemplate/transaction manager, không tự đóng Session hoặc Connection do framework cấp. Với consumer tự tạo thì đóng bằng try-with-resources.

Nếu chỉ cần lọc đơn giản trong Spring, JmsTemplate.receiveSelected hoặc @JmsListener thường rõ ràng hơn.

## 10. Demo chạy được: Java 17, Spring Boot 3.3 và ActiveMQ Artemis

Mục này tạo một ứng dụng gửi các message có property khác nhau tới **bốn queue thử nghiệm** (mỗi queue có UUID riêng để tránh tồn dư). Ứng dụng dùng JmsTemplate.convertAndSend(...) để gắn property đúng kiểu, sau đó dùng receiveSelectedAndConvert(...) để minh họa kết quả từng operator.

**Điểm thiết kế:** ví dụ chỉ có một consumer đồng bộ tại mỗi lần nhận, không có listener chạy nền cạnh tranh. Hai trường hợp có nhiều message matching được **sắp xếp kết quả trong Java trước khi in**, vì không nên xây logic nghiệp vụ dựa vào giả định message khác queue/sessions luôn có thứ tự xác định.

### 10.1. Chuẩn bị broker

Yêu cầu JDK 17+, Maven, Docker và cổng TCP 61616 trống. Khởi động broker Artemis:

~~~bash
docker run --detach --rm --name selector-demo-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chờ broker sẵn sàng trước khi chạy ứng dụng. Image demo có username/password artemis/artemis theo cấu hình mẫu; production cần tài khoản/quyền riêng, image được pin version, không dùng mật khẩu minh họa.

Vì demo sinh tên queue động, broker phải cho phép auto-create queue. Nếu deployment không cho auto-create, phải khai báo destination và ACL tương ứng trước, hoặc sửa demo dùng những queue đã được cấp phát.

Cấu trúc project:

~~~text
spring-jms-selectors/
├── pom.xml
└── src/main/
    ├── java/example/jmsselectors/SelectorDemoApplication.java
    └── resources/application.properties
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>spring-jms-selectors</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.x dựa trên Spring Framework 6.x và Jakarta JMS (jakarta.jms.*), không trộn javax.jms.* của Spring 5. Việc cố định version ở ví dụ giúp tái lập API khi học; production cần chọn bản được hỗ trợ và kiểm thử theo tiêu chuẩn của tổ chức.

### 10.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Ứng dụng chỉ có CommandLineRunner, không cần HTTP server hoặc @JmsListener. Mọi receive đều do code chủ động gọi, nên dễ quan sát selector nào match.

### 10.4. SelectorDemoApplication.java

~~~java
package example.jmsselectors;

import java.util.UUID;
import java.util.stream.Stream;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelectorDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JmsTemplate jms) {
        return args -> {
            jms.setReceiveTimeout(3_000L);

            String runId = UUID.randomUUID()
                    .toString().replace("-", "");
            String qBetween = "demo.sel.between." + runId;
            String qIn = "demo.sel.in." + runId;
            String qLike = "demo.sel.like." + runId;
            String qNull = "demo.sel.null." + runId;

            // BETWEEN: 15 và 20 đều thuộc khoảng [15,20].
            sendNumber(jms, qBetween, "age-14", "Age", 14);
            sendNumber(jms, qBetween, "age-15", "Age", 15);
            sendNumber(jms, qBetween, "age-20", "Age", 20);
            sendNumber(jms, qBetween, "age-21", "Age", 21);

            String between = String.join(", ",
                    Stream.of(
                            take(jms, qBetween,
                                    "Age BETWEEN 15 AND 20"),
                            take(jms, qBetween,
                                    "Age BETWEEN 15 AND 20"))
                            .sorted()
                            .toList());
            System.out.println("BETWEEN: " + between);

            // IN: chỉ chọn String-valued Department.
            sendText(jms, qIn, "finance", "Department", "FINANCE");
            sendText(jms, qIn, "legal", "Department", "LEGAL");
            sendText(jms, qIn, "warehouse", "Department", "WAREHOUSE");

            String in = String.join(", ",
                    Stream.of(
                            take(jms, qIn,
                                    "Department IN ('FINANCE','WAREHOUSE')"),
                            take(jms, qIn,
                                    "Department IN ('FINANCE','WAREHOUSE')"))
                            .sorted()
                            .toList());
            System.out.println("IN: " + in);

            // LIKE: !_ là literal underscore, % là hậu tố.
            sendText(jms, qLike, "literal-underscore",
                    "Code", "ORD_100");
            sendText(jms, qLike, "other",
                    "Code", "ORDX100");

            String like = take(jms, qLike,
                    "Code LIKE 'ORD!_%' ESCAPE '!'");
            System.out.println("LIKE: " + like);

            // IS NULL: một message không có property GroupTag.
            jms.convertAndSend(qNull, "missing");
            sendText(jms, qNull, "present",
                    "GroupTag", "G-A");

            String absent = take(jms, qNull,
                    "GroupTag IS NULL");
            String present = take(jms, qNull,
                    "GroupTag IS NOT NULL");
            System.out.println("IS NULL: " + absent);
            System.out.println("IS NOT NULL: " + present);
        };
    }

    private static void sendNumber(
            JmsTemplate jms,
            String queue,
            String body,
            String property,
            int value) {

        jms.convertAndSend(queue, body, message -> {
            message.setIntProperty(property, value);
            return message;
        });
    }

    private static void sendText(
            JmsTemplate jms,
            String queue,
            String body,
            String property,
            String value) {

        jms.convertAndSend(queue, body, message -> {
            message.setStringProperty(property, value);
            return message;
        });
    }

    private static String take(
            JmsTemplate jms,
            String queue,
            String selector) {

        Object body =
                jms.receiveSelectedAndConvert(queue, selector);
        if (!(body instanceof String text)) {
            throw new IllegalStateException(
                    "No matching TextMessage: " + selector);
        }
        return text;
    }
}
~~~

Lớp trên là ví dụ Java 17 hoàn chỉnh với main(), bean CommandLineRunner và helper methods. Nó dùng JmsTemplate do Spring Boot cấu hình qua starter Artemis, default String ↔ TextMessage converter, MessagePostProcessor để thêm metadata và receiveSelectedAndConvert để chọn message.

### 10.5. Chạy chương trình và output

Trong thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Với broker hoạt động đúng, quyền queue hợp lệ, không có competing consumer và mỗi receive thành công trong timeout, output do ứng dụng tự in là:

~~~text
BETWEEN: age-15, age-20
IN: finance, warehouse
LIKE: literal-underscore
IS NULL: missing
IS NOT NULL: present
~~~

Spring Boot và Artemis có thể in thêm log. Để giữ output ổn định, code sắp xếp hai body trong BETWEEN và IN trước khi in. Những message không match (age-14, age-21, legal, other) **không bị nhận bởi các receive có selector**; chúng vẫn là message trong queue theo chính sách broker và có thể được nhận bởi consumer khác.

Nếu một selector trả null do timeout hoặc broker chặn việc nhận, take() ném exception với tên selector thay vì in kết quả sai như thể thành công. Demo dùng queue UUID để tránh message cũ từ lượt chạy trước. **Chưa cần** sử dụng @JmsListener vì mục tiêu là so sánh các toán tử theo thứ tự rõ ràng.

Dừng broker:

~~~bash
docker stop selector-demo-broker
~~~

### 10.6. Thí nghiệm đổi từng operator

**BETWEEN:** đổi thành Age BETWEEN 14 AND 21, nhận bốn message (chỉnh demo để receive bốn lần). Đổi thành Age BETWEEN 15 AND 19, chỉ còn "age-15". Nếu dùng Age NOT BETWEEN 15 AND 20, hai message ngoài khoảng được chọn; missing Age vẫn không tự match.

**IN:** thêm message Department="FINANCE", kiểm tra có được match không. Đổi Department thành string "finance" để thấy khác case. Thử dùng Department NOT IN ('FINANCE','WAREHOUSE') để nhận "legal".

**LIKE:** thay "ORD_100" thành "ORDX100". Với pattern "ORD!_%", kết quả không match; nếu dùng "ORD_%" (không escape), "ORDX100" lại có thể match vì _ là wildcard.

**IS NULL:** thêm message có GroupTag="" rồi chạy selector IS NULL; message ấy không match vì property tồn tại. Dùng IS NOT NULL để nhận message có chuỗi rỗng.

**UNKNOWN:** thêm một message không có Age, sau đó thử Age NOT BETWEEN 15 AND 20. Nó không match vì UNKNOWN, nhưng Age IS NULL match.

## 11. Kết hợp nhiều toán tử cho bài toán thực tế

Ví dụ consumer xử lý yêu cầu ở Việt Nam/Singapore, tổng tiền trong một khoảng và chỉ chọn event CREATE/UPDATE:

~~~sql
(EventType IN ('ORDER_CREATED', 'ORDER_UPDATED'))
AND (Region IN ('VN', 'SG'))
AND (AmountMinor BETWEEN 100000 AND 500000)
~~~

Producer phải gắn:

~~~java
message.setStringProperty("EventType", "ORDER_CREATED");
message.setStringProperty("Region", "VN");
message.setLongProperty("AmountMinor", 250000L);
~~~

Nếu AmountMinor thiếu, toàn bộ biểu thức là UNKNOWN khi hai vế khác TRUE; message không match. Đừng nhầm đây là “lọc sai”: broker chỉ tuân theo dữ liệu JMS properties thực sự được gửi.

### 11.1. Routing theo tên có prefix

~~~sql
(EventType IN ('ORDER_CREATED','ORDER_CANCELLED'))
AND CorrelationKey LIKE 'ORD-%'
~~~

Khớp các event cần thiết có CorrelationKey dạng "ORD-...". Nếu CorrelationKey không được gửi, LIKE là UNKNOWN và message không match. Khi cần cách ly dữ liệu xấu, dùng một consumer khác có selector CorrelationKey IS NULL; nhưng hãy xem xét rõ tương tác với những consumer khác trên cùng queue.

### 11.2. Nhóm quét metadata thiếu

~~~sql
(EventType = 'ORDER_CREATED')
AND (Region IS NULL OR CorrelationKey IS NULL)
~~~

Đây là luồng kiểm tra contract. Một selector dành cho “data invalid” không thay thế validate body và không thể phân loại tất cả lỗi schema; chẳng hạn dữ liệu body bị thiếu orderId nhưng header đủ vẫn không bị phát hiện bởi selector.

### 11.3. Khoảng thời gian theo UTC

Nếu producer ghi CreatedAtEpochMs là long milliseconds, consumer có thể chọn:

~~~sql
CreatedAtEpochMs >= 1793318400000
AND CreatedAtEpochMs < 1793404800000
~~~

Các số trong biểu thức chỉ minh họa định dạng epoch millisecond; khi dùng thực tế phải tính giới hạn từ Instant/ZoneId của business domain và kiểm thử. Đây là khoảng **nửa mở**, thường an toàn hơn BETWEEN cho các time windows liên tiếp.

### 11.4. “Không thuộc tập” có phải là “thuộc tập khác”?

Không luôn luôn. Với Region NOT IN ('VN','SG'), message thiếu Region không thuộc tập theo nghĩa Java null-check nhưng trong JMS selector kết quả là UNKNOWN, không match. Nếu business rule muốn “những nước khác và chưa được gán”, phải viết thêm Region IS NULL.

## 12. Hiệu năng, độ trễ và semantics Queue/Topic

### 12.1. Queue: message không match không bị lấy rồi bỏ

Với Queue, selector quyết định message nào phù hợp với consumer. Các message không match selector của consumer này vẫn có thể nằm chờ consumer khác có điều kiện phù hợp hoặc consumer không gắn selector.

Không đồng nghĩa mọi message đã lọc sẽ tự chuyển sang queue khác. Selector **không phải router thực hiện move message giữa destinations**: nó chỉ chi phối việc chọn cho từng consumer/subscription.

Nếu chỉ có một consumer với selector quá hẹp, queue có thể tích lũy những message không ai chọn. Theo dõi queue depth, độ tuổi message, group/selector distribution và các nhánh không có subscriber.

### 12.2. Topic: selector thuộc subscription

Với Topic, selector được gắn khi subscription được tạo. Thông điệp không match có thể không được thêm vào subscription ấy; các subscription khác có thể có selector khác và nhận các bản sao phù hợp. Tương tác giữa durable subscription, selector thay đổi và cleanup phụ thuộc JMS API/broker, nên cần quản lý vòng đời subscription rõ ràng.

Không suy luận “topic message không match selector” có nghĩa mọi subscriber đều không được giao. Nó chỉ không phù hợp với một subscription cụ thể.

### 12.3. Tránh selector quá tốn kém

BETWEEN numeric/IN trên property routing rõ ràng có thể dễ tối ưu hơn việc đánh giá LIKE có wildcard ở đầu, nhưng hiệu quả thực tế phụ thuộc broker có tối ưu/index selector ra sao. Jakarta Messaging **không bảo đảm index**, chi phí cố định hoặc thời gian trả kết quả.

Thực hành:

- Đặt routing metadata nhỏ, ổn định, đúng kiểu và thường xuyên được query.
- Ưu tiên equality hoặc IN trên enum rời rạc khi phù hợp.
- Tránh LIKE '%suffix' nếu queue lớn, đặc biệt nếu không có cơ chế tối ưu provider-specific.
- Không tạo hàng nghìn selectors khác nhau cho mỗi user/tenant nếu broker không được thiết kế để chịu tải đó.
- Test under load với message mix thật, số lượng listener/consumer thật và nhiều producer.
- Không copy toàn bộ body JSON sang message properties chỉ để lọc; cân bằng chi phí metadata/size/PII.

### 12.4. Khi nào nên tách queue/topic thay vì selector?

Nếu các nhóm consumer có lifecycle, QoS, retention, quyền, số lượng retry hoặc SLA khác nhau, việc tách queue/topic theo domain có thể rõ ràng hơn nhồi tất cả vào một queue rồi lọc. Selector thích hợp cho **phân đoạn theo metadata** trong cùng mô hình giao tiếp, không phải công cụ thay thế mọi topology design.

Ví dụ: payment.commands và analytics.events có tính chất xử lý hoàn toàn khác. Dùng một queue cộng selector để thay topology có thể dẫn tới backlog và quyền truy cập khó quản lý.

## 13. Selector và bảo mật

JMS selector **không phải authorization boundary**. User/tenant không được bảo đảm cô lập chỉ vì consumer của họ có selector Region='VN'; vẫn cần cấu hình broker ACL, credentials, permissions và tách tài nguyên khi cần.

### 13.1. Không ghép input bên ngoài trực tiếp

Nếu cho user truyền giá trị Region rồi ghép:

~~~java
String selector = "Region = '" + userInput + "'";
~~~

đầu vào có single quote hoặc đoạn điều kiện khác có thể làm expression lỗi hoặc thay đổi ý nghĩa. JMS selector không có API bind parameter chuẩn tương đương PreparedStatement SQL.

Với **tập enum hữu hạn**, tốt nhất kiểm tra whitelist:

~~~java
Set<String> allowed = Set.of("VN", "SG", "TH");
if (!allowed.contains(userInput)) {
    throw new IllegalArgumentException("Unsupported region");
}
String selector = "Region = '" + userInput + "'";
~~~

Đây là snippet Java 17 (import java.util.Set) chỉ an toàn cho trường hợp userInput đã được whitelist cố định như trên. Với String bất kỳ, phải escape literal (single quote -> doubled single quote), kiểm soát độ dài, tên property và biểu thức; không chuyển nguyên một chuỗi do client cung cấp thành selector mà không xác thực.

~~~java
static String quoteSelectorString(String value) {
    return "'" + value.replace("'", "''") + "'";
}
~~~

Hàm trên chỉ xử lý **String literal quoting**, không tự đảm bảo an toàn cho tên property hoặc pattern LIKE. Nếu input được đưa vào LIKE, còn phải xem xét wildcard %/_ và ESCAPE theo contract.

### 13.2. Property names và PII

Không đưa số thẻ, access token, email nhạy cảm hoặc thông tin cá nhân làm property routing nếu broker logs/metrics có thể ghi metadata. Sử dụng nhãn domain không nhạy cảm và chia sẻ quyền tối thiểu cho các consumer. Cân nhắc encryption/masking cho payload, tuân thủ chính sách dữ liệu của hệ thống.

## 14. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/khắc phục |
| --- | --- | --- |
| Selector BETWEEN không match dù body JSON có AmountMinor | Property không được gắn trên JMS Message; chỉ nằm trong body | Gắn setIntProperty/setLongProperty trước send. |
| AmountMinor BETWEEN không match với "2500" | Property là String, không phải numeric | Dùng setIntProperty thay vì setStringProperty. |
| IN nhận lỗi hoặc không hoạt động với danh sách số | IN chuẩn chỉ nhận string literals | Dùng OR với numeric equality hoặc đổi sang enum string. |
| IN không match "vn" với 'VN' | String literal/case khác nhau | Chuẩn hóa enum ở producer và test. |
| LIKE 'ORD_%' match cả ORDX123 | _ là wildcard | Dùng LIKE 'ORD!_%' ESCAPE '!'. |
| LIKE 'ORD-%' match "ORD-" | % cho phép chuỗi rỗng | Bổ sung pattern/validation để yêu cầu hậu tố không rỗng. |
| NOT LIKE không nhận message thiếu Code | NOT UNKNOWN vẫn UNKNOWN | Cân nhắc Code IS NULL OR ... nếu policy cho phép. |
| IS NULL không match Region="" | Chuỗi rỗng vẫn là giá trị | Dùng Region = '' nếu contract yêu cầu nhận empty string. |
| Region = NULL không match message thiếu | So sánh với NULL trả UNKNOWN | Dùng IS NULL. |
| Nhiều điều kiện OR nhận message sai EventType | Thiếu ngoặc nhóm AND/OR | Ghi rõ (A AND (B OR C)). |
| InvalidSelectorException lúc tạo consumer | Sai cú pháp: dấu quote, ngoặc, keyword | Unit test selector và thử trên broker thực. |
| Listener chạy nhưng chỉ queue depth tăng | Không message nào match metadata; property tên/kiểu sai | Inspect message headers/properties và selector đang active. |
| JmsTemplate.receiveSelected trả null | Timeout hoặc không có message matching | Đừng kết luận queue trống; kiểm tra selector và receiveTimeout. |
| Tìm đúng kiểu ngày nhưng sai khoảng | Epoch seconds vs milliseconds, timezone lệch | Contract UTC/epochMillis, tạo bounds bằng Instant. |
| Chỉ một tenant nhận được message | Một consumer selector quá rộng/narrow hoặc ACL topology sai | Audit naming/selector, cấu hình bảo mật và consumer count. |
| Thay @JmsListener.selector không thấy hiệu lực | Container cũ vẫn chạy với selector trước đó | Redeploy/recreate subscription/container thích hợp. |
| Broker CPU cao khi nhiều consumer có LIKE | Selector đắt/đầu wildcard, nhiều biến thể | Benchmark broker, đơn giản hóa metadata/topology. |

### 14.1. Quy trình debug theo bước

1. **Dữ liệu thật:** dùng broker console/debug client để xem property **và kiểu thật**, không chỉ body.
2. **Selector thật:** lấy expression đang được Spring listener/container sử dụng sau khi resolve configuration, không chỉ xem source code.
3. **Cú pháp:** có quote/ngoặc đúng, có dùng IN với string literals, LIKE/ESCAPE đúng?
4. **Tên:** property identifier đúng hoa/thường không, có viết nhầm keyword?
5. **Null:** field thiếu có làm UNKNOWN không, có phải thêm IS NULL?
6. **Domain:** consumer đang nhận Queue hay Topic, subscription đúng không?
7. **Timeout:** receiveSelected đang đợi bao lâu, có message matching nào thực sự được gửi trong khoảng ấy?
8. **Transaction:** message đã commit chưa, selector có không khớp do producer chưa gắn properties lúc send?
9. **Lỗi schema:** body và JMS metadata có bất nhất về EventType/Region/Version không?
10. **Vận hành:** metrics backlog, unconsumed messages, retry, dead-letter, expiry và listener health.

## 15. Các tình huống thiết kế đáng suy nghĩ

### 15.1. Muốn lọc số tiền, nhưng producer có hai phiên bản

Producer v1 đặt AmountMinor bằng String "2500"; producer v2 đặt bằng int 2500. Dù dữ liệu nghiệp vụ giống nhau, selector numeric BETWEEN chỉ hoạt động đáng tin với v2.

Giải pháp không phải cố viết selector “tự ép kiểu”; hãy chuẩn hóa contract, version metadata, triển khai consumer phù hợp, hoặc bổ sung một property numeric mới song song trong giai đoạn migration.

### 15.2. Tenant không được phép đọc message của tenant khác

Selector TenantId='A' có thể giúp route nội bộ, nhưng **không thay ACL**. Nếu yêu cầu cách ly dữ liệu là ràng buộc bảo mật, phân quyền destination/subscription và tài khoản broker mới là lớp kiểm soát chính. Không cho client tự sửa selector rồi truy cập dữ liệu khác.

### 15.3. Muốn lọc đơn hàng chứa mặt hàng đặc biệt

Nếu ProductSku chỉ có trong JSON body, selector không thể tìm trực tiếp. Có thể đưa ProductCategory hoặc RequiresReview làm JMS property sau khi validate producer, hoặc thiết kế queue/route khác. Consumer vẫn phải kiểm tra body; property route là **projection** từ dữ liệu nghiệp vụ, không thay thế hợp đồng gốc.

### 15.4. Có những message không ai nhận

Queue chứa message thiếu EventType, trong khi tất cả consumers đều có selector EventType IN (...). Chúng sẽ tích tụ. Cần một chiến lược riêng: bổ sung consumer kiểm soát EventType IS NULL, quarantine hoặc contract validation tại producer; theo dõi backlog và dead-letter policy.

### 15.5. Cần lọc theo một thời điểm deadline

Nếu deadline nằm ở business property long DeadlineEpochMs, selector có thể so với **một numeric literal được tính khi tạo consumer**. Tuy nhiên selector không có hàm NOW() portable để tự cập nhật mỗi millisecond. Trong listener hoạt động lâu, business deadline thay đổi theo đồng hồ nên nên validate ở handler, không nhét một “now” cố định vào selector rồi mong nó tự cập nhật.

## 16. Checklist khi viết selector production

- [ ] Field cần lọc nằm trong JMS headers/properties được chuẩn hỗ trợ, không chỉ body.
- [ ] Producer gắn property bằng đúng type: int/long cho BETWEEN, String cho IN/LIKE.
- [ ] Property name hợp lệ, không trùng keyword, ổn định và đúng hoa/thường.
- [ ] BETWEEN được hiểu là **inclusive**; time windows liên tiếp cân nhắc half-open.
- [ ] IN chỉ dùng string literal list, không dùng subquery/numeric list.
- [ ] LIKE sử dụng % và _ có chủ đích; nếu muốn literal %, _ thì dùng ESCAPE.
- [ ] Missing property được thiết kế rõ; NOT không làm UNKNOWN trở thành TRUE.
- [ ] IS NULL/IS NOT NULL dùng đúng nghĩa, không nhầm JSON null hoặc empty string.
- [ ] Có ngoặc khi trộn AND/OR và BETWEEN.
- [ ] Không dựa vào implicit String-number conversion hoặc SQL functions không chuẩn.
- [ ] Không ghép user input chưa whitelist/escape thành selector.
- [ ] @JmsListener containerFactory, Queue/Topic và ConnectionFactory được cấu hình đúng.
- [ ] Có receiveTimeout hữu hạn nếu dùng JmsTemplate.receiveSelected.
- [ ] Có test integration trên đúng broker/provider và đúng tập dữ liệu property.
- [ ] Có metric backlog và đường xử lý message không khớp.
- [ ] Không dùng selector làm cơ chế bảo mật tenant hoặc thay schema validation.

## 17. Câu hỏi tự kiểm tra

**Câu 1. BETWEEN có bao gồm cận dưới và trên không?** Có. X BETWEEN 10 AND 20 match 10 và 20.

**Câu 2. IN có chấp nhận AmountMinor IN (100,200) theo chuẩn JMS không?** Không. IN chuẩn dùng danh sách string literals với String-valued identifier.

**Câu 3. LIKE 'ORD-%' có match 'ORD-' không?** Có, vì % có thể khớp chuỗi rỗng.

**Câu 4. LIKE 'AB_' có match 'AB' không?** Không. Dấu _ yêu cầu đúng một ký tự.

**Câu 5. Muốn dấu _ literal trong pattern thì làm gì?** Chọn ESCAPE; ví dụ Code LIKE 'ORD!_%' ESCAPE '!'.

**Câu 6. Region thiếu thì Region <> 'VN' TRUE hay UNKNOWN?** UNKNOWN; selector không match.

**Câu 7. Region thiếu thì Region IS NULL?** TRUE.

**Câu 8. Region="" thì Region IS NULL?** FALSE, vì empty string vẫn là giá trị được cung cấp.

**Câu 9. Selector đọc trực tiếp JSON body để kiểm tra $.amount được không?** Không theo Jakarta Messaging chuẩn.

**Câu 10. Vì sao String "20" không tự match Age BETWEEN 18 AND 65?** Selector không áp conversion getter String->int; property type phải phù hợp.

**Câu 11. Những kết quả nào khiến selector chọn message?** Chỉ TRUE, không chọn FALSE hoặc UNKNOWN.

**Câu 12. JmsTemplate.receiveSelected trả null có nghĩa queue rỗng không?** Không nhất thiết; có thể có message không khớp hoặc timeout.

**Câu 13. @JmsListener(selector=...) tạo bộ lọc ở đâu?** Listener container tạo JMS consumer/subscription với selector; broker/provider dùng metadata để lọc giao message.

**Câu 14. Nếu dùng NOT LIKE với property thiếu, có lấy được message không?** Không; NOT UNKNOWN vẫn UNKNOWN. Muốn lấy missing phải xét IS NULL riêng.

**Câu 15. Có nên dùng selector TenantId='tenant-A' để thay cho broker ACL không?** Không. Selector chỉ lọc delivery, không cấp quyền hay bảo đảm cô lập bảo mật.

### Bài tập thực hành

1. Chạy demo và kiểm tra chính xác output của BETWEEN/IN/LIKE/IS NULL.
2. Đổi số tuổi hai đầu mút, chứng minh BETWEEN bao gồm cận.
3. Đổi Department thành lowercase và dự đoán IN có match hay không.
4. Đổi Code từ "ORD_100" sang "ORDX100", so sánh LIKE có ESCAPE với không ESCAPE.
5. Gửi một message thiếu Age và kiểm tra Age NOT BETWEEN 15 AND 20 so với Age IS NULL.
6. Thêm sender gắn setStringProperty("Age","20"), quan sát vì sao numeric BETWEEN không match.
7. Viết @JmsListener với selector kết hợp IN, BETWEEN và LIKE; dùng Testcontainers Artemis hoặc broker test để kiểm chứng.
8. Viết bộ test tách TRUE, FALSE, UNKNOWN cho biểu thức AND/OR và NULL.
9. Cấu hình hai consumers với selectors không chồng lấn; kiểm tra queue depth khi có message không phù hợp với cả hai.
10. Xây dựng naming contract EventType, Region, AmountMinor có version và test tương thích producer/consumer.
11. Thiết kế xử lý riêng Region IS NULL thay vì mặc định đưa message về Region='VN'.
12. Mô phỏng selector do người dùng tự cung cấp, thử dấu nháy đơn và chứng minh nhu cầu whitelist/quoting.

## 18. Tài liệu tham khảo chính thức

- Jakarta Messaging 3.1, phần 3.8 Message selection và 3.8.1.2 Null values: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 specification document/PDF: https://jakarta.ee/specifications/messaging/3.1/
- Spring Framework, Receiving a Message (JmsTemplate): https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.2 JmsTemplate API, receiveSelected và receiveSelectedAndConvert: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework, Annotation-driven Listener Endpoints (@JmsListener): https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework 6.2 JmsListener API, selector attribute: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Boot Getting Started, Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- Apache ActiveMQ Artemis Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
