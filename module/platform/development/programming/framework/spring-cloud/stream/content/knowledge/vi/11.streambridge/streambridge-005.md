# Phân biệt binding có sẵn với destination động

Trong Spring Cloud Stream, ứng dụng thường gửi message qua binding đầu ra được khai báo trong cấu hình. Tuy nhiên, có những lúc đích gửi chỉ được biết khi chương trình đang chạy, chẳng hạn gửi thông báo đến luồng của một tenant, một nhóm khách hàng hoặc một miền nghiệp vụ được chọn theo dữ liệu đầu vào. `StreamBridge` hỗ trợ cả hai cách: gửi qua binding đã cấu hình trước và gửi đến destination được tạo binding khi cần.

Hai cách này có liên quan nhưng không giống nhau. Với binding có sẵn, ứng dụng biết tên binding và cấu hình ánh xạ nó đến destination, binder cùng các thuộc tính producer. Với destination động, ứng dụng cung cấp tên đích lúc gọi `StreamBridge`; Spring Cloud Stream có thể tạo output binding khi lần gửi đầu tiên xảy ra. Khả năng tạo topic, exchange hoặc tài nguyên tương ứng còn phụ thuộc binder, broker, quyền và chính sách provisioning.

Bài thuộc chương **StreamBridge** của module `SPRING_CLOUD_STREAM`, tập trung vào cách chọn giữa cấu hình tĩnh và đích động, cách đặt tên, kiểm soát tài nguyên, xử lý lỗi và kiểm thử.

## 1. StreamBridge giải quyết nhu cầu nào?

Mô hình hàm `Supplier`/`Function`/`Consumer` phù hợp khi luồng message gắn trực tiếp với một hàm. Nhưng một ứng dụng Spring cũng có thể cần gửi message từ một thành phần imperative, chẳng hạn REST controller, service nghiệp vụ, listener của một hệ thống khác hoặc một quy trình xử lý đồng bộ. `StreamBridge` cung cấp API để gửi payload hoặc Spring `Message<?>` vào output binding mà không cần viết một function chỉ để chuyển tiếp message.

Ví dụ, sau khi người dùng cập nhật địa chỉ giao hàng, một service phát sự kiện `AddressChanged`:

```text
REST request
    |
    v
AddressService
    |
    | StreamBridge.send(...)
    v
Output binding
    |
    v
Binder
    |
    v
Kafka / RabbitMQ / Pulsar
```

`StreamBridge` không thay thế binder. Nó gửi message vào một binding; binder vẫn chịu trách nhiệm kết nối với broker và chuyển message theo cấu hình của binding đó.

## 2. Phân biệt binding name và destination

Đây là nền tảng để hiểu binding có sẵn và destination động:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Binding name | Tên điểm kết nối logic trong ứng dụng Spring Cloud Stream | `auditOutput` |
| Destination | Tên đích mà binder ánh xạ tới tài nguyên của broker | `audit.events` |
| Binder | Thành phần tích hợp với một loại broker | Kafka binder, Rabbit binder, Pulsar binder |
| Tài nguyên vật lý | Đối tượng broker thực sự nhận hoặc lưu message | Kafka topic, RabbitMQ exchange/queue, Pulsar topic |

Với binding được khai báo trước, tên binding có thể khác tên destination. Ví dụ `auditOutput` ánh xạ tới destination `audit.events`. Khi gọi `StreamBridge.send`, ứng dụng dùng tên binding `auditOutput`.

Với destination động, tên truyền cho `StreamBridge` thường đồng thời là tên binding được tạo khi chạy và tên destination mà binder sử dụng. Ví dụ gọi `send("tenant-42.events", event)` sẽ yêu cầu gửi đến đích `tenant-42.events`; không cần khai báo sẵn một function binding cho từng tenant.

Không nên dùng lẫn hai loại tên. Nếu đã khai báo binding `auditOutput` trỏ tới `audit.events`, gọi `send("audit.events", event)` là một yêu cầu khác với `send("auditOutput", event)`; tên truyền vào được diễn giải như tên binding/destination theo cơ chế resolve của StreamBridge.

## 3. Binding đầu ra có sẵn

Binding có sẵn là binding được khai báo rõ trong cấu hình ứng dụng. Khi ứng dụng cần tạo output binding không gắn với output của một `Function`, có thể liệt kê tên binding trong `spring.cloud.stream.output-bindings`.

Ví dụ khai báo một binding tên `auditOutput` và ánh xạ nó tới destination `audit.events`:

```yaml
spring:
  cloud:
    stream:
      output-bindings: auditOutput
      bindings:
        auditOutput:
          destination: audit.events
          content-type: application/json
```

`output-bindings` yêu cầu framework tạo output binding có tên `auditOutput`. Phần `bindings.auditOutput` mô tả destination và content type. Tên binding không bắt buộc trùng với tên topic hoặc exchange.

Service có thể gửi sự kiện qua binding đó:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record AuditEvent(String actorId, String action, String resourceId) {}

@Service
class AuditPublisher {

    private final StreamBridge streamBridge;

    AuditPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(AuditEvent event) {
        boolean accepted = streamBridge.send("auditOutput", event);
        if (!accepted) {
            throw new IllegalStateException("Could not send audit event");
        }
    }
}
```

Trong ví dụ này, code Java chỉ biết binding name `auditOutput`. Destination thực tế, content type và cấu hình producer được quản lý ở cấu hình Spring Cloud Stream. Khi đổi destination theo môi trường, có thể thay cấu hình mà không cần sửa lời gọi trong service.

### Khi nào nên khai báo trước?

Binding có sẵn phù hợp khi:

- Các destination đã biết trước và số lượng ổn định.
- Mỗi luồng cần content type, partitioning, retry, header mapping hoặc thuộc tính producer riêng.
- Hạ tầng cần được provision và review trước khi ứng dụng triển khai.
- Muốn kiểm soát rõ quyền truy cập, tên tài nguyên và cấu hình theo môi trường.
- Nhiều thành phần trong ứng dụng cần gửi vào cùng một luồng đã được chuẩn hóa.

Với các sự kiện nghiệp vụ cốt lõi như `orders.created`, `payments.authorized` hoặc `inventory.reserved`, binding có sẵn thường giúp hợp đồng và topology dễ quản lý hơn.

## 4. Destination động

Destination động được xác định khi chương trình đang chạy. Khi `StreamBridge` nhận một tên binding chưa được khai báo, framework có thể tạo output binding theo yêu cầu và sử dụng tên đó làm destination mặc định.

Ví dụ một ứng dụng gửi sự kiện đến destination theo tenant:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record TenantEvent(String tenantId, String eventType, String data) {}

@Service
class TenantEventPublisher {

    private final StreamBridge streamBridge;

    TenantEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String destination, TenantEvent event) {
        return streamBridge.send(destination, event);
    }
}
```

Nếu gọi `publish("tenant-42.events", event)`, ứng dụng yêu cầu StreamBridge gửi message đến destination `tenant-42.events`. Binding có thể được tạo ở lần gửi đầu tiên. Các lần gửi tiếp theo có thể sử dụng binding đã được tạo và quản lý trong runtime.

```text
Lần gửi đầu tiên
StreamBridge.send("tenant-42.events", event)
             |
             v
      Resolve binding name
             |
             v
      Chưa có binding?
             |
             v
      Tạo output binding động
             |
             v
      Binder kết nối destination
             |
             v
      Gửi message

Các lần gửi tiếp theo
             |
             v
      Dùng binding đã resolve
```

Destination động hữu ích khi số đích không thể liệt kê đầy đủ lúc triển khai hoặc khi một ứng dụng cần định tuyến theo dữ liệu runtime. Tuy nhiên, khả năng tự tạo tài nguyên phụ thuộc binder và broker. Ví dụ, Kafka có thể cần topic được tạo sẵn nếu auto topic creation bị tắt; RabbitMQ có thể cần exchange hoặc topology được provision; Pulsar có thể cần namespace và quyền tạo topic phù hợp.

## 5. Hạn chế destination động bằng allowlist

Nếu tên destination được lấy trực tiếp từ request hoặc dữ liệu người dùng, không nên chuyển tiếp chuỗi đó thẳng vào `StreamBridge.send`. Một giá trị tùy ý có thể khiến ứng dụng tạo hoặc truy cập tài nguyên ngoài dự kiến, gây tăng số lượng destination, làm khó kiểm soát quyền và tăng chi phí vận hành.

Spring Cloud Stream có thuộc tính `spring.cloud.stream.dynamicDestinations` để giới hạn các destination được phép tạo động. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - tenant-a.events
        - tenant-b.events
        - tenant-c.events
```

Khi cấu hình allowlist, chỉ những destination được phép mới có thể được resolve theo cơ chế dynamic destination của framework. Hãy kiểm tra hành vi và cú pháp đúng với phiên bản Spring Cloud Stream đang sử dụng, đặc biệt nếu ứng dụng kết hợp nhiều binder hoặc có quy tắc phân quyền riêng.

Ở tầng nghiệp vụ, nên ánh xạ một định danh đã được xác thực sang destination được ứng dụng quản lý:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class TenantEventRouter {

    private static final Map<String, String> DESTINATIONS = Map.of(
        "tenant-a", "tenant-a.events",
        "tenant-b", "tenant-b.events",
        "tenant-c", "tenant-c.events"
    );

    private final StreamBridge streamBridge;

    TenantEventRouter(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(String tenantId, TenantEvent event) {
        String destination = DESTINATIONS.get(tenantId);
        if (destination == null) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        if (!streamBridge.send(destination, event)) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
```

Allowlist trong cấu hình và kiểm tra tenant ở tầng nghiệp vụ bảo vệ hai ranh giới khác nhau: cấu hình giới hạn những đích mà framework được phép resolve; code nghiệp vụ xác định người gọi có quyền gửi đến đích nào.

## 6. So sánh hai cách

| Tiêu chí | Binding có sẵn | Destination động |
|---|---|---|
| Thời điểm xác định đích | Khi cấu hình ứng dụng | Khi ứng dụng chạy |
| Tên truyền vào `send` | Tên binding đã khai báo | Tên destination/binding động |
| Ánh xạ tên | Binding name có thể khác destination | Thường dùng tên động làm destination mặc định |
| Thuộc tính producer | Có thể cấu hình rõ theo từng binding | Thường dựa vào cấu hình mặc định hoặc cấu hình có sẵn cho binding tương ứng |
| Provisioning | Dễ quản lý trước khi triển khai | Có thể phát sinh lúc runtime, tùy binder và quyền broker |
| Số lượng đích | Thường hữu hạn, ổn định | Có thể thay đổi theo dữ liệu runtime |
| Kiểm soát truy cập | Dễ gắn quyền theo destination cố định | Cần allowlist và xác thực/ủy quyền ở tầng nghiệp vụ |
| Vận hành | Dễ theo dõi metric, cấu hình và topology | Cần quản lý vòng đời, cardinality và cleanup của nhiều đích |
| Trường hợp phù hợp | Luồng nghiệp vụ cốt lõi, destination ổn định | Định tuyến đến một tập đích được chọn ở runtime |

Không có cách nào tốt hơn trong mọi tình huống. Hãy chọn theo mức độ ổn định của topology, yêu cầu vận hành và cách phân quyền.

## 7. Content type và message headers

`StreamBridge.send` có thể gửi một đối tượng Java làm payload hoặc một Spring `Message<?>` nếu cần kiểm soát headers. Với binding có sẵn, có thể khai báo content type trong cấu hình:

```yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents
      bindings:
        orderEvents:
          destination: orders.events
          content-type: application/json
```

Gửi payload đơn giản:

```java
streamBridge.send("orderEvents", orderEvent);
```

Gửi message kèm metadata:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderEvent(String orderId, Instant occurredAt) {}

String correlationId = UUID.randomUUID().toString();
OrderEvent orderEvent = new OrderEvent("ORD-42", Instant.now());

Message<OrderEvent> message = MessageBuilder
    .withPayload(orderEvent)
    .setHeader("eventId", UUID.randomUUID().toString())
    .setHeader("eventType", "OrderPlaced")
    .setHeader("correlationId", correlationId)
    .build();

streamBridge.send("orderEvents", message);
```

Payload mang dữ liệu nghiệp vụ; headers mang metadata như event ID, correlation ID hoặc thông tin truy vết. Binder có thể ánh xạ header sang metadata riêng của broker, nhưng không phải header nào cũng được hỗ trợ hoặc giữ nguyên qua mọi binder. Hãy kiểm thử các header quan trọng với broker thật.

Với destination động, nếu mỗi đích có hợp đồng payload khác nhau, cần bảo đảm content type và kiểu message được xác định rõ. Không nên gửi các schema không liên quan vào cùng một destination mà không có discriminator hoặc quy tắc versioning.

## 8. Giá trị trả về của `send` có ý nghĩa gì?

`StreamBridge.send(...)` trả về boolean để cho biết message đã được gửi/được chấp nhận qua output channel theo cơ chế của StreamBridge hay chưa. Giá trị `true` không có nghĩa consumer phía sau đã xử lý nghiệp vụ thành công, cũng không tự chứng minh message đã được mọi replica hoặc hệ thống đích xác nhận bền vững.

Hãy phân biệt các mốc:

1. Ứng dụng gọi `send` và message được chấp nhận bởi output channel.
2. Binder/producer gửi message đến broker.
3. Broker xác nhận theo mức bảo đảm được cấu hình.
4. Consumer nhận message.
5. Consumer commit kết quả nghiệp vụ.

Mỗi mốc có cơ chế lỗi và bảo đảm riêng. Nếu nghiệp vụ cần xác nhận broker đã ghi message, hãy cấu hình và sử dụng cơ chế xác nhận của binder/producer phù hợp. Nếu cần biết consumer đã hoàn thành, cần một phản hồi nghiệp vụ hoặc trạng thái được lưu riêng.

Không nên coi boolean `true` là một transaction phân tán bao trùm database của ứng dụng và broker. Nếu service cập nhật database rồi gửi event, hãy xem xét transactional outbox để tránh trạng thái database đã commit nhưng message chưa được phát, hoặc message đã phát nhưng trạng thái gửi chưa được lưu.

## 9. Destination động và nhiều binder

Một ứng dụng có thể dùng nhiều binder, chẳng hạn Kafka cho event stream và RabbitMQ cho hàng đợi tác vụ. Binding có sẵn có thể chỉ định binder cụ thể trong cấu hình binding. Với destination động, cần có chiến lược xác định binder nào sẽ xử lý đích đó; không nên giả định chỉ tên destination là đủ để chọn đúng broker trong mọi cấu hình đa binder.

Khi cần nhiều broker, hãy cân nhắc:

- Khai báo binding có sẵn cho những luồng có yêu cầu broker cố định.
- Dùng cấu hình binder mặc định rõ ràng hoặc cấu hình ánh xạ được framework hỗ trợ cho các đích động.
- Không cho dữ liệu request quyết định tên binder hoặc endpoint broker.
- Kiểm thử từng đường gửi trên đúng binder, vì kiểu destination và metadata được ánh xạ khác nhau.

Nếu ứng dụng có nhiều binder và destination động có thể thuộc nhiều broker, hãy xác định rõ quy tắc định tuyến ở tầng ứng dụng hoặc tạo các publisher riêng có cấu hình rõ ràng. Tránh để một chuỗi đầu vào tùy ý quyết định nơi dữ liệu được gửi.

## 10. Provisioning và vòng đời destination

Binding có sẵn giúp hạ tầng có thể tạo tài nguyên trước khi ứng dụng khởi động. Với destination động, binding có thể được tạo khi gửi lần đầu, nhưng điều đó không đồng nghĩa mọi broker luôn tự tạo tài nguyên thành công.

| Broker | Destination đầu ra | Điều cần xác nhận khi dùng đích động |
|---|---|---|
| Kafka | Topic | Topic auto-create có được bật không; tài khoản producer có quyền ghi; partition và retention có đúng chính sách không |
| RabbitMQ | Exchange, sau đó định tuyến theo queue binding | Exchange có được tạo không; routing key và queue binding đã tồn tại chưa; message không được định tuyến được xử lý thế nào |
| Pulsar | Topic | Namespace có tồn tại không; quyền produce và chính sách auto topic creation có cho phép không |

Trong production, các tài nguyên quan trọng thường nên được provision bằng quy trình hạ tầng có kiểm soát. Với dynamic destination, cần xác định ai chịu trách nhiệm tạo, giám sát, thay đổi retention và dọn dẹp tài nguyên không còn dùng.

Nếu mỗi tenant tạo một topic riêng, số lượng tenant tăng có thể dẫn đến hàng nghìn topic, exchange hoặc queue. Điều này làm tăng chi phí metadata, giám sát, phân quyền, backup và vận hành. Một topic chung với `tenantId` trong payload/header và key phù hợp có thể đơn giản hơn nếu yêu cầu cách ly dữ liệu cho phép. Quyết định cần dựa trên yêu cầu bảo mật, retention, tải và quyền truy cập của từng tenant.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `send` không gửi được | Binding không resolve được, lỗi tạo channel hoặc cấu hình binder không hợp lệ | Kiểm tra tên binding, log StreamBridge và binder |
| Gửi nhầm destination | Dùng destination thay cho binding name đã cấu hình | Kiểm tra ánh xạ `bindings.<name>.destination` |
| Dynamic destination bị từ chối | Đích không nằm trong `dynamicDestinations` allowlist | Kiểm tra tên sau khi chuẩn hóa và allowlist |
| Binding được tạo nhưng broker không có tài nguyên | Broker tắt auto provisioning hoặc thiếu quyền | Kiểm tra topic/exchange/namespace, quyền và provisioning |
| RabbitMQ không có queue nhận message | Exchange tồn tại nhưng không có queue/routing binding phù hợp | Kiểm tra exchange type, routing key và queue binding |
| Consumer nhận payload sai kiểu | Content type hoặc schema không thống nhất | Kiểm tra content type, converter và payload thực |
| Số lượng destination tăng bất thường | Tên đích lấy từ dữ liệu không kiểm soát hoặc có cardinality quá cao | Thêm allowlist, chuẩn hóa tên và theo dõi số binding |
| `send` trả về true nhưng consumer không xử lý | Mới xác nhận bước gửi vào channel; consumer có thể lỗi, chưa subscribe hoặc đang lag | Kiểm tra broker, group/subscription, retry và DLQ |

Khi debug, lần theo luồng theo thứ tự: tên truyền vào `StreamBridge.send`, binding được resolve, destination thực tế, binder được chọn, tài nguyên broker và consumer. Chỉ kiểm tra log của producer là chưa đủ để chứng minh message đã đến consumer.

## 12. Kiểm thử binding có sẵn và destination động

Hai cách cần các kịch bản kiểm thử khác nhau:

| Kịch bản | Binding có sẵn | Destination động |
|---|---|---|
| Đúng tên | Gọi bằng binding name đã cấu hình | Gọi bằng tên destination được phép |
| Ánh xạ destination | Xác nhận binding trỏ đúng destination vật lý | Xác nhận tên động được dùng đúng làm destination |
| Content type | Kiểm tra cấu hình binding | Kiểm tra cấu hình mặc định hoặc metadata message |
| Tài nguyên | Xác nhận provisioning trước hoặc lúc startup theo cấu hình | Xác nhận hành vi tạo binding/tài nguyên ở lần gửi đầu |
| Tên không hợp lệ | Kiểm tra binding name không tồn tại | Kiểm tra destination ngoài allowlist bị từ chối |
| Lỗi broker | Xác nhận lỗi publish được quan sát | Xác nhận lỗi resolve/provision/publish được phân biệt |

Ví dụ kiểm thử cần xác nhận boolean trả về và nội dung được gửi đến output destination. Với Spring Cloud Stream Test Binder, có thể kiểm tra message được chuyển vào destination test tương ứng mà không cần broker thật. Tuy nhiên, test binder không chứng minh được quyền tạo topic, exchange hoặc subscription, cũng không xác nhận đầy đủ semantics của broker.

Với kiểm thử tích hợp, nên chạy ít nhất một kịch bản trên đúng loại broker sẽ dùng trong triển khai. Kiểm tra cả payload, headers, content type, routing và việc consumer nhận được message. Với dynamic destination, kiểm tra thêm allowlist, số lượng binding được tạo và hành vi khi destination không tồn tại.

## 13. Quan sát và bảo mật

Khi dùng destination động, metric chỉ theo dõi tổng số message có thể không đủ. Nên quan sát:

- Số binding động đang hoạt động và tốc độ tạo binding mới.
- Số lần gửi thành công/thất bại theo binder và destination đã được chuẩn hóa.
- Số destination bị từ chối do không nằm trong allowlist.
- Lỗi provisioning, lỗi xác thực, lỗi publish và backlog ở consumer.
- Số lượng tài nguyên broker, dung lượng lưu trữ và retention theo miền nghiệp vụ.

Không dùng tenant ID hoặc destination tùy ý làm nhãn metric nếu cardinality không được giới hạn. Log có thể ghi destination đã được xác thực, correlation ID và event ID nhưng không ghi dữ liệu nhạy cảm trong payload.

Chỉ cấp quyền publish đến những destination ứng dụng thực sự cần. Nếu binder dùng một tài khoản có quyền ghi rộng, allowlist ở ứng dụng càng quan trọng. Với multi-tenant, kiểm tra quyền truy cập tenant trước khi chọn destination; không dựa vào tên destination như cơ chế phân quyền duy nhất.

## 14. Quy trình chọn và triển khai

Khi thiết kế một đường gửi bằng `StreamBridge`:

1. Xác định destination có biết trước khi triển khai hay chỉ biết khi xử lý request.
2. Nếu destination ổn định, khai báo output binding và ánh xạ binding name tới destination.
3. Nếu destination động, xác định quy tắc đặt tên, allowlist và cách kiểm tra quyền ở tầng nghiệp vụ.
4. Cấu hình binder, content type, producer properties và provisioning theo broker.
5. Gửi bằng binding name đối với binding có sẵn; dùng tên đích động đã được kiểm soát đối với dynamic destination.
6. Phân biệt kết quả `send` với xác nhận broker và kết quả xử lý của consumer.
7. Thiết kế retry, outbox hoặc cơ chế xác nhận phù hợp với yêu cầu giao nhận.
8. Kiểm thử đúng destination, payload, headers, lỗi broker và tên không hợp lệ.
9. Theo dõi số binding, số tài nguyên, lỗi publish và backlog.
10. Lập quy trình dọn dẹp destination động và thu hồi quyền khi tenant hoặc luồng không còn hoạt động.

## 15. Tự kiểm tra

- [ ] Phân biệt được binding name, destination, binder và tài nguyên vật lý.
- [ ] Giải thích được cách khai báo output binding có sẵn bằng `output-bindings`.
- [ ] Biết vì sao lời gọi `StreamBridge.send` với binding name đã cấu hình khác với tên destination động.
- [ ] Mô tả được cách dynamic destination được resolve và tạo binding khi gửi lần đầu.
- [ ] Biết giới hạn destination động bằng allowlist và kiểm tra quyền tenant.
- [ ] Hiểu rằng provisioning tài nguyên phụ thuộc broker, binder và quyền được cấp.
- [ ] Phân biệt giá trị trả về của `send` với xác nhận broker và hoàn tất xử lý nghiệp vụ.
- [ ] Chọn được khi nào nên dùng binding có sẵn và khi nào destination động phù hợp.
- [ ] Thiết kế được kiểm thử, metric và vòng đời cho dynamic destination.

## Kết luận

Binding có sẵn xác định trước tên binding, destination và thuộc tính producer; `StreamBridge.send` được gọi bằng tên binding đó. Destination động cho phép ứng dụng chọn đích khi chạy và framework có thể tạo output binding trong lần gửi đầu tiên. Cách động hữu ích khi topology thay đổi theo dữ liệu runtime, nhưng cần allowlist, kiểm tra quyền, giới hạn số lượng tài nguyên và quy trình provisioning rõ ràng. Dù dùng cách nào, hãy phân biệt việc message được chấp nhận ở output channel với việc broker xác nhận và consumer hoàn tất nghiệp vụ.
