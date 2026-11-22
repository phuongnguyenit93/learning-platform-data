# Định danh phụ thuộc với @MapsId trong Spring Data JPA

Trong JPA, một entity có thể dùng khóa chính của entity khác làm toàn bộ hoặc một phần khóa chính của chính nó. Kiểu ánh xạ này gọi là derived identity (định danh phụ thuộc). Annotation `@MapsId` biểu diễn mối quan hệ đó: khóa ngoại của quan hệ đồng thời tham gia vào khóa chính của entity phụ thuộc.

Ví dụ điển hình là hồ sơ người dùng có cùng ID với người dùng, hoặc dòng đơn hàng có khóa chính gồm ID đơn hàng và số thứ tự dòng. `@MapsId` giúp JPA đồng bộ phần khóa chính từ quan hệ, tránh phải ánh xạ cùng một cột khóa ngoại theo hai cách độc lập.

Bài này dùng Java 17+, Spring Boot 3.x và Jakarta Persistence. Các import JPA trong ví dụ là `jakarta.persistence`. Với dự án Spring Boot 2.x cũ, namespace tương ứng thường là `javax.persistence`; không trộn hai namespace trong cùng entity model.

## 1. Định danh phụ thuộc là gì?

Giả sử hệ thống có hai bảng:

- `app_users` lưu người dùng, mỗi người dùng có khóa chính `id`.
- `user_profiles` lưu hồ sơ mở rộng; một hồ sơ chỉ thuộc về một người dùng và không có danh tính độc lập.

Nếu `user_profiles.user_id` vừa là khóa chính vừa là khóa ngoại tham chiếu `app_users.id`, ID của hồ sơ chính là ID của người dùng.

| app_users | user_profiles |
|---|---|
| `id` — PK | `user_id` — PK, FK |
| `email` | `bio` |

Ví dụ: người dùng có ID 41 thì hồ sơ của người dùng đó cũng có ID 41. Không tồn tại một ID độc lập khác cho hồ sơ.

Định danh phụ thuộc có hai dạng phổ biến:

1. Quan hệ cung cấp toàn bộ khóa chính của entity phụ thuộc, thường là One-to-One dùng chung primary key.
2. Quan hệ cung cấp một phần khóa chính, thường là Many-to-One kết hợp với một thành phần khác trong `@EmbeddedId`.

## 2. @MapsId dùng để làm gì?

`@MapsId` đánh dấu thuộc tính quan hệ `@OneToOne` hoặc `@ManyToOne` mà khóa ngoại của quan hệ được ánh xạ vào toàn bộ hoặc một phần khóa chính của entity hiện tại.

Có hai cách dùng chính:

- `@MapsId` không có giá trị: quan hệ ánh xạ vào toàn bộ khóa chính của entity phụ thuộc.
- `@MapsId("attributeName")`: quan hệ ánh xạ vào thuộc tính có tên tương ứng bên trong khóa chính nhúng `@EmbeddedId`.

Tên truyền vào `@MapsId` là tên thuộc tính Java trong lớp ID, không phải tên cột SQL. Kiểu của thuộc tính ID được ánh xạ phải tương thích với kiểu khóa chính của entity được tham chiếu.

`@MapsId` không tự tạo cascade, không tự quản lý transaction và không thay thế ràng buộc khóa ngoại trong database. Nó mô tả cách JPA ánh xạ khóa của entity phụ thuộc từ quan hệ.

## 3. One-to-One: hồ sơ dùng chung ID với người dùng

### 3.1. Entity cha AppUser

Tạo file `AppUser.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_users")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 150)
    private String email;

    protected AppUser() {
    }

    public AppUser(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

`AppUser` là entity cha và tự sinh khóa chính bằng cơ chế identity của database. Trước khi persist, ID có thể chưa có giá trị; sau khi entity được persist, JPA provider nhận ID do database cấp.

### 3.2. Entity phụ thuộc UserProfile

Tạo file `UserProfile.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "user_profiles")
public class UserProfile {

    @Id
    @Column(name = "user_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private AppUser user;

    @Column(length = 500)
    private String bio;

    protected UserProfile() {
    }

    public UserProfile(AppUser user, String bio) {
        this.user = Objects.requireNonNull(user);
        this.bio = bio;
    }

    public Long getId() {
        return id;
    }

    public AppUser getUser() {
        return user;
    }

    public String getBio() {
        return bio;
    }
}
~~~

Các điểm quan trọng:

- `@Id` xác định khóa chính của `UserProfile`.
- `@Column(name = "user_id")` ánh xạ thuộc tính ID vào cột `user_id`.
- `@OneToOne` khai báo quan hệ một-một từ hồ sơ đến người dùng.
- `@JoinColumn(name = "user_id")` chỉ định cột khóa ngoại trong bảng `user_profiles`.
- `@MapsId` nói rằng khóa chính của hồ sơ được lấy từ khóa chính của `user`.
- Không có `@GeneratedValue` trên `UserProfile.id`, vì ID của hồ sơ được kế thừa từ người dùng.

Cùng một cột `user_id` được dùng cho cả khóa chính và khóa ngoại. `@MapsId` giúp JPA hiểu đây là một ánh xạ thống nhất, thay vì hai thuộc tính độc lập cùng ghi vào một cột.

Cấu trúc logic của bảng hồ sơ:

~~~sql
create table user_profiles (
    user_id bigint not null primary key,
    bio varchar(500),
    constraint fk_user_profile_user
        foreign key (user_id) references app_users(id)
);
~~~

Khóa chính cũng là khóa ngoại nên mỗi người dùng có tối đa một hồ sơ. Quan hệ này không tự bắt buộc mọi người dùng phải có hồ sơ; nếu nghiệp vụ yêu cầu, cần bảo đảm điều đó trong quy trình tạo dữ liệu hoặc bằng quy tắc phù hợp ở database.

### 3.3. Tạo người dùng và hồ sơ

Dùng `EntityManager` để thấy rõ thứ tự persist. Tạo file `ProfileService.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProfileService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public Long createUserWithProfile(String email, String bio) {
        AppUser user = new AppUser(email);
        entityManager.persist(user);

        // Với IDENTITY, persist thường thực thi INSERT để lấy ID.
        entityManager.flush();

        UserProfile profile = new UserProfile(user, bio);
        entityManager.persist(profile);

        entityManager.flush();
        return profile.getId();
    }
}
~~~

Luồng thực hiện:

1. Tạo entity `AppUser`.
2. Persist người dùng để JPA quản lý entity và lấy khóa chính.
3. Tạo `UserProfile` với quan hệ đến người dùng đã được quản lý.
4. Persist hồ sơ.
5. JPA lấy `user.id` để điền vào `UserProfile.id` theo `@MapsId`.
6. Flush đồng bộ các thay đổi xuống database; transaction commit khi phương thức kết thúc thành công.

`flush()` giúp làm rõ thời điểm ghi và lấy ID trong ví dụ. Flush không phải commit; transaction vẫn có thể rollback nếu có lỗi trước khi kết thúc.

Có thể dùng repository thay cho `EntityManager`. Điều quan trọng là entity cha phải được persist hoặc được cascade persist hợp lệ, và quan hệ phải được gán cho entity phụ thuộc trước khi lưu.

### 3.4. Kiểm thử khóa chính được chia sẻ

Ví dụ kiểm thử bằng `@DataJpaTest` và `TestEntityManager`:

~~~java
package com.example.mapsid;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class UserProfileMappingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void profileUsesTheUsersPrimaryKey() {
        AppUser user = new AppUser("linh@example.com");
        entityManager.persist(user);
        entityManager.flush();

        UserProfile profile = new UserProfile(user, "Backend developer");
        entityManager.persist(profile);
        entityManager.flush();

        assertThat(profile.getId()).isEqualTo(user.getId());

        UserProfile loaded =
                entityManager.find(UserProfile.class, user.getId());

        assertThat(loaded.getUser().getId()).isEqualTo(user.getId());
        assertThat(loaded.getBio()).isEqualTo("Backend developer");
    }
}
~~~

Test xác nhận ID của hồ sơ bằng ID người dùng và quan hệ có thể được đọc lại. `@DataJpaTest` thường chạy trong transaction được rollback sau test, giúp dữ liệu kiểm thử không tồn tại lâu dài.

## 4. Many-to-One: quan hệ tạo một phần khóa chính

Một đơn hàng có nhiều dòng; mỗi dòng được định danh bằng cặp `(order_id, line_number)`:

- `order_id` tham chiếu đơn hàng.
- `line_number` phân biệt các dòng bên trong cùng đơn hàng.

Khi đó `order_id` là một phần khóa chính và đồng thời là khóa ngoại. Dùng `@MapsId("orderId")` để ánh xạ quan hệ vào đúng phần ID đó.

### 4.1. Lớp khóa OrderLineId

Tạo file `OrderLineId.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_number")
    private Integer lineNumber;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineId that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Lớp khóa nhúng cần constructor không tham số và định nghĩa `equals`/`hashCode` dựa trên tất cả thành phần khóa. Điều này đặc biệt quan trọng khi ID được dùng trong collection hoặc cache.

### 4.2. Entity PurchaseOrder

Tạo file `PurchaseOrder.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }
}
~~~

### 4.3. Entity OrderLine với @MapsId("orderId")

Tạo file `OrderLine.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 80)
    private String sku;

    protected OrderLine() {
    }

    public OrderLine(
            PurchaseOrder order,
            Integer lineNumber,
            String sku) {

        this.order = Objects.requireNonNull(order);
        this.id = new OrderLineId(null, lineNumber);
        this.sku = Objects.requireNonNull(sku);
    }

    public OrderLineId getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }
}
~~~

`@MapsId("orderId")` tham chiếu đúng thuộc tính `orderId` trong `OrderLineId`. Tên này phải trùng tên thuộc tính Java trong lớp ID, không phải tên cột `order_id`.

Khi persist `OrderLine`, JPA lấy ID của `order` và đồng bộ vào `id.orderId`. Thành phần `lineNumber` vẫn do ứng dụng cung cấp. Khóa chính của bảng là cặp `(order_id, line_number)`.

~~~sql
create table order_lines (
    order_id bigint not null,
    line_number integer not null,
    sku varchar(80) not null,
    primary key (order_id, line_number),
    constraint fk_order_line_order
        foreign key (order_id) references purchase_orders(id)
);
~~~

### 4.4. Persist đơn hàng và dòng hàng

~~~java
package com.example.mapsid;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public OrderLineId createOrderWithLine(String sku) {
        PurchaseOrder order = new PurchaseOrder();
        entityManager.persist(order);
        entityManager.flush();

        OrderLine line = new OrderLine(order, 1, sku);
        entityManager.persist(line);
        entityManager.flush();

        return line.getId();
    }
}
~~~

Sau khi persist, khóa của dòng có dạng `OrderLineId(orderId = <ID đơn hàng>, lineNumber = 1)`. Ứng dụng không cần tự gán `orderId` vì nó được ánh xạ từ quan hệ.

## 5. Phân biệt @MapsId với quan hệ thông thường

Một quan hệ `@ManyToOne` thông thường chỉ tạo khóa ngoại. Khóa chính của entity con vẫn độc lập:

~~~java
@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;
}
~~~

Trong ví dụ này, `Comment.id` là ID riêng của bình luận; `post_id` chỉ là khóa ngoại. Không dùng `@MapsId` vì khóa của bài viết không phải một phần khóa chính của bình luận.

| Đặc điểm | Quan hệ thông thường | Quan hệ với @MapsId |
|---|---|---|
| Khóa chính entity con | Độc lập | Lấy toàn bộ hoặc một phần từ entity được tham chiếu |
| Khóa ngoại | Cột riêng | Đồng thời ánh xạ vào khóa chính |
| Ví dụ | Comment có ID riêng, tham chiếu Post | UserProfile dùng ID của AppUser |
| Nhiều entity con cùng tham chiếu một cha | Có thể | Có thể nếu phần ID còn lại phân biệt từng entity |

Nếu entity con có ID riêng và chỉ cần lưu quan hệ đến cha, hãy dùng quan hệ thông thường. Dùng `@MapsId` khi mô hình dữ liệu thật sự yêu cầu khóa chính phụ thuộc.

## 6. Quan hệ hai chiều và phía sở hữu

Trong ví dụ One-to-One, `UserProfile` là phía sở hữu vì nó chứa `@JoinColumn` và khóa ngoại. Nếu muốn truy cập hồ sơ từ `AppUser`, có thể bổ sung phía inverse:

~~~java
@OneToOne(mappedBy = "user", fetch = FetchType.LAZY)
private UserProfile profile;
~~~

`mappedBy = "user"` trỏ đến thuộc tính quan hệ `user` trong `UserProfile`. Phía inverse không khai báo một `@JoinColumn` thứ hai và không phải nơi đặt `@MapsId` cho quan hệ này.

Trong quan hệ hai chiều, hãy cập nhật cả hai phía trong helper method nếu ứng dụng cần object graph nhất quán. Dù cập nhật object graph ở cả hai phía, phía sở hữu vẫn quyết định dữ liệu quan hệ được ghi xuống database.

## 7. Transaction, cascade và vòng đời entity

`@MapsId` chỉ mô tả cách ánh xạ định danh; nó không tự quyết định vòng đời của entity cha và con.

1. **Gán quan hệ trước khi persist entity phụ thuộc.** Nếu `user` hoặc `order` là null, JPA không có nguồn để xác định phần ID được ánh xạ.
2. **Entity cha phải được quản lý hoặc được persist theo cascade hợp lệ.** Nếu tham chiếu một entity mới chưa được persist và không có cascade phù hợp, provider có thể báo lỗi transient object.
3. **Không tự gán ID độc lập xung đột với @MapsId.** Quan hệ là nguồn dữ liệu cho phần khóa phụ thuộc.
4. **Dùng transaction cho một nghiệp vụ gồm nhiều lần ghi.** Nếu tạo cha thành công nhưng tạo con thất bại, transaction cần rollback để tránh trạng thái dở dang.
5. **Chọn cascade có chủ đích.** `@MapsId` không tự bật `CascadeType.PERSIST` hay `CascadeType.REMOVE`. Chỉ thêm cascade khi vòng đời nghiệp vụ thật sự yêu cầu.
6. **Tôn trọng khóa ngoại và quy tắc xóa.** Entity con phụ thuộc thường không thể tồn tại khi entity cha bị xóa; xác định rõ cascade, thứ tự xóa và ràng buộc database.
7. **Không dùng ID trước khi nó được sinh.** Với ID tự tăng, giá trị có thể chỉ xuất hiện sau persist/flush tùy chiến lược và provider.

Đối với One-to-One dùng chung primary key, việc xóa người dùng thường cũng cần xử lý hồ sơ trước hoặc dùng cascade phù hợp với mô hình. Không thêm cascade xóa chỉ để làm cho ví dụ chạy; hãy cân nhắc dữ liệu lịch sử và yêu cầu lưu trữ.

## 8. Các lỗi ánh xạ thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| ID của entity phụ thuộc vẫn null | Chưa gán quan hệ hoặc cha chưa có ID | Persist cha, gán association rồi persist con |
| Không thể persist entity con | Quan hệ bắt buộc đang null hoặc cha là transient | Đảm bảo association hợp lệ và cascade/persist cha |
| Lỗi trùng cột mapping | Ánh xạ khóa ngoại như thuộc tính độc lập đồng thời với ID mà không dùng MapsId | Dùng `@MapsId` để biểu diễn cột dùng chung |
| Giá trị @MapsId không được nhận diện | Truyền tên cột thay vì tên thuộc tính trong EmbeddedId | Dùng đúng tên Java, ví dụ `@MapsId("orderId")` |
| Composite key không hoạt động trong Set/Map | Thiếu hoặc sai equals/hashCode | So sánh tất cả thành phần khóa |
| Xóa cha thất bại | Còn entity con tham chiếu cha qua FK | Xử lý con trước hoặc thiết kế cascade phù hợp |
| Cập nhật quan hệ nhưng ID không nhất quán | Thay association sau khi entity đã được quản lý hoặc đã có ID xung đột | Thiết kế quan hệ trước khi persist; nếu đổi cha, xử lý như thay đổi khóa định danh và kiểm thử kỹ |

Thay đổi khóa chính của entity đang tồn tại là thao tác rủi ro. Với entity dùng `@MapsId`, đổi quan hệ cha có thể đồng nghĩa đổi khóa chính của entity con. Thông thường nên xem quan hệ xác định danh tính là bất biến sau khi tạo entity; nếu nghiệp vụ cần chuyển sang cha khác, cân nhắc xóa và tạo lại entity phụ thuộc trong một transaction thay vì thay ID tùy tiện.

## 9. Khi nào nên dùng @MapsId?

Dùng `@MapsId` khi:

- Entity phụ thuộc không có danh tính độc lập ngoài entity cha.
- One-to-One dùng chung primary key là quy tắc dữ liệu thật.
- Một phần khóa chính composite của entity con chính là khóa của entity cha.
- Muốn JPA đồng bộ giá trị khóa ngoại và khóa chính theo cùng một mapping.
- Mô hình domain thể hiện rõ vòng đời entity con phụ thuộc vào entity cha.

Không dùng `@MapsId` chỉ vì hai entity có ID bằng nhau trong một ví dụ. Nếu ID của entity con được sinh độc lập và quan hệ chỉ là khóa ngoại thông thường, dùng `@ManyToOne` hoặc `@OneToOne` cùng `@JoinColumn` là đủ.

## 10. Checklist kiểm tra trước khi triển khai

- [ ] Đã xác định entity nào là cha và entity nào phụ thuộc.
- [ ] Đã xác định quan hệ ánh xạ toàn bộ khóa hay chỉ một phần khóa.
- [ ] Với khóa đơn, dùng `@MapsId` không tham số.
- [ ] Với `@EmbeddedId`, giá trị `@MapsId("...")` khớp tên thuộc tính Java.
- [ ] Kiểu thuộc tính ID tương thích với kiểu khóa chính của entity cha.
- [ ] Cột được ánh xạ nhất quán giữa `@Id`/`@EmbeddedId` và `@JoinColumn`.
- [ ] Entity cha đã được persist hoặc cascade phù hợp trước khi persist entity con.
- [ ] Lớp khóa composite có constructor phù hợp, equals và hashCode đúng.
- [ ] Cascade, transaction và hành vi xóa được thiết kế theo vòng đời nghiệp vụ.
- [ ] Test xác nhận ID được đồng bộ và khóa ngoại tồn tại trong database.

`@MapsId` phù hợp nhất khi quan hệ giữa các entity cũng là một phần của định danh. Với One-to-One dùng chung primary key, nó ánh xạ toàn bộ ID từ cha sang con; với composite key, nó ánh xạ đúng một thành phần của khóa nhúng. Khi mô hình ID, association, transaction và vòng đời được thiết kế nhất quán, JPA có thể duy trì khóa phụ thuộc mà không cần ứng dụng tự đồng bộ các cột khóa bằng tay.
