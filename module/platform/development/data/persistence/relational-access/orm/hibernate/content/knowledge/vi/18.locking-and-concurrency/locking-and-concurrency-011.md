# Bất biến giữa nhiều hàng và vai trò của ràng buộc cơ sở dữ liệu

Một hệ thống Hibernate có thể dùng entity, transaction và locking để cập nhật dữ liệu nhất quán. Nhưng khi một quy tắc nghiệp vụ phụ thuộc vào **nhiều hàng database**, chỉ kiểm tra điều kiện trong Java rồi ghi các entity thường chưa đủ. Hai transaction đồng thời có thể cùng đọc một trạng thái hợp lệ, mỗi transaction tự thấy mình được phép ghi, rồi kết hợp lại tạo ra trạng thái vi phạm quy tắc.

Quy tắc phải luôn đúng của dữ liệu được gọi là **invariant (bất biến)**. Ví dụ: một email chỉ thuộc về một tài khoản; một đơn hàng phải tham chiếu khách hàng tồn tại; một ghế chỉ được đặt một lần; tổng số chỗ đã giữ không vượt sức chứa; hai lịch đặt cùng tài nguyên không được chồng lấn. **Ràng buộc cơ sở dữ liệu** như primary key, unique, foreign key, check và exclusion constraint giúp bảo vệ các quy tắc này ngay tại nơi dữ liệu được ghi, kể cả khi có nhiều request, worker, ứng dụng hoặc script SQL cùng thao tác.

Bài học đặt chủ đề trong Hibernate ORM và chương **Khóa và đồng thời**. Trọng tâm là hiểu ranh giới giữa kiểm tra nghiệp vụ ở application, transaction isolation/locking và constraint thực thi tại database. Cú pháp SQL nâng cao có thể khác theo DBMS; ví dụ PostgreSQL được ghi rõ khi sử dụng tính năng riêng của hệ quản trị đó.

## 1. Invariant là gì và tại sao nhiều hàng làm bài toán khó hơn?

Một invariant là điều kiện mà dữ liệu phải thỏa mãn sau mọi transaction đã commit. Nó có thể liên quan tới:

- Một giá trị trên một hàng: số dư không âm, trạng thái thuộc tập giá trị hợp lệ.
- Nhiều hàng trong cùng bảng: email không trùng, một ghế không có hai lượt đặt đang hoạt động.
- Nhiều bảng: đơn hàng tham chiếu khách hàng tồn tại, mỗi chi tiết thuộc một đơn hàng.
- Một tập dữ liệu hoặc một aggregate: tổng số chỗ đặt không vượt sức chứa, tổng phân bổ ngân sách không vượt hạn mức.
- Một khoảng thời gian: hai lịch sử dụng cùng phòng không được chồng lấn.

Ví dụ hệ thống đặt phòng có sức chứa 10 người. Quy tắc:

~~~text
Số reservation đang hoạt động của một phòng <= capacity của phòng
~~~

Nếu chỉ có một request, logic đơn giản:

1. Đếm reservation đang hoạt động.
2. Nếu còn chỗ thì thêm reservation.
3. Commit.

Nhưng hai request chạy cùng lúc có thể cùng nhìn thấy 9 reservation, cùng kết luận còn một chỗ và cùng thêm một hàng. Sau hai commit, số reservation là 11.

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: COUNT active reservations = 9
    B->>DB: COUNT active reservations = 9
    A->>A: 9 < capacity 10, cho phép
    B->>B: 9 < capacity 10, cho phép
    A->>DB: INSERT reservation A
    B->>DB: INSERT reservation B
    A->>DB: COMMIT
    B->>DB: COMMIT
    Note over DB: Tổng reservation = 11, invariant bị phá vỡ
~~~

Đây là một dạng **race condition**. Mỗi transaction riêng lẻ đã chạy đúng đoạn kiểm tra của nó, nhưng việc xen kẽ các thao tác khiến kết quả tổng thể sai. Đây cũng là ví dụ gần với **write skew**: hai transaction dựa trên cùng một tập dữ liệu đọc được, rồi ghi các hàng khác nhau làm một invariant chung bị vi phạm.

### 1.1. Kiểm tra ở Java và bảo đảm ở database có vai trò khác nhau

| Cơ chế | Mục đích | Có bảo vệ mọi đường ghi không? |
| --- | --- | --- |
| Validation trong service | Trả thông báo nghiệp vụ dễ hiểu, từ chối sớm | Không; chỉ bảo vệ đường đi qua service đó |
| Hibernate mapping | Mô tả entity, association, nullability và metadata | Chỉ có hiệu lực vật lý khi schema thực thi ràng buộc tương ứng |
| Transaction | Nhóm thao tác thành một đơn vị commit/rollback | Không tự ngăn mọi race condition |
| Isolation/locking | Điều phối cách transaction đọc/ghi dữ liệu đồng thời | Có thể bảo vệ invariant nếu chọn đúng phạm vi và mọi writer tuân thủ |
| Database constraint | Từ chối trạng thái dữ liệu vi phạm ngay tại DB | Có; áp dụng cho các đường ghi chịu sự quản lý của constraint |
| Trigger/stored procedure | Thực thi logic dữ liệu ở DB khi constraint chuẩn chưa đủ | Có thể áp dụng tập trung, nhưng cần thiết kế và kiểm thử cẩn thận |

Thiết kế tốt thường kết hợp nhiều lớp: application kiểm tra để đưa ra phản hồi thân thiện; transaction/locking kiểm soát đồng thời; database constraint làm hàng rào cuối cho các invariant mà DB có thể biểu đạt.

## 2. Phân loại invariant để chọn đúng ràng buộc

Không phải mọi quy tắc nghiệp vụ đều có thể đặt trong một `CHECK`. Trước khi viết Hibernate annotation hay SQL, hãy xác định quy tắc thuộc nhóm nào.

| Loại invariant | Ví dụ | Cơ chế database thường dùng |
| --- | --- | --- |
| Định danh duy nhất | Hai tài khoản không có cùng ID | `PRIMARY KEY` |
| Giá trị business key duy nhất | Email không trùng | `UNIQUE` hoặc unique index |
| Tham chiếu hợp lệ | `purchase_orders.customer_id` phải tồn tại | `FOREIGN KEY` |
| Giá trị trên một hàng hợp lệ | `quantity > 0` | `CHECK` và `NOT NULL` nếu cần |
| Kết hợp nhiều cột duy nhất | Mỗi sản phẩm chỉ có một dòng trong mỗi kho | `UNIQUE(warehouse_id, product_id)` |
| Không chồng lấn | Hai booking cùng phòng không giao nhau về thời gian | Exclusion constraint hoặc cơ chế locking/kiểm tra phù hợp |
| Giới hạn tổng hợp qua nhiều hàng | Tổng reservation không vượt capacity | Khóa hàng cha, cập nhật counter nguyên tử, serializable hoặc mô hình dữ liệu khác |
| Quy tắc liên bảng phức tạp | Parent phải có ít nhất một child | Transaction/application logic, trigger hoặc mô hình schema thích hợp |

**Chọn cơ chế gần với invariant nhất.** Nếu quy tắc chỉ là một cột phải dương, dùng CHECK. Nếu là unique theo hai cột, dùng unique constraint ghép. Nếu là tổng số hàng phải nhỏ hơn capacity, một CHECK trên từng reservation không thể đếm các hàng còn lại; phải thiết kế cơ chế đồng thời khác.

## 3. Những constraint cơ bản và ý nghĩa trong Hibernate

### 3.1. Primary key: một định danh duy nhất

`PRIMARY KEY` đảm bảo mỗi hàng có một định danh duy nhất và không null. Hibernate khai báo bằng `@Id` hoặc `@EmbeddedId`:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected Customer() {}
}
~~~

Hibernate cần primary key để quản lý entity identity trong persistence context, tạo association và cập nhật/xóa hàng. Tuy nhiên, identity map của một `Session` không thay thế primary key vật lý. Nếu database không có constraint phù hợp hoặc có đường ghi ngoài ORM, tính duy nhất vẫn phải được bảo vệ tại DB.

### 3.2. Unique constraint: duy nhất theo một hoặc nhiều cột

Một email không được dùng cho hai tài khoản:

~~~java
@Entity
@Table(
    name = "accounts",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_accounts_email",
            columnNames = "email"
        )
    }
)
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 254)
    private String email;

    protected Account() {}
}
~~~

Hoặc SQL migration:

~~~sql
alter table accounts
add constraint uk_accounts_email unique (email);
~~~

Nếu unique key gồm nhiều cột:

~~~java
@Entity
@Table(
    name = "warehouse_stock",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_stock_warehouse_product",
        columnNames = {"warehouse_id", "product_id"}
    )
)
public class WarehouseStock {
    @Id
    private Long id;

    @Column(name = "warehouse_id", nullable = false)
    private Long warehouseId;

    @Column(name = "product_id", nullable = false)
    private Long productId;
}
~~~

Điều này bảo đảm mỗi cặp warehouse/product chỉ có tối đa một hàng. Không thể thay nó bằng code kiểu `if (repository.existsByEmail(email)) ... save()` rồi cho rằng an toàn trước hai request đồng thời.

**Null và UNIQUE:** cách DBMS xử lý nhiều giá trị null trong unique constraint có khác biệt giữa các hệ quản trị và có thể có tùy chọn riêng. Nếu email bắt buộc, kết hợp `NOT NULL` với `UNIQUE` thay vì dựa vào hành vi null mặc định.

### 3.3. Foreign key: bảo đảm tham chiếu có thật

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_order_customer")
    )
    private Customer customer;
}
~~~

FK trong DB bảo đảm mỗi `customer_id` khác null phải tham chiếu hàng customer hợp lệ. `optional = false` và `nullable = false` mô tả mapping/DDL, nhưng schema đang chạy phải thực sự có constraint và cột NOT NULL. Annotation không tự sửa database legacy.

Foreign key không chỉ ngăn orphan reference; nó còn quy định hành vi khi xóa hoặc đổi khóa cha, tùy `ON DELETE`/`ON UPDATE` và DBMS. Hibernate cascade là cơ chế vòng đời entity ở ORM, không đồng nghĩa với FK constraint hoặc `ON DELETE CASCADE`.

### 3.4. Check constraint: kiểm tra điều kiện trên một hàng

Ví dụ quantity phải dương và discount nằm trong khoảng hợp lệ:

~~~sql
create table order_items (
    id bigint primary key,
    quantity integer not null,
    discount_percent numeric(5,2) not null,
    constraint ck_item_quantity_positive
        check (quantity > 0),
    constraint ck_item_discount_range
        check (discount_percent >= 0
           and discount_percent <= 100)
);
~~~

Hibernate có annotation riêng `org.hibernate.annotations.Check` trong các phiên bản hỗ trợ:

~~~java
import org.hibernate.annotations.Check;

@Entity
@Table(name = "order_items")
@Check(
    constraints = "quantity > 0 and discount_percent between 0 and 100"
)
public class OrderItem {
    @Id
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "discount_percent", nullable = false)
    private BigDecimal discountPercent;
}
~~~

`@Check` là Hibernate-specific, còn `CHECK` là constraint SQL. Với schema được quản lý bằng Flyway/Liquibase, nên tạo constraint bằng migration và giữ mapping nhất quán. `CHECK` thường đánh giá biểu thức trên **một hàng đang được insert/update**; nó không phải công cụ portable để chạy `COUNT(*)` qua bảng khác hoặc so tổng nhiều hàng.

Cũng cần chú ý logic ba giá trị của SQL: biểu thức CHECK thường không bị vi phạm khi kết quả là UNKNOWN do NULL, tùy quy tắc DBMS. Nếu cột bắt buộc, khai báo `NOT NULL` riêng.

### 3.5. Exclusion constraint và index đặc thù

Một quy tắc “hai booking của cùng phòng không được chồng thời gian” không chỉ là kiểm tra `start_at < end_at` trên một hàng. Nó so khoảng thời gian của một hàng với nhiều hàng khác.

PostgreSQL có **exclusion constraint** với range operators; ví dụ khái niệm:

~~~sql
-- PostgreSQL-specific; ví dụ cần extension/operator class phù hợp.
create extension if not exists btree_gist;

alter table room_bookings
add constraint ex_room_booking_no_overlap
exclude using gist (
    room_id with =,
    tstzrange(start_at, end_at, '[)') with &&
)
where (status = 'CONFIRMED');
~~~

Constraint này từ chối hai hàng đã xác nhận nếu cùng `room_id` và khoảng thời gian giao nhau. Đây là tính năng PostgreSQL-specific, cần xem version, extension và kiểu cột; không thể chép nguyên SQL sang mọi DBMS.

Nếu DBMS không có exclusion constraint, cần cơ chế locking/transaction thích hợp hoặc một mô hình khác như slot table với unique key. Kiểm tra overlap trong Java đơn thuần có race condition giống bài toán capacity.

## 4. Tại sao check-then-act không an toàn?

Một đoạn service thường thấy:

~~~java
@Transactional
public void registerEmail(String email) {
    if (accountRepository.existsByEmail(email)) {
        throw new EmailAlreadyUsedException(email);
    }

    accountRepository.save(new Account(email));
}
~~~

Đoạn code dễ hiểu và hữu ích để trả lỗi sớm, nhưng không bảo đảm uniqueness khi concurrency:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Database
    participant B as Request B
    A->>DB: SELECT exists(email) → false
    B->>DB: SELECT exists(email) → false
    A->>DB: INSERT account(email)
    B->>DB: INSERT account(email)
    A->>DB: COMMIT
    B->>DB: COMMIT
    Note over DB: Không có UNIQUE thì email bị trùng
~~~

Nếu DB có unique constraint, một insert thành công; insert còn lại bị từ chối. Ứng dụng có thể bắt lỗi tại transaction boundary và chuyển thành thông báo “email đã được sử dụng”.

**Kiểm tra trước constraint vẫn hữu ích** vì phản hồi thân thiện và tránh thao tác vô ích. Nhưng unique constraint là thứ bảo vệ invariant khi hai request cùng đi qua bước kiểm tra.

### 4.1. Phân biệt business validation và database guarantee

~~~java
@Transactional
public void registerEmail(String email) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }

    // Kiểm tra sớm giúp thông báo rõ ràng.
    if (accountRepository.existsByEmail(email)) {
        throw new EmailAlreadyUsedException(email);
    }

    accountRepository.save(new Account(email));
}
~~~

Service vẫn nên validate format, normalize email theo quy tắc domain và kiểm tra quyền. DB unique constraint đảm bảo không có hai hàng vi phạm key đã định nghĩa. Cần thống nhất **chuẩn hóa**: nếu domain xem `User@Example.com` và `user@example.com` là cùng địa chỉ, constraint phải dùng biểu diễn normalized hoặc collation/index phù hợp. Unique trên raw text có thể không tương ứng với business equality.

### 4.2. Khi constraint vi phạm, lỗi có thể chỉ xuất hiện ở flush/commit

Hibernate có thể chưa gửi `INSERT` tại lời gọi repository save/persist. SQL thường được gửi ở flush hoặc commit, dù IDENTITY hoặc thao tác cụ thể có thể buộc phát sớm. Vì vậy:

~~~java
try {
    service.registerEmail(email);
} catch (DataIntegrityViolationException ex) {
    // Xử lý ở phía ngoài transaction boundary phù hợp.
}
~~~

Cách catch thực tế phụ thuộc Spring transaction proxy và repository. Không nuốt constraint exception bên trong transaction rồi tiếp tục dùng cùng persistence context; sau lỗi ghi, transaction có thể rollback-only và Session không nên tái sử dụng.

## 5. Invariant nhiều hàng: tổng reservation không vượt capacity

Đây là ví dụ điển hình mà CHECK đơn giản không đủ.

### 5.1. Mô hình bảng

~~~sql
create table rooms (
    id bigint primary key,
    capacity integer not null,
    reserved_count integer not null default 0,
    constraint ck_room_capacity_nonnegative
        check (capacity >= 0),
    constraint ck_room_reserved_within_capacity
        check (reserved_count >= 0
           and reserved_count <= capacity)
);

create table reservations (
    id bigint primary key,
    room_id bigint not null references rooms(id),
    guest_name varchar(120) not null,
    status varchar(20) not null
);
~~~

CHECK trên `rooms` bảo đảm `reserved_count` không vượt `capacity` **trên hàng rooms đó**. Nó không chứng minh `reserved_count` bằng số reservation thực tế. Đó là một invariant liên bảng cần quy trình cập nhật đồng bộ, trigger hoặc một mô hình khác.

Nếu mỗi request chỉ chạy:

~~~sql
select count(*)
from reservations
where room_id = :roomId
  and status = 'ACTIVE';
~~~

rồi insert nếu count nhỏ hơn capacity, hai transaction vẫn có thể cùng thấy một chỗ cuối. Phải **tuần tự hóa hoặc nguyên tử hóa** thao tác kiểm tra và chiếm chỗ.

### 5.2. Cách A: khóa hàng cha rồi kiểm tra và ghi

Trong Hibernate/JPA, có thể khóa row `Room` bằng pessimistic write lock:

~~~java
import jakarta.persistence.LockModeType;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;

@Transactional
public void reserve(long roomId, String guestName) {
    Room room = entityManager.find(
        Room.class,
        roomId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (room == null) {
        throw new RoomNotFoundException(roomId);
    }

    long activeCount = entityManager.createQuery(
        "select count(r) from Reservation r " +
        "where r.room.id = :roomId and r.status = :status",
        Long.class
    )
    .setParameter("roomId", roomId)
    .setParameter("status", ReservationStatus.ACTIVE)
    .getSingleResult();

    if (activeCount >= room.getCapacity()) {
        throw new RoomFullException(roomId);
    }

    entityManager.persist(
        new Reservation(room, guestName, ReservationStatus.ACTIVE)
    );
}
~~~

`Room`, `Reservation`, enum và exception là các kiểu domain minh họa. Import transaction annotation trong dự án Spring thường là `org.springframework.transaction.annotation.Transactional`; ví dụ dùng annotation JTA ở trên chỉ nhằm nhấn mạnh transaction boundary và cần chọn đúng API theo runtime.

Ý tưởng:

1. Mỗi request khóa cùng hàng `rooms(id)`.
2. Transaction thứ hai phải chờ transaction thứ nhất nhả lock.
3. Transaction đầu đếm và insert reservation rồi commit.
4. Transaction sau mới lấy được lock, sau đó đọc trạng thái đã commit và đếm lại.
5. Nếu capacity đã đầy, request sau từ chối.

**Điều kiện quan trọng:** tất cả đường ghi reservation phải tuân thủ quy ước khóa cùng hàng cha **trước khi** đếm/ghi. Nếu một batch job hoặc ứng dụng khác insert trực tiếp mà không khóa room, invariant vẫn có thể bị phá. Khóa parent row là một **protocol đồng thời ở application**, không tự tạo ra constraint tổng hợp tại DB.

Với thao tác khóa nhiều phòng, nên lấy khóa theo thứ tự ID nhất quán để giảm deadlock. Lock timeout/deadlock phải được xử lý bằng transaction mới và retry có giới hạn nếu nghiệp vụ cho phép.

### 5.3. Cách B: optimistic locking trên hàng aggregate

Một lựa chọn là giữ counter trên `Room` và dùng `@Version`:

~~~java
@Entity
@Table(name = "rooms")
public class Room {
    @Id
    private Long id;

    @Column(nullable = false)
    private int capacity;

    @Column(name = "reserved_count", nullable = false)
    private int reservedCount;

    @Version
    private long version;

    public boolean hasSpace() {
        return reservedCount < capacity;
    }

    public void reserveOne() {
        if (!hasSpace()) {
            throw new IllegalStateException("Room is full");
        }
        reservedCount++;
    }

    public int getCapacity() { return capacity; }
    public int getReservedCount() { return reservedCount; }
}
~~~

Trong transaction:

~~~java
@Transactional
public void reserve(long roomId, String guestName) {
    Room room = entityManager.find(Room.class, roomId);

    if (room == null) {
        throw new RoomNotFoundException(roomId);
    }

    room.reserveOne();
    entityManager.persist(new Reservation(room, guestName));
}
~~~

Hai transaction cùng tải `Room` version 4 và cùng tăng counter từ 9 lên 10. Khi commit, cả hai cố cập nhật cùng row với điều kiện version cũ. Một transaction cập nhật thành công và tăng version; transaction còn lại không còn hàng khớp version cũ và gặp optimistic-lock conflict. Toàn bộ transaction thất bại phải rollback, bao gồm reservation insert của nó.

Cách này yêu cầu **mọi thao tác làm thay đổi số reservation đều cập nhật cùng hàng Room** và version. Nếu chỉ đếm child rows mà không dirty parent, `@Version` trên Room không bảo vệ được invariant.

Sau optimistic-lock conflict, nếu retry được, phải mở transaction mới, tải Room/version mới và tính lại điều kiện. Không retry bằng entity/context đã thất bại.

### 5.4. Cách C: cập nhật có điều kiện nguyên tử

Một câu SQL có thể kết hợp kiểm tra capacity với cập nhật counter:

~~~sql
update rooms
set reserved_count = reserved_count + 1,
    version = version + 1
where id = :roomId
  and reserved_count < capacity;
~~~

Nếu số hàng cập nhật là 1, đã chiếm được một chỗ; nếu là 0, phòng không tồn tại hoặc đã đầy. Câu UPDATE là một thao tác nguyên tử ở DBMS: hai request không thể cùng thành công trên một giá trị counter cuối cùng nếu điều kiện đã hết chỗ.

Sau đó insert reservation trong **cùng transaction**:

~~~text
BEGIN
  UPDATE rooms ... WHERE reserved_count < capacity
  nếu updateCount != 1: báo hết chỗ
  INSERT reservations(...)
COMMIT
~~~

Nếu insert child thất bại, rollback sẽ hoàn tác cả việc tăng counter. Nếu dùng bulk/native update trong một Hibernate persistence context đã load Room, entity Room có thể giữ counter/version cũ vì bulk DML không tự đồng bộ state managed. Cần flush trước thao tác và clear/refresh hoặc tránh giữ entity stale trong context, theo cách tích hợp cụ thể.

Counter này vẫn cần invariant phụ: `reserved_count` phải bằng số reservation active. Đảm bảo nó bằng cách cho mọi create/cancel/reactivate đi qua cùng transaction protocol, hoặc thực thi bằng trigger/stored procedure phù hợp. Nếu các đường ghi ngoài ứng dụng không thể tuân thủ, hãy cân nhắc mô hình slot/constraint thay thế.

### 5.5. Cách D: biểu diễn chỗ ngồi thành từng slot có unique key

Nếu phòng có 10 ghế đánh số từ 1 đến 10, có thể tạo 10 slot rows:

~~~sql
create table room_slots (
    room_id bigint not null references rooms(id),
    slot_number integer not null,
    reservation_id bigint unique,
    primary key (room_id, slot_number)
);
~~~

Một slot chỉ có một hàng cho mỗi cặp room/seat. Hai request cùng chiếm ghế số 5 không thể tạo hai slot row có cùng PK. Nếu cập nhật `reservation_id` từ null, có thể dùng câu lệnh có điều kiện:

~~~sql
update room_slots
set reservation_id = :reservationId
where room_id = :roomId
  and slot_number = :slotNumber
  and reservation_id is null;
~~~

Chỉ một transaction có thể cập nhật slot còn trống thành công. Đây là cách **mô hình hóa invariant bằng cấu trúc dữ liệu**, thay vì đếm một tập hàng. Nó phù hợp khi domain thật sự có slot/tài nguyên rời rạc; không phải mọi capacity dạng số đều nên chuyển thành hàng slot.

## 6. Vì sao @Version trên một entity không tự bảo vệ mọi invariant?

`@Version` hỗ trợ optimistic locking cho **hàng/entity được version hóa**. Nó không tự hiểu mọi quy tắc aggregate.

Ví dụ, một phòng có 10 reservation và hai transaction thêm hai reservation khác nhau. Nếu mỗi transaction chỉ insert một `Reservation` và không cập nhật `Room`, cả hai có thể commit vì không đụng cùng row/version.

~~~text
Room#7 (capacity=10, version=4)
Reservations active = 9

Tx A: đọc count=9, insert Reservation#A
Tx B: đọc count=9, insert Reservation#B

Hai transaction ghi hai row Reservation khác nhau.
Không có update Room => Room.version không đổi.
~~~

**Version chỉ có tác dụng khi các thao tác cạnh tranh thực sự cập nhật/kiểm tra cùng entity version.** Nếu invariant liên quan tới một aggregate root, có thể buộc mọi thay đổi child đi qua cập nhật root/counter hoặc khóa root. Đây là một quy ước kiến trúc cần áp dụng thống nhất.

### 6.1. Khi nào optimistic locking đủ?

- Tất cả thay đổi liên quan đều cập nhật cùng row version.
- Transaction xử lý conflict bằng cách rollback và tải lại trạng thái.
- Không có đường ghi ngoài ORM bỏ qua version.
- Invariant có thể được biểu diễn qua trạng thái aggregate đã tải và cập nhật.

### 6.2. Khi nào cần constraint DB hoặc isolation mạnh hơn?

- Có nhiều ứng dụng/script cùng ghi.
- Quy tắc unique/foreign key có thể diễn đạt bằng constraint.
- Invariant phụ thuộc nhiều row nhưng không có aggregate root chung để version hóa.
- Có nguy cơ write skew dù mỗi transaction cập nhật các row riêng.
- Cần bảo vệ ngay cả khi application code bị lỗi.

## 7. Isolation level, write skew và phantom rows

Transaction isolation quyết định những thay đổi nào một transaction có thể quan sát từ transaction khác. Mức isolation mạnh hơn có thể ngăn một số anomalies nhưng không phải mọi DBMS triển khai giống nhau.

| Isolation level (tên phổ biến) | Khái niệm khái quát | Lưu ý |
| --- | --- | --- |
| READ UNCOMMITTED | Có thể cho phép dirty read trong hệ quản trị hỗ trợ | Nhiều DBMS không triển khai đúng theo nghĩa này hoặc dùng cách khác |
| READ COMMITTED | Mỗi statement đọc dữ liệu đã commit theo quy tắc DBMS | Hai statement trong một transaction có thể thấy snapshot khác nhau |
| REPEATABLE READ | Bảo vệ tính lặp lại của các lần đọc theo semantics DBMS | Không phải mọi implementation đều ngăn phantom/write skew |
| SERIALIZABLE | DBMS cố đảm bảo kết quả tương đương một thứ tự tuần tự | Có thể abort transaction; application phải xử lý serialization failure/retry |

### 7.1. Write skew

Một phòng có quy tắc ít nhất một bác sĩ phải trực. Hai bác sĩ A và B đang trực; mỗi transaction đọc thấy có hai người. Transaction A tắt lịch trực của A, transaction B tắt lịch trực của B. Hai transaction cập nhật **hai hàng khác nhau**, nên một optimistic version trên từng bác sĩ không phát hiện xung đột. Kết quả không còn ai trực.

Đây là ví dụ write skew. Có thể giải quyết bằng cách:

- Đặt invariant ở một hàng aggregate/root chung và version/lock hàng đó.
- Dùng khóa phạm vi phù hợp trước khi đọc/ghi.
- Dùng SERIALIZABLE nếu DBMS/driver hỗ trợ semantics cần thiết, rồi xử lý transaction bị abort.
- Mô hình hóa trạng thái để dùng constraint unique/check phù hợp.
- Dùng stored procedure/trigger nếu invariant cần được thực thi tập trung tại DB.

Không chọn SERIALIZABLE chỉ vì tên nghe “an toàn nhất”; cần xem lock contention, retry rate, query plan và khả năng triển khai của DBMS. Một transaction SERIALIZABLE vẫn có thể thất bại và cần được chạy lại từ đầu với transaction mới.

### 7.2. Phantom rows

Một transaction đếm các reservation active. Transaction khác chèn một hàng mới phù hợp điều kiện. Hàng mới là **phantom** đối với tập kết quả của truy vấn ban đầu.

Locking một row reservation hiện có không nhất thiết ngăn insert thêm một row mới. Cần khóa một parent row chung, dùng range/predicate locking nếu DBMS hỗ trợ, SERIALIZABLE, constraint hoặc mô hình khác. Không giả định `PESSIMISTIC_WRITE` trên một entity bất kỳ tự khóa mọi hàng tương lai thỏa điều kiện truy vấn.

## 8. Pessimistic locking trong Hibernate/JPA

JPA cung cấp `LockModeType.PESSIMISTIC_READ` và `PESSIMISTIC_WRITE`. Hibernate chuyển chúng thành locking phù hợp dialect/DBMS, thường dùng SQL như `SELECT ... FOR UPDATE` khi được hỗ trợ.

~~~java
Room room = entityManager.find(
    Room.class,
    roomId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Lock được giữ theo transaction và DBMS quyết định chính sách blocking/timeout. Nó hữu ích khi nhiều transaction cần đồng bộ qua cùng hàng guard.

### 8.1. Lock một hàng không đồng nghĩa lock toàn bộ invariant

Nếu invariant là “không có hai booking trùng khoảng thời gian”, lock một booking hiện có có thể không chặn một booking mới cùng khoảng. Nếu không có hàng guard chung, hai transaction vẫn có thể cùng thấy không có booking xung đột.

Có thể khóa hàng resource/room trước khi kiểm tra overlap, và bắt buộc tất cả thao tác booking dùng cùng protocol. Hoặc dùng exclusion constraint/serializable phù hợp DBMS. Chọn cách dựa trên khả năng kiểm soát mọi writer.

### 8.2. Lock timeout và deadlock

Khi lock không lấy được trong thời hạn, Hibernate/JPA có thể báo lock timeout hoặc exception liên quan; deadlock do DBMS phát hiện cũng có thể làm transaction thất bại. Sau lỗi transaction, rollback và bỏ persistence context bị ảnh hưởng. Nếu retry, dùng transaction mới, backoff và giới hạn số lần thử.

Nếu một thao tác khóa nhiều hàng, giữ thứ tự lock nhất quán (ví dụ tăng dần theo ID) giúp giảm deadlock. Transaction nên ngắn; không chờ người dùng hoặc gọi HTTP bên ngoài trong lúc giữ DB lock nếu không cần.

## 9. Các constraint ghép và invariant nghiệp vụ

### 9.1. Unique ghép

Mỗi sản phẩm chỉ có một hàng tồn kho trong mỗi kho:

~~~sql
alter table warehouse_stock
add constraint uk_stock_warehouse_product
unique (warehouse_id, product_id);
~~~

Đây là cách bảo vệ tự nhiên cho invariant “một cặp khóa chỉ có một hàng”. Trong Hibernate, dùng `@Table(uniqueConstraints = ...)` để mô tả DDL nếu schema do Hibernate tạo; production migration nên là nguồn sự thật của schema.

### 9.2. Unique có điều kiện (partial/filtered unique index)

Một người dùng chỉ có một phiên đăng nhập đang hoạt động cho mỗi thiết bị:

~~~sql
-- PostgreSQL-specific partial unique index.
create unique index uq_active_device_session
on device_sessions(user_id, device_id)
where status = 'ACTIVE';
~~~

Index này chỉ áp dụng cho hàng có status ACTIVE. SQL Server có filtered index và các DBMS khác có cách riêng; đây không phải cú pháp JPA portable. Annotation `@UniqueConstraint` thông thường không biểu diễn predicate partial index. Tạo bằng migration và kiểm tra đúng DBMS.

### 9.3. No-overlap constraint

Với lịch đặt phòng, một CHECK `start_at < end_at` chỉ kiểm tra mỗi khoảng tự hợp lệ. Nó không bảo đảm khoảng này không chồng khoảng của một hàng khác. Cần exclusion constraint, khóa resource row trước khi tìm khoảng xung đột, hoặc cơ chế SERIALIZABLE/predicate locking theo DBMS.

### 9.4. Tổng tiền đơn hàng và các dòng chi tiết

Invariant “order.total = sum(order_items.line_total)” trải qua nhiều hàng/bảng. Một CHECK trên `orders.total` không thể đơn giản truy vấn bảng child trong SQL chuẩn. Một số phương án:

- Tính tổng ở application khi thay đổi line items và cập nhật `orders.total` trong cùng transaction.
- Dùng trigger/stored procedure để đồng bộ tổng tại DB nếu cần mọi writer đều tuân thủ.
- Không lưu tổng, mà tính bằng query khi đọc nếu chi phí phù hợp.
- Dùng materialized/derived data có quy trình refresh và reconciliation.
- Dùng aggregate root lock/version để tuần tự hóa thay đổi line items.

Nếu giữ tổng được tính sẵn, phải bảo đảm mọi thao tác thêm, sửa, xóa item đều cập nhật tổng trong cùng transaction. Một batch import bypass service có thể khiến tổng sai nếu không có constraint/trigger khác bảo vệ.

## 10. Constraint được khai báo trong Hibernate có bảo đảm database đã có chưa?

Không nhất thiết. Cần phân biệt **mapping metadata**, **DDL generation** và **schema thật đang chạy**.

| Khai báo | Ý nghĩa mapping/DDL | Điều phải kiểm tra |
| --- | --- | --- |
| `@Column(nullable = false)` | Mô tả cột không null | Cột thật có NOT NULL không? |
| `@Column(unique = true)` | Gợi ý unique constraint đơn cột cho schema generation | Constraint/index thật có tồn tại và hợp với normalization không? |
| `@Table(uniqueConstraints = ...)` | Mô tả unique constraint nhiều cột cho DDL | Migration đã tạo đúng thứ tự/cột/tên chưa? |
| `@JoinColumn(foreignKey = ...)` | Mô tả FK khi tạo schema | DB thật có FK đang enabled/validated không? |
| Hibernate `@Check` | Mô tả check constraint trong schema generation | Migration và DBMS có thực thi biểu thức tương ứng không? |
| `@Version` | ORM optimistic locking metadata | Mọi đường ghi có tôn trọng version không? Bulk/native SQL có bypass không? |

Nếu dùng Flyway/Liquibase, migration là nơi quản lý schema. Thêm annotation trong entity không tự thay đổi một database production đã tồn tại, trừ khi có quy trình schema update tương ứng và được phép chạy. Không nên dựa vào `hbm2ddl.auto=update` để thay thế migration phức tạp.

### 10.1. Constraint có thể chưa được validate

Một số DBMS hỗ trợ tạo constraint ở trạng thái chưa validate dữ liệu cũ rồi xác thực sau; cách làm và semantics khác nhau. Ví dụ PostgreSQL có `NOT VALID` cho một số constraint như FK/CHECK, sau đó `VALIDATE CONSTRAINT`. Việc constraint chưa validate không có nghĩa dữ liệu cũ đã hợp lệ; cần theo dõi migration và trạng thái constraint rõ ràng.

## 11. Xử lý constraint violation trong Hibernate

Một câu lệnh persist có thể chưa gửi SQL ngay. Constraint violation có thể xuất hiện khi:

- Hibernate phát insert/update sớm để lấy generated ID.
- `flush()` được gọi tường minh.
- Query cần auto-flush theo flush mode.
- Transaction commit kích hoạt flush.

Ví dụ:

~~~java
@Transactional
public void createAccount(String email) {
    Account account = new Account(email);
    entityManager.persist(account);
    // Lỗi UNIQUE có thể phát sinh khi flush/commit sau đó.
}
~~~

Nếu muốn biết lỗi ở phạm vi service khi phát triển hoặc cần trả kết quả ngay, có thể gọi `entityManager.flush()` một cách có chủ đích; nhưng nó **không commit transaction**. Constraint vẫn được database kiểm tra.

Sau khi DB từ chối SQL/flush, transaction có thể rollback-only/aborted và Session không còn thích hợp để tái sử dụng. Để xử lý:

1. Để transaction kết thúc bằng rollback.
2. Đóng/bỏ persistence context bị ảnh hưởng theo transaction management.
3. Phân loại constraint theo tên, SQLState/vendor code hoặc cause chain.
4. Chuyển lỗi sang thông báo nghiệp vụ phù hợp (ví dụ email đã tồn tại) nếu đó là kết quả dự kiến.
5. Nếu retry có ý nghĩa, bắt đầu transaction và persistence context mới, tải lại dữ liệu và tính lại điều kiện.

**Không nuốt constraint exception rồi tiếp tục ghi các entity khác trong cùng transaction/session** như thể row lỗi đã bị bỏ khỏi action queue.

### 11.1. Đừng dùng exception message làm hợp đồng

Một `ConstraintViolationException` có thể đại diện cho FK, UNIQUE, CHECK hoặc NOT NULL. Spring có thể chuyển thành `DataIntegrityViolationException`; JPA/Hibernate có thể bọc trong `PersistenceException` và `SQLException`. Tên exception và message phụ thuộc integration/driver/DBMS.

Nếu cần phân loại, đặt tên constraint ổn định trong migration và xem cause chain/SQLState. Không trả tên bảng nội bộ hoặc SQL đầy đủ cho client.

### 11.2. Phân biệt DB constraint với Bean Validation

`jakarta.validation.ConstraintViolationException` từ Bean Validation (ví dụ `@NotNull`, `@Size`) là lỗi kiểm tra object ở tầng Java. `org.hibernate.exception.ConstraintViolationException` là lỗi constraint database/JDBC được Hibernate chuyển đổi. Hai loại khác nguồn và thời điểm.

Bean Validation giúp phản hồi sớm; database constraint bảo vệ dữ liệu trước race condition và writer khác. Không dùng một loại để thay thế loại còn lại.

## 12. Transaction và constraint: ai chịu trách nhiệm điều gì?

Một invariant nên được bảo vệ trong một transaction có ranh giới rõ. Ví dụ chuyển tiền giữa hai tài khoản:

~~~text
BEGIN
  debit account A
  credit account B
  write transfer record
COMMIT
~~~

Nếu bước credit hoặc ghi transfer thất bại, rollback phải hoàn tác debit trong cùng transaction. Một `CHECK(balance >= 0)` trên từng account giúp ngăn số dư âm nếu mọi cập nhật phải đi qua DB constraint. Nhưng việc bảo đảm tổng tiền hai tài khoản không đổi vẫn phụ thuộc transaction và logic chuyển tiền: database không tự hiểu rằng hai hàng là hai vế của một nghiệp vụ.

### 12.1. Cập nhật có điều kiện thay vì đọc rồi ghi

Trừ tiền không cho phép âm:

~~~sql
update accounts
set balance = balance - :amount,
    version = version + 1
where id = :accountId
  and balance >= :amount;
~~~

Nếu update count là 0, có thể tài khoản không tồn tại hoặc số dư không đủ. Câu update có điều kiện tránh race kiểu đọc số dư rồi trừ sau. Kết hợp `CHECK(balance >= 0)` để bảo vệ invariant ở DB nếu mọi đường ghi áp dụng cùng schema.

Với chuyển tiền, cần cập nhật cả hai tài khoản trong **một transaction**, xử lý trường hợp hai ID trùng, lock/update theo thứ tự ổn định và ghi transfer record. Nếu dùng native SQL/bulk update bên dưới Hibernate, phải quản lý persistence context stale state và version một cách tường minh.

### 12.2. Transaction atomicity không tự ngăn mọi race

Một transaction bảo đảm nhóm thao tác commit hoặc rollback theo atomicity. Nhưng hai transaction đều atomic vẫn có thể cùng làm sai invariant nếu isolation/locking/constraint không đủ. Đừng kết luận “đã có @Transactional nên không cần unique/FK/locking”.

## 13. Trigger và stored procedure: khi constraint chuẩn không đủ

Một số invariant thực sự phụ thuộc nhiều bảng hoặc phép tổng hợp. Nếu tất cả writer phải được bảo vệ và DBMS không thể biểu diễn bằng unique/check/FK/exclusion constraint, có thể dùng:

- **Trigger:** chạy khi insert/update/delete, kiểm tra hoặc cập nhật dữ liệu liên quan.
- **Stored procedure:** gom thao tác dữ liệu và invariant vào một API database có quyền thực thi được kiểm soát.
- **Aggregate guard row/counter:** mọi thay đổi khóa cùng một hàng để tuần tự hóa.
- **Reconciliation job:** phát hiện lệch dữ liệu còn sót lại và cảnh báo/sửa theo quy trình.

Các giải pháp này có trade-off:

- Logic nằm trong DB có thể khó chia sẻ/kiểm thử nếu ứng dụng hỗ trợ nhiều DBMS.
- Trigger có thể tạo side effect ẩn và làm SQL của Hibernate khó dự đoán.
- Thứ tự trigger, deadlock và recursion cần được kiểm soát.
- Counter/denormalized aggregate cần mọi đường ghi cập nhật đúng.
- Reconciliation phát hiện sau khi dữ liệu sai; nó không thay thế bảo vệ đồng bộ nếu invariant phải luôn đúng.

Ưu tiên constraint declarative đơn giản trước. Chỉ dùng trigger/procedure khi invariant thực sự cần và có người chịu trách nhiệm quản lý logic DB.

## 14. Mô hình hóa để constraint trở nên đơn giản hơn

Đôi khi cách tốt nhất là thay cấu trúc dữ liệu.

Ví dụ “mỗi người chỉ có một booking đang hoạt động cho một tài nguyên” có thể dùng partial unique index. “Một ghế chỉ có một booking” có thể dùng bảng slot với PK ghép. “Một phòng chỉ còn N chỗ” có thể dùng counter/guard row được cập nhật nguyên tử.

| Invariant khó diễn đạt | Thay đổi mô hình có thể giúp |
| --- | --- |
| Tổng reservation không vượt capacity | Lưu counter trên room và constraint `reserved_count <= capacity`; hoặc mô hình từng slot |
| Không trùng tài nguyên đang active | Partial/filtered unique index theo status |
| Không chồng thời gian | Exclusion constraint hoặc lock resource trước khi kiểm tra |
| Một parent phải có ít nhất một child | Quy trình tạo aggregate trong transaction, trigger hoặc thiết kế parent state rõ ràng |
| Tổng order bằng tổng item | Cập nhật aggregate total trong cùng transaction hoặc tính khi đọc |
| Không cho hai phiên cùng chiếm một tài nguyên | Dùng row/slot có unique key để chiếm giữ nguyên tử |

Không phải mọi invariant phải được kiểm tra bằng cách đếm lại bảng. Nếu dữ liệu có thể được biểu diễn bằng một khóa duy nhất hoặc một row guard, việc bảo vệ concurrency thường rõ ràng hơn.

## 15. Kiểm thử invariant dưới tải đồng thời

Một test tuần tự có thể luôn pass trong khi production gặp race. Cần kiểm tra hành vi của nhiều transaction độc lập:

- Dùng database thật hoặc cùng loại DBMS với production nếu constraint/isolation đặc thù.
- Mở nhiều transaction/session riêng, đồng thời thực hiện thao tác tranh chấp.
- Dùng barrier/latch để điều khiển thời điểm các transaction đọc và ghi, tránh test chỉ chạy tình cờ tuần tự.
- Kiểm tra số hàng commit cuối cùng và invariant thực tế, không chỉ assert exception.
- Kiểm tra retry/rollback, transaction outcome và persistence context sau lỗi.
- Lặp lại test đủ số lần trong môi trường phù hợp để quan sát deadlock/timeout/serialization failures.
- Bao phủ cả writer ngoài Hibernate nếu hệ thống có batch, integration hoặc script quản trị.

Ví dụ test concept cho unique email: khởi chạy hai transaction với cùng email; kỳ vọng **chỉ một** hàng commit, transaction còn lại nhận lỗi unique hoặc kết quả duplicate đã được xử lý. Với capacity 10, chạy nhiều request đồng thời; sau khi tất cả kết thúc, đếm reservation active và assert không quá 10. Test cần thực sự chạy transaction trên các connection độc lập để tạo concurrency.

**Không chỉ mock repository** rồi kết luận DB constraint hoạt động. Mock không thực thi unique/FK/check/index, không mô phỏng isolation và lock behavior.

## 16. Các lỗi thường gặp khi thiết kế invariant

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “Đã gọi existsBy... trước insert thì không trùng.” | Hai transaction có thể cùng thấy chưa tồn tại; cần unique constraint |
| “@Transactional ngăn hai request cùng đặt chỗ.” | Atomicity không tự tuần tự hóa kiểm tra/ghi; cần lock, constraint hoặc atomic update |
| “@Version trên child bảo vệ tổng số child.” | Version chỉ bảo vệ row/entity được kiểm tra; nếu thêm hai child khác nhau không update parent thì không có conflict |
| “CHECK có thể COUNT hàng trong bảng khác.” | CHECK thông thường dành cho row-level expression; cross-row aggregate cần cơ chế khác |
| “FK cascade và JPA CascadeType.REMOVE là một.” | DB referential action và ORM entity lifecycle là hai cơ chế |
| “Annotation @UniqueConstraint tự sửa schema production.” | Chỉ mô tả mapping/DDL generation; migration/schema thật phải được quản lý |
| “Bắt DataIntegrityViolationException rồi tiếp tục cùng transaction.” | Transaction có thể rollback-only; kết thúc unit of work rồi xử lý scope mới |
| “SERIALIZABLE không bao giờ thất bại.” | DBMS có thể abort để bảo toàn serializability; application phải xử lý retry |
| “Khóa một hàng bất kỳ sẽ ngăn phantom insert.” | Lock scope và DBMS semantics phải khớp invariant |
| “Counter trên parent tự luôn bằng số child.” | Cần tất cả writer cập nhật đồng bộ hoặc trigger/procedure |
| “Flush thành công là transaction đã commit.” | Flush gửi DML; commit mới hoàn tất transaction |
| “Reconciliation job thay thế constraint.” | Reconciliation phát hiện/sửa lệch; có thể có khoảng thời gian dữ liệu sai |

## 17. Quy trình chọn cơ chế bảo vệ invariant

1. **Viết invariant bằng một câu chính xác.** Nêu rõ phạm vi: hàng, cặp khóa, tenant, aggregate, thời gian hay toàn bảng.
2. **Xác định điều kiện hợp lệ và null semantics.** Ví dụ “một email duy nhất sau khi normalize” khác “email raw text duy nhất”.
3. **Chọn constraint declarative trước.** PK, FK, NOT NULL, UNIQUE, CHECK hoặc exclusion constraint nếu DBMS hỗ trợ.
4. **Nếu invariant liên hàng không biểu đạt được bằng constraint đơn giản, chọn concurrency protocol.** Guard row, pessimistic lock, optimistic version trên aggregate, atomic conditional update hoặc SERIALIZABLE.
5. **Bảo đảm mọi writer tuân thủ.** ORM, native SQL, batch import, trigger, service khác và công cụ quản trị.
6. **Đặt transaction boundary đúng.** Các thay đổi cấu thành một invariant phải commit/rollback theo cùng đơn vị nghiệp vụ nếu có thể.
7. **Xử lý lỗi ở ranh giới transaction.** Phân loại constraint/lock/serialization exception; rollback và bỏ persistence context lỗi; retry bằng transaction mới khi hợp lệ.
8. **Migration dữ liệu cũ trước khi thêm constraint.** Kiểm tra duplicates, orphan references, nulls, overlapping ranges và counter drift.
9. **Kiểm thử concurrency trên DBMS thực.** Dùng nhiều connection/session và xác nhận trạng thái cuối cùng.
10. **Giám sát và đối soát.** Log constraint name/SQLState, retry rate, deadlock và các metric invariant quan trọng.

## 18. Ba tình huống để áp dụng

### Tình huống A — Email tài khoản không được trùng

Dùng validation/normalization ở service để trả thông báo dễ hiểu; unique constraint trên giá trị normalized để bảo vệ concurrency. Nếu hai request cùng đăng ký, một request thành công và request kia xử lý unique violation thành “email đã được sử dụng”. Không retry nguyên insert vô hạn.

### Tình huống B — Phòng có sức chứa hữu hạn

Không chỉ count reservation rồi insert. Chọn một trong các protocol: khóa Room row trước khi đếm; tăng counter có `@Version`; atomic conditional update; hoặc mô hình slot. Giữ thao tác chiếm chỗ và tạo reservation trong cùng transaction. Tất cả đường hủy/đổi reservation phải cập nhật counter/slot đúng quy tắc.

### Tình huống C — Lịch đặt không được chồng lấn

Một CHECK trên từng hàng chỉ xác nhận `start < end`. Nếu DBMS hỗ trợ exclusion constraint, dùng nó để bảo vệ không chồng khoảng. Nếu không, khóa resource/room guard row trước khi truy vấn overlap và insert, với mọi writer dùng cùng protocol; cân nhắc isolation mạnh hơn và retry khi DB abort transaction.

## 19. Bài tập tự kiểm tra

1. Hai request cùng chạy `existsByEmail` và đều nhận false. Cơ chế nào bảo đảm cuối cùng chỉ có một account với email đó?
2. Vì sao `CHECK(reserved_count <= capacity)` không bảo đảm `reserved_count` bằng số reservation active trong bảng con?
3. Một entity `Room` có `@Version`, nhưng thao tác đặt chỗ chỉ insert hai entity `Reservation` khác nhau. Vì sao version của Room có thể không phát hiện race?
4. Nếu mọi thao tác reservation đều khóa cùng hàng Room trước khi count/insert, điều kiện nào phải đúng để protocol an toàn?
5. Khi dùng native atomic update tăng counter, vì sao persistence context có thể cần refresh/clear?
6. Một CHECK `start_at < end_at` có ngăn hai booking khác hàng chồng thời gian không? Cần constraint/cơ chế nào?
7. Tại sao `@Transactional` không tự làm unique constraint trở nên thừa?
8. Khi SERIALIZABLE abort một transaction, vì sao retry phải chạy lại toàn bộ unit of work với context mới?
9. Phân biệt FK constraint với `CascadeType.REMOVE`.
10. Nếu database có nhiều writer ngoài Hibernate, vì sao constraint DB càng quan trọng?

**Gợi ý:** (1) UNIQUE; (2) CHECK chỉ xem hàng Room, không đếm child rows; (3) không update cùng versioned row; (4) mọi writer khóa cùng guard row, giữ lock đến commit và dùng transaction phù hợp; (5) bulk/native DML bypass managed state; (6) exclusion constraint hoặc lock/serializable protocol; (7) hai transaction vẫn có thể cùng kiểm tra rồi insert; (8) transaction/context cũ đã bị abort; (9) FK bảo vệ tham chiếu ở DB, cascade REMOVE lan truyền entity lifecycle trong ORM; (10) DB constraint áp dụng tập trung cho mọi đường ghi chịu schema.

## 20. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): entity mapping, schema generation, locking, transactions và optimistic locking.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): `@Version`, lock modes, transaction và entity lifecycle.
- [PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary key, unique, foreign key, check và exclusion constraints; cú pháp/khả năng ở các DBMS khác cần tra tài liệu tương ứng.
- [PostgreSQL Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): serialization anomalies, isolation và serialization failure.

**Nguyên tắc cốt lõi:** invariant phải được xác định ở đúng phạm vi dữ liệu. Validation trong Java giúp giải thích quy tắc; transaction nhóm các thay đổi; locking/isolation điều phối các transaction cạnh tranh; còn constraint database bảo vệ những trạng thái mà DB có thể biểu đạt trước mọi writer. Với invariant tổng hợp qua nhiều hàng, hãy thiết kế guard row, counter nguyên tử, exclusion/unique constraint hoặc transaction protocol cụ thể, và bảo đảm mọi đường ghi cùng tuân thủ.
