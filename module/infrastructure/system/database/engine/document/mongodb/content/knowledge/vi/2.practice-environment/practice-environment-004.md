# Khởi tạo replica set phục vụ thực hành giao dịch và change stream

MongoDB có thể chạy như một máy chủ **standalone**, nhưng hai tính năng quan trọng để học cách xây dựng ứng dụng có trạng thái là **giao dịch nhiều tài liệu (multi-document transactions)** và **change streams** cần một triển khai **replica set** hoặc **sharded cluster**. Bài này thiết lập môi trường replica set trên máy phát triển, kiểm tra trạng thái của các thành viên, rồi thực thi một giao dịch và quan sát thay đổi dữ liệu theo thời gian thực.

## 1. Mục tiêu và kiến thức nền

Sau khi thực hành, bạn có thể:

1. Phân biệt máy chủ standalone với một replica set và hiểu vai trò của **primary**, **secondary**, **oplog** và cơ chế bầu chọn.
2. Khởi tạo một replica set một thành viên bằng Docker để chạy nhanh giao dịch và change stream.
3. Xác nhận node đã trở thành primary, dùng đúng connection string của replica set và lưu dữ liệu qua lần khởi động lại.
4. Thực hiện giao dịch chuyển số dư giữa hai tài liệu, đồng thời quan sát sự kiện insert/update/delete qua change stream.
5. Mở rộng thành replica set ba thành viên để khảo sát sao chép và failover khi cần.

**Replica set** là nhóm tiến trình `mongod` cùng duy trì một tập dữ liệu logic. Thông thường, ứng dụng ghi vào **primary**; các **secondary** sao chép các thao tác qua **oplog** (operation log) và có thể được bầu làm primary mới khi node hiện tại không còn khả dụng. Trong replica set ba thành viên có quyền bầu chọn, đa số là hai thành viên.

Đối với **transaction**, replica set cung cấp hạ tầng session và điều phối commit cần thiết để cập nhật nhiều tài liệu như một đơn vị nguyên tử. Đối với **change stream**, MongoDB đọc tiến trình thay đổi từ oplog và phát các sự kiện của thao tác đã được majority commit. Thao tác trên một tài liệu riêng lẻ vẫn có tính nguyên tử ngay cả khi không dùng transaction; giao dịch phát huy tác dụng khi nhiều thao tác phải thành công hoặc thất bại cùng nhau.

| Môi trường | Giao dịch nhiều tài liệu | Change stream | Sao chép và failover |
| --- | --- | --- | --- |
| Standalone | Không | Không | Không |
| Replica set một thành viên | Có | Có | Không có node dự phòng |
| Replica set ba thành viên | Có | Có | Có thể thực hành sao chép, bầu chọn và failover |

**Lựa chọn thực hành:** bắt đầu bằng replica set **một thành viên** để tập trung vào transaction và change stream. Chỉ cần phần ba thành viên ở mục 6 khi muốn thực hành khả năng sẵn sàng cao. Một thành viên đáp ứng yêu cầu về tính năng nhưng **không cung cấp dự phòng dữ liệu hay failover**.

## 2. Chuẩn bị môi trường

Cần có Docker Engine hoặc Docker Desktop đang chạy, cổng **27017** trên máy chưa bị chiếm và một cửa sổ terminal (PowerShell, Bash hoặc terminal tương đương). Các ví dụ dùng Docker image **mongo:8.0** để các bước có cùng dòng phiên bản; máy chủ MongoDB khác phiên bản có thể hiển thị thông tin trạng thái hơi khác.

Kiểm tra Docker:

~~~bash
docker version
docker ps
~~~

Image MongoDB chính thức đã chứa công cụ **mongosh**, nên bạn không bắt buộc phải cài MongoDB Shell trên máy host. Trong phần một thành viên, cổng được xuất ra địa chỉ loopback **127.0.0.1** của host nhằm tránh mở máy chủ không bật xác thực ra mạng ngoài. Đây là cấu hình học tập; khi triển khai hệ thống thật phải dùng xác thực, phân quyền, bảo mật mạng và cấu hình replica set phù hợp.

## 3. Tạo replica set một thành viên

### 3.1. Khởi động tiến trình MongoDB

Chạy lần lượt các lệnh sau trong terminal của host:

~~~bash
docker volume create mongo-rs-lab-data

docker run -d --name mongo-rs-lab --hostname mongo-rs-lab -p 127.0.0.1:27017:27017 -v mongo-rs-lab-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all

docker ps
~~~

Ý nghĩa các tham số:

- **--replSet rs0**: bật chế độ replica set với tên logic là `rs0`; tên này phải trùng với cấu hình khởi tạo và connection string.
- **--bind_ip_all**: cho tiến trình `mongod` lắng nghe trên các interface của container; cổng public vẫn bị giới hạn ở loopback của host bởi tùy chọn `-p`.
- **-v mongo-rs-lab-data:/data/db**: lưu dữ liệu, oplog và cấu hình của replica set trong một Docker named volume, tránh mất khi thay container.
- **--name mongo-rs-lab**: đặt tên container để tiện dùng lệnh `docker exec`, `docker logs`, `docker stop` và `docker start`.

Nếu container vừa chạy mà shell chưa kết nối được, xem log để chờ MongoDB khởi động:

~~~bash
docker logs mongo-rs-lab
~~~

### 3.2. Khởi tạo cấu hình replica set

Mở shell ngay trong container:

~~~bash
docker exec -it mongo-rs-lab mongosh
~~~

Trong giao diện `mongosh`, thực thi JavaScript:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
})
~~~

Kết quả thành công có trường **ok: 1**. Địa chỉ `localhost:27017` được chọn có chủ đích cho môi trường **một node**: chính tiến trình MongoDB trong container nhìn thấy bản thân qua địa chỉ này; một client chạy trực tiếp trên host cũng truy cập được cùng địa chỉ vì Docker đã ánh xạ cổng 27017.

**Chỉ chạy rs.initiate() một lần cho bộ dữ liệu mới.** Nếu volume đã chứa cấu hình replica set của lần chạy trước, hãy kiểm tra trạng thái hiện có bằng `rs.status()` thay vì khởi tạo lại. Việc khởi động lại container với cùng volume không yêu cầu tái khởi tạo.

### 3.3. Đợi bầu primary và xác minh

Tiếp tục chạy trong `mongosh`:

~~~javascript
rs.status()
db.hello()
db.adminCommand({ ping: 1 })
~~~

Sau khi bầu chọn hoàn thành, các dấu hiệu quan trọng là:

- Trong `rs.status()`, trường **set** là `rs0`, **myState** bằng `1`, thành viên hiện tại có **stateStr** là `PRIMARY`.
- Trong `db.hello()`, **setName** là `rs0` và **isWritablePrimary** là `true`.
- Lệnh `ping` trả về **ok: 1**, xác nhận máy chủ phản hồi.

Nếu ban đầu thấy `STARTUP2`, `RECOVERING` hoặc chưa có primary, đợi tiến trình bầu chọn rồi truy vấn lại trạng thái. Khi dùng replica set một node, thường chỉ mất một khoảng ngắn để node trở thành primary.

Từ máy host có cài `mongosh`, kết nối qua URI:

~~~bash
mongosh "mongodb://localhost:27017/?replicaSet=rs0"
~~~

Hoặc tiếp tục dùng shell bên trong container:

~~~bash
docker exec -it mongo-rs-lab mongosh "mongodb://localhost:27017/?replicaSet=rs0"
~~~

Connection string mẫu cho ứng dụng chạy **trực tiếp trên host**:

~~~text
mongodb://localhost:27017/replica_lab?replicaSet=rs0
~~~

Đối với Spring Boot, ví dụ cấu hình môi trường học tập là:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/replica_lab?replicaSet=rs0
~~~

Chỉ thêm tùy chọn `directConnection=true` khi hiểu rõ mục đích kết nối trực tiếp đến một node. Với replica set nhiều node, ứng dụng thường cần **topology discovery** để driver tìm primary và chuyển node sau failover; không nên dùng tùy chọn này như giải pháp mặc định cho lỗi phân giải hostname.

## 4. Kiểm chứng transaction trên replica set

Ví dụ chuyển **200 đơn vị** từ tài khoản A sang B. Điều kiện nghiệp vụ: không được trừ tiền ở A mà bỏ lỡ cộng tiền ở B. Để tránh dữ liệu cũ ảnh hưởng kết quả, chuẩn bị một bộ tài liệu xác định.

Mở `mongosh` kết nối với replica set và chạy:

~~~javascript
const lab = db.getSiblingDB("replica_lab");

lab.accounts.deleteMany({});
lab.accounts.insertMany([
  { _id: "A", balance: 1000 },
  { _id: "B", balance: 500 }
]);

lab.accounts.find().sort({ _id: 1 }).toArray();
~~~

Bắt đầu một **session**, rồi mở transaction và thực thi cả hai phép cập nhật qua database thuộc session đó:

~~~javascript
const session = db.getMongo().startSession();

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const accounts = session.getDatabase("replica_lab").accounts;

  const debit = accounts.updateOne(
    { _id: "A", balance: { $gte: 200 } },
    { $inc: { balance: -200 } }
  );
  if (debit.modifiedCount !== 1) {
    throw new Error("Khong du so du hoac khong tim thay tai khoan A");
  }

  const credit = accounts.updateOne(
    { _id: "B" },
    { $inc: { balance: 200 } }
  );
  if (credit.modifiedCount !== 1) {
    throw new Error("Khong tim thay tai khoan B");
  }

  session.commitTransaction();
  print("Giao dich da commit");
} catch (error) {
  if (session.inTransaction()) {
    session.abortTransaction();
  }
  print("Giao dich loi: " + error.message);
} finally {
  session.endSession();
}

db.getSiblingDB("replica_lab").accounts.find().sort({ _id: 1 }).toArray();
~~~

Sau khi commit thành công, tài khoản A có **800**, B có **700** và tổng số dư vẫn là **1.500**. Nếu một bước phát sinh lỗi trước commit, transaction được abort; các cập nhật chưa commit không trở thành trạng thái dữ liệu cuối cùng.

Để thấy hành vi rollback một cách riêng biệt, tạo session mới, thay đổi A rồi chủ động abort:

~~~javascript
const rollbackSession = db.getMongo().startSession();
rollbackSession.startTransaction();

rollbackSession.getDatabase("replica_lab").accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: -50 } }
);

rollbackSession.abortTransaction();
rollbackSession.endSession();

db.getSiblingDB("replica_lab").accounts.find().sort({ _id: 1 }).toArray();
~~~

Số dư vẫn phải là A = 800 và B = 700 vì thay đổi **-50** chưa được commit. Trong ứng dụng thực, nên dùng API **withTransaction** hoặc cơ chế retry theo hướng dẫn của MongoDB driver để xử lý lỗi giao dịch tạm thời, cùng tình huống không xác định được kết quả commit khi mất kết nối. Không tự động chạy lại một giao dịch có tác dụng phụ bên ngoài cơ sở dữ liệu mà chưa thiết kế tính idempotent.

**Lưu ý:** không đặt write concern riêng cho từng thao tác nằm trong transaction; cấu hình write concern ở cấp transaction/commit. Snapshot read concern hỗ trợ góc nhìn nhất quán; majority write concern yêu cầu commit được xác nhận ở mức đa số thành viên.

## 5. Quan sát change stream trực tiếp

Change stream cho phép một client đăng ký nhận sự kiện khi tài liệu thay đổi. Ví dụ này dùng **hai phiên mongosh đồng thời**. Sự kiện phát sau khi watch được mở, vì change stream không tự phát lại toàn bộ dữ liệu đã tồn tại.

### 5.1. Terminal A: mở luồng theo dõi

Trong terminal A, kết nối replica set rồi chuẩn bị collection (chỉ tạo nếu chưa có):

~~~javascript
const eventDb = db.getSiblingDB("replica_lab");
if (!eventDb.getCollectionNames().includes("events")) {
  eventDb.createCollection("events");
}

const stream = eventDb.events.watch(
  [
    {
      $match: {
        operationType: { $in: ["insert", "update", "delete"] }
      }
    }
  ],
  { fullDocument: "updateLookup" }
);

print("Dang doi 3 su kien...");
for (let i = 0; i < 3; i++) {
  const change = stream.next();
  printjson({
    type: change.operationType,
    key: change.documentKey,
    fullDocument: change.fullDocument,
    resumeToken: change._id
  });
}
stream.close();
~~~

Vòng lặp sẽ **chờ** cho đến khi nhận đủ ba sự kiện. Hãy giữ terminal A đang chạy và thực hiện bước tiếp theo ở terminal B.

### 5.2. Terminal B: tạo thay đổi

Trong terminal B, mở thêm một `mongosh` vào cùng replica set. Chạy:

~~~javascript
const eventDb = db.getSiblingDB("replica_lab");

eventDb.events.insertOne({
  _id: "evt-1",
  kind: "lab",
  value: 1,
  createdAt: new Date()
});

eventDb.events.updateOne(
  { _id: "evt-1" },
  { $set: { value: 2 } }
);

eventDb.events.deleteOne({ _id: "evt-1" });
~~~

Terminal A lần lượt nhận các sự kiện có **operationType** là `insert`, `update` và `delete`. Mỗi sự kiện thường chứa:

| Trường | Ý nghĩa |
| --- | --- |
| `_id` | Resume token để tiếp tục theo dõi sau sự kiện đã xử lý |
| `operationType` | Loại thay đổi: insert, update, delete, replace, v.v. |
| `ns` | Database và collection phát sinh sự kiện |
| `documentKey` | Định danh tài liệu bị thay đổi, thường gồm `_id` |
| `fullDocument` | Tài liệu đầy đủ khi có sẵn; với `updateLookup`, MongoDB truy vấn phiên bản hiện tại cho update |
| `updateDescription` | Các trường cập nhật hoặc bị loại bỏ đối với sự kiện update |

Giá trị **fullDocument** của update không nhất thiết là ảnh chụp tài liệu tại đúng thời điểm update: các thao tác tiếp theo có thể diễn ra trước khi lookup hoàn tất. Khi tài liệu đã bị xóa, lookup có thể trả về `null`. Sự kiện delete không chứa tài liệu đã bị xóa trong `fullDocument` như một bản sao đầy đủ.

### 5.3. Resume token và phạm vi theo dõi

Sau khi đọc một sự kiện, ứng dụng có thể lưu `change._id` để mở lại change stream với tham số **resumeAfter**:

~~~javascript
// Ví dụ giả định savedToken là _id từ một sự kiện đã xử lý.
const resumedStream = db.getSiblingDB("replica_lab").events.watch(
  [],
  { resumeAfter: savedToken }
);
~~~

Đoạn trên minh họa cách dùng API; **savedToken phải là token thực tế**, được ứng dụng lưu từ sự kiện trước đó. Khi dùng trong chương trình, chỉ cập nhật token đã lưu sau khi xử lý thành công sự kiện tương ứng, nhằm tránh bỏ mất công việc khi ứng dụng khởi động lại.

Change stream có thể mở ở cấp collection, database hoặc deployment tùy API và quyền truy cập. Nó phụ thuộc vào **oplog**, vì vậy khả năng tiếp tục chỉ được bảo đảm khi lịch sử cần thiết còn nằm trong cửa sổ oplog. Nếu lịch sử quá cũ, ứng dụng có thể nhận lỗi **ChangeStreamHistoryLost** và cần quy trình tái đồng bộ thích hợp. Change stream không thay thế hàng đợi thông điệp bền vững hay cơ chế xử lý trùng lặp/idempotency của ứng dụng.

## 6. Mở rộng: replica set ba thành viên

Một node giúp kích hoạt tính năng nhưng không cho thấy sao chép hoặc bầu chọn. Khi muốn quan sát hành vi **primary → secondary**, có thể dùng Docker Compose với ba MongoDB container chung một Docker network.

Tạo file **compose.mongo-rs.yml** trong một thư mục thực hành riêng với nội dung:

~~~yaml
services:
  mongo1:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    volumes:
      - mongo1-data:/data/db

  mongo2:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    volumes:
      - mongo2-data:/data/db

  mongo3:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    volumes:
      - mongo3-data:/data/db

volumes:
  mongo1-data:
  mongo2-data:
  mongo3-data:
~~~

Khởi động ba tiến trình:

~~~bash
docker compose -f compose.mongo-rs.yml up -d
docker compose -f compose.mongo-rs.yml ps
docker compose -f compose.mongo-rs.yml exec mongo1 mongosh
~~~

Trong shell của **mongo1**, khởi tạo replica set:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1:27017" },
    { _id: 1, host: "mongo2:27017" },
    { _id: 2, host: "mongo3:27017" }
  ]
})
~~~

Các tên **mongo1**, **mongo2**, **mongo3** là DNS service nội bộ của Docker Compose. Chúng giải quyết được từ các container trong cùng network; không tự động phân giải được từ terminal hoặc JVM chạy trực tiếp trên host.

Kiểm tra trong container:

~~~javascript
rs.status()
rs.conf()
db.hello()
~~~

Đợi cho đến khi có một node `PRIMARY` và hai node `SECONDARY`. Có thể dùng connection string sau **từ một container nằm trong cùng Docker network**:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/replica_lab?replicaSet=rs0
~~~

Nếu cần chạy ứng dụng Java trên host với replica set ba container, phải thiết kế hostname/port được phân giải và truy cập **nhất quán** từ cả thành viên replica set lẫn Java driver. Chỉ publish cổng 27017/27018/27019 mà giữ các host nội bộ `mongo1` trong `rs.conf()` thường dẫn đến lỗi discovery từ host; đây là vấn đề địa chỉ mạng chứ không phải lỗi transaction. Đối với bài học cơ bản trên host, dùng replica set một thành viên ở mục 3 sẽ đơn giản hơn.

Để luyện failover, xác định primary hiện tại trong `rs.status()`, dừng **đúng container primary đó**, rồi quan sát primary mới được bầu ở hai node còn lại. Thời gian bầu chọn có thể làm thao tác ghi tạm thời thất bại; driver có cấu hình phù hợp sẽ tìm primary mới. Sau đó khởi động lại node đã dừng và kiểm tra nó gia nhập replica set. Replica set ba node chịu được một thành viên không khả dụng trong điều kiện hai thành viên còn lại có thể liên lạc và tạo đa số.

## 7. Các lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Transaction numbers are only allowed on a replica set member or mongos` | MongoDB còn chạy standalone hoặc client nối nhầm instance | Kiểm tra `--replSet`, `rs.status()`, `db.hello()` và URI |
| `The $changeStream stage is only supported on replica sets` | Chưa kết nối vào replica set/sharded cluster | Khởi tạo `rs.initiate()`, đợi có primary và kết nối đúng node |
| `ReplicaSetNoPrimary` / server selection timeout | Chưa bầu xong, node bị dừng, hoặc hostname/port trong cấu hình không tới được từ client | Kiểm tra `rs.status()`, Docker logs và từng hostname trong `rs.conf()` |
| `getaddrinfo ENOTFOUND mongo1` từ host | Tên DNS Docker Compose chỉ tồn tại trong network container | Chạy client cùng network hoặc cấu hình địa chỉ replica set reachable từ host |
| `not primary` hoặc `NotWritablePrimary` | Node đang là secondary hoặc trong lúc chuyển primary | Chờ bầu chọn, dùng replica set URI để driver khám phá primary |
| `ChangeStreamHistoryLost` / không thể resume | Oplog không còn sự kiện tương ứng với resume token | Xây dựng đường khôi phục/tái đồng bộ dữ liệu và lưu token thường xuyên |
| `Unauthorized` | MongoDB có bật xác thực nhưng client thiếu thông tin đăng nhập/quyền | Cấp credentials và role đúng; không tắt bảo mật cho môi trường thật |
| Port 27017 đã được sử dụng | Instance MongoDB hoặc container khác chiếm cổng | Dừng instance xung đột hoặc thiết kế ánh xạ và URI khác cho bài lab |

Một cách chẩn đoán theo thứ tự là xác nhận container còn chạy, MongoDB trả lời `ping`, replica set có primary, tên replica set đúng trong URI, rồi kiểm tra các hostname thành viên có truy cập được từ **vị trí thực tế của client** hay không.

## 8. Duy trì và dọn dẹp môi trường lab

Với replica set một thành viên:

~~~bash
docker stop mongo-rs-lab
docker start mongo-rs-lab
docker exec -it mongo-rs-lab mongosh
~~~

Lần khởi động lại, kiểm tra `rs.status()` và dữ liệu trong `replica_lab`. Named volume giúp MongoDB giữ cấu hình replica set và dữ liệu giữa các lần restart. Khi không cần container, có thể chạy `docker rm -f mongo-rs-lab`; thao tác này **không tự xóa named volume**. Chỉ xóa volume khi đã chấp nhận mất toàn bộ dữ liệu thực hành.

Với ba thành viên:

~~~bash
docker compose -f compose.mongo-rs.yml stop
docker compose -f compose.mongo-rs.yml start
docker compose -f compose.mongo-rs.yml ps
~~~

Không dùng tùy chọn xóa volume của Docker Compose nếu muốn giữ dữ liệu. Sau mỗi lần restart, replica set có thể cần một khoảng ngắn để xác định primary trước khi nhận ghi.

## 9. Kết quả mong đợi sau bài thực hành

Bạn có một triển khai MongoDB với `rs0` đã được khởi tạo, kiểm tra được trạng thái primary và sử dụng được URI mang tham số `replicaSet=rs0`. Giao dịch chuyển tiền cập nhật đồng thời hai tài khoản hoặc rollback toàn bộ; change stream nhận các sự kiện dữ liệu sau khi đăng ký theo dõi. Nếu sử dụng thêm ba thành viên, bạn có thể khảo sát cách secondary đồng bộ và cách replica set tiếp tục hoạt động sau khi primary không khả dụng.

Đối với dịch vụ thực tế, replica set còn cần thiết kế bền vững hơn bài lab: ít nhất ba thành viên phù hợp, giám sát replication lag và oplog, backup/restore, bảo mật kết nối, quy trình nâng cấp, kiểm thử failover và chiến lược retry của driver. Những yêu cầu đó nằm ngoài mục tiêu khởi tạo môi trường thực hành ở đây.
