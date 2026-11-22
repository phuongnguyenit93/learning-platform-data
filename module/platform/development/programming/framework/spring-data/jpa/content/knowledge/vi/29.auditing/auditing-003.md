# Ghi nhận người tạo và người chỉnh sửa với @CreatedBy, @LastModifiedBy và AuditorAware

Spring Data JPA Auditing giúp tự động lưu thông tin người thực hiện thao tác trên entity. Hai annotation `@CreatedBy` và `@LastModifiedBy` ghi nhận ai đã tạo và ai chỉnh sửa bản ghi gần nhất. Interface `AuditorAware<T>` cung cấp danh tính của người dùng hiện tại để Spring Data đưa vào các trường này.

Cơ chế này giúp ứng dụng có lịch sử trách nhiệm cơ bản mà không phải truyền username hoặc user ID vào mọi lệnh `save`. Phần quan trọng là cấu hình auditing, gắn listener vào entity và cung cấp một `AuditorAware` phù hợp với cách ứng dụng xác định người dùng hiện tại.

## 1. Hai trường auditor có ý nghĩa gì?

- `@CreatedBy`: đánh dấu thuộc tính lưu người tạo entity. Giá trị được thiết lập khi entity được tạo lần đầu.
- `@LastModifiedBy`: đánh dấu thuộc tính lưu người chỉnh sửa gần nhất. Giá trị được cập nhật khi entity được sửa.

Hai annotation này thuộc package `org.springframework.data.annotation`. Chúng mô tả metadata auditing cho Spring Data; bản thân annotation không tự biết người dùng đang đăng nhập là ai.

Ví dụ, một bản ghi bài viết có thể lưu:

| Thời điểm | createdBy | lastModifiedBy |
|---|---|---|
| Lần đầu lưu bởi alice | alice | alice |
| Sau đó bob chỉnh sửa | alice | bob |
| Sau đó alice chỉnh sửa lại | alice | alice |

Theo cấu hình mặc định `modifyOnCreate = true` của `@EnableJpaAuditing`, trường `@LastModifiedBy` cũng được gán khi tạo mới. Nếu đặt `modifyOnCreate = false`, auditing không thiết lập metadata sửa đổi trong lần tạo đầu tiên.

Auditor là danh tính thực hiện thao tác, không nhất thiết là người sở hữu bản ghi. Ví dụ, một nhân viên hỗ trợ có thể sửa bản ghi do khách hàng tạo; khi đó `createdBy` vẫn là khách hàng còn `lastModifiedBy` là nhân viên hỗ trợ.

## 2. Khai báo các trường auditing trên entity

Có thể đặt các trường dùng chung trong một lớp cha được đánh dấu `@MappedSuperclass`. Các entity kế thừa lớp này sẽ dùng chung mapping và listener.

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedBy
    @Column(name = "created_by", updatable = false)
    private String createdBy;

    @LastModifiedBy
    @Column(name = "last_modified_by")
    private String lastModifiedBy;

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

Các điểm cần hiểu:

- `@MappedSuperclass` cho phép entity con kế thừa các thuộc tính persistent từ lớp cha. Lớp cha không được ánh xạ thành một bảng riêng chỉ vì annotation này.
- `@EntityListeners(AuditingEntityListener.class)` đăng ký listener nhận các sự kiện vòng đời JPA và gọi Spring Data Auditing.
- `updatable = false` trên `createdBy` ngăn cột người tạo bị đưa vào câu lệnh SQL UPDATE thông thường. Giá trị vẫn được ghi khi INSERT.
- `lastModifiedBy` có thể thay đổi trong các lần cập nhật tiếp theo.

Một entity cụ thể có thể kế thừa lớp auditing:

```java
package com.example.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Article extends AuditedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Article() {
    }

    public Article(String title) {
        this.title = title;
    }

    public void rename(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Nếu không dùng lớp cha chung, có thể đặt `@EntityListeners(AuditingEntityListener.class)`, `@CreatedBy` và `@LastModifiedBy` trực tiếp trên từng entity. Cách dùng lớp cha giúp tránh lặp lại mapping ở nhiều entity.

## 3. Bật JPA Auditing

Spring Data cần được bật auditing trong cấu hình ứng dụng. Ví dụ dưới đây đặt tên bean cung cấp auditor là `auditorAware`:

```java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {
}
```

`@EnableJpaAuditing` đăng ký hạ tầng auditing của Spring Data JPA. Thuộc tính `auditorAwareRef` trỏ tới bean thực hiện `AuditorAware`. Tên này phải khớp với tên bean trong cấu hình. Nếu ứng dụng chỉ có một bean `AuditorAware`, có thể dùng cấu hình mặc định mà không chỉ định tham chiếu; khai báo tường minh giúp dễ đọc khi dự án có nhiều cấu hình.

Chỉ bật `@EnableJpaAuditing` là chưa đủ nếu entity chưa đăng ký `AuditingEntityListener`. Ngược lại, listener cũng cần auditing infrastructure được kích hoạt và có thể lấy được auditor hiện tại.

## 4. AuditorAware lấy người dùng hiện tại như thế nào?

`AuditorAware<T>` là interface Spring Data dùng để lấy danh tính hiện tại. Kiểu `T` phải tương thích với kiểu thuộc tính được đánh dấu `@CreatedBy` và `@LastModifiedBy`.

Nếu ứng dụng dùng Spring Security và lưu username dạng `String`, có thể triển khai như sau:

```java
package com.example.config;

import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    public AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }
}
```

Phương thức `getCurrentAuditor()` trả về `Optional<String>`:

1. Đọc `Authentication` từ `SecurityContextHolder`.
2. Kiểm tra context có authentication hay không.
3. Bỏ qua trường hợp chưa xác thực hoặc anonymous.
4. Trả về tên principal bằng `authentication.getName()` khi đã xác thực.

Ví dụ dùng `String` vì `createdBy` và `lastModifiedBy` trong lớp `AuditedEntity` cũng là `String`. Nếu muốn lưu ID người dùng, hãy dùng một kiểu nhất quán, chẳng hạn `AuditorAware<Long>` cùng các trường `Long`, và lấy ID từ principal tùy chỉnh của ứng dụng.

Nếu không sử dụng Spring Security, có thể triển khai `AuditorAware` dựa trên cơ chế xác định người thực hiện của hệ thống. Với tác vụ nền, scheduler hoặc batch job không có request đăng nhập, ứng dụng nên cung cấp một danh tính hệ thống có ý nghĩa như `system` hoặc `batch-job` thay vì để lịch sử thiếu người thực hiện.

`Optional.empty()` có nghĩa là provider không cung cấp auditor cho lần xử lý đó. Các trường auditor có thể không được thiết lập; nếu nghiệp vụ bắt buộc phải có người tạo/người sửa, cần xác định rõ cách xử lý request anonymous và tác vụ nền.

## 5. Sử dụng auditing qua repository

Sau khi cấu hình xong, mã nghiệp vụ chỉ cần lưu entity bằng repository. Ứng dụng không phải tự gọi setter để gán `createdBy` hoặc `lastModifiedBy`.

```java
package com.example.repository;

import com.example.domain.Article;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository
        extends JpaRepository<Article, Long> {
}
```

Ví dụ luồng sử dụng:

```java
Article article = new Article("Spring Data JPA");
articleRepository.save(article);

// Người dùng khác chỉnh sửa entity trong một transaction sau.
article.rename("Spring Data JPA Auditing");
articleRepository.save(article);
```

Khi entity được persist, listener gọi auditing handler để thiết lập metadata tạo mới. Khi entity được cập nhật, listener cập nhật metadata sửa đổi. Việc ghi thực tế diễn ra theo vòng đời JPA, thường tại thời điểm flush hoặc commit transaction; không nên dựa vào việc giá trị đã được đồng bộ ngay trước khi persistence context flush.

Kết quả mong đợi nếu lần đầu lưu do `alice` thực hiện và lần sau do `bob` thực hiện:

- Sau lần tạo: `createdBy = "alice"`, `lastModifiedBy = "alice"`.
- Sau lần chỉnh sửa: `createdBy = "alice"`, `lastModifiedBy = "bob"`.

Các giá trị được lưu trong database cùng entity, nên có thể đọc lại qua repository sau khi transaction hoàn tất.

## 6. Quan hệ giữa auditing người dùng và auditing thời gian

Spring Data JPA cung cấp thêm `@CreatedDate` và `@LastModifiedDate` để lưu thời điểm tạo và cập nhật. Chúng có thể được dùng cùng với hai annotation auditor:

```java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;
```

Các trường ngày giờ thường dùng kiểu `Instant`, `LocalDateTime` hoặc kiểu thời gian được Spring Data hỗ trợ. Khi cần cả người thực hiện và thời điểm, entity có thể lưu bốn thông tin:

| Trường | Ý nghĩa |
|---|---|
| `createdBy` | Ai tạo bản ghi |
| `createdDate` | Bản ghi được tạo lúc nào |
| `lastModifiedBy` | Ai sửa gần nhất |
| `lastModifiedDate` | Bản ghi được sửa gần nhất lúc nào |

Hai annotation người dùng không tự tạo timestamp. Nếu cần ngày giờ, phải khai báo thêm các trường date tương ứng. Spring Data dùng auditing handler để thiết lập chúng trong cùng quy trình lifecycle.

## 7. Lưu ý với async, batch và thao tác ngoài JPA

Auditing dựa trên thông tin auditor mà ứng dụng cung cấp tại thời điểm listener xử lý entity. Một số tình huống cần được thiết kế riêng:

- **Async execution:** `SecurityContextHolder` thường gắn với thread xử lý request. Khi chuyển công việc sang thread khác, context có thể không còn. Cần truyền hoặc thiết lập danh tính một cách an toàn cho tác vụ async.
- **Scheduled job và batch:** không có người dùng đăng nhập như request thông thường. Hãy dùng auditor hệ thống có tên rõ ràng để phân biệt thay đổi tự động với thay đổi của người dùng.
- **Anonymous request:** nếu `AuditorAware` trả về `Optional.empty()`, hệ thống không có auditor để ghi. Xác định xem trường được phép null hay cần gán actor hệ thống.
- **Bulk JPQL UPDATE/DELETE:** truy vấn bulk tác động trực tiếp lên database và bỏ qua lifecycle callback của từng entity. `AuditingEntityListener` vì thế không tự cập nhật `lastModifiedBy` cho các dòng bị bulk update. Nếu cần audit trong thao tác đó, hãy đưa giá trị auditor vào câu lệnh hoặc dùng một quy trình ghi nhận riêng.
- **Native SQL hoặc ghi ngoài JPA:** listener JPA không chạy khi dữ liệu được cập nhật trực tiếp bằng SQL, công cụ khác hoặc service khác. Nếu mọi đường ghi đều phải có audit, cần bảo đảm tất cả writer tuân thủ cùng quy tắc hoặc chuyển một phần trách nhiệm xuống database.

Auditing ứng dụng hữu ích để biết actor trong luồng JPA. Nó không thay thế audit log bảo mật bất biến khi hệ thống cần bằng chứng chống chỉnh sửa, theo dõi thay đổi trước/sau hoặc lưu lịch sử đầy đủ.

## 8. Lỗi thường gặp và cách kiểm tra

- **Thiếu `@EnableJpaAuditing`:** auditing infrastructure chưa được đăng ký. Bật annotation trong cấu hình Spring.
- **Thiếu `@EntityListeners(AuditingEntityListener.class)`:** entity không nhận callback auditing. Đăng ký listener trên entity hoặc lớp `@MappedSuperclass` dùng chung.
- **Không có bean `AuditorAware`:** Spring không thể lấy auditor khi cấu hình yêu cầu bean. Tạo bean và bảo đảm tên khớp với `auditorAwareRef`.
- **Sai kiểu generic:** `AuditorAware<Long>` không tương thích với trường auditor kiểu `String`. Đồng bộ kiểu trả về và kiểu thuộc tính.
- **Luôn nhận giá trị rỗng:** kiểm tra SecurityContext, trạng thái authentication, anonymous token và việc truyền context sang thread khác.
- **Người tạo bị thay đổi khi update:** kiểm tra mapping cột và không tự gán lại trường `createdBy`. Có thể đặt `updatable = false` để ngăn cập nhật cột này ở SQL UPDATE.
- **Bulk update không đổi người sửa:** đây là hành vi dự kiến vì bulk update bỏ qua entity listener. Hãy cập nhật auditor tường minh hoặc dùng thao tác entity thông thường nếu cần lifecycle callback.

Để xác minh, hãy tạo một entity khi đăng nhập bằng user A, flush và đọc lại để kiểm tra hai trường auditor. Sau đó chỉnh sửa entity bằng user B trong transaction khác, flush và đọc lại lần nữa. Kết quả cần giữ nguyên `createdBy` là A và cập nhật `lastModifiedBy` thành B. Bổ sung một bài kiểm tra cho anonymous hoặc batch job để xác nhận chính sách khi không có người dùng request.

## 9. Ghi nhớ

`@CreatedBy` và `@LastModifiedBy` đánh dấu các trường lưu actor tạo và sửa entity. `AuditingEntityListener` kết nối vòng đời JPA với auditing handler, `@EnableJpaAuditing` bật hạ tầng và `AuditorAware<T>` cung cấp danh tính hiện tại. Khi triển khai, hãy đồng bộ kiểu dữ liệu auditor, xử lý rõ anonymous và tác vụ nền, đồng thời nhớ rằng bulk update và các đường ghi ngoài JPA không tự kích hoạt auditing listener.