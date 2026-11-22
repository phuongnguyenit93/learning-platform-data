# TTL index, thời gian hết hạn và độ trễ xóa nền trong MongoDB

## 1. TTL index giải quyết vấn đề gì?

Một cơ sở dữ liệu không phải lưu mọi document mãi mãi. Nhiều loại dữ liệu chỉ có giá trị trong một khoảng thời gian:

- Phiên đăng nhập, mã xác thực một lần (OTP), token khôi phục mật khẩu.
- Dữ liệu cache tạm thời, yêu cầu xử lý có thời hạn.
- Log kỹ thuật, sự kiện hoặc dữ liệu đo đạc chỉ cần giữ lại một số ngày.
- Bản ghi job tạm thời sau khi kết thúc xử lý.
- Dữ liệu telemetry có chính sách retention rõ ràng.

Nếu ứng dụng phải tự chạy một cron job để xóa dữ liệu cũ, cần quản lý lịch chạy, tránh trùng worker và xử lý lỗi. MongoDB cung cấp **Time-To-Live index (TTL index)**, một loại index đặc biệt giúp server **tự động xóa document** sau khi hết thời hạn.

Ví dụ một document:

~~~javascript
{
  _id: "SESSION-001",
  userId: "USER-001",
  createdAt: ISODate("2026-01-01T10:00:00.000Z")
}
~~~

Nếu collection có TTL index trên **createdAt** với **expireAfterSeconds: 3600**, document trở thành ứng viên được xóa sau khi tròn một giờ kể từ **createdAt**, tức từ **11:00:00 UTC** ngày 01/01/2026.

**Điểm quan trọng nhất:** TTL là **cơ chế dọn dẹp dữ liệu bất đồng bộ**, không phải một bộ hẹn giờ xóa chính xác tới từng giây. Document đã quá hạn **có thể vẫn tồn tại và vẫn được truy vấn thấy** trong một khoảng thời gian cho tới khi tác vụ xóa nền xử lý. Nếu token hết hạn lúc 11:00:00, hệ thống xác thực phải từ chối token ở thời điểm đó theo quy tắc nghiệp vụ, **không được chờ đến lúc document biến mất**.

~~~text
Document được tạo
       |
       v
Trường Date + expireAfterSeconds
       |
       v
Thời điểm hết hạn (deadline)
       |
       +------> Ứng dụng tự kiểm tra deadline
       |        để từ chối dữ liệu đã hết hiệu lực
       |
       v
TTL monitor quét nền theo chu kỳ
       |
       v
Xóa document đủ điều kiện
       |
       v
Replication / cập nhật index / giải phóng không gian logic
~~~

## 2. TTL index thực chất là gì?

TTL index là **single-field index** trên một field chứa **BSON Date** hoặc một array có chứa giá trị BSON Date. Nó có tùy chọn **expireAfterSeconds** để xác định khi nào document đủ điều kiện xóa.

Ví dụ:

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_sessions_created_at",
    expireAfterSeconds: 3600
  }
);
~~~

Ý nghĩa:

- **{createdAt: 1}:** chỉ mục theo field createdAt, thứ tự tăng dần.
- **expireAfterSeconds: 3600:** mỗi document hết hạn sau 3.600 giây kể từ giá trị thời gian ở createdAt.
- **name:** tên index để nhận diện, quản trị và sửa đổi cấu hình.
- TTL monitor của **mongod** sẽ xử lý các document đã đủ điều kiện xóa.

TTL index vẫn có thể hỗ trợ query theo indexed field như index thường, nhưng vai trò đặc biệt là **tự động xóa dữ liệu**. Vì vậy, việc tạo hoặc sửa TTL index có tác động trực tiếp đến **retention của toàn collection**, không chỉ đến tốc độ truy vấn.

### 2.1. Công thức thời điểm hết hạn

Với cách cấu hình theo khoảng thời gian kể từ ngày lưu trong document:

\[
\text{expiryTime}=\text{indexedDate}+\text{expireAfterSeconds}
\]

Khi thời gian hiện tại của server đạt hoặc vượt **expiryTime**, document **đủ điều kiện** cho TTL monitor xóa. Khái niệm **đủ điều kiện** không đồng nghĩa **đã được xóa vật lý**.

Ví dụ:

| Giá trị indexedDate | expireAfterSeconds | Thời điểm đủ điều kiện xóa |
|---|---:|---|
| 10:00:00 UTC | 60 | 10:01:00 UTC |
| 10:00:00 UTC | 3.600 | 11:00:00 UTC |
| 10:00:00 UTC | 86.400 | 10:00:00 UTC ngày hôm sau |
| 10:00:00 UTC | 0 | Ngay từ thời điểm indexedDate |

Trong hàng cuối, **0** là một giá trị hợp lệ của **expireAfterSeconds**: nó không có nghĩa vô hiệu hóa TTL.

### 2.2. Date trong BSON khác string ngày giờ

Hai document sau có ý nghĩa khác nhau:

~~~javascript
{
  _id: "GOOD",
  createdAt: ISODate("2026-01-01T10:00:00.000Z")
}

{
  _id: "WRONG_TYPE",
  createdAt: "2026-01-01T10:00:00.000Z"
}
~~~

**GOOD** có createdAt kiểu **BSON Date**. **WRONG_TYPE** chỉ có string dù nhìn giống ISO-8601. TTL index dựa trên **BSON Date**; document có field không phải Date hoặc array không chứa Date sẽ **không được TTL xóa dựa trên field đó**.

Để kiểm tra kiểu:

~~~javascript
db.sessions.aggregate([
  {
    $project: {
      _id: 1,
      createdAt: 1,
      createdAtType: { $type: "$createdAt" }
    }
  }
]);
~~~

Kết quả có thể cho **"date"**, **"string"**, **"null"** hoặc **"missing"**. Đây là khác biệt rất quan trọng khi dữ liệu đến từ REST API, import JSON hoặc mapper Java.

## 3. Hai mô hình thời hạn: thời gian tương đối và thời điểm tuyệt đối

### 3.1. Hết hạn sau N giây kể từ createdAt

Trường hợp giữ log trong 7 ngày kể từ thời điểm tạo:

~~~javascript
db.event_logs.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_event_logs_7d",
    expireAfterSeconds: 7 * 24 * 60 * 60
  }
);
~~~

Document:

~~~javascript
db.event_logs.insertOne({
  eventType: "API_REQUEST",
  createdAt: new Date(),
  message: "request completed"
});
~~~

Mỗi document có thời hạn dựa trên **createdAt + 604800 giây**. Mọi document trong collection dùng cùng một chính sách retention **7 ngày** trên index đó.

**Dùng khi:** dữ liệu cùng loại có tuổi thọ cố định, ví dụ logs trong 7 ngày hoặc session records trong 30 phút kể từ khi tạo.

### 3.2. Hết hạn ở thời điểm riêng của từng document

Trường hợp mỗi token có **expiresAt** khác nhau, ví dụ có token hết hạn sau 10 phút và token sau 24 giờ:

~~~javascript
db.tokens.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_tokens_expires_at",
    expireAfterSeconds: 0
  }
);
~~~

Tạo hai token:

~~~javascript
const now = new Date();

db.tokens.insertMany([
  {
    _id: "TOKEN-SHORT",
    createdAt: now,
    expiresAt: new Date(now.getTime() + 10 * 60 * 1000)
  },
  {
    _id: "TOKEN-LONG",
    createdAt: now,
    expiresAt: new Date(now.getTime() + 24 * 60 * 60 * 1000)
  }
]);
~~~

Với **expireAfterSeconds: 0**, TTL index lấy **expiresAt** làm chính thời điểm đủ điều kiện xóa. Ứng dụng có thể đặt expiresAt riêng cho từng document.

**Dùng khi:** mỗi bản ghi có deadline do nghiệp vụ quyết định, ví dụ OTP, reset token, booking hold hoặc một job có hạn xử lý khác nhau.

### 3.3. Không dùng nhầm thời gian tương đối và tuyệt đối

Nếu document đã có **expiresAt = createdAt + 10 phút** mà index lại đặt **expireAfterSeconds: 600**, TTL chỉ đủ điều kiện xóa **10 phút sau expiresAt** — tổng cộng 20 phút từ createdAt.

~~~text
createdAt = 10:00
expiresAt = 10:10

TTL {expiresAt:1}, expireAfterSeconds:0
    -> đủ điều kiện xóa lúc 10:10

TTL {expiresAt:1}, expireAfterSeconds:600
    -> đủ điều kiện xóa lúc 10:20
~~~

Vì vậy phải xác định rõ field đó mang nghĩa **“thời điểm bắt đầu tính tuổi”** hay **“thời điểm hết hạn cuối cùng”** trước khi tạo index.

### 3.4. TTL có xóa riêng một field đã hết hạn không?

Không. TTL index đánh dấu và **xóa toàn bộ document**, không chỉ xóa giá trị của field createdAt/expiresAt. Ví dụ một tài khoản có:

~~~javascript
{
  _id: "USER-001",
  email: "user@example.test",
  profile: { displayName: "Example" },
  resetCodeExpiresAt: ISODate("2026-01-01T10:10:00Z")
}
~~~

Đặt TTL index trên **resetCodeExpiresAt** của collection **users** có thể khiến **toàn bộ user document** bị xóa khi mã khôi phục hết hạn. Đây là lỗi mô hình dữ liệu nghiêm trọng.

Giải pháp: lưu mã khôi phục trong collection tạm riêng như **password_reset_tokens**, hoặc dùng logic **$unset** field và job riêng nếu thật sự muốn làm sạch một thuộc tính.

## 4. Tạo TTL index trong mongosh

### 4.1. Chuẩn bị collection dùng riêng cho bài thực hành

~~~javascript
use ttl_index_lab

db.createCollection("sessions");
~~~

Nếu collection đã tồn tại, bỏ bước **createCollection** hoặc sử dụng collection tên khác. Những lệnh trong bài tác động đến dữ liệu thật của database được chỉ định, vì vậy chỉ chạy trên môi trường thử nghiệm.

### 4.2. Tạo index TTL 30 phút

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_sessions_30m",
    expireAfterSeconds: 1800
  }
);
~~~

Tạo document:

~~~javascript
db.sessions.insertMany([
  {
    _id: "S-RECENT",
    userId: "U-001",
    createdAt: new Date()
  },
  {
    _id: "S-OLD",
    userId: "U-002",
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000)
  }
]);
~~~

**S-OLD** đã quá 30 phút so với thời điểm createdAt và vì vậy **đủ điều kiện xóa**. Nó có thể vẫn xuất hiện trong các truy vấn ngay sau khi insert, cho đến khi TTL monitor xử lý.

### 4.3. Kiểm tra cấu hình TTL bằng getIndexes

~~~javascript
db.sessions.getIndexes();
~~~

Kết quả rút gọn có thể như sau:

~~~javascript
[
  {
    name: "_id_",
    key: { _id: 1 }
  },
  {
    name: "ttl_sessions_30m",
    key: { createdAt: 1 },
    expireAfterSeconds: 1800
  }
]
~~~

Metadata thực tế còn có thể chứa version và các tùy chọn khác tùy phiên bản MongoDB. Điều cần xác nhận là **key một field Date**, **expireAfterSeconds**, **name**.

### 4.4. TTL 0 giây cho expiresAt

~~~javascript
db.password_reset_tokens.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_reset_token_expires_at",
    expireAfterSeconds: 0
  }
);
~~~

Document:

~~~javascript
db.password_reset_tokens.insertOne({
  tokenHash: "hash-not-plain-text",
  userId: "U-001",
  expiresAt: new Date(Date.now() + 15 * 60 * 1000)
});
~~~

Trong production, không nên lưu reset token nhạy cảm dạng plaintext. Cơ chế tạo, băm, xác minh và vô hiệu hóa token phải được thiết kế riêng; TTL chỉ đảm nhiệm dọn dẹp.

## 5. Khi nào document thực sự biến mất? Độ trễ xóa nền

### 5.1. Thời điểm hết hạn khác thời điểm xóa

Giả sử một document có **expiresAt = 10:05:00 UTC** và TTL index **expireAfterSeconds: 0**:

~~~text
10:04:59       Document chưa hết hạn
10:05:00       Đã hết hạn theo business deadline
10:05:01       Ứng dụng phải coi nó không còn hiệu lực
10:05:15       Document có thể vẫn còn trong collection
10:06:00       TTL monitor có thể đã xử lý, hoặc đang bận
10:06:30+      Khi backlog/tải lớn, document vẫn có thể còn
...            TTL monitor xóa khi có cơ hội và đủ tài nguyên
~~~

Các mốc sau 10:05:00 chỉ minh họa **khả năng trễ**, không phải thời gian MongoDB cam kết.

MongoDB TTL monitor là tác vụ chạy nền, thông thường **kiểm tra khoảng mỗi 60 giây**. Do đó có thể có một khoảng chờ trước khi bắt đầu xóa các document mới hết hạn. Sau đó, thời gian hoàn tất còn phụ thuộc lượng dữ liệu hết hạn và tải hệ thống.

**Không có SLA mặc định “chắc chắn xóa sau đúng 60 giây”.** Trong tình huống phải xóa hàng triệu document, backlog có thể kéo dài hơn nhiều.

### 5.2. Vì sao TTL monitor gây độ trễ?

Một số nguyên nhân:

1. **Chu kỳ quét:** document có thể hết hạn ngay sau khi monitor kiểm tra xong.
2. **Nhiều TTL indexes:** monitor phải xử lý nhiều index/collection.
3. **Backlog lớn:** hàng trăm nghìn hoặc hàng triệu document đã đủ điều kiện xóa.
4. **Tải ghi và xóa:** xóa thực sự tiêu thụ CPU/I/O, duy trì index và tác động replication.
5. **Replica set failover:** khi primary thay đổi, tiến trình xóa TTL cần hoạt động trên primary mới.
6. **Lưu trữ chậm hoặc áp lực tài nguyên:** server có thể không hoàn thành được lượng công việc trong một chu kỳ.
7. **Time series bucket:** việc xóa có thể phải chờ cả bucket cùng hết hạn, không chỉ một measurement.

Hãy hiểu TTL như **eventual cleanup**, không phải hard real-time scheduler.

### 5.3. Cơ chế pass và sub-pass của TTL monitor

Trong các phiên bản MongoDB hiện đại, TTL background process duyệt các TTL indexes và xóa document hết hạn theo từng giai đoạn. Với từng index, quá trình xử lý chuyển sang index khác khi một trong các điều kiện xảy ra:

- Đã xóa **50.000 document** từ index hiện tại;
- Đã dành khoảng **một giây** xóa trên index hiện tại;
- Đã xóa hết những document đang đủ điều kiện ở index đó.

Sau khi xem qua các TTL index, một **sub-pass** hoàn thành. Monitor tiếp tục các sub-pass nếu vẫn còn dữ liệu đủ điều kiện. Một **pass** hoàn thành khi đã xử lý hết các document đủ điều kiện ở tất cả TTL indexes trong lượt đó.

Ngoài ra, quá trình xử lý có giới hạn thời gian nhằm không để một đợt xóa kéo dài vô hạn trên cùng chu kỳ; TTL deletion về cơ bản là tác vụ nền **một luồng** trong ngữ cảnh mô tả của MongoDB. Từ **MongoDB 6.1**, server có thể **batch các thao tác xóa** để tăng hiệu quả.

Những số như **50.000** hoặc **một giây** giải thích cơ chế công bằng và giới hạn thời gian làm việc theo index; **không phải** cam kết rằng mỗi giây MongoDB luôn xóa được 50.000 document.

### 5.4. “Tác vụ nền” không có nghĩa xóa không tốn tài nguyên

TTL monitor chạy nền để chọn dữ liệu cần xóa, nhưng các thao tác **delete** phát sinh vẫn là thao tác ghi bình thường tác động đến:

- document và index của collection;
- cache và storage engine;
- journal/replication theo cơ chế triển khai;
- oplog và việc áp dụng xóa trên secondary của replica set;
- disk usage và thời gian phục vụ query.

TTL có thể tạo tải lớn nếu một đợt dữ liệu rất nhiều document cùng hết hạn. Vì vậy khi thiết kế retention, phải tính cả **tốc độ phát sinh document** lẫn **tốc độ xóa được**.

## 6. Đã hết hạn nhưng còn document: xử lý ở lớp ứng dụng

### 6.1. Không dùng sự tồn tại của document để cấp quyền

Ví dụ ứng dụng xác thực OTP bằng:

~~~javascript
// Sai về nghiệp vụ: document có thể còn sau khi hết hạn.
db.otp_tokens.findOne({
  tokenHash: suppliedHash
});
~~~

Nếu document quá hạn nhưng TTL monitor chưa xóa, query vẫn có thể trả về kết quả. Điều này có thể khiến token đã hết hạn vẫn được sử dụng.

Thay vào đó, phải ràng buộc **expiresAt**:

~~~javascript
const now = new Date();

const token = db.otp_tokens.findOne({
  tokenHash: suppliedHash,
  expiresAt: { $gt: now },
  status: "ACTIVE"
});
~~~

Truy vấn này chỉ nhận token có deadline còn hiệu lực theo thời điểm kiểm tra. Trong API production, hãy dùng nguồn thời gian đáng tin cậy, kiểm soát clock skew và lựa chọn thời điểm kiểm tra nhất quán.

### 6.2. Mẫu truy vấn kiểm tra session

~~~javascript
db.sessions.findOne({
  _id: "S-RECENT",
  revoked: { $ne: true },
  expiresAt: { $gt: new Date() }
});
~~~

Nếu session đã hết hạn, query không trả về session hợp lệ dù TTL cleanup chưa chạy. Nhưng việc dùng **revoked: {$ne:true}** còn khớp field thiếu; nếu security policy yêu cầu trạng thái rõ ràng, dùng **status: "ACTIVE"** hoặc schema ổn định thay vì phủ định mơ hồ.

### 6.3. Kiểm tra và tiêu thụ token một lần

Nếu OTP chỉ được phép sử dụng một lần, truy vấn kiểm tra rồi xóa ở hai bước rời nhau có thể có race condition. Có thể cân nhắc thao tác nguyên tử **findOneAndDelete** với điều kiện deadline:

~~~javascript
const token = db.otp_tokens.findOneAndDelete({
  tokenHash: suppliedHash,
  status: "ACTIVE",
  expiresAt: { $gt: new Date() }
});
~~~

Nếu không match, token đã hết hạn/không hợp lệ/đã dùng. Ví dụ giả định chỉ có một token hợp lệ với **tokenHash** và unique index/kiểm soát thích hợp. Hệ thống thật còn cần chống brute force, rate limit, băm token, kiểm soát tenant/user, audit và xử lý sự cố mạng.

TTL index giúp dọn những token không được sử dụng; **đảm bảo token hết hiệu lực đúng hạn là trách nhiệm của nghiệp vụ**.

### 6.4. Phân biệt retention với legal deletion

TTL có thể là một phần giải pháp retention nhưng **không thích hợp nếu yêu cầu xóa dữ liệu chính xác tức thời** (ví dụ sau một sự kiện hủy quyền, yêu cầu pháp lý tức thời hoặc hoàn thành giao dịch nhạy cảm). Khi cần xóa ngay theo một sự kiện, ứng dụng phải thực hiện **deleteOne/deleteMany** với điều kiện và cơ chế xác nhận thích hợp, không chờ TTL.

Việc xóa document khỏi collection cũng không tự chứng minh đã xóa mọi bản sao trong backup, archive, log hoặc các hệ thống downstream. Chính sách xóa dữ liệu phải xét toàn bộ vòng đời dữ liệu.

## 7. TTL index chỉ hoạt động với kiểu dữ liệu thời gian phù hợp

### 7.1. BSON Date, không phải string hay BSON Timestamp

~~~javascript
db.ttl_examples.insertMany([
  {
    _id: "DATE",
    expiresAt: ISODate("2026-01-01T00:00:00Z")
  },
  {
    _id: "STRING",
    expiresAt: "2026-01-01T00:00:00Z"
  },
  {
    _id: "NULL",
    expiresAt: null
  },
  {
    _id: "MISSING"
  }
]);
~~~

Nếu collection này có TTL index **{expiresAt: 1}** và **expireAfterSeconds: 0**, MongoDB có thể xóa **DATE** khi tới hạn. Các document **STRING**, **NULL** và **MISSING** không có BSON Date hợp lệ nên không tự hết hạn theo TTL index đó.

**BSON Timestamp** là kiểu riêng (thường dùng trong ngữ cảnh replication), không phải BSON Date. Đừng đưa Timestamp vào field TTL rồi kỳ vọng nó được hiểu như ngày giờ thông thường.

### 7.2. Nếu field là array các giá trị Date

MongoDB hỗ trợ TTL index trên field chứa **mảng giá trị Date**. Nếu có nhiều Date, TTL sử dụng **ngày sớm nhất** trong array để tính thời điểm hết hạn.

~~~javascript
{
  _id: "ARRAY-DATES",
  cleanupTimes: [
    ISODate("2026-01-01T10:00:00Z"),
    ISODate("2026-01-01T12:00:00Z")
  ]
}
~~~

Với **expireAfterSeconds: 0**, document đủ điều kiện xóa từ **10:00**, không chờ đến 12:00. Đây là điểm dễ gây mất dữ liệu nếu ứng dụng lưu “một danh sách các deadline” và mong MongoDB đợi deadline muộn nhất.

Nếu business rule yêu cầu xóa khi **tất cả phần tử** trong mảng hết hạn, hãy lưu một field **latestExpiresAt** được tính có kiểm soát, thay vì trực tiếp TTL trên mảng ngày.

### 7.3. Thiếu field hoặc sai kiểu có thể khiến dữ liệu tồn tại mãi

Ví dụ khi import một triệu document nhưng 2% có **createdAt** dạng string do sai mapper, 2% đó có thể tích lũy mà không được TTL xóa.

MongoDB không tự sửa lỗi kiểu và không tự hiểu ISO string như BSON Date. Các biện pháp:

1. Dùng schema validation yêu cầu field thời gian có **bsonType: "date"**.
2. Kiểm soát conversion tại driver/DTO.
3. Định kỳ theo dõi document thiếu field hoặc có kiểu không hợp lệ.
4. Migration dữ liệu cũ theo batch trước khi kỳ vọng TTL hoạt động đúng.

Ví dụ kiểm tra những document thiếu field:

~~~javascript
db.sessions.countDocuments({
  createdAt: { $exists: false }
});
~~~

Ví dụ kiểm tra field hiện diện nhưng sai kiểu:

~~~javascript
db.sessions.countDocuments({
  createdAt: {
    $exists: true,
    $not: { $type: "date" }
  }
});
~~~

Truy vấn kiểm tra kiểu cần được cân nhắc trên collection lớn, vì có thể tốn I/O. Nếu dữ liệu legacy chứa array Dates hoặc field thiếu, hãy thiết kế chính xác tập “không hợp lệ” theo domain, không áp dụng một predicate duy nhất cho mọi trường hợp.

## 8. Schema validation cho field TTL

MongoDB có **$jsonSchema** để bảo vệ cấu trúc của document trước khi ghi. Với session chỉ được tạo khi có createdAt:

~~~javascript
db.createCollection("validated_sessions", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["createdAt", "userId"],
      properties: {
        createdAt: {
          bsonType: "date",
          description: "Session creation time must be BSON Date"
        },
        userId: {
          bsonType: "string"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.validated_sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800, name: "ttl_validated_session_30m" }
);
~~~

Nếu ứng dụng cố insert:

~~~javascript
db.validated_sessions.insertOne({
  userId: "U-001",
  createdAt: "2026-01-01T10:00:00Z"
});
~~~

MongoDB có thể từ chối vì **createdAt** là string, không phải BSON Date. Validator giúp giảm rủi ro “document không bao giờ hết hạn vì sai kiểu”.

**Lưu ý:** validator không tự thay đổi những document đã tồn tại trước khi bật rule. Các tài liệu cũ cần được phát hiện và migrate có kiểm soát. Ngoài ra, việc cho phép array Dates, null hoặc bỏ qua field là quyết định schema riêng; ví dụ này quy định **một BSON Date bắt buộc**.

## 9. Các giới hạn quan trọng của TTL index

### 9.1. TTL chỉ hỗ trợ single-field index

~~~javascript
// TTL hợp lệ trên một field Date của collection thông thường:
db.events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

Không tạo một **compound TTL index** để kỳ vọng TTL có điều kiện:

~~~javascript
// Sai ý định: không có compound TTL theo nghĩa thông thường.
db.events.createIndex(
  { tenantId: 1, createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

MongoDB quy định TTL index là **single-field**; compound indexes **không hỗ trợ TTL**, và **expireAfterSeconds** của một compound index không được áp dụng như chức năng TTL. Nếu cần query hiệu quả theo tenant và thời gian, hãy tạo **index query riêng** và **TTL index riêng**.

~~~javascript
db.events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400, name: "ttl_event_1d" }
);

db.events.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "ix_tenant_event_created" }
);
~~~

Hai index phục vụ **hai mục tiêu khác nhau**: xóa hết hạn và truy vấn theo tenant.

### 9.2. Không tạo TTL index trên _id

Index mặc định **_id_** không hỗ trợ TTL. Không thể dùng:

~~~javascript
// Không dùng _id làm key của TTL index.
db.events.createIndex(
  { _id: 1 },
  { expireAfterSeconds: 3600 }
);
~~~

Ngay cả khi **_id** là ObjectId có một phần thông tin thời gian, nó vẫn **không phải BSON Date** và field _id không hỗ trợ TTL. Tạo field **createdAt** hoặc **expiresAt** riêng.

### 9.3. Không áp dụng TTL index cho capped collection

MongoDB không hỗ trợ tạo TTL index trên **capped collections**. Capped collection có chính sách lưu trữ và vòng đời riêng (dữ liệu cũ có thể bị ghi đè/xóa theo cơ chế capped khi đạt dung lượng), không phải cùng semantics với TTL.

### 9.4. Giá trị expireAfterSeconds hợp lệ

Với TTL index thông thường, **expireAfterSeconds** là số nguyên từ **0** đến **2.147.483.647** giây (bao gồm hai đầu). Không nên truyền số âm, chuỗi, **NaN** hay một kiểu dữ liệu bất thường.

Không được coi **expireAfterSeconds: 0** là vô hiệu hóa TTL; nó có nghĩa **ngưỡng tính từ thời điểm Date bằng 0 giây**.

### 9.5. TTL index có cần unique không?

TTL index không mặc định yêu cầu **unique**. Các document có cùng **expiresAt** vẫn có thể tồn tại và cùng trở thành ứng viên xóa. Nếu nghiệp vụ cần uniqueness cho một khóa như **tokenHash**, tạo một index unique riêng theo mô hình dữ liệu:

~~~javascript
db.tokens.createIndex(
  { tokenHash: 1 },
  { unique: true, name: "uq_token_hash" }
);

db.tokens.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_token_expires_at" }
);
~~~

TTL index không tự tạo unique constraint cho tokenHash. Việc tạo index bổ sung có chi phí duy trì và phải được cân nhắc với workload.

### 9.6. Không thể đổi TTL bằng cách gọi lại createIndex

Giả sử đã có:

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800, name: "ttl_sessions_30m" }
);
~~~

Gọi lại **createIndex** cùng key nhưng đổi thành **expireAfterSeconds: 3600** không phải cách chuẩn để sửa index hiện tại. MongoDB có quy tắc kiểm tra index specification và có thể từ chối thay đổi options không tương thích. Hãy dùng **collMod** như Mục 10.

### 9.7. Hidden TTL index vẫn tự xóa dữ liệu

**Hidden index** được ẩn khỏi query planner nhưng vẫn tồn tại và được duy trì. Nếu nó là TTL index, cơ chế tự xóa **vẫn hoạt động**.

~~~javascript
db.sessions.hideIndex("ttl_sessions_30m");
~~~

Thao tác này **không tạm dừng TTL deletion**. Đừng dùng **hideIndex** như một công tắc “pause expiration”. Muốn thay chính sách retention cần quy trình riêng; thay đổi TTL monitor ở cấp server có rủi ro vận hành rất lớn.

## 10. Thay đổi thời hạn TTL bằng collMod

### 10.1. Đổi từ 30 phút thành 60 phút

Nếu index TTL trên **createdAt** đang có **expireAfterSeconds: 1800**, có thể dùng **collMod**:

~~~javascript
db.runCommand({
  collMod: "sessions",
  index: {
    keyPattern: { createdAt: 1 },
    expireAfterSeconds: 3600
  }
});
~~~

Hoặc chỉ định index bằng tên tùy API/version:

~~~javascript
db.runCommand({
  collMod: "sessions",
  index: {
    name: "ttl_sessions_30m",
    expireAfterSeconds: 3600
  }
});
~~~

Lệnh **collMod** thay đổi thuộc tính TTL mà **không phải xây dựng lại toàn bộ index**. Tên index cũ **ttl_sessions_30m** có thể không còn phản ánh retention 60 phút; vì vậy tên index nên được chọn sao cho không gây hiểu sai, và phải cập nhật tài liệu vận hành.

### 10.2. Rút ngắn TTL có thể gây “bão xóa”

Giả sử collection giữ log 30 ngày. Thay **expireAfterSeconds** thành 1 ngày đồng nghĩa nhiều document 2–30 ngày tuổi **trở thành quá hạn ngay lập tức**. TTL monitor có thể bắt đầu một backlog xóa rất lớn sau khi cấu hình thay đổi.

Rủi ro:

- CPU/I/O và write latency tăng;
- replication lag;
- giảm hiệu năng query đang chạy;
- tốn tài nguyên cập nhật index;
- phân mảnh lưu trữ và không gian đĩa không trở về ngay như dung lượng logic đã xóa.

MongoDB khuyến nghị cân nhắc **xóa dữ liệu quá hạn theo từng batch nhỏ trước khi rút ngắn TTL**, sau đó mới thực hiện **collMod**. Việc chia batch phải có rate limit, bảo vệ query chính và theo dõi replication.

### 10.3. Chuyển index thường thành TTL index

Từ **MongoDB 5.1**, MongoDB hỗ trợ chuyển một **single-field index thường** phù hợp thành TTL index bằng cách thêm **expireAfterSeconds** qua **collMod**.

Ví dụ index thường có key **{createdAt: 1}**:

~~~javascript
db.runCommand({
  collMod: "sessions",
  index: {
    keyPattern: { createdAt: 1 },
    expireAfterSeconds: 1800
  }
});
~~~

Trước khi chuyển đổi, cần kiểm tra:

1. Index hiện tại đúng field, kiểu và định nghĩa được hỗ trợ;
2. Các document cũ có createdAt BSON Date đúng;
3. Có bao nhiêu document đã quá 30 phút;
4. Hệ thống chấp nhận được áp lực xóa và chính sách retention;
5. Có backup và quy trình phục hồi phù hợp nếu index được đặt sai.

**Tạo TTL index trên dữ liệu đã tồn tại có thể lập tức khiến rất nhiều document đủ điều kiện xóa** khi index build hoàn tất. Không coi đây là thay đổi “chỉ thêm cấu trúc tối ưu truy vấn”.

### 10.4. Xóa TTL index dừng cơ chế xóa mới nhưng không khôi phục dữ liệu

~~~javascript
db.sessions.dropIndex("ttl_sessions_30m");
~~~

Nếu TTL index đã bị xóa, các document còn tồn tại không tiếp tục bị dọn theo TTL index đó. Nhưng các document **đã bị TTL xóa trước đó sẽ không tự quay trở lại**.

**Drop index không phải thao tác rollback dữ liệu.** Phải phân biệt khôi phục cấu hình retention với khôi phục document đã xóa từ backup.

## 11. TTL trên replica set và sharded cluster

### 11.1. Replica set

Trong replica set, TTL monitor chỉ chủ động xóa tài liệu khi node ở trạng thái **primary**. Các **secondary** không tự chạy vòng xóa TTL độc lập để quyết định xóa cùng dữ liệu; chúng **áp dụng các delete được replicate từ primary**.

~~~text
             Replica set

             PRIMARY
       TTL monitor tìm expiry
                  |
                  v
         Delete documents
                  |
                  v
             Oplog entries
               /      \
              v        v
         SECONDARY  SECONDARY
          Apply        Apply
          deletes      deletes
~~~

Điều này giúp việc xóa TTL tuân theo cơ chế replication. Trong thời gian failover hoặc replication lag, thời điểm document hết hạn và thời điểm các bản sao đồng bộ trạng thái xóa có thể khác nhau.

Nếu ứng dụng đọc từ secondary, dữ liệu đã hết hạn vẫn có thể được thấy trong thời gian lag, thậm chí sau khi primary đã xóa. Vì vậy **điều kiện expiresAt trong query/authorization** vẫn cần thiết.

### 11.2. Sharded cluster

Trong một sharded cluster, dữ liệu được phân bố trên nhiều shard. TTL deletion được thực hiện bởi **mongod primary của các shard tương ứng**, theo các quy tắc vận hành của cluster. Không nên xem TTL như một job duy nhất chạy “một lần cho cả cluster” tại mongos.

Các yếu tố ảnh hưởng độ trễ:

- tỷ lệ tài liệu quá hạn trên từng shard;
- phân bố shard key và lượng write;
- số lượng TTL indexes mỗi shard;
- replication lag và điều kiện tài nguyên trên từng replica set;
- di chuyển chunk/balancer và trạng thái cluster.

Một shard có nhiều dữ liệu cũ hơn shard khác có thể khiến backlog TTL của nó lớn hơn. Cần quan sát từng node/shard, không chỉ trung bình toàn cluster.

### 11.3. TTL index không tự thay shard key hoặc bảo đảm tenant isolation

Nếu collection chứa dữ liệu nhiều tenant, TTL index trên **expiresAt** vẫn xóa theo thời điểm hết hạn của từng document. Nó không tự kiểm tra quyền truy cập theo tenant, không tự tạo index compound tenantId+expiresAt và không thay thế filter theo tenant trong ứng dụng.

Phân quyền, index truy vấn và chính sách TTL là ba vấn đề riêng:

~~~text
Authorization: tenantId / role
Query speed:   {tenantId:1, expiresAt:1} (nếu phù hợp)
TTL cleanup:   {expiresAt:1}, expireAfterSeconds:0
~~~

## 12. TTL với time series collection: có thêm độ trễ do bucket

MongoDB hỗ trợ **time series collections** để lưu dữ liệu đo đạc theo thời gian. Time series có cơ chế đóng gói document thành **bucket** và những quy tắc TTL riêng.

Ví dụ tạo một collection time series giữ dữ liệu 24 giờ:

~~~javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensorId",
    granularity: "seconds"
  },
  expireAfterSeconds: 24 * 60 * 60
});
~~~

Ở đây **expireAfterSeconds** là **tùy chọn khi tạo time series collection**, không giống cách tạo TTL index thường trên bất kỳ compound field nào.

### 12.1. Cả bucket có thể phải hết hạn trước khi được xóa

Với time series, MongoDB xóa bucket khi **mọi measurement trong bucket đã hết hạn** theo chính sách tương ứng. Điều này có nghĩa một measurement riêng lẻ có thể đã qua retention deadline nhưng bucket chứa nó còn measurement mới hơn, nên nó vẫn tồn tại cho đến khi cả bucket đủ điều kiện dọn.

~~~text
Bucket:
  measuredAt 10:00
  measuredAt 10:15
  measuredAt 10:40

TTL = 1 giờ

Measurement lúc 10:00 đủ 1 giờ lúc 11:00,
nhưng bucket có dữ liệu đến 10:40;
bucket có thể chưa được xóa trước 11:40,
sau đó còn chờ TTL background cleanup.
~~~

Đây là ví dụ logic với các mốc thời gian minh họa; chính xác lúc nào một bucket kết thúc tùy cấu hình bucket/granularity và version MongoDB.

**Kết luận:** TTL time series có thể có độ trễ lớn hơn chỉ riêng chu kỳ ~60 giây của monitor, bởi phải chờ hết hạn toàn bộ bucket.

### 12.2. Partial TTL trên time series

Từ **MongoDB 7.0**, MongoDB hỗ trợ **partial TTL index** cho time series collections theo những quy tắc cụ thể: TTL index dùng **timeField** làm key, còn **partialFilterExpression** dựa vào **metaField**. Có thể áp dụng thời hạn ngắn hơn cho nhóm measurement thuộc một loại metadata so với retention chung của collection.

Tính năng này **không có nghĩa** mọi collection thường có thể tạo TTL index compound hoặc TTL theo bất kỳ biểu thức partial nào tùy ý. Phải đối chiếu version, kiểu collection và giới hạn về timeField/metaField.

### 12.3. Không nhầm TTL index và collection expireAfterSeconds

| Kiểu lưu trữ | Cơ chế cấu hình thường gặp |
|---|---|
| Collection thông thường | **createIndex({dateField:1}, {expireAfterSeconds:N})** |
| Time series collection | **expireAfterSeconds** ở cấu hình collection; một số trường hợp hỗ trợ partial TTL index từ 7.0 |
| Clustered collection có hỗ trợ | Có thể cấu hình retention ở cấp collection theo tài liệu loại collection |

Không lấy tùy chọn của time series collection áp dụng nguyên xi cho một regular collection.

## 13. Giám sát TTL monitor và backlog xóa

### 13.1. Đọc metrics.ttl trong serverStatus

Trong mongosh:

~~~javascript
const status = db.serverStatus();
printjson(status.metrics.ttl);
~~~

Những metric thường có trong các phiên bản phù hợp:

- **metrics.ttl.deletedDocuments:** số document đã được TTL xóa trong khoảng thời gian thống kê hiện tại.
- **metrics.ttl.passes:** số lượt pass TTL hoàn thành.
- **metrics.ttl.subPasses:** số lượt sub-pass TTL hoàn thành.

Một ví dụ cấu trúc (số liệu minh họa):

~~~javascript
{
  deletedDocuments: NumberLong(250000),
  passes: NumberLong(120),
  subPasses: NumberLong(340)
}
~~~

Các bộ đếm là số **tích lũy**, không phải “số document bị xóa trong một giây”. Để đánh giá tốc độ, lấy **chênh lệch giữa hai lần đo** và chia theo thời gian tương ứng.

~~~javascript
const first = db.serverStatus().metrics.ttl;
// Đo lần thứ hai sau một khoảng thời gian do hệ giám sát quản lý.
const second = db.serverStatus().metrics.ttl;
~~~

Đoạn trên chỉ minh họa nguồn dữ liệu; hai lệnh chạy ngay sát nhau không có ý nghĩa tính rate. Trong production, hệ thống monitoring thu metric theo khoảng thời gian xác định và phải xử lý counter reset (restart/rotation) đúng cách.

### 13.2. Kiểm tra danh sách TTL indexes

~~~javascript
db.sessions.getIndexes();
~~~

Xác nhận field Date, tên index, **expireAfterSeconds** và trạng thái index. Nếu một collection không có TTL index do lỗi migration hoặc đã bị drop, đừng chờ monitor tự dọn.

### 13.3. Kiểm tra backlog của document đã hết hạn

Với TTL kiểu **expiresAt + 0 giây**:

~~~javascript
const now = new Date();

db.tokens.countDocuments({
  expiresAt: {
    $type: "date",
    $lte: now
  }
});
~~~

Kết quả biểu diễn một **ước lượng số document đủ điều kiện xóa còn tồn tại tại thời điểm query**, không phải cam kết tất cả sẽ biến mất ở chu kỳ kế tiếp. Dữ liệu có thể tiếp tục thay đổi đồng thời khi query chạy.

Với TTL kiểu **createdAt + 1800 giây**:

~~~javascript
const cutoff = new Date(Date.now() - 1800 * 1000);

db.sessions.countDocuments({
  createdAt: {
    $type: "date",
    $lte: cutoff
  }
});
~~~

Những query này có thể tốn chi phí với collection lớn và workload cao. Không lập lịch full scan mỗi giây để “giám sát TTL”. Dựa vào index và sampling/metrics phù hợp quy mô.

### 13.4. Quan sát thao tác TTL đang chạy

MongoDB có thể hiển thị các delete đang chạy của TTL monitor qua **db.currentOp()** hoặc những công cụ giám sát tương ứng, tùy quyền và phiên bản:

~~~javascript
db.currentOp();
~~~

Không thấy một TTL delete trong currentOp **không chứng minh monitor đã bị tắt**: tác vụ có thể chưa tới lượt hoặc đã kết thúc rất nhanh.

### 13.5. Các metric vận hành hữu ích

| Metric | Cách hiểu |
|---|---|
| **Expired-but-present document count** | Backlog tài liệu quá hạn còn được query thấy. |
| **TTL deletedDocuments rate** | Tốc độ xóa thực tế theo thời gian đo. |
| **TTL passes/subPasses** | Hoạt động của monitor và các lượt xử lý. |
| **Replication lag** | Secondary đã theo kịp delete từ primary hay chưa. |
| **Disk I/O, cache pressure** | Tác động vận hành khi xóa nhiều. |
| **Write latency p95/p99** | Xóa TTL có tạo tác động tới workload chính không. |
| **Collection count/storage size** | Xu hướng retention và khả năng dữ liệu tích tụ. |

Để đo **độ trễ TTL thực tế**, có thể lấy mẫu document với **expiresAt** đã được biết và quan sát thời điểm nó biến mất trên môi trường đo được kiểm soát. Không có trường timestamp xóa tự động trong document sau khi nó đã bị xóa, nên muốn đo chi tiết có thể cần instrumentation riêng ngoài collection nguồn.

## 14. Những điều có thể làm TTL ngừng hoạt động hoặc chậm bất thường

### 14.1. Sai kiểu field Date

Document lưu **"2026-01-01T10:00:00Z"** dưới dạng string, MongoDB không tự coi đó là Date khi TTL đánh giá.

**Cách xử lý:** schema validation, mapper đúng BSON Date, migration các bản ghi sai kiểu.

### 14.2. Field thiếu hoặc chứa null

Document không có field indexed Date không đủ điều kiện hết hạn theo TTL đó.

**Cách xử lý:** quyết định business rule cho trường hợp thiếu expiresAt. Nếu mọi token bắt buộc có expiry, dùng validator **required + bsonType:"date"**.

### 14.3. Thời gian lưu sai múi giờ hoặc đồng hồ lệch

Nếu ứng dụng tính expiresAt bằng đồng hồ lệch nhiều phút, document có thể hết hạn sớm hoặc muộn hơn ý định.

**Cách xử lý:** dùng thời gian UTC/Instant nhất quán, đồng bộ NTP, tránh nhầm giữa mili giây và giây, theo dõi clock skew giữa các thành phần.

### 14.4. TTL monitor chưa chạy hết backlog

Hệ thống vừa bật TTL trên collection có hàng triệu document quá hạn. Monitor chỉ xử lý dần theo tài nguyên và vòng xử lý.

**Cách xử lý:** chia deletion lịch sử thành batch có kiểm soát trước khi bật hoặc rút ngắn TTL; theo dõi metrics và replication.

### 14.5. Node đang là secondary

TTL monitor chỉ chủ động xóa trên primary của replica set; secondary áp dụng các delete được replicate. Truy vấn metrics trên một secondary không nhất thiết phản ánh cùng hành vi của primary.

**Cách xử lý:** kiểm tra topology và read preference, giám sát primary và replication.

### 14.6. TTL monitor bị tắt do cấu hình vận hành

MongoDB có server parameter **ttlMonitorEnabled**, mặc định được bật trên mongod thích hợp. Việc tắt TTL monitor có thể làm document không được dọn và còn ảnh hưởng tới các hệ thống nội bộ dựa vào TTL.

MongoDB khuyến nghị **không tắt TTL monitor trong production**, trừ khi được hướng dẫn bởi MongoDB Support hoặc có kế hoạch vận hành được đánh giá kỹ.

Để **kiểm tra** trên một deployment có quyền thích hợp:

~~~javascript
db.adminCommand({
  getParameter: 1,
  ttlMonitorEnabled: 1
});
~~~

Không đưa thao tác **setParameter ttlMonitorEnabled=false** vào quy trình thử nghiệm tùy tiện vì nó có thể ảnh hưởng đến nhiều collection và chức năng nội bộ.

### 14.7. TTL index đã bị drop hoặc cấu hình sai

Nếu không tìm thấy **expireAfterSeconds** trên index trong **getIndexes()**, có thể collection chưa có TTL index như mong đợi, hoặc index đã bị chuyển/đổi.

**Cách xử lý:** đối chiếu index catalog và migration history, không suy luận từ annotation trong Java rằng MongoDB chắc chắn đang có index đúng.

## 15. Java Sync Driver: tạo TTL index và ghi BSON Date

Java Sync Driver cung cấp **MongoCollection.createIndex()** và **IndexOptions.expireAfter()**. Ví dụ dưới đây dùng TTL trên **expiresAt** với giá trị 0 giây để mỗi document có deadline riêng.

### 15.1. Tạo index trong Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

import java.util.Date;
import java.util.concurrent.TimeUnit;

public final class TtlIndexExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must be provided"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("ttl_index_lab");
            MongoCollection<Document> tokens =
                    database.getCollection("tokens_java");

            tokens.createIndex(
                Indexes.ascending("expiresAt"),
                new IndexOptions()
                    .name("ttl_tokens_java")
                    .expireAfter(0L, TimeUnit.SECONDS)
            );

            Date now = new Date();
            Date expiresAt = new Date(
                    now.getTime() + TimeUnit.MINUTES.toMillis(10)
            );

            tokens.insertOne(
                new Document("tokenHash", "demo-hash")
                    .append("createdAt", now)
                    .append("expiresAt", expiresAt)
            );

            System.out.println("Inserted token with expiration " + expiresAt);
        }
    }
}
~~~

Lớp **Date** trong Java được driver mã hóa thành BSON Date theo cơ chế codec phù hợp. Dù ví dụ dùng Date, ứng dụng có thể chọn **Instant** trong domain và chuyển đổi có kiểm soát.

**Chú ý:** đoạn mã minh họa tạo index, không phải ứng dụng lưu token bí mật hoàn chỉnh. Trong production, index creation nên được triển khai bằng migration được quản lý, tránh để mỗi instance tạo cấu trúc quan trọng không có điều phối.

### 15.2. Query token chưa hết hạn trong Java

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gt;

Document token = tokens.find(
        and(
            eq("tokenHash", suppliedHash),
            eq("status", "ACTIVE"),
            gt("expiresAt", new Date())
        )
).first();
~~~

Truy vấn này **tự loại document đã quá hạn** dù monitor còn chưa dọn. **suppliedHash** giả định là giá trị đã được xử lý an toàn và dùng query builder typed, không phải chuỗi truy vấn dựng bằng cách ghép raw JSON không kiểm soát.

### 15.3. TTL tương đối trong Java

~~~java
tokens.createIndex(
    Indexes.ascending("createdAt"),
    new IndexOptions()
        .name("ttl_tokens_created_at_1h")
        .expireAfter(1L, TimeUnit.HOURS)
);
~~~

Đây là ví dụ **một index khác với retention theo createdAt**. Trong một collection thật, việc có nhiều TTL indexes trên các field khác nhau có thể khiến document bị xóa theo **điều kiện hết hạn sớm nhất mà nó thỏa**. Đừng vô tình tạo cả **expiresAt TTL** và **createdAt TTL** nếu domain chỉ mong một deadline.

### 15.4. Đọc index metadata trong Java

~~~java
for (Document indexSpec : tokens.listIndexes()) {
    System.out.println(indexSpec.toJson());
}
~~~

Java driver dùng **listIndexes()**, trong khi **mongosh** có helper **getIndexes()**.

## 16. Spring Data MongoDB: TTL qua @Indexed và IndexOperations

Spring Data MongoDB hỗ trợ định nghĩa index bằng annotation và tạo index thông qua **MongoTemplate.indexOps()**. Điều quan trọng là cấu hình phải thực sự được tạo ở MongoDB; chỉ khai báo annotation trong code không tự đảm bảo index đã xuất hiện.

### 16.1. Entity dùng expiresAt

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "verification_tokens")
public class VerificationTokenDocument {

    @Id
    private String id;

    private String tokenHash;

    @Indexed(name = "ttl_verification_token", expireAfterSeconds = 0)
    private Instant expiresAt;

    // Constructor, getters, setters...
}
~~~

**Instant** phù hợp để biểu diễn thời điểm tuyệt đối UTC trong Java. Spring Data MongoDB có thể map Instant thành BSON Date theo converter cấu hình. Nếu hệ thống có custom converters, cần kiểm tra biểu diễn thực tế trong MongoDB.

### 16.2. Không nhầm annotation với index đã được tạo

Tùy phiên bản và cấu hình **auto-index creation**, Spring Data MongoDB có thể không tự tạo index từ annotation trong quá trình startup. Sau triển khai, kiểm tra bằng:

~~~javascript
db.verification_tokens.getIndexes();
~~~

Xác minh index thật sự có **{expiresAt:1}** và **expireAfterSeconds:0**. Khi hệ thống chạy nhiều instance, nên dùng migration có điều phối hoặc cơ chế đảm bảo index được tạo một cách nhất quán.

### 16.3. Tạo index thông qua MongoTemplate

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

// mongoTemplate được inject sẵn.
mongoTemplate.indexOps("verification_tokens").ensureIndex(
    new Index()
        .on("expiresAt", Sort.Direction.ASC)
        .named("ttl_verification_token")
        .expire(0, TimeUnit.SECONDS)
);
~~~

Ví dụ dùng **IndexOperations** để quản lý index theo cách chủ động. Nếu index cùng key đã có nhưng options TTL khác, việc gọi **ensureIndex** không thay thế cho một migration dùng **collMod** phù hợp.

### 16.4. Truy vấn hợp lệ trong Spring Data

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tokenHash").is(suppliedHash)
            .and("status").is("ACTIVE")
            .and("expiresAt").gt(Instant.now())
);
~~~

Truy vấn này xác định điều kiện hiệu lực trong business logic. TTL cleanup vẫn hoạt động độc lập ở database. Với luồng xác thực có tính cạnh tranh, cần xử lý atomic consume/revoke và chống replay như một nghiệp vụ riêng.

## 17. TTL và chiến lược lưu trữ logs, sessions, cache

### 17.1. Session records

Với session có thời hạn cố định 30 phút từ lúc tạo:

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800 }
);
~~~

Nếu session được gia hạn (sliding expiration), dùng **createdAt TTL cố định** có thể xóa session vẫn còn hiệu lực. Khi domain cho phép gia hạn, nên lưu **expiresAt** được cập nhật mỗi lần gia hạn và dùng **expireAfterSeconds: 0**, hoặc có mô hình session khác theo hợp đồng.

### 17.2. Cache entries

~~~javascript
db.cache_entries.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Khi đọc cache, vẫn cần kiểm tra **expiresAt > now**. Nếu không, ứng dụng có thể phục vụ cache quá hạn trong thời gian monitor chưa xóa. TTL không phải replacement cho logic kiểm soát cache staleness.

### 17.3. Audit và sự kiện nghiệp vụ

Một số dữ liệu audit cần giữ theo yêu cầu pháp lý, kiểm toán hoặc điều tra. Không nên áp đặt TTL index chỉ dựa trên mục tiêu giảm dung lượng nếu chính sách retention chưa được phê duyệt.

Với dữ liệu log thông thường, TTL có thể phù hợp, nhưng xóa TTL cũng sinh tải I/O và replication. Khi dữ liệu cần lưu dài hạn với chi phí thấp hơn, cân nhắc **archive** trước khi xóa.

### 17.4. Dữ liệu có thời hạn khác nhau theo loại hoặc tenant

Ví dụ tenant A giữ 7 ngày, tenant B giữ 30 ngày. Một TTL index **createdAt + 7 ngày** không tự đọc tenantId để áp dụng thời hạn khác. Có thể thiết kế field **expiresAt** được tính theo chính sách của từng tenant:

~~~javascript
{
  tenantId: "TENANT-A",
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  expiresAt: ISODate("2026-01-08T00:00:00Z")
}
~~~

~~~javascript
{
  tenantId: "TENANT-B",
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  expiresAt: ISODate("2026-01-31T00:00:00Z")
}
~~~

Với **TTL expiresAt + 0**, mỗi document có deadline riêng mà không cần compound TTL index. Cần bảo đảm logic tính expiresAt được kiểm thử và không cho client tự chọn retention vượt quyền cho phép.

## 18. Vận hành an toàn khi triển khai TTL trên collection có dữ liệu cũ

### 18.1. Tình huống rủi ro

Một collection **application_logs** có 80 triệu document, bao gồm dữ liệu nhiều năm. Team muốn giữ 7 ngày và tạo:

~~~javascript
db.application_logs.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_application_logs_7d",
    expireAfterSeconds: 604800
  }
);
~~~

Nếu hầu hết dữ liệu đã quá 7 ngày, chúng **đủ điều kiện xóa ngay sau khi index build hoàn tất**. Điều này có thể gây backlog và tác động nặng tới server trong thời gian dài.

### 18.2. Quy trình đề xuất

1. **Xác nhận chính sách retention:** ai phê duyệt, nhóm dữ liệu nào được xóa, có yêu cầu archive/backup không.
2. **Đánh giá dữ liệu:** đếm/sampling document quá hạn, đo độ lớn, kiểm tra kiểu field Date, xem phân bố theo shard/tenant.
3. **Xem topology và tải:** primary/secondary, write concern, giờ cao điểm, dung lượng dự phòng.
4. **Dọn lịch sử có giới hạn:** nếu rất nhiều document quá hạn, xóa theo batch nhỏ có rate limit và giám sát thay vì bật TTL đột ngột.
5. **Tạo hoặc chỉnh TTL index:** sử dụng createIndex hoặc collMod phù hợp.
6. **Giám sát backlog và hiệu năng:** metrics.ttl, replication lag, write/query latency.
7. **Theo dõi sau triển khai:** không coi việc lệnh createIndex thành công là đã xóa hết dữ liệu.

### 18.3. Ví dụ xóa dữ liệu cũ theo từng lô

Một script mongosh minh họa cách **chọn một nhóm nhỏ _id** rồi xóa; dùng trong môi trường có kiểm soát:

~~~javascript
const cutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
const batchSize = 200;

const ids = db.application_logs
  .find(
    { createdAt: { $lt: cutoff } },
    { _id: 1 }
  )
  .limit(batchSize)
  .toArray()
  .map(d => d._id);

if (ids.length > 0) {
  const result = db.application_logs.deleteMany({
    _id: { $in: ids },
    createdAt: { $lt: cutoff }
  });
  printjson(result);
}
~~~

Script xóa **tối đa 200 document được chọn trong một lượt** rồi dừng, không tự lặp vô hạn. Các lần chạy tiếp theo cần được **điều phối, giới hạn tốc độ và quan sát metrics**. Trên collection cực lớn nên dùng phương án chọn key, index và batch strategy phù hợp; thao tác **deleteMany** không tự giới hạn bằng option **limit**, nên giới hạn bằng cách tìm IDs trước.

### 18.4. Chú ý dung lượng đĩa sau delete

MongoDB/WiredTiger có thể tái sử dụng không gian đã xóa nội bộ mà **không trả ngay dung lượng tệp vật lý về filesystem**. Vì vậy xóa 100 GB dữ liệu không có nghĩa dung lượng ổ đĩa quan sát bằng hệ điều hành giảm đúng 100 GB.

Các thao tác như **compact** có điều kiện và tác động vận hành riêng, cần đọc tài liệu phiên bản cụ thể và lên kế hoạch. Không chạy compact hay rebuild tùy tiện chỉ vì số liệu disk usage không giảm ngay.

## 19. TTL và lựa chọn giữa tự động xóa, job riêng và archive

| Yêu cầu | TTL index | Job xóa chủ động | Archive/backup |
|---|---|---|---|
| Dọn dữ liệu sau một deadline tương đối/tuyệt đối | Phù hợp, eventual cleanup. | Phù hợp nếu cần điều kiện phức tạp hơn. | Không thay thế cleanup của dữ liệu nóng. |
| Xóa đúng thời điểm tới từng giây | **Không bảo đảm.** | Cần thiết kế kiểm soát thời điểm và tải, vẫn có độ trễ thực tế. | Không nhằm xóa tức thời. |
| Xóa theo nhiều field/rule phức tạp | Hạn chế, TTL index một field. | Linh hoạt hơn. | Có thể phân loại dữ liệu trước lưu trữ. |
| Archive trước khi xóa | TTL không tự archive. | Job có thể archive rồi delete. | Là thành phần của workflow. |
| Điều kiện per-document khác nhau | Dùng **expiresAt + 0**. | Có thể dùng query đặc thù. | Tùy chính sách. |
| Đảm bảo token hết hiệu lực đúng deadline | **Không.** | Business query phải kiểm tra deadline. | Không liên quan. |
| Retention lâu dài của time series | Hỗ trợ theo bucket/time series. | Có thể áp dụng workflow chuyên biệt. | Cân nhắc khi cần dữ liệu lịch sử. |

TTL đặc biệt hữu ích khi **dữ liệu hết hạn có thể bị xóa bất đồng bộ** và tiêu chí xóa chỉ dựa trên thời gian. Khi phải bảo đảm trạng thái nghiệp vụ, lưu trữ lịch sử, đồng bộ nhiều hệ thống hoặc xóa có kiểm soát theo sự kiện, cần bổ sung workflow riêng.

## 20. Những lỗi thường gặp

### 20.1. Trông chờ token biến mất ngay ở expiresAt

**Sai:** “Document còn trong collection, vậy token còn hiệu lực.”

**Đúng:** kiểm tra **expiresAt > now** trong logic xác thực; TTL chỉ dọn dẹp sau.

### 20.2. Dùng expireAfterSeconds = 0 để tắt TTL

**Sai:** 0 nghĩa là không hết hạn.

**Đúng:** 0 nghĩa deadline đúng bằng giá trị BSON Date trong field. Nếu muốn tắt cơ chế xóa phải thay đổi thiết kế/index/config tương ứng, không đặt TTL bằng 0.

### 20.3. Lưu thời gian dưới dạng string

**Sai:** **"2026-01-01T10:00:00Z"** được TTL tự hiểu như Date.

**Đúng:** lưu BSON Date, ví dụ **ISODate(...)** trong mongosh hoặc Date/Instant qua converter phù hợp.

### 20.4. Cố tạo compound TTL theo tenant

**Sai ý định:** **createIndex({tenantId:1,expiresAt:1}, {expireAfterSeconds:0})**.

**Đúng:** TTL single-field trên expiresAt; tạo compound index riêng để hỗ trợ query theo tenant nếu cần.

### 20.5. Đặt TTL trên collection người dùng để xóa OTP

**Sai:** TTL trên **resetCodeExpiresAt** của document user sẽ chỉ xóa reset code.

**Đúng:** TTL xóa **toàn bộ document**, nên lưu OTP/token trong collection riêng hoặc thiết kế cleanup field khác.

### 20.6. Quên kiểm tra document không có field TTL

**Sai:** mọi document đều tự hết hạn dù thiếu expiresAt.

**Đúng:** document thiếu Date có thể tồn tại lâu dài. Cần validation và monitoring.

### 20.7. Mảng Date có nhiều deadline

**Sai:** TTL chọn ngày cuối cùng trong mảng.

**Đúng:** TTL lấy **ngày sớm nhất** phù hợp để tính expiration.

### 20.8. Rút TTL từ 30 ngày xuống một ngày trong giờ cao điểm

**Sai:** chỉ thay một option index nên không ảnh hưởng nhiều.

**Đúng:** hàng triệu document có thể lập tức đủ điều kiện bị xóa; cần kế hoạch dọn theo batch và quan sát tải.

### 20.9. Hide TTL index để pause deletion

**Sai:** hideIndex khiến server ngừng dọn.

**Đúng:** hidden TTL index **vẫn tiếp tục xóa**; hide chỉ ảnh hưởng query planner.

### 20.10. Tin rằng secondary tự xóa đúng deadline

**Sai:** mọi member replica set tự chạy TTL cleanup độc lập.

**Đúng:** primary tạo delete, secondary replicate; read lag vẫn có thể khiến document quá hạn được đọc thấy.

### 20.11. Đọc metrics.ttl.deletedDocuments như tốc độ tức thời

**Sai:** deletedDocuments = 200000 nghĩa là 200000 document/giây.

**Đúng:** là counter tích lũy; cần lấy delta theo thời gian và xử lý reset.

### 20.12. Dùng TTL làm backup hay archive

**Sai:** TTL tự lưu dữ liệu cũ ở nơi khác trước khi xóa.

**Đúng:** TTL chỉ delete; muốn archive phải có pipeline riêng trước khi retention xóa.

## 21. Bài thực hành tự kiểm tra

### Bài 1 — Tạo TTL sau 90 giây

Tạo collection **short_lived** trong database lab, có TTL index **{createdAt:1}** với **expireAfterSeconds:90**:

~~~javascript
use ttl_index_lab

db.short_lived.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 90, name: "ttl_short_lived_90s" }
);
~~~

Insert một document mới và một document có createdAt cũ 10 phút:

~~~javascript
db.short_lived.insertMany([
  {
    _id: "NEW",
    createdAt: new Date(),
    description: "Should live about 90 seconds or longer"
  },
  {
    _id: "OLD",
    createdAt: new Date(Date.now() - 10 * 60 * 1000),
    description: "Already eligible for deletion"
  }
]);
~~~

Quan sát **db.short_lived.find()** ở các thời điểm khác nhau. Mục đích là thấy **OLD đủ điều kiện xóa ngay nhưng không cam kết biến mất tức thời**, còn NEW đủ điều kiện sau 90 giây và có thể còn thêm một khoảng trễ.

### Bài 2 — Chỉ mục tuyệt đối

Thiết lập TTL **expireAfterSeconds:0** trên **expiresAt** cho collection **one_time_codes**. Tạo hai document với expiresAt cách thời điểm tạo 2 phút và 15 phút. Giải thích vì sao một TTL index áp dụng được cả hai deadline.

### Bài 3 — Sai kiểu BSON

Insert vào collection có TTL:

~~~javascript
db.short_lived.insertOne({
  _id: "STRING_DATE",
  createdAt: new Date().toISOString(),
  description: "Wrong BSON type"
});
~~~

Truy vấn **$type** để thấy createdAt là string và giải thích vì sao việc tồn tại quá hạn không nhất thiết là lỗi TTL monitor.

### Bài 4 — Kiểm tra backlog

Đọc:

~~~javascript
db.serverStatus().metrics.ttl;
~~~

Đếm số document có **createdAt <= now - 90 giây** trong collection lab và so sánh với số liệu TTL. Vì sao một lần đọc **deletedDocuments** không cho biết chính xác số record đã bị xóa trong một khoảng thời gian ngắn?

### Bài 5 — Thay đổi thời hạn

Mô tả kế hoạch đổi TTL của collection log từ **30 ngày xuống 7 ngày** khi đang có nhiều triệu document cũ. Viết câu lệnh **collMod** cần chạy, nhưng trước đó phải giải thích bước kiểm tra dữ liệu, dọn theo batch, replication lag và rollback.

### Bài 6 — Bảo vệ endpoint đăng nhập

Cho document session:

~~~javascript
{
  sessionId: "S-001",
  userId: "U-01",
  status: "ACTIVE",
  expiresAt: ISODate("2026-01-01T10:10:00Z")
}
~~~

Tại 10:10:01 UTC, document vẫn còn trong MongoDB. API nên chấp nhận hay từ chối? Viết query có điều kiện **expiresAt > now** và giải thích tại sao TTL monitor không phải lớp kiểm soát quyền truy cập.

### Bài 7 — Time series TTL

Một bucket time series chứa các measurement từ 10:00 đến 10:40, với TTL một giờ. Tại sao measurement 10:00 có thể còn tồn tại sau 11:00? Phân biệt **bucket expiration** với **monitor cleanup delay**.

### Bài 8 — Khi business yêu cầu archive

Hệ thống phải lưu log hot 7 ngày nhưng dữ liệu audit phải được archive trong 3 năm. Hãy đề xuất luồng:

~~~text
New event -> Hot MongoDB collection
                         |
                         v
                  Archive pipeline
                         |
                         v
                  Durable archive
                         |
                         v
                TTL cleanup hot data
~~~

Nêu những bước cần kiểm tra để tránh mất dữ liệu khi archive chưa hoàn tất mà TTL đã xóa bản hot.

## 22. Câu hỏi ôn tập

1. TTL index khác index đơn trường thông thường ở tính năng nào?
2. **expireAfterSeconds:3600** trên createdAt có nghĩa gì?
3. **expireAfterSeconds:0** trên expiresAt khác với dùng 0 để “vô hiệu hóa” ra sao?
4. Tại sao token đã hết hạn vẫn có thể được **findOne** trả về?
5. Độ trễ xóa nền có thể lớn hơn 60 giây hay không? Vì sao?
6. Document thiếu field TTL hoặc lưu thời gian dạng string có được xóa theo TTL không?
7. Khi TTL field là một array BSON Dates, MongoDB chọn ngày sớm nhất hay muộn nhất?
8. TTL index có thể tạo trên compound key **{tenantId:1,expiresAt:1}** không?
9. Có thể dùng **hideIndex** để dừng TTL deletion không?
10. Vì sao rút ngắn TTL trên collection lớn có thể gây tải xóa đột ngột?
11. Dùng lệnh nào thay đổi expireAfterSeconds của một TTL index hiện hữu?
12. **metrics.ttl.passes** và **subPasses** giúp quan sát điều gì?
13. TTL deletion hoạt động ra sao trong replica set primary/secondary?
14. Vì sao time series bucket có thể còn sau thời điểm measurement sớm nhất hết hạn?
15. Trong Java/Spring Data, cần kiểm tra gì để chắc chắn expiresAt được lưu là BSON Date?
16. Nếu TTL xóa document user chỉ vì reset code hết hạn, sai lầm nằm ở đâu?

## 23. Tổng kết

TTL index là công cụ hữu ích để tự động dọn document khi **retention có thể diễn đạt bằng một giá trị Date**. Nhưng phải phân biệt **ba thời điểm**:

~~~text
1. Thời điểm dữ liệu được tạo
           |
           v
2. Thời điểm dữ liệu hết hiệu lực
     = Date + expireAfterSeconds
     hoặc = expiresAt khi expireAfterSeconds:0
           |
           | Ứng dụng phải tự từ chối dữ liệu quá hạn
           v
3. Thời điểm TTL monitor thực sự xóa document
     = bất đồng bộ, có thể trễ > 60 giây khi tải lớn
~~~

**Nguyên tắc quan trọng:**

1. TTL index thông thường là **index một trường chứa BSON Date**; không hỗ trợ compound TTL hay TTL trên _id.
2. **expireAfterSeconds** là số giây kể từ Date của document; **0** dùng khi Date chính là deadline cần xóa.
3. TTL **xóa toàn bộ document**, không chỉ xóa một field.
4. **TTL monitor dọn bất đồng bộ**, không bảo đảm xóa ngay lúc hết hạn; ứng dụng phải tự kiểm tra deadline khi phục vụ dữ liệu.
5. **Field sai kiểu/missing không tự hết hạn**, nên cần schema validation và migration dữ liệu cũ.
6. **Array các Date** dùng thời điểm **sớm nhất** để tính ngưỡng TTL.
7. **Hidden TTL index vẫn xóa**, còn thay đổi TTL của index đang tồn tại phải dùng **collMod** theo quy định.
8. **Rút ngắn TTL có thể kích hoạt backlog xóa rất lớn**; lập kế hoạch dọn theo batch và giám sát tải.
9. **Primary replica set thực hiện TTL deletion**, secondary replicate delete; time series có thêm ràng buộc xóa theo bucket.
10. TTL là một thành phần của **data lifecycle**, không thay thế logic authorization, xóa tức thời, backup hoặc archive.

### Tài liệu chính thức

- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — cấu hình, giới hạn, background deletion, pass/sub-pass và replication.
- [Expire Data from Collections](https://www.mongodb.com/docs/manual/tutorial/expire-data/) — TTL theo thời gian tương đối và tuyệt đối.
- [collMod Command](https://www.mongodb.com/docs/manual/reference/command/collMod/) — thay đổi expireAfterSeconds của index.
- [Server Parameters](https://www.mongodb.com/docs/manual/reference/parameters/) — ttlMonitorEnabled và các tham số mongod.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/) — hidden TTL index vẫn thực hiện expiration.
- [Time Series Automatic Removal](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — retention và xóa theo bucket.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — createIndex/IndexOptions và mapping BSON Date.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — @Indexed, IndexOperations và conversion.

Khi triển khai TTL trong hệ thống thực, hãy đối chiếu tài liệu với **phiên bản MongoDB/driver hiện tại**, kiểm tra BSON type của field thời gian, khối lượng dữ liệu quá hạn và topology. Cần thiết kế TTL như **dọn dữ liệu cuối vòng đời**, còn việc quyết định bản ghi **có được sử dụng tại thời điểm hiện tại** phải do nghiệp vụ kiểm tra một cách tường minh.
