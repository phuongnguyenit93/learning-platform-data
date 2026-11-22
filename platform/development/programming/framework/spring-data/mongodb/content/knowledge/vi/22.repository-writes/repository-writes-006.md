# Phương thức delete suy diễn và kiểu dữ liệu trả về

## 1. Vấn đề: xóa theo điều kiện khác xóa theo ID

Trong một ứng dụng Spring Data MongoDB, việc xóa một document theo ID khá đơn giản: gọi **deleteById(id)** trên repository. Tuy nhiên, nghiệp vụ thường yêu cầu xóa theo điều kiện, chẳng hạn:

- Xóa các phiếu hỗ trợ có **status = EXPIRED** của một tenant.
- Xóa các bản ghi nháp được tạo trước một mốc thời gian.
- Xóa dữ liệu thử nghiệm theo một nhãn phân loại đã kiểm soát.
- Xóa một nhóm document và cần biết **đã xóa bao nhiêu**, hoặc cần giữ **danh sách nội dung vừa xóa** để ghi nhận nghiệp vụ.

Spring Data MongoDB hỗ trợ **derived delete queries**: khai báo phương thức repository có tiền tố **delete...By** hoặc **remove...By**; framework suy ra filter từ tên phương thức. Đáng chú ý, **kiểu dữ liệu trả về** có thể làm thay đổi cách thực hiện thao tác: trả số lượng document bị xóa, hoặc truy xuất và trả các entity được chọn để xóa.

Bài **Phương thức delete suy diễn và kiểu dữ liệu trả về** nằm trong chương **Ghi qua repository** của module **SPRING_DATA_MONGODB**. Module sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua MongoTemplate hoặc repository; kiến thức này hỗ trợ thiết kế truy vấn, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài học, bạn có thể:

1. Đọc và viết tên method **deleteBy...**, **removeBy...**, **deleteAllBy...**.
2. Phân biệt return type **long/Long** và **List<Entity>** cho derived delete.
3. So sánh derived delete với **deleteById**, **delete(entity)** và **MongoTemplate.remove**.
4. Hiểu rằng trả lại entity đã xóa có thể cần **đọc dữ liệu trước khi xóa**, không có nghĩa toàn thao tác là một transaction.
5. Bảo vệ filter theo tenant, trạng thái và điều kiện thời gian.
6. Thiết kế xóa khối lượng lớn, phân quyền, retry, soft delete và optimistic locking đúng yêu cầu.
7. Kiểm thử kết quả xóa thực tế và xác minh không ảnh hưởng document ngoài phạm vi.

## 2. Document mẫu: phiếu hỗ trợ

Giả sử dịch vụ có collection **support_tickets**:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  status: "EXPIRED",
  category: "RETURN",
  subject: "Yêu cầu đổi hàng",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Document khác thuộc một tenant khác:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-b",
  status: "EXPIRED",
  category: "RETURN",
  subject: "Hỏi về giao hàng",
  createdAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

Yêu cầu quan trọng: khi xóa các ticket đã hết hạn của **shop-a**, tuyệt đối không được xóa ticket của **shop-b**, dù chúng có cùng status.

Entity Java:

~~~java
package com.example.support;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "support_tickets")
public record TicketDocument(
    @Id ObjectId id,
    String tenantId,
    String status,
    String category,
    String subject,
    Instant createdAt
) {}
~~~

Annotation **@Document** xác định collection; **@Id** ánh xạ property Java **id** sang BSON **_id**. Các property khác trong ví dụ dùng tên BSON giống tên Java. Mốc thời gian là Instant/BSON Date để tránh nhầm với chuỗi ngày giờ thông thường.

## 3. Repository tối giản và các phương thức delete suy diễn

~~~java
package com.example.support;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface TicketRepository
        extends MongoRepository<TicketDocument, ObjectId> {

    long deleteByTenantIdAndStatus(
        String tenantId,
        String status
    );

    List<TicketDocument> removeByTenantIdAndCategory(
        String tenantId,
        String category
    );

    long deleteByTenantIdAndStatusAndCreatedAtBefore(
        String tenantId,
        String status,
        Instant cutoff
    );

    List<TicketDocument> findByTenantId(String tenantId);
}
~~~

**Không cần tự viết class implementation** cho ba derived delete methods trên trong một cấu hình repository MongoDB hợp lệ. Spring Data phân tích tên phương thức và xây thao tác phù hợp qua repository infrastructure.

Tên method mô tả:

- **deleteByTenantIdAndStatus**: xóa những Ticket có tenantId và status tương ứng.
- **removeByTenantIdAndCategory**: xóa những Ticket có tenantId và category tương ứng, đồng thời trả entity được chọn để xóa.
- **deleteByTenantIdAndStatusAndCreatedAtBefore**: xóa những Ticket thuộc tenant, có status nhất định và createdAt trước cutoff.
- **findByTenantId**: phương thức đọc dùng để đối chiếu hoặc kiểm thử; không xóa gì.

**Phần lớn ví dụ dùng chữ ký trả long hoặc List<TicketDocument>**, vì đây là hai nhóm kết quả đặc trưng và cần hiểu rõ. Các return type khác phải được xét theo hợp đồng repository, phiên bản Spring Data và cách ứng dụng muốn sử dụng kết quả.

## 4. Ngôn ngữ của tên method: deleteBy và removeBy

Spring Data nhận diện các tiền tố delete/remove trong phương thức suy diễn. Ví dụ:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);

long removeByTenantIdAndStatus(
    String tenantId, String status
);
~~~

Với cùng điều kiện và cùng return type, hai chữ ký này thể hiện cùng ý định xóa theo filter. Việc chọn từ **delete** hay **remove** chủ yếu là quy ước đặt tên nhóm API; không nên gán ý nghĩa “delete là hard delete, remove là soft delete”.

### 4.1. All không có nghĩa xóa toàn collection khi vẫn có filter

~~~java
long deleteAllByTenantIdAndStatus(
    String tenantId, String status
);
~~~

Trong phương thức suy diễn, **All** có thể là từ mô tả của phần chủ ngữ. Truy vấn vẫn chứa các predicate sau **By**. Nó không đồng nghĩa lệnh **repository.deleteAll()** không có điều kiện.

So sánh:

| Method | Phạm vi |
| --- | --- |
| deleteByTenantIdAndStatus("shop-a", "EXPIRED") | Document khớp tenant và status |
| deleteAllByTenantIdAndStatus("shop-a", "EXPIRED") | Cùng kiểu filter suy diễn |
| deleteById(id) | Document theo ID |
| deleteAll() | Toàn bộ các document repository đang quản lý, không có filter nghiệp vụ |

**Không tạo method xóa không có điều kiện để tiết kiệm vài ký tự.** Với dữ liệu nhiều tenant, filter theo tenant là ranh giới an toàn quan trọng.

### 4.2. Predicate theo property Java

Tên method được phân tích theo **property của entity Java**, không phải việc nối chuỗi tùy ý. Ví dụ createdAt dùng tên Java, còn MongoDB lưu một BSON Date có tên tương ứng.

~~~java
long deleteByTenantIdAndCreatedAtBefore(
    String tenantId,
    Instant cutoff
);
~~~

Framework diễn đạt một điều kiện tương tự:

~~~javascript
db.support_tickets.deleteMany({
  tenantId: "shop-a",
  createdAt: { $lt: ISODate("2025-07-01T00:00:00Z") }
});
~~~

Đây là **hình dung ngữ nghĩa filter**, không phải khẳng định mọi return type derived delete đều chạy một lệnh deleteMany giống hệt. Chiến lược thực thi thay đổi theo kiểu kết quả; phần tiếp theo là điểm cốt lõi.

## 5. Long/long: trả số document bị xóa

Khi caller cần biết **đã xóa bao nhiêu document**, hãy chọn chữ ký có return type dạng số lượng:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

Trong service:

~~~java
public long purgeExpired(String tenantId) {
    return repository.deleteByTenantIdAndStatus(
        tenantId,
        "EXPIRED"
    );
}
~~~

Giả sử trước khi gọi có bảy ticket EXPIRED thuộc shop-a và ba ticket EXPIRED thuộc shop-b. Nếu không có ghi đồng thời và tất cả thao tác thành công, kết quả có thể là:

~~~text
purgeExpired("shop-a") -> 7
~~~

Chỉ những ticket của shop-a khớp filter mới được xóa. Giá trị **7** là **số document mà thao tác xóa báo đã xóa**, không phải số phần tử của collection sau khi xóa.

### 5.1. long và Long khác nhau thế nào ở Java?

~~~java
long deleteByTenantIdAndStatus(String tenantId, String status);

Long removeByTenantIdAndStatus(String tenantId, String status);
~~~

**long** là primitive; **Long** là wrapper. Với derived delete đếm số document đã xóa, cả hai có thể thể hiện cùng ý nghĩa số lượng trong hợp đồng repository thông dụng.

Nếu ứng dụng không có ý định trả null, **long** là lựa chọn gọn và dễ hiểu. Không sử dụng nullable Long để ngụ ý “chưa chạy xóa”: thao tác repository có thể hoàn thành hợp lệ với **0** bản ghi bị xóa.

### 5.2. Số 0 không nhất thiết là lỗi

~~~text
deleteByTenantIdAndStatus("shop-a", "EXPIRED") -> 0
~~~

Điều này có thể có nghĩa:

- Không còn ticket nào khớp filter.
- Ticket đã được xóa ở lần chạy trước.
- Status hoặc tenant không đúng.
- Các ticket đã đổi trạng thái trước lúc xóa.

**0 là một kết quả hợp lệ ở tầng database.** Tầng nghiệp vụ quyết định nên trả “không có gì để xóa”, HTTP 200 với deletedCount=0, hay một lỗi điều kiện không thỏa. Đừng mặc định xóa 0 document đồng nghĩa database lỗi.

### 5.3. Đếm số lượng bị xóa khác count trước khi xóa

Không nên viết:

~~~java
long totalBefore = repository.countByTenantIdAndStatus(
    tenantId, "EXPIRED"
);
repository.deleteByTenantIdAndStatus(tenantId, "EXPIRED");
return totalBefore;
~~~

Nếu có writer khác giữa **count** và **delete**, số đếm trước đó có thể không đúng với số thực sự bị xóa. Nếu nghiệp vụ cần kết quả của thao tác xóa, hãy **trả trực tiếp giá trị derived delete**.

## 6. List<Entity>: trả lại những entity được chọn để xóa

Khi caller cần nội dung của những ticket bị xóa, khai báo:

~~~java
List<TicketDocument> removeByTenantIdAndCategory(
    String tenantId,
    String category
);
~~~

Ví dụ:

~~~java
List<TicketDocument> removed =
    repository.removeByTenantIdAndCategory(
        "shop-a",
        "TEST"
    );

for (TicketDocument ticket : removed) {
    auditLogger.recordDeletedTicket(
        ticket.id(),
        ticket.subject()
    );
}
~~~

**auditLogger** là dependency minh họa của tầng ứng dụng. Danh sách **removed** chứa các entity được truy xuất cho hoạt động xóa, nên ứng dụng có thể đọc thông tin như ID, subject hay createdAt từ chúng.

Khác với dạng trả số lượng, việc trả **List<TicketDocument>** yêu cầu có dữ liệu entity để trả. Vì MongoDB deleteOne/deleteMany thông thường chỉ trả kết quả đếm, Spring Data cần một chiến lược **tìm các entity phù hợp rồi xóa** (hoặc cơ chế tương đương của phiên bản triển khai).

### 6.1. Danh sách trả về là nội dung trước khi bị xóa

Với ba ticket TEST:

~~~text
removeByTenantIdAndCategory("shop-a", "TEST")
    -> [TicketA, TicketB, TicketC]
~~~

Sau thao tác thành công, các document tương ứng không còn trong collection theo điều kiện xóa. List trả về là **dữ liệu đọc được của các entity liên quan**, không phải những entity vẫn đang hiện diện trong MongoDB.

**Không nên dựa vào thứ tự List nếu phương thức không quy định sort**, vì thứ tự kết quả của truy vấn không mặc nhiên là hợp đồng ổn định.

### 6.2. Danh sách không phải bằng chứng giao dịch snapshot

Giả sử Spring Data phải tìm document rồi mới xóa. Giữa hai bước, một writer khác có thể cập nhật hoặc xóa document phù hợp. Khi đó, danh sách đã đọc và trạng thái xóa thực tế có thể không phản ánh cùng một snapshot.

**Không cam kết mỗi phần tử trong List là một bản ghi đã bị xóa thành công và được khóa tại thời điểm đọc**, trừ khi hệ thống có bảo đảm rõ ràng từ transaction/cơ chế thực thi đã kiểm chứng.

Nếu ứng dụng bắt buộc ghi nhận chính xác nội dung bị xóa, cần một kiến trúc audit/transaction hoặc outbox phù hợp, không chỉ đổi return type thành List rồi xem là bảo đảm atomicity.

### 6.3. Chi phí khác biệt với trả số

| Khía cạnh | long/Long | List<Entity> |
| --- | --- | --- |
| Dữ liệu trả về cho Java | Một số lượng | Nhiều entity |
| Nhu cầu đọc entity trước khi xóa | Không cần để dựng return value | Có thể cần đọc dữ liệu trước |
| Chi phí RAM của caller | Nhỏ | Tăng theo số entity trả |
| Chi phí mạng và mapping | Thường thấp hơn | Có thể cao hơn đáng kể |
| Có sẵn nội dung phục vụ audit? | Không | Có dữ liệu entity |
| Nên dùng xóa khối lượng rất lớn? | Thường phù hợp hơn | Phải kiểm soát giới hạn và bộ nhớ |

Nếu chỉ cần **deletedCount**, chọn kiểu trả số. Nếu thật sự cần dữ liệu trước khi xóa, chọn List với giới hạn, quy trình audit và bảo đảm nhất quán phù hợp.

## 7. Một return type không thay thế kiểm thử ngữ nghĩa

Tên method giống nhau nhưng kiểu trả về khác có thể khiến Spring Data lựa chọn đường thực thi khác nhau:

~~~java
// Method 1: muốn biết số document bị xóa.
long deleteByTenantIdAndStatus(String tenantId, String status);

// Method 2: muốn nhận danh sách entity liên quan đến xóa.
List<TicketDocument> removeByTenantIdAndCategory(
    String tenantId, String category
);
~~~

Không nên suy rằng:

- Phương thức trả List luôn chỉ là **deleteMany + trả danh sách do driver tự tạo**.
- Phương thức trả số luôn tạo trước một List rồi gọi **size()**.
- Hai kiểu trả về có chi phí, event và transaction semantics giống nhau.

Spring Data có thể triển khai khác nhau theo store, phiên bản và return type. Trong ứng dụng production, cần kiểm thử trên phiên bản **Spring Data MongoDB và MongoDB Server đang sử dụng**, đặc biệt khi dựa vào entity callback, auditing hoặc transaction.

### 7.1. Các return type khác

Một số thiết kế repository có thể sử dụng **void** khi caller không cần biết số lượng. Tuy nhiên, với logic xóa theo điều kiện, **long/Long và List<Entity>** làm hợp đồng rõ hơn: hoặc lấy count, hoặc lấy dữ liệu entity.

Tránh khai báo tùy tiện **Optional<T>**, **Page<T>**, **Stream<T>** hay một DTO tùy ý cho derived delete mà chưa xác minh API hỗ trợ kết quả đó. Return type không phải cách tự do yêu cầu framework làm mọi thao tác dữ liệu; nó phải thuộc tập kiểu được repository query infrastructure chấp nhận.

## 8. So sánh với các phương thức CRUD kế thừa

MongoRepository kế thừa những thao tác xóa thông dụng, chẳng hạn:

~~~java
repository.deleteById(id);

repository.delete(ticket);

repository.deleteAllById(ids);

repository.deleteAll();
~~~

Các thao tác này không được suy diễn từ điều kiện nghiệp vụ trong tên method như **deleteByTenantIdAndStatus**.

| Method | Đầu vào | Kết quả ở Java | Ghi chú |
| --- | --- | --- | --- |
| deleteById(ID id) | Một ID | void | Xóa theo định danh |
| delete(T entity) | Một entity | void | Có thể có semantics @Version tùy entity/store |
| deleteAllById(Iterable<ID>) | Tập ID | void | Xóa theo các ID được chỉ định |
| deleteAll() | Không có filter | void | Cực kỳ nguy hiểm trên collection production |
| deleteByTenantIdAndStatus(...) | Predicate suy diễn | long/Long | Trả số document bị xóa |
| removeByTenantIdAndCategory(...) | Predicate suy diễn | List<TicketDocument> | Trả dữ liệu entity của những record liên quan đến xóa |

**deleteById(id) không phải deleteByIdAndTenantId(id, tenantId).** Trong ứng dụng nhiều tenant, chỉ biết ObjectId không tự chứng minh caller được phép xóa document đó.

### 8.1. Khi cần ID và tenant cùng đúng

Có thể định nghĩa:

~~~java
long deleteByIdAndTenantId(
    ObjectId id,
    String tenantId
);
~~~

Khi đó, filter ràng buộc cả ID và tenant. Số lượng thường là 0 hoặc 1 nếu _id là duy nhất.

Service phải lấy tenantId từ **ngữ cảnh xác thực**; không coi một tham số tenantId do client tùy ý gửi là bằng chứng quyền truy cập.

## 9. Derived delete là truy vấn theo filter, không phải soft delete

Tên method **removeBy...** có thể gây nhầm với soft delete, nhưng không có quy tắc nào cho rằng remove nghĩa là đặt cờ **deleted=true**.

~~~java
long removeByTenantIdAndStatus(String tenantId, String status);
~~~

Phương thức trên diễn đạt **xóa document** theo filter. Nếu nghiệp vụ yêu cầu giữ document để phục hồi hoặc audit, phải triển khai soft delete riêng.

Ví dụ với MongoTemplate (giả định schema có **deleted** và **deletedAt**):

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("EXPIRED")
        .and("deleted").is(false)
);

Update update = new Update()
    .set("deleted", true)
    .currentDate("deletedAt");

var result = mongoTemplate.updateMulti(
    query,
    update,
    TicketDocument.class
);
~~~

Đây là **mẫu thiết kế soft delete**: TicketDocument ở phần đầu chưa khai báo deleted/deletedAt, nên cần mở rộng schema và chính sách truy vấn nếu áp dụng thực tế.

Khi soft delete, phải cập nhật mọi đường đọc (repository, MongoTemplate, aggregation), index và retention. Đừng chỉ đổi tên method từ deleteBy sang removeBy rồi kỳ vọng dữ liệu được giữ lại.

## 10. Cách viết filter suy diễn an toàn

### 10.1. Nên ràng buộc tenant ngay trong query

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

So với:

~~~java
// Nguy hiểm nếu dùng trong hệ thống nhiều tenant.
long deleteByStatus(String status);
~~~

Phương thức thứ hai có thể xóa tất cả ticket EXPIRED của nhiều tenant khác nhau, nếu account MongoDB có quyền và service không có lớp giới hạn khác.

**Bảo mật cần nằm trong thiết kế thao tác xóa**, không chỉ ở thao tác đọc trước khi xóa.

### 10.2. Ràng buộc trạng thái được phép xóa

Nghiệp vụ có thể chỉ cho xóa ticket EXPIRED hoặc DRAFT, không xóa OPEN:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

Service cần validate status thuộc tập được phép:

~~~java
if (!"EXPIRED".equals(status) && !"DRAFT".equals(status)) {
    throw new IllegalArgumentException(
        "This status cannot be deleted"
    );
}
~~~

Đừng cho phép client truyền **bất kỳ status** nào rồi gọi derived delete, nếu policy chỉ cho một số trạng thái.

### 10.3. Xóa theo tuổi dữ liệu

~~~java
long deleteByTenantIdAndStatusAndCreatedAtBefore(
    String tenantId,
    String status,
    Instant cutoff
);
~~~

Ví dụ:

~~~java
Instant cutoff = Instant.parse("2025-07-01T00:00:00Z");

long deleted = repository
    .deleteByTenantIdAndStatusAndCreatedAtBefore(
        tenantId,
        "EXPIRED",
        cutoff
    );
~~~

**Before** biểu diễn điều kiện thời gian nhỏ hơn cutoff. Chú ý timezone khi client nhập ngày tháng; Instant giúp xác định thời điểm theo UTC thay vì dựa vào local time không tường minh.

### 10.4. Null và dữ liệu legacy

Nếu status bị thiếu, khác null hoặc lưu sai kiểu BSON, điều kiện status = EXPIRED không khớp. Đừng nới lỏng filter xóa chỉ vì một số document legacy có schema khác.

Với migration, trước hết phải đo và phân loại dữ liệu; sau đó xây chính sách xóa riêng với điều kiện rõ ràng, có backup/audit và kiểm thử.

## 11. Index: giúp tìm đúng document cần xóa

Derived query vẫn cần MongoDB tìm những document khớp filter. Với workload:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId,
    String status
);
~~~

Một index cần đánh giá:

~~~javascript
db.support_tickets.createIndex({
  tenantId: 1,
  status: 1
});
~~~

Với xóa theo cutoff:

~~~javascript
db.support_tickets.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1
});
~~~

Index có thể giúp chọn các document cần xóa, nhưng bản thân thao tác xóa còn phải cập nhật dữ liệu và index tương ứng. **Không thể kết luận delete sẽ luôn nhanh chỉ vì có IXSCAN**.

### 11.1. Kiểm tra filter bằng find trước khi thực hiện delete

Trên database kiểm thử hoặc khi kiểm tra trước một đợt xóa có kiểm soát:

~~~javascript
db.support_tickets.find({
  tenantId: "shop-a",
  status: "EXPIRED",
  createdAt: { $lt: ISODate("2025-07-01T00:00:00Z") }
}).limit(20);
~~~

Đánh giá đường truy vấn:

~~~javascript
db.support_tickets.find({
  tenantId: "shop-a",
  status: "EXPIRED"
}).explain("executionStats");
~~~

Quan sát **winningPlan**, **totalKeysExamined**, **totalDocsExamined** và **nReturned**. Giải thích kế hoạch find là cách kiểm tra đường tìm document tương ứng, **không phản ánh toàn bộ chi phí** của delete hay việc cập nhật index.

### 11.2. Không tạo index chỉ dựa vào tên method

Một collection có thể có nhiều phương thức delete khác nhau. Mỗi index làm tăng chi phí ghi/lưu trữ, nên cần đo query thường xuyên, độ chọn lọc, kích thước collection và các đường đọc khác trước khi quyết định.

## 12. Khác biệt với MongoTemplate.remove

Trong MongoTemplate, có thể chủ động xây Query và lấy **DeleteResult**:

~~~java
import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("EXPIRED")
);

DeleteResult result =
    mongoTemplate.remove(query, TicketDocument.class);

long deletedCount = result.getDeletedCount();
~~~

**Đây là cách tương ứng về mục tiêu** với derived delete trả số lượng. MongoTemplate phù hợp khi filter được xây động, cần điều kiện phức tạp hoặc muốn kiểm soát rõ query options.

### 12.1. Tại sao derived delete gọn hơn?

~~~java
long deleted =
    repository.deleteByTenantIdAndStatus(
        tenantId,
        "EXPIRED"
    );
~~~

Repository đã biểu diễn filter trong tên method, không phải lặp lại mã Criteria ở service. Đối với các điều kiện phổ biến và ổn định, cách này dễ đọc và dễ kiểm thử.

### 12.2. Khi cần danh sách entity trước khi xóa

MongoTemplate có API dạng:

~~~java
List<TicketDocument> removed =
    mongoTemplate.findAllAndRemove(
        Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("category").is("TEST")
        ),
        TicketDocument.class
    );
~~~

Đây là lựa chọn thể hiện rõ nhu cầu **lấy dữ liệu entity và xóa**. Tuy nhiên, cần kiểm chứng chính xác tính nhất quán với concurrent writes và transaction trên phiên bản thư viện sử dụng; không mặc định findAllAndRemove là một transaction nhiều document.

### 12.3. Xóa một document và trả lại dữ liệu

Nếu điều kiện chỉ nhắm một document, MongoTemplate cũng có **findAndRemove**:

~~~java
TicketDocument removed = mongoTemplate.findAndRemove(
    Query.query(Criteria.where("_id").is(id)),
    TicketDocument.class
);
~~~

Lệnh này dành cho trường hợp **một document**. Nếu query không match, kết quả có thể là null. Không dùng findAndRemove để xóa tất cả document theo một status; mục tiêu của nó khác với derived delete nhiều bản ghi.

## 13. Delete trả List và chi phí dữ liệu lớn

Một phương thức như:

~~~java
List<TicketDocument> removeByTenantIdAndStatus(
    String tenantId,
    String status
);
~~~

có thể trả về **hàng trăm nghìn entity** khi filter rộng. Khi đó:

1. Driver phải truyền dữ liệu entity để phục vụ kết quả.
2. Spring Data phải ánh xạ BSON thành object.
3. Java giữ List lớn trong bộ nhớ.
4. Xóa vẫn cần tác động tới nhiều document và index.
5. Audit/logger có thể phát sinh thêm tải đáng kể.

Nếu chỉ cần số lượng, **trả long/Long** thường phù hợp hơn. Nếu cần lưu nội dung phục vụ tuân thủ, hãy thiết kế batch nhỏ, retention/audit và chiến lược khôi phục thay vì tải mọi document vào một List.

### 13.1. Không tự chuyển List thành count cho tiện

~~~java
// Không nên nếu mục tiêu duy nhất là đếm số xóa.
long deleted =
    repository.removeByTenantIdAndStatus(
        tenantId, "EXPIRED"
    ).size();
~~~

Đoạn trên có thể phải đọc nhiều entity chỉ để lấy một con số. Dùng phương thức **long deleteBy...** là hợp đồng thích hợp hơn.

### 13.2. Không có “delete đúng N record” chỉ nhờ List return type

Kiểu List không tự tạo giới hạn xóa. Nếu nghiệp vụ cần xóa theo từng lô 500 document, phải xây một quy trình khác: chọn một tập ID được giới hạn và có thứ tự ổn định, xóa theo ID/điều kiện an toàn, ghi checkpoint và lặp lại có kiểm soát.

Các thao tác chọn ID rồi xóa là nhiều bước; giữa chúng có thể có cập nhật đồng thời. Nếu quy trình cần tính chính xác cao, phải thiết kế điều kiện ghi/transaction hoặc mô hình trạng thái phù hợp.

## 14. Atomicity: một document khác nhiều document

MongoDB bảo đảm **một thao tác ghi trên một document có tính nguyên tử**, nhưng xóa nhiều document bằng một derived delete **không tự mang ý nghĩa “tất cả hoặc không có gì”** ở cấp nhiều document.

Ví dụ xóa 10.000 ticket hết hạn:

~~~java
long deleted =
    repository.deleteByTenantIdAndStatus(
        "shop-a", "EXPIRED"
    );
~~~

Không nên giả định:

- Toàn bộ 10.000 document được xóa như một transaction mặc định.
- Nếu lỗi giữa chừng, mọi document đã xóa được tự rollback.
- List entity được đọc trước xóa là snapshot bất biến.
- Count và nội dung trước đó luôn phản ánh cùng một thời điểm.

### 14.1. Khi cần transaction nhiều document

Spring Data MongoDB có thể tích hợp transaction khi deployment hỗ trợ và cấu hình **MongoTransactionManager**:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void purgeAndWriteAudit(String tenantId) {
    long deleted =
        ticketRepository.deleteByTenantIdAndStatus(
            tenantId, "EXPIRED"
        );

    auditService.recordPurge(tenantId, deleted);
}
~~~

Ví dụ trên chỉ minh họa **ranh giới giao dịch trong service**. Để audit và delete cùng tham gia transaction thực sự, auditService phải ghi dữ liệu theo cơ chế được MongoTransactionManager quản lý, lời gọi phải đi qua Spring transactional proxy, và MongoDB deployment phải hỗ trợ transaction. Nếu auditService gửi sự kiện HTTP hoặc message ra hệ thống ngoài, **@Transactional MongoDB không tự rollback tác dụng ở hệ thống đó**.

### 14.2. Transaction không thay thế validation

Ngay cả khi có transaction, caller vẫn phải được cấp quyền xóa, filter tenant phải chính xác và business state phải hợp lệ. Transaction có thể đảm bảo rollback nhóm ghi nhưng **không tự ngăn xóa nhầm các document thỏa filter quá rộng**.

## 15. Optimistic locking với @Version

Spring Data MongoDB hỗ trợ **@Version** cho các entity muốn phát hiện thay đổi đồng thời:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "support_tickets")
public record VersionedTicket(
    @Id ObjectId id,
    String tenantId,
    String status,
    @Version Long version
) {}
~~~

Khi xóa **một entity cụ thể có version**, các thao tác repository hỗ trợ optimistic locking có thể kiểm tra version và phát hiện stale state tùy hợp đồng/phiên bản framework.

Nhưng derived delete:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

**Không tự có expectedVersion từ một entity Java**: tham số đầu vào chỉ có tenantId và status. Đừng suy rằng @Version trên entity tự động khiến mọi derived delete theo status kiểm tra phiên bản của từng document như khi thao tác delete(entity).

### 15.1. Ràng buộc phiên bản trong filter

Nếu cần xóa một document **chỉ khi version vẫn bằng 4**, có thể dùng một query explicit:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("tenantId").is(tenantId)
        .and("version").is(4L)
);

DeleteResult result =
    mongoTemplate.remove(query, VersionedTicket.class);
~~~

Nếu deletedCount=0, có thể ID không tồn tại, tenant không khớp hoặc version đã đổi. Ứng dụng cần xác định cách báo conflict mà không làm lộ dữ liệu của tenant khác.

Đây là một **conditional delete** dựa trên filter; không cần đọc rồi xóa vô điều kiện.

## 16. Kiểm soát tenant, quyền truy cập và dữ liệu nhạy cảm

Xóa thường là thao tác khó phục hồi nên cần ràng buộc quyền chặt hơn nhiều API đọc.

### 16.1. Tenant phải đến từ context đã xác thực

Không nên viết controller nhận tenantId tùy ý từ query parameter rồi truyền thẳng vào:

~~~java
repository.deleteByTenantIdAndStatus(
    requestTenantId,
    "EXPIRED"
);
~~~

Ngay cả khi filter có tenantId, caller có thể cố truyền ID của tenant khác. Service phải đối chiếu tenant từ principal/session/token đã xác thực hoặc policy authorization được áp dụng.

### 16.2. Dữ liệu trả về từ List có thể nhạy cảm

Nếu TicketDocument chứa tên khách hàng, số điện thoại hoặc mô tả sự cố, **List<TicketDocument>** từ derived delete có thể khiến nhiều dữ liệu nội bộ đi vào log, response hoặc message.

Không trả thẳng entity đã xóa ra public API trừ khi có yêu cầu rõ và phân quyền phù hợp. Nên chuyển thành một DTO chỉ gồm **ID, status và các trường được phép công bố**, hoặc chỉ trả deletedCount.

### 16.3. Audit khác với log

In thông tin xóa ra log không bảo đảm audit có tính toàn vẹn hay độ bền. Nếu phải lưu dấu vết pháp lý, cần thiết kế audit document/event có quyền ghi, retention, chống chỉnh sửa và quy tắc transaction/outbox phù hợp.

## 17. Xóa nhiều: tránh lỗi filter quá rộng

Một phương thức:

~~~java
long deleteByStatus(String status);
~~~

có thể cực kỳ nguy hiểm nếu thiếu tenantId. Một controller có bug truyền status rỗng, null hoặc một giá trị khác mong đợi có thể khiến filter suy diễn khác với dự đoán.

### 17.1. Phòng vệ trước khi xóa

~~~java
public long deleteExpiredTickets(
        String tenantId,
        Instant cutoff
) {
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException(
            "Tenant is required"
        );
    }
    if (cutoff == null) {
        throw new IllegalArgumentException(
            "Cutoff is required"
        );
    }

    return repository
        .deleteByTenantIdAndStatusAndCreatedAtBefore(
            tenantId,
            "EXPIRED",
            cutoff
        );
}
~~~

Việc validate ở Java là lớp bảo vệ, nhưng phải đi kèm ràng buộc quyền. **Không xem validate input là thay thế authorization**.

### 17.2. Quy trình dry-run

Trước một đợt purge lớn, có thể chạy một truy vấn đọc với **cùng filter** để xem một vài ID mẫu và số lượng dự kiến. Tuy nhiên, kết quả dry-run chỉ là ảnh chụp ở thời điểm đọc; giữa dry-run và delete, dữ liệu có thể thay đổi.

Nếu cần bảo đảm “chỉ xóa đúng các ID đã duyệt”, hãy thiết kế thao tác theo **danh sách ID đã duyệt**, kèm điều kiện tenant/version và cơ chế xử lý ghi đồng thời. Không chỉ count trước rồi gọi deleteByStatus không giới hạn.

## 18. Retry và idempotency của delete

Về trạng thái cuối, xóa theo một filter cố định thường có tính chất:

~~~text
Lần 1: xóa 5 document -> deletedCount = 5
Lần 2: không còn document tương ứng -> deletedCount = 0
~~~

Nhưng **không thể kết luận mọi retry derived delete đều không có tác dụng phụ**:

- Một document mới có thể được tạo giữa hai lần gọi và cũng khớp filter.
- Các sự kiện audit, thông báo hoặc callback có thể bị tạo lặp.
- Caller có thể đã mất kết nối sau khi server thực hiện xóa nhưng trước khi nhận kết quả.
- Phép xóa trả List có thể cần bước đọc trước và quan sát dữ liệu khác giữa các lần.

### 18.1. Không lặp vô hạn khi timeout

Nếu xóa số lượng lớn bị timeout, không nên retry liên tục với filter rộng mà không đối soát. Hãy giới hạn retry, quan sát lỗi, kiểm tra dữ liệu còn lại và dùng checkpoint hoặc ID ổn định nếu quy trình cần kết quả có thể truy vết.

### 18.2. Tạo operation key cho quy trình purge quan trọng

Một đợt xóa lớn có thể được nhận diện bằng:

- **jobId**: định danh lệnh purge.
- **tenantId** và filter được duyệt.
- **cutoff** không đổi qua các lần chạy.
- **processed IDs/chunks** hoặc checkpoint.
- **deletedCount confirmed** và phần kết quả chưa rõ.

Đây là kiến trúc vận hành riêng, không có sẵn chỉ bằng việc khai báo một phương thức deleteBy....

## 19. Reactive derived delete và kiểu trả về

Trong ứng dụng reactive, repository kế thừa **ReactiveMongoRepository**:

~~~java
package com.example.support;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveTicketRepository
        extends ReactiveMongoRepository<TicketDocument, ObjectId> {

    Mono<Long> deleteByTenantIdAndStatus(
        String tenantId,
        String status
    );

    Flux<TicketDocument> removeByTenantIdAndCategory(
        String tenantId,
        String category
    );

    Mono<Long> deleteByTenantIdAndStatusAndCreatedAtBefore(
        String tenantId,
        String status,
        Instant cutoff
    );
}
~~~

Về ý định:

- **Mono<Long>** phát số document bị xóa.
- **Flux<TicketDocument>** phát các entity liên quan đến thao tác xóa, có thể phải đọc dữ liệu để cung cấp nội dung.

**Không gọi block() để lấy count trong WebFlux.** Hãy trả Mono hoặc compose bằng map/flatMap.

### 19.1. Subscription thực thi công việc

~~~java
Mono<Long> deletion =
    reactiveRepository.deleteByTenantIdAndStatus(
        tenantId, "EXPIRED"
    );
~~~

Chỉ tạo một Mono không bảo đảm MongoDB đã chạy lệnh. Khi WebFlux hoặc một subscriber đăng ký, pipeline mới thực thi.

### 19.2. Tránh subscribe nhiều lần

~~~java
// Không nên: tự subscribe rồi trả Mono để WebFlux subscribe lần nữa.
deletion.subscribe();
return deletion;
~~~

Hai subscription có thể thực hiện hai đợt xóa khác nhau. Lần thứ hai có thể thấy thêm dữ liệu mới khớp filter; count vì thế không nhất thiết giống lần đầu. Với API xóa quan trọng, cần thiết kế idempotency/operation key nếu request được retry hoặc publisher có nguy cơ subscribe lại.

### 19.3. Xóa trả Flux không phải stream an toàn cho mọi quy mô

Đừng cho rằng việc dùng Flux thay List tự động biến xóa 1 triệu entity thành quy trình ít tài nguyên và có audit chính xác. Tùy triển khai, delete trả entity có thể phải tìm dữ liệu rồi thực hiện xóa; cancellation, backpressure và concurrent writes cần được kiểm chứng. Với purge lớn, nên dùng quy trình theo lô có checkpoint và giới hạn.

## 20. Khi nào chọn MongoTemplate thay derived method?

Derived delete rất hợp với filter ngắn, ổn định:

~~~java
long deleteByTenantIdAndStatus(String tenantId, String status);
~~~

MongoTemplate thường dễ mở rộng hơn khi có:

- Nhiều filter tùy chọn theo request, nhưng đều phải đảm bảo phân quyền.
- Điều kiện logic phức tạp ($or, $elemMatch, khoảng ngày nhiều nhánh).
- Yêu cầu điều kiện ID + version + business status thay đổi theo workflow.
- Xóa theo danh sách ID giới hạn và có checkpoint.
- Cần chủ động đọc **DeleteResult**, thiết lập query options hoặc thao tác findAndRemove.

Ví dụ filter có tenant, status và cutoff:

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("EXPIRED")
        .and("createdAt").lt(cutoff)
);

DeleteResult result =
    mongoTemplate.remove(query, TicketDocument.class);
~~~

Nếu có hơn một repository method khác nhau chỉ để xử lý các tổ hợp filter tùy ý, việc tạo một custom repository fragment dùng MongoTemplate có thể rõ ràng hơn.

### 20.1. Khi nên dùng TTL index?

Nếu một collection chứa document chỉ cần tự động hết hạn theo một timestamp và **không đòi quy trình audit/xóa tức thời chính xác**, MongoDB TTL index có thể phù hợp hơn việc chạy derived delete theo lịch.

TTL deletion **không diễn ra đúng tức thời tại timestamp** và cần cấu hình theo kiểu BSON Date/cách lưu field; cũng không tự hiểu quyền tenant hoặc trạng thái nghiệp vụ phức tạp. Đừng thay một quy trình xóa cần kiểm toán bằng TTL chỉ vì muốn giảm số lệnh delete.

## 21. Kiểm thử tích hợp phương thức trả số lượng

Unit test mock repository chỉ xác minh service gọi method đúng; nó **không chứng minh** Spring Data phân tích tên method hoặc MongoDB thực hiện xóa đúng filter. Cần kiểm thử tích hợp trên MongoDB test instance riêng (ví dụ Testcontainers).

Ví dụ JUnit 5:

~~~java
package com.example.support;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class TicketDerivedDeleteTest {

    @Autowired TicketRepository repository;
    @Autowired MongoTemplate template;

    private TicketDocument ticket(
            String tenant,
            String status,
            String category,
            String subject) {
        return new TicketDocument(
            new ObjectId(),
            tenant,
            status,
            category,
            subject,
            Instant.parse("2025-06-01T09:00:00Z")
        );
    }

    @Test
    void returnsDeletedCountWithoutTouchingOtherTenant() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "OTHER-" + UUID.randomUUID();

        TicketDocument a = repository.insert(
            ticket(tenant, "EXPIRED", "RETURN", "A")
        );
        TicketDocument b = repository.insert(
            ticket(tenant, "EXPIRED", "DELIVERY", "B")
        );
        TicketDocument keep = repository.insert(
            ticket(tenant, "OPEN", "RETURN", "C")
        );
        TicketDocument other = repository.insert(
            ticket(otherTenant, "EXPIRED", "RETURN", "D")
        );

        try {
            long deleted =
                repository.deleteByTenantIdAndStatus(
                    tenant, "EXPIRED"
                );

            assertThat(deleted).isEqualTo(2L);
            assertThat(repository.existsById(a.id())).isFalse();
            assertThat(repository.existsById(b.id())).isFalse();
            assertThat(repository.existsById(keep.id())).isTrue();
            assertThat(repository.existsById(other.id())).isTrue();

            assertThat(repository.deleteByTenantIdAndStatus(
                tenant, "EXPIRED"
            )).isZero();
        } finally {
            template.remove(
                Query.query(Criteria.where("tenantId").is(tenant)),
                TicketDocument.class
            );
            template.remove(
                Query.query(Criteria.where("_id").is(other.id())),
                TicketDocument.class
            );
        }
    }
}
~~~

Test trên tạo ba ticket cho một tenant thử nghiệm và một ticket của tenant khác. Nó xác nhận:

1. **deletedCount=2** đúng với hai ticket EXPIRED.
2. Ticket OPEN của cùng tenant được giữ lại.
3. Ticket EXPIRED của tenant khác được giữ lại.
4. Gọi xóa lần nữa cho cùng filter và không thêm dữ liệu mới trả về **0**.

Fixture được tạo trong database test và dọn sau khi chạy; không dùng thử những lệnh xóa như vậy trên production.

### 21.1. Không phụ thuộc thứ tự document

Khi kiểm thử derived query trả List, nên so sánh ID theo kiểu **containsExactlyInAnyOrder** hoặc dùng Set, thay vì dựa vào thứ tự tự nhiên của MongoDB. Nếu API yêu cầu thứ tự của dữ liệu trả về, phải thiết kế và kiểm chứng thứ tự đó riêng.

## 22. Kiểm thử phương thức trả danh sách entity

Trong cùng lớp test ở phần trước, thêm method:

~~~java
@Test
void returnsEntitiesSelectedForDeletion() {
    String tenant = "TEST-" + UUID.randomUUID();

    TicketDocument first = repository.insert(
        ticket(tenant, "OPEN", "DEMO", "First")
    );
    TicketDocument second = repository.insert(
        ticket(tenant, "CLOSED", "DEMO", "Second")
    );
    TicketDocument keep = repository.insert(
        ticket(tenant, "OPEN", "OTHER", "Keep")
    );

    try {
        java.util.List<TicketDocument> deleted =
            repository.removeByTenantIdAndCategory(
                tenant, "DEMO"
            );

        assertThat(deleted)
            .extracting(TicketDocument::id)
            .containsExactlyInAnyOrder(
                first.id(),
                second.id()
            );

        assertThat(repository.existsById(first.id())).isFalse();
        assertThat(repository.existsById(second.id())).isFalse();
        assertThat(repository.existsById(keep.id())).isTrue();
    } finally {
        template.remove(
            Query.query(Criteria.where("tenantId").is(tenant)),
            TicketDocument.class
        );
    }
}
~~~

Test dùng **List<TicketDocument>** để xác minh nội dung entity được trả về, đồng thời xác nhận hai document đã bị xóa còn ticket OTHER được giữ lại.

Không nên chỉ assert **deleted.size() == 2** mà không kiểm tra ID: nếu method xóa sai hai document, test đếm vẫn có thể vượt qua.

### 22.1. Ma trận kiểm thử cần bổ sung

| Trường hợp | Kỳ vọng |
| --- | --- |
| Filter khớp 0 document | long = 0; List rỗng |
| Filter khớp một document | long = 1; List chứa entity phù hợp |
| Filter khớp nhiều document | Count chính xác; List có đúng các ID |
| Hai tenant có cùng status | Chỉ tenant được phép bị tác động |
| createdAt đúng bằng cutoff | Before không xóa mốc bằng cutoff |
| Thiếu status hoặc schema legacy | Không tự nới lỏng filter |
| Ticket đổi status trước khi xóa | Chỉ xóa nếu filter còn khớp lúc thực hiện |
| Entity có @Version | Phân biệt delete(entity) và derived delete |
| Không có index phù hợp | Đo truy vấn và latency trên fixture đủ lớn |
| Trả List nhiều entity | Xác định giới hạn/chi phí bộ nhớ |
| Xóa với soft-delete policy | Không gọi hard delete vô ý |
| Transaction/audit bắt buộc | Kiểm chứng rollback và tác động bên ngoài riêng |

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| deleteBy... trả 0 dù có dữ liệu | Filter sai tenant/status/kiểu BSON hoặc dữ liệu đổi | Đối chiếu query và document thực |
| Xóa ticket của tenant khác | Thiếu tenantId hoặc tenant không lấy từ auth | Ràng buộc tenant và authorization |
| Định trả số nhưng repository trả List rất lớn | Chọn return type không phù hợp | Dùng long/Long nếu chỉ cần count |
| List được dùng làm audit chắc chắn | Đọc entity và xóa có thể là nhiều bước | Thiết kế transaction/outbox/audit |
| Mong removeBy... là soft delete | Tiền tố remove không có nghĩa đánh dấu deleted | Dùng update để soft delete |
| Gọi deleteAll() trên production | Nhầm với deleteAllBy... có filter | Giới hạn API xóa, review code |
| save/delete entity và derived delete khác concurrency | @Version không tự áp dụng mọi query | Dùng expectedVersion/conditional delete |
| Chạy count rồi delete báo sai số xóa | Hai lần đọc/ghi khác thời điểm | Dùng deletedCount của chính delete |
| Delete hàng triệu bản ghi gây tải cao | Filter rộng, không chia batch | Lập kế hoạch purge có checkpoint |
| Reactive không thấy dữ liệu bị xóa | Publisher chưa subscribe | Trả Mono/Flux đúng pipeline |
| Reactive xóa nhiều lần | Subscribe/retry lặp | Idempotency và tránh subscribe thủ công |
| Xóa rất chậm dù có index | Nhiều document cần xóa hoặc index maintenance | Đo find explain và ghi metrics |
| Method derived delete không khởi tạo | Tên property Java sai hoặc return type không hỗ trợ | Kiểm tra parser, entity và kiểu trả |
| API trả entity đã xóa chứa dữ liệu nhạy cảm | Trả trực tiếp List<Entity> ra response/log | Chọn DTO phù hợp và phân quyền |

### 23.1. Quy trình chẩn đoán

1. Xác nhận repository thực sự làm việc với collection dự kiến.
2. Đọc tên method: **delete/remove**, các property sau **By**, các toán tử **And/Before/In**.
3. Kiểm tra tên property Java và mapping **@Field/@Id** sang BSON.
4. Đối chiếu tenant/status/cutoff với document và quyền truy cập.
5. Xác nhận kiểu trả: **long/Long** hay **List<Entity>**.
6. Phân biệt deletedCount=0 với exception do database/driver.
7. Nếu có List, xác nhận không lạm dụng bộ nhớ và không coi List là snapshot giao dịch.
8. Nếu có timeout/concurrent writes, kiểm tra retry, version và audit.
9. Với truy vấn chậm, xem index/find explain và metrics delete thực tế.
10. Tái hiện bằng kiểm thử tích hợp với fixture riêng để tránh xóa dữ liệu production.

## 24. Bài tập thực hành

### Bài tập 1: chọn kiểu trả về

Service cần xóa ticket EXPIRED của shop-a và chỉ trả số lượng đã xóa. Nên dùng kiểu nào?

**Đáp án:** **long** hoặc **Long**, ví dụ:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

Không cần List<TicketDocument> nếu không có yêu cầu dữ liệu entity.

### Bài tập 2: trả dữ liệu để ghi nhận

Nghiệp vụ cần biết ID và subject của những ticket DEMO được chọn để xóa. Chọn method nào?

**Gợi ý đáp án:**

~~~java
List<TicketDocument> removeByTenantIdAndCategory(
    String tenantId, String category
);
~~~

Chỉ lấy những field cần thiết để ghi nhận, chú ý dữ liệu nhạy cảm và khả năng dữ liệu thay đổi đồng thời. Nếu audit có yêu cầu chính xác mạnh, phải thiết kế transaction/outbox phù hợp.

### Bài tập 3: hiểu tên removeBy

Một developer nói “removeByStatus sẽ soft-delete”. Điều này đúng không?

**Đáp án:** Không. Derived remove/delete mặc định hướng đến xóa document. Soft delete cần dùng update thay đổi cờ trạng thái và sửa chính sách đọc.

### Bài tập 4: bảo vệ tenant

Trong hệ thống nhiều tenant, method:

~~~java
long deleteByStatus(String status);
~~~

có thể gây vấn đề gì?

**Đáp án:** Có thể xóa document cùng status của nhiều tenant. Cần đưa tenantId vào filter, xác thực quyền và không tin tenantId tùy ý từ client.

### Bài tập 5: zero delete

Một method deleteByTenantIdAndStatus trả 0. Có phải MongoDB thất bại không?

**Đáp án:** Không nhất thiết. Có thể không có document nào khớp. Tầng nghiệp vụ quyết định xem 0 là kết quả hợp lệ hay tình huống cần thông báo.

### Bài tập 6: xóa trước cutoff

Viết method xóa các ticket EXPIRED của tenant tạo **trước** một Instant cutoff.

~~~java
long deleteByTenantIdAndStatusAndCreatedAtBefore(
    String tenantId,
    String status,
    Instant cutoff
);
~~~

Điều kiện **Before** là nhỏ hơn cutoff; document có createdAt đúng bằng cutoff không khớp.

### Bài tập 7: List lớn

Một job cần xóa 500.000 document nhưng chỉ báo cáo số lượng. Vì sao dùng List<TicketDocument> có thể tốn kém?

**Đáp án:** Có thể cần đọc/ánh xạ rất nhiều entity và giữ chúng trong List, gây tốn RAM/mạng và tăng rủi ro timeout. Dùng kết quả đếm và thiết kế purge theo lô nếu cần kiểm soát tải.

### Bài tập 8: count rồi delete

Một service count được 12 ticket trước khi xóa, nhưng delete thực tế xóa 10. Service nên trả số nào nếu mục tiêu là số đã xóa?

**Đáp án:** Trả **10** từ kết quả delete; count trước là một quan sát ở thời điểm khác.

### Bài tập 9: optimistic locking

Entity có @Version. Derived method chỉ nhận tenantId và status có chắc kiểm tra version mỗi document như delete(entity) không?

**Đáp án:** Không được giả định như vậy. Nếu cần expectedVersion, phải ràng buộc version trong filter hoặc dùng API xóa theo entity/version có hợp đồng phù hợp.

### Bài tập 10: reactive

Phương thức xóa theo tenant/status trong ReactiveMongoRepository cần trả số lượng. Kiểu trả là gì?

**Đáp án:** **Mono<Long>**. Nếu cần dữ liệu entity trước khi xóa, có thể sử dụng return type reactive dạng **Flux<TicketDocument>** theo API được hỗ trợ.

### Bài tập 11: transaction và audit

Xóa ticket trong MongoDB rồi ghi một HTTP audit event. Chỉ đặt @Transactional trên method có bảo đảm cả hai thao tác cùng rollback không?

**Đáp án:** Không. MongoDB transaction không tự bao trùm một request HTTP tới dịch vụ khác. Cần thiết kế outbox/giao thức phối hợp và xác minh ranh giới transaction.

### Bài tập 12: kiểm thử chính xác

Test derived delete trả List có size=2. Vậy test đã chứng minh xóa đúng hai document chưa?

**Đáp án:** Chưa đầy đủ. Phải kiểm tra ID của hai document trong List, xác minh chúng không còn trong database, đồng thời đảm bảo các document ngoài filter được giữ nguyên.

## 25. Checklist cho production

Trước khi công bố một derived delete method:

- **Phạm vi:** tên method có đủ tenant, status, thời gian hoặc điều kiện nghiệp vụ bắt buộc chưa?
- **Quyền:** tenantId và policy có được xác minh từ principal đã xác thực không?
- **Kiểu trả:** caller cần deletedCount hay thật sự cần nội dung entity?
- **Khối lượng:** số document có thể khớp tối đa là bao nhiêu?
- **Index:** có index phù hợp để tìm candidate documents không?
- **Concurrency:** có writer nào có thể thay đổi document giữa đọc và xóa không?
- **Version:** thao tác có cần expectedVersion hoặc transaction không?
- **Soft delete:** quy định lưu giữ/khôi phục có cho hard delete không?
- **Audit:** dữ liệu nào được ghi lại, ở đâu và với bảo đảm gì?
- **Retry:** có cơ chế tránh thao tác lặp, timeout hoặc kết quả chưa rõ không?
- **Reactive:** subscription có được quản lý nhất quán, không block/subscribe trùng không?
- **Test:** có kiểm thử cả deleted=0, đúng tenant, đúng ID và không tác động ngoài filter không?

Một phương thức **deleteBy...** có thể chỉ vài dòng, nhưng tính đúng đắn của thao tác xóa phụ thuộc toàn bộ những điều kiện này.

## 26. Tổng kết

1. **deleteBy... và removeBy...** là các tiền tố truy vấn xóa suy diễn của Spring Data MongoDB; tên method mô tả filter từ property Java.
2. **long/Long** biểu diễn **số document đã xóa**, thích hợp khi không cần tải nội dung entity.
3. **List<Entity>** trả dữ liệu entity liên quan đến xóa, có thể phát sinh bước đọc và chi phí bộ nhớ/mạng lớn hơn.
4. **Kiểu trả về không tự tạo transaction** và không bảo đảm snapshot nhất quán dưới concurrent writes.
5. **Xóa 0 document không tự động là lỗi**; cần phân biệt kết quả hợp lệ với exception.
6. **deleteById/delete(entity)** khác với derived delete theo predicate; **deleteAll()** có thể xóa toàn collection.
7. **removeBy... không có nghĩa soft delete**; soft delete cần update cờ trạng thái và chính sách truy vấn riêng.
8. **Index hỗ trợ tìm document mục tiêu**, nhưng thao tác xóa còn có chi phí ghi và bảo trì index.
9. **@Version, tenant, trạng thái và phân quyền** phải được thiết kế có chủ đích; không suy chúng được tự động áp dụng cho mọi derived delete.
10. **ReactiveMongoRepository dùng Mono<Long>/Flux<Entity>** theo mục đích trả về, và không nên block hoặc subscribe lặp.
11. **Kiểm thử MongoDB thật** cần xác minh ID đã bị xóa, ID còn lại và kết quả trả về trong từng kiểu method.
12. **Xóa khối lượng lớn cần giới hạn, checkpoint và đối soát**, không chỉ dựa vào một List trả về.

Hiểu rõ **phương thức delete suy diễn và kiểu dữ liệu trả về** giúp ứng dụng **SPRING_DATA_MONGODB** lựa chọn đường xóa có chủ đích, kiểm soát dữ liệu bị tác động, tránh đọc dữ liệu thừa và xây dựng thao tác repository có thể kiểm thử, theo dõi và vận hành an toàn.
