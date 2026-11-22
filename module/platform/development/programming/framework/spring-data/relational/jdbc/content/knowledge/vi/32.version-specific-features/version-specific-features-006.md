# AOT và native image: cấu hình, tối ưu repository và giới hạn

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, Ahead-of-Time processing (AOT) giúp chuẩn bị một phần công việc vốn thường diễn ra khi ứng dụng khởi động. Spring phân tích cấu hình và bean definitions ở build time, sinh mã khởi tạo, proxy và runtime hints. Spring Data JDBC còn có thể sinh trước implementation cho những query method đủ điều kiện trong repository.

Khi kết hợp với **GraalVM Native Image**, các kết quả AOT được dùng để biên dịch ứng dụng thành executable dành cho một hệ điều hành và kiến trúc cụ thể. Native image có thể khởi động nhanh và dùng ít bộ nhớ hơn trong nhiều workload, nhưng yêu cầu ứng dụng tuân theo mô hình closed-world: classpath, bean graph, reflection, resource và proxy cần được biết trước hoặc khai báo bằng hints.

Bài này phân biệt AOT với native compilation, cấu hình Spring Boot/Gradle, cách Spring Data JDBC sinh repository query methods, cách khai báo domain types và dialect, runtime hints, các giới hạn cần biết và quy trình kiểm thử native image.

## 1. Phân biệt AOT và GraalVM Native Image

Hai khái niệm liên quan nhưng không đồng nghĩa:

- **Spring AOT** phân tích ApplicationContext tại build time, tạo source code/bytecode và runtime hints để khởi tạo ứng dụng theo cách tĩnh hơn.
- **GraalVM Native Image** dùng phân tích tĩnh để biên dịch ứng dụng và các dependency thành executable native, không cần mang theo JVM để chạy.

AOT cũng có thể chạy trên JVM. Điều này hữu ích để kiểm tra code khởi tạo đã sinh trước khi tốn thời gian build native executable.

~~~mermaid
flowchart TD
    Source["Spring Boot + Spring Data JDBC source"]
    AOT["Spring AOT<br/>processAot"]
    Generated["Generated code<br/>Runtime hints<br/>AOT repository methods"]
    JVM["Run on JVM<br/>spring.aot.enabled=true"]
    Native["GraalVM Native Image<br/>nativeCompile"]
    Executable["Platform-specific executable"]
    Source --> AOT --> Generated
    Generated --> JVM
    Generated --> Native --> Executable
~~~

| Khía cạnh | JVM thông thường | AOT trên JVM | Native image |
|---|---|---|---|
| Spring context | Phần lớn phân tích khi chạy | Dùng kết quả AOT đã sinh | Dùng kết quả AOT đã sinh |
| Query method repository | Có thể cần xử lý metadata khi khởi động | Dùng implementation đủ điều kiện đã sinh | Dùng implementation đủ điều kiện đã sinh |
| Reflection/resources/proxies | JVM thường linh hoạt hơn | Kiểm tra các hint đã sinh | Phải được phân tích hoặc khai báo trước |
| Runtime classpath | Có thể thay đổi theo cách triển khai | Cố định theo artifact đã build | Cố định tại build time |
| Đầu ra | JAR/class chạy trên JVM | JAR/class có AOT assets | Executable theo OS/CPU target |

Không phải bật AOT là ứng dụng tự trở thành native executable. AOT tạo các tài sản cần thiết; native image compiler mới tạo executable.

## 2. AOT đem lại lợi ích gì cho Spring Data JDBC?

Spring Data JDBC đóng góp vào AOT theo nhiều hướng:

1. **ManagedTypes và entity metadata:** ghi nhận tập domain types đã được phát hiện khi xử lý ứng dụng.
2. **Runtime hints cho repository:** cung cấp reflection hints cho entity, return types, annotation Spring Data và repository fragments.
3. **AOT repository methods:** sinh implementation trước cho các query method có thể xác định tại build time.
4. **Auditing và các tích hợp khác:** đóng góp hints cần thiết cho những tính năng Spring Data liên quan.

Điểm đáng chú ý là AOT repository chuyển một phần công việc phân tích derived query, annotated query và named query từ lúc khởi động sang lúc build. Vì thế, ứng dụng có thể giảm công việc xử lý repository metadata khi khởi động.

**AOT repository không tối ưu execution plan của database và không tự làm câu SQL chạy nhanh hơn.** Nếu một truy vấn chậm vì thiếu index, trả quá nhiều cột hoặc JOIN không phù hợp, vẫn phải tối ưu query và schema như bình thường.

## 3. Đánh dấu domain types để Spring Data phát hiện

Spring Data cần biết các domain types được quản lý. Với Spring Data JDBC, hãy dùng annotation mapping trên entity:

~~~java
package com.example.sales.order;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private Long customerId;
    private String status;

    protected Order() {
    }

    public Order(Long customerId) {
        this.customerId = customerId;
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public String getStatus() {
        return status;
    }
}
~~~

**@Table** giúp Spring Data nhận diện domain type trong quá trình quét entity và đưa nó vào **ManagedTypes**. Điều này quan trọng với native image vì không thể dựa vào classpath scanning động lúc runtime như JVM thông thường.

Với entity con được ánh xạ vào bảng riêng qua **@MappedCollection**, hãy bảo đảm mapping domain được Spring Data nhận diện đúng. Nếu ứng dụng có cách tổ chức package hoặc entity scanning đặc biệt, cần cấu hình tập managed types phù hợp với cấu hình Spring Data JDBC của dự án.

Không dựa vào việc native executable tự tìm mọi class trong package ở runtime. Việc phát hiện type cần hoàn tất trong giai đoạn AOT.

## 4. Cấu hình Gradle cho AOT và native image

Với Spring Boot Gradle Plugin, có thể thêm GraalVM Native Build Tools plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'org.graalvm.buildtools.native' version '1.1.14'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là ví dụ theo tài liệu Spring Boot 4.1.2 và Native Build Tools 1.1.14 hiện hành. Với dự án thực tế, hãy dùng phiên bản Spring Boot, Spring Data Relational, GraalVM và JDBC driver được dependency management của dự án hỗ trợ; không ghép phiên bản ngẫu nhiên.

Khi áp dụng GraalVM Native Image plugin, Spring Boot tự cấu hình AOT plugin và task liên quan. Các task thường dùng:

~~~bash
# Sinh code và tài nguyên AOT cho application
./gradlew processAot

# Biên dịch native executable
./gradlew nativeCompile

# Biên dịch và chạy test trong native image
./gradlew nativeTest
~~~

**nativeCompile** sử dụng output từ **processAot**. **nativeTest** sử dụng AOT output của application và test. Việc biên dịch native image thường tốn thời gian và tài nguyên hơn build JAR JVM.

Nếu chỉ muốn chạy AOT trên JVM để kiểm tra generated context, có thể áp dụng **org.springframework.boot.aot** plugin mà chưa cần native plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

apply plugin: 'org.springframework.boot.aot'
~~~

Sau khi build artifact có AOT assets, có thể chạy:

~~~bash
java -Dspring.aot.enabled=true -jar build/libs/application.jar
~~~

Lệnh và đường dẫn artifact có thể cần điều chỉnh theo tên project và cấu hình Gradle. Nếu không có generated AOT assets trong JAR, chỉ đặt system property không tạo ra chúng.

## 5. AOT cố định những quyết định cấu hình nào?

Spring AOT phân tích ApplicationContext dựa trên classpath và Environment tại build time. Vì vậy, một số quyết định trở thành một phần của ứng dụng đã được xử lý:

- Classpath phải được xác định tại build time.
- Bean graph không thể tùy ý thay đổi theo property lúc runtime.
- Profile được chọn trong lúc AOT có thể được giữ cố định trong cấu hình đã sinh.
- Các điều kiện như **@ConditionalOnProperty** được đánh giá khi build.
- Bean đăng ký động bằng những cách AOT không thể phân tích có thể không được đưa vào generated context hoặc thiếu hints.

Ví dụ:

~~~java
@Configuration
@Profile("production")
class ProductionConfiguration {
    // Bean chỉ được đưa vào AOT context nếu profile phù hợp
    // được kích hoạt trong môi trường build AOT.
}
~~~

Nếu build AOT khi profile **production** không được bật, sau đó chỉ truyền **--spring.profiles.active=production** lúc chạy native image không thể bảo đảm tạo ra bean đã bị loại khỏi generated context.

Tương tự, nếu một bean chỉ được tạo khi property có giá trị **feature.enabled=true**, hãy cấu hình đúng property cho **processAot**. Đừng kỳ vọng đổi property lúc chạy native image sẽ tái thực hiện toàn bộ quyết định bean graph.

### Tránh đăng ký bean mà AOT không thể suy luận

Các pattern sau cần được xem xét cẩn thận:

- Đăng ký singleton instance trực tiếp qua **registerSingleton**.
- Bean definition dùng instance supplier/lambda hoặc method reference mà AOT không thể chuyển đổi.
- Tạo bean dựa trên class name được đọc từ cấu hình lúc runtime.
- Tự quét classpath hoặc tạo proxy/class động trong lúc chạy.
- Bean factory method khai báo kiểu trả về quá tổng quát khiến AOT không nhận diện implementation thực.

Ưu tiên **@Configuration**, **@Bean**, component scanning và kiểu trả về cụ thể. Nếu phải đăng ký bean động, hãy kiểm tra hướng dẫn AOT của Spring Framework và cung cấp contribution/hints phù hợp.

## 6. AOT repositories trong Spring Data JDBC

**AOT repositories** là tối ưu riêng của Spring Data: Spring Data phân tích query methods đã biết ở build time và sinh implementation cho những method đủ điều kiện.

Ví dụ repository:

~~~java
package com.example.sales.order;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends CrudRepository<Order, Long> {

    List<Order> findByStatus(String status);

    Optional<Order> findByExternalReference(String externalReference);

    Page<Order> findByCustomerId(Long customerId, Pageable pageable);

    @Query("SELECT * FROM orders WHERE status = :status")
    List<Order> findOrdersByStatus(@Param("status") String status);

    @Modifying
    @Query("UPDATE orders SET status = :status WHERE id = :id")
    int changeStatus(@Param("id") Long id, @Param("status") String status);
}
~~~

Các method như **findByStatus**, query có **@Query**, named query và method có phân trang có thể được phân tích trước. Spring Data sinh query method implementation để tránh phải phân tích lại metadata method khi mỗi ứng dụng khởi động.

Generated fragment có tên theo dạng:

~~~text
<Repository FQCN>Impl__Aot
~~~

Fragment được đặt trong package của repository interface. Đây là chi tiết nội bộ do Spring Data quản lý. Không tham chiếu trực tiếp generated class trong application code vì tên và cách sinh implementation có thể thay đổi giữa các phiên bản.

## 7. Những query method nào được AOT repositories hỗ trợ?

Theo tài liệu Spring Data Relational 4.1.2, các nhóm sau đủ điều kiện nếu method không bị loại bởi giới hạn khác:

| Nhóm | Hỗ trợ |
|---|---|
| Derived query methods | Có |
| Query khai báo bằng **@Query** | Có |
| Named query methods | Có |
| **@Modifying** trả về **void**, **int**, **long** | Có |
| Pagination | Có |
| Return type **Slice**, **Stream**, **Optional** | Có |
| DTO projection và interface projection | Có |
| Value Expressions | Có |

Không phải mọi method trong repository interface đều được sinh implementation mới. Những method được cung cấp bởi base repository class hoặc fragment tương ứng tiếp tục dùng implementation của fragment đó.

## 8. Những giới hạn quan trọng của AOT repositories

Tài liệu hiện hành nêu một số nhóm bị loại hoặc chưa hỗ trợ:

| Trường hợp | Tình trạng |
|---|---|
| Method nhận **ScrollPosition**, ví dụ keyset scrolling | Chưa được hỗ trợ |
| Method kế thừa từ **CrudRepository** | Không sinh lại; dùng base repository implementation |
| Querydsl methods | Không sinh bởi JDBC AOT repository |
| Query by Example | Không sinh bởi JDBC AOT repository |
| Method có implementation quá phức tạp | Có thể bị loại khỏi AOT generation |
| Method được xử lý bởi custom repository implementation fragment | Không phải query method độc lập để AOT sinh implementation |
| Stored procedure methods | Có thể xuất hiện trong metadata, nhưng method code không được sinh trong AOT repository |

Điều này không có nghĩa các method bị loại tự động không chạy trong native image. Chúng vẫn cần implementation từ base fragment, custom fragment hoặc cơ chế tương ứng và phải đáp ứng các yêu cầu native image/hints của phần implementation đó.

Ví dụ method dùng **ScrollPosition**:

~~~java
Window<Order> findFirst100ByStatusOrderById(
    String status,
    ScrollPosition position
);
~~~

Đây là dạng keyset/scrolling không thuộc tập method AOT repository được tài liệu 4.1.2 hỗ trợ. Nếu ứng dụng cần native image, hãy kiểm tra phương thức cụ thể với phiên bản Spring Data đang dùng và cân nhắc phân trang **Pageable**/**Slice** nếu phù hợp với nghiệp vụ.

### Custom repository fragment

Ví dụ repository có fragment:

~~~java
public interface OrderSearchRepository {
    List<Order> searchWithSpecialRules(String status);
}

public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    @Override
    public List<Order> searchWithSpecialRules(String status) {
        // Custom implementation.
        return List.of();
    }
}
~~~

Method được triển khai bởi fragment này không được AOT query generator viết lại thành derived query implementation. Nếu custom fragment dùng reflection, resource hoặc proxy động, chính implementation phải có native image hints cần thiết.

## 9. Metadata repository được sinh ra

Trong AOT processing, Spring Data JDBC introspect query methods và lưu metadata dưới dạng JSON cạnh package của repository interface. Metadata có thể mô tả:

- Tên repository và module.
- Signature của method.
- Query đã chuẩn hóa.
- Count query cho pagination.
- Named query name.
- Fragment mà method được delegate tới.

Ví dụ minh họa rút gọn:

~~~json
{
  "name": "com.example.sales.order.OrderRepository",
  "module": "JDBC",
  "type": "IMPERATIVE",
  "methods": [
    {
      "name": "findByStatus",
      "signature": "List<Order> findByStatus(String)",
      "query": {
        "query": "SELECT * FROM orders WHERE status = :status"
      }
    }
  ]
}
~~~

Đây là ví dụ giải thích cấu trúc metadata, không phải file cấu hình mà ứng dụng cần tự tạo. Spring Data quản lý metadata được sinh ra.

Query trong metadata là dạng đã chuẩn hóa:

- Value expressions được thay bằng bind markers.
- Metadata không mô tả đầy đủ xử lý bind value lúc runtime.
- **StartingWith**/**EndingWith** có thể thêm wildcard vào giá trị bind ở runtime.
- Runtime sort không thể được viết thành query string cố định tại build time vì giá trị sort chỉ có khi method được gọi.

## 10. Tùy chọn bật/tắt AOT repository

AOT repository được tạo khi Spring AOT được bật. Có thể tắt generation để chẩn đoán vấn đề hoặc tạm loại bỏ tối ưu riêng:

~~~properties
# Tắt AOT repositories cho mọi Spring Data module
spring.aot.repositories.enabled=false

# Hoặc chỉ tắt AOT repositories của Spring Data JDBC
spring.aot.jdbc.repositories.enabled=false
~~~

Hai property này có phạm vi khác nhau. Không cần tắt AOT repository trong ứng dụng bình thường nếu các query method đều hoạt động đúng. Nếu tắt để điều tra, cần kiểm tra lại native image vì bạn đang thay đổi cách repository được chuẩn bị.

Một quyết định build time khác cần lưu ý: Spring Data module dùng để triển khai repository được cố định trong AOT output. Nếu thay đổi module/implementation hoặc thay đổi điều kiện bean có ảnh hưởng đến repository, phải chạy AOT processing lại.

## 11. Cung cấp JdbcDialect để tránh truy cập database sớm

Spring Data JDBC cần **JdbcDialect** để xử lý khác biệt SQL giữa các database. Cách mặc định có thể dò dialect bằng cách lấy connection và đọc metadata. Trong quá trình AOT, việc dò dialect có thể gây truy cập database sớm khi build.

Tài liệu Spring Data Relational khuyến nghị cung cấp dialect tường minh để tránh kết nối database không cần thiết trong AOT processing.

Ví dụ với PostgreSQL trong cấu hình Spring Data JDBC tùy chỉnh:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.dialect.JdbcDialect;
import org.springframework.data.jdbc.core.dialect.JdbcPostgresDialect;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    public JdbcDialect jdbcDialect(
            NamedParameterJdbcOperations operations) {
        return JdbcPostgresDialect.INSTANCE;
    }
}
~~~

Đoạn code chỉ phù hợp khi ứng dụng thực sự dùng PostgreSQL. Với MySQL, MariaDB, SQL Server hoặc database khác, chọn đúng JDBC dialect tương ứng. Trong ứng dụng Spring Boot dùng auto-configuration, hãy tích hợp cấu hình dialect theo extension point/bean mà phiên bản Boot và Spring Data JDBC đang hỗ trợ; tránh tạo hai cấu hình persistence cạnh tranh.

Không khai báo PostgreSQL dialect chỉ để làm build AOT thành công khi database runtime là loại khác. Dialect quyết định SQL và cách xử lý kiểu dữ liệu, vì vậy chọn sai dialect có thể làm query hoặc ghi dữ liệu lỗi.

## 12. Runtime hints cho native image

Native image phân tích reachability từ entry point. GraalVM không thể tự suy luận mọi hành vi động như:

- Reflection gọi method/constructor không có direct call.
- Đọc file/resource theo tên được tạo lúc runtime.
- Java serialization.
- Tạo JDK dynamic proxy theo interface.
- JNI hoặc các thư viện native.

Spring AOT và Spring Data đóng góp nhiều hints tự động, gồm hints cho auditing, managed types, repository entity/return type, repository fragments và annotation. Tuy nhiên, dependency bên thứ ba hoặc code tự viết có thể cần hints bổ sung.

### Đăng ký RuntimeHintsRegistrar

Ví dụ một thư viện ngoài dùng reflection để tạo **LegacyPayload** và cần đọc resource:

~~~java
package com.example.nativeimage;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class ApplicationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            LegacyPayload.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.resources().registerPattern(
            "legacy/config/*.json"
        );
    }
}
~~~

Kích hoạt hints bằng **@ImportRuntimeHints**:

~~~java
package com.example.config;

import com.example.nativeimage.ApplicationRuntimeHints;
import org.springframework.aot.hint.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApplicationRuntimeHints.class)
public class NativeImageConfiguration {
}
~~~

Chỉ đăng ký quyền truy cập cần thiết. Không bật reflection cho mọi class hoặc đưa toàn bộ resource vào image một cách tùy tiện; hints quá rộng làm giảm lợi ích phân tích tĩnh và có thể tăng kích thước executable.

### Hints cho type binding

Với kiểu được serialize/deserialized nhưng không được Spring suy luận từ endpoint hoặc contract đã biết, có thể dùng **@RegisterReflectionForBinding** hoặc đăng ký reflection hints phù hợp. Những type được Spring Data JDBC quản lý thường đã có hints do Spring Data đóng góp; chỉ bổ sung khi lỗi thực tế cho thấy còn thiếu.

### RuntimeHintsPredicates

Có thể kiểm thử hints tùy chỉnh mà không cần build native image:

~~~java
@Test
void registersLegacyPayloadHints() {
    RuntimeHints hints = new RuntimeHints();
    new ApplicationRuntimeHints()
        .registerHints(hints, getClass().getClassLoader());

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onType(LegacyPayload.class)
    ).accepts(hints);

    assertThat(
        RuntimeHintsPredicates.resource()
            .forResource("legacy/config/sample.json")
    ).accepts(hints);
}
~~~

Các test này xác minh registry chứa hints mong muốn. Chúng không thay thế việc chạy native executable và kiểm thử đường code thực tế.

## 13. Kiểm thử AOT trên JVM trước khi build native

Một quy trình thực tế nên chia thành nhiều tầng:

1. Chạy unit test và integration test trên JVM như bình thường.
2. Chạy AOT processing để phát hiện vấn đề trong generated bean definitions và repository methods.
3. Chạy ứng dụng trên JVM với **spring.aot.enabled=true**.
4. Build native executable.
5. Chạy native executable và integration test trên database mục tiêu.
6. Chạy native tests trong CI ở tần suất phù hợp.

Ví dụ kiểm tra AOT trên JVM:

~~~bash
java -Dspring.aot.enabled=true -jar build/libs/application.jar
~~~

Khi AOT-enabled JVM khởi động thành công, độ tin cậy tăng lên vì ứng dụng đã sử dụng generated initialization code. Tuy nhiên, native image vẫn có khác biệt về reflection, resource, proxy, class loading và driver.

Spring Boot khuyến nghị tiếp tục chạy phần lớn unit/integration test trên JVM để vòng lặp phát triển nhanh. Tập trung native testing vào những phần dễ khác biệt giữa JVM và native executable.

## 14. Kiểm thử Spring Data JDBC trong native image

Một native smoke test chỉ xác minh application context khởi động là chưa đủ. Với Spring Data JDBC, nên kiểm tra các thao tác thực tế:

- Repository được khởi tạo và inject đúng.
- Derived query method chạy đúng.
- **@Query** và **@Modifying** bind tham số đúng.
- Pagination/count query trả metadata chính xác.
- DTO/interface projection được ánh xạ.
- Custom repository fragment hoạt động.
- Converter, callback và auditing được gọi đúng.
- ID generation và optimistic locking hoạt động.
- JDBC driver kết nối được database.
- Flyway/Liquibase hoặc resource migration được đóng gói và đọc được.
- Transaction commit/rollback đúng.
- JSON serialization và các resource được dùng bởi endpoint có mặt trong image.

Đặc biệt, hãy chạy test với database và JDBC driver thực tế. H2 có thể hữu ích cho test nhanh nhưng không chứng minh driver PostgreSQL/MySQL/SQL Server hoạt động trong native image.

## 15. Tracing agent để tìm hint còn thiếu

GraalVM Native Image tracing agent có thể chạy ứng dụng JVM và ghi nhận một số hoạt động reflection, resource hoặc proxy mà code thực tế đã sử dụng:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=build/native-agent-config \
  -jar build/libs/application.jar
~~~

Sau khi khởi động, hãy thực hiện các luồng đại diện như đăng nhập, tìm Order, chạy query projection, đọc file cấu hình và gọi endpoint. Khi ứng dụng dừng, agent ghi các hint đã quan sát vào thư mục cấu hình.

Tracing agent hữu ích để tìm hành vi mà AOT không nhận diện được, nhưng kết quả chỉ phản ánh những code path đã chạy. Nếu không thực hiện luồng cập nhật hoặc một query hiếm gặp, agent không thể ghi nhận hint cho luồng đó.

Khi chạy agent qua test suite, output có thể chứa nhiều hint chỉ cần cho test framework. Hãy review và lọc trước khi đưa file vào:

~~~text
src/main/resources/META-INF/native-image/
~~~

Không sao chép toàn bộ output một cách máy móc. Kết hợp tracing agent với tài liệu reachability metadata và test native thực tế.

## 16. Giới hạn của JDBC driver và dependency bên thứ ba

Spring Data JDBC có thể đóng góp hints cho phần code của Spring Data, nhưng không thể tự cung cấp đầy đủ hints cho mọi thư viện ngoài.

Các thành phần cần kiểm tra:

- JDBC driver có reachability metadata/native support phù hợp với phiên bản GraalVM đang dùng không.
- Driver có nạp resource, charset hoặc class bằng tên động không.
- Pool connection có yêu cầu reflection/proxy đặc biệt không.
- Thư viện migration có resource/script cần đưa vào image không.
- Logging, metrics, tracing hoặc security provider có phụ thuộc reflection/JNI không.
- Custom converter, type handler và callback có dùng reflection không được suy luận không.

Nếu một dependency không có metadata hoặc có hành vi runtime không tương thích closed-world, việc thêm một reflection hint đơn giản có thể không đủ. Cần kiểm tra tài liệu của thư viện, reachability metadata repository hoặc thay thế dependency/pattern không tương thích.

Native image cũng là executable gắn với OS và kiến trúc mục tiêu. Build cho Linux x86-64 không tạo ra executable Windows ARM64. Hãy build trên target phù hợp hoặc dùng quy trình buildpack/CI tương ứng.

## 17. Những quyết định AOT được cố định và cách xử lý thay đổi

Một khi generated AOT assets đã được tạo, những quyết định tại build time là một phần của artifact:

| Thay đổi | Cần chạy AOT lại? |
|---|---|
| Thêm/xóa bean hoặc thay đổi **@Configuration** | Có |
| Thay đổi profile hoặc conditional property ảnh hưởng bean graph | Có |
| Thêm/sửa repository query method | Có |
| Thay đổi domain type/repository fragment | Có |
| Thay đổi dependency hoặc version ảnh hưởng classpath | Có |
| Chỉ thay đổi dữ liệu trong database | Không, nếu không thay đổi code/config AOT |
| Chỉ thay đổi một property runtime không ảnh hưởng bean graph | Thường không, nhưng phải kiểm tra property có được AOT đánh giá hay không |

Nếu đổi Spring Data module thực hiện repository hoặc chuyển cấu hình repository giữa các module, cần AOT re-processing. Không dùng generated class cũ với source code mới.

## 18. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách xử lý |
|---|---|---|
| Bật AOT là đã có native executable | AOT tạo code/hints; native compiler mới tạo executable | Chạy native build task |
| AOT repositories sinh mọi method repository | Chỉ sinh query method đủ điều kiện | Kiểm tra base methods, custom fragments và unsupported methods |
| **CrudRepository.save/findById** được sinh lại | Base implementation tiếp tục được dùng | Giữ repository base implementation tương thích native |
| AOT làm SQL nhanh hơn | Chủ yếu chuyển phân tích query method sang build time | Tối ưu index, SQL, projection và transaction riêng |
| Mọi **ScrollPosition** method đều được AOT hỗ trợ | Keyset/ScrollPosition hiện chưa được hỗ trợ trong JDBC AOT repository | Kiểm tra phiên bản và chọn API phù hợp |
| **@Table** chỉ phục vụ tên bảng | Nó còn giúp Spring Data phát hiện domain type cho ManagedTypes | Annotate domain types được quản lý |
| Native image có thể quét classpath lúc runtime | Closed-world không hỗ trợ classpath scanning động như JVM | Để scanning diễn ra ở build time |
| Spring tự tạo mọi reflection hint cho thư viện ngoài | Spring chủ yếu biết phần tích hợp của chính nó | Kiểm tra reachability metadata và thêm hints khi cần |
| Chạy AOT trên JVM chứng minh native chắc chắn chạy | AOT JVM không bao phủ mọi khác biệt native | Build và chạy native test |
| Có thể đổi profile tùy ý sau khi native image đã build | Profile/conditional bean decisions được chốt ở build time | Build artifact theo môi trường/feature cần dùng |
| Chỉ cần tracing agent chạy một lần | Agent chỉ ghi nhận code path đã được thực thi | Chạy các luồng đại diện và review hints |
| Build native trên một OS dùng được mọi OS | Executable phụ thuộc platform/architecture | Build theo target deployment |

## 19. Quy trình triển khai đề xuất

### Giai đoạn phát triển

1. Dùng Spring Data JDBC repository và query methods thông thường.
2. Annotate domain types bằng **@Table** và kiểm tra entity scanning.
3. Giữ custom repository fragment đơn giản, rõ ràng và hạn chế reflection động.
4. Chạy test trên JVM và database tương ứng.
5. Bật AOT để phát hiện cấu hình bean phụ thuộc runtime.

### Giai đoạn chuẩn bị native

1. Thêm GraalVM Native Build Tools plugin.
2. Chạy **processAot** với đúng environment/profile/conditional properties.
3. Cung cấp **JdbcDialect** phù hợp để tránh truy cập DB sớm khi dò dialect.
4. Kiểm tra query method nào được AOT sinh và method nào dùng fragment/base implementation.
5. Bổ sung RuntimeHints cho dependency hoặc code động nếu cần.
6. Chạy AOT-enabled JVM.

### Giai đoạn CI/CD

1. Chạy unit và integration tests trên JVM.
2. Chạy AOT processing và AOT-enabled JVM smoke test.
3. Build native executable cho target deployment.
4. Chạy native tests hoặc native integration smoke test.
5. Kiểm tra kết nối JDBC, repository CRUD/query, transaction và migration.
6. Đo startup time, memory footprint và hiệu năng request trên workload đại diện.
7. Lưu lại platform, JDK/GraalVM, Spring Boot và driver version cùng artifact.

Đo startup và memory là cần thiết để xác nhận native image có lợi ích thực tế với workload. Native build tốn thời gian hơn, nên không phải service nào cũng cần native deployment.

## 20. Bài thực hành

1. Tạo Spring Boot application dùng Spring Data JDBC với entity Order có **@Table**.
2. Tạo **OrderRepository** có derived query, **@Query**, **@Modifying** và pagination.
3. Thêm GraalVM Native Build Tools plugin và chạy **processAot**.
4. Quan sát generated source, runtime hints và metadata query repository.
5. Chạy ứng dụng trên JVM với **spring.aot.enabled=true**.
6. Build native executable và chạy với database test.
7. Viết một repository method nhận **ScrollPosition**; xác định giới hạn AOT của method trong phiên bản đang dùng.
8. Tạo custom repository fragment có reflection vào class được xác định từ cấu hình; thử native build và bổ sung hint tối thiểu.
9. Dùng **RuntimeHintsPredicates** để kiểm tra custom hints.
10. Chạy tracing agent qua các luồng repository/query thực tế; review output trước khi đưa vào resource.
11. Kiểm tra JDBC driver và migration resource trong native executable.
12. So sánh startup time, memory footprint và request throughput giữa JVM và native image.

## 21. Ghi nhớ

Spring AOT chuẩn bị ApplicationContext, generated code và runtime hints ở build time. GraalVM Native Image dùng các kết quả đó để tạo executable theo platform. Spring Data JDBC bổ sung AOT repository generation cho derived, annotated và named query methods đủ điều kiện, giúp chuyển một phần phân tích query method sang build time.

AOT repository không thay thế base CRUD implementation, không sinh mọi custom fragment và hiện có giới hạn với **ScrollPosition**/keyset scrolling. Hãy annotate domain types, cấu hình đúng profile và **JdbcDialect**, bổ sung runtime hints cho code/dependency động, rồi kiểm tra AOT trên JVM trước khi build native. Cuối cùng, chạy native integration tests với JDBC driver và database thật; chỉ build thành công chưa đủ để chứng minh ứng dụng hoạt động đúng.

## Tài liệu tham khảo

- [Spring Data Relational — Ahead of Time Optimizations](https://docs.spring.io/spring-data/relational/reference/jdbc/aot.html)
- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot — Ahead-of-Time Processing with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/aot.html)
- [Spring Boot — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Data JDBC — JdbcDialect API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/JdbcDialect.html)
