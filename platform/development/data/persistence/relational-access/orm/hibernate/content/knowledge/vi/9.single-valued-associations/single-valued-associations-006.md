# Khóa ngoại thiếu, dữ liệu không nhất quán và cách xử lý lỗi trong quan hệ đơn trị Hibernate

Trong Hibernate ORM, quan hệ đơn trị (*to-one association*) gồm **`@ManyToOne`** và **`@OneToOne`**. Mỗi thuộc tính Java tham chiếu đến nhiều nhất một entity khác, nhưng ở cơ sở dữ liệu (DBMS), tham chiếu ấy thường được biểu diễn bằng **một giá trị khóa ngoại (foreign key – FK)**. Khi dữ liệu sạch và ràng buộc được thực thi, Hibernate có thể dựa vào giá trị đó để định vị bản ghi liên quan. Khi khóa ngoại bị thiếu, trỏ sai hoặc chỉ được kiểm soát bằng mã ứng dụng, hành vi sẽ khác nhau giữa thời điểm ghi, tải entity, khởi tạo proxy và flush transaction.

Bài này dùng Jakarta Persistence cùng Hibernate ORM 6.x, minh họa chủ yếu theo Hibernate 6.6. Tên exception chính xác và thời điểm phát sinh còn phụ thuộc phiên bản, cách fetch, cấu hình proxy/bytecode enhancement, JDBC driver và DBMS. Trọng tâm là phân biệt **dữ liệu được phép không có quan hệ** với **dữ liệu vi phạm tính toàn vẹn tham chiếu**, từ đó chọn cách phòng ngừa, phát hiện và sửa lỗi.

## 1. Phân biệt bốn trạng thái của một khóa ngoại

Giả sử bảng đơn hàng lưu `customer_id` tham chiếu bảng khách hàng:

~~~sql
create table customers (
    id bigint primary key,
    full_name varchar(120) not null
);

create table purchase_orders (
    id bigint primary key,
    customer_id bigint,
    order_code varchar(40) not null
);
~~~

Dữ liệu có thể có các trạng thái sau:

| Dữ liệu ở `purchase_orders` | Dữ liệu ở `customers` | Ý nghĩa | Có phải vi phạm FK? |
| --- | --- | --- | --- |
| `customer_id = 10` | Có `customers.id = 10` | Tham chiếu hợp lệ | Không |
| `customer_id IS NULL` | Bất kỳ | Không gắn khách hàng | Không, nếu quan hệ/cột cho phép null |
| `customer_id = 999` | Không có `customers.id = 999` | **Dangling/broken foreign key**: FK trỏ tới bản ghi không tồn tại | Có, nếu DB thực thi ràng buộc FK |
| `customer_id = 10` | Có hàng 10 nhưng bị lọc do tenant, soft delete hoặc quyền truy cập | Bản ghi tồn tại vật lý nhưng không nhìn thấy theo ngữ cảnh truy vấn | **Không nhất thiết** là broken FK vật lý |

Trong ví dụ SQL trên chưa có ràng buộc FK. Vì vậy, DBMS có thể cho phép lưu `customer_id = 999`. Nếu thêm:

~~~sql
alter table purchase_orders
add constraint fk_order_customer
foreign key (customer_id) references customers(id);
~~~

thì DBMS sẽ từ chối ghi tham chiếu tới khách hàng không tồn tại, giả sử constraint đang được thực thi bình thường. **Ràng buộc FK không yêu cầu cột NOT NULL**: cột nullable có FK vẫn có thể chứa null; khi có giá trị khác null thì giá trị đó phải tham chiếu hợp lệ. Nếu nghiệp vụ bắt buộc đơn hàng phải có khách hàng, cần cả **NOT NULL** và **FOREIGN KEY**.

Một lỗi diễn đạt thường gặp là gọi `customer_id IS NULL` là “khóa ngoại bị hỏng”. Null có thể là trạng thái hoàn toàn hợp lệ của quan hệ tùy chọn. Chỉ khi quy tắc nghiệp vụ yêu cầu customer, nó mới là dữ liệu thiếu bắt buộc.

## 2. Mapping `@ManyToOne`, `@OneToOne` và bên sở hữu khóa ngoại

### 2.1. Quan hệ nhiều-một bắt buộc

~~~java
import jakarta.persistence.*;

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

    protected PurchaseOrder() {}

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    private String fullName;

    protected Customer() {}
}
~~~

Các khai báo khác nhau mang trách nhiệm riêng:

- **`@ManyToOne`** mô tả liên kết nhiều đơn hàng tới một khách hàng; mỗi đơn hàng chỉ chứa một tham chiếu `customer`.
- **`fetch = LAZY`** yêu cầu trì hoãn tải entity khách hàng khi có thể; đây là chiến lược fetch, không phải ràng buộc toàn vẹn.
- **`optional = false`** khai báo quan hệ bắt buộc về mặt mô hình đối tượng; Hibernate có thể dùng thông tin này cho nullability và tối ưu hóa. Nó không thay thế constraint trong DBMS.
- **`@JoinColumn(nullable = false)`** mô tả cột join không cho null trong DDL mà ORM tạo và trong metadata ánh xạ. Schema đã triển khai chỉ thực thi điều này khi có constraint thực tế.
- **`@ForeignKey(name = ...)`** mô tả tên constraint khi Hibernate tham gia tạo DDL. Nó không tự thay đổi database đã tồn tại nếu ứng dụng chỉ dùng migration do công cụ khác quản lý.

Nếu bảng hiện tại có `customer_id` không ràng buộc, thêm `@JoinColumn(nullable = false)` trong mã mà không chạy migration **không biến cột đã tồn tại thành NOT NULL**. Tương tự, một annotation nói FK tồn tại không đồng nghĩa DB đang thực thi nó.

### 2.2. Quan hệ một-một cần thêm tính duy nhất

~~~java
@Entity
@Table(name = "user_profiles")
public class UserProfile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "user_id",
        nullable = false,
        unique = true,
        foreignKey = @ForeignKey(name = "fk_profile_user")
    )
    private AppUser user;

    protected UserProfile() {}
}
~~~

Với cách ánh xạ một-một dùng FK ở bảng `user_profiles`, cần đồng thời xem xét:

1. **FK:** `user_id` phải tham chiếu người dùng tồn tại.
2. **UNIQUE:** một người dùng không có nhiều profile cùng loại.
3. **NOT NULL:** chỉ thêm khi profile bắt buộc gắn với người dùng.
4. **Quy tắc xóa:** khi xóa người dùng, profile sẽ bị chặn xóa, xóa theo hoặc phải xử lý riêng tùy constraint và chính sách nghiệp vụ.

Chỉ có FK mà không có UNIQUE vẫn có thể tồn tại nhiều hàng profile cùng trỏ một user. Hibernate không thể bảo đảm ý nghĩa một-một nếu database và các đường ghi khác không thực thi ràng buộc tương ứng.

Một dạng một-một khác là **shared primary key** qua `@MapsId`:

~~~java
@Entity
@Table(name = "user_profiles")
public class UserProfile {
    @Id
    private Long id;

    @OneToOne(optional = false, fetch = FetchType.LAZY)
    @MapsId
    @JoinColumn(name = "id")
    private AppUser user;

    protected UserProfile() {}
}
~~~

Ở mô hình này, `user_profiles.id` vừa là primary key của profile vừa là foreign key đến `users.id`. Nó tránh cần một cột FK riêng và thường phù hợp với thực thể phụ có định danh phụ thuộc vào thực thể chính. Nhưng **schema hiện hữu phải được thiết kế/migration đúng**: việc thêm `@MapsId` vào entity không tự sửa dữ liệu cũ.

### 2.3. Bên sở hữu và `mappedBy`

Với quan hệ hai chiều, **bên sở hữu (owning side)** là phía ánh xạ FK hoặc join table và điều khiển việc cập nhật quan hệ ở database. Phía còn lại dùng `mappedBy` để chỉ ra thuộc tính sở hữu:

~~~java
// Trong Customer:
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();
~~~

Đối với một-một hai chiều, một phía sở hữu `@JoinColumn`; phía kia khai báo `@OneToOne(mappedBy = "...")`. **Sửa riêng field ở phía không sở hữu** mà không đồng bộ phía sở hữu có thể khiến trạng thái Java và FK ghi xuống database lệch nhau. Các helper method cập nhật cả hai phía trong bộ nhớ giúp tránh lỗi này.

## 3. Vì sao dữ liệu “mồ côi” có thể xuất hiện?

Một giá trị FK khác null nhưng không có bản ghi đích thường xuất hiện khi:

- **Cơ sở dữ liệu không có constraint FK**: schema được tạo thủ công, schema legacy, hoặc DDL từng bị cấu hình bỏ constraint.
- **Import/ETL hoặc script ghi dữ liệu theo thứ tự sai**: đơn hàng vào trước khách hàng và không có cơ chế hoãn constraint phù hợp.
- **Xóa dữ liệu bằng SQL trực tiếp** khi FK không tồn tại hoặc bị tắt: xóa customer nhưng để lại đơn hàng tham chiếu.
- **Migration hoặc đồng bộ giữa hệ thống không hoàn chỉnh**: ID bị ánh xạ sai, thiếu bản ghi cha, thay định danh mà không cập nhật con.
- **Cố ý dùng tham chiếu mềm** sang dữ liệu nằm ở dịch vụ hoặc database khác; FK vật lý không thể thực thi xuyên ranh giới đó.
- **Đường ghi bỏ qua ORM**: trigger, batch SQL, integration hoặc công cụ quản trị tạo dữ liệu không tuân thủ giả định trong entity.
- **Ràng buộc tenant không đầy đủ**: tham chiếu tới một khách hàng của tenant khác dù ID vật lý tồn tại, nếu chỉ kiểm tra ID đơn lẻ.

Ngoài broken FK vật lý còn có **bản ghi “không nhìn thấy”** vì `@Filter`, soft-delete restriction, tenant predicate hay quy tắc phân quyền. Không nên tự động sửa `customer_id` thành null chỉ vì truy vấn ORM không nhìn thấy customer; phải phân biệt **không tồn tại vật lý** với **không thuộc phạm vi được phép truy cập**.

## 4. Những kiểu lỗi có thể xuất hiện ở các giai đoạn khác nhau

| Giai đoạn | Ví dụ tình huống | Nhóm lỗi hoặc biểu hiện cần xem xét |
| --- | --- | --- |
| Khởi động `SessionFactory` | Mapping quan hệ sai, cột join không hợp lệ, thiếu entity đích | `MappingException`/`AnnotationException` hoặc lỗi boot tương ứng |
| `persist`/`flush` entity mới | Quan hệ bắt buộc null hoặc trỏ tới đối tượng transient chưa được lưu | `PropertyValueException`, `TransientPropertyValueException` hoặc lỗi tương ứng |
| Thực thi SQL ghi | FK/NOT NULL/UNIQUE/CHECK vi phạm trong DBMS | Lỗi JDBC được Hibernate chuyển thành `org.hibernate.exception.ConstraintViolationException`, hoặc wrapper `PersistenceException`/framework |
| `find`/lazy initialization | FK có giá trị nhưng hàng đích không tồn tại | Có thể gặp `EntityNotFoundException` khi khởi tạo reference/proxy; phụ thuộc cơ chế tải |
| Nạp quan hệ gắn `@NotFound(EXCEPTION)` | FK trỏ tới hàng đích không tồn tại | Theo Hibernate 6.x User Guide, có thể gặp `FetchNotFoundException` ngay trong lúc nạp association |
| Nạp quan hệ gắn `@NotFound(IGNORE)` | FK trỏ tới hàng đích không tồn tại | Hibernate trình bày association là `null`, có thể che khuất lỗi dữ liệu |
| Nạp quan hệ một-một | Nhiều hàng tương ứng một giá trị phải duy nhất | Hibernate có thể báo lỗi cardinality hoặc ứng dụng có kết quả khó dự đoán nếu schema thiếu UNIQUE |
| Query có filter/soft delete | Khóa đích tồn tại nhưng bị loại khỏi kết quả hợp lệ | Association không giải quyết được theo ngữ cảnh; không đồng nghĩa dữ liệu FK vật lý sai |

**Thời điểm báo lỗi quan trọng.** `entityManager.persist()` có thể chỉ thay đổi persistence context. SQL `INSERT`/`UPDATE` có thể phát khi `flush()` hoặc `commit()`; với `GenerationType.IDENTITY` hay một số thao tác khác có thể phát sớm hơn. Vì vậy bắt exception chỉ quanh `persist()` nhưng để commit ngoài phạm vi xử lý **không bảo đảm bắt được lỗi FK**.

Ngoài ra, `jakarta.validation.ConstraintViolationException` (lỗi Bean Validation) **khác** `org.hibernate.exception.ConstraintViolationException` (lỗi constraint SQL/JDBC). Chúng có nguyên nhân và điểm xử lý khác nhau mặc dù tên đơn giản giống nhau.

## 5. Ba cơ chế khác nhau: constraint DB, `@ForeignKey(NO_CONSTRAINT)` và `@NotFound`

Đây là điểm dễ nhầm nhất của quan hệ đơn trị khi dữ liệu legacy không sạch.

### 5.1. Có FK vật lý: lựa chọn mặc định nên ưu tiên

~~~sql
create table purchase_orders (
    id bigint primary key,
    customer_id bigint not null,
    constraint fk_order_customer
        foreign key (customer_id) references customers(id)
);
~~~

Với DBMS đang thực thi constraint, một `INSERT` hoặc `UPDATE` gán ID khách hàng không tồn tại sẽ bị từ chối. Khi xóa khách hàng còn đơn hàng tham chiếu, DBMS cũng áp dụng quy tắc FK: mặc định thường là chặn xóa, trừ khi schema quy định hành vi `ON DELETE` phù hợp.

Ưu điểm lớn là **tất cả các đường ghi cùng chịu một invariant**, kể cả JDBC thuần, công cụ migration, batch job hay dịch vụ không dùng Hibernate. Hibernate validation và annotation chỉ là lớp bổ sung; integrity thật sự thuộc DBMS.

### 5.2. `@ForeignKey(NO_CONSTRAINT)`: chỉ bỏ DDL FK

~~~java
import jakarta.persistence.ConstraintMode;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(
    name = "customer_id",
    foreignKey = @ForeignKey(ConstraintMode.NO_CONSTRAINT)
)
private Customer customer;
~~~

Khai báo này nói với công cụ tạo DDL của ORM **đừng tạo constraint FK** cho join column đó. Nó **không** có nghĩa “nếu không tìm thấy bản ghi customer thì trả null”, cũng không bảo đảm dữ liệu luôn hợp lệ. Nếu ứng dụng tự quản lý integrity và muốn giữ hành vi lazy mặc định, đây là một cơ chế khác `@NotFound`. Tuy nhiên, bỏ FK khiến trách nhiệm kiểm tra mọi đường ghi chuyển sang thiết kế ứng dụng và vận hành dữ liệu.

Một DB có constraint FK thật sự đã tồn tại sẽ không bị xóa chỉ vì source Java thêm `NO_CONSTRAINT`; cần migration nếu muốn thay đổi schema.

### 5.3. `@NotFound(EXCEPTION)`: chấp nhận schema không có FK nhưng báo lỗi tham chiếu hỏng

~~~java
import org.hibernate.annotations.NotFound;
import org.hibernate.annotations.NotFoundAction;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
@NotFound(action = NotFoundAction.EXCEPTION)
private Customer customer;
~~~

Theo Hibernate 6.x, `@NotFound` được thiết kế cho quan hệ mà database **không thực thi physical FK** và có thể có tham chiếu sai. Với `EXCEPTION` (giá trị mặc định), Hibernate kiểm tra xem target có tồn tại khi nạp association; nếu không, Hibernate ORM 6.x User Guide mô tả lỗi `FetchNotFoundException`.

Hai hệ quả cần cân nhắc:

1. **`@NotFound` ngầm hiểu không có FK constraint cho mục đích DDL**.
2. **Quan hệ đơn trị gắn `@NotFound` được xử lý eager**, ngay cả khi khai báo `fetch = LAZY`. Hibernate cần xác định target có thật để quyết định ném lỗi hay trả null.

Điều này làm thay đổi fetch plan, có thể tăng SQL hoặc kích thước kết quả khi truy vấn nhiều bản ghi. Nếu mục tiêu chính là phát hiện sai lệch dữ liệu một cách sớm và rõ ràng, `EXCEPTION` có giá trị; nhưng vẫn không thay thế constraint DB.

### 5.4. `@NotFound(IGNORE)`: biểu diễn target thiếu thành null

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
@NotFound(action = NotFoundAction.IGNORE)
private Customer customer;
~~~

Với dữ liệu `purchase_orders.customer_id = 999` mà không có customer ID 999, Hibernate trình bày `order.getCustomer() == null`. Cơ chế này hữu ích như **biện pháp tương thích tạm thời** khi phải đọc dữ liệu legacy chưa thể sửa ngay.

Nhưng có ba đánh đổi nghiêm trọng:

- **Mất phân biệt thông tin:** Java trả null cho cả cột FK thật sự null lẫn FK khác null nhưng không tìm thấy target. Muốn biết giá trị gốc phải có phương án quan sát dữ liệu độc lập.
- **Chi phí tải:** to-one relation có `@NotFound` không còn lazy theo yêu cầu thông thường; nó có thể gây truy vấn bổ sung/khác fetch plan.
- **Nguy cơ thay đổi dữ liệu:** trong một số tình huống flush/update, trạng thái association null có thể dẫn tới ghi đè giá trị FK hỏng ban đầu, nhất là khi update tĩnh bao gồm cột FK. Không nên xem `IGNORE` là chế độ chỉ đọc, an toàn tuyệt đối cho mọi thao tác ghi.

Nếu quan hệ bắt buộc về nghiệp vụ, `IGNORE` không “sửa” được đơn hàng thiếu khách hàng; nó chỉ giúp một đường đọc đi tiếp và có thể khiến logic nghiệp vụ xử lý sai. Cần quan sát, cảnh báo, kế hoạch sửa dữ liệu và xác định quyền đọc/ghi khi áp dụng.

### 5.5. Bảng quyết định nhanh

| Cách khai báo/thiết kế | Có FK vật lý? | Gặp target không tồn tại | Lazy to-one |
| --- | --- | --- | --- |
| Mapping JPA bình thường + FK trong DB | Có, nên là mặc định | DB ngăn phát sinh qua đường ghi hợp lệ; dữ liệu cũ cần xử lý trước khi thêm FK | Theo mapping và khả năng Hibernate |
| Mapping JPA + `NO_CONSTRAINT` | Không sinh FK qua Hibernate DDL | Hành vi runtime thông thường; lỗi có thể xuất hiện lúc dereference/proxy initialization | Không bị `NO_CONSTRAINT` buộc eager |
| `@NotFound(EXCEPTION)` | Ngầm không tạo FK | Báo lỗi khi nạp association; Hibernate 6.x mô tả `FetchNotFoundException` | **Eager** |
| `@NotFound(IGNORE)` | Ngầm không tạo FK | Coi association như null | **Eager** |

Nếu DB đã có ràng buộc ngoại lai và dữ liệu tuân thủ nó, **không cần `@NotFound`**. Khi muốn dữ liệu không nhất quán được phản ánh rõ thành lỗi, thường nên sửa dữ liệu rồi thêm constraint thay vì duy trì vĩnh viễn logic bỏ qua.

## 6. Tình huống đọc: phân biệt target ID không tồn tại và proxy chưa được khởi tạo

Giả sử mapping thường có `fetch = FetchType.LAZY` và FK khác null trỏ đến ID không tồn tại. Một code path có thể trông như sau:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 101L);
Customer customer = order.getCustomer();

// Tùy proxy / fetching, thao tác này có thể kích hoạt truy vấn tải Customer:
String name = customer.getFullName();
~~~

Không thể cam kết lỗi nhất thiết phát sinh tại `find()`, `getCustomer()` hay `getFullName()` trong mọi configuration. Khi Hibernate sử dụng proxy cho một association, đối tượng đại diện có thể tồn tại trước khi target được tải. Việc khởi tạo proxy mới phát hiện target thiếu và có thể ném `jakarta.persistence.EntityNotFoundException` hoặc một ngoại lệ Hibernate liên quan.

Ngược lại, gọi:

~~~java
Customer customer = entityManager.find(Customer.class, 999L);
~~~

khi không có khách hàng ID 999 thường trả `null` (nếu không có ngoại lệ khác). Còn:

~~~java
Customer reference = entityManager.getReference(Customer.class, 999L);
~~~

có thể trả về reference chưa được xác thực ngay; khi truy cập để tải dữ liệu thực sự mới có thể ném `EntityNotFoundException`. `getReference()` không phải một thao tác “kiểm tra tồn tại” đáng tin cậy trước khi tạo liên kết.

Vì thế **API trả 404 cho một đơn hàng không tồn tại** khác với **đơn hàng tồn tại nhưng quan hệ customer bị hỏng**. Trường hợp sau là sự cố integrity nội bộ, không nên bị biến nhầm thành thông báo “khách hàng không tồn tại” cho phía người dùng nếu nó che mất vấn đề dữ liệu.

## 7. Tình huống ghi: tham chiếu transient, null, FK sai và thời điểm flush

### 7.1. Gán một entity chưa được lưu

~~~java
PurchaseOrder order = new PurchaseOrder();
order.setCustomer(new Customer()); // Customer chưa có ID hợp lệ/chưa được lưu.
entityManager.persist(order);
~~~

Nếu quan hệ không có cascade persist thích hợp và customer là đối tượng transient, Hibernate có thể ném `TransientPropertyValueException`, `TransientObjectException` hoặc lỗi tương ứng. Điều này **khác** trường hợp khóa ngoại đã có giá trị nhưng target bị xóa khỏi DB. Hibernate nhận thấy đối tượng tham chiếu chưa có trạng thái persistent được chấp nhận để ghi FK.

Giải pháp đúng thường là tải customer managed đã tồn tại hoặc lưu customer mới **có chủ đích** trong cùng transaction nếu nghiệp vụ cho phép. Không bật `cascade = CascadeType.ALL` chỉ để tránh lỗi khi một đơn hàng tham chiếu khách hàng độc lập: cascade persist/remove có thể làm thay đổi vòng đời entity không mong muốn.

### 7.2. Gán target theo ID nhưng bản ghi không tồn tại

~~~java
Customer customerRef = entityManager.getReference(Customer.class, customerId);
order.setCustomer(customerRef);
entityManager.persist(order);
~~~

`getReference` không nhất thiết kiểm tra ngay bản ghi ID đó có thật. Nếu ID không tồn tại và DB có FK constraint, `INSERT` thường bị từ chối khi SQL được thực thi. Nếu schema không có FK, có thể ghi thành công **tham chiếu mồ côi** rồi lỗi mới xuất hiện ở lượt đọc sau.

Nếu API cần trả lỗi thân thiện khi khách hàng không tồn tại, có thể gọi `find` và kiểm tra, nhưng **kiểm tra trước không thay thế FK**: sau khi `find` thành công, transaction khác vẫn có thể xóa hàng đích trước khi transaction này ghi, tùy isolation và locking. DB constraint là lớp bảo vệ cuối cùng.

### 7.3. Mapping bắt buộc nhưng FK null

~~~java
@ManyToOne(optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

Nếu `customer` null khi ghi, Hibernate có thể phát hiện không hợp lệ trước khi gửi SQL, hoặc DB từ chối ở thời điểm SQL thực thi tùy cấu hình. Vì vậy cả hai mức đều cần được thiết kế: **validate đầu vào/case nghiệp vụ** và **NOT NULL/FK constraint thực tế**.

### 7.4. Lỗi có thể chỉ phát khi commit

~~~java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public void createOrder(SessionFactory sessionFactory, PurchaseOrder order) {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            session.persist(order);
            tx.commit(); // SQL/constraint error có thể xuất hiện ở đây.
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    }
}
~~~

Sau lỗi Hibernate/JDBC khi flush hoặc ghi transaction, **rollback và bỏ session/persistence context hiện tại**. Đừng tiếp tục sửa entity rồi gọi commit lại trên cùng session với giả định mọi action queue và snapshot vẫn hợp lệ.

Trong Spring/JPA, việc commit có thể do transaction interceptor thực hiện **sau khi phương thức `@Transactional` trả về**. Một `try/catch` chỉ bao quanh `persist()` trong service có thể không bắt được lỗi DB xảy ra lúc interceptor commit. Hãy xử lý ở **ranh giới transaction** và lớp exception translation phù hợp, ví dụ `DataIntegrityViolationException` trong hệ sinh thái Spring, với cách unwrap cause có kiểm soát.

## 8. Phát hiện khóa ngoại mồ côi bằng SQL

Khi nghi ngờ data integrity, cách đáng tin cậy nhất là **kiểm tra schema và dữ liệu vật lý**. Với ví dụ đơn hàng–khách hàng:

~~~sql
select
    o.id as order_id,
    o.customer_id
from purchase_orders o
left join customers c on c.id = o.customer_id
where o.customer_id is not null
  and c.id is null
order by o.id;
~~~

Câu này liệt kê các đơn hàng có giá trị `customer_id` khác null nhưng không có hàng khách hàng tương ứng. Một cách viết khác với `NOT EXISTS`:

~~~sql
select o.id, o.customer_id
from purchase_orders o
where o.customer_id is not null
  and not exists (
      select 1
      from customers c
      where c.id = o.customer_id
  );
~~~

SQL trên dùng tên bảng/cột minh họa; áp dụng cho schema thực phải thay đúng identifier/tenant key. Nếu dữ liệu có tenant, việc join chỉ theo `id` có thể bỏ sót sai lệch logic:

~~~sql
-- Ví dụ chỉ phù hợp nếu cả hai bảng đều có tenant_id.
select o.id, o.tenant_id, o.customer_id
from purchase_orders o
left join customers c
       on c.id = o.customer_id
      and c.tenant_id = o.tenant_id
where o.customer_id is not null
  and c.id is null;
~~~

Ở đây một hàng có thể trỏ tới customer ID tồn tại nhưng của tenant khác. FK đơn cột trên `customer_id` có thể không ngăn lỗi này; cần xem xét unique key/foreign key ghép hoặc cơ chế bảo đảm tenant tại DB/app tùy mô hình.

### 8.1. Kiểm tra null ở quan hệ bắt buộc

~~~sql
select id
from purchase_orders
where customer_id is null;
~~~

Nếu yêu cầu nghiệp vụ là tất cả đơn hàng phải có customer, đây là danh sách cần sửa trước khi áp dụng `NOT NULL`. Cột null và FK sai là hai nhóm xử lý khác nhau: hàng null có thể cần gắn lại customer; hàng trỏ sai cần xác định ID gốc đúng hay xóa tham chiếu tùy nghiệp vụ.

### 8.2. Kiểm tra quan hệ một-một bị trùng

Giả sử `user_profiles.user_id` lẽ ra duy nhất:

~~~sql
select user_id, count(*) as duplicate_count
from user_profiles
where user_id is not null
group by user_id
having count(*) > 1;
~~~

Nếu truy vấn trả nhiều hàng, schema không thực thi uniqueness như mô hình một-một mong muốn. Đừng thêm `UNIQUE` trước khi xử lý dữ liệu trùng, và đừng chọn một profile ngẫu nhiên để giữ mà không dựa trên quy tắc nghiệp vụ/audit.

### 8.3. Phân biệt broken FK với soft delete và filter

Nếu bảng customer có cột `deleted_at`, việc Hibernate loại những hàng đã soft-delete khỏi association **không có nghĩa** SQL anti-join vật lý trên sẽ tìm thấy chúng là broken FK. Hãy kiểm tra đồng thời hai phạm vi:

- **Toàn vẹn vật lý:** hàng customer có còn tồn tại theo PK/FK không?
- **Toàn vẹn logic:** customer có thuộc tenant hiện tại, đang hoạt động và được phép tham chiếu theo nghiệp vụ không?

Hai câu hỏi có thể cho hai câu trả lời khác nhau. Không nên dựa duy nhất vào việc `order.getCustomer() == null` để quyết định chạy script sửa dữ liệu.

## 9. Sửa dữ liệu sai: phải chọn đúng ngữ nghĩa

Khi đã có danh sách FK mồ côi, không tồn tại một lệnh sửa phù hợp cho tất cả trường hợp. Một số hướng xử lý:

| Tình huống | Chiến lược | Điều kiện phải xác minh |
| --- | --- | --- |
| Đơn hàng phải có khách hàng, ID sai do import | Khôi phục/đối chiếu đúng customer rồi cập nhật `customer_id` | Có căn cứ mapping ID; tránh gắn nhầm khách hàng và vi phạm bảo mật |
| Quan hệ thực sự tùy chọn | Đặt FK về null cho các bản ghi không còn target, có audit | Ứng dụng hiểu nghĩa null; không làm mất thông tin cần truy vết |
| Bản ghi cha bị xóa nhầm | Khôi phục bản ghi cha từ nguồn tin cậy | Phù hợp lịch sử, ràng buộc và quy tắc pháp lý/lưu trữ |
| Bản ghi con không còn giá trị | Xóa hoặc archive có kiểm soát | Được nghiệp vụ cho phép; xử lý mọi quan hệ phụ thuộc |
| Dữ liệu từ hệ thống ngoài | Chuyển FK cứng sang external identifier và cơ chế reconciliation | Đây thật sự là tham chiếu liên hệ ngoài, không phải association cùng DB |
| Parent soft-deleted | Xử lý visibility/retention rule thay vì xóa FK vật lý tùy tiện | Đánh giá nghiệp vụ khi parent bị ẩn |
| One-to-one có dữ liệu trùng | Dedupe, merge hoặc chuyển sang model 1-n có chủ đích | Có tiêu chí chọn bản ghi chuẩn và bảo toàn lịch sử |

Ví dụ sửa **chỉ khi** quan hệ được phép null và đã được nghiệp vụ phê duyệt:

~~~sql
-- Minh họa SQL tương đối phổ biến; nên xem số hàng ảnh hưởng trước.
update purchase_orders o
set customer_id = null
where o.customer_id is not null
  and not exists (
      select 1
      from customers c
      where c.id = o.customer_id
  );
~~~

Lệnh này có thể phá vỡ nghiệp vụ nếu đơn hàng bắt buộc có customer. Trong triển khai thật, cần xác định phạm vi, lưu danh sách bản ghi bị sửa, chạy trong transaction có kế hoạch rollback/khôi phục và khóa/điều phối nguồn ghi để tránh phát sinh inconsistency mới trong lúc sửa.

Khi dùng `@NotFound(IGNORE)`, một số bản ghi hỏng có thể vẫn xuất hiện như null trong object graph. Việc sửa từ ORM mà không phân biệt FK gốc là **rủi ro**; SQL kiểm kê dữ liệu vật lý đáng tin cậy hơn cho công tác reconciliation.

## 10. Đưa constraint trở lại sau khi sửa dữ liệu

Nếu nghiệp vụ cho phép FK vật lý, tiến trình bền vững thường là:

1. **Đo lường** số lượng null, orphan FK và duplicate của quan hệ một-một.
2. **Phân loại** theo nguồn sinh dữ liệu, tenant, ngày tạo, quy tắc xóa/soft delete.
3. **Sửa nguyên nhân ghi sai**: batch import, migration, mapper, code cập nhật quan hệ, dịch vụ ngoài.
4. **Sửa dữ liệu hiện có** bằng script có audit và chạy trên bản sao môi trường trước.
5. **Thêm hoặc xác thực constraint** tại DB: FK, NOT NULL, UNIQUE theo đúng cardinality và nghiệp vụ.
6. **Giám sát** để phát hiện lại ngay khi hệ thống có đường ghi mới.

Với bảng lớn, thêm FK có thể khóa hoặc quét bảng tùy DBMS. PostgreSQL có một lựa chọn riêng cho việc thêm constraint mà chưa xác thực toàn bộ bản ghi cũ:

~~~sql
-- PostgreSQL-specific: kiểm tra phiên bản, lock và kế hoạch migration.
alter table purchase_orders
add constraint fk_order_customer
foreign key (customer_id) references customers(id)
not valid;

-- Sau khi đã sửa dữ liệu cũ:
alter table purchase_orders
validate constraint fk_order_customer;
~~~

Trong PostgreSQL, constraint `NOT VALID` đối với FK vẫn thực thi trên các thay đổi mới phù hợp, còn dữ liệu tồn tại trước đó được xác thực khi chạy `VALIDATE CONSTRAINT`. Đây **không phải SQL portable**; ở DBMS khác, chiến lược online migration, mức khóa và cú pháp khác. Không được xem `NOT VALID` là cách bỏ qua việc sửa dữ liệu cũ mãi mãi.

Với quan hệ một-một, nếu cần thêm `UNIQUE(user_id)`, phải giải quyết duplicate trước. Với quan hệ bắt buộc, thêm `NOT NULL` sau khi xử lý mọi giá trị null; ngoại lệ và kiểu DDL cụ thể tùy DBMS.

## 11. Thiết kế ứng dụng xử lý lỗi cho người dùng và vận hành

Một API thường cần tách ba lớp lỗi:

1. **Sai đầu vào/ngữ nghĩa nghiệp vụ:** người dùng gửi ID customer không tồn tại hoặc không thuộc quyền; application service có thể trả phản hồi xác định, ví dụ 400/404/422 theo hợp đồng API.
2. **Xung đột thao tác đồng thời:** customer vừa bị xóa/đổi trạng thái, thao tác ghi vi phạm FK/lock/version; trả phản hồi phù hợp, đôi khi 409 Conflict nếu là xung đột có thể xử lý từ client.
3. **Bất nhất dữ liệu đã lưu:** DB chứa đơn hàng với FK trỏ sai hoặc one-to-one trùng; đây thường là lỗi integrity phía server cần log, cảnh báo và sửa dữ liệu, không nên giả là lỗi đầu vào bình thường của request.

~~~mermaid
flowchart TD
    A[Yêu cầu gắn Customer vào Order] --> B[Kiểm tra ID và quyền truy cập]
    B --> C{Customer hợp lệ theo nghiệp vụ?}
    C -- Không --> D[Trả lỗi đầu vào/không thấy theo API]
    C -- Có --> E[Thực hiện transaction và ghi FK]
    E --> F{DB chấp nhận commit?}
    F -- Có --> G[Trả kết quả]
    F -- Không --> H[Rollback, phân loại constraint/concurrency]
    H --> I[Log có cấu trúc và phản hồi an toàn]
~~~

### 11.1. Ví dụ service đọc DTO với ranh giới dữ liệu rõ ràng

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderView getOrder(long orderId) {
        PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

        if (order == null) {
            throw new OrderNotFoundException(orderId);
        }

        Customer customer = order.getCustomer();

        if (customer == null) {
            // Chỉ đúng nếu liên kết customer bắt buộc theo nghiệp vụ.
            throw new IllegalStateException(
                    "Order has no valid customer: " + orderId
            );
        }

        return new OrderView(orderId, customer.getId());
    }
}

public record OrderView(Long orderId, Long customerId) {}
~~~

`OrderNotFoundException` là exception nghiệp vụ giả định. Mã này mô tả rõ **order không tồn tại** và **order tồn tại nhưng không có valid customer** là hai tình huống khác nhau. Khi có broken FK và mapping lazy thông thường, Hibernate có thể ném exception **trước khi** vào nhánh kiểm tra `customer == null`; vì thế handler ở ranh giới service/transaction còn phải phân loại lỗi ORM.

Nếu dùng `@NotFound(IGNORE)`, `customer == null` có thể bao gồm trường hợp cột `customer_id` khác null nhưng target biến mất. Service không có đủ thông tin để tự quyết định lỗi là “không có customer” hay “tham chiếu hỏng” chỉ từ field này. Muốn audit phải có một nguồn kiểm kê FK gốc hoặc truy vấn thích hợp.

### 11.2. Không biến mọi integrity error thành “không tìm thấy”

Trong ứng dụng Spring, framework có thể translate lỗi ghi constraint thành `DataIntegrityViolationException`; trong JPA thuần, có thể thấy `PersistenceException` cùng các cause Hibernate/JDBC. Cách chuyển đổi này phụ thuộc integration, phiên bản và vị trí transaction kết thúc.

Phân loại nên dựa trên **constraint name**, SQLState/vendor error code hoặc loại nguyên nhân có thể xác nhận; không so khớp toàn bộ exception message như hợp đồng ổn định. Một `ConstraintViolationException` cũng có thể do UNIQUE, NOT NULL hoặc CHECK, không riêng FK. Không nên trả nguyên SQL, tên bảng nhạy cảm hay dữ liệu nội bộ cho client.

Trong khi log để điều tra, nên ghi business correlation ID, loại thao tác, entity ID, constraint name/SQLState nếu được phép, transaction outcome và số lượng bản ghi liên quan. Tránh đưa thông tin cá nhân hoặc toàn bộ payload vào log.

### 11.3. Chọn chính sách retry hợp lý

- **FK sai do customer ID không tồn tại:** retry nguyên request không làm dữ liệu đúng lên; cần sửa đầu vào hoặc đồng bộ bản ghi cha.
- **Xung đột optimistic locking/deadlock tạm thời:** có thể retry một unit of work mới theo policy và giới hạn lần thử, với thao tác có tính idempotent.
- **Data integrity đã hỏng trong DB:** retry chỉ lặp lỗi; nên cảnh báo, cách ly công việc hoặc sửa dữ liệu.
- **Tham chiếu tới hệ thống ngoài chưa đồng bộ:** có thể đặt cơ chế eventual consistency/reconciliation và retry theo thời hạn nghiệp vụ, thay vì cố ánh xạ thành FK cứng không thể thực thi.

Sau một lỗi transaction, rollback rồi mở transaction/session **mới** trước khi retry. Không retry trên một persistence context đã gặp lỗi flush.

## 12. Xóa entity cha: `cascade`, `orphanRemoval` và `ON DELETE`

Một lỗi FK thường xuất hiện khi xóa khách hàng trong lúc còn nhiều đơn hàng:

~~~sql
delete from customers where id = 10;
~~~

Nếu bảng `purchase_orders` có FK `customer_id` tham chiếu `customers.id` và không có hành vi xóa liên đới, DB có thể từ chối. Không nên mặc định rằng Hibernate có thể tự xóa mọi tham chiếu chỉ vì mapping có `@ManyToOne`.

Cần phân biệt:

| Cơ chế | Ai điều phối | Ý nghĩa thực tế |
| --- | --- | --- |
| `CascadeType.REMOVE` | JPA/Hibernate | Lan truyền thao tác xóa entity theo hướng association đã mapping; phải xét ownership và vòng đời đối tượng. |
| `orphanRemoval = true` | JPA/Hibernate trên association hỗ trợ | Xóa entity con khi bị tách khỏi quan hệ sở hữu có semantics phù hợp; **không** phải công cụ sửa FK trỏ sai nói chung. |
| FK `ON DELETE RESTRICT/NO ACTION` | DBMS | Ngăn xóa parent khi còn child tham chiếu (theo thời điểm constraint được kiểm tra). |
| FK `ON DELETE CASCADE` | DBMS | Khi parent bị xóa, DB tự xóa child tương ứng, theo schema thực. |
| FK `ON DELETE SET NULL` | DBMS | Khi parent bị xóa, DB đặt FK của child thành null; chỉ có ý nghĩa khi cột/quan hệ cho phép null. |
| Soft delete | Ứng dụng/mapping | Giữ hàng vật lý, thay trạng thái hiển thị. FK vẫn có thể hợp lệ về vật lý nhưng association có thể bị filter. |

`CascadeType.REMOVE` trên một quan hệ `@ManyToOne` trỏ tới entity dùng chung như `Customer` thường là **rủi ro**: xóa một order không được vô tình xóa customer đang được nhiều order khác tham chiếu. Khi vòng đời con phụ thuộc cha trong one-to-one, cascade/orphan removal có thể phù hợp hơn nhưng vẫn phải thiết kế cụ thể.

Nếu DB dùng `ON DELETE CASCADE` mà Hibernate còn giữ entity bị ảnh hưởng trong persistence context, cần hiểu phạm vi đồng bộ và tình trạng stale state. Tùy mapping và thao tác, không nên giả định mọi object managed được cập nhật lập tức sau một lệnh xóa cascade do DB tự thực hiện.

## 13. Quan hệ một-một có những lỗi riêng

### 13.1. Thiếu UNIQUE

`@OneToOne` biểu diễn mỗi owner có nhiều nhất một target. Nếu FK lưu ở bảng con và không có unique constraint, hai hàng con có thể cùng trỏ một owner. Query inverse one-to-one có thể tìm thấy nhiều target cho cùng ID và Hibernate có thể ném exception khi tải. Sửa mapping Java mà bỏ qua dữ liệu trùng không khắc phục được vấn đề.

### 13.2. Phía inverse không biết association null hay có dữ liệu

Ở quan hệ một-một hai chiều mà FK nằm ở bảng con, khi chỉ tải bảng cha, Hibernate có thể cần truy vấn phụ để biết một target có tồn tại không. `fetch = LAZY` ở phía inverse không phải lúc nào được tôn trọng theo kỳ vọng nếu không có bytecode enhancement/cấu hình phù hợp. Nếu hàng con bị thiếu hoặc trùng, hành vi tải càng nhạy cảm. Không nên dùng “đổi hết sang LAZY” như một biện pháp sửa dữ liệu inconsistent.

### 13.3. `@MapsId` và tính toàn vẹn

Với shared primary key one-to-one, ID của con đồng thời tham chiếu parent. Nếu con tồn tại mà parent không còn, đây là broken FK. Nếu parent tồn tại nhưng con chưa được tạo, bản thân điều đó **không nhất thiết** vi phạm FK của bảng con; nó có thể là trạng thái thiếu cấu phần theo quy tắc nghiệp vụ. DB constraint một chiều không bảo đảm “mỗi parent phải có đúng một child”; yêu cầu này có thể cần quy trình tạo đồng thời, kiểm tra nghiệp vụ hoặc cấu trúc schema phù hợp.

## 14. Concurrency, isolation và ràng buộc nhiều tenant

Ngay cả khi ứng dụng gọi `find(Customer.class, id)` rồi mới ghi order, vẫn có thể có race:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as Transaction B
    participant DB as Database
    A->>DB: SELECT customer id=10 (có hàng)
    B->>DB: DELETE customer id=10
    B->>DB: COMMIT
    A->>DB: INSERT order customer_id=10
    DB-->>A: FK violation nếu constraint đang thực thi
~~~

Nếu không có DB FK, transaction A có thể ghi orphan FK. Đây là ví dụ vì sao kiểm tra ở application là cần thiết cho thông báo nghiệp vụ nhưng không thay thế constraint. Các mức isolation và chiến lược khóa có thể thay đổi trình tự/khả năng các thao tác; kế hoạch cụ thể cần dựa trên DBMS.

Trong hệ thống multi-tenant dùng một schema chung, chỉ có `customer_id` có thể không đủ để bảo đảm customer cùng tenant. Ví dụ:

~~~sql
-- Mô hình minh họa: mỗi customer có (tenant_id, id) duy nhất.
alter table customers
add constraint uq_customers_tenant_id_id unique (tenant_id, id);

alter table purchase_orders
add constraint fk_order_customer_same_tenant
foreign key (tenant_id, customer_id)
references customers (tenant_id, id);
~~~

Khóa ngoại ghép này chỉ phù hợp nếu các cột, nullability và unique/primary key đã được thiết kế tương thích. Cần đánh giá ngữ nghĩa null của composite FK và chính sách tenant cho mọi bảng. Nếu dữ liệu được bảo vệ bằng row-level security, filter hoặc `@TenantId`, cũng phải xác định cách integrity vật lý được thực thi. **Filter nhìn thấy ít hàng hơn không đồng nghĩa FK vật lý có thể dùng cùng điều kiện filter.**

## 15. Thiết kế theo tình huống: chọn giải pháp nào?

### Tình huống A — Đơn hàng luôn phải có khách hàng

**Chọn:** `@ManyToOne(optional=false)`, `@JoinColumn(nullable=false)`, cột NOT NULL và FK constraint tại DB. Application service kiểm tra ID và quyền truy cập trước, DB là tuyến bảo vệ cuối. Không dùng `@NotFound(IGNORE)` để che lỗi, vì một order không có valid customer là dữ liệu không thỏa invariant nghiệp vụ.

### Tình huống B — Hệ thống legacy có hàng nghìn FK mồ côi nhưng cần đọc tiếp

**Chọn theo giai đoạn:** kiểm kê anti-join, sửa đường ghi, phân loại dữ liệu, migration từng phần. Trong thời gian chuyển tiếp, `@NotFound(EXCEPTION)` hữu ích nếu muốn lỗi xuất hiện sớm; `@NotFound(IGNORE)` chỉ khi ứng dụng có thể hợp lệ hóa association null và có cơ chế audit FK hỏng riêng. Theo dõi số lượng dữ liệu bị che và chi phí eager fetch, sau đó loại bỏ giải pháp tạm nếu DB có thể được ràng buộc.

### Tình huống C — Profile thực sự tùy chọn

**Chọn:** một-một có uniqueness tương ứng, nhưng không tạo profile khi user chưa hoàn tất onboarding. Một user không có profile là trạng thái hợp lệ, khác với profile có FK user không tồn tại. Nếu profile dùng shared primary key và lưu ở bảng con, việc user không có child không vi phạm FK chiều child → user.

### Tình huống D — Dịch vụ A lưu ID của tài nguyên thuộc dịch vụ B

**Chọn:** xem đó là **external reference** thay vì tự động mô hình hóa thành `@ManyToOne` tới một entity không có cùng database/transaction. Sử dụng identifier bất biến, trạng thái xác nhận, retry/reconciliation và quy tắc eventual consistency; FK vật lý không thể áp dụng xuyên database/service boundary theo cách thông thường. Không lạm dụng `@NotFound(IGNORE)` để biến một hợp đồng tích hợp không đáng tin cậy thành quan hệ ORM giả.

### Tình huống E — Xóa người dùng nhưng vẫn cần giữ lịch sử đơn hàng

**Chọn:** xác định chính sách lưu trữ, anonymization hoặc soft delete. Tránh xóa cứng parent làm order mất tham chiếu nếu nghiệp vụ yêu cầu truy vết. FK có thể đặt RESTRICT, còn ứng dụng xử lý trạng thái người dùng không hoạt động. Không gắn `CascadeType.REMOVE` từ order sang user.

## 16. Những nguyên tắc để tránh lỗi tái phát

1. **Định nghĩa rõ association bắt buộc hay tùy chọn.** Null có thể hợp lệ; FK trỏ target không tồn tại là một trạng thái khác.
2. **Đặt ràng buộc thực thi tại DB nếu có thể.** FK, NOT NULL và UNIQUE bảo vệ cả các đường ghi ngoài Hibernate.
3. **Đừng nhầm DDL annotation với schema thật.** `@JoinColumn(nullable=false)` và `@ForeignKey` không tự sửa bảng đã triển khai.
4. **Dùng `@NotFound` có chủ đích.** `IGNORE` che broken FK thành null; cả `IGNORE` và `EXCEPTION` khiến to-one association eager và ngầm không tạo FK qua Hibernate DDL.
5. **Phân biệt thời điểm phát lỗi.** Lỗi có thể xuất hiện khi hydrate/proxy initialize, flush, commit hoặc khi DB từ chối DELETE.
6. **Sau lỗi SQL/flush phải rollback transaction và bỏ session.** Retry bằng transaction mới nếu lỗi có thể retry.
7. **Không bật cascade xóa mù quáng.** Vòng đời parent/child và quy tắc ON DELETE phải phản ánh nghiệp vụ.
8. **Phân biệt broken FK vật lý với target bị filter/soft-delete/tenant ẩn.** Sửa dữ liệu chỉ sau khi xác nhận đúng nguyên nhân.
9. **Kiểm kê và migration trước khi thêm constraint.** Dữ liệu hiện có phải được khôi phục/dedupe theo quy tắc, rồi mới validate ràng buộc.
10. **Ghi log và giám sát ở ranh giới transaction.** Dùng constraint name, SQLState/cause, correlation ID và metric số bản ghi hỏng; không để lỗi integrity bị diễn giải thành lỗi input bình thường.

## 17. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide – Associations / `@NotFound`](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): mô tả `NotFoundAction.EXCEPTION`, `IGNORE`, hệ quả eager fetch và quan hệ không có physical foreign key.
- [Hibernate ORM 6.6 `PropertyValueException` Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/PropertyValueException.html): những trường hợp null không hợp lệ và tham chiếu entity transient chưa được lưu.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn đúng user guide và migration guide của phiên bản đang dùng.
- [Jakarta Persistence API](https://jakarta.ee/specifications/persistence/): đặc tả chuẩn của `@ManyToOne`, `@OneToOne`, `@JoinColumn`, `@ForeignKey`, `EntityManager`, `EntityNotFoundException` và transaction behavior.

Đối với quan hệ đơn trị, câu hỏi quan trọng nhất là **“DB có thực sự bảo đảm bản ghi tham chiếu tồn tại và có đúng một bản ghi đích theo quy tắc hay không?”**. Mapping Hibernate mô tả quan hệ và quyết định cách nạp entity; constraint DB bảo vệ dữ liệu; logic application quyết định phản hồi nghiệp vụ; công cụ migration và audit sửa sai lệch lịch sử. Giữ rõ bốn vai trò này giúp vừa xử lý an toàn những FK đã hỏng, vừa ngăn dữ liệu tương tự tiếp tục phát sinh.
