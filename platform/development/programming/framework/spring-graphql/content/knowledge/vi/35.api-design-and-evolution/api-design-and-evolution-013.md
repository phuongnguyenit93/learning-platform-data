# Tránh schema quá rộng trong GraphQL

GraphQL cho phép client chọn nhiều field và đi sâu qua các quan hệ trong một request. Tính linh hoạt này dễ dẫn tới schema có quá nhiều field, type dùng chung cho mọi nghiệp vụ, input chứa hàng chục filter và quan hệ lồng nhau không giới hạn. Kết quả là API khó hiểu, khó bảo mật, khó tối ưu và khó thay đổi mà không ảnh hưởng client.

Tránh schema quá rộng không có nghĩa là giới hạn số field bằng một con số cứng. Mục tiêu là giữ API surface vừa đủ cho use case thực tế, phản ánh ranh giới nghiệp vụ rõ ràng và cung cấp dữ liệu theo nhu cầu có kiểm soát. Với Spring for GraphQL, việc thiết kế bắt đầu ở SDL; controller, service, DataLoader và security phải thực hiện đúng ý nghĩa của schema.

## Dấu hiệu schema đang quá rộng

Một schema có thể đã quá rộng khi xuất hiện nhiều dấu hiệu sau:

- Một object type chứa field của nhiều vai trò hoặc bounded context, dù các client khác nhau chỉ cần những phần dữ liệu khác nhau.
- Root `Query` và `Mutation` có nhiều field tổng quát như `getEntity`, `search`, `update`, nhận tên type hoặc JSON để quyết định hành vi lúc runtime.
- Một input object gom filter của nhiều màn hình hoặc nghiệp vụ, với phần lớn field chỉ có ý nghĩa trong một số request.
- Quan hệ trả về list không phân trang, hoặc cho phép client duyệt sâu qua nhiều lớp quan hệ mà không có giới hạn.
- Có nhiều field trùng nghĩa, khác tên nhẹ hoặc chỉ phục vụ một client cũ mà không còn được sử dụng.
- Schema public để lộ field nội bộ, dữ liệu nhạy cảm hoặc hành động mà caller không nên truy cập.
- Resolver phải có nhiều nhánh theo role, tenant, trạng thái hoặc tên field vì một type đang gánh quá nhiều trách nhiệm.
- Mỗi thay đổi nghiệp vụ đều buộc sửa một type lớn và có nguy cơ làm hỏng nhiều client không liên quan.

Đếm số field không đủ để kết luận schema rộng. Một type có nhiều field nhưng cùng thuộc một khái niệm ổn định có thể vẫn hợp lý. Ngược lại, một type nhỏ nhưng gom nhiều hành vi không liên quan vào một mutation tổng quát cũng là thiết kế khó bảo trì.

## Bắt đầu từ use case và bounded context

Thiết kế GraphQL schema từ câu hỏi client cần giải quyết, không bắt đầu bằng cách sao chép toàn bộ bảng database thành type. Một bảng có thể chứa cột phục vụ vận hành, audit, billing và support; không có nghĩa tất cả cột đó đều là field public của một GraphQL object.

Ví dụ, hệ thống bán sách có các use case khác nhau:

| Use case | Dữ liệu client cần |
| --- | --- |
| Trang danh mục | Tiêu đề, ảnh bìa, giá hiển thị, tác giả, trạng thái còn hàng. |
| Trang chi tiết sách | Mô tả, nhà xuất bản, thể loại, đánh giá và thông tin phát hành. |
| Quản lý đơn hàng | Trạng thái đơn, dòng hàng, tổng tiền và lịch sử giao hàng. |
| Vận hành kho | SKU, vị trí kho, số lượng khả dụng và thông tin nhập hàng. |

Không cần đưa mọi dữ liệu này vào một `Book` type duy nhất. Có thể tạo các type đại diện cho khái niệm và quyền sở hữu rõ ràng, hoặc field riêng trên type với authorization thích hợp. Quyết định phụ thuộc vào việc các field có cùng ý nghĩa nghiệp vụ và vòng đời hay không.

## Tránh một object type gánh mọi trách nhiệm

Ví dụ thiết kế quá rộng:

```graphql
type Customer {
  id: ID!
  name: String!
  email: String
  phone: String
  passwordHash: String
  roles: [String!]!
  internalNotes: String
  invoices: [Invoice!]!
  supportTickets: [SupportTicket!]!
  riskScore: Float
  creditLimit: Float
  warehouseAssignments: [Warehouse!]!
  auditEvents: [AuditEvent!]!
}
```

Type này trộn dữ liệu hồ sơ, xác thực, billing, support, risk, warehouse và audit. Nó tạo ra contract khó bảo vệ và có thể làm query tải nhiều quan hệ nặng.

Thiết kế rõ trách nhiệm hơn:

```graphql
type CustomerSummary {
  id: ID!
  displayName: String!
}

type CustomerProfile {
  id: ID!
  displayName: String!
  contact: CustomerContact
}

type CustomerContact {
  email: String
  phone: String
}

type Invoice {
  id: ID!
  number: String!
  total: Money!
  status: InvoiceStatus!
}

type SupportTicket {
  id: ID!
  subject: String!
  status: TicketStatus!
}

type Query {
  customer(id: ID!): CustomerProfile
  myInvoices(first: Int = 20, after: String): InvoiceConnection!
  mySupportTickets(first: Int = 20, after: String): SupportTicketConnection!
}
```

Type mới mô tả từng phần contract có ý nghĩa. `CustomerSummary` có thể dùng trong danh sách; `CustomerProfile` dùng cho màn hình hồ sơ; invoice và support ticket được truy cập qua query riêng có phân trang.

Không nhất thiết phải tách type chỉ vì field có quyền truy cập khác nhau. GraphQL field authorization vẫn cần được thực thi ở server; việc đặt field trong type riêng chỉ giúp contract và use case dễ hiểu hơn, không thay thế kiểm tra quyền.

## Tránh root field tổng quát và CRUD quá rộng

Root field là điểm vào chính của API. Tên field nên mô tả tài nguyên hoặc hành động nghiệp vụ, không bắt client truyền tên class, tên bảng hoặc câu lệnh tùy ý.

Thiết kế quá tổng quát:

```graphql
type Query {
  getEntity(type: String!, id: ID!): JSON
  search(type: String!, filter: JSON): [JSON!]!
}

type Mutation {
  saveEntity(type: String!, id: ID, payload: JSON!): JSON
  execute(command: String!, arguments: JSON): JSON
}
```

Client không biết contract của từng loại dữ liệu. Schema không thể kiểm tra field, kiểu dữ liệu và quan hệ của payload; authorization và validation bị đẩy vào các nhánh runtime. Codegen cũng không thể tạo type an toàn.

Thiết kế theo use case:

```graphql
type Query {
  book(id: ID!): Book
  searchBooks(input: BookSearchInput!): BookConnection!
  order(id: ID!): Order
  myOrders(first: Int = 20, after: String): OrderConnection!
}

type Mutation {
  createBook(input: CreateBookInput!): BookPayload!
  placeOrder(input: PlaceOrderInput!): PlaceOrderPayload!
  cancelOrder(input: CancelOrderInput!): CancelOrderPayload!
}
```

Các field có thể được triển khai bởi controller và service riêng. Schema thể hiện input/output rõ ràng, giúp validation, authorization, documentation và client code generation có cơ sở cụ thể.

Không cần tạo một mutation riêng cho mọi cột database. Hãy đặt mutation theo hành động có ý nghĩa nghiệp vụ như `placeOrder`, `cancelOrder`, `changeShippingAddress`; mỗi use case có thể cập nhật nhiều bảng bên trong application service.

## Thiết kế input chuyên biệt theo use case

Một `SearchInput` dùng chung cho toàn hệ thống thường trở thành object khổng lồ với nhiều field nullable, khó xác định field nào hợp lệ trong ngữ cảnh nào.

Ví dụ input tổng quát không nên dùng:

```graphql
input SearchInput {
  text: String
  customerId: ID
  bookId: ID
  orderId: ID
  invoiceStatus: String
  ticketStatus: String
  warehouseId: ID
  minPrice: Float
  maxPrice: Float
  createdAfter: String
  createdBefore: String
  includeArchived: Boolean
  includeDeleted: Boolean
  sortBy: String
  sortDirection: String
  ...
}
```

Thay bằng input có phạm vi rõ:

```graphql
input BookSearchInput {
  keyword: String
  authorId: ID
  category: BookCategory
  minPrice: Money
  maxPrice: Money
  publishedAfter: Date
  publishedBefore: Date
  first: Int = 20
  after: String
}

input OrderSearchInput {
  status: OrderStatus
  placedAfter: DateTime
  placedBefore: DateTime
  first: Int = 20
  after: String
}
```

Input riêng giúp GraphQL kiểm tra đúng loại filter và giúp service nhận một command/query object có ý nghĩa. Nếu hai use case thực sự chia sẻ một nhóm field ổn định, có thể tái sử dụng một input type nhỏ; không nên tạo abstraction chung chỉ để tránh lặp vài dòng SDL.

### Giới hạn filter và sort

Không nên cho client truyền tên cột SQL, tên property Java hoặc biểu thức sort tự do. Dùng enum cho các lựa chọn có tập giá trị xác định:

```graphql
enum BookSortField {
  TITLE
  PRICE
  PUBLISHED_AT
}

enum SortDirection {
  ASC
  DESC
}

input BookSortInput {
  field: BookSortField!
  direction: SortDirection! = ASC
}
```

Server ánh xạ enum sang danh sách sort field cho phép. Không nối trực tiếp giá trị client vào SQL/JPQL. Đồng thời giới hạn số filter kết hợp, khoảng ngày, kích thước trang và chi phí truy vấn.

## Phân trang mọi quan hệ có thể lớn

Field list không phân trang là một trong những nguồn làm schema và query trở nên khó kiểm soát. Ví dụ:

```graphql
type Author {
  books: [Book!]!
}
```

Client có thể yêu cầu toàn bộ sách của một tác giả. Khi dữ liệu tăng, resolver có thể tải quá nhiều bản ghi và response lớn bất thường.

Đưa phân trang vào field:

```graphql
type Author {
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

Quy định giới hạn `first` ở server, ví dụ từ 1 đến 100. Default value giúp client cũ không phải gửi argument mới; validation/service vẫn phải từ chối giá trị vượt giới hạn. Cursor nên ổn định theo thứ tự sort và có thể dùng opaque encoding để client không phụ thuộc cấu trúc nội bộ.

Các quan hệ có khả năng lớn như orders, invoices, reviews, audit events và support tickets nên có pagination hoặc query chuyên biệt. Không phải mọi list đều cần connection: list enum nhỏ hoặc tập giá trị cố định có thể trả trực tiếp.

Trong Spring for GraphQL, bind input đã thiết kế theo use case vào một record riêng rồi kiểm tra giới hạn trước khi gọi service:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

public record BookSearchInput(
        String keyword,
        String authorId,
        Integer first,
        String after) {
}

@Controller
public class CatalogQueryController {

    private final CatalogService catalogService;

    public CatalogQueryController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public BookConnection searchBooks(@Argument("input") BookSearchInput input) {
        int first = input.first() == null ? 20 : input.first();
        if (first < 1 || first > 100) {
            throw new IllegalArgumentException("first phải nằm trong khoảng 1..100");
        }
        return catalogService.search(input.keyword(), input.authorId(), first, input.after());
    }
}
```

Ví dụ giả định schema có `searchBooks(input: BookSearchInput!): BookConnection!` và `BookSearchInput.first` là nullable với default `20`. Trong ứng dụng thực tế, dùng exception handler để ánh xạ lỗi giới hạn thành mã GraphQL client error ổn định; không trả stack trace hoặc message nội bộ.

## Kiểm soát chiều sâu và độ phức tạp của query

GraphQL cho phép client kết hợp field lồng nhau. Một query có thể mở rộng số lượng resolver theo cấp số nhân nếu mỗi object trả nhiều quan hệ list.

Ví dụ query nguy hiểm khi không giới hạn:

```graphql
query DeepCatalog {
  authors(first: 100) {
    books(first: 100) {
      reviews(first: 100) {
        comments(first: 100) {
          author {
            books(first: 100) {
              id
            }
          }
        }
      }
    }
  }
}
```

Để bảo vệ server, kết hợp nhiều lớp:

- Giới hạn page size ở từng field list.
- Giới hạn query depth để ngăn cây lồng nhau quá sâu.
- Tính query complexity/cost theo field, đặc biệt với list và resolver tốn tài nguyên.
- Đặt timeout cho downstream call và database query.
- Dùng rate limit, authentication và quota theo client/tenant.
- Dùng DataLoader hoặc `@BatchMapping` để tránh N+1 khi truy vấn quan hệ.
- Theo dõi latency, lỗi và số lượng DataFetcher/SQL để hiệu chỉnh cost model.

Giới hạn depth đơn lẻ không đủ: query nông vẫn có thể yêu cầu một list hàng trăm nghìn phần tử. Giới hạn page size đơn lẻ cũng không đủ nếu client lồng nhiều list. Cost analysis nên tính cả số lượng phần tử tối đa và trọng số của field.

Spring for GraphQL chạy trên GraphQL Java và cho phép tích hợp instrumentation qua `GraphQlSource`. Có thể đăng ký query depth/complexity instrumentation phù hợp với phiên bản GraphQL Java đang dùng bằng cấu hình `GraphQlSourceBuilderCustomizer` của Spring Boot hoặc builder trực tiếp. API cụ thể của instrumentation phụ thuộc GraphQL Java version được dependency management chọn; không nên copy một constructor từ version khác mà chưa kiểm tra dependency tree.

Các giới hạn nghiệp vụ như `first <= 100` vẫn cần thực hiện trong argument validation/service, ngay cả khi đã có query complexity instrumentation.

## Không expose field chỉ vì entity/database có field đó

GraphQL schema là public contract. Việc một field có trong JPA entity hoặc database không có nghĩa client được phép đọc nó.

Ví dụ không nên expose:

```graphql
type Employee {
  id: ID!
  name: String!
  salary: Money
  disciplinaryNotes: String
  managerPrivateComments: String
  accessToken: String
}
```

Các field nhạy cảm như access token, password hash, private notes hoặc dữ liệu cá nhân không nên trở thành public GraphQL field. Với dữ liệu hợp lệ nhưng chỉ một số role được đọc, có thể dùng field authorization và kiểm tra quyền tại service/resolver. Ẩn field khỏi schema và kiểm tra quyền truy cập là hai quyết định khác nhau.

Ví dụ field có bảo vệ quyền:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;

@Controller
public class EmployeePrivateDataController {

    private final EmployeeService employeeService;

    public EmployeePrivateDataController(EmployeeService employeeService) {
        this.employeeService = employeeService;
    }

    @SchemaMapping(typeName = "Employee", field = "salary")
    @PreAuthorize("hasAuthority('employee:salary:read')")
    public Money salary(Employee employee) {
        return employeeService.salaryFor(employee.id());
    }
}
```

Để method security hoạt động, ứng dụng cần bật method security và cấu hình Spring Security phù hợp. Việc có `@PreAuthorize` không thay thế kiểm tra quyền theo tenant hoặc quan hệ sở hữu trong service.

Không dùng việc tắt introspection như giải pháp chính để che field nhạy cảm. Client có thể biết schema từ codegen, logs hoặc tài liệu; server vẫn phải enforce authorization trên mọi request.

## Chia schema thành file theo domain trong Spring for GraphQL

Schema lớn có thể được chia thành nhiều file SDL để dễ sở hữu và review. Đây là cách tổ chức mã nguồn; nó không tự làm API surface nhỏ hơn.

Ví dụ cấu trúc:

```text
src/main/resources/graphql/
├── catalog.graphqls
├── orders.graphqls
└── customers.graphqls
```

File `catalog.graphqls` khai báo root type:

```graphql
type Query {
  book(id: ID!): Book
  searchBooks(input: BookSearchInput!): BookConnection!
}

type Book {
  id: ID!
  title: String!
  author: Author
}
```

File `orders.graphqls` mở rộng Query và khai báo các type của order:

```graphql
extend type Query {
  order(id: ID!): Order
  myOrders(first: Int = 20, after: String): OrderConnection!
}

type Order {
  id: ID!
  status: OrderStatus!
  total: Money!
}
```

File `customers.graphqls` có thể khai báo `extend type Query` cho customer profile và các type liên quan.

Spring Boot có thể nạp các schema resource dưới `classpath:graphql/**/` theo cấu hình mặc định. Nếu thay đổi schema location, cấu hình `spring.graphql.schema.locations` tương ứng. Trong ứng dụng không dùng Boot, truyền toàn bộ schema resources vào `GraphQlSource` builder.

Chỉ khai báo `type Query` và `type Mutation` gốc một lần; file khác dùng `extend type Query` hoặc `extend type Mutation`. Chia file theo domain giúp review và phân quyền ownership, nhưng gateway/client vẫn nhìn thấy một schema đã hợp nhất.

## Khi nào cần nhiều GraphQL service hoặc Federation?

Không nên tách subgraph chỉ vì một file SDL quá dài. Có thể chia file, package controller và module service theo domain trong cùng ứng dụng mà vẫn giữ một GraphQL endpoint.

Federation phù hợp khi các domain được sở hữu và triển khai độc lập, có ranh giới dữ liệu rõ và cần compose thành một supergraph. Tách subgraph chỉ để giảm số field của một schema có thể làm tăng độ phức tạp vận hành: network calls, entity resolution, authentication giữa service, tracing phân tán và xử lý lỗi xuyên service.

Trước khi tách, xác định:

- Domain nào thực sự sở hữu entity và dữ liệu?
- Team nào chịu trách nhiệm schema, resolver và vận hành?
- Có nhu cầu triển khai độc lập hoặc scale riêng không?
- Latency và failure mode của các lời gọi liên subgraph có chấp nhận được không?
- Entity key, authorization và data ownership có rõ ràng không?

Nếu chưa có nhu cầu đó, modular monolith với schema resources và application services theo domain thường đơn giản hơn.

## Giữ schema gọn qua vòng đời API

Schema rộng thường hình thành dần qua các field được thêm nhưng không bao giờ được xem lại. Cần quản lý vòng đời field:

1. Thêm field theo use case có client và owner cụ thể.
2. Ghi rõ semantics, nullability, pagination, authorization và error behavior.
3. Theo dõi usage trước khi deprecate hoặc loại bỏ field.
4. Dùng `@deprecated(reason: "...")` để báo client chuyển sang field mới.
5. Chỉ xóa field sau khi kiểm tra operation usage và thời gian migration.
6. Giữ schema diff và operation checks trong CI.

Ví dụ deprecate field cũ:

```graphql
type Query {
  customer(id: ID!): Customer
    @deprecated(reason: "Dùng customerProfile(id:) để lấy hồ sơ khách hàng.")
  customerProfile(id: ID!): CustomerProfile
}
```

Reason phải hướng client tới field hoặc flow thay thế thực sự tồn tại. Không deprecate chỉ để đổi tên nếu chưa có migration plan; hai field có thể cùng tồn tại trong thời gian chuyển đổi.

## Kiểm thử schema surface

Test không chỉ xác minh resolver trả đúng dữ liệu. Cần kiểm tra schema contract để ngăn field nội bộ hoặc generic field vô tình xuất hiện.

Có thể dùng `GraphQlTester` để chạy introspection trong test nội bộ:

```java
@Test
void customerSchemaDoesNotExposePrivateCredentials() {
    graphQlTester.document("""
            query {
              __type(name: "CustomerProfile") {
                fields {
                  name
                }
              }
            }
            """)
            .execute()
            .path("__type.fields[*].name")
            .entityList(String.class)
            .doesNotContain("passwordHash", "accessToken", "internalNotes");
}
```

Introspection có thể bị cấu hình hạn chế trong production; test có thể kiểm tra SDL được build hoặc schema registry artifact thay vì gọi endpoint public. Mục tiêu là xác nhận public contract chỉ chứa field dự định.

Test query complexity/page size nên gửi operation vượt giới hạn và xác minh request bị từ chối trước khi resolver tốn tài nguyên chạy. Test authorization nên gọi field nhạy cảm bằng cả principal có quyền và không có quyền. Test DataLoader cần kiểm tra số lần batch call hoặc số SQL query, không chỉ kiểm tra response đúng.

## Lộ trình refactor schema đang quá rộng

Không cần thiết kế lại toàn bộ schema trong một lần. Có thể giảm rủi ro theo từng bước:

1. **Kiểm kê:** xuất SDL hiện tại, nhóm root field/type/input theo domain và xác định field không có owner.
2. **Quan sát usage:** xem operation nào thực sự gọi field, client nào đang sử dụng và tần suất ra sao.
3. **Phân loại:** field nhạy cảm, field trùng nghĩa, field tổng quát, quan hệ không phân trang, filter quá rộng và field không còn dùng.
4. **Định nghĩa contract đích:** thêm type/input/query chuyên biệt theo use case; đặt pagination và authorization.
5. **Triển khai song song:** thêm field mới, giữ field cũ và chuyển resolver sang application service phù hợp.
6. **Di chuyển client:** cập nhật operation, codegen và test contract.
7. **Deprecate và loại bỏ:** chỉ xóa field cũ khi usage cho thấy không còn client cần nó.
8. **Theo dõi:** kiểm tra latency, error rate, query complexity, DataLoader batching và số SQL query sau refactor.

Không đổi tên hoặc đổi nullability cùng lúc với việc chia domain nếu không cần thiết. Tách thay đổi thành các bước nhỏ giúp schema diff và lỗi production dễ truy nguyên.

## Lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Copy toàn bộ JPA entity thành GraphQL type | Lộ field nội bộ và gắn API vào persistence model. | Thiết kế output type theo contract/use case. |
| Một `SearchInput` cho mọi domain | Nhiều field vô nghĩa trong từng request và validation phức tạp. | Dùng input chuyên biệt, chỉ tái sử dụng nhóm field thật sự ổn định. |
| `JSON` cho mọi payload | Mất schema validation, codegen và khả năng discover. | Khai báo input/output type rõ ràng; chỉ dùng scalar JSON cho dữ liệu thực sự opaque. |
| Mutation `updateEntity` tổng quát | Không diễn đạt hành động và invariant nghiệp vụ. | Dùng mutation theo use case như `cancelOrder` hoặc `changeAddress`. |
| List quan hệ không phân trang | Có thể tải toàn bộ dữ liệu và tạo response lớn. | Dùng connection/cursor hoặc query chuyên biệt. |
| Chỉ giới hạn query depth | Query nông vẫn có thể tải list rất lớn. | Kết hợp page size, query cost, timeout và rate limit. |
| Dùng type riêng như biện pháp authorization | Client vẫn có thể gọi field nếu server không kiểm tra quyền. | Enforce quyền ở resolver/service và tenant scope. |
| Chia file SDL rồi nghĩ schema đã nhỏ hơn | Chỉ thay đổi cấu trúc source, public contract vẫn như cũ. | Đánh giá API surface và domain boundaries riêng. |
| Tách Federation chỉ vì schema dài | Tăng network, ownership và vận hành không cần thiết. | Chỉ tách khi có bounded context/team/deployment độc lập. |
| Xóa field cũ ngay sau khi thêm field mới | Client cũ bị lỗi. | Theo dõi usage, deprecate và migration theo giai đoạn. |

## Ghi nhớ

Tránh schema quá rộng bằng cách thiết kế từ use case và bounded context, không sao chép toàn bộ database model lên API. Dùng type và input chuyên biệt, root field có tên nghiệp vụ, list có phân trang, filter/sort có giới hạn và field authorization rõ ràng. Giới hạn chiều sâu và độ phức tạp query để bảo vệ runtime.

Chia SDL thành nhiều file giúp tổ chức source nhưng không làm public schema nhỏ hơn. Federation chỉ nên được dùng khi có ranh giới domain và nhu cầu triển khai độc lập. Với schema đã tồn tại, quan sát usage, thêm contract mới song song, deprecate có kế hoạch và loại bỏ field cũ sau khi client đã chuyển đổi.

## Tài liệu tham khảo

- [GraphQL.org — Schema and Types](https://graphql.org/learn/schema/)
- [GraphQL.org — Best Practices](https://graphql.org/learn/best-practices/)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [Apollo GraphOS — Schema Design](https://www.apollographql.com/docs/graphos/schema-design/)
