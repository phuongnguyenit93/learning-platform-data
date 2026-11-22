# Phân biệt DAO, Repository, Service và đối tượng miền trong Spring Framework

> **Bối cảnh học tập:** Bài này thuộc phần **Thiết kế tầng dữ liệu** của Spring Framework. Bốn thuật ngữ DAO, Repository, Service và đối tượng miền (domain object) thường xuất hiện cùng nhau nhưng mô tả **những trách nhiệm khác nhau**. Chúng không mặc nhiên là bốn lớp bắt buộc của mọi ứng dụng. Mục tiêu là xác định nơi đặt truy vấn dữ liệu, quy tắc nghiệp vụ, điều phối giao dịch và mô hình nghiệp vụ; biết khi nào có thể gộp hoặc tách chúng một cách có lý do.

## 1. Một tình huống cụ thể để phân biệt vai trò

Một cửa hàng có hai sản phẩm: sách Java còn 5 cuốn và sách Spring còn 3 cuốn. Yêu cầu `checkout(1, 2, 2, 1)` nghĩa là đặt 2 cuốn Java và 1 cuốn Spring trong một lần thanh toán. Hệ thống cần:

1. Xác định hai sản phẩm tồn tại, số lượng yêu cầu dương và không vượt tồn kho.
2. Giảm tồn kho tương ứng.
3. Nếu một sản phẩm không đủ hàng, **toàn bộ yêu cầu thất bại**, không giữ lại việc trừ kho ở sản phẩm trước.
4. Khi có yêu cầu đồng thời, không ghi đè sai trạng thái tồn kho mà người khác vừa thay đổi.

Bốn thành phần giải quyết những câu hỏi khác nhau:

- **Đối tượng miền `Product`:** “Một sản phẩm có được phép đặt thêm `quantity` không? Nếu có, trạng thái tồn kho hợp lệ tiếp theo là gì?”
- **DAO `JdbcProductDao`:** “Đọc các cột `id, sku, available_stock, version` từ bảng `product` và gửi câu UPDATE ra sao?”
- **Repository `ProductRepository`:** “Tầng nghiệp vụ tìm và lưu một `Product` bằng giao diện nào, không cần biết SQL hay bảng dữ liệu?”
- **Application Service `CheckoutService`:** “Thực hiện use case đặt nhiều sản phẩm theo trình tự nào, trong một giao dịch nào, và trả lỗi nghiệp vụ ra sao?”

**Cách nhớ thực dụng:** domain object nắm quy tắc của trạng thái nghiệp vụ; DAO nắm thao tác lưu trữ mức thấp; Repository là cửa ngõ truy xuất/lưu đối tượng miền; Service điều phối một hành động nghiệp vụ hoàn chỉnh.

## 2. So sánh trách nhiệm trong một bảng

| Tiêu chí | Đối tượng miền (Domain object) | DAO (Data Access Object) | Repository | Service (Application Service) |
| --- | --- | --- | --- | --- |
| Trọng tâm | Trạng thái, ý nghĩa, quy tắc và hành vi nghiệp vụ | Kỹ thuật đọc/ghi dữ liệu, SQL, mapping hàng | Cung cấp tập hợp các đối tượng/aggregate theo ngôn ngữ miền | Điều phối use case, chính sách thao tác, transaction |
| Đầu vào điển hình | Số lượng, giá trị, trạng thái khác | Khóa SQL, điều kiện truy vấn, tham số | ID miền, tiêu chí có ý nghĩa trong miền, domain object | Command/request của use case |
| Đầu ra điển hình | Trạng thái/hành vi hợp lệ hoặc lỗi quy tắc | Row, persistence record, số hàng cập nhật | Domain object/aggregate hoặc `Optional` | Kết quả use case, receipt/DTO hoặc lỗi |
| Biết JDBC/JPA? | Tốt nhất không cần biết | Thường biết rõ JDBC/SQL hoặc API lưu trữ | **Contract** không cần biết; **adapter implementation** biết | Không cần biết chi tiết truy vấn |
| Biết transaction? | Không tự bắt đầu transaction | Tham gia transaction do tầng trên quản lý | Tham gia transaction, thường không quyết định phạm vi use case | Thường xác định ranh giới cho cả use case |
| Ví dụ | `product.reserve(2)` | `UPDATE product SET ...` | `products.findById(id)`, `products.save(product)` | `checkout(first, second)` |

**Đây là phân biệt theo trách nhiệm, không phải theo tên class.** Một class mang tên `ProductRepository` nhưng chỉ trả `ResultSet` và chứa SQL có thể đang làm công việc DAO. Một `ProductService` chỉ chuyển tiếp từng lời gọi CRUD, không có orchestration hay policy nào, có thể là một tầng thừa. Ngược lại, một lớp dùng `@Repository` trong Spring có thể trực tiếp thực hiện DAO và Repository khi bài toán đơn giản; không bắt buộc tạo thêm một adapter chỉ để đủ bốn lớp.

## 3. Quan hệ gọi và quan hệ phụ thuộc

Một thiết kế có ranh giới rõ ràng thường đi theo luồng:

~~~mermaid
flowchart TD
    Caller["Controller / CLI / message consumer"] --> App["CheckoutService\nuse case + transaction"]
    App --> Domain["Product\nkiểm tra quy tắc, tạo trạng thái hợp lệ"]
    App --> Port["ProductRepository\ncontract theo miền"]
    Port -. "được hiện thực bởi" .-> Adapter["JdbcProductRepository\nmapping domain <-> row"]
    Adapter --> DAO["JdbcProductDao\nSQL + JdbcTemplate"]
    DAO --> DB[("Database / product table")]
~~~

Luồng mũi tên là cách code **gọi hoặc phụ thuộc**. Product **không gọi ngược xuống database**. Application Service thao tác trên Product và interface Repository. Adapter ánh xạ giữa Product với dữ liệu thực tế; DAO phụ trách SQL. SQL đi qua JDBC/DataSource đến DBMS, nhưng đó là cơ chế truy cập dữ liệu bên dưới DAO chứ không tạo thêm một vai trò nghiệp vụ.

Cấu trúc module có thể chia thành:

~~~text
com.example.boundaries
├── domain
│   ├── Product.java                 # đối tượng miền
│   └── ProductRepository.java       # cổng truy xuất theo miền
├── service
│   └── CheckoutService.java         # use case + transaction
├── data
│   ├── JdbcProductDao.java          # SQL, ProductRow
│   └── JdbcProductRepository.java   # adapter + mapping
└── DaoRepositoryLessonApplication.java
~~~

Trong cách phân lớp định hướng miền, `domain` không import `data`; `data` có thể import `domain` để hiện thực hợp đồng. Spring tiêm implementation của `ProductRepository` vào Service tại runtime. Đây là **đảo chiều phụ thuộc ở mức contract**, khác với việc service phụ thuộc trực tiếp vào một lớp SQL cụ thể.

Cũng có thể đặt repository interface trong package `application` thay vì `domain`, tùy quy mô và trường phái kiến trúc. Vấn đề cần giữ là **contract phản ánh nhu cầu nghiệp vụ** và không buộc tầng trên biết chi tiết lưu trữ.

## 4. Đối tượng miền: mô hình hóa ý nghĩa và bất biến

**Domain object** là đối tượng Java dùng để thể hiện khái niệm của nghiệp vụ. Nó có thể là:

- **Entity miền:** có danh tính ổn định, ví dụ một Product có ID; trạng thái có thể thay đổi theo thời gian. Trong DDD, so sánh entity thường quan tâm identity, không chỉ toàn bộ field.
- **Value object:** được định nghĩa bằng giá trị, ví dụ `Money(amount, currency)` hoặc `Address`; thường bất biến và so sánh bằng giá trị.
- **Aggregate:** một nhóm đối tượng với một aggregate root kiểm soát các bất biến xuyên nhóm. Repository thường thao tác ở ranh giới aggregate thay vì tạo repository cho mọi bảng.
- **Domain service:** mô tả quy tắc miền không thuộc tự nhiên về một entity/value object riêng lẻ, ví dụ chính sách tính phí dựa trên nhiều yếu tố; khác Application Service điều phối use case.

Ví dụ quy tắc `Product.reserve(quantity)`:

~~~java
public Product reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }
    if (quantity > availableStock) {
        throw new IllegalStateException("Insufficient stock: " + sku);
    }
    return new Product(id, sku, availableStock - quantity, version);
}
~~~

Đây là hành vi miền: sản phẩm không cho phép số lượng đặt bằng 0, âm hoặc lớn hơn tồn kho. Nó **không cần biết** dữ liệu nằm trong PostgreSQL, H2, một file hay bộ nhớ. Ví dụ dùng immutable `record Product` để dễ theo dõi sự chuyển trạng thái; record này là **ảnh chụp trạng thái miền**. Nếu hệ thống dùng đầy đủ mô hình DDD entity có equality theo ID, hãy cân nhắc một class với ngữ nghĩa identity phù hợp, thay vì mặc nhiên lấy equality của Java record (so sánh tất cả component) làm equality của entity.

### Bất biến miền và ràng buộc database bổ trợ nhau

Kiểm tra `availableStock >= 0` khi tạo Product giúp ngăn tạo trạng thái Java vô nghĩa; `CHECK (available_stock >= 0)` trong schema giúp bảo vệ dữ liệu khi có nhiều đường ghi. Hai mức kiểm tra có mục đích khác nhau: domain diễn đạt lý do nghiệp vụ; database bảo toàn cấu trúc và ràng buộc dữ liệu, kể cả khi một tiến trình khác ghi trực tiếp vào bảng.

### Domain object không đồng nghĩa JPA entity

Một class gắn `@Entity` là đối tượng thuộc mô hình persistence của JPA. Nó **có thể** đồng thời là entity miền nếu cấu trúc và hành vi phù hợp; nhưng trong hệ thống phức tạp, JPA entity chứa mapping kỹ thuật, lazy proxy hoặc quan hệ bảng có thể được tách khỏi domain model. Không phải mỗi bảng phải có một domain entity, và không phải mỗi domain object phải có một bảng.

## 5. DAO: chi tiết kỹ thuật của truy cập dữ liệu

DAO thường biết “cách nói chuyện với kho dữ liệu”:

- Viết SQL/JPQL hoặc gọi driver/client; gắn tham số thay vì nối chuỗi đầu vào.
- Ánh xạ `ResultSet` thành `ProductRow` hoặc kiểu persistence thích hợp.
- Trả số hàng đã cập nhật, khóa, dữ liệu truy vấn, hoặc exception truy cập dữ liệu.
- Dùng API quản lý tài nguyên phù hợp (với Spring JDBC, `JdbcTemplate` lo vòng đời Statement/ResultSet và phối hợp Connection).

Ví dụ chữ ký DAO trong bài thực hành:

~~~java
Optional<ProductRow> findById(long id);
int updateStock(long id, int newStock, long expectedVersion);
~~~

Chữ ký nói ngôn ngữ lưu trữ: một hàng của bảng sản phẩm và số hàng SQL thực sự cập nhật. DAO không cần quyết định “giỏ hàng có hợp lệ?”, “phải xử lý hai sản phẩm như một đơn vị?”, hoặc “giao dịch thất bại nên trả mã HTTP nào?”. Những vấn đề đó thuộc miền, Service hoặc tầng giao tiếp.

**DAO là pattern**, không phải một annotation riêng của Spring. Annotation `@Repository` của Spring là một stereotype đăng ký bean tầng persistence và có thể kích hoạt dịch ngoại lệ persistence; không có quy tắc rằng mọi DAO phải tên `*Repository` hoặc mọi class gắn `@Repository` đều đáp ứng trọn DDD Repository pattern.

Trong dự án JDBC nhỏ, một class `JdbcProductRepository` chứa thẳng `JdbcTemplate` có thể hợp lý. Việc chia thành `JdbcProductDao` và `JdbcProductRepository` nên tạo giá trị thật (tách SQL/row mapping khỏi domain mapping, chia sẻ adapter, hỗ trợ migrate backend), thay vì chỉ tăng số file.

## 6. Repository: giao diện theo ngôn ngữ của miền

Repository tạo cảm giác thao tác trên **tập đối tượng miền**. Chẳng hạn:

~~~java
public interface ProductRepository {
    Optional<Product> findById(long id);
    void save(Product product);
}
~~~

Service biết `Product` và `ProductRepository`; nó không cần biết bảng `product`, câu `SELECT`, `JdbcTemplate` hay cách map một dòng SQL. Adapter chuyển từ `ProductRow` sang `Product` khi đọc và từ `Product` sang tham số SQL khi ghi.

Chữ “Repository” có **hai cách sử dụng thường gặp**:

1. **Repository pattern theo thiết kế miền/DDD:** một contract phản ánh cách lấy/lưu aggregate bằng khái niệm miền; interface có thể do tầng miền hoặc application sở hữu, adapter ở infrastructure hiện thực.
2. **Spring Data repository:** interface như `JpaRepository<ProductEntity, Long>` sử dụng cơ chế sinh implementation của Spring Data. Nó giúp giảm mã persistence nhưng vẫn là hạ tầng dựa trên entity và quy ước framework; không tự biến mọi truy vấn CRUD thành một mô hình miền tốt.

Ví dụ một phương thức `findActiveOrdersForCustomer(customerId)` diễn đạt rõ nhu cầu miền. Không cần thiết phải mở vô hạn `findByField1AndField2And...` chỉ vì Spring Data hỗ trợ derived query methods. Ngược lại, CRUD rất đơn giản có thể chỉ cần Spring Data repository trực tiếp bên trong Service, miễn là kiến trúc không đòi một persistence port riêng.

### Repository nên theo bảng hay theo aggregate?

Với ứng dụng CRUD thuần, repository theo entity/bảng là lựa chọn phổ biến. Trong thiết kế DDD, repository thường theo **aggregate root**. Ví dụ `Order` gồm `OrderLine`; nếu chỉnh `OrderLine` có thể phá vỡ invariant của đơn hàng, nên cập nhật qua `Order` và `OrderRepository` sẽ giúp kiểm soát luật. Không có nghĩa mọi hệ thống đều phải áp dụng DDD đầy đủ; chọn theo độ phức tạp quy tắc.

## 7. Service: điều phối use case, bảo toàn tính nguyên tử

Application Service mô tả *hành động hệ thống thực hiện* thay vì chi tiết SQL:

~~~text
checkout(...)
    -> kiểm tra yêu cầu tổng thể
    -> lấy Product A qua ProductRepository
    -> yêu cầu Product A reserve(qtyA)
    -> lưu Product A
    -> lấy Product B qua ProductRepository
    -> yêu cầu Product B reserve(qtyB)
    -> lưu Product B
    -> hoàn tất hoặc rollback toàn bộ
~~~

Những trách nhiệm thích hợp cho Service gồm:

- Điều phối nhiều đối tượng miền/repository; quyết định thứ tự các bước của một use case.
- Định nghĩa transaction boundary phù hợp, ví dụ `@Transactional` cho checkout.
- Kiểm soát authorization ở tầng ứng dụng (nếu cần) và chính sách xử lý lệnh, idempotency, orchestration tích hợp khác.
- Chuyển trạng thái miền thành kết quả đầu ra của use case (DTO/receipt) mà không đưa mô hình persistence ra API.

**Không nên dồn toàn bộ luật vào Service.** Một Service chứa hàng trăm câu `if` diễn đạt trực tiếp mọi trạng thái Product, còn Product chỉ giữ getters/setters, thường là dấu hiệu **anemic domain model** trong bài toán có quy tắc phức tạp. Khi quy tắc chỉ liên quan tới trạng thái của một đối tượng, ưu tiên đặt cùng đối tượng đó; khi use case phối hợp nhiều đối tượng và tài nguyên, Service điều phối.

### Application Service khác Domain Service

- **Application Service:** “Lấy dữ liệu, gọi quy tắc miền, lưu kết quả, xuất sự kiện sau giao dịch” — điều phối công việc và transaction.
- **Domain Service:** “Tính chính sách chiết khấu dựa trên trạng thái đơn hàng và khách hàng” — một quy tắc nghiệp vụ không thuộc riêng một entity.

Một domain service không nhất thiết gắn `@Service`; nó có thể là Java class thuần. Trong Spring, `@Service` là stereotype đăng ký bean, **không tự phân biệt** application service với domain service.

### Transaction thường bao quanh use case

Trong chế độ proxy thông dụng của Spring, `@Transactional` trên public Service method được gọi **qua Spring proxy**. Các thao tác repository/JDBC cùng DataSource transaction-aware sẽ tham gia transaction hiện hành. Lỗi thuộc rollback rule (mặc định như unchecked exception) dẫn tới rollback. Nếu chỉ đánh dấu transaction cho từng DAO method riêng lẻ, việc lưu hai sản phẩm có thể commit độc lập và không bảo toàn nguyên tử của checkout.

Một private helper được gọi **bên trong** public transactional method vẫn chạy trong transaction đã mở. Nhưng đặt `@Transactional` **chỉ** trên private helper hoặc dựa vào self-invocation từ `this.method()` không kích hoạt lời gọi proxy mới; phải thiết kế ranh giới rõ ràng.

## 8. Phân biệt Domain object, Persistence model, DTO và Command

Các kiểu thường bị đặt lẫn với bốn thành phần chính:

| Kiểu | Mục đích | Ví dụ | Có nên để lộ qua API? |
| --- | --- | --- | --- |
| Domain object | Quy tắc và trạng thái có ý nghĩa nghiệp vụ | `Product`, `Money`, `Order` | Tùy kiến trúc, nhưng thường có lớp chuyển đổi |
| Persistence model/row | Mô tả cách dữ liệu được lưu | `ProductRow(id, sku, stock, version)` | Thường không |
| JPA entity | Đối tượng được JPA quản lý/mapping đến bảng | `@Entity ProductEntity` | Tránh xuất trực tiếp khi có lazy fields, data nhạy cảm hoặc coupling schema |
| Command/request DTO | Biểu đạt đầu vào use case | `CheckoutCommand(productIds, quantities)` | Có thể nhận/được tạo từ HTTP request |
| Response DTO | Hình dạng dữ liệu đầu ra | `CheckoutReceipt(orderId, lines)` | Thường có |

**Mapping không phải nghiệp vụ:** `ProductRow → Product` chỉ chuyển cấu trúc lưu trữ sang biểu diễn miền; kiểm tra số lượng đặt hợp lệ nằm ở hành vi domain. Nếu Product và bảng trùng nhau trong bài toán nhỏ, có thể dùng chung model khi chấp nhận coupling. Tách model là một **lựa chọn về độ phức tạp và khả năng thay đổi**, không phải lễ nghi bắt buộc.

## 9. Ví dụ chạy được: Java 21, Spring Boot, Spring JDBC và H2

Ví dụ cố ý giữ **cả DAO và Repository adapter** để nhìn thấy ranh giới. Trong dự án thật, có thể gộp hai lớp hạ tầng nếu chúng chỉ chuyển tiếp vô ích. Chương trình console khởi chạy Spring context, lấy các bean qua DI, thao tác hai sản phẩm và in trạng thái trước/sau. Không cần server HTTP.

### 9.1. Tổ chức file và dependency

~~~text
build.gradle
src/main/resources/application.properties
src/main/resources/schema.sql
src/main/resources/data.sql
src/main/java/com/example/boundaries/DaoRepositoryLessonApplication.java
src/main/java/com/example/boundaries/domain/Product.java
src/main/java/com/example/boundaries/domain/ProductRepository.java
src/main/java/com/example/boundaries/data/JdbcProductDao.java
src/main/java/com/example/boundaries/data/JdbcProductRepository.java
src/main/java/com/example/boundaries/service/CheckoutService.java
~~~

**`build.gradle`** — ví dụ dùng các phiên bản cố định đã biết để tái hiện. Java toolchain 21 phải được cài hoặc cấu hình Gradle cung cấp.

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**`src/main/resources/application.properties`** — Spring Boot khởi tạo DataSource/HikariCP và chạy hai script SQL. Đặt chế độ không có web server vì chương trình chỉ dùng `CommandLineRunner`.

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:dao_repository_lesson;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**`src/main/resources/schema.sql`** — `version` phục vụ optimistic concurrency, còn CHECK giúp DB tự bảo vệ tồn kho không âm.

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    available_stock INT NOT NULL CHECK (available_stock >= 0),
    version BIGINT NOT NULL CHECK (version >= 0)
);
~~~

**`src/main/resources/data.sql`**:

~~~sql
INSERT INTO product (id, sku, available_stock, version)
VALUES (1, 'JAVA-BOOK', 5, 0);

INSERT INTO product (id, sku, available_stock, version)
VALUES (2, 'SPRING-BOOK', 3, 0);
~~~

### 9.2. Domain object thuần Java: `Product.java`

~~~java
package com.example.boundaries.domain;

public record Product(long id, String sku, int availableStock, long version) {
    public Product {
        if (id <= 0 || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid product identity");
        }
        if (availableStock < 0 || version < 0) {
            throw new IllegalArgumentException("Invalid product state");
        }
    }

    public Product reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (quantity > availableStock) {
            throw new IllegalStateException("Insufficient stock: " + sku);
        }
        return new Product(id, sku, availableStock - quantity, version);
    }
}
~~~

**Điểm cần quan sát:** Không có `@Component`, `@Entity`, `JdbcTemplate` hay SQL. Domain bảo vệ trạng thái hợp lệ và diễn đạt hành vi `reserve` bằng từ vựng kinh doanh. Đối tượng trả về giữ nguyên `version` đã đọc; phiên bản chỉ tăng khi SQL UPDATE thành công. Do đây là Java record bất biến, repository lưu snapshot mới sau khi hành vi miền chạy.

### 9.3. Repository contract: `ProductRepository.java`

~~~java
package com.example.boundaries.domain;

import java.util.Optional;

public interface ProductRepository {
    Optional<Product> findById(long id);
    void save(Product product);
}
~~~

Service sẽ import interface này, không import JDBC implementation. Contract chỉ nói về Product và ID; việc thiếu dữ liệu được biểu đạt bằng `Optional.empty()`.

### 9.4. DAO: `JdbcProductDao.java`

~~~java
package com.example.boundaries.data;

import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class JdbcProductDao {
    private final JdbcTemplate jdbc;

    public JdbcProductDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<ProductRow> findById(long id) {
        return jdbc.query(
            "SELECT id, sku, available_stock, version FROM product WHERE id = ?",
            (rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getInt("available_stock"),
                rs.getLong("version")
            ),
            id
        ).stream().findFirst();
    }

    public int updateStock(long id, int newStock, long expectedVersion) {
        return jdbc.update(
            "UPDATE product " +
            "SET available_stock = ?, version = version + 1 " +
            "WHERE id = ? AND version = ?",
            newStock, id, expectedVersion
        );
    }
}

record ProductRow(long id, String sku, int stock, long version) {}
~~~

**Đây là hai kiểu trong một file Java:** public class `JdbcProductDao` và package-private record `ProductRow` đều nằm cùng package `com.example.boundaries.data`, hợp lệ với Java. DAO trả **row model** và số dòng UPDATE, không trả khái niệm checkout. `?` được bind bằng PreparedStatement qua JdbcTemplate, tránh SQL injection do nối chuỗi tham số. Truy vấn 0 hàng trả `Optional.empty()`; UPDATE 0 hàng báo điều kiện `version` không khớp hoặc bản ghi không tồn tại.

### 9.5. Repository adapter: `JdbcProductRepository.java`

~~~java
package com.example.boundaries.data;

import com.example.boundaries.domain.Product;
import com.example.boundaries.domain.ProductRepository;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcProductRepository implements ProductRepository {
    private final JdbcProductDao dao;

    public JdbcProductRepository(JdbcProductDao dao) {
        this.dao = dao;
    }

    @Override
    public Optional<Product> findById(long id) {
        return dao.findById(id)
            .map(row -> new Product(
                row.id(), row.sku(), row.stock(), row.version()
            ));
    }

    @Override
    public void save(Product product) {
        int updated = dao.updateStock(
            product.id(), product.availableStock(), product.version()
        );
        if (updated != 1) {
            throw new IllegalStateException(
                "Concurrent product update: " + product.id()
            );
        }
    }
}
~~~

**Đây là điểm chuyển đổi:** DAO hiểu `ProductRow` và câu SQL; adapter hiểu cả row lẫn domain `Product`, thực hiện mapping và kiểm tra việc ghi có thành công hay không. Nếu version người khác đã thay đổi, UPDATE với `WHERE version = ?` không cập nhật được dòng nào và adapter báo lỗi. Đó là cơ chế **optimistic concurrency control** đơn giản; trong ứng dụng thật nên dùng exception phân loại rõ và quyết định retry theo nghiệp vụ.

### 9.6. Application Service: `CheckoutService.java`

~~~java
package com.example.boundaries.service;

import com.example.boundaries.domain.Product;
import com.example.boundaries.domain.ProductRepository;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final ProductRepository products;

    public CheckoutService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void checkout(long firstId, int firstQty, long secondId, int secondQty) {
        if (firstId == secondId) {
            throw new IllegalArgumentException("Products must be distinct");
        }
        reserveAndSave(firstId, firstQty);
        reserveAndSave(secondId, secondQty);
    }

    private void reserveAndSave(long id, int quantity) {
        Product current = products.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Product: " + id));
        Product reserved = current.reserve(quantity);
        products.save(reserved);
    }
}
~~~

Ở đây, **Service không chứa SQL**, **DAO không chứa luật checkout**, còn **Product không biết transaction**. Lần lượt gọi `reserveAndSave` cho hai sản phẩm cho thấy vì sao transaction bao toàn bộ public method: nếu cập nhật sản phẩm thứ nhất đã xong nhưng đối tượng thứ hai không đủ số lượng, exception unchecked ở lần thứ hai sẽ khiến Spring rollback cả hai UPDATE. Private method là helper chạy bên trong giao dịch đã mở, không cần annotation riêng.

### 9.7. Chương trình gọi và stdout: `DaoRepositoryLessonApplication.java`

~~~java
package com.example.boundaries;

import com.example.boundaries.domain.ProductRepository;
import com.example.boundaries.service.CheckoutService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DaoRepositoryLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(DaoRepositoryLessonApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CheckoutService checkout, ProductRepository products) {
        return args -> {
            show("Before", products);
            checkout.checkout(1L, 2, 2L, 1);
            show("After success", products);

            try {
                checkout.checkout(1L, 1, 2L, 99);
            } catch (IllegalStateException ex) {
                System.out.println("Failed checkout: " + ex.getMessage());
            }

            show("After rollback", products);
        };
    }

    private static void show(String label, ProductRepository products) {
        var javaBook = products.findById(1L).orElseThrow();
        var springBook = products.findById(2L).orElseThrow();
        System.out.printf(
            "%s: JAVA-BOOK=%d, SPRING-BOOK=%d%n",
            label, javaBook.availableStock(), springBook.availableStock()
        );
    }
}
~~~

Tại thư mục có `build.gradle`, nếu đã có Gradle wrapper: chạy `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows PowerShell. Nếu đã cài Gradle tương thích mà chưa có wrapper: `gradle bootRun`. Chương trình có thể in thêm log của Spring; **các dòng do mã demo chủ động in** phải là:

~~~text
Before: JAVA-BOOK=5, SPRING-BOOK=3
After success: JAVA-BOOK=3, SPRING-BOOK=2
Failed checkout: Insufficient stock: SPRING-BOOK
After rollback: JAVA-BOOK=3, SPRING-BOOK=2
~~~

**Lần thành công:** Product A được domain đổi trạng thái 5 → 3; Repository ghi phiên bản 0 → 1. Product B đổi 3 → 2, phiên bản 0 → 1. Service kết thúc bình thường nên transaction commit.

**Lần thất bại:** Product A tạm giảm 3 → 2 (trong transaction mới), nhưng Product B yêu cầu 99 nên `Product.reserve` ném `IllegalStateException`. Spring JDBC transaction manager rollback; A vẫn bằng 3, B vẫn bằng 2 sau giao dịch. Giá trị version của A ở database cũng quay lại phiên bản đã commit trước đó. Không có câu SQL rollback viết thủ công trong Repository hay DAO.

**Giới hạn ví dụ:** Không có giỏ hàng thật, bảng đơn hàng, thanh toán, bảo mật, chính sách retry, phát sự kiện hoặc kiểm toán; `checkout` ở đây chỉ là một use case giảm tồn kho nhằm mô tả ranh giới lớp. Quy tắc “không tồn kho âm” cùng optimistic version là cần thiết nhưng chưa đủ để thiết kế hệ thống checkout production. Khi dùng database khác, cần kiểm tra transaction isolation, deadlock handling và SQL dialect trên engine thực tế.

## 10. Theo dõi một lời gọi xuyên bốn vai trò

| Bước | Class / method | Thuộc trách nhiệm nào? | Tín hiệu thực tế |
| --- | --- | --- | --- |
| 1 | `CheckoutService.checkout` | Application Service | Bắt đầu use case, Spring mở/giữ transaction |
| 2 | `ProductRepository.findById` | Repository contract | Service yêu cầu đối tượng miền, không thấy SQL |
| 3 | `JdbcProductRepository.findById` | Adapter Repository | Chuyển `ProductRow` thành `Product` |
| 4 | `JdbcProductDao.findById` | DAO | JDBC chạy `SELECT` có tham số |
| 5 | `Product.reserve` | Domain object | Đảm bảo quy tắc số lượng, tạo trạng thái hợp lệ |
| 6 | `ProductRepository.save` | Repository contract | Service yêu cầu lưu kết quả miền |
| 7 | `JdbcProductDao.updateStock` | DAO | UPDATE với `version` làm điều kiện |
| 8 | `CheckoutService` kết thúc/throw | Application Service + transaction manager | Commit cả hai sản phẩm hoặc rollback cả hai |

Để phân tích lỗi thực tế, hãy hỏi **quy tắc sai hay dữ liệu sai hay giao dịch sai?** Nếu lượng đặt âm vẫn được chấp nhận, nhìn vào domain invariant. Nếu SQL đọc sai cột, nhìn DAO/mapping. Nếu UPDATE thành công dù version đã cũ, nhìn điều kiện và xử lý kết quả lưu tại tầng persistence. Nếu sản phẩm A đã bị trừ trong khi sản phẩm B thất bại, kiểm tra Service transaction boundary và đường gọi qua proxy.

## 11. Khi dùng Spring Data JPA, ranh giới thay đổi thế nào?

Với JPA, nhiều ứng dụng không viết DAO JDBC riêng; Spring Data tạo repository implementation từ interface:

~~~java
// Ví dụ cấu trúc JPA, minh họa API chứ không phải file chạy độc lập.
public interface ProductJpaRepository
        extends org.springframework.data.jpa.repository.JpaRepository<ProductEntity, Long> {
}
~~~

`ProductEntity` ở đây phải là class entity đã được mapping `@Entity` phù hợp; snippet trên cố tình chỉ mô tả **contract Spring Data**, không phải chương trình biên dịch độc lập.

Các ranh giới có thể là:

~~~text
CheckoutService
  -> ProductRepository (cổng theo domain, nếu cần tách)
      -> JpaProductRepositoryAdapter
          -> ProductJpaRepository (Spring Data JPA)
              -> EntityManager / JPA provider
                  -> JDBC / Database
~~~

Hoặc trong ứng dụng CRUD đơn giản:

~~~text
ProductService -> ProductJpaRepository -> JPA provider -> Database
~~~

Không có DAO JDBC thủ công là chuyện bình thường; **Repository vẫn làm nhiệm vụ truy xuất/lưu dữ liệu**, còn JPA provider thực hiện SQL và mapping. Nếu entity JPA đồng thời chứa domain behavior và đáp ứng yêu cầu miền, có thể sử dụng trực tiếp. Nếu entity bị ảnh hưởng quá nhiều bởi schema, lazy loading, ORM lifecycle và cấu trúc persistence, tách `Product` miền khỏi `ProductEntity` lưu trữ.

**Điểm khác JDBC:** JPA theo dõi entity trong persistence context; dirty checking và `flush` có thể phát SQL muộn hơn thời điểm gọi setter, còn một lệnh `JdbcTemplate.update` thường gửi SQL ngay. Dù công nghệ khác nhau, Service vẫn nên quản lý transaction của use case; không nên dựa vào việc mỗi câu lệnh lưu tự hoạt động như giao dịch độc lập.

## 12. Chọn mức độ tách lớp phù hợp

Không có công thức bắt buộc “1 controller → 1 service → 1 repository → 1 DAO → 1 entity” cho mọi chức năng.

**Trường hợp A — CRUD nhỏ, quy tắc ít:** Spring Data repository trả entity JPA trực tiếp cho một Service mỏng hoặc handler đơn giản; ưu tiên mã gọn, rõ ràng. Nếu một Service chỉ gọi một repository method mà không chứa use case nào, có thể cân nhắc có cần nó không. Dù đơn giản, vẫn nên tránh đưa SQL thẳng vào Controller.

**Trường hợp B — JDBC có mapping và quy tắc rõ:** Service → Repository interface → JDBC adapter. Adapter có thể dùng JdbcTemplate trực tiếp; chỉ tách DAO khi SQL/row mapping có đời sống riêng hoặc adapter có nhiều nguồn dữ liệu.

**Trường hợp C — Nghiệp vụ phức tạp, nhiều aggregate/nguồn lưu:** Domain model giàu hành vi, repository ports theo aggregate, application services theo use case, persistence adapters phù hợp. Ưu tiên khả năng kiểm thử domain và thay đổi công nghệ lưu trữ mà ít ảnh hưởng đến lõi nghiệp vụ.

**Không phụ thuộc trực tiếp vào tên annotation:** `@Service` và `@Repository` là Spring stereotypes. Quy tắc đặt trách nhiệm do thiết kế quyết định; việc thêm annotation không tự tạo kiến trúc tách bạch.

Một quy tắc thực hành hữu ích: **định nghĩa interface Repository khi tầng nghiệp vụ cần một hợp đồng ổn định hoặc cần độc lập persistence**. Nếu chỉ có một implementation đơn giản, mọi nơi đều nằm cùng module và mức độ thay đổi thấp, việc tạo interface riêng vẫn là một trade-off; tránh abstraction chỉ để phòng một nhu cầu chưa có.

## 13. Quy tắc miền, giao dịch và cạnh tranh đồng thời

Phân vai rõ ràng giúp phát hiện **hai loại tính đúng**:

1. **Đúng ở mức đối tượng:** `Product.reserve` không tạo trạng thái âm. Có thể kiểm thử trực tiếp bằng Java đơn giản, không cần Spring context.
2. **Đúng ở mức nhiều thao tác/database:** hai lần lưu thuộc một transaction, và các yêu cầu đồng thời không ghi đè lẫn nhau. Đây là việc phối hợp Service, Repository adapter, điều kiện SQL và DBMS.

Trong ví dụ, `WHERE id = ? AND version = ?` giúp phát hiện một bản ghi đã thay đổi kể từ lúc Service đọc nó. Nếu version không khớp, UPDATE trả 0; Repository báo lỗi; transaction thất bại. Đây là **optimistic locking thủ công**. JPA có thể hỗ trợ cùng ý tưởng qua `@Version`, nhưng phải hiểu thời điểm flush và exception tương ứng. Với mức cạnh tranh rất cao, có thể cân nhắc locking trong database hoặc thao tác UPDATE có điều kiện theo nghiệp vụ.

**Không đặt việc giữ kết nối và transaction vào domain object:** Domain object không nên gọi `entityManager.flush()`, `jdbc.update()` hay `connection.commit()`. Nếu có ngoại lệ domain, Service quyết định cách use case phản hồi; transaction manager phối hợp rollback. Trong JDBC một DataSource, việc tự gọi `dataSource.getConnection()` rồi commit thủ công ở DAO có thể làm mất ranh giới transaction đang do Spring quản lý. Sử dụng JdbcTemplate hoặc API giao dịch tương thích với Spring.

Nếu use case gọi một API thanh toán ngoài database, transaction cơ sở dữ liệu **không bao phủ tự động** thao tác thanh toán bên ngoài. Các workflow đa hệ thống cần thiết kế riêng (idempotency, outbox, saga/compensation phù hợp). Đây là trách nhiệm điều phối của application layer chứ không thể giải quyết chỉ bằng thêm `@Transactional` cho một DAO.

## 14. Đặt kiểm thử tại đúng ranh giới

| Bài kiểm thử | Thành phần chính | Bằng chứng mong đợi |
| --- | --- | --- |
| Đặt 0 cuốn, -1 cuốn, quá tồn kho | `Product.reserve` | Ném lỗi đúng quy tắc, không tạo Product bất hợp lệ |
| Đọc hàng thiếu, SQL mapping, update theo version | `JdbcProductDao` | `Optional.empty()` đúng; update rows = 1 hoặc 0 theo điều kiện |
| Mapping từ row sang domain và truyền expectedVersion | `JdbcProductRepository` | Product đúng field, xung đột lưu phát sinh lỗi |
| Checkout hai sản phẩm với kho đủ | `CheckoutService` | Gọi đúng hai lần lưu, thứ tự hợp lý, hoàn tất use case |
| Sản phẩm thứ hai không đủ và sản phẩm đầu đã cập nhật | Spring integration test có transaction thực | Database không giữ lại UPDATE thứ nhất sau rollback |
| Hai request cùng cập nhật một version | Integration test chạy cạnh tranh | Không có silent lost update; lỗi/retry đúng chính sách |

**Phân biệt test mock và test transaction:** Một unit test dùng mock `ProductRepository` có thể kiểm tra Service điều phối, nhưng không thể chứng minh rollback trong database hay Spring proxy đã hoạt động. Hãy dùng integration test qua bean Spring thật với DataSource thực tế hoặc môi trường phù hợp để kiểm tra atomicity, SQL, constraints và locking. Với DAO JDBC, `@JdbcTest` có thể cung cấp một lát cắt kiểm thử JDBC; với JPA, `@DataJpaTest` phục vụ persistence JPA. Kiểm tra transaction nên tránh trường hợp chính transaction của bài test che giấu commit/rollback của use case.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao dễ sai | Cách định hướng |
| --- | --- | --- |
| “DAO và Repository luôn là hai tầng bắt buộc” | Cả hai đôi khi cùng giải quyết một truy vấn CRUD | Chỉ tách khi có trách nhiệm và giá trị phân tách rõ |
| “Repository đồng nghĩa Spring Data `JpaRepository`” | Một bên là pattern miền, một bên là API framework | Hiểu contract theo miền và implementation dùng ORM là hai mức khác nhau |
| “Service chứa toàn bộ mọi quy tắc” | Domain object trở thành chỉ có dữ liệu, khó giữ invariant | Đưa hành vi gắn chặt trạng thái vào domain; Service điều phối |
| “JPA entity luôn là domain entity tốt” | Mapping/lazy loading/schema có thể làm méo mô hình | Dùng chung khi phù hợp, tách khi coupling gây vấn đề |
| “Một bảng phải có một Repository” | Repository DDD thường theo aggregate, không theo bảng | Xác định ranh giới nhất quán nghiệp vụ |
| “Có `@Transactional` là hai cập nhật chắc chắn cùng transaction” | Self-invocation, transaction manager khác, thao tác tự mở Connection | Xác minh proxy, transaction manager và tài nguyên được enlist |
| “Có domain validation rồi không cần DB constraint” | Nhiều tiến trình và race condition vẫn có thể vi phạm | Domain rule + constraint/locking/version ở DB |
| “DTO, row và domain object là một” | Tên trường/ý nghĩa/chu kỳ đời sống khác nhau | Mapping rõ ở ranh giới API/persistence khi cần |
| “Repository trả mọi lỗi thành `null` hoặc `false`” | Không phân biệt not-found, xung đột, timeout và lỗi SQL | Dùng `Optional` cho thiếu dữ liệu; exception phù hợp cho lỗi kỹ thuật/vi phạm |
| “Chỉ cần unit test Service mock là đủ” | Không xác minh SQL, commit/rollback, pool, DB constraints | Bổ sung integration tests ở các đường rủi ro |

Một lưu ý về **exception translation**: Spring JDBC dùng `DataAccessException` (unchecked) cho nhiều lỗi truy cập dữ liệu. Trong JPA, `@Repository` với hạ tầng Spring phù hợp có thể tham gia cơ chế dịch ngoại lệ persistence. Service có thể chọn chuyển lỗi đó thành kết quả ứng dụng cụ thể, nhưng không nên biến mọi lỗi hạ tầng thành “không tìm thấy” hay retry vô điều kiện.

## 16. Tự kiểm tra và bài tập thiết kế

**Câu 1.** Quy tắc “số lượng đặt phải dương và không vượt tồn kho hiện tại” thuộc lớp nào?  
**Đáp án:** Hành vi của Product/domain object phù hợp vì quy tắc phụ thuộc trực tiếp trạng thái sản phẩm. Database constraint/concurrency vẫn cần bảo vệ dữ liệu khi nhiều transaction cùng chạy.

**Câu 2.** Câu `SELECT id, sku ... FROM product WHERE id = ?` nên nằm ở đâu?  
**Đáp án:** DAO hoặc persistence adapter của Repository, không trong Product hay Application Service.

**Câu 3.** Giao diện `Optional<Product> findById(long id)` có thể được Service sử dụng mà không biết backend gì không?  
**Đáp án:** Có. Đây là ưu điểm của Repository contract theo miền; adapter thực hiện chi tiết lưu trữ.

**Câu 4.** Checkout hai sản phẩm, UPDATE A thành công nhưng B lỗi. Ai chịu trách nhiệm bảo đảm một đơn vị giao dịch?  
**Đáp án:** Application Service xác định transaction boundary cho cả use case; Spring transaction manager và DBMS thực thi commit/rollback, các DAO tham gia đúng transaction.

**Câu 5.** Nếu ứng dụng chỉ có CRUD 1 bảng, tạo interface Repository, implementation, DAO và mapper riêng có luôn tốt hơn một `JdbcTemplate`-based Repository không?  
**Đáp án:** Không. Thiết kế nên phản ánh mức độ phức tạp và ranh giới thay đổi thực tế, tránh thêm tầng chuyển tiếp không mang trách nhiệm riêng.

**Bài tập:** Thêm nghiệp vụ `returnStock(productId, quantity)`. Đặt quy tắc `quantity > 0` và tạo trạng thái sau khi trả hàng ở Product; thêm thao tác lưu theo version ở Repository/DAO; Service làm nhiệm vụ tải Product, gọi hành vi, lưu trong transaction. Sau đó lập integration test: hai lệnh cùng version chỉ một lần cập nhật có thể thành công; lệnh còn lại phải nhận tín hiệu conflict rõ ràng. Cẩn thận tránh integer overflow khi cộng tồn kho số lượng lớn.

## 17. Ghi nhớ thiết kế

- **Domain object** giữ ý nghĩa, trạng thái hợp lệ và hành vi nghiệp vụ; không cần biết SQL/JDBC.
- **DAO** nói ngôn ngữ hạ tầng lưu trữ: query, row mapping, số hàng cập nhật.
- **Repository** cho Service một cổng truy xuất/lưu domain object; adapter có thể dùng DAO, JDBC trực tiếp hoặc Spring Data JPA.
- **Application Service** tổ chức use case, phối hợp domain/repository và xác định ranh giới giao dịch.
- **Tách lớp có mục đích:** dùng ít lớp hơn khi trách nhiệm thực sự đơn giản, nhưng giữ ranh giới rõ ở nơi thay đổi, bất biến và consistency quan trọng.

Khi gặp một method mới, hãy hỏi: “Đây là **luật của đối tượng**, **chi tiết truy vấn**, **hợp đồng truy xuất**, hay **một bước điều phối use case**?” Câu trả lời đó chỉ ra vị trí đặt mã tốt hơn nhiều so với việc nhìn vào hậu tố tên file.
