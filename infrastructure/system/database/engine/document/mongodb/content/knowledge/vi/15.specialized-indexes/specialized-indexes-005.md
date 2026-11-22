# Hashed index và phạm vi truy vấn được hỗ trợ

MongoDB có nhiều loại index để tối ưu các kiểu truy vấn khác nhau. **Hashed index** là index lưu **giá trị băm (hash)** của một trường thay vì lưu nguyên giá trị trường theo thứ tự tự nhiên như B-tree index thông thường. Mục tiêu nổi bật của hashed index là hỗ trợ **truy vấn bằng nhau (equality)** và làm nền tảng cho **hashed shard key**, giúp phân phối các khóa có giá trị tăng liên tục lên nhiều vùng dữ liệu khi triển khai sharding.

Tuy nhiên, hashed index **không phải index đa năng**. Vì phép băm phá vỡ thứ tự tự nhiên của giá trị gốc, index này không thích hợp để giải quyết trực tiếp các truy vấn **phạm vi (range)**, **sắp xếp theo trường gốc (sort)** hoặc một số hình thức tối ưu như **covered query**.

Bài học giải thích cơ chế, cú pháp, phạm vi truy vấn được hỗ trợ, những hạn chế cần nhớ, thiết kế compound hashed index, quan hệ với sharding, cách quan sát query plan và các ví dụ quyết định chọn index trong ứng dụng.

## 1. Bắt đầu từ câu hỏi: index lưu gì?

Giả sử collection `events` lưu các sự kiện do người dùng tạo:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  userId: "user-10042",
  tenantId: "TENANT-A",
  type: "PAGE_VIEW",
  createdAt: ISODate("2026-03-01T08:15:00Z"),
  payload: {
    page: "/catalog",
    device: "mobile"
  }
}
```

Với index B-tree thông thường:

```javascript
db.events.createIndex({ userId: 1 });
```

MongoDB lưu khóa index theo thứ tự so sánh của giá trị `userId`. Index có thể hỗ trợ những thao tác phù hợp như tìm theo equality, một số điều kiện phạm vi trên cùng trường và sắp xếp theo trường đó, tùy query shape và query planner.

Với hashed index:

```javascript
db.events.createIndex({ userId: "hashed" });
```

MongoDB tính một giá trị băm xác định từ `userId` rồi dùng giá trị băm làm khóa index. Có thể hình dung:

```text
Giá trị gốc                 Giá trị được đánh chỉ mục
----------------------------------------------------
"user-10042"   ----hash--->  h_1 (số băm)
"user-10043"   ----hash--->  h_2
"user-10044"   ----hash--->  h_3

Quan hệ:
"user-10042" < "user-10043" < "user-10044"

Không suy ra:
h_1 < h_2 < h_3
```

Các ký hiệu `h_1`, `h_2`, `h_3` ở đây chỉ là minh họa, không phải output hash thực tế của MongoDB. Điều quan trọng là **giá trị gần nhau theo thứ tự gốc không nhất thiết có giá trị hash gần nhau**.

### 1.1. Hashed index tối ưu điều gì?

Từ một giá trị cụ thể như `"user-10042"`, MongoDB có thể tính hash tương ứng rồi tìm vùng khóa của index liên quan đến giá trị đó. Do đó, phép tìm **bằng một giá trị đã biết** là trường hợp chính.

Ngược lại, từ câu hỏi “tất cả userId từ `user-10000` đến `user-20000`”, khoảng giá trị gốc không tương ứng một đoạn liên tục của hash. MongoDB không thể dùng thứ tự hash như thứ tự userId để chạy range scan hiệu quả theo kiểu B-tree.

### 1.2. Phân biệt index và shard key

**Hashed index** là cấu trúc index của collection. **Hashed shard key** là cách MongoDB dùng hash của trường khóa để phân phối document trong một **sharded collection**.

Hai khái niệm liên quan nhưng không đồng nhất:

- Tạo `db.events.createIndex({ userId: "hashed" })` trên collection thông thường **không tự chia collection thành nhiều shard**.
- Muốn sharding phải có sharded cluster, shard key và thao tác cấu hình sharding phù hợp.
- Một sharded collection có hashed shard key dùng các giá trị hash để xác định vùng phân phối.
- Query planner có thể dùng hashed index để tìm theo equality ngay cả khi collection **không sharded**.

## 2. Tạo và quan sát hashed index

### 2.1. Tạo index trên một trường

```javascript
db.events.createIndex(
  { userId: "hashed" },
  { name: "idx_userId_hashed" }
);
```

Tham số `"hashed"` là loại index key, không phải một String được so sánh trực tiếp với trường userId. Không viết `{ userId: 1 }` nếu mục tiêu là một hashed index; đó là index tăng dần thông thường.

Xem danh sách index:

```javascript
db.events.getIndexes();
```

Trong metadata, index có key pattern dạng:

```javascript
{
  key: { userId: "hashed" },
  name: "idx_userId_hashed"
}
```

Các field metadata khác có thể tùy phiên bản và option; đoạn trên chỉ minh họa các thuộc tính quan trọng của index.

### 2.2. Một field chỉ được băm một cách xác định

Một giá trị giống nhau được ánh xạ tới hash giống nhau theo cơ chế hashing MongoDB sử dụng. Đây là cơ sở để equality lookup.

Tuy nhiên, **hash không phải định danh duy nhất tuyệt đối**:

- Về nguyên tắc, các giá trị khác nhau có thể cho cùng hash (hash collision).
- Một số loại dữ liệu số còn có các quy tắc chuẩn hóa trước khi hash.
- Vì vậy, máy chủ vẫn cần bảo đảm **so sánh đúng giá trị gốc** theo ngữ nghĩa query; không thể tự xem “hash trùng” là “document chắc chắn khớp”.

Đó cũng là lý do không nên dùng hashed index thay cho **unique index** hoặc cho rằng chỉ một hash là đủ để xác nhận danh tính của record.

### 2.3. Index không sửa nội dung document

Tạo hashed index không biến:

```javascript
{ userId: "user-10042" }
```

thành một document có trường `userId` chứa số hash. Field lưu trong BSON vẫn giữ giá trị gốc. Hash được duy trì trong **cấu trúc index** và phục vụ các thao tác phù hợp.

Nếu muốn lưu một field “hashedUserId” thực sự vào document, đó là quyết định của ứng dụng và **khác** việc tạo hashed index. Không tự thêm hash nghiệp vụ chỉ để mô phỏng cơ chế MongoDB nếu không có lý do cụ thể.

## 3. Phạm vi truy vấn: equality là trường hợp chính

### 3.1. Toán tử bằng nhau

Truy vấn equality:

```javascript
db.events.find({
  userId: "user-10042"
});
```

Hoặc viết tường minh bằng `$eq`:

```javascript
db.events.find({
  userId: { $eq: "user-10042" }
});
```

Hai dạng trên biểu diễn điều kiện bằng nhau trên field `userId`. Với hashed index phù hợp và collection đủ lớn, query planner **có thể** sử dụng index để định vị những record có hash của giá trị này.

Không nên khẳng định “cứ có hashed index là query chắc chắn dùng index”: MongoDB lựa chọn query plan dựa trên dữ liệu, độ chọn lọc, kích thước collection và các index khác. Với collection rất nhỏ, quét collection có thể rẻ hơn.

### 3.2. Truy vấn nhiều giá trị cụ thể bằng $in

```javascript
db.events.find({
  userId: {
    $in: ["user-10042", "user-10043", "user-10044"]
  }
});
```

`$in` mang nghĩa khớp một trong nhiều giá trị. Vì mỗi phần tử trong danh sách là một phép equality, hashed index có thể được xem xét để phục vụ các giá trị này.

Tuy nhiên:

- Một danh sách `$in` rất dài có thể dẫn đến nhiều phép tìm và chi phí lập kế hoạch/xử lý.
- Index không tự bảo đảm thứ tự trả về giống thứ tự các phần tử trong mảng `$in`.
- Nếu cần sắp xếp theo thời gian, tên hoặc userId, phải khai báo `sort()` và kiểm tra index tương ứng.
- Nếu field lưu không đúng kiểu BSON như dữ liệu truy vấn, equality có thể không khớp.

Ví dụ:

```javascript
db.events.find({
  userId: { $in: ["user-10042", "user-10043"] }
})
.sort({ createdAt: -1, _id: -1 })
.limit(50);
```

Hashed index trên `userId` có thể hỗ trợ điều kiện lọc, nhưng **không tự hỗ trợ sort theo `createdAt`**. Có thể cần thêm index hoặc một bước sort tùy query plan.

### 3.3. Điều kiện kết hợp với field khác

```javascript
db.events.find({
  userId: "user-10042",
  type: "PURCHASE"
});
```

Hashed index đơn trường có thể giúp tìm các record của user rồi kiểm tra `type` trên document phù hợp. Nhưng nếu mỗi user có hàng triệu event, chỉ index `userId` có thể vẫn phải duyệt rất nhiều record trước khi lọc `type`.

Hãy cân nhắc compound index khi những truy vấn kết hợp này xuất hiện thường xuyên; quyết định dựa vào workload, không chỉ vì “hashed index đã tồn tại”.

### 3.4. Các toán tử không nên mặc định tối ưu bằng hashed index

| Truy vấn trên field hashed | Hashed index có phù hợp không? | Lý do |
|---|---|---|
| `{ userId: "u42" }` | **Phù hợp** cho equality | Tính hash một giá trị cụ thể |
| `{ userId: { $eq: "u42" } }` | **Phù hợp** | Equality tường minh |
| `{ userId: { $in: ["u1", "u2"] } }` | **Có thể phù hợp** | Nhiều equality lookup |
| `{ userId: { $gt: "u100" } }` | **Không phù hợp cho range scan trên field hashed** | Hash không giữ thứ tự String |
| `{ userId: { $gte: "u100", $lt: "u200" } }` | **Không phù hợp** | Khoảng gốc không liên tục theo hash |
| `{ userId: { $ne: "u42" } }` | Thường không hiệu quả | Điều kiện phủ phần lớn miền giá trị |
| `{ userId: { $nin: [...] } }` | Thường không hiệu quả | Không phải tập equality dương chọn lọc |
| `{ userId: /^user-10/ }` | **Không hỗ trợ prefix range theo String** | Hash mất quan hệ tiền tố |
| `sort({ userId: 1 })` | **Không thể dùng hash để trả thứ tự userId gốc** | Thứ tự hash khác thứ tự String |
| Projection chỉ từ hashed index | **Không thể covered query bằng hashed index** | Index chứa hash thay vì field gốc |

Bảng này nói về khả năng **tận dụng hashed key để tối ưu điều kiện**. MongoDB vẫn có thể **thực thi** các query range, regex, sort hay `$ne` bằng collection scan hoặc một index khác. “Hashed index không hỗ trợ range” **không có nghĩa MongoDB không cho phép viết range query**.

## 4. Vì sao hashed index không hỗ trợ range query?

B-tree index thông thường trên giá trị số có thứ tự:

```text
Giá trị gốc được index:
10, 11, 12, 13, 14, 15, 16, 17, 18, 19

Truy vấn score >= 12 và score < 18:
              [12, 13, 14, 15, 16, 17]
```

Index có thể tìm điểm bắt đầu `12` rồi quét đến trước `18`.

Với hashed index:

```text
Gốc:   10, 11, 12, 13, 14, 15, 16, 17, 18, 19
Hash:  h7, h2, h9, h1, h5, h0, h8, h3, h6, h4

Thứ tự hash:
h0, h1, h2, h3, h4, h5, h6, h7, h8, h9
```

Mỗi giá trị trong khoảng `[12, 18)` có thể nằm ở vị trí hash khác nhau. Không có một đoạn index liên tục tương ứng với khoảng số đó. Vì vậy, hashed index không phải cấu trúc dùng để tăng tốc truy vấn:

```javascript
db.metrics.find({
  score: { $gte: 50, $lt: 100 }
});
```

Nếu `score` có hashed index mà ứng dụng chủ yếu chạy range query, hãy tạo **B-tree index thông thường** phù hợp:

```javascript
db.metrics.createIndex({ score: 1 });
```

### 4.1. Range kết hợp equality vẫn cần xem khóa nào dùng range

Một query:

```javascript
db.events.find({
  userId: "user-10042",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
});
```

Ở đây:

- `userId` được so sánh **bằng nhau**: phù hợp hashed lookup.
- `createdAt` được lọc bằng **khoảng Date**: cần một khóa B-tree có thứ tự Date nếu muốn tối ưu phạm vi.

Hashed index **đơn trường** `{ userId: "hashed" }` không giúp range scan trên `createdAt`. Nhưng điều đó không cấm một **compound hashed index** có trường Date thông thường, như phần sau.

### 4.2. Regex và tiền tố không chuyển thành range trên hash

Một B-tree index String đôi khi có thể hỗ trợ prefix regex có neo đầu chuỗi, tùy collation/pattern:

```javascript
db.users.find({
  username: /^nguyen/
});
```

Nhưng hashed index trên `username` không lưu các username bắt đầu bằng `nguyen` nằm gần nhau. Khi ứng dụng thường tìm prefix, auto-complete hoặc sắp theo tên, cần đánh giá B-tree/text/search index phù hợp với semantics truy vấn, không chọn hash chỉ vì dữ liệu là String.

## 5. Hashed index và sort: không giữ thứ tự gốc

Lệnh:

```javascript
db.events.find({})
  .sort({ userId: 1 })
  .limit(20);
```

đòi kết quả theo thứ tự so sánh của **userId gốc**, không theo thứ tự hash. Hashed index không thể được xem là một B-tree index tăng dần trên `userId`.

Tương tự:

```javascript
db.events.find({ userId: "user-10042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Hashed lookup giúp lọc theo `userId`, nhưng nếu có rất nhiều document của cùng user, MongoDB vẫn phải sắp xếp hoặc dùng một index khác hỗ trợ sort theo `createdAt`. Một index B-tree thông thường có thể phù hợp hơn:

```javascript
db.events.createIndex({
  userId: 1,
  createdAt: -1,
  _id: -1
});
```

Index trên cho phép equality ở `userId`, rồi đọc các event theo thời gian trong vùng khóa phù hợp. Nó có thể hỗ trợ cả **lọc theo user** và **sort theo thời gian**, thay vì chỉ tối ưu hash equality.

### 5.1. Đừng nhầm thứ tự query với thứ tự shard

Hashed sharding có thể phân phối các khóa tăng đều giữa nhiều shard để tránh dồn insert vào vùng khóa cuối của một shard. **Điều đó không làm kết quả query trở nên được sắp xếp**. Sharded query muốn có thứ tự xác định vẫn cần `sort()`, query planner và các index cần thiết.

### 5.2. Có thể vừa có hashed index vừa có B-tree index?

Có thể cần cả hai nếu các workload khác nhau biện minh được chi phí:

```javascript
db.events.createIndex(
  { userId: "hashed" },
  { name: "userId_hashed" }
);

db.events.createIndex(
  { userId: 1, createdAt: -1 },
  { name: "userId_createdAt_desc" }
);
```

Tuy nhiên, mỗi index tốn bộ nhớ/dung lượng và chi phí insert/update/delete. Nếu không dùng sharding và phần lớn query là equality + sort/range trên field khác, B-tree compound index có thể đáp ứng tốt mà **không cần** hashed index riêng. Chỉ duy trì cả hai khi có lợi ích đo được hoặc cần hashed index phục vụ sharding.

## 6. Covered query: hashed index không thể trả lại trường gốc chỉ từ hash

Một **covered query** là truy vấn có thể được phục vụ hoàn toàn từ index cho những trường cần lọc và trả kết quả, không cần đọc document ở bước `FETCH` (với các điều kiện và hạn chế cụ thể).

Ví dụ B-tree index:

```javascript
db.users.createIndex({
  tenantId: 1,
  username: 1
});
```

Query:

```javascript
db.users.find(
  { tenantId: "TENANT-A" },
  { _id: 0, username: 1 }
);
```

Trong điều kiện phù hợp, index có thể cung cấp username gốc và lọc tenant, dẫn đến covered query.

Với hashed index:

```javascript
db.users.createIndex({
  username: "hashed"
});
```

Index lưu **hash(username)** chứ không lưu nguyên username. Nó không thể trả giá trị `username` gốc chỉ bằng cách lấy hash và giải mã ngược — hash không phải phép mã hóa có thể đảo lại. MongoDB **không dùng hashed index để cover query**.

Ví dụ:

```javascript
db.users.find(
  { username: "nguyen.an" },
  { username: 1, _id: 0 }
);
```

Ngay cả khi query có thể dùng hashed index để định vị candidate, engine vẫn phải kiểm tra document để lấy/đối chiếu dữ liệu gốc theo semantics của truy vấn. Không nên suy luận rằng “chỉ có một field được trả về” thì hashed index sẽ thành covered query.

Điều này cũng liên quan tới hash collision: giá trị hash chỉ thu hẹp ứng viên, còn sự tương đương thật phải xác nhận trên giá trị gốc.

## 7. Quy tắc cho kiểu dữ liệu của field hashed

### 7.1. Không dùng field dạng array

**Hashed index không hỗ trợ multikey hashing trên array** như một multikey index thông thường. Không nên tạo hashed index cho trường có thể chứa array:

```javascript
{
  _id: 1,
  tags: ["mongodb", "database", "backend"]
}
```

Nếu muốn tìm document có tag bằng `"mongodb"`, dùng B-tree multikey index:

```javascript
db.articles.createIndex({ tags: 1 });

db.articles.find({ tags: "mongodb" });
```

Khi tạo hashed index trên trường có array hoặc chèn/cập nhật một array vào field đã có hashed index, MongoDB có thể từ chối thao tác do giới hạn multikey hashed index. Với compound hashed index, cũng phải xét hạn chế multikey của loại index trong phiên bản triển khai; tránh thiết kế các trường index có thể trở thành array mà không kiểm tra.

### 7.2. Quy tắc hashing của các kiểu số

Một điểm dễ bất ngờ: khi hash giá trị **floating point**, MongoDB có quy tắc chuyển giá trị sang số nguyên 64-bit trước khi băm. Điều này có thể khiến **những giá trị số khác nhau chia sẻ một hash**.

Ví dụ mang tính khái niệm:

```javascript
db.scores.insertMany([
  { _id: "S1", score: 2.1 },
  { _id: "S2", score: 2.8 },
  { _id: "S3", score: 3.2 }
]);

db.scores.createIndex({ score: "hashed" });
```

Các giá trị `2.1` và `2.8` có thể bị quy về phần nguyên tương ứng khi hash, vì vậy không được giả định mỗi số thập phân khác nhau luôn có khóa hash khác nhau.

**Điều quan trọng:** truy vấn `{ score: 2.1 }` không vì thế được phép trả sai `2.8`. MongoDB còn kiểm tra điều kiện theo giá trị gốc. Hashed index không dùng để cưỡng chế uniqueness; với các phép so sánh phạm vi số học, B-tree index phù hợp hơn.

Nếu dữ liệu số có kích thước rất lớn, giá trị Decimal128, Double, Int64 hoặc sự pha trộn kiểu, cần hiểu chính xác quy tắc hashing của phiên bản MongoDB đang dùng trước khi chọn field làm hashed shard key. Không nên dùng giá trị floating point làm shard key nếu nghiệp vụ kỳ vọng mỗi chênh lệch thập phân được phân phối như các khóa hoàn toàn độc lập.

### 7.3. Null, trường thiếu và schema không nhất quán

Một collection có thể chứa:

```javascript
{ _id: "A", userId: "user-10042" }
{ _id: "B", userId: null }
{ _id: "C" }
```

Truy vấn `{ userId: null }` trong MongoDB có semantics khớp giá trị null và trường thiếu ở những trường hợp thông thường. Việc index hóa và sử dụng hashed index không tự thay đổi semantics của null/missing.

Nếu field hashed là shard key, quy tắc thiếu field/null còn liên quan routing và phân bố shard; cần chuẩn hóa schema và kiểm tra các giới hạn sharding. Với mã người dùng hoặc mã khách hàng, thường nên yêu cầu **giá trị hợp lệ, kiểu đồng nhất và độ phân biệt cao**, thay vì để nhiều document có khóa null.

### 7.4. Hash không thay thế mã hóa bảo mật

Hashed index **không phải công cụ che giấu dữ liệu**. Document vẫn lưu giá trị gốc, index có hash phục vụ tra cứu, còn quyền đọc field và bảo vệ dữ liệu phụ thuộc authentication, authorization, encryption và chính sách hệ thống.

Không nên lưu password rồi tạo hashed index và cho rằng password đã được bảo vệ. Password cần được xử lý bằng thuật toán password hashing chuyên dụng (salted, có work factor), không phải bằng MongoDB hashed index.

## 8. Unique index: không thể đặt unique trên hashed index

Một yêu cầu thường gặp: “Mỗi userId phải xuất hiện duy nhất, vậy dùng hashed index với `unique: true` được không?”

**Không.** Hashed indexes không hỗ trợ ràng buộc unique theo cách của unique B-tree index. Không dùng:

```javascript
// Không phải thiết kế hợp lệ để cưỡng chế uniqueness.
db.users.createIndex(
  { username: "hashed" },
  { unique: true }
);
```

Muốn unique username, dùng B-tree unique index:

```javascript
db.users.createIndex(
  { username: 1 },
  { unique: true }
);
```

Nếu hệ thống phải kiểm tra uniqueness theo tenant:

```javascript
db.users.createIndex(
  { tenantId: 1, username: 1 },
  { unique: true }
);
```

Trong ứng dụng, hãy xử lý duplicate-key error khi hai request đồng thời tạo cùng username; việc “find trước rồi insert” không thay thế unique constraint ở database.

### 8.1. Nếu collection dùng hashed shard key thì sao?

Trong sharded collection, MongoDB áp dụng các ràng buộc về unique index và shard key. Một B-tree unique index thêm vào **không được mặc định coi là enforce uniqueness toàn cluster** khi key pattern không tương thích với shard key theo quy tắc của phiên bản MongoDB.

Ví dụ hashed shard key `userId` có thể hữu ích để phân phối dữ liệu nhưng không đồng nghĩa uniqueness của `username` trên toàn cluster được bảo vệ chỉ bằng cách tạo thêm index `{ username: 1 }`. Thiết kế cần xác định ranh giới unique theo tenant/shard, ứng dụng hay collection registry riêng nếu cần.

**Chọn hashed shard key và chọn unique constraint là hai quyết định riêng**; phải kiểm tra khả năng kết hợp của chúng trước khi triển khai.

### 8.2. Collision không phải duplicate key

Ngay cả khi hai giá trị khác nhau có cùng hash, hashed index vẫn không thể được dùng để kết luận chúng là cùng một giá trị nghiệp vụ. Một unique index thông thường so sánh khóa theo ngữ nghĩa index/collation; hashed index chỉ phục vụ điều hướng candidate lookup.

## 9. Compound hashed index: kết hợp hash với khóa có thứ tự

MongoDB hỗ trợ **compound hashed indexes** trong các phiên bản có tính năng này. Một compound hashed index kết hợp **một field hashed** với những field dùng thứ tự B-tree thông thường.

Ví dụ:

```javascript
db.events.createIndex(
  {
    tenantId: 1,
    userId: "hashed",
    createdAt: -1
  },
  {
    name: "tenant_userHash_createdAt"
  }
);
```

Cách hiểu:

1. `tenantId: 1` là khóa có thứ tự thông thường, đứng đầu index.
2. `userId: "hashed"` lưu giá trị hash của userId.
3. `createdAt: -1` là trường Date có thứ tự giảm dần **bên trong một vùng các khóa tiền tố phù hợp**.

Chỉ nên có **một trường hashed** trong cùng compound hashed index; không xem đó là cách băm cả document hoặc băm mọi trường trong key pattern.

### 9.1. Query equality rồi range trên trường thường

Với query:

```javascript
db.events.find({
  tenantId: "TENANT-A",
  userId: "user-10042",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
})
.sort({ createdAt: -1 })
.limit(100);
```

Về mặt cấu trúc khóa, index có thể tận dụng:

- Equality `tenantId` ở phần prefix.
- Equality `userId` qua hash ở trường kế tiếp.
- Range và sort `createdAt` trên trường B-tree thông thường phía sau, khi các trường tiền tố được ràng buộc bằng equality thích hợp.

Như vậy, **compound hashed index có thể tham gia query chứa range**, nhưng range nằm trên **trường B-tree khác**, không phải trên chính field hashed.

Phải phân biệt phát biểu:

- “Hashed key không cung cấp range order cho giá trị gốc” — đúng.
- “Bất kỳ compound index nào có một hashed field đều không dùng được cho bất kỳ range query nào” — quá rộng và dễ sai.

### 9.2. Query chỉ có tenantId

```javascript
db.events.find({
  tenantId: "TENANT-A"
});
```

Vì `tenantId` là field đứng đầu index, truy vấn có thể tận dụng prefix index tùy planner và độ chọn lọc. Nhưng nếu tenant A chiếm phần lớn collection, planner có thể chọn kế hoạch khác.

### 9.3. Query chỉ có userId

```javascript
db.events.find({
  userId: "user-10042"
});
```

Nếu compound index bắt đầu bằng `tenantId`, query không ràng buộc tenantId có thể không tận dụng tốt cấu trúc tiền tố. Không nên tự giả định index `{ tenantId: 1, userId: "hashed" }` thay thế hoàn toàn index `{ userId: "hashed" }` cho mọi query chỉ lọc userId.

Nếu ứng dụng luôn có tenantId từ ngữ cảnh xác thực, query có tenantId thường hợp lý và giúp tránh đọc cross-tenant. Nếu người dùng cần tìm user trên mọi tenant, đó là một workload khác và có thể cần index khác.

### 9.4. Range trên chính userId vẫn không được hash hỗ trợ

```javascript
db.events.find({
  tenantId: "TENANT-A",
  userId: { $gte: "user-10000", $lt: "user-20000" }
});
```

Index ở phần 9 không có thứ tự userId gốc; field hashed không thể cung cấp một đoạn range theo chữ/số của userId. Nếu đây là query thường xuyên, dùng B-tree compound index:

```javascript
db.events.createIndex({
  tenantId: 1,
  userId: 1
});
```

### 9.5. Vị trí trường hashed ảnh hưởng query shape

So sánh:

```javascript
// A: thường thuận lợi khi mọi query luôn lọc tenantId.
db.events.createIndex({
  tenantId: 1,
  userId: "hashed",
  createdAt: -1
});

// B: hashed userId đứng đầu, target workload theo userId.
db.events.createIndex({
  userId: "hashed",
  createdAt: -1
});
```

Hai index có field khác nhau ở đầu nên phạm vi ứng dụng khác nhau. Chọn theo các truy vấn thực tế và ràng buộc của sharding nếu index còn dùng làm shard-key index. Không phải cứ thêm nhiều field vào compound index là mọi query đều tốt hơn: index rộng hơn tốn dung lượng và chi phí cập nhật.

## 10. Hashed shard key: phân phối giá trị tăng liên tục

Hashed sharding là use case nổi bật. Ví dụ một collection có khóa `_id` là giá trị tăng liên tục:

```text
1, 2, 3, 4, 5, 6, ...
```

Với range-based sharding trực tiếp theo khóa tăng, nhiều insert mới có thể tập trung ở vùng khóa cuối và gây **hot shard** nếu phân phối không thích hợp.

Hashed shard key biến mỗi giá trị thành hash trước khi ánh xạ tới vùng shard-key range:

```text
_id 1000001 -> hash H1 -> vùng shard A
_id 1000002 -> hash H2 -> vùng shard C
_id 1000003 -> hash H3 -> vùng shard B
...
```

Những khóa tăng liên tục ở miền gốc được phân tán hơn trong miền hash. Điều này có thể giúp **phân phối write load** tốt hơn khi có nhiều giá trị shard key khác nhau.

### 10.1. Ví dụ ý tưởng cấu hình trên sharded cluster

Chỉ thực hiện trong một **sharded cluster** đã được cấu hình, với quyền quản trị và kế hoạch shard key phù hợp:

```javascript
// Ví dụ namespace app.events, chạy qua mongos.
use app;

// Tạo hashed index tương ứng nếu cần.
db.events.createIndex({ userId: "hashed" });

// Shard collection theo hashed userId.
sh.shardCollection("app.events", { userId: "hashed" });
```

Cú pháp và điều kiện thao tác phụ thuộc phiên bản MongoDB/triển khai. Sharding còn cần đánh giá cardinality, phân bố giá trị, các giá trị thiếu/null, khối lượng document, routing query, migration chunk và giới hạn unique index; không chạy lệnh mẫu trên production chỉ vì thấy hashed index tồn tại.

### 10.2. Query equality trên shard key có lợi thế routing

Nếu shard key là `{ userId: "hashed" }`, query với equality chính xác:

```javascript
db.events.find({ userId: "user-10042" });
```

thường có thể **target** vùng shard chứa giá trị hash tương ứng (theo metadata phân bố hiện tại), thay vì phải gửi toàn bộ truy vấn tới mọi shard.

Ngược lại, query:

```javascript
db.events.find({
  createdAt: { $gte: ISODate("2026-03-01T00:00:00Z") }
});
```

không chứa shard key nên có thể phải **scatter-gather** trên nhiều shard. Range trên chính shard key gốc cũng không tương ứng với một miền hash liên tục.

Chọn shard key không chỉ để ghi phân tán. Nếu hầu hết truy vấn cần đọc theo tenant, thời gian và trạng thái, một shard key không xuất hiện trong query có thể làm phần lớn read load trở nên tốn kém.

### 10.3. Hashed sharding không giải quyết hot key đơn lẻ

Giả sử một user rất nổi tiếng tạo hàng nghìn event mỗi giây và mọi document đều có:

```javascript
{ userId: "celebrity-1" }
```

Hash của `"celebrity-1"` là **một giá trị cố định**. Tất cả các document có cùng shard key value sẽ được định tuyến tới cùng phạm vi khóa của sharding. Thêm shard không tự phân bố một giá trị userId duy nhất.

Cần phân biệt:

- **Monotonic hot range:** nhiều giá trị khóa khác nhau nhưng tăng về phía cuối miền — hashed sharding có thể giúp phân tán.
- **Hot key:** một giá trị khóa đơn lẻ nhận gần như toàn bộ tải — hash của nó vẫn chỉ là một giá trị.

Với hot key thực sự, có thể cân nhắc phân vùng bổ sung ở mô hình dữ liệu như bucket/suffix, chọn compound shard key phù hợp, hoặc tách lưu lượng theo sự kiện. Mỗi giải pháp đều ảnh hưởng truy vấn và uniqueness; không nên tự thêm số ngẫu nhiên vào khóa mà bỏ qua cách đọc theo user.

### 10.4. Không giữ locality theo khoảng gốc

Hash phân tán các giá trị gần nhau. Nếu workload thường hỏi:

```javascript
db.orders.find({
  orderNo: { $gte: 100000, $lt: 101000 }
});
```

range theo `orderNo` có thể trải rộng trên nhiều shard khi `orderNo` là hashed shard key. Đây là đánh đổi: **phân phối insert đều hơn** nhưng **range locality thấp hơn**.

Trước khi chọn hashed shard key, cần biết phần lớn query là equality theo shard key hay range trên nó. Nếu range scans rất quan trọng, range-based sharding hoặc một key design khác có thể phù hợp hơn.

## 11. Hashed index có thể được dùng cho sort trên field khác không?

Một câu hỏi tinh tế: “Đã nói hashed index không hỗ trợ sort, vậy compound hashed index có `createdAt: -1` ở sau có hỗ trợ sort không?”

Cần tách hai ý:

1. Hashed key **không giữ thứ tự giá trị gốc** của chính field hashed.
2. Trong compound index, **các field B-tree thông thường** vẫn có thứ tự trong vùng khóa phù hợp.

Ví dụ:

```javascript
db.events.createIndex({
  tenantId: 1,
  userId: "hashed",
  createdAt: -1
});
```

Khi query equality cả `tenantId` và `userId`, các record phù hợp ở cùng vùng khóa tiền tố có thể được truy xuất theo `createdAt` giảm dần qua phần B-tree của index.

```javascript
db.events.find({
  tenantId: "TENANT-A",
  userId: "user-10042"
})
.sort({ createdAt: -1 })
.limit(20);
```

Khả năng sử dụng index vẫn phải xác minh bằng explain. Không nên mở rộng kết luận này thành “hashed index có thể sort theo userId gốc”: điều đó vẫn không đúng.

Với query chỉ ràng buộc tenantId nhưng không ràng buộc userId, thứ tự khóa tổng thể vẫn phân nhóm theo **hash(userId)** trước createdAt, nên index không tự cho một danh sách toàn tenant được sắp giảm dần tuyệt đối theo createdAt.

Đây chính là lý do **thứ tự các field trong compound index** quan trọng.

## 12. Xem explain để biết index thực sự được dùng

Không nên đoán index từ tên hoặc chỉ vì index đã được tạo. Dùng `explain("executionStats")` để quan sát query plan.

### 12.1. Equality query

```javascript
db.events.find({
  userId: "user-10042"
}).explain("executionStats");
```

Khi planner dùng hashed index, kế hoạch thường có phần truy cập index tương ứng; các stage cụ thể có thể khác giữa phiên bản/query engine.

Những thông tin hữu ích:

| Trường hoặc stage | Ý nghĩa |
|---|---|
| `winningPlan` | Kế hoạch được chọn |
| `IXSCAN` | Có bước duyệt index |
| `FETCH` | Cần truy xuất document hoặc xác minh kết quả |
| `COLLSCAN` | Quét collection |
| `SORT` | Có bước sort bổ sung |
| `totalKeysExamined` | Số khóa index đã xét |
| `totalDocsExamined` | Số document đã kiểm tra |
| `nReturned` | Số document kết quả |
| `executionTimeMillis` | Thời gian được công cụ explain ghi nhận |

Có thể thấy `FETCH` ngay cả khi hashed index giúp lọc, vì index chứa hash chứ không phải giá trị gốc và hashed index không cover query.

### 12.2. So sánh với range query

```javascript
db.events.find({
  userId: {
    $gte: "user-10000",
    $lt: "user-20000"
  }
}).explain("executionStats");
```

Không kỳ vọng hashed index trên userId cung cấp một range scan theo thứ tự userId gốc. MongoDB có thể chọn collection scan hoặc index B-tree khác. Nếu query thường xuyên, nên so sánh kế hoạch khi có index `{ userId: 1 }` trong môi trường thử.

### 12.3. So sánh sort query

```javascript
db.events.find({
  userId: "user-10042"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Nếu chỉ có hashed index đơn trường, engine có thể cần bước sort bổ sung cho `createdAt`. Khi có compound B-tree hoặc compound hashed index phù hợp, kế hoạch có thể khác. Đừng chỉ đo thời gian một lần trên collection vài chục record; hãy thử với dữ liệu có phân bố và số lượng đại diện workload thực tế.

### 12.4. Dùng hint cẩn trọng

Để tìm hiểu hành vi index trong môi trường thử, có thể dùng `hint()`:

```javascript
db.events.find({
  userId: "user-10042"
})
.hint("idx_userId_hashed")
.explain("executionStats");
```

`hint()` buộc một index cụ thể được xem xét sử dụng theo ngữ nghĩa của API; nó **không biến hashed index thành hỗ trợ range hay sort gốc**. Không đưa hint vào code production chỉ dựa vào một thử nghiệm nhỏ, vì dữ liệu và query plan có thể thay đổi.

## 13. Thiết kế index theo workload thay vì theo tên field

Giả sử collection có ba nhóm truy vấn:

**Nhóm A — tìm sự kiện của một user theo ID:**

```javascript
db.events.find({ userId: "user-10042" });
```

**Nhóm B — lấy lịch sử user theo thời gian:**

```javascript
db.events.find({
  userId: "user-10042",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z")
  }
})
.sort({ createdAt: -1 })
.limit(100);
```

**Nhóm C — phân tích sự kiện toàn hệ thống theo thời gian:**

```javascript
db.events.find({
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
});
```

Các lựa chọn ứng viên:

| Workload | Index ứng viên | Giải thích |
|---|---|---|
| A: equality userId | `{ userId: "hashed" }` hoặc `{ userId: 1 }` | Cả hai có thể hỗ trợ equality; hash có ý nghĩa hơn khi đi cùng sharding strategy |
| B: equality userId + Date range/sort | `{ userId: 1, createdAt: -1 }` | B-tree compound trực tiếp phục vụ equality + thứ tự Date |
| B trên collection cần hashed field | `{ userId: "hashed", createdAt: -1 }` | Hash equality ở prefix, Date có thứ tự phía sau |
| C: Date range toàn collection | `{ createdAt: 1 }` | Range scan theo thời gian |
| Prefix username | `{ username: 1 }` hoặc search index chuyên biệt | Hash không giữ tiền tố String |
| Unique username | `{ username: 1 }` với `unique: true` | Hashed index không unique |
| Hashed shard key phân phối event theo user | `{ userId: "hashed" }` làm nền shard key | Đánh đổi locality; cân nhắc hot userId |
| Sort toàn tenant theo createdAt | `{ tenantId: 1, createdAt: -1, _id: -1 }` | Tránh hashed field không ràng buộc đứng giữa |

Không nên mặc định tạo tất cả các index ứng viên: mỗi index tăng chi phí ghi, cache và storage. Thiết kế index là lựa chọn giữa **tần suất truy vấn, độ chọn lọc, lượng dữ liệu, phân phối shard, kích thước index và write amplification**.

### 13.1. Hashed index có thể dư thừa nếu chỉ có equality trên collection nhỏ

Nếu collection có vài nghìn user và truy vấn chủ yếu:

```javascript
db.users.findOne({ emailNormalized: "a@example.com" });
```

B-tree index `{ emailNormalized: 1 }` có thể đã đáp ứng tốt, đồng thời còn cho phép unique và một số dạng range/sort. Thêm hashed index không có nghĩa lookup luôn nhanh hơn.

Hash không phải phép tăng tốc thần kỳ cho mọi equality. Nó đặc biệt hữu ích trong **kiến trúc phân phối khóa** hoặc những trường hợp thiết kế index đã được đo phù hợp.

### 13.2. Field có cardinality thấp không tạo được phân phối tốt

Một shard key hashed như `status` với chỉ ba giá trị:

```javascript
{ status: "NEW" }
{ status: "PAID" }
{ status: "CANCELLED" }
```

chỉ có một số rất ít giá trị hash riêng biệt. Hàng triệu document cùng status vẫn tập trung theo những giá trị khóa tương ứng; hashed sharding không tự biến ba trạng thái thành hàng triệu phân vùng độc lập. Nên ưu tiên shard key có **cardinality cao** và phân bố ghi phù hợp.

### 13.3. Không chọn field bị sửa thường xuyên làm shard key mà không hiểu hệ quả

Field nằm trong shard key có ảnh hưởng lớn tới routing và vị trí lưu trữ. Một field hay thay đổi có thể tạo nghiệp vụ và chi phí vận hành phức tạp khi cần thay đổi khóa; không nên chọn hashed shard key chỉ vì một trường hiện có được ghi thường xuyên. Cần hiểu tính ổn định, cardinality, quyền cập nhật shard key và các hạn chế của phiên bản đang triển khai.

## 14. Ví dụ ứng dụng Java MongoDB Driver

Trong Java Sync Driver, có thể tạo hashed index bằng builder `Indexes.hashed()`.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

MongoDatabase database = mongoClient.getDatabase("app");
MongoCollection<Document> events = database.getCollection("events");

// Hashed index trên userId.
String indexName = events.createIndex(Indexes.hashed("userId"));
System.out.println(indexName);
```

Truy vấn equality:

```java
import com.mongodb.client.model.Filters;

for (Document event : events.find(
        Filters.eq("userId", "user-10042"))) {
    System.out.println(event.toJson());
}
```

Truy vấn range theo thời gian và sort:

```java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Sorts.descending;

import java.util.Date;

Date from = new Date(1772323200000L);

for (Document event : events.find(
        and(
            eq("userId", "user-10042"),
            gte("createdAt", from)
        ))
        .sort(descending("createdAt"))
        .limit(50)) {
    System.out.println(event.toJson());
}
```

Ví dụ trình bày cách gọi driver; **không** khẳng định hashed index đơn trường tự hỗ trợ sort createdAt. Muốn kiểm soát query plan, tạo index theo workload và dùng explain/monitoring của driver hoặc `mongosh`.

Với Spring Data MongoDB, có thể tạo index qua các API index-operations tương ứng trong phiên bản đang dùng. Nên quản lý index thông qua migration/deployment có kiểm soát, không nhất thiết tạo index lặp lại mỗi khi ứng dụng khởi động.

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Hashed index lưu nguyên userId đã sắp xếp.” | Index lưu hash của giá trị, không giữ thứ tự gốc. |
| “Có hashed index thì mọi điều kiện query đều nhanh.” | Chủ yếu hữu ích cho equality; range/sort trên hashed field không tận dụng thứ tự gốc. |
| “Không hỗ trợ range nghĩa là query `$gte` bị cấm.” | Query vẫn hợp lệ, nhưng cần index khác/scan để phục vụ hiệu quả. |
| “`$in` là range query.” | `$in` là nhiều giá trị equality, có thể được hashed index hỗ trợ. |
| “Hashed index tự sắp xếp userId alphabetically.” | Không; `sort({ userId: 1 })` cần thứ tự String gốc. |
| “Hashed index cover query nếu chỉ trả một field.” | Không; hash không chứa giá trị gốc để cover. |
| “Có thể `unique: true` trên hashed index.” | Hashed index không hỗ trợ unique constraint như B-tree unique index. |
| “Mỗi số Double khác nhau luôn cho hash khác nhau.” | Các quy tắc chuyển numeric trước hashing có thể tạo hash trùng. |
| “Hashed index hỗ trợ mảng tags như multikey.” | Không; hashed index không hỗ trợ multikey hash trên array. |
| “Tạo hashed index là đã sharding.” | Không; sharding cần sharded cluster và shard key. |
| “Hashed shard key giải quyết một user quá nóng.” | Một giá trị userId vẫn cho một hash; hot key không tự phân tán. |
| “Hash _id tăng dần thì order range vẫn ở gần nhau.” | Hash làm mất locality của khoảng giá trị gốc. |
| “Compound hashed index không dùng được với bất kỳ range nào.” | Range có thể được hỗ trợ trên field B-tree khác khi prefix phù hợp; không phải trên field hashed. |
| “Mọi query có index đều nên dùng hint.” | Planner có thể chọn index khác tốt hơn; hint cần đo và kiểm soát. |

## 16. Quy trình đánh giá trước khi chọn hashed index

Một quy trình thiết kế thực tế nên bắt đầu bằng các **query shape** thay vì loại index mong muốn.

**Bước 1 — Liệt kê truy vấn.** Ghi filter, sort, projection, limit và tần suất cho những endpoint hoặc batch job quan trọng. Ví dụ: tìm user bằng ID, phân trang lịch sử user theo thời gian, thống kê toàn hệ thống theo khoảng ngày.

**Bước 2 — Xác định kiểu toán tử trên candidate hashed field.** Nếu chủ yếu là `$eq`/`$in`, hashed index có thể phù hợp. Nếu `$gte`, `$lt`, regex prefix, sort hay unique chiếm phần lớn, B-tree hoặc index chuyên biệt khác thường cần thiết.

**Bước 3 — Đánh giá loại dữ liệu.** Field có thể là array không? Có null/missing? Có số thực hay nhiều BSON number type? Có được sửa sau khi insert? Với hashed shard key, cardinality và phân bố giá trị có đủ cao không?

**Bước 4 — Chọn standalone hay compound.** Nếu query cần tenantId, userId equality và thời gian, cân nhắc thứ tự các field trong compound index. Nếu query chỉ userId, prefix khác có thể làm index không phù hợp.

**Bước 5 — Xác định có sharding không.** Nếu chỉ muốn query equality, B-tree có thể đã đủ. Nếu mục tiêu là phân tán các giá trị shard key tăng dần, đánh giá hashed sharding và các hệ quả về read routing/uniqueness.

**Bước 6 — Đo với dữ liệu đại diện.** Dùng `explain("executionStats")`, đo số key/doc examined, p95 latency, dung lượng index, tốc độ insert/update và mức phân phối tải.

**Bước 7 — Triển khai có kiểm soát.** Tạo index qua migration, quan sát tác động build, theo dõi query plan sau rollout và giữ phương án rollback. Không bỏ index cũ chỉ vì tạo hashed index mới.

## 17. Bài tập thực hành

### Bài 1 — Equality và range trên cùng một trường

Tạo collection `hashedLab` với 10.000 document có `userId` là chuỗi và `createdAt` là BSON Date.

1. Tạo `db.hashedLab.createIndex({ userId: "hashed" })`.
2. Dùng `explain("executionStats")` cho query `{ userId: "user-42" }`.
3. Dùng explain cho `{ userId: { $gte: "user-100", $lt: "user-200" } }`.
4. Tạo B-tree index `{ userId: 1 }` trong môi trường thử và so sánh query plan.
5. Giải thích vì sao hash equality không cung cấp một đoạn range theo String gốc.

### Bài 2 — Sorting sau hashed lookup

Với một user có nhiều event, viết query lấy 20 event mới nhất.

1. Dùng hashed index đơn trường `{ userId: "hashed" }`.
2. Quan sát bước sort khi query `sort({ createdAt: -1 })`.
3. Tạo `{ userId: 1, createdAt: -1 }` và so sánh kế hoạch.
4. Thiết kế thêm phiên bản compound hashed nếu yêu cầu kiến trúc có hashed field và giải thích điều kiện equality prefix.

### Bài 3 — Numeric hashing

Insert các record có `score` là số thực `2.1`, `2.8` và `3.2`. Tạo hashed index trên `score`, chạy equality query `score: 2.1` rồi xác nhận kết quả không phải mọi document chung hash. Giải thích vì sao index không thể là unique index cho điểm số.

### Bài 4 — Compound hashed index

Tạo:

```javascript
db.events.createIndex({
  tenantId: 1,
  userId: "hashed",
  createdAt: -1
});
```

Đánh giá bốn query:

1. Equality cả `tenantId` và `userId`.
2. Equality cả hai và range `createdAt`.
3. Chỉ equality `userId`, không có `tenantId`.
4. Equality tenantId và range trên `userId` gốc.

Query nào phù hợp cấu trúc index? Query nào cần một B-tree index khác? Vì sao vị trí các key quan trọng?

### Bài 5 — Hashed sharding với ID tăng dần

Giả sử mỗi phút tạo một triệu đơn hàng với `orderNo` tăng liên tục. Phân tích khả năng tạo hot shard khi range-shard trực tiếp theo orderNo và lý do hashed shard key có thể cải thiện phân phối write.

Sau đó đánh giá query `orderNo >= 500000 and orderNo < 600000`: hashed sharding gây ra đánh đổi gì? Nếu tất cả request cùng cập nhật một orderNo duy nhất thì hash có giải quyết hot key không?

### Bài 6 — Unique trên sharded collection

Ứng dụng có tài khoản với `tenantId` và `username`. Cần username unique trong mỗi tenant, trong khi dữ liệu được sharding theo một khóa hashed.

1. Giải thích vì sao hashed index không phải unique index.
2. Phác thảo unique B-tree index cần thiết theo nghiệp vụ.
3. Nêu vì sao phải kiểm tra ràng buộc unique index với shard key/topology trước khi triển khai.
4. Mô tả cách xử lý duplicate key khi hai request tạo cùng username.

### Bài 7 — Chọn index theo API

Một ứng dụng có:

- API A: tìm bằng `deviceId`.
- API B: tìm các deviceId bắt đầu bằng `sensor-2026`.
- API C: xem telemetry một thiết bị theo range `measuredAt`.
- API D: xem telemetry toàn hệ thống trong 24 giờ gần nhất.

Chọn index ứng viên cho từng API và nêu khi nào hashed shard key trên deviceId có thể hợp lý. Không được kết luận một hashed index đơn trường đủ cho cả bốn API.

## 18. Tài liệu MongoDB tham khảo

- [Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/)
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [Compound Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/create/)
- [Create Indexes](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/)
- [Query Plans and Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [Sharding](https://www.mongodb.com/docs/manual/sharding/)

## Kết luận

**Hashed index** lưu giá trị băm của field, vì vậy rất phù hợp để tra cứu **equality** và là nền tảng cho **hashed shard key**. Các giá trị gần nhau theo thứ tự gốc có thể phân tán trong miền hash, giúp phân phối nhiều khóa tăng liên tục giữa các shard nhưng đồng thời làm mất **range locality**.

Phạm vi hỗ trợ quan trọng nhất cần nhớ: **`$eq` và nhiều giá trị equality qua `$in` có thể tận dụng hashed index; range, prefix regex và sort theo giá trị gốc của field hashed không được phục vụ theo thứ tự hash**. Hashed index cũng không cover query, không hỗ trợ multikey trên array và không cưỡng chế uniqueness. Compound hashed index có thể kết hợp equality trên field hash với range/sort của **field B-tree khác** khi prefix phù hợp.

Cuối cùng, **index không đồng nghĩa sharding**, và **hashed sharding không giải quyết hot key đơn lẻ**. Hãy chọn hashed index theo mục tiêu phân phối và query shape, dùng B-tree khi cần range/sort/unique, rồi kiểm chứng bằng `explain()` cùng workload đại diện trước khi triển khai.

