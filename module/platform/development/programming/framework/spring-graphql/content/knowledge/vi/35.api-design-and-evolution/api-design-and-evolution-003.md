# Backward compatibility

GraphQL API thường được thiết kế để tiến hóa liên tục trong một schema chung. Khi sản phẩm cần thêm chức năng, server có thể bổ sung type, field hoặc argument để client mới sử dụng, trong khi client cũ vẫn tiếp tục gửi operation như trước. Cách tiến hóa này chỉ hiệu quả khi server giữ được **backward compatibility**: những operation đang hợp lệ và hành vi mà client đang dựa vào vẫn hoạt động sau khi API thay đổi.

Trong Spring for GraphQL, schema SDL là hợp đồng mà client nhìn thấy. Resolver, scalar, validation, authorization và logic nghiệp vụ quyết định hành vi thực tế phía sau hợp đồng đó. Vì vậy, một thay đổi có thể không làm SDL mất tính hợp lệ nhưng vẫn phá vỡ client ở runtime, chẳng hạn field trước đây luôn có dữ liệu nay trả `null`, enum xuất hiện giá trị mới mà client cũ không xử lý, hoặc default pagination thay đổi.

Bài học này trình bày cách phân loại thay đổi tương thích, cách dùng `@deprecated` để chuyển client dần dần, cách kiểm tra operation cũ bằng Spring for GraphQL, và cách đưa schema compatibility vào quy trình CI/CD.

## 1. Backward compatibility là gì?

Backward compatibility nghĩa là phiên bản server mới vẫn hỗ trợ các client đang dùng hợp đồng cũ trong khoảng thời gian mà API cam kết hỗ trợ.

Ví dụ, phiên bản đầu có schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    name: String!
}
~~~

Client cũ gửi:

~~~graphql
query LegacyBook($id: ID!) {
    book(id: $id) {
        id
        name
    }
}
~~~

Khi sản phẩm muốn đổi tên `name` thành `displayName`, cách thay đổi an toàn là thêm field mới và tiếp tục hỗ trợ field cũ:

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
~~~

Client mới có thể chuyển sang `displayName`; client cũ vẫn truy vấn `name` mà không cần phát hành bản cập nhật ngay lập tức.

Một thay đổi tương thích cần xét cả schema contract và hành vi runtime. Nếu query vẫn validate nhưng server trả dữ liệu với ý nghĩa khác, client vẫn có thể bị hỏng.

## 2. Bốn lớp tương thích của GraphQL API

| Lớp | Câu hỏi cần trả lời | Ví dụ thay đổi có rủi ro |
| --- | --- | --- |
| Schema compatibility | Operation cũ có còn validate được không? | Xóa field, đổi tên argument, thay type |
| Data compatibility | Client có còn nhận được hình dạng và giá trị dữ liệu đã cam kết không? | Field `String!` bắt đầu trả null, đổi ý nghĩa enum |
| Behavioral compatibility | Cùng operation có còn cho kết quả và tác dụng nghiệp vụ như trước không? | Đổi default sort, pagination, mutation side effect |
| Operational compatibility | Client cũ có còn được xác thực, phân quyền và phục vụ trong điều kiện hỗ trợ không? | Siết authorization, bỏ client credential, giảm rate limit |

GraphQL specification xem thay đổi làm một request vốn hợp lệ trở thành không hợp lệ là breaking change. Tuy nhiên, định nghĩa đó chưa bao quát hết rủi ro runtime hoặc client code generation. Vì vậy, quy trình API nên phân biệt:

- **Breaking change:** operation cũ không còn hợp lệ hoặc không thể dùng theo hợp đồng cũ.
- **Dangerous change:** operation vẫn hợp lệ nhưng có thể làm một số client lỗi khi chạy.
- **Safe additive change:** mở rộng schema mà client cũ không cần thay đổi vẫn tiếp tục hoạt động.

Không nên chỉ dựa vào schema diff để kết luận một thay đổi hoàn toàn an toàn.

## 3. GraphQL thường tiến hóa schema thay vì tạo version cho mỗi thay đổi

REST API thường dùng URL hoặc header để phân biệt version. GraphQL cho phép client chọn chính xác field cần đọc, nên nhiều thay đổi có thể được triển khai bằng cách bổ sung khả năng vào cùng một schema.

Ví dụ:

- Thêm `Book.subtitle` không ảnh hưởng operation chưa chọn field đó.
- Thêm một query mới `popularBooks` không làm query cũ mất hiệu lực.
- Thêm input field tùy chọn có thể mở rộng cách lọc dữ liệu.
- Thêm một mutation mới không bắt buộc client cũ phải dùng nó.

Vì vậy, GraphQL thường ưu tiên schema tiến hóa theo hướng additive và tránh tạo `/graphql/v2` chỉ vì một field mới.

Điều này không có nghĩa GraphQL cấm versioning. Có thể cần version hoặc schema riêng khi thay đổi nghiệp vụ không thể duy trì song song, yêu cầu pháp lý khác nhau, hoặc hai nhóm client cần hợp đồng độc lập. Hãy dùng versioning khi ranh giới sản phẩm thực sự khác nhau, không dùng nó thay cho quy trình deprecation.

## 4. Những thay đổi thường tương thích

Các thay đổi sau thường an toàn với operation cũ nếu không làm thay đổi hành vi của field hiện có:

| Thay đổi | Vì sao thường an toàn | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Thêm field vào object type | Client chỉ nhận field đã chọn | Resolver mới không làm thay đổi field cũ hoặc tài nguyên chung |
| Thêm query/mutation mới | Operation cũ không tham chiếu field mới | Không đổi semantics của root field hiện có |
| Thêm argument tùy chọn | Client cũ không cần truyền argument | Default và hành vi khi bỏ qua phải được xác định |
| Thêm input field tùy chọn | Client cũ vẫn có thể gửi input object cũ | Không làm thay đổi validation/default của field hiện tại |
| Thêm type không được tham chiếu | Operation hiện tại không dùng type đó | Kiểm tra composition nếu dùng Federation |
| Bổ sung mô tả SDL | Không thay đổi kiểu hoặc runtime | Mô tả phải phản ánh đúng hợp đồng |

Ví dụ thêm field:

~~~graphql
type Book {
    id: ID!
    title: String!
    subtitle: String
}
~~~

Operation cũ chỉ chọn `id` và `title`, nên vẫn hợp lệ và không phải thay đổi cách đọc dữ liệu.

Dù vậy, một thay đổi additive vẫn có thể ảnh hưởng client dùng code generation, exhaustive enum/union handling hoặc schema snapshot. Hãy kiểm tra nhóm client thực tế thay vì mặc định mọi thay đổi thêm đều vô hại.

## 5. Những thay đổi có thể phá vỡ client

Các thay đổi dưới đây cần được xem là breaking hoặc dangerous cho đến khi có bằng chứng ngược lại:

| Thay đổi | Rủi ro |
| --- | --- |
| Xóa hoặc đổi tên field/type | Operation tham chiếu tên cũ không còn validate |
| Xóa hoặc đổi tên argument | Operation truyền argument cũ không còn hợp lệ |
| Thêm required argument không có default | Operation cũ không truyền argument sẽ lỗi validation |
| Xóa input field | Client gửi input field đó sẽ lỗi validation |
| Xóa enum value | Operation dùng giá trị đó có thể không còn hợp lệ |
| Đổi scalar/object/list type | Client nhận shape hoặc kiểu dữ liệu khác |
| Đổi nullability | Client có thể nhận null hoặc lỗi null propagation ngoài dự kiến |
| Đổi default argument/input | Operation không truyền giá trị có thể nhận hành vi khác |
| Thay đổi ý nghĩa field | Query vẫn chạy nhưng client diễn giải sai dữ liệu |
| Siết authorization hoặc validation | Client từng thành công có thể nhận lỗi hoặc không còn truy cập được |

Một số thay đổi như thêm enum value hoặc thêm member vào union không làm operation cũ trở thành invalid theo GraphQL validation, nhưng có thể phá vỡ client sinh code có `switch` exhaustive. Nên coi chúng là dangerous change và đánh giá khả năng xử lý giá trị mới của client.

## 6. Nullability là một phần quan trọng của hợp đồng

GraphQL dùng `!` để cam kết một giá trị không null. Thay đổi nullability có thể ảnh hưởng trực tiếp đến cách client xử lý response và cách GraphQL lan truyền lỗi.

| Trước | Sau | Rủi ro |
| --- | --- | --- |
| `title: String!` | `title: String` | Client cũ có thể giả định title luôn tồn tại nhưng nay phải xử lý null |
| `title: String` | `title: String!` | Server cam kết mạnh hơn, nhưng nếu resolver vẫn trả null, lỗi sẽ lan truyền lên parent |
| `books: [Book!]!` | `books: [Book]` | Client phải xử lý list null và item null |
| `books: [Book]` | `books: [Book!]!` | Hợp đồng dữ liệu thay đổi; resolver và dữ liệu lưu trữ phải đáp ứng cam kết mới |

Không nên đổi nullability chỉ vì muốn SDL trông “chặt chẽ” hơn. Hãy kiểm tra dữ liệu thực, lỗi downstream, cache và mọi client đang tiêu thụ field.

Nếu cần một field có cam kết nullability khác, cách an toàn thường là thêm field mới với hợp đồng mới, giữ field cũ cho client hiện tại, rồi deprecate field cũ sau khi migration hoàn tất.

## 7. Enum và union cần chú ý client exhaustive handling

Enum output có thể được sinh thành enum Java, Kotlin, TypeScript hoặc Swift trong client. Một số client xử lý tất cả giá trị đã biết bằng `switch` và không có nhánh fallback.

Ví dụ:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    status: BookStatus!
}
~~~

Thêm `SCHEDULED` là thay đổi additive đối với schema, nhưng client cũ có thể không biết giá trị này:

~~~graphql
enum BookStatus {
    DRAFT
    SCHEDULED
    PUBLISHED
    ARCHIVED
}
~~~

Trước khi thêm enum output value, hãy xác minh client có nhánh `unknown`/fallback hoặc có thể được cập nhật đồng bộ.

Tương tự, thêm một object type vào union có thể làm client phải xử lý một nhánh mới:

~~~graphql
union SearchResult = Book | Author | Publisher
~~~

Nếu thêm `Magazine`, client dùng inline fragment và `__typename` cần có chiến lược cho member chưa biết. Đừng xóa enum value hoặc union member đang được client gửi/đọc.

## 8. Argument, input object và default value

Thay đổi ở input position có thể làm operation cũ không còn hợp lệ hoặc đổi hành vi.

Ví dụ ban đầu:

~~~graphql
type Query {
    books(first: Int = 20, after: String): [Book!]!
}
~~~

Nếu đổi `first` thành required mà không có default:

~~~graphql
type Query {
    books(first: Int!, after: String): [Book!]!
}
~~~

Các operation cũ gọi `books` mà không truyền `first` sẽ lỗi validation.

Tương tự, xóa input field, đổi tên argument hoặc đổi enum value được dùng làm input có thể phá vỡ operation đã phát hành.

Default value cũng là một phần của contract. Nếu client bỏ qua `first`, thay default từ 20 thành 100 có thể làm response lớn hơn và tăng tải server. Nếu đổi default sort từ `NEWEST` sang `POPULAR`, client vẫn validate nhưng dữ liệu trả về thay đổi.

Khi thay đổi default, hãy kiểm tra cả hành vi và giới hạn tài nguyên, không chỉ schema diff.

## 9. Thay đổi schema không phải cách duy nhất gây breaking change

Client thường phụ thuộc vào semantics mà SDL không thể mô tả đầy đủ. Ví dụ field `price: Money!` vẫn giữ nguyên type nhưng có thể thay đổi từ giá trước thuế sang giá đã gồm thuế.

Những thay đổi runtime có thể phá vỡ client:

- Thay đổi đơn vị tiền tệ, múi giờ, làm tròn hoặc cách diễn giải giá trị.
- Thay đổi thứ tự mặc định của list hoặc pagination cursor.
- Đổi cách tính `totalCount`, trạng thái hoặc business status.
- Thay đổi validation rule, error code hoặc việc trả partial data.
- Thay đổi authorization khiến user/tenant cũ không còn truy cập được.
- Thay đổi side effect của mutation hoặc tính idempotent.
- Thay đổi tần suất, thứ tự hoặc payload của subscription event.

Hãy ghi semantics quan trọng trong description của SDL và tài liệu API. Với thay đổi nghiệp vụ, cần contract test và changelog dù schema diff không báo breaking.

## 10. Dùng @deprecated để báo trước thay đổi

Directive `@deprecated` đánh dấu field hoặc enum value không còn được khuyến nghị sử dụng. Thành phần cũ vẫn tồn tại trong schema và tiếp tục hoạt động trong thời gian client chuyển đổi.

Ví dụ:

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}

enum BookStatus {
    PUBLISHED
    OUT_OF_PRINT @deprecated(reason: "Use ARCHIVED instead.")
    ARCHIVED
}
~~~

GraphQL introspection cung cấp `isDeprecated` và `deprecationReason` để công cụ hiển thị cảnh báo cho developer.

Một deprecation reason tốt nên nói rõ:

- Thành phần nào thay thế.
- Client cần chuyển sang cách dùng nào.
- Có khác biệt về semantics hoặc dữ liệu hay không.
- Tài liệu migration nào cần đọc.

Đừng deprecate field chỉ vì muốn đổi tên mà chưa có field thay thế hoạt động đầy đủ.

## 11. Quy trình đổi tên field mà không làm hỏng client cũ

Giả sử API đang có `Book.name` và muốn đổi sang `Book.displayName`.

**Bước 1: Thêm field mới và giữ field cũ.**

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
~~~

**Bước 2: Cho cả hai field dùng cùng nguồn dữ liệu.**

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "name")
    public String legacyName(Book book) {
        return book.displayName();
    }

    @SchemaMapping(typeName = "Book", field = "displayName")
    public String displayName(Book book) {
        return book.displayName();
    }
}
~~~

Hai field có cùng semantics nên client cũ và client mới nhận cùng giá trị. Nếu field cũ và mới có semantics khác nhau, hãy mô tả khác biệt và không dùng chung resolver một cách máy móc.

**Bước 3: Chuyển client sang field mới.**

Client mới chọn `displayName`; client cũ tiếp tục chọn `name`.

**Bước 4: Theo dõi việc sử dụng field cũ.**

Ghi nhận operation/client nào còn chọn `Book.name`, rồi liên hệ hoặc hướng dẫn nhóm client cần migration.

**Bước 5: Chỉ xóa field cũ khi đạt điều kiện kết thúc hỗ trợ.**

Không xóa chỉ vì đã phát hành field mới. Cần kiểm tra usage, phiên bản client còn được hỗ trợ và lịch deprecation đã công bố.

## 12. Thay thế query hoặc mutation cũ bằng field mới

Khi muốn thay một root field, giữ nguyên field cũ và tạo field mới với tên hoặc input contract rõ hơn.

~~~graphql
type Query {
    searchBooks(query: String!): [Book!]!
        @deprecated(reason: "Use findBooks(text:) instead.")

    findBooks(text: String!): [Book!]!
}
~~~

Cả hai resolver có thể gọi chung một service:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookSearchController {

    private final BookSearchService searchService;

    public BookSearchController(BookSearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<Book> searchBooks(@Argument String query) {
        return searchService.search(query);
    }

    @QueryMapping
    public List<Book> findBooks(@Argument String text) {
        return searchService.search(text);
    }
}
~~~

Cách này tránh đổi tên argument tại chỗ. Operation cũ vẫn hợp lệ, còn operation mới có contract mới.

Với mutation, cần giữ semantics của side effect. Nếu tạo mutation mới, hãy bảo đảm việc gọi mutation cũ và mới không vô tình tạo hai cách xử lý khác nhau hoặc tạo dữ liệu trùng lặp.

## 13. Deprecate argument và input field

Một số phiên bản GraphQL specification hỗ trợ `@deprecated` trên argument và input field, nhưng khả năng tooling và GraphQL Java phụ thuộc baseline đang dùng. Hãy xác nhận phiên bản GraphQL Java mà Spring for GraphQL quản lý trước khi dựa vào introspection deprecation cho các vị trí này.

Dù có hỗ trợ directive, deprecate argument không giải quyết được việc thay đổi contract nếu client cũ vẫn cần truyền argument đó. Hãy giữ argument cũ có hiệu lực trong giai đoạn migration và bổ sung đường đi mới.

Ví dụ nếu cần đổi cách tìm kiếm, thường dễ quản lý hơn khi thêm field mới:

~~~graphql
type Query {
    searchBooks(query: String!): [Book!]!
        @deprecated(reason: "Use findBooks(text:) instead.")
    findBooks(text: String!): [Book!]!
}
~~~

Không đổi `query: String!` thành `text: String!` ngay trên field cũ; operation đang truyền `query` sẽ không còn hợp lệ.

## 14. Theo dõi usage trước khi xóa thành phần deprecated

Schema introspection cho biết một field đã deprecated, nhưng không cho biết client nào còn sử dụng nó. Muốn quyết định xóa an toàn, server cần telemetry về operation thực tế.

Nên theo dõi tối thiểu:

- Operation name hoặc persisted operation ID.
- Client name và client version nếu có.
- Type và field path được chọn.
- Số lần gọi trong một khoảng thời gian đủ dài.
- Tỷ lệ lỗi và ảnh hưởng tới nhóm client cụ thể.

Không ghi raw variables hoặc dữ liệu cá nhân chỉ để đo field usage. Chỉ thu thập metadata cần thiết và tuân theo chính sách privacy của hệ thống.

Nếu API có mobile client, hãy tính đến phiên bản ứng dụng cũ còn được cài đặt nhưng không còn phát hành thường xuyên. Usage bằng 0 trong một tuần chưa chắc chứng minh mọi client đã migration.

## 15. Kiểm tra deprecation bằng GraphQL introspection

Client tool có thể truy vấn schema để phát hiện field deprecated:

~~~graphql
query InspectBookDeprecations {
    __type(name: "Book") {
        fields(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
~~~

Response giúp xác nhận `name` vẫn tồn tại và có reason rõ ràng, trong khi `displayName` là field mới.

Có thể kiểm tra enum value tương tự:

~~~graphql
query InspectBookStatus {
    __type(name: "BookStatus") {
        enumValues(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
~~~

Introspection chỉ kiểm tra metadata schema. Nó không chứng minh resolver cũ vẫn hoạt động đúng hoặc client đã ngừng sử dụng field. Hãy kết hợp introspection, integration test và usage telemetry.

## 16. Contract test operation cũ bằng GraphQlTester

Một cách trực tiếp để giữ backward compatibility là lưu các operation quan trọng của client dưới dạng fixture hoặc test document. Sau mỗi thay đổi schema/resolver, thực thi lại các operation đó.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@SpringBootTest
class BackwardCompatibilityTests {

    private final GraphQlTester graphQlTester;

    @Autowired
    BackwardCompatibilityTests(GraphQlTester graphQlTester) {
        this.graphQlTester = graphQlTester;
    }

    @Test
    void legacyBookOperationStillWorks() {
        graphQlTester.document("""
                query LegacyBook($id: ID!) {
                    book(id: $id) {
                        id
                        name
                    }
                }
                """)
                .variable("id", "book-42")
                .execute()
                .errors()
                .verify()
                .path("book.name")
                .entity(String.class)
                .isEqualTo("Clean Code");
    }
}
~~~

Ví dụ giả định test configuration đã cung cấp `GraphQlTester` kết nối tới ứng dụng. Test này xác minh operation cũ còn validate, resolver vẫn hoạt động và field cũ trả đúng dữ liệu.

Nên giữ expected result có ý nghĩa nghiệp vụ. Chỉ kiểm tra response không có error là chưa đủ nếu semantics của field có thể đã thay đổi.

## 17. Test cả client mới và deprecation metadata

Sau khi thêm field thay thế, cần kiểm tra cả đường đi mới:

~~~java
@Test
void newBookOperationReturnsDisplayName() {
    graphQlTester.document("""
            query NewBook($id: ID!) {
                book(id: $id) {
                    id
                    displayName
                }
            }
            """)
            .variable("id", "book-42")
            .execute()
            .errors()
            .verify()
            .path("book.displayName")
            .entity(String.class)
            .isEqualTo("Clean Code");
}
~~~

Có thể test introspection để bảo đảm field cũ vẫn được đánh dấu deprecated:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

record BookFieldMetadata(
        String name,
        boolean isDeprecated,
        String deprecationReason) {
}

@Test
void legacyNameFieldIsDeprecated() {
    graphQlTester.document("""
            query {
                __type(name: "Book") {
                    fields(includeDeprecated: true) {
                        name
                        isDeprecated
                        deprecationReason
                    }
                }
            }
            """)
            .execute()
            .path("__type.fields")
            .entityList(BookFieldMetadata.class)
            .satisfies(fields -> {
                BookFieldMetadata legacyName = fields.stream()
                        .filter(field -> field.name().equals("name"))
                        .findFirst()
                        .orElseThrow();

                assertThat(legacyName.isDeprecated()).isTrue();
                assertThat(legacyName.deprecationReason())
                        .isEqualTo("Use displayName instead.");
            });
}
~~~

`BookFieldMetadata` là DTO test tương ứng với các field `name`, `isDeprecated` và `deprecationReason`. Có thể dùng projection khác theo cách deserialize mà test suite đang sử dụng.

## 18. Đưa schema compatibility vào CI/CD

Contract test trong một repository chỉ kiểm tra operation mà nhóm đã lưu. Nếu có nhiều client độc lập, cần thêm kiểm tra schema diff và operation usage.

Một pipeline thường gồm:

1. Validate SDL và build schema.
2. So sánh schema mới với schema đã phát hành.
3. Phân loại breaking và dangerous changes.
4. Validate các operation đã đăng ký hoặc thu thập từ client.
5. Chạy contract/integration tests của các client quan trọng.
6. Kiểm tra Federation composition nếu schema thuộc subgraph.
7. Chỉ publish schema sau khi các check bắt buộc đạt.

Apollo GraphOS Schema Checks là một ví dụ: build check xác nhận subgraph có thể compose, operations check so sánh thay đổi với operation telemetry để tìm client có nguy cơ bị ảnh hưởng. Những công cụ khác có thể so sánh SDL snapshots và validate operation registry tương tự.

Schema checks chỉ thấy operation đã được thu thập trong phạm vi dữ liệu và thời gian cấu hình. Operation hiếm dùng, client cũ offline hoặc client chưa gửi metadata có thể không xuất hiện. Vì vậy kết quả pass không thay thế chính sách hỗ trợ client và contract test.

## 19. Backward compatibility trong Federation

Với Spring for GraphQL Federation, một subgraph thay đổi schema có thể ảnh hưởng hai phạm vi:

- Client gọi supergraph và phụ thuộc vào operation hiện có.
- Subgraph khác phụ thuộc vào entity key, field ownership hoặc field được expose qua composition.

Trước khi xóa hoặc đổi một field trong subgraph:

- Kiểm tra field có được subgraph khác dùng qua `@key`, `@requires` hoặc `@provides` hay không.
- Kiểm tra thay đổi có làm supergraph composition thất bại không.
- Kiểm tra operation của client qua router, không chỉ operation gửi trực tiếp tới subgraph.
- Giữ entity key và field contract ổn định trong giai đoạn migration.
- Chạy composition check và operation check trước khi publish.

Một thay đổi có thể hợp lệ trong SDL riêng lẻ nhưng không compose được với các subgraph còn lại. Vì vậy Federation cần cả schema compatibility và composition compatibility.

## 20. Quy trình deprecation và removal an toàn

Một quy trình có thể áp dụng cho field, argument, enum value hoặc mutation cũ:

**Giai đoạn 1 — Chuẩn bị**

- Xác định thành phần cần thay thế và lý do.
- Thiết kế contract mới, bảo đảm đáp ứng đủ nhu cầu client.
- Thêm resolver và test cho contract mới.

**Giai đoạn 2 — Phát hành song song**

- Deploy server có cả thành phần cũ và mới.
- Đánh dấu thành phần cũ bằng `@deprecated` với reason cụ thể.
- Cập nhật tài liệu, changelog và hướng dẫn migration.

**Giai đoạn 3 — Migration**

- Thông báo các client đang sử dụng thành phần cũ.
- Chuyển client sang contract mới.
- Theo dõi field usage, operation usage và lỗi sau migration.
- Giữ đường đi cũ hoạt động trong thời gian hỗ trợ đã cam kết.

**Giai đoạn 4 — Xác nhận removal**

- Usage đã về 0 hoặc chỉ còn client nằm ngoài chính sách hỗ trợ.
- Client quan trọng đã xác nhận migration.
- Schema checks và contract tests không còn phát hiện dependency.
- Có release note và kế hoạch rollback phù hợp.

**Giai đoạn 5 — Xóa thành phần cũ**

- Xóa field hoặc type deprecated trong một release đã công bố.
- Chạy schema diff, operation checks và integration tests.
- Theo dõi lỗi validation và phản hồi client sau khi phát hành.

Không đặt một thời gian deprecation cố định cho mọi API. Thời gian cần dựa vào tốc độ cập nhật client, cam kết hỗ trợ và mức độ ảnh hưởng.

## 21. Những lỗi thường gặp khi quản lý backward compatibility

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client cũ lỗi sau khi đổi tên field | Đổi tên trực tiếp trong SDL | Thêm field mới, giữ field cũ và deprecate |
| Query cũ không validate | Xóa argument hoặc thêm required argument | Giữ contract cũ; thêm query/mutation mới nếu cần |
| Client lỗi khi enum xuất hiện giá trị mới | Client xử lý enum exhaustive | Bổ sung fallback hoặc phối hợp cập nhật client |
| Response phát sinh null ngoài dự kiến | Thay đổi nullability hoặc resolver data | Giữ nullability cũ, kiểm tra dữ liệu và thêm field mới nếu cần |
| Query vẫn chạy nhưng kết quả đổi nghĩa | Thay đổi semantics mà không đổi schema | Xem semantics là contract; thêm field mới hoặc migration rõ ràng |
| Field deprecated bị xóa quá sớm | Chỉ dựa vào ngày phát hành field mới | Theo dõi usage và client version trước removal |
| Schema check pass nhưng client production lỗi | Operation telemetry không bao phủ client đó | Kết hợp registry, contract tests và client inventory |
| Subgraph build được nhưng supergraph lỗi | Không kiểm tra Federation composition | Chạy composition check trước publish |
| Metric/log không biết ai dùng field cũ | Không có client identity hoặc field usage tracking | Thu thập metadata client và field path phù hợp |
| Deprecation reason không giúp migration | Chỉ ghi “deprecated” | Nêu field thay thế, lý do và hướng dẫn |

## 22. Quy trình đánh giá một thay đổi API

Trước khi merge một schema change, hãy trả lời lần lượt:

1. Operation nào đang dùng field, type, argument hoặc enum value bị thay đổi?
2. Thay đổi có làm operation cũ mất khả năng validate không?
3. Thay đổi có làm nullability, response shape hoặc giá trị enum khác đi không?
4. Default value, sorting, pagination hoặc mutation side effect có đổi không?
5. Client code generation có thể bị ảnh hưởng bởi enum hoặc union member mới không?
6. Có thể thêm field/type mới và giữ contract cũ song song không?
7. Nếu cần deprecate, reason và replacement đã rõ chưa?
8. Có test operation cũ, operation mới và behavior quan trọng chưa?
9. Schema diff và operation usage checks đã chạy chưa?
10. Nếu dùng Federation, composition và client operations qua router đã được kiểm tra chưa?
11. Có telemetry để biết client nào còn dùng thành phần cũ không?
12. Điều kiện và thời điểm removal đã được công bố chưa?

Nếu chưa trả lời được câu hỏi về usage, không nên kết luận một thay đổi là an toàn chỉ dựa vào việc server build thành công.

## 23. Những điểm cần ghi nhớ

- Backward compatibility bao gồm schema, dữ liệu, hành vi runtime và vận hành.
- GraphQL thường tiến hóa bằng cách thêm field/type thay vì version hóa mỗi thay đổi.
- Thay đổi làm operation cũ mất khả năng validate là breaking change.
- Enum/union additions có thể là dangerous change với client xử lý exhaustive.
- Nullability, default values và semantics là một phần của contract.
- `@deprecated` giúp client nhận biết thành phần cũ nhưng không tự theo dõi usage.
- Thêm contract mới và giữ contract cũ hoạt động trong giai đoạn migration.
- Theo dõi operation/client usage trước khi xóa thành phần deprecated.
- Dùng `GraphQlTester` để giữ lại các operation cũ trong contract test.
- Đưa schema diff, operation checks và Federation composition vào CI/CD.
- Chỉ xóa thành phần cũ khi đã đáp ứng chính sách hỗ trợ và điều kiện migration.

Backward compatibility không chỉ là giữ cho schema compile được. Nó là cam kết rằng client đang được hỗ trợ có đủ thời gian và thông tin để chuyển đổi mà không bị gián đoạn. Thiết kế theo hướng additive, deprecate có lộ trình, theo dõi usage và kiểm thử operation thực tế sẽ giúp Spring for GraphQL API tiến hóa mà vẫn giữ được độ tin cậy với client hiện tại.

## Tài liệu tham khảo

- [GraphQL — Schema Design and Versioning](https://www.graphql.org/learn/schema-design/)
- [GraphQL — Schema Change Management](https://www.graphql.org/learn/governance-versioning/)
- [GraphQL — Schema Review and Breaking Changes](https://www.graphql.org/learn/schema-review/)
- [GraphQL Specification — Type System Evolution and Deprecation](https://spec.graphql.org/September2026/)
- [Apollo GraphQL — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [Apollo GraphQL — Schema Change Management](https://www.apollographql.com/docs/graphos/platform/production-readiness/change-management)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
