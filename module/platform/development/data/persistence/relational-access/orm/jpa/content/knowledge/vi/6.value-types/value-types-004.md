# Ghi đè ánh xạ quan hệ trong đối tượng nhúng với @AssociationOverride

## 1. Vì sao cần ghi đè ánh xạ quan hệ?

Trong Jakarta Persistence (JPA), **kiểu giá trị nhúng** (*embeddable value type*) cho phép gom một nhóm thuộc tính có ý nghĩa chung thành một lớp Java dùng lại được. Thay vì đưa tất cả thuộc tính vào entity, ta khai báo lớp **@Embeddable** và nhúng nó vào entity bằng **@Embedded**.

Một đối tượng nhúng có thể chứa không chỉ các trường cơ bản như String, LocalDate hay BigDecimal, mà còn cả **quan hệ đến entity khác**, chẳng hạn **@ManyToOne** đến nhân viên phụ trách hoặc **@OneToOne** đến đối tượng hồ sơ. Khi nhúng đối tượng này vào những vị trí khác nhau, mỗi vị trí có thể cần **tên cột khóa ngoại** hoặc **bảng liên kết** khác nhau.

Ví dụ, cùng một kiểu giá trị **Assignment** mô tả “người được giao và ghi chú”, nhưng entity **WorkItem** cần lưu hai vai trò:

- Người phụ trách chính trong cột **primary_assignee_id**.
- Người phụ trách dự phòng trong cột **backup_assignee_id**.

Nếu cả hai đều dùng nguyên ánh xạ mặc định **assignee_id** của kiểu nhúng, chúng có thể cùng tranh chấp một cột. Nếu chỉ đổi tên cột ghi chú mà không đổi khóa ngoại, quan hệ vẫn ánh xạ sai. JPA cung cấp **@AssociationOverride** và **@AssociationOverrides** để xử lý tình huống này.

> **Ý tưởng chính:** giữ nguyên mô hình Java của kiểu nhúng, nhưng chỉ định lại *vị trí lưu quan hệ* ở từng nơi sử dụng. Ghi đè ánh xạ quan hệ không tạo ra một entity mới cho đối tượng nhúng và không thay đổi bản chất kiểu quan hệ.

## 2. Ôn lại @Embeddable, @Embedded và quan hệ bên trong kiểu giá trị

Xét một kiểu giá trị mô tả người được giao công việc:

~~~java
package com.example.work;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Embeddable
public class Assignment {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "assignee_id", nullable = false)
    private StaffMember assignee;

    @Column(name = "assignment_note", length = 200)
    private String note;

    protected Assignment() {
        // JPA cần constructor không tham số phù hợp.
    }

    public Assignment(StaffMember assignee, String note) {
        this.assignee = assignee;
        this.note = note;
    }

    public StaffMember getAssignee() {
        return assignee;
    }

    public String getNote() {
        return note;
    }
}
~~~

Trong ví dụ:

1. **Assignment** là **@Embeddable**, không phải **@Entity**. Nó không khai báo khóa chính riêng và không mặc nhiên có bảng riêng.
2. Trường **assignee** là quan hệ **@ManyToOne** đến entity **StaffMember**; cơ chế ánh xạ dự kiến cột khóa ngoại **assignee_id** ở bảng của entity chứa Assignment.
3. Trường **note** là thuộc tính cơ bản và mặc định được lưu trong cột **assignment_note** của bảng chứa.
4. Đối tượng nhúng là một phần trạng thái của entity sở hữu. Khi entity đó được quản lý, các thuộc tính của đối tượng nhúng tham gia persistence context và quá trình đồng bộ theo mapping.

Một entity đích tối giản:

~~~java
package com.example.work;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "staff_members")
public class StaffMember {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    protected StaffMember() {}

    public StaffMember(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Nếu một entity chỉ nhúng **Assignment** một lần, mapping mặc định có thể đã đủ:

~~~java
@Entity
public class WorkItem {
    @Id
    private Long id;

    @Embedded
    private Assignment assignment;
}
~~~

Nhưng khi cùng kiểu nhúng xuất hiện ở nhiều field, tên cột khóa ngoại hoặc cột cơ bản thường cần được phân biệt. Đó là nơi dùng annotation ghi đè.

### 2.1. Đối tượng nhúng không có danh tính độc lập

Khác với **StaffMember**, một **Assignment** không có một định danh JPA riêng để quản lý như entity. Nhiều WorkItem có thể trỏ đến cùng một StaffMember; việc mỗi WorkItem có một Assignment chỉ mô tả vai trò của StaffMember trong công việc đó.

~~~text
StaffMember (entity, có ID)
        ^
        | nhiều WorkItem có thể tham chiếu
        |
WorkItem (entity, có ID)
  |
  +-- primaryAssignment (Assignment: giá trị nhúng)
  |       +-- assignee ----> StaffMember
  |       +-- note
  |
  +-- backupAssignment (Assignment: giá trị nhúng)
          +-- assignee ----> StaffMember
          +-- note
~~~

Các đối tượng nhúng **không** làm phát sinh hai hàng Assignment riêng biệt. Các cột của chúng được ánh xạ vào nơi lưu của WorkItem theo quy tắc JPA.

## 3. Các annotation dùng để ghi đè ánh xạ

### 3.1. @AssociationOverride

**@AssociationOverride** cho phép ghi đè **ánh xạ quan hệ** đã được định nghĩa trước, thường là quan hệ trong **@Embeddable** hoặc quan hệ được kế thừa từ **@MappedSuperclass**.

Một khai báo điển hình:

~~~java
@Embedded
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(
        name = "primary_assignee_id",
        nullable = false
    )
)
private Assignment primaryAssignment;
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| **name** | Tên thuộc tính quan hệ cần ghi đè trong kiểu nhúng, tính từ vị trí áp dụng annotation |
| **joinColumns** | Một hoặc nhiều **@JoinColumn** mô tả cột khóa ngoại của quan hệ |
| **joinTable** | **@JoinTable** mô tả bảng liên kết khi quan hệ được lưu qua bảng trung gian |

**joinColumns** và **joinTable** là hai cách ánh xạ khác nhau; chọn cách phù hợp với quan hệ và schema, không khai báo đồng thời hai cách cho cùng một override.

Ở ví dụ trên, **name = "assignee"** nói đến **tên thuộc tính Java bên trong Assignment**, còn **name = "primary_assignee_id"** bên trong @JoinColumn là **tên cột SQL** của bảng chứa WorkItem. Phân biệt hai loại tên này là rất quan trọng.

### 3.2. @AssociationOverrides

**@AssociationOverrides** dùng khi cần khai báo **nhiều @AssociationOverride** tại cùng một vị trí:

~~~java
@Embedded
@AssociationOverrides({
    @AssociationOverride(
        name = "requestedBy",
        joinColumns = @JoinColumn(name = "review_requested_by_id")
    ),
    @AssociationOverride(
        name = "approvedBy",
        joinColumns = @JoinColumn(name = "review_approved_by_id")
    )
})
private ApprovalParticipants reviewParticipants;
~~~

Annotation này là một nhóm các override độc lập; mỗi **name** phải trỏ đúng một thuộc tính quan hệ có mặt trong kiểu nhúng tương ứng.

### 3.3. Khác biệt với @AttributeOverride

**@AttributeOverride** chỉ định lại ánh xạ **cột thuộc tính cơ bản**, ví dụ String note thành cột **primary_assignment_note**:

~~~java
@AttributeOverride(
    name = "note",
    column = @Column(name = "primary_assignment_note", length = 200)
)
~~~

**@AssociationOverride** chỉ định lại ánh xạ **quan hệ**, ví dụ **assignee** thành khóa ngoại **primary_assignee_id**:

~~~java
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(name = "primary_assignee_id")
)
~~~

| Thuộc tính trong @Embeddable | Annotation phù hợp | Đối tượng được cấu hình |
|---|---|---|
| String note | @AttributeOverride | @Column |
| BigDecimal amount | @AttributeOverride | @Column |
| @ManyToOne StaffMember assignee | @AssociationOverride | @JoinColumn hoặc cách join phù hợp |
| @OneToOne Profile profile | @AssociationOverride | Cột hoặc bảng liên kết của quan hệ |
| @ManyToMany Set<Tag> tags | @AssociationOverride nếu quan hệ dùng bảng liên kết | @JoinTable |

Đổi tên thuộc tính Java trong lớp không tự đổi mapping của các nơi nhúng; ngược lại, chỉ đổi @Column của **note** không giúp JPA biết **assignee** phải dùng cột khóa ngoại khác.

## 4. Ví dụ hoàn chỉnh: nhúng một kiểu hai lần

Đây là tình huống thực tế thường gặp nhất: **một entity có nhiều nhóm dữ liệu cùng kiểu, nhưng mỗi nhóm có khóa ngoại riêng**.

### 4.1. Ánh xạ WorkItem

Lớp **Assignment** và **StaffMember** đã khai báo ở phần trước. Bây giờ tạo WorkItem với hai vai trò:

~~~java
package com.example.work;

import jakarta.persistence.AssociationOverride;
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "work_items")
public class WorkItem {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "title", nullable = false, length = 180)
    private String title;

    @Embedded
    @AssociationOverride(
        name = "assignee",
        joinColumns = @JoinColumn(
            name = "primary_assignee_id",
            referencedColumnName = "id",
            nullable = false
        )
    )
    @AttributeOverride(
        name = "note",
        column = @Column(
            name = "primary_assignment_note",
            length = 200
        )
    )
    private Assignment primaryAssignment;

    @Embedded
    @AssociationOverride(
        name = "assignee",
        joinColumns = @JoinColumn(
            name = "backup_assignee_id",
            referencedColumnName = "id",
            nullable = false
        )
    )
    @AttributeOverride(
        name = "note",
        column = @Column(
            name = "backup_assignment_note",
            length = 200
        )
    )
    private Assignment backupAssignment;

    protected WorkItem() {}

    public WorkItem(
        String title,
        Assignment primaryAssignment,
        Assignment backupAssignment
    ) {
        this.title = title;
        this.primaryAssignment = primaryAssignment;
        this.backupAssignment = backupAssignment;
    }

    public Long getId() {
        return id;
    }

    public Assignment getPrimaryAssignment() {
        return primaryAssignment;
    }

    public Assignment getBackupAssignment() {
        return backupAssignment;
    }
}
~~~

Trong WorkItem:

- Hai trường **primaryAssignment** và **backupAssignment** đều mang cùng kiểu Java **Assignment**.
- Trong **primaryAssignment**, **assignee** được lưu bởi khóa ngoại **primary_assignee_id**; trong **backupAssignment**, khóa ngoại là **backup_assignee_id**.
- Tương tự, hai thuộc tính **note** lần lượt dùng **primary_assignment_note** và **backup_assignment_note**.
- Cả hai khóa ngoại cùng tham chiếu cột **id** của bảng **staff_members**, nhưng **vai trò** của chúng khác nhau.
- **@ManyToOne(fetch = LAZY, optional = false)** vẫn được định nghĩa trong Assignment. @AssociationOverride thay đổi cấu trúc join, không định nghĩa lại fetch hoặc cardinality.

Ở đây hai vai trò đều bắt buộc có người được giao; vì vậy ví dụ dùng **nullable = false** cho cả hai cột khóa ngoại. Nếu nghiệp vụ muốn vai trò dự phòng có thể vắng mặt, cần thiết kế tính optional/null một cách nhất quán thay vì chỉ sửa nullable ở một chỗ.

### 4.2. Hình dung schema

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE staff_members (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE work_items (
    id BIGINT PRIMARY KEY,
    title VARCHAR(180) NOT NULL,
    primary_assignee_id BIGINT NOT NULL,
    primary_assignment_note VARCHAR(200),
    backup_assignee_id BIGINT NOT NULL,
    backup_assignment_note VARCHAR(200),
    CONSTRAINT fk_work_primary_assignee
        FOREIGN KEY (primary_assignee_id) REFERENCES staff_members(id),
    CONSTRAINT fk_work_backup_assignee
        FOREIGN KEY (backup_assignee_id) REFERENCES staff_members(id)
);
~~~

Lược đồ này mô tả các cột và ràng buộc quan hệ; cơ chế **@GeneratedValue** phải có cấu hình cấp ID tương ứng để thực hiện INSERT thực tế. SQL sinh từ provider có thể khác theo cơ sở dữ liệu, dialect và chiến lược sinh khóa.

Đặc biệt **không có bảng Assignment**. Dữ liệu Assignment được trải thành các cột ở **work_items**, còn StaffMember là entity có bảng riêng.

Ví dụ một hàng WorkItem:

| id | title | primary_assignee_id | primary_assignment_note | backup_assignee_id | backup_assignment_note |
|---:|---|---:|---|---:|---|
| 501 | Kiểm tra bản phát hành | 7 | Kiểm tra API | 19 | Thay ca buổi tối |

Khi tải WorkItem này, JPA biết **primaryAssignment.assignee** phải nối theo cột **primary_assignee_id**, trong khi **backupAssignment.assignee** phải nối theo **backup_assignee_id**.

### 4.3. Lưu dữ liệu qua persistence context

Giả sử có **EntityManager** loại RESOURCE_LOCAL hoạt động hợp lệ:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    StaffMember primary = em.find(StaffMember.class, 7L);
    StaffMember backup = em.find(StaffMember.class, 19L);
    if (primary == null || backup == null) {
        throw new IllegalArgumentException("Staff member not found");
    }

    WorkItem item = new WorkItem(
        "Kiểm tra bản phát hành",
        new Assignment(primary, "Kiểm tra API"),
        new Assignment(backup, "Thay ca buổi tối")
    );

    em.persist(item);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Đoạn mã chỉ minh họa một Unit of Work; việc tạo, đóng EntityManager và EntityManagerFactory được đảm nhiệm ở tầng gọi. JPA ghi khóa ngoại theo mapping của từng field embedded trong WorkItem. Trong ví dụ này, **primary** và **backup** đã là entity managed do **find()** trả về; không cần gọi persist cho chúng.

Đừng bật **CascadeType.PERSIST** trên quan hệ tới nhân viên chỉ để tránh việc tìm nhân viên hiện có. Cascade mang ý nghĩa quản lý vòng đời đối tượng và có thể kéo theo thao tác không mong muốn nếu dùng sai.

### 4.4. Truy vấn với đường dẫn thuộc tính Java

Trong JPQL, truy cập quan hệ thông qua **đường dẫn thuộc tính**, không thông qua tên cột SQL:

~~~java
List<WorkItem> items = em.createQuery(
    """
    select w
    from WorkItem w
    where w.primaryAssignment.assignee.id = :staffId
    """,
    WorkItem.class
).setParameter("staffId", 7L)
 .getResultList();
~~~

Ví dụ dùng text block Java 15+. Nếu ứng dụng dùng phiên bản Java cũ hơn, thay text block bằng chuỗi Java thông thường. Tên **primaryAssignment**, **assignee** và **id** xuất phát từ mapping Java. Câu SQL do provider sinh sẽ dựa vào **primary_assignee_id** mà @AssociationOverride quy định.

Có thể truy vấn theo vai trò dự phòng:

~~~java
List<WorkItem> backupItems = em.createQuery(
    "select w from WorkItem w " +
    "where w.backupAssignment.assignee.id = :staffId",
    WorkItem.class
).setParameter("staffId", 19L)
 .getResultList();
~~~

Một lỗi phổ biến là viết JPQL **w.primary_assignee_id**; đây là tên cột, không phải thuộc tính Java của entity.

## 5. @AssociationOverrides cho nhiều quan hệ trong cùng đối tượng nhúng

Đôi khi một kiểu nhúng chứa **hai hoặc nhiều quan hệ** và ta muốn sử dụng lại cả nhóm trong nhiều vai trò.

Ví dụ:

~~~java
@Embeddable
public class ReviewParticipants {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "requester_id")
    private StaffMember requestedBy;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "approver_id")
    private StaffMember approvedBy;

    protected ReviewParticipants() {}
}
~~~

Khi nhúng vào một entity khác, ta cần cột riêng cho cả requester và approver:

~~~java
@Entity
@Table(name = "change_requests")
public class ChangeRequest {
    @Id
    private Long id;

    @Embedded
    @AssociationOverrides({
        @AssociationOverride(
            name = "requestedBy",
            joinColumns = @JoinColumn(
                name = "review_requested_by_id"
            )
        ),
        @AssociationOverride(
            name = "approvedBy",
            joinColumns = @JoinColumn(
                name = "review_approved_by_id"
            )
        )
    })
    private ReviewParticipants reviewParticipants;

    protected ChangeRequest() {}
}
~~~

Ý nghĩa:

| Thuộc tính Java | Ánh xạ gốc trong @Embeddable | Ánh xạ sau override |
|---|---|---|
| reviewParticipants.requestedBy | requester_id | review_requested_by_id |
| reviewParticipants.approvedBy | approver_id | review_approved_by_id |

Vẫn chỉ có **một ReviewParticipants** bên trong ChangeRequest nhưng chứa hai quan hệ cần ghi đè. Ngược lại, ở ví dụ WorkItem phía trên, có **hai instance Assignment** với cùng một quan hệ bên trong; mỗi vị trí embedded cần override riêng.

Nếu ứng dụng dùng Jakarta Persistence và môi trường Java hỗ trợ repeatable annotations, có thể thấy nhiều @AssociationOverride viết liền nhau; **@AssociationOverrides** vẫn là cú pháp nhóm rõ ràng và dễ đọc, đặc biệt trong tài liệu hoặc codebase cần tương thích nhất quán.

## 6. Đường dẫn lồng nhau khi một @Embeddable chứa @Embeddable khác

Kiểu nhúng có thể chứa một kiểu nhúng sâu hơn. Khi quan hệ nằm nhiều cấp bên trong, tên trong **@AssociationOverride** sử dụng **đường dẫn thuộc tính, ngăn cách bởi dấu chấm**.

### 6.1. Mô hình hai tầng

Giả sử một địa chỉ chứa quốc gia tham chiếu entity:

~~~java
@Entity
@Table(name = "countries")
public class Country {
    @Id
    private String code;

    protected Country() {}
}

@Embeddable
public class Address {
    @Column(name = "street", length = 160)
    private String street;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "country_code", referencedColumnName = "code")
    private Country country;

    protected Address() {}
}

@Embeddable
public class DeliveryDetails {
    @Embedded
    private Address address;

    @Column(name = "delivery_note", length = 200)
    private String deliveryNote;

    protected DeliveryDetails() {}
}
~~~

Entity **PurchaseOrder** có một nhóm thông tin giao hàng:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Embedded
    @AssociationOverride(
        name = "address.country",
        joinColumns = @JoinColumn(
            name = "delivery_country_code",
            referencedColumnName = "code"
        )
    )
    @AttributeOverrides({
        @AttributeOverride(
            name = "address.street",
            column = @Column(name = "delivery_street", length = 160)
        ),
        @AttributeOverride(
            name = "deliveryNote",
            column = @Column(name = "delivery_note", length = 200)
        )
    })
    private DeliveryDetails delivery;

    protected PurchaseOrder() {}
}
~~~

Đường dẫn:

~~~text
PurchaseOrder.delivery             (@Embedded DeliveryDetails)
  └── address                      (@Embedded Address)
       ├── street                  (basic attribute)
       └── country                 (@ManyToOne Country)
~~~

Ở vị trí annotation trên trường **delivery**, tên **address.country** xác định quan hệ cần ghi đè, còn **address.street** xác định thuộc tính cơ bản. Đường dẫn **không** chứa tiền tố **delivery** vì annotation đang áp dụng trực tiếp lên trường đó.

Khi cần diễn đạt cùng override ở cấp lớp entity, quy tắc tên phải phản ánh đường dẫn từ phạm vi khai báo, chẳng hạn **delivery.address.country**. Không thể sử dụng một tên ngắn nếu nó không còn xác định đúng thuộc tính từ vị trí đặt annotation.

### 6.2. Tại sao không dùng tên cột SQL trong thuộc tính name?

Ví dụ sai về ý tưởng:

~~~java
@AssociationOverride(
    name = "country_code",
    joinColumns = @JoinColumn(name = "delivery_country_code")
)
~~~

Trong mô hình Address, **country_code** là tên cột gốc, còn quan hệ Java tên **country**. Vì @AssociationOverride cần biết **thuộc tính quan hệ nào** được ghi đè, nên phải dùng **name = "address.country"** khi áp dụng ở DeliveryDetails. Tên cột thực cần đổi đặt tại **@JoinColumn(name = "...")**.

## 7. Ghi đè bằng @JoinTable

Đối với một quan hệ được lưu bằng **bảng liên kết** thay vì khóa ngoại trực tiếp, có thể chỉ định **joinTable** trong @AssociationOverride.

Điển hình là quan hệ **@ManyToMany** từ một kiểu nhúng tới entity khác.

### 7.1. Kiểu nhúng sở hữu quan hệ nhiều-nhiều

Ví dụ một nhóm người được phép xem:

~~~java
@Entity
@Table(name = "user_accounts")
public class UserAccount {
    @Id
    private Long id;

    protected UserAccount() {}
}

@Embeddable
public class Audience {

    @ManyToMany
    @JoinTable(
        name = "generic_audience_members",
        joinColumns = @JoinColumn(name = "owner_id"),
        inverseJoinColumns = @JoinColumn(name = "member_id")
    )
    private Set<UserAccount> members = new HashSet<>();

    protected Audience() {}

    public Set<UserAccount> getMembers() {
        return members;
    }
}
~~~

Trong ví dụ này, Audience không có khóa chính riêng. Bảng liên kết nối **entity đang nhúng Audience** với những UserAccount liên quan. Nếu một entity cần dùng Audience cho hai mục đích, nó có thể ghi đè tên bảng và khóa ngoại của từng trường embedded.

### 7.2. Hai nhóm Audience, hai bảng liên kết

~~~java
@Entity
@Table(name = "campaigns")
public class Campaign {

    @Id
    private Long id;

    @Embedded
    @AssociationOverride(
        name = "members",
        joinTable = @JoinTable(
            name = "campaign_internal_members",
            joinColumns = @JoinColumn(name = "campaign_id"),
            inverseJoinColumns = @JoinColumn(name = "member_id")
        )
    )
    private Audience internalAudience = new Audience();

    @Embedded
    @AssociationOverride(
        name = "members",
        joinTable = @JoinTable(
            name = "campaign_external_members",
            joinColumns = @JoinColumn(name = "campaign_id"),
            inverseJoinColumns = @JoinColumn(name = "member_id")
        )
    )
    private Audience externalAudience = new Audience();

    protected Campaign() {}
}
~~~

Giả sử các annotation còn thiếu được import từ **jakarta.persistence** và Java collections; tập **Set/HashSet** thuộc **java.util**.

Schema minh họa:

~~~sql
CREATE TABLE campaigns (
    id BIGINT PRIMARY KEY
);

CREATE TABLE user_accounts (
    id BIGINT PRIMARY KEY
);

CREATE TABLE campaign_internal_members (
    campaign_id BIGINT NOT NULL REFERENCES campaigns(id),
    member_id BIGINT NOT NULL REFERENCES user_accounts(id),
    PRIMARY KEY (campaign_id, member_id)
);

CREATE TABLE campaign_external_members (
    campaign_id BIGINT NOT NULL REFERENCES campaigns(id),
    member_id BIGINT NOT NULL REFERENCES user_accounts(id),
    PRIMARY KEY (campaign_id, member_id)
);
~~~

Ở đây:

- **joinColumns** trong **@JoinTable** chỉ định cột phía entity chứa Audience, tức **Campaign**.
- **inverseJoinColumns** chỉ định cột tham chiếu entity đích, tức **UserAccount**.
- **name = "members"** trong @AssociationOverride vẫn là tên thuộc tính quan hệ Java của Audience.
- **joinTable.name** được dùng làm tên bảng SQL riêng cho từng vai trò.

Không nên đặt cả hai vai trò vào cùng bảng liên kết nếu schema không có cột hoặc quy tắc phân biệt vai trò rõ ràng. Dùng hai bảng trong ví dụ giúp mỗi tập thành viên có ý nghĩa độc lập.

### 7.3. @JoinColumn hay @JoinTable?

| Mapping gốc | Cách override thường phù hợp | Ví dụ |
|---|---|---|
| @ManyToOne gắn khóa ngoại trong bảng chứa | joinColumns | work_items.primary_assignee_id |
| @OneToOne sở hữu khóa ngoại trong bảng chứa | joinColumns | documents.approver_profile_id |
| @ManyToMany sở hữu bảng liên kết | joinTable | campaign_internal_members |
| Quan hệ một-nhiều unidirectional dùng join table | joinTable | Bảng trung gian nối entity chứa và các entity con |
| Quan hệ inverse có mappedBy | Phải xét lại phía sở hữu | Không thể đổi tùy tiện sang một khóa ngoại riêng trên phía inverse |

Đây là các trường hợp thường gặp. Khi triển khai thực tế, cần căn cứ vào **mapping gốc** và **sơ đồ sở hữu quan hệ**; không thể biến một quan hệ inverse thành quan hệ sở hữu bằng việc thay tên bảng trong annotation.

## 8. Khóa ngoại gồm nhiều cột

Một quan hệ có thể tham chiếu khóa ghép của entity đích. Khi đó, **@AssociationOverride** có thể khai báo nhiều **@JoinColumn** trong mảng **joinColumns**.

Giả sử bảng khách hàng có khóa chính ghép:

~~~text
customers
  tenant_id     PK phần 1
  customer_no   PK phần 2
  display_name
~~~

Entity Customer được ánh xạ đúng khóa ghép bằng **@EmbeddedId** hoặc **@IdClass**. Một kiểu nhúng chứa quan hệ:

~~~java
@Embeddable
public class CustomerLink {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumns({
        @JoinColumn(
            name = "customer_tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @JoinColumn(
            name = "customer_no",
            referencedColumnName = "customer_no"
        )
    })
    private Customer customer;

    protected CustomerLink() {}
}
~~~

Khi được nhúng vào phiếu dịch vụ, ta đổi cả hai cột của khóa ngoại:

~~~java
@Embedded
@AssociationOverride(
    name = "customer",
    joinColumns = {
        @JoinColumn(
            name = "billing_tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @JoinColumn(
            name = "billing_customer_no",
            referencedColumnName = "customer_no"
        )
    }
)
private CustomerLink billingCustomer;
~~~

Điểm cần nhớ:

1. Với khóa ghép, cần ánh xạ **đầy đủ các thành phần** theo khóa/unique key của entity đích.
2. **name** trong @JoinColumn là cột khóa ngoại ở bảng đang chứa quan hệ; **referencedColumnName** là cột được tham chiếu của bảng entity đích.
3. Nếu bỏ sót một thành phần, dùng sai referencedColumnName hoặc vô tình trỏ vào cột không phù hợp, provider có thể thất bại khi khởi tạo mapping hoặc DB có thể từ chối DDL/DML.
4. Khi schema cho phép null, cần hiểu quy tắc toàn bộ composite foreign key và nghiệp vụ; không nên để một nửa khóa null mà không có thiết kế rõ ràng.

Ví dụ ở trên tập trung vào cách ghi đè **cột join**; phần định nghĩa hoàn chỉnh của khóa ghép Customer là một chủ đề ánh xạ định danh riêng.

## 9. Đặt override trên field, getter hoặc lớp entity

### 9.1. Override trực tiếp trên vị trí @Embedded

Cách dễ hiểu nhất là đặt **@AssociationOverride** ngay trên field embedded:

~~~java
@Embedded
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(name = "primary_assignee_id")
)
private Assignment primaryAssignment;
~~~

Annotation này chỉ có hiệu lực đối với **vị trí primaryAssignment**. Một field embedded khác cùng kiểu Assignment có thể có cấu hình override riêng.

### 9.2. Override ở cấp lớp entity

Với class-level override, **name** cần chỉ đường dẫn đầy đủ từ entity đến quan hệ cần ghi đè:

~~~java
@Entity
@AssociationOverride(
    name = "primaryAssignment.assignee",
    joinColumns = @JoinColumn(name = "primary_assignee_id")
)
public class WorkItem {
    @Id
    private Long id;

    @Embedded
    private Assignment primaryAssignment;

    protected WorkItem() {}
}
~~~

Ví dụ này minh họa một cách diễn đạt thay thế cho việc đặt override lên field. Không cần khai báo **cùng một override ở cả lớp và field** trừ khi có lý do và hiểu rõ quy tắc ưu tiên của provider. Một nhóm lớn override đôi khi dễ theo dõi hơn nếu đặt gần trường nhúng, nơi vai trò nghiệp vụ được xác định.

### 9.3. Tôn trọng chiến lược truy cập của JPA

Nếu entity dùng **field access** (ví dụ @Id đặt trên field), thường đặt @Embedded/@AssociationOverride trên field. Nếu entity dùng **property access**, đặt các annotation tương ứng trên getter:

~~~java
@Embedded
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(name = "primary_assignee_id")
)
public Assignment getPrimaryAssignment() {
    return primaryAssignment;
}
~~~

Đặt annotation sai phía có thể khiến mapping không áp dụng như mong muốn. Khi cần trộn field và property access một cách chủ động, dùng **@Access** phù hợp theo đặc tả JPA.

### 9.4. Override cũng có thể dùng với @MappedSuperclass

**@AssociationOverride** không chỉ dành cho @Embeddable. Một entity kế thừa **@MappedSuperclass** có thể ghi đè mapping quan hệ đã khai báo ở superclass, ví dụ đổi tên khóa ngoại được thừa hưởng cho bảng của subclass.

Tuy nhiên, trong chủ đề kiểu giá trị nhúng, cách dùng quan trọng nhất vẫn là **ghi đè từ field @Embedded hoặc đường dẫn chứa nó**. Không nên nhầm superclass mapping với việc đối tượng nhúng tự có một bảng mới.

## 10. Điều gì thay đổi và điều gì giữ nguyên?

Phạm vi của @AssociationOverride hẹp hơn một số lập trình viên tưởng:

| Đặc điểm quan hệ | @AssociationOverride có thay đổi không? | Cách xử lý đúng |
|---|---|---|
| Tên cột khóa ngoại | Có, qua joinColumns | Đặt @JoinColumn(name = ...) |
| Cột đích được tham chiếu | Có, qua referencedColumnName khi phù hợp | Khớp khóa của entity đích và schema |
| Tên bảng liên kết | Có, qua joinTable | Đặt @JoinTable(name = ...) |
| Các cột của bảng liên kết | Có, qua joinColumns/inverseJoinColumns của @JoinTable | Phân biệt phía sở hữu và phía đích |
| Loại quan hệ @ManyToOne, @OneToOne, @ManyToMany | Không | Được quyết định ở khai báo quan hệ gốc |
| Kiểu entity đích | Không | Được xác định bởi kiểu trường/targetEntity của mapping gốc |
| FetchType.LAZY hoặc EAGER | Không | Cấu hình trong annotation quan hệ gốc |
| CascadeType | Không | Cấu hình trong annotation quan hệ gốc |
| optional của @ManyToOne/@OneToOne | Không | Quy định ở quan hệ gốc |
| orphanRemoval | Không | Phụ thuộc quan hệ gốc khi áp dụng |
| Tên cột thuộc tính cơ bản trong embeddable | Không | Dùng @AttributeOverride |
| Dữ liệu có được quản lý theo transaction hay không | Không | Do persistence context và transaction quyết định |

Điều này tác động trực tiếp đến thiết kế kiểu nhúng dùng lại: nếu các nơi sử dụng cần **fetch, cascade hoặc optional khác nhau**, riêng @AssociationOverride **không đủ** để biểu diễn sự khác biệt. Có thể phải thiết kế các kiểu nhúng hoặc entity khác, hoặc đưa quan hệ lên entity chủ để giữ đúng quy tắc nghiệp vụ.

### 10.1. Ví dụ về optional và nullable

Giả sử trong @Embeddable có:

~~~java
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "assignee_id", nullable = false)
private StaffMember assignee;
~~~

Sau đó một vị trí nhúng ghi:

~~~java
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(
        name = "backup_assignee_id",
        nullable = true
    )
)
~~~

**nullable = true** trong cấu hình join biểu diễn cột SQL có thể NULL khi sinh schema, nhưng **optional = false** ở mapping quan hệ vẫn thể hiện quan hệ bắt buộc có entity đích. Cấu hình này có thể làm thông điệp giữa mô hình Java và schema thiếu nhất quán. Khi nghiệp vụ yêu cầu vai trò không bắt buộc, hãy điều chỉnh thiết kế tổng thể để ý nghĩa của optional và nullable khớp nhau.

Không nên xem @AssociationOverride là cách thay thế hoặc ghi đè **@ManyToOne(optional = ...)**.

### 10.2. Khi quan hệ có mappedBy

Quan hệ hai chiều có **phía sở hữu** và **phía không sở hữu**. Ví dụ ở quan hệ ManyToOne/OneToMany hai chiều thông dụng, cột khóa ngoại nằm ở phía ManyToOne. Chỉ đổi @JoinColumn trên một phía **mappedBy** không làm nó trở thành phía sở hữu.

Khi gặp mapping phức tạp trong @Embeddable:

- Xác định entity nào thực sự lưu khóa ngoại hoặc bảng liên kết.
- Kiểm tra quan hệ trong kiểu nhúng là owning-side hay inverse-side.
- Đặt override trên mapping có ý nghĩa vật lý ở phía sở hữu.
- Không cố “sửa” một quan hệ inverse bằng cách khai báo thêm @JoinColumn trái với thiết kế sở hữu.

Nếu mô hình liên tục đòi hỏi đảo vai trò sở hữu ở mỗi lần nhúng, nên cân nhắc thiết kế khác thay vì dựa vào một chuỗi override khó hiểu.

## 11. Kết hợp với @AttributeOverrides trong mô hình tái sử dụng

Đối tượng nhúng thường có cả **dữ liệu giá trị** và **tham chiếu entity**. Khi lặp lại cùng kiểu nhúng, có thể cần cả hai nhóm annotation:

~~~java
@Embeddable
public class ApprovalInfo {
    @Column(name = "approval_comment", length = 500)
    private String comment;

    @Column(name = "approved_at")
    private LocalDateTime approvedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "approver_id")
    private StaffMember approver;

    protected ApprovalInfo() {}
}
~~~

Một entity có hai bước phê duyệt:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "comment",
        column = @Column(name = "initial_approval_comment", length = 500)
    ),
    @AttributeOverride(
        name = "approvedAt",
        column = @Column(name = "initial_approved_at")
    )
})
@AssociationOverride(
    name = "approver",
    joinColumns = @JoinColumn(name = "initial_approver_id")
)
private ApprovalInfo initialApproval;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "comment",
        column = @Column(name = "final_approval_comment", length = 500)
    ),
    @AttributeOverride(
        name = "approvedAt",
        column = @Column(name = "final_approved_at")
    )
})
@AssociationOverride(
    name = "approver",
    joinColumns = @JoinColumn(name = "final_approver_id")
)
private ApprovalInfo finalApproval;
~~~

Đoạn mã là hai field của một entity có các import phù hợp. Cách ánh xạ này giúp type ApprovalInfo có thể dùng lại nhưng cột dữ liệu của mỗi bước được phân biệt rõ ràng.

Sơ đồ quan hệ:

~~~mermaid
flowchart TD
    A[Entity chứa 2 bước phê duyệt] --> B[initialApproval: ApprovalInfo]
    A --> C[finalApproval: ApprovalInfo]
    B --> D[initial_approver_id]
    B --> E[initial_approved_at / initial_approval_comment]
    C --> F[final_approver_id]
    C --> G[final_approved_at / final_approval_comment]
    D --> H[(staff_members)]
    F --> H
~~~

**@AttributeOverride** và **@AssociationOverride** bổ sung cho nhau; không có annotation nào thay thế hoàn toàn annotation còn lại.

## 12. Kết hợp với các mapping nâng cao

### 12.1. Kiểu nhúng được dùng trong @ElementCollection

Một entity có thể chứa tập các kiểu nhúng trong **@ElementCollection**. Khi đó, dữ liệu của mỗi embeddable thường nằm trong collection table; những quan hệ entity bên trong kiểu nhúng cũng chịu các quy tắc ánh xạ tương ứng.

Ví dụ về ý tưởng:

~~~java
@Embeddable
public class ContactRole {
    @ManyToOne
    @JoinColumn(name = "staff_id")
    private StaffMember staff;

    @Column(name = "role_name", length = 60)
    private String roleName;

    protected ContactRole() {}
}

@Entity
public class Project {
    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "project_contact_roles",
        joinColumns = @JoinColumn(name = "project_id")
    )
    @AssociationOverride(
        name = "staff",
        joinColumns = @JoinColumn(name = "contact_staff_id")
    )
    private Set<ContactRole> contacts = new HashSet<>();

    protected Project() {}
}
~~~

Ở đây, **project_contact_roles** là collection table chứa các giá trị nhúng ContactRole; cột **contact_staff_id** trong bảng này tham chiếu staff_members. Tùy loại quan hệ và vị trí ánh xạ, một số dạng collection-valued relationship bên trong embeddable bị giới hạn theo đặc tả, nên không được suy luận rằng mọi đồ thị quan hệ đều có thể đặt tự do trong @ElementCollection.

Đặc biệt, **@ElementCollection** lưu các giá trị nhúng, còn **@OneToMany** quản lý tập các entity có identity riêng. Hai trường hợp khác nhau về vòng đời và khóa.

### 12.2. Không lẫn với @EmbeddedId

**@EmbeddedId** dùng một embeddable làm **định danh ghép** của entity. Các quy tắc cho class dùng làm embedded ID nghiêm ngặt hơn class dùng như value object thông thường. Không nên đưa các quan hệ bất kỳ vào một embedded ID rồi giả định có thể sửa join bằng @AssociationOverride. Nếu muốn ánh xạ khóa ghép liên kết entity, cần xem các quy tắc định danh và **@MapsId** theo mô hình cụ thể.

### 12.3. Không phải mọi quan hệ trong embeddable đều cần override

Nếu chỉ có một vị trí embedded và tên join mặc định phù hợp với DB, có thể giữ:

~~~java
@Embedded
private Assignment assignment;
~~~

Ghi đè có ích khi phải thay đổi tên khóa ngoại/bảng liên kết, ánh xạ tới schema hiện hữu, hoặc phân biệt nhiều vị trí dùng lại. Không cần thêm annotation chỉ để tăng độ dài code.

## 13. Tác động đến transaction, cascade và lazy loading

@AssociationOverride thay đổi **cách JPA biết quan hệ được lưu ở đâu**, không thay đổi quy trình làm việc của persistence context.

Khi WorkItem đang managed:

~~~java
WorkItem item = em.find(WorkItem.class, 501L);
StaffMember primary = item.getPrimaryAssignment().getAssignee();
StaffMember backup = item.getBackupAssignment().getAssignee();
~~~

Nếu hai StaffMember khác nhau, JPA có thể dùng hai khóa ngoại riêng như đã khai báo. Nếu **fetch = LAZY**, việc đọc đối tượng đích có thể khiến provider truy vấn hoặc khởi tạo proxy khi cần; còn có truy vấn ngay tại lệnh getter hay không phụ thuộc provider, tình trạng entity trong context và chiến lược fetch.

Một số điểm cần tránh nhầm lẫn:

1. **Override không bắt đầu transaction.** Transaction được quản lý bởi EntityTransaction, JTA hoặc transaction manager của framework.
2. **Override không bảo đảm dữ liệu được flush ngay.** Dirty checking và flush vẫn tuân thủ vòng đời persistence context.
3. **Override không bật cascade.** Nếu quan hệ @ManyToOne không có cascade, gọi persist WorkItem không tự persist một StaffMember mới chưa được quản lý.
4. **Override không thay fetch mode.** Nếu quan hệ gốc là EAGER, đổi join column không làm nó thành LAZY; nếu là LAZY, cần dùng entity trong bối cảnh có khả năng tải quan hệ khi cần.
5. **Override không sửa dữ liệu cũ trong DB.** Nếu trước đây cả hai vai trò cùng dùng một cột, chuyển sang hai cột cần migration và quy tắc di chuyển dữ liệu.

Ví dụ, thay đổi người phụ trách chính qua một Assignment mới:

~~~java
tx.begin();

WorkItem item = em.find(WorkItem.class, 501L);
StaffMember replacement = em.find(StaffMember.class, 30L);

if (item == null || replacement == null) {
    throw new IllegalArgumentException("Missing data");
}

// Giả định WorkItem có phương thức setPrimaryAssignment phù hợp.
item.setPrimaryAssignment(
    new Assignment(replacement, "Chuyển giao cho ca sáng")
);

tx.commit();
~~~

Khi WorkItem managed và transaction được commit hợp lệ, provider theo dõi trạng thái của embedded Assignment để cập nhật **primary_assignee_id** và **primary_assignment_note**. Cột **backup_assignee_id** không cần đổi theo logic nghiệp vụ này. Tuy nhiên, ORM có thể tạo câu SQL UPDATE với tập cột cụ thể tùy cách triển khai; không nên phụ thuộc vào dạng SQL chính xác nếu đặc tả không bảo đảm.

## 14. Xử lý thay đổi schema trong dự án thực tế

Ghi đè ánh xạ thường đi kèm thay đổi thiết kế bảng. Cần kiểm tra **cột nào hiện có**, ràng buộc nào đang áp dụng, và cần xử lý dữ liệu cũ ra sao.

Giả sử bảng work_items ban đầu chỉ có:

~~~sql
assignee_id BIGINT,
assignment_note VARCHAR(200)
~~~

Sau khi bổ sung người phụ trách chính và dự phòng, ứng dụng cần:

~~~sql
primary_assignee_id BIGINT,
primary_assignment_note VARCHAR(200),
backup_assignee_id BIGINT,
backup_assignment_note VARCHAR(200)
~~~

Quy trình triển khai điển hình:

1. Quyết định dữ liệu cũ của **assignee_id** được chuyển vào **primary_assignee_id** hay vai trò nào khác.
2. Tạo các cột mới ở schema bằng migration (Flyway, Liquibase hoặc cơ chế tương đương).
3. Chuyển dữ liệu theo quy tắc nghiệp vụ; xác định giá trị cho backup nếu cần.
4. Thêm khóa ngoại và NOT NULL phù hợp sau khi dữ liệu đáp ứng yêu cầu.
5. Cập nhật mapping JPA bằng @AssociationOverride và @AttributeOverride.
6. Thực hiện triển khai tương thích giữa phiên bản ứng dụng và schema nếu hệ thống yêu cầu rolling deployment.

Không nên giả định rằng đổi **@JoinColumn(name = "...")** trong mã sẽ tự đổi tên cột DB đang có ở production. Cơ chế schema-generation của JPA/provider khác với hệ thống migration có phiên bản; tự động update schema không bảo đảm chuyển dữ liệu và ràng buộc theo ý đồ nghiệp vụ.

### 14.1. Khi sử dụng database có sẵn

Đối với một schema kế thừa, quan hệ có thể dùng tên khác nhau:

~~~text
orders.approved_by_user_id
refunds.authorized_staff_id
receipts.checked_by_id
~~~

Cùng kiểu nhúng ApprovalInfo tham chiếu StaffMember nhưng phải được đặt **@AssociationOverride** ở từng entity để khớp tên cột, miễn là ý nghĩa nghiệp vụ và các tùy chọn quan hệ gốc tương thích.

Điều này là một lợi ích lớn của kiểu giá trị nhúng: **dùng lại cấu trúc Java mà không bắt buộc tất cả bảng SQL có cùng tên cột**.

## 15. Các lỗi thường gặp và cách xử lý

### 15.1. Hai field embedded dùng chung tên khóa ngoại

~~~java
@Embedded
private Assignment primaryAssignment;

@Embedded
private Assignment backupAssignment;
~~~

Vì Assignment khai báo **@JoinColumn(name = "assignee_id")**, cả hai field có thể cùng ánh xạ tới **assignee_id**. Provider có thể phát hiện mapping xung đột hoặc tạo hành vi không đúng mong muốn.

**Cách xử lý:** dùng @AssociationOverride riêng cho từng field để có **primary_assignee_id** và **backup_assignee_id**; đồng thời dùng @AttributeOverride cho các cột cơ bản trùng tên.

### 15.2. Dùng @AttributeOverride cho quan hệ

Ví dụ sai:

~~~java
@AttributeOverride(
    name = "assignee",
    column = @Column(name = "primary_assignee_id")
)
~~~

**assignee** là @ManyToOne, không phải basic attribute; dùng **@AssociationOverride** với **@JoinColumn**.

### 15.3. Dùng @AssociationOverride cho String

Ví dụ sai:

~~~java
@AssociationOverride(
    name = "note",
    joinColumns = @JoinColumn(name = "primary_note")
)
~~~

**note** là String được @Column ánh xạ, không phải một association. Cần **@AttributeOverride**.

### 15.4. Sai tên ở name

Trong kiểu nhúng Assignment, property là **assignee**, nhưng dùng:

~~~java
@AssociationOverride(
    name = "assignee_id",
    joinColumns = @JoinColumn(name = "primary_assignee_id")
)
~~~

Tên đầu tiên trỏ vào một cột SQL, trong khi API yêu cầu tên thuộc tính Java. Hãy sửa thành **name = "assignee"**.

### 15.5. Quên đường dẫn trong kiểu nhúng lồng nhau

Nếu DeliveryDetails chứa Address và Address chứa Country, khai báo trên **delivery** phải tìm đến **address.country**. Viết **country** không đủ để chỉ ra mối quan hệ nằm sâu trong Address.

### 15.6. Cấu hình @JoinTable nhưng bảng liên kết không khớp

Với quan hệ ManyToMany, cần phân biệt:

- Tên bảng liên kết.
- Join column tham chiếu entity sở hữu.
- Inverse join column tham chiếu entity đích.

Đảo hai phía hoặc đặt cả hai field embedded dùng chung một join table không phân vai trò có thể dẫn đến dữ liệu trộn lẫn hoặc lỗi khóa ngoại. Kiểm tra DDL, khóa của bảng trung gian và vai trò sở hữu trong mapping gốc.

### 15.7. Mong override thay đổi optional/fetch/cascade

**@AssociationOverride** không có tham số để ghi đè @ManyToOne(optional), fetch hoặc cascade. Khi các nơi nhúng cần chiến lược đó khác nhau, cân nhắc tách kiểu giá trị hoặc đưa quan hệ lên từng entity.

### 15.8. Dùng tên cột trong JPQL

Sai về cú pháp đường dẫn:

~~~sql
select w from WorkItem w where w.primary_assignee_id = :id
~~~

Đúng:

~~~sql
select w from WorkItem w where w.primaryAssignment.assignee.id = :id
~~~

JPQL dùng **tên thuộc tính Java**. Tên cột **primary_assignee_id** chỉ thuộc về mapping hoặc SQL native.

### 15.9. Hiểu sai hiện tượng dữ liệu cũ trong persistence context

Sau khi cập nhật khóa ngoại bằng native SQL, một WorkItem đang managed có thể vẫn giữ đối tượng Assignment cũ. @AssociationOverride không khiến persistence context tự cập nhật. Khi trộn JPA với bulk update hoặc native DML, cần hiểu cơ chế flush, refresh và clear phù hợp với transaction.

### 15.10. Phụ thuộc vào DDL provider sinh

Annotation có thể hỗ trợ schema generation, nhưng cách đặt tên constraint, quoting, kiểu dữ liệu và thứ tự SQL có thể khác giữa Hibernate, EclipseLink và từng database. Với ứng dụng production, hãy kiểm soát schema bằng migration và xác nhận các khóa ngoại tương ứng tồn tại.

## 16. Hướng dẫn thiết kế ánh xạ quan hệ trong kiểu nhúng

Trước khi viết @AssociationOverride, nên trả lời theo thứ tự:

**Bước 1: Xác định kiểu nhúng có tái sử dụng hợp lý không.** Nó có đại diện một nhóm giá trị có ý nghĩa thống nhất? Nếu chỉ có quan hệ độc lập và mỗi nơi cần cascade/fetch/optional khác nhau, việc đặt quan hệ trực tiếp lên entity có thể dễ hiểu hơn.

**Bước 2: Xác định thuộc tính quan hệ trong @Embeddable.** Ví dụ **assignee**, **approver**, **country**, **members**. Đây chính là tên được đưa vào thuộc tính **name** của @AssociationOverride (hoặc đường dẫn kết hợp dấu chấm khi lồng nhau).

**Bước 3: Xác định bên sở hữu và cách lưu.** Với quan hệ sở hữu khóa ngoại, dùng **joinColumns**; với quan hệ dùng bảng liên kết, dùng **joinTable**. Không áp đặt join mới lên phía inverse khi mapping gốc không cho phép.

**Bước 4: Lập danh sách cột vật lý theo từng vị trí.** Cùng Assignment có thể xuất hiện tại **primaryAssignment** và **backupAssignment**; mỗi vị trí phải có join column và các cột cơ bản phù hợp.

**Bước 5: Đảm bảo các ràng buộc cùng ý nghĩa.** Kiểm tra optional, nullable, tham chiếu khóa đích, composite key, unique constraint và vòng đời entity liên quan.

**Bước 6: Kiểm tra sự tương thích với schema hiện có.** Ánh xạ JPA không tự di chuyển dữ liệu cũ hoặc giải quyết xung đột tên cột. Thiết kế migration rõ trước khi triển khai.

**Bước 7: Viết JPQL theo đường dẫn entity.** Kiểm tra các truy vấn dùng thuộc tính nhúng và quan hệ như **workItem.primaryAssignment.assignee**.

## 17. Bài tập tự thực hành

### Bài 1: Hai địa chỉ, hai quốc gia

Cho lớp nhúng:

~~~java
@Embeddable
public class PostalAddress {
    @Column(name = "street")
    private String street;

    @ManyToOne
    @JoinColumn(name = "country_id")
    private Country country;

    protected PostalAddress() {}
}
~~~

Một entity Customer nhúng **billingAddress** và **shippingAddress**. Schema muốn:

| Vai trò | Cột đường | Khóa ngoại quốc gia |
|---|---|---|
| billingAddress | billing_street | billing_country_id |
| shippingAddress | shipping_street | shipping_country_id |

**Yêu cầu:** thêm các annotation ghi đè cần thiết.

Lời giải minh họa (hai field trong entity Customer):

~~~java
@Embedded
@AttributeOverride(
    name = "street",
    column = @Column(name = "billing_street")
)
@AssociationOverride(
    name = "country",
    joinColumns = @JoinColumn(name = "billing_country_id")
)
private PostalAddress billingAddress;

@Embedded
@AttributeOverride(
    name = "street",
    column = @Column(name = "shipping_street")
)
@AssociationOverride(
    name = "country",
    joinColumns = @JoinColumn(name = "shipping_country_id")
)
private PostalAddress shippingAddress;
~~~

Đáp án dùng @AttributeOverride cho **street** và @AssociationOverride cho **country**. Nếu Country có khóa chính không phải cột ID mặc định, cần cấu hình referencedColumnName tương ứng.

### Bài 2: Ghi đè một quan hệ ở cấp lồng nhau

Cho mô hình:

~~~text
Invoice
 └── paymentDetails (@Embedded PaymentDetails)
      └── authorization (@Embedded Authorization)
           └── approvedBy (@ManyToOne UserAccount)
~~~

Yêu cầu trường khóa ngoại ở bảng Invoice phải tên **payment_approved_by_id**. Đặt annotation trên field **paymentDetails**, giá trị **name** phải là gì?

**Đáp án:**

~~~java
@Embedded
@AssociationOverride(
    name = "authorization.approvedBy",
    joinColumns = @JoinColumn(name = "payment_approved_by_id")
)
private PaymentDetails paymentDetails;
~~~

Đường dẫn bắt đầu ở **PaymentDetails**, vì annotation áp dụng trực tiếp trên **paymentDetails**.

### Bài 3: Hai tập thành viên

Một lớp nhúng **Audience** có quan hệ **@ManyToMany members**. Entity Campaign có **internalAudience** và **externalAudience**.

**Câu hỏi:** Dùng **joinColumns** hay **joinTable** để đặt hai bảng **campaign_internal_members** và **campaign_external_members**?

**Đáp án:** Dùng **joinTable** trong @AssociationOverride cho từng vị trí embedded. Trong @JoinTable phải cấu hình đúng **name**, **joinColumns**, **inverseJoinColumns**. **joinColumns** trực tiếp trên @AssociationOverride không diễn tả tên bảng liên kết.

### Bài 4: Nhận diện cấu hình không thể giải quyết bằng override

Một kiểu nhúng có:

~~~java
@ManyToOne(fetch = FetchType.EAGER, optional = false)
@JoinColumn(name = "manager_id", nullable = false)
private StaffMember manager;
~~~

Ở một entity, developer muốn quan hệ này thành **LAZY** và **optional = true**, nhưng chỉ cho phép thay annotation tại nơi @Embedded.

**Đáp án:** @AssociationOverride chỉ thay ánh xạ join, không thay **fetch** hay **optional**. Cần thiết kế lại kiểu nhúng/quan hệ hoặc điều chỉnh mapping gốc cho phù hợp với các use case.

### Bài 5: Khóa ngoại hai cột

Entity đích Customer có khóa ghép **tenant_id** và **customer_no**. Khi nhúng CustomerLink vào Invoice, hai cột khóa ngoại cần tên **invoice_tenant_id**, **invoice_customer_no**.

**Lời giải:**

~~~java
@AssociationOverride(
    name = "customer",
    joinColumns = {
        @JoinColumn(
            name = "invoice_tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @JoinColumn(
            name = "invoice_customer_no",
            referencedColumnName = "customer_no"
        )
    }
)
~~~

Phần quan hệ CustomerLink và khóa ghép của Customer vẫn phải được ánh xạ nhất quán với cấu trúc khóa đích.

## 18. Bảng ghi nhớ nhanh

| Nhu cầu | Cách ánh xạ |
|---|---|
| Thay tên cột khóa ngoại của quan hệ trong @Embeddable | @AssociationOverride(name = "...", joinColumns = @JoinColumn(...)) |
| Ghi đè nhiều quan hệ tại một vị trí embedded | @AssociationOverrides({...}) |
| Thay tên cột String, BigDecimal, LocalDate trong @Embeddable | @AttributeOverride(name = "...", column = @Column(...)) |
| Thay tên bảng trung gian của quan hệ ManyToMany | @AssociationOverride(..., joinTable = @JoinTable(...)) |
| Quan hệ nằm trong embeddable lồng nhau | Dùng đường dẫn thuộc tính với dấu chấm, ví dụ address.country |
| Hai field embedded cùng kiểu, cùng quan hệ | Mỗi field có override theo tên cột hoặc join table riêng |
| Quan hệ có khóa ngoại ghép | Khai báo nhiều @JoinColumn và referencedColumnName tương ứng |
| Muốn thay fetch, cascade, optional, cardinality | Sửa thiết kế hoặc khai báo quan hệ gốc; @AssociationOverride không làm việc này |
| Muốn truy vấn theo quan hệ đã override | Dùng JPQL dựa trên tên thuộc tính Java, ví dụ w.primaryAssignment.assignee.id |
| Schema production đã có cột khác | Cấu hình override khớp schema và quản lý migration nếu cần |

**Ghi đè ánh xạ quan hệ trong đối tượng nhúng** là công cụ giúp tái sử dụng một lớp **@Embeddable** chứa quan hệ entity mà vẫn ánh xạ đúng các khóa ngoại hoặc bảng liên kết của từng vị trí sử dụng. Hãy xác định chính xác **thuộc tính quan hệ**, **phía sở hữu**, **cấu trúc join**, **đường dẫn lồng nhau** và **ràng buộc của schema**. Khi phân biệt rõ @AssociationOverride với @AttributeOverride, bạn có thể thiết kế value object dùng lại mà vẫn giữ database mapping minh bạch và nhất quán.
