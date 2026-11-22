# Schema composition

Khi một hệ thống GraphQL được chia thành nhiều service theo domain, mỗi service có thể sở hữu một phần schema và dữ liệu riêng. Ví dụ, Catalog quản lý sản phẩm, Inventory quản lý tồn kho, còn Shipping tính phí giao hàng. Client vẫn muốn truy vấn các thông tin này qua một GraphQL API thống nhất.

**Schema composition** là quá trình kết hợp các subgraph schema thành một supergraph schema. Supergraph chứa các type và field được đóng góp từ nhiều subgraph cùng metadata để router biết field nào do service nào resolve và cần gọi các service theo thứ tự nào.

Trong Spring for GraphQL, mỗi ứng dụng thường triển khai một subgraph. Spring tích hợp thư viện federation-jvm để tạo schema và xử lý entity request. Công việc composition thường do Apollo GraphOS hoặc Rover CLI thực hiện; Spring for GraphQL không tự thay thế router hay composition engine.

Bài này trình bày mô hình subgraph, supergraph và API schema; cách các type được hợp nhất; entity và field ownership; các directive Federation quan trọng; khác biệt Federation 1 và 2; cách compose bằng Rover; cách tích hợp subgraph Spring for GraphQL; kiểm tra thay đổi trong CI và xử lý lỗi composition.

## 1. Schema composition là gì?

Trong GraphQL thông thường, một server thường cung cấp một schema hoàn chỉnh. Trong kiến trúc federation, schema được chia thành nhiều phần độc lập:

- Subgraph schema: schema do một service hoặc một team sở hữu. Nó định nghĩa các type và field mà service có thể resolve.
- Supergraph schema: kết quả composition của tất cả subgraph. Ngoài type và field, nó chứa metadata federation để router lập kế hoạch gọi subgraph.
- API schema: schema công khai mà client nhìn thấy. Nó bỏ các chi tiết nội bộ chỉ phục vụ router như federation machinery và các field được đánh dấu không công khai.

~~~mermaid
flowchart TD
    A[Catalog subgraph SDL] --> D[Schema composition]
    B[Inventory subgraph SDL] --> D
    C[Shipping subgraph SDL] --> D
    D --> E[Supergraph schema]
    E --> F[GraphQL Router]
    F --> G[API schema exposed to clients]
    H[Client operation] --> F
    F --> A
    F --> B
    F --> C
~~~

Composition không đơn giản là nối các file SDL lại với nhau. Nó phải kiểm tra các định nghĩa có thể hợp nhất an toàn hay không, field nào được nhiều subgraph resolve, entity nào có thể được tham chiếu và dữ liệu nào cần lấy trước khi gọi resolver phụ thuộc.

Nếu hai subgraph định nghĩa cùng một field với kiểu trả về không tương thích, hoặc supergraph có một field mà không phải mọi đường truy vấn hợp lệ đều có thể resolve, composition sẽ thất bại.

## 2. Ví dụ domain gồm nhiều subgraph

Giả sử hệ thống thương mại điện tử có ba subgraph:

| Subgraph | Trách nhiệm | Field đóng góp cho Product |
|---|---|---|
| Catalog | Thông tin sản phẩm | id, name, price, weight |
| Inventory | Tồn kho | inStock |
| Shipping | Ước tính giao hàng | shippingEstimate |

Client muốn gửi một operation:

~~~graphql
query {
  product(id: "p-100") {
    id
    name
    price
    inStock
    shippingEstimate
  }
}
~~~

Catalog tìm sản phẩm. Inventory bổ sung field inStock cho cùng entity Product. Shipping tính shippingEstimate dựa trên weight do Catalog cung cấp.

Router đọc supergraph metadata để biết:

1. Gọi Catalog để lấy Product và các field cơ bản.
2. Chuyển representation của Product sang Inventory để lấy inStock.
3. Lấy weight nếu chưa có trong response và chuyển representation sang Shipping để tính shippingEstimate.
4. Ghép kết quả thành một GraphQL response duy nhất.

Client không cần biết các field đến từ ba service khác nhau.

## 3. Entity và value type khi composition

Composition cần phân biệt hai kiểu type quan trọng.

### Entity

Entity là object có định danh ổn định và có thể được tham chiếu từ nhiều subgraph. Directive @key khai báo tập field dùng để nhận diện một entity.

Ví dụ Catalog sở hữu Product:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String!
  price: Int!
  weight: Int!
}
~~~

Inventory cũng định nghĩa Product với cùng key nhưng chỉ đóng góp field tồn kho:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  inStock: Boolean!
}
~~~

Hai subgraph không cần định nghĩa toàn bộ field của Product giống nhau. Vì Product là entity, mỗi subgraph có thể đóng góp các field khác nhau miễn là khai báo key tương thích và các field có thể được resolve đúng theo quy tắc federation.

Trong runtime, router có thể gửi một entity representation chứa typename và key tới subgraph khác. Spring for GraphQL dùng @EntityMapping để nạp entity tương ứng từ representation.

### Value type

Value type là object không có định danh độc lập trong federation. Ví dụ Address có thể chỉ là một nhóm giá trị được nhúng trong Customer:

~~~graphql
type Address {
  street: String!
  city: String!
  postalCode: String!
}
~~~

Nếu nhiều subgraph định nghĩa cùng value type, composition phải bảo đảm mọi field trong type có thể được resolve trên mọi đường truy vấn hợp lệ. Một subgraph không thể đóng góp field mới vào value type rồi để subgraph khác trả về cùng type nhưng không thể resolve field đó.

Nếu type tương ứng với một bản ghi dữ liệu có ID ổn định và các domain cần bổ sung field độc lập, hãy cân nhắc biến nó thành entity.

## 4. Federation 2 và directive @link

Federation 2 yêu cầu subgraph khai báo specification federation bằng directive @link. Danh sách import chỉ ra directive nào được dùng trong SDL.

Ví dụ:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external", "@requires"]
  )
~~~

Nếu directive không được import, nó vẫn có thể được dùng dưới dạng tên đã namespace, chẳng hạn federation__shareable. Import tường minh thường giúp schema dễ đọc hơn.

Các điểm khác nhau đáng chú ý:

| Federation 1 | Federation 2 |
|---|---|
| Không dùng @link để opt in | Mỗi subgraph dùng @link để chọn Federation spec |
| Type extension và @extends được dùng phổ biến | GraphQL extend keyword được hỗ trợ trực tiếp; không bắt buộc @extends |
| Value type được xem là shareable theo quy tắc Federation 1 | Field object mặc định chỉ có một subgraph resolve, muốn chia sẻ phải khai báo @shareable |
| Ít công cụ hỗ trợ rollout field | Có @inaccessible và @override để hỗ trợ thay đổi từng bước |

Federation 2 không bắt buộc phải dùng @extends khi SDL hỗ trợ từ khóa extend của GraphQL. Directive @extends chủ yếu dành cho thư viện tạo schema bằng code mà không hỗ trợ từ khóa extend.

Hãy thống nhất phiên bản federation spec giữa các subgraph và phiên bản composition engine. Không sao chép directive chỉ có trong Federation 2.7 hoặc 2.9 vào subgraph đang dùng spec cũ mà chưa kiểm tra tính tương thích.

## 5. Các directive ảnh hưởng đến composition

Các directive Federation mô tả định danh entity, quyền resolve field và dependency giữa các subgraph.

| Directive | Phiên bản | Ý nghĩa |
|---|---|---|
| @link | Federation 2 | Khai báo Federation spec và import directive |
| @key | Federation 1+ | Khai báo field dùng để định danh entity |
| @external | Federation 1+ | Khai báo field được tham chiếu nhưng subgraph hiện tại không sở hữu việc resolve |
| @requires | Federation 1+ | Khai báo field từ subgraph khác cần được lấy trước khi resolve field hiện tại |
| @provides | Federation 1+ | Khai báo field entity mà subgraph có thể resolve tại một đường truy vấn cụ thể |
| @shareable | Federation 2 | Cho phép nhiều subgraph cùng resolve một field |
| @inaccessible | Federation 2 | Giữ định nghĩa trong supergraph nhưng ẩn khỏi API schema của client |
| @override | Federation 2 | Chuyển quyền resolve field từ subgraph cũ sang subgraph mới |
| @extends | Federation 1+ | Directive tương thích cho thư viện không hỗ trợ GraphQL type extension |

### 5.1. @key: xác định entity

Một entity có thể có một hoặc nhiều key. Ví dụ Product có thể được nhận diện bằng id hoặc sku:

~~~graphql
type Product
  @key(fields: "id")
  @key(fields: "sku") {
  id: ID!
  sku: String!
  name: String!
}
~~~

Key phải định danh duy nhất một instance entity. Key có thể chứa nhiều field hoặc field lồng nhau:

~~~graphql
type Product @key(fields: "sku region { code }") {
  sku: String!
  region: Region!
}
~~~

Chỉ khai báo key khi subgraph thực sự có thể nhận diện entity theo các field đó. Key không phải một field tùy ý để router chuyển dữ liệu; nó là hợp đồng định danh giữa các subgraph.

### 5.2. @external và @requires

Shipping cần weight của Product do Catalog sở hữu để tính shippingEstimate. Trong Shipping SDL:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external", "@requires"]
  )

type Product @key(fields: "id") {
  id: ID!
  weight: Int! @external
  shippingEstimate: Int!
    @requires(fields: "weight")
}
~~~

@external cho biết Shipping không sở hữu việc resolve weight. @requires cho router biết cần lấy weight từ subgraph có khả năng resolve field này trước khi gọi resolver shippingEstimate.

Resolver trong Shipping có thể nhận giá trị weight đã được router đưa vào representation:

~~~java
@Controller
public class ShippingController {

    @SchemaMapping
    public Integer shippingEstimate(Product product) {
        return calculateShipping(product.weight());
    }

    private Integer calculateShipping(Integer weight) {
        return weight * 2;
    }
}
~~~

Đoạn Java chỉ minh họa logic nghiệp vụ. Cách ánh xạ representation và entity cần được cấu hình theo Spring for GraphQL federation integration ở phần sau.

Field được liệt kê trong @requires phải được khai báo trong subgraph hiện tại và đánh dấu @external. Nếu thiếu, composition sẽ báo lỗi vì router không thể xác định dependency của field.

### 5.3. @provides: tối ưu tại một query path

Inventory thường không sở hữu Product.name, nhưng khi truy vấn danh sách sản phẩm hết hàng, Inventory có thể lấy được name từ nguồn dữ liệu cục bộ. @provides khai báo khả năng đó tại đúng field path:

Trong Catalog, field name phải được đánh dấu @shareable để cho biết ít nhất một subgraph khác cũng có thể resolve field này:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String! @shareable
}
~~~

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external", "@provides"]
  )

type Product @key(fields: "id") {
  id: ID!
  name: String! @external
  inStock: Boolean!
}

type Query {
  outOfStockProducts: [Product!]!
    @provides(fields: "name")
}
~~~

Inventory có thể resolve name cho Product trả về từ outOfStockProducts, nhưng không nhất thiết có thể resolve name ở mọi đường truy vấn Product khác.

@provides là tối ưu tùy chọn. Nó có thể giúp router tránh gọi thêm Catalog cho field được cung cấp ở query path đó. Chỉ khai báo khi resolver thực sự bảo đảm field có thể được trả về tại path tương ứng.

### 5.4. @shareable: cho phép nhiều subgraph resolve một field

Trong Federation 2, một field object mặc định được một subgraph resolve. Nếu nhiều subgraph có thể trả về cùng field với cùng ý nghĩa, hãy đánh dấu @shareable:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@shareable"]
  )

type CurrencyInfo @shareable {
  code: String!
  symbol: String!
}
~~~

Có thể đặt @shareable trên type để áp dụng cho các field trong định nghĩa đó, hoặc đặt trên từng field. Nếu một field được đánh dấu @shareable trong một subgraph, các subgraph Federation 2 khác định nghĩa field đó phải đánh dấu @shareable hoặc @external tương ứng.

Chỉ chia sẻ field khi các resolver có semantics tương đương. Nếu hai subgraph trả giá trị khác nhau cho cùng một field, router có thể chọn đường thực thi khác nhau và client nhận kết quả không nhất quán.

### 5.5. @inaccessible: rollout field theo từng bước

Khi thêm field vào value type được nhiều subgraph định nghĩa, cập nhật một subgraph trước có thể làm composition thất bại vì subgraph còn lại chưa thể resolve field mới.

Có thể đánh dấu field mới là @inaccessible trong giai đoạn rollout:

~~~graphql
type Address @shareable {
  city: String!
  postalCode: String!
  deliveryZone: String! @inaccessible
}
~~~

Router vẫn biết field deliveryZone trong supergraph, nhưng field đó không xuất hiện trong API schema công khai nên client chưa thể yêu cầu nó. Khi tất cả subgraph cần thiết đã cập nhật và có thể resolve field, có thể gỡ @inaccessible để công khai field.

@inaccessible cũng hữu ích khi một field nội bộ được dùng trong @key nhưng không nên xuất hiện trong API schema. Directive này không phải cơ chế phân quyền thay thế; nó chỉ điều khiển field có được đưa vào API schema hay không.

### 5.6. @override: chuyển field sang subgraph khác

Khi muốn di chuyển field từ subgraph cũ sang subgraph mới, @override khai báo subgraph mới nhận trách nhiệm resolve:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  inStock: Boolean! @override(from: "Catalog")
}
~~~

Giả sử trước đó Catalog resolve Product.inStock. Sau khi triển khai Inventory có resolver tương đương, Inventory khai báo @override(from: "Catalog"). Supergraph sẽ chuyển định tuyến field sang Inventory.

Tên trong from phải khớp chính xác tên subgraph đã khai báo trong supergraph configuration hoặc GraphOS. Chỉ một subgraph được override một field tại một thời điểm; khai báo nhiều nguồn override cho cùng field sẽ gây lỗi composition.

Federation 2.7 trở lên còn hỗ trợ progressive @override với label phần trăm traffic, cho phép chuyển dần lưu lượng và theo dõi trước khi hoàn tất migration. Hãy kiểm tra phiên bản Federation spec và router trước khi dùng tính năng này.

## 6. Các quy tắc composition cần nhớ

Composition engine kiểm tra nhiều quy tắc. Các lỗi phổ biến nhất liên quan đến field ownership, chữ ký field và khả năng resolve.

### 6.1. Không định nghĩa trùng field nếu không shareable

Trong Federation 2, nhiều subgraph không thể cùng định nghĩa một field object trừ khi field đó được đánh dấu @shareable. Nếu field chỉ do một subgraph resolve, subgraph khác có thể khai báo field đó là @external khi cần tham chiếu trong @requires hoặc @provides.

### 6.2. Field được chia sẻ phải có chữ ký tương thích

Các subgraph cùng resolve một field phải có kiểu trả về và kiểu argument tương thích. Ví dụ sau không thể compose:

~~~graphql
# Catalog
type Event @shareable {
  timestamp: String!
}

# Analytics
type Event @shareable {
  timestamp: Int!
}
~~~

Một subgraph trả String còn subgraph kia trả Int. Composition không thể chọn một định nghĩa duy nhất cho supergraph nên phải thất bại.

### 6.3. Field phải resolve được trên mọi đường truy vấn hợp lệ

Giả sử hai subgraph cùng định nghĩa value type Position:

~~~graphql
# Subgraph A
type Query {
  positionA: Position!
}

type Position @shareable {
  x: Int!
  y: Int!
}

# Subgraph B
type Query {
  positionB: Position!
}

type Position @shareable {
  x: Int!
  y: Int!
  z: Int!
}
~~~

Hai schema riêng lẻ hợp lệ, nhưng composition có thể thất bại. Supergraph hợp nhất Position với field z. Client có thể yêu cầu positionA.z, nhưng Subgraph A không có khả năng resolve z và Subgraph B không thể nhận diện instance Position được trả về từ positionA nếu type này không phải entity.

Có ba cách xử lý thường gặp:

1. Định nghĩa và resolve field z trong mọi subgraph định nghĩa Position. Subgraph không có dữ liệu có thể trả null nếu schema cho phép.
2. Đánh dấu field mới @inaccessible trong giai đoạn rollout, sau đó gỡ directive khi tất cả subgraph đã sẵn sàng.
3. Biến Position thành entity có @key nếu nó thực sự có định danh ổn định, để router có thể chuyển entity sang subgraph khác.

Không dùng @shareable chỉ để làm composition hết lỗi. @shareable khẳng định mọi subgraph được đánh dấu có thể resolve field đó một cách nhất quán.

### 6.4. Union và intersection khi hợp nhất type

Composition dùng hai chiến lược:

- Union: lấy tất cả thành phần được đóng góp từ các subgraph.
- Intersection: chỉ lấy thành phần được định nghĩa ở mọi subgraph liên quan.

| Thành phần schema | Chiến lược thường dùng |
|---|---|
| Object type | Union các field |
| Union type | Union các member type |
| Interface type | Union các field |
| Input object | Intersection các input field |
| Field arguments | Intersection các argument |

Ví dụ hai subgraph cùng định nghĩa User:

~~~graphql
# Accounts
type User @key(fields: "id") {
  id: ID!
  name: String!
}

# Profiles
type User @key(fields: "id") {
  id: ID!
  avatarUrl: String
}
~~~

Supergraph có thể chứa cả name và avatarUrl vì object type được hợp nhất theo union. Router dùng entity key để chuyển User từ Accounts sang Profiles khi cần lấy avatarUrl.

Ngược lại, input object và field arguments dùng intersection để router không gửi argument mà một subgraph không hiểu. Nếu intersection làm mất một input field hoặc argument non-null mà subgraph yêu cầu, composition sẽ thất bại.

Enum có quy tắc phụ thuộc cách sử dụng. Nếu enum chỉ là kiểu trả về, các value có thể được hợp nhất theo union. Nếu enum được dùng làm input hoặc argument, các value cần giao nhau để router không gửi giá trị subgraph không hỗ trợ. Nếu enum vừa được dùng làm output vừa làm input, các định nghĩa phải khớp nhau.

## 7. Thực hiện schema composition bằng Rover CLI

Apollo cung cấp hai cách phổ biến để composition:

- GraphOS managed composition: publish subgraph schema lên GraphOS. GraphOS tự compose các schema mới nhất và cập nhật supergraph nếu composition thành công.
- Local composition bằng Rover CLI: phù hợp với phát triển local, kiểm tra trước khi publish và pipeline CI.

### 7.1. Tạo supergraph.yaml

File cấu hình mô tả phiên bản Federation, routing URL và nguồn SDL của từng subgraph:

~~~yaml
federation_version: =2.3.2
subgraphs:
  catalog:
    routing_url: http://localhost:8081/graphql
    schema:
      file: ./schemas/catalog.graphql
  inventory:
    routing_url: http://localhost:8082/graphql
    schema:
      file: ./schemas/inventory.graphql
  shipping:
    routing_url: http://localhost:8083/graphql
    schema:
      file: ./schemas/shipping.graphql
~~~

Trong ví dụ, schema.file trỏ tới SDL đã export của từng subgraph. Rover cũng hỗ trợ lấy SDL qua introspection hoặc từ GraphOS graph reference. Routing URL là địa chỉ router sẽ dùng để gửi operation đến service tương ứng.

Phiên bản Federation trong file cấu hình cần tương thích với các directive mà SDL sử dụng. Không chọn version thấp hơn version cần thiết cho directive mới.

### 7.2. Chạy composition

Chạy lệnh:

~~~bash
rover supergraph compose --config ./supergraph.yaml
~~~

Để lưu kết quả thành artifact:

~~~bash
rover supergraph compose \
  --config ./supergraph.yaml \
  --output ./build/supergraph.graphql
~~~

File supergraph.graphql là schema nội bộ dành cho router/gateway. Không dùng file này làm schema công khai cho GraphQL client và không chỉnh sửa thủ công để sửa lỗi composition. Hãy sửa subgraph SDL hoặc directive rồi chạy composition lại.

Nếu composition thất bại, Rover trả về lỗi và không tạo supergraph mới hợp lệ. Đây là một bước build tương tự compile: router không nên được triển khai với schema composition lỗi.

### 7.3. Composition tự động với GraphOS

Trong managed federation, sau khi publish schema của một subgraph, GraphOS kết hợp phiên bản mới nhất của các subgraph. Nếu thành công, router có thể nhận supergraph mới theo cơ chế phân phối schema đã cấu hình.

Composition thất bại không đồng nghĩa phải xóa schema vừa publish khỏi registry. Registry có thể phản ánh schema subgraph đang chạy, trong khi supergraph/router vẫn giữ bản composition thành công trước đó. Cần xem trạng thái composition trong GraphOS và khắc phục xung đột trước khi triển khai tiếp.

## 8. Tích hợp Federation subgraph trong Spring for GraphQL

Spring for GraphQL tích hợp thư viện federation-jvm để khởi tạo GraphQL schema cho một subgraph. Khi dùng Spring Boot, khai báo FederationSchemaFactory và cấu hình GraphQlSourceBuilderCustomizer:

~~~java
@Configuration
public class FederationConfig {

    @Bean
    GraphQlSourceBuilderCustomizer federationCustomizer(
            FederationSchemaFactory factory) {
        return builder -> builder.schemaFactory(factory::createGraphQLSchema);
    }

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }
}
~~~

FederationSchemaFactory tạo schema có các thành phần federation cần thiết như _service và _entities. Khi cấu hình bằng Spring Boot, GraphQlSourceBuilderCustomizer cho phép thay schema factory mà vẫn giữ cơ chế tạo GraphQlSource của Boot.

Đây là cấu hình phía subgraph. Nó không compose nhiều service và không chạy router. Supergraph vẫn được tạo bởi GraphOS hoặc Rover CLI như phần trước.

### 8.1. Kiểm tra SDL được subgraph công bố

Subgraph cung cấp field _service để router hoặc công cụ federation lấy SDL:

~~~graphql
query {
  _service {
    sdl
  }
}
~~~

SDL trả về cần chứa các directive Federation và type extension mà composition engine cần. Khi debug composition, kiểm tra SDL thực tế do service công bố thay vì chỉ đọc file schema trong source code, vì runtime wiring hoặc schema factory có thể làm thay đổi schema cuối cùng.

### 8.2. Resolve entity trong Spring

Router gọi field _entities với danh sách representation. Spring for GraphQL ánh xạ mỗi representation tới method @EntityMapping:

~~~java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @EntityMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }
}
~~~

Tham số @Argument được lấy từ representation map. Method cũng có thể nhận toàn bộ Map<String, Object>, danh sách representation khi batch load, GraphQLContext hoặc DataLoader tùy nhu cầu.

Các field khác của Product tiếp tục được resolve bằng @SchemaMapping. Nếu cần nạp nhiều entity cùng lúc, có thể nhận danh sách key và trả danh sách entity theo đúng thứ tự, hoặc dùng @BatchMapping và DataLoader để giảm số lần truy cập dữ liệu.

Composition thành công không bảo đảm entity resolver chạy đúng. Cần kiểm thử riêng cả schema contract, entity lookup và các field được đóng góp.

## 9. Kiểm tra schema thay đổi trong CI

Composition nên là một bước kiểm tra bắt buộc trước khi publish schema. Có thể kết hợp hai cấp validation:

1. Local composition kiểm tra các subgraph SDL có thể tạo thành supergraph.
2. GraphOS schema checks kiểm tra thay đổi có phá vỡ operation đang được client sử dụng hay không.

Ví dụ kiểm tra một subgraph đã đăng ký trong GraphOS:

~~~bash
rover subgraph check commerce@current \
  --name catalog \
  --schema ./schemas/catalog.graphql
~~~

Lệnh cần graph reference, tên subgraph và SDL mới. Build check xác minh schema có thể compose với các subgraph còn lại. Operations check so sánh thay đổi với operation metrics đã thu thập để phát hiện field hoặc type đang được client sử dụng nhưng bị xóa hay thay đổi không tương thích.

Linter check có thể phát hiện vấn đề về quy ước và best practices. Nếu GraphOS không có operation metrics để so sánh, các thay đổi có khả năng phá vỡ client có thể bị đánh giá là không an toàn. Hãy cấu hình gửi operation metrics trước khi phụ thuộc vào operations checks.

### Pipeline gợi ý

~~~mermaid
flowchart TD
    A[Pull request thay đổi subgraph SDL] --> B[Validate GraphQL SDL]
    B --> C[rover subgraph check]
    C --> D{Composition và checks pass?}
    D -- No --> E[Trả lỗi cho pull request]
    D -- Yes --> F[Build và test subgraph]
    F --> G[Deploy subgraph]
    G --> H[Đợi replicas sẵn sàng]
    H --> I[Publish subgraph SDL]
    I --> J[GraphOS compose supergraph]
    J --> K[Router nhận schema mới]
~~~

Nên publish schema sau khi các replica của subgraph đã chạy phiên bản code tương ứng. Nếu publish SDL mới trước khi resolver mới được triển khai, router có thể gửi operation tới subgraph chưa có field hoặc entity resolver cần thiết.

Một lần schema check thành công không loại bỏ hoàn toàn race condition. Subgraph khác có thể thay đổi trong lúc pipeline đang chạy. Vì vậy, GraphOS vẫn cần thực hiện composition khi publish và pipeline phải xử lý trạng thái composition thất bại.

## 10. Những lỗi composition thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field được định nghĩa ở nhiều subgraph | Chưa đánh dấu @shareable hoặc chưa xác định ownership | Chọn một owner hoặc khai báo shareable nếu resolver thực sự tương đương |
| Shared field có kiểu trả về khác nhau | SDL của các subgraph không tương thích | Thống nhất scalar, nullability, list shape và arguments |
| Field của value type không resolve được | Một subgraph đóng góp field mà subgraph khác không thể resolve | Dùng entity, triển khai field ở mọi subgraph hoặc rollout bằng @inaccessible |
| @requires báo field không hợp lệ | Field dependency chưa khai báo hoặc chưa đánh dấu @external | Khai báo field external và kiểm tra FieldSet |
| @provides không compose | Field không external, không shareable ở subgraph khác hoặc không thể resolve tại path đó | Kiểm tra ownership và đường truy vấn cung cấp field |
| Không nhận directive Federation 2 | Thiếu @link hoặc thiếu directive trong import | Thêm @link và import directive cần dùng |
| @override không tìm thấy nguồn | Giá trị from không khớp tên subgraph | So khớp với tên trong supergraph.yaml hoặc GraphOS |
| Entity không được router chuyển tới subgraph | Thiếu @key hoặc key không tương thích | Khai báo key ổn định và resolver entity |
| Input field hoặc argument biến mất sau composition | Các subgraph định nghĩa không giống nhau; composition dùng intersection | Đồng bộ input fields và arguments, đặc biệt là non-null |
| Supergraph compose thành công nhưng request lỗi | Resolver, entity mapping hoặc service runtime chưa triển khai đúng | Kiểm thử _entities và query qua router |
| GraphOS không cập nhật router | Composition mới thất bại hoặc launch chưa hoàn tất | Kiểm tra composition result và trạng thái launch |

## 11. Checklist kiểm thử schema composition

Trước khi chấp nhận thay đổi schema:

1. Mỗi subgraph có SDL hợp lệ và đúng Federation version.
2. Federation 2 subgraph có @link và import đủ directive đang sử dụng.
3. Mỗi entity có @key ổn định và các subgraph tham gia có thể nhận diện key.
4. Field có owner rõ ràng; field trùng chỉ được chia sẻ khi có @shareable phù hợp.
5. Field @requires có khai báo @external và dữ liệu dependency thực sự có sẵn.
6. Field @provides chỉ xuất hiện tại path mà subgraph có thể resolve.
7. Input types và arguments tương thích giữa các subgraph.
8. Field mới của value type được rollout an toàn.
9. @override trỏ đúng tên subgraph nguồn và chỉ có một subgraph nhận override.
10. Rover supergraph compose hoặc GraphOS build check thành công.
11. Operations checks không phát hiện client operation bị phá vỡ ngoài dự kiến.
12. Subgraph trả SDL đúng qua _service.sdl.
13. Entity lookup qua _entities hoạt động với representation thực tế.
14. Query end-to-end qua router trả về field từ tất cả subgraph.
15. Code resolver đã được deploy trước khi schema mới được publish.

Composition xác nhận schema có thể kết hợp về mặt cấu trúc. Nó không thay thế integration test, kiểm thử authorization, performance test hoặc kiểm tra dữ liệu thực tế của các subgraph.

## 12. Quy trình thiết kế và rollout schema

Khi thêm hoặc di chuyển field trong federated graph:

1. Xác định domain nào sở hữu dữ liệu và resolver của field.
2. Quyết định field thuộc entity hay value type.
3. Nếu là entity, xác định key ổn định và resolver entity ở từng subgraph.
4. Nếu field được nhiều subgraph resolve, đánh giá semantics trước khi dùng @shareable.
5. Nếu field phụ thuộc dữ liệu từ subgraph khác, mô tả dependency bằng @external và @requires.
6. Chỉ dùng @provides khi subgraph có thể cung cấp field tại một query path cụ thể.
7. Dùng @inaccessible để rollout field mới theo từng bước nếu cần.
8. Dùng @override khi chuyển quyền resolve field và theo dõi migration.
9. Chạy composition và schema checks trong CI.
10. Deploy code và resolver trước, sau đó publish SDL tương ứng.
11. Kiểm tra query plan và trace ở router để xác nhận số lần gọi subgraph hợp lý.
12. Gỡ directive tạm thời sau khi rollout hoàn tất và chạy composition lại.

Schema composition là bước hợp nhất và kiểm tra hợp đồng giữa các subgraph. Apollo Federation dùng directive để mô tả entity identity, field ownership, shared field và dependency; composition engine tạo supergraph để router định tuyến operation. Spring for GraphQL triển khai phần subgraph bằng FederationSchemaFactory, @EntityMapping và các resolver thông thường. Kết hợp composition với schema checks, integration tests và rollout có kiểm soát giúp các team phát triển schema độc lập mà vẫn duy trì một GraphQL API thống nhất.

## Tài liệu tham khảo

- Spring for GraphQL — Federation: https://docs.spring.io/spring-graphql/reference/federation.html
- Apollo Federation — Schema Composition: https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/composition
- Apollo Federation — Composition Rules: https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/composition-rules
- Apollo Federation — Directives: https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives
- Apollo Rover — Supergraph Commands: https://www.apollographql.com/docs/rover/commands/supergraphs
- Apollo GraphOS — Schema Checks: https://www.apollographql.com/docs/graphos/platform/schema-management/checks
