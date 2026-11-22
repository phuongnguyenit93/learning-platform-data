# TTL ở cấp bản ghi, trường hoặc collection theo khả năng của từng hệ

## 1. TTL giải quyết bài toán gì trong vòng đời dữ liệu?

Không phải mọi dữ liệu đều cần được giữ vô thời hạn. Một hệ thống có thể muốn:

- Mã OTP chỉ có hiệu lực trong 5 phút.
- Phiên đăng nhập (session) hết hạn sau 30 phút không hoạt động.
- Cache kết quả truy vấn được làm mới sau 2 phút.
- Sự kiện thiết bị được giữ 30 ngày để phân tích ngắn hạn.
- Log kỹ thuật được giữ 7 ngày, sau đó chuyển sang kho lưu trữ hoặc xóa.
- Các bản ghi thử nghiệm được tự động thu dọn để tránh tăng chi phí.

**TTL (Time To Live)** là cơ chế xác định thời gian sống của một đối tượng dữ liệu hoặc một phần dữ liệu. Sau khi hết hạn, hệ thống có thể coi dữ liệu là không hợp lệ, không còn hiển thị trong truy vấn hoặc tiến hành xóa theo cơ chế của từng cơ sở dữ liệu.

Ví dụ:

```text
10:00:00  Ghi session S1 với TTL = 30 phút
    |
    |  Có thể đọc và sử dụng nếu chưa hết hạn
    v
10:30:00  Mốc hết hạn logic
    |
    |  Hệ quản trị có thể chưa dọn byte vật lý ngay
    v
10:30:xx  Tác vụ nền / truy cập / compaction xử lý dữ liệu hết hạn
```

**Hai sự kiện phải được phân biệt:**

1. **Hết hạn logic (logical expiration):** theo hợp đồng, dữ liệu không còn được xem là hợp lệ.
2. **Dọn dẹp vật lý (physical deletion/reclamation):** database loại bỏ bản ghi hoặc thu hồi dung lượng trên đĩa/bộ nhớ.

Nhiều hệ NoSQL thực hiện bước thứ hai **bất đồng bộ**. Do đó, TTL thường là cơ chế quản lý vòng đời và chi phí lưu trữ, **không phải đồng hồ bảo đảm xóa vật lý chính xác đến từng mili giây**.

### 1.1. TTL nằm ở đâu trong kiến trúc?

```text
                        Dữ liệu nghiệp vụ
                               |
                 Xác định chính sách vòng đời
                               |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
    Hết hạn key/item      Hết hạn field/cell    Chính sách tập dữ liệu
        |                      |                      |
        v                      v                      v
     Redis key             Cassandra cell        Collection/table/index
     DynamoDB item         Redis hash field       Default TTL / retention
     MongoDB document*                            theo khả năng sản phẩm

* MongoDB TTL index đặt trên field Date nhưng xóa toàn document.
```

Một yêu cầu "TTL 7 ngày" là chưa đủ. Cần nói rõ **đơn vị nào hết hạn**, **tính từ khi nào** và **điều gì xảy ra khi nó hết hạn**.

## 2. Các khái niệm nền tảng: TTL, expireAt và retention

### 2.1. TTL tương đối

TTL tương đối có dạng:

\[
expiresAt = startTime + duration
\]

Ví dụ một cache key được ghi lúc 10:00 với TTL 120 giây thì mốc hết hạn là 10:02.

`startTime` có thể là:

- Thời điểm tạo bản ghi;
- Thời điểm ghi/cập nhật gần nhất;
- Thời điểm một trường được ghi;
- Thời điểm hệ thống xác nhận một hoạt động hợp lệ.

Quy tắc nào được dùng tùy database và API ghi. Không được tự suy rằng **mọi thao tác UPDATE đều gia hạn TTL**.

### 2.2. Thời điểm hết hạn tuyệt đối

Một số hệ sử dụng trường `expiresAt` hoặc `expireAt` thay vì đếm từ lúc ghi:

```json
{
  "sessionId": "S100",
  "createdAt": "2026-11-14T08:00:00Z",
  "expiresAt": "2026-11-14T08:30:00Z"
}
```

Ở đây, `expiresAt` là mốc nghiệp vụ. Với MongoDB, giá trị trong tài liệu thực tế nên là **BSON Date** nếu dùng TTL index; với DynamoDB TTL, thường là **Number theo Unix epoch seconds**. Cùng tên trường không có nghĩa các hệ dùng cùng kiểu dữ liệu.

### 2.3. TTL và thời hạn lưu giữ (retention)

TTL có thể là công cụ thực thi một phần chính sách **retention**, nhưng chúng không đồng nghĩa:

- TTL: cơ chế hết hạn của key, item, cell hoặc document.
- Retention: quy định **giữ loại dữ liệu nào trong bao lâu**, ai có quyền truy cập, khi nào lưu trữ/xóa, có ngoại lệ pháp lý hay không.
- Archiving: chuyển dữ liệu ít dùng sang kho lưu trữ khác.
- Purging: xóa dữ liệu khỏi một hay nhiều hệ theo chính sách.

Ví dụ log cần giữ 90 ngày để điều tra, rồi mới xóa. Nếu đặt TTL 7 ngày trong database mà không có bản lưu trữ hợp lệ, hệ thống có thể **mất dữ liệu cần dùng**.

### 2.4. Absolute TTL và sliding expiration

**Hết hạn tuyệt đối:** phiên kết thúc ở một thời điểm cố định dù người dùng có hoạt động.

**Sliding expiration:** phiên được gia hạn khi có hoạt động hợp lệ.

```text
Absolute:
10:00 tạo phiên
10:20 hoạt động
10:30 vẫn hết hạn

Sliding:
10:00 tạo phiên, hạn 10:30
10:20 hoạt động -> hạn mới 10:50
10:45 hoạt động -> hạn mới 11:15
```

Một hệ có thể kết hợp **idle timeout 30 phút** và **absolute lifetime 24 giờ**. Khi gia hạn, phải bảo đảm không vượt giới hạn tuyệt đối:

\[
effectiveExpiry = \min(lastActivity + idleTimeout,\ createdAt + maxLifetime)
\]

TTL do database cung cấp chỉ là một phần của chính sách. Nếu cần giới hạn tuyệt đối, ứng dụng vẫn phải giữ và kiểm tra mốc tương ứng.

## 3. Các cấp độ TTL cần phân biệt

### 3.1. TTL ở cấp key/item/document

Toàn bộ đối tượng có cùng vòng đời. Khi hết hạn, dữ liệu của key/item/document bị xóa hoặc không còn được coi là tồn tại theo cơ chế sản phẩm.

Ví dụ:

```json
{
  "sessionId": "S100",
  "userId": "U42",
  "issuedAt": "2026-11-14T08:00:00Z",
  "expiresAt": "2026-11-14T08:30:00Z",
  "device": "mobile"
}
```

Nếu TTL cấp document áp dụng cho `S100`, thì **toàn bộ document session** hết hạn, không phải chỉ trường `device`.

### 3.2. TTL ở cấp field/column/cell

Chỉ một giá trị thuộc tính có vòng đời riêng. Phần còn lại của record có thể tiếp tục tồn tại.

Ví dụ khái niệm:

```text
user U42:
    displayName = "An"              (không TTL)
    lastOtpCode = "123456"          (TTL 5 phút)
    marketingPreference = true      (không TTL)
```

Nếu hệ hỗ trợ field/cell TTL thật sự, `lastOtpCode` có thể hết hạn mà `displayName` vẫn còn. Nếu database **không** hỗ trợ, ứng dụng cần tách OTP thành một key/document riêng hoặc tự xóa trường bằng job.

### 3.3. TTL ở cấp collection, table, bucket hoặc index

Một chính sách mặc định có thể được khai báo trên một nhóm dữ liệu:

- Mọi document của một collection được xét theo trường thời gian.
- Mọi cell được ghi vào một bảng có default TTL.
- Mọi item trong container có TTL mặc định.
- Những index dữ liệu theo ngày được xóa theo chính sách vòng đời.

**Quan trọng:** “TTL cấp collection” có ít nhất hai ý nghĩa khác nhau:

1. **Chính sách áp dụng cho các bản ghi trong collection**: sau thời hạn, các bản ghi riêng lẻ được loại bỏ.
2. **Xóa toàn bộ collection/index như một đơn vị**: phù hợp dữ liệu phân vùng thời gian, ví dụ xóa index log của một ngày.

Đừng đồng nhất hai cơ chế chỉ vì đều được cấu hình ở cấp nhóm dữ liệu.

### 3.4. Bảng so sánh nhanh

| Hệ / cơ chế | Cấp thường được hỗ trợ | Điểm cần nhớ |
|---|---|---|
| Redis | Key | `EXPIRE`, `SET ... EX/PX` áp dụng cho cả key |
| Redis phiên bản hỗ trợ hash-field expiration | Field trong hash | `HEXPIRE` / `HPEXPIRE`; cần kiểm tra phiên bản |
| MongoDB | Document qua TTL index trên field Date | Field được đánh index là căn cứ hết hạn; **xóa toàn document** |
| MongoDB time-series | Collection time-series / bucket dữ liệu | Chính sách hết hạn dựa trên time field; dọn bất đồng bộ |
| DynamoDB | Item dựa vào thuộc tính epoch seconds | TTL cấu hình theo table và một attribute; xóa cả item |
| Cassandra / ScyllaDB | Giá trị cell/column; default ở table | TTL có thể khác nhau giữa các cell; tạo tombstone khi hết hạn |
| Azure Cosmos DB for NoSQL | Item; mặc định theo container | `defaultTtl` ở container và `_ttl` từng item |
| Cloud Firestore | Document theo timestamp field trong collection group | Chính sách gắn với field, nhưng **xóa document** |
| Couchbase | Document; chính sách tối đa ở bucket/collection | Expiry document và giới hạn mặc định theo cấu hình |
| Elasticsearch/OpenSearch | Thường retention ở index/data stream | Chính sách rollover/delete index; không mặc định TTL cho từng field |

Bảng mô tả hướng phổ biến, không thay thế tài liệu sản phẩm. Phiên bản, edition và loại dịch vụ managed có thể thay đổi API hoặc phạm vi hỗ trợ.

## 4. Redis: TTL cấp key và trường hash ở phiên bản hỗ trợ

Redis đặc biệt phổ biến để lưu cache, session, rate-limit metadata hoặc trạng thái tạm thời. Redis có cơ chế expiration trực tiếp cho **key**.

### 4.1. Tạo key có TTL ngay lúc ghi

```redis
SET session:S100 "U42" EX 1800
```

Lệnh trên tạo/ghi key và đặt TTL 1.800 giây (30 phút). Có thể đặt độ chính xác mili giây bằng `PX`:

```redis
SET cache:product:P100 "cached-value" PX 120000
```

Hai lệnh trên thể hiện TTL tương đối.

### 4.2. Đặt TTL cho key đã tồn tại

```redis
SET otp:U42 "934812"
EXPIRE otp:U42 300
```

`EXPIRE` dùng đơn vị giây; `PEXPIRE` dùng mili giây.

Đo TTL còn lại:

```redis
TTL otp:U42
PTTL otp:U42
```

Với Redis, `TTL` thường trả:

- Số giây còn lại khi key có thời hạn;
- `-1` khi key tồn tại nhưng không có expiration;
- `-2` khi key không tồn tại (bao gồm trường hợp đã hết hạn theo ngữ nghĩa truy cập).

Nếu thao tác `SET` ghi đè giá trị của key, thời hạn cũ có thể bị xóa theo ngữ nghĩa mặc định của lệnh. Có các tùy chọn như `KEEPTTL` khi muốn giữ TTL trong phiên bản hỗ trợ:

```redis
SET session:S100 "U42:updated" KEEPTTL
```

**Đừng giả định mọi UPDATE đều bảo toàn TTL hoặc tự gia hạn TTL**. Cần xét từng command và phiên bản.

### 4.3. Key-level TTL khác field-level TTL

Giả sử:

```redis
HSET user:U42 displayName "An" lastOtp "934812"
EXPIRE user:U42 300
```

`EXPIRE user:U42 300` áp dụng cho **toàn bộ key hash**. Sau 5 phút, cả `displayName` và `lastOtp` có thể biến mất. Nếu chỉ muốn OTP hết hạn, đây là mô hình sai.

Một cách tương thích rộng hơn là tách TTL field thành key khác:

```redis
HSET user:U42 displayName "An"
SET otp:U42 "934812" EX 300
```

Khi đó `user:U42` và `otp:U42` có vòng đời độc lập.

### 4.4. Hash-field expiration trong Redis mới

Redis từ **7.4** có hỗ trợ hết hạn đối với field trong hash thông qua những command như `HEXPIRE` và `HPEXPIRE`. Ví dụ khi chạy trên phiên bản có tính năng:

```redis
HSET session:S100 userId "U42" otp "934812"
HEXPIRE session:S100 300 FIELDS 1 otp
```

Mục tiêu là field `otp` hết hạn sau 300 giây trong khi `userId` còn được giữ.

Điểm cần nhớ:

- Đây **không phải** khả năng có ở mọi phiên bản Redis hoặc mọi dịch vụ Redis-compatible.
- TTL cấp field chỉ áp dụng cho cấu trúc và API được hỗ trợ, không biến mọi loại object thành document có TTL trường tùy ý.
- Cần kiểm tra những thao tác cập nhật field nào có thể thay đổi/giữ thời hạn.
- Lệnh truy vấn TTL của field có API riêng; không được dùng `TTL key` để suy ra TTL của từng hash field.

Nếu môi trường chưa hỗ trợ, tách key vẫn là giải pháp thực dụng.

### 4.5. Redis hết hạn bằng cơ chế nào?

Redis có cách kiểm tra khi truy cập và xử lý key hết hạn chủ động ở nền. Vì vậy, mốc TTL không đồng nghĩa mọi byte được thu hồi đúng tại thời điểm đó.

Trong nhiều tình huống, khi truy cập một key đã hết hạn, Redis coi key là không còn giá trị sử dụng. Nhưng nếu nghiệp vụ cần một hành động xảy ra chính xác tại mốc thời gian, ví dụ giải phóng ghế rồi đồng thời thanh toán, **chỉ đợi key tự biến mất không đủ**.

### 4.6. Một ví dụ không nên phụ thuộc TTL như khóa giao dịch

```text
SET seat:E1:A12 booking:B1 NX EX 180
```

Đây là một cách tạo claim tạm thời ở Redis, nhưng **không tự đảm bảo** rằng callback thanh toán cũ của B1 không xác nhận sau khi TTL hết và B2 đã lấy ghế. Cần kiểm tra owner, phiên đặt/fencing token và trạng thái tại nguồn có bảo đảm phù hợp trước khi xác nhận đơn.

## 5. MongoDB: TTL index trên trường Date xóa toàn document

MongoDB hỗ trợ **TTL index** để tự động loại bỏ những document đã quá hạn. Điểm dễ nhầm là **chỉ mục được đặt lên một field, nhưng đối tượng bị xóa là document**.

### 5.1. Hết hạn sau một khoảng tính từ thời điểm tạo

Ví dụ collection `sessions`:

```javascript
db.sessions.insertOne({
  sessionId: "S100",
  userId: "U42",
  createdAt: new Date(),
  device: "mobile"
});

db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800 }
);
```

Ở thiết kế này, một document có thời điểm `createdAt` sẽ đủ điều kiện xóa khi thời gian hiện tại vượt quá `createdAt + 1800 giây`.

Nếu document còn chứa `device` hoặc `userId`, chúng cũng biến mất khi document bị xóa. MongoDB **không chỉ xóa trường `createdAt`**.

### 5.2. Hết hạn tại thời điểm tuyệt đối

Một cách khác là lưu `expiresAt` kiểu BSON Date, rồi tạo index với `expireAfterSeconds: 0`:

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);

db.sessions.insertOne({
  sessionId: "S101",
  userId: "U42",
  expiresAt: new Date(Date.now() + 30 * 60 * 1000)
});
```

`expireAfterSeconds: 0` có nghĩa document đủ điều kiện hết hạn khi đến **thời điểm lưu trong `expiresAt`**.

Đây là cách linh hoạt khi từng document có thời hạn khác nhau. Một phiên có thể hết hạn sau 10 phút, phiên khác sau 60 phút, dù cùng một TTL index.

### 5.3. Field TTL không có nghĩa xóa field

Giả sử document user chứa:

```json
{
  "userId": "U42",
  "displayName": "An",
  "lastOtp": "934812",
  "otpExpiresAt": "2026-11-14T08:05:00Z"
}
```

Nếu tạo TTL index trên `otpExpiresAt`, database sẽ xóa **cả document user** khi mốc đó qua. Điều này không đáp ứng yêu cầu “OTP hết hạn nhưng hồ sơ vẫn còn”.

Các cách thiết kế phù hợp hơn:

1. Tách OTP thành collection `otp_challenges` có document riêng và TTL index.
2. Lưu field OTP nhưng mỗi lần dùng đều kiểm tra `otpExpiresAt`, đồng thời có job xóa field bằng `$unset`.
3. Dùng một hệ hỗ trợ TTL cấp field/cell, nếu hợp lý với phần còn lại của kiến trúc.

### 5.4. TTL index không phải lời hứa xóa đúng từng giây

MongoDB dùng tiến trình TTL monitor kiểm tra và loại bỏ document hết hạn ở nền. Việc xóa có thể trễ tùy lịch kiểm tra, tải, số lượng document quá hạn và topology.

Không nên viết:

```javascript
// Sai nếu dùng làm điều kiện bảo mật duy nhất:
const session = db.sessions.findOne({ sessionId: "S101" });
// "Có document" không bảo đảm "chưa hết hạn nghiệp vụ".
```

Thay vào đó, một đường xác thực session có thể kiểm tra mốc hết hạn:

```javascript
db.sessions.findOne({
  sessionId: "S101",
  expiresAt: { $gt: new Date() }
});
```

Đây vẫn là một mẫu truy vấn minh họa; một hệ xác thực đầy đủ còn cần kiểm soát token, thu hồi, quyền truy cập, truy vấn có index và các quy tắc bảo mật khác.

### 5.5. Kiểu dữ liệu và index có ý nghĩa

Trường được dùng cho TTL index cần có **kiểu Date phù hợp**. Chuỗi ISO 8601 chỉ *trông giống* ngày:

```javascript
{ expiresAt: "2026-11-14T08:30:00Z" }
```

không giống:

```javascript
{ expiresAt: ISODate("2026-11-14T08:30:00Z") }
```

Khi viết ứng dụng Java, nên ánh xạ từ `Instant`/`Date` sang BSON Date đúng cách. Nếu tài liệu lịch sử có kiểu khác hoặc thiếu trường, phải kiểm tra cơ chế TTL áp dụng cho chúng trước khi dựa vào chính sách.

### 5.6. Collection time-series và retention

MongoDB có khả năng đặt chính sách hết hạn cho **time-series collection** theo time field. Ví dụ mô tả ý tưởng:

```javascript
db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "recordedAt",
    metaField: "deviceId",
    granularity: "seconds"
  },
  expireAfterSeconds: 30 * 24 * 60 * 60
});
```

Ở đây thời hạn retention áp dụng cho dữ liệu time-series theo ngữ nghĩa của collection, và việc dọn có thể liên quan đến bucket lưu trữ thời gian. Không nên mặc định một reading được xóa chính xác ngay khi tròn 30 ngày.

**MongoDB TTL index thông thường là một single-field index**, không có nghĩa index ghép tùy ý sẽ được chấp nhận làm TTL. Những tùy chọn TTL/partial TTL cho time-series cũng có điều kiện riêng tùy phiên bản; cần xác nhận với đúng sản phẩm.

## 6. Cassandra: TTL ở cấp cell/column và default TTL theo table

Apache Cassandra là ví dụ rõ ràng cho sự khác biệt giữa TTL ở mức **giá trị cột/cell** và TTL được đặt **mặc định cho cả bảng**.

### 6.1. TTL khi INSERT

Ví dụ bảng sự kiện theo người dùng:

```sql
CREATE TABLE events_by_user (
    user_id uuid,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((user_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Ghi sự kiện với TTL 7 ngày:

```sql
INSERT INTO events_by_user (
    user_id, event_time, event_id, event_type, payload
)
VALUES (?, ?, ?, ?, ?)
USING TTL 604800;
```

`604800` giây tương đương 7 ngày. Giá trị TTL được áp dụng theo ngữ nghĩa cell của Cassandra, không phải một job chạy sau 7 ngày để xóa toàn bộ bảng.

### 6.2. TTL riêng khi UPDATE

Có thể đặt thời hạn cho những giá trị được ghi bởi một lệnh UPDATE:

```sql
UPDATE events_by_user
USING TTL 3600
SET payload = ?
WHERE user_id = ?
  AND event_time = ?
  AND event_id = ?;
```

Ví dụ này minh họa `payload` nhận thời hạn một giờ ở lần ghi đó; những cột khác có thể có TTL khác hoặc không có TTL tùy cách chúng được ghi.

Điểm quan trọng: **primary key không được hiểu là một cột sẽ tự mất hạn độc lập như thuộc tính thông thường**. Bản ghi/hàng tồn tại và cách hàng được trả về sau khi cell hết hạn chịu ngữ nghĩa row liveness và cell của engine.

### 6.3. Kiểm tra TTL còn lại của một cột

Cassandra có hàm CQL `TTL(column)` cho những cột hỗ trợ:

```sql
SELECT event_id, event_type, TTL(payload)
FROM events_by_user
WHERE user_id = ?;
```

Kết quả giúp biết còn bao nhiêu giây đối với cell. Nếu cột không có TTL hoặc đã hết hạn, kết quả cần diễn giải theo ngữ nghĩa của CQL và trạng thái hiện tại.

### 6.4. Default TTL ở mức table

Có thể cấu hình:

```sql
CREATE TABLE short_lived_events (
    stream_id text,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((stream_id), occurred_at, event_id)
) WITH default_time_to_live = 604800;
```

Ý nghĩa: các giá trị dữ liệu được ghi vào bảng có **TTL mặc định 7 ngày**, trừ khi một thao tác ghi có quy tắc ghi đè thời hạn theo hỗ trợ của Cassandra.

**Đây không phải một “ngày xóa cả table”.** Bảng vẫn tồn tại, các hàng được ghi vào những thời điểm khác nhau có thể hết hạn ở những thời điểm khác nhau.

### 6.5. Cell TTL tạo khả năng “hàng còn nhưng thiếu trường”

Giả sử:

```text
event_type = "CLICK"       (TTL 30 ngày)
payload    = "{...}"       (TTL 7 ngày)
event_time = thuộc khóa chính
```

Sau 10 ngày, `payload` có thể đã hết hạn nhưng `event_type` vẫn còn. Ứng dụng phải chấp nhận trường này thiếu/null theo mô hình đọc phù hợp.

Nếu nghiệp vụ yêu cầu mọi trường của một sự kiện biến mất cùng nhau, nên ghi chúng với **cùng chính sách TTL** hoặc chọn mô hình khác giúp vòng đời thống nhất. TTL độc lập giữa cell có thể làm mất tính toàn vẹn logic của một aggregate nếu thiết kế không cẩn thận.

### 6.6. TTL và tombstone

Trong Cassandra, dữ liệu hết hạn được xử lý theo cơ chế **tombstone** và quá trình lưu trữ/compaction. Mục tiêu là tránh một replica còn dữ liệu cũ làm nó sống lại sau đồng bộ trong những điều kiện được cơ chế xử lý xóa bảo vệ.

Hệ quả vận hành:

- Nhiều cell hết hạn có thể tạo lượng tombstone đáng kể.
- Truy vấn đọc qua những vùng có nhiều tombstone có thể tốn CPU/I/O và tăng độ trễ.
- Dung lượng vật lý không nhất thiết giảm ngay khi TTL hết.
- Repair, compaction và `gc_grace_seconds` liên quan đến an toàn xóa; cấu hình thiếu hiểu biết có thể gây rủi ro.
- Với dữ liệu time-series ghi theo thời gian và hết hạn theo cửa sổ, có thể đánh giá chiến lược compaction phù hợp như TimeWindowCompactionStrategy, sau khi hiểu dạng ghi và late-arriving data.

Không nên giảm `gc_grace_seconds` tùy tiện chỉ để xóa tombstone nhanh. Hãy đánh giá những yêu cầu repair, replica downtime và rủi ro dữ liệu đã xóa xuất hiện lại theo tài liệu engine.

### 6.7. TTL không tự đảm bảo mọi hàng trong một partition hết hạn cùng lúc

Nếu hàng trong cùng partition được ghi vào các ngày khác nhau với TTL 7 ngày, từng giá trị có thể hết hạn theo **thời điểm ghi riêng**. Điều này khác với yêu cầu “xóa toàn bộ lịch sử của khách vào ngày 01/12”.

Nếu cần xóa toàn bộ nhóm tại một thời điểm nghiệp vụ, cần thiết kế thêm cutoff/partition theo thời gian, quyền sở hữu và cách xóa có kiểm soát.

## 7. DynamoDB: TTL cấp item theo thuộc tính số epoch seconds

Amazon DynamoDB cho phép bật TTL trên một thuộc tính được khai báo cho table. Mỗi item có giá trị thời gian hợp lệ trong thuộc tính đó có thể được tự động xóa khi hết hạn.

### 7.1. Mẫu dữ liệu

Ví dụ một item session:

```json
{
  "PK": "SESSION#S100",
  "userId": "U42",
  "issuedAt": "2026-11-14T08:00:00Z",
  "expiresAt": 1794645000
}
```

`expiresAt` trong ví dụ là một **Number có giá trị Unix epoch theo giây**, không phải chuỗi ISO 8601 hoặc số mili giây. Giá trị số cụ thể cần được tính đúng theo mốc thời gian mong muốn; không nên sao chép con số ví dụ vào hệ thống thật mà không tính lại.

Cấu hình TTL ở cấp table tham chiếu tên thuộc tính, ví dụ `expiresAt`. Item thiếu hoặc không có giá trị hợp lệ ở thuộc tính này sẽ không được xét theo quy tắc TTL đó như item có timestamp hợp lệ.

### 7.2. Tính Unix epoch seconds trong Java

```java
import java.time.Duration;
import java.time.Instant;

Instant now = Instant.now();
long expiresAtSeconds =
        now.plus(Duration.ofMinutes(30)).getEpochSecond();
```

`Instant.toEpochMilli()` trả **mili giây** và không được dùng trực tiếp như epoch seconds. Sai đơn vị có thể khiến item sống lâu hơn dự kiến rất nhiều.

### 7.3. TTL xóa cả item, không chỉ thuộc tính

Khi `expiresAt` hết hạn, toàn bộ item `SESSION#S100` đủ điều kiện xóa. DynamoDB TTL **không chỉ xóa thuộc tính `expiresAt`**.

Nếu một item user chứa cả hồ sơ lâu dài và OTP ngắn hạn, đặt TTL trên item user là nguy hiểm. Cần tách OTP/session thành item riêng hoặc xử lý field bằng quy trình ứng dụng.

### 7.4. Không bảo đảm xóa ngay lập tức

DynamoDB TTL thực hiện xóa bất đồng bộ; item đã hết hạn có thể vẫn tồn tại và được đọc/ghi trong một khoảng thời gian trước khi dịch vụ dọn dẹp. Tùy hoạt động của dịch vụ, thời gian này có thể kéo dài, không phải một SLA đến giây/phút.

Vì vậy đường nghiệp vụ phải kiểm tra `expiresAt`:

```text
read session item
    |
    +--> item không tồn tại -> invalid
    |
    +--> expiresAt <= now -> invalid
    |
    +--> expiresAt > now -> tiếp tục kiểm tra quyền/session
```

Nếu dùng DynamoDB Query/Scan, có thể lọc dữ liệu hết hạn trong kết quả để tránh hiển thị, nhưng **FilterExpression không thay thế kiểm tra nghiệp vụ nguyên tử khi ghi**, và một số thao tác vẫn đọc dữ liệu trước khi lọc theo cơ chế của DynamoDB.

### 7.5. Đồng bộ delete sang các hệ khác

Một item được xóa bởi TTL có thể tạo bản ghi thay đổi trên DynamoDB Streams khi stream được cấu hình phù hợp. Tuy nhiên, nếu ứng dụng cần xóa cùng item trong search/cache, phải kiểm tra rõ **cách nhận diện TTL service deletion**, topology, Global Tables, retention của stream và cơ chế replay.

Không nên giả định mọi TTL deletion ở mọi vùng đều có metadata giống hệt hoặc event stream được bật mặc định.

## 8. Azure Cosmos DB for NoSQL: container default TTL và per-item TTL

Azure Cosmos DB for NoSQL có mô hình TTL thuận tiện để minh họa hai cấp:

- **Container-level TTL:** chính sách mặc định cho các item trong container.
- **Item-level TTL:** item ghi đè thời hạn thông qua thuộc tính `_ttl` khi cấu hình container cho phép.

### 8.1. Mặc định ở container

Một container có thể có `defaultTtl` là một số giây dương để các item được hết hạn theo thời hạn mặc định.

Ví dụ khái niệm cấu hình:

```json
{
  "id": "sessions",
  "partitionKey": {
    "paths": ["/tenantId"],
    "kind": "Hash"
  },
  "defaultTtl": 1800
}
```

`defaultTtl = 1800` nghĩa là item mặc định có tuổi thọ 1.800 giây theo quy tắc TTL của Cosmos DB. Thời hạn thường được xét từ timestamp sửa đổi gần nhất do hệ lưu trữ quản lý, không đơn thuần là mốc `createdAt` nghiệp vụ bất biến.

### 8.2. Ghi đè ở item

```json
{
  "id": "S100",
  "tenantId": "T1",
  "userId": "U42",
  "_ttl": 300
}
```

Item có `_ttl = 300` có thể hết hạn sau 300 giây dù container có mặc định khác, khi TTL được bật và áp dụng theo cấu hình tương ứng.

Các giá trị cấu hình đáng biết:

- `defaultTtl` không thiết lập/null: TTL không bật theo kiểu mặc định của API này.
- `defaultTtl = -1`: TTL được bật nhưng không tự hết hạn item nếu item không quy định TTL riêng.
- `defaultTtl > 0`: có TTL mặc định cho item.
- `_ttl` của item có thể ghi đè theo những giá trị được API chấp nhận; cần xét rõ trường hợp `-1`.

Chi tiết các giá trị cần được xác nhận với đúng API/version Cosmos DB đang dùng.

### 8.3. TTL khi cập nhật item

Vì TTL có thể được tính từ thời điểm sửa đổi gần nhất của item, **thao tác cập nhật có thể gia hạn vòng đời** theo cơ chế mặc định. Điều đó phù hợp cache theo hoạt động, nhưng không phù hợp nếu dữ liệu phải hết hạn đúng 30 ngày sau lúc tạo bất kể có cập nhật.

Nếu chính sách là absolute expiration, nên lưu thêm mốc `hardExpiresAt` nghiệp vụ và kiểm tra nó ở đường đọc/ghi quan trọng, hoặc dùng thiết kế có khả năng giữ mốc hết hạn cố định.

### 8.4. Xóa logic và xóa vật lý

Cosmos DB có thể làm item quá hạn không còn hiển thị trong thao tác đọc/query theo ngữ nghĩa TTL trước khi tài nguyên lưu trữ được thu hồi hoàn toàn. Không nên suy luận “không đọc thấy” nghĩa là không còn byte nào trong hạ tầng/backups.

TTL có thể tạo chi phí hoặc ảnh hưởng đến việc phân bổ tài nguyên theo cơ chế dịch vụ; với dữ liệu lớn cần theo dõi dung lượng, throughput và tiến độ dọn dẹp.

## 9. Cloud Firestore: TTL policy theo trường thời gian nhưng xóa document

Cloud Firestore hỗ trợ chính sách TTL sử dụng một trường timestamp trong document, thường áp dụng trong phạm vi **collection group**.

Ví dụ document:

```json
{
  "sessionId": "S100",
  "userId": "U42",
  "expiresAt": "2026-11-14T08:30:00Z"
}
```

Đây là JSON minh họa. Khi ghi Firestore thật, `expiresAt` phải được ánh xạ sang **Timestamp** của Firestore theo yêu cầu của TTL policy, không chỉ là string.

### 9.1. Phạm vi của policy

Nếu cấu hình TTL policy cho collection group `sessions` trên trường `expiresAt`, Firestore có thể xóa document đủ điều kiện hết hạn.

Mặc dù policy **dựa vào một field**, đối tượng bị xóa là **toàn document**, không phải riêng trường timestamp.

### 9.2. Xóa nền, không làm cơ chế hết hạn bảo mật

Việc xóa TTL diễn ra bất đồng bộ và không có bảo đảm chính xác tại giây hết hạn. Ứng dụng có yêu cầu “mã truy cập không dùng sau 10:30” phải kiểm tra `expiresAt` trong logic/ủy quyền phù hợp, không phụ thuộc việc document được Firestore dọn ngay lúc 10:30.

Nếu trường TTL bị thiếu hoặc không đúng kiểu, document có thể không được áp dụng TTL như kỳ vọng. Cần validation và kiểm tra dữ liệu lịch sử khi bật policy.

### 9.3. Quan hệ với các document khác

Xóa document session không nhất thiết tự xóa các document liên quan theo ý nghĩa ứng dụng. Ví dụ một hồ sơ user có subcollection phiên làm việc hoặc một read model `sessions_by_device` nằm nơi khác có thể cần chính sách riêng.

Không nên coi TTL của một document là cơ chế cascade delete xuyên mọi mối quan hệ.

## 10. Couchbase: expiry document và giới hạn ở bucket/collection

Couchbase hỗ trợ expiration cho document, và trong các phiên bản/cấu hình phù hợp có thể khai báo **maxTTL** ở bucket hoặc collection để áp dụng giới hạn vòng đời.

### 10.1. Document expiry

Một document cache hoặc session có thể được ghi với thời hạn tương đối hoặc một thời điểm hết hạn thông qua SDK theo API của phiên bản được sử dụng.

```text
collection.upsert(
    key = "session::S100",
    value = sessionDocument,
    expiry = 30 minutes
)
```

Đây là **giả mã minh họa**, không phải cú pháp nguyên văn của mọi Couchbase SDK. Điều cần hiểu là expiration gắn với **document key**, không phải một trường bất kỳ trong JSON.

### 10.2. MaxTTL theo phạm vi

Cấu hình maxTTL ở bucket/collection đặt giới hạn hoặc chính sách mặc định tùy phiên bản và cơ chế hỗ trợ. Khi tạo collection để chứa session ngắn hạn, việc đặt retention mặc định giúp giảm lỗi ứng dụng quên truyền thời hạn.

Tuy nhiên:

- Không nên mặc định cấu hình bucket và collection có thứ tự ưu tiên giống nhau ở mọi phiên bản.
- Thao tác cập nhật/upsert có thể ảnh hưởng expiry nếu không yêu cầu giữ lại; nhiều SDK có lựa chọn preserve expiry.
- Việc dọn vật lý chịu cơ chế của storage engine.

Đừng đặt hồ sơ người dùng và session ngắn hạn trong cùng document rồi mong expiry chỉ tác động một trường.

## 11. Search engine: retention cấp index khác TTL của từng document

Elasticsearch và OpenSearch thường được dùng với dữ liệu log/event theo thời gian. Một kiến trúc phổ biến là tạo các index hoặc data stream backing indices theo chu kỳ, rồi dùng chính sách vòng đời:

```text
logs-2026-11-01
logs-2026-11-02
logs-2026-11-03
       |
       v
Giữ dữ liệu trong khoảng retention
       |
       v
Rollover / delete index cũ
```

Các cơ chế như **Index Lifecycle Management (ILM)** hoặc **Index State Management (ISM)** quản lý rollover, chuyển tầng lưu trữ, đóng hoặc xóa index theo khả năng của sản phẩm.

### 11.1. Vì sao xóa cả index có thể rẻ hơn xóa document?

Nếu mỗi ngày có hàng triệu log, xóa từng document cũ bằng nhiều thao tác có thể gây overhead và phân mảnh. Khi dữ liệu được chia theo thời gian, xóa toàn bộ index đã hết hạn có thể đơn giản và hiệu quả hơn.

Nhưng nó chỉ đúng nếu **mọi dữ liệu trong index đó đều có chính sách retention phù hợp**. Nếu index chứa dữ liệu mới và cũ trộn lẫn, xóa cả index có thể mất dữ liệu còn hợp lệ.

### 11.2. Không nên nhầm index lifecycle với TTL theo field

Một field `expiresAt` trong tài liệu tìm kiếm không tự làm search engine xóa document nếu không có cơ chế thích hợp. Trong những phiên bản Elasticsearch hiện đại, không nên dựa vào kiểu mapping TTL đời cũ đã bị loại bỏ.

Nếu cần xóa một số document riêng lẻ, có thể dùng quy trình xóa theo ID, job `delete_by_query` hoặc chính sách tổ chức index phù hợp. Cần đánh giá chi phí, refresh, event đồng bộ từ nguồn và khả năng một bản ghi đã xóa bị replay lại.

## 12. Khi chỉ muốn một trường hết hạn: chọn mô hình thế nào?

Đây là điểm cốt lõi của chủ đề. Giả sử document người dùng:

```json
{
  "userId": "U42",
  "displayName": "An",
  "lastOtp": "934812",
  "otpExpiresAt": "2026-11-14T08:05:00Z"
}
```

Yêu cầu: giữ `displayName` lâu dài, xóa hoặc vô hiệu `lastOtp` sau 5 phút.

### 12.1. Phương án A — Database hỗ trợ TTL cấp field/cell

Ví dụ Cassandra ghi riêng cell `last_otp` với TTL ngắn, hoặc Redis phiên bản mới áp dụng field expiration cho hash.

Ưu điểm:

- Trường hết hạn theo cơ chế lưu trữ.
- Không cần tạo một document thứ hai chỉ cho trường đó.

Nhược điểm:

- Dữ liệu còn lại có thể thiếu trường, ứng dụng phải chịu được cấu trúc không đồng nhất.
- Nếu một bất biến nghiệp vụ cần nhiều trường đồng thời tồn tại, TTL từng cell có thể làm cấu trúc “nửa sống nửa hết hạn”.
- Hành vi cập nhật TTL trên field và khôi phục sau lỗi cần kiểm tra theo engine.

### 12.2. Phương án B — Tách dữ liệu ngắn hạn thành đối tượng riêng

```text
users:
    U42 -> {displayName: "An"}

otp_challenges:
    OTP#U42#requestId -> {
        codeHash: "...",
        expiresAt: ...
    }
~~~

Ưu điểm:

- Vòng đời rõ ràng.
- Dùng được TTL cấp key/document/item ở nhiều hệ.
- Giảm nguy cơ xóa nhầm hồ sơ lâu dài.
- Dễ giám sát số OTP đang hoạt động.

Nhược điểm:

- Có thêm khóa/document và thao tác đọc.
- Cần xử lý mối liên kết khi user bị xóa hoặc cấp OTP mới.
- Nếu chỉ cho một OTP hợp lệ mỗi user, phải bảo vệ tính duy nhất hoặc trạng thái phiên ở nguồn.

Đây thường là cách **dễ kiểm soát nhất khi hệ không hỗ trợ field TTL**.

### 12.3. Phương án C — Lưu thời điểm và kiểm tra logic

Giữ `lastOtp` và `otpExpiresAt` trong user document, nhưng khi xác minh:

```text
if now >= otpExpiresAt:
    reject
else:
    verify code
~~~

Sau đó job chạy `unset` hoặc ghi đè trường đã hết hạn.

Ưu điểm: không cần tính năng TTL field từ database. Nhược điểm: dữ liệu hết hạn có thể còn tồn tại vật lý; nếu job lỗi, trường vẫn được lưu. Đường xác minh **bắt buộc** kiểm tra timestamp, không thể chỉ kiểm tra field có tồn tại.

Với OTP, nên lưu mã ở dạng hash theo thiết kế xác thực phù hợp, giới hạn số lần thử và ngăn replay; TTL không giải quyết toàn bộ bảo mật.

### 12.4. So sánh ba phương án

| Tiêu chí | Native field/cell TTL | Tách object | Timestamp + cleanup |
|---|---|---|---|
| Yêu cầu hỗ trợ đặc biệt từ DB | Có | Không nhiều | Không nhiều |
| Vòng đời độc lập | Có | Rõ ràng | Do ứng dụng quản lý |
| Truy vấn cùng hồ sơ | Thuận tiện | Có thể đọc thêm | Thuận tiện |
| Rủi ro xóa nhầm hồ sơ | Thấp nếu dùng đúng | Thấp | Thấp |
| Dọn vật lý tự động | Theo engine | TTL của object | Cần job |
| Bảo đảm hết hạn chính xác | Vẫn cần quy tắc đọc | Vẫn cần quy tắc đọc | Phải kiểm tra trong ứng dụng |
| Kiểu dữ liệu có thể thiếu trường | Có | Hồ sơ ổn định | Có thể còn trường hết hạn |

## 13. TTL với cache và dữ liệu nghiệp vụ có tính nhất quán khác nhau

### 13.1. Cache-aside

Mẫu cache-aside:

```text
Read product P100
      |
      v
GET cache:P100
      |
   +--+--+
   |     |
 hit    miss
   |     |
   |     v
   |   Read source DB
   |     |
   |     v
   |   SET cache:P100 EX 120
   |     |
   +---> trả kết quả
~~~

TTL 120 giây giúp cache không giữ dữ liệu vĩnh viễn. Nhưng **cache vẫn có thể cũ trong khoảng TTL** sau khi nguồn cập nhật.

Nếu giá sản phẩm đổi, chỉ chờ TTL hết có thể không đáp ứng SLO. Có thể thêm invalidation hoặc write-through/read-through theo chiến lược phù hợp.

### 13.2. TTL không giải quyết cache stampede

Nếu hàng nghìn request cùng đọc một key vừa hết hạn, chúng có thể đồng thời truy vấn nguồn. Cần cân nhắc:

- TTL có jitter để tránh đồng loạt hết hạn;
- Single-flight/request coalescing;
- Stale-while-revalidate khi nghiệp vụ cho phép;
- Rate limiting và fallback;
- Lưu cache theo version hoặc event invalidation.

Ví dụ phân tán TTL:

```text
baseTTL = 120 giây
jitter  = giá trị ngẫu nhiên 0..30 giây
ttl     = baseTTL + jitter
~~~

Đây là một cách giảm đồng bộ thời điểm hết hạn, không phải quy tắc cố định cho mọi cache.

### 13.3. TTL ngắn không thay thế kiểm tra nguồn khi giao dịch

Ví dụ cache tồn kho có TTL 5 giây. Một khách đặt đơn đúng lúc cache còn hiển thị 1 sản phẩm, nhưng nguồn đã có 0.

Nếu quyết định bán hàng dựa hoàn toàn vào cache, hệ có thể bán vượt hàng. Bước xác nhận cuối phải dùng nguồn có thao tác trừ tồn kho/kiểm tra bất biến được bảo vệ phù hợp.

## 14. TTL, session và phân quyền: yêu cầu chính xác thường mạnh hơn cleanup

### 14.1. Session không được dùng sau deadline

Dù document session đã hết hạn chưa bị MongoDB/DynamoDB xóa, hệ xác thực phải coi nó là **không hợp lệ ngay sau thời điểm deadline**, theo quy tắc đồng hồ/độ lệch cho phép.

Một logic minh họa:

```java
import java.time.Instant;

public boolean isSessionValid(
        Instant expiresAt,
        boolean revoked,
        Instant now) {

    return !revoked
            && expiresAt != null
            && now.isBefore(expiresAt);
}
```

Đây là một phần rất nhỏ của xác thực, không thay thế kiểm tra chữ ký token, quyền truy cập, chống replay hoặc tính nhất quán của trạng thái thu hồi.

### 14.2. Cập nhật sliding TTL không được vượt absolute lifetime

Giả sử session:

```json
{
  "sessionId": "S100",
  "createdAt": "2026-11-14T08:00:00Z",
  "idleExpiresAt": "2026-11-14T08:30:00Z",
  "absoluteExpiresAt": "2026-11-15T08:00:00Z"
}
```

Khi có hoạt động lúc 08:20, hệ có thể kéo `idleExpiresAt` tới 08:50. Nhưng nếu hoạt động gần hết 24 giờ, không được gia hạn vượt `absoluteExpiresAt`.

Nếu dùng một TTL database cấp key có sliding expiration, ứng dụng phải tính **TTL hiệu lực** dựa trên hai deadline. Nếu chỉ gọi `EXPIRE key 1800` mỗi lần, nó có thể vô tình kéo dài session không giới hạn.

### 14.3. Thu hồi quyền không thể chỉ đợi TTL

Người dùng bị khóa hoặc quyền truy cập bị thu hồi cần được xử lý theo hợp đồng bảo mật. Chờ cache/session TTL 30 phút mới hết có thể không chấp nhận được.

Có thể kết hợp:

- Kiểm tra trạng thái thu hồi ở nguồn.
- Version của session/permission.
- Event invalidation.
- Token thời hạn ngắn và cơ chế refresh có kiểm soát.
- Policy authorization phù hợp với mức độ rủi ro.

TTL là một **giới hạn thời gian**, không phải cơ chế phân quyền đầy đủ.

## 15. TTL và quan hệ dữ liệu: không có cascade delete tự động

Giả sử một người dùng U42 có:

```text
users/U42
    |
    +--> sessions/S1 (TTL 30 phút)
    +--> sessions/S2 (TTL 30 phút)
    +--> login_events/E1 (TTL 30 ngày)
    +--> recommendations/R1 (TTL 7 ngày)
~~~

Khi `sessions/S1` hết hạn, database có thể xóa session. Điều đó **không có nghĩa user U42 bị xóa**, cũng không có nghĩa mọi read model chứa session S1 ở các nơi khác tự động cập nhật.

### 15.1. Dữ liệu lặp có TTL khác nhau

Nếu `sessions_by_user` dùng TTL 30 phút nhưng `sessions_by_device` không TTL, cùng session có thể còn ở danh sách thiết bị sau khi biến mất khỏi danh sách người dùng.

Cần chính sách:

- Các projection có cùng deadline không?
- Có event delete/expire để các bảng khác dọn không?
- Có reconciler kiểm tra orphan không?
- Nếu một bảng được phép giữ lịch sử lâu hơn, ý nghĩa hiển thị có thay đổi không?

### 15.2. TTL và đối soát định kỳ

Một job reconciliation có thể tìm:

- Session đã hết hạn vẫn nằm trong search/read model.
- Một projection bị TTL xóa sớm hơn nguồn.
- Một hàng đã xóa được replay từ snapshot cũ.
- Trường có TTL khác khiến record còn nhưng thiếu thông tin bắt buộc.
- Các bảng có retention khác với hợp đồng.

**Nguồn đúng cho reconciliation phải được định nghĩa rõ:** một session đã hết hạn logic có thể cần coi là “không còn tồn tại” đối với view đang hoạt động, dù item nguồn chưa bị dọn vật lý.

### 15.3. Đừng dùng TTL để giải quyết ràng buộc nhiều thực thể

Nếu một đơn hàng hoàn tất cần giữ chứng từ và lịch sử để audit, đặt TTL trên record nguồn có thể làm mất thông tin mà các bảng dẫn xuất không thể tái tạo.

Hãy tách:

- Dữ liệu tạm thời: TTL ngắn.
- Dữ liệu nghiệp vụ chính: retention theo quy định.
- Lịch sử/audit: chính sách lưu lâu dài hoặc lưu trữ riêng.
- Các projection/cache: TTL theo nhu cầu truy vấn, có thể dựng lại.

## 16. Clock, timezone và độ chính xác thời gian

TTL phụ thuộc thời gian; hiểu sai đơn vị hoặc timezone có thể tạo lỗi khó phát hiện.

### 16.1. Unix epoch seconds và milliseconds

Ví dụ Java:

```java
import java.time.Instant;

Instant deadline = Instant.parse("2026-11-15T00:00:00Z");

long seconds = deadline.getEpochSecond();
long millis = deadline.toEpochMilli();
```

Hai giá trị khác nhau khoảng **1.000 lần**. Nếu DynamoDB kỳ vọng seconds mà ứng dụng ghi milliseconds, item có thể không hết hạn trong khoảng dự kiến.

Một số hệ lại nhận `Date` theo milliseconds nội bộ; phải dùng driver/codec phù hợp thay vì tự truyền number tùy tiện.

### 16.2. Lưu thời điểm UTC, hiển thị theo timezone

Ví dụ:

```text
2026-11-14T08:30:00Z
2026-11-14T15:30:00+07:00
```

Hai cách viết biểu thị cùng một thời điểm. Dữ liệu thời gian nên được parse thành kiểu thời điểm phù hợp và so trên cùng trục UTC.

Không nên dùng chuỗi giờ địa phương thiếu timezone như `"2026-11-14 15:30"` để làm deadline nếu không có quy ước rõ.

### 16.3. Clock skew trong hệ phân tán

Nếu hai server có đồng hồ lệch nhau, việc mỗi server tự quyết định hết hạn có thể khác nhau trong cửa sổ rất nhỏ. Với cache thông thường điều này có thể không quan trọng; với thanh toán hoặc quyền truy cập, cần quy tắc clock/trust phù hợp.

Nhiều database dùng đồng hồ của hệ lưu trữ để xác định TTL. Ứng dụng vẫn có thể dùng đồng hồ riêng để đánh giá deadline nghiệp vụ. Phải xác định **nguồn thời gian nào là căn cứ** và mức lệch được chấp nhận.

### 16.4. Thời gian trôi không giống thời gian xử lý job

Nếu tác vụ nền dọn TTL mỗi phút, thời gian xóa thực tế có thể trễ. Ngược lại, một số hệ có thể coi dữ liệu đã hết hạn và không trả nó dù byte vật lý chưa được thu hồi.

Khi test, cần phân biệt:

- Kiểm tra dữ liệu **còn hiệu lực** trước/sau deadline;
- Kiểm tra dữ liệu **có còn truy vấn thấy** theo ngữ nghĩa engine;
- Kiểm tra dung lượng **đã được dọn vật lý**.

Ba điều này có thể có kết quả khác nhau tại cùng một thời điểm.

## 17. TTL và tombstone, compaction, chi phí vận hành

### 17.1. Xóa logic có thể tạo thêm công việc

Trong một số storage engine LSM, một lệnh xóa hoặc TTL hết hạn có thể tạo metadata/tombstone để việc đọc và đồng bộ biết dữ liệu không còn hợp lệ. Byte trên disk có thể chỉ được thu hồi khi compaction tiến hành.

Vì vậy, TTL không phải một thao tác miễn phí:

- Xử lý expire/delete tiêu tốn CPU.
- Dữ liệu hết hạn có thể vẫn chiếm storage trong một thời gian.
- Tombstone ảnh hưởng truy vấn đọc theo phạm vi.
- Việc dọn có thể cần I/O lớn.
- Replication/backup cũng có chi phí và chính sách riêng.

### 17.2. Nhiều dữ liệu hết hạn cùng lúc

Giả sử 10 triệu cache key được tạo vào 10:00 với TTL đúng 1 giờ. Chúng cùng hết hạn vào 11:00, có thể tạo spike CPU/I/O hoặc cache misses, tùy engine.

Có thể:

- Thêm jitter vào TTL cache.
- Dùng rolling retention.
- Chia partition theo thời gian.
- Giới hạn tốc độ cleanup hoặc batch job.
- Pre-warm cache cho key nóng nếu cần.
- Đo hit rate và tải backend khi hàng loạt key hết hạn.

Không nên thêm jitter nếu nghiệp vụ yêu cầu deadline tuyệt đối chính xác, chẳng hạn OTP; trường hợp đó cần kiểm tra deadline riêng và không tùy tiện kéo dài hiệu lực.

### 17.3. Dọn theo partition thời gian

Với log/sự kiện time-series:

```text
events_2026_11_12
events_2026_11_13
events_2026_11_14
~~~

Nếu toàn bộ một partition/index chứa dữ liệu cùng kỳ retention, xóa cả partition/index có thể hiệu quả hơn xóa từng bản ghi.

Nhưng nếu trong một partition có dữ liệu cần lưu 7 ngày và dữ liệu cần lưu 90 ngày, xóa nguyên partition sau 7 ngày sẽ vi phạm chính sách. **Cách chia dữ liệu phải phù hợp với vòng đời**.

## 18. TTL không thay thế quy trình xóa dữ liệu nhạy cảm

Một yêu cầu xóa thông tin cá nhân có thể bao trùm:

- Database gốc;
- Cache;
- Search index;
- Vector store;
- Read model phi chuẩn hóa;
- Analytics theo chính sách áp dụng;
- Backup và bản xuất;
- Event log còn giữ payload.

TTL ở một collection không đảm bảo tất cả các bản sao liên quan đã được xóa. Tương tự, một hệ tìm kiếm có retention 30 ngày không phải lời cam kết rằng dữ liệu cá nhân được xóa ngay khi người dùng yêu cầu.

Cần quy trình:

1. Xác định các kho có chứa dữ liệu.
2. Phát lệnh/sự kiện xóa tương ứng.
3. Áp dụng deletion với ID/version guard.
4. Kiểm tra không bị event cũ “hồi sinh”.
5. Đối soát các projection theo phạm vi.
6. Ghi nhận xử lý sao lưu/retention theo chính sách và yêu cầu pháp lý áp dụng.

Không được suy luận rằng TTL của ứng dụng đồng nghĩa với đáp ứng mọi nghĩa vụ bảo vệ dữ liệu.

## 19. TTL và replay: tránh làm dữ liệu hết hạn sống lại

Giả sử session S100 đã hết hạn và bị xóa. Một worker khôi phục từ snapshot cũ lại nhận:

```json
{
  "sessionId": "S100",
  "expiresAt": "2026-11-14T08:30:00Z",
  "version": 3
}
```

Nếu worker cứ upsert, session có thể xuất hiện trở lại trong một read model.

### 19.1. Quy tắc khi import/replay

Trước khi dựng lại projection:

- Xác định deadline và chính sách TTL.
- Nếu object đã hết hạn logic, không coi nó là dữ liệu hoạt động.
- Nếu có delete event/version mới hơn, không áp dụng upsert cũ.
- Nếu là history snapshot cố ý, lưu ở hệ lịch sử với ý nghĩa khác, không đưa lại vào danh sách session active.
- Giữ tombstone/version marker đủ lâu để chặn event cũ trong phạm vi replay.

### 19.2. Backfill phải xét dữ liệu vẫn còn thay đổi

Một quá trình snapshot + stream nên có mốc log/CDC hoặc cơ chế bắt kịp để không tạo khoảng trống. Nếu snapshot v5 được ghi sau event v6 mà không có version guard, read model có thể quay lại trạng thái cũ hoặc tạo lại dữ liệu đã hết hạn.

TTL khiến vấn đề này rõ hơn vì **xóa do hết hạn** cũng là một thay đổi cần được đưa vào mô hình đồng bộ.

## 20. Cách chọn TTL theo dữ liệu và nhu cầu

### 20.1. Xác định những câu hỏi cần trả lời trước

- Dữ liệu hết hạn sau **khoảng thời gian từ lúc tạo**, từ lần truy cập cuối hay tại deadline tuyệt đối?
- Hết hạn **toàn key/document**, một trường hay cả một lớp dữ liệu?
- Có được phép đọc dữ liệu cũ thêm vài giây/phút không?
- Có yêu cầu không được truy cập sau deadline dù database chưa dọn không?
- Dữ liệu có thể được dựng lại từ nguồn khác không?
- Dữ liệu có liên hệ với bản ghi không có TTL?
- Có cần audit/retention pháp lý không?
- Chi phí delete/tombstone/compaction ra sao?
- Khi TTL hết, các read model/caches khác cập nhật thế nào?
- Khi replay/backfill, có khả năng khôi phục dữ liệu đã hết hạn không?

### 20.2. Bảng quyết định

| Bài toán | Đơn vị lưu phù hợp | Chiến lược gợi ý |
|---|---|---|
| Cache một response | Redis key | `SET ... EX/PX`, thêm invalidation/jitter nếu cần |
| OTP 5 phút | Key/document riêng hoặc field TTL được hỗ trợ | Kiểm tra deadline và giới hạn lượt thử |
| Session 30 phút | Key/item/document riêng | TTL + kiểm tra hết hạn logic và thu hồi |
| Thuộc tính tạm trong hồ sơ | Cell/field hoặc object tách | Không đặt document TTL lên hồ sơ lâu dài |
| Event IoT giữ 30 ngày | Table time-series / collection time-series | Default TTL/retention theo partition và theo dõi dọn |
| Session ở DynamoDB | Item `expiresAt` epoch seconds | TTL theo table + kiểm tra deadline trong ứng dụng |
| Tài liệu Firestore ngắn hạn | Document với Timestamp TTL field | Policy theo collection group, không coi xóa tức thời |
| Container Cosmos nhiều item ngắn hạn | Container `defaultTtl` + item `_ttl` | Làm rõ behavior khi update |
| Log theo ngày ở search | Index/data stream theo thời gian | ILM/ISM rollover và delete index |
| Bảng giao dịch chính | Không tự gắn TTL ngắn | Retention/archiving theo nghiệp vụ và audit |

Một đơn vị lưu có vòng đời khác biệt rõ rệt thường nên được **tách riêng**. Ví dụ token reset mật khẩu, OTP và hồ sơ user có thời hạn khác nhau; gộp cả ba rồi đặt TTL cho document chung dễ tạo lỗi nghiêm trọng.

## 21. Triển khai và thay đổi chính sách TTL trên dữ liệu đang có

### 21.1. Trước khi bật TTL cho collection/table lớn

Giả sử collection có 20 triệu document `sessions`, nhưng trước đây chưa có TTL. Tạo TTL index có thể khiến hàng triệu document cũ **đủ điều kiện xóa ngay** và làm tăng tải dọn dẹp.

Quy trình nên cân nhắc:

1. Thống kê số bản ghi và phân phối tuổi dữ liệu.
2. Phân biệt dữ liệu đang hoạt động, dữ liệu cần lưu và dữ liệu sai kiểu.
3. Chọn trường thời gian cùng ngữ nghĩa.
4. Kiểm tra trường thiếu/null/string.
5. Ước lượng số bản ghi sẽ hết hạn khi bật.
6. Chuẩn bị tải, dung lượng, backup/retention và khả năng rollback.
7. Triển khai có kiểm soát và theo dõi quá trình dọn dẹp.

Không nên tạo TTL trên production chỉ vì “muốn tự dọn” mà chưa biết bao nhiêu dữ liệu sẽ biến mất.

### 21.2. Thay TTL có thể tạo tác động ngược

Nếu giảm retention từ 90 ngày xuống 7 ngày, nhiều dữ liệu vốn chưa hết hạn có thể lập tức trở thành ứng viên xóa. Nếu tăng từ 7 lên 90 ngày, những bản ghi **đã bị xóa vật lý** không tự quay trở lại.

Cần xác định có snapshot/backup hợp lệ, có phải backfill không và liệu thay đổi có ảnh hưởng các báo cáo cần dữ liệu lịch sử không.

### 21.3. Không dùng TTL để xóa dữ liệu sai kiểu một cách mù quáng

Ví dụ phần lớn `expiresAt` là BSON Date, nhưng một số document có string. TTL index không nhất thiết xử lý document string như mong muốn. Cần lập kế hoạch migration và validation kiểu Date thay vì mặc định index sẽ sửa lỗi dữ liệu.

Tương tự, DynamoDB TTL yêu cầu epoch seconds; nếu ứng dụng lỡ ghi milliseconds, chỉ bật TTL không thể tự hiểu đúng deadline.

### 21.4. Rollout và rollback

Một kế hoạch triển khai tốt:

- Thống nhất hợp đồng TTL ở API và schema.
- Áp dụng validation cho dữ liệu mới.
- Kiểm tra canary collection/partition nếu phù hợp.
- Bật TTL hoặc policy theo khả năng sản phẩm.
- Đo số object đủ điều kiện hết hạn, số đã dọn, độ trễ và lỗi.
- Đối soát ảnh hưởng đến read model.
- Chỉ giảm dần retention sau khi bảo đảm dữ liệu không cần giữ nữa.

Rollback một lệnh cấu hình **không khôi phục** bản ghi đã bị dọn. Cần đặc biệt thận trọng với thay đổi làm mất dữ liệu.

## 22. Quan sát và đo lường TTL trong production

### 22.1. Metric cần theo dõi

| Nhóm | Metric gợi ý | Ý nghĩa |
|---|---|---|
| Đúng hạn | Tỷ lệ request đọc được giá trị đã quá deadline nghiệp vụ | Kiểm tra đường đọc |
| Dọn dẹp | Số bản ghi/key đã expired theo thời gian | Xem cơ chế cleanup hoạt động |
| Backlog | Số object đã hết hạn nhưng chưa được dọn | Theo dõi độ trễ cleanup |
| Dung lượng | Kích thước lưu trữ trước/sau retention | Xác định chi phí thật |
| Hiệu năng | p95/p99 read/write, CPU/I/O/compaction | Phát hiện tác động TTL |
| Cache | Hit ratio, misses, eviction, stampede | Xem TTL có gây tải nguồn không |
| Cassandra | Tombstone-related reads, compaction pressure | Phát hiện chi phí TTL cell |
| DynamoDB | TTL deletion metrics/stream theo khả năng | Biết item được dọn |
| Projection | Orphan/missing after expiry, repair lag | Kiểm tra vòng đời các bản sao |
| Bảo mật | Truy cập sau hết hạn, delete overdue | Bảo đảm nghĩa vụ nghiệp vụ |

Không phải metric nào cũng có sẵn trực tiếp từ mọi sản phẩm. Với hệ không công bố backlog TTL, có thể lấy mẫu hoặc chạy job đối soát theo cách hạn chế tải.

### 22.2. SLO ví dụ

Với session:

> 100% request xác thực sau deadline đã xác định phải bị từ chối bởi logic nghiệp vụ, bất kể cơ chế dọn document có trễ.

Với dữ liệu telemetry:

> Ít nhất 99% dữ liệu quá retention 30 ngày được loại khỏi đường truy vấn hoạt động trong vòng 24 giờ sau deadline; dọn vật lý được theo dõi theo khả năng hệ lưu trữ.

Hai SLO kiểm soát **hai thứ khác nhau**: tính hợp lệ nghiệp vụ và độ trễ dọn dẹp. Ngưỡng chỉ là ví dụ cần thay bằng yêu cầu thực tế.

### 22.3. Cảnh báo cần phân biệt loại lỗi

- Nhiều bản ghi quá hạn vẫn được API coi là hợp lệ → lỗi nghiêm trọng ở lớp nghiệp vụ.
- Cleanup trễ nhưng dữ liệu đã bị lọc đúng → vấn đề vận hành/dung lượng.
- TTL mới làm biến mất bản ghi dài hạn → lỗi mô hình dữ liệu/chính sách.
- Sau expiration, projection còn dữ liệu orphan → lỗi đồng bộ vòng đời.
- Tăng tombstone/read latency → áp lực compaction hoặc thiết kế TTL.
- Hàng triệu cache key hết hạn cùng lúc → cache stampede hoặc cấu hình đồng loạt.

## 23. Kiểm thử TTL: không chỉ chờ đồng hồ

### 23.1. Các tình huống phải có

1. Đọc **trước deadline**.
2. Đọc **đúng deadline** theo quy tắc `<` hay `<=`.
3. Đọc **sau deadline** nhưng trước khi background cleanup chạy.
4. Cập nhật key/field và kiểm tra TTL có được giữ/gia hạn như mong muốn.
5. Một record không có TTL.
6. TTL bằng 0/giá trị âm khi API có ý nghĩa đặc biệt.
7. Sai kiểu timestamp, sai seconds/milliseconds.
8. Nhiều field có TTL khác nhau.
9. Delete/replay sự kiện cũ.
10. Restart/failover/multi-region theo những bảo đảm đang sử dụng.

Đường bảo mật hoặc giao dịch phải được kiểm thử cả khi **record vẫn tồn tại trong database sau deadline**.

### 23.2. Kiểm thử deadline ở Java với Clock

Thay vì gọi `Instant.now()` trực tiếp khắp code, inject `Clock`:

```java
import java.time.Clock;
import java.time.Instant;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        if (expiresAt == null) {
            return true; // Quy tắc ví dụ: thiếu deadline = không hợp lệ.
        }
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
```

Ví dụ dùng đồng hồ cố định:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-14T08:30:00Z"),
        ZoneOffset.UTC
);

ExpiryPolicy policy = new ExpiryPolicy(fixed);

boolean expired = policy.isExpired(
        Instant.parse("2026-11-14T08:30:00Z")
);
// true: ngay tại deadline đã coi là hết hạn.
```

Cách này kiểm thử **quy tắc hết hạn trong ứng dụng** một cách xác định. Nó không thay thế integration test với database để quan sát TTL monitor hoặc cơ chế compaction thực tế.

### 23.3. Integration test không nên đòi physical delete tức thì

Một test dạng:

```text
Write item TTL 2 giây
Sleep 2 giây
Assert database chắc chắn đã xóa vật lý
```

có thể thất bại ngẫu nhiên ở hệ xóa bất đồng bộ, dù database hoạt động đúng. Thay vào đó:

- Kiểm tra deadline nghiệp vụ bằng Clock.
- Dùng polling có timeout hợp lý nếu cần quan sát xóa vật lý.
- Phân biệt **sau deadline đã không hợp lệ** với **đã dọn**.
- Không đặt một thời hạn giả định nhỏ hơn bảo đảm được sản phẩm công bố.
- Test tính nhất quán sau replay và sau worker lỗi.

## 24. Những nhầm lẫn phổ biến

**“TTL luôn xóa dữ liệu đúng giây hết hạn.”** Sai ở nhiều hệ. TTL có thể có mốc hết hạn logic và dọn vật lý bất đồng bộ.

**“Chỉ mục TTL đặt trên field sẽ xóa field đó.”** Sai với MongoDB: TTL index dùng trường Date để quyết định xóa **cả document**.

**“DynamoDB TTL là timestamp ISO 8601.”** Sai: cơ chế này dùng thuộc tính Number theo **Unix epoch seconds**.

**“Redis EXPIRE trên hash chỉ hết hạn một field.”** Sai: `EXPIRE` áp dụng cả key. Hash-field expiration chỉ có ở những phiên bản Redis hỗ trợ API riêng.

**“Cassandra TTL luôn xóa cả row cùng lúc.”** Không phải mặc định: TTL hoạt động ở mức cell, các cột có thể hết hạn khác nhau.

**“default_time_to_live trên Cassandra nghĩa là table bị DROP.”** Sai: đó là TTL mặc định cho dữ liệu ghi trong bảng.

**“Cosmos DB TTL luôn tính từ createdAt.”** Không mặc định: cần hiểu quy tắc timestamp sửa đổi và item/container TTL.

**“Firestore TTL field là kiểu string có ngày ISO.”** Không: chính sách yêu cầu kiểu thời gian được Firestore hỗ trợ; tên trường không tự chuyển string thành Timestamp.

**“Không truy vấn thấy item nghĩa là đĩa đã thu hồi dung lượng.”** Không chắc: nhiều hệ tách logical visibility và physical cleanup.

**“TTL là cơ chế thu hồi quyền truy cập tức thì.”** Không. Phải kiểm tra deadline và trạng thái quyền theo nghiệp vụ, nhất là khi dữ liệu được dọn bất đồng bộ.

**“Chỉ cần TTL ở nguồn thì cache, search và các view tự sạch.”** Không: các bản sao khác có vòng đời riêng và cần đồng bộ/xóa/đối soát.

**“Bật TTL lên dữ liệu cũ là an toàn.”** Không nếu nhiều bản ghi cũ đã quá hạn hoặc trường thời gian sai kiểu; phải đánh giá trước nguy cơ mất dữ liệu.

## 25. Bài tập tự vận dụng

### Bài tập 1 — MongoDB xóa document hay xóa trường?

Collection `users` có document:

```javascript
{
  userId: "U42",
  displayName: "An",
  otp: "934812",
  otpExpiresAt: ISODate("2026-11-14T08:05:00Z")
}
```

Nhóm phát triển tạo TTL index trên `otpExpiresAt` với `expireAfterSeconds: 0`.

**Câu hỏi:** Sau khi hết hạn, còn `displayName` không? Nên sửa mô hình thế nào?

**Gợi ý:** TTL index làm **cả document** đủ điều kiện xóa. Nên tách OTP sang document riêng hoặc dùng timestamp + cleanup field có kiểm soát.

### Bài tập 2 — Redis key và hash field

```redis
HSET user:U42 displayName "An" otp "934812"
EXPIRE user:U42 300
```

**Câu hỏi:** Những gì bị ảnh hưởng sau 300 giây? Nếu chỉ OTP cần hết hạn, nên làm gì?

**Gợi ý:** Toàn hash key. Tách OTP thành key riêng có TTL, hoặc dùng hash-field TTL nếu phiên bản Redis hỗ trợ và mô hình phù hợp.

### Bài tập 3 — DynamoDB seconds hay milliseconds?

Java tạo:

```java
long expiresAt = Instant.now()
        .plusSeconds(1800)
        .toEpochMilli();
```

và ghi vào DynamoDB TTL attribute.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** `toEpochMilli()` trả milliseconds; DynamoDB TTL cần epoch **seconds**. Dùng `getEpochSecond()`.

### Bài tập 4 — Cassandra cột có vòng đời khác nhau

Một hàng có `event_type` TTL 30 ngày và `payload` TTL 7 ngày.

**Câu hỏi:** Sau 10 ngày, ứng dụng có thể thấy điều gì?

**Gợi ý:** `payload` có thể đã hết hạn trong khi `event_type` còn. Schema và code đọc phải chấp nhận thiếu trường, hoặc thay mô hình nếu toàn bộ sự kiện cần hết hạn đồng nhất.

### Bài tập 5 — Cosmos DB và cập nhật item

Một item có TTL 30 phút tính theo ngữ nghĩa timestamp sửa đổi của container. Worker cập nhật metadata mỗi 10 phút.

**Câu hỏi:** Item có thể sống lâu hơn 30 phút từ lúc tạo không?

**Gợi ý:** Có thể, nếu update làm mới mốc TTL. Cần quy tắc absolute expiry riêng nếu phải dừng đúng 30 phút sau creation.

### Bài tập 6 — Session hết hạn nhưng item còn

DynamoDB chưa dọn một item session đã hết hạn 2 giờ. API đọc item vẫn nhận kết quả.

**Câu hỏi:** Có được xác thực người dùng bằng item đó không?

**Gợi ý:** Không; đường xác thực phải so `expiresAt` với thời điểm hiện tại và kiểm tra các điều kiện session khác.

### Bài tập 7 — TTL không cascade

Session S1 hết hạn trong Redis, nhưng `sessions_by_device` trong Cassandra vẫn có hàng S1.

**Câu hỏi:** Điều gì cần thiết để các màn hình đồng nhất?

**Gợi ý:** Xác định nguồn sự thật, đồng bộ expire/delete hoặc đối soát hàng orphan; TTL ở Redis không xóa bảng Cassandra.

### Bài tập 8 — Time-series retention

Một collection sensor chứa 30 triệu reading/ngày, cần giữ 30 ngày.

**Câu hỏi:** Nên đánh giá những lựa chọn nào?

**Gợi ý:** TTL mặc định/bộ lưu time-series theo sản phẩm, partition/bucket theo thời gian, compaction và tombstone, dọn cả partition/index nếu phù hợp, độ trễ cleanup, backup và nhu cầu truy vấn late-arriving data.

### Bài tập 9 — Cache stampede

Một triệu cache key cùng được tạo lúc 10:00 với TTL 3.600 giây. Đến 11:00 lượng truy vấn nguồn tăng đột biến.

**Câu hỏi:** Cách giảm hiện tượng?

**Gợi ý:** TTL jitter với cache không yêu cầu deadline tuyệt đối, single-flight, pre-warming hoặc stale-while-revalidate khi nghiệp vụ cho phép.

### Bài tập 10 — Sự khác nhau giữa retention và TTL

Một sự kiện giao dịch cần giữ lịch sử 5 năm nhưng cache tổng hợp chỉ cần 10 phút.

**Câu hỏi:** Có nên đặt TTL 10 phút trên giao dịch gốc không?

**Gợi ý:** Không. Dữ liệu nguồn và cache có vòng đời khác nhau; TTL ngắn nên áp dụng cho cache, còn lịch sử có retention/archiving theo nghiệp vụ.

### Bài tập 11 — Kiểm thử xóa vật lý

Test tạo document MongoDB có `expiresAt` sau 1 giây, sleep 1 giây và yêu cầu document chắc chắn đã biến mất.

**Câu hỏi:** Vì sao test dễ không ổn định?

**Gợi ý:** TTL monitor xóa bất đồng bộ, nên không có bảo đảm xóa vật lý đúng 1 giây. Kiểm tra deadline nghiệp vụ riêng và dùng cách kiểm thử database phù hợp với cơ chế cleanup.

### Bài tập 12 — Replay và dữ liệu hết hạn

Snapshot v3 chứa session S1 đã hết hạn, còn event delete v4 đã được áp dụng ở view.

**Câu hỏi:** Làm sao không làm S1 xuất hiện lại?

**Gợi ý:** Kiểm tra deadline, giữ delete version/tombstone, chống áp dụng snapshot/event cũ và đối soát sau rebuild.

## 26. Kết luận

**TTL là cơ chế quản lý thời gian sống của dữ liệu, nhưng cấp độ áp dụng khác nhau đáng kể giữa các hệ NoSQL.** Redis phổ biến với TTL cấp key và có thêm hash-field expiration ở những phiên bản mới; MongoDB dùng TTL index đặt trên Date field để xóa cả document; DynamoDB dùng thuộc tính Unix epoch seconds để xóa item; Cassandra hỗ trợ TTL ở cấp cell và mặc định theo table; Cosmos DB có mặc định theo container và ghi đè ở item; Firestore dùng timestamp field để xóa document; còn search engine thường dùng vòng đời index hoặc data stream.

Khi thiết kế, phải phân biệt **TTL cấp field thực sự** với **TTL index theo field nhưng xóa toàn bản ghi**. Cũng cần phân biệt **deadline logic** với **thời điểm thu hồi dung lượng vật lý**: nhiều engine dọn bất đồng bộ, nên không thể lấy sự tồn tại của một bản ghi làm bằng chứng nó vẫn hợp lệ.

Một chính sách TTL đáng tin cậy cần nêu rõ **đơn vị hết hạn, mốc bắt đầu, đơn vị thời gian, điều kiện gia hạn, read semantics, retention, tác động lên quan hệ/read model, khả năng replay và quy trình đối soát/xóa**. Chọn đúng ranh giới dữ liệu ngay từ đầu — đặc biệt tách những đối tượng có vòng đời khác nhau — giúp hệ thống tự dọn hiệu quả mà không vô tình xóa dữ liệu nghiệp vụ cần giữ.

