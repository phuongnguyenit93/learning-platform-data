# Hợp đồng messaging và dữ liệu phục vụ Stub Runner

Trong **Spring Cloud Contract**, một hợp đồng HTTP thường tạo ra **WireMock mapping** để consumer giả lập lời gọi REST. Với **messaging**, câu chuyện khác: producer phát thông điệp vào một destination, còn consumer nhận thông điệp qua broker hoặc kênh tích hợp. Một **messaging stub** không đơn giản là HTTP endpoint trả JSON. **Stub Runner** cần đọc được dữ liệu hợp đồng, biết **kịch bản nào cần kích hoạt**, **message sẽ được gửi tới đâu**, **headers** và **payload mẫu** cần phát, đồng thời có **messaging adapter** kết nối với hạ tầng test.

Bài thuộc chương **Sinh và đóng gói stub** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun hướng dẫn viết hợp đồng producer–consumer bằng **Groovy/YAML DSL**, sinh **producer verification tests**, tạo và phát hành artifact **stubs**, sử dụng **Stub Runner** và đưa toàn bộ quy trình vào CI để phát hiện thay đổi giao tiếp không tương thích. Trọng tâm ở đây là **nội dung messaging được đóng gói trong stub artifact** và cách consumer sử dụng nội dung đó, chứ không chỉ cách định nghĩa message trong DSL.

Sau bài học, bạn có thể phân biệt messaging contract với HTTP mapping, tổ chức một sự kiện có `label`/destination/payload/headers rõ ràng, xây dựng quy trình producer verification → đóng gói `stubs` → Stub Runner consumer test, và chẩn đoán trường hợp artifact tải thành công nhưng consumer **không nhận được message**.

## 1. Messaging stub khác HTTP stub ở điểm nào?

Giả sử có **Order Service** (producer) và **Billing Service** (consumer). Sau khi đơn hàng được tạo thành công, Order Service phát sự kiện `OrderCreated` tới destination `orders.created`. Billing lắng nghe sự kiện và lập hóa đơn.

~~~mermaid
flowchart TD
    A["Order Service: tạo đơn"] --> B["Phát OrderCreated"]
    B --> C["orders.created trên broker/binder"]
    C --> D["Billing Service nhận và xử lý"]
    E["Messaging Contract"] --> F["Generated producer test"]
    F --> B
    E --> G["Stub artifact chứa dữ liệu contract"]
    G --> H["Stub Runner + messaging adapter"]
    H --> C
~~~

Hai chế độ kiểm thử phải được hiểu riêng:

| Đặc điểm | HTTP stub | Messaging stub |
| --- | --- | --- |
| Tương tác giả lập | Consumer gửi HTTP request; stub trả status/headers/body. | Consumer nhận message mẫu; test kích hoạt và quan sát message qua kênh messaging. |
| Dữ liệu trung tâm | Method, URL, request matcher và response. | `label`, destination, headers, payload và điều kiện input/trigger. |
| Công cụ giả lập thông thường | WireMock HTTP server. | Stub Runner kết hợp messaging adapter/integration phù hợp. |
| Cổng HTTP | Có thể cần một port, ví dụ 8089. | Không bắt buộc một HTTP port chỉ để phát message; cần một kênh/binder được cấu hình. |
| Test consumer kiểm | Client gửi request và xử lý HTTP response. | Listener/deserializer/business handler nhận và xử lý event. |
| Điều không tự chứng minh | Producer thật đã trả HTTP đúng nếu bỏ qua verification. | Producer thật đã publish đúng, broker bảo đảm delivery/retry/order nếu thiếu verification/integration tests. |

**Điểm mấu chốt:** artifact có thể chứa **messaging contracts nhưng không có mapping WireMock cho những kịch bản đó**. Điều này không nhất thiết là lỗi đóng gói. Cần kiểm các **file contract messaging và khả năng Stub Runner đọc/trigger chúng**, thay vì chỉ đếm file JSON trong thư mục `mappings`.

## 2. Phân biệt dữ liệu nào thuộc contract và dữ liệu nào thuộc test

Một producer event có các thành phần:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| `label` | `orderCreatedV1` | Định danh kịch bản để Stub Runner có thể kích hoạt message stub. |
| `input` | `triggeredBy('publishOrderCreated()')` | Nêu cách generated producer test kích hoạt producer phát message. |
| `sentTo` | `orders.created` | Destination logic nơi output message phải được phát/quan sát. |
| `headers` | `contentType=application/json`, `eventType=OrderCreated` | Metadata mà consumer có thể dùng để route/parse event. |
| `body` | JSON có `eventId`, `orderId`, `amountMinor` | Payload mẫu mà consumer xử lý và producer phải đáp ứng. |
| `matchers`, nếu có | `eventId` thỏa một định dạng quy định | Cho phép giá trị producer sinh động nhưng giữ ràng buộc quan trọng. |

Ngoài hợp đồng, **test setup** phải có:

- Ở **producer**: phương thức hoặc message input để kích hoạt hành vi, fixture, dịch vụ gửi message, kênh thu thập output và cấu hình Contract Verifier messaging.
- Ở **consumer**: listener nhận đúng destination, message converter, cơ chế để Stub Runner đưa message vào test binder/broker, và assertion về kết quả xử lý.
- Trong **CI**: build producer, artifact stub theo version, repository, quyền tải, và thứ tự chạy kiểm thử.

**Đừng nhúng thông tin môi trường tạm thời vào payload** chỉ để Stub Runner chạy được: địa chỉ broker trên một máy cụ thể, token thật, tên topic sinh ngẫu nhiên không được consumer biết hoặc dữ liệu người dùng thật. Dữ liệu fixture phải xác định, không nhầm với địa chỉ hạ tầng của một môi trường.

## 3. Tình huống ví dụ: OrderCreated v1

Giả sử hai bên thống nhất một sự kiện `OrderCreated` mang các trường:

~~~json
{
  "eventId": "evt-00042",
  "orderId": "ORD-1042",
  "amountMinor": 125000,
  "currency": "VND",
  "occurredAt": "2026-01-15T10:20:30Z"
}
~~~

Message có metadata:

~~~text
destination: orders.created
contentType: application/json
eventType: OrderCreated
schemaVersion: 1
~~~

Quy ước nghiệp vụ:

1. `eventId` dùng để phân biệt một sự kiện, có thể hỗ trợ xử lý trùng lặp.
2. `orderId` xác định đơn hàng mà Billing phải lập hóa đơn.
3. `amountMinor` là số nguyên theo **đơn vị nhỏ nhất được hệ thống quy định**, không phải một số thực mơ hồ; `currency` làm rõ đơn vị tiền.
4. `occurredAt` là chuỗi thời điểm UTC ở dạng đã thống nhất.
5. `eventType` và `schemaVersion` là metadata **consumer thật sự dùng**; nếu consumer không dùng chúng thì không nên tự thêm assertion vô nghĩa.

Giá trị như `evt-00042`, `ORD-1042` là **mẫu** để test ổn định; chúng không có nghĩa producer trong production được phép phát cùng `eventId` cho mọi đơn. Nếu producer tạo ID động, dùng matcher hợp lý ở phía producer verification và một giá trị cố định ở phía stub consumer.

## 4. Định nghĩa hợp đồng messaging bằng Groovy DSL

Tạo tệp tại `src/test/resources/contracts/messages/order_created.groovy` trong repository **producer**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    description 'Phát OrderCreated v1 cho Billing khi tạo đơn thành công'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-1042',
            amountMinor: 125000,
            currency: 'VND',
            occurredAt: '2026-01-15T10:20:30Z'
        )
    }
}
~~~

**Ý nghĩa của mỗi phần khi sinh test và stub:**

- `label 'orderCreatedV1'`: tên kịch bản để test consumer có thể yêu cầu Stub Runner **phát sự kiện mẫu**. Nên đặt tên duy nhất, có ý nghĩa và ổn định qua các lần build.
- `triggeredBy('publishOrderCreated()')`: tên lệnh mà **generated producer test** gọi để làm producer thực phát sự kiện. Nó **không phải** tên method mà consumer test phải gọi.
- `sentTo('orders.created')`: destination mà generated producer test kỳ vọng producer gửi message và messaging stub dùng để định tuyến payload mẫu; adapter/binder phải biết ánh xạ đích này.
- `headers`: dữ liệu metadata. Cần xác minh header được giữ/convert đúng kiểu trên messaging transport thực tế nếu consumer phụ thuộc vào chúng.
- `body`: dữ liệu sự kiện được kiểm ở producer và được dùng làm message mẫu cho consumer.

Ví dụ này dùng **payload tĩnh** để thấy rõ dữ liệu cần đóng gói. Khi thêm matcher cho ID/timestamp động, cần giữ **giá trị ví dụ phía consumer** và **matcher phía producer** nhất quán, không dùng regex quá rộng hoặc giá trị mẫu nằm ngoài miền quy định.

### 4.1. Khi event ID do producer tạo động

Trong Groovy DSL, có thể tách hai góc nhìn ở **output message body** bằng `consumer(...)` và `producer(...)`. Một biến thể minh họa cho `eventId`:

~~~groovy
body(
    eventId: $(consumer('evt-00042'),
               producer(regex('evt-[0-9]{5}'))),
    orderId: 'ORD-1042',
    amountMinor: 125000,
    currency: 'VND',
    occurredAt: '2026-01-15T10:20:30Z'
)
~~~

Từ góc nhìn **consumer stub**, `evt-00042` là một mẫu cụ thể để test có thể quan sát. Từ góc nhìn **producer verification**, regex giúp kiểm ID thực theo định dạng công bố mà không buộc producer tạo chính xác cùng ID trong production. Cần xác nhận phiên bản Spring Cloud Contract hiện tại hỗ trợ kiểu matcher/serialization này trên messaging và kiểm mã test sinh ra.

**Không coi một regex là bảo đảm tính duy nhất** của `eventId`. Tính không trùng qua nhiều lần phát phải được kiểm bằng business/integration tests thích hợp.

## 5. Hợp đồng YAML: cùng ý định, cần xác nhận schema theo phiên bản

Nếu nhóm dùng **YAML DSL**, có thể diễn đạt cùng dữ liệu dưới dạng:

~~~yaml
description: Phát OrderCreated v1 cho Billing
label: orderCreatedV1
input:
  triggeredBy: publishOrderCreated()
outputMessage:
  sentTo: orders.created
  headers:
    contentType: application/json
    eventType: OrderCreated
    schemaVersion: 1
  body:
    eventId: evt-00042
    orderId: ORD-1042
    amountMinor: 125000
    currency: VND
    occurredAt: "2026-01-15T10:20:30Z"
~~~

**Lưu ý:** đây là cách trình bày **ý định của một messaging contract bằng YAML**; khả năng hỗ trợ, tên khóa và cấu trúc matcher cần được xác nhận bằng **phiên bản Spring Cloud Contract mà dự án đang dùng**. Một tài liệu YAML parse được không đủ để bảo đảm Contract Verifier sẽ hiểu và sinh ra stub như mong đợi. Hãy chạy plugin, kiểm generated producer test và thử trigger từ Stub Runner.

Chỉ để **một DSL có hiệu lực** cho cùng sự kiện trong một lượt build. Nếu để cả bản Groovy và YAML tương đương trong đường dẫn được plugin nạp, có thể tạo test/stub trùng lặp hoặc hai bản bị cập nhật lệch nhau.

## 6. Producer verification: làm sao chứng minh sự kiện đã được phát?

Contract Verifier không tự chạy nghiệp vụ producer chỉ từ `outputMessage`. Với hợp đồng `triggeredBy`, generated test cần gọi đúng method và **thu được message thực** mà ứng dụng phát ra.

Giả sử Order Service dùng **Spring Cloud Stream**. Có thể có một publisher:

~~~java
package com.acme.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderEventPublisher {
    private final StreamBridge bridge;

    public OrderEventPublisher(StreamBridge bridge) {
        this.bridge = bridge;
    }

    public void publishOrderCreated() {
        Message<OrderCreated> message = MessageBuilder
            .withPayload(new OrderCreated(
                "evt-00042", "ORD-1042", 125000L,
                "VND", "2026-01-15T10:20:30Z"))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventType", "OrderCreated")
            .setHeader("schemaVersion", 1)
            .build();

        boolean accepted = bridge.send("ordersCreated-out-0", message);
        if (!accepted) {
            throw new IllegalStateException("Cannot publish OrderCreated");
        }
    }
}
~~~

Ví dụ này giả định có Java record `OrderCreated` gồm `eventId`, `orderId`, `amountMinor`, `currency`, `occurredAt`, cùng các dependencies Spring Cloud Stream tương thích. `StreamBridge.send(...)` dùng **tên binding** trong ứng dụng, không nhất thiết chính là tên topic/queue ngoài broker.

Cấu hình mẫu ánh xạ binding sang destination:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        ordersCreated-out-0:
          destination: orders.created
          content-type: application/json
~~~

Lớp **base test** để generated test gọi trigger:

~~~java
package com.acme.orders;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class MessageContractTestBase {
    @Autowired
    private OrderEventPublisher publisher;

    public void publishOrderCreated() {
        publisher.publishOrderCreated();
    }
}
~~~

**Quan trọng:** phần base test này **mới cung cấp trigger**, chưa phải cấu hình messaging verification hoàn chỉnh. Dự án còn cần **MessageVerifier, test binder hoặc messaging adapter** để Contract Verifier quan sát output message, theo công cụ và phiên bản Spring Cloud Contract đang dùng. Nếu không có adapter thích hợp, generated test có thể không tìm thấy message dù method publisher được gọi.

### 6.1. Test phải kiểm đúng tầng

Một generated producer test messaging có ý nghĩa:

~~~text
1. Chuẩn bị fixture cho Order Service
2. Gọi publishOrderCreated() của base test
3. Chờ message ở destination orders.created
4. Đối chiếu headers eventType, schemaVersion, contentType
5. Đối chiếu payload OrderCreated theo body/matcher của contract
~~~

Đây là **mô tả luồng**, không phải mã Java nguyên văn plugin sinh ra. Nếu adapter nhận message **trước serialization**, một test xanh chưa chứng minh bytes gửi lên Kafka/RabbitMQ production đúng định dạng. Khi consumer phụ thuộc vào wire schema, hãy thêm bài test codec/transport thực tế.

## 7. Sinh và đóng gói artifact stubs

Khi hợp đồng đã có, producer dùng Contract Verifier plugin để sinh kiểm thử và tài nguyên stub. Ví dụ cấu hình Maven plugin (một phần của `pom.xml`):

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.1.5</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>com.acme.orders.MessageContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

`4.1.5` là **ví dụ một phiên bản của dòng 4.1.x**, không phải phiên bản được yêu cầu cho mọi dự án; chọn plugin/dependencies theo BOM/release train tương thích với Spring Boot và Spring Cloud đang dùng. Dự án cần dependencies Contract Verifier, Spring Boot Test, Spring Cloud Stream và messaging test adapter/binder phù hợp. Không dùng tùy tiện `testMode=MOCKMVC` để thay cho môi trường thu thập message: HTTP test mode và messaging verification là hai việc khác nhau.

Ở producer Maven đã cấu hình đúng, workflow tham khảo:

~~~shell
mvn clean verify
~~~

Sau khi xác nhận producer verification đạt, tạo/cài artifact vào local:

~~~shell
mvn install
~~~

Trên CI/release, sau bước verification và các cổng chất lượng khác, phát hành artifact vào repository đã chọn bằng quy trình Maven deploy/publishing của dự án:

~~~shell
mvn deploy
~~~

**Không biến chuỗi lệnh này thành yêu cầu chạy ba lần trong mọi CI**. Tùy lifecycle và pipeline, `install` hoặc `deploy` có thể chạy lại các bước test. Mấu chốt là **generated producer tests phải thực thi và đạt trước khi một bản stub được xem là đáng tin**, chứ không phải cố gắng xuất JAR bằng mọi giá. Không dùng `-DskipTests` trong bước phát hành có mục tiêu chứng minh producer đã đúng hợp đồng.

### 7.1. Phân biệt JAR ứng dụng và JAR stub

Thông thường producer có thể tạo:

~~~text
order-service-1.0.0.jar
order-service-1.0.0-stubs.jar
~~~

Tọa độ Maven của stub:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.0.0
classifier = stubs
~~~

Viết gọn:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

**JAR ứng dụng** chứa code chạy của Order Service; **JAR stubs** chứa dữ liệu để consumer mô phỏng giao tiếp. Stub Runner dùng **artifact stub**, không cần khởi động nguyên ứng dụng producer để chạy message contract test của consumer.

## 8. Stub JAR messaging có những tài nguyên gì?

Spring Cloud Contract thường đặt dữ liệu stub dưới `META-INF` theo thông tin group/artifact/version. Một cấu trúc **minh họa** cho `order-service-1.0.0-stubs.jar`:

~~~text
order-service-1.0.0-stubs.jar
└── META-INF/
    └── com.acme/
        └── order-service/
            └── 1.0.0/
                ├── contracts/
                │   └── messages/
                │       └── order_created.groovy
                └── mappings/
                    └── ... (nếu module còn có hợp đồng HTTP)
~~~

**Cấu trúc thực tế có thể khác theo phiên bản/cấu hình packaging**; cần mở JAR đã được sinh để xác nhận. Điều đáng kiểm:

1. **Đúng artifact** với classifier `stubs`, groupId, artifactId, version như consumer yêu cầu.
2. Có **messaging contract** hoặc biểu diễn tương ứng được Stub Runner hỗ trợ; nội dung không bị loại khỏi bước đóng gói.
3. Contract có **label** `orderCreatedV1` và destination/payload/headers như đã thống nhất.
4. Nếu module cũng có HTTP contracts, JAR có thể chứa **WireMock mappings** cho HTTP. Nếu chỉ có messaging thì **không nhất thiết có HTTP mapping**.
5. Artifact có thể được tải trong chế độ `LOCAL`/`REMOTE` của consumer; không chỉ tồn tại file `.jar` không rõ tọa độ.

Một lỗi thường gặp là kiểm `stubs.jar` chỉ bằng cách đếm file `mappings/*.json`. Với messaging, **đếm 0 mapping không chứng minh hợp đồng messaging bị thiếu**. Phải kiểm tài nguyên contract và thử **trigger** trên một test consumer có messaging integration.

### 8.1. Dữ liệu nào cần để Stub Runner phát message?

| Dữ liệu | Có trong contract | Consumer/Stub Runner dùng để làm gì |
| --- | --- | --- |
| `label=orderCreatedV1` | Có | Chọn kịch bản cụ thể khi test yêu cầu phát event. |
| `outputMessage.sentTo=orders.created` | Có | Chỉ ra nơi adapter phải đưa message tới. |
| `outputMessage.body` | Có | Tạo payload ví dụ mà listener của consumer sẽ nhận. |
| `outputMessage.headers` | Có | Cung cấp metadata cho conversion/routing/assertion. |
| `input.triggeredBy` | Có | Chủ yếu phục vụ **producer generated test** kích hoạt hành vi; không phải REST URL của stub. |
| Broker hostname/port thực | Thường **không** nên hardcode trong contract | Đến từ cấu hình test binder/broker của consumer. |
| Consumer listener/function | **Không** | Do ứng dụng consumer cung cấp và test thực thi. |
| Queue/test probe và timeout | **Không** | Do fixture test consumer kiểm soát. |

Đừng xem `triggeredBy` là lệnh chạy phương thức của producer từ xa ở consumer test. Stub Runner **không khởi động producer**; nó sử dụng **dữ liệu output message đã đóng gói** để phát thông điệp giả qua adapter được cấu hình.

## 9. LOCAL, REMOTE và phiên bản stub

**LOCAL** phù hợp khi producer đã cài artifact vào Maven local và consumer test chạy trên cùng máy/môi trường:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

**REMOTE** phù hợp với CI của consumer trên máy/runner khác, khi stub đã được publish lên Maven repository:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/maven-releases"
)
~~~

`https://repo.example.org/maven-releases` là **địa chỉ giả minh họa**, không phải repository thực. Trong dự án, khai báo đúng URL, tài khoản/quyền đọc và bảo vệ credentials bằng CI secrets. Có thể cấu hình repository theo property bên ngoài thay vì hardcode.

**Tại sao ghim version?** Nếu consumer dùng một bản stub thay đổi ngầm, cùng commit consumer có thể pass hôm nay nhưng fail hôm sau mà không có thay đổi code. Ghim `1.0.0` hoặc dùng version được chọn có chủ đích giúp test **có thể tái lập** và truy nguyên producer commit. Nếu dùng phiên bản snapshot, phải chấp nhận và quản lý rủi ro mutable artifact theo chính sách CI.

Với **messaging-only**, consumer không nhất thiết cần cung cấp một HTTP port trong chuỗi `ids`. Điều nó cần là **messaging adapter/binder** được kết nối để event được đưa tới listener. Nếu consumer còn dùng HTTP stubs cùng artifact, các HTTP mappings có thể dùng một port tương ứng.

## 10. Stub Runner ở consumer: dùng label để phát sự kiện

Trong Billing Service, giả sử đã có một Spring Cloud Stream consumer nhận `OrderCreated` từ destination `orders.created`. Bài test cần **Stub Runner**, một **message adapter** phù hợp và cơ chế chờ kết quả từ listener.

Một test JUnit 5 minh họa:

~~~java
package com.acme.billing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingMessageContractTest {
    @Autowired
    private StubTrigger stubTrigger;

    @Autowired
    private BillingEventProbe probe;

    @Test
    void consumesOrderCreatedV1() {
        stubTrigger.trigger("orderCreatedV1");

        BillingOrderCreated received =
            probe.awaitEvent("evt-00042");

        assertThat(received.orderId()).isEqualTo("ORD-1042");
        assertThat(received.amountMinor()).isEqualTo(125000L);
        assertThat(received.currency()).isEqualTo("VND");
    }
}
~~~

Đây là **khung test minh họa**, không phải một class chạy độc lập: `BillingEventProbe`, `BillingOrderCreated` và `awaitEvent` cần được consumer triển khai; cần dependencies Stub Runner, Spring Cloud Stream messaging integration, một binder/test broker phù hợp và test setup chứa listener.

Chỉ gọi `stubTrigger.trigger(...)` **không tự bảo đảm** listener đã nhận. Phải cấu hình adapter để Stub Runner **gửi vào đúng destination mà Billing đăng ký**, và dùng assertion kiểm **tác động quan sát được**. `awaitEvent` phải có **timeout hữu hạn** để tránh test treo nếu binder/label sai.

### 10.1. Một listener và probe tối giản

Giả sử converter ở phía consumer ánh xạ JSON event thành record:

~~~java
package com.acme.billing;

public record BillingOrderCreated(
    String eventId,
    String orderId,
    long amountMinor,
    String currency,
    String occurredAt
) {}
~~~

Test probe có thể dùng `BlockingQueue` để ghi nhận sự kiện:

~~~java
package com.acme.billing;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class BillingEventProbe {
    private final BlockingQueue<BillingOrderCreated> events =
        new LinkedBlockingQueue<>();

    public void accept(BillingOrderCreated event) {
        events.offer(event);
    }

    public BillingOrderCreated awaitEvent(String eventId) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (System.nanoTime() < deadline) {
            BillingOrderCreated event;
            try {
                event = events.poll(100, TimeUnit.MILLISECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", e);
            }
            if (event != null && event.eventId().equals(eventId)) {
                return event;
            }
        }
        throw new AssertionError("No OrderCreated event: " + eventId);
    }
}
~~~

Một functional consumer Spring Cloud Stream có thể nối tới probe:

~~~java
@Configuration
class BillingConsumerConfig {
    @Bean
    Consumer<BillingOrderCreated> orderCreatedConsumer(
            BillingEventProbe probe) {
        return probe::accept;
    }
}
~~~

Cấu hình binding của consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderCreatedConsumer-in-0:
          destination: orders.created
          content-type: application/json
~~~

**Giới hạn của ví dụ:** đây là cách minh họa luồng **đích → converter → listener → probe**; với Spring Cloud Stream functional model, dự án cần cấu hình function definition nếu cần để binder xác định đúng consumer. Một số binder/test adapter dùng `Message<T>` thay vì chuyển thẳng thành DTO; khi đó phải đồng bộ kiểu function và converter. Không đưa `BillingEventProbe` dùng cho test vào service production nếu nó chỉ nhằm thu thập event thử nghiệm.

## 11. Nếu trigger không đến listener, kiểm những gì?

Một test consumer có thể tìm thấy artifact stub và nhận được `StubTrigger` bean, nhưng listener vẫn không nhận event. Hãy kiểm theo đường đi:

~~~mermaid
flowchart TD
    A["Consumer tải đúng artifact stubs?"] --> B["Messaging contract + label tồn tại?"]
    B --> C["Stub Runner messaging adapter bật và sẵn sàng?"]
    C --> D["Destination từ contract được ánh xạ đúng?"]
    D --> E["Binder/test broker giao message tới consumer?"]
    E --> F["Deserializer hiểu payload/contentType?"]
    F --> G["Listener thực thi business logic?"]
    G --> H["Probe/assertion nhận đúng sự kiện?"]
~~~

| Triệu chứng | Nguyên nhân đáng kiểm | Hướng điều tra |
| --- | --- | --- |
| Không tìm thấy stub artifact. | Sai group/artifact/version/classifier, chưa install/publish, repo không truy cập được. | Đối chiếu `ids` với tọa độ JAR và repository. |
| Không trigger được `orderCreatedV1`. | Contract không được đóng gói, label không tồn tại/trùng hoặc Stub Runner không đọc được dạng contract. | Mở JAR và kiểm contract, label, log khởi tạo Stub Runner. |
| Trigger được nhưng message không đến. | Chưa có messaging integration hoặc binder/test broker; destination không khớp. | Kiểm adapter, mapping `sentTo`, cấu hình binding/listener. |
| Message đến nhưng DTO null/sai. | Content-Type, converter hoặc field naming/serialization không khớp. | Kiểm raw payload, headers và cấu hình deserializer. |
| Test fail không ổn định. | Listener xử lý bất đồng bộ, timeout nhỏ, message cũ còn trong queue. | Dùng eventId riêng, fixture sạch, await có deadline, không dùng `sleep`. |
| Consumer nhận hai event. | Duplicate trigger hoặc event còn từ lần test trước. | Cô lập queue/destination, reset probe, kiểm idempotency. |

Không sửa hợp đồng để bỏ header/body quan trọng chỉ vì adapter test bị cấu hình sai. Cần phân biệt lỗi **packaging**, lỗi **wiring**, lỗi **serialization** và lỗi **consumer business logic**.

## 12. Trường hợp input message rồi mới có output message

Không phải mọi messaging contract đều được kích hoạt bằng một method trong base test. Một producer có thể **nhận message đầu vào** rồi **phát message đầu ra**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'invoiceRequestHandled'

    input {
        messageFrom('billing.invoice.request')
        messageBody(orderId: 'ORD-1042')
        messageHeaders {
            header('contentType', 'application/json')
        }
    }

    outputMessage {
        sentTo('billing.invoice.created')
        headers {
            header('contentType', 'application/json')
        }
        body(
            orderId: 'ORD-1042',
            invoiceStatus: 'CREATED'
        )
    }
}
~~~

Khác biệt so với `triggeredBy`:

- Ở producer test, cần **đưa một message input hợp lệ** vào kênh mà ứng dụng đang lắng nghe, rồi quan sát output.
- Ở consumer stub test, cần hiểu **hành vi stub khi nhận input message** và cách adapter đang hỗ trợ liên hệ input/output.
- Không được cho rằng `StubTrigger.trigger(label)` tự thực hiện một vòng xử lý broker production thực sự; khả năng mô phỏng phụ thuộc integration và phiên bản.

Với kịch bản phức tạp (request–reply messaging, transactional outbox, retry, dead-letter queue), nên bổ sung integration tests. Stub contract mô tả các trường hợp giao tiếp được chọn; nó không tự mô phỏng toàn bộ ngữ nghĩa delivery của broker.

## 13. Dữ liệu mẫu, matcher và tính tương thích của consumer

Một payload stub tốt phải **đủ cụ thể để consumer test kiểm được mã xử lý**, nhưng **không ngầm biến ví dụ thành giá trị duy nhất hợp lệ**.

| Trường | Mẫu stub | Ràng buộc có thể cần ở producer | Rủi ro nếu chỉ có mẫu |
| --- | --- | --- | --- |
| `eventId` | `evt-00042` | Định dạng, không rỗng; duy nhất theo chính sách hệ thống. | Producer có thể luôn phát cùng ID mà test một message không phát hiện. |
| `orderId` | `ORD-1042` | ID đúng schema và tương ứng đơn thực được tạo. | Consumer test không chứng minh order tồn tại. |
| `amountMinor` | `125000` | Số nguyên, miền cho phép, đơn vị tiền rõ. | Không phát hiện sai scale hoặc overflow ở giá trị biên. |
| `currency` | `VND` | Tập mã tiền được hỗ trợ. | Không kiểm consumer xử lý mã khác đúng nếu API cho phép nhiều loại. |
| `occurredAt` | `2026-01-15T10:20:30Z` | ISO timestamp theo hợp đồng; múi giờ/độ chính xác rõ. | Consumer có thể sai khi nhận offset/precision khác. |
| `schemaVersion` | `1` | Quy tắc version/giải mã. | Consumer có thể không xử lý bản v2. |

Trong **output message**, producer verification có thể sử dụng matcher để kiểm dữ liệu động; consumer stub nhận giá trị **mẫu tĩnh**. Điều này phù hợp vì Stub Runner chủ yếu **mô phỏng lời hứa**, không thực thi thuật toán tạo ID. Tuy nhiên, nếu contract body dùng sai kiểu JSON, consumer test có thể thất bại do converter hoặc, nguy hiểm hơn, chấp nhận dữ liệu khác với production.

### 13.1. Missing và null trong payload

Hai dạng:

~~~json
{"orderId":"ORD-1042","note":null}
~~~

~~~json
{"orderId":"ORD-1042"}
~~~

**không giống nhau** khi consumer phân biệt “xóa ghi chú” và “không gửi ghi chú”. Nếu converter producer được cấu hình lược bỏ giá trị null, wire payload có thể không còn tương đương contract. Một test messaging chỉ quan sát object trước serialization có thể bỏ qua sai biệt đó; cần **test serializer/transport** khi field presence là điều consumer phụ thuộc.

### 13.2. Header cũng là dữ liệu hợp đồng

Đặc biệt với messaging, consumer có thể route theo `eventType` hoặc dùng `schemaVersion` để chọn decoder. Một message đúng body nhưng thiếu header có thể không bao giờ đến đúng handler.

Với Spring Cloud Stream/Kafka/RabbitMQ, kiểu/giá trị header có thể được chuyển đổi. Khi header là yêu cầu hợp đồng, cần kiểm:

1. Header có được tạo trước publish không?
2. Binder/serializer có giữ lại và gửi đúng header không?
3. Consumer adapter có đọc được kiểu được kỳ vọng không?
4. Stub Runner có phát được cùng metadata theo contract không?

Không mặc định mọi header của `MessageHeaders` sẽ xuất hiện nguyên xi dưới dạng một JSON field. Body và transport metadata là hai kênh thông tin khác nhau.

## 14. Stub messaging không thay thế broker integration tests

Một phép kiểm bằng Stub Runner xác minh consumer **có thể xử lý sự kiện theo mẫu** và listener/wiring phù hợp với môi trường test. Nó không chứng minh toàn bộ đặc tính vận hành:

- **Delivery semantics:** at-most-once, at-least-once, retry và duplicate delivery.
- **Ordering:** thứ tự giữa các event, partition/key hoặc concurrency.
- **Transaction/outbox:** trạng thái database và message publish có nhất quán khi lỗi không?
- **Serialization/native encoding:** JSON, Avro, Protobuf, schema registry và bytes thực trên transport.
- **DLQ/retry topology:** broker routing, dead-letter policies, consumer acknowledgements.
- **Security:** broker credentials, ACL, TLS, quyền publish/subscribe.
- **Performance:** throughput, latency, backpressure và tài nguyên.

Nếu các yếu tố này là yêu cầu sản phẩm, cần **integration tests với binder/broker phù hợp** (ví dụ Testcontainers cho Kafka/RabbitMQ khi dự án dùng chúng) và đo đạc vận hành. Không đòi Stub Runner phải thay một broker production hoàn chỉnh.

## 15. Quy trình CI: từ contract producer đến consumer độc lập

~~~mermaid
flowchart TD
    A["PR sửa message contract hoặc producer"] --> B["Review payload/headers/destination/label"]
    B --> C["Sinh & chạy producer messaging tests"]
    C --> D["Kiểm serialization/adapter khi cần"]
    D --> E{"Producer verification đạt?"}
    E -->|Không| F["Chặn phát hành artifact"]
    E -->|Có| G["Đóng gói JAR classifier stubs"]
    G --> H["Kiểm contract và metadata trong JAR"]
    H --> I["Publish phiên bản lên Maven repository"]
    I --> J["Consumer CI tải stubs qua Stub Runner"]
    J --> K["Kích hoạt label + listener assertions"]
    K --> L["Đánh giá consumer cũ còn tương thích"]
~~~

Các quy tắc CI quan trọng:

1. **Không publish một stub chưa được producer xác minh.** Việc đóng gói thành công không bảo đảm các generated producer tests đã chạy.
2. **Gắn được artifact với commit và version** để truy nguyên source contract thực sự sinh ra dữ liệu đó.
3. **Kiểm nội dung JAR**, không chỉ kiểm JAR tồn tại. Với messaging, đặc biệt kiểm `contracts`/`label`/destination và khả năng trigger.
4. **Không dùng cùng Maven local repository như một giả định cho hai CI độc lập**. Producer publish `stubs`; consumer tải qua repository phù hợp.
5. **Ghim artifact version** hoặc chọn version có chủ đích, tránh một bản mutable mới bất ngờ đổi payload.
6. **Kiểm cả nhánh producer và consumer**. Producer test đảm bảo nguồn phát theo hợp đồng; consumer test đảm bảo listener xử lý theo hợp đồng.
7. **Giữ hợp đồng còn được hỗ trợ** hoặc có kế hoạch version/migration trước khi xóa trường, đổi topic, đổi enum, thay header hoặc thu hẹp miền dữ liệu.

### 15.1. Kiểm những thay đổi có thể phá tương thích

| Thay đổi | Ví dụ | Tác động có thể xảy ra |
| --- | --- | --- |
| Đổi destination | `orders.created` → `orders.v2` | Listener cũ không nhận sự kiện. |
| Bỏ hoặc đổi header | `eventType=OrderCreated` không còn | Consumer định tuyến/deserialize sai. |
| Đổi tên trường | `amountMinor` → `totalAmount` | DTO consumer không đọc được. |
| Đổi kiểu dữ liệu | Number → String | Consumer cũ có thể parse lỗi hoặc hiểu sai. |
| Đổi enum | `CREATED` → `NEW` | Handler không nhận ra trạng thái. |
| Bỏ field bắt buộc | Xóa `orderId` | Consumer không còn khóa liên kết hóa đơn. |
| Đổi meaning | `amountMinor` từ đơn vị nhỏ nhất sang đơn vị chính | Consumer có thể tính sai tiền dù schema tương tự. |
| Bỏ label test | `orderCreatedV1` không còn | Consumer CI không trigger được stub cũ; cần chuyển đổi có kế hoạch. |

**Label** là giao diện phục vụ kịch bản stub/test, nên cũng cần ổn định trong quy trình consumer verification. Tuy nhiên, việc đổi label tự nó không nhất thiết là thay đổi giao thức production; phải tách **tương thích sự kiện trên broker** và **tương thích bộ công cụ/test** khi đánh giá tác động.

## 16. Lỗi thường gặp và quy tắc chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chỉ tìm thấy `mappings` trống trong JAR. | Hợp đồng chỉ có messaging, không phải HTTP. | Kiểm contract messaging, label và thử trigger; đừng kết luận lỗi từ số HTTP mappings. |
| `StubTrigger` không trigger được label. | Contract thiếu trong artifact, tên label sai, artifact/version khác. | Mở JAR thực và đối chiếu label với `ids`. |
| Trigger thành công nhưng probe timeout. | Adapter không nối đúng binder/destination; listener chưa subscribe. | Kiểm Spring Cloud Stream bindings, integration setup và logs. |
| Consumer parse event bị lỗi. | Content-Type, schemaVersion, converter hoặc kiểu field không khớp. | Capture payload/headers tại consumer và so hợp đồng. |
| Producer test không tìm thấy message. | `triggeredBy` không gọi đúng method hoặc MessageVerifier chưa cấu hình. | Kiểm generated test/base test, test binder và nơi nhận output. |
| Producer test pass nhưng production gửi bytes sai. | Test quan sát trước serializer, binder production khác. | Thêm serialization/transport integration tests. |
| Consumer CI không tải được stub. | Repository sai, classifier thiếu, version không publish, quyền đọc thiếu. | Kiểm Maven coordinates và chế độ LOCAL/REMOTE. |
| Test chập chờn khi chạy song song. | Dùng chung queue, label, eventId hoặc probe còn event cũ. | Reset/cô lập fixture, dùng deadline, tránh chung state. |
| Stub có message nhưng consumer không xử lý. | Listener chưa được đăng ký hoặc function binding sai. | Kiểm function definition và destination. |
| Consumer test pass, producer thực đổi payload. | Chưa bắt buộc producer verification khi publish. | Cấu hình CI chặn phát hành và kiểm tương thích cũ. |

Khi debug, đi theo thứ tự: **tọa độ stub → nội dung JAR → label → messaging adapter → destination/binder → converter → listener → assertion**. Song song, kiểm nhánh producer: **trigger → producer publish → MessageVerifier → generated assertions**. Hai đường đi này gặp nhau ở **hợp đồng**, không phải ở việc chia sẻ cùng một process producer.

## 17. Bài thực hành: đóng gói và trigger OrderCreated

Thực hành trên một producer Spring Boot/Spring Cloud Stream đã cấu hình Spring Cloud Contract Verifier và một consumer có Stub Runner:

1. **Xác định contract** cho `OrderCreatedV1` có `label=orderCreatedV1`, `sentTo=orders.created`, headers và payload ở mục 3.
2. **Viết Groovy messaging contract** theo mục 4, đặt trong thư mục contract của producer.
3. **Cài đặt producer publisher** qua `StreamBridge`, cấu hình binding trỏ tới `orders.created`.
4. **Tạo base test** cung cấp `publishOrderCreated()` và thiết lập messaging adapter/test binder để generated test thu được sự kiện.
5. **Chạy producer verification**; kiểm test thực sự được sinh, được chạy và assertion body/header/destination đạt.
6. **Gây lỗi có chủ đích:** đổi `currency` thành `USD` hoặc `orderId` thành một giá trị không đúng hợp đồng, chạy lại để xác nhận producer test FAIL rồi hoàn nguyên.
7. **Đóng gói/cài artifact `stubs`** sau khi producer verification đạt; mở JAR và tìm contract, label, destination, body.
8. **Kiểm consumer bằng Stub Runner LOCAL**, trigger `orderCreatedV1`, xác nhận Billing listener nhận event và lưu/kích hoạt tác dụng nghiệp vụ mong đợi.
9. **Thử làm sai wiring:** đổi destination của consumer, quan sát probe timeout; khôi phục rồi xác nhận PASS.
10. **Đưa vào CI hai máy/runner độc lập**: producer publish artifact `stubs` lên repository; consumer tải bằng `REMOTE` và chạy cùng test không cần khởi động Order Service.
11. **Mô phỏng breaking change:** bỏ `orderId` hoặc đổi `eventType`; nêu consumer nào sẽ ảnh hưởng và kế hoạch giữ tương thích/version.

**Tiêu chí hoàn thành:** có **artifact stub mang đúng tọa độ**, chứa **message contract được Stub Runner nhận diện**, producer test đã xác minh publisher, consumer test trigger đúng **label**, nhận được **payload/headers qua adapter**, và pipeline chặn publish khi producer sai hợp đồng.

## 18. Câu hỏi tự kiểm tra

1. Vì sao một JAR chỉ có messaging contracts có thể không chứa WireMock HTTP mappings?
2. `label 'orderCreatedV1'` khác `sentTo('orders.created')` thế nào?
3. `triggeredBy('publishOrderCreated()')` được dùng ở nhánh producer hay consumer Stub Runner?
4. Điều gì cần thiết để `stubTrigger.trigger("orderCreatedV1")` thật sự đưa message tới Billing listener?
5. Vì sao tải được artifact `stubs` chưa chứng minh messaging adapter đã cấu hình đúng?
6. Tại sao generated producer test kiểm Spring Message trước serialization có thể bỏ sót lỗi bytes/headers trên broker?
7. Khi nào chọn Stub Runner `LOCAL`, khi nào chọn `REMOTE` và vì sao nên ghim version?
8. Vì sao một response HTTP 404 do WireMock no-match không liên quan đến việc listener không nhận messaging event?
9. Nếu đổi destination nhưng giữ nguyên payload, đó có thể là breaking change không?
10. Vì sao cần cả producer verification lẫn consumer test với Stub Runner trước khi coi một phiên bản event là tương thích?

**Ghi nhớ:** **Messaging stub là dữ liệu hợp đồng có thể được Stub Runner kích hoạt và đưa qua một messaging adapter, không phải một producer thật hoặc một HTTP WireMock endpoint**. Hãy định nghĩa rõ **label, destination, headers, payload mẫu**, xác minh producer phát đúng sự kiện, đóng gói đúng artifact **classifier `stubs`**, kiểm nội dung JAR và cấu hình binder để consumer nhận được message. Khi CI buộc producer verification đạt trước publish và consumer kiểm bằng Stub Runner theo version xác định, thay đổi giao tiếp giữa hai dịch vụ sẽ được phát hiện sớm mà không cần chạy toàn bộ hệ thống.
