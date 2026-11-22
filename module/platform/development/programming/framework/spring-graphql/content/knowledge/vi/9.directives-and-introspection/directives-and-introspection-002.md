# Built-in @skip

Trong GraphQL, directive là chỉ thị gắn vào operation hoặc schema element để thay đổi cách GraphQL xử lý một phần của request. Một directive dựng sẵn thường dùng ở phía client là **@skip**. Directive này cho phép client yêu cầu GraphQL bỏ qua một field hoặc một nhánh selection khi điều kiện Boolean có giá trị true.

Với Spring for GraphQL, @skip được xử lý bởi GraphQL engine trong quá trình thực thi operation. Ứng dụng không cần viết controller method riêng để triển khai directive này. Tuy nhiên, hiểu chính xác điều kiện, vị trí áp dụng và ảnh hưởng đến resolver giúp xây dựng request linh hoạt, kiểm thử đúng và tránh nhầm directive điều khiển response với cơ chế bảo mật.

## 1. @skip là gì?

`@skip` là directive dựng sẵn của GraphQL, dùng để loại một selection khỏi kết quả thực thi khi điều kiện của nó là `true`.

Cú pháp:

~~~graphql
fieldName @skip(if: Boolean!)
~~~

Argument `if` có kiểu `Boolean!`, nghĩa là phải nhận giá trị Boolean khác null. Khi `if` là `true`, selection được đánh dấu skip. Khi `if` là `false`, selection được thực thi bình thường.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
    author: Author
}
~~~

Client có thể yêu cầu bỏ qua field description:

~~~graphql
query BookDetail($skipDescription: Boolean!) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $skipDescription)
    }
}
~~~

Nếu variables là:

~~~json
{
    "skipDescription": true
}
~~~

GraphQL không thực thi selection `description` và field này không xuất hiện trong response:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action"
        }
    }
}
~~~

Nếu `skipDescription` là `false`, GraphQL thực thi field và response có thêm description nếu resolver trả về dữ liệu.

## 2. Vì sao cần @skip?

Một màn hình có thể hiển thị dữ liệu khác nhau tùy tab, trạng thái hoặc lựa chọn của người dùng. Nếu client luôn gửi tất cả field, server có thể phải thực hiện những resolver không cần thiết cho giao diện hiện tại.

Ví dụ màn hình chi tiết sách có chế độ xem tóm tắt và chế độ xem đầy đủ. Cả hai cần cùng thông tin cơ bản, nhưng chỉ chế độ đầy đủ cần description:

~~~graphql
query BookScreen($fullView: Boolean!) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $fullView == false)
    }
}
~~~

Biểu thức so sánh trực tiếp trong argument GraphQL như trên không hợp lệ. GraphQL không hỗ trợ biểu thức Boolean tùy ý trong argument. Hãy tính điều kiện ở client và truyền bằng variable:

~~~graphql
query BookScreen($skipDescription: Boolean!) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $skipDescription)
    }
}
~~~

Ở phía client:

- Chế độ xem đầy đủ: truyền `skipDescription = false`.
- Chế độ tóm tắt: truyền `skipDescription = true`.

`@skip` giữ operation document ổn định, còn variables quyết định field nào được đưa vào kết quả ở từng lần gọi.

## 3. Điều kiện if và variables

Argument `if` bắt buộc có kiểu Boolean khác null. Cách phổ biến là khai báo operation variable với kiểu `Boolean!`:

~~~graphql
query ProductDetail($hideStock: Boolean!) {
    product(id: "product-10") {
        id
        name
        stockQuantity @skip(if: $hideStock)
    }
}
~~~

Khi truyền:

~~~json
{
    "hideStock": true
}
~~~

field stockQuantity bị bỏ qua.

Khi truyền:

~~~json
{
    "hideStock": false
}
~~~

field stockQuantity được thực thi.

Nếu variable bị thiếu hoặc có giá trị null, request không thỏa kiểu non-null và bị từ chối trong quá trình xử lý variables. Có thể khai báo default cho variable để tránh phải truyền trong mọi trường hợp:

~~~graphql
query ProductDetail($hideStock: Boolean! = false) {
    product(id: "product-10") {
        id
        name
        stockQuantity @skip(if: $hideStock)
    }
}
~~~

Nếu client không cung cấp `hideStock`, GraphQL sử dụng default false và field stockQuantity được chọn.

Không dùng chuỗi `"true"` hoặc số `1` thay cho Boolean. Giá trị phải là JSON Boolean:

~~~json
{
    "hideStock": true
}
~~~

## 4. @skip áp dụng ở những vị trí nào?

Theo GraphQL specification, `@skip` có thể được đặt tại ba vị trí trong executable document:

| Vị trí | Ý nghĩa |
| --- | --- |
| `FIELD` | Bỏ qua một field cụ thể. |
| `FRAGMENT_SPREAD` | Bỏ qua một lần sử dụng fragment. |
| `INLINE_FRAGMENT` | Bỏ qua một inline fragment. |

### Bỏ qua một field

~~~graphql
query BookDetail($skipAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author @skip(if: $skipAuthor) {
            id
            name
        }
    }
}
~~~

Khi `skipAuthor` là true, cả field author cùng selection set con của nó bị bỏ qua.

### Bỏ qua một fragment spread

~~~graphql
fragment AuthorDetails on Author {
    id
    name
    biography
}

query BookDetail($skipAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author {
            ...AuthorDetails @skip(if: $skipAuthor)
        }
    }
}
~~~

Khi điều kiện true, lần sử dụng fragment AuthorDetails bị bỏ qua. Các field khác trong selection set của author vẫn có thể được thực thi nếu được chọn riêng.

### Bỏ qua một inline fragment

~~~graphql
query Search($skipBookDetails: Boolean!) {
    search(keyword: "Spring") {
        __typename
        ... on Book @skip(if: $skipBookDetails) {
            title
            isbn
        }
        ... on Author {
            name
        }
    }
}
~~~

Khi `skipBookDetails` là true, nhánh inline fragment trên Book bị bỏ qua. Nhánh Author không bị ảnh hưởng bởi directive đó.

`@skip` không được đặt tùy ý ở mọi vị trí. Ví dụ, directive này không có location cho operation definition, variable definition hay fragment definition. Nếu muốn điều kiện hóa một nhóm field, hãy đặt directive tại fragment spread hoặc inline fragment phù hợp.

## 5. Kết hợp @skip với nested field

Directive có thể đặt trên field ở bất kỳ cấp nào trong selection set, miễn là location hợp lệ.

~~~graphql
query BookDetails(
    $skipDescription: Boolean!
    $skipAuthor: Boolean!
    $skipReviews: Boolean!
) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $skipDescription)
        author @skip(if: $skipAuthor) {
            id
            name
        }
        reviews @skip(if: $skipReviews) {
            id
            rating
            comment
        }
    }
}
~~~

Client có thể điều khiển riêng từng nhánh:

~~~json
{
    "skipDescription": false,
    "skipAuthor": true,
    "skipReviews": true
}
~~~

Response có description, nhưng không có author và reviews:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action",
            "description": "A practical guide"
        }
    }
}
~~~

Mỗi directive được đánh giá theo giá trị variable của request hiện tại. Điều kiện ở một field không tự động ảnh hưởng đến field ngang cấp hoặc field khác trong operation.

## 6. Phân biệt @skip và @include

GraphQL cung cấp hai directive điều kiện có ý nghĩa bổ sung cho nhau:

- `@skip(if: true)` bỏ qua selection.
- `@include(if: true)` đưa selection vào thực thi.

Ví dụ dùng `@include`:

~~~graphql
query BookDetail($showAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author @include(if: $showAuthor) {
            id
            name
        }
    }
}
~~~

Nếu `showAuthor` là true, author được thực thi. Nếu false, author bị loại khỏi kết quả.

Có thể diễn đạt cùng một logic bằng `@skip`:

~~~graphql
query BookDetail($hideAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author @skip(if: $hideAuthor) {
            id
            name
        }
    }
}
~~~

Khi dùng cả hai directive trên cùng một selection:

~~~graphql
query BookDetail(
    $skipAuthor: Boolean!
    $includeAuthor: Boolean!
) {
    book(id: "book-42") {
        id
        title
        author
            @skip(if: $skipAuthor)
            @include(if: $includeAuthor) {
                id
                name
            }
    }
}
~~~

Selection chỉ được thực thi khi điều kiện skip là false và điều kiện include là true.

| `skip(if)` | `include(if)` | Kết quả |
| --- | --- | --- |
| false | true | Thực thi selection |
| true | true | Bỏ qua selection |
| false | false | Bỏ qua selection |
| true | false | Bỏ qua selection |

Trong thực tế, thường chỉ cần một directive để diễn đạt rõ ý định. Dùng đồng thời chỉ khi có lý do và bảo đảm các điều kiện không gây khó hiểu cho người đọc operation.

## 7. GraphQL xử lý @skip như thế nào?

`@skip` là executable directive. GraphQL engine kiểm tra document, xác định điều kiện và loại selection khỏi tập field cần thực thi khi điều kiện là true.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Client gửi operation và variables"] --> B["Parse và validate document"]
    B --> C["Coerce variables"]
    C --> D["Đánh giá @skip(if)"]
    D --> E{"if = true?"}
    E -->|Có| F["Bỏ qua selection"]
    E -->|Không| G["Thực thi field resolver"]
    F --> H["Tạo response từ các field còn lại"]
    G --> H
~~~

Một số điểm cần hiểu:

- Schema vẫn phải có field được chọn. `@skip` không làm cho field không tồn tại trở nên hợp lệ.
- Document vẫn phải hợp lệ về cú pháp, tên field, argument, kiểu và selection set.
- Variables vẫn được kiểm tra và coercion theo khai báo, kể cả khi một field có thể bị skip.
- Khi selection bị skip, data fetcher/resolver của field đó không được gọi.
- Field bị skip không được trả về như một key có giá trị null; key đó bị loại khỏi object kết quả.
- Các field khác không bị skip vẫn được thực thi bình thường.

Nếu tất cả field con trong một object selection bị skip, object kết quả có thể không chứa những key đó. Client cần xử lý sự vắng mặt của key theo điều kiện request đã gửi, không tự hiểu nó là giá trị null của field.

## 8. @skip trong Spring for GraphQL

Spring for GraphQL sử dụng GraphQL Java để thực thi operation. Các directive dựng sẵn như `@skip` được engine hỗ trợ sẵn, do đó không cần tạo annotation Java, `@SchemaMapping` hoặc `RuntimeWiringConfigurer` chỉ để bật chức năng này.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
}
~~~

Controller có resolver cho reviews:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Operation:

~~~graphql
query BookDetail($skipReviews: Boolean!) {
    book(id: "book-42") {
        id
        title
        reviews @skip(if: $skipReviews) {
            id
            rating
        }
    }
}
~~~

Khi `skipReviews` là true, GraphQL engine bỏ qua field reviews và method `reviews` không được gọi. Khi `skipReviews` là false, field được thực thi và Spring gọi method mapping để lấy danh sách Review.

Điều này có thể tránh các truy vấn dữ liệu không cần thiết trong request cụ thể. Tuy nhiên, nếu root resolver đã tải reviews trước và gắn sẵn vào object Book, directive không thể hoàn tác công việc đã diễn ra ở root resolver. Hãy đặt việc tải dữ liệu tại resolver phù hợp hoặc dùng chiến lược truy vấn có cân nhắc selection set.

## 9. Kiểm thử @skip bằng GraphQlTester

Nên kiểm thử cả hai nhánh điều kiện: skip và execute.

Ví dụ khi skip field reviews:

~~~java
@Test
void skipsReviewsWhenVariableIsTrue() {
    graphQlTester.document("""
            query BookDetail($skipReviews: Boolean!) {
                book(id: "book-42") {
                    id
                    title
                    reviews @skip(if: $skipReviews) {
                        id
                        rating
                    }
                }
            }
            """)
        .variable("skipReviews", true)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");
}
~~~

Có thể xác nhận field reviews không xuất hiện trong response bằng cách kiểm tra response JSON hoặc sử dụng API kiểm tra path phù hợp với phiên bản GraphQlTester của dự án.

Kiểm thử khi không skip:

~~~java
@Test
void executesReviewsWhenVariableIsFalse() {
    graphQlTester.document("""
            query BookDetail($skipReviews: Boolean!) {
                book(id: "book-42") {
                    reviews @skip(if: $skipReviews) {
                        id
                        rating
                    }
                }
            }
            """)
        .variable("skipReviews", false)
        .execute()
        .path("book.reviews[0].rating")
        .entity(Integer.class)
        .isEqualTo(5);
}
~~~

Ngoài response, có thể dùng mock hoặc spy để xác nhận resolver reviews không được gọi khi field bị skip và được gọi khi điều kiện false. Nên bổ sung test cho các trường hợp:

- Variable skip bị thiếu hoặc nhận null khi khai báo non-null.
- Field object bị skip cùng toàn bộ selection set con.
- Fragment spread và inline fragment có directive.
- Kết hợp @skip với @include.
- Field lồng nhau có argument và resolver tốn kém.
- Field non-null bị skip: key không xuất hiện và không phát sinh null propagation chỉ vì field đó bị bỏ qua.

## 10. Kiểm tra directive qua introspection

GraphQL hỗ trợ introspection để client hoặc công cụ khám phá schema. Có thể truy vấn danh sách directive, vị trí áp dụng và argument mà schema công bố:

~~~graphql
query DirectiveDefinitions {
    __schema {
        directives {
            name
            locations
            args {
                name
                type {
                    kind
                    name
                    ofType {
                        kind
                        name
                    }
                }
            }
        }
    }
}
~~~

Trong kết quả, tìm directive có tên `skip` để xem argument `if` và kiểu Boolean non-null cùng các locations được hỗ trợ. Công cụ và phiên bản server có thể quyết định cách hiển thị các directive dựng sẵn trong danh sách introspection; nếu không thấy, cần đối chiếu GraphQL specification và khả năng introspection của endpoint.

Introspection giúp khám phá hợp đồng schema, nhưng không thay thế việc kiểm tra operation cụ thể. Với lỗi `@skip`, cần kiểm tra document, variable type, giá trị variables và field location.

## 11. @skip không phải cơ chế bảo mật

`@skip` điều khiển việc field có được đưa vào response của một operation hay không. Nó không cấp hoặc thu hồi quyền truy cập dữ liệu.

Client có thể gửi một request khác mà không gắn `@skip` vào field. Vì vậy, không được dựa vào việc giao diện ẩn field hoặc client truyền skip=true để bảo vệ dữ liệu nhạy cảm.

Ví dụ, nếu field salary chỉ dành cho quản lý:

~~~graphql
type Employee {
    id: ID!
    name: String!
    salary: Float
}
~~~

Directive:

~~~graphql
query EmployeeDetail($skipSalary: Boolean!) {
    employee(id: "employee-7") {
        id
        name
        salary @skip(if: $skipSalary)
    }
}
~~~

Nếu client truyền false, field salary sẽ được yêu cầu. Server vẫn phải kiểm tra người dùng có quyền xem salary hay không bằng Spring Security, method security, resolver authorization hoặc chính sách phù hợp khác.

Dùng `@skip` để giảm field không cần thiết trong response; dùng authorization phía server để bảo vệ dữ liệu. Hai mục tiêu này độc lập với nhau.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Argument if bị từ chối | Truyền String, số hoặc null thay vì Boolean khác null. | Khai báo variable Boolean! và truyền JSON Boolean. |
| Field vẫn xuất hiện | Điều kiện skip đang là false. | Kiểm tra giá trị variable và default. |
| Field không xuất hiện dù mong muốn | Variable skip là true hoặc include directive đang false. | Kiểm tra cả @skip và @include trên selection. |
| Resolver không chạy | Field bị skip hoặc không nằm trong selection set thực tế. | Kiểm tra directive và operation được gửi. |
| Field không hợp lệ dù có @skip | Field không tồn tại, sai kiểu hoặc selection set sai. | Sửa document theo schema; directive không bỏ qua validation. |
| Dữ liệu nhạy cảm vẫn có thể truy cập | Dùng @skip như một cơ chế ẩn field. | Bổ sung authorization phía server. |
| Query vẫn tốn thời gian | Root resolver tải dữ liệu trước khi nested field bị skip. | Chuyển việc tải dữ liệu vào field resolver hoặc tối ưu chiến lược truy vấn. |

## 13. Những điểm cần ghi nhớ

- `@skip(if: Boolean!)` bỏ qua một selection khi điều kiện là true.
- Directive có thể áp dụng lên field, fragment spread và inline fragment.
- Dùng Boolean variables để điều khiển field theo từng request; không viết biểu thức tùy ý trong argument.
- Field bị skip không xuất hiện trong response và resolver của field đó không được gọi.
- Document và variables vẫn phải hợp lệ; `@skip` không bỏ qua bước validation hoặc coercion.
- `@include` có logic bổ sung; khi dùng cả hai, selection chỉ chạy nếu không bị skip và được include.
- Spring for GraphQL xử lý directive dựng sẵn qua GraphQL engine, không cần resolver tùy chỉnh.
- `@skip` không thay thế authorization và không phải cơ chế bảo vệ dữ liệu.

`@skip` là cách đơn giản để điều khiển selection set theo nhu cầu của client. Khi dùng đúng với variables, hiểu rõ tác động đến resolver và kết hợp kiểm thử, ứng dụng Spring for GraphQL có thể tránh thực thi những field không cần thiết mà vẫn giữ schema và logic bảo mật rõ ràng.

