# Bật reactive method security đúng cấu hình mục tiêu

Trong ứng dụng Spring WebFlux, bảo vệ URL bằng `SecurityWebFilterChain` chưa chắc đã bảo vệ mọi nơi gọi service. Một service có thể được gọi từ controller, message handler, scheduled task hoặc một bean khác. **Reactive method security** đặt kiểm tra authorization ngay tại phương thức service, giúp chính sách quyền được áp dụng ở ranh giới nghiệp vụ.

Để bật cơ chế này, cấu hình ứng dụng bằng `@EnableReactiveMethodSecurity` và đặt annotation như `@PreAuthorize` trên các phương thức trả về kiểu reactive. Cấu hình này khác với `@EnableWebFluxSecurity`: một bên bảo vệ lời gọi phương thức, bên còn lại bảo vệ request HTTP. Module **Spring Security Testing** sử dụng `spring-security-test`, `@WithMockUser`, `SecurityContext`, `StepVerifier` và `WebTestClient` để kiểm tra các nhánh được phép hoặc bị từ chối trên Servlet và Reactive; bài này tập trung vào cấu hình đúng cho nhánh Reactive.

## 1. Reactive method security bảo vệ điều gì?

Reactive method security kiểm tra quyền khi một phương thức được gọi qua Spring-managed proxy và trả về một reactive publisher như `Mono` hoặc `Flux`. Thay vì chỉ hỏi “request có được vào URL không?”, nó hỏi “principal hiện tại có được thực hiện hành động nghiệp vụ này không?”.

Ví dụ:

- `GET /reports/{id}` có thể được phép ở tầng URL, nhưng service chỉ cho người có authority `report:read` đọc báo cáo.
- `POST /reports` có thể được định tuyến tới controller, nhưng service yêu cầu `report:write`.
- Một bean khác gọi cùng service cũng phải đi qua method security nếu lời gọi đi qua proxy và có reactive security context phù hợp.

Annotation thường dùng để bắt đầu là `@PreAuthorize`:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public Mono<Report> findById(UUID id) {
    return repository.findById(id);
}
~~~

Khi caller không có authority yêu cầu, publisher kết thúc bằng lỗi access denied và phần nghiệp vụ không được thực thi. Khi caller có quyền, publisher tiếp tục phát kết quả như bình thường.

## 2. Bật bằng @EnableReactiveMethodSecurity

Đặt annotation trên một lớp cấu hình được Spring nạp vào application context:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Annotation này bật các interceptor cần thiết để Spring áp dụng reactive method authorization. Chỉ khai báo annotation trong một lớp không được component scan hoặc không được import vào context thì chưa đủ; test và ứng dụng phải thực sự nạp cấu hình đó.

Trong dự án Spring Boot dùng WebFlux, các dependency nền tảng thường gồm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Dùng Spring Boot dependency management hoặc Spring Security BOM để các artifact tương thích phiên bản. Không ghép tùy tiện các phiên bản Spring Security khác nhau.

### Không nhầm với @EnableWebFluxSecurity

Hai annotation có nhiệm vụ khác nhau:

| Cấu hình | Phạm vi bảo vệ |
| --- | --- |
| `@EnableWebFluxSecurity` | HTTP request đi qua WebFlux security web filter chain; ví dụ path, authentication, HTTP authorization. |
| `@EnableReactiveMethodSecurity` | Lời gọi phương thức reactive được Spring AOP proxy bảo vệ; ví dụ `@PreAuthorize` trên service. |

Ứng dụng WebFlux thường cần cả hai nếu muốn bảo vệ cả request HTTP lẫn ranh giới service:

~~~java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class ApplicationSecurityConfiguration {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ trên thể hiện hai lớp cấu hình cùng tồn tại. Nếu ứng dụng dùng OAuth2 Resource Server, form login hoặc cơ chế khác, thay phần HTTP authentication theo thiết kế thực tế. Không cần bật `@EnableWebFluxSecurity` chỉ để kiểm tra một service method trong test đơn vị; nhưng `@EnableReactiveMethodSecurity` phải có trong context của service đó.

Ngược lại, `@EnableReactiveMethodSecurity` **không tự cấu hình URL security**. Nếu không có WebFlux security filter chain, annotation trên service không thay thế chính sách HTTP.

## 3. Dùng @PreAuthorize trên service trả Mono hoặc Flux

Ví dụ service quản lý báo cáo:

~~~java
public record Report(UUID id, String title) {
}

@Service
class ReportService {

    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('report:read')")
    Mono<Report> findById(UUID id) {
        return repository.findById(id);
    }

    @PreAuthorize("hasAuthority('report:write')")
    Mono<Report> create(CreateReport command) {
        return repository.save(new Report(
            UUID.randomUUID(),
            command.title()
        ));
    }

    @PreAuthorize("hasRole('EDITOR')")
    Flux<Report> findAllForEditor() {
        return repository.findAll();
    }
}
~~~

Các method được bảo vệ trả `Mono` hoặc `Flux`, tức là reactive publisher. `@PreAuthorize` kiểm tra quyền trước khi publisher được phép tiếp tục xử lý. Có thể dùng role hoặc authority:

- `hasRole('EDITOR')` thường kiểm tra authority `ROLE_EDITOR`.
- `hasAuthority('report:write')` kiểm tra đúng chuỗi `report:write`.
- `@WithMockUser(roles = "EDITOR")` tạo authority `ROLE_EDITOR`.
- `@WithMockUser(authorities = "report:write")` tạo authority đúng như khai báo, không tự thêm `ROLE_`.

Chọn cách khai báo trùng với quy ước quyền của ứng dụng. Không dùng `roles` cho một authority tùy chỉnh rồi thắc mắc vì sao test bị từ chối.

### Phương thức phải đi qua proxy của Spring

Method security dựa trên Spring AOP. Để interceptor hoạt động:

- Service phải là bean do Spring quản lý.
- Caller phải gọi method qua proxy mà Spring tạo.
- Không gọi method được bảo vệ bằng self-invocation như `this.findById(id)` từ một method khác trong cùng bean rồi kỳ vọng proxy chặn lời gọi nội bộ đó.
- Cần chú ý kiểu proxy và giới hạn của method/class `final`; với proxy dựa trên interface, caller phải sử dụng interface proxy expose.

Ví dụ self-invocation dễ gây hiểu nhầm:

~~~java
@Service
class ReportService {

    public Mono<Report> loadForDashboard(UUID id) {
        // Lời gọi this.* không đi qua Spring proxy.
        return this.findById(id);
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<Report> findById(UUID id) {
        return repository.findById(id);
    }
}
~~~

Nếu cần áp dụng cùng một chính sách, tách phương thức được bảo vệ sang một bean khác hoặc thiết kế lời gọi qua proxy công khai. Không dựa vào self-invocation để kiểm tra authorization.

## 4. SecurityContext trong Reactive nằm ở Reactor Context

Trong ứng dụng imperative, nhiều cơ chế bảo mật truyền `SecurityContext` qua `ThreadLocal`. Với Reactive, một request có thể chạy qua nhiều thread và scheduler; vì vậy Spring Security lưu security context trong **Reactor Context**.

Điều này ảnh hưởng trực tiếp đến cách viết service:

- Dùng các cơ chế reactive-aware của Spring Security để đọc principal.
- Không giả định `SecurityContextHolder.getContext()` luôn chứa user khi đang ở reactive pipeline.
- Không gọi `block()` hoặc tự `subscribe()` trong service chỉ để đọc authentication.
- Không tách publisher khỏi context rồi mong authorization tiếp tục thấy cùng principal.

Ví dụ lấy tên người dùng hiện tại:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

`ReactiveSecurityContextHolder` đọc context từ subscription hiện tại. Các operator Reactor thông thường duy trì context theo quy tắc Reactor; khi tự tạo publisher hoặc chuyển sang một cơ chế bất đồng bộ khác, hãy bảo đảm security context được truyền theo cách được hỗ trợ.

`@PreAuthorize` trong reactive method security cũng sử dụng context reactive để đánh giá authentication. Nếu test method security không nhìn thấy user, kiểm tra Reactor context test support và cách publisher được subscribe.

## 5. Kiểm tra trực tiếp service bằng StepVerifier

Test trực tiếp service giúp tách method security khỏi routing và HTTP filter. Dùng `@SpringBootTest` để nạp cấu hình `@EnableReactiveMethodSecurity`, rồi kiểm tra publisher bằng `StepVerifier`.

Ví dụ:

~~~java
@SpringBootTest
class ReportServiceMethodSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanFindReport() {
        StepVerifier.create(reportService.findById(UUID.fromString(
                "11111111-1111-1111-1111-111111111111")))
            .expectNextMatches(report -> report.title().equals("Quarterly"))
            .verifyComplete();
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void writerWithoutReadAuthorityIsDenied() {
        StepVerifier.create(reportService.findById(UUID.fromString(
                "11111111-1111-1111-1111-111111111111")))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Ví dụ giả định repository trả về báo cáo có tiêu đề `Quarterly` trong test context. Có thể dùng test repository hoặc mock phù hợp; điều cần chứng minh là:

- User có `report:read` nhận được kết quả.
- User chỉ có `report:write` không thể đọc nếu thiếu `report:read`.
- Nhánh bị từ chối phát lỗi access denied trong publisher.

### Đảm bảo test listener đưa authentication vào Reactor Context

Spring Security Test cung cấp `@WithMockUser` và `ReactorContextTestExecutionListener` để hỗ trợ test reactive method security. Khi dùng test execution listener mặc định của Spring, listener cần thiết được đăng ký theo cơ chế Spring Security Test. Nếu dự án khai báo `@TestExecutionListeners` tùy chỉnh và tắt listener mặc định, hãy bảo đảm `ReactorContextTestExecutionListener` vẫn được đăng ký.

Một dấu hiệu cấu hình test chưa đúng là `@WithMockUser` xuất hiện trên test method nhưng reactive publisher vẫn chạy như anonymous. Kiểm tra listener/context trước khi sửa expression hoặc nới quyền trong service.

## 6. Kiểm tra qua WebTestClient khi cần kiểm thử toàn luồng

Test service trực tiếp chứng minh method interceptor. Nếu cần xác minh request WebFlux, authentication ở HTTP layer và method security cùng hoạt động, dùng `WebTestClient` đã tích hợp Spring Security.

Ví dụ controller gọi service:

~~~java
@RestController
@RequestMapping("/api/reports")
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{id}")
    Mono<Report> find(@PathVariable UUID id) {
        return reportService.findById(id);
    }
}
~~~

Test qua WebTestClient:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReportEndpointMethodSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanGetReport() {
        webTestClient
            .mutateWith(mockUser().authorities(
                new SimpleGrantedAuthority("report:read")))
            .get()
            .uri("/api/reports/11111111-1111-1111-1111-111111111111")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void userWithoutReadAuthorityIsForbidden() {
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

Các static import tương ứng thuộc `SecurityMockServerConfigurers.mockUser`. Cần bảo đảm WebTestClient đã được cấu hình Spring Security và application context nạp reactive method security. Với test WebFlux slice, import cấu hình method security và service cần thiết; với full integration test, nạp application context thực tế.

Trong test này, request có thể vượt qua URL authorization nhưng vẫn bị service method từ chối. Đây là cách kiểm tra ranh giới nghiệp vụ mà HTTP matcher đơn thuần không thể thay thế.

## 7. URL authorization và method authorization không thay thế nhau

Một ứng dụng có thể bảo vệ cùng endpoint ở hai lớp:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/reports/**").authenticated()
    .anyExchange().permitAll());
~~~

Và ở service:

~~~java
@PreAuthorize("hasAuthority('report:read')")
Mono<Report> findById(UUID id) {
    return repository.findById(id);
}
~~~

Hai lớp giải quyết mục tiêu khác nhau:

| HTTP authorization | Reactive method authorization | Kết quả |
| --- | --- | --- |
| Không đăng nhập | Bất kỳ | HTTP security từ chối trước controller. |
| Đã đăng nhập | Thiếu `report:read` | Request qua URL rule, service từ chối. |
| Đã đăng nhập | Có `report:read` | Cả hai lớp cho phép. |
| `permitAll()` ở URL | Thiếu `report:read` | URL cho qua, service vẫn từ chối. |

`permitAll()` không vô hiệu hóa `@PreAuthorize`. Tương tự, một service method được bảo vệ không tự đảm bảo mọi URL khác trong ứng dụng đều có HTTP security phù hợp.

## 8. Chọn đúng annotation và đúng kiểu ứng dụng

| Tình huống | Cấu hình nên xem xét |
| --- | --- |
| Ứng dụng WebFlux, service trả `Mono`/`Flux` | `@EnableReactiveMethodSecurity` |
| Ứng dụng Servlet/imperative, service trả giá trị đồng bộ | `@EnableMethodSecurity` |
| WebFlux cần bảo vệ cả URL và service | `@EnableWebFluxSecurity` cùng `@EnableReactiveMethodSecurity` |
| Chỉ cần kiểm tra service reactive trực tiếp | Nạp `@EnableReactiveMethodSecurity` trong test context |
| Ứng dụng hybrid có cả Servlet và Reactive context | Cấu hình từng security context đúng loại; không dùng một annotation thay thế cho context còn lại |

Không dùng `@EnableMethodSecurity` như lựa chọn thay thế mặc định cho reactive method security. Cơ chế imperative thường dựa trên thread-bound security context; reactive method security cần context-aware cho Reactor. Nếu service trả kiểu đồng bộ trong một ứng dụng WebFlux, đừng mặc định `@EnableReactiveMethodSecurity` sẽ bảo vệ method đó theo cách reactive; hãy xác định ranh giới và chọn cơ chế method security phù hợp.

Các annotation authorization bổ sung và cách chúng hoạt động có thể phụ thuộc phiên bản Spring Security. Khi sử dụng `@PostAuthorize`, filtering hoặc annotation JSR-250, kiểm tra tài liệu phiên bản và test đúng kiểu trả về; bài này dùng `@PreAuthorize` làm mẫu cơ bản, ổn định cho reactive service.

## 9. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@PreAuthorize` không chặn method | Chưa bật `@EnableReactiveMethodSecurity` hoặc config không được nạp | Kiểm tra application context và component scan/import. |
| User có quyền nhưng vẫn bị từ chối | Role/authority không khớp expression | Kiểm tra `hasRole` so với `hasAuthority` và tiền tố `ROLE_`. |
| `@WithMockUser` không có hiệu lực trong test reactive | Reactor context test listener không được đăng ký | Kiểm tra `ReactorContextTestExecutionListener` và test execution listeners. |
| Lời gọi nội bộ bỏ qua annotation | Self-invocation không đi qua proxy | Tách method sang bean khác hoặc gọi qua proxy. |
| Method đồng bộ không được reactive interceptor bảo vệ | Method không trả Publisher | Chọn cấu hình method security phù hợp với kiểu method. |
| HTTP request bị từ chối trước service | WebFlux HTTP authorization hoặc authentication từ chối | Xác minh HTTP chain trước khi đánh giá method security. |
| Service chạy nhưng context không có principal | Publisher bị tách khỏi Reactor Context hoặc tự subscribe sai cách | Duy trì reactive chain và dùng `ReactiveSecurityContextHolder`. |
| Test chỉ chạy khi gọi `.block()` | Test không subscribe đúng cách hoặc đang dùng sai API | Dùng `StepVerifier`/`WebTestClient` và tránh block trong reactive service. |

Không sửa lỗi context bằng cách gọi `subscribe()` bên trong service hoặc lấy user từ `SecurityContextHolder` kiểu imperative. Những cách đó có thể làm mất quan hệ giữa request, publisher và security context.

## 10. Checklist bật reactive method security

- [ ] Ứng dụng thực sự dùng WebFlux/reactive stack cho các method cần bảo vệ.
- [ ] Dependency Spring Security tương thích với phiên bản Spring Boot/Spring Framework.
- [ ] Cấu hình `@EnableReactiveMethodSecurity` được nạp vào application context.
- [ ] HTTP security được cấu hình riêng bằng `@EnableWebFluxSecurity` khi cần bảo vệ URL.
- [ ] Service là Spring bean và lời gọi đi qua proxy.
- [ ] Phương thức được bảo vệ trả `Mono`, `Flux` hoặc Publisher phù hợp.
- [ ] Expression dùng đúng role/authority của ứng dụng.
- [ ] Code đọc principal dùng `ReactiveSecurityContextHolder` khi cần.
- [ ] Test reactive có Reactor context test support.
- [ ] Có test user đủ quyền, thiếu quyền và anonymous theo mục tiêu.
- [ ] Có test trực tiếp service bằng StepVerifier và test HTTP bằng WebTestClient khi cần.
- [ ] Không dùng `@EnableMethodSecurity` thay thế tùy tiện cho reactive method security.

## Bài tập thực hành

Một service `InvoiceService` có các phương thức:

- `Mono<Invoice> findById(UUID id)` yêu cầu authority `invoice:read`.
- `Mono<Invoice> approve(UUID id)` yêu cầu authority `invoice:approve`.

Hãy bật reactive method security và viết test:

1. User có `invoice:read` đọc invoice thành công.
2. User chỉ có `invoice:approve` không được đọc invoice.
3. User có `invoice:approve` phê duyệt invoice thành công.
4. User chỉ có `invoice:read` không được phê duyệt invoice.
5. Gọi endpoint WebFlux qua WebTestClient để chứng minh URL authentication và method authorization hoạt động ở hai lớp.

**Tự kiểm tra:** Nếu chỉ thêm `@EnableWebFluxSecurity` mà không bật `@EnableReactiveMethodSecurity`, annotation `@PreAuthorize` trên service có được kích hoạt không? Không. HTTP security và reactive method security là hai cấu hình riêng.

## Ghi nhớ

Bật reactive method security bằng `@EnableReactiveMethodSecurity` trong application context, đặt `@PreAuthorize` trên Spring-managed service method trả `Mono`/`Flux`, và bảo đảm lời gọi đi qua proxy. Security context của Reactive nằm trong Reactor Context, vì vậy test nên dùng `StepVerifier`, `@WithMockUser` có reactive context support hoặc `WebTestClient` với mock user. `@EnableWebFluxSecurity` bảo vệ HTTP; `@EnableReactiveMethodSecurity` bảo vệ phương thức nghiệp vụ. Khi ứng dụng cần cả hai lớp, cấu hình và kiểm thử cả hai một cách riêng biệt.
