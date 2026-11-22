# Kiểm soát việc bật HAL Explorer trong môi trường triển khai

## 1. HAL Explorer làm gì và vì sao cần kiểm soát

HAL Explorer là giao diện web để khám phá REST API dùng HAL hoặc HAL-FORMS. Nó đọc các link hypermedia trong response, cho phép đi từ resource gốc tới collection, item, search và các relation khác; đồng thời hiển thị status, headers và body của response.

HAL Explorer là một API client có khả năng gửi request thay đổi dữ liệu. Tài liệu Spring Data REST mô tả các thao tác GET, POST, PUT, PATCH và DELETE ngay trong giao diện. Vì vậy, cần xem nó như một công cụ vận hành dành cho developer hoặc nhóm hỗ trợ có quyền phù hợp, không phải một trang tài liệu chỉ đọc.

Spring Data REST cung cấp tích hợp riêng qua dependency:

- Maven: org.springframework.data:spring-data-rest-hal-explorer
- Gradle: org.springframework.data:spring-data-rest-hal-explorer

Khi dependency này có trên runtime classpath, Spring Data REST tự cấu hình HAL Explorer tại URI gốc của ứng dụng. Nếu API dùng base path như /api, hãy xác nhận URI thực tế sau khi chạy ứng dụng; giao diện có thể điều hướng hoặc redirect tới root của API.

Điểm cần tách biệt:

- **HAL Explorer là giao diện client.** Nó giúp người dùng khám phá và gọi API.
- **Spring Data REST vẫn là API.** Các repository resource, HAL links và HTTP endpoints tiếp tục hoạt động ngay cả khi bỏ giao diện Explorer.
- **Spring Security mới là nơi quyết định ai được gọi API và được phép làm gì.** Explorer không tạo ra cơ chế phân quyền riêng và không thể thay thế authorization ở server.

## 2. Bật HAL Explorer trong ứng dụng

Nếu đang dùng Spring Boot, phiên bản dependency được quản lý bởi Spring Boot dependency management hoặc Spring Data BOM. Không cần tự ghim version trừ khi dự án chủ động quản lý phiên bản Spring Data.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-rest-hal-explorer</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.data:spring-data-rest-hal-explorer")
}
~~~

Sau khi thêm dependency, chạy ứng dụng và mở URI gốc của Spring Data REST trong trình duyệt. Explorer sẽ đọc HAL document, liệt kê các link và cho phép mở resource theo từng relation.

Nếu chỉ muốn thử nhanh, có thể khởi động ứng dụng ở local:

~~~bash
./mvnw spring-boot:run
~~~

hoặc:

~~~bash
./gradlew bootRun
~~~

Khi dependency không có trên runtime classpath, Spring Data REST vẫn có thể trả HAL JSON tại API root nếu starter Spring Data REST và repository configuration còn được bật. Bỏ HAL Explorer không đồng nghĩa với tắt Spring Data REST.

## 3. Kiểm soát dependency theo môi trường

Tài liệu Spring Data REST mô tả cách kích hoạt Explorer bằng dependency và tự cấu hình giao diện ở URI gốc. Danh sách cấu hình cơ bản của Spring Data REST có các thuộc tính như base path, page size, media type và response body; tài liệu không đưa ra thuộc tính bật/tắt HAL Explorer dạng spring.data.rest.enable-hal-explorer.

Vì vậy, không nên thêm một dòng cấu hình như sau với giả định rằng framework sẽ hiểu nó:

~~~properties
spring.data.rest.enable-hal-explorer=false
~~~

Nếu muốn Explorer chỉ có ở môi trường phát triển hoặc kiểm thử, hãy quản lý dependency trong build configuration.

### Maven profile

Đặt dependency vào profile riêng trong pom.xml:

~~~xml
<profiles>
    <profile>
        <id>dev-hal-explorer</id>
        <dependencies>
            <dependency>
                <groupId>org.springframework.data</groupId>
                <artifactId>spring-data-rest-hal-explorer</artifactId>
            </dependency>
        </dependencies>
    </profile>
</profiles>
~~~

Build có Explorer:

~~~bash
./mvnw -Pdev-hal-explorer package
~~~

Build production không kích hoạt profile:

~~~bash
./mvnw package
~~~

### Gradle property

Với Gradle Groovy DSL, có thể thêm dependency có điều kiện:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")

    if (providers.gradleProperty("enableHalExplorer").orNull == "true") {
        runtimeOnly("org.springframework.data:spring-data-rest-hal-explorer")
    }
}
~~~

Chạy local với Explorer:

~~~bash
./gradlew bootRun -PenableHalExplorer=true
~~~

Build production không truyền property:

~~~bash
./gradlew bootJar
~~~

Runtime-only phù hợp khi ứng dụng không cần tham chiếu trực tiếp tới class của Explorer trong source code. Cách khai báo implementation trong tài liệu Spring Data REST cũng hợp lệ.

### Chọn cách triển khai theo chiến lược artifact

Build profile ở trên tạo ra artifact khác nhau: bản dev có dependency Explorer, bản production không có. Điều này dễ hiểu và dễ kiểm tra, nhưng cần lưu ý nếu quy trình release yêu cầu build một artifact duy nhất rồi promote lần lượt qua dev, staging và production.

Nếu bắt buộc dùng cùng một artifact ở mọi môi trường, hãy chọn một trong các cách sau:

- Đặt Explorer ở một ứng dụng hoặc static host riêng, rồi chỉ mở route đó trong mạng nội bộ.
- Giữ dependency trong artifact nhưng chặn URI giao diện tại reverse proxy hoặc Spring Security ở production. Xác nhận chính xác route trước khi chặn để không vô tình chặn luôn API root.
- Chỉ cho nhóm vận hành có quyền truy cập giao diện, đồng thời áp dụng authorization riêng cho API resource.

Không dùng @Profile để giả định rằng dependency đã biến mất khỏi classpath. Profile của Spring điều khiển bean và cấu hình runtime; nó không tự loại bỏ thư viện đã đóng gói trong artifact.

## 4. Bảo vệ Explorer và API trong production

### Bảo vệ cả giao diện lẫn REST resource

Có hai lớp URL cần kiểm tra:

1. URI phục vụ trang HTML của Explorer.
2. URI API mà Explorer gọi để đọc hoặc thay đổi resource.

Có thể bảo vệ trang Explorer bằng role dành cho developer hoặc nhóm hỗ trợ. API cần có authorization theo resource và operation. Nếu chỉ bảo vệ trang HTML mà API vẫn public, người dùng vẫn có thể gọi API bằng curl hoặc client khác. Ngược lại, nếu API được bảo vệ nhưng trang Explorer public, người dùng chưa đăng nhập có thể nhìn thấy giao diện nhưng các request API sẽ bị từ chối.

Khi cấu hình Spring Security, hãy xác nhận path thực tế của Explorer và API root trước khi viết request matcher. Nếu API base path là /api, URI root và route của Explorer có thể liên quan tới base path đó. Không sao chép matcher chung chung mà chưa kiểm tra mapping của phiên bản đang dùng.

### Phân quyền theo repository và method

Spring Data REST tích hợp với Spring Security. Có thể dùng method-level security như @PreAuthorize để giới hạn quyền ở repository hoặc method cụ thể. Ví dụ:

~~~java
@PreAuthorize("hasRole('ROLE_USER')")
public interface OrderRepository extends CrudRepository<Order, UUID> {

    @PreAuthorize("hasRole('ROLE_ADMIN')")
    @Override
    Optional<Order> findById(UUID id);

    @PreAuthorize("hasRole('ROLE_ADMIN')")
    @Override
    void deleteById(UUID id);
}
~~~

Đây là ví dụ rút gọn để minh họa vị trí đặt quyền. Cần bật method security bằng @EnableMethodSecurity và khai báo đủ các method nhạy cảm của repository.

Lưu ý: method-level security ghi đè repository-level security thay vì cộng dồn với nó. Với thao tác xóa của CrudRepository, cần xem xét tất cả các biến thể delete như deleteById, delete, deleteAll(Iterable) và deleteAll() để không bỏ sót đường gọi.

Nếu một repository nội bộ không nên được xuất thành REST resource, có thể đánh dấu trực tiếp:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends CrudRepository<AuditRecord, UUID> {
}
~~~

Có thể chọn repository detection strategy phù hợp, ví dụ chỉ xuất repository được đánh dấu rõ ràng. Việc này giảm bề mặt API ngay cả khi Explorer không được cài đặt.

### CSRF khi dùng session hoặc cookie authentication

Spring Security bật CSRF protection mặc định cho các HTTP method không an toàn như POST, PUT, PATCH và DELETE. HAL Explorer có thể gửi các method này, nên request phải có CSRF token hợp lệ nếu ứng dụng dùng cơ chế xác thực dựa trên session/cookie và CSRF đang được bật.

Cách xử lý:

- Đảm bảo client lấy được token theo cơ chế CSRF mà ứng dụng cấu hình.
- Gửi token trong request header hoặc parameter theo cấu hình của Spring Security.
- Kiểm thử cả request thiếu token và request có token.
- Không tắt CSRF toàn cục chỉ để Explorer gửi được POST hoặc DELETE.

Với ứng dụng dùng bearer token không tự động được trình duyệt đính kèm, mô hình CSRF có thể khác. Hãy xác định cách credential được gửi và threat model của ứng dụng trước khi thay đổi CSRF configuration.

### CORS khi Explorer chạy khác origin

Nếu Explorer được tích hợp trong cùng Spring Boot application và được phục vụ cùng origin với API, thông thường không cần thêm CORS chỉ để giao diện gọi API đó.

Nếu dùng hosted Explorer hoặc một static host riêng, trình duyệt sẽ áp dụng CORS. API phải trả CORS headers phù hợp cho origin của Explorer. Chỉ cho phép domain, HTTP methods và headers cần thiết; không dùng Access-Control-Allow-Origin: * trong production. Tài liệu HAL Explorer cũng cảnh báo cấu hình wildcard chỉ dành cho development/test.

### TLS và thông tin xác thực

- Dùng HTTPS cho cả giao diện và API.
- Ưu tiên token ngắn hạn và quyền tối thiểu cần thiết.
- Không chia sẻ URL bookmark hoặc ảnh chụp có chứa token hay thông tin xác thực.
- Với HAL Explorer standalone phiên bản mới, tài liệu ghi nhận custom headers có thể được lưu trong URL fragment để khôi phục trạng thái. Hãy kiểm tra đúng phiên bản UI được đóng gói trước khi áp dụng chi tiết này; không đưa token thật vào link chia sẻ hoặc ticket.
- Giới hạn truy cập bằng VPN, mạng nội bộ, reverse proxy allowlist hoặc role vận hành nếu Explorer được giữ lại ở production.

## 5. Cấu hình base path và cách truy cập

Spring Data REST mặc định phục vụ API ở URI gốc. Có thể đổi base path trong application.yml:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
~~~

Khi cấu hình như trên, các resource được xuất sẽ nằm dưới /api. Hãy kiểm tra route giao diện Explorer theo phiên bản dependency đang dùng; không suy luận rằng URI HTML và API root luôn là cùng một path.

Ví dụ kiểm tra bằng curl:

~~~bash
curl -i -H "Accept: text/html" https://example.internal/api/
~~~

Request trên kiểm tra response mà trình duyệt yêu cầu. Để kiểm tra API root độc lập với giao diện:

~~~bash
curl -i -H "Accept: application/hal+json" https://example.internal/api/
~~~

Khi Explorer được bật, response cho browser route thường là HTML hoặc redirect tới trang Explorer theo mapping của dependency. Khi bỏ Explorer, API root vẫn phải trả HAL JSON nếu Spring Data REST còn được bật và request yêu cầu media type HAL.

Nếu app đặt context path ở server.servlet.context-path, reverse proxy rewrite path hoặc ingress prefix, hãy cộng các phần đó vào URL kiểm tra.

## 6. Kiểm thử việc bật/tắt theo môi trường

Không nên chỉ kiểm tra bằng mắt sau khi deploy. Kết hợp kiểm tra build dependency, HTTP response và quyền truy cập.

### Kiểm tra dependency trong artifact

Maven, khi build bản dev:

~~~bash
./mvnw -Pdev-hal-explorer dependency:tree -Dincludes=org.springframework.data:spring-data-rest-hal-explorer
~~~

Maven, khi build production không kích hoạt profile:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-rest-hal-explorer
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-rest-hal-explorer --configuration runtimeClasspath
~~~

Với artifact production, kết quả mong đợi là không có đường dependency tới spring-data-rest-hal-explorer. Có thể kiểm tra executable jar đã đóng gói bằng jar tf và tìm tên artifact trong BOOT-INF/lib.

### Integration test cho API root và giao diện

Ví dụ dùng Spring Boot, MockMvc và Spring Security Test. Điều chỉnh EXPLORER_URI và API_ROOT theo base path và route thực tế của ứng dụng.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HalExplorerExposureTests {

    private static final String EXPLORER_URI = "/";
    private static final String API_ROOT = "/api/";

    @Autowired
    MockMvc mvc;

    @Test
    void apiRootStillReturnsHal() throws Exception {
        mvc.perform(get(API_ROOT).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links").exists());
    }

    @Test
    void explorerEntryIsHtmlWhenIncludedInThisBuild() throws Exception {
        mvc.perform(get(EXPLORER_URI).accept(MediaType.TEXT_HTML))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML));
    }
}
~~~

Test giao diện chỉ nên chạy trong build variant có dependency Explorer. Với build production không có dependency, kiểm tra route Explorer không còn trả trang HTML; nếu API root và Explorer route trùng nhau, vẫn xác nhận request Accept: application/hal+json trả HAL JSON. Một số phiên bản hoặc base-path mapping có thể redirect, vì vậy hãy xác nhận final URI và response của phiên bản cụ thể trước khi cố định assertion.

Lưu ý quan trọng: @ActiveProfiles("dev") chỉ bật cấu hình Spring profile. Nó không thêm dependency vào classpath. Nếu dependency được điều khiển bằng Maven/Gradle build profile, phải chạy test với đúng build profile tương ứng.

### Test quyền truy cập và CSRF

Thêm dependency test của Spring Security nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ kiểm tra request thay đổi dữ liệu có CSRF token:

~~~java
@Test
@WithMockUser(roles = "API_ADMIN")
void authorizedUserCanCreateResourceWithCsrf() throws Exception {
    mvc.perform(post("/api/people")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "firstName": "Grace",
                  "lastName": "Hopper"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

Nên có thêm test cho các trường hợp:

- Anonymous không được đọc API hoặc mở giao diện nội bộ, theo authentication policy.
- User chỉ có quyền đọc không thể POST, PUT, PATCH hoặc DELETE.
- User thiếu quyền xóa nhận 403 khi gọi delete endpoint.
- Request dùng cookie/session thiếu CSRF token bị từ chối; request có token hợp lệ được xử lý theo quyền.
- Nếu Explorer chạy khác origin, preflight từ origin được phép thành công và origin không được phép không nhận CORS permission.

Không tắt filter trong MockMvc test bảo mật; nếu dùng @AutoConfigureMockMvc(addFilters = false), test sẽ bỏ qua chính filter chain cần kiểm chứng.

## 7. Checklist trước khi deploy

- [ ] Xác nhận dependency Explorer có hoặc không có trong runtime classpath của artifact.
- [ ] Xác nhận profile/build variant được chọn đúng cho dev, staging và production.
- [ ] Ghi nhận chính xác URI Explorer, API root, base path và context path.
- [ ] API root trả HAL JSON khi client gửi Accept: application/hal+json.
- [ ] Trang Explorer chỉ được truy cập bởi nhóm được phép.
- [ ] API có authorization ở server; không dựa vào việc ẩn nút trong giao diện.
- [ ] Quyền GET và quyền ghi/xóa được kiểm tra riêng.
- [ ] CSRF được giữ đúng với session/cookie authentication.
- [ ] CORS chỉ mở cho origin cần thiết nếu Explorer được host khác origin.
- [ ] HTTPS được bật; token có thời hạn ngắn và không bị chia sẻ qua URL/log.
- [ ] Repository nội bộ hoặc dữ liệu nhạy cảm không được export ngoài ý muốn.
- [ ] Có test xác nhận trạng thái UI và API sau mỗi lần build/deploy.

## 8. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mở URI gốc nhưng không thấy Explorer | Dependency không có trong runtime classpath hoặc build profile chưa được bật | Kiểm tra dependency tree/dependencyInsight và artifact thực tế |
| Dev có Explorer nhưng production vẫn có | Dependency nằm trong dependencies mặc định thay vì profile riêng, hoặc đang deploy nhầm artifact | Kiểm tra build log, version artifact và runtimeClasspath |
| Không biết thuộc tính nào để tắt Explorer | Đang tìm một property không được tài liệu Spring Data REST công bố | Quản lý dependency theo build variant hoặc chặn route đã xác minh ở security/proxy |
| URI / trả 404 nhưng API nằm ở /api | API base path hoặc server context path đã thay đổi | Kiểm tra spring.data.rest.base-path, server.servlet.context-path và reverse proxy rewrite |
| Browser hiển thị HAL JSON thay vì HTML | Request đang đi tới API representation hoặc route Explorer không được map như dự kiến | Gửi Accept: text/html, kiểm tra URI gốc và mapping của dependency |
| Explorer mở được nhưng API trả 401/403 | UI route và API có security policy riêng; request API thiếu credential hoặc role | Xác nhận authentication header/session và authorization của repository |
| GET chạy được nhưng POST/DELETE trả 403 | Thiếu CSRF token hoặc user không có quyền ghi/xóa | Kiểm tra CSRF header/token và method-level security |
| Request từ hosted Explorer bị CORS block | API chưa cho phép origin của UI hoặc thiếu headers/methods trong preflight | Chỉ cho phép origin, methods và headers cần thiết |
| Người dùng có thể xóa dữ liệu qua Explorer | API cho phép delete với quyền của user đang đăng nhập | Giới hạn quyền delete ở server, kiểm tra tất cả delete methods và dùng role tối thiểu |
| API root không còn sau khi bỏ Explorer | Đã loại nhầm starter Spring Data REST hoặc tắt repository configuration | Chỉ bỏ dependency HAL Explorer; giữ starter và cấu hình Spring Data REST nếu API vẫn cần hoạt động |
| Link chia sẻ chứa credential | UI lưu custom headers trong URL fragment ở một số phiên bản | Không chia sẻ link có token; thu hồi token nếu đã lộ và dùng token ngắn hạn |

Khi chẩn đoán auto-configuration, có thể chạy ứng dụng với --debug để xem điều kiện auto-configuration. Đồng thời kiểm tra runtime dependency tree; đây là cách xác nhận trực tiếp nhất liệu Explorer có nằm trong artifact đang chạy hay không.

## 9. Tài liệu và ví dụ chính thức

- [Spring Data REST Reference — Tools / HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html): dependency Maven/Gradle, cách tự cấu hình UI tại URI gốc, điều hướng HAL và các thao tác GET/POST/PUT/PATCH/DELETE.
- [Spring Data REST Reference — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): Spring Boot starter, auto-configuration, base path và các thuộc tính cấu hình Spring Data REST.
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html): bảo vệ repository và method bằng Spring Security; lưu ý method-level rule ghi đè repository-level rule.
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection mặc định cho unsafe HTTP methods, token repository, request header và tích hợp JavaScript.
- [HAL Explorer Reference Documentation](https://toedter.github.io/hal-explorer/release/reference-doc/): chức năng UI, authentication headers, CORS, thao tác dữ liệu và lưu trạng thái trình duyệt. Đây là tài liệu cho HAL Explorer standalone hiện hành; hãy đối chiếu phiên bản được đóng gói trong spring-data-rest-hal-explorer.
- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): cách Spring Boot kích hoạt và loại trừ auto-configuration.
- [Spring Data REST — Getting Started guide](https://spring.io/guides/gs/accessing-data-rest): ví dụ API HAL, link resource, pagination và gọi CRUD bằng HTTP.
