# Schema evolution với interface

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích interface là contract chung cho nhiều object type trong GraphQL.
- Đánh giá tác động khi thêm, đổi tên, xóa field hoặc thêm object type triển khai interface.
- Lập kế hoạch thay đổi schema theo hướng tương thích ngược.
- Dùng field deprecation, inline fragment và __typename để hỗ trợ client chuyển đổi.
- Kiểm thử interface và các concrete type trong Spring for GraphQL.

## Interface là contract chung

GraphQL interface mô tả tập field mà nhiều object type cùng cung cấp. Client có thể truy vấn một field trả về interface và chọn các field chung mà không cần biết trước object cụ thể nào sẽ được trả về.

Ví dụ, một ứng dụng nội dung có sách và bài viết. Cả hai đều có định danh và tiêu đề:

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
}

type Book implements SearchResult {
  id: ID!
  title: String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String!
  url: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

SearchResult là contract chung. Book và Article phải cung cấp các field id và title. Mỗi object type vẫn có thể có field riêng như isbn hoặc url.

Client có thể truy vấn field chung:

~~~graphql
query {
  search {
    id
    title
  }
}
~~~

Nếu cần dữ liệu riêng của từng loại, client dùng inline fragment:

~~~graphql
query {
  search {
    __typename
    id
    title
    ... on Book {
      isbn
    }
    ... on Article {
      url
    }
  }
}
~~~

__typename cho biết concrete object type của từng phần tử. Interface tạo ra một điểm truy cập ổn định cho dữ liệu chung, trong khi inline fragment cho phép client khai thác field đặc thù.

## Vì sao interface ảnh hưởng đến schema evolution?

Interface là contract được nhiều object type cùng thực hiện. Khi contract thay đổi, mọi object type triển khai interface đều phải tiếp tục đáp ứng contract mới.

Ví dụ, nếu thêm field publishedAt vào SearchResult, cả Book và Article phải có field tương ứng. Field này có thể nullable, nhưng vẫn phải được khai báo trên từng object type triển khai interface. Nullable chỉ có nghĩa giá trị trả về có thể là null; nó không làm cho việc khai báo field trở thành tùy chọn.

Điều này tạo ra hai khía cạnh khi tiến hóa schema:

- **Tương thích với client:** các operation hiện tại có còn hợp lệ và giữ nguyên ý nghĩa không?
- **Tương thích trong schema server:** tất cả object type, resolver và nguồn dữ liệu có đáp ứng contract mới không?

Một thay đổi có thể an toàn với client nhưng vẫn làm schema server không hợp lệ nếu object type triển khai interface chưa được cập nhật.

## Đánh giá các thay đổi thường gặp

| Thay đổi | Tác động tới client hiện tại | Tác động tới object type triển khai interface |
| --- | --- | --- |
| Thêm field nullable vào interface | Thường là additive với operation cũ | Tất cả implementor phải khai báo field mới |
| Thêm field non-null vào interface | Operation cũ vẫn có thể hợp lệ, nhưng dữ liệu mới phải luôn có giá trị | Tất cả implementor phải khai báo và bảo đảm trả giá trị non-null |
| Thêm argument nullable vào field interface | Client cũ có thể tiếp tục gọi mà không truyền argument | Mỗi field triển khai phải hỗ trợ argument tương ứng theo contract |
| Xóa hoặc đổi tên field interface | Breaking với client đang truy vấn field đó | Implementor và resolver phải được cập nhật |
| Đổi kiểu field interface | Có thể làm operation hoặc dữ liệu client không còn tương thích | Kiểu trả về của implementor phải thỏa quy tắc triển khai interface |
| Thêm object type mới triển khai interface | Có thể làm xuất hiện __typename mới ở runtime | Object type mới phải thực hiện đầy đủ field của interface |
| Xóa một implementor | Client có thể không còn nhận được một loại kết quả trước đây | Cần gỡ mapping và nguồn dữ liệu tương ứng |

Không nên chỉ nhìn vào việc schema diff được phân loại là additive hay breaking. Hãy xem cả cách client xử lý __typename, cách server phân giải kiểu runtime và các ràng buộc dữ liệu thực tế.

## Thêm field vào interface

Giả sử ứng dụng muốn mọi kết quả tìm kiếm có ngày tạo. Ta muốn bổ sung createdAt:

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
}
~~~

Sau khi bổ sung, mọi object type triển khai interface cần khai báo field:

~~~graphql
type Book implements SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
  url: String!
}
~~~

Trong ví dụ này createdAt nullable vì dữ liệu cũ có thể chưa lưu ngày tạo hoặc một nguồn dữ liệu chưa cung cấp thông tin đó. Resolver có thể trả về null cho bản ghi chưa có giá trị.

Nếu khai báo createdAt: DateTime!, mọi implementor phải trả về giá trị khác null cho mọi kết quả hợp lệ. Trước khi chọn non-null, hãy xác minh dữ liệu lịch sử, dữ liệu từ hệ thống tích hợp và tất cả đường thực thi resolver đều đáp ứng điều kiện.

### Triển khai theo từng giai đoạn

Với hệ thống có nhiều implementor hoặc nhiều nhóm phát triển, có thể triển khai field mới theo các bước:

1. Xác định toàn bộ object type đang triển khai interface và nơi cung cấp dữ liệu.
2. Thêm field mới vào từng object type cụ thể trước, đồng thời triển khai resolver hoặc property tương ứng.
3. Kiểm thử các concrete type, bao gồm cả bản ghi cũ có thể không có dữ liệu.
4. Sau khi các implementor đều sẵn sàng, thêm field vào interface để client có thể truy vấn trực tiếp trên kiểu trừu tượng.
5. Cập nhật client và theo dõi lỗi, dữ liệu null cùng mức sử dụng field mới.

Việc thêm field vào object type cụ thể trước cho phép client cần thiết có thể truy vấn field qua inline fragment. Khi interface được mở rộng, client có thể chuyển sang truy vấn field chung trên interface.

## Thêm argument vào field của interface

Interface có thể khai báo argument cho field. Ví dụ:

~~~graphql
interface SearchResult {
  id: ID!
  title(locale: String): String!
}
~~~

Các object type triển khai phải cung cấp field title với argument locale tương thích:

~~~graphql
type Book implements SearchResult {
  id: ID!
  title(locale: String): String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title(locale: String): String!
  url: String!
}
~~~

Khi thêm argument vào field interface, cần cập nhật các field triển khai tương ứng. Ưu tiên argument nullable hoặc có default để client cũ vẫn gọi được mà không cần truyền giá trị mới. Thêm argument non-null không có default sẽ buộc client cung cấp giá trị và có thể làm operation cũ không còn hợp lệ.

Các argument đã được interface công bố cần có tên và kiểu tương thích trên field triển khai. Object type có thể có argument bổ sung riêng, nhưng client truy vấn qua interface không thể sử dụng argument chỉ tồn tại trên một concrete type.

## Thêm object type mới triển khai interface

Một thay đổi thường gặp khác là thêm loại kết quả mới. Ví dụ, hệ thống bổ sung video:

~~~graphql
type Video implements SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
  durationSeconds: Int!
  playbackUrl: String!
}
~~~

Nếu query search bắt đầu trả về Video, client cũ vẫn có thể đọc các field chung id và title. Tuy nhiên, response có thể chứa __typename: "Video" mà client chưa từng biết.

Điều này đặc biệt quan trọng với client dùng code generation hoặc xử lý kết quả bằng exhaustive switch. Nếu client giả định chỉ có Book và Article, khi gặp Video có thể bỏ qua dữ liệu, hiển thị lỗi hoặc không xử lý được trạng thái giao diện.

Client nên có nhánh xử lý mặc định cho concrete type chưa biết:

~~~typescript
switch (result.__typename) {
  case "Book":
    return renderBook(result);
  case "Article":
    return renderArticle(result);
  default:
    return renderGenericSearchResult(result);
}
~~~

Đây là ví dụ phía client; nguyên tắc tương tự áp dụng cho bất kỳ ngôn ngữ nào có xử lý phân nhánh theo __typename. Trước khi đưa implementor mới vào kết quả production, hãy kiểm thử client hiện tại với một concrete type chưa được nhận diện.

Thêm implementor thường không làm operation GraphQL hiện tại mất hợp lệ, nhưng có thể thay đổi tập kết quả runtime. Vì vậy, hãy xem đây là một thay đổi có tác động hành vi và thông báo cho các nhóm sở hữu client.

## Đổi tên hoặc xóa field: dùng deprecation trước

Đổi tên hoặc xóa field interface ngay lập tức có thể làm hỏng mọi client đang truy vấn field đó. GraphQL cung cấp directive @deprecated để đánh dấu field cũ và thông báo cách thay thế:

~~~graphql
interface SearchResult {
  id: ID!
  title: String! @deprecated(reason: "Use displayTitle instead")
  displayTitle: String!
}
~~~

Các object type triển khai phải cung cấp cả field cũ lẫn field mới trong giai đoạn chuyển đổi:

~~~graphql
type Book implements SearchResult {
  id: ID!
  title: String! @deprecated(reason: "Use displayTitle instead")
  displayTitle: String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String! @deprecated(reason: "Use displayTitle instead")
  displayTitle: String!
  url: String!
}
~~~

Quy trình migration có thể thực hiện như sau:

1. Thêm field mới và triển khai nó trên tất cả implementor.
2. Giữ field cũ để client hiện tại tiếp tục hoạt động.
3. Đánh dấu field cũ bằng @deprecated cùng lý do và tên field thay thế.
4. Cập nhật client, tài liệu và ví dụ operation sang field mới.
5. Theo dõi telemetry hoặc log operation để xác định client còn sử dụng field cũ.
6. Chỉ xóa field cũ khi đã hoàn tất thời gian chuyển đổi và các client phụ thuộc đã được xử lý.

Deprecation là tín hiệu cho tooling và người phát triển, không tự chặn client truy vấn field cũ. Server vẫn cần theo dõi việc sử dụng và có kế hoạch loại bỏ rõ ràng.

## Thay đổi kiểu trả về và nullability

Kiểu trả về của field interface là một phần quan trọng của contract. Đổi từ String sang String!, từ String sang Int, hoặc từ object type sang một kiểu khác đều có thể ảnh hưởng đến client.

GraphQL cho phép kiểu trả về của field triển khai interface cụ thể hơn trong những trường hợp hợp lệ, ví dụ một interface trả về một interface/object trừu tượng và implementor trả về một object type cụ thể tương thích. Tuy nhiên, thay đổi kiểu trên chính interface vẫn có thể ảnh hưởng đến operation và response của mọi client truy vấn qua interface.

Nullability cần được xem xét cẩn thận:

- Nới lỏng từ non-null sang nullable có thể làm client đang giả định giá trị luôn có mặt phải xử lý thêm null.
- Siết chặt từ nullable sang non-null chỉ an toàn nếu server bảo đảm giá trị luôn có mặt; dữ liệu cũ hoặc resolver có thể làm GraphQL phát sinh lỗi và lan truyền null lên field cha.
- Thay đổi scalar hoặc cấu trúc object có thể buộc client thay đổi model và cách parse response.

Vì vậy, khi thay đổi kiểu hoặc nullability, thường nên thêm field mới, migrate client rồi deprecate field cũ thay vì sửa trực tiếp kiểu đang được sử dụng rộng rãi.

## Dùng interface mới khi contract chung thay đổi lớn

Nếu một nhóm field mới không phù hợp với contract hiện tại hoặc thay đổi có nguy cơ ảnh hưởng nhiều client, có thể giới thiệu interface mới và cho object type triển khai đồng thời cả hai interface.

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
}

interface DatedSearchResult {
  id: ID!
  title: String!
  createdAt: DateTime!
}

type Book implements SearchResult & DatedSearchResult {
  id: ID!
  title: String!
  createdAt: DateTime!
  isbn: String!
}

type Article implements SearchResult & DatedSearchResult {
  id: ID!
  title: String!
  createdAt: DateTime!
  url: String!
}

type Query {
  search: [SearchResult!]!
  datedSearch: [DatedSearchResult!]!
}
~~~

Client cũ tiếp tục dùng search và SearchResult. Client mới có thể dùng datedSearch để nhận contract bổ sung. Khi các client cũ đã chuyển đổi, nhóm có thể đánh giá việc deprecate API cũ.

Interface mới không phải lúc nào cũng cần thiết. Nó làm schema có thêm khái niệm và field cần duy trì. Chỉ dùng cách này khi hai contract thực sự có vòng đời hoặc yêu cầu tương thích khác nhau.

## Triển khai interface trong Spring for GraphQL

Ở tầng controller, một query có thể trả về danh sách các object thuộc nhiều concrete type:

~~~java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search() {
        return searchService.search();
    }
}
~~~

Trong ví dụ, SearchResult là kiểu Java phía domain hoặc abstraction mà các lớp Book và Article cùng triển khai. GraphQL runtime cần xác định concrete GraphQL object type cho từng kết quả để tạo __typename và phân giải inline fragment.

Nếu cơ chế type resolution mặc định không suy ra đúng GraphQL type từ object Java, hãy cấu hình TypeResolver qua RuntimeWiringConfigurer. Khi thêm implementor mới, cần cập nhật type resolution cùng resolver/service trả dữ liệu:

~~~java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return wiringBuilder -> wiringBuilder.type(
        TypeRuntimeWiring.newTypeWiring("SearchResult")
            .typeResolver(environment -> {
                Object source = environment.getObject();
                if (source instanceof Book) {
                    return environment.getSchema().getObjectType("Book");
                }
                if (source instanceof Article) {
                    return environment.getSchema().getObjectType("Article");
                }
                if (source instanceof Video) {
                    return environment.getSchema().getObjectType("Video");
                }
                throw new IllegalStateException(
                        "Unsupported SearchResult source: " + source.getClass().getName());
            })
    );
}
~~~

Đây là ví dụ minh họa cho việc ánh xạ kiểu Java sang GraphQL object type. Trong ứng dụng thực tế, nên xử lý trường hợp không nhận diện được source object bằng lỗi rõ ràng hoặc cơ chế fallback phù hợp, thay vì âm thầm trả về null. Tên và cách tổ chức domain class có thể khác schema, vì vậy cần kiểm thử type resolution với từng implementor.

Khi thay đổi interface, hãy xem xét đồng thời:

- SDL của interface và các object type triển khai.
- Resolver của field mới trên từng concrete type.
- Service và nguồn dữ liệu trả về các concrete object.
- Type resolver nếu ứng dụng cấu hình thủ công.
- Client query dùng field chung, inline fragment và __typename.

## Kiểm thử thay đổi interface

GraphQlTester giúp kiểm thử operation trên schema và xác minh kiểu cụ thể được trả về. Ví dụ:

~~~java
graphQlTester.document("""
        query {
            search {
                __typename
                id
                title
                ... on Book {
                    isbn
                }
                ... on Article {
                    url
                }
            }
        }
        """)
    .execute()
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
~~~

Khi thêm field vào interface, kiểm tra operation truy vấn field mới qua interface và xác minh tất cả implementor có kết quả đúng. Khi thêm concrete type, kiểm tra type resolution trả đúng __typename và inline fragment tương ứng hoạt động.

Một bộ kiểm thử schema evolution nên bao gồm:

1. Schema vẫn hợp lệ khi tất cả object type triển khai interface.
2. Field chung có kết quả hợp lệ trên từng concrete type.
3. Field nullable xử lý được dữ liệu cũ không có giá trị.
4. Field non-null không trả về null trong bất kỳ trường hợp hợp lệ nào.
5. Concrete type mới được nhận diện và trả đúng __typename.
6. Client query cũ vẫn thực thi sau thay đổi additive.
7. Field deprecated vẫn hoạt động trong giai đoạn migration.
8. Type resolver báo lỗi rõ ràng khi gặp source object không được hỗ trợ.

Ngoài test ở cấp GraphQL, nên dùng schema diff hoặc schema compatibility check trong CI để phát hiện field bị xóa, đổi kiểu, đổi nullability hoặc thay đổi tập possible types ngoài dự kiến. Kiểm tra schema tĩnh không thay thế integration test vì nó không xác minh dữ liệu thực và hành vi resolver.

## Quy trình tiến hóa interface an toàn

Khi lên kế hoạch thay đổi interface, có thể áp dụng trình tự sau:

~~~mermaid
flowchart TD
    A[Xác định mục tiêu thay đổi] --> B[Liệt kê implementor và client]
    B --> C[Phân loại tác động schema và runtime]
    C --> D[Thiết kế thay đổi additive hoặc interface mới]
    D --> E[Cập nhật SDL, resolver và type resolution]
    E --> F[Kiểm thử từng concrete type và client cũ]
    F --> G[Triển khai và theo dõi telemetry]
    G --> H[Deprecate field cũ nếu có]
    H --> I[Loại bỏ sau khi client đã migrate]
~~~

Trước khi triển khai, hãy ghi lại:

- Những object type nào đang triển khai interface.
- Các client nào truy vấn field chung hoặc dựa vào __typename.
- Field mới có dữ liệu đầy đủ trong mọi nguồn hay không.
- Thay đổi có cần resolver, type resolver hoặc migration dữ liệu không.
- Điều kiện và thời điểm có thể xóa field deprecated.

Đối với thay đổi ảnh hưởng nhiều nhóm, nên công bố schema change và thời gian chuyển đổi. Việc này giúp client có thời gian cập nhật code generation, cache, model và xử lý concrete type mới.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Schema không khởi động sau khi thêm field interface | Một hoặc nhiều object type chưa khai báo field bắt buộc của interface | Cập nhật tất cả implementor và kiểm tra schema validation |
| Field mới luôn trả null | Resolver hoặc dữ liệu của concrete type chưa được cập nhật | Kiểm tra resolver, property và dữ liệu lịch sử |
| GraphQL báo lỗi non-null | Một implementor trả null cho field non-null | Xem lại dữ liệu và chọn nullable nếu contract cho phép |
| Client không xử lý được kết quả mới | Có implementor mới và __typename chưa được client nhận diện | Thêm fallback branch và cập nhật client |
| Inline fragment không chạy | Type resolution trả sai concrete type | Kiểm tra TypeResolver và mapping domain object |
| Client cũ lỗi sau khi đổi field | Field cũ bị xóa hoặc đổi kiểu quá sớm | Khôi phục field, thêm field thay thế và dùng deprecation |
| Schema diff báo thay đổi bất ngờ | Field hoặc nullability của interface/implementor bị chỉnh ngoài dự kiến | Đưa schema compatibility check vào CI |

## Thực hành tổng hợp

Với schema SearchResult gồm Book và Article, hãy thực hiện các thay đổi:

1. Thêm field nullable createdAt: DateTime vào từng object type trước.
2. Bổ sung resolver hoặc dữ liệu createdAt cho Book và Article.
3. Thêm createdAt vào interface và kiểm thử query chỉ truy vấn qua SearchResult.
4. Thêm object type Video triển khai SearchResult; cập nhật service và type resolution nếu cần.
5. Kiểm thử __typename, inline fragment và nhánh fallback phía client.
6. Thêm field displayTitle, đánh dấu title deprecated và cập nhật client sang field mới.
7. Viết schema compatibility check để bảo đảm không vô tình xóa field cũ trước khi hoàn tất migration.

Sau bài thực hành, hãy giải thích thay đổi nào chỉ bổ sung khả năng cho client, thay đổi nào có thể làm thay đổi kết quả runtime và thay đổi nào buộc mọi implementor phải cập nhật.

## Ghi nhớ

Interface là contract chung của nhiều object type. Mọi object type triển khai phải cung cấp các field được khai báo trên interface, kể cả field nullable. Vì vậy, thêm field vào interface cần cập nhật toàn bộ implementor; thêm object type mới có thể thay đổi các giá trị __typename mà client nhận được. Hãy ưu tiên thay đổi additive, dùng inline fragment cho field riêng, thêm field mới trước khi deprecate field cũ và chỉ xóa sau khi client đã chuyển đổi. Trong Spring for GraphQL, kiểm tra cả resolver, type resolution và từng concrete type bằng GraphQlTester cùng schema compatibility check.
