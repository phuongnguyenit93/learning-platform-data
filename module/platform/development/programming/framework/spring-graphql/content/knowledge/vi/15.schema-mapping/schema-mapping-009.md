# Mapping field có argument

Trong GraphQL, argument có thể được khai báo trên bất kỳ field nào, không chỉ các field gốc của Query hoặc Mutation. Điều này cho phép client truyền điều kiện lọc, phân trang, sắp xếp hoặc tùy chọn hiển thị ngay tại field lồng nhau mà họ muốn lấy dữ liệu.

Trong Spring for GraphQL, một field lồng nhau có argument thường được xử lý bằng **@SchemaMapping**. Method resolver nhận object nguồn từ field cha và các giá trị argument thông qua **@Argument**. Hiểu rõ hai loại dữ liệu này giúp triển khai resolver đúng, tránh nhầm argument của field cha với field con, đồng thời kiểm soát hiệu năng khi một field được gọi cho nhiều object.

## 1. Argument có thể nằm trên field lồng nhau

Xét schema của một hệ thống quản lý sách:

~~~graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10, minRating: Int): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Field books thuộc root type Query và không nhận argument. Field reviews thuộc type Book, nhận hai argument:

- `first` giới hạn số review cần lấy, mặc định là 10.
- `minRating` lọc review theo mức đánh giá tối thiểu.

Client có thể chọn field lồng nhau và truyền argument trực tiếp tại đó:

~~~graphql
query BookReviews {
    books {
        id
        title
        reviews(first: 3, minRating: 4) {
            id
            rating
            comment
        }
    }
}
~~~

Trong operation này, first và minRating thuộc field Book.reviews. Chúng không phải argument của Query.books.

Đây là đặc điểm quan trọng của GraphQL: mỗi field có thể khai báo bộ argument riêng. Client chỉ truyền tham số cho field mà họ muốn điều khiển, kể cả khi field nằm sâu trong selection set.

## 2. Phân biệt argument của field cha và field con

Một operation có thể có argument ở nhiều cấp:

~~~graphql
type Query {
    books(authorId: ID!): [Book!]!
}

type Book {
    reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Client:

~~~graphql
query AuthorBooks($authorId: ID!, $first: Int!, $minRating: Int) {
    books(authorId: $authorId) {
        id
        title
        reviews(first: $first, minRating: $minRating) {
            id
            rating
        }
    }
}
~~~

Có hai nhóm argument độc lập:

| Field | Argument | Mục đích |
| --- | --- | --- |
| Query.books | authorId | Chọn danh sách sách của một tác giả. |
| Book.reviews | first | Giới hạn số review của từng sách. |
| Book.reviews | minRating | Lọc review của từng sách theo rating. |

Khi Spring gọi resolver cho Book.reviews, method nhận argument first và minRating của field này. Argument authorId đã được dùng ở resolver Query.books; nó không tự động xuất hiện trong resolver Book.reviews.

Nếu resolver field con cần thông tin từ object cha, hãy đọc từ source object. Nếu cần một tham số khác do client truyền trực tiếp vào field con, khai báo argument đó trong SDL và nhận bằng @Argument.

## 3. Source object trong @SchemaMapping

Với field lồng nhau, Spring for GraphQL cung cấp object cha làm source object cho resolver.

Ví dụ Java record:

~~~java
public record Book(
        String id,
        String title,
        String authorId
) {
}

public record Review(
        String id,
        int rating,
        String comment
) {
}
~~~

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Resolver:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Argument("first") Integer first,
            @Argument("minRating") Integer minRating) {

        return reviewService.findByBook(
                book.id(),
                first,
                minRating
        );
    }
}
~~~

Trong method trên:

- Book book là source object, tức object cha mà GraphQL đang phân giải.
- @Argument("first") nhận argument first của field reviews.
- @Argument("minRating") nhận argument minRating của field reviews.
- ReviewService thực hiện truy vấn dữ liệu theo ID của Book và các điều kiện lọc.

Source object không phải dữ liệu client gửi dưới dạng argument. Nó là kết quả đã được resolver ở cấp cha trả về. Còn các tham số có @Argument được bind từ operation hiện tại.

### Spring xác định field được ánh xạ như thế nào?

Với khai báo:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book, @Argument("first") Integer first) {
    return reviewService.findByBook(book.id(), first);
}
~~~

Spring ánh xạ method vào field Book.reviews.

Có thể lược bỏ một số thuộc tính nếu Spring suy ra được từ tên method và kiểu source parameter:

~~~java
@SchemaMapping
public List<Review> reviews(Book book, @Argument("first") Integer first) {
    return reviewService.findByBook(book.id(), first);
}
~~~

Trong trường hợp này, tên source type được suy ra từ Book và tên field từ method reviews. Khi schema lớn hoặc method có tên khác field, ghi rõ typeName và field giúp mapping dễ đọc, tránh nhầm lẫn.

## 4. Nhận scalar, enum và nhiều argument

Argument của field có thể là scalar, enum hoặc các kiểu đầu vào hợp lệ khác.

Ví dụ schema:

~~~graphql
enum ReviewSort {
    NEWEST
    OLDEST
    HIGHEST_RATING
}

type Book {
    id: ID!
    reviews(
        first: Int = 10
        minRating: Int
        sort: ReviewSort = NEWEST
    ): [Review!]!
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("minRating") Integer minRating,
        @Argument("sort") ReviewSort sort) {

    return reviewService.findReviews(
            book.id(),
            first,
            minRating,
            sort
    );
}
~~~

Java enum:

~~~java
public enum ReviewSort {
    NEWEST,
    OLDEST,
    HIGHEST_RATING
}
~~~

Client operation:

~~~graphql
query {
    books {
        id
        reviews(
            first: 5
            minRating: 4
            sort: HIGHEST_RATING
        ) {
            id
            rating
        }
    }
}
~~~

Tên enum literal trong GraphQL document không đặt trong dấu nháy. Khi truyền qua JSON variables, giá trị enum được biểu diễn bằng chuỗi:

~~~json
{
    "sort": "HIGHEST_RATING"
}
~~~

Trong operation thực tế, variable phải được khai báo với kiểu enum tương ứng. GraphQL kiểm tra giá trị enum trước khi gọi resolver. Nếu client gửi giá trị không tồn tại trong schema, request bị từ chối.

## 5. Dùng input object làm argument của nested field

Khi field có nhiều điều kiện lọc, có thể gom chúng vào input object.

SDL:

~~~graphql
enum ReviewSort {
    NEWEST
    OLDEST
    HIGHEST_RATING
}

input ReviewFilterInput {
    minRating: Int
    verifiedOnly: Boolean
    sort: ReviewSort
}

type Book {
    id: ID!
    reviews(first: Int = 10, filter: ReviewFilterInput): [Review!]!
}
~~~

Java record:

~~~java
public record ReviewFilterInput(
        Integer minRating,
        Boolean verifiedOnly,
        ReviewSort sort
) {
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("filter") ReviewFilterInput filter) {

    return reviewService.findReviews(book.id(), first, filter);
}
~~~

Client:

~~~graphql
query BookReviews($filter: ReviewFilterInput) {
    books {
        id
        reviews(first: 5, filter: $filter) {
            id
            rating
            comment
        }
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "minRating": 4,
        "verifiedOnly": true,
        "sort": "HIGHEST_RATING"
    }
}
~~~

Input object giúp nhóm các điều kiện liên quan, làm chữ ký method gọn hơn và dễ mở rộng. Các field trong input object phải tuân thủ quy tắc GraphQL input type: dùng scalar, enum, list hoặc input object khác; không dùng output object.

## 6. Default value, nullable và giá trị null

Argument có thể khai báo default value trong SDL:

~~~graphql
type Book {
    reviews(first: Int = 10): [Review!]!
}
~~~

Nếu client không truyền first, GraphQL sử dụng giá trị mặc định 10 trước khi gọi resolver. Vì vậy, tham số Java Integer first thường nhận 10 khi argument bị bỏ qua.

Nếu client truyền first: 3, resolver nhận 3. Nếu argument nullable và client truyền tường minh null, resolver nhận null; default value không thay thế explicit null.

| Cách client truyền | Giá trị resolver nhận |
| --- | --- |
| Bỏ qua first, SDL có default 10 | 10 |
| Truyền first: 3 | 3 |
| Truyền first: null cho argument nullable | null |
| Bỏ qua argument non-null không có default | Request không hợp lệ |
| Truyền null cho argument non-null | Request không hợp lệ |

Nếu khai báo:

~~~graphql
reviews(first: Int! = 10): [Review!]!
~~~

client có thể bỏ qua argument vì có default, nhưng không được truyền null. Default và non-null là hai quy tắc bổ sung cho nhau.

Không nên mặc định rằng tham số Java luôn khác null chỉ vì field có default ở một nơi khác. Hãy kiểm tra chính xác argument definition của field trong SDL và trường hợp client gửi explicit null.

## 7. Phân biệt omitted và explicit null bằng ArgumentValue

Với argument nullable, đôi khi ứng dụng cần phân biệt client không truyền argument với client truyền argument có giá trị null.

Spring for GraphQL cung cấp ArgumentValue<T> để giữ thông tin này.

Ví dụ SDL:

~~~graphql
type Book {
    reviews(minRating: Int): [Review!]!
}
~~~

Resolver:

~~~java
import org.springframework.graphql.data.ArgumentValue;

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("minRating") ArgumentValue<Integer> minRating) {

    if (minRating.isOmitted()) {
        return reviewService.findAllByBook(book.id());
    }

    if (minRating.value() == null) {
        return reviewService.findWithoutRatingFilter(book.id());
    }

    return reviewService.findWithMinimumRating(
            book.id(),
            minRating.value()
    );
}
~~~

Ba trạng thái có thể được xử lý riêng:

- Omitted: client không gửi minRating, server dùng hành vi mặc định của nghiệp vụ.
- Explicit null: client gửi minRating là null, server có thể hiểu là không áp dụng bộ lọc.
- Có giá trị: server áp dụng điều kiện lọc theo rating.

Không phải API nào cũng cần phân biệt hai trạng thái đầu. Nếu omitted và null có cùng ý nghĩa, tham số Java nullable thông thường sẽ đơn giản hơn. Chỉ dùng ArgumentValue khi khác biệt này có ý nghĩa nghiệp vụ.

Với input object lồng nhau, cũng có thể dùng ArgumentValue cho field cần phân biệt omitted và null:

~~~java
public record ReviewFilterInput(
        ArgumentValue<Integer> minRating,
        ArgumentValue<Boolean> verifiedOnly
) {
}
~~~

Cần kiểm thử binding của các trường hợp omitted, null và có giá trị với phiên bản Spring for GraphQL mà dự án sử dụng.

## 8. Dùng argument cho phân trang và lọc

Nested field thường trả về danh sách có thể lớn. Argument là nơi thích hợp để giới hạn số phần tử hoặc chọn trang.

Ví dụ phân trang offset:

~~~graphql
type Book {
    id: ID!
    reviews(first: Int = 20, offset: Int = 0): [Review!]!
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("offset") Integer offset) {

    int safeFirst = first == null ? 20 : Math.min(Math.max(first, 1), 100);
    int safeOffset = offset == null ? 0 : Math.max(offset, 0);

    return reviewService.findPage(
            book.id(),
            safeFirst,
            safeOffset
    );
}
~~~

Việc giới hạn first ở server ngăn client yêu cầu một lượng dữ liệu quá lớn. Không nên chỉ dựa vào giá trị default trong SDL, vì client vẫn có thể truyền số rất lớn hoặc số âm.

Với dữ liệu thay đổi thường xuyên hoặc danh sách lớn, cursor pagination thường ổn định hơn offset pagination. Ví dụ:

~~~graphql
type Book {
    id: ID!
    reviews(first: Int = 20, after: String): ReviewConnection!
}

type ReviewConnection {
    edges: [ReviewEdge!]!
    pageInfo: PageInfo!
}

type ReviewEdge {
    cursor: String!
    node: Review!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}
~~~

Argument after cho biết vị trí tiếp tục từ cursor trước đó. Server cần xác thực cursor và áp dụng thứ tự sắp xếp ổn định để tránh lặp hoặc bỏ sót phần tử khi dữ liệu thay đổi.

Argument cũng có thể điều khiển lọc theo trạng thái, thời gian, ngôn ngữ hoặc thứ tự. Mỗi tham số cần có ý nghĩa rõ ràng và được kiểm tra ở server.

## 9. Cùng một nested field được gọi cho nhiều parent object

Khi client truy vấn danh sách sách và chọn reviews, GraphQL sẽ phân giải field reviews cho từng Book trong danh sách:

~~~graphql
query {
    books {
        id
        reviews(first: 3, minRating: 4) {
            id
            rating
        }
    }
}
~~~

Nếu books trả về 50 object, resolver Book.reviews có thể được gọi 50 lần. Mỗi lần nhận một source Book khác nhau nhưng cùng argument first = 3 và minRating = 4.

Điều này làm rõ vai trò của source object và argument:

- Source object thay đổi theo từng Book.
- Argument đến từ cùng vị trí field trong operation nên có cùng giá trị cho mỗi Book trong lần thực thi này.
- Kết quả cần được tải riêng theo Book ID và các điều kiện argument.

Nếu resolver gọi repository một lần cho từng Book, request có thể gặp vấn đề N+1.

## 10. Tránh N+1 khi nested field có argument

Ví dụ resolver đơn giản:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("minRating") Integer minRating) {

    return reviewRepository.findByBookIdAndRating(
            book.id(),
            minRating,
            PageRequest.of(0, first)
    );
}
~~~

Nếu có 50 Book, cách triển khai này có thể phát sinh 50 truy vấn review. Có thể dùng DataLoader hoặc batching để tải dữ liệu theo nhóm.

Khi kết quả phụ thuộc vào argument, khóa tải dữ liệu cần biểu diễn đủ các yếu tố ảnh hưởng đến kết quả. Ví dụ một key có thể gồm:

~~~java
public record ReviewBatchKey(
        String bookId,
        Integer first,
        Integer minRating
) {
}
~~~

Nếu chỉ dùng bookId làm key trong khi kết quả còn phụ thuộc first hoặc minRating, cache có thể trả nhầm kết quả cho hai lần gọi có điều kiện khác nhau.

Một chiến lược batch có thể:

1. Thu thập các key gồm bookId và điều kiện lọc.
2. Nhóm các key theo bộ điều kiện tương thích.
3. Truy vấn dữ liệu theo lô.
4. Phân phối kết quả về đúng key.
5. Giữ thứ tự và giới hạn số phần tử theo từng key.

DataLoader thường có phạm vi theo request để tránh dùng chung dữ liệu cache giữa các request khác nhau. Không nên dùng một cache toàn cục cho kết quả phụ thuộc người dùng hoặc quyền truy cập.

@BatchMapping là một cách thuận tiện để gom việc phân giải field cho nhiều source object. Khi field có argument, cần bảo đảm chiến lược batch vẫn áp dụng đúng argument và không trộn kết quả của những điều kiện khác nhau. Với logic lọc/phân trang phức tạp, có thể cần DataLoader với key tổng hợp hoặc một truy vấn repository thiết kế riêng.

## 11. Kiểm tra và bảo mật argument

Mọi argument đều do client cung cấp và phải được xem là dữ liệu không đáng tin cậy.

Ví dụ first là Int nhưng GraphQL không tự giới hạn nó trong khoảng 1 đến 100. Resolver hoặc service phải kiểm tra:

- Giới hạn tối đa của page size.
- Offset không âm.
- Giá trị enum nằm trong tập schema đã công bố.
- Khoảng thời gian bắt đầu không lớn hơn thời gian kết thúc.
- Bộ lọc không làm lộ dữ liệu ngoài phạm vi người dùng được phép xem.

Không sử dụng tenantId, ownerId hoặc user ID do client gửi làm căn cứ duy nhất để quyết định quyền truy cập. Server cần lấy danh tính từ security context và kiểm tra quyền trên từng resource.

Nếu nested field trả về thông tin nhạy cảm, quyền đọc phải được kiểm tra tại resolver hoặc service tương ứng. Việc client không chọn field đó trong selection set không phải là biện pháp bảo mật.

## 12. Kiểm thử mapping field có argument bằng GraphQlTester

Có thể dùng GraphQlTester để kiểm tra operation truyền argument vào nested field:

~~~java
@Test
void filtersReviewsByArguments() {
    graphQlTester.document("""
            query BookReviews($first: Int!, $minRating: Int) {
                books {
                    reviews(first: $first, minRating: $minRating) {
                        id
                        rating
                    }
                }
            }
            """)
        .variable("first", 3)
        .variable("minRating", 4)
        .execute()
        .path("books[0].reviews[0].rating")
        .entity(Integer.class)
        .isEqualTo(5);
}
~~~

Đây là ví dụ minh họa; test cần có schema và dữ liệu phù hợp, đồng thời cấu hình service/repository hoặc mock theo test context của dự án.

Nên kiểm thử các tình huống:

- Argument được truyền trực tiếp bằng literal.
- Argument được truyền qua variables.
- Argument bị bỏ qua và SDL có default.
- Argument nullable được truyền explicit null.
- Argument non-null bị thiếu hoặc nhận null.
- Input object có field bị bỏ qua và field null.
- first bằng 0, số âm hoặc vượt giới hạn.
- Bộ lọc trả danh sách rỗng.
- Source Book khác nhau nhận kết quả review đúng.
- DataLoader hoặc batch resolver không trộn kết quả giữa các bộ argument.

Có thể dùng mock hoặc spy để xác nhận service nhận đúng Book ID và argument. Với kiểm thử hiệu năng, đo số lần gọi repository khi truy vấn nhiều Book để phát hiện N+1.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| @Argument nhận null | Tên argument trong annotation không khớp SDL hoặc client không gửi giá trị. | Đối chiếu tên argument, operation và variables. |
| Lấy nhầm argument của field cha | Nhầm phạm vi argument giữa các cấp selection set. | Đọc argument trên đúng field mà resolver đang ánh xạ. |
| Source object bị null hoặc sai kiểu | Mapping không khớp type cha hoặc method source parameter không đúng. | Kiểm tra typeName, field và kiểu source. |
| Default không được áp dụng | Argument có thể được gửi explicit null hoặc SDL không khai báo default ở đúng field. | Kiểm tra schema và payload thực tế. |
| Không phân biệt omitted và null | Dùng Java nullable type thông thường trong khi nghiệp vụ cần biết field có được gửi hay không. | Dùng ArgumentValue<T>. |
| Field trả quá nhiều dữ liệu | Không giới hạn page size hoặc argument không được validate. | Đặt giới hạn ở server và dùng pagination. |
| Nested resolver chạy nhiều truy vấn | Mỗi source object kích hoạt một lần truy vấn riêng. | Dùng DataLoader hoặc batching phù hợp. |
| DataLoader trả nhầm kết quả | Cache key không bao gồm các argument ảnh hưởng kết quả. | Dùng composite key và phạm vi cache phù hợp. |
| Người dùng xem được dữ liệu ngoài quyền | Chỉ kiểm tra argument mà không kiểm tra authorization trên resource. | Kiểm tra quyền ở server dựa trên security context. |

Khi debug, kiểm tra SDL trước để xác định field và argument, sau đó xem operation client gửi. Tiếp theo xác nhận source object, tên @Argument, giá trị sau default/coercion và lời gọi service. Nếu kết quả đúng nhưng chậm khi có nhiều parent object, kiểm tra số lần truy vấn và batching.

## 14. Quy trình triển khai field có argument

Khi thêm argument cho một nested field, có thể làm theo trình tự:

1. Xác định field thuộc type cha nào và dữ liệu nào cần điều khiển.
2. Khai báo argument trong SDL với kiểu, nullability và default phù hợp.
3. Chọn scalar, enum hoặc input object theo độ phức tạp của tham số.
4. Viết @SchemaMapping cho đúng type và field.
5. Nhận source object ở tham số resolver và argument bằng @Argument.
6. Dùng ArgumentValue<T> nếu cần phân biệt omitted với explicit null.
7. Validate giới hạn, filter và quyền truy cập trong server.
8. Thiết kế pagination nếu field trả về danh sách.
9. Kiểm tra N+1 và chọn DataLoader hoặc batching khi cần.
10. Viết GraphQlTester cho các trường hợp argument hợp lệ, null, omitted và biên.
11. Đo số lần gọi repository với nhiều parent object.

## 15. Những điểm cần ghi nhớ

- Argument có thể được khai báo trên field lồng nhau, không chỉ root Query hoặc Mutation.
- Argument thuộc về field nơi nó được khai báo; argument của field cha không tự động chuyển xuống field con.
- @SchemaMapping ánh xạ nested field; source object thường là tham số đầu tiên của method.
- @Argument bind argument của field hiện tại vào tham số Java.
- Argument có thể là scalar, enum, list hoặc input object.
- Default được dùng khi argument bị bỏ qua; explicit null vẫn là null nếu argument nullable.
- ArgumentValue<T> giữ được khác biệt giữa omitted và explicit null.
- Dùng argument cho filtering, sorting và pagination, đồng thời luôn giới hạn giá trị ở server.
- Nested resolver có thể gây N+1; DataLoader và batching cần tính cả argument trong khóa tải nếu kết quả phụ thuộc vào chúng.
- Argument không thay thế authorization; server phải kiểm tra quyền trên resource.

Mapping field có argument giúp GraphQL client điều khiển dữ liệu ở đúng cấp field, đặc biệt với các quan hệ lồng nhau có lọc và phân trang. Khi kết hợp source object, @SchemaMapping, @Argument, validation và batching phù hợp, ứng dụng Spring for GraphQL có thể cung cấp API linh hoạt mà vẫn giữ hiệu năng và tính an toàn.

