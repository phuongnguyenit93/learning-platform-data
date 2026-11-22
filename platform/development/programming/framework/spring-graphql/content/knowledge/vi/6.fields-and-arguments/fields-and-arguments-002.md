# Argument bắt buộc trong GraphQL và Spring for GraphQL

Trong GraphQL, một argument được xem là bắt buộc khi kiểu của nó là **Non-Null** (có dấu `!`) và không có giá trị mặc định. Quy tắc này được khai báo ngay trong schema SDL, vì vậy GraphQL có thể từ chối request thiếu argument hoặc truyền `null` trước khi gọi resolver.

Spring for GraphQL sử dụng schema đã được kiểm tra để bind giá trị hợp lệ vào tham số Java bằng `@Argument`. Điều này giúp chữ ký của API thể hiện rõ dữ liệu client phải cung cấp, đồng thời giúp server phát hiện request sai ngay ở bước validation và input coercion.

## 1. Argument bắt buộc là gì?

GraphQL phân biệt kiểu nullable và non-null:

- `String` cho phép giá trị `null`.
- `String!` không cho phép giá trị `null`.
- `ID!` yêu cầu một giá trị ID khác `null`.
- `[ID!]!` yêu cầu danh sách không null và mọi phần tử trong danh sách cũng không null.

Ví dụ schema khai báo một query tìm sách:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

`id: ID!` là argument bắt buộc. Client phải cung cấp `id` và không được truyền `null`. Kiểu trả về `Book` không có dấu `!`, nên query vẫn có thể trả `null` nếu không tìm thấy sách. Nullability của argument và nullability của kết quả là hai cam kết độc lập.

GraphQL định nghĩa một argument là *required argument* khi argument có kiểu Non-Null và không có default value. Vì vậy, dấu `!` là điều kiện quan trọng, nhưng khi đọc schema cũng phải kiểm tra xem argument có giá trị mặc định hay không.

## 2. Thiếu argument và truyền null là hai trường hợp khác nhau

Với khai báo `book(id: ID!)`, cả hai request sau đều không hợp lệ.

**Thiếu argument:**

~~~graphql
query {
    book {
        id
        title
    }
}
~~~

**Truyền null:**

~~~graphql
query {
    book(id: null) {
        id
        title
    }
}
~~~

Trường hợp thứ nhất không cung cấp argument. Trường hợp thứ hai có cung cấp argument nhưng giá trị là `null`. Cả hai vi phạm hợp đồng Non-Null, nên GraphQL trả lỗi request và không gọi resolver `book`.

Nếu argument là nullable, hai trường hợp này có thể được phân biệt:

~~~graphql
type Query {
    books(keyword: String): [Book!]!
}
~~~

Với `keyword: String`, client có thể bỏ qua argument hoặc truyền `null`. Server có thể áp dụng quy tắc riêng cho từng tình huống, chẳng hạn không lọc khi không có keyword. Nếu nghiệp vụ cần phân biệt rõ “không gửi điều kiện” với “gửi null”, hãy thiết kế input và quy tắc xử lý có chủ đích.

## 3. Khai báo argument bắt buộc trong SDL

### 3.1. Argument đơn giản

Các scalar thường được dùng làm argument bắt buộc gồm `ID!`, `String!`, `Int!`, `Float!` và `Boolean!`:

~~~graphql
type Query {
    book(id: ID!): Book
    books(first: Int!, published: Boolean!): [Book!]!
}
~~~

Client phải truyền đủ cả `first` và `published` khi gọi `books`. Giá trị `false` của Boolean vẫn là giá trị hợp lệ; Non-Null chỉ cấm `null`, không yêu cầu giá trị phải là `true` hoặc khác giá trị mặc định của Java.

Tương tự, `String!` vẫn chấp nhận chuỗi rỗng `""`. Dấu `!` chỉ kiểm tra nullability, không kiểm tra chuỗi có nội dung, số có nằm trong khoảng nghiệp vụ hay ID có tồn tại trong cơ sở dữ liệu.

### 3.2. Argument dạng input object

Khi thao tác cần nhiều dữ liệu, nên gom các giá trị vào input object. Ví dụ mutation tạo sách:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    subtitle: String
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Có hai cấp bắt buộc:

1. `input: CreateBookInput!` yêu cầu client truyền input object.
2. Bên trong object, `title` và `authorId` cũng bắt buộc vì có kiểu Non-Null và không có default value.

`subtitle: String` là nullable nên client có thể bỏ qua hoặc truyền `null`. Nếu truyền một object nhưng thiếu `title` hoặc `authorId`, input coercion thất bại và resolver mutation không được gọi.

Ví dụ hợp lệ:

~~~graphql
mutation CreateBook {
    createBook(input: {
        title: "GraphQL thực hành"
        authorId: "author-12"
    }) {
        id
        title
    }
}
~~~

Ví dụ không hợp lệ vì thiếu `authorId`:

~~~graphql
mutation CreateBook {
    createBook(input: {
        title: "GraphQL thực hành"
    }) {
        id
    }
}
~~~

Input object giúp API có cấu trúc rõ ràng và dễ mở rộng. Khi thêm field mới, hãy cân nhắc khả năng tương thích với client hiện tại; thêm một field Non-Null không có default vào input object đang được sử dụng có thể làm các request cũ trở nên không hợp lệ.

### 3.3. Argument là danh sách

GraphQL cho phép ràng buộc nullability ở cấp danh sách và phần tử:

| Kiểu | Ý nghĩa |
| --- | --- |
| `[ID]` | Danh sách có thể null, phần tử có thể null |
| `[ID!]` | Danh sách có thể null, phần tử không thể null |
| `[ID]!` | Danh sách không thể null, phần tử có thể null |
| `[ID!]!` | Danh sách không thể null, phần tử không thể null |

Ví dụ:

~~~graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
~~~

Client phải gửi một danh sách khác null. Danh sách rỗng `[]` hợp lệ, nhưng danh sách chứa phần tử null không hợp lệ. Nếu nghiệp vụ yêu cầu danh sách phải có ít nhất một ID, cần kiểm tra điều kiện đó ở tầng validation hoặc service; `[ID!]!` không tự áp đặt kích thước tối thiểu.

## 4. Default value và ý nghĩa của dấu !

Một argument Non-Null có default value không còn là *required argument* theo định nghĩa của GraphQL. Client có thể bỏ qua argument và server dùng giá trị mặc định. Tuy nhiên, nếu client chủ động truyền `null`, request vẫn không hợp lệ.

~~~graphql
type Query {
    books(first: Int! = 20): [Book!]!
}
~~~

Với khai báo này:

- `books` không truyền `first`: GraphQL dùng giá trị `20`.
- `books(first: 5)`: GraphQL dùng giá trị `5`.
- `books(first: null)`: GraphQL từ chối request vì `Int!` không nhận null.

Do đó, nếu yêu cầu nghiệp vụ là client luôn phải cung cấp giá trị, không khai báo default value cho argument Non-Null.

Input object field cũng có thể có default:

~~~graphql
input BookSearchInput {
    keyword: String!
    page: Int! = 1
    pageSize: Int! = 20
}
~~~

`keyword` là field bắt buộc; `page` và `pageSize` có thể được bỏ qua vì có default. Nếu client truyền `page: null`, request vẫn lỗi.

## 5. Argument bắt buộc khi dùng GraphQL variables

Trong ứng dụng thực tế, client thường tách giá trị khỏi GraphQL document bằng variables. Kiểu của biến phải tương thích với vị trí argument mà nó được sử dụng.

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Request hợp lệ gửi variables:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-101"
    }
}
~~~

Nếu object `variables` không có key `id`, biến Non-Null không có default bị thiếu và operation không thể thực thi. Nếu gửi `"id": null`, input coercion cũng thất bại. Cả hai đều không gọi resolver.

### 5.1. Default value của variable

Variable cũng có thể có default value:

~~~graphql
query FindBook($id: ID! = "book-101") {
    book(id: $id) {
        id
        title
    }
}
~~~

Trong trường hợp này, client có thể bỏ qua variable `id` và GraphQL dùng default `book-101`. Giá trị `null` được truyền tường minh vẫn không hợp lệ. Cần phân biệt default của variable với default khai báo trên argument trong schema; cả hai đều có thể cung cấp giá trị khi client bỏ qua, nhưng nằm ở hai vị trí khác nhau của hợp đồng.

### 5.2. Variable phải tương thích với argument

Khi argument yêu cầu `ID!`, biến `$id: ID!` là lựa chọn trực tiếp và rõ ràng. Biến nullable `$id: ID` không thể tùy tiện dùng ở vị trí Non-Null vì GraphQL không thể bảo đảm nó không null tại thời điểm thực thi. Một số trường hợp có default ở variable hoặc ở argument có thể đáp ứng quy tắc tương thích của GraphQL, nhưng không nên dựa vào ngoại lệ đó nếu mục tiêu là biểu diễn một giá trị bắt buộc. Hãy khai báo variable Non-Null khi client cần cung cấp giá trị.

## 6. Spring for GraphQL bind argument bắt buộc bằng @Argument

Spring for GraphQL ánh xạ argument từ GraphQL field vào tham số method thông qua `@Argument`. Schema chịu trách nhiệm xác định request có hợp lệ hay không; `@Argument` thực hiện binding giá trị đã được GraphQL chấp nhận.

Ví dụ resolver cho query `book(id: ID!)`:

~~~java
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
    public Book book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

`@Argument("id")` lấy đúng argument có tên `id`. Với argument bắt buộc, GraphQL đã kiểm tra giá trị trước khi gọi method, vì vậy resolver nhận một giá trị hợp lệ theo kiểu GraphQL. Không cần lặp lại kiểm tra null chỉ để bù cho một schema đã khai báo đúng Non-Null; vẫn cần kiểm tra các quy tắc nghiệp vụ khác như ID có tồn tại hay người dùng có quyền truy cập.

### 6.1. Bind input object vào Java record

Với mutation nhận `CreateBookInput!`, có thể bind vào Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        String subtitle
) {}
~~~

~~~java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Valid CreateBookInput input
    ) {
        return bookService.create(input);
    }
}
~~~

Spring chuyển input object thành `CreateBookInput`. GraphQL đã xác nhận `input`, `title` và `authorId` có mặt, khác null theo SDL. `@Valid` có thể được dùng thêm để chạy Bean Validation nếu ứng dụng có Jakarta Validation provider và constraint tương ứng.

### 6.2. Non-Null không thay thế Bean Validation

SDL `title: String!` chỉ bảo đảm giá trị khác null. Nếu muốn từ chối chuỗi rỗng hoặc chỉ chứa khoảng trắng, khai báo constraint ở Java:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId,
        String subtitle
) {}
~~~

Hai tầng validation giải quyết hai vấn đề khác nhau:

| Tầng | Ví dụ kiểm tra |
| --- | --- |
| GraphQL schema và input coercion | Argument bắt buộc có được cung cấp không? Giá trị có phải null không? Kiểu có đúng không? |
| Bean Validation | Chuỗi có rỗng không? Số có nằm trong khoảng cho phép không? Field có tuân thủ constraint ứng dụng không? |
| Service/domain | Tác giả có tồn tại không? Người dùng có quyền tạo sách không? Quy tắc nghiệp vụ có được đáp ứng không? |

Không nên dựa vào SDL để kiểm tra mọi quy tắc nghiệp vụ. Ngược lại, không nên chờ đến service mới phát hiện một argument bắt buộc bị thiếu, vì schema đã có thể mô tả điều đó rõ ràng.

## 7. GraphQL xử lý lỗi argument bắt buộc như thế nào?

GraphQL kiểm tra document, argument và variables trước khi thực thi resolver. Nếu request thiếu argument Non-Null, truyền `null` vào vị trí Non-Null hoặc thiếu field bắt buộc trong input object, GraphQL tạo request error.

Ví dụ client gửi:

~~~graphql
query {
    book(id: null) {
        id
    }
}
~~~

Response sẽ chứa `errors` mô tả vi phạm argument Non-Null. Vì lỗi xảy ra trước khi thực thi, GraphQL không gọi `BookController.book(...)`; đây không phải lỗi phát sinh từ service hoặc database.

Điều này khác với trường hợp resolver chạy thành công nhưng không tìm thấy sách. Với schema `book(id: ID!): Book`, resolver có thể trả `null` cho kết quả không tồn tại và response có `data.book: null`. Argument vẫn hợp lệ, chỉ có kết quả nghiệp vụ là không tìm thấy dữ liệu.

Nếu resolver trả null cho một field output được khai báo Non-Null, GraphQL sẽ tạo execution error và áp dụng null propagation lên field cha gần nhất có thể nhận null. Đừng nhầm lỗi này với lỗi request do client bỏ qua một argument bắt buộc.

## 8. Kiểm thử argument bắt buộc bằng GraphQlTester

Nên kiểm tra cả request hợp lệ lẫn các trường hợp thiếu argument và truyền null. Ví dụ với `GraphQlTester` trong test của Spring for GraphQL:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@GraphQlTest(BookController.class)
class RequiredArgumentTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @BeforeEach
    void setUp() {
        given(bookService.findById("book-101"))
                .willReturn(Optional.of(new Book("book-101", "GraphQL thực hành")));
    }

    @Test
    void acceptsRequiredId() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                    }
                }
                """)
            .variable("id", "book-101")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-101");
    }

    @Test
    void rejectsMissingRequiredVariable() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                    }
                }
                """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }

    @Test
    void rejectsNullRequiredVariable() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                    }
                }
                """)
            .variable("id", null)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }
}
~~~

Ví dụ giả định `BookController` có trong GraphQL test slice và service được cấu hình hoặc mock để trả về sách có ID `book-101`. Các test lỗi xác nhận request bị từ chối ở tầng GraphQL; nếu cần chứng minh resolver không được gọi, có thể verify mock service không có tương tác tương ứng.

Nên bổ sung test cho các tình huống:

1. Thiếu argument ngay trong field, ví dụ `{ book { id } }`.
2. Argument Non-Null được truyền `null` trực tiếp.
3. Thiếu variable Non-Null trong map `variables`.
4. Variable Non-Null được truyền giá trị `null`.
5. Input object thiếu field Non-Null hoặc truyền field đó bằng `null`.
6. Argument Non-Null có default value: bỏ qua được nhưng truyền `null` bị từ chối.
7. Giá trị khác null nhưng vi phạm Bean Validation hoặc quy tắc nghiệp vụ.

## 9. Thiết kế API khi thêm argument bắt buộc

Thêm một argument bắt buộc vào field đã được client sử dụng là thay đổi có thể phá vỡ tương thích. Client cũ chưa gửi argument mới sẽ bị GraphQL từ chối trước khi resolver chạy.

Ví dụ API cũ:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Nếu đổi thành:

~~~graphql
type Query {
    books(tenantId: ID!): [Book!]!
}
~~~

mọi client đang gọi `books` phải được cập nhật để truyền `tenantId`. Trước khi thay đổi, hãy cân nhắc:

- Có thể lấy tenant từ principal hoặc GraphQLContext đã được xác thực thay vì yêu cầu client truyền hay không?
- Có thể thêm argument nullable trong giai đoạn chuyển tiếp và xác định rõ cách xử lý khi không có giá trị hay không?
- Có default value an toàn, đúng nghiệp vụ cho mọi client hay không?
- Các client, ứng dụng mobile và tích hợp bên ngoài đã được cập nhật chưa?

Không nên đặt default value tùy tiện chỉ để tránh lỗi tương thích. Giá trị mặc định phải có ý nghĩa nghiệp vụ rõ ràng và không được làm lộ dữ liệu giữa các tenant hoặc bỏ qua quy tắc bảo mật.

## 10. Những điểm cần nhớ

- Argument bắt buộc là Non-Null và không có default value.
- Thiếu argument và truyền `null` là hai lỗi khác nhau nhưng đều vi phạm Non-Null.
- Input object có thể chứa nhiều field bắt buộc; mỗi field được kiểm tra theo kiểu và default riêng.
- Non-Null không đồng nghĩa chuỗi không rỗng, số nằm trong khoảng hợp lệ hoặc ID tồn tại.
- GraphQL kiểm tra request trước khi gọi resolver; `@Argument` bind giá trị đã hợp lệ vào Java.
- Bean Validation và service tiếp tục kiểm tra constraint và quy tắc nghiệp vụ.
- Thêm argument bắt buộc vào schema đã công bố có thể phá vỡ client cũ.

## Tài liệu tham khảo

- [GraphQL Specification — Required Arguments](https://spec.graphql.org/October2021/#sec-Required-Arguments)
- [GraphQL Specification — Non-Null](https://spec.graphql.org/October2021/#sec-Non-Null)
- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
