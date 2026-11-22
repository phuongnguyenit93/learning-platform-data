# Named query và tệp META-INF/jdbc-named-queries.properties

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, một repository method có thể lấy dữ liệu bằng query được suy diễn từ tên phương thức, bằng SQL khai báo trực tiếp qua `@Query`, hoặc bằng **named query** được đặt trong tệp tài nguyên trên classpath. Named query cho phép tách câu SQL khỏi interface repository và đặt câu lệnh ở một nơi có tên định danh rõ ràng.

Với Spring Data JDBC, tệp named query mặc định có tên chính xác:

`META-INF/jdbc-named-queries.properties`

Mỗi query được khai báo bằng một key kết hợp **tên domain type** và **tên repository method**. Khi repository gọi method tương ứng, Spring Data tìm named query theo key đó và thực thi SQL với tham số được bind.

## 1. Khi nào nên dùng named query?

Giả sử ứng dụng có entity `Customer` và cần tìm khách theo họ. Truy vấn đơn giản có thể suy diễn từ method:

~~~java
List<Customer> findByLastName(String lastName);
~~~

Khi câu SQL phức tạp hơn, ví dụ cần join, CTE, hàm đặc thù của database hoặc logic báo cáo, bạn có thể muốn viết SQL rõ ràng. Có ba lựa chọn thường gặp:

| Cách khai báo | SQL nằm ở đâu? | Phù hợp khi |
|---|---|---|
| Derived query | Tên method repository | Truy vấn đơn giản theo property |
| `@Query` | Ngay trên method repository | SQL ngắn, gắn chặt với method |
| Named query | `META-INF/jdbc-named-queries.properties` | Muốn tách SQL khỏi interface hoặc quản lý câu lệnh có tên riêng |

Named query hữu ích khi SQL dài, cần đọc độc lập với Java code, hoặc có nhiều câu truy vấn cần được quản lý tập trung. Nó vẫn là SQL cụ thể cho schema/database, không phải một ngôn ngữ query trừu tượng.

## 2. Cấu trúc và vị trí của tệp

Trong ứng dụng Gradle hoặc Maven tiêu chuẩn, đặt resource tại:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/customer/
    │       ├── Customer.java
    │       └── CustomerRepository.java
    └── resources/
        └── META-INF/
            └── jdbc-named-queries.properties
~~~

Đường dẫn trong source là `src/main/resources/META-INF/jdbc-named-queries.properties`. Khi build, file được copy vào classpath của ứng dụng; Spring Data JDBC tìm resource theo tên mặc định `META-INF/jdbc-named-queries.properties`.

Không đặt file trong package Java như `src/main/java/com/example/...`, và không đổi tên tùy ý thành `named-queries.properties` nếu chưa cấu hình cơ chế lookup khác. Tên và vị trí resource là một phần của convention.

Với ứng dụng nhiều module, file phải nằm trong resources của module được đóng gói vào runtime classpath nơi repository hoạt động. Một file nằm trong module khác nhưng không được đưa vào runtime classpath sẽ không được tìm thấy.

## 3. Quy tắc đặt tên query

Key của named query được tạo từ **tên domain class** và **tên method repository**, nối bằng dấu chấm:

~~~text
<DomainType>.<repositoryMethodName>
~~~

Ví dụ:

| Domain type | Repository method | Key trong properties |
|---|---|---|
| `Customer` | `findByLastName` | `Customer.findByLastName` |
| `Order` | `findRecentOrders` | `Order.findRecentOrders` |
| `Product` | `countAvailableProducts` | `Product.countAvailableProducts` |

Tên method phải khớp chính xác với method khai báo trong repository, bao gồm chữ hoa/chữ thường. Tên domain type là tên lớp domain mà repository quản lý; không dùng tên bảng SQL thay thế cho tên lớp.

Ví dụ, nếu domain class là `CustomerProfile` và method là `findActiveProfiles`, key sẽ là `CustomerProfile.findActiveProfiles`, dù bảng có tên `customer_profiles`.

## 4. Ví dụ đầy đủ: tìm Customer theo họ

### Domain entity

~~~java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    @Column("last_name")
    private String lastName;

    protected Customer() {
        // Dành cho Spring Data JDBC.
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
~~~

### Repository method

~~~java
package com.example.customer;

import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByLastName(
        @Param("lastName") String lastName
    );
}
~~~

Method không có `@Query`. Spring Data JDBC có thể tìm named query theo key `Customer.findByLastName`.

### Tệp jdbc-named-queries.properties

~~~properties
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName ORDER BY id
~~~

Khi gọi:

~~~java
List<Customer> customers =
    customerRepository.findByLastName("Nguyễn");
~~~

Spring Data JDBC tìm câu SQL trong resource, bind giá trị `lastName` vào tham số `:lastName`, thực thi và ánh xạ các hàng kết quả thành danh sách `Customer`.

## 5. Named parameter và an toàn tham số

Named query dùng named parameter theo cú pháp `:parameterName`:

~~~properties
Customer.findByName=SELECT id, first_name, last_name FROM customers WHERE first_name = :firstName AND last_name = :lastName
~~~

Repository:

~~~java
List<Customer> findByName(
    @Param("firstName") String firstName,
    @Param("lastName") String lastName
);
~~~

Tên sau dấu hai chấm phải khớp tên tham số được Spring Data nhận diện. Dùng `@Param` tường minh giúp tránh phụ thuộc vào việc compiler có lưu tên tham số Java hay không.

**Không nối giá trị đầu vào vào SQL.** Hãy viết `WHERE last_name = :lastName` và để Spring Data/JDBC bind tham số. Cách này tách dữ liệu khỏi cú pháp SQL, xử lý escaping đúng và tránh SQL injection từ giá trị người dùng.

Không dùng kiểu:

~~~java
String sql = "SELECT * FROM customers WHERE last_name = '" + lastName + "'";
~~~

Named query không tự động biến tên cột hoặc tên bảng thành tham số. Các identifier như bảng, cột và hướng sắp xếp phải được xác định trong SQL. Nếu cần lựa chọn sort động, dùng API sorting/query phù hợp hoặc xây dựng câu SQL có kiểm soát từ whitelist; không bind identifier như bind một giá trị.

## 6. Định dạng properties và SQL nhiều dòng

`jdbc-named-queries.properties` là Java properties file, không phải YAML hoặc SQL script. Mỗi entry có dạng:

~~~properties
query.key=SQL statement
~~~

Các dòng bắt đầu bằng `#` hoặc `!` có thể dùng làm comment:

~~~properties
# Queries for CustomerRepository
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName
~~~

Với SQL dài, có thể dùng dấu gạch chéo ngược `\` ở cuối dòng để nối dòng theo quy tắc Java properties:

~~~properties
Customer.searchDirectory=SELECT id, first_name, last_name \
    FROM customers \
    WHERE last_name = :lastName \
    ORDER BY last_name, first_name, id
~~~

Dấu `\` cuối dòng báo rằng giá trị properties tiếp tục ở dòng kế tiếp. Khoảng trắng đầu dòng nối tiếp được xử lý theo quy tắc properties; hãy kiểm tra SQL sau khi nối nếu định dạng có khoảng trắng mang ý nghĩa.

Nếu SQL chứa ký tự đặc biệt của properties như dấu gạch chéo ngược ở cuối hoặc các ký tự escape, cần tuân thủ quy tắc escape của Java properties. Cách đơn giản là giữ SQL trên một dòng hoặc dùng continuation rõ ràng.

## 7. Named query có thể dùng cho truy vấn phức tạp

Ví dụ cần tìm Customer có ít nhất một Order đã xác nhận. SQL có thể dùng `EXISTS`:

~~~properties
Customer.findCustomersWithConfirmedOrders=SELECT c.id, c.first_name, c.last_name FROM customers c WHERE EXISTS (SELECT 1 FROM sales_orders o WHERE o.customer_id = c.id AND o.status = :status) ORDER BY c.id
~~~

Repository:

~~~java
List<Customer> findCustomersWithConfirmedOrders(
    @Param("status") String status
);
~~~

Gọi:

~~~java
List<Customer> customers =
    customerRepository.findCustomersWithConfirmedOrders("CONFIRMED");
~~~

Named query này trả về Customer root, không phải danh sách Order. Nó chỉ dùng bảng `sales_orders` trong điều kiện lọc. Customer vẫn là aggregate riêng và Order vẫn là aggregate riêng.

Một ví dụ khác là truy vấn thống kê có kết quả scalar:

~~~properties
Customer.countCustomersWithOrders=SELECT COUNT(DISTINCT c.id) FROM customers c JOIN sales_orders o ON o.customer_id = c.id
~~~

Repository có thể khai báo:

~~~java
long countCustomersWithOrders();
~~~

Kiểu trả về phải tương thích với giá trị mà query trả về. Với truy vấn scalar, không khai báo method trả về `Customer` vì kết quả không chứa các cột để ánh xạ thành entity.

## 8. Named query và @Query: chọn một nơi khai báo

Nếu SQL được đặt trực tiếp trên repository:

~~~java
@Query("""
    SELECT id, first_name, last_name
    FROM customers
    WHERE last_name = :lastName
    ORDER BY id
    """)
List<Customer> findByLastName(
    @Param("lastName") String lastName
);
~~~

Đây là cách dùng `@Query` thay cho named query. Khi một method có câu query khai báo trực tiếp bằng annotation, câu query đó được dùng cho method; named query cùng key không phải nguồn cần chỉnh sửa cho method đó.

Nên chọn:

- **Derived query** khi tên method diễn đạt được điều kiện đơn giản.
- **`@Query`** khi SQL ngắn và reviewer cần thấy ngay cạnh method.
- **Named query** khi SQL dài, cần tách khỏi Java interface, hoặc muốn quản lý SQL trong resource riêng.

Không duy trì cùng một SQL ở cả `@Query` và properties với kỳ vọng hai bản tự đồng bộ. Chọn một nguồn khai báo cho mỗi method để tránh sửa nhầm nơi.

## 9. Named query, derived query và quy trình tìm câu lệnh

Khi repository method không có `@Query`, Spring Data có thể tìm một named query theo quy ước tên. Nếu không có named query phù hợp, framework có thể tạo query từ tên method theo cơ chế query lookup strategy mặc định.

Ví dụ:

~~~java
List<Customer> findByLastName(String lastName);
~~~

Có thể hoạt động bằng derived query nếu không có entry named query. Khi thêm entry:

~~~properties
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName
~~~

method đó sẽ sử dụng SQL được khai báo. Điều này cho phép thay đổi từ derived query sang SQL tường minh mà không phải đổi tên method gọi từ service.

Nếu muốn dùng SQL tường minh và không dựa vào convention, `@Query` là lựa chọn rõ ràng. Khi debug, hãy kiểm tra method name, tên domain type, key properties và classpath resource trước khi kết luận repository không tìm thấy SQL.

## 10. Kết quả SQL phải phù hợp với kiểu trả về

Named query không tự chuyển mọi result set thành bất kỳ kiểu Java nào. SQL phải trả về cột và kiểu dữ liệu phù hợp với kết quả method:

| Kiểu trả về | Dạng kết quả SQL |
|---|---|
| `Customer` | Một hàng có các cột ánh xạ Customer |
| `Optional<Customer>` | Không hoặc một hàng Customer |
| `List<Customer>` | Nhiều hàng Customer |
| `long` | Một giá trị số, thường là COUNT |
| `boolean` | Một giá trị boolean tương thích với driver/mapping |
| Projection/DTO | Các cột/alias tương ứng với thuộc tính projection |

Đối với entity, truy vấn nên trả về khóa chính và các cột được mapping cần thiết. Nếu entity có `@Column("first_name")`, tên cột SQL phải được nhận diện đúng theo mapping. Dùng alias khi query biểu thức hoặc tên cột khác với property.

### Truy vấn join không tự biến aggregate khác thành object con

SQL có thể join nhiều bảng để lọc hoặc lấy projection, nhưng việc join trong câu SQL không tự thay đổi ranh giới aggregate. Nếu repository method trả về `Customer`, hãy bảo đảm result set phù hợp mapping Customer. Nếu cần một DTO gồm Customer và dữ liệu Order, hãy khai báo projection/DTO riêng và alias cột rõ ràng.

Đối với aggregate có collection con, không giả định rằng một query tùy chỉnh join bảng con sẽ tự động dựng toàn bộ object graph giống `findById`. Cần thiết kế kết quả theo hợp đồng của query và kiểm tra mapping theo phiên bản Spring Data JDBC đang dùng; khi cần tải aggregate theo cơ chế mapping tiêu chuẩn, dùng thao tác repository phù hợp.

## 11. Named query cho từng dialect database

Một properties file có thể chứa nhiều câu lệnh, nhưng câu SQL vẫn phải tương thích với database đang chạy. Nếu cùng một ứng dụng hỗ trợ PostgreSQL và MySQL, tránh giả định một câu query phức tạp sẽ chạy giống nhau trên cả hai.

Khác biệt có thể xuất hiện ở:

- Hàm xử lý chuỗi, ngày giờ và JSON.
- Cú pháp phân trang, CTE hoặc biểu thức đặc thù.
- Cách cast kiểu dữ liệu.
- Tên hàm và cú pháp generated column.
- Kiểu dữ liệu trả về của hàm aggregate.

Nếu SQL dùng cú pháp chung, một named query có thể phục vụ cả hai. Nếu cần SQL riêng theo dialect, hãy tổ chức tài nguyên/cấu hình theo chiến lược rõ ràng của ứng dụng, hoặc dùng custom repository/implementation để chọn câu lệnh phù hợp. Không đặt hai entry cùng key trong một properties file và mong framework tự chọn theo database.

## 12. Tổ chức nhiều named query

Một file có thể quản lý query của nhiều domain type:

~~~properties
# Customer
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName
Customer.findByName=SELECT id, first_name, last_name FROM customers WHERE first_name = :firstName AND last_name = :lastName

# Order
Order.findRecentOrders=SELECT id, customer_id, status, created_at FROM sales_orders WHERE created_at >= :since ORDER BY created_at DESC
Order.countByCustomer=SELECT COUNT(*) FROM sales_orders WHERE customer_id = :customerId

# Product
Product.findBySku=SELECT id, sku, unit_price, stock_quantity FROM products WHERE sku = :sku
~~~

Quy ước hữu ích:

- Nhóm entry theo domain type và thêm comment để người đọc dễ tìm.
- Mỗi key chỉ xuất hiện một lần trong resource cuối cùng.
- Dùng tên method đúng với repository.
- Dùng named parameter có tên dễ hiểu, khớp với `@Param`.
- Chọn thứ tự cột/alias nhất quán với entity hoặc projection.
- Không lưu mật khẩu, token hoặc dữ liệu bí mật trong SQL properties.

Khi số lượng query lớn, có thể phân tách theo module hoặc custom query infrastructure nếu ứng dụng có cơ chế hỗ trợ; tuy nhiên, resource mặc định mà Spring Data JDBC tìm là `META-INF/jdbc-named-queries.properties`.

## 13. Kiểm tra named query đã được nạp

Khi method không chạy đúng SQL mong muốn, hãy xác định theo từng lớp:

1. **Resource path:** file có nằm trong `src/main/resources/META-INF/` không?
2. **Classpath:** file có được đóng gói trong output resources/JAR của module runtime không?
3. **Key:** key có đúng dạng `DomainType.methodName` không?
4. **Method:** repository có khai báo method đúng tên và đúng tham số không?
5. **Parameter:** tên `:parameterName` có khớp `@Param("parameterName")` không?
6. **SQL:** tên bảng/cột, kiểu tham số và cú pháp có đúng dialect không?
7. **Result mapping:** query trả về đủ cột và kiểu tương thích với method return type không?

Có thể kiểm tra resource đã được copy sau build bằng cách xem nội dung trong output resources của module hoặc liệt kê nội dung JAR. Ví dụ Gradle:

~~~powershell
Get-Content .\build\resources\main\META-INF\jdbc-named-queries.properties
~~~

Đường dẫn ví dụ giả định đang đứng tại module chứa ứng dụng và đã chạy task build/resources phù hợp. Nếu dự án dùng source set hoặc module layout khác, kiểm tra output classpath tương ứng.

Để quan sát SQL và bind parameter trong môi trường phát triển, bật logging phù hợp cho Spring JDBC và Spring Data Relational theo phiên bản đang dùng. Không bật log giá trị nhạy cảm ở production.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Named query không được tìm thấy | Sai tên file hoặc đặt sai thư mục | Dùng `META-INF/jdbc-named-queries.properties` trên classpath |
| Query không được sử dụng dù file tồn tại | Key không khớp domain type hoặc method name | Kiểm tra `<DomainType>.<methodName>` chính xác |
| Method chạy derived query thay vì SQL trong file | Không có entry đúng key hoặc resource chưa được đóng gói | Kiểm tra key và output resources/JAR |
| Lỗi thiếu tham số | `:name` không khớp tên tham số | Dùng `@Param("name")` rõ ràng |
| SQL injection hoặc lỗi dấu nháy | Nối chuỗi đầu vào vào SQL | Dùng named parameter và bind giá trị |
| Lỗi cột không tồn tại | SQL dùng tên bảng/cột khác schema | Đối chiếu DDL và mapping `@Column` |
| Lỗi ánh xạ kết quả | Query thiếu ID/cột cần thiết hoặc alias không phù hợp | Trả về cột tương thích entity/projection |
| Query chạy ở PostgreSQL nhưng lỗi MySQL | Dùng cú pháp/hàm riêng dialect | Viết SQL tương thích hoặc tách chiến lược theo dialect |
| Properties bị tách sai dòng | Dùng continuation/escape không đúng | Kiểm tra quy tắc Java properties và chuỗi SQL sau khi nối |
| Sửa SQL nhưng ứng dụng vẫn dùng bản cũ | Resource trong build output/JAR chưa được cập nhật | Rebuild/restart đúng artifact đang chạy |

## 15. Bài thực hành

1. Tạo entity `Customer` ánh xạ bảng `customers` và repository có method `findByLastName`.
2. Tạo `src/main/resources/META-INF/jdbc-named-queries.properties` với key `Customer.findByLastName`.
3. Viết SQL có named parameter `:lastName` và khai báo method parameter bằng `@Param("lastName")`.
4. Gọi method với họ có dấu tiếng Việt; xác minh kết quả đúng.
5. Thêm named query `Customer.findCustomersWithConfirmedOrders` dùng `EXISTS` để lọc khách có đơn CONFIRMED.
6. Thêm query đếm Customer có Order và khai báo method trả về `long`.
7. Tạm đổi key thành `Customer.findByLastNames` (sai tên) để quan sát framework không dùng entry đó; khôi phục key đúng sau thử nghiệm.
8. Đưa cùng SQL vào `@Query` trên method và quan sát annotation khai báo trực tiếp được dùng; sau đó bỏ annotation để method dùng named query.
9. Thử truyền đầu vào chứa dấu nháy đơn và xác minh bind parameter vẫn coi đó là dữ liệu, không phải một phần cú pháp SQL.
10. Kiểm tra file properties được đóng gói vào output/JAR và ứng dụng vẫn tìm thấy sau khi chạy từ artifact đã build.

## 16. Ghi nhớ

Named query của Spring Data JDBC được khai báo trong resource `META-INF/jdbc-named-queries.properties`. Mỗi entry dùng key `DomainType.methodName` và value là SQL; repository method tương ứng cung cấp tham số để framework bind vào các placeholder như `:lastName`.

Named query giúp tách SQL khỏi Java interface, nhưng vẫn cần quản lý chặt tên key, resource classpath, dialect, kiểu trả về và mapping cột. Dùng derived query cho điều kiện đơn giản, `@Query` cho SQL ngắn gắn với method, và named query khi muốn quản lý SQL trong resource riêng. Luôn bind giá trị thay vì nối chuỗi đầu vào, đồng thời kiểm tra result set đúng với entity hoặc projection mà repository method khai báo.
