# Giá trị thiếu và logic ba trạng thái trong JMS Message Selector

> **Ngữ cảnh:** Spring Framework – JMS · **Nhóm:** Lọc thông điệp.  
> **Mục tiêu:** Hiểu chính xác điều gì xảy ra khi JMS message **không có một property**, vì sao biểu thức selector có thể cho kết quả **TRUE**, **FALSE** hoặc **UNKNOWN**, cách `AND`/`OR`/`NOT` lan truyền giá trị chưa biết, và cách viết bộ lọc an toàn cho producer/consumer. Bài có bảng chân trị, ví dụ Java 21 chạy độc lập và một ứng dụng Spring Boot + ActiveMQ Artemis để kiểm chứng thực tế.

## 1. Tình huống gây lỗi: "không phải READY" chưa chắc được chọn

Một consumer muốn nhận các đơn **không** ở trạng thái `READY`:

```java
@JmsListener(
    destination = "orders.events",
    selector = "NOT (status = 'READY')")
public void handle(String payload) {
    // ...
}
```

Nếu thông điệp có `status='BLOCKED'`, điều kiện là `NOT FALSE = TRUE`: consumer nhận.

Nếu thông điệp **không có property `status`**, điều kiện `status = 'READY'` **không phải FALSE**. Theo Jakarta Messaging/SQL92, tham chiếu tới property không tồn tại được xem như `NULL`, phép so sánh với `NULL` tạo kết quả `UNKNOWN`, và `NOT UNKNOWN` vẫn là `UNKNOWN`. **Message không khớp selector** vì JMS chỉ chấp nhận kết quả `TRUE`.

Do đó, cách viết bên dưới mới diễn đạt “không READY, **kể cả thiếu status**”:

```sql
status IS NULL OR status <> 'READY'
```

Còn nếu nghiệp vụ yêu cầu **status phải tồn tại và khác READY**:

```sql
status IS NOT NULL AND status <> 'READY'
```

Đây là hai hợp đồng khác nhau. Không tự thêm nhánh `IS NULL` trước khi quyết định message thiếu metadata nên được xử lý, bỏ qua, đưa vào queue lỗi hay sửa từ producer.

**Thông điệp nhớ lâu:** `NOT` không tự động biến `UNKNOWN` thành `TRUE`.

## 2. Message selector được đánh giá trên dữ liệu nào?

JMS selector là một biểu thức điều kiện theo **tập con cú pháp SQL92**, được JMS provider đánh giá dựa trên **một số JMS header fields và JMS message properties**, không dựa vào body.

```text
JMS TextMessage
├── Headers theo JMS
│   ├── JMSPriority
│   ├── JMSCorrelationID
│   └── JMSType
├── Properties do producer đặt
│   ├── status = "READY"        (String, có thể vắng)
│   ├── retryCount = 3          (int, có thể vắng)
│   └── urgent = false         (boolean, có thể vắng)
└── Body
    {"status":"READY","retryCount":3}     <-- selector KHÔNG đọc JSON này
```

Giả sử producer gửi:

```java
// Fragment: có sẵn một jakarta.jms.Message message.
message.setStringProperty("status", "READY");
message.setIntProperty("retryCount", 3);
message.setBooleanProperty("urgent", false);
```

Thì selector có thể dùng `status`, `retryCount`, `urgent`. Nếu producer **chỉ** đặt `"status"` trong JSON body của `TextMessage` mà **không** gọi `setStringProperty`, thì từ góc nhìn selector, property `status` **không tồn tại**.

Các JMS header fields được phép tham chiếu trong selector tiêu chuẩn gồm `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID` và `JMSType`. Một số header như `JMSCorrelationID`, `JMSType` có thể có giá trị null; `JMSMessageID` được provider quản lý. Không suy diễn mọi getter header JMS đều là tên selector tiêu chuẩn.

**Tên property phân biệt chữ hoa/chữ thường:** `status` và `Status` là hai identifier khác nhau. Keywords `AND`, `OR`, `NOT`, `IS NULL` không phân biệt hoa/thường về mặt cú pháp.

## 3. Property thiếu: vì sao gọi là NULL?

Theo đặc tả Jakarta Messaging 3.1, khi biểu thức selector tham chiếu đến **property không có trong message**, giá trị của tham chiếu đó là `NULL` trong quá trình đánh giá. Đây là **quy tắc của selector**, không có nghĩa ứng dụng bắt buộc phải gọi `setStringProperty("status", null)`.

Phân biệt:

| Message có gì? | Cách producer tạo | Ý nghĩa trong selector |
| --- | --- | --- |
| Không có `status` | Không gọi bất kỳ setter nào cho `status` | `status` được xem là `NULL`. |
| `status = "READY"` | `setStringProperty("status","READY")` | String `READY`, tồn tại. |
| `status = ""` | `setStringProperty("status","")` | Chuỗi rỗng, **không phải NULL**. |
| `urgent = false` | `setBooleanProperty("urgent", false)` | Boolean `FALSE`, **không phải NULL**. |
| `retryCount = 0` | `setIntProperty("retryCount",0)` | Số nguyên `0`, **không phải NULL**. |
| `retryCount = "0"` | `setStringProperty("retryCount","0")` | String `"0"`, không tự trở thành số 0 khi so sánh selector. |

Việc đọc property trong code không nên được dùng để đoán nó có tồn tại:

```java
// Fragment: có sẵn jakarta.jms.Message incoming.
boolean exists = incoming.propertyExists("status");
Object value = incoming.getObjectProperty("status");

System.out.println("exists=" + exists);
System.out.println("value=" + value);
```

`propertyExists` là phép kiểm tra rõ ràng sự hiện diện của property. Với một property **vắng mặt**, `getObjectProperty` trả về `null` theo contract API; những getter typed khác có quy tắc chuyển đổi/ngoại lệ riêng. **Đừng dùng `getBooleanProperty(...) == false` hay một giá trị mặc định giả định nào để kết luận property đã được set.**

**Ba khái niệm khác nhau:**

1. **Java `null`:** tham chiếu trong code Java.
2. **JMS property vắng mặt / selector `NULL`:** thiếu thông tin ở JMS envelope.
3. **`UNKNOWN`:** kết quả logic khi biểu thức không thể khẳng định đúng hoặc sai do `NULL`.

Phép `status IS NULL` tạo kết quả **TRUE/FALSE**; còn phép `status = 'READY'` khi status vắng mặt tạo kết quả **UNKNOWN**.

## 4. Tại sao phải có TRUE, FALSE và UNKNOWN?

Logic Boolean thông thường có hai giá trị:

```text
TRUE   FALSE
```

Selector áp dụng logic ba trạng thái (three-valued logic):

```text
TRUE       (T): mệnh đề chắc chắn đúng
FALSE      (F): mệnh đề chắc chắn sai
UNKNOWN    (U): không đủ dữ liệu để xác định đúng hay sai
```

**Quy tắc giao message quan trọng nhất:**

| Kết quả cuối cùng của selector | Consumer có match không? |
| --- | --- |
| `TRUE` | **Có**: message phù hợp với consumer này. |
| `FALSE` | **Không**. |
| `UNKNOWN` | **Không**. |

`FALSE` và `UNKNOWN` có **cùng kết quả nhận/không nhận**, nhưng chúng **không đồng nghĩa** vì có thể cho kết quả khác khi kết hợp thêm `AND`, `OR` hoặc `NOT`. Chẳng hạn `FALSE OR TRUE = TRUE` và `UNKNOWN OR TRUE = TRUE`, nhưng `FALSE OR FALSE = FALSE` còn `UNKNOWN OR FALSE = UNKNOWN`.

Broker không nhất thiết tạo một nhãn “UNKNOWN” trong UI cho từng message; đây là mô hình **đánh giá biểu thức**, không phải trạng thái business của message. Một message không match queue consumer có thể nằm lại chờ consumer khác hoặc selector khác; việc tồn tại/expire/redelivery phụ thuộc destination và broker policy.

## 5. Bảng chân trị chuẩn theo SQL92/Jakarta Messaging

Dùng ký hiệu `T=TRUE`, `F=FALSE`, `U=UNKNOWN`.

### 5.1. Phép AND

| `A AND B` | B=T | B=F | B=U |
| --- | --- | --- | --- |
| **A=T** | T | F | U |
| **A=F** | F | F | F |
| **A=U** | U | F | U |

Ý nghĩa:

- `T AND U = U`: một điều kiện đúng nhưng điều kiện còn lại thiếu dữ liệu → chưa thể kết luận cả hai đúng.
- `F AND U = F`: có một điều kiện sai chắc chắn → cả biểu thức sai dù còn một điều kiện thiếu.
- `U AND U = U`: cả hai chưa xác định.

### 5.2. Phép OR

| `A OR B` | B=T | B=F | B=U |
| --- | --- | --- | --- |
| **A=T** | T | T | T |
| **A=F** | T | F | U |
| **A=U** | T | U | U |

Ý nghĩa:

- `T OR U = T`: có một nhánh chắc chắn đúng → toàn bộ OR đúng.
- `F OR U = U`: nhánh thứ nhất sai, nhánh thứ hai thiếu dữ liệu → toàn bộ còn chưa xác định.
- `U OR U = U`.

### 5.3. Phép NOT

| A | `NOT A` |
| --- | --- |
| T | F |
| F | T |
| U | U |

**NOT không sửa được dữ liệu thiếu**. Vì vậy mọi biến thể `status <> 'READY'`, `NOT (status = 'READY')`, `status NOT IN (...)` đều cần suy xét trường hợp `status` không tồn tại.

## 6. Ví dụ từng bước với property `status`

Giả sử selector `status = 'READY'`. Có ba message:

| Message | Property status | `status = 'READY'` | Có được chọn? |
| --- | --- | --- | --- |
| M1 | `READY` | T | Có |
| M2 | `BLOCKED` | F | Không |
| M3 | **không có property** | U | Không |

Thêm `NOT`:

| Message | `status = 'READY'` | `NOT (status = 'READY')` | Có được chọn? |
| --- | --- | --- | --- |
| M1 | T | F | Không |
| M2 | F | T | Có |
| M3 | U | U | **Không** |

Muốn bao gồm M3, sử dụng:

```sql
status IS NULL OR status <> 'READY'
```

Đánh giá:

| Message | `status IS NULL` | `status <> 'READY'` | OR | Có được chọn? |
| --- | --- | --- | --- | --- |
| M1 = READY | F | F | F | Không |
| M2 = BLOCKED | F | T | T | Có |
| M3 = thiếu | T | U | **T** | Có |

Nếu chỉ muốn trạng thái hợp lệ, có thể dùng:

```sql
status IS NOT NULL AND status <> 'READY'
```

Biểu thức này **không xác thực** `status` có một giá trị thuộc enum nghiệp vụ hợp lệ; nó chỉ kiểm tra property tồn tại và khác READY khi kiểu so sánh phù hợp. Để kiểm soát contract tốt hơn, đặt `status IN ('BLOCKED', 'CANCELLED')` và test phiên bản schema.

### 6.1. Một mệnh đề tưởng “luôn đúng” nhưng không đúng khi thiếu dữ liệu

```sql
status = 'READY' OR status <> 'READY'
```

Với status có String hợp lệ, nó là T; nhưng khi status vắng mặt:

```text
UNKNOWN OR UNKNOWN = UNKNOWN
```

Vì vậy **không match**. Đây là lý do phép loại trừ thứ ba của Boolean 2 trạng thái không thể áp dụng nguyên xi khi tồn tại `NULL`.

## 7. Ví dụ kết hợp AND/OR trong lọc đơn hàng

Selector:

```sql
eventType = 'OrderCreated' AND retryCount > 2
```

Giả sử `eventType='OrderCreated'` đã được set và `retryCount` bị thiếu:

```text
TRUE AND UNKNOWN = UNKNOWN
```

Message **không** được giao cho consumer. Nếu `eventType='OrderCancelled'` (điều kiện trái sai) và retryCount thiếu:

```text
FALSE AND UNKNOWN = FALSE
```

Cũng không giao, nhưng với kết quả logic khác.

Selector thứ hai:

```sql
eventType = 'OrderCreated' OR retryCount > 2
```

Với eventType đúng và retryCount thiếu:

```text
TRUE OR UNKNOWN = TRUE
```

Message được chọn. Với eventType sai và retryCount thiếu:

```text
FALSE OR UNKNOWN = UNKNOWN
```

Không được chọn.

**Mẹo debug:** tách selector phức tạp thành từng phép so sánh, gán T/F/U cho mỗi phần theo metadata **thực sự nằm trong JMS properties**, rồi tính theo bảng chân trị. Tránh dựa vào “điều kiện đọc giống tiếng Việt” vì NOT/NULL có thể làm trực giác sai.

## 8. `IS NULL` và `IS NOT NULL` có ý nghĩa đặc biệt

Hai toán tử này chuyển từ câu hỏi “giá trị có biết không?” thành một mệnh đề **có đáp án T hoặc F** cho trường cần kiểm tra.

| Property status | `status IS NULL` | `status IS NOT NULL` |
| --- | --- | --- |
| Thiếu | TRUE | FALSE |
| `"READY"` | FALSE | TRUE |
| `""` | FALSE | TRUE |
| `"BLOCKED"` | FALSE | TRUE |

Dùng khi cần:

- **Lấy message legacy thiếu field:** `schemaVersion IS NULL`.
- **Chỉ lấy message có metadata:** `tenantId IS NOT NULL`.
- **Hỗ trợ hai nguồn, một nguồn chưa gửi property mới:** `(region IS NULL OR region = 'APAC')`.

Nhưng `IS NULL` **không thay thế validation**: `tenantId IS NOT NULL` cũng đúng khi tenantId là chuỗi rỗng `""` hoặc string sai định dạng. Kết hợp validation ở producer/consumer, không coi selector là bộ kiểm tra schema hoàn chỉnh.

### Những điều không nên làm

- Viết `status = NULL` hoặc `status <> NULL` để thử dữ liệu thiếu. **Hãy dùng `IS NULL`/`IS NOT NULL`**; `NULL` không phải kiểu literal so sánh thông thường trong tập con cú pháp selector.
- Viết `status = 'null'` rồi nghĩ đó là null. `'null'` là một **String literal** gồm bốn ký tự.
- Xem `NOT (status IS NULL)` và `status IS NOT NULL` là phép lọc khác nhau: chúng tương đương với kiểm tra sự hiện diện phù hợp, nhưng `NOT (status = 'READY')` **không** giống `status IS NULL OR status <> 'READY'`.
- Coi chuỗi rỗng là NULL. Nếu nghiệp vụ muốn chuỗi rỗng cũng được xem là “chưa thiết lập”, phải định nghĩa riêng, ví dụ `status IS NULL OR status = ''`.

## 9. LIKE, IN, BETWEEN và NOT khi property thiếu

Tập con SQL92 selector hỗ trợ các toán tử như `LIKE`, `IN`, `BETWEEN` với quy tắc kiểu dữ liệu/NULL tương ứng.

| Selector | Message thiếu property được tham chiếu | Kết quả trên phần biểu thức |
| --- | --- | --- |
| `status IN ('READY','BLOCKED')` | status thiếu | U |
| `status NOT IN ('READY','BLOCKED')` | status thiếu | U |
| `status LIKE 'PAY%'` | status thiếu | U |
| `status NOT LIKE 'PAY%'` | status thiếu | U |
| `retryCount BETWEEN 1 AND 5` | retryCount thiếu | U |
| `retryCount NOT BETWEEN 1 AND 5` | retryCount thiếu | U |
| `retryCount > 0` | retryCount thiếu | U |

Các phép này không tự coi dữ liệu thiếu là “không thuộc tập” hoặc “nằm ngoài khoảng”. `NOT UNKNOWN = UNKNOWN`.

Ví dụ muốn bắt đầu bằng `PAY` **hoặc thiếu mã**:

```sql
eventCode IS NULL OR eventCode LIKE 'PAY%'
```

Muốn lấy những record có `retryCount` ngoài khoảng 1–5 **hoặc thiếu**:

```sql
retryCount IS NULL OR retryCount NOT BETWEEN 1 AND 5
```

**Không tùy tiện mở rộng filter:** thêm `OR property IS NULL` sẽ khiến những message legacy hoặc lỗi producer bắt đầu được consumer xử lý. Đó là thay đổi nghiệp vụ cần test và có migration plan.

### Toán tử so sánh và tính toán

JMS selectors cho phép `=`, `<>`, `>`, `>=`, `<`, `<=` cùng phép toán số học trong giới hạn hỗ trợ. Khi một toán hạng là `NULL`, kết quả so sánh thông thường là U. Nhưng **hai giá trị có kiểu không tương thích** là một vấn đề khác: ví dụ property được set bằng String `"3"` và selector so sánh `retryCount > 2` **không mặc định convert String thành số 3**; đặc tả nêu kết quả biểu thức không hợp kiểu là FALSE trong trường hợp so sánh đó.

Hãy phân biệt **không có property** (NULL → UNKNOWN) với **có property sai kiểu** (có thể FALSE hoặc lỗi theo phép toán/quy định provider); chúng thường cùng “không match” nhưng nguyên nhân và cách sửa khác nhau.

## 10. Ví dụ Java 21 chạy độc lập: tự tính logic ba trạng thái

Trước khi dùng broker, có thể chứng minh bảng chân trị với Java thuần. File `TriLogicDemo.java`:

```java
public class TriLogicDemo {

    enum Truth { TRUE, FALSE, UNKNOWN }

    static Truth not(Truth x) {
        return switch (x) {
            case TRUE -> Truth.FALSE;
            case FALSE -> Truth.TRUE;
            case UNKNOWN -> Truth.UNKNOWN;
        };
    }

    static Truth and(Truth a, Truth b) {
        if (a == Truth.FALSE || b == Truth.FALSE) {
            return Truth.FALSE;
        }
        if (a == Truth.TRUE && b == Truth.TRUE) {
            return Truth.TRUE;
        }
        return Truth.UNKNOWN;
    }

    static Truth or(Truth a, Truth b) {
        if (a == Truth.TRUE || b == Truth.TRUE) {
            return Truth.TRUE;
        }
        if (a == Truth.FALSE && b == Truth.FALSE) {
            return Truth.FALSE;
        }
        return Truth.UNKNOWN;
    }

    public static void main(String[] args) {
        Truth t = Truth.TRUE;
        Truth f = Truth.FALSE;
        Truth u = Truth.UNKNOWN;

        System.out.println("TRUE AND UNKNOWN = " + and(t, u));
        System.out.println("FALSE AND UNKNOWN = " + and(f, u));
        System.out.println("TRUE OR UNKNOWN = " + or(t, u));
        System.out.println("FALSE OR UNKNOWN = " + or(f, u));
        System.out.println("NOT UNKNOWN = " + not(u));
        System.out.println("UNKNOWN OR TRUE = " + or(u, t));
    }
}
```

Biên dịch và chạy bằng Java 21:

```bash
javac TriLogicDemo.java
java TriLogicDemo
```

**Stdout chính xác** của chương trình này:

```text
TRUE AND UNKNOWN = UNKNOWN
FALSE AND UNKNOWN = FALSE
TRUE OR UNKNOWN = TRUE
FALSE OR UNKNOWN = UNKNOWN
NOT UNKNOWN = UNKNOWN
UNKNOWN OR TRUE = TRUE
```

Chương trình minh họa quy tắc toán tử và hoàn toàn không cần Jakarta JMS dependency. Nó **không phải parser SQL92** và không mô phỏng mọi trường hợp kiểu dữ liệu/nhà cung cấp. Để xác minh selector thực, phải chạy một consumer trên broker và kiểm tra những message nào được giao.

## 11. Ví dụ Spring Boot + Artemis: hai selector, hai queue tách biệt

Mục đích thí nghiệm:

1. Chứng minh `status IS NULL` cho phép nhận message thiếu `status`.
2. Chứng minh phép `status = 'READY' AND retryCount > 2` **không nhận** message thiếu `retryCount`, dù status đã đúng.
3. Chứng minh FALSE và UNKNOWN đều không khớp và **message còn lại trên queue** theo queue/broker policy.
4. Không lẫn các message kiểm thử hai selector trên cùng một queue khiến một listener cạnh tranh lấy nhầm workload của listener khác.

Đây là **một ứng dụng Spring Boot chạy được** có hai `@JmsListener` trên **hai queue độc lập**:

- `demo.selector.status`: chọn `status = 'READY' OR status IS NULL`.
- `demo.selector.retry`: chọn `status = 'READY' AND retryCount > 2`.

Điều kiện: **Java 21**, **Spring Boot 3.3.5**, Artemis broker chạy riêng tại `tcp://localhost:61616`, hai queue test đã provision hoặc Artemis được cấu hình auto-create phù hợp. Ví dụ không dựa vào một embedded broker mặc định.

### 11.1. Gradle

File `settings.gradle`:

```groovy
rootProject.name = 'selector-three-valued-demo'
```

File `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL:tcp://localhost:61616}
    user: ${JMS_USER:artemis}
    password: ${JMS_PASSWORD:artemis}
  jms:
    pub-sub-domain: false
```

Giá trị `artemis/artemis` ở đây chỉ là ví dụ local; thay bằng user/password/tài khoản có quyền trên môi trường thực, không hard-code secrets production. `pub-sub-domain=false` xác nhận destination là queue. Dependency JMS starter **không thay thế việc khởi động broker hoặc provision queue**.

### 11.2. Toàn bộ mã Java

Tạo file `src/main/java/com/example/jms/SelectorNullDemoApplication.java`:

```java
package com.example.jms;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class SelectorNullDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelectorNullDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publishCases(JmsTemplate template) {
        return args -> {
            // Queue A: status thiếu => IS NULL là TRUE.
            send(template, "demo.selector.status",
                    "S-READY", "READY", null);
            send(template, "demo.selector.status",
                    "S-MISSING", null, null);
            send(template, "demo.selector.status",
                    "S-BLOCKED", "BLOCKED", null);
            send(template, "demo.selector.status",
                    "S-EMPTY", "", null);

            // Queue B: phải thỏa status READY và retryCount > 2.
            send(template, "demo.selector.retry",
                    "R-3", "READY", 3);
            send(template, "demo.selector.retry",
                    "R-MISSING", "READY", null);
            send(template, "demo.selector.retry",
                    "R-2", "READY", 2);
            send(template, "demo.selector.retry",
                    "R-BLOCKED", "BLOCKED", null);
        };
    }

    private static void send(
            JmsTemplate template,
            String queue,
            String caseId,
            String status,
            Integer retryCount) {

        template.send(queue, session -> {
            TextMessage message = session.createTextMessage(caseId);
            message.setStringProperty("caseId", caseId);

            // Không đặt property chính là cách tạo giá trị thiếu.
            if (status != null) {
                message.setStringProperty("status", status);
            }
            if (retryCount != null) {
                message.setIntProperty("retryCount", retryCount);
            }
            return message;
        });
    }
}

@Component
class SelectorConsumers {

    @JmsListener(
            destination = "demo.selector.status",
            selector = "status = 'READY' OR status IS NULL")
    public void onStatus(TextMessage message) throws JMSException {
        System.out.println(
                "STATUS " + message.getText()
                + " hasStatus="
                + message.propertyExists("status"));
    }

    @JmsListener(
            destination = "demo.selector.retry",
            selector = "status = 'READY' AND retryCount > 2")
    public void onRetry(TextMessage message) throws JMSException {
        System.out.println("RETRY " + message.getText());
    }
}
```

Giải thích:

- `@SpringBootApplication` tạo application context; `@EnableJms` bật nhận diện `@JmsListener`.
- `ApplicationRunner` được Spring Boot gọi sau khi context đã khởi tạo. Nó gửi tám message, chia đúng hai queue; listener lifecycle do Spring quản lý.
- `JmsTemplate.send` dùng `MessageCreator` để tạo raw `TextMessage`. Không cần `MessageConverter` và không có JSON body gây nhầm lẫn; payload chỉ chứa mã case.
- `status == null` ở **biến Java truyền vào method helper** dẫn đến **không gọi `setStringProperty`**. Đây là cách có chủ đích tạo message **thiếu property**.
- `retryCount` dùng `setIntProperty`, nên biểu thức số học `retryCount > 2` có kiểu tương thích.
- Listener nhận raw `TextMessage` và dùng `propertyExists("status")` để cho thấy S-MISSING thật sự không có property.
- Mỗi listener chỉ xử lý các message có biểu thức selector đánh giá `TRUE`; message không khớp không đi vào callback của listener đó.

### 11.3. Kết quả kỳ vọng theo logic chuẩn

Bảng cho queue `demo.selector.status`:

| Message | status | `status = 'READY'` | `status IS NULL` | OR | Listener nhận? |
| --- | --- | --- | --- | --- | --- |
| S-READY | READY | T | F | T | **Có** |
| S-MISSING | thiếu | U | T | T | **Có** |
| S-BLOCKED | BLOCKED | F | F | F | Không |
| S-EMPTY | `""` | F | F | F | Không |

Bảng cho queue `demo.selector.retry`:

| Message | status | retryCount | `status='READY'` | `retryCount > 2` | AND | Listener nhận? |
| --- | --- | --- | --- | --- | --- | --- |
| R-3 | READY | 3 (int) | T | T | T | **Có** |
| R-MISSING | READY | thiếu | T | U | U | Không |
| R-2 | READY | 2 (int) | T | F | F | Không |
| R-BLOCKED | BLOCKED | thiếu | F | U | F | Không |

Vì listener chạy bất đồng bộ, không cam kết thứ tự log. Trong môi trường test **sạch**, tập các dòng nghiệp vụ cần quan sát là:

```text
STATUS S-READY hasStatus=true
STATUS S-MISSING hasStatus=false
RETRY R-3
```

Đây là **tập dòng kỳ vọng**, không phải thứ tự stdout bắt buộc và không bao gồm Spring Boot startup logs. Trên queue `demo.selector.status` còn S-BLOCKED/S-EMPTY; trên queue `demo.selector.retry` còn R-MISSING/R-2/R-BLOCKED nếu không có consumer khác, TTL, expiry hoặc chính sách làm mất chúng. Không dùng mô tả tồn dư như một cam kết message được giữ vô hạn.

### 11.4. Cách chạy

Từ project đã có Gradle wrapper:

```bash
# Linux/macOS:
./gradlew bootRun

# Windows:
gradlew.bat bootRun
```

Chạy trên broker test riêng với các queue không có messages cũ. Nếu sử dụng cùng queue qua nhiều lần `bootRun`, `ApplicationRunner` sẽ gửi **thêm** tám message mỗi lần; các message không match có thể tích lại trên broker, tạo backlog.

Broker có thể tự tạo queue khi auto-create bật. Nếu môi trường tắt auto-create, hãy provision hai queue bằng quản trị Artemis trước khi chạy. Java `Session.createQueue` hoặc `JmsTemplate.send` **không bảo đảm** queue vật lý tồn tại trên mọi JMS broker.

## 12. Vì sao dùng hai queue cho thí nghiệm?

Nếu đặt hai `@JmsListener` có selector khác nhau trên **cùng queue**, hai consumers có thể **cạnh tranh** nhận các message thỏa selector của mình. Một message có thể thỏa cả hai selectors, nhưng trong queue point-to-point nó không trở thành hai bản sao để hai listener cùng xử lý. Điều này khiến số log không phản ánh trực tiếp bảng chân trị.

Thí nghiệm dùng hai queue để giữ bộ test độc lập:

- Queue A kiểm tra `OR` và `IS NULL`.
- Queue B kiểm tra `AND` và dữ liệu thiếu.
- Mỗi message chỉ đưa vào một queue tương ứng.

Nếu muốn broadcast cùng một event đến nhiều consumer groups, hãy thiết kế topic và subscriptions hoặc nhiều fan-out queues, **không** coi hai consumers của cùng một queue là mô hình broadcast.

### Message không match có bị mất không?

Không nên trả lời chung “có” hoặc “không” cho mọi loại destination:

- Với **queue**, message chưa match consumer này có thể tiếp tục chờ consumer khác có selector phù hợp, chờ selector thay đổi/redeploy, hoặc bị ảnh hưởng bởi TTL, expiry, broker quota và các policies.
- Với **topic**, khả năng message được giữ hay không còn phụ thuộc subscription là durable hay non-durable, active/offline, selector được đặt khi đăng ký và chính sách broker. Không dùng lập luận queue để suy ra topic luôn giữ message bị loại.
- **Selector không phải câu lệnh xóa, ACK hay DLQ.** Bị filter ra chưa đồng nghĩa được xử lý thất bại hoặc được chuyển dead-letter.

Vì vậy khi thấy consumer không nhận message, hãy kiểm tra queue backlog, consumer selectors, expiry/DLQ và routes trước khi kết luận producer chưa gửi.

## 13. Dữ liệu sai kiểu: khác hoàn toàn với dữ liệu thiếu

JMS selector **không áp dụng** các conversion giống getter typed của `Message` khi đánh giá property.

Ví dụ producer:

```java
// Đang tạo một JMS Message mới:
message.setStringProperty("retryCount", "3");
```

Consumer lại dùng:

```sql
retryCount > 2
```

`retryCount` **không thiếu**; nó tồn tại dưới dạng **String `"3"`**, trong khi `2` là literal số. Theo quy tắc so sánh kiểu của JMS selector, trường hợp không tương thích này không match, chứ không tự parse `"3"` thành số `3`.

Ngược lại:

```java
message.setIntProperty("retryCount", 3);
```

cho phép selector đánh giá đúng kiểu số.

**Không dùng `IS NOT NULL` để thay kiểm tra type:** `retryCount IS NOT NULL` vẫn TRUE khi giá trị là String `"3"`, dù so sánh số có thể thất bại.

### Boolean false khác property thiếu

Hai message:

```java
message.setBooleanProperty("urgent", false);
```

và message không hề đặt `urgent`.

| Selector | urgent=false | urgent thiếu |
| --- | --- | --- |
| `urgent = FALSE` | TRUE | UNKNOWN |
| `urgent = TRUE` | FALSE | UNKNOWN |
| `NOT urgent` | TRUE | UNKNOWN |
| `urgent IS NULL` | FALSE | TRUE |
| `urgent IS NOT NULL` | TRUE | FALSE |

**Giải pháp phụ thuộc nghiệp vụ:** nếu urgent thiếu cần xem là “không khẩn”, dùng `urgent IS NULL OR urgent = FALSE`; nếu thiếu là lỗi hợp đồng, dùng validation và đưa message vào luồng kiểm soát. Đừng để logic “thiếu nghĩa là false” xuất hiện ngầm.

## 14. Cú pháp, độ ưu tiên và dấu ngoặc

Một số nguyên tắc dễ gây nhầm lẫn:

- Độ ưu tiên giữa các toán tử logic: **`NOT` > `AND` > `OR`**.
- Dấu ngoặc `(...)` làm rõ ý đồ và tránh việc thêm một nhánh `IS NULL` làm thay đổi toàn bộ điều kiện.
- Dùng dấu nháy đơn cho String literal: `'READY'`, không dùng dấu nháy kép như Java string trong câu selector.
- `<>` là toán tử không bằng theo SQL92; `!=` **không phải ký hiệu bảo đảm portable** trong subset selector JMS.
- Các từ khóa operator không phân biệt hoa/thường, nhưng **tên property thì có phân biệt**.
- Các tên bắt đầu `JMSX` hoặc `JMS_` được dành cho standard/provider; đặt tên property ứng dụng riêng, không tự chiếm prefix.
- Provider xác minh cú pháp khi tạo consumer; biểu thức không hợp lệ có thể gây `InvalidSelectorException`/`JMSException` tùy API, không phải silently match nothing.
- JMS không hỗ trợ toàn bộ SQL, vì vậy không tự thêm `COALESCE`, `CASE WHEN`, SQL joins hoặc SQL comments vào selector.

So sánh hai biểu thức:

```sql
status = 'READY' AND retryCount > 2 OR status IS NULL
```

và:

```sql
status = 'READY' AND (retryCount > 2 OR status IS NULL)
```

Biểu thức thứ nhất là `(status='READY' AND retryCount>2) OR status IS NULL` do `AND` ưu tiên hơn `OR`; nó sẽ nhận message **thiếu status**. Biểu thức thứ hai yêu cầu status là READY trước, vì vậy message thiếu status không match. Đây có thể là sự khác biệt nghiệp vụ lớn chỉ do dấu ngoặc.

**Mẫu an toàn để thay thế:** luôn thêm dấu ngoặc quanh một điều kiện tổng hợp khi trộn `AND` với `OR`, ví dụ `eventType='OrderCreated' AND (status IS NULL OR status <> 'READY')`.

## 15. Các mẫu selector an toàn cho dữ liệu không đồng nhất

### 15.1. Mặc định chặt: chỉ nhận message hợp đồng đầy đủ

```sql
eventType = 'OrderCreated'
AND schemaVersion = 1
AND tenantId IS NOT NULL
AND status IN ('READY', 'BLOCKED')
```

Điều này bỏ qua các message thiếu bất kỳ property nào; nó **không** chứng nhận tenantId có giá trị hợp lệ hoặc payload đúng JSON schema.

### 15.2. Tương thích producer cũ thiếu property tùy chọn

Giả sử phiên bản cũ không set `region` và muốn dùng vùng mặc định APAC:

```sql
eventType = 'OrderCreated'
AND (region IS NULL OR region = 'APAC')
```

Chỉ phù hợp khi nghiệp vụ đã thống nhất **vắng region = APAC**, có test tương thích và có kế hoạch dừng fallback khi migration xong.

### 15.3. Chọn tất cả message không thuộc nhóm READY, kể cả thiếu status

```sql
status IS NULL OR status <> 'READY'
```

Chỉ dùng nếu message thiếu status là đối tượng consumer phải chủ động xử lý. Nếu trạng thái thiếu đồng nghĩa dữ liệu hỏng, hãy phân tách queue test/validation/DLQ thay vì cho vào business flow.

### 15.4. Chỉ nhận message không READY và có giá trị status

```sql
status IS NOT NULL AND status <> 'READY'
```

Nên bổ sung kiểm tra enum hợp lệ khi xử lý. Một String `'WRONG'` cũng khác READY.

### 15.5. Nhận message urgent=false hoặc không có urgent

```sql
urgent = FALSE OR urgent IS NULL
```

Khác với `NOT urgent` vì missing urgent sẽ đánh giá UNKNOWN ở vế đó.

### 15.6. Làm rõ ranh giới hỗ trợ schemaVersion

```sql
eventType = 'OrderCreated'
AND schemaVersion = 1
```

Bỏ qua message thiếu schemaVersion. Nếu producer legacy không có property này, muốn nhận legacy phải thiết kế rõ ràng một nhánh:

```sql
eventType = 'OrderCreated'
AND (schemaVersion IS NULL OR schemaVersion = 1)
```

Nhưng **hãy xác nhận schema body của legacy thực sự tương thích với v1**, không chỉ cho phép selector nhận thêm message. Consumer có thể parse lỗi hoặc xử lý sai nếu body không tuân hợp đồng.

## 16. Quan sát và kiểm thử khi message không được chọn

Một selector đánh giá U không tạo exception mặc định; nó thường chỉ khiến message **không match**. Điều này làm production debugging khó hơn lỗi parse rõ ràng.

### Checklist kiểm tra

1. **Tách ba tầng:** producer đã gửi? broker đã nhận? consumer selector có match? HTTP/API producer trả thành công chưa chứng minh consumer đã nhận.
2. **Kiểm tra đúng broker và destination:** queue/topic, namespace, address/routing, consumers, ACL.
3. **Xem message properties:** `propertyExists`, tên có phân biệt hoa/thường, kiểu `String/int/boolean` thực tế và message headers.
4. **Không nhìn JSON body để kết luận selector thấy property.**
5. **Tính T/F/U từng điều kiện:** nếu thiếu, đánh dấu U; dùng bảng AND/OR/NOT để ra kết quả cuối.
6. **Chú ý selector của mỗi consumer:** một message trong queue có thể được nhận bởi consumer khác, kể cả consumer có selector rỗng, nên không suy luận từ một listener log.
7. **So sánh cấu hình giữa môi trường:** broker provider, version, auto-create policy, producer metadata, selector sau redeploy.
8. **Quan sát backlog và TTL/expiry:** message không match có thể tồn, expire hoặc bị xử lý bởi consumer khác tùy hệ thống.
9. **Đo lượng message thiếu metadata:** producer nên emit metric hoặc đặt contract tests kiểm tra required properties để tránh backlog âm thầm.
10. **Dùng queue test riêng** khi thay selector; đừng đổ message giả, xóa backlog hoặc thử consumer không selector trên production queue.

### Kiểm thử hồi quy bắt buộc

| Test case | Input JMS property | Selector kiểm thử | Kỳ vọng |
| --- | --- | --- | --- |
| Khớp trực tiếp | status READY | `status='READY'` | MATCH |
| Sai trực tiếp | status BLOCKED | `status='READY'` | NO MATCH (F) |
| Thiếu trực tiếp | không có status | `status='READY'` | NO MATCH (U) |
| Thiếu với NOT | không có status | `NOT(status='READY')` | NO MATCH (U) |
| Thiếu với IS NULL | không có status | `status IS NULL` | MATCH |
| Empty khác NULL | status `""` | `status IS NULL` | NO MATCH |
| False khác NULL | urgent=false | `urgent IS NULL` | NO MATCH |
| Boolean thiếu | không có urgent | `NOT urgent` | NO MATCH (U) |
| AND false với unknown | status BLOCKED, thiếu retry | `status='READY' AND retryCount>2` | NO MATCH (F) |
| AND true với unknown | status READY, thiếu retry | Cùng selector | NO MATCH (U) |
| OR true với unknown | status READY, thiếu retry | `status='READY' OR retryCount>2` | MATCH |
| String không là số | retryCount String `"3"` | `retryCount>2` | NO MATCH vì không hợp kiểu |

Để **phân biệt F và U**, đừng chỉ dùng số message nhận được: hai trạng thái đều không match. Cần biết metadata đầu vào và đánh giá biểu thức hoặc dùng một chương trình truth-table riêng như mục 10. Nếu broker cung cấp trace selector, dùng nó theo tài liệu provider nhưng không giả định mọi broker log ba trạng thái ra console.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Dùng `NOT (status='READY')` để bắt cả status thiếu | Missing status → U, không nhận | `status IS NULL OR status <> 'READY'` nếu nghiệp vụ thực sự muốn nhận missing. |
| Xem FALSE và UNKNOWN là một | Dự đoán sai khi thêm OR/NOT | Dùng bảng chân trị T/F/U. |
| Xem `""` là NULL | Lọc sai message có empty String | Validate và đặt điều kiện empty riêng. |
| Xem `false` là property chưa set | Bỏ nhầm message Boolean false | Dùng `propertyExists` và so sánh Boolean đúng kiểu. |
| Dùng `status = NULL` | Không phải cách kiểm tra null chuẩn | `status IS NULL`. |
| Chỉ đặt status trong JSON body | Selector thấy property vắng → U | Set JMS property trong `MessagePostProcessor` hoặc `MessageCreator`. |
| Đặt retryCount bằng String `"3"` nhưng so sánh `> 2` | So sánh sai kiểu; không match | `setIntProperty("retryCount",3)`. |
| Tên property khác chữ hoa | `status` khác `Status` | Chuẩn hóa contract tên field. |
| Không đặt ngoặc khi trộn AND/OR | Selector nhận rộng hoặc hẹp hơn ý định | Dùng ngoặc theo business rule. |
| Tưởng message không match bị xóa | Backlog bất ngờ và thông điệp lặng lẽ tồn | Quan sát queue consumers, expiry, TTL và DLQ. |
| Dùng selector như schema validator | Dữ liệu tồn tại nhưng vô nghĩa vẫn được nhận | Schema validation ở producer/consumer. |
| Dùng queue có nhiều listener như topic broadcast | Message được phân chia giữa consumers | Dùng topic/subscription/fan-out queues nếu cần bản sao. |
| Chỉ test data đầy đủ | Không phát hiện missing-property regression | Thêm missing/empty/false/zero/wrong-type cases. |

## 18. Câu hỏi tự kiểm tra và bài tập

1. Với `status` thiếu, biểu thức `status='READY'` cho kết quả gì? Vì sao không được giao?
2. Tại sao `NOT(status='READY')` không chọn message thiếu status?
3. Viết bảng chân trị `AND` và `OR` cho ba giá trị T/F/U; nêu ý nghĩa của `FALSE AND UNKNOWN` và `TRUE OR UNKNOWN`.
4. Viết selector cho “không READY và status bắt buộc tồn tại”.
5. Viết selector cho “không READY hoặc không có status”. Vì sao khác câu 4?
6. `status=""` và thiếu `status` có giống nhau không? Dùng operator nào để phân biệt?
7. Một producer set `urgent=false`, producer khác bỏ property `urgent`. `NOT urgent` chọn message nào?
8. Với `eventType='OrderCreated'` và retryCount thiếu, tính kết quả của `eventType='OrderCreated' AND retryCount>2` và phiên bản dùng OR.
9. Tại sao `setStringProperty("retryCount","3")` không tương đương `setIntProperty("retryCount",3)` trong selector?
10. Vì sao selector không nhìn thấy `status` nằm trong JSON body của `TextMessage`?
11. So sánh ý nghĩa của `status IS NULL` và `status = 'null'`.
12. Khi hai `@JmsListener` dùng hai selectors trên cùng một queue, tại sao không thể xem hai log outputs như fan-out?
13. Thiết kế một bảng test cho message thiếu `schemaVersion` khi nâng cấp producer từ legacy sang v1.
14. Nếu queue backlog tăng mà listener không lỗi, bạn sẽ kiểm tra những thông tin gì trước tiên?
15. Dùng `propertyExists` và bảng chân trị để giải thích vì sao một message bị filter dù nó mang JSON body có field đúng.

**Kết luận:** Trong JMS selector, **property thiếu ⇒ NULL ⇒ phép so sánh thường cho UNKNOWN**; `NOT UNKNOWN` vẫn là UNKNOWN, chỉ **TRUE** mới match. `IS NULL`/`IS NOT NULL` giúp nói rõ hành vi mong muốn khi metadata thiếu; `AND`/`OR` cần được tính theo bảng chân trị. Viết selector đúng không chỉ là cú pháp SQL92 mà còn là **hợp đồng đặt properties đúng kiểu và quyết định nghiệp vụ với dữ liệu thiếu**.

### Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 – Message selector và Null values](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#message-selector) — định nghĩa subset SQL92, property thiếu, bảng chân trị AND/OR/NOT và điều kiện TRUE-only.
- [Jakarta Messaging – Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — `propertyExists`, JMS headers/properties và các getter/setter.
- [Spring Framework – Annotated JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener(selector=...)`, listener container factory và raw JMS arguments.
- [Spring Framework – Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` và `MessageCreator`.
- [Apache ActiveMQ Artemis – JMS Support](https://artemis.apache.org/components/artemis/documentation/latest/) — broker/JMS queue routing, consumers, message selection và quản trị backlog.
