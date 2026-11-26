# Truy vấn count, exists và delete theo điều kiện

Trong **SPRING_DATA_COUCHBASE**, repository thường được dùng để lấy document, nhưng nhiều nghiệp vụ chỉ cần biết **có document thỏa điều kiện hay không**, **có bao nhiêu document**, hoặc cần **xóa một tập document theo điều kiện rõ ràng**. Đây là ba thao tác liên quan nhưng khác nhau về mục tiêu, kết quả trả về, chi phí và rủi ro. Việc dùng `findBy...` rồi tải toàn bộ entity để đếm, hoặc xóa hàng loạt chỉ dựa trên một tên phương thức dài, có thể khiến tầng truy cập dữ liệu vừa chậm vừa khó kiểm soát.

Bài thuộc chương **Truy vấn dẫn xuất** và tập trung vào các nhóm phương thức **`countBy...`**, **`existsBy...`** và **`deleteBy...`/`removeBy...`** trong ngữ pháp Spring Data. Với Spring Data Couchbase, cần đặc biệt phân biệt **cú pháp suy diễn được từ tên phương thức** với **khả năng thực thi mà phiên bản Couchbase repository thực sự hỗ trợ**: không thể mặc định mọi dạng xóa dẫn xuất đều hoạt động giống Spring Data JPA. Khi xóa nhiều document, việc xác định namespace, điều kiện SQL++, chính sách kiểm soát đồng thời và phương thức ghi thực tế quan trọng hơn sự ngắn gọn của tên method.

Nội dung kết nối document mapping, repository và `CouchbaseTemplate` với SQL++ trên bucket/scope/collection; đồng thời xem xét index, TTL, CAS, giao dịch, consistency và API reactive để xây dựng tầng truy cập an toàn, hiệu quả và dễ vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết các phương thức `countBy...` và `existsBy...` để hỏi về số lượng hoặc sự tồn tại theo điều kiện.
2. Giải thích khác biệt giữa kết quả `long`, `boolean`, `Optional<T>` và `List<T>`.
3. Hiểu ngữ nghĩa dự kiến của `deleteBy...`, biết cách **kiểm tra hỗ trợ theo phiên bản Spring Data Couchbase** trước khi dùng.
4. Phân biệt **xóa theo ID bằng key-value** với **xóa theo bộ lọc nội dung bằng SQL++** hoặc quy trình tìm rồi xóa.
5. Thiết kế điều kiện xóa có tenant, trạng thái, ngưỡng thời gian và cờ bảo vệ; tránh xóa nhầm.
6. Không đồng nhất số đếm **trước khi xóa** với số document **thực sự xóa thành công**.
7. Hiểu rủi ro của chuỗi `exists → insert` hoặc `count → delete` dưới cạnh tranh và độ trễ index.
8. Chọn index và kiểm tra `EXPLAIN` cho truy vấn `COUNT`/`EXISTS`/`DELETE`.
9. Biết khi nào nên dùng `@Query`, `CouchbaseTemplate`, SDK Query API, key-value API hoặc transaction.
10. Thiết kế bài kiểm thử cho điều kiện xóa, `NULL`/`MISSING`, TTL, reactive và sự kiện lỗi một phần.

## 2. Bối cảnh ví dụ: dọn tài khoản lưu trữ

Giả sử ứng dụng có bucket `app`, scope `crm`, collection `customers`. Hệ thống đa tenant lưu khách hàng, trong đó một số document đã chuyển sang trạng thái `ARCHIVED` và có thể xóa sau một thời gian lưu trữ.

Một document mẫu:

```json
{
  "tenant_id": "tenant-a",
  "email": "an@example.test",
  "status": "ARCHIVED",
  "archived_at": "2026-08-15T00:00:00Z",
  "retention_hold": false,
  "display_name": "An Nguyen"
}
```

Document có ID riêng trong Couchbase, ví dụ `customer::tenant-a::C001`. Trong ví dụ, `retention_hold = true` có nghĩa document **không được xóa** dù đã vượt thời gian lưu trữ; nếu field này `NULL` hoặc `MISSING`, chính sách an toàn là **không tự coi là false**.

Entity Java:

```java
package example.crm;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field
    private String email;

    @Field
    private String status;

    @Field("archived_at")
    private Instant archivedAt;

    @Field("retention_hold")
    private Boolean retentionHold;

    @Field("display_name")
    private String displayName;

    protected Customer() {
        // Dành cho document mapping.
    }

    // Constructor nghiệp vụ và getters/setters lược bỏ.
}
```

Bài giả định kết nối Couchbase và bucket đã được cấu hình. Mapping `@Scope`/`@Collection` chỉ định namespace logic, còn `@Field` ánh xạ property Java sang khóa JSON. Cách lưu `Instant` phải được kiểm tra trong ứng dụng thực tế; ví dụ minh họa chuỗi ISO 8601 chuẩn UTC nhưng converter có thể lưu khác.

## 3. Phương thức `countBy...`: đếm đúng đối tượng cần biết

Một repository có thể mô tả phép đếm với điều kiện ngay trong tên method:

```java
package example.crm;

import java.time.Instant;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    long countByStatus(String status);

    long countByTenantIdAndStatus(
        String tenantId,
        String status
    );

    long countByTenantIdAndStatusAndArchivedAtBefore(
        String tenantId,
        String status,
        Instant cutoff
    );
}
```

Cách đọc `countByTenantIdAndStatus("tenant-a", "ARCHIVED")` là: trả **số document** có property Java `tenantId` bằng `tenant-a` **và** `status` bằng `ARCHIVED`.

SQL++ biểu diễn mục tiêu đếm:

```sql
-- SQL++ minh họa, không phải query nguyên văn framework sinh ra.
SELECT COUNT(1) AS total
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`status` = $status;
```

Trong thực tế, Spring Data Couchbase có thể thêm type discriminator, metadata hoặc dùng projection/query shape khác. Quan trọng là **điều kiện đếm** và **tập document nguồn** phải giống yêu cầu nghiệp vụ; đừng suy ra truy vấn thực tế chỉ từ hình thức tên method.

### 3.1. `countBy...` không phải `findBy...().size()`

Cách không nên dùng với tập lớn:

```java
// Không nên làm thế khi mục tiêu chỉ là đếm.
int total = repository.findByStatus("ARCHIVED").size();
```

Nó có thể phải lấy và mapping toàn bộ entity trước khi tính kích thước danh sách ở Java. Trái lại, `countByStatus` biểu đạt nhu cầu **đếm ở phía dữ liệu**, không tải từng document về ứng dụng chỉ để gọi `size()`.

| Cách làm | Đầu ra | Hệ quả |
| --- | --- | --- |
| `findByStatus(...).size()` | Số lượng bằng kích thước `List` | Có thể tải toàn bộ entity, tốn mạng/bộ nhớ. |
| `countByStatus(...)` | Một số nguyên | Diễn đạt mục tiêu đếm và giảm dữ liệu trả về. |
| `Page.getTotalElements()` | Tổng số cho giao diện phân trang | Có thể dựa vào truy vấn đếm bổ sung. |
| `count()` kế thừa repository | Tổng document của phạm vi repository | Không có bộ lọc tùy biến như `countByStatus`. |

### 3.2. Đếm document, không phải đếm giá trị field

Trong SQL++, `COUNT(1)` đếm các dòng của tập kết quả thỏa `WHERE`. `COUNT(field)` có thể khác do xử lý giá trị `NULL`/`MISSING`. Với bài toán “có bao nhiêu khách hàng”, cần đếm **document**, không vô tình đếm chỉ những document đã có email hoặc phone.

Truy vấn đếm theo từng trạng thái cũng khác với một `countByStatus` đơn lẻ:

```sql
SELECT c.`status` AS status, COUNT(1) AS total
FROM `app`.`crm`.`customers` AS c
GROUP BY c.`status`;
```

Đây là **aggregate theo nhóm**, không nên cố biểu diễn bằng `countBy...` rồi gọi nhiều lần cho mọi trạng thái khi có nhiều giá trị. Nếu cần `GROUP BY`, hãy chọn SQL++ tường minh qua query API thích hợp.

### 3.3. Đếm khi dữ liệu vừa ghi

`countBy...` thường truy vấn qua SQL++/Query Service và index, vì vậy kết quả có thể chưa phản ánh tất cả thao tác key-value mới nhất dưới mức scan consistency mặc định. Nếu báo cáo đòi hỏi mức nhất quán cụ thể, cần cấu hình query options được phiên bản Spring Data Couchbase hỗ trợ; không mặc định `countBy...` luôn là số lượng tức thời tuyệt đối.

## 4. Phương thức `existsBy...`: hỏi có hay không

Khi ứng dụng chỉ cần biết ít nhất một document thỏa điều kiện, `existsBy...` diễn đạt đúng mục đích hơn `findBy...`.

```java
public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    boolean existsByTenantIdAndEmail(
        String tenantId,
        String email
    );

    boolean existsByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Ví dụ:

```java
boolean emailAlreadyUsed = repository.existsByTenantIdAndEmail(
    "tenant-a",
    "an@example.test"
);
```

Ý nghĩa là kiểm tra **có ít nhất một** customer thuộc tenant này có email trùng, không phải trả danh sách email hoặc đếm mọi document cho giao diện.

SQL++ minh họa để kiểm tra sự tồn tại có thể tìm một bản ghi:

```sql
SELECT META(c).id AS id
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`email` = $email
LIMIT 1;
```

**Không khẳng định Spring Data Couchbase sinh chính xác truy vấn `LIMIT 1` ở trên.** Tùy phiên bản, `existsBy...` có thể được triển khai bằng query count hoặc một dạng truy vấn khác. Đánh giá hiệu năng dựa trên SQL++ thực tế và `EXPLAIN`, không chỉ dựa vào tên method.

### 4.1. `existsBy...` khác `Optional<T> findBy...`

| Mục đích | Phương thức | Kết quả |
| --- | --- | --- |
| Chỉ cần biết có email chưa | `existsByTenantIdAndEmail(...)` | `boolean` |
| Muốn đọc thông tin khách hàng | `findByTenantIdAndEmail(...)` | `Optional<Customer>` nếu nghiệp vụ bảo đảm duy nhất |
| Muốn biết có bao nhiêu bản ghi trùng | `countByTenantIdAndEmail(...)` | `long` |

`existsBy...` không chứng minh có **đúng một** document; nó chỉ chứng minh có ít nhất một document phù hợp. Một secondary index trên email cũng **không tự đặt ràng buộc uniqueness** cho toàn collection.

### 4.2. Bẫy `exists → insert` dưới cạnh tranh

Mã giả:

```java
if (!repository.existsByTenantIdAndEmail(tenantId, email)) {
    repository.save(newCustomer);
}
```

không bảo đảm tính duy nhất:

```text
Request A: exists(email) -> false
Request B: exists(email) -> false
Request A: save(customer-A) -> thành công
Request B: save(customer-B) -> thành công
```

Cả hai request đều có thể quan sát chưa tồn tại trước khi ghi, và query index còn có thể cập nhật trễ. Đây là **race condition**; `existsBy...` thích hợp để trả thông báo gợi ý cho UI, nhưng **không thể thay thế thao tác ghi có điều kiện**.

Nếu cần uniqueness ở quy mô tenant + email, có thể cân nhắc thiết kế khóa document quyết định, document “reservation” riêng và thao tác **insert-if-absent** key-value, hoặc giao dịch và quy tắc đồng bộ phù hợp. Cần thiết kế chuẩn hóa email và xử lý xung đột khi ghi; không chỉ dựa vào query check.

## 5. Xóa theo document ID khác xóa theo bộ lọc

Trước khi bàn về `deleteBy...`, cần tách hai thao tác:

| Tác vụ | Đường truy cập | Đặc điểm |
| --- | --- | --- |
| `deleteById(id)` kế thừa repository | Chủ yếu key-value theo document ID | Nhắm đến một document đã biết khóa. |
| Xóa document theo `status = ARCHIVED` | Tìm bằng điều kiện trên trường JSON rồi xóa | Có thể ảnh hưởng nhiều document, liên quan Query Service/index hoặc nhiều thao tác key-value. |
| Xóa từng document với CAS | Key-value theo ID và CAS tương ứng | Giúp phát hiện thay đổi đồng thời trên từng document. |
| SQL++ `DELETE FROM ... WHERE ...` | DML theo điều kiện ở Query Service | Cần index, kiểm soát namespace, predicate và kết quả mutation. |

Biết ID và đã có quyết định xóa một document cụ thể thì `deleteById` có thể là phương án trực tiếp. Nếu ứng dụng đa tenant, **không được chỉ dựa vào ID do client gửi** mà bỏ qua kiểm tra quyền sở hữu document hoặc chính sách phân quyền.

Xóa theo điều kiện là thao tác có nguy cơ cao hơn truy vấn count/exists: một predicate thiếu tenant, sai dấu so sánh hoặc sai collection có thể xóa nhiều dữ liệu hơn dự kiến.

## 6. `deleteBy...` và `removeBy...`: tên method có nói đủ không?

Trong ngữ pháp Spring Data nói chung, `deleteBy...` và `removeBy...` biểu đạt ý định **xóa những entity thỏa điều kiện**. Có thể thấy chữ ký minh họa:

```java
// CHỈ LÀ VÍ DỤ Ý ĐỊNH.
// Phải xác minh hỗ trợ và ngữ nghĩa của phiên bản Spring Data Couchbase.
long deleteByTenantIdAndStatusAndArchivedAtBefore(
    String tenantId,
    String status,
    java.time.Instant cutoff
);
```

Nó được đọc là: xóa các customer có `tenantId`, `status` và `archivedAt < cutoff`. Tuy nhiên, **không nên đưa nguyên chữ ký này vào production mà chưa xác nhận Spring Data Couchbase hỗ trợ derived delete**; không phải mọi hình thức query derivation của Spring Data Commons đều có cùng implementation ở mọi data store.

Cần làm rõ bốn câu hỏi trên đúng phiên bản thư viện:

1. Parser có nhận diện `deleteBy...`/`removeBy...` là một truy vấn xóa hay không?
2. Thư viện thực thi **một SQL++ DELETE** hay **truy vấn tìm rồi xóa từng document**?
3. Kiểu trả về nào được phép: `void`, `long` số lượng, hoặc dạng khác? Có thật sự là **số document đã xóa** không?
4. Có áp dụng mapping, type discriminator, version/CAS, callback, auditing, transaction và query consistency giống đường xóa từng entity không?

Không được suy luận từ một tên method rằng SQL++ `DELETE`, callback hoặc optimistic locking sẽ diễn ra theo cách mong đợi. Nếu câu trả lời chưa rõ, hãy dùng API xóa tường minh đã được xác nhận, viết integration test và kiểm tra cả document trước/sau khi xóa.

### 6.1. Không đặt tên `deleteBy...` như lệnh xóa tự động an toàn

Phương thức:

```java
deleteByStatus("ARCHIVED");
```

thiếu tenant và ngưỡng thời gian; trên collection dùng chung cho nhiều tenant, có thể nhắm đến tất cả document ARCHIVED. Một API an toàn hơn phải mang các điều kiện bảo vệ, nhưng **thêm điều kiện vào tên method vẫn chưa đủ** nếu thiếu kiểm soát quyền, kiểm tra dữ liệu hoặc chấp thuận nghiệp vụ.

Với ví dụ này, không xóa khách hàng đang có `retention_hold = true`, cũng không tự xóa những document thiếu flag. Truy vấn xóa cần đưa chính sách vào predicate hoặc dùng quy trình thao tác an toàn tương đương.

## 7. SQL++ `DELETE` theo điều kiện: minh bạch và có kiểm soát

Khi cần dọn dữ liệu lưu trữ theo chính sách rõ ràng, có thể mô tả truy vấn SQL++ như sau:

```sql
-- MINH HỌA. Không chạy trên dữ liệu thật khi chưa có phê duyệt
-- và chưa xác minh namespace, predicates, quyền ghi, backup.
DELETE FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`status` = "ARCHIVED"
  AND c.`archived_at` < $cutoff
  AND c.`retention_hold` = false;
```

Điều kiện gồm:

- **Tenant:** chỉ xóa document của tenant được xác thực từ context server, không lấy tùy ý từ client.
- **Trạng thái:** chỉ cho phép trạng thái `ARCHIVED`.
- **Thời gian:** document phải lưu trữ trước mốc cutoff. Với `<`, document đúng bằng cutoff **không bị chọn**.
- **Cờ bảo vệ:** chỉ xóa khi field `retention_hold` hiện hữu và đúng Boolean `false`. Nếu `NULL` hoặc `MISSING`, điều kiện không được coi là true.

Nếu Spring Data Couchbase không hỗ trợ derived delete hoặc không kiểm soát đầy đủ ngữ nghĩa, có thể thực thi DML tường minh qua Query API của Couchbase SDK, `@Query` (khi phiên bản hỗ trợ câu lệnh DML và xử lý mutation đúng), hoặc API `CouchbaseTemplate` thích hợp. Tên API cụ thể và cách lấy mutation metrics cần đối chiếu tài liệu phiên bản đang dùng.

**Không giả định** một câu `DELETE` có cùng callback, mapping, CAS hoặc transaction với việc gọi `repository.delete(entity)` từng document. Đây là hai đường thao tác có thể có đặc tính khác nhau.

### 7.1. Đếm trước khi xóa bằng đúng predicate

Trước thao tác có tác động lớn, chạy một `SELECT COUNT` dùng **cùng điều kiện**:

```sql
SELECT COUNT(1) AS candidates
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`status` = "ARCHIVED"
  AND c.`archived_at` < $cutoff
  AND c.`retention_hold` = false;
```

Sau đó có thể kiểm tra mẫu document, ví dụ chỉ lấy ID và các trường quyết định xóa:

```sql
SELECT META(c).id AS documentId,
       c.`tenant_id` AS tenantId,
       c.`archived_at` AS archivedAt,
       c.`retention_hold` AS retentionHold
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`status` = "ARCHIVED"
  AND c.`archived_at` < $cutoff
  AND c.`retention_hold` = false
ORDER BY c.`archived_at` ASC
LIMIT 20;
```

Việc đọc mẫu và đếm là bước **kiểm tra trước**, không tạo bảo đảm rằng số document xóa sẽ chính xác bằng số đếm. Trong thời gian giữa hai truy vấn, document có thể bị cập nhật hoặc hết hạn.

### 7.2. Muốn biết đã xóa bao nhiêu?

Phân biệt:

- **Candidates:** số document khớp tại thời điểm truy vấn đếm.
- **Requested:** số ID hoặc tập điều kiện ứng dụng định xử lý.
- **Mutated/removed:** số document backend báo đã xóa thành công qua kết quả DML/SDK, nếu API cung cấp.
- **Visible afterward:** số document còn thấy qua query sau xóa, phụ thuộc consistency và việc dữ liệu tiếp tục thay đổi.

Không lấy `countBefore - countAfter` làm chỉ số duy nhất của số document đã xóa: document mới có thể xuất hiện, document khác có thể bị TTL xóa, và query index có thể đang cập nhật. Với DML, xem mutation metrics/`RETURNING` theo phiên bản; với key-value remove, ghi nhận kết quả từng thao tác.

### 7.3. Xóa theo lô thay vì quét toàn collection một lần

Khi số candidate lớn, nên cân nhắc:

1. Chọn một lô ID theo điều kiện và thứ tự xác định.
2. Giới hạn kích thước lô phù hợp năng lực hệ thống.
3. Kiểm tra lại điều kiện bảo vệ trước khi xóa nếu dữ liệu có thể thay đổi.
4. Xóa với chính sách cạnh tranh, retry và giám sát rõ ràng.
5. Ghi checkpoint để có thể tiếp tục mà không phải bắt đầu lại.

Nếu dùng SQL++ `DELETE ... LIMIT`, phải kiểm tra hỗ trợ trên phiên bản Couchbase và tránh giả định thứ tự chọn lô khi không có cơ chế xác định tương ứng. Một cách khác là phân trang theo khóa ID hoặc cutoff rồi xóa các document qua KV API với CAS, có kiểm tra từng bản ghi. Phương án tối ưu phụ thuộc yêu cầu độ chính xác, tải và mức nhất quán.

## 8. CAS, cập nhật đồng thời và lỗi `count → delete`

Xét tình huống quản trị viên đặt cờ `retention_hold = true` trong lúc tác vụ dọn dữ liệu chạy:

```text
T0: Job đếm thấy 100 document đủ điều kiện.
T1: Admin chuyển một document sang retention_hold=true.
T2: Job xóa theo danh sách ID đã lấy trước đó.
```

Nếu job chỉ lấy ID rồi xóa mà không kiểm tra trạng thái/cờ mới, nó có thể xóa document vừa được bảo vệ.

Có hai hướng cần phân biệt:

- **Xóa theo predicate được đánh giá lúc thực thi:** DML SQL++ có thể xem điều kiện hiện tại theo semantics của Query Service/transaction tương ứng; cần hiểu guarantees thực tế, đặc biệt với ghi đồng thời và index consistency.
- **Đọc rồi xóa theo ID:** nên cân nhắc CAS hoặc cơ chế atomic conditional operation để phát hiện document thay đổi kể từ lúc đọc.

CAS là cơ chế kiểm tra version của **một document**. Nó không tự biến xóa hàng nghìn document thành thao tác nguyên tử. Nếu cần nhất quán nhiều document hoặc bảo đảm chính sách nghiêm ngặt, phải thiết kế transaction/quy trình phối hợp phù hợp với phạm vi hỗ trợ của Couchbase.

### 8.1. Không dùng `existsBy...` làm khóa

Ví dụ `existsById(id)` trả true ngay trước khi xóa không bảo đảm `deleteById(id)` chắc chắn thành công: document có thể được xóa hoặc sửa trong khoảng thời gian giữa hai lời gọi. Trạng thái “đã tồn tại” chỉ là một quan sát tại thời điểm đọc.

Khi xử lý xóa idempotent, cần xác định cách ứng xử với document đã không còn tồn tại, xung đột CAS hoặc lỗi tạm thời. Không biến lỗi hệ thống thành “đã xóa” khi không có bằng chứng thao tác hoàn tất.

## 9. `NULL`, `MISSING` và kiểm tra kiểu trong điều kiện xóa

Couchbase cho phép document có cấu trúc không đồng nhất:

```json
{"retention_hold": false}
```

```json
{"retention_hold": true}
```

```json
{"retention_hold": null}
```

```json
{}
```

Nếu chính sách là “chỉ xóa khi cờ bảo vệ được lưu rõ `false`”, điều kiện `c.retention_hold = false` có ưu điểm **không mặc định coi null/missing là false**.

Tuy nhiên, nếu legacy data có `retention_hold = "false"` (chuỗi), nó cũng không nên được coi như Boolean false khi quyết định xóa. Hãy chuẩn hóa dữ liệu hoặc xác định quy tắc migration trước khi vận hành.

Mốc thời gian `archived_at` cũng có thể `NULL`, `MISSING` hoặc sai kiểu. Điều kiện so sánh ngày trên trường sai kiểu có thể không phản ánh tuổi lưu trữ. Đặc biệt, một số document được ghi bằng converter khác có thể lưu timestamp thành số thay vì chuỗi; không được trộn kiểu rồi dựa vào `< cutoff` để xóa an toàn.

**Không dùng điều kiện quá rộng** như `status != "ACTIVE"` để suy ra “được phép xóa”: nó có thể chọn nhiều trạng thái không mong muốn và có ngữ nghĩa đặc biệt với null/missing. Luôn dùng **danh sách trạng thái cho phép được xóa** và điều kiện bảo vệ rõ ràng.

## 10. Bộ dữ liệu kiểm thử count, exists và delete

Giả sử cutoff là **2026-09-01T00:00:00Z** và chính sách cho phép dọn document `ARCHIVED` cũ của tenant-a với `retention_hold = false`.

| ID | Tenant | Status | `archived_at` | Hold | Hợp lệ để xóa? |
| --- | --- | --- | --- | --- | :---: |
| `c01` | tenant-a | ARCHIVED | 2026-08-15 | false | ✓ |
| `c02` | tenant-a | ARCHIVED | 2026-10-01 | false | ✗ — chưa đủ hạn |
| `c03` | tenant-a | ARCHIVED | 2026-08-01 | true | ✗ — đang giữ |
| `c04` | tenant-a | ACTIVE | 2026-07-01 | false | ✗ — sai trạng thái |
| `c05` | tenant-b | ARCHIVED | 2026-08-01 | false | ✗ — tenant khác |
| `c06` | tenant-a | ARCHIVED | 2026-08-30 | false | ✓ |
| `c07` | tenant-a | ARCHIVED | 2026-08-05 | MISSING | ✗ — chưa xác thực hold |
| `c08` | tenant-a | ARCHIVED | NULL | false | ✗ — không rõ mốc lưu trữ |

Từ bộ dữ liệu này:

| Truy vấn logic | Kết quả kỳ vọng |
| --- | --- |
| `countByTenantIdAndStatus("tenant-a", "ARCHIVED")` | `6`: `c01`, `c02`, `c03`, `c06`, `c07`, `c08` |
| `existsByTenantIdAndStatus("tenant-b", "ARCHIVED")` | `true` do có `c05` |
| `existsByTenantIdAndStatus("tenant-b", "ACTIVE")` | `false` |
| Đếm với tenant-a, status ARCHIVED, archived_at trước cutoff, hold=false | `2`: `c01`, `c06` |
| Xóa với **đúng cùng bộ lọc** và không có ghi cạnh tranh | Chỉ `c01` và `c06` bị xóa |

Lưu ý `countByTenantIdAndStatusAndArchivedAtBefore` **chưa đủ** để quyết định xóa: nó còn có thể tính cả `c03` có hold=true và `c07` có hold missing. Nếu dùng derived query, phải biểu diễn **tất cả điều kiện an toàn** và kiểm tra keyword hỗ trợ; nếu không, dùng truy vấn tường minh.

### 10.1. Giá trị biên

Nếu một document ARCHIVED có `archived_at` **đúng bằng cutoff**, điều kiện `< cutoff` sẽ **không** chọn document. Nếu yêu cầu nghiệp vụ là “trước hoặc bằng”, dùng `<=` và kiểm tra lại. Một lỗi ranh giới một ngày hoặc một mili giây trong job xóa có tác động nghiêm trọng hơn một lỗi lọc khi hiển thị danh sách.

## 11. Index cho count, exists và delete theo điều kiện

Truy vấn theo trường nội dung thường đi qua SQL++/Query Service, cần index phù hợp. Các thao tác `countBy`, `existsBy` và DML `DELETE` có thể có cách thực thi khác nhau, nhưng đều hưởng lợi từ việc **truy cập nhanh tới tập document thỏa predicate**.

Giả sử các query thực tế có type discriminator qua `_class`, một composite index minh họa:

```sql
CREATE INDEX ix_customers_type_tenant_status_hold_date
ON `app`.`crm`.`customers`(
    `_class`,
    `tenant_id`,
    `status`,
    `retention_hold`,
    `archived_at`
);
```

Ý định: các field equality như tenant, status, hold đứng trước field range `archived_at`. Nhưng index tối ưu phụ thuộc độ chọn lọc, phân bố dữ liệu, điều kiện do framework sinh ra và phiên bản Couchbase.

- Nếu ứng dụng không dùng `_class` như ví dụ, không áp dụng index có discriminator theo giả định này.
- Nếu `archived_at` có nhiều giá trị `MISSING`, phải kiểm tra index có bao phủ tập document mong muốn và kế hoạch Query Service.
- `existsByTenantIdAndEmail` có thể cần index riêng hướng đến `tenant_id + email` khi truy vấn thường xuyên.
- Index càng nhiều, chi phí ghi và dung lượng càng lớn; tránh tạo index riêng cho mỗi chữ ký repository.
- Với xóa số lượng lớn, cần tính tải dọn dữ liệu và ảnh hưởng đến index, không chỉ tối ưu truy vấn tìm candidate.

### 11.1. Dùng `EXPLAIN` cho truy vấn đếm và DML

```sql
EXPLAIN
SELECT COUNT(1) AS candidates
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`status` = "ARCHIVED"
  AND c.`archived_at` < $cutoff
  AND c.`retention_hold` = false;
```

Khi phân tích thật, sử dụng SQL++ tương đương query do framework thực thi, bao gồm discriminator và tên trường JSON đã mapping. Kiểm tra index scan, mức bao phủ, fetch, độ trễ và số document phù hợp.

Có thể xem `EXPLAIN` của DML nếu server/phiên bản hỗ trợ, nhưng đừng dùng lệnh `DELETE` trực tiếp để “kiểm tra kế hoạch” trên dữ liệu sống. Chỉ chạy hành động gây thay đổi dữ liệu trong quy trình được kiểm soát; `EXPLAIN` không thay thế bảo đảm quyền và predicate đúng.

## 12. TTL và sự khác biệt giữa xóa chủ động với hết hạn tự động

Couchbase hỗ trợ TTL cho document. Nếu retention policy chỉ nhằm giữ dữ liệu trong một thời gian cố định, đôi khi có thể dùng **expiration** thay vì quét `status` và xóa thủ công. Nhưng hai cách không giống nhau:

| Xóa chủ động theo điều kiện | TTL của document |
| --- | --- |
| Chỉ chạy khi job/application quyết định xóa | Document hết hạn theo cấu hình expiration |
| Có thể phụ thuộc trạng thái ARCHIVED, tenant, retention_hold | Cần thiết kế TTL để phản ánh chính sách; TTL không tự suy ra mọi điều kiện nghiệp vụ |
| Có thể cần dry-run, audit và phê duyệt | Cần kiểm tra cách expiration ảnh hưởng mục tiêu lưu trữ |
| Có thể trả mutation outcome từ job | Hết hạn không tự gửi về repository một kết quả `deleteBy...` tương ứng |

Một document có `retention_hold = true` nhưng TTL vẫn được cấu hình ngắn có thể hết hạn trái chính sách nếu không thiết kế đường ghi/TTL hợp lý. TTL không mặc nhiên được “tạm dừng” bởi field giữ dữ liệu. Vì vậy cần quản trị TTL, trạng thái và lịch sử thay đổi chính sách cùng nhau.

Trong lúc job chạy, document khác có thể hết hạn làm kết quả `countBy...` thay đổi ngay cả khi job chưa xóa gì.

## 13. Giao dịch, nhất quán và phạm vi bảo đảm

### 13.1. Count và delete thường không tạo snapshot chung

Chuỗi:

```text
T0: count candidates = 100
T1: một document được cập nhật retention_hold = true
T2: DELETE theo predicate
T3: count candidates = 0 hoặc một số khác
```

không tự nằm trong một giao dịch nguyên tử. Ngay cả khi cả hai query dùng consistency cao hơn, vẫn có thể có tác vụ khác cập nhật document giữa chúng. Mức query scan consistency như dạng `REQUEST_PLUS` có thể giúp đợi index bắt kịp mutation theo semantics của phiên bản, nhưng **không biến nhiều request thành một transaction**.

Nếu cần tính nguyên tử trên nhiều document, phải thiết kế giao dịch theo khả năng thực tế của Couchbase SDK và Spring Data phiên bản đang dùng, cùng giới hạn hiệu năng, thời gian và kích thước. Không cho rằng derived `deleteBy...` tự mở transaction vì có chữ “delete”.

### 13.2. Dữ liệu vừa ghi và tác vụ kiểm tra tồn tại

```text
save(customer)                     -> ghi key-value thành công
findById(customer.id)              -> đọc theo ID
existsByTenantIdAndEmail(...)      -> SQL++ qua index
countByTenantIdAndStatus(...)      -> SQL++ qua index
```

Ngay sau `save`, exists/count theo field có thể chưa phản ánh ghi mới tại mức consistency thông thường. Nếu cần read-your-own-write, chọn query scan consistency phù hợp hoặc dùng đường KV theo ID; không thể chỉ tăng độ chờ tùy tiện mà không đánh giá tải và yêu cầu đúng đắn.

### 13.3. Namespace và phân quyền

Một truy vấn count, exists hoặc delete nhắm vào **bucket/scope/collection** theo mapping và cấu hình. Nếu dùng SQL++ tường minh, namespace có thể được chỉ ra trực tiếp. Phải đảm bảo collection đúng và user Couchbase chỉ được cấp quyền cần thiết.

Trong ứng dụng đa tenant, điều kiện `tenant_id` phải đến từ **context xác thực được server kiểm soát**, không chỉ từ tham số client. Đặc biệt với job dọn dữ liệu, cần giới hạn quyền vận hành, log audit và cơ chế tạm dừng.

## 14. Reactive: `Mono<Boolean>`, `Mono<Long>` và xóa bất đồng bộ

Repository reactive dùng Reactor để biểu diễn kết quả theo kiểu bất đồng bộ và không chặn:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    // Các chữ ký minh họa: xác minh dạng derived query
    // và kiểu trả về theo phiên bản Spring Data Couchbase.
    Mono<Long> countByTenantIdAndStatus(
        String tenantId,
        String status
    );

    Mono<Boolean> existsByTenantIdAndEmail(
        String tenantId,
        String email
    );
}
```

`Mono<Boolean>` và `Mono<Long>` thể hiện một kết quả logic sau khi publisher hoàn tất. `ReactiveCouchbaseRepository` còn có các operation xóa theo ID/entity do interface cung cấp, nhưng **không tự đồng nghĩa hỗ trợ mọi dạng derived delete theo điều kiện**.

Với API xóa reactive, chỉ được xác nhận thành công khi publisher phát tín hiệu hoàn tất hoặc có kết quả operation được kiểm tra. Không coi việc tạo một `Mono` hay đăng ký job là bằng chứng document đã bị xóa.

**Một ví dụ sai về bảo đảm:** gọi `existsBy...` rồi `flatMap` sang `save` vẫn không loại bỏ race condition kiểm tra-rồi-ghi. Reactive là mô hình tiêu thụ và phối hợp thao tác, không tự tạo ràng buộc uniqueness hay transaction.

Tránh gọi `block()` trong luồng web reactive nếu không có kiến trúc cô lập blocking phù hợp.

## 15. Thiết kế quy trình xóa an toàn trong sản phẩm

Trước một batch job xóa theo điều kiện, cần một quy trình có thể xem xét và truy vết:

1. **Chốt phạm vi:** namespace, tenant, trạng thái được phép xóa, chính sách hold và cutoff; chỉ định người/phần hệ thống có thẩm quyền.
2. **Kiểm tra input:** không cho cutoff tương lai ngoài chính sách, không cho tenant rỗng, không dùng status tùy ý.
3. **Dry-run:** đếm candidate và lấy mẫu ID bằng cùng predicate, có kiểm tra dữ liệu ngoại lệ.
4. **Phê duyệt hoặc cơ chế kiểm soát:** theo độ nhạy dữ liệu và yêu cầu nội bộ, đảm bảo có quyền phù hợp trước khi chạy.
5. **Chọn kỹ thuật thực thi:** SQL++ DELETE, thao tác KV có CAS, hoặc workflow transaction theo yêu cầu; kiểm tra hỗ trợ SDK/phiên bản.
6. **Giới hạn lô:** chia nhỏ khi dữ liệu lớn, theo dõi tải Query Service và index; cân nhắc rate-limit/backpressure.
7. **Quan sát kết quả:** ghi số candidate, mutation metrics, số lỗi, document ID theo chính sách audit; không tự đồng nhất candidate với success.
8. **Idempotency và retry:** xử lý document đã mất, CAS conflict, timeout, partial failure; retry đúng mục tiêu tránh xóa quá phạm vi.
9. **Xác minh sau thao tác:** dùng query consistency phù hợp để kiểm tra candidate còn lại, đối chiếu với mutation metrics và log.
10. **Khả năng khôi phục:** chuẩn bị chính sách sao lưu/retention hoặc soft delete phù hợp trước khi chọn hard delete.

### 15.1. Soft delete thay vì hard delete khi cần khôi phục

Một số nghiệp vụ nên cập nhật `status = DELETED` hoặc `deleted_at` thay vì xóa document ngay. Cách này cho phép phục hồi và lưu lịch sử trong một khoảng thời gian, nhưng cũng phải thiết kế:

- Mọi query hiển thị có loại document đã xóa mềm không?
- Index của luồng đang hoạt động có lọc `deleted_at` hợp lý không?
- Khi nào document được hard delete/TTL theo chính sách?
- Các thao tác ghi đồng thời có thể “hồi sinh” document đã soft delete không?
- Có yêu cầu bảo mật phải xóa hoàn toàn dữ liệu sau thời hạn hay không?

Soft delete và TTL cần được lựa chọn theo yêu cầu retention, audit và pháp lý thực tế; không chỉ theo sự thuận tiện của repository.

## 16. Khi nào nên ưu tiên `@Query` hoặc `CouchbaseTemplate`?

| Tình huống | Lựa chọn nên xem xét |
| --- | --- |
| Chỉ đếm theo một vài trường đơn giản | `countBy...` |
| Chỉ kiểm tra ít nhất một document | `existsBy...` |
| Xóa một document theo ID đã được xác thực | `deleteById`/KV API |
| Xóa theo bộ lọc nhưng derived delete không hỗ trợ hoặc semantics không rõ | SQL++ DML tường minh qua API được hỗ trợ |
| Bộ lọc xóa có tenant, giữ dữ liệu, cutoff và điều kiện tùy chọn | `CouchbaseTemplate`/query builder/SDK Query API thích hợp |
| Cần count theo nhóm, projection phức tạp | SQL++ `GROUP BY` qua `@Query` hoặc query API |
| Cần CAS hoặc retry theo document | Key-value API có khả năng kiểm tra xung đột |
| Cần kiểm soát nhiều thay đổi nguyên tử | Transaction API phù hợp với phiên bản và giới hạn hệ thống |

`@Query` cho phép diễn đạt truy vấn cố định rõ hơn, nhưng khả năng dùng câu lệnh DML qua annotation phải được kiểm tra đúng phiên bản Spring Data Couchbase. Không giả định `@Query("DELETE ...")` luôn hoạt động giống một repository method trả entity.

`CouchbaseTemplate` và SDK Query API giúp kiểm soát cấu trúc điều kiện và options chi tiết, song vẫn cần binding tham số, kiểm tra quyền và xử lý kết quả. Không dùng query text tự nối từ input người dùng cho các điều kiện quan trọng.

## 17. Bài tập vận dụng

Dùng bảng `c01`–`c08` ở mục 10 và cutoff `2026-09-01T00:00:00Z`.

**Bài A — Đếm:** Chỉ muốn biết tenant-a có bao nhiêu document ARCHIVED (không xét tuổi và hold). Phương thức `countByTenantIdAndStatus("tenant-a", "ARCHIVED")` dự kiến trả `6`. Giải thích vì sao con số này **không** được dùng trực tiếp như số candidate được phép xóa.

**Bài B — Tồn tại:** Tenant-b có document ARCHIVED hay không? `existsByTenantIdAndStatus("tenant-b", "ARCHIVED")` dự kiến là `true`, nhưng điều này không cho biết document có đủ điều kiện lưu trữ để xóa hay không.

**Bài C — Lọc an toàn:** Viết một câu SQL++ `COUNT` trả số document của tenant-a có status ARCHIVED, archived_at trước cutoff, retention_hold=false. Kết quả trên bảng phải là `2`.

**Bài D — Xóa an toàn:** Dùng **đúng cùng predicate** trong câu `DELETE` và xác nhận chỉ `c01`, `c06` là mục tiêu khi không có ghi cạnh tranh. Vì sao `c07` không được chọn? — Vì `retention_hold` của document này là `MISSING`, không được coi bằng Boolean false.

**Bài E — Race condition:** A và B đồng thời gọi `existsByTenantIdAndEmail`, đều nhận false rồi cùng `save` email mới. Hãy đề xuất cơ chế kiểm soát uniqueness ở đường ghi, thay vì xem `existsBy...` là khóa.

**Bài F — Count trước/sau:** Giả sử trước job có 2 candidate, trong lúc job chạy một document khác hết hạn TTL và một document mới chuyển sang ARCHIVED. Vì sao `countBefore - countAfter` không chứng minh chắc chắn số document job đã xóa? — Vì tập dữ liệu đang thay đổi độc lập với job và query index có thể không đồng bộ ngay.

**Bài G — Khi derived delete không được hỗ trợ:** Nêu cách triển khai thay thế đảm bảo điều kiện tenant, cutoff và hold rõ ràng, dùng SQL++ DML hoặc danh sách document ID với kiểm tra CAS; kiểm tra outcome và chỉ báo hoàn tất sau khi operation trả kết quả thành công.

### Bảng kiểm trước khi triển khai

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Chỉ cần `boolean` hay `long`? | Chọn `existsBy` hoặc `countBy`, không tải toàn bộ entity. |
| Có đang dùng count như phép bảo đảm uniqueness? | Count/exists không thay khóa/transaction ở đường ghi. |
| `deleteBy...` có thật được Couchbase repository hỗ trợ? | Kiểm tra phiên bản, SQL++ được sinh, kiểu trả về và callback/CAS. |
| Có điều kiện tenant/retention hold/cutoff? | Tránh xóa nhầm toàn collection hoặc document được bảo vệ. |
| Field `NULL`/`MISSING` hoặc sai kiểu? | Không tự xem thiếu hold là false hay thiếu ngày là quá hạn. |
| Có đếm và kiểm tra mẫu bằng cùng predicate? | Giảm rủi ro xóa rộng hơn dự kiến. |
| Có tác vụ ghi đồng thời? | Kiểm soát race, CAS, transaction và partial failure. |
| Kết quả mutation có được kiểm tra không? | Không lấy số đếm trước xóa làm số xóa thành công. |
| Index hỗ trợ COUNT/EXISTS/DELETE không? | Tránh full scan và kiểm tra `EXPLAIN`. |
| Job có giới hạn lô, rate-limit và audit? | Bảo vệ hiệu năng, quyền và khả năng phục hồi. |
| Consistency và TTL có được xét đến? | Hiểu vì sao số lượng biến đổi giữa các lần kiểm tra. |
| Có khả năng khôi phục hoặc soft delete khi cần? | Hard delete có thể không đảo ngược được. |

## 18. Ghi nhớ

**`countBy...`** trả số lượng document thỏa điều kiện, **`existsBy...`** trả câu trả lời có/không, còn **`deleteBy...`** diễn đạt ý định xóa theo predicate trong ngữ pháp Spring Data nhưng phải **xác minh khả năng hỗ trợ và ngữ nghĩa thực thi của Spring Data Couchbase theo phiên bản**. Không lấy `findBy...().size()` để đếm tập lớn, không dùng `existsBy...` làm khóa bảo đảm uniqueness và không coi `countBefore` là số document đã xóa.

Xóa theo điều kiện là **thao tác thay đổi dữ liệu có rủi ro cao**: phải giới hạn namespace/tenant, trạng thái, thời gian, cờ bảo vệ, chuẩn hóa dữ liệu và quyền truy cập. Kiểm tra JSON `NULL`/`MISSING`, index, `EXPLAIN`, query consistency, TTL, CAS và giao dịch trước khi vận hành. Khi derived query không thể biểu đạt an toàn, dùng SQL++ tường minh qua `@Query`, `CouchbaseTemplate` hoặc SDK API được hỗ trợ, chia lô, kiểm tra kết quả mutation và giữ cơ chế audit/khôi phục phù hợp.
