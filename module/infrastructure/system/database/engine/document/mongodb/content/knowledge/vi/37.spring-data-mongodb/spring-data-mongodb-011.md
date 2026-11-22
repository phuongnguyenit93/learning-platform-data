# Quản lý index tường minh và rủi ro tự tạo index khi khởi động

Một ứng dụng Spring Boot dùng **Spring Data MongoDB** có thể khai báo index ngay trên Java entity bằng `@Indexed` hoặc `@CompoundIndex`. Cách viết này rất thuận tiện: người phát triển nhìn vào class là biết một số yêu cầu truy vấn và ràng buộc dữ liệu. Nhưng giữa **khai báo mong muốn** và **thay đổi cấu trúc index thật trong MongoDB** có một khoảng cách vận hành rất quan trọng.

Hãy hình dung ứng dụng đang chạy trên 20 pods, collection `customer_accounts` chứa 80 triệu documents. Một lập trình viên thêm:

```java
@Indexed(unique = true)
private String email;
```

rồi bật:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

Khi phiên bản ứng dụng mới được triển khai, nhiều instances có thể tìm cách tạo index ở thời điểm khởi động. Nếu dữ liệu hiện có chứa email trùng, index unique không được tạo thành công. Nếu collection rất lớn, quá trình build index có thể gây tải CPU, I/O, disk và làm tăng độ trễ ứng dụng. Nếu index định nghĩa khác index đang tồn tại nhưng có cùng tên, MongoDB có thể báo **index options conflict**. Nếu đổi sang TTL index, dữ liệu đủ điều kiện hết hạn có thể bị xóa sau khi TTL monitor xử lý. Một thay đổi tưởng như chỉ nằm ở Java annotation vì thế có thể trở thành **database schema migration ở production**.

Bài học **“Quản lý index tường minh và rủi ro tự tạo index khi khởi động”** thuộc chương **Spring Data MongoDB** sẽ phân tích cách Spring Data phát hiện index metadata, cách tạo index chủ động qua `MongoTemplate`, những nguy cơ của auto-index creation, và quy trình triển khai index có kiểm soát, kiểm tra trước/sau và rollback.

Ba nguyên tắc xuyên suốt:

1. **Annotation mô tả ý định; index thực tế là đối tượng của MongoDB.** Không coi hai trạng thái này luôn đồng bộ.
2. **Khởi động ứng dụng và nâng cấp schema/index là hai vòng đời khác nhau.** Hạn chế để mọi application pod tự thực hiện DDL khi startup.
3. **Index tốt phải an toàn về dữ liệu, hiệu năng và vận hành**, không chỉ giúp một truy vấn chạy nhanh.

> **Lưu ý phiên bản:** Từ Spring Data MongoDB **3.0**, auto-index creation không còn được bật mặc định. Các property, annotation attributes và API có thể thay đổi giữa Spring Data MongoDB/Spring Boot releases; trước khi triển khai phải kiểm tra tài liệu phù hợp đúng phiên bản đang sử dụng.

---

## 1. Tại sao index cần được quản lý như một phần của schema?

MongoDB cho phép cấu trúc document linh hoạt, nhưng điều đó không có nghĩa cấu trúc database không cần quản lý.

Một MongoDB deployment có nhiều thành phần cần giữ nhất quán:

```text
Application source code
       │
       ├── Java entities (@Document, @Field, @Indexed)
       ├── Repository query methods
       ├── Aggregation pipelines
       ├── Mongotemplate queries
       └── Business rules
                    │
                    ▼
           Database schema contract
                    │
       ┌────────────┼────────────┐
       │            │            │
  Data shape     Indexes      Constraints
       │            │            │
       └────────────┼────────────┘
                    │
                    ▼
          MongoDB production data
```

Index có thể đảm nhận hai nhóm nhiệm vụ:

- **Tối ưu hiệu năng**: hỗ trợ filter, sort, range, pagination, projection.
- **Bảo vệ invariant**: unique index ngăn trùng khóa, TTL index thực hiện retention theo chính sách.

Thêm một index có thể chạm vào mọi dữ liệu hiện có trong collection; xóa một index có thể phá hiệu năng hoặc làm mất ràng buộc duy nhất. Do đó, index là một phần của **database contract** giữa ứng dụng và dữ liệu.

### 1.1. Ví dụ bài toán

Một collection:

```javascript
{
  _id: ObjectId("..."),
  tenantId: "TENANT-01",
  emailNormalized: "alice@example.com",
  status: "ACTIVE",
  createdAt: ISODate("2026-11-10T08:00:00Z"),
  lastSeenAt: ISODate("2026-11-14T03:00:00Z"),
  expiresAt: null
}
```

Các truy vấn:

```javascript
// Tìm tài khoản theo tenant và email đã chuẩn hóa
db.customer_accounts.findOne({
  tenantId: "TENANT-01",
  emailNormalized: "alice@example.com"
});

// Danh sách tài khoản ACTIVE mới nhất
db.customer_accounts.find({
  tenantId: "TENANT-01",
  status: "ACTIVE"
})
.sort({ createdAt: -1 })
.limit(20);
```

Một số indexes ứng viên:

```javascript
{ tenantId: 1, emailNormalized: 1 }             // unique theo tenant
{ tenantId: 1, status: 1, createdAt: -1 }        // truy vấn hot
{ expiresAt: 1 }                                // TTL nếu cần
```

Mỗi index phải có **lý do tồn tại** và kế hoạch vòng đời.

## 2. Ba lớp cần phân biệt

Trong Spring Data MongoDB có ba lớp:

| Lớp | Ví dụ | Ý nghĩa |
|---|---|---|
| Entity metadata | `@Indexed`, `@CompoundIndex` | Khai báo index trong mã Java |
| Index management API | `MongoTemplate.indexOps(...).ensureIndex(...)` | Yêu cầu MongoDB tạo index |
| MongoDB catalog | `db.collection.getIndexes()` hoặc `listIndexes()` | Trạng thái index thực tế trên server |

Ví dụ:

```java
@Indexed(name = "idx_email")
private String emailNormalized;
```

**Không tự chứng minh** rằng database đã tồn tại index `idx_email`. Nếu automatic index creation bị tắt, annotation vẫn ở đó nhưng MongoDB không nhất thiết đã tạo index.

Ngược lại, một index được DBA tạo trước đó có thể tồn tại ở MongoDB dù entity không có annotation tương ứng.

### 2.1. Những câu hỏi phải được trả lời riêng

1. Ứng dụng **muốn** những indexes nào?
2. MongoDB **đang có** những indexes nào?
3. Quy trình nào **được phép thay đổi** indexes?
4. Khi phát hiện khác nhau, hệ thống phải fail, cảnh báo hay tự sửa?
5. Ai phê duyệt thay đổi có tác động tới dữ liệu?

Đây là nền tảng của việc quản lý index tường minh.

## 3. Cơ chế auto-index creation trong Spring Data MongoDB

Spring Data MongoDB hỗ trợ phát hiện khai báo index của mapped entities và tạo index tương ứng khi tính năng auto-index creation được kích hoạt.

Theo hành vi được tài liệu Spring Data mô tả, khi bật tính năng:

- Các index được khai báo cho tập entity ban đầu có thể được xử lý khi application context khởi động.
- Entity được truy cập lần đầu trong lúc ứng dụng chạy cũng có thể kích hoạt giải quyết index metadata tương ứng.
- Việc tạo index phụ thuộc mapping context, entity discovery, cấu hình và database access.

Khi tính năng **tắt**, việc khai báo annotation không tự đồng nghĩa với thao tác `createIndexes` trên MongoDB.

### 3.1. Vì sao Spring Data đổi mặc định từ 3.0?

Bật auto-index creation trên mọi startup có thể tạo tác động không mong đợi đối với:

- Collection có dữ liệu sẵn;
- Quá trình phục hồi/recreate collection;
- Dữ liệu không đáp ứng unique constraints;
- Rủi ro performance;
- Quy trình quản trị database độc lập với ứng dụng;
- Nhiều application instances triển khai đồng thời.

Đó là lý do nên xem index creation như **một bước quản lý cấu trúc database riêng**, không chỉ là side effect của việc một service được triển khai.

### 3.2. Mặc định không phải lời hứa mãi mãi

Kiểm tra exact versions của:

- Spring Boot;
- Spring Data MongoDB;
- Spring Data Commons;
- MongoDB Java Driver;
- MongoDB Server;
- Cấu hình tùy chỉnh `MongoMappingContext`;
- `MongoTemplate`/`ReactiveMongoTemplate` sử dụng thực tế.

Nếu ứng dụng tự cấu hình mapping context, hành vi có thể khác với ứng dụng chỉ dùng Spring Boot auto-configuration.

## 4. Bật hoặc tắt bằng Spring Boot property

Với những phiên bản Spring Boot có hỗ trợ property tương ứng, có thể viết:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: false
```

Hoặc trong `application.properties`:

```properties
spring.data.mongodb.auto-index-creation=false
```

Khi bật:

```properties
spring.data.mongodb.auto-index-creation=true
```

Spring Boot có thể cấu hình index creation từ mapping metadata theo auto-configuration phù hợp.

### 4.1. Cấu hình khuyến nghị cho môi trường production

Một hướng phổ biến:

```yaml
# application-prod.yml
spring:
  data:
    mongodb:
      auto-index-creation: false
```

Sau đó tạo index qua **migration job có kiểm soát**, không để mỗi API pod tự quyết định.

Không áp dụng property này một cách mù quáng khi dự án có custom MongoDB configuration ghi đè. Phải xác nhận runtime behavior qua cấu hình và logs trong môi trường thử nghiệm.

### 4.2. Cấu hình Java `AbstractMongoClientConfiguration`

Spring Data có extension point cho index creation khi tự cấu hình MongoDB:

```java
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;

public abstract class BaseMongoConfiguration
        extends AbstractMongoClientConfiguration {

    @Override
    protected boolean autoIndexCreation() {
        return false;
    }
}
```

Đoạn trên minh họa **phương thức cần ghi đè**, không phải một cấu hình hoàn chỉnh: một subclass thực tế còn phải cung cấp database name và client theo API của phiên bản đang dùng. Tránh tạo đồng thời nhiều cấu hình MongoDB cạnh tranh trong cùng context.

### 4.3. Đừng dựa vào môi trường developer

Nếu dev dùng `auto-index-creation=true` còn production `false`, một integration test chạy ở dev có thể thành công nhờ index tự xuất hiện, trong khi production sẽ thiếu index nếu migration không chạy.

Cần **kiểm tra index contract độc lập** với việc test query trả đúng kết quả.

## 5. `@Indexed`: khai báo index trên một field

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.time.Instant;

@Document(collection = "customer_accounts")
public class CustomerAccount {

    @Id
    private String id;

    private String tenantId;

    @Field("email_normalized")
    @Indexed(name = "idx_email_normalized")
    private String emailNormalized;

    private String status;
    private Instant createdAt;

    // Constructor, getters, setters theo ứng dụng.
}
```

Đây là một index đơn trường cho `emailNormalized`, ánh xạ sang physical field `email_normalized` theo metadata.

### 5.1. Tên field Java và tên BSON có thể khác nhau

`@Field("email_normalized")` khiến field được lưu dưới tên khác. Khi khai báo index qua Spring mapping metadata, cần kiểm tra **key thật** trên MongoDB thay vì giả định nó là tên Java.

Nếu tạo index thủ công bằng collection name và raw `Document`, bạn phải tự dùng **physical BSON field names**.

### 5.2. `@Indexed` không quyết định query nào dùng index

Query planner của MongoDB chọn kế hoạch dựa trên query shape, selectivity, sort và các indexes có sẵn.

Chỉ thêm annotation không bảo đảm:

- Query sẽ nhanh hơn;
- Planner dùng index;
- `COLLSCAN` biến mất;
- Index hỗ trợ mọi sort;
- Index không làm writes chậm.

Cần dùng `explain("executionStats")` và đo read/write p95/p99.

## 6. `@CompoundIndex`: thiết kế theo query shape

Giả sử truy vấn thường xuyên:

```javascript
db.customer_accounts.find({
  tenantId: "TENANT-01",
  status: "ACTIVE"
})
.sort({ createdAt: -1 })
.limit(20);
```

Entity:

```java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customer_accounts")
@CompoundIndex(
    name = "idx_tenant_status_created_desc",
    def = "{'tenantId': 1, 'status': 1, 'createdAt': -1}"
)
public class CustomerAccount {
    // Fields và methods được lược bỏ.
}
```

Compound index thường phù hợp hơn tạo ba single-field indexes riêng nếu workload chủ yếu lọc tenant/status và sắp theo ngày.

### 6.1. Thứ tự key quan trọng

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

không tương đương về mọi query với:

```javascript
{ createdAt: -1, tenantId: 1, status: 1 }
```

Với equality predicates, sort và range queries, cần cân nhắc thứ tự khóa (ví dụ heuristic ESR) và đo bằng dữ liệu thực.

### 6.2. Index theo prefix

Compound index có thể giúp một số query có điều kiện theo leading fields, nhưng không bảo đảm tối ưu cho query chỉ lọc `status` mà không có `tenantId`.

Không xóa một single-field index chỉ vì tên field của nó cũng xuất hiện trong compound index.

### 6.3. Annotation có thể lặp

Spring Data hỗ trợ khai báo nhiều compound indexes bằng cơ chế annotation tương ứng như `@CompoundIndexes` tùy version. Tuy vậy, **nhiều index annotations không tự tạo thành một chiến lược index tốt**. Mỗi index cần có query shape, owner và yêu cầu nghiệp vụ.

## 7. Unique index: biến một annotation thành constraint

Ví dụ yêu cầu: email chỉ được duy nhất **trong cùng tenant**.

```java
@CompoundIndex(
    name = "uq_tenant_email",
    def = "{'tenantId': 1, 'emailNormalized': 1}",
    unique = true
)
```

MongoDB sẽ enforce uniqueness theo khóa compound tương ứng khi index tồn tại và dữ liệu hợp lệ.

### 7.1. Không dùng unique email toàn cục nếu nghiệp vụ cho phép trùng giữa tenant

Sai nếu cùng email được phép thuộc nhiều tenants:

```java
@Indexed(unique = true)
private String emailNormalized;
```

Định nghĩa này yêu cầu email duy nhất **trong toàn collection**, không theo tenant.

Định nghĩa đúng phải phản ánh business key, ví dụ `(tenantId, emailNormalized)`.

### 7.2. Unique không tự sửa dữ liệu trùng

Giả sử collection đã có:

```javascript
{ tenantId: "T-01", emailNormalized: "alice@example.com" }
{ tenantId: "T-01", emailNormalized: "alice@example.com" }
```

Yêu cầu tạo unique index trên hai fields có thể thất bại vì duplicate keys.

Đây là một trong những nguyên nhân khiến **auto-index creation trong startup** nguy hiểm: một deployment ứng dụng mới có thể lỗi ngay khi kết nối vào database đang tồn tại dữ liệu chưa sạch.

### 7.3. Validation trong Java không thay unique index

Một đoạn:

```java
if (!repository.existsByEmailNormalized(email)) {
    repository.save(customer);
}
```

có race condition:

```text
Request A kiểm tra: chưa tồn tại
Request B kiểm tra: chưa tồn tại
Request A insert
Request B insert
```

Nếu uniqueness bắt buộc, cần unique index thật ở MongoDB và xử lý duplicate-key exception phù hợp.

## 8. Unique index trên dữ liệu thiếu/null

Một lỗi phổ biến là bật:

```java
@Indexed(unique = true)
private String phoneNumber;
```

trong khi phần lớn documents chưa có `phoneNumber`.

Unique index thông thường có những quy tắc đối với missing/null values. Chẳng hạn, single-field unique index có thể không cho phép nhiều documents với key giá trị null/missing tương ứng.

Nếu nghiệp vụ muốn "chỉ số điện thoại **được khai báo hợp lệ** mới phải duy nhất", nên cân nhắc **partial unique index**.

### 8.1. Định nghĩa business rule trước

Các câu hỏi:

- Missing phone khác `null` không?
- String rỗng có được tính là số điện thoại không?
- Có cần chuẩn hóa số theo mã quốc gia?
- Số điện thoại được phép dùng lại sau khi account xóa mềm?
- Unique theo tenant hay toàn hệ thống?
- Phải coi số đang ở trạng thái verified hay mọi số đã nhập?

Index không thể tự suy ra câu trả lời. Trước khi tạo unique index cần audit dữ liệu cũ và quy tắc chuẩn hóa.

## 9. Partial index: giới hạn tập document được index

Một partial index chỉ chứa các documents khớp `partialFilterExpression`.

Ví dụ business rule:

> Email đã chuẩn hóa phải duy nhất giữa những account đang hoạt động (`deleted: false`) trong một tenant; account đã xóa mềm không cần chiếm khóa.

Một index MongoDB ứng viên:

```javascript
db.customer_accounts.createIndex(
  { tenantId: 1, email_normalized: 1 },
  {
    name: "uq_active_tenant_email",
    unique: true,
    partialFilterExpression: {
      deleted: false
    }
  }
);
```

Lợi ích:

- Index nhỏ hơn nếu số account đã xóa mềm nhiều;
- Khóa unique chỉ áp dụng cho records thuộc filter;
- Có thể giảm write/storage overhead so với index bao phủ toàn bộ collection.

### 9.1. Đừng hiểu partial index như full index

Truy vấn:

```javascript
db.customer_accounts.find({
  tenantId: "T-01",
  deleted: false,
  email_normalized: "alice@example.com"
});
```

có thể tận dụng partial index theo điều kiện query planner. Nhưng truy vấn không giới hạn `deleted:false` có thể cần cả records không nằm trong partial index nên không thể mặc nhiên dùng index đó mà vẫn trả kết quả đầy đủ.

### 9.2. Spring Data index API

Trong Spring Data MongoDB, `Index` và `PartialIndexFilter` có thể biểu diễn partial index:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.PartialIndexFilter;
import org.springframework.data.mongodb.core.query.Criteria;

Index index = new Index()
    .on("tenantId", Sort.Direction.ASC)
    .on("emailNormalized", Sort.Direction.ASC)
    .named("uq_active_tenant_email")
    .unique()
    .partial(
        PartialIndexFilter.of(
            Criteria.where("deleted").is(false)
        )
    );
```

Khi dùng class-based `indexOps(CustomerAccount.class)`, cần xác minh mapping physical field names của phiên bản Spring Data đang dùng và index thực trên server.

### 9.3. Partial unique cũng có giới hạn

Nếu account chuyển `deleted:true` thành `deleted:false`, MongoDB phải thêm key vào partial index; thao tác có thể bị từ chối nếu khóa trùng với active account khác.

Tạo partial unique index không có nghĩa mọi dữ liệu cũ tự được làm sạch hoặc rằng quá trình restore/update trạng thái luôn thành công.

## 10. Sparse và partial: không được nhầm

Hai tùy chọn:

- **Sparse index:** thường index documents có field được index theo quy tắc của MongoDB/index type.
- **Partial index:** index documents thỏa điều kiện filter rõ ràng.

Chúng không tương đương:

```javascript
{ phoneNumber: { $exists: true } }
```

và:

```javascript
{ verified: true, deleted: false }
```

Nếu business rule cần điều kiện thứ hai, sparse không đủ biểu đạt.

Không cấu hình `sparse:true` cùng `partialFilterExpression` trên một index vì MongoDB không cho phép tổ hợp tùy chọn đó.

## 11. TTL index: nguy cơ xóa dữ liệu ngay sau khi tạo

TTL index là dạng index đặc biệt giúp MongoDB tự xóa documents hết hạn theo thời gian.

Ví dụ một collection `login_sessions`:

```javascript
{
  _id: "SESSION-001",
  userId: "U-101",
  expiresAt: ISODate("2026-11-14T06:00:00Z")
}
```

Index:

```javascript
db.login_sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_expires_at",
    expireAfterSeconds: 0
  }
);
```

`expireAfterSeconds: 0` ở đây nghĩa là document đủ điều kiện hết hạn khi `expiresAt` đã đến, theo cơ chế TTL.

### 11.1. TTL index không chỉ tối ưu query

Nó tạo **chính sách xóa dữ liệu**. Nếu tạo TTL index trên collection có hàng triệu documents với `expiresAt` đã ở quá khứ, MongoDB TTL monitor có thể bắt đầu xóa lượng lớn dữ liệu sau khi index được tạo.

Vì vậy việc khai báo `@Indexed` với expire options rồi bật auto-index creation là thay đổi có nguy cơ về **data retention**, không chỉ performance.

### 11.2. TTL xóa bất đồng bộ

TTL monitor không bảo đảm document biến mất chính xác tại một millisecond. Dữ liệu hết hạn có thể còn tồn tại một khoảng thời gian trước khi được xử lý.

Không dùng TTL như một hệ thống scheduling chính xác tới từng giây hoặc như cơ chế authorization duy nhất. Ứng dụng vẫn phải kiểm tra hạn sử dụng ở thời điểm truy cập nếu cần bảo mật.

### 11.3. Spring Data TTL index bằng API

Ví dụ tạo tường minh:

```java
import java.time.Duration;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

Index ttl = new Index()
    .on("expiresAt", Sort.Direction.ASC)
    .named("ttl_expires_at")
    .expire(Duration.ZERO);
```

Cần xác nhận API/version và kiểu dữ liệu lưu trữ. TTL truyền thống có điều kiện về field kiểu Date/array Date và index type; một `String` chứa ngày không tự trở thành Date.

### 11.4. Không sửa TTL period như annotation change thông thường

Nếu đã có index TTL với period 30 ngày và muốn thành 7 ngày, việc thay annotation **không bảo đảm** index thực trong MongoDB tự đổi. Một số thay đổi TTL có thể cần thao tác quản trị chuyên biệt (`collMod` theo server version) hoặc quy trình recreate được hỗ trợ.

**Không drop/recreate TTL index mù quáng**, vì có thể gây đợt xóa lớn và tải I/O/replication.

## 12. Những loại index khác Spring Data có thể mô tả

Spring Data MongoDB hỗ trợ những annotation/index definitions khác nhau theo phiên bản, ví dụ:

| Loại | Mục đích | Cần lưu ý |
|---|---|---|
| `@Indexed` | Single-field index, unique/TTL và tùy chọn | Lỗi khi dữ liệu không thỏa constraint |
| `@CompoundIndex` | Compound B-tree index | Key order, prefix, sort |
| `@GeoSpatialIndexed` | Geospatial index | Geometry validity, index type |
| `@TextIndexed` | MongoDB text index | Không đồng nhất MongoDB Search/Lucene |
| `@WildcardIndexed` | Dynamic document paths | Có thể phình index |
| `@HashIndexed` | Hashed index | Hỗ trợ equality, giới hạn cho range |
| `Index`/`IndexDefinition` | Tạo index programmatic | Có thể chọn options tường minh |

Khả năng/annotation attributes cụ thể phải được xác minh với phiên bản Spring Data đang dùng.

### 12.1. MongoDB Search/Vector Search khác database B-tree indexes

Atlas Search/MongoDB Search và Vector Search có cơ chế quản lý index, định dạng và vòng đời riêng. Không coi `@Indexed` hoặc `MongoTemplate.indexOps().ensureIndex(...)` là cách tự động triển khai mọi Search/Vector Search index.

Nếu hệ thống dùng `$search` hoặc `$vectorSearch`, cần một migration/manifest tương ứng và kiểm tra indexing lag, Search Nodes, mappings và authorization.

## 13. Nested objects, maps và mapping context

Spring Data có thể phát hiện index metadata từ entity model, nhưng cấu trúc nested objects/Maps có những quy tắc riêng.

Ví dụ:

```java
@Document(collection = "products")
public class Product {
    @Id
    private String id;

    private Map<String, Object> attributes;
}
```

Keys trong `attributes` có thể tùy biến theo tenant hoặc loại sản phẩm.

### 13.1. Map keys là dữ liệu động

Không nên giả định resolver sẽ tự tạo index cho mọi key có thể xuất hiện trong `Map`. Làm vậy vừa khó dự đoán vừa không có giới hạn rõ ràng.

Spring Data index resolution có quy tắc riêng với map-like properties; wildcard indexing là một lựa chọn khi phù hợp. Nếu thực sự chỉ query `attributes.color`, index cụ thể có thể rẻ và dễ vận hành hơn wildcard toàn bộ attributes.

### 13.2. Nested fields và tên index

Khi entity được nhúng (`@Field`, nested class), index path/name có thể được xử lý dựa trên mapping metadata và scope của entity. Nếu so sánh desired/actual indexes, phải xem **BSON key thực** sau mapping.

### 13.3. Không mặc định mọi class Java đều được scan

Một class có annotation nhưng chưa được Mongo mapping context nhận diện hoặc chưa được truy cập có thể chưa có index tạo theo auto-index lifecycle.

Cần inventory entity types, không lấy số index hiện có làm bằng chứng rằng mọi annotation đã được thực thi.

## 14. Spring Data `MongoTemplate` quản lý index tường minh

API quan trọng:

```java
MongoTemplate#indexOps(...)
```

Nó trả về `IndexOperations`, cho phép:

- `ensureIndex(IndexDefinition)`;
- `getIndexInfo()`;
- `dropIndex(...)`;
- Các chức năng index management khác theo phiên bản.

Ví dụ:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexOperations;

public final class CustomerIndexDefinitions {

    public static void ensureLookupIndex(
            MongoTemplate template) {

        IndexOperations operations =
            template.indexOps(CustomerAccount.class);

        Index index = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("status", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .named("idx_tenant_status_created_desc");

        String name = operations.ensureIndex(index);

        System.out.println("Index name: " + name);
    }
}
```

### 14.1. `ensureIndex` thực sự làm gì?

Ở mức ý nghĩa, API yêu cầu MongoDB bảo đảm index có definition tương ứng theo khả năng server. Nó có thể tạo index mới nếu chưa tồn tại, hoặc kết thúc bình thường khi MongoDB đã có index tương đương.

**Không có nghĩa nó là công cụ database schema diff/migration toàn diện.** Nếu một index cùng tên có key/options khác, MongoDB có thể trả conflict; nó không nhất thiết tự động alter unique/partial/TTL/collation sang ý định mới.

### 14.2. `indexOps(Class<?>)` so với `indexOps(String)`

```java
template.indexOps(CustomerAccount.class);
```

liên hệ với entity mapping/collection metadata.

```java
template.indexOps("customer_accounts");
```

chỉ rõ collection name.

Đặc biệt khi dùng `@Field`, collection naming strategy, custom converters và inheritance, phải kiểm tra các field names thực để tránh tạo index trên đường dẫn BSON không đúng.

### 14.3. `ensureIndex` là thay đổi production

Nó có thể kích hoạt index build, sử dụng CPU/disk/I/O và gặp lỗi. Không gọi tùy tiện ở request handler, controller hoặc một scheduled job không có giới hạn.

## 15. Đọc index metadata bằng Spring Data

Một cách:

```java
import java.util.List;
import org.springframework.data.mongodb.core.index.IndexInfo;

List<IndexInfo> indexes =
    template.indexOps(CustomerAccount.class).getIndexInfo();

for (IndexInfo indexInfo : indexes) {
    System.out.println(indexInfo.getName());
}
```

`IndexInfo` phản ánh metadata theo API và version, nhưng khi cần diff chi tiết, thường phải kiểm tra `key`, `unique`, `partialFilterExpression`, `collation`, `expireAfterSeconds` và các options khác.

### 15.1. Đọc raw catalog qua MongoDB Driver

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> collection =
    template.getCollection("customer_accounts");

for (Document spec : collection.listIndexes()) {
    // Trong production cần redact metadata trước khi log.
    System.out.println(spec.toJson());
}
```

Lệnh `listIndexes()` là read-only. Output có thể tiết lộ cấu trúc dữ liệu, tên fields và những quy tắc nhạy cảm; lưu evidence ở nơi có kiểm soát.

### 15.2. Mongosh

```javascript
db.customer_accounts.getIndexes();
```

Một index có thể có các trường:

```javascript
{
  v: 2,
  key: {
    tenantId: 1,
    email_normalized: 1
  },
  name: "uq_tenant_email",
  unique: true
}
```

**Định nghĩa trên server** là bằng chứng cuối cùng rằng index thực đang tồn tại, không phải chỉ một annotation trong source.

## 16. Tại sao `ensureIndex` không thay thế versioned migration?

Giả sử release A có:

```javascript
{ tenantId: 1, email_normalized: 1 }
```

không unique.

Release B mong muốn:

```javascript
{ tenantId: 1, email_normalized: 1 }
```

unique.

Một lời gọi `ensureIndex` không thể làm biến đổi index hiện tại thành unique theo cách không cần thao tác, preflight hay xử lý dữ liệu. Có thể cần:

1. Kiểm tra duplicate keys.
2. Xử lý dữ liệu trùng theo business policy.
3. Lên kế hoạch index mới/sửa index theo hỗ trợ version.
4. Xác nhận app cũ và app mới vẫn tương thích.
5. Thực hiện migration riêng.
6. Kiểm chứng unique behavior.
7. Cập nhật migration history và đóng change.

### 16.1. Thay `@Indexed(unique=false)` thành `true` không phải migration

Annotation mới chỉ nói **muốn có** thuộc tính mới. Database index cũ không nhất thiết tự bị thay thế.

Cần diff actual vs desired và kế hoạch thay đổi.

### 16.2. Đổi tên index không đơn giản là rename file

Đổi:

```java
@Indexed(name = "idx_email_v1")
```

thành:

```java
@Indexed(name = "idx_email_v2")
```

có thể tạo một index mới cùng key/options hoặc gặp quy tắc equivalent index của MongoDB. Tùy server version và index type, không thể giả định hệ thống sẽ tự xóa tên cũ.

### 16.3. Tạo nhiều index tương đương là một chi phí

Giữ hai indexes gần giống nhau có thể tăng disk và write maintenance, dù query planner chỉ dùng một. Trước khi thêm index mới, cần inventory và phân tích overlap.

## 17. Vì sao không để mọi pod thực thi DDL khi khởi động?

Một sơ đồ deployment:

```text
                    Deployment rollout
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           Pod A          Pod B        Pod C
              │            │            │
              ├── createIndex()...
              ├────────── createIndex()...
              └──────────────── createIndex()...
                           │
                           ▼
                   MongoDB collection
```

Nếu mọi pod có auto-index creation:

- Có thể cùng gửi yêu cầu create index;
- Khi index chưa có, phát sinh thêm hoạt động điều phối;
- Khi index options lệch, có lỗi do conflict;
- Khi build index nặng, resource pressure tăng;
- Startup/readiness bị ảnh hưởng;
- Lỗi ở index migration có thể khiến application rollout thất bại;
- Nếu một số pods cũ và mới có definitions khác nhau, drift/conflicts khó kiểm soát.

### 17.1. Không có nghĩa MongoDB tạo ba bản index giống nhau

MongoDB có cơ chế nhận diện index definitions và xử lý createIndexes; yêu cầu tương đương thường không tạo ba bản vật lý giống hệt. Rủi ro chính là **các tác động DDL đồng thời, drift giữa phiên bản và thiếu quyền điều phối**, không phải lời khẳng định mỗi pod luôn tạo một bản index riêng.

### 17.2. Startup và readiness là hai ý nghĩa khác nhau

Một API service có thể sẵn sàng trả request nhưng lại bị giữ startup bởi index build hoặc bị crash vì duplicate key. Ngược lại, nếu app bỏ qua lỗi tạo index và lên READY, query có thể chậm hoặc uniqueness chưa được enforce.

Không nên kết hợp **khả năng phục vụ API** và **trạng thái schema migration** thành một điều kiện mơ hồ.

### 17.3. Tính năng tạo index lúc truy cập entity lần đầu

Rủi ro không giới hạn ở startup. Nếu auto-index creation được bật và một mapped entity chỉ được dùng khi job hiếm chạy, index creation có thể xảy ra **sau khi app đã online**.

Đây là lý do cần kiểm soát index lifecycle qua migration rõ ràng, thay vì giả định mọi thay đổi đều diễn ra đúng maintenance window lúc khởi động.

## 18. Tạo index trên collection lớn có tác động gì?

Một index build phải xử lý các documents hiện có để tạo index keys, ghi cấu trúc index và đồng bộ theo topology.

Các chi phí có thể xảy ra:

- Scan dữ liệu;
- CPU cho key extraction và sort;
- Disk I/O;
- Memory và temporary files;
- Disk headroom;
- Replication/member coordination;
- Tăng p95/p99 của query và write;
- Thời gian build kéo dài;
- Lỗi unique nếu có duplicate;
- Tương tác với backup, balancing hoặc shard operations.

### 18.1. Không đồng nhất với khóa collection kiểu phiên bản rất cũ

MongoDB index build behavior thay đổi theo release. Không tuyên bố tạo index luôn khóa toàn collection từ đầu đến cuối, hoặc rằng index build luôn không ảnh hưởng latency. Cần đọc tài liệu của version đang dùng về concurrent index builds, commit quorum và các giai đoạn khóa.

### 18.2. Disk đủ để chạy bình thường chưa chắc đủ để build index

Nếu volume còn 3% dung lượng, một index build trên collection lớn có thể không đủ temporary working space hoặc permanent footprint.

Preflight cần ước lượng index size và headroom, bao gồm rollback/rebuild.

### 18.3. Không tạo index quan trọng lần đầu đúng giờ peak

Nếu một index cần thiết cho version ứng dụng mới, hãy lên kế hoạch **tạo và xác nhận index trước khi mở traffic phụ thuộc**. Không buộc app khởi động đúng lúc cao điểm rồi mới tạo index.

## 19. Rủi ro cụ thể với unique index

Một migration unique index thường thất bại trong các tình huống:

1. Dữ liệu trùng sau nhiều năm vận hành.
2. Dữ liệu missing/null nhiều records.
3. Không chuẩn hóa case/whitespace của email.
4. Có tài khoản deleted/archived mà vẫn giữ khóa.
5. Điều kiện unique toàn cục nhầm với unique theo tenant.
6. Query/app vẫn ghi dữ liệu trùng khi đang build index.
7. Unique index trên sharded collection không phù hợp yêu cầu shard key.
8. Một index khác cùng tên nhưng options khác.
9. Collation làm hai strings được coi là tương đương theo cách business chưa chuẩn bị.

### 19.1. Tìm duplicate trước migration

Ví dụ `mongosh` dùng aggregation read-only, trên môi trường được phép:

```javascript
db.customer_accounts.aggregate([
  {
    $match: {
      email_normalized: { $type: "string" }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        email: "$email_normalized"
      },
      count: { $sum: 1 }
    }
  },
  {
    $match: {
      count: { $gt: 1 }
    }
  },
  {
    $limit: 100
  }
]);
```

Pipeline tìm **một số nhóm trùng** theo rule minh họa. Nó có thể tốn tài nguyên trên collection lớn; nên chạy theo kế hoạch, dùng dữ liệu/index phù hợp và không coi đây là toàn bộ kiểm tra. Nếu muốn unique chỉ cho `deleted:false`, bộ lọc duplicate phải khớp predicate đó.

### 19.2. Tránh sửa trùng tự động không có business policy

Nếu trùng email giữa hai account, ứng dụng có thể cần:

- Merge records;
- Chọn primary account;
- Notify người dùng;
- Giữ lịch sử/audit;
- Thực hiện GDPR/data retention actions nếu liên quan.

Không xóa documents trùng bằng `deleteMany()` chỉ để build index thành công.

### 19.3. Kiểm tra cả write paths trong cửa sổ chuyển đổi

Nếu đã dọn duplicate, nhưng ứng dụng cũ vẫn ghi records trùng trước khi index unique hoàn tất, migration có thể thất bại lại. Có thể cần deployment theo giai đoạn, validation ở app, migration gating và unique enforcement ở cuối quá trình.

## 20. Rủi ro cụ thể với TTL index

Tạo TTL index mới có thể kích hoạt xóa một lượng lớn records đã quá hạn.

Ví dụ:

```text
Collection sessions: 25 triệu documents
expireAt trước hiện tại: 12 triệu documents
```

Nếu deployment vừa bật annotation TTL và auto-index creation, TTL monitor có thể bắt đầu dọn 12 triệu documents, gây:

- Delete throughput tăng;
- Replication traffic tăng;
- Disk I/O và cache pressure;
- Tác động queries khác;
- Mất dữ liệu nếu expire policy sai.

### 20.1. Kiểm tra tập sắp bị xóa

Trước khi tạo TTL, nên đo số documents đủ điều kiện:

```javascript
db.login_sessions.countDocuments({
  expiresAt: { $lte: new Date() }
});
```

Câu lệnh có thể đắt trên dữ liệu lớn nếu thiếu index; dùng trong quy trình preflight phù hợp. Không chỉ đếm tổng: cần kiểm tra business retention của từng loại session.

### 20.2. Nếu cần xóa lượng lớn dữ liệu cũ

Có thể lập kế hoạch dọn theo lô trước/hoặc cùng migration theo quy trình kiểm soát, để tránh TTL xóa quá nhiều một lúc. Không tự tăng `expireAfterSeconds` tạm thời rồi quên giảm.

### 20.3. TTL không thay authorization

Một session đã hết hạn vẫn phải bị từ chối bởi application logic ngay cả khi TTL monitor chưa xóa document.

## 21. Rủi ro với partial, collation và index options

Một index có thể có cùng key pattern nhưng khác:

- `unique`;
- `partialFilterExpression`;
- `sparse`;
- `collation`;
- `expireAfterSeconds`;
- `hidden`;
- Các options/version-specific khác.

### 21.1. Collation thay đổi nghĩa của uniqueness

Ví dụ ứng dụng muốn `"ALICE@example.com"` và `"alice@example.com"` được coi là một email.

Một unique index với collation phù hợp có thể enforce khác một unique index theo simple binary comparison.

Nhưng phải xác nhận:

- Locale/strength;
- Field normalization;
- Existing duplicates theo collation mới;
- Driver/query collation;
- Sort behavior;
- Index constraints.

Không chỉ thêm `.unique()` và nghĩ đã đạt case-insensitive unique.

### 21.2. Partial filter và unique scope

Thay điều kiện từ:

```javascript
{ deleted: false }
```

sang:

```javascript
{ status: "ACTIVE" }
```

làm thay đổi tập documents chịu unique constraint. Cần dữ liệu và business review; không xem đây là sửa tên field đơn giản.

### 21.3. Khi index cùng tên nhưng definition khác

Không bỏ qua exception `IndexOptionsConflict` để app chạy tiếp mà không có log/cảnh báo. Nếu app mới phụ thuộc index mới và database vẫn có index cũ, có thể xuất hiện correctness/performance regression.

## 22. Rủi ro của index creation trên sharded cluster

Trong sharded MongoDB, một logical collection được phân bổ trên nhiều shards.

```text
Spring Boot application
          │
          ▼
        mongos
          │
     ┌────┼─────┐
     ▼    ▼     ▼
   Shard A B     C
```

Một tạo index có thể ảnh hưởng nhiều shards, resource sử dụng và metadata. Ngoài ra:

- Unique indexes trên sharded collection có giới hạn liên quan shard key.
- Index được tạo ở toàn collection theo semantics sharded deployment.
- Query không có shard key có thể scatter-gather dù có index tốt trên mỗi shard.
- Index build trên các shard có thể không kết thúc cùng một lúc.
- Migrating chunks/resharding có ảnh hưởng tài nguyên.
- Rollback phải xét toàn cluster.

Một annotation trong Java **không đủ ngữ cảnh** để xác nhận unique constraint phù hợp sharding topology. Preflight phải đọc đúng MongoDB sharding/index rules theo version.

## 23. Atlas và self-managed: phân chia trách nhiệm

| Hạng mục | Atlas | Self-managed |
|---|---|---|
| Tạo B-tree index | Qua driver/Atlas workflows phù hợp | Qua driver/DBA workflows |
| Index lifecycle | Team ứng dụng/DBA vẫn chịu trách nhiệm | Team ứng dụng/DBA |
| Monitoring | Atlas metrics/alerts tùy tier | Tools/observability do team vận hành |
| Storage headroom | Tier/cloud metrics | Disk/volume/container |
| Replica topology | Atlas quản lý nhiều chi tiết | Team tự điều phối |
| Search indexes | API/Atlas Search workflows | Theo Search deployment hỗ trợ |
| Authorization | Database users/Atlas roles | MongoDB users/roles |
| Migration approvals | Tổ chức tự quy định | Tổ chức tự quy định |

Managed service **không tự chọn index đúng cho mọi query và không dọn dữ liệu trùng theo nghiệp vụ**.

Nếu muốn index qua migration job, service account migration cần privileges đủ dùng, nhưng API service thông thường không nên có quyền tạo/drop indexes.

## 24. Least privilege: API service không cần quyền DDL

Khi bật auto-index creation, application identity thường cần đủ quyền tạo index.

Điều này dễ dẫn đến anti-pattern:

```text
Public-facing API
   ├── Read customer data
   ├── Write customer data
   └── Create/drop database indexes
```

Nếu ứng dụng bị compromise, quyền tạo index có thể bị lợi dụng để gây load/disk pressure hoặc thay đổi cấu trúc.

Một cách tách:

```text
API identity:
  read/write collections cần thiết
  không cấp quyền index-admin không cần thiết

Migration identity:
  createIndexes + related DDL theo scope
  chỉ dùng trong migration window

Operator identity:
  quản trị theo phê duyệt
```

### 24.1. Không phải mọi migration cần root

Tạo indexes trên vài collections không có nghĩa phải cấp `root@admin`. Dùng custom role hoặc quyền được tổ chức phê duyệt, giảm blast radius.

### 24.2. Thử trong staging bằng đúng service credentials

Nếu staging dùng root nhưng production API identity không có quyền tạo indexes, auto-index creation có thể thất bại ngay khi production deploy. Tốt nhất là tách DDL khỏi startup để service credentials không cần quyền đó.

## 25. Quy trình quản lý index tường minh

Một kiến trúc đề xuất:

```text
Source code / index manifest
           │
           ▼
Preflight / schema review
           │
           ├── Scan current indexes
           ├── Check data constraints
           ├── Check compatibility
           └── Estimate impact
           │
           ▼
Approved migration job
           │
           ├── Create new index
           ├── Verify index definitions
           ├── Verify business invariants
           └── Record migration version
           │
           ▼
Deploy application version
           │
           ▼
Observe SLO and query plans
           │
           ▼
Cleanup obsolete index in later change
```

Quan trọng nhất: **khởi chạy migration trước khi application cần index**, hoặc theo thứ tự tương thích ngược được thiết kế. Không để app mới tự làm schema migration ở cùng thời điểm API pods đều khởi động.

## 26. Thiết kế index manifest

Một nhóm có thể lưu index intentions ở version control, ví dụ YAML:

```yaml
database: commerce
collection: customer_accounts
indexes:
  - name: uq_tenant_email_active_v2
    keys:
      tenantId: 1
      email_normalized: 1
    unique: true
    partialFilterExpression:
      deleted: false

  - name: idx_tenant_status_created_desc
    keys:
      tenantId: 1
      status: 1
      createdAt: -1

owner: customer-platform
changeId: DB-INDEX-2026-041
```

Đây là **manifest minh họa do đội tự định nghĩa**, không phải file format chính thức mà Spring Data tự đọc.

Cần mô tả:

- Index name;
- Exact key fields/order;
- Options: unique, TTL, partial, collation, hidden;
- Target collection;
- MongoDB/Spring version;
- Business purpose;
- Query shapes;
- Risk level;
- Rollback plan.

### 26.1. Vì sao cần versioning?

Một index có thể thay theo release:

```text
v1: { tenantId, email }
v2: { tenantId, emailNormalized } unique
v3: partial unique chỉ cho active accounts
```

Không muốn phát triển một entity annotation mới rồi mất dấu đường chuyển đổi dữ liệu từ v1 tới v3.

## 27. Migration runner riêng thay vì `ApplicationRunner` của API

Một số dự án gọi `ensureIndex()` từ một Spring `ApplicationRunner` trong chính ứng dụng API:

```java
@Component
class IndexBootstrapRunner implements ApplicationRunner {
    // ...
}
```

Nhìn tiện vì chạy khi startup, nhưng nó vẫn gắn **DDL lifecycle với API deployment**. Nếu 30 pods khởi động, 30 runners có thể cùng hành động.

### 27.1. Phương án khuyến nghị

Đóng gói cùng codebase nhưng chạy qua **một migration task độc lập**:

```text
CI/CD
  │
  ▼
Migration approval
  │
  ▼
One-off Kubernetes Job / CLI task
  │
  ▼
MongoDB indexes verified
  │
  ▼
Roll out API pods
```

Không cần bắt buộc dùng một framework migration nhất định. Có thể dùng tool/versioned scripts theo chuẩn tổ chức, miễn là:

- Có versioning;
- Có lock/coordination khi cần;
- Có audit;
- Có preflight;
- Có rollback;
- Có idempotency;
- Có xác minh thực tế sau tạo index.

### 27.2. Tách execution mode bằng profile

Nếu cùng Spring Boot application package, có thể tạo runner chỉ kích hoạt trong profile riêng:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Profile("mongo-index-migration")
@Component
public class MongoIndexMigrationRunner
        implements ApplicationRunner {

    private final MongoIndexMigrationService migrationService;

    public MongoIndexMigrationRunner(
            MongoIndexMigrationService migrationService) {
        this.migrationService = migrationService;
    }

    @Override
    public void run(ApplicationArguments args) {
        migrationService.applyApprovedMigrations();
    }
}
```

`MongoIndexMigrationService` là **service ứng dụng phải tự hiện thực**, không phải class có sẵn trong Spring Data. Profile chỉ là một lớp điều phối: migration job vẫn cần identity riêng, lock, kiểm soát deploy và không khởi tạo cùng các API pods thông thường.

### 27.3. Profile không phải bảo đảm một instance

Nếu hai Kubernetes Jobs cùng bật profile đó, cả hai vẫn chạy. Cần orchestrator bảo đảm singleton hoặc distributed lease/migration coordination.

## 28. Ví dụ migration class tạo hai indexes

Giả định collection `customer_accounts`, Spring mapping đã cấu hình.

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexOperations;

public final class CustomerAccountIndexMigration {

    private final MongoTemplate template;

    public CustomerAccountIndexMigration(
            MongoTemplate template) {
        this.template = template;
    }

    public void apply() {
        IndexOperations ops =
            template.indexOps(CustomerAccount.class);

        Index emailUnique = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("emailNormalized", Sort.Direction.ASC)
            .named("uq_tenant_email_v2")
            .unique();

        Index statusSort = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("status", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .named("idx_tenant_status_created_desc");

        ops.ensureIndex(emailUnique);
        ops.ensureIndex(statusSort);
    }
}
```

**Ví dụ này chỉ minh họa API.** Trên production, gọi `apply()` phải được đặt sau các bước:

1. Kiểm tra duplicate tenant/email.
2. Kiểm tra names/options đã tồn tại.
3. Xác minh index build được hỗ trợ.
4. Có đủ storage/headroom.
5. Đã được phê duyệt.
6. Có monitoring và rollback.
7. Postcondition xác nhận index đang tồn tại đúng spec.

Không gọi `apply()` trực tiếp trong constructor/service initialization.

### 28.1. Chú ý tới field alias

Nếu entity map `emailNormalized` thành `email_normalized`, phải xác nhận actual index key từ catalog. Khi cần tuyệt đối chính xác, dùng migration script dựa trên **BSON field names đã quyết định**.

### 28.2. Tạo index không phải logic trong transaction business

Index DDL có các giới hạn riêng và thường không được coi là một phần của transaction nghiệp vụ như cập nhật order/payment. Không thiết kế “bắt đầu transaction → tạo index → cập nhật 50.000 documents → commit” như thể tất cả là một đơn vị atomic.

## 29. Dùng `MongoPersistentEntityIndexResolver` như nguồn metadata

Nếu vẫn muốn các annotation là nguồn khai báo nhưng không muốn tự động tạo index mỗi startup, Spring Data cung cấp `MongoPersistentEntityIndexResolver` để **đọc index definitions từ mapping context**.

Ví dụ khái niệm:

```java
import org.springframework.data.mongodb.core.index.IndexDefinition;
import org.springframework.data.mongodb.core.index.IndexOperations;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;

var mappingContext =
    mongoTemplate.getConverter().getMappingContext();

var resolver =
    new MongoPersistentEntityIndexResolver(mappingContext);

IndexOperations indexOps =
    mongoTemplate.indexOps(CustomerAccount.class);

for (IndexDefinition definition :
        resolver.resolveIndexFor(CustomerAccount.class)) {

    indexOps.ensureIndex(definition);
}
```

Cách này giúp giữ index declarations gần domain model nhưng **đưa thời điểm thực thi** về migration job có kiểm soát. Code chi tiết/overloads cần phù hợp với Spring Data version cụ thể.

### 29.1. Resolver không tự là migration framework

Resolver giúp tìm index metadata, không tự:

- So sánh tất cả options với catalog;
- Lập kế hoạch xóa index cũ;
- Dọn duplicate data;
- Ước tính index build duration;
- Bảo vệ khỏi race giữa nhiều migration runners;
- Bảo đảm rollback;
- Quản lý version schema;
- Xác nhận postconditions.

Nếu ứng dụng có nhiều versions chạy đồng thời, annotation definitions khác nhau có thể làm drift. Cần một **versioned desired-state contract**.

### 29.2. Không dùng mọi entity tự động khi có scope đặc biệt

Một package có thể chứa entities phục vụ nhiều databases hoặc tenant collections. Resolver trên tất cả entities mà không phân biệt target có thể tạo indexes ở sai nơi.

Phải xác định collection/database scope của migration và có allowlist.

## 30. Preflight: so sánh desired indexes với actual indexes

Trước migration, lấy hai tập:

```text
Desired indexes (source/manifest)
            │
            ▼
     Normalize definitions
            │
            ├── key pattern + order
            ├── name
            ├── unique
            ├── partial filter
            ├── TTL
            ├── collation
            └── other options
            │
            ▼
Actual indexes (listIndexes)
            │
            ▼
       Compare
            │
     ┌──────┼───────────┐
     ▼      ▼           ▼
   MATCH  MISSING    CONFLICT
     │      │           │
     │      ▼           ▼
   PASS   APPROVE     BLOCK RELEASE
          CREATE      + DESIGN MIGRATION
```

Không biến `CONFLICT` thành một lệnh tự drop rồi create lại.

### 30.1. So sánh theo semantics, không chỉ JSON string

MongoDB có các field metadata do server sinh (`v`, `ns`,...) và những defaults có thể không xuất hiện trong spec. Việc chuẩn hóa phải xét **ngữ nghĩa key pattern/options**, không so toàn bộ JSON raw theo thứ tự key không liên quan.

Nhưng **thứ tự fields trong index key pattern** là có ý nghĩa; không được sort alphabetic key fields để so sánh rồi làm mất thứ tự compound index.

### 30.2. MISSING không phải luôn “tạo ngay”

Nếu index thiếu nhưng collection chứa nhiều dữ liệu, cần:

- Data constraint check;
- Performance/capacity estimate;
- Permission;
- Change window;
- Approval;
- Owner;
- Fallback.

### 30.3. ORPHAN/EXTRA index

Index thực có nhưng không nằm trong manifest có thể là:

- Legacy index cần bỏ;
- Index do DBA tạo;
- Index unique/TTL phục vụ chính sách khác;
- Index hỗ trợ report/DR hiếm dùng;
- Index do release khác quản lý.

Không tự xóa mọi index “ngoài manifest”. Đánh giá ownership và query usage trước.

## 31. Bản ghi lịch sử migration

Một collection quản lý migration có thể có:

```javascript
{
  _id: "mongo-index-2026-041",
  collection: "customer_accounts",
  state: "COMPLETED",
  appliedAt: ISODate("2026-11-14T04:00:00Z"),
  definitionHash: "sha256:...",
  appliedBy: "migration-job",
  changeId: "DB-INDEX-2026-041"
}
```

Đây là ví dụ **schema nội bộ do ứng dụng tự thiết kế**. Một migration framework thực có thể có collection/format khác.

### 31.1. Khi nào ghi `COMPLETED`?

Chỉ sau khi:

- MongoDB xác nhận index build/create step hoàn tất theo semantics triển khai;
- Đã đọc lại actual index spec;
- Postconditions đạt;
- Không có conflict;
- Các dữ liệu/constraints liên quan được xác nhận.

Không ghi marker hoàn tất trước `ensureIndex`, vì job có thể chết sau khi ghi marker nhưng trước khi index tồn tại.

### 31.2. Có thể crash sau khi tạo index nhưng trước khi ghi marker

Đây là trạng thái **cần resume an toàn**:

```text
ensureIndex success
       │
    Job crashes
       │
Migration record not COMPLETED
       │
       ▼
Next run:
  inspect actual index
  if exact desired spec exists → mark completed
  else → handle conflict / resume according to policy
```

Đó là lý do migration phải idempotent ở **mức desired state**, không đơn giản thử chạy lại toàn bộ bất kể catalog.

### 31.3. Migration marker không ngăn race

Nếu hai jobs đọc cùng trạng thái `PENDING` rồi đồng thời sửa, marker đơn thuần không phải distributed lock. Cần external coordination hoặc lease có logic expiry/fencing khi môi trường cho phép concurrent executors.

## 32. Tách quyền database users

Một mô hình:

| Identity | Quyền cần thiết | Không nên cấp |
|---|---|---|
| API service | CRUD collections nghiệp vụ | `createIndex`, `dropIndex`, quản trị users |
| Index migration job | Index DDL cho đúng database/collections | `root` toàn cluster nếu không cần |
| Monitoring service | Read-only status/metrics | Ghi customer data |
| Backup agent | Backup/restore privileges theo tool | Business write quyền rộng |
| DBA break-glass | Quyền quản trị có kiểm soát | Dùng làm API credentials |

Nếu API startup không còn phải tạo indexes, service account có thể bỏ quyền `createIndex` theo thiết kế. Đây là một lợi ích bảo mật đáng kể.

### 32.1. Chạy migration bằng secrets riêng

Không chia sẻ mật khẩu admin dài hạn vào ứng dụng thông thường. Migration credentials có thể được cấp trong thời gian giới hạn qua vault/workload identity và được thu hồi khi hoàn tất.

### 32.2. Audit ai thay index

Cần trace:

```text
Change ID
DB/collection/index name
Executor identity
Timestamp
Desired spec hash
Before/after evidence
Approval
Outcome
```

Không ghi raw credential hoặc connection string vào logs.

## 33. Đặt thứ tự deploy: expand → migrate → switch → contract

Ví dụ thay index email từ bản cũ sang index mới:

```text
Release N: app dùng email legacy
              │
              ▼
Expand:
  thêm field emailNormalized, app ghi cả hai
              │
              ▼
Backfill:
  chuẩn hóa dữ liệu cũ có revision guard
              │
              ▼
Preflight:
  kiểm tra duplicates/normalization
              │
              ▼
Index migration:
  tạo uq_tenant_email_normalized
              │
              ▼
Switch:
  app queries/validation dùng emailNormalized
              │
              ▼
Observe:
  đo correctness/performance
              │
              ▼
Contract:
  bỏ legacy index ở release sau
```

### 33.1. Không drop index cũ trước khi app mới sẵn sàng

Nếu app version cũ vẫn chạy trong rolling deployment, nó có thể cần index cũ. Xóa trước có thể gây p99 regression, timeouts và quá tải CPU.

### 33.2. Dữ liệu mới vẫn đang được ghi khi backfill

Nếu backfill đọc bản cũ rồi ghi `emailNormalized`, có thể overwrite giá trị mới do app cập nhật. Cần source revision/update guards và chính sách dual-write/CDC khi thích hợp.

### 33.3. Contract là một change riêng

Sau khi xác minh tất cả clients/queries đã chuyển và không còn rollback path cần index cũ, mới lên lịch drop. Không gộp create index mới và drop index cũ trong một bước không thể quan sát/rollback dễ dàng.

## 34. Xử lý index name conflicts

Một lỗi có thể xảy ra:

```text
Existing index:
  name: idx_status_created
  key: { status: 1, createdAt: -1 }

Desired:
  name: idx_status_created
  key: { tenantId: 1, status: 1, createdAt: -1 }
```

Đổi cấu trúc key nhưng giữ tên có thể gây conflict khi tạo.

### 34.1. Không tự động drop index name cũ

Nếu ngay lập tức:

```javascript
db.customer_accounts.dropIndex("idx_status_created");
```

truy vấn cũ có thể mất index. Nên:

1. Dùng tên mới có version/scope rõ.
2. Tạo index mới có chủ đích.
3. Kiểm tra query plan.
4. Chuyển application.
5. Quan sát.
6. Xóa index cũ sau khi được phê duyệt.

### 34.2. Names phải ổn định và có mục đích

Một naming convention:

```text
uq_tenant_email_active_v2
idx_tenant_status_created_desc
ttl_session_expires_at
idx_geo_store_location
```

Không nhất thiết phải mã hóa mọi thứ vào tên, nhưng cần phân biệt chức năng và tránh trùng tên ngoài ý muốn.

### 34.3. Không dùng tên index làm business key

Index name là metadata quản trị; ứng dụng không nên coi đó là định danh nghiệp vụ có thể trả về frontend. Nếu code sử dụng `hint("idx_...")`, việc đổi tên có thể ảnh hưởng query và phải được review.

## 35. Hidden index để kiểm tra khả năng bỏ index

MongoDB hỗ trợ **hidden index** theo phiên bản để query planner bỏ qua index mà chưa xóa index structure.

Ví dụ **thao tác thay đổi, chỉ làm khi được phê duyệt**:

```javascript
db.customer_accounts.hideIndex("idx_tenant_status_created_desc");
```

Khi hidden:

- Index không được planner lựa chọn;
- Không thể ép dùng hidden index bằng `hint`;
- Index **vẫn được duy trì khi ghi**;
- Index **vẫn chiếm dung lượng**;
- Unique constraint vẫn được áp dụng nếu index unique;
- TTL expiration vẫn diễn ra nếu là TTL index.

### 35.1. Hidden không đo được write gain khi drop

Một hidden index vẫn có chi phí write maintenance, nên:

```text
Before hide:
  Reads use index; writes maintain index.

After hide:
  Reads cannot use index; writes still maintain it.

After drop:
  Reads cannot use index; writes no longer maintain it.
```

Hidden test hữu ích để đánh giá **read regression** trước khi drop, không phải để chứng minh write throughput sẽ cải thiện bao nhiêu sau drop.

### 35.2. Không hide hoặc drop `_id` index

`_id` index có quy tắc đặc biệt và không thể bị xử lý như secondary index thông thường.

### 35.3. Hidden cũng là DDL

`hideIndex`/`unhideIndex` thay đổi hành vi query planner và có thể gây tăng COLLSCAN. Không coi đó là lệnh quan sát an toàn để chạy tùy ý trên production.

## 36. Đo index usage trước khi drop

Trong `mongosh`, có thể đọc:

```javascript
db.customer_accounts.aggregate([
  { $indexStats: {} },
  {
    $project: {
      name: 1,
      key: 1,
      host: 1,
      accesses: 1
    }
  }
]);
```

`$indexStats` cung cấp thông tin lượt sử dụng index theo ngữ nghĩa và scope MongoDB.

### 36.1. Zero access chưa chắc index vô dụng

Các lý do:

- Server restart gần đây;
- Index mới tạo;
- Batch job chưa chạy;
- Primary khác/secondary dùng index;
- Tenant lớn chưa gửi traffic;
- Index phục vụ unique/TTL;
- Index chỉ dùng lúc failover;
- Thời gian đo quá ngắn.

Không drop chỉ vì `accesses.ops=0` trong một ngày.

### 36.2. Mốc `since` quan trọng

Đọc:

```text
accesses.ops = 0
accesses.since = 5 minutes ago
```

khác xa:

```text
accesses.ops = 0
accesses.since = 90 days ago
```

Chỉ số có thể reset sau restart hoặc thao tác quản lý index. Với replica set/sharded cluster, phải nhìn những nodes/shards phù hợp.

### 36.3. Query plans và metrics mới quyết định

Kết hợp:

- `getIndexes()`;
- `$indexStats`;
- `explain("executionStats")`;
- Slow query patterns;
- Read/write p95/p99;
- Index size;
- CPU/I/O/working set.

Index được dùng ít nhưng giúp một truy vấn quản trị critical tránh scan hàng trăm triệu documents vẫn có thể phải giữ.

## 37. Test index contract: xác minh actual catalog

Một integration test có thể dùng `MongoTemplate`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.IndexInfo;

class CustomerAccountIndexContractTest {

    @Autowired
    MongoTemplate template;

    @Test
    void shouldHaveRequiredIndex() {
        List<IndexInfo> infos =
            template.indexOps(CustomerAccount.class)
                    .getIndexInfo();

        assertThat(infos.stream()
            .map(IndexInfo::getName))
            .contains("uq_tenant_email_v2");
    }
}
```

Ví dụ là **khung kiểm tra**, muốn chạy được cần cấu hình test framework/dependencies/database và data lifecycle của dự án.

### 37.1. Test tên index thôi chưa đủ

Một index cùng tên có thể không đúng key/options trong một tình huống migration conflict. Contract test chất lượng cần so:

```text
name
key pattern and order
unique
partialFilterExpression
expireAfterSeconds
collation
hidden / other relevant options
```

Có thể dùng `listIndexes()` để lấy raw catalog rồi normalize.

### 37.2. Test trên MongoDB thực khi cần tính năng index

Mock `MongoTemplate` có thể trả về một danh sách giả, nhưng không chứng minh MongoDB thực sự enforce uniqueness/TTL/collation.

Testcontainers hoặc một MongoDB test cluster được quản lý phù hợp giúp kiểm tra:

- Duplicate-key enforcement;
- Index build errors;
- Actual index catalog;
- Partial unique semantics;
- TTL behavior qua kỳ quan sát;
- Query explain.

Với sharding, standalone test container không chứng minh các giới hạn unique index/shard key.

### 37.3. Không dùng test xóa dữ liệu production

Integration tests tạo collection thử riêng, có cleanup, không trỏ tới production credentials.

## 38. Test đảm bảo auto-index creation bị tắt

Trong test môi trường tương ứng, cần xác nhận:

1. Cấu hình production thực sự có `auto-index-creation=false`.
2. API identity không cần quyền DDL.
3. Khởi động application không chạy create index ngoài dự kiến.
4. Migration job là nguồn duy nhất cho DDL được phê duyệt.
5. Index contract test xác nhận indexes đã được tạo trước API rollout.

### 38.1. Không chỉ grep YAML

Spring Boot có config precedence: environment variables, command line args, profiles, external config và custom beans có thể ghi đè. Việc một tệp YAML chứa `false` không chứng minh runtime mapping context đã tắt.

### 38.2. Kiểm tra runtime theo cách an toàn

Trong staging, có thể bật logging/audit có kiểm soát hoặc dùng quyền truy cập read-only để quan sát catalog trước và sau startup. Không log raw secrets hoặc bật profiler quá rộng.

### 38.3. Nếu dùng ReactiveMongoTemplate

Spring Data Reactive có APIs và lifecycle khác Sync `MongoTemplate`; không copy nguyên ví dụ blocking sang reactive/event-loop. Quy trình migration riêng có thể dùng client/driver phù hợp với nền tảng và hoàn thành bằng cơ chế subscription/await được kiểm soát.

## 39. Tình huống lỗi 1: ứng dụng restart thất bại vì duplicate

Tình huống:

```text
Release 1: không có unique email index
Release 2: thêm @Indexed(unique=true)
Auto index creation: true

Production data:
  User A: email = "alice@example.com"
  User B: email = "alice@example.com"
```

Khi new app khởi động, yêu cầu create unique index thất bại.

### 39.1. Không nên sửa thế nào?

- Không xóa ngẫu nhiên một account trùng;
- Không tạm cấp root cho API;
- Không disable validation để deployment báo xanh;
- Không bỏ qua lỗi rồi coi constraint đã được enforce.

### 39.2. Quy trình xử lý đúng

1. Tạm dừng rollout.
2. Giữ app cũ phục vụ nếu tương thích.
3. Phân tích business rule của uniqueness.
4. Trích xuất duplicate groups theo scope.
5. Xây remediation data có owner.
6. Backfill/normalize nếu cần.
7. Tạo unique index bằng migration có phê duyệt.
8. Xác minh unique enforcement.
9. Deploy app mới.
10. Theo dõi và đóng finding.

## 40. Tình huống lỗi 2: deployment chậm vì index build

Tình huống:

```text
Collection: 100 million documents
Index annotation mới: { tenantId: 1, createdAt: -1 }
Pods: 25
auto-index-creation: true
```

Khi rolling deployment:

- Start time tăng;
- Database disk I/O tăng;
- Read/write p99 tăng;
- Một số pods fail readiness;
- Kubernetes restart thêm pods và khiến rollout nhiễu.

### 40.1. Phân biệt nguyên nhân

Không phải cứ 25 pods là MongoDB build 25 indexes vật lý. Nhưng một index build thật trên collection lớn có thể đã đủ gây resource pressure, trong khi nhiều clients đồng thời khiến điều phối và logs khó đọc.

### 40.2. Phòng ngừa

- Tạo index trước qua migration window;
- Đo CPU/disk/index build progress;
- Chờ index ready;
- Sau đó mới rollout app;
- Không gắn DDL vào app readiness;
- Có alert/stop condition.

## 41. Tình huống lỗi 3: index không được đổi dù annotation đã sửa

Mã cũ:

```java
@Indexed(name = "idx_email", unique = false)
private String email;
```

Mã mới:

```java
@Indexed(name = "idx_email", unique = true)
private String email;
```

Ứng dụng restart, nhưng index trong MongoDB vẫn không có unique hoặc migration báo conflict.

**Bài học:** thay Java annotation không phải cách nâng cấp một index hiện hữu khi options không tương thích. Phải quản lý chuyển đổi bằng migration cụ thể, dữ liệu sạch và postcondition.

## 42. Tình huống lỗi 4: TTL xóa lịch sử không mong muốn

Một entity archival có:

```java
// Ví dụ khai báo TTL cần xác nhận semantics/version.
@Indexed(expireAfterSeconds = 0)
private Instant archivedAt;
```

Nếu business định giữ hồ sơ vô thời hạn, việc đưa `archivedAt` vào TTL index có thể làm hồ sơ cũ đủ điều kiện xóa.

### 42.1. Cần xác nhận gì?

- Field nào thực sự là expiry timestamp?
- Retention policy bao lâu?
- Records hiện có nào đủ điều kiện xóa?
- Index có thể tạo delta lớn về delete throughput không?
- Có backup/recovery point không?
- Pháp lý/compliance có chấp thuận không?

Với Spring Data phiên bản mới, một số TTL annotation attributes có thể được thay thế/bổ sung; điều quan trọng là **semantics MongoDB thực**, không chỉ thuộc tính Java.

## 43. Tình huống lỗi 5: staging có index, production thiếu index

Trong dev:

```properties
spring.data.mongodb.auto-index-creation=true
```

Trong production:

```properties
spring.data.mongodb.auto-index-creation=false
```

Một repository query chạy rất nhanh trên dev vì annotation tự tạo compound index. Production chưa chạy migration nên query thành `COLLSCAN`.

### 43.1. Cách tránh

- Mỗi release có danh sách required index specs.
- CI/staging chạy migration chủ động.
- Contract test đọc index catalog.
- Production preflight xác nhận index trước deploy.
- Giám sát slow queries và query plans.
- Không tin rằng code entity tự sinh index trong mọi environment.

## 44. Tình huống lỗi 6: nhiều app versions có metadata index khác nhau

Trong rolling rollout:

```text
Old pods: @CompoundIndex(name="idx_v1", def="...")
New pods: @CompoundIndex(name="idx_v2", def="...")
```

Nếu cả hai bật auto-index creation, database có thể xuất hiện index v1 và v2 cùng tồn tại hoặc các yêu cầu xung đột. Khi rollback app, metadata kỳ vọng lại khác.

### 44.1. Phương án tốt hơn

- Migration job quyết định index state;
- Old/new apps tương thích với index state trong giai đoạn overlap;
- Create-new trước;
- Deploy-new;
- Theo dõi;
- Drop-old trong release sau;
- Không để startup cũ tự “khôi phục” index cũ.

## 45. Kế hoạch rollback một thay đổi index

Không có một rollback chung cho mọi loại index.

| Thay đổi | Rollback khả thi? | Rủi ro |
|---|---|---|
| Thêm performance index | Drop index sau đánh giá | Query plan/maintenance, resource |
| Ẩn index | Unhide index | Ngay trong lúc hidden có thể gây query chậm |
| Drop index | Recreate index | Rebuild tốn thời gian/disk |
| Thêm unique index | Drop chỉ khi được phê duyệt | Mất invariant, dữ liệu có thể trùng |
| Thêm TTL index | Drop/chỉnh tùy quy trình | Dữ liệu đã xóa **không tự quay lại** |
| Đổi partial filter | Migration mới | Unique scope và data semantics đổi |
| Đổi collation | Migration mới | Query/uniqueness thay đổi |
| Thay shard-related index | Giới hạn theo sharding | Có thể không hạ được trực tiếp |

### 45.1. Rollback code khác rollback dữ liệu

Nếu TTL đã xóa 2 triệu documents, revert Java annotation **không phục hồi** 2 triệu documents. Nếu unique constraint bị drop, dữ liệu trùng tạo trong khoảng đó có thể làm recreate unique thất bại.

Vì thế cần backup, change gates và kiểm tra hậu quả không đảo ngược.

### 45.2. Rebuild index không tức thì

Nếu drop nhầm index trên collection lớn, để tạo lại có thể cần nhiều thời gian và tài nguyên; không đặt RTO dựa trên giả định `createIndex()` luôn hoàn tất trong vài giây.

## 46. Index size và write cost

Mỗi index có chi phí storage và maintenance.

Một hệ có:

```text
Collection size: 40 GiB
Total index size: 26 GiB
Writes: 3.000/s
```

Nếu thêm nhiều compound indexes chỉ vì “mỗi query một index”, total index size/working set và write I/O có thể tăng đáng kể.

### 46.1. Dùng thống kê index

Mongosh:

```javascript
db.customer_accounts.stats({
  scale: 1024 * 1024
});
```

Có thể xem `totalIndexSize`, `indexSizes`, `nindexes` theo output và version.

### 46.2. Index không phải toàn bộ disk

Storage engine, journal, metadata, snapshots, logs và backup có footprints riêng. Phải tính capacity trên toàn cluster, kể cả replica copies.

### 46.3. Tối ưu theo truy vấn nóng

Một index mới nên gắn với:

```text
Query shape
Frequency
Read p95/p99
Docs/keys examined
Expected benefit
Write penalty
Disk size
Operational owner
```

Không tự tạo index cho mọi Java property chỉ để repository query nào cũng có “index riêng”.

## 47. MongoDB query plan là nguồn xác minh hiệu năng

Một query:

```javascript
db.customer_accounts.find({
  tenantId: "T-01",
  status: "ACTIVE"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Quan sát:

- `winningPlan`;
- `IXSCAN`/`COLLSCAN` hoặc stages tương ứng;
- `totalDocsExamined`;
- `totalKeysExamined`;
- `nReturned`;
- `executionTimeMillis`;
- Blocking sort;
- Disk/memory side effects trong workload.

### 47.1. `explain` không thay load test

Một lần `explain` không bao gồm mọi driver pool wait, network RTT, concurrent writes, cache state và p99 application traffic.

### 47.2. Index mới không bảo đảm planner chọn nó

Query planner cân nhắc selectivity, sort và data distribution. Nếu index được tạo nhưng query vẫn dùng đường cũ, cần phân tích plan, không tiếp tục tạo thêm index mù quáng.

## 48. Thiết kế migration dry-run

Một migration tool có thể có hai chế độ:

```text
DRY_RUN:
  read desired specs
  read actual specs
  compute differences
  validate permissions/capacity
  output plan
  NO write operations

APPLY:
  require approval/change ID
  acquire migration ownership
  execute steps
  verify postconditions
  record migration result
```

### 48.1. Dry-run không phải chỉ in lệnh sẽ chạy

Một dry-run hữu ích còn kiểm:

- Current collection name/database;
- Current index names/options;
- Existing data duplicates;
- TTL expiration candidates;
- Resource headroom;
- Sharding/topology constraints;
- Driver/Server version;
- Concurrent deployment risk;
- Rollback availability.

### 48.2. Phân loại outcome

| Outcome | Ý nghĩa | Hành động |
|---|---|---|
| MATCH | Actual index đúng spec | PASS |
| MISSING | Chưa có | Lập kế hoạch tạo |
| CONFLICT | Same name/key khác options quan trọng | BLOCK + manual migration |
| UNSUPPORTED | Feature/version không hỗ trợ | BLOCK |
| DATA_INVALID | Duplicate/invalid data | Remediate data |
| RESOURCE_RISK | Thiếu disk/capacity | Chọn window/tăng capacity |
| EXTRA | Có index ngoài manifest | Điều tra owner, không auto drop |

## 49. Lược đồ phối hợp CI/CD

Một pipeline kiểm soát có thể:

```text
Pull request
   │
   ├── Review index manifest
   ├── Review query/load impact
   └── Approve migration
           │
           ▼
      Integration tests
           │
           ▼
      Staging migration
           │
           ▼
      Staging app rollout
           │
           ▼
      Load/failure tests
           │
           ▼
      Production preflight
           │
           ▼
      One-off migration job
           │
           ▼
      Verify actual indexes
           │
           ▼
      Application rollout
           │
           ▼
      Monitor / rollback gate
```

### 49.1. Không dùng CI credential toàn quyền dài hạn

Migration runner nên nhận credential ngắn hạn/được quản lý và audit. Sau migration, API app tiếp tục chạy với identity ít quyền hơn.

### 49.2. Không đánh dấu release thành công trước khi index ready

Nếu một API version mới cần compound index để đạt p99, phải đợi actual index sẵn sàng theo MongoDB procedure, không chỉ nhận HTTP 200 từ deployment pipeline.

## 50. Lưu ý với nhiều tenants và nhiều collections

Một mô hình multi-tenant có thể dùng:

1. Shared database/shared collection với `tenantId`.
2. Database per tenant.
3. Collection per tenant.
4. Hybrid topology.

### 50.1. Shared collection

Index thường cần tenant field trong compound key để hỗ trợ query authorization và performance.

```javascript
{ tenantId: 1, email_normalized: 1 }
```

Không quên tenant predicate ở application query; index không tự cung cấp row-level authorization.

### 50.2. Collection per tenant

Nếu có hàng nghìn collections động, auto-index creation dựa trên một static entity class không tự bảo đảm mọi tenant collection đều có đúng indexes.

Phải thiết kế migration enumeration/ownership, rate limiting và lifecycle khi tenant mới được tạo.

### 50.3. Database per tenant

`MongoTemplate`/`MongoDatabaseFactory` có thể định tuyến databases động. Migration phải áp dụng đúng target database, không chạy một lần trên default database rồi coi mọi tenants đã có index.

### 50.4. Tenant onboarding cần schema gate

Khi tạo tenant mới:

```text
Provision database/collection
       │
       ▼
Apply required indexes
       │
       ▼
Verify index catalog
       │
       ▼
Enable tenant traffic
```

Không đưa user traffic vào collection mới chưa có required indexes nếu query SLO hoặc uniqueness phụ thuộc chúng.

## 51. Kiểm tra ứng dụng với Readiness và Health

Một yêu cầu thực tế là app không được phục vụ request nếu thiếu index bắt buộc. Nhưng không nên biến readiness probe thành một bộ migration DDL.

### 51.1. Read-only index contract check

Có thể tạo một bước startup **chỉ đọc** catalog để xác nhận:

```text
Required index exists and matches → READY
Required index missing/conflict → NOT READY + alert
```

Điều kiện này cần cân nhắc:

- Readiness probe không nên gọi `listIndexes` liên tục mỗi vài giây trên hàng nghìn pods;
- Cache kết quả trong một bước startup/hệ monitoring;
- Không chặn toàn hệ chỉ vì một index không critical nếu policy cho phép degrade;
- Có alert và owner;
- Không tự sửa index trong readiness handler.

### 51.2. Fail closed với correctness constraints

Nếu một service phụ thuộc uniqueness để tránh trùng giao dịch, việc index thiếu có thể là **blocker**. Với performance index, đội vận hành có thể quyết định tạm degraded mode trong điều kiện giới hạn.

Cần phân loại severity trước khi viết health gate, không coi mọi index như nhau.

## 52. Spring Data Repositories không làm index tự tồn tại

Repository method:

```java
public interface CustomerAccountRepository
        extends MongoRepository<CustomerAccount, String> {

    Optional<CustomerAccount> findByTenantIdAndEmailNormalized(
        String tenantId,
        String emailNormalized
    );
}
```

có thể được Spring Data chuyển thành MongoDB query phù hợp. Nhưng **khai báo repository method không đồng nghĩa đã tạo index** cho `(tenantId, emailNormalized)`.

Điều cần làm:

- Thiết kế index theo query shape;
- Tạo qua migration;
- Kiểm tra `getIndexes` và explain;
- Đo dưới tải;
- Test uniqueness nếu là invariant.

### 52.1. `save()` không phải lúc nào là insert đơn giản

Spring Data `save()` có semantics insert hoặc replace/update theo entity id và mapping. Nếu một unique index được thêm vào, các lệnh save có thể bắt đầu trả duplicate key errors theo constraint. Phải có exception handling và mapping đúng ra business errors.

### 52.2. Duplicate key exception

Spring DAO có thể chuyển exception MongoDB sang dạng như `DuplicateKeyException` trong Spring DataAccessException hierarchy theo ngữ cảnh. Xử lý nó thành business conflict khi phù hợp, không retry vô hạn.

Ví dụ:

```java
try {
    repository.save(account);
} catch (org.springframework.dao.DuplicateKeyException ex) {
    throw new IllegalStateException(
        "Account business key already exists",
        ex
    );
}
```

Đây là ví dụ về luồng xử lý; trong API thực nên trả response/domain error có kiểm soát, không lộ raw MongoDB exception/PII.

## 53. Các anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách làm tốt hơn |
|---|---|---|
| Bật auto-index production vì tiện | DDL khi startup | Migration job riêng |
| Mọi pod tự gọi `ensureIndex` | DDL đồng thời, drift | One-off coordinated migration |
| `@Indexed(unique=true)` trên data cũ chưa kiểm | Duplicate error | Audit/remediate trước |
| Dùng unique email toàn cục trong multi-tenant | Chặn account hợp lệ | Compound tenant key |
| Không kiểm null/missing | Unique index creation lỗi | Partial/business semantics |
| Sửa unique/TTL option chỉ qua annotation | Index catalog không đổi | Explicit migration |
| Quên TTL có thể xóa records | Mất dữ liệu | Retention preflight |
| `@Indexed` nghĩa index chắc chắn tồn tại | Production thiếu index | Catalog contract check |
| Dùng API root account | Blast radius lớn | Least privilege |
| Gọi `ensureIndex` trong HTTP request | Tải bất ngờ/latency | Migration phase |
| Gọi `ensureIndex` trong liveness probe | Restart loop | Read-only health checks |
| Drop index khi có conflict | Query/correctness regression | Versioned staged migration |
| Drop index không có rollback | Rebuild lâu | Change window |
| Xóa unique/TTL theo `$indexStats=0` | Mất invariant | Phân biệt chức năng |
| Không đo build headroom | Disk full/index fail | Capacity preflight |
| Test chỉ trên empty collection | Không thấy duplicate/load | Realistic staging data |
| Staging bật auto, prod tắt | Index drift | Same migration process |
| So index names mà bỏ key/options | Sai contract | Full semantic comparison |
| Không quan tâm physical `@Field` name | Tạo sai index | Verify actual BSON keys |
| Coi index như transaction change | Rollback giả | DDL runbook |
| Tạo nhiều single-field indexes | Write/storage penalty | Query-shape driven |
| Hiểu hidden index là giảm write | Sai, hidden vẫn maintained | Dùng để thử read impact |
| Không tính sharding uniqueness | Constraint có thể không hợp lệ | Version-specific sharded rules |
| Không quản lý tenant collections động | Một số tenant thiếu index | Provisioning schema gate |
| Coi Search index như B-tree `@Indexed` | Thiếu lifecycle/cost | Search-specific migration |
| Log raw index diff chứa metadata nội bộ | Lộ schema/network | Redact logs |
| Ghi migration marker trước khi tạo xong | Bỏ sót index | Postcondition first |
| Không có owner/alert | Không ai xử lý rollout lỗi | Operational runbook |

## 54. Bài tập thực hành

### Bài 1 — Phân biệt annotation và actual index

Một class có:

```java
@Indexed(name = "idx_email")
private String email;
```

Production có `auto-index-creation=false`.

1. Có thể kết luận index đã tồn tại không?
2. Cần kiểm tra MongoDB catalog bằng lệnh gì?
3. Có thể tạo index qua API nào?
4. Ai nên có quyền index DDL?
5. Readiness nên ứng xử ra sao nếu thiếu index critical?

### Bài 2 — Compound index cho tenant

Repository query theo `tenantId`, `status` và sort `createdAt` giảm.

1. Viết `@CompoundIndex`.
2. Viết `Index` builder tương đương.
3. Tại sao thứ tự fields quan trọng?
4. Query chỉ có `status` có chắc dùng index không?
5. `explain` cần xem gì?

### Bài 3 — Unique index với dữ liệu trùng

Collection có ba accounts cùng tenant và hai accounts trùng email.

1. Viết aggregation tìm duplicates.
2. Đề xuất business remediation.
3. Khi nào tạo unique index?
4. Nếu data đang ghi song song thì làm sao tránh duplicates mới?
5. Tại sao auto-index trong startup dễ thất bại?

### Bài 4 — Nullable phone number

Một triệu accounts, 90% không có `phoneNumber`.

1. Tạo single-field unique index có thể gặp gì?
2. Partial unique phù hợp điều kiện nào?
3. String rỗng/null/missing phải phân biệt ra sao?
4. Nên dùng key theo tenant không?
5. Khi user thêm số trùng, ứng dụng xử lý thế nào?

### Bài 5 — TTL risk

Collection `sessions` có 10 triệu documents đã hết hạn.

1. Nếu thêm TTL index lúc startup có thể xảy ra gì?
2. Cần đo tập eligible thế nào?
3. TTL có xóa đúng lúc hết hạn không?
4. Có cần backup trước migration không?
5. Làm sao giảm delete storm?

### Bài 6 — Bật cấu hình Spring

So sánh:

```properties
spring.data.mongodb.auto-index-creation=true
```

và:

```properties
spring.data.mongodb.auto-index-creation=false
```

1. Hành vi mong muốn là gì?
2. Tại sao property có thể bị override?
3. `AbstractMongoClientConfiguration#autoIndexCreation()` ảnh hưởng gì?
4. Khi custom MongoTemplate, phải xác nhận gì?
5. Production nên chọn chiến lược nào?

### Bài 7 — `MongoTemplate.indexOps()`

Viết migration dùng:

```java
MongoTemplate.indexOps(CustomerAccount.class)
```

để tạo:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Đặt tên rõ ràng, đọc lại index list và ghi migration outcome.

### Bài 8 — `ensureIndex` và conflicts

MongoDB đã có:

```javascript
{ key: { email: 1 }, name: "idx_email" }
```

App muốn:

```javascript
{ key: { email: 1 }, name: "idx_email", unique: true }
```

1. Vì sao không coi là migration đơn giản?
2. Rủi ro duplicate?
3. Cần tạo index mới/sửa theo quy trình nào?
4. Rollback thế nào?
5. Nếu bỏ unique thì correctness bị ảnh hưởng gì?

### Bài 9 — Nhiều pods

Deployment 30 API pods cùng bật auto-index creation.

1. Vì sao đây là mô hình không tối ưu?
2. MongoDB có chắc tạo 30 physical index copies không?
3. Startup/readiness có rủi ro gì?
4. Thiết kế one-off migration job.
5. Cần lock/coordination gì nếu jobs trùng?

### Bài 10 — Index contract test

Viết integration test:

- Kết nối MongoDB test;
- Đọc `getIndexInfo` hoặc `listIndexes`;
- Kiểm tra name/key order;
- Kiểm tra unique và partial filter;
- Fail khi index thiếu;
- Không tự tạo index khi read-only check.

### Bài 11 — Migration state

Job tạo index thành công nhưng crash trước khi ghi marker.

1. Lần chạy tiếp theo phải làm gì?
2. Vì sao không mặc định chạy `dropIndex()`?
3. Khi nào ghi `COMPLETED`?
4. Race giữa hai executors xử lý thế nào?
5. Definition hash giúp gì?

### Bài 12 — Partial unique và soft delete

Business cho phép email được tái sử dụng sau khi account cũ `deleted:true`.

1. Định nghĩa partial unique.
2. Query nào dùng index?
3. Nếu khôi phục account cũ từ deleted sang active, có thể lỗi gì?
4. Đối chiếu dữ liệu cũ ra sao?
5. Tại sao unique vẫn là business invariant?

### Bài 13 — Hidden index

Một index ít được dùng nhưng chiếm 12 GiB.

1. Hiding nó giúp đo gì?
2. Khi hidden, writes có còn maintain không?
3. TTL/unique behavior có biến mất không?
4. Có thể dùng hint không?
5. Thiết kế kế hoạch drop có rollback.

### Bài 14 — Multi-tenant collections động

Hệ thống có 500 tenant collections, mỗi collection cần ba indexes.

1. Vì sao một static annotation không đủ đảm bảo?
2. Thiết kế provisioning migration loop có rate limit.
3. Một tenant index migration fail thì xử lý thế nào?
4. Làm sao tránh quét và tạo 1.500 indexes trong giờ peak?
5. Có cần audit per-tenant schema version không?

### Bài 15 — Atlas và self-managed

Lập bảng trách nhiệm về:

- Quyền tạo index;
- Storage headroom;
- Query monitoring;
- Backup;
- Index build scheduling;
- Search index lifecycle;
- DDL audit.

Giải thích vì sao Atlas managed không thay trách nhiệm ứng dụng.

### Bài 16 — Index performance regression

Sau tạo compound index, read p95 giảm từ 150 ms xuống 45 ms nhưng write p99 tăng từ 90 ms lên 230 ms.

1. Cần xem traffic mix nào?
2. Index size/working set tăng bao nhiêu?
3. Có thể tạo partial index không?
4. Có nên drop ngay không?
5. Thiết kế benchmark và SLO decision.

### Bài 17 — CI/CD migration pipeline

Thiết kế:

```text
PR review → staging migration → tests
→ production preflight → migrate once
→ verify → API rollout → monitor
```

Cho mỗi bước, nêu owner, evidence, stop condition và rollback.

### Bài 18 — Incident response

Sự cố: Sau release, API pods crash loop; logs có index options conflict; collection đã có 70 triệu documents.

1. Thu thập bằng chứng read-only gì?
2. Làm sao giữ app cũ hoạt động?
3. Tại sao không nên tự drop conflicting index?
4. Phân tích chi phí build index mới thế nào?
5. Khi nào GO/NO-GO?

## 55. Checklist trước khi tạo index trên production

### Dữ liệu và tính đúng đắn

- [ ] Xác định collection/database/tenant scope.
- [ ] Xác định business purpose của index.
- [ ] Đã audit dữ liệu trùng cho unique indexes.
- [ ] Đã kiểm tra null/missing/empty values.
- [ ] Đã kiểm tra normalization/collation.
- [ ] Đã kiểm tra partial filter và soft delete semantics.
- [ ] Đã kiểm tra TTL retention và số records sắp hết hạn.
- [ ] Có backup/recovery point khi cần.
- [ ] Không mở rộng quyền API service không cần thiết.

### Tương thích và hiệu năng

- [ ] Server và Spring Data versions hỗ trợ options.
- [ ] Index phù hợp shard key/unique constraints nếu sharded.
- [ ] Có đủ disk/CPU/I/O headroom cho build.
- [ ] Đã benchmark staging với dữ liệu đại diện.
- [ ] Đã đo read/write p95/p99.
- [ ] Đã xem `getIndexes` và `$indexStats`.
- [ ] Không duplicate indexes không cần thiết.
- [ ] Có query-plan verification.
- [ ] Có change window/owner/on-call.
- [ ] Có rollback và post-deploy monitoring.

### Quy trình

- [ ] Auto-index creation production được kiểm soát hoặc tắt.
- [ ] Migration chạy độc lập, không đồng loạt ở API pods.
- [ ] Migration identity có least privilege.
- [ ] Desired/actual index specs được diff.
- [ ] Preflight có trạng thái PASS/MISSING/CONFLICT.
- [ ] Không tự drop indexes khi conflict.
- [ ] Migration marker chỉ ghi sau postcondition.
- [ ] App rollout chỉ diễn ra khi required indexes sẵn sàng.
- [ ] Không log secrets hoặc dữ liệu nhạy cảm.
- [ ] Có evidence và thời điểm triển khai.

## 56. Checklist sau khi triển khai index

- [ ] `getIndexes`/`listIndexes` phản ánh spec được duyệt.
- [ ] Unique/TTL/partial semantics đã được kiểm tra.
- [ ] Không có index build vẫn đang lỗi hoặc treo.
- [ ] Read p95/p99 đạt mục tiêu.
- [ ] Write p95/p99 và throughput vẫn đạt SLO.
- [ ] Disk usage/headroom phù hợp.
- [ ] CPU/I/O/replication lag không bất thường.
- [ ] Query planner sử dụng index khi thích hợp.
- [ ] Không có mới phát sinh duplicate errors không được xử lý.
- [ ] API services không phải thực hiện DDL khi restart.
- [ ] Migration history đã ghi đúng.
- [ ] Có owner theo dõi trong stabilization window.
- [ ] Index cũ chỉ bị xóa ở change sau khi đủ bằng chứng.

## 57. Tài liệu tham khảo

Đối chiếu với tài liệu chính thức của **đúng Spring Data MongoDB, Spring Boot và MongoDB Server version**:

- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Template APIs](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html)
- [Spring Boot Reference — Data](https://docs.spring.io/spring-boot/reference/data/index.html)
- [MongoDB Indexes Overview](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB `createIndexes` Command](https://www.mongodb.com/docs/manual/reference/command/createIndexes/)
- [MongoDB Index Builds](https://www.mongodb.com/docs/manual/core/index-creation/)
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB `$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexstats/)
- [MongoDB `listIndexes`](https://www.mongodb.com/docs/manual/reference/command/listIndexes/)
- [MongoDB Query Explain](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Sharded Unique Index Constraints](https://www.mongodb.com/docs/manual/core/index-unique/#sharded-clusters)
- [MongoDB Search Documentation](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search Documentation](https://www.mongodb.com/docs/vector-search/)

## Kết luận

Quản lý index trong **Spring Data MongoDB** có hai phần phải tách bạch: **mô tả index trong Java model** và **thay đổi index catalog thật trên MongoDB**. `@Indexed`, `@CompoundIndex` và các annotation khác giúp gần mã nguồn với cấu trúc dữ liệu, nhưng không bảo đảm database đã có đúng index hoặc rằng một thay đổi annotation sẽ tự chuyển đổi index hiện hữu theo cách an toàn.

Auto-index creation có thể thuận tiện trong môi trường học tập, prototype hoặc những hệ nhỏ được kiểm soát. Tuy nhiên, với collection production lớn, nhiều API pods, dữ liệu cũ và yêu cầu HA, cách này có các rủi ro đáng kể: **index build trong startup, duplicate-key failures, TTL deletes, option conflicts, tăng I/O/disk, quyền DDL quá rộng và drift giữa các app versions**. Một index có thể được giải quyết cả khi entity được truy cập lần đầu trong lúc ứng dụng chạy, nên rủi ro không chỉ tập trung ở thời điểm deploy.

Hướng vận hành bền vững là:

1. **Tắt hoặc kiểm soát chặt auto-index creation** cho application production.
2. **Khai báo desired index state có version/owner**, bằng annotations kết hợp resolver hoặc manifest riêng.
3. **Chạy preflight** so sánh actual catalog, kiểm tra dữ liệu unique/TTL, capacity và compatibility.
4. **Thực thi migration riêng**, bằng `MongoTemplate.indexOps().ensureIndex()` hoặc công cụ có kiểm soát, đúng một chủ thể và đúng change window.
5. **Đọc lại actual index specs**, chạy integration/performance tests rồi mới triển khai application phụ thuộc.
6. **Theo dõi và chỉ drop index cũ sau khi đủ bằng chứng**, với rollback riêng cho từng loại thay đổi.

Một database index không chỉ là dòng annotation hoặc “tối ưu vài milliseconds”. Nó có thể quyết định **dữ liệu nào được phép tồn tại, bản ghi nào bị xóa, truy vấn nào đạt SLO và quá trình khởi động ứng dụng có an toàn hay không**. Vì vậy, hãy quản lý index như một **database schema migration có phiên bản, phê duyệt, bằng chứng và khả năng phục hồi**, thay vì một tác dụng phụ của startup.

