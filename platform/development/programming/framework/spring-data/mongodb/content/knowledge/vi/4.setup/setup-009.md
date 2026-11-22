# Chuẩn bị replica set khi bài thực hành cần transaction hoặc change stream

## 1. Mục tiêu và bối cảnh

Trong module **SPRING_DATA_MONGODB**, ứng dụng Spring sử dụng Spring Data MongoDB để kết nối MongoDB, ánh xạ document Java, truy vấn qua repository hoặc `MongoTemplate`, thực hiện aggregation, tạo index, quản lý transaction, truy cập reactive và chẩn đoán hiệu năng. Một số bài học chỉ cần MongoDB chạy ở chế độ độc lập (*standalone*), nhưng hai nhóm bài thực hành sau cần một topology phù hợp:

- **Transaction trên nhiều document/collection:** ví dụ tạo đơn hàng và ghi bản ghi outbox trong cùng một transaction MongoDB.
- **Change stream:** ứng dụng theo dõi sự kiện insert, update, replace, delete của collection và phản ứng khi dữ liệu thay đổi.

MongoDB hỗ trợ hai khả năng này trên **replica set** (hoặc triển khai sharded cluster phù hợp). Một `mongod` standalone thông thường không đủ để thực hành các tính năng đó.

Bài này hướng dẫn thiết lập **replica set một nút** tên `rs0` trên máy phát triển, kiểm tra nó đã có PRIMARY, cấu hình kết nối từ ứng dụng Spring, chạy phép thử transaction và change stream, rồi xử lý những lỗi kết nối hay gặp.

> **Phạm vi:** replica set một nút đủ để học transaction và change stream, nhưng **không có tính sẵn sàng cao** và không mô phỏng được bầu chọn/failover giữa nhiều nút. Với môi trường vận hành thực tế, cần thiết kế replica set nhiều nút, bảo mật, backup, giám sát và quy trình nâng cấp riêng.

## 2. Replica set là gì và vì sao hai tính năng này cần nó?

Một **replica set** là nhóm các tiến trình MongoDB `mongod` duy trì cùng một tập dữ liệu thông qua cơ chế replication. Trong topology phổ biến có:

- **PRIMARY:** nhận thao tác ghi thông thường và phát sinh các mục trong operation log (*oplog*).
- **SECONDARY:** sao chép các thay đổi từ oplog; có thể trở thành PRIMARY sau một cuộc bầu chọn khi đủ điều kiện.
- **Cơ chế bầu chọn và số đông (majority):** chi phối việc chọn PRIMARY và các bảo đảm liên quan đến xác nhận ghi trong cấu hình nhiều nút.

**Oplog** là lịch sử thao tác có thứ tự dùng cho replication. **Change stream** sử dụng hạ tầng này để phát các sự kiện thay đổi cho client; vì vậy chạy `$changeStream` trên standalone sẽ bị từ chối.

**Multi-document transaction** sử dụng client session và cơ chế điều phối giao dịch của MongoDB. MongoDB không hỗ trợ loại transaction này trên một `mongod` standalone. Với một replica set đã khởi tạo, transaction có thể trải qua nhiều document/collection, tùy phiên bản máy chủ, cấu hình và giới hạn của hệ thống.

Một replica set **một nút** vẫn có PRIMARY và oplog sau khi `rs.initiate()` thành công. Tuy nhiên, chỉ một nút thì mất nút đó đồng nghĩa mất khả năng phục vụ; `w: "majority"` trong topology một nút cũng không tạo ra bản sao dữ liệu độc lập.

| Cấu hình | Ghi document | Multi-document transaction | Change stream | Chịu lỗi mất một nút |
| --- | --- | --- | --- | --- |
| Standalone `mongod` | Có | Không | Không | Không |
| Replica set một nút | Có | Có | Có | Không |
| Replica set nhiều nút, đủ quorum | Có | Có | Có | Tùy số nút, quorum và cấu hình |
| Sharded cluster phù hợp | Có | Có | Có | Tùy kiến trúc và cấu hình |

Đừng nhầm **transaction**, **change stream** và **replication**: transaction phục vụ tính nguyên tử/nhất quán của nhóm thao tác; change stream cung cấp luồng sự kiện; replication sao chép dữ liệu và là cơ sở hạ tầng cần thiết cho các tính năng trên.

## 3. Điều kiện trước khi thực hành

Ví dụ bên dưới giả định:

- Máy phát triển có **Docker Engine/Docker Desktop** và có thể chạy container Linux; hoặc đã cài `mongod` và `mongosh` để chạy trực tiếp.
- Cổng TCP **27017** trên máy phát triển chưa bị một dịch vụ khác chiếm.
- Java/Spring Boot và Spring Data MongoDB đã có trong ứng dụng. Đối với ví dụ cấu hình, phần YAML sử dụng cách đặt thuộc tính của **Spring Boot 3.x**; khi dùng phiên bản Spring Boot khác, cần kiểm tra tên thuộc tính và starter tương ứng với phiên bản đó.
- Bài thử chạy **trên máy phát triển**, chưa bật xác thực MongoDB. Cổng chỉ được publish lên loopback (`127.0.0.1`), không mở trực tiếp trên Internet.

Trong bài, ta đặt:

| Giá trị | Ý nghĩa |
| --- | --- |
| `rs0` | Tên replica set |
| `mongodb-rs0` | Tên Docker container |
| `127.0.0.1:27017` | Địa chỉ MongoDB nhìn từ ứng dụng chạy trên host |
| `spring_mongo_lab` | Database dùng để thực hành |
| `orders`, `outbox` | Hai collection minh họa transaction |
| `mongo-rs0-data` | Docker volume giữ dữ liệu sau khi dừng/chạy lại container |

> **Lưu ý về môi trường:** hướng dẫn Docker ở mục 4 giả định **ứng dụng Spring chạy trên máy host**, ngoài Docker. Nếu ứng dụng chạy trong một container khác, hãy xem mục 8 về DNS và địa chỉ thành viên replica set, vì `localhost` trong mỗi container chỉ trỏ về chính container đó.

## 4. Cách A — tạo replica set một nút bằng Docker

Đây là cách thuận tiện để bắt đầu mà không cần cài trực tiếp `mongod` trên máy host.

### Bước 1: chạy MongoDB ở chế độ replica set

Trong terminal (PowerShell, Bash hoặc terminal tương đương), chạy:

```bash
docker run -d --name mongodb-rs0 -p 127.0.0.1:27017:27017 -v mongo-rs0-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all
```

Ý nghĩa các thành phần chính:

- `mongo:8.0`: ví dụ image MongoDB phiên bản 8.0. Có thể dùng phiên bản khác nếu tương thích với bài học; nên cố định dòng phiên bản để môi trường thực hành ổn định.
- `--replSet rs0`: yêu cầu `mongod` chạy dưới tên replica set `rs0`.
- `--bind_ip_all`: cho `mongod` lắng nghe trên các giao diện bên trong container. Ánh xạ `-p 127.0.0.1:27017:27017` giới hạn cổng publish trên host về loopback.
- `-v mongo-rs0-data:/data/db`: giữ dữ liệu khi container bị dừng/xóa rồi tạo lại với volume đó.

Kiểm tra container:

```bash
docker ps --filter name=mongodb-rs0
docker logs mongodb-rs0
```

Thao tác chạy `mongod` với `--replSet` **chưa đủ**: phải khởi tạo cấu hình replica set ở bước sau.

### Bước 2: mở `mongosh` trong container

```bash
docker exec -it mongodb-rs0 mongosh
```

Từ đây, các lệnh trong khối `javascript` được nhập **trực tiếp tại dấu nhắc `mongosh`**, không phải tại PowerShell. Cách nhập tương tác này cũng tránh lỗi escape dấu nháy khi lồng JavaScript vào lệnh `docker exec` trên Windows.

Khởi tạo replica set một nút:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Đặt `host: "localhost:27017"` vì cả MongoDB và ứng dụng được thực hành theo topology **một container MongoDB + ứng dụng chạy trực tiếp trên host**. Client trên host có thể kết nối qua cổng publish và nhận địa chỉ thành viên `localhost:27017` khi driver khám phá replica set.

Nếu `rs.initiate()` trả về `ok: 1`, cấu hình đã được chấp nhận. Sau khi nút được bầu làm PRIMARY, có thể ghi dữ liệu.

**Không chạy lại `rs.initiate()` mỗi lần khởi động.** Cấu hình replica set được lưu trong data volume. Nếu đã khởi tạo, gọi lại sẽ báo lỗi vì replica set đã được cấu hình.

### Bước 3: xác minh PRIMARY

Tiếp tục trong `mongosh`:

```javascript
rs.status().set;
rs.status().members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  health: m.health
}));
db.adminCommand({ hello: 1 }).isWritablePrimary;
```

Kết quả mong đợi:

- `rs.status().set` là `rs0`.
- Có một phần tử `members` với `stateStr: "PRIMARY"` và `health: 1`.
- `isWritablePrimary` bằng `true`.

Ngay sau khi khởi tạo, nút có thể chưa kịp chuyển sang PRIMARY. Nếu chưa thấy PRIMARY, kiểm tra lại `rs.status()` và `docker logs mongodb-rs0` để tìm nguyên nhân.

Có thể kiểm tra oplog đã có hay chưa:

```javascript
db.getSiblingDB("local").getCollection("oplog.rs").stats().count;
```

Số mục oplog thay đổi theo hoạt động; mục đích là xác nhận collection oplog của replica set tồn tại, không phải yêu cầu một con số nhất định.

### Bước 4: kết nối từ máy host

Thoát `mongosh` bằng `exit`. Nếu host cũng cài `mongosh`, thử kết nối:

```bash
mongosh "mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0"
```

Lệnh này không bắt buộc nếu ứng dụng dùng Java driver trực tiếp. URI dành cho ứng dụng trên host là:

```text
mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0
```

`replicaSet=rs0` yêu cầu driver xác nhận đúng tên replica set; nó **không tự bật replica set** cho một máy chủ đang chạy standalone. Tên `rs0` phải khớp cấu hình đã khởi tạo.

### Bước 5: dừng và chạy lại môi trường

```bash
docker stop mongodb-rs0
docker start mongodb-rs0
```

Data volume vẫn giữ dữ liệu và cấu hình replica set. Nếu phải tạo lại container với cùng volume, cần bảo đảm tên, port và cấu hình khởi động khớp; không được xóa dữ liệu một cách vô ý.

## 5. Cách B — dùng `mongod` cài trực tiếp trên máy

Nếu MongoDB Server và `mongosh` đã được cài trên máy host, có thể chạy một `mongod` riêng cho bài học. Ví dụ lệnh sau giả định thư mục dữ liệu đã tồn tại và đường dẫn phù hợp với hệ điều hành:

```bash
mongod --dbpath ./mongo-rs0-data --port 27017 --bind_ip 127.0.0.1 --replSet rs0
```

Mở một terminal khác:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Trong `mongosh`, thực hiện một lần:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Sau khi PRIMARY sẵn sàng, kiểm tra như mục 4. Cần tạo thư mục `mongo-rs0-data` trước khi chạy `mongod`, bảo đảm quyền ghi dữ liệu và tránh trùng port với một instance MongoDB khác.

**Chỉ thực hiện một trong hai cách A hoặc B trên cùng cổng 27017**, trừ khi cố ý đổi port. Nếu cả hai cùng chạy, một tiến trình sẽ không thể bind vào cổng đó.

## 6. Kiểm chứng transaction ngay trong `mongosh`

Sau khi replica set có PRIMARY, ta thử một transaction ghi vào hai collection `orders` và `outbox`. Hai insert phải cùng được commit hoặc được hủy nếu transaction không hoàn thành.

Mở `mongosh`:

```bash
docker exec -it mongodb-rs0 mongosh
```

Tạo session và chạy transaction:

```javascript
const session = db.getMongo().startSession();
const lab = session.getDatabase("spring_mongo_lab");

try {
  session.startTransaction();

  lab.orders.insertOne({
    _id: "tx-order-001",
    status: "PLACED",
    total: NumberDecimal("2500000")
  });

  lab.outbox.insertOne({
    _id: "tx-event-001",
    orderId: "tx-order-001",
    type: "ORDER_PLACED"
  });

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
```

Kiểm tra cả hai document sau khi commit:

```javascript
const checkDb = db.getSiblingDB("spring_mongo_lab");
checkDb.orders.findOne({ _id: "tx-order-001" });
checkDb.outbox.findOne({ _id: "tx-event-001" });
```

Cả hai phải tồn tại. Nếu chạy lại ví dụ nguyên trạng, ID đã có sẽ gây lỗi trùng khóa; hãy dùng ID mới cho mỗi lần thực hành hoặc chủ động xử lý dữ liệu thử nghiệm.

Thử **rollback** bằng một ID khác:

```javascript
const rollbackSession = db.getMongo().startSession();
const rollbackDb = rollbackSession.getDatabase("spring_mongo_lab");

try {
  rollbackSession.startTransaction();
  rollbackDb.orders.insertOne({
    _id: "tx-order-rollback",
    status: "PLACED"
  });
  rollbackSession.abortTransaction();
} finally {
  rollbackSession.endSession();
}

db.getSiblingDB("spring_mongo_lab")
  .orders.findOne({ _id: "tx-order-rollback" });
```

Kết quả mong đợi là `null`: document vừa thêm đã bị hủy cùng transaction.

**Lưu ý:**

- Transaction thực hành sử dụng MongoDB session; lệnh ghi phải được gọi từ collection có liên kết với **cùng session**. Ghi bằng một kết nối/collection khác nằm ngoài session sẽ không tự gia nhập transaction.
- Transaction minh họa không bao gồm lời gọi HTTP, hệ thanh toán bên ngoài hoặc thao tác trên cơ sở dữ liệu khác. Một MongoDB transaction không biến nhiều hệ thống độc lập thành một transaction phân tán duy nhất.
- Với hệ thống cần tính nhất quán mạnh về độ bền, hãy xác định `readConcern`, `writeConcern` ở mức phù hợp, cách xử lý lỗi commit và retry. Một node với `majority` không tương đương khả năng chịu lỗi của replica set nhiều node.

## 7. Kiểm chứng change stream ngay trong `mongosh`

Để nhìn thấy sự kiện, cần **hai terminal** kết nối tới replica set. Nếu dùng Docker, ở cả hai terminal có thể mở:

```bash
docker exec -it mongodb-rs0 mongosh
```

### Terminal A: bắt đầu lắng nghe

Nhập trong `mongosh`:

```javascript
const watchDb = db.getSiblingDB("spring_mongo_lab");
const stream = watchDb.orders.watch([
  { $match: { operationType: "insert" } }
]);

while (stream.hasNext()) {
  printjson(stream.next());
}
```

Vòng lặp sẽ chờ khi chưa có sự kiện. Điều này là bình thường vì change stream là luồng theo dõi liên tục. Khi hoàn tất bài thử, dùng `Ctrl+C` để dừng vòng lặp.

### Terminal B: phát sinh dữ liệu mới

Nhập trong `mongosh` của terminal B:

```javascript
db.getSiblingDB("spring_mongo_lab").orders.insertOne({
  _id: "cs-order-001",
  status: "NEW",
  createdAt: new Date()
});
```

Terminal A sẽ nhận một sự kiện có `operationType: "insert"`, `ns` cho biết namespace, `documentKey._id` là ID document, thường có `fullDocument` và `_id` ở cấp sự kiện là **resume token**.

Dòng lệnh `watch()` theo dõi những thay đổi phát sinh **sau khi stream bắt đầu** (trừ khi cấu hình tùy chọn khởi động/tiếp tục thích hợp). Nó không phải truy vấn tải lại toàn bộ các đơn đã tồn tại từ trước.

Muốn xem nhiều loại thay đổi, có thể bỏ `$match` hoặc đặt điều kiện cho `update`, `replace`, `delete`. Với update, `fullDocument` không mặc định luôn chứa bản document mới hoàn chỉnh; hãy hiểu rõ lựa chọn `fullDocument: "updateLookup"` và sự khác biệt giữa nội dung update và trạng thái hiện tại được tra cứu.

### Resume token và tiêu thụ tin cậy

Change stream event có resume token để client có thể nối lại từ một mốc nếu kết nối gián đoạn. Ứng dụng thực tế cần:

1. Xử lý sự kiện theo cách **idempotent**, vì khi reconnect/retry vẫn có thể xử lý lặp.
2. Lưu token ở nơi bền vững **sau khi** xử lý dữ liệu thành công theo một chiến lược phù hợp.
3. Sử dụng tùy chọn resume khi tạo lại stream.
4. Theo dõi khoảng lưu giữ oplog: nếu lịch sử cần resume đã bị loại khỏi oplog, token quá cũ có thể không còn dùng được.

Change stream không mặc định mang ý nghĩa “exactly once” cho các side effect ngoài MongoDB. Nếu đang xây dựng hàng đợi công việc hoặc đồng bộ hệ thống ngoài, cần thiết kế cơ chế retry, chống trùng và phục hồi rõ ràng.

## 8. Chuỗi kết nối và vấn đề hostname trong replica set

Sau khi kết nối vào một seed host, MongoDB driver có thể khám phá danh sách thành viên replica set bằng địa chỉ mà server **quảng bá** trong cấu hình `rs.conf()`. Vì vậy, mạng và DNS là điểm hay khiến bài thực hành bị kẹt.

### 8.1. Ứng dụng Spring chạy trên host

Dùng topology đã thiết lập ở mục 4:

```text
Ứng dụng Spring (host)
    |
    | mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0
    v
Cổng Docker publish 127.0.0.1:27017
    |
    v
MongoDB container (rs0 / PRIMARY)
  rs.conf(): member host = localhost:27017
```

Máy host có thể phân giải `localhost`, nên driver tìm lại thành viên được quảng bá. Việc sử dụng seed `127.0.0.1` và member `localhost` ở đây đều chỉ một máy host.

### 8.2. Ứng dụng Spring nằm trong container khác

Nếu ứng dụng chạy trong cùng Docker network với dịch vụ MongoDB có tên `mongo`, thành viên replica set nên quảng bá địa chỉ DNS mà **container ứng dụng cũng phân giải và kết nối được**, chẳng hạn `mongo:27017`. URI phía container ứng dụng có dạng:

```text
mongodb://mongo:27017/spring_mongo_lab?replicaSet=rs0
```

Một cấu hình thành viên tương ứng khi khởi tạo **môi trường mới dành cho các container**:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo:27017" }
  ]
});
```

Địa chỉ `mongo` trong ví dụ phải thực sự là tên DNS của MongoDB trong Docker network, và `mongod` phải có thể phân giải tên đó khi khởi tạo.

**Không thay tùy tiện `localhost` thành `mongo` trong replica set đã chạy chỉ vì đổi nơi đặt ứng dụng.** Cần kiểm tra topology, DNS ở cả hai phía và điều chỉnh cấu hình theo quy trình thích hợp. Địa chỉ phù hợp với container có thể không phân giải được từ host, và ngược lại.

### 8.3. `directConnection=true` có giải quyết mọi vấn đề không?

Tham số `directConnection=true` có thể hữu ích trong một số bài thử Docker một nút khi địa chỉ thành viên được quảng bá không truy cập được từ bên ngoài, bởi driver được yêu cầu kết nối trực tiếp tới seed. Tuy nhiên, nó **không thay thế thiết kế hostname có thể truy cập trong topology thật**, và không phải cách chữa mọi lỗi transaction/change stream hay cấu hình replica set nhiều nút.

Trước khi thêm tùy chọn đó, nên kiểm tra:

```javascript
rs.conf()._id;
rs.conf().members.map(m => m.host);
rs.status().members.map(m => m.stateStr);
```

Nếu client nhìn thấy hostname không thể phân giải hoặc không có PRIMARY, hãy sửa đúng vấn đề cấu hình/kết nối. Với bài thực hành đơn nút trên host ở mục 4, URI có `replicaSet=rs0` là lựa chọn rõ ràng.

## 9. Kết nối Spring Boot với replica set

### 9.1. Dependency và cấu hình URI

Ví dụ cho ứng dụng **Spring Boot 3.x** dùng truy cập đồng bộ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

Cấu hình trong `application.yml`:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0
```

Nếu đang dùng dự án Gradle, cần dependency tương đương. Với ứng dụng reactive, dùng starter MongoDB reactive phù hợp phiên bản framework:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Chỉ thêm cả hai starter đồng bộ/reactive nếu ứng dụng thực sự cần cả hai cách truy cập. **Không tự suy đoán tên property/starter giữa các phiên bản Spring Boot:** các ví dụ này được đặt trong phạm vi Boot 3.x; với Boot 4.x hoặc bản tùy biến, kiểm tra tài liệu cấu hình phiên bản đang dùng.

Để tránh nhập sai mật khẩu trong file nguồn khi bật xác thực ở môi trường khác, nên đưa URI và thông tin nhạy cảm qua environment variable hoặc cơ chế quản lý secret thay vì commit vào repository.

### 9.2. Đăng ký `MongoTransactionManager` cho truy cập đồng bộ

Spring Data MongoDB cung cấp `MongoTransactionManager` để liên kết `@Transactional` với MongoDB client session. Ví dụ một class cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory mongoDatabaseFactory
    ) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
```

Sau đó, một service có thể thực hiện hai insert trong cùng transaction:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LabOrderService {
    private final MongoTemplate mongoTemplate;

    public LabOrderService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional
    public void createOrderAndOutbox(String orderId) {
        mongoTemplate.insert(
            new Document("_id", orderId)
                .append("status", "PLACED"),
            "orders"
        );

        mongoTemplate.insert(
            new Document("_id", "event-" + orderId)
                .append("orderId", orderId)
                .append("type", "ORDER_PLACED"),
            "outbox"
        );
    }
}
```

Ví dụ chỉ minh họa **phạm vi transaction MongoDB**. Trong ứng dụng thật cần xử lý idempotency, tình trạng ghi trùng ID, validation và retry theo loại lỗi. `@Transactional` hoạt động khi phương thức được gọi qua proxy Spring thích hợp; gọi nội bộ trong cùng object (*self-invocation*) có thể không kích hoạt transaction theo cơ chế proxy mặc định.

**Kiểm chứng rollback:** tạo một trường hợp có lỗi ở insert thứ hai (chẳng hạn cố tình trùng `_id` ở collection `outbox`) rồi kiểm tra insert thứ nhất không còn sau khi transaction bị hủy. Bài thử nên được thực hiện trên dữ liệu thử nghiệm tách biệt để tránh nhầm với lần chạy trước.

### 9.3. Transaction trong reactive application

Với stack reactive, dùng `ReactiveMongoTransactionManager` thay cho transaction manager đồng bộ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory mongoDatabaseFactory
    ) {
        return new ReactiveMongoTransactionManager(mongoDatabaseFactory);
    }
}
```

Trong reactive flow, transaction context được truyền qua Reactor context; có thể áp dụng `@Transactional` lên phương thức trả về `Mono`/`Flux` hoặc dùng `TransactionalOperator` khi cần phạm vi giao dịch tường minh. Tránh trộn lẫn thao tác blocking với reactive và tránh gọi `subscribe()` thủ công bên trong service rồi giả định toàn bộ các bước vẫn thuộc cùng transaction.

## 10. Theo dõi change stream bằng Spring Data MongoDB

Ngoài cách theo dõi với `mongosh`, Spring Data MongoDB cung cấp API change stream cho mã Java. Với cách reactive, có thể viết một phương thức trả về `Flux`:

```java
import org.bson.Document;
import reactor.core.publisher.Flux;

import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderChangeStreamService {
    private final ReactiveMongoTemplate template;

    public OrderChangeStreamService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<Document>> watchOrders() {
        return template.changeStream(
            "orders",
            ChangeStreamOptions.builder().build(),
            Document.class
        );
    }
}
```

Bên nhận `Flux` cần quản lý subscription, logging, xử lý lỗi, reconnect, resume token và giới hạn tải. Việc khai báo `Flux` đơn thuần chưa bắt đầu lắng nghe; stream chỉ chạy khi có subscription. Với hệ thống sản xuất, xử lý side effect phải có idempotency và cách checkpoint token sau khi hoàn tất công việc.

Để lọc sự kiện, có thể truyền aggregation filter tương ứng cho `ChangeStreamOptions`. Khi muốn biết tài liệu hiện hành sau một lần update, cần hiểu tùy chọn `fullDocument`; không phải lúc nào sự kiện update cũng mang sẵn toàn bộ document mới.

Đối với ứng dụng imperative, Spring Data còn có cơ chế lắng nghe change stream dùng `MongoTemplate` và `MessageListenerContainer`; chọn API theo mô hình luồng xử lý của ứng dụng. Một change stream không thay thế truy vấn ban đầu nếu màn hình hoặc service cần tải cả dữ liệu đã tồn tại từ trước lúc subscribe.

## 11. Index và aggregation sau khi replica set sẵn sàng

Replica set là **điều kiện topology** cho transaction/change stream, nhưng không tự tối ưu truy vấn. Khi module tiến đến phần aggregation, index và chẩn đoán hiệu năng, vẫn cần thiết kế index theo cách ứng dụng thực sự truy vấn.

Ví dụ, nếu thường lấy đơn của khách theo thời gian:

```javascript
use spring_mongo_lab
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "c-01" })
         .sort({ createdAt: -1 })
         .limit(20)
         .explain("executionStats");
```

Lưu ý các document thử nghiệm từ mục transaction chưa có `customerId` hoặc `createdAt`; cần chèn dữ liệu phù hợp khi thực hành truy vấn này. `explain("executionStats")` giúp quan sát kế hoạch truy vấn, số index key/document được xem xét và hiệu năng trên dữ liệu có ý nghĩa; một collection quá nhỏ khó phản ánh workload thật.

Với change stream, không nên tạo nhiều client hoặc pipeline quá rộng không cần thiết. Luồng theo dõi kéo dài có chi phí duy trì kết nối và xử lý sự kiện. Khi mở rộng nhiều consumer, hãy giám sát độ trễ xử lý, khả năng bắt kịp oplog và lỗi khôi phục stream.

## 12. Các lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra và hướng xử lý |
| --- | --- | --- |
| `Transaction numbers are only allowed on a replica set member or mongos` | Kết nối tới standalone | Kiểm tra `--replSet` và `rs.status()`; khởi tạo replica set rồi kết nối lại |
| `$changeStream stage is only supported on replica sets` | Server không ở topology hỗ trợ change stream | Kiểm tra replica set đã được khởi tạo; không dùng `watch()` trên standalone |
| `not primary` / `NotWritablePrimary` | Chưa có PRIMARY hoặc client đi tới nút không nhận ghi | Kiểm tra `rs.status().members` và khả năng bầu chọn; thử lại khi topology ổn định |
| `ReplicaSetNoPrimary` / `ServerSelectionTimeoutException` | Driver không tìm được PRIMARY hoặc không kết nối được địa chỉ thành viên | Kiểm tra port, container, DNS, `rs.conf().members[*].host`, network và URI |
| URI khai báo `replicaSet=rs0` nhưng tên set khác | Không khớp tên replica set | Đối chiếu `rs.conf()._id` và URI |
| App trên host không truy cập được `mongo:27017` | `mongo` chỉ là DNS trong Docker network | Dùng topology hostname dành cho host hoặc cấu hình DNS/network phù hợp |
| App trong container kết nối `localhost:27017` thất bại | `localhost` trỏ tới chính app container | Dùng hostname MongoDB có thể truy cập trong Docker network và khai báo member tương ứng |
| `rs.initiate()` báo đã khởi tạo | Lệnh đã chạy trước đó; cấu hình lưu trong volume | Đọc `rs.status()`, tránh init lại |
| Lỗi duplicate key khi chạy thử transaction lần nữa | Dùng lại các `_id` của lần trước | Tạo ID mới hoặc làm sạch dữ liệu thử nghiệm có kiểm soát |
| Change stream không thấy dữ liệu cũ | `watch()` bắt đầu theo dõi từ thời điểm khởi tạo | Chạy lệnh insert sau khi bắt đầu stream; nếu cần dữ liệu cũ, truy vấn riêng |
| Resume token hết hiệu lực / thiếu lịch sử | Sự kiện nằm ngoài khoảng oplog còn giữ | Xây dựng quy trình tái đồng bộ và checkpoint, giám sát oplog window |
| Giao dịch bị hủy hoặc phát sinh conflict | Tranh chấp cập nhật, lỗi mạng, lỗi commit hay giới hạn transaction | Phân biệt lỗi có thể retry; áp dụng retry/idempotency theo MongoDB driver và nghiệp vụ |
| Không có quyền gọi `watch()` khi bật auth | User thiếu quyền theo dõi thích hợp | Kiểm tra role và quyền truy cập collection/database |

Các lệnh gợi ý để tự kiểm tra:

```javascript
rs.conf()._id;
rs.conf().members.map(m => m.host);
rs.status().members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  health: m.health
}));
db.adminCommand({ hello: 1 });
```

Và trên host:

```bash
docker ps --filter name=mongodb-rs0
docker logs mongodb-rs0
```

Nếu `rs.status()` lỗi trong môi trường Docker, trước hết xác nhận lệnh đã chạy trong `mongosh` kết nối đúng container. Một số lỗi tưởng là transaction hoặc change stream thực chất là **kết nối nhầm instance** MongoDB standalone đang chiếm cổng 27017.

## 13. Kiểm thử phù hợp trước khi học transaction/change stream sâu hơn

Để xác nhận bài setup đã sẵn sàng, nên kiểm tra theo thứ tự:

1. **Topology:** `rs.status()` trả về tên `rs0`, có PRIMARY; `hello.isWritablePrimary` là `true`.
2. **Khả năng kết nối:** ứng dụng Spring truy cập URI đúng, tạo và đọc một document bằng repository hoặc `MongoTemplate`.
3. **Transaction:** hai insert thuộc cùng session được commit cùng nhau; khi chủ động abort hoặc gây lỗi ở thao tác sau, kết quả trước đó được rollback.
4. **Change stream:** bắt đầu `watch()` trước, sau đó insert document mới ở terminal khác và quan sát event nhận được.
5. **Ứng dụng reactive (nếu có):** khởi động subscription thật, kiểm tra xử lý event, hủy subscription và hành vi khi kết nối gián đoạn.
6. **Truy vấn/index:** tạo index cần thiết, chạy truy vấn có dữ liệu đại diện và xem `explain("executionStats")`.
7. **Khả năng khởi động lại:** dùng `docker stop`/`docker start`, xác nhận replica set giữ cấu hình và có thể phục hồi kết nối sau khi PRIMARY hoạt động trở lại.

Các phép thử này xác nhận **môi trường kỹ thuật đã sẵn sàng**; chúng không chứng minh toàn bộ logic transaction, exactly-once, tính nhất quán giữa nhiều hệ thống hoặc khả năng chịu lỗi của cluster sản xuất.

## 14. Những điều cần đổi khi triển khai nhiều nút thực tế

Môi trường lab một nút đơn giản hóa nhiều vấn đề. Khi vận hành một replica set thật, cần tính thêm:

- **Quorum và khả năng chịu lỗi:** thường thiết kế số lượng thành viên bỏ phiếu hợp lý (ví dụ ba nút dữ liệu ở các failure domain thích hợp) để vẫn duy trì majority khi mất một nút. Việc chỉ thêm thành viên mà thiếu phân bố hoặc năng lực hạ tầng không tự tạo tính sẵn sàng cao.
- **Tên máy và mạng:** mỗi member quảng bá hostname ổn định, phân giải được từ những client cần khám phá topology và từ các member; không cấu hình mọi member là `localhost`.
- **Bảo mật:** bật xác thực client, xác thực nội bộ giữa các member, TLS và phân quyền tối thiểu; hạn chế network và quản lý secret đúng cách.
- **Độ bền và nhất quán:** thiết kế write concern/read concern phù hợp, test failover, rollback do replication và cơ chế retry.
- **Oplog và change stream:** giám sát cửa sổ oplog, tốc độ ghi, độ trễ consumer và cách khôi phục khi token không còn hiệu lực.
- **Vận hành:** backup/restore, monitoring, nâng cấp phiên bản, quy trình xử lý lỗi và kiểm thử hỗn loạn có kiểm soát.

Không nên sao chép nguyên lệnh Docker lab `--bind_ip_all` cộng với MongoDB không xác thực lên máy chủ công cộng. Ở bài này, việc publish chỉ trên `127.0.0.1` là một điều kiện an toàn quan trọng của ví dụ.

## 15. Tổng kết và checklist sẵn sàng thực hành

Trước khi bắt đầu các bài Spring Data MongoDB về transaction hoặc change stream, xác nhận:

- [ ] MongoDB chạy với `--replSet rs0`, đã `rs.initiate()` đúng một lần và có PRIMARY.
- [ ] Driver dùng URI tới đúng server, đúng replica set và hostname thành viên có thể truy cập.
- [ ] Thử transaction trong `mongosh` thành công, gồm cả trường hợp abort.
- [ ] Thử `watch()` trước khi insert và nhận sự kiện đúng.
- [ ] Spring Boot đã có starter MongoDB phù hợp, cấu hình kết nối đúng theo phiên bản đang dùng.
- [ ] Đã đăng ký transaction manager phù hợp cho imperative/reactive nếu thực hành `@Transactional`.
- [ ] Phân biệt được lỗi replica set, lỗi DNS, lỗi auth, lỗi transaction và lỗi resume token.
- [ ] Hiểu rằng replica set **một nút chỉ phục vụ môi trường học tập**, chưa cung cấp failover thực tế.

Sau khi hoàn tất những bước trên, môi trường đã có nền tảng để thực hành truy vấn với repository và `MongoTemplate`, aggregation, index, transaction trên nhiều document, change stream, reactive access, kiểm thử tích hợp và chẩn đoán hiệu năng dữ liệu trong **Spring Data MongoDB**. Quan trọng nhất là tách bạch hai vấn đề: **replica set làm cho tính năng khả dụng**, còn **tính đúng đắn và độ tin cậy của nghiệp vụ** phụ thuộc thêm vào cách dùng session, transaction boundary, điều kiện truy vấn, xử lý retry và thiết kế dữ liệu.

