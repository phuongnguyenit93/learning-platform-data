# Auto-configuration của Spring Boot trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích auto-configuration của Spring Boot giải quyết công việc gì và cách nó hoạt động.
- Hiểu vai trò của starter, classpath, conditional annotation, bean và application properties.
- Mô tả cách Spring Boot tự cấu hình các thành phần nền tảng của Spring for GraphQL.
- Biết schema SDL được tìm thấy, nạp và ghép vào GraphQL runtime như thế nào.
- Cấu hình endpoint GraphQL, transport và các tính năng liên quan bằng application.properties hoặc application.yml.
- Bổ sung resolver, runtime wiring, scalar, instrumentation và customizer mà vẫn tận dụng được cấu hình tự động.
- Nhận biết khi nào auto-configuration lùi lại để nhường quyền cho bean do ứng dụng cung cấp.
- Chẩn đoán trường hợp cấu hình tự động không được kích hoạt hoặc bị vô hiệu hóa ngoài ý muốn.

## 1. Auto-configuration là gì?

Auto-configuration là cơ chế Spring Boot tự động đăng ký các bean và thiết lập hạ tầng ứng dụng dựa trên những gì có trong classpath, các bean đã tồn tại và cấu hình của ứng dụng.

Khi thêm một starter vào dự án, starter đưa các thư viện cần thiết vào classpath. Spring Boot nhận biết những thư viện đó và xem xét các cấu hình tự động tương ứng. Nếu điều kiện phù hợp, Boot đăng ký các bean nền tảng để ứng dụng có thể hoạt động với lượng cấu hình thủ công nhỏ hơn.

Với Spring for GraphQL, auto-configuration giúp ứng dụng có sẵn các thành phần như:

- GraphQL runtime được xây dựng từ schema SDL và runtime wiring.
- Cơ chế kết nối các controller method với field trong schema.
- GraphQL service và web handler phục vụ request.
- Transport phù hợp với stack web đang sử dụng, chẳng hạn Spring MVC hoặc WebFlux.
- Các thành phần hỗ trợ như DataLoader registry và quan sát hoạt động khi có dependency/cấu hình tương ứng.

Auto-configuration không tự thiết kế schema nghiệp vụ, không tự viết resolver cho từng field và cũng không tự quyết định quyền truy cập dữ liệu. Ứng dụng vẫn phải cung cấp schema, controller, service nghiệp vụ và các chính sách phù hợp.

Có thể xem auto-configuration là phần lắp ráp hạ tầng. Nó kết nối những thành phần nền tảng theo các quy ước phổ biến để nhóm phát triển tập trung vào API và nghiệp vụ.

## 2. Starter, dependency và auto-configuration liên hệ với nhau như thế nào?

Trong một dự án Spring Boot, starter thường là dependency tổng hợp. Nó kéo vào các thư viện cần thiết cho một nhóm tính năng.

Ví dụ, dự án sử dụng Spring for GraphQL thường khai báo starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>
~~~

Nếu dùng Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
}
~~~

Nên để Spring Boot quản lý phiên bản dependency thông qua parent/BOM hoặc cơ chế dependency management tương ứng, tránh tự ghim các phiên bản Spring GraphQL và GraphQL Java không tương thích với phiên bản Boot đang dùng.

Thêm starter mới chỉ là bước đưa thư viện vào classpath. Các cấu hình tự động chỉ được áp dụng khi ứng dụng khởi động qua cơ chế Spring Boot và điều kiện của chúng thỏa mãn.

Một số starter liên quan có thể được thêm tùy stack và nhu cầu, chẳng hạn starter web MVC, WebFlux hoặc RSocket. Transport nào được kích hoạt phụ thuộc vào dependency và điều kiện ứng dụng, vì vậy không nên giả định chỉ thêm GraphQL starter là mọi loại transport đều được bật.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Khai báo spring-boot-starter-graphql"] --> B["Các thư viện xuất hiện trong classpath"]
    B --> C["Spring Boot tìm các auto-configuration"]
    C --> D{"Các điều kiện có thỏa mãn?"}
    D -->|Có| E["Đăng ký bean nền tảng"]
    D -->|Không| F["Bỏ qua cấu hình đó"]
    E --> G["Ứng dụng bổ sung schema và resolver"]
    F --> G
    G --> H["GraphQL API sẵn sàng theo cấu hình cuối cùng"]
~~~

## 3. Spring Boot quyết định có áp dụng auto-configuration hay không

Auto-configuration không chạy vô điều kiện. Spring Boot sử dụng các điều kiện để quyết định một cấu hình hoặc bean có được tạo hay không.

### 3.1. Điều kiện trên classpath

**@ConditionalOnClass** kiểm tra một hoặc nhiều class có tồn tại trong classpath hay không.

Ví dụ khái niệm:

~~~java
@AutoConfiguration
@ConditionalOnClass(GraphQlSource.class)
class GraphQlInfrastructureAutoConfiguration {
    // Khai báo các bean GraphQL nền tảng
}
~~~

Nếu ứng dụng không có thư viện cung cấp **GraphQlSource**, cấu hình này không được áp dụng. Điều kiện classpath cho phép một thư viện cung cấp tính năng tùy chọn mà không bắt mọi ứng dụng phải cài tất cả dependency liên quan.

### 3.2. Điều kiện trên bean

**@ConditionalOnMissingBean** chỉ tạo bean mặc định khi chưa có bean phù hợp do ứng dụng hoặc cấu hình khác đăng ký.

~~~java
@Bean
@ConditionalOnMissingBean
GraphQlMetrics graphQlMetrics() {
    return new DefaultGraphQlMetrics();
}
~~~

Ví dụ trên chỉ minh họa cơ chế. Nếu ứng dụng tự đăng ký một bean **GraphQlMetrics**, bean mặc định có thể lùi lại và bean của ứng dụng được sử dụng.

**@ConditionalOnBean** làm điều ngược lại: chỉ áp dụng cấu hình khi một bean phụ thuộc đã tồn tại.

Cơ chế này giúp ứng dụng thay thế từng phần hạ tầng. Tuy nhiên, nếu tự cung cấp một bean ở tầng nền tảng, bạn có thể khiến Boot bỏ qua cả bean mặc định vốn đảm nhiệm nhiều công việc hơn. Hãy hiểu rõ trách nhiệm của bean trước khi thay thế.

### 3.3. Điều kiện trên property

**@ConditionalOnProperty** kiểm tra giá trị cấu hình. Ví dụ một tính năng có thể chỉ được bật khi property được đặt thành **true**.

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.graphql.audit",
        name = "enabled",
        havingValue = "true")
GraphQlAuditListener graphQlAuditListener() {
    return new GraphQlAuditListener();
}
~~~

Đây là ví dụ cho cấu hình riêng của ứng dụng. Với property chuẩn của Spring Boot, hãy sử dụng đúng tên property mà phiên bản Boot đang dùng công bố.

### 3.4. Điều kiện trên môi trường ứng dụng

Boot cũng có các điều kiện để phân biệt ứng dụng web servlet, reactive web, ứng dụng không có web server, hoặc môi trường kiểm thử.

Ví dụ, cấu hình cho Spring MVC chỉ nên được áp dụng khi các class MVC cần thiết có trong classpath và ứng dụng đang chạy theo web application type phù hợp. Cấu hình cho WebFlux có điều kiện tương ứng.

Nhờ đó, cùng một ứng dụng Spring GraphQL có thể chọn transport phù hợp với stack web mà không cần khởi tạo cả hai stack.

### 3.5. Auto-configuration có thứ tự

Các cấu hình tự động có thể khai báo quan hệ trước/sau để bảo đảm bean phụ thuộc được xem xét đúng thời điểm. Những annotation như **@AutoConfigureBefore**, **@AutoConfigureAfter** hoặc thuộc tính **before**/**after** của **@AutoConfiguration** phục vụ mục đích này.

Thứ tự không nên được dùng như một cách chữa mọi vấn đề bean. Nếu hai cấu hình cùng tạo một bean mà không có điều kiện rõ ràng, cần xem lại điều kiện và ranh giới trách nhiệm của chúng.

## 4. Cách Spring Boot phát hiện auto-configuration

Với các phiên bản Spring Boot hiện đại, lớp thư viện auto-configuration công bố danh sách cấu hình thông qua file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File này liệt kê các class được đánh dấu bằng **@AutoConfiguration**. Spring Boot đọc danh sách và đánh giá điều kiện của từng cấu hình trong quá trình khởi tạo application context.

Ở các phiên bản Boot cũ hơn, cơ chế đăng ký auto-configuration sử dụng metadata trong **META-INF/spring.factories**. Khi nâng cấp phiên bản Boot hoặc tự viết thư viện starter, cần tuân theo cơ chế discovery của phiên bản mục tiêu.

Trong ứng dụng sử dụng **@SpringBootApplication**, annotation này bao gồm cơ chế component scanning và bật auto-configuration thông qua **@EnableAutoConfiguration**.

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Không cần thêm **@EnableAutoConfiguration** lần nữa khi đã dùng **@SpringBootApplication**.

Cũng cần phân biệt:

- **Component scanning** tìm các component do ứng dụng khai báo, chẳng hạn **@Controller**, **@Service** và **@Component**.
- **Auto-configuration discovery** tìm các class cấu hình tự động được thư viện công bố.
- **Configuration properties binding** chuyển giá trị từ file cấu hình, biến môi trường hoặc nguồn property khác thành object cấu hình.

Ba cơ chế phối hợp với nhau nhưng có mục đích riêng.

## 5. Auto-configuration của Spring for GraphQL

Khi dependency GraphQL có mặt và ứng dụng khởi động bằng Spring Boot, các cấu hình tự động của GraphQL có thể lắp ráp hạ tầng dựa trên những điều kiện cần thiết.

Ở mức khái niệm, quá trình gồm các phần:

1. Đọc các property thuộc nhóm **spring.graphql**.
2. Tìm các file schema SDL ở vị trí được cấu hình.
3. Xây dựng **GraphQlSource** từ schema và runtime wiring.
4. Đăng ký các thành phần GraphQL cần thiết để thực thi request.
5. Kết nối web handler với transport được ứng dụng hỗ trợ.
6. Bổ sung các thành phần tích hợp khi dependency và điều kiện tương ứng có mặt.

Các tên class nội bộ, điều kiện cụ thể và thứ tự cấu hình có thể thay đổi theo phiên bản Spring Boot. Khi cần xác minh chính xác một bean trong dự án, hãy xem condition report hoặc tài liệu của đúng phiên bản đang sử dụng.

### 5.1. GraphQlSource và schema SDL

Một trong những phần quan trọng nhất của auto-configuration là tạo GraphQL runtime từ schema.

Theo quy ước mặc định, Spring Boot tìm schema trong classpath dưới thư mục:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            └── catalog.graphqls
~~~

Các file có phần mở rộng GraphQL schema được hỗ trợ sẽ được nạp và kết hợp thành schema ứng dụng. Vị trí và phần mở rộng có thể điều chỉnh qua property.

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Sau khi có schema, ứng dụng cần cung cấp DataFetcher cho field **book**. Trong Spring for GraphQL, controller method có thể đảm nhiệm việc đó:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Spring for GraphQL phát hiện controller và đăng ký mapping tương ứng. Auto-configuration cung cấp hạ tầng GraphQL; controller của ứng dụng cung cấp hành vi nghiệp vụ cho field.

### 5.2. RuntimeWiringConfigurer và custom scalar

Khi schema cần scalar hoặc wiring bổ sung, ứng dụng có thể đăng ký **RuntimeWiringConfigurer**.

~~~java
@Configuration
class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> {
            // Đăng ký scalar, type resolver hoặc wiring bổ sung
        };
    }
}
~~~

Đây là điểm mở rộng cho runtime wiring. Boot có thể thu thập các **RuntimeWiringConfigurer** đã đăng ký và áp dụng chúng khi xây dựng GraphQL runtime.

Ví dụ, custom scalar **DateTime** cần serializer và parser phù hợp. Chỉ khai báo **scalar DateTime** trong SDL là chưa đủ để runtime biết cách chuyển đổi giữa biểu diễn GraphQL và kiểu Java.

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

Khi ứng dụng bổ sung scalar, cần bảo đảm tên scalar trong wiring khớp với tên được dùng trong schema.

### 5.3. GraphQlSourceBuilderCustomizer

Trong Spring Boot, **GraphQlSourceBuilderCustomizer** cho phép tùy chỉnh quá trình xây dựng GraphQL source ở mức builder.

Điểm mở rộng này hữu ích khi cần điều chỉnh cấu hình xây dựng runtime mà không thay thế toàn bộ cơ chế auto-configuration.

~~~java
@Bean
GraphQlSourceBuilderCustomizer graphQlSourceBuilderCustomizer() {
    return builder -> {
        // Tùy chỉnh builder của GraphQlSource theo API phiên bản đang dùng
    };
}
~~~

Nội dung tùy chỉnh cụ thể phụ thuộc API builder của phiên bản Spring Boot/Spring GraphQL đang dùng. Không nên sao chép một method từ ví dụ của phiên bản khác mà chưa kiểm tra API hiện hành.

### 5.4. Transport và web handler

Sau khi có GraphQL runtime và execution service, ứng dụng cần một transport để client gửi request.

Với Spring MVC, Boot có thể cấu hình endpoint HTTP GraphQL khi các điều kiện MVC phù hợp. Với WebFlux, Boot có thể cấu hình endpoint reactive tương ứng. Các tích hợp WebSocket hoặc RSocket có điều kiện và property riêng.

Endpoint HTTP mặc định thường là **/graphql**. Có thể đổi đường dẫn bằng:

~~~yaml
spring:
  graphql:
    path: /api/graphql
~~~

Khi đổi path, client phải gửi request đến đường dẫn mới. Nếu dùng reverse proxy hoặc API gateway, cần đồng bộ route bên ngoài với endpoint bên trong ứng dụng.

GraphiQL là giao diện trình duyệt hỗ trợ khám phá và thử GraphQL API. Nó không phải thành phần bắt buộc để API hoạt động và thường được tắt mặc định. Chỉ bật trong môi trường phù hợp và cân nhắc chính sách bảo mật khi triển khai.

## 6. Cấu hình bằng application.properties và application.yml

Spring Boot cung cấp nhóm property **spring.graphql** để cấu hình các phần phổ biến.

Ví dụ YAML:

~~~yaml
spring:
  graphql:
    path: /graphql
    schema:
      locations: classpath:graphql/
      file-extensions: .graphqls,.gqls
    graphiql:
      enabled: false
~~~

Ví dụ tương đương trong **application.properties**:

~~~properties
spring.graphql.path=/graphql
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls
spring.graphql.graphiql.enabled=false
~~~

Ý nghĩa:

| Property | Mục đích |
| --- | --- |
| **spring.graphql.path** | Đường dẫn endpoint HTTP GraphQL |
| **spring.graphql.schema.locations** | Vị trí tìm schema SDL |
| **spring.graphql.schema.file-extensions** | Phần mở rộng file schema được tìm |
| **spring.graphql.graphiql.enabled** | Bật/tắt giao diện GraphiQL khi tích hợp có hỗ trợ |

Tên property và giá trị mặc định cần được đối chiếu với phiên bản Boot của dự án. Khi một property không được phiên bản hiện tại hỗ trợ, việc đặt nó trong file cấu hình có thể không tạo ra hành vi mong muốn.

### 6.1. Tách cấu hình theo môi trường

Không phải môi trường nào cũng nên bật cùng một tính năng. Có thể dùng profile để tách cấu hình:

~~~yaml
# application-dev.yml
spring:
  graphql:
    graphiql:
      enabled: true
~~~

~~~yaml
# application-prod.yml
spring:
  graphql:
    graphiql:
      enabled: false
~~~

Kích hoạt profile qua biến môi trường hoặc tham số chạy ứng dụng:

~~~properties
spring.profiles.active=dev
~~~

Không nên lưu bí mật, token hoặc mật khẩu trong file cấu hình được commit. Dùng biến môi trường, secret manager hoặc cơ chế quản lý cấu hình an toàn của nền tảng triển khai.

## 7. Auto-configuration lùi lại khi ứng dụng tự cung cấp bean

Một nguyên tắc quan trọng của Spring Boot là cấu hình mặc định có thể lùi lại để ứng dụng tùy chỉnh.

Giả sử ứng dụng tự cung cấp một bean **GraphQlSource** được xây dựng từ schema và runtime wiring riêng. Cấu hình tự động tạo **GraphQlSource** mặc định thường có điều kiện chỉ tạo khi chưa có bean tương ứng. Khi tự khai báo bean, method **@Bean** phải trả về một **GraphQlSource** thực sự được xây dựng bằng API phù hợp với phiên bản Spring GraphQL đang dùng.

Khi bean tùy chỉnh xuất hiện, auto-configuration có thể không tạo bean mặc định nữa. Các cấu hình phụ thuộc vào bean đó có thể tiếp tục hoạt động nếu bean thay thế đáp ứng đúng hợp đồng.

### 7.1. Property hay custom bean?

Nên chọn mức tùy chỉnh nhỏ nhất đáp ứng yêu cầu:

| Nhu cầu | Cách cấu hình nên cân nhắc |
| --- | --- |
| Đổi URL GraphQL | Property **spring.graphql.path** |
| Đổi nơi chứa schema | **spring.graphql.schema.locations** |
| Bật/tắt GraphiQL | Property tương ứng |
| Thêm DataFetcher nghiệp vụ | **@Controller**, **@QueryMapping**, **@SchemaMapping** |
| Đăng ký scalar hoặc type resolver | **RuntimeWiringConfigurer** |
| Tùy chỉnh builder tạo GraphQL source | **GraphQlSourceBuilderCustomizer** |
| Thay một bean nền tảng | Tự đăng ký bean tương ứng khi thực sự cần |

Tự khai báo một bean nền tảng có thể làm Boot lùi lại khỏi cấu hình mặc định. Trước khi thay thế, hãy kiểm tra các bean liên quan có còn được tạo và kết nối đúng hay không.

### 7.2. Không nên loại bỏ auto-configuration quá sớm

Spring Boot cho phép loại trừ auto-configuration bằng thuộc tính **exclude** hoặc property loại trừ tương ứng. Tuy nhiên, loại bỏ toàn bộ cấu hình GraphQL có thể khiến nhiều bean nền tảng không còn được đăng ký.

Chỉ dùng exclusion khi thực sự muốn tự quản lý toàn bộ phần cấu hình đó hoặc khi một cấu hình cụ thể gây xung đột đã được xác định rõ.

~~~java
@SpringBootApplication(exclude = SomeAutoConfiguration.class)
class CatalogApplication {
}
~~~

Tên class trong ví dụ là placeholder minh họa; hãy dùng đúng auto-configuration class được công bố bởi thư viện đang sử dụng. Trong nhiều trường hợp, bổ sung một bean hoặc điều chỉnh property là đủ và ít ảnh hưởng hơn.

## 8. Tự viết auto-configuration cho thư viện nội bộ

Khi xây dựng một thư viện dùng lại trong nhiều ứng dụng, có thể tạo auto-configuration riêng. Ví dụ, thư viện muốn cung cấp một bộ quy tắc GraphQL dùng chung.

Một cấu hình tự động cơ bản:

~~~java
@AutoConfiguration
@ConditionalOnClass(GraphQlSource.class)
public class CompanyGraphQlAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CompanyGraphQlPolicy companyGraphQlPolicy() {
        return new DefaultCompanyGraphQlPolicy();
    }
}
~~~

Ý nghĩa:

- **@AutoConfiguration** đánh dấu class là cấu hình tự động của Boot.
- **@ConditionalOnClass** chỉ kích hoạt khi API GraphQL cần thiết có trong classpath.
- **@ConditionalOnMissingBean** cho phép ứng dụng thay thế policy mặc định.

Để Boot phát hiện cấu hình, thư viện cần khai báo class trong file:

~~~text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file là tên đầy đủ của class, mỗi cấu hình một dòng:

~~~text
com.example.graphql.CompanyGraphQlAutoConfiguration
~~~

Một thư viện starter thường tách phần dependency tổng hợp và phần auto-configuration để người dùng có thể thêm tính năng bằng một dependency rõ ràng. Cấu trúc module cụ thể phụ thuộc cách tổ chức thư viện và quy mô dự án.

### 8.1. Dùng configuration properties cho thư viện

Không nên rải các chuỗi cấu hình tùy ý trong nhiều class. Có thể gom cấu hình vào một lớp có **@ConfigurationProperties**.

~~~java
@ConfigurationProperties(prefix = "company.graphql")
public class CompanyGraphQlProperties {

    private boolean auditEnabled;

    public boolean isAuditEnabled() {
        return auditEnabled;
    }

    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }
}
~~~

Auto-configuration có thể bật binding cho lớp này:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(CompanyGraphQlProperties.class)
public class CompanyGraphQlAutoConfiguration {
}
~~~

Ứng dụng sử dụng thư viện có thể cấu hình:

~~~yaml
company:
  graphql:
    audit-enabled: true
~~~

Trong code thực tế, nên cân nhắc dùng constructor binding hoặc record theo phong cách phù hợp với phiên bản Boot mục tiêu, đồng thời cung cấp metadata để IDE gợi ý property.

### 8.2. Kiểm thử auto-configuration

Không nên chỉ kiểm tra rằng application context khởi động thành công. Cần kiểm tra cả điều kiện kích hoạt và hành vi lùi lại.

**ApplicationContextRunner** giúp tạo context nhỏ với auto-configuration mục tiêu:

~~~java
class CompanyGraphQlAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CompanyGraphQlAutoConfiguration.class));

    @Test
    void createsDefaultPolicyWhenMissing() {
        this.contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(CompanyGraphQlPolicy.class);
        });
    }

    @Test
    void backsOffWhenApplicationDefinesPolicy() {
        this.contextRunner
                .withBean(CompanyGraphQlPolicy.class,
                        () -> new CustomCompanyGraphQlPolicy())
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(CompanyGraphQlPolicy.class);
                    assertThat(context.getBean(CompanyGraphQlPolicy.class))
                            .isInstanceOf(CustomCompanyGraphQlPolicy.class);
                });
    }
}
~~~

Tên class trong ví dụ là các kiểu do thư viện minh họa định nghĩa. Trong test thực tế, cần bổ sung các điều kiện classpath, property và bean phụ thuộc để phản ánh đúng hợp đồng của auto-configuration.

## 9. Chẩn đoán auto-configuration

Khi endpoint GraphQL không xuất hiện hoặc một bean mong đợi không được tạo, hãy kiểm tra theo thứ tự.

### 9.1. Xác nhận dependency

Kiểm tra starter và dependency quản lý phiên bản có đúng hay không. Nếu class GraphQL cần thiết không có trong classpath, điều kiện **@ConditionalOnClass** sẽ không thỏa mãn.

Có thể xem dependency tree bằng Maven:

~~~bash
./mvnw dependency:tree
~~~

Hoặc Gradle:

~~~bash
./gradlew dependencies
~~~

Lệnh cụ thể có thể khác theo hệ điều hành và cấu trúc dự án.

### 9.2. Bật condition evaluation report

Chạy ứng dụng với tham số **--debug** để Spring Boot in báo cáo điều kiện auto-configuration:

~~~bash
java -jar app.jar --debug
~~~

Báo cáo giúp phân biệt:

- Cấu hình nào đã được áp dụng.
- Cấu hình nào bị bỏ qua.
- Điều kiện nào không thỏa mãn.
- Bean nào đã tồn tại khiến cấu hình mặc định lùi lại.

Nếu ứng dụng có Spring Boot Actuator và endpoint điều kiện được bật, có thể sử dụng endpoint **conditions** để xem báo cáo tương ứng. Endpoint quản trị cần được bảo vệ và chỉ công bố theo chính sách vận hành.

### 9.3. Kiểm tra schema location

Nếu ứng dụng khởi động nhưng GraphQL schema không được nạp như mong đợi:

- Kiểm tra file nằm trong **src/main/resources/graphql/** hoặc vị trí đã cấu hình.
- Kiểm tra phần mở rộng file được hỗ trợ.
- Kiểm tra cú pháp SDL và các type tham chiếu.
- Kiểm tra log khởi động để tìm lỗi parse hoặc validation schema.
- Kiểm tra property có bị profile hoặc biến môi trường ghi đè không.

### 9.4. Kiểm tra web application type

Nếu GraphQL runtime tồn tại nhưng endpoint HTTP không được đăng ký, hãy kiểm tra stack web:

- Dự án có dependency Spring MVC hoặc WebFlux phù hợp không?
- Có vô tình đưa cả hai stack vào classpath khiến Boot chọn loại ứng dụng khác dự kiến không?
- Có cấu hình **spring.main.web-application-type** ghi đè loại ứng dụng không?
- Có property endpoint hoặc path tùy chỉnh không?
- Có exclusion nào vô hiệu hóa cấu hình transport không?

Không nên sửa resolver hoặc schema khi nguyên nhân thực tế nằm ở transport.

## 10. Ví dụ cấu hình một ứng dụng GraphQL nhỏ

Giả sử xây dựng API tra cứu sách. Ứng dụng cần một schema, một controller và một file cấu hình.

Cấu trúc:

~~~text
src/
├── main/
│   ├── java/com/example/catalog/
│   │   ├── CatalogApplication.java
│   │   ├── BookController.java
│   │   └── BookService.java
│   └── resources/
│       ├── application.yml
│       └── graphql/
│           └── schema.graphqls
└── test/
    └── java/com/example/catalog/
~~~

Schema:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Cấu hình:

~~~yaml
spring:
  graphql:
    path: /graphql
    schema:
      locations: classpath:graphql/
~~~

Controller:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Ứng dụng khởi động qua **SpringApplication.run(...)**. Spring Boot phát hiện starter và các dependency cần thiết, nạp schema, tạo GraphQL runtime, kết nối controller với field và đăng ký transport tương ứng.

Client có thể gửi:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42"
}
~~~

Điểm cần nhớ là file cấu hình chỉ điều chỉnh hạ tầng; schema xác định hợp đồng API; controller và service cung cấp hành vi nghiệp vụ. Auto-configuration lắp ráp các phần đó thành ứng dụng có thể nhận và thực thi GraphQL request.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không có GraphQL endpoint | Thiếu starter, thiếu stack web hoặc auto-configuration bị loại trừ | Kiểm tra dependency tree và condition report |
| Schema không được nạp | File sai vị trí, sai extension hoặc property location không đúng | Kiểm tra **spring.graphql.schema.*** và log khởi động |
| Field có trong SDL nhưng không có dữ liệu | Chưa đăng ký DataFetcher/controller mapping hoặc resolver lỗi | Kiểm tra **@QueryMapping**, **@SchemaMapping** và service |
| Bean mặc định không xuất hiện | Có bean tùy chỉnh khiến **@ConditionalOnMissingBean** lùi lại | Kiểm tra context và condition report |
| GraphiQL không truy cập được | Tính năng đang tắt hoặc dependency/tích hợp tương ứng không có | Kiểm tra property và transport |
| Endpoint chạy sai path | Property bị profile hoặc biến môi trường ghi đè | Kiểm tra effective configuration |
| MVC/WebFlux không hoạt động như dự kiến | Web application type hoặc dependency không phù hợp | Kiểm tra classpath và **spring.main.web-application-type** |
| Nâng cấp Boot làm thay đổi auto-configuration | Điều kiện, property hoặc cơ chế đăng ký thay đổi theo phiên bản | Đọc migration guide và kiểm tra report của phiên bản mới |

## 12. Nguyên tắc sử dụng auto-configuration

Khi phát triển ứng dụng Spring for GraphQL, hãy áp dụng các nguyên tắc sau:

1. Bắt đầu bằng starter tương thích với phiên bản Spring Boot đang sử dụng.
2. Để Boot tạo hạ tầng mặc định nếu chưa có nhu cầu tùy chỉnh.
3. Đặt schema trong resource location theo quy ước hoặc cấu hình rõ vị trí.
4. Dùng **application.yml**/**application.properties** cho các giá trị cấu hình được hỗ trợ.
5. Dùng **@Controller**, **@QueryMapping**, **@SchemaMapping** cho hành vi nghiệp vụ của field.
6. Dùng **RuntimeWiringConfigurer** và customizer khi cần mở rộng GraphQL runtime.
7. Chỉ thay bean nền tảng khi hiểu rõ bean mặc định đang đảm nhiệm điều gì.
8. Dùng condition report để chẩn đoán thay vì đoán nguyên nhân từ một biểu hiện bên ngoài.
9. Khi nâng cấp Spring Boot, kiểm tra lại property, điều kiện và auto-configuration discovery theo phiên bản mới.
10. Viết test cho cả trường hợp cấu hình được áp dụng và trường hợp Boot lùi lại khi ứng dụng cung cấp bean riêng.

Auto-configuration giúp giảm mã cấu hình, nhưng không thay thế việc hiểu kiến trúc. Khi nắm được classpath, conditions, properties, bean và extension point, bạn có thể tùy chỉnh ứng dụng có kiểm soát mà vẫn giữ được lợi ích từ Spring Boot.

## 13. Tổng kết

Auto-configuration của Spring Boot lắp ráp các bean và hạ tầng dựa trên dependency có trong classpath, property và bean đã tồn tại. Với Spring for GraphQL, cơ chế này giúp nạp schema, xây dựng GraphQL runtime, kết nối resolver và cấu hình transport phù hợp với ứng dụng.

Ứng dụng thường chỉ cần thêm starter, đặt schema vào resource, khai báo controller và cấu hình các property cần thiết. Khi cần mở rộng, hãy ưu tiên extension point chuyên biệt như **RuntimeWiringConfigurer**, **GraphQlSourceBuilderCustomizer** hoặc bean có điều kiện phù hợp. Condition evaluation report và test với **ApplicationContextRunner** giúp xác minh vì sao cấu hình được áp dụng hoặc lùi lại.

Hiểu cách Boot quyết định cấu hình nào được kích hoạt là nền tảng để xây dựng, tùy chỉnh và chẩn đoán một ứng dụng Spring for GraphQL ổn định.

