# Cursor không hợp lệ, không có kết quả và chiến lược kết nối lại

> **Chương:** Tailable cursor  
> **Module:** `SPRING_DATA_MONGODB`

Một hệ thống theo dõi sự kiện vận hành lưu các bản ghi vào **MongoDB capped collection** và muốn nhận những bản ghi mới gần như theo thời gian thực. Ứng dụng dùng **tailable cursor**: sau khi đã đọc tới phần cuối, con trỏ có thể tiếp tục chờ những document mới được append thay vì kết thúc giống cursor của truy vấn thông thường. Khi sự kiện ngừng xuất hiện trong vài phút, ứng dụng cần xác định: **thực sự không có dữ liệu mới, cursor vẫn đang đợi, hay cursor đã chết và cần kết nối lại?**

Trong Spring Data MongoDB, ta có thể sử dụng `ReactiveMongoTemplate.tail(...)`, repository reactive với `@Tailable`, hoặc `MessageListenerContainer` với `TailableCursorRequest` ở phía imperative. Nhưng chỉ mở lại một `Flux`/cursor khi thấy lỗi là chưa đủ. Capped collection có thể **ghi đè dữ liệu cũ**, cursor có thể trở nên không hợp lệ, một truy vấn ban đầu không khớp có thể làm stream đóng, và **tailable cursor không cung cấp resume token của change stream**. Nếu kết nối lại chỉ từ “hiện tại”, consumer có thể mất dữ liệu; nếu phát lại từ điểm cũ không có deduplication, consumer có thể xử lý trùng.

Bài này thuộc module `SPRING_DATA_MONGODB`: dùng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua `MongoTemplate` hoặc repository; thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Trọng tâm trực tiếp là **phân loại cursor không hợp lệ, không có kết quả, và chiến lược reconnect/recovery**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao tailable cursor chỉ phù hợp với **capped collection** và thứ tự tự nhiên (`$natural`).
2. Phân biệt `onNext`, **không có `onNext` trong lúc cursor vẫn sống**, `onComplete`, `onError` và `cancel`.
3. Nhận diện cursor mất hiệu lực do collection bị drop/recreate, capped rollover/position lost, election, network hoặc cấu hình query không phù hợp.
4. Hiểu tình huống **truy vấn ban đầu chưa khớp bản ghi**, cách theo dõi subscription/cursor và vì sao `Flux.empty()` không đồng nghĩa “đang đợi”.
5. Dùng `ReactiveMongoTemplate.tail(Query, Class<T>)` hoặc `@Tailable` để đọc liên tục mà không tự `subscribe()` trong mỗi request HTTP.
6. Tách chiến lược **retry khi lỗi** và **repeat/reopen khi cursor kết thúc**, có backoff, retry budget và chống vòng lặp nóng.
7. Thiết kế checkpoint ở tầng ứng dụng khi **không có resume token**, với idempotency và phát hiện lỗ hổng dữ liệu do capped rollover.
8. So sánh tailable cursor với change stream và quyết định khi nào nên dùng giải pháp khác.
9. Kiểm thử với capped collection thật, cursor sống nhưng im lặng, kết nối bị hủy, no initial match và chu kỳ reconnect.
10. Thiết kế metrics, cảnh báo, giới hạn tài nguyên và runbook ứng phó sự cố.

## 2. Tailable cursor hoạt động thế nào?

MongoDB có hai ý tưởng khác nhau:

- **Cursor thông thường:** duyệt các kết quả tại thời điểm truy vấn; khi đã hết kết quả, cursor thường kết thúc.
- **Tailable cursor:** đối với capped collection, sau khi đến cuối dữ liệu đang có, cursor có thể giữ mở để quan sát các document được append tiếp.

```text
CAPPED COLLECTION (append order)

[E01][E02][E03][E04]       <- điểm cuối hiện tại
                  ^
                  | Tailable cursor đọc tới đây
                  v
             Chờ document tiếp theo

Sau khi insert E05:

[E01][E02][E03][E04][E05]
                       ^
                       |
                    onNext(E05)
                       |
                       v
                 Tiếp tục đợi
```

Cursor **không tự biến thành message queue**. Nó là một cursor gắn vào MongoDB collection, chịu các giới hạn về collection lifecycle, batch/getMore, điều kiện query, network, session và dữ liệu bị ghi đè.

### 2.1. Tại sao phải dùng capped collection?

Capped collection có **kích thước tối đa được cấu hình**; MongoDB giữ dữ liệu theo dạng vòng: khi dung lượng chạm giới hạn, document cũ có thể bị loại để nhường chỗ cho document mới. Đây là điều kiện thiết yếu cho tailable cursors, nhưng cũng là nguyên nhân **không thể coi cursor là cơ chế lưu trữ event vĩnh viễn**.

Giả sử capped collection chỉ đủ giữ E100–E200. Nếu consumer đang offline ở E050, khi kết nối lại, **E051–E099 có thể đã bị ghi đè**. Dù reconnect thành công, không có cách dùng cursor đó để lấy lại những document đã không còn trong collection.

### 2.2. Natural order, không tự sort lại

Tailable cursor đọc theo **thứ tự tự nhiên (`$natural`)** của capped collection. Không thêm `Sort.by("createdAt")` hoặc `sort({_id:1})` rồi mong cursor vẫn có semantics tail đúng. Nếu bài toán cần đọc theo một khóa nghiệp vụ có thứ tự chính xác riêng, phải thiết kế dữ liệu/cơ chế replay phù hợp, không sửa cursor bằng sort.

### 2.3. Tailable cursor không báo các update như change stream

Tailable cursor thường dùng để nhận **những document được append** vào capped collection. Nó không gửi một event envelope có `operationType`, `updateDescription` và `resumeToken` cho mọi thay đổi của các collection khác. Nếu use case là “bất cứ update/delete nào trên `orders` cũng phải có sự kiện”, **change stream** hoặc transactional outbox thường phù hợp hơn.

## 3. Năm trạng thái phải phân biệt

| Trạng thái | Dấu hiệu trên API reactive | Ý nghĩa | Hành động |
| --- | --- | --- | --- |
| **Có document mới** | `onNext(document)` | Cursor đang trả dữ liệu | Xử lý, chỉ checkpoint khi xử lý thành công |
| **Đang mở nhưng im lặng** | Chưa có `onNext/onError/onComplete` | Có thể chỉ là không có document mới | Giữ cursor, theo dõi health; không tự coi là lỗi |
| **Cursor hoàn tất** | `onComplete` | Publisher không còn phát tiếp | Phân loại nguyên nhân và mở lại có delay nếu policy cho phép |
| **Cursor lỗi/không hợp lệ** | `onError` | Lỗi server, network, query, cursor position... | Phân loại lỗi; retry/reopen hoặc fail-fast/reconcile |
| **Caller chủ động hủy** | `cancel` / `Disposable.dispose()` | Không phải lỗi của database | Cleanup; **không tự reconnect** khi đã shutdown có chủ đích |

### 3.1. Không có sự kiện không giống Flux.empty()

`Flux.empty()` phát `onComplete` ngay. Một tailable Flux đang đợi insert thường **chưa phát bất kỳ tín hiệu terminal nào**. Nếu code chỉ có:

```java
source.switchIfEmpty(fallback());
```

thì `fallback()` chỉ chạy khi upstream **hoàn tất rỗng**, không chạy đơn thuần vì cursor chưa có bản ghi nào trong 30 giây. Hơn nữa, khi một tailable cursor bị kết thúc sớm do không có initial match, `switchIfEmpty` là dấu hiệu của complete, **không chứng minh server vẫn đang watch**.

### 3.2. blockFirst() có thể chờ rất lâu

```java
EventDocument first = reactiveTemplate
    .tail(query, EventDocument.class)
    .blockFirst();
```

Đây là **phản ví dụ** trong ứng dụng WebFlux: không có event thì lệnh blocking có thể chờ đến khi nhận dữ liệu hoặc cursor kết thúc/lỗi. Nó chiếm thread, khó quản lý cancellation và không giúp khôi phục cursor. Trong đường reactive, hãy giữ `Flux` và quản lý subscription bằng lifecycle.

### 3.3. timeout() dễ nhầm im lặng với lỗi

```java
// Chỉ là chính sách minh họa, KHÔNG là mặc định an toàn.
Flux<EventDocument> impatient = source
    .timeout(java.time.Duration.ofSeconds(10));
```

`timeout` có thể **cancel upstream** khi không có item trong 10 giây và phát lỗi `TimeoutException`. Nếu workload hợp pháp có thể im lặng 10 phút, code trên liên tục hủy và reconnect một cursor đang khỏe.

Chỉ dùng timeout như **liveness policy** khi nguồn có hợp đồng heartbeat/event cadence rõ. Với tail theo sự kiện nghiệp vụ không định kỳ, dùng metrics cursor, monitoring từ driver/server, hoặc heartbeat document riêng có hợp đồng rõ hơn.

### 3.4. onComplete không phải “đã hoàn thành công việc”

Một stream làm nhiệm vụ giám sát liên tục không có khái niệm “hoàn thành vĩnh viễn” khi database còn hoạt động. `onComplete` có thể báo **cursor không còn hợp lệ** hoặc query không còn điều kiện để tail; nếu hệ thống cần tiếp tục nhận event, supervisor phải quyết định re-open và đánh giá có khả năng mất dữ liệu không.

### 3.5. onError không đồng nghĩa mọi lỗi đều retry được

Lỗi network transient có thể phục hồi sau reconnect; nhưng truy vấn vào collection thường (không capped), sai authorization, sort không hỗ trợ hoặc schema mapping sai sẽ **lặp lại cùng lỗi** nếu không sửa cấu hình. Một `retryWhen` vô hạn sẽ biến lỗi cấu hình thành vòng reconnect liên tục.

## 4. Điều kiện ban đầu: query không match có thể làm cursor chết

Spring Data MongoDB nêu rõ tailable cursors có thể trở nên **dead/invalid**, trong đó trường hợp query **không tìm thấy document phù hợp ban đầu** là một bẫy quan trọng. Không nên giả định “không có kết quả lúc mở” luôn có nghĩa cursor đã đăng ký chờ một document tương lai đúng filter.

Ví dụ:

```java
Query query = Query.query(
    Criteria.where("tenantId").is("TENANT-A")
        .and("level").is("CRITICAL"));

Flux<EventDocument> stream =
    reactiveTemplate.tail(query, EventDocument.class);
```

Nếu capped collection hiện chỉ có events `INFO` và `WARN`, truy vấn `CRITICAL` có thể không tìm được một điểm bắt đầu phù hợp. Tùy server/driver/query, cursor có thể hoàn tất sớm thay vì chờ vô hạn. Hãy kiểm thử đúng version triển khai và **quan sát tín hiệu terminal**.

### 4.1. Vì sao filter quá hẹp làm tăng rủi ro?

- Nếu query match được một document cũ, cursor có thể có điểm bắt đầu để tail.
- Nếu query ban đầu không match, cursor có thể bị kết thúc trước khi một event tương lai xuất hiện.
- Nếu có nhiều filter tùy user request, việc mở/tắt cursor theo mỗi filter có thể vừa tốn tài nguyên vừa khó phân biệt no-match.
- Nếu cần consumer **chạy liên tục bất kể event thuộc loại nào**, nên cân nhắc tail unfiltered ở scope đã được cho phép, rồi **lọc ở tầng xử lý** với giới hạn/authorization phù hợp.

Điều cuối không có nghĩa được phép tải và phát mọi tenant data tới client; backend vẫn phải giữ quyền đọc và phân luồng dữ liệu an toàn.

### 4.2. Hai kiểu “không có kết quả”

```text
CASE A — cursor đã tìm thấy vị trí ban đầu:
  Open -> read existing match(es) -> await more documents
                                   -> no onNext for a while
  => Có thể vẫn đang sống.

CASE B — query ban đầu không tìm thấy match:
  Open -> no initial match -> cursor may close/dead
  => Phải quan sát onComplete/onError và policy reopen.
```

Thiết kế test phải phân biệt hai ca; `expectNoEvent(Duration)` không đủ để chứng minh cursor vẫn open nếu test không có tín hiệu cursor readiness hoặc subscription lifecycle.

## 5. Tạo capped collection và dữ liệu mẫu

Mô hình sự kiện cho hệ thống theo dõi thiết bị:

```javascript
// Chỉ thực hiện trong MongoDB TEST được cấp quyền.
db.createCollection("device_event_log", {
  capped: true,
  size: 16 * 1024 * 1024,
  max: 20000
});

db.device_event_log.insertMany([
  {
    _id: "EVT-0001",
    sequence: NumberLong(1),
    tenantId: "TENANT-A",
    deviceId: "DEV-01",
    level: "INFO",
    message: "started",
    recordedAt: ISODate("2026-11-20T02:00:00Z")
  },
  {
    _id: "EVT-0002",
    sequence: NumberLong(2),
    tenantId: "TENANT-A",
    deviceId: "DEV-01",
    level: "WARN",
    message: "temperature-high",
    recordedAt: ISODate("2026-11-20T02:00:01Z")
  }
]);
```

Collection này có **dung lượng và số document tối đa** được cấu hình. Khi đủ giới hạn, MongoDB có thể loại document cũ nhất để thêm document mới. Các giá trị `size`/`max` chỉ là ví dụ; trong production phải đo **tốc độ ghi, kích thước trung bình mỗi event và thời gian giữ dữ liệu mong muốn**.

### 5.1. Kiểm tra có thực sự là capped collection

```javascript
db.device_event_log.isCapped()
// Mong đợi true.

db.getCollectionInfos({ name: "device_event_log" })
// Kiểm tra options: capped, size, max.
```

Không chỉ dựa vào tên collection có chữ “log” để kết luận nó là capped. Một collection MongoDB thường không hỗ trợ tailable cursor đúng cách chỉ vì có field `recordedAt` được index.

### 5.2. Capped collection không phải một queue có ACK

Tailable cursor không xóa document sau khi consumer xử lý và không có consumer-group commit offset hay cơ chế ACK được MongoDB quản lý như broker. Nhiều consumers tail cùng collection có thể nhận **cùng những document**. Consumer cần tự quản lý:

- Idempotency key và xử lý duplicate.
- Định nghĩa checkpoint riêng.
- Consumer ownership nếu business chỉ cho phép một worker áp hiệu ứng.
- Chính sách replay/backfill khi dữ liệu đã bị ghi đè.
- Quyền truy cập tenant và retention.

### 5.3. Không dùng capped collection nếu cần dữ liệu giữ vô hạn

Một capped collection 16 MiB có thể giữ được nhiều giờ ở tải thấp nhưng chỉ vài giây khi nguồn phát rất lớn. Đừng dùng nó làm **source of truth duy nhất** cho số liệu tài chính, audit lâu dài hoặc một workflow không được phép mất event.

Nếu yêu cầu là “sự kiện phải tồn tại để replay trong 30 ngày”, cần bộ lưu trữ bền vững và chính sách retention tương ứng; tailable cursor chỉ có thể là **đường truyền nhanh**, không thay thế archive/outbox/queue durable.

## 6. Entity và ReactiveMongoTemplate.tail(...)

File `DeviceEvent.java`:

```java
package com.example.monitoring;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "device_event_log")
public record DeviceEvent(
    @Id String id,
    long sequence,
    String tenantId,
    String deviceId,
    String level,
    String message,
    Instant recordedAt
) {}
```

File `DeviceEventTailSource.java`:

```java
package com.example.monitoring;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public final class DeviceEventTailSource {

    private final ReactiveMongoTemplate template;

    public DeviceEventTailSource(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<DeviceEvent> tailAll() {
        return template.tail(
            new Query(), DeviceEvent.class);
    }
}
```

`tail(Query, Class<T>)` là API Spring Data MongoDB reactive trả `Flux<T>`. Một `Query` rỗng không đồng nghĩa không có kết quả: nó thể hiện **không áp filter**, và cursor có thể đọc các documents hiện có trước khi chờ những documents tiếp theo.

### 6.1. Một lần gọi method chưa mở cursor

```java
Flux<DeviceEvent> events = source.tailAll();
// Tạo Publisher, chưa chứng minh đã có subscription.
```

Khi caller thực sự subscribe, driver bắt đầu tương tác với MongoDB. Trong ứng dụng thực, cần có một **component quản lý subscription**, giữ `Disposable`, shutdown có kiểm soát và báo lỗi; không mở cursor ẩn trong một request handler.

### 6.2. Tail với Query có filter

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Flux<DeviceEvent> tailForTenant(
        String authorizedTenantId) {

    if (authorizedTenantId == null
            || authorizedTenantId.isBlank()) {
        return Flux.error(new IllegalArgumentException(
            "Thiếu tenant được xác thực"));
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(authorizedTenantId));

    return template.tail(query, DeviceEvent.class);
}
```

Đây là **method minh họa** đặt trong service có `template` được inject. `authorizedTenantId` phải đến từ security context; không nhận một tenant bất kỳ từ client rồi coi query là đã có authorization.

Filter có thể làm cursor không tìm thấy document ban đầu và đóng sớm như mục 4. Nếu bài toán là “theo dõi không được mất event cho tenant A”, phải thiết kế chiến lược mở/reopen và checkpoint, chứ không chỉ trả một `Flux` rồi quên.

### 6.3. Không sort, không phân trang một tail như một query bình thường

```java
// PHẢN VÍ DỤ: sort theo recordedAt làm mất giả định natural order.
Query query = new Query()
    .with(org.springframework.data.domain.Sort.by("recordedAt"));
return template.tail(query, DeviceEvent.class);
```

Thay đổi sort có thể bị MongoDB từ chối hoặc khiến cursor không còn thoả điều kiện tail. Nếu cần đọc “5 records mới nhất” để hiển thị lịch sử, hãy dùng **truy vấn thông thường** riêng với index/sort. Nếu cần stream append, dùng tailable cursor theo natural order và policy phù hợp.

### 6.4. Không chỉ dùng take(1) để kết luận stream đã khỏe

```java
Flux<DeviceEvent> first = source.tailAll().take(1);
```

`take(1)` sẽ cancel upstream sau event đầu tiên; test này có thể chứng minh **đọc được ít nhất một document**, nhưng không chứng minh cursor giữ được subscription trong nhiều phút, phục hồi sau rollover hoặc xử lý reconnect. Test liveness/recovery phải kiểm tra vòng đời đủ dài và sự kiện insert sau khi watcher đã sẵn sàng.

## 7. @Tailable trên ReactiveMongoRepository

Spring Data MongoDB hỗ trợ khai báo query theo repository:

File `DeviceEventRepository.java`:

```java
package com.example.monitoring;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.mongodb.repository.Tailable;
import reactor.core.publisher.Flux;

public interface DeviceEventRepository
        extends ReactiveMongoRepository<DeviceEvent, String> {

    @Tailable
    Flux<DeviceEvent> findByTenantId(String tenantId);
}
```

Ứng dụng có thể gọi:

```java
Flux<DeviceEvent> tenantEvents =
    repository.findByTenantId(authorizedTenantId);
```

`repository` là bean được Spring inject, `authorizedTenantId` phải được kiểm tra quyền. `@Tailable` thay đổi cách MongoDB query cursor hoạt động; nó không biến repository thành broker durable, không cấp resume token và không tự xử lý khi collection rollover.

### 7.1. @Tailable khác ReactiveMongoRepository.findAll()

| API | Ý nghĩa |
| --- | --- |
| `repository.findAll()` | Reactive stream các document đáp ứng một truy vấn thông thường; đến cuối thì complete |
| `@Tailable Flux<T> ...` | Cố gắng giữ cursor mở trên capped collection để nhận documents append tiếp |
| `template.tail(Query, T.class)` | Điều khiển query tailable trực tiếp từ template |
| `ChangeStreamEvent<T>` | Envelope của change stream; **không phải** kết quả của `@Tailable` |

Nếu code gọi `findAll()` rồi gắn `repeat()`, nó chỉ **chạy lại truy vấn thông thường**, không có semantics của một tailable cursor. Điều đó có thể tạo polling loop, load lặp dữ liệu và tăng tải.

### 7.2. Điều kiện lọc không có kết quả ở lúc subscribe

Ngay cả khi method trả `Flux<T>`, startup behavior của tailable cursor vẫn cần được quan sát. Đối với consumer dài hạn, không xem `findByTenantId("TENANT-NOT-SEEN-YET")` là sẽ luôn chờ tài liệu đầu tiên vô hạn. Trong test, xác minh trường hợp tenant đã có dữ liệu và tenant chưa có dữ liệu, cùng tín hiệu `onComplete`/`onError` mà driver thực tế phát.

## 8. Imperative: MessageListenerContainer và TailableCursorRequest

Với ứng dụng sử dụng `MongoTemplate` imperative, Spring Data MongoDB cung cấp messaging abstraction để quản lý tailable cursor qua listener container. API liên quan gồm:

- `DefaultMessageListenerContainer`.
- `TailableCursorRequest` và builder.
- `MessageListener` nhận messages.
- `Subscription`/container lifecycle để hủy và dừng.

Ví dụ khái niệm:

```java
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.TailableCursorRequest;
import org.springframework.data.mongodb.core.query.Query;

MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);

TailableCursorRequest request = TailableCursorRequest.builder()
    .collection("device_event_log")
    .filter(new Query())
    .publishTo(message -> {
        DeviceEvent event = (DeviceEvent) message.getBody();
        // Xử lý có kiểm soát; không bỏ qua errors/checkpoint.
    })
    .build();

container.start();
container.register(request, DeviceEvent.class);

// Chỉ stop tại shutdown lifecycle của ứng dụng:
// container.stop();
```

Đoạn code minh họa các điểm tích hợp, không phải bean Spring hoàn chỉnh; chữ ký/generic types có thể cần điều chỉnh cho phiên bản Spring Data cụ thể. Không đưa `container.stop()` ngay sau `register(...)` trong production. Khi listener lỗi, cần quan sát error handler/container task và cơ chế phục hồi riêng.

### 8.1. Không tự mở blocking cursor trên request thread

`MongoCursor` trong synchronous driver có phương thức đọc blocking. Nếu đặt một vòng `while(true)` đợi tailable events trên thread phục vụ HTTP request, request có thể chiếm thread vô thời hạn và shutdown khó.

Với imperative Spring Data, ưu tiên `MessageListenerContainer` và executor/lifecycle phù hợp. Với reactive, giữ luồng `Flux`/subscription trong component có chủ sở hữu và chính sách dừng.

### 8.2. Imperative listener cũng cần phân biệt im lặng và chết

Một callback `MessageListener` **không được gọi** trong một phút có thể là hoàn toàn bình thường nếu không có insert. Muốn biết cursor còn sống, phải xem subscription/container task state, errors, driver monitoring và thiết kế heartbeat; không lấy “listener không chạy” làm bằng chứng MongoDB đã hỏng.

## 9. Những nguyên nhân khiến cursor không còn hợp lệ

Không có một nguyên nhân duy nhất cho “tailable cursor stopped”. Cần phân loại theo tầng:

| Nhóm | Ví dụ | Đặc điểm | Chính sách sơ bộ |
| --- | --- | --- | --- |
| **Dữ liệu và vị trí cursor** | Capped collection ghi đè vị trí mà cursor đang dựa vào; capped position lost | Cursor có thể mất hiệu lực dù kết nối mạng vẫn tốt | Reopen **kèm đánh giá lỗ hổng dữ liệu** |
| **Query và collection** | Truy vấn ban đầu không match, collection không capped, sort không hỗ trợ | Có thể complete sớm hoặc báo lỗi tùy trường hợp | Sửa query/config; chỉ reopen khi có điều kiện hợp lý |
| **Collection lifecycle** | Drop, recreate, rename/cấu trúc đổi | Cursor cũ không còn bám đúng collection | Dừng, xác minh schema và scope; bootstrap lại |
| **MongoDB topology** | Primary stepdown, election, node unavailable | Transient network/server error có thể phục hồi | Retry có backoff, quan sát state và kiểm tra gap |
| **Network / client** | Socket reset, server selection timeout, pool pressure | Có thể phát lỗi từ driver/reactive publisher | Retry có giới hạn; không áp cho mọi exception |
| **Security** | Credentials hết hạn, role mất quyền, authentication failure | Retry y nguyên không giải quyết | Fail-fast và cảnh báo vận hành |
| **Application lifecycle** | JVM shutdown, `dispose()`, upstream `take(1)`, HTTP disconnect | Cursor bị đóng **theo chủ đích** | Cleanup, không tự khởi động lại |
| **Business downstream** | Handler ném exception, checkpoint store lỗi | Có thể làm toàn stream terminate nhưng cursor nguồn không hỏng | Xử lý business error, không lặp source mù quáng |

### 9.1. CappedPositionLost: không chỉ là một lỗi cần retry

Một tailable cursor theo dõi capped collection phải giữ được vị trí khi đọc. Nếu collection ghi nhanh, consumer xử lý chậm hoặc bị dừng, document ở vị trí cần đọc có thể bị **ghi đè**. MongoDB có thể báo lỗi kiểu **capped position lost**. Reopen cho phép đọc dữ liệu còn giữ được, nhưng **không thể khôi phục những document đã biến mất**.

```text
Cursor last saw E005

Producer fast:
  E006 ... E500 inserted

Capped collection now retains only:
  E300 ... E500

Cursor position E006 no longer available
       |
       +--> cursor error / invalid
       |
       +--> reopen from existing data
                 |
                 +--> E006..E299 cannot be read here
```

Nếu SLA yêu cầu “không mất một event nào”, cần archive/outbox/queue durable hoặc quy trình rebuild, không chỉ tăng số lần reconnect.

### 9.2. Drop/recreate collection

Khi một collection bị drop rồi tạo lại cùng tên, **cursor cũ không tự trở thành cursor mới trên collection mới**. Hệ thống cần:

1. Nhận biết collection lifecycle có thể đã thay đổi.
2. Xác minh collection mới là capped và có đúng schema/options.
3. Đánh giá checkpoint của collection cũ có còn ý nghĩa không.
4. Quyết định có cần snapshot/rebuild hay không.
5. Chỉ mở lại sau khi các điều kiện được xác nhận.

Không coi “cùng tên `device_event_log`” là bằng chứng chắc chắn cùng một luồng dữ liệu liên tục.

### 9.3. Sai quyền hoặc sai query là lỗi bền vững

Nếu tài khoản không có quyền đọc collection, hoặc MongoDB từ chối `tailable` trên collection thường, retry mỗi 100 ms chỉ tạo log/tải. Hãy phân biệt **configuration error** với network transient bằng mã lỗi/exception chain và fail rõ ràng để người vận hành sửa.

Tránh parse chuỗi message tiếng Anh làm quy tắc duy nhất: driver/server versions có thể thay đổi wording. Khi cần phân loại, ưu tiên loại exception, server error code/code name có kiểm chứng và một error policy được test.

## 10. Retry khi lỗi khác Repeat khi complete

Trong Reactor:

- `retryWhen(...)` subscribe lại **khi upstream phát `onError`** theo chính sách.
- `repeatWhen(...)` subscribe lại **khi upstream phát `onComplete`** theo chính sách.
- Khi subscriber **cancel**, không nên tự động tạo subscription mới.

Vì một tailable stream có thể chết bằng cả **error** lẫn **normal completion**, chỉ gắn `retryWhen` là **chưa đủ** để xử lý mọi trường hợp. Ngược lại, chỉ gắn `repeat()` sẽ không phục hồi lỗi và có nguy cơ vòng lặp nóng.

### 10.1. Cách sai: retry vô hạn mọi lỗi

```java
// PHẢN VÍ DỤ.
return template.tail(new Query(), DeviceEvent.class)
    .retry();
```

Nhược điểm:

- Sai cấu hình cũng retry vô hạn.
- Không có backoff, có thể spam MongoDB.
- Không phân biệt lỗi source với lỗi downstream.
- Không xử lý cursor complete.
- Không có checkpoint nên có thể đọc trùng hoặc mất sự kiện.
- Không cho operator trạng thái fail để hành động.

### 10.2. Cách sai: repeat ngay lập tức

```java
// PHẢN VÍ DỤ khi cursor có thể đóng ngay vì no initial match.
return template.tail(query, DeviceEvent.class)
    .repeat();
```

Khi query không match ở thời điểm mở và cursor complete tức thì, `repeat()` có thể tạo **vòng re-open liên tục**, chiếm CPU, tạo nhiều lệnh query và làm MongoDB quá tải.

### 10.3. Dùng defer để mỗi lần retry tạo cursor mới

```java
Flux<DeviceEvent> newCursorEverySubscribe =
    Flux.defer(() ->
        reactiveTemplate.tail(
            new Query(), DeviceEvent.class));
```

`Flux.defer` giúp mỗi lần subscribe/retry tạo **một Publisher tail mới** và áp lại các quyết định được xây trong supplier. Với checkpoint, cần tải checkpoint **bên trong defer**, không chụp một giá trị cũ rồi dùng lại mãi.

### 10.4. Chính sách reconnect có backoff và giới hạn

File `TailableReconnectSource.java`:

```java
package com.example.monitoring;

import java.time.Duration;
import com.mongodb.MongoSocketException;
import com.mongodb.MongoTimeoutException;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

public final class TailableReconnectSource {

    private final ReactiveMongoTemplate template;

    public TailableReconnectSource(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<DeviceEvent> watchWithReconnect() {
        Flux<DeviceEvent> eachCursor = Flux.defer(
            () -> template.tail(
                new Query(), DeviceEvent.class));

        return eachCursor
            // Chỉ retry lỗi tạm thời đã được phân loại.
            .retryWhen(Retry.backoff(
                    5, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(10))
                .jitter(0.5)
                .filter(TailableReconnectSource::isNetworkProblem))
            // Cursor complete: re-open chậm, không spin.
            .repeatWhen(completions ->
                completions.delayElements(
                    Duration.ofSeconds(3)));
    }

    private static boolean isNetworkProblem(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof MongoSocketException
                    || current instanceof MongoTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là **mẫu reconnect cơ bản** chứ chưa phải một consumer có delivery guarantee. Nếu driver báo lỗi khác như election-related hay vị trí bị ghi đè, bộ phân loại này có thể **dừng** chứ không tự khởi động lại. Điều đó có chủ ý: phải quyết định riêng khi nào error còn an toàn để reopen và khi nào cần reconciliation.

### 10.5. Đọc kỹ ý nghĩa của chuỗi operator

```text
DEFER(create tailable cursor)
          |
          +--> onNext: forward event
          |
          +--> onError:
          |     if transient + retry budget -> backoff -> new subscribe
          |     else -> propagate error to supervisor
          |
          +--> onComplete:
                repeatWhen -> wait 3s -> new subscribe

Cancel/shutdown -> close subscription, no automatic re-open.
```

Trong ví dụ, `retryWhen` chỉ retry những lỗi mà `isNetworkProblem` chấp nhận. Mọi lỗi khác phải nổi lên để supervisor/alert, không bị giấu trong `onErrorResume(ex -> Flux.empty())` — cách giấu lỗi đó vô tình biến một exception thành complete rồi kích hoạt vòng repeat không có phân loại.

### 10.6. Retry budget không phải downtime budget

`Retry.backoff(5, ...)` giới hạn **số lần retry của một chuỗi lỗi**, nhưng không tự xác định hệ thống đã vượt RTO hay cursor bị im lặng bao lâu. Cần có alert, tổng deadline hoặc supervisor quản lý vòng đời ở cấp service.

Sau khi retry hết, hãy **phát error**, đánh dấu consumer degraded/failed và để cơ chế vận hành quyết định tái khởi động. Không loop vô hạn trên mọi error chỉ để dashboard nhìn thấy process còn chạy.

### 10.7. Phân biệt restart và phục hồi dữ liệu

Code `watchWithReconnect()` chỉ giải quyết **liveness của kết nối**, không có checkpoint. Nếu cursor kết thúc và mở lại từ đầu tập dữ liệu đang giữ, consumer có thể nhận nhiều bản ghi đã xử lý; nếu chỉ bắt đầu ở cuối hiện tại, có thể bỏ qua các bản ghi bị tạo trong downtime.

Vì vậy **“reconnect success” ≠ “recovered without data loss”**. Khi nghiệp vụ cần xử lý một lần về mặt hiệu ứng, phải có chiến lược application checkpoint/replay/dedupe ngay từ đầu.

## 11. Vì sao tailable cursor không có resume token?

Change stream trả **resume token** trong event envelope và có cơ chế `resumeAfter(...)`/`startAfter(...)` theo điều kiện oplog. Tailable cursor trả **document của capped collection**, không trả token change-stream.

```text
Change stream:
  ChangeStreamEvent<T>
     +-- event._id = opaque resume token
     +-- operationType / documentKey / fullDocument

Tailable cursor:
  DeviceEvent
     +-- DeviceEvent.id
     +-- DeviceEvent.sequence (nếu application tạo)
     +-- payload fields
     +-- KHÔNG có change-stream resume token
```

Không truyền `DeviceEvent.id` cho `ChangeStreamOptions.resumeAfter(...)`. Chúng thuộc hai giao thức hoàn toàn khác. Tương tự, không coi MongoDB `ObjectId` là một offset toàn cục, tăng đơn điệu theo thứ tự append trong mọi trường hợp.

### 11.1. Nếu cần replay, tự định nghĩa offset có ý nghĩa

Một phương án là thêm `sequence` hoặc `eventId` vào **từng document được append**. Tuy nhiên:

- `eventId` chỉ giúp dedupe nếu unique và ổn định.
- `sequence` dùng làm offset **phải phản ánh một thứ tự ghi đáng tin cậy**. Một counter phát số trước lúc insert không đủ nếu nhiều producer có thể ghi không đúng thứ tự sequence.
- `recordedAt` hoặc `ObjectId` không bảo đảm thứ tự append chính xác qua mọi máy/producer/clock.
- Nếu dữ liệu đã rollover, ngay cả một sequence chính xác cũng **không tạo lại** document đã mất.

Không thiết kế “resume từ `_id > lastId`” như một giải pháp mặc định. Nếu `_id` là UUID ngẫu nhiên, phép so sánh số học/lexicographic chẳng liên quan tới thứ tự append.

### 11.2. Điều kiện để sequence checkpoint có ý nghĩa

Một chiến lược đơn giản có thể dùng khi hệ thống bảo đảm:

1. Mỗi event có một `sequence` tăng đơn điệu **theo đúng thứ tự append trong một stream**.
2. Không có bản ghi sequence thấp hơn được append sau bản ghi sequence cao hơn trong cùng stream.
3. Không có sequence bị dành chỗ nhưng mãi không ghi mà lại hiểu như data loss.
4. Consumer checkpoint chỉ sau durable effect.
5. Có unique `eventId` để idempotency khi replay.

Đây là những **điều kiện về kiến trúc producer**, không phải điều MongoDB/Spring Data tự cam kết.

## 12. Đọc lại từ checkpoint ứng dụng

Giả sử một producer phát `sequence` theo đúng thứ tự append trong phạm vi collection. Kho checkpoint lưu `lastAppliedSequence` cho **mỗi stream/consumer identity**, chẳng hạn:

```javascript
{
  _id: "device-event-consumer-A",
  lastAppliedSequence: NumberLong(1250),
  updatedAt: ISODate("2026-11-20T02:30:00Z"),
  streamVersion: 1
}
```

Khi reconnect, consumer có thể tìm document với `sequence > 1250`. Nhưng nếu ở thời điểm mở chưa có document đáp ứng điều kiện, **tailable cursor có thể đóng sớm**. Vì thế vẫn cần logic reopen có delay, không coi query filter là một subscription vô hạn được bảo đảm.

### 12.1. Checkpoint reader reactive

File `DeviceEventCheckpointStore.java`:

```java
package com.example.monitoring;

import reactor.core.publisher.Mono;

public interface DeviceEventCheckpointStore {

    // Empty means this stream has never completed an event.
    Mono<Long> loadLastAppliedSequence();

    // Must durably persist a monotonic checkpoint,
    // not blindly overwrite a newer checkpoint.
    Mono<Void> saveLastAppliedSequence(long sequence);
}
```

Đây là interface, không phải một repository implementation hoàn chỉnh. Trong production, nên thêm `streamId`, `consumerOwner`, `streamVersion` và kiểm soát monotonic update/fencing khi có nhiều instances.

### 12.2. Tải checkpoint trong Flux.defer, không giữ offset cũ

File `CheckpointAwareTailableSource.java`:

```java
package com.example.monitoring;

import java.time.Duration;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

public final class CheckpointAwareTailableSource {

    private final ReactiveMongoTemplate template;
    private final DeviceEventCheckpointStore checkpoints;
    private final CursorErrorPolicy errorPolicy;

    public CheckpointAwareTailableSource(
            ReactiveMongoTemplate template,
            DeviceEventCheckpointStore checkpoints,
            CursorErrorPolicy errorPolicy) {
        this.template = template;
        this.checkpoints = checkpoints;
        this.errorPolicy = errorPolicy;
    }

    public Flux<DeviceEvent> open() {
        return Flux.defer(() ->
                checkpoints.loadLastAppliedSequence()
                    .defaultIfEmpty(0L)
                    .flatMapMany(lastApplied -> {
                        Query query = Query.query(
                            Criteria.where("sequence")
                                .gt(lastApplied));
                        return template.tail(
                            query, DeviceEvent.class);
                    }))
            .retryWhen(Retry.backoff(
                    5, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(8))
                .filter(errorPolicy::isTemporary))
            .repeatWhen(completions ->
                completions.delayElements(
                    Duration.ofSeconds(2)));
    }

    public interface CursorErrorPolicy {
        boolean isTemporary(Throwable error);
    }
}
```

**Điều kiện tiên quyết:** code này chỉ có ý nghĩa khi sequence được tạo đúng thứ tự append như mục 11.2. `defaultIfEmpty(0L)` chọn sequence đầu tiên từ 1. Nếu stream của dự án bắt đầu số khác hoặc có snapshot offset, phải cấu hình lại.

**Tách biệt error handling:** `CursorErrorPolicy` chỉ nhận diện lỗi tạm thời khi mở/đọc cursor. Lỗi không được chấp nhận đi ra ngoài để supervisor cảnh báo; không âm thầm coi lỗi sai index/collection hoặc capped position lost là network transient có thể retry vô hại.

### 12.3. Một lỗi khó phát hiện: thứ tự cấp sequence khác thứ tự insert

```text
Producer A obtains sequence=100
Producer B obtains sequence=101
Producer B inserts E101 first
Consumer processes 101, checkpoints 101
Producer A inserts E100 later
Consumer resumes with sequence > 101
E100 is now permanently skipped
```

Do đó, nếu có concurrent writers, **một bộ đếm sequence tăng đơn điệu tại lúc cấp ID là chưa đủ**. Cần bảo đảm append order thực tế, dùng một writer/partition có ordering contract, hoặc thiết kế replay bằng event IDs + overlap/deduplication/watermark có kiểm soát. Nếu không bảo đảm được, đừng khẳng định query `sequence > checkpoint` cho “exactly once”.

### 12.4. Không dùng timestamp làm checkpoint tuyệt đối

`recordedAt > lastSeenTimestamp` có thể bỏ sót các event có timestamp bằng nhau hoặc được ghi trễ. `recordedAt >= lastSeenTimestamp` có thể gây duplicate; nhưng duplicate thường dễ xử lý hơn missed events nếu có eventId dedupe.

Nếu phải dùng timestamp, cần độ trễ cho phép (watermark), quét chồng lấp (overlap) có giới hạn, deduplication và kiểm tra retention. Không mặc định timestamp của nhiều producers đồng bộ tuyệt đối.

## 13. Xử lý tuần tự, durable effect rồi checkpoint

Cho một `DeviceEventHandler`:

```java
package com.example.monitoring;

import reactor.core.publisher.Mono;

public interface DeviceEventHandler {
    // Must be idempotent by stable event.id().
    Mono<Void> applyOnce(DeviceEvent event);
}
```

File `DeviceEventConsumer.java`:

```java
package com.example.monitoring;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class DeviceEventConsumer {

    private final CheckpointAwareTailableSource source;
    private final DeviceEventHandler handler;
    private final DeviceEventCheckpointStore checkpoints;

    public DeviceEventConsumer(
            CheckpointAwareTailableSource source,
            DeviceEventHandler handler,
            DeviceEventCheckpointStore checkpoints) {
        this.source = source;
        this.handler = handler;
        this.checkpoints = checkpoints;
    }

    public Flux<DeviceEvent> consume() {
        return source.open()
            .concatMap(event ->
                handler.applyOnce(event)
                    .then(checkpoints.saveLastAppliedSequence(
                        event.sequence()))
                    .thenReturn(event));
    }
}
```

`concatMap` giúp **mỗi event được xử lý xong rồi mới xử lý tiếp event sau** trên nhánh consumer, giữ thứ tự checkpoint. Event có thể được replay khi consumer crash/reconnect, nên `handler.applyOnce` phải idempotent và lưu hiệu ứng bền vững trước khi trả `Mono<Void>` thành công.

### 13.1. Không checkpoint trước business effect

```java
// PHẢN VÍ DỤ: mất event nếu process crash sau checkpoint.
source.open().concatMap(event ->
    checkpoints.saveLastAppliedSequence(event.sequence())
        .then(handler.applyOnce(event)));
```

Nếu `saveLastAppliedSequence` thành công rồi `handler.applyOnce` thất bại, lần restart query `sequence > lastApplied` sẽ bỏ qua event mà business effect chưa được áp dụng.

### 13.2. Không nuốt lỗi rồi checkpoint

```java
// PHẢN VÍ DỤ: đánh dấu processed dù handler lỗi.
handler.applyOnce(event)
    .onErrorResume(error -> Mono.empty())
    .then(checkpoints.saveLastAppliedSequence(
        event.sequence()));
```

Muốn bỏ qua một event có chủ đích, phải có **policy rõ, metric, audit và/hoặc dead-letter record**. Không dùng `onErrorResume` cho mọi lỗi rồi mặc định coi event đã xử lý.

### 13.3. Handler lỗi khác cursor lỗi

Trong code mục 13, `source.open()` có retry riêng cho lỗi cursor, nhưng `handler.applyOnce` nằm **sau** source operator. Nếu handler ném lỗi, nó đi ra ngoài consumer để supervisor xử lý; không được tự động tính là MongoDB cursor bị lỗi.

Lợi ích:

- Tránh mở lại cursor chỉ vì downstream API bị từ chối.
- Có thể phân loại lỗi business, validation, timeout và poison event riêng.
- Không vô tình vượt qua event chưa xử lý.
- Khi restart consumer, checkpoint vẫn trỏ event đã hoàn tất cuối cùng.

### 13.4. Ghi effect và checkpoint trong cùng transaction khi phù hợp

Nếu target read model và checkpoint đều ở **cùng MongoDB deployment hỗ trợ transaction**, có thể cân nhắc một transaction ngắn để vừa ghi **idempotent applied-event marker/effect**, vừa cập nhật checkpoint. Không tự áp một `@Transactional` cho mọi hệ thống ngoài: HTTP, Kafka và cơ sở dữ liệu khác không rollback cùng MongoDB.

Với external side effects, dùng event ID ổn định, consumer inbox/outbox, ACK và reconciliation. Đừng nói “exactly once” chỉ nhờ có `concatMap` và một field `lastAppliedSequence`.

### 13.5. Capped position lost phải làm gì với checkpoint?

Giả sử checkpoint ghi `100`, nhưng capped collection đang giữ event từ `300`:

1. Cursor cũ có thể đã mất vị trí, không thể đọc event `101..299`.
2. Reopen với `sequence > 100` có thể đọc từ `300`.
3. Nếu sequence gap không phải một hiện tượng hợp lệ của producer, đây là **data loss gap**.
4. Không nên checkpoint `300` và âm thầm tuyên bố hoàn tất `101..299`.
5. Cần alert, đánh dấu degraded và thực hiện snapshot/reconciliation từ source bền vững.

**Giới hạn:** nếu sequence được cấp từ counter có lỗ hợp lệ (rollback, bỏ số), không thể chỉ so `next == previous + 1` để kết luận mất dữ liệu. Gap detection phải dựa trên **hợp đồng sequence của producer**, không phải suy luận chung từ MongoDB.

## 14. Ba chiến lược phục hồi và giới hạn của từng cách

Không có một công thức reconnect đúng cho tất cả các hệ thống. Có thể chọn:

### 14.1. Chiến lược A — Live only, chấp nhận mất event

Mỗi lần reconnect, mở tailable cursor trên tập dữ liệu phù hợp mà không cố replay đúng từng document. Chỉ sử dụng khi:

- Consumer chỉ làm mới UI/cache tạm thời.
- Có snapshot/current-state API khác để đồng bộ lại.
- Không có side effect tài chính, điểm thưởng hoặc audit bắt buộc.
- Product owner đã chấp nhận có thể mất một số biến động trong downtime.

Ưu điểm: ít trạng thái, dễ triển khai. Nhược điểm: **không có bảo đảm delivery**; phải diễn đạt rõ trong SLA.

### 14.2. Chiến lược B — Application checkpoint + replay còn retention

Lưu event ID hoặc sequence hợp lệ; khi reconnect, đọc lại các event còn trong capped collection và dedupe.

Điều kiện:

1. Producer có một khóa replay phù hợp và thứ tự append được bảo đảm theo hợp đồng.
2. Consumer xử lý idempotent.
3. Có kiểm tra gap và phương án xử lý nếu checkpoint đã nằm ngoài dữ liệu còn giữ.
4. Tốc độ consumer đủ bắt kịp producer, không chỉ reconnect.

Ưu điểm: có thể phục hồi khỏi network interruptions ngắn. Nhược điểm: **phụ thuộc retention và producer ordering**; không tạo ra exactly-once chỉ bằng query.

### 14.3. Chiến lược C — Durable event source + tailable cursor cho độ trễ thấp

Sự kiện được ghi vào **source bền vững** (outbox/queue/event store) với một offset/event ID có ý nghĩa. Tailable cursor chỉ là kênh nhận nhanh; khi mất kết nối/rollover, consumer so sánh offset và replay từ source bền vững.

Ưu điểm: có cơ chế lấp khoảng dữ liệu thực sự; dễ xác nhận downstream consistency. Nhược điểm: thêm thành phần, chi phí và consistency workflow.

### 14.4. Bảng chọn chiến lược

| Yêu cầu | Live only | Checkpoint trên capped | Durable source + reconcile |
| --- | --- | --- | --- |
| Dashboard chấp nhận vài event bị lỡ | Có thể | Có thể | Thường không bắt buộc |
| Cần replay vài phút khi offline | Không bảo đảm | Có điều kiện | Có |
| Offline vượt thời gian capped giữ dữ liệu | Không | **Không** | Có nếu source còn dữ liệu |
| Tăng điểm thưởng đúng một lần | Không phù hợp | Chỉ khi thêm idempotency và gap handling | Thường phù hợp hơn |
| Audit bắt buộc nhiều tháng | Không phù hợp | Không phù hợp | Cần lưu trữ bền vững theo policy |
| Triển khai ít thành phần | Cao | Trung bình | Thấp hơn |

## 15. Kết nối lại cần một state machine, không chỉ một operator

Đối với consumer phục vụ production, có thể diễn giải trạng thái:

```text
STARTING
   |
   v
VALIDATING_COLLECTION
   |
   +-- non-capped / no permission --> FAILED_CONFIG
   |
   v
OPENING_CURSOR
   |
   +-- temporary error --> BACKOFF --> OPENING_CURSOR
   +-- non-retryable  --> FAILED_CONFIG / MANUAL_REPAIR
   |
   v
ACTIVE (receiving, or validly waiting)
   |
   +-- onNext --> PROCESSING --> CHECKPOINT --> ACTIVE
   |
   +-- onComplete --> CLOSED --> BACKOFF --> OPENING_CURSOR
   |
   +-- network error --> BACKOFF --> OPENING_CURSOR
   |
   +-- capped position lost --> RECONCILIATION_REQUIRED
   |
   +-- cancellation / shutdown --> STOPPED
```

**ACTIVE** không có nghĩa “luôn nhận được sự kiện trong 5 giây”. Đó là một trạng thái liveness, cần được xác nhận qua subscription lifecycle, server health và khi cần heartbeat.

### 15.1. Reconnect không được diễn ra sau chủ động stop

Ví dụ:

```java
import reactor.core.Disposable;

Disposable subscription =
    consumer.consume().subscribe(
        event -> metrics.onProcessed(event),
        error -> metrics.onConsumerFailed(error));

// Ở callback shutdown của component đang sở hữu:
subscription.dispose();
```

`consumer` là instance đã inject/khởi tạo, `metrics` là service giám sát. Đoạn này chỉ minh họa ownership của `Disposable`; production cần integration với Spring lifecycle (`SmartLifecycle` hoặc component tương đương), supervision, readiness và cleanup, không gọi `subscribe()` tùy ý rồi bỏ mất reference.

Khi `dispose()` xảy ra, downstream cancel làm upstream tail kết thúc; không được gắn một vòng “cứ thấy stop lại mở” ngoài subscription khiến JVM shutdown bị treo hoặc cursor mới sinh liên tục.

### 15.2. Đừng ẩn lỗi trong doOnError

```java
source.open()
    .doOnError(error -> metrics.onCursorError(error))
    .onErrorResume(error -> Flux.empty());
```

Đây là **mẫu nguy hiểm**: `onErrorResume` có thể biến mọi lỗi thành normal completion, kích hoạt một lớp `repeatWhen` ở ngoài rồi che mất lý do gốc. Logging/metrics **không thay** phân loại lỗi và quyết định fail-fast/reconcile.

### 15.3. Retry có giới hạn và circuit breaker

Nếu server hỏng, mỗi instance gửi hàng trăm attempts có thể làm tình trạng tệ hơn. Hãy:

- Dùng exponential backoff với jitter.
- Có số lần thử/deadline hợp lý trước khi báo degraded.
- Giới hạn số consumer instances và cursors.
- Đưa cấu hình sai/credential lỗi vào trạng thái cần con người can thiệp.
- Đặt reconnect concurrency và circuit breaker phù hợp khi toàn cụm sự cố.

Không tự “heal” một consumer bằng cách bỏ hết checkpoint rồi bắt đầu lại tại hiện tại; nó có thể xóa bằng chứng của lỗ hổng dữ liệu cần xử lý.

## 16. Heartbeat và health: cách phát hiện cursor còn sống

Đối với một stream sự kiện nghiệp vụ ngẫu nhiên, **thời gian từ `onNext` gần nhất** là metric activity, **không phải bằng chứng kết nối còn sống**.

### 16.1. Ba metric tách biệt

| Metric | Trả lời |
| --- | --- |
| `time_since_last_event` | Bao lâu rồi không nhận một event? |
| `cursor_subscription_active` | Subscription/client task đang còn hoạt động không? |
| `time_since_last_successful_checkpoint` | Bao lâu rồi không áp dụng một event bền vững? |

Ở nguồn tải thấp, hai metric đầu có thể là “1 giờ không có event” và “cursor vẫn active”; điều đó bình thường. Ở nguồn có heartbeat mỗi 5 giây, một phút không có heartbeat mới đáng nghi.

### 16.2. Heartbeat document có contract riêng

Một producer có thể append heartbeat vào capped collection theo chu kỳ:

```javascript
{
  _id: "HB-20261120-020000",
  type: "HEARTBEAT",
  tenantId: "SYSTEM",
  recordedAt: ISODate("2026-11-20T02:00:00Z")
}
```

Nếu dùng heartbeat, hãy xác định:

- Ai chịu trách nhiệm append và điều gì xảy ra khi producer chết?
- Heartbeat có ảnh hưởng retention/rollover của dữ liệu thực không?
- Consumer có đang lọc bỏ heartbeat **tại server** khiến query initial match trở nên rủi ro không?
- Heartbeat có cần checkpoint, hay chỉ là tín hiệu health?
- Lịch phát, ngưỡng cảnh báo và clock skew được tính thế nào?

Không append heartbeat bằng user tenant ID giả, và không lạm dụng heartbeat đến mức nó ghi đè event nghiệp vụ nhanh hơn.

### 16.3. Server maxAwaitTime không phải tổng timeout của stream

Ở MongoDB driver, tailable-await cursors có thể dùng `maxAwaitTimeMS`/`maxAwaitTime` để kiểm soát thời gian một `getMore` chờ dữ liệu trước khi trả về. **Khoảng chờ của một getMore** không đồng nghĩa **cursor phải complete/error sau khoảng đó**, và cũng không có nghĩa một `Flux.timeout` của Reactor có thể được thay thế trực tiếp bằng maxAwaitTime.

Nếu cần điều chỉnh await/batch/driver behavior, kiểm tra API của đúng phiên bản MongoDB Java Driver và Spring Data đang dùng. Không dùng một con số `maxAwaitTimeMS=1000` rồi coi nó là SLA “event phải đến trong 1 giây”.

### 16.4. Đừng lẫn health của MongoDB với health của consumer

MongoDB ping thành công **không chứng minh** stream đã subscribe hoặc checkpoint có tiến triển. Ngược lại, một khoảng không có sự kiện không chứng minh MongoDB đã chết. Readiness/health nên kết hợp:

- Driver connection/server selection.
- Trạng thái subscription/container.
- Error/reconnect counters.
- Checkpoint lag khi nguồn được biết có hoạt động.
- Producer heartbeat hoặc end-to-end synthetic event **chỉ trong môi trường được kiểm soát**.

## 17. Backpressure và tốc độ ghi của capped collection

Tailable cursor có thể nhanh hơn downstream processor. Nếu producer ghi E001–E010000 trong một phút, consumer chỉ xử lý 100 events/phút, **capped collection sẽ ghi đè vị trí trước khi consumer kịp đọc** nếu retention window nhỏ.

### 17.1. Tăng buffer không giải quyết mất dữ liệu về dài hạn

```java
// PHẢN VÍ DỤ nếu dùng buffer vô hạn để che consumer chậm.
source.open()
    .onBackpressureBuffer();
```

Nó có thể chuyển nghẽn từ MongoDB cursor sang memory của ứng dụng; buffer vô hạn rủi ro OOM và không đảm bảo source lịch sử vẫn có. Cần:

- Giảm chi phí handler và I/O downstream.
- Kiểm soát concurrency có giữ ordering/offset.
- Tăng capped size/retention nếu hợp lý.
- Dùng durable queue/outbox nếu event không được phép mất.
- Giám sát tiêu thụ và rate producer/consumer.

### 17.2. Một vài khoảng thời gian cần đo

| Biến | Ý nghĩa |
| --- | --- |
| `write_rate_events_per_second` | Số document được append |
| `bytes_per_second` | Tốc độ tăng dung lượng capped |
| `effective_retention_window` | Khoảng tuổi của document cũ nhất còn tồn tại |
| `process_rate_events_per_second` | Tốc độ consumer áp effect |
| `consumer_lag_events` | Độ chênh về số sequence (nếu có ordering contract) |
| `time_to_catch_up` | Khả năng consumer bắt kịp trước khi rollover |

Một phép ước lượng **mang tính năng lực**, không phải bảo đảm:

```text
retention_seconds ~= capped_size_bytes / observed_write_bytes_per_second
```

Ví dụ, 16 MiB ở tốc độ ghi 1 MiB/s có thể chỉ giữ khoảng 16 giây dữ liệu, chưa tính overhead và giới hạn `max`. Cần đo trên workload thật, đặc biệt khi document size biến động.

### 17.3. Thứ tự checkpoint với parallelism

`source.flatMap(event -> handler.applyOnce(event))` có thể hoàn thành không theo thứ tự. Nếu checkpoint đơn tuyến, dễ ghi offset E105 trước khi E104 xử lý xong. Muốn tăng throughput, phải chia stream theo partition key ổn định và có **per-partition checkpoint/watermark**, không đơn thuần thay `concatMap` bằng `flatMap(concurrency=32)`.

## 18. Kiểm thử tailable cursor phải có capped collection thật

Một unit test mock `ReactiveMongoTemplate.tail(...)` bằng `Flux.just(E1, E2)` chỉ chứng minh service tiêu thụ được Flux. Nó **không** chứng minh:

- MongoDB collection thật có `capped: true`.
- Cursor giữ mở ở cuối dữ liệu.
- Query initial no-match có thể complete/invalid.
- Cursor báo lỗi khi vị trí capped bị ghi đè.
- Reconnect đọc được document còn retention nhưng không lấy được document đã biến mất.
- `@Tailable` của repository được Spring Data thực thi đúng.

Các hành vi này cần **integration test với MongoDB server thật**. Không cần replica set chỉ để test một tailable cursor cơ bản trên capped collection; nhưng môi trường phải có MongoDB hỗ trợ tailable cursor. Nếu cùng test transaction/change streams, các tính năng đó có topology requirements riêng.

### 18.1. Test matrix

| Test | Điều kiện | Mong đợi |
| --- | --- | --- |
| Collection hợp lệ | `capped: true` | Tail có thể nhận document đã có và document append sau |
| Collection không capped | Normal collection | Server/driver từ chối tailable behavior hoặc báo lỗi phù hợp |
| Cursor im lặng | Tạm ngừng insert sau khi đã có match | Không tự phát onNext; terminal state được giám sát riêng |
| Initial no-match | Filter không khớp record đang giữ | Quan sát complete/error/idle theo server/version; supervisor không spin |
| Cursor complete | Fake source `Flux.empty()` | `repeatWhen` mở lại sau delay |
| Transient error | Fake source lỗi cho phép retry | `retryWhen` tôn trọng budget |
| Non-retryable | Fake source lỗi validation/config | Không retry; báo error |
| Cancel | Dispose subscription | Không tự tạo cursor mới |
| Rollover | Collection size nhỏ, producer ghi nhanh | Quan sát mất position/gap; không khẳng định replay đủ |
| Checkpoint | Handler thành công rồi mới save | Event chỉ được checkpoint sau durable effect |
| Crash/replay | Failure giữa effect và checkpoint | Handler idempotent nên không double-apply |
| Producer reorder | Sequence không theo append | Test phát hiện nguy cơ skip event |

### 18.2. Integration test nhận document mới sau khi subscribe

Ví dụ Spring Boot 3.x, JUnit 5, Reactor Test, Spring Data MongoDB reactive. **Chỉ chạy trên một MongoDB TEST được cấp quyền với database riêng**. Tạo collection tên ngẫu nhiên để không đụng dữ liệu khác.

File `TailableCursorIntegrationTest.java`:

```java
package com.example.monitoring;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class TailableCursorIntegrationTest {

    @Autowired
    ReactiveMongoTemplate template;

    private static DeviceEvent event(
            String id, long sequence, String level) {
        return new DeviceEvent(
            id, sequence, "TENANT-TEST",
            "DEV-TEST", level, "test",
            Instant.parse("2026-11-20T02:00:00Z"));
    }

    @Test
    void receivesAnAppendAfterInitialDocument() {
        String name = "tail_test_"
            + UUID.randomUUID().toString()
                .replace("-", "");

        String suffix = UUID.randomUUID().toString();
        DeviceEvent first =
            event("E1-" + suffix, 1L, "INFO");
        DeviceEvent second =
            event("E2-" + suffix, 2L, "WARN");

        try {
            StepVerifier.create(
                template.createCollection(
                    name,
                    CollectionOptions.empty()
                        .capped()
                        .size(2 * 1024 * 1024)
                        .maxDocuments(1000)))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(template.insert(first, name))
                .expectNextCount(1)
                .verifyComplete();

            Flux<DeviceEvent> tail = template.tail(
                new Query(), DeviceEvent.class, name)
                .take(2);

            StepVerifier.create(tail)
                .assertNext(actual -> {
                    assertThat(actual.id()).isEqualTo(first.id());
                    assertThat(actual.sequence()).isEqualTo(1L);
                })
                // Đã nhận event đầu: cursor có subscription,
                // tránh chỉ sleep rồi đoán watcher đã sẵn.
                .then(() -> StepVerifier.create(
                        template.insert(second, name))
                    .expectNextCount(1)
                    .verifyComplete())
                .assertNext(actual -> {
                    assertThat(actual.id())
                        .isEqualTo(second.id());
                    assertThat(actual.sequence())
                        .isEqualTo(2L);
                })
                .expectComplete()
                .verify(Duration.ofSeconds(20));
        } finally {
            // Chỉ drop collection độc lập của test job.
            StepVerifier.create(template.dropCollection(name))
                .verifyComplete();
        }
    }
}
```

Vì đã seed `first` **trước khi subscribe** và `StepVerifier` chờ nhận `first` rồi mới insert `second`, bài kiểm tra tránh được race phổ biến: “gửi insert trong lúc cursor chưa mở”. `take(2)` chủ động hủy upstream sau hai bản ghi; đây là hành vi **của test**, không phải cursor đã tự hoàn tất.

### 18.3. Không chạy drop trên database thật

Ví dụ dùng collection tên ngẫu nhiên nhưng vẫn có `dropCollection(name)` trong `finally`. Bắt buộc cấu hình profile/test URI đến **database cô lập**, không chia sẻ với dev/prod. Không đưa đoạn code này vào một service khởi tạo lúc production start.

Trước khi chạy test, kiểm tra:

1. MongoDB test connection được cấp quyền tạo/xóa collection.
2. Database chỉ phục vụ test hoặc container.
3. Collection có `capped=true` và size hợp lý.
4. Test runner có Reactor Test và Spring Data MongoDB reactive dependencies.
5. MongoDB/driver version phù hợp với API.

Test là **mã minh họa** trong tài liệu, không có tuyên bố đã được biên dịch/thực thi ở bước soạn Markdown.

### 18.4. Test initial no-match nhưng không giả định kết quả của mọi phiên bản

Trong một test khác, seed document chỉ có `level=INFO`, rồi tail bằng query `level=CRITICAL`. Theo dõi cả ba tín hiệu:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

AtomicBoolean sourceCompleted = new AtomicBoolean(false);
AtomicReference<Throwable> sourceError =
    new AtomicReference<>();

Query criticalOnly = Query.query(
    Criteria.where("level").is("CRITICAL"));

Flux<DeviceEvent> tail = template
    .tail(criticalOnly, DeviceEvent.class, testCollectionName)
    .doOnComplete(() -> sourceCompleted.set(true))
    .doOnError(sourceError::set);

// Giới hạn thời gian quan sát ở phía test.
StepVerifier.create(
        tail.take(Duration.ofSeconds(2)))
    .verifyComplete();

System.out.println("Source completed = "
    + sourceCompleted.get());
System.out.println("Source error = "
    + sourceError.get());
```

Đây là **đoạn test method** có `template`, `testCollectionName`, `StepVerifier` và imports sẵn. Mục đích không phải assert rằng mọi MongoDB version đều complete trong một khoảng cố định; là quan sát **source completion/error riêng với việc test timeout tự cancel upstream**. Nếu source phát error, test cần assert error theo fixture cụ thể, không ẩn nó rồi tuyên bố luôn PASS.

### 18.5. Unit test repeatWhen không cần MongoDB

Khi kiểm thử **chính sách reopen**, mock một nguồn hoàn tất ngay:

```java
package com.example.monitoring;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class TailableReconnectPolicyTest {

    @Test
    void reopensAfterTwoEmptyCompletions() {
        AtomicInteger opens = new AtomicInteger();
        DeviceEvent expected = new DeviceEvent(
            "TEST-" + UUID.randomUUID(),
            1L, "TEST", "DEV", "INFO",
            "arrived", java.time.Instant.now());

        Flux<DeviceEvent> syntheticSource =
            Flux.defer(() -> {
                int attempt = opens.incrementAndGet();
                if (attempt <= 2) {
                    return Flux.<DeviceEvent>empty();
                }
                return Flux.just(expected);
            });

        Flux<DeviceEvent> reopen =
            syntheticSource
                .repeatWhen(completions ->
                    completions.delayElements(
                        Duration.ofMillis(20)))
                .take(1);

        StepVerifier.create(reopen)
            .expectNext(expected)
            .verifyComplete();

        assertThat(opens.get()).isEqualTo(3);
    }
}
```

Test này chỉ chứng minh **Reactor resubscribe sau complete** mà không quay vòng tức thì. Nó không chứng minh MongoDB cursor sẽ complete khi no-match ở mọi version, cũng không kiểm tra capped position loss.

### 18.6. Unit test retry budget và fail-fast

Một test khác nên đưa vào nguồn lỗi:

- Error A thuộc nhóm tạm thời → policy cho retry một số lần rồi phục hồi.
- Error B thuộc nhóm permission/config → policy không retry, phát `onError`.
- Sau khi retry budget cạn → stream phát lỗi tới supervisor.
- Sau cancel từ `take(1)` hoặc `Disposable.dispose()` → không có re-subscription ngoài ý muốn.

Không phải tạo một cluster bị mất kết nối thật để kiểm tra **thuần policy Reactor**; unit test với `Flux.defer`/`Flux.error` đủ. Nhưng để kiểm tra driver thật/close semantics, cần test tích hợp riêng.

## 19. Tạo lỗi rollover trong môi trường kiểm thử

Rollover là hiện tượng phụ thuộc tốc độ/size và lịch xử lý cursor. Một test có thể:

1. Tạo capped collection rất nhỏ trên **MongoDB test cô lập**.
2. Seed event E001 và mở tail.
3. Cố ý trì hoãn consumer (trong test) và append nhiều documents có payload tương đối lớn để buộc capped vòng.
4. Quan sát sự kiện có thể bị ghi đè và lỗi position lost.
5. Dừng, inspect collection để biết sequence nhỏ nhất còn giữ.
6. So với checkpoint để xác định khoảng dữ liệu không thể replay.
7. Assert trạng thái **RECONCILIATION_REQUIRED** theo business policy thay vì tự đánh dấu thành công.

Không viết một test ép `CappedPositionLost` luôn xảy ra sau đúng 100 inserts: hành vi phụ thuộc storage, batch, scheduling, phiên bản MongoDB và thời điểm cursor getMore. Điều đáng xác minh là **khi phát hiện gap/position lost, consumer không âm thầm bỏ qua**.

### 19.1. Một chỉ số retained range

Nếu producer có sequence theo append order và capped collection đang giữ E300–E500, việc đọc lại:

```javascript
db.device_event_log.find().sort({ $natural: 1 }).limit(1);
```

cho biết một document ở đầu dữ liệu **còn tồn tại**. Nhưng đây là truy vấn **thường**, không phải tail. Từ document đầu, consumer có thể đối chiếu với checkpoint theo đúng hợp đồng sequence. Không kết luận “không có gap” chỉ vì document đầu còn có `_id` tăng dần — điều đó không chứng minh tất cả event đã được xử lý.

## 20. Metrics và log cho reconnect

Một hệ thống có thể liên tục reconnect mà không cảnh báo nếu metrics chỉ đo “service process còn sống”. Cần tách liveness, correctness và data retention.

### 20.1. Những metrics nên theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| `tailable_cursor_open_attempts_total` | Số lần cố mở cursor |
| `tailable_cursor_active` | Số subscription/cursor đang mở theo stream |
| `tailable_cursor_completed_total` | Nguồn phát `onComplete`, phân biệt cancel |
| `tailable_cursor_errors_total` | Error theo loại: transient, config, position lost |
| `tailable_cursor_reconnect_total` | Số lần mở lại do error hoặc complete |
| `tailable_cursor_reconnect_delay_seconds` | Thời gian chờ trước attempt tiếp |
| `tailable_cursor_retry_exhausted_total` | Retry budget đã cạn |
| `tailable_events_received_total` | Số document source phát ra |
| `tailable_events_processed_total` | Số business effects đã xử lý bền vững |
| `tailable_checkpoint_write_failure_total` | Số lần không ghi được checkpoint |
| `tailable_checkpoint_sequence` | Offset cuối đã áp theo stream (chỉ khi sequence hợp lệ) |
| `tailable_duplicate_event_total` | Sự kiện lặp được dedupe |
| `tailable_gap_detected_total` | Phát hiện khoảng không thể replay/ordering gap |
| `tailable_oldest_retained_age_seconds` | Tuổi của document cũ nhất còn giữ |
| `tailable_handler_duration_seconds` | Thời gian xử lý downstream |

Không gắn event ID, user ID hoặc tenant có cardinality cao làm metric labels. Sử dụng stream name, worker role, error category và environment có tập giá trị hữu hạn. Với logs, dùng correlation ID an toàn; tránh ghi nguyên payload chứa PII.

### 20.2. Phân loại log có cấu trúc

```json
{
  "event": "tailable_cursor_reconnect",
  "stream": "device-event-log",
  "cause": "CURSOR_COMPLETED",
  "action": "REOPEN_AFTER_BACKOFF",
  "attempt": 3,
  "delayMs": 2000,
  "checkpointMode": "APPLICATION_SEQUENCE",
  "dataGapStatus": "NOT_YET_CHECKED"
}
```

`dataGapStatus` phải được giữ là **chưa kiểm tra** cho tới khi có evidence producer/retained-range phù hợp. Đừng log `"recovered": true` chỉ vì MongoDB đã chấp nhận cursor mới.

### 20.3. Cảnh báo theo tác động, không chỉ đếm errors

Ví dụ:

- **Reconnect rate tăng**, chưa có gap: kiểm tra mạng, election, connection pool và server selection.
- **Checkpoint age tăng** trong lúc producer vẫn phát đều: kiểm tra downstream slow/blocked, event processing exceptions.
- **Capped retention window giảm dưới RTO mục tiêu**: cần tăng capacity hoặc giảm tốc độ ghi/bổ sung durable source.
- **Position lost**: ưu tiên data reconciliation, không chỉ khởi động lại process.
- **Active=0** khi supervisor đã được yêu cầu chạy: kiểm tra shutdown/cancellation và error path.
- **Received tăng nhưng processed không tăng**: lỗi business handler, không mặc định cursor mất kết nối.

## 21. Runbook: xử lý sự cố “không nhận sự kiện mới”

Đi lần lượt theo chứng cứ:

### Bước 1 — Kiểm tra producer

- Có thật sự append event mới vào đúng collection/database không?
- Event được append có đúng shape và tenant không?
- Producer có bị chặn bởi validation, permission hoặc quota không?
- Có document mới khi chạy **truy vấn thường** (đọc kiểm tra được cấp quyền) không?

Nếu không có insert, tail yên lặng là hành vi bình thường.

### Bước 2 — Xác minh collection

```javascript
db.device_event_log.isCapped();
db.getCollectionInfos({ name: "device_event_log" });
```

Kiểm tra:

- Capped=true?
- Collection có bị drop/recreate?
- Đúng database/collection name?
- Có còn dữ liệu trong thời gian retention?

Không tự thay `size` hoặc drop/recreate production collection khi chưa có kế hoạch migration và quyền phù hợp.

### Bước 3 — Kiểm tra subscription/driver

- `Flux` có được subscribe không?
- Có `onComplete`, `onError` hoặc `cancel` trong logs/traces không?
- Imperative listener container có đang chạy không, task đã lỗi chưa?
- Application shutdown hoặc request disconnect có dispose cursor không?
- MongoDB server selection có lỗi hoặc primary election không?

Không dùng “last onNext đã 5 phút” làm chẩn đoán duy nhất.

### Bước 4 — Kiểm tra query ban đầu

- Có filter quá hẹp khiến **initial no-match** không?
- Có dùng sort không phù hợp với tailable cursor?
- Có query không có initial match nhưng code chỉ chờ mà không giám sát completion?
- Có đang lọc theo tenant chưa từng có document trong capped collection?

Nếu query có thể đóng sớm do no-match, điều chỉnh policy reopen có delay hoặc thiết kế lại scope; không tạo reconnect loop dưới 100 ms.

### Bước 5 — Kiểm tra lỗi và phân loại

| Lỗi quan sát | Hành động |
| --- | --- |
| Socket timeout / server selection transient | Retry có backoff/budget; kiểm tra network/cluster |
| Cursor complete | Repeat/reopen có delay nếu consumer còn được yêu cầu chạy |
| Collection không capped | Fail config, không retry vô hạn |
| Capped position lost | Reconcile/gap detection trước khi tuyên bố recovery |
| Authentication/authorization failure | Fail-fast, sửa credentials/roles |
| Query invalid/unsupported sort | Sửa code/query, chạy test |
| Handler/checkpoint lỗi | Xử lý downstream, không checkpoint event lỗi |
| Chủ động dispose | Không auto-reconnect |

### Bước 6 — Đánh giá khả năng mất dữ liệu

1. Đọc checkpoint cuối được lưu bền vững.
2. Xác định document cũ nhất còn trong capped collection (theo natural order).
3. Nếu có sequence hợp lệ, so sánh theo **hợp đồng thứ tự append thực tế**.
4. Nếu có gap, ghi nhận phạm vi dữ liệu có thể đã mất và source nào có thể backfill.
5. Không tự nâng checkpoint lên current để dập cảnh báo.
6. Sau reconciliation, khôi phục consumer và quan sát checkpoint bắt kịp nguồn.

### Bước 7 — Hậu kiểm

Ghi lại nguyên nhân: config, network, rollover, consumer lag, data retention, unauthorized query hay lifecycle bug. Cập nhật monitoring, capacity sizing và integration tests để tránh tái diễn.

## 22. So sánh tailable cursor, change stream và polling

| Tiêu chí | Tailable cursor | Change stream | Polling có checkpoint |
| --- | --- | --- | --- |
| Dữ liệu nguồn | **Capped collection** | Replica set/sharded MongoDB hỗ trợ | Collection/truy vấn phù hợp |
| Mục đích | Đọc documents append mới | Theo dõi **thay đổi** insert/update/delete/... | Đọc những bản ghi đáp ứng điều kiện theo chu kỳ |
| Envelope sự kiện MongoDB | Không có operationType/resume token như change stream | Có `ChangeStreamEvent<T>`/resume token | Không có, trừ khi tự thiết kế |
| Resume | Tự định nghĩa checkpoint/replay | Resume token trong phạm vi oplog/history | Keyset/checkpoint tự thiết kế |
| Retention | Dung lượng capped, rollover | Oplog/change-stream history | Theo collection/history policy |
| Cập nhật/xóa source | Không phải sự kiện update/delete của collection thường | Có thể phát sự kiện tương ứng | Tùy query/thiết kế delta |
| Không có event | Cursor có thể await; initial no-match cần xử lý | Cursor sống dài, thường chờ thay đổi | Lần poll trả rỗng bình thường |
| Reconnect | Mở cursor mới, đánh giá gap | Driver resume + token theo điều kiện | Poll lại theo checkpoint |
| Hạ tầng bắt buộc | Capped collection | Replica set/sharded cluster | Không nhất thiết capped |
| Dùng cho audit bền vững | Không đủ nếu chỉ có capped | Không đủ nếu lịch sử bị cuốn mất | Cần source bền vững |

### 22.1. Khi nên chọn tailable cursor

Phù hợp khi:

- Dữ liệu vốn là một **append-only log ngắn hạn** được lưu trong capped collection.
- Producer/consumer gần thời gian thực, downtime ngắn và có retention window đủ.
- Ứng dụng chấp nhận policy liveness/recovery rõ.
- Không cần event envelope của update/delete ở các collection khác.

### 22.2. Khi nên chọn change stream

Phù hợp hơn nếu:

- Cần phản ứng trước **thay đổi** của collection thường.
- Cần `operationType`, `documentKey`, update delta và resume token.
- Cần theo dõi nhiều collection trong database/deployment được hỗ trợ.
- Hệ thống đã có replica set/sharded cluster.

Change streams vẫn có giới hạn oplog retention, duplicates/retry và checkpoint. Đừng hiểu “có resume token” là bảo đảm replay vĩnh viễn.

### 22.3. Khi polling có thể đơn giản hơn

Nếu ứng dụng chỉ cần làm mới bảng thống kê mỗi phút, một query có index/checkpoint và scheduler **có thể đơn giản hơn** một stream dài hạn. Polling dễ quan sát vòng đời mỗi request, nhưng cần tránh full scans và thiết kế keyset/idempotency nếu event không được phép mất.

Việc chọn mô hình phải dựa trên SLA, tốc độ ghi, retention và yêu cầu delivery, không chỉ vì một API có tên “reactive” hay “real-time”.

## 23. Những hiểu nhầm cần loại bỏ

1. **“Tailable hoạt động trên mọi collection.”** Sai: cần capped collection.
2. **“Không có event 10 giây là cursor chết.”** Sai: có thể chỉ đang chờ.
3. **“Flux.empty() là cursor đang đợi.”** Sai: đó là completion ngay.
4. **“Không match ban đầu sẽ luôn đợi document tương lai.”** Không được bảo đảm; có thể cursor dead/close.
5. **“Chỉ retryWhen là xử lý được mọi kết thúc.”** Sai: complete không phải error.
6. **“Chỉ repeat là đủ.”** Sai: không xử lý error và có thể tạo hot loop.
7. **“Timeout là heartbeat.”** Không: `timeout` có thể hủy cursor hợp lệ.
8. **“Cứ reconnect thì không mất dữ liệu.”** Sai: capped rollover có thể đã ghi đè lịch sử.
9. **“Document ID là change-stream resume token.”** Sai: hai loại cursor khác nhau.
10. **“ObjectId luôn là offset theo thứ tự insert.”** Không có bảo đảm toàn cục như vậy.
11. **“Counter sequence tăng là đủ cho đúng thứ tự.”** Chưa đủ nếu insert của writers bị đảo.
12. **“Checkpoint trước khi handler chạy cho nhanh hơn.”** Sai: dễ mất event sau crash.
13. **“Dùng flatMap song song vẫn ghi checkpoint đơn tuần tự được.”** Không nếu không có watermark/partitioning.
14. **“No match thì mở lại ngay không delay.”** Sai: dễ tạo vòng lặp nóng.
15. **“Đổi sort thành recordedAt sẽ đúng hơn.”** Không phù hợp với semantics tailable natural order.
16. **“dispose() cũng cần tự reconnect.”** Sai: cancel có chủ đích cần cleanup và dừng.
17. **“MongoDB ping được thì stream chắc còn hoạt động.”** Sai: subscription/lifecycle riêng.
18. **“Một capped collection tự là durable queue.”** Sai: không có ACK/consumer group/retention vô hạn.
19. **“@Tailable tự xử lý reconnect và dedupe.”** Không; ứng dụng phải thiết kế.
20. **“Mock Flux.just() đủ kiểm chứng cursor.”** Không: cần integration test với capped collection thật.

## 24. Checklist code review trước khi triển khai

### 24.1. Data contract và collection

1. **Capped collection thật:** đã xác minh `isCapped()`/collection options, không chỉ đặt annotation.
2. **Kích thước retention:** `size`/`max` đáp ứng tốc độ ghi và thời gian offline mục tiêu.
3. **Schema ổn định:** entity Java mapping đúng field, version và collection.
4. **Event ID:** có khóa ổn định để dedupe khi cần.
5. **Sequence nếu dùng:** có **hợp đồng append ordering** và test producer concurrency.
6. **Không đòi replay vô hạn:** có archive/rebuild policy khi vượt retention.
7. **Không xóa/drop trong routine:** tránh làm cursor invalid và mất dữ liệu ngoài kế hoạch.

### 24.2. Cursor/query lifecycle

8. **Đúng API:** `ReactiveMongoTemplate.tail`/`@Tailable` hoặc `MessageListenerContainer`.
9. **Natural order:** không sort theo field tùy ý trên tailable query.
10. **Initial no-match:** đã test và có policy reopen có delay.
11. **Idle khác complete:** không coi khoảng không có `onNext` là cursor dead.
12. **Complete khác error:** có `repeatWhen` policy và `retryWhen` policy riêng.
13. **Fail-fast trên cấu hình sai:** permission, non-capped, query invalid không retry vô hạn.
14. **Capped position lost:** nhận diện và chuyển sang reconcile/alert.
15. **Backoff/jitter:** không tạo reconnect storm.
16. **Retry budget:** khi cạn budget phải phát status fail/degraded.
17. **Cancel/shutdown:** không tự mở cursor mới sau stop.
18. **Single ownership:** không tạo vô hạn cursors từ các HTTP requests.

### 24.3. Processing và checkpoint

19. **Replay mode rõ:** live-only, capped checkpoint hay durable source.
20. **Checkpoint sau durable effect:** không ngược thứ tự.
21. **Idempotency:** replay/multiple replicas không tạo duplicate business effect.
22. **Không swallow error:** handler lỗi không được tự checkpoint.
23. **Ordered processing:** `concatMap` hoặc partition-aware watermark, không checkpoint vượt event chưa xong.
24. **Gap detection:** có policy cho rollover/consumer lag; không tự tăng checkpoint qua gap.
25. **Không nhầm ID:** `ObjectId`, timestamp hay `ChangeStreamOptions` token không được giả định làm tailable offset.
26. **Hỗ trợ failover:** phân loại network lỗi và lập kế hoạch recovery khi collection lifecycle đổi.

### 24.4. Validation và vận hành

27. **Unit tests:** retry budget, complete-repeat, cancel, fail-fast.
28. **Integration tests:** capped thật, initial match, append sau subscribe, initial no-match.
29. **Fault scenarios:** rollover, network/driver disconnect, process restart khi có checkpoint.
30. **Đúng môi trường:** test isolation; không drop dữ liệu dùng chung.
31. **Metrics:** active, error, reconnect, checkpoint, lag, capped retention và gaps.
32. **Runbook:** cảnh báo có đường xử lý config vs transient vs data loss.
33. **Security:** tenant scoped, không expose raw event/PII cho client tùy ý.
34. **SLA đúng:** hiểu khác biệt giữa streaming “gần thời gian thực” và “không mất event”.

## 25. Bài tập thực hành

Ứng dụng có capped collection `sensor_events` với các sự kiện:

```javascript
{
  _id: "EVT-500",
  sequence: NumberLong(500),
  sensorId: "S-01",
  tenantId: "TENANT-A",
  kind: "MEASUREMENT",
  value: 37.8,
  recordedAt: ISODate("2026-11-20T02:00:00Z")
}
```

### Bài tập 1 — Phân loại terminal signals

Cho năm tình huống:

1. Không có insert trong 15 phút, cursor chưa `onComplete/onError`.
2. Cursor phát `onComplete` ngay sau khi query `kind="ALERT"` chưa match document nào.
3. Driver phát network timeout.
4. MongoDB báo capped position lost.
5. Operator shutdown app và dispose subscription.

Với từng tình huống, điền:

| Tình huống | Có reconnect không? | Có cần kiểm tra mất dữ liệu không? |
| --- | --- | --- |
| 1 | Không chỉ vì im lặng | Chỉ khi có evidence lag/retention |
| 2 | Có thể reopen sau delay nếu stream cần tiếp tục | Tùy replay/offset policy |
| 3 | Retry có giới hạn nếu lỗi transient | Có nếu downtime có thể vượt retention |
| 4 | Reopen chỉ sau đánh giá/reconcile | **Có, ưu tiên** |
| 5 | **Không** | Theo shutdown/restart contract |

Giải thích vì sao `timeout(Duration.ofSeconds(10))` không phải lời giải mặc định cho (1).

### Bài tập 2 — Capped collection và query

Tạo một collection test:

```javascript
db.createCollection("sensor_events_test", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
});
```

Hãy:

1. Xác minh `isCapped()` trả true.
2. Seed một event `MEASUREMENT`.
3. Mở một tailable cursor với query rỗng.
4. Append thêm event `ALERT` **sau khi đã xác minh cursor nhận seed**.
5. Quan sát event mới và terminal signals.
6. Thử query ban đầu `kind="NEVER-SEEN"`, quan sát sự khác biệt.

Chỉ thực hiện trên MongoDB test riêng. Không dùng data/capped collection của production.

### Bài tập 3 — Retry hay Repeat?

Đánh giá:

```java
Flux<DeviceEvent> events =
    template.tail(new Query(), DeviceEvent.class)
        .retryWhen(Retry.backoff(
            3, Duration.ofMillis(100)));
```

Vì sao code trên **không xử lý normal completion**? Thêm `repeatWhen` với delay thích hợp, phân biệt error retryable và non-retryable, và giải thích vì sao không cần repeat sau `cancel`.

### Bài tập 4 — Một vòng lặp nóng

Một API dùng:

```java
return template.tail(
        Query.query(Criteria.where("tenantId")
            .is("TENANT-NOT-YET-SEEN")),
        DeviceEvent.class)
    .repeat();
```

Giả sử MongoDB trả cursor complete ngay khi no-match. Hãy giải thích vì sao query bị mở lại liên tục, cách `repeatWhen(...delayElements(...))` sửa được vấn đề liveness nhưng **không tự bảo đảm delivery**, và cách thiết kế initial match/filter để tránh vấn đề.

### Bài tập 5 — Chọn checkpoint

Một team dự định lưu `lastSeenObjectId` rồi dùng:

```java
Criteria.where("_id").gt(lastSeenObjectId)
```

Phản biện:

- `ObjectId` có chắc tăng theo append order giữa các JVM writers không?
- Có thể document có `_id` dạng UUID ngẫu nhiên không?
- Khi capped collection rollover thì sao?
- Chỉ có `_id` có đủ để phát hiện bỏ sót không?
- Có thể chọn `eventId` để dedupe và một sequence/offset có producer contract riêng không?

### Bài tập 6 — Producer reorder

Diễn biến:

```text
t0 A reserves sequence 100
t1 B reserves sequence 101
t2 B inserts E101
t3 consumer checkpoints 101
t4 A inserts E100
t5 consumer reconnects with sequence > 101
```

Hãy chứng minh event E100 bị bỏ qua trong chiến lược checkpoint đơn giản. Đề xuất cơ chế buộc append ordering, hoặc overlap/dedupe/watermark có khả năng xử lý late arrivals.

### Bài tập 7 — Checkpoint sau xử lý

Code sai:

```java
source.flatMap(event ->
    checkpoint.saveLastAppliedSequence(
        event.sequence())
        .then(service.apply(event)));
```

Chỉ ra:

1. Checkpoint xảy ra trước effect.
2. `flatMap` có thể làm sequence hoàn tất đảo thứ tự.
3. Crash sau checkpoint làm mất event chưa xử lý.

Viết lại bằng `concatMap`, `applyOnce` có idempotency và checkpoint sau khi effect bền vững. Giải thích trường hợp crash sau effect nhưng trước checkpoint gây replay nhưng không double-apply.

### Bài tập 8 — Rollover và data gap

Consumer checkpoint 100, nhưng collection đang giữ từ 300 trở đi. Chọn một trong ba chiến lược:

- Live-only: bỏ qua lỗ hổng theo SLA đã chấp thuận, rebuild snapshot UI nếu cần.
- Checkpoint + capped: báo `RECONCILIATION_REQUIRED`, không tuyên bố xử lý đủ.
- Durable source: lấy E101..299 từ archive/outbox/queue rồi mới bắt kịp realtime.

Tại sao chỉ tăng `size` của capped collection **sau khi sự kiện đã bị ghi đè** không khôi phục được lịch sử cũ?

### Bài tập 9 — Thiết kế health

Hệ thống không nhận event mới trong 20 phút nhưng MongoDB ping vẫn thành công. Thiết kế bảng quan sát:

```text
source_has_new_data?
subscription_active?
source_completed_or_error?
producer_heartbeat_due?
checkpoint_age?
capped_retention_window?
```

Giải thích những trường hợp:

- Producer thật sự im lặng.
- Cursor đã complete nhưng supervisor không reopen.
- Handler lỗi nên không cập nhật checkpoint.
- Cursor còn active nhưng producer đã tắt.

### Bài tập 10 — Test reconnect không cần MongoDB

Tạo `Flux.defer`:

- Attempt 1: `Flux.empty()`.
- Attempt 2: `Flux.empty()`.
- Attempt 3: `Flux.just(E1)`.

Dùng `repeatWhen` với delay ngắn và `take(1)`, assert đã mở ba lần. Sau đó thêm một nhánh error có `retryWhen` budget 2, một error non-retryable và một cancel test. Không dùng `Thread.sleep` để phỏng đoán thứ tự.

### Bài tập 11 — Khi nào chuyển sang change stream?

Một hệ thống lúc đầu dùng capped `device_event_log`, nhưng sau đó yêu cầu theo dõi **update/delete** trong collection `devices` bình thường và có resume token từ MongoDB. Trả lời:

1. Vì sao `@Tailable` trên `devices` không giải quyết yêu cầu?
2. Change stream cần topology nào?
3. Nó cung cấp những metadata gì khác tailable?
4. Resume token có thể mất hiệu lực khi lịch sử oplog không còn không?
5. Có cần transactional outbox khi phải phát business event ổn định không?

### Bài tập 12 — Sự cố production

Quan sát:

```text
tailable_cursor_reconnect_total       tăng rất nhanh
tailable_cursor_completed_total       tăng tương ứng
tailable_cursor_errors_total          gần như không tăng
tailable_events_received_total        = 0
tailable_checkpoint_age_seconds       tăng
```

Nhận định ưu tiên: có thể **initial no-match khiến cursor complete ngay**, rồi `repeat()` không có delay gây hot loop. Hãy kiểm tra query/filter, collection, subscription, test behavior của phiên bản server; bổ sung backoff, giới hạn mở cursor và alert. Nhưng nếu producer chưa từng ghi event vào collection, checkpoint age tăng **không đủ chứng minh mất dữ liệu**.

## 26. Câu hỏi ôn tập nhanh

| Câu hỏi | Trả lời ngắn |
| --- | --- |
| Tailable cursor cần loại collection nào? | Capped collection |
| Không có `onNext` nghĩa là đã lỗi? | Không |
| `onComplete` có được `retryWhen` xử lý? | Không, dùng repeat/reopen policy |
| `onError` có được `repeatWhen` xử lý? | Không trực tiếp |
| Query ban đầu không match có thể gây gì? | Cursor có thể dead/complete |
| Capped rollover làm gì? | Có thể làm mất cursor position và lịch sử cũ |
| Có resume token MongoDB không? | Không, khác change stream |
| `ObjectId` là offset đáng tin cậy? | Không mặc định |
| Checkpoint lúc nào? | Sau durable business processing |
| Vì sao idempotency? | Reconnect/replay có thể xử lý lại |
| `Flux.timeout` có phải heartbeat không? | Không |
| `dispose()` có cần reconnect không? | Không khi shutdown có chủ đích |
| `@Tailable` dùng với repository nào? | ReactiveMongoRepository trong ví dụ |
| API template nào để tail reactive? | `ReactiveMongoTemplate.tail(Query, Class<T>)` |
| Không được thêm sort theo timestamp vì sao? | Tailable yêu cầu natural order |
| Khi nào cần snapshot/reconcile? | Khi checkpoint không còn trong retained data/gap |
| Vì sao tăng capped size chưa chắc đủ? | Tải/retention có thể tăng và dữ liệu cũ đã mất |
| Khi nào change stream phù hợp hơn? | Theo dõi update/delete và cần event envelope/resume token |

## 27. Tài liệu tham khảo

- Spring Data MongoDB — [Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html): capped collections, imperative container, reactive template và repository `@Tailable`.
- Spring Data MongoDB API — [ReactiveMongoTemplate](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): `tail(Query, Class<T>)` và các overload.
- Spring Data MongoDB API — [Tailable](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Tailable.html): repository annotation tailable.
- Spring Data MongoDB API — [TailableCursorRequest](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/messaging/TailableCursorRequest.html): request và listener container imperative.
- Spring Data MongoDB API — [DefaultMessageListenerContainer](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/messaging/DefaultMessageListenerContainer.html): quản lý subscriptions/tasks và lifecycle.
- MongoDB Manual — [Tailable Cursors](https://www.mongodb.com/docs/manual/core/tailable-cursors/): capped cursor semantics, restrictions và lưu ý liveness.
- MongoDB Manual — [Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/): kích thước cố định, thứ tự tự nhiên và rollover.
- MongoDB Manual — [getMore Command](https://www.mongodb.com/docs/manual/reference/command/getMore/): `maxTimeMS` và await semantics của tailable cursors.
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changestreams/): so sánh event envelope và resume token.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscribe, complete/error/cancel, `retryWhen`, `repeatWhen`, `concatMap` và backpressure.

## Ghi nhớ

**Không có document mới không có nghĩa cursor đã chết; cursor complete, cursor error và cancellation là ba tình huống khác nhau cần xử lý theo chính sách riêng.** Tailable cursor chỉ dùng đúng cách với capped collection và thứ tự tự nhiên; query ban đầu không có kết quả có thể làm cursor không hợp lệ, còn capped rollover có thể khiến vị trí đọc bị mất. Trong Reactor, `retryWhen` dùng cho lỗi tạm thời, `repeatWhen` dùng cho completion, cả hai cần backoff/giới hạn và phải tôn trọng shutdown chủ động. **Kết nối lại không đồng nghĩa phục hồi không mất dữ liệu**: tailable cursor không có resume token, nên checkpoint/idempotency/gap detection phải do ứng dụng thiết kế, với nguồn replay bền vững nếu SLA không cho phép mất event. Kiểm thử trên capped collection thật, phân biệt idle/complete/error, quan sát retention và checkpoint, và dùng change stream hoặc outbox khi yêu cầu vượt giới hạn của tailable cursor.
