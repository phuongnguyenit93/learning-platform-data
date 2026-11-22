# Viết GraphQlTester cho query

GraphQlTester là API kiểm thử của Spring for GraphQL. Nó cho phép gửi một GraphQL document, truyền variables, thực thi qua GraphQL engine và kiểm tra response theo từng path. Khi kiểm thử Query, ta xác nhận schema nhận đúng trường và đối số, resolver được gọi, dữ liệu được chuyển đổi đúng và lỗi được trả về theo hợp đồng GraphQL.

Bài thực hành sử dụng API danh mục sách với ba thao tác đọc: lấy danh sách, tìm theo mã và tìm theo từ khóa. Ta sẽ viết test ở tầng GraphQL bằng @GraphQlTest, dùng Mockito thay thế service, sau đó kiểm thử endpoint HTTP bằng HttpGraphQlTester.

## 1. Mục tiêu và phạm vi kiểm thử

Sau bài này, bạn có thể cấu hình @GraphQlTest, gửi query bằng GraphQlTester, truyền variables và kiểm tra dữ liệu, nullability, errors cũng như lời gọi service.

Test xác nhận schema, request, mapping, lời gọi service, response và errors. Khi mock service, test tập trung vào luồng GraphQL và resolver.

## 2. Chuẩn bị dependency và schema

Với Maven, các dependency cần thiết gồm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
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

Spring Boot dependency management quản lý version cho các dependency tương ứng. spring-graphql-test cung cấp GraphQlTester và các công cụ kiểm thử GraphQL.

Đặt schema tại src/main/resources/graphql/schema.graphqls:

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

Hai quy tắc nullability ảnh hưởng trực tiếp đến assertion:

- bookById trả về Book có thể null khi không tìm thấy mã sách.
- searchBooks trả về [Book!]!, nghĩa là danh sách và từng phần tử đều không null. Không có kết quả thì resolver trả danh sách rỗng.

## 3. Chuẩn bị resolver

Dùng Java record biểu diễn dữ liệu:

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

Service contract:

~~~java
package com.example.bookcatalog.book;

import java.util.List;
import java.util.Optional;

public interface BookService {
    List<Book> findAll();
    Optional<Book> findById(String id);
    List<Book> searchByKeyword(String keyword);
}
~~~

Resolver:

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

Spring dùng tên phương thức làm tên trường GraphQL nếu @QueryMapping không chỉ định name. Với searchBooks, thuộc tính name ánh xạ tên trường SDL tới phương thức Java search.

Trong test slice, BookService được thay bằng mock. Ta chủ động thiết lập dữ liệu trả về và xác minh resolver truyền đúng tham số xuống service.

## 4. Cách sử dụng GraphQlTester

Một test GraphQL cơ bản gồm các bước:

1. document(...) tạo GraphQL operation.
2. variable(...) truyền giá trị cho biến.
3. execute() thực thi document.
4. errors() kiểm tra lỗi trong response.
5. path(...) chọn trường cần kiểm tra.
6. entity(...) hoặc entityList(...) chuyển dữ liệu thành kiểu Java.

Ví dụ:

~~~java
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
        .verify()
        .path("books[0].id")
        .entity(String.class)
        .isEqualTo("B-101");
~~~

errors().verify() xác nhận response không có GraphQL errors. path("books[0].id") chọn id của phần tử đầu tiên. entity(String.class) chuyển giá trị thành String để assertion.

Đường dẫn trong path được tính từ phần data của response, không cần thêm tiền tố data. Với response có data.books[0].id, path cần dùng là books[0].id.

GraphQlTester thường dùng path(...) để chọn trường, entity(...) để đọc object hoặc giá trị đơn, entityList(...) để đọc danh sách, valueIsNull() để kiểm tra null và errors() để kiểm tra lỗi.

Với query chỉ chọn một vài thuộc tính, hãy kiểm tra từng path thay vì ánh xạ response thiếu trường vào một record có nhiều thuộc tính.

## 5. Viết test bằng @GraphQlTest

@GraphQlTest tạo test slice cho Spring for GraphQL. Spring cấu hình schema, GraphQL infrastructure và controller được chỉ định. Các dependency của controller có thể được thay bằng mock.

~~~java
package com.example.bookcatalog.book;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.graphql.test.tester.GraphQlTester;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@GraphQlTest(BookQueryController.class)
class BookQueryControllerGraphQlTest {

    @Autowired
    private GraphQlTester graphQlTester;

    @MockBean
    private BookService bookService;

    // Đặt các test case tại đây.
}
~~~

@GraphQlTest giới hạn Spring context vào phần cần cho GraphQL test. @MockBean đăng ký mock BookService để controller được khởi tạo. GraphQlTester được Spring Boot cấu hình và inject vào test.

Với Spring Framework mới hỗ trợ @MockitoBean, có thể dùng annotation đó thay cho @MockBean.

### 5.1. Kiểm thử query lấy danh sách

~~~java
@Test
void shouldReturnBooks() {
    Book first = new Book(
            "B-101", "Spring in Action", "Craig Walls", 2022, 39.90
    );
    Book second = new Book(
            "B-102", "Effective Java", "Joshua Bloch", 2018, 45.00
    );

    given(bookService.findAll()).willReturn(List.of(first, second));

    graphQlTester.document("""
            query {
                books {
                    id
                    title
                    author
                    publishedYear
                    price
                }
            }
            """)
            .execute()
            .errors()
            .verify()
            .path("books")
            .entityList(Book.class)
            .containsExactly(first, second);

    verify(bookService).findAll();
}
~~~

Test xác nhận trường books được thực thi, dữ liệu được ánh xạ thành danh sách Book đúng thứ tự và resolver gọi findAll(). Ta chọn đủ các trường của Book để so sánh record với dữ liệu mẫu.

Nếu query chỉ chọn một vài thuộc tính, hãy kiểm tra các path tương ứng thay vì so sánh toàn bộ Book.

### 5.2. Kiểm thử query có biến

Khi đối số thay đổi theo từng request, nên dùng GraphQL variables thay vì ghép giá trị vào chuỗi query.

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

~~~java
@Test
void shouldReturnBookById() {
    Book expected = new Book(
            "B-102", "Effective Java", "Joshua Bloch", 2018, 45.00
    );

    given(bookService.findById("B-102"))
            .willReturn(Optional.of(expected));

    graphQlTester.document("""
            query BookDetail($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                    author
                    publishedYear
                    price
                }
            }
            """)
            .variable("id", "B-102")
            .execute()
            .errors()
            .verify()
            .path("bookById")
            .entity(Book.class)
            .isEqualTo(expected);

    verify(bookService).findById("B-102");
}
~~~

variable("id", "B-102") truyền giá trị cho biến $id. GraphQL runtime kiểm tra biến với khai báo ID! trong operation. Resolver nhận đối số id thông qua @Argument("id").

Test phát hiện tên biến hoặc đối số không khớp, resolver ánh xạ sai trường và kiểu trả về không tương thích với schema.

### 5.3. Kiểm thử danh sách rỗng

~~~java
@Test
void shouldReturnEmptyListWhenSearchHasNoResult() {
    given(bookService.searchByKeyword("unknown"))
            .willReturn(List.of());

    graphQlTester.document("""
            query SearchBooks($keyword: String!) {
                searchBooks(keyword: $keyword) {
                    id
                    title
                }
            }
            """)
            .variable("keyword", "unknown")
            .execute()
            .errors()
            .verify()
            .path("searchBooks")
            .entityList(Book.class)
            .hasSize(0);
}
~~~

Query vẫn phải chọn ít nhất một trường của Book vì GraphQL yêu cầu selection set cho kiểu object. Với danh sách rỗng, assertion chỉ kiểm tra số phần tử nên không cần so sánh object.

### 5.4. Kiểm thử trường nullable

Khi không tìm thấy sách, service trả Optional.empty() và resolver chuyển thành null. Vì SDL khai báo bookById có thể null, response hợp lệ:

~~~java
@Test
void shouldReturnNullWhenBookDoesNotExist() {
    given(bookService.findById("UNKNOWN"))
            .willReturn(Optional.empty());

    graphQlTester.document("""
            query BookDetail($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "UNKNOWN")
            .execute()
            .errors()
            .verify()
            .path("bookById")
            .valueIsNull();
}
~~~

Không dùng valueIsNull() để kiểm tra danh sách không có phần tử. Danh sách rỗng và giá trị null là hai kết quả khác nhau theo hợp đồng SDL.

### 5.5. Kiểm thử GraphQL errors

GraphQL response có thể chứa data cùng errors. Khi resolver phát sinh lỗi, GraphQL engine có thể trả dữ liệu một phần và ghi lỗi tương ứng trong errors.

~~~java
@Test
void shouldExposeGraphQlExecutionError() {
    given(bookService.findById("B-500"))
            .willThrow(new IllegalStateException("Book store unavailable"));

    var response = graphQlTester.document("""
            query BookDetail($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "B-500")
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).isNotEmpty();
    });
}
~~~

Test xác nhận lỗi thực thi xuất hiện trong response. Thông điệp và mã lỗi phụ thuộc vào DataFetcherExceptionResolver hoặc cơ chế xử lý exception. Nếu API cam kết mã lỗi, hãy kiểm tra mã hoặc extension công khai thay vì exception nội bộ.

Có thể kiểm tra lỗi validation bằng một query thiếu đối số bắt buộc:

~~~java
@Test
void shouldRejectQueryWithoutRequiredArgument() {
    var response = graphQlTester.document("""
            query {
                bookById {
                    id
                }
            }
            """)
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).isNotEmpty();
    });
}
~~~

Query vi phạm khai báo id: ID! trong schema. Resolver không nên được gọi vì GraphQL validation từ chối operation trước khi thực thi.

## 6. Kiểm thử qua HTTP bằng HttpGraphQlTester

@GraphQlTest phù hợp để kiểm tra schema, resolver và cách GraphQL engine xử lý query. Nó không khởi chạy toàn bộ ứng dụng qua HTTP endpoint thực.

Nếu cần xác nhận request đi qua web server và endpoint /graphql, dùng HttpGraphQlTester trong integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookQueryHttpTest {

    @Autowired
    private HttpGraphQlTester graphQlTester;

    @Test
    void shouldQueryBookThroughHttpEndpoint() {
        graphQlTester.document("query { books { id title } }")
                .execute().errors().verify()
                .path("books[0].id").entity(String.class)
                .isEqualTo("B-101");
    }
}
~~~

@SpringBootTest khởi động ứng dụng trong môi trường test. RANDOM_PORT cấp một cổng HTTP ngẫu nhiên. @AutoConfigureHttpGraphQlTester cấu hình tester để gửi request tới GraphQL endpoint của ứng dụng.

Test HTTP sử dụng service và dữ liệu của application context thật. Hãy nạp fixture có sách B-101 trong test profile hoặc database kiểm thử để assertion có dữ liệu ổn định.

| Tiêu chí | @GraphQlTest | HttpGraphQlTester |
|---|---|---|
| Mục tiêu | Schema và resolver | Luồng HTTP tích hợp |
| Spring context | Test slice | Toàn bộ application context |
| HTTP server | Không cần endpoint thật | Có server trên cổng ngẫu nhiên |
| Tốc độ | Thường nhanh hơn | Thường chậm hơn |
| Phù hợp | Mapping, variables, response, lỗi resolver | Endpoint và cấu hình web |

Dùng test slice cho phần lớn kiểm thử resolver. Dành integration test cho những hành vi cần xác nhận qua HTTP.

## 7. Lỗi thường gặp

| Hiện tượng | Nguyên nhân và hướng xử lý |
|---|---|
| Không inject được GraphQlTester | Kiểm tra spring-graphql-test và annotation test. |
| Controller không được khởi tạo | Đưa controller vào phạm vi @GraphQlTest. |
| Không inject được service | Dùng @MockBean hoặc @MockitoBean. |
| Không tìm thấy trường hoặc biến | Đối chiếu SDL, @QueryMapping, variable(...) và @Argument. |
| Path không tồn tại hoặc nhận lỗi thay vì null | Kiểm tra selection set, path, nullability và errors. |
| HTTP test không kết nối được | Kiểm tra @SpringBootTest và @AutoConfigureHttpGraphQlTester. |

Hãy dùng errors().verify() trong test mong đợi thành công. Với test chuyên kiểm tra lỗi, dùng errors().satisfy(...) để xác nhận lỗi xuất hiện theo điều kiện mong muốn.

Không nên chỉ gọi trực tiếp phương thức controller để kiểm thử GraphQL. Cách đó bỏ qua schema parsing, field mapping, argument binding và serialization. Hãy gửi document qua GraphQlTester để kiểm tra đúng hợp đồng API.

## 8. Bài tập thực hành

Hoàn thiện bộ kiểm thử cho API danh mục sách:

1. Kiểm tra books trả về đúng hai phần tử và đúng thứ tự.
2. Kiểm tra bookById bằng variable id, cả khi tìm thấy và không tìm thấy.
3. Kiểm tra searchBooks trả danh sách rỗng khi không có kết quả.
4. Kiểm tra lỗi thực thi hoặc query thiếu đối số bắt buộc.
5. Dùng Mockito verify và thêm một integration test HTTP nếu cần xác nhận endpoint.

Tiêu chí hoàn thành: các trường Query có test thành công; variables được truyền đúng; dữ liệu, null, danh sách rỗng và errors được phân biệt; assertion kiểm tra đúng path và nullability; service được mock ở resolver test và endpoint được kiểm tra qua HTTP khi cần.

Khi mở rộng API, hãy gửi document như client thực sự gửi và kiểm tra response như client thực sự nhận. Chỉ mock dependency nằm ngoài phạm vi của test. Nhờ vậy, bộ kiểm thử GraphQlTester bảo vệ hợp đồng API khi schema hoặc resolver thay đổi.

