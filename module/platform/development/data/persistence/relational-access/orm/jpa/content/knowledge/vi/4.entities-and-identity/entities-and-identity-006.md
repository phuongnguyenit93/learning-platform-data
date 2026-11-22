# Phân biệt định danh Java, định danh entity và khóa chính

Trong một ứng dụng dùng JPA/Hibernate, cùng một sản phẩm có thể xuất hiện dưới dạng **đối tượng Java trong bộ nhớ**, **entity được persistence context quản lý**, và **một hàng trong cơ sở dữ liệu**. Ba góc nhìn này có liên hệ nhưng không phải một khái niệm. Nhầm lẫn chúng dẫn đến lỗi khi so sánh entity, thiết kế `equals()/hashCode()`, sử dụng `HashSet`, thao tác `merge()` hoặc chọn khóa chính.

Ví dụ, hai biến Java có thể cùng trỏ đến một object; hai object khác nhau có thể đại diện cho cùng một bản ghi; và một object mới có thể chưa có hàng nào trong database để đại diện. Để giải thích đúng, cần trả lời ba câu hỏi khác nhau:

1. **Định danh Java (Java object identity):** đây có phải **cùng một thể hiện object** trong JVM hay không?
2. **Định danh entity (JPA entity identity):** đây có phải **cùng một entity persistence**, được nhận diện bằng kiểu entity và giá trị định danh của nó hay không?
3. **Khóa chính (database primary key):** cơ sở dữ liệu xác định **một hàng trong một bảng** bằng cột hoặc tổ hợp cột nào?

> Lưu ý thuật ngữ: trong cú pháp Java, *identifier* cũng có nghĩa là **tên** biến, class, method như `product` hoặc `getId`. Trong bài học về entity, “định danh Java” được xét theo nghĩa **object identity**: danh tính của một instance đang tồn tại trong bộ nhớ; đây không phải tên biến.

## 1. Bản đồ ba loại định danh

| Khía cạnh | Định danh Java | Định danh entity trong JPA | Khóa chính của cơ sở dữ liệu |
|---|---|---|---|
| Đối tượng được nhận diện | Một instance Java trong JVM | Một entity của mô hình persistence | Một hàng của một bảng |
| Cách xác định | So sánh tham chiếu bằng `==` | Kiểu entity và giá trị khóa định danh được khai báo qua `@Id` hoặc `@EmbeddedId` | Cột hoặc tổ hợp cột thuộc ràng buộc `PRIMARY KEY` |
| Phạm vi | Các tham chiếu tới object khi JVM đang chạy | Tập entity của persistence unit; tính duy nhất instance managed trong từng persistence context | Phạm vi bảng và database/schema liên quan |
| Thời gian tồn tại | Vòng đời object trong bộ nhớ | Vòng đời và trạng thái của entity theo JPA; định danh thường gắn với dữ liệu persisted | Còn hàng trong database thì còn khóa, kể cả sau khi ứng dụng khởi động lại |
| Do ai quản lý | JVM và mã Java | JPA provider, ví dụ Hibernate | Hệ quản trị cơ sở dữ liệu |
| Ví dụ | `a == b` | `em.find(Product.class, 42L)` | `products.id = 42` |
| Điều không bảo đảm | Cùng nội dung không có nghĩa cùng object | Cùng entity không có nghĩa hai reference phải là một object ở mọi context | Có cùng một con số nhưng ở hai bảng không có nghĩa cùng thực thể nghiệp vụ |

Ba lớp nhìn này có thể xếp như sau:

~~~text
           BỘ NHỚ JVM
    +-----------------------+
    | Java object A         |
    | Product{id=42}        |
    +-----------------------+
                 |
                 | Java reference == ?
                 |
    +-----------------------+
    | Java object B         |
    | Product{id=42}        |
    +-----------------------+

           JPA / ORM
    Entity type = Product
    @Id value   = 42
    Persistence context quản lý instance đại diện cho entity đó

          DATABASE
    products
    +----+-----------+-----------+
    | id | sku       | name      |
    +----+-----------+-----------+
    | 42 | JAVA-042  | Java Book |
    +----+-----------+-----------+
      ^
      PRIMARY KEY
~~~

Trong một persistence context cụ thể, JPA duy trì một thể hiện managed đại diện cho một danh tính entity. Nhưng hai persistence context độc lập có thể tải cùng hàng database thành **hai Java object khác nhau**. Đây là điểm khác biệt quan trọng nhất trong thực tế.

## 2. Định danh Java: object identity khác giá trị và trạng thái

### 2.1. Hai biến trỏ cùng object

Một object có thể được tham chiếu bởi nhiều biến:

~~~java
class ProductDraft {
    String sku;
    String name;

    ProductDraft(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }
}

ProductDraft first = new ProductDraft("JAVA-042", "Java Book");
ProductDraft alias = first;

System.out.println(first == alias); // true

alias.name = "Updated Java Book";
System.out.println(first.name);     // Updated Java Book
~~~

`first` và `alias` là **hai tên biến**, nhưng cùng tham chiếu tới **một thể hiện object**. Do đó, `first == alias` trả về `true`. Thay đổi thuộc tính qua biến này có thể thấy qua biến kia.

### 2.2. Cùng giá trị vẫn có thể là hai object

~~~java
ProductDraft a = new ProductDraft("JAVA-042", "Java Book");
ProductDraft b = new ProductDraft("JAVA-042", "Java Book");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false nếu không override equals()
~~~

Hai object có dữ liệu giống nhau nhưng được tạo bởi hai lệnh `new`. Toán tử `==` so sánh chúng theo **danh tính tham chiếu**, không so sánh từng trường dữ liệu.

Nếu class không override `equals()` thì phương thức `Object.equals()` mặc định cũng kiểm tra cùng object. Tuy nhiên, class có thể tự định nghĩa so sánh giá trị:

~~~java
record ProductView(String sku, String name) {}

ProductView x = new ProductView("JAVA-042", "Java Book");
ProductView y = new ProductView("JAVA-042", "Java Book");

System.out.println(x == y);      // false
System.out.println(x.equals(y)); // true: record so sánh thành phần giá trị
~~~

Ba phép kiểm tra cần phân biệt:

- `a == b`: **identity của tham chiếu Java**.
- `a.equals(b)`: **logic bằng nhau do class định nghĩa**, có thể theo identity, giá trị hoặc ID.
- `a.hashCode()`: mã băm phục vụ cấu trúc dữ liệu như `HashMap`/`HashSet`; nó không phải một mã định danh duy nhất.

**`System.identityHashCode(object)` không phải khóa chính, cũng không phải ID duy nhất toàn cục.** Giá trị này có thể trùng nhau giữa các object và không ổn định xuyên các lần chạy JVM. Không lưu nó vào database để thay cho khóa chính.

### 2.3. Java reference không phản ánh quan hệ tồn tại trong database

Hai instance Java khác nhau đều có thể chứa trường `id = 42`:

~~~java
ProductView one = new ProductView("JAVA-042", "Java Book");
ProductView two = new ProductView("JAVA-042", "Java Book");
~~~

Không thể kết luận từ riêng `one == two`, `one.equals(two)` hay từ các chuỗi giống nhau rằng đang có một hàng database nào đó. `ProductView` ở đây chỉ là record Java, **không phải entity JPA**. Để có định danh persistence cần ánh xạ entity và tương tác với database/provider tương ứng.

## 3. Khóa chính: định danh một hàng ở tầng quan hệ

Giả sử sử dụng PostgreSQL và một bảng:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);
~~~

Dữ liệu mẫu:

| id | sku | name |
|---:|---|---|
| 42 | JAVA-042 | Java Book |
| 43 | DB-043 | Database Guide |

Ở đây:

- `id` là **khóa chính** (primary key, viết tắt PK). Nó xác định một hàng duy nhất trong bảng `products`.
- `sku` là **khóa ứng viên/nghiệp vụ** trong ví dụ vì có ràng buộc `UNIQUE` và `NOT NULL`; hệ thống có thể dùng SKU để tìm sản phẩm, nhưng SKU **không phải primary key** của bảng này.
- `name` chỉ là thuộc tính mô tả. Nhiều sản phẩm có thể có cùng tên.

### 3.1. Các tính chất chính của primary key

Một khóa chính:

1. **Duy nhất trong bảng**: không có hai hàng cùng giá trị khóa chính.
2. **Không NULL**: mọi hàng phải có giá trị khóa chính hợp lệ.
3. **Có thể gồm một hoặc nhiều cột**: khóa đơn hoặc khóa ghép (composite primary key).
4. **Thường được bảng khác tham chiếu qua foreign key**: ràng buộc khóa ngoại giúp bảo vệ quan hệ dữ liệu.
5. **Nên có tính ổn định**: sửa khóa chính có thể tác động tới hàng loạt khóa ngoại và cache; trong thiết kế thực tế, thường không đổi khóa sau khi tạo.

Tính duy nhất là **trong phạm vi bảng**. `products.id = 42` và `customers.id = 42` không xung đột; hai khóa này có thể cùng tồn tại vì nằm ở hai bảng khác nhau. Tương tự, hai database riêng biệt có thể có cùng cặp bảng/ID mà không đại diện cho cùng dữ liệu nghiệp vụ.

### 3.2. Khóa chính và khóa nghiệp vụ

Có hai hướng thông dụng:

| Chiến lược | Ví dụ | Điểm mạnh | Điều cần cân nhắc |
|---|---|---|---|
| **Khóa tự nhiên / nghiệp vụ** (*natural/business key*) | `sku` hoặc mã quốc gia | Có ý nghĩa trong domain; đôi khi đã được cấp sẵn | Quy tắc nghiệp vụ có thể đổi; chuỗi có thể dài, phân biệt hoa/thường hoặc có quy tắc chuẩn hóa |
| **Khóa thay thế** (*surrogate key*) | `id BIGINT` tự sinh hoặc UUID | Ít phụ thuộc thuộc tính có thể thay đổi; thường tiện cho foreign key | Phải thêm ràng buộc unique cho khóa nghiệp vụ nếu domain yêu cầu |

Một cách phổ biến là chọn `products.id` làm PK và đặt `UNIQUE(sku)` để bảo đảm SKU không bị trùng. Việc dùng surrogate key **không loại bỏ** nhu cầu enforce tính duy nhất nghiệp vụ bằng ràng buộc database.

### 3.3. Khóa ngoại tham chiếu khóa chính

Ví dụ bảng chi tiết đơn hàng:

~~~sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT fk_order_lines_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

`order_lines.product_id = 42` là **foreign key**, nó trỏ đến hàng `products.id = 42`. Thuộc tính `product_id` trong bảng `order_lines` không phải primary key của hàng chi tiết, vì hàng đã dùng `order_lines.id` làm primary key.

Một object Java tham chiếu `Product` qua thuộc tính `product` **không tự tạo khóa ngoại vật lý** trong database. Việc này phụ thuộc schema và cấu hình mapping JPA tương ứng.

## 4. Định danh entity: @Id là cầu nối từ Java sang database

Một JPA entity là class được provider quản lý theo mô hình persistence. JPA cần biết **thuộc tính nào là định danh** để phân biệt các entity cùng loại.

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    protected Product() {
        // Constructor không tham số phục vụ JPA.
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
~~~

Các annotation có vai trò riêng:

| Annotation | Ý nghĩa |
|---|---|
| `@Entity` | Đăng ký class là một entity trong mô hình JPA |
| `@Table(name = "products")` | Ánh xạ entity vào bảng quan hệ tương ứng |
| `@Id` | Chỉ định thuộc tính định danh của entity |
| `@GeneratedValue(strategy = IDENTITY)` | Yêu cầu provider phối hợp cơ chế sinh ID của database |
| `@Column(unique = true)` trên `sku` | Khai báo ràng buộc duy nhất dự kiến khi provider tạo schema; schema thật vẫn phải có ràng buộc thích hợp |

**`@Id` và `@GeneratedValue` không phải một annotation.** `@Id` xác định **định danh là gì**; `@GeneratedValue` xác định **cách giá trị đó được cấp** trong trường hợp dùng chiến lược sinh ID. JPA hỗ trợ cả entity có ID do ứng dụng gán thủ công.

Trong ví dụ, `Product.id` ánh xạ tới `products.id`. Khi entity đã persisted, giá trị ID của entity là cách ứng dụng và provider nói tới cùng bản ghi database, nhưng entity identity vẫn là **khái niệm ở tầng ORM**, còn PK là **ràng buộc do database thực thi**.

### 4.1. Một con số ID có đủ để nhận diện entity không?

Không. Nếu có `Product(id=42)` và `Customer(id=42)`, đó là **hai entity khác loại**, tương ứng hai tập dữ liệu khác nhau.

Trong một persistence unit, định danh entity thường được hiểu theo cặp:

~~~text
(entity type, primary-key value)

(Product, 42)  -> một Product
(Customer, 42) -> một Customer khác
~~~

Do đó, đừng thiết kế một cache nghiệp vụ chung chỉ lưu `Map<Long, Object>` nếu nó chứa nhiều loại entity. Khóa cache tối thiểu phải phân biệt loại entity (và khi cần cả nguồn dữ liệu/tenant), thay vì giả định `42` là duy nhất trên toàn ứng dụng.

### 4.2. @Id không đảm bảo dữ liệu đã tồn tại

Có ba trường hợp:

~~~text
new Product("JAVA-042", "Java Book")
    |
    +-- id == null (thường gặp với ID tự sinh)
    +-- đang là Java object mới
    +-- chưa có hàng trong database

Một Product được gán id=42 bằng code
    |
    +-- biết giá trị định danh được gán
    +-- KHÔNG suy ra hàng products(id=42) đã tồn tại

em.find(Product.class, 42L) thành công
    |
    +-- đã tìm thấy entity ứng với id=42
    +-- object trả về là managed trong persistence context hiện tại
~~~

Nếu mô hình dùng ID tự sinh, việc chọn `Long` thay vì `long` thường giúp biểu diễn trạng thái chưa có ID bằng `null`. Với `long`, giá trị mặc định `0` có thể bị hiểu nhầm là ID hợp lệ.

Không được mặc định rằng mọi `id != null` đều đồng nghĩa entity đã persisted. Một entity detached có ID nhưng không còn được context quản lý; một entity dùng ID được gán thủ công cũng có ID trước khi gọi `persist()`.

## 5. Persistence context duy trì danh tính entity như thế nào?

**Persistence context** là phạm vi trong đó EntityManager theo dõi các entity managed. Trong cùng một context, với một danh tính entity nhất định, JPA quản lý một instance đại diện thống nhất. Đặc điểm này thường được mô tả là *identity map* và liên quan tới **first-level cache** của ORM.

Giả sử database có một Product mang ID 42:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
try {
    Product a = em.find(Product.class, 42L);
    Product b = em.find(Product.class, 42L);

    if (a != null) {
        System.out.println(a == b); // true: cùng managed instance
        System.out.println(a.getId().equals(b.getId())); // true
    }
} finally {
    em.close();
}
~~~

`em.find` có thể trả về `null` nếu không có bản ghi tương ứng. Khi bản ghi tồn tại và được quản lý trong cùng persistence context, hai lần tìm entity đó trả về cùng Java instance theo ngữ nghĩa identity của JPA.

### 5.1. Cùng hàng, khác persistence context

Bây giờ dùng hai EntityManager khác nhau:

~~~java
EntityManager em1 = entityManagerFactory.createEntityManager();
EntityManager em2 = entityManagerFactory.createEntityManager();

try {
    Product left = em1.find(Product.class, 42L);
    Product right = em2.find(Product.class, 42L);

    if (left != null && right != null) {
        System.out.println(left == right); // false trong ví dụ hai context độc lập
        System.out.println(left.getId().equals(right.getId())); // true
    }
} finally {
    em1.close();
    em2.close();
}
~~~

Với hai context độc lập thực sự, mỗi context có thể quản lý một object Java riêng cho cùng bản ghi. **Cùng entity identity không bắt buộc cùng Java object identity ở những context khác nhau**.

Lưu ý: trong ứng dụng Spring, một `EntityManager` được inject có thể là proxy tới EntityManager gắn với transaction hiện tại; đừng suy luận chỉ từ số lượng biến Java rằng chắc chắn có hai context khác nhau. Đoạn trên chủ động gọi `createEntityManager()` hai lần để mô tả hai context riêng.

### 5.2. Trong cùng context, truy vấn có lấy dữ liệu mới nhất không?

Không phải lúc nào. Vì context quản lý một instance thống nhất, việc `find` lần hai có thể trả lại entity đang managed, thay vì tải lại dữ liệu đã bị giao dịch khác thay đổi. Khi cần cập nhật trạng thái, có thể xem xét `refresh()`, chính sách cache, transaction isolation và cơ chế khóa tương ứng.

Đảm bảo identity trong context **không phải** đảm bảo dữ liệu mới nhất trên toàn hệ thống, và cũng **không phải** cơ chế chống cập nhật mất dữ liệu (*lost update*). Tính đồng thời cần được giải quyết riêng, ví dụ bằng `@Version` và optimistic locking khi phù hợp.

## 6. Vòng đời entity làm thay đổi mối quan hệ giữa object và ID

Định danh Java tồn tại ngay khi một object được tạo. Định danh entity và sự quản lý của JPA lại phụ thuộc trạng thái của entity:

~~~text
         new Product(...)
                |
                v
        NEW / TRANSIENT
        Java object đã có identity
        Có thể chưa có @Id value
                |
          em.persist(...)
                |
                v
             MANAGED <----------- em.merge(detached)
                |                       |
         flush / commit                 | trả về managed copy
                |                       |
                v                       |
          DB row / PK                DETACHED
                ^                    ^    |
                |                    |    |
          dữ liệu lưu bền         clear/close/detach
                |
             em.remove(...)
                |
                v
             REMOVED
       (xóa theo transaction)
~~~

Sơ đồ minh họa các chuyển trạng thái thường gặp, không có ý nghĩa tất cả entity luôn đi qua mọi trạng thái theo thứ tự đó.

| Trạng thái JPA | Java object còn tồn tại? | Provider theo dõi thay đổi? | ID thường gặp |
|---|---|---|---|
| **New/transient** | Có | Chưa | `null` nếu tự sinh; có thể đã được gán nếu ứng dụng quản lý ID |
| **Managed** | Có | Có, trong persistence context | Được xác định theo mapping và chiến lược cấp ID |
| **Detached** | Có | Không còn trong context trước đó | Thường vẫn giữ ID của entity persisted |
| **Removed** | Có | Có trạng thái chờ xóa trong context | Có thể vẫn giữ giá trị ID Java; không đồng nghĩa hàng đã biến mất trước commit |

### 6.1. Gọi persist() rồi ID đã có ngay chưa?

Không có một thời điểm chung cho tất cả cách sinh khóa. Ví dụ với `GenerationType.IDENTITY`, provider có thể phải thực thi `INSERT` sớm để lấy ID do database sinh. Với `SEQUENCE`, provider có thể lấy giá trị sequence trước khi gửi INSERT. Với UUID do provider sinh, thời điểm cấp cũng phụ thuộc cơ chế và phiên bản sử dụng.

~~~java
Product product = new Product("JAVA-042", "Java Book");

// Java object tồn tại; id thường là null với cấu hình tự sinh.
em.persist(product);

// Entity đã được yêu cầu quản lý; việc có id và thời điểm gửi SQL
// phụ thuộc chiến lược sinh ID và provider.

em.flush(); // Đồng bộ thay đổi với database; chưa phải commit.
~~~

Không xây dựng nghiệp vụ dựa trên giả định “ID luôn có ngay sau `new`” hoặc “`persist()` luôn thực hiện SQL INSERT tức thì”.

### 6.2. Định danh của detached entity không biến mất khi đóng context

~~~java
EntityManager firstEm = entityManagerFactory.createEntityManager();
Product detached;
try {
    detached = firstEm.find(Product.class, 42L);
} finally {
    firstEm.close();
}

// detached vẫn là object Java nếu biến còn tham chiếu nó.
// Nhưng nó không còn được firstEm quản lý.
~~~

Khi đóng EntityManager, object được trả ra không tự biến mất khỏi bộ nhớ; nó trở thành detached nếu trước đó là managed. Nó vẫn có Java object identity và giá trị ID đã tải, nhưng thay đổi thuộc tính trên nó không còn tự động được context trước theo dõi.

### 6.3. merge() không “nối lại” object Java cũ theo nghĩa ==

Đây là tình huống dễ gây nhầm:

~~~java
EntityManager nextEm = entityManagerFactory.createEntityManager();
EntityTransaction tx = nextEm.getTransaction();

try {
    tx.begin();

    Product managed = nextEm.merge(detached);

    // managed là instance được quản lý trong nextEm;
    // detached vẫn là object detached.
    System.out.println(managed == detached); // false với detached object

    managed.rename("Java Book - 2nd edition");
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    nextEm.close();
}
~~~

`merge(detached)` sao chép trạng thái thích hợp vào một managed instance và **trả về instance managed đó**. Đối tượng được truyền vào vẫn detached. Nếu đã có entity managed cùng ID trong context đích, trạng thái được hợp nhất vào entity đó; nếu chưa có, provider có thể tải/tạo instance managed phù hợp.

Vì vậy, sau `merge()` hãy làm việc với **giá trị trả về** nếu cần tiếp tục cập nhật. Không dựa vào biểu thức `managed == detached`, cũng không tự viết phương thức `equals` chỉ để “biến hai object thành một object”.

### 6.4. remove() không xóa Java object

Khi gọi `em.remove(product)` trên một entity managed, entity đi vào trạng thái removed theo JPA; việc xóa hàng được đồng bộ theo transaction. Java reference cũ vẫn có thể tồn tại sau đó, và object không trở nên `null`. Sau rollback, trạng thái và dữ liệu cần được xử lý theo ngữ nghĩa transaction/context. Không dùng `== null` để xác định một hàng đã bị xóa.

## 7. Ba cách so sánh “cùng sản phẩm” với kết quả khác nhau

Giả sử có hai reference `p` và `q`. Mỗi cách kiểm tra trả lời một câu hỏi riêng:

| Câu hỏi | Biểu thức thường dùng | Kết luận |
|---|---|---|
| Có cùng object Java? | `p == q` | Chỉ so sánh reference identity |
| Hai object có được coi là bằng nhau theo contract của class? | `p.equals(q)` | Phụ thuộc cách implement `equals()` |
| Hai entity cùng loại được gắn cùng ID? | So sánh kiểu entity và `getId()` khác `null` | Có thể xác định cùng persistence identity khi ID và nguồn dữ liệu phù hợp |
| Hai object chắc chắn cùng trạng thái hiện tại trong DB? | Không có một phép so sánh object đơn giản | Phải xét transaction, version, dữ liệu và thời điểm đọc |
| Cùng SKU có phải cùng hàng DB không? | `sku` bằng nhau **kèm** ràng buộc unique trong đúng phạm vi | Chỉ đúng nếu dữ liệu đã được bảo vệ bằng quy tắc domain/schema tương ứng |

**Không dùng `==` để kiểm tra “hai object có cùng ID hay không”**, đặc biệt khi chúng được lấy ở hai transaction/context khác nhau. Ngược lại, không dùng `equals()` để kết luận hai biến thực sự tham chiếu cùng instance; `equals()` có thể trả true cho hai object hoàn toàn tách biệt.

### 7.1. Vì sao dùng == cho Long ID cũng sai?

`Long` là object wrapper. Khi có hai giá trị `Long`, biểu thức `idA == idB` so sánh tham chiếu nếu cả hai toán hạng đều là `Long`. Một số giá trị nhỏ có thể trùng reference do cơ chế cache wrapper, tạo cảm giác mã hoạt động, nhưng không được dựa vào điều đó.

~~~java
Long idA = Long.valueOf(1000L);
Long idB = Long.valueOf(1000L);

System.out.println(idA.equals(idB)); // true
// Không dùng idA == idB để so sánh giá trị định danh.
~~~

So sánh an toàn khi có thể có `null`:

~~~java
import java.util.Objects;

boolean sameValue = Objects.equals(idA, idB);
~~~

Với entity tự sinh ID, hai đối tượng mới đều có `id == null`; `Objects.equals(null, null)` là `true`, nhưng **không được kết luận chúng là cùng entity**. Khi so sánh persistence ID theo PK tự sinh, cần xử lý trường hợp ID chưa có.

## 8. equals() và hashCode(): một trong những bẫy phổ biến nhất của entity

JPA không bắt buộc mọi entity phải override `equals()`/`hashCode()` theo một chiến lược duy nhất. Tuy nhiên, chúng rất quan trọng khi entity được đặt trong `Set`, dùng làm key của `Map`, hoặc được so sánh ở các transaction khác nhau.

### 8.1. Nếu giữ mặc định của Object

Nếu `Product` không override hai phương thức, `equals()` dùng Java object identity. Đây là hành vi nhất quán khi tất cả thao tác nằm trong cùng persistence context, vì cùng entity managed dùng một object.

Bất tiện xuất hiện khi cùng bản ghi được tải ở hai persistence context khác nhau: hai object có cùng khóa database nhưng `equals()` mặc định là false. Đây không phải lỗi của JPA mà là lựa chọn semantics của `Object.equals()`.

### 8.2. Cách viết dễ lỗi: equals() và hashCode() trực tiếp theo id tự sinh

Ví dụ **không nên sao chép máy móc**:

~~~java
// Minh họa bẫy thiết kế:
@Override
public boolean equals(Object other) {
    if (!(other instanceof Product p)) {
        return false;
    }
    return java.util.Objects.equals(id, p.id);
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(id);
}
~~~

Có ít nhất hai vấn đề:

1. Hai Product vừa tạo có `id == null` sẽ được coi là bằng nhau vì `Objects.equals(null, null)` trả true, dù đó là hai object mới độc lập.
2. Khi entity được thêm vào `HashSet` trước khi `id` được cấp, sau đó ID đổi từ `null` sang một giá trị mới thì `hashCode()` đổi. Điều này có thể làm `HashSet.contains(product)` không tìm ra object ở bucket ban đầu.

Ví dụ:

~~~java
Set<Product> products = new HashSet<>();

Product p = new Product("JAVA-042", "Java Book");
products.add(p); // hashCode có thể dựa vào id == null

em.persist(p);   // id có thể được cấp ngay hoặc khi provider flush
em.flush();

// Nếu hashCode giờ khác hashCode lúc thêm,
// products.contains(p) có thể trả false.
~~~

Việc đặt primary key do database sinh vào hàm hash thay đổi theo vòng đời entity cần được cân nhắc kỹ. **Không sửa ID bằng setter để “đồng bộ lại” dữ liệu**; đó là hướng xử lý sai.

### 8.3. Một chiến lược với ID tự sinh: chỉ so sánh khi ID không null

Đối với class entity đơn giản, không có phân cấp kế thừa entity và không có yêu cầu so sánh đặc biệt, có thể cân nhắc mẫu:

~~~java
// Trong class Product:
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Product p)) {
        return false;
    }

    Long currentId = getId();
    Long otherId = p.getId();
    return currentId != null && currentId.equals(otherId);
}

@Override
public int hashCode() {
    return Product.class.hashCode();
}
~~~

Ý tưởng:

- Cùng reference luôn bằng nhau.
- Hai object mới, khác reference, chưa có ID sẽ không bị coi là cùng entity chỉ vì đều có `null`.
- Hai instance `Product` khác nhau có cùng ID không null có thể được xem bằng nhau theo định danh entity.
- `hashCode()` có giá trị ổn định trước và sau khi sinh ID, giữ nguyên bucket nếu object đã được đặt vào hash collection.

Đổi lại, hash constant làm nhiều entity cùng đi vào một bucket, có thể kém hiệu quả với tập rất lớn. Đây chỉ là một **mẫu minh họa cho entity không có inheritance**. Trong thực tế, proxy của Hibernate, phân cấp entity, khả năng override, phạm vi tenant và cách provider sinh proxy có thể làm việc xác định “cùng loại entity” phức tạp hơn `instanceof`. Cần lựa chọn và kiểm thử chiến lược đúng với mapping và provider đang dùng; không có một đoạn `equals()` ngắn thích hợp cho mọi entity.

### 8.4. Khi dùng khóa nghiệp vụ bất biến

Nếu một khóa nghiệp vụ thực sự duy nhất và **không thay đổi trong vòng đời entity**, có thể cân nhắc `equals()/hashCode()` dựa trên khóa đó, thay vì ID tự sinh. Ví dụ `sku` là mã nhận diện bất biến, được cấp trước khi tạo Product và có ràng buộc unique ở database.

Điều kiện quan trọng là:

- Giá trị phải có mặt khi object tham gia collection và giữ ổn định sau đó.
- Quy tắc chuẩn hóa và so sánh trong Java phải tương thích với ràng buộc duy nhất của database (ví dụ xử lý chữ hoa/thường hoặc khoảng trắng).
- Giá trị phải duy nhất trong đúng phạm vi domain; nếu SKU chỉ duy nhất **trong mỗi cửa hàng**, có thể phải bao gồm mã cửa hàng/tenant.
- Nếu nghiệp vụ cho phép sửa SKU hoặc tái sử dụng mã, khóa này có thể không phù hợp cho `equals()/hashCode()`.

**Natural key và surrogate key là lựa chọn thiết kế dữ liệu; business equality và persistence identity là lựa chọn ngữ nghĩa đối tượng.** Chúng có thể liên quan nhưng không tự động giống nhau.

### 8.5. Proxy và kế thừa cần chú ý

Hibernate có thể trả về **proxy** thay vì instance class thuần, đặc biệt với lazy associations. Khi đó:

~~~java
product.getClass() == other.getClass()
~~~

có thể không phù hợp nếu một bên là proxy subclass của bên kia. Ngược lại, dùng `instanceof` thiếu cân nhắc trong hệ thống có entity inheritance có thể coi hai kiểu entity khác nhau có cùng ID là bằng nhau, gây lỗi tính đối xứng/bắc cầu của `equals()`.

Trước khi chọn cách so sánh entity, xác định rõ:

1. Có dùng Hibernate proxy hoặc bytecode enhancement?
2. Entity có kế thừa hoặc cùng bảng trong hierarchy không?
3. ID được gán trước hay được sinh sau `persist()`?
4. Entity có được dùng trong `HashSet`/`HashMap` khi còn transient không?
5. Nghiệp vụ có dùng nhiều datasource/tenant cùng tập giá trị ID không?

Không nên dùng tự động `@Data`, `@EqualsAndHashCode` của Lombok trên entity có nhiều quan hệ mà không kiểm soát trường tham gia so sánh. Việc đưa các association lazy hoặc collection hai chiều vào `equals()/hashCode()` có thể kích hoạt truy vấn, gây đệ quy vô hạn hoặc khiến hash thay đổi.

## 9. Khóa ghép: khi định danh entity gồm nhiều thuộc tính

Không phải primary key nào cũng chỉ có một `Long id`. Một bảng có thể cần định danh bằng hai cột. Ví dụ bảng đăng ký học:

~~~sql
CREATE TABLE enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
~~~

Ở đây, hàng `(student_id = 5, course_id = 8)` khác hàng `(student_id = 5, course_id = 9)`. Không thể nhận diện một hàng chỉ bằng `student_id`, vì cùng sinh viên có thể đăng ký nhiều khóa học.

### 9.1. Ánh xạ bằng @EmbeddedId

Tạo lớp giá trị biểu diễn ID ghép:

~~~java
package com.example.school;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class EnrollmentId implements Serializable {
    @Column(name = "student_id")
    private Long studentId;

    @Column(name = "course_id")
    private Long courseId;

    protected EnrollmentId() {}

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = Objects.requireNonNull(studentId);
        this.courseId = Objects.requireNonNull(courseId);
    }

    public Long getStudentId() {
        return studentId;
    }

    public Long getCourseId() {
        return courseId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof EnrollmentId that)) {
            return false;
        }
        return Objects.equals(studentId, that.studentId)
            && Objects.equals(courseId, that.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
~~~

Entity sử dụng khóa ghép:

~~~java
package com.example.school;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "enrollments")
public class Enrollment {
    @EmbeddedId
    private EnrollmentId id;

    @Column(name = "enrolled_at", nullable = false)
    private Instant enrolledAt;

    protected Enrollment() {}

    public Enrollment(EnrollmentId id, Instant enrolledAt) {
        this.id = id;
        this.enrolledAt = enrolledAt;
    }

    public EnrollmentId getId() {
        return id;
    }
}
~~~

Đọc entity:

~~~java
EnrollmentId key = new EnrollmentId(5L, 8L);
Enrollment enrollment = em.find(Enrollment.class, key);
~~~

Với khóa ghép:

- Toàn bộ `EnrollmentId(studentId, courseId)` là **giá trị định danh entity**, tương ứng tổ hợp PK trong bảng.
- Lớp PK cần có ngữ nghĩa bằng nhau và hash nhất quán theo các thành phần, triển khai `Serializable` và constructor không tham số phù hợp.
- Các giá trị PK phải ổn định trong vòng đời entity; với entity persisted, không tự ý đổi trường thuộc PK.
- Nếu ánh xạ association `Student` và `Course` cùng với khóa ghép, có thể sử dụng `@MapsId` để đồng bộ khóa ngoại/khóa chính theo mapping phù hợp. Ví dụ ở đây chỉ ánh xạ hai cột ID để tập trung vào khái niệm định danh.

JPA còn hỗ trợ `@IdClass`. Với `@IdClass`, các thành phần ID được khai báo trực tiếp trên entity và một class riêng mô tả khóa tổng hợp. Hai cách đều nhằm ánh xạ **một identity nhiều cột**, không phải tạo ra nhiều identity độc lập cho cùng entity.

### 9.2. Hai trường cùng giá trị chưa chắc có cùng ý nghĩa ở hai entity

Nếu `EnrollmentId(5, 8)` và một entity khác cũng có cặp ID `(5, 8)`, chúng vẫn là các entity khác nhau vì **kiểu entity cũng là một phần của ngữ nghĩa identity**. Lớp `EnrollmentId` chỉ đại diện cho cấu trúc giá trị khóa, không phải instance của một hàng hay một EntityManager.

## 10. ID được sinh ở đâu, và điều đó ảnh hưởng gì?

JPA cho phép nhiều chiến lược cấp ID. Khi quyết định thiết kế, cần phân biệt **nguồn sinh giá trị** và **định danh của entity**.

| Chiến lược | Ví dụ | Đặc điểm quan trọng |
|---|---|---|
| Gán thủ công | `@Id String code` rồi set trong constructor | Ứng dụng tạo ID trước `persist()`; không chứng minh DB row đã có |
| `GenerationType.IDENTITY` | Cột tự tăng/identity của DBMS | ID thường do DB cung cấp khi insert; có thể ảnh hưởng khả năng batch insert |
| `GenerationType.SEQUENCE` | Sequence của database | Provider lấy giá trị sequence, có thể cấp ID trước câu INSERT |
| `GenerationType.TABLE` | Bảng hỗ trợ cấp số | Provider dùng bảng riêng để quản lý ID; cần xem xét contention/hiệu năng |
| `GenerationType.UUID` | UUID được provider sinh | Có trong Jakarta Persistence 3.1; cần dùng provider và phiên bản hỗ trợ tương thích |
| `GenerationType.AUTO` | Provider chọn chiến lược | Cách thực tế phụ thuộc provider và database |

Ví dụ dùng sequence trên PostgreSQL:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_seq_gen"
)
@SequenceGenerator(
    name = "product_seq_gen",
    sequenceName = "product_id_seq",
    allocationSize = 50
)
private Long id;
~~~

Nếu dùng mapping này, schema database và chiến lược sinh ID phải tương thích với sequence `product_id_seq`. Giá trị `allocationSize` liên quan tới cách provider cấp phát các dải ID, không chỉ là chuyện cú pháp. Không tùy tiện thay `IDENTITY` thành `SEQUENCE` khi schema đang dùng identity column mà chưa thay đổi migration và cấu hình tương ứng.

### 10.1. UUID có giải quyết mọi vấn đề identity?

UUID thường hữu ích khi nhiều dịch vụ muốn tạo định danh không cần phối hợp trực tiếp với một sequence trung tâm. Nhưng:

- UUID là **giá trị ID**, không phải Java reference identity.
- UUID trong cùng trường có thể dùng làm primary key nếu schema được thiết kế tương ứng.
- UUID không thay cho ràng buộc duy nhất nghiệp vụ, transaction hay optimistic locking.
- Kiểu lưu trữ UUID, thứ tự sinh, locality trong index và version UUID có thể ảnh hưởng hiệu năng.

Vì vậy, chọn UUID hay số nguyên chủ yếu dựa vào kiến trúc dữ liệu và yêu cầu triển khai; khái niệm JPA entity identity không thay đổi.

## 11. Định danh trong quan hệ @ManyToOne

Giả sử có entity `OrderLine` tham chiếu `Product`:

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    protected OrderLine() {}

    public Product getProduct() {
        return product;
    }
}
~~~

Mối liên hệ ba tầng:

~~~text
OrderLine Java object
  |
  | thuộc tính: Product product
  v
Product Java reference / có thể là lazy proxy
  |
  | JPA entity identity: (Product, product.id)
  v
DB: order_lines.product_id ---> products.id (PRIMARY KEY)
~~~

Trong ví dụ này:

- `OrderLine.id` là định danh entity và PK của **dòng hàng**, không phải của Product.
- `OrderLine.product` là một tham chiếu Java tới entity Product; nó có thể chứa object đã tải hoặc proxy lazy do provider quản lý.
- `order_lines.product_id` là foreign key, dùng để tham chiếu PK của Product.
- Một Product có thể được tham chiếu bởi nhiều OrderLine; nhiều Java reference có thể trỏ đến cùng một instance managed trong cùng persistence context.

Khi chỉ cần khóa của một entity liên quan, một số provider có thể lấy ID qua proxy mà chưa cần tải đủ trường của entity; hành vi chi tiết phụ thuộc provider và cách truy cập. Không nên mặc định rằng mọi lần `getProduct().getId()` đều tạo SQL, cũng không nên mặc định rằng không có SQL trong mọi cấu hình.

## 12. Đừng nhầm ID với những thuộc tính khác

| Thuộc tính/cơ chế | Đặc điểm | Có phải entity identity? |
|---|---|---|
| `@Id` / `@EmbeddedId` | Định danh entity | Có |
| `@GeneratedValue` | Cách tạo giá trị cho ID | Không tự nó là identity; dùng cùng `@Id` |
| `@Column(unique = true)` | Khai báo duy nhất cho cột/schema | Không mặc định là `@Id` |
| `@NaturalId` của Hibernate | Khai báo natural ID riêng của Hibernate | Khác với định danh JPA bằng `@Id` |
| `@Version` | Phát hiện cập nhật đồng thời theo optimistic locking | Không |
| `System.identityHashCode()` | Hash liên quan object identity trong JVM | Không |
| `equals()/hashCode()` | Contract so sánh Java do class quyết định | Không tự động là entity identity |
| Object reference `==` | Xác định cùng Java instance | Không tự động suy ra tồn tại DB row |

### 12.1. @Version không phải một phần của khóa chính

Ví dụ:

~~~java
@Version
private long version;
~~~

`version` được dùng để phát hiện xung đột cập nhật theo optimistic locking. Nếu một Product đổi từ version 3 sang 4, nó **vẫn là Product có ID 42**, không trở thành entity mới. Số phiên bản không phải một phần của primary key trừ khi mô hình dữ liệu cố ý thiết kế một khóa khác, và đó là bài toán riêng.

### 12.2. Tên hiển thị và ID

Một người dùng có thể thấy “Java Book” là tên của Product, nhưng đổi tên không làm thay đổi PK. Tương tự, email người dùng hoặc mã đơn hàng hiển thị có thể là khóa nghiệp vụ, trong khi primary key vẫn là một số/UUID nội bộ. Khi xây API hoặc UI, cần xác định rõ trường nào được dùng để định danh tài nguyên và trường nào chỉ để hiển thị.

## 13. Các tình huống thực tế để tự kiểm tra hiểu biết

### Tình huống A: cùng instance trong một transaction

~~~java
Product p1 = em.find(Product.class, 42L);
Product p2 = em.find(Product.class, 42L);
~~~

Nếu entity tồn tại và cả hai thao tác sử dụng cùng persistence context, `p1 == p2` là `true`. Provider đã quản lý một instance cho danh tính `(Product, 42)`.

### Tình huống B: cùng hàng, hai request khác nhau

Request thứ nhất và thứ hai tạo EntityManager khác nhau, đều tải Product ID 42. `p1 == p2` thường là `false`, mặc dù hai object đại diện cho cùng bản ghi. `p1.equals(p2)` phụ thuộc cách entity triển khai `equals()`; không có quy tắc toàn cục bắt buộc mọi entity tự coi bằng nhau ở hai context.

### Tình huống C: hai sản phẩm mới cùng id = null

~~~java
Product p1 = new Product("JAVA-100", "Java Basics");
Product p2 = new Product("JAVA-200", "Java Advanced");
~~~

Hai object đều có `getId() == null` với chiến lược tự sinh. Chúng **không phải cùng một Product**. Dùng `Objects.equals(p1.getId(), p2.getId())` riêng lẻ sẽ trả true nhưng dẫn tới kết luận sai.

### Tình huống D: hai entity khác bảng cùng id 42

`Product(id=42)` và `Customer(id=42)` có cùng **giá trị số**, không có cùng **entity identity**; khóa chính thuộc hai bảng khác nhau. Mã Java chỉ dùng giá trị số ID để quyết định hai object bằng nhau sẽ sai.

### Tình huống E: merge object detached

Một Product ID 42 được tải trong transaction cũ, sau đó context đóng. Khi merge vào context mới, provider trả về một managed instance; object detached cũ vẫn giữ nguyên Java identity. **Dùng instance trả về từ `merge()`** khi muốn thao tác tiếp trong context mới.

### Tình huống F: ID thay đổi sau khi đặt vào HashSet

Entity được thêm vào `HashSet` khi ID còn null, rồi provider cấp ID. Nếu `hashCode()` phụ thuộc ID, cấu trúc hash có thể hoạt động không đúng kỳ vọng. Chọn chiến lược hash ổn định hoặc tránh đưa entity chưa ổn định identity vào hashed collection.

### Tình huống G: ứng dụng đa tenant

Nếu mỗi tenant có bảng `products` riêng và đều tồn tại `id=42`, ID đơn lẻ chưa đủ để nhận diện một thực thể **trên toàn ứng dụng**. Cần kèm tenant hoặc namespace trong cache, API, quyền truy cập và mô hình định danh phù hợp. JPA persistence identity trong một context và khóa chính của một bảng không tự bảo đảm unique toàn hệ thống đa tenant.

## 14. Quy tắc thiết kế và sử dụng trong dự án JPA

Khi thiết kế entity mới:

1. **Chọn đúng primary key** ở DB: khóa đơn hay khóa ghép, natural hay surrogate, nguồn sinh ID và các foreign key liên quan.
2. **Ánh xạ identity tường minh** bằng `@Id` hoặc `@EmbeddedId`; bảo đảm schema và mapping đồng bộ.
3. **Giữ ID ổn định** sau khi entity đã được persist. Không cho phép chỉnh sửa PK như một thuộc tính nghiệp vụ bình thường.
4. **Tách khóa nghiệp vụ khỏi PK nếu cần**: mã `sku` có thể unique mà không cần là primary key.
5. **Hiểu phạm vi persistence context**: một instance managed cho mỗi entity identity trong context; context khác có thể trả object khác.
6. **Quy định equals/hashCode có chủ đích** dựa trên yêu cầu của domain, giá trị ID chưa được cấp, entity inheritance và proxy của provider.
7. **Không dùng Java identity làm khóa database**: `==`, `Object.hashCode()` và `System.identityHashCode()` không thay thế PK.
8. **Không dùng ID để suy ra trạng thái transaction**: có ID không đồng nghĩa row đã commit, detached không đồng nghĩa entity đã biến mất.
9. **Không bỏ qua ràng buộc DB**: `@Id` và annotations mô tả mapping, trong khi database thực thi PRIMARY KEY, UNIQUE và FOREIGN KEY.
10. **Xử lý concurrency riêng**: cùng ID không có nghĩa dữ liệu hai phiên đọc luôn giống nhau; dùng version/locking và transaction isolation thích hợp.

### Bài tập thực hành

**Bài 1.** Giả sử `Product a = new Product("A", "One")` và `Product b = new Product("B", "Two")`. Cả hai `getId()` đều null. Hỏi:

- `a == b` là gì?
- `Objects.equals(a.getId(), b.getId())` là gì?
- Vì sao hai kết quả không được dùng thay thế nhau để kết luận cùng entity?

**Gợi ý:** hai object Java khác nhau nhưng phép so sánh hai giá trị null là true; chưa có persistence ID đủ để nhận diện chúng là một.

**Bài 2.** Với cùng một `EntityManager em`, gọi `find(Product.class, 42L)` hai lần. Nếu hàng tồn tại, kết quả có cùng reference không? Nếu mỗi lần dùng một `EntityManager` độc lập, kết quả có buộc cùng reference không?

**Gợi ý:** tính đồng nhất instance được JPA bảo đảm trong cùng persistence context, không áp dụng qua các context độc lập.

**Bài 3.** Thiết kế bảng `enrollments(student_id, course_id, enrolled_at)` sao cho mỗi sinh viên chỉ đăng ký mỗi khóa học một lần. Đề xuất `PRIMARY KEY` và ánh xạ JPA tương ứng.

**Gợi ý:** PK `(student_id, course_id)` và `@EmbeddedId` hoặc `@IdClass`.

**Bài 4.** Một Product có `id=42` và `version=7`. Khi cập nhật tên, version thành 8. Hỏi entity identity và database primary key có đổi không?

**Gợi ý:** không; version phục vụ optimistic locking, không thay thế ID.

Điều cần nhớ là **định danh Java trả lời “có phải cùng object?”, định danh entity trả lời “có phải cùng entity trong mô hình persistence?”, còn khóa chính trả lời “database nhận diện hàng này bằng khóa nào?”**. Hiểu rõ phạm vi của từng loại giúp thiết kế mapping chính xác, tránh lỗi so sánh đối tượng và xử lý đúng các entity khi chúng đi qua nhiều transaction, persistence context và tầng dữ liệu.
