# Phân biệt thông tin người sửa cuối với lịch sử từng phiên bản

Trong ứng dụng Spring Data JPA, hai nhu cầu thường bị nhầm lẫn:

1. **Biết ai tạo và ai sửa bản ghi gần nhất:** lưu metadata như người tạo, thời điểm tạo, người sửa cuối và thời điểm sửa cuối ngay trên bảng entity.
2. **Biết dữ liệu đã thay đổi như thế nào qua thời gian:** lưu lại các phiên bản trước và sau của entity để có thể xem trạng thái tại một thời điểm hoặc một revision.

Spring Data JPA Auditing giải quyết nhu cầu thứ nhất. Hibernate Envers là một lựa chọn phổ biến để giải quyết nhu cầu thứ hai bằng cách lưu lịch sử revision. Hai cơ chế có thể được dùng cùng nhau, nhưng chúng không thay thế cho nhau.

Bài này trình bày cơ chế của từng cách, cấu hình người thực hiện thao tác, truy vấn lịch sử, tác động của bulk update/delete, cách kiểm thử và tiêu chí chọn giải pháp theo yêu cầu nghiệp vụ.

**Điều kiện của ví dụ:** các đoạn mã dùng Java 17 trở lên, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence và Hibernate. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Ví dụ lấy người dùng từ Spring Security; nếu ứng dụng không dùng Spring Security, thay phần lấy principal bằng nguồn định danh đáng tin cậy của ứng dụng. Đây là các phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng javac.

## 1. Hai nhu cầu khác nhau

Giả sử bảng **products** có một sản phẩm:

| id | name | price | created_by | created_at | last_modified_by | last_modified_at |
|---:|---|---:|---|---|---|---|
| 42 | Keyboard | 800000 | linh | 2026-10-01 | minh | 2026-11-09 |

Các cột created_by và last_modified_by trả lời:

- Ai đã tạo sản phẩm?
- Ai là người sửa gần nhất?
- Sản phẩm được tạo và sửa lần cuối lúc nào?

Nhưng chúng không trả lời được:

- Trước ngày 9/11, giá sản phẩm là bao nhiêu?
- Ai đã sửa giá từ 750000 thành 800000?
- Tên sản phẩm đã thay đổi qua những lần nào?
- Trạng thái sản phẩm ở revision thứ ba là gì?

Khi Minh sửa sản phẩm, last_modified_by và last_modified_at được cập nhật. Giá trị của người sửa trước đó bị thay thế. Nếu cần lịch sử, phải có nơi lưu các phiên bản cũ.

| Khả năng | Spring Data Auditing | Lịch sử revision |
|---|---|---|
| Người tạo | Có thể lưu | Có thể lưu trong revision metadata |
| Thời điểm tạo | Có | Có |
| Người sửa cuối | Có | Có thể xác định từ revision mới nhất nếu lưu actor |
| Thời điểm sửa cuối | Có | Có thể xác định từ revision mới nhất |
| Xem giá trị cũ | Không | Có |
| Xem trạng thái entity tại revision trước | Không | Có |
| Theo dõi nhiều lần thay đổi | Không | Có |
| Dung lượng lưu trữ | Thấp | Cao hơn theo số revision |

Không nên gọi bốn cột created/modified là một hệ thống version history. Chúng chỉ mô tả metadata hiện tại của một hàng.

## 2. Spring Data JPA Auditing lưu metadata hiện tại

Spring Data Auditing cung cấp bốn annotation thường dùng:

- **@CreatedBy**: người tạo entity.
- **@CreatedDate**: thời điểm tạo entity.
- **@LastModifiedBy**: người sửa entity gần nhất.
- **@LastModifiedDate**: thời điểm sửa entity gần nhất.

Các giá trị được cập nhật thông qua JPA entity lifecycle listener. Chúng được lưu cùng hàng entity và không tự tạo bảng lịch sử riêng.

### Tạo lớp Auditable dùng chung

Có thể đặt các field audit trong một mapped superclass:

~~~java
package com.example.audit;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class Auditable {

    @CreatedBy
    @Column(name = "created_by", updatable = false, length = 100)
    private String createdBy;

    @CreatedDate
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @LastModifiedBy
    @Column(name = "last_modified_by", length = 100)
    private String lastModifiedBy;

    @LastModifiedDate
    @Column(name = "last_modified_at")
    private Instant lastModifiedAt;

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

Entity kế thừa lớp này:

~~~java
package com.example.catalog.domain;

import com.example.audit.Auditable;
import jakarta.persistence.*;

import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product extends Auditable {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }

    public void rename(String newName) {
        this.name = newName;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

**@MappedSuperclass** cho phép các entity kế thừa mapping field audit mà không tạo một bảng riêng cho lớp Auditable. **@EntityListeners(AuditingEntityListener.class)** kết nối lifecycle callback của JPA với Spring Data Auditing.

Dùng **updatable = false** cho createdBy và createdAt giúp JPA không đưa các cột này vào câu UPDATE thông thường. Đây là bảo vệ ở mức mapping ORM; quyền database và các câu SQL trực tiếp vẫn cần được quản lý riêng.

## 3. Bật auditing và cung cấp AuditorAware

Spring Data cần biết actor hiện tại để điền @CreatedBy và @LastModifiedBy. Interface **AuditorAware<T>** cung cấp thông tin đó.

Cấu hình:

~~~java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

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
~~~

**@EnableJpaAuditing** kích hoạt cơ chế auditing. Thuộc tính **auditorAwareRef** chỉ định bean được dùng để lấy actor.

Trong ví dụ:

- Người dùng đã đăng nhập được định danh bằng authentication.getName().
- Request anonymous không được gán nhầm thành một người dùng đã xác thực.
- Khi không có actor, AuditorAware trả Optional.empty(); field auditor có thể để null tùy cấu hình và yêu cầu của ứng dụng.

Nếu hệ thống có batch job hoặc scheduler, cần quy định actor cho các thao tác nền, ví dụ một định danh service account như **system:nightly-import**. Không nên nhận giá trị createdBy/lastModifiedBy trực tiếp từ request body vì client có thể giả mạo người thực hiện.

Nếu không dùng Spring Security, AuditorAware có thể lấy user ID từ request context, application context hoặc cơ chế xác thực riêng. Nguồn dữ liệu phải phản ánh actor đã được xác thực.

## 4. Metadata được cập nhật vào thời điểm nào?

Khi entity được persist lần đầu:

- createdBy và createdAt được thiết lập.
- lastModifiedBy và lastModifiedAt cũng có thể được thiết lập cho lần tạo đầu tiên, vì đây cũng là lần thay đổi đầu tiên.

Khi entity managed được cập nhật và JPA thực hiện lifecycle update:

- createdBy và createdAt được giữ nguyên.
- lastModifiedBy và lastModifiedAt được cập nhật theo actor và thời gian hiện tại.

Ví dụ service:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = repository.findById(id).orElseThrow();
        product.changePrice(newPrice);

        // Dirty checking sẽ ghi thay đổi khi flush/commit.
        // AuditingEntityListener cập nhật lastModified metadata.
    }
}
~~~

Entity đã được tải trong transaction là managed. Dirty checking phát hiện thay đổi và Hibernate thực hiện UPDATE khi flush. Entity listener của Spring Data cập nhật các field audit trong lifecycle callback tương ứng.

Nếu dùng **save()** trên repository, Spring Data vẫn thực hiện persist hoặc merge theo trạng thái entity. Với entity managed trong transaction, thường không cần gọi save chỉ để kích hoạt dirty checking.

**@Transactional(readOnly = true)** không phải transaction ghi. Không dùng một transaction chỉ đọc cho thao tác thay đổi dữ liệu rồi mong audit metadata được cập nhật như một lần ghi bình thường.

## 5. Vì sao Auditing không phải lịch sử từng phiên bản?

Giả sử một sản phẩm thay đổi ba lần:

| Thời điểm | Actor | Giá |
|---|---|---:|
| 01/10 | linh | 700000 |
| 05/10 | minh | 750000 |
| 09/11 | hoa | 800000 |

Nếu chỉ dùng Spring Data Auditing, hàng products cuối cùng có thể lưu:

~~~text
price = 800000
created_by = linh
created_at = 2026-10-01
last_modified_by = hoa
last_modified_at = 2026-11-09
~~~

Thông tin về giá 700000 và 750000 đã bị thay thế. Cột last_modified_by cũng chỉ giữ actor gần nhất. Không có cách khôi phục toàn bộ lịch sử từ bốn cột này.

Nếu yêu cầu cần biết mỗi revision đã thay đổi những gì, cần một cơ chế ghi lịch sử riêng, ví dụ:

- Hibernate Envers.
- Bảng audit tự thiết kế.
- Event store hoặc domain event log.
- CDC/audit ở tầng database, tùy kiến trúc.

## 6. Hibernate Envers lưu lịch sử revision

**Hibernate Envers** là module của Hibernate dùng để theo dõi lịch sử thay đổi entity. Envers tạo revision và bảng audit tương ứng cho các entity được đánh dấu **@Audited**.

Với entity Product, có thể thêm:

~~~java
import org.hibernate.envers.Audited;

@Entity
@Table(name = "products")
@Audited
public class Product extends Auditable {
    // id, name, price và các field khác
}
~~~

Khi entity được tạo, cập nhật hoặc xóa qua entity lifecycle được Envers hỗ trợ, Envers ghi dữ liệu revision trong cùng transaction database.

Theo cấu hình mặc định thường gặp:

- Bảng **REVINFO** lưu thông tin revision, như revision number và timestamp.
- Bảng **products_AUD** lưu trạng thái audit của Product qua các revision.
- Cột **REV** liên kết bản ghi audit với revision.
- Cột **REVTYPE** biểu thị loại thay đổi: ADD, MOD hoặc DEL.

Tên bảng và cấu trúc có thể được cấu hình. Đây là mô hình lịch sử trạng thái entity, không phải tự động ghi lại mọi thao tác SQL tùy ý.

### Cấu hình dependency

Với Spring Boot, thêm module Envers tương thích với Hibernate version do Spring Boot quản lý:

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
</dependency>
~~~

Thông thường nên để Spring Boot dependency management chọn version đồng bộ với Hibernate ORM hiện có. Không tự nâng riêng Envers sang một version khác nếu chưa xác nhận tương thích.

## 7. Đánh dấu entity và field cần audit

Có thể đánh dấu toàn entity:

~~~java
@Entity
@Audited
@Table(name = "products")
public class Product {
    // ...
}
~~~

Khi đó các thuộc tính persistent phù hợp được theo dõi trong revision history.

Nếu một field không cần lưu lịch sử, có thể dùng **@NotAudited**:

~~~java
@Audited
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    @NotAudited
    private String temporaryDisplayHint;
}
~~~

Không đưa dữ liệu nhạy cảm như password hash, token, secret hoặc thông tin không cần thiết vào audit history chỉ vì entity đã được đánh dấu @Audited. Lịch sử có thể tồn tại lâu hơn dữ liệu hiện tại và cần chính sách phân quyền, retention, masking và xóa dữ liệu phù hợp.

Với association, cần xác định entity đích có được audit hay không. Envers có các tùy chọn mapping như **RelationTargetAuditMode.NOT_AUDITED** cho trường hợp muốn lưu quan hệ tới entity không được audit; hãy thiết kế và kiểm thử riêng cho từng loại quan hệ.

## 8. Truy vấn trạng thái entity ở revision trước

Envers cung cấp **AuditReader** để đọc lịch sử.

Ví dụ service:

~~~java
@Service
public class ProductHistoryService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<Number> findRevisions(Long productId) {
        AuditReader reader =
            AuditReaderFactory.get(entityManager);

        return reader.getRevisions(Product.class, productId);
    }

    @Transactional(readOnly = true)
    public Product findAtRevision(Long productId, Number revision) {
        AuditReader reader =
            AuditReaderFactory.get(entityManager);

        return reader.find(Product.class, productId, revision);
    }
}
~~~

**getRevisions(Product.class, productId)** trả về các revision number có lịch sử của entity đó.

**find(Product.class, productId, revision)** trả về trạng thái Product tại revision được yêu cầu. Kết quả là trạng thái lịch sử được dựng lại từ audit data; không dùng object đó như entity hiện tại để ghi đè dữ liệu production.

Ví dụ sử dụng:

~~~java
List<Number> revisions = historyService.findRevisions(productId);

for (Number revision : revisions) {
    Product snapshot =
        historyService.findAtRevision(productId, revision);

    System.out.println(
        revision + " -> " + snapshot.getName()
            + ", price=" + snapshot.getPrice()
    );
}
~~~

Đây là đoạn mã minh họa cách gọi API trong ứng dụng có Envers và dữ liệu audit đã tồn tại. Giá trị thực tế phụ thuộc lịch sử revision của database.

Nếu entity đã bị xóa, Envers vẫn có thể lưu revision xóa; việc đọc trạng thái trước khi xóa và cách biểu diễn revision DEL phụ thuộc audit strategy và cấu hình. Hãy kiểm thử trường hợp xóa riêng.

## 9. Lưu actor và thông tin bổ sung vào revision

Envers mặc định lưu revision number và timestamp. Nếu cần biết **ai** tạo revision, có thể dùng custom revision entity và **RevisionListener** để bổ sung actor hoặc metadata phù hợp.

Ví dụ cấu trúc custom revision entity:

~~~java
@Entity
@Table(name = "REVINFO")
@RevisionEntity(ActorRevisionListener.class)
public class ActorRevision extends DefaultRevisionEntity {

    @Column(name = "actor", length = 100)
    private String actor;

    public String getActor() {
        return actor;
    }

    public void setActor(String actor) {
        this.actor = actor;
    }
}
~~~

Listener:

~~~java
public class ActorRevisionListener implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        ActorRevision revision = (ActorRevision) revisionEntity;

        // Đọc actor từ context được ứng dụng quản lý an toàn.
        revision.setActor(AuditActorContext.currentActor());
    }
}
~~~

**AuditActorContext** trong ví dụ là adapter do ứng dụng tự xây dựng để cung cấp actor cho listener; đây không phải class có sẵn của Hibernate. Cần thiết kế context này để hoạt động đúng với request thread, async execution, scheduled job và message consumer. Không giả định RevisionListener luôn có thể nhận một Spring bean thông qua constructor injection.

Có thể bổ sung các thông tin như correlation ID hoặc loại nguồn thay đổi nếu chúng cần thiết cho việc điều tra. Tránh lưu toàn bộ request payload hoặc bí mật xác thực vào revision metadata.

Khi kết hợp Spring Data Auditing và Envers:

- createdBy/lastModifiedBy cung cấp thông tin nhanh trên entity hiện tại.
- Actor trong revision metadata cho biết người thực hiện từng revision.
- Envers lưu trạng thái entity theo revision để có thể so sánh các phiên bản.

Không nhất thiết phải dùng cả hai. Chọn theo nhu cầu truy vấn hiện tại và lịch sử.

## 10. Bulk update/delete có thể bỏ qua cả hai cơ chế

Một giới hạn quan trọng: JPQL bulk update/delete và native SQL DML chạy trực tiếp trên database, bỏ qua entity lifecycle thông thường.

Ví dụ:

~~~java
@Modifying
@Transactional
@Query("""
    update Product p
    set p.price = :price
    where p.id = :id
    """)
int updatePriceDirectly(
    @Param("id") Long id,
    @Param("price") BigDecimal price
);
~~~

Đây là bulk JPQL update. Nó không tải từng Product rồi thực hiện lifecycle update. Vì vậy:

- Spring Data AuditingEntityListener không được gọi cho từng entity.
- @LastModifiedBy và @LastModifiedDate không tự được cập nhật.
- Envers không tự tạo revision cho từng entity bị tác động bởi bulk DML.
- Persistence context có thể vẫn giữ object cũ sau khi database đã thay đổi.

Nếu cần audit history đầy đủ, hãy dùng entity lifecycle update hoặc tự ghi audit record một cách tường minh trong cùng transaction. Với bulk DML, có thể cập nhật các cột audit trực tiếp trong câu lệnh, nhưng đó vẫn không tạo đầy đủ revision history như Envers.

Ví dụ cập nhật metadata trực tiếp:

~~~java
@Modifying
@Transactional
@Query("""
    update Product p
    set p.price = :price,
        p.lastModifiedBy = :actor,
        p.lastModifiedAt = :changedAt
    where p.id = :id
    """)
int updatePriceAndAudit(
    @Param("id") Long id,
    @Param("price") BigDecimal price,
    @Param("actor") String actor,
    @Param("changedAt") Instant changedAt
);
~~~

Cách này chỉ cập nhật metadata hiện tại. Nó không tạo snapshot cũ/mới trong Envers. Nếu cần lịch sử, phải thiết kế thao tác ghi revision/audit riêng hoặc tránh bulk DML cho use case đó.

Sau bulk DML, cân nhắc flush trước và clear persistence context sau truy vấn để tránh entity managed bị stale. Các tùy chọn **flushAutomatically** và **clearAutomatically** trên @Modifying có thể hỗ trợ, nhưng clear sẽ detach các entity trong persistence context hiện tại.

## 11. @Version không phải auditing hoặc revision history

Một annotation khác dễ bị nhầm là **@Version** của JPA:

~~~java
@Version
private Long version;
~~~

@Version hỗ trợ optimistic locking. Nó giúp phát hiện transaction cập nhật dựa trên một phiên bản đã cũ, thường bằng cách đưa version hiện tại vào điều kiện UPDATE.

Ví dụ hai người cùng tải Product version 4:

1. Người A cập nhật trước, version tăng thành 5.
2. Người B vẫn đang giữ version 4.
3. Khi B cập nhật, điều kiện version không còn khớp và provider báo optimistic locking conflict.

@Version không lưu nội dung các phiên bản trước. Nó chỉ quản lý số version hiện tại để phát hiện cập nhật đồng thời.

| Cơ chế | Mục đích chính |
|---|---|
| @CreatedBy / @LastModifiedBy | Ai tạo và ai sửa gần nhất |
| @CreatedDate / @LastModifiedDate | Khi nào tạo và sửa gần nhất |
| Hibernate Envers | Lịch sử trạng thái entity qua các revision |
| @Version | Phát hiện cập nhật đồng thời dựa trên version |

Một entity có thể dùng cả @Version, Spring Data Auditing và Envers nếu nghiệp vụ cần cả ba khả năng.

## 12. Lịch sử revision không giống domain event log

Envers lưu trạng thái entity theo revision. Điều đó hữu ích để trả lời “Product đã có giá trị nào tại revision 7?”.

Nhưng nó không tự trả lời đầy đủ các câu hỏi nghiệp vụ:

- Vì sao người dùng đổi giá?
- Đơn hàng nào dẫn tới thay đổi sản phẩm?
- Hệ thống đã gửi thông báo nào?
- Một hành động nghiệp vụ đã xảy ra theo trình tự nào?
- Có cần phát sự kiện sang hệ thống khác không?

Đây là khác biệt giữa state history và domain event:

- **State history** lưu snapshot/trạng thái entity qua các revision.
- **Domain event** diễn đạt sự kiện có ý nghĩa nghiệp vụ, ví dụ ProductPriceChanged với giá cũ, giá mới, actor, lý do và correlation ID.
- **Transactional outbox** lưu sự kiện cần phát trong cùng transaction database để worker gửi sau commit.

Nếu cần điều tra nghiệp vụ, tích hợp hệ thống hoặc tái dựng chuỗi hành động, hãy cân nhắc domain event/outbox thay vì coi Envers là event store hoàn chỉnh.

## 13. Chọn chiến lược theo yêu cầu

| Yêu cầu | Giải pháp phù hợp |
|---|---|
| Chỉ cần hiển thị người sửa cuối | Spring Data Auditing |
| Cần createdAt/createdBy và modifiedAt/modifiedBy | Spring Data Auditing |
| Cần xem trạng thái entity tại revision cũ | Hibernate Envers |
| Cần actor cho từng revision | Envers với custom revision entity/listener |
| Cần phát sự kiện sau khi transaction commit | Transactional event/outbox |
| Cần phát hiện hai người cùng cập nhật | @Version optimistic locking |
| Cần audit các bulk SQL hoặc thay đổi ngoài JPA | Audit database/CDC hoặc ghi audit tường minh |

Nếu ứng dụng chỉ cần bốn cột audit, Envers có thể làm tăng dung lượng và độ phức tạp không cần thiết. Nếu yêu cầu là lịch sử từng lần sửa, bốn cột audit không đủ.

## 14. Kiểm thử Spring Data Auditing

Một integration test nên xác nhận created metadata được giữ nguyên và modified metadata được cập nhật.

Ví dụ test configuration cung cấp actor cố định:

~~~java
@TestConfiguration
@EnableJpaAuditing
class AuditTestConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("test-user");
    }
}
~~~

Test:

~~~java
@DataJpaTest
@Import(AuditTestConfiguration.class)
class ProductAuditingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void recordsCreatedAndModifiedMetadata() {
        Product product =
            new Product("Keyboard", new BigDecimal("800000"));

        entityManager.persistAndFlush(product);

        assertThat(product.getCreatedBy()).isEqualTo("test-user");
        assertThat(product.getCreatedAt()).isNotNull();
        assertThat(product.getLastModifiedBy()).isEqualTo("test-user");
        assertThat(product.getLastModifiedAt()).isNotNull();

        Instant originalCreatedAt = product.getCreatedAt();

        product.changePrice(new BigDecimal("850000"));
        entityManager.flush();

        assertThat(product.getCreatedAt()).isEqualTo(originalCreatedAt);
        assertThat(product.getLastModifiedBy()).isEqualTo("test-user");
        assertThat(product.getLastModifiedAt()).isNotNull();
    }
}
~~~

Test giả định entity Product và auditing listener đã được cấu hình như các phần trước. Nếu ứng dụng đã bật auditing trong main configuration, không bật thêm một cấu hình xung đột trong test; hãy import hoặc override AuditorAware theo test context thực tế.

Để kiểm tra actor thay đổi, dùng một AuditorAware test có thể trả về actor khác nhau giữa hai lần flush. Để kiểm tra thời gian chính xác, có thể cấu hình DateTimeProvider dùng Clock cố định thay vì so sánh timestamp dựa vào tốc độ thực thi test.

## 15. Kiểm thử lịch sử Envers

Với Envers, integration test nên:

1. Persist Product lần đầu và flush.
2. Thay đổi giá trong transaction tiếp theo và flush/commit.
3. Lấy danh sách revision bằng AuditReader.
4. Đọc Product ở từng revision.
5. Xác nhận giá cũ và mới đúng như mong đợi.
6. Kiểm tra cả revision xóa nếu use case cần lưu lịch sử deletion.

Ví dụ phần đọc lịch sử trong test:

~~~java
@Test
@Transactional
void storesProductRevisions() {
    AuditReader reader =
        AuditReaderFactory.get(entityManager);

    List<Number> revisions =
        reader.getRevisions(Product.class, productId);

    assertThat(revisions).hasSizeGreaterThanOrEqualTo(2);

    Product firstVersion =
        reader.find(Product.class, productId, revisions.get(0));

    Product latestVersion =
        reader.find(
            Product.class,
            productId,
            revisions.get(revisions.size() - 1)
        );

    assertThat(firstVersion.getPrice())
        .isEqualByComparingTo("800000");

    assertThat(latestVersion.getPrice())
        .isEqualByComparingTo("850000");
}
~~~

Đoạn test giả định Product đã có ít nhất hai revision được commit và Envers đã được cấu hình. Trong test thực tế, cần tạo entity và commit/flush theo transaction boundary phù hợp; revision Envers thường được ghi khi transaction kết thúc thành công. Nếu toàn bộ thay đổi nằm trong một transaction duy nhất, chúng có thể thuộc cùng một revision thay vì tạo nhiều revision riêng.

Không chỉ kiểm tra số revision. Hãy kiểm tra giá trị snapshot, actor metadata, revision type, deletion và rollback behavior theo yêu cầu của ứng dụng.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| createdBy/lastModifiedBy luôn null | Chưa bật auditing hoặc AuditorAware trả empty | Kiểm tra @EnableJpaAuditing, entity listener và actor context |
| Timestamp không được cập nhật | Thiếu @CreatedDate/@LastModifiedDate hoặc listener | Kiểm tra mapping và lifecycle |
| lastModifiedBy bị giả mạo | Lấy actor trực tiếp từ request body | Lấy principal từ security context đáng tin cậy |
| Không có lịch sử giá cũ | Chỉ dùng cột LastModified | Bật Envers hoặc thiết kế audit history |
| Envers không tạo revision | Entity chưa @Audited hoặc thao tác dùng bulk DML | Kiểm tra mapping và dùng entity lifecycle |
| Bulk update không đổi audit metadata | Bulk JPQL bỏ qua entity listener | Cập nhật metadata tường minh hoặc dùng entity update |
| Không tìm thấy bảng _AUD | Envers chưa được thêm/cấu hình schema chưa tạo | Kiểm tra dependency, DDL và migration |
| Lịch sử thiếu actor | Revision metadata mặc định không có user | Tạo custom revision entity/listener |
| Audit table tăng rất nhanh | Ghi quá nhiều revision hoặc lưu field không cần thiết | Xác định phạm vi audit và chính sách retention |
| Nhầm @Version với history | Version chỉ hỗ trợ optimistic locking | Dùng Envers hoặc event/audit store cho lịch sử |
| Audit history chứa dữ liệu nhạy cảm | Đánh dấu @Audited toàn entity mà không rà soát field | Dùng @NotAudited và chính sách bảo vệ dữ liệu |

## 17. Checklist thiết kế audit

- [ ] Xác định chỉ cần người sửa cuối hay cần lịch sử từng phiên bản.
- [ ] Dùng @CreatedBy/@CreatedDate/@LastModifiedBy/@LastModifiedDate cho metadata hiện tại.
- [ ] Bật @EnableJpaAuditing và cung cấp AuditorAware.
- [ ] Lấy actor từ danh tính đã xác thực, không tin dữ liệu client gửi lên.
- [ ] Quy định actor cho batch job, scheduler và message consumer.
- [ ] Dùng @Audited và Hibernate Envers khi cần revision history.
- [ ] Dùng custom revision entity nếu cần actor hoặc correlation metadata cho từng revision.
- [ ] Loại dữ liệu nhạy cảm/không cần thiết khỏi audit history.
- [ ] Hiểu bulk JPQL/native DML không kích hoạt entity auditing/Envers lifecycle thông thường.
- [ ] Dùng @Version cho optimistic locking, không dùng nó thay cho lịch sử.
- [ ] Dùng domain event/outbox nếu cần lưu ý nghĩa nghiệp vụ hoặc phát sự kiện đáng tin cậy.
- [ ] Thiết kế phân quyền đọc lịch sử, retention, migration và dung lượng audit table.
- [ ] Kiểm thử create, update, delete, rollback, bulk DML và actor attribution.

## 18. Kết luận

**Spring Data JPA Auditing** lưu metadata của trạng thái hiện tại: ai tạo, tạo lúc nào, ai sửa gần nhất và sửa lúc nào. Những giá trị modified sẽ được thay thế khi có lần cập nhật tiếp theo; cơ chế này không giữ lại các giá trị cũ.

**Hibernate Envers** lưu lịch sử revision để có thể truy vấn trạng thái entity ở những phiên bản trước. Nếu cần actor cho từng revision, có thể bổ sung custom revision entity và listener. Cả hai cơ chế đều phụ thuộc entity lifecycle và không tự theo dõi bulk JPQL/native DML.

Hãy chọn theo câu hỏi mà hệ thống cần trả lời: metadata hiện tại dùng Spring Data Auditing; lịch sử trạng thái dùng Envers; lịch sử sự kiện nghiệp vụ dùng domain event/outbox; phát hiện cập nhật đồng thời dùng @Version. Có thể kết hợp các cơ chế khi mỗi cơ chế giải quyết một yêu cầu riêng.