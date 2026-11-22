# Kiểm thử auditing, callback và sự kiện sau commit trong Spring Data JPA

Một ứng dụng Spring Data JPA thường cần kiểm tra ba nhóm hành vi có liên quan nhưng khác nhau:

- **Auditing** tự ghi nhận người tạo, người sửa và thời điểm tạo/sửa entity.
- **JPA lifecycle callback** chạy quanh các thao tác persist, update, remove của từng entity.
- **Sự kiện sau commit** chạy khi transaction đã commit thành công, phù hợp để bắt đầu một tác vụ tiếp theo như gửi thông báo hoặc tạo yêu cầu xử lý.

Các cơ chế này có thời điểm thực thi và mục đích khác nhau. Một bài kiểm thử đúng phải chứng minh dữ liệu audit đã được ghi, callback đã được gọi khi entity được flush, và listener AFTER_COMMIT chỉ chạy sau khi transaction thực sự commit. Bài viết dùng Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5, AssertJ và H2 trong ví dụ.

## 1. Phân biệt auditing, callback và transaction event

| Cơ chế | Thời điểm | Mục đích |
|---|---|---|
| Spring Data Auditing | Khi entity được tạo hoặc cập nhật qua JPA lifecycle | Ghi created/modified date và auditor |
| JPA callback như `@PrePersist`, `@PostUpdate` | Quanh thao tác persist/update/remove của từng entity | Chuẩn hóa hoặc kiểm tra trạng thái entity |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau khi transaction commit thành công | Kích hoạt công việc phụ thuộc vào dữ liệu đã commit |

Không nên xem `@PostPersist` là sự kiện sau commit. Callback này được gọi sau khi thao tác INSERT được thực hiện, nhưng transaction vẫn có thể rollback sau đó. Nếu cần phản ứng chỉ khi transaction commit, dùng transaction-bound event.

Spring Data Auditing cũng dựa trên JPA entity listener. Nó giúp quản lý các trường metadata phổ biến, trong khi callback tùy chỉnh dành cho logic gắn với vòng đời entity. Transaction event lại hoạt động ở cấp transaction, không phải cấp entity.

## 2. Cấu hình Spring Data Auditing

Spring Data JPA cung cấp các annotation:

- `@CreatedDate`: thời điểm tạo entity.
- `@LastModifiedDate`: thời điểm sửa gần nhất.
- `@CreatedBy`: người tạo entity.
- `@LastModifiedBy`: người sửa gần nhất.

Các annotation này thuộc `org.springframework.data.annotation`. Để chúng được xử lý trong JPA, gắn `AuditingEntityListener` và bật `@EnableJpaAuditing`.

Tạo lớp cha dùng chung:

**AuditableEntity.java**

```java
package com.example.audit;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedDate
    @Column(updatable = false, nullable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

Entity kế thừa lớp cha:

**AuditNote.java**

```java
package com.example.audit;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_notes")
public class AuditNote extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String content;

    protected AuditNote() {
    }

    public AuditNote(String content) {
        this.content = content;
    }

    public Long getId() {
        return id;
    }

    public String getContent() {
        return content;
    }

    public void changeContent(String content) {
        this.content = content;
    }
}
```

Bật auditing trong cấu hình ứng dụng:

**JpaAuditConfig.java**

```java
package com.example.audit;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration(proxyBeanMethods = false)
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditConfig {
}
```

Khai báo `AuditorAware` để Spring Data biết ai đang thực hiện thao tác:

**AuditorConfig.java**

```java
package com.example.audit;

import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration(proxyBeanMethods = false)
public class AuditorConfig {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system-user");
    }
}
```

Trong production, giá trị auditor thường lấy từ người dùng đã xác thực trong SecurityContext, hoặc từ context của tác vụ nền. Không nên ghi cố định `system-user` nếu cần truy vết người dùng thật. Khi không có người dùng, có thể trả về `Optional.empty()` hoặc một actor hệ thống theo quy ước của ứng dụng.

Có thể đặt `@EnableJpaAuditing` và bean `AuditorAware` trong cùng một configuration class. Ví dụ tách chúng ra để dễ thay thế auditor trong kiểm thử. Nếu ứng dụng đã bật auditing ở cấu hình production, không bật thêm một cấu hình trùng lặp trong test.

## 3. Kiểm thử auditing bằng @DataJpaTest

`@DataJpaTest` tạo Spring context tập trung cho JPA, cấu hình repository/entity và thường dùng database nhúng khi dependency phù hợp có mặt. Test slice có phạm vi hẹp, vì vậy cấu hình auditing có thể cần được import tường minh.

Cấu hình auditor cố định dành cho test:

**AuditingTestConfig.java**

```java
package com.example.audit;

import java.util.Optional;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@TestConfiguration(proxyBeanMethods = false)
@EnableJpaAuditing(auditorAwareRef = "testAuditorAware")
public class AuditingTestConfig {

    @Bean
    AuditorAware<String> testAuditorAware() {
        return () -> Optional.of("integration-test");
    }
}
```

Bài kiểm thử:

**AuditNoteTest.java**

```java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(AuditingTestConfig.class)
class AuditNoteTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void fillsCreatedAndModifiedAuditFields() {
        AuditNote note = new AuditNote("first version");

        entityManager.persistAndFlush(note);

        assertThat(note.getCreatedBy()).isEqualTo("integration-test");
        assertThat(note.getLastModifiedBy()).isEqualTo("integration-test");
        assertThat(note.getCreatedAt()).isNotNull();
        assertThat(note.getLastModifiedAt()).isNotNull();

        Instant createdAt = note.getCreatedAt();

        note.changeContent("second version");
        entityManager.flush();

        assertThat(note.getCreatedBy()).isEqualTo("integration-test");
        assertThat(note.getLastModifiedBy()).isEqualTo("integration-test");
        assertThat(note.getCreatedAt()).isEqualTo(createdAt);
        assertThat(note.getLastModifiedAt()).isAfterOrEqualTo(createdAt);
    }
}
```

Các assertion chứng minh:

1. Khi persist và flush, created date/by và modified date/by được gán.
2. Khi thay đổi một thuộc tính và flush, last modified được cập nhật.
3. Created date/by được giữ nguyên sau lần cập nhật.

Gọi `flush()` để buộc JPA đồng bộ thay đổi với database và kích hoạt lifecycle listener ngay trong test. Chỉ gọi `persist()` hoặc `save()` chưa chắc đã thực thi SQL ngay lập tức vì JPA có thể trì hoãn đến lúc flush hoặc commit.

Test slice mặc định chạy trong transaction được rollback sau mỗi test. Điều đó không cản trở kiểm thử auditing và callback vì chúng chạy trong quá trình persist/update và flush, trước khi rollback.

## 4. Kiểm thử JPA lifecycle callback

JPA callback phù hợp với logic nhỏ, đồng bộ và gắn trực tiếp với một entity. Ví dụ: chuẩn hóa chuỗi trước khi insert hoặc ghi dấu thời điểm entity được cập nhật.

**CallbackArticle.java**

```java
package com.example.audit;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Locale;

@Entity
@Table(name = "callback_articles")
public class CallbackArticle {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    private String normalizedTitle;

    private Instant updatedAt;

    protected CallbackArticle() {
    }

    public CallbackArticle(String title) {
        this.title = title;
    }

    public String getNormalizedTitle() {
        return normalizedTitle;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void rename(String title) {
        this.title = title;
    }

    @PrePersist
    void beforeInsert() {
        normalizedTitle = title == null
            ? null
            : title.trim().toLowerCase(Locale.ROOT);
    }

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Test callback:

**CallbackArticleTest.java**

```java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CallbackArticleTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void invokesPrePersistAndPreUpdate() {
        CallbackArticle article =
            new CallbackArticle("  Spring Data JPA  ");

        entityManager.persistAndFlush(article);

        assertThat(article.getNormalizedTitle())
            .isEqualTo("spring data jpa");

        article.rename("JPA callbacks");
        entityManager.flush();

        assertThat(article.getUpdatedAt()).isNotNull();
    }
}
```

`@PrePersist` chạy trước thao tác INSERT; `@PreUpdate` chạy trước thao tác UPDATE. Các callback khác gồm `@PostPersist`, `@PostUpdate`, `@PreRemove` và `@PostRemove`. Có thể đặt callback trực tiếp trong entity hoặc trong một lớp được khai báo bằng `@EntityListeners`.

Giữ callback ngắn và chỉ thay đổi trạng thái phù hợp của chính entity. Tránh gọi repository, truy vấn EntityManager, gửi HTTP/email hoặc thực hiện công việc bên ngoài trong callback. Những hành động đó làm vòng đời persistence khó dự đoán và không có bảo đảm rằng transaction cuối cùng sẽ commit. Nếu callback ném runtime exception trong transaction, thao tác persistence có thể thất bại và transaction bị rollback.

## 5. Phát hành sự kiện trong transaction và xử lý AFTER_COMMIT

Giả sử khi tạo hóa đơn, ứng dụng muốn gửi thông báo. Gửi email ngay trong phương thức service có thể tạo ra thông báo dù transaction lưu hóa đơn sau đó rollback.

Thay vào đó, service phát hành một application event trong transaction. Listener dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ xử lý khi transaction commit thành công.

Event:

**InvoiceCreatedEvent.java**

```java
package com.example.invoice;

public record InvoiceCreatedEvent(Long invoiceId) {
}
```

Entity và repository:

**Invoice.java**

```java
package com.example.invoice;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }

    public Long getId() {
        return id;
    }
}
```

**InvoiceRepository.java**

```java
package com.example.invoice;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InvoiceRepository
        extends JpaRepository<Invoice, Long> {
}
```

Service lưu entity và phát event:

**InvoiceService.java**

```java
package com.example.invoice;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public InvoiceService(
            InvoiceRepository repository,
            ApplicationEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long create(String invoiceNumber) {
        Invoice invoice =
            repository.saveAndFlush(new Invoice(invoiceNumber));

        eventPublisher.publishEvent(
            new InvoiceCreatedEvent(invoice.getId())
        );

        return invoice.getId();
    }
}
```

Listener:

**InvoiceCreatedListener.java**

```java
package com.example.invoice;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class InvoiceCreatedListener {

    private final List<Long> handledInvoiceIds =
        new CopyOnWriteArrayList<>();

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onInvoiceCreated(InvoiceCreatedEvent event) {
        handledInvoiceIds.add(event.invoiceId());
    }

    public List<Long> handledInvoiceIds() {
        return List.copyOf(handledInvoiceIds);
    }
}
```

Event được publish trước khi transaction kết thúc, nhưng listener được gọi sau commit. Nếu transaction rollback, listener AFTER_COMMIT không được gọi. Nếu event được publish ngoài transaction, listener transaction-bound mặc định không chạy; thuộc tính `fallbackExecution = true` có thể thay đổi hành vi đó, nhưng chỉ bật khi nghiệp vụ thực sự muốn xử lý cả trường hợp không có transaction.

Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Chọn phase theo thời điểm nghiệp vụ yêu cầu. `@EventListener` thông thường xử lý ngay khi event được publish và không chờ commit.

## 6. Kiểm thử sự kiện sau commit và rollback

Một điểm dễ gây nhầm lẫn: `@DataJpaTest` mặc định chạy mỗi test trong transaction do Spring Test quản lý và rollback khi test kết thúc. Vì transaction chưa commit, listener AFTER_COMMIT sẽ không được gọi trong phần thân test.

Để kiểm thử commit thực sự, có thể tắt transaction test-managed cho phương thức test. Khi đó, lời gọi tới service mở transaction riêng qua proxy; service commit trước khi trả về và listener đồng bộ được gọi trước khi test tiếp tục.

**InvoiceAfterCommitTest.java**

```java
package com.example.invoice;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
@Import({InvoiceService.class, InvoiceCreatedListener.class})
class InvoiceAfterCommitTest {

    @Autowired
    private InvoiceService invoiceService;

    @Autowired
    private InvoiceCreatedListener listener;

    @Autowired
    private InvoiceRepository repository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private ApplicationEventPublisher eventPublisher;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void handlesEventAfterServiceTransactionCommits() {
        Long id = invoiceService.create("INV-2026-001");

        assertThat(repository.findById(id)).isPresent();
        assertThat(listener.handledInvoiceIds()).containsExactly(id);
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void doesNotHandleEventWhenTransactionRollsBack() {
        TransactionTemplate transaction =
            new TransactionTemplate(transactionManager);

        transaction.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );

        transaction.executeWithoutResult(status -> {
            eventPublisher.publishEvent(
                new InvoiceCreatedEvent(-1L)
            );
            status.setRollbackOnly();
        });

        assertThat(listener.handledInvoiceIds()).doesNotContain(-1L);
    }
}
```

Trong test commit, service được gọi qua Spring bean đã được proxy nên `@Transactional` mở và commit transaction. Vì listener mặc định chạy đồng bộ, sau khi `create()` trả về, danh sách đã có invoice ID.

Trong test rollback, event được publish khi transaction đang hoạt động, nhưng transaction bị đánh dấu rollback-only. Listener AFTER_COMMIT không được gọi nên ID kiểm thử `-1L` không xuất hiện trong danh sách.

Nếu giữ transaction test mặc định, test không commit ở cuối phương thức nên assertion ngay trong test sẽ thấy listener chưa được gọi. Có thể dùng `@Commit` hoặc `TestTransaction.flagForCommit()` và `TestTransaction.end()`, nhưng khi cần kiểm tra ngay sau khi service commit, tắt test transaction giúp ranh giới dễ hiểu hơn.

Nếu listener được đánh dấu `@Async`, xử lý sẽ chạy trên executor khác và có thể hoàn tất sau khi service trả về. Khi đó, test cần chờ có điều kiện bằng cơ chế đồng bộ phù hợp; không dùng sleep cố định vì dễ gây flaky test.

## 7. Ghi dữ liệu mới trong listener sau commit

Sau khi AFTER_COMMIT chạy, transaction gốc đã hoàn tất. Tài nguyên persistence có thể vẫn được gắn với thread trong quá trình hoàn tất callback, nhưng các thay đổi database phát sinh tại thời điểm này sẽ không được commit như một phần của transaction đã hoàn tất.

Nếu listener cần ghi thêm dữ liệu, hãy gọi một service khác mở transaction mới:

```java
@Service
public class NotificationLogService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordSent(Long invoiceId) {
        // Persist notification log in a new transaction.
    }
}
```

Listener inject `NotificationLogService` và gọi phương thức này. Dùng một Spring bean riêng để lời gọi đi qua transaction proxy; gọi một phương thức `REQUIRES_NEW` khác trong cùng object bằng self-invocation sẽ không kích hoạt proxy như mong muốn.

Có thể kết hợp `@Async` nếu muốn tách việc gửi thông báo khỏi thread commit:

```java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendInvoiceNotice(InvoiceCreatedEvent event) {
    // Delegate to a notification service.
}
```

Cần bật `@EnableAsync` và cấu hình executor phù hợp. Lỗi trong tác vụ async không được ném ngược về request đã commit; cần log, retry và giám sát riêng.

## 8. AFTER_COMMIT không thay thế hàng đợi bền vững

Transaction-bound event bảo đảm listener chỉ được gọi sau commit trong tiến trình hiện tại. Nó không phải message broker và không tự lưu event bền vững. Nếu ứng dụng dừng đột ngột sau khi commit nhưng trước khi listener hoàn tất, công việc phụ có thể bị mất.

Với email, webhook hoặc message quan trọng cần bảo đảm giao nhận, cân nhắc transactional outbox:

1. Trong cùng transaction nghiệp vụ, lưu hóa đơn và một bản ghi outbox mô tả event.
2. Commit cả hai cùng nhau.
3. Một worker đọc các bản ghi outbox chưa xử lý và gửi message.
4. Đánh dấu đã xử lý sau khi gửi thành công; hỗ trợ retry và idempotency để tránh xử lý trùng.

Có thể dùng AFTER_COMMIT event để đánh thức worker như một tối ưu, nhưng bản ghi outbox mới là nguồn dữ liệu bền vững để khôi phục khi ứng dụng restart.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Trường created/modified luôn null | Chưa bật auditing, thiếu `AuditingEntityListener` hoặc thiếu `AuditorAware` | Kiểm tra `@EnableJpaAuditing`, listener và auditor bean |
| CreatedBy có giá trị nhưng LastModifiedBy trống | AuditorAware trả về empty hoặc context người dùng không có ở thời điểm flush | Kiểm tra nguồn lấy actor và thời điểm thực thi |
| Callback không chạy khi test | Chưa flush hoặc entity không phát sinh UPDATE thực tế | Dùng `persistAndFlush`, thay đổi thuộc tính rồi flush |
| AFTER_COMMIT listener không chạy trong @DataJpaTest | Test-managed transaction bị rollback thay vì commit | Tắt transaction của test hoặc chủ động kết thúc test transaction bằng commit |
| Listener chạy dù thao tác nghiệp vụ thất bại | Dùng `@EventListener` tức thời thay vì transaction-bound listener | Dùng `@TransactionalEventListener` với phase phù hợp |
| Ghi DB trong listener nhưng không thấy dữ liệu | Đang dùng transaction đã commit xong | Gọi service khác với `REQUIRES_NEW` |
| Event async không được kiểm tra ổn định | Test assertion trước khi executor xử lý xong | Dùng latch, future hoặc điều kiện chờ có timeout |
| Thông báo có thể mất khi process dừng | In-process event không có lưu trữ bền vững | Dùng transactional outbox và cơ chế retry |

## 10. Checklist cho bộ kiểm thử

- **Auditing:** test cả lần persist và lần update; xác nhận created fields giữ nguyên và modified fields được cập nhật.
- **Auditor:** dùng actor cố định trong test để kết quả lặp lại được; kiểm tra trường hợp không có actor.
- **Lifecycle callback:** flush sau persist/update; xác nhận thay đổi do callback tạo ra; không dựa vào callback để chứng minh commit.
- **Transaction event:** kiểm tra listener AFTER_COMMIT với transaction đã commit thật; kiểm tra rollback không kích hoạt listener.
- **Test slice:** nhớ rằng `@DataJpaTest` mặc định rollback; cấu hình rõ khi test cần commit.
- **Async:** đồng bộ test bằng latch/future thay vì sleep; kiểm tra lỗi executor.
- **Độ bền:** nếu công việc phụ không được phép mất, kiểm thử outbox, retry và idempotency.

Auditing trả lời câu hỏi ai tạo/sửa và khi nào; callback xử lý một phần vòng đời của entity; transaction event điều phối công việc theo kết quả commit. Tách đúng ba trách nhiệm này giúp test phản ánh chính xác hành vi của Spring Data JPA và tránh gửi thông báo hoặc ghi dữ liệu phụ từ một transaction chưa thành công.