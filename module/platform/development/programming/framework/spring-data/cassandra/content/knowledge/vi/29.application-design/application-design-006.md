# Xóa mềm, TTL và điều kiện dữ liệu còn hiệu lực trong Spring Data Cassandra

Trong ứng dụng dùng **Spring Data Cassandra**, một bản ghi còn tồn tại trong Apache Cassandra chưa chắc còn được phép hiển thị hoặc sử dụng. Ví dụ: người dùng đã xóa một tài nguyên, phiên đăng nhập đã hết hạn hoặc một mã xác thực đã quá thời gian sử dụng. Thiết kế tốt cần phân biệt rõ **trạng thái nghiệp vụ**, **thời điểm hết hiệu lực** và **cơ chế dọn dữ liệu** của Cassandra.

Bài này nằm trong phần **Thiết kế ứng dụng**. Trọng tâm là thiết kế bảng theo cách đọc, ánh xạ entity/repository của Spring Data Cassandra, dùng CQL và `CqlSession` cho các thao tác cần kiểm soát TTL hoặc điều kiện ghi, đồng thời quản lý chi phí tombstone, tính nhất quán và hiệu năng trong hệ phân tán.

## 1. Ba khái niệm dễ bị nhầm lẫn

| Cơ chế | Mục đích | Cách triển khai thường gặp | Điều cần nhớ |
| --- | --- | --- | --- |
| **Xóa mềm (soft delete)** | Ẩn hoặc vô hiệu hóa dữ liệu theo quyết định nghiệp vụ nhưng vẫn giữ dấu vết | Cột `deleted`, `deleted_at`, hoặc `status` | Bản ghi vẫn còn trong bảng; mọi đường đọc và ghi phải tôn trọng trạng thái xóa |
| **TTL (Time To Live)** | Đặt thời gian tồn tại cho các ô dữ liệu được ghi | `INSERT/UPDATE ... USING TTL`, `default_time_to_live` | TTL hết hạn làm dữ liệu không còn được trả về, rồi được thu gom sau; không đồng nghĩa xóa vật lý ngay lập tức |
| **Điều kiện còn hiệu lực** | Quyết định dữ liệu *có được dùng ngay lúc này* không | `deleted = false`, `status = ACTIVE`, `now < expires_at`, quyền sở hữu... | Là quy tắc nghiệp vụ; phải được áp dụng tại điểm sử dụng dữ liệu |

Giả sử một liên kết chia sẻ có `expires_at = 15:00` và được người dùng xóa lúc `14:45`. Từ `14:45`, liên kết phải không còn truy cập được dù TTL dự kiến hết lúc `15:00`. Ngược lại, khi đồng hồ đến `15:00`, liên kết hết hiệu lực dù dữ liệu của nó vẫn còn trong Cassandra hoặc chưa được compaction thu gom.

Một quy tắc đọc có thể viết thành:

```text
isVisible(resource, now, requester)
  = resource tồn tại
    AND resource.deleted != true
    AND resource.status == ACTIVE
    AND (resource.expires_at IS NULL OR now < resource.expires_at)
    AND requester được phép truy cập resource
```

Quy tắc trên áp dụng ở lớp service sau khi đọc theo khóa. Cassandra không có cơ chế lọc tùy ý như cơ sở dữ liệu quan hệ: thêm `WHERE deleted = false` hoặc `WHERE expires_at > now()` vào một truy vấn bất kỳ thường không hợp lệ hoặc dẫn đến cách truy vấn kém hiệu quả. **Hình dạng truy vấn quyết định hình dạng bảng.**

## 2. Thiết kế bảng từ đường truy cập

Giả sử dịch vụ thường xuyên đọc một tài nguyên bằng cặp `(tenantId, resourceId)`. Thiết kế một partition cho mỗi cặp định danh giúp truy vấn theo khóa rõ ràng và giới hạn kích thước partition:

```sql
CREATE TABLE resources_by_id (
    tenant_id uuid,
    resource_id uuid,
    title text,
    status text,
    deleted boolean,
    deleted_at timestamp,
    expires_at timestamp,
    PRIMARY KEY ((tenant_id, resource_id))
) WITH default_time_to_live = 0;
```

Ở đây, cả `tenant_id` và `resource_id` tạo thành **composite partition key**; mỗi cặp khóa xác định một partition. Khi tạo mới, ứng dụng đặt `deleted = false` và `status = 'ACTIVE'`. Giá trị `deleted` cần được khởi tạo nhất quán, nhất là khi thao tác sau này dùng điều kiện `IF deleted = false`.

Truy vấn đọc một tài nguyên:

```sql
SELECT tenant_id, resource_id, title, status, deleted, deleted_at, expires_at
FROM resources_by_id
WHERE tenant_id = ? AND resource_id = ?;
```

Nếu cần liệt kê tài nguyên theo tenant, bảng trên **không** phục vụ trực tiếp truy vấn chỉ có `tenant_id` vì thiếu phần còn lại của partition key. Phải thiết kế thêm bảng đọc như `active_resources_by_tenant`, với chiến lược giới hạn partition (ví dụ phân bucket theo thời gian hoặc nhóm) dựa trên lưu lượng thực tế. Khi xóa mềm, hệ thống phải cập nhật hoặc loại tài nguyên khỏi bảng phục vụ danh sách; một luồng cập nhật bất đồng bộ có thể gây trễ, vì vậy tại điểm mở chi tiết hoặc thực hiện hành động vẫn phải kiểm tra bản ghi nguồn.

### Ánh xạ khóa và entity với Spring Data Cassandra

Ví dụ rút gọn sau mô tả cách ánh xạ hai thành phần partition key. Khi triển khai cần bổ sung constructor, getter/setter và `equals`/`hashCode` cho lớp khóa.

```java
@PrimaryKeyClass
public class ResourceKey implements Serializable {
    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "resource_id", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID resourceId;

    // Constructors, accessors, equals() và hashCode()
}

@Table("resources_by_id")
public class Resource {
    @PrimaryKey
    private ResourceKey key;

    private String title;
    private String status;
    private Boolean deleted;

    @Column("deleted_at")
    private Instant deletedAt;

    @Column("expires_at")
    private Instant expiresAt;

    // Constructors và accessors
}

public interface ResourceRepository
        extends CassandraRepository<Resource, ResourceKey> {
}
```

Spring Data Cassandra chịu trách nhiệm mapping đối tượng và truy cập repository. Tuy nhiên, annotation entity **không tự động** bổ sung điều kiện `deleted = false` vào mọi truy vấn. Ứng dụng phải tổ chức đường đọc để không bỏ sót kiểm tra hiệu lực.

## 3. Thiết kế xóa mềm

### 3.1. Đánh dấu thay vì xóa vật lý

Thao tác xóa mềm điển hình:

```sql
UPDATE resources_by_id
SET deleted = true, deleted_at = ?
WHERE tenant_id = ? AND resource_id = ?;
```

Câu lệnh trên là một **upsert** theo ngữ nghĩa CQL: nếu chưa có bản ghi, `UPDATE` thông thường vẫn có thể tạo các ô dữ liệu mới cho khóa đó. Vì vậy, nếu yêu cầu chỉ xóa tài nguyên thực sự đang tồn tại và đang hoạt động, dùng thao tác có điều kiện:

```sql
UPDATE resources_by_id
SET deleted = true, deleted_at = ?
WHERE tenant_id = ? AND resource_id = ?
IF deleted = false;
```

`IF` kích hoạt **lightweight transaction (LWT)** cho partition liên quan. Kết quả CQL có cột `[applied]` cho biết điều kiện có được đáp ứng hay không. LWT tốn tài nguyên và độ trễ hơn ghi thông thường; chỉ dùng khi cần chặn đua tranh trạng thái, không tự động áp dụng cho mọi mutation.

Ví dụ qua Java Driver được dùng cùng Spring Data Cassandra:

```java
SimpleStatement statement = SimpleStatement.newInstance(
    "UPDATE resources_by_id " +
    "SET deleted = true, deleted_at = ? " +
    "WHERE tenant_id = ? AND resource_id = ? " +
    "IF deleted = false",
    Instant.now(), tenantId, resourceId
);

Row row = cqlSession.execute(statement).one();
boolean applied = row != null && row.getBoolean("[applied]");
```

Nếu `applied = false`, không được tự kết luận rằng bản ghi đã xóa: nó có thể chưa tồn tại, đã xóa hoặc không có trạng thái `deleted = false`. Đọc trạng thái hiện tại để đưa ra phản hồi nghiệp vụ; thao tác xóa lặp lại có thể được coi là thành công về mặt idempotency nếu tài nguyên thực sự đã ở trạng thái xóa.

### 3.2. Chặn ghi sau khi đã xóa

Chỉ bảo vệ lệnh `delete` là chưa đủ. Một đường ghi khác có thể vô tình làm xuất hiện lại nội dung hoặc chuyển `deleted` về `false`. Với tài nguyên cần quy tắc “đã xóa thì không được cập nhật”, các mutation cạnh tranh phải tuân thủ cùng giao thức điều kiện:

```sql
UPDATE resources_by_id
SET title = ?
WHERE tenant_id = ? AND resource_id = ?
IF deleted = false;
```

Điều này yêu cầu trạng thái xóa được khởi tạo từ lúc tạo và các đường ghi tương ứng cùng tuân thủ quy tắc. Một `INSERT`/`UPDATE` không điều kiện từ tiến trình khác vẫn có thể phá vỡ giả định. Nếu nghiệp vụ cho phép khôi phục, hãy xây dựng thao tác *restore* riêng với kiểm tra quyền, trạng thái và quan hệ với các bảng đọc.

Xóa mềm cũng **không phải xóa dữ liệu nhạy cảm theo nghĩa vật lý**. Nếu chính sách lưu giữ yêu cầu xóa hẳn, cần quy trình xóa cứng và xử lý dữ liệu liên quan, bản sao, chỉ mục/bảng đọc cùng các yêu cầu vận hành tương ứng.

## 4. TTL: thời gian sống của dữ liệu trong Cassandra

### 4.1. TTL tác động lên những gì?

TTL trong Cassandra gắn với **các ô dữ liệu không thuộc primary key được ghi bởi mutation**. Không nên hình dung TTL là bộ đếm tồn tại của một đối tượng Java hay một lệnh xóa hàng theo lịch. Nếu chỉ cập nhật một cột với TTL, những cột khác có thể vẫn tồn tại sau khi cột đó hết hạn.

```sql
UPDATE resources_by_id USING TTL 600
SET title = 'Tiêu đề tạm'
WHERE tenant_id = ? AND resource_id = ?;
```

Sau khoảng 600 giây, ô `title` từ mutation này hết hiệu lực; `deleted`, `status`, `expires_at` vẫn có thể còn. Ngược lại, khi viết lại một ô mà không kèm TTL theo lệnh, thời hạn của giá trị mới có thể khác hoặc bị xóa bỏ (trừ khi bảng áp dụng TTL mặc định). Do đó, phải xác định rõ **những cột nào cùng một vòng đời**.

Ví dụ dành cho dữ liệu có vòng đời ngắn: phiên tạm hoặc mã xác thực.

```sql
CREATE TABLE sessions_by_id (
    tenant_id uuid,
    session_id uuid,
    subject_id uuid,
    expires_at timestamp,
    PRIMARY KEY ((tenant_id, session_id))
) WITH default_time_to_live = 0;

INSERT INTO sessions_by_id (
    tenant_id, session_id, subject_id, expires_at
) VALUES (?, ?, ?, ?) USING TTL 900;
```

Trong ví dụ này, dữ liệu không thuộc khóa chính được ghi với TTL 900 giây (15 phút). Nếu không còn ô dữ liệu sống, hàng sẽ không còn xuất hiện trong kết quả đọc thông thường. Các dấu vết hết hạn còn tồn tại trong lưu trữ cho đến khi cơ chế thu gom phù hợp xử lý.

### 4.2. TTL theo lệnh và TTL mặc định của bảng

- `INSERT ... USING TTL n` hoặc `UPDATE ... USING TTL n`: áp dụng TTL tính bằng **giây** cho các giá trị được ghi trong lệnh đó.
- `default_time_to_live = n`: đặt TTL mặc định của bảng khi ứng dụng không cung cấp TTL riêng; phù hợp khi mọi dữ liệu trong bảng có cùng chính sách tồn tại.
- `TTL(column)` trong `SELECT`: đọc số giây còn lại của ô đang sống khi cột hỗ trợ TTL; giá trị `null` thường nghĩa là ô không có TTL hoặc không có giá trị sống để trả về.
- TTL bằng `0` trên một mutation có thể dùng để ghi giá trị mới **không có TTL**, tùy quy tắc TTL mặc định của bảng; không biến các ô khác thành vĩnh viễn.

Kiểm tra TTL của một ô:

```sql
SELECT subject_id, expires_at, TTL(subject_id) AS remaining_seconds
FROM sessions_by_id
WHERE tenant_id = ? AND session_id = ?;
```

Đừng lấy giá trị `remaining_seconds` làm đồng hồ nghiệp vụ chính xác tuyệt đối. TTL phụ thuộc thời điểm ghi và đồng hồ các node; kết quả có thể thay đổi giữa các lần đọc. Quy tắc cấp phép, thanh toán hoặc hiệu lực pháp lý cần `expires_at` và một cách đánh giá thời gian được chuẩn hóa.

### 4.3. Ghi TTL từ ứng dụng Spring

Nếu nghiệp vụ chủ động quyết định thời gian sống của từng bản ghi, có thể thực hiện CQL qua `CqlSession`. Cách này kết hợp với repository cho thao tác đọc/mapping bình thường:

```java
int ttlSeconds = 900;
Instant now = Instant.now();
Instant expiresAt = now.plusSeconds(ttlSeconds);

SimpleStatement statement = SimpleStatement.newInstance(
    "INSERT INTO sessions_by_id " +
    "(tenant_id, session_id, subject_id, expires_at) " +
    "VALUES (?, ?, ?, ?) USING TTL ?",
    tenantId, sessionId, subjectId, expiresAt, ttlSeconds
);
cqlSession.execute(statement);
```

Giá trị từ ứng dụng được bind qua placeholder thay vì nối chuỗi CQL. Với câu lệnh lặp lại thường xuyên, chuẩn bị `PreparedStatement` một lần và bind các giá trị cho mỗi lần ghi để giảm chi phí parse/prepare. Tùy phiên bản Spring Data Cassandra, `@TimeToLive` hoặc các tùy chọn `CassandraTemplate` cũng có thể khai báo TTL; hãy kiểm tra API tương ứng với phiên bản dự án trước khi chọn cách dùng. Dù dùng API nào, phải kiểm soát cùng một chính sách TTL ở mọi đường tạo và cập nhật.

## 5. `expires_at` là điều kiện nghiệp vụ, TTL là vòng đời lưu trữ

Một service đọc nên tập trung điều kiện hiệu lực tại một chỗ. Ví dụ với `ResourceRepository` ở trên:

```java
public Optional<Resource> findVisible(ResourceKey key, Instant now) {
    return resourceRepository.findById(key)
        .filter(resource -> !Boolean.TRUE.equals(resource.getDeleted()))
        .filter(resource -> "ACTIVE".equals(resource.getStatus()))
        .filter(resource -> resource.getExpiresAt() == null
            || now.isBefore(resource.getExpiresAt()));
}
```

Trong hệ thống thật, thêm kiểm tra quyền của người gọi và chuyển `Instant now` từ `Clock` được cấu hình chung để dễ kiểm thử. Khoảng hiệu lực nên được định nghĩa rõ, ví dụ **`now < expires_at`** nghĩa là ngay tại `expires_at` dữ liệu đã hết hiệu lực. Toàn bộ API đọc chi tiết, tải về, thực hiện hành động và luồng nền tiêu thụ dữ liệu cần chia sẻ cùng điều kiện, không chỉ giao diện người dùng.

Ví dụ với session có TTL 900 giây, lưu `expires_at = issued_at + 900 giây` cho phép từ chối session ngay khi hết hạn ngay cả khi việc dọn dữ liệu vật lý chưa hoàn tất. Nếu người dùng chủ động thu hồi session trước đó, phải có trạng thái thu hồi (`revoked_at`/`deleted`) hoặc một cơ chế thu hồi phù hợp; chỉ chờ TTL sẽ tạo khoảng thời gian session vẫn được chấp nhận.

### Ma trận quyết định

| Có bản ghi? | `deleted` | `expires_at` | Kết quả đọc nghiệp vụ |
| --- | --- | --- | --- |
| Không | Bất kỳ | Bất kỳ | Không tìm thấy/không còn khả dụng |
| Có | `true` | Còn hạn | Từ chối vì đã xóa mềm |
| Có | `false` | Đã đến hoặc qua hạn | Từ chối vì hết hiệu lực |
| Có | `false` | Chưa hết hạn hoặc `null` | Cân nhắc tiếp `status`, quyền truy cập và quy tắc khác |

Không có `expires_at` không nhất thiết là vĩnh viễn: tùy domain, `null` có thể bị cấm hoặc mang ý nghĩa riêng. Hãy định nghĩa từ yêu cầu nghiệp vụ rồi kiểm tra nhất quán ở tất cả đường ghi.

## 6. Tương tác giữa xóa mềm, TTL và các lần cập nhật

### Tình huống A: Dữ liệu bị xóa mềm rồi hết TTL

Nếu TTL được áp dụng cho cả các ô `deleted`/`deleted_at`, dấu xóa cũng có thể biến mất. Khi một số ô khác còn sống lâu hơn hoặc bị ghi mới, trạng thái dễ trở nên mơ hồ. Đặc biệt nguy hiểm nếu ứng dụng diễn giải `deleted = null` là “chưa xóa”.

**Giải pháp:** chọn một vòng đời nhất quán cho cả thực thể tạm thời; hoặc giữ marker xóa đủ lâu theo chính sách dữ liệu và chặn các writer tạo lại bản ghi. Đối với bản ghi cần khả năng kiểm toán dài hạn, có thể tách trạng thái/nhật ký khỏi phần payload có TTL. Đừng đặt TTL ngắn cho marker trong khi payload hoặc các bảng đọc còn có thể tiếp tục tồn tại.

### Tình huống B: Cập nhật kéo dài hoặc xóa bỏ TTL

Một lệnh `UPDATE` ghi lại ô `subject_id` sau 5 phút có thể làm thay đổi thời hạn tồn tại của ô này. Nếu ghi lại với TTL 900 giây, thời điểm hết hạn mới là khoảng 15 phút kể từ lần cập nhật, không phải kể từ lúc tạo session. Nếu ghi không có TTL và bảng không có TTL mặc định, ô mới có thể tồn tại vô thời hạn.

**Giải pháp:** lưu `expires_at` là thời hạn tuyệt đối; khi cập nhật, tính TTL còn lại theo thời hạn đó và từ chối cập nhật nếu đã hết hạn. Với quy tắc “hết hạn tuyệt đối sau 15 phút”, không tự động đặt lại TTL 900 giây cho mỗi lần ghi. Nếu tính TTL từ thời gian còn lại, kiểm tra giá trị dương, giới hạn hợp lệ và cách làm tròn theo giây. `expires_at` vẫn là nguồn quyết định nghiệp vụ tại thời điểm đọc.

### Tình huống C: Xóa mềm và cập nhật xảy ra đồng thời

Hai tiến trình có thể cùng đọc `deleted = false` rồi một tiến trình xóa, tiến trình kia sửa `title`. Đọc trước khi ghi không đủ bảo vệ vì trạng thái có thể đổi giữa hai bước. Sử dụng mutation có `IF deleted = false` cho các chuyển trạng thái cần điều kiện; nếu thiết kế dùng LWT, các writer liên quan phải tuân thủ giao thức đó.

**Lưu ý:** Cassandra không tự đảm bảo giao dịch nguyên tử trải rộng nhiều bảng. Khi có `resources_by_id` và `active_resources_by_tenant`, cần xây dựng cập nhật có thể thử lại, xử lý lỗi từng phần và chiến lược đối soát. Việc đồng bộ bảng danh sách có thể trễ, nên thao tác nhạy cảm phải xác minh trạng thái nguồn.

### Tình huống D: Ghi lại cùng primary key sau khi hết hạn

Một key đã hết TTL không đồng nghĩa ứng dụng có thể tùy tiện tái sử dụng định danh. Nếu hệ thống có thông điệp trễ, worker retry hoặc dữ liệu trong bảng khác, ghi mới cùng khóa có thể khiến một liên kết/tài nguyên đã hết hiệu lực xuất hiện lại.

**Giải pháp:** dùng định danh đủ tính duy nhất, hạn chế tái sử dụng key, thiết kế idempotency cho lệnh tạo, và cân nhắc lưu dấu vết nghiệp vụ riêng khi cần chặn tái tạo trong một khoảng thời gian.

## 7. Tính nhất quán và tombstone trong vận hành

### 7.1. TTL/xóa cứng tạo tombstone

Khi TTL hết hạn, Cassandra xử lý dữ liệu như đã bị xóa về mặt logic và tạo thông tin tombstone để các replica không khôi phục giá trị cũ. `DELETE` vật lý cũng tạo tombstone. Các tombstone không nhất thiết được thu gom ngay: compaction và các điều kiện liên quan đến `gc_grace_seconds` quyết định khả năng dọn dẹp an toàn. **Giảm `gc_grace_seconds` tùy tiện** có thể khiến dữ liệu xóa bị xuất hiện lại khi replica cũ quay về mà chưa được sửa chữa/đồng bộ đúng cách.

Xóa mềm thuần túy là cập nhật trạng thái, không thay thế mọi hệ quả lưu trữ của TTL hoặc `DELETE`; nhưng dùng marker xóa trong nhiều bảng vẫn tăng chi phí ghi và bảo trì. Khối lượng lớn ô hết hạn trong partition được truy vấn rộng có thể khiến truy vấn phải quét nhiều tombstone, tăng độ trễ hoặc chạm ngưỡng cảnh báo/lỗi.

### 7.2. Thiết kế để giảm chi phí đọc

- Đọc theo partition key đầy đủ và giới hạn lượng hàng trả về; tránh quét rộng để tìm vài bản ghi còn hiệu lực.
- Với sự kiện có cùng chính sách thời gian giữ lại, cân nhắc partition theo time bucket và chiến lược compaction phù hợp như **TimeWindowCompactionStrategy (TWCS)**; phải kiểm tra mẫu ghi, TTL và việc cập nhật dữ liệu cũ trước khi chọn.
- Phân biệt **paging** của Cassandra với việc lọc nghiệp vụ: một trang CQL có thể chứa nhiều bản ghi đã xóa mềm hoặc đã quá `expires_at`; cần xác định cách tính số phần tử/trang và continuation token cho API.
- Theo dõi số tombstone được quét, read latency, kích thước partition, số lần compaction, độ trễ giữa xóa nguồn và cập nhật bảng danh sách; kiểm tra thực tế bằng truy vấn và chỉ số vận hành.
- Nếu cần “chỉ liệt kê dữ liệu active” với lưu lượng lớn, thiết kế bảng đọc chuyên dụng theo truy vấn; tránh dựa vào `ALLOW FILTERING` cho truy vấn sản xuất.

### 7.3. Consistency level không thay quy tắc nghiệp vụ

Replication và consistency level ảnh hưởng khả năng đọc thấy bản cập nhật mới nhất. Một replica chậm có thể khiến client tạm thời thấy dữ liệu cũ khi dùng mức nhất quán thấp. Với yêu cầu thu hồi/xóa cần hiệu lực chặt chẽ, xác định consistency level cho đọc và ghi, replication factor, chiến lược LWT khi cần điều kiện cạnh tranh và yêu cầu độ trễ nghiệp vụ. Không có một cấu hình duy nhất phù hợp tất cả trường hợp: mức nhất quán mạnh hơn thường phải đánh đổi độ trễ và khả dụng.

Ngay cả khi dùng LWT cho thao tác đổi trạng thái, ứng dụng vẫn phải áp dụng điều kiện đọc và đảm bảo những đường ghi khác không phá vỡ giao thức. Đừng hiểu `IF` là giao dịch nhiều bảng hoặc là bộ lọc tự động cho mọi repository method.

## 8. Chọn cách làm theo yêu cầu

| Yêu cầu | Thiết kế khuyến nghị | Điểm kiểm tra |
| --- | --- | --- |
| Ẩn tài nguyên sau khi người dùng nhấn xóa, vẫn có thể khôi phục | Cờ `deleted`, `deleted_at`; service lọc hiệu lực; thao tác đổi trạng thái có điều kiện khi cần | Không API nào bỏ qua trạng thái xóa; các bảng đọc được cập nhật |
| Mã xác thực chỉ sống 10 phút | Bảng riêng với TTL 600 giây và `expires_at` | Không gia hạn ngoài ý muốn khi cập nhật; chặn mã đã hết hạn ở service |
| Phiên bị thu hồi ngay nhưng bình thường hết hạn sau 15 phút | `expires_at` + cơ chế revoke, TTL để dọn dữ liệu | Thu hồi có hiệu lực ở mọi điểm xác thực, tính nhất quán đủ đáp ứng SLA |
| Nhật ký có thời hạn giữ lại cố định | TTL/bucket/compaction được thiết kế theo mẫu truy vấn | Tombstone, compaction, truy vấn theo thời gian và lưu giữ bắt buộc |
| Xóa hẳn dữ liệu theo chính sách | Quy trình xóa cứng và dọn mọi bảng/bản sao liên quan | Không coi `deleted = true` hoặc hết TTL là bằng chứng xóa vật lý tức thì |

## 9. Các ca kiểm thử nên có

1. **Đọc hợp lệ:** bản ghi `deleted = false`, `status = ACTIVE`, `expires_at` ở tương lai được trả về.
2. **Đã xóa mềm:** bản ghi còn trong Cassandra nhưng service trả “không khả dụng”; thử ở cả endpoint chi tiết và hành động sử dụng.
3. **Ranh giới hết hạn:** kiểm tra ngay trước, đúng lúc và sau `expires_at`; xác nhận quy tắc `now < expires_at`.
4. **Xóa lặp và ghi đồng thời:** xóa hai lần, cập nhật cùng lúc với xóa; xác nhận kết quả LWT `[applied]` và xử lý thất bại có điều kiện.
5. **TTL thực tế:** ghi dữ liệu sống ngắn trong môi trường tích hợp, đọc `TTL(column)`, xác nhận dữ liệu hết hạn không còn được trả về; không đòi compaction vật lý xảy ra ngay.
6. **Cập nhật gần hết hạn:** đảm bảo cập nhật không vô tình gia hạn vòng đời tuyệt đối; kiểm tra giá trị TTL còn lại.
7. **Bảng đọc và paging:** khi nhiều mục bị xóa mềm, danh sách không lộ mục đã xóa và vẫn trả trang đúng hợp đồng API.
8. **Đồng hồ và độ trễ:** kiểm tra `Clock` có thể điều khiển trong unit test và độ trễ đồng bộ bảng đọc trong integration test; với yêu cầu nhất quán mạnh, thử tình huống nhiều writer.

## 10. Checklist khi đưa vào sản xuất

- Định nghĩa rõ ý nghĩa của `deleted`, `status`, `expires_at` và thời điểm chính xác bắt đầu hết hiệu lực.
- Thiết kế bảng theo các truy vấn thực sự cần, bao gồm chi tiết, danh sách, kiểm tra hiệu lực và các thao tác cập nhật.
- Đặt điều kiện hiệu lực ở service hoặc lớp domain dùng chung; không kỳ vọng repository tự lọc trạng thái xóa mềm.
- Chọn TTL cho đúng các ô dữ liệu có cùng vòng đời; thống nhất cách cập nhật để không vô tình gia hạn hoặc loại bỏ TTL.
- Dùng LWT có chủ đích khi quy tắc chuyển trạng thái cần ngăn cạnh tranh; kiểm tra `[applied]` và xử lý retry/idempotency.
- Xác định sự đánh đổi giữa tính nhất quán, độ trễ và độ sẵn sàng; kiểm tra hành vi khi có nhiều replica hoặc nhiều bảng đọc.
- Theo dõi tombstone, compaction, kích thước partition và đọc phân trang; có kế hoạch lưu giữ/xóa vật lý phù hợp chính sách dữ liệu.

**Kết luận:** trong Spring Data Cassandra, **xóa mềm** thể hiện ý định nghiệp vụ, **`expires_at`** quyết định dữ liệu còn được dùng hay không, còn **TTL** giúp quản lý vòng đời lưu trữ. Kết hợp ba cơ chế đúng cách đòi hỏi thiết kế bảng theo truy vấn, kiểm soát mọi đường ghi/đọc và hiểu chi phí của hệ phân tán; một cờ xóa hoặc TTL đơn lẻ không thể thay thế toàn bộ những trách nhiệm đó.
