# Pagination contract

Pagination contract định nghĩa cách client chia một collection thành nhiều phần và tiếp tục đọc phần kế tiếp. Trong GraphQL, pagination không được quy định sẵn bởi schema language; ứng dụng phải công bố arguments, response shape, thứ tự dữ liệu, giới hạn kích thước và semantics của metadata.

Một contract tốt giúp client biết cách đi tiếp hoặc quay lại, không phải tự đoán từ số lượng phần tử. Nó cũng giúp server thay đổi database và query strategy mà không làm client phụ thuộc vào offset, SQL hoặc cấu trúc repository.

Với Spring for GraphQL, contract được khai báo bằng SDL; resolver bind arguments bằng `@Argument` và chuyển chúng sang application service. Service thực thi pagination theo contract rồi trả connection/page DTO. Không nên trả thẳng `Page<T>` của Spring Data như một phần của public API vì đó là abstraction persistence có thể thay đổi theo framework và không diễn đạt đầy đủ semantics GraphQL.

## 1. Pagination giải quyết vấn đề gì?

Một query trả toàn bộ collection có thể tăng chi phí theo số lượng dữ liệu:

~~~graphql
query {
    products {
        id
        name
    }
}
~~~

Khi catalog có vài chục nghìn sản phẩm, response lớn làm tăng thời gian query, bộ nhớ, network transfer và chi phí render phía client. Pagination giới hạn số item trả về trong một lần request.

Pagination contract cần trả lời:

- Client yêu cầu bao nhiêu item?
- Client bắt đầu từ vị trí nào?
- Thứ tự item được xác định ra sao?
- Filter và sort có được giữ nguyên giữa các trang không?
- Client nhận biết còn trang tiếp theo hay không bằng cách nào?
- Có cung cấp tổng số item không, và con số đó có chính xác không?
- Server xử lý thế nào khi input không hợp lệ hoặc dữ liệu thay đổi?

Nếu những quy tắc này không được định nghĩa, hai client có thể hiểu cùng một response theo hai cách khác nhau.

## 2. Chọn kiểu pagination phù hợp

Hai contract phổ biến là offset/page pagination và cursor/connection pagination.

| Tiêu chí | Offset/page | Cursor/connection |
| --- | --- | --- |
| Input | page, size hoặc offset, limit | first, after hoặc last, before |
| Response | content và page metadata | edges, cursors và PageInfo |
| Nhảy đến trang bất kỳ | Dễ, nếu biết page number | Không phải mục tiêu chính |
| Trang sâu | Có thể chậm do database phải bỏ qua nhiều row | Thường ổn định hơn khi có keyset index |
| Dữ liệu thay đổi giữa các request | Insert/delete phía trước offset có thể làm lặp hoặc bỏ sót item | Ít bị dịch chuyển bởi insert/delete trước cursor |
| Tổng số trang | Dễ tính nếu có count | Thường không cần count |
| Contract phía client | Đơn giản cho bảng dữ liệu | Phù hợp infinite scroll và forward/backward traversal |

Không có một kiểu pagination tốt nhất cho mọi collection. Offset phù hợp với bảng quản trị nhỏ, dữ liệu ít thay đổi và nhu cầu nhảy đến trang cụ thể. Cursor phù hợp với collection lớn, feed, lịch sử giao dịch hoặc infinite scrolling.

Không nên công bố cả page/size và first/after trên cùng một field chỉ để hỗ trợ mọi kiểu client. Hai kiểu có semantics khác nhau; nếu thật sự cần cả hai, đặt tên field rõ ràng và mô tả lý do tồn tại của từng contract.

## 3. Contract offset/page pagination

Offset pagination thường dùng page và size. Cần quy định page bắt đầu từ 0 hay 1. Spring Data PageRequest dùng page index bắt đầu từ 0; nếu public API dùng page bắt đầu từ 1 thì resolver phải chuyển đổi rõ ràng.

Ví dụ contract:

~~~graphql
type Query {
    productsPage(page: Int = 0, size: Int = 20): ProductPage!
}

type ProductPage {
    items: [Product!]!
    pageInfo: OffsetPageInfo!
}

type Product {
    id: ID!
    name: String!
}

type OffsetPageInfo {
    page: Int!
    size: Int!
    hasNextPage: Boolean!
    totalElements: Int
    totalPages: Int
}
~~~

Semantics cần được công bố:

- page là zero-based hoặc one-based.
- size là số item tối đa server trả về.
- pageInfo.page phản ánh page đã được áp dụng sau validation.
- pageInfo.size là page size thực tế.
- hasNextPage cho biết còn dữ liệu sau trang hiện tại.
- totalElements/totalPages có thể null nếu server không tính count.

Nếu totalElements có thể vượt giới hạn signed 32-bit của GraphQL Int, không dùng Int một cách âm thầm. Có thể định nghĩa custom scalar Long/BigInt với coercing rõ ràng hoặc không công bố count chính xác.

Một số API dùng offset và limit thay vì page và size. Nếu chọn kiểu này, định nghĩa offset là số item bỏ qua, limit là số item tối đa và giới hạn offset tối đa để tránh request quá sâu.

## 4. Contract cursor/connection pagination

Cursor pagination thường dùng Relay Connection pattern. Một connection chứa edges và PageInfo; mỗi edge chứa node và cursor.

~~~graphql
scalar DateTime

type Query {
    products(
        first: Int = 20
        after: String
        filter: ProductFilter
        sort: ProductSort = CREATED_AT_DESC
    ): ProductConnection!
}

type Product {
    id: ID!
    name: String!
    createdAt: DateTime!
    availability: ProductAvailability!
}

type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
    totalCount: Int
}

type ProductEdge {
    cursor: String!
    node: Product!
}

type PageInfo {
    hasNextPage: Boolean!
    hasPreviousPage: Boolean!
    startCursor: String
    endCursor: String
}

input ProductFilter {
    keyword: String
    categoryId: ID
    availability: ProductAvailability
}

enum ProductSort {
    CREATED_AT_DESC
    CREATED_AT_ASC
    NAME_ASC
}

enum ProductAvailability {
    IN_STOCK
    OUT_OF_STOCK
    PREORDER
}
~~~

Trong contract này, client gửi first để yêu cầu số edge tối đa và after để tiếp tục sau cursor nhận được từ trang trước. sort là enum để server chỉ cho phép các thứ tự đã hỗ trợ. Filter mô tả tập dữ liệu mà client muốn duyệt.

Các field Connection/Edge/PageInfo là contract public. Client không cần biết server dùng SQL keyset predicate, Spring Data scrolling hay một search engine để lấy trang.

## 5. Chọn Relay Connection hay response đơn giản

Relay Connection là convention phổ biến, đặc biệt khi client dùng Relay hoặc cần cursor ở từng edge. Tuy nhiên, không phải API nào cũng bắt buộc dùng đầy đủ Relay shape.

Một response đơn giản có thể là:

~~~graphql
type ProductSlice {
    items: [Product!]!
    nextCursor: String
    hasNext: Boolean!
}
~~~

Shape đơn giản dễ dùng cho API chỉ hỗ trợ forward pagination. Đổi lại, nó không có cursor cho từng edge, không biểu diễn backward pagination theo convention và khó tái sử dụng component pagination chung.

Hãy chọn một shape phù hợp với client ecosystem và giữ nhất quán giữa các collection tương tự. Không thêm edges/pageInfo/totalCount nếu client không cần, nhưng cũng không tự thiết kế một response khác nhau cho mỗi field collection.

## 6. Quy định page size và giới hạn server

Client không được quyền yêu cầu số item không giới hạn. Contract cần quy định:

- Giá trị mặc định nếu client bỏ qua page size.
- Giá trị tối thiểu.
- Giá trị tối đa.
- Hành vi khi page size âm, bằng 0 hoặc vượt giới hạn.
- Server có clamp giá trị hay trả lỗi.

Ví dụ policy:

| Input | Hành vi |
| --- | --- |
| Không truyền first | Dùng default 20 |
| first = 1 | Trả tối đa 1 edge |
| first = 100 | Chấp nhận nếu max là 100 |
| first = 101 | Trả BAD_REQUEST |
| first = 0 | Từ chối hoặc hỗ trợ theo contract được công bố |
| first âm | Từ chối |

Clamp và reject đều có thể dùng, nhưng không nên chọn ngẫu nhiên theo từng resolver. Reject làm lỗi client rõ ràng; clamp thân thiện hơn nhưng client cần biết server đã điều chỉnh page size. Nếu clamp, metadata nên trả effective page size để client không giả định sai.

Giới hạn page size là một phần của bảo vệ query cost. Kết hợp nó với query complexity, timeout, rate limit và giới hạn số lượng nested collection.

## 7. Quy tắc kết hợp arguments

Contract cursor cần nói rõ các arguments nào được kết hợp:

| Arguments | Quy tắc gợi ý |
| --- | --- |
| first không có after | Trang đầu theo sort/filter |
| first cùng after | Trang tiếp theo |
| last cùng before | Trang trước nếu hỗ trợ backward |
| first cùng last | Từ chối |
| after cùng before | Từ chối nếu contract không định nghĩa |
| cursor không có page size | Dùng default hoặc yêu cầu page size theo contract |

Nếu hỗ trợ đầy đủ Relay-style forward/backward pagination, định nghĩa rõ semantics của first/after và last/before. Không nhận first và last cùng lúc nếu không có lý do rõ ràng.

Với offset contract, không trộn page với offset hoặc page với cursor trên cùng field. Nếu API dùng page và size, cả hai phải có default/validation rõ. Nếu dùng offset và limit, quy định đơn vị offset và giới hạn tối đa.

## 8. Thứ tự dữ liệu là một phần của contract

Pagination không có ý nghĩa nếu thứ tự item không ổn định. Mỗi collection cần một sort order xác định:

~~~graphql
enum ProductSort {
    CREATED_AT_DESC
    CREATED_AT_ASC
    NAME_ASC
}
~~~

Tên enum mô tả thứ tự công khai. Server cần ánh xạ từng enum sang thứ tự database ổn định. Ví dụ CREATED_AT_DESC có thể thực thi:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

ID là tie-breaker để các bản ghi có cùng created_at vẫn có thứ tự xác định. Tie-breaker không nhất thiết phải lộ thành một sort option riêng trong schema.

Không nhận tên cột hoặc biểu thức SQL tùy ý từ client. Sort phải là allowlist, tránh SQL injection và tránh tạo query shape không có index phù hợp.

Nếu sort field có thể null, quy định nulls first/last và bảo đảm predicate/cursor theo đúng quy tắc đó. Với NAME_ASC, cần xác định collation/case sensitivity nếu client phụ thuộc vào thứ tự hiển thị chính xác.

## 9. Filter phải nhất quán qua các trang

Khi client duyệt một collection, mỗi trang phải áp dụng cùng filter và authorization scope. Nếu client lấy trang đầu với categoryId = "c-1", sau đó đổi categoryId nhưng vẫn dùng cursor cũ, ranh giới cursor có thể không còn hợp lệ đối với tập dữ liệu mới.

Contract nên quy định một trong hai cách:

1. Cursor được ràng buộc với canonical filter và sort; thay đổi filter/sort làm cursor không hợp lệ.
2. Cursor chỉ đại diện sort key và được áp dụng lên filter mới; semantics này được công bố rõ.

Cách thứ nhất dễ dự đoán hơn cho client. Server có thể lưu hoặc encode fingerprint của filter/sort trong cursor để phát hiện cursor dùng sai scope. Page size có thể được thay đổi giữa các request nếu contract cho phép; nó thường không phải thành phần của cursor identity.

Filter có giá trị mặc định cũng cần canonicalize giống nhau. Ví dụ availability không truyền và availability = ALL có thể mang cùng semantics hoặc khác nhau; phải quyết định trước khi tính fingerprint.

## 10. Cursor là opaque token của contract

Client nên xem cursor là chuỗi opaque: nhận từ edge và gửi lại nguyên vẹn trong after/before. Không parse cursor, tự tăng cursor hoặc tạo cursor từ ID nếu API không công bố format.

Cursor thường cần đủ thông tin để xác định vị trí trong sort order, chẳng hạn createdAt và id. Nó có thể có version để server thay đổi format về sau. Nếu cursor cần chống sửa đổi, server có thể ký payload; Base64 chỉ là encoding và không phải mã hóa.

Cursor không phải credential và không cấp quyền truy cập. Dù cursor có chữ ký, server vẫn phải áp dụng authorization và tenant scope trên mỗi request. Không đặt token, secret hoặc dữ liệu cá nhân không cần thiết trong cursor.

Nếu cursor gắn với filter/sort, server cần kiểm tra fingerprint và trả lỗi có code ổn định khi client dùng cursor sai scope hoặc version không còn hỗ trợ.

## 11. Ý nghĩa của PageInfo

PageInfo giúp client điều hướng mà không tự suy luận từ số lượng edges:

| Field | Semantics cần công bố |
| --- | --- |
| hasNextPage | Có ít nhất một edge sau edge cuối của trang hiện tại |
| hasPreviousPage | Có ít nhất một edge trước edge đầu của trang hiện tại |
| startCursor | Cursor của edge đầu; null khi không có edge |
| endCursor | Cursor của edge cuối; null khi không có edge |

Không đặt hasNextPage = edges.size() == first. Trang có đúng first edge vẫn có thể là trang cuối. Server thường lấy thêm một item hoặc dùng EXISTS để xác định còn dữ liệu.

Nếu chỉ hỗ trợ forward pagination, hãy định nghĩa cách tính hasPreviousPage. Có thể kiểm tra bằng EXISTS theo filter/sort trước vị trí đầu tiên; không tự đặt true chỉ vì request có after nếu dữ liệu đã bị xóa hoặc scope thay đổi.

Với connection rỗng, edges là list rỗng và startCursor/endCursor là null. Không tạo cursor giả.

## 12. totalCount không phải lúc nào cũng cần

totalCount thường được thêm để UI hiển thị "có N kết quả". Tuy nhiên, count chính xác có thể đắt hơn lấy một trang, nhất là khi filter phức tạp, join nhiều bảng hoặc authorization predicate làm tập dữ liệu nhỏ.

Nếu cung cấp totalCount, định nghĩa:

- Count là chính xác hay ước lượng.
- Count có tính theo filter hiện tại không.
- Count có áp dụng tenant/authorization scope không.
- Count có thể null khi server không tính không.
- Count và edges có cùng snapshot hay có thể phản ánh thời điểm khác nhau.

Không để totalCount có semantics mơ hồ. Một field nullable có thể có nghĩa "không được tính" hoặc "không có quyền xem count"; hai trường hợp cần được phân biệt bằng contract/error nếu client cần.

Không chạy COUNT(*) chỉ để tính hasNextPage. Kỹ thuật lấy n + 1 item thường đủ cho forward navigation.

## 13. Dữ liệu thay đổi giữa các request

Pagination thường diễn ra qua nhiều HTTP request, nên database state có thể thay đổi giữa các trang. Contract cần xác định mức nhất quán mà client có thể mong đợi.

Với offset pagination, insert/delete ở đầu danh sách có thể đẩy vị trí của các item và gây lặp hoặc bỏ sót. Với cursor/keyset pagination, insert trước cursor thường ít ảnh hưởng hơn, nhưng update sort key có thể làm item di chuyển qua ranh giới.

Nếu nghiệp vụ cần duyệt một snapshot ổn định, có thể dùng watermark/snapshot token hoặc một phiên bản dữ liệu cố định. Cách này có chi phí lưu trạng thái và cần thời hạn token. Không hứa snapshot consistency nếu backend không thực sự cung cấp nó.

Với feed cập nhật liên tục, contract có thể chấp nhận eventual traversal: item mới xuất hiện ở đầu feed sẽ được nhìn thấy khi client refresh từ đầu, còn phiên duyệt hiện tại tiếp tục từ cursor cũ.

## 14. Pagination trong nested fields

Một query có thể phân trang root collection và nhiều collection lồng nhau:

~~~graphql
query {
    customers(first: 10) {
        edges {
            node {
                id
                orders(first: 5) {
                    edges {
                        node {
                            id
                            items(first: 10) {
                                edges {
                                    node {
                                        productName
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

Mỗi collection có cursor và PageInfo riêng. Cursor của customers không thể dùng cho orders hoặc items. Contract cần làm rõ page size cap áp dụng cho từng collection, tổng số item tối đa trong một operation và query complexity.

Không tự động tải toàn bộ nested collection rồi mới cắt trong Java. Resolver nên chuyển arguments xuống query service/repository để database hoặc downstream API thực hiện pagination.

Nếu nested resolver gọi database/service một lần cho từng parent, pagination vẫn có thể tạo N+1. Dùng batch loading cho parent keys và bảo đảm batch API hiểu filter, sort và page arguments tương ứng. Không gộp các trang của nhiều parent vào một cache key thiếu parent identity.

## 15. Authorization và tenant scope

Mọi trang phải dùng cùng policy truy cập như query không phân trang. Không cho cursor hoặc page number bỏ qua điều kiện tenant, owner hay visibility.

Ví dụ, myOrders không nên nhận customerId tùy ý nếu endpoint chỉ được phép trả đơn hàng của principal hiện tại. Service cần suy ra customer/tenant từ security context rồi áp dụng trong truy vấn:

~~~java
@QueryMapping
public OrderConnection myOrders(
        @Argument Integer first,
        @Argument String after,
        Principal principal) {

    return orderQueryService.findVisibleOrders(
        principal, first, after);
}
~~~

Nếu API có admin search cho phép lọc theo customerId, đó là use case khác với myOrders và cần authorization riêng. Cursor được tạo bởi user khác không được dùng để vượt qua scope hiện tại.

Nếu cursor chứa filter fingerprint, không đưa tenant secret hoặc quyền truy cập vào payload. Server vẫn phải lấy tenant từ principal và kiểm tra quyền.

## 16. Validation và error contract

Pagination arguments là input công khai, cần validate trước khi query:

- first/last/size không âm và không vượt maximum.
- page/offset không vượt giới hạn số nguyên và giới hạn vận hành.
- Không kết hợp các arguments bị cấm.
- Cursor phải decode được, đúng version và đủ sort key.
- Filter và sort phải thuộc schema/allowlist.
- Cursor phải tương thích với filter/sort hiện tại nếu contract yêu cầu.

Có thể chuẩn hóa lỗi:

| Trường hợp | Error code gợi ý |
| --- | --- |
| Page size âm | INVALID_PAGE_SIZE |
| Page size vượt max | PAGE_SIZE_EXCEEDED |
| Cursor sai format | INVALID_CURSOR |
| Cursor version không hỗ trợ | UNSUPPORTED_CURSOR_VERSION |
| Cursor không khớp filter/sort | CURSOR_SCOPE_MISMATCH |
| Sort option không hợp lệ | INVALID_SORT |

Nếu arguments được định nghĩa enum/int trong SDL, GraphQL validation và input coercion sẽ bắt một số lỗi trước resolver. Các quy tắc liên quan nhau như first cùng last, max page size hoặc cursor/filter fingerprint vẫn cần application validation.

Không trả stack trace hoặc nội dung cursor đã decode cho client. Error code phải ổn định để client có thể xử lý.

## 17. Nullability và empty page

Schema cần nhất quán cho collection:

~~~graphql
type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
    totalCount: Int
}

type ProductEdge {
    cursor: String!
    node: Product!
}
~~~

Với contract này:

- Connection luôn tồn tại.
- edges luôn là list, có thể rỗng.
- Mỗi edge phải có cursor và node.
- pageInfo luôn tồn tại.
- totalCount có thể null nếu không được tính theo semantics đã công bố.

Nếu một node bị xóa giữa lúc query và serialize, service cần quyết định loại edge đó khỏi kết quả hoặc trả lỗi theo contract. Không trả edge với node null nếu schema khai báo Product! và client không được chuẩn bị cho trường hợp đó.

Empty page không phải lỗi. Nếu cursor trỏ đến cuối tập, server có thể trả edges rỗng, PageInfo phù hợp và không có GraphQL error. Cursor sai format hoặc sai scope mới là lỗi input.

## 18. Mapping contract sang Spring for GraphQL

SDL công bố arguments và response shape. Ví dụ resolver:

~~~java
@Controller
public class ProductQueryController {

    private final ProductQueryService productQueryService;

    public ProductQueryController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @QueryMapping
    public ProductConnection products(
            @Argument Integer first,
            @Argument String after,
            @Argument ProductFilter filter,
            @Argument ProductSort sort,
            Principal principal) {

        return productQueryService.findProducts(
            first, after, filter, sort, principal);
    }
}
~~~

Controller chỉ bind arguments và gọi service. Service chịu trách nhiệm default, validation, authorization, cursor decoding, repository query và xây PageInfo.

Có thể gom arguments vào một Java record nếu input contract được thiết kế thành input object:

~~~graphql
input ProductPageRequest {
    first: Int = 20
    after: String
    filter: ProductFilter
    sort: ProductSort = CREATED_AT_DESC
}
~~~

~~~graphql
type Query {
    products(input: ProductPageRequest): ProductConnection!
}
~~~

Đây là biến thể thay cho field products(first, after, filter, sort) ở ví dụ trước; không khai báo cả hai field cùng tên trong một schema. Input object tiện khi có nhiều pagination/filter arguments và cần tái sử dụng. Arguments riêng phù hợp với query đơn giản và tương thích Relay convention. Không cần lồng input chỉ để gom hai field nếu nó làm client query dài hơn mà không có lợi ích rõ.

## 19. DTO cho Page và Connection

Không expose trực tiếp framework Page hoặc Slice nếu contract không muốn phụ thuộc Spring Data. Tạo DTO riêng:

~~~java
public record ProductEdge(String cursor, ProductView node) {
}

public record PageInfo(
        boolean hasNextPage,
        boolean hasPreviousPage,
        String startCursor,
        String endCursor) {
}

public record ProductConnection(
        List<ProductEdge> edges,
        PageInfo pageInfo,
        Integer totalCount) {
}
~~~

Offset contract có thể dùng:

~~~java
public record OffsetPageInfo(
        int page,
        int size,
        boolean hasNextPage,
        Integer totalElements,
        Integer totalPages) {
}

public record ProductPage(
        List<ProductView> items,
        OffsetPageInfo pageInfo) {
}
~~~

DTO giữ schema contract độc lập với persistence implementation. Sau này service có thể đổi từ Spring Data Page sang keyset query hoặc search backend mà không cần thay response shape.

## 20. Không để Spring Data Page trở thành public contract

Spring Data Page chứa content, number, size, totalElements, totalPages và các method tiện ích. Nó phù hợp ở repository/application boundary, nhưng public GraphQL contract nên định nghĩa field và semantics mà client cần.

Ví dụ mapping:

~~~java
Page<ProductEntity> page = repository.findAll(specification, pageable);

return new ProductPage(
    page.getContent().stream()
        .map(productMapper::toView)
        .toList(),
    new OffsetPageInfo(
        page.getNumber(),
        page.getSize(),
        page.hasNext(),
        Math.toIntExact(page.getTotalElements()),
        page.getTotalPages()));
~~~

Đoạn mapping cần cân nhắc overflow của totalElements; Math.toIntExact sẽ ném lỗi nếu count vượt Int. Nếu dữ liệu có thể lớn hơn giới hạn, dùng scalar phù hợp hoặc bỏ count.

Với Slice, server có thể biết hasNext mà không cần total count. Nếu public contract chỉ cần hasNextPage, Slice có thể phù hợp hơn Page, nhưng vẫn nên map sang DTO riêng.

## 21. Client navigation contract

Client nên dùng metadata server trả về:

- Trang đầu: không gửi after.
- Trang tiếp: gửi endCursor của trang hiện tại vào after.
- Trang trước: dùng startCursor và before nếu backward pagination được hỗ trợ.
- Không tự tăng hoặc giải mã cursor.
- Reset cursor khi filter hoặc sort thay đổi.
- Giữ filter/sort ổn định trong suốt một lần duyệt.
- Có thể thay đổi page size nếu contract cho phép.
- Dùng hasNextPage/hasPreviousPage để bật/tắt điều hướng.

Với infinite scroll, client thường append edges và deduplicate theo node ID nếu có thể nhận cùng item qua refresh hoặc cập nhật live. Dedup là chiến lược UI; server vẫn cần đảm bảo thứ tự và cursor semantics.

Với offset pagination, client có thể lưu page number và nhảy trực tiếp đến page khác. Nhưng nếu dataset thay đổi, page number không bảo đảm item ở trang đó giữ nguyên như lần đọc trước.

## 22. Backward pagination

Nếu hỗ trợ backward traversal, contract có thể dùng last và before:

Đây là phiên bản thay thế cho khai báo Query forward-only ở phần Connection, không phải một root type thứ hai trong cùng schema:

~~~graphql
type Query {
    products(
        first: Int
        after: String
        last: Int
        before: String
        filter: ProductFilter
        sort: ProductSort = CREATED_AT_DESC
    ): ProductConnection!
}
~~~

Cần định nghĩa rõ:

- first/after dùng để đi về phía sau trong thứ tự công khai.
- last/before dùng để lấy các edge đứng trước cursor.
- Không nhận first cùng last trong một request.
- startCursor/endCursor luôn phản ánh thứ tự công khai của connection.
- hasNextPage/hasPreviousPage được tính theo cùng sort/filter scope.

Server có thể đảo sort nội bộ khi query backward rồi đảo kết quả lại trước khi trả response. Client không nên thấy thứ tự khác chỉ vì dùng last/before.

Nếu sản phẩm chỉ có nút "Load more", forward-only contract đơn giản hơn và có thể đủ. Không triển khai backward chỉ vì Relay có convention đó nếu không có use case.

## 23. Pagination và cache

Cache key của một trang cần bao gồm các thành phần ảnh hưởng đến kết quả:

- Field/root collection.
- Filter đã canonicalize.
- Sort order.
- Cursor hoặc page/offset.
- Page size nếu response shape phụ thuộc nó.
- Tenant/user scope khi dữ liệu được phân quyền.

Không cache theo cursor đơn lẻ nếu cursor không ràng buộc filter/sort hoặc authorization scope. Không chia sẻ response đã phân quyền giữa các user chỉ vì query text giống nhau.

Cursor thường là opaque và có thể hết hạn nếu contract dùng snapshot token. Client cần xử lý cursor invalid/expired bằng cách quay lại trang đầu hoặc refresh collection theo semantics được công bố.

Cache invalidation cần xem xét mutation tạo/xóa/cập nhật item có ảnh hưởng đến sort/filter. Không hứa cache pagination luôn nhất quán tức thời nếu hệ thống dùng eventual consistency.

## 24. Performance và query planning

Pagination contract giới hạn response size nhưng không tự bảo đảm query nhanh. Server cần query plan phù hợp:

- Offset lớn có thể phải scan/bỏ qua nhiều row.
- Cursor/keyset cần predicate khớp sort key.
- Composite index nên hỗ trợ equality filters và sort columns.
- Projection chỉ lấy các cột cần cho edge/node.
- Tránh count không cần thiết.
- Batch nested fields để tránh N+1.
- Giới hạn tổng page size ở nested collections.

Nếu collection được tìm qua search engine, cursor có thể là search-after token hoặc continuation token của backend. Client vẫn chỉ thấy opaque String; resolver chuyển nó sang backend token theo contract.

Đừng expose cursor nội bộ của database hoặc search engine như một format được client tự tạo. Giữ adapter giữa public cursor và backend paging mechanism để có thể thay đổi backend.

## 25. Kiểm thử contract bằng GraphQlTester

Test nên kiểm tra response shape và hành vi giữa các trang:

~~~java
@Test
void returnsNextPageUsingEndCursor() {
    var firstResponse = graphQlTester.document("""
            query {
                products(first: 2, sort: CREATED_AT_DESC) {
                    edges {
                        cursor
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
            """)
        .execute();

    firstResponse.errors().verify();
    firstResponse.path("products.edges")
        .entityList(ProductEdgeView.class)
        .hasSize(2);

    String endCursor = firstResponse.path("products.pageInfo.endCursor")
        .entity(String.class)
        .get();

    var nextResponse = graphQlTester.document("""
            query NextProducts($after: String) {
                products(first: 2, after: $after, sort: CREATED_AT_DESC) {
                    edges {
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                    }
                }
            }
            """)
        .variable("after", endCursor)
        .execute();

    nextResponse.errors().verify();
    nextResponse.path("products.edges")
        .entityList(ProductEdgeIdView.class)
        .hasSize(2);
}
~~~

Fixture cần đủ dữ liệu để có ít nhất hai trang. DTO view dùng trong test phải khớp selection set. Test cũng nên so sánh ID giữa hai trang để xác nhận không có item trùng trong fixture ổn định.

## 26. Bộ test cần có cho pagination contract

| Nhóm | Trường hợp cần kiểm tra |
| --- | --- |
| Default | Bỏ page size thì server dùng default đã công bố |
| Boundaries | Size = 1, max size, max + 1, 0 và số âm |
| First page | Không cursor, đúng sort/filter |
| Next page | Dùng endCursor của trang trước |
| Last page | hasNextPage = false |
| Empty collection | edges rỗng, cursors null |
| Sort | Thứ tự xác định khi nhiều item cùng sort value |
| Filter | Filter được giữ qua trang và cursor sai scope bị từ chối |
| Cursor | Sai format, version cũ, thiếu key hoặc hết hạn |
| Backward | last/before trả đúng thứ tự công khai |
| Count | totalCount đúng semantics hoặc null theo contract |
| Authorization | Không thể dùng cursor để đọc tenant khác |
| Concurrent changes | Insert/delete/update có hành vi theo consistency contract |
| Nested collection | Mỗi parent có cursor/pageInfo riêng |
| Performance | Query count không tăng tuyến tính do nested resolver |

Test GraphQL contract bằng GraphQlTester. Test repository/query plan riêng với database phù hợp khi cần xác minh keyset, index và performance. Test client integration nếu response được cache hoặc gateway biến đổi.

## 27. Tiến hóa pagination contract

Pagination contract là public API và cần tiến hóa tương thích:

- Thêm field metadata nullable thường an toàn hơn đổi nghĩa field hiện có.
- Không đổi page index từ zero-based sang one-based trong cùng field.
- Không đổi sort mặc định nếu client phụ thuộc thứ tự hiện tại mà không thông báo.
- Không đổi cursor format theo cách làm cursor đang được client giữ trở nên vô hiệu mà không có policy.
- Không thay page/size thành first/after trong cùng field.
- Không đổi semantics của hasNextPage hoặc totalCount.

Nếu cần chuyển offset sang cursor:

1. Thêm field connection mới, ví dụ productsConnection.
2. Giữ field page cũ trong giai đoạn chuyển đổi.
3. Đánh dấu field cũ @deprecated với hướng dẫn cụ thể.
4. Theo dõi client usage.
5. Cập nhật client và kiểm thử cả hai contract.
6. Chỉ xóa field cũ khi đã xác nhận consumer đã chuyển.

Không trả cursor theo format nội bộ rồi yêu cầu client migrate khi backend thay đổi. Public cursor nên là token do server quản lý và có thể version hóa.

## 28. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Không quy định page bắt đầu từ 0 hay 1 | Client gọi sai trang | Công bố indexing convention |
| Không giới hạn page size | Response quá lớn và query cost cao | Default và maximum rõ ràng |
| Dùng sort không ổn định | Item có thể lặp hoặc bị bỏ qua | Unique tie-breaker |
| hasNextPage suy ra từ edges.size() | Trang cuối có thể bị báo sai | Fetch thêm một item hoặc EXISTS |
| totalCount luôn chạy dù client không cần | Query count đắt | Tính count theo nhu cầu và semantics |
| Dùng cursor với filter khác | Ranh giới trang không còn ý nghĩa | Ràng buộc cursor với filter/sort |
| Tin cursor là credential | Replay có thể vượt quyền | Authorization trên mọi request |
| Dùng page và cursor lẫn lộn | Client không hiểu navigation | Chọn một contract rõ cho mỗi field |
| Trả Spring Data Page trực tiếp | API phụ thuộc framework | Map sang GraphQL DTO |
| Nested list không có pagination | Query có thể trả dữ liệu khổng lồ | Connection riêng cho từng collection |
| Batch loader bỏ qua parent/filter scope | Trả nhầm dữ liệu giữa parent | Batch key đầy đủ và authorization scope |
| Đổi default sort âm thầm | Client thấy item thay đổi thứ tự | Version/evolution có kiểm soát |
| Xóa offset field ngay khi có cursor field | Client cũ bị breaking | Deprecate và migrate theo usage |

## 29. Quy trình thiết kế pagination contract

Một quy trình có thể áp dụng cho từng collection:

1. Xác định use case client: bảng có số trang, infinite scroll hay feed.
2. Chọn offset/page hoặc cursor/connection.
3. Định nghĩa arguments, default và giới hạn.
4. Công bố sort options và thứ tự ổn định.
5. Xác định filter scope và quy tắc cursor reuse.
6. Định nghĩa response shape, PageInfo và totalCount semantics.
7. Chọn nullability và error codes.
8. Áp dụng authorization/tenant scope cho mọi trang.
9. Thiết kế resolver/service DTO độc lập với repository type.
10. Kiểm thử navigation, boundaries, concurrent changes và schema compatibility.
11. Đo query plan, index, nested query count và response size.

## 30. Nguyên tắc thiết kế Pagination contract

Pagination contract phải mô tả hành vi mà client có thể dựa vào: kiểu navigation, page size, sort order, filter scope, metadata, empty page và lỗi input. Chọn offset khi cần nhảy đến page number trên collection vừa phải; chọn cursor connection khi cần duyệt collection lớn và tiếp tục từ một vị trí ổn định.

Giữ sort order xác định, ràng buộc cursor với filter/sort khi cần, áp dụng authorization ở mọi request và không để cursor trở thành credential. Công bố rõ semantics của hasNextPage, hasPreviousPage và totalCount; giới hạn page size và nested collection để kiểm soát query cost.

Trong Spring for GraphQL, khai báo contract bằng SDL, bind arguments qua @Argument và trả DTO Page/Connection riêng. Application service chịu trách nhiệm validation, query và metadata; resolver không nên để client phụ thuộc Spring Data Page hoặc backend continuation token. Kiểm thử contract bằng GraphQlTester và kiểm tra query plan ở repository layer.

Một pagination API tốt cho phép client tiếp tục duyệt dữ liệu theo quy tắc ổn định, trong khi server vẫn có thể thay đổi cách truy vấn và lưu trữ phía sau contract.

## Tài liệu tham khảo

- [Relay Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Data Commons — Paging and Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [GraphQL Specification — Type System](https://spec.graphql.org/)
