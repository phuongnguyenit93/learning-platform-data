# Schema inspection trước khi chạy

Trong Spring for GraphQL, schema là hợp đồng mô tả những query, mutation, subscription, object type, input, scalar và kiểu trừu tượng mà API cung cấp. Trước khi ứng dụng nhận request, cần kiểm tra schema đã được nạp đầy đủ, có cấu trúc hợp lệ và chứa những thành phần mà ứng dụng mong đợi.

**Schema inspection** là việc kiểm tra schema sau khi các tệp SDL đã được tìm thấy và kết hợp thành GraphQL schema có thể thực thi. Việc này giúp phát hiện sớm lỗi như thiếu type, sai root field, thiếu field quan trọng hoặc thay đổi hợp đồng ngoài dự kiến. Với Spring for GraphQL, có thể kiểm tra schema được tạo qua `GraphQlSource`, kiểm tra quy tắc riêng của ứng dụng khi Spring khởi tạo context và dùng `GraphQlTester` để xác minh hành vi thực tế.

## 1. Vì sao cần kiểm tra schema trước khi chạy API?

Một ứng dụng có thể có nhiều tệp SDL, ví dụ tách `Query`, `Mutation`, type theo miền nghiệp vụ và các phần mở rộng. Việc các tệp tồn tại trên đĩa chưa bảo đảm schema cuối cùng đã đúng.

Những vấn đề thường gặp gồm:

- Một tệp SDL không nằm trong resource pattern mà ứng dụng cấu hình nên không được nạp.
- Một type hoặc scalar được tham chiếu nhưng chưa được định nghĩa.
- Nhiều tệp định nghĩa trùng type hoặc field, hoặc mở rộng type không đúng cú pháp.
- Root type hoặc field cần thiết bị đổi tên hay bị xóa.
- Union, interface hoặc custom scalar chưa có cách phân giải/đăng ký phù hợp.
- Schema vẫn hợp lệ về cú pháp nhưng không còn khớp với resolver hoặc hợp đồng mà client đang sử dụng.

Schema inspection giúp phát hiện các lỗi cấu trúc và các điều kiện nghiệp vụ của schema ngay khi khởi động hoặc trong kiểm thử. Điều này đặc biệt quan trọng với module Spring for GraphQL, nơi schema SDL, resolver, directive và các thành phần runtime wiring cùng tạo nên API.

## 2. Schema được hình thành qua những bước nào?

Trong cấu hình Spring Boot thông thường, quá trình xây dựng schema có thể tóm tắt như sau:

```text
Tệp SDL trong resources
        |
        v
Tìm tài nguyên theo schema locations
        |
        v
Đọc và phân tích SDL
        |
        v
Kết hợp type definitions và extensions
        |
        v
Áp dụng RuntimeWiringConfigurer
        |
        v
Tạo GraphQLSchema / GraphQlSource
        |
        v
Kiểm tra schema và quy tắc của ứng dụng
        |
        v
GraphQL endpoint sẵn sàng phục vụ request
```

Spring Boot thường tìm schema trong `classpath:graphql/**/`, với các phần mở rộng phổ biến như `.graphqls` và `.gqls`. Các vị trí này có thể được tùy chỉnh bằng `spring.graphql.schema.locations`.

Ví dụ cấu hình nhiều thư mục schema:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/common/**/
        - classpath:graphql/catalog/**/
        - classpath:graphql/order/**/
```

Khi khai báo danh sách location riêng, hãy liệt kê đầy đủ những thư mục ứng dụng cần nạp. Không mặc định rằng location mặc định vẫn được cộng thêm vào danh sách mới.

Sau khi SDL được nạp, GraphQL Java xây dựng `GraphQLSchema` và kết hợp runtime wiring. Spring for GraphQL dùng `GraphQlSource` làm nguồn cung cấp schema và đối tượng thực thi GraphQL. Vì vậy, kiểm tra `GraphQlSource.schema()` cho phép xem schema hiệu lực sau khi các resource và cấu hình đã được áp dụng.

## 3. Phân biệt kiểm tra SDL và kiểm tra schema hiệu lực

Hai việc này có liên quan nhưng không giống nhau:

| Nội dung kiểm tra | Kiểm tra SDL/resource | Kiểm tra schema hiệu lực |
|---|---|---|
| Câu hỏi | Tệp nào tồn tại, cú pháp SDL có đúng không? | Schema cuối cùng mà GraphQL sẽ sử dụng có những type và field nào? |
| Đầu vào | Tệp `.graphqls`, `.gqls` và resource locations | `GraphQLSchema` sau khi Spring/GraphQL Java xây dựng |
| Phát hiện | Sai cú pháp, thiếu file, sai pattern, lỗi extension | Thiếu root field, thiếu type, sai nullability, thiếu thành viên union hoặc sai cấu trúc sau khi kết hợp |
| Công cụ | Kiểm tra resource, parser SDL, build startup | `GraphQlSource.schema()`, GraphQL Java API, `SchemaPrinter`, `GraphQlTester` |

Một tệp SDL có thể hợp lệ riêng lẻ nhưng schema kết hợp vẫn có vấn đề, chẳng hạn một phần mở rộng tham chiếu type không tồn tại. Ngược lại, chỉ nhìn vào `GraphQLSchema` không cho biết chính xác tệp nguồn nào đã cung cấp từng định nghĩa. Khi điều tra lỗi nạp schema, nên kiểm tra cả resource locations lẫn schema cuối cùng.

## 4. Lấy schema hiệu lực từ `GraphQlSource`

Spring for GraphQL cung cấp `GraphQlSource`, trong đó `schema()` trả về `GraphQLSchema` đã được xây dựng. Có thể inject bean này vào một thành phần kiểm tra:

```java
import graphql.schema.GraphQLObjectType;
import graphql.schema.GraphQLSchema;
import graphql.schema.GraphQLType;
import org.springframework.graphql.GraphQlSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.InitializingBean;

@Configuration
class GraphQlSchemaInspectionConfiguration {

    @Bean
    InitializingBean inspectGraphQlSchema(GraphQlSource graphQlSource) {
        return () -> {
            GraphQLSchema schema = graphQlSource.schema();

            GraphQLObjectType queryType = schema.getQueryType();
            if (queryType == null) {
                throw new IllegalStateException("GraphQL Query root type is missing");
            }

            GraphQLType book = schema.getType("Book");
            if (!(book instanceof GraphQLObjectType)) {
                throw new IllegalStateException("Expected GraphQL object type Book");
            }

            GraphQLObjectType bookType = (GraphQLObjectType) book;
            if (bookType.getFieldDefinition("id") == null) {
                throw new IllegalStateException("Required field Book.id is missing");
            }
        };
    }
}
```

Ví dụ này kiểm tra ba điều kiện của ứng dụng: có query root, có object type `Book` và `Book` có field `id`. Nếu điều kiện không thỏa, bean khởi tạo thất bại và Spring không hoàn tất quá trình khởi tạo application context.

Đây là các kiểm tra theo hợp đồng riêng của ứng dụng. Một API khác có thể cần kiểm tra `Product`, `Order`, `Mutation.createOrder` hoặc một union member cụ thể. Chỉ nên kiểm tra những điều kiện mà ứng dụng thực sự yêu cầu; không nên cố định mọi type thành bắt buộc nếu chúng là tùy chọn theo profile.

Các import được trình bày để minh họa API liên quan. API và import chính xác cần đối chiếu phiên bản Spring for GraphQL/GraphQL Java mà dự án đang sử dụng.

## 5. Kiểm tra root type, field và kiểu trả về

`GraphQLSchema` cho phép truy cập các root type:

```java
GraphQLObjectType queryType = schema.getQueryType();
GraphQLObjectType mutationType = schema.getMutationType();
GraphQLObjectType subscriptionType = schema.getSubscriptionType();
```

`queryType` là root type cần có của schema. `mutationType` và `subscriptionType` có thể là `null` nếu API không khai báo những operation đó.

Để xem những field của root query:

```java
queryType.getFieldDefinitions().forEach(field -> {
    System.out.println("Query field: " + field.getName());
});
```

Có thể kiểm tra một field cụ thể:

```java
if (queryType.getFieldDefinition("bookById") == null) {
    throw new IllegalStateException("Query.bookById is missing");
}
```

Với một object type, có thể kiểm tra tên field, argument và kiểu trả về. Ví dụ:

```java
GraphQLObjectType bookType = (GraphQLObjectType) schema.getType("Book");
GraphQLFieldDefinition titleField = bookType.getFieldDefinition("title");

if (titleField == null) {
    throw new IllegalStateException("Book.title is missing");
}

System.out.println("Book.title type: " + titleField.getType());
```

Trong thực tế, nên kiểm tra cả kiểu và nullability nếu client phụ thuộc vào cam kết đó. Ví dụ, thay đổi `String` thành `String!` hoặc ngược lại có thể ảnh hưởng đến cách client xử lý dữ liệu và lỗi. Khi cần so sánh cấu trúc wrapper một cách tổng quát, có thể duyệt `GraphQLType` và phân biệt `GraphQLNonNull`, `GraphQLList` với named type.

## 6. Kiểm tra tính hợp lệ của GraphQL schema

GraphQL Java xây dựng schema từ type definitions và runtime wiring. Ngoài lỗi phân tích SDL và lỗi build, ứng dụng có thể chủ động gọi `SchemaValidator` để chạy kiểm tra cấu trúc schema:

```java
import graphql.schema.GraphQLSchema;
import graphql.schema.validation.SchemaValidationError;
import graphql.schema.validation.SchemaValidator;

import java.util.Set;

GraphQLSchema schema = graphQlSource.schema();
Set<SchemaValidationError> errors = new SchemaValidator().validateSchema(schema);

if (!errors.isEmpty()) {
    throw new IllegalStateException("GraphQL schema validation failed: " + errors);
}
```

`SchemaValidator` bổ sung một bước kiểm tra rõ ràng trong quy trình startup hoặc test. Tùy phiên bản GraphQL Java, các loại lỗi và chi tiết API có thể thay đổi; hãy dùng phiên bản được Spring Boot quản lý và kiểm tra tài liệu tương ứng.

Schema validation không thay thế việc kiểm thử nghiệp vụ. Một schema có thể hợp lệ nhưng resolver vẫn truy vấn sai dữ liệu, trả về `null` cho field Non-null hoặc thực thi quyền truy cập chưa đúng.

## 7. In schema hiệu lực để review

Khi cần xem schema cuối cùng sau khi các tệp SDL đã được kết hợp, GraphQL Java cung cấp `SchemaPrinter`:

```java
import graphql.schema.idl.SchemaPrinter;

String effectiveSdl = new SchemaPrinter().print(graphQlSource.schema());
System.out.println(effectiveSdl);
```

Kết quả là SDL được in từ schema đã xây dựng. Nó hữu ích để review, lưu artifact trong pipeline hoặc so sánh giữa các phiên bản. Schema được in có thể được chuẩn hóa về thứ tự và định dạng, vì vậy không nhất thiết giống nguyên văn các file nguồn.

Trong ứng dụng thực tế, nên dùng logger hoặc một bước build/test riêng thay cho `System.out.println`. Tránh ghi toàn bộ schema vào log production nếu schema có mô tả hoặc metadata nội bộ không nên công khai.

## 8. Kiểm tra runtime wiring và resolver

Schema mô tả field có thể được gọi, còn runtime wiring kết nối field với data fetcher, scalar, type resolver và các thành phần thực thi khác.

Spring for GraphQL hỗ trợ nhiều cách đăng ký resolver:

- Annotation controller như `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`.
- `RuntimeWiringConfigurer` để đăng ký data fetcher, scalar, type resolver hoặc directive wiring.
- Default property fetcher để đọc thuộc tính từ source object khi không có resolver riêng.

Do đó, không thể kết luận một field bị thiếu resolver chỉ bằng cách nhìn vào danh sách field của schema. Một field có thể hoạt động bằng default property fetcher. Ngược lại, schema có thể hợp lệ nhưng một custom scalar hoặc union chưa được đăng ký đúng và chỉ bộc lộ vấn đề khi thực thi.

Nên xác minh các field quan trọng bằng query thực tế trong test context. Kiểm tra cả trường hợp resolver trả dữ liệu, trường hợp không có dữ liệu, lỗi nghiệp vụ và kiểu runtime của interface/union. Với những field cần authorization, kiểm tra cả người dùng được phép và không được phép truy cập.

## 9. Kiểm tra schema bằng `GraphQlTester`

`GraphQlTester` cho phép gửi GraphQL document đến schema trong test context. Có thể dùng nó để xác minh field mà schema công bố thực sự hoạt động:

```java
@GraphQlTest(BookController.class)
class BookSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void bookQueryIsAvailable() {
        given(bookService.findById("book-01"))
            .willReturn(new Book("book-01", "GraphQL Basics"));

        graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("bookById.id").entity(String.class).isEqualTo("book-01");
    }
}
```

Đây là ví dụ minh họa; các import, static import `given` và SDL khai báo `Query.bookById` cùng `Book` cần có trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Có thể thêm assertion cho `title`, kiểm tra field thiếu, hoặc kiểm tra lỗi khi resolver không trả dữ liệu theo nullability đã khai báo.

Kiểm thử introspection cũng có thể xác minh tên type và field, nhưng query nghiệp vụ như ví dụ trên kiểm tra được cả schema lẫn đường thực thi resolver. Hai cách bổ sung cho nhau: introspection xác minh metadata; query thực tế xác minh hành vi.

## 10. Đưa schema inspection vào quá trình khởi động và CI

Một quy trình kiểm tra thực tế có thể gồm:

1. **Kiểm tra resource:** xác nhận pattern schema locations tìm được các tệp SDL mong muốn.
2. **Build application context:** để Spring Boot và GraphQL Java phân tích, kết hợp SDL và tạo `GraphQlSource`.
3. **Kiểm tra schema hiệu lực:** xác nhận root type, type quan trọng, field bắt buộc, nullability và thành viên interface/union.
4. **Kiểm tra runtime wiring:** xác minh custom scalar, type resolver, directive wiring và các resolver quan trọng.
5. **Chạy GraphQlTester:** gửi những operation đại diện cho API và kiểm tra response.
6. **So sánh schema:** nếu cần, in schema hiệu lực bằng `SchemaPrinter` hoặc dùng introspection để so sánh với bản phát hành trước.

Có thể đặt các kiểm tra này trong test suite hoặc trong một bean kiểm tra khi application context khởi tạo. Nếu kiểm tra startup thất bại, hãy để quá trình khởi tạo thất bại rõ ràng thay vì tiếp tục phục vụ một schema không đáp ứng hợp đồng mà ứng dụng yêu cầu.

Một bean `InitializingBean` được tạo sau khi dependency `GraphQlSource` đã sẵn sàng, vì vậy có thể kiểm tra schema trong quá trình khởi tạo context. Với kiểm tra chạy qua `ApplicationRunner`, mã chạy sau khi context được khởi tạo và trước khi Spring Boot phát sự kiện `ApplicationReadyEvent`; cần kết hợp readiness probe nếu triển khai trong môi trường có load balancer hoặc orchestration.

## 11. Những lỗi thường gặp khi inspection

**Chỉ kiểm tra file SDL mà không xem schema cuối cùng.** Resource có thể không được nạp do sai pattern hoặc profile. Hãy kiểm tra `GraphQlSource.schema()` sau khi ứng dụng xây dựng schema.

**Cho rằng schema hợp lệ đồng nghĩa resolver hoạt động.** Schema validation chủ yếu kiểm tra cấu trúc. Cần gửi query qua `GraphQlTester` để xác minh resolver và runtime wiring.

**Đánh dấu mọi field phải có resolver riêng.** Nhiều field được phân giải bằng default property fetcher. Chỉ kiểm tra resolver tùy chỉnh ở nơi ứng dụng thực sự yêu cầu logic riêng.

**Không kiểm tra nullability.** Field đổi từ nullable sang Non-null hoặc ngược lại có thể làm thay đổi hành vi client. Hãy coi nullability là một phần của hợp đồng API.

**Bỏ qua union và interface.** Các kiểu trừu tượng cần phân giải kiểu runtime đúng. Kiểm tra `possibleTypes` và test từng thành viên thực tế.

**Chỉ log schema nhưng không kiểm tra điều kiện.** In SDL giúp quan sát, nhưng không tự động phát hiện field bắt buộc bị xóa. Hãy viết các assertion cụ thể cho hợp đồng ứng dụng.

**Không xét môi trường triển khai.** Profile hoặc cấu hình khác nhau có thể nạp schema khác nhau. Nên chạy kiểm tra trong từng cấu hình môi trường quan trọng.

## Kết luận

Schema inspection trước khi chạy giúp xác nhận GraphQL schema hiệu lực đã được nạp và đáp ứng những điều kiện mà ứng dụng cần. Với Spring for GraphQL, có thể lấy schema từ `GraphQlSource`, kiểm tra root type và field bằng GraphQL Java API, dùng `SchemaValidator` và `SchemaPrinter` khi phù hợp, rồi xác minh resolver bằng `GraphQlTester`. Kết hợp kiểm tra cấu trúc với kiểm thử operation giúp phát hiện lỗi schema loading và runtime wiring sớm trong startup hoặc CI.
