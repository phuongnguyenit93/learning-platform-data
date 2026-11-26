# Gọi bean có proxy trả về Mono hoặc Flux

Reactive method security chỉ bảo vệ được lời gọi đi qua **Spring-managed proxy**. Khi một service được cấu hình `@EnableReactiveMethodSecurity` và phương thức có `@PreAuthorize`, caller cần gọi bean đã được Spring inject; sau đó kiểm tra publisher `Mono` hoặc `Flux` bằng cách subscribe, chẳng hạn với `StepVerifier`. Tự tạo service bằng `new`, gọi phương thức qua `this`, hoặc bỏ qua proxy có thể khiến interceptor không chạy.

Bài học thuộc module **Spring Security Testing** tập trung vào ranh giới lời gọi này: cách inject và gọi bean có proxy, cách hiểu lỗi authorization trong reactive publisher, cách duy trì `SecurityContext` trong Reactor Context và cách kiểm tra rằng repository/nghiệp vụ không chạy khi user bị từ chối. Ví dụ dùng cả `Mono` và `Flux`, với kiểm thử trực tiếp bằng `StepVerifier` và kiểm thử HTTP bằng `WebTestClient`.

## 1. Vì sao proxy quan trọng?

Spring method security dựa trên AOP interceptor. Khi Spring tạo bean có phương thức được bảo vệ, bean được expose cho caller dưới dạng proxy. Proxy nhận lời gọi, chạy authorization interceptor rồi mới cho phép lời gọi tiếp tục theo chính sách.

~~~mermaid
flowchart TD
    A[Caller inject bean từ Spring] --> B[Proxy nhận lời gọi method]
    B --> C[Target method tạo Mono hoặc Flux]
    C --> D[Interceptor bọc publisher với authorization]
    D --> E[Caller subscribe]
    E --> F{Authentication có quyền?}
    F -- Không --> G[Publisher phát AccessDeniedException]
    F -- Có --> H[Reactive work được subscribe]
    H --> I[Publisher phát dữ liệu hoặc hoàn tất]
~~~

Với reactive method security, method có thể được gọi để tạo publisher; interceptor gắn kiểm tra authorization vào publisher và kiểm tra quyền trong quá trình subscription. Reactive work của publisher chỉ tiếp tục khi authorization cho phép. Vì vậy, không nên chỉ gọi method rồi kết luận quyền đã được kiểm tra:

~~~java
Mono<Report> result = reportOperations.findById(id);
// Publisher mới được tạo; chưa có subscriber để quan sát kết quả.
~~~

Hãy subscribe bằng `StepVerifier`, `WebTestClient` hoặc một subscriber thực tế:

~~~java
StepVerifier.create(reportOperations.findById(id))
    .expectNextCount(1)
    .verifyComplete();
~~~

Nếu user thiếu quyền, subscriber nhận một error signal thay vì dữ liệu. Đây là hành vi reactive; không nhất thiết là một exception đồng bộ được ném ngay tại dòng gọi method.

Vì method có thể chạy phần code Java dùng để lắp ráp publisher trước subscription, hãy tránh thực hiện side effect imperative ngay trong lúc lắp ráp. Đưa thao tác vào `Mono.defer` hoặc `Flux.defer` để chúng chỉ chạy trong pipeline sau khi authorization cho phép.

## 2. Inject bean qua Spring container

Ví dụ service expose interface để caller phụ thuộc vào abstraction:

~~~java
public interface ReportOperations {
    Mono<Report> findById(UUID id);
    Flux<Report> findRecent();
    Mono<Void> archive(UUID id);
}

@Service
class SecuredReportService implements ReportOperations {

    private final ReportRepository repository;

    SecuredReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @Override
    @PreAuthorize("hasAuthority('report:read')")
    public Mono<Report> findById(UUID id) {
        return repository.findById(id);
    }

    @Override
    @PreAuthorize("hasAuthority('report:read')")
    public Flux<Report> findRecent() {
        return repository.findRecent();
    }

    @Override
    @PreAuthorize("hasAuthority('report:archive')")
    public Mono<Void> archive(UUID id) {
        return repository.archive(id);
    }
}
~~~

Trong ví dụ này, annotation đặt trên các method public của implementation. Caller inject `ReportOperations` từ application context:

~~~java
@Service
class ReportFacade {

    private final ReportOperations reports;

    ReportFacade(ReportOperations reports) {
        this.reports = reports;
    }

    Mono<Report> load(UUID id) {
        return reports.findById(id);
    }
}
~~~

`ReportFacade` nhận bean qua constructor injection. Lời gọi `reports.findById(id)` đi qua reference do Spring cung cấp, vì vậy interceptor method security có cơ hội áp dụng. Trong test, cũng inject `ReportOperations` hoặc `ReportFacade` từ context thay vì tự tạo implementation.

Không viết:

~~~java
ReportOperations reports = new SecuredReportService(repository);
~~~

Đối tượng được tạo trực tiếp không đi qua quá trình tạo proxy của Spring. Annotation `@PreAuthorize` vẫn nằm trên method nhưng không có interceptor nào tự động chạy trên object đó.

## 3. Proxy không chặn self-invocation

Một bean gọi method được bảo vệ của chính nó qua `this` sẽ bỏ qua proxy:

~~~java
@Service
class ReportService {

    public Mono<Report> loadForDashboard(UUID id) {
        // Lời gọi nội bộ không quay lại proxy.
        return this.findById(id);
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<Report> findById(UUID id) {
        return repository.findById(id);
    }
}
~~~

Caller bên ngoài gọi `loadForDashboard` qua proxy, nhưng lời gọi `this.findById` diễn ra bên trong target object. Interceptor của `findById` không được kích hoạt chỉ vì method đó có annotation.

Các cách thiết kế phù hợp:

- Tách method được bảo vệ sang một service bean riêng và inject bean đó.
- Để caller gọi trực tiếp method được bảo vệ qua proxy.
- Nếu cần self-reference, dùng một thiết kế proxy-aware được Spring hỗ trợ và kiểm thử rõ ràng; tránh biến việc tự gọi proxy thành phụ thuộc vòng khó bảo trì.

Tương tự, method trên object được tạo bằng `new`, object test fixture không do Spring quản lý, hoặc target object được lấy và gọi trực tiếp đều không có bảo đảm method security.

## 4. Kiểu proxy và chữ ký method

Spring AOP có thể dùng JDK dynamic proxy hoặc class-based proxy. Với JDK proxy, caller thường inject interface; với class-based proxy, Spring tạo subclass của class mục tiêu. Để tránh test phụ thuộc vào chi tiết proxy:

- Inject interface nếu service có interface phù hợp.
- Đặt method bảo vệ ở phạm vi public và gọi qua bean proxy.
- Tránh `final` class/method khi cần class-based proxy.
- Không ép kiểu target object hoặc lấy target từ proxy để gọi trực tiếp.
- Kiểm tra cấu hình proxy của ứng dụng nếu test cho kết quả khác nhau giữa interface và class.

Có thể dùng `AopUtils.isAopProxy` để chẩn đoán trong test:

~~~java
assertThat(AopUtils.isAopProxy(reportOperations)).isTrue();
~~~

Assertion này chỉ xác nhận reference là proxy AOP; nó chưa chứng minh expression authorization đúng hoặc publisher được subscribe đúng cách. Hành vi vẫn cần được kiểm tra bằng test cho user đủ quyền và user thiếu quyền.

## 5. Mono và Flux đều phải được trả về từ method được bảo vệ

Reactive method security cần method trả về reactive publisher để interceptor kết hợp authorization với reactive execution. Những chữ ký phổ biến:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public Mono<Report> findById(UUID id) {
    return repository.findById(id);
}

@PreAuthorize("hasAuthority('report:read')")
public Flux<Report> findRecent() {
    return repository.findRecent();
}

@PreAuthorize("hasAuthority('report:archive')")
public Mono<Void> archive(UUID id) {
    return repository.archive(id);
}
~~~

- `Mono<T>` phát tối đa một phần tử hoặc hoàn tất rỗng.
- `Flux<T>` phát không, một hoặc nhiều phần tử.
- `Mono<Void>` biểu diễn thao tác bất đồng bộ chỉ cần hoàn tất hoặc lỗi.

Đừng chuyển một method reactive thành `void` rồi tự gọi `subscribe()` bên trong:

~~~java
// Không nên: publisher tách khỏi caller và method không trả publisher.
@PreAuthorize("hasAuthority('report:archive')")
public void archive(UUID id) {
    repository.archive(id).subscribe();
}
~~~

Khi method trả `void`, reactive interceptor không có publisher để gắn kiểm tra theo reactive context. Hơn nữa, subscription nội bộ tách lỗi và vòng đời thao tác khỏi caller. Hãy trả `Mono<Void>` để caller kiểm soát subscription và quan sát kết quả.

## 6. Đừng thực hiện side effect trước khi publisher được bảo vệ

Method body có thể được gọi để xây dựng publisher. Vì vậy, không đặt tác dụng phụ imperative trước khi trả `Mono`/`Flux`:

~~~java
@PreAuthorize("hasAuthority('report:archive')")
public Mono<Void> archive(UUID id) {
    auditLog.write("archive requested: " + id); // Side effect eager.
    return repository.archive(id);
}
~~~

Đoạn code trên có thể ghi log/tạo tác dụng phụ trong lúc method được gọi để dựng publisher, trước khi subscriber quan sát kết quả authorization. Hãy đưa công việc vào reactive pipeline:

~~~java
@PreAuthorize("hasAuthority('report:archive')")
public Mono<Void> archive(UUID id) {
    return Mono.defer(() -> {
        auditLog.write("archive requested: " + id);
        return repository.archive(id);
    });
}
~~~

Các lời gọi repository reactive thường chỉ dựng publisher và thực thi khi subscribe, nhưng không nên mặc định mọi thư viện đều lazy. Kiểm tra contract của API và bọc thao tác eager trong `Mono.defer`/`Flux.defer` khi cần. Không gọi `block()` hoặc `subscribe()` bên trong method được bảo vệ.

## 7. SecurityContext phải theo Reactor Context

Trong Reactive, thread có thể thay đổi giữa các operator. Spring Security sử dụng Reactor Context để mang authentication qua pipeline, thay vì dựa vào một `ThreadLocal` cố định.

Nếu service cần đọc user hiện tại:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

Đừng dùng `SecurityContextHolder.getContext()` như trong code imperative rồi mong nó luôn chứa principal trong reactive pipeline. Cũng đừng tự subscribe publisher bên trong service, vì context của caller có thể không còn được liên kết với subscription đó.

Các operator Reactor thông thường duy trì Reactor Context theo semantics của Reactor. Khi tích hợp callback hoặc API async bên ngoài, hãy kiểm tra context propagation; không giả định một callback chạy ngoài pipeline tự động có security context.

`@PreAuthorize` cũng cần authentication từ reactive context để đánh giá expression. Một test có `@WithMockUser` nhưng publisher chạy như anonymous thường là dấu hiệu test context/listener chưa được cấu hình đúng hoặc publisher được subscribe ngoài ngữ cảnh dự kiến.

## 8. Test trực tiếp proxy Mono bằng StepVerifier

Test trực tiếp service giúp xác minh method interceptor mà không cần HTTP layer. Nạp application context có `@EnableReactiveMethodSecurity`, inject interface proxy và dùng `StepVerifier`.

~~~java
@SpringBootTest
class ReportOperationsSecurityTest {

    @Autowired
    ReportOperations reportOperations;

    @Autowired
    ReportRepository reportRepository;

    private static final UUID REPORT_ID =
        UUID.fromString("11111111-1111-1111-1111-111111111111");

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanSubscribeToFindById() {
        StepVerifier.create(reportOperations.findById(REPORT_ID))
            .expectNextMatches(report -> report.id().equals(REPORT_ID))
            .verifyComplete();
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void writerWithoutReadAuthorityIsDenied() {
        StepVerifier.create(reportOperations.findById(REPORT_ID))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Ví dụ giả định test context có repository chứa báo cáo với `REPORT_ID`. Có thể dùng database test hoặc mock repository. Với test dùng mock, nên xác minh repository không được gọi ở ca bị từ chối:

~~~java
verify(reportRepository, never()).findById(REPORT_ID);
~~~

Điều đó chứng minh authorization chặn trước khi truy cập dữ liệu. Nếu test dùng repository thật, thay assertion tương tác bằng cách xác minh không có truy vấn/thay đổi dữ liệu không mong muốn.

### Hỗ trợ Reactor Context trong test

Spring Security Test cung cấp `@WithMockUser` và `ReactorContextTestExecutionListener` để hỗ trợ `@WithMockUser` trong reactive method security. Khi dùng test execution listener mặc định của Spring, listener này được đăng ký bởi cơ chế Spring Security Test. Nếu dự án tùy chỉnh `@TestExecutionListeners` và tắt listener mặc định, cần giữ listener reactive tương ứng.

Một lựa chọn khác là thiết lập authentication tường minh trong Reactor Context:

~~~java
Authentication authentication =
    UsernamePasswordAuthenticationToken.authenticated(
        "lan",
        "N/A",
        List.of(new SimpleGrantedAuthority("report:read"))
    );

StepVerifier.create(
        reportOperations.findById(REPORT_ID)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication)))
    .expectNextCount(1)
    .verifyComplete();
~~~

Cách tường minh hữu ích khi test cần kiểm soát chính xác authentication hoặc không dùng annotation test. Context được gắn vào subscription của publisher; đừng chỉ gọi method rồi thêm context vào một publisher không liên quan.

## 9. Test Flux và Mono<Void>

Với `Flux`, kiểm tra cả số lượng/nội dung phần tử và nhánh bị từ chối:

~~~java
@Test
@WithMockUser(authorities = "report:read")
void readerCanSubscribeToRecentReports() {
    StepVerifier.create(reportOperations.findRecent())
        .expectNextCount(2)
        .verifyComplete();
}

@Test
@WithMockUser(authorities = "report:write")
void writerCannotSubscribeToRecentReports() {
    StepVerifier.create(reportOperations.findRecent())
        .expectError(AccessDeniedException.class)
        .verify();
}
~~~

Với thao tác trả `Mono<Void>`, không dùng `expectNext`; xác minh publisher hoàn tất:

~~~java
@Test
@WithMockUser(authorities = "report:archive")
void archivistCanArchive() {
    StepVerifier.create(reportOperations.archive(REPORT_ID))
        .verifyComplete();
}

@Test
@WithMockUser(authorities = "report:read")
void readerCannotArchive() {
    StepVerifier.create(reportOperations.archive(REPORT_ID))
        .expectError(AccessDeniedException.class)
        .verify();
}
~~~

Nếu phiên bản hoặc cấu hình wrap access denied thành một subtype cụ thể, dùng assertion theo contract exception của dự án, chẳng hạn `expectErrorMatches(error -> error instanceof AccessDeniedException)`. Không đổi lỗi thành success chỉ để test pass.

## 10. WebTestClient kiểm tra lời gọi qua controller tới proxy

Test service trực tiếp chứng minh method security. Để xác minh request WebFlux đi qua HTTP filter chain rồi tới service proxy, dùng `WebTestClient` đã tích hợp Spring Security:

~~~java
@RestController
@RequestMapping("/api/reports")
class ReportController {

    private final ReportOperations reports;

    ReportController(ReportOperations reports) {
        this.reports = reports;
    }

    @GetMapping("/{id}")
    Mono<Report> findById(@PathVariable UUID id) {
        return reports.findById(id);
    }
}
~~~

Test:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReportControllerSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanReadReport() {
        webTestClient
            .mutateWith(mockUser().authorities(
                new SimpleGrantedAuthority("report:read")))
            .get()
            .uri("/api/reports/11111111-1111-1111-1111-111111111111")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void userWithoutReadAuthorityIsDeniedByMethodSecurity() {
        webTestClient
            .mutateWith(mockUser().authorities(
                new SimpleGrantedAuthority("report:write")))
            .get()
            .uri("/api/reports/11111111-1111-1111-1111-111111111111")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Hai test giả định URL rule yêu cầu authentication nhưng cho user đã đăng nhập qua tới controller; service mới yêu cầu `report:read`. Nếu URL rule từ chối trước, test không chứng minh method security. Hãy giữ URL policy đủ để request hợp lệ đi tới controller và dùng quyền khác nhau để cô lập method authorization.

## 11. Phân biệt lỗi HTTP với lỗi method security

Một request bị từ chối có thể bị chặn ở nhiều tầng:

| Quan sát | Nguyên nhân có thể | Cách tách biệt |
| --- | --- | --- |
| Anonymous nhận `401`/redirect trước controller | HTTP authentication | Dùng mock user để kiểm tra method layer riêng. |
| User đã đăng nhập nhưng URL trả `403` trước controller | HTTP authorization | Cho URL qua với user đã xác thực rồi kiểm tra service method. |
| URL qua nhưng publisher service phát access denied | Reactive method security | Gọi trực tiếp proxy bằng StepVerifier hoặc xác minh controller đã gọi service. |
| Repository không được gọi | Có thể method security chặn trước nghiệp vụ | Xác minh user/token và test đối chứng đủ quyền. |
| Repository được gọi dù method bị từ chối | Side effect eager, lời gọi bypass proxy hoặc annotation không được áp dụng | Kiểm tra proxy, self-invocation và cách tạo publisher. |

Method security không thay thế HTTP security. Một service được bảo vệ vẫn có thể bị gọi từ các URL không có authentication policy phù hợp; ngược lại, URL `authenticated()` không bảo đảm caller có authority nghiệp vụ.

## 12. Những lỗi phổ biến khi gọi bean có proxy

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Annotation có nhưng method vẫn chạy | Caller gọi object được tạo bằng `new` | Inject bean từ Spring context. |
| Lời gọi ngoài bị chặn, lời gọi nội bộ không bị chặn | Self-invocation qua `this` | Tách method sang bean khác hoặc gọi qua proxy. |
| Test không nhận access denied | Publisher chưa subscribe | Dùng StepVerifier/WebTestClient để kích hoạt và quan sát publisher. |
| Test nhận lỗi đồng bộ khác dự kiến | Method thực hiện side effect/eager work trước khi trả publisher | Đưa công việc vào `Mono.defer`/`Flux.defer`. |
| Context không có user | Subscription không mang Reactor Context | Dùng `@WithMockUser` với listener reactive hoặc `contextWrite`. |
| Repository vẫn chạy ở nhánh denied | Lời gọi bypass proxy hoặc tác dụng phụ eager | Kiểm tra proxy và xác minh repository invocation. |
| Method `void` không được bảo vệ theo reactive semantics | Không trả Publisher | Trả `Mono<Void>` và để caller subscribe. |
| Proxy không intercept method | Method/class `final`, visibility hoặc kiểu proxy không phù hợp | Dùng method public và inject qua interface/proxy phù hợp. |

## 13. Checklist kiểm thử lời gọi proxy

- [ ] Service là bean do Spring quản lý.
- [ ] Cấu hình `@EnableReactiveMethodSecurity` được nạp trong test context.
- [ ] Caller inject bean qua Spring, tốt nhất qua interface phù hợp.
- [ ] Method bảo vệ trả `Mono`, `Flux` hoặc Publisher reactive được hỗ trợ.
- [ ] Lời gọi đi qua proxy, không gọi target trực tiếp hoặc self-invocation.
- [ ] Publisher được subscribe bằng StepVerifier hoặc WebTestClient.
- [ ] Authentication có mặt trong Reactor Context.
- [ ] Có test user đủ quyền và user thiếu quyền.
- [ ] Nhánh bị từ chối phát access denied và repository/service không tạo tác dụng phụ.
- [ ] Side effect được đặt trong pipeline, không chạy eager trước authorization.
- [ ] HTTP authorization được tách khỏi method authorization trong test.

## Bài tập thực hành

Một `InvoiceOperations` bean có hai method:

- `Mono<Invoice> findById(UUID id)` yêu cầu `invoice:read`.
- `Mono<Void> approve(UUID id)` yêu cầu `invoice:approve`.

Hãy viết test:

1. Inject bean từ Spring context và xác nhận reference là proxy AOP.
2. User có `invoice:read` subscribe `findById` và nhận invoice.
3. User chỉ có `invoice:approve` subscribe `findById` và nhận access denied.
4. User có `invoice:approve` subscribe `approve` và publisher hoàn tất.
5. User chỉ có `invoice:read` subscribe `approve` và nhận access denied.
6. Xác minh repository không được gọi ở các ca bị từ chối.
7. Gọi method qua một facade bean khác và xác minh lời gọi vẫn đi qua proxy.
8. Tạo một ví dụ self-invocation, quan sát giới hạn proxy, rồi refactor method sang bean riêng.

**Tự kiểm tra:** Vì sao `reportOperations.findById(id)` chưa đủ để kết luận authorization đã được kiểm tra? Vì method trả một publisher; test phải subscribe để quan sát kết quả hoặc error signal trong reactive pipeline.

## Ghi nhớ

Hãy gọi method được bảo vệ qua **bean proxy do Spring inject**, và để caller subscribe `Mono`/`Flux`. Reactive method security gắn authorization với publisher và dùng Reactor Context để lấy authentication. Tự tạo object, gọi qua `this`, trả `void` rồi tự subscribe, hoặc thực hiện side effect eager có thể làm test bỏ qua ranh giới bảo vệ. Dùng `StepVerifier` cho service, `WebTestClient` cho toàn luồng HTTP, và xác minh repository không chạy khi quyền bị từ chối.
