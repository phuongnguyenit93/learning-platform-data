# Xây query và @QueryMapping

Trong Spring for GraphQL, một thao tác đọc bắt đầu từ trường của kiểu gốc Query trong schema SDL. Spring ánh xạ trường đó tới một phương thức Java bằng @QueryMapping; phương thức gọi service để lấy dữ liệu và trả kết quả cho GraphQL runtime. Bài thực hành này xây một API tra cứu sách để thấy đầy đủ luồng từ schema, resolver đến request và kiểm thử.

## 1. Mục tiêu và tình huống

Giả sử ứng dụng quản lý danh mục sách cần cung cấp ba thao tác đọc:

- Lấy toàn bộ sách.
- Tìm một sách theo mã.
- Tìm sách theo từ khóa trong tiêu đề hoặc tên tác giả.

Sau bài này, bạn có thể:

1. Khai báo trường Query và kiểu dữ liệu trả về bằng SDL.
2. Viết controller GraphQL với @Controller và @QueryMapping.
3. Nhận tham số truy vấn bằng @Argument.
4. Chọn kiểu trả về phù hợp và xử lý trường hợp không tìm thấy dữ liệu.
5. Gửi GraphQL query bằng biến và kiểm thử resolver bằng GraphQlTester.

Ta tập trung vào các trường ở cấp Query. Việc phân giải các trường quan hệ lồng nhau và tối ưu N+1 sẽ được xử lý ở các bài về @SchemaMapping, @BatchMapping và DataLoader.

## 2. Chuẩn bị dự án

Dùng ứng dụng Spring Boot có Spring for GraphQL và một HTTP server. Với Maven, các dependency chính là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Spring Boot mặc định tìm schema trong thư mục classpath:graphql/ và cung cấp HTTP endpoint tại /graphql. Tạo file:

~~~text
src/main/resources/graphql/schema.graphqls
~~~

Nếu muốn đổi endpoint, có thể cấu hình trong application.properties:

~~~properties
spring.graphql.path=/graphql
~~~

Giữ nguyên giá trị trên thì không cần khai báo property này. Tên file schema có thể khác, miễn nằm trong vị trí schema mà ứng dụng đang cấu hình.

## 3. Khai báo schema SDL

Tạo schema.graphqls với nội dung:

~~~graphql
type Query {
    books: [Book!]!
    bookById(id: ID!): Book
    searchBooks(keyword: String!): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: String!
    publishedYear: Int!
    price: Float!
}
~~~

Đọc schema theo từng phần:

| Khai báo | Ý nghĩa |
|---|---|
| type Query | Kiểu gốc chứa các thao tác đọc mà client có thể gọi. |
| books: [Book!]! | Trả về một danh sách không null; từng phần tử trong danh sách cũng không null. |
| bookById(id: ID!): Book | Bắt buộc truyền id; kết quả Book có thể null nếu không tìm thấy. |
| searchBooks(keyword: String!): [Book!]! | Bắt buộc truyền từ khóa; kết quả luôn là một danh sách, có thể rỗng. |
| ID! | Mã định danh bắt buộc. ID là kiểu định danh, client không nên phụ thuộc vào việc nó có dạng số hay chuỗi. |
| Float! | Số thực dấu phẩy động; ví dụ này dùng double trong Java. |

Dấu chấm than thể hiện tính không null. Ví dụ, [Book!]! có nghĩa danh sách không được null và không phần tử nào trong danh sách được null. Trong khi đó, Book không có dấu chấm than nên có thể trả về null. Thiết kế này phù hợp với thao tác tìm theo mã: mã hợp lệ về mặt cú pháp nhưng không tồn tại trong dữ liệu thì kết quả là null.

Schema là hợp đồng API. Tên trường, tên đối số và kiểu dữ liệu trong Java cần tương thích với hợp đồng đó. GraphQL chỉ trả về các trường client yêu cầu, nên một request có thể lấy id và title mà không cần nhận toàn bộ thuộc tính của Book.

## 4. Tạo kiểu dữ liệu và service

Dùng Java record để biểu diễn dữ liệu sách:

~~~java
package com.example.bookcatalog.book;

public record Book(
        String id,
        String title,
        String author,
        int publishedYear,
        double price
) {
}
~~~

Tạo service cung cấp dữ liệu mẫu. Trong ứng dụng thực tế, service này có thể gọi repository hoặc một hệ thống lưu trữ khác.

~~~java
package com.example.bookcatalog.book;

import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Locale;
import java.util.Optional;

@Service
public class BookService {

    private final List<Book> books = List.of(
            new Book("B-101", "Spring in Action", "Craig Walls", 2022, 39.90),
            new Book("B-102", "Effective Java", "Joshua Bloch", 2018, 45.00),
            new Book("B-103", "GraphQL in Action", "Samer Buna", 2021, 42.50)
    );

    public List<Book> findAll() {
        return books;
    }

    public Optional<Book> findById(String id) {
        return books.stream()
                .filter(book -> book.id().equals(id))
                .findFirst();
    }

    public List<Book> searchByKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return List.of();
        }

        String normalizedKeyword = keyword.trim().toLowerCase(Locale.ROOT);

        return books.stream()
                .filter(book ->
                        book.title().toLowerCase(Locale.ROOT).contains(normalizedKeyword)
                        || book.author().toLowerCase(Locale.ROOT).contains(normalizedKeyword))
                .toList();
    }
}
~~~

Service chịu trách nhiệm tìm kiếm dữ liệu. Controller GraphQL sẽ nhận request, chuyển các đối số cho service và trả kết quả. Cách chia này giúp resolver không phải chứa chi tiết truy cập dữ liệu, đồng thời cho phép tái sử dụng service từ những luồng khác.

## 5. Viết resolver bằng @QueryMapping

Tạo BookQueryController:

~~~java
package com.example.bookcatalog.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping(name = "searchBooks")
    public List<Book> search(@Argument("keyword") String keyword) {
        return bookService.searchByKeyword(keyword);
    }
}
~~~

Các thành phần quan trọng:

- @Controller đăng ký lớp thành Spring bean để Spring for GraphQL phát hiện các phương thức xử lý dữ liệu.
- @QueryMapping ánh xạ phương thức vào một trường của kiểu gốc Query.
- Nếu không chỉ định tên trong @QueryMapping, Spring dùng tên phương thức làm tên trường GraphQL. Vì vậy phương thức books() xử lý trường books và bookById() xử lý trường bookById.
- Có thể chỉ định tên trường tường minh bằng @QueryMapping(name = "searchBooks"). Trong ví dụ, tên phương thức Java là search nhưng tên trường GraphQL là searchBooks.
- @Argument("id") liên kết đối số id trong SDL với tham số Java id. Ghi rõ tên đối số giúp tránh phụ thuộc vào metadata tên tham số khi biên dịch.
- Kiểu trả về của phương thức được GraphQL runtime chuyển thành giá trị của trường. Một List<Book> trở thành danh sách Book; một Book trở thành đối tượng Book.

Spring GraphQL cũng hỗ trợ khai báo ánh xạ tường minh bằng @SchemaMapping(typeName = "Query", field = "books"). @QueryMapping là cách viết chuyên biệt cho các trường thuộc Query, vì vậy phù hợp hơn cho các resolver đọc ở cấp gốc.

Lưu ý rằng tên trường GraphQL phải tồn tại trong schema. Có một phương thức @QueryMapping không tự động tạo thêm trường vào SDL. Nếu resolver trả về một đối tượng Book, các trường id, title, author, publishedYear và price được đọc từ thuộc tính tương ứng của đối tượng.

## 6. Gửi query và đọc kết quả

### Lấy danh sách sách

Request:

~~~graphql
query {
    books {
        id
        title
        author
    }
}
~~~

Client chỉ yêu cầu ba trường nên response chỉ chứa ba trường đó:

~~~json
{
  "data": {
    "books": [
      {
        "id": "B-101",
        "title": "Spring in Action",
        "author": "Craig Walls"
      },
      {
        "id": "B-102",
        "title": "Effective Java",
        "author": "Joshua Bloch"
      },
      {
        "id": "B-103",
        "title": "GraphQL in Action",
        "author": "Samer Buna"
      }
    ]
  }
}
~~~

### Tìm sách theo mã bằng biến

Nên dùng biến khi đối số thay đổi theo từng request. Query:

~~~graphql
query BookDetail($id: ID!) {
    bookById(id: $id) {
        id
        title
        author
        publishedYear
        price
    }
}
~~~

Giá trị biến:

~~~json
{
  "id": "B-101"
}
~~~

Khi gọi qua HTTP, client gửi POST đến /graphql với body chứa query và variables:

~~~json
{
  "query": "query BookDetail($id: ID!) { bookById(id: $id) { id title author publishedYear price } }",
  "variables": {
    "id": "B-101"
  }
}
~~~

Response khi tìm thấy sách:

~~~json
{
  "data": {
    "bookById": {
      "id": "B-101",
      "title": "Spring in Action",
      "author": "Craig Walls",
      "publishedYear": 2022,
      "price": 39.9
    }
  }
}
~~~

Nếu mã không tồn tại, resolver trả null và response có dạng:

~~~json
{
  "data": {
    "bookById": null
  }
}
~~~

Điều này hợp lệ vì trường bookById được khai báo là Book có thể null. Nếu đổi schema thành Book!, việc trả null sẽ vi phạm hợp đồng non-null và GraphQL tạo lỗi thực thi; giá trị null có thể lan lên trường cha gần nhất cho phép null. Vì vậy cần chọn nullability dựa trên hành vi nghiệp vụ dự kiến.

### Tìm theo từ khóa

Query:

~~~graphql
query SearchBooks($keyword: String!) {
    searchBooks(keyword: $keyword) {
        id
        title
        author
    }
}
~~~

Variables:

~~~json
{
  "keyword": "java"
}
~~~

Kết quả sẽ gồm những sách có tiêu đề hoặc tác giả chứa từ khóa, không phân biệt chữ hoa và chữ thường. Nếu không có kết quả, resolver trả danh sách rỗng. Vì schema khai báo [Book!]!, danh sách rỗng là một kết quả hợp lệ.

## 7. Kiểm thử bằng GraphQlTester

Có thể kiểm thử resolver ở tầng GraphQL bằng @GraphQlTest. Nếu dự án chưa có dependency kiểm thử, bổ sung cả spring-boot-starter-test và spring-graphql-test (scope test):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~java
package com.example.bookcatalog.book;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookQueryController.class)
@Import(BookService.class)
class BookQueryControllerTest {

    @Autowired
    private GraphQlTester graphQlTester;

    @Test
    void shouldReturnBooks() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("books[0].id")
                .entity(String.class)
                .isEqualTo("B-101");
    }

    @Test
    void shouldFindBookById() {
        graphQlTester.document("""
                query BookDetail($id: ID!) {
                    bookById(id: $id) {
                        title
                    }
                }
                """)
                .variable("id", "B-102")
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Effective Java");
    }

    @Test
    void shouldReturnNullWhenBookDoesNotExist() {
        graphQlTester.document("""
                query BookDetail($id: ID!) {
                    bookById(id: $id) {
                        id
                    }
                }
                """)
                .variable("id", "UNKNOWN")
                .execute()
                .path("bookById")
                .valueIsNull();
    }
}
~~~

@GraphQlTest cấu hình test slice cho GraphQL và controller được chỉ định. @Import đưa BookService vào context vì test cần service thật để cung cấp dữ liệu mẫu. GraphQlTester gửi document, truyền biến và kiểm tra dữ liệu tại đường dẫn trong response.

Ba kiểm thử xác nhận các hành vi khác nhau: danh sách có thể được truy vấn, đối số được truyền đúng vào resolver, và trường bookById có thể trả null khi không tìm thấy dữ liệu. Khi chạy test trong dự án, hãy bảo đảm schema.graphqls nằm đúng vị trí và tên trường trong document trùng với SDL.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy trường trong Query | Trường chưa được khai báo trong SDL hoặc tên resolver không khớp. | So sánh tên trong type Query với tên phương thức hoặc thuộc tính name của @QueryMapping. |
| Resolver không được gọi | Lớp thiếu @Controller, không nằm trong component scan hoặc phương thức thiếu @QueryMapping. | Kiểm tra package của ứng dụng và annotation trên controller. |
| Đối số nhận null | Tên đối số trong @Argument không khớp với tên đối số trong SDL. | Dùng @Argument("id") và kiểm tra request có truyền id. |
| Lỗi kiểu dữ liệu | Kiểu Java không tương thích với scalar hoặc cấu trúc SDL. | Đối chiếu String/ID, int/Int, double/Float và kiểu danh sách. |
| Lỗi non-null khi không tìm thấy bản ghi | Resolver trả null trong khi SDL khai báo trường là non-null. | Xem lại nullability hoặc quy ước xử lý trường hợp không tìm thấy. |
| Schema không được tải | File nằm sai thư mục hoặc cấu hình schema locations không bao gồm thư mục chứa file. | Kiểm tra vị trí graphql/schema.graphqls và cấu hình Spring GraphQL. |

Khi gặp lỗi, đọc cả hai phần data và errors trong response. GraphQL có thể trả dữ liệu một phần cùng danh sách lỗi; HTTP status đơn lẻ không mô tả đầy đủ kết quả thực thi của một GraphQL operation.

## 9. Bài tập thực hành

Tiếp tục mở rộng API danh mục sách:

1. Thêm trường latestBooks vào Query để trả về tối đa N sách mới nhất. Khai báo đối số limit trong SDL, nhận nó bằng @Argument và kiểm soát giới hạn đầu vào ở service.
2. Thêm trường booksByYear(year: Int!) để lọc theo năm xuất bản. Viết phương thức service riêng và một resolver bằng @QueryMapping.
3. Viết kiểm thử cho trường hợp danh sách rỗng, mã sách tồn tại và mã sách không tồn tại.
4. Thử đổi kiểu trả về bookById từ Book thành Book! rồi kiểm tra điều gì xảy ra khi resolver trả null. Sau đó khôi phục schema theo quy tắc nghiệp vụ đã chọn.

Tiêu chí hoàn thành: schema mô tả đúng ba thao tác đọc; mỗi trường Query có một resolver tương ứng; đối số được liên kết đúng; response chỉ chứa trường được client yêu cầu; và các trường hợp tìm thấy, không tìm thấy đều có kiểm thử.


