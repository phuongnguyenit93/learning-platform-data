# Thiết kế schema tiến hóa

Một GraphQL API thường được nhiều phiên bản ứng dụng sử dụng cùng lúc. Ứng dụng web có thể được cập nhật ngay, trong khi ứng dụng di động cũ vẫn gửi các operation đã phát hành từ nhiều tháng trước. Vì vậy, schema cần tiến hóa theo cách giữ được hợp đồng mà client đang dùng, đồng thời mở đường cho chức năng mới.

Với Spring for GraphQL, schema SDL và các resolver Java cùng tạo nên hợp đồng đó. Một thay đổi schema chỉ hoàn tất khi field mới có resolver đúng, quyền truy cập phù hợp, hiệu năng chấp nhận được và các operation cũ vẫn chạy như dự kiến.

Sau bài thực hành này, bạn có thể:

- Phân biệt thay đổi tương thích, thay đổi có rủi ro và thay đổi phá vỡ tương thích.
- Mở rộng schema bằng field, argument và input field tùy chọn.
- Đổi tên field theo quy trình deprecate rồi migrate.
- Giữ tương thích khi thay đổi cách phân trang, enum và input object.
- Triển khai resolver bằng `@QueryMapping`, `@SchemaMapping` và `@BatchMapping`.
- Kiểm tra schema và operation bằng `GraphQlTester`, sau đó triển khai theo từng giai đoạn.

## 1. Xem schema là hợp đồng công khai

Schema GraphQL mô tả những gì client được phép hỏi và gửi lên server: kiểu dữ liệu, field, argument, input, enum và nullability. Client thường sinh mã hoặc kiểm tra operation dựa trên schema, vì thế một thay đổi có thể ảnh hưởng đến client ngay cả khi mã Java phía server vẫn biên dịch thành công.

Ví dụ, một API danh mục sản phẩm đang cung cấp schema ban đầu:

```graphql
scalar BigDecimal

type Query {
    product(id: ID!): Product
    products: [Product!]!
}

type Product {
    id: ID!
    code: String!
    name: String!
    price: Money!
}

type Money {
    amount: BigDecimal!
    currency: String!
}
```

Client có thể đang gọi:

```graphql
query ProductList {
    products {
        id
        code
        name
        price {
            amount
            currency
        }
    }
}
```

Các client đã phát hành phụ thuộc vào tên `products`, `code`, hình dạng `Money` và quy tắc nullability. Khi thiết kế thay đổi, hãy bắt đầu bằng việc xác định operation nào đang sử dụng phần schema liên quan. Log operation, persisted query, thống kê field hoặc danh sách client là những nguồn hữu ích để xác định phạm vi ảnh hưởng.

## 2. Phân loại mức độ tương thích trước khi sửa schema

Không phải mọi thay đổi cộng thêm đều an toàn trong mọi client. Bảng sau là quy tắc thực hành để đánh giá trước một lần phát hành.

| Thay đổi | Đánh giá thường gặp | Lý do cần xem xét |
|---|---|---|
| Thêm Query hoặc Mutation mới | Tương thích | Operation cũ không cần gọi field mới |
| Thêm output field mới | Tương thích | Client cũ không chọn field đó; resolver mới vẫn phải hoạt động đúng |
| Thêm argument tùy chọn | Tương thích | Client cũ có thể tiếp tục bỏ qua argument |
| Thêm input field tùy chọn | Tương thích | Input object cũ vẫn hợp lệ |
| Đánh dấu field cũ `@deprecated` | Tương thích | Field vẫn tồn tại và vẫn phục vụ client cũ |
| Xóa hoặc đổi tên field/argument | Phá vỡ tương thích | Operation cũ có thể không còn hợp lệ |
| Đổi kiểu trả về hoặc thay đổi nullability | Có thể phá vỡ tương thích | Kiểu mã sinh ra và cách xử lý dữ liệu có thể thay đổi |
| Thêm input field hoặc argument bắt buộc | Phá vỡ tương thích | Request cũ không gửi giá trị bắt buộc |
| Xóa enum value | Phá vỡ tương thích | Client có thể vẫn gửi hoặc xử lý giá trị đó |
| Đổi ý nghĩa của field nhưng giữ nguyên tên và kiểu | Phá vỡ hợp đồng ngữ nghĩa | Operation vẫn chạy nhưng kết quả không còn như client mong đợi |

Đặc biệt, hãy đánh giá nullability ở cả hai phía:

- Với output, `Product` và `Product!` thể hiện cam kết khác nhau. Nếu resolver trả về `null` cho field `!`, GraphQL phát sinh lỗi thực thi và giá trị null có thể lan lên field cha theo quy tắc null bubbling. Thay đổi nullability vì thế cần được xem là thay đổi hợp đồng và kiểm chứng dữ liệu thực tế.
- Với input, `String` cho phép client bỏ qua hoặc gửi `null`; `String!` yêu cầu giá trị hợp lệ. Chuyển input tùy chọn thành bắt buộc có thể làm request cũ thất bại.
- `0`, chuỗi rỗng và `null` là các giá trị khác nhau. Không dùng `null` để thay cho một giá trị mặc định nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

## 3. Mở rộng theo hướng additive

Nguyên tắc an toàn là bổ sung khả năng mới trước, cho client thời gian chuyển đổi, rồi mới cân nhắc loại bỏ khả năng cũ. Hãy ưu tiên:

1. Thêm field mới với tên và ý nghĩa rõ ràng.
2. Thêm argument tùy chọn hoặc input field tùy chọn khi cần lọc dữ liệu.
3. Giữ field cũ hoạt động trong thời gian client chuyển đổi.
4. Chỉ xóa field cũ sau khi có bằng chứng usage đã về mức chấp nhận được và đã thông báo theo chính sách API.

Tránh đổi nghĩa của field hiện tại chỉ để tránh thêm tên mới. Chẳng hạn, nếu `price` trước đây là giá niêm yết nhưng nay cần biểu diễn giá sau giảm, hãy thêm field có tên thể hiện rõ khái niệm mới hoặc một kiểu dữ liệu mới. Giữ nguyên tên mà đổi ý nghĩa khiến client khó phát hiện lỗi hơn cả lỗi validation.

## 4. Thực hành tiến hóa schema sản phẩm từ v1 sang v2

Giả sử hệ thống cần ba khả năng mới: tìm kiếm có bộ lọc và phân trang, đổi tên `code` thành `sku`, và hiển thị tồn kho cùng nhà cung cấp. Ta sẽ mở rộng schema mà vẫn giữ operation cũ.

SDL sau khi mở rộng có thể như sau:

```graphql
scalar BigDecimal

type Query {
    product(id: ID!): Product
    products: [Product!]!

    productConnection(
        filter: ProductFilter
        first: Int = 20
        after: String
    ): ProductConnection!
}

type Product {
    id: ID!
    code: String! @deprecated(reason: "Use sku instead.")
    sku: String!
    name: String!
    price: Money!
    stock: Int
    supplier: Supplier
}

type Money {
    amount: BigDecimal!
    currency: String!
}

input ProductFilter {
    categoryId: ID
    status: ProductStatus
}

enum ProductStatus {
    ACTIVE
    DRAFT
    ARCHIVED
}

type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
}

type ProductEdge {
    cursor: String!
    node: Product!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}

type Supplier {
    id: ID!
    name: String!
}
```

Các điểm tương thích trong ví dụ:

- `products` vẫn giữ nguyên tên và kiểu trả về. Client cũ tiếp tục sử dụng được.
- `productConnection` là field mới. Client mới có thể dùng `filter`, `first` và `after`; cả ba argument đều tùy chọn.
- `ProductFilter` được thêm mới. Những field bên trong input object đều tùy chọn nên client có thể chỉ gửi phần lọc cần thiết.
- `code` vẫn tồn tại nhưng được đánh dấu `@deprecated`. `sku` là field mới, có thể được client mới chọn độc lập.
- `stock` và `supplier` là nullable vì thông tin có thể chưa tồn tại, không được phép xem, hoặc không có trong nguồn dữ liệu cho một sản phẩm cụ thể. Cần định nghĩa rõ từng trường hợp ở tầng nghiệp vụ và xử lý lỗi.
- `BigDecimal` là custom scalar; ứng dụng phải đăng ký runtime scalar tương ứng để SDL và GraphQL runtime hiểu cùng một định dạng số thập phân. Không nên dùng `Float` cho tiền tệ nếu hệ thống cần độ chính xác thập phân.

Client cũ tiếp tục chạy query cũ. Client mới có thể gửi:

```graphql
query ProductSearch {
    productConnection(
        filter: { categoryId: "cat-10", status: ACTIVE }
        first: 20
    ) {
        edges {
            cursor
            node {
                id
                sku
                name
                stock
                supplier {
                    id
                    name
                }
            }
        }
        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
```

Không thay kiểu trả về của `products` từ `[Product!]!` sang `ProductConnection!` trong cùng lần phát hành. Hai kiểu dữ liệu có cấu trúc khác nhau. Tạo field mới cho connection giúp client có thời gian chuyển đổi mà không làm hỏng operation hiện hữu.

## 5. Đổi tên field bằng deprecation

GraphQL không có thao tác rename field mà vẫn giữ operation cũ tự động hợp lệ. Hãy xem đổi tên là một quá trình gồm nhiều lần phát hành:

1. Thêm field mới, ví dụ `sku`, và triển khai resolver trả về cùng giá trị nghiệp vụ với `code`.
2. Giữ `code` và gắn `@deprecated(reason: "Use sku instead.")`.
3. Cập nhật tài liệu, ví dụ và client để dùng `sku`.
4. Theo dõi tần suất sử dụng `code` theo operation hoặc client.
5. Chỉ xóa `code` trong một thay đổi phá vỡ tương thích đã được thông báo và phối hợp với các client còn sử dụng.

Directive `@deprecated` làm cho ý định thay thế hiển thị trong schema introspection và công cụ phát triển. Nó không tự động chặn request, không tự viết lại query và cũng không tự xóa resolver. Trong giai đoạn chuyển tiếp, server vẫn phải phục vụ field cũ.

## 6. Cập nhật resolver trong Spring for GraphQL

Trong ứng dụng Spring Boot dùng Spring for GraphQL, các file SDL thường được đặt dưới `src/main/resources/graphql/`. Spring khởi tạo schema từ các file này và liên kết field với controller method hoặc data fetcher tương ứng.

Ví dụ controller cho các Query mới và field tương thích cũ:

```java
@Controller
public class ProductGraphQlController {

    private final ProductService productService;

    public ProductGraphQlController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }

    @QueryMapping
    public List<Product> products() {
        return productService.findAll();
    }

    @QueryMapping
    public ProductConnection productConnection(
            @Argument ProductFilter filter,
            @Argument Integer first,
            @Argument String after) {

        int pageSize = first == null ? 20 : Math.min(Math.max(first, 1), 100);
        return productService.findConnection(filter, pageSize, after);
    }

    @SchemaMapping(typeName = "Product", field = "code")
    public String legacyCode(Product product) {
        return product.sku();
    }
}
```

`@QueryMapping` liên kết method với field thuộc `Query`. `@SchemaMapping` liên kết method với một field cụ thể của object type. Trong ví dụ, `code` vẫn đọc được từ model mới thông qua resolver tương thích, còn `sku` có thể được Spring phân giải từ property/accessor tương ứng của `Product` nếu không cần logic tùy chỉnh.

Giới hạn `first` ở server giúp client không yêu cầu một trang quá lớn. Giá trị mặc định trong SDL và giới hạn trong resolver cần thống nhất với chính sách phân trang của service. Với API thực tế, service cũng phải xác thực cursor, thứ tự sắp xếp ổn định và quyền truy cập trên từng bản ghi.

## 7. Đánh giá input object khi schema thay đổi

Thêm field tùy chọn vào input object thường tương thích:

```graphql
input ProductFilter {
    categoryId: ID
    status: ProductStatus
    minPrice: BigDecimal
    maxPrice: BigDecimal
}
```

Client cũ chỉ gửi `categoryId` vẫn hợp lệ. Tuy nhiên, hãy giữ ý nghĩa của các field ổn định. Nếu `minPrice` và `maxPrice` được tính theo đơn vị tiền tệ của sản phẩm, cần mô tả rõ điều đó hoặc đưa currency vào input; không để client tự đoán.

Đối với mutation cập nhật, cần phân biệt ba trường hợp: field không được gửi, field được gửi với `null`, và field được gửi với giá trị cụ thể. Ví dụ, không gửi `description` có thể mang nghĩa giữ nguyên mô tả, còn gửi `description: null` có thể mang nghĩa xóa mô tả. DTO Java thông thường đôi khi làm mất khác biệt này khi bind input. Spring for GraphQL cung cấp `ArgumentValue<T>` để biểu diễn cả trạng thái không được cung cấp và giá trị được cung cấp, kể cả `null`; hãy dùng khi nghiệp vụ cần phân biệt hai trường hợp.

Không thêm một input field bắt buộc vào mutation đang được client sử dụng rộng rãi nếu client cũ không thể gửi field đó. Có thể tạo mutation mới với input type mới, hoặc thêm field tùy chọn rồi xác thực theo quy tắc tương thích trong giai đoạn chuyển đổi.

## 8. Tiến hóa enum và kiểu trừu tượng

Enum cũng là một phần của hợp đồng. Thêm một enum value vào enum chỉ dùng làm input thường cho phép server nhận thêm lựa chọn mới. Nhưng khi enum xuất hiện trong output, client có thể sinh mã với switch exhaustive hoặc giả định chỉ có các giá trị đã biết. Client nên có nhánh xử lý giá trị không nhận diện được.

Không xóa enum value khi vẫn còn dữ liệu hoặc client gửi giá trị đó. Có thể đánh dấu enum value cũ bằng `@deprecated` để thông báo lựa chọn thay thế, rồi đo usage trước khi loại bỏ.

Với interface và union, thêm một kiểu triển khai hoặc một member mới cũng có thể ảnh hưởng client dùng fragment theo kiểu cụ thể. Client cần xử lý trường hợp `__typename` mới. Khi mở rộng kiểu trừu tượng, hãy kiểm tra operation dùng inline fragment và kiểm tra các client có logic phân nhánh theo `__typename`.

## 9. Giữ ổn định ngữ nghĩa của pagination và scalar

Phân trang là một ví dụ điển hình của thay đổi trông có vẻ nhỏ nhưng ảnh hưởng trực tiếp đến client. Khi thêm connection, hãy xác định rõ:

- `first` là số phần tử tối đa, có giới hạn trên cụ thể.
- `after` là cursor opaque do server tạo; client không tự diễn giải cấu trúc nội bộ.
- Thứ tự sắp xếp phải ổn định giữa các trang, kể cả khi nhiều bản ghi có cùng giá trị sắp xếp chính.
- `hasNextPage` phản ánh dữ liệu còn lại theo cùng điều kiện lọc và quyền truy cập.
- `endCursor` có thể là `null` khi không có edge cuối cùng.

Với custom scalar như `BigDecimal`, `DateTime` hoặc `Currency`, schema phải đi cùng quy tắc serialize, parse input và kiểm tra giá trị. Không đổi định dạng từ chuỗi thập phân sang số dấu phẩy động chỉ vì kiểu Java nội bộ thay đổi. Nếu cần một biểu diễn mới, hãy cân nhắc scalar hoặc field mới và cho client thời gian di chuyển.

## 10. Bảo mật khi thêm field

Một field mới có thể mở ra dữ liệu nhạy cảm mà Query cha trước đây không cung cấp. Quyền truy cập cần được đánh giá ở đúng cấp độ field và bản ghi. Ví dụ, `stock` có thể chỉ dành cho người dùng có quyền xem tồn kho, trong khi `name` vẫn công khai.

Trong Spring Security, có thể áp dụng method security cho resolver, ví dụ:

```java
@PreAuthorize("hasAuthority('inventory:read')")
@SchemaMapping(typeName = "Product", field = "stock")
public Integer stock(Product product) {
    return inventoryService.availableStock(product.id());
}
```

Đảm bảo method security đã được bật trong ứng dụng. Hãy quyết định rõ hành vi khi người dùng không có quyền: trả lỗi GraphQL cho field, trả `null` theo chính sách công khai, hay từ chối toàn bộ operation. Vì `stock` trong SDL là nullable, lỗi hoặc dữ liệu không có ở field này không bắt buộc làm mất toàn bộ object `Product`. Tuy vậy, nullability không thay thế kiểm soát truy cập; resolver vẫn phải kiểm tra quyền.

Ngoài quyền trên field, truy vấn theo `id`, filter và cursor phải áp dụng quyền ở cấp bản ghi. Không được để một field mới vô tình bỏ qua tenant boundary hoặc điều kiện phân quyền vốn có trong service.

## 11. Kiểm soát N+1 khi thêm quan hệ

Thêm field `supplier` có thể khiến mỗi Product gọi một truy vấn riêng để tải nhà cung cấp. Với danh sách lớn, schema vẫn hợp lệ nhưng chi phí truy vấn tăng theo số sản phẩm. Spring for GraphQL hỗ trợ `@BatchMapping` để tải quan hệ theo lô:

```java
@BatchMapping(typeName = "Product", field = "supplier")
public Map<Product, Supplier> supplier(List<Product> products) {
    return supplierService.findForProducts(products);
}
```

`findForProducts` cần trả về ánh xạ từ từng Product nguồn sang Supplier tương ứng, theo đúng semantics của field. Nếu quan hệ không tồn tại, xử lý theo nullability đã khai báo. Với quan hệ phức tạp hơn, có thể dùng `DataLoader` để gom yêu cầu và chia sẻ kết quả trong phạm vi execution.

Khi thêm field mới, hãy kiểm tra số lần gọi repository/service, kích thước batch, giới hạn trang và khả năng truy vấn lồng nhau. GraphQL cho phép client chọn nhiều nhánh dữ liệu trong một operation; vì vậy cần giới hạn độ sâu, độ phức tạp hoặc chi phí truy vấn theo chính sách của ứng dụng khi phù hợp.

## 12. Kiểm thử operation cũ và mới bằng GraphQlTester

Kiểm thử schema chỉ xác nhận schema có thể được tạo; nó chưa chứng minh resolver trả dữ liệu đúng. Hãy giữ các operation đại diện cho client cũ và thêm operation mới vào bộ kiểm thử.

Ví dụ với `GraphQlTester`:

```java
@SpringBootTest
class ProductGraphQlCompatibilityTests {

    @Autowired
    private GraphQlTester graphQlTester;

    @Test
    void oldFieldCodeRemainsAvailable() {
        graphQlTester.document("""
                query {
                    product(id: "p-1") {
                        id
                        code
                        sku
                    }
                }
                """)
            .execute()
            .path("product.code").entity(String.class).isEqualTo("SKU-001")
            .path("product.sku").entity(String.class).isEqualTo("SKU-001");
    }

    @Test
    void newConnectionSupportsOptionalFilterAndPagination() {
        graphQlTester.document("""
                query {
                    productConnection(
                        filter: { status: ACTIVE }
                        first: 10
                    ) {
                        edges { cursor node { id sku } }
                        pageInfo { hasNextPage endCursor }
                    }
                }
                """)
            .execute()
            .path("productConnection.edges").entityList(Object.class).hasSize(1);
    }
}
```

Đây là khung kiểm thử minh họa; fixture, mock hoặc dữ liệu test cần cung cấp sản phẩm `p-1` và kết quả connection tương ứng. Nếu dùng `@SpringBootTest`, cấu hình test phải khởi tạo đầy đủ service và GraphQL schema. Có thể dùng `@GraphQlTest` khi chỉ muốn kiểm thử lát cắt controller và cung cấp các dependency giả lập.

Nên có thêm các kiểm tra cho:

- Schema khởi tạo thành công và custom scalar đã được đăng ký.
- Field cũ còn được truy vấn trong giai đoạn deprecation.
- Client có thể bỏ qua toàn bộ input tùy chọn hoặc chỉ gửi một phần input.
- Phân biệt input bị bỏ qua với input được gửi `null` khi nghiệp vụ yêu cầu.
- Người dùng thiếu quyền không đọc được field nhạy cảm.
- Field quan hệ không tạo N+1 khi truy vấn danh sách.
- Cursor sai, trang quá lớn và dữ liệu rỗng được xử lý theo hợp đồng.

## 13. Đưa kiểm tra tương thích vào quy trình phát hành

Với mỗi thay đổi schema, review nên trả lời được các câu hỏi: field hoặc argument nào được thêm, đổi hoặc bỏ; operation nào đang sử dụng chúng; client cũ có tiếp tục hợp lệ không; resolver có dữ liệu và quyền truy cập đúng không; chi phí truy vấn có thay đổi không.

Có thể tự động hóa bằng cách lưu schema của bản phát hành trước và so sánh với schema ứng viên trong CI. Công cụ diff schema giúp phát hiện field bị xóa, kiểu bị đổi, input bắt buộc mới hoặc enum value bị loại bỏ. Sau bước diff, kiểm tra các operation thực tế hoặc persisted query với schema mới để tìm operation không còn hợp lệ.

Schema diff không phát hiện được mọi thay đổi ngữ nghĩa. Ví dụ, giữ `price: Money!` nhưng đổi currency mặc định hoặc đổi cách tính giá vẫn có thể làm hỏng client. Vì thế, kiểm thử nghiệp vụ, review mô tả field và theo dõi dữ liệu runtime vẫn cần thiết.

## 14. Triển khai theo quy trình expand–migrate–contract

Một lần đổi tên `code` thành `sku` có thể được phát hành theo trình tự sau:

| Giai đoạn | Thay đổi phía server | Việc cần làm ở client |
|---|---|---|
| Expand | Thêm `sku`, giữ `code`, triển khai cả hai resolver | Chưa cần đổi ngay |
| Migrate | Giữ cả hai field và theo dõi usage | Chuyển query, code sinh và kiểm thử sang `sku` |
| Verify | Kiểm tra log cho thấy client quan trọng không còn gọi `code` | Phát hành các client đã cập nhật |
| Contract | Xóa `code` trong đợt thay đổi phá vỡ tương thích đã thông báo | Đảm bảo không còn client phụ thuộc field cũ |

Khi có nhiều instance server chạy song song trong lúc deploy, mỗi instance cần hiểu schema và operation theo cách tương thích trong suốt quá trình chuyển tiếp. Triển khai resolver hỗ trợ field mới trước khi phát hành client bắt đầu yêu cầu field đó. Không xóa field cũ chỉ dựa vào việc một client mới đã được phát hành; hãy dựa trên usage quan sát được và vòng đời hỗ trợ đã thống nhất.

## 15. Checklist trước khi hợp nhất thay đổi schema

- [ ] Đã xác định operation, client và field hiện tại bị ảnh hưởng.
- [ ] Thay đổi được phân loại là tương thích, có rủi ro hay phá vỡ tương thích.
- [ ] Field mới có tên, mô tả, kiểu và nullability phản ánh đúng nghiệp vụ.
- [ ] Argument và input field mới là tùy chọn nếu client cũ cần tiếp tục gửi request cũ.
- [ ] Field hoặc enum value sắp thay thế đã được đánh dấu `@deprecated` với lý do rõ ràng.
- [ ] Resolver Spring for GraphQL đã được triển khai và xử lý trường hợp thiếu dữ liệu.
- [ ] Quyền truy cập được kiểm tra ở cấp field và bản ghi.
- [ ] Field quan hệ mới đã được đánh giá N+1 và có batching/DataLoader khi cần.
- [ ] Pagination, scalar, enum và semantics của `null` được mô tả nhất quán.
- [ ] `GraphQlTester` xác nhận operation cũ và operation mới.
- [ ] Schema diff và kiểm tra operation được chạy trong CI.
- [ ] Có kế hoạch migrate, theo dõi usage và thời điểm contract field cũ.

## Bài tập thực hành

Một API quản lý đơn hàng hiện có `order(id: ID!): Order` và `Order.total: BigDecimal!`. Sản phẩm cần bổ sung trạng thái thanh toán, chi tiết tiền tệ và khả năng lọc đơn hàng theo khoảng thời gian.

Hãy thiết kế một lần tiến hóa schema đáp ứng các yêu cầu sau:

1. Giữ operation cũ truy vấn `order` và `total` hoạt động.
2. Thêm thông tin tiền tệ mà không thay đổi ý nghĩa của `total`.
3. Thêm filter tùy chọn cho truy vấn danh sách đơn hàng.
4. Đánh dấu một field cũ cần thay thế bằng `@deprecated` và mô tả quy trình chuyển client.
5. Xác định field nào cần nullable, field nào có thể cam kết non-null, kèm lý do.
6. Viết SDL mới, resolver Spring for GraphQL và ít nhất hai kiểm thử `GraphQlTester`: một cho operation cũ, một cho operation mới.
7. Nếu trạng thái thanh toán chỉ dành cho một nhóm người dùng, xác định nơi kiểm tra quyền và cách trả lỗi.

Khi hoàn thành, hãy tự kiểm tra rằng client cũ vẫn gửi được operation ban đầu, client mới có thể sử dụng các field mới, và việc loại bỏ field cũ chỉ diễn ra sau khi đã có dữ liệu usage đủ tin cậy.
