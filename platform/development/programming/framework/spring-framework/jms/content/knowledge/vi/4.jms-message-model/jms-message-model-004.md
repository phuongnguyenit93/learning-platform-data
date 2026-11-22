# MapMessage và tập thuộc tính có kiểu trong JMS

> **Ngữ cảnh:** Spring Framework – JMS, nhóm kiến thức **Mô hình Message**. Bài này giải thích hai tập dữ liệu có kiểu trên cùng một JMS message: **các cặp tên–giá trị trong body của `MapMessage`** và **message properties** nằm ngoài body, dùng cho metadata và message selector. Ví dụ sử dụng Java 21, Jakarta Messaging (JMS) 3.1, Spring Boot 3.3 và ActiveMQ Artemis.

## 1. Một JMS message có ba vùng khác nhau

Đừng nhầm body dạng Map với toàn bộ message. JMS tổ chức thông điệp thành ba phần:

```text
JMS Message (một đơn vị gửi/nhận)
├── Headers                 <-- do JMS định nghĩa
│   ├── JMSMessageID
│   ├── JMSCorrelationID
│   ├── JMSDestination
│   └── JMSRedelivered, ...
├── Properties              <-- các trường mở rộng có kiểu
│   ├── eventType = "OrderPaid"       (String)
│   ├── schemaVersion = 1            (int)
│   └── tenantId = "store-a"         (String)
└── Body: MapMessage        <-- nội dung nghiệp vụ dạng tên–giá trị
    ├── orderId = "ORD-42"           (String)
    ├── amountMinor = 125000L        (long)
    ├── itemCount = 2                (int)
    ├── verified = true              (boolean)
    └── proof = byte[]{1, 35}        (byte[])
```

- **Headers** là trường chuẩn của `jakarta.jms.Message`, chẳng hạn `getJMSMessageID()`, `getJMSCorrelationID()`. Chúng có API riêng, không phải các map entries.
- **Properties** là tập thuộc tính có kiểu có mặt trên **mọi loại JMS message** (`TextMessage`, `BytesMessage`, `MapMessage`...). Broker có thể dùng chúng để lọc theo **message selector**.
- **Body** chứa dữ liệu chính. Khi loại body là `MapMessage`, ta dùng `setString/getString`, `setInt/getInt`, `setBytes/getBytes`... và tên field để đọc/ghi.

**Quy tắc quan trọng:** `message.getString("orderId")` chỉ tồn tại trên `MapMessage` và truy cập **body**; `message.getStringProperty("eventType")` truy cập **properties**. Tên trùng nhau giữa hai vùng vẫn biểu thị **hai giá trị độc lập**. Message selector **không đọc được các field trong body `MapMessage`**.

## 2. `MapMessage` là gì, khác `java.util.Map` ở đâu?

`MapMessage` là subtype của `jakarta.jms.Message`, mô tả body như một tập **(String name, typed value)**. Provider tạo instance thông qua `Session.createMapMessage()` hoặc `JMSContext.createMapMessage()`. Ứng dụng không tự `new MapMessage()` vì đó là interface do provider triển khai.

Đặc tính:

- **Tên field** là `String` khác `null` và khác chuỗi rỗng; tên là khóa để truy cập ngẫu nhiên. Tên **phân biệt hoa/thường**: `orderId` khác `OrderId`.
- **Giá trị có kiểu cụ thể**; API cho phép truy cập theo tên, **không cần đọc tuần tự theo vị trí** như `StreamMessage`.
- **Không có thứ tự duyệt được bảo đảm**. `getMapNames()` trả `Enumeration` tên các field, nhưng không được dựa vào thứ tự nhận được để định nghĩa giao thức.
- Body **không phải** `Map<String,Object>` tùy ý: chỉ các loại giá trị mà Jakarta Messaging cho phép. Không nhét trực tiếp `List`, `HashMap` lồng nhau, `BigDecimal`, `LocalDate` hoặc domain object rồi kỳ vọng provider tự serialize.
- Có thể `getObject(name)` để lấy wrapper tương ứng (`Integer`, `Long`, `Boolean`, `Character`...), `String` hoặc `byte[]`; đối với field chưa tồn tại, `getObject` trả `null`.

So với các loại body khác:

| Loại JMS | Body | Phù hợp |
| --- | --- | --- |
| `TextMessage` | Một `String`, thường chứa JSON/XML/text | Giao thức liên ngôn ngữ hoặc schema JSON có đối tượng lồng nhau. |
| **`MapMessage`** | Các cặp tên–giá trị **kiểu nguyên thủy, String, byte[]** | Bản ghi phẳng, field có kiểu rõ, bên nhận JMS biết trước hợp đồng field. |
| `BytesMessage` | Luồng bytes | Protocol nhị phân tự định nghĩa, cần tự quản lý encoding/schema. |
| `StreamMessage` | Dãy giá trị có kiểu đọc theo thứ tự | Message có layout tuần tự đã thống nhất. |
| `ObjectMessage` | `Serializable` Java object | Trường hợp hai phía kiểm soát Java serialization; cần cân nhắc tương thích và an toàn deserialize. |

## 3. Những kiểu giá trị được phép trong body

| Kiểu giá trị | Phương thức ghi | Phương thức đọc | Ví dụ |
| --- | --- | --- | --- |
| `boolean` | `setBoolean(name, value)` | `getBoolean(name)` | `verified = true` |
| `byte` | `setByte` | `getByte` | `level = (byte) 2` |
| `short` | `setShort` | `getShort` | `batch = (short) 12` |
| **`char`** | `setChar` | `getChar` | `sourceCode = 'W'` |
| `int` | `setInt` | `getInt` | `itemCount = 2` |
| `long` | `setLong` | `getLong` | `amountMinor = 125000L` |
| `float` | `setFloat` | `getFloat` | `ratio = 0.5f` |
| `double` | `setDouble` | `getDouble` | `score = 0.75d` |
| `String` | `setString` | `getString` | `orderId = "ORD-42"` |
| **`byte[]`** | `setBytes` | `getBytes` | `proof = new byte[]{1, 35}` |

`setObject(name, value)` nhận các **wrapper** của kiểu nguyên thủy, `String` và `byte[]` (không nhận một POJO hoặc `Map` lồng nhau). `setBytes(name, bytes, offset, length)` còn cho phép chép một đoạn của mảng bytes.

Ví dụ minh họa API (đây là đoạn bên trong callback có `jakarta.jms.Session session`; không phải chương trình độc lập):

```java
MapMessage body = session.createMapMessage();
body.setString("orderId", "ORD-42");
body.setInt("itemCount", 2);
body.setLong("amountMinor", 125_000L);
body.setBoolean("verified", true);
body.setChar("sourceCode", 'W');
body.setBytes("proof", new byte[] { 0x01, 0x23 });

// Dạng tổng quát tương đương:
body.setObject("retriesAllowed", Integer.valueOf(3));

// Các trường sau không hợp lệ với MapMessage.setObject:
// body.setObject("items", List.of("A", "B"));
// body.setObject("price", new BigDecimal("12.50"));
```

Đối với tiền tệ, nên dùng **đơn vị nhỏ nhất dạng số nguyên** như `amountMinor` kèm `currency` nếu miền nghiệp vụ phù hợp; đừng phụ thuộc độ chính xác nhị phân của `double` cho phép tính tiền. Với dữ liệu thời gian, quy ước `long` epoch milliseconds hoặc `String` ISO-8601 và ghi rõ đơn vị, múi giờ, phiên bản schema.

### `MapMessage` không tự làm thay nhiệm vụ thiết kế schema

Hai consumer có thể đều biết field `amountMinor` nhưng hiểu khác đơn vị nếu hợp đồng không nói rõ. Hãy thống nhất:

1. Tên field và chính xác kiểu setter (ví dụ `amountMinor: long`).
2. Field bắt buộc/tùy chọn; ý nghĩa của field vắng mặt hoặc null.
3. Đơn vị đo, enum, miền giá trị và ràng buộc.
4. Cách nâng phiên bản schema để worker cũ không đọc sai giá trị.

## 4. Quy tắc đọc kiểu và chuyển đổi trong `MapMessage`

Không phải mọi `getXxx` đều chuyển đổi được mọi kiểu. Đặc tả có **bảng chuyển đổi bắt buộc**; từ `row type` (kiểu đã ghi) sang các `getter` được phép:

| Đã ghi bằng kiểu | Có thể đọc bằng getter |
| --- | --- |
| `boolean` | `getBoolean`, `getString` |
| `byte` | `getByte`, `getShort`, `getInt`, `getLong`, `getString` |
| `short` | `getShort`, `getInt`, `getLong`, `getString` |
| `char` | `getChar`, `getString` |
| `int` | `getInt`, `getLong`, `getString` |
| `long` | `getLong`, `getString` |
| `float` | `getFloat`, `getDouble`, `getString` |
| `double` | `getDouble`, `getString` |
| `String` | `getString` và các getter boolean, byte, short, int, long, float, double nếu parse được; **không** có chuyển sang `char` |
| `byte[]` | `getBytes` |

Các cột không được hỗ trợ phải báo `MessageFormatException`. Khi đọc chuỗi như một số mà chuỗi không thể parse, Jakarta Messaging quy định `NumberFormatException`. Với `getBoolean` từ `String`, quy tắc `Boolean.valueOf(String)` áp dụng; các chuỗi khác `"true"` (không phân biệt hoa/thường) trở thành `false`, nên cần validate đầu vào nếu muốn chỉ chấp nhận đúng `true/false`.

Ví dụ:

```java
MapMessage m = session.createMapMessage();
m.setInt("itemCount", 2);
m.setString("retryAfterSeconds", "30");
m.setDouble("ratio", 0.75);

long a = m.getLong("itemCount");              // Hợp lệ: int -> long
int b = m.getInt("retryAfterSeconds");        // Hợp lệ: String "30" -> int
String c = m.getString("ratio");              // Hợp lệ: double -> String

// m.getInt("ratio");                         // MessageFormatException
// m.getChar("retryAfterSeconds");            // MessageFormatException
// m.getBytes("itemCount");                   // MessageFormatException
```

**Đừng áp dụng trực giác ép kiểu Java:** `int -> double` **không nằm trong bảng chuyển đổi của `MapMessage`**, dù Java có phép mở rộng đó trong code bình thường. Nếu producer muốn float/double, hãy gửi đúng kiểu giao thức.

### Field thiếu, null và kiểm tra trước khi đọc

`itemExists(name)` giúp phân biệt **field không được ghi** với một field đang hiện diện. `getObject("missing")` trả `null` nếu field vắng. Theo đặc tả, đọc field vắng qua getter nguyên thủy được xử lý giống chuyển đổi từ chuỗi null; chẳng hạn `getChar` khi thiếu field phải ném `NullPointerException`, còn `getInt` có thể dẫn tới `NumberFormatException`. Với boolean, chuyển đổi `Boolean.valueOf(null)` cho `false`, dễ nhầm “không có dữ liệu” thành giá trị hợp lệ.

Nên kiểm tra tồn tại trước và kiểm tra kiểu/giá trị hợp đồng:

```java
if (!m.itemExists("itemCount")) {
    throw new IllegalArgumentException("Missing itemCount");
}
Object value = m.getObject("itemCount");
if (!(value instanceof Integer)) {
    throw new IllegalArgumentException("itemCount must be an int");
}
int itemCount = (Integer) value;
if (itemCount < 0) {
    throw new IllegalArgumentException("itemCount must be non-negative");
}
```

Đoạn kiểm tra là một **mảnh code**, dùng `m` đã tạo ở ví dụ phía trên. Trong hệ thống thực tế, lỗi dữ liệu cần được phân loại để tránh retry vô hạn cùng một thông điệp hỏng.

## 5. Message properties: cũng có kiểu, nhưng **không nằm trong MapMessage body**

Mọi `jakarta.jms.Message` đều có nhóm phương thức:

```java
message.setStringProperty("eventType", "OrderPaid");
message.setIntProperty("schemaVersion", 1);
message.setBooleanProperty("requiresAudit", true);

String type = message.getStringProperty("eventType");
int version = message.getIntProperty("schemaVersion");
boolean audit = message.getBooleanProperty("requiresAudit");
```

**Khác biệt thiết yếu giữa hai tập có kiểu:**

| Tiêu chí | `MapMessage` body entries | `Message` properties |
| --- | --- | --- |
| Mục đích | Dữ liệu nghiệp vụ | Metadata định tuyến/lọc, phân loại và điều khiển theo ứng dụng |
| API ghi | `setInt("itemCount", 2)` | `setIntProperty("schemaVersion", 1)` |
| API đọc | `getInt("itemCount")` | `getIntProperty("schemaVersion")` |
| Kiểu hỗ trợ | `boolean, byte, short, char, int, long, float, double, String, byte[]` | `boolean, byte, short, int, long, float, double, String` |
| Có `char` và `byte[]`? | **Có** | **Không** |
| Tên hợp lệ | `String` khác null và rỗng | Phải tuân theo cú pháp identifier của message selector |
| Duyệt tên | `getMapNames()` | `getPropertyNames()` |
| Kiểm tra tên | `itemExists(name)` | `propertyExists(name)` |
| Xóa và cho phép sửa phần đã nhận | `clearBody()` | `clearProperties()` |
| Message selector nhìn thấy? | **Không** | **Có**, nếu property có mặt và selector hợp lệ |

`setObjectProperty` chỉ nhận `Boolean, Byte, Short, Integer, Long, Float, Double, String`. Không nhận `Character`, `byte[]`, `BigDecimal` hoặc `List`. Tập giá trị của properties là một phần của hợp đồng JMS, không phụ thuộc việc body là `MapMessage` hay `TextMessage`.

Tên property phải tuân theo quy tắc identifier: có thể bắt đầu bằng chữ, `_` hoặc ký tự Java identifier hợp lệ, tiếp theo là các ký tự identifier; không dùng tên trống hoặc các từ khóa selector như `AND`, `NULL`, `TRUE`. Ví dụ `schemaVersion` hợp lệ; `order-status` không phù hợp để dùng trực tiếp làm identifier trong selector. Tên property **phân biệt hoa/thường**.

### Headers và chuẩn `JMSX` không phải properties tự định nghĩa tùy tiện

- `JMSMessageID`, `JMSCorrelationID`, `JMSPriority`, `JMSDestination`... là **headers**, có getter/setter tương ứng như `getJMSCorrelationID()`; chúng không xuất hiện trong `getPropertyNames()`.
- Jakarta Messaging giữ tiền tố **`JMSX`** cho properties chuẩn, chẳng hạn `JMSXDeliveryCount` (do provider ghi khi receive, từ 1 trở lên) và `JMSXGroupID` (group ID cho message grouping). **Đừng tạo tên ứng dụng bắt đầu bằng `JMSX`**.
- Tiền tố **`JMS_<vendor_name>`** thuộc không gian property riêng của nhà cung cấp. Đặt metadata ứng dụng bằng tên trung tính như `eventType` hoặc `schemaVersion`.
- `JMSXDeliveryCount >= 2` thường báo message được giao lại, nhưng bản thân con số không phải cơ chế chống trùng business side effects; luôn thiết kế consumer idempotent.

## 6. Cơ chế message selector: lý do nên đặt metadata ở properties

Một consumer muốn nhận `OrderPaid` phiên bản schema 1 có thể khai báo selector:

```sql
eventType = 'OrderPaid' AND schemaVersion = 1
```

Producer phải đặt:

```java
message.setStringProperty("eventType", "OrderPaid");
message.setIntProperty("schemaVersion", 1);
```

**Không có tác dụng với selector** nếu chỉ gọi:

```java
message.setString("eventType", "OrderPaid"); // Body của MapMessage
message.setInt("schemaVersion", 1);          // Body của MapMessage
```

Vì selector chỉ nhìn vào headers/properties, các field trong body **không được tự động ánh xạ thành properties**.

**Lưu ý về kiểu trong selector:** dù `getIntProperty("schemaVersion")` có thể parse một chuỗi `"1"` theo quy tắc getter, selector `schemaVersion = 1` **không tự áp dụng phép chuyển kiểu khi gọi getter**. Nếu producer gửi `setStringProperty("schemaVersion", "1")`, so sánh số này không tương đương `setIntProperty(..., 1)`. Hãy thống nhất kiểu property từ đầu và kiểm thử với broker thật.

Selector dùng cú pháp tương tự một phần SQL92; giá trị chuỗi dùng dấu nháy đơn. Property không tồn tại có giá trị logic `NULL` trong selector, và so sánh với nó không mặc nhiên bằng `true`. Dùng `IS NULL`/`IS NOT NULL` khi cần biểu đạt rõ điều kiện thiếu.

**Thiết kế:** chỉ thêm metadata phục vụ định tuyến, phân loại, theo dõi vào properties; đặt chi tiết đơn hàng và payload lớn trong body. Nhiều property dài hoặc quá nhiều property có thể làm tăng chi phí cho broker và selector.

## 7. Ví dụ Spring Boot 3.3 + Artemis: gửi và nhận đúng `MapMessage`

Ví dụ tối thiểu này dùng **Java 21**, **Spring Boot 3.3.5**, **Jakarta JMS**, một **queue** có tên `orders.typed`. Nhiệm vụ ở đây là mô hình Message; queue được dùng để tránh trộn thêm topic/subscription vào ví dụ.

Yêu cầu môi trường: broker **ActiveMQ Artemis đang hoạt động** tại `tcp://localhost:61616`, có queue `orders.typed` hoặc chính sách auto-create phù hợp. Nếu broker cần xác thực, cấu hình tài khoản Artemis qua biến môi trường `SPRING_ARTEMIS_USER` và `SPRING_ARTEMIS_PASSWORD`; ví dụ không cung cấp mật khẩu cứng.

### 7.1 Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'typed-map-jms-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
  jms:
    pub-sub-domain: false
    listener:
      session:
        transacted: true
server:
  port: 8080
```

`session.transacted: true` minh họa cơ chế nhận/commit tại listener; một lỗi xử lý chưa commit sẽ khiến lần nhận bị rollback và có thể redeliver theo cấu hình broker. Nó **không tự tạo transaction xuyên DB và JMS**.

### 7.2 Java source hoàn chỉnh

Tạo `src/main/java/com/example/typedmap/TypedMapJmsApplication.java`:

```java
package com.example.typedmap;

import java.util.Arrays;

import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableJms
public class TypedMapJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TypedMapJmsApplication.class, args);
    }
}

@RestController
class TypedOrderSender {
    private final JmsTemplate jmsTemplate;

    TypedOrderSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @PostMapping("/orders/demo")
    ResponseEntity<String> sendDemo() {
        jmsTemplate.send("orders.typed", session -> {
            MapMessage message = session.createMapMessage();

            // BODY: các field nghiệp vụ có kiểu
            message.setString("orderId", "ORD-42");
            message.setLong("amountMinor", 125_000L);
            message.setString("currency", "VND");
            message.setInt("itemCount", 2);
            message.setBoolean("verified", true);
            message.setChar("sourceCode", 'W');
            message.setBytes("proof", new byte[] { 0x01, 0x23 });

            // PROPERTIES: metadata để broker lọc theo selector
            message.setStringProperty("eventType", "OrderPaid");
            message.setIntProperty("schemaVersion", 1);

            // HEADER: thuộc tính chuẩn JMS, không nằm trong body
            message.setJMSCorrelationID("req-42");
            return message;
        });

        return ResponseEntity.accepted().body("ENQUEUED ORD-42");
    }
}

@Component
class TypedOrderConsumer {
    @JmsListener(
            destination = "orders.typed",
            selector = "eventType = 'OrderPaid' AND schemaVersion = 1")
    public void receive(MapMessage message) throws JMSException {
        // Raw MapMessage được Spring @JmsListener hỗ trợ.
        if (!message.itemExists("orderId")
                || !message.itemExists("amountMinor")) {
            throw new IllegalArgumentException("Missing required body fields");
        }

        System.out.printf(
                "BODY orderId=%s amountMinor=%d currency=%s "
                + "itemCount=%d verified=%b sourceCode=%c proof=%s%n",
                message.getString("orderId"),
                message.getLong("amountMinor"),
                message.getString("currency"),
                message.getInt("itemCount"),
                message.getBoolean("verified"),
                message.getChar("sourceCode"),
                Arrays.toString(message.getBytes("proof")));

        System.out.printf(
                "META eventType=%s schemaVersion=%d correlation=%s%n",
                message.getStringProperty("eventType"),
                message.getIntProperty("schemaVersion"),
                message.getJMSCorrelationID());
    }
}
```

Phân tích từng phần:

1. `JmsTemplate.send(destination, messageCreator)` gọi callback với `Session` thực và gửi chính đối tượng `MapMessage` được tạo. Không có JSON, không cần `Serializable` hoặc custom converter.
2. `setString/setLong/setInt/setBoolean/setChar/setBytes` ghi vào **body**. `setStringProperty/setIntProperty` ghi vào **properties**. `setJMSCorrelationID` ghi vào **header**.
3. Listener nhận trực tiếp `MapMessage`; Spring JMS hỗ trợ argument kiểu raw `jakarta.jms.Message` hoặc subclass phù hợp. Ta đọc body/properties/header bằng ba nhóm API tương ứng.
4. `selector` chỉ xét properties. Nhờ `eventType` và `schemaVersion` được gắn đúng vùng/kiểu, thông điệp phù hợp sẽ được consumer xử lý.
5. `@EnableJms` bật cơ chế listener annotation. Spring Boot tự cấu hình `ConnectionFactory`/`JmsTemplate` từ Artemis starter khi môi trường phù hợp.
6. Việc API trả HTTP 202 chỉ báo producer đã giao lệnh gửi thành công theo cấu hình. Nó **không bảo đảm** listener đã xử lý xong hay downstream đã commit business transaction.

### 7.3 Chạy và kết quả có thể quan sát

Khởi động broker trước. Trong project Gradle có wrapper:

```bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
```

Gửi message:

```bash
curl -i -X POST http://localhost:8080/orders/demo
```

HTTP response dự kiến chứa status `202 Accepted` và body:

```text
ENQUEUED ORD-42
```

Một trích đoạn stdout của listener **sau khi** message được broker chuyển tới:

```text
BODY orderId=ORD-42 amountMinor=125000 currency=VND itemCount=2 verified=true sourceCode=W proof=[1, 35]
META eventType=OrderPaid schemaVersion=1 correlation=req-42
```

Hai dòng trên có nội dung xác định từ các field; **thời điểm xuất hiện** so với HTTP response và các Spring startup logs phụ thuộc scheduling/broker. Nếu broker không hoạt động, có lỗi xác thực hoặc queue chưa được tạo theo chính sách, ví dụ sẽ không gửi/nhận thành công; đó là phụ thuộc môi trường, không phải kết quả chuẩn đầu ra.

### 7.4 Dùng Spring `convertAndSend` với một Java Map

Khi ứng dụng dùng `SimpleMessageConverter` mặc định, một `java.util.Map` chứa các kiểu được JMS hỗ trợ có thể được chuyển thành `MapMessage`. `MessagePostProcessor` thêm properties/headers trước khi gửi:

```java
Map<String, Object> payload = new LinkedHashMap<>();
payload.put("orderId", "ORD-42");
payload.put("amountMinor", 125_000L);
payload.put("verified", true);

jmsTemplate.convertAndSend("orders.typed", payload, message -> {
    message.setStringProperty("eventType", "OrderPaid");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
```

Đây là **đoạn code minh họa**, cần import `java.util.Map`, `java.util.LinkedHashMap` và có sẵn biến `JmsTemplate jmsTemplate`. Nó không tương đương một cơ chế mapping mọi object: `Map<String,Object>` vẫn phải chỉ chứa **giá trị hợp lệ của `MapMessage`**; custom `MessageConverter` có thể thay đổi loại message trên wire. Ví dụ chạy đầy đủ phía trên dùng `session.createMapMessage()` để thấy rõ điều gì được gửi.

## 8. Duyệt các field, kiểm tra hợp đồng và metadata

Khi không biết trước toàn bộ tên field (chẳng hạn viết công cụ debug), có thể duyệt tên:

```java
// Trích đoạn bên trong listener, với MapMessage message:
for (java.util.Enumeration<?> names = message.getMapNames();
        names.hasMoreElements();) {
    String name = (String) names.nextElement();
    Object value = message.getObject(name);
    System.out.println("body field: " + name + "=" + value);
}

for (java.util.Enumeration<?> names = message.getPropertyNames();
        names.hasMoreElements();) {
    String name = (String) names.nextElement();
    Object value = message.getObjectProperty(name);
    System.out.println("message property: " + name + "=" + value);
}
```

**Không dựa vào thứ tự in ra:** `getMapNames()` và `getPropertyNames()` đều không cam kết thứ tự. `byte[]` khi in qua `Object.toString()` không có dạng dễ đọc; dùng `Arrays.toString`/hex/Base64 theo hợp đồng và **không log thông tin nhạy cảm**. `getPropertyNames()` cũng không liệt kê các header chuẩn.

Trong consumer nghiệp vụ, thường không cần duyệt động: kiểm tra các field bắt buộc và đọc đúng kiểu; reject schema không hỗ trợ. Nếu cần schema evolvable, cho phép **field mới có thể bỏ qua** nhưng không tự đổi kiểu field cũ; dùng `schemaVersion` trong properties và các test tương thích producer/consumer.

## 9. Quy tắc read-only và việc `clearBody`/`clearProperties`

Khi message **mới được tạo**, có thể ghi body và properties. Khi được **nhận từ broker**, body và properties ở chế độ **read-only** để provider quản lý an toàn. Ghi trực tiếp sau receive có thể ném `MessageNotWriteableException`.

Hai thao tác thay đổi trạng thái **độc lập**:

| Gọi hàm | Xóa dữ liệu gì? | Phần nào có thể ghi lại? |
| --- | --- | --- |
| `message.clearBody()` | Toàn bộ body entries của `MapMessage` | Body; properties cũ vẫn còn. |
| `message.clearProperties()` | Toàn bộ properties | Properties; body cũ vẫn còn. |

Không dùng `clearBody` để xóa metadata hoặc `clearProperties` để xóa body. Những lệnh này thay đổi **đối tượng message đang thao tác**, không phải cách “xóa một tin nhắn đã được broker nhận” hay tự ACK nó. Khi cần tạo message mới, thông thường hãy dùng `session.createMapMessage()` mới và copy các field đã kiểm tra, tránh tái sử dụng/mutate message nhận rồi gửi lại không có kế hoạch.

**Không có API chuẩn để xóa riêng một property** sau khi đã thêm; `clearProperties()` xóa cả tập. Với body `MapMessage`, cũng không có `remove(field)` tương đương `java.util.Map.remove`; dựng body mới nếu cần thay đổi cấu trúc đáng kể.

## 10. Xử lý sai kiểu, dữ liệu thiếu và tính tương thích

| Tình huống | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Producer `setDouble("amountMinor", 125000.0)`; consumer `getLong` | `MessageFormatException` do bảng chuyển đổi không cho double → long. | Thống nhất dùng `long` ngay từ schema, kiểm thử kiểu thật. |
| Producer `setString("itemCount", "two")`; consumer `getInt` | `NumberFormatException` khi parse. | Validate dữ liệu phía gửi; đừng gửi số dưới dạng text nếu không cần. |
| Consumer đọc `getBoolean("verified")` khi field thiếu | Có thể nhận `false` như một conversion từ null, làm che giấu thiếu dữ liệu. | Kiểm tra `itemExists("verified")` trước. |
| Producer gửi `List` hoặc `BigDecimal` bằng `setObject` | `MessageFormatException` vì kiểu không hỗ trợ. | Thiết kế flat scalar schema hoặc dùng `TextMessage`/JSON, schema rõ ràng. |
| Producer đặt `eventType` trong body nhưng consumer dùng selector | Selector không nhìn thấy body; message không được chọn theo điều kiện đó. | Đặt metadata ở `setStringProperty`. |
| Producer dùng `setStringProperty("schemaVersion", "1")` nhưng selector là `schemaVersion = 1` | Type mismatch trong selector; getter conversion không được tự động áp dụng. | Dùng `setIntProperty` và kiểm thử selector. |
| Consumer cố sửa body của message nhận | `MessageNotWriteableException`. | Xử lý read-only; tạo message mới nếu cần transform rồi publish. |
| Thêm field mới nhưng thay tên/kiểu field cũ mà không đổi version | Consumer cũ có thể đọc sai hoặc lỗi. | Version hóa và triển khai tương thích trước–sau. |
| Đặt `JMSXDeliveryCount` như property của ứng dụng | Chiếm tên tiêu chuẩn do provider quản lý. | Dùng property tên ứng dụng, đọc `JMSXDeliveryCount` chỉ để quan sát delivery attempts. |
| Dùng `double` lưu tiền, không có đơn vị hoặc currency | Sai số hoặc consumer hiểu khác đơn vị. | Số nguyên minor units hoặc số thập phân dạng chuỗi theo schema đã thống nhất. |

### MapMessage giải quyết kiểu dữ liệu, không giải quyết tự động độ tin cậy

Bản thân `MapMessage` không quyết định message là persistent, có bị redeliver, có vào DLQ, thứ tự xử lý hay exactly-once business outcome. Các tính chất đó phụ thuộc JMS delivery mode, broker, transaction/ACK, retry và thiết kế idempotency. Nếu consumer xử lý DB thành công rồi lỗi trước JMS ACK, toàn bộ message (headers/properties/body) có thể được giao lại; hãy mang `eventId` ổn định và chống trùng ở nơi ghi kết quả nghiệp vụ.

Đối với trao đổi dài hạn giữa nhiều phiên bản hoặc nhiều ngôn ngữ, đánh giá khả năng tương thích provider/protocol, chọn schema có version và có thể cân nhắc `TextMessage` JSON hoặc schema nhị phân có hợp đồng cụ thể. `MapMessage` tiện cho JMS clients trao đổi **các trường phẳng có kiểu**, nhưng không thay thế chiến lược schema evolution.

## 11. Bài tập thực hành và câu hỏi kiểm tra

1. Sửa ví dụ để thêm `createdAtEpochMs: long` vào body; thêm `tenantId: String` vào properties. Viết selector chỉ nhận `tenantId = 'store-a' AND schemaVersion = 1`. Tại sao `createdAtEpochMs` không dùng trực tiếp trong selector?
2. Chuyển `itemCount` từ `int` sang `String` có giá trị `"2"`. `getInt("itemCount")` có thể chạy được không? Vì sao vẫn không nên âm thầm đổi kiểu trong hợp đồng?
3. Sử dụng `setChar("sourceCode", 'W')`, sau đó thử `getString("sourceCode")`. Vì sao `char` có trong `MapMessage` nhưng không nằm trong property API?
4. Thêm field `proof: byte[]`; vì sao `setObjectProperty("proof", new byte[]{...})` không hợp lệ? Nếu cần lọc dựa trên trạng thái của chứng từ, bạn nên dùng property nào thay cho raw bytes?
5. Phân biệt `itemExists("verified")` và `propertyExists("verified")` khi cùng tên xuất hiện ở cả body và properties.
6. Nêu sự khác nhau giữa `clearBody` và `clearProperties` trên message nhận; tại sao không nên dùng chúng để “sửa” dữ liệu vừa nhận nhằm xử lý lỗi?
7. Thử một field không tồn tại và một field có sai kiểu; nêu ngoại lệ/giá trị có thể xảy ra với `getObject`, `getInt`, `getBoolean` và `getChar`. Vì sao consumer cần kiểm tra field bắt buộc?
8. Giải thích vì sao `JMSXDeliveryCount=2` không có nghĩa chỉ mới xử lý hai lần ở tầng nghiệp vụ; cần cơ chế nào để chống trùng?

**Ghi nhớ:** `MapMessage` lưu **body gồm các field phẳng có kiểu**; message properties là **metadata có kiểu trên mọi JMS message**, có thể được broker dùng trong selectors; headers là **trường JMS chuẩn**. Chọn đúng vùng dữ liệu, đúng setter/getter, đúng kiểu schema và kiểm tra field thiếu sẽ tránh phần lớn lỗi tương tác giữa producer, consumer và broker.

### Tài liệu tham khảo

- [Jakarta Messaging 3.1 – MapMessage API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/mapmessage) — kiểu body, accessor, conversion và `itemExists`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — mục 3.5, 3.8, 3.11: properties, selectors, body read-only, conversion.
- [Jakarta Messaging 3.1 – Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — headers, properties, `clearBody`, `clearProperties`, `JMSXDeliveryCount`.
- [Spring Framework – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — raw `MapMessage` parameter, `@JmsListener` và `selector`.
- [Spring Framework – Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate.send`, `SimpleMessageConverter` map-to-`MapMessage` và `MessagePostProcessor`.
