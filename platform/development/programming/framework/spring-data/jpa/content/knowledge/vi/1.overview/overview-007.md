# Kiến thức Java, SQL và Spring cần có trước khi bắt đầu

Bài học này giúp bạn xác định những nền tảng cần có trước khi học Spring Data JPA. Spring Data JPA giúp thao tác với dữ liệu quan hệ thuận tiện hơn, nhưng để hiểu được repository, entity, truy vấn và transaction, bạn cần nắm được ba lớp kiến thức: Java để mô hình hóa dữ liệu và viết ứng dụng, SQL để hiểu cơ sở dữ liệu quan hệ, và Spring để hiểu cách các thành phần của ứng dụng được tạo và phối hợp.

Bạn không cần thành thạo mọi tính năng nâng cao trước khi bắt đầu. Hãy nắm chắc các khái niệm cốt lõi, biết đọc ví dụ và có thể tự viết một chương trình nhỏ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Java, SQL, Spring, JPA, Hibernate và Spring Data JPA trong một ứng dụng.
- Đọc và viết được lớp Java biểu diễn dữ liệu, sử dụng interface, generics, collections, exception và các tính năng Java hiện đại ở mức cơ bản.
- Thiết kế bảng đơn giản, khai báo khóa chính và khóa ngoại, viết truy vấn có JOIN, lọc, sắp xếp và tổng hợp.
- Hiểu IoC, Dependency Injection, bean, cấu hình Spring Boot và ranh giới transaction.
- Nhận biết những vấn đề mà JPA giải quyết, đồng thời hiểu vì sao vẫn cần kiến thức SQL và transaction.

## 2. Bức tranh tổng thể: dữ liệu đi qua những lớp nào?

Trong ứng dụng Spring Data JPA, luồng xử lý thường có dạng:

~~~text
Controller
    ↓
Service
    ↓
Spring Data Repository
    ↓
JPA EntityManager
    ↓
JPA Provider (thường là Hibernate)
    ↓
JDBC Driver
    ↓
Cơ sở dữ liệu quan hệ
~~~

Mỗi thành phần có trách nhiệm riêng:

- **Java** là ngôn ngữ dùng để viết logic nghiệp vụ và mô hình hóa dữ liệu.
- **Spring Framework** quản lý đối tượng, dependency, cấu hình và các dịch vụ dùng chung như transaction.
- **JPA** là đặc tả Java quy định cách ánh xạ đối tượng Java với dữ liệu quan hệ và cách quản lý vòng đời entity.
- **Hibernate** là một JPA provider phổ biến, hiện thực đặc tả JPA và chuyển thao tác trên entity thành SQL.
- **Spring Data JPA** cung cấp lớp repository, giúp giảm mã truy cập dữ liệu và hỗ trợ tạo truy vấn từ tên phương thức hoặc khai báo truy vấn.
- **JDBC** là API nền tảng để Java giao tiếp với cơ sở dữ liệu thông qua driver.
- **Cơ sở dữ liệu** lưu trữ dữ liệu thực tế, thực thi SQL, ràng buộc và transaction.

Vì vậy, Spring Data JPA không phải là cơ sở dữ liệu và cũng không thay thế SQL. Khi một truy vấn chậm hoặc trả về dữ liệu sai, bạn vẫn cần hiểu câu SQL được thực thi, cấu trúc bảng và cách cơ sở dữ liệu xử lý truy vấn.

## 3. Nền tảng Java cần nắm

### 3.1. Kiểu dữ liệu, biến và giá trị null

Bạn cần phân biệt kiểu nguyên thủy và kiểu tham chiếu:

- Kiểu nguyên thủy như **int**, **long**, **boolean** lưu giá trị trực tiếp và không thể nhận **null**.
- Kiểu bao như **Integer**, **Long**, **Boolean** là object và có thể nhận **null**.
- **String** là kiểu tham chiếu bất biến.
- **BigDecimal** phù hợp với phép tính tiền tệ hoặc số thập phân cần độ chính xác; không nên dùng **double** cho số tiền vì sai số biểu diễn nhị phân.

Sự khác biệt giữa **long** và **Long** đặc biệt quan trọng khi ánh xạ dữ liệu. Một cột có thể chưa có giá trị hoặc một entity mới có thể chưa được cấp ID, vì vậy kiểu bao thường phù hợp hơn cho thuộc tính có khả năng null.

### 3.2. Lớp, object và lập trình hướng đối tượng

Bạn cần hiểu:

- **Class** mô tả cấu trúc và hành vi; **object** là một thể hiện cụ thể của class.
- **Constructor** khởi tạo object.
- **Encapsulation** bảo vệ trạng thái bên trong thông qua phạm vi truy cập và phương thức.
- **Interface** mô tả hợp đồng; class có thể triển khai một hoặc nhiều interface.
- **Inheritance** thể hiện quan hệ kế thừa; **composition** ghép các object để tạo hành vi. Trong thiết kế nghiệp vụ, composition thường giúp giảm phụ thuộc cứng.
- **Access modifier** như public, protected, private và phạm vi package quyết định nơi có thể truy cập thành phần.

Khi làm việc với JPA, bạn sẽ gặp các class biểu diễn entity, các interface repository và các service. Nếu chưa hiểu class, object, constructor và interface, việc đọc những thành phần này sẽ rất khó.

### 3.3. Collections và quy tắc equals/hashCode

Nắm được mục đích của các collection phổ biến:

- **List** giữ thứ tự và cho phép phần tử trùng lặp.
- **Set** biểu diễn tập hợp không chứa phần tử trùng nhau theo quy tắc equality.
- **Map** lưu cặp khóa và giá trị; khóa phải có quy tắc equality và hash ổn định khi được dùng trong map.

Bạn cần biết khi nào dùng từng loại và hiểu hợp đồng của **equals()** và **hashCode()**. Hai object được xem là bằng nhau theo equals thì phải có cùng hashCode. Quy tắc này ảnh hưởng đến Set, Map và cả cách quản lý quan hệ giữa các entity.

Với entity JPA, việc viết equals/hashCode cần cẩn thận vì ID có thể chưa tồn tại khi object mới được tạo. Không nên sao chép máy móc một cách triển khai equality từ DTO hoặc class thông thường sang entity.

### 3.4. Generics và interface

Generics cho phép tái sử dụng kiểu dữ liệu mà vẫn giữ kiểm tra kiểu lúc biên dịch. Ví dụ, **List<Customer>** cho biết danh sách chứa Customer; **JpaRepository<Customer, Long>** cho biết repository quản lý entity Customer có kiểu ID là Long.

Bạn nên đọc được khai báo interface, kiểu tham số, kiểu trả về và generic type. Đây là nền tảng để hiểu repository của Spring Data JPA.

### 3.5. Exception và xử lý lỗi

Phân biệt:

- **Checked exception** phải được khai báo hoặc xử lý theo quy tắc của Java.
- **Unchecked exception** kế thừa RuntimeException và không bắt buộc khai báo trong chữ ký phương thức.
- **try/catch/finally** dùng để xử lý lỗi tại nơi có đủ ngữ cảnh.
- Không nên bắt mọi exception rồi bỏ qua; lỗi cần được xử lý, chuyển đổi hoặc truyền tiếp một cách có chủ đích.

Trong ứng dụng dữ liệu, lỗi có thể phát sinh do dữ liệu vi phạm constraint, kết nối thất bại, truy vấn sai hoặc transaction bị rollback. Hiểu exception giúp bạn xác định lỗi xảy ra ở tầng nào.

### 3.6. Annotation, reflection và lambda

Framework Java sử dụng annotation làm metadata. Ví dụ, **@Service**, **@Repository**, **@Transactional** và các annotation JPA mô tả vai trò hoặc hành vi của class, method và field. Bạn không cần tự viết reflection ngay từ đầu, nhưng nên hiểu annotation là metadata và framework có thể đọc metadata đó lúc chạy.

Ngoài ra, nên biết cú pháp lambda, functional interface, Stream API và Optional:

- Lambda truyền hành vi dưới dạng biểu thức.
- Stream hỗ trợ biến đổi và tổng hợp dữ liệu trong bộ nhớ.
- Optional biểu diễn kết quả có thể không tồn tại và thường xuất hiện trong API repository.

Stream xử lý collection đã có trong bộ nhớ; nó không tự động trở thành truy vấn SQL. Khi dữ liệu lớn, lọc và phân trang ở cơ sở dữ liệu thường hiệu quả hơn việc tải toàn bộ dữ liệu về rồi lọc bằng Stream.

Ví dụ Java 17+ dưới đây minh họa collection, Stream, Optional và BigDecimal:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

public class JavaPrerequisiteDemo {
    record Customer(Long id, String name) {}

    public static void main(String[] args) {
        List<Customer> customers = List.of(
            new Customer(1L, "An"),
            new Customer(2L, "Binh")
        );

        Optional<Customer> result = customers.stream()
            .filter(customer -> customer.name().equals("An"))
            .findFirst();

        BigDecimal total = List.of(
            new BigDecimal("12.50"),
            new BigDecimal("3.25")
        ).stream().reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println(result.map(Customer::name).orElse("Khong tim thay"));
        System.out.println(total);
    }
}
~~~

Lưu đoạn mã thành **JavaPrerequisiteDemo.java**, sau đó chạy:

~~~bash
javac JavaPrerequisiteDemo.java
java JavaPrerequisiteDemo
~~~

Kết quả:

~~~text
An
15.75
~~~

**record** phù hợp với một số kiểu dữ liệu chỉ mang giá trị như DTO hoặc value object. Entity JPA thường cần class có trạng thái và vòng đời riêng; đừng mặc định rằng mọi record đều có thể thay thế entity.

### 3.7. Ngày giờ và kiểu dữ liệu phù hợp

Nên biết các kiểu trong **java.time**:

- **LocalDate** biểu diễn ngày không có múi giờ.
- **LocalDateTime** biểu diễn ngày giờ không gắn múi giờ.
- **Instant** biểu diễn một thời điểm trên dòng thời gian, thường phù hợp khi cần lưu thời điểm tuyệt đối.
- **OffsetDateTime** mang theo độ lệch múi giờ.

Chọn kiểu theo ý nghĩa nghiệp vụ và thống nhất cách lưu trữ, chuyển đổi múi giờ. Không nên dùng Date hoặc Calendar cho mã mới nếu không có lý do tương thích.

### 3.8. Build tool và kiểm thử

Biết đọc file **build.gradle** hoặc **pom.xml**, hiểu dependency, version và cách chạy ứng dụng. Bạn cũng nên biết cách chạy test bằng Gradle hoặc Maven, đọc lỗi biên dịch và đọc stack trace.

Không cần tự cấu hình build nâng cao trước khi học JPA, nhưng cần hiểu rằng Spring Boot, Spring Data JPA, Hibernate và JDBC driver là các dependency phối hợp với nhau.

## 4. SQL và cơ sở dữ liệu quan hệ

### 4.1. Bảng, hàng, cột và kiểu dữ liệu

Cơ sở dữ liệu quan hệ lưu dữ liệu trong các bảng. Một hàng biểu diễn một bản ghi; một cột biểu diễn một thuộc tính. Mỗi cột có kiểu dữ liệu và có thể có các ràng buộc.

Ví dụ, hệ thống bán hàng có thể có bảng **customers** và **orders**. Một khách hàng có thể có nhiều đơn hàng; mỗi đơn hàng thuộc về một khách hàng.

Bạn cần biết các kiểu thường gặp như INTEGER, BIGINT, VARCHAR, DATE, TIMESTAMP, BOOLEAN và DECIMAL. Tên kiểu và hành vi cụ thể có thể khác nhau giữa PostgreSQL, MySQL, SQL Server và các hệ quản trị khác.

### 4.2. Khóa chính, khóa ngoại và constraint

- **PRIMARY KEY** xác định duy nhất mỗi hàng và không được null.
- **FOREIGN KEY** đảm bảo giá trị tham chiếu đến bản ghi tồn tại ở bảng liên quan.
- **UNIQUE** ngăn giá trị trùng trong phạm vi ràng buộc.
- **NOT NULL** bắt buộc phải có giá trị.
- **CHECK** giới hạn giá trị theo điều kiện.
- **DEFAULT** cung cấp giá trị mặc định khi insert không truyền cột đó.

Ràng buộc ở cơ sở dữ liệu bảo vệ tính toàn vẹn dữ liệu ngay cả khi dữ liệu đến từ nhiều ứng dụng hoặc nhiều luồng xử lý. Không nên chỉ dựa vào kiểm tra ở giao diện hoặc Java.

### 4.3. Các nhóm câu lệnh SQL

Bạn nên phân biệt các nhóm lệnh:

- **DDL** định nghĩa cấu trúc, ví dụ CREATE TABLE và ALTER TABLE.
- **DML** thay đổi dữ liệu, ví dụ INSERT, UPDATE và DELETE.
- **DQL** thường dùng để chỉ truy vấn dữ liệu bằng SELECT.
- **DCL** quản lý quyền truy cập, ví dụ GRANT và REVOKE.
- **TCL** điều khiển transaction, ví dụ COMMIT và ROLLBACK.

Trước khi học repository, hãy tự viết được SELECT có WHERE, ORDER BY, LIMIT hoặc cú pháp phân trang tương đương của hệ quản trị đang dùng.

### 4.4. JOIN và quan hệ giữa các bảng

JOIN là kiến thức bắt buộc vì dữ liệu nghiệp vụ thường được tách thành nhiều bảng.

- **INNER JOIN** chỉ trả về các hàng có quan hệ khớp ở hai phía.
- **LEFT JOIN** giữ tất cả hàng ở bảng bên trái và điền NULL cho phía phải khi không có bản ghi khớp.
- **RIGHT JOIN** giữ tất cả hàng ở bảng bên phải; trong thực tế có thể viết lại bằng cách đổi thứ tự bảng và dùng LEFT JOIN.
- **CROSS JOIN** tạo tích Descartes giữa hai tập hàng.

Ví dụ tạo bảng và truy vấn khách hàng cùng đơn hàng:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total DECIMAL(12, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

SELECT
    c.id,
    c.name,
    o.id AS order_id,
    o.total
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = 1
ORDER BY o.created_at DESC;
~~~

Đọc được truy vấn này giúp bạn hiểu quan hệ giữa entity và cách một truy vấn repository có thể cần JOIN để lấy dữ liệu liên quan.

### 4.5. NULL, lọc và tổng hợp

SQL có logic ba giá trị: TRUE, FALSE và UNKNOWN. Vì vậy, so sánh một giá trị với NULL bằng dấu bằng không hoạt động như so sánh thông thường. Hãy dùng **IS NULL** hoặc **IS NOT NULL**.

Nắm các hàm và mệnh đề:

- **COUNT**, **SUM**, **AVG**, **MIN**, **MAX** để tổng hợp.
- **GROUP BY** gom nhóm bản ghi.
- **HAVING** lọc sau khi nhóm.
- **DISTINCT** loại bỏ kết quả trùng.
- **IN**, **BETWEEN**, **LIKE**, **EXISTS** để biểu diễn điều kiện.

Cần phân biệt WHERE và HAVING: WHERE lọc hàng trước khi nhóm; HAVING lọc nhóm sau khi GROUP BY.

### 4.6. Chuẩn hóa và thiết kế quan hệ

Chuẩn hóa giúp giảm lặp dữ liệu và tránh lỗi khi thêm, sửa hoặc xóa. Ở mức cơ bản, bạn cần biết:

- Mỗi bảng nên đại diện cho một loại thực thể hoặc một quan hệ có ý nghĩa.
- Không lưu danh sách nhiều giá trị trong một cột chỉ để tránh tạo bảng quan hệ.
- Dùng khóa ngoại để thể hiện quan hệ.
- Quan hệ một-một, một-nhiều và nhiều-nhiều cần cách thiết kế bảng phù hợp.
- Với quan hệ nhiều-nhiều, thường cần bảng nối chứa khóa ngoại đến hai bảng liên quan.

Thiết kế quan hệ đúng giúp việc ánh xạ entity và truy vấn bằng JPA dễ hiểu hơn.

### 4.7. Index và hiệu năng truy vấn

Index giúp cơ sở dữ liệu tìm dữ liệu nhanh hơn trong nhiều trường hợp, nhưng cũng tốn dung lượng và làm tăng chi phí ghi. Không nên tạo index cho mọi cột.

Bạn nên hiểu:

- Index thường hữu ích với cột hay dùng để tìm kiếm, JOIN hoặc sắp xếp.
- Thứ tự cột trong composite index có ý nghĩa.
- Truy vấn có thể không dùng index nếu biểu thức, kiểu dữ liệu hoặc điều kiện không phù hợp.
- Execution plan cho biết cơ sở dữ liệu dự định thực hiện truy vấn như thế nào.

Khi truy vấn chậm, hãy kiểm tra SQL, số lượng hàng, index và execution plan thay vì chỉ thêm cache hoặc tăng tài nguyên.

### 4.8. Transaction và ACID

Transaction gom nhiều thao tác dữ liệu thành một đơn vị công việc. Bốn thuộc tính ACID là:

- **Atomicity**: hoặc tất cả thao tác thành công, hoặc transaction bị hủy theo cơ chế rollback.
- **Consistency**: transaction đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ khác, dựa trên ràng buộc và quy tắc nghiệp vụ.
- **Isolation**: các transaction đồng thời được cô lập theo mức isolation đã chọn.
- **Durability**: dữ liệu đã commit được lưu bền vững theo bảo đảm của hệ quản trị.

Bạn nên biết commit, rollback và các vấn đề khi chạy đồng thời như dirty read, non-repeatable read, phantom read và lost update. Mỗi hệ quản trị có thể hỗ trợ isolation và hành vi khóa khác nhau.

### 4.9. SQL an toàn

Không nối chuỗi đầu vào người dùng trực tiếp vào câu SQL. Dùng parameter binding hoặc prepared statement để tách dữ liệu khỏi cấu trúc câu truy vấn. Đây là nguyên tắc quan trọng để tránh SQL injection.

## 5. Spring Framework và Spring Boot

### 5.1. IoC và Dependency Injection

**Inversion of Control (IoC)** nghĩa là ứng dụng giao quyền tạo và quản lý object cho container. **Dependency Injection (DI)** là cách container cung cấp dependency cho object cần sử dụng.

Thay vì một service tự tạo repository bằng **new**, Spring tạo bean và inject dependency. Cách này giảm kết dính và giúp thay thế dependency khi kiểm thử.

Constructor injection thường là lựa chọn rõ ràng vì dependency được thể hiện ngay trong constructor và có thể khai báo final:

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }
}
~~~

Ví dụ trên giả định CustomerRepository là một bean mà Spring có thể cung cấp. Bạn không cần tự khởi tạo nó bằng new.

### 5.2. Bean và các annotation thường gặp

- **@Component** đánh dấu một class để Spring quản lý như bean.
- **@Service** thể hiện vai trò tầng nghiệp vụ.
- **@Repository** thể hiện vai trò truy cập dữ liệu và hỗ trợ chuyển đổi một số exception liên quan đến persistence.
- **@Controller** và **@RestController** dùng ở tầng web.
- **@Configuration** và **@Bean** khai báo cấu hình và bean tường minh.
- **@Autowired** có thể dùng để inject dependency; với class chỉ có một constructor, Spring có thể tự sử dụng constructor đó mà không cần annotation.

Annotation không tự làm cho mọi class trở thành bean. Class phải nằm trong phạm vi component scan hoặc được khai báo qua cấu hình.

### 5.3. Spring Boot, auto-configuration và cấu hình

Spring Boot cung cấp cách khởi tạo ứng dụng, auto-configuration và cơ chế cấu hình ngoài mã nguồn. Bạn nên hiểu:

- Class khởi động thường có **@SpringBootApplication**.
- Component scan tìm các bean trong phạm vi được cấu hình.
- Auto-configuration dựa trên dependency và điều kiện để tạo cấu hình mặc định.
- File **application.properties** hoặc **application.yml** chứa cấu hình.
- Profile như **dev**, **test**, **prod** cho phép thay đổi cấu hình theo môi trường.
- Thông tin kết nối database như URL, username và password nên được quản lý qua cấu hình môi trường hoặc secret phù hợp, không hard-code vào mã nguồn.

Spring Boot giúp giảm cấu hình thủ công, nhưng khi có lỗi kết nối hoặc bean không được tạo, bạn vẫn cần hiểu component scan, dependency và cấu hình.

### 5.4. Phân chia tầng Controller, Service và Repository

Một ứng dụng đơn giản thường tách trách nhiệm như sau:

- **Controller** nhận request, kiểm tra dữ liệu đầu vào ở mức giao tiếp và trả response.
- **Service** thực hiện quy tắc nghiệp vụ, phối hợp nhiều repository và xác định ranh giới transaction.
- **Repository** thực hiện thao tác truy cập dữ liệu.
- **Entity** mô hình hóa trạng thái được lưu trong cơ sở dữ liệu.
- **DTO** biểu diễn dữ liệu trao đổi qua API hoặc giữa các lớp khi cần.

Không nên đặt toàn bộ nghiệp vụ trong controller hoặc để entity trở thành response API mặc định. Phân chia trách nhiệm rõ ràng giúp dễ kiểm thử và thay đổi.

### 5.5. Transaction trong Spring

Bạn cần biết **@Transactional** đánh dấu ranh giới transaction. Ở ứng dụng Spring Data JPA, annotation này thường được đặt tại service method đại diện cho một thao tác nghiệp vụ cần nhiều bước dữ liệu cùng thành công hoặc cùng rollback.

Một số điểm cần hiểu trước khi học sâu:

- Transaction thường được quản lý qua proxy của Spring.
- Lời gọi nội bộ giữa các method trong cùng object có thể không đi qua proxy, nên không phải lúc nào annotation trên method được gọi nội bộ cũng tạo hiệu lực như mong đợi.
- Theo mặc định phổ biến, transaction rollback với unchecked exception và Error; checked exception không tự động làm rollback nếu không cấu hình thêm.
- Transaction nên đủ ngắn, tránh giữ transaction mở trong lúc gọi dịch vụ bên ngoài hoặc chờ người dùng.
- Cần phân biệt transaction ở tầng ứng dụng với transaction do cơ sở dữ liệu thực thi.

Không cần thuộc mọi propagation và isolation option ngay từ đầu. Trước hết hãy hiểu vì sao một thao tác nghiệp vụ cần commit hoặc rollback như một đơn vị.

### 5.6. Kiểm thử ứng dụng Spring

Biết sự khác nhau giữa unit test và integration test:

- Unit test kiểm tra logic của một class với dependency được giả lập khi phù hợp.
- Integration test kiểm tra nhiều thành phần phối hợp, ví dụ Spring context, repository và database.
- Test repository nên xác minh truy vấn và mapping với cơ sở dữ liệu tương thích.
- Test service nên kiểm tra quy tắc nghiệp vụ và kết quả khi xảy ra lỗi.

Kiểm thử giúp phát hiện lỗi mapping, transaction và truy vấn mà chỉ kiểm tra biên dịch không thể phát hiện.

## 6. Những khái niệm JPA nên hình dung trước

Bạn chưa cần biết chi tiết mọi API JPA, nhưng nên hiểu các thuật ngữ sau để việc học tiếp theo không bị rời rạc:

- **ORM (Object-Relational Mapping)** ánh xạ object Java với bảng và quan hệ trong cơ sở dữ liệu.
- **Entity** là object được JPA quản lý và ánh xạ với dữ liệu lưu trữ.
- **EntityManager** là API trung tâm của JPA để quản lý entity.
- **Persistence Context** theo dõi các entity đang được quản lý trong một phạm vi làm việc.
- **Dirty Checking** là cơ chế phát hiện thay đổi trên entity được quản lý để tạo lệnh cập nhật khi đồng bộ.
- **Flush** đồng bộ thay đổi trong persistence context xuống cơ sở dữ liệu; flush không đồng nghĩa với commit transaction.
- **Lazy Loading** trì hoãn tải dữ liệu liên quan đến khi cần; nếu truy cập ngoài phạm vi persistence context phù hợp, có thể gặp lỗi.
- **N+1 Query** là tình huống một truy vấn lấy danh sách được theo sau bởi nhiều truy vấn riêng lẻ để lấy dữ liệu liên quan.
- **Cascade** quy định một số thao tác trên entity có thể lan sang entity liên quan; cần chọn cẩn thận để tránh thao tác dữ liệu ngoài ý muốn.

Những khái niệm này sẽ được học kỹ hơn trong phần JPA. Ở giai đoạn chuẩn bị, chỉ cần hiểu mục đích và nhận biết vấn đề mà chúng giải quyết.

## 7. Thứ tự học đề xuất

Nếu kiến thức hiện tại chưa đồng đều, hãy học theo thứ tự:

1. **Java cơ bản và OOP**: class, object, interface, collections, generics, exception, annotation và lambda.
2. **SQL căn bản**: SELECT, INSERT, UPDATE, DELETE, JOIN, constraint, transaction và index ở mức khái niệm.
3. **Spring Core**: IoC, DI, bean, component scan và cấu hình.
4. **Spring Boot**: khởi động ứng dụng, dependency, application configuration và profile.
5. **JPA nền tảng**: entity, mapping, persistence context, EntityManager và quan hệ.
6. **Spring Data JPA**: repository, derived query, JPQL, native query, phân trang và sắp xếp.
7. **Thực hành nâng cao**: transaction, fetch strategy, N+1, locking, auditing và tối ưu truy vấn.

Không cần chờ đến khi hoàn thành mọi chủ đề nâng cao mới bắt đầu JPA. Khi đã hiểu Java OOP, SQL cơ bản và DI của Spring, bạn có thể bắt đầu học JPA song song với việc củng cố phần còn yếu.

## 8. Bài thực hành chuẩn bị

Hãy thực hiện một bài tập nhỏ về quản lý khách hàng và đơn hàng:

**Phần Java**

- Tạo class Customer với ID, email và tên.
- Tạo class Order với ID, tổng tiền và thời điểm tạo.
- Dùng kiểu phù hợp cho tiền và ngày giờ.
- Tạo một service đơn giản nhận repository qua constructor.
- Viết unit test cho quy tắc kiểm tra email hoặc tổng tiền.

**Phần SQL**

- Tạo bảng customers và orders.
- Khai báo khóa chính, khóa ngoại, UNIQUE và NOT NULL.
- Thêm ít nhất hai khách hàng và ba đơn hàng.
- Viết truy vấn lấy đơn hàng cùng tên khách hàng bằng JOIN.
- Viết truy vấn tính tổng tiền đơn hàng theo từng khách hàng bằng GROUP BY.

**Phần Spring**

- Tạo một ứng dụng Spring Boot nhỏ.
- Khai báo một service và inject dependency qua constructor.
- Đọc cấu hình từ application.properties hoặc application.yml.
- Tạo một integration test để xác minh Spring context khởi động được.

Khi đã hiểu từng phần độc lập, hãy kết nối chúng bằng Spring Data JPA. Khi đó bạn sẽ biết repository đang thay thế phần mã nào, SQL được sinh ra để làm gì và transaction bảo vệ thao tác nghiệp vụ ra sao.

## 9. Checklist tự đánh giá

Bạn có thể bắt đầu học Spring Data JPA khi phần lớn câu dưới đây trả lời được:

- [ ] Tôi giải thích được class, object, interface và constructor.
- [ ] Tôi phân biệt được List, Set và Map.
- [ ] Tôi hiểu generics, equals/hashCode, exception và Optional ở mức cơ bản.
- [ ] Tôi biết chọn BigDecimal cho tiền và kiểu java.time phù hợp cho ngày giờ.
- [ ] Tôi viết được SELECT có WHERE, ORDER BY và JOIN.
- [ ] Tôi hiểu primary key, foreign key, UNIQUE, NOT NULL và quan hệ một-nhiều.
- [ ] Tôi giải thích được transaction, commit, rollback và ACID.
- [ ] Tôi hiểu IoC, Dependency Injection và bean trong Spring.
- [ ] Tôi phân biệt được trách nhiệm của Controller, Service và Repository.
- [ ] Tôi hiểu @Transactional được dùng để làm gì ở tầng nghiệp vụ.

Nếu còn thiếu một vài mục, hãy ghi lại và bổ sung trong lúc học. Nếu chưa hiểu JOIN, khóa ngoại hoặc DI, nên dành thời gian ôn lại trước vì đây là nền tảng xuất hiện liên tục trong các ví dụ JPA.

## 10. Những nhầm lẫn thường gặp

1. **Spring Data JPA, JPA và Hibernate là một thứ**: không đúng. JPA là đặc tả, Hibernate là một implementation phổ biến, còn Spring Data JPA cung cấp abstraction repository và tích hợp với JPA.
2. **Dùng repository thì không cần SQL**: không đúng. Repository giảm mã truy cập dữ liệu, nhưng SQL vẫn quyết định cách cơ sở dữ liệu đọc và ghi dữ liệu.
3. **Entity giống hệt DTO**: không nên mặc định như vậy. Entity có vòng đời persistence và quan hệ; DTO phục vụ trao đổi dữ liệu.
4. **Mọi thao tác đều tự động nằm trong một transaction**: không đúng. Cần hiểu ranh giới transaction, cách proxy hoạt động và vị trí đặt @Transactional.
5. **Dùng Stream để lọc dữ liệu lớn luôn tốt**: không đúng. Nếu có thể lọc, sắp xếp và phân trang tại database thì thường nên để database thực hiện.
6. **Lazy loading luôn giúp ứng dụng nhanh hơn**: không đúng. Nếu truy cập quan hệ trong vòng lặp, lazy loading có thể tạo N+1 query.
7. **Có khóa ngoại trong Java là đủ**: không đúng. Constraint ở database mới bảo vệ dữ liệu trước mọi nguồn ghi vào cơ sở dữ liệu.

## 11. Câu hỏi ôn tập

**1. Vì sao cần hiểu SQL khi đã có Spring Data JPA?**

Vì Spring Data JPA vẫn tạo và thực thi truy vấn trên cơ sở dữ liệu. SQL giúp bạn hiểu JOIN, lọc, phân trang, constraint và hiệu năng của truy vấn.

**2. Vì sao cần hiểu interface và generics?**

Repository thường được khai báo bằng interface và tham số hóa theo entity cùng kiểu ID. Hiểu hai khái niệm này giúp bạn đọc được API như JpaRepository<Customer, Long>.

**3. IoC và DI giải quyết vấn đề gì?**

Chúng chuyển trách nhiệm tạo và cung cấp dependency sang container, giảm kết dính giữa các class và giúp kiểm thử dễ hơn.

**4. Flush có giống commit không?**

Không. Flush đồng bộ thay đổi của persistence context xuống database; commit kết thúc transaction thành công. Một transaction có thể flush nhiều lần trước khi commit.

**5. Có cần học Hibernate trước Spring Data JPA không?**

Không cần học sâu Hibernate trước. Hãy nắm Java, SQL và Spring DI, sau đó học JPA và hiểu dần cách provider như Hibernate thực thi các thao tác.

Khi hoàn thành các nền tảng trên, bạn đã có đủ kiến thức để bắt đầu với entity, repository và truy vấn trong Spring Data JPA.