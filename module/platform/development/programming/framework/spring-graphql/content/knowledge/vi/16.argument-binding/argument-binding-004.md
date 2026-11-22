# Argument name và parameter name trong Spring for GraphQL

Trong GraphQL SDL, mỗi field có thể khai báo các argument với tên do schema quyết định. Trong Java controller, method handler nhận các giá trị đó qua tham số phương thức, thường dùng annotation `@Argument`. Spring for GraphQL cần biết tên GraphQL argument nào sẽ được bind vào từng Java parameter.

Tên GraphQL argument và tên Java parameter có thể giống nhau hoặc khác nhau. Khi giống nhau và compiler lưu metadata tên tham số, Spring có thể tự suy luận. Khi khác nhau, hoặc khi muốn code không phụ thuộc metadata compiler, hãy chỉ rõ tên bằng `@Argument("...")`.

## 1. Hai loại tên có vai trò khác nhau

Xét schema:

```graphql
type Query {
    bookById(bookId: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

`bookId` là tên argument trong GraphQL API. Nó là một phần của contract mà client sử dụng:

```graphql
query {
    bookById(bookId: "book-10") {
        id
        title
    }
}
```

Trong Java, tham số method có thể được đặt tên `bookId`, `id`, `requestedId` hoặc tên khác. Tên Java chỉ phục vụ code phía server. Spring for GraphQL cần ánh xạ tên GraphQL `bookId` sang đúng tham số Java.

```java
@QueryMapping
public Book bookById(@Argument("bookId") String id) {
    return bookService.findById(id).orElse(null);
}
```

Ở ví dụ này, GraphQL argument là `bookId`, còn Java parameter là `id`. Giá trị từ `bookId` được bind vào `id` nhờ tên được chỉ rõ trong `@Argument`.

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| GraphQL argument name | `bookId` trong SDL | Tên client phải dùng khi gọi field. |
| Java parameter name | `id` trong method | Tên biến được dùng trong phần thân method. |
| `@Argument` name | `@Argument("bookId")` | Chỉ định GraphQL argument cần bind vào parameter. |

## 2. Khai báo tên argument tường minh bằng `@Argument`

`@Argument` nằm trong package `org.springframework.graphql.data.method.annotation`. Có thể truyền tên GraphQL argument trực tiếp vào annotation:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("bookId") String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`@Argument("bookId")` chỉ định rõ argument tên `bookId`. Tên biến Java `id` có thể thay đổi mà không cần đổi schema hoặc query phía client. Cách viết này hữu ích khi:

- Tên GraphQL theo quy ước API khác tên Java trong code.
- Java parameter có tên ngắn hoặc mang ý nghĩa domain riêng.
- Muốn tránh phụ thuộc vào compiler metadata.
- Đang bảo trì API lâu dài và cần mapping dễ đọc ngay tại method signature.

Annotation cũng hỗ trợ thuộc tính `name`, ví dụ `@Argument(name = "bookId")`. Thuộc tính `value` là alias của `name`, vì vậy `@Argument("bookId")` và `@Argument(name = "bookId")` có cùng ý nghĩa.

## 3. Suy luận argument name từ Java parameter name

Nếu không ghi tên trong `@Argument`, Spring for GraphQL mặc định dùng tên Java parameter khi tên đó có thể được khám phá từ class đã biên dịch.

Ví dụ SDL:

```graphql
type Query {
    bookById(bookId: ID!): Book
}
```

Controller:

```java
@QueryMapping
public Book bookById(@Argument String bookId) {
    return bookService.findById(bookId).orElse(null);
}
```

Vì Java parameter tên `bookId`, Spring suy luận GraphQL argument cũng tên `bookId`. Client tiếp tục gọi `bookById(bookId: ...)` như đã khai báo trong SDL.

Để Java reflection đọc được tên tham số, cần biên dịch class với metadata tên parameter. Với Java 8 trở lên, cách rõ ràng và nên dùng là bật compiler option `-parameters`. Một số phiên bản/cấu hình compiler cũng có thể cung cấp tên qua debug information, nhưng không nên dựa vào hành vi đó nếu build cần ổn định giữa môi trường.

Nếu metadata tên tham số không có và `@Argument` không chỉ định tên, framework không thể suy luận chính xác argument cần lấy. Khi đó hãy bật `-parameters` hoặc ghi tên rõ ràng trong annotation.

## 4. Bật `-parameters` trong Maven

Với Maven Compiler Plugin, bật tùy chọn `parameters`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Cấu hình này yêu cầu compiler ghi tên parameter vào bytecode để Java reflection có thể truy cập. Nếu project đã quản lý plugin trong `pluginManagement`, hãy đặt cấu hình vào phần plugin thực sự được áp dụng cho module biên dịch.

Sau khi thay đổi, cần biên dịch lại source để tạo class mới có metadata. Chỉ sửa `pom.xml` mà vẫn chạy các file `.class` cũ thì tên tham số vẫn có thể không được tìm thấy.

## 5. Bật `-parameters` trong Gradle

Với Gradle Java plugin, có thể thêm compiler argument cho các task `JavaCompile`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Nếu build dùng Kotlin DSL (`build.gradle.kts`):

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Đặt cấu hình ở build script của module chứa controller hoặc ở cấu hình dùng chung phù hợp với dự án. Sau đó chạy lại compile/test để các class được tạo với parameter metadata mới.

## 6. So sánh hai cách ánh xạ

Giả sử schema có argument `authorId`:

```graphql
type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
```

Cách thứ nhất: dùng tên Java parameter để suy luận:

```java
@QueryMapping
public List<Book> booksByAuthor(@Argument String authorId) {
    return bookService.findByAuthor(authorId);
}
```

Cách thứ hai: khai báo GraphQL argument name rõ ràng:

```java
@QueryMapping
public List<Book> booksByAuthor(@Argument("authorId") String id) {
    return bookService.findByAuthor(id);
}
```

Hai cách có kết quả tương đương nếu parameter metadata có sẵn trong cách thứ nhất. Cách tường minh không phụ thuộc tên biến Java hay cờ compiler; cách suy luận ngắn gọn hơn khi hai tên đã trùng nhau và build bảo đảm metadata.

| Tiêu chí | Suy luận từ parameter name | Tên tường minh trong `@Argument` |
| --- | --- | --- |
| Cú pháp | Ngắn hơn | Rõ mapping ngay tại annotation |
| Yêu cầu metadata | Cần khám phá được tên parameter | Không cần metadata tên parameter |
| Khi đổi tên biến Java | Có thể phải đổi GraphQL argument hoặc annotation | Không ảnh hưởng GraphQL mapping |
| Phù hợp | Tên Java và SDL thống nhất | Tên Java và SDL khác nhau hoặc cần mapping ổn định |

Trong codebase lớn, có thể thống nhất một quy ước: dùng `@Argument("...")` cho các argument có tên khác Java parameter; dùng suy luận khi tên trùng và compiler đã bật `-parameters` trên toàn bộ module. Quan trọng là team áp dụng nhất quán và kiểm thử cấu hình build.

## 7. Tên argument với input object

`@Argument` không chỉ bind scalar. Khi argument là input object, Spring for GraphQL có thể bind giá trị thành Java record hoặc class.

Schema:

```graphql
input BookSearchInput {
    keyword: String
    authorId: ID
    publishedAfter: String
}

type Query {
    searchBooks(filter: BookSearchInput!): [Book!]!
}
```

Java input record và resolver:

```java
public record BookSearchCriteria(
        String keyword,
        String authorId,
        String publishedAfter) {
}
```

```java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") BookSearchCriteria criteria) {
    return bookService.search(criteria);
}
```

Ở đây, `filter` là tên argument GraphQL. `BookSearchCriteria` là kiểu Java nhận giá trị của argument đó. Tên Java class không cần giống `BookSearchInput`, nhưng các thuộc tính/constructor parameter phải tương thích với các field bên trong input object.

Spring sử dụng `GraphQlArgumentBinder` để tạo object đích. Với record hoặc class có primary/data constructor, binder ánh xạ các giá trị input vào constructor. Với class có default constructor, binder có thể tạo instance rồi gán qua setter. Quá trình bind được thực hiện đệ quy cho input object lồng nhau.

Record component có tên được lưu trong metadata của record; với class dùng constructor thông thường, cần bảo đảm tên constructor parameter có thể được khám phá nếu binder dựa vào chúng. Giữ tên component/property Java tương ứng với field trong SDL giúp binding dễ dự đoán. Nếu schema và Java property phải dùng quy ước tên khác nhau, có thể tùy biến `GraphQlArgumentBinder` thông qua `AnnotatedControllerConfigurer` và `nameResolver` thay vì đổi tên field public của schema một cách tùy tiện.

## 8. Phân biệt `@Argument` và `@Arguments`

Hai annotation này có phạm vi khác nhau:

- `@Argument` lấy một argument có tên từ field hiện tại rồi bind giá trị đó vào parameter.
- `@Arguments` lấy toàn bộ map argument cấp cao nhất của field rồi bind map đó vào một object hoặc `Map`.

Ví dụ SDL có hai argument riêng:

```graphql
type Query {
    searchBooks(keyword: String, limit: Int): [Book!]!
}
```

Dùng `@Argument` để lấy từng argument:

```java
@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") String text,
        @Argument("limit") Integer pageSize) {
    return bookService.search(text, pageSize);
}
```

Dùng `@Arguments` để bind toàn bộ argument vào một record:

```java
public record SearchBooksArguments(String keyword, Integer limit) {
}
```

```java
import org.springframework.graphql.data.method.annotation.Arguments;

@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(arguments.keyword(), arguments.limit());
}
```

Với `@Arguments Map<String, Object>`, method nhận raw map của tất cả argument. Với `@Argument("filter") Map<String, Object>`, method nhận raw map của riêng argument `filter`. Không dùng `@Argument Map` để lấy toàn bộ argument map; cho mục đích đó, dùng `@Arguments Map`.

## 9. Quy tắc đặt tên GraphQL và Java

GraphQL thường dùng `camelCase` cho field và argument:

```graphql
type Query {
    booksByAuthor(authorId: ID!, pageSize: Int = 20): [Book!]!
}
```

Java cũng thường dùng `camelCase` cho parameter:

```java
@QueryMapping
public List<Book> booksByAuthor(
        @Argument String authorId,
        @Argument Integer pageSize) {
    return bookService.findByAuthor(authorId, pageSize);
}
```

Khi tên giống nhau, code ngắn và dễ đọc. Khi khác nhau, thể hiện mapping bằng annotation:

```java
@QueryMapping
public List<Book> booksByAuthor(
        @Argument("authorId") String writerId,
        @Argument("pageSize") Integer limit) {
    return bookService.findByAuthor(writerId, limit);
}
```

Không nên đổi tên GraphQL argument chỉ để khớp một biến Java cục bộ. GraphQL argument là contract công khai và có thể được nhiều client sử dụng. Hãy giữ tên schema ổn định, rồi ánh xạ sang tên nội bộ bằng `@Argument`.

## 10. Argument name không quyết định bắt buộc hay giá trị mặc định

`@Argument` dùng để xác định argument cần bind; annotation không có thuộc tính `required` hoặc `defaultValue`. Tính bắt buộc và giá trị mặc định được khai báo trong GraphQL SDL.

```graphql
type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}
```

Trong schema trên:

- `id: ID!` là argument bắt buộc. GraphQL từ chối request thiếu `id` hoặc truyền null.
- `limit: Int = 20` có giá trị mặc định 20 khi client bỏ qua argument.
- `limit` nullable nên client có thể truyền null tường minh; default không thay thế một giá trị null đã được gửi.

Resolver chỉ cần bind argument:

```java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}

@QueryMapping
public List<Book> books(@Argument("limit") Integer limit) {
    return bookService.findRecent(limit);
}
```

Nếu `limit` có thể null, service cần quy định rõ cách xử lý hoặc schema nên cung cấp default/Non-Null phù hợp với nghiệp vụ. Không dùng tên annotation để thay thế quy tắc validation của SDL.

## 11. Binding lỗi và cách chẩn đoán

Nếu GraphQL argument không được bind vào kiểu Java đích, Spring for GraphQL có thể phát sinh `BindException` với các lỗi theo đường dẫn field trong input. Ví dụ input có `filter.authorId` nhưng Java record không có constructor/property tương ứng hoặc kiểu dữ liệu không chuyển đổi được.

Khi chẩn đoán, kiểm tra theo thứ tự:

1. Tên argument trong SDL có đúng với `@Argument("...")` hoặc Java parameter name được suy luận không?
2. Build có bật `-parameters` nếu đang dùng suy luận tên không?
3. Client có truyền đúng tên argument và đúng kiểu GraphQL không?
4. Nếu argument là input object, constructor/property Java có tương thích với các field của input type không?
5. Có kiểu lồng nhau hoặc collection cần binder chuyển đổi không?
6. Có custom conversion hoặc `GraphQlArgumentBinder` configuration nào làm thay đổi cách bind không?

Ví dụ lỗi do lệch tên:

```graphql
type Query {
    bookById(bookId: ID!): Book
}
```

```java
// Sai nếu parameter metadata cho biết tên là "id" và không có argument "id".
@QueryMapping
public Book bookById(@Argument String id) {
    return bookService.findById(id).orElse(null);
}
```

Sửa bằng cách chỉ rõ tên GraphQL argument:

```java
@QueryMapping
public Book bookById(@Argument("bookId") String id) {
    return bookService.findById(id).orElse(null);
}
```

Hoặc đổi tên parameter thành `bookId` và bảo đảm compiler lưu parameter metadata.

## 12. Kiểm thử mapping tên argument

Nên kiểm thử resolver thông qua GraphQL document để xác nhận contract SDL và method parameter hoạt động cùng nhau.

Ví dụ kiểm thử argument được ánh xạ tường minh:

```java
@Test
void explicitArgumentNameIsBoundToJavaParameter() {
    graphQlTester.document("""
            query FindBook($id: ID!) {
                bookById(bookId: $id) {
                    title
                }
            }
            """)
        .variable("id", "book-10")
        .execute()
        .path("bookById.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
}
```

Ví dụ kiểm thử input object:

```java
@Test
void namedInputArgumentIsBoundToRecord() {
    graphQlTester.document("""
            query Search($filter: BookSearchInput!) {
                searchBooks(filter: $filter) {
                    title
                }
            }
            """)
        .variable("filter", Map.of("keyword", "spring"))
        .execute()
        .path("searchBooks[0].title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
}
```

Các ví dụ giả định `graphQlTester`, service và fixture đã được cấu hình trong test context. Nếu dự án dựa vào suy luận tên parameter, hãy giữ một integration test chạy với class đã biên dịch bằng đúng build configuration. Nếu chỉ test bằng IDE hoặc build tool khác với production, có thể bỏ sót lỗi thiếu `-parameters`.

Các trường hợp nên kiểm tra:

1. Tên argument trùng parameter name và được suy luận thành công.
2. Tên GraphQL argument khác Java parameter name nhưng `@Argument("...")` ánh xạ đúng.
3. Build thiếu parameter metadata nhưng annotation có tên tường minh vẫn hoạt động.
4. Argument bắt buộc bị thiếu hoặc null được GraphQL từ chối theo SDL.
5. Argument có default nhận đúng giá trị khi bị bỏ qua.
6. Input object được bind đúng vào record/class, bao gồm field lồng nhau.
7. `@Argument Map` và `@Arguments Map` nhận đúng phạm vi dữ liệu khác nhau.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy argument khi method dùng `@Argument` không tên | Java parameter name không được lưu trong bytecode | Bật `-parameters` hoặc ghi `@Argument("name")`. |
| Resolver nhận null dù client gửi giá trị | Tên trong SDL không khớp tên annotation/parameter | So sánh tên argument và mapping trong method signature. |
| Đổi tên biến Java làm query lỗi | Mapping đang phụ thuộc parameter name được suy luận | Dùng tên tường minh trong `@Argument` hoặc giữ đồng bộ tên. |
| Dùng `@Argument Map` nhưng chỉ nhận một phần dữ liệu | Annotation lấy một argument được chỉ định | Dùng `@Arguments Map` nếu cần toàn bộ argument map. |
| Input object không bind được | Java constructor/property không tương thích input type | Kiểm tra record component, constructor, setter và kiểu lồng nhau. |
| Mong `@Argument` tự bắt buộc giá trị | Nhầm annotation binding với schema validation | Khai báo `!` hoặc default trong SDL. |
| Build local chạy nhưng môi trường khác lỗi | Cấu hình compiler không nhất quán giữa các module | Chuẩn hóa `-parameters` và kiểm thử artifact được build trong CI. |

## 14. Checklist khi ánh xạ argument name

1. Xác định tên argument chính thức trong GraphQL SDL.
2. Nếu Java parameter có cùng tên, bật `-parameters` để Spring có thể suy luận.
3. Nếu tên khác nhau hoặc muốn mapping độc lập compiler, dùng `@Argument("graphqlName")`.
4. Dùng `@Argument` cho một argument; dùng `@Arguments` cho toàn bộ map argument cấp cao nhất.
5. Với input object, bảo đảm Java record/class có constructor hoặc property tương thích.
6. Đặt required/default trong SDL, không tìm thuộc tính tương ứng trong `@Argument`.
7. Giữ tên GraphQL ổn định khi refactor biến Java.
8. Kiểm thử cả mapping tường minh, suy luận tên và cấu hình build thực tế.

Tên GraphQL argument thuộc về contract của API; tên Java parameter thuộc về cách triển khai resolver. Spring for GraphQL kết nối hai phía qua `@Argument`, có thể dùng tên parameter để suy luận hoặc dùng tên tường minh để kiểm soát mapping. Khi hiểu rõ hai lựa chọn này và cấu hình compiler nhất quán, controller sẽ dễ đọc, ít lỗi bind và an toàn hơn khi refactor.

Tài liệu tham khảo: [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html).
