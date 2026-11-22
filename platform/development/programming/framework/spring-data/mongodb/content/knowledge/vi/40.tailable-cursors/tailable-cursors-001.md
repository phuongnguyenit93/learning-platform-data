# Collection giới hạn dung lượng (capped collection) và cursor chờ dữ liệu mới

## 1. Bài toán: theo dõi một dòng bản ghi được ghi liên tục

Giả sử dịch vụ thanh toán ghi bản tin kỹ thuật mỗi khi thực hiện một bước xử lý: nhận yêu cầu, gọi cổng thanh toán, nhận phản hồi, hoàn tất. Một màn hình vận hành muốn hiển thị những bản tin mới ngay khi chúng xuất hiện, gần giống lệnh `tail -f` trên Linux. Nếu truy vấn `find()` thông thường, ứng dụng nhận hết các document tại thời điểm đọc và cursor sẽ kết thúc. Muốn thấy dữ liệu mới, ứng dụng phải tự truy vấn lại.

MongoDB có một cặp cơ chế giải quyết trường hợp này:

- **Capped collection**: collection có giới hạn dung lượng, được quản lý như bộ đệm vòng; khi đầy, bản ghi cũ được loại khỏi tập dữ liệu để nhường chỗ cho bản ghi mới.
- **Tailable cursor**: cursor dành cho capped collection, có thể tiếp tục đứng ở cuối dữ liệu và đọc những document được **insert** về sau.
- **`awaitData`**: tùy chọn để thao tác `getMore` đợi một khoảng thời gian khi chưa có document mới, thay vì liên tục trả về các đợt dữ liệu rỗng.

Trong module **SPRING_DATA_MONGODB**, Spring Data MongoDB giúp tạo capped collection qua `MongoTemplate`, mở luồng bằng `ReactiveMongoTemplate.tail(...)` hoặc repository gắn `@Tailable`, và tích hợp vòng đời listener vào ứng dụng Spring.

~~~text
Writer A -----------+
                    |
Writer B -------+   v
                +--> capped collection: [E97][E98][E99][E100]
                    |                        ^         ^
                    |                        |         |
                    +--> tailable cursor ----+---------+--> chờ insert E101
                                                              |
Writer C -------------------------------------- insert E101 ---+
                                                              |
                                                     nhận E101 và tiếp tục chờ
~~~

Mục tiêu của bài:

1. Phân biệt giới hạn theo **byte** và theo **số document**, hiểu cơ chế loại bản ghi cũ cùng hệ quả với lưu trữ.
2. Tạo, kiểm tra và ghi dữ liệu vào capped collection bằng `mongosh` và Spring Data MongoDB.
3. Giải thích sự khác nhau giữa cursor thường, `tailable` và `tailable + awaitData`.
4. Xây một consumer Spring Data reactive theo dõi document mới, chủ động hủy subscription và nhận biết stream kết thúc/lỗi.
5. Nhận diện trường hợp cursor bị đóng, dữ liệu bị ghi đè trước khi đọc, và chọn cơ chế phù hợp nếu cần khôi phục không mất dữ liệu.

## 2. Capped collection hoạt động như bộ đệm vòng

### 2.1. Giới hạn dung lượng

Khi tạo collection, ta khai báo:

| Tùy chọn MongoDB | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `capped: true` | Có, để tạo loại capped | Bật cấu trúc collection có giới hạn dung lượng |
| `size` | Có | Giới hạn kích thước collection theo **byte**; phải lớn hơn 0 |
| `max` | Không | Số document tối đa được giữ lại; không thay thế yêu cầu có `size` |

MongoDB sử dụng giới hạn dung lượng và, nếu có, giới hạn số document để quyết định lúc nào bản ghi cũ phải nhường chỗ. Vì kích thước mỗi document khác nhau, **`size: 5 MiB` không tương đương với 5.000 bản ghi**, kể cả khi cấu hình thêm `max: 5000`.

Ví dụ một collection tối đa 5 MiB và 5.000 bản ghi:

~~~javascript
use tail_demo

db.createCollection("activity_log", {
  capped: true,
  size: 5 * 1024 * 1024,
  max: 5000
})
~~~

Collection trên có thể bắt đầu loại bản ghi cũ **trước khi** đạt 5.000 document nếu dung lượng byte đã chạm ngưỡng. Tương tự, nếu đạt 5.000 document trước ngưỡng byte thì giới hạn số bản ghi được áp dụng.

Capped collection không giống một bảng lịch sử lưu trữ mãi mãi: khi bộ đệm quay vòng, bản ghi cũ đã bị loại khỏi nguồn dữ liệu. Nếu nhiều người ghi đồng thời, MongoDB cũng **không bảo đảm thứ tự trả về trùng tuyệt đối với thứ tự các lệnh insert từ các client**.

### 2.2. Những gì được giữ và những gì mất

~~~text
Dung lượng còn trống:
[E1][E2][E3][      ][      ]

Sau nhiều lần insert:
[E1][E2][E3][E4][E5]

Thêm E6 khi đã chạm ngưỡng:
[E2][E3][E4][E5][E6]
 ^ E1 không còn trong collection
~~~

Sơ đồ chỉ mô tả *logic* bộ đệm vòng; đây không phải bản đồ vị trí vật lý của byte trên ổ đĩa. Không suy ra rằng MongoDB luôn xóa chính xác một document cho mỗi lần insert: số document bị loại phụ thuộc kích thước và ngưỡng thực tế.

Có ba hệ quả quan trọng:

- **Retention được quyết định bởi sức chứa và tốc độ ghi**, không phải bởi một thời hạn đảm bảo. Một đợt ghi đột biến có thể khiến dữ liệu chỉ còn vài phút thay vì vài giờ.
- **Consumer chậm có thể mất vị trí đọc.** Khi bản ghi tại vị trí cursor trỏ tới đã bị ghi đè, tailable cursor có thể trở nên vô hiệu.
- **Không có lịch sử vô hạn để phát lại.** Một bản ghi đã bị loại khỏi capped collection sẽ không thể lấy lại từ chính collection đó.

### 2.3. Ràng buộc thiết kế

Theo các giới hạn MongoDB, cần lưu ý:

- Capped collection **không thể sharding**.
- Không thực hiện **write vào capped collection trong transaction**; không dùng `$out` để ghi kết quả vào đó.
- Capped collection không phải lựa chọn tốt cho CRUD thông thường cần xóa tùy ý hay cập nhật kích thước document. Nên xem mỗi document là bản ghi **append-only** và tránh cập nhật làm document phình to.
- Collection phải được **tạo tường minh dưới dạng capped**. Nếu chương trình vô tình insert trước vào tên collection chưa tồn tại, MongoDB có thể tạo collection thường; khi đó truy vấn tailable sẽ không chạy như mong đợi.
- Capped collection không phải queue có ACK, transaction consumption hoặc consumer group. Mỗi subscriber đọc độc lập; MongoDB không tự phân chia công việc giữa các subscriber.

Với dữ liệu cần xóa theo thời gian, truy vấn trên index, thay đổi trạng thái hoặc phân vùng theo shard, một **collection thường + TTL index** hoặc cơ chế khác có thể phù hợp hơn.

## 3. Tạo và kiểm tra capped collection bằng mongosh

Dùng MongoDB local hoặc một deployment cho phép tạo collection, rồi chạy:

~~~javascript
use tail_demo

// Chỉ tạo khi chưa có collection tên này:
db.createCollection("activity_log", {
  capped: true,
  size: 5242880,
  max: 5000
})

// Phải trả true:
db.activity_log.isCapped()

// Xem options đã khai báo:
db.getCollectionInfos({ name: "activity_log" })

// Một bản ghi hạt giống để cursor có dữ liệu lúc mở:
db.activity_log.insertOne({
  source: "bootstrap",
  level: "INFO",
  message: "Collection is ready",
  createdAt: new Date()
})
~~~

Khi chạy lại ví dụ, bỏ qua lệnh `createCollection` nếu collection đã tồn tại. Không xóa dữ liệu thật chỉ để chạy lại ví dụ. Muốn kiểm tra dung lượng và số bản ghi hiện tại:

~~~javascript
db.activity_log.stats()

db.activity_log.find()
  .sort({ $natural: -1 })
  .limit(5)
~~~

`$natural: -1` cho phép xem các document gần cuối collection trước. Để quan sát trật tự tự nhiên theo chiều đọc tailable, có thể dùng `$natural: 1`. Đây là thứ tự lưu trữ tự nhiên, **không phải cam kết sắp xếp theo `createdAt`, `_id` hoặc thứ tự toàn cục của nhiều client**.

### 3.1. Tạo collection từ Spring Data MongoDB

Nếu cấu hình schema bằng Java, gọi `MongoTemplate` trong bước khởi tạo được quản lý (migration/bootstrap) **trước khi writer và consumer hoạt động**:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.CollectionOptions;

public final class ActivityLogSchema {
    private static final String COLLECTION = "activity_log";

    private ActivityLogSchema() {}

    public static void createForFreshDatabase(MongoTemplate mongoTemplate) {
        if (mongoTemplate.collectionExists(COLLECTION)) {
            // Không coi "đã tồn tại" là bằng chứng collection là capped.
            // Kiểm tra thực tế qua isCapped() hoặc listCollections options.
            return;
        }

        mongoTemplate.createCollection(
            COLLECTION,
            CollectionOptions.empty()
                .capped()
                .size(5L * 1024 * 1024)
                .maxDocuments(5000)
        );
    }
}
~~~

Ví dụ trên minh họa API `CollectionOptions.empty().capped().size(...).maxDocuments(...)`. Trong ứng dụng có nhiều instance, hãy để migration do **một tiến trình điều phối** chịu trách nhiệm, xử lý trường hợp hai instance tạo đồng thời, và **fail fast** nếu collection đã tồn tại nhưng không phải capped. Tên collection cùng kiểu entity không tự biến một collection thường thành capped.

### 3.2. Đổi kích thước sau khi tạo

MongoDB hiện có các lệnh quản trị dành cho việc thay đổi giới hạn capped collection, chẳng hạn `collMod` với `cappedSize` hoặc `cappedMax` ở các phiên bản hỗ trợ. Đây là thao tác thay đổi sức chứa có khả năng loại bản ghi cũ; chỉ dùng sau khi kiểm tra phiên bản server và kế hoạch giữ dữ liệu. Đừng giả định đổi một thuộc tính trên Java entity là sẽ đổi được đặc tính collection đang tồn tại.

## 4. Cursor thường, tailable và awaitData

Một cursor thường được mở bằng `find()`, đọc các batch và kết thúc khi kết quả đã cạn. Dữ liệu được chèn sau đó **không** làm cursor thông thường tự mở lại.

Tailable cursor khác ở chỗ tiếp tục giữ vị trí cuối trong capped collection. Dù đã đọc hết các document hiện hữu, client có thể gọi `getMore` để nhận các document được insert tiếp theo.

~~~mermaid
flowchart TD
    A["Mở find trên capped collection"] --> B["Đọc các document hiện có"]
    B --> C{"Đã hết batch hiện tại?"}
    C -->|"Chưa"| B
    C -->|"Rồi, cursor thường"| D["Cursor kết thúc"]
    C -->|"Rồi, tailable"| E["Giữ cursor ở cuối"]
    E --> F{"Có insert mới?"}
    F -->|"Có"| G["getMore trả document mới"]
    G --> E
    F -->|"Chưa, awaitData"| H["getMore chờ tới khi có dữ liệu / hết thời hạn"]
    H --> E
~~~

| Cơ chế | Khi đọc hết dữ liệu hiện tại | Khi chưa có bản ghi mới | Mục đích |
| --- | --- | --- | --- |
| `find` thường | Cursor kết thúc | Không tự đợi | Truy vấn kết quả hữu hạn |
| `tailable` | Có thể tiếp tục giữ cursor | Client phải gọi `getMore` tiếp | Theo dõi insert trên capped collection |
| `tailable + awaitData` | Có thể tiếp tục giữ cursor | Server chờ một khoảng ngắn trong `getMore` | Theo dõi insert với ít lần hỏi rỗng |

**`awaitData` không hứa chờ vô hạn.** Nếu hết thời hạn chờ mà chưa có document, server có thể trả về **batch rỗng**, trong khi cursor vẫn còn sống. Vì vậy, `batch rỗng` không đồng nghĩa “đã hết stream”. Tầng driver hoặc Spring Data phải tiếp tục tương tác với cursor còn hợp lệ. Thời gian chờ có thể được cấu hình qua cơ chế `maxAwaitTimeMS` phù hợp với driver.

Tailable cursor **không dùng index** để thực hiện đường đọc của nó; về bản chất là quét theo natural order. Khi truy vấn có filter, quá trình quét ban đầu có thể tốn tài nguyên, và nếu không có document nào phù hợp tại thời điểm mở, stream có thể chết sớm. Với trường hợp đọc có điều kiện dựa trên index, MongoDB thường khuyến nghị cursor thường + ghi nhớ giá trị cuối để truy vấn tiếp.

### 4.1. Thử trực tiếp trong hai phiên mongosh

Ở cửa sổ A, sau khi đã tạo và seed collection:

~~~javascript
use tail_demo

const cursor = db.activity_log.find({})
  .tailable({ awaitData: true })
  .maxAwaitTimeMS(2000)

// Đọc thử document đang có:
if (cursor.hasNext()) {
  printjson(cursor.next())
}

// Gọi hasNext()/next() tiếp để quan sát document mới.
// Cần quản lý việc cursor còn mở, timeout và ngắt vòng lặp
// khi viết một vòng lặp theo dõi dài hạn.
~~~

Ở cửa sổ B:

~~~javascript
use tail_demo

db.activity_log.insertOne({
  source: "payments",
  level: "INFO",
  message: "Payment request accepted",
  createdAt: new Date()
})
~~~

Quay lại A và gọi `cursor.hasNext()` rồi `cursor.next()` để nhận bản ghi mới (nếu cursor còn hiệu lực). `hasNext()` có thể chờ trong một khoảng thời gian; một lần trả `false` do hết thời gian đợi chưa đủ để kết luận toàn bộ nguồn dữ liệu đã kết thúc. Với chương trình thực tế, ưu tiên để driver/Spring Data quản lý vòng nhận thay vì tạo vòng `while(true)` bận CPU.

## 5. Spring Data reactive: đọc luồng document bằng tail(...)

Ở Spring Data MongoDB, API chính là:

~~~java
Flux<T> tail(Query query, Class<T> entityClass, String collectionName);
~~~

Phương thức này nằm trên `ReactiveMongoOperations`/`ReactiveMongoTemplate`. Nó trả về `Flux<T>`; quá trình đọc bắt đầu khi có **subscription**. Trong ví dụ dưới đây, ta nhận thẳng `org.bson.Document` để tập trung vào cursor và tránh giả định về entity mapping.

Yêu cầu dự án: Spring Boot với **Spring Data MongoDB Reactive** (ví dụ starter `spring-boot-starter-data-mongodb-reactive`), kết nối tới database `tail_demo` và collection `activity_log` đã tạo đúng kiểu. Một cấu hình local điển hình:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/tail_demo
~~~

### 5.1. Consumer reactive có vòng đời rõ ràng

~~~java
import jakarta.annotation.PreDestroy;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Component
public class ActivityTailConsumer {
    private static final Logger log =
        LoggerFactory.getLogger(ActivityTailConsumer.class);

    private final ReactiveMongoTemplate mongoTemplate;
    private Disposable subscription;

    public ActivityTailConsumer(ReactiveMongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        Flux<Document> stream = mongoTemplate.tail(
            new Query(),
            Document.class,
            "activity_log"
        );

        subscription = stream.subscribe(
            event -> log.info(
                "Nguon={}, muc={}, noiDung={}",
                event.getString("source"),
                event.getString("level"),
                event.getString("message")
            ),
            error -> log.error("Tailable cursor gap loi", error),
            () -> log.warn("Tailable cursor da ket thuc")
        );
    }

    @PreDestroy
    public void stop() {
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
~~~

Điều cần đọc đúng từ đoạn code:

1. `new Query()` nghĩa là **không lọc document**; consumer sẽ nhận các document đang có trước, sau đó chờ document mới, với điều kiện cursor còn hiệu lực.
2. `tail(...)` tạo nguồn `Flux`, còn `subscribe(...)` mới đăng ký tiêu thụ. Nếu chỉ khai báo `Flux` rồi không subscribe, sẽ không có log nhận dữ liệu.
3. Lambda `error` ghi nhận stream bị lỗi; lambda `complete` ghi nhận stream đã kết thúc. **Đây chưa phải hệ thống tự khôi phục**.
4. `subscription.dispose()` khi ứng dụng dừng giúp đóng cursor/giải phóng tài nguyên. Không tạo một subscription mới cho mỗi HTTP request.
5. Đọc được document không có nghĩa một tác vụ phụ như ghi Elasticsearch, gửi email hay cập nhật database khác đã hoàn tất. Ví dụ chỉ log để minh họa nguồn dữ liệu.

Trong phần sản xuất, nếu handler là thao tác I/O không đồng bộ, ưu tiên xử lý dữ liệu bằng một pipeline `concatMap` hoặc cơ chế giới hạn concurrency phù hợp, tránh gọi `subscribe()` lồng trong `doOnNext`; cần theo dõi lỗi và mức độ chậm của handler.

### 5.2. Writer reactive để thử luồng

Một writer có thể dùng `ReactiveMongoTemplate.insert(...)` và trả về `Mono` cho caller subscribe hoặc chờ kết quả:

~~~java
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public final class ActivityLogWriter {
    private final ReactiveMongoTemplate mongoTemplate;

    public ActivityLogWriter(ReactiveMongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Mono<Document> append(String message) {
        Document event = new Document("source", "payments")
            .append("level", "INFO")
            .append("message", message)
            .append("createdAt", Date.from(Instant.now()));

        return mongoTemplate.insert(event, "activity_log");
    }
}
~~~

Caller có thể gọi `writer.append("Order received")` rồi **subscribe** trong luồng ứng dụng hoặc composition reactive thích hợp. Nếu chỉ gọi phương thức và bỏ qua `Mono` trả về, insert chưa được thực hiện. Ngoài ra, phải tạo capped collection trước khi writer hoạt động.

### 5.3. Có nên filter trực tiếp trong tail?

Ví dụ:

~~~java
import static org.springframework.data.mongodb.core.query.Criteria.where;

Query paymentsOnly = new Query(where("source").is("payments"));

Flux<Document> payments = mongoTemplate.tail(
    paymentsOnly,
    Document.class,
    "activity_log"
);
~~~

Lệnh lọc này hợp lệ về mặt biểu đạt nhưng có nhược điểm: nếu tại thời điểm mở không có bản ghi nào có `source = "payments"`, cursor có thể không duy trì được trạng thái chờ lâu dài. Nó cũng không tận dụng index theo cách một `find` thường làm.

Với log tổng hợp, một lựa chọn đơn giản là tail tất cả document rồi lọc ở consumer, khi lưu lượng đủ thấp và chấp nhận đọc thêm; còn với dữ liệu nhiều và cần truy vấn theo index, hãy xét **poll theo watermark** hoặc một cơ chế phát sự kiện phù hợp hơn.

## 6. Reactive repository và @Tailable

Nếu đã ánh xạ document thành domain type, Spring Data cho phép đánh dấu một query repository bằng `@Tailable`. Ví dụ tối giản cho một entity có getter/setter/constructor phù hợp:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.mongodb.repository.Tailable;
import org.bson.types.ObjectId;
import reactor.core.publisher.Flux;

@Document(collection = "activity_log")
public class ActivityEvent {
    @Id
    private ObjectId id;
    private String source;
    private String level;
    private String message;

    // Khai báo constructor và getters/setters theo quy ước mapping
    // của dự án; được lược bỏ ở đây để làm rõ repository.
}

public interface ActivityEventRepository
        extends ReactiveMongoRepository<ActivityEvent, ObjectId> {

    @Tailable
    Flux<ActivityEvent> findBySource(String source);
}
~~~

`@Tailable` chỉ có ý nghĩa cho phương thức trả nhiều phần tử, chẳng hạn `Flux<ActivityEvent>`. Nó không biến collection thường thành capped, không tự bảo đảm khôi phục khi cursor chết, và không phải cách để lấy một `Mono` kết quả đơn. Cũng như ví dụ `paymentsOnly`, truy vấn `findBySource(...)` có nguy cơ kết thúc khi không có bản ghi phù hợp lúc bắt đầu. Dùng repository khi mô hình entity rõ ràng; dùng `ReactiveMongoTemplate.tail(...)` khi cần kiểm soát query, collection name hoặc nhận tài liệu BSON thô.

## 7. Trường hợp chỉ có MongoTemplate đồng bộ

Spring Data MongoDB cũng hỗ trợ tailable cursor thông qua `MessageListenerContainer` cùng `TailableCursorRequest` khi ứng dụng dựa trên driver đồng bộ. Một listener đồng bộ cần task chạy lâu dài và tài nguyên thread, vì vậy ứng dụng có nhiều subscriber thường nên cân nhắc reactive trước.

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListener;
import org.springframework.data.mongodb.core.messaging.TailableCursorRequest;

public final class SyncTailExample {
    public static void run(MongoTemplate template) {
        DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer(template);

        MessageListener<Document, Document> listener =
            message -> System.out.println(message.getBody().toJson());

        TailableCursorRequest request = TailableCursorRequest.builder()
            .collection("activity_log")
            .publishTo(listener)
            .build();

        container.register(request, Document.class);
        container.start();

        // Ứng dụng thực: giữ container trong managed bean
        // và gọi container.stop() khi kết thúc vòng đời.
    }
}
~~~

Đoạn này chỉ minh họa cách đăng ký; **không** phải một chương trình đầy đủ tự dừng. Hãy giữ đối tượng `container` trong bean và gọi `container.stop()` khi shutdown. Listener không thay thế retry, checkpoint hoặc xử lý trùng lặp ở tầng nghiệp vụ.

## 8. Những tình huống stream dừng hoặc mất bản ghi

### 8.1. Collection trống hoặc query không khớp dữ liệu

Tailable cursor có thể bị đóng ngay nếu truy vấn lúc tạo không trả về document phù hợp. Đó là lý do bài thực hành đã **insert bản ghi seed trước khi subscribe**. Trong hệ thống thật, không thể luôn dựa vào một seed giả để đảm bảo mọi filter đều có match; cần thiết kế cách mở lại có kiểm soát và xem xét khả năng mất bản ghi trong khoảng gián đoạn.

~~~text
T0: capped collection trống
T1: consumer mở tail -> cursor không có kết quả ban đầu, có thể kết thúc
T2: writer insert E1
T3: consumer đã dừng nên không nhận E1
~~~

Một `Flux` kết thúc bình thường cũng cần được quan sát, không chỉ exception. Nếu chỉ triển khai `retryWhen(...)` cho **lỗi**, trường hợp completion im lặng có thể không được đăng ký lại; có thể cần cơ chế repeat/resubscribe có delay phù hợp. Tuy nhiên, **mở lại cursor không tự phục hồi bản ghi đã bị loại**.

### 8.2. Cursor bị vượt qua bởi bộ đệm vòng

~~~text
Consumer đọc tới E100
Writer tạo E101 ... E50000 rất nhanh
Collection nhỏ, E100 cùng các event liền sau đã bị loại
Consumer gọi getMore -> vị trí hiện tại có thể không còn hợp lệ
~~~

Không đặt tốc độ xử lý consumer thấp hơn tốc độ sinh event trong thời gian dài rồi kỳ vọng `awaitData` sửa được vấn đề. `awaitData` chỉ giúp chờ khi **chưa có** dữ liệu; nó không mở rộng sức chứa hay làm queue bền vững.

### 8.3. Mất kết nối, failover và restart

Cursor có vòng đời gắn với kết nối/session và trạng thái server. Khi quá trình ứng dụng dừng, kết nối bị ngắt, collection bị drop hoặc cursor bị invalidate, consumer cần mở lại và xác định khoảng thời gian bị bỏ lỡ.

**Tailable cursor không cung cấp resume token** như MongoDB Change Streams. Nếu cần hồi phục, phải tự thiết kế: document có định danh/số thứ tự sự kiện, lưu watermark xử lý, giữ nguồn lịch sử bền vững đủ lâu, và có đường **backfill/reconciliation** bằng một query thích hợp. Chỉ lưu `Instant.now()` lúc restart không thể chứng minh không bỏ sót sự kiện.

Đặc biệt, `ObjectId` thường giúp định danh document nhưng **không phải số thứ tự giao dịch chặt chẽ giữa nhiều writer**; không thể suy ra exactly-once hay total order chỉ bằng so sánh `_id`.

### 8.4. Subscriber chậm và backpressure

Dù `Flux` hỗ trợ backpressure, writer vẫn có thể tiếp tục insert vào capped collection. Subscriber chậm, handler chặn thread, buffer trong memory quá lớn hoặc pool kết nối bị thiếu đều làm tăng rủi ro cursor không theo kịp. Nếu bản ghi là sự kiện nghiệp vụ quan trọng, không sử dụng `onBackpressureDrop` như giải pháp tùy tiện: việc drop ở consumer là đánh mất dữ liệu được giao.

## 9. Lựa chọn cơ chế phù hợp với yêu cầu sản phẩm

| Yêu cầu | Capped + tailable cursor | Change stream | Query định kỳ / dữ liệu thường |
| --- | --- | --- | --- |
| Theo dõi **document mới được insert** | Phù hợp cho log/buffer hữu hạn | Có event insert cùng các loại thay đổi khác | Có thể dùng watermark |
| Theo dõi **update/delete** | Không phát sự kiện update/delete theo nghĩa CDC | Phù hợp | Cần thiết kế so sánh/tombstone |
| Lưu trữ dài hạn | Không phù hợp nếu bị ghi đè | Chỉ đọc lịch sử trong giới hạn oplog, không thay kho sự kiện | Tùy thiết kế retention |
| Điều kiện topology | Capped collection, có thể trên standalone | Cần replica set hoặc sharded cluster | Tùy query/database |
| Tiếp tục sau restart | Không có resume token | Có resume token với giới hạn lịch sử oplog | Tự quản watermark |
| Sharding collection nguồn | Capped không hỗ trợ sharding | Có thể watch collection phù hợp trong cluster | Collection thường có thể sharding |
| Giải quyết consumer group / exactly-once | Không | Không tự có | Không tự có |

Một số quyết định điển hình:

- **Bảng log kỹ thuật xem trực tiếp, chấp nhận mất dòng cũ**: capped collection + tailable cursor là cách triển khai gọn.
- **Đồng bộ search index khi order có insert, update, delete**: ưu tiên change stream nếu topology và yêu cầu khôi phục cho phép.
- **Lưu lịch sử audit/pháp lý lâu dài, phải tra cứu nhiều trường**: dùng collection thường có chính sách retention/index/backup; capped collection không phải nguồn sự thật duy nhất.
- **Hàng đợi xử lý đơn hàng bảo đảm retry/ACK, nhiều worker tranh việc**: cần thiết kế durable queue/outbox/broker và idempotency; tailable cursor chỉ là tín hiệu đọc.
- **Tra cứu theo thời gian hay bộ lọc index**: cursor thường với watermark có thể hiệu quả hơn việc quét natural order của tailable.

## 10. Ước tính sức chứa và quan sát vận hành

Nếu mỗi log document trung bình 800 byte, hệ thống nhận 200 document/giây, và muốn giữ khoảng 10 phút dữ liệu:

~~~text
200 doc/giây × 600 giây = 120.000 document
120.000 × 800 byte = 96.000.000 byte (~91,6 MiB)
~~~

Đây mới là dung lượng payload trung bình; BSON overhead, metadata, biến thiên kích thước, đỉnh lưu lượng và giới hạn số document có thể khiến retention thực tế thấp hơn. Nên dùng mức dung lượng có dự phòng và **đo bằng tải thử**. Ví dụ cấu hình 5 MiB trong bài chỉ dùng cho demo, không hứa giữ 10 phút với lưu lượng trên.

Các chỉ số nên thu thập ở tầng ứng dụng và MongoDB:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| `isCapped()` và collection options | Collection đang thực sự đúng kiểu và giới hạn chưa? |
| `countDocuments`, `stats` và kích thước thực | Bộ đệm đang dùng bao nhiêu dung lượng? |
| Số subscription/cursor mở | Có tạo nhiều listener hoặc quên dispose không? |
| Thời gian từ `createdAt` tới lúc xử lý | Người đọc có đang theo kịp người ghi không? |
| Lần `onError`/`onComplete`, số lần mở lại | Consumer có âm thầm chết hay lặp lỗi liên tục không? |
| Số thứ tự sự kiện bị khuyết / reconciliation errors | Đã mất bản ghi nào trong quá trình restart/ghi đè? |
| Write rate và kích thước trung bình/max document | Retention dự kiến là bao lâu khi tải tăng? |

Không gắn document ID hay message thô vào metric label cardinality cao. Cần phân biệt “5 phút không có log vì hệ thống đang rảnh” với “5 phút không có log vì consumer đã kết thúc”: theo dõi trạng thái subscription và heartbeat của worker.

### 10.1. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động phù hợp |
| --- | --- | --- |
| Lỗi khi mở `tail` | Collection chưa tồn tại hoặc không phải capped | Kiểm tra `isCapped()`; tạo/migrate đúng kiểu trước khi insert |
| Không nhận document mới | Chưa subscribe, stream đã complete, filter không match | Xem callback `onComplete`/`onError`, seed, filter, subscriptions |
| Bắt đầu thì nhận nhiều document cũ | `tail(new Query())` đọc phần dữ liệu đã có | Thiết kế rõ bootstrap/điểm bắt đầu; đừng hiểu là chỉ nhận tương lai |
| Mất dòng khi writer ghi dồn | Capped quay vòng nhanh, cursor đọc chậm | Tăng retention, giảm latency handler, dùng nguồn bền vững nếu không được mất |
| CPU tăng dù không có write | Consumer tự busy-poll `hasNext` hoặc loop restart | Dùng `awaitData`/reactive, backoff và kiểm tra trạng thái cursor |
| Rò rỉ connection/thread khi deploy lại | Không hủy subscription hoặc không stop container | Gắn vòng đời tài nguyên vào Spring bean |
| Hiện tượng xử lý hai lần | Hai instance cùng mở tail, hoặc replay sau restart | Tách worker ownership/dedupe theo event ID; không giả định exactly-once |

## 11. Thực hành cuối bài và tiêu chí tự kiểm tra

Thực hiện trên một database thử nghiệm:

1. Tạo `activity_log` theo ví dụ và xác minh `db.activity_log.isCapped() === true`.
2. Insert một bản ghi seed. Chạy ứng dụng Spring Boot có `ActivityTailConsumer` rồi insert thêm 2 bản ghi từ `mongosh`. Quan sát rằng console nhận cả bản ghi đã tồn tại lúc subscribe và những bản ghi insert sau.
3. Dừng ứng dụng và xác minh tài nguyên được giải phóng qua `dispose()`. Khởi động lại để thấy việc mở cursor mới **không phải resume từ token**.
4. Trên collection thử nghiệm **riêng**, giảm `size`/`max` hoặc insert lượng lớn log để thấy document cũ bị loại. So sánh kết quả `find().sort({$natural: 1})` trước và sau.
5. Thử mở tail khi collection trống hoặc với filter không có match; quan sát complete/error và xác định phải xử lý vòng đời subscription thế nào.
6. Tạo cùng listener trên hai instance thử nghiệm. Kiểm tra cùng một document có thể đến nhiều subscriber; giải thích vì sao đây không phải hàng đợi work-sharing.

Tự trả lời các câu hỏi sau trước khi đưa cơ chế này vào sản xuất:

- Nếu stream hoàn toàn im lặng, làm sao phân biệt “không có insert mới” và “consumer đã chết”?
- Nếu 20 phút mất kết nối trong khi capped collection chỉ giữ được 10 phút, dữ liệu nào không thể lấy lại?
- Tại sao `awaitData` giúp giảm việc hỏi rỗng nhưng không bảo đảm không mất event?
- Vì sao không dùng trực tiếp tailable cursor để bắt sự kiện **update/delete** trên collection `orders`?
- Ứng dụng cần ghi đơn hàng và sự kiện outbox trong một transaction; có nên dùng capped collection làm outbox nguồn chính không? Vì sao?

## 12. Những điều cần nhớ

**Capped collection** cung cấp vùng lưu trữ document có sức chứa hữu hạn, tự loại dữ liệu cũ theo giới hạn; **tailable cursor** là cách theo dõi document mới bằng natural scan; **`awaitData`** giúp cursor đợi tại server trong từng lần `getMore`. Bộ ba này hữu ích cho các luồng log/telemetry gần thời gian thực mà việc mất lịch sử cũ đã được chấp nhận.

Trong Spring Data MongoDB, có thể triển khai bằng `ReactiveMongoTemplate.tail(...)`, `@Tailable` trên repository reactive hoặc `MessageListenerContainer` cho imperative API. Dù dùng cách nào, cần tạo đúng collection trước, quản lý subscription, quan sát completion/error, tính sức chứa thực tế và có cơ chế phục hồi riêng nếu yêu cầu dữ liệu không được mất.

### Tài liệu tham khảo

- [MongoDB Manual — Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/)
- [MongoDB Manual — Create a Capped Collection](https://www.mongodb.com/docs/manual/core/capped-collections/create-capped-collection/)
- [MongoDB Manual — Tailable Cursors](https://www.mongodb.com/docs/manual/core/tailable-cursors/)
- [MongoDB Manual — cursor.tailable()](https://www.mongodb.com/docs/manual/reference/method/cursor.tailable/)
- [Spring Data MongoDB — Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html)
- [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html)

