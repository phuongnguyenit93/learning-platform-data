# Kiểm tra callback vòng đời entity

Callback vòng đời entity là các phương thức được Jakarta Persistence gọi tại những thời điểm xác định trong quá trình một entity được lưu, cập nhật, xóa hoặc nạp từ cơ sở dữ liệu. Kiểm thử callback giúp xác nhận những quy tắc gắn với vòng đời dữ liệu — chẳng hạn đặt trạng thái mặc định, chuẩn hóa trường dữ liệu hoặc ghi nhận thời điểm tạo và cập nhật — thực sự được thực thi bởi JPA provider khi ứng dụng thao tác với persistence context.

Trong Spring, các bài kiểm thử này thường dùng Spring Boot Test với `@DataJpaTest` và `TestEntityManager`, hoặc dùng `EntityManager` trong một test context JPA thông thường. Điều quan trọng là phải để JPA provider thực hiện thao tác và đi qua ranh giới `flush`, `clear`, `find` phù hợp. Gọi trực tiếp phương thức callback không kiểm tra được hành vi vòng đời của entity.

## 1. Các callback vòng đời của JPA

Jakarta Persistence định nghĩa bảy loại callback chính:

| Callback | Thời điểm chạy | Trường hợp thường kiểm tra |
| --- | --- | --- |
| `@PrePersist` | Trước khi entity mới được insert | Đặt giá trị mặc định, chuẩn hóa dữ liệu trước khi insert |
| `@PostPersist` | Sau khi lệnh insert được thực hiện | Xác nhận hành vi sau insert hoặc giá trị đã được tạo |
| `@PreUpdate` | Trước khi lệnh update được thực hiện | Cập nhật trường dẫn xuất trước khi ghi dữ liệu |
| `@PostUpdate` | Sau khi lệnh update được thực hiện | Xác nhận hành vi sau update |
| `@PreRemove` | Trước khi entity bị xóa | Kiểm tra quy tắc trước khi xóa |
| `@PostRemove` | Sau khi lệnh delete được thực hiện | Xác nhận hành vi sau delete |
| `@PostLoad` | Sau khi trạng thái entity được nạp | Khởi tạo trạng thái tạm hoặc kiểm tra dữ liệu sau khi nạp |

Các callback có thể được khai báo ngay trong entity hoặc trong một lớp listener được đăng ký bằng `@EntityListeners`. Với callback đặt trong entity, phương thức có kiểu trả về `void`, không nhận tham số và không phải phương thức static. Ví dụ:

```java
@Entity
public class Account {
    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @PrePersist
    private void initializeStatus() {
        if (status == null) {
            status = "NEW";
        }
    }
}
```

Với entity listener, phương thức callback nhận entity làm tham số:

```java
public class AccountListener {
    @PrePersist
    public void beforePersist(Account account) {
        if (account.getStatus() == null) {
            account.setStatus("NEW");
        }
    }
}
```

```java
@Entity
@EntityListeners(AccountListener.class)
public class Account {
    // Các trường và getter/setter của entity
}
```

`@PreUpdate` không có nghĩa là chạy mỗi khi gọi setter. Callback này được gọi khi JPA chuẩn bị ghi một thay đổi của entity trong quá trình flush. Nếu entity không thay đổi, provider thường không phát sinh câu lệnh update và callback `@PreUpdate` cũng không chạy. Tương tự, `@PostUpdate` gắn với việc update thực sự được thực hiện.

## 2. Hiểu đúng ranh giới thực thi

Các thao tác `persist`, thay đổi một entity đang được quản lý và `remove` thường chỉ thay đổi trạng thái trong persistence context hoặc lên lịch thao tác SQL. JPA provider đồng bộ những thay đổi đó với cơ sở dữ liệu khi flush. Vì vậy, test cần chủ động flush ở điểm muốn kiểm tra.

```mermaid
flowchart TD
    A[Entity mới] --> B[@PrePersist]
    B --> C[INSERT khi flush]
    C --> D[@PostPersist]
    E[Entity đang được quản lý và bị thay đổi] --> F[@PreUpdate]
    F --> G[UPDATE khi flush]
    G --> H[@PostUpdate]
    I[Entity được yêu cầu xóa] --> J[@PreRemove]
    J --> K[DELETE khi flush]
    K --> L[@PostRemove]
    M[SELECT và nạp entity] --> N[@PostLoad]
```

Một số điểm cần phân biệt khi viết assertion:

- `flush()` yêu cầu provider đồng bộ persistence context với cơ sở dữ liệu trong transaction hiện tại. Flush không đồng nghĩa với commit.
- `clear()` xóa các entity đang được quản lý khỏi persistence context. Sau đó `find()` phải nạp lại entity, giúp test kiểm tra dữ liệu đã lưu thay vì chỉ đọc lại object cũ trong bộ nhớ.
- Callback sau insert, update hoặc delete có thể đã chạy dù transaction sau đó bị rollback. Vì vậy, `@PostPersist` không chứng minh dữ liệu đã được commit bền vững.
- `@PostLoad` chỉ được kiểm tra có ý nghĩa khi entity thực sự được nạp lại. Gọi `find()` với cùng một entity vẫn đang được quản lý có thể trả về chính object trong persistence context mà không tạo lần nạp mới.
- Với chiến lược sinh khóa chính khác nhau, thời điểm ID được gán có thể khác nhau. Không nên viết `@PrePersist` với giả định rằng ID tự sinh luôn có sẵn.

## 3. Chuẩn bị môi trường kiểm thử trong Spring

`@DataJpaTest` là lựa chọn phù hợp khi muốn kiểm tra entity, mapping, repository và callback JPA trong Spring Boot. Annotation này tạo test slice cho tầng JPA, cấu hình các thành phần persistence cần thiết và thường chạy mỗi test trong một transaction được rollback sau khi test kết thúc.

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.beans.factory.annotation.Autowired;

@DataJpaTest
class AccountLifecycleTest {
    @Autowired
    private TestEntityManager entityManager;
}
```

`TestEntityManager` cung cấp các thao tác tiện dụng như `persistAndFlush`, `flush`, `clear`, `remove` và `find`. Nếu không dùng Spring Boot, có thể cấu hình test context bằng Spring Test, inject `EntityManager` thông qua `@PersistenceContext`, rồi thực hiện các thao tác JPA tương tự.

Một test slice có thể dùng cơ sở dữ liệu nhúng như H2 nếu dependency tương ứng có trong dự án. Cách này nhanh và hữu ích cho kiểm thử mapping, nhưng nếu ứng dụng phụ thuộc vào cú pháp SQL, kiểu dữ liệu, constraint hoặc hành vi riêng của PostgreSQL, MySQL hay một hệ quản trị khác, nên chạy thêm integration test với đúng hệ quản trị mục tiêu, chẳng hạn thông qua Testcontainers.

Các ví dụ dưới đây dùng `jakarta.persistence`, phù hợp với Spring Boot 3 trở lên. Dự án Spring Boot 2 hoặc dự án JPA cũ có thể cần đổi import sang `javax.persistence` theo phiên bản đang dùng.

## 4. Ví dụ entity có callback

Ví dụ `Customer` đặt trạng thái mặc định và chuẩn hóa tên trước khi insert, chuẩn hóa lại tên trước khi update, đồng thời ghi nhận các callback đã chạy bằng trường tạm để minh họa cách kiểm tra.

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.PostRemove;
import jakarta.persistence.PostUpdate;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreRemove;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import java.util.Locale;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String normalizedName;

    @Column(nullable = false)
    private String status;

    @Transient
    private boolean loaded;

    @Transient
    private boolean postPersistCalled;

    @Transient
    private boolean postUpdateCalled;

    @Transient
    private boolean preRemoveCalled;

    @Transient
    private boolean postRemoveCalled;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    @PrePersist
    private void beforePersist() {
        if (status == null) {
            status = "NEW";
        }
        normalizedName = normalize(name);
    }

    @PostPersist
    private void afterPersist() {
        postPersistCalled = true;
    }

    @PreUpdate
    private void beforeUpdate() {
        normalizedName = normalize(name);
    }

    @PostUpdate
    private void afterUpdate() {
        postUpdateCalled = true;
    }

    @PreRemove
    private void beforeRemove() {
        preRemoveCalled = true;
    }

    @PostRemove
    private void afterRemove() {
        postRemoveCalled = true;
    }

    @PostLoad
    private void afterLoad() {
        loaded = true;
    }

    private static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getNormalizedName() {
        return normalizedName;
    }

    public String getStatus() {
        return status;
    }

    public boolean isLoaded() {
        return loaded;
    }

    public boolean isPostPersistCalled() {
        return postPersistCalled;
    }

    public boolean isPostUpdateCalled() {
        return postUpdateCalled;
    }

    public boolean isPreRemoveCalled() {
        return preRemoveCalled;
    }

    public boolean isPostRemoveCalled() {
        return postRemoveCalled;
    }
}
```

Các cờ `@Transient` chỉ phục vụ minh họa trong test và không được lưu vào bảng. Trong ứng dụng thực tế, nên ưu tiên kiểm tra tác động nghiệp vụ có thể quan sát được, ví dụ giá trị mặc định hoặc trường đã chuẩn hóa. Không nên thêm các cờ kiểm thử vào entity sản xuất chỉ để đếm số lần callback chạy.

## 5. Kiểm tra callback khi insert và load

Test đầu tiên xác nhận `@PrePersist` đã đặt giá trị trước khi insert và `@PostPersist` đã chạy sau insert. Sau đó test xóa persistence context và nạp lại entity để xác nhận `@PostLoad`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerLifecycleTest {
    @Autowired
    private TestEntityManager entityManager;

    @Test
    void appliesPersistAndLoadCallbacks() {
        Customer customer = new Customer("  An Nguyen  ");

        entityManager.persistAndFlush(customer);

        Long id = customer.getId();
        assertThat(customer.getStatus()).isEqualTo("NEW");
        assertThat(customer.getNormalizedName()).isEqualTo("an nguyen");
        assertThat(customer.isPostPersistCalled()).isTrue();

        entityManager.clear();

        Customer reloaded = entityManager.find(Customer.class, id);

        assertThat(reloaded).isNotNull();
        assertThat(reloaded.getNormalizedName()).isEqualTo("an nguyen");
        assertThat(reloaded.isLoaded()).isTrue();
    }
}
```

`persistAndFlush` làm rõ thời điểm insert được thực hiện, vì thế test có thể kiểm tra các callback gắn với insert. `clear()` rất quan trọng trong phần kiểm tra load: nếu bỏ qua bước này, `find()` có thể trả về instance đã có sẵn trong persistence context và test không chứng minh được `@PostLoad` đã chạy.

## 6. Kiểm tra callback khi update

Để kiểm tra `@PreUpdate`, trước hết phải lưu entity, sau đó thay đổi một trường khiến entity trở thành dirty và flush. Test cũng nên đọc lại dữ liệu sau `clear()` để xác nhận giá trị đã được ghi xuống cơ sở dữ liệu.

```java
@Test
void normalizesNameBeforeUpdate() {
    Customer customer = new Customer("Lan");
    entityManager.persistAndFlush(customer);

    Long id = customer.getId();
    customer.setName("  BINH  ");

    entityManager.flush();

    assertThat(customer.getNormalizedName()).isEqualTo("binh");
    assertThat(customer.isPostUpdateCalled()).isTrue();

    entityManager.clear();

    Customer reloaded = entityManager.find(Customer.class, id);
    assertThat(reloaded.getName()).isEqualTo("  BINH  ");
    assertThat(reloaded.getNormalizedName()).isEqualTo("binh");
}
```

Nếu test chỉ gọi `setName()` rồi kiểm tra ngay, nó mới xác nhận setter hoạt động; nó chưa xác nhận JPA đã gọi `@PreUpdate`. Nếu không flush, callback có thể chưa chạy. Nếu không clear và nạp lại, test có thể chỉ đọc giá trị trên object đang được quản lý. Cả hai bước đều giúp test kiểm tra đúng hành vi của tầng dữ liệu.

## 7. Kiểm tra callback khi remove

Với thao tác xóa, gọi `remove()` và flush để provider thực hiện delete. Có thể kiểm tra callback trước và sau delete trên instance đã bị xóa, sau đó xác nhận bản ghi không còn khi nạp lại.

```java
@Test
void runsRemoveCallbacksAndDeletesTheRow() {
    Customer customer = new Customer("Mai");
    entityManager.persistAndFlush(customer);
    Long id = customer.getId();

    entityManager.remove(customer);
    entityManager.flush();

    assertThat(customer.isPreRemoveCalled()).isTrue();
    assertThat(customer.isPostRemoveCalled()).isTrue();

    entityManager.clear();
    assertThat(entityManager.find(Customer.class, id)).isNull();
}
```

Kiểm tra cả callback lẫn kết quả truy vấn giúp phân biệt hai vấn đề: callback có được gọi hay không, và thao tác xóa có thực sự được đồng bộ xuống cơ sở dữ liệu hay không. Nếu ứng dụng dùng cascade remove, hãy tạo dữ liệu quan hệ trong test để kiểm tra đúng đường đi cascade mà ứng dụng sử dụng.

## 8. Kiểm tra entity listener và Spring Data auditing

Khi logic callback được đặt trong lớp listener, test vẫn nên kích hoạt thao tác thông qua `EntityManager` hoặc repository. Điều đó xác nhận listener đã được gắn với entity và JPA provider đã gọi nó đúng thời điểm. Nếu listener dùng một dependency do Spring quản lý, cần kiểm tra cấu hình tích hợp JPA/Spring của dự án; khả năng inject phụ thuộc vào cách cấu hình provider và phiên bản nền tảng.

Spring Data JPA auditing là một trường hợp thường gặp của callback listener. `AuditingEntityListener` xử lý các annotation như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy`. Cấu hình auditing thường cần `@EnableJpaAuditing` và đăng ký listener trên entity:

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class OrderRecord {
    @Id
    @GeneratedValue
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
```

Trong test slice `@DataJpaTest`, hãy bảo đảm cấu hình bật auditing được đưa vào test context, chẳng hạn thông qua một cấu hình test được import. Sau khi persist và flush, kiểm tra `createdAt`; sau khi sửa entity và flush, kiểm tra `updatedAt`. Với kiểm thử thời gian, nên cấu hình nguồn thời gian có thể kiểm soát nếu dự án hỗ trợ `DateTimeProvider` hoặc `Clock`. Tránh dùng `Thread.sleep()` để chờ timestamp thay đổi vì cách đó làm test chậm và dễ chập chờn.

## 9. Các lỗi kiểm thử thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `@PreUpdate` không chạy | Entity chưa thay đổi, đang detached hoặc chưa flush | Sửa một trường persistent trên entity đang managed rồi gọi `flush()` |
| `@PostLoad` không chạy trong lần `find()` | Entity đã có trong persistence context | Gọi `clear()` trước khi nạp lại |
| Giá trị callback đúng trong object nhưng chưa chắc đã lưu | Chỉ kiểm tra instance đang managed | Flush, clear rồi truy vấn lại |
| `@PostPersist` đã chạy nhưng bản ghi không còn sau test | Transaction test bị rollback | Phân biệt callback sau SQL với commit transaction |
| Test xóa vẫn tìm thấy bản ghi | Chưa flush hoặc đang đọc trạng thái cũ trong persistence context | Flush, clear rồi `find()` lại |
| Test thời gian lúc qua lúc trượt | Dùng thời gian hệ thống và so sánh quá chặt | Dùng clock có thể kiểm soát hoặc assertion có khoảng dung sai hợp lý |
| Test qua với H2 nhưng lỗi trên production | Khác biệt dialect, kiểu dữ liệu hoặc hành vi hệ quản trị | Chạy integration test với cùng loại database production |

Một nguyên nhân khác là đặt logic quá nhiều trong callback. Callback JPA được gọi trong quá trình quản lý persistence context, vì vậy nên giữ chúng ngắn và tập trung vào trạng thái của chính entity. Không nên thực hiện truy vấn qua `EntityManager`, gọi dịch vụ mạng, gửi email hoặc thay đổi các entity khác từ callback. Các hành động phụ thuộc vào commit nên được xử lý bằng cơ chế phù hợp ở tầng ứng dụng, ví dụ sự kiện giao dịch sau commit hoặc transactional outbox.

Nếu callback ném exception, thao tác persistence có thể thất bại và transaction có thể bị đánh dấu rollback. Khi đây là hành vi nghiệp vụ cần bảo đảm, hãy viết test kích hoạt đúng thao tác JPA và xác nhận exception tại ranh giới `flush()`; không gọi trực tiếp phương thức callback để mô phỏng lỗi.

## 10. Nguyên tắc viết test đáng tin cậy

1. Dùng entity thật và JPA provider thật trong test context để callback được gọi theo lifecycle thực tế.
2. Xác định rõ thao tác nào đang được kiểm tra: insert, update, remove hay load.
3. Dùng `persistAndFlush()` hoặc `flush()` để kích hoạt đồng bộ khi cần kiểm tra callback ghi dữ liệu.
4. Dùng `clear()` rồi `find()` để xác nhận trạng thái đã được lưu và để kích hoạt một lần load mới.
5. Kiểm tra kết quả nghiệp vụ có thể quan sát được; chỉ kiểm tra cờ hoặc số lần gọi khi đó thực sự là mục tiêu của test.
6. Nhớ rằng transaction của `@DataJpaTest` thường rollback sau test. Callback chạy không có nghĩa transaction đã commit.
7. Dùng loại database gần với môi trường triển khai khi logic phụ thuộc vào đặc tính riêng của hệ quản trị.

Một test callback tốt chứng minh được chuỗi hành vi từ thao tác persistence, qua callback, đến trạng thái entity hoặc dữ liệu được đọc lại. Khi test kiểm soát rõ flush và persistence context, lỗi trong callback sẽ được phát hiện tại đúng tầng dữ liệu và dễ xác định nguyên nhân hơn.
