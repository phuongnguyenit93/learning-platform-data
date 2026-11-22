# Tenant context trong Spring for GraphQL

Trong ứng dụng multi-tenant, nhiều tổ chức hoặc khách hàng cùng sử dụng một GraphQL API nhưng dữ liệu của họ phải được tách biệt. Tenant context là thông tin xác định request hiện tại thuộc tenant nào và được dùng xuyên suốt quá trình phân giải field, gọi service, truy vấn repository, batch loading và phát subscription event.

Spring for GraphQL cung cấp `GraphQLContext`, `@ContextValue`, `Principal` và `@AuthenticationPrincipal` để truyền thông tin theo từng GraphQL execution. Tuy nhiên, việc có tenant context không tự bảo đảm cách ly dữ liệu. Ứng dụng vẫn phải xác minh danh tính, xác định tenant từ nguồn đáng tin cậy và áp dụng tenant filter ở tầng service/repository cho mọi thao tác đọc, ghi và xóa.

## 1. Tenant và tenant context là gì?

Tenant là một đơn vị khách hàng hoặc tổ chức có phạm vi dữ liệu riêng trong cùng một hệ thống. Ví dụ một nền tảng quản lý dự án có thể phục vụ nhiều công ty:

- Công ty A có dự án, thành viên và hóa đơn riêng.
- Công ty B có dữ liệu tương tự nhưng không được nhìn thấy dữ liệu của A.
- Một người dùng có thể thuộc một hoặc nhiều tenant với vai trò khác nhau.

`TenantContext` là object mô tả phạm vi tenant của request, thường chứa:

| Thành phần | Mục đích |
|---|---|
| `tenantId` | Định danh tenant hiện tại. |
| `subject` | Người dùng hoặc service đã được xác thực. |
| `authorities` hoặc roles | Các quyền đã được xác minh nếu ứng dụng cần dùng. |
| `correlationId` | Mã theo dõi request, nếu cần cho logging/tracing. |

Ví dụ model bất biến:

```java
public record TenantContext(
    String tenantId,
    String subject
) {}
```

Không nên nhầm tenant context với một biến toàn cục hoặc field mutable trên singleton service. Tenant context phải thuộc đúng request hoặc execution để dữ liệu của tenant này không rò sang request của tenant khác.

## 2. Các mô hình lưu trữ multi-tenant

Trước khi triển khai GraphQL context, cần xác định cách dữ liệu được phân vùng:

| Mô hình | Cách tổ chức | Đặc điểm |
|---|---|---|
| Shared database, shared schema | Mọi tenant dùng chung bảng; mỗi hàng có `tenant_id`. | Dễ vận hành và tối ưu tài nguyên; mọi query phải lọc tenant chính xác. |
| Shared database, schema per tenant | Mỗi tenant có schema database riêng. | Tách cấu trúc ở mức schema; cần chọn schema đúng cho từng request. |
| Database per tenant | Mỗi tenant có database riêng. | Cách ly mạnh hơn; quản lý connection, migration và vận hành phức tạp hơn. |
| Hybrid | Kết hợp các mô hình trên. | Phù hợp hệ thống có tenant lớn/nhỏ với yêu cầu khác nhau. |

Trong mô hình shared schema, ví dụ bảng `project` có thể gồm:

```sql
CREATE TABLE project (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL
);

CREATE INDEX idx_project_tenant_id_id
    ON project (tenant_id, id);
```

Mọi thao tác cần định danh cả `tenant_id` và resource ID. Chỉ truy vấn `WHERE id = :id` là chưa đủ nếu ID không được bảo đảm duy nhất toàn hệ thống hoặc nếu ứng dụng cần defense-in-depth.

## 3. Tenant context đi qua GraphQL request như thế nào?

Luồng xử lý nên có ranh giới rõ ràng:

```text
Client request
      |
      v
Spring Security authentication
      |
      v
Principal / verified JWT claims
      |
      v
Resolve active TenantContext
      |
      v
GraphQL execution
      |
      +---- @QueryMapping / @MutationMapping
      |
      +---- @SchemaMapping / @BatchMapping
      |
      v
Tenant-aware service
      |
      v
Tenant-filtered repository / database
```

Các nguyên tắc:

1. Xác thực người dùng trước khi tin cậy danh tính.
2. Xác định tenant từ principal/claim đã xác minh hoặc từ một nguồn tin cậy khác.
3. Truyền tenant context theo request hoặc truyền tenant ID tường minh vào service.
4. Áp dụng tenant filter ở tầng truy cập dữ liệu.
5. Kiểm tra quyền của người dùng đối với tài nguyên trong tenant đó.

GraphQL argument như `tenantId` có thể là tham số nghiệp vụ trong một API quản trị đặc biệt, nhưng không được dùng làm bằng chứng tenant của người gửi request. Người dùng không được tự đổi tenant bằng cách sửa argument hoặc header tùy ý.

## 4. Lấy tenant từ danh tính đã xác thực

Với OAuth2 Resource Server, Spring Security xác thực JWT và có thể cung cấp `Jwt` làm principal cho annotated controller thông qua `@AuthenticationPrincipal`.

Ví dụ factory tạo tenant context từ claim đã xác minh:

```java
@Component
class TenantContextFactory {

    private final TenantMembershipService membershipService;

    TenantContextFactory(TenantMembershipService membershipService) {
        this.membershipService = membershipService;
    }

    TenantContext from(Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId == null || tenantId.isBlank()) {
            throw new AccessDeniedException("Tenant claim is required");
        }

        return new TenantContext(tenantId, jwt.getSubject());
    }

    TenantContext from(Principal principal) {
        return membershipService.findActiveTenantFor(principal.getName())
            .orElseThrow(() -> new AccessDeniedException("No active tenant"));
    }
}
```

```java
interface TenantMembershipService {
    Optional<TenantContext> findActiveTenantFor(String subject);
}
```

Trong ví dụ này, `membershipService` là dependency của factory và trả về tenant membership đang hoạt động của subject. Có thể dùng cách tra membership này khi một người dùng được phép tham gia nhiều tenant và tenant hiện hành được chọn theo chính sách của ứng dụng.

`tenant_id` chỉ đáng tin cậy sau khi JWT được xác thực chữ ký, issuer, audience và thời hạn theo cấu hình Spring Security. Nếu một người dùng được phép chọn giữa nhiều tenant, claim có thể chỉ chứa danh sách tenant hoặc token không chứa tenant hiện hành; khi đó ứng dụng cần xác minh membership và lựa chọn tenant theo một quy trình được kiểm soát.

Nếu ứng dụng dùng session authentication hoặc custom principal, có thể nhận `Principal`/`Authentication` và dùng service tra cứu tenant membership. Spring for GraphQL hỗ trợ `Principal` và `@AuthenticationPrincipal` làm method argument trong annotated controller.

## 5. Truyền tenant vào service từ resolver

Cách trực tiếp và dễ kiểm soát là resolver lấy tenant từ principal rồi truyền tenant ID vào service:

```graphql
type Query {
    projects: [Project!]!
    project(id: ID!): Project
}

type Project {
    id: ID!
    name: String!
}
```

```java
public record Project(UUID id, String name, String tenantId) {
    public Project withName(String newName) {
        return new Project(id, newName, tenantId);
    }
}

@Controller
class ProjectController {

    private final TenantContextFactory tenantContextFactory;
    private final ProjectService projectService;

    ProjectController(
            TenantContextFactory tenantContextFactory,
            ProjectService projectService) {
        this.tenantContextFactory = tenantContextFactory;
        this.projectService = projectService;
    }

    @QueryMapping
    Flux<Project> projects(Principal principal) {
        TenantContext tenant = tenantContextFactory.from(principal);
        return projectService.findAllForTenant(tenant.tenantId());
    }

    @QueryMapping
    Mono<Project> project(
            @Argument UUID id,
            Principal principal) {
        TenantContext tenant = tenantContextFactory.from(principal);
        return projectService.findByTenantAndId(tenant.tenantId(), id);
    }
}
```

Tenant ID không nằm trong GraphQL query. Server lấy tenant từ principal và truyền vào service. Cách này phù hợp khi resolver chỉ cần tenant cho một thao tác và không cần chia sẻ nhiều metadata giữa các field.

Nếu dùng `Principal` thay cho `Jwt`, `TenantContextFactory` có thể tra membership theo `principal.getName()`. Không lấy username hoặc tenant ID từ argument do client tự gửi rồi coi đó là principal đã xác thực.

## 6. Dùng `GraphQLContext` cho thông tin dùng chung trong một execution

`GraphQLContext` là context cấp execution, có thể dùng để truyền thông tin xuyên suốt nhiều data fetcher của cùng một GraphQL operation. Nó hữu ích khi nhiều field lồng nhau cùng cần tenant context.

Ví dụ root resolver xác định tenant từ JWT, lưu context trước khi trả về parent objects:

```java
@Controller
class ProjectController {

    private final TenantContextFactory tenantContextFactory;
    private final ProjectService projectService;

    ProjectController(
            TenantContextFactory tenantContextFactory,
            ProjectService projectService) {
        this.tenantContextFactory = tenantContextFactory;
        this.projectService = projectService;
    }

    @QueryMapping
    Flux<Project> projects(
            @AuthenticationPrincipal Jwt jwt,
            GraphQLContext graphQLContext) {

        TenantContext tenant = tenantContextFactory.from(jwt);
        graphQLContext.put("tenantContext", tenant);

        return projectService.findAllForTenant(tenant.tenantId());
    }
}
```

Field con có thể đọc lại context bằng `@ContextValue`:

```java
@SchemaMapping(typeName = "Project", field = "billingSummary")
Mono<BillingSummary> billingSummary(
        Project project,
        @ContextValue("tenantContext") TenantContext tenant) {

    return billingService.summaryForTenantAndProject(
        tenant.tenantId(), project.id()
    );
}
```

`GraphQLContext` được chia sẻ trong một execution, còn `@ContextValue` giúp bind một giá trị cụ thể từ context vào method argument. Nên đặt context một lần ở ranh giới đã xác định và xem `TenantContext` là immutable.

Ví dụ root resolver trên phù hợp khi operation lấy danh sách project làm root rồi phân giải field con của chúng. Nếu một operation có nhiều root field độc lập, không nên dựa vào thứ tự thực thi của một resolver để thiết lập context cho resolver khác. Hãy resolve tenant từ principal trong từng root resolver hoặc khởi tạo context trước execution bằng một interceptor/integration có quyền truy cập nguồn tenant đã xác minh.

## 7. Dùng HTTP header chỉ khi header đến từ nguồn tin cậy

Spring for GraphQL có `HttpRequestHeaderInterceptor` để sao chép header HTTP được chọn vào `GraphQLContext`:

```java
@Configuration
class GraphQlTenantHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor tenantHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
            .mapHeader("X-Verified-Tenant")
            .build();
    }
}
```

Import của interceptor có sẵn:

```java
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;
```

Controller có thể đọc giá trị:

```java
@QueryMapping
Flux<Project> projects(
        @ContextValue("X-Verified-Tenant") String tenantId) {
    return projectService.findAllForTenant(tenantId);
}
```

Chỉ dùng cách này khi API gateway hoặc reverse proxy đáng tin cậy đã xác thực người dùng, kiểm tra membership, xóa header cùng tên do client gửi lên và tự đặt `X-Verified-Tenant`. Backend cần được bảo vệ để client không thể gọi trực tiếp và giả mạo header.

Nếu browser hoặc client gọi thẳng GraphQL endpoint, không dùng một header tùy ý như `X-Tenant-Id` làm nguồn xác định tenant. Hãy dùng principal đã xác thực hoặc một tenant selection flow được kiểm tra quyền.

## 8. Tenant-aware service và repository

Đưa tenant ID thành tham số bắt buộc của các service method truy cập dữ liệu giúp chính sách cách ly rõ ràng và dễ kiểm thử.

Service:

```java
@Service
class ProjectService {

    private final ProjectRepository repository;

    ProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    Flux<Project> findAllForTenant(String tenantId) {
        return repository.findAllByTenantId(tenantId);
    }

    Mono<Project> findByTenantAndId(String tenantId, UUID projectId) {
        return repository.findByTenantIdAndId(tenantId, projectId);
    }
}
```

Repository reactive:

```java
interface ProjectRepository extends ReactiveCrudRepository<Project, UUID> {

    Flux<Project> findAllByTenantId(String tenantId);

    Mono<Project> findByTenantIdAndId(String tenantId, UUID id);
}
```

Với JPA, có thể dùng derived query tương tự hoặc khai báo `@Query` với điều kiện `tenantId`. Điều quan trọng là tenant phải có mặt trong predicate của thao tác truy cập dữ liệu.

Không nên chỉ tải project theo ID rồi kiểm tra tenant sau khi đã trả object qua nhiều tầng. Truy vấn có tenant predicate ngay từ đầu giảm nguy cơ lộ dữ liệu và giúp database tận dụng index phù hợp.

## 9. Bảo vệ mutation và thao tác ghi/xóa

Mutation không nên nhận `tenantId` như dữ liệu quyết định tenant sở hữu bản ghi. Server phải gán tenant từ context đã xác minh.

SDL:

```graphql
input CreateProjectInput {
    name: String!
}

type Mutation {
    createProject(input: CreateProjectInput!): Project!
    renameProject(id: ID!, name: String!): Project!
    deleteProject(id: ID!): Boolean!
}
```

Resolver:

```java
@MutationMapping
Mono<Project> createProject(
        @Argument CreateProjectInput input,
        @AuthenticationPrincipal Jwt jwt) {

    TenantContext tenant = tenantContextFactory.from(jwt);
    return projectService.createForTenant(tenant.tenantId(), input.name());
}
```

Service cần bảo đảm cả update và delete đều có tenant predicate:

```java
Mono<Project> renameProject(String tenantId, UUID id, String name) {
    return repository.findByTenantIdAndId(tenantId, id)
        .switchIfEmpty(Mono.error(new ProjectNotFoundException(id)))
        .flatMap(project -> repository.save(project.withName(name)));
}

Mono<Boolean> deleteProject(String tenantId, UUID id) {
    return repository.deleteByTenantIdAndId(tenantId, id)
        .thenReturn(true);
}
```

Các method repository `deleteByTenantIdAndId` và model `withName` là ví dụ cần triển khai theo công nghệ persistence của ứng dụng. Không dùng `deleteById(id)` nếu thao tác đó không kiểm tra tenant ownership.

## 10. Kết hợp tenant context với `@BatchMapping`

Field lồng nhau cũng phải giữ tenant boundary. Giả sử mỗi project có danh sách member:

```graphql
type Project {
    id: ID!
    name: String!
    members: [Member!]!
}

type Member {
    id: ID!
    name: String!
}
```

Các model Java minh họa:

```java
public record Member(UUID id, UUID projectId, String name, String tenantId) {}
```

`@BatchMapping` hỗ trợ `@ContextValue`, `GraphQLContext` và `Principal` làm method argument. Có thể dùng tenant context đã được thiết lập ở root resolver:

```java
@BatchMapping(typeName = "Project", field = "members")
Mono<Map<Project, List<Member>>> members(
        List<Project> projects,
        @ContextValue("tenantContext") TenantContext tenant) {

    Set<UUID> projectIds = projects.stream()
        .map(Project::id)
        .collect(Collectors.toSet());

    return memberService.findForTenantAndProjectIds(
            tenant.tenantId(), projectIds)
        .collectMultimap(Member::projectId)
        .map(membersByProject -> {
            Map<Project, List<Member>> result = new LinkedHashMap<>();
            for (Project project : projects) {
                Collection<Member> members = membersByProject.getOrDefault(
                    project.id(), List.of());
                result.put(project, List.copyOf(members));
            }
            return result;
        });
}
```

Service truy vấn theo cả tenant và tập project ID:

```java
Flux<Member> findForTenantAndProjectIds(
        String tenantId,
        Set<UUID> projectIds) {
    return memberRepository.findAllByTenantIdAndProjectIdIn(tenantId, projectIds);
}
```

Batch query cần áp dụng tenant predicate ngay ở repository. Không tải member theo danh sách project ID thuần túy rồi giả định mọi project đều thuộc tenant hiện tại.

Nếu field batch không có context từ root resolver, có thể nhận `Principal` trực tiếp trong `@BatchMapping` rồi resolve tenant từ principal. Đây là lựa chọn tốt khi không muốn phụ thuộc vào context được thiết lập ở một root field cụ thể.

## 11. Truyền tenant context vào DataLoader

Khi dùng `BatchLoaderRegistry`, batch loading function cũng có thể truy cập `GraphQLContext` qua `BatchLoaderEnvironment`. Spring for GraphQL bảo đảm context của batch loader là cùng context được cung cấp cho data fetcher và `@BatchMapping`.

Ví dụ đăng ký mapped batch loader:

```java
@Configuration
class MemberDataLoaderConfiguration {

    MemberDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            MemberService memberService) {

        registry.forTypePair(UUID.class, Member.class)
            .registerMappedBatchLoader((memberIds, environment) -> {
                GraphQLContext context = (GraphQLContext) environment.getContext();
                TenantContext tenant = context.get("tenantContext");

                return memberService.findByTenantAndIds(
                    tenant.tenantId(), memberIds
                ).collectMap(Member::id);
            });
    }
}
```

Ở đây key là `UUID` và value là `Member`; batch loader lấy tenant context từ GraphQL execution rồi tải dữ liệu theo cả tenant ID và member IDs. Cần đăng ký DataLoader bằng `BatchLoaderRegistry` để nhận lợi ích context propagation của Spring for GraphQL.

Nếu ứng dụng dùng nhiều tenant trong cùng một GraphQL execution (một trường hợp đặc biệt cần thiết kế rõ ràng), không nên giả định một `tenantContext` duy nhất đủ cho mọi key. Khi đó, tenant cần trở thành một phần của key hoặc local context theo từng lần `load`, và batch loader phải phân nhóm theo tenant trước khi truy vấn.

## 12. Tenant isolation trong DataLoader và cache

DataLoader mặc định cache theo key trong phạm vi một GraphQL request. Nếu một execution chỉ có một tenant context bất biến, key resource ID có thể đủ để phân biệt dữ liệu trong request đó, miễn batch loader luôn lọc theo tenant.

Rủi ro lớn hơn thường nằm ở cache dùng chung giữa nhiều request:

- Cache key chỉ có `projectId` có thể trả dữ liệu của tenant A cho tenant B nếu ID không global-unique.
- Cache toàn ứng dụng không được dùng `TenantContext` mutable hoặc `ThreadLocal` để ngầm xác định tenant.
- Cache cần namespace theo tenant, ví dụ `(tenantId, projectId)`.
- Khi đổi membership hoặc quyền, cache phải có invalidation phù hợp.

Ví dụ key value object:

```java
public record TenantProjectKey(String tenantId, UUID projectId) {}
```

Với Caffeine/Redis hoặc cache service, dùng key có tenant ID giúp tránh va chạm giữa các tenant. Không chỉ thêm tenant vào cache key; vẫn phải xác thực và kiểm tra quyền trước khi trả dữ liệu.

## 13. Kết hợp tenant context với authorization

Tenant isolation và authorization là hai lớp khác nhau:

- Tenant isolation bảo đảm request chỉ truy cập dữ liệu thuộc tenant được chọn.
- Authorization kiểm tra user có quyền thực hiện hành động trên tài nguyên trong tenant đó hay không.

Ví dụ người dùng thuộc tenant A có thể chỉ được đọc project do nhóm của họ quản lý. Service có thể dùng method security:

```java
@Service
class ProjectAuthorizationService {

    private final ProjectRepository repository;

    ProjectAuthorizationService(ProjectRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('project:read')")
    public Mono<Project> findByTenantAndId(String tenantId, UUID projectId) {
        return repository.findByTenantIdAndId(tenantId, projectId);
    }
}
```

Ứng dụng cần bật method security, ví dụ bằng `@EnableMethodSecurity` trong cấu hình Spring Security.

`@PreAuthorize` kiểm tra authority tổng quát; điều kiện ownership/tenant vẫn cần được áp dụng trong service hoặc query. Không nên chỉ dựa vào role `USER` hoặc `ADMIN` mà bỏ qua tenant predicate.

Với các thao tác nhạy cảm, có thể trả cùng một kết quả `NOT_FOUND` cho resource không tồn tại và resource thuộc tenant khác để tránh tiết lộ sự tồn tại của dữ liệu ngoài phạm vi. Chính sách này cần thống nhất trong API và log nội bộ.

## 14. Tenant context với Subscription

Subscription có vòng đời dài hơn query thông thường. Tenant context cần được xác định khi client đăng ký subscription và dùng để lọc mọi event phát ra.

Ví dụ:

```java
@SubscriptionMapping
Flux<ProjectEvent> projectEvents(
        @Argument UUID projectId,
        @AuthenticationPrincipal Jwt jwt) {

    TenantContext tenant = tenantContextFactory.from(jwt);

    return projectService.verifyCanRead(tenant, projectId)
        .thenMany(eventPublisher.eventsForTenantProject(
            tenant.tenantId(), projectId));
}
```

Event source phải lọc theo cả tenant ID và project ID. Không nhận `tenantId` từ subscription argument rồi phát mọi event có cùng project ID.

Với WebSocket, authentication có thể được thiết lập qua `AuthenticationWebSocketInterceptor` từ payload `connection_init`. Kết nối dài hạn cần chính sách cho token hết hạn, membership bị thu hồi hoặc user bị chuyển tenant. Có thể đóng stream, yêu cầu reconnect hoặc kiểm tra quyền định kỳ/theo event tùy yêu cầu bảo mật.

## 15. Context propagation và phạm vi sống

`GraphQLContext` gắn với một GraphQL execution. `BatchLoaderRegistry` giúp context được truyền tới batch loading function; các annotated controller có thể đọc bằng `GraphQLContext` hoặc `@ContextValue`.

Không nên lưu tenant context vào:

- Field mutable của `@Controller`, `@Service` hoặc component singleton.
- Static variable dùng chung giữa request.
- `ThreadLocal` tự quản lý mà không có cơ chế context propagation phù hợp.
- Cache global chỉ dựa trên ID tài nguyên.

Trong Spring WebFlux, request có thể chạy qua nhiều thread; không giả định `ThreadLocal` luôn giữ đúng tenant. Dùng `GraphQLContext`, `@ContextValue`, `Principal` hoặc các cơ chế Reactor/Spring Security context được hỗ trợ.

Nếu dùng asynchronous data fetcher hoặc scheduler riêng, cần kiểm tra context propagation tới các tác vụ con. Khi truyền tenant vào service, truyền giá trị tường minh thường dễ hiểu và an toàn hơn phụ thuộc vào thread-local state.

## 16. Defense in depth ở database

Ứng dụng nên áp dụng tenant predicate ở service/repository, nhưng hệ thống có yêu cầu cách ly cao có thể bổ sung lớp bảo vệ ở database:

- Row-Level Security (RLS) để database tự giới hạn hàng theo tenant session/context.
- Database role hoặc schema riêng cho tenant.
- Connection pool/connection routing có tenant-aware configuration.
- Composite foreign key hoặc constraint bảo đảm quan hệ giữa các bảng không nối chéo tenant.

Nếu dùng RLS, phải bảo đảm tenant session variable được đặt an toàn cho từng transaction/connection và được reset trước khi connection quay lại pool. Không để tenant ID từ request trước tồn tại trên connection được tái sử dụng cho request khác.

Database isolation là lớp bảo vệ bổ sung; không thay thế xác thực và authorization ở ứng dụng. Cần kiểm thử cả khi query được gọi trực tiếp qua repository và khi đi qua GraphQL.

## 17. Kiểm thử tenant context và isolation

Kiểm thử nên tập trung vào việc không thể truy cập chéo tenant, kể cả qua field lồng nhau và batch loading.

| Tình huống | Kỳ vọng |
|---|---|
| JWT thuộc tenant A truy vấn danh sách project | Chỉ trả project của A. |
| JWT thuộc tenant A truy vấn ID của project B | Không trả dữ liệu của B; response theo chính sách not-found/forbidden. |
| Client tự gửi `tenantId=B` trong GraphQL argument | Không thay đổi tenant được xác định từ principal. |
| Tenant A truy vấn `Project.members` | Batch query chỉ tải member của A. |
| Hai request A và B chạy đồng thời | Context và cache không trộn dữ liệu. |
| Mutation tạo project | Server tự gán tenant từ context. |
| Mutation update/delete ID của tenant khác | Không thay đổi dữ liệu tenant khác. |
| Subscription theo dõi project | Chỉ phát event thuộc tenant đã xác minh. |
| Token/membership bị thu hồi | Subscription bị dừng hoặc quyền được đánh giá lại theo chính sách. |

Ví dụ kiểm thử resolver/service với principal giả lập:

```java
@GraphQlTest(ProjectController.class)
@Import(TenantContextFactory.class)
class ProjectTenantTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    ProjectService projectService;

    @MockitoBean
    TenantMembershipService tenantMembershipService;

    @Test
    @WithMockUser(username = "alice")
    void loadsProjectsForResolvedTenant() {
        given(tenantMembershipService.findActiveTenantFor("alice"))
            .willReturn(Optional.of(new TenantContext("tenant-a", "alice")));
        given(projectService.findAllForTenant("tenant-a"))
            .willReturn(Flux.just(new Project(
                UUID.randomUUID(), "Project A", "tenant-a")));

        graphQlTester.document("""
                query {
                    projects { name }
                }
                """)
            .execute()
            .path("projects[0].name")
            .entity(String.class)
            .isEqualTo("Project A");

        then(projectService).should().findAllForTenant("tenant-a");
    }
}
```

Đây là ví dụ minh họa; `tenantMembershipService`, model, resolver và cấu hình JWT/principal cần được cung cấp trong test context. `@WithMockUser` tạo principal kiểm thử theo Spring Security; nếu resolver nhận `Jwt`, dùng test security context hoặc mock principal JWT phù hợp thay vì giả định `@WithMockUser` tự tạo `Jwt`.

Ngoài unit/slice test, nên có integration test chạy database thật hoặc Testcontainers để xác minh tenant predicate, transaction và RLS nếu ứng dụng dùng các cơ chế đó.

## 18. Lỗi thường gặp

**Tin `tenantId` do client gửi.** Client có thể sửa argument hoặc header. Xác định tenant từ principal đã xác thực hoặc nguồn gateway đáng tin cậy.

**Chỉ lọc tenant ở query root.** Field lồng nhau, DataLoader, mutation và subscription cũng phải có tenant filter riêng.

**Đưa tenant context vào singleton mutable field.** Request đồng thời có thể ghi đè tenant của nhau. Dùng context theo execution hoặc truyền tenant tường minh.

**Dùng `GraphQLContext` như cache toàn ứng dụng.** Context chỉ thuộc execution; không giữ reference của nó trong service singleton.

**Quên tenant predicate trong batch query.** Batch loading có thể tải nhiều ID cùng lúc; luôn lọc theo tenant trong chính batch repository call.

**Cache global chỉ theo resource ID.** Dùng composite key có tenant ID và kiểm tra quyền trước khi trả cache hit.

**Dùng `@PreAuthorize` thay cho tenant filtering.** Role/authority không tự thêm tenant predicate vào SQL. Cần kiểm tra cả quyền và ownership.

**Không xét subscription dài hạn.** Token hoặc membership có thể thay đổi sau khi subscribe. Xây dựng chính sách thu hồi và kiểm tra quyền.

**Tin ThreadLocal trong WebFlux.** Reactive execution có thể chuyển thread. Dùng `GraphQLContext`, `@ContextValue` và cơ chế context propagation phù hợp.

## Kết luận

Tenant context trong Spring for GraphQL là thông tin theo execution dùng để xác định phạm vi dữ liệu của một tenant. Hãy lấy tenant từ principal/claim đã xác minh hoặc nguồn gateway được bảo vệ, rồi truyền qua `GraphQLContext`, `@ContextValue`, `Principal` hoặc service argument. Áp dụng tenant predicate ở mọi query, mutation, batch loader và subscription; namespace cache theo tenant; kiểm tra authorization trên từng tài nguyên; và kiểm thử đồng thời nhiều tenant để phát hiện rò rỉ dữ liệu. `GraphQLContext` giúp truyền thông tin, còn tenant isolation thực sự phải được bảo đảm ở service, repository và khi cần ở database.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers and `GraphQLContext`](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Web Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Batch Loading and `BatchLoaderRegistry`](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
