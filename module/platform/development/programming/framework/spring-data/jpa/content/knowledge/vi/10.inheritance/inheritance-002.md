# Chia sẻ thuộc tính bằng @MappedSuperclass

Trong một ứng dụng Spring Data JPA, nhiều Entity thường có cùng các thuộc tính kỹ thuật như khóa chính, phiên bản để kiểm soát cập nhật đồng thời, thời điểm tạo và thời điểm cập nhật. Nếu khai báo lặp lại các trường và annotation này trong từng Entity, mã nguồn dễ bị trùng lặp và không nhất quán.

JPA cung cấp @MappedSuperclass để đặt mapping dùng chung vào một lớp cha. Các Entity con kế thừa các thuộc tính và mapping đó, nhưng lớp cha không trở thành một Entity độc lập và không có bảng riêng. Đây là cách tái sử dụng mapping bằng kế thừa Java, phù hợp khi các lớp con có cùng cấu trúc persistence nhưng không cần truy vấn đa hình qua lớp cha.

## 1. Bài toán lặp lại thuộc tính giữa các Entity

Giả sử hệ thống có Customer, Product và Invoice. Cả ba đều cần khóa chính, thời điểm tạo và version.

Nếu mỗi Entity tự khai báo các trường này, mã nguồn sẽ lặp lại:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private Instant createdAt;
}
~~~

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private Instant createdAt;
}
~~~

Việc lặp lại không sai về mặt JPA, nhưng khi cần thay đổi quy ước, ví dụ đổi tên cột, thêm callback hoặc thêm trường audit, phải sửa từng Entity. Một Entity có thể bị bỏ sót hoặc dùng mapping khác với phần còn lại.

Có thể đưa phần mapping chung vào một lớp cha bằng @MappedSuperclass.

## 2. @MappedSuperclass hoạt động như thế nào?

@MappedSuperclass đánh dấu một lớp Java mà mapping của nó được kế thừa bởi các Entity con. JPA đọc các annotation trên lớp cha và áp dụng chúng vào mapping của từng Entity con.

Ví dụ:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    private Instant updatedAt;

    protected BaseEntity() {
    }

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Entity Customer:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer extends BaseEntity {

    @Column(nullable = false, length = 150)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Entity Product:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product extends BaseEntity {

    @Column(nullable = false, length = 120)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Mapping id, version, createdAt và updatedAt được kế thừa vào cả hai Entity. Bảng customers chứa các cột chung cùng full_name; bảng products chứa các cột chung cùng name. JPA không tạo bảng base_entity.

Mô hình khái niệm:

~~~text
              BaseEntity
           @MappedSuperclass
       id, version, createdAt,
              updatedAt
                  |
           +------+------+
           |             |
        Customer       Product
         @Entity        @Entity
           |             |
       customers      products
       id              id
       version         version
       created_at      created_at
       updated_at      updated_at
       full_name       name
~~~

Mỗi Entity con vẫn là một Entity độc lập, có bảng và Repository riêng.

## 3. @MappedSuperclass không phải Entity

Đây là khác biệt quan trọng nhất giữa mapped superclass và entity inheritance.

Một lớp được đánh dấu @MappedSuperclass:

- Không được quản lý như một Entity độc lập trong persistence context.
- Không có bảng database riêng chỉ vì được đánh dấu @MappedSuperclass.
- Không thể dùng trực tiếp làm Entity type của JpaRepository.
- Không thể là kiểu đích của quan hệ Entity như @ManyToOne hoặc @OneToMany.
- Không thể được truy vấn trực tiếp bằng JPQL như một Entity.

Ví dụ không phù hợp:

~~~java
public interface BaseEntityRepository
        extends JpaRepository<BaseEntity, Long> {
}
~~~

BaseEntity không phải Entity. Hãy khai báo Repository cho các lớp con:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Nếu nghiệp vụ cần truy vấn tất cả loại đối tượng qua một kiểu cha, hoặc cần quan hệ trỏ đến kiểu cha, hãy cân nhắc entity inheritance: lớp cha được đánh dấu @Entity và sử dụng chiến lược @Inheritance thích hợp.

## 4. Kế thừa identifier và version

Một mapped superclass có thể khai báo identifier bằng @Id hoặc @EmbeddedId. Entity con kế thừa mapping identifier đó.

Ví dụ BaseEntity có:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Customer và Product đều kế thừa trường id kiểu Long. Repository của mỗi Entity dùng Long làm ID type:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Dù thuộc tính id được khai báo trong lớp cha, nó vẫn là khóa chính của từng bảng Entity con. Giá trị ID của Customer và Product được quản lý trong các bảng riêng; cùng một số ID ở hai bảng không có nghĩa đó là cùng một Entity.

@Version cũng có thể đặt trong mapped superclass:

~~~java
@Version
private Long version;
~~~

Hibernate dùng version để thực hiện optimistic locking. Khi một transaction cập nhật Entity, provider kiểm tra version hiện tại. Nếu một transaction khác đã cập nhật bản ghi và tăng version, thao tác ghi cũ có thể thất bại với lỗi optimistic locking.

Không khai báo thêm identifier thứ hai trong lớp con nếu không có mapping đặc biệt được JPA hỗ trợ. Mỗi Entity phải có một identifier mapping rõ ràng.

## 5. Trường được kế thừa và access strategy

JPA hỗ trợ hai cách truy cập thuộc tính:

- **Field access:** annotation mapping được đặt trên field.
- **Property access:** annotation mapping được đặt trên getter.

JPA thường xác định access type dựa trên vị trí đặt annotation định danh trong hierarchy. Nếu lớp cha đặt @Id trên field, nên giữ field access nhất quán ở các lớp con.

Ví dụ:

~~~java
import jakarta.persistence.*;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class BaseEntity {

    @Id
    private Long id;

    protected BaseEntity() {
    }
}
~~~

Không nên đặt một số annotation trên field và một số annotation trên getter một cách tùy tiện. Nếu cần trộn hai cách, hãy chỉ định @Access rõ ràng ở cấp lớp hoặc thuộc tính theo quy tắc JPA.

Các thuộc tính Java không được lưu có thể đánh dấu @Transient. Những field static hoặc transient theo quy tắc persistence cũng không được ánh xạ như thuộc tính persistent thông thường.

## 6. Ghi đè tên cột bằng @AttributeOverride

Mapped superclass có thể cung cấp tên cột mặc định. Mỗi Entity con có thể ghi đè mapping của thuộc tính cơ bản bằng @AttributeOverride.

Lớp cha:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "created_at")
    private Instant createdAt;
}
~~~

Customer đổi tên cột:

~~~java
@Entity
@Table(name = "customers")
@AttributeOverrides({
    @AttributeOverride(
        name = "id",
        column = @Column(name = "customer_id")
    ),
    @AttributeOverride(
        name = "createdAt",
        column = @Column(name = "registered_at")
    )
})
public class Customer extends BaseEntity {

    private String fullName;
}
~~~

Product có thể giữ mapping mặc định hoặc ghi đè riêng:

~~~java
@Entity
@Table(name = "products")
@AttributeOverride(
    name = "createdAt",
    column = @Column(name = "created_on")
)
public class Product extends BaseEntity {

    private String name;
}
~~~

Trong @AttributeOverride:

- name là tên thuộc tính Java được kế thừa.
- column là mapping cột SQL mới.
- Không dùng tên bảng hoặc tên cột thay cho tên thuộc tính Java.
- @AttributeOverrides cho phép khai báo nhiều override.

Có thể dùng override cho thuộc tính cơ bản được kế thừa và các thuộc tính nhúng theo đường dẫn phù hợp. Nếu các Entity con không cần khác biệt, giữ mapping ở lớp cha để tránh cấu hình dư thừa.

## 7. Ghi đè quan hệ bằng @AssociationOverride

Mapped superclass cũng có thể khai báo quan hệ JPA. Nếu các Entity con cần tên join column hoặc join table khác nhau, dùng @AssociationOverride.

Lớp cha:

~~~java
import jakarta.persistence.*;

@MappedSuperclass
public abstract class OwnedEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id")
    private User owner;

    protected OwnedEntity() {
    }

    public User getOwner() {
        return owner;
    }
}
~~~

Customer ghi đè join column:

~~~java
@Entity
@Table(name = "customers")
@AssociationOverride(
    name = "owner",
    joinColumns = @JoinColumn(name = "customer_owner_id")
)
public class Customer extends OwnedEntity {

    private String fullName;
}
~~~

@AssociationOverride tham chiếu tên thuộc tính quan hệ được kế thừa. Nó có thể thay đổi join columns hoặc join table tùy kiểu quan hệ. Đối tượng User trong ví dụ phải là Entity thực sự được JPA quản lý.

Mapped superclass có thể chứa quan hệ đến Entity, nhưng bản thân mapped superclass không thể là target entity của một quan hệ.

## 8. Lifecycle callback trong mapped superclass

Các callback JPA có thể được khai báo trong mapped superclass và áp dụng cho các Entity con.

~~~java
@MappedSuperclass
public abstract class TimestampedEntity {

    private Instant createdAt;
    private Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
~~~

Khi một Entity con được persist, callback @PrePersist có thể được gọi. Khi Entity được cập nhật thông qua cơ chế persistence thông thường, @PreUpdate được gọi trước khi cập nhật.

Lưu ý:

- Bulk JPQL update và native SQL không thực hiện callback cho từng Entity như dirty checking thông thường.
- Callback nên ngắn, dễ dự đoán và không thực hiện công việc I/O kéo dài.
- Nếu nhiều lớp trong hierarchy khai báo callback, hãy hiểu thứ tự callback của JPA và tránh xử lý trùng lặp.
- Không coi callback là cơ chế audit đầy đủ nếu ứng dụng còn ghi dữ liệu qua batch job hoặc SQL trực tiếp.

## 9. Kết hợp với Spring Data JPA auditing

Spring Data JPA cung cấp auditing để tự động điền người tạo và thời điểm tạo/cập nhật. Các trường audit có thể đặt trong mapped superclass.

~~~java
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
public abstract class AuditableEntity {

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;
}
~~~

Bật auditing:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

Nếu muốn ghi người dùng hiện tại, cần cấu hình AuditorAware<T> để cung cấp actor. Ví dụ ứng dụng web có thể lấy username đã xác thực từ Spring Security context.

Các annotation @CreatedDate, @LastModifiedDate, @CreatedBy và @LastModifiedBy thuộc Spring Data, không phải Jakarta Persistence. Chúng cần listener và cấu hình auditing tương ứng.

## 10. So sánh @MappedSuperclass, @Embeddable và Entity inheritance

Ba cách này giải quyết các bài toán khác nhau:

| Cơ chế | Dùng khi | Có bảng riêng? | Truy vấn lớp đó như Entity? |
|---|---|---|---|
| @MappedSuperclass | Chia sẻ mapping qua kế thừa | Không | Không |
| @Embeddable + @Embedded | Gom nhóm thuộc tính thành value object | Không; các cột nằm trong bảng Entity chứa nó | Không |
| Entity inheritance | Mô hình hóa hierarchy Entity có tính đa hình | Tùy @Inheritance | Có |

Ví dụ @Embeddable phù hợp với Address hoặc Money:

~~~java
@Embeddable
public class Address {
    private String street;
    private String city;
}
~~~

Entity dùng composition:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @Embedded
    private Address address;
}
~~~

Nếu lớp cha cần được truy vấn như Entity hoặc được tham chiếu bởi quan hệ JPA, hãy xem xét entity inheritance với @Entity và @Inheritance. @MappedSuperclass không cung cấp khả năng đa hình đó.

## 11. Khi nào nên dùng @MappedSuperclass?

Phù hợp khi:

- Nhiều Entity có chung id, version, createdAt, updatedAt hoặc trường audit.
- Mỗi Entity con có bảng riêng.
- Không cần truy vấn lớp cha như một Entity.
- Mapping chung có cùng ý nghĩa và có thể dùng chung quy ước.

Không phù hợp khi:

- Lớp cha cần có Repository riêng.
- Cần quan hệ @ManyToOne trỏ đến lớp cha.
- Cần JPQL truy vấn tất cả lớp con thông qua kiểu cha.
- Các lớp con có cấu trúc dữ liệu khác nhau đến mức lớp cha chỉ còn một vài thuộc tính không liên quan.
- Muốn gom nhóm giá trị theo composition thay vì kế thừa.

## 12. Những lỗi thường gặp

**Tạo Repository cho mapped superclass**

Mapped superclass không phải Entity. Hãy tạo Repository cho từng Entity con.

**Kỳ vọng có bảng cha**

JPA không tạo bảng riêng cho lớp @MappedSuperclass. Các thuộc tính của nó được ánh xạ vào bảng từng Entity con.

**Dùng @Inheritance với mapped superclass để truy vấn đa hình**

@Inheritance dành cho entity inheritance. Nếu cần truy vấn kiểu cha, hãy chuyển sang một Entity hierarchy thực sự.

**Ghi đè sai tên thuộc tính**

name trong @AttributeOverride và @AssociationOverride là tên thuộc tính Java được kế thừa, không phải tên cột SQL.

**Khai báo identifier trùng lặp**

Nếu lớp cha đã khai báo @Id, lớp con không nên khai báo thêm một @Id độc lập cho cùng Entity.

**Trộn field access và property access**

Giữ access strategy nhất quán hoặc dùng @Access tường minh để tránh provider đọc/ghi khác với dự kiến.

**Đưa logic nghiệp vụ quá nhiều vào lớp cha**

Mapped superclass nên chứa các thuộc tính và hành vi thật sự dùng chung. Logic riêng của Customer không nên đặt trong BaseEntity chỉ vì muốn tái sử dụng.

**Callback không chạy với bulk update**

JPQL bulk update và native SQL bỏ qua lifecycle của từng Entity. Nếu dữ liệu được cập nhật theo cách đó, hãy tự xử lý audit/version hoặc dùng quy trình phù hợp.

## 13. Kiểm tra mapping sau khi triển khai

Một integration test nên xác nhận:

1. Entity con được JPA nhận diện và có thể persist.
2. Các cột kế thừa xuất hiện trong bảng Entity con.
3. ID và version được ánh xạ đúng.
4. Callback hoặc auditing cập nhật các trường chung theo mong đợi.
5. @AttributeOverride tạo tên cột như dự kiến.
6. Quan hệ kế thừa có join column đúng.
7. Repository của từng Entity con hoạt động với đúng ID type.
8. JPQL không cố truy vấn mapped superclass như một Entity.

Ngoài test, hãy xem DDL hoặc schema migration và SQL thực tế. Việc ứng dụng khởi động thành công không đảm bảo schema đang chạy khớp với thiết kế mong muốn.

## 14. Kết luận

@MappedSuperclass là cách tái sử dụng mapping JPA qua kế thừa Java. Nó phù hợp để chia sẻ identifier, version, thuộc tính cơ bản, quan hệ và lifecycle callback giữa nhiều Entity có bảng riêng. Lớp cha không có bảng, không phải Entity độc lập và không hỗ trợ truy vấn đa hình. Dùng @AttributeOverride và @AssociationOverride khi Entity con cần tùy chỉnh mapping. Nếu cần value object, chọn @Embeddable; nếu cần lớp cha có thể truy vấn như Entity, chọn entity inheritance.
