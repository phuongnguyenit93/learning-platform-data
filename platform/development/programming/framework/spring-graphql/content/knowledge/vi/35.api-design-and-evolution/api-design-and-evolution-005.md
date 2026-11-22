# Thêm field không phá client

GraphQL API thường được tiến hóa bằng cách bổ sung khả năng vào schema đang dùng, thay vì tạo một phiên bản endpoint mới cho mỗi thay đổi. Vì client chỉ nhận những field được chọn trong operation, việc thêm một field mới vào object type thường không làm query cũ mất hiệu lực. Client cũ tiếp tục yêu cầu các field quen thuộc; client mới có thể chọn thêm field khi sẵn sàng.

Trong Spring for GraphQL, thay đổi này cần được thực hiện đồng bộ ở SDL và phần xử lý dữ liệu. Thêm field vào schema nhưng không có resolver hoặc dữ liệu phù hợp có thể khiến client mới nhận `null`, lỗi thực thi hoặc kết quả sai. Một thay đổi additive an toàn cần giữ nguyên hợp đồng cũ, có ngữ nghĩa rõ ràng cho dữ liệu cũ và được kiểm thử bằng những operation đại diện cho client hiện tại.

## 1. Vì sao GraphQL API có thể tiến hóa mà không cần version cho mỗi thay đổi?

Với REST, một endpoint thường trả một cấu trúc response do server định nghĩa. Nếu server thêm property vào JSON, client dùng deserializer nghiêm ngặt có thể gặp vấn đề tùy công nghệ. GraphQL hoạt động theo cách khác: client khai báo chính xác field cần nhận trong query.

Ví dụ, client cũ gửi:

```graphql
query ProductCard {
    product(id: "p-101") {
        id
        name
        price
    }
}
```

Server trả đúng các field được chọn. Khi schema được bổ sung `brandLabel`, operation trên vẫn hợp lệ vì nó không tham chiếu đến field mới và các field cũ vẫn còn nguyên.

Client mới có thể yêu cầu thêm field:

```graphql
query ProductCard {
    product(id: "p-101") {
        id
        name
        price
        brandLabel
    }
}
```

Hai client dùng chung endpoint và schema hiện tại. Client cũ không phải nâng cấp ngay khi server bổ sung field.

## 2. Thay đổi additive và thay đổi breaking

Thay đổi additive mở rộng schema mà không làm mất khả năng thực thi các operation đang hợp lệ. Thay đổi breaking làm operation cũ không còn hợp lệ hoặc thay đổi ngữ nghĩa theo cách client hiện tại không thể xử lý an toàn.

| Thay đổi | Đánh giá thường gặp | Lý do |
|---|---|---|
| Thêm field nullable vào object type | Additive | Query cũ không cần chọn field mới. |
| Thêm query hoặc mutation mới | Additive | Operation cũ không bị ảnh hưởng. |
| Thêm argument có default hoặc nullable | Additive | Client cũ có thể tiếp tục bỏ qua argument. |
| Thêm field optional vào input object | Thường additive | Input cũ vẫn hợp lệ nếu field mới không bắt buộc. |
| Thêm field non-null vào output type | Additive về validation, cần kiểm tra dữ liệu | Resolver phải bảo đảm luôn trả giá trị khi client chọn field. |
| Thêm argument non-null không có default vào field cũ | Breaking | Query cũ không truyền argument mới sẽ không hợp lệ. |
| Xóa hoặc đổi tên field | Breaking | Query cũ tham chiếu field không còn tồn tại. |
| Đổi kiểu field hoặc thay đổi nullability output | Breaking/rủi ro cao | Hợp đồng kiểu dữ liệu hoặc khả năng null thay đổi. |
| Thêm enum value hoặc union member | Có thể nguy hiểm | Client dùng exhaustive switch có thể không biết giá trị mới. |

Không nên chỉ dựa vào nhãn “non-breaking” của công cụ schema diff. Cần xem cả validation ở GraphQL server, code generation của client, cách client xử lý giá trị chưa biết và hành vi runtime của resolver.

## 3. Thêm field vào object type

Giả sử schema ban đầu có Product:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    price: Float!
}
```

Ta muốn bổ sung nhãn thương hiệu để client có thể hiển thị trên product card. Có thể thêm field nullable:

```graphql
type Product {
    id: ID!
    name: String!
    price: Float!
    brandLabel: String
}
```

Client cũ chỉ chọn `id`, `name`, `price` nên không bị buộc thay đổi. Client mới chọn `brandLabel` khi giao diện cần dùng.

Field nullable phù hợp khi dữ liệu lịch sử chưa có thương hiệu, bản ghi chưa được enrich hoặc resolver có thể không tìm thấy nhãn. Nếu field thực sự luôn có giá trị với mọi Product tồn tại, có thể cân nhắc `String!`; tuy nhiên phải bảo đảm invariant đó trong dữ liệu và resolver trước khi công bố.

## 4. Vì sao field mới thường nên nullable lúc đầu?

GraphQL nullability là một phần của hợp đồng API:

- `String` cho phép resolver trả chuỗi hoặc `null`.
- `String!` cam kết resolver trả chuỗi, không được trả `null`.

Nếu resolver của field `String!` trả `null`, GraphQL tạo execution error và null có thể lan lên parent theo quy tắc non-null propagation. Điều này có thể làm mất cả object hoặc phần response lớn hơn field mới.

Ví dụ dữ liệu cũ có thể chưa lưu `brandLabel`. Nếu khai báo:

```graphql
type Product {
    id: ID!
    brandLabel: String!
}
```

thì resolver cần tính được nhãn cho tất cả Product mà client có thể truy vấn, kể cả dữ liệu legacy. Nếu không bảo đảm được, schema nên dùng `brandLabel: String` và client xử lý trường hợp không có nhãn.

Nullable không có nghĩa là tùy tiện trả null. Hợp đồng nên giải thích rõ null có nghĩa là “không có dữ liệu”, “không áp dụng” hay “không thể hiển thị”. Nếu cần phân biệt nhiều trạng thái, có thể thiết kế một object kết quả có `status`, `value` hoặc `reason` thay vì dùng null cho mọi trường hợp.

## 5. Client cũ không tự nhận field mới

GraphQL không tự động thêm mọi field vào response. Client chỉ nhận field mới nếu operation chọn nó.

Query cũ:

```graphql
query {
    product(id: "p-101") {
        id
        name
    }
}
```

Response vẫn có hình dạng:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard"
    }
  }
}
```

Query mới:

```graphql
query {
    product(id: "p-101") {
        id
        name
        brandLabel
    }
}
```

Response có thêm `brandLabel` vì client đã yêu cầu:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "brandLabel": "Northwind"
    }
  }
}
```

Đây là cơ chế chính giúp thêm field vào GraphQL object type mà không làm response của query cũ tự thay đổi.

## 6. Triển khai field mới trong Spring for GraphQL

Spring for GraphQL thường dùng schema-first: SDL mô tả hợp đồng, còn annotated controller cung cấp DataFetcher cho các field cần logic riêng.

Đặt SDL trong resource, ví dụ `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    brandLabel: String
}
```

Controller có thể ánh xạ query và field mới:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class ProductController {

    private final ProductCatalog products;
    private final BrandQueryService brands;

    ProductController(ProductCatalog products, BrandQueryService brands) {
        this.products = products;
        this.brands = brands;
    }

    @QueryMapping
    ProductView product(@Argument String id) {
        return products.findById(id).orElse(null);
    }

    @SchemaMapping(typeName = "Product", field = "brandLabel")
    String brandLabel(ProductView product) {
        if (product.brandId() == null) {
            return null;
        }

        return brands.displayName(product.brandId()).orElse(null);
    }
}
```

Các model và service được dùng trong ví dụ:

```java
import java.util.Optional;

public record ProductView(String id, String name, String brandId) {}

public interface ProductCatalog {
    Optional<ProductView> findById(String id);
}

public interface BrandQueryService {
    Optional<String> displayName(String brandId);
}
```

`@QueryMapping` ánh xạ field `Query.product`. `@SchemaMapping` ánh xạ field `Product.brandLabel` và nhận parent object `ProductView`. Nếu Java object đã có property cùng tên và chỉ cần đọc giá trị, GraphQL property data fetcher mặc định có thể đọc property đó mà không cần viết `@SchemaMapping`. Với field tính toán, truy vấn quan hệ hoặc cần kiểm soát riêng, resolver tường minh giúp thể hiện rõ cách lấy dữ liệu.

## 7. Đừng quên resolver và nguồn dữ liệu

Thêm SDL chỉ làm field xuất hiện trong schema. Nó không tự tạo dữ liệu.

Trước khi phát hành field mới, kiểm tra:

1. Field có đúng tên và kiểu trong SDL không?
2. Resolver có được đăng ký cho field cần xử lý không?
3. Parent object có đủ dữ liệu để tính field không?
4. Dữ liệu legacy có thể thiếu giá trị không?
5. Khi không tìm thấy dữ liệu, resolver trả `null`, giá trị mặc định hay lỗi nghiệp vụ?
6. Quyền truy cập có giống với các field liên quan không?
7. Resolver có gây thêm truy vấn N+1 khi client chọn field trên danh sách không?

Nếu field mới được lấy từ quan hệ, cân nhắc `@BatchMapping` hoặc DataLoader khi query có thể trả về nhiều parent objects. Một field additive vẫn có thể làm tăng tải database nếu resolver thực hiện một truy vấn riêng cho từng object.

## 8. Thêm field vào input object

Input object được dùng khi client gửi dữ liệu vào query hoặc mutation:

```graphql
input ProductFilter {
    category: String
}

type Query {
    products(filter: ProductFilter): [Product!]!
}
```

Có thể bổ sung một field tùy chọn:

```graphql
input ProductFilter {
    category: String
    minPrice: Float
}
```

Client cũ chỉ gửi `category` vẫn hợp lệ vì `minPrice` có thể bị bỏ qua hoặc nhận null. Resolver/service cần định nghĩa rõ cách xử lý khi `minPrice` không được truyền.

Không nên thêm field non-null không có default vào input object đang được sử dụng:

```graphql
input ProductFilter {
    category: String
    minPrice: Float!
}
```

Các request cũ không gửi `minPrice` sẽ không còn hợp lệ. Nếu field mới bắt buộc với một luồng nghiệp vụ mới, cân nhắc thêm mutation hoặc input type mới, hoặc dùng field nullable/default và áp dụng điều kiện bắt buộc theo ngữ cảnh phù hợp.

## 9. Thêm argument tùy chọn cho field hiện có

Argument mới nên nullable hoặc có default để operation cũ tiếp tục hợp lệ.

Trước:

```graphql
type Query {
    products: [Product!]!
}
```

Sau:

```graphql
type Query {
    products(category: String): [Product!]!
}
```

Query cũ `products { id name }` vẫn hợp lệ. Query mới có thể lọc theo category:

```graphql
query {
    products(category: "hardware") {
        id
        name
    }
}
```

Trong Spring for GraphQL, resolver có thể nhận argument:

```java
@QueryMapping
List<ProductView> products(@Argument String category) {
    return products.findByCategory(category);
}
```

Nếu cần giá trị mặc định ổn định, có thể khai báo default trong SDL:

```graphql
type Query {
    products(limit: Int = 20): [Product!]!
}
```

Không thêm argument non-null bắt buộc vào field đã tồn tại nếu chưa có kế hoạch migrate client:

```graphql
type Query {
    products(category: String!): [Product!]!
}
```

Operation cũ không truyền `category` sẽ thất bại ở bước validation trước khi resolver được gọi.

## 10. Cẩn trọng với enum value mới

Thêm một giá trị enum không làm query GraphQL cũ sai về mặt schema, nhưng có thể làm client cũ gặp lỗi ở code xử lý kết quả.

Ví dụ:

```graphql
enum OrderStatus {
    PENDING
    PAID
    CANCELLED
}
```

Sau đó thêm:

```graphql
enum OrderStatus {
    PENDING
    PAID
    CANCELLED
    REFUNDED
}
```

Client dùng switch exhaustive có thể không có nhánh cho `REFUNDED`. Với enum trả về cho client, nên có nhánh fallback cho giá trị chưa biết:

```typescript
switch (order.status) {
  case "PENDING":
    return showPending();
  case "PAID":
    return showPaid();
  case "CANCELLED":
    return showCancelled();
  default:
    return showUnknownStatus();
}
```

Đoạn TypeScript chỉ minh họa cách client phòng thủ. Với client được sinh type từ schema, cần cấu hình và kiểm thử cách code generator xử lý enum value mới.

## 11. Cẩn trọng khi mở rộng interface hoặc union

Thêm một object type mới vào union hoặc thêm một implementation mới cho interface có thể làm client cũ gặp một runtime type chưa biết.

Ví dụ union:

```graphql
union SearchResult = Product | Brand
```

Khi bổ sung `Article`:

```graphql
union SearchResult = Product | Brand | Article
```

Client có fragment cho `Product` và `Brand` vẫn hợp lệ, nhưng code xử lý kết quả nên có fallback cho `__typename` chưa biết. Tương tự, client xử lý interface cần tránh giả định chỉ có các concrete type đã biết tại thời điểm build.

## 12. Thêm field vào interface

Nếu thêm field vào GraphQL interface, mọi object type triển khai interface đó phải cung cấp field tương ứng. Thay đổi này có thể yêu cầu cập nhật nhiều type và nhiều resolver cùng lúc.

Ví dụ:

```graphql
interface Node {
    id: ID!
}
```

Nếu thêm `createdAt`:

```graphql
interface Node {
    id: ID!
    createdAt: String
}
```

Các object type như `Product`, `Order` và `Customer` đang `implements Node` phải khai báo `createdAt` với kiểu tương thích. Trước khi merge thay đổi, kiểm tra toàn bộ implementation và schema composition nếu dùng Federation.

Khi chỉ một loại object cần field mới, thêm field trực tiếp vào object type thường có phạm vi nhỏ hơn và ít ràng buộc hơn.

## 13. Thêm field trong hệ thống có Federation

Với GraphQL Federation, một field mới phải được thêm vào subgraph sở hữu field đó. Nếu field mới nằm trên entity được nhiều subgraph chia sẻ, cần kiểm tra key, ownership và composition.

Ví dụ Reviews subgraph bổ sung `reviewCount` trên Product:

```graphql
type Product @key(fields: "id") {
    id: ID!
    reviews: [Review!]!
    reviewCount: Int
}
```

Resolver có thể tính số lượng review:

```java
@SchemaMapping(typeName = "Product", field = "reviewCount")
Integer reviewCount(Product product) {
    return reviews.countByProductId(product.id());
}
```

Trước khi phát hành, xác minh:

- Field mới chỉ được định nghĩa ở subgraph sở hữu nó, trừ khi dùng directive shareable phù hợp.
- Entity key cần thiết vẫn có trong representation để subgraph phân giải field.
- Subgraph có `@EntityMapping` để nhận diện Product.
- Schema composition thành công.
- Gateway/router được cập nhật supergraph artifact trước khi client gửi query chọn field mới.
- Resolver có quyền truy cập dữ liệu và hiệu năng phù hợp.

Không thêm cùng một field vào nhiều subgraph với kỳ vọng gateway tự chọn resolver. Field ownership phải rõ ràng hoặc được khai báo shareable đúng theo Federation specification.

## 14. Đánh dấu field cũ deprecated khi thay thế

Nếu field mới thay thế field cũ, giữ field cũ và đánh dấu deprecated:

```graphql
type Product {
    id: ID!
    displayName: String
    name: String @deprecated(reason: "Use displayName instead.")
}
```

Client cũ vẫn có thể query `name`. Client mới chuyển sang `displayName`. Introspection và công cụ schema có thể hiển thị lý do deprecated để hướng dẫn người dùng API.

Deprecation là tín hiệu cho migration, không phải cơ chế tự động ngăn field được gọi. Server vẫn cần tiếp tục phục vụ field deprecated cho tới khi có bằng chứng đủ tin cậy rằng các client cần thiết đã ngừng sử dụng.

## 15. Quy trình migrate field cũ sang field mới

Một quy trình an toàn có thể chia thành các giai đoạn:

1. **Bổ sung:** thêm field mới và resolver, giữ nguyên field cũ.
2. **Kiểm thử:** xác minh cả query cũ và query mới hoạt động.
3. **Thông báo:** công bố field mới, lý do thay đổi và ví dụ migration.
4. **Chuyển đổi client:** cập nhật từng ứng dụng hoặc operation sang field mới.
5. **Theo dõi:** kiểm tra field usage, persisted operations, log và phiên bản client.
6. **Deprecate:** đánh dấu field cũ với reason rõ ràng khi bắt đầu giai đoạn loại bỏ.
7. **Loại bỏ:** chỉ xóa field cũ sau khi đã đánh giá ảnh hưởng và tuân thủ chính sách hỗ trợ client.

Không xóa field chỉ vì đã đánh dấu deprecated một khoảng thời gian cố định. Một client cũ ít được dùng nhưng vẫn có nghiệp vụ quan trọng có thể cần thời gian hỗ trợ dài hơn.

## 16. Kiểm thử để bảo vệ client cũ

Schema diff có thể phát hiện một số thay đổi breaking, nhưng không thay thế test runtime. Với Spring for GraphQL, `GraphQlTester` có thể chạy operation giống client đang sử dụng.

Ví dụ test query cũ và query mới:

```java
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest(ProductController.class)
class ProductControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    ProductCatalog products;

    @MockitoBean
    BrandQueryService brands;

    @Test
    void oldQueryStillWorksAfterAddingBrandLabel() {
        given(products.findById("p-101"))
            .willReturn(Optional.of(
                new ProductView("p-101", "Keyboard", "brand-1")
            ));

        graphQlTester.document("""
                query {
                    product(id: "p-101") {
                        id
                        name
                    }
                }
                """)
            .execute()
            .path("product.name")
            .entity(String.class)
            .isEqualTo("Keyboard");
    }

    @Test
    void newQueryCanReadBrandLabel() {
        given(products.findById("p-101"))
            .willReturn(Optional.of(
                new ProductView("p-101", "Keyboard", "brand-1")
            ));
        given(brands.displayName("brand-1"))
            .willReturn(Optional.of("Northwind"));

        graphQlTester.document("""
                query {
                    product(id: "p-101") {
                        id
                        brandLabel
                    }
                }
                """)
            .execute()
            .path("product.brandLabel")
            .entity(String.class)
            .isEqualTo("Northwind");
    }
}
```

Ví dụ dùng `@GraphQlTest` của Spring Boot 3.x và `@MockitoBean` của Spring Framework 6.2 trở lên. Với Spring Boot 4.x, package của `@GraphQlTest` chuyển sang `org.springframework.boot.graphql.test.autoconfigure`. Ở Spring Framework cũ hơn, có thể dùng `@MockBean` nếu phiên bản Spring Boot hỗ trợ annotation đó.

Test thứ nhất quan trọng vì nó chứng minh operation cũ vẫn hợp lệ sau khi schema được mở rộng. Test thứ hai chứng minh field mới có resolver và dữ liệu thực tế. Nên bổ sung test cho trường hợp `brandId` null hoặc brand không tồn tại để xác nhận semantics của nullable field.

## 17. Kiểm tra schema diff trong CI

Nên lưu SDL trong version control và kiểm tra thay đổi schema ở pull request. Schema diff có thể phát hiện:

- Field hoặc type bị xóa.
- Field đổi tên hoặc đổi kiểu.
- Output nullability thay đổi.
- Argument mới trở thành bắt buộc.
- Enum value bị xóa.
- Directive hoặc entity key thay đổi.
- Thay đổi Federation ownership làm composition thất bại.

Với hệ thống có registry, có thể chạy schema checks dựa trên operation usage để biết thay đổi có ảnh hưởng client đang hoạt động hay không. Tuy vậy, operation usage chỉ phản ánh traffic được ghi nhận; cần tính tới client offline, mobile app cũ, batch job và đối tác bên ngoài.

CI nên có tối thiểu:

1. Schema syntax/validation.
2. Schema compatibility diff.
3. Unit test resolver.
4. GraphQL contract test cho operation cũ.
5. Integration test cho field mới và các dependency dữ liệu.
6. Federation composition test nếu module là subgraph.

## 18. Theo dõi mức sử dụng field

Trước khi loại bỏ field cũ, cần biết client nào còn dùng nó. Có thể thu thập thông tin ở gateway hoặc GraphQL instrumentation:

- Operation name và operation signature/hash.
- Field được chọn trong operation.
- Số lần gọi và thời gian thực thi.
- Client/application identity nếu có cơ chế xác định đáng tin cậy.
- Phiên bản ứng dụng hoặc persisted operation identifier nếu client gửi kèm.

Tránh ghi toàn bộ variables hoặc dữ liệu nhạy cảm vào log chỉ để theo dõi usage. Metrics nên dùng nhãn có cardinality được kiểm soát; không dùng raw user ID hay toàn bộ query text làm metric tag.

Nếu không có field-level usage data, hãy dùng persisted operation registry, access log hoặc telemetry tại gateway để ước lượng phạm vi ảnh hưởng. Không thể kết luận một field không còn được dùng chỉ vì vài ngày không thấy request.

## 19. Thêm field mới có thể ảnh hưởng hiệu năng

Field mới không làm query cũ tự động tải thêm dữ liệu vì GraphQL chỉ thực thi field được chọn. Tuy nhiên, khi client mới chọn field đó, resolver có thể tăng số lần gọi database hoặc service ngoài.

Ví dụ query danh sách:

```graphql
query {
    products {
        id
        name
        brandLabel
    }
}
```

Nếu `brandLabel` gọi database một lần cho từng Product, query có thể tạo N+1. Dùng `@BatchMapping` hoặc DataLoader để gom brand ID và tải theo nhóm. Đặt giới hạn pagination và theo dõi latency của field mới sau phát hành.

Không thực hiện truy vấn ngoài hoặc tính toán đắt tiền trong resolver nếu field chưa được client yêu cầu. Resolver chỉ chạy khi field xuất hiện trong selection set, vì vậy cần giữ lazy execution đúng cách.

## 20. Thêm field mới có thể ảnh hưởng bảo mật

Field mới có thể làm lộ dữ liệu mà client trước đây không truy cập được. Kiểm tra authorization ở cấp field hoặc application service:

- Field có dữ liệu nhạy cảm hoặc nội bộ không?
- Người dùng có quyền đọc field này trên đúng resource không?
- Tenant/ownership có được kiểm tra không?
- Nếu không có quyền, API trả lỗi hay null? Hành vi có nhất quán với chính sách hiện tại không?
- DataLoader có cache theo request và phân vùng theo security context phù hợp không?

Việc thêm field không nên vô tình làm rộng quyền truy cập của một query vốn đã được cấp phép cho các field cũ.

## 21. Khi field mới không thể thêm vào type hiện tại

Đôi khi field mới có semantics khác hẳn hoặc chỉ áp dụng cho một số trường hợp. Có thể cân nhắc:

- Tạo object type lồng nhau để gom một nhóm thuộc tính.
- Thêm query mới chuyên biệt cho use case mới.
- Tạo input type mới nếu cấu trúc mutation đã thay đổi đáng kể.
- Dùng interface/union nếu response thực sự có nhiều biến thể.
- Giữ field cũ và thêm field mới trong giai đoạn migration.

Không nên nhồi field có ý nghĩa không liên quan vào một type chỉ để tránh thêm type mới. Schema cần diễn đạt domain rõ ràng và có khả năng tiến hóa.

## 22. Checklist trước khi phát hành field mới

- [ ] Field mới có tên và semantics rõ ràng.
- [ ] Output field nullable nếu dữ liệu hiện tại chưa bảo đảm luôn có giá trị.
- [ ] Input field hoặc argument mới không bắt buộc với client cũ.
- [ ] Resolver hoặc property fetcher trả đúng dữ liệu.
- [ ] Null, not-found và authorization có semantics rõ ràng.
- [ ] Field không gây N+1 hoặc chi phí không kiểm soát.
- [ ] Query cũ vẫn chạy trong contract test.
- [ ] Query mới trả đúng dữ liệu trong integration test.
- [ ] Schema diff và Federation composition (nếu có) đều pass.
- [ ] Tài liệu API và ví dụ client đã được cập nhật.
- [ ] Telemetry đủ để theo dõi field sau khi phát hành.

## 23. Lỗi thường gặp

**Thêm field non-null nhưng dữ liệu cũ không có giá trị.** Resolver trả null sẽ gây execution error và có thể làm null lan lên parent. Dùng nullable field hoặc backfill dữ liệu trước khi cam kết non-null.

**Chỉ sửa SDL mà không triển khai resolver.** Field xuất hiện trong schema nhưng không có dữ liệu. Kiểm tra property fetcher và `@SchemaMapping`.

**Thêm required argument vào field cũ.** Operation cũ không truyền argument sẽ fail validation. Dùng argument nullable hoặc có default.

**Thêm required input field.** Client cũ gửi input object thiếu field mới sẽ không hợp lệ. Bắt đầu bằng field optional hoặc default phù hợp.

**Thêm enum value mà không chuẩn bị client.** Client exhaustive switch có thể không xử lý giá trị mới. Bổ sung nhánh fallback và kiểm thử code generation.

**Thêm field vào interface nhưng quên implementation.** Các object type triển khai interface phải cập nhật để đáp ứng hợp đồng mới.

**Đánh dấu deprecated rồi xóa ngay.** Deprecation không chứng minh client đã migrate. Theo dõi usage và phối hợp thời gian hỗ trợ.

**Không kiểm tra field mới trong Federation.** Composition hoặc entity resolution có thể thất bại nếu ownership, key và resolver không nhất quán.

**Không theo dõi chi phí resolver.** Field mới có thể gây N+1, latency hoặc tải downstream khi client bắt đầu chọn nó.

## Kết luận

Để thêm field mà không phá client, hãy mở rộng schema theo hướng additive, giữ nguyên field cũ và chọn nullability phù hợp với dữ liệu thực tế. Với Spring for GraphQL, cập nhật SDL cùng resolver, kiểm thử cả operation cũ và mới bằng `GraphQlTester`, kiểm tra schema diff trong CI và theo dõi hiệu năng/usage sau phát hành. Các thay đổi liên quan input bắt buộc, argument required, enum, interface và union cần được đánh giá riêng vì chúng có thể tạo ra rủi ro tương thích dù nhìn bề ngoài chỉ là thêm một dòng schema.

## Tài liệu tham khảo

- [GraphQL — Schema Design](https://graphql.org/learn/schema-design/)
- [GraphQL — Schema Change Management](https://www.graphql.org/learn/governance-versioning/)
- [GraphQL — Review and Validate Schema Changes](https://www.graphql.org/learn/schema-review/)
- [GraphQL Specification — Type System and `@deprecated`](https://spec.graphql.org/September2026/#sec--deprecated)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Apollo — Schema Basics and Schema Evolution](https://www.apollographql.com/docs/apollo-server/schema/schema)
