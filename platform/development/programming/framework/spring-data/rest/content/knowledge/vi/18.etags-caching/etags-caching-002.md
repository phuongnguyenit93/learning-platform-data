# Phân biệt annotation `@Version` của JPA và Spring Data

Trong các ứng dụng Spring, annotation `@Version` được dùng để hỗ trợ optimistic locking: phát hiện một bản ghi đã bị thay đổi sau khi client hoặc transaction đọc nó. Tuy nhiên, có hai annotation cùng tên thuộc hai hệ sinh thái khác nhau:

- `jakarta.persistence.Version` thuộc Jakarta Persistence (JPA), được persistence provider như Hibernate sử dụng.
- `org.springframework.data.annotation.Version` thuộc Spring Data Commons, được các module Spring Data như JDBC và MongoDB sử dụng theo mapping metadata của từng module.

Hai annotation cùng biểu đạt ý tưởng versioning nhưng không phải hai tên thay thế cho nhau. Chọn annotation theo persistence technology đang quản lý entity. Với repository Spring Data JPA, dùng annotation JPA; với Spring Data JDBC hoặc MongoDB, dùng annotation Spring Data tương ứng.

## 1. Optimistic locking giải quyết vấn đề gì?

Giả sử hai người dùng cùng mở một bản ghi sản phẩm khi version hiện tại là 4. Người dùng A đổi tên và lưu trước. Sau đó người dùng B gửi một thay đổi dựa trên dữ liệu cũ mà họ đã đọc.

Nếu server chỉ ghi theo ID, thao tác của B có thể ghi đè thay đổi mới của A mà không phát hiện xung đột. Đây là lost update.

Optimistic locking gắn một version với bản ghi. Khi đọc, ứng dụng nhận version hiện tại; khi ghi, persistence layer chỉ cập nhật nếu version trong database vẫn bằng version mà transaction đã đọc. Nếu một transaction khác đã cập nhật trước, điều kiện version không còn khớp và lần ghi cũ bị từ chối.

```text
Ban đầu: database version = 4

Client A đọc version 4
Client B đọc version 4

Client A cập nhật:
  UPDATE ... WHERE id = 42 AND version = 4
  Thành công; version tăng lên 5

Client B cập nhật:
  UPDATE ... WHERE id = 42 AND version = 4
  Không còn hàng nào khớp version 4
  => phát hiện optimistic locking conflict
```

Cơ chế này phù hợp khi xung đột ghi không xảy ra thường xuyên và không cần khóa database trong suốt thời gian người dùng chỉnh sửa. Nó không giữ một row lock từ lúc đọc đến lúc ghi; thay vào đó, nó phát hiện xung đột ở thời điểm ghi.

## 2. @Version của JPA: jakarta.persistence.Version

Với entity được quản lý bởi JPA, dùng annotation `jakarta.persistence.Version`. Trong các ứng dụng dùng JPA cũ trước Jakarta EE 9, package tương ứng là `javax.persistence.Version`.

Ví dụ entity JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;

    // getters and setters
}
```

JPA persistence provider quản lý thuộc tính version. Khi entity được persist hoặc cập nhật, provider sử dụng version để phát hiện xung đột và cập nhật version theo quy tắc của persistence provider.

Trong một lần update, SQL do provider tạo thường có dạng khái quát:

```sql
UPDATE product
SET name = ?, version = 5
WHERE id = 42 AND version = 4;
```

Nếu một transaction khác đã đổi version thành 5 trước đó, câu lệnh với điều kiện `version = 4` không cập nhật được hàng nào. Provider phát hiện xung đột và báo lỗi optimistic locking, thường qua `OptimisticLockException` hoặc exception được Spring dịch sang `OptimisticLockingFailureException`.

Một số điểm cần nhớ:

- Thuộc tính có `@Version` phải thuộc entity JPA được quản lý bởi persistence context.
- JPA provider chịu trách nhiệm đọc, kiểm tra và tăng version; ứng dụng không nên tự tăng hoặc gán version như một field nghiệp vụ.
- Một entity JPA có một thuộc tính version được chỉ định theo quy tắc của JPA.
- Kiểu thuộc tính version phải là kiểu được JPA hỗ trợ, chẳng hạn `int`, `Integer`, `long`, `Long` hoặc `Timestamp` theo phiên bản đặc tả đang dùng.
- Nếu cần kiểm soát chi tiết lock mode cho một truy vấn, JPA còn có `LockModeType.OPTIMISTIC` và các lock mode liên quan; chúng là cấu hình lock riêng, không thay thế thuộc tính version.

## 3. @Version của Spring Data: org.springframework.data.annotation.Version

Spring Data Commons định nghĩa annotation `org.springframework.data.annotation.Version`. Các module Spring Data có thể đọc annotation này từ mapping metadata để thực hiện optimistic locking theo cơ chế của datastore tương ứng.

Ví dụ với Spring Data JDBC:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String reference;

    @Version
    private Long version;

    // getters and setters
}
```

Ở đây entity được Spring Data JDBC mapping, không phải JPA entity. Spring Data JDBC dùng version property để kiểm tra trạng thái khi cập nhật hoặc xóa aggregate. Khi version hiện tại không khớp với version mà entity mang theo, thao tác có thể thất bại với `OptimisticLockingFailureException`.

Với Spring Data MongoDB, cùng annotation Spring Data có thể được dùng trên document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {

    @Id
    private String id;

    private String name;

    @Version
    private Long version;

    // getters and setters
}
```

Spring Data MongoDB đưa version vào điều kiện cập nhật document và tăng version khi ghi theo semantics của module. Nếu document đã được cập nhật bởi một thao tác khác, lần ghi dựa trên version cũ có thể bị từ chối.

Cùng một annotation Spring Data Commons được dùng bởi nhiều module, nhưng cách thực hiện ở JDBC, MongoDB hoặc datastore khác phụ thuộc implementation của module đó. Không suy ra rằng mọi module đều tạo SQL hoặc có cùng hành vi persistence.

## 4. So sánh hai annotation

| Tiêu chí | JPA @Version | Spring Data @Version |
|---|---|---|
| Package | `jakarta.persistence.Version`; JPA cũ dùng `javax.persistence.Version` | `org.springframework.data.annotation.Version` |
| Chủ sở hữu metadata | Jakarta Persistence | Spring Data Commons |
| Persistence technology | Entity do JPA provider quản lý | Các Spring Data mapping module hỗ trợ versioning |
| Ví dụ thường gặp | Spring Data JPA với Hibernate | Spring Data JDBC, Spring Data MongoDB |
| Cách kiểm tra version | JPA provider thực hiện trong persistence lifecycle | Module Spring Data tương ứng thực hiện theo datastore |
| Lỗi thường gặp | `OptimisticLockException`, có thể được Spring dịch | Thường là `OptimisticLockingFailureException` |
| Có thể hoán đổi trực tiếp? | Không | Không |

Tên class giống nhau không có nghĩa chúng thuộc cùng một annotation type. Java phân biệt annotation bằng package đầy đủ. Nếu import nhầm, persistence module có thể không nhận ra metadata version mà nó cần.

## 5. Chọn đúng annotation theo repository

Hãy bắt đầu từ công nghệ persistence thực sự quản lý entity:

| Loại repository | Annotation version phù hợp |
|---|---|
| `JpaRepository` với entity JPA | `jakarta.persistence.Version` (hoặc `javax.persistence.Version` với JPA cũ) |
| `CrudRepository` / `Repository` dùng Spring Data JDBC | `org.springframework.data.annotation.Version` |
| Spring Data MongoDB repository | `org.springframework.data.annotation.Version` |
| Spring Data module khác | Kiểm tra module có hỗ trợ version metadata và cách triển khai cụ thể |

Việc một interface repository kế thừa `CrudRepository` không đủ để quyết định annotation. Spring Data JPA cũng cung cấp repository abstraction dựa trên các interface Spring Data chung. Cần xem repository được cấu hình bởi module nào và entity được mapping bởi JPA, JDBC hay MongoDB.

Không gắn cả hai annotation lên cùng một thuộc tính với hy vọng tăng khả năng tương thích. Điều đó làm metadata khó hiểu và không khiến các persistence provider tự động chia sẻ cùng một cơ chế versioning.

## 6. Khi có xung đột, ứng dụng nhận được gì?

Giả sử hai request cập nhật cùng một product:

1. Cả hai cùng đọc entity với version 4.
2. Request A lưu trước; version được tăng thành 5.
3. Request B vẫn mang version 4 và cố lưu.
4. Persistence layer phát hiện version không khớp và từ chối thao tác của B.

Ở Spring Data JPA, lỗi có thể xuất phát từ `jakarta.persistence.OptimisticLockException` và được Spring chuyển đổi thành exception thuộc nhóm optimistic locking. Với Spring Data JDBC/MongoDB, module tương ứng thường báo `OptimisticLockingFailureException`.

Khi đưa qua Spring Data REST, HTTP status cụ thể phụ thuộc exception mapping và cấu hình ứng dụng. Xung đột thường được biểu diễn thành `409 Conflict`; nếu API dùng conditional request như ETag/If-Match, điều kiện không còn đúng có thể được biểu diễn bằng `412 Precondition Failed`. Client nên đọc status và response body theo API contract.

Client không nên tự động gửi lại cùng payload cũ ngay khi gặp conflict. Cách xử lý phù hợp thường là đọc representation mới nhất, cho người dùng hoặc nghiệp vụ hòa giải các thay đổi, rồi gửi một update mới dựa trên version hiện tại.

## 7. @Version không đồng nghĩa với ETag hoặc If-Match

Version property là metadata concurrency ở persistence layer. ETag và If-Match là cơ chế conditional request của HTTP. Chúng có thể được kết hợp, nhưng không tự động là một thứ.

- `@Version` giúp persistence layer phát hiện một lần ghi dựa trên version cũ.
- ETag là validator của representation do HTTP server công bố.
- `If-Match` cho phép client yêu cầu server chỉ xử lý request nếu validator vẫn khớp.
- Có version field trong entity không tự bảo đảm Spring Data REST đã phát ETag tương ứng hoặc tự kiểm tra If-Match.

Nếu API muốn dùng ETag, cần cấu hình và kiểm thử cơ chế tạo validator, so sánh điều kiện và ánh xạ lỗi ở tầng HTTP. Không nên tự coi giá trị version trong JSON là ETag hợp lệ nếu server chưa định nghĩa hợp đồng đó.

Tương tự, không nên coi version field là dữ liệu mà client có quyền tùy ý ghi. Persistence layer cần quản lý version. Nếu field được đưa vào representation để client quan sát, hãy xác định rõ cách deserialize và ngăn client ghi đè version theo cấu hình API phù hợp.

## 8. Transaction và giới hạn của optimistic locking

Optimistic locking bảo vệ những thao tác ghi mà persistence layer thực sự kiểm tra version. Nó không tự bảo vệ mọi thay đổi ngoài database.

Một số giới hạn cần lưu ý:

- Nếu ứng dụng cập nhật dữ liệu bằng native SQL hoặc bulk update bỏ qua cơ chế version của ORM, version có thể không được kiểm tra hoặc tăng như mong đợi.
- Nếu nhiều bảng hoặc aggregate có quan hệ, version của một entity không nhất thiết đại diện cho toàn bộ trạng thái nghiệp vụ liên quan.
- Nếu side effect ngoài database đã chạy trước khi transaction bị rollback vì version conflict, side effect đó có thể không tự được hoàn tác.
- Nếu client đọc một representation rất lâu trước khi ghi, xác suất conflict tăng; ứng dụng cần thông báo và hỗ trợ hòa giải.
- Optimistic locking không thay thế validation, authorization, unique constraints hoặc foreign keys.

Với tác vụ gửi message, email hoặc gọi dịch vụ thanh toán, cần xác định transaction boundary và thiết kế deduplication/outbox nếu thao tác có thể được thử lại. Version check chỉ giải quyết việc phát hiện stale write tại persistence layer.

## 9. Checklist triển khai

1. Xác định repository đang dùng Spring Data JPA, JDBC hay MongoDB.
2. Với JPA entity, import `jakarta.persistence.Version`; với Spring Data mapping module hỗ trợ versioning, import `org.springframework.data.annotation.Version`.
3. Chọn kiểu version được persistence technology hỗ trợ.
4. Để persistence provider/module quản lý việc tăng version; không dùng version như một field nghiệp vụ.
5. Kiểm thử hai transaction hoặc hai client cùng đọc một version rồi cập nhật cạnh tranh.
6. Xác nhận exception optimistic locking được xử lý đúng ở service và HTTP layer.
7. Nếu cần ETag/If-Match, cấu hình riêng conditional request và kiểm thử response.
8. Không để bulk/native update hoặc side effect ngoài database vô tình bỏ qua concurrency policy.
9. Tài liệu hóa cho client cách xử lý conflict: đọc lại, hòa giải và gửi thay đổi mới.

`jakarta.persistence.Version` và `org.springframework.data.annotation.Version` cùng hỗ trợ ý tưởng optimistic locking nhưng thuộc hai hệ metadata khác nhau. Hãy chọn annotation theo persistence module đang quản lý entity, để version được kiểm tra và cập nhật đúng nơi. Với Spring Data REST, cần kết hợp xử lý conflict ở tầng HTTP và hướng dẫn client đọc lại trạng thái mới khi một update dựa trên version cũ bị từ chối.
