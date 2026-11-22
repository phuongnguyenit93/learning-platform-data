# Enum input

Trong GraphQL, **enum** là kiểu dữ liệu liệt kê một tập giá trị hữu hạn mà schema cho phép. Khi dùng enum làm input, client chỉ có thể gửi một trong những giá trị đã được khai báo. Điều này giúp API thể hiện rõ các lựa chọn hợp lệ, chẳng hạn trạng thái đơn hàng, thể loại sách, vai trò hoặc hướng sắp xếp.

Với Spring for GraphQL, enum trong SDL có thể được ánh xạ vào Java enum để controller và service làm việc với kiểu dữ liệu rõ ràng. Bài học này trình bày cách khai báo enum, truyền enum qua argument và input object, cách GraphQL kiểm tra giá trị, cũng như những điểm cần chú ý khi thay đổi enum trong API.

## 1. Enum trong GraphQL là gì?

Enum được khai báo bằng từ khóa `enum`, sau đó là tên kiểu và danh sách các giá trị:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}
~~~

`BookGenre` là một enum type với bốn giá trị được phép. Client có thể sử dụng các giá trị này khi truyền argument hoặc field thuộc input object.

Enum khác scalar như `String` ở chỗ nó giới hạn tập giá trị. Với một argument kiểu String, client có thể gửi gần như bất kỳ chuỗi nào. Với argument kiểu BookGenre, chỉ bốn giá trị được định nghĩa trong schema được chấp nhận.

Ví dụ:

~~~graphql
type Query {
    booksByGenre(genre: BookGenre!): [Book!]!
}
~~~

Field `booksByGenre` yêu cầu argument `genre` khác null và phải thuộc enum BookGenre.

## 2. Truyền enum trong GraphQL operation

Khi viết giá trị enum trực tiếp trong GraphQL document, dùng tên enum value mà không đặt trong dấu nháy:

~~~graphql
query {
    booksByGenre(genre: TECHNOLOGY) {
        id
        title
    }
}
~~~

`TECHNOLOGY` là enum literal. Nếu viết thành chuỗi:

~~~graphql
query {
    booksByGenre(genre: "TECHNOLOGY") {
        id
        title
    }
}
~~~

request không hợp lệ vì `"TECHNOLOGY"` là String literal, trong khi schema yêu cầu BookGenre. GraphQL kiểm tra kiểu của literal trước khi thực thi resolver.

### Truyền enum bằng variables

Trong ứng dụng thực tế, nên dùng variables để tách dữ liệu đầu vào khỏi operation document:

~~~graphql
query BooksByGenre($genre: BookGenre!) {
    booksByGenre(genre: $genre) {
        id
        title
    }
}
~~~

Request variables là JSON:

~~~json
{
    "genre": "TECHNOLOGY"
}
~~~

Ở đây chuỗi JSON phải có dấu nháy theo cú pháp JSON. GraphQL sẽ chuyển giá trị chuỗi đó thành enum value tương ứng dựa trên kiểu BookGenre đã khai báo.

Phân biệt hai cú pháp:

| Vị trí | Cách viết |
| --- | --- |
| GraphQL literal | `genre: TECHNOLOGY` |
| JSON variables | `{"genre": "TECHNOLOGY"}` |
| String literal trong GraphQL | `genre: "TECHNOLOGY"` — sai kiểu nếu argument yêu cầu BookGenre |

Tên enum value phân biệt chữ hoa và chữ thường. `TECHNOLOGY` và `technology` là hai tên khác nhau; nếu schema chỉ khai báo TECHNOLOGY thì giá trị viết thường không hợp lệ.

## 3. Dùng enum bên trong input object

Enum thường được kết hợp với input object để mô tả bộ lọc có cấu trúc:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilterInput {
    keyword: String
    genre: BookGenre
    includeOutOfPrint: Boolean = false
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Client gửi:

~~~graphql
query SearchBooks($filter: BookFilterInput) {
    books(filter: $filter) {
        id
        title
        genre
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY",
        "includeOutOfPrint": false
    }
}
~~~

GraphQL kiểm tra cả cấu trúc BookFilterInput và giá trị của field genre. Nếu genre không thuộc BookGenre, request bị từ chối trước khi resolver nhận dữ liệu.

Enum cũng có thể được dùng trong list:

~~~graphql
input BookSearchInput {
    genres: [BookGenre!]
}
~~~

Client có thể truyền nhiều giá trị:

~~~json
{
    "genres": ["TECHNOLOGY", "SCIENCE"]
}
~~~

`[BookGenre!]` cho phép list có thể null, nhưng từng phần tử trong list không được null. Nếu cần list và tất cả phần tử đều bắt buộc khác null, dùng `[BookGenre!]!`.

## 4. Enum có thể dùng cho cả input và output

Một enum type không chỉ dành cho input. Cùng một enum có thể được dùng làm argument, field trong input object và kiểu trả về của output field.

~~~graphql
enum OrderStatus {
    PENDING
    CONFIRMED
    SHIPPING
    COMPLETED
    CANCELLED
}

input OrderFilterInput {
    status: OrderStatus
}

type Order {
    id: ID!
    status: OrderStatus!
}

type Query {
    order(id: ID!): Order
    orders(filter: OrderFilterInput): [Order!]!
}
~~~

Client có thể lọc theo trạng thái và nhận trạng thái của từng đơn hàng:

~~~graphql
query OrdersByStatus($filter: OrderFilterInput) {
    orders(filter: $filter) {
        id
        status
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "status": "SHIPPING"
    }
}
~~~

Response:

~~~json
{
    "data": {
        "orders": [
            {
                "id": "order-1001",
                "status": "SHIPPING"
            }
        ]
    }
}
~~~

Khi enum xuất hiện trong response, GraphQL serialize giá trị nội bộ thành tên enum value mà schema công bố. Client nhận một trong các tên enum đã định nghĩa, không phải một chuỗi trạng thái tùy ý.

## 5. Ánh xạ enum input vào Java trong Spring for GraphQL

Cách đơn giản và dễ bảo trì là đặt tên Java enum trùng với enum value trong SDL.

GraphQL SDL:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

type Query {
    booksByGenre(genre: BookGenre!): [Book!]!
}
~~~

Java enum:

~~~java
package com.example.catalog.book;

public enum BookGenre {
    TECHNOLOGY,
    SCIENCE,
    HISTORY,
    FICTION
}
~~~

Resolver dùng `@Argument`:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookGenre;
import com.example.catalog.book.BookService;
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
    public List<Book> booksByGenre(@Argument("genre") BookGenre genre) {
        return bookService.findByGenre(genre);
    }
}
~~~

Spring for GraphQL nhận argument đã được GraphQL kiểm tra và bind vào tham số Java. Khi tên enum value trong schema tương ứng với tên constant Java, việc ánh xạ thường rất trực tiếp.

Service nhận kiểu BookGenre thay vì String:

~~~java
@Service
public class BookService {

    public List<Book> findByGenre(BookGenre genre) {
        return bookRepository.findByGenre(genre);
    }
}
~~~

Cách này giúp compiler hỗ trợ kiểm tra kiểu. Trong code nghiệp vụ, không cần so sánh chuỗi như `"TECHNOLOGY"` hoặc tự kiểm tra một danh sách tên hợp lệ.

Nếu tên enum trong SDL khác tên constant Java hoặc cần ánh xạ sang một giá trị nội bộ khác, phải cấu hình enum value mapping hoặc cơ chế chuyển đổi tương ứng trong GraphQL runtime. Không nên mặc định rằng tên khác nhau sẽ tự động được chuyển đổi đúng.

## 6. Bind enum trong Java input object

Khi enum nằm trong input object, khai báo thuộc tính Java bằng enum tương ứng.

SDL:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilterInput {
    keyword: String
    genre: BookGenre
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Java DTO:

~~~java
package com.example.catalog.book;

public record BookFilterInput(
        String keyword,
        BookGenre genre
) {
}
~~~

Controller:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument("filter") BookFilterInput filter) {
        return bookService.search(filter);
    }
}
~~~

Khi client truyền:

~~~json
{
    "filter": {
        "keyword": "GraphQL",
        "genre": "TECHNOLOGY"
    }
}
~~~

field genre được bind thành BookGenre.TECHNOLOGY trong Java object. Nếu client bỏ qua genre hoặc truyền null, thuộc tính Java có thể nhận null vì field trong SDL là nullable. Service cần xử lý trường hợp đó theo ý nghĩa của bộ lọc, ví dụ không áp dụng điều kiện genre.

Nếu schema khai báo `genre: BookGenre!`, client phải cung cấp một enum value hợp lệ và khác null. Kiểu Java cũng nên thể hiện đúng cam kết đó trong quy tắc xử lý của ứng dụng.

## 7. Default value và null với enum

Enum argument hoặc input field có thể khai báo giá trị mặc định. Giá trị mặc định trong SDL dùng enum literal không có dấu nháy:

~~~graphql
enum SortDirection {
    ASC
    DESC
}

input BookSortInput {
    direction: SortDirection = ASC
}

type Query {
    books(sort: BookSortInput): [Book!]!
}
~~~

Khi client bỏ qua direction, GraphQL sử dụng ASC. Nếu client truyền direction là DESC, giá trị DESC được dùng.

~~~graphql
query SortedBooks($sort: BookSortInput) {
    books(sort: $sort) {
        id
        title
    }
}
~~~

Nếu biến sort không có direction:

~~~json
{
    "sort": {}
}
~~~

direction nhận default ASC.

Nếu direction là field nullable và client gửi tường minh null:

~~~json
{
    "sort": {
        "direction": null
    }
}
~~~

giá trị vẫn là null, không tự động đổi thành ASC. Ứng dụng cần quyết định null có nghĩa là không sắp xếp, dùng thứ tự mặc định ở service hay từ chối theo quy tắc nghiệp vụ.

Nếu khai báo `direction: SortDirection! = ASC`, client có thể bỏ qua field vì có default; nhưng gửi null tường minh vẫn không hợp lệ.

Không nên nhầm default value với fallback trong Java. Default ở SDL được áp dụng trong quá trình GraphQL xử lý input; fallback trong service là quy tắc nghiệp vụ riêng và cần được thiết kế nhất quán.

## 8. GraphQL kiểm tra enum input như thế nào?

Enum giúp lỗi dữ liệu đầu vào được phát hiện sớm. Có hai tình huống thường gặp.

**Enum literal không tồn tại trong schema:**

~~~graphql
query {
    booksByGenre(genre: FANTASY) {
        id
    }
}
~~~

Nếu BookGenre không khai báo FANTASY, document không vượt qua bước validation. Resolver không được gọi.

**Variable chứa giá trị enum không hợp lệ:**

Operation khai báo:

~~~graphql
query BooksByGenre($genre: BookGenre!) {
    booksByGenre(genre: $genre) {
        id
    }
}
~~~

Variables:

~~~json
{
    "genre": "FANTASY"
}
~~~

GraphQL không thể coerce giá trị này thành BookGenre vì FANTASY không nằm trong enum. Request bị từ chối trước khi thực thi field.

Có thể phân biệt các lớp kiểm tra:

| Lớp | Ví dụ | Kết quả |
| --- | --- | --- |
| GraphQL schema/validation | Enum literal không có trong schema | Request error, resolver chưa chạy |
| Variable coercion | JSON variable chứa tên enum không hợp lệ | Request error, resolver chưa chạy |
| Binding Java | Kiểu Java hoặc mapping enum không tương thích | Có thể phát sinh lỗi khi bind argument |
| Nghiệp vụ | Enum hợp lệ nhưng không được phép trong trạng thái hiện tại | Resolver/service từ chối thao tác |

Ví dụ enum có giá trị CANCELLED hợp lệ về mặt schema, nhưng người dùng không có quyền hủy đơn hàng hoặc đơn hàng đã hoàn tất. Đây là kiểm tra nghiệp vụ và authorization, không phải validation enum của GraphQL.

## 9. Thiết kế và mở rộng enum an toàn

Enum là một phần của hợp đồng API công khai. Việc thay đổi danh sách giá trị có thể ảnh hưởng cả server và client.

**Chọn giá trị ổn định, có ý nghĩa.** Dùng các tên như PENDING, COMPLETED hoặc CANCELLED thay vì tên gắn với chi tiết triển khai nội bộ. Giá trị enum nên phản ánh khái niệm nghiệp vụ mà client có thể hiểu.

**Dùng quy ước đặt tên nhất quán.** Enum value thường dùng chữ hoa và dấu gạch dưới, ví dụ IN_PROGRESS hoặc OUT_OF_STOCK. GraphQL phân biệt hoa thường, nên cần thống nhất ngay từ đầu.

**Không dùng enum thay cho dữ liệu mở.** Nếu danh sách giá trị thay đổi thường xuyên hoặc do quản trị viên tự định nghĩa, một String hoặc object type phù hợp hơn. Enum thích hợp khi tập lựa chọn được kiểm soát bởi schema và thay đổi theo phiên bản API.

**Thêm enum value cần xem xét client.** Thêm một giá trị thường tương thích với client chỉ gửi các giá trị cũ. Tuy nhiên, client nhận enum ở output có thể dùng switch exhaustive hoặc sinh code từ schema; giá trị mới có thể khiến client cũ không xử lý được. Client nên có nhánh fallback cho enum value chưa biết.

**Không xóa hoặc đổi tên tùy tiện.** Xóa hoặc đổi tên một enum value có thể làm request cũ không hợp lệ và khiến client không hiểu response. Nên đánh dấu deprecated, thông báo lộ trình thay thế và chỉ loại bỏ khi có kế hoạch phiên bản phù hợp.

Có thể đánh dấu một enum value đã lỗi thời bằng directive `@deprecated`:

~~~graphql
enum OrderStatus {
    PENDING
    PROCESSING
    SHIPPED
    DELIVERED
    OLD_COMPLETE @deprecated(reason: "Use DELIVERED instead")
}
~~~

Giá trị deprecated vẫn tồn tại trong schema để tương thích, nhưng công cụ hỗ trợ GraphQL có thể cảnh báo client nên chuyển sang giá trị mới.

## 10. Enum và bảo mật nghiệp vụ

Enum giới hạn tập dữ liệu client có thể gửi, nhưng không thay thế xác thực và phân quyền.

Ví dụ:

~~~graphql
enum UserRole {
    READER
    EDITOR
    ADMIN
}

input ChangeRoleInput {
    userId: ID!
    role: UserRole!
}
~~~

Việc schema cho phép ADMIN không có nghĩa mọi người dùng đều được phép gán role đó. Server phải kiểm tra:

- Người gửi request là ai.
- Người gửi có quyền thay đổi role không.
- Người nhận có thuộc phạm vi quản lý của người gửi không.
- Thay đổi có hợp lệ với chính sách bảo mật hiện hành không.

Không dựa vào enum do client truyền để xác định quyền của chính client. Quyền phải lấy từ security context đáng tin cậy ở server và được kiểm tra trong resolver/service hoặc lớp method security.

## 11. Kiểm thử enum input bằng GraphQlTester

Có thể dùng GraphQlTester để kiểm tra enum được truyền qua variables và bind vào resolver:

~~~java
@Test
void filtersBooksByGenre() {
    graphQlTester.document("""
            query BooksByGenre($genre: BookGenre!) {
                booksByGenre(genre: $genre) {
                    id
                    title
                }
            }
            """)
        .variable("genre", "TECHNOLOGY")
        .execute()
        .path("booksByGenre[0].title")
        .entity(String.class)
        .isEqualTo("Spring in Action");
}
~~~

Với input object:

~~~java
@Test
void filtersBooksWithInputObject() {
    graphQlTester.document("""
            query SearchBooks($filter: BookFilterInput) {
                books(filter: $filter) {
                    id
                    title
                }
            }
            """)
        .variable("filter", Map.of(
            "keyword", "Spring",
            "genre", "TECHNOLOGY"
        ))
        .execute()
        .path("books[0].title")
        .entity(String.class)
        .isEqualTo("Spring in Action");
}
~~~

Nên kiểm thử thêm:

- Truyền từng enum value hợp lệ.
- Truyền enum value không tồn tại.
- Phân biệt enum literal không có dấu nháy với String literal.
- Bỏ qua enum field có default và gửi null tường minh.
- Truyền enum trong list và input object lồng nhau.
- Kiểm tra resolver nhận đúng Java enum constant.
- Kiểm tra enum hợp lệ nhưng bị từ chối bởi quy tắc nghiệp vụ hoặc quyền truy cập.
- Kiểm tra client xử lý được giá trị output mới hoặc deprecated.

Test nên xác nhận cả kết quả GraphQL lẫn hành vi service. Với lỗi validation/coercion, kiểm tra response có errors và xác nhận resolver không được gọi.

## 12. Những điểm cần ghi nhớ

- Enum khai báo tập giá trị hữu hạn bằng từ khóa enum trong SDL.
- Enum literal trong GraphQL document không đặt trong dấu nháy; JSON variables biểu diễn enum bằng chuỗi.
- Enum có thể dùng trong argument, input object field, list và output field.
- GraphQL kiểm tra enum literal và variable trước khi resolver thực thi.
- Java enum có thể nhận giá trị enum khi tên constant tương thích với enum value trong schema.
- Default value được dùng khi field bị bỏ qua; null tường minh vẫn là null nếu field nullable.
- Enum giới hạn lựa chọn nhưng không thay thế validation nghiệp vụ hoặc authorization.
- Thêm, deprecated, đổi tên hay xóa enum value cần xem xét ảnh hưởng đến client.

Enum input giúp API thể hiện rõ các lựa chọn hợp lệ và phát hiện dữ liệu sai kiểu ngay ở ranh giới GraphQL. Khi kết hợp SDL nhất quán, Java enum tương ứng, kiểm tra nghiệp vụ và kiểm thử bằng GraphQlTester, ứng dụng Spring for GraphQL có thể xử lý các trạng thái và lựa chọn đầu vào an toàn, dễ bảo trì.

