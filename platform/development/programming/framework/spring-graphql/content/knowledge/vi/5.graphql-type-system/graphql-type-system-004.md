# Input object type

Trong GraphQL, **input object type** là kiểu dữ liệu dùng để gom nhiều giá trị đầu vào thành một object có cấu trúc. Thay vì khai báo nhiều argument rời rạc trên một field, schema có thể định nghĩa một input type rồi dùng type đó làm argument cho Query hoặc Mutation.

Input object đặc biệt hữu ích với các thao tác tìm kiếm, lọc dữ liệu, tạo mới và cập nhật. Với Spring for GraphQL, object đầu vào này có thể được ánh xạ vào Java class hoặc record thông qua annotation @Argument, giúp controller nhận dữ liệu có cấu trúc và chuyển tiếp đến lớp nghiệp vụ.

## 1. Input object type là gì?

Input object được khai báo bằng từ khóa input trong SDL:

~~~graphql
input BookFilter {
    keyword: String
    genre: String
    authorId: ID
}
~~~

BookFilter là một input object type gồm ba field:

- keyword nhận chuỗi tìm kiếm.
- genre nhận thể loại sách.
- authorId nhận định danh tác giả.

Input object chưa phải là một thao tác có thể gọi trực tiếp. Nó cần được sử dụng ở vị trí đầu vào, thường là argument của một field:

~~~graphql
type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Client truyền object theo cấu trúc đã khai báo:

~~~graphql
query SearchBooks($filter: BookFilter) {
    books(filter: $filter) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY",
        "authorId": "author-7"
    }
}
~~~

GraphQL kiểm tra cấu trúc và kiểu của input theo schema trước khi chuyển dữ liệu đến resolver. Client không thể tự ý thêm field ngoài định nghĩa của BookFilter hoặc truyền một giá trị không tương thích với kiểu đã khai báo.

## 2. Phân biệt input object và output object

GraphQL phân biệt kiểu dùng để nhận dữ liệu từ client và kiểu dùng để trả dữ liệu về client.

| Đặc điểm | Input object | Output object |
| --- | --- | --- |
| Khai báo | input | type |
| Mục đích | Nhận dữ liệu đầu vào | Mô tả dữ liệu trả về |
| Dùng ở đâu | Argument, input field, biến có kiểu input | Field return type và selection set |
| Có field argument | Không | Có thể có |
| Có thể chứa object output | Không | Có thể chứa object, interface hoặc union |

Ví dụ output type:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

Ví dụ input type:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}
~~~

Hai kiểu này không thể thay thế cho nhau. Không thể khai báo argument có kiểu Book nếu Book là output object; cũng không thể dùng CreateBookInput làm kiểu trả về của một field để client chọn các field con.

Cách tách riêng giúp schema thể hiện rõ mục đích dữ liệu. Output type có thể chứa field được tính toán, quan hệ và resolver. Input type chỉ mô tả những giá trị client được phép gửi vào.

## 3. Các kiểu dữ liệu hợp lệ bên trong input object

Field của input object chỉ được sử dụng các kiểu đầu vào hợp lệ:

- Scalar dựng sẵn như Int, Float, String, Boolean, ID.
- Enum.
- Input object khác.
- List của các kiểu đầu vào hợp lệ.
- Các dạng non-null được tạo bằng dấu chấm than.

Ví dụ:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input AuthorFilter {
    authorId: ID
    nameContains: String
}

input BookFilter {
    keyword: String
    genre: BookGenre
    author: AuthorFilter
    years: [Int!]
    includeOutOfPrint: Boolean = false
}
~~~

Trong ví dụ này:

- genre chỉ nhận một trong các giá trị enum đã khai báo.
- author là input object lồng nhau.
- years là list số nguyên, từng phần tử không được null.
- includeOutOfPrint có giá trị mặc định là false.

Không dùng output object, interface hoặc union làm kiểu field của input object. Input object cũng không khai báo resolver field riêng hay argument cho từng field. Nếu cần mô hình hóa một tập lựa chọn đầu vào có cấu trúc, hãy dùng scalar, enum hoặc input object lồng nhau.

### Ví dụ input object lồng nhau

Schema:

~~~graphql
input DateRangeInput {
    from: String
    to: String
}

input BookSearchInput {
    keyword: String
    author: AuthorFilter
    published: DateRangeInput
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Operation:

~~~graphql
query SearchBooks($input: BookSearchInput) {
    searchBooks(input: $input) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "keyword": "GraphQL",
        "author": {
            "nameContains": "Nguyen"
        },
        "published": {
            "from": "2022-01-01",
            "to": "2025-12-31"
        }
    }
}
~~~

Cấu trúc lồng nhau cho phép nhóm các điều kiện theo ý nghĩa nghiệp vụ. Nếu bộ lọc ngày giờ được sử dụng trong ứng dụng thực tế, nên định nghĩa custom scalar phù hợp với định dạng ngày giờ và quy tắc múi giờ thay vì dùng chuỗi không có quy ước.

## 4. Required field, optional field và dấu chấm than

Trong input object, một field có thể bắt buộc hoặc tùy chọn.

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    subtitle: String
}
~~~

- title và authorId là required input fields vì có kiểu non-null và không có default value.
- subtitle là optional input field vì kiểu của nó cho phép null.

Client phải cung cấp hai field bắt buộc:

~~~json
{
    "title": "Spring for GraphQL",
    "authorId": "author-7"
}
~~~

Nếu bỏ title hoặc gửi title: null, request không hợp lệ ở bước input coercion. Resolver không nhận được input hợp lệ để thực thi.

Một field non-null có default value không bắt buộc client phải truyền, vì GraphQL có thể dùng giá trị mặc định khi field bị bỏ qua:

~~~graphql
input BookPageInput {
    page: Int! = 1
    size: Int! = 20
}
~~~

Trong trường hợp này, client có thể bỏ qua page hoặc size; GraphQL sử dụng default tương ứng. Nếu client truyền tường minh null cho một field non-null, request vẫn không hợp lệ.

## 5. Phân biệt field bị bỏ qua và field có giá trị null

Một điểm quan trọng khi thiết kế input là **không gửi field** và **gửi field với giá trị null** là hai trạng thái khác nhau.

Xét input type:

~~~graphql
input UpdateBookInput {
    title: String
    subtitle: String
}
~~~

Client có thể gửi:

~~~json
{
    "title": "New title"
}
~~~

Ở đây subtitle bị bỏ qua. Hoặc gửi:

~~~json
{
    "title": "New title",
    "subtitle": null
}
~~~

Ở đây subtitle được gửi tường minh với giá trị null.

GraphQL giữ được sự khác biệt này trong quá trình coercion input object: field bị bỏ qua có thể không xuất hiện trong map giá trị đã coercion, còn field được gửi với null có giá trị null. Khác biệt này rất quan trọng với thao tác cập nhật:

- Bỏ qua subtitle có thể mang nghĩa giữ nguyên subtitle hiện tại.
- Gửi subtitle: null có thể mang nghĩa xóa subtitle.

Nếu ánh xạ thẳng vào Java DTO mà cả hai trường hợp đều trở thành Java null, ứng dụng có thể mất thông tin về việc client có gửi field hay không. Với API cập nhật cần phân biệt hai trạng thái, hãy dùng kiểu dữ liệu hoặc cơ chế binding có khả năng lưu trạng thái hiện diện của field, hoặc thiết kế input rõ ràng với cờ thao tác như clearSubtitle. Cần kiểm thử cả trường hợp bỏ qua và gửi null.

### Default value và null

Default value được dùng khi field không được cung cấp. Nó không có nghĩa là mọi giá trị null đều tự động được thay bằng default.

~~~graphql
input SearchInput {
    keyword: String = "GraphQL"
}
~~~

- Input {} sử dụng giá trị mặc định GraphQL.
- Input {"keyword": "Spring"} sử dụng giá trị Spring.
- Input {"keyword": null} giữ giá trị null vì field cho phép null.

Hiểu đúng ba trạng thái này giúp tránh ghi đè dữ liệu hoặc áp dụng bộ lọc ngoài ý muốn.

## 6. Dùng input object cho Query và Mutation

Input object có thể được dùng làm argument của Query để mô tả điều kiện tìm kiếm:

~~~graphql
input BookFilterInput {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Với thao tác ghi, input object thường gom các thuộc tính mà client gửi để tạo hoặc cập nhật dữ liệu:

~~~graphql
input CreateBookInput {
    title: String!
    description: String
    authorId: ID!
    genre: BookGenre!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Operation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        genre
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "title": "Learning Spring GraphQL",
        "description": "A practical introduction",
        "authorId": "author-7",
        "genre": "TECHNOLOGY"
    }
}
~~~

Input object tạo ra một hợp đồng đầu vào có tên và có thể tái sử dụng. Khi nhiều mutation có cùng cấu trúc dữ liệu, có thể dùng chung input type nếu ngữ nghĩa và quy tắc validation thực sự giống nhau. Nếu hai thao tác có yêu cầu nghiệp vụ khác nhau, nên tạo input type riêng để tránh một thay đổi làm ảnh hưởng ngoài dự kiến đến API khác.

## 7. Ánh xạ input object vào Java với Spring for GraphQL

Spring for GraphQL có thể chuyển input object thành Java class hoặc record. Ví dụ SDL:

~~~graphql
input CreateBookInput {
    title: String!
    description: String
    authorId: ID!
    genre: BookGenre!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Khai báo enum Java tương ứng:

~~~java
public enum BookGenre {
    TECHNOLOGY,
    SCIENCE,
    HISTORY,
    FICTION
}
~~~

Khai báo Java record:

~~~java
public record CreateBookInput(
        String title,
        String description,
        String authorId,
        BookGenre genre
) {
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
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
    public Book createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Spring for GraphQL thực hiện các bước chính:

1. Đọc argument input từ operation.
2. GraphQL kiểm tra object theo CreateBookInput trong schema.
3. Spring chuyển giá trị đã coercion sang kiểu Java đích.
4. Method được ánh xạ bằng @MutationMapping nhận object và gọi service.
5. Kết quả trả về được GraphQL engine hoàn thành theo selection set của client.

Tên thuộc tính Java cần tương thích với tên field trong input object. Nếu cần ánh xạ phức tạp, có thể dùng class với constructor hoặc cơ chế chuyển đổi phù hợp thay vì buộc mọi input phải là record.

### Input object lồng nhau trong Java

Với SDL:

~~~graphql
input DateRangeInput {
    from: String
    to: String
}

input BookSearchInput {
    keyword: String
    published: DateRangeInput
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Java record tương ứng:

~~~java
public record DateRangeInput(String from, String to) {
}

public record BookSearchInput(
        String keyword,
        DateRangeInput published
) {
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument("input") BookSearchInput input) {
    return bookService.search(input);
}
~~~

Kiểu Java cần phản ánh cấu trúc lồng nhau của SDL. Nếu schema thay đổi tên field hoặc kiểu dữ liệu, cần cập nhật DTO tương ứng và kiểm thử binding.

## 8. Validation cho input object

GraphQL thực hiện kiểm tra ở cấp schema trước khi gọi resolver:

- Field có tồn tại trong input type không.
- Giá trị có tương thích với scalar hoặc enum không.
- Input object lồng nhau có đúng cấu trúc không.
- Field non-null có bị thiếu hoặc nhận null không.
- List có chứa phần tử đúng kiểu không.

Những kiểm tra này chưa thay thế validation nghiệp vụ. Ví dụ, limit: Int! vẫn có thể nhận số âm; GraphQL chỉ xác nhận đó là số nguyên khác null. Quy tắc như giới hạn trang tối đa, độ dài tiêu đề, quyền sở hữu author hoặc trạng thái cho phép cập nhật phải được kiểm tra trong ứng dụng.

Ví dụ kiểm tra trong service:

~~~java
@Service
public class BookService {

    public Book create(CreateBookInput input) {
        if (input.title() == null || input.title().isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }

        if (input.title().length() > 200) {
            throw new IllegalArgumentException("Title is too long");
        }

        if (!authorExists(input.authorId())) {
            throw new IllegalArgumentException("Author does not exist");
        }

        return saveBook(input);
    }
}
~~~

Trong dự án thực tế, có thể sử dụng Jakarta Bean Validation với constraint như @NotBlank, @Size, @Min và @Max, kết hợp cấu hình validation phù hợp cho Spring GraphQL. Dù dùng cách nào, lỗi validation cần được chuyển thành GraphQL error có thông điệp và mã lỗi phù hợp; tránh trả thông tin nội bộ hoặc dữ liệu nhạy cảm trong thông báo.

Ví dụ input type có giới hạn ở cấp SDL:

~~~graphql
input BookPageInput {
    page: Int! = 1
    size: Int! = 20
}
~~~

Resolver hoặc service vẫn phải bảo đảm page lớn hơn hoặc bằng 1 và size không vượt giới hạn hệ thống. Schema khai báo kiểu và tính bắt buộc; service thực thi quy tắc miền nghiệp vụ.

## 9. Thiết kế input object dễ mở rộng

Một input object tốt nên phản ánh một nhóm dữ liệu có ý nghĩa nghiệp vụ.

**Đặt tên theo mục đích.** Các tên như CreateBookInput, UpdateBookInput, BookFilterInput nói rõ dữ liệu được dùng để làm gì. Tránh tên chung chung như InputData hoặc CommonInput.

**Không gom mọi thứ vào một input type khổng lồ.** Nếu create, update và search có yêu cầu khác nhau, tách type giúp kiểm soát field bắt buộc, default và quyền thay đổi.

**Dùng input object lồng nhau khi có nhóm dữ liệu độc lập.** Ví dụ DateRangeInput hoặc AuthorFilterInput có thể được tái sử dụng nếu cùng ngữ nghĩa.

**Giới hạn kích thước và độ sâu.** Input list lớn hoặc object lồng sâu có thể làm tăng chi phí parse, validate và xử lý. Cần đặt giới hạn phù hợp ở schema, transport hoặc lớp nghiệp vụ.

**Không dùng input thay cho authorization.** Việc client gửi authorId hoặc ownerId không có nghĩa họ được phép thao tác trên tài nguyên đó. Server phải kiểm tra danh tính và quyền trên từng tài nguyên.

**Cẩn trọng với update semantics.** Xác định rõ field bị bỏ qua, field null và field có giá trị mới mang ý nghĩa gì. Nếu API cần xóa một giá trị, quy ước rõ ràng trong input và kiểm thử.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Schema báo input field dùng sai kiểu | Dùng output object, interface hoặc union trong input definition. | Chuyển sang scalar, enum hoặc input object phù hợp. |
| Thiếu field bắt buộc | Input field non-null không có default bị bỏ qua. | Cung cấp field và giá trị khác null. |
| Enum không hợp lệ | Client gửi giá trị không nằm trong enum. | Đối chiếu tên enum value trong SDL. |
| Input object lồng nhau không bind được | Cấu trúc JSON hoặc kiểu Java không tương thích với SDL. | Kiểm tra tên field, nested DTO và kiểu dữ liệu. |
| Resolver nhận giá trị null | Field tùy chọn bị bỏ qua hoặc được gửi tường minh null. | Kiểm tra operation variables và quy tắc default. |
| Không phân biệt bỏ qua và null khi update | DTO đơn giản có thể biểu diễn cả hai trạng thái bằng cùng Java null. | Dùng binding giữ trạng thái hiện diện hoặc thiết kế input có chỉ thị rõ ràng. |
| Giá trị hợp lệ theo schema nhưng sai nghiệp vụ | Schema chỉ kiểm tra kiểu, không kiểm tra mọi quy tắc miền. | Validate trong service và trả lỗi GraphQL phù hợp. |
| Client gửi object có field lạ | JSON không khớp input type đã khai báo. | Sửa tên field hoặc cập nhật schema có kiểm soát. |

Khi debug, kiểm tra lần lượt SDL, request variables, kiểu Java nhận argument và validation trong service. Nếu lỗi xảy ra trước khi resolver chạy, thường cần xem lại input coercion hoặc schema. Nếu resolver đã chạy nhưng nghiệp vụ từ chối dữ liệu, kiểm tra validation và xử lý exception của ứng dụng.

## 11. Kiểm thử input object với GraphQlTester

Có thể dùng GraphQlTester để kiểm tra mutation nhận input object và trả dữ liệu mong đợi:

~~~java
@Test
void createsBookFromInput() {
    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("input", Map.of(
            "title", "Learning Spring GraphQL",
            "authorId", "author-7",
            "genre", "TECHNOLOGY"
        ))
        .execute()
        .path("createBook.title")
        .entity(String.class)
        .isEqualTo("Learning Spring GraphQL");
}
~~~

Ngoài trường hợp hợp lệ, nên kiểm thử:

- Thiếu field bắt buộc.
- Gửi null cho field non-null.
- Gửi enum value không tồn tại.
- Gửi nested input object sai cấu trúc.
- Bỏ qua field có default và gửi null tường minh.
- Gửi input hợp lệ về kiểu nhưng vi phạm quy tắc nghiệp vụ.
- Cập nhật với field bị bỏ qua so với field được gửi null.

Kiểm thử ở cấp GraphQL xác nhận schema và binding. Kiểm thử service xác nhận quy tắc nghiệp vụ. Kiểm thử tích hợp xác nhận lỗi được chuyển thành response GraphQL đúng cách.

## 12. Những điểm cần ghi nhớ

- Input object type được khai báo bằng từ khóa input và chỉ dùng ở vị trí đầu vào.
- Field của input object chỉ chứa scalar, enum, input object khác, list và các dạng non-null tương ứng.
- Output object khai báo bằng type không thể dùng làm input type.
- Field non-null không có default là bắt buộc; default được dùng khi field bị bỏ qua.
- Bỏ qua field và gửi field với null là hai trạng thái khác nhau, đặc biệt quan trọng với thao tác cập nhật.
- Spring for GraphQL có thể bind input object vào Java class hoặc record qua @Argument.
- GraphQL kiểm tra cấu trúc và kiểu; service vẫn phải kiểm tra quy tắc nghiệp vụ, authorization và giới hạn tài nguyên.

Input object giúp GraphQL API nhận dữ liệu có cấu trúc, dễ mở rộng và rõ ràng về hợp đồng. Khi kết hợp schema chặt chẽ, Java DTO phù hợp và validation ở lớp nghiệp vụ, ứng dụng Spring for GraphQL có thể xử lý an toàn các bộ lọc phức tạp cũng như thao tác tạo và cập nhật dữ liệu.

