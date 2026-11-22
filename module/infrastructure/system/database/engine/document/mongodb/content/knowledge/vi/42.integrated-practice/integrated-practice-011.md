# Triển khai Change Stream có lưu mốc tiếp tục và chống xử lý lặp trong MongoDB

## 1. Bài thực hành tổng hợp: mục tiêu và kết quả cuối cùng

Chúng ta xây một dịch vụ Java theo dõi thay đổi của collection `sales.orders` trong MongoDB. Mỗi khi đơn hàng được tạo, cập nhật, thay thế hoặc xóa, dịch vụ cập nhật một collection dùng cho đọc nhanh tên `sales.order_read_models`.

Khác với ví dụ chỉ `watch()` và `println`, consumer phải **tiếp tục được sau khởi động lại** và **không áp cùng một event hai lần**.

Sau khi hoàn thành, ta có thể:

1. Khởi động MongoDB replica set dùng riêng cho lab.
2. Mở Change Stream bằng MongoDB Java Sync Driver.
3. Đọc `resume token` ở dạng BSON và lưu lâu dài trong MongoDB.
4. Ghi `processed_changes` để nhận biết event đã xử lý.
5. Cập nhật read model, receipt và checkpoint trong **một transaction ở cùng MongoDB deployment**.
6. Dừng consumer, khởi động lại rồi tiếp tục từ checkpoint.
7. Cố ý tua checkpoint về một token cũ để kiểm chứng chống lặp.
8. Nhận biết lỗi không thể resume, sự kiện ngoài dự kiến và các giới hạn của mô hình.

Luồng dự kiến:

```text
                     sales.orders
                           |
                           | INSERT/UPDATE/REPLACE/DELETE
                           v
                    MongoDB oplog
                           |
                           v
                  Change Stream cursor
                           |
                           v
                   Java consumer
                           |
                           v
               Transaction trên target
                 /          |           \
                v           v            v
       order_read_models  processed_changes  consumer_checkpoints
           (projection)      (receipt)         (resume token)
                \            |              /
                 \___________|_____________/
                             |
                        COMMIT thành công
                             |
                             v
                      Đọc event kế tiếp
```

**Phạm vi quan trọng:** bài lab đặt source và target collections trong **cùng một replica set** để transaction có thể bao trùm projection, receipt và checkpoint. Khi source và target nằm ở hai cluster độc lập hoặc side effect là email, payment hay HTTP API, không thể dùng transaction này để bảo đảm atomicity xuyên các hệ thống. Các phần sau trình bày hướng mở rộng an toàn.

---

## 2. Kiến thức nền cần nhớ

**Change Stream** là API theo dõi các thay đổi được MongoDB ghi nhận trên collection, database hoặc deployment được hỗ trợ.

Một event có thể mang:

```javascript
{
  _id: {
    _data: "opaque-resume-token"
  },
  operationType: "update",
  clusterTime: Timestamp({ t: 1794662400, i: 1 }),
  ns: {
    db: "sales",
    coll: "orders"
  },
  documentKey: {
    _id: "O100"
  },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Phân biệt:

- `event._id`: **resume token** định vị event trong Change Stream.
- `event.documentKey._id`: ID tài liệu nghiệp vụ bị thay đổi.
- `clusterTime`: logical timestamp, **không thay thế** resume token.
- `operationType`: insert, update, replace, delete, hoặc event quản trị khác.
- `fullDocument`: document theo tùy chọn Change Stream, không luôn có.

### 2.1. Những bảo đảm cần thiết

Change Streams có thể khôi phục từ mốc được hỗ trợ khi lịch sử còn giữ, nhưng không tự làm cho một tác dụng phụ ngoài MongoDB trở thành exactly-once. Ví dụ consumer cập nhật database thành công, crash trước khi lưu token, sau đó nhận lại cùng event.

### 2.2. Tại sao dùng receipt?

Một receipt với khóa event duy nhất giúp xác định event đã được áp dụng vào target. Nó bổ sung cho checkpoint:

- **Checkpoint** nói consumer sẽ tiếp tục đọc từ đâu.
- **Receipt** nói event cụ thể đã được áp dụng hay chưa.
- **Transaction** bảo đảm receipt, projection và checkpoint cùng commit hoặc cùng rollback trong lab này.

### 2.3. Tại sao còn phải giữ thứ tự?

Một event cũ áp dụng sau event mới có thể ghi đè state:

```text
E1: status = PAID
E2: status = REFUNDED

Apply E2 first, then E1
=> target sai thành PAID
```

Lab giữ **một reader, một handler tuần tự**. Nếu mở rộng song song, phải dùng per-key ordering, version fencing hoặc quy tắc tương đương.

---

## 3. Điều kiện tiên quyết

Cần:

- Java 17 hoặc phiên bản Java tương thích với driver đang dùng.
- Maven hoặc build tool của dự án.
- MongoDB Java **Sync Driver**.
- MongoDB deployment hỗ trợ Change Streams: replica set hoặc sharded cluster.
- Quyền đọc source, tạo/ghi target collections và sử dụng transactions ở lab.
- `mongosh` để tạo dữ liệu và kiểm chứng.
- Docker nếu dùng MongoDB local container.
- Một terminal chạy consumer Java và một terminal chạy `mongosh`.

**Không thực hiện thao tác `drop()`, đổi checkpoint hoặc tắt process mongod trên production.** Mọi command thay đổi dữ liệu ở đây dành cho database lab được cô lập.

### 3.1. Phiên bản và topology

Lệnh ví dụ có thể dùng image MongoDB 7.0 cho lab; không hiểu đó là yêu cầu hay khuyến nghị phiên bản mới nhất. Chọn MongoDB Server, FCV và Java driver phù hợp hệ thống thực tế. Các API Change Streams, pre/post images và server configuration có khác biệt theo release.

### 3.2. Standalone không đủ

Một `mongod` standalone thông thường không cung cấp Change Streams. Một replica set **một data-bearing member** dùng được cho lab phát hiện changes và transactions, nhưng không có khả năng chịu lỗi/election của replica set nhiều members.

---

# PHẦN I — TẠO MÔI TRƯỜNG LAB

## 4. Khởi động single-node replica set bằng Docker

Ví dụ terminal Bash với Docker đã cài:

```bash
docker run -d \
  --name mongo-change-lab \
  -p 127.0.0.1:27017:27017 \
  mongo:7.0 \
  --replSet rs0 \
  --bind_ip_all
```

Khởi tạo replica set:

```bash
docker exec mongo-change-lab mongosh \
  --quiet \
  --eval 'rs.initiate({_id:"rs0", members:[{_id:0, host:"localhost:27017"}]})'
```

Kiểm tra:

```bash
docker exec mongo-change-lab mongosh \
  --quiet \
  --eval 'rs.status().members.map(m=>({name:m.name,state:m.stateStr}))'
```

Đợi đến khi member đạt `PRIMARY`.

### 4.1. Connection string cho lab

Vì đây là một container có port được publish ở `127.0.0.1`, có thể dùng:

```text
mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true
```

`directConnection=true` ở đây **chỉ để đơn giản hóa kết nối lab một node**. Production replica set nên dùng topology discovery với nhiều seeds hoặc SRV URI, TLS và authentication đúng cách.

### 4.2. Vấn đề hostname trong Docker

Member hostname được quảng bá trong replica set phải có thể phân giải được từ nơi driver kết nối. Ví dụ dùng `localhost:27017` phù hợp với lab chạy mongod publish port vào host local; với Docker Compose, Kubernetes hoặc kết nối từ container khác, dùng hostname/DNS do mạng đó cung cấp. Nếu driver kết nối được một lần rồi chuyển sang hostname không truy cập được, hãy kiểm tra cấu hình member và URI thay vì thay đổi ngẫu nhiên retry timeout.

### 4.3. Không chạy MongoDB mở mạng không xác thực

Ví dụ bind host về loopback để hạn chế truy cập. Trong môi trường nhiều máy/production, cần TLS, authentication/keyfile và network policy. Không áp dụng cấu hình lab không xác thực cho cluster thật.

---

## 5. Tạo collections riêng

Vào `mongosh`:

```bash
docker exec -it mongo-change-lab mongosh
```

Trong shell:

```javascript
use sales;

db.createCollection("orders");
db.createCollection("order_read_models");
db.createCollection("processed_changes");
db.createCollection("consumer_checkpoints");
```

Nếu một collection đã tồn tại, xử lý theo trạng thái môi trường test; không chạy script reset dữ liệu trên namespace không thuộc quyền của mình.

### 5.1. Vai trò từng collection

| Collection | Chứa gì? | Ai ghi? |
| --- | --- | --- |
| `orders` | Nguồn dữ liệu đơn hàng | Application/mongosh lab |
| `order_read_models` | Bản chiếu document để đọc nhanh | Change Stream consumer |
| `processed_changes` | Receipt cho event đã áp | Change Stream consumer |
| `consumer_checkpoints` | Resume token cuối đã commit | Change Stream consumer |

### 5.2. Cấu trúc mẫu của một order

```javascript
{
  _id: "O100",
  tenantId: "T1",
  customerId: "C100",
  status: "PENDING",
  totalMinor: NumberLong("199000"),
  version: NumberLong("1")
}
```

Trong lab này `_id` dùng string để dễ nhìn. MongoDB cũng hỗ trợ ObjectId hoặc các BSON types hợp lệ khác. Khi làm production consumer, không tự chuyển ObjectId sang string nếu target cần bảo toàn kiểu.

### 5.3. Unique index receipts

Mặc định mỗi collection có unique index `_id`. Ta sẽ dùng một **BSON document làm `_id`** của receipt, chứa consumer identity và toàn bộ resume token:

```javascript
{
  _id: {
    consumer: "orders-projection-v1",
    token: {
      _data: "opaque-resume-token"
    }
  }
}
```

Cùng consumer + cùng token sẽ trùng `_id`, vì vậy chỉ một receipt được chấp nhận.

**Không lưu token bằng `event.getDocumentKey().get("_id")`** vì nhiều updates của cùng order phải là những events khác nhau.

---

## 6. Maven dependencies

Một `pom.xml` minh họa cho Java 17, Maven và MongoDB Java Sync Driver:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>example.mongodb</groupId>
  <artifactId>change-stream-idempotent-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <mongodb.driver.version>5.5.0</mongodb.driver.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.mongodb</groupId>
      <artifactId>mongodb-driver-sync</artifactId>
      <version>${mongodb.driver.version}</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>example.mongodb.ChangeStreamOrderConsumer</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Phiên bản ở đây là **ví dụ về một bộ dependencies**, không đại diện bản mới nhất. Trước khi chạy, đối chiếu Maven Central và compatibility matrix của Java Driver/MongoDB Server đang dùng.

Cấu trúc project:

```text
change-stream-idempotent-lab/
  pom.xml
  src/
    main/
      java/
        example/
          mongodb/
            ChangeStreamOrderConsumer.java
```

---

# PHẦN II — THIẾT KẾ CHECKPOINT VÀ IDEMPOTENCY

## 7. Quy ước consumer ID

Ta dùng:

```text
orders-projection-v1
```

Consumer ID giúp:

- Phân biệt nhiều logical pipelines.
- Tránh ghi chung một checkpoint.
- Namespace khóa receipt.
- Liên kết `pipelineVersion` với trạng thái đã xử lý.

Nếu sau này đổi scope, filter hoặc transform semantics một cách không tương thích, hãy chọn một `consumerId`/generation mới hoặc làm migration checkpoint có kiểm soát.

### 7.1. Không chia sẻ ID giữa hai consumer khác nhau

Một consumer xây `orderReadModels` và một consumer gửi email không được dùng chung checkpoint nếu chúng có tiến độ xử lý độc lập.

### 7.2. Bài lab dùng một active instance

Trong môi trường này, **chỉ chạy một tiến trình** `ChangeStreamOrderConsumer` cho `orders-projection-v1` tại một thời điểm. Nếu chạy hai tiến trình, cả hai có thể đọc cùng token và cạnh tranh transaction; unique receipt bảo vệ không tạo trùng committed receipt, nhưng checkpoint ownership và ordering cần lease/fencing bổ sung để đạt production-grade multi-instance behavior.

---

## 8. Schema checkpoint

Một checkpoint:

```javascript
{
  _id: "orders-projection-v1",
  stream: "sales.orders",
  version: 1,
  resumeToken: {
    _data: "opaque-server-generated-value"
  },
  updatedAt: ISODate("2026-11-14T10:00:00Z")
}
```

`resumeToken` phải giữ **đúng kiểu BSON** mà Java Driver trả ra.

### 8.1. Không chuyển token sang timestamp

Không thay bằng:

```javascript
{
  lastClusterTime: ISODate("2026-11-14T10:00:00Z")
}
```

`clusterTime` không định danh duy nhất từng event. Đặc biệt các thay đổi trong transaction có thể chia sẻ logical timestamp.

### 8.2. Không phân tích `_data`

`resumeToken` là giá trị opaque. Không cắt prefix hoặc tự giải mã byte để tính thứ tự. Chỉ lưu và dùng lại với API `resumeAfter`, `startAfter` khi phù hợp.

### 8.3. Phân biệt token đọc được và token đã xử lý

Consumer có thể nhận event E20 nhưng chưa ghi projection. Token E20 đang có ở RAM **chưa được phép** ghi làm checkpoint bền vững.

---

## 9. Schema receipt chống lặp

Một receipt có khóa chứa consumer và token:

```javascript
{
  _id: {
    consumer: "orders-projection-v1",
    token: {
      _data: "opaque-event-token"
    }
  },
  operationType: "update",
  processedAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 9.1. Vì sao receipts ở cùng transaction?

Nếu ghi receipt thành công rồi projection thất bại, replay nhìn thấy receipt và bỏ qua event → mất cập nhật.

Nếu projection thành công rồi receipt thất bại, replay có thể áp event lần nữa → lỗi đối với thao tác không idempotent.

Trong lab, `receipt + projection + checkpoint` cùng transaction nên không có khoảng hở commit giữa ba records.

### 9.2. Không dùng TTL ngắn cho receipt tùy tiện

Nếu receipt hết hạn trước khi khả năng replay của consumer kết thúc, một event cũ có thể bị xử lý lại như mới. Retention phải dựa trên độ dài replay/rebootstrap, chiến lược checkpoint và rủi ro business.

### 9.3. Khi receipt mang event token có thay đổi sau rebootstrap

Resume token bảo vệ duplicate **cùng change event**. Nếu rebootstrap hoặc migration khác phát sinh **business event mới** cho cùng hành vi, nó có thể có token khác. Với email/payment cần **business operation ID** độc lập với stream token.

---

## 10. Transaction boundary

Từng event được xử lý:

```text
Read event E100
       |
       v
BEGIN TRANSACTION
       |
       +--> find receipt E100
       |
       +--> if absent:
       |       insert receipt E100
       |       upsert/delete projection
       |
       +--> replace checkpoint with token E100
       |
       v
COMMIT TRANSACTION
       |
       v
Read next event
```

Nếu transaction abort, cả projection, receipt và checkpoint không commit.

### 10.1. Điều kiện

- Target collections và transaction session thuộc **cùng MongoDB deployment**.
- MongoDB topology hỗ trợ transactions.
- Có đủ write concern/durability cho yêu cầu.
- Transaction ngắn và hoạt động được lặp lại theo driver retry semantics.
- Không có external API trong transaction callback.

### 10.2. Idempotent còn cần thiết không?

Có. Transaction giảm một loại khoảng hở nội bộ, nhưng khi:

- Consumer bị triển khai lại với checkpoint cũ.
- Có worker khác đọc trùng.
- Có manual replay.
- Có side effects ngoài transaction.

thì receipt/idempotency vẫn là lớp bảo vệ quan trọng.

### 10.3. Điều gì được bảo đảm trong lab?

Khi transaction **commit thành công**:

```text
receipt exists
projection reflects event
checkpoint has event token
```

Khi transaction **abort**:

```text
no receipt for event
no projection change from transaction
no checkpoint advance from transaction
```

Đây là atomicity của target operations trong cùng deployment; nó không tự cho biết toàn bộ hệ thống ngoài MongoDB đã hoàn thành nghiệp vụ.

---

# PHẦN III — JAVA IMPLEMENTATION XUYÊN SUỐT

## 11. Class hoàn chỉnh: ChangeStreamOrderConsumer

Tạo file `src/main/java/example/mongodb/ChangeStreamOrderConsumer.java`.

```java
package example.mongodb;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;

import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.OperationType;

import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ChangeStreamOrderConsumer {

    private static final String CONSUMER_ID =
        "orders-projection-v1";

    private static final String DATABASE = "sales";

    private static final TransactionOptions TX_OPTIONS =
        TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

    private final MongoClient client;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> readModels;
    private final MongoCollection<BsonDocument> receipts;
    private final MongoCollection<BsonDocument> checkpoints;

    private final AtomicBoolean running =
        new AtomicBoolean(true);

    public ChangeStreamOrderConsumer(MongoClient client) {
        this.client = client;

        MongoDatabase db = client.getDatabase(DATABASE);

        this.orders = db.getCollection("orders");

        this.readModels =
            db.getCollection("order_read_models");

        this.receipts =
            db.getCollection(
                "processed_changes",
                BsonDocument.class
            );

        this.checkpoints =
            db.getCollection(
                "consumer_checkpoints",
                BsonDocument.class
            );
    }

    public void stop() {
        running.set(false);
    }

    public void run() {
        BsonDocument savedToken = loadCheckpoint();

        ChangeStreamIterable<Document> iterable =
            orders.watch()
                .fullDocument(FullDocument.UPDATE_LOOKUP)
                .maxAwaitTime(2, TimeUnit.SECONDS);

        if (savedToken != null) {
            iterable = iterable.resumeAfter(savedToken);
            System.out.println("RESUMING_FROM_CHECKPOINT");
        } else {
            System.out.println("NO_CHECKPOINT_STARTING_FRESH");
        }

        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 iterable.cursor()) {

            System.out.println("STREAM_READY");

            while (running.get()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    continue;
                }

                BsonDocument token =
                    event.getResumeToken();

                if (token == null) {
                    throw new IllegalStateException(
                        "Missing resume token"
                    );
                }

                processAtomically(event, token);

                System.out.println(
                    "COMMITTED_EVENT type="
                    + event.getOperationType()
                );
            }
        }
    }

    private BsonDocument loadCheckpoint() {
        BsonDocument record = checkpoints.find(
            Filters.eq("_id", CONSUMER_ID)
        ).first();

        if (record == null) {
            return null;
        }

        return record.getDocument("resumeToken");
    }

    private void processAtomically(
            ChangeStreamDocument<Document> event,
            BsonDocument token
    ) {
        BsonDocument receiptKey =
            new BsonDocument(
                "consumer",
                new BsonString(CONSUMER_ID)
            ).append(
                "token",
                token
            );

        try (ClientSession session =
                 client.startSession()) {

            session.withTransaction(() -> {

                BsonDocument existing =
                    receipts.find(
                        session,
                        Filters.eq("_id", receiptKey)
                    ).first();

                if (existing == null) {
                    receipts.insertOne(
                        session,
                        new BsonDocument(
                            "_id",
                            receiptKey
                        ).append(
                            "operationType",
                            new BsonString(
                                event.getOperationType()
                                    .getValue()
                            )
                        )
                    );

                    applyToReadModel(session, event);
                } else {
                    System.out.println(
                        "DUPLICATE_EVENT_SKIPPED"
                    );
                }

                BsonDocument newCheckpoint =
                    new BsonDocument(
                        "_id",
                        new BsonString(CONSUMER_ID)
                    ).append(
                        "stream",
                        new BsonString("sales.orders")
                    ).append(
                        "resumeToken",
                        token
                    );

                checkpoints.replaceOne(
                    session,
                    Filters.eq("_id", CONSUMER_ID),
                    newCheckpoint,
                    new ReplaceOptions().upsert(true)
                );

                return null;
            }, TX_OPTIONS);
        }
    }

    private void applyToReadModel(
            ClientSession session,
            ChangeStreamDocument<Document> event
    ) {
        OperationType type =
            event.getOperationType();

        if (type == OperationType.INSERT
                || type == OperationType.REPLACE
                || type == OperationType.UPDATE) {

            Document full =
                event.getFullDocument();

            if (full == null) {
                throw new IllegalStateException(
                    "fullDocument is unavailable for "
                    + type
                );
            }

            // Stable transformation: preserve _id/type.
            Document projection =
                new Document(full);

            readModels.replaceOne(
                session,
                Filters.eq("_id", full.get("_id")),
                projection,
                new ReplaceOptions().upsert(true)
            );

        } else if (type == OperationType.DELETE) {

            BsonDocument key =
                event.getDocumentKey();

            if (key == null
                    || !key.containsKey("_id")) {
                throw new IllegalStateException(
                    "Delete missing document key"
                );
            }

            readModels.deleteOne(
                session,
                key
            );

        } else {
            throw new IllegalStateException(
                "Unsupported Change Stream event: "
                + type
            );
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGODB_URI",
            "mongodb://127.0.0.1:27017/"
                + "?replicaSet=rs0&directConnection=true"
        );

        AtomicBoolean running =
            new AtomicBoolean(true);

        try (MongoClient client =
                 MongoClients.create(uri)) {

            ChangeStreamOrderConsumer consumer =
                new ChangeStreamOrderConsumer(client);

            Runtime.getRuntime().addShutdownHook(
                new Thread(consumer::stop)
            );

            consumer.run();
        }
    }
}
```

### 11.1. Diễn giải từng nhóm trách nhiệm

- `loadCheckpoint()`: đọc token BSON đã commit cuối cùng.
- `orders.watch()`: mở stream ở collection scope.
- `.resumeAfter(savedToken)`: tiếp tục sau token đã lưu.
- `.fullDocument(UPDATE_LOOKUP)`: yêu cầu lấy document cho update khi có thể.
- `cursor.tryNext()`: đợi event hoặc trả null nếu chưa có.
- `processAtomically()`: mở transaction target cho event.
- `receipts.find(...)`: kiểm tra token đã xử lý.
- `receipts.insertOne(...)`: ghi dấu event.
- `applyToReadModel(...)`: upsert hoặc delete projection.
- `checkpoints.replaceOne(...)`: lưu token **trong cùng transaction**.
- `withTransaction(...)`: commit hoặc abort cả nhóm thao tác.
- `try-with-resources`: đóng session/cursor/client theo vòng đời.

### 11.2. Vì sao không gọi external API trong callback?

`withTransaction` có thể retry callback khi gặp lỗi tạm thời. Nếu callback gọi `emailService.send(...)`, email có thể được gửi lại ngay cả trước khi xử lý chuyện resume. Chỉ dùng các operations MongoDB thuộc transaction; side effects bên ngoài cần workflow riêng.

### 11.3. Vì sao handler tuần tự?

Điều này giúp checkpoint không vượt qua một event còn xử lý dở. Một reader/one active owner là điều kiện được giả định trong lab; code chưa triển khai distributed lease/fencing.

### 11.4. `fullDocument` chưa phải historical post-image chính xác

`UPDATE_LOOKUP` có thể lấy state mới hơn event đang xử lý; ví dụ `PAID` rồi `REFUNDED` rất nhanh, lookup cho event `PAID` có thể đã thấy `REFUNDED`. Lab xây **projection trạng thái cuối**, không phải business audit log. Nếu cần lịch sử transition chính xác, dùng domain outbox hoặc pre/post-images theo cấu hình/version phù hợp.

### 11.5. Xử lý fullDocument null ở bản minh họa

Bản lab **ném lỗi và không checkpoint** nếu `fullDocument` không có cho update/replace. Với workload thật, trạng thái đó có thể xảy ra do document bị xóa trước lookup; production code phải có policy rõ, ví dụ xử lý patch, post-image hoặc rebuild state. Không âm thầm coi null là delete event.

### 11.6. Lưu ý `main` và graceful shutdown

Shutdown hook đặt `running=false`. Do `tryNext()` có thể block, quá trình dừng phụ thuộc thời gian await/getMore và timeout. Production có thể cần close cursor từ cancellation controller theo contract `MongoCursor` hoặc đóng theo deadline của orchestrator. `main` ở đây chỉ là ứng dụng lab đơn giản.

### 11.7. Không tự bổ sung logging PII

Các log minh họa chỉ in operation type, không in raw customer documents, resume token hoặc credentials.

---

## 12. Vì sao dùng `BsonDocument` cho checkpoint và receipt?

Các resume tokens là BSON opaque. `BsonDocument` giúp lưu lại giá trị mà driver cung cấp mà không cần chuyển thành chuỗi JSON.

Ví dụ:

```java
BsonDocument token = event.getResumeToken();

BsonDocument checkpoint =
    new BsonDocument(
        "_id",
        new BsonString("orders-projection-v1")
    ).append("resumeToken", token);
```

Khi khôi phục:

```java
BsonDocument savedToken =
    checkpoint.getDocument("resumeToken");

orders.watch()
    .resumeAfter(savedToken);
```

### 12.1. Tránh serialization gây mất kiểu

Không biến token thành `Map<String, Object>` rồi lưu ra JSON tùy ý nếu pipeline có thể làm mất BSON type information.

### 12.2. Token không phải secret đăng nhập

Token không cấp quyền database, nhưng vẫn là metadata vận hành có thể chứa thông tin nhạy cảm về vị trí replication. Không nên xuất ra client hoặc logs công khai.

### 12.3. Không so sánh token theo thứ tự từ `_data`

Không sort `resumeToken._data` như chuỗi rồi cho rằng token lớn hơn luôn có thứ tự event mới hơn. MongoDB không cam kết format để ứng dụng tự suy luận như vậy.

---

## 13. Vì sao receipt key chứa cả consumer?

Giả sử hai projections độc lập:

```text
orders-search-index-v1
orders-notification-intent-v1
```

Cùng event E100 cần được xử lý **một lần ở mỗi pipeline**, không phải một lần trên toàn hệ thống.

Vì vậy:

```text
(receipt.consumer, receipt.token)
```

phù hợp hơn:

```text
receipt.token only
```

khi các pipelines dùng chung receipt collection.

### 13.1. Không dùng documentKey làm event identity

Cùng order `"O100"` có thể có nhiều updates và delete:

```text
E1: O100 inserted
E2: O100 status=PAID
E3: O100 status=SHIPPED
E4: O100 deleted
```

Nếu dedup theo `_id="O100"`, sẽ xử lý E1 rồi bỏ E2, E3, E4 sai hoàn toàn.

---

## 14. Atomicity và trường hợp duplicate

Xét event E1 đã được xử lý, nhưng checkpoint bị người vận hành đưa về token trước E1 trong môi trường lab.

Khi E1 được đọc lại:

```text
Transaction:
  find receipt E1 -> exists
  skip projection write
  save checkpoint E1
  commit
```

Kết quả:

- Receipt không bị tạo lần thứ hai.
- Projection không được cập nhật lại bởi event này.
- Checkpoint có thể tiến về vị trí vừa đọc.
- Consumer tiếp tục các events sau đó.

### 14.1. Tại sao cần cả receipt dù checkpoint đã atomic?

Ở normal path, atomic checkpoint và projection làm việc rất tốt. Receipt vẫn hữu ích khi có **manual rewind**, duplicated delivery từ một nguồn khác hoặc trình xử lý muốn cung cấp thêm bằng chứng event đã áp dụng.

### 14.2. Một lưu ý về checkpoint regression

Code lab **giả định chỉ một active consumer owner** và event được đọc tuần tự. Trong hệ chạy hai instances cùng ID, một worker cũ có thể ghi checkpoint về token cũ nếu không có compare-and-swap/lease fencing. Receipt không đủ để bảo vệ con trỏ tiến độ khỏi mọi tranh chấp.

### 14.3. Production nên có fencing

Gắn checkpoint với owner generation và chỉ cho worker đang giữ lease hợp lệ commit. Nếu worker mất lease, phải ngừng xử lý, không được áp dữ liệu hoặc lưu token.

---

# PHẦN IV — CHẠY VÀ KIỂM CHỨNG LAB

## 15. Biên dịch và chạy consumer

Trong thư mục project:

```bash
mvn -q compile exec:java
```

Có thể đặt URI bằng biến môi trường:

```bash
export MONGODB_URI="mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mvn -q compile exec:java
```

Ví dụ trên dùng shell Bash. Trong PowerShell:

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mvn -q compile exec:java
```

Đầu ra khởi động lần đầu:

```text
NO_CHECKPOINT_STARTING_FRESH
STREAM_READY
```

**Chỉ chèn events sau khi thấy `STREAM_READY`** ở bước lab này để tránh race giữa việc khởi động consumer và tạo thay đổi.

### 15.1. Nếu xuất hiện lỗi “not supported on standalone”

Kiểm tra `rs.status()` và connection string. `mongod` chạy với `--replSet` nhưng chưa `rs.initiate()`/chưa có PRIMARY chưa phải một replica set hoạt động đầy đủ.

### 15.2. Nếu connection timeout

Kiểm tra Docker port binding, hostname advertised trong replica set, network, TLS/auth và server selection. Không tự sửa semantics checkpoint chỉ vì không kết nối được.

---

## 16. Bước thử nghiệm 1: insert

Trong terminal `mongosh`:

```javascript
use sales;

db.orders.insertOne({
  _id: "O100",
  tenantId: "T1",
  customerId: "C100",
  status: "PENDING",
  totalMinor: NumberLong("199000"),
  version: NumberLong("1")
});
```

Ở terminal consumer, kỳ vọng:

```text
COMMITTED_EVENT type=insert
```

Kiểm tra projection:

```javascript
db.order_read_models.findOne({ _id: "O100" });
```

Kỳ vọng document có `status: "PENDING"` cùng những trường nguồn.

### 16.1. Kiểm tra checkpoint

```javascript
db.consumer_checkpoints.findOne({
  _id: "orders-projection-v1"
});
```

Kỳ vọng có `resumeToken` BSON và `stream: "sales.orders"`.

### 16.2. Kiểm tra receipt

```javascript
db.processed_changes.countDocuments();
```

Nếu collection lab trước đó sạch và mới có một change event được xử lý, kỳ vọng count là 1.

### 16.3. Quan trọng: đừng dùng `Thread.sleep(100)` làm assertion

Consumer bất đồng bộ. Trong test tự động, hãy poll đến khi projection/checkpoint xuất hiện trong deadline phù hợp, thay vì giả định đúng 100 ms sau insert đã xong.

---

## 17. Bước thử nghiệm 2: update

Tiếp tục trong `mongosh`:

```javascript
db.orders.updateOne(
  { _id: "O100" },
  {
    $set: {
      status: "PAID",
      version: NumberLong("2")
    }
  }
);
```

Consumer:

```text
COMMITTED_EVENT type=update
```

Projection:

```javascript
db.order_read_models.findOne({
  _id: "O100"
});
```

Kỳ vọng:

```javascript
{
  _id: "O100",
  tenantId: "T1",
  customerId: "C100",
  status: "PAID",
  totalMinor: NumberLong("199000"),
  version: NumberLong("2")
}
```

Receipt count sau hai events được xử lý:

```javascript
db.processed_changes.countDocuments();
// 2
```

### 17.1. Điều test thật sự chứng minh

- `insert` và `update` là hai events khác nhau.
- Mỗi event có receipt riêng.
- Checkpoint tiến sau event thứ hai.
- Projection cuối phản ánh cập nhật.

Nó **không** chứng minh một email về thanh toán đã được gửi đúng một lần; bài lab không có external email provider.

---

## 18. Bước thử nghiệm 3: replace

Thay toàn document bằng cách giữ `_id`:

```javascript
db.orders.replaceOne(
  { _id: "O100" },
  {
    _id: "O100",
    tenantId: "T1",
    customerId: "C100",
    status: "FULFILLED",
    totalMinor: NumberLong("199000"),
    version: NumberLong("3")
  }
);
```

Kiểm tra:

```javascript
db.order_read_models.findOne({
  _id: "O100"
});
```

Kỳ vọng status `FULFILLED`.

### 18.1. Đừng nhầm replace với update

`replaceOne()` có thể tạo Change Stream event `replace`; consumer phải xử lý cả loại event này nếu business cần theo dõi mọi thay đổi state.

### 18.2. Checkpoint sau replace

Nếu xử lý thành công, receipt count tăng thêm 1, checkpoint đổi sang resume token của replace event.

---

## 19. Bước thử nghiệm 4: delete

```javascript
db.orders.deleteOne({
  _id: "O100"
});
```

Consumer:

```text
COMMITTED_EVENT type=delete
```

Kiểm tra:

```javascript
db.order_read_models.findOne({
  _id: "O100"
});
// null
```

Receipt count tiếp tục tăng thêm một khi delete event đã commit xử lý.

### 19.1. Vì sao không dùng fullDocument trên delete?

Delete event thường chỉ mang `documentKey` để biết record nào đã bị xóa. Nếu business phải biết email người dùng hoặc tenant ID khi delete, thiết kế key mapping/pre-image/outbox thích hợp; không giả định fullDocument luôn có.

### 19.2. Sharded collection

`documentKey` có thể chứa shard key fields. Lab không sharded nên bộ lọc được đưa trực tiếp vào `deleteOne`. Khi source/target khác shard key/schema, cần mapping và routing hợp lệ.

---

## 20. Bước thử nghiệm 5: dừng và khởi động lại

Sau khi các events đã được commit và checkpoint đã tồn tại, dừng consumer bằng Ctrl+C.

Khởi động lại:

```bash
mvn -q compile exec:java
```

Output:

```text
RESUMING_FROM_CHECKPOINT
STREAM_READY
```

Tạo event mới:

```javascript
db.orders.insertOne({
  _id: "O101",
  tenantId: "T1",
  status: "PENDING",
  version: NumberLong("1")
});
```

Kiểm tra:

```javascript
db.order_read_models.findOne({
  _id: "O101"
});
```

Kỳ vọng `O101` được tạo sau restart.

### 20.1. Điều đã được chứng minh

- Resume token không chỉ nằm trong RAM.
- Consumer mới có thể đọc từ checkpoint đã commit.
- Những events mới không bị bỏ qua.
- Không cần ghi nhớ server cursor ID.

### 20.2. Không lưu server cursor ID như token

MongoDB server cursor ID là state tạm thời của cursor phiên làm việc. Resume token là dữ liệu change stream dùng cho recovery theo API.

---

# PHẦN V — CỐ Ý REPLAY ĐỂ KIỂM CHỨNG CHỐNG LẶP

## 21. Vì sao cần kiểm thử replay?

Một consumer hoạt động 10 phút mà không bị lỗi có thể vẫn sai khi process crash đúng giữa apply và checkpoint. Muốn chứng minh chống lặp, cần thử **đọc lại cùng một event**.

Lab cung cấp hai cách:

1. **Manual checkpoint rewind** trong database test.
2. **Failure injection** ở các điểm trước/sau transaction commit.

Không được sửa checkpoint production bằng tay nếu chưa có recovery runbook, ownership và backups.

---

## 22. Chuẩn bị một luồng sự kiện mới cho replay

Trên database `sales` trong lab, chỉ khi không còn data từ bài test cũ gây nhiễu, tạo document mới:

```javascript
db.orders.insertOne({
  _id: "O200",
  tenantId: "T2",
  status: "NEW",
  version: NumberLong("1")
});
```

Đợi consumer xử lý `O200` và checkpoint có token tương ứng.

Tạo nơi giữ token đầu tiên:

```javascript
const checkpointBeforeUpdate =
  db.consumer_checkpoints.findOne({
    _id: "orders-projection-v1"
  }).resumeToken;

db.lab_control.replaceOne(
  { _id: "saved-before-update" },
  {
    _id: "saved-before-update",
    token: checkpointBeforeUpdate
  },
  { upsert: true }
);
```

Collection `lab_control` chỉ dùng cho việc thử nghiệm trong môi trường cô lập.

### 22.1. Vì sao cần đợi consumer commit trước khi lưu token?

Nếu đọc token trước khi event insert được commit, ta có thể vô tình lưu một checkpoint cũ. Hãy kiểm tra `order_read_models` và receipt count thay vì đoán thời gian.

### 22.2. Tạo event thứ hai

```javascript
db.orders.updateOne(
  { _id: "O200" },
  {
    $set: {
      status: "PAID",
      version: NumberLong("2")
    }
  }
);
```

Đợi projection hiển thị `PAID`. Ghi nhận receipt count:

```javascript
const receiptsAfterUpdate =
  db.processed_changes.countDocuments();

print(receiptsAfterUpdate);
```

---

## 23. Tua checkpoint về token cũ: chỉ trong lab

**Dừng consumer trước**, bảo đảm không có instance nào còn dùng consumer ID này.

Trong `mongosh`:

```javascript
const oldToken =
  db.lab_control.findOne({
    _id: "saved-before-update"
  }).token;

db.consumer_checkpoints.updateOne(
  { _id: "orders-projection-v1" },
  {
    $set: {
      resumeToken: oldToken
    }
  }
);
```

Bây giờ checkpoint trỏ về token **sau insert O200 nhưng trước update O200**.

Khởi động consumer lại:

```bash
mvn -q compile exec:java
```

Kỳ vọng console ghi một event được nhận lại nhưng handler phát hiện receipt đã có:

```text
RESUMING_FROM_CHECKPOINT
STREAM_READY
DUPLICATE_EVENT_SKIPPED
COMMITTED_EVENT type=update
```

### 23.1. Kết quả cần kiểm tra

```javascript
db.order_read_models.findOne({
  _id: "O200"
});
```

Vẫn là `status: "PAID"`.

```javascript
db.processed_changes.countDocuments();
```

Không tăng thêm do event update đã có receipt.

### 23.2. Test này chứng minh điều gì?

- Consumer có thể đọc lại event đã xử lý.
- Receipt của event đã xử lý vẫn tồn tại.
- Handler không chạy lại projection cho event đó.
- Checkpoint được đưa về vị trí vừa xử lý.

### 23.3. Không đồng nghĩa toàn hệ thống exactly-once

Nếu handler còn gửi một email trước khi ghi receipt, email có thể đã gửi lặp. Transaction receipt/projection ở MongoDB không bao trùm email provider.

---

## 24. Failure injection: crash trước transaction commit

Tưởng tượng handler làm:

```text
BEGIN
  insert receipt E300
  update read model E300
  write checkpoint E300
  crash before COMMIT
```

Khi process đột ngột chết trước commit, transaction chưa commit sẽ không để lại trạng thái hoàn chỉnh của nhóm thay đổi.

Sau restart:

```text
resume after earlier checkpoint
read E300 again
transaction applies E300
commit
```

### 24.1. Bài test cần kiểm tra

- Không có receipt E300 từ transaction chưa commit.
- Không có projection update nửa chừng từ transaction đó.
- Checkpoint không vượt E300.
- Replay sau restart có thể apply E300.

### 24.2. Lỗi ambiguous commit

Nếu process chết **ngay sau khi gửi commit** mà chưa nhận phản hồi, tình huống không rõ commit đã thành công hay chưa. Sau restart, đọc lại durable checkpoint:

- Nếu commit thành công, token đã được lưu cùng receipt/projection; resume sau E300.
- Nếu commit không thành công, token vẫn cũ; E300 được đọc lại và apply.
- Nếu checkpoint bị rollback theo durability policy, có thể replay nhiều hơn; receipt và idempotency vẫn quan trọng.

### 24.3. Không thử bằng cách kill mongod production

Dùng failure hooks trong worker hoặc một process test và database cô lập. Đừng làm crash primary thật để xác nhận logic application.

---

## 25. Failure injection: crash sau transaction commit

Sơ đồ:

```text
BEGIN
  receipt E301
  projection E301
  checkpoint E301
COMMIT SUCCESS
process crashes before next poll
```

Sau restart, consumer load token E301 và `resumeAfter(E301)`.

Kỳ vọng:

- E301 không cần xử lý lại.
- Event E302 sau đó vẫn được nhận.
- Projection, receipt và checkpoint cùng hiện diện.
- Không có half-applied state.

### 25.1. Vì sao `withTransaction` hữu ích?

Một vài lỗi tạm thời có thể khiến driver retry callback/commit theo semantics. Nhưng callback chỉ nên bao gồm các MongoDB operations thuộc transaction, với input event/token ổn định, không có external side effects.

### 25.2. Nếu target không hỗ trợ transaction?

Cần phương án khác:

- Idempotent state writes.
- Receipt và checkpoint ghi theo protocol chấp nhận replay.
- Durable outbox hoặc queues.
- Reconciliation để sửa partial effects.
- Không tuyên bố atomicity mà deployment không cung cấp.

---

# PHẦN VI — GIẢI THÍCH CÁC ĐIỂM KHÓ

## 26. `resumeAfter`, `startAfter`, `startAtOperationTime`

| API | Dùng khi | Chú ý |
| --- | --- | --- |
| `resumeAfter(token)` | Restart thông thường từ token của stream | Token/history phải hợp lệ |
| `startAfter(token)` | Mở stream sau invalidate token trong điều kiện được hỗ trợ | Không tự dựng lại collection |
| `startAtOperationTime(ts)` | Bắt đầu từ một BSON logical timestamp có history hỗ trợ | Không định danh một event cụ thể như token |

### 26.1. Trong lab dùng resumeAfter

Vì checkpoint luôn là event token vừa commit, `resumeAfter(token)` phù hợp.

### 26.2. Khi gặp invalidate

`resumeAfter` không được dùng để resume sau invalidate theo cách thông thường. Tùy scope và điều kiện, `startAfter` có thể được sử dụng để mở stream mới. Tuy vậy nếu collection bị drop rồi tạo lại, business projection có thể cần rebuild.

### 26.3. Không dùng hai starting options cùng lúc

Một Change Stream chỉ nên có **một starting position** được định nghĩa.

### 26.4. `startAtOperationTime` không nhận Java Date

Nó dùng BSON `Timestamp`, có seconds và increment; không lấy `new Date()` rồi cast sang token.

---

## 27. Tại sao không dùng `clusterTime` làm checkpoint?

Ví dụ hai events trong cùng transaction có cùng logical timestamp:

```text
E1 clusterTime = T100
E2 clusterTime = T100
```

Nếu consumer xử lý E1 rồi lưu duy nhất T100, lúc restart khó biết E2 đã xử lý hay chưa.

Resume token chứa vị trí cụ thể hơn theo API Change Streams. **Giữ nguyên event token** thay vì tự thiết kế checkpoint trên một timestamp chỉ có tính gần đúng.

### 27.1. Không dùng wall clock làm sequence

Các máy có thể bị clock skew; Java `Instant.now()` là mốc thời gian xử lý ở client, không phải offset của stream.

### 27.2. Không dùng document ID làm checkpoint

Một document có thể update nhiều lần. Cursor position và document identity là hai khái niệm khác nhau.

---

## 28. Post-batch resume token và empty batches

Khi không có event mới, server có thể trả empty batch kèm `postBatchResumeToken`/high-watermark. MongoDB Java Driver có API tương ứng:

```java
BsonDocument token = cursor.getResumeToken();
```

Điều này khác với token trả ra trên một event cụ thể.

### 28.1. Vì sao bài lab chỉ checkpoint event tokens?

Để đơn giản hóa correctness: với một handler tuần tự, checkpoint luôn gắn với event đã xử lý thành công.

### 28.2. Lợi ích khi lưu high-watermark

Một consumer ít hoạt động có thể giữ token cũ trong thời gian dài; trong một số điều kiện history retention, checkpoint high-watermark mới hơn có lợi cho recovery.

### 28.3. Rủi ro

Nếu reader đã đọc nhiều events nhưng workers còn xử lý, lưu high-watermark quá xa có thể skip những events chưa ack.

Chỉ lưu `getResumeToken()` từ empty batches khi **không còn pending/in-flight work trước vị trí đó** và có protocol về ownership và checkpoint.

---

## 29. `UPDATE_LOOKUP` không phải exact post-image lịch sử

Giả sử source thay đổi liên tục:

```text
T1: status=PENDING
T2: status=PAID
T3: status=REFUNDED
T4: worker nhận update event của T2
```

`fullDocument(UPDATE_LOOKUP)` có thể trả state hiện tại `REFUNDED` tại lúc lookup, không nhất thiết chính xác state sau T2.

### 29.1. Lab làm gì?

Xây một read model theo trạng thái tài liệu. Khi các events xử lý tuần tự và source cuối cùng không đổi nữa, projection cuối kỳ vọng hội tụ về state nguồn. Nó không được dùng như event-sourcing log ghi lại mọi transition chính xác.

### 29.2. Nếu cần thông báo trạng thái cụ thể

Một `OrderPaid` email phải phản ánh business transition chính xác, không thể chỉ suy từ document state hiện tại khi nhận update event chậm.

Cân nhắc:

- Transactional outbox.
- Immutable domain event ID.
- Pre/post images khi collection và server hỗ trợ.
- Durable event log có retention đủ dài.

### 29.3. Nếu fullDocument null

Có thể do document bị delete trước khi lookup. Handler không được coi null là một delete event nếu chưa có policy bảo đảm điều đó đúng. Bản lab ném lỗi để chặn checkpoint và yêu cầu điều chỉnh semantics cho workload thực.

---

## 30. Delete và sự kiện ngoài dự kiến

Bản lab xử lý:

```text
insert
update
replace
delete
```

Những event như:

```text
drop
rename
invalidate
```

phải được xử lý theo chính sách. Bản lab ném exception để **không báo success sai**.

### 30.1. Không lọc sự kiện quan trọng rồi tự tin là pipeline khỏe

Nếu một stream filter loại bỏ invalidate/DDL behavior không phù hợp, consumer có thể không biết namespace thay đổi. Tổ chức phải chọn policy riêng cho schema/migration events.

### 30.2. Dừng pipeline có chủ đích

Một lỗi không recoverable nên chuyển trạng thái consumer thành `FAILED`, `REBOOTSTRAP_REQUIRED` hoặc trạng thái rõ ràng, thay vì vòng lặp retry vô hạn.

---

## 31. Điều gì xảy ra khi source không còn oplog history?

`resumeAfter` yêu cầu resume token còn trong lịch sử có thể truy cập được theo semantics server. Oplog window bị giới hạn bởi size/retention và tốc độ writes.

```text
T0 checkpoint saved
T1 consumer offline
T2 source writes heavily
T3 old oplog history rolled over
T4 consumer resumes token T0 -> ERROR
```

Nếu token đã mất history:

1. Không xóa token rồi mở stream “từ bây giờ” mà tuyên bố đầy đủ dữ liệu.
2. Đánh dấu consumer cần **rebootstrap** hoặc replay từ nguồn bền vững khác.
3. Xác định ảnh hưởng business của events có thể đã mất.
4. Rebuild projection từ source state, có capture boundary đúng.
5. Reconcile kết quả với source.
6. Chỉ chuyển HEALTHY sau khi phục hồi/catch-up.

### 31.1. Tăng oplog sau sự cố không khôi phục quá khứ

Nâng size/retention giúp tương lai, không tái tạo entries đã bị loại.

### 31.2. Domain event cần retention dài hơn

Nếu cần gửi email cho mọi transition đã diễn ra, current state sau rebootstrap không đủ tái tạo lịch sử. Một outbox/event log lâu dài có thể cần thiết.

---

## 32. Bootstrap những documents đã tồn tại trước khi watch()

Nếu collection đã có hàng triệu orders, một Change Stream bắt đầu mới **không tự phát insert events cho toàn bộ dữ liệu cũ**.

Một projection mới cần initial load.

### 32.1. Cách sai

```text
1. Scan all existing orders
2. End scan
3. Start Change Stream
```

Writes xảy ra giữa scan và stream start có thể bị bỏ sót.

### 32.2. Cách an toàn hơn về mặt khái niệm

```text
Establish safe CDC starting point
              |
              v
Persist changes durably from T0
              |
              +------------------+
              |                  |
              v                  v
       Backfill snapshot     Capture live changes
              |                  |
              +------------------+
                         |
                         v
                Replay changes in order
                         |
                         v
                Reconcile + go live
```

### 32.3. Bẫy overwrite

Nếu backfill viết `PENDING` sau khi CDC đã ghi `PAID`, projection bị lùi state. Cần:

- Backfill rồi replay captured events theo thứ tự.
- Hoặc version-aware conditional writes.
- Hoặc dùng snapshot/migration tool được hỗ trợ.
- Hoặc tạm dừng writes nếu SLA cho phép.

### 32.4. Oplog window phải đủ

Nếu initial scan kéo dài nhiều giờ, phải chắc chắn stream events từ T0 được persist/replay và history không mất giữa chừng.

---

## 33. Vị trí lưu state khi source và target khác cluster

Ví dụ production:

```text
MongoDB source cluster A
       |
       v
Change Stream consumer
       |
       v
MongoDB target cluster B
       |
       +--> projection
       +--> receipt
       +--> checkpoint
```

Transaction trên target B có thể nhóm projection, receipt và checkpoint, miễn toàn bộ chúng thuộc B và topology hỗ trợ.

Nhưng transaction này **không bao trùm** source cluster A hay external services.

### 33.1. Nếu target là Elasticsearch

Không có MongoDB transaction cho index write Elasticsearch và MongoDB checkpoint. Cần idempotent document ID/version, retry, durable queue, and reconciliation.

### 33.2. Nếu target là Kafka

Có thể dùng connector hoặc outbox, nhưng end-to-end exactly-once cần phân tích offset commit/sink semantics. Không mặc định Kafka transaction tự làm MongoDB event + external business effect thành một transaction duy nhất.

### 33.3. Nếu target là email provider

Provider-level idempotency/delivery ledger/reconciliation quyết định khả năng chống gửi trùng; MongoDB resume token chỉ là một phần.

---

# PHẦN VII — NÂNG CẤP THÀNH HỆ THỐNG PRODUCTION

## 34. Worker lease và fencing

Bản lab giả định một consumer process. Production có thể chạy Kubernetes replicas, autoscaling hoặc rolling deployment, khiến hai instances cùng hoạt động.

```text
Worker A owns consumerId
        |
   A becomes paused
        |
   Lease expires
        |
Worker B owns consumerId
        |
A wakes up and tries to commit old token
```

Nếu không có fencing, A có thể ghi checkpoint cũ đè lên checkpoint mới.

### 34.1. Cấu trúc lease gợi ý

```javascript
{
  _id: "orders-projection-v1",
  ownerId: "pod-42",
  generation: NumberLong("12"),
  leaseUntil: ISODate("2026-11-14T10:01:00Z")
}
```

### 34.2. Nguyên tắc

- Mỗi logical stream có một active owner hoặc một partition protocol rõ.
- Khi nhận lease mới, tăng fencing generation.
- Transaction/checkpoint write phải kiểm tra generation đang hợp lệ.
- Worker mất lease ngừng apply và checkpoint.
- Không chỉ kiểm tra lease lúc startup; phải validate trong write path.

### 34.3. Receipt không thay fencing

Receipt tránh một event được commit hai lần, nhưng không nhất thiết ngăn một worker cũ **lùi checkpoint** hoặc ghi projection theo logic outdated.

---

## 35. Khi cần scale nhiều workers

Một reader:

```text
MongoChangeStreamCursor
          |
          v
     Ordered dispatcher
          |
    +-----+-----+
    |           |
  Key A       Key B
  Worker A    Worker B
```

### 35.1. Partition theo aggregate key

Dùng `documentKey._id` hoặc business aggregate ID để tất cả events của cùng order vào cùng ordered queue.

### 35.2. Giữ thứ tự theo key

Không cho E5/E6 của cùng order hoàn tất đảo thứ tự rồi ghi state cũ.

### 35.3. Checkpoint contiguous prefix

Nếu E10 hoàn thành, E11 chưa hoàn thành, E12 đã xong, **chưa checkpoint qua E11**.

Chỉ được tiến đến vị trí mà mọi events trước đó đã ack, trừ khi có một protocol phân vùng và checkpoint khác được chứng minh đúng.

### 35.4. Queue phải bounded

Một `LinkedBlockingQueue` không giới hạn với source 30.000 events/s và sink 300 events/s có thể làm heap tăng không kiểm soát.

### 35.5. Backpressure có chi phí

Dừng fetch lâu làm lag tăng và oplog window tiếp tục co. Cần scaling, metrics, durable buffering hoặc điều tiết source workload, không chỉ tăng queue size.

---

## 36. Transaction throughput và chi phí

Mỗi event trong lab tạo một transaction:

```text
find receipt
insert receipt
upsert/delete projection
upsert checkpoint
commit
```

Ưu điểm là ranh giới correctness rõ. Nhưng throughput có thể bị giới hạn bởi:

- Transaction setup/commit round trips.
- Majority write latency.
- Index maintenance ở receipts/checkpoints.
- Document size.
- Number of active consumers.
- Disk IOPS.
- Network RTT.

### 36.1. Có thể batch transactions không?

Có, nhưng phải xử lý:

- Receipt theo từng event.
- Thứ tự events.
- Toàn bộ batch commit/abort.
- Checkpoint cuối batch.
- Transaction lifetime/size limits.
- Replay nhiều events nếu crash.
- Không trộn external side effects.

### 36.2. Khi nào cần lưu receipt mãi?

Nếu checkpoint và projection atomic, cùng một active consumer và không có manual replay/cross-system side effects, receipt có thể không cần giữ vô hạn. Tuy vậy việc tối ưu bỏ receipt phải gắn với replay/rebootstrap policy và mong muốn audit, không làm theo cảm tính.

### 36.3. TTL receipts phải có retention policy

Một TTL index dọn receipts có thể tiết kiệm storage, nhưng expiry quá sớm làm duplicate event trở thành “mới” khi replay cũ. Không đặt TTL 1 giờ nếu business cho phép replay sau nhiều ngày.

---

## 37. Retry lỗi tạm thời

Một consumer có thể gặp:

- Connection reset.
- Temporary server selection timeout.
- Primary election.
- Network partition.
- Target write concern timeout.
- Transaction conflict/retry.
- CPU/disk pressure.

Driver Change Streams có thể tự resume một số lỗi theo API contract, nhưng application vẫn cần restart policy.

### 37.1. Sơ đồ xử lý

```text
Stream read / apply throws
          |
          v
Classify error
          |
     +----+----+
     |         |
Transient    Non-recoverable
     |         |
     v         v
Close cursor  Mark FAILED
Backoff       Alert
Reload token  No silent skip
Reopen        Rebootstrap if needed
```

### 37.2. Không retry vô hạn mọi lỗi

Unsupported event type, schema error, wrong permissions hoặc history lost không được xử lý bằng tight loop `try again`.

### 37.3. Backoff và jitter

Ví dụ policy:

```text
Attempt 1: 200 ms + jitter
Attempt 2: 500 ms + jitter
Attempt 3: 1 s + jitter
Attempt 4: 2 s + jitter
Cap:       30 s
```

Đây là minh họa, không phải cấu hình cố định cho mọi SLA.

---

## 38. `writeConcern: majority` và ambiguity

Transaction trong lab dùng:

```java
TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

### 38.1. Tại sao chọn majority?

Muốn projection/receipt/checkpoint đã commit có mức durability phù hợp trên replica set nhiều members, giảm rủi ro rollback của committed state theo semantics có hỗ trợ.

### 38.2. Một node lab vẫn chỉ có một bản dữ liệu

`w:majority` trên replica set một node không thay thế dự phòng dữ liệu, backups hoặc khả năng chịu lỗi của topology có nhiều data-bearing members.

### 38.3. Timeout không chứng minh transaction chắc chắn thất bại

Một network timeout sau commit command có thể làm application chưa biết kết quả. Driver có logic retry commit theo error labels phù hợp; sau process restart, kiểm tra durable checkpoint/receipts và cho phép replay idempotent.

### 38.4. Không nuốt duplicate key của index khác

Nếu `order_read_models` có unique index nghiệp vụ và ghi projection vi phạm nó, không được catch mọi `E11000` rồi coi event đã xử lý. Receipt duplicate và business constraint duplicate là hai nguyên nhân khác nhau.

---

## 39. Quan sát và monitoring

Các metrics hữu ích:

| Metric | Câu hỏi |
| --- | --- |
| Consumer running/last successful poll | Worker còn sống không? |
| Last event processed at | Có event đang được xử lý không? |
| Last checkpoint commit at | Token có tiến không? |
| Events/sec | Throughput |
| Duplicate receipts seen | Có replay/duplicate delivery không? |
| Transaction commit errors | Target có chấp nhận effects không? |
| Resume attempts | Mạng/topology có ổn không? |
| Oplog window | Có đủ history để resume không? |
| Consumer lag | Worker đang tụt lại bao lâu? |
| In-flight/queue depth | Có backpressure không? |
| Unknown event types | Schema/DDL có đổi không? |
| Projection mismatches | Kết quả có đúng không? |
| History lost/rebootstrap count | Có cần rebuild không? |

### 39.1. Không có event không đồng nghĩa consumer chết

Một collection ít writes có thể im lặng hàng giờ. Cần health check cursor/poll, không chỉ nhìn `events/sec=0`.

### 39.2. Lag thấp không chứng minh dữ liệu đúng

Một handler có bug transform nhưng vẫn checkpoint nhanh có thể khiến dashboard lag=0 trong khi projection sai. Cần periodic reconciliation.

### 39.3. Cảnh báo theo headroom

Nếu source oplog window là 2 giờ còn consumer lag đã 90 phút và tăng, cần can thiệp trước khi token không thể resume.

---

## 40. Kiểm thử tự động: phân chia cấp độ

### Unit tests

- Mapping event type → projection action.
- Deterministic transformation.
- Receipt key chứa consumer + token.
- Unsupported event type gây lỗi.
- Retry classifier và backoff.
- Version/tombstone policy nếu bổ sung.

### Integration tests

- MongoDB replica set thật.
- Insert/update/replace/delete events.
- Checkpoint BSON round-trip.
- Transaction atomicity.
- Restart từ resumeAfter.
- Replay token cũ không áp projection lại.
- MongoDB permissions/roles phù hợp.

### Fault-injection tests

- Crash trước target transaction commit.
- Crash sau commit nhưng trước event tiếp theo.
- Resume token quá cũ.
- Downstream timeout.
- Worker lease expiration.
- Race khi đọc fullDocument updateLookup.

### End-to-end tests

- Order API ghi source.
- Consumer xây projection.
- User đọc projection.
- Nếu có notification delivery, kiểm tra idempotency ở provider/ledger.

---

## 41. Ví dụ JUnit integration test skeleton

Để chạy tự động, dùng MongoDB replica set từ Testcontainers hoặc môi trường thử nghiệm riêng, cùng Awaitility hoặc polling có deadline.

```java
@Test
void insertIsProjectedAndCheckpointed() {
    String id = "test-" + UUID.randomUUID();

    // Start consumer and wait for STREAM_READY.
    // Insert into sales.orders with _id=id.

    await()
        .atMost(Duration.ofSeconds(30))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() -> {
            assertNotNull(
                readModels.find(
                    Filters.eq("_id", id)
                ).first()
            );
        });

    assertNotNull(
        checkpoints.find(
            Filters.eq("_id", "orders-projection-v1")
        ).first()
    );

    // Stop consumer and close all resources.
}
```

Đây là skeleton vì fixture `readModels`, `checkpoints`, `await` và lifecycle của consumer phải được tạo bởi JUnit/Testcontainers project thực tế.

### 41.1. Chờ consumer sẵn sàng

Không chỉ gọi `executor.submit(consumer::run)` rồi insert ngay: worker có thể chưa mở stream khi insert diễn ra.

### 41.2. Dùng ID riêng

Mỗi test nên có `_id`, consumer ID hoặc database riêng, tránh test khác làm lệch receipt count và checkpoint.

### 41.3. Không dùng một sleep cố định

`Thread.sleep(500)` có thể pass trên laptop và fail trên CI do scheduling/network. Poll điều kiện với deadline và diagnostics.

---

## 42. Test transaction rollback

Thiết kế test hook:

```text
Inside transaction:
  insert receipt
  update projection
  save checkpoint
  throw synthetic exception before commit
```

Kỳ vọng:

- Transaction abort.
- Receipt không tồn tại.
- Projection chưa áp sự kiện.
- Checkpoint vẫn ở token cũ.
- Khi bỏ hook và restart, event được xử lý.

### 42.1. Không chạy câu lệnh throw sau commit và gọi đó là rollback test

Nếu exception phát sinh **sau commit**, dữ liệu đã commit không tự được hoàn tác. Đó là bài test replay/unknown outcome khác.

### 42.2. Failure injection ở layer phù hợp

Có thể thêm interface `FailureHook` vào consumer để đặt điểm lỗi trước commit hoặc dùng integration test riêng. Không cần tắt mongod toàn bộ chỉ để kiểm thử application transaction boundary.

---

## 43. Test xử lý lặp qua receipts

Kịch bản:

1. Consumer nhận E1.
2. Commit projection/receipt/checkpoint E1.
3. Dừng consumer.
4. Tua checkpoint về token trước E1, chỉ ở lab.
5. Khởi động consumer.
6. Nhận E1 lần nữa.
7. Assert receipt count không tăng, projection không thay đổi ngoài mong đợi.
8. Assert checkpoint sau E1 khi đã xử lý replay.

### 43.1. Đừng kiểm tra chỉ bằng log

Log `"DUPLICATE_EVENT_SKIPPED"` hữu ích nhưng không đủ chứng minh state cuối. Kiểm tra số receipt, projection state và checkpoint.

### 43.2. Test lặp không bằng cách tạo một update mới giống hệt

Hai writes cùng giá trị có thể tạo events khác nhau hoặc một update no-op không phát event tùy operation. Muốn test duplicate **cùng event**, phải thật sự replay token hoặc mô phỏng delivery event ID cũ.

---

## 44. Test two-worker concurrency

Nếu hai instances vô ý dùng chung consumer ID:

- Cả hai có thể mở stream.
- Cả hai có thể nhận cùng event.
- Một transaction receipt có thể commit, transaction còn lại đụng unique conflict hoặc write conflict.
- Checkpoint có thể bị ghi lùi nếu không có fencing và sequencing.

Bài lab **không hỗ trợ** chạy hai active consumers cùng ID. Khi nâng cấp phải bổ sung distributed ownership và test:

```text
A owns generation=10
B attempts -> rejected

A loses lease
B owns generation=11
A old transaction -> rejected by fencing
B advances checkpoint
```

Không nên coi unique receipt một mình là giải pháp cluster coordination.

---

## 45. Test `invalidate` và history lost

Trong collection lab riêng, có thể thử drop/rename rồi quan sát stream bị invalidate theo scope. Khi đó:

- Consumer không được checkpoint thành công một event không hiểu.
- Restart không tự loop `resumeAfter(invalidateToken)` mãi.
- Recovery policy phân biệt việc namespace có tồn tại hoặc phải rebuild.
- Với token quá cũ, đánh dấu `REBOOTSTRAP_REQUIRED`.

### 45.1. Không ép oplog rollover trong production

Test history lost bằng fault injection hoặc một lab riêng với oplog nhỏ/write load được kiểm soát; không tăng hàng triệu writes trên cluster thật để ép mất lịch sử.

### 45.2. Một snapshot không tái tạo được business notifications quá khứ

Nếu mục tiêu là thông báo mọi transition đã xảy ra, phải giữ domain events/outbox đủ lâu. Snapshot hiện tại chỉ tái tạo final state, không thể biết mọi event trong gap đã mất.

---

# PHẦN VIII — MỞ RỘNG SANG THÔNG BÁO THỰC TẾ

## 46. Tại sao không gọi email ngay trong Change Stream callback?

Giả sử:

```text
Change Stream event E400
          |
          v
emailProvider.send("Order paid")
          |
          v
Provider sends email
          |
          v
Network response lost
          |
          v
Consumer retries E400
          |
          v
Email may be sent twice
```

MongoDB transaction cho receipt/projection/checkpoint **không bao trùm** email provider.

### 46.1. Dùng notification intent

Thay vì gửi ngay:

```text
Change Stream
     |
     v
Create notification intent
  stable ID: "order-O100-paid-C100"
     |
     v
Checkpoint Change Stream event
     |
     v
Separate delivery worker
     |
     v
Email provider with idempotency key
```

### 46.2. Mẫu dữ liệu

```javascript
{
  _id: "notification-order-O100-paid-C100",
  businessEventId: "order-O100-paid-v2",
  recipientId: "C100",
  channel: "EMAIL",
  state: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 46.3. Side effect business-level idempotency

Dùng business event ID ổn định, không phụ thuộc việc MongoDB emit một token mới sau rebootstrap/migration.

---

## 47. Transactional outbox cho domain events

Nếu notification phải có thông tin đúng tại mốc chuyển trạng thái, có thể ghi domain event trong cùng transaction với order update:

```text
BEGIN TRANSACTION on source
    |
    +--> update order O100 status=PAID
    |
    +--> insert outbox OrderPaid event
    |
COMMIT
    |
    v
Change Stream watches outbox
    |
    v
Reliable delivery pipeline
```

Outbox event immutable:

```javascript
{
  _id: "order-O100-paid-event-v2",
  aggregateId: "O100",
  type: "OrderPaid",
  version: NumberLong("2"),
  payload: {
    customerId: "C100",
    totalMinor: NumberLong("199000")
  },
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 47.1. Outbox có thể replay lâu dài

Nếu outbox được giữ đủ lâu, consumer có thể quét pending events ngay cả khi oplog history mất. Change Stream có thể chỉ là cơ chế **đánh thức worker nhanh**, còn outbox là durable source of truth.

### 47.2. Vẫn cần delivery idempotency

Publish/email có thể thành công rồi worker crash trước khi mark delivered. Outbox không tự loại bỏ ambiguity của external provider.

### 47.3. Không lẫn lộn database change với business intent

Một admin data repair có thể update order nhưng không nên kích hoạt gửi lại `OrderPaid`. Domain event giúp tách business logic khỏi thao tác storage.

---

## 48. Khi target là search index

Ví dụ đồng bộ `orders` sang Elasticsearch/OpenSearch:

```text
MongoDB orders
    |
    v
Change Stream
    |
    v
Transform to search document
    |
    v
Search index update by stable order ID
    |
    v
Checkpoint after acknowledged result
```

Các quy tắc:

- Dùng ID ổn định của document.
- Đảm bảo eventual update/delete.
- Xử lý stale updates và out-of-order events.
- Dùng version strategy nếu sink hỗ trợ.
- Có reindex/rebootstrap path.
- Lưu checkpoint và consumer metadata.
- Theo dõi lag và mismatches.
- Không tuyên bố atomic transaction MongoDB + search engine.

---

## 49. Khi target là cache

Nếu chỉ cần invalidation:

```text
Order updated
    |
    v
Change Stream consumer
    |
    v
Invalidate cache key order:O100
```

Xóa cache key nhiều lần thường là idempotent, nhưng cũng cần:

- Không bỏ sự kiện làm cache stale vô hạn.
- TTL của cache chỉ là fallback, không thay CDC recovery.
- Khi history lost, có thể flush/rebuild cache phù hợp.
- Khi delete, invalidation vẫn phải được xử lý.
- Multi-tenant keys phải tránh đụng nhau.

Đây là trường hợp Change Stream thích hợp hơn gửi external business notifications, vì side effect `invalidate` thường an toàn khi lặp.

---

# PHẦN IX — TROUBLESHOOTING

## 50. Consumer không nhận event

Kiểm tra:

1. Source có thật là replica set/sharded cluster?
2. `rs.status()` có PRIMARY và trạng thái khỏe?
3. Java URI có tới đúng database/collection?
4. Credentials có quyền `changeStream` và `find` phù hợp?
5. Consumer đã in `STREAM_READY` trước khi tạo event?
6. Event có thuộc operation types đang xử lý?
7. Pipeline có lọc nhầm events?
8. Có một consumer khác đã ghi checkpoint mới hơn?
9. Source có majority commit đối với thay đổi cần quan sát?
10. Network, TLS và DNS có ổn không?

### 50.1. `watch()` không nhận dữ liệu cũ

Đó là behavior bình thường; cần bootstrap documents lịch sử.

### 50.2. Không thấy event do sai scope

Một consumer watch `sales.orders` không nhận thay đổi của `sales.payments`. Kiểm tra scope trước khi tăng timeout.

---

## 51. Consumer luôn nhận lại cùng event

Giả thuyết:

- Checkpoint store save thất bại.
- Resume token không được cập nhật.
- Handler throw trước transaction commit.
- Một event type không hỗ trợ khiến worker restart liên tục.
- Token bị rewind do instance cũ.
- Checkpoint collection không có quyền write.
- `loadCheckpoint()` đọc sai consumer ID.

Đo:

```javascript
db.consumer_checkpoints.findOne({
  _id: "orders-projection-v1"
});
```

và receipt:

```javascript
db.processed_changes.countDocuments();
```

### 51.1. Đừng sửa bằng cách xóa token

Xóa checkpoint rồi start ở hiện tại có thể làm mất những events chưa xử lý.

### 51.2. Tìm lỗi application trước

Nếu event luôn có fullDocument null và handler ném exception, network retries sẽ không sửa. Cần policy cho updateDescription/post-images/outbox.

---

## 52. Checkpoint có nhưng projection sai

Có thể do:

- Transformation không đúng.
- FullDocument UPDATE_LOOKUP phản ánh state khác kỳ vọng.
- Dùng nhầm `event._id` và `documentKey._id`.
- Duplicate receipt từ consumer khác.
- Target schema khác source.
- Read preference của truy vấn projection đang đọc secondary stale.
- Worker cũ ghi đè state.
- Manual rewind rồi xử lý sai thứ tự.
- Unsupported event bị bỏ qua nhưng checkpoint vẫn tiến.
- Multi-document transaction không được dùng cho effect và token.

Hãy so sánh source và target theo cùng logical point khi dữ liệu còn thay đổi, không chỉ count thô.

---

## 53. Lỗi `E11000` khi insert receipt

Có thể receipt cùng token đã tồn tại, **hoặc** có unique constraint khác.

Trong mô hình single-owner tuần tự, code lab kiểm tra receipt trước khi insert trong transaction; nếu vẫn gặp `E11000`, cần xem:

- Có hai processes cùng consumer ID?
- Transaction retry/concurrency conflict?
- Key receipt được serialize ổn định?
- Có một unique index khác trong processed collection?
- Source/target consumer ID bị chia sẻ?
- Có thao tác test/migration đã sửa state?

**Không catch mọi `MongoException` 11000 rồi coi là success**, đặc biệt khi lỗi từ projection business unique index.

---

## 54. Lỗi history lost

Biểu hiện:

- Resume từ saved token không thành công.
- Server báo resume point không còn trong change history hoặc lỗi tương đương theo release.
- Consumer đã offline lâu và oplog window ngắn.

Hành động:

1. Mark `REBOOTSTRAP_REQUIRED`.
2. Không advance checkpoint.
3. Đánh giá source of truth và target divergence.
4. Rebuild/catch-up có mốc nhất quán.
5. Xác minh tình trạng đã phục hồi trước khi báo healthy.

---

## 55. Consumer chậm dần

Đo:

- Source event rate.
- Target transaction commit latency.
- Checkpoint write pressure.
- MongoDB server CPU/IOPS.
- Oplog window.
- Reader getMore latency.
- Receipt collection/index size.
- Queue depth nếu có.
- Lỗi retry và số transaction conflicts.

Cách xử lý có thể gồm:

- Tối ưu projection indexes.
- Giảm fullDocument payload.
- Batch hợp lý.
- Tăng target capacity.
- Chia partition theo key với ordering.
- Durable queue để cách ly spike.
- Điều chỉnh receipt retention theo protocol.
- Thêm metrics và backpressure.

Không chỉ tăng số consumer instances cùng checkpoint ID; cách đó có thể tạo concurrency race.

---

# PHẦN X — CHECKLIST VÀ BÀI TẬP

## 56. Checklist hoàn thành lab

- [ ] MongoDB lab đã chạy replica set.
- [ ] Consumer có thể mở `watch()`.
- [ ] Có bốn collections theo thiết kế.
- [ ] Resume token được lưu nguyên BSON.
- [ ] Checkpoint gắn đúng consumer ID.
- [ ] Receipt key chứa consumer + event token.
- [ ] Handler hỗ trợ insert/update/replace/delete.
- [ ] Projection, receipt, checkpoint cùng transaction.
- [ ] Checkpoint chỉ commit sau projection/receipt.
- [ ] Insert tạo read model.
- [ ] Update sửa read model.
- [ ] Replace cập nhật document đầy đủ.
- [ ] Delete xóa read model.
- [ ] Restart đọc được checkpoint cũ.
- [ ] Event mới sau restart vẫn được xử lý.
- [ ] Manual rewind dẫn đến nhận diện duplicate.
- [ ] Receipt count không tăng khi replay cùng token.
- [ ] Không chạy hai consumers cùng ID trong lab.
- [ ] Biết giới hạn UPDATE_LOOKUP.
- [ ] Biết lịch sử cũ cần bootstrap.
- [ ] Biết khi nào history lost cần rebootstrap.
- [ ] Không gọi external API trong transaction callback.
- [ ] Không làm việc trên production namespace.

---

## 57. Bài tập 1 — Resume token là gì?

Một update event có:

```javascript
{
  _id: { _data: "token-A" },
  documentKey: { _id: "O100" }
}
```

**Hỏi:** Token nào được lưu để `resumeAfter`?

**Đáp án:** `event._id` / Java `event.getResumeToken()`, không phải `"O100"`.

---

## 58. Bài tập 2 — Tại sao không checkpoint trước apply?

```text
1. save token E5
2. write projection E5
3. write fails
4. restart
```

**Đáp án:** Restart từ sau E5 có thể bỏ qua event chưa áp. Phải commit effect và checkpoint cùng transaction hoặc checkpoint sau effect được ack với idempotent replay.

---

## 59. Bài tập 3 — Crash giữa apply và checkpoint

Trong kiến trúc hai writes riêng, projection thành công rồi process crash trước token save.

**Đáp án:** E5 có thể replay; handler phải idempotent. Lab tránh half-state nội bộ nhờ atomic transaction.

---

## 60. Bài tập 4 — Manual rewind

E10 đã có receipt, checkpoint bị đưa về E9, rồi consumer nhận E10.

**Đáp án:** Consumer thấy receipt, không áp lại projection; checkpoint tiến qua E10 theo protocol single-owner.

---

## 61. Bài tập 5 — Duplicate business ID

Order O100 nhận ba updates. Nếu receipt chỉ dùng O100 làm `_id`?

**Đáp án:** Update đầu tiên được ghi, hai updates sau bị hiểu nhầm duplicate. Phải dùng event identity/token hoặc business event version.

---

## 62. Bài tập 6 — `UPDATE_LOOKUP`

Order PAID rồi REFUNDED rất nhanh, consumer xử lý update PAID chậm.

**Đáp án:** Lookup có thể thấy REFUNDED. Không dùng UPDATE_LOOKUP như exact event after-image cho audit/notification lịch sử.

---

## 63. Bài tập 7 — Delete

Khi source delete O100, handler chỉ xử lý insert/update.

**Đáp án:** Target giữ stale document. Cần delete event handler hoặc tombstone theo schema.

---

## 64. Bài tập 8 — Two workers

Hai pods dùng cùng consumer ID, đều đọc E100.

**Đáp án:** Receipt có thể ngăn hai committed effects trong transaction, nhưng cần lease/fencing để bảo vệ checkpoint và ordering; không chạy hai instances như lab nguyên bản.

---

## 65. Bài tập 9 — Parallel ack

E11 chưa hoàn thành, E12 đã hoàn thành. Có thể lưu token E12 không?

**Đáp án:** Không theo protocol tuần tự/contiguous prefix, vì restart có thể skip E11.

---

## 66. Bài tập 10 — History lost

Consumer nghỉ 48 giờ, source oplog chỉ còn 6 giờ lịch sử.

**Đáp án:** Không tự xóa token rồi watch từ hiện tại. Cần rebootstrap hoặc replay từ nguồn sự kiện bền vững đủ lâu.

---

## 67. Bài tập 11 — Inbox trước email

Một worker ghi receipt xong rồi crash trước khi gửi email.

**Đáp án:** Nếu replay bỏ qua khi có receipt, email có thể mất vĩnh viễn. Cần notification intent + delivery protocol/provider idempotency, không chỉ unique receipt.

---

## 68. Bài tập 12 — Email trước inbox

Email đã gửi nhưng response timeout, worker retry.

**Đáp án:** Có thể gửi hai email. Dùng stable idempotency key ở provider hoặc chính sách xử lý outcome unknown.

---

## 69. Bài tập 13 — Event filter thay đổi

Consumer v1 chỉ xử lý inserts, v2 thêm updates nhưng dùng token v1.

**Đáp án:** Những updates lịch sử trước token v1 đã bị lọc sẽ không tự quay lại. Cần migration checkpoint/pipelineVersion hoặc rebootstrap.

---

## 70. Bài tập 14 — Outbox

Vì sao dùng outbox cho `OrderPaid` thay vì suy từ mọi update status?

**Đáp án:** Outbox chứa immutable business intent, stable event ID/version, có thể commit cùng order và giữ để replay theo retention policy.

---

## 71. Bài tập 15 — Transaction callback

`withTransaction` callback có `emailService.send()` rồi cập nhật MongoDB.

**Đáp án:** Không an toàn vì callback có thể được retry. Tách external side effect sang delivery worker với idempotency.

---

## 72. Bài tập 16 — Empty batch

`tryNext()` trả null nhiều lần liên tục.

**Đáp án:** Có thể chưa có events mới, không đồng nghĩa stream đã hết. Cần health/readiness và có thể xem post-batch token theo API.

---

## 73. Bài tập 17 — Source và target khác cluster

Có thể dùng một MongoDB transaction để commit source event, target projection và external email cùng lúc không?

**Đáp án:** Không. Cần outbox, idempotent sink, checkpoint và reconciliation xuyên hệ thống.

---

## 74. Bài tập 18 — TTL receipt

Receipt TTL 1 giờ nhưng cho phép replay sau một tuần.

**Đáp án:** Không phù hợp. Event cũ có thể được xử lý lại mà receipt đã bị xóa. Retention phải phù hợp replay horizon và business contract.

---

## 75. Bài tập 19 — Read model đã đúng nhưng lag=0

Báo cáo source/target hash khác ở 0,1% documents.

**Đáp án:** Consumer có thể transform sai hoặc skip events dù checkpoint tiến. Cần reconciliation và điều tra thay vì chỉ dựa vào lag metric.

---

## 76. Bài tập 20 — High-watermark

Reader có ba events in-flight nhưng cursor nhận postBatchResumeToken mới hơn.

**Đáp án:** Không lưu token đó làm checkpoint trước khi ba events được ack; có nguy cơ bỏ qua work sau restart.

---

## 77. Những ngộ nhận thường gặp

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Change Stream tự xử lý đúng một lần.” | Resume/retry có thể tạo duplicate; cần idempotency. |
| “Đã đọc event là được checkpoint.” | Phải xác nhận effect trước hoặc commit atomic với checkpoint. |
| “Resume token là document ID.” | Là event-level opaque BSON token. |
| “Có thể dùng clusterTime thay token.” | Timestamp không định danh mọi event riêng lẻ. |
| “Lưu token trong RAM đủ để restart.” | Phải lưu durable. |
| “Source và target khác cluster vẫn có một MongoDB transaction chung.” | Không có atomicity tự nhiên xuyên hai deployments. |
| “Unique receipt trước email bảo đảm gửi một lần.” | Có thể mất gửi nếu crash trước email. |
| “Email trước receipt thì không bị lặp.” | Có thể gửi trùng khi response unknown. |
| “Checkpoint trong transaction là không cần idempotency.” | Replay/manual rewind/side effects khác vẫn cần. |
| “Receipt theo order ID là đủ.” | Một order có nhiều events. |
| “UPDATE_LOOKUP luôn đúng state lúc event xảy ra.” | Có thể trả state mới hơn hoặc null. |
| “Delete event chắc chắn mang fullDocument.” | Thường chỉ có documentKey. |
| “Event cũ chạy lại không thể làm sai state.” | Có thể ghi đè state mới nếu thiếu ordering/version. |
| “Chạy hai consumer cùng ID tự cân bằng tải.” | Có thể xử lý trùng hoặc làm checkpoint lùi. |
| “Queue unbounded tăng reliability.” | Có thể OOM và không bền vững. |
| “Empty batch nghĩa stream kết thúc.” | Có thể chỉ tạm thời không có changes. |
| “Driver tự resume mọi lỗi mãi mãi.” | Chỉ lỗi/điều kiện được hỗ trợ. |
| “Xóa checkpoint khi history lost là recovery.” | Có thể bỏ mất changes chưa xử lý. |
| “Change Stream tự backfill dữ liệu cũ.” | Cần snapshot/backfill riêng. |
| “Lưu high-watermark luôn an toàn.” | Không được vượt các events in-flight chưa ack. |
| “Count và lag bằng nhau nghĩa dữ liệu đúng.” | Values, types và transformations vẫn có thể sai. |
| “Một receipt collection là audit log lâu dài.” | Cần retention, security và dữ liệu business phù hợp. |
| “MongoDB transaction cho phép gọi API ngoài trong callback.” | Callback retry có thể nhân đôi side effect ngoài. |

---

## 78. Tài liệu tham khảo

Các nguồn chính thức và tài liệu công cụ nên dùng khi triển khai:

1. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — phạm vi, nguyên lý và resume.
2. [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — các event types và event fields.
3. [MongoDB Manual — Change Stream Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — vận hành, oplog history và lưu ý production.
4. [MongoDB Manual — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history window, replication.
5. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity.
6. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability và majority acknowledgement.
7. [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — watch, resume và các options.
8. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction` và retries.
9. [MongoDB Java Driver — MongoChangeStreamCursor Javadoc](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/MongoChangeStreamCursor.html) — cursor API, `getResumeToken`, `tryNext`.
10. [MongoDB Java Driver — ChangeStreamIterable Javadoc](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/ChangeStreamIterable.html) — `resumeAfter`, `startAfter`, options.
11. [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — khi cần ảnh tài liệu trước/sau thay đổi.
12. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — giới hạn retries và error behavior.
13. [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — connector-based pipelines.
14. [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — integration tests có MongoDB thật.
15. [Awaitility Usage](https://github.com/awaitility/awaitility/wiki/Usage) — polling với deadline cho tests bất đồng bộ.

Tài liệu trên mô tả **một lab tổng hợp**. API/exception types và behavior có thể khác theo Java Driver, MongoDB Server, FCV và topology. Trước production, cần đối chiếu version và thực hiện Content QA, integration/performance tests, failure-injection tests và security review theo quy trình dự án.

---

## 79. Kết luận

Để triển khai Change Stream có thể **tiếp tục sau restart** và **chống xử lý lặp**, một consumer cần nhiều hơn một vòng lặp đọc events:

- **Resume token:** lưu nguyên dạng BSON, bền vững, theo đúng consumer scope.
- **Checkpoint:** chỉ advance sau khi effect được xác nhận hoặc commit cùng effect trong transaction phù hợp.
- **Receipt/idempotency:** đánh dấu event đã xử lý, nhận diện replay mà không lặp tác dụng phụ.
- **Ordering:** chỉ một active reader tuần tự trong lab; production cần lease/fencing/per-key ordering khi scale.
- **Recovery:** resume từ checkpoint nếu history còn, không âm thầm bỏ events khi history lost.
- **Bootstrap:** có cách đưa dữ liệu lịch sử vào target mà không bỏ lọt changes lúc backfill.
- **Observability:** theo dõi event lag, oplog window, duplicate receipts, checkpoint progress và mismatches.
- **Giới hạn transaction:** target MongoDB transaction không bảo đảm đúng một lần cho email/payment/hệ thống khác; cần outbox và business idempotency.

Trong bài lab, `order_read_models`, `processed_changes` và `consumer_checkpoints` cùng được commit bằng một MongoDB transaction. Nhờ vậy, khi một event đã commit, **dữ liệu đích, bằng chứng đã xử lý và mốc tiếp tục nhất quán với nhau**. Đây là nền tảng để mở rộng thành các hệ thống đồng bộ và thông báo có khả năng khôi phục đáng tin cậy.
