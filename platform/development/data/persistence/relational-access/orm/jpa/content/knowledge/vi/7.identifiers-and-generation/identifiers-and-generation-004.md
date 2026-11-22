# Vai trò của @GeneratedValue và chiến lược AUTO trong JPA

Khi một ứng dụng Java lưu entity mới vào cơ sở dữ liệu quan hệ, nó cần xác định **khóa chính** để phân biệt từng bản ghi. Nếu mỗi lần tạo khách hàng, đơn hàng hoặc sản phẩm đều phải tự nghĩ ra một giá trị `id`, ứng dụng dễ gặp lỗi trùng khóa, xử lý đồng thời phức tạp và phải phụ thuộc vào quy tắc cấp số thủ công.

Trong **Jakarta Persistence (JPA)**, annotation **`@GeneratedValue`** khai báo rằng giá trị khóa chính của entity sẽ được cấp bằng một cơ chế sinh định danh. Trong các chiến lược mà JPA cung cấp, **`GenerationType.AUTO`** cho phép **JPA provider quyết định cách sinh khóa phù hợp** dựa trên khả năng của cơ sở dữ liệu, kiểu khóa và cấu hình của provider.

Ví dụ ngắn gọn:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

Ở đây, lập trình viên tạo sản phẩm bằng `new Product("Bàn phím")` và không phải tự gán `id`. JPA provider phối hợp với database hoặc một cơ chế tạo giá trị để cấp định danh trước hoặc trong quá trình lưu. Tuy vậy, **`AUTO` không có nghĩa database nào cũng dùng cùng thuật toán** và cũng không phải lời hứa rằng ID luôn có ngay khi gọi constructor.

## 1. Khóa chính là gì và vì sao cần sinh tự động?

Trong cơ sở dữ liệu quan hệ, **primary key** (khóa chính) là một hoặc nhiều cột xác định duy nhất một hàng. Ví dụ bảng `products`:

| id | name |
| ---: | --- |
| 101 | Bàn phím |
| 102 | Chuột |
| 103 | Màn hình |

Giá trị `id` phải phân biệt được các hàng. Ở mức JPA, một entity cũng cần thuộc tính định danh, thường được đánh dấu bằng `@Id`:

```java
@Id
private Long id;
```

Nếu không dùng cơ chế sinh tự động, mã ứng dụng có thể phải cung cấp khóa:

```java
Product product = new Product();
product.setId(101L); // Ví dụ về khóa do ứng dụng tự cấp.
entityManager.persist(product);
```

Cách tự cấp có thể phù hợp với khóa đến từ hệ thống bên ngoài hoặc quy tắc nghiệp vụ có chủ đích, nhưng không phù hợp nếu nhiều request đều tự tính `MAX(id) + 1`. Hai transaction cùng đọc giá trị lớn nhất có thể chọn cùng khóa, rồi một transaction gặp lỗi trùng khóa.

Với `@GeneratedValue`, **cơ chế sinh giá trị định danh được khai báo trong mapping**, còn ứng dụng tập trung vào dữ liệu nghiệp vụ:

```java
Product product = new Product("Bàn phím");
entityManager.persist(product);

// ID sẽ được cấp theo cơ chế sinh khóa đã chọn.
// Thời điểm có thể đọc được ID phụ thuộc strategy/provider.
```

Cần phân biệt các trách nhiệm:

- **`@Id`**: cho JPA biết thuộc tính nào là **định danh của entity**.
- **`@GeneratedValue`**: cho JPA biết định danh đó **được sinh bằng cơ chế được cấu hình**.
- **Ràng buộc `PRIMARY KEY` của database**: đảm bảo định danh hợp lệ và không trùng ở tầng dữ liệu, kể cả khi có ứng dụng khác ghi trực tiếp vào bảng.

`@GeneratedValue` không thay thế `@Id` hay ràng buộc khóa chính trong schema. Nó cũng **không tự tạo một khóa nghiệp vụ có ý nghĩa**, như số hóa đơn hiển thị cho khách hàng.

## 2. @GeneratedValue khai báo điều gì?

Annotation nằm trong package:

```java
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
```

Cú pháp thường gặp:

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

`@GeneratedValue` có hai thuộc tính chính cần biết:

| Thuộc tính | Công dụng | Ví dụ |
| --- | --- | --- |
| `strategy` | Chọn chiến lược sinh khóa. | `GenerationType.AUTO`, `IDENTITY`, `SEQUENCE`, `TABLE`; Jakarta Persistence mới còn có `UUID`. |
| `generator` | Tham chiếu tên generator đã khai báo, khi sử dụng cơ chế generator tương ứng. | `@GeneratedValue(strategy = SEQUENCE, generator = "product_seq_gen")`. |

Nếu **không ghi `strategy`**, giá trị mặc định là `GenerationType.AUTO`. Hai cách dưới đây tương đương ở mức khai báo chiến lược:

```java
@Id
@GeneratedValue
private Long id;
```

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

Viết tường minh `AUTO` có thể giúp người đọc nhận biết ý định để provider lựa chọn; viết ngắn `@GeneratedValue` cũng là cách dùng hợp lệ.

### 2.1. @GeneratedValue áp dụng cho định danh nào?

Ứng dụng portable nên dùng `@GeneratedValue` với **khóa chính đơn** được đánh dấu bằng `@Id` và kiểu dữ liệu mà chiến lược sinh hỗ trợ, thường là các kiểu số như `Long`/`Integer`. Với Jakarta Persistence hiện đại, chiến lược `UUID` hỗ trợ định danh UUID theo quy định của phiên bản đặc tả.

Không nên mặc định áp dụng `@GeneratedValue` cho:

- Trường không phải khóa chính, chẳng hạn `orderNumber` hoặc `createdAt`.
- Mọi thành phần của khóa chính tổng hợp `@EmbeddedId` hoặc `@IdClass` rồi kỳ vọng mọi JPA provider hoạt động như nhau.
- Kiểu dữ liệu tùy ý mà provider hoặc chiến lược đã chọn không hỗ trợ.

Đối với khóa tổng hợp, nếu ứng dụng cần sinh một phần định danh, phải kiểm tra cơ chế provider hỗ trợ và tính di động của mapping. Trong một mô hình đơn giản, dùng khóa chính đơn được sinh tự động thường dễ quản lý hơn.

### 2.2. Vì sao thường dùng Long thay vì long?

Trong Java:

```java
private Long id;  // mặc định null khi entity mới được tạo
private long id;  // mặc định 0 khi entity mới được tạo
```

`Long` cho phép thể hiện rõ trạng thái “entity mới, chưa có khóa” bằng `null`. Đây là kiểu thường dùng cho khóa sinh tự động trong domain model JPA, đồng thời giúp tránh việc giá trị mặc định `0` bị hiểu nhầm là một định danh hợp lệ.

Dù vậy, **`id == null` không phải phép kiểm tra trạng thái entity đầy đủ trong mọi ngữ cảnh**. Một entity đã detached vẫn có ID; một entity mới được gán ID có thể chưa được lưu, và thời điểm nhận ID phụ thuộc cơ chế generator. Vòng đời `new`, `managed`, `detached` và `removed` cần được hiểu riêng với việc một trường `id` đang có giá trị.

## 3. GenerationType.AUTO thực sự làm gì?

`GenerationType.AUTO` là một **yêu cầu ở mức trừu tượng**: để JPA provider chọn chiến lược sinh định danh phù hợp. Provider có thể căn cứ vào:

1. **Khả năng của DBMS/dialect**, chẳng hạn hỗ trợ sequence, identity column hoặc cơ chế mô phỏng.
2. **Kiểu dữ liệu của khóa**, ví dụ kiểu số khác với kiểu `UUID`.
3. **Phiên bản và quy tắc nội bộ của provider**.
4. **Cấu hình generator**, naming strategy, persistence unit và những tuỳ chọn đặc thù đã khai báo.

Luồng khái quát:

```text
@Entity Product
    |
    +-- @Id
    +-- @GeneratedValue(strategy = AUTO)
                      |
                      v
                JPA provider
               (ví dụ Hibernate)
                      |
               Xem database/dialect,
               kiểu ID và cấu hình
                      |
             +--------+---------+
             |        |         |
          SEQUENCE  IDENTITY   TABLE
             |        |         |
             +--------+---------+
                      |
              Cơ sở dữ liệu
                      |
              ID cho entity mới

Một số trường hợp/phiên bản còn hỗ trợ sinh UUID.
```

**`AUTO` không phải là thuật toán “lấy số cuối cộng một”**. Nó cũng không khẳng định provider sẽ ưu tiên một chiến lược nhất định trên mọi hệ quản trị.

Ví dụ khi triển khai:

- Trên hệ quản trị có sequence, provider có thể dùng **sequence** để cấp ID.
- Trên hệ quản trị hỗ trợ cột identity/auto-increment, provider có thể chọn **identity** hoặc cơ chế khác.
- Nếu cần tạo khóa bằng bảng phụ, provider có thể sử dụng **table-based generator**.
- Với kiểu ID UUID và phiên bản Jakarta Persistence/provider hỗ trợ, chiến lược tự động có thể chọn cách tạo UUID thích hợp.

Các câu trên nêu **khả năng**, không phải bảng quy tắc cố định cho PostgreSQL, MySQL, Oracle hay một provider cụ thể. Quyết định thực tế phải được xác nhận từ cấu hình và SQL được tạo trong môi trường triển khai.

### 3.1. AUTO giúp điều gì?

`AUTO` hữu ích khi ứng dụng cần mô tả **ý định sinh khóa** nhưng chưa cần gắn mapping với cơ chế cụ thể:

```java
@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() {}

    public Book(String title) {
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

Khi chạy trên một database và provider đã cấu hình tương thích, cùng đoạn mapping có thể được sử dụng mà không phải viết mã tạo khóa thủ công.

Lợi ích chính là **giảm phụ thuộc trực tiếp của mã entity vào một thuật toán cấp phát khóa**. Tuy nhiên, chuyển hệ quản trị hoặc nâng cấp provider vẫn có thể thay đổi generator được lựa chọn, tên sequence/bảng phụ, số lượng khóa dự trữ hoặc thời điểm chạy SQL. Vì vậy, **AUTO không bảo đảm chuyển database mà không cần điều chỉnh schema/migration**.

### 3.2. AUTO không tự xác định chính xác schema

Ví dụ dưới đây là hai khả năng lưu trữ khác nhau:

**Cách A – dùng sequence để cấp giá trị `id`:**

```sql
-- PostgreSQL, ví dụ minh họa một sequence:
CREATE SEQUENCE books_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
```

Provider có thể lấy giá trị sequence rồi chèn bản ghi với `id` đã có:

```sql
SELECT nextval('books_id_seq');

INSERT INTO books (id, title) VALUES (?, ?);
```

**Cách B – dùng cột identity:**

```sql
-- PostgreSQL, ví dụ một schema khác:
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
```

Lúc đó database cấp ID khi thực thi `INSERT`; provider có thể gửi câu lệnh tương tự:

```sql
INSERT INTO books (title) VALUES (?);
```

Tùy driver/provider, ID có thể được lấy qua generated keys, `RETURNING` hoặc cơ chế thích hợp khác.

Hai schema trên là **hai phương án minh họa**, không phải schema mà `AUTO` cam kết sẽ tự chọn trong mọi trường hợp. Nếu ứng dụng tự quản lý bảng bằng Flyway hoặc Liquibase, schema phải khớp với chiến lược mà provider thực sự sử dụng. Không nên tạo một cột identity rồi giả định provider sẽ không tìm sequence, hoặc ngược lại.

## 4. So sánh AUTO với các chiến lược cụ thể

`GenerationType` có những lựa chọn quan trọng sau:

| Chiến lược | Cơ chế cốt lõi | Thời điểm/cách cấp khóa thường gặp | Điều cần quan tâm |
| --- | --- | --- | --- |
| **`AUTO`** | Provider lựa chọn cơ chế thích hợp. | Phụ thuộc chiến lược được chọn thực tế. | Cần biết provider/dialect/schema đang dùng gì. |
| **`IDENTITY`** | Cột identity/auto-increment do database sinh. | Thường cần thực thi `INSERT` để biết giá trị. | Có thể hạn chế JDBC insert batching và trì hoãn INSERT tùy provider. |
| **`SEQUENCE`** | Sử dụng database sequence. | Có thể lấy ID trước `INSERT`. | Cần sequence phù hợp, cấu hình allocation và đồng bộ với schema. |
| **`TABLE`** | Dùng bảng phụ để lưu trạng thái cấp phát khóa. | Có thể cấp ID trước khi chèn entity thông qua thao tác trên bảng generator. | Thêm truy vấn/khóa cạnh tranh trên bảng phụ, cần cấu hình phù hợp. |
| **`UUID`** | Sinh định danh theo UUID. | Có thể sinh mà không cần đợi một cột identity của database. | Thuộc Jakarta Persistence 3.1+; cần kiểu khóa, provider và DB tương thích. |

Bảng này giải thích nguyên lý. Các tối ưu như cấp trước một nhóm ID, caching, kiểu SQL và chính sách flush là chi tiết của từng provider.

### 4.1. IDENTITY

Với:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

database thường sinh ID tại thời điểm hàng mới được chèn. Trên nhiều hệ quản trị, cơ chế identity/auto-increment có tính năng sẵn có.

Tác động thực tế: nếu provider phải chèn hàng để biết ID, việc trì hoãn `INSERT` và gom nhiều insert vào một JDBC batch có thể bị hạn chế. Nhưng không nên khẳng định “`persist()` luôn lập tức `INSERT`” trong mọi môi trường: cách xử lý có thể chịu ảnh hưởng giao dịch và provider. Điều chắc chắn là **cơ chế identity phụ thuộc vào thao tác chèn để nhận giá trị từ database**.

### 4.2. SEQUENCE

Với `SEQUENCE`, database có đối tượng sequence độc lập để cấp các giá trị. Một giá trị có thể được lấy trước khi chèn entity, tạo điều kiện cho provider gom các INSERT khi cấu hình hỗ trợ.

```java
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;

@Id
@SequenceGenerator(
    name = "book_seq_generator",
    sequenceName = "books_id_seq",
    allocationSize = 1
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "book_seq_generator"
)
private Long id;
```

Ví dụ này sử dụng một generator có tên `book_seq_generator` và sequence thật tên `books_id_seq`. Nếu sequence được tạo thủ công trong PostgreSQL, có thể dùng:

```sql
CREATE SEQUENCE books_id_seq START WITH 1 INCREMENT BY 1;
```

Ở ví dụ, `allocationSize = 1` giúp dễ thấy cách cấp từng giá trị. Với cấu hình cấp phát theo khối lớn hơn, cần hiểu cơ chế tối ưu của provider và đảm bảo tham số generator phù hợp với sequence/schema thực tế. Một số provider kiểm tra sự tương thích giữa `allocationSize` và increment của sequence.

### 4.3. TABLE

Cơ chế `TABLE` dùng một bảng phụ để lưu trạng thái cấp phát khóa:

```java
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.TableGenerator;

@Id
@TableGenerator(
    name = "book_table_generator",
    table = "id_generators",
    pkColumnName = "entity_name",
    valueColumnName = "next_value",
    pkColumnValue = "books",
    allocationSize = 1
)
@GeneratedValue(
    strategy = GenerationType.TABLE,
    generator = "book_table_generator"
)
private Long id;
```

Provider sử dụng bảng `id_generators` và các cột cấu hình để giữ giá trị cấp phát. Cơ chế này có thể hoạt động trên nhiều database vì dựa vào bảng thông thường, nhưng có thể tạo thêm I/O và cạnh tranh khóa khi nhiều transaction cần ID.

Với `AUTO`, provider *có thể* dùng một cơ chế tương tự mà ứng dụng không khai báo `@TableGenerator` tường minh. Tên bảng, cấu trúc và cách tối ưu lúc đó phụ thuộc provider.

### 4.4. UUID trong Jakarta Persistence hiện đại

Jakarta Persistence 3.1 bổ sung chiến lược `GenerationType.UUID`:

```java
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class ApiResource {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    protected ApiResource() {}
}
```

`UUID` không phải dạng số tăng tuần tự; nó hữu ích khi cần định danh ít phụ thuộc vào một bộ cấp số tập trung. Việc hỗ trợ `UUID` trực tiếp bằng enum `GenerationType` **phụ thuộc phiên bản Jakarta Persistence**; các dự án JPA cũ dùng `javax.persistence` có thể không có lựa chọn này hoặc phải dùng tính năng riêng của provider.

Không nên cho rằng mọi trường `String`/`UUID` với `AUTO` đều được sinh theo cùng cách ở mọi phiên bản. Nếu UUID là một quyết định thiết kế quan trọng, khai báo rõ chiến lược và kiểm tra provider đang dùng.

## 5. Vòng đời sinh khóa: từ new đến managed

Khi tạo entity Java bằng constructor, entity ở trạng thái **new/transient**:

```java
Book book = new Book("JPA Fundamentals");

System.out.println(book.getId()); // null nếu dùng Long chưa gán
```

Một luồng làm việc điển hình:

```text
new Book("JPA Fundamentals")
          |
          | ID ban đầu thường null
          v
entityManager.persist(book)
          |
          | entity chuyển sang managed
          | provider chuẩn bị/cấp ID theo chiến lược
          |
          +--> SEQUENCE/TABLE: có thể lấy giá trị trước INSERT
          |
          +--> IDENTITY: thường cần INSERT để lấy khóa
          |
          +--> UUID: có thể sinh giá trị tại ứng dụng/provider
          |
          v
flush / commit theo giao dịch
          |
          v
database có hàng mới cùng khóa chính
```

Điều quan trọng là phân biệt:

- **Constructor:** không tự xin ID từ JPA khi chỉ viết `new Book(...)`.
- **`persist()`:** yêu cầu đưa entity mới vào persistence context, với việc sinh định danh theo mapping.
- **`flush()`:** đồng bộ thay đổi đang chờ xuống database; SQL có thể đã chạy trước đó, tùy chiến lược.
- **`commit()`:** cam kết transaction thành công; không chỉ đơn thuần là “tạo số ID”.
- **`close()`:** đóng application-managed `EntityManager`; không phải bước sinh khóa.

### 5.1. Ví dụ Java SE với EntityManager

Giả sử persistence unit `shopPU` đã được cấu hình cho giao dịch `RESOURCE_LOCAL` và entity `Book`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class SaveBookExample {
    public static void main(String[] args) {
        EntityManagerFactory factory =
                Persistence.createEntityManagerFactory("shopPU");

        try {
            saveBook(factory);
        } finally {
            factory.close();
        }
    }

    static void saveBook(EntityManagerFactory factory) {
        EntityManager em = factory.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            try {
                tx.begin();

                Book book = new Book("JPA Fundamentals");
                em.persist(book);

                tx.commit();

                // Sau commit thành công, provider phải dùng ID
                // đã được cấp để định danh hàng vừa lưu.
                System.out.println("Saved book id: " + book.getId());
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Ví dụ sử dụng `EntityTransaction` vì persistence unit đã được giả định là `RESOURCE_LOCAL`. Trong ứng dụng Jakarta EE dùng JTA hoặc Spring sử dụng `@Transactional`, giao dịch do container/framework quản lý nên cách tổ chức begin/commit/rollback khác.

Phương thức in ID **sau commit thành công** để minh họa kết quả rõ ràng. Không nên xây dựng logic ứng dụng dựa trên một giả định mơ hồ rằng mọi chiến lược đều tạo ID ngay sau `new` hoặc ngay cùng một thời điểm trước khi SQL chạy.

### 5.2. Nếu cần ID trước khi thực thi thao tác phụ thuộc?

Giả sử một nghiệp vụ phải tạo đơn hàng rồi tạo các dòng chi tiết tham chiếu đến đơn hàng. Khi dùng **quan hệ JPA được ánh xạ**, thường nên thiết lập liên kết bằng entity thay vì tự đoán số khóa:

```java
PurchaseOrder order = new PurchaseOrder();

OrderLine line = new OrderLine();
line.setOrder(order); // Liên kết đối tượng, không tự dự đoán order.id.

entityManager.persist(order);
entityManager.persist(line);
```

Mã ví dụ giả định có các mapping liên quan đã cấu hình và transaction thích hợp. JPA provider có thể sắp xếp SQL theo phụ thuộc khóa ngoại, tuy nhiên hành vi chính xác phụ thuộc mapping, cascade, generator và provider.

Nếu thật sự cần giá trị khóa chính để đưa vào một hệ thống bên ngoài **trước khi commit**, phải cân nhắc: transaction sau đó có thể rollback nên bản ghi chưa chắc tồn tại bền vững. Một ID đã được cấp **không đồng nghĩa dữ liệu đã commit**. Để đồng bộ với hệ thống ngoài, nên cân nhắc outbox/event sau commit hoặc cơ chế bảo đảm nhất quán thích hợp.

## 6. AUTO có tạo ra ID liên tục, tăng theo thời gian và không trùng tuyệt đối không?

**Không nên sử dụng giả định đó.** Sinh khóa chính và sinh số thứ tự nghiệp vụ là hai mục tiêu khác nhau.

### 6.1. Khoảng trống giữa các ID là bình thường

Giả sử generator cấp các giá trị:

```text
Lần cấp ID:  100, 101, 102, 103, 104, 105
Commit:      có  có  lỗi  có  lỗi  có
Bảng lưu:    100, 101,      103,      105
```

Những số bị “mất” có thể đến từ rollback, lỗi insert, batch cấp ID trước, sequence cache hoặc nhiều instance ứng dụng. Database sequence thường không hoàn tác một giá trị đã cấp chỉ vì transaction rollback.

Do đó:

- **ID không nhất thiết liên tiếp**.
- **ID lớn hơn không bảo đảm bản ghi được commit muộn hơn**.
- **ID không đại diện cho thời điểm tạo/duyệt đơn hàng**.
- **Không dùng ID để tính số lượng hàng** hoặc phát hành số chứng từ bắt buộc không có khoảng trống.

Nếu muốn thứ tự theo thời gian, dùng trường ngày tạo phù hợp, có lưu ý về tính đồng thời và độ chính xác timestamp. Nếu cần số hóa đơn phải tuần tự theo yêu cầu pháp lý/nghiệp vụ, thiết kế **cơ chế cấp số nghiệp vụ riêng**, có quy tắc transaction và xử lý lỗi tương ứng.

### 6.2. Ai bảo đảm không trùng?

Một generator được cấu hình đúng phải tạo được những ID thích hợp cho mapping. Nhưng bảo đảm cuối cùng của mô hình quan hệ vẫn là **PRIMARY KEY/UNIQUE constraint** trong database.

Nếu nhiều ứng dụng, script hoặc service cùng ghi vào bảng, chúng cần dùng nguồn cấp khóa tương thích. Một bộ tăng biến local trong bộ nhớ của mỗi service không đủ bảo đảm toàn hệ thống không bị trùng. Với `AUTO`, đặc biệt cần hiểu provider lấy ID từ sequence, identity hay bảng phụ nào để cấu hình các writer khác cho đúng.

## 7. Các vấn đề khi đổi database hoặc nâng cấp JPA provider

Một ưu điểm của `AUTO` là mapping đơn giản. Đổi lại, lựa chọn cụ thể có thể thay đổi theo môi trường.

| Thay đổi | Tình huống có thể phát sinh | Điều cần xem xét |
| --- | --- | --- |
| Chuyển từ database A sang database B | Cơ chế identity/sequence khác nhau. | Schema, migration, kiểu khóa và SQL provider tạo ra. |
| Nâng cấp provider ORM | Tên sequence mặc định hoặc cách cấp phát có thể thay đổi. | Cấu hình generator và migration tương thích. |
| Tắt tính năng tự tạo schema | Provider dự kiến có sequence/bảng generator nhưng DB chưa tạo. | Tạo đối tượng cần thiết trong migration. |
| Dùng nhiều instance ứng dụng | Nhiều worker cấp ID đồng thời. | Nguồn cấp phát đồng bộ và constraint database. |
| Dữ liệu cũ đã có ID | Sequence/bảng generator bắt đầu ở giá trị thấp hơn ID hiện có. | Căn chỉnh generator sau import/migration. |
| Đổi kiểu ID từ số sang UUID | Truy vấn, khóa ngoại, index và API có thể thay đổi. | Schema, DTO, hợp đồng dữ liệu và provider. |

### 7.1. Vì sao lỗi “sequence does not exist” có thể xuất hiện?

Nếu provider chọn cơ chế sequence nhưng schema không có sequence mà provider mong đợi, quá trình sinh khóa có thể thất bại trước khi insert entity. Tên sequence có thể do provider chọn mặc định hoặc do generator được cấu hình.

Ví dụ ở PostgreSQL, kiểm tra schema và tạo sequence phù hợp với migration. Không đoán tên chỉ dựa trên `@GeneratedValue(strategy = AUTO)`; cần biết mapping thực tế của provider.

Tương tự, nếu provider chọn table generator nhưng bảng phụ chưa tồn tại hoặc chưa có dữ liệu cần thiết, lần cấp ID có thể thất bại.

### 7.2. Nếu sequence phát ID trùng bản ghi cũ?

Ví dụ bảng đã chứa `id = 1000`, nhưng sequence mới được tạo lại bắt đầu từ 1. Khi sinh ID trùng khóa cũ, lệnh insert bị từ chối bởi primary key constraint.

Cần **đồng bộ trạng thái generator với dữ liệu hiện có** trong migration/khôi phục dữ liệu. Cách cập nhật sequence hoặc identity tùy DBMS; không nên sửa số theo cách thủ công khi có transaction đang ghi đồng thời mà chưa có kế hoạch khóa/dừng ghi an toàn.

### 7.3. Khi nào nên chuyển từ AUTO sang chiến lược tường minh?

Nếu ứng dụng cần:

- Kiểm soát chính xác tên sequence hoặc bảng generator.
- Bảo đảm mapping khớp với schema do migration quản lý.
- Tối ưu cấp phát ID và insert batching theo database.
- Tránh thay đổi hành vi cấp khóa ngoài ý muốn khi nâng cấp provider.
- Chọn UUID theo hợp đồng định danh của hệ thống.

thì có thể khai báo tường minh `SEQUENCE`, `IDENTITY` hoặc `UUID` (nếu được hỗ trợ), cùng generator tương ứng.

Điều này không có nghĩa `AUTO` luôn kém. **`AUTO` phù hợp khi sự linh hoạt cao hơn nhu cầu kiểm soát chi tiết**, còn chiến lược tường minh phù hợp khi có yêu cầu kỹ thuật cụ thể.

## 8. AUTO và @SequenceGenerator: có thể kết hợp không?

`@GeneratedValue` có thuộc tính `generator` để tham chiếu generator được đặt tên. Ví dụ chắc chắn, dễ hiểu và portable khi muốn dùng database sequence là:

```java
@SequenceGenerator(
    name = "order_sequence_generator",
    sequenceName = "order_id_seq",
    allocationSize = 1
)
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_sequence_generator"
)
private Long id;
```

Cấu hình này **diễn đạt rõ `SEQUENCE`**, phù hợp khi đã biết database và muốn quản lý sequence tường minh.

Một số provider có thể hỗ trợ khai báo tên generator cùng `AUTO` hoặc diễn giải metadata generator theo quy tắc riêng. Tuy nhiên, nếu mục tiêu là **buộc sử dụng một sequence cụ thể**, hãy dùng `GenerationType.SEQUENCE` và `@SequenceGenerator` để tránh phụ thuộc vào cách provider chọn cơ chế khi `AUTO`.

Với hệ thống nhiều module hoặc nhiều entity, cần đặt tên generator rõ ràng, tránh cấu hình trùng tên không chủ ý, và đảm bảo phần DDL migration khớp cấu hình Java.

## 9. GeneratedValue không thay thế thiết kế quan hệ và khóa ngoại

Giả sử ứng dụng có entity `Customer` và `PurchaseOrder`:

```java
@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    protected Customer() {}
}
```

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    @ManyToOne(optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {}
}
```

Hai entity có khóa chính riêng. `PurchaseOrder.customer` là **quan hệ khóa ngoại**; giá trị của nó phải trỏ đến một khách hàng hợp lệ. Việc đơn hàng có ID tự sinh không tự tạo khách hàng hay đảm bảo khách hàng đã được persist.

Khi lưu các entity liên quan, cần hiểu:

- Đối tượng nào là new, managed hoặc detached.
- Quan hệ có `cascade = PERSIST` hay không.
- Thứ tự và thời điểm SQL được provider tạo.
- Constraint khóa ngoại của database.
- Transaction chứa những thao tác cần nguyên tử.

Nếu hai entity tham gia một transaction, provider có thể sinh ID đúng theo từng generator và xử lý các lệnh chèn, nhưng ánh xạ quan hệ/cascade vẫn phải được khai báo hợp lý.

## 10. Những sai lầm thường gặp với @GeneratedValue và AUTO

### 10.1. Bỏ @Id và chỉ giữ @GeneratedValue

```java
// Không phải mapping khóa chính hợp lệ:
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

`@GeneratedValue` cần gắn với thuộc tính định danh được JPA nhận biết bằng `@Id`. Nếu thiếu định danh, entity mapping có thể không hợp lệ và provider sẽ báo lỗi lúc khởi tạo.

### 10.2. Gán tay id nhưng vẫn dùng generator

```java
Book book = new Book("Clean Code");
// book.setId(999L); // Không nên tự cấp ID tùy ý khi dùng GeneratedValue.
entityManager.persist(book);
```

Một mapping có `@GeneratedValue` tuyên bố rằng ID được cấp bởi generator. Việc ứng dụng tự gán ID có thể dẫn đến hành vi không như mong đợi: bị coi là entity khác trạng thái, giá trị bị thay thế, bị từ chối hoặc phát sinh lỗi tùy API/provider. Nếu nghiệp vụ cần khóa do ứng dụng cấp, hãy thiết kế chiến lược **assigned ID** riêng thay vì trộn hai mô hình.

### 10.3. Coi AUTO là auto-increment

```java
@GeneratedValue(strategy = GenerationType.AUTO)
```

không có nghĩa cột database chắc chắn dùng `AUTO_INCREMENT` hoặc `IDENTITY`. Provider có thể chọn sequence hoặc cơ chế khác. Nếu yêu cầu bắt buộc dùng identity, hãy khai báo `GenerationType.IDENTITY` và kiểm tra DB hỗ trợ.

### 10.4. Giả định ID có ngay sau new

```java
Book book = new Book("JPA Fundamentals");
Long id = book.getId(); // Thường null, vì chưa persist.
```

Constructor Java thông thường không làm việc với persistence context, nên không có lý do để gọi generator. ID sẽ được cấp theo vòng đời JPA và strategy khi entity được persist.

### 10.5. Dựa vào ID trước commit để xác nhận lưu thành công

Một entity có thể nhận ID từ sequence trước khi `INSERT`, hoặc nhận ID trong quá trình `INSERT`, nhưng transaction sau đó vẫn có thể rollback. Không thể kết luận “có ID” đồng nghĩa “hàng đã tồn tại bền vững”.

### 10.6. Cấu hình sequence và allocationSize không khớp schema

Nếu provider cấp trước nhóm ID nhưng cấu hình và sequence thực tế không phù hợp, ứng dụng có thể gặp lỗi khi khởi tạo, cấp ID sai kỳ vọng hoặc ảnh hưởng hiệu năng. Cần quản lý mapping và migration cùng nhau, xác minh những tham số generator quan trọng.

### 10.7. Dùng khóa sinh tự động như số thứ tự nghiệp vụ

ID có thể có khoảng trống và thứ tự cấp phát khác thứ tự commit. Số invoice hiển thị hoặc số hợp đồng có chính sách pháp lý cần cơ chế riêng, không suy ra từ `@GeneratedValue(AUTO)`.

### 10.8. Không để database bảo vệ khóa chính

Dù mapping có generator, bảng vẫn cần `PRIMARY KEY`. Generator chỉ là nguồn cấp giá trị; constraint giúp database bảo vệ tính duy nhất khi có nhiều writer và các đường ghi khác nhau.

## 11. Khi nào chọn AUTO trong thực tế?

Có thể cân nhắc dựa trên yêu cầu:

| Hoàn cảnh | Hướng lựa chọn |
| --- | --- |
| Học JPA cơ bản, mô hình CRUD đơn giản, dùng provider và schema đã cấu hình tương thích. | `@GeneratedValue` hoặc `@GeneratedValue(strategy = AUTO)` là điểm bắt đầu phù hợp. |
| Dùng một hệ quản trị có sequence, cần tên sequence xác định và muốn kiểm soát cấp ID. | `SEQUENCE` với `@SequenceGenerator` tường minh. |
| Dùng cột identity do DB cấp và muốn giữ đúng chiến lược này. | `IDENTITY`, cân nhắc ảnh hưởng insert batching. |
| Database không có sequence phù hợp, cần cơ chế cấp số qua bảng phụ. | `TABLE` khi có lý do kỹ thuật và kiểm soát được cạnh tranh. |
| Muốn ID dạng UUID cho phân tán hoặc API. | `UUID` nếu Jakarta Persistence/provider hỗ trợ; xác nhận định dạng và schema. |
| Nhiều provider hoặc đổi DB thường xuyên. | `AUTO` có thể giảm ràng buộc ở mapping, nhưng vẫn phải thử tương thích schema/migration. |
| Hệ thống có schema cố định, yêu cầu tối ưu cao và quy trình migration chặt. | Thường nên chọn chiến lược rõ ràng, kiểm soát DDL và thông số generator. |

Quyết định nên dựa trên **khả năng database, kiểu khóa, transaction, số lượng insert, công cụ migration và yêu cầu thay đổi hệ thống**. Với dự án học tập, `AUTO` giúp nhìn rõ vai trò của JPA; với dự án vận hành lâu dài, cần biết provider thực sự làm gì.

## 12. Câu hỏi tự kiểm tra

**1. `@Id` khác `@GeneratedValue` ở điểm nào?**

`@Id` xác định thuộc tính khóa chính của entity; `@GeneratedValue` khai báo cách nhận giá trị cho khóa chính. Trong database, ràng buộc `PRIMARY KEY` vẫn cần đảm bảo tính duy nhất.

**2. Nếu viết `@GeneratedValue` mà không khai báo `strategy`, chiến lược nào được dùng?**

Mặc định là `GenerationType.AUTO`.

**3. AUTO có luôn chọn IDENTITY trên MySQL và SEQUENCE trên PostgreSQL không?**

Không thể khẳng định như một quy tắc chung của đặc tả. Lựa chọn thực tế tùy provider, phiên bản, kiểu khóa, dialect và cấu hình. Cần xem SQL/cấu hình trong dự án cụ thể.

**4. Sau khi gọi `new Book(...)`, vì sao `id` thường là `null`?**

Vì object chưa được JPA quản lý và chưa đi qua cơ chế sinh khóa. `Long` mặc định `null` khi chưa gán giá trị.

**5. ID đã có nghĩa là transaction đã commit chưa?**

Chưa. Sequence hoặc cơ chế khác có thể cấp ID trước commit. Transaction có thể rollback, và ID đã cấp không bảo đảm bản ghi tồn tại bền vững.

**6. Khi nào dùng `@SequenceGenerator`?**

Khi cần cấu hình rõ một generator dùng database sequence, gồm tên sequence và các thuộc tính cấp phát. Nếu muốn buộc dùng sequence, nên kết hợp với `GenerationType.SEQUENCE`.

**7. AUTO có đảm bảo ID không có khoảng trống?**

Không. Rollback, sequence caching, cấp trước nhiều ID và thao tác đồng thời có thể tạo khoảng trống. ID không nên được dùng làm số thứ tự nghiệp vụ yêu cầu liên tục.

**8. Có nên dùng `@GeneratedValue` cho khóa chính tổng hợp không?**

Không nên giả định tính portable cho cơ chế đó. `@GeneratedValue` phổ biến và được chuẩn hóa rõ cho khóa chính đơn; khóa tổng hợp cần chiến lược định danh riêng phù hợp với provider/đặc tả.

**9. Nếu dùng Flyway hoặc Liquibase thì AUTO có tự sửa schema giúp không?**

Không. `AUTO` chỉ yêu cầu provider chọn cách sinh khóa. Schema, sequence, identity column hoặc bảng generator phải được tạo/cập nhật phù hợp với provider và chiến lược đó.

## 13. Ghi nhớ cốt lõi

`@GeneratedValue` giúp JPA cấp **khóa chính được sinh tự động** cho entity, giảm phần việc tự cấp ID và hỗ trợ quản lý định danh nhất quán với cơ sở dữ liệu. `@Id` xác định trường khóa chính; `@GeneratedValue` xác định chiến lược cấp giá trị cho trường ấy.

`GenerationType.AUTO` là **lựa chọn để provider quyết định chiến lược sinh khóa**, không phải một thuật toán cấp số cụ thể. Nó có thể mang lại sự thuận tiện trong mapping, nhưng sự vận hành chính xác vẫn phụ thuộc **provider, dialect, kiểu khóa, schema và transaction**.

Khi thiết kế hệ thống, hãy nhớ bốn điều: **ID sinh tự động không thay cho primary key constraint; ID đã được cấp không chứng minh transaction đã commit; ID không nhất thiết liên tục; và AUTO cần tương thích với schema thực tế**. Hiểu đúng những giới hạn này giúp lựa chọn khóa và chiến lược sinh phù hợp với ứng dụng JPA.
