# Triển khai schema nhiều module

Khi một ứng dụng Spring for GraphQL phát triển, schema SDL thường lớn dần theo số domain và nhóm phát triển. Đặt toàn bộ type, query, mutation và input trong một file khiến việc review khó hơn, làm tăng xung đột khi nhiều team cùng sửa và khiến ranh giới sở hữu dữ liệu không rõ ràng.

Có thể chia schema thành nhiều file và nhiều module Java, sau đó hợp nhất chúng khi ứng dụng khởi động. Mỗi module sở hữu phần SDL và resolver của domain mình; Spring Boot tìm các resource trên runtime classpath, Spring for GraphQL đưa chúng vào cùng một schema và GraphQL Java kiểm tra schema hợp nhất.

Bài này trình bày cách tổ chức SDL theo feature/domain, mở rộng root type bằng type extension, cấu hình Spring Boot để quét schema trong các dependency JAR, phối hợp DataFetcher và annotated controller từ nhiều module, kiểm tra schema khi build và triển khai. Ví dụ sử dụng một ứng dụng dạng modular monolith: Catalog, Orders và Inventory cùng chạy trong một Spring Boot application và công bố một GraphQL endpoint.

## 1. Hiểu đúng về schema nhiều module

Schema nhiều module có hai lớp tổ chức:

- **Nhiều file SDL:** chia một schema logic thành các file nhỏ theo domain hoặc feature.
- **Nhiều module build:** mỗi Gradle/Maven module có thể đóng gói SDL và Java code của domain vào JAR riêng. Ứng dụng GraphQL phụ thuộc các module này ở runtime.

Khi ứng dụng khởi động, các SDL resource được tìm thấy sẽ được parse và hợp nhất thành một GraphQLSchema. Client vẫn nhìn thấy một API GraphQL thống nhất. Thư mục SDL hoặc tên Gradle module không tạo ra namespace GraphQL riêng.

~~~mermaid
flowchart TD
    A[Catalog module] --> D[Runtime classpath]
    B[Orders module] --> D
    C[Inventory module] --> D
    D --> E[Spring Boot schema resource scanning]
    E --> F[Merge SDL definitions and extensions]
    F --> G[GraphQLSchema]
    H[RuntimeWiringConfigurer beans] --> I[RuntimeWiring]
    J[Annotated controllers] --> I
    I --> K[Executable schema]
    G --> K
    K --> L[GraphQL endpoint]
~~~

Điều này khác với Apollo Federation. Các module trong bài được nạp vào cùng một tiến trình và hợp thành một schema tại startup. Nếu Catalog, Orders và Inventory là các service triển khai độc lập, mỗi service sở hữu endpoint riêng, việc quét classpath không thể hợp nhất schema từ các service từ xa; khi đó cần một kiến trúc gateway/federation hoặc cơ chế schema registry phù hợp.

## 2. Chia SDL theo domain và feature

Hãy chọn ranh giới file theo phần nghiệp vụ mà một nhóm có thể sở hữu và thay đổi độc lập. Ví dụ:

~~~text
src/main/resources/
└── graphql/
    ├── common/
    │   ├── scalars.graphqls
    │   └── pagination.graphqls
    ├── catalog/
    │   ├── catalog.graphqls
    │   └── product-search.graphqls
    ├── orders/
    │   └── orders.graphqls
    └── inventory/
        └── inventory.graphqls
~~~

Trong một Gradle multi-project build, các resource có thể nằm trong từng module:

~~~text
catalog/
└── src/main/
    ├── java/com/acme/catalog/...
    └── resources/graphql/catalog/catalog.graphqls

orders/
└── src/main/
    ├── java/com/acme/orders/...
    └── resources/graphql/orders/orders.graphqls

inventory/
└── src/main/
    ├── java/com/acme/inventory/...
    └── resources/graphql/inventory/inventory.graphqls

app/
└── src/main/resources/application.yml
~~~

Tên thư mục giúp người đọc nhận ra domain sở hữu file. Tất cả type vẫn thuộc cùng GraphQL type system sau khi hợp nhất; vì vậy tên type, field, enum, input và directive phải duy nhất trong schema cuối cùng.

### 2.1. Một module sở hữu định nghĩa gốc

Ví dụ Catalog sở hữu định nghĩa Product và phần Query gốc:

~~~graphql
type Query {
  product(id: ID!): Product
  products: [Product!]!
}

type Product {
  id: ID!
  name: String!
  price: Float!
}
~~~

Orders sở hữu Order và Mutation gốc. Module này có thể bổ sung một query vào Query đã được Catalog định nghĩa:

~~~graphql
extend type Query {
  order(id: ID!): Order
}

type Mutation {
  placeOrder(input: PlaceOrderInput!): Order!
}

input PlaceOrderInput {
  productId: ID!
  quantity: Int!
}

type Order {
  id: ID!
  status: String!
  quantity: Int!
}
~~~

Inventory bổ sung các field thuộc trách nhiệm tồn kho:

~~~graphql
extend type Query {
  lowStockProducts: [Product!]!
}

extend type Product {
  inventory: InventorySummary!
}

type InventorySummary {
  available: Int!
  reserved: Int!
}
~~~

Kết quả hợp nhất có một type Query chứa product, products, order và lowStockProducts; một type Mutation chứa placeOrder; và một type Product có thêm field inventory. Mỗi module chỉ định nghĩa type gốc mà nó sở hữu một lần. Module khác dùng extend type để đóng góp field vào type đã tồn tại.

Trong ví dụ trên, schema dùng tên root convention mặc định Query và Mutation, nên không cần khai báo schema definition riêng. Nếu ứng dụng dùng tên root tùy chỉnh, khai báo schema definition một lần trong file nền tảng và bảo đảm tất cả root type được tham chiếu đều có định nghĩa trong tập SDL hợp nhất.

### 2.2. Dùng type extension đúng cách

GraphQL SDL hỗ trợ:

- extend type Query để thêm query field.
- extend type Mutation để thêm mutation field.
- extend type Subscription để thêm subscription field.
- extend type Product để bổ sung field vào object type do domain khác sở hữu.
- extend interface hoặc union khi cần mở rộng type trừu tượng theo quy tắc GraphQL.

Type được mở rộng phải có định nghĩa gốc trong tập schema. Ví dụ extend type Product sẽ lỗi nếu module Catalog không nằm trên runtime classpath hoặc không cung cấp type Product.

Không tạo nhiều định nghĩa type Query, type Product hoặc type Mutation trong các file độc lập. Chọn một module sở hữu định nghĩa gốc; các module còn lại đóng góp bằng extension. Tránh khai báo lại field đã tồn tại trong extension, vì một field chỉ nên có một định nghĩa rõ ràng về kiểu trả về, argument và nullability.

## 3. Đóng gói schema trong Gradle multi-module

Mỗi module Java thông thường có thể đóng gói SDL trong JAR bằng source set resources mặc định. Không cần plugin GraphQL riêng chỉ để đưa file .graphqls vào JAR.

Ví dụ cấu hình dependency của ứng dụng:

~~~gradle
// app/build.gradle
dependencies {
    implementation(project(":catalog"))
    implementation(project(":orders"))
    implementation(project(":inventory"))

    implementation("org.springframework.boot:spring-boot-starter-graphql")
}
~~~

Nếu một module chỉ chứa SDL và không có Java type cần tham chiếu lúc compile, có thể khai báo nó là runtime dependency:

~~~gradle
dependencies {
    runtimeOnly(project(":shared-graphql-schema"))
}
~~~

Điều quan trọng là JAR chứa schema phải có mặt trên runtime classpath của ứng dụng GraphQL. Nếu module không được khai báo trong dependency graph, resource của nó sẽ không được Spring Boot tìm thấy.

Kiểm tra resource đã được đóng gói vào JAR của module:

~~~bash
./gradlew :catalog:jar
jar tf catalog/build/libs/catalog-1.0.0.jar | grep graphql/
~~~

Trên PowerShell có thể lọc kết quả bằng:

~~~powershell
jar tf catalog/build/libs/catalog-1.0.0.jar | Select-String 'graphql/'
~~~

Với Spring Boot executable JAR, dependency module thường nằm trong BOOT-INF/lib dưới dạng JAR lồng nhau. Hãy kiểm tra JAR của từng module và kiểm thử ứng dụng đã đóng gói để xác nhận các resource được phát hiện trên runtime classpath.

## 4. Cấu hình Spring Boot quét schema từ nhiều module

Spring Boot mặc định tìm file có phần mở rộng .graphqls hoặc .gqls dưới classpath:graphql/**. Với schema nằm trong nhiều dependency JAR, cần dùng prefix classpath* để tìm resource ở tất cả classpath location phù hợp.

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath*:graphql/**/
      file-extensions: .graphqls,.gqls
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.graphql.schema.locations | Vị trí Spring Boot tìm SDL resource |
| classpath*:graphql/**/ | Tìm thư mục graphql trong nhiều classpath location, bao gồm dependency JAR |
| spring.graphql.schema.file-extensions | Các phần mở rộng được xem là schema file |

Ở phiên bản Spring Boot có hỗ trợ schema mapping inspection, có thể bật thêm:

~~~yaml
spring:
  graphql:
    schema:
      inspection:
        enabled: true
~~~

Hãy kiểm tra application properties của đúng phiên bản Spring Boot đang dùng trước khi thêm thuộc tính tùy chọn này.

Khác biệt quan trọng:

- classpath: thường trỏ tới resource trong một classpath location.
- classpath*: cho phép Spring ResourcePatternResolver tìm các resource phù hợp trên nhiều classpath location.

Nếu chỉ chạy được khi SDL đặt trong app/src/main/resources nhưng mất type khi chuyển SDL vào module dependency, hãy kiểm tra prefix classpath*. Đồng thời xác nhận module dependency có trong runtime classpath và JAR chứa đúng đường dẫn graphql/.

Spring Boot tìm resource theo pattern và phần mở rộng đã cấu hình. Tên thư mục catalog, orders hay inventory chỉ có ý nghĩa tổ chức; chúng không tự động tạo schema riêng hoặc giới hạn phạm vi type.

## 5. Spring for GraphQL hợp nhất resource và runtime wiring

GraphQlSource là abstraction của Spring for GraphQL để cung cấp GraphQL instance. Builder mặc định có thể nhận một hoặc nhiều Spring Resource, parse chúng và hợp nhất thành schema logic trước khi tạo executable GraphQLSchema.

Khi dùng Spring Boot starter, auto-configuration tạo GraphQlSource builder, nạp schema resource theo cấu hình, phát hiện RuntimeWiringConfigurer và Instrumentation bean, sau đó tạo schema. Vì vậy, ứng dụng thông thường chỉ cần cấu hình locations và khai báo các module dependency.

Nếu cần tự tạo GraphQlSource trong một cấu hình đặc biệt, builder có thể nhận nhiều resource:

~~~java
GraphQlSource.Builder builder = GraphQlSource.schemaResourceBuilder()
        .schemaResources(catalogSchema, ordersSchema, inventorySchema)
        .configureRuntimeWiring(runtimeWiringConfigurer);
~~~

Đây là minh họa cho API builder khi bạn đã có các Resource tương ứng. Trong ứng dụng Spring Boot, ưu tiên để Boot tự tìm resource theo classpath pattern. Chỉ tự thay thế GraphQlSource khi thật sự cần kiểm soát nguồn schema hoặc schema creation; nếu tự khai báo GraphQlSource bean, cần chịu trách nhiệm cho toàn bộ cấu hình mà auto-configuration trước đó cung cấp.

### 5.1. Cơ chế merge ở GraphQL Java

GraphQL Java parse mỗi SDL thành TypeDefinitionRegistry. Nhiều registry có thể được merge vào một registry trước khi SchemaGenerator tạo GraphQLSchema:

~~~java
SchemaParser parser = new SchemaParser();
TypeDefinitionRegistry registry = new TypeDefinitionRegistry();

for (Resource resource : schemaResources) {
    try (InputStream input = resource.getInputStream()) {
        registry.merge(parser.parse(input));
    }
}

GraphQLSchema schema = new SchemaGenerator()
        .makeExecutableSchema(registry, runtimeWiring);
~~~

Đoạn code minh họa cơ chế merge ở mức GraphQL Java. Trong ứng dụng Spring for GraphQL, GraphQlSource.Builder.schemaResources(...) đảm nhận việc nạp và hợp nhất resource; bạn không cần tự parse từng file nếu không có yêu cầu tùy biến riêng.

Việc merge không biến các file thành những schema độc lập. GraphQL Java kiểm tra toàn bộ type reference, root operation, field, argument, directive và scalar trên registry chung. Một type được tham chiếu trong module Inventory phải có định nghĩa hợp lệ trong toàn bộ tập SDL mà ứng dụng nạp.

## 6. Mỗi module quản lý resolver của domain mình

SDL chỉ mô tả contract. Nó không tự kết nối field với service hoặc repository. Mỗi module cần đăng ký DataFetcher tương ứng thông qua annotated controller hoặc RuntimeWiringConfigurer.

Catalog có thể dùng controller cho query product:

~~~java
@Controller
public class CatalogGraphQlController {

    private final CatalogService catalogService;

    public CatalogGraphQlController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return catalogService.findById(id);
    }
}
~~~

Inventory sở hữu resolver cho field inventory được thêm vào Product:

~~~java
@Controller
public class InventoryGraphQlController {

    private final InventoryService inventoryService;

    public InventoryGraphQlController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @SchemaMapping(typeName = "Product", field = "inventory")
    public InventorySummary inventory(Product product) {
        return inventoryService.getSummary(product.id());
    }
}
~~~

Orders có thể đăng ký mutation:

~~~java
@Controller
public class OrdersGraphQlController {

    private final OrderService orderService;

    public OrdersGraphQlController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order placeOrder(@Argument PlaceOrderInput input) {
        return orderService.place(input);
    }
}
~~~

Spring for GraphQL phát hiện controller và đăng ký các method được annotate thành DataFetcher. Khi các module được đóng gói thành dependency JAR, cần bảo đảm package controller của chúng nằm trong component scan hoặc được import rõ ràng. Resource SDL có thể được nạp thành công trong khi controller chưa được Spring tạo bean; hai bước này phải được kiểm tra riêng.

Trong ví dụ, Product là kiểu Java dùng chung giữa Catalog và Inventory. Nên đặt projection/contract này trong module API dùng chung, chẳng hạn catalog-api hoặc graphql-contract, để Inventory chỉ phụ thuộc vào kiểu cần thiết cho resolver. Nếu Product nằm trực tiếp trong module Catalog, Inventory phải có compile dependency tới module chứa Product; tránh kéo cả implementation persistence của Catalog chỉ để nhận source object.

### 6.1. RuntimeWiringConfigurer từ nhiều module

Các module cũng có thể đóng góp RuntimeWiringConfigurer bean để đăng ký custom scalar, directive, TypeResolver hoặc DataFetcher cấp thấp:

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogGraphQlConfiguration {

    @Bean
    RuntimeWiringConfigurer catalogRuntimeWiring() {
        return builder -> builder.scalar(CatalogScalars.money());
    }
}
~~~

Spring Boot phát hiện các bean RuntimeWiringConfigurer và áp dụng chúng vào GraphQlSource builder. Có thể để mỗi module đăng ký một configurer riêng, miễn là configuration class của module được component scan hoặc import vào application context.

Thông thường nên dùng @QueryMapping, @MutationMapping, @SchemaMapping và @BatchMapping cho resolver nghiệp vụ. RuntimeWiringConfigurer phù hợp với thành phần dùng chung hoặc những trường hợp cần API GraphQL Java ở mức thấp.

Không để hai module cùng đăng ký DataFetcher cho cùng một tọa độ type/field nếu không có chủ đích rõ ràng. Nếu nhiều module cùng đóng góp vào một object type, hãy chia các field bằng SDL extension và giao mỗi field cho một resolver owner.

## 7. Quy tắc thiết kế để schema không xung đột

| Quy tắc | Lý do |
|---|---|
| Mỗi object/input/enum/scalar có một định nghĩa gốc | Tránh trùng type name khi merge |
| Chỉ một module định nghĩa gốc cho Query, Mutation và Subscription | Giữ ownership của root type rõ ràng |
| Module khác dùng extend type để thêm field | Tránh định nghĩa lại root hoặc object type |
| Không định nghĩa lại field đã có | Tránh xung đột kiểu, argument và nullability |
| Dùng tên type có ý nghĩa domain và nhất quán | Tránh hai module vô tình tạo type cùng tên |
| Đặt shared scalar, enum và input contract trong module dùng chung | Tránh nhiều bản định nghĩa lệch nhau |
| Giữ quan hệ dependency module có hướng | Tránh vòng phụ thuộc giữa domain |
| Kiểm thử schema hợp nhất trong application context | Xác nhận resource và resolver cùng được nạp |

### 7.1. Cẩn thận với type extension

Một extension có thể tham chiếu type được định nghĩa trong resource khác. Tuy nhiên, type gốc phải có mặt trong registry cuối cùng. Ví dụ:

- inventory.graphqls mở rộng Product.
- Product phải được định nghĩa trong một resource mà ứng dụng thực sự nạp.
- Nếu module catalog bị bỏ khỏi runtime dependency, schema creation sẽ thất bại do Product không tồn tại.

Tương tự, nếu module payments mở rộng Mutation thì phải có một type Mutation gốc ở đâu đó. Nếu không có, schema extension không thể tạo root mutation type từ hư không.

### 7.2. Shared contract và phụ thuộc giữa domain

Không phải mọi quan hệ dữ liệu đều nên được biểu diễn bằng cách mở rộng type của module khác. Khi field thực sự là một phần của API object, type extension là cách phù hợp. Nếu một domain chỉ cần tham chiếu tới domain khác, có thể dùng ID hoặc một object reference rõ ràng để tránh phụ thuộc sâu.

Ví dụ Inventory mở rộng Product bằng inventory summary là hợp lý nếu API muốn client truy vấn tồn kho ngay dưới Product. Nhưng Catalog không nên phải phụ thuộc vào implementation của InventoryService. Resolver của Inventory chịu trách nhiệm lấy dữ liệu tồn kho, còn Catalog chỉ sở hữu Product contract.

## 8. Những lỗi thường gặp khi triển khai schema nhiều module

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Chỉ schema trong app module được nạp | Đang dùng classpath: thay vì classpath*: | Đổi locations sang classpath*:graphql/**/ và kiểm tra dependency |
| Không tìm thấy type được module khác tham chiếu | Module không nằm trong runtime classpath hoặc JAR thiếu resource | Kiểm tra Gradle dependency và nội dung JAR |
| Lỗi duplicate type definition | Nhiều file cùng định nghĩa type gốc | Chọn một owner; file còn lại dùng extend type |
| Lỗi unknown type trong extension | Type gốc chưa được nạp hoặc viết sai tên | Kiểm tra resource chứa type gốc và spelling |
| Mutation root không tồn tại | Chưa có type Mutation gốc hoặc schema definition không khai báo mutation root | Thêm định nghĩa root đúng một lần |
| Query field có trong introspection nhưng luôn null | SDL được nạp nhưng chưa có resolver/property tương ứng | Kiểm tra controller, DataFetcher và source object |
| Controller module không được phát hiện | Package ngoài phạm vi component scan hoặc thiếu @Import | Điều chỉnh component scan hoặc import cấu hình module |
| Hai module tranh cùng resolver | Trùng DataFetcher mapping cho cùng type/field | Xác định một owner và gỡ đăng ký trùng |
| Chạy local được nhưng chạy JAR thiếu schema | Resource bị loại khỏi artifact hoặc dependency chỉ có ở test/runtime không đúng | Kiểm tra JAR module và runtime dependency của app |
| Thêm file mới nhưng schema không thay đổi | File sai extension hoặc nằm ngoài locations pattern | Kiểm tra .graphqls/.gqls và schema.locations |

## 9. Kiểm thử schema sau khi hợp nhất

Kiểm thử từng resolver riêng lẻ chưa đủ. Cần ít nhất một integration test khởi tạo application context với toàn bộ module dependency để xác nhận Spring Boot tìm thấy mọi SDL resource và GraphQL schema được tạo thành công.

Thêm thư viện test:

~~~gradle
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Có thể dùng ExecutionGraphQlServiceTester để kiểm thử trực tiếp server execution mà không cần mở HTTP port:

~~~java
@SpringBootTest
class ModularSchemaIntegrationTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    private ExecutionGraphQlServiceTester tester;

    @BeforeEach
    void setUp() {
        tester = ExecutionGraphQlServiceTester.create(executionGraphQlService);
    }

    @Test
    void shouldResolveFieldsContributedByDifferentModules() {
        tester.document("""
                query {
                  product(id: "p-100") {
                    id
                    inventory {
                      available
                    }
                  }
                }
                """)
                .execute()
                .path("product", product -> product
                        .path("id").entity(String.class).isEqualTo("p-100")
                        .path("inventory.available").entity(Integer.class).isEqualTo(12));
    }
}
~~~

Test này xác nhận một operation đi qua Query field do Catalog sở hữu và field inventory do Inventory mở rộng Product. Nó cũng xác nhận SDL và controller của các module cùng tham gia một schema runtime.

Nên bổ sung các kiểm tra:

1. Application context khởi động được khi có đủ module dependency.
2. Query field từ từng domain hoạt động.
3. Field được thêm qua extend type có resolver tương ứng.
4. Mutation root và mutation field từ module sở hữu hoạt động.
5. Interface/union, scalar và directive dùng chung được wiring đúng.
6. Schema inspection không phát hiện mapping bị thiếu ngoài dự kiến.
7. Test với executable JAR để xác nhận resource từ dependency JAR có mặt ở runtime.

Nếu cần kiểm tra cả transport HTTP, dùng HttpGraphQlTester với WebTestClient. ExecutionGraphQlServiceTester kiểm tra execution ở server side; nó không kiểm tra HTTP routing, header hoặc WebGraphQlInterceptor.

## 10. Kiểm tra schema trong CI và khi triển khai

Schema nhiều module cần được xác minh ở cả compile/build time lẫn application startup:

~~~mermaid
flowchart TD
    A[Thay đổi SDL hoặc resolver trong module] --> B[Build module JAR]
    B --> C[Kiểm tra resource trong JAR]
    C --> D[Build application với dependency graph đầy đủ]
    D --> E[Khởi tạo Spring context và merge schema]
    E --> F{Schema và mapping hợp lệ?}
    F -- No --> G[Fail CI, sửa SDL hoặc wiring]
    F -- Yes --> H[Chạy GraphQlTester integration tests]
    H --> I[Build executable JAR hoặc image]
    I --> J[Deploy application]
    J --> K[Kiểm tra startup health và GraphQL smoke query]
~~~

Các bước nên có trong pipeline:

- Build các module đóng góp SDL và xác nhận resource được đóng gói.
- Build ứng dụng GraphQL với đúng runtime dependencies.
- Khởi tạo application context để phát hiện lỗi parse, merge và schema generation.
- Chạy integration test qua GraphQlTester cho field đến từ nhiều module.
- Chạy schema compatibility check nếu API có client hoặc consumer bên ngoài.
- Build và kiểm tra executable JAR/container image trước khi triển khai.

Spring for GraphQL tạo schema khi application khởi động. Nếu một module resource bị thiếu, schema có thể lỗi ngay lúc startup; nếu resource tồn tại nhưng controller không được phát hiện, mapping có thể thiếu. Không xem việc build từng module thành công là bằng chứng schema toàn ứng dụng hợp lệ.

Schema SDL được đóng gói trong JAR là tài nguyên tĩnh. Thay đổi schema ở một module cần build artifact mới và triển khai phiên bản ứng dụng chứa artifact đó. Nếu muốn cập nhật schema độc lập trong runtime mà không triển khai lại ứng dụng, cần một kiến trúc resource/schema registry và cơ chế refresh riêng; cấu hình classpath mặc định không tự theo dõi thay đổi trong JAR.

## 11. Checklist trước khi phát hành

- [ ] Mỗi type gốc có một module sở hữu rõ ràng.
- [ ] Query, Mutation và Subscription root được định nghĩa đúng một lần.
- [ ] Module khác mở rộng root/object type bằng extend type.
- [ ] Không có field hoặc type trùng tên ngoài chủ đích.
- [ ] Mọi SDL resource dùng phần mở rộng .graphqls hoặc .gqls đã cấu hình.
- [ ] Spring Boot dùng classpath*: nếu cần quét dependency JAR.
- [ ] Các module schema nằm trong runtime dependency graph.
- [ ] JAR của module thực sự chứa thư mục graphql/.
- [ ] Controller/configuration của module được component scan hoặc import.
- [ ] RuntimeWiringConfigurer không đăng ký DataFetcher xung đột.
- [ ] Schema inspection và integration test không có lỗi ngoài dự kiến.
- [ ] Test được chạy với toàn bộ application context và executable artifact.
- [ ] Các module được phát hành với phiên bản tương thích trong cùng một lần triển khai.

Triển khai schema nhiều module là cách chia nhỏ một GraphQL contract theo domain mà vẫn giữ một API thống nhất. Hãy để từng module sở hữu SDL và resolver của mình, dùng type extension để đóng góp field vào type gốc, cấu hình Spring Boot quét resource trên toàn runtime classpath và kiểm thử schema sau khi hợp nhất. Khi các domain trở thành service triển khai độc lập, chuyển sang mô hình gateway/federation thay vì cố gắng dùng classpath resource scanning để ghép schema từ xa.

## Tài liệu tham khảo

- Spring Boot — Spring for GraphQL: https://docs.spring.io/spring-boot/reference/web/spring-graphql.html
- Spring Boot — Application Properties (spring.graphql.schema): https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring for GraphQL — Request Execution and Schema Resources: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- GraphQL Java — Schema and Modularising the Schema SDL: https://graphql-java.com/documentation/schema/
