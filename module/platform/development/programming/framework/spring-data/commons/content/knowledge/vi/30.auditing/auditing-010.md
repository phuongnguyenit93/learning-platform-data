# Giới hạn auditing khi bỏ qua quy trình lưu entity

## 1. Mục tiêu và phạm vi

Trong chương **Auditing** của module **Spring Data Commons**, bài này giải thích vì sao một thao tác đã cập nhật dữ liệu thành công nhưng các trường người sửa và thời gian sửa vẫn có thể giữ nguyên.

Sau bài học, bạn cần làm được các việc sau:

- Phân biệt metadata auditing với cơ chế thực sự điền metadata.
- Nhận diện những đường ghi không đi qua lifecycle của entity.
- Quyết định giữa lưu entity và cập nhật trực tiếp kèm metadata tường minh.
- Đánh giá riêng hành vi của JPA, JDBC, R2DBC và MongoDB.
- Kiểm chứng dữ liệu đã lưu, thay vì chỉ quan sát object hoặc số bản ghi bị ảnh hưởng.

Tình huống xuyên suốt là đóng một phiếu xử lý. Hệ thống lưu trạng thái, người tạo, thời điểm tạo, người sửa gần nhất và thời điểm sửa gần nhất. Khi tối ưu thao tác đóng phiếu thành một câu update trực tiếp, lập trình viên cần giữ nguyên hợp đồng metadata đã công bố.

## 2. Metadata không tự theo dõi mọi thay đổi trong database

Spring Data Commons cung cấp các abstraction dùng chung:

| Thành phần | Vai trò |
| --- | --- |
| `@CreatedBy`, `@CreatedDate` | Mô tả metadata tạo mới |
| `@LastModifiedBy`, `@LastModifiedDate` | Mô tả metadata sửa gần nhất |
| `AuditorAware<T>` | Cung cấp danh tính cho auditing đồng bộ |
| `ReactiveAuditorAware<T>` | Cung cấp danh tính cho auditing reactive |
| `DateTimeProvider` | Cung cấp thời gian cho hạ tầng auditing |

Các thành phần này cần được kết nối với hạ tầng auditing của store. Chỉ thêm annotation vào class chưa đủ. Xem [Spring Data Commons: Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

Có thể hình dung một đường ghi có auditing như sau:

~~~text
Thao tác thay đổi entity
    -> lifecycle/callback mà store hỗ trợ
    -> điền metadata audit trên entity
    -> ghi trạng thái entity
    -> hoàn tất thao tác hoặc transaction
~~~

Một đường ghi khác có thể là:

~~~text
Câu lệnh update + tham số
    -> database cập nhật trực tiếp
    -> không có bước điền metadata trên từng entity
~~~

Ở đường thứ hai, database chỉ biết những giá trị được lệnh ghi cung cấp, cộng với các cơ chế riêng của database nếu có. Nó không đọc annotation Java để tìm người dùng hiện tại.

**Nguyên tắc áp dụng:** xác định đường thực thi của thao tác ghi trước khi kết luận annotation auditing có hiệu lực.

## 3. Phân loại đường ghi trước khi chọn giải pháp

| Đường ghi | Điều cần xác minh |
| --- | --- |
| Lưu entity qua repository của store | Auditing đã bật, mapping hợp lệ và đường lưu có tích hợp auditing |
| Entity JPA đang managed thay đổi trong transaction | Listener auditing được cấu hình; provider thực hiện lifecycle cập nhật khi flush |
| JPQL bulk update hoặc native SQL update | Lệnh có chủ động ghi metadata không; trạng thái entity đang giữ có còn đúng không |
| Modifying query trong Spring Data JDBC | Các cột audit cần có trong câu SQL nếu muốn thay đổi chúng |
| SQL trực tiếp qua `JdbcTemplate` hoặc `DatabaseClient` | Thành phần nào chịu trách nhiệm gán actor, thời gian và xử lý cạnh tranh |
| Update theo điều kiện trong MongoDB | Không suy ra auditing của đường save từ việc API vẫn thuộc Spring Data |
| Script, migration, ứng dụng khác ghi cùng database | Hợp đồng metadata có được triển khai tại đường ghi đó không |

Bảng này dùng để phân tích, không thay thế hợp đồng API của từng store và phiên bản đang sử dụng.

Tên method cũng chưa đủ để kết luận. Một custom repository fragment có thể tự tải entity rồi lưu, hoặc chỉ chạy SQL. Cùng nằm trong repository không có nghĩa cùng đi qua một chuỗi callback.

Tương tự, `saveAll` nhận nhiều entity và một bulk update theo điều kiện là hai hình thức khác nhau. Số lượng phần tử lớn không tự quyết định auditing có chạy; cần xem cơ chế thực thi.

## 4. Ví dụ JPA: thay đổi entity và update trực tiếp

### 4.1. Mô hình minh họa

Các ví dụ JPA dưới đây giả định ứng dụng đã cấu hình datasource, repository và auditing đúng cách, bao gồm `@EnableJpaAuditing`, nguồn auditor kiểu `String` và listener tương ứng. Xem [Spring Data JPA: Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html).

Entity dùng Jakarta Persistence; đây là mô hình riêng của JPA:

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@Table(name = "ticket")
@EntityListeners(AuditingEntityListener.class)
public class Ticket {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @Version
    private long version;

    @CreatedBy
    @Column(name = "created_by", updatable = false)
    private String createdBy;

    @CreatedDate
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @LastModifiedBy
    @Column(name = "modified_by")
    private String modifiedBy;

    @LastModifiedDate
    @Column(name = "modified_at")
    private Instant modifiedAt;

    protected Ticket() {
    }

    public Ticket(String status) {
        this.status = status;
    }

    public void close() {
        this.status = "CLOSED";
    }
}
~~~

`updatable = false` kiểm soát mapping update của JPA cho cột tương ứng. Nó không ngăn một script SQL có quyền ghi sửa cột đó. Nếu cần ràng buộc ở database, phải thiết kế thêm tại database.

### 4.2. Đường thay đổi entity

Trong service đã inject `TicketRepository repository`:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void closeThroughEntity(Long id) {
    Ticket ticket = repository.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException("Ticket not found"));

    ticket.close();
}
~~~

Nếu entity đang managed trong transaction JPA này, thay đổi có thể được đồng bộ nhờ dirty checking. Không bắt buộc phải có một lời gọi `save` mới tạo được cập nhật JPA.

Với một thay đổi cần ghi, auditing đã cấu hình tham gia thông qua lifecycle của JPA. Điều cần kiểm tra là lifecycle có được thực hiện hay không, thay vì chỉ tìm từ khóa `save` trong service.

Không coi một lần gọi service không làm đổi trạng thái là bằng chứng chắc chắn sẽ có SQL update hoặc một mốc audit mới. Chính sách “ghi nhận mọi lần yêu cầu đóng phiếu” là yêu cầu khác với “ghi người sửa trạng thái gần nhất”.

### 4.3. Đường update trực tiếp

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TicketRepository
        extends JpaRepository<Ticket, Long> {

    @Modifying
    @Query("""
        update Ticket t
           set t.status = :status
         where t.id = :id
        """)
    int changeStatusDirect(
            @Param("id") Long id,
            @Param("status") String status);
}
~~~

Method này phải được gọi trong transaction ghi phù hợp. Nó gửi JPQL update trực tiếp, không tải từng phiếu rồi gọi `close()`.

Giả sử dữ liệu trước thao tác:

| Thuộc tính | Giá trị |
| --- | --- |
| `status` | `OPEN` |
| `modifiedBy` | `user-a` |
| `modifiedAt` | `t0` |

Người `user-b` gọi `changeStatusDirect(id, "CLOSED")`. Nếu không có cơ chế database bổ sung, câu query chỉ yêu cầu đổi `status`. Không có cơ sở để kỳ vọng hai cột audit tự chuyển thành `user-b` và `t1`.

Giá trị trả về `1` chỉ cho biết query ảnh hưởng một bản ghi. Nó không chứng minh metadata audit đã được cập nhật đúng.

## 5. Khi chọn update trực tiếp, ghi rõ hợp đồng metadata

Có thể giữ cách cập nhật trực tiếp nếu chủ động đưa các trường cần thay đổi vào query.

Thêm method sau vào repository JPA ở trên:

~~~java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true)
@Query("""
    update Ticket t
       set t.status = :status,
           t.modifiedBy = :actorId,
           t.modifiedAt = :modifiedAt,
           t.version = t.version + 1
     where t.id = :id
       and t.version = :expectedVersion
    """)
int changeStatusWithAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("actorId") String actorId,
        @Param("modifiedAt") java.time.Instant modifiedAt,
        @Param("expectedVersion") long expectedVersion);
~~~

Trong một service đã inject repository, `java.time.Clock clock` và thành phần `currentActor` của ứng dụng:

~~~java
@Transactional
public void closeDirect(
        Long id,
        long expectedVersion) {

    String actorId = currentActor.requireActorId();
    java.time.Instant modifiedAt = clock.instant();

    int changed = repository.changeStatusWithAudit(
            id,
            "CLOSED",
            actorId,
            modifiedAt,
            expectedVersion);

    if (changed != 1) {
        throw new org.springframework.dao.OptimisticLockingFailureException(
                "Ticket missing or version changed");
    }
}
~~~

`currentActor.requireActorId()` là hợp đồng minh họa: trả về định danh hợp lệ từ nguồn xác thực của ứng dụng hoặc báo lỗi. Nó không phải API sẵn có của Spring Data. `Clock` cũng cần được ứng dụng cung cấp.

Các quyết định trong ví dụ:

- Chỉ ghi người sửa và thời gian sửa; giữ nguyên metadata tạo mới.
- Đưa actor và thời gian vào cùng lệnh cập nhật trạng thái.
- Kiểm tra phiên bản mong đợi và tăng phiên bản ngay trong lệnh.
- Nếu không cập nhật được đúng một phiếu, dừng thao tác theo chính sách lỗi đã chọn.

Kết quả `0` có thể do id không tồn tại hoặc phiên bản đã khác. Ví dụ gộp hai trường hợp trong cùng một lỗi; nếu nghiệp vụ cần phân biệt, phải thiết kế quy trình kiểm tra riêng.

Đây là **ghi metadata tường minh**. Query không làm cho listener auditing bỗng được gọi. Cách này cần được duy trì khi thêm field audit hoặc thay đổi quy tắc danh tính, thời gian.

Nếu ứng dụng kết hợp auditing tự động với query trực tiếp, nên thống nhất nguồn actor và quy ước thời gian. Một bên dùng đồng hồ ứng dụng, bên khác dùng giờ database có thể tạo ra các mốc khó so sánh.

## 6. JPA còn có persistence context và phiên bản

### 6.1. Entity trong bộ nhớ có thể đã cũ

Sau bulk update, một entity đã tải trước đó có thể vẫn giữ trạng thái cũ trong persistence context. Đọc lại qua cùng context có thể khiến việc kiểm tra kết quả bị sai lệch.

`flushAutomatically` yêu cầu flush trước khi chạy modifying query; `clearAutomatically` yêu cầu clear sau đó. Clear tác động đến persistence context, không chỉ phiếu vừa cập nhật. Các object đã detach không còn được dirty checking theo dõi như trước.

Vì vậy, hai tùy chọn này cần phù hợp với ranh giới transaction. Không tiếp tục sửa một reference cũ rồi mặc định thay đổi sẽ được lưu.

Xem [Spring Data JPA: Modifying Queries](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.modifying-queries).

### 6.2. Audit và optimistic locking là hai trách nhiệm khác nhau

Có `modifiedAt` không đồng nghĩa có kiểm soát lost update. Với bulk update JPA, không dựa vào `@Version` để tự thêm điều kiện phiên bản như đường thay đổi từng entity; ví dụ trên chủ động xử lý điều kiện và tăng phiên bản.

Đặc tả cũng nêu bulk update không tự đồng bộ persistence context với kết quả. Xem [Jakarta Persistence 3.2, Bulk Update and Delete Operations](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2#bulk-update-and-delete-operations).

Xét hai request cùng đọc phiên bản `7`. Nếu cả hai cùng ghi mà không kiểm tra phiên bản, request sau có thể ghi đè request trước. Hai trường audit có thể vẫn được điền đầy đủ, nhưng tính đúng của nghiệp vụ đã mất.

Đây là lý do cần kiểm tra riêng ba kết quả: dữ liệu nghiệp vụ, metadata audit và chính sách cạnh tranh.

## 7. JDBC và R2DBC: SQL trực tiếp cần hợp đồng riêng

Spring Data JDBC nói rõ modifying query chạy trực tiếp tại database, không gọi events/callbacks; các trường auditing không tự cập nhật nếu query không ghi chúng. Xem [Spring Data JDBC: Modifying Query](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html#jdbc.query-methods.at-query.modifying).

Một SQL có chủ đích giữ hợp đồng của ví dụ đóng phiếu có thể là:

~~~sql
UPDATE ticket
   SET status = :status,
       modified_by = :actorId,
       modified_at = :modifiedAt,
       version = version + 1
 WHERE id = :id
   AND version = :expectedVersion
~~~

Đây là mẫu SQL với tham số có tên. Cần chọn API binding, kiểu thời gian và schema phù hợp với driver/database thực tế. Không nối chuỗi dữ liệu người dùng vào SQL.

Trong R2DBC, auditing có điểm tích hợp qua entity callback trước conversion. Xem [Spring Data R2DBC: EntityCallbacks](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-callbacks.html).

Khi dùng `DatabaseClient` để gửi SQL trực tiếp, không có bước chuyển entity qua callback đó. Một bean `ReactiveAuditorAware` vẫn cần thành phần gọi nó; bean không tự chặn mọi câu SQL để chèn actor.

Thiết kế reactive cần xác định thêm thời điểm lấy danh tính: dữ liệu thuộc subscriber nên được giải quyết trong đúng publisher và context của thao tác. Tránh chụp danh tính một lần khi khởi tạo một publisher dùng chung rồi tái sử dụng cho nhiều người.

Các annotation `@Query` và `@Modifying` thuộc module cụ thể. Không sao chép import JPA vào repository JDBC/R2DBC rồi coi chúng có cùng ngữ nghĩa.

## 8. MongoDB: phân biệt save document với update theo điều kiện

Spring Data MongoDB tích hợp auditing qua `AuditingEntityCallback` hoặc biến thể reactive tại bước trước conversion của entity. Xem [Spring Data MongoDB: Store specific EntityCallbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html#mongodb.entity-callbacks).

Một lệnh cập nhật bằng điều kiện và các update operator không tương đương với việc tải từng document, áp dụng auditing rồi save.

Ví dụ sau cập nhật collection `tickets` trực tiếp. Giả định tên field lưu thực tế là `status`, `modifiedBy`, `modifiedAt`; `ticketId` có kiểu BSON tương ứng với `_id` đang lưu:

~~~java
import java.util.Date;

import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
        Criteria.where("_id").is(ticketId));

Update update = new Update()
        .set("status", "CLOSED")
        .set("modifiedBy", actorId)
        .set("modifiedAt", Date.from(clock.instant()));

var result = mongoTemplate.updateFirst(
        query,
        update,
        "tickets");
~~~

Ở đây metadata xuất hiện vì mã đã thêm chúng vào `Update`. Không phải vì `updateFirst` tự đọc `@LastModifiedBy`.

Ví dụ dùng tên collection và tên field lưu trực tiếp; không giả định mapping của entity JPA ở mục trước áp dụng cho MongoDB. Nếu có `@Field` hoặc quy tắc đổi tên, phải xác định đúng tên field cho API đang dùng.

Cần kiểm tra kết quả update và chính sách khi không khớp document. Ví dụ này chưa triển khai điều kiện phiên bản; nếu cần chống ghi đè, bổ sung cơ chế phù hợp với store và API đã chọn.

Đối với upsert, còn phải phân biệt metadata chỉ ghi khi tạo và metadata ghi mỗi lần sửa. Một quy tắc `setOnInsert` cho dữ liệu tạo mới có thể hữu ích, nhưng cần thiết kế đầy đủ cả trường hợp chưa tồn tại và đã tồn tại. Không dùng cùng một phép `set` cho mọi field rồi vô tình đổi người tạo của document cũ.

## 9. Các writer ngoài ứng dụng và nguồn sự thật của metadata

Giả sử ứng dụng chính được kiểm tra auditing đầy đủ, nhưng dữ liệu còn được sửa bởi một job nhập liệu chạy SQL. Metadata vẫn thiếu nếu job đó chỉ cập nhật trạng thái.

Một hợp đồng có thể được phân công như sau:

| Writer | Trách nhiệm cần có |
| --- | --- |
| API nghiệp vụ qua entity lifecycle | Cấu hình và dùng auditing của store |
| Query cập nhật trực tiếp | Ghi metadata cùng thao tác nghiệp vụ |
| Job nền | Dùng actor hệ thống có định danh rõ và quy ước thời gian đã thống nhất |
| Script sửa dữ liệu | Ghi lý do, actor vận hành và metadata theo quy trình sửa dữ liệu |
| Hệ thống tích hợp | Thực thi cùng hợp đồng hoặc đi qua một dịch vụ ghi tập trung |

Nếu nhiều writer không cùng nằm trong ứng dụng Java, có thể cân nhắc quy tắc ở database như trigger. Khi đó cần xác định cách truyền danh tính ứng dụng và thành phần nào là nguồn sự thật cho từng field.

Tài khoản kết nối database thường đại diện cho ứng dụng hoặc pool kết nối; nó không tự đại diện cho người dùng nghiệp vụ. Việc truyền actor qua thuộc tính của session cần được thiết kế phù hợp với database và vòng đời connection.

Một default value cho cột cũng không mặc nhiên là cơ chế cập nhật mỗi lần sửa. Cần phân biệt giá trị mặc định lúc insert, biểu thức trong lệnh update và trigger.

Nếu cả ứng dụng lẫn database cùng ghi `modifiedAt`, hãy chọn một quy tắc rõ ràng. Nếu không, giá trị trên object trả về có thể khác giá trị cuối cùng sau khi database xử lý.

## 10. Transaction, xóa dữ liệu và lịch sử thay đổi

### 10.1. Metadata trên object chưa chứng minh commit

Callback có thể đã điền `modifiedAt` trong bộ nhớ trước khi lệnh ghi hoặc transaction thất bại. Vì vậy:

~~~text
Object có audit fields
    không đủ để kết luận
database đã lưu và transaction đã commit
~~~

Khi cần xác nhận thành công, kiểm tra kết quả lưu trong đúng ngữ cảnh transaction. Trong một phép kiểm tra rollback, đọc lại từ transaction khác sau khi transaction thất bại đã kết thúc.

Thời điểm auditing được lấy cũng không nên được gọi là thời điểm commit chính xác. Nó thường đại diện cho lúc hạ tầng hoặc mã ứng dụng tạo metadata cho thao tác.

### 10.2. Hard delete không để lại bản ghi chứa metadata

Nếu phiếu bị xóa vật lý, các trường `createdBy` và `modifiedBy` trên chính phiếu không còn tồn tại trong bảng hoặc collection. Chúng không tự trở thành lịch sử người đã xóa.

Nếu cần soft delete, hãy coi thao tác đặt cờ xóa là một đường ghi cần hợp đồng metadata. Nếu dùng query trực tiếp để đặt cờ, vẫn phải quyết định cách ghi người sửa và thời gian.

### 10.3. Last modified không phải toàn bộ lịch sử

Hai lần đóng/mở lại phiếu có thể liên tiếp ghi đè cùng cặp `modifiedBy` và `modifiedAt`. Không thể khôi phục các trạng thái trung gian chỉ từ cặp cuối cùng.

Nếu cần lịch sử, thiết kế nơi lưu riêng, ví dụ bảng sự kiện nghiệp vụ, giải pháp revision phù hợp hoặc cơ chế thu nhận thay đổi ở database. Hãy xác định cả cách lưu actor và dữ liệu trước/sau cần thiết.

Nếu cập nhật phiếu và ghi một dòng lịch sử trong cùng database quan hệ, có thể đặt chúng trong cùng transaction phù hợp. Nếu gửi lịch sử sang hệ thống khác, cần giải quyết thêm việc chuyển giao và retry; lời gọi mạng sau update không tự có tính nguyên tử cùng database.

## 11. Đọc lại dữ liệu để kiểm chứng từng đường ghi

Dùng một phiếu được tạo bởi `user-a` tại `t0`, sau đó sửa bởi `user-b` tại `t1`. Tạo dữ liệu riêng cho từng trường hợp để kết quả trước không che lỗi của trường hợp sau.

| Trường hợp | Kết quả cần kiểm tra |
| --- | --- |
| Thay đổi entity qua đường lifecycle đã cấu hình | Trạng thái mới và metadata sửa theo hợp đồng auditing |
| Query chỉ đổi trạng thái | Trạng thái đổi; metadata không tự đổi nếu không có cơ chế bổ sung |
| Query có metadata tường minh | Trạng thái, actor, thời gian được ghi đúng; metadata tạo giữ nguyên |
| Phiên bản mong đợi đã cũ | Không ghi đè dữ liệu mới hơn theo chính sách cạnh tranh |
| Không có actor nhưng thao tác bắt buộc có actor | Thao tác bị từ chối theo hợp đồng ứng dụng |
| Job có actor hệ thống | Dữ liệu ghi rõ định danh job, không mượn danh tính request bất kỳ |
| Transaction rollback | Dữ liệu lưu không chứa thay đổi bị rollback |
| Upsert | Phân biệt đúng metadata tạo mới và metadata sửa |

Một trình tự kiểm tra hữu ích:

1. Tạo fixture, lưu và kết thúc bước chuẩn bị.
2. Thực hiện đúng API đang muốn kiểm tra với actor/thời gian kiểm soát được.
3. Hoàn tất transaction hoặc publisher theo cơ chế của API.
4. Đọc lại qua trạng thái truy cập mới, tránh object và cache cũ.
5. So sánh các field nghiệp vụ, audit và phiên bản cần thiết.

Với JPA, có thể flush/clear hoặc dùng transaction kiểm tra riêng tùy mục tiêu. Flush chưa có nghĩa commit; đừng dùng hai khái niệm này thay nhau.

Khi so sánh thời gian, tính đến độ chính xác mà database thực sự lưu. Một `Instant` trong JVM có thể có phần lẻ chi tiết hơn cột hoặc BSON Date.

Đếm số lần gọi provider có ích để chẩn đoán, nhưng kết quả quan trọng vẫn là metadata được lưu bởi chính đường ghi đang kiểm tra.

## 12. Các cách sửa dễ gây hiểu nhầm

| Cách làm | Vấn đề |
| --- | --- |
| Thêm tiếp annotation vào cùng field | Không tạo callback cho một đường ghi đang bỏ qua entity |
| Thêm `@Transactional` rồi chờ auditing chạy | Transaction không tự biến SQL trực tiếp thành lifecycle entity |
| Gọi `saveAndFlush` cho một entity không liên quan | Không áp dụng auditing cho các hàng khác đã bị bulk update |
| Sau bulk update, save lại một object cũ để “bù audit” | Có thể ghi đè dữ liệu bằng trạng thái cũ hoặc phát sinh thêm lần ghi |
| Chỉ ghi timestamp, bỏ actor ngoài ý muốn | Hợp đồng “ai sửa” vẫn chưa được đáp ứng |
| Cho client tự gửi `modifiedBy` | Danh tính audit có thể không phản ánh người đã được hệ thống xác thực |
| Gán metadata trong DTO phản hồi | Không chứng minh dữ liệu đã lưu có metadata tương ứng |
| Gọi handler auditing trên một object tạm | Metadata chỉ được tính trên object; vẫn cần đưa giá trị vào lệnh ghi thực tế |

Cách chọn giải pháp nên bắt đầu từ yêu cầu:

- Nếu cần logic và lifecycle trên từng entity, ưu tiên đường ghi entity phù hợp với store.
- Nếu cần cập nhật trực tiếp vì quy mô hoặc tính chất của thao tác, đưa metadata và điều kiện cạnh tranh vào thiết kế của chính đường ghi đó.
- Nếu có nhiều writer độc lập, chọn cơ chế thực thi hợp đồng thống nhất ở tầng thích hợp.

Không giả định tối ưu ít câu lệnh hơn luôn giữ nguyên toàn bộ ngữ nghĩa của cách tải entity rồi lưu. Khi thay đổi đường ghi, metadata, validation, callback nghiệp vụ và kiểm soát cạnh tranh đều cần được xem xét theo yêu cầu thực tế.

## 13. Bài thực hành

Xây dựng thao tác đóng phiếu cho một store đã chọn:

1. Định nghĩa rõ người tạo, thời gian tạo, người sửa và thời gian sửa.
2. Cài đặt một đường ghi qua entity lifecycle và xác minh cấu hình auditing.
3. Tạo một đường update trực tiếp chỉ đổi trạng thái để quan sát giới hạn.
4. Sửa đường trực tiếp để ghi metadata cùng thao tác nghiệp vụ.
5. Bổ sung chính sách cạnh tranh nếu phiếu có thể được nhiều bên sửa đồng thời.
6. Đọc lại dữ liệu trong từng trường hợp, kiểm tra metadata tạo không bị thay đổi.
7. Mô tả cách một job hoặc script ngoài ứng dụng sẽ tuân thủ cùng hợp đồng.
8. Giải thích riêng cách đáp ứng yêu cầu lưu lịch sử nếu nghiệp vụ cần biết mọi lần thay đổi.

Bài thực hành đạt yêu cầu khi bạn chỉ ra được **đường ghi nào gọi auditing**, **thành phần nào cung cấp metadata cho đường bỏ qua lifecycle** và **dữ liệu nào đã được lưu để chứng minh hợp đồng đó**.
