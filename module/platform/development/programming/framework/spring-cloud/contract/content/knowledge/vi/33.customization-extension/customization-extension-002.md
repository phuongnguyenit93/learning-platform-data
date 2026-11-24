# Custom assertion và helper trong base test

## Mục tiêu bài học

**Spring Cloud Contract** cho phép mô tả hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh kiểm thử phía producer và phát hành stub cho consumer sử dụng qua **Stub Runner**. Phần lớn điều kiện nên được diễn đạt bằng matcher khai báo: status, headers, JSONPath, giá trị cụ thể, kiểu dữ liệu hoặc regular expression. Khi xuất hiện một bất biến nghiệp vụ phức tạp hơn, nhóm có thể bổ sung **custom assertion** và phương thức hỗ trợ trong **base test class**.

Bài **“Custom assertion và helper trong base test”** thuộc chương **Tùy biến và mở rộng**. Trọng tâm không phải viết thật nhiều code tùy chỉnh, mà là biết **khi nào cần mở rộng**, method được generator gọi ra sao, cách đảm bảo helper **kiểm tra giá trị thật** và làm sao chứng minh nó không tạo false PASS.

Sau bài học, bạn có thể:

- Phân biệt contract DSL, generated test, base test, helper assertion và stub artifact.
- Chọn matcher khai báo hoặc custom assertion theo yêu cầu thực tế.
- Hiểu vai trò của **`byCommand(...)`** trong Groovy response body matcher theo phiên bản hỗ trợ.
- Xây helper Java có kiểm tra kiểu, null, boundary và failure message rõ ràng.
- Cấu hình producer base test với MockMvc và kết nối với generated tests.
- Tách helper kiểm tra kết quả khỏi helper tạo fixture hoặc kích hoạt message.
- Đọc generated source, kiểm tra method signature và viết unit tests cho helper.
- Rà soát side effects, bảo mật và CI evidence trước khi công bố tương thích producer–consumer.

## 1. Custom assertion giải quyết vấn đề nào?

Giả sử Order Service có response:

~~~json
{
  "orderId": "ORD-12045",
  "status": "PAID",
  "amount": 125000,
  "currency": "VND"
}
~~~

Các yêu cầu đơn giản như `status = PAID` hoặc `currency = VND` có thể kiểm tra trực tiếp trong DSL. Nhưng nếu `orderId` phải có một định dạng riêng và một checksum nghiệp vụ, hoặc `amount` phải có các ràng buộc về đơn vị, độ chính xác hay giới hạn, matcher cơ bản có thể chưa diễn đạt đủ rõ.

Đó là lúc **custom assertion** hữu ích: generated producer test có thể nhận giá trị thực, rồi gọi một phương thức Java để xác minh bất biến. Tuy nhiên, helper mang thêm code và dependencies; nó không phải cách mặc định cho mọi field.

**Nguyên tắc chọn lựa:** dùng matcher DSL khi có thể mô tả trực tiếp, dùng custom assertion khi bất biến khó diễn đạt rõ và có giá trị bảo vệ một cam kết quan sát được của API.

| Điều kiện | Công cụ thường phù hợp |
| --- | --- |
| HTTP status là 200 | `response.status` |
| Header `Content-Type` là JSON | `response.headers` |
| Trường `status` bằng `PAID` | Body literal/JSONPath equality |
| `orderId` khớp regex được công bố | Matcher regex |
| `orderId` cần thuật toán kiểm tra chuyên biệt | Custom assertion |
| `amount` phải là số dương và đúng precision | Matcher chuyên biệt hoặc helper |
| `total = subtotal + tax` | Test bổ sung trên toàn response hoặc cơ chế multi-value được kiểm chứng |
| Request thực sự ghi một record | Integration assertion với database test |
| Message được phát đúng destination | Message contract và producer message test |

Không nên dùng helper để che một hợp đồng chưa định nghĩa rõ. Nếu consumer phụ thuộc `status = PAID`, đừng thay assertion đó bằng lời gọi mơ hồ như `checkResponse(response)` mà reviewer không hiểu đang kiểm gì.

## 2. Đường chạy từ contract đến assertion

~~~mermaid
flowchart TD
    C["Contract Groovy/YAML"] --> G["Contract Verifier sinh test"]
    G --> T["Generated producer test"]
    B["Base test class"] --> T
    H["Custom assertion helper"] --> B
    T --> P["Producer implementation"]
    P --> R["Response / message thật"]
    R --> T
    T --> A{"Matcher / helper đạt?"}
    A -->|Có| OK["Producer test PASS"]
    A -->|Không| FAIL["Producer test FAIL"]
    C --> S["Sinh stub artifact"]
    S --> ST["Stub Runner"]
    ST --> CT["Consumer tests"]
~~~

Hai nhánh phải được phân biệt:

- **Producer verification:** generated test kiểm tra implementation producer có đáp ứng contract hay không. Đây là nơi base test và custom assertion có thể được gọi.
- **Consumer stub tests:** Stub Runner trả response mẫu/mapping để consumer chạy thử. Custom helper Java trong producer base test **không tự động được chuyển thành code kiểm tra của consumer**.

Một HTTP stub có thể trả `ORD-12045`, còn generated test chấp nhận mọi ID thỏa pattern hoặc checksum. Consumer test vẫn phải có assertions riêng nếu muốn kiểm tra consumer thực sự xử lý ID đó đúng.

## 3. Base test class là gì?

Base test class thường là class mà **generated producer tests kế thừa** hoặc được cấu hình làm cơ sở trong cơ chế sinh test của phiên bản Spring Cloud Contract đang dùng.

Nó có thể cung cấp:

- Cấu hình Spring test context, MockMvc/HTTP client.
- Fixture cho database hoặc dependency giả.
- Phương thức kích hoạt producer message.
- Các helper hỗ trợ kiểm tra response và headers.
- Setup/teardown dành cho từng test, mỗi suite hoặc một môi trường dùng chung.

Ví dụ project:

~~~text
order-service/
├── pom.xml
├── src/test/resources/contracts/orders/get_paid_order.groovy
├── src/test/java/com/example/orders/contract/
│   ├── OrderContractBase.java
│   ├── OrderContractAssertions.java
│   └── OrderContractAssertionsTest.java
└── target/
    ├── generated-test-sources/...
    └── ...
~~~

Thư mục dưới `target` chỉ minh họa; tên chính xác thay đổi theo plugin/version/configuration.

Một class `OrderContractBase` nằm trong test sources **không tự được dùng**. Build plugin phải biết class đó qua `baseClassForTests` hoặc cơ chế mapping base class tương ứng.

## 4. Cấu hình base class cho Maven

Một đoạn POM minh họa:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>${spring-cloud-contract.version}</version>
      <extensions>true</extensions>
      <configuration>
        <baseClassForTests>
          com.example.orders.contract.OrderContractBase
        </baseClassForTests>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`spring-cloud-contract.version` là property cần được quản lý bằng version tương thích với Spring Boot/Spring Cloud của dự án; đoạn này chưa phải POM hoàn chỉnh.

Với nhiều nhóm hợp đồng, một số phiên bản hỗ trợ cấu hình **base class mappings** thay vì một base class duy nhất. Cách đặt mapping, regex/package và thứ tự lựa chọn phụ thuộc plugin version. **Đừng đoán generated class sẽ extends base nào; hãy đọc source được sinh.**

Với Gradle, ý tưởng tương tự là chỉ ra contract DSL root và base class trong cấu hình plugin dành cho version hiện hành. Không copy tên Maven properties sang Gradle nếu chưa kiểm tra DSL của plugin.

## 5. HTTP base test với Spring MVC và RestAssuredMockMvc

Ví dụ khung cho producer sử dụng **Spring MVC**, **JUnit 5** và **MockMvc**:

~~~java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
public abstract class OrderContractBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void setUpHttp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }

    public void assertValidOrderId(Object actual) {
        OrderContractAssertions.requireValidOrderId(actual);
    }

    public void assertPositiveAmount(Object actual) {
        OrderContractAssertions.requirePositiveAmount(actual);
    }
}
~~~

Giả định: generated tests được cấu hình để dùng RestAssuredMockMvc, và project có đủ test dependencies. Đây không phải base class chung cho mọi producer. Với WebFlux, WebTestClient, RestAssured trên server thật hoặc messaging, cách setup khác.

Trong ví dụ này:

- `@SpringBootTest` cung cấp Spring context test.
- `@AutoConfigureMockMvc` cấu hình MockMvc.
- `@BeforeEach` kết nối RestAssuredMockMvc với MockMvc.
- Hai method `public` là điểm gọi helper mà generated subclass có thể truy cập.
- Helper riêng chứa quy tắc nghiệp vụ, để base test không phải chứa quá nhiều assertions.

**Không mock toàn bộ controller để nó trả chính body mẫu trong contract**. Làm vậy có thể khiến generated test PASS trong khi implementation producer thật trả cấu trúc khác. Chỉ fake những external dependencies cần cô lập và giữ đường logic quan trọng được kiểm tra.

## 6. Helper Java thuần và thông điệp thất bại rõ ràng

Một helper độc lập:

~~~java
package com.example.orders.contract;

import java.math.BigDecimal;
import java.util.regex.Pattern;

public final class OrderContractAssertions {

    private static final Pattern ID_PATTERN =
        Pattern.compile("^ORD-[0-9]{4,}$");

    private OrderContractAssertions() {}

    public static void requireValidOrderId(Object actual) {
        if (!(actual instanceof String)) {
            throw new AssertionError(
                "orderId phải là JSON string, nhận kiểu " +
                typeName(actual)
            );
        }

        String id = (String) actual;
        if (!ID_PATTERN.matcher(id).matches()) {
            throw new AssertionError(
                "orderId không có định dạng ORD-<digits>"
            );
        }
    }

    public static void requirePositiveAmount(Object actual) {
        if (!(actual instanceof Number)) {
            throw new AssertionError(
                "amount phải là JSON number, nhận kiểu " +
                typeName(actual)
            );
        }

        BigDecimal amount =
            new BigDecimal(actual.toString());

        if (amount.compareTo(BigDecimal.ZERO) <= 0) {
            throw new AssertionError(
                "amount phải lớn hơn 0"
            );
        }
    }

    private static String typeName(Object actual) {
        return actual == null
            ? "null"
            : actual.getClass().getSimpleName();
    }
}
~~~

Những quyết định ở đây có chủ đích:

1. Helper nhận `Object` để chủ động kiểm tra type của dữ liệu JSONPath trả về.
2. `orderId` chỉ hợp lệ khi là `String` đúng pattern, không tự ép một `Number` thành chuỗi.
3. `amount` phải là số, không coi string `"125000"` tương đương JSON number `125000`.
4. Khi bất biến không đạt, helper ném `AssertionError` — test framework báo FAIL.
5. Không ghi database, gọi network, tạo token hoặc thay state producer.
6. Không in toàn bộ response, giảm nguy cơ lộ dữ liệu khi CI lưu log.

Regex và điều kiện số trong ví dụ chỉ có ý nghĩa nếu **được producer/consumer thỏa thuận**; không phải quy định sẵn cho mọi Order API.

### Vì sao không dùng phương thức trả về boolean?

Nếu generated test chỉ gọi:

~~~java
checkOrderId(actual);
~~~

mà phương thức trả về `false`, JUnit **không tự fail** trừ khi generator thực sự wrap kết quả đó trong assertion. Dùng helper trả về `void` và ném `AssertionError` khi sai là cách rõ ràng cho mô hình custom command đã kiểm chứng.

## 7. Định nghĩa custom matcher bằng Groovy DSL

Trong các phiên bản Spring Cloud Contract hỗ trợ **`byCommand(...)`** ở response body matchers, có thể tham chiếu method từ base test.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Lấy đơn đã thanh toán với ID hợp lệ"

    request {
        method GET()
        url "/api/orders/ORD-12045"
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-12045",
            status: "PAID",
            amount: 125000,
            currency: "VND"
        )

        bodyMatchers {
            jsonPath('$.orderId',
                byCommand('assertValidOrderId($it)'))
            jsonPath('$.amount',
                byCommand('assertPositiveAmount($it)'))
        }
    }
}
~~~

Cách đọc:

- `jsonPath('$.orderId', ...)` chọn giá trị từ response JSON thực.
- `byCommand('assertValidOrderId($it)')` biểu thị custom command để generator tạo lời gọi helper tương ứng.
- `$it` là placeholder của cú pháp custom command; người học **không cần khai báo** biến Java/Groovy có tên này.
- `assertValidOrderId` và `assertPositiveAmount` phải tồn tại với chữ ký có thể được lời gọi sinh ra sử dụng.
- Body vẫn cung cấp **giá trị mẫu** để tạo stub response.

**Lưu ý phiên bản:** chi tiết generator thay `$it`, kiểu dữ liệu được sinh và vị trí DSL hỗ trợ `byCommand` cần kiểm tra theo bản Spring Cloud Contract đang dùng. Ví dụ thể hiện phương pháp dành cho Groovy response body matchers, không khẳng định mọi YAML field hoặc message matcher có cùng API.

### Vì sao dùng chuỗi single quote?

~~~groovy
jsonPath('$.orderId', byCommand('assertValidOrderId($it)'))
~~~

Chuỗi Groovy single quote giữ nguyên ký hiệu placeholder cho generator. Một lỗi dễ gặp là tự thêm nội suy Groovy hoặc Java expression vào chuỗi khiến mã sinh không còn đúng cú pháp.

## 8. Custom matcher có thể thay đổi ý nghĩa của hợp đồng

Giả sử trước khi tùy biến, contract có:

~~~groovy
body(orderId: "ORD-12045", status: "PAID")
~~~

Nếu test trước đây yêu cầu **equality** của `orderId` với `ORD-12045`, thay nó bằng helper chỉ kiểm tra pattern `^ORD-[0-9]{4,}$` có thể cho phép cả `ORD-99999`.

Đây không chỉ là thay đổi implementation test: đó là **thay đổi mức độ ràng buộc** của contract.

| Cách kiểm tra | Ý nghĩa |
| --- | --- |
| Exact equality | Phải là một giá trị cụ thể, phù hợp fixture cố định |
| Regex pattern | Chấp nhận một tập giá trị theo format |
| Custom helper | Chấp nhận những giá trị helper định nghĩa là hợp lệ |
| Không assertion | Không nhất thiết phát hiện thay đổi ở field đó |

Nếu consumer cần **ID trả về phải trùng ID trong request**, việc helper chỉ xác nhận format chưa đủ. Cần kiểm tra quan hệ request–response bằng khả năng DSL hỗ trợ hoặc test bổ sung phù hợp.

**Không được tự nới matcher chỉ để producer test PASS.** Reviewer cần xem quy tắc nào đã trở thành yếu hơn, và có consumer nào dựa vào quy tắc cũ không.

## 9. Kiểm tra generated source thay vì suy đoán

Khi Maven plugin đã được cấu hình, có thể chạy:

~~~bash
./mvnw clean test
~~~

Hoặc chạy đến pha verify để thực hiện những quality gates được bind trong dự án:

~~~bash
./mvnw clean verify
~~~

Các lệnh chỉ có tác dụng đúng khi plugin goals, generated test source set và test runner được cấu hình. `BUILD SUCCESS` **không tự chứng minh** custom assertion được gọi.

Trong generated source, tìm lời gọi có ý nghĩa tương đương:

~~~java
// Phác thảo, không phải output nguyên văn của generator.
Object actualId =
    /* lấy JSONPath $.orderId từ response thực */;
assertValidOrderId(actualId);
~~~

Điều cần xác minh:

1. Contract có được plugin phát hiện không?
2. Generated test source có thực sự được tạo không?
3. Generated test có kế thừa đúng base class không?
4. Có lời gọi `assertValidOrderId` đúng method không?
5. Kiểu Java thực tế được truyền vào method là gì?
6. Test runner có thực thi generated test và ghi report không?
7. Khi cố ý đưa input sai ở **test kiểm tra âm tính**, helper có làm test FAIL không?

Bước cuối rất quan trọng: nó phát hiện trường hợp helper tồn tại nhưng **không bao giờ được gọi**.

## 10. Viết unit tests riêng cho helper

Ví dụ dùng JUnit 5:

~~~java
package com.example.orders.contract;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderContractAssertionsTest {

    @Test
    void validIdPasses() {
        assertDoesNotThrow(() ->
            OrderContractAssertions.requireValidOrderId(
                "ORD-12045"
            )
        );
    }

    @Test
    void invalidIdFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requireValidOrderId(
                "INVALID"
            )
        );
    }

    @Test
    void wrongIdTypeFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requireValidOrderId(
                12045
            )
        );
    }

    @Test
    void positiveAmountPasses() {
        assertDoesNotThrow(() ->
            OrderContractAssertions.requirePositiveAmount(
                125000
            )
        );
    }

    @Test
    void zeroAmountFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requirePositiveAmount(
                0
            )
        );
    }

    @Test
    void numericStringFails() {
        assertThrows(AssertionError.class, () ->
            OrderContractAssertions.requirePositiveAmount(
                "125000"
            )
        );
    }
}
~~~

Unit test kiểm tra **helper logic**, còn generated producer test kiểm tra **việc helper được gắn đúng với behavior producer**. Hai phép thử bổ sung nhau; không thay thế nhau.

### Boundary cases cũng quan trọng

Với format `ORD-` và ít nhất bốn chữ số, có thể thử:

~~~text
Hợp lệ:
ORD-0000
ORD-12045

Không hợp lệ:
ORD-12
ord-12045
ORD-12A4
null
12045 (JSON number)
~~~

Nếu contract thật có thêm checksum hoặc upper bound, test cả điều kiện đó. Chỉ thử `ORD-12045` rồi cho rằng helper đúng với mọi chuỗi là chưa đủ.

## 11. Vấn đề type của JSONPath và method signature

Một JSONPath có thể trả:

- `String` cho JSON string.
- `Integer`, `Long`, `BigDecimal` hoặc kiểu number khác.
- `Boolean` cho boolean.
- `List` hoặc `Map` cho array/object.
- `null` khi field thiếu, tùy thư viện/cách đọc.

Do đó một helper có signature:

~~~java
public void assertPositiveAmount(String amount)
~~~

có thể không khớp với number của JSON parser. Nếu generated code cast sai, test có thể báo `ClassCastException` trước khi assertion chạy.

### Những cách giải quyết

- Xem generated code và giá trị thực ở response.
- Dùng `Object` làm tham số ở ranh giới nếu cần kiểm tra type động.
- Kiểm tra type và null rõ, rồi chuyển về type nghiệp vụ phù hợp.
- Không ép mọi giá trị thành string để tránh nhận nhầm schema.
- Với số thập phân, sử dụng `BigDecimal` và quy tắc precision/rounding phù hợp; không so equality bằng double một cách tùy tiện khi nghiệp vụ tài chính yêu cầu chính xác.

Một lỗi loại dữ liệu **phải làm test FAIL**, không nên chuyển số dạng string thành số rồi vô tình che breaking change.

## 12. Phân biệt byCommand, execute và triggeredBy

Ba khái niệm này không giống nhau:

| Cơ chế | Vai trò chính | Điểm cần lưu ý |
| --- | --- | --- |
| **`byCommand(...)`** | Custom matching/assertion command trong vị trí DSL được hỗ trợ | Helper phải được generated test gọi đúng chữ ký |
| **`execute(...)`** | Tham chiếu phương thức tính/tạo giá trị động ở phía test tùy ngữ cảnh DSL/version | Không đồng nghĩa với kiểm tra kết quả |
| **`triggeredBy(...)`** | Chỉ phương thức kích hoạt producer để phát message | Là hành động, có thể tạo side effects |
| **Matcher khai báo** | Điều kiện exact/type/regex/JSONPath | Thường dễ review hơn custom code |
| **Fixture/setup helper** | Chuẩn bị state trước khi chạy | Không nên che hành vi producer |

Ví dụ khái niệm:

~~~text
createOrderId()             -> cung cấp dữ liệu test
assertValidOrderId(actual)  -> kiểm tra dữ liệu nhận được
markTestOrderAsPaid()       -> kích hoạt producer phát message
~~~

Không thay `byCommand` bằng `execute` vì thấy cả hai liên quan custom code. Khi DSL có phân biệt phía consumer/producer của giá trị động, cần xác minh **mã sẽ chạy ở phía nào** và stub nào được sinh.

## 13. Base test cho HTTP khác base test cho message

Một producer có thể vừa phục vụ HTTP vừa phát message. Không nên mặc định một base class thiết lập mọi adapter cho mọi generated tests.

Ví dụ layout:

~~~text
src/test/resources/contracts/
  orders-http/get_paid_order.groovy
  orders-message/order_paid.yml

src/test/java/com/example/contract/
  HttpOrderContractBase.java
  OrderMessageContractBase.java
  OrderContractAssertions.java
~~~

- HTTP base test cấu hình MockMvc/HTTP test client và fixtures.
- Message base test cung cấp method trigger, binder/broker test và kiểm tra output message.
- Assertion helper thuần có thể được dùng lại khi thực sự chia sẻ semantics.

Trong nhiều phiên bản plugin, **base class mappings** có thể phân biệt nhóm contracts. Cần kiểm tra cách cấu hình cụ thể và package của generated class; không tự đoán tên property hoặc tên Java class được sinh.

### Vì sao không đặt tất cả trong một base class?

Một lớp chung có thể khởi động database, broker, HTTP server và background jobs cho cả test chỉ cần một matcher JSON đơn giản. Điều đó làm test chậm, flaky và tăng tác dụng phụ. Chia class theo **phạm vi test** giúp giảm những dependency không cần thiết.

## 14. Message contract và phương thức trigger

Ví dụ YAML:

~~~yaml
description: "Đơn đã thanh toán phát ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAID
    orderId: ORD-12045
    schemaVersion: 2
  headers:
    correlationId: CONTRACT-CORR-12045
~~~

`markTestOrderAsPaid()` là method trong producer test environment dùng để **kích hoạt behavior thật cần xác minh**. Nó không phải một assertion.

Một ví dụ phương thức ở base class:

~~~java
// Minh họa, service/fixture là thành phần của dự án.
public void markTestOrderAsPaid() {
    // Gọi application service thật với dữ liệu test.
    // Môi trường dùng test DB và test broker/binder.
    // Không gửi email, payment hoặc event production.
}
~~~

Để producer message tests có ý nghĩa:

1. Trigger phải thực sự chạy đường logic phát message.
2. Message output được captured bởi adapter test phù hợp.
3. Test kiểm tra destination, body và headers theo contract.
4. Các dependencies không thuộc phạm vi được cô lập.
5. Cần test consumer riêng qua Stub Runner hoặc infrastructure tương ứng.

**Không được nhầm `label` với topic name**; `sentTo` là logical destination theo adapter và cấu hình messaging. Message contract PASS không tự chứng minh exactly-once, ordering, retention hoặc routing của broker production.

## 15. Assertion liên quan nhiều trường

Một response:

~~~json
{
  "subtotal": 100000,
  "tax": 10000,
  "total": 110000
}
~~~

cần thỏa:

~~~text
total = subtotal + tax
~~~

Không nên giả định `$it` trong `jsonPath('$.total', ...)` chứa luôn `subtotal` và `tax`. Placeholder thường liên quan **giá trị mà JSONPath đang chọn**.

Có thể chọn:

1. DSL matcher khai báo nếu phiên bản hỗ trợ biểu thức có đủ dữ liệu.
2. Producer integration test bổ sung parse **toàn body JSON**.
3. Custom command chỉ khi generated test thực sự có thể truyền đủ tham số qua cơ chế version hỗ trợ.

Ví dụ helper thuần nhận đủ dữ liệu:

~~~java
public static void requireValidTotal(
        long subtotal, long tax, long total) {
    if (subtotal < 0 || tax < 0) {
        throw new AssertionError(
            "subtotal và tax không được âm"
        );
    }

    long expected;
    try {
        expected = Math.addExact(subtotal, tax);
    } catch (ArithmeticException e) {
        throw new AssertionError(
            "subtotal + tax bị overflow", e
        );
    }

    if (total != expected) {
        throw new AssertionError(
            "total phải bằng subtotal + tax"
        );
    }
}
~~~

Đây là helper Java có thể được dùng bởi **handwritten producer integration test**. Không tự điền lời gọi vào `byCommand` khi chưa biết generator có chuyển đủ ba giá trị hay không.

## 16. Cách viết assertion tốt khi có lỗi

Một custom assertion cần ném lỗi **đủ thông tin** để chẩn đoán, nhưng không lộ dữ liệu nhạy cảm.

| Cách viết | Đánh giá |
| --- | --- |
| `throw new AssertionError()` | Không nói bất biến nào sai |
| `orderId không đúng format ORD-<digits>` | Rõ hơn, ít lộ thông tin |
| `amount phải là JSON number; thực tế String` | Rõ loại lỗi schema |
| Dump toàn bộ Authorization/response body | Có thể lộ secret hoặc dữ liệu cá nhân |

Nên:

- Ghi field/JSONPath hoặc tên bất biến.
- Phân biệt missing/null, wrong type và wrong value.
- Không swallow exception.
- Không tự sửa response/DB để assertion PASS.
- Chỉ log giá trị mẫu tổng hợp nếu chắc chắn an toàn.
- Dùng test framework assertion utilities khi phù hợp, nhưng giữ method behavior tương thích với generator.

Nếu helper kiểm tra rất nhiều điều kiện, cân nhắc tách thành các matcher riêng để CI report dễ chỉ ra trường nào thất bại.

## 17. Rủi ro side effects của custom helper

Tên `assertValidOrderId` không biến method thành read-only. Nó vẫn có thể gọi network, database hoặc truy cập secrets bằng quyền của CI process.

| Anti-pattern | Vấn đề | Cách thay |
| --- | --- | --- |
| Assertion gọi production API | Gây I/O ngoài test và phụ thuộc availability | Chỉ kiểm tra response đã thu thập |
| Helper gọi repository `save` để “sửa” dữ liệu | Làm test xanh giả | Setup riêng, assertion chỉ đọc |
| Catch `AssertionError` rồi ghi log | Che test FAIL | Để lỗi lan lên test runner |
| `contains("PAID")` trên toàn JSON | Có thể match trường debug | Parse đúng `$.status` |
| `System.setProperty` trong helper | Thay global state của test khác | Cấu hình theo instance |
| `Thread.sleep` cố định | Flaky, chậm CI | Polling theo predicate và timeout hữu hạn |
| Log nguyên request headers | Rò rỉ Authorization/Cookie | Redact |
| Tắt hostname verification | Che lỗi TLS | Test certificate + truststore |
| Tải script từ URL để kiểm tra | Mở rộng trust boundary của build | Bỏ I/O, pin dependencies và review |
| Gọi service để “tìm expected response” | Expected value phụ thuộc bên ngoài | Fixture/hợp đồng xác định |

Không phải tất cả **integration assertions có I/O** đều sai. Ví dụ POST phải tạo đúng record trong **test DB**. Nhưng hãy đặt tên và phạm vi rõ, ghi nhận tài nguyên được phép, không giấu I/O trong helper định dạng ID.

## 18. Setup, assertion và cleanup phải tách biệt

Một flow khuyến nghị:

~~~text
SETUP:
  verify isolated test environment
  seed synthetic fixture in test database
  configure test-only external clients

ACT:
  generated test invokes producer endpoint/message logic

ASSERT:
  DSL matchers + custom pure helpers inspect actual output
  explicit integration checks inspect allowed side effects

CLEANUP:
  stop async work
  delete only records/resources owned by this test
~~~

Lý do:

- Nếu assertion ghi lại expected state trước khi đọc, nó **không còn xác minh producer**.
- Nếu cleanup xóa toàn bộ bảng/topic dùng chung, các tests song song có thể phá nhau.
- Nếu side effect xảy ra trên thread/server transaction khác, `@Transactional` của test không mặc định rollback mọi thứ.
- Nếu scheduler hoặc message consumer tiếp tục chạy sau `@AfterEach`, test khác có thể nhận tác động.

Với CI có test chạy song song, nên dùng namespace/ID riêng, test DB/broker riêng hoặc cơ chế isolation đủ mạnh và xác minh thread safety của HTTP test client.

## 19. Nguồn gây false PASS ngoài logic helper

Một test PASS có thể kém giá trị vì:

1. Generated test không được sinh.
2. `0 tests` được thực thi nhưng build vẫn xanh.
3. Base class không phải class generated test extends.
4. Command bị lỗi nhưng code sinh không gọi helper.
5. Helper trả boolean false mà framework không kiểm tra.
6. Fixture/mock trả đúng body mẫu mà không đi qua implementation producer.
7. Matcher được nới đến mức không phát hiện schema change.
8. Consumer test chạy với stub artifact **version cũ**.
9. Dữ liệu test quá đơn giản, không bao phủ boundary/error cases.
10. Test có retry hoặc shared state khiến lỗi bị che.

### Kiểm tra âm tính

Một kỹ thuật quan trọng là cố ý đưa giá trị sai trong **test fixture riêng có kiểm soát**:

~~~text
orderId = "INVALID"

Expected:
generated producer test FAIL
message: orderId không có định dạng ORD-<digits>
~~~

Nếu test vẫn PASS, kiểm tra mapping của `byCommand`, generated code và test execution. **Không sửa producer production behavior để tạo lỗi test** ngoài một môi trường kiểm chứng được quản lý.

## 20. Khi helper trở thành phần mềm cần bảo trì

Một custom assertion sau khi được dùng rộng rãi có thể là dependency của nhiều contract tests. Nên áp dụng:

- Tên method thể hiện rõ bất biến: `assertValidOrderId` thay vì `check`.
- Signature đơn giản, có null/type policy.
- Không phụ thuộc implementation data structure không thuộc contract.
- Unit tests độc lập và boundary tests.
- Changelog/review khi thay đổi matcher semantics.
- Không đưa state hoặc network vào method.
- Đảm bảo tương thích với Java/test runner/plugin version của producer.
- Không tạo một `CommonHelpers` khổng lồ cho các domains không liên quan.

Đặc biệt, **đổi helper có thể thay đổi hàng loạt contract tests** dù không sửa file DSL. Vì thế review helpers như **một phần của contract surface**, không chỉ như utility code nội bộ.

### Khi helper bị đổi để accept thêm giá trị

Nếu `assertValidOrderId` trước đây chỉ chấp nhận `ORD-1234` format, rồi thay để accept mọi chuỗi không rỗng, có thể vô tình mất contract validation ở tất cả DSL tham chiếu method đó.

Một review đúng cần tìm tất cả callers đã được cấu hình, so sánh old/new semantics và chạy lại producer tests cùng consumer-impact tests liên quan.

## 21. Lỗi thường gặp và đường chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Bước đầu kiểm tra |
| --- | --- | --- |
| `cannot find symbol assertValidOrderId` | Base class không được dùng, tên/visibility sai | Generated test extends ai? |
| `ClassCastException` | JSONPath trả type khác | Chữ ký method và actual type |
| JSONPath luôn null | Path sai/missing field | Response body và matcher path |
| Custom helper không làm test FAIL | Không được gọi hoặc swallow error | Negative test + generated source |
| Test FAIL trước HTTP request | Context/setup lỗi | Spring context, bean startup, fixture |
| Stub Runner không áp dụng helper | Helper chỉ chạy producer side | Consumer tests có assertions riêng? |
| Message trigger không tồn tại | `triggeredBy` tham chiếu method sai | Base test/message test generator |
| Event xuất hiện ở broker dùng chung | Test profile sai | URL, credentials, binder |
| Local PASS, CI FAIL | Test runner/plugin/toolchain khác, fixture flaky | Effective configuration và reports |
| Maven xanh với `0 generated tests` | Goals/test execution bị skip | Plugin logs và Surefire/Failsafe reports |
| CI PASS với stub cũ | Version/cache mismatch | GAV/classifier/checksum đã tải |

Thứ tự kiểm tra hữu ích: **contract discovered → generated source → base class → helper call → test execution → producer behavior → artifact provenance → consumer verification**.

Đừng đổi DSL matcher khi vấn đề thực tế là test class không compile hoặc CI không chạy generated tests.

## 22. CI và bằng chứng cần lưu

~~~mermaid
flowchart TD
    A["Commit DSL + base helper"] --> B["Unit tests của helper"]
    B --> C{"PASS?"}
    C -->|Không| X["BLOCK"]
    C -->|Có| D["Sinh generated producer tests"]
    D --> E{"Có lời gọi helper?"}
    E -->|Không| X
    E -->|Có| F["Chạy producer tests"]
    F --> G{"PASS, không skip?"}
    G -->|Không| X
    G -->|Có| H["Sinh/publish stub artifact"]
    H --> I["Khóa GAV/version/checksum"]
    I --> J["Consumer Stub Runner tests"]
    J --> K{"Consumer assertions PASS?"}
    K -->|Không| X
    K -->|Có| L["Lưu evidence và đánh giá release"]
~~~

Một record CI có thể ghi:

~~~yaml
# Metadata do dự án thiết kế, không phải output mặc định SCC.
producer_commit: "abc123_FULL_COMMIT"
contract_revision: "def456_FULL_COMMIT"
helper_tests:
  status: PASS
generated_producer_tests:
  executed: true
  skipped: 0
  status: PASS
stub_artifact:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "SHA256_DA_TINH_TU_JAR"
consumer_tests:
  stub_coordinate: "com.example.orders:order-service:2.5.0:stubs"
  status: PASS
~~~

Các giá trị là placeholder minh họa; CI phải tính checksum từ file thật và đọc test reports. **Không lấy chữ `BUILD SUCCESS` làm bằng chứng duy nhất** nếu generated tests bị skip.

## 23. Bài tập thực hành

### Bài tập A — Chọn matcher

Response có `status = PAID` và `orderId` theo regex `^ORD-[0-9]{4,}$`.

**Yêu cầu:** điều kiện nào nên dùng matcher DSL, khi nào cần custom helper?

**Gợi ý:** equality/regex khai báo đủ thì không cần helper; chỉ dùng helper nếu có checksum/bất biến riêng.

### Bài tập B — Viết helper số tiền

`amount` phải là JSON number dương, không được là numeric string.

**Yêu cầu:** viết helper nhận `Object` và tests cho 0, số âm, null, string và số dương.

**Gợi ý:** `instanceof Number` rồi chuyển `BigDecimal` để so sánh.

### Bài tập C — Sai method signature

DSL có `byCommand('assertValidOrderId($it)')` nhưng base test chỉ có `private boolean checkId(String value)`.

**Yêu cầu:** phân tích lỗi tên method, visibility và return type.

**Gợi ý:** tạo accessible method có tên đúng; ném `AssertionError` khi không đạt.

### Bài tập D — Helper chưa từng chạy

Generated test vẫn PASS với `orderId = INVALID`.

**Yêu cầu:** lập danh sách kiểm tra.

**Gợi ý:** generated source, base class mapping, JSONPath, skip flags và negative unit test.

### Bài tập E — Matcher bị nới

Trước đây ID phải trùng `ORD-12045` của fixture; helper mới chỉ kiểm tra tiền tố `ORD-`.

**Yêu cầu:** đánh giá nguy cơ false PASS.

**Gợi ý:** cần kiểm tra quan hệ với request; nới format có thể làm mất điều kiện.

### Bài tập F — Message trigger

Contract có `triggeredBy: markTestOrderAsPaid()`; helper chỉ trả `true` mà không gọi producer.

**Yêu cầu:** vì sao không kiểm chứng message producer?

**Gợi ý:** trigger phải kích hoạt đường publish thật trong test binder/broker cô lập.

### Bài tập G — Assertion có network

`assertValidOrderId` gọi API production để kiểm tra ID tồn tại.

**Yêu cầu:** viết lại cách kiểm chứng.

**Gợi ý:** helper thuần; integration check riêng chỉ dùng môi trường test được cho phép.

### Bài tập H — Quan hệ ba trường

Response có `subtotal`, `tax` và `total`.

**Yêu cầu:** `$it` của JSONPath `$.total` có tự cung cấp ba trường không? Cần test ra sao?

**Gợi ý:** không mặc định; dùng assertion test đọc toàn response hoặc API hỗ trợ đã được kiểm chứng.

### Bài tập I — Producer tests bị skip

Consumer PASS với Stub Runner, nhưng Maven build producer không chạy generated tests.

**Yêu cầu:** có đủ bằng chứng API compatibility không?

**Gợi ý:** chưa; producer implementation chưa được xác minh với hợp đồng.

### Bài tập J — Chia base class

Một `ContractBase` khởi động MockMvc, Kafka và scheduler cho mọi HTTP contracts.

**Yêu cầu:** thiết kế lại cho tests nhanh và ít side effects.

**Gợi ý:** base classes theo nhóm HTTP/message, helper thuần được dùng lại.

## 24. Checklist trước khi merge custom assertion

### Thiết kế

- [ ] Có lý do cụ thể phải dùng helper thay vì matcher khai báo.
- [ ] Điều kiện helper là bất biến consumer quan tâm.
- [ ] Không nới điều kiện một cách vô ý.
- [ ] Đã định nghĩa null, wrong type và boundary behavior.
- [ ] Helper có tên và failure message rõ.

### Base test và sinh test

- [ ] Base class mapping đúng package, generated test extends/nạp đúng class.
- [ ] Method accessible, tên và signature khớp generated call.
- [ ] Đã kiểm tra cú pháp `byCommand` của plugin version thực tế.
- [ ] Generated source chứa invocation của helper.
- [ ] Helper có unit tests độc lập.
- [ ] Negative test khiến generated producer test FAIL như dự kiến.
- [ ] Generated tests được biên dịch, chạy và không skip.
- [ ] Base test không mock luôn output producer cần kiểm chứng.

### An toàn và vận hành

- [ ] Helper không tự sửa dữ liệu để PASS.
- [ ] Không gọi network hoặc đọc secret trong pure assertion.
- [ ] Side effects của integration assertions được ghi rõ và cô lập.
- [ ] Fixture synthetic, deterministic và có cleanup trong phạm vi test.
- [ ] Không có shared mutable state gây lỗi song song.
- [ ] Không log Authorization/PII/raw payload nhạy cảm.
- [ ] Message triggers dùng test binder/broker, không gửi production.
- [ ] Không dùng `@Transactional` như bảo đảm mọi side effects rollback.

### Bằng chứng tương thích

- [ ] Contract revision và producer commit được ghi.
- [ ] Producer generated tests PASS thật sự.
- [ ] Stub JAR đúng artifactId/version/classifier và có checksum.
- [ ] Consumer Stub Runner tải đúng artifact mới.
- [ ] Consumer tests có assertions nghiệp vụ riêng.
- [ ] CI report nêu phạm vi và giới hạn, không tuyên bố mọi production behavior đã được test.

## Kết luận

**Custom assertion** và **helper trong base test** cho phép mở rộng khả năng kiểm tra của Spring Cloud Contract khi matcher khai báo chưa diễn đạt đủ một bất biến nghiệp vụ. Thiết kế tốt phải giữ hợp đồng rõ ràng, helper thuần và có unit test, base class chỉ chuẩn bị đúng môi trường, và generated producer tests thực sự gọi helper trên **output của producer**.

Không nên nhầm một custom assertion PASS phía producer với khả năng tương thích toàn bộ consumer. Stub Runner còn cần được chạy với artifact đúng phiên bản và consumer phải có assertions riêng. Kết luận CI chỉ đáng tin khi có **producer verification + stub provenance + consumer verification** cùng revision.

**Ghi nhớ:** *Ưu tiên matcher khai báo khi đủ; dùng custom helper có chủ đích; đọc generated source để chắc chắn lời gọi xảy ra; và đừng dùng assertion để che lỗi producer hoặc làm test xanh giả.*
