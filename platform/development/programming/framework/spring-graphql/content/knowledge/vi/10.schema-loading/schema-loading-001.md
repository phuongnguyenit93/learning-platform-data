# SchemaResourceBuilder trong Spring for GraphQL

`SchemaResourceBuilder` là builder của Spring for GraphQL dùng để tạo `GraphQlSource` từ một hoặc nhiều schema resource. Nó nhận các đối tượng `Resource` của Spring, đọc nội dung SDL, kết hợp các định nghĩa thành một schema GraphQL và cho phép cấu hình runtime wiring trước khi build.

Builder này hữu ích khi ứng dụng cần tự kiểm soát danh sách file schema, nạp schema từ classpath hoặc filesystem, hoặc tạo `GraphQlSource` ngoài cơ chế auto-configuration của Spring Boot. Nếu chỉ cần đổi thư mục schema trong một ứng dụng Spring Boot thông thường, properties của starter thường đã đủ; hiểu rõ builder giúp chọn đúng mức cấu hình và tránh vô tình bỏ qua các thành phần runtime mà Boot đã thiết lập.

## 1. GraphQlSource và SchemaResourceBuilder

Spring for GraphQL dùng `GraphQlSource` để cung cấp GraphQL schema và runtime được tạo từ schema đó. `GraphQlSource` là đầu vào cho `ExecutionGraphQlService`, thành phần thực thi operation và điều phối các data fetcher.

`GraphQlSource` cung cấp factory method:

~~~java
GraphQlSource.schemaResourceBuilder()
~~~

Method này trả về `GraphQlSource.SchemaResourceBuilder`. Builder nhận các schema resource và kế thừa các khả năng cấu hình chung của `GraphQlSource.Builder`.

Một luồng tạo schema điển hình:

~~~mermaid
flowchart TD
    A[Spring Resource objects] --> B[SchemaResourceBuilder]
    B --> C[Read SDL resources]
    C --> D[Parse type definitions]
    D --> E[Merge schema definitions and extensions]
    E --> F[Build GraphQLSchema]
    G[RuntimeWiringConfigurer] --> H[RuntimeWiring]
    F --> I[GraphQL runtime]
    H --> I
    I --> J[GraphQlSource]
    J --> K[ExecutionGraphQlService]
~~~

Các bước trên mô tả vai trò khái quát. Builder phối hợp schema definition với runtime wiring để tạo GraphQL runtime hoàn chỉnh. SDL mô tả type và field; runtime wiring cung cấp cách thực thi field, scalar, type resolver và các thành phần liên quan.

## 2. Tạo GraphQlSource từ một resource

Nếu schema chỉ có một file, có thể tạo builder và truyền `ClassPathResource`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlSourceConfiguration {

    @Bean
    GraphQlSource graphQlSource() {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls")
                )
                .build();
    }
}
~~~

`schemaResources(...)` nhận các đối tượng `Resource` của Spring. `ClassPathResource` trỏ đến file nằm trên classpath, thường được đặt trong `src/main/resources`. Đường dẫn truyền vào `ClassPathResource` là đường dẫn tương đối với classpath, không phải đường dẫn tuyệt đối trên máy phát triển.

Ví dụ file `src/main/resources/graphql/schema.graphqls`:

~~~graphql
type Query {
    apiVersion: String!
    greeting(name: String!): String!
}
~~~

Khi ứng dụng khởi động, builder đọc file, parse SDL và tạo schema. Nếu resource không tồn tại hoặc SDL không hợp lệ, quá trình tạo `GraphQlSource` thất bại; ứng dụng nên phát hiện lỗi này ngay lúc khởi động thay vì đợi client gửi request.

## 3. Nạp nhiều schema resource

Trong ứng dụng lớn, schema thường được chia theo domain. `SchemaResourceBuilder` cho phép truyền nhiều resource trong cùng một lần gọi:

~~~java
@Bean
GraphQlSource graphQlSource() {
    return GraphQlSource.schemaResourceBuilder()
            .schemaResources(
                    new ClassPathResource("graphql/schema.graphqls"),
                    new ClassPathResource("graphql/book/book.graphqls"),
                    new ClassPathResource("graphql/author/author.graphqls"),
                    new ClassPathResource("graphql/member/member.graphqls")
            )
            .build();
}
~~~

Các file ví dụ:

`graphql/schema.graphqls` khai báo root type:

~~~graphql
type Query {
    apiVersion: String!
}
~~~

`graphql/book/book.graphqls` khai báo type và mở rộng query:

~~~graphql
type Book {
    id: ID!
    title: String!
}

extend type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

`graphql/author/author.graphqls` khai báo domain tác giả:

~~~graphql
type Author {
    id: ID!
    name: String!
}

extend type Query {
    author(id: ID!): Author
    authors: [Author!]!
}
~~~

Sau khi build, các định nghĩa trên tạo thành một `GraphQLSchema` duy nhất. Client vẫn gửi query đến một GraphQL endpoint và có thể chọn field từ nhiều domain trong cùng operation.

## 4. Spring Resource và cách chọn nguồn schema

`SchemaResourceBuilder` làm việc với abstraction `org.springframework.core.io.Resource`, vì vậy nguồn schema không bị giới hạn ở classpath.

| Resource | Nguồn dữ liệu | Trường hợp sử dụng |
| --- | --- | --- |
| `ClassPathResource` | Resource được đóng gói trên classpath | Schema nằm trong `src/main/resources` hoặc trong dependency JAR |
| `FileSystemResource` | File trên filesystem | Schema được mount hoặc đặt ngoài artifact ứng dụng |
| `UrlResource` | Resource có URL | Schema được cung cấp qua URL mà ứng dụng có quyền truy cập |
| `ByteArrayResource` | Mảng byte trong bộ nhớ | Kiểm thử hoặc trường hợp schema được tạo trong runtime |

Ví dụ dùng file ngoài classpath:

~~~java
import org.springframework.core.io.FileSystemResource;

GraphQlSource source = GraphQlSource.schemaResourceBuilder()
        .schemaResources(
                new FileSystemResource("/opt/app/graphql/schema.graphqls")
        )
        .build();
~~~

Đường dẫn filesystem phụ thuộc môi trường triển khai. Nếu schema cần đi cùng ứng dụng và chạy ổn định trong JAR, nên đặt trong classpath. Nếu schema được quản lý bên ngoài artifact, cần bảo đảm file tồn tại, quyền đọc và phiên bản schema tương thích với phiên bản ứng dụng.

## 5. Dùng ResourcePatternResolver để nạp theo pattern

`SchemaResourceBuilder.schemaResources(...)` nhận các `Resource` cụ thể; nó không phải API tự quét thư mục bằng wildcard. Khi muốn lấy tất cả file SDL trong các thư mục con, dùng `ResourcePatternResolver` để tìm resource trước, sau đó truyền mảng kết quả cho builder.

~~~java
import java.io.IOException;

import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlResourcePatternConfiguration {

    @Bean
    GraphQlSource graphQlSource() throws IOException {
        ResourcePatternResolver resolver =
                new PathMatchingResourcePatternResolver();

        Resource[] resources = resolver.getResources(
                "classpath*:graphql/**/*.graphqls"
        );

        if (resources.length == 0) {
            throw new IllegalStateException(
                    "No GraphQL schema resources found"
            );
        }

        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(resources)
                .build();
    }
}
~~~

Pattern `classpath*:graphql/**/*.graphqls` tìm các file `.graphqls` trong thư mục `graphql` và các thư mục con trên toàn bộ classpath. Prefix `classpath*:` hữu ích khi resource có thể nằm trong nhiều classpath root hoặc dependency JAR. Nếu ứng dụng dùng cả `.gqls`, hãy tìm thêm phần mở rộng đó và gộp kết quả trước khi truyền vào builder.

Không nên quét quá rộng như `classpath*:**/*.graphqls`, vì có thể vô tình nạp schema của thư viện hoặc module không thuộc API hiện tại. Hãy giới hạn pattern trong một namespace rõ ràng, ví dụ `graphql/**`.

## 6. Phân biệt resource pattern với schema locations của Spring Boot

Khi dùng `spring-boot-starter-graphql`, Spring Boot tự cấu hình `GraphQlSource` và tìm schema theo `spring.graphql.schema.locations`. Mặc định, schema thường được tìm trong `classpath:graphql/**/` với phần mở rộng `.graphqls` và `.gqls`.

Ví dụ cấu hình:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
      file-extensions: .graphqls,.gqls
~~~

Nếu schema nằm trong thư mục khác:

~~~yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
        - classpath:shared-graphql/**/
~~~

Hai cách cấu hình có mục đích khác nhau:

| Cách | Vai trò |
| --- | --- |
| `spring.graphql.schema.locations` | Khai báo vị trí/pattern để Spring Boot auto-configuration tìm schema resource |
| `ResourcePatternResolver` | Tự tìm `Resource` theo pattern trong code Java |
| `SchemaResourceBuilder.schemaResources(...)` | Nhận các `Resource` đã xác định và tạo `GraphQlSource` |

Nếu chỉ cần thêm thư mục schema cho ứng dụng Boot, hãy dùng properties trước. Tự tạo `GraphQlSource` bean chỉ cần thiết khi muốn kiểm soát trực tiếp việc tạo source hoặc đang xây dựng ứng dụng không dùng auto-configuration.

## 7. SchemaResourceBuilder và RuntimeWiring

Schema resource chỉ chứa định nghĩa SDL. Để GraphQL thực thi được field, runtime cần `RuntimeWiring` tương ứng. Spring for GraphQL cung cấp `RuntimeWiringConfigurer` để đăng ký scalar, data fetcher, directive wiring và type resolver.

Ví dụ cấu hình scalar `DateTime` trong lúc build source:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.graphql.execution.GraphQlSource;

GraphQlSource source = GraphQlSource.schemaResourceBuilder()
        .schemaResources(
                new ClassPathResource("graphql/schema.graphqls")
        )
        .configureRuntimeWiring(wiring ->
                wiring.scalar(ExtendedScalars.DateTime)
        )
        .build();
~~~

Với ứng dụng Spring Boot, các bean `RuntimeWiringConfigurer` thường được auto-configuration thu thập và áp dụng. Khi tự tạo `GraphQlSource`, cần chủ động đưa các configurer cần thiết vào builder. Ví dụ dưới đây áp dụng các configurer theo thứ tự Spring:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
GraphQlSource graphQlSource(
        ObjectProvider<RuntimeWiringConfigurer> configurers
) {
    GraphQlSource.SchemaResourceBuilder builder =
            GraphQlSource.schemaResourceBuilder()
                    .schemaResources(
                            new ClassPathResource("graphql/schema.graphqls"),
                            new ClassPathResource("graphql/book/book.graphqls")
                    );

    configurers.orderedStream()
            .forEach(builder::configureRuntimeWiring);

    return builder.build();
}
~~~

Đoạn code minh họa cách áp dụng các bean configurer hiện có, bao gồm những configurer đăng ký controller nếu chúng đã được cấu hình trong application context. Khi tự thay thế GraphQlSource mặc định, hãy kiểm tra rõ các bean runtime wiring cần được đưa vào builder; nếu bỏ sót `AnnotatedControllerConfigurer`, các method `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping` có thể không được đăng ký thành data fetcher.

## 8. Các cấu hình khác trên builder

`SchemaResourceBuilder` kế thừa các điểm cấu hình của `GraphQlSource.Builder`. Ngoài `schemaResources(...)`, một số API thường dùng gồm:

| API | Mục đích |
| --- | --- |
| `configureRuntimeWiring(...)` | Áp dụng một hoặc nhiều `RuntimeWiringConfigurer` |
| `defaultTypeResolver(...)` | Cung cấp type resolver mặc định cho interface và union |
| `schemaFactory(...)` | Tùy chỉnh cách tạo `GraphQLSchema` từ type definition registry và runtime wiring |
| `configureGraphQl(...)` | Điều chỉnh `GraphQL.Builder` trước khi tạo runtime |
| `instrumentation(...)` | Đăng ký GraphQL Java instrumentation |
| `exceptionResolvers(...)` | Cấu hình các resolver xử lý exception của data fetcher |
| `subscriptionExceptionResolvers(...)` | Cấu hình xử lý lỗi của subscription publisher |
| `inspectSchemaMappings(...)` | Kiểm tra schema mapping và báo cáo các điểm chưa khớp |

Không cần cấu hình mọi API cho mỗi ứng dụng. Chọn extension point theo nhu cầu: scalar và type resolver thuộc runtime wiring; schema factory chỉ cần khi muốn thay đổi quá trình tạo schema; instrumentation dùng cho quan sát hoặc điều chỉnh execution; schema inspection giúp phát hiện mapping sai trong lúc khởi động.

## 9. Tổ chức SDL để builder hợp nhất chính xác

Khi nạp nhiều resource, GraphQL vẫn validate kết quả như một schema duy nhất. Việc tách file không tạo namespace riêng cho từng domain.

Một cấu trúc thường dùng:

~~~text
src/main/resources/
└── graphql/
    ├── schema.graphqls
    ├── common/
    │   ├── scalars.graphqls
    │   └── enums.graphqls
    ├── book/
    │   ├── book.graphqls
    │   └── book-mutation.graphqls
    └── author/
        └── author.graphqls
~~~

Các quy tắc cần giữ:

1. Mỗi object type, input type, enum, scalar và directive chỉ có một định nghĩa gốc.
2. Dùng `extend type Query` hoặc `extend type Mutation` để domain bổ sung field vào root type đã khai báo.
3. Type extension phải có type gốc tương ứng trong schema tổng hợp.
4. Không để trùng field name trong cùng một object type.
5. Các custom scalar được khai báo trong SDL phải có implementation trong runtime wiring.
6. Không dựa vào thứ tự tên file để giải quyết phụ thuộc giữa type; schema tổng hợp phải hợp lệ sau khi tất cả resource được nạp.

Ví dụ file nền tảng khai báo root type:

~~~graphql
type Query {
    apiVersion: String!
}
~~~

File domain sách mở rộng root type:

~~~graphql
type Book {
    id: ID!
    title: String!
}

extend type Query {
    books: [Book!]!
}
~~~

Nếu `book.graphqls` có `extend type Query` nhưng không có resource nào khai báo `type Query`, quá trình parse/validation sẽ thất bại. Vì vậy cần kiểm tra cả tập resource được tìm thấy, không chỉ kiểm tra riêng từng file.

## 10. Tự tạo GraphQlSource có thay thế auto-configuration không?

Trong Spring Boot, `GraphQlSource` mặc định được tạo theo điều kiện thiếu bean cùng loại. Khi ứng dụng khai báo một `GraphQlSource` bean riêng, auto-configuration tạo source mặc định có thể lùi lại.

Điều này có nghĩa ứng dụng tự chịu trách nhiệm tạo schema và cấu hình runtime wiring cho source đó. Những cấu hình trước đây được Boot áp dụng qua properties hoặc các bean extension cần được kiểm tra lại, đặc biệt:

- Các `RuntimeWiringConfigurer`, bao gồm controller configurer.
- Custom scalar và type resolver.
- Instrumentation và exception resolver.
- Schema inspection hoặc schema factory tùy chỉnh.
- Các resource locations và phần mở rộng file.

Nếu mục tiêu chỉ là thêm một scalar hoặc bật schema inspection, thường nên giữ auto-configuration và dùng bean `RuntimeWiringConfigurer` hoặc `GraphQlSourceBuilderCustomizer`. Tự tạo `GraphQlSource` là thay đổi rộng hơn vì ứng dụng kiểm soát trực tiếp bước build.

## 11. Kiểm thử SchemaResourceBuilder

Có thể kiểm tra trực tiếp schema được tạo từ các resource. Ví dụ với JUnit và AssertJ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

import static org.assertj.core.api.Assertions.assertThat;

class GraphQlSourceBuilderTests {

    @Test
    void buildsSchemaFromMultipleResources() {
        GraphQlSource source = GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls"),
                        new ClassPathResource("graphql/book/book.graphqls"),
                        new ClassPathResource("graphql/author/author.graphqls")
                )
                .build();

        assertThat(source.schema().getType("Query")).isNotNull();
        assertThat(source.schema().getType("Book")).isNotNull();
        assertThat(source.schema().getType("Author")).isNotNull();
    }
}
~~~

Các file schema trên phải nằm trong `src/test/resources` hoặc `src/main/resources` của test runtime. Test này xác nhận builder đã đọc và hợp nhất các type. Nếu cần xác nhận resolver hoạt động, hãy bổ sung integration test với `ExecutionGraphQlService` hoặc test slice Spring for GraphQL để thực thi một operation.

Với ứng dụng Spring Boot, `@GraphQlTest` có thể kiểm tra schema và controller trong test slice:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@GraphQlTest(BookController.class)
class BookSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void exposesBookFieldFromDomainSchema() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isEmpty());
    }
}
~~~

Test này giả định `BookController` và dependency của nó đã có trong test slice hoặc được mock phù hợp. Nếu chỉ muốn kiểm tra schema parse, bài test builder trực tiếp phía trên ít phụ thuộc hơn.

## 12. Lỗi thường gặp khi nạp schema resource

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy schema resource | Sai classpath path hoặc resource chưa được đóng gói | Kiểm tra vị trí `src/main/resources` và tên file |
| Builder nhận mảng resource rỗng | Pattern không khớp hoặc dùng sai prefix | Kiểm tra `classpath:`/`classpath*:` và phần mở rộng |
| `Type ... not found` | Thiếu resource định nghĩa type được tham chiếu | Bổ sung resource hoặc sửa tên type |
| `Cannot extend type ... because it is not defined` | Có type extension nhưng thiếu type gốc | Khai báo root/object type gốc trong một resource được nạp |
| Duplicate type hoặc field | Nhiều file định nghĩa trùng tên | Chỉ giữ một định nghĩa gốc và dùng type extension hợp lệ |
| Schema build thành công nhưng resolver không chạy | Runtime wiring chưa đăng ký data fetcher/controller configurer | Đưa các `RuntimeWiringConfigurer` cần thiết vào builder |
| Custom scalar không parse được | SDL có scalar nhưng runtime wiring chưa đăng ký implementation | Thêm scalar implementation vào runtime wiring |
| Chạy IDE được nhưng JAR lỗi | Dùng filesystem path phụ thuộc máy hoặc resource không được đóng gói | Dùng classpath resource hoặc cấu hình external resource rõ ràng |
| Custom GraphQlSource làm mất cấu hình Boot | Auto-configuration đã lùi khi có bean source riêng | Áp dụng lại properties và các runtime wiring cần thiết trong builder |

Khi chẩn đoán, nên kiểm tra số lượng và tên resource tìm được trước, sau đó kiểm tra lỗi SDL và cuối cùng là runtime wiring. Ba giai đoạn này giúp phân biệt lỗi tìm file, lỗi schema và lỗi thực thi.

## 13. Quy trình lựa chọn cách nạp schema

Khi xây dựng GraphQL API với Spring for GraphQL, có thể chọn cách nạp schema theo nhu cầu:

1. Với ứng dụng Spring Boot thông thường, đặt SDL trong `src/main/resources/graphql` và dùng auto-configuration.
2. Khi chỉ cần đổi thư mục hoặc thêm thư mục schema, cấu hình `spring.graphql.schema.locations`.
3. Khi cần tự tìm resource bằng wildcard, dùng `ResourcePatternResolver` để lấy `Resource[]` rồi truyền vào `schemaResources(...)`.
4. Khi cần chỉ định chính xác một vài file, dùng `ClassPathResource`, `FileSystemResource` hoặc loại `Resource` phù hợp.
5. Khi tự build `GraphQlSource`, áp dụng các `RuntimeWiringConfigurer` cần thiết và kiểm tra controller, scalar, type resolver, exception resolver.
6. Kiểm thử cả schema tổng hợp lẫn operation thực tế; kiểm tra thêm cách resource được đóng gói trong JAR.

`SchemaResourceBuilder` là điểm vào trực tiếp để biến các Spring `Resource` chứa SDL thành một `GraphQlSource`. Khi phân biệt rõ việc tìm resource, hợp nhất schema và cấu hình runtime wiring, ứng dụng có thể tổ chức schema theo domain hoặc theo môi trường triển khai mà vẫn giữ một GraphQL schema thống nhất.

## Tài liệu tham khảo

- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Framework — Resource abstraction](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Framework — Resource pattern resolution](https://docs.spring.io/spring-framework/reference/core/resources.html#resources-resourceloader)
