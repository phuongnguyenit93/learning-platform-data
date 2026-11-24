# Correlation ID, khóa nghiệp vụ và dữ liệu định tuyến

## 1. Vì sao ba loại định danh này quan trọng trong message contract?

Trong hệ thống giao tiếp bất đồng bộ, producer phát một thông điệp rồi tiếp tục công việc mà không nhất thiết đợi consumer xử lý xong. Spring Cloud Contract (**SCC**) cho phép mô tả hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh bài kiểm thử phía producer, tạo stub để consumer kiểm tra qua **Stub Runner**, và kết hợp với CI nhằm phát hiện thay đổi không tương thích.

Khi một thông điệp có payload JSON hợp lệ nhưng thiếu metadata hoặc gửi sai nơi, hệ thống vẫn có thể hoạt động sai:

- Consumer không liên kết được kết quả với yêu cầu ban đầu vì thiếu **correlation ID**.
- Hai sự kiện cùng một sản phẩm đến những partition khác nhau do **business key** không nhất quán, làm xử lý thứ tự trở nên khó dự đoán.
- Một sự kiện được phát đúng body nhưng vào **topic, exchange hoặc routing key** không được consumer đăng ký.
- Consumer không chống được thông điệp trùng lặp vì nhầm **event ID** với correlation ID.
- Contract test chỉ assert payload, bỏ qua header và destination nên pipeline xanh mặc dù giao tiếp thực tế đã gãy.

Bài này tập trung vào **correlation ID, khóa nghiệp vụ và dữ liệu định tuyến** trong chương *Hợp đồng thông điệp* của module `SPRING_CLOUD_CONTRACT`. Mục tiêu không chỉ đặt tên các field, mà là xác định ý nghĩa, chỗ lưu, cách kiểm chứng và giới hạn của Spring Cloud Contract khi phối hợp với Kafka, RabbitMQ hoặc Spring Cloud Stream.

### Sau bài học, bạn có thể

1. Phân biệt `correlationId`, `eventId`, `businessKey`, message key, partition key, topic và routing key.
2. Quyết định metadata nào nằm trong payload, header hay thuộc cấu hình transport.
3. Viết message contract Groovy/YAML với destination, header và body.
4. Kết nối generated producer test với **luồng phát message thật**, không tự tạo sự kiện giả trong test base.
5. Kiểm tra consumer với Stub Runner và biết bài test nào cần broker thật/test broker.
6. Thiết kế tương quan sự kiện, idempotency, phân vùng, ordering, retry và schema evolution.
7. Xây checklist CI phát hiện thay đổi message không tương thích.

## 2. Kịch bản: một yêu cầu cập nhật tồn kho

Giả sử **Inventory Service** là producer, phát sự kiện `InventoryChanged`. **Checkout Service** và **Fulfillment Service** là hai consumer:

~~~mermaid
flowchart LR
    A["API cập nhật tồn kho"] --> B["Inventory Service"]
    B --> C["inventory.events"]
    C --> D["Checkout Service"]
    C --> E["Fulfillment Service"]
    B --> F["Contract Verifier"]
    F --> G["Generated producer tests"]
    C --> H["Broker hoặc test binder"]
~~~

Một request cập nhật tồn kho có ngữ cảnh:

~~~text
tenantId:       tenant-a
sku:            SKU-123
newQuantity:    12
correlationId:  corr-1001
~~~

Producer phát message mẫu:

~~~json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "eventType": "InventoryChanged",
  "tenantId": "tenant-a",
  "sku": "SKU-123",
  "available": true,
  "quantity": 12,
  "aggregateVersion": 7
}
~~~

Các **application message headers** minh họa:

~~~text
correlationId: corr-1001
businessKey: tenant-a|SKU-123
eventType: InventoryChanged
schemaVersion: 1
~~~

Và thông tin định tuyến:

~~~text
Logical destination: inventory.events
Kafka message key (khi dùng Kafka): tenant-a|SKU-123
~~~

Đây là **quy ước của ứng dụng ví dụ**, không phải SCC hay broker tự gán mặc định. Đặc biệt, chỉ thêm header `businessKey` **không tự khiến Kafka dùng nó làm record key**; adapter/binder phải được cấu hình ánh xạ rõ ràng.

## 3. Bảng phân biệt các loại định danh

| Giá trị | Câu hỏi nó trả lời | Phạm vi và tính ổn định |
|---|---|---|
| **Correlation ID** | “Những thông điệp nào cùng thuộc một yêu cầu/luồng xử lý?” | Có thể dùng lại trên **nhiều sự kiện khác nhau** của cùng workflow |
| **Event ID / Message ID** | “Đây là sự kiện logic nào?” | Cần phân biệt sự kiện này với sự kiện khác; thường **ổn định khi redelivery cùng sự kiện** |
| **Business key / Aggregate key** | “Sự kiện này nói về đối tượng nghiệp vụ nào?” | Ổn định với cùng aggregate, ví dụ tenant + SKU |
| **Kafka record key / Partition key** | “Broker dùng giá trị nào để quyết định partition?” | Phụ thuộc transport/partitioner, có thể chọn business key |
| **Destination / Topic / Queue / Exchange** | “Message được gửi đến đâu?” | Thường là một phần cấu hình hoặc contract vận chuyển |
| **RabbitMQ routing key** | “Exchange áp dụng routing rule nào?” | Phụ thuộc exchange type và binding, **khác Kafka key** |
| **Trace ID / Span ID** | “Luồng thực thi phân tán nào đang được quan sát?” | Do hệ thống tracing quản lý; không mặc nhiên bằng correlation ID |
| **Causation ID** | “Event nào trực tiếp gây ra event này?” | Thường là ID của sự kiện/lệnh cha, giúp truy vết chuỗi nhân quả |

Có thể liên hệ ba ID bằng tình huống:

~~~text
Correlation ID: corr-1001
  ├── Event ID: evt-a1   businessKey: tenant-a|SKU-123
  │      InventoryChanged(quantity=12)
  ├── Event ID: evt-a2   businessKey: tenant-a|SKU-123
  │      InventoryReserved(quantity=2)
  └── Event ID: evt-b1   businessKey: tenant-a|ORDER-789
         CheckoutConfirmed
~~~

Ba sự kiện **cùng correlation ID** nhưng có **event ID khác nhau** và có thể mang **business key khác nhau**. Nếu lấy correlation ID làm khóa partition trong mọi trường hợp, các event của cùng sản phẩm từ nhiều workflow khác nhau có thể bị phân tán không mong muốn; nếu lấy business key làm event ID, consumer không phân biệt được hai lần cập nhật cùng sản phẩm.

## 4. Correlation ID: liên kết một chuỗi xử lý

Correlation ID là định danh dùng để gắn các bước giao tiếp vào một request hoặc một quy trình xuyên dịch vụ. Ví dụ HTTP request của Checkout:

~~~http
POST /api/inventory/adjust HTTP/1.1
Content-Type: application/json
X-Correlation-Id: corr-1001

{"tenantId":"tenant-a","sku":"SKU-123","quantity":12}
~~~

Inventory Service nhận request, xử lý và phát `InventoryChanged` với application header:

~~~text
correlationId: corr-1001
~~~

Consumer có thể đưa correlation ID đó vào log, metrics có kiểm soát hoặc các event tiếp theo để điều tra toàn bộ quy trình.

### Quy tắc triển khai cần chốt

- **Nguồn ID:** nhận từ ingress đáng tin hoặc sinh mới khi thiếu. Giá trị do bên ngoài truyền vào cần được **validate** và giới hạn độ dài, không tin vô điều kiện.
- **Phạm vi truyền:** HTTP header tên `X-Correlation-Id` có thể được chuyển thành application message header `correlationId`; mapping này phải được code thực hiện.
- **Không dùng làm định danh sự kiện:** các event khác nhau trong một request có thể chia sẻ correlation ID.
- **Không mặc định là ID tracing:** `traceparent` trong W3C Trace Context có cấu trúc và semantics riêng. Có thể liên kết chúng, nhưng không nên đổi tên tùy tiện.
- **Không chứa dữ liệu nhạy cảm:** tránh nhúng email, số điện thoại, token, session ID hoặc dữ liệu cá nhân vào giá trị correlation.
- **Có chiến lược khi thiếu:** giữ nguyên message để xử lý, từ chối, đưa DLQ hoặc tạo ID mới? Chính sách phải được thống nhất giữa producer và consumer.

Đối với một workflow bất đồng bộ dài, correlation ID có thể tồn tại lâu hơn một HTTP request. Việc truyền nó qua nhiều bước cần được kiểm thử, không chỉ gắn ở endpoint đầu tiên.

## 5. Event ID: định danh sự kiện để chống xử lý trùng

Broker thường có đặc tính **at-least-once delivery** trong các cấu hình phổ biến: cùng một sự kiện logic có thể được giao lại khi retry, rebalance hoặc consumer xử lý xong nhưng chưa ghi nhận acknowledgement.

Ví dụ hai lần giao message:

~~~text
delivery #1: eventId=550e8400-e29b-41d4-a716-446655440000
delivery #2: eventId=550e8400-e29b-41d4-a716-446655440000
~~~

Hai delivery cần được consumer nhận diện là **cùng một event** nếu nghiệp vụ yêu cầu xử lý idempotent. Nếu producer sinh một event ID mới mỗi lần thử gửi lại **cùng một sự kiện**, cơ chế dedup theo event ID sẽ mất tác dụng.

Phân biệt:

| Trường hợp | Event ID | Correlation ID | Business key |
|---|---|---|---|
| Redelivery cùng event | **Giữ nguyên** | Giữ nguyên | Giữ nguyên |
| Hai sự kiện cập nhật cùng SKU | **Khác nhau** | Có thể giống hoặc khác | Có thể giống |
| Sự kiện cập nhật SKU khác trong cùng workflow | **Khác nhau** | Có thể giống | **Khác nhau** |

Consumer thường lưu dấu vết xử lý dựa trên `eventId` hoặc kết hợp `source + eventId` theo quy ước hệ thống. Đó là một phần thiết kế **idempotency**, không phải chức năng SCC tự triển khai.

Đừng thay event ID bằng Kafka offset: offset chỉ có nghĩa trong một partition cụ thể, không phải định danh nghiệp vụ bền vững khi re-publish sang broker/topic khác.

## 6. Business key: đối tượng nào đang được thay đổi?

Trong ví dụ tồn kho, aggregate được xác định bởi:

~~~text
tenantId = tenant-a
sku      = SKU-123

businessKey = tenant-a|SKU-123
~~~

Nếu ứng dụng đa tenant, chỉ dùng `SKU-123` có thể **va chạm** giữa hai tenant. Nếu key được ghép bằng dấu `|`, cần định nghĩa quy tắc escaping/normalization hoặc dùng biểu diễn key có cấu trúc, tránh trường hợp dữ liệu chứa chính dấu phân cách.

Business key nên:

- **Ổn định** giữa các sự kiện của cùng aggregate.
- **Không chứa bí mật**; nếu key xuất hiện trong log/header/broker metadata, cần cân nhắc PII và quyền truy cập.
- **Có quy ước chuẩn hóa**: chữ hoa/thường, Unicode, khoảng trắng đầu cuối, định dạng ID.
- **Phù hợp mục tiêu grouping/order**: với aggregate tồn kho, thường chọn tenant + SKU; với đơn hàng, tenant + order ID.
- **Không thay đổi âm thầm** khi hệ thống nâng version schema hoặc refactor dữ liệu.

Khi consumer cần giữ thứ tự xử lý thay đổi của cùng SKU, business key là ứng viên phù hợp cho **Kafka record key**. Nhưng việc nó có thật sự quyết định partition hay không phụ thuộc implementation adapter/binder và cấu hình broker.

## 7. Dữ liệu định tuyến: phân biệt destination và key

Trong Spring Cloud Contract message DSL, `sentTo(...)` thường diễn tả **destination** đầu ra mà test messaging/verifier cần quan sát:

~~~groovy
outputMessage {
    sentTo('inventory.events')
}
~~~

Nhưng một hệ thống thực có thể có nhiều lớp định tuyến:

| Tầng | Ví dụ | Trách nhiệm |
|---|---|---|
| Application intent | `InventoryChanged` | Xác định loại sự kiện |
| Logical destination | `inventory.events` | Nơi producer công bố sự kiện theo contract |
| Spring Cloud Stream binding | `inventoryChanged-out-0` | Tên binding giữa ứng dụng và binder |
| Kafka topic | `inventory.events` | Topic broker thực |
| Kafka record key | `tenant-a|SKU-123` | Đầu vào của cơ chế partitioning |
| RabbitMQ exchange | `inventory.exchange` | Điểm nhận message của broker |
| RabbitMQ routing key | `inventory.changed.tenant-a` | Dùng với routing/binding theo loại exchange |
| Consumer group/queue | `checkout-consumer` | Nhóm consumer nhận message theo topology |

Không phải hệ thống nào cũng có tất cả các lớp trên. Chúng **không đồng nghĩa**; việc thay tên topic hoặc routing key có thể làm consumer không nhận được event dù JSON vẫn đúng.

**Quan trọng:** contract kiểm tra `sentTo('inventory.events')` có thể quan sát destination **ở mức abstraction của test binder**, không nhất thiết xác nhận Kafka topic thật, Rabbit exchange binding hoặc Kafka partition key. Nếu những thông tin đó là một phần cam kết vận hành, cần test adapter/broker bổ sung.

## 8. Kafka key khác RabbitMQ routing key

### 8.1. Với Kafka

Trong Kafka, mỗi record được gửi đến một **topic**. Record key thường được partitioner sử dụng để chọn **partition**. Với một topic có nhiều partition, các message cùng key thường được đưa vào cùng partition theo partitioner/cấu hình ổn định.

Điều đó giúp consumer xử lý các thay đổi **cùng aggregate** theo thứ tự của log partition, nhưng cần biết giới hạn:

- Kafka **không bảo đảm thứ tự toàn cục** giữa các partition.
- Thứ tự trong một partition còn phụ thuộc chiến lược publish/retry và cách consumer xử lý song song.
- Thay **số partition**, partitioner hoặc serialization của key có thể làm cách ánh xạ key→partition thay đổi.
- Trường `businessKey` nằm trong JSON hoặc custom header **không mặc định** trở thành Kafka record key.
- Consumer cần xem **bytes/format key** nếu dùng key để group hoặc route, không chỉ đọc payload.

### 8.2. Với RabbitMQ

Một message thường được publish đến **exchange** kèm **routing key**; exchange dựa vào loại exchange và bindings để chọn queue nhận message. Ví dụ topic exchange có thể dùng key dạng:

~~~text
inventory.changed.tenant-a
~~~

Đó là một **mẫu định tuyến**, không phải Kafka partition key. Đừng sao chép giả định về thứ tự theo Kafka partition sang RabbitMQ routing key. RabbitMQ còn có semantics của queue, consumer acknowledgements, retry/dead-letter riêng.

### 8.3. Kết luận thực hành

Nếu mục đích là **cùng aggregate đi cùng partition**, nên xác định rõ business key, Kafka key mapping và thử với broker/adapter thực. Nếu mục đích là **chọn một queue theo loại sự kiện hoặc tenant**, cần kiểm tra exchange, routing key và queue binding thực tế. Spring Cloud Contract chỉ bảo vệ những phần được contract và test environment thật sự quan sát.

## 9. Contract Groovy DSL cho message có metadata

Giả sử producer phát một message sau khi application service thay đổi tồn kho. Contract đặt dưới vị trí producer đã cấu hình, ví dụ:

~~~text
src/test/resources/contracts/inventory/inventory-changed.groovy
~~~

Nội dung:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Phát InventoryChanged cùng correlation và khóa nghiệp vụ'
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')

        headers {
            header('contentType', 'application/json')
            header('correlationId', 'corr-1001')
            header('businessKey', 'tenant-a|SKU-123')
            header('eventType', 'InventoryChanged')
            header('schemaVersion', '1')
        }

        body(
            eventId: '550e8400-e29b-41d4-a716-446655440000',
            eventType: 'InventoryChanged',
            tenantId: 'tenant-a',
            sku: 'SKU-123',
            available: true,
            quantity: 12,
            aggregateVersion: 7
        )

        bodyMatchers {
            jsonPath('$.eventId', byRegex(uuid()))
        }
    }
}
~~~

Các thành phần quan trọng:

1. `label` là tên nhận diện contract; trong một số luồng Stub Runner messaging, consumer có thể yêu cầu trigger theo label.
2. `input.triggeredBy` chỉ **phương thức trong producer test base** để kích hoạt hành vi phát message. Đây không phải method của consumer.
3. `outputMessage.sentTo` mô tả logical destination kỳ vọng.
4. `outputMessage.headers` mô tả metadata mà producer cần đặt trên message ở tầng mà test verifier nhìn thấy.
5. `outputMessage.body` mô tả JSON payload mẫu mà consumer cần hiểu.
6. `bodyMatchers` cho phép `eventId` thay đổi nhưng phải đúng dạng UUID, thay vì buộc mỗi lần producer sinh ID bằng cùng chuỗi mẫu.

**Cảnh báo:** đừng biến `triggerInventoryChanged()` thành một phương thức tự gửi message mẫu. Phương thức trigger phải gọi **luồng nghiệp vụ production** tạo ra message thật. Những field động khác như timestamp hoặc ID có thể cần matcher phù hợp với phiên bản SCC đang dùng.

Cú pháp `uuid()`, cách sử dụng `bodyMatchers` cho message và khả năng quan sát header/transport cần được đối chiếu với phiên bản Spring Cloud Contract đã chọn và xác nhận bằng **generated test thật**.

## 10. Cùng ý tưởng trong YAML DSL

Một tệp `inventory-changed.yml` tương đương về ý tưởng:

~~~yaml
description: Phát InventoryChanged cùng correlation và khóa nghiệp vụ
label: inventoryChanged

input:
  triggeredBy: triggerInventoryChanged()

outputMessage:
  sentTo: inventory.events
  headers:
    contentType: application/json
    correlationId: corr-1001
    businessKey: 'tenant-a|SKU-123'
    eventType: InventoryChanged
    schemaVersion: '1'
  body:
    eventId: 550e8400-e29b-41d4-a716-446655440000
    eventType: InventoryChanged
    tenantId: tenant-a
    sku: SKU-123
    available: true
    quantity: 12
    aggregateVersion: 7
  matchers:
    body:
      - path: $.eventId
        type: by_regex
        predefined: uuid
~~~

Một số điểm về YAML:

- `input.triggeredBy` và `outputMessage` là **schema của SCC**, không phải tính năng mặc định của YAML parser.
- `businessKey` được quote vì có ký tự phân cách do ứng dụng chọn; nếu key có dấu `:` hoặc chuỗi có thể bị YAML hiểu sai, càng cần quote rõ.
- `schemaVersion: '1'` là **chuỗi** trong ví dụ; đổi thành số `1` sẽ thay kiểu metadata và có thể ảnh hưởng consumer.
- `aggregateVersion: 7` là **số JSON**, dùng để phân biệt phiên bản aggregate trong payload.
- Body matcher tập trung vào event ID động; những field như `sku`, `quantity` và header có kỳ vọng cố định ở kịch bản mẫu.

Hai contract Groovy/YAML trên là **hai phương án**, không cần đưa cả hai vào cùng project nếu cùng mô tả một tình huống. Test base, messaging adapter và plugin phải được cấu hình tương ứng để hợp đồng được xử lý thành bài kiểm thử thực sự.

## 11. Phân biệt field trong payload, header và transport envelope

Một sự kiện có thể được chia thành ba lớp:

~~~text
TRANSPORT ENVELOPE
  destination/topic: inventory.events
  record key:       tenant-a|SKU-123
  partition:        do broker/partitioner quyết định

APPLICATION HEADERS
  correlationId:    corr-1001
  businessKey:      tenant-a|SKU-123
  schemaVersion:    1
  eventType:        InventoryChanged

BODY (JSON)
  eventId:          550e8400-e29b-41d4-a716-446655440000
  tenantId:         tenant-a
  sku:              SKU-123
  available:        true
  quantity:         12
  aggregateVersion: 7
~~~

| Nơi đặt | Ưu điểm | Lưu ý |
|---|---|---|
| **Payload** | Dễ serialize, lưu trữ, replay, áp dụng JSON schema | Consumer phải parse body mới lấy metadata |
| **Application header** | Có thể đọc nhanh trước khi parse body; hữu ích cho tracing/routing | Header propagation và converter/binder có thể khác nhau |
| **Transport key/envelope** | Broker sử dụng trực tiếp cho partition/routing | Cần kiểm tra adapter, wire format và cấu hình transport |
| **Cả header và payload** | Có thể hữu ích khi nhiều consumer/tooling khác nhau cần đọc | Phải có quy tắc **nhất quán** và test không cho hai giá trị mâu thuẫn |

Không nên nhân bản dữ liệu tùy tiện. Nếu `tenantId` hoặc `businessKey` có mặt ở cả header và body, contract phải quyết định khi chúng khác nhau thì consumer xử lý thế nào: từ chối, dùng giá trị nào, hay ghi lỗi an toàn. Các quy tắc bảo mật/ủy quyền **không được** chỉ dựa trên header do nguồn không tin cậy tự khai báo.

## 12. Producer code: tạo metadata từ ngữ cảnh nghiệp vụ

Để kiểm chứng có ý nghĩa, message phải được sinh từ **application service production**. Ví dụ mô hình hóa sự kiện:

~~~java
package com.example.inventory;

public record InventoryChangedEvent(
        String eventId,
        String eventType,
        String tenantId,
        String sku,
        boolean available,
        int quantity,
        long aggregateVersion) {
}
~~~

Một port phát sự kiện:

~~~java
package com.example.inventory;

public interface InventoryEventPublisher {
    void publish(
            InventoryChangedEvent event,
            String correlationId,
            String businessKey);
}
~~~

Application service xử lý cập nhật và gọi port:

~~~java
package com.example.inventory;

import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InventoryApplicationService {

    private final InventoryEventPublisher eventPublisher;

    public InventoryApplicationService(
            InventoryEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void changeStock(
            String tenantId,
            String sku,
            int quantity,
            long aggregateVersion,
            String correlationId) {

        // Demo chỉ minh họa xây sự kiện. Ứng dụng thật còn
        // cần kiểm tra quyền, transaction, lưu state/outbox, v.v.
        String businessKey = tenantId + "|" + sku;

        InventoryChangedEvent event = new InventoryChangedEvent(
            UUID.randomUUID().toString(),
            "InventoryChanged",
            tenantId,
            sku,
            quantity > 0,
            quantity,
            aggregateVersion
        );

        eventPublisher.publish(event, correlationId, businessKey);
    }
}
~~~

**Các quy tắc quan trọng:**

- `eventId` sinh **một lần cho sự kiện logic**; nếu thực hiện lại delivery cho chính sự kiện đó, nên giữ nguyên ID đã lưu (ví dụ từ outbox), không gọi `UUID.randomUUID()` lại cho mỗi retry.
- `correlationId` đến từ ngữ cảnh request/workflow; **không tự thay bằng eventId**.
- `businessKey` được xây từ tenant + SKU để grouping theo aggregate.
- `aggregateVersion` cần đến từ phiên bản state thật nếu dùng cho ordering; giá trị đưa vào `changeStock` chỉ minh họa, không phải bảo đảm tự động tuần tự.
- Để tránh mất event giữa cập nhật DB và publish, ứng dụng production có thể cần **transactional outbox** hoặc cơ chế đảm bảo phù hợp. Contract test không thay thế kiểm chứng tính nhất quán transaction.

## 13. Adapter: custom businessKey chưa phải broker key

Một adapter có thể đặt application headers khi gửi qua Spring Cloud Stream:

~~~java
package com.example.inventory;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Component;

@Component
public class StreamInventoryEventPublisher
        implements InventoryEventPublisher {

    private final StreamBridge bridge;

    public StreamInventoryEventPublisher(StreamBridge bridge) {
        this.bridge = bridge;
    }

    @Override
    public void publish(
            InventoryChangedEvent event,
            String correlationId,
            String businessKey) {

        Message<InventoryChangedEvent> message =
                MessageBuilder.withPayload(event)
                    .setHeader("correlationId", correlationId)
                    .setHeader("businessKey", businessKey)
                    .setHeader("eventType", "InventoryChanged")
                    .setHeader("schemaVersion", "1")
                    .build();

        boolean accepted = bridge.send(
            "inventoryChanged-out-0", message
        );

        if (!accepted) {
            throw new IllegalStateException("Failed to send event");
        }
    }
}
~~~

Ví dụ trên có chủ đích tách **logical binding name** `inventoryChanged-out-0` khỏi **destination broker** `inventory.events`. Trong Spring Cloud Stream, cấu hình binding có thể ánh xạ tên binding sang destination:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventoryChanged-out-0:
          destination: inventory.events
~~~

Cấu hình này chỉ mang tính minh họa; nó không được viết vào một tệp thực của dự án ở bước học này.

**Chưa đủ để khẳng định có Kafka record key.** `setHeader("businessKey", ...)` mới tạo một **application header**. Với Kafka binder, cần ánh xạ nó thành **Kafka key** bằng API/header/config binder phù hợp phiên bản (ví dụ cơ chế `KafkaHeaders.KEY` nếu adapter đang dùng hỗ trợ). Với RabbitMQ, phải cấu hình exchange/routing key riêng.

Không tự giả định tên header Kafka của mọi phiên bản Spring Kafka/Spring Cloud Stream là giống nhau. Kiểm tra **record key thực tế ở broker hoặc producer adapter integration test**, không chỉ thấy businessKey trong JSON.

### Vì sao không kiểm tra mỗi boolean send?

`StreamBridge.send(...)` báo việc gửi qua abstraction tương ứng; giá trị thành công **không tự chứng minh** broker đã lưu bền vững và consumer xử lý event. Phần xác nhận delivery, retry, outbox, DLQ và acknowledgement có những test/đảm bảo riêng.

## 14. Base test: kích hoạt production use case, không tự phát message

Generated message contract test cần cách kích hoạt event. Ví dụ trong producer test base:

~~~java
package com.example.inventory;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    InventoryApplicationService inventoryService;

    public void triggerInventoryChanged() {
        inventoryService.changeStock(
            "tenant-a",
            "SKU-123",
            12,
            7L,
            "corr-1001"
        );
    }
}
~~~

Trong dự án thực, base test còn phải cấu hình **message verifier/test binder** thích hợp để SCC quan sát output. Nếu có database, cần fixture/transaction để trạng thái ban đầu ổn định. Generated test phải được nối với Spring context và message infrastructure của producer.

**Phản ví dụ sai mục tiêu:**

~~~java
// Không nên: base test tự đóng gói message giống contract.
public void triggerInventoryChanged() {
    testSink.send(
        "inventory.events",
        "{\"eventType\":\"InventoryChanged\","
        + "\"sku\":\"SKU-123\",\"quantity\":12}"
    );
}
~~~

Cách sai tạo một event đúng mẫu ở **test helper**, không đi qua `InventoryApplicationService` hay adapter production. Producer có thể mất correlationId, gửi sai destination hoặc tính `available` sai mà generated test vẫn xanh.

**Phép thử xác nhận:** tạm làm sai một trong các bước production, chẳng hạn bỏ header `correlationId` khỏi adapter hoặc đổi `quantity` thành 11. Generated producer test đúng phạm vi phải **đỏ** ở assertion tương ứng. Sau đó khôi phục code.

## 15. Contract Verifier quan sát những gì?

Message contract có thể kiểm tra các điều kiện được mô tả:

- Sự kiện được **phát ra sau trigger** phù hợp.
- `sentTo('inventory.events')` khớp destination quan sát bởi message verifier.
- Body JSON có các field bắt buộc và kiểu/giá trị đúng.
- Các header như `correlationId`, `businessKey`, `eventType`, `schemaVersion` xuất hiện và thỏa kỳ vọng.
- Giá trị động, ví dụ `eventId`, khớp matcher thích hợp.
- Generated test **được sinh và thực thi**, không chỉ tồn tại dưới dạng file contract.

Nhưng không nên suy ra rằng một generated message test tự động kiểm chứng:

- Kafka record key thực tế và partition được broker chọn.
- RabbitMQ exchange type, queue binding hoặc routing key.
- Consumer group, offset commit, broker ACL/TLS.
- Delivery lặp, idempotency, exactly-once, DLQ, retry/backoff.
- Thứ tự toàn hệ thống hoặc tính nhất quán DB–message.
- Thời gian latency thực tế qua network/broker production.

Những điều đó cần **integration tests ở adapter/broker** hoặc kiểm tra vận hành riêng. SCC là lớp cam kết giao tiếp quan trọng, không thay thế toàn bộ kiểm thử event-driven.

## 16. Header matcher: tĩnh, động và propagation

Contract ví dụ dùng `correlationId: corr-1001` để generated producer test có thể xác nhận **giá trị được truyền từ trigger**. Trong hệ thống thực, correlation ID thay đổi theo mỗi workflow.

Có ba cách thiết kế kiểm thử:

1. **Mẫu xác định:** base test gọi use case với `corr-1001`, contract yêu cầu đúng `corr-1001`. Cách này chứng minh propagation cho một input xác định.
2. **Matcher định dạng:** kiểm tra correlation ID tuân theo regex/format được phép khi ID được sinh động. Cần dùng cơ chế matcher headers của DSL/version đang dùng, sau đó xem generated assertion.
3. **Integration test bổ sung:** gọi producer với **hai correlation ID khác nhau**, quan sát event tương ứng và chứng minh ID đầu vào được phản ánh chính xác, không phải hằng số hardcode.

Một producer luôn phát `corr-1001` có thể vượt qua contract mẫu cố định nhưng **thất bại** ở integration test với `corr-2002`. Vì vậy, matcher regex chỉ kiểm tra hình thức chưa chắc chứng minh **quan hệ với ngữ cảnh đầu vào**.

### Trường hợp header thiếu, rỗng và sai format

| Đầu vào hoặc header đầu ra | Quy tắc cần xác định |
|---|---|
| Không có correlation ID | Sinh mới, từ chối hoặc chuyển sang chính sách khác? |
| `correlationId: ""` | Có được chấp nhận không? |
| Giá trị rất dài | Giới hạn độ dài để ngăn log/trace abuse |
| Giá trị chứa xuống dòng | Phải bị từ chối hoặc chuẩn hóa an toàn |
| Cùng ID ở header và body | Hai giá trị có buộc khớp không? |
| Trace ID có nhưng correlation ID không có | Có map một chiều hay giữ độc lập? |

Không nên để test chỉ kiểm tra header **tồn tại** trong khi consumer thật cần header **chính xác của request cụ thể**.

## 17. Business key và thứ tự sự kiện theo aggregate

Với tồn kho, hai event có thể xảy ra liên tiếp:

~~~text
eventId=evt-101   businessKey=tenant-a|SKU-123   aggregateVersion=7
eventId=evt-102   businessKey=tenant-a|SKU-123   aggregateVersion=8
~~~

Nếu cùng business key được ánh xạ đúng thành Kafka record key, hai event thường được đưa đến cùng partition trong một cấu hình ổn định. Consumer có thể dùng `aggregateVersion` để nhận diện **event cũ/đến trễ** hoặc kiểm tra mất thứ tự.

Không chỉ dựa vào thứ tự broker:

- Một consumer có thể xử lý bất đồng bộ và hoàn thành handler không theo thứ tự.
- Retry hoặc dead-letter/re-publish có thể làm luồng xử lý bị gián đoạn.
- Thay số partition hoặc thuật toán partitioning có thể thay đổi nơi lưu các record mới.
- Nhiều producer đồng thời phát cho cùng aggregate cần cơ chế kiểm soát version/state để giữ thứ tự ý nghĩa.
- Business key bị viết khác chữ hoa/thường hoặc tenantId có/không sẽ tách cùng aggregate thành nhiều key.

Một test hữu ích là phát hai event cùng key với version 7 và 8, xác minh adapter gửi đúng key, consumer cập nhật state theo chính sách version, và thử event cũ đến sau. Contract test đơn lẻ với một event không tự chứng minh được các điều kiện ordering này.

## 18. Correlation và idempotency qua một chuỗi sự kiện

Giả sử Inventory Service phát `InventoryChanged`, Checkout Service xử lý rồi phát `CheckoutUpdated`:

~~~mermaid
sequenceDiagram
    participant HTTP as API Request
    participant Inventory as Inventory Service
    participant Broker as Message Broker
    participant Checkout as Checkout Service
    HTTP->>Inventory: changeStock(correlationId=corr-1001)
    Inventory->>Broker: InventoryChanged(eventId=evt-101, key=tenant-a|SKU-123)
    Broker-->>Checkout: deliver evt-101, corr-1001
    Checkout->>Checkout: dedup theo eventId; xử lý nghiệp vụ
    Checkout->>Broker: CheckoutUpdated(eventId=evt-202, correlationId=corr-1001)
    Broker-->>Checkout: redeliver evt-101
    Checkout->>Checkout: nhận ra đã xử lý evt-101
~~~

Quy tắc:

- **Correlation ID** giữ nguyên trong workflow nếu các bước thuộc cùng yêu cầu.
- **Event ID** của `CheckoutUpdated` khác `InventoryChanged` vì đó là một sự kiện logic khác.
- **Business key** có thể đổi từ SKU sang order ID khi bước tiếp theo nói về aggregate khác.
- **Causation ID** (nếu dùng) của `CheckoutUpdated` có thể trỏ đến `evt-101`.
- Redelivery của `evt-101` nên giữ event ID để consumer có thể bỏ qua xử lý trùng.

Contract messaging cho một output có thể bảo vệ header/payload; để kiểm tra idempotency và chuỗi nhiều sự kiện, cần **consumer handler tests, integration tests và state assertions** tương ứng.

## 19. Stub Runner và kiểm tra phía consumer

Sau khi producer tạo stub từ contract, consumer có thể dùng **Stub Runner** để phát một message mô phỏng theo label của contract. Ví dụ cấu hình test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryEventConsumerContractTest {
    // Consumer test cần có message test infrastructure phù hợp.
}
~~~

Trong môi trường sử dụng `LOCAL`, stub JAR phải sẵn trong Maven local repository. Với môi trường CI tách job, có thể cấu hình repository từ xa và mode phù hợp.

Ở một số API của Stub Runner messaging, test có thể dùng `StubTrigger` để kích hoạt message theo label:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.contract.stubrunner.StubTrigger;

@Autowired
StubTrigger stubTrigger;

void triggerStubMessage() {
    stubTrigger.trigger("inventoryChanged");
}
~~~

Đây là **đoạn minh họa** phải đặt trong class test, còn messaging adapter/test binder và consumer listener cần được cấu hình. Tên package, API trigger và mode hỗ trợ phụ thuộc phiên bản SCC. Test cần kiểm tra consumer **thực sự nhận** message và xử lý các field/header.

Một consumer test nên xác minh:

1. Listener nhận message từ đúng destination/subscription mà môi trường test hỗ trợ.
2. `correlationId` được lấy ra và truyền vào bước xử lý/log phù hợp.
3. `businessKey` hoặc aggregate fields được ánh xạ đúng đối tượng.
4. `eventId` giúp dedup khi cùng event được phát hai lần.
5. `schemaVersion` được đọc đúng, body map sang DTO hợp lệ.
6. Hành vi xử lý của consumer đúng, không chỉ “message được trigger”.

**Giới hạn:** Stub Runner messaging có thể mô phỏng message ở tầng contract/test binder. Nó không nhất thiết tái tạo chính xác Kafka partition key, Rabbit exchange binding hay broker acknowledgment. Với những ràng buộc này, cần integration test với adapter/broker.

## 20. Test broker/adapter cho khóa phân vùng và routing

Nếu business key phải biến thành Kafka record key, test nên kiểm tra **record thực tế**, không chỉ header tự tạo. Với Kafka, một test dùng Embedded Kafka hoặc Testcontainers Kafka có thể:

1. Khởi động broker test với topic có cấu hình xác định.
2. Chạy producer adapter production với message business key.
3. Đọc record bằng Kafka consumer test.
4. Assert **topic**, **record.key()**, headers và payload.
5. Phát hai event cùng business key, kiểm tra partition trong cấu hình test ổn định.
6. Thử key khác tenant/SKU và xác nhận quy tắc canonicalization.

Mẫu assertion khái niệm:

~~~java
// Mã minh họa bên trong broker integration test đã cấu hình.
// record là ConsumerRecord<String, byte[]> đọc từ broker test.
assertThat(record.topic()).isEqualTo("inventory.events");
assertThat(record.key()).isEqualTo("tenant-a|SKU-123");
assertThat(record.value()).isNotEmpty();
~~~

Đừng kết luận hai key khác nhau **bắt buộc** vào hai partition khác nhau: partitioner có thể băm ra cùng partition. Điều cần bảo vệ là **key đúng**, và nếu cần ordering cùng aggregate, kiểm tra tính nhất quán của partition trong cấu hình đang sử dụng.

Với RabbitMQ, bài test tương ứng cần xác nhận exchange, routing key, queue binding và nơi consumer thực sự nhận message. Kafka record key và Rabbit routing key có mục tiêu khác nhau, không dùng một assertion chung cho cả hai.

## 21. Dữ liệu định tuyến sai gây lỗi như thế nào?

| Thay đổi | Kết quả có thể xảy ra | Test cần có |
|---|---|---|
| Đổi `inventory.events` thành `inventory.v2.events` | Consumer subscribe topic cũ không nhận event | Contract `sentTo` và adapter/broker integration |
| Bỏ header `correlationId` | Mất liên kết trace/workflow | Generated producer test + consumer handler test |
| Dùng `eventId` làm Kafka key thay business key | Event cùng SKU bị phân tán sang partition khác | Broker adapter test kiểm tra record key |
| Đổi key từ `tenant-a|SKU-123` sang `SKU-123` | Các tenant có thể va chạm grouping | Unit test key builder + broker test |
| Đổi `schemaVersion` từ string `"1"` thành số 1 | Consumer parsing/header handling có thể hỏng | Contract header + consumer compatibility test |
| Đổi Rabbit routing key | Message đi sai queue hoặc không có binding nhận | Rabbit integration test |
| Đổi field `sku` thành `productId` | Consumer không deserialize/read đúng | Producer contract + consumer stub mới |
| Sinh eventId mới cho mỗi retry của cùng event | Consumer dedup không còn hoạt động | Outbox/retry/idempotency integration test |
| Gửi event cùng aggregate sai thứ tự | Consumer có state cũ hoặc logic sai | Version/order handling test |

**Chẩn đoán:** nếu consumer không thấy event, đừng chỉ kiểm tra body JSON. Hãy lần theo destination → binding → broker route/key → consumer group/queue → serialization → listener.

## 22. Header không tin cậy và rủi ro bảo mật

Correlation ID và business key thường xuất hiện trong log và metrics, đôi khi đi qua nhiều tổ chức hoặc nhiều tenant. Chúng cần được xử lý như dữ liệu đầu vào:

- **Validate format, length, character set**; không cho giá trị quá dài hoặc chứa ký tự điều khiển được ghi thẳng vào log.
- **Không coi tenantId trong header tự khai báo là căn cứ phân quyền**. Phải đối chiếu với authentication/authorization context đáng tin cậy.
- **Không nhúng thông tin cá nhân** vào correlation ID hoặc broker key nếu không cần thiết; có thể dùng ID ngẫu nhiên/opaque hoặc khóa được mã hóa/băm theo chính sách.
- **Giảm cardinality không kiểm soát** trong metrics: correlation ID riêng từng request không phù hợp làm label cho time-series có giới hạn.
- **Tránh leakage giữa tenant**: sự kiện routing sai tenant có thể nghiêm trọng hơn lỗi functional thông thường.
- **Giữ schema cho metadata ổn định** và có quy tắc xử lý header không hợp lệ.
- Nếu sử dụng tracing headers (như `traceparent`), dùng thư viện propagation theo chuẩn, đừng tự thay đổi ID bằng string tùy ý.

Contract test có thể kiểm tra field và format, nhưng kiểm tra ACL, authorization, isolation và broker security vẫn cần các test bảo mật/tích hợp riêng.

## 23. Schema evolution: thay đổi header cũng có thể breaking

Không chỉ thay body mới làm consumer hỏng. Header và routing metadata có thể là một phần API/message contract.

Ví dụ phiên bản 1 dùng:

~~~text
correlationId: corr-1001
businessKey: tenant-a|SKU-123
schemaVersion: "1"
destination: inventory.events
~~~

Phiên bản 2 muốn đổi:

~~~text
traceId: corr-1001
partitionKey: tenant-a:SKU-123
schemaVersion: "2"
destination: inventory.v2.events
~~~

Nếu consumer đang đọc `correlationId` hoặc subscribe `inventory.events`, việc thay tên/cách encode có thể **phá tương thích** dù body vẫn giữ nguyên.

Một kế hoạch tiến hóa thường có giai đoạn:

1. **Expand:** producer tiếp tục cung cấp header/destination cũ trong khi thêm metadata/đường gửi mới nếu hệ thống cần.
2. **Migrate:** consumer mới biết đọc/subscribe theo quy ước mới; chạy test với cả stub cũ và stub ứng viên.
3. **Contract:** chỉ loại bỏ cách cũ sau khi các consumer cần hỗ trợ đã chuyển đổi.
4. **Release gate:** không phát hành bản mới khi tương thích chưa được kiểm chứng hoặc chưa có kế hoạch versioning.

Khi dùng **dual-publish** sang hai topic để chuyển đổi, cần thiết kế idempotency và event identity rõ ràng: cùng một sự kiện logic được gửi qua hai kênh có thể bị cùng một consumer xử lý trùng.

## 24. CloudEvents và tracing: có thể áp dụng nhưng không nên trộn ID

Một số hệ thống sử dụng **CloudEvents** để chuẩn hóa envelope sự kiện. Các thuộc tính như `id`, `source`, `type`, `subject`, `time` có ý nghĩa của chuẩn. Ví dụ:

~~~json
{
  "specversion": "1.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": "/inventory-service",
  "type": "com.example.inventory.changed.v1",
  "subject": "tenant-a/SKU-123",
  "time": "2026-11-24T04:00:00Z",
  "data": {
    "tenantId": "tenant-a",
    "sku": "SKU-123",
    "quantity": 12
  }
}
~~~

CloudEvents `id` kết hợp với `source` phục vụ định danh sự kiện theo semantics chuẩn. `subject` có thể giúp mô tả đối tượng nguồn, nhưng không mặc nhiên là Kafka record key. **Correlation ID** vẫn là một khái niệm riêng, có thể được mang qua extension attribute hoặc header theo quy ước.

Nếu dùng W3C Trace Context, `traceparent` và các tracing baggage/headers cần được propagate bởi thư viện phù hợp; đừng mặc nhiên coi `traceId` bằng `eventId` hoặc `businessKey`.

Bài này không yêu cầu chuyển sang CloudEvents. Ý nghĩa chính là **đừng chọn ngẫu nhiên một ID rồi dùng nó cho mọi mục đích**; khi áp dụng một chuẩn envelope, hãy giữ semantics của chuẩn và kiểm thử sự chuyển đổi.

## 25. Đưa message contracts vào CI/CD

Một pipeline bảo vệ tương thích có thể chia thành các cổng:

~~~mermaid
flowchart TD
    A["PR thay producer, contract hoặc adapter"] --> B["Parse/generate message contract tests"]
    B --> C["Chạy generated producer tests với app flow thật"]
    C --> D{"Header/body/destination đạt?"}
    D -- "Không" --> X["BLOCK"]
    D -- "Có" --> E["Broker/adapter tests cho key/routing"]
    E --> F{"Key/topic/binding đúng?"}
    F -- "Không" --> X
    F -- "Có" --> G["Đóng gói stub ứng viên"]
    G --> H["Consumer tests dùng Stub Runner"]
    H --> I{"Consumer xử lý event đúng?"}
    I -- "Không" --> X
    I -- "Có" --> J["Tiếp tục release gates"]
~~~

Trong một producer Maven đã cấu hình plugin:

~~~bash
./mvnw clean verify
~~~

Với Gradle có Spring Cloud Contract plugin tương ứng:

~~~bash
./gradlew clean test
~~~

Các lệnh trên **chỉ mang tính minh họa vòng build**: tên task, test base, message verifier và cách đóng gói stub tùy plugin/version. Không suy ra contract messaging đã chạy nếu chỉ thấy build exit 0.

CI cần lưu bằng chứng:

- Contract được phát hiện, generated test **thực sự chạy** và quan sát message từ production trigger.
- Header, payload, destination đã được kiểm chứng; không có matcher quá lỏng.
- Kết quả adapter/broker integration cho Kafka key hoặc Rabbit routing khi có ràng buộc tương ứng.
- Artifact stub đúng **group, artifact, version, classifier, commit**; không dùng nhầm cache.
- Consumer đã kích hoạt stub/message, listener thực sự xử lý và các assertion đạt.
- Retry/dedup/order tests cho những yêu cầu đặc biệt của nghiệp vụ.

**Không nên chỉ cho CI xanh khi một tệp JSON fixture parse hợp lệ.** Trong hệ thống message-driven, metadata và routing sai có thể khiến consumer không bao giờ nhìn thấy event.

## 26. Bài thực hành theo bốn vòng

### Vòng A — Phân tích metadata

Với sự kiện `InventoryChanged`, lập bảng giải thích:

1. `correlationId = corr-1001`: các event nào trong workflow cùng chia sẻ?
2. `eventId = 550e8400-e29b-41d4-a716-446655440000`: điều gì xảy ra khi redelivery?
3. `businessKey = tenant-a|SKU-123`: vì sao cần tenantId?
4. Destination `inventory.events` là logic application hay broker topic?
5. Với Kafka, field nào phải được đưa thành **record key** để grouping theo SKU?

**Đầu ra:** sơ đồ propagation và bảng owner của từng field/header/transport.

### Vòng B — Viết message contract và producer test

1. Viết Groovy hoặc YAML message contract từ phần 9/10.
2. Đặt `label`, `triggeredBy`, `sentTo`, headers, body và matcher UUID cho event ID.
3. Tạo test base gọi `InventoryApplicationService.changeStock(...)` thật.
4. Cấu hình message verifier/test binder và chạy generated producer tests.
5. Cố tình bỏ `correlationId` hoặc đổi destination trong adapter; test phù hợp phải phát hiện lỗi.

**Đầu ra:** contract, base test, generated source/test report, bằng chứng thử sai có chủ đích.

### Vòng C — Kiểm tra broker routing và idempotency

1. Dùng broker test hoặc test adapter, publish event với `businessKey`.
2. Đọc Kafka record (nếu dùng Kafka), xác nhận `record.key()` và topic.
3. Phát hai event cùng SKU với `aggregateVersion` tăng dần, kiểm tra partition/order trong phạm vi cấu hình ổn định.
4. Phát lại **cùng eventId**, consumer không được áp dụng thay đổi nghiệp vụ hai lần nếu yêu cầu idempotent.
5. Đổi tenant nhưng giữ SKU, xác nhận key không bị va chạm.

**Đầu ra:** log/record key, test result cho dedup, phân tích giới hạn ordering.

### Vòng D — Consumer contract và thay đổi breaking

1. Đóng gói stub ứng viên từ đúng commit.
2. Cho Checkout dùng Stub Runner trigger label `inventoryChanged`; kiểm tra listener xử lý metadata.
3. Đổi `correlationId` thành `traceId` hoặc đổi destination trong một nhánh thử.
4. Quan sát producer/consumer tests nào thất bại.
5. Lập kế hoạch chuyển đổi để consumer cũ không mất event.

**Đầu ra:** stub coordinate, consumer test report, danh sách breaking changes và phương án migration.

## 27. Checklist trước khi hợp nhất message contract

- [ ] Mỗi field `correlationId`, `eventId`, `businessKey` có vai trò và chủ sở hữu được mô tả rõ.
- [ ] Không dùng correlation ID làm event ID hoặc Kafka partition key nếu semantics không phù hợp.
- [ ] Event ID ổn định cho redelivery của **cùng sự kiện logic**.
- [ ] Business key bao gồm đủ thành phần nhận diện aggregate, nhất là tenant.
- [ ] Header/payload/transport key được ánh xạ rõ và không mâu thuẫn.
- [ ] Contract mô tả đúng `label`, `triggeredBy`, `sentTo`, header và body.
- [ ] Generated producer test gọi **production use case**, không tự gửi JSON mẫu từ base test.
- [ ] Message verifier/test binder quan sát đúng destination và headers.
- [ ] Nếu dùng Kafka partition key, có adapter/broker test xác nhận **`record.key()` thực tế**.
- [ ] Nếu dùng RabbitMQ routing, có kiểm tra exchange/routing key/queue binding.
- [ ] Có kiểm tra header thiếu, blank, sai format và input không tin cậy khi cần.
- [ ] Consumer dùng event ID cho dedup theo chính sách; không đồng nhất với correlation ID.
- [ ] Các thay đổi header, schema version hoặc destination đã được đánh giá là có thể breaking.
- [ ] Consumer test dùng Stub Runner với stub ứng viên đúng version/commit.
- [ ] CI xác nhận số generated tests > 0, lưu test report, artifact và broker test result.
- [ ] Có kế hoạch retry, DLQ, order và dedup khi nghiệp vụ yêu cầu; không suy ra chúng từ contract đơn lẻ.

## 28. Câu hỏi tự kiểm tra

**1. Correlation ID và event ID khác nhau thế nào?**

Correlation ID nhóm **nhiều bước trong cùng workflow**. Event ID định danh **một sự kiện logic**; các lần redelivery của sự kiện đó nên giữ nguyên event ID để consumer có thể chống xử lý trùng.

**2. Business key có tự trở thành Kafka record key khi đặt trong header không?**

Không. `businessKey` là metadata ứng dụng. Producer adapter hoặc binder phải ánh xạ nó thành Kafka key bằng cơ chế hỗ trợ của phiên bản dùng trong dự án, rồi kiểm tra record thật.

**3. `sentTo('inventory.events')` có chứng minh Kafka partition key và RabbitMQ routing key đúng không?**

Không. Nó mô tả destination mà message contract verifier quan sát. Kafka key/partition và Rabbit routing cần integration tests với adapter/broker nếu thuộc cam kết quan trọng.

**4. Nếu hai event khác nhau có cùng correlation ID thì consumer có được dedup theo correlation ID không?**

Thông thường không. Hai event có thể thuộc cùng workflow nhưng đều cần được xử lý; dedup theo correlation ID sẽ làm mất event hợp lệ.

**5. Vì sao base test không nên tự gửi message mẫu?**

Vì test có thể đạt dù production code không phát event, thiếu header hoặc route sai. Base test phải kích hoạt production use case để generated test quan sát output thật.

**6. Vì sao đổi destination/topic cũng có thể là breaking change?**

Vì consumer subscribe nơi cũ có thể **không nhận được message** dù body JSON không đổi. Cần phối hợp triển khai, kiểm tra routing và có chiến lược chuyển đổi.

**7. Vì sao cùng business key thường hữu ích cho Kafka nhưng không bảo đảm thứ tự toàn hệ thống?**

Vì partitioner có thể đưa record cùng key vào một partition, nơi Kafka duy trì thứ tự log. Nhưng không có thứ tự toàn cục giữa partition và còn có các yếu tố retry, concurrent processing, thay partition count và nhiều producer.

## 29. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): message contracts, generated producer tests và Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): DSL Groovy/YAML, message input/output và matcher.
- [Spring Cloud Contract – Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): kiểm thử hợp đồng thông điệp và message infrastructure (đối chiếu URL/phiên bản tài liệu khi áp dụng).
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): bindings, destination và binder-specific message metadata.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): Kafka record keys, headers, producer/consumer.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): topic, partition và delivery semantics.
- [RabbitMQ Tutorials](https://www.rabbitmq.com/tutorials): exchanges, routing keys, queues và bindings.
- [CloudEvents Specification](https://github.com/cloudevents/spec): chuẩn envelope và các thuộc tính `id`, `source`, `type`, `subject`.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): cấu trúc `traceparent` và propagation.

**Lưu ý phiên bản:** Cú pháp message DSL, khả năng matcher trên header/body, `StubTrigger`, message verifier và cách binder ánh xạ Kafka/Rabbit metadata phụ thuộc phiên bản SCC/Spring Cloud Stream/broker adapter. Luôn kiểm tra **generated test, stub mapping và record thực tế** theo bộ phiên bản dự án đang dùng. Ví dụ là tài liệu học tập, không phải kết quả build đã được chạy.

---

**Điểm cần nhớ:** `correlationId` liên kết các bước của một workflow; `eventId` nhận diện một sự kiện logic và giúp chống redelivery; `businessKey` chỉ aggregate để grouping và có thể trở thành partition key **nếu adapter ánh xạ đúng**. `sentTo` mô tả nơi phát message ở mức contract, còn Kafka key, partition và Rabbit routing cần kiểm chứng theo transport. Một message contract đáng tin phải bảo vệ **body + headers + destination**, đi qua **producer code thật**, rồi kiểm tra consumer bằng **stub ứng viên** và các bài test broker/adapter cần thiết trong CI.
