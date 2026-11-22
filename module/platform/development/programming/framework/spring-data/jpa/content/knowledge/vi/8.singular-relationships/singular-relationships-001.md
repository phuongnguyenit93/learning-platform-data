# Phân biệt quan hệ đơn hướng, hai hướng và phía sở hữu

## 1. Hướng quan hệ trong mô hình Entity

Trong JPA, một quan hệ mô tả cách các đối tượng Entity tham chiếu lẫn nhau. Có hai cách tổ chức đường tham chiếu trong Java:

- **Đơn hướng (unidirectional):** chỉ một Entity giữ thuộc tính tham chiếu tới Entity còn lại. Ví dụ `PurchaseOrder` có thuộc tính `customer`, nhưng `Customer` không có collection `orders`.
- **Hai hướng (bidirectional):** cả hai Entity đều có thuộc tính tham chiếu qua lại. Ví dụ `PurchaseOrder.customer` và `Customer.orders` cùng biểu diễn một quan hệ.

Hướng quan hệ trong object model là một khái niệm riêng với lực lượng quan hệ trong cơ sở dữ liệu. `@ManyToOne`, `@OneToMany`, `@OneToOne` và `@ManyToMany` mô tả cardinality; đơn hướng/hai hướng mô tả số chiều tham chiếu trong Java. Một quan hệ nhiều-một vẫn có thể đơn hướng hoặc hai hướng.

Không bắt buộc phải ánh xạ hai hướng chỉ vì database có khóa ngoại. Nếu use case chỉ cần đi từ đơn hàng tới khách hàng, mapping đơn hướng thường đơn giản và ít rủi ro hơn.

## 2. Phía sở hữu (owning side) là gì?

Trong một quan hệ JPA, **phía sở hữu** là phía quyết định cập nhật liên kết xuống database. Với quan hệ dùng khóa ngoại, phía sở hữu thường là Entity chứa thuộc tính khóa ngoại và khai báo `@JoinColumn`. Với quan hệ dùng join table, phía sở hữu là phía khai báo `@JoinTable` hoặc phía không khai báo `mappedBy`.

Phía còn lại của quan hệ hai hướng là **inverse side** (phía nghịch đảo), được khai báo bằng `mappedBy`. Giá trị `mappedBy` là tên thuộc tính Java ở phía sở hữu, phân biệt hoa/thường và không phải tên cột database.

Ví dụ:

```java
// PurchaseOrder owns the relationship because it contains customer_id.
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;

// Customer is the inverse side.
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();
```

Trong ví dụ này, `mappedBy = "customer"` trỏ tới thuộc tính `PurchaseOrder.customer`. Hibernate lấy quan hệ từ thuộc tính đó để ghi `customer_id`. Chỉ thêm một đơn hàng vào `Customer.orders` mà không gán `PurchaseOrder.customer` sẽ không cập nhật khóa ngoại như mong muốn.

Quy tắc quan trọng: khi thay đổi quan hệ hai hướng, hãy cập nhật phía sở hữu để thay đổi được lưu; đồng thời cập nhật cả hai phía trong bộ nhớ để object graph nhất quán.

## 3. Quan hệ đơn hướng và hai hướng: chọn theo nhu cầu

| Tiêu chí | Đơn hướng | Hai hướng |
| --- | --- | --- |
| Đường truy cập trong Java | Một phía truy cập phía kia | Có thể truy cập từ cả hai phía |
| Số thuộc tính quan hệ | Ít hơn | Nhiều hơn, có tham chiếu vòng |
| Đồng bộ object graph | Thường đơn giản | Phải giữ hai phía nhất quán |
| Trường hợp phù hợp | Use case chỉ điều hướng một chiều | Use case thường xuyên cần điều hướng hai chiều |
| Rủi ro phổ biến | Mapping join table ngoài ý muốn với OneToMany đơn hướng | Quên cập nhật owning side hoặc gặp vòng lặp khi serialize |

Không nên tạo quan hệ hai hướng chỉ để thuận tiện cho một màn hình hoặc một truy vấn. Có thể dùng repository query, DTO projection hoặc JPQL join khi cần dữ liệu phía còn lại mà không cần thêm collection ngược vào Entity.

## 4. OneToMany/ManyToOne hai hướng: phía ManyToOne sở hữu

Đây là mẫu phổ biến nhất. Khóa ngoại `customer_id` nằm trong bảng `purchase_order`, vì vậy `PurchaseOrder` sở hữu quan hệ:

```java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer", cascade = CascadeType.PERSIST)
    private List<PurchaseOrder> orders = new ArrayList<>();

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
        order.setCustomer(this);
    }

    public void removeOrder(PurchaseOrder order) {
        orders.remove(order);
        order.setCustomer(null);
    }
}
```

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
```

Đây là các phần khai báo cốt lõi; trong ứng dụng thực tế cần bổ sung constructor, getter/setter và quy tắc equals/hashCode phù hợp. `Customer.orders` dùng `mappedBy`, còn `PurchaseOrder.customer` chứa `@JoinColumn` nên là phía sở hữu.

Phương thức `addOrder` cập nhật cả collection và thuộc tính sở hữu. Nếu chỉ gọi `customer.getOrders().add(order)`, Java collection có thể chứa đơn hàng nhưng `order.customer` vẫn null; khi flush, `customer_id` có thể không được ghi như mong đợi. Nếu `nullable = false`, thao tác lưu còn có thể thất bại do khóa ngoại null.

Phương thức `removeOrder` ở trên chỉ phù hợp khi quan hệ cho phép bỏ liên kết và cột khóa ngoại nullable. Nếu `customer_id` là NOT NULL, cần định nghĩa nghiệp vụ xóa đơn hàng, chuyển sang khách hàng khác hoặc từ chối thao tác. Có thể dùng `orphanRemoval = true` nếu việc bỏ đơn hàng khỏi collection đồng nghĩa xóa Entity con, nhưng đây là quyết định vòng đời dữ liệu, không phải cách đồng bộ quan hệ mặc định.

## 5. OneToMany đơn hướng

Nếu chỉ cần từ `Customer` truy cập các `PurchaseOrder` mà không cần thuộc tính `PurchaseOrder.customer`, có thể khai báo `@OneToMany` đơn hướng. Theo mặc định, JPA thường dùng join table cho mapping này:

```java
@OneToMany
@JoinTable(
    name = "customer_order",
    joinColumns = @JoinColumn(name = "customer_id"),
    inverseJoinColumns = @JoinColumn(name = "order_id", unique = true)
)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Để dùng khóa ngoại trên bảng con mà không thêm thuộc tính ngược, có thể khai báo `@JoinColumn` trực tiếp trên collection:

```java
@OneToMany
@JoinColumn(name = "customer_id")
private List<PurchaseOrder> orders = new ArrayList<>();
```

Ở dạng đơn hướng này, collection là phía khai báo liên kết; không có `mappedBy` vì Entity con không có thuộc tính quan hệ tương ứng. Cần kiểm tra DDL Hibernate tạo ra hoặc migration đã có để chắc chắn cấu trúc khóa ngoại khớp với mapping. Nếu cần thao tác thường xuyên từ đơn hàng về khách hàng, cân nhắc chuyển sang mapping hai hướng `ManyToOne`/`OneToMany`.

## 6. OneToOne: phía chứa khóa ngoại sở hữu

Với quan hệ tài khoản và hồ sơ, giả sử bảng `profile` chứa `account_id`, thì `Profile` là phía sở hữu:

```java
@Entity
public class Profile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false, unique = true)
    private Account account;
}
```

```java
@Entity
public class Account {
    @Id
    private Long id;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private Profile profile;
}
```

`Profile.account` sở hữu quan hệ vì bảng `profile` có khóa ngoại `account_id`. `Account.profile` là inverse side. `unique = true` thể hiện ràng buộc một tài khoản chỉ được liên kết tối đa với một hồ sơ ở cấp schema; vẫn cần migration tạo unique constraint tương ứng.

Nếu khóa ngoại đặt ở bảng `account`, hãy đảo vị trí owning/inverse cho đúng schema. Với OneToOne, phía sở hữu được xác định bởi nơi lưu khóa ngoại, không phải bởi Entity nào có vẻ là đối tượng cha trong nghiệp vụ.

## 7. ManyToMany: phía sở hữu quản lý join table

Ví dụ học viên đăng ký nhiều khóa học và mỗi khóa học có nhiều học viên. Join table `student_course` lưu hai khóa ngoại:

```java
@Entity
public class Student {
    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
```

```java
@Entity
public class Course {
    @Id
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
```

`Student.courses` là owning side vì khai báo `@JoinTable`; `Course.students` là inverse side vì `mappedBy = "courses"`. Khi thêm hoặc xóa liên kết, phải cập nhật `Student.courses` để Hibernate ghi thay đổi vào join table. Nếu giữ hai collection trong bộ nhớ, helper method nên đồng bộ cả hai.

```java
public void addCourse(Course course) {
    courses.add(course);
    course.getStudents().add(this);
}

public void removeCourse(Course course) {
    courses.remove(course);
    course.getStudents().remove(this);
}
```

Tránh `CascadeType.REMOVE` một cách tùy tiện trong ManyToMany: một `Course` có thể được nhiều `Student` dùng chung, nên xóa một học viên không đồng nghĩa xóa khóa học. Nếu quan hệ có thuộc tính riêng như thời điểm đăng ký, điểm số hoặc trạng thái, hãy tạo Entity trung gian như `Enrollment` thay vì dùng ManyToMany trực tiếp.

## 8. Đồng bộ hai phía trong bộ nhớ

JPA không tự bảo đảm hai thuộc tính Java của quan hệ hai hướng luôn đồng bộ khi ứng dụng thay đổi một phía. Hibernate dựa vào owning side để ghi liên kết. Vì thế nên đóng gói thao tác thêm/xóa trong helper method của domain model:

- Thêm quan hệ: thêm phần tử vào collection và gán tham chiếu owning side.
- Bỏ quan hệ: gỡ phần tử khỏi collection và cập nhật owning side theo quy tắc nghiệp vụ.
- Không để service tự sửa tùy tiện từng collection ở nhiều nơi; tập trung logic đồng bộ giúp tránh trạng thái lệch.

Với quan hệ hai hướng, `toString()`, `equals()` và `hashCode()` cần tránh đi qua toàn bộ quan hệ vòng. Ví dụ `Customer` tham chiếu `PurchaseOrder` và `PurchaseOrder` lại tham chiếu `Customer`; đưa cả hai thuộc tính vào `toString()` có thể gây đệ quy. Đưa collection mutable vào `hashCode()` cũng có thể làm hỏng hành vi của `HashSet` khi quan hệ thay đổi. Hãy chọn định danh ổn định và quy tắc equality phù hợp vòng đời Entity.

## 9. Owning side, cascade và orphanRemoval là ba khái niệm khác nhau

| Cơ chế | Câu hỏi mà nó trả lời |
| --- | --- |
| Owning side / `mappedBy` | Phía nào quyết định ghi liên kết FK hoặc join table? |
| `cascade` | Thao tác persist/merge/remove/refresh/detach có lan sang Entity liên quan không? |
| `orphanRemoval` | Khi Entity con bị gỡ khỏi quan hệ OneToOne/OneToMany, có xóa Entity con khỏi database không? |

`cascade = PERSIST` không làm inverse side trở thành owning side. `cascade = ALL` cũng không tự đồng bộ hai thuộc tính Java. Tương tự, `orphanRemoval = true` không thay thế việc cập nhật owning side; nó thể hiện quy tắc vòng đời của Entity con. Chỉ bật cascade và orphan removal khi quan hệ sở hữu vòng đời thực sự, tránh xóa nhầm dữ liệu được dùng chung.

## 10. Thay đổi quan hệ và flush

Với một `PurchaseOrder` đang managed, thay đổi `order.setCustomer(newCustomer)` sẽ cập nhật phía sở hữu. Hibernate sẽ ghi giá trị `customer_id` mới khi flush hoặc commit transaction. Nếu chỉ thêm order vào `newCustomer.orders` mà không thay đổi `order.customer`, Hibernate không có thay đổi owning side để ghi khóa ngoại.

Với Entity detached, cần đưa đối tượng trở lại persistence context theo đúng quy trình `merge` hoặc tải Entity managed rồi thay đổi. `merge()` trả về một instance managed khác; tiếp tục thao tác trên object detached ban đầu không làm thay đổi instance managed đã được merge.

Không nên kỳ vọng SQL phát sinh ngay ở lệnh gọi setter. Hibernate có thể trì hoãn cập nhật cho đến flush/commit. Nếu cần kiểm tra, bật log SQL trong môi trường phát triển và quan sát câu `UPDATE` hoặc thao tác join table.

## 11. Fetching và vòng lặp khi trả Entity ra API

Quan hệ hai hướng tạo object graph có thể đi vòng. Khi serialize Entity trực tiếp thành JSON, serializer có thể lặp `Customer.orders[0].customer.orders...`, gây đệ quy vô hạn hoặc payload quá lớn. Dùng DTO/projection để định nghĩa dữ liệu API cần trả; không để cấu trúc JSON phụ thuộc hoàn toàn vào đồ thị Entity.

Fetch type cũng độc lập với owning side. Mặc định JPA quy định `ManyToOne` và `OneToOne` là EAGER, còn `OneToMany` và `ManyToMany` là LAZY. EAGER có thể kéo theo truy vấn ngoài dự kiến; LAZY có thể phát sinh lỗi khi truy cập ngoài transaction hoặc N+1 nếu không lập kế hoạch fetch. Chọn fetch plan theo use case bằng query, entity graph hoặc projection; không dùng `mappedBy` để điều khiển fetch.

## 12. Lỗi thường gặp và cách chẩn đoán

**Thêm phần tử vào collection nhưng FK không đổi.** Kiểm tra collection có phải inverse side với `mappedBy` không. Cập nhật thuộc tính owning side.

**Đặt `mappedBy` sai tên.** Giá trị phải trùng chính xác tên thuộc tính quan hệ ở Entity sở hữu, không phải tên cột như `customer_id`.

**Có hai phía nhưng chỉ một phía hiển thị dữ liệu mới.** Đồng bộ cả hai thuộc tính trong helper method; owning side quyết định dữ liệu được ghi, còn inverse collection có thể vẫn cũ trong bộ nhớ.

**Join table xuất hiện ngoài dự kiến.** Kiểm tra `@OneToMany` đơn hướng: mặc định có thể dùng join table. Nếu schema cần FK ở bảng con, khai báo `@JoinColumn` hoặc thiết kế quan hệ hai hướng với `ManyToOne` sở hữu FK.

**Xóa parent làm mất dữ liệu dùng chung.** Rà soát `CascadeType.REMOVE` và `orphanRemoval`; chúng là quy tắc vòng đời, không phải công cụ đồng bộ quan hệ.

**SQL update đúng nhưng API trả JSON bị lặp.** Tách DTO khỏi Entity và xác định rõ hướng dữ liệu API cần công khai.

## 13. Checklist thiết kế quan hệ

- Chọn đơn hướng hay hai hướng theo nhu cầu điều hướng thật sự của use case.
- Xác định FK hoặc join table nằm ở đâu trước khi khai báo owning side.
- Với quan hệ hai hướng, chỉ định `mappedBy` ở inverse side và trỏ tới đúng thuộc tính Java.
- Cập nhật owning side và đồng bộ object graph bằng helper method.
- Quyết định cascade và orphanRemoval độc lập với owning side.
- Xem xét fetch plan, N+1 và nguy cơ vòng lặp khi serialize.
- Kiểm tra DDL, foreign key, unique constraint và SQL sinh ra trên database mục tiêu.

Đơn hướng hay hai hướng là lựa chọn của mô hình đối tượng; owning side là quy tắc ghi quan hệ xuống database. Nắm rõ hai khái niệm này giúp mapping dễ hiểu, tránh lỗi FK không được cập nhật và giữ vòng đời Entity đúng với nghiệp vụ.