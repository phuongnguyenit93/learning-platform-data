# Kiểm thử message khớp, không khớp và sai kiểu dữ liệu

> **Chủ đề:** Lọc thông điệp trong Spring Framework JMS. Bài này tập trung kiểm thử **JMS Message Selector** khi message **khớp**, **không khớp**, **thiếu property**, **sai kiểu property**, hoặc **body mang kiểu JMS khác dự kiến**. Điểm quan trọng: một selector lựa chọn message dựa trên **JMS headers và message properties**, **không đọc JSON/text body**. Một message không được chọn không đồng nghĩa đã bị xóa khỏi queue.

## 1. Mục tiêu và kết quả cần chứng minh

Sau bài học, bạn có thể:

1. Viết selector SQL-92 subset như `eventType = 'order.created' AND score >= 8`.
2. Phân biệt “message **không khớp** vì giá trị” với “**không khớp** vì kiểu property”, và với “**không khớp** vì property thiếu”.
3. Giải thích vì sao `setStringProperty("score", "9")` **không tương đương** `setIntProperty("score", 9)` khi dùng selector số `score >= 8`.
4. Biết rằng `NULL` tạo logic ba giá trị: TRUE, FALSE, UNKNOWN; chỉ TRUE mới được chọn.
5. Thử `receiveSelected` bằng bộ dữ liệu có ID riêng, timeout hữu hạn, rồi xác nhận **message chưa khớp vẫn còn** trên queue thử.
6. Phân biệt **sai kiểu property trong selector** với **sai kiểu JMS body** (`TextMessage` vs `BytesMessage`): selector có thể khớp metadata dù consumer không giải mã được body.
7. Tạo và chạy một chương trình Java 17/Spring Boot 3.3.5/ActiveMQ Artemis có assertions rõ ràng cho từng trường hợp.
8. Biết cách chẩn đoán lỗi syntax `InvalidSelectorException`, case-sensitive property, mismatch giữa producer/consumer và cạnh tranh nhiều consumers.

**Tiêu chí PASS:** Chỉ message có `score` kiểu số và giá trị đạt ngưỡng mới được chọn bởi `score >= 8`; message score thấp, score là String, và score không tồn tại **không bị lấy** bởi selector ấy. Sau đó, các message chưa khớp phải vẫn nhận được bằng selector thích hợp trên **queue thử riêng**. Một message có `BytesMessage` body vẫn có thể khớp selector dựa trên `score` — lỗi body type phải được phát hiện **sau** khi nhận.

## 2. Selector thực sự kiểm tra trường nào?

JMS selector là một biểu thức điều kiện dạng subset SQL-92. JMS provider dùng nó để quyết định một message có được giao cho một consumer cụ thể hay không.

~~~text
Producer A                       Broker / Queue                Consumer #1
  TextMessage
  properties:
    eventType = "invoice"
    score = 9 (int)  ------------> message pending
                                           |
                                           v
                                  selector:
                                  eventType = 'invoice'
                                  AND score >= 8  -----> ĐƯỢC GIAO (TRUE)

Producer B
  TextMessage
  properties:
    eventType = "invoice"
    score = "9" (String) --------> message pending
                                           |
                                           v
                                  cùng selector --------> KHÔNG GIAO (FALSE)
                                                         message vẫn ở queue
~~~

Selector có thể sử dụng:
- **JMS standard headers được phép trong selector**: `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, `JMSType`.
- **Message properties** do producer đặt, chẳng hạn `eventType`, `score`, `schemaVersion`, `tenantId`, `urgent`.
- **Một số JMSX/provider properties** phù hợp, tùy đặc tả và provider hỗ trợ.

**Không thể** dùng selector đọc trực tiếp:
- `TextMessage.getText()` hoặc một field bên trong JSON body.
- Mảng bytes của `BytesMessage`.
- Một thuộc tính Java DTO chỉ tồn tại trong bộ nhớ producer mà chưa được ánh xạ sang JMS property.
- Tùy ý mọi JMS header: ví dụ `JMSExpiration` **không nằm trong danh sách standard header references** được JMS selector cho phép, dù có getter trên `Message`.

Để lọc theo trường nghiệp vụ trong JSON, producer phải **chép trường đó thành JMS property** (nếu thích hợp), hoặc dùng consumer parse/validate sau khi nhận. Việc lọc theo body ở broker đôi khi có tính năng riêng của vendor (ví dụ Artemis XPath), **không phải JMS selector portable**.

## 3. Property type là một phần của hợp đồng message

Xét hai lệnh:

~~~java
// Cùng chữ số 9, nhưng khác kiểu dữ liệu trên wire.
message.setIntProperty("score", 9);       // java.lang.Integer, JMS int
message.setStringProperty("score", "9");  // java.lang.String, JMS String
~~~

Hai lệnh trên là **hai ví dụ riêng**, không nên gọi nối tiếp lên cùng property nếu mục tiêu là chứng minh khác kiểu: lệnh sau sẽ thay thế giá trị trước. Trong một thí nghiệm thật, tạo **hai message** khác nhau.

Selector:

~~~sql
score >= 8
~~~

**Kết quả theo Jakarta Messaging 3.1:**
- `score` là **int 9** → so sánh số hợp lệ → TRUE.
- `score` là **int 3** → so sánh số hợp lệ → FALSE.
- `score` là **String "9"** → so sánh String với literal số không cùng kiểu → FALSE; provider **không tự parse** chuỗi thành số cho JMS selector chuẩn.
- Không có property `score` → giá trị được xem là `NULL` → kết quả UNKNOWN → không được chọn.

**Điểm dễ nhầm:** các quy tắc chuyển đổi của API `message.getIntProperty("score")` khi đọc property không phải quy tắc của selector. JMS có hỗ trợ một số chuyển đổi getter từ `String` sang số, nhưng **JMS selector không áp dụng bảng chuyển đổi getter đó**. Vì vậy, việc một consumer đọc được `getIntProperty("score") == 9` từ một String property **không chứng minh** selector số sẽ khớp.

### 3.1. Ma trận kết quả cần kiểm thử

Giả sử mọi message có `eventType = "order.created"`, selector:

~~~sql
eventType = 'order.created' AND score >= 8
~~~

| Case | Cách producer đặt `score` | Giá trị JMS property | Kết quả selector | Lý do |
| --- | --- | --- | --- | --- |
| MATCH | `setIntProperty("score", 9)` | số nguyên `9` | **TRUE → nhận** | Khác biệt `9 >= 8` là phép so sánh số hợp lệ |
| NON_MATCH | `setIntProperty("score", 3)` | số nguyên `3` | **FALSE → không nhận** | `3 >= 8` sai |
| WRONG_TYPE | `setStringProperty("score", "9")` | chuỗi `"9"` | **FALSE → không nhận** | String không tự thành số |
| MISSING | Không đặt property `score` | `NULL` | **UNKNOWN → không nhận** | Toán tử so sánh với NULL cho UNKNOWN |
| WRONG_EVENT | `setIntProperty("score", 9)`, nhưng `eventType = "other"` | số nguyên `9` | **FALSE → không nhận** | Vế `eventType` không khớp |
| WRONG_BODY_TYPE | `BytesMessage` với `score` int `10` | số nguyên `10`, body bytes | **TRUE → có thể nhận** | Selector không đọc/kiểm tra body |

Trong phần chạy thực tế, ta dùng `runId` ngẫu nhiên và một queue thử để cô lập mỗi lần chạy. Message chưa khớp được kiểm tra **sau khi lần thử chọn message khớp** bằng những selector khác. Không dựa vào queue rỗng hoặc thứ tự mặc định của broker để kết luận.

### 3.2. So sánh với String literal

Nếu producer cố tình gửi `score` dưới dạng String `"9"`, selector String tương ứng là:

~~~sql
score = '9'
~~~

Selector trên có thể chọn message String `"9"`, nhưng **không** chọn message số int `9` vì hai kiểu khác nhau. Đây là một test bổ sung để chứng minh provider vẫn giữ message sai kiểu cho tới khi có consumer phù hợp.

Không nên chọn String cho dữ liệu cần so sánh mức ngưỡng hoặc tính toán số. So sánh String dùng thứ tự theo ký tự và các operator được hỗ trợ cho chuỗi (thông dụng là `=`, `<>`, `LIKE`), **không được dùng `score >= '8'` để giả lập số**. Hợp đồng producer nên quy định rõ field là `int`/`long` và mọi bên tuân thủ.

## 4. FALSE khác UNKNOWN: property thiếu hoặc NULL

JMS selector sử dụng logic ba giá trị của SQL: `TRUE`, `FALSE`, `UNKNOWN`.

Một property không tồn tại được thay bằng `NULL` trong biểu thức. So sánh với NULL không trả về FALSE trực tiếp mà thường là UNKNOWN. **Chỉ TRUE mới chọn message**.

| Biểu thức | `score = 9` (int) | `score = 3` (int) | Không có `score` |
| --- | --- | --- | --- |
| `score >= 8` | TRUE | FALSE | UNKNOWN |
| `NOT (score >= 8)` | FALSE | TRUE | UNKNOWN |
| `score IS NULL` | FALSE | FALSE | TRUE |
| `score IS NOT NULL` | TRUE | TRUE | FALSE |
| `score >= 8 OR score IS NULL` | TRUE | FALSE | TRUE |
| `score >= 8 AND score IS NOT NULL` | TRUE | FALSE | FALSE |

**Hệ quả quan trọng:** `NOT (score >= 8)` **không chọn** message không có `score`. Để lấy message thiếu field, dùng `score IS NULL`. Đừng dùng `score = NULL` hay `score <> NULL` để kiểm tra NULL; chúng không có ý nghĩa như `IS NULL`/`IS NOT NULL`.

Logic ba giá trị cũng ảnh hưởng biểu thức phức tạp:
- `TRUE AND UNKNOWN` → UNKNOWN;
- `FALSE AND UNKNOWN` → FALSE;
- `TRUE OR UNKNOWN` → TRUE;
- `FALSE OR UNKNOWN` → UNKNOWN;
- `NOT UNKNOWN` → UNKNOWN.

Ví dụ một message thiếu `score`:
- `eventType = 'order.created' AND score >= 8` → UNKNOWN → không nhận.
- `eventType = 'order.created' AND score IS NULL` → TRUE → nhận.
- `eventType = 'order.created' OR score >= 8` → TRUE nếu `eventType` khớp, dù `score` thiếu.

Vì vậy cần test cả **property thiếu** chứ không chỉ giá trị sai. Một biểu thức dùng `OR` vô tình có thể mở rộng số message được nhận vượt dự kiến.

## 5. Cú pháp selector và các trường hợp dễ sai

### 5.1. Các toán tử phổ biến

| Nhu cầu | Selector hợp lệ | Chú ý |
| --- | --- | --- |
| So sánh String | `eventType = 'order.created'` | String literal trong dấu nháy đơn |
| So sánh số | `score >= 8` | `score` phải là kiểu số phù hợp |
| Boolean | `urgent = TRUE` | `TRUE` không có nháy |
| Kết hợp | `eventType = 'order.created' AND score >= 8` | Cả hai vế phải TRUE |
| Một trong nhiều loại | `eventType IN ('order.created','order.updated')` | Các phần tử phải đúng kiểu |
| Theo prefix | `eventType LIKE 'order.%'` | `%` là wildcard trong LIKE |
| Thiếu property | `score IS NULL` | Không viết `score = NULL` |
| Có property | `score IS NOT NULL` | Không chứng minh đúng kiểu |
| Dựa vào header | `JMSPriority >= 7` | Priority là JMS header hợp lệ |
| Phân biệt delivery mode | `JMSDeliveryMode = 'PERSISTENT'` | Đây là **String trong selector**, không phải số `2` |
| Theo correlation | `JMSCorrelationID = 'request-123'` | ID phải được producer đặt |

**Property names phân biệt chữ hoa/chữ thường:** `eventType` và `EventType` là hai identifiers khác nhau. Selector keywords (`AND`, `OR`, `IN`, `LIKE`) không phân biệt hoa-thường, nhưng **tên property và nội dung String literal** có phân biệt.

### 5.2. Lỗi cú pháp và lỗi dữ liệu khác nhau

- `score >=` → **sai cú pháp**; provider phải từ chối selector không hợp lệ, thường bằng `jakarta.jms.InvalidSelectorException` hoặc exception của Spring bọc lại.
- `score >= 8` nhưng producer đặt String `"9"` → **biểu thức đúng cú pháp, dữ liệu không đúng kiểu**; không bắt buộc ném exception khi tạo consumer. Message thường **không khớp**.
- `score > 8` nhưng property thiếu → **đúng cú pháp**, kết quả UNKNOWN, không khớp.
- `score >= 8` nhưng score int `3` → **đúng cú pháp**, kết quả FALSE, không khớp.

Đừng gom cả bốn tình huống vào một nhóm “selector failed”. Việc không nhận được message không đủ chứng minh selector sai cú pháp hay server chặn quyền.

### 5.3. Tên property và escape

JMS selector identifiers có quy tắc như Java identifiers. Nên dùng tên đơn giản như `eventType`, `tenantId`, `score`, `schemaVersion`. Tên chứa dấu chấm, gạch nối hoặc ký tự đặc biệt có thể cần cơ chế vendor-specific nếu muốn lọc; tránh lệ thuộc cú pháp mở rộng khi muốn portable JMS.

Với String literal, dấu nháy đơn bên trong phải được viết thành hai dấu nháy đơn. Ví dụ giá trị `O'Brien` trong selector:

~~~sql
customerName = 'O''Brien'
~~~

**Không** ghép input người dùng chưa kiểm soát vào selector. Dùng ID/enum đã validate hoặc cơ chế escape chính xác; khi xây điều kiện động phức tạp, tốt nhất ánh xạ input vào tập giá trị an toàn do ứng dụng xác định.

## 6. Vòng đời message **không khớp** trên queue

Với **JMS queue thông thường** và một consumer có selector:

~~~text
Broker queue demo.selector.tests
  |
  |-- Message #1: score=9 (int)
  |       |
  |       +--> Consumer selector score >= 8: nhận #1
  |
  |-- Message #2: score=3 (int)
  |       |
  |       +--> Consumer selector score >= 8: KHÔNG nhận
  |       +--> vẫn pending, consumer phù hợp khác có thể nhận
  |
  |-- Message #3: score="9" (String)
  |       |
  |       +--> Consumer selector score >= 8: KHÔNG nhận
  |       +--> Consumer selector score = '9': có thể nhận
  |
  |-- Message #4: thiếu score
          |
          +--> Consumer selector score >= 8: KHÔNG nhận
          +--> Consumer selector score IS NULL: có thể nhận
~~~

**Không khớp ≠ bị xóa.** Với queue, message không phù hợp selector của consumer này có thể nằm trong queue chờ consumer khác. Tuy nhiên, không được khẳng định nó sẽ ở đó mãi: TTL/expiration, broker purge, các queue filters, DLQ/expiry address, quotas và consumer khác có thể ảnh hưởng.

Đặc biệt phân biệt:
- **Consumer selector:** broker đã route message vào queue; consumer chỉ nhận những message có selector TRUE.
- **Queue/address filter của Artemis:** có thể lọc ngay khi message được route, khiến message không bao giờ vào queue đó. Đây là một lớp khác.
- **Topic non-durable subscription:** message không khớp một subscriber có thể không được lưu cho subscriber ấy theo cùng cách queue; đừng lấy kết quả queue để suy ra cho mọi topic/subscription.

Để chứng minh message không khớp **còn pending**, cần thử lại bằng một selector khác, hoặc dùng cơ chế browse/metrics của broker với test queue. Đừng chỉ nói “receive trả null vậy message bị bỏ”.

## 7. Kiến trúc của bộ test đầy đủ

Ta sẽ tạo **năm case** trong một queue thử và dùng `runId` riêng:

| Case ID | Body | Properties | Được selector `score >= 8` chọn? |
| --- | --- | --- | --- |
| `HIGH` | `TextMessage("case:HIGH")` | `score` int `9` | Có |
| `LOW` | `TextMessage("case:LOW")` | `score` int `3` | Không |
| `WRONG_TYPE` | `TextMessage("case:WRONG_TYPE")` | `score` String `"9"` | Không |
| `MISSING` | `TextMessage("case:MISSING")` | Không có `score` | Không |
| `WRONG_BODY_TYPE` | `BytesMessage` chứa 2 bytes | `score` int `10` | **Có**: selector không xét body |

Thứ tự test:
1. Tạo `runId` dạng UUID, gửi bốn `TextMessage`: HIGH, LOW, WRONG_TYPE, MISSING.
2. Consumer với `runId = 'uuid' AND score >= 8` nhận **HIGH**.
3. Gọi cùng selector lần nữa và chờ timeout hữu hạn → `null`; chứng minh không còn message **khớp tiêu chí số** tại thời điểm thử.
4. Dùng `score = '9'` để lấy lại WRONG_TYPE và xác nhận property đúng là `String`.
5. Dùng `score < 8` lấy LOW, dùng `score IS NULL` lấy MISSING; chứng minh các message từng bị loại **chưa bị consumer trước đó tiêu thụ**.
6. Gửi thêm `BytesMessage` có `score=10`; dùng selector số lấy message này; kiểm tra `instanceof BytesMessage` và không giả định `TextMessage`.
7. Chỉ in `ALL_ASSERTIONS_PASSED` sau khi mọi assertion thành công.

**Vì sao gửi WRONG_BODY_TYPE sau cùng?** Để lần nhận numeric đầu tiên chỉ có một message khớp (HIGH), giúp kết quả kiểm tra không phụ thuộc thứ tự phân phối. Khi gửi thêm bytes case, phép thử body type mới được cô lập hoàn toàn.

**Vì sao mọi selector đều có `runId`?** Nếu queue còn message từ lần thử trước, một selector quá rộng có thể nhận message cũ và làm test sai. `runId` UUID mới và kiểm tra `caseId` làm từng phép đo độc lập.

## 8. Project chạy được: Java 17 + Spring Boot 3.3.5 + Artemis

### 8.1. Điều kiện chạy

- JDK 17+, Gradle đã cài (hoặc tạo Gradle wrapper).
- Broker **ActiveMQ Artemis** ở `tcp://localhost:61616`; queue **anycast** tên `demo.selector.tests` đã tạo trước hoặc broker test cho phép auto-create.
- Credentials `demo/demo` chỉ là ví dụ cho broker học đã được cấu hình; phải thay bằng tài khoản thật của môi trường test.
- Tài khoản có quyền **send** và **consume** trên queue này.
- Không có consumer khác đang đọc từ queue demo, không có queue-level filter/TTL quá ngắn làm mất message.
- Chạy trên môi trường **test cách ly**, tuyệt đối không dùng queue đang mang dữ liệu nghiệp vụ.

**Lưu ý bảo mật:** không sử dụng tài khoản production trong YAML; đặt `SPRING_ARTEMIS_USER`, `SPRING_ARTEMIS_PASSWORD` bằng environment/secret manager khi chạy ngoài môi trường mẫu.

### 8.2. Cấu trúc thư mục

~~~text
jms-selector-cases/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/SelectorCasesApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-selector-cases'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
  jms:
    cache:
      enabled: false
~~~

`mode: native` bảo đảm Spring Boot dùng broker bên ngoài tiến trình, không âm thầm chuyển sang broker embedded khi bạn muốn kiểm tra queue thật. Tắt cache trong **demo nhỏ** để dễ quan sát phép thử; không coi đây là khuyến nghị cấu hình cho ứng dụng xử lý tải lớn.

### 8.3. Java đầy đủ

`src/main/java/demo/SelectorCasesApplication.java`:

~~~java
package demo;

import java.util.UUID;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.Message;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorCasesApplication {

    private static final String QUEUE = "demo.selector.tests";
    private static final long TIMEOUT_MS = 750L;

    public static void main(String[] args) {
        SpringApplication.run(SelectorCasesApplication.class, args);
    }

    @Bean
    ApplicationRunner checkCases(JmsTemplate template) {
        return args -> {
            // UUID chỉ gồm các ký tự an toàn khi chèn vào String literal.
            String runId = UUID.randomUUID().toString();
            String base = "runId = '" + runId + "'";

            // Cấu hình một lần trước khi test, không thay đổi concurrent.
            template.setReceiveTimeout(TIMEOUT_MS);

            // Cùng body kiểu TextMessage; property score khác nhau.
            sendText(template, runId, "HIGH", 9, null);
            sendText(template, runId, "LOW", 3, null);
            sendText(template, runId, "WRONG_TYPE", null, "9");
            sendText(template, runId, "MISSING", null, null);

            System.out.println("SENT_TEXT_CASES=4");

            String numeric = base + " AND score >= 8";

            // Positive test: int 9 thỏa điều kiện số.
            Message high = expectCase(
                    template.receiveSelected(QUEUE, numeric), "HIGH");
            if (!(high.getObjectProperty("score") instanceof Integer)) {
                throw new IllegalStateException("HIGH score is not int");
            }
            System.out.println("NUMERIC_MATCH=HIGH");

            // Negative test: LOW, WRONG_TYPE, MISSING phải không khớp.
            Message unexpected = template.receiveSelected(QUEUE, numeric);
            if (unexpected != null) {
                throw new IllegalStateException(
                        "Unexpected numeric match: "
                        + unexpected.getStringProperty("caseId"));
            }
            System.out.println("NO_OTHER_NUMERIC_MATCH=true");

            // String "9" khớp String literal, không khớp numeric >= 8.
            Message wrongType = expectCase(
                    template.receiveSelected(
                            QUEUE, base + " AND score = '9'"),
                    "WRONG_TYPE");
            if (!(wrongType.getObjectProperty("score") instanceof String)) {
                throw new IllegalStateException("Expected String score");
            }
            System.out.println("STRING_TYPED_MATCH=WRONG_TYPE");

            // Score 3 không đạt ngưỡng 8, nhưng vẫn nằm ở queue.
            Message low = expectCase(
                    template.receiveSelected(
                            QUEUE, base + " AND score < 8"),
                    "LOW");
            if (!(low.getObjectProperty("score") instanceof Integer)) {
                throw new IllegalStateException("LOW score is not int");
            }
            System.out.println("LOW_SCORE_RECOVERED=LOW");

            // Property thiếu cần kiểm tra với IS NULL.
            Message missing = expectCase(
                    template.receiveSelected(
                            QUEUE, base + " AND score IS NULL"),
                    "MISSING");
            if (missing.propertyExists("score")) {
                throw new IllegalStateException(
                        "MISSING unexpectedly has score");
            }
            System.out.println("MISSING_SCORE_RECOVERED=MISSING");

            // Case thứ năm: body là BytesMessage, score vẫn là số.
            template.send(QUEUE, session -> {
                BytesMessage bytes = session.createBytesMessage();
                bytes.writeBytes(new byte[] {1, 2});
                bytes.setStringProperty("runId", runId);
                bytes.setStringProperty(
                        "caseId", "WRONG_BODY_TYPE");
                bytes.setIntProperty("score", 10);
                return bytes;
            });

            Message bodyCase = expectCase(
                    template.receiveSelected(QUEUE, numeric),
                    "WRONG_BODY_TYPE");
            if (!(bodyCase instanceof BytesMessage)) {
                throw new IllegalStateException(
                        "Expected BytesMessage body");
            }
            System.out.println("BYTE_BODY_SELECTED=true");

            System.out.println("ALL_ASSERTIONS_PASSED");
        };
    }

    private static void sendText(
            JmsTemplate template,
            String runId,
            String caseId,
            Integer numericScore,
            String textScore) {

        template.convertAndSend(
                QUEUE, "case:" + caseId, message -> {
                    message.setStringProperty("runId", runId);
                    message.setStringProperty("caseId", caseId);

                    if (numericScore != null) {
                        message.setIntProperty(
                                "score", numericScore);
                    }
                    if (textScore != null) {
                        message.setStringProperty(
                                "score", textScore);
                    }
                    return message;
                });
    }

    private static Message expectCase(
            Message message, String expectedCase)
            throws JMSException {

        if (message == null) {
            throw new IllegalStateException(
                    "Timed out waiting for " + expectedCase);
        }
        String actual = message.getStringProperty("caseId");
        if (!expectedCase.equals(actual)) {
            throw new IllegalStateException(
                    "Expected " + expectedCase + ", got " + actual);
        }
        return message;
    }
}
~~~

### 8.4. Giải thích các quyết định trong code

1. `JmsTemplate` là bean Spring Boot tạo từ `ConnectionFactory` Artemis; code dùng `convertAndSend(..., MessagePostProcessor)` để đặt JMS properties **trước khi gửi**.
2. `String` body được `SimpleMessageConverter` mặc định chuyển thành `TextMessage`. Do đó HIGH/LOW/WRONG_TYPE/MISSING chỉ khác về **metadata**, không khác kiểu body.
3. `sendText` dùng `Integer numericScore` và `String textScore` riêng, tuyệt đối không gọi `setIntProperty` và `setStringProperty` cho cùng message trong cùng case.
4. Mỗi message có `runId` và `caseId`. `runId` được thêm vào **mọi selector**; `caseId` giúp assertion báo đúng message.
5. `numeric` là biểu thức `score >= 8`. Do score kiểu `int`, message HIGH khớp; LOW không đủ giá trị, WRONG_TYPE có String nên không cùng kiểu, MISSING dẫn tới UNKNOWN.
6. Lần nhận thứ hai với `numeric` trả `null` sau timeout khi chỉ còn LOW/WRONG_TYPE/MISSING. **Đây không phải mất message**: test tiếp theo cố tình nhận lại ba message bằng điều kiện tương ứng.
7. `score = '9'` chọn WRONG_TYPE; `score < 8` chọn LOW; `score IS NULL` chọn MISSING. Những case này chứng minh message ban đầu không khớp vẫn có thể được tiêu thụ bằng consumer khác.
8. `BytesMessage` với score int `10` được gửi **sau** khi bốn case trên đã kiểm tra xong. Selector số khớp dù body khác, vì selector không đọc body.
9. `expectCase` báo lỗi nếu timeout hoặc `caseId` khác mong đợi. PASS cuối cùng chỉ được in nếu mọi message thực sự đúng, không phải chỉ nhận được bất kỳ message nào.
10. `setReceiveTimeout(750L)` giới hạn thời gian nhận cho từng lời gọi. Lời gọi trễ/broker lỗi vẫn có thể khiến tổng thời gian lâu hơn; timeout của receive **không** bao trùm tạo connection, DNS/TLS hoặc broker recovery.
11. Test dùng queue riêng không có consumer cạnh tranh. Trong hệ thống thật, một consumer khác có thể nhận/ack message trước test, làm kết quả không còn đáng tin.
12. Vì không dùng JMS transaction bao toàn bộ test, test chủ động nhận và xác nhận các message. Nếu assertion ném exception giữa chừng, một số message còn lại có thể lưu trong queue thử; sử dụng `runId` mới để test không nhầm. Dọn dữ liệu bằng công cụ quản trị trên **queue test** theo chính sách được cho phép.

### 8.5. Chạy chương trình

Tại thư mục project:

~~~bash
gradle bootRun
~~~

Khi broker sẵn sàng, queue/ACL đúng và không có consumer khác tranh chấp, các dòng do **ứng dụng** in ra lần lượt là:

~~~text
SENT_TEXT_CASES=4
NUMERIC_MATCH=HIGH
NO_OTHER_NUMERIC_MATCH=true
STRING_TYPED_MATCH=WRONG_TYPE
LOW_SCORE_RECOVERED=LOW
MISSING_SCORE_RECOVERED=MISSING
BYTE_BODY_SELECTED=true
ALL_ASSERTIONS_PASSED
~~~

Spring Boot/Artemis có thể in thêm log. UUID thay đổi mỗi lần chạy nhưng không được in, nên output trên ổn định. **Không kết luận pass nếu dòng cuối không xuất hiện**. Nếu broker không chạy, không đủ quyền, queue không được định tuyến hoặc message bị consumer khác lấy, chương trình có thể ném exception và không có output PASS.

**Vì sao không có riêng `WRONG_EVENT` trong code?** Bảng ở mục 3 giải thích case đó nhưng chương trình ưu tiên cô lập hai trục cần kiểm tra: **so sánh đúng/sai về giá trị** và **sai kiểu**. Có thể mở rộng test với `eventType` bằng cách thêm String property và thêm vế `AND` vào selector, giữ nguyên cách kiểm tra `runId`.

### 8.6. Mở rộng: thêm case so khớp event type

Để phát hiện nhầm tên property, bổ sung một message với:

~~~java
// Snippet: trong MessagePostProcessor của producer.
message.setStringProperty("eventType", "order.created");
message.setIntProperty("score", 9);
~~~

Consumer dùng:

~~~sql
eventType = 'order.created' AND score >= 8
~~~

Nếu đổi producer thành `setStringProperty("EventType", ...)` mà vẫn giữ selector `eventType`, property cần đọc không tồn tại, biểu thức trở thành UNKNOWN. Đây là cách tạo test negative cho **case sensitivity**. Không được xem việc Java DTO có field `eventType` là bằng chứng JMS property `eventType` đã có trên wire.

## 9. Sai kiểu của property ≠ sai kiểu của JMS body

Có hai lỗi “type mismatch” khác bản chất:

| Trục | Ví dụ | Selector tác động thế nào? | Lỗi xuất hiện ở đâu? |
| --- | --- | --- | --- |
| Property metadata | `score` String `"9"` nhưng selector numeric `score >= 8` | Không khớp | Trong quá trình provider đánh giá selector |
| JMS body | `BytesMessage` có `score` int `10` nhưng consumer mong `TextMessage` | **Vẫn khớp** nếu metadata đúng | Khi consumer cast/convert/deserializes |
| DTO schema | `TextMessage` JSON thiếu field bắt buộc của DTO | Selector có thể vẫn khớp | Khi JSON converter/validation chạy |
| Custom property type | `urgent` String `"true"` nhưng selector `urgent = TRUE` | Không khớp do String vs Boolean | Broker/provider selector |
| JMS header policy | Selector dựa `JMSPriority >= 7`, producer chỉ gọi `message.setJMSPriority(7)` | Priority thực có thể bị provider ghi đè lúc send | Quyết định QoS tại producer/provider |

### 9.1. Ví dụ TextMessage vs BytesMessage

~~~java
// Snippet: receiver nhận raw JMS message từ một consumer/filter.
if (received instanceof jakarta.jms.TextMessage text) {
    String body = text.getText();
    // parse JSON hoặc xử lý String
} else if (received instanceof jakarta.jms.BytesMessage bytes) {
    // xử lý bytes theo contract cụ thể
} else {
    throw new IllegalArgumentException(
            "Unsupported JMS body type");
}
~~~

Đây là snippet, cần biến `received` do consumer trả về. Không cast mù:

~~~java
String body = ((jakarta.jms.TextMessage) received).getText();
~~~

Nếu message thực là `BytesMessage`, đoạn cast sẽ ném `ClassCastException`, mặc dù selector đã khớp hoàn toàn.

Với `JmsTemplate.receiveSelectedAndConvert`, `SimpleMessageConverter` có thể trả `String` cho `TextMessage` và `byte[]` cho `BytesMessage`. Do đó một phép cast kết quả sang `String` cũng có thể lỗi với payload bytes. Custom Jackson/JSON converter còn có thể ném `MessageConversionException` khi content type, class/schema hoặc JSON không phù hợp. Đây là lỗi **tầng decode**, không phải selector.

### 9.2. Khi sai kiểu property có thể là bug nghiêm trọng?

Giả sử producer A gửi:

~~~java
message.setIntProperty("retryCount", 3);
~~~

Nhưng một producer B đọc dữ liệu từ HTTP form rồi gửi:

~~~java
message.setStringProperty("retryCount", "3");
~~~

Nếu listener yêu cầu `retryCount < 5`, toàn bộ message từ B có thể **không được consumer đó nhận** mặc dù người vận hành nhìn dashboard thấy “retryCount 3”. Kết quả là queue backlog tăng hoặc message chờ cho đến khi TTL hết hạn.

Để ngăn:
- Công bố schema **cho JMS properties**, không chỉ JSON body.
- Dùng một lớp producer helper cho các property chung, có test `getObjectProperty` trả về đúng wrapper type.
- Quan sát số message pending theo selector/destination và queue age.
- Xác định cách xử lý dữ liệu không đúng contract, ví dụ một consumer kiểm tra message không chuẩn trên queue riêng hoặc một cơ chế quarantine/browse có kiểm soát. **Không** để consumer fallback không selector trên queue production rồi tự nhận mọi message nếu chưa có kiến trúc xử lý an toàn.

## 10. Đừng bỏ qua các trường hợp biên quan trọng

### 10.1. Boolean vs String

~~~java
message.setBooleanProperty("urgent", true);
~~~

Selector đúng:

~~~sql
urgent = TRUE
~~~

Selector `urgent = 'true'` có literal String; không tương đương Boolean TRUE. Kiểm thử cần cả `true`, `false`, String `"true"` và property thiếu. Không nên parse String ở selector để hợp thức hóa producer gửi sai kiểu.

### 10.2. Numeric promotion

So sánh giữa các loại số JMS (ví dụ int và long/double literal) có các quy tắc numeric promotion được đặc tả hỗ trợ. Tuy vậy, việc String `"9"` thành số **không** thuộc nhóm này. Kiểm thử nên bao gồm `int`, `long`, giá trị âm, số lớn và boundary (ví dụ `score = 8` đúng với `>=8`; `7` không khớp) nếu nghiệp vụ cần.

### 10.3. NULL và logic phủ định

Đừng viết:

~~~sql
NOT (score >= 8)
~~~

với kỳ vọng “lấy tất cả message không đạt, bao gồm missing”. Message thiếu `score` vẫn UNKNOWN sau `NOT`. Nếu nghiệp vụ muốn nhận cả low score và missing, dùng:

~~~sql
score < 8 OR score IS NULL
~~~

Selector này vẫn **không** tự xử lý message có score String `"9"`. Nếu muốn tách dữ liệu sai kiểu, nên thiết kế một pipeline kiểm định/quan sát riêng, không cố đoán kiểu bằng một biểu thức không portable.

### 10.4. LIKE không phải phép toán số

`eventType LIKE 'order.%'` là hợp lệ khi `eventType` là String. Không nên dùng `score LIKE '9%'` để lọc score int `9`. Đó là dữ liệu sai kiểu/điều kiện sai tầng.

### 10.5. Case sensitivity

Property names và String values là case-sensitive: `eventType = 'Invoice'` khác `eventType = 'invoice'`. SQL keywords thì không phân biệt case. Test nên có message cùng giá trị nhưng khác casing nếu hệ thống có nhiều producer/SDK.

### 10.6. Invalid syntax có thể bị phát hiện trước lúc có message

JMS provider **phải** kiểm tra selector syntax khi tạo consumer. `score >=` không hợp lệ ngay cả khi queue rỗng; provider có thể ném `InvalidSelectorException` ở bước tạo consumer. Điều này khác với `score >= 8` khi score là String: syntax hoàn toàn hợp lệ và provider có thể chỉ đánh giá FALSE khi gặp message.

Spring `JmsTemplate` thường chuyển JMS checked exception sang Spring `JmsException` runtime. Khi viết test lỗi cú pháp, kiểm tra loại nguyên nhân và broker/provider logs, không kết luận từ `receiveSelected(...) == null`.

## 11. Thêm test cho `@JmsListener(selector=...)`

Trong ứng dụng production, JMS thường nhận bất đồng bộ qua `@JmsListener`, nhưng **nguyên tắc selector giống hệt**: chỉ message có biểu thức TRUE được giao vào listener.

~~~java
// Snippet nằm trong @Component của ứng dụng Spring có bật JMS listener.
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'order.created' AND score >= 8")
public void onHighScore(String body) {
    System.out.println("HIGH_SCORE=" + body);
}
~~~

Cần import `org.springframework.jms.annotation.JmsListener`, cấu hình listener container và `ConnectionFactory`. Đây là snippet, **không** chèn vào project chạy ở mục 8 trên cùng queue, vì listener này có thể cạnh tranh nhận message và làm sai test đồng bộ.

Một lỗi phổ biến là unit test gọi trực tiếp `onHighScore("...")` rồi khẳng định selector hoạt động. Việc gọi method Java trực tiếp **không đi qua JMS provider**, nên không kiểm tra selector. Để test thực:
1. Start listener container trên broker test.
2. Gửi message có properties và types xác định.
3. Dùng `CountDownLatch` hoặc trạng thái được ghi nhận để đợi callback với timeout hữu hạn.
4. Assert chỉ các message khớp được xử lý; message không khớp cần kiểm chứng còn trên queue hoặc bởi consumer chuyên dụng.
5. Không dùng `Thread.sleep` cố định để làm bằng chứng duy nhất trong test concurrency.

### 11.1. Những kiểm thử nên tách khỏi unit test thuần

**Unit test producer** có thể dùng mocks để xác nhận lời gọi `setIntProperty` thay vì `setStringProperty`. Nhưng nó **không chứng minh** syntax/semantics của broker selector. **Integration test** với một JMS provider thật (ví dụ Artemis cô lập) mới chứng minh message được broker chọn đúng theo hợp đồng.

Nếu có nhiều phiên bản provider, test cross-provider theo JMS spec, nhất là các khác biệt về filter extension. Đừng chỉ chạy một unit test mô phỏng SQL bằng Java rồi kết luận Artemis hoặc broker khác chắc chắn xử lý y hệt.

## 12. Kiểm thử Spring JMS bằng bảng test cases

| ID | Dữ liệu đầu vào | Selector | Kỳ vọng | Bằng chứng tốt |
| --- | --- | --- | --- | --- |
| T01 | `score` int 9 | `score >= 8` | Match | `receiveSelected` trả đúng `caseId` |
| T02 | `score` int 8 | `score >= 8` | Match biên | Nhận được message boundary |
| T03 | `score` int 7 | `score >= 8` | Không match | Timeout, rồi receive lại bằng `score < 8` |
| T04 | `score` String "9" | `score >= 8` | Không match | Timeout, rồi nhận bằng `score = '9'` |
| T05 | Không có `score` | `score >= 8` | Không match (UNKNOWN) | Nhận lại bằng `score IS NULL` |
| T06 | Không có `score` | `NOT (score >= 8)` | Không match (UNKNOWN) | Không nhận; `IS NULL` nhận được |
| T07 | `eventType` String "order.created" | `eventType = 'order.created'` | Match | Nhận đúng ID |
| T08 | `EventType`, thiếu `eventType` | `eventType = 'order.created'` | Không match | `eventType IS NULL` đúng |
| T09 | `urgent` Boolean true | `urgent = TRUE` | Match | Nhận được message |
| T10 | `urgent` String "true" | `urgent = TRUE` | Không match | String selector `urgent = 'true'` match |
| T11 | `BytesMessage`, score int 10 | `score >= 8` | Match dù body bytes | Raw message là `BytesMessage` |
| T12 | Bất kỳ message | `score >=` | Syntax error | `InvalidSelectorException`/Spring wrapper |
| T13 | `score` int 9 | `score = '9'` | Không match | String literal khác số |
| T14 | `score` int 9, eventType không khớp | `score >= 8 AND eventType = 'other'` | Không match | Điều kiện AND sai |
| T15 | `score` int 9, runId khác | `runId = 'a' AND score >= 8` | Không match | Không lẫn dữ liệu từ run khác |

Không nhất thiết đưa 15 cases vào một queue cùng lúc. Hãy nhóm theo rủi ro, tạo ID riêng, gửi đúng message cần thử và **dọn có kiểm soát** sau mỗi nhóm. Với các ca negative, phải **chứng minh message vẫn còn** khi mục đích test là filter, thay vì suy rằng message đã mất sau timeout.

## 13. Chẩn đoán khi message không được nhận

### 13.1. Thứ tự điều tra nên làm

1. **Kết nối và quyền:** broker URL, credentials, port/TLS và quyền `send`/`consume`. Một lỗi authorization không phải lỗi selector.
2. **Destination thực:** producer và consumer dùng cùng queue/address/routing type không? Có queue filter hoặc divert không?
3. **Message có được gửi:** producer nhận lỗi hay có transaction chưa commit? Có message pending trên queue test không?
4. **Property tồn tại không:** in tên property và kiểu qua `getObjectProperty` trong môi trường test; tránh in payload nhạy cảm.
5. **Selector đúng không:** cú pháp, dấu nháy, tên property case-sensitive, String vs number, logic NULL.
6. **Consumer đã start chưa:** với classic JMS `Connection.start()` cần được gọi để giao message; Spring template/container thường quản lý phần này.
7. **Queue có competing consumers không:** message có thể được listener khác tiêu thụ và ACK trước khi test nhận.
8. **TTL/expiry/DLQ:** message có bị hết hạn hoặc policy chuyển đi không?
9. **Timeout:** thời gian chờ có đủ không; provider đang chậm hay thực sự không match?
10. **Body conversion:** raw message được nhận nhưng chuyển DTO lỗi thì vấn đề nằm ở converter/schema, không phải selector.

### 13.2. Quan sát queue mà không tiêu thụ nhầm

Khi cần xem metadata:
- Dùng **broker management/queue browse** phù hợp, chỉ với quyền được cấp.
- Nếu viết tool JMS QueueBrowser, hiểu rằng browse không nhất thiết cho snapshot nguyên tử dưới concurrent modifications.
- Không tạo một consumer “không selector” trên queue production chỉ để “in message” rồi vô tình ACK dữ liệu thật.
- Đừng xóa queue, purge hoặc tự thay expiry policy chỉ để test PASS.

**An toàn với dữ liệu nhạy cảm:** properties có thể chứa tenant ID, trace ID và định danh nghiệp vụ. Chỉ log những trường phục vụ debug, bỏ thông tin cá nhân/mật khẩu/token khỏi logs.

## 14. Test độc lập kiểu producer–consumer và schema contract

Một hệ thống có hai producers:
- Producer Java dùng `message.setIntProperty("schemaVersion", 2)`.
- Producer STOMP hoặc gateway khác có thể gửi property `schemaVersion` dưới dạng String `"2"`.

Consumer JMS dùng `schemaVersion >= 2`. Kết quả có thể khác dù dashboard hiển thị “2”. Vì vậy, hợp đồng API nên chỉ rõ:

~~~text
Property contract:
  eventType      : String, required
  schemaVersion  : int, required
  tenantId       : String, required
  attempt        : int, optional
  urgent         : boolean, optional

Body contract:
  Content type   : JSON UTF-8 trong TextMessage
  Schema version : phù hợp với schemaVersion property
  Event ID       : String ổn định để deduplication
~~~

Ở đây `schemaVersion` phải có kiểu JMS primitive int thực sự, không chỉ chuỗi JSON text. Mỗi producer nên có contract test để chứng minh **đúng kiểu property**, consumer có integration tests với broker để chứng minh selector lựa chọn đúng.

Nếu hệ thống **cố ý** chỉ dùng String properties do transport limitation, hãy thiết kế selectors theo String/equality hoặc đổi schema/transport. Apache Artemis Core có extension `convert_string_expressions:` cho một số filter expressions; đó **không phải cú pháp JMS selector portable**. Không dựa vào extension này trong code ứng dụng cần chạy trên nhiều JMS provider mà không có test tương thích.

### 14.1. Queue filter và consumer selector khác chỗ nào?

Artemis hỗ trợ **queue filter** trong cấu hình broker và **consumer filter/selector** trong client:
- Queue filter quyết định **message nào được route vào queue**.
- Consumer selector quyết định **message nào trong queue được giao tới consumer**.
- Queue filter không khớp có thể khiến message không tồn tại trong queue đó; consumer selector không khớp thường để message chờ consumer khác, nếu không có policy khác can thiệp.

Nếu bài test kết luận “message không match vẫn ở queue”, cần bảo đảm test sử dụng **consumer selector**, không nhầm với queue-level filter.

## 15. Thiết kế cleanup và độ tin cậy của phép thử

Một test đáng tin không phá hủy dữ liệu và không phụ thuộc vào tình cờ:
- Sử dụng dedicated queue, ví dụ `demo.selector.tests`, và `runId` UUID mới.
- Dùng timeout hữu hạn; không để receive chặn vô hạn.
- Gửi các case trong một bước có kiểm soát rồi chỉ bắt đầu assert khi gửi đã trả về thành công.
- **Không phụ thuộc thứ tự message** nếu nhiều message có thể cùng match; tốt nhất thiết kế mỗi selector mong đợi một case duy nhất.
- Với negative test, sau `null` cần kiểm tra message chưa khớp còn khả dụng qua selector khác.
- Không dùng message từ production hoặc queue có consumers khác.
- Tránh tự động purge trong `finally` nếu không thể chứng minh đúng ownership; cleanup bằng công cụ test/broker có giới hạn run ID và quyền riêng.
- Một integration test có thể fail sau vài receive khiến message khác còn pending. Lần chạy mới dùng runId khác và không được coi message cũ là pass.
- Cấu hình TTL/retention để message lỗi test không tồn tại mãi; khi TTL quá ngắn, test sẽ bị mất dữ liệu trước lúc kiểm tra, gây false failure.
- Test không chứng minh persistent delivery qua restart, transaction giữa DB và broker hay exactly-once side effect. Đây là những bài kiểm thử khác.

## 16. Checklist trước khi chấp nhận selector production

- [ ] Tên property và kiểu JMS của từng trường được mô tả trong **contract**.
- [ ] Producer sử dụng đúng `setIntProperty`/`setStringProperty`/`setBooleanProperty`.
- [ ] Consumer chỉ lọc theo **headers/properties**, không tưởng rằng body JSON được phân tích tự động.
- [ ] Có test positive, negative theo giá trị, wrong type và missing/NULL.
- [ ] Có test syntax invalid để phân biệt lỗi tạo consumer với non-match.
- [ ] Có test case sensitivity và boundary value nếu quan trọng.
- [ ] Cần nhận message thiếu field thì dùng `IS NULL`; không dựa vào `NOT(expression)`.
- [ ] Có integration test với broker thực, kiểm tra message không match **còn lại** trên queue đúng.
- [ ] Không có queue filter/consumer khác/TTL làm nhiễu kết quả.
- [ ] Kiểm tra receiver nhận raw `TextMessage`/`BytesMessage` phù hợp với converter.
- [ ] Biểu thức selector có giá trị dynamic đã validate/escape, không nhận chuỗi raw không tin cậy.
- [ ] Có metric queue depth, message age, conversion errors và DLQ để phát hiện message “không có consumer nào nhận”.
- [ ] Test trên queue riêng, không purge message thật, và có kế hoạch dọn dữ liệu test.

### Câu hỏi tự kiểm tra

1. Vì sao `setStringProperty("score", "9")` không thỏa `score >= 8`, trong khi `getIntProperty("score")` đôi khi vẫn trả về 9?
2. `score >= 8` là FALSE hay UNKNOWN khi message không có property `score`?
3. Vì sao `NOT (score >= 8)` không nhận message thiếu `score`? Viết selector đúng để nhận chúng.
4. Một message `BytesMessage` có `score=10` có bị loại khi selector `score >= 8` không? Khi nào consumer mới phát hiện sai body type?
5. JMS selector có trực tiếp đọc field `amount` bên trong JSON body được không?
6. Nếu consumer có selector không khớp, có thể tuyên bố message đã bị xóa khỏi queue không?
7. `eventType` và `EventType` có được coi là cùng JMS property name không?
8. `score >=` gây loại lỗi nào, và lỗi đó thường xuất hiện ở bước nào?
9. Tại sao cần `runId` trong integration test được chạy nhiều lần trên cùng queue?
10. Điểm khác biệt giữa Artemis queue filter và JMS consumer selector là gì?

**Ghi nhớ:** Kiểm thử selector phải bao gồm **giá trị + kiểu + thiếu property + kiểu body + phạm vi queue/consumer**. Một selector chỉ match khi biểu thức đạt **TRUE**. `score` kiểu String không tự chuyển thành int; giá trị không tồn tại là NULL/UNKNOWN; message không được chọn bởi consumer selector thường **vẫn ở queue**, không bị xóa. Đưa các trường cần lọc thành JMS properties có kiểu đúng và luôn kiểm tra bằng integration test trên broker thật.

## Tài liệu tham khảo

1. Jakarta Messaging 3.1 Specification, `3.5 Message properties` và `3.8 Message selection`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
2. Jakarta Messaging 3.1 API — `Message` (property types, getters/setters, selector): https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
3. Spring Framework 6.1 — `JmsTemplate` (receiveSelected, receiveAndConvert, receiveTimeout): https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
4. Spring Framework — Receiving a Message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
5. Apache ActiveMQ Artemis — Filter Expressions (consumer vs queue filtering, JMS and Core differences): https://artemis.apache.org/components/artemis/documentation/latest/filter-expressions.html
6. Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
7. Spring Integration — Using JMS Message Selectors: https://docs.spring.io/spring-integration/reference/jms.html
