# Tránh vòng lặp event và message

Trong `SPRING_INTEGRATION_ADAPTERS`, một luồng tích hợp thường nhận dữ liệu qua inbound adapter, chuyển đổi hoặc định tuyến message bằng `MessageChannel`, rồi gửi dữ liệu ra ngoài qua outbound adapter. Gateway có thể kết hợp chiều gửi và nhận phản hồi; poller có thể đọc nguồn theo lịch. Khi một đầu ra lại trở thành đầu vào của chính luồng đó, cùng một event có thể chạy qua hệ thống nhiều lần, tạo ra bản ghi trùng, gửi thông báo lặp hoặc làm tăng tải liên tục.

Bài học này tập trung vào cách nhận diện và chặn vòng lặp trong các luồng file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Cần phân biệt hai vấn đề: **vòng lặp** là đường đi khiến message quay lại một bước đã xử lý nó; **message trùng** là cùng một sự kiện được giao nhiều lần, có thể do retry, redelivery hoặc cơ chế bảo đảm giao nhận. Hai vấn đề thường xuất hiện cùng nhau nhưng cần các biện pháp bảo vệ bổ sung.

## 1. Vòng lặp hình thành như thế nào?

Một event mô tả điều đã xảy ra trong nghiệp vụ, chẳng hạn `OrderCreated`. Message là đơn vị Spring Integration chuyển giữa các endpoint; nó mang payload cùng headers như ID, correlation, nguồn gửi hoặc thông tin định tuyến. Một event có thể được đóng gói trong nhiều message khác nhau khi đi qua các adapter. Vì vậy, chỉ nhìn vào tên channel hoặc loại adapter chưa đủ để biết một message có đang quay lại hay không; cần hiểu cả topology nội bộ lẫn đường đi qua hệ thống bên ngoài.

Các dạng vòng lặp thường gặp:

- **Nối vòng trong ứng dụng:** channel A chuyển sang handler B, handler B gửi lại channel A. Một bridge hoặc router cấu hình sai cũng có thể tạo cạnh quay ngược.
- **Echo qua hệ thống ngoài:** ứng dụng nhận event từ Kafka, gửi event đó lên một topic mà chính inbound adapter đang tiêu thụ, rồi nhận lại bản tin vừa phát.
- **Đọc lại dữ liệu đầu ra:** file outbound ghi vào thư mục mà file inbound đang theo dõi; hoặc SFTP outbound tải tệp lên đúng thư mục remote mà inbound poller quét.
- **CDC tự kích hoạt:** luồng nhận thay đổi từ bảng cơ sở dữ liệu, cập nhật lại chính bảng được theo dõi, khiến bộ đọc change data capture phát sinh event mới.
- **Phản hồi quay thành yêu cầu:** HTTP hoặc messaging gateway gửi request, nhận reply, rồi một route khác đưa reply vào lại request channel.
- **Fan-out bị hiểu nhầm là duplicate:** `PublishSubscribeChannel` phát một message tới nhiều subscriber. Nếu một subscriber gửi message trở lại nhánh đầu vào, hệ thống vừa fan-out vừa tạo vòng lặp.

Ví dụ topology có nguy cơ:

```text
Kafka inbound adapter
        |
        v
  eventChannel ---> xử lý nghiệp vụ ---> Kafka outbound adapter
        ^                                      |
        +----------- cùng một topic ------------+
```

Nếu outbound publish vào đúng topic mà inbound consume, event có thể quay lại. Consumer group, offset hoặc poller chỉ điều khiển cách đọc; chúng không tự chứng minh rằng event đã được xử lý đúng một lần.

## 2. Thiết kế topology có hướng rõ ràng

Hãy xác định ranh giới vào, xử lý và ra trước khi cấu hình adapter. Một luồng điển hình có dạng:

```text
Nguồn ngoài
    |
    v
Inbound adapter
    |
    v
partnerInboundChannel
    |
    v
Kiểm tra hợp đồng + loop guard
    |
    v
domainEventChannel
    |
    v
Handler nghiệp vụ
    |
    v
partnerOutboundChannel
    |
    v
Outbound adapter
    |
    v
Đích ngoài
```

Đường phản hồi, nếu có, nên là một luồng riêng với hợp đồng và correlation ID rõ ràng. Không nối đầu ra trở lại channel đầu vào chỉ để “chờ” phản hồi. Với request-reply, gateway chịu trách nhiệm ghép reply với request; handler phản hồi cần trả về reply channel hoặc cơ chế tương ứng, không phát reply như một request mới.

Một số nguyên tắc khi thiết kế channel:

- Đặt tên channel theo vai trò và chiều dữ liệu, ví dụ `partnerInboundChannel`, `validatedOrderChannel`, `partnerOutboundChannel`. Tên rõ ràng giúp phát hiện kết nối ngược khi đọc cấu hình.
- Chọn channel theo ngữ nghĩa. `DirectChannel` chuyển message tới một subscriber; `PublishSubscribeChannel` phát message tới nhiều subscriber; `QueueChannel` lưu message để consumer lấy sau. Fan-out là hành vi có chủ đích, không phải cơ chế chống lặp.
- Chỉ dùng bridge khi cần chuyển tiếp giữa hai channel. Kiểm tra toàn bộ đường đi để tránh bridge A sang B đồng thời bridge B ngược về A.
- Router phải có route mặc định hoặc nhánh loại bỏ được xác định rõ. Không định tuyến message không hợp lệ về lại channel nguồn để thử vô hạn.
- Các nhánh chỉ ghi log hoặc đo lường nên không có side effect nghiệp vụ. Nếu nhánh giám sát cần gửi message đi nơi khác, dùng channel riêng và bảo đảm nó không nhập ngược vào luồng xử lý.

## 3. Đặt loop guard tại ranh giới inbound

Loop guard kiểm tra message ngay sau inbound adapter, trước khi message có thể kích hoạt side effect. Để guard hoạt động qua nhiều hệ thống, hãy thống nhất một event envelope. Ví dụ:

```json
{
  "eventId": "evt-8f12",
  "eventType": "InventoryAdjusted",
  "originSystem": "warehouse-erp",
  "lastEmitter": "inventory-service",
  "visitedSystems": ["warehouse-erp", "inventory-service"],
  "hopCount": 2,
  "correlationId": "order-391",
  "causationId": "evt-7a21",
  "schemaVersion": 1,
  "payload": {
    "sku": "SKU-42",
    "quantity": 18
  }
}
```

Ý nghĩa của các trường:

| Trường | Vai trò |
|---|---|
| `eventId` | Định danh ổn định của event; giữ nguyên qua retry và redelivery |
| `originSystem` | Hệ thống phát sinh event ban đầu; không thay đổi khi chuyển tiếp |
| `lastEmitter` | Hệ thống vừa phát message ở chặng gần nhất |
| `visitedSystems` | Các hệ thống đã xử lý hoặc chuyển tiếp event; dùng để phát hiện quay lại |
| `hopCount` | Số chặng đã đi qua; giới hạn độ dài đường đi |
| `correlationId` | Liên kết các message thuộc cùng một nghiệp vụ hoặc request |
| `causationId` | Event hoặc message trực tiếp gây ra event hiện tại |
| `schemaVersion` | Phiên bản hợp đồng payload |

Khi outbound adapter phát event sang hệ thống kế tiếp, handler tạo envelope kế tiếp bằng cách giữ `eventId` và `originSystem`, cập nhật `lastEmitter`, thêm mã hệ thống hiện tại vào `visitedSystems`, đồng thời tăng `hopCount`. Khi inbound adapter nhận lại event, guard loại bỏ event đã có mã hệ thống hiện tại trong `visitedSystems`, hoặc đã vượt giới hạn hop.

Ví dụ Java DSL dưới đây giả định adapter đã chuyển JSON thành `Map`. Trong ứng dụng thực tế, có thể thay `Map` bằng DTO đã validate. `SERVICE_ID` và `MAX_HOPS` là cấu hình của ứng dụng.

```java
import java.util.Collection;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.core.MessageSelector;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
MessageSelector loopGuard() {
    return message -> {
        Object payload = message.getPayload();
        if (!(payload instanceof Map)) {
            return false; // Envelope sai định dạng: đưa sang nhánh loại bỏ.
        }

        Map<?, ?> event = (Map<?, ?>) payload;
        Object eventId = event.get("eventId");
        Object visited = event.get("visitedSystems");
        Object hops = event.get("hopCount");

        boolean visitedHere = visited instanceof Collection
                && ((Collection<?>) visited).contains(SERVICE_ID);
        int hopCount = hops instanceof Number
                ? ((Number) hops).intValue() : 0;

        return eventId != null && !visitedHere && hopCount < MAX_HOPS;
    };
}

@Bean
IntegrationFlow partnerInboundFlow(MessageSelector loopGuard) {
    return IntegrationFlow.from("partnerInboundChannel")
            .filter(loopGuard,
                    endpoint -> endpoint.discardChannel("loopDiscardChannel"))
            .channel("domainEventChannel")
            .get();
}
```

Trong ví dụ, selector trả về `false` cho envelope sai định dạng, event đã đi qua service hiện tại hoặc event vượt giới hạn hop. `discardChannel` đưa các message bị loại sang nhánh riêng để ghi nhận và điều tra. Không gửi chúng trở lại inbound channel. Nếu hệ thống cần phân biệt message lỗi hợp đồng với message echo, hãy dùng các selector hoặc nhánh loại bỏ riêng để có số liệu chính xác.

**Lưu ý về headers:** Spring message headers có ích cho định tuyến trong ứng dụng, nhưng không phải mọi adapter hoặc hệ thống ngoài đều truyền tất cả headers. Khi metadata cần đi xuyên qua HTTP, JMS, AMQP, Kafka, file hoặc SFTP, hãy ánh xạ nó vào transport headers được hỗ trợ hoặc đặt trong envelope payload. Xác minh cấu hình header mapper và nội dung thực tế sau khi đi qua adapter. Không dựa vào một header nội bộ có thể bị mất ở ranh giới transport.

## 4. Kết hợp loop guard với idempotency

Loop guard ngăn một event quay lại theo đường đi đã biết. Idempotency ngăn cùng một event tạo side effect nhiều lần khi broker giao lại, poller đọc lại hoặc client retry. Một consumer nên có khóa idempotency ổn định, thường là cặp `(originSystem, eventId)` hoặc một ID toàn cục được đảm bảo duy nhất.

Quy trình xử lý có thể tổ chức như sau:

1. Validate envelope và kiểm tra `eventId`.
2. Dùng kho trạng thái bền vững để nhận quyền xử lý khóa idempotency. Nếu khóa đã hoàn tất, ghi nhận duplicate và kết thúc message.
3. Thực hiện cập nhật nghiệp vụ.
4. Đánh dấu xử lý hoàn tất trong cùng transaction với thay đổi nghiệp vụ khi cả hai nằm trong cùng cơ sở dữ liệu.
5. Nếu cần phát event tiếp theo, ghi nó vào transactional outbox trong cùng transaction; tiến trình publisher gửi outbox sau đó.

Spring Integration có `IdempotentReceiverInterceptor`, `MetadataStore` và `MetadataStoreSelector` để triển khai kiểm soát message trùng. Chọn implementation `MetadataStore` có lưu trữ bền vững và dùng chung khi ứng dụng chạy nhiều instance. Một bộ nhớ trong tiến trình không bảo vệ được khi restart hoặc khi hai instance nhận cùng event đồng thời. Với nghiệp vụ quan trọng, khóa duy nhất ở database hoặc thao tác claim nguyên tử giúp tránh race condition.

Ví dụ SQL theo cú pháp PostgreSQL cho bảng lưu event đã nhận:

```sql
INSERT INTO consumed_event (origin_system, event_id, processed_at)
VALUES (:originSystem, :eventId, CURRENT_TIMESTAMP)
ON CONFLICT (origin_system, event_id) DO NOTHING;
```

Ứng dụng chỉ tiếp tục khi thao tác insert thực sự tạo bản ghi mới. Cần thực hiện thao tác claim và thay đổi nghiệp vụ trong transaction phù hợp; nếu đánh dấu đã xử lý rồi mới thực hiện side effect ở một transaction độc lập, lỗi giữa hai bước có thể làm mất event. Với side effect bên ngoài database, gửi kèm idempotency key nếu API đích hỗ trợ, hoặc dùng outbox và trạng thái giao nhận để có thể retry an toàn.

Không nên hứa hẹn “exactly once” chỉ vì broker hoặc adapter có chế độ giao nhận đặc biệt. Trong một luồng đi qua nhiều hệ thống, retry và lỗi mạng vẫn có thể tạo giao nhận lặp. Thiết kế consumer idempotent và side effect có khóa ổn định thường là cách kiểm soát thực tế hơn.

## 5. Áp dụng theo từng loại adapter

| Loại kết nối | Nguyên nhân dễ tạo vòng lặp | Cách phòng tránh |
|---|---|---|
| File | Inbound poller theo dõi cùng thư mục mà outbound adapter ghi file | Tách thư mục `inbox`, `outbox` và `archive`; chỉ quét mẫu tên file đầu vào; chuyển file đã nhận sang archive; ghi file đầu ra bằng tên tạm rồi đổi tên tại thư mục outbox |
| SFTP | Inbound poller tải lại file mà outbound vừa upload | Tách remote path theo chiều; lọc tên file và trạng thái hoàn tất; lưu dấu nhận file bền vững; archive hoặc xóa file nguồn theo thỏa thuận với đối tác |
| HTTP | Webhook nhận callback từ endpoint mà outbound client vừa gọi | Dùng URL và route riêng cho webhook và API outbound; kiểm tra chữ ký và event ID; dùng idempotency key; không gọi callback về chính webhook nếu hợp đồng không yêu cầu |
| JMS | Consumer nhận lại message mà producer của cùng luồng vừa gửi | Dùng queue/topic riêng theo chiều hoặc theo loại event; cấu hình selector và routing rõ ràng; kiểm soát redelivery và dead-letter queue; giữ event ID ổn định |
| AMQP | Binding của exchange định tuyến message trở lại queue nguồn | Rà soát exchange, routing key và queue binding; tách routing key cho event vào/ra; không bind queue nguồn vào route phát lại cùng event |
| Kafka | Consumer đọc topic mà chính service đang publish | Tách topic đầu vào và đầu ra; chỉ dùng topic chung khi hợp đồng event và subscription được thiết kế rõ; lọc event do service tự phát và dùng event ID để chống xử lý lặp |
| Database / CDC | Consumer cập nhật bảng nằm trong tập bảng CDC đang theo dõi | Tách bảng nguồn, bảng đích và outbox; lọc thay đổi do service tự tạo khi phù hợp; tránh ghi lại cùng dữ liệu vào bảng nguồn; xác định transaction và thứ tự phát event |

Một số điểm cần kiểm tra sâu hơn:

- **File và SFTP:** poller chỉ quyết định lúc nào đọc. Nó không đảm bảo file chỉ được xử lý một lần. Bộ lọc accept-once trong bộ nhớ có thể mất dấu sau restart; cân nhắc metadata store bền vững, tên file duy nhất, checksum hoặc archive. Không đọc file đang được outbound adapter ghi dở.
- **HTTP:** inbound endpoint thường nhận webhook trong khi outbound gateway gọi API đối tác. Tách hai URL theo vai trò và kiểm tra `eventId`, chữ ký, thời điểm phát và idempotency key. Nếu đối tác gửi callback, callback phải có correlation ID để liên kết với request gốc.
- **JMS và AMQP:** redelivery sau rollback là hành vi giao nhận có thể xảy ra, không nhất thiết là vòng lặp topology. Cấu hình retry có giới hạn, backoff và dead-letter route; bảo đảm dead-letter queue không bị route trở lại queue nguồn vô hạn.
- **Kafka:** consumer group giúp các consumer trong cùng group chia tải; nó không ngăn một service đọc lại event mà service đó vừa publish. Dùng topic, key, event type và subscription theo hợp đồng. Nếu cần loại event do chính service phát, kiểm tra metadata nguồn ở consumer.
- **Database:** transactional outbox giúp cập nhật dữ liệu và ghi event cần phát trong cùng transaction. CDC publisher đọc outbox và phát ra broker; consumer không nên ghi kết quả echo trở lại chính bảng outbox hoặc bảng đang tạo cùng loại change event.

## 6. Kiểm soát poller, gateway và luồng lỗi

**Poller** điều khiển nhịp đọc nguồn như thư mục, SFTP hoặc bảng dữ liệu. Cấu hình fixed delay, cron, transaction và giới hạn số message mỗi lần poll để quản lý tải. Các thiết lập này không thay thế loop guard hoặc idempotency. Nếu poller đọc một nguồn có thể bị outbound adapter ghi lại, cần sửa ranh giới nguồn/đích trước khi tinh chỉnh lịch.

**Gateway** thường thực hiện request-reply. Giữ correlation ID từ request đến reply, đặt timeout và xác định rõ reply channel. Nếu reply là một event nghiệp vụ mới, hãy tạo event ID mới và khai báo causation ID trỏ về request hoặc event gốc. Không tái sử dụng nguyên event ID cho một sự kiện mới chỉ vì nó có liên quan.

**Error flow** cần có điểm kết thúc. Retry nên giới hạn số lần, có backoff và phân loại lỗi tạm thời với lỗi dữ liệu. Sau khi hết retry, chuyển message sang dead-letter hoặc quarantine channel để điều tra. Tránh cấu hình error handler gửi message lỗi trở lại chính channel đã gây lỗi mà không có giới hạn. Khi replay từ dead-letter, giữ event ID gốc để idempotency tiếp tục bảo vệ side effect.

## 7. Kiểm thử và quan sát

Một bài kiểm thử tích hợp nên bao gồm cả đường đi bình thường và tình huống quay lại:

1. Gửi một event mới qua inbound adapter giả lập; xác nhận handler nghiệp vụ chạy một lần và outbound adapter phát đúng một event.
2. Gửi lại cùng `eventId`; xác nhận consumer nhận diện duplicate và không lặp side effect.
3. Gửi event có `visitedSystems` chứa `SERVICE_ID`; xác nhận loop guard chuyển message sang discard channel.
4. Gửi event có `hopCount` đạt giới hạn; xác nhận nó bị chặn trước handler nghiệp vụ.
5. Mô phỏng broker redelivery hoặc poller đọc lại sau restart; xác nhận metadata idempotency vẫn còn.
6. Làm cho outbound hoặc handler phát sinh lỗi; xác nhận retry có giới hạn và dead-letter không quay lại luồng nguồn.
7. Kiểm tra header mapping hoặc envelope sau mỗi ranh giới transport để chắc chắn event ID và metadata cần thiết vẫn được giữ.

Trong log và metric, nên theo dõi `eventId`, `originSystem`, `lastEmitter`, `correlationId`, channel, adapter, số hop và kết quả guard. Tạo metric riêng cho message hợp lệ, duplicate, loop bị chặn, envelope lỗi, retry và dead-letter. Có thể cảnh báo khi số message bị chặn hoặc số hop tăng bất thường. Tránh ghi toàn bộ payload chứa dữ liệu nhạy cảm vào log; metadata định danh và trạng thái thường đủ để truy vết.

### Bài tập thực hành

Một service Spring Integration đọc event `OrderUpdated` từ Kafka topic `orders`, cập nhật cơ sở dữ liệu, sau đó phát event đã chuẩn hóa lên topic `orders`. Inbound adapter cũng đang consume topic `orders`. Sau mỗi lần xử lý, event lại xuất hiện ở đầu vào và tiếp tục cập nhật database.

Hãy đề xuất cách sửa theo thứ tự ưu tiên:

1. Vẽ lại chiều inbound và outbound; chọn topic riêng hoặc routing contract riêng để consumer không đọc lại event do chính luồng phát ra.
2. Bổ sung envelope có `eventId`, `originSystem`, `visitedSystems`, `hopCount` và `causationId`; giữ nguyên event ID qua retry.
3. Đặt filter ngay sau inbound adapter và chuyển event bị loại sang channel giám sát.
4. Thêm idempotency store bền vững với khóa `(originSystem, eventId)` để bảo vệ trường hợp broker redelivery.
5. Nếu cập nhật database và phát event phải nhất quán, ghi event vào transactional outbox trong cùng transaction rồi publish từ outbox.
6. Kiểm thử event mới, event echo, duplicate delivery, restart consumer và lỗi publish.

**Tiêu chí hoàn thành:** topology không có cạnh quay về nguồn ngoài ý muốn; event echo bị chặn trước side effect; duplicate delivery không tạo cập nhật nghiệp vụ lặp; retry và error flow có giới hạn; event vẫn truy vết được qua các adapter.
