# Argument nullable

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ý nghĩa của argument nullable trong GraphQL schema.
- Phân biệt argument bị bỏ qua với argument được truyền giá trị null.
- Hiểu cách default value tương tác với argument và variables.
- Thiết kế query filter và mutation cập nhật từng phần với input nullable.
- Bind argument trong Spring for GraphQL và dùng ArgumentValue<T> khi cần nhận biết trạng thái omitted.

## Argument nullable là gì?

Trong GraphQL SDL, một argument không có dấu ! là nullable. Client có thể truyền một giá trị hợp lệ hoặc null, và cũng có thể bỏ qua argument nếu schema không yêu cầu nó.

Ví dụ:

~~~graphql
type Query {
  books(authorId: ID, keyword: String, first: Int): [Book!]!
}
~~~

Ba argument authorId, keyword và first đều nullable. Client có thể gọi field mà không truyền argument nào:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Hoặc chỉ truyền một vài argument:

~~~graphql
query {
  books(authorId: "author-12") {
    id
    title
  }
}
~~~

Hoặc truyền rõ null:

~~~graphql
query {
  books(authorId: null, keyword: "Spring") {
    id
    title
  }
}
~~~

Việc một argument nullable có thể nhận null không có nghĩa ứng dụng bắt buộc phải xử lý null theo một cách cố định. Schema xác định dữ liệu nào hợp lệ về mặt GraphQL; ý nghĩa nghiệp vụ của giá trị bị bỏ qua hoặc null do resolver và service quyết định.

## Phân biệt nullable và non-null

GraphQL dùng dấu ! để khai báo một giá trị non-null:

~~~graphql
type Query {
  bookById(id: ID!): Book
  books(authorId: ID): [Book!]!
}
~~~

id: ID! là argument bắt buộc: client phải cung cấp giá trị và giá trị đó không được null. authorId: ID là argument tùy chọn: client có thể bỏ qua hoặc truyền null.

| Khai báo | Có thể bỏ qua? | Có thể truyền null? |
| --- | --- | --- |
| ID! không có default | Không | Không |
| ID | Có | Có |
| Int = 20 | Có, GraphQL dùng default | Có; null tường minh không kích hoạt default |
| Int! = 20 | Có, GraphQL dùng default | Không |

Một argument non-null có default vẫn có thể bị bỏ qua vì GraphQL có giá trị thay thế. Argument non-null không có default mới là required argument theo nghĩa client phải cung cấp.

Nếu client truyền null cho argument non-null, GraphQL từ chối request trong giai đoạn kiểm tra/coercion đầu vào. Resolver không được gọi với giá trị null đó.

## Phân biệt omitted và explicit null

Đây là khác biệt quan trọng khi thiết kế API. Với argument nullable không có default, hai request sau đều hợp lệ:

~~~graphql
query {
  books {
    id
  }
}
~~~

~~~graphql
query {
  books(authorId: null) {
    id
  }
}
~~~

Request thứ nhất không gửi argument authorId. Request thứ hai gửi argument và giá trị của nó là null. GraphQL giữ được khác biệt này trong quá trình xử lý input. Tuy nhiên, nếu resolver chỉ nhận một biến Java nullable như String authorId, cả hai trường hợp thường đều được bind thành null; method không thể suy ra client đã bỏ qua argument hay chủ động gửi null.

Sự khác biệt này thường quan trọng với:

- Bộ lọc tìm kiếm: bỏ qua filter có thể nghĩa là không lọc; gửi null có thể nghĩa là tìm các bản ghi chưa có giá trị.
- Mutation cập nhật: bỏ qua field có thể nghĩa là giữ nguyên dữ liệu; gửi null có thể nghĩa là xóa giá trị hiện tại.
- Cấu hình tùy chọn: bỏ qua có thể dùng cấu hình mặc định; null có thể biểu thị yêu cầu tắt hoặc xóa cấu hình.

Hãy xác định semantics này trong contract API. Không nên để client phải đoán ý nghĩa của null.

## Default value được áp dụng khi nào?

GraphQL cho phép khai báo default cho argument:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

Nếu client bỏ qua first, GraphQL sử dụng giá trị 20. Nếu client truyền first: 5, resolver nhận 5. Nếu client truyền rõ first: null, giá trị là null vì argument có kiểu nullable; default không thay thế một giá trị null được gửi tường minh.

Quy tắc tương tự áp dụng cho field trong input object:

~~~graphql
input BookSearchInput {
  keyword: String
  first: Int = 20
}

type Query {
  searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Nếu object input được truyền nhưng thiếu field first, GraphQL áp dụng default 20. Nếu field có mặt với giá trị null, giá trị vẫn là null vì first nullable.

Default value trong schema là một phần contract chung của API. Nó hữu ích khi mọi client đều nên nhận cùng một giá trị mặc định. Nếu default phụ thuộc vào người dùng, tenant, quyền hoặc ngữ cảnh request, hãy tính ở tầng service thay vì hard-code trong SDL.

## Nullable variables và argument

Variables cũng có nullability riêng. Ví dụ:

~~~graphql
query SearchBooks($authorId: ID, $first: Int) {
  books(authorId: $authorId, first: $first) {
    id
    title
  }
}
~~~

Client truyền variables bằng JSON:

~~~json
{
  "authorId": "author-12",
  "first": 10
}
~~~

Nếu không có key authorId trong object variables, biến không được cung cấp. Nếu có key "authorId": null, biến được cung cấp với giá trị null. Với biến nullable và argument nullable, cả hai trường hợp đều hợp lệ; sự khác biệt có thể ảnh hưởng đến việc argument có hiện diện trong dữ liệu thực thi hay không.

Variable default được khai báo ngay trong operation:

~~~graphql
query SearchBooks($first: Int = 10) {
  books(first: $first) {
    id
  }
}
~~~

Nếu client không cung cấp variable first, GraphQL dùng default 10. Nếu client truyền "first": null, giá trị variable là null, không dùng default 10.

Variable nullable không thể tùy ý truyền vào vị trí non-null. Ví dụ, $id: ID không thể dùng cho argument id: ID! nếu không có điều kiện default phù hợp. Cách đơn giản và rõ ràng nhất cho argument bắt buộc là khai báo variable non-null:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}
~~~

GraphQL kiểm tra tính tương thích giữa kiểu variable và vị trí sử dụng trước khi thực thi resolver.

## Bind nullable argument trong Spring for GraphQL

Với annotated controller, @Argument liên kết argument trong schema với tham số method Java:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @Argument("authorId") String authorId,
            @Argument("keyword") String keyword,
            @Argument("first") Integer first) {

        int pageSize = first != null ? first : 20;
        return bookService.search(authorId, keyword, pageSize);
    }
}
~~~

Với kiểu Java tham chiếu như String hoặc Integer, giá trị có thể là null. Không dùng kiểu nguyên thủy int cho argument nullable nếu method cần biểu diễn trạng thái thiếu giá trị, vì kiểu nguyên thủy không chứa được null.

Trong ví dụ trên, first có thể được default ở service. Nếu schema đã khai báo first: Int = 20, GraphQL sẽ áp dụng default trước khi resolver nhận argument. Hãy chọn một nơi chịu trách nhiệm đặt default để tránh lặp logic và tạo ra hai giá trị mặc định khác nhau.

### Dùng ArgumentValue<T> để nhận biết omitted

Nếu cần phân biệt argument bị bỏ qua với argument được truyền null, Spring for GraphQL cung cấp ArgumentValue<T>. Wrapper này cho biết argument có bị omitted hay không và cho phép đọc giá trị bên trong:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @Argument("authorId") ArgumentValue<String> authorId) {

        if (authorId.isOmitted()) {
            return bookService.findAll();
        }
        if (authorId.value() == null) {
            return bookService.findWithoutAuthor();
        }
        return bookService.findByAuthorId(authorId.value());
    }
}
~~~

Trong ví dụ, client bỏ qua authorId thì lấy tất cả sách; truyền null thì tìm sách chưa có tác giả; truyền một ID thì lọc theo tác giả. Đây là semantics do ứng dụng lựa chọn. Nếu nghiệp vụ không cần phân biệt, dùng tham số nullable thông thường sẽ đơn giản hơn.

Khi cần nhận biết omission, hãy cân nhắc default value trong SDL. Default được áp dụng trong quá trình GraphQL xử lý input; nếu muốn resolver tự quyết định giữa omitted và null, không nên che mất trạng thái đó bằng một default không cần thiết.

## Nullable field trong input object và mutation cập nhật từng phần

Argument nullable đặc biệt hữu ích với mutation dạng patch. Ví dụ, người dùng có thể cập nhật tiêu đề hoặc xóa phụ đề của một cuốn sách:

~~~graphql
input UpdateBookInput {
  title: String
  subtitle: String
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Hai field trong UpdateBookInput đều nullable. Client có thể chỉ gửi field cần cập nhật:

~~~graphql
mutation UpdateTitle($id: ID!, $input: UpdateBookInput!) {
  updateBook(id: $id, input: $input) {
    id
    title
    subtitle
  }
}
~~~

Variables:

~~~json
{
  "id": "book-101",
  "input": {
    "title": "Spring GraphQL Guide"
  }
}
~~~

Trong request này, title có mặt, còn subtitle bị bỏ qua. Nếu gửi "subtitle": null, client đã chỉ định rõ giá trị null. Một API patch có thể quy ước bỏ qua là giữ nguyên, còn null là xóa nội dung.

### Binding input object bằng ArgumentValue

Nếu bind input object vào DTO chỉ có các thuộc tính nullable thông thường, giá trị bị bỏ qua và giá trị null tường minh có thể cùng trở thành null. Có thể dùng ArgumentValue<T> ở từng field để giữ lại trạng thái omitted:

~~~java
public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> subtitle) {
}
~~~

Controller có thể chuyển DTO thành lệnh cập nhật:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {

    if (!input.title().isOmitted() && input.title().value() == null) {
        throw new IllegalArgumentException("title must not be null");
    }

    return bookService.update(
            id,
            input.title(),
            input.subtitle());
}
~~~

Service nhận từng ArgumentValue và chỉ thay đổi field không bị omitted. Với subtitle, giá trị null có thể được hiểu là xóa phụ đề. Với title, ví dụ trên từ chối null theo quy tắc nghiệp vụ dù SDL cho phép nullable. Điều đó cho thấy schema nullability và validation nghiệp vụ có vai trò khác nhau.

Khi dùng ArgumentValue trong input DTO, cần kiểm tra binding bằng test trên phiên bản Spring for GraphQL của dự án. Không nên thay mọi field nullable thành wrapper nếu use case không cần phân biệt omission với explicit null.

## Thiết kế semantics cho filter và patch

Trước khi khai báo nullable, hãy trả lời hai câu hỏi: client có thể bỏ qua field không, và nếu gửi null thì hệ thống phải làm gì?

| Use case | Omitted | Explicit null |
| --- | --- | --- |
| Filter theo tác giả | Không áp dụng filter | Chỉ lấy sách chưa có tác giả |
| Filter theo từ khóa | Không giới hạn theo từ khóa | Có thể từ chối hoặc coi như không có từ khóa |
| Patch phụ đề | Giữ phụ đề hiện tại | Xóa phụ đề |
| Thay đổi email liên hệ | Giữ email hiện tại | Xóa email nếu nghiệp vụ cho phép |
| Giới hạn kết quả có default | Dùng default của schema | Không có giới hạn nếu service cho phép, hoặc từ chối |

Đây là các ví dụ về semantics có thể chọn, không phải quy tắc bắt buộc của GraphQL. Hãy ghi rõ trong tài liệu API và giữ hành vi nhất quán giữa các mutation/query.

## Kiểm thử omitted, null và default

Kiểm thử cần bao phủ ít nhất ba trạng thái:

1. Không gửi argument hoặc không có key variable.
2. Gửi argument/variable với giá trị null.
3. Gửi một giá trị cụ thể.

Với query:

~~~graphql
query SearchBooks($authorId: ID) {
  books(authorId: $authorId) {
    id
  }
}
~~~

Hãy chạy test với variables không có key authorId, variables có "authorId": null và variables có "authorId": "author-12". Nếu resolver dùng ArgumentValue, xác minh cả isOmitted() và value() cho từng trường hợp.

Với default value:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

Kiểm thử khi bỏ qua first để xác minh giá trị hiệu lực là 20, khi truyền first: 5 để xác minh giá trị là 5, và khi truyền first: null để xác minh default không được áp dụng cho explicit null.

Với mutation patch, kiểm tra rằng field omitted giữ nguyên dữ liệu, field có giá trị được cập nhật và field được truyền null được xử lý theo semantics đã công bố. Ngoài kết quả trả về, nên kiểm tra trạng thái dữ liệu sau mutation để tránh test chỉ xác nhận response mà bỏ sót side effect.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Argument nullable nhận null ngoài dự kiến | Client bỏ qua argument hoặc truyền null | Kiểm tra variables và semantics của API; dùng ArgumentValue nếu cần phân biệt |
| Argument non-null bị từ chối | Client thiếu giá trị hoặc gửi null | Sửa schema/operation hoặc gửi giá trị hợp lệ |
| Default không được áp dụng | Client truyền explicit null | Phân biệt omitted với null; chỉ bỏ qua argument nếu muốn dùng default |
| Java báo lỗi khi nhận null | Dùng kiểu nguyên thủy như int cho argument nullable | Dùng kiểu tham chiếu như Integer |
| Mutation vô tình xóa dữ liệu | Resolver coi omitted và null là cùng một trạng thái | Dùng ArgumentValue và định nghĩa rõ patch semantics |
| DTO input không phân biệt omitted | Thuộc tính DTO chỉ dùng kiểu nullable thông thường | Dùng ArgumentValue<T> cho field cần phân biệt và kiểm thử binding |

## Thực hành tổng hợp

Xây dựng API tìm kiếm và cập nhật sách với các yêu cầu:

1. Query books(authorId: ID, keyword: String, first: Int = 20) cho phép client chọn bộ lọc.
2. Nếu authorId bị bỏ qua, không lọc theo tác giả; nếu explicit null, chỉ lấy sách chưa có tác giả.
3. Nếu first bị bỏ qua, dùng giá trị mặc định 20; nếu explicit null, trả lỗi validation theo chính sách API.
4. Mutation updateBook(id: ID!, input: UpdateBookInput!) hỗ trợ cập nhật một phần.
5. Field subtitle bị bỏ qua thì giữ nguyên; explicit null thì xóa phụ đề.

Dùng ArgumentValue<T> ở các vị trí cần phân biệt trạng thái. Viết test cho omitted, explicit null, giá trị cụ thể và default. Sau đó mô tả semantics của từng argument để client có thể sử dụng API mà không phải suy đoán.

## Ghi nhớ

Argument nullable không có dấu !, vì vậy client có thể bỏ qua hoặc truyền null. Hai trạng thái đó có ý nghĩa khác nhau trong nhiều use case, đặc biệt là filter và mutation cập nhật từng phần. GraphQL áp dụng default khi giá trị bị bỏ qua, còn explicit null vẫn là null nếu kiểu cho phép. Trong Spring for GraphQL, tham số @Argument nullable thông thường có thể không phân biệt được omitted với null; ArgumentValue<T> giúp giữ lại khác biệt này. Hãy xác định semantics trong schema, xử lý ở service và kiểm thử đủ các trạng thái đầu vào.
