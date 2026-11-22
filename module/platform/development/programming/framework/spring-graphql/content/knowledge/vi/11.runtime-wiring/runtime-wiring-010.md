# Code registry

Trong GraphQL Java, **CodeRegistry** là thành phần liên kết các field trong schema với logic thực thi. Schema SDL mô tả API có những type và field nào; code registry cho GraphQL biết cần gọi DataFetcher nào để lấy giá trị của một field và TypeResolver nào để xác định kiểu object thực tế khi field trả về interface hoặc union.

Trong Spring for GraphQL, phần lớn ứng dụng không cần tự tạo GraphQLCodeRegistry. Spring kết nối các controller annotation như @QueryMapping và @SchemaMapping với GraphQL runtime. Khi cần đăng ký DataFetcher, TypeResolver hoặc cấu hình thực thi ở mức GraphQL Java, có thể dùng RuntimeWiringConfigurer. Hiểu quan hệ giữa schema, RuntimeWiring và CodeRegistry giúp tránh đăng ký trùng resolver và chẩn đoán được lỗi wiring.

## 1. CodeRegistry là gì?

GraphQL schema định nghĩa các type và field mà client có thể truy vấn. Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Schema cho biết field Query.book nhận argument id và trả về Book. Tuy nhiên, SDL không chứa Java code để tìm quyển sách. GraphQL cần một thành phần thực thi field đó.

Code registry lưu các liên kết thực thi, tiêu biểu:

- **DataFetcher**: lấy hoặc tính giá trị cho một field.
- **TypeResolver**: xác định concrete object type cho interface hoặc union.

Một cách hình dung:

~~~mermaid
flowchart TD
    A["GraphQL SDL"] --> B["GraphQL schema"]
    C["RuntimeWiring"] --> D["GraphQLCodeRegistry"]
    B --> E["Executable GraphQL runtime"]
    D --> E
    E --> F["Client gửi operation"]
    F --> G["Tra cứu DataFetcher theo field"]
    G --> H["Thực thi và tạo response"]
~~~

Schema và code registry có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| SDL / GraphQLSchema | Mô tả cấu trúc và hợp đồng API. |
| RuntimeWiring | Cấu hình các thành phần thực thi khi xây dựng schema. |
| GraphQLCodeRegistry | Lưu mapping DataFetcher và TypeResolver mà GraphQL engine sử dụng. |
| DataFetcher | Lấy giá trị của một field cụ thể. |
| TypeResolver | Chọn object type cụ thể cho interface hoặc union. |

Code registry không thay thế schema. Một DataFetcher được đăng ký cho field không có trong schema cũng không tự tạo field đó cho client. Field vẫn phải được khai báo trong SDL.

## 2. FieldCoordinates: địa chỉ của một field

Một field được xác định bằng type cha và tên field. GraphQL Java biểu diễn cặp này bằng FieldCoordinates.

Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Hai field có địa chỉ khác nhau:

- Query.book
- Book.title

Ngay cả khi nhiều type có field cùng tên, mỗi mapping vẫn được phân biệt theo type cha. Vì vậy, chỉ dùng tên field như book hoặc id là không đủ để xác định một DataFetcher duy nhất trong schema.

Trong GraphQL Java, tạo tọa độ bằng:

~~~java
FieldCoordinates.coordinates("Query", "book")
~~~

Tọa độ này cho biết DataFetcher sẽ được dùng khi GraphQL phân giải field book trên type Query.

Khi chẩn đoán lỗi mapping, hãy kiểm tra cả tên type và tên field. Một DataFetcher đăng ký vào Book.author sẽ không xử lý Query.author, dù hai field cùng tên.

## 3. DataFetcher là gì?

DataFetcher là hàm mà GraphQL Java gọi để lấy giá trị của một field. Nó nhận DataFetchingEnvironment, nơi cung cấp thông tin của lần thực thi hiện tại, ví dụ:

- Source object của field đang được phân giải.
- Argument mà client truyền cho field.
- GraphQL context và local context.
- Thông tin field, selection và schema liên quan.
- Các biến và metadata của operation.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

DataFetcher Java:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findById(id);
};
~~~

GraphQL truyền argument id vào environment. DataFetcher đọc giá trị đó, gọi service và trả về Book. GraphQL engine tiếp tục phân giải những field con mà client chọn, chẳng hạn id và title.

DataFetcher có thể trả về giá trị đồng bộ hoặc kiểu bất đồng bộ được GraphQL Java hỗ trợ, chẳng hạn CompletionStage. Với thao tác gọi dịch vụ từ xa hoặc I/O, xử lý bất đồng bộ phù hợp có thể giúp tránh chặn thread xử lý request.

Không nên đặt toàn bộ nghiệp vụ vào DataFetcher. Hãy giữ DataFetcher ở vai trò kết nối GraphQL với service; quy tắc nghiệp vụ, giao dịch và truy cập dữ liệu nên được tổ chức trong các thành phần chuyên trách.

## 4. Source object và argument trong DataFetcher

DataFetcher không chỉ dùng cho root Query. Khi GraphQL phân giải một field lồng nhau, source object chính là kết quả của field cha.

Schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

Khi client gửi:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

GraphQL thực hiện Query.book trước. Giá trị Book trả về trở thành source object khi phân giải Book.title và Book.author. Với Book.author, DataFetcher có thể lấy authorId từ source object Book rồi truy vấn Author.

Ví dụ DataFetcher cho field lồng nhau:

~~~java
DataFetcher<Author> authorFetcher = environment -> {
    Book sourceBook = environment.getSource();
    return authorService.findById(sourceBook.authorId());
};
~~~

Nếu field có argument, có thể đọc thêm bằng environment.getArgument:

~~~graphql
type Book {
    reviews(first: Int = 10): [Review!]!
}
~~~

~~~java
DataFetcher<List<Review>> reviewsFetcher = environment -> {
    Book sourceBook = environment.getSource();
    Integer first = environment.getArgument("first");
    return reviewService.findByBookId(sourceBook.id(), first);
};
~~~

Source object và argument là hai nguồn dữ liệu khác nhau: source đến từ field cha, còn argument đến từ field hiện tại trong operation.

## 5. RuntimeWiring kết nối DataFetcher với schema

GraphQL Java cung cấp RuntimeWiring như một API cấp cao để đăng ký DataFetcher, TypeResolver, custom scalar và một số thành phần thực thi khác. Khi tạo executable schema từ SDL, SchemaGenerator sử dụng RuntimeWiring để xây dựng schema và code registry tương ứng.

Ví dụ đăng ký DataFetcher cho Query.book:

~~~java
RuntimeWiring runtimeWiring = RuntimeWiring.newRuntimeWiring()
    .type("Query", typeWiring -> typeWiring
        .dataFetcher("book", environment -> {
            String id = environment.getArgument("id");
            return bookService.findById(id);
        }))
    .build();
~~~

Trong ví dụ này:

- type("Query", ...) chọn object type có tên Query.
- dataFetcher("book", ...) đăng ký DataFetcher cho field book của Query.
- environment.getArgument("id") lấy argument đã được GraphQL xử lý.
- Kết quả từ service trở thành giá trị của field book.

SchemaGenerator dùng TypeDefinitionRegistry và RuntimeWiring để tạo GraphQLSchema:

~~~java
TypeDefinitionRegistry typeRegistry =
        new SchemaParser().parse(schemaFile);

GraphQLSchema schema = new SchemaGenerator()
        .makeExecutableSchema(typeRegistry, runtimeWiring);
~~~

Đây là cách xây dựng schema ở mức GraphQL Java thuần. Trong ứng dụng Spring Boot, Spring for GraphQL thường quản lý việc nạp SDL và tạo GraphQL runtime. Vì vậy, không cần tự tạo SchemaParser hoặc SchemaGenerator trong mỗi controller.

## 6. GraphQLCodeRegistry và cách đăng ký trực tiếp

GraphQLCodeRegistry là registry thực thi được gắn với GraphQLSchema. Có thể tạo builder và đăng ký DataFetcher bằng FieldCoordinates:

~~~java
DataFetcher<Book> bookFetcher =
        environment -> bookService.findById(
                environment.getArgument("id"));

GraphQLCodeRegistry codeRegistry =
        GraphQLCodeRegistry.newCodeRegistry()
            .dataFetcher(
                FieldCoordinates.coordinates("Query", "book"),
                bookFetcher
            )
            .build();
~~~

Trong quá trình xây dựng schema ở mức GraphQL Java, registry được gắn vào GraphQLSchema:

~~~java
GraphQLSchema schema = GraphQLSchema.newSchema()
        .query(queryType)
        .codeRegistry(codeRegistry)
        .build();
~~~

Ví dụ này giả định queryType và các type cần thiết đã được xây dựng hợp lệ. Trong ứng dụng thực tế, GraphQLSchema phải có đầy đủ type, root operation và các mapping cần thiết.

Khi dùng GraphQL Java trực tiếp, GraphQLCodeRegistry hữu ích nếu cần kiểm soát rõ mapping theo FieldCoordinates. Với ứng dụng Spring Boot, thường nên đăng ký qua RuntimeWiringConfigurer để tích hợp vào GraphQlSource do Spring quản lý, thay vì tự xây dựng một GraphQLSchema riêng và bỏ qua auto-configuration.

## 7. Đăng ký RuntimeWiringConfigurer trong Spring for GraphQL

Spring for GraphQL cho phép ứng dụng cung cấp bean RuntimeWiringConfigurer. Spring gọi configurer khi xây dựng GraphQL runtime từ SDL.

Ví dụ:

~~~java
package com.example.catalog.config;

import com.example.catalog.book.BookService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlConfig {

    @Bean
    RuntimeWiringConfigurer bookRuntimeWiring(BookService bookService) {
        return wiringBuilder -> wiringBuilder
            .type("Query", typeWiring -> typeWiring
                .dataFetcher("book", environment -> {
                    String id = environment.getArgument("id");
                    return bookService.findById(id);
                }));
    }
}
~~~

Schema tương ứng:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Spring Boot quản lý bean configurer và kết hợp cấu hình đó khi tạo GraphQL runtime. DataFetcher đã đăng ký sẽ xử lý Query.book khi client gọi field này.

Có thể có nhiều RuntimeWiringConfigurer trong ứng dụng, mỗi bean đóng góp một phần cấu hình. Nên chia theo domain hoặc chức năng khi điều đó giúp code dễ quản lý, đồng thời tránh nhiều configurer đăng ký cùng một tọa độ field.

### Không đăng ký trùng với controller annotation

Spring for GraphQL hỗ trợ annotated controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

@QueryMapping được Spring phát hiện và đăng ký thành DataFetcher cho Query.book. Vì vậy, nếu field Query.book đã được xử lý bởi controller này, không nên đăng ký thêm một DataFetcher khác cho cùng tọa độ trong RuntimeWiringConfigurer.

Chọn một nơi chịu trách nhiệm cho mỗi mapping:

- Dùng @QueryMapping, @MutationMapping và @SchemaMapping cho logic gắn với controller Spring.
- Dùng RuntimeWiringConfigurer khi cần tích hợp trực tiếp API GraphQL Java, ví dụ custom DataFetcher hoặc TypeResolver.
- Dùng property data fetcher mặc định khi field có thể đọc trực tiếp từ thuộc tính của source object.

Đăng ký trùng mapping có thể gây xung đột hoặc làm hành vi khó dự đoán tùy cách các configurer được kết hợp. Hãy giữ mỗi field có một nguồn mapping rõ ràng.

## 8. TypeResolver trong CodeRegistry

DataFetcher lấy giá trị field. TypeResolver giải quyết một vấn đề khác: khi field trả về interface hoặc union, GraphQL cần biết object thực tế thuộc concrete type nào để chọn đúng selection set.

Ví dụ schema:

~~~graphql
interface SearchResult {
    id: ID!
}

type Book implements SearchResult {
    id: ID!
    title: String!
}

type Author implements SearchResult {
    id: ID!
    name: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
~~~

Resolver Query.search có thể trả về danh sách object Book và Author. Nhưng GraphQL cần TypeResolver để xác định kiểu cụ thể của từng phần tử.

Ví dụ cấu hình trong RuntimeWiring:

~~~java
.type("SearchResult", typeWiring -> typeWiring
    .typeResolver(environment -> {
        Object source = environment.getObject();

        if (source instanceof Book) {
            return environment.getSchema().getObjectType("Book");
        }

        if (source instanceof Author) {
            return environment.getSchema().getObjectType("Author");
        }

        return null;
    }))
~~~

Trong ứng dụng thực tế, cần bảo đảm mọi concrete type có thể xuất hiện đều được xử lý. Nếu resolver không xác định được type, GraphQL không thể hoàn thành field interface/union và sẽ tạo execution error.

Với union, nguyên tắc tương tự: TypeResolver phải trả về object type là thành viên hợp lệ của union. Không thể trả một type không được khai báo trong union hoặc một input type.

## 9. CodeRegistry và default property data fetcher

Không phải field nào cũng cần DataFetcher tùy chỉnh. GraphQL Java có cơ chế property data fetching để đọc giá trị từ source object.

Ví dụ:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

Nếu Query.book trả về một Java object Book có accessor phù hợp cho id và title, GraphQL có thể đọc các giá trị đó mà không cần đăng ký DataFetcher riêng cho Book.id và Book.title.

Ví dụ Java record:

~~~java
public record Book(String id, String title) {
}
~~~

Với record này, các accessor id() và title() cung cấp dữ liệu tương ứng. Với JavaBean, getter như getId() và getTitle() thường được dùng bởi property data fetcher.

Khi cần truy vấn quan hệ hoặc tính toán field, đăng ký DataFetcher riêng:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Property access phù hợp khi dữ liệu đã có trên source object. Resolver tùy chỉnh phù hợp khi field cần service, repository, argument hoặc logic nghiệp vụ. Không nên thêm mapping tường minh chỉ để lặp lại đúng giá trị mà property fetcher đã cung cấp.

## 10. Custom scalar và các thành phần wiring liên quan

Code registry tập trung vào DataFetcher và TypeResolver. RuntimeWiring còn có thể đăng ký các thành phần khác như custom scalar.

Ví dụ SDL:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

Nếu DateTime là scalar tùy chỉnh, ứng dụng phải cung cấp implementation GraphQLScalarType với quy tắc parse input và serialize output phù hợp. Có thể đăng ký qua RuntimeWiringConfigurer:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer(GraphQLScalarType dateTimeScalar) {
    return wiringBuilder -> wiringBuilder.scalar(dateTimeScalar);
}
~~~

Custom scalar không phải DataFetcher. Scalar xác định cách chuyển đổi giá trị; DataFetcher lấy giá trị field. Dù cùng được cấu hình qua RuntimeWiring, hai trách nhiệm này khác nhau.

Tương tự, directive wiring hoặc type resolver cũng có trách nhiệm riêng. Khi debug, xác định thành phần nào đang thiếu trước khi thêm cấu hình mới vào registry.

## 11. Kiểm thử mapping và code registry

Có thể dùng GraphQlTester để kiểm thử field đã được đăng ký và trả dữ liệu đúng:

~~~java
@Test
void resolvesBookThroughGraphQl() {
    graphQlTester.document("""
            query BookDetail($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring in Action");
}
~~~

Nếu dùng RuntimeWiringConfigurer, nên kiểm tra operation gọi đúng DataFetcher. Có thể mock hoặc spy service để xác nhận:

- DataFetcher nhận đúng argument.
- DataFetcher gọi service đúng một lần với khóa tương ứng.
- Field không được gọi khi không nằm trong selection set.
- Field lồng nhau nhận đúng source object.
- TypeResolver trả concrete type đúng với từng object.
- Custom scalar parse và serialize theo định dạng đã công bố.

Nên có test tích hợp tạo GraphQL runtime từ SDL thật. Một test chỉ gọi trực tiếp lambda DataFetcher không xác nhận rằng mapping đã được gắn đúng tọa độ hoặc schema đã nạp đúng.

## 12. Các lỗi thường gặp khi cấu hình CodeRegistry

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Field có trong SDL nhưng không lấy được dữ liệu | Không có DataFetcher phù hợp và source object không có property tương ứng. | Đăng ký DataFetcher hoặc cung cấp property/accessor đúng. |
| DataFetcher không được gọi | Mapping đăng ký sai type name hoặc field name. | Kiểm tra FieldCoordinates hoặc type trong RuntimeWiring. |
| Field trả null ngoài dự kiến | Source object không có giá trị, service trả null hoặc property fetcher không tìm thấy accessor. | Kiểm tra source, getter/record accessor và service. |
| Controller mapping bị xung đột | Cùng field được đăng ký qua annotation và RuntimeWiringConfigurer. | Chỉ giữ một mapping cho tọa độ field. |
| Interface/union không phân giải được | Thiếu TypeResolver hoặc resolver không nhận diện object. | Đăng ký TypeResolver và xử lý mọi concrete type hợp lệ. |
| Custom scalar không hoạt động | Chưa đăng ký GraphQLScalarType hoặc coercing sai. | Cấu hình scalar qua RuntimeWiringConfigurer. |
| Query gọi service quá nhiều lần | DataFetcher con thực hiện truy vấn riêng cho từng source object. | Đo số lần gọi và dùng DataLoader hoặc @BatchMapping khi phù hợp. |
| Schema khởi động thất bại | Lỗi SDL hoặc schema validation bị nhầm với lỗi registry. | Kiểm tra parse/validation trước, sau đó mới kiểm tra wiring. |

Khi DataFetcher không chạy, hãy kiểm tra schema trước, rồi kiểm tra tọa độ mapping và việc configurer có được Spring đăng ký hay không. Nếu field đã chạy nhưng trả null, kiểm tra source object và service. Nếu lỗi chỉ xảy ra với interface hoặc union, tập trung vào TypeResolver.

## 13. Những điểm cần ghi nhớ

- GraphQLCodeRegistry lưu mapping DataFetcher và TypeResolver mà GraphQL runtime sử dụng.
- FieldCoordinates xác định field bằng cặp type cha và tên field.
- DataFetcher lấy giá trị field từ source object, argument và context.
- RuntimeWiring là API cấp cao để cấu hình các thành phần thực thi khi tạo schema; code registry được tích hợp vào GraphQLSchema.
- Spring for GraphQL cho phép bổ sung cấu hình bằng RuntimeWiringConfigurer.
- @QueryMapping và @SchemaMapping cũng được Spring chuyển thành DataFetcher; tránh đăng ký trùng cùng field.
- Property data fetcher mặc định có thể đọc accessor từ source object mà không cần resolver tùy chỉnh.
- TypeResolver xác định concrete object type cho interface và union.
- Custom scalar là thành phần wiring riêng, không phải DataFetcher.
- Khi chẩn đoán, kiểm tra SDL, FieldCoordinates, configurer, source object và loại resolver tương ứng.

CodeRegistry là cầu nối giữa cấu trúc schema và logic thực thi của GraphQL Java. Trong Spring for GraphQL, hiểu registry cùng RuntimeWiringConfigurer giúp tích hợp resolver tùy chỉnh đúng cách, giữ mapping rõ ràng và xử lý các kiểu dữ liệu phức tạp mà không làm rối cấu trúc controller.

