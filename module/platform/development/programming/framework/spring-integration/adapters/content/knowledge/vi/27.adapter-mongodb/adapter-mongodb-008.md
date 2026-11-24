# MetadataStore trong MongoDB với Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **`MetadataStore`** là kho **key–value metadata** dùng ghi nhớ trạng thái kỹ thuật giữa các lần poll, message và lần khởi động ứng dụng; phân biệt với lưu document nghiệp vụ hoặc Spring Message.
- Hiểu sự khác nhau giữa `SimpleMetadataStore` trong RAM, `MetadataStore` bền vững và `ConcurrentMetadataStore` dùng trong nhiều thread/instance.
- Khởi tạo đúng **`MongoDbMetadataStore`** từ `MongoDatabaseFactory` hoặc `MongoTemplate`, chọn collection metadata và đăng ký bean tên `metadataStore` khi phù hợp.
- Sử dụng chính xác `get`, `put`, `remove`, **`putIfAbsent`** và **`replace`**; phân biệt kiểm tra rồi ghi hai bước với thao tác nguyên tử.
- Dùng MongoDB-backed metadata cho **persistent accept-once filter** của File, FTP/SFTP, Feed và cho **Idempotent Receiver**.
- Thiết kế khóa có namespace gồm môi trường, flow, nguồn và định danh file/event; xử lý thay đổi version, xung đột khóa và retention.
- Nhận diện ranh giới giữa **đã đánh dấu seen/claimed** và **downstream business commit**, thiết kế retry, rollback/recovery, lease và idempotency cho yêu cầu tin cậy.
- Kiểm thử restart, hai instance cạnh tranh cùng khóa, lỗi MongoDB, mất mạng, filter reset, failover và graceful shutdown.
- Chọn giữa `MongoDbMetadataStore`, `MongoDbMessageStore`, MongoDB inbound adapter, change stream và một work-queue chuyên dụng theo đúng nhu cầu.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi module là kết nối các hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành luồng trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, chú trọng **hợp đồng message, lỗi và vòng đời kết nối**. Ở đây, MongoDB không chỉ lưu dữ liệu nghiệp vụ: nó còn có thể lưu **trạng thái nhận biết nguồn** giúp các adapter xử lý nhất quán qua restart hoặc giữa nhiều instance.

## 1. Bài toán: một file SFTP bị nhận lại sau khi restart

Một hệ thống đối tác mỗi ngày gửi file qua SFTP:

~~~text
/remote/orders/orders_20261123_01.csv
/remote/orders/orders_20261123_02.csv
~~~

Ứng dụng Spring Integration dùng SFTP inbound adapter để tải file về thư mục local, rồi biến từng dòng thành order message và đưa sang Kafka.

Một phiên bản đơn giản dùng `AcceptOnceFileListFilter` trong RAM có thể chạy như sau:

~~~text
09:00  Instance A phát hiện orders_20261123_01.csv
09:01  Filter ghi nhận file đã thấy trong bộ nhớ A
09:02  File được xử lý; ứng dụng dừng để triển khai bản mới
09:05  Instance A' khởi động lại; bộ nhớ filter ban đầu trống
09:06  Cùng file vẫn tồn tại trên SFTP → có thể được phát lại
~~~

Khi có hai instance đồng thời, một bộ nhớ riêng cho mỗi instance cũng không đủ để phối hợp:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as SFTP server
    A->>D: listFiles()
    B->>D: listFiles()
    D-->>A: orders_01.csv
    D-->>B: orders_01.csv
    Note over A,B: Mỗi bộ lọc RAM đều chưa thấy file
    A->>A: acceptOnce = true
    B->>B: acceptOnce = true
    Note over A,B: Hai worker có thể xử lý cùng dữ liệu
~~~

**`MongoDbMetadataStore` giải quyết phần trạng thái chung:** các bộ lọc có thể truy cập một kho metadata bền để ghi nhận file/event đã thấy. Việc nhiều tiến trình cùng dùng **`ConcurrentMetadataStore.putIfAbsent`** giúp chỉ một tiến trình chèn khóa mới trong một thời điểm.

Tuy nhiên, **file được ghi nhận là đã thấy không đồng nghĩa Kafka đã nhận hoặc order đã commit**. Crash sau bước đánh dấu nhưng trước khi xử lý hoàn tất vẫn là một vấn đề riêng cần thiết kế phục hồi.

## 2. MetadataStore là gì, và nó không phải gì?

Spring Integration định nghĩa interface:

~~~java
org.springframework.integration.metadata.MetadataStore
~~~

Nó cung cấp hợp đồng **`String key → String value`**, dùng lưu những trạng thái nhỏ phục vụ các thành phần integration:

- File nào đã được thấy và thời gian sửa cuối của file.
- Mốc thời gian/cursor đã quan sát ở một feed hoặc nguồn phù hợp.
- Một business event key đã được một bước idempotent receiver chấp nhận hay chưa.
- Phiên bản/giá trị cuối đã ghi cho một marker kỹ thuật.
- Một dạng checkpoint nhỏ **nếu chính ứng dụng thiết kế semantics của checkpoint**.

Điều này khác với lưu payload của message.

| Thành phần | Lưu gì? | Dùng để làm gì? |
|---|---|---|
| **`MetadataStore`** | Các cặp **String key/value** | Trạng thái seen, marker, dedup/checkpoint |
| **`ConcurrentMetadataStore`** | Cặp key/value và phép cập nhật nguyên tử | Nhiều thread/instance cùng cạnh tranh khóa |
| **`MongoDbMetadataStore`** | Metadata bền trong collection MongoDB | Dùng chung trạng thái qua restart và nhiều instance |
| **`SimpleMetadataStore`** | Metadata trong bộ nhớ | Lab hoặc trạng thái ngắn hạn, không bền qua restart |
| **`MongoDbMessageStore`** | Spring Messages / message groups | Message store cho queue/channel/aggregator tùy loại |
| **`MongoDbChannelMessageStore`** | Messages của persistent channel | Queue-backed channel theo hợp đồng riêng |
| **MongoDB inbound channel adapter** | Đọc business documents theo poll | Phát Message từ MongoDB collection |
| **MongoDB outbound channel adapter** | Ghi business payload vào MongoDB | Lưu document nghiệp vụ |
| **MongoDB change stream** | Sự kiện thay đổi MongoDB | Phát change events qua subscription |
| **MessageChannel** | Vận chuyển/định tuyến Message | Nối các endpoint trong IntegrationFlow |

**Không cấu hình `MongoDbMetadataStore` rồi cho rằng `QueueChannel` tự trở nên bền vững.** Một persistent channel cần loại `MessageStore` tương thích và cấu hình queue riêng. MetadataStore không có contract lưu `Message<?>`, headers hoặc payload.

### 2.1. Metadata tồn tại ở mức nào?

Một entry minh họa về mặt logic:

~~~text
key   = "prod|sftp-orders|/remote/orders/orders_01.csv"
value = "2026-11-23T02:00:00Z"
~~~

Đây là **minh họa key/value nghiệp vụ**, không phải schema BSON cố định của `MongoDbMetadataStore`. Spring Integration có thể xây khóa/giá trị khác nhau tùy loại filter, prefix và phiên bản. Không tự can thiệp vào document nội bộ theo một cấu trúc bạn tự đoán rồi kỳ vọng framework vẫn hiểu đúng.

### 2.2. Khi nào metadata bền giúp ích?

- Application restart nhưng file/feed chưa bị xóa khỏi nguồn.
- Rolling deployment có nhiều instance cùng scan một thư mục.
- Một workflow cần kiểm tra một event key đã xuất hiện trước đó.
- Các adapter cần chia sẻ một trạng thái kỹ thuật đơn giản giữa process.
- Muốn di chuyển việc giữ trạng thái từ RAM sang hạ tầng bền đã có MongoDB.

Ngược lại, metadata không phải giải pháp duy nhất cho mọi công việc: **atomic database claim**, durable broker, outbox, message store hoặc transaction có thể phù hợp hơn nếu cần bảo đảm business completion.

## 3. Phân biệt ba interface và hai loại store

### 3.1. MetadataStore cơ bản

Interface `MetadataStore` có các method:

| Method | Giá trị trả về | Hành vi |
|---|---|---|
| `get(key)` | `String` hoặc `null` | Đọc giá trị hiện tại; `null` khi không có khóa |
| `put(key, value)` | `void` | Ghi hoặc cập nhật giá trị cho khóa |
| `remove(key)` | Giá trị cũ hoặc `null` | Xóa entry theo khóa |

Các operation hữu ích nhưng **không đủ để chống race** trong mã tự viết theo kiểu “get trước, put sau”.

### 3.2. ConcurrentMetadataStore

Interface `ConcurrentMetadataStore` mở rộng `MetadataStore`, thêm hai phép quan trọng:

| Method | Giá trị trả về | Khi nào thành công? |
|---|---|---|
| **`putIfAbsent(key, value)`** | **`null`** nếu chèn thành công; **giá trị cũ** nếu khóa đã có | Nguyên tử ở mức một key |
| **`replace(key, oldValue, newValue)`** | **`true`** nếu giá trị hiện tại đúng oldValue và được thay | Compare-and-set (CAS) trên một key |

Ví dụ:

~~~java
String first = store.putIfAbsent("source|file-101", "seen-by-A");
// Nếu first == null: A đã đặt entry thành công.

String second = store.putIfAbsent("source|file-101", "seen-by-B");
// second == "seen-by-A": B không được chèn cùng key.

boolean updated = store.replace(
        "source|file-101", "seen-by-A", "processed");
// true khi entry vẫn còn chính xác giá trị "seen-by-A".
~~~

**Không coi `putIfAbsent(...) == null` là “file đã được xử lý”.** Nó chỉ cho biết caller thắng cuộc đua **ghi nhận khóa**.

### 3.3. Vì sao “get rồi put” không an toàn?

Đoạn code sau không phù hợp với ứng dụng nhiều instance:

~~~java
if (store.get(key) == null) {
    store.put(key, "seen");
    process(file);
}
~~~

Race:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant M as MongoDB MetadataStore
    A->>M: get(key) → null
    B->>M: get(key) → null
    A->>M: put(key,"seen")
    B->>M: put(key,"seen")
    Note over A,B: Cả hai đều chạy process(file)
~~~

Thay bằng:

~~~java
String previous = store.putIfAbsent(key, "seen");
if (previous == null) {
    process(file);
}
~~~

Ở đây MongoDB-backed `ConcurrentMetadataStore` bảo đảm thao tác **chèn key** là nguyên tử theo contract. Nhưng việc gọi `process(file)` là operation kế tiếp **không thuộc cùng atomic MongoDB operation**.

## 4. MongoDbMetadataStore dùng API nào?

Class chính:

~~~java
org.springframework.integration.mongodb.metadata.MongoDbMetadataStore
~~~

`MongoDbMetadataStore` được Spring Integration cung cấp từ phiên bản 4.2 và **triển khai `ConcurrentMetadataStore`**. Nó dùng MongoDB để lưu metadata, nhờ vậy nhiều application instances có thể truy cập cùng trạng thái nếu cùng database, collection và key namespace.

Các constructor được cung cấp theo API hiện hành:

~~~java
new MongoDbMetadataStore(mongoDatabaseFactory);
new MongoDbMetadataStore(mongoDatabaseFactory, "integration_metadata");

new MongoDbMetadataStore(mongoTemplate);
new MongoDbMetadataStore(mongoTemplate, "integration_metadata");
~~~

Trong đó:

- `mongoDatabaseFactory` có kiểu **`org.springframework.data.mongodb.MongoDatabaseFactory`**.
- `mongoTemplate` có kiểu **`org.springframework.data.mongodb.core.MongoTemplate`**.
- Constructor một tham số dùng collection mặc định `DEFAULT_COLLECTION_NAME`.
- Constructor hai tham số cho phép đặt collection metadata tường minh.
- `MongoTemplate` là implementation của `MongoOperations` nhưng constructor cụ thể này nhận **MongoTemplate**, không mặc định nhận mọi implementation `MongoOperations`.
- Class metadata store không phải reactive MongoDB client; các operation theo contract ở đây là synchronous/blocking.

**Chú ý phiên bản:** tài liệu ví dụ lịch sử có thể dùng tên `MongoDbFactory`. Với Spring Data MongoDB hiện đại, interface Java là **`MongoDatabaseFactory`**. Bean name `mongoDbFactory` trong XML không phải bằng chứng Java interface cũ còn được dùng.

## 5. Thêm dependency và kết nối MongoDB

### 5.1. Maven cho Spring Boot 3.x

Với ứng dụng Spring Boot 3.x, quản lý version qua BOM tương thích:

~~~xml
<!-- Các dependency nằm trong <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

File/SFTP filters cần dependency adapter tương ứng nếu thực hành phần đó, ví dụ `spring-integration-file` hoặc `spring-integration-sftp`. Trong ứng dụng Spring Boot, bạn có thể lấy các module đó qua những starter/managed dependency phù hợp. **Không bắt buộc có SFTP server để học API MetadataStore cơ bản.**

Nếu dự án dùng Spring Boot hoặc Spring Integration major version khác, kiểm tra BOM/import và driver tương thích. Bài này tập trung vào **blocking MongoDbMetadataStore**, không trộn tùy ý với reactive driver.

### 5.2. URI MongoDB local

Trong `application.yml` cho Spring Boot 3.x:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/integration_lab
~~~

Đây là **database thử nghiệm**. Trong production, dùng secret manager/biến môi trường, TLS và MongoDB permissions có phạm vi phù hợp. Nếu Boot đã cung cấp `MongoDatabaseFactory` và `MongoTemplate`, hãy inject chúng thay vì tạo thêm một MongoClient bên trong từng filter.

## 6. Cấu hình bean MongoDbMetadataStore bằng Java

### 6.1. Đăng ký bean có tên metadataStore

Một cấu hình thực hành:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.mongodb.metadata.MongoDbMetadataStore;

@Configuration
public class MongoMetadataConfiguration {

    @Bean("metadataStore")
    public ConcurrentMetadataStore metadataStore(
            MongoDatabaseFactory mongoDatabaseFactory) {

        return new MongoDbMetadataStore(
                mongoDatabaseFactory, "integration_metadata");
    }
}
~~~

Ý nghĩa:

1. `MongoDatabaseFactory` xác định MongoDB database/connection thực tế.
2. `"integration_metadata"` là **collection dành riêng cho trạng thái kỹ thuật**; không dùng lẫn với collection telemetry/order business.
3. `ConcurrentMetadataStore` là interface đủ khả năng phục vụ các persistent accept-once filters và idempotent receiver.
4. Tên bean **`metadataStore`** là convention để **những thành phần có cơ chế tự tìm MetadataStore** có thể phát hiện bean chung.
5. Không phải mọi adapter đều tự động sử dụng bean chỉ vì tên trùng convention. Với filters, nên **inject/store một cách tường minh** để bảo đảm đúng nơi ghi trạng thái.
6. Các instance khác muốn chia sẻ state phải dùng **cùng MongoDB deployment/database/collection và key scheme**.

Khi cần một metadata store khác cho workload hoặc môi trường, đặt bean riêng và inject bằng `@Qualifier`. Tránh hai bean cùng tên nhưng chỉ một bean thật sự được dùng vì autowiring khác nhau.

### 6.2. Cấu hình từ MongoTemplate

Nếu đã có bean `MongoTemplate` do Spring Boot quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.mongodb.metadata.MongoDbMetadataStore;

@Bean("metadataStore")
public ConcurrentMetadataStore metadataStore(
        MongoTemplate mongoTemplate) {

    return new MongoDbMetadataStore(
            mongoTemplate, "integration_metadata");
}
~~~

**Đây là cách thay thế mục 6.1**, không khai báo cả hai bean `metadataStore` trong cùng context. `MongoDbMetadataStore` sẽ dùng cấu hình database/driver mà template có.

### 6.3. Default collection hay collection có tên rõ?

Có thể dùng constructor chỉ có factory/template để giữ `DEFAULT_COLLECTION_NAME`, nhưng trong môi trường thật **chọn tên tường minh thường dễ vận hành**:

~~~text
Database: integration_lab
Collection: integration_metadata
Keys:
  prod|orders-sftp|/remote/orders/orders_01.csv
  prod|invoice-idempotency|invoice-123
~~~

Tên collection không tự tạo quyền truy cập: account MongoDB phải được phép thao tác trong collection đó. Hãy giữ collection metadata riêng khỏi business documents và message store để tránh các thao tác retention hoặc migration không đúng mục đích.

## 7. API get, put, putIfAbsent, replace, remove qua ví dụ

### 7.1. Class thử nghiệm thao tác metadata

~~~java
package example.mongodb;

import java.util.Objects;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.stereotype.Service;

@Service
public class MetadataExampleService {

    private final ConcurrentMetadataStore store;

    public MetadataExampleService(
            ConcurrentMetadataStore store) {
        this.store = store;
    }

    public boolean firstSeen(String source, String eventId) {
        String key = "demo|v1|" + source + "|" + eventId;
        return store.putIfAbsent(key, "SEEN") == null;
    }

    public String getStatus(String source, String eventId) {
        return store.get("demo|v1|" + source + "|" + eventId);
    }

    public boolean advanceStatus(
            String source, String eventId,
            String expected, String next) {

        Objects.requireNonNull(expected);
        Objects.requireNonNull(next);
        String key = "demo|v1|" + source + "|" + eventId;

        return store.replace(key, expected, next);
    }

    public String removeMarker(String source, String eventId) {
        String key = "demo|v1|" + source + "|" + eventId;
        return store.remove(key);
    }
}
~~~

**Giới hạn của ví dụ:** source/eventId phải được validation trước khi trở thành key; không cho input dài hoặc chứa phân tách không được quy định làm thay đổi namespace. Code ví dụ chỉ minh họa API metadata, **chưa triển khai một workflow claim/lease/ACK an toàn**.

### 7.2. Trình tự thao tác

Giả sử một key chưa tồn tại:

~~~text
get("demo|v1|sftp|evt-101")                 -> null

putIfAbsent("demo|v1|sftp|evt-101","SEEN") -> null
get(...)                                    -> "SEEN"

putIfAbsent("demo|v1|sftp|evt-101","SEEN") -> "SEEN"

replace("demo|v1|sftp|evt-101",
        "SEEN","DONE")                       -> true

replace("demo|v1|sftp|evt-101",
        "SEEN","FAILED")                     -> false

remove("demo|v1|sftp|evt-101")             -> "DONE"
get(...)                                    -> null
~~~

Khi thao tác `putIfAbsent` trả `null`, caller giành được quyền **đặt key**. Khi `replace` trả false, có thể giá trị đã bị thay đổi, key đã bị xóa hoặc expectedValue sai; phải xử lý như **CAS conflict**, không tùy tiện gọi `put` ghi đè.

### 7.3. Hành vi put khác putIfAbsent

`put(key, value)` **ghi hoặc cập nhật** entry không điều kiện giá trị cũ. Nó phù hợp với marker quản trị/giá trị mới nhất khi ứng dụng có quyền cập nhật, nhưng **không dùng để giành quyền xử lý độc quyền**.

~~~java
store.put("source|checkpoint", "offset-200");
store.put("source|checkpoint", "offset-150");
// Nếu không có guard, checkpoint đã bị lùi từ 200 về 150.
~~~

Nếu offset/cursor cần tiến đơn điệu, dùng logic so sánh và **compare-and-set** phù hợp, có retry conflict. Không mặc định metadata store hiểu thứ tự của String offset; đó là business rule.

### 7.4. remove không phải compare-and-delete

`remove(key)` xóa key theo tên, không nhận expected value. Nếu có owner/lease đang thay đổi, xóa không điều kiện có thể vô tình xóa marker mới của worker khác.

Nếu cần “chỉ owner hiện tại được release”, hãy dùng protocol có điều kiện và/hoặc cơ chế database phù hợp. Không gọi `remove` tùy tiện trong error handler khi không biết key có đang thuộc worker khác.

## 8. Vì sao MongoDbMetadataStore an toàn hơn bộ nhớ cục bộ khi nhiều instance?

### 8.1. Chia sẻ trạng thái

Hai instance cần dùng cùng database/collection:

~~~mermaid
flowchart LR
    A["Spring Instance A"] --> F1["SFTP persistent filter"]
    B["Spring Instance B"] --> F2["SFTP persistent filter"]
    F1 --> M["MongoDbMetadataStore<br/>shared collection"]
    F2 --> M
    M --> DB[("MongoDB")]
    F1 --> C["MessageChannel"]
    F2 --> C
~~~

Một lần filter/selector thực hiện `putIfAbsent` hoặc `replace` trên **cùng key** chỉ có một operation thắng theo contract atomic. Không có lợi ích nếu instance A dùng collection `integration_metadata_a` còn B dùng `integration_metadata_b`, hoặc hai instance tạo hai key khác nhau cho cùng file.

### 8.2. Atomic key operation ≠ distributed transaction

Hai điều phải tách bạch:

- **Atomic trên entry:** ghi một key mới hoặc thay giá trị khi expectedValue khớp.
- **End-to-end business completion:** đã tải file đầy đủ, parse, lưu database đích, gửi Kafka/JMS và xác nhận nghiệp vụ.

Một operation metadata nguyên tử **không bao gồm** tất cả bước gửi HTTP, SFTP, Kafka hay JMS. Nếu file được đánh dấu SEEN rồi thread crash trước khi gửi message, có thể mất cơ hội xử lý lại nếu filter luôn tin marker đã lưu.

### 8.3. MetadataStore không tự trở thành distributed lock hoàn chỉnh

Bạn có thể xây một protocol owner/lease bằng metadata key/value, nhưng phải tự xử lý:

- Lease expiration và sai lệch đồng hồ giữa các node.
- Ai có quyền cập nhật/release key.
- Trường hợp process pause lâu rồi tiếp tục xử lý sau khi mất lease.
- Fencing token nếu side effect bên ngoài cần ngăn owner cũ ghi.
- Key bị kẹt do crash và cách thu hồi.
- Bảo đảm một request chỉ được tính hoàn tất sau business commit.

Nếu công việc là work queue MongoDB cần claim atomically trên document, **`findAndModify` theo trạng thái/lease** hoặc một message broker bền có thể phù hợp hơn MetadataStore thuần.

## 9. Persistent accept-once filter cho File inbound adapter

### 9.1. Filter mặc định trong RAM và filter persistent

Một `AcceptOnceFileListFilter` kiểu cơ bản nhớ file đã chấp nhận trong process. Sau restart, trạng thái RAM mất. Khi nguồn file không tự xóa/di chuyển, cùng file có thể được xử lý lại.

`FileSystemPersistentAcceptOnceFileListFilter` nhận một `ConcurrentMetadataStore` và prefix để lưu trạng thái file:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.file.filters.FileSystemPersistentAcceptOnceFileListFilter;
import org.springframework.integration.metadata.ConcurrentMetadataStore;

@Bean
public FileSystemPersistentAcceptOnceFileListFilter localFileFilter(
        ConcurrentMetadataStore metadataStore) {

    return new FileSystemPersistentAcceptOnceFileListFilter(
            metadataStore, "prod|file-import|");
}
~~~

Filter có thể ghi nhận **tên đường dẫn và thời gian chỉnh sửa file**; file thay đổi modified time có thể được xem là phiên bản mới và nhận lại tùy hợp đồng filter.

**Prefix dùng để tránh xung đột:** hai luồng nhập dữ liệu khác nhau có thể cùng thấy một file tên `orders.csv`. Nếu dùng chung key namespace một cách vô ý, trạng thái nhận của luồng A có thể ngăn luồng B.

### 9.2. Gắn filter vào FileReadingMessageSource

Ví dụ một source đọc file trên local disk:

~~~java
package example.mongodb;

import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.FileSystemPersistentAcceptOnceFileListFilter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class LocalFileInboundConfig {

    @Bean("importFiles")
    public MessageChannel importFiles() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow importLocalFiles(
            FileSystemPersistentAcceptOnceFileListFilter localFileFilter) {

        FileReadingMessageSource source =
                new FileReadingMessageSource();
        source.setDirectory(new File("data/incoming"));
        source.setFilter(localFileFilter);

        return IntegrationFlow
                .from(source,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(10)))
                .channel("importFiles")
                .get();
    }
}
~~~

**Điều kiện dùng:** thư mục `data/incoming` tồn tại và có quyền đọc, channel `importFiles` có consumer nhận `java.io.File`, ứng dụng có dependency `spring-integration-file`. Đường dẫn tương đối ở trên chỉ để lab; production cần cấu hình absolute path và kiểm soát quyền.

`maxMessagesPerPoll(10)` giới hạn số lần source nhận message trong một poll task, **không phải** số lượng metadata keys trong collection. Nếu có nhiều consumer hoặc thread, phải test sự phối hợp của source/filter và chính sách file lifecycle.

### 9.3. Một file đã thấy có thể thay đổi

Persistent accept-once file filters thường dùng filename/path và last-modified time làm thông tin nhận biết; nếu file bị ghi đè hoặc thay timestamp, filter có thể cho nhận lại. Điều này **khác với unique-content hash**.

Nếu nghiệp vụ yêu cầu “file bất biến và chỉ ghi một lần”, có thể thêm checksum hoặc business file ID ở tầng xử lý. Nếu file có thể được cập nhật sau khi đẩy tới SFTP, hãy quy định hợp đồng tên file/mtime/rename, tránh đọc file chưa hoàn tất.

## 10. MongoDB MetadataStore với SFTP / FTP inbound

SFTP inbound là hai tầng:

1. **Remote filter** quyết định file nào trên SFTP nên được tải về.
2. **Local filter** quyết định file local nào nên được phát thành Spring Message.

~~~mermaid
flowchart LR
    S["SFTP remote directory"] --> RF["SftpPersistentAcceptOnceFileListFilter"]
    RF -->|"Chọn file"| DL["Download/synchronize"]
    DL --> L["Local directory"]
    L --> LF["FileSystemPersistentAcceptOnceFileListFilter"]
    LF --> C["MessageChannel<File>"]
    RF --> M["Shared MongoDbMetadataStore"]
    LF --> M
~~~

**Tách remote/local state là điều quan trọng:** một file có thể đã được tải về nhưng chưa được gửi qua handler, hoặc có thể được gửi qua handler nhưng downstream xử lý lỗi. Hai filter không tự tạo một transaction bảo đảm toàn bộ các bước.

### 10.1. Remote SFTP filter dùng shared MongoDB store

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.sftp.filters.SftpPersistentAcceptOnceFileListFilter;

@Bean("remoteOrdersFilter")
public SftpPersistentAcceptOnceFileListFilter remoteOrdersFilter(
        ConcurrentMetadataStore metadataStore) {

    return new SftpPersistentAcceptOnceFileListFilter(
            metadataStore, "prod|sftp-remote-orders|");
}
~~~

Cấu hình filter này vào **remote filter** của SFTP inbound synchronizer/adapter, ví dụ XML attribute `filter`, hoặc cấu hình Java DSL/API tương đương của phiên bản bạn dùng. Với `FileSystemPersistentAcceptOnceFileListFilter`, gắn riêng làm **local filter** qua `local-filter`.

Nếu bạn dùng cả hai bộ lọc cùng collection, hãy dùng prefix khác nhau để tránh cùng một file bị hiểu nhầm là đã nhận ở tầng khác.

### 10.2. Ví dụ XML wiring

Một bản wiring minh họa với các bean filter được khai báo trong Spring context:

~~~xml
<!-- XML phải có namespace int và int-sftp, sessionFactory và channel -->
<int-sftp:inbound-channel-adapter
        id="ordersSftpInbound"
        session-factory="sftpSessionFactory"
        channel="importFiles"
        remote-directory="/remote/orders"
        local-directory="file:./data/orders"
        filter="remoteOrdersFilter"
        local-filter="localOrdersFilter"
        max-fetch-size="10">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="10"/>
</int-sftp:inbound-channel-adapter>
~~~

Trong đó:

- `remoteOrdersFilter` là bean `SftpPersistentAcceptOnceFileListFilter`.
- `localOrdersFilter` là bean `FileSystemPersistentAcceptOnceFileListFilter` với prefix **khác**.
- `sftpSessionFactory` do ứng dụng cung cấp, dùng credentials/host key được kiểm soát.
- `importFiles` là channel có consumer nhận File payload.
- `max-fetch-size` giới hạn số file remote được tải mỗi lượt synchronization phù hợp API adapter.
- `max-messages-per-poll` giới hạn số File Messages được phát ở một poll task.
- `max-fetch-size` và `max-messages-per-poll` **không có cùng nghĩa**; cần điều chỉnh theo file size, queue/backlog và concurrency.

Cấu hình XML là **phương án thay thế** flow File inbound ở mục 9, không đăng ký hai endpoint cùng cạnh tranh nhận cùng thư mục khi bạn chỉ muốn một pipeline.

### 10.3. Lưu ý quan trọng về failure/retry SFTP

Theo hành vi remote persistent file filter, các file có thể được ghi vào metadata **trước khi download**. Khi transfer thất bại, các bộ lọc có khả năng reverse có thể được rollback cho trường hợp transfer error. **Nhưng lỗi downstream sau khi file đã tải và được gửi thành message thường không tự xóa marker remote/local**.

Ví dụ:

~~~text
SFTP remote accept → metadata đánh dấu seen
    ↓
Download hoàn tất → local file
    ↓
Local filter phát File Message
    ↓
Kafka publish lỗi → downstream chưa commit
    ↓
Marker seen vẫn có thể tồn tại
~~~

Vì thế không nên tuyên bố “đã dùng persistent filter thì không mất dữ liệu, không cần retry”. Nếu cần xử lý lại khi downstream thất bại, phải thiết kế rollback/reset filter, trạng thái business hoặc durable queue riêng theo loại lỗi.

**Khác biệt phiên bản:** từ Spring Integration 7.0, persistent file list filters sử dụng key với **đường dẫn dài hơn** (đường dẫn thư mục lấy file kèm tên file) để giảm xung đột khi có hai file cùng tên ở các thư mục khác nhau. Khi nâng major version, phải đánh giá migration key cũ, tránh re-fetch hoặc bỏ sót ngoài ý muốn.

## 11. Idempotent Receiver dùng MongoDbMetadataStore

### 11.1. Tại sao cần Idempotent Receiver?

Một Kafka/JMS/AMQP/HTTP/UDP integration flow có thể nhận lại cùng sự kiện do retry, redelivery hoặc client gửi trùng. Dù nguồn đã có broker checkpoint, downstream vẫn nên dùng một **business event key bền** để nhận diện duplicate.

Ví dụ:

~~~json
{
  "eventId": "evt-101",
  "tenantId": "tenant-a",
  "type": "READING_CREATED",
  "deviceId": "node-7"
}
~~~

Không dùng Spring `MessageHeaders.ID` làm business dedup key: một event redelivery có thể được bọc vào message mới với UUID khác.

### 11.2. MetadataStoreSelector

Spring Integration cung cấp `MetadataStoreSelector`: từ request Message, selector tạo key và gọi `ConcurrentMetadataStore.putIfAbsent`. Nếu key chưa có, message được chấp nhận; nếu key đã tồn tại, nó được coi là duplicate theo policy mặc định.

Ví dụ:

~~~java
package example.mongodb;

public record BusinessEvent(
        String tenantId,
        String eventId,
        String type) {
}
~~~

Cấu hình selector và interceptor:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;

@Configuration
public class DeduplicationConfig {

    @Bean("deduplicateAdvice")
    public IdempotentReceiverInterceptor deduplicateAdvice(
            ConcurrentMetadataStore metadataStore) {

        MetadataStoreSelector selector =
            new MetadataStoreSelector(message -> {
                BusinessEvent event =
                        (BusinessEvent) message.getPayload();

                if (event.tenantId() == null
                        || event.eventId() == null
                        || event.eventId().isBlank()) {
                    throw new IllegalArgumentException(
                            "Missing stable event identity");
                }

                return "prod|events|v1|"
                        + event.tenantId()
                        + "|" + event.eventId();
            }, metadataStore);

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);

        // Yêu cầu duplicate không đi vào business handler.
        advice.setDiscardChannelName("nullChannel");
        return advice;
    }
}
~~~

Sau đó gắn vào một `@ServiceActivator` endpoint:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IdempotentReceiver;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class BusinessEventHandlerConfig {

    @Bean
    @ServiceActivator(inputChannel = "rawBusinessEvents")
    @IdempotentReceiver("deduplicateAdvice")
    public MessageHandler businessHandler() {
        return message -> {
            BusinessEvent event =
                    (BusinessEvent) message.getPayload();

            // Gọi service xử lý đã có contract và idempotency.
            System.out.println("Processing " + event.eventId());
        };
    }
}
~~~

Code minh họa cần một channel `rawBusinessEvents`, producer, dependencies và consumer wiring phù hợp trong cùng Spring context. Đoạn handler hiện chỉ ghi log — **không có business commit thật**.

### 11.3. Bẫy mặc định của IdempotentReceiverInterceptor

Khi interceptor **không** có `discardChannel` và không bật `throwExceptionOnRejection`, duplicate **có thể vẫn được chuyển tới handler**, nhưng được gắn header `duplicateMessage=true` để handler tự quyết định.

Nếu mục tiêu là chặn duplicate **trước khi handler chạy**, cần cấu hình discard channel (ví dụ `nullChannel`) hoặc chính sách từ chối tương ứng. Không đọc chữ “IdempotentReceiver” rồi tự suy ra duplicate mặc định luôn bị loại.

### 11.4. Khi selector đã ghi key nhưng handler thất bại

Trình tự:

~~~text
MetadataStoreSelector.accept(event)
  → putIfAbsent(eventKey, value) thành công
  → business handler bắt đầu
  → service đích lỗi / process crash
  → key vẫn tồn tại
  → redelivery bị coi là duplicate
~~~

**Đây là rủi ro đánh dấu quá sớm.** MetadataStoreSelector tiêu chuẩn chủ yếu là công cụ **lựa chọn chấp nhận**, không phải transaction manager cho Kafka + MongoDB + HTTP.

Đối với sự kiện không được mất, cần thiết kế:

- Lưu trạng thái `PROCESSING/DONE/RETRY` theo event ID.
- Chỉ đánh dấu DONE sau khi business commit được xác nhận.
- Có lease/timeout để phục hồi key PROCESSING bị kẹt.
- Có idempotency tại đích để xử lý trường hợp đích đã commit nhưng response bị thất lạc.
- Dùng durable broker/outbox hoặc database transaction đúng phạm vi khi cần.
- Không tự động xóa key sau mọi exception nếu có worker khác vừa claim lại bằng CAS.

### 11.5. compareValues và xử lý phiên bản

`MetadataStoreSelector` có thể cấu hình một `BiPredicate<String,String>` bằng `compareValues(...)` cho trường hợp muốn chấp nhận **giá trị mới** thay vì luôn loại mọi message cùng key.

Một ví dụ lý thuyết: key là file ID, value là số thứ tự bản cập nhật. Selector có thể chấp nhận phiên bản lớn hơn và thay metadata bằng CAS. Nhưng **điều kiện so sánh chuỗi phải được định nghĩa**, không dùng phép so sánh từ điển tùy tiện cho các số như `"9"` và `"10"`.

Trong bài học cơ bản, `putIfAbsent` thường dễ hiểu và an toàn hơn; chỉ bật compareValues khi đã xây test concurrency và version semantics.

## 12. MetadataStore khác với MongoDB inbound polling state

Đây là một điểm liên quan trực tiếp đến chương Adapter MongoDB:

- **`MongoDbMessageSource`** định kỳ query collection có document `status=NEW`.
- **`MongoDbMetadataStore`** là một kho key/value dùng bởi filter/selector hoặc code ứng dụng.
- **Chỉ đăng ký bean `metadataStore` không làm `MongoDbMessageSource` tự theo dõi “document đã poll”**.

Ví dụ query:

~~~javascript
db.inbox_events.find({ status: "NEW" })
~~~

Nếu MongoDbMessageSource chạy mỗi 5 giây và không cập nhật trạng thái, nó sẽ thấy lại cùng document. Việc có một MongoDbMetadataStore trong Spring context **không thay đổi query đó**.

Muốn tránh đọc lặp:

1. Thiết kế MongoDB query/update/claim trên chính document nguồn, ví dụ trạng thái `NEW → PROCESSING → DONE`.
2. Hoặc dùng một bộ lọc/selector sau source với metadata key ổn định, **có chính sách retry cho lỗi downstream**.
3. Nếu nhiều instance cần độc quyền xử lý một document, cân nhắc `MongoOperations.findAndModify` có điều kiện/lease thay cho đọc rồi ghi hai bước.
4. Nếu cần toàn bộ thay đổi từ MongoDB, xem xét change stream + resume token/checkpoint riêng.

**Không coi MetadataStore là một cursor tự động của MongoDB inbound adapter.** Mối liên hệ chỉ xuất hiện khi ứng dụng **cấu hình** endpoint cụ thể dùng metadata.

## 13. Thiết kế key namespace, value và retention

### 13.1. Key nên ổn định và đủ ngữ cảnh

Một key phù hợp có thể gồm:

~~~text
<environment>|<application>|<flow>|<source>|<identity>
~~~

Ví dụ:

~~~text
prod|ingestion|sftp-orders|partner-a|/remote/orders/2026-11-23.csv
prod|ingestion|file-local|site-3|D:/incoming/order-101.csv
prod|ingestion|idempotent|tenant-a|evt-101
~~~

Từ `"prod"`, `"ingestion"` và `"tenant-a"` ở đây chỉ là **giá trị minh họa**, không phải framework bắt buộc phải dùng. Với filter chuẩn, class tự thêm prefix/path/timestamp theo hợp đồng; không tự nối thêm những thành phần làm thay đổi key nội bộ của filter nếu chưa kiểm tra implementation/version.

### 13.2. Các lỗi key namespace thường gặp

| Sai sót | Hậu quả |
|---|---|
| Hai flow dùng cùng prefix nhưng ý nghĩa khác nhau | Key va chạm, file/event bị bỏ qua nhầm |
| Prefix khác giữa A/B dù cùng logical source | Hai instance không phối hợp, duplicate |
| Key dùng timestamp nhận message | Redelivery có timestamp mới, dedup vô hiệu |
| Key thiếu tenant/source | Khóa giống nhau giữa tenant khác nhau |
| Key chứa secret/token | Lộ thông tin trong metadata/log/backup |
| Key dựa vào đường dẫn chưa normalize | Hai path logic giống nhau trở thành hai key |
| Key bị đổi khi nâng phiên bản filter | Re-fetch ngoài ý muốn hoặc không nhìn thấy state cũ |
| Key quá dài/hỗn hợp ký tự | Vận hành/giám sát/backup khó khăn |
| Value chứa payload lớn | Dùng sai mục đích, tăng dữ liệu MongoDB |

### 13.3. Bao lâu nên giữ metadata?

Một kho persistent không tự có chính sách “quên sau 30 ngày” theo nghiệp vụ. Nếu mỗi ngày có hàng triệu file/event ID, collection sẽ tăng theo tốc độ này nếu không có retention.

Phải quyết định:

- Thời gian tối đa nguồn có thể redeliver/replay dữ liệu.
- Thời gian còn cần dedup trước khi chấp nhận xử lý lại.
- Yêu cầu audit, pháp lý, backup và disaster recovery.
- Tình huống một file thay đổi mtime nhưng tên giữ nguyên.
- Cách xóa entry **mà không tạo reprocessing hàng loạt**.

**Không tự tạo TTL index** dựa trên một field bạn suy đoán có trong schema `MongoDbMetadataStore`. Nếu muốn TTL, cần kiểm tra schema thật/version, rồi thiết kế retention ở tầng ứng dụng hoặc store tùy biến; MongoDB TTL deletion là hoạt động nền, không thay thế một lease chính xác theo thời gian.

### 13.4. Thay prefix là một migration

Giả sử key cũ là `prod|sftp-orders|...` nhưng bản mới chuyển thành `prod|sftp-v2|...`. Với MetadataStore, đó là **hai namespace khác nhau**. Bộ lọc mới có thể không nhìn thấy những file đã ghi nhận trước đó.

Do đó, khi đổi prefix, cấu trúc đường dẫn, adapter version hoặc collection, cần kế hoạch:

1. Chụp backup trạng thái metadata.
2. Xác định key format cũ và mới.
3. Thử trên database clone với file đã nhận/chưa nhận.
4. Chạy migration/compatibility policy có kiểm soát.
5. Theo dõi duplicate/replay sau rollout.
6. Không xóa metadata cũ ngay khi chưa xác minh kết quả.

## 14. Lỗi, retry và khôi phục sau crash

### 14.1. Các ranh giới trong workflow

Một pipeline SFTP → MongoDB metadata → Kafka có thể có các mốc:

~~~text
A. SFTP file xuất hiện
B. Persistent filter đặt marker "đã thấy"
C. File được tải về local
D. File Message được tạo trên MessageChannel
E. Handler parse/validate thành order events
F. Kafka hoặc database đích xác nhận ghi
G. Business trạng thái hoàn tất và ACK theo hợp đồng
~~~

Marker ở bước **B** không chứng minh **F/G** đã thành công. Nếu process crash giữa B và G, phải có cơ chế recovery: file local còn được scan, business checkpoint, requeue, reset filter có kiểm soát, hoặc idempotent downstream xử lý lại an toàn.

### 14.2. Bảng failure modes

| Lỗi | Tình huống | Điều cần thiết kế |
|---|---|---|
| MongoDB unavailable | `putIfAbsent`/`replace` ném exception | Fail closed hoặc retry có giới hạn; không mặc định cho qua filter |
| Network timeout khi ghi metadata | Không rõ server đã ghi chưa | Đọc lại key/cần cùng key để reconcile, không tự dùng key mới |
| Key đã ghi, download thất bại | File chưa tải đủ | Remote filter rollback theo contract khi hỗ trợ; test thực tế |
| Key đã ghi, handler thất bại | Downstream chưa commit | Replay/recovery, tránh at-most-once ngoài ý muốn |
| Message đã gửi, ACK thất lạc | Đích có thể đã xử lý | Event ID ổn định, idempotent downstream |
| Worker A chết sau claim | Key PROCESSING bị kẹt | Lease/owner/expiry hoặc recovery job |
| Worker A sống lại sau hết lease | Chủ cũ vẫn chạy | Fencing/version check trước side effect |
| Hai worker chọn cùng file | Cạnh tranh nguồn | Dùng chung metadata store, prefix và atomic key |
| MongoDB failover | Có I/O errors/write concern uncertainty | Retry budget, consistency và kiểm tra topology |
| Metadata collection bị xóa | Mất trạng thái seen | Backup/restore, hạn chế quyền delete, có kế hoạch replay |
| Đổi prefix/filter version | Không nhận ra state cũ | Migration và test restart |
| Lượng keys tăng mạnh | Storage/index lớn | Retention có kiểm soát và metrics |

### 14.3. Chính sách fail-open hay fail-closed?

Nếu MetadataStore không truy cập được:

- **Fail-open**: vẫn cho message đi tiếp dù không kiểm tra dedup; có thể tạo duplicate/side effect trùng.
- **Fail-closed**: từ chối hoặc tạm dừng nhận message mới; giảm nguy cơ duplicate nhưng ảnh hưởng availability.

Không có một lựa chọn đúng cho mọi workload. Với các nghiệp vụ có nguy cơ tính phí/gửi lệnh trùng, **fail-closed hoặc durable retry** thường đáng cân nhắc hơn. Nếu nguồn bền và downstream idempotent, có thể có phương án khác.

**Tránh bắt `Exception` rồi coi là “không có key”.** MetadataStore `get(key)==null` và MongoDB không phản hồi là **hai trạng thái hoàn toàn khác nhau**.

## 15. Transaction, CAS, lease và exactly-once

### 15.1. CAS chỉ bảo đảm trạng thái metadata theo một khóa

Một CAS:

~~~java
boolean advanced = store.replace(
        "event|evt-101",
        "PROCESSING:worker-a",
        "DONE");
~~~

chỉ thành công nếu key đang có đúng giá trị cũ. Nó không:

- Commit Kafka offset.
- Gửi HTTP request rồi chờ ACK.
- Đánh dấu một file SFTP đã được xóa khỏi server.
- Tạo transaction giữa MongoDB và JMS.
- Bảo đảm chỉ một lần business side effect ở một hệ thống khác.

### 15.2. Tại sao remove sau exception nguy hiểm?

Giả sử worker A ghi marker `PROCESSING:A` rồi pause lâu. Worker B dùng một protocol lease hợp lệ thu hồi ownership thành `PROCESSING:B`. Nếu A tỉnh dậy và gọi `remove(key)` không điều kiện, A sẽ **xóa key của B**.

Vì `MetadataStore.remove(key)` không nhận expected value, phải tránh dùng làm “release lock theo owner” cho protocol phức tạp. Hãy thiết kế biến thể dùng transaction/document conditional delete phù hợp hoặc một lock service chuyên dụng có fencing nếu cần.

### 15.3. Khi cần MongoDB transaction

Nếu nghiệp vụ cần cập nhật nhiều document MongoDB atomically, cần MongoDB topology hỗ trợ và `MongoTransactionManager` với transaction boundary đúng. Một `MongoDbMetadataStore` tự thân **không tạo transaction bao trùm business collection, broker hoặc HTTP** chỉ vì cùng sử dụng MongoDB.

Ngay cả MongoDB multi-document transaction cũng không tự tạo distributed exactly-once với SFTP, Kafka/JMS, HTTP hay file system. Khi cần bền vững xuyên hệ thống, cân nhắc **outbox, durable inbox, idempotent consumer, state machine và reconciliation**.

## 16. Kiểm thử API cơ bản với MongoDB thật

### 16.1. Bài test get/put/replace/remove và restart

Dùng MongoDB **test instance riêng** hoặc Testcontainers khi runner có Docker. Ví dụ JUnit 5 với Spring Boot Test và database test:

~~~java
package example.mongodb;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.integration.mongodb.metadata.MongoDbMetadataStore;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoDbMetadataStoreIT {

    @Autowired
    MongoDatabaseFactory mongoDatabaseFactory;

    @Test
    void survivesRecreatingStoreObject() {
        String key = "it|metadata|" + UUID.randomUUID();

        MongoDbMetadataStore first = new MongoDbMetadataStore(
                mongoDatabaseFactory, "integration_metadata_test");
        MongoDbMetadataStore second = new MongoDbMetadataStore(
                mongoDatabaseFactory, "integration_metadata_test");

        try {
            assertNull(first.get(key));

            assertNull(first.putIfAbsent(key, "SEEN"));
            assertEquals("SEEN", second.get(key));

            assertEquals("SEEN",
                    second.putIfAbsent(key, "OTHER"));

            assertFalse(second.replace(
                    key, "WRONG", "DONE"));

            assertTrue(second.replace(
                    key, "SEEN", "DONE"));

            assertEquals("DONE", first.get(key));
            assertEquals("DONE", first.remove(key));
            assertNull(second.get(key));
        } finally {
            first.remove(key);
        }
    }
}
~~~

Bài test tạo **hai object store dùng cùng MongoDB collection**; nó chứng minh state không nằm riêng trong bộ nhớ của object Java đầu tiên. Test này **chưa tự chứng minh qua process restart thật**; bài thực hành bổ sung sẽ tắt/mở Spring context hoặc app và đọc lại key.

**Không chạy với production database** vì test ghi/xóa metadata. Chỉ cleanup key có prefix/UUID của chính bài test.

### 16.2. Test hai worker tranh cùng một key

Có thể chạy hai thread dùng hai object store trên cùng database:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.junit.jupiter.api.Assertions.*;

void assertOneWinner(
        MongoDbMetadataStore storeA,
        MongoDbMetadataStore storeB,
        String key) throws Exception {

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch gate = new CountDownLatch(1);

    try {
        Future<String> a = pool.submit(() -> {
            gate.await();
            return storeA.putIfAbsent(key, "A");
        });

        Future<String> b = pool.submit(() -> {
            gate.await();
            return storeB.putIfAbsent(key, "B");
        });

        gate.countDown();

        int winners = (a.get() == null ? 1 : 0)
                    + (b.get() == null ? 1 : 0);

        assertEquals(1, winners);
    } finally {
        pool.shutdownNow();
    }
}
~~~

Đoạn này là **helper method**, không phải toàn bộ test class. Test phải dùng **key chưa tồn tại** và xóa đúng key sau khi hoàn thành; nếu key tồn tại trước test, cả hai call có thể trả giá trị cũ, không ai thắng. Nếu hệ thống runner không cho phép tạo thread hoặc MongoDB đang bị gián đoạn, cần phân tích test failure thay vì tuyên bố mất tính nguyên tử của store ngay.

### 16.3. Test putIfAbsent khác put

Trong một test riêng:

~~~java
store.put("it|cursor|123", "100");
assertEquals("100", store.get("it|cursor|123"));

store.put("it|cursor|123", "90");
assertEquals("90", store.get("it|cursor|123"));
~~~

Điều đó minh họa `put` có thể ghi đè giá trị và làm checkpoint lùi nếu ứng dụng không bảo vệ. **Không dùng literal key cố định trong test chạy song song**; thêm UUID/prefix để tránh đụng dữ liệu test khác.

## 17. Kiểm thử persistent file filter và restart

### 17.1. Test filter trên một file local

Với `FileSystemPersistentAcceptOnceFileListFilter`, có thể tạo file tạm có đường dẫn duy nhất trong **thư mục test** và kiểm tra:

1. Filter A chấp nhận file lần đầu.
2. Filter A từ chối file lần hai khi mtime không đổi.
3. Tạo **filter B** mới dùng cùng MongoDbMetadataStore collection/prefix.
4. Filter B vẫn từ chối file: chứng minh marker lưu bền qua đối tượng filter.
5. Thay đổi modified time theo cách có kiểm soát.
6. Xác minh filter xử lý file đã sửa theo contract phiên bản.
7. Gọi API reset filter hoặc cleanup **chỉ key test** khi thật sự cần.
8. Khởi động app process mới và chạy lại để kiểm tra persistence thực tế.

Nếu filter bị cấu hình nhầm `SimpleMetadataStore`, test restart có thể fail vì marker không được lưu ở MongoDB.

### 17.2. Test SFTP remote và local filters độc lập

Dùng SFTP test server và MongoDB test instance:

- Seed file trên remote với đường dẫn/mtime ổn định.
- Xác nhận một instance tải file, instance khác chia sẻ remote metadata không tải lại một file chưa thay đổi theo expected behavior.
- Xác nhận local filter không phát lại file đã xử lý trên restart khi dùng persistent store.
- Thử file tải dang dở rồi thất bại: quan sát rollback remote filter nếu implementation hỗ trợ.
- Thử lỗi handler **sau khi tải hoàn tất**: không mặc định marker bị xóa.
- Thay mtime remote để xem file có thể được xem là thay đổi.
- Thử hai file cùng tên ở hai thư mục, đặc biệt khi nâng lên Spring Integration 7.x.
- Kiểm tra prefix remote/local không trùng và hai instance cùng dùng một key scheme.
- Nếu dùng `maxFetchSize`, kiểm tra tác động khi nhiều instance cùng scan remote directory.

**Kết quả chấp nhận file một lần không chứng minh business ACK đã hoàn tất**. Test phải đo cả trạng thái filter và dữ liệu thực sự được commit xuống Kafka/DB đích.

## 18. Quan sát và quản lý metadata collection

Những metric gợi ý (không mặc định Spring Integration xuất đúng tên này):

| Metric | Mục đích |
|---|---|
| `metadata_get_total` | Số lần đọc state |
| `metadata_put_if_absent_total` | Số lần thử nhận key mới |
| `metadata_put_if_absent_won_total` | Số lần chèn thành công |
| `metadata_duplicate_detected_total` | Số lần key đã tồn tại |
| `metadata_cas_conflicts_total` | Số replace thất bại do khác giá trị |
| `metadata_operation_latency_seconds` | Độ trễ MongoDB metadata IO |
| `metadata_operation_errors_total` | Lỗi query/write/auth/network |
| `metadata_collection_documents` | Số entry và xu hướng tăng trưởng |
| `metadata_expired_or_removed_total` | Retention/recovery cleanup |
| `file_remote_fetch_failures_total` | Lỗi tải remote file |
| `file_downstream_processing_errors_total` | Lỗi sau khi file được nhận |
| `idempotent_rejected_total` | Số duplicate bị chặn |
| `business_committed_total` | Số sự kiện nghiệp vụ thật sự hoàn tất |

**Phân biệt:** số metadata markers, số File Messages được phát, số event từ file và số business transactions thành công có thể rất khác nhau.

### 18.1. Dung lượng và index

Vì metadata được lưu trong collection MongoDB, cần theo dõi số document, kích thước index và thời gian truy cập key. Tài liệu API không yêu cầu người dùng tự đoán schema rồi tạo index tùy tiện. Nếu cần tối ưu, kiểm tra collection thực tế do phiên bản triển khai tạo ra, đánh giá query plan/index hiện có và lập kế hoạch migration.

Với key namespace ổn định, retention hợp lý, backup và MongoDB monitoring, MetadataStore có thể vận hành lâu dài mà không cần sửa tay hàng loạt metadata.

### 18.2. Read/write concern và failover

Atomic operation của MongoDB không đồng nghĩa toàn bộ khả năng giữ dữ liệu qua failover đều giống nhau ở mọi **write concern/read concern**. Nếu metadata dùng để ngăn side effect trùng trên nhiều node, cần đánh giá topology replica set, cấu hình write concern phù hợp, timeout và tình huống response bị mất.

Khi kết quả một write không rõ, **dùng lại đúng key** và reconcile trạng thái thay vì tạo key mới theo attempt. Không “thử chạy tiếp” với một local in-memory metadata store trừ khi chấp nhận nguy cơ duplicate.

### 18.3. Backup, restore và thay đổi version

Backup metadata cùng các checkpoint nghiệp vụ liên quan. Khi restore dữ liệu business đến một thời điểm khác nhưng metadata đến thời điểm mới hơn/cũ hơn, có thể xảy ra:

- **Metadata quá mới:** file/event chưa thực sự commit trong restore nhưng bị coi là đã thấy.
- **Metadata quá cũ:** file/event đã commit nhưng bị xử lý lại.

Vì thế cần **kế hoạch khôi phục nhất quán**, kiểm tra replay và idempotency. Không coi metadata backup độc lập là đủ để phục hồi toàn pipeline.

## 19. Bảo mật MongoDB metadata store

- Dùng **least privilege**: tài khoản có quyền cần thiết trên **collection metadata**, không mặc nhiên có quyền đọc/ghi mọi collection nghiệp vụ.
- Đặt URI/credentials trong secret manager/biến môi trường; bật TLS khi phù hợp.
- Không đặt token, mật khẩu, thông tin nhạy cảm hoặc payload cá nhân vào metadata key/value.
- Đừng log toàn bộ key nếu path/tenant ID của khách hàng là dữ liệu nhạy cảm; có thể dùng hash/ẩn một phần.
- Tránh cho client HTTP/Kafka/SFTP tự điều khiển prefix/key namespace để chiếm khóa của người khác.
- Có chính sách backup/retention/audit và phân quyền **delete/drop collection** nghiêm ngặt.
- Giới hạn số lượng keys một request có thể tạo; chống metadata cardinality explosion.
- Đặt timeout/circuit breaker/retry budget cho MongoDB metadata IO, tránh nghẽn toàn bộ poller.
- Nếu dùng nhiều tenant, kiểm tra xem một shared metadata collection có đáp ứng yêu cầu tenant isolation hay phải tách factory/database theo quyền truy cập.
- Đảm bảo monitoring không có label theo từng key/file/event ID gây cardinality quá lớn.

**Không hiểu “dùng MongoDB” là “mặc định an toàn”.** Tính an toàn còn phụ thuộc roles, dữ liệu trong key/value, đường đi của credentials và quy trình khôi phục.

## 20. Những lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Restart xong file bị nhận lại | Filter vẫn dùng SimpleMetadataStore | Inject persistent store, test restart |
| Hai instance vẫn tải trùng | DB/collection/prefix khác nhau | So sánh config store của hai instance |
| Filter remote nhận đúng nhưng local phát lại | Remote và local dùng metadata khác hoặc local không bền | Kiểm tra cả hai filters |
| Filter chặn file chưa xử lý xong | Marker được đặt trước downstream commit | Recovery/replay theo contract |
| `putIfAbsent` luôn trả giá trị cũ | Key đã tồn tại, có thể do lần chạy trước | Kiểm tra state bằng get và namespace |
| `replace` luôn false | oldValue sai hoặc key đã đổi | Readback current value, xử lý CAS conflict |
| Xóa key xong duplicate xuất hiện | Removal làm file/event eligible trở lại | Chỉ cleanup theo quy trình |
| Key va chạm giữa hai flow | Prefix thiếu namespace | Thiết kế prefix theo environment/flow |
| Nâng phiên bản SFTP rồi tải lại | Key format/filter behavior thay đổi | Migration plan, test file path |
| MongoDB down làm poller lỗi | Metadata IO cần MongoDB | Health/error channel/retry budget |
| MongoTemplate bean ambiguities | Có nhiều DB beans chưa qualifier | @Qualifier và factory đúng database |
| App start nhưng lần poll đầu fail | Driver có thể kết nối/lỗi khi IO | Readiness/timeout và observability |
| Metadata collection tăng vô hạn | Không có retention chính sách | Ước tính growth, cleanup có kiểm soát |
| Dedup chặn event đã fail | Selector đặt marker trước business completion | State machine/lease/reconciliation |
| Idempotent advice vẫn gọi handler với duplicate | Chưa cấu hình discard/error | Kiểm tra duplicateMessage, setDiscardChannel |
| MetadataStore được khai báo nhưng MongoDB inbound vẫn đọc lặp | Source không tự dùng metadata | Thiết kế state/claim trong nguồn hoặc selector |
| Business record và metadata restore không khớp | Backup/restore không nhất quán | Replay và idempotency |
| Processor A xóa marker của B | remove không CAS | Không dùng remove làm release owner |

Trình tự khoanh vùng:

~~~text
Inbound file / message
  -> Filter hoặc MetadataStoreSelector
  -> key/value namespace
  -> MongoDbMetadataStore
  -> MongoDatabaseFactory / MongoTemplate
  -> MongoDB collection / driver
  -> MessageChannel / handler
  -> business commit / ACK
~~~

Đặt log/metric để phân biệt **metadata write success** với **business handler success**.

## 21. Bài thực hành tổng hợp

Xây một pipeline **SFTP/File → Spring Integration → Kafka/DB**, dùng MongoDB để lưu trạng thái accept-once.

### Phần A — MetadataStore cơ bản

1. Tạo database `integration_lab` và cấu hình MongoDB local/test.
2. Tạo bean `ConcurrentMetadataStore` bằng `MongoDbMetadataStore(mongoDatabaseFactory, "integration_metadata")`.
3. Gọi `get` trước khi ghi, `putIfAbsent` hai lần, kiểm tra giá trị trả về.
4. Gọi `replace(key, old, new)` với oldValue đúng và sai, so sánh boolean.
5. Dùng `remove` cho một key test, xác minh lần `putIfAbsent` tiếp theo có thể thành công.
6. Tạo thêm một object store từ cùng factory/collection và xác minh nó thấy cùng key.
7. Không dùng trực tiếp một MongoDB collection nghiệp vụ để lưu metadata.

### Phần B — File và SFTP accept-once

1. Tạo `FileSystemPersistentAcceptOnceFileListFilter` với prefix riêng.
2. Gắn vào `FileReadingMessageSource`, thiết lập poller và File Message consumer.
3. Đưa một file vào thư mục lab, xác minh chỉ phát một lần trong các poll liên tiếp khi file không đổi.
4. Restart process, xác minh filter vẫn nhớ file qua MongoDB.
5. Cấu hình SFTP remote filter bằng `SftpPersistentAcceptOnceFileListFilter` với cùng store nhưng prefix khác.
6. Thử failure lúc download và failure lúc downstream, giải thích khác biệt của rollback.
7. Tạo hai file tên giống nhau ở hai thư mục và kiểm tra key theo phiên bản framework.
8. Chạy hai instance cùng một shared collection/prefix, xác minh chỉ một instance nhận key theo contract filter.

### Phần C — Idempotent Receiver

1. Tạo `BusinessEvent(tenantId, eventId, type)` có ID ổn định.
2. Tạo `MetadataStoreSelector` với key gồm môi trường, tenant, event ID.
3. Gắn `IdempotentReceiverInterceptor`, cấu hình discard channel và đo số duplicate bị loại.
4. Gửi hai messages cùng eventId nhưng UUID Spring Message khác, xác minh selector vẫn nhận diện duplicate.
5. Mô phỏng handler lỗi sau khi key đã lưu, thảo luận rủi ro mất retry.
6. Thiết kế state machine PROCESSING → DONE → RETRY có lease/owner nếu nghiệp vụ yêu cầu.
7. Thử timeout khi ghi metadata nhưng key có thể đã được tạo; dùng get/readback trước retry.

### Phần D — Production hardening

1. Thiết kế retention khi có hàng triệu metadata keys mỗi ngày.
2. Kiểm tra quyền MongoDB cần cho collection metadata và tách secret khỏi code.
3. Chọn write concern phù hợp và thử failover trên môi trường test.
4. Xây metric metadata putIfAbsent thắng/thua, CAS conflict, latency, errors và business success.
5. Thực hành đổi prefix trên database clone và đo duplicate/replay.
6. Thiết kế restore plan khi metadata snapshot và business dataset không cùng thời điểm.
7. So sánh MongoDbMetadataStore với MongoDbMessageStore, queue broker và atomic claim MongoDB.

**Câu hỏi tự đánh giá:**

- `MetadataStore` khác `MessageStore` ở điểm nào?
- Vì sao `SimpleMetadataStore` có thể gây duplicate sau restart?
- Constructor `MongoDbMetadataStore` nhận những kiểu bean nào?
- Tên bean `metadataStore` có làm mọi adapter tự động sử dụng nó không?
- `putIfAbsent` trả gì khi chèn thành công và khi khóa đã có?
- Vì sao `get + put` có race khi nhiều instance?
- `replace(key, old, new)` giúp bảo đảm gì và không bảo đảm gì?
- Vì sao không nên dùng `remove(key)` như một compare-and-delete có owner?
- File persistent accept-once filter khác hash-based dedup thế nào?
- SFTP inbound có bao nhiêu tầng file filters và trách nhiệm từng tầng?
- Marker “file seen” có chứng minh dữ liệu Kafka đã commit không?
- Nếu IdempotentReceiverInterceptor không cấu hình discard, duplicate có nhất thiết bị loại không?
- Vì sao event dedup key cần dựa trên business ID thay vì Spring Message UUID?
- Vì sao chỉ đăng ký MetadataStore không làm MongoDbMessageSource tự bỏ qua document NEW đã poll?
- Khi nâng Spring Integration major version, điều gì có thể thay đổi trong filter key?
- Dùng TTL index không có kế hoạch có thể gây rủi ro gì?
- Sau MongoDB failover, nếu write result không rõ thì nên dùng lại khóa cũ hay tạo khóa mới?

## 22. Tài liệu tham khảo

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): mục MongoDB Metadata Store, kết nối MongoDatabaseFactory, Message Store và adapters.
- [Spring Integration API — MongoDbMetadataStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/metadata/MongoDbMetadataStore.html): constructors, get/put/remove/putIfAbsent/replace.
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): generic key/value state, persistent stores và tìm bean metadataStore.
- [Spring Integration API — ConcurrentMetadataStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html): hợp đồng atomic putIfAbsent/replace.
- [Spring Integration Reference — SFTP Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/sftp/inbound.html): remote/local filters và xử lý failure.
- [Spring Integration Reference — Remote Persistent File List Filters](https://docs.spring.io/spring-integration/reference/file/remote-persistent-flf.html): key format, rollback/re-fetch và shared metadata.
- [Spring Integration API — FileSystemPersistentAcceptOnceFileListFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/file/filters/FileSystemPersistentAcceptOnceFileListFilter.html): constructor nhận ConcurrentMetadataStore và prefix.
- [Spring Integration API — SftpPersistentAcceptOnceFileListFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/sftp/filters/SftpPersistentAcceptOnceFileListFilter.html): remote file metadata filter.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): MetadataStoreSelector, interceptor, discard và duplicateMessage header.
- [Spring Integration API — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): key/value strategy, compareValues và accept().
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, MongoDatabaseFactory, transaction, driver consistency.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) và [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): cấu hình consistency và durability.

## Kết luận

**`MongoDbMetadataStore` là một implementation bền của `ConcurrentMetadataStore`**, giúp các thành phần Spring Integration lưu và chia sẻ metadata key/value giữa những lần khởi động và giữa nhiều application instances. Các operation **`putIfAbsent` và `replace`** hỗ trợ cập nhật nguyên tử theo key, hữu ích cho persistent accept-once filters của File/SFTP/FTP và cho Idempotent Receiver.

Trong **SPRING_INTEGRATION_ADAPTERS**, MetadataStore là **trạng thái điều phối**, không phải `MessageChannel`, `MessageStore` hay cơ sở dữ liệu nghiệp vụ. Thiết kế đúng cần chọn chung MongoDB database/collection, key namespace ổn định, filter/selector wiring tường minh, policy xử lý lỗi/retry và retention có kiểm soát. **Một marker “đã thấy” không đồng nghĩa dữ liệu đã xử lý thành công**: với workflow không được mất hoặc xử lý trùng, vẫn phải thiết kế commit/ACK, lease/claim, idempotency, recovery và vận hành xuyên các hệ thống.
