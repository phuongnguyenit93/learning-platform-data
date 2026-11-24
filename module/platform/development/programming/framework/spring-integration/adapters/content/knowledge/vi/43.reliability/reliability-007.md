# MetadataStoreSelector

**Chương:** Reliability  
**Bài học:** MetadataStoreSelector  
**Module:** Spring Integration Adapters  
**Ngôn ngữ:** Tiếng Việt  
**Bối cảnh:** Kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành với File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, chú trọng contract của message, idempotency, lỗi, transaction và vòng đời kết nối.

> **Trọng tâm:** `MetadataStoreSelector` là một thành phần nhỏ nhưng quan trọng của Spring Integration để quyết định **message nào được chấp nhận dựa trên key/value trong metadata store**. Hiểu rõ thời điểm lưu key, ngữ nghĩa `putIfAbsent`/`replace`, lựa chọn key/value, và ranh giới giữa **“đã được chọn”** với **“nghiệp vụ đã hoàn tất”** là điều kiện để không làm mất message khi xảy ra lỗi.

## 1. Bài toán thực tế

Một hệ thống Spring Integration nhận message từ nhiều nguồn. Hệ thống ngoài có thể gửi trùng, poller có thể đọc lại sau restart, listener có thể nhận redelivery sau rollback và người vận hành có thể replay message từ dead-letter queue (DLQ).

Ví dụ, file `orders-2026-11-23.csv` được SFTP inbound adapter tải về. File splitter phát message cho từng dòng; một số dòng đã xử lý xong trước khi ứng dụng khởi động lại. Sau restart, hệ thống cần biết **dòng nào đã được chấp nhận trước đó** để tránh vô tình thực hiện lại toàn bộ tác vụ.

Một ví dụ khác: HTTP inbound gateway nhận `CREATE_ORDER` có `tenantId=T42` và `orderId=ORD-971`. Client bị timeout nên gửi lại cùng thao tác. Nếu xử lý hai lần, downstream có thể tạo hai đơn. Một bộ chọn message theo **business operation key** giúp nhận diện lần xuất hiện sau.

Nhưng bộ chọn theo key chỉ là **một lớp giảm lặp**, không phải toàn bộ giao dịch end-to-end:

- Nếu key được ghi trước khi ghi DB và tiến trình bị crash, lần sau có thể bị từ chối dù đơn chưa tạo.
- Nếu hai instance dùng hai store riêng, cả hai có thể chấp nhận cùng key.
- Nếu khóa chỉ dựa trên file name, hai file khác nhau nhưng cùng tên có thể bị coi là trùng.
- Nếu kết quả API ngoài đã commit nhưng response mất, retry không có idempotency ở downstream vẫn có thể tạo side effect lặp.

**Mục tiêu:** Dùng `MetadataStoreSelector` đúng vai trò, kết hợp đúng store, đúng key/value strategy và đúng error/ack semantics theo từng adapter.

### 1.1. Sau bài này bạn sẽ làm được gì?

1. Giải thích `MetadataStoreSelector` so với `MessageSelector`, `IdempotentReceiverInterceptor` và persistent file filter.
2. Hiểu `accept(Message<?>)`, `keyStrategy`, `valueStrategy`, `compareValues`, `ConcurrentMetadataStore`.
3. Viết và kiểm thử selector theo **first-seen key**, **version tăng dần** hoặc **sequence number** khi thứ tự xử lý được bảo đảm.
4. Chọn store trong bộ nhớ, JDBC, Redis hoặc các persistent store khác theo nhu cầu scale-out/durability.
5. Gắn selector vào inbound processing flow mà không vô tình biến lỗi business thành duplicate được bỏ qua.
6. Thiết kế recovery, replay, idempotency, acknowledgment và transaction cho File/SFTP, HTTP, JMS, AMQP, Kafka và JDBC.
7. Theo dõi hoạt động, phát hiện stale key, collision, crash window và lỗi metadata store.

## 2. Đặt MetadataStoreSelector vào đúng kiến trúc

Trong Spring Integration, một inbound adapter/gateway tạo `Message<?> ` và gửi tới `MessageChannel`. Consumer/handler nhận message và thực hiện logic. Một `MessageSelector` trả về `boolean`:

- `true`: Message được **chấp nhận** theo điều kiện của selector.
- `false`: Message **bị từ chối** theo điều kiện của selector.

`MetadataStoreSelector` là implementation của `MessageSelector` sử dụng metadata store để nhớ trạng thái key/value giữa các message.

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / JDBC"] --> IN["Inbound adapter / gateway / poller"]
    IN --> CH["MessageChannel"]
    CH --> SEL["MetadataStoreSelector"]
    SEL --> STORE["ConcurrentMetadataStore"]
    STORE --> SEL
    SEL -->|accept = true| H["Business handler"]
    SEL -->|accept = false| REJ["Duplicate route / marker / rejection"]
    H --> OUT["DB / external API / outbound adapter"]
    H -.-> LOG["Business outcome + audit"]
    REJ -.-> LOG
~~~

**Quan trọng:** `MetadataStoreSelector` chỉ cung cấp quyết định `accept`. Nó **không tự là inbound adapter**, **không tự đọc file**, **không tự tạo DLQ**, **không tự quyết định broker ack/offset** và **không tự đánh dấu một tác vụ nghiệp vụ là hoàn tất**.

### 2.1. Những component thường phối hợp

| Thành phần | Vai trò |
| --- | --- |
| `MetadataStoreSelector` | Tạo key/value và quyết định chấp nhận message |
| `MessageProcessor<String>` | Chiến lược lấy key hoặc value từ message |
| `ConcurrentMetadataStore` | Kho key/value có thao tác cập nhật atomic theo contract |
| `IdempotentReceiverInterceptor` | Advice bọc `MessageHandler`, sử dụng selector để gắn marker hoặc từ chối message |
| `MessageFilter` | Endpoint filter dùng `MessageSelector` để chuyển tiếp hoặc loại message |
| `MessageChannel` | Đường truyền tới handler hoặc duplicate/error flow |
| Accept-once file filter | Ngăn nhận/tải lặp file theo tiêu chí file-level |
| Transactional inbox | Theo dõi trạng thái **PROCESSING/COMPLETED/FAILED**, có thể gắn transaction nghiệp vụ |
| Broker offset/ack | Quản lý delivery phía JMS/AMQP/Kafka, độc lập với selector |

## 3. Hợp đồng API của MetadataStoreSelector

`MetadataStoreSelector` thuộc package:

~~~java
import org.springframework.integration.selector.MetadataStoreSelector;
~~~

Nó triển khai `MessageSelector` và sử dụng `MessageProcessor<String>` cùng `ConcurrentMetadataStore`. Các constructor thông dụng:

~~~java
new MetadataStoreSelector(keyStrategy);
new MetadataStoreSelector(keyStrategy, valueStrategy);
new MetadataStoreSelector(keyStrategy, concurrentMetadataStore);
new MetadataStoreSelector(keyStrategy, valueStrategy, concurrentMetadataStore);
~~~

Mỗi `keyStrategy`/`valueStrategy` là một **MessageProcessor** nhận `Message<?>` và trả về `String` dùng làm key hoặc value. Có thể dùng Java lambda khi kiểu được suy luận phù hợp.

### 3.1. `accept(Message<?>)` thực sự làm gì?

Với logic thông thường, selector:

1. Đọc message, tính **key** bằng `keyStrategy`.
2. Tính **value** bằng `valueStrategy`, hoặc dùng **timestamp header** theo mặc định.
3. Thực hiện `ConcurrentMetadataStore.putIfAbsent(key, value)`.
4. Nếu key **chưa có**, operation lưu value và selector trả `true`.
5. Nếu key **đã có**, selector trả `false`, trừ khi cấu hình `compareValues` cho phép một version/value mới và kho cập nhật được theo điều kiện atomic.

~~~mermaid
flowchart TD
    M["Message"] --> K["keyStrategy(message)"]
    K --> V["valueStrategy(message) hoặc timestamp header"]
    V --> PUT["ConcurrentMetadataStore.putIfAbsent(key, value)"]
    PUT --> HAS{"Key đã tồn tại?"}
    HAS -->|Chưa| A["Lưu key/value -> accept=true"]
    HAS -->|Có, không compareValues| R["accept=false"]
    HAS -->|Có, có compareValues| C{"compareValues(old,new)?"}
    C -->|Không| R
    C -->|Có| CAS["replace(key,old,new) atomic"]
    CAS -->|Thành công| A
    CAS -->|Không thành công| RETRY["Đánh giá lại theo ngữ nghĩa store/selector"]
~~~

Đây là **sơ đồ khái niệm**, không mô phỏng mọi chi tiết vòng lặp cạnh tranh bên trong implementation. Điểm chính là **khả năng chấp nhận key mới hoặc thay value phải dựa trên thao tác atomic**, không dựa trên `get` rồi `put` rời rạc.

### 3.2. Giá trị mặc định không phải trạng thái nghiệp vụ

Khi không cung cấp `valueStrategy`, selector sử dụng **timestamp message header** làm metadata value (tài liệu Javadoc mô tả biểu diễn dạng hex). Timestamp được lưu để có value phù hợp; **nó không phải bằng chứng tác vụ đã commit**, cũng không mặc nhiên là expiration hay checkpoint có ý nghĩa nghiệp vụ.

Nếu muốn lưu **sequence number**, **version**, **watermark** hoặc một value có ý nghĩa khác, hãy cung cấp `valueStrategy` rõ ràng và kiểm thử logic so sánh. Không nên cho rằng timestamp là thứ tự nghiệp vụ.

### 3.3. Bốn câu hỏi không thể bỏ qua

| Câu hỏi | Nếu không trả lời rõ |
| --- | --- |
| Key mô tả **điều gì**? | Dễ drop nhầm message hợp lệ hoặc nhận message trùng |
| Value mang **ngữ nghĩa gì**? | Có thể overwrite checkpoint sai khi dùng `compareValues` |
| Store có **atomic/durable** không? | Hai instance cùng chấp nhận; restart quên trạng thái |
| `accept=true` đại diện **đã nhận** hay **đã hoàn tất**? | Có thể mất nghiệp vụ khi crash hoặc retry |

## 4. ConcurrentMetadataStore là nền tảng của quyết định

`ConcurrentMetadataStore` mở rộng `MetadataStore` bằng hai thao tác quan trọng:

~~~java
String oldValue = store.putIfAbsent(key, value);
boolean changed = store.replace(key, expectedOldValue, newValue);
~~~

- `putIfAbsent` **trả `null` khi ghi thành công**, hoặc trả value đã tồn tại nếu key đã có.
- `replace` chỉ thay value khi value hiện tại bằng `expectedOldValue`; kết quả `true` nghĩa là thay thành công.

Những thao tác này là **atomic trong phạm vi contract backend**. Chúng giúp chống race condition giữa nhiều message cùng key.

### 4.1. Vì sao không dùng get rồi put?

~~~text
Instance A: get(K) -> null
Instance B: get(K) -> null
Instance A: put(K, A)
Instance B: put(K, B)
Kết quả: cả A và B tin rằng mình nhận quyền xử lý K.
~~~

Với `putIfAbsent` atomic:

~~~text
Instance A: putIfAbsent(K, A) -> null      -> được chấp nhận
Instance B: putIfAbsent(K, B) -> "A"      -> bị từ chối
~~~

**Lưu ý về scale-out:** `SimpleMetadataStore` có thể hỗ trợ atomic trong cùng một instance, nhưng **mỗi JVM sở hữu một store riêng** thì không có phối hợp phân tán. Cần shared store thực sự khi nhiều pods/instances có thể thấy cùng operation.

### 4.2. Cần đánh giá tính đúng đắn của backend

Đối với một `JdbcMetadataStore`, Redis, MongoDB, Zookeeper hoặc backend khác được hỗ trợ, hãy kiểm tra:

1. `putIfAbsent` và `replace` có thực sự atomic trên topology đang dùng không?
2. Có mất key sau restart, eviction, failover hoặc rollback transaction không?
3. Có contention hoặc latency bất thường khi nhiều consumer tranh một key không?
4. Có namespace/region/prefix để nhiều flow không đụng key nhau không?
5. Có hạn chế riêng của backend không, ví dụ `replace` trong một số cấu hình Redis Cluster?
6. Có chính sách lưu, xóa và bảo vệ key phù hợp dữ liệu nghiệp vụ không?

**Chỉ nhìn tên implementation không đủ:** Cần kiểm thử các đặc tính durability/atomicity trong môi trường triển khai thật.

## 5. Key strategy: chọn đúng định danh trùng

Một `keyStrategy` tốt phải dựa vào **business contract** hoặc **checkpoint contract** cụ thể, không chỉ dựa vào message object.

### 5.1. Ví dụ key phổ biến

| Luồng | Key gợi ý | Điểm phải kiểm tra |
| --- | --- | --- |
| HTTP tạo đơn | tenant + operation + order ID/version | Client giữ key khi retry, body fingerprint không đổi |
| SFTP file-level | remote source + path + file generation | Cùng tên file được sửa có được coi là version mới? |
| File splitter per-line | file generation + line/record ID | Reorder hoặc chèn dòng có làm đổi ý nghĩa line number? |
| JMS/AMQP event | tenant + business event ID | Republish có giữ event ID không? |
| Kafka record transport | topic + partition + offset | Chỉ chống đọc lại cùng record, không chống republish cùng event |
| Kafka business event | producer event ID/operation ID | Có ổn định qua resend, backfill không? |
| JDBC poller | business row ID + action/version | Một hàng mới cho cùng operation có bị trùng không? |
| Workload pipeline | workflow run + operation/target | Retry cùng job có giữ định danh thao tác không? |

**`MessageHeaders.ID` thường không phù hợp làm business idempotency key**, vì mỗi delivery hoặc transform có thể tạo message ID mới. `MessageHeaders.TIMESTAMP` cũng không phải ID nghiệp vụ.

### 5.2. Key phải đủ namespace

~~~text
Kém:
    order-971

Tốt hơn:
    order:create:v1:tenant-T42:order-971

Khác operation:
    order:cancel:v1:tenant-T42:order-971
~~~

Nếu dùng chung metadata store cho nhiều flow, key `order-971` có thể gây xung đột giữa `CREATE_ORDER` và `CANCEL_ORDER`. Prefix có ý nghĩa nghiệp vụ giúp tránh collision.

### 5.3. Key thiếu hoặc không hợp lệ

Khi message không có tenant ID hoặc operation ID:

- **Không** dùng key rỗng hoặc `"UNKNOWN"` cho tất cả message.
- Chuyển sang validation/quarantine với lý do rõ ràng.
- Hoặc dùng fallback **được hợp đồng nghiệp vụ cho phép** và có test.

Một key không hợp lệ có thể gây **data loss** nghiêm trọng hơn một exception rõ ràng, vì những message hợp lệ sau đó bị selector coi là duplicate.

### 5.4. Hash và bảo vệ dữ liệu

Nếu key chứa email, số định danh cá nhân hoặc dữ liệu nhạy cảm, nên cân nhắc **hash có namespace hoặc reference được bảo vệ**, không đưa nguyên PII vào metadata store, metric labels hoặc log. Phải giữ tính ổn định của key qua restart, migration và replay; thay đổi thuật toán băm hoặc salt cần có kế hoạch tương thích.

## 6. Value strategy: ý nghĩa của giá trị lưu

**Key** xác định nhóm message cần theo dõi; **value** quyết định thông tin lưu cho key.

Không phải mọi trường hợp cần value phức tạp. Mẫu **chỉ nhận lần đầu** dùng value mặc định là đủ về mặt selector, nhưng một số kịch bản cần:

- Version hoặc revision của tài liệu.
- Sequence number của bản ghi trong file.
- Watermark xử lý một dòng sự kiện có thứ tự.
- Checksum hoặc ETag của đối tượng nguồn.
- Marker/checkpoint có meaning được quản trị ngoài selector.

### 6.1. Bảng key/value

| Kịch bản | Key | Value | Quy tắc accept |
| --- | --- | --- | --- |
| Chỉ nhận thao tác lần đầu | business operation ID | Timestamp/default | Chấp nhận nếu key chưa tồn tại |
| Version cập nhật tăng dần | entity ID | version number | Chấp nhận nếu key mới hoặc new version đủ điều kiện |
| File split theo sequence | file generation | sequence number | Chấp nhận tăng dần nếu thứ tự bảo đảm |
| Phát hiện file thay đổi | file identity/path | file version/checksum | Chấp nhận khi phiên bản thật sự thay đổi |
| Poller checkpoint | source stream ID | event watermark | Chỉ tăng watermark khi an toàn với ordering/commit |

**Không nên dùng value để lưu raw payload, access token hoặc secret.** Metadata store là nơi lưu dấu kỹ thuật, không phải kho dữ liệu nghiệp vụ có bảo mật đầy đủ.

### 6.2. Khi cần lưu kết quả nghiệp vụ

`MetadataStoreSelector` không được thiết kế để thay thế **result cache, inbox record hoặc audit store**. Khi cần trả lại HTTP response của request đã hoàn tất, hãy lưu `COMPLETED` và result reference ở kho nghiệp vụ riêng với transaction/unique key phù hợp.

Một timestamp `seen` không cho biết callback HTTP đã thành công, Kafka offset đã commit hay thao tác ngân hàng đã được xác nhận.

## 7. compareValues: chấp nhận value mới theo điều kiện

Từ **Spring Integration 5.3**, `MetadataStoreSelector` hỗ trợ cấu hình **`compareValues`** với `BiPredicate<String,String>`.

- Tham số thứ nhất: **old value** đang lưu trong metadata store.
- Tham số thứ hai: **new value** được tính từ message hiện tại.
- Nếu predicate trả `true`, selector cố cập nhật value cũ thành mới theo `replace` atomic.
- Nếu predicate trả `false`, message bị từ chối vì không thỏa điều kiện update.

~~~java
selector.setCompareValues((oldValue, newValue) ->
        Integer.parseInt(newValue) > Integer.parseInt(oldValue));
~~~

Đây là ví dụ **chỉ nhận version tăng**. Kiểm tra kiểu, range và cách mã hóa value phải được thực hiện, không mặc định mọi string đều parse thành integer hợp lệ.

### 7.1. Những sai lầm về compareValues

| Sai lầm | Hậu quả |
| --- | --- |
| Đảo vị trí `old/new` | Chấp nhận version cũ, từ chối version mới |
| So sánh string theo từ điển | `"10"` có thể được xem nhỏ hơn `"9"` |
| So sánh timestamp delivery như version business | Message đến sau bị xem là “mới” dù là duplicate |
| Không xử lý null/format không hợp lệ | Exception vào error path không kiểm soát |
| Dùng một high-watermark cho event đến lệch thứ tự | Bỏ mất event chưa xử lý nhưng có số nhỏ hơn |
| Cho phép overwrite marker dù xử lý chưa commit | Restart bỏ qua một số operation chưa hoàn tất |
| Dùng key file path mà không có generation/version | File mới cùng tên bị loại sai |

### 7.2. High-watermark chỉ đúng khi có bảo đảm ordering

Ví dụ file có các dòng 1, 2, 3 và selector lưu **max sequence**:

~~~text
Old checkpoint: 1
Nhận dòng 3 -> compareValues(1,3) = true -> lưu 3
Nhận dòng 2 -> compareValues(3,2) = false -> bỏ dòng 2
~~~

Nếu dòng 2 **chưa từng được xử lý**, cách dùng high-watermark này gây mất dữ liệu. Vì vậy:

- Chỉ dùng monotonic watermark khi processing **đúng thứ tự** và checkpoint được cập nhật theo kết quả đã commit.
- Với xử lý song song/out-of-order, dùng **per-event/per-line key** hoặc một cấu trúc tracking các khoảng/lỗ hổng sequence.
- Một boolean predicate so sánh hai value **không tự tạo cam kết xử lý liên tục (contiguous commit)**.

### 7.3. compareValues không phải compare-and-set nghiệp vụ

`ConcurrentMetadataStore.replace` giúp tránh ghi đè value khi bản ghi store đã thay đổi ngoài dự kiến. Nhưng việc chấp nhận message **không đồng nghĩa side effect nghiệp vụ đã được commit atomically cùng value**. Cần phối hợp transaction/inbox hoặc reconciliation để xử lý cửa sổ lỗi.

## 8. Ví dụ Java thuần: selector first-seen

Ví dụ sau minh họa API theo các phiên bản Spring Integration có `MetadataStoreSelector`, `SimpleMetadataStore` và `MessageBuilder`.

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class FirstSeenDemo {
    public static void main(String[] args) {
        ConcurrentMetadataStore store = new SimpleMetadataStore();

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> {
                    String tenant = message.getHeaders().get("tenantId", String.class);
                    String operationId =
                            message.getHeaders().get("operationId", String.class);
                    if (tenant == null || operationId == null) {
                        throw new IllegalArgumentException("Missing stable business key");
                    }
                    return "order:create:" + tenant + ":" + operationId;
                },
                store
        );

        Message<String> first = MessageBuilder.withPayload("create-order")
                .setHeader("tenantId", "T42")
                .setHeader("operationId", "ORD-971")
                .build();

        Message<String> redelivery = MessageBuilder.withPayload("create-order")
                .setHeader("tenantId", "T42")
                .setHeader("operationId", "ORD-971")
                .build();

        System.out.println(selector.accept(first));      // true
        System.out.println(selector.accept(redelivery)); // false
    }
}
~~~

**Ý nghĩa:** Hai message có Spring message IDs khác nhau vẫn tạo cùng business key. Lần đầu chấp nhận và lưu key; lần sau bị từ chối. Ví dụ chạy trong **một JVM**, không xử lý transaction hoặc restart durability.

### 8.1. Không dùng SimpleMetadataStore làm bằng chứng production

Sau restart, một `SimpleMetadataStore` mới không chứa key trước đó và `selector.accept(redelivery)` có thể trả `true`. Trong nhiều instance, mỗi JVM riêng cũng có thể cùng trả `true`.

Muốn chống lặp trên cluster/restart, phải chọn **persistent shared ConcurrentMetadataStore** hoặc thiết kế **transactional inbox** phù hợp hơn với business correctness.

## 9. Ví dụ Java: valueStrategy và compareValues

Một use case dễ hiểu là xử lý **revision mới nhất** cho tài liệu ở nguồn có các revision được đánh số và bảo đảm nghiệp vụ chấp nhận version tăng.

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class RevisionDemo {
    public static void main(String[] args) {
        ConcurrentMetadataStore store = new SimpleMetadataStore();

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> "doc:" + require(message, "documentId"),
                message -> require(message, "revision"),
                store
        );

        selector.setCompareValues((oldValue, newValue) ->
                Long.parseLong(newValue) > Long.parseLong(oldValue));

        Message<String> rev1 = msg("A-42", "1");
        Message<String> rev1Again = msg("A-42", "1");
        Message<String> rev2 = msg("A-42", "2");
        Message<String> stale = msg("A-42", "1");

        System.out.println(selector.accept(rev1));       // true
        System.out.println(selector.accept(rev1Again));  // false
        System.out.println(selector.accept(rev2));       // true
        System.out.println(selector.accept(stale));      // false
    }

    static String require(Message<?> message, String header) {
        String value = message.getHeaders().get(header, String.class);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing header: " + header);
        }
        return value;
    }

    static Message<String> msg(String documentId, String revision) {
        return MessageBuilder.withPayload("document-data")
                .setHeader("documentId", documentId)
                .setHeader("revision", revision)
                .build();
    }
}
~~~

### 9.1. Điều kiện để dùng ví dụ đúng

Selector theo revision là lựa chọn hợp lý khi **chỉ revision lớn nhất** có ý nghĩa cần xử lý. Nếu nghiệp vụ yêu cầu thực thi **mọi revision theo đúng thứ tự**, việc nhận revision 4 trước revision 3 rồi bỏ revision 3 là **sai**.

Do đó trước khi dùng `compareValues`, hãy xác định:

1. Event là **snapshot mới nhất** hay **delta tuần tự**?
2. Các revision có thể đến out-of-order không?
3. Có cần xử lý đủ mọi revision không?
4. Update metadata value có cùng transaction với business effect không?
5. Có cần kiểm chứng external outcome trước khi nâng watermark không?

## 10. Gắn MetadataStoreSelector với IdempotentReceiverInterceptor

`MetadataStoreSelector` chỉ ra quyết định. `IdempotentReceiverInterceptor` là **AOP Advice** áp vào `MessageHandler.handleMessage()` tại endpoint được cấu hình.

Khi selector từ chối message:

- Nếu **không có** `discardChannel` và không bật ném exception khi từ chối, `IdempotentReceiverInterceptor` có thể **chuyển message tới handler với header `duplicateMessage=true`** để handler quyết định.
- Nếu cấu hình **discard channel** hoặc `throwExceptionOnRejection`, message bị từ chối **không được gửi vào target handler** theo hành vi cấu hình.

Điều này khác với suy nghĩ “selector trả false thì message bị loại bỏ ở mọi trường hợp”. Phải test đường thực thi thật.

### 10.1. Ví dụ gắn advice trong Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.MessageChannel;

@Configuration
public class IdempotentEndpointConfiguration {

    @Bean
    public MetadataStoreSelector orderMetadataSelector(
            ConcurrentMetadataStore sharedMetadataStore) {
        return new MetadataStoreSelector(
                message -> "orders:v1:"
                        + message.getHeaders().get("tenantId")
                        + ":"
                        + message.getHeaders().get("operationId"),
                sharedMetadataStore
        );
    }

    @Bean
    public IdempotentReceiverInterceptor orderIdempotentAdvice(
            MetadataStoreSelector orderMetadataSelector,
            MessageChannel duplicateOrdersChannel) {

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(orderMetadataSelector);
        advice.setDiscardChannel(duplicateOrdersChannel);
        return advice;
    }

    @Bean
    public IntegrationFlow orderProcessingFlow(
            OrderProcessor orderProcessor,
            IdempotentReceiverInterceptor orderIdempotentAdvice) {
        return IntegrationFlow.from("ordersInputChannel")
                .handle(orderProcessor, "process",
                        endpoint -> endpoint.advice(orderIdempotentAdvice))
                .get();
    }
}
~~~

**Điều kiện để dùng mã mẫu:**

- `OrderProcessor` do ứng dụng định nghĩa.
- `ordersInputChannel` và `duplicateOrdersChannel` phải được khai báo và có subscriber đúng.
- `sharedMetadataStore` phải là bean store phù hợp với phạm vi durability/concurrency. Không dùng `SimpleMetadataStore` trong production đa instance nếu cần state chia sẻ.
- Các headers `tenantId`/`operationId` được tạo bởi bước nhận/chuẩn hóa message và đã qua validation.
- API builder/overload cần kiểm tra theo Spring Integration version cụ thể của dự án.

**Nguy cơ lỗi:** Nếu metadata key đã được lưu mà `OrderProcessor.process` thất bại, message sau đó có thể bị từ chối. Bọc handler bằng advice **chưa giải quyết** cửa sổ lỗi giữa store và business commit.

### 10.2. Khi cần xử lý duplicate bằng business response

Với HTTP inbound gateway, việc gửi duplicate sang `duplicateOrdersChannel` kiểu one-way có thể **không trả reply cho caller**. Client nhận timeout hoặc behavior không đúng contract.

Nếu API yêu cầu idempotent HTTP response, hãy thiết kế endpoint **đọc result cache/inbox để trả cùng kết quả** hoặc trả trạng thái `PENDING`/`CONFLICT`. Không sử dụng discard-only handler thay cho hợp đồng request-reply mà không có test.

### 10.3. Dùng MessageFilter khi phù hợp

`MetadataStoreSelector` cũng có thể được truyền cho một `MessageFilter`. Khi đó filter quyết định đường **accept/reject** trước handler tiếp theo, không phải advice bao handler.

So sánh:

| Tiêu chí | `MessageFilter` | `IdempotentReceiverInterceptor` |
| --- | --- | --- |
| Vị trí | Endpoint filter rõ trong flow | Advice gắn với handler |
| Logic selector | Có thể dùng `MetadataStoreSelector` | Có thể dùng `MetadataStoreSelector` |
| Duplicate | Lộ rõ discard/reject route | Có thể gắn header hoặc discard tùy cấu hình |
| Áp dụng | Phù hợp lọc message trước handler | Phù hợp pattern idempotent receiver tại endpoint |
| Điều không bảo đảm | Transaction hoặc durability của business | Transaction hoặc durability của business |

## 11. MetadataStoreSelector và File/SFTP inbound adapter

File và SFTP adapters thường có **file discovery/download filters** như accept-once hoặc persistent accept-once. Chúng trả lời:

> File nguồn này có cần được nhận hoặc tải lại trong lần poll hiện tại không?

`MetadataStoreSelector` ở downstream trả lời câu hỏi khác:

> Message/record được sinh từ file này có key/value đã được xử lý hoặc chọn trước đó chưa?

### 11.1. File-level filter khác record-level selector

~~~text
SFTP /orders/import-2026-11-23.csv
  Dòng 1: ORD-971 -> business COMPLETED
  Dòng 2: ORD-972 -> handler FAILED
  Dòng 3: ORD-973 -> business COMPLETED

File filter: tệp đã nhận/tải?
Record selector: từng operation có key/value gì?
Inbox: từng operation có outcome nghiệp vụ nào?
~~~

Nếu file filter đã đánh dấu file nhưng dòng 2 chưa xử lý, không thể coi cả file đã hoàn tất. Cần state/recovery ở cấp record và kế hoạch tái đọc file khi phù hợp.

### 11.2. Cấu hình MetadataStoreSelector cho FileSplitter

FileSplitter có thể phát **sequenceNumber** header theo cấu hình. Một ví dụ dùng **file identity làm key**, **sequence number làm value** và `compareValues` để chấp nhận số tăng dần.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;

// Chỉ đúng khi các line được xử lý theo thứ tự và checkpoint an toàn.
MetadataStoreSelector selector = new MetadataStoreSelector(
        message -> message.getHeaders()
                .get(FileHeaders.ORIGINAL_FILE, java.io.File.class)
                .getAbsolutePath(),
        message -> String.valueOf(message.getHeaders()
                .get(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER)),
        sharedStore
);
selector.setCompareValues((oldValue, newValue) ->
        Integer.parseInt(oldValue) < Integer.parseInt(newValue));
~~~

`sharedStore` trong ví dụ là một `ConcurrentMetadataStore` đã được ứng dụng cấu hình. Logic trên bám theo pattern được tài liệu Spring Integration mô tả, nhưng **không tự bảo đảm không mất dòng sau crash**.

### 11.3. Hai nguy cơ của high-watermark file

**Nguy cơ A — xử lý out-of-order:**

~~~text
File F có line 1, 2, 3.
Line 3 được chọn trước line 2.
Store high-watermark = 3.
Line 2 đến sau -> bị loại dù chưa business-commit.
~~~

**Nguy cơ B — selector đánh dấu trước commit:**

~~~text
Line 2 được accept, store = 2.
Business handler lỗi trước khi lưu kết quả.
Ứng dụng restart rồi đọc lại line 2.
Selector thấy old = 2, new = 2 -> reject.
~~~

Muốn bảo đảm xử lý từng dòng, nên cân nhắc **per-line operation key + transactional inbox** hoặc checkpoint tiến dần **sau khi** có bằng chứng commit và bảo đảm ordering.

### 11.4. File identity phải có generation

Nếu đối tác ghi đè cùng path file trong ngày sau, key chỉ bằng absolute path sẽ dùng chung checkpoint với file trước. Cần contract xác định **file immutable**, **version/ETag/checksum**, upload-complete marker, retention và có được phép reprocess hay không.

## 12. SFTP streaming và vòng đời session

SFTP streaming inbound adapter có thể mang theo session/resource cần được đóng đúng lúc; FileSplitter hoặc downstream flow có thể liên quan tới việc giải phóng session sau khi tiêu thụ stream.

Khi đặt selector:

- Không biến một duplicate rejection thành lý do bỏ qua thao tác đóng tài nguyên.
- Đảm bảo error/recovery path vẫn đóng stream/session theo contract của adapter và splitter.
- Nếu chỉ một phần bản ghi được xử lý, xác định remote file có thể được replay bằng cách nào.
- Persistent file filter hoặc metadata store cần được thiết kế đồng bộ với local staging/checkpoint.
- Tránh giữ SFTP session mở chỉ vì retry downstream quá lâu.

**File đã được tải hoặc stream đã đóng không đồng nghĩa tất cả records đã được commit ở đích.** Tách trạng thái transfer khỏi trạng thái xử lý nghiệp vụ.

## 13. HTTP inbound: selector có đủ cho idempotency response?

Giả sử client gọi:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: create-order-T42-ORD-971

{"tenantId":"T42","orderId":"ORD-971","amount":150000}
~~~

Nếu HTTP gateway thấy key chưa có, hệ thống xử lý lệnh tạo đơn và trả `201` với order reference. Nếu client timeout, lần gửi lại có cùng key nhưng **Spring Message ID và timestamp mới**. Selector dùng business key sẽ phát hiện trùng.

Nhưng **chỉ phát hiện trùng chưa đủ**. Hợp đồng HTTP thường cần:

| Trạng thái cùng key | Response có thể phù hợp |
| --- | --- |
| **COMPLETED**, same fingerprint | Trả kết quả đã lưu theo contract |
| **PROCESSING** | Trả pending/accepted hoặc chờ theo latency budget |
| **FAILED_FINAL** | Trả lỗi nghiệp vụ đã lưu |
| **OUTCOME_UNKNOWN** | Trả trạng thái cần đối soát, không giả thành công |
| Same key, **different payload** | `409 Conflict` hoặc lỗi contract tương đương |

Vì vậy với HTTP gateway cần phản hồi idempotent có giá trị, hãy dùng **business inbox/result store** và cho gateway trả response, thay vì chỉ `discardChannel`.

### 13.1. Điều gì xảy ra nếu selector reject trước gateway reply?

Nếu duplicate đi tới một `DirectChannel` chỉ log, caller có thể không nhận reply như kỳ vọng và timeout. Dù selector hoạt động đúng về mặt Boolean, contract HTTP lại sai.

**Tiêu chí test:** Hai requests cùng key và cùng payload phải nhận response nhất quán; request thứ hai không tạo thêm side effect.

## 14. JMS, AMQP và Kafka: duplicate từ redelivery

`MetadataStoreSelector` có thể đặt gần handler nhận message broker. Tuy nhiên broker/container quản lý **ack/nack, transaction, redelivery, offset commit và DLQ/DLT** theo cơ chế riêng.

| Nguồn | Duplicate xảy ra khi | Phải kiểm tra thêm |
| --- | --- | --- |
| JMS | Session rollback, thiếu acknowledgment, republish | Transacted session, redelivery count, DLQ policy |
| AMQP/RabbitMQ | Nack/requeue, consumer crash, publish lại | Ack mode, DLX, requeue và listener container |
| Kafka | Consumer rebalance, offset chưa commit, republish | Offset/partition, transaction, error handler, DLT |

### 14.1. Transaction boundary

Nếu selector ghi key vào metadata store **ngoài transaction nghiệp vụ**, còn handler lỗi:

~~~text
1) selector.accept(K) = true; store đã có K
2) handler ghi DB thất bại -> rollback business transaction
3) JMS/AMQP/Kafka redeliver K
4) selector.accept(K) = false
5) message có thể bị discard/ack theo adapter configuration
~~~

Hậu quả có thể là **business operation chưa hoàn thành nhưng source message không còn được xử lý lại**.

Biện pháp tùy kiến trúc:

- Dùng store và business transaction có semantics phối hợp được chứng minh.
- Dùng transactional inbox/unique constraint để ghi result và trạng thái trong cùng DB transaction.
- Dùng `PROCESSING/COMPLETED` và logic recovery rõ, không chỉ marker `seen`.
- Khi không biết downstream đã commit, dùng reconciliation trước khi replay.
- Test ack/offset thật bằng broker test environment.

### 14.2. Kafka offset và business event ID

~~~text
Transport identity:
    topic=orders, partition=4, offset=101

Business identity:
    tenant=T42, operation=CREATE_ORDER, orderId=ORD-971
~~~

Nếu cùng event được republish ở offset 205, key `topic+partition+offset` **không** nhận diện được duplicate business. Chọn key theo mục đích: tránh xử lý lại cùng record transport hay tránh lặp cùng operation trên nhiều deliveries/sources.

### 14.3. Lưu ý với broker exactly-once

Một broker hoặc framework có thể hỗ trợ transaction/semantics mạnh trong **phạm vi cụ thể**. Không suy ra nó bảo đảm exactly-once cho side effect tại DB, REST API, SFTP hay dịch vụ ngoài broker. Idempotent Receiver và kiểm soát downstream vẫn có vai trò.

## 15. JDBC inbound: row polling và selector

JDBC inbound adapter có thể poll bản ghi trạng thái `NEW` rồi gửi message. Có hai ID khác nhau:

- **Row ID** trong bảng staging: phân biệt hàng vật lý.
- **Business operation ID:** Phân biệt tác vụ có ý nghĩa nghiệp vụ.

Nếu upstream insert hai hàng khác nhau cho cùng thao tác, selector theo row ID sẽ không thấy duplicate business.

### 15.1. Ví dụ trạng thái hàng

~~~text
NEW -> CLAIMED -> PROCESSING -> COMPLETED
                    |
                    +-> RETRYABLE_FAILURE
                    |
                    +-> NEEDS_RECONCILIATION
~~~

Khi nhiều poller hoạt động, cần row claim với locking/optimistic version/transaction thích hợp; một câu `SELECT ... WHERE processed = false` chưa đủ để chống hai worker cùng lấy hàng.

### 15.2. Vì sao nên dùng unique constraint?

Một local DB side effect có thể nằm chung transaction với inbox marker:

~~~sql
-- Lược đồ minh họa, không phải một JDBC inbound adapter configuration.
CREATE TABLE inbound_inbox (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_key      VARCHAR(240) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    operation_state    VARCHAR(40) NOT NULL,
    result_ref         VARCHAR(240),
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

Unique constraint giúp bảo vệ cạnh tranh ở tầng DB. Nếu message đã `COMPLETED`, lần gửi lại có thể trả cached result; nếu vẫn `PROCESSING`, cần lease/reconciliation.

**MetadataStoreSelector không mặc nhiên quản lý những trạng thái này.** Inbox nghiệp vụ là một thiết kế bổ sung, không chỉ thay type của metadata store.

## 16. Cửa sổ lỗi quan trọng: ghi key trước business commit

Khi dùng `MetadataStoreSelector`, việc key được chấp nhận có thể dẫn đến **ghi key/value vào store trước khi handler nghiệp vụ thực hiện xong**.

~~~mermaid
sequenceDiagram
    participant B as Broker / Adapter
    participant S as MetadataStoreSelector
    participant M as MetadataStore
    participant H as Business handler
    participant D as Database
    B->>S: Message operation=ORD-971
    S->>M: putIfAbsent(K, value)
    M-->>S: null (key mới)
    S->>H: accept=true
    H->>D: Ghi nghiệp vụ
    Note over H,D: Crash/rollback trước commit
    B->>S: Redelivery cùng operation K
    S->>M: putIfAbsent(K, value2)
    M-->>S: oldValue (key đã tồn tại)
    S-->>B: accept=false
~~~

Trong ví dụ này, một metadata key có thể tồn tại trong khi business effect **không tồn tại**. Nếu duplicate bị discard và nguồn ack, message có thể bị mất về mặt nghiệp vụ.

### 16.1. Phân biệt ba trạng thái

| Trạng thái | Có thể suy ra từ `MetadataStoreSelector` đơn giản? | Điều cần có |
| --- | --- | --- |
| **SEEN / CLAIMED** | Có: key đã được lưu | Metadata store |
| **COMPLETED** | **Không** | Bản ghi nghiệp vụ/transaction/result store |
| **OUTCOME_UNKNOWN** | **Không** | Reconciliation sau timeout/crash |

Đây là lý do `MetadataStoreSelector` thích hợp **làm selector/guard cho trường hợp được thiết kế rõ**, nhưng không nên là cơ sở duy nhất để công bố **exactly-once end-to-end**.

### 16.2. Khi nào có thể chấp nhận "mark trước"?

Có những luồng mà semantics này là đủ, ví dụ chỉ cần ngăn gửi lại **thông báo không quan trọng**, không có yêu cầu xử lý bền vững và chấp nhận xác suất bỏ lỡ khi crash. Khi đó phải ghi rõ **delivery guarantee** thực tế, owner và mức chấp nhận mất bản tin.

Với **đơn hàng, thanh toán, chuyển dữ liệu có giá trị hoặc cập nhật trạng thái quan trọng**, nên chọn cơ chế bảo vệ outcome mạnh hơn.

### 16.3. Transactional inbox

Một cách phổ biến khi nghiệp vụ nằm trong cùng database:

1. Bắt đầu transaction.
2. Tạo/claim row với unique business key.
3. Thực hiện thay đổi dữ liệu nghiệp vụ.
4. Ghi `COMPLETED` và result vào inbox.
5. Commit đồng thời nghiệp vụ và trạng thái hoàn tất.

Nếu rollback, không để lại một marker `COMPLETED` sai. Nếu event redeliver sau commit, đọc lại outcome.

**Chú ý:** Nếu side effect là gọi HTTP/SFTP/JMS bên ngoài, local DB transaction **không tự bao trùm** hệ thống đó; cần idempotency ở downstream và/hoặc outbox/reconciliation.

## 17. compareValues không tự là một checkpoint đã commit

Với file split hoặc nguồn có sequence, `compareValues` thường được dùng như một **high-watermark**. Nhưng sự kiện “message N được selector nhận” không đồng nghĩa “mọi message đến N đã xử lý thành công”.

### 17.1. Điều kiện để checkpoint theo sequence đáng tin

1. **Thứ tự được bảo đảm:** Message đến và được xử lý theo sequence mong muốn.
2. **Không có lỗ hổng:** Nếu N được checkpoint thì các message trước N đã hoàn tất hoặc được xử lý theo chính sách.
3. **Checkpoint sau commit:** Value chỉ được nâng sau khi business outcome an toàn, hoặc có cơ chế rollback/checkpoint transaction thực sự.
4. **Không sai generation:** Một file hoặc stream mới không dùng lại key của generation trước.
5. **Recovery rõ:** Có cách xử lý khi process crash giữa checkpoint và ack.

Một `compareValues` chỉ dựa `new > old` **chỉ thỏa điều kiện thứ nhất về mặt số học**, không bảo đảm bốn điều còn lại.

### 17.2. Gap-aware checkpoint

Với event đến không theo thứ tự, có thể cần:

~~~text
Committed contiguous checkpoint = 40
Events completed after 40: {42, 43}
Event 41 chưa completed

Không nâng committed checkpoint lên 43.

Khi 41 completed:
    41, 42, 43 đều đã completed
    -> mới có thể nâng contiguous checkpoint lên 43
~~~

Cấu trúc `completed gaps` và transaction riêng là trách nhiệm của application hoặc hệ thống checkpoint chuyên dụng; **không có sẵn chỉ qua một MetadataStoreSelector với một value string**.

## 18. Sự khác nhau giữa metadata store và message store

Tên gọi gần nhau nhưng chức năng khác:

| Loại store | Nội dung điển hình | Vai trò |
| --- | --- | --- |
| **MetadataStore** | Key/value dạng string | Checkpoint, marker, version, filter state |
| **MessageStore** | Spring Messages/nhóm messages tùy implementation | Lưu message cho queue, aggregator hoặc các pattern liên quan |
| **Business inbox** | Operation ID, payload fingerprint, state, result | Bảo đảm workflow nghiệp vụ và idempotent response |
| **Outbox** | Event hoặc lệnh outbound chờ gửi | Điều phối side effect ra hệ thống khác |
| **DLQ / quarantine** | Failure record hoặc message không xử lý được | Điều tra, sửa dữ liệu, replay |

`ConcurrentMetadataStore` cung cấp thao tác key/value atomic. Nó **không thay thế** full message persistence, retry queue hoặc business result store.

### 18.1. Vì sao không lưu payload vào value?

Value của MetadataStoreSelector được thiết kế phục vụ **lookup/compare**, không thích hợp để:

- Lưu file nhị phân lớn hoặc payload JSON phức tạp.
- Ghi raw access token, cookie, mật khẩu hoặc PII.
- Thay thế lưu trạng thái nghiệp vụ nhiều bước.
- Tạo audit evidence bất biến theo chuẩn kiểm toán.

Nếu cần lưu đầy đủ bản tin thất bại, dùng failure store hoặc broker bền vững có schema/retention/permission rõ.

## 19. Cấu hình store bền vững và an toàn

Spring Integration cung cấp các implementation store hỗ trợ nhiều nhu cầu, như `SimpleMetadataStore`, `PropertiesPersistingMetadataStore`, `JdbcMetadataStore`, `RedisMetadataStore`, `MongoDbMetadataStore`, `ZookeeperMetadataStore` và một số lựa chọn khác theo phiên bản/module.

### 19.1. So sánh ưu và nhược điểm

| Store | Ưu điểm | Giới hạn cần đánh giá |
| --- | --- | --- |
| `SimpleMetadataStore` | Gọn, đơn giản, hữu ích cho unit test | Trong bộ nhớ; mất state khi JVM dừng |
| Properties-backed | Có thể lưu state thành file | Flush/restart/crash và chia sẻ đa instance cần xem kỹ |
| JDBC-backed | Durable, tận dụng DB operation và transaction | Locking, schema, throughput, transaction boundary |
| Redis-backed | Shared, latency thấp theo topology phù hợp | Persistence/eviction/failover và atomic operations theo cấu hình |
| MongoDB-backed | Shared document persistence | Cần kiểm tra write concern và tính atomic theo contract |
| ZooKeeper-backed | State phối hợp phân tán theo kịch bản | Availability/operational overhead và ACL |
| Custom ConcurrentMetadataStore | Có thể tối ưu cho hệ thống riêng | Phải thực hiện chính xác `putIfAbsent`, `replace` và lỗi cạnh tranh |

### 19.2. Redis Cluster có một lưu ý thực thi

Tài liệu Spring Integration Redis có lưu ý rằng `RedisMetadataStore.replace()` gặp hạn chế trong **Redis Cluster** do cơ chế `WATCH` dùng cho atomicity không được hỗ trợ trong cấu hình được mô tả. Vì vậy **không mặc định** mọi Redis deployment đều đáp ứng `compareValues`/CAS giống nhau.

Khi dùng `compareValues` với Redis hoặc backend phân tán, hãy **xác minh chính xác giới hạn phiên bản, topology, thao tác atomic và test cạnh tranh**, không chỉ test `putIfAbsent` ở một instance.

### 19.3. PropertiesPersistingMetadataStore và crash

Một properties-backed store có thể chỉ ghi xuống file khi **ApplicationContext đóng bình thường**, trừ khi được flush theo cơ chế hỗ trợ. Crash hoặc kill -9 có thể làm mất state mới. Đối với ingest quan trọng, không coi file persistence mà chưa test crash là đủ.

### 19.4. Namespace và quyền truy cập

Một shared store có thể chứa keys từ nhiều flows. Cần đặt:

- Prefix per application/flow/environment/tenant.
- Tránh dùng key production với dev nếu hai môi trường chia sẻ backend.
- ACL/database permission giới hạn ai được đọc/sửa/xóa metadata.
- Backup, retention, cleanup và capacity plan.
- Cảnh báo trên thao tác xóa tập keys bất thường.

Việc xóa nhầm metadata store có thể làm **hàng loạt messages cũ được xem là mới**, gây side effects trùng.

## 20. Khi metadata store không khả dụng

Giả sử selector muốn `putIfAbsent(K,V)` nhưng Redis/DB timeout.

Các lựa chọn:

| Phương án | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| **Fail closed**: ném exception/giữ message ở nguồn | Business operation nhạy cảm | Backlog tăng; cần retry và alert |
| **Quarantine**: lưu failure ở kho bền vững khác | Có failure store độc lập và contract cho phép | Phải bảo đảm không ack trước khi persist |
| **Fail open**: bỏ qua idempotency guard | Chỉ khi có kiểm soát downstream đủ mạnh và được phê duyệt | Tăng side effects trùng |
| **Pause ingestion** | Store outage rộng, nguồn có thể buffer | Lag, SLA và recovery runbook |

Với thao tác tạo đơn/ghi dữ liệu nhạy cảm, **fail open tự động** thường là rủi ro lớn. Nếu metadata store chính là lớp idempotency duy nhất thì không nên lặng lẽ chuyển sang xử lý không kiểm tra.

### 20.1. Retry lỗi store khác retry lỗi downstream

Nếu DB metadata store lỗi, retry trong selector có thể giúp khắc phục transient connection. Nhưng retry không giải quyết schema sai, key invalid hoặc permissions bị thiếu.

Tránh:

~~~text
metadata store timeout
 -> retry vô hạn ở selector
 -> consumer thread bị giữ
 -> broker backlog tăng
 -> nguồn tiếp tục redeliver
 -> retry storm
~~~

Nên giới hạn attempts, backoff/jitter theo thư viện sử dụng, circuit breaker khi cần và báo trạng thái **deduplication unavailable** cho vận hành.

## 21. Chọn giữa first-seen selector và compareValues

| Nhu cầu | Khuyến nghị |
| --- | --- |
| Chỉ nhận event với business ID chưa từng thấy | First-seen `putIfAbsent` theo operation key |
| Chỉ quan tâm bản snapshot có version mới hơn | `compareValues(newVersion > oldVersion)` nếu version monotonic và out-of-order có chủ đích |
| Cần xử lý mọi event theo thứ tự | Không dùng đơn giản high-watermark nếu có thể có gap; dùng ordered processing/checkpoint an toàn |
| Cần trả cùng HTTP result khi retry | Business inbox/result store, có thể dùng selector bổ sung |
| Cần chống duplicate xuyên hai nguồn | Key ở tầng nghiệp vụ, shared store hoặc unique constraint |
| Cần không mất operation qua crash | Transactional inbox/outbox + ack/commit đúng |
| Chỉ muốn tránh download file cũ | Persistent file filter ở source layer |
| Cần phát hiện cùng key nhưng body khác | Fingerprint/compare business input riêng, không chỉ timestamp/value mặc định |

**Đừng chọn `compareValues` chỉ vì muốn “cho phép retry”.** Retry một operation chưa hoàn tất cần trạng thái nghiệp vụ và kiểm chứng outcome; tăng một numeric metadata value không phải cách quản lý state machine đầy đủ.

## 22. XML/annotation configuration: các cách gắn selector

Java DSL là một lựa chọn, nhưng hệ thống Spring Integration lâu đời có thể dùng XML namespace, các annotation endpoint hoặc Java config.

### 22.1. Ví dụ XML fragment

~~~xml
<!-- Minh họa các thuộc tính idempotent-receiver; yêu cầu namespace,
     bean name và endpoint thật từ cấu hình ứng dụng. -->
<int:idempotent-receiver
    id="ordersIdempotency"
    endpoint="ordersHandler"
    metadata-store="sharedMetadataStore"
    key-expression="'orders:' + headers['tenantId'] + ':' + headers['operationId']"
    discard-channel="duplicatesChannel"
    throw-exception-on-rejection="false" />
~~~

Cần kiểm tra **namespace schema/attributes** tương ứng phiên bản Spring Integration và sự tồn tại của endpoint có ID `ordersHandler`. Ví dụ này không tự tạo `sharedMetadataStore`, `duplicatesChannel` hoặc business transaction.

### 22.2. Khi có compareValues

~~~xml
<!-- value và compareValues có thể được cấu hình bằng strategy/bean
     theo schema phiên bản đang dùng. -->
<int:idempotent-receiver
    endpoint="revisionHandler"
    metadata-store="sharedMetadataStore"
    key-expression="'doc:' + headers['documentId']"
    value-expression="headers['revision'].toString()"
    compare-values="revisionComparePredicate" />
~~~

Bean `revisionComparePredicate` phải là `BiPredicate<String,String>` theo ngữ nghĩa **old rồi new**. Khi đưa vào production cần đảm bảo kiểu dữ liệu và version semantics đã được kiểm tra.

### 22.3. Annotation endpoint

Spring Integration hỗ trợ `@IdempotentReceiver` gắn tại messaging endpoint theo những kịch bản Java config thích hợp. Annotation tham chiếu interceptor bean; nó **không tự tạo key/value strategy** và **không tự gắn idempotency cho mọi handler**.

Sử dụng XML, Java DSL hoặc annotation nào cũng phải kiểm tra:

1. Advice/filter có thực sự nằm trước side effect cần bảo vệ không?
2. Duplicate được đánh dấu, gửi discard channel hay ném exception?
3. Error/ack semantics có phù hợp với inbound adapter không?
4. Selector state có bền và nhất quán khi restart/scale-out không?

## 23. Kiểm thử selector ở cấp unit

Đầu tiên cần kiểm tra **Boolean decision** và biến đổi metadata value độc lập với adapter/broker.

### 23.1. JUnit 5: accept và reject

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MetadataStoreSelectorTest {

    @Test
    void acceptsOnlyFirstSeenOperationKey() {
        SimpleMetadataStore store = new SimpleMetadataStore();
        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> String.valueOf(
                        message.getHeaders().get("businessOperationId")),
                store);

        var first = MessageBuilder.withPayload("payload-A")
                .setHeader("businessOperationId", "create:T42:971")
                .build();
        var duplicate = MessageBuilder.withPayload("payload-A")
                .setHeader("businessOperationId", "create:T42:971")
                .build();
        var anotherOperation = MessageBuilder.withPayload("payload-B")
                .setHeader("businessOperationId", "create:T42:972")
                .build();

        assertTrue(selector.accept(first));
        assertFalse(selector.accept(duplicate));
        assertTrue(selector.accept(anotherOperation));
    }

    @Test
    void acceptsIncreasingRevisionOnly() {
        SimpleMetadataStore store = new SimpleMetadataStore();
        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> String.valueOf(
                        message.getHeaders().get("documentId")),
                message -> String.valueOf(
                        message.getHeaders().get("revision")),
                store);
        selector.setCompareValues((oldValue, newValue) ->
                Long.parseLong(newValue) > Long.parseLong(oldValue));

        var v1 = MessageBuilder.withPayload("doc")
                .setHeader("documentId", "D-100")
                .setHeader("revision", 1)
                .build();
        var v2 = MessageBuilder.withPayload("doc")
                .setHeader("documentId", "D-100")
                .setHeader("revision", 2)
                .build();

        assertTrue(selector.accept(v1));
        assertFalse(selector.accept(v1));
        assertTrue(selector.accept(v2));
        assertFalse(selector.accept(v1));
        assertEquals("2", store.get("D-100"));
    }
}
~~~

Trong test đầu, `String.valueOf(null)` có thể tạo chuỗi `"null"` nếu header vắng; đó **không phải cách validation production**. Test này cố ý chỉ minh họa API selector. Trong ứng dụng thật, key strategy phải reject missing/invalid headers trước khi gọi store.

### 23.2. Test compareValues với key khác

Đừng chỉ test một key. Cần xác nhận:

- Version của tài liệu A không ảnh hưởng tài liệu B.
- `old=9, new=10` chấp nhận theo so sánh số học.
- `old=10, new=9` bị từ chối.
- `old=10, new=10` bị từ chối.
- Invalid revision không làm hỏng store hoặc ghi value không hợp lệ.
- Các thread gửi cùng revision chỉ có **quyền chấp nhận đúng theo atomic policy**.

### 23.3. Test handler invocation

Boolean selector đúng chưa đủ. Với `IdempotentReceiverInterceptor`, test:

1. First-seen message → business handler được gọi.
2. Duplicate có discard channel → business handler không gọi lần hai.
3. Duplicate không discard → header `duplicateMessage` được xử lý theo hợp đồng.
4. Discard handler lỗi → behavior với upstream và ack được ghi nhận.
5. Handler lỗi sau selector accept → redelivery không bị mất vì marker sai.

## 24. Kiểm thử concurrency và crash recovery

### 24.1. Nhiều threads cùng key

Mục tiêu là chứng minh **atomic `putIfAbsent` thực sự chấp nhận đúng số message** theo contract.

~~~text
Setup:
    20 concurrent tasks
    cùng tenant=T42 và operationId=ORD-971
    cùng shared ConcurrentMetadataStore

Expected for first-seen selector:
    accept=true đúng 1 task
    accept=false 19 tasks

Nhưng:
    business outcome của task được accept vẫn phải được kiểm chứng.
~~~

Đây là kiểm thử atomics **ở selector layer**, không đủ để khẳng định business exactly-once.

### 24.2. Nhiều instances

Khởi chạy hai consumer trên cùng shared store:

- Instance A nhận message K.
- Instance B nhận duplicate K đúng lúc.
- Chỉ một instance được accept theo first-seen semantics.
- Restart cả hai, trạng thái K vẫn tồn tại khi store phải durable.
- Thử failover/eviction theo topology thực tế.

Nếu test chỉ chạy hai threads nhưng vẫn dùng một `SimpleMetadataStore`, nó **không kiểm tra vấn đề store riêng của mỗi JVM**.

### 24.3. Failure injection matrix

| Mốc thất bại | Cần quan sát |
| --- | --- |
| Trước `putIfAbsent` | Không ghi marker; source có thể retry |
| Sau `putIfAbsent`, trước handler | Marker tồn tại nhưng business chưa chạy |
| Sau local DB write, trước commit | Transaction rollback có để lại marker sai không? |
| Sau DB commit, trước broker ack | Redelivery có tránh side effect thứ hai không? |
| Sau gửi HTTP nhưng trước response | Có OUTCOME_UNKNOWN và reconciliation không? |
| Trong lúc `replace` cạnh tranh | Value có bị ghi lùi hoặc ghi sai không? |
| Metadata store unavailable | Có fail-safe hoặc bỏ qua dedupe trái ý không? |
| Restart/kill -9 | Persistence và resume đúng chứ? |
| TTL/key cleanup | Replay cũ có tạo duplicate ngoài dự kiến không? |

**Nên test từng failure point**, vì “happy path chạy được” không chứng minh reliability.

## 25. Kiểm thử adapter và ack/offset

### 25.1. File/SFTP

- File được tải lần đầu và bị lọc ở lần poll tiếp theo theo contract.
- App restart không đọc lại file ngoài ý định nếu metadata store bền.
- Nếu một record trong file lỗi, các record chưa hoàn tất còn khả năng phục hồi.
- File bị ghi đè/cùng path có generation mới không bị nhận diện sai.
- Nếu dùng FileSplitter high-watermark, test line 3 đến trước line 2.
- Verify đóng SFTP stream/session sau success, rejection và error.

### 25.2. HTTP

- Hai requests cùng Idempotency-Key và cùng body nhận response thống nhất.
- Key trùng, body khác trả conflict.
- Request thứ hai đến khi lần đầu đang PROCESSING nhận pending/đợi theo contract.
- Handler failure không bị selector “đóng dấu” thành success.
- Hợp đồng timeout phù hợp khi dùng gateway request-reply.

### 25.3. JMS/AMQP

- Sau business commit nhưng trước ack, broker redeliver không tạo side effect mới.
- Sau business rollback, redelivery vẫn có đường xử lý hợp lệ.
- Duplicate discard/reply không khiến ack sớm khi operation chưa completed.
- DLQ được tạo đúng theo broker policy, không phải do selector tự tạo.

### 25.4. Kafka

- Consumer rebalance sau local commit không tạo duplicate.
- Cùng business event được republish ở offset khác vẫn được phát hiện nếu cần business dedupe.
- Offset commit không vượt quá những message cần xử lý hoặc đã được nhận trách nhiệm bền.
- DLT replay giữ operation key và có audit.

### 25.5. JDBC

- Hai pollers tranh cùng row được claim đúng theo cơ chế transaction.
- Cùng business operation nằm ở hai rows được dedupe nghiệp vụ.
- Rollback không để lại `COMPLETED` sai.
- Outbound HTTP timeout có reconciliation trước khi đánh dấu processed.

## 26. Observability, metrics và audit

### 26.1. Chỉ số nên theo dõi

| Metric ứng dụng gợi ý | Ý nghĩa |
| --- | --- |
| `metadata_selector_accept_total` | Số message được selector chấp nhận |
| `metadata_selector_reject_total` | Số message bị coi duplicate/stale |
| `metadata_selector_compare_accept_total` | Số version/value mới được chấp nhận |
| `metadata_store_operation_error_total` | Lỗi thao tác metadata store |
| `metadata_store_cas_conflict_total` | Tín hiệu tranh chấp khi update state, nếu có instrumentation |
| `metadata_store_latency_seconds` | Độ trễ store, ảnh hưởng throughput/ack |
| `idempotency_conflict_total` | Same key nhưng different business payload |
| `idempotency_in_progress_age` | Tuổi operation chưa hoàn tất |
| `inbound_redelivery_total` | Redelivery thực tế theo adapter |
| `recovery_pending_total` | Message còn trong failure store hoặc cần đối soát |
| `replay_total` | Replay được phê duyệt, thành công/thất bại |

Đây là **tên metrics do ứng dụng đề xuất**, không phải Spring Integration tự tạo toàn bộ. Không đặt message ID/business ID vào label metric nếu tạo cardinality rất cao. Đưa correlation ID vào structured log/tracing với quyền truy cập phù hợp.

### 26.2. Structured log mẫu

~~~json
{
  "event": "metadata_selector.rejected",
  "flow": "sftp-orders-to-jdbc",
  "sourceAdapter": "sftp",
  "operationType": "CREATE_ORDER",
  "operationKeyRef": "sha256-prefix:91ac...",
  "decision": "ALREADY_SEEN",
  "businessOutcome": "UNKNOWN",
  "correlationId": "trace-84021",
  "metadataBackend": "jdbc",
  "observedAt": "2026-11-23T09:00:00Z"
}
~~~

Trong log này, `ALREADY_SEEN` và `businessOutcome=UNKNOWN` **không được đồng nghĩa với business success**. Một dashboard chỉ đếm rejected messages mà không đối chiếu completed outcomes có thể che giấu message bị bỏ sót.

Không log raw access token, mật khẩu SFTP, Authorization headers, private keys hoặc payload nhạy cảm chỉ để phục vụ dedupe analysis.

### 26.3. Cảnh báo quan trọng

- Tỷ lệ reject tăng sau restart hoặc deployment.
- Metadata store bị reset/eviction hoặc key space tăng đột biến.
- Có many-to-one key collisions giữa các tenants/operations.
- `compareValues` từ chối hàng loạt bản ghi out-of-order.
- Consumer ack rate cao nhưng business completed rate giảm.
- Số operation trạng thái `PROCESSING` hoặc `UNKNOWN` tăng liên tục.
- Store latency tăng gây poller lag/consumer backlog.
- Replay dùng key mới làm phát sinh side effect lặp.

## 27. Runbook: xử lý sự cố selector reject sai

### 27.1. Triệu chứng

Một nhóm đơn hàng không xuất hiện trong DB sau khi nhận file SFTP. Log cho thấy selector từ chối với lý do duplicate.

### 27.2. Các bước điều tra

1. Xác định **flow, adapter, handler và vị trí selector** thật.
2. Tìm message/business operation key đã bị từ chối và metadata value hiện tại.
3. Kiểm tra keyStrategy và valueStrategy có tạo collision hoặc sai version không.
4. Tìm outcome ở business DB, inbox và downstream API.
5. Xem lịch restart, scale-out, replay, retry và nguồn có out-of-order không.
6. Kiểm tra atomicity/durability của store trên topology đang chạy.
7. Đối chiếu trạng thái ack/offset/file filter để biết nguồn còn giữ message không.
8. Không xóa key trước khi biết operation đã commit hay chưa.

### 27.3. Ma trận quyết định

| Tìm thấy | Quyết định |
| --- | --- |
| Key tồn tại, business COMPLETED | Giữ marker; duplicate hợp lệ, không replay |
| Key tồn tại, business chưa từng chạy | Khắc phục marker/state và replay có kiểm soát |
| Key tồn tại, outcome downstream không rõ | Reconciliation trước retry |
| Two keys bị gộp do chiến lược key sai | Sửa key namespace, xác định tất cả operations bị bỏ |
| Store mất key sau restart | Điều tra khả năng duplicate thật, chuyển durable store |
| High-watermark vượt qua sequence chưa xử lý | Hạ/checkpoint lại có kiểm soát hoặc replay gap theo inbox |
| Store outage | Fail-safe theo policy, ngăn ack sai |

### 27.4. Khi cần replay

Trước khi replay:

- Có owner/approval nếu operation có side effect nhạy cảm.
- Xác định **original operation key** và request fingerprint.
- Biết downstream đã/ chưa xử lý lần đầu.
- Nếu cần xóa/sửa metadata, chỉ tác động **đúng key/namespace** và dùng concurrency protection.
- Giới hạn throughput, chạy canary rồi tăng dần khi backlog lớn.
- Lưu audit: lý do, người thực hiện, scope, before/after, result.

**Tuyệt đối không flush toàn bộ Redis/metadata table chỉ để xử lý một đơn bị bỏ sót.** Việc đó có thể biến hàng nghìn event cũ thành "new".

## 28. Tình huống xuyên suốt: FileSplitter cập nhật báo cáo

Một ứng dụng lấy file giao dịch hằng giờ từ SFTP, dùng `FileSplitter` phát từng record, lưu báo cáo vào JDBC và phát một event sang Kafka.

### 28.1. Kiến trúc ban đầu

~~~mermaid
flowchart LR
    SFTP["SFTP inbound + file filter"] --> FILE["Local file / stream"]
    FILE --> SPLIT["FileSplitter"]
    SPLIT --> CH["MessageChannel"]
    CH --> SEL["MetadataStoreSelector"]
    SEL --> JDBC["JDBC business handler"]
    JDBC --> KAFKA["Kafka outbound"]
    SEL --> META["Shared metadata store"]
    KAFKA --> OUTBOX["Delivery / reconciliation status"]
~~~

### 28.2. Kịch bản A — dòng được xử lý theo thứ tự

File F thế hệ G1 có dòng 1,2,3. Selector lưu `key=F:G1`, value lần lượt 1,2,3 qua `compareValues`. Nếu không xảy ra lỗi, không có xử lý song song và checkpoint an toàn, flow có thể bỏ qua những dòng đã có sequence sau restart.

### 28.3. Kịch bản B — lỗi giữa select và JDBC commit

Selector chấp nhận dòng 2 và lưu `value=2`. JDBC transaction lỗi trước commit; ứng dụng restart. Dòng 2 được phát lại, nhưng `compareValues(old=2,new=2)` từ chối.

**Bài học:** Một watermark trong metadata store không tự chứng minh JDBC commit. Cần thiết kế transactional inbox hoặc checkpoint thực sự liên kết với outcome nghiệp vụ.

### 28.4. Kịch bản C — xử lý song song out-of-order

Các dòng 2 và 3 được dispatch tới hai workers. Dòng 3 cập nhật value lên 3 trước khi dòng 2 được xử lý. Selector sau đó từ chối dòng 2. Nếu yêu cầu phải xử lý đủ mọi dòng, không thể dùng một `max sequence` đơn giản.

**Hướng sửa:** Chuyển sang `key = file-generation + record-business-id` và lưu outcome theo record, hoặc bảo đảm xử lý có thứ tự/checkpoint liên tục.

### 28.5. Kịch bản D — Kafka publish thành công, xác nhận bị mất

JDBC đã commit và Kafka producer publish event, nhưng process crash trước khi cập nhật trạng thái gửi. Khi restart, pipeline có thể gửi lại event.

**Hướng xử lý:** Dùng transactional outbox hoặc chiến lược phát/reconcile được hỗ trợ; consumer Kafka vẫn phải xem xét idempotency riêng. `MetadataStoreSelector` ở inbound không tự bảo đảm Kafka outbound có exactly-once xuyên DB.

### 28.6. Thiết kế cải tiến

~~~mermaid
flowchart TD
    SRC["SFTP + file generation"] --> SPLIT["FileSplitter/record parser"]
    SPLIT --> KEY["Canonical business operation key"]
    KEY --> INBOX["Transactional inbox / atomic claim"]
    INBOX --> CHECK{"State?"}
    CHECK -->|Completed| ACK["Skip side effect / cached outcome"]
    CHECK -->|Processing| WAIT["Wait / lease / investigate"]
    CHECK -->|New| DB["JDBC business transaction"]
    DB --> OB["Outbox entry cùng transaction"]
    OB --> WORK["Outbound Kafka worker"]
    WORK --> RES["Result / reconciliation"]
    RES --> COMPLETE["Mark COMPLETED"]
    COMPLETE --> ACK
    CHECK -->|Conflict| ERR["Quarantine + audit"]
~~~

Ở thiết kế này, `MetadataStoreSelector` vẫn có thể là **optimization** để giảm số message phải xử lý sâu, nhưng **inbox/business unique constraint** mới chịu trách nhiệm chính về correctness qua crash. Nếu selector được đặt trước inbox, phải chắc chắn nó không chặn một operation chưa hoàn tất.

### 28.7. Record audit minh họa

~~~json
{
  "eventId": "SFTP-REPORT-REPLAY-004",
  "sourceFile": "orders-2026-11-23.csv",
  "fileGeneration": "sha256:example",
  "recordNumber": 2,
  "businessOperationKey": "order:create:T42:ORD-972",
  "selectorDecision": "ALREADY_SEEN",
  "businessOutcome": "NOT_COMMITTED",
  "recoveryDecision": "RECONCILE_AND_REPLAY",
  "owner": "integration-platform",
  "verification": "pending"
}
~~~

Đây là schema ứng dụng minh họa. Đối tượng `selectorDecision=ALREADY_SEEN` không được tự chuyển thành `businessOutcome=COMPLETED`.

## 29. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Dùng Spring Message ID làm business key | ID có thể mới sau redelivery/transform | Dùng stable operation ID |
| Dùng file path duy nhất làm key cho file có thể ghi đè | File thế hệ mới bị coi trùng | Thêm generation/version hoặc immutable upload contract |
| Không set valueStrategy nhưng nghĩ value là business version | Mặc định là message timestamp | Cung cấp valueStrategy |
| So sánh string `"10" > "9"` theo từ điển | Thứ tự lexical khác thứ tự số học | Parse và validate numeric revision |
| Đảo thứ tự tham số `compareValues` | Version cũ có thể thay version mới | `oldValue` trước, `newValue` sau |
| Dùng high-watermark với xử lý out-of-order | Message chưa xử lý bị bỏ qua | Ordered processing/gap tracking/per-record keys |
| Selector accept rồi coi business completed | Crash sau marker gây mất operation | Inbox + transaction/reconciliation |
| `SimpleMetadataStore` trên nhiều pods | Store không chia sẻ | Shared atomic durable store |
| Dùng `get` rồi `put` riêng | Race condition giữa consumers | `putIfAbsent`/`replace` atomic |
| Không kiểm tra Redis/DB topology | CAS không có guarantees dự kiến | Test backend và phiên bản cụ thể |
| Discard duplicate của HTTP gateway mà không có reply | Client timeout lặp | Cached result/pending/conflict response |
| Quên source ack/offset | Message bị mất hoặc redeliver vô hạn | Integration tests theo adapter/container |
| Xóa key khi HTTP timeout | Side effect có thể đã commit | Reconciliation trước retry |
| Tự động flush metadata khi debug | Event cũ được xem là mới | Scoped changes + approval + audit |
| Một key chung cho nhiều side effects | Nhánh A success che nhánh B fail | Per-consumer/per-operation key/outbox |
| Key chứa PII hoặc raw credential | Rò rỉ qua metadata/log | Hash/reference và ACL |
| TTL ngắn hơn replay window | Replay tạo duplicate | Retention phù hợp business correctness |
| Không có runbook cho stale marker | Operator replay tùy tiện | Trạng thái rõ, owner và failure evidence |

## 30. Bài tập tự kiểm tra

### Bài 1. Nhận lần đầu và duplicate

Một selector với key `order:create:T42:ORD-971` đang dùng `SimpleMetadataStore`. Message đầu được accept; message thứ hai có cùng operation key nhưng Spring Message ID khác.

**Đáp án:** Message thứ hai bị từ chối theo first-seen semantics trong cùng store. Spring Message ID khác không ảnh hưởng nếu keyStrategy dựa vào operation ID.

### Bài 2. Restart JVM

Sau khi restart ứng dụng, message cũ được selector accept lại mặc dù trước đó đã xử lý.

**Đáp án:** Nếu dùng `SimpleMetadataStore`, state in-memory đã mất. Cần persistent/shared store hoặc transactional inbox và test restart.

### Bài 3. compareValues cũ và mới

Old = `"9"`, New = `"10"`. Bạn dùng `old.compareTo(new) < 0`.

**Đáp án:** Lexical comparison có thể sai với số có nhiều chữ số. Parse số nguyên và so theo numeric version sau khi validate.

### Bài 4. Out-of-order records

File có dòng 1,2,3; dòng 3 đến trước dòng 2; selector lưu maximum sequence.

**Đáp án:** Dòng 2 có thể bị từ chối dù chưa hoàn tất. Không dùng high-watermark đơn giản nếu cần xử lý đủ mọi record và không bảo đảm ordering.

### Bài 5. Crash sau putIfAbsent

Store đã lưu K; business transaction thất bại. Broker redeliver.

**Đáp án:** Selector đơn giản có thể reject K, gây mất operation nếu bị discard/ack. Dùng inbox/transaction state hoặc recovery đảm bảo K chưa completed vẫn được xử lý.

### Bài 6. HTTP request-reply

Client retry cùng Idempotency-Key; duplicate route chỉ ghi log.

**Đáp án:** Không đủ. API cần trả cached business result, pending hoặc conflict theo contract; không để caller timeout vô hạn.

### Bài 7. Hai pods và atomicity

Hai pods mỗi pod có `SimpleMetadataStore` riêng. Cả hai cùng nhận K.

**Đáp án:** Cả hai có thể accept. Cần shared store/unique constraint ở nơi phối hợp thật sự.

### Bài 8. File thế hệ mới

Đối tác upload một file mới cùng tên nhưng nội dung đã thay đổi. Selector chỉ dùng absolute path làm key.

**Đáp án:** File mới có thể bị xem trùng với file cũ. Cần version/generation/checksum hoặc contract upload bất biến.

### Bài 9. Tạo bản mới có chủ đích

Một tài liệu cùng ID được cập nhật sang revision 2. Chính sách nghiệp vụ chỉ cần latest revision.

**Đáp án:** Dùng `valueStrategy=revision` và `compareValues(new>old)` có thể phù hợp nếu version monotonic, concurrency/backfill và transaction semantics đã được kiểm chứng.

### Bài 10. Metadata store outage

Redis metadata store không truy cập được nhưng adapter vẫn nhận hàng nghìn đơn.

**Đáp án:** Không tự fail open nếu đây là lớp chống trùng duy nhất. Cần policy fail-safe, buffer/backpressure, alert và retry có giới hạn; nếu có downstream idempotency mạnh, quyết định bỏ qua guard vẫn phải được phê duyệt.

## 31. Checklist triển khai MetadataStoreSelector

1. **Đúng mục đích:** Dùng selector để quyết định message accept/reject, không xem đó là transaction coordinator.
2. **Đúng key:** Key gắn với business operation hoặc checkpoint contract, có namespace và version phù hợp.
3. **Đúng value:** Biết mặc định là timestamp; chỉ dùng version/sequence khi có valueStrategy rõ ràng.
4. **Đúng compareValues:** Old trước, new sau; validate kiểu và semantics cập nhật.
5. **Ordering được hiểu rõ:** High-watermark không được bỏ mất event out-of-order hoặc gap chưa xử lý.
6. **Store atomic:** `putIfAbsent`/`replace` đúng trên topology thực tế.
7. **Store durable:** Nếu cần sống qua restart, dùng persistent shared store, kiểm tra crash/failover.
8. **Không ghi key quá sớm mà bỏ quên outcome:** Có inbox/transaction/reconciliation nếu nghiệp vụ quan trọng.
9. **Duplicate behavior rõ:** Interceptor đánh dấu header, discard hoặc exception theo cấu hình.
10. **Handler advice gắn đúng điểm:** Không để side effect ở trước vị trí guard.
11. **Source và business state tách biệt:** File filter/checkpoint không đồng nghĩa business completed.
12. **Ack đúng:** JMS/AMQP/Kafka commit/ack/offset theo outcome, integration test thật.
13. **HTTP reply đúng:** Duplicate có cached result/pending/conflict hợp lệ.
14. **JDBC state đúng:** Row claim, unique constraint và transaction được thiết kế rõ.
15. **Retry/replay đúng:** Giữ nguyên operation key, có DLQ/reconciliation cho outcome unknown.
16. **Fan-out đúng:** Per-consumer/per-effect idempotency khi nhiều nhánh có side effects độc lập.
17. **Key lifecycle rõ:** Retention, eviction, migration, backup và scoped cleanup.
18. **Store outage an toàn:** Không bỏ qua dedupe không kiểm soát, có backpressure và cảnh báo.
19. **Observability:** Theo dõi accepted/rejected, store errors, stale keys và business completion.
20. **Bảo mật:** Không đưa secret/PII vào key/value/log, hạn chế quyền sửa/xóa metadata.
21. **Test cạnh tranh:** Nhiều threads/instances, restart, redis/database failover và version races.
22. **Test crash windows:** Sau selector accept, trước commit, sau commit và trước ack.
23. **Runbook:** Có owner và quy trình xác minh/replay một key cụ thể.
24. **Phụ thuộc phiên bản:** Kiểm tra imports, DSL, store semantics và `compareValues` theo Spring Integration version dự án.

## 32. Tài liệu tham khảo

Các nguồn chính thức để đối chiếu API và ngữ nghĩa với phiên bản đang dùng:

1. **Spring Integration – Idempotent Receiver Enterprise Integration Pattern**  
   https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
2. **Spring Integration – Metadata Store**  
   https://docs.spring.io/spring-integration/reference/meta-data-store.html
3. **Spring Integration – File Splitter / Idempotent Downstream Processing a Split File**  
   https://docs.spring.io/spring-integration/reference/file/splitter.html
4. **Spring Integration Javadoc – MetadataStoreSelector**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html
5. **Spring Integration Javadoc – ConcurrentMetadataStore**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html

Các đoạn Java/XML trong bài là **ví dụ học tập**, yêu cầu dự án lựa chọn dependencies và đối chiếu API theo đúng version Spring Integration/Spring Retry/Spring Boot đang sử dụng. Không sao chép toàn bộ cấu hình vào production mà bỏ qua transaction, ack semantics và bài kiểm thử đối ứng.

## 33. Tổng kết

`MetadataStoreSelector` là một `MessageSelector` dùng `ConcurrentMetadataStore` để lựa chọn message qua **key/value**. Với key mới, selector dựa vào `putIfAbsent` để chấp nhận; với key đã có, `compareValues` cho phép chấp nhận và cập nhật value mới theo điều kiện khi dùng store hỗ trợ atomic update. `IdempotentReceiverInterceptor` hoặc `MessageFilter` giúp đưa quyết định này vào luồng xử lý.

Điều quan trọng nhất là **không đồng nhất việc selector đã lưu key với việc nghiệp vụ đã hoàn tất**. File/SFTP filter có trách nhiệm ở lớp nhận file; JMS/AMQP/Kafka quản lý redelivery và ack/offset; HTTP gateway cần trả business reply; JDBC cần state và transaction; còn dữ liệu chuyển qua nhiều hệ thống thường cần **stable operation key, unique constraint, transactional inbox/outbox, idempotent downstream và reconciliation**. Khi áp dụng đúng các ranh giới này, `MetadataStoreSelector` trở thành một công cụ tin cậy giúp giảm xử lý trùng **mà không bỏ sót những message chưa thực sự được xử lý thành công**.
