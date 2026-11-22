# Namespacing query

## 1. Vì sao cần tổ chức namespace cho Query?

Khi GraphQL API còn nhỏ, root type `Query` thường có một số field đơn giản:

```graphql
type Query {
    book(id: ID!): Book
    books(first: Int): [Book!]!
    author(id: ID!): Author
    authors(first: Int): [Author!]!
    account(id: ID!): Account
    invoices(first: Int): [Invoice!]!
}
```

Khi hệ thống lớn dần, nhiều domain cùng bổ sung field vào `Query`. Root type trở thành một danh sách dài, tên field dễ va chạm, khó phân chia quyền sở hữu và khó giúp người dùng khám phá API.

Namespacing query là cách nhóm các field theo domain hoặc chức năng bằng những object type trung gian. Client vẫn gửi một GraphQL operation đến cùng endpoint, nhưng đường dẫn field trong query thể hiện rõ nhóm nghiệp vụ mà dữ liệu thuộc về.

Ví dụ:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
    billing: BillingQueries!
}
```

Thay vì đặt tất cả field ở cùng cấp, schema tạo các nhóm `catalog`, `accounts` và `billing`.

## 2. Namespacing không phải cú pháp đặc biệt của GraphQL

GraphQL Specification không định nghĩa một từ khóa `namespace` hoặc cơ chế namespace riêng cho Query. Đây là một pattern thiết kế schema dựa trên object type và field thông thường.

Cần phân biệt namespacing schema với những khái niệm dễ nhầm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Query namespace | `catalog { books { id } }` | Nhóm field trong schema theo object type |
| Operation name | `query CatalogPage { ... }` | Tên của operation do client đặt |
| Alias | `recent: books(first: 5)` | Đổi key trong response của một lần gọi |
| Fragment | `...BookFields` | Tái sử dụng selection set |
| HTTP path | `/graphql` | Endpoint nhận GraphQL request |

Operation name, alias và fragment không tạo namespace cho schema. Namespacing được định nghĩa trong SDL và là một phần của public API contract.

## 3. Một Query root và nhiều nhóm object

Mỗi GraphQL schema có đúng một root type cho Query. Theo quy ước, type này tên là `Query`; schema có thể khai báo một tên root khác bằng schema definition, nhưng vẫn chỉ có một query root. Ví dụ `schema { query: RootQuery }` đổi tên root type, không tạo thêm một namespace độc lập.

Namespacing không tạo thêm nhiều Query root. Nó tạo field trên Query root, mỗi field trả về một object type đại diện cho một nhóm truy vấn.

Ví dụ SDL đầy đủ:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
    billing: BillingQueries!
}

type CatalogQueries {
    book(id: ID!): Book
    books(genre: String, first: Int = 20): [Book!]!
}

type AccountQueries {
    me: Account
    account(id: ID!): Account
}

type BillingQueries {
    invoice(id: ID!): Invoice
    invoices(first: Int = 20): [Invoice!]!
}

type Book {
    id: ID!
    title: String!
}

type Account {
    id: ID!
    displayName: String!
}

type Invoice {
    id: ID!
    total: Int!
}
```

`CatalogQueries`, `AccountQueries` và `BillingQueries` là object type thông thường. Chúng không phải service, module hay database riêng. Mục đích chính là tạo một cấu trúc field dễ khám phá và dễ quản lý.

Field name chỉ cần duy nhất trong object type chứa field đó. Vì vậy `CatalogQueries.book` và `AccountQueries.book` có thể cùng tên mà không xung đột; schema coordinates của chúng khác nhau. Ngược lại, tất cả field khai báo trực tiếp trên `Query` vẫn dùng chung một không gian tên.

## 4. Client truy vấn các namespace

Client có thể chọn một hoặc nhiều nhóm trong cùng operation:

```graphql
query Dashboard {
    catalog {
        books(genre: "SCIENCE", first: 5) {
            id
            title
        }
    }
    accounts {
        me {
            id
            displayName
        }
    }
    billing {
        invoices(first: 3) {
            id
            total
        }
    }
}
```

GraphQL server vẫn thực thi một operation trên một schema. Các namespace chỉ là những nhánh field trong selection set. Client không cần gửi request riêng đến `/catalog`, `/accounts` hoặc `/billing`.

GraphQL cho phép client chọn field cần thiết trong mỗi nhóm, nên một màn hình có thể kết hợp dữ liệu từ nhiều domain mà không phải tải toàn bộ object namespace.

## 5. Triển khai namespace root bằng Spring for GraphQL

Field `Query.catalog` cần trả về một object làm source cho các field con. Nếu namespace chỉ dùng để nhóm truy vấn, object này có thể là một marker object không chứa dữ liệu nghiệp vụ.

Khai báo Java type:

```java
public record CatalogQueries() {
}
```

Resolver cho field root:

```java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CatalogNamespaceController {

    @QueryMapping
    public CatalogQueries catalog() {
        return new CatalogQueries();
    }
}
```

`@QueryMapping` mặc định ánh xạ method vào field cùng tên trên root type `Query`. Method `catalog()` không cần gọi database vì nó chỉ tạo điểm bắt đầu cho nhánh `CatalogQueries`.

Nếu dùng namespace non-null (`catalog: CatalogQueries!`), resolver phải luôn trả về object không null. Nếu resolver trả null, GraphQL sẽ phát sinh lỗi và áp dụng null propagation theo schema.

## 6. Ánh xạ field con bằng `@SchemaMapping`

Các field trong `CatalogQueries` được xử lý như field của một object type thông thường. Spring for GraphQL dùng `@SchemaMapping` để ánh xạ chúng:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CatalogQueriesController {

    private final BookService bookService;

    public CatalogQueriesController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping(typeName = "CatalogQueries", field = "books")
    public List<BookView> books(
            CatalogQueries source,
            @Argument("genre") String genre,
            @Argument("first") Integer first) {

        return bookService.findBooks(genre, first);
    }

    @SchemaMapping(typeName = "CatalogQueries", field = "book")
    public BookView book(
            CatalogQueries source,
            @Argument("id") String id) {

        return bookService.findBook(id);
    }
}
```

Spring truyền parent object `CatalogQueries` vào tham số source. Các tham số `@Argument` lấy giá trị từ arguments của field con. `BookService` là service nghiệp vụ của ứng dụng.

Tên `typeName` phải khớp tên object type trong SDL. Nếu method có tên trùng field, có thể bỏ `field` và chỉ khai báo `@SchemaMapping(typeName = "CatalogQueries")`.

## 7. Tách controller theo namespace

Khi mỗi domain có nhiều query, có thể tách controller theo nhóm để code dễ điều hướng:

```text
graphql/
├── namespace/
│   ├── CatalogNamespaceController.java
│   ├── AccountNamespaceController.java
│   └── BillingNamespaceController.java
├── catalog/
│   └── CatalogQueriesController.java
├── account/
│   └── AccountQueriesController.java
└── billing/
    └── BillingQueriesController.java
```

Controller namespace chỉ giải quyết field root như `catalog`, `accounts`, `billing`. Controller domain giải quyết các field con thuộc object type tương ứng.

Không bắt buộc mỗi namespace phải có một controller riêng. Có thể gom các mapping nhỏ vào một controller nếu chúng cùng trách nhiệm và dễ bảo trì. Điều quan trọng là mapping phải rõ `typeName` để tránh hai method vô tình đăng ký cùng một schema coordinate.

## 8. Pattern namespace so với prefix field

Namespacing bằng object type không phải lựa chọn duy nhất. Một API có thể giữ Query phẳng nhưng đặt prefix domain cho từng field:

```graphql
type Query {
    catalogBook(id: ID!): Book
    catalogBooks(genre: String, first: Int): [Book!]!
    accountMe: Account
    accountById(id: ID!): Account
    billingInvoice(id: ID!): Invoice
    billingInvoices(first: Int): [Invoice!]!
}
```

So sánh:

| Tiêu chí | Object namespace | Prefix field |
| --- | --- | --- |
| Cấu trúc query | Có thêm một cấp lồng nhau | Phẳng ở Query root |
| Tên field | Có thể dùng tên ngắn trong từng object type | Cần tên duy nhất trên Query root |
| Khả năng khám phá | Client duyệt theo nhóm domain | Client tìm qua prefix hoặc schema docs |
| Resolver Spring | Root dùng `@QueryMapping`, field con dùng `@SchemaMapping` | Các field dùng `@QueryMapping` |
| Độ sâu query | Tăng thêm một cấp | Không tăng cấp namespace |
| Phù hợp | API lớn, domain rõ, nhiều field liên quan | API nhỏ hoặc muốn giữ query root phẳng |

Chọn pattern dựa trên kích thước schema, cách client khám phá API và nhu cầu quản lý domain. Không nên thêm namespace chỉ để làm tên field ngắn hơn nếu đổi lại query trở nên sâu và khó đọc.

## 9. Khi nào nên tạo namespace?

Một namespace có giá trị khi các field bên trong có quan hệ nghiệp vụ rõ ràng. Ví dụ `catalog` chứa `book`, `books`, `categories`; `accounts` chứa `me`, `account`, `preferences`; `billing` chứa `invoice`, `invoices`, `paymentMethods`.

Một số tiêu chí thực tế:

- Có nhiều field cùng thuộc một domain hoặc bounded context.
- Tên field ở root bắt đầu trùng lặp do nhiều domain cùng dùng các từ như `list`, `search`, `detail`.
- Client thường truy vấn nhiều field trong cùng một nhóm.
- Một nhóm có thể phát triển độc lập và có người chịu trách nhiệm schema rõ ràng.
- Cần giảm sự lộn xộn của root type khi API lớn dần.

Nếu Query chỉ có vài field đơn giản, root phẳng thường dễ dùng hơn. Namespace không phải mục tiêu tự thân; nó phải làm schema dễ hiểu hơn.

## 10. Chọn tên namespace và type nhất quán

Tên namespace là một phần của API công khai, nên cần ổn định và mô tả domain. Thường dùng danh từ hoặc tên domain ở field root:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
    billing: BillingQueries!
}
```

Một số quy tắc:

- Field namespace nên là danh từ/domain, không phải động từ như `getCatalog`.
- Dùng tên số nhiều hoặc tên nhóm khi namespace chứa nhiều query, ví dụ `catalog`, `accounts`, `billing`.
- Type namespace nên có hậu tố dễ nhận diện như `CatalogQueries` hoặc `CatalogQuery` và thống nhất trong toàn schema.
- Tránh tên chung chung như `data`, `common`, `misc`, `manager`.
- Tránh đưa tên database, tên repository hoặc tên microservice vào public schema nếu đó không phải khái niệm nghiệp vụ ổn định.
- Không đổi namespace chỉ vì package Java hoặc team nội bộ được đổi tên.

Tên field GraphQL phân biệt chữ hoa/chữ thường. Hãy chọn convention nhất quán, thường là `camelCase` cho field và `PascalCase` cho object type.

## 11. Đặt argument ở field thực sự sử dụng chúng

Arguments nên được khai báo tại field cần lọc, phân trang hoặc định danh dữ liệu. Không đặt tất cả arguments ở namespace root nếu chúng chỉ áp dụng cho một query con.

```graphql
type CatalogQueries {
    book(id: ID!): Book
    books(
        genre: String
        first: Int = 20
        after: String
        sort: BookSort = TITLE_ASC
    ): BookConnection!
}

enum BookSort {
    TITLE_ASC
    TITLE_DESC
    PUBLISHED_AT_DESC
}
```

Trong ví dụ này, `id` chỉ có ý nghĩa với `book`; `genre`, `first`, `after` và `sort` chỉ có ý nghĩa với `books`.

Khi API có nhiều field cần chung một nhóm input, có thể tạo `input` type riêng để tái sử dụng. Không tạo một input object khổng lồ chỉ để gom các argument không liên quan.

## 12. Phân trang và giới hạn truy vấn trong namespace

Namespacing không làm thay đổi semantics của pagination. Field trả danh sách vẫn cần giới hạn số phần tử và có cursor/page strategy rõ ràng.

Ví dụ connection:

```graphql
type CatalogQueries {
    books(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
}

type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}
```

Đặt default limit hợp lý, giới hạn `first` tối đa ở resolver/service và kiểm tra cursor. Namespace không bảo vệ server khỏi query lấy quá nhiều dữ liệu.

## 13. Namespace không phải ranh giới bảo mật

Không nên giả định rằng field nằm dưới `catalog` thì mọi field con đều có cùng quyền truy cập. Một query có thể kết hợp nhiều namespace và mỗi field có thể có chính sách riêng.

Ví dụ:

- `catalog.books` có thể công khai.
- `accounts.me` yêu cầu người dùng đã xác thực.
- `accounts.account(id)` có thể chỉ cho phép người dùng xem account của chính họ hoặc có quyền quản trị.
- `billing.invoices` có thể yêu cầu scope tài chính.

Hãy kiểm tra quyền tại resolver/service sở hữu dữ liệu, dùng Spring Security method security hoặc cơ chế authorization hiện có. Việc đặt field trong cùng object namespace chỉ là tổ chức schema, không tự tạo authorization boundary.

Nếu cần kiểm soát quyền ở cấp field, hãy bảo đảm các mapping và service kiểm tra cả tenant, owner và scope. Không tin ID do client gửi chỉ vì nó nằm dưới namespace đã xác thực.

## 14. DataLoader và N+1 vẫn áp dụng bình thường

Namespace không thay đổi cách GraphQL resolve các field con. Nếu `catalog.books` trả về nhiều `Book`, các field tiếp theo như `Book.author` vẫn có thể gây N+1.

Có thể dùng `@BatchMapping` như thông thường:

```java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<BookView, AuthorView> author(List<BookView> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
```

Batch mapping gom việc tải author cho nhiều Book trong cùng execution. Có thể dùng `BatchLoaderRegistry` và DataLoader nếu cần kiểm soát cache/request scope hoặc cách batch chi tiết hơn.

## 15. Xử lý lỗi ở field con

Lỗi phát sinh từ `catalog.books` hoặc `billing.invoices` vẫn là lỗi GraphQL tại field tương ứng. Namespace không tạo một error boundary mới.

Response có thể chứa dữ liệu từ namespace khác cùng với error path cụ thể. Để minh họa trường hợp `books` có thể null, schema cần khai báo field này nullable:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
}

type CatalogQueries {
    books(first: Int): [Book!]
}

type Book {
    id: ID!
}

type AccountQueries {
    me: Account
}

type Account {
    id: ID!
    displayName: String!
}
```

Khi đó response có thể giữ namespace và các nhánh dữ liệu độc lập:

```json
{
  "data": {
    "catalog": {
      "books": null
    },
    "accounts": {
      "me": {
        "id": "user-1",
        "displayName": "An"
      }
    }
  },
  "errors": [
    {
      "message": "Unable to load books",
      "path": ["catalog", "books"]
    }
  ]
}
```

Hãy chọn nullability phù hợp. Nếu `books` được khai báo `[Book!]!`, lỗi ở field có thể lan lên namespace hoặc root theo quy tắc non-null propagation. Không khai báo non-null chỉ vì muốn response trông gọn; hãy xác định dữ liệu có thực sự luôn tồn tại hay không.

## 16. Namespacing Query không đồng nghĩa namespacing Mutation

Có thể tạo object grouping cho Mutation về mặt cú pháp, nhưng cần cẩn trọng với semantics thực thi. GraphQL thực thi các field trực tiếp trên mutation root theo thứ tự tuần tự. Các field lồng bên trong object mà mutation root trả về không tự động có semantics tuần tự đó.

Ví dụ sau không nên dùng để gom các side effect thành những mutation con:

```graphql
type Mutation {
    catalog: CatalogMutations!
}

type CatalogMutations {
    createBook(input: CreateBookInput!): Book!
    deleteBook(id: ID!): Boolean!
}
```

`catalog` là field mutation root duy nhất. `createBook` và `deleteBook` là field lồng, không phải root mutation field. Nếu client chọn cả hai, không nên dựa vào semantics tuần tự của mutation root để bảo đảm thứ tự side effect giữa chúng.

Đối với command có side effect, thường nên giữ các field trực tiếp trên `Mutation` và dùng prefix domain:

```graphql
type Mutation {
    catalogCreateBook(input: CreateBookInput!): Book!
    catalogDeleteBook(id: ID!): Boolean!
    billingPayInvoice(id: ID!): PaymentResult!
}
```

Như vậy các mutation root field vẫn được thực thi tuần tự theo GraphQL semantics. Chỉ dùng nested mutation namespace khi hiểu rõ hệ quả và không phụ thuộc vào thứ tự tuần tự giữa các field con.

## 17. Namespacing và query depth/complexity

Object namespace thêm một cấp vào đường dẫn field. Ví dụ `books { id }` trở thành `catalog { books { id } }`. Điều này làm tăng query depth tối thiểu và có thể tác động đến các query depth/complexity limit đang dùng.

Khi chuyển một API lớn sang namespace:

- Kiểm tra cấu hình `MaxQueryDepthInstrumentation` hoặc query depth limit hiện tại.
- Kiểm tra complexity calculator nếu có tính phí theo cấp field.
- Kiểm tra persisted query hoặc allowlist vì query document đã thay đổi.
- Kiểm tra client query generator và cache key dựa trên document.
- Đo latency và kích thước response trước/sau thay đổi.

Thêm một cấp namespace thường không tạo thêm database round-trip nếu root resolver chỉ trả marker object. Tuy vậy, nó vẫn thêm field resolution và một cấp nesting trong execution tree.

## 18. Tiến hóa từ Query phẳng sang namespaced Query

Không nên xóa field root cũ ngay khi thêm namespace mới. Có thể triển khai theo các bước:

1. Giữ field cũ và thêm namespace mới vào SDL.
2. Ánh xạ field cũ và field mới đến cùng service nghiệp vụ để bảo đảm semantics nhất quán.
3. Viết contract test cho cả hai đường truy vấn.
4. Đánh dấu field cũ bằng `@deprecated` và cung cấp lý do cùng đường thay thế.
5. Theo dõi usage theo schema coordinate/client để biết khi nào có thể loại bỏ.
6. Thông báo thời hạn migration và chỉ xóa field cũ trong một thay đổi breaking có kế hoạch.

Ví dụ:

```graphql
type Query {
    books(first: Int): [Book!]!
        @deprecated(reason: "Use catalog { books(first: ...) }.")
    catalog: CatalogQueries!
}

type CatalogQueries {
    books(first: Int): [Book!]!
}
```

Trong Spring for GraphQL, hai mapping có thể gọi cùng `BookService`:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<BookView> books(@Argument("first") Integer first) {
        return bookService.findBooks(first);
    }

    @SchemaMapping(typeName = "CatalogQueries", field = "books")
    public List<BookView> catalogBooks(
            CatalogQueries source,
            @Argument("first") Integer first) {
        return bookService.findBooks(first);
    }
}
```

`@deprecated` giúp client và tooling nhận biết field cũ, nhưng không tự động chuyển query cũ sang field mới. Client vẫn cần thay selection path từ `books` thành `catalog { books }`.

## 19. Alias không thay thế migration schema

GraphQL alias có thể đổi response key trong một query:

```graphql
query {
    catalogBooks: catalog {
        books(first: 5) {
            id
            title
        }
    }
}
```

Alias `catalogBooks` chỉ tồn tại trong operation này. Nó không tạo field `catalogBooks` trong schema và không giúp client khác khám phá tên đó qua introspection.

Nếu muốn giữ API cũ trong thời gian migration, phải giữ field cũ trong SDL và resolver tương ứng. Alias chỉ hữu ích khi client muốn đặt tên response key, chẳng hạn khi cùng query một field với arguments khác nhau.

## 20. Kiểm thử namespaced Query với GraphQlTester

Nên kiểm thử query qua public GraphQL API thay vì chỉ gọi Java resolver trực tiếp. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.test.tester.GraphQlTester;

class CatalogNamespaceTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void readsBooksThroughCatalogNamespace() {
        graphQlTester.document("""
                query CatalogBooks {
                    catalog {
                        books(first: 2) {
                            id
                            title
                        }
                    }
                }
                """)
                .execute()
                .path("catalog.books")
                .entityList(BookView.class)
                .hasSize(2);
    }
}
```

Ví dụ trên giả định test context đã cung cấp `GraphQlTester`, chẳng hạn qua `@GraphQlTest` hoặc cấu hình tester phù hợp với transport đang kiểm thử. Với HTTP thật, có thể dùng `HttpGraphQlTester` để kiểm tra endpoint qua HTTP.

Ngoài response, nên kiểm thử:

- Namespace root không null và đúng schema type.
- Arguments được truyền đến đúng field con.
- Authorization được kiểm tra riêng theo field.
- Pagination limit được áp dụng.
- Field con dùng DataLoader hoặc batch mapping khi cần.
- Error path có đúng namespace và field name.
- Field phẳng cũ và field namespaced mới trả dữ liệu tương thích trong giai đoạn migration.
- Schema introspection hiển thị đúng field và deprecation reason.

## 21. Lỗi thiết kế thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo namespace cho mọi nhóm nhỏ | Query dài và sâu không cần thiết | Chỉ nhóm khi có domain/field liên quan |
| Dùng tên `common`, `data`, `misc` | Client không hiểu ý nghĩa nhóm | Dùng tên domain hoặc capability rõ ràng |
| Nghĩ namespace là authorization boundary | Field nhạy cảm có thể bị truy cập sai quyền | Kiểm tra quyền tại resolver/service sở hữu dữ liệu |
| Root resolver gọi backend chỉ để tạo namespace | Tốn một round-trip không cần thiết | Trả marker object nếu namespace không chứa dữ liệu |
| Dùng `@QueryMapping` cho field con | Mapping không khớp root Query | Dùng `@SchemaMapping` với `typeName` của namespace |
| Lồng mutation có side effect | Mất bảo đảm tuần tự giữa các mutation con | Giữ command ở mutation root và dùng prefix domain |
| Quên tăng query depth limit | Query hợp lệ bị từ chối sau khi thêm namespace | Đánh giá lại depth/complexity limit |
| Xóa field cũ ngay khi thêm namespace | Client cũ bị breaking change | Deprecate, theo dõi usage rồi mới loại bỏ |
| Dùng alias như field thay thế | Schema không có field mới, tooling không thấy | Thêm field mới trong SDL và resolver |
| Namespace type name trùng hoặc thiếu nhất quán | Schema khó đọc và dễ xung đột | Đặt tên type riêng, thống nhất convention |

## 22. Checklist thiết kế namespaced Query

- [ ] Giữ một Query root và tạo object type cho từng namespace cần thiết.
- [ ] Chọn tên field namespace theo domain hoặc capability.
- [ ] Đặt tên type namespace nhất quán, dễ nhận diện.
- [ ] Chỉ nhóm các field có quan hệ nghiệp vụ rõ ràng.
- [ ] Đặt arguments tại field thực sự sử dụng chúng.
- [ ] Dùng `@QueryMapping` cho field root namespace.
- [ ] Dùng `@SchemaMapping` cho field con của namespace.
- [ ] Trả marker object nếu namespace chỉ có nhiệm vụ nhóm query.
- [ ] Giữ authorization ở resolver/service và kiểm tra tenant/owner/scope.
- [ ] Giữ pagination, DataLoader và error handling cho các field con.
- [ ] Kiểm tra query depth/complexity sau khi thêm một cấp lồng nhau.
- [ ] Không áp dụng máy móc object namespace cho mutation có side effect.
- [ ] Dùng `@deprecated` và theo dõi usage khi thay thế field cũ.
- [ ] Kiểm thử response, error path, security và migration bằng `GraphQlTester`.

## Kết luận

Namespacing query là pattern tổ chức root `Query` bằng các object type trung gian như `CatalogQueries`, `AccountQueries` và `BillingQueries`. Nó giúp nhóm field theo domain, giảm sự lộn xộn của root type và làm query của client dễ khám phá hơn. Đây không phải cú pháp namespace đặc biệt của GraphQL và cũng không tạo thêm Query root hay endpoint mới.

Trong Spring for GraphQL, resolver của namespace root thường dùng `@QueryMapping` và trả về một marker object; các field con dùng `@SchemaMapping` với `typeName` tương ứng. Các cơ chế arguments, authorization, DataLoader, pagination và error handling vẫn hoạt động theo semantics GraphQL thông thường. Chỉ nên dùng namespace khi nó làm schema rõ hơn; cần cân nhắc query depth, migration từ field phẳng và đặc biệt không giả định nested mutation có semantics tuần tự như mutation root.

## Tài liệu tham khảo

- [GraphQL Specification — Root Operation Types](https://spec.graphql.org/September2025/#sec-Root-Operation-Types)
- [GraphQL Specification — Objects and Fields](https://spec.graphql.org/September2025/#sec-Objects)
- [GraphQL Specification — Executing Mutations](https://spec.graphql.org/September2025/#sec-Normal-and-Serial-Execution)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL — Schema and Type System](https://graphql.org/learn/schema/)
