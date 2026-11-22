# Phân biệt kiểu chuỗi với kiểu số trong JMS message property và selector

## 1. Vì sao một giá trị “12” có thể không được lọc?

Trong **Spring Framework JMS**, một producer có thể gửi hai message cùng có property tên `orderCount` và người đọc console nhìn thấy cùng giá trị “12”. Nhưng hai message đó không nhất thiết khớp cùng một **JMS message selector**:

```java
// Message A: property có kiểu int.
messageA.setIntProperty("orderCount", 12);

// Message B: property có kiểu String.
messageB.setStringProperty("orderCount", "12");
```

Sau đó một consumer được cấu hình selector:

```sql
orderCount = 12
```

sẽ khớp với **message A**, không khớp với **message B**. Ngược lại:

```sql
orderCount = '12'
```

sẽ khớp với **message B**, không khớp với **message A**.

Dấu nháy đơn quanh `'12'` **không chỉ là một cách trình bày**: theo cú pháp selector của Jakarta Messaging, đó là **String literal**. Số `12` không có nháy đơn là **numeric literal**. JMS selector không âm thầm ép String `"12"` thành số 12 trước khi so sánh.

Bài học này tập trung vào **đúng một vấn đề: kiểu dữ liệu của JMS property tác động thế nào tới cú pháp và kết quả lọc thông điệp**. Đây là nguyên nhân phổ biến của lỗi “Queue có message nhưng consumer với selector không nhận được”.

### Hình dung luồng xử lý

```text
Producer A                              Producer B
setIntProperty("orderCount", 12)        setStringProperty("orderCount", "12")
           |                                       |
           +-------------------+-------------------+
                               |
                          JMS Queue
                               |
                    Consumer với selector
                        orderCount = 12
                               |
                    chỉ message A khớp
                               |
                        Spring handler
```

Một selector chỉ nhận những message mà biểu thức đánh giá thành **TRUE**. Kết quả **FALSE** hoặc **UNKNOWN** không làm message đó được giao cho consumer có selector ấy.

## 2. JMS property là gì? Khác gì body và header?

Một JMS message có ba vùng khái niệm:

1. **Headers**: trường chuẩn do JMS quy định như `JMSMessageID`, `JMSPriority`, `JMSCorrelationID`, `JMSType` (với phạm vi dùng trong selector do đặc tả giới hạn).
2. **Properties**: các cặp tên–giá trị bổ sung do ứng dụng hoặc provider gắn vào message, ví dụ `orderCount`, `region`, `retryCount`.
3. **Body**: nội dung chính của `TextMessage`, `BytesMessage`, `MapMessage` v.v.

**JMS selector đọc một số JMS header và message property; nó không truy vấn trực tiếp JSON/XML hay field của body.**

Ví dụ message sau có body text:

```json
{"orderId":"O-101","amount":120}
```

Nếu producer chỉ tạo `TextMessage` chứa JSON này mà **không** đặt property `amount`, selector:

```sql
amount > 100
```

không tìm được một property tên `amount`; kết quả biểu thức là **UNKNOWN**, không phải TRUE. Muốn lọc bằng selector, producer phải ghi property riêng trước khi gửi:

```java
TextMessage msg = session.createTextMessage(
        "{\"orderId\":\"O-101\",\"amount\":120}"
);
msg.setIntProperty("amount", 120);
```

Đây là **snippet trong một `MessageCreator` hoặc trong một method có `Session` hợp lệ**, không phải chương trình Java chạy độc lập.

### Các kiểu property chuẩn

Jakarta Messaging hỗ trợ đúng các nhóm giá trị property sau:

| Kiểu khi ghi | Java/Jakarta Messaging API | Ví dụ |
| --- | --- | --- |
| Boolean | `setBooleanProperty` | `setBooleanProperty("paid", true)` |
| Byte | `setByteProperty` | `setByteProperty("level", (byte) 2)` |
| Short | `setShortProperty` | `setShortProperty("attempts", (short) 3)` |
| Integer | `setIntProperty` | `setIntProperty("count", 12)` |
| Long | `setLongProperty` | `setLongProperty("amountMinor", 12000L)` |
| Float | `setFloatProperty` | `setFloatProperty("score", 12.5F)` |
| Double | `setDoubleProperty` | `setDoubleProperty("score", 12.5D)` |
| String | `setStringProperty` | `setStringProperty("count", "12")` |

Không có property type chuẩn riêng cho `BigDecimal`, `LocalDate`, `UUID` hoặc một Java bean tùy ý. `setObjectProperty` chỉ nhận các wrapper `Boolean`, `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` và `String` theo đặc tả. Đừng giả định `setObjectProperty("price", new BigDecimal("1.25"))` là hợp lệ trên mọi JMS provider.

**Tên property và kiểu của property được xác định khi producer ghi nó**; hai thông tin ấy phải được thống nhất giữa producer, consumer và tài liệu schema sự kiện.

## 3. Đặt property bằng setter nào thì selector hiểu kiểu đó

### 3.1. Ghi đúng numeric property

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage msg = session.createTextMessage("ORDER-001");
    msg.setIntProperty("orderCount", 12);
    msg.setLongProperty("amountMinor", 105_000L);
    msg.setDoubleProperty("riskScore", 0.75D);
    return msg;
});
```

Đoạn trên cần biến `JmsTemplate jmsTemplate` từ Spring và import `jakarta.jms.TextMessage`; các Queue/provider phải đã sẵn sàng.

Các selector tương ứng:

```sql
orderCount = 12
amountMinor >= 100000
riskScore > 0.5
```

Vì các giá trị mang kiểu số, chúng có thể dùng phép so sánh số và các biểu thức số khác mà đặc tả cho phép. Mệnh đề `amountMinor >= 100000` áp dụng lên giá trị `long` theo quy tắc promotion số của selector.

### 3.2. Ghi String property dù nội dung trông giống số

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage msg = session.createTextMessage("ORDER-002");
    msg.setStringProperty("orderCount", "12");
    msg.setStringProperty("postalCode", "00123");
    return msg;
});
```

Các selector phù hợp là:

```sql
orderCount = '12'
postalCode = '00123'
```

`postalCode` là **định danh**, không phải đại lượng để cộng/trừ: giữ `String` là lựa chọn đúng vì `"00123"` phải giữ số 0 đầu. `orderCount` đại diện số lượng, nên nếu producer muốn consumer so sánh số, tốt hơn ghi `int` ngay từ đầu.

**Không nên dùng `String` chỉ vì giá trị ban đầu đến từ HTTP JSON, CSV, file cấu hình hoặc biểu mẫu.** Ứng dụng phải parse/validate ở tầng producer và đặt **đúng property type** khi gửi JMS.

### 3.3. `setObjectProperty` không đồng nghĩa “tất cả thành String”

```java
msg.setObjectProperty("countA", Integer.valueOf(12));
msg.setObjectProperty("countB", "12");
```

- `countA` có kiểu `Integer` và khớp `countA = 12`.
- `countB` có kiểu `String` và khớp `countB = '12'`.

Khi dùng `setObjectProperty`, kiểu wrapper của object rất quan trọng. Ví dụ `Integer.valueOf(12)` không giống `"12"`.

## 4. Literal trong cú pháp JMS selector: có nháy hay không?

JMS message selector sử dụng **một tập con của cú pháp biểu thức điều kiện SQL-92**. Nó **không phải** câu SQL hoàn chỉnh và không được áp dụng các quy tắc ép kiểu tự động của cơ sở dữ liệu.

| Literal selector | Kiểu ý nghĩa | Ví dụ hợp lệ |
| --- | --- | --- |
| `12` | Số nguyên chính xác (exact numeric) | `orderCount = 12` |
| `-5` | Số âm | `balanceDelta < 0` |
| `12.5` | Số xấp xỉ (approximate numeric) | `riskScore >= 12.5` |
| `'12'` | String, **không phải số** | `orderCount = '12'` |
| `'PAID'` | String | `paymentState = 'PAID'` |
| `TRUE` / `FALSE` | Boolean | `isPaid = TRUE` |
| `'true'` | String | `isPaid = 'true'` |
| `NULL` | Giá trị không xác định trong phép kiểm tra null | `orderCount IS NULL` |

**Dấu nháy kép** `"12"` trong Java thường là dấu bao một **Java String chứa selector**, không phải ký hiệu của String literal ở ngôn ngữ selector. Ví dụ:

```java
String numericSelector = "orderCount = 12";
String textSelector = "orderCount = '12'";
```

Biểu thức thứ nhất có literal số; biểu thức thứ hai có literal chuỗi. Ký tự nháy đơn nằm **bên trong** chuỗi Java, nên không cần escape trong Java source.

Dùng **nháy đơn** để bao string trong selector. Nếu giá trị chuỗi có ký tự nháy đơn, phải nhân đôi nó trong literal:

```java
String selector = "customerName = 'O''Brien'";
```

Ví dụ này so khớp property `customerName` có giá trị `O'Brien`.

### Bảng dự đoán kết quả

Giả sử tại thời điểm selector được kiểm tra, message thật sự có đúng kiểu property trong cột thứ hai:

| Property đã ghi | Kiểu thực tế | Selector | Kết quả |
| --- | --- | --- | --- |
| `setIntProperty("n", 12)` | int | `n = 12` | TRUE |
| `setIntProperty("n", 12)` | int | `n = '12'` | FALSE |
| `setStringProperty("n", "12")` | String | `n = '12'` | TRUE |
| `setStringProperty("n", "12")` | String | `n = 12` | FALSE |
| `setStringProperty("n", "12")` | String | `n > 10` | FALSE |
| `setLongProperty("n", 12L)` | long | `n > 10` | TRUE |
| `setDoubleProperty("n", 12.5)` | double | `n >= 12` | TRUE |
| `setBooleanProperty("paid", true)` | boolean | `paid = TRUE` | TRUE |
| `setStringProperty("paid", "true")` | String | `paid = TRUE` | FALSE |
| `setStringProperty("paid", "true")` | String | `paid = 'true'` | TRUE |
| Không đặt property `n` | Không tồn tại | `n = 12` | UNKNOWN |
| Không đặt property `n` | Không tồn tại | `n IS NULL` | TRUE |

*TRUE* nghĩa là message được chọn; *FALSE* và *UNKNOWN* đều không được giao cho consumer mang selector đó.

## 5. Quy tắc quan trọng: getter có thể ép kiểu, selector thì không

Đây là nguồn gây nhầm lẫn rất phổ biến:

```java
msg.setStringProperty("orderCount", "12");

String raw = msg.getStringProperty("orderCount"); // "12"
int parsed = msg.getIntProperty("orderCount");    // 12
```

Theo **bảng chuyển đổi property khi đọc** của Jakarta Messaging, việc lấy `String` property dưới dạng số qua `getIntProperty` có thể được hỗ trợ, nếu chuỗi biểu diễn một số nguyên hợp lệ.

Nhưng selector:

```sql
orderCount > 10
```

**không áp dụng** bảng chuyển đổi dùng cho getter. `orderCount` vẫn là **String** vì nó được đặt bằng `setStringProperty`. So sánh số là không phù hợp kiểu, kết quả **FALSE**.

```text
Producer ghi setStringProperty("orderCount", "12")
                     |
                     +--> getIntProperty("orderCount")
                     |    bảng conversion khi ĐỌC -> int 12
                     |
                     +--> selector "orderCount > 10"
                          KHÔNG áp bảng conversion -> FALSE
```

Đặc tả Jakarta Messaging nêu rõ **type của property trong selector tương ứng với type dùng khi đặt property**, và những chuyển đổi cho property getter **không được áp dụng khi chạy selector**.

### Các trường hợp getter khác

- `getStringProperty("count")` có thể chuyển số nguyên 12 thành chuỗi `"12"`. Điều này **không** làm property gốc biến thành String trong selector.
- `getIntProperty("count")` trên String `"12"` có thể trả 12.
- `getIntProperty("count")` trên String `"12x"` phải báo `NumberFormatException` nếu parse không hợp lệ.
- Hướng chuyển đổi không nằm trong bảng hỗ trợ có thể báo `MessageFormatException`.
- `getObjectProperty("count")` giúp kiểm tra **kiểu thực tế**: một property int trả wrapper `Integer`, còn String property trả `String`.

**Đừng dùng thành công của `getIntProperty` làm bằng chứng rằng selector số phải match.** Hai hành vi tuân theo các quy tắc khác nhau.

## 6. So sánh số: int, long, float và double

Khi cả hai vế có ý nghĩa **numeric**, JMS selector cho phép các phép so sánh:

```sql
orderCount > 10
orderCount >= 10
orderCount < 100
orderCount <> 0
orderCount BETWEEN 10 AND 20
amountMinor + feeMinor >= 100000
```

### 6.1. Integer khác Long có match nhau không?

Khác với **String so với số**, so sánh giữa các nhóm số có thể hợp lệ. Đặc tả cho phép so sánh **exact numeric** với **approximate numeric** và áp quy tắc **Java numeric promotion** khi cần.

Ví dụ:

```java
msg.setIntProperty("n", 12);
```

có thể so sánh được với literal `12`, và nếu dùng `setLongProperty("n", 12L)` thì selector `n > 10` vẫn là một so sánh số thích hợp. Không cần đổi `long` thành String.

### 6.2. So sánh số thực cần chú ý độ chính xác

```java
msg.setDoubleProperty("ratio", 0.1D);
```

Selector `ratio > 0.05` có ý nghĩa số. Nhưng `double`/`float` có lỗi biểu diễn nhị phân, nên không xây dựng logic tài chính yêu cầu **so sánh số thập phân chính xác** bằng các giá trị floating-point mà không đánh giá sai số.

Với tiền, một chiến lược thường rõ ràng hơn là dùng đơn vị nhỏ nhất:

```java
msg.setLongProperty("amountMinor", 12_345L);
```

và lọc:

```sql
amountMinor >= 10000
```

Ví dụ này biểu diễn `12_345` đơn vị nhỏ, không phải Java `BigDecimal` nhúng trực tiếp vào property.

### 6.3. Không dùng phép so sánh thứ tự cho String

JMS selector chỉ hỗ trợ phép so sánh `=` và `<>` cho **String** và **Boolean**. Đừng viết:

```sql
postalCode > '10000'
```

rồi kỳ vọng nó so sánh chuỗi theo thứ tự từ điển, hoặc tưởng nó convert `postalCode` thành số. Với String, dùng `=`, `<>`, `LIKE`, `IN` theo cú pháp thích hợp.

## 7. `BETWEEN`, `IN`, `LIKE`: chọn đúng toán tử cho đúng kiểu

### 7.1. `BETWEEN` dành cho biểu thức số

Nếu producer ghi:

```java
msg.setIntProperty("orderCount", 15);
```

selector:

```sql
orderCount BETWEEN 10 AND 20
```

đánh giá TRUE. Nhưng nếu producer ghi `setStringProperty("orderCount", "15")`, selector trên **không** chuyển `"15"` thành số; kết quả không match.

### 7.2. `IN` dùng các String literal

```java
msg.setStringProperty("region", "VN");
```

selector:

```sql
region IN ('VN', 'SG', 'TH')
```

khớp vì `region` là String. Trong chuẩn JMS selector, cú pháp `IN` được định nghĩa cho **identifier có giá trị String hoặc NULL** với danh sách String literal. Đừng suy diễn SQL `n IN (1, 2, 3)` được JMS selector portable hỗ trợ. Với property số, hãy diễn đạt tường minh:

```sql
n = 1 OR n = 2 OR n = 3
```

Nếu hệ thống broker hỗ trợ extension cho numeric `IN`, đó có thể là đặc tính riêng; không nên phụ thuộc khi muốn code tương thích Jakarta Messaging.

### 7.3. `LIKE` là phép lọc mẫu chuỗi

```java
msg.setStringProperty("customerCode", "VIP-007");
```

selector:

```sql
customerCode LIKE 'VIP-%'
```

khớp với tiền tố `VIP-`. Dấu `%` khớp chuỗi ký tự bất kỳ, `_` khớp một ký tự. `LIKE` không phải phép so sánh số.

Nếu business ID là `"000007"`, việc lưu String và lọc bằng `customerCode = '000007'` giữ nguyên các số 0 đầu, thay vì parse thành số 7 và đánh mất định dạng.

## 8. Property không tồn tại, NULL và phép phủ định

Selector sử dụng **logic ba giá trị**: TRUE, FALSE và UNKNOWN. Nếu message không có property `orderCount`, biểu thức:

```sql
orderCount = 12
```

không có giá trị số để so sánh, nên kết quả là **UNKNOWN**. Nó không match. Để kiểm tra có/không có property:

```sql
orderCount IS NULL
orderCount IS NOT NULL
```

Với property không tồn tại, `IS NULL` đánh giá TRUE.

Một điểm tinh tế: nếu property `orderCount` là **String `"12"`**, các phép so sánh numeric không phù hợp kiểu. Theo quy tắc đặc tả, việc so sánh giữa hai kiểu không tương tự cho kết quả FALSE; **đừng tưởng `orderCount <> 12` là cách portable để bắt riêng các String property khác 12**. Hãy so sánh đúng kiểu `orderCount <> '12'`, hoặc tốt hơn là chuẩn hóa schema property.

### Tên property có phân biệt chữ hoa/chữ thường

```java
msg.setIntProperty("orderCount", 12);
```

Selector đúng:

```sql
orderCount = 12
```

Selector dùng tên khác:

```sql
OrderCount = 12
```

sẽ tham chiếu một identifier khác, thường trả UNKNOWN nếu `OrderCount` không tồn tại.

Chọn tên property dạng identifier hợp lệ của JMS selector (ví dụ `orderCount`, `retryCount`, `region`), tránh từ khóa dành riêng như `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`. Các tiền tố `JMSX` và `JMS_` được dành cho property chuẩn/provider; đừng dùng chúng tùy ý cho custom property.

## 9. Áp dụng trong Spring JMS: gửi property và khai báo selector

### 9.1. Producer dùng `MessagePostProcessor`

Nếu ứng dụng đang gửi payload bằng `JmsTemplate.convertAndSend`, có thể gắn property trong `MessagePostProcessor`:

```java
jmsTemplate.convertAndSend(
        "orders.in",
        "ORDER-001",
        message -> {
            message.setIntProperty("orderCount", 12);
            message.setStringProperty("region", "VN");
            return message;
        }
);
```

Ở đây:

- `"ORDER-001"` là **body** sau khi được Spring `MessageConverter` chuyển thành JMS message.
- `orderCount` là **numeric property** kiểu int.
- `region` là **String property**.
- Selector `orderCount >= 10 AND region = 'VN'` có thể match nếu destination, provider và consumer được cấu hình tương thích.
- Nếu vô tình đổi sang `setStringProperty("orderCount", "12")`, phần `orderCount >= 10` không match nữa.

`MessagePostProcessor` được gọi **trước khi gửi**; property thường không thể tùy tiện thay đổi trên message vừa nhận vì received message properties mặc định là read-only.

### 9.2. Consumer dùng `@JmsListener(selector = ...)`

```java
@Component
class HighVolumeListener {

    @JmsListener(
            destination = "orders.in",
            selector = "orderCount >= 10 AND region = 'VN'")
    public void handle(String body) {
        System.out.println("High volume: " + body);
    }
}
```

Đây là **class trong Spring application** có JMS infrastructure, cần import `org.springframework.stereotype.Component` và `org.springframework.jms.annotation.JmsListener`. Selector chỉ xét **property/header**; handler nhận body do converter xử lý.

Đừng đặt listener này vào cùng một Queue trong demo nhận đồng bộ ở mục 10 nếu muốn quan sát output chính xác: hai consumer cạnh tranh có thể giành message của nhau. Trong ứng dụng production, cần chủ động thiết kế selector và concurrency trên các consumer.

### 9.3. Consumer đồng bộ dùng `receiveSelected`

```java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

Message numeric = receiver.receiveSelected(
        "orders.in", "orderCount >= 10");
Message textual = receiver.receiveSelected(
        "orders.in", "orderCount = '12'");
```

Đây là snippet trong method có `ConnectionFactory connectionFactory` và import `jakarta.jms.Message`. Nếu không có message phù hợp trong thời gian chờ, mỗi lời gọi có thể trả **`null`**. Không nên diễn giải `null` thành “Queue trống hoàn toàn”: Queue có thể chứa message không match selector hoặc bị consumer khác xử lý.

## 10. Demo đầy đủ Java 17 + Spring Boot + Artemis: hai message có cùng nội dung số

Demo được thiết kế để chứng minh **cùng giá trị hiển thị `12`, khác property type, nên khác kết quả selector**.

- Gửi message `NUMERIC-12` có property `orderCount` kiểu `int` với giá trị `12`.
- Gửi message `STRING-12` có property `orderCount` kiểu `String` với giá trị `"12"`.
- Nhận bằng selector số `orderCount = 12`: chỉ nhận `NUMERIC-12`.
- Tiếp tục thử selector số `orderCount > 10`: không được nhận `STRING-12` còn lại, nên hết chờ và trả `null`.
- Nhận bằng selector chuỗi `orderCount = '12'`: nhận `STRING-12`.
- Đọc raw property để xác nhận `getObjectProperty` là `String` nhưng `getIntProperty` vẫn có thể trả `12` theo bảng conversion.

**Môi trường:** Java 17+, Gradle tương thích Spring Boot 3.3.x, Spring Boot 3.3.13, JMS provider Apache ActiveMQ Artemis ngoài ứng dụng. Chương trình này **không khai báo `@JmsListener`**, để tránh cạnh tranh consumer với `JmsTemplate.receiveSelected`.

### 10.1. Khởi động broker local

Máy đã có Docker có thể chạy một broker Artemis dành cho học tập:

```bash
docker run --detach --rm --name artemis-selector-types -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Đợi broker sẵn sàng qua `docker logs artemis-selector-types`. Broker phải có Queue `demo.selector.property-types` hoặc cho phép tự tạo Queue. Nhiều cấu hình Artemis test có thể bật auto-create; trong môi trường có kiểm soát cần chủ động provision destination và cấp quyền thích hợp.

**Quan trọng:** hãy bắt đầu với Queue sạch, không có message từ lần chạy trước và không có consumer khác, nếu muốn so sánh output minh họa bên dưới. Mật khẩu demo không dùng trong production.

### 10.2. Dự án Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'jms-selector-property-types'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      receive-timeout: 800ms
```

`receive-timeout: 800ms` giúp phép kiểm tra selector không match **trả `null` sau thời gian chờ hữu hạn**, thay vì chặn vô hạn. Timeout này áp dụng cho các phương thức nhận bằng **auto-configured `JmsTemplate`**. Nó không tạo hay sửa kiểu dữ liệu property.

### 10.3. Class Java đầy đủ

Tạo `src/main/java/example/jms/SelectorPropertyTypesApplication.java`:

```java
package example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorPropertyTypesApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SelectorPropertyTypesApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(JmsTemplate jmsTemplate) {
        return args -> {
            String queue = "demo.selector.property-types";

            // A. Cùng giá trị 12 nhưng property là Integer.
            jmsTemplate.convertAndSend(
                    queue, "NUMERIC-12", message -> {
                        message.setIntProperty("orderCount", 12);
                        message.setStringProperty("region", "VN");
                        return message;
                    });

            // B. Cùng giá trị hiển thị "12" nhưng là String.
            jmsTemplate.convertAndSend(
                    queue, "STRING-12", message -> {
                        message.setStringProperty("orderCount", "12");
                        message.setStringProperty("region", "VN");
                        return message;
                    });

            Object numeric = jmsTemplate.receiveSelectedAndConvert(
                    queue, "orderCount = 12");

            // Sau khi numeric được nhận, chỉ còn String "12".
            // Selector số không thể so sánh String > 10.
            Object noNumericMatch =
                    jmsTemplate.receiveSelectedAndConvert(
                            queue, "orderCount > 10");

            // Selector chuỗi tìm được message String còn lại.
            Message stringMessage = jmsTemplate.receiveSelected(
                    queue, "orderCount = '12'");

            if (!(stringMessage instanceof TextMessage textMessage)) {
                throw new IllegalStateException(
                        "Missing expected STRING-12 TextMessage");
            }

            System.out.println("NUMERIC_EQUALS=" + numeric);
            System.out.println("NUMERIC_GT_AGAIN=" + noNumericMatch);
            System.out.println("STRING_EQUALS=" + textMessage.getText());
            System.out.println("STRING_TYPE=" +
                    stringMessage.getObjectProperty(
                            "orderCount").getClass().getSimpleName());
            System.out.println("STRING_GET_INT=" +
                    stringMessage.getIntProperty("orderCount"));
        };
    }
}
```

Class sử dụng `ApplicationRunner`, nên lambda có thể ném exception từ JMS getters. Spring Boot tạo `JmsTemplate` và `ConnectionFactory` từ starter + cấu hình. `SimpleMessageConverter` mặc định chuyển `String` payload thành `TextMessage`.

### 10.4. Chạy và xem output

Từ thư mục chứa `build.gradle`, nếu máy có Gradle tương thích:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper: Linux/macOS dùng `./gradlew bootRun`; Windows dùng `gradlew.bat bootRun`.

Với broker sẵn sàng, Queue sạch, không có consumer khác và các lần gửi thành công, **những dòng do ứng dụng tự in** dự kiến là:

```text
NUMERIC_EQUALS=NUMERIC-12
NUMERIC_GT_AGAIN=null
STRING_EQUALS=STRING-12
STRING_TYPE=String
STRING_GET_INT=12
```

Giải thích:

- `NUMERIC_EQUALS=NUMERIC-12`: numeric property match numeric literal.
- `NUMERIC_GT_AGAIN=null`: sau khi message numeric được nhận, còn String property `"12"`; nó không match phép so sánh số `> 10`.
- `STRING_EQUALS=STRING-12`: selector `= '12'` match String.
- `STRING_TYPE=String`: property thật sự được ghi kiểu String.
- `STRING_GET_INT=12`: getter được phép convert chuỗi số hợp lệ sang int; **selector không thực hiện conversion tương ứng**.

Đây là output **dự kiến trong điều kiện đã nêu**, không phải kết quả một lần chạy broker đã được thực hiện trong quá trình biên soạn bài. Broker dispatch, queue backlog, consumer khác, quyền hoặc network có thể làm kết quả thay đổi hay ném lỗi. Không biến demo thành kiểm tra realtime chính xác tới từng mili-giây.

Dừng môi trường học sau khi xong:

```bash
docker stop artemis-selector-types
```

## 11. Phân biệt cách lọc bằng `@JmsListener` và bằng `JmsTemplate`

Trong Spring, selector có thể đặt ở **consumer bất đồng bộ** hoặc **consumer đồng bộ**.

**Bất đồng bộ:**

```java
@JmsListener(
        destination = "orders.events",
        selector = "orderCount >= 10 AND region = 'VN'")
public void onHighVolumeOrder(String body) {
    // Chỉ chạy nếu message khớp selector.
}
```

**Đồng bộ:**

```java
Object result = jmsTemplate.receiveSelectedAndConvert(
        "orders.events",
        "orderCount >= 10 AND region = 'VN'");
```

Cả hai dùng cùng quy tắc kiểu dữ liệu selector của Jakarta Messaging. Điểm khác:

| Chủ đề | `@JmsListener(selector=...)` | `JmsTemplate.receiveSelected(...)` |
| --- | --- | --- |
| Ai tạo consumer? | Spring listener container | `JmsTemplate` trong lời gọi |
| Kiểu property được kiểm tra | Theo setter lúc producer gửi | Y hệt |
| Vùng áp dụng selector | Consumer gắn với listener | Chỉ consumer trong lượt nhận |
| Luồng xử lý | Async callback khi message đến | Thread gọi bị block đến khi nhận hoặc timeout |
| Không match | Handler không nhận message đó | Có thể trả `null` khi timeout |
| Phù hợp | Xử lý liên tục | Kiểm tra và tác vụ đồng bộ có giới hạn |

`@JmsListener` **không tự parse JSON body** để nhận field `orderCount`. Khi payload là DTO chứa `int count`, nếu producer không gắn JMS property, selector vẫn không thể dùng field đó.

### Consumer khác có thể vẫn nhận message

Trong Queue, message không match selector của consumer A có thể tiếp tục nằm trên Queue cho consumer B có selector khác hoặc consumer không lọc. Với Topic, tiêu chuẩn phân phối phụ thuộc subscription; một message không match selector của một subscription không được giao cho subscription đó.

Nếu app vừa chạy listener với selector `orderCount = 12` vừa chạy consumer không filter trên cùng Queue, consumer không filter có thể nhận message trước. Vì vậy khi test kiểu property, **tránh các consumer cạnh tranh** để kết quả rõ ràng.

## 12. Kiểm tra kiểu property đúng cách khi debug

Khi một selector không match, bước đầu không phải sửa điều kiện bằng cách thêm nháy đơn tùy tiện, mà là **xác minh type tại thời điểm gửi**.

### 12.1. Dùng `getObjectProperty`

```java
Message message = ...; // Một JMS Message thực sự vừa nhận.

Object raw = message.getObjectProperty("orderCount");

if (raw == null) {
    System.out.println("orderCount missing");
} else {
    System.out.println("type=" + raw.getClass().getSimpleName());
    System.out.println("value=" + raw);
}
```

Đây là snippet trong method có `Message message` hợp lệ; `getObjectProperty` có thể ném `JMSException`, nên method phải khai báo hoặc xử lý checked exception. Đối với `setIntProperty`, type thường là `Integer`; đối với `setStringProperty`, type là `String`.

### 12.2. Thử `propertyExists`

```java
if (!message.propertyExists("orderCount")) {
    System.out.println("Property chưa được gắn");
}
```

Phân biệt **property thiếu** với **property có nhưng sai kiểu**. Không nên sửa theo kiểu `orderCount IS NULL` nếu vấn đề thật là `"12"` được ghi bằng String thay vì int.

### 12.3. Quan sát header/property thực sự, không chỉ body

Với `TextMessage`, `getText()` không đủ để xác minh property. Khi log phục vụ debug, nên ghi một số metadata đã cho phép:

```text
messageId=...
property=orderCount
propertyType=java.lang.String
propertyValue=12
selector=orderCount > 10
matchExpected=false
```

Đây là định dạng log **minh họa**, không phải output của một chương trình cụ thể. Tránh log payload hoặc properties chứa token, thông tin cá nhân hoặc bí mật vận hành. Nếu broker cung cấp management console hiển thị property type, dùng nó để đối chiếu nhưng vẫn nên test bằng API Jakarta JMS để tránh cách console render giống nhau.

### 12.4. Danh sách kiểm tra trong thực tế

1. Producer gọi setter nào cho property? `setIntProperty` hay `setStringProperty`?
2. Tên property có đúng **chữ hoa/chữ thường** không?
3. Consumer đang dùng selector **numeric** hay **String literal có nháy đơn**?
4. Property có thật trên message chưa, hay dữ liệu chỉ nằm trong JSON body?
5. Có consumer khác đang nhận cùng Queue không?
6. Message có bị expire, rollback, redelivery hoặc đưa vào DLQ không?
7. Broker/provider có rule, transformation hoặc extension selector riêng không?
8. Có sự thay đổi schema giữa các phiên bản producer không?

## 13. Thiết kế schema property để tránh sai kiểu

Đây là một **hợp đồng liên ứng dụng**: producer ở service A và consumer ở service B phải thống nhất property tên gì, kiểu gì và selector tương ứng.

Ví dụ hợp đồng đơn giản:

| Property | Type JMS | Ý nghĩa | Selector ví dụ |
| --- | --- | --- | --- |
| `eventType` | String | Loại sự kiện | `eventType = 'ORDER_CREATED'` |
| `region` | String | Mã vùng | `region IN ('VN','SG')` |
| `orderCount` | int | Số lượng đơn | `orderCount >= 10` |
| `amountMinor` | long | Tổng tiền theo đơn vị nhỏ | `amountMinor > 100000` |
| `isPriority` | boolean | Cờ nghiệp vụ | `isPriority = TRUE` |
| `createdAtEpochMs` | long | Thời gian Unix theo ms | `createdAtEpochMs >= 1760000000000` |
| `postalCode` | String | Định danh giữ số 0 đầu | `postalCode = '00123'` |

Cần quyết định **kiểu ngay từ bước xây dựng event schema**:

- **Số lượng, số lần retry, mức điểm có so sánh độ lớn:** dùng int/long/float/double thích hợp.
- **Mã định danh, số thẻ, số điện thoại, mã ZIP, mã hóa đơn có số 0 đầu:** thường dùng String, không dùng phép so sánh số.
- **Thời điểm cần so sánh lớn/nhỏ:** dùng long epoch millis theo hợp đồng schema nếu selector cần lọc.
- **Trạng thái nghiệp vụ:** thường dùng String có tập giá trị hạn chế hoặc boolean đúng nghĩa; đừng đổi String `"true"` thành boolean ngầm ở consumer.

### Producer nhận dữ liệu từ HTTP/CSV

Dữ liệu đến từ request hoặc CSV có thể ở dạng String, nhưng cần validate:

```java
String rawCount = "12"; // Ví dụ dữ liệu nhập vào đã được validate.

int orderCount;
try {
    orderCount = Integer.parseInt(rawCount);
} catch (NumberFormatException ex) {
    throw new IllegalArgumentException(
            "orderCount must be a valid integer", ex);
}

jmsTemplate.convertAndSend("orders.in", "ORDER-003",
        msg -> {
            msg.setIntProperty("orderCount", orderCount);
            return msg;
        });
```

Đây là snippet trong service đã inject `JmsTemplate`. Nếu cần giới hạn nghiệp vụ (ví dụ 0–1.000), kiểm tra range sau khi parse; `Integer.parseInt` chỉ kiểm tra biểu diễn số hợp lệ trong phạm vi int, không tự áp quy tắc nghiệp vụ.

### Tránh thay đổi type dưới cùng tên mà không version hóa

Nếu phiên bản cũ của producer phát `orderCount` dưới dạng String, còn phiên bản mới chuyển thành int, người tiêu thụ dùng:

```sql
orderCount >= 10
```

sẽ chỉ thấy các message có numeric property thích hợp; message cũ chưa xử lý không match. Đừng “vá nhanh” bằng các giả định SQL convert tự động.

Một chiến lược migration rõ ràng:

1. Bổ sung property mới `orderCountInt` kiểu int trong producer, trong khi tạm duy trì `orderCountText` kiểu String nếu cần tương thích.
2. Cập nhật consumer mới lọc `orderCountInt >= 10`.
3. Theo dõi backlog và phiên bản producer còn cũ.
4. Sau khi hết giai đoạn song song, bỏ property cũ theo kế hoạch nâng cấp.

Cũng có thể dùng `schemaVersion` kiểu int để phân biệt biến thể. Đừng cố dùng một selector mơ hồ trên cùng một tên property có lúc String, lúc int trong hệ thống lớn nếu có thể tránh.

## 14. JMS headers và trường hợp đặc biệt về kiểu

Không phải tất cả selector identifier đều là custom property. Một số **JMS header** được đặc tả cho phép trong selector và có type/biểu diễn riêng.

### `JMSPriority` là số

```sql
JMSPriority >= 7
```

đây là biểu thức số. **`JMSPriority = '7'` không tương đương**, vì `'7'` là String literal.

### `JMSDeliveryMode` được biểu diễn bằng String trong selector

Mặc dù Java API trả delivery mode dưới dạng hằng số số `DeliveryMode.PERSISTENT` / `NON_PERSISTENT`, **trong JMS selector** header `JMSDeliveryMode` được xem như có giá trị String đặc biệt:

```sql
JMSDeliveryMode = 'PERSISTENT'
```

Đây là một ngoại lệ do **đặc tả selector của JMS quy định**, không phải vì provider tự ép kiểu ở mọi property. Đừng lấy ngoại lệ này làm lý do viết `orderCount = '12'` khi property thực tế là int.

### `JMSType`, `JMSCorrelationID`, `JMSMessageID`

Những header này có thể được dùng trong selector theo quy tắc JMS nếu giá trị và cú pháp phù hợp, nhưng chúng không thay thế custom property về số lượng/giá tiền. Một số header có thể NULL và chịu logic ba giá trị.

### Đừng nhầm `JMSXDeliveryCount` với custom String `"1"`

`JMSXDeliveryCount` là property JMS-defined kiểu số nguyên (provider cung cấp trong ngữ cảnh delivery). Selector, nếu broker hỗ trợ và field có mặt, cần sử dụng numeric literal đúng kiểu. Không tự đặt một String property cùng tên `"1"` rồi suy ra nó tương đương.

## 15. Hiệu năng, vận hành và an toàn khi dùng selector

Selector hữu ích vì JMS provider có thể **lọc message trước khi giao tới consumer**. Tuy vậy:

- Selector không nhất thiết làm các message **không khớp biến mất** khỏi Queue; chúng có thể tiếp tục chờ consumer khác, gây backlog.
- Nhiều selector phức tạp, nhiều consumer và Queue lớn có thể làm tăng chi phí broker; hãy đo theo provider thực tế thay vì đoán.
- Một property sai kiểu có thể khiến toàn bộ nhóm consumer mới **không nhận message cũ**, dù nhìn trên dashboard body vẫn hợp lệ.
- Một số broker có cú pháp/extension selector riêng. Nếu cần portable Jakarta Messaging, bám vào SQL-92 subset của đặc tả.
- Đừng đưa input thô của người dùng vào selector bằng nối String thiếu kiểm soát. Nếu cần lọc mã định danh động, validate và escape single quote đúng cú pháp JMS; tốt hơn dùng danh sách giá trị được phép và cấu hình rõ ràng.

Ví dụ khi mã vùng là `"O'Brien"`, literal JMS phải là `'O''Brien'`. Không được tạo điều kiện selector bằng dữ liệu đầu vào không được validate nếu điều đó cho phép thay đổi ý nghĩa biểu thức.

**Không dùng selector để làm phép xác thực/phân quyền nghiệp vụ.** Selector là công cụ routing và tối ưu delivery; security của broker/queue và quyền producer/consumer phải được cấu hình riêng.

## 16. Lỗi thường gặp, câu hỏi và bài tập

### Bảng lỗi nhanh

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `orderCount > 10` không nhận message nhìn thấy “12” | Property thật ra là String `"12"`. | Producer dùng `setIntProperty`, không chỉ đổi selector mù quáng. |
| `orderCount = '12'` không nhận message | Property thật là int 12. | Dùng `orderCount = 12` cho numeric property. |
| `getIntProperty` trả 12 nhưng selector `> 10` vẫn không match | Getter được phép chuyển String sang số; selector không được chuyển. | Dùng `getObjectProperty` kiểm tra type gốc. |
| `postalCode` mất số 0 đầu | Lưu code dưới dạng int. | Chọn String property và selector có nháy. |
| `paid = TRUE` không match | Producer dùng String `"true"`. | Dùng boolean property hoặc selector String phù hợp hợp đồng. |
| `amountMinor >= 1000` không match | Field chỉ có trong JSON body, chưa phải JMS property. | Set numeric JMS property riêng trước khi gửi. |
| Selector `OrderCount = 12` không nhận gì | Tên property khác case `orderCount`. | Khớp đúng tên và case. |
| `n IN (1,2,3)` lỗi cú pháp/không portable | `IN` trong chuẩn JMS dành cho String literal list. | Với số dùng `n=1 OR n=2 OR n=3`. |
| String property `name > 'A'` lỗi/không đúng | String comparison chỉ có `=`, `<>`; `LIKE` cho pattern. | Sửa logic lọc. |
| Selector sai dẫn đến startup lỗi | Selector syntax không hợp lệ. | Đọc root cause `InvalidSelectorException`; test với provider. |
| Consumer không thấy message dù selector đúng | Consumer khác lấy Queue message, TTL hết, destination sai hoặc ACL. | Kiểm tra broker, Queue/Topic, concurrency, transaction. |
| Chuyển schema làm mất route message cũ | Cùng tên property được ghi bằng hai kiểu qua nhiều phiên bản. | Version schema, migration từng bước, test backlog. |

### Câu 1

Producer:

```java
msg.setStringProperty("quantity", "9");
```

Hai selector `quantity > 5` và `quantity = '9'` sẽ thế nào?

**Đáp án:** `quantity > 5` không match vì String không dùng làm số; `quantity = '9'` match.

### Câu 2

Producer:

```java
msg.setIntProperty("quantity", 9);
```

Selector `quantity = '9'` có match không?

**Đáp án:** Không. Literal `'9'` là String, trong khi property có kiểu int. Dùng `quantity = 9`.

### Câu 3

Tại sao `msg.getStringProperty("quantity")` có thể trả `"9"` khi producer đã `setIntProperty("quantity", 9)`?

**Đáp án:** Getter cho phép chuyển numeric value thành String theo bảng conversion. Việc đọc như String không thay đổi type gốc trong selector.

### Câu 4

`msg.setLongProperty("totalMinor", 1_000_000L)` và selector `totalMinor >= 500000`: có phù hợp không?

**Đáp án:** Có. Đây là so sánh số thích hợp. Sử dụng long cho đơn vị nhỏ của tiền cũng giúp tránh lỗi floating-point trong các phép so sánh chính xác đơn giản.

### Câu 5

Nếu property `region` không tồn tại, `region = 'VN'` là FALSE hay UNKNOWN?

**Đáp án:** UNKNOWN. Chỉ TRUE mới làm message match; dùng `region IS NULL` để tìm message thiếu property.

### Câu 6

Một consumer dùng `orderCount <> 10`. Có nên dùng nó để tìm mọi message mà property `orderCount` **không phải** int 10, bao gồm String `"10"`?

**Đáp án:** Không nên. So sánh khác kiểu không phải một phép phân loại đáng tin cậy cho schema; đối chiếu đúng type, đặt property/flag schema riêng hoặc chuẩn hóa producer.

### Câu 7

Bạn muốn lọc mã bưu chính `00123`. Nên ghi property dạng nào?

**Đáp án:** String `"00123"`, và chọn selector `postalCode = '00123'`. Đó là identifier, không phải số dùng để tính toán.

### Bài tập thực hành

Từ demo mục 10:

1. Đổi `setIntProperty("orderCount", 12)` thành `setStringProperty("orderCount", "12")`. Dự đoán kết quả `receiveSelectedAndConvert(queue, "orderCount = 12")`; chạy trên Queue sạch để xác minh.
2. Thay một message có `setLongProperty("orderCount", 12L)`. Thử `orderCount >= 10` rồi giải thích numeric promotion.
3. Thêm `region = 'VN'` bằng `AND`, rồi cố tình đổi `region` thành `"vn"` để kiểm tra String equality có phân biệt ký tự.
4. Ghi `postalCode = "00123"` và thử selector chuỗi; kiểm tra vì sao parse int 123 làm mất định dạng.
5. Tạo một message không có property `orderCount`; so sánh `orderCount = 12` với `orderCount IS NULL`.

**Trong mọi bài tập**, nên dùng Queue riêng hoặc reset Queue đã kiểm soát, không để listener/consumer khác cạnh tranh và dùng receive timeout hữu hạn để không treo chương trình.

## 17. Tài liệu chuẩn và ghi nhớ

- [Jakarta Messaging 3.1 Specification — 3.5 Message Properties và 3.8 Message Selection](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 — Message interface API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
- [Spring Framework — Sending a Message bằng JmsTemplate và MessagePostProcessor](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework 6.2 — JmsTemplate API, receiveSelected/receiveSelectedAndConvert](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Getting Started — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Spring Boot 3 — JMS / ActiveMQ Artemis Configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)

**Tóm tắt quy tắc cần nhớ:**

1. **Setter quyết định type:** `setIntProperty("n", 12)` khác `setStringProperty("n", "12")`.
2. **Selector giữ type thật:** `n = 12` khác `n = '12'`; `n > 10` chỉ có ý nghĩa khi `n` numeric.
3. **Getter conversion không có nghĩa selector conversion:** `getIntProperty` có thể parse `"12"`, nhưng selector không tự parse.
4. **Selector không đọc body JSON:** muốn lọc field nào, cần gắn property/header được hỗ trợ.
5. **Thiết kế schema nhất quán:** thống nhất tên, kiểu, phạm vi giá trị và phiên bản giữa producer–consumer; test bằng broker thực tế để tránh những lỗi routing âm thầm.
