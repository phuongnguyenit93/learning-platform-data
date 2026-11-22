# Kiểm thử unique index, TTL và các hành vi diễn ra bất đồng bộ trong MongoDB

## 1. Mở đầu: cùng là MongoDB, nhưng không phải mọi kết quả đều xuất hiện ngay

Giả sử một hệ thống Java dùng MongoDB cho ba tác vụ:

1. Đăng ký tài khoản: `emailNormalized` của mỗi tài khoản phải duy nhất.
2. Lưu mã xác minh: document phải tự biến mất khi hết hạn.
3. Gửi sự kiện: sau khi ghi đơn hàng, một background worker cập nhật collection trạng thái hoặc gửi message.

Trong ba trường hợp, cách kiểm thử **khác nhau về thời điểm quan sát**.

- **Unique index** chặn thao tác ghi gây trùng ở thời điểm server áp dụng ràng buộc, sau khi index đã sẵn sàng. Test phải xác minh lệnh thứ hai thất bại với duplicate-key, không chờ một background worker phát hiện trùng.
- **TTL index** đánh dấu document đủ điều kiện hết hạn theo dữ liệu ngày/giờ, nhưng xóa tài liệu bằng tiến trình nền. Test không được kỳ vọng document bị xóa đúng giây hết hạn.
- **Các hành vi bất đồng bộ khác** như worker xử lý outbox, secondary replication, Search indexing, Change Streams consumer, event-driven projections có độ trễ và điểm thất bại riêng. Test phải chờ **điều kiện nghiệp vụ** đạt được trong một deadline hợp lý.

```text
                 Một thao tác nghiệp vụ
                          |
         +----------------+------------------+
         |                |                  |
         v                v                  v
   Unique index       TTL index        Background worker
         |                |                  |
   Ghi vi phạm?      expiresAt đã qua?    Có job/event?
         |                |                  |
   Server từ chối     TTL monitor         Worker chạy
   ngay khi write     kiểm tra định kỳ     khi được schedule
         |                |                  |
    Assert lỗi          Poll đến khi        Poll trạng thái
    hoặc thành công     bị xóa thật         output ổn định
```

> **Nguyên tắc trung tâm:** test một **ràng buộc đồng bộ** phải kiểm tra kết quả của thao tác; test một **hệ thống bất đồng bộ** phải kiểm tra sự hội tụ về trạng thái mong đợi trong một khoảng thời gian, không đoán chính xác lúc nào nó xảy ra.

---

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

- Tạo và kiểm thử single-field, compound, sparse, partial unique indexes.
- Xác minh lỗi `E11000` khi insert, update, upsert và concurrent writes.
- Phân biệt unique index với kiểm tra trùng bằng query ở application.
- Kiểm thử semantics của `null`, trường thiếu, collation và phạm vi tenant.
- Hiểu TTL `expireAfterSeconds`, kiểu BSON Date và clock UTC.
- Viết integration test TTL chống flakiness bằng polling với deadline.
- Biết tại sao `Thread.sleep(1000)` không chứng minh TTL hỏng.
- Tổ chức MongoDB Testcontainers/JUnit integration tests.
- Kiểm thử eventual consistency, retry, idempotency, worker và trạng thái “không được xảy ra”.
- Phân tách unit, integration và end-to-end tests cho những chức năng này.
- Chẩn đoán test thất bại do lỗi logic, hạ tầng, sai thời gian hoặc scheduling.

---

## 3. Ba nhóm hành vi cần kiểm thử

| Nhóm | Ví dụ | Cách xác minh |
| --- | --- | --- |
| Ràng buộc ngay khi ghi | Unique index, schema validation | Assert write thành công hoặc trả lỗi cụ thể |
| Bất đồng bộ do MongoDB | TTL deletion, secondary replication, Search indexing | Poll điều kiện quan sát ở đúng nguồn đọc |
| Bất đồng bộ do ứng dụng | Outbox consumer, background export, retry queue | Poll trạng thái nghiệp vụ, timeout và idempotency |

### 3.1. Không nhầm “lệnh được nhận” với “hệ thống đã hội tụ”

Một `insertOne` thành công không chứng minh message đã xuất hiện trong Kafka. Một tài liệu có `expiresAt` trong quá khứ không chứng minh TTL monitor đã xóa xong. Một `createIndex` chưa trả thành công không chứng minh unique constraint đã sẵn sàng.

### 3.2. Eventual consistency có giới hạn

“Eventual” không có nghĩa test chờ vô hạn. Test phải có:

- Một **điều kiện** quan sát được.
- Một **deadline** đủ lớn theo môi trường và SLA.
- Chu kỳ poll hợp lý.
- Dữ liệu/namespace cô lập.
- Thông tin chẩn đoán khi hết thời gian.
- Cleanup tài nguyên ngay cả khi test thất bại.

---

## 4. Mô hình dữ liệu ví dụ

Sử dụng một collection `accounts`:

```javascript
{
  _id: ObjectId("691800000000000000000001"),
  tenantId: "tenant-A",
  emailNormalized: "user@example.com",
  active: true,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Một collection `verificationCodes`:

```javascript
{
  _id: ObjectId("691800000000000000000002"),
  accountId: ObjectId("691800000000000000000001"),
  codeHash: "hash-not-raw-secret",
  expiresAt: ISODate("2026-11-14T08:05:00Z")
}
```

Và một collection `outbox`:

```javascript
{
  _id: "event-1001",
  aggregateId: "order-1001",
  eventType: "ORDER_CREATED",
  state: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Các ví dụ dùng database **test riêng**. Không chạy `drop()`, tạo/xóa indexes hoặc chèn dữ liệu giả vào production.

---

# PHẦN I — KIỂM THỬ UNIQUE INDEX

## 5. Unique index bảo đảm điều gì?

Unique index đặt constraint tại tầng MongoDB: **không cho hai documents khác nhau có cùng một index key** theo index specification, collation và filter tương ứng.

Ví dụ:

```javascript
db.accounts.createIndex(
  { emailNormalized: 1 },
  { unique: true, name: "uq_email_normalized" }
);
```

Nếu đã có:

```javascript
{
  _id: 1,
  emailNormalized: "alice@example.com"
}
```

thì insert document khác:

```javascript
{
  _id: 2,
  emailNormalized: "alice@example.com"
}
```

bị từ chối bằng duplicate-key error.

### 5.1. Unique index khác `findOne()` trước khi insert

Đoạn code:

```java
if (accounts.find(eq("emailNormalized", email)).first()
        == null) {
    accounts.insertOne(document);
}
```

**Không bảo đảm uniqueness trong concurrency**. Hai requests có thể cùng đọc “chưa có” rồi cùng insert.

```text
Request A                  Request B
---------                  ---------
find -> no email           find -> no email
       |                          |
       +-----------+--------------+
                   |
             both insert
```

Với unique index, một thao tác được chấp nhận và thao tác trùng bị từ chối theo ràng buộc được server thực thi.

### 5.2. Test không chỉ kiểm tra dữ liệu sau cùng

Nên kiểm tra **cả hai**:

1. Write đầu tiên được chấp nhận.
2. Write thứ hai ném đúng duplicate-key error.
3. Collection còn đúng số document và dữ liệu dự kiến.

---

## 6. Mongosh test: duplicate insert

```javascript
use mongo_index_test;

db.accounts.drop();

db.accounts.createIndex(
  { emailNormalized: 1 },
  { unique: true, name: "uq_email_normalized" }
);

db.accounts.insertOne({
  _id: "acct-1",
  emailNormalized: "alice@example.com"
});

db.accounts.insertOne({
  _id: "acct-2",
  emailNormalized: "alice@example.com"
});
```

Lệnh insert thứ hai thất bại với lỗi tương tự:

```text
E11000 duplicate key error
```

Mã lỗi duplicate-key thông dụng là **11000**. Không cần so sánh toàn bộ message nguyên văn vì message có thể thay đổi theo MongoDB version, driver và cách format field.

### 6.1. Cần phân biệt duplicate `_id` với duplicate field

Nếu test vô ý dùng cùng `_id`, hệ thống có thể báo lỗi index `_id_` chứ không phải unique `emailNormalized`.

**Đúng cách:** hai documents có **hai `_id` khác nhau**, nhưng cùng giá trị `emailNormalized`.

---

## 7. JUnit 5: assert lỗi unique bằng Java Sync Driver

Với `org.mongodb:mongodb-driver-sync` và JUnit 5:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

public class UniqueIndexTest {

    private MongoCollection<Document> accounts;

    @Test
    void duplicateEmailIsRejected() {
        accounts.createIndex(
            Indexes.ascending("emailNormalized"),
            new IndexOptions()
                .unique(true)
                .name("uq_email_normalized")
        );

        accounts.insertOne(
            new Document("_id", "acct-1")
                .append("emailNormalized",
                        "alice@example.com")
        );

        MongoWriteException error =
            assertThrows(
                MongoWriteException.class,
                () -> accounts.insertOne(
                    new Document("_id", "acct-2")
                        .append("emailNormalized",
                                "alice@example.com")
                )
            );

        assertEquals(11000, error.getError().getCode());
        assertEquals(
            1,
            accounts.countDocuments()
        );
    }
}
```

`accounts` cần được khởi tạo bằng fixture của test class; đoạn trên minh họa riêng test method. Phần sau trình bày Testcontainers/JUnit setup đầy đủ.

### 7.1. Vì sao không assert message chính xác?

Không nên:

```java
assertEquals(
    "E11000 duplicate key error collection: ...",
    error.getMessage()
);
```

Thông điệp chứa namespace, index name, key và format phụ thuộc release. Ưu tiên:

- Error category/type.
- Error code 11000.
- Collection state.
- Index metadata nếu cần chứng minh ràng buộc nào gây lỗi.

### 7.2. Một số thao tác trả exception class khác

- `insertOne()` duplicate thường trả `MongoWriteException`.
- `bulkWrite()` có thể trả `MongoBulkWriteException`.
- `createIndex()` thất bại trên dữ liệu trùng có thể trả `MongoCommandException` hoặc subclass theo driver.
- Không gom mọi thao tác vào `assertThrows(MongoWriteException.class, ...)` nếu API không bảo đảm cùng exception type.

---

## 8. Kiểm thử unique khi UPDATE

Unique index kiểm tra cả inserts **và updates**.

Đã có:

```javascript
{ _id: "A", emailNormalized: "a@example.com" }
{ _id: "B", emailNormalized: "b@example.com" }
```

Thao tác:

```javascript
db.accounts.updateOne(
  { _id: "B" },
  { $set: { emailNormalized: "a@example.com" } }
);
```

phải bị từ chối khi unique index đang tồn tại.

### 8.1. Java example

```java
accounts.createIndex(
    Indexes.ascending("emailNormalized"),
    new IndexOptions().unique(true)
);

accounts.insertOne(
    new Document("_id", "A")
        .append("emailNormalized", "a@example.com")
);

accounts.insertOne(
    new Document("_id", "B")
        .append("emailNormalized", "b@example.com")
);

MongoWriteException error = assertThrows(
    MongoWriteException.class,
    () -> accounts.updateOne(
        Filters.eq("_id", "B"),
        Updates.set("emailNormalized",
                    "a@example.com")
    )
);

assertEquals(11000, error.getError().getCode());

Document unchanged = accounts.find(
    Filters.eq("_id", "B")
).first();

assertEquals(
    "b@example.com",
    unchanged.getString("emailNormalized")
);
```

### 8.2. Vì sao cần assert document không đổi?

Bài test phải chứng minh update bị từ chối mà không thay đổi field đang kiểm tra. Chỉ assert error có thể bỏ qua sự sai khác trong dữ liệu do test setup.

---

## 9. Unique compound index: duy nhất theo tenant

Trong SaaS đa tenant, email có thể phải duy nhất **trong một tenant**, không phải toàn hệ thống.

Index:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true, name: "uq_tenant_email" }
);
```

Bảng kỳ vọng:

| Document | tenantId | emailNormalized | Kết quả |
| --- | --- | --- | --- |
| A | T1 | a@example.com | Được ghi |
| B | T1 | a@example.com | Từ chối |
| C | T2 | a@example.com | Được ghi |
| D | T1 | b@example.com | Được ghi |

### 9.1. Java test

```java
accounts.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId"),
        Indexes.ascending("emailNormalized")
    ),
    new IndexOptions().unique(true)
);

accounts.insertOne(
    new Document("_id", "A")
        .append("tenantId", "T1")
        .append("emailNormalized", "a@example.com")
);

assertThrows(
    MongoWriteException.class,
    () -> accounts.insertOne(
        new Document("_id", "B")
            .append("tenantId", "T1")
            .append("emailNormalized", "a@example.com")
    )
);

assertDoesNotThrow(
    () -> accounts.insertOne(
        new Document("_id", "C")
            .append("tenantId", "T2")
            .append("emailNormalized", "a@example.com")
    )
);
```

### 9.2. Điều gì cần kiểm tra thêm?

- Tenant ID không thiếu/null nếu domain yêu cầu.
- Tạo index trước khi ghi dữ liệu.
- Các query tenant isolation không bỏ `tenantId`.
- Nếu collection sharded, unique index phải thỏa sharding restrictions; xem phần chuyên biệt.

---

## 10. Unique single-field và null/missing

Đây là case rất dễ viết test sai.

Với **non-sparse single-field unique index**:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

Tài liệu MongoDB quy định một document có trường `email` **thiếu** hoặc `email: null` tạo index key null. Vì uniqueness, không thể có nhiều documents cùng key null trên index đó.

```javascript
db.users.insertOne({ _id: 1 });
// Thành công nếu chưa có null-key nào.

db.users.insertOne({ _id: 2 });
// Duplicate key, vì email cũng missing -> null-key.
```

### 10.1. Test phải bao gồm trường thiếu

Không chỉ test hai strings trùng nhau. Nếu API có optional email, hãy xác định domain cho phép:

- Nhiều người chưa cung cấp email?
- Một document có `email: null` là hợp lệ?
- Nếu có, index nên sparse hay partial?
- Cần phân biệt missing với explicit null không?

### 10.2. Compound unique null semantics

Với compound index `{ tenantId: 1, email: 1 }`, constraint áp dụng trên **tổ hợp key**.

Hai documents:

```javascript
{ tenantId: "T1", email: null }
{ tenantId: "T2", email: null }
```

có tổ hợp khác nên có thể cùng tồn tại.

Nhưng hai documents cùng `tenantId: "T1"` và `email` missing/null có thể xung đột.

Không suy luận compound unique chỉ cho phép một document thiếu email trên **toàn collection**: phải xem cả index tuple.

---

## 11. Unique sparse index

Sparse index bỏ qua documents **thiếu field** được index.

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "uq_optional_email_sparse"
  }
);
```

Kỳ vọng:

```javascript
db.users.insertOne({ _id: 1 });
db.users.insertOne({ _id: 2 });
// Cả hai không có email: có thể thành công.

db.users.insertOne({ _id: 3, email: null });
// Có entry null và có thể thành công.

db.users.insertOne({ _id: 4, email: null });
// Trùng null-key -> từ chối.
```

### 11.1. Sparse không có nghĩa bỏ qua null

Một field **tồn tại nhưng có giá trị null** vẫn được sparse index lập chỉ mục. Vì vậy sparse unique cho phép nhiều documents **thiếu** email, nhưng không mặc nhiên cho phép nhiều explicit null.

### 11.2. Compound sparse behavior phức tạp hơn

Sparse compound index có quy tắc chọn document được index phụ thuộc các key types. Không áp một cách máy móc logic của single-field sparse sang mọi compound index.

---

## 12. Unique partial index: kiểm soát tập tài liệu chịu constraint

Partial index chỉ index documents match `partialFilterExpression`.

Ví dụ chỉ áp unique cho `email` kiểu string:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uq_email_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Nhờ vậy:

- Hai documents thiếu `email` được phép.
- Hai documents có `email: null` không nằm trong filter này.
- Hai documents có cùng email **string** bị từ chối.

### 12.1. Vì sao dùng `$type: "string"`?

Nó tránh hiểu nhầm giữa:

- `email` missing.
- `email: null`.
- `email` tồn tại dưới dạng string.

Ứng dụng vẫn nên có schema validation để tránh email là number/array nếu domain không cho phép.

### 12.2. Java tạo partial unique index

```java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

IndexOptions options = new IndexOptions()
    .unique(true)
    .name("uq_email_string")
    .partialFilterExpression(
        new Document(
            "email",
            new Document("$type", "string")
        )
    );

users.createIndex(
    Indexes.ascending("email"),
    options
);
```

### 12.3. Nên kiểm thử đủ ba nhóm

1. Document nằm trong filter và key chưa trùng → thành công.
2. Document nằm trong filter và key trùng → duplicate-key.
3. Document không nằm trong filter → không chịu constraint này.

---

## 13. Soft delete và unique partial

Nếu tài khoản bị xóa mềm nhưng email được phép tái sử dụng, có thể chọn field `active`:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  {
    unique: true,
    name: "uq_active_tenant_email",
    partialFilterExpression: { active: true }
  }
);
```

Bài test:

```text
1. Insert active=true, T1, a@example.com       -> SUCCESS
2. Insert active=true, T1, a@example.com       -> DUPLICATE
3. Change first account active=false           -> SUCCESS
4. Insert new active=true, T1, a@example.com   -> SUCCESS
5. Change old account active=true              -> DUPLICATE
```

### 13.1. Test trạng thái chuyển tiếp

Một ràng buộc partial unique chỉ có hiệu lực với các documents **đang match filter**. Vì vậy cần test cả update làm document **đi vào** tập filter, không chỉ inserts.

### 13.2. Domain phải định nghĩa trường active

Document thiếu `active` sẽ không match `{active: true}`. Nếu business mặc định “thiếu active nghĩa đang hoạt động” nhưng index không hiểu quy ước đó, uniqueness có thể bị lọt. Dùng schema validation hoặc thiết kế field bắt buộc.

---

## 14. Collation và kiểm thử không phân biệt hoa/thường

Mặc định, unique index với collation đơn giản có thể xem:

```text
Alice@Example.com
alice@example.com
```

là hai string khác nhau.

Nếu domain cần case-insensitive equality, hãy tạo unique index với collation phù hợp:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uq_email_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

`strength: 2` là một cấu hình collation thường dùng cho phân biệt dấu nhưng không phân biệt chữ hoa/chữ thường theo locale tương ứng.

### 14.1. Test

```javascript
db.users.insertOne({
  _id: "U1",
  email: "Alice@example.com"
});

db.users.insertOne({
  _id: "U2",
  email: "alice@example.com"
});
// Có thể nhận E11000 do cùng collation key.
```

### 14.2. Không biến quy tắc email thành công thức đơn giản

Các chính sách canonicalization email có thể khác giữa domain/provider. Không tự áp một phương pháp lower-case hoặc strip dấu/chấm trên mọi địa chỉ nếu hệ thống chưa có business policy.

### 14.3. Query collation và index collation

Một query muốn tận dụng index có collation có thể cần chỉ định collation tương thích, trừ khi collection default đã trùng. Test cả uniqueness lẫn kế hoạch query/index nếu endpoint phụ thuộc performance.

---

## 15. Unique multikey: lặp trong một document khác lặp giữa documents

Khi indexed field là array, MongoDB có thể tạo **multikey index**.

Với unique multikey index, constraint áp dụng trên những index keys **giữa các documents**. Một document có các giá trị array lặp lại không tự động vi phạm chỉ vì các entries trong cùng document trùng.

Ví dụ:

```javascript
db.groups.createIndex(
  { aliases: 1 },
  { unique: true }
);
```

Một document:

```javascript
{
  _id: "G1",
  aliases: ["red", "red", "blue"]
}
```

có thể được chấp nhận; MongoDB không thêm duplicate index entry cho cùng key bên trong document. Nhưng một document khác có alias `"red"` sẽ vi phạm.

### 15.1. Đừng dùng unique multikey thay application validation

Nếu business yêu cầu không cho trùng phần tử **trong cùng array**, cần schema/application validation riêng. Unique multikey không bảo đảm bất biến đó.

### 15.2. Compound multikey có hạn chế

Một compound multikey index không cho mỗi document có nhiều hơn một indexed field là array theo các ràng buộc của MongoDB. Test riêng cho schema nhiều arrays.

---

## 16. Index build: test điều kiện trước khi bắt đầu ghi

Nếu collection đã có duplicate data:

```javascript
db.users.insertMany([
  { _id: "U1", email: "a@example.com" },
  { _id: "U2", email: "a@example.com" }
]);
```

lệnh:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

có thể thất bại khi MongoDB phát hiện duplicate key trong quá trình index build/commit.

### 16.1. Không chỉ test inserts sau khi index tạo

Cần hai tình huống riêng:

1. Collection rỗng/không trùng → build thành công → constraint có hiệu lực.
2. Collection đã có duplicates → index build thất bại → không giả định index đã tồn tại.

### 16.2. Java test ý tưởng

```java
users.insertMany(List.of(
    new Document("_id", "U1").append("email", "a@x.test"),
    new Document("_id", "U2").append("email", "a@x.test")
));

assertThrows(
    com.mongodb.MongoCommandException.class,
    () -> users.createIndex(
        Indexes.ascending("email"),
        new IndexOptions().unique(true)
    )
);
```

Driver version/API có thể sử dụng subtype của `MongoCommandException`. Khi cần test ổn định hơn, hãy xác minh **error code 11000 và index không ở trạng thái ready** thay vì đối chiếu nguyên văn message.

### 16.3. Replica set index builds có commit quorum

Index builds hiện đại trên replica set có cơ chế commit quorum. Đừng chạy hai write requests dựa vào giả định “đã bắt đầu createIndex thì unique constraint hoàn tất”. Chỉ bắt đầu test writes sau khi `createIndex` trả thành công hoặc fixture đã xác nhận index ready.

---

## 17. Kiểm thử concurrent inserts: chính xác một winner

Đây là test rất quan trọng vì `findOne()`-then-`insertOne()` dễ có race condition.

### 17.1. Mục tiêu

Hai threads cùng cố insert một `emailNormalized` trong cùng tenant:

- **Một thao tác thành công.**
- **Một thao tác thất bại duplicate key (11000).**
- Collection cuối cùng có đúng **một** document với key đó.
- Không giả định thread A luôn thắng.

### 17.2. Java/JUnit 5 code

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

public class ConcurrentUniqueTest {

    private MongoCollection<Document> accounts;

    @Test
    void concurrentCreateExactlyOneWinner() throws Exception {
        accounts.createIndex(
            Indexes.compoundIndex(
                Indexes.ascending("tenantId"),
                Indexes.ascending("emailNormalized")
            ),
            new IndexOptions().unique(true)
        );

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        ExecutorService pool =
            Executors.newFixedThreadPool(2);

        try {
            Callable<Boolean> write = () -> {
                ready.countDown();

                if (!start.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Start barrier timed out"
                    );
                }

                String id = java.util.UUID.randomUUID()
                    .toString();

                try {
                    accounts.insertOne(
                        new Document("_id", id)
                            .append("tenantId", "T1")
                            .append("emailNormalized",
                                    "race@example.com")
                    );
                    return true;
                } catch (MongoWriteException e) {
                    if (e.getError().getCode() == 11000) {
                        return false;
                    }
                    throw e;
                }
            };

            Future<Boolean> first = pool.submit(write);
            Future<Boolean> second = pool.submit(write);

            assertTrue(
                ready.await(10, TimeUnit.SECONDS),
                "Workers did not become ready"
            );

            start.countDown();

            boolean a = first.get(20, TimeUnit.SECONDS);
            boolean b = second.get(20, TimeUnit.SECONDS);

            assertNotEquals(
                a, b,
                "Exactly one write must succeed"
            );

            assertEquals(
                1,
                accounts.countDocuments(
                    new Document("tenantId", "T1")
                        .append(
                            "emailNormalized",
                            "race@example.com"
                        )
                )
            );
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

### 17.3. Lưu ý về determinism

`CountDownLatch` giúp hai threads đến gần một ranh giới bắt đầu giống nhau, **không bảo đảm** server nhận hai packets đúng cùng nanosecond. Điều cần test là invariant luôn đúng bất kể interleaving.

### 17.4. Không assert `first == true`

Thread scheduling, network và server execution order không được hứa hẹn. Test winner theo danh tính thread là flaky.

---

## 18. Bulk writes và duplicate key

Với bulk insert:

```java
List<Document> data = List.of(
    new Document("_id", "A").append("email", "a@example.com"),
    new Document("_id", "B").append("email", "a@example.com"),
    new Document("_id", "C").append("email", "c@example.com")
);
```

Nếu có unique index trên email:

- `ordered` có thể dừng xử lý các operations tiếp theo khi lỗi.
- `unordered` có thể tiếp tục các operations khác.
- Một bulk operation có thể thành công **một phần**.
- Exception có thể là `MongoBulkWriteException`, không chỉ `MongoWriteException`.

### 18.1. Test cần xác minh state cuối cùng

Không assert “bulk ném exception nên không có bản ghi nào được ghi”. Hãy kiểm tra:

- Những documents được ghi thành công.
- Duplicate record bị chặn.
- Số records/keys.
- Error code trong `getWriteErrors()`.
- Ordered/unordered semantics theo driver/server version.

### 18.2. Retry sau bulk lỗi

Nếu retry cả batch và không có idempotency key, có thể gặp duplicate do records đã được ghi thành công trước đó. Test retry logic nên dùng `_id`/business key ổn định và kiểm tra trạng thái cuối.

---

## 19. Upsert và unique index

Khi hai requests đồng thời chạy `updateOne(..., upsert=true)` cho cùng business key, unique index vẫn rất quan trọng.

Ví dụ:

```java
accounts.updateOne(
    Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.eq("externalId", "E100")
    ),
    Updates.setOnInsert("status", "NEW"),
    new UpdateOptions().upsert(true)
);
```

Với compound unique index `{tenantId:1, externalId:1}`, các requests cạnh tranh không thể tạo hai documents có cùng unique key.

### 19.1. Nhưng không phải mọi upsert race luôn tự thành công

Tùy filter/update shape và retry behavior, một trong các operations có thể trả duplicate-key khi cạnh tranh. Ứng dụng cần policy phù hợp (đọc lại trạng thái, retry có điều kiện, thông báo conflict). Không giả định tất cả upserts đồng thời đều thành công theo cùng một đường.

### 19.2. Test cần khẳng định domain invariant

- Không quá một document cho business key.
- Nếu gọi lại operation idempotent, trạng thái không bị duplicate.
- Không có hai side effects (email, payment, message).
- Exception/retry result được xử lý đúng.

---

## 20. Sharded clusters và unique index

Trong sharded collection, unique index có restrictions.

Điểm cốt lõi: ràng buộc unique giữa shards chỉ được MongoDB hỗ trợ khi unique index là shard key hoặc **có shard key làm prefix**, theo quy định về index type/topology. Hashed index không hỗ trợ `unique: true`.

Ví dụ sharded theo `{tenantId:1}` thì unique `{tenantId:1, email:1}` phù hợp về prefix, nhưng các constraints khác như shard key và index options vẫn phải kiểm tra.

### 20.1. Test trên replica set không chứng minh sharded compatibility

Nếu production chạy sharded cluster, một test MongoDB standalone/replica set chỉ chứng minh logic uniqueness trong topology đó, không chứng minh có thể tạo chính index trên sharded collection.

### 20.2. Chọn test layer

- Unit: domain key composition.
- Integration: unique enforcement trên replica set.
- Environment compatibility: shard key/index restrictions trên sharded staging.
- E2E: các writers từ nhiều mongos không tạo duplicate.

### 20.3. Đừng định nghĩa unique trên hashed index

Nếu cần sharding theo hash và uniqueness business key, phải đọc chính sách MongoDB và thiết kế shard key/index phù hợp; không cố `unique:true` trên hashed index.

---

# PHẦN II — KIỂM THỬ TTL INDEX

## 21. TTL index là gì?

**Time-To-Live (TTL)** index cho phép MongoDB tự động xóa documents khi đến hạn, thường dùng cho:

- Session records.
- One-time verification tokens.
- Temporary logs.
- Dữ liệu telemetry ngắn hạn.
- Retry metadata có hạn lưu.
- Cache documents có thể tái tạo.

Ví dụ:

```javascript
db.verificationCodes.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expires_at"
  }
);
```

Với `expireAfterSeconds: 0`, document đủ điều kiện hết hạn khi thời điểm trong field `expiresAt` đã đến, theo thời gian server và semantics TTL.

Ví dụ khác:

```javascript
db.auditEvents.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
```

Document đủ điều kiện sau khoảng một ngày kể từ `createdAt`.

### 21.1. TTL là physical cleanup

Nó xóa **cả document** khỏi collection, không chỉ loại một field hay đổi `active:false`.

### 21.2. TTL không phải bộ định thời chính xác tới mili-giây

TTL monitor chạy nền và kiểm tra theo chu kỳ. Đến hạn **không đồng nghĩa đã bị xóa ngay**.

---

## 22. TTL dùng BSON Date, không phải string ngày tháng

Ví dụ đúng:

```javascript
db.verificationCodes.insertOne({
  _id: "V1",
  expiresAt: ISODate("2026-11-14T08:00:00Z")
});
```

Ví dụ không đúng cho TTL field:

```javascript
db.verificationCodes.insertOne({
  _id: "V2",
  expiresAt: "2026-11-14T08:00:00Z"
});
```

Ở ví dụ thứ hai, `expiresAt` là **string**, không phải BSON Date. TTL index không tự parse string ISO thành Date để xóa.

### 22.1. Test BSON type

```javascript
db.verificationCodes.find({
  _id: "V1",
  expiresAt: { $type: "date" }
});
```

Hoặc ở Java:

```java
Date expiresAt =
    document.getDate("expiresAt");
```

Nếu dữ liệu có thể là null/thiếu/sai kiểu, test cả validation và TTL behavior.

### 22.2. TTL với array

Nếu indexed field là array có nhiều BSON Date, MongoDB dùng **giá trị Date sớm nhất** trong array để tính hết hạn. Đây là edge case quan trọng, không áp logic “lấy ngày muộn nhất” theo suy luận.

### 22.3. Field missing/null

Nếu document thiếu indexed field hoặc field không chứa Date, TTL index không có đủ giá trị ngày phù hợp để expire document. Điều này dễ tạo “document tồn tại mãi” nếu ứng dụng vô tình ghi sai kiểu.

---

## 23. TTL monitor có tính bất đồng bộ

Theo tài liệu MongoDB:

- TTL monitor chạy background.
- Thông thường nó kiểm tra theo chu kỳ **khoảng 60 giây**.
- Delete có thể xảy ra trong khoảng 0–60 giây sau khi document đủ điều kiện và monitor hoạt động.
- Khi backlog, tải lớn, failover hoặc resource pressure, xóa có thể chậm hơn chu kỳ này.
- Trên replica set, **primary** thực hiện TTL deletes; secondaries replicate operations xóa.
- Sau khi TTL index mới được tạo xong, monitor mới có thể xử lý các tài liệu đã hết hạn trong collection.

### 23.1. Timeline minh họa

```text
12:00:00  Document expiresAt
12:00:01  Application find() có thể vẫn đọc thấy document
12:00:30  TTL monitor chưa chạy lượt mới
12:01:00  TTL monitor quét và bắt đầu delete
12:01:02  Document có thể đã biến mất
```

Không có cam kết thời điểm chính xác cho từng document.

### 23.2. Không test bằng sleep cứng

Không tốt:

```java
Thread.sleep(1500);
assertNull(codes.find(eq("_id", id)).first());
```

Dù code đúng, TTL monitor có thể chưa chạy; test fail ngẫu nhiên hoặc fail liên tục trên máy nhanh/chậm.

### 23.3. Dùng polling có deadline

```text
insert expired document
       |
       v
assert exists immediately
       |
       v
poll every 1 second
       |
       +--> deleted? PASS
       |
       +--> deadline? FAIL with diagnostics
```

Một deadline integration test thường cần dài hơn chu kỳ TTL mặc định, ví dụ 2–3 phút; đây là **ngưỡng test theo môi trường**, không phải SLA đảm bảo MongoDB sẽ xóa trong đúng 3 phút.

---

## 24. `expireAfterSeconds`: tính thời điểm expire

Với TTL index:

```javascript
db.events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 3600 }
);
```

Document:

```javascript
{
  _id: "E100",
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

sẽ đủ điều kiện hết hạn sau khoảng:

```text
createdAt + 3600 seconds
= 2026-11-14T11:00:00Z
```

Nhưng **physical deletion** có thể diễn ra sau đó.

### 24.1. Dùng `expiresAt` và TTL 0

Khi từng document có thời hạn khác nhau:

```javascript
db.codes.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

Mỗi document tự mang thời điểm expire riêng. Đây là mô hình thường thích hợp cho OTP/password reset tokens.

### 24.2. Không nhầm time zone

BSON Date lưu mốc thời gian UTC. Application nên dùng `Instant` hoặc chuẩn mốc UTC, không tự cộng 7 giờ vào Java `Date`.

### 24.3. Chọn Date đã hết hạn rõ ràng cho test

Để không phải chờ thời gian nghiệp vụ:

```java
Date expired = Date.from(
    Instant.now().minusSeconds(300)
);
```

Dùng Date của 5 phút trước giúp xác định document đã đủ điều kiện ngay khi inserted; test chỉ cần chờ monitor chạy.

---

## 25. Integration test TTL bằng Awaitility

Đoạn code giả định có dependencies:

- Java MongoDB Sync Driver.
- JUnit 5.
- Awaitility.
- MongoDB instance thật từ Testcontainers hoặc môi trường test cô lập.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import static com.mongodb.client.model.Filters.eq;
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

public class TtlIndexTest {

    private MongoCollection<Document> codes;

    @Test
    void expiredDocumentIsEventuallyDeleted() {
        codes.createIndex(
            Indexes.ascending("expiresAt"),
            new IndexOptions()
                .expireAfter(0L, java.util.concurrent.TimeUnit.SECONDS)
                .name("ttl_expires_at")
        );

        String id = "expired-" + java.util.UUID.randomUUID();

        codes.insertOne(
            new Document("_id", id)
                .append(
                    "expiresAt",
                    Date.from(Instant.now().minusSeconds(300))
                )
        );

        // Insert đã acknowledged; tài liệu vừa tồn tại.
        // Không ép TTL phải chưa kịp xóa tại một mốc rất ngắn.
        await()
            .atMost(Duration.ofMinutes(3))
            .pollInterval(Duration.ofSeconds(1))
            .until(
                () -> codes.find(eq("_id", id)).first() == null
            );
    }
}
```

**API chú ý:** Các phiên bản Java Sync Driver có overload `IndexOptions.expireAfter(Long, TimeUnit)` hoặc API thời lượng mới hơn. Đối chiếu Javadocs của driver dependency thực tế; nếu không có overload đó, có thể dùng `.expireAfter(0L, TimeUnit.SECONDS)` trên dòng hỗ trợ hoặc dùng `new IndexOptions().expireAfter(0L, TimeUnit.SECONDS)` tương đương. Khi viết ở Java driver 5.x, đây là hình thức điển hình.

### 25.1. Tại sao không assert document “phải tồn tại 100 ms sau insert”?

TTL monitor có thể đang chạy ngay lúc insert; expired document có thể bị xóa rất nhanh. Một assertion bắt buộc “còn tồn tại” sau insert có thể flaky. Nếu test cần xác nhận insert acknowledged, hãy kiểm tra kết quả insert hoặc kiểm tra data trong bước khác với TTL monitor được kiểm soát.

### 25.2. Test này không chứng minh deadline SLA 3 phút

Nó chỉ chứng minh trong môi trường đang chạy, TTL deletion diễn ra trong khoảng time budget của test. Nếu fail, phải xem TTL monitor/primary/IOPS, không tự kết luận sản phẩm MongoDB hứa xóa đúng hạn 3 phút.

---

## 26. Một mô hình TTL test rõ ràng hơn: expired và non-expired

Trong cùng collection test, tạo hai documents:

```java
Date past = Date.from(
    Instant.now().minusSeconds(600)
);

Date future = Date.from(
    Instant.now().plusSeconds(3600)
);

codes.insertMany(List.of(
    new Document("_id", "expired")
        .append("expiresAt", past),
    new Document("_id", "fresh")
        .append("expiresAt", future)
));
```

Sau đó:

1. Poll đến khi `"expired"` bị xóa.
2. Assert `"fresh"` vẫn tồn tại.
3. Kiểm tra TTL index configuration là `expireAfterSeconds:0`.

Ví dụ:

```java
await()
    .atMost(Duration.ofMinutes(3))
    .pollInterval(Duration.ofSeconds(1))
    .until(
        () -> codes.find(eq("_id", "expired")).first() == null
    );

assertNotNull(
    codes.find(eq("_id", "fresh")).first()
);
```

### 26.1. Tại sao future phải đủ xa?

Nếu chọn `future = now + 1 second`, đến lúc monitor chạy document cũng đã hết hạn. Test “fresh chưa bị xóa” sẽ sai do setup, không phải do MongoDB.

### 26.2. Không chứng minh “never” bằng một lần query

Assertion future tồn tại sau 90 giây chứng minh nó còn ở **mốc quan sát**, không chứng minh không bao giờ bị xóa trước khi hết hạn. Với TTL Date đủ xa, bài test kiểm tra nhóm nghiệp vụ dự kiến trong khoảng chạy.

---

## 27. Kiểm thử TTL index có tồn tại và option đúng

Một test TTL chỉ poll document biến mất có thể vô tình thành công nếu document bị code khác xóa. Vì vậy nên kiểm tra fixture:

```javascript
db.verificationCodes.getIndexes();
```

Kỳ vọng index:

```javascript
{
  key: { expiresAt: 1 },
  name: "ttl_expires_at",
  expireAfterSeconds: 0
}
```

Đây là một phần metadata minh họa; output thực còn các fields khác.

Java:

```java
boolean found = false;

for (Document index : codes.listIndexes()) {
    if ("ttl_expires_at".equals(index.getString("name"))) {
        Number ttl = (Number) index.get("expireAfterSeconds");
        assertNotNull(ttl);
        assertEquals(0L, ttl.longValue());
        found = true;
    }
}

assertTrue(found, "Expected TTL index was not created");
```

### 27.1. Verify index creation trước test deletion

Nếu `createIndex()` thất bại mà test âm thầm bỏ qua lỗi, polling sẽ timeout nhưng nguyên nhân thực là fixture setup. Tách báo lỗi index setup và TTL behavior giúp chẩn đoán rõ.

---

## 28. TTL index restrictions quan trọng

Các quy tắc tiêu biểu trong MongoDB Manual:

- TTL index thông thường là **single-field index**.
- Compound index không hỗ trợ TTL theo cách thông thường; option `expireAfterSeconds` có thể bị bỏ qua trên compound specification.
- `_id` không được dùng làm TTL index key.
- TTL cần field Date hoặc array chứa Date.
- Missing hoặc field không có Date sẽ không expire.
- Khi giảm TTL duration trên collection lớn, nhiều documents có thể trở thành eligible cùng lúc và tạo delete load lớn.
- Với time-series collections có các quy tắc riêng về bucket và partial TTL theo phiên bản.

### 28.1. Test ngăn sai cấu hình

Nếu application cần TTL trên `expiresAt`, test nên xác minh đúng index key và option; không chỉ kiểm tra collection có “một index bất kỳ”.

### 28.2. Không coi `expireAfterSeconds` là milliseconds

```javascript
{ expireAfterSeconds: 60 }
```

nghĩa là **60 giây**, không phải 60 mili-giây. Trong Java, hãy kiểm tra `TimeUnit`/duration overload đang dùng.

---

## 29. TTL trên time-series collection

Time-series collections có semantics riêng:

- Có thể cấu hình `expireAfterSeconds` tại collection.
- TTL xử lý **buckets** khi các measurements trong bucket đủ điều kiện hết hạn.
- Bucket retention có thể làm một số measurements tồn tại lâu hơn ngưỡng được tính cho từng measurement.
- Từ MongoDB 7.0, có **partial TTL index** dựa trên `metaField` của time-series collection theo các điều kiện được tài liệu hỗ trợ.
- Không dùng cùng giả định timing của ordinary collection để assert time-series document biến mất đúng mốc.

### 29.1. Ví dụ bucket behavior

```text
Bucket spans time 10:00 to 10:59
expireAfterSeconds = 300

Một measurement lúc 10:00 có thể không bị
xóa riêng ngay 10:05 nếu bucket vẫn chứa
measurement mới hơn chưa expire.
```

### 29.2. Cần test ở cấp nào?

- Index/collection metadata.
- Timestamp types và granularity.
- Bucket aging qua một khoảng thời gian phù hợp.
- Eventual disappearance khi toàn bucket eligible.
- Behavior theo MongoDB version thực tế.

### 29.3. Tránh time-series TTL test quá ngắn

Một test chờ 10–20 giây trên time-series có bucket span một giờ có thể fail dù hệ thống đúng. Thiết kế test fixtures trong quá khứ đủ xa và đọc tài liệu bucket max span theo granularity.

---

## 30. TTL trên replica set: primary mới thực hiện delete

Trên replica set:

```text
MongoDB PRIMARY
    |
    | TTL monitor identifies expired docs
    v
DELETE operation
    |
    | replication/oplog
    v
MongoDB SECONDARIES
```

Vì vậy:

- Chỉ primary chủ động thực hiện TTL deletes.
- Secondaries nhận hiệu ứng xóa qua replication.
- Nếu test đọc secondary, có thể thấy một document cũ trong thời gian replication lag.
- Sau failover có thể có khoảng trễ đến khi primary mới thực hiện TTL pass.
- Một standalone container đơn có thể khác với replica set production ở những điểm này.

### 30.1. Test nên đọc từ primary khi xác minh TTL cơ bản

Dùng read preference mặc định primary để giảm nguồn eventual delay thứ hai.

### 30.2. Test replication riêng

Nếu ứng dụng cố tình đọc secondary, cần có test riêng “sau khi primary xóa, secondary cuối cùng phản ánh xóa” với deadline. Không trộn hai vấn đề vào cùng một test rồi khó biết lỗi do TTL hay replication.

---

## 31. TTL không thay kiểm tra hết hạn ở application

Đây là nguyên tắc bảo mật rất quan trọng.

Mã OTP đã hết hạn lúc 10:00 nhưng TTL monitor chưa xóa đến 10:00:45. Nếu application chỉ kiểm tra:

```java
codes.find(Filters.eq("codeHash", hash)).first();
```

rồi cho phép sử dụng vì document vẫn tồn tại, mã hết hạn có thể được chấp nhận.

### 31.1. Query đúng cho hành vi nghiệp vụ

```java
Date now = new Date();

Document usable = codes.find(
    Filters.and(
        Filters.eq("codeHash", hash),
        Filters.gt("expiresAt", now)
    )
).first();
```

TTL chỉ chịu trách nhiệm cleanup storage, còn application kiểm tra deadline logic.

### 31.2. Test nên chia hai phần

**Unit/integration business test:**

- Insert một mã có `expiresAt` trong quá khứ.
- Gọi API xác thực ngay.
- Kỳ vọng từ chối **không cần đợi TTL monitor**.

**TTL integration test:**

- Insert mã đã hết hạn.
- Poll đến khi document được MongoDB dọn.
- Không dùng kết quả vật lý dọn document làm điều kiện xác thực hợp lệ.

---

## 32. Kiểm thử clock và độ lệch thời gian

Trong Java, tạo ngày hết hạn bằng `Instant` và `Clock`:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-14T10:00:00Z"),
    ZoneOffset.UTC
);

Instant expiresAt = Instant.parse(
    "2026-11-14T09:59:59Z"
);

boolean expired =
    !expiresAt.isAfter(fixed.instant());

assertTrue(expired);
```

### 32.1. Clock injectable giúp unit test deterministic

Các trường hợp:

- Trước hạn 1 ms.
- Đúng hạn.
- Sau hạn 1 ms.
- Qua ngày/tháng/năm.
- UTC timezone.
- Bảo đảm input Date đúng BSON type khi save.

### 32.2. Không thể chỉ fake Java clock để ép MongoDB TTL monitor

MongoDB server có clock của nó. `Clock.fixed` chỉ thay đồng hồ trong code Java test, **không đổi server clock**.

Vì vậy:

- Unit test deadline logic với fake Clock.
- TTL integration test với Date đã cũ hơn server wall clock đáng kể.
- Không sửa đồng hồ OS/docker host khi chạy suite chung.

---

## 33. TTL monitor metrics và chẩn đoán

MongoDB có thể báo:

```javascript
db.serverStatus().metrics.ttl;
```

Tùy phiên bản, các fields gồm:

- `deletedDocuments`: số documents đã bị TTL xóa kể từ lúc process bắt đầu.
- `passes`: số TTL passes.
- `subPasses`: số sub-passes.
- Những counters bổ sung như `deletedKeys`, `examinedDocuments`, `examinedKeys`, `invalidTTLIndexSkips` theo version.

### 33.1. Counters là toàn server

Không được suy luận:

```text
metrics.ttl.deletedDocuments tăng 1
=> document test của tôi chắc chắn đã bị xóa
```

Server có thể đang xóa document khác trong collection khác. Để xác minh đối tượng test, **query theo ID cụ thể**.

### 33.2. Dùng delta để điều tra

```text
before: metrics.ttl.passes = 100
after:  metrics.ttl.passes = 102
```

Delta cho thấy đã có các lượt monitor, nhưng nếu document test vẫn tồn tại phải kiểm tra:

- Index key/option.
- BSON Date.
- Giá trị Date.
- Primary state.
- Read preference.
- Collection name.
- Server version.
- TTL monitor/backlog.

### 33.3. Không xem một số metric làm nguồn sự thật duy nhất

Một số Atlas tiers/permissions không cho đọc mọi serverStatus fields. Test phải có một assertion nghiệp vụ cốt lõi; metrics chỉ làm diagnostics nếu khả dụng.

---

## 34. Thay đổi TTL index option

Nếu một TTL index đã tồn tại và cần đổi `expireAfterSeconds`, tài liệu MongoDB yêu cầu dùng `collMod`, không đơn giản gọi `createIndex()` cùng key với option mới.

Ví dụ cú pháp:

```javascript
db.runCommand({
  collMod: "verificationCodes",
  index: {
    keyPattern: { expiresAt: 1 },
    expireAfterSeconds: 3600
  }
});
```

### 34.1. Test migration index

Khi sửa retention policy, cần test:

1. Index hiện tại có cấu hình cũ.
2. Migration chạy `collMod` thành công trên release hỗ trợ.
3. `getIndexes()` trả option mới.
4. Test boundary date đã đổi.
5. Không làm dữ liệu production bị xóa ngoài ý muốn.

### 34.2. Rủi ro khi giảm TTL

Giảm từ 30 ngày xuống 1 giờ có thể làm số lượng rất lớn documents trở nên expired ngay. TTL monitor sẽ dọn dần, có thể ảnh hưởng IOPS và độ trễ. Không chạy migration retention mà bỏ qua performance risk.

---

# PHẦN III — TEST ENVIRONMENT VÀ TEST PATTERNS

## 35. Test pyramid

Có ba lớp hợp lý:

| Lớp | Dùng để test | Đặc điểm |
| --- | --- | --- |
| Unit | Tính `expiresAt`, canonicalization, validation, retry policy | Nhanh, deterministic, không cần MongoDB |
| Integration | Index constraint, TTL deletion, queries, writes | Cần MongoDB thật, TTL test có thể chậm |
| End-to-end | API đăng ký, worker, messaging, secondary reads | Kiểm tra toàn luồng, tốn tài nguyên |

### 35.1. Đừng mock MongoDB để chứng minh unique index

Một mock repository trả duplicate-key theo cấu hình chỉ chứng minh application xử lý exception, **không chứng minh server index được tạo đúng**.

### 35.2. Đừng bắt unit suite chờ 60 giây TTL

Business expiration logic có thể test bằng injected Clock trong milliseconds. Chỉ một số integration tests cần chờ tiến trình TTL monitor thật.

### 35.3. Test tag

Có thể dùng JUnit tags:

```java
@Tag("integration")
@Tag("slow-ttl")
@Test
void expiredDocumentEventuallyRemoved() {
    // ...
}
```

CI có thể chạy slow TTL suite ở profile thích hợp, nhưng không được bỏ qua mãi nếu retention feature là critical.

---

## 36. Testcontainers + JUnit 5 cho MongoDB thật

Ví dụ dùng Testcontainers API phổ biến ở dòng 1.x:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import java.util.UUID;

public abstract class MongoIntegrationFixture {

    private static final MongoDBContainer MONGO =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    static {
        MONGO.start();
    }

    private static final MongoClient CLIENT =
        MongoClients.create(
            MONGO.getReplicaSetUrl()
        );

    protected MongoCollection<Document> collection;
    protected String collectionName;

    @BeforeEach
    void newCollection() {
        collectionName = "case_" + UUID.randomUUID()
            .toString()
            .replace("-", "");

        MongoDatabase database =
            CLIENT.getDatabase("mongo_testing");

        collection = database.getCollection(collectionName);
    }

    @AfterEach
    void cleanup() {
        if (collection != null) {
            collection.drop();
        }
    }
}
```

Lưu ý:

- Code minh họa sử dụng Testcontainers API của những bản có `org.testcontainers.containers.MongoDBContainer`.
- Các Testcontainers phiên bản mới có thể thay package/module API; đối chiếu release documentation của dependency.
- Chọn image version **có hỗ trợ** tính năng đang test; `mongo:7.0` chỉ là ví dụ.
- Đoạn fixture chỉ minh họa lifecycle, không bao gồm cấu hình dependency/build; CI cần Docker runtime và quyền phù hợp.
- Vì là test environment, việc `drop()` chỉ áp dụng collection tên ngẫu nhiên trong database test.
- Một số test MongoDB transaction/change stream cần replica set; `getReplicaSetUrl()` hỗ trợ kết nối Testcontainers replica set trong API tương ứng.

### 36.1. Không chạy TTL test trong in-memory mock

TTL monitor là chức năng server. In-memory mock thường không mô phỏng lịch background deletion và index semantics đầy đủ.

### 36.2. Không dùng cluster production làm integration fixture

Test unique/TTL có thể tạo/xóa index, insert duplicate records, chờ xóa documents và drop collections. Luôn dùng môi trường riêng, không tái sử dụng namespace production.

---

## 37. Fixture cô lập để tránh test ảnh hưởng nhau

Các nguồn flakiness thường thấy:

- Hai test cùng dùng collection `users`.
- Test A gọi `drop()` khi test B đang insert.
- TTL monitor xóa records còn lại từ test trước.
- Một test tạo unique index, test khác kỳ vọng collection chưa có index.
- Background worker của test trước vẫn chạy khi test sau bắt đầu.
- Một test dùng Date tương lai quá gần.

### 37.1. Một collection cho mỗi test

```java
String name = "ttl_" +
    UUID.randomUUID().toString().replace("-", "");

MongoCollection<Document> codes =
    database.getCollection(name);
```

Khi `@AfterEach`, drop đúng collection mà test đó sở hữu.

### 37.2. Không chỉ dựa vào collection cleanup

Nếu test có Kafka consumer, scheduled worker, HTTP server hoặc executor threads, cần dừng các thành phần ấy sau test, nếu không event của test cũ có thể gây side effects ở test mới.

### 37.3. Test parallelism

Có thể chạy các unit tests song song. Với integration tests phụ thuộc MongoDB TTL monitor hoặc tài nguyên Docker, cần giới hạn mức parallelism phù hợp. TTL monitor là một background service chung trong `mongod`, không cấp một thread riêng cho mỗi test collection.

---

## 38. Awaitility: chờ trạng thái thay vì chờ một thời gian cứng

Với công việc bất đồng bộ:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() -> {
        assertEquals(
            "COMPLETED",
            jobs.find(eq("_id", jobId))
                .first()
                .getString("status")
        );
    });
```

### 38.1. Ưu điểm

- Có thể pass ngay khi điều kiện thỏa.
- Không giữ test lâu nếu hệ thống xử lý nhanh.
- Có deadline và thông báo timeout.
- Có thể kiểm tra kết quả phức tạp qua `untilAsserted`.

### 38.2. Polling phải an toàn

Biểu thức poll nên là **read-only**. Đừng làm:

```java
await().until(() -> sendEmailAgain());
```

vì mỗi lần poll sẽ gây side effect.

### 38.3. Null-safe poll

Nếu record chưa được tạo:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .until(() -> {
        Document job =
            jobs.find(eq("_id", jobId)).first();
        return job != null
            && "COMPLETED".equals(job.getString("status"));
    });
```

Tránh `job.getString(...)` khi `job == null` khiến test fail sai loại lỗi.

---

## 39. Chọn timeout theo đặc tính từng hành vi

| Hành vi | Đặc tính | Deadline test gợi ý |
| --- | --- | --- |
| Unique duplicate insert | Constraint đồng bộ | Assert exception ngay trong thao tác |
| Worker trong memory | Scheduling nhanh nhưng không deterministic | Vài giây |
| Outbox consumer qua broker | Network/consumer scheduling | Hàng chục giây |
| Secondary replication | Lag phụ thuộc topology/load | Theo SLO thử nghiệm |
| TTL deletion | Monitor định kỳ ~60 s + backlog | Vài phút cho integration |
| Time-series TTL | Bucket granularity + monitor | Dựa trên bucket span |
| Search indexing | Đồng bộ dữ liệu sang search index riêng | Theo dữ liệu/index size |
| Backup/index build | Có thể dài và phụ thuộc dung lượng | Theo mục tiêu riêng, không chung timeout ngắn |

Đây là **ví dụ thiết kế test budget**, không phải các SLA MongoDB cam kết.

### 39.1. Không copy-paste timeout 1 giây mọi nơi

Nếu CI bị quá tải hoặc container mới cold-start, 1 giây có thể là quá ngắn cho worker. Nhưng cũng không đặt 10 phút vô điều kiện cho mọi test, vì lỗi logic sẽ tốn thời gian phát hiện.

### 39.2. Quan sát p95/p99 thực tế

Có thể đo độ trễ hoàn thành các async jobs ở staging/CI, rồi chọn budget có headroom hợp lý. Đừng dùng số đo một máy phát triển làm duy nhất.

---

## 40. Kiểm thử “eventually” khác “never”

**Eventually:** điều kiện cuối cùng phải thành đúng.

```text
TTL: document phải cuối cùng bị xóa.
Outbox: event phải cuối cùng thành PROCESSED.
```

**Never:** sự kiện bị cấm không được xảy ra trong một cửa sổ quan sát.

```text
Không bao giờ có hai active accounts trùng email trong cùng tenant.
Không gửi cùng payment hai lần.
```

### 40.1. Invariant trực tiếp thường dễ chứng minh hơn

Unique index làm MongoDB từ chối duplicate ngay. Test hai concurrent writes + count cuối là bằng chứng về trường hợp cạnh tranh được test.

### 40.2. Với async “never”, một lần query không đủ

Nếu muốn bảo đảm không gửi hai messages trong 5 giây, cần theo dõi trong **cả cửa sổ** chứ không chỉ assert số lượng đúng 1 tại giây đầu.

Awaitility có các patterns `during`/`atLeast` theo phiên bản, hoặc viết observer thu events rồi assert sau một observation window có deadline. Dù vậy, một test hữu hạn không thể chứng minh một event sẽ **không bao giờ** xảy ra sau khi test kết thúc; cần idempotency/unique constraints ở production.

---

## 41. Kiểm thử trạng thái chuyển tiếp

Một background job có state machine:

```text
PENDING -> RUNNING -> COMPLETED
                   \-> FAILED -> RETRY_WAIT -> RUNNING
```

Không nên chỉ test kết quả `COMPLETED`. Cần quan tâm:

- Một job không đồng thời ở hai states.
- Không có hai workers sở hữu cùng lease.
- State transitions được ghi đúng.
- Retries có giới hạn và backoff.
- Failed event được quarantine.
- Duplicate event không tạo duplicate effects.
- Sau `COMPLETED` không xử lý tiếp tùy tiện.

### 41.1. Test worker success

```java
String jobId = createTestJob();

await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(200))
    .until(() -> {
        Document job = jobs.find(eq("_id", jobId)).first();
        return job != null
            && "COMPLETED".equals(job.getString("state"));
    });
```

### 41.2. Test error path

Không để test chờ worker thành `COMPLETED` nếu đúng nghiệp vụ là chuyển `FAILED`. Dùng state machine và assert error metadata/retry count tương ứng.

---

## 42. Outbox và idempotency test

Một flow:

```text
Order created
     |
     v
Insert outbox event
     |
     v
Worker publishes event
     |
     v
Mark outbox PROCESSED
```

Nếu worker publish thành công rồi crash trước khi mark, event có thể bị publish lại.

### 42.1. Thiết kế test

1. Tạo order và outbox event ID cố định.
2. Cho worker gửi một lần.
3. Giả lập crash giữa publish và checkpoint.
4. Restart worker.
5. Xác minh downstream idempotency theo event ID.
6. Xác minh không có duplicate business side effect.
7. Kiểm tra outbox state sau retry.

### 42.2. Unique index trên event ID

Một unique index trên `eventId` ở downstream inbox có thể giúp từ chối xử lý lại trùng event. Nhưng side effect bên ngoài (thanh toán/email) còn cần chính sách idempotency riêng.

### 42.3. Không test bằng sleep đoán lịch worker

Không nên:

```java
sendEvent();
Thread.sleep(500);
assertEquals(1, countProcessed());
```

Thay bằng poll theo event/job ID và deadline.

---

## 43. Change Streams và test eventual event

Change Streams cho phép subscription thay đổi ở MongoDB khi deployment hỗ trợ.

Một bài test cần lưu ý:

- Change Stream cần topology hỗ trợ (thường replica set/sharded cluster).
- Listener phải **được thiết lập trước** thao tác tạo event nếu muốn chứng minh event đó được thấy.
- Mở cursor/tạo subscription không được nhầm với worker đã thật sự ready.
- `resume token` khác server cursor ID.
- `tryNext()` có thể chưa có event và trả null, không có nghĩa stream đã kết thúc.
- Cleanup cursor/subscription khi test kết thúc.

### 43.1. Race “subscribe vs publish”

Sai:

```text
startListenerAsync()
insertDocument()
assertListenerSawEvent()
```

nếu `startListenerAsync()` trả ngay trước khi listener thật sự subscribe.

### 43.2. Test đúng với barrier

```text
start listener
wait listener READY
insert document with correlation ID
await event with matching ID
close listener
```

### 43.3. Không assert thứ tự tuyệt đối khi nguồn phân tán

Với nhiều partitions/shards/consumers, order guarantee có scope cụ thể. Chỉ assert những thứ hệ thống thực sự cam kết.

---

## 44. Replication lag và read preference trong integration tests

Trên replica set:

- Primary xử lý writes.
- Secondary nhận và áp dụng oplog.
- Một read từ secondary có thể thấy state cũ.

### 44.1. Test ghi rồi đọc primary

Để kiểm tra unique/TTL logic cơ bản, ưu tiên read primary nhằm giảm ảnh hưởng replica lag.

### 44.2. Test read-your-writes

Nếu business yêu cầu đọc thấy write vừa hoàn tất, chọn read preference/read concern/session semantics đúng. Không mặc định secondaryPreferred sẽ thấy write ngay.

### 44.3. Test eventual secondary consistency

1. Write document ở primary.
2. Poll trên secondary theo configured read preference.
3. Deadline dựa trên môi trường/lag SLA.
4. Ghi diagnostics lag nếu timeout.
5. Không đánh đồng replication lag với TTL monitor lag.

---

## 45. Hành vi xóa TTL trong ứng dụng có replication

Khi document hết hạn:

```text
Primary TTL delete
        |
        v
Secondary replay delete
```

Một test `find()` trên secondary có thể tiếp tục nhìn thấy document dù primary đã xóa. Nếu test fail:

1. Kiểm tra primary đã xóa chưa.
2. Kiểm tra read preference của test.
3. Kiểm tra secondary lag.
4. Kiểm tra TTL metrics.
5. Kiểm tra Date/index metadata.

Không giải quyết bằng cách tăng timeout tùy tiện khi root cause là sai nguồn đọc.

---

## 46. Test negative path của TTL

Các trường hợp nên có:

| Document | Ý nghĩa | Kỳ vọng |
| --- | --- | --- |
| `expiresAt` Date quá khứ | Đủ điều kiện TTL | Cuối cùng bị xóa |
| `expiresAt` Date tương lai xa | Chưa đủ hạn | Không bị xóa trong cửa sổ test |
| Thiếu `expiresAt` | Không có indexed Date | Không bị TTL xóa |
| `expiresAt` là string | Sai BSON type | Không bị TTL xóa |
| `expiresAt: null` | Không có Date | Không bị TTL xóa |
| Array nhiều Date | Dùng ngày sớm nhất | Cuối cùng hết hạn theo ngày sớm nhất |
| Index `expireAfterSeconds:0` | Expire theo absolute Date | Ngày quá khứ bị xóa sau monitor |
| Index `expireAfterSeconds:3600` | Expire theo Date + duration | Trước/ngang/sau ngưỡng tính đúng |

### 46.1. Không dùng TTL để chứng minh validation

Nếu ứng dụng **phải từ chối** string ở `expiresAt`, test schema validation hoặc application validation phải assert write bị từ chối. TTL chỉ không dọn string, đó không phải validation.

### 46.2. Khi test “không xóa”, cần cửa sổ quan sát

Một assertion tức thời trên Date tương lai chỉ nói document đang tồn tại. Với test retention policy, kết hợp kiểm tra metadata + logic tính expiration + một khoảng quan sát phù hợp với monitor schedule.

---

## 47. Kiểm thử ranh giới thời gian bằng Clock

Tách domain logic khỏi TTL:

```java
public final class CodeExpiryService {
    private final Clock clock;

    public CodeExpiryService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(clock.instant());
    }
}
```

Unit test:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-14T10:00:00Z"),
    ZoneOffset.UTC
);

CodeExpiryService service =
    new CodeExpiryService(fixed);

assertFalse(
    service.isExpired(
        Instant.parse("2026-11-14T10:00:00.001Z")
    )
);

assertTrue(
    service.isExpired(
        Instant.parse("2026-11-14T10:00:00Z")
    )
);

assertTrue(
    service.isExpired(
        Instant.parse("2026-11-14T09:59:59.999Z")
    )
);
```

### 47.1. Lưu ý Precision

BSON Date lưu mili-giây từ Unix epoch. Nếu domain dùng nanoseconds, cần thống nhất policy làm tròn/chuyển sang milliseconds trước khi so sánh với persisted dates.

### 47.2. Server Clock riêng

Clock trong service Java không thay server time của MongoDB TTL monitor. TTL integration test dùng thời điểm quá khứ/tương lai rõ ràng để tránh phải điều chỉnh clock hệ thống.

---

## 48. Tránh các nguồn flakiness khi test async

Các anti-pattern thường gặp:

1. Dùng `Thread.sleep(100)` thay cho điều kiện.
2. Không chờ index build hoàn tất.
3. Dùng chung database/collection giữa tests song song.
4. Query secondary khi cần quan sát primary state.
5. Dùng Date chỉ cách hiện tại vài mili-giây.
6. Không đợi worker/subscriber ready trước khi publish.
7. Test phụ thuộc thứ tự scheduling của hai threads.
8. Dùng same document IDs giữa các tests.
9. Không cleanup jobs/threads sau failure.
10. Trộn unique index, TTL và external retries vào một test khó hiểu.
11. Timeout quá ngắn so với TTL monitor cycle.
12. Timeout quá dài làm bug ẩn nhiều phút.
13. Chờ một side effect xảy ra mà worker thực tế đã tắt.
14. Không ghi log correlation ID.
15. Dùng mocks để kết luận về MongoDB server behavior.

### 48.1. Test deterministic trước tiên

Khi có thể, đưa tính toán thời gian và state transition vào các hàm thuần rồi unit test. Chỉ để phần thật sự asynchronous/DB-dependent cho integration.

---

## 49. Chẩn đoán khi TTL integration test timeout

Giả sử sau ba phút document quá khứ vẫn còn.

Kiểm tra theo thứ tự:

1. Test có kết nối đúng URI/database/collection không?
2. `getIndexes()` có index đúng key/option không?
3. `expiresAt` có phải BSON Date không?
4. Giá trị Date đã thật sự ở quá khứ so với server clock chưa?
5. `expireAfterSeconds` có đúng **giây**, không phải milliseconds, không?
6. Collection có phải time-series với bucket semantics khác không?
7. MongoDB có PRIMARY và TTL monitor đang chạy không?
8. Read preference có vô tình là secondary không?
9. Có TTL backlog lớn từ các tests khác không?
10. Có tạo index thành công trước insert không?
11. Có server-side TTL metric `passes` tăng không?
12. Có `deletedDocuments` tăng không (chỉ dùng làm diagnostic)?
13. Có migration/index modification gây xung đột không?
14. Có test khác re-insert cùng `_id` không?
15. Có external cleanup worker ảnh hưởng kết quả không?
16. Docker host/CI có quá tải IOPS/CPU không?

### 49.1. Không chữa flake bằng timeout vô hạn

Nếu mọi TTL test cần 10 phút trên một collection vài documents và nhiều test bị timeout, điều tra monitor/fixture trước khi tăng timeout tiếp.

---

## 50. Chẩn đoán khi unique index test fail

Các nguyên nhân:

- Index chưa được tạo hoặc tạo thất bại do duplicates có sẵn.
- Test chỉ kiểm tra duplicate `_id` chứ không phải field cần bảo vệ.
- Index là compound nhưng test quên field một phần key.
- Index là sparse/partial, document không match filter.
- Collation của test không khớp với index.
- Test collection bị dùng chung và còn records cũ.
- Sharded cluster không hỗ trợ index specification đó.
- Các writes có `w`/acknowledgement policy không phù hợp.
- Test retry logic nuốt duplicate-key và báo thành công giả.
- BulkWrite trả exception khác MongoWriteException.
- Fixture tạo index sau khi workers đã bắt đầu.

### 50.1. Cần kiểm tra metadata, không chỉ lời exception

```javascript
db.accounts.getIndexes();
```

Xác nhận:

- `key`.
- `unique`.
- `partialFilterExpression`.
- `sparse`.
- `collation`.
- `name`.

---

## 51. Test retry và idempotency không chỉ đếm request

Một job có thể bị giao lại nhiều lần. Hãy kiểm tra:

- Không tạo thêm record có cùng business key.
- Không gửi external payment hai lần.
- Không có hai `COMPLETED` events cho một operation.
- Retry count theo policy.
- Thao tác duplicate được ghi nhận là idempotent success hay conflict đúng domain.
- Kết quả cuối có thể truy vấn được.
- Không giữ resource/lease vô hạn sau timeout.

### 51.1. Unique index không bảo đảm toàn bộ side effect

Một unique index trên `eventId` có thể chặn ghi trùng vào MongoDB, nhưng không tự ngăn một email gửi lần hai nếu ứng dụng gọi email service **trước** khi ghi inbox marker. Test integration phải mô phỏng thứ tự thất bại có thật.

---

## 52. Observability cho test bất đồng bộ

Để một failure dễ phân tích, log:

```text
testCaseId
collection namespace
document _id / correlationId
index name/key/options
event createdAt / expiresAt
observed state during polls
worker attempt count
last poll timestamp
deadline
MongoDB server version/topology
TTL passes/deletedDocuments if available
```

### 52.1. Tránh log secrets

Nếu test dùng token/OTP, log hash/correlation ID, không log nguyên mã xác minh hoặc thông tin cá nhân.

### 52.2. Không lấy `serverStatus` mỗi 10ms

Monitoring query có chi phí và cần quyền. Thu thập metrics vào lúc timeout hoặc theo chu kỳ vừa phải.

### 52.3. Poll condition quan trọng nhất

Một test TTL có thể log 5 metric của server nhưng vẫn phải assert document của **chính test** đã bị xóa.

---

## 53. Sử dụng `@Timeout` với JUnit

Có thể đặt overall test timeout để ngăn suite treo:

```java
@Tag("slow-ttl")
@Timeout(value = 4, unit = TimeUnit.MINUTES)
@Test
void ttlEventuallyDeletes() {
    // Awaitility deadline 3 phút.
}
```

Lưu ý:

- `@Timeout` của JUnit và timeout của Awaitility có phạm vi khác.
- Có thể xảy ra vấn đề hủy thread đang block; thiết kế cleanup cần `finally`/try-with-resources.
- Không đặt JUnit timeout **ngắn hơn** Awaitility deadline cộng startup/fixture overhead.

### 53.1. Không dùng timeout một phút cho TTL 60 giây

Nếu container khởi động/index build vài giây và TTL monitor cũng có thể chờ gần 60 giây, tổng test budget một phút có thể không đủ ngay cả khi server hoạt động bình thường.

---

## 54. `await().untilAsserted()` và diagnostics khi deadline hết

Ví dụ test background job:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        Document job = jobs.find(eq("_id", jobId)).first();

        assertNotNull(job);
        assertEquals("COMPLETED", job.getString("state"));
        assertEquals(0, job.getInteger("errorCount", 0));
    });
```

Nếu hết deadline, failure cho biết assertion nào chưa thỏa.

### 54.1. Cẩn thận poll exception

Một transient network exception khi poll có thể bị Awaitility xử lý khác với assertion error. Không blanket-ignore mọi exception nếu test đáng lẽ phải fail khi DB unreachable. Chỉ ignore những exception **thật sự được coi là transient** theo policy.

### 54.2. Ghi dữ liệu diagnostic đúng lúc

Khi timeout, đọc documents/job state/metrics theo quyền phù hợp và attach vào CI artifacts (tránh secrets). Không thay test failure bằng một warning rồi cho suite pass.

---

## 55. Kiểm thử eventual deletion có thể bị job khác “qua mặt”

Giả sử một test:

```java
await().until(() -> codes.find(eq("_id", id)).first() == null);
```

và service ứng dụng có cleanup scheduler cũng đang xóa document.

Test sẽ pass dù TTL index không hoạt động.

### 55.1. Cách tách biệt

- Chạy TTL integration trên namespace chỉ được MongoDB TTL monitor dọn.
- Không chạy application cleanup worker đối với collection test.
- Kiểm tra TTL index metadata và BSON Date.
- Quan sát TTL metrics nếu cần chẩn đoán.
- Test business cleanup riêng.

### 55.2. Đừng bật hai cơ chế rồi tuyên bố kiểm chứng từng cơ chế

Nếu mục tiêu là TTL, fixture phải có ownership rõ: không có một background worker khác có thể xóa cùng record.

---

## 56. Race giữa TTL và application read

Tình huống:

```text
10:00:00 Token expires.
10:00:01 User submits token.
10:00:02 TTL has not deleted the document.
```

Nếu application chỉ kiểm tra token tồn tại, người dùng có thể được chấp nhận dù token hết hạn.

Test nên:

1. Insert token có `expiresAt` quá khứ.
2. Gọi verify API **ngay**, không chờ TTL.
3. Kỳ vọng response expired/invalid.
4. Trong TTL integration riêng, cuối cùng token bị dọn.
5. Nếu token có cơ chế one-time use, test concurrent redeem hai lần chỉ một lần được phép.

### 56.1. Atomic consume một lần

Một hướng thiết kế là dùng `findOneAndDelete`/conditional update với filter có `expiresAt > now` và unused state, khi phù hợp business/security model. Test hai requests cạnh tranh phải đảm bảo không có hai lần redeem thành công.

### 56.2. TTL không thay atomicity

TTL chỉ cleanup, không cung cấp transactional “consume exactly once” cho token. Đây là hai constraints riêng.

---

## 57. Kiểm thử concurrent token consumption

Một ví dụ domain yêu cầu mỗi mã chỉ dùng một lần:

```text
Request A            Request B
    |                    |
find token             find token
    |                    |
redeem?                redeem?
```

Nếu hai requests chỉ `find` rồi cập nhật, race có thể cho cả hai cùng thành công.

Một thao tác atomic phù hợp:

```java
Document consumed =
    codes.findOneAndDelete(
        Filters.and(
            Filters.eq("_id", codeId),
            Filters.gt("expiresAt", new Date())
        )
    );
```

Với cùng `_id`, một request có thể xóa và nhận document, request còn lại nhận null. Test concurrent requests kiểm tra **đúng một** thành công.

### 57.1. Lưu ý

- Không lộ raw OTP khi log/assert.
- Có thể cần thêm `accountId`, hash và trạng thái bảo mật trong filter.
- Nếu side effect của redeem là external, vẫn cần idempotency.
- Nếu Date từ client bị lệch clock, cần policy clock skew hoặc server-side timestamp logic.
- TTL monitor có thể xóa token trước cả hai requests khi đã expired; đây là behavior đúng.

---

## 58. Test data setup cho TTL và unique trong một hệ thống

Một bài integration có cả unique và TTL:

```javascript
db.oneTimeCodes.createIndex(
  { accountId: 1, purpose: 1 },
  {
    unique: true,
    name: "uq_account_purpose"
  }
);

db.oneTimeCodes.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expires_at"
  }
);
```

### 58.1. Cách hiểu đúng hai index

- Unique index cấm có **hai documents cùng accountId/purpose tại cùng thời điểm**, bất kể `expiresAt` đã qua hay chưa.
- TTL index tự dọn document đã hết hạn nhưng **không xóa ngay**.
- Vì vậy việc tạo mã mới cho cùng accountId/purpose trước khi TTL monitor dọn mã cũ có thể trả E11000.

### 58.2. Đây là một race nghiệp vụ thực tế

Nếu ứng dụng giả định “mã cũ hết hạn nghĩa là unique key đã rảnh”, sẽ thất bại ngẫu nhiên.

Các hướng thiết kế:

1. Update/upsert **cùng document** để cấp lại mã, thay `expiresAt`.
2. Xóa mã cũ có điều kiện trước khi insert mới, có xét concurrency.
3. Thay business key để cho phép nhiều generation ID, chỉ một mã được đánh dấu active theo ràng buộc.
4. Dùng partial unique trên field trạng thái `active` và quản lý transition atomically khi phù hợp.
5. Dùng một record chứa version/nonce cập nhật có điều kiện.

### 58.3. Test buộc phải có

- Tạo mã lần đầu.
- Yêu cầu tạo lại ngay sau khi logic expire nhưng TTL chưa chắc dọn.
- Hai requests cấp mã đồng thời.
- Mã cũ không được redeem sau expiration.
- Mã mới hoạt động.
- Cuối cùng TTL dọn các bản ghi expired theo policy.

---

## 59. Testing matrix tổng hợp

| Case | Setup | Action | Expected |
| --- | --- | --- | --- |
| Unique insert | Index ready, key A | Insert key A lần 2 | E11000 |
| Unique update | Hai keys A/B | Update B→A | E11000; B unchanged |
| Compound unique | T1/A có sẵn | T2/A | Success |
| Compound duplicate | T1/A có sẵn | T1/A | E11000 |
| Single unique missing | Một doc thiếu field | Doc thứ hai thiếu | Duplicate |
| Sparse unique missing | Hai docs thiếu field | Insert cả hai | Success |
| Sparse explicit null | Một null đã có | Thêm null khác | Duplicate |
| Partial unique | Chỉ active indexed | Inactive duplicate | Success |
| Partial promotion | Inactive duplicate | Set active:true | Duplicate |
| Case-insensitive unique | Collation strength 2 | Khác hoa/thường | Duplicate |
| Multikey unique | Duplicate trong cùng doc | Insert một doc | Có thể thành công |
| Multikey giữa docs | Alias A đã có | Doc khác alias A | Duplicate |
| Index build duplicate | Data có duplicates | Create unique index | Build fails |
| Concurrent insert | Hai writers cùng key | Barrier start | Một winner |
| TTL expired | Date quá khứ | Wait/poll | Eventually absent |
| TTL future | Date tương lai xa | Observe | Remains in window |
| TTL wrong type | String Date | Wait | Không bị TTL xóa |
| TTL missing | Không có field | Wait | Không bị TTL xóa |
| TTL array | Hai Date values | Wait | Expire theo Date sớm nhất |
| TTL + unique | Old expired nhưng chưa dọn | Insert same unique key | Có thể E11000 |
| Worker eventual | Job PENDING | Trigger processing | Eventually COMPLETED |
| Worker failure | Dependency fails | Trigger | FAILED/RETRY theo policy |
| Worker duplicate | Cùng event gửi 2 lần | Retry | Không duplicate effect |
| Change stream | Subscriber READY | Insert | Event cuối cùng tới |
| Secondary read | Primary write | Read secondary | Eventually visible |
| Token one-time | Hai redeem requests | Concurrent | Một winner |
| Cursor/listener cancel | Có job đang chạy | Cancel | Resources cleanup |
| Test isolation | Hai tests chạy song song | Cùng suite | Không ảnh hưởng nhau |

---

## 60. Bài tập 1: vì sao check-then-insert sai?

Code:

```java
if (accounts.find(eq("email", email)).first() == null) {
    accounts.insertOne(
        new Document("email", email)
    );
}
```

Hai requests cùng email chạy đồng thời.

**Hỏi:** Tại sao có thể tạo duplicate?

**Đáp án:** Cả hai có thể đọc “chưa tồn tại” trước khi bất kỳ request nào insert. Test concurrency phải có **unique index** thực và kiểm tra một winner/một duplicate-key.

---

## 61. Bài tập 2: unique index trên email optional

Index:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

Hai users không có field `email`.

**Đáp án:** Với non-sparse single-field unique index, chúng có cùng null index key, nên không thể cùng tồn tại. Nếu domain cho phép email optional, cân nhắc partial unique trên string email.

---

## 62. Bài tập 3: sparse unique với null

Index:

```javascript
db.users.createIndex(
  { email: 1 },
  { sparse: true, unique: true }
);
```

Hai documents `email:null`.

**Đáp án:** Sparse bỏ qua missing fields, nhưng explicit null vẫn được index; hai null có thể trùng key và bị từ chối.

---

## 63. Bài tập 4: partial unique cho active

Index:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: { active: true }
  }
);
```

User A inactive và user B active có cùng email.

**Đáp án:** Có thể cùng tồn tại vì chỉ B được index. Nếu đổi A sang active mà B vẫn active, update bị duplicate-key.

---

## 64. Bài tập 5: TTL sau một giây

Đặt `expiresAt = now + 1s`, sleep 1500 ms, assert null.

**Đáp án:** Flaky. MongoDB TTL monitor không đảm bảo xóa ngay sau expiration; cần poll với deadline và dùng Date quá khứ rõ ràng để chỉ kiểm thử monitor.

---

## 65. Bài tập 6: TTL option tính theo đơn vị nào?

```javascript
db.tokens.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 600 }
);
```

**Đáp án:** Document đủ điều kiện sau 600 giây (~10 phút) từ field BSON Date, không phải 600 milliseconds.

---

## 66. Bài tập 7: BSON Date hay String?

Document:

```javascript
{ _id: "V1", expiresAt: "2026-11-14T10:00:00Z" }
```

**Đáp án:** `expiresAt` là string, MongoDB TTL không tự parse để expire. Sửa application serialization/schema validation.

---

## 67. Bài tập 8: TTL expired nhưng token còn trong collection

Business API thấy token và cho phép sử dụng.

**Đáp án:** Sai security model. API phải kiểm tra `expiresAt > now` và one-time consumption; TTL chỉ cleanup.

---

## 68. Bài tập 9: unique và TTL cùng collection

Unique trên `{accountId:1,purpose:1}`, TTL trên `expiresAt`. Token cũ đã expired, token mới same key bị E11000.

**Đáp án:** TTL không dọn tức thì; unique constraint vẫn áp dụng cho document cũ còn tồn tại. Dùng update/upsert hoặc thay schema/cấp mã theo policy, không chờ may rủi.

---

## 69. Bài tập 10: TTL replica set

Primary đã xóa token, secondaryPreferred query vẫn đọc thấy token.

**Đáp án:** Có thể do replication lag. Test TTL cơ bản nên đọc primary; test consistency của secondary riêng.

---

## 70. Bài tập 11: concurrent winners

Hai threads insert cùng unique key; test kỳ vọng thread A luôn thành công.

**Đáp án:** Flaky do scheduling. Chỉ assert có đúng một thành công và một duplicate-key, bất kể thread.

---

## 71. Bài tập 12: index build trên dữ liệu trùng

Collection có hai email trùng rồi `createIndex(...unique:true)`.

**Đáp án:** Index build thất bại khi phát hiện duplicate. Không được giả định constraint đã sẵn sàng.

---

## 72. Bài tập 13: async worker

Một job thường chạy sau 200 ms. Test sleep 250 ms rồi assert completed.

**Đáp án:** Không ổn định dưới CI load. Dùng poll theo job ID trong deadline dựa trên SLO/test budget.

---

## 73. Bài tập 14: polling có side effects

Một test gọi `sendEvent()` lại ở mỗi poll.

**Đáp án:** Sai. Poll phải là read-only condition, còn trigger chỉ thực hiện một lần. Nếu không, test có thể tạo duplicate events.

---

## 74. Bài tập 15: kiểm thử không duplicate side effects

Tại giây thứ nhất count=1, test pass. Worker có retry sau 5 giây làm count=2.

**Đáp án:** Một assert tức thời chưa chứng minh “không duplicate”. Dùng idempotency invariant và cửa sổ quan sát phù hợp với retry schedule.

---

## 75. Bài tập 16: Change Stream subscribe race

Test mở consumer async và insert ngay. Consumer bỏ lỡ event.

**Đáp án:** Chờ consumer báo READY trước khi publish; dùng correlation ID và poll event đúng.

---

## 76. Bài tập 17: schema validation và TTL

Document không có `expiresAt` tồn tại lâu, đội ngũ cho rằng TTL broken.

**Đáp án:** TTL không xóa document thiếu Date field; test cần xác minh BSON type và có thể thêm schema validator để buộc presence/type.

---

## 77. Bài tập 18: partial TTL của time-series

Một measurement đã hết hạn nhưng bucket chứa measurement mới hơn.

**Đáp án:** Time-series TTL xử lý bucket theo granularity/expiration của toàn bucket, không mặc nhiên xóa riêng measurement ngay mốc.

---

## 78. Bài tập 19: test dùng mock MongoDB

Mock tự trả E11000 khi email trùng.

**Đáp án:** Chỉ chứng minh application xử lý lỗi, không chứng minh unique index được tạo và thực thi bởi MongoDB thật. Cần integration test.

---

## 79. Bài tập 20: CI flake TTL liên tục

TTL tests timeout nhiều dù Date quá khứ.

**Đáp án:** Kiểm tra monitor, primary, index metadata, test isolation, Docker CPU/IOPS và deadline trước khi tăng timeout vô hạn.

---

## 80. Checklist kiểm thử trước khi đưa vào production

### Unique index

- [ ] Index được tạo với đúng key/unique option.
- [ ] Index build hoàn tất trước khi test writes.
- [ ] Insert duplicate trả error code 11000.
- [ ] Update sang duplicate bị chặn và giữ document cũ.
- [ ] Compound unique có case khác tenant.
- [ ] Missing/null behavior phù hợp domain.
- [ ] Sparse/partial filter được test cả match và non-match.
- [ ] Collation/canonicalization được test.
- [ ] Multikey semantics được hiểu đúng.
- [ ] Index build thất bại khi data có duplicate.
- [ ] Concurrent inserts cho đúng một winner.
- [ ] Bulk partial success được xử lý.
- [ ] Upsert/race có idempotency policy.
- [ ] Sharded uniqueness đáp ứng shard-key prefix constraints.

### TTL

- [ ] `expiresAt`/`createdAt` là BSON Date.
- [ ] Index TTL single-field và option đúng.
- [ ] `expireAfterSeconds` tính theo giây.
- [ ] Dùng Date quá khứ rõ ràng cho E2E TTL.
- [ ] Có deadline lớn hơn chu kỳ monitor và headroom.
- [ ] Dùng polling, không sleep cố định.
- [ ] Future date còn tồn tại trong observation window.
- [ ] Missing/null/wrong type được kiểm tra.
- [ ] Arrays dùng Date sớm nhất theo behavior.
- [ ] Time-series bucket semantics được tách riêng.
- [ ] Kiểm tra TTL primary vs secondary read.
- [ ] TTL metrics hỗ trợ diagnostics, không thay document assertion.
- [ ] Security/business expiration được test độc lập.
- [ ] TTL không bị nhầm là cơ chế giải phóng unique key tức thì.

### Async behavior

- [ ] Có correlation ID hoặc unique test ID.
- [ ] Trigger một lần, poll read-only.
- [ ] Chờ consumer/worker readiness trước khi phát sự kiện.
- [ ] Có bounded wait và failure message hữu ích.
- [ ] Test không phụ thuộc thread scheduling cụ thể.
- [ ] Retry và duplicate events có idempotency.
- [ ] Partial failures được kiểm tra.
- [ ] Cancellation và cleanup rõ ràng.
- [ ] Test data isolation và giới hạn parallelism.
- [ ] Không dùng mocks thay server integration.
- [ ] Có phân loại unit/integration/end-to-end phù hợp.
- [ ] Không nhầm eventually-complete với immediately-complete.
- [ ] Không dùng một snapshot count để chứng minh “never”.
- [ ] Có diagnostics khi CI timeout.
- [ ] Không thao tác trực tiếp production namespace.

---

## 81. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Unique index được kiểm tra bởi một scheduled job.” | Unique constraint được thực thi trong write/index state, không phải TTL-like background cleanup. |
| “Query trước khi insert đủ chống duplicate.” | Có race khi concurrent writers; cần unique index. |
| “Hai threads phải cùng thắng hoặc cùng thua.” | Với cùng unique key và index ready, kỳ vọng một thành công một duplicate. |
| “Index unique đã khai báo trong code nghĩa chắc tồn tại trên DB.” | Migration/fixture phải tạo index thành công. |
| “Nếu lỗi E11000 thì luôn do email.” | Có thể do `_id` hoặc index khác; cần kiểm tra key/index. |
| “Unique sparse bỏ qua mọi null.” | Sparse bỏ qua missing, explicit null vẫn indexed. |
| “Partial unique áp dụng cho cả documents không match filter.” | Chỉ những documents match expression chịu constraint. |
| “Unique compound nghĩa từng field phải riêng lẻ unique.” | Constraint áp trên **tổ hợp** indexed values. |
| “Array có phần tử lặp trong cùng document sẽ vi phạm unique multikey.” | Không mặc nhiên; unique áp giữa documents theo index keys. |
| “Tạo index unique trên data trùng sẽ thành công và dọn trùng.” | Build có thể thất bại; MongoDB không tự xóa dữ liệu trùng. |
| “Unique index trên sharded cluster giống replica set mọi mặt.” | Có shard-key prefix và index-type restrictions. |
| “TTL xóa đúng giây expiresAt.” | Cleanup chạy nền, có độ trễ. |
| “TTL 60 giây nghĩa phải chờ đúng 60 giây rồi assert.” | Monitor có scheduling/backlog, cần polling. |
| “TTL field là ISO string cũng được.” | Cần BSON Date/array Date. |
| “TTL tự xóa document thiếu field Date.” | Không. |
| “expireAfterSeconds tính bằng milliseconds.” | Tính bằng giây. |
| “Compound TTL hoạt động bình thường.” | TTL thông thường chỉ single-field. |
| “TTL xóa trên mọi secondary.” | Primary xóa, secondaries replicate. |
| “Document còn tồn tại thì token chưa hết hạn.” | Business expiration khác physical cleanup. |
| “BSON Date dùng timezone local.” | Date lưu mốc UTC; chuyển đổi UI tách biệt. |
| “Time-series TTL xóa từng measurement đúng hạn.” | Xóa theo bucket semantics. |
| “Mock có thể chứng minh TTL monitor chạy.” | Cần MongoDB thật. |
| “Chỉ cần Thread.sleep đủ lâu là deterministic.” | Không bảo đảm dưới tải biến đổi. |
| “Có thể poll bằng write/trigger lại.” | Poll nên là read-only. |
| “One-time success đồng nghĩa không bao giờ duplicate.” | Cần invariant/idempotency và observation window. |
| “Change Stream listener start call nghĩa consumer ready.” | Cần readiness barrier. |
| “Test đọc secondary ngay sau primary write chắc chắn thấy.” | Có replication lag/read concern considerations. |
| “Tăng timeout giải quyết mọi flake.” | Cần sửa test isolation, setup và root cause. |
| “Unique + TTL nghĩa unique key rảnh ngay lúc expired.” | Không, document còn trong DB vẫn chiếm key. |

---

## 82. Tài liệu tham khảo MongoDB chính thức

1. [Unique Indexes and Duplicate Values — MongoDB Manual](https://www.mongodb.com/docs/manual/core/index-unique/) — ràng buộc unique, null/missing, compound, multikey và sharded restrictions.
2. [Unique Indexes and Schema Validation](https://www.mongodb.com/docs/manual/tutorial/unique-indexes-schema-validation/) — tình huống compound/missing và partial uniqueness.
3. [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) — phân biệt missing với explicit null.
4. [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — filter expression và unique scope.
5. [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — index setup, Date, TTL monitor scheduling và restrictions.
6. [Set up Automatic Removal for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — bucket granularity và cleanup.
7. [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — index build/commit quorum.
8. [Create Indexes — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/) — IndexOptions và unique exceptions.
9. [CRUD Insert — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/insert/) — insert operations và errors.
10. [Bulk Write — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/) — ordered/unordered và partial failures.
11. [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — metrics.ttl và counters khác.
12. [Sharded Cluster Unique Constraints](https://www.mongodb.com/docs/manual/tutorial/unique-constraints-on-arbitrary-fields/) — design uniqueness across shards.
13. [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — chạy MongoDB thật trong integration tests.
14. [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage) — polling có deadline, `until`/`untilAsserted`.
15. [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — lifecycle, assertThrows, timeout và test tags.

Các chi tiết về partial TTL time-series, TTL monitor metrics, index build, driver exceptions và Testcontainers package names có thể thay đổi theo phiên bản. Khi áp dụng, đối chiếu tài liệu ứng với MongoDB Server, Java driver, Testcontainers, Awaitility và JUnit đang dùng.

---

## 83. Kết luận

**Kiểm thử unique index** phải chứng minh **tính toàn vẹn dữ liệu được MongoDB thực thi**: một key trùng không thể lọt qua dù có concurrency. Cần test không chỉ insert mà cả update, compound keys, null/missing, partial/sparse, collation và index readiness.

**Kiểm thử TTL** phải chấp nhận **xóa bất đồng bộ**: expiration time chỉ khiến document đủ điều kiện xóa, TTL monitor dọn sau đó. Dùng BSON Date, index đúng, poll có deadline và quan sát theo document ID; không dựa vào sleep vài giây hoặc tin rằng TTL thay business expiration check.

**Kiểm thử async behavior** cần test trạng thái hội tụ, timeout, retry/idempotency, data isolation và side effects. Polling read-only và readiness barriers làm test đáng tin cậy hơn những delay ngẫu nhiên.

Cuối cùng, đừng quên tương tác giữa hai tính năng: **một document đã hết hạn logic nhưng chưa bị TTL xóa vẫn có thể chiếm unique key**. Thiết kế application phải giải quyết tình huống này bằng atomic update, idempotency hoặc data model phù hợp.

**Một test đáng tin không cố ép hệ thống bất đồng bộ chạy “ngay lập tức”; nó khẳng định đúng những bảo đảm mà MongoDB và ứng dụng thực sự cung cấp, với thời hạn quan sát rõ ràng và dữ liệu kiểm thử được cô lập.**
