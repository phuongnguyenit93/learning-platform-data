# Authorization giữa các subgraph

Trong kiến trúc Apollo Federation, một GraphQL API được ghép từ nhiều subgraph. Router nhận operation từ client, lập kế hoạch thực thi rồi gọi một hoặc nhiều subgraph để lấy dữ liệu. Mỗi subgraph có thể sở hữu dữ liệu, schema và cơ chế truy cập riêng. Vì vậy, authorization phải được thiết kế xuyên suốt từ Router tới từng subgraph.

Một nguyên tắc quan trọng là: Router có thể xác thực và từ chối request sớm, nhưng subgraph vẫn phải bảo vệ dữ liệu mà nó sở hữu. Directive `@key` chỉ mô tả cách nhận diện entity; nó không cấp quyền đọc entity đó.

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ranh giới bảo mật giữa client, Federation Router và các subgraph.
- Phân biệt authentication ở Router với authorization tại subgraph.
- Hiểu cách Router gọi entity resolver thông qua field `_entities`.
- Cấu hình Federation support bằng `FederationSchemaFactory` trong Spring for GraphQL.
- Bảo vệ `@EntityMapping` và các field được resolve trong subgraph.
- Lấy `Principal`, JWT và GraphQLContext trong resolver.
- Dùng Spring Security method authorization cho entity và field.
- Truyền identity hoặc claims từ Router tới subgraph một cách đáng tin cậy.
- Phân biệt quyền người dùng với danh tính service-to-service.
- Kiểm tra tenant, quyền sở hữu và scope khi tải federated entity.
- Xử lý GraphQL errors an toàn khi entity access bị từ chối.
- Kiểm thử trực tiếp `_entities`, field-level authorization và Router policy.

## 1. Vì sao Federation cần authorization ở nhiều tầng?

Một supergraph thường có nhiều subgraph, ví dụ:

- **Catalog subgraph** sở hữu Product, Category và thông tin mô tả sản phẩm.
- **Inventory subgraph** sở hữu số lượng tồn kho và trạng thái kho.
- **Pricing subgraph** sở hữu giá, chiết khấu và chính sách giá.
- **Order subgraph** sở hữu đơn hàng và lịch sử mua.

Một query của client có thể cần dữ liệu từ cả bốn subgraph. Router điều phối các lời gọi và ghép kết quả thành một GraphQL response.

Ví dụ:

~~~graphql
query ProductDetails($id: ID!) {
  product(id: $id) {
    id
    name
    inventory {
      available
    }
    price {
      amount
      currency
    }
  }
}
~~~

Client gửi một request tới Router. Router có thể gọi Catalog để lấy Product, sau đó gọi Inventory và Pricing bằng các entity representation của Product.

Mỗi subgraph phải tự bảo vệ dữ liệu mà nó cung cấp. Người dùng có quyền xem tên sản phẩm chưa chắc có quyền xem tồn kho của kho nội bộ hoặc giá dành riêng cho đối tác.

Nếu chỉ bảo vệ root Query trong Catalog, request đi vào Inventory qua entity resolution vẫn có thể truy cập dữ liệu nếu Inventory không kiểm tra quyền. Vì vậy, cần xem toàn bộ các đường truy cập tới dữ liệu, bao gồm cả root field, `_entities`, nested field và batch loader.

## 2. Phân biệt authentication và authorization

Hai khái niệm có vai trò khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang gửi request? | JWT xác định user và issuer |
| Authorization | Người đó được làm gì? | User có scope `inventory:read` |
| Tenant isolation | User được thao tác trong phạm vi dữ liệu nào? | Chỉ đọc Product thuộc tenant hiện tại |
| Service authentication | Thành phần backend nào đang gọi? | Router được xác thực bằng mTLS |

Một request có thể đã được xác thực thành công nhưng vẫn không có quyền đọc một field cụ thể.

Ví dụ, JWT có thể chứa:

~~~json
{
  "sub": "user-42",
  "tenant_id": "tenant-a",
  "scope": "catalog:read"
}
~~~

Token xác định user và tenant. Nhưng nó không có scope `inventory:read`, do đó user có thể xem thông tin catalog nhưng không được xem tồn kho.

Không suy ra quyền chỉ từ việc request đã đi qua Router. Authentication và authorization cần được thực hiện tại ranh giới bảo mật phù hợp.

## 3. Vai trò của Federation Router

Router là entry point của supergraph. Nó thường chịu trách nhiệm:

- Xác thực credential của client.
- Kiểm tra một số quyền ở cấp graph hoặc field.
- Lập kế hoạch query và chọn subgraph cần gọi.
- Truyền thông tin identity hoặc authorization cần thiết tới subgraph.
- Tổng hợp data và errors từ nhiều subgraph.

Apollo Router hỗ trợ nhiều chiến lược authentication và authorization, có thể kết hợp:

1. Xác thực JWT ở Router.
2. Dùng authorization directives để từ chối field trước khi gọi subgraph.
3. Chuyển tiếp JWT hoặc claims đã xác minh tới subgraph.
4. Dùng coprocessor hoặc policy plugin cho các quy tắc phức tạp.

Router giúp từ chối request sớm và giảm số lời gọi backend. Tuy nhiên, Router không thay thế authorization trong subgraph. Subgraph có thể được gọi bởi Router khác, một service nội bộ hoặc một client truy cập trực tiếp nếu network cho phép.

## 4. Subgraph phải bảo vệ dữ liệu mà nó sở hữu

Giả sử Inventory subgraph cung cấp field `Product.inventory`. Nếu chỉ Router kiểm tra scope, một người gọi trực tiếp endpoint của Inventory có thể bỏ qua Router policy.

Subgraph nên tự xác thực request và kiểm tra quyền tại service method thực hiện truy cập dữ liệu.

Các lớp bảo vệ thường gồm:

- HTTP security để yêu cầu credential hợp lệ.
- Method security để kiểm tra scope hoặc authority.
- Object-level authorization để kiểm tra tenant và quyền sở hữu.
- Field-level authorization để bảo vệ dữ liệu nhạy cảm.
- Repository query có điều kiện tenant hoặc owner.

Không nên chỉ kiểm tra quyền tại giao diện, Router hoặc một root resolver. Mọi đường đi tới dữ liệu phải đi qua policy phù hợp.

## 5. Federation entity và field _entities

Apollo Federation bổ sung cơ chế entity resolution để Router có thể yêu cầu một subgraph tải entity dựa trên key.

Ví dụ Product được nhận diện bằng id:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String!
}
~~~

Một subgraph khác có thể mở rộng Product:

~~~graphql
extend type Product @key(fields: "id") {
  id: ID! @external
  inventory: Inventory
}
~~~

Router có thể gửi operation nội bộ tới field `_entities` với representation:

~~~json
{
  "__typename": "Product",
  "id": "p-100"
}
~~~

Subgraph nhận representation và gọi entity resolver tương ứng. Trong Spring for GraphQL, method được đánh dấu `@EntityMapping` xử lý việc tải federated entity.

Điều quan trọng về bảo mật:

- Representation chỉ cung cấp dữ liệu nhận diện entity.
- Key không chứng minh người gửi có quyền đọc entity.
- Client hoặc một service có thể thử thay ID để truy cập entity khác.
- Tenant ID trong representation cũng không phải bằng chứng đáng tin cậy về tenant hiện tại.
- Entity resolver cần kiểm tra identity và policy trước khi trả entity.

Không coi `@key`, `@external`, `@requires` hoặc `@shareable` là directive cấp quyền truy cập.

## 6. Cấu hình Federation trong Spring for GraphQL

Spring for GraphQL tích hợp với thư viện `federation-jvm` để tạo schema cho subgraph. Để bật Federation, khai báo `FederationSchemaFactory` và kết nối nó với `GraphQlSource`.

Ví dụ cấu hình:

~~~java
@Configuration
public class FederationConfiguration {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {

        return builder ->
                builder.schemaFactory(factory::createGraphQLSchema);
    }
}
~~~

Với Spring Boot, builder customizer được áp dụng trong quá trình tạo GraphQL runtime. Nếu ứng dụng tự tạo `GraphQlSource`, cần bảo đảm schema factory này thực sự được gắn vào builder.

Ví dụ SDL cho Inventory subgraph với Federation 2:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.6",
    import: ["@key", "@external", "@requiresScopes"]
  )

extend type Product @key(fields: "id") {
  id: ID! @external
  inventory: Inventory
    @requiresScopes(scopes: [["inventory:read"]])
}

type Inventory {
  available: Int!
  warehouseCode: String
}
~~~

Trong ví dụ này, `Product` được sở hữu bởi subgraph khác. Inventory subgraph khai báo phần mở rộng và cung cấp field inventory.

`@requiresScopes` là authorization directive được Federation Router hỗ trợ khi cấu hình đúng phiên bản và tính năng. Nó không tự động biến thành Spring Security method security. Service trong Inventory subgraph vẫn cần kiểm tra quyền để bảo vệ dữ liệu khi có request đi vào subgraph theo đường khác.

## 7. Bật HTTP authentication trong từng subgraph

Một subgraph Spring Boot có thể dùng Spring Security OAuth2 Resource Server để xác thực JWT.

Dependency Gradle:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-security")
implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
~~~

Cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Security filter chain:

~~~java
@Configuration
@EnableMethodSecurity
public class InventorySecurityConfiguration {

    @Bean
    SecurityFilterChain inventorySecurityFilterChain(
            HttpSecurity http) throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Cấu hình trên yêu cầu JWT hợp lệ cho endpoint GraphQL. Spring Security xác minh chữ ký và các claim theo cấu hình resource server, bao gồm issuer. Trong môi trường thực tế, cần bảo đảm audience của token cũng phù hợp với subgraph hoặc API resource đang nhận token.

Nếu dùng cookie/session authentication thay vì bearer token, cần giữ CSRF protection và kiểm thử CSRF token. Chỉ cấu hình stateless/disable CSRF khi cơ chế credential và kiến trúc client thực sự phù hợp.

## 8. Lấy Principal hoặc JWT trong @EntityMapping

Spring for GraphQL hỗ trợ truyền thông tin xác thực vào method `@EntityMapping`. Các tham số có thể gồm:

- `java.security.Principal`.
- `@AuthenticationPrincipal` để lấy principal từ Spring Security.
- `GraphQLContext` hoặc `@ContextValue`.
- `DataLoader` để tải entity theo batch.

Ví dụ entity resolver:

~~~java
@Controller
public class InventoryFederationController {

    private final ProductAccessService productAccessService;

    public InventoryFederationController(
            ProductAccessService productAccessService) {
        this.productAccessService = productAccessService;
    }

    @EntityMapping
    public Product product(
            @Argument String id,
            @AuthenticationPrincipal Jwt jwt) {

        productAccessService.assertVisible(id, jwt);
        return new Product(id);
    }
}
~~~

DTO entity:

~~~java
public record Product(String id) {
}
~~~

Method `assertVisible` xác minh user hiện tại có thể tham chiếu Product đó trong tenant của họ. Chỉ sau khi policy thành công, resolver mới trả entity reference cho GraphQL tiếp tục resolve field.

Không lấy tenant ID từ argument do client gửi để quyết định quyền. Tenant cần được lấy từ claim đã xác minh hoặc security context đáng tin cậy.

## 9. Kiểm tra tenant ở entity resolver

Entity key thường chỉ có ID. Để tránh IDOR (Insecure Direct Object Reference), service cần kết hợp ID với tenant hoặc owner lấy từ identity đã xác thực.

Ví dụ service:

~~~java
@Service
public class ProductAccessService {

    private final ProductRepository repository;

    public ProductAccessService(ProductRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("isAuthenticated()")
    public void assertVisible(String productId, Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");

        boolean visible =
                repository.existsByIdAndTenantId(productId, tenantId);

        if (!visible) {
            throw new EntityNotVisibleException();
        }
    }
}
~~~

Repository kiểm tra cả hai điều kiện:

~~~java
public interface ProductRepository
        extends JpaRepository<ProductEntity, String> {

    boolean existsByIdAndTenantId(
            String productId,
            String tenantId);
}
~~~

Cách truy vấn này tránh tải entity chỉ theo ID rồi mới kiểm tra tenant ở tầng Java. Database chỉ xác nhận entity có thuộc tenant được phép hay không.

Nếu ứng dụng cần tránh tiết lộ entity có tồn tại ở tenant khác, hãy dùng cùng một kết quả nghiệp vụ cho cả hai trường hợp không tồn tại và không được phép truy cập, ví dụ `EntityNotVisibleException` với message chung.

## 10. Bảo vệ field nhạy cảm trong subgraph

Sau khi entity được resolve, các field của entity vẫn cần policy riêng.

Ví dụ Inventory subgraph chỉ cho user có scope `inventory:read` xem số lượng tồn:

~~~java
@Controller
public class InventoryFieldController {

    private final InventoryService inventoryService;

    public InventoryFieldController(
            InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @SchemaMapping(typeName = "Product", field = "inventory")
    public Inventory inventory(
            Product product,
            @AuthenticationPrincipal Jwt jwt) {

        return inventoryService.findForProduct(product.id(), jwt);
    }
}
~~~

Service:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_inventory:read')")
    public Inventory findForProduct(String productId, Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");

        return repository.findByProductIdAndTenantId(
                        productId, tenantId)
                .map(entity -> new Inventory(
                        entity.getAvailable(),
                        entity.getWarehouseCode()))
                .orElseThrow(EntityNotVisibleException::new);
    }
}
~~~

Spring Security Resource Server mặc định ánh xạ OAuth2 scopes thành authorities có tiền tố `SCOPE_`. Vì vậy scope `inventory:read` tương ứng authority `SCOPE_inventory:read`.

Có hai kiểm tra riêng:

1. `@EntityMapping` xác minh Product representation có thể được tham chiếu trong tenant hiện tại.
2. Service của field inventory xác minh user có scope xem dữ liệu tồn kho và vẫn lọc theo tenant.

Nếu user có quyền đọc catalog nhưng không có quyền đọc inventory, Router có thể từ chối field sớm bằng directive; subgraph cũng từ chối khi service method được gọi.

## 11. @key không phải authorization policy

Các directive Federation mô tả cấu trúc và quan hệ giữa subgraph. Chúng không thay thế access control.

| Directive | Vai trò trong Federation | Có cấp quyền truy cập không? |
|---|---|---|
| `@key` | Khai báo field dùng để nhận diện entity | Không |
| `@external` | Đánh dấu field được sở hữu bởi subgraph khác | Không |
| `@requires` | Khai báo field cần lấy để resolve field khác | Không |
| `@provides` | Khai báo field được cung cấp trong một nhánh | Không |
| `@shareable` | Cho phép nhiều subgraph cùng resolve field | Không |
| `@authenticated` | Router authorization directive yêu cầu request đã xác thực | Có ở Router nếu được hỗ trợ/cấu hình |
| `@requiresScopes` | Router kiểm tra scope yêu cầu | Có ở Router nếu được hỗ trợ/cấu hình |

Ví dụ, Product có:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
}
~~~

Điều đó chỉ nói rằng Product có thể được nhận diện bằng id. Nó không có nghĩa mọi user biết ID đều được phép tải Product.

Tương tự, `@requires(fields: "size weight")` mô tả dữ liệu cần thiết cho một resolver. Nó không xác nhận người dùng có quyền đọc size hoặc weight.

## 12. Authorization directives tại Router

Apollo Federation 2 hỗ trợ các authorization directives như `@authenticated` và `@requiresScopes`. Router có thể kiểm tra chúng trước khi lập kế hoạch hoặc gửi request tới subgraph.

Ví dụ SDL:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.6",
    import: ["@authenticated", "@requiresScopes"]
  )

type Query {
  currentUser: User @authenticated
}

type User {
  id: ID!
  email: String @requiresScopes(scopes: [["user:email:read"]])
}
~~~

Ý nghĩa:

- Request phải được xác thực để gọi currentUser.
- Field email yêu cầu scope `user:email:read`.
- Router có thể loại bỏ hoặc từ chối phần query không đáp ứng policy theo hành vi của phiên bản Router.

`@policy` có thể dùng cho quy tắc phức tạp hơn, nhưng cần supergraph plugin hoặc coprocessor thực thi policy. Việc khai báo directive trong SDL không tự tạo một policy engine.

Các directive này là cơ chế Router. Subgraph Spring vẫn cần kiểm tra quyền trong service method, đặc biệt khi subgraph có thể được gọi trực tiếp hoặc qua một đường tích hợp khác.

## 13. Chuyển tiếp Authorization header từ Router

Một cách đơn giản là Router chuyển tiếp JWT của client tới các subgraph. Ví dụ cấu hình Apollo Router:

~~~yaml
headers:
  all:
    request:
      - propagate:
          named: authorization
~~~

Với cấu hình này, header Authorization từ request client được chuyển tiếp tới subgraph. Mỗi subgraph có thể dùng OAuth2 Resource Server để xác minh token và ánh xạ scopes thành authorities.

Ưu điểm:

- Subgraph dùng lại Spring Security.
- Mỗi service tự kiểm tra quyền theo dữ liệu mà nó sở hữu.
- Không cần tin một header user ID do Router tự thêm mà chưa có cơ chế xác minh.

Lưu ý:

- Chỉ chuyển tiếp header cần thiết.
- Token phải có audience phù hợp với subgraph hoặc có chiến lược token exchange.
- Không log nguyên văn bearer token.
- Không chuyển tiếp cookie hoặc credential không liên quan.
- Bảo vệ kết nối Router-subgraph bằng private network và TLS/mTLS phù hợp.

Header propagation chỉ chuyển credential; nó không tự xác minh token và không tự tạo authorization policy.

## 14. Không tin các identity header do client tự gửi

Một thiết kế nguy hiểm là subgraph nhận các header như:

~~~http
X-User-Id: admin
X-Tenant-Id: tenant-a
X-Roles: ADMIN
~~~

Nếu Router chuyển tiếp các header này nguyên trạng mà không loại bỏ giá trị do client gửi, attacker có thể tự đặt danh tính hoặc tenant khác.

Nếu cần Router xác thực JWT rồi chuyển claims đã kiểm tra:

1. Router phải xóa các header identity do client cung cấp.
2. Router tạo lại header từ claims đã xác minh.
3. Kết nối Router-subgraph phải được bảo vệ, thường bằng mTLS hoặc service authentication.
4. Subgraph chỉ tin header đó từ Router đã xác thực.
5. Subgraph vẫn kiểm tra policy theo tenant, scope và object.

Ví dụ cấu hình ý tưởng:

~~~yaml
headers:
  all:
    request:
      - remove:
          named: x-authenticated-user
      - remove:
          named: x-authenticated-tenant
      - propagate:
          named: authorization
~~~

Các rule cụ thể phụ thuộc phiên bản Router và cách xác thực. Nếu Router dùng coprocessor hoặc plugin để chèn claims, hãy bảo đảm thứ tự remove/insert đúng và subgraph không thể bị truy cập từ nguồn không đáng tin.

Không dùng header `X-User-Id` làm nguồn danh tính nếu subgraph không thể chứng minh header đó do Router tin cậy tạo ra.

## 15. Phân biệt user identity và service identity

Trong môi trường nhiều subgraph, một request có ít nhất hai danh tính cần xem xét:

- **User identity**: người dùng cuối đang thực hiện hành động.
- **Service identity**: Router hoặc một subgraph đang gọi service khác.

Service identity chứng minh request đến từ thành phần backend được phép kết nối. Nó không tự chứng minh user cuối có quyền đọc dữ liệu.

Ví dụ:

- Router có certificate mTLS hợp lệ để gọi Inventory.
- User có JWT với scope `catalog:read` nhưng không có `inventory:read`.
- Router được phép kết nối Inventory, nhưng request của user vẫn không được đọc inventory.

Không dùng service account quyền rộng để bỏ qua user authorization. Khi subgraph gọi một service khác, cần xác định rõ hành động được ủy quyền theo user hay theo service:

| Mục đích | Credential phù hợp |
|---|---|
| Xác thực Router được phép gọi subgraph | mTLS hoặc service credential |
| Xác định user cuối | JWT hoặc delegated token |
| Kiểm tra scope của user | User claims đã xác minh |
| Gọi nội bộ không phụ thuộc user | Service token với quyền tối thiểu |
| Gọi nội bộ thay mặt user | Token exchange/delegation theo chính sách |

Khi dùng token exchange, cần giữ thông tin actor/caller nếu nghiệp vụ cần audit ai đã thực hiện lời gọi thay mặt user.

## 16. Bảo vệ khi subgraph bị gọi trực tiếp

Trong production, subgraph thường chỉ được expose trong private network và chỉ nhận traffic từ Router. Tuy nhiên, network restriction là một lớp bảo vệ bổ sung, không thay thế authorization.

Cần cân nhắc:

- Không public ingress trực tiếp tới subgraph nếu không cần.
- Dùng mTLS hoặc workload identity giữa Router và subgraph.
- Xác minh JWT hoặc trusted identity ở subgraph.
- Giới hạn endpoint GraphQL và management endpoint.
- Bảo vệ `_entities` giống các field khác.
- Không để một endpoint debug hoặc alternate transport bỏ qua SecurityFilterChain.
- Áp dụng authorization cho các service method được gọi từ GraphQL.

Nếu subgraph cần cho phép service nội bộ gọi trực tiếp, hãy xác định rõ service principal và quyền của nó. Không mặc định mọi request từ mạng nội bộ đều đáng tin.

## 17. Dùng GraphQLContext cho tenant hoặc metadata đã xác thực

Một số policy cần metadata từ request như tenant ID, correlation ID hoặc thông tin đã xác minh từ interceptor.

Spring for GraphQL hỗ trợ GraphQLContext và các annotation như `@ContextValue`. `@EntityMapping` cũng có thể nhận GraphQLContext, Principal hoặc `@AuthenticationPrincipal`.

Một WebGraphQlInterceptor hoặc security integration có thể đưa tenant đã xác minh vào GraphQLContext trước khi thực thi operation. Cách lấy Authentication phụ thuộc ứng dụng dùng Spring MVC hay WebFlux; với WebFlux, cần đọc security context theo Reactor Context thay vì giả định có ThreadLocal. Không lấy tenant từ GraphQL variables hoặc header không đáng tin.

Trong resolver:

~~~java
@EntityMapping
public Product product(
        @Argument String id,
        @ContextValue("tenantId") String tenantId) {

    return productAccessService.requireVisible(id, tenantId);
}
~~~

Nếu đã có `@AuthenticationPrincipal Jwt`, có thể lấy tenant trực tiếp từ claim của JWT đã xác minh. Chọn một nguồn identity nhất quán và tránh duy trì hai giá trị tenant có thể mâu thuẫn.

## 18. DataLoader phải giữ authorization context

DataLoader thường được tạo theo từng GraphQL request thông qua BatchLoaderRegistry. Batch loader có thể nhận GraphQLContext hoặc BatchLoaderEnvironment để áp dụng tenant và authorization.

Ví dụ:

~~~java
@Configuration
public class ProductLoaderConfiguration {

    public ProductLoaderConfiguration(
            BatchLoaderRegistry registry,
            ProductReadService productReadService) {

        registry.forTypePair(String.class, Product.class)
                .registerMappedBatchLoader((productIds, environment) -> {
                    String tenantId =
                            environment.getGraphQlContext()
                                    .get("tenantId");

                    return productReadService.findVisibleProducts(
                            tenantId, productIds);
                });
    }
}
~~~

Batch loader cần query theo cả tenant và IDs:

~~~java
public Map<String, Product> findVisibleProducts(
        String tenantId,
        Set<String> productIds) {

    return repository.findAllByTenantIdAndIdIn(
                    tenantId, productIds)
            .stream()
            .collect(Collectors.toMap(
                    ProductEntity::getId,
                    this::toProduct));
}
~~~

Không chỉ lọc dữ liệu ở resolver trước khi gọi DataLoader. Batch loader phải thực hiện tenant filter tại nơi truy vấn dữ liệu, vì nó là nơi trực tiếp tải entity.

DataLoader cache nên nằm trong phạm vi request. Không chia sẻ loader giữa các request hoặc tenant. Nếu kết quả phụ thuộc thêm vào scope hoặc user, cần bảo đảm cache key và loader lifecycle không khiến dữ liệu của principal này được dùng cho principal khác.

## 19. Xử lý entity không được phép truy cập

Khi entity resolver không tìm thấy entity hoặc user không có quyền, ứng dụng cần chọn một chính sách nhất quán.

Hai lựa chọn phổ biến:

- Trả kết quả không tồn tại nếu API muốn che giấu việc entity có tồn tại ở tenant khác.
- Trả access denied nếu nghiệp vụ cho phép tiết lộ rằng entity có tồn tại nhưng user không có quyền.

Với dữ liệu nhạy cảm, thường nên tránh phân biệt hai trường hợp ở response công khai nếu điều đó tạo ra IDOR enumeration.

Ví dụ exception:

~~~java
public class EntityNotVisibleException
        extends RuntimeException {
}
~~~

Entity resolver có thể ném exception này khi không tìm thấy entity trong tenant hiện tại hoặc khi policy từ chối.

Không trả nguyên văn câu SQL, tenant ID, internal product ID hoặc thông tin hệ thống trong GraphQL error.

## 20. Chuẩn hóa GraphQL errors từ @EntityMapping

Spring for GraphQL hỗ trợ `@GraphQlExceptionHandler` để ánh xạ exception từ `@EntityMapping` thành GraphQL errors. Exception handler có thể đặt trong controller hoặc `@ControllerAdvice`.

Ví dụ:

~~~java
@ControllerAdvice
public class FederationExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleEntityNotVisible(
            EntityNotVisibleException exception) {

        return GraphqlErrorBuilder.newError()
                .message("Entity is not available")
                .extensions(Map.of(
                        "code", "ENTITY_NOT_AVAILABLE"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception) {

        return GraphqlErrorBuilder.newError()
                .message("Access denied")
                .extensions(Map.of(
                        "code", "FORBIDDEN"))
                .build();
    }
}
~~~

Các errors từ entity resolver được đưa vào response của operation `_entities`. Router có thể tổng hợp errors này vào response supergraph.

Nên giữ message ổn định và không tiết lộ exception message gốc. Client có thể dựa vào error code để hiển thị thông báo phù hợp; log nội bộ có thể ghi chi tiết hơn nhưng phải tránh token và dữ liệu cá nhân.

## 21. Lưu ý bảo mật về exception handling trong Federation

Entity resolver là ranh giới quan trọng vì nó xử lý representation từ Router. Nếu exception chưa được xử lý và message gốc bị đưa vào response, thông tin nội bộ có thể bị lộ.

Tại thời điểm biên soạn bài học này, Spring đã công bố CVE-2026-59356 liên quan tới việc Federation controller mặc định có thể đưa full exception message vào response khi exception từ `@EntityMapping` không được xử lý bởi exception handler. Các nhánh bị ảnh hưởng gồm:

- Spring for GraphQL 2.0.0 đến 2.0.5.
- Spring for GraphQL 1.4.0 đến 1.4.7.
- Spring for GraphQL 1.3.0 đến 1.3.10.

Các bản sửa tương ứng là 2.0.6, 1.4.8 và 1.3.11. Hãy dùng bản đã được vá phù hợp với nhánh đang triển khai và vẫn chuẩn hóa lỗi trong ứng dụng.

Không dựa vào việc ẩn stack trace ở Router để thay thế việc xử lý exception an toàn tại subgraph.

## 22. Kiểm thử authorization của service method

Có thể kiểm tra policy độc lập bằng Spring Security Test.

Thêm dependency test:

~~~groovy
testImplementation("org.springframework.security:spring-security-test")
~~~

Ví dụ service method:

~~~java
@Service
public class InventoryService {

    @PreAuthorize("hasAuthority('SCOPE_inventory:read')")
    public Inventory readInventory(String productId) {
        // Load inventory.
        return new Inventory(12, "WH-01");
    }
}
~~~

Test user có scope:

~~~java
@SpringBootTest
class InventoryServiceSecurityTests {

    @Autowired
    InventoryService inventoryService;

    @Test
    @WithMockUser(authorities = "SCOPE_inventory:read")
    void userWithInventoryScopeCanRead() {
        Inventory inventory =
                inventoryService.readInventory("p-100");

        assertThat(inventory.available()).isEqualTo(12);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_catalog:read")
    void userWithoutInventoryScopeIsDenied() {
        assertThatThrownBy(() ->
                inventoryService.readInventory("p-100"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Test phải gọi bean thật do Spring quản lý để method-security proxy hoạt động. Nếu thay InventoryService bằng Mockito mock, test không còn xác nhận `@PreAuthorize`.

## 23. Kiểm thử _entities qua HTTP

Cần có integration test cho đường đi Federation entity resolution, không chỉ test root Query.

Ví dụ operation:

~~~graphql
query ProductEntity($representations: [_Any!]!) {
  _entities(representations: $representations) {
    ... on Product {
      id
      inventory {
        available
      }
    }
  }
}
~~~

Variables:

~~~json
{
  "representations": [
    {
      "__typename": "Product",
      "id": "p-100"
    }
  ]
}
~~~

Test có thể dùng `HttpGraphQlTester` và gửi bearer token hợp lệ:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class InventoryFederationAuthorizationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void userWithInventoryScopeCanResolveEntity() {
        HttpGraphQlTester authorizedTester = graphQlTester.mutate()
                .headers(headers ->
                        headers.setBearerAuth(validInventoryToken()))
                .build();

        authorizedTester.documentName("productEntity")
                .variable("representations", List.of(
                        Map.of(
                                "__typename", "Product",
                                "id", "p-100")))
                .execute()
                .path("_entities[0].inventory.available")
                .entity(Integer.class)
                .isEqualTo(12);
    }
}
~~~

Ví dụ giả định test có token hợp lệ do test identity provider hoặc JWT test fixture tạo ra, file `productEntity.graphql` nằm trong test document source và dữ liệu Product thuộc tenant của user.

Test user không có scope:

~~~java
@Test
void userWithoutInventoryScopeCannotReadInventory() {
    HttpGraphQlTester viewerTester = graphQlTester.mutate()
            .headers(headers ->
                    headers.setBearerAuth(validCatalogOnlyToken()))
            .build();

    viewerTester.documentName("productEntity")
            .variable("representations", List.of(
                    Map.of(
                            "__typename", "Product",
                            "id", "p-100")))
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors)
                            .anyMatch(error ->
                                    error.getMessage()
                                            .contains("Access denied")));
}
~~~

Trong test thực tế, nên kiểm tra thêm error path và field data theo nullability của schema. Không chỉ xác nhận response có errors; hãy bảo đảm field inventory không trả dữ liệu.

Nếu test dùng HTTP server chạy ở cổng riêng, `@WithMockUser` trên test thread không tự động trở thành credential của request. Hãy gửi bearer token hoặc dùng test web client có cơ chế mock security phù hợp với in-process test.

## 24. Kiểm thử tenant isolation

Một user có scope `inventory:read` vẫn không được đọc tồn kho của tenant khác.

Test matrix:

| User | Scope | Tenant | Entity tenant | Kết quả |
|---|---|---|---|---|
| Alice | inventory:read | tenant-a | tenant-a | Cho phép |
| Alice | inventory:read | tenant-a | tenant-b | Từ chối hoặc không tìm thấy |
| Bob | catalog:read | tenant-b | tenant-b | Không được đọc inventory |
| Anonymous | Không có | — | tenant-a | HTTP authentication bị từ chối |

Test nên thử thay entity ID trong representation để bảo đảm user không thể truy cập entity ngoài tenant chỉ bằng cách biết ID.

Đặc biệt, không lấy tenant từ representation:

~~~json
{
  "__typename": "Product",
  "id": "p-100",
  "tenantId": "tenant-b"
}
~~~

Nếu tenantId không phải một key đã được schema tin cậy và policy cho phép, giá trị này vẫn là input không đáng tin. Dùng tenant claim đã xác minh từ Authentication hoặc GraphQLContext.

## 25. Kiểm thử Router policy và subgraph policy riêng biệt

Một hệ thống Federation cần kiểm thử ít nhất hai tầng:

**Router tests**

- JWT không hợp lệ bị từ chối.
- Request không có scope bị từ chối trước khi gọi subgraph nếu Router policy được bật.
- Header identity do client tự gửi bị loại bỏ.
- Header hoặc claims được chuyển tiếp đúng tới subgraph.
- Một field được bảo vệ bởi `@requiresScopes` không xuất hiện trong kết quả khi thiếu scope.

**Subgraph tests**

- Request trực tiếp tới subgraph không có token bị từ chối.
- JWT sai issuer hoặc audience không được chấp nhận.
- `@EntityMapping` kiểm tra tenant/entity visibility.
- `@SchemaMapping` gọi service có method-security.
- DataLoader batch query áp dụng tenant filter.
- Field nhạy cảm không xuất hiện khi thiếu quyền.
- Exception được chuyển thành error message an toàn.

Router policy và subgraph policy có thể cùng từ chối một request. Đây là defense in depth, không phải logic trùng lặp vô ích: Router tối ưu và từ chối sớm; subgraph bảo vệ dữ liệu tại nơi sở hữu dữ liệu.

## 26. Kiểm thử lỗi và partial data

GraphQL có thể trả data và errors cùng lúc. Ví dụ user được phép đọc Product nhưng không được phép đọc Inventory.

Response minh họa:

~~~json
{
  "data": {
    "_entities": [
      {
        "id": "p-100",
        "inventory": null
      }
    ]
  },
  "errors": [
    {
      "message": "Access denied",
      "path": ["_entities", 0, "inventory"],
      "extensions": {
        "code": "FORBIDDEN"
      }
    }
  ]
}
~~~

Đây là ví dụ minh họa; response thực tế còn phụ thuộc nullability trong SDL và cách Router tổng hợp errors.

Test nên xác nhận:

- Product field công khai vẫn có dữ liệu nếu policy cho phép.
- Inventory là null hoặc bị loại khỏi data theo schema.
- Error path trỏ tới đúng field hoặc entity resolver.
- Error code ổn định.
- Không có token, tenant ID hoặc exception message nội bộ trong response.

Nếu field được khai báo non-null, GraphQL có thể lan truyền null lên parent theo nullability rules. Hãy thiết kế SDL phù hợp với hành vi khi authorization thất bại.

## 27. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| User xem được field khi gọi subgraph trực tiếp | Chỉ bảo vệ ở Router | Bổ sung method/object authorization trong subgraph |
| Entity resolver trả dữ liệu của tenant khác | Chỉ query theo entity ID | Lọc bằng tenant claim đã xác minh |
| `@key` bị hiểu nhầm là quyền truy cập | Nhầm identity với authorization | Kiểm tra policy trong @EntityMapping/service |
| Router đã xác thực nhưng subgraph không có Principal | Không truyền credential hoặc context | Cấu hình header propagation/token exchange |
| Subgraph tin X-User-Id từ client | Router không loại header giả mạo | Strip header và chèn claims đã xác minh |
| Service token có quyền quá rộng | Dùng service identity thay cho user policy | Kết hợp service authentication và user authorization |
| Field resolver bỏ qua policy | Chỉ bảo vệ root Query | Bảo vệ service method được gọi từ mọi đường truy cập |
| DataLoader trả dữ liệu tenant khác | Loader cache dùng sai scope hoặc batch query thiếu tenant filter | Loader per request và query theo tenant |
| _entities không được bảo vệ | Chỉ test root Query | Kiểm thử trực tiếp entity representations |
| GraphQL error lộ exception message | Entity mapping exception không được chuẩn hóa | @GraphQlExceptionHandler và nâng cấp bản vá |
| @requiresScopes không có tác dụng | Router chưa hỗ trợ hoặc chưa bật authorization | Kiểm tra phiên bản và Router configuration |
| @WithMockUser không hoạt động qua live HTTP | SecurityContext chỉ nằm trên test thread | Gửi JWT thực trong HttpGraphQlTester |
| Router từ chối nhưng subgraph vẫn nhận request khác | Có đường truy cập trực tiếp | Network policy và subgraph security |

## 28. Checklist triển khai authorization giữa các subgraph

Trước khi đưa Federation supergraph vào production:

- [ ] Router xác thực credential của client.
- [ ] Router policy được bật cho directive cần dùng.
- [ ] Mỗi subgraph xác thực request theo trust model đã chọn.
- [ ] Kết nối Router-subgraph được bảo vệ bằng TLS/mTLS hoặc service identity phù hợp.
- [ ] Subgraph không public trực tiếp nếu không cần.
- [ ] `@EntityMapping` kiểm tra entity visibility và tenant.
- [ ] Field nhạy cảm có authorization ở service hoặc resolver.
- [ ] `@key` chỉ được dùng để nhận diện entity, không dùng làm quyền truy cập.
- [ ] Tenant lấy từ identity đã xác minh, không lấy từ representation.
- [ ] Header identity do client gửi được strip trước khi Router chèn claims.
- [ ] Phân biệt user identity với service identity.
- [ ] DataLoader được tạo per request và batch query áp dụng tenant filter.
- [ ] GraphQL errors không tiết lộ exception message hoặc dữ liệu nội bộ.
- [ ] Spring for GraphQL đang ở phiên bản đã vá security advisory liên quan.
- [ ] Có test trực tiếp `_entities` với user đủ quyền và thiếu quyền.
- [ ] Có test tenant isolation và object ownership.
- [ ] Có test Router policy và subgraph policy riêng.
- [ ] Có test partial data và error path theo nullability của schema.

## Kết luận

Authorization giữa các subgraph cần được thiết kế theo nhiều lớp. Router xác thực request và có thể áp dụng authorization directives để từ chối field sớm. Mỗi subgraph vẫn phải bảo vệ dữ liệu mà nó sở hữu, đặc biệt tại `@EntityMapping`, `@SchemaMapping`, service method và batch loader.

Trong Spring for GraphQL, FederationSchemaFactory tích hợp schema Federation, còn `@EntityMapping` xử lý entity representations từ `_entities`. Các method này có thể nhận Principal, `@AuthenticationPrincipal` hoặc GraphQLContext để áp dụng policy. `@PreAuthorize` bảo vệ service method, trong khi repository query cần lọc theo tenant hoặc owner.

Không xem entity key, header do client gửi hoặc service identity là bằng chứng user có quyền truy cập. Hãy xác thực credential, truyền identity theo kênh tin cậy, kiểm tra scope và tenant ở subgraph, chuẩn hóa GraphQL errors và kiểm thử cả Router lẫn từng subgraph. Cách tiếp cận này giúp supergraph giữ được ranh giới bảo mật ngay cả khi entity được truy cập từ nhiều đường thực thi khác nhau.

## Tài liệu tham khảo

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Apollo — Authenticating Requests with the GraphOS Router](https://www.apollographql.com/docs/graphos/routing/v3/security/router-authentication)
- [Apollo — Authorization in the GraphOS Router](https://www.apollographql.com/docs/graphos/routing/security/authorization)
- [Apollo — Header Propagation](https://www.apollographql.com/docs/graphos/routing/header-propagation)
- [Apollo — Federation Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Advisory — CVE-2026-59356](https://spring.io/security/cve-2026-59356)
