# Kích hoạt producer bằng triggeredBy

## Mục tiêu học tập

Trong **Spring Cloud Contract**, một hợp đồng không chỉ mô tả request/response HTTP mà còn có thể mô tả **thông điệp** trao đổi qua Spring Cloud Stream, Spring Integration, JMS hoặc công nghệ messaging được cấu hình. Producer là dịch vụ **phát thông điệp**; consumer là dịch vụ **nhận và xử lý thông điệp**. Hợp đồng **Groovy/YAML DSL** là nguồn để sinh **kiểm thử phía producer**, đóng gói **stub**, dùng **Stub Runner** ở phía consumer và đưa kiểm chứng vào **CI** nhằm phát hiện thay đổi giao diện không tương thích.

Bài này thuộc chương **Hợp đồng thông điệp** và tập trung vào `triggeredBy`: cách yêu cầu generated producer test **gọi một phương thức trong base test** để khởi phát hành vi tạo thông điệp, thay vì đợi một thông điệp đầu vào khác.

Sau bài học, bạn có thể:

- Giải thích vai trò của `input.triggeredBy` trong hợp đồng messaging.
- Viết Groovy DSL và YAML DSL mô tả **sự kiện được producer tự phát** sau một hành động.
- Định nghĩa phương thức kích hoạt trong **base test class** và nối phương thức đó với code producer thật.
- Đọc generated producer test để xác minh **trigger → nhận output → assert payload/header**.
- Phân biệt `triggeredBy` phía producer với `label` và `StubTrigger.trigger(...)` phía consumer.
- Kiểm soát destination, binder, fixture và thời gian chờ để test message ổn định.
- Nhận diện giới hạn của contract test với broker, retry, thứ tự thông điệp và transaction.

## 1. Khi nào cần triggeredBy?

Ví dụ hệ thống quản lý tồn kho có hai dịch vụ:

- **Inventory Service** là producer, phát sự kiện `StockChanged` khi số lượng hàng thay đổi.
- **Checkout Service** là consumer, nghe sự kiện đó để cập nhật khả năng cho đặt hàng.

Khi quantity của SKU-101 chuyển thành 0, Inventory phát một sự kiện minh họa:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 0
}
~~~

Sự kiện được gửi tới destination logic `stock-events` và có thể kèm header `eventType: StockChanged`, `contentType: application/json`.

Producer có thể phát sự kiện bởi các nguyên nhân như:

- Một service method được gọi sau khi hoàn tất thao tác nghiệp vụ.
- Một command nội bộ kích hoạt việc cập nhật tồn kho.
- Một scheduled task hoàn tất xử lý.
- Một event nội bộ được ghi vào outbox rồi chuyển đi.

Trong tất cả trường hợp trên, **generated contract test vẫn cần một hành động xác định để kích hoạt producer**. Đó là lúc dùng `triggeredBy`.

### Ngữ nghĩa cốt lõi

~~~groovy
input {
    triggeredBy('emitStockChanged()')
}
~~~

Đoạn này nói: **ở phía producer test, hãy gọi phương thức `emitStockChanged()`**. Phương thức do nhóm tự định nghĩa trong base test class hoặc nơi mà generated test truy cập được, và nó phải dẫn đến việc producer phát sự kiện.

`triggeredBy` **không phải** tên topic, queue hay consumer callback. Nó cũng **không tự phát thông điệp** nếu phương thức được gọi không làm gì.

Tách rõ ba thao tác:

| Thành phần | Ai dùng? | Mục đích |
|---|---|---|
| `triggeredBy('emitStockChanged()')` | **Generated producer test** | Gọi phương thức khởi phát hành vi producer |
| `outputMessage.sentTo('stock-events')` | **Generated test / messaging adapter** | Chỉ ra destination cần quan sát thông điệp đầu ra |
| `label 'stock_changed'` | **Consumer test với Stub Runner** | Đặt tên sự kiện stub để test consumer có thể chủ động phát bằng `StubTrigger` |

Không nên thay `triggeredBy` bằng `label` hoặc ngược lại. Chúng nằm ở hai giai đoạn của contract testing.

## 2. Nhìn toàn bộ luồng hai phía

~~~mermaid
sequenceDiagram
    participant D as Contract Groovy/YAML
    participant T as Generated producer test
    participant B as Base test class
    participant P as Producer thực
    participant M as Messaging verifier / test binder
    participant S as Stub Runner
    participant C as Consumer test
    D->>T: Sinh test từ triggeredBy + outputMessage
    T->>B: Gọi emitStockChanged()
    B->>P: Gọi nghiệp vụ phát StockChanged
    P->>M: Gửi thông điệp tới stock-events
    T->>M: Nhận message và assert payload, headers
    D->>S: Đóng gói contract thành stub artifact
    C->>S: trigger("stock_changed")
    S->>C: Phát message giả lập tới destination
    C->>C: Xác minh handler và trạng thái consumer
~~~

**Hai đường kiểm chứng không thay thế nhau:**

1. **Producer test** kiểm tra rằng code producer thật **có phát** đúng message sau khi được kích hoạt.
2. **Consumer test** dùng message stub để kiểm tra rằng code consumer thật **xử lý được** thông điệp theo hợp đồng.

Nếu test consumer với Stub Runner xanh, điều đó không tự chứng minh code Inventory đang phát message đúng. Nếu producer test xanh, điều đó không tự chứng minh Checkout xử lý message đúng.

## 3. Một hợp đồng Groovy DSL đầy đủ

Giả sử Inventory phát sự kiện khi `SKU-101` chuyển sang hết hàng. Đặt contract ở thư mục mà plugin được cấu hình đọc, ví dụ:

~~~text
src/test/resources/contracts/inventory/
└── stockChanged.groovy
~~~

Nội dung:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Phat su kien khi ton kho SKU-101 ve 0'
    label 'stock_changed'

    input {
        triggeredBy('emitStockChanged()')
    }

    outputMessage {
        sentTo('stock-events')

        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )

        headers {
            header('eventType', 'StockChanged')
            messagingContentType(applicationJson())
        }
    }
}
~~~

### Đọc từng phần

| Đoạn DSL | Ý nghĩa | Sai lầm cần tránh |
|---|---|---|
| `description` | Mô tả tình huống cho người đọc | Coi mô tả là assertion kỹ thuật |
| `label 'stock_changed'` | Tên để phía consumer kích hoạt message stub | Nghĩ label là tên method Java |
| `input.triggeredBy` | Method generated producer test gọi | Nghĩ đó là tên topic/broker |
| `outputMessage.sentTo` | Destination cần nhận message | Nghĩ chỉ cần đặt đúng string là binder đã kết nối |
| `outputMessage.body` | Nội dung message phải phù hợp | Nhầm `quantity: 0` là string `'0'` |
| `outputMessage.headers` | Header mà producer cần phát | Nhầm HTTP `Content-Type` với cấu hình header messaging |
| `messagingContentType(applicationJson())` | Nội dung message là JSON theo helper DSL | Tự cho rằng consumer luôn nhận đúng kiểu Java object mà không xét converter |

`body` có ba field với **kiểu dữ liệu cụ thể**: `eventType` và `sku` là string, `quantity` là number. Nếu consumer deserialize `quantity` thành số, đổi `0` thành chuỗi `"0"` có thể phá vỡ hợp đồng.

`sentTo('stock-events')` chỉ là **tên destination minh họa**. Tên này phải được thống nhất với cấu hình binding hoặc messaging integration thực tế.

### Điều gì xảy ra trong generated test?

Về mặt hành vi, generator cần tạo một test tương đương:

~~~text
WHEN
    emitStockChanged()

THEN
    receive one expected message from destination "stock-events"
    assert message exists
    assert header eventType == "StockChanged"
    assert messaging contentType == "application/json"
    assert body.eventType == "StockChanged"
    assert body.sku == "SKU-101"
    assert body.quantity == 0 (number)
~~~

Đây là **pseudocode**, không phải bản chép nguyên văn generated Java test. Cú pháp, class và cách parse payload khác nhau theo phiên bản Spring Cloud Contract và messaging adapter. Điều quan trọng là test **thực sự gọi method trigger** và **nhận thông điệp từ destination**, chứ không chỉ kiểm tra một JSON fixture tĩnh.

## 4. YAML DSL tương đương

Spring Cloud Contract hỗ trợ biểu diễn tình huống tương đương bằng YAML. Ví dụ file `stockChanged.yml`:

~~~yaml
description: 'Phat su kien khi ton kho SKU-101 ve 0'
label: stock_changed
input:
  triggeredBy: emitStockChanged()
outputMessage:
  sentTo: stock-events
  body:
    eventType: 'StockChanged'
    sku: 'SKU-101'
    quantity: 0
  headers:
    eventType: 'StockChanged'
    contentType: 'application/json'
~~~

Điểm khác:

- YAML dùng `input.triggeredBy: emitStockChanged()` thay cho Groovy `triggeredBy('emitStockChanged()')`.
- `outputMessage.body` là YAML mapping. String, number và boolean cần giữ đúng kiểu.
- `headers` là mapping. `contentType` ở đây thuộc **message**, không phải HTTP request.
- Không copy nguyên hàm Groovy `messagingContentType(...)` vào YAML.

**Chọn một định dạng cho một tình huống trong build thực tế**, trừ khi nhóm chủ động muốn tạo các contract khác nhau và bảo đảm không sinh mapping/event trùng. Đặt cả `stockChanged.groovy` và `stockChanged.yml` biểu diễn cùng một sự kiện có thể dẫn tới nhiều test hoặc hai stub tương đương không cần thiết.

### Cẩn thận với YAML quoting

~~~yaml
outputMessage:
  body:
    sku: '00123'
    quantity: 0
    available: false
~~~

`'00123'` là mã định danh string; `0` là number; `false` là boolean. Đổi thành `quantity: '0'` hoặc `available: 'false'` sẽ đổi kiểu của message. Parser YAML còn có khác biệt theo phiên bản/schema với `on`, `off`, `yes`, `no` nên quote nếu chúng phải là văn bản.

## 5. Viết phương thức kích hoạt trong base test

Một contract có `triggeredBy('emitStockChanged()')` chỉ có ý nghĩa khi generated test **gọi được** method đó. Với Spring Boot, base test class thường khởi tạo application context, đăng ký messaging verifier và gọi service phát thông điệp.

Ví dụ một phương án Java:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import com.example.inventory.StockEventPublisher;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.verifier.messaging.boot.AutoConfigureMessageVerifier;

@SpringBootTest(classes = InventoryApplication.class)
@AutoConfigureMessageVerifier
public abstract class InventoryMessageContractBase {

    @Autowired
    private StockEventPublisher publisher;

    public void emitStockChanged() {
        publisher.publishStockChanged("SKU-101", 0);
    }
}
~~~

**Điểm bắt buộc:**

- Tên method `emitStockChanged()` phải khớp chuỗi được khai báo trong `triggeredBy`.
- Method phải **truy cập được** từ generated test; `public` là lựa chọn dễ hiểu trong ví dụ.
- Method phải khởi phát **code producer thật**. Nếu nó chỉ ghi log hoặc tạo một object rồi không gửi message, test sẽ không nhận được sự kiện.
- `@AutoConfigureMessageVerifier` cần thiết để thiết lập hạ tầng verifier cho messaging theo hướng dẫn Spring Cloud Contract.
- `@SpringBootTest` dựng ứng dụng trong môi trường test; không tự bảo đảm mọi broker, queue, topic đã sẵn sàng.
- Base class **phải được plugin chỉ định** qua `baseClassForTests` hoặc cơ chế ánh xạ base classes phù hợp; chỉ có file Java trong `src/test` không đủ.

### Method trigger nên gọi tầng nào?

| Cách viết method | Đánh giá | Vì sao |
|---|---|---|
| Gọi application service thực, service phát sự kiện | **Ưu tiên** khi muốn bảo vệ hành vi publish | Test đi qua mã producer được cam kết |
| Gọi publisher component thực trực tiếp | Phù hợp khi contract kiểm chứng chính publisher | Chưa bảo vệ điều kiện nghiệp vụ quyết định khi nào phát |
| Gọi controller thật để kích hoạt nghiệp vụ | Có thể phù hợp, nhưng là một bước setup phức tạp hơn | Cần kiểm soát HTTP/auth/dữ liệu nền |
| Gọi một fake emitter tự gửi đúng fixture, bỏ qua producer | **Không phù hợp** nếu mục tiêu là kiểm chứng producer | Test có thể xanh dù code producer bị hỏng |
| Gọi method không phát gì | Sai | Generated test sẽ chờ message rồi fail/timeout |
| Gọi method phát nhiều sự kiện ngẫu nhiên | Không ổn định | Test có thể nhận nhầm message hoặc phụ thuộc thứ tự |

Đặt tên method để thể hiện **hành động nghiệp vụ**, ví dụ `emitStockChanged()`, `completeShipment()` hoặc `markInvoicePaid()`. Tránh `test1()` hoặc `doSomething()` vì reviewer khó biết sự kiện phát từ đâu.

## 6. Ví dụ producer phát message qua Spring Cloud Stream

Giả sử Inventory dùng **Spring Cloud Stream `StreamBridge`** để phát sự kiện. Một component Java minh họa:

~~~java
package com.example.inventory;

import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class StockEventPublisher {

    private final StreamBridge streamBridge;

    public StockEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publishStockChanged(String sku, int quantity) {
        Message<Map<String, Object>> message = MessageBuilder
            .withPayload(Map.<String, Object>of(
                "eventType", "StockChanged",
                "sku", sku,
                "quantity", quantity
            ))
            .setHeader("eventType", "StockChanged")
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
            .build();

        boolean sent = streamBridge.send("stockChanged-out-0", message);
        if (!sent) {
            throw new IllegalStateException("Cannot publish stock event");
        }
    }
}
~~~

Và cấu hình destination, ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        stockChanged-out-0:
          destination: stock-events
          content-type: application/json
~~~

Trong ví dụ này:

- `stockChanged-out-0` là **tên binding logic** được component dùng khi gọi `StreamBridge.send(...)`.
- `stock-events` là **destination** mà message được chuyển tới.
- Contract khai báo `sentTo('stock-events')` để verifier quan sát đúng đích.
- `eventType` là header do ứng dụng đặt; `contentType` được mô tả bằng helper DSL và message header/cấu hình phù hợp.

**Quan trọng:** đây là ví dụ kiến trúc Spring Cloud Stream, không phải cam kết mọi dự án có thể chạy bằng cách chỉ sao chép hai file. Producer còn cần đúng starter/binder, Spring Boot/Cloud version tương thích và test configuration. Nếu phiên bản StreamBridge hoặc converter biến đổi payload/header khác ví dụ, hãy đọc **message thực tế trong generated test** và điều chỉnh cấu hình.

### Test binder thay vì broker production

Trong môi trường contract tests với Spring Cloud Stream, có thể sử dụng **test binder** để quan sát message mà không phải chạy Kafka/RabbitMQ production. Theo tài liệu Spring Cloud Contract, dependency test thường có dạng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream</artifactId>
    <classifier>test-binder</classifier>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
~~~

Với Gradle có thể khai báo:

~~~groovy
testImplementation(
    group: 'org.springframework.cloud',
    name: 'spring-cloud-stream',
    classifier: 'test-binder'
)
~~~

Tùy phiên bản, cần thêm cấu hình test binder hoặc `@ImportAutoConfiguration(TestChannelBinderConfiguration.class)`, đảm bảo binder test thực sự được sử dụng. **Không tự giả định** có dependency là Spring đã chuyển hoàn toàn sang test binder trong mọi cấu hình. Nếu dùng nhiều binder, chọn rõ binder được kiểm tra.

### Producer test bảo vệ đến đâu?

Ví dụ gọi trực tiếp `StockEventPublisher` chỉ xác nhận component đó phát message với payload/header đúng trong phạm vi test. Nếu hành vi thực là “khi đơn hàng được xác nhận thành công mới phát StockChanged”, một test chỉ gọi publisher **chưa kiểm chứng điều kiện nghiệp vụ** và transaction. Hãy thiết kế thêm service/integration test, hoặc để method trigger gọi **application service thực** theo đúng tình huống.

## 7. Kết nối base class với Spring Cloud Contract plugin

Trong module producer, plugin phải biết base class nào được generated tests kế thừa.

Cấu hình Maven minh họa:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
            com.example.inventory.contract.InventoryMessageContractBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

`REPLACE_WITH_COMPATIBLE_VERSION` chỉ là placeholder; phải dùng phiên bản Spring Cloud Contract phù hợp với Spring Boot và Spring Cloud release train của dự án. `testFramework` quyết định framework của generated tests; JUnit 5 không phải mặc định cố định trên mọi version.

Với Gradle (phần cấu hình minh họa):

~~~groovy
contracts {
    testFramework = 'JUNIT5'
    baseClassForTests =
        'com.example.inventory.contract.InventoryMessageContractBase'
}
~~~

Các đoạn trên **không phải toàn bộ build file**; còn phải áp dụng plugin, dependency `spring-cloud-starter-contract-verifier`, repository và dependency messaging tương thích. Nếu project có nhiều nhóm contract với base class khác nhau, có thể dùng cơ chế mapping base classes do plugin hỗ trợ.

**Đừng chọn `testMode=MOCKMVC` chỉ để thử message:** test mode HTTP và messaging integration là hai khái niệm khác nhau. Với thông điệp, điều thiết yếu là `@AutoConfigureMessageVerifier` cùng adapter/binder phù hợp, không phải setup MockMvc khi không có HTTP request.

## 8. Kiểm tra generated producer test thật sự làm gì

Sau khi cấu hình build, producer chạy bước sinh/chạy contract test. Với Maven, có thể dùng:

~~~bash
./mvnw clean verify
~~~

Đường dẫn generated tests thường nằm ở:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Tên file và vị trí cụ thể phụ thuộc plugin/version và build output directory. Hãy xem log build để biết **có bao nhiêu contract message được phát hiện và test thực thi**, không kết luận build xanh đồng nghĩa mọi contract đã chạy.

### Bốn bằng chứng cần tìm

Với contract `stockChanged.groovy`, hãy mở generated test tương ứng và xác minh:

1. **Trigger:** Test thật sự gọi `emitStockChanged()` (không chỉ gọi một stub trả message).
2. **Receive:** Sau khi trigger, test nhận một message từ `stock-events` qua messaging verifier.
3. **Headers:** Test assert `eventType`, `contentType` hoặc các header mà consumer phụ thuộc.
4. **Payload:** Test assert các field `eventType`, `sku`, `quantity` với đúng kiểu/giá trị hoặc matcher đã công bố.

Một hình dung về generated test (**pseudocode, không phải output Java nguyên văn**):

~~~text
TEST validate_stockChanged:
  WHEN:
    emitStockChanged()  // method từ base class

  THEN:
    message = messagingVerifier.receive("stock-events")
    assert message != null
    assert message.headers["eventType"] == "StockChanged"
    assert contentType is application/json

    payload = decodeJson(message)
    assert payload.eventType == "StockChanged"
    assert payload.sku == "SKU-101"
    assert payload.quantity == 0
~~~

Hành vi tương tự được tài liệu Spring Cloud Contract mô tả: generated test gọi method trong `triggeredBy`, sau đó nhận thông điệp ở destination rồi kiểm tra body/headers. Cú pháp assertion có thể dùng JsonPath, assertion utility hoặc object mapper phụ thuộc generator.

**Không sửa generated test trực tiếp.** Nếu assertion sai hoặc method không tìm thấy, sửa DSL, base class, binder/test setup rồi sinh lại. File generated thường bị ghi đè ở lần build tiếp theo.

### Tín hiệu “xanh nhưng chưa đủ”

- Test chỉ thấy message được gửi nhưng không kiểm tra `quantity` dù consumer phụ thuộc kiểu number.
- Test không thực sự chạy do filter task hoặc không phát hiện contract.
- Base class trực tiếp đưa fixture vào một queue test mà không gọi publisher thật.
- Contract mới bỏ field quan trọng và producer code cũng bỏ field đó; generated test mới xanh nhưng consumer cũ vẫn lỗi.
- Generated test đang dùng message khác từ test trước vì destination bị dùng chung và không reset.

Những trường hợp này cần xem **giới hạn kiểm thử** và bằng chứng thực thi, không chỉ xem màu xanh của CI.

## 9. Phân biệt triggeredBy với messageFrom

Hai kiểu hợp đồng messaging phục vụ hai tình huống khác nhau.

### A. Producer tự phát thông điệp sau hành động

~~~groovy
input {
    triggeredBy('emitStockChanged()')
}
outputMessage {
    sentTo('stock-events')
    body(eventType: 'StockChanged', sku: 'SKU-101', quantity: 0)
}
~~~

Ở đây không cần mô tả một message đầu vào cụ thể. Test **gọi method** để làm producer phát message.

### B. Producer phát phản hồi do nhận một message khác

~~~groovy
input {
    messageFrom('stock-commands')
    messageBody(
        command: 'RefreshStock',
        sku: 'SKU-101'
    )
    messageHeaders {
        header('contentType', 'application/json')
    }
}
outputMessage {
    sentTo('stock-events')
    body(
        eventType: 'StockRefreshed',
        sku: 'SKU-101'
    )
}
~~~

Ở đây generated producer test cần **đưa một message vào** destination `stock-commands` rồi quan sát output. Nó khác với việc gọi `emitStockChanged()`.

| Câu hỏi | `triggeredBy` | `messageFrom` + `messageBody` |
|---|---|---|
| Hành động làm test bắt đầu | Gọi một method trong base class | Đưa một message vào input destination |
| Có cần message đầu vào? | Không, trừ khi method tự kích hoạt quy trình có message nội bộ | Có, được mô tả trong contract |
| Producer được kiểm chứng | Hành vi phát message từ tác vụ/nghiệp vụ | Hành vi xử lý message đầu vào và phát output |
| Setup cần có | Method trigger, service publisher, output adapter | Input adapter/listener, message converter, output adapter |
| Sai lầm phổ biến | Method trống hoặc chỉ đẩy fixture giả | Test không thực sự đi qua listener thật |

Không nên viết đồng thời `triggeredBy` và `messageFrom` cho cùng một tình huống nếu chưa có nhu cầu cụ thể và chưa xác nhận DSL hỗ trợ tổ hợp đó. Hãy chọn **mô hình tương tác đúng với cách producer hoạt động**.

## 10. Label và StubTrigger: kích hoạt sự kiện ở phía consumer

Đây là phần hay bị nhầm nhất.

Contract chứa:

~~~groovy
label 'stock_changed'
input {
    triggeredBy('emitStockChanged()')
}
~~~

Có **hai tên khác nhau**:

- `emitStockChanged()` là method **trên producer base test**. Generated producer test gọi method này.
- `stock_changed` là **label của message stub**. Consumer test có thể gọi `StubTrigger.trigger("stock_changed")` để yêu cầu Stub Runner phát sự kiện mô phỏng.

**Consumer test không cần gọi method `emitStockChanged()` từ producer.** Nó chỉ cần stub artifact đúng version và tích hợp messaging của Stub Runner.

### Stub Trigger API

Spring Cloud Contract có interface:

~~~java
import org.springframework.cloud.contract.stubrunner.StubTrigger;
~~~

Các cách dùng thường gặp:

~~~java
stubTrigger.trigger("stock_changed");

// Khi có nhiều stub trùng label, chọn producer rõ ràng:
stubTrigger.trigger("com.example:inventory-producer", "stock_changed");

// Có thể kiểm tra các label được load:
stubTrigger.labels();
~~~

Một số version cho phép dùng artifactId đơn thay vì `groupId:artifactId` trong đối số đầu của overload hai tham số. Với hệ thống nhiều producer, nên chọn cách định danh đầy đủ để tránh kích hoạt nhầm sự kiện.

### Ví dụ consumer test skeleton

~~~java
package com.example.checkout.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class StockChangedConsumerContractTest {

    @Autowired
    StubTrigger stubTrigger;

    @Test
    void triggersStockChangedMessage() {
        boolean triggered = stubTrigger.trigger(
            "com.example:inventory-producer",
            "stock_changed"
        );
        assertThat(triggered).isTrue();

        // Đợi Checkout event handler xử lý sự kiện.
        // Assert projection/logic thật của Checkout phản ánh quantity=0.
        // Không chỉ assert triggered==true rồi coi là đã kiểm tra consumer.
    }
}
~~~

Đây là **skeleton**: chưa có lớp projection/consumer thật hoặc cấu hình test binder/broker để nhận message. Trong dự án, phải nối messaging destination với consumer handler và viết assertion lên trạng thái **sau khi xử lý**. `LOCAL` yêu cầu artifact stub ở Maven local repository; CI có thể dùng repository phù hợp và chế độ cấu hình khác.

`triggered==true` chỉ cho thấy Stub Runner tìm/đã kích hoạt label theo API, **không chứng minh consumer xử lý đúng**. Cần thêm assertion thực sự, ví dụ projection của SKU-101 chuyển thành `OUT_OF_STOCK`.

## 11. Consumer test và xử lý bất đồng bộ

Messaging thường bất đồng bộ, nên trạng thái consumer có thể chưa thay đổi ngay sau `stubTrigger.trigger(...)`. Một test viết:

~~~java
stubTrigger.trigger("stock_changed");
assertThat(stockProjection.find("SKU-101").quantity()).isEqualTo(0);
~~~

có thể **flaky** nếu handler xử lý sự kiện ở thread khác hoặc qua broker. Hãy dùng cơ chế chờ có giới hạn, không dùng `Thread.sleep` cố định nếu có lựa chọn tốt hơn.

Ví dụ pseudocode với Awaitility (cần dependency test phù hợp):

~~~java
boolean triggered = stubTrigger.trigger(
    "com.example:inventory-producer",
    "stock_changed"
);
assertThat(triggered).isTrue();

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(
            stockProjection.find("SKU-101").quantity()
        ).isEqualTo(0)
    );
~~~

Cần import `org.awaitility.Awaitility.await`, `java.time.Duration` và các assertion tương ứng. `stockProjection` chỉ là ví dụ cho code consumer thật. Mục tiêu là **đợi điều kiện nghiệp vụ đạt được**, với timeout hợp lý, thay vì ngủ một khoảng mơ hồ rồi hy vọng message đã xử lý xong.

### Tính lặp lại khi test

- Xóa hoặc reset message/state cũ trước mỗi test.
- Dùng key dữ liệu `SKU-101` và quantity minh họa nhất quán.
- Tránh chia sẻ topic/destination giữa các test không có cơ chế phân biệt hoặc isolation.
- Nếu consumer xử lý trùng event, cần test idempotency riêng.
- Tránh sleep quá dài làm pipeline CI chậm mà vẫn có nguy cơ race condition.

## 12. Destination và integration: tại sao nhận không được message?

`outputMessage.sentTo` không nên xem là một chuỗi tùy ý. Spring Cloud Contract giải thích destination theo messaging integration:

- Với **Spring Cloud Stream/Spring Integration**, hệ thống thường thử giải quyết theo destination của binding/channel, rồi tới tên channel theo cơ chế tương ứng.
- Với **Apache Camel**, tên có thể mang cú pháp component URI, ví dụ `activemq:output`.
- Với **JMS/AMQP/Kafka**, queue, topic, binder, broker và destination semantics phụ thuộc framework/adapter đã cấu hình.

Vì vậy, trong ví dụ:

~~~groovy
outputMessage {
    sentTo('stock-events')
}
~~~

nếu component gửi tới `stockChanged-out-0` được cấu hình destination khác, producer test có thể **không nhận được message** dù publisher đã gọi `send(...)` thành công.

### Checklist cấu hình message routing

1. `StreamBridge.send(...)` đang dùng binding name nào?
2. Binding đó trỏ `destination` nào trong test profile?
3. `sentTo(...)` có giải quyết đúng đích theo messaging adapter không?
4. Test có sử dụng **test binder** hay broker thật?
5. Header `contentType` có được converter thiết lập nhất quán không?
6. Destination có message tồn dư từ test khác không?
7. Nếu dùng broker thật, queue/topic có tồn tại và có quyền subscribe/publish không?

**Không giải quyết lỗi destination bằng cách đổi `sentTo` thành một nơi ngẫu nhiên chỉ để test xanh.** Contract phải phản ánh đúng giao diện mà consumer đăng ký nhận.

### Có nhiều framework messaging trên classpath

Nếu ứng dụng vừa có Spring Cloud Stream, Spring Integration hoặc các thư viện messaging khác, Stub Runner có thể cần được chỉ rõ integration nào hoạt động. Tài liệu Spring Cloud Contract có các property để bật/tắt những adapter tương ứng. Nếu tích hợp không phù hợp, message stub có thể được route sai hoặc không khởi tạo được.

Cần xem dependency, cấu hình của **phiên bản dự án** và log Stub Runner; không mặc định “có mọi messaging starter thì Stub Runner tự chọn đúng”.

## 13. Payload và headers: cố định cái gì, matcher cái gì?

Hợp đồng nên mô tả những trường mà consumer thực sự cần. Với `StockChanged`, giả sử Checkout phụ thuộc:

| Trường | Giá trị minh họa | Mức độ ràng buộc đề xuất |
|---|---|---|
| `eventType` | `StockChanged` | Cố định theo loại sự kiện |
| `sku` | `SKU-101` | Giá trị mẫu cụ thể hoặc định dạng ID nếu có nhiều SKU |
| `quantity` | `0` | Number; kiểm tra nhánh hết hàng |
| `eventId` | `evt-1001` | Mẫu ổn định ở stub; định dạng/ràng buộc ở producer nếu ID động |
| `occurredAt` | `2026-01-15T08:30:00Z` | Mẫu ổn định + định dạng/clock kiểm soát ở producer |
| Header `contentType` | `application/json` | Cần tương thích converter của consumer |
| Header `eventType` | `StockChanged` | Kiểm chứng nếu consumer route theo header |

Nếu producer sinh UUID hoặc timestamp khác nhau, không nên cố định chúng trong assertion producer trừ khi test kiểm soát generator/clock. Spring Cloud Contract Groovy DSL có cơ chế **consumer/producer values** và matcher; YAML có schema matcher riêng. Việc đặt matcher phải theo **phía cần kiểm chứng** (request/response hoặc input/output messaging), không chỉ thay mọi thứ bằng `.*`.

**Ví dụ phản tác dụng:** chỉ kiểm tra `eventType` rồi bỏ qua `quantity`, trong khi Checkout dựa vào nó để chặn đặt hàng. Test vẫn có thể xanh khi producer đổi `quantity` từ number thành string.

### Thông điệp rỗng hoặc lỗi

Một số nghiệp vụ cần kiểm chứng:

- Không phát event khi cập nhật không làm thay đổi trạng thái.
- Không phát event khi transaction thất bại.
- Không phát duplicate event cho một operation idempotent.
- Phát message đúng schema khi quantity về 0.
- Giữ compatibility với consumer phiên bản cũ.

Không phải mọi ràng buộc “**không phát**” hoặc về transaction/dedup đều được một contract `triggeredBy + outputMessage` đơn lẻ diễn đạt đầy đủ. Hãy thêm service/integration tests cho trạng thái, transaction/outbox và negative cases.

## 14. Các lỗi thường gặp khi dùng triggeredBy

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Generated test báo không tìm thấy `emitStockChanged()` | Base class sai hoặc method không truy cập được | Kiểm tra `baseClassForTests`, package, chữ ký method và generated class |
| Method trigger chạy nhưng test không nhận event | Method không gọi publisher, destination sai hoặc binder chưa đúng | Log publisher/binder, `sentTo`, cấu hình binding |
| Test lỗi bean `ContractVerifierMessaging`/message verifier | Thiếu `@AutoConfigureMessageVerifier` hoặc adapter/dependency | Kiểm tra base test và classpath |
| Test nhận event khác fixture | Destination chứa message cũ hoặc producer phát nhiều message | Cô lập/clear state, kiểm tra số message và khóa định danh |
| Test chờ rồi timeout | Không publish, topic sai, listener chưa đăng ký hoặc quá trình async chưa hoàn tất | Theo dấu lời gọi trigger và receive, cấu hình timeout |
| Stub Trigger không tìm thấy label | Label thiếu/sai, artifact stub cũ | Xem `labels()`, nội dung artifact và version |
| `trigger(...)` trả true nhưng consumer không thay đổi trạng thái | Stub được kích hoạt nhưng consumer không lắng nghe/handler lỗi | Kiểm tra binder/broker, consumer handler và assertion trạng thái |
| Consumer nhận `quantity` là string | Quote sai YAML hoặc serialization khác cam kết | Đọc payload thực, kiểm tra kiểu và contract |
| Producer test xanh nhưng consumer lỗi | Contract mới phá vỡ schema cũ hoặc consumer dùng stub khác revision | Chạy consumer test với candidate stub, compatibility review |
| Local test chạy, CI không chạy | Dependency test binder/repository/profile thiếu | So sánh cấu hình CI và log plugin/binder |
| Event được phát hai lần khi test chạy song song | Cùng destination/state hoặc trigger không idempotent | Cô lập dữ liệu và kiểm tra thao tác bên dưới |

### Phân biệt bốn loại lỗi

1. **Compile/sinh test lỗi:** Method trigger hoặc base class chưa kết nối đúng.
2. **Receive timeout:** Trigger chạy nhưng chưa có message đến destination verifier quan sát.
3. **Assertion lỗi:** Đã nhận message nhưng field/header khác hợp đồng.
4. **Consumer handler lỗi:** Stub đã phát sự kiện nhưng consumer không xử lý đúng.

Chẩn đoán theo loại sẽ nhanh hơn việc thay đổi ngẫu nhiên `sentTo`, label hoặc tăng timeout.

## 15. Đưa kiểm thử message producer và consumer vào CI

Một pipeline thực tế nên có luồng chứng cứ từ contract đến hai phía:

~~~mermaid
flowchart TD
    A["PR thay Groovy/YAML message contract"] --> B["Kiểm tra DSL, label, destination"]
    B --> C["Sinh generated producer tests"]
    C --> D["Chạy base method triggeredBy"]
    D --> E{"Nhận event + assert body/headers?"}
    E -->|Không| F["Chặn merge, điều tra code/binder/schema"]
    E -->|Có| G["Đóng gói versioned stub artifact"]
    G --> H["Consumer Stub Runner dùng candidate stub"]
    H --> I["trigger(label) + test consumer handler"]
    I --> J{"Consumer test đạt?"}
    J -->|Không| K["Sửa contract/consumer, lên kế hoạch migration"]
    J -->|Có| L["Review tương thích và phát hành"]
~~~

Các bước tối thiểu:

1. **Preflight contract:** `input.triggeredBy` có method tồn tại; `label` và `sentTo` thể hiện đúng giao diện.
2. **Generated test discovery:** plugin tìm được contract và thực sự chạy test; không coi build xanh khi có 0 test là thành công.
3. **Producer verification:** method trigger gọi code producer; message tới đúng destination và assertion body/header đạt.
4. **Stub packaging:** phát hành stub chứa định nghĩa contract messaging từ đúng revision; tránh ghi đè artifact bất biến.
5. **Consumer verification:** Stub Runner tải đúng artifact, trigger bằng label và kiểm tra consumer handler với timeout có giới hạn.
6. **Compatibility review:** thay topic, key, header, field, kiểu JSON hoặc event name phải đánh giá các consumer đang chạy.
7. **Tracing:** lưu commit DSL, commit producer, artifact version và kết quả consumer test.

### Versioning quan trọng

Consumer test phải chỉ rõ mình dùng stub nào, chẳng hạn phiên bản `com.example:inventory-producer:1.0.0:stubs` nếu đây là tọa độ đã phát hành. Không chỉ test với một alias `latest` không truy vết được rồi kết luận đã xác minh candidate version.

Khác với HTTP stub thường biểu diễn request/response trong WireMock mapping, **message stub cần contract definition và messaging route hỗ trợ** để Stub Runner kích hoạt event. Vì vậy nên kiểm tra **artifact stub thực tế có chứa contract** và label mong muốn, không chỉ tìm JSON WireMock mapping HTTP.

## 16. Bài tập thực hành: sửa contract không phát sự kiện

### Tình huống

Inventory có service:

~~~java
public void publishOutOfStock(String sku) {
    publisher.publishStockChanged(sku, 0);
}
~~~

Nhóm viết contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_out'
    input {
        triggeredBy('triggerStockOut()')
    }
    outputMessage {
        sentTo('wrong-destination')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: '0'
        )
    }
}
~~~

Base class của nhóm:

~~~java
public void triggerStockOut() {
    // Chưa gọi InventoryService hoặc publisher.
}
~~~

Trong khi producer thực sự gửi message tới destination `stock-events` và consumer mong `quantity` là **number**.

**Câu hỏi:**

1. Có bao nhiêu lỗi khiến test không kiểm chứng đúng hành vi?
2. Generated producer test sẽ làm gì khi method trigger trống?
3. Nếu sửa method nhưng giữ destination sai, chuyện gì xảy ra?
4. Nếu sửa destination nhưng giữ `quantity: '0'`, rủi ro gì?
5. Consumer test phải gọi `triggerStockOut()` hay `StubTrigger.trigger("stock_out")`?

### Gợi ý lời giải

**Ít nhất ba lỗi cần sửa:**

1. Method `triggerStockOut()` chưa gọi nghiệp vụ producer thật.
2. `sentTo('wrong-destination')` không khớp destination `stock-events`.
3. `quantity: '0'` là string, trong khi consumer mong number `0`.

Phiên bản contract sau sửa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_out'
    input {
        triggeredBy('triggerStockOut()')
    }
    outputMessage {
        sentTo('stock-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Base test method có thể dùng:

~~~java
@Autowired
private InventoryService inventoryService;

public void triggerStockOut() {
    inventoryService.publishOutOfStock("SKU-101");
}
~~~

Cần bảo đảm `InventoryService` thực sự có phương thức `publishOutOfStock` trong dự án học, cùng publisher/binder đã cấu hình và trạng thái test phù hợp.

**Cách đọc kết quả:**

- Nếu method trigger trống, generated test thường không nhận được message và có thể timeout/thất bại.
- Nếu destination sai, verifier có thể chờ sai nơi dù publisher đã phát event.
- Nếu `quantity` sai kiểu, ngay cả khi event tới, assertion/consumer deserialize có thể không đúng hợp đồng.
- Ở phía consumer, dùng `StubTrigger.trigger("stock_out")` để phát event giả lập. Không gọi method Java từ producer.
- Consumer test cần chứng minh logic handler, không dừng ở việc `trigger(...)` trả `true`.

### Bài tập nâng cao

Đổi sự kiện thành `StockChanged` có thêm `eventId` và `occurredAt` do producer sinh tự động. Hãy đề xuất:

- Giá trị mẫu ổn định cho stub.
- Matcher hoặc test kiểm tra format ở producer.
- Các trường consumer nào đang phụ thuộc.
- Cách tránh flaky khi consumer xử lý async.
- Cách kiểm soát idempotency và event duplication trong các test bổ sung.

## 17. Checklist trước khi phê duyệt message contract

- [ ] Producer/consumer và ý nghĩa nghiệp vụ của event được xác định rõ.
- [ ] `input.triggeredBy` mô tả method khởi phát phù hợp; method tồn tại và truy cập được.
- [ ] Base test được plugin chọn đúng, có `@AutoConfigureMessageVerifier`.
- [ ] Trigger method gọi code producer thật thay vì gửi fixture giả bỏ qua implementation.
- [ ] Messaging adapter/binder/destination tương ứng với `outputMessage.sentTo`.
- [ ] `outputMessage.body` giữ đúng kiểu dữ liệu và các field consumer phụ thuộc.
- [ ] `outputMessage.headers` bảo vệ header và content type cần thiết.
- [ ] Generated test thực sự chạy, nhận đúng event và assert payload/header.
- [ ] `label` được đặt ổn định và không trùng gây nhầm giữa các stub.
- [ ] Stub artifact chứa contract message từ đúng revision và được version rõ ràng.
- [ ] Consumer test sử dụng `StubTrigger.trigger(label)` và assert handler/state thật.
- [ ] Test async có timeout có giới hạn; trạng thái/queue được cô lập.
- [ ] Thay đổi destination/schema/version được đánh giá với consumer cũ.
- [ ] CI lưu kết quả producer và consumer test gắn với cùng contract revision.

## 18. Ghi nhớ và tài liệu tham khảo

**`triggeredBy` là cách để generated producer test gọi hành động khởi phát sự kiện, không phải tên topic và cũng không phải lời gọi của consumer.** Đặt nó trong `input` của messaging contract, chỉ ra output bằng `outputMessage.sentTo`, `body` và `headers`. Base test phải có method được khai báo, gọi vào code producer thật và thiết lập messaging verifier/binder phù hợp.

Ở phía consumer, **`label` cùng `StubTrigger.trigger(...)`** giúp Stub Runner phát sự kiện giả lập để kiểm tra handler. Hai phía cần dùng cùng version hợp đồng và stub, còn CI phải chạy test thực sự thay vì chỉ tạo file.

Tài liệu tham khảo chính thức:

- [Spring Cloud Contract – Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): `triggeredBy`, `outputMessage`, các messaging integrations và `StubTrigger`.
- [Spring Cloud Contract – YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): cấu trúc YAML `input.triggeredBy` và `outputMessage`.
- [Spring Cloud Contract – Getting Started](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): cách sinh test, dùng base class và triển khai producer–consumer contract.

Lưu ý cuối: một contract kiểm chứng sự kiện được phát với payload/header đúng **không tự chứng minh** transaction outbox, broker delivery guarantees, retry, thứ tự event hay tính idempotent trong production. Các tính chất đó cần thêm kiểm thử tầng service, integration và hạ tầng messaging tương ứng.
