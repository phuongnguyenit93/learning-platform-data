# Timeout, đồng bộ và chờ kết quả xử lý bất đồng bộ

## Mục tiêu học tập

Trong **Spring Cloud Contract**, hợp đồng mô tả cách **producer** (dịch vụ phát thông điệp) giao tiếp với **consumer** (dịch vụ nhận và xử lý thông điệp). Hợp đồng có thể dùng **Groovy/YAML DSL** để sinh kiểm thử phía producer, tạo stub cho consumer kiểm thử bằng **Stub Runner**, và được tích hợp trong **CI** để phát hiện thay đổi giao diện không tương thích.

Trong chương **Kiểm thử messaging**, thử thách lớn không chỉ là xác nhận payload JSON đúng. Thông điệp thường được gửi, nhận, xử lý và ghi trạng thái **bất đồng bộ**; vì thế assertion chạy quá sớm có thể thất bại, còn timeout quá dài hoặc việc chờ sai điều kiện có thể làm test xanh giả hay không ổn định.

Sau bài học, bạn có thể:

- Phân biệt **gửi thông điệp**, **nhận thông điệp**, **xử lý thành công** và **quan sát trạng thái nghiệp vụ đã cập nhật**.
- Hiểu vai trò của **timeout khi generated producer test nhận output message** và **timeout khi consumer test đợi handler xử lý**.
- Viết contract Groovy/YAML cho một sự kiện, cấu hình base test và biết generated test cần chờ điều gì.
- Dùng **Stub Runner + StubTrigger** và cơ chế **polling có giới hạn** như Awaitility để kiểm tra consumer bất đồng bộ.
- Phát hiện **race condition**, thông điệp cũ, sai destination, trễ lịch chạy và correlation ID không khớp.
- Chọn độ dài timeout, khoảng poll, fixture và cơ chế cô lập hợp lý cho CI.
- Hiểu những bảo đảm mà contract test cung cấp và các tình huống cần test broker/transaction/retry riêng.

## 1. Bài toán thực tế: sự kiện StockChanged đến chậm

Giả sử **Inventory Service** là producer. Sau khi thay đổi tồn kho, nó phát sự kiện `StockChanged` đến destination `stock-events`. **Checkout Service** là consumer: khi nhận sự kiện, nó cập nhật một projection nội bộ rồi quyết định có cho đặt hàng hay không.

Payload được hai bên thống nhất:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 0
}
~~~

Checkout có thể xử lý theo các bước:

1. Nhận message từ broker/binder.
2. Deserialize JSON, kiểm tra `eventType`, `sku` và `quantity`.
3. Cập nhật projection tồn kho trong database/cache.
4. Sau khi cập nhật thành công, luồng nghiệp vụ đọc được trạng thái `OUT_OF_STOCK`.

Các bước có thể chạy trên thread khác nhau hoặc có độ trễ ghi dữ liệu. Test gọi `trigger(...)` rồi lập tức đọc projection có thể thực hiện assertion **trước khi bước 3 hoàn tất**, mặc dù consumer vẫn xử lý đúng.

### Một dòng thời gian minh họa

~~~mermaid
sequenceDiagram
    participant Test as Consumer test
    participant Stub as Stub Runner
    participant Bus as Test binder / broker
    participant Handler as Checkout handler
    participant DB as Stock projection
    Test->>Stub: trigger("stock_changed")
    Stub->>Bus: Publish StockChanged
    Stub-->>Test: Trigger accepted
    Test->>DB: Read quantity immediately
    DB-->>Test: Old value (8)
    Bus-->>Handler: Deliver message
    Handler->>DB: Save quantity = 0
    Test->>DB: Retry read with bounded polling
    DB-->>Test: New value (0)
~~~

**Điểm cốt lõi:** `trigger(...)` trả thành công chỉ có nghĩa **lệnh kích hoạt stub đã được chấp nhận** theo API Stub Runner. Nó **không bảo đảm** handler đã hoàn tất, database đã commit hoặc projection đã sẵn sàng cho một lần đọc mới.

## 2. Ba cấp độ “thành công” không giống nhau

| Cấp độ | Ví dụ | Bằng chứng tương ứng | Không tự chứng minh |
|---|---|---|---|
| **Đã gọi lệnh phát** | `inventoryService.changeStock(...)` chạy xong | Trigger method đã được gọi | Message đã đến đúng destination |
| **Message đã xuất hiện trên destination** | Verifier nhận `StockChanged` | Producer messaging contract test nhận và assert payload/header | Consumer đã xử lý thành công |
| **Consumer xử lý xong** | Projection của SKU-101 chuyển thành 0 | Consumer test quan sát trạng thái nghiệp vụ cuối cùng | Broker production luôn giao tin hoặc đúng thứ tự |

Một số ứng dụng còn có cấp độ thứ tư: message được ghi bền vững vào broker/outbox rồi được giao đến consumer theo chính sách riêng. Contract test với test binder có thể xác nhận **nội dung và luồng phát trong môi trường test**, nhưng không tự chứng minh durability, exactly-once hay bảo đảm giao hàng thực tế của broker.

### Đồng bộ và bất đồng bộ ở đâu?

- **Đồng bộ ở test:** phương thức test gọi `emitStockChanged()` và nhận quyền điều khiển trở lại.
- **Bất đồng bộ ở ứng dụng:** producer có thể publish trên scheduler, listener, transactional event hoặc một thread khác.
- **Bất đồng bộ ở consumer:** handler có thể cập nhật projection sau khi Stub Runner trả về.
- **Nhất quán sau cùng (eventual consistency):** dữ liệu đọc sau publish có thể tạm thời là giá trị cũ, rồi mới trở thành giá trị mới.

**Không bắt buộc toàn bộ pipeline messaging phải chạy đồng bộ để test có thể xác định.** Thay vào đó, phải **chờ tín hiệu kết quả đúng**, có giới hạn thời gian và cách cô lập dữ liệu.

## 3. Timeout nào đang được nói tới?

Từ “timeout” thường bị dùng chung cho nhiều cơ chế:

| Loại timeout | Điểm bắt đầu và kết thúc | Dùng để kiểm tra gì? |
|---|---|---|
| **Producer receive timeout** | Sau khi trigger, generated test đợi output message | Producer có phát message đúng destination trong thời gian chờ không? |
| **Consumer processing wait** | Sau khi stub phát event, test đợi trạng thái ứng dụng | Handler đã xử lý và ghi trạng thái mong đợi chưa? |
| **Broker poll/receive timeout** | Client/binder đợi một message từ queue/topic | Có message để đọc trong phiên nhận đó không? |
| **Request/reply timeout** | Một lời gọi chờ phản hồi message tương ứng | Có reply đúng correlation và hạn chờ không? |
| **Retry/backoff deadline** | Nhiều lần thử hoặc một workflow đang được retry | Khi nào dừng cố gắng và báo lỗi? |
| **JUnit/build timeout** | Tổng thời gian thực thi một test hoặc job | Tránh job treo vô hạn khi setup hoặc test lỗi |

Các timeout trên **không thay thế nhau**. Ví dụ tăng JUnit timeout từ 5 lên 60 giây sẽ không giúp generated producer test nếu messaging receiver chỉ đợi một khoảng rất ngắn theo cấu hình của nó. Ngược lại, tăng timeout nhận message có thể che giấu lỗi destination hoặc làm CI chậm.

**Không nhầm với HTTP timeout:** HTTP `504 Gateway Timeout` là một phản hồi HTTP từ gateway/server, còn khi consumer message chờ broker hoặc handler, thường **không có HTTP status** nào liên quan.

## 4. Groovy DSL cho một sự kiện bất đồng bộ

Giả sử Inventory phát message sau hành động cập nhật kho. Contract Groovy minh họa có thể đặt tại `src/test/resources/contracts/inventory/stockChanged.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Phat StockChanged khi SKU-101 ve 0'
    label 'stock_changed'

    input {
        triggeredBy('changeStockForContract()')
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

Ý nghĩa của từng phần:

| DSL | Bên sử dụng | Vai trò |
|---|---|---|
| `label 'stock_changed'` | Consumer / Stub Runner | Định danh event stub để chủ động kích hoạt |
| `triggeredBy('changeStockForContract()')` | Generated producer test | Gọi method trong base class để làm producer phát event |
| `sentTo('stock-events')` | Messaging verifier | Chỉ định destination cần quan sát |
| `body(...)` | Generated assertion và stub | Payload/kiểu dữ liệu đã cam kết |
| `headers {...}` | Generated assertion và stub | Header consumer dựa vào, như event type và content type |

`quantity: 0` là số, **không phải** chuỗi `'0'`. Nếu Checkout deserialize quantity thành integer, thay kiểu này có thể phá vỡ consumer dù event vẫn được gửi thành công.

Ở bài này, `changeStockForContract()` là method mà nhóm **phải tự viết trong base test**. Spring Cloud Contract không tự hiểu phải đổi bản ghi tồn kho nào hay đợi transaction ở database ra sao.

### YAML DSL tương ứng

Có thể dùng YAML thay cho Groovy:

~~~yaml
description: 'Phat StockChanged khi SKU-101 ve 0'
label: stock_changed
input:
  triggeredBy: changeStockForContract()
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

Hai ví dụ có **cùng ý định**, không nên đưa cả hai vào cùng build như hai contract độc lập cho cùng tình huống nếu điều đó tạo test và stub trùng.

YAML `input.triggeredBy` là **tên/lời gọi method**, không phải một cấu hình delay. `outputMessage.sentTo` là **destination**, không phải tên biến Java. Muốn producer test quan sát được event, base test và messaging integration phải khớp destination thực.

## 5. Producer base test: kích hoạt mã thật rồi để verifier nhận output

Một base class Spring Boot có thể có hình dạng:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import com.example.inventory.InventoryService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.verifier.messaging.boot.AutoConfigureMessageVerifier;

@SpringBootTest(classes = InventoryApplication.class)
@AutoConfigureMessageVerifier
public abstract class InventoryMessageContractBase {

    @Autowired
    private InventoryService inventoryService;

    public void changeStockForContract() {
        inventoryService.changeQuantity("SKU-101", 0);
    }
}
~~~

`InventoryService` và `changeQuantity(...)` là API **minh họa**, cần phù hợp với code producer thực tế. Base class phải được plugin Spring Cloud Contract chọn qua `baseClassForTests` hoặc cơ chế mapping base classes của plugin.

**Điều cần bảo vệ:** method `changeStockForContract()` phải thực sự gọi vào **luồng nghiệp vụ/publisher của producer**. Nếu method chỉ gửi một fixture trực tiếp vào verifier hoặc mock toàn bộ việc publish, generated test có thể xanh mà không chứng minh publisher thật đã thực hiện hành vi đúng.

### Có thể publish sau khi method trả về

Giả sử `changeQuantity` lưu dữ liệu rồi phát event bằng cơ chế bất đồng bộ. Khi generated test gọi method, event có thể đến destination sau đó một khoảng ngắn. Trong luồng test, receiver của Spring Cloud Contract cần chờ được output message.

Nếu producer có outbox worker chạy theo lịch rất thưa hoặc broker cần vài giây để khởi động, một generated test mặc định có thể timeout trước khi event xuất hiện.

Để giải quyết, nên ưu tiên:

1. Bảo đảm **test binder/receiver đã sẵn sàng** trước khi gọi trigger.
2. Cấu hình scheduling/transaction/binder trong test sao cho event đến được một cách xác định.
3. Kiểm tra timeout thực tế của **messaging verifier/receiver** theo phiên bản Spring Cloud Contract và integration đang dùng.
4. Chỉ tăng khoảng chờ khi đã có bằng chứng event hợp lệ có thể đến chậm trong điều kiện test.
5. Nếu workflow cần chờ outbox thực, bổ sung **integration test chuyên biệt** thay vì ép mọi generated contract test phụ thuộc lịch xử lý lâu dài.

### Test binder và phạm vi kiểm chứng

Với **Spring Cloud Stream**, có thể dùng **test binder** để tránh phụ thuộc trực tiếp vào Kafka/RabbitMQ production. Dependency và cơ chế kích hoạt test binder phụ thuộc phiên bản Spring Cloud Stream.

Ví dụ dependency cho những dòng Spring Cloud Stream sử dụng artifact test-binder riêng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong một số cấu hình/phiên bản khác, tài liệu sử dụng `spring-cloud-stream` với classifier `test-binder` và type `test-jar`. **Không trộn hai phương án một cách máy móc.** Hãy dùng dependency và cách kích hoạt tương thích với Spring Boot/Spring Cloud release train mà dự án dùng; kiểm tra log để xác nhận verifier đã nối tới **đúng binder và destination**.

Test binder giúp tập trung vào **contract payload, header và publisher logic** trong phạm vi test. Nó không tự chứng minh partition assignment, retry topic, broker retention hoặc độ bền lưu message trong môi trường production.

## 6. Đọc generated producer test: test đang chờ điều gì?

Sau khi module producer được cấu hình Spring Cloud Contract Verifier và chạy lifecycle build thích hợp, generated tests thường được tạo ở các vùng output như:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Đường dẫn và tên class có thể thay đổi theo phiên bản plugin/cấu hình. Hãy xem log của build thật để xác nhận test được sinh và **đã thực sự chạy**.

### Hình dạng của generated test

Theo ngữ nghĩa Spring Cloud Contract, test được sinh sẽ thực hiện các bước tương đương (**pseudocode**, không phải Java output nguyên văn):

~~~text
WHEN:
    changeStockForContract()

THEN:
    msg = messagingVerifier.receive("stock-events", contractSettings)

    assert msg != null
    assert msg.headers["eventType"] == "StockChanged"
    assert msg.contentType matches "application/json"

    payload = decodeJson(msg)
    assert payload.eventType == "StockChanged"
    assert payload.sku == "SKU-101"
    assert payload.quantity == 0  // number
~~~

Trong tài liệu chính thức, generated test có lời gọi **receive** để lấy message từ destination, kèm thông tin/cấu hình contract. Cách timeout được truyền, mặc định của receiver, cơ chế polling và API Java cụ thể phụ thuộc phiên bản hoặc messaging integration. Vì vậy, **không nên tự phát minh một thuộc tính YAML như `receiveTimeoutMs` rồi cho rằng Spring Cloud Contract sẽ tự đọc**.

### Năm bằng chứng quan trọng

Khi review generated test, cần xác minh:

1. Method `changeStockForContract()` được gọi thật và chạy trên producer test application.
2. Receiver đang đọc **đúng destination `stock-events`**, không phải queue/topic khác.
3. Lời gọi receive có thể **chờ** cho message đến và có giới hạn thời gian; hiểu timeout theo API thực.
4. Assertion kiểm tra **header và payload đúng kiểu**, không chỉ có một message bất kỳ.
5. Nếu nhận được nhiều message, test không vô tình dùng message cũ hoặc một event từ test khác làm bằng chứng.

**Nhận được message không có nghĩa chắc chắn là message của trigger vừa chạy.** Nếu destination chứa message cũ có payload giống fixture, test có thể xanh giả. Cần cô lập trạng thái hoặc sử dụng correlation dữ liệu test đủ riêng biệt.

### Khi producer test timeout

Chẩn đoán theo thứ tự:

~~~mermaid
flowchart TD
    A["Generated producer test timeout"] --> B{"Trigger method có được gọi?"}
    B -->|Không| C["Kiểm tra base class, generated test, JUnit lifecycle"]
    B -->|Có| D{"Code producer có publish?"}
    D -->|Không| E["Kiểm tra nghiệp vụ, transaction, scheduler, error log"]
    D -->|Có| F{"Đúng destination và binder?"}
    F -->|Không| G["Kiểm tra StreamBridge binding, sentTo, converter"]
    F -->|Có| H{"Message đến sau timeout?"}
    H -->|Có| I["Xem thời gian thực, setup và receive timeout phù hợp"]
    H -->|Không rõ| J["Trace message ID, headers và trạng thái queue"]
~~~

Đừng sửa `outputMessage.body` để test chờ ít hơn. Sai body gây **assertion mismatch** khi message đã nhận được, còn **receive timeout** thường liên quan trigger, route, binder hoặc thời gian. Hai lỗi cần hướng điều tra khác nhau.

## 7. Consumer test: chờ **trạng thái nghiệp vụ**, không chỉ chờ trigger

Ở consumer, Spring Cloud Contract **Stub Runner** có thể phát một message stub theo `label` thông qua `StubTrigger`.

Ví dụ lớp test minh họa:

~~~java
package com.example.checkout.contract;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class StockChangedConsumerContractTest {

    @Autowired
    StubTrigger stubTrigger;

    @Autowired
    StockProjection stockProjection;

    @Test
    void updatesProjectionAfterStockChanged() {
        // Fixture phải tạo trạng thái ban đầu đúng và sạch.
        // Ví dụ: SKU-101 đang có quantity = 8.

        boolean triggered = stubTrigger.trigger(
            "com.example:inventory-producer",
            "stock_changed"
        );
        assertThat(triggered).isTrue();

        await()
            .atMost(Duration.ofSeconds(5))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                assertThat(stockProjection.quantityOf("SKU-101"))
                    .isEqualTo(0)
            );
    }
}
~~~

**Đây là skeleton**, chưa tự chứa cấu hình cho `StockProjection`, cleanup database hay binder của Checkout. Dự án thật phải khai báo interface/service projection, nạp fixture ban đầu, bảo đảm handler lắng nghe `stock-events` và sử dụng dependency Awaitility trong test classpath.

`LOCAL` giả định stub artifact đã có ở Maven local repository. Trong CI, dùng repository/mode phù hợp và ghim **đúng phiên bản candidate stub**, không vô tình lấy bản cũ trong cache.

### Vì sao dùng `untilAsserted`?

Với assertion thông thường:

~~~java
stubTrigger.trigger("stock_changed");
assertThat(stockProjection.quantityOf("SKU-101")).isEqualTo(0);
~~~

test có thể chạy quá sớm và thấy giá trị cũ `8`. Nếu dùng `Thread.sleep(2000)`, test lại luôn chờ ít nhất hai giây dù handler xử lý trong 20 ms; vẫn có nguy cơ fail khi CI tải nặng hơn.

Với Awaitility:

- Assertion được thực hiện **nhiều lần**, cho đến khi đạt hoặc hết thời gian.
- Test có **giới hạn**, không treo vô hạn.
- Polling kết thúc sớm nếu consumer đã xử lý xong.
- Khi quá hạn, test thất bại và phản ánh việc trạng thái chưa đạt trong ngân sách chờ.

**Điều Awaitility không làm:** nó không tự bảo đảm message đã được publish, không tạo transaction, không đăng ký listener và không sửa race condition trong code production. Nó chỉ làm việc **quan sát điều kiện cuối cùng** đúng thời điểm hơn.

### Một điều kiện đủ mạnh là gì?

Không nên chỉ đợi “projection khác null” nếu fixture đã có projection từ trước.

Tốt hơn:

~~~java
await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
    StockView view = stockProjection.find("SKU-101");
    assertThat(view).isNotNull();
    assertThat(view.quantity()).isEqualTo(0);
    assertThat(view.status()).isEqualTo("OUT_OF_STOCK");
});
~~~

`StockView` và `stockProjection` ở trên là **kiểu minh họa của ứng dụng**, không phải API Spring Cloud Contract. Assertion cần xác nhận **đúng hành vi consumer phụ thuộc**. Với trường hợp test chạy lại, phải bảo đảm fixture đầu vào không có quantity 0 ngay từ trước khi trigger, nếu không test có thể xanh mà chưa xử lý message mới.

## 8. Tránh test xanh giả: kiểm tra **sự thay đổi**, không chỉ trạng thái có sẵn

Một lỗi phổ biến:

1. Test trước đã xử lý `StockChanged` cho `SKU-101` và ghi quantity 0.
2. Test sau không reset database.
3. Test sau trigger event nhưng listener bị lỗi.
4. Awaitility kiểm tra `quantity == 0` và **đạt ngay** do dữ liệu cũ.

Lúc này test báo xanh dù consumer không xử lý event trong lượt test hiện tại.

### Cách thiết kế chống false positive

- **Reset projection** về giá trị ban đầu (ví dụ 8) trước mỗi test và xác nhận reset thành công.
- **Dùng mã SKU/ID khác nhau** cho các trường hợp cần độc lập, tránh đụng test khác khi chạy song song.
- Nếu event có `eventId`, lưu/quan sát ID cuối cùng đã xử lý để phân biệt event mới và event cũ.
- Khi dùng database, bảo đảm reset transaction và transaction listener thực sự có thể nhìn thấy trạng thái cần thiết.
- Nếu producer hoặc consumer có cơ chế **dedup**, đặt test ID và state để không vô tình bỏ qua message hợp lệ do “đã xử lý”.

Ví dụ cách nghĩ:

~~~text
BEFORE:
  projection(SKU-101).quantity == 8
  processedEventId != evt-contract-101

TRIGGER:
  StubTrigger.trigger(stock_changed)

AWAIT:
  projection(SKU-101).quantity == 0
  processedEventId == evt-contract-101
~~~

`evt-contract-101` là ID minh họa. Nếu hợp đồng không công bố event ID hoặc ứng dụng không lưu nó, đừng thêm field chỉ để test dễ. Khi đó tối thiểu phải **cô lập fixture và xác nhận trạng thái trước**.

## 9. Điều kiện chờ nên đặt ở đâu?

| Tình huống | Nên đợi điều gì? | Không nên chỉ đợi |
|---|---|---|
| Producer vừa gọi publisher | Message với header/body đúng xuất hiện ở destination test | Method publisher trả về |
| Consumer nhận StockChanged | Projection đã commit với quantity mới | Stub trigger trả `true` |
| Consumer lưu đơn hàng sau event | Bản ghi business thực sự tồn tại/đổi trạng thái | Listener method được gọi nhưng transaction chưa hoàn tất |
| Request/reply messaging | Reply đúng correlation ID và payload | Có *bất kỳ* message trên reply topic |
| Consumer có retry khi lỗi tạm thời | Cuối cùng đạt kết quả đúng hoặc có trạng thái retry thất bại như thiết kế | Mới thực hiện một attempt |
| Luồng có dead-letter | Message lỗi được đưa đến DLQ với metadata đã cam kết | Một exception được log mà không có kết quả xử lý rõ |

**Chờ điều kiện kết quả** giúp test phản ánh đúng hành vi. Nhưng phải cẩn thận: một số side effect như gửi email hoặc gọi dịch vụ ngoài không dễ quan sát. Khi cần, tạo fake/mock cho dependency và chờ một tín hiệu observable có nghĩa, không thay thế logic consumer chính bằng một stub trống.

### Điều kiện chờ có thể là nhiều assertion

Trong một test event `OrderConfirmed`, chỉ kiểm tra `status=CONFIRMED` có thể bỏ sót việc tổng tiền chưa cập nhật. Khi consumer phụ thuộc cả hai, có thể dùng cùng `untilAsserted` để yêu cầu:

~~~java
await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
    OrderView order = orderProjection.find("ORD-101");
    assertThat(order.status()).isEqualTo("CONFIRMED");
    assertThat(order.amount()).isEqualTo(125000);
});
~~~

Phép kiểm tra này cần backend đọc dữ liệu **nhất quán đủ cho mục tiêu**. Nếu hai field được commit trong hai transaction khác nhau, test cần thể hiện rõ điều gì đã được ứng dụng cam kết và có nên chấp nhận một trạng thái tạm thời hay không.

## 10. Chọn timeout và poll interval theo ngân sách có cơ sở

Không có một con số timeout luôn đúng cho mọi dự án. Thời gian chờ chịu ảnh hưởng bởi:

- Thời gian khởi động/context/binder.
- Thời gian publisher gửi message.
- Độ trễ broker hoặc test binder.
- Scheduling thread và consumer concurrency.
- Thời gian deserialize, xử lý nghiệp vụ và transaction commit.
- Tải tài nguyên của CI runner.

Một cách ước lượng:

~~~text
T_budget =
    T_publish
  + T_delivery
  + T_processing
  + T_commit
  + T_scheduling_margin
~~~

Ví dụ **minh họa** khi đo trên môi trường test:

| Giai đoạn | Khoảng thường quan sát |
|---|---|
| Publish/binder | 30 ms |
| Delivery/scheduler | 60 ms |
| Handler | 150 ms |
| Commit/visibility | 80 ms |
| Dự phòng tải CI | 500 ms |
| **Ngân sách mẫu** | **820 ms** |

Các số trong bảng chỉ giúp minh họa phương pháp, **không phải benchmark hoặc mặc định của Spring Cloud Contract**. Test thường cần một biên an toàn hơn giá trị quan sát để tránh flaky, nhưng không nên tự tăng lên 60 giây mỗi khi fail.

### Poll interval không phải timeout

Nếu `atMost(5s)` và `pollInterval(100ms)`:

- **5 giây** là giới hạn chờ tối đa.
- **100 ms** là khoảng cách giữa các lần kiểm tra (với hành vi mặc định và cấu hình thư viện cụ thể).
- Test có thể kết thúc sớm khi điều kiện đạt.

Polling quá dày dễ gây tốn CPU và tải database; polling quá thưa làm chậm phát hiện kết quả. Chọn khoảng kiểm tra hợp lý với tốc độ xử lý và chi phí truy vấn projection.

### Khi nào tăng timeout?

Chỉ cân nhắc sau khi xác định:

1. Message **đã đến đúng destination** nhưng consumer xử lý hợp lệ cần thêm thời gian.
2. Kịch bản nghiệp vụ **thực sự bất đồng bộ** và giới hạn cũ thấp hơn thời gian hợp lệ.
3. CI có độ trễ scheduler đã đo được và test vẫn có deadline hợp lý.
4. Không có race condition hoặc shared state chưa xử lý.

Nếu message chưa hề được phát, queue sai hoặc listener không chạy, tăng timeout thường chỉ làm test thất bại **chậm hơn**.

## 11. Đồng bộ hóa setup và listener trước khi trigger

Một lỗi khó phát hiện là **publish trước khi consumer/binder sẵn sàng**.

Tình huống minh họa:

~~~mermaid
sequenceDiagram
    participant Test as Test thread
    participant Context as Spring context
    participant Listener as Event listener
    participant Bus as Broker / test binder
    Test->>Context: Start
    Context-->>Test: Some beans created
    Test->>Bus: Trigger event too early
    Bus--xListener: No ready subscription / wrong route
    Context->>Listener: Start subscription later
    Test->>Test: Await projection, then timeout
~~~

Các hướng khắc phục:

- Để framework test dựng **đầy đủ application context** trước khi test method bắt đầu; nếu listener khởi tạo bất đồng bộ, có một readiness condition phù hợp.
- Dùng binder test được cấu hình chắc chắn, và reset/chuẩn bị channel trước khi gửi sự kiện.
- Nếu chạy Kafka/RabbitMQ thật trong integration test, chờ subscription/consumer assignment theo cơ chế của thư viện, không ngủ cố định một khoảng tùy tiện.
- Tránh dùng `@BeforeAll` khởi động async task rồi test ngay khi chưa bảo đảm nó sẵn sàng.
- Nếu dùng nhiều listener, kiểm tra destination/group/filter để đúng handler được kích hoạt.

**Không đánh đồng** Spring application context đã start với mọi subscription broker đều sẵn sàng trong mọi kiến trúc. Mức readiness tùy framework và hạ tầng.

## 12. Message correlation, thứ tự và nhiều sự kiện cùng destination

Một generated test có thể cần chờ một output message, nhưng producer thực tế đôi khi phát nhiều event cùng lúc:

~~~text
stock-events:
  StockChanged(SKU-202, quantity=5)
  StockChanged(SKU-101, quantity=0)
  StockChanged(SKU-303, quantity=9)
~~~

Nếu test chỉ lấy **message đầu tiên** rồi assert `SKU-101`, nó có thể fail vì nhận `SKU-202` trước. Một số receiver có cơ chế đọc theo destination và thứ tự; không nên giả định nó tự lọc theo field nghiệp vụ.

### Thiết kế test tránh đụng nhau

- Dùng **destination/channel test riêng** hoặc mỗi test một môi trường/binder khi cần.
- Dùng `sku`/event ID xác định để nhận diện sự kiện của test.
- Nếu ứng dụng phát nhiều output như thiết kế, contract/test cần mô tả đúng **sự kiện quan trọng** và cách chọn nó.
- Giữ queue/binder sạch giữa các test; không để payload của test trước còn chờ.
- Tránh chạy các contract dùng chung destination trong parallel mode khi verifier không hỗ trợ phân tách phù hợp.
- Với hệ thống cần bảo đảm thứ tự, kiểm chứng thứ tự ở **tầng broker/integration** theo partition key và cấu hình thật, không suy từ một test binder đơn giản.

### Correlation trong request/reply

Trong kịch bản **request/reply messaging**, consumer gửi message request và nhận reply. Nếu có nhiều request đồng thời, reply phải mang **correlation ID** để bên nhận ghép đúng response.

Một test chỉ chờ “có reply trên `stock-replies`” có thể nhận nhầm reply của request khác. Test đúng nên kiểm tra **correlation key, payload và loại reply**. Cách cấu hình correlation header phụ thuộc framework, nên không tự giả định tên header cụ thể như `correlationId` là mặc định ở mọi broker.

Spring Cloud Contract có thể mô tả input/output messages, nhưng bảo đảm request/reply đúng khi concurrency cao cần thêm test tình huống giao đồng thời.

## 13. MessageFrom và triggeredBy: đường chờ khác nhau

### Kịch bản A: producer tự phát sau hành động

~~~groovy
input {
    triggeredBy('changeStockForContract()')
}
outputMessage {
    sentTo('stock-events')
    body(eventType: 'StockChanged', sku: 'SKU-101', quantity: 0)
}
~~~

Generated test **gọi method** để kích hoạt, sau đó **đợi output**.

### Kịch bản B: producer xử lý một message đầu vào

~~~groovy
input {
    messageFrom('stock-commands')
    messageBody(
        command: 'RefreshStock',
        sku: 'SKU-101'
    )
}
outputMessage {
    sentTo('stock-events')
    body(eventType: 'StockRefreshed', sku: 'SKU-101')
}
~~~

Generated test cần **gửi hoặc đưa input message** đến hệ thống theo adapter phù hợp, sau đó **đợi output**.

Điểm chung: **thời gian chờ đầu ra** chỉ có ý nghĩa khi input/trigger đi qua **code producer thật** và messaging integration đúng. Khác biệt là cách bắt đầu quá trình: gọi một method hay gửi một message.

| Tiêu chí | `triggeredBy` | `messageFrom` |
|---|---|---|
| Bắt đầu bằng | Method trong base class | Input message trên destination |
| Phù hợp khi | Task/service/scheduler phát event | Listener nhận command/event rồi phản hồi |
| Setup quan trọng | Method trigger, nghiệp vụ, publisher | Input binding/listener, converter, output binding |
| Lỗi chờ thường gặp | Method không publish hoặc publish sau transaction | Input không đến handler hoặc listener chưa ready |
| Kết thúc | Nhận output message và assert | Nhận output message và assert |

Không thêm một `triggeredBy` giả vào hợp đồng messageFrom chỉ để ép test hoạt động: chọn đúng mô hình giao tiếp mà producer đang cung cấp.

## 14. Retry, dead-letter và “không có message” có kiểm chứng được không?

### Retry có thể làm kết quả đến muộn

Nếu consumer xử lý lỗi tạm thời và retry, projection có thể chỉ cập nhật sau một vài lần thử. Test cần:

- Đợi một kết quả nghiệp vụ cuối cùng **có giới hạn**.
- Nếu cần chứng minh retry, kiểm tra số lần thử hoặc tín hiệu mà ứng dụng công bố.
- Đảm bảo không có event cũ khiến test qua trước khi retry hiện tại thành công.
- Không tạo delay quá dài chỉ để chờ số lần retry; có thể dùng fake clock/scheduler khi hỗ trợ.

### Dead-letter queue (DLQ)

Khi payload không hợp lệ hoặc handler liên tục thất bại, broker/binder có thể đưa event đến DLQ theo cấu hình. Một contract cho **payload hợp lệ** không tự kiểm tra chính sách dead-letter. Nên dùng integration test hoặc adapter test phù hợp để xác nhận:

- Điều kiện chuyển sang DLQ.
- Số lần retry và backoff.
- Metadata/correlation của message lỗi.
- Khả năng xử lý lại an toàn nếu nghiệp vụ yêu cầu.

### Kiểm tra “không phát message”

Đây là **negative assertion**: trong một trường hợp, producer không được phát event. Một bài test chỉ chờ 200 ms và thấy không có event **không thể chứng minh tuyệt đối** rằng event sẽ không xuất hiện sau 201 ms.

Muốn kiểm tra hành vi không phát:

1. Xác định **ranh giới thời gian/hành vi** mà ứng dụng cam kết.
2. Ưu tiên kiểm tra **quyết định nghiệp vụ/transaction** trực tiếp khi có thể.
3. Nếu cần quan sát destination, đặt cửa sổ nhận hữu hạn có lý do và đảm bảo queue ban đầu sạch.
4. Không coi một lệnh receive timeout là bằng chứng mạnh rằng code producer sẽ không bao giờ publish.

Với xử lý qua outbox, có thể cần kiểm tra **không tạo outbox record** khi transaction rollback hoặc không đủ điều kiện phát, thay vì chỉ đợi một destination im lặng.

## 15. Các nguyên nhân phổ biến của flaky test

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer test fail ngay sau `trigger` | Assertion chạy trước handler | Polling có giới hạn theo trạng thái nghiệp vụ |
| Test xanh dù listener không chạy | Projection đã chứa dữ liệu từ test trước | Seed/reset trạng thái trước test, dùng event ID |
| Producer test timeout khi receive | Method không publish, destination/binder sai | Trace trigger → publisher → binding → receiver |
| Test chỉ fail trên CI | Tải scheduler, khởi tạo binder chậm, ràng buộc thời gian quá cứng | Đo latency, readiness và điều chỉnh timeout có cơ sở |
| Test fail khi chạy song song | Dùng chung destination, state hoặc event ID | Cô lập resource/test case |
| Test nhận sai payload | Có message cũ hoặc producer phát nhiều event | Correlation và cleanup queue |
| Stub Trigger trả `false` | Label không tồn tại trong artifact hoặc stub chưa load | Kiểm tra `labels()`, version artifact và messaging adapter |
| Trigger trả `true` nhưng projection không đổi | Handler chưa đăng ký, bị lỗi, topic sai hoặc chưa commit | Kiểm tra consumer log, binder, trạng thái và assertion |
| Message đến nhưng header/type sai | Converter/schema thay đổi, YAML quote sai | Đọc message thực, sửa DSL/converter đúng kiểu |
| Retry quá lâu làm test timeout | Backoff dài hơn deadline hoặc lỗi liên tục | Thiết kế ngân sách thử lại và fake clock |
| Khi test đơn lẻ xanh nhưng chạy cả suite fail | Shared mutable state hoặc listener tạo hai lần | Reset beans/binder/state, kiểm soát test isolation |

### Phân tầng lỗi để debug

Không nên gọi mọi thất bại là “timeout”. Hãy phân loại:

1. **Trigger failure:** Không gọi được method hoặc `StubTrigger` không tìm thấy label.
2. **Publish failure:** Code producer không gửi message.
3. **Routing/binder failure:** Message đã phát nhưng không đến đúng destination.
4. **Receive timeout:** Verifier không quan sát được output trong hạn chờ.
5. **Assertion mismatch:** Đã nhận message nhưng header/body không đúng.
6. **Consumer processing timeout:** Stub đã phát, handler có thể nhận nhưng trạng thái cuối chưa đạt.
7. **Test isolation failure:** Nhận message cũ hoặc trạng thái từ test khác.

Mỗi loại có phương pháp kiểm tra khác nhau; việc tăng `atMost` thường chỉ phù hợp nhóm (6) sau khi xác nhận nguyên nhân.

## 16. Những gì consumer test với Stub Runner không tự chứng minh

| Phạm vi | Contract/Stub Runner hỗ trợ tốt | Cần test bổ sung khi nào? |
|---|---|---|
| Payload/header của event | Producer test và stub kiểm chứng message đã cam kết | Schema evolution phức tạp, encoding tùy chỉnh |
| Consumer đọc và xử lý payload | Consumer test với stub, assertion trạng thái | Nhiều nhánh, dữ liệu biên chưa có contract |
| Async handler hoàn tất | Awaitility/observable state trong test | Performance và throughput ở tải cao |
| Broker giao hàng | Test binder mô phỏng đường giao trong phạm vi setup | Kafka/RabbitMQ retention, partition, failover |
| Exactly-once/idempotency | Test một event có thể bổ sung kiểm tra logic | Duplicate delivery, retry, transaction |
| Ordering | Test tình huống cụ thể | Nhiều partition, concurrency và ordering guarantees |
| Outbox transaction | Test có thể kích hoạt nghiệp vụ | Atomic DB commit và publish thực |
| Recovery sau mất kết nối | Fault simulation trong môi trường test | Integration với broker/network failure |
| Backward compatibility | Contract mới + consumer test với candidate stub | Các consumer cũ, versioning, rollout thực tế |

**Producer test xanh với contract mới không có nghĩa tất cả consumer cũ tương thích.** Nếu producer đổi `quantity` từ number thành string và đồng thời sửa DSL, generated test mới có thể vẫn xanh. Cần chạy consumer tests thực sự dùng **candidate stub cùng revision**, đánh giá compatibility trước khi publish.

## 17. Đưa kiểm chứng bất đồng bộ vào CI

~~~mermaid
flowchart TD
    A["PR cập nhật message contract"] --> B["Kiểm tra DSL, label và destination"]
    B --> C["Sinh generated producer tests"]
    C --> D["Base test trigger publisher"]
    D --> E{"Receive + assert trong timeout?"}
    E -->|Không| F["Chặn merge, phân loại lỗi"]
    E -->|Có| G["Đóng gói candidate stub có version"]
    G --> H["Stub Runner dùng đúng artifact"]
    H --> I["Trigger label và await business state"]
    I --> J{"Consumer xử lý đúng?"}
    J -->|Không| K["Điều tra listener/schema/state"]
    J -->|Có| L["Compatibility review rồi phát hành"]
~~~

### Các cổng CI nên có

1. **Contract discovery:** Generator đọc đúng file Groovy/YAML; không chấp nhận build xanh vì `0 tests`.
2. **Producer setup:** `@AutoConfigureMessageVerifier`, binder và base class được gắn đúng.
3. **Producer receive:** Thực sự nhận event từ destination, assert payload và header đúng kiểu, với hạn chờ hợp lý.
4. **Stub artifact:** Gắn version/commit có thể truy vết và chứa label event.
5. **Consumer setup:** Listener, binder và projection ở trạng thái sạch trước khi trigger.
6. **Consumer wait:** Assertion dựa vào kết quả nghiệp vụ, có timeout và polling rõ ràng.
7. **Isolation:** Test song song không đọc chung message/state ngoài chủ đích.
8. **Compatibility:** Schema, header, destination hoặc kiểu trường thay đổi phải kiểm tra consumer đang dùng phiên bản cũ.
9. **Observability:** Khi test fail, log không chứa dữ liệu nhạy cảm nhưng có thông tin trigger, destination, event ID và khoảng chờ thực.
10. **Không bỏ qua flaky:** Fail thất thường là dấu hiệu phải điều tra, không phải lý do auto-retry job vô hạn.

### Ghi chứng cứ có thể truy vết

Báo cáo PR/CI hữu ích nên cho biết:

~~~text
Contract revision: <commit>
Producer revision: <commit>
Generated test: <class/method>
Messaging integration: <test binder or broker>
Message destination: stock-events
Stub artifact: com.example:inventory-producer:<version>:stubs
Consumer revision: <commit>
Consumer test: <class/method>
Wait condition: quantity(SKU-101) == 0
Wait budget: <configured duration>
Result: PASS / FAIL / TIMEOUT + diagnostic
~~~

Các giá trị trong dấu `<...>` là placeholder cho báo cáo thực tế, không phải dữ liệu do plugin tự điền.

## 18. Bài thực hành: sửa một test bất đồng bộ chưa đáng tin

### Đề bài

Checkout sử dụng event `StockChanged` để cập nhật projection. Một đồng nghiệp viết test:

~~~java
@Test
void handlesStockChanged() {
    stubTrigger.trigger("stock_changed");
    Thread.sleep(200);
    assertThat(stockProjection.quantityOf("SKU-101"))
        .isEqualTo(0);
}
~~~

Test chạy xanh trên máy cá nhân nhưng thỉnh thoảng fail trên CI. Đồng thời khi vô hiệu hóa listener, test đôi lúc vẫn xanh.

**Câu hỏi:**

1. Vì sao `Thread.sleep(200)` không đồng bộ hóa được với handler?
2. Vì sao test có thể xanh khi listener không chạy?
3. Cần kiểm tra điều gì trước khi trigger?
4. Nên dùng điều kiện chờ nào để thể hiện kết quả nghiệp vụ?
5. Nếu có nhiều event đến cùng destination, làm sao biết kết quả là của event test hiện tại?

### Lời giải tham khảo

**Vấn đề 1:** `Thread.sleep(200)` chỉ dừng thread test 200 ms, không đảm bảo listener đã nhận và commit dữ liệu. Nếu CI bận, handler có thể cần lâu hơn.

**Vấn đề 2:** Projection có thể đã chứa quantity 0 từ test trước; assertion hiện tại không chứng minh listener xử lý event mới.

**Vấn đề 3:** Seed/reset fixture để trước test `SKU-101` có quantity 8; xác minh trạng thái đó, dọn các event cũ hoặc dùng ID riêng.

**Vấn đề 4:** Dùng Awaitility và check trạng thái cuối trong deadline:

~~~java
@Test
void handlesStockChanged() {
    assertThat(stockProjection.quantityOf("SKU-101"))
        .isEqualTo(8);

    assertThat(stubTrigger.trigger("stock_changed"))
        .isTrue();

    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
            assertThat(stockProjection.quantityOf("SKU-101"))
                .isEqualTo(0)
        );
}
~~~

Đoạn trên chỉ là **phần thân test**; cần setup fixture, import, bean, stub artifact, binder và consumer listener thực tế. Thời gian 5 giây là **ngân sách minh họa** chứ không phải giá trị mặc định tối ưu.

**Vấn đề 5:** Dùng event ID, correlation/key phù hợp nếu giao diện có hỗ trợ, hoặc cô lập destination/test data. Không nhận một message cũ có cùng body làm bằng chứng cho event vừa trigger.

### Bài mở rộng: producer nhận message quá muộn

Generated producer test gọi `changeStockForContract()` nhưng receiver không thấy `StockChanged` trong thời gian chờ. Producer log cho thấy event đến `stock-events` sau khi một job scheduler chạy vài giây.

Hãy đề xuất thứ tự xử lý:

1. Kiểm tra contract `sentTo`, binding và header.
2. Xác nhận trigger method thực sự gọi luồng publisher.
3. Kiểm tra transaction/outbox/scheduler, đo độ trễ.
4. Xác định test cần bảo vệ publisher trực tiếp hay workflow scheduler hoàn chỉnh.
5. Nếu giữ workflow async, cấu hình test setup/receiver timeout phù hợp với **API thực tế của phiên bản Spring Cloud Contract**.
6. Bổ sung integration test broker/outbox nếu contract test chỉ quan sát được một phần giao diện.

**Không nên** sửa test bằng cách bỏ assertion message hoặc đặt timeout cực dài ngay lập tức.

## 19. Checklist trước khi phê duyệt thay đổi messaging

- [ ] Contract có `label`, destination, header và payload phù hợp consumer.
- [ ] `triggeredBy` hoặc `messageFrom` phản ánh đúng hành động làm producer phát event.
- [ ] Base test gọi code producer thật và dùng messaging verifier/binder đúng.
- [ ] Generated test nhận **đúng message**, không phải event cũ từ test khác.
- [ ] Payload và headers được assert với đúng type và matcher.
- [ ] Timeout nhận producer có cơ sở, không che giấu lỗi publish/route.
- [ ] Consumer Stub Runner dùng **đúng candidate stub artifact**.
- [ ] Consumer listener/subscription sẵn sàng trước khi trigger.
- [ ] Fixture consumer được reset, trạng thái **trước trigger** được kiểm tra.
- [ ] Consumer test đợi **trạng thái nghiệp vụ cuối**, không chỉ kiểm tra `trigger()==true`.
- [ ] Polling/timeout có giới hạn và phù hợp tải CI.
- [ ] Test song song không chia sẻ message state nguy hiểm.
- [ ] Các trường hợp retry, duplicate, ordering, DLQ, transaction được test bổ sung khi nghiệp vụ phụ thuộc.
- [ ] CI ghi rõ revision, artifact stub, test và thời gian chờ thực thi.
- [ ] Khi thay message schema/destination, các consumer cũ được rà soát tương thích.

## 20. Ghi nhớ và tài liệu tham khảo

**Trong messaging contract testing, “trigger thành công” không đồng nghĩa với “consumer đã xử lý xong”.** Generated producer test cần **khởi phát hành vi producer và nhận output message** để assert nội dung; consumer test cần **dùng Stub Runner phát event rồi chờ kết quả nghiệp vụ** với timeout có giới hạn. Hãy ưu tiên polling trên trạng thái quan sát được, fixture sạch, correlation rõ ràng và readiness của listener.

Spring Cloud Contract bảo vệ những tương tác message đã khai báo trong **Groovy/YAML DSL**, chứ không tự chứng minh mọi bảo đảm của broker, transaction, retry, message ordering hay exactly-once. Khi kết hợp producer tests, consumer Stub Runner tests và integration tests đúng phạm vi, CI có khả năng phát hiện thay đổi thông điệp không tương thích mà vẫn tránh test bất ổn.

### Tham khảo chính thức

- [Spring Cloud Contract — Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): `triggeredBy`, `messageFrom`, `outputMessage`, verifier, messaging integration và `StubTrigger`.
- [Spring Cloud Contract — YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): cấu trúc `input` và `outputMessage` cho YAML DSL.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): cách kích hoạt message stub bằng label.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html): lựa chọn test binder để kiểm tra messaging integration.

**Kết luận:** timeout phải bảo vệ một ranh giới có nghĩa, polling phải quan sát một kết quả có nghĩa, và mỗi lần test phải chứng minh **sự kiện của chính lượt chạy đó** đã được xử lý. Khi ba điều này được kiểm soát, kiểm thử messaging bất đồng bộ sẽ hữu ích và ổn định hơn nhiều so với cách dùng một `Thread.sleep` cố định.
