# Bảo vệ API theo vai trò và quyền sở hữu tài nguyên trong Spring Data REST

Một API an toàn phải trả lời được hai câu hỏi ở mọi request: người gọi có được phép thực hiện chức năng này không, và họ có được phép thao tác trên đúng tài nguyên được chỉ định không? Phân quyền theo vai trò (role-based access control, RBAC) giải quyết câu hỏi thứ nhất. Kiểm tra quyền sở hữu hoặc quyền trên từng đối tượng giải quyết câu hỏi thứ hai.

Trong Spring Data REST, repository có thể tự động trở thành collection, item, search và association resource. Vì vậy, bảo vệ một URL hoặc một controller không đủ: cùng một entity có thể được truy cập qua nhiều đường dẫn và HTTP method. Hãy thiết kế quyền ở cả lớp request, repository/service và truy vấn dữ liệu; sau đó kiểm thử bằng các tài khoản có vai trò và chủ sở hữu khác nhau.

## 1. Vai trò và quyền sở hữu giải quyết hai loại rủi ro

| Loại kiểm soát | Câu hỏi | Ví dụ |
|---|---|---|
| Vai trò/chức năng | Người dùng có được gọi chức năng này không? | Chỉ ADMIN được xóa tài liệu; USER được đọc tài liệu |
| Quyền trên tài nguyên | Người dùng có quyền với bản ghi cụ thể này không? | Alice chỉ đọc hoặc sửa tài liệu do Alice sở hữu |
| Phạm vi dữ liệu/tenant | Tài nguyên có thuộc tenant hoặc nhóm mà người dùng tham gia không? | Thành viên tenant A không xem được dữ liệu tenant B |
| Quyền trên quan hệ | Người dùng có thể gắn, bỏ hoặc đọc tài nguyên liên kết không? | Người sở hữu dự án mới được thêm thành viên vào dự án |

Nếu chỉ kiểm tra role USER ở endpoint `GET /documents/{id}`, mọi USER có thể thử thay ID để đọc tài liệu của người khác. Đây là Broken Object Level Authorization (BOLA), còn thường được gọi là IDOR. ID tuần tự hay UUID đều không thay thế kiểm tra quyền. Mọi endpoint nhận ID hoặc tham chiếu đối tượng từ path, query, header, body hay HAL link phải kiểm tra quyền trên đối tượng tương ứng.

Một ma trận quyền mẫu:

| Hành động | USER là chủ sở hữu | USER không sở hữu | ADMIN |
|---|---:|---:|---:|
| Đọc item | Cho phép | Từ chối | Cho phép |
| Liệt kê tài nguyên của mình | Cho phép | Chỉ dữ liệu của mình | Cho phép theo chính sách |
| Tạo tài nguyên | Cho phép, server gán owner | Không áp dụng | Cho phép |
| Sửa tài nguyên | Cho phép trường được phép sửa | Từ chối | Cho phép |
| Xóa tài nguyên | Theo chính sách, ví dụ từ chối | Từ chối | Cho phép |
| Đổi owner/tenant | Từ chối | Từ chối | Chỉ quy trình quản trị riêng |

Đây chỉ là ví dụ. Hãy xác định rõ quyền đọc, tạo, cập nhật, xóa, chia sẻ và quản lý quan hệ cho từng loại tài nguyên; không suy ra rằng có quyền đọc thì cũng có quyền sửa hoặc xóa.

## 2. Bảo vệ ở nhiều lớp

Một cấu trúc thường dùng:

1. **Request authorization:** Spring Security xác thực request và chặn các route cần role hoặc authentication.
2. **Method authorization:** `@PreAuthorize` bảo vệ phương thức repository/service; biểu thức có thể kiểm tra role, tham số, principal và quyền trên entity.
3. **Query scope:** truy vấn chỉ trả về bản ghi mà người dùng được xem, ví dụ lọc theo owner hoặc tenant lấy từ Authentication.
4. **Domain invariant:** owner, tenant và các trường nhạy cảm được gán hoặc xác minh ở server; client không thể tự chuyển quyền sở hữu.
5. **Test và audit:** kiểm tra cả request hợp lệ lẫn request cố tình thay ID, owner, relation hoặc query parameter.

Request authorization giúp chặn sớm các nhóm endpoint. Method authorization bảo vệ nghiệp vụ khi cùng một service được gọi từ REST, job nền hoặc luồng khác. Query scope giảm nguy cơ lộ dữ liệu trong collection/search và tránh tải toàn bộ bản ghi rồi mới lọc.

Không dùng URL khó đoán làm cơ chế phân quyền. Không tin `ownerId`, `tenantId`, role hoặc username gửi trong JSON. Danh tính đáng tin cậy phải lấy từ `Authentication`/principal đã được xác thực.

## 3. Cấu hình Spring Security cho HTTP request

Spring Boot Security starter không tự bật method security. Cần khai báo `@EnableMethodSecurity` cho các annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`.

Ví dụ dưới đây giả định Spring Data REST có base path `/api`. Điều chỉnh matcher theo base path và các route thực tế của ứng dụng:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .build();
    }
}
```

Với cấu hình role mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; `hasRole("USER")` kiểm tra `ROLE_USER`. Nếu dùng permission string riêng, dùng `hasAuthority("document:read")` hoặc `hasAuthority("document:write")` để so khớp chính xác authority. Không tự thêm tiền tố `ROLE_` khi gọi `hasRole`.

Các matcher phải được sắp xếp từ cụ thể đến tổng quát. Quy tắc cuối cùng nên yêu cầu authenticated hoặc denyAll để route mới không vô tình được công khai. Request matcher chỉ kiểm tra chức năng/route; nó không tự xác minh người gọi sở hữu ID nằm trong URL.

Nếu ứng dụng dùng JWT/resource server, HTTP Basic hoặc form login, cấu hình cơ chế authentication phù hợp với môi trường. Với API thuần token, trả 401/403 theo hợp đồng JSON đã công bố; không để client phải xử lý redirect HTML ngoài dự kiến.

Không tắt CSRF một cách máy móc. Với browser dùng cookie/session, giữ CSRF protection cho request thay đổi trạng thái. Nếu API dùng bearer token stateless, hãy đánh giá cấu hình CSRF theo cách credential được trình duyệt gửi tự động và kiến trúc xác thực thực tế. CORS chỉ quyết định browser origin nào được phép gửi request; CORS không phải authorization và không thay thế kiểm tra owner.

## 4. Bật method security và bảo vệ repository được export

Spring Data REST hỗ trợ Spring Security method security trên repository interface và từng method. Có thể đặt `@PreAuthorize` ở cấp repository hoặc method. Theo tài liệu Spring Data REST, annotation ở method ghi đè annotation ở repository; hai biểu thức không tự động kết hợp. Vì vậy, khi override một method, hãy viết đầy đủ điều kiện cần có trong biểu thức mới.

Ví dụ dùng mặc định deny và chỉ mở một số method có chủ đích. Giả định entity `Document` có quan hệ `owner.username`, ID kiểu UUID và repository được export tại `/api/documents`:

```java
@RepositoryRestResource(path = "documents")
@PreAuthorize("denyAll")
public interface DocumentRepository
        extends JpaRepository<Document, UUID> {

    @Override
    @PreAuthorize("hasRole('ADMIN') or " +
        "(hasRole('USER') and " +
        "@documentAuthorization.isOwner(#id, authentication.name))")
    Optional<Document> findById(@P("id") UUID id);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    Page<Document> findAll(Pageable pageable);

    @RestResource(path = "by-owner", rel = "by-owner")
    @PreAuthorize("hasRole('ADMIN') or " +
        "(hasRole('USER') and #username == authentication.name)")
    Page<Document> findByOwner_Username(
        @Param("username") String username,
        Pageable pageable
    );

    @RestResource(exported = false)
    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    @Override
    <S extends Document> S save(@P("document") S document);

    @RestResource(exported = false)
    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    boolean existsByIdAndOwner_Username(
        @Param("id") UUID id,
        @Param("username") String username
    );

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(@P("id") UUID id);
}
```

Trong ví dụ này:

- `@PreAuthorize("denyAll")` ở repository chặn các method chưa được mở rõ ràng. `findAll(Pageable)` chỉ cho ADMIN; USER dùng search theo owner.
- `findById` cho ADMIN hoặc USER là owner của đúng ID.
- Search `/api/documents/search/by-owner?username=alice` chỉ cho Alice xem dữ liệu của Alice; ADMIN có thể xem username bất kỳ. Không nhận username từ client rồi tin tưởng mà thiếu biểu thức kiểm tra.
- `save` được ẩn khỏi Spring Data REST bằng `@RestResource(exported = false)`, nhưng được phép gọi nội bộ từ service đã bảo vệ. `existsByIdAndOwner_Username` cũng không được export; nó chỉ hỗ trợ kiểm tra ownership.
- Các method khác không có annotation riêng vẫn bị `denyAll`. Nếu muốn mở thêm API, hãy thêm quy tắc cụ thể cho method đó.

`@P` từ `org.springframework.security.access.method.P` và Spring Data `@Param` giúp đặt tên tham số dùng trong SpEL như `#id`, `#username`. Có thể dùng tên tham số Java nếu biên dịch với `-parameters`, nhưng annotation tường minh giúp interface dễ đọc và ít phụ thuộc cấu hình compiler.

Ví dụ bean kiểm tra owner:

```java
@Component("documentAuthorization")
@RequiredArgsConstructor
public class DocumentAuthorization {

    private final DocumentRepository documents;

    public boolean isOwner(UUID id, String username) {
        return documents.existsByIdAndOwner_Username(id, username);
    }
}
```

Tên property `Owner_Username` là đường dẫn qua quan hệ `owner.username` trong derived query của Spring Data. Điều chỉnh theo tên field entity thật. Phương thức `existsByIdAndOwner_Username` được đánh dấu `exported = false` để không biến helper kiểm tra quyền thành một search endpoint công khai.

Ví dụ minh họa này mở quyền đọc item và query theo owner, cho ADMIN đọc collection và xóa theo ID. Những method chưa khai báo vẫn bị chặn. Khi thêm `saveAll`, `delete`, `deleteAll`, `deleteAllById`, batch operation hoặc custom modifying query, phải quyết định rõ quyền cho từng method. Không giả định chỉ có một đường ghi/xóa. Tập method của `CrudRepository`/`JpaRepository` thay đổi theo phiên bản Spring Data; kiểm tra interface mà ứng dụng đang dùng và khóa mọi đường mutation chưa được phép.

## 5. Kiểm tra ownership trong service và bảo vệ thao tác ghi

Với nghiệp vụ phức tạp, hãy đặt quyền sở hữu ở service và để controller gọi service. Nếu Spring Data REST vẫn export trực tiếp repository, request REST có thể gọi repository proxy mà không đi qua service của bạn. Khi đó phải bảo vệ repository method tương ứng hoặc ẩn đường export và dùng endpoint tùy chỉnh.

Ví dụ service chỉ cho owner hoặc ADMIN sửa tiêu đề:

```java
@Service
@RequiredArgsConstructor
public class DocumentService {

    private final DocumentRepository documents;
    private final UserRepository users;

    @Transactional
    @PreAuthorize("hasRole('ADMIN') or " +
        "(hasRole('USER') and " +
        "@documentAuthorization.isOwner(#id, authentication.name))")
    public Document update(
            @P("id") UUID id,
            UpdateDocumentRequest request) {

        Document document = documents.findById(id)
            .orElseThrow(() -> new EntityNotFoundException());

        document.setTitle(request.title());
        // DTO không có ownerId hoặc tenantId.
        return documents.save(document);
    }

    @Transactional
    @PreAuthorize("hasRole('USER')")
    public Document create(
            CreateDocumentRequest request,
            Authentication authentication) {

        Document document = new Document();
        document.setTitle(request.title());
        document.setOwner(
            users.findByUsername(authentication.getName())
                .orElseThrow(() -> new EntityNotFoundException())
        );
        return documents.save(document);
    }
}
```

Trong ví dụ, repository `save` là method nội bộ đã được ẩn khỏi REST và chỉ cho phép role phù hợp gọi. Endpoint ghi nên được triển khai bằng `@RepositoryRestController` nếu cần nằm dưới base path Spring Data REST, hoặc bằng `@RestController` với route riêng. Controller chỉ nhận DTO có các trường client được phép thay đổi rồi gọi service.

Các nguyên tắc quan trọng cho thao tác ghi:

- **Create:** server lấy user/tenant từ Authentication và tự gán owner. Bỏ qua hoặc từ chối ownerId/tenantId do client gửi.
- **Update/PATCH:** tải hoặc truy vấn bản ghi trong phạm vi người gọi; xác minh owner trước khi thay đổi. DTO chỉ chứa trường được phép sửa, không bind trực tiếp toàn bộ entity.
- **Owner/tenant bất biến:** không cho phép PATCH/PUT đổi owner hoặc tenant. Chuyển quyền sở hữu phải là use case riêng, có quyền quản trị và audit.
- **Delete:** kiểm tra role và ownership trên đúng bản ghi; không chỉ kiểm tra role ở URL.
- **Bulk:** xác minh quyền cho từng ID hoặc giới hạn query theo tenant/owner; một request chứa nhiều ID không được làm lộ hoặc xóa tài nguyên ngoài phạm vi.
- **Association:** khi gắn/bỏ relation qua HAL link, kiểm tra quyền trên cả resource cha và resource được liên kết.

Spring Data REST có các event `BeforeCreate`, `BeforeSave`, `BeforeLinkSave`, `BeforeLinkDelete` và các event liên quan. `@RepositoryEventHandler` với `@HandleBeforeCreate`/`@HandleBeforeSave` có thể dùng để gán owner từ principal hoặc ngăn thay đổi owner. Event handler là nơi giữ invariant cho thao tác đi qua REST exporter; vẫn cần method/service authorization vì service có thể được gọi ngoài REST event flow.

Nếu dùng `@PostAuthorize` để kiểm tra đối tượng trả về, hãy nhớ method đã thực thi và dữ liệu có thể đã được tải trước khi quyền bị từ chối. Với collection lớn, tránh `@PostFilter` tải toàn bộ danh sách rồi mới lọc trong bộ nhớ. Ưu tiên truy vấn có điều kiện owner/tenant ngay trong database. `@PostAuthorize` phù hợp cho một số kiểm tra item sau khi trả về; `@PreAuthorize` hoặc query scoped thường rõ ràng hơn khi cần chặn trước truy cập.

## 6. Bảo vệ mọi đường truy cập tới tài nguyên

Một entity có thể được truy cập qua nhiều resource trong Spring Data REST. Hãy lập danh sách và kiểm tra từng đường sau:

| Đường truy cập | Điều cần kiểm tra |
|---|---|
| API root và collection | Link/rel nào được công bố; GET collection có lọc theo owner/tenant hay chỉ ADMIN |
| Item resource | GET, PUT, PATCH, DELETE có kiểm tra đúng ID và owner |
| Search resource | Từng query method có điều kiện role và owner; không cho đổi username/tenant để đọc dữ liệu người khác |
| Association resource | GET association, PUT/PATCH link, DELETE link kiểm tra quyền trên cả hai phía |
| Custom controller | Có dùng cùng service/policy; không tạo route bỏ qua repository security |
| Batch/import/job | Quyền được kiểm tra trong service; job system có identity và phạm vi rõ ràng |
| Projection/excerpt | Không làm lộ trường nhạy cảm; projection không phải cơ chế authorization |
| HAL link | Việc link xuất hiện không có nghĩa caller được phép thao tác; request theo link vẫn phải kiểm tra quyền |

Không coi việc ẩn link trong HAL, projection hoặc UI là biện pháp bảo vệ. Client có thể tự tạo URL và gửi request. Bảo vệ phải nằm ở server tại điểm thực hiện hành động.

Nếu không muốn tiết lộ một tài nguyên có tồn tại hay không, ứng dụng có thể chọn trả 404 cho cả trường hợp không tồn tại và không thuộc quyền người gọi. Nếu muốn phân biệt tài nguyên có thật nhưng bị cấm, trả 403. Chọn chính sách nhất quán cho API và không để khác biệt response vô tình tiết lộ dữ liệu.

## 7. Kiểm thử quyền theo ma trận

Test cần có ít nhất hai USER khác nhau (Alice và Bob), một ADMIN và request chưa xác thực. Tạo hai tài nguyên với owner khác nhau; dùng ID của Alice để thử request bằng cả Alice, Bob và ADMIN.

Ví dụ với MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId)
                .accept("application/hal+json"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void anotherUserCannotReadDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId)
                .accept("application/hal+json"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId)
                .accept("application/hal+json"))
            .andExpect(status().isOk());
    }
}
```

Các ID trong ví dụ là fixture do test chuẩn bị trước. Nếu ứng dụng dùng chính sách che giấu tài nguyên không thuộc quyền, assertion của Bob phải là 404 thay vì 403.

Bộ test nên bao phủ:

- Anonymous gọi API riêng tư: 401 hoặc response authentication đã công bố.
- USER gọi chức năng chỉ dành cho ADMIN: 403.
- Alice đọc/sửa/xóa tài nguyên của Alice theo chính sách: kết quả đúng.
- Bob dùng ID của Alice với GET, PUT, PATCH và DELETE: bị từ chối.
- Bob đổi `username`, `ownerId`, `tenantId` hoặc nested relation trong query/body: không thể vượt quyền.
- USER truy vấn collection/search: chỉ nhận bản ghi trong phạm vi của mình.
- ADMIN thao tác trên tài nguyên theo quyền quản trị.
- Request sửa owner/tenant bị từ chối hoặc trường đó không được bind.
- Association link không cho gắn tài nguyên thuộc tenant khác.
- Batch request chứa cả ID hợp lệ và ID ngoài phạm vi có kết quả được xác định rõ, không thực hiện một phần ngoài ý muốn.
- Projection và response lỗi không tiết lộ trường nhạy cảm.

Dùng `@WithMockUser(username = "alice", roles = "USER")` để chạy test method/service. Với MockMvc, có thể dùng `with(user("alice").roles("USER"))` trên từng request. Khi CSRF đang bật, request POST/PUT/PATCH/DELETE cần token hợp lệ trong test, ví dụ `with(csrf())`. Nếu test gửi HTTP tới server thật bằng RANDOM_PORT, request chạy ở thread khác; `@WithMockUser` trên thread test không tự truyền Authentication sang server. Khi đó gửi credential/token thật của test qua HTTP request.

Một test trực tiếp gọi service chỉ chứng minh method security ở service. Một test MockMvc chứng minh filter chain, mapping và method security cùng hoạt động qua HTTP. Nên có cả hai cho các luồng quan trọng.

## 8. Các lỗi bảo mật thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| USER đọc được tài nguyên của USER khác | Chỉ kiểm tra authenticated hoặc role, không kiểm tra owner | Thêm object-level check ở method/service hoặc query scoped |
| Collection GET trả dữ liệu của mọi người | `findAll` không được giới hạn; chỉ item endpoint có security | Chặn `findAll` chung và cung cấp query/service chỉ trả dữ liệu của caller |
| Query search vượt tenant | Client truyền owner/tenant tùy ý và server dùng trực tiếp | So sánh với principal hoặc lấy tenant từ Authentication trong service |
| Thêm @PreAuthorize nhưng không có tác dụng | Chưa bật `@EnableMethodSecurity`, bean không được Spring quản lý hoặc gọi nội bộ qua self-invocation | Bật method security; gọi qua Spring proxy; kiểm tra test tích hợp |
| Method override làm mất role ở class | Method-level annotation ghi đè class-level thay vì cộng dồn | Viết lại toàn bộ điều kiện trong annotation ở method |
| Một đường delete vẫn hoạt động | Chỉ bảo vệ `deleteById`, còn `delete`, `deleteAll`, bulk/custom query chưa được xử lý | Khóa mặc định và mở rõ từng mutation signature trong phiên bản repository hiện tại |
| Owner bị thay đổi qua PATCH | DTO/entity binding nhận trường owner từ client | Dùng DTO allowlist; gán owner ở server; kiểm tra BeforeSave và service |
| Search helper xuất hiện thành REST endpoint | Derived query nội bộ được exporter công bố | Đặt `@RestResource(exported = false)` cho helper |
| Association endpoint bỏ qua quyền | Chỉ kiểm tra quyền trên parent hoặc item route | Kiểm tra cả parent lẫn target khi đọc hoặc sửa link |
| Test qua service xanh nhưng REST vẫn hở | Repository exporter gọi repository trực tiếp, không đi qua service | Bảo vệ repository method hoặc ẩn export và route qua controller/service |
| Test dùng @WithMockUser nhưng server thật vẫn 401 | SecurityContext chỉ tồn tại trên thread test | Gửi Basic/Bearer credential trong HTTP request tới server |
| API trả 500 thay vì 403 | AccessDeniedException bị xử lý sai hoặc exception handler tùy biến | Kiểm tra filter chain và exception translation; test status thực tế bằng MockMvc |

## 9. Checklist triển khai

- [ ] Có ma trận role × resource × action cho từng loại entity.
- [ ] Tất cả request private đều được xác thực và route được phân quyền theo nguyên tắc deny by default.
- [ ] Method security đã bật bằng `@EnableMethodSecurity`.
- [ ] Repository/service method có kiểm tra quyền trên đúng tài nguyên.
- [ ] Collection và search query giới hạn theo owner/tenant lấy từ principal.
- [ ] Các inherited CRUD, bulk và custom modifying method đã được kiểm kê; method chưa cho phép vẫn bị chặn.
- [ ] Create gán owner/tenant từ server; update không cho client tự đổi owner/tenant.
- [ ] Association, search, projection, custom controller và batch endpoint đều được kiểm tra.
- [ ] Không dựa vào UUID, URL khó đoán, ẩn link hoặc UI để thay thế authorization.
- [ ] Test chéo Alice/Bob/ADMIN và anonymous cho GET, POST, PUT, PATCH, DELETE, search và association.
- [ ] Test xác minh cả HTTP status lẫn dữ liệu trả về, bao gồm không rò rỉ dữ liệu ngoài phạm vi.
- [ ] CORS, CSRF, authentication và lỗi 401/403 được cấu hình theo mô hình client thực tế.
- [ ] Log/audit ghi nhận principal, hành động, resource ID và kết quả mà không ghi token hoặc bí mật.

## 10. Tài liệu chính thức

- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html) — ví dụ `@PreAuthorize`/`@Secured` trực tiếp trên repository và cách bật method security.
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html) — `BeforeCreate`, `BeforeSave`, `BeforeLinkSave`, `BeforeLinkDelete` và `@RepositoryEventHandler`.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — request matcher, role/authority và quy tắc cuối cùng.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) — `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, custom authorization bean và tham số SpEL.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html) — AuthorizationManager và kiến trúc quyết định quyền.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html) — `@WithMockUser`, `@WithUserDetails` và kiểm thử method authorization.
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/) — tích hợp Spring Security với MockMvc.
- [Spring Security — Running a Test as a User in MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html) — `user()` request post-processor và user giả lập.
- [Spring Security — Testing with CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) — thêm CSRF token cho request thay đổi trạng thái.
- [OWASP API Security Top 10: API1 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) — rủi ro khi API nhận ID nhưng không xác minh quyền trên object.
- [OWASP Web Security Testing Guide: API BOLA](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/12-API_Testing/02-API_Broken_Object_Level_Authorization/) — phương pháp thử thay ID và kiểm tra quyền trên các endpoint.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) — các nguyên tắc bảo vệ REST API.
