# Xác minh không đọc hoặc ghi tài nguyên trái phép dù status đã đúng

Trong kiểm thử phân quyền HTTP, một phản hồi `401`, `403` hoặc `404` chỉ chứng minh **mã trạng thái mà phía client nhận được**. Nó chưa chứng minh tài nguyên được bảo vệ an toàn. Một API có thể trả `403 Forbidden` nhưng vẫn đưa thông tin bí mật vào response body, đã ghi thay đổi vào cơ sở dữ liệu, đã phát một sự kiện nghiệp vụ hoặc đã thực hiện lời gọi đến dịch vụ ngoài trước khi từ chối yêu cầu.

Bài này tập trung vào cách chứng minh điều ngược lại bằng `spring-security-test`: người dùng không có quyền **không đọc được dữ liệu** và **không gây được thay đổi nghiệp vụ**, trong khi người được phép vẫn thao tác bình thường. Kỹ thuật áp dụng cho Spring Security trên Servlet với `MockMvc`, và được mở rộng sang Reactive với `WebTestClient`.

## 1. Xác định điều phải chứng minh

Giả sử hệ thống quản lý ghi chú cung cấp hai endpoint:

- `GET /api/notes/{id}`: xem nội dung ghi chú.
- `PATCH /api/notes/{id}`: thay đổi nội dung ghi chú.

`alice` và `bob` đều đăng nhập hợp lệ, đều có vai trò `USER`, nhưng mỗi người chỉ sở hữu ghi chú của mình. Nếu `alice` đoán được ID ghi chú của `bob`, yêu cầu vẫn phải bị ngăn chặn. Đây là trường hợp điển hình của **Broken Object Level Authorization (BOLA)**, thường được gọi là IDOR khi ID tài nguyên bị dùng để truy cập trái phép.

Một ca kiểm thử phân quyền nên chứng minh đồng thời các bất biến sau:

| Lớp bằng chứng | Câu hỏi cần trả lời | Quan sát trong test |
|---|---|---|
| HTTP | Yêu cầu bị từ chối theo chính sách chưa? | Status là `401`, `403` hoặc `404` được hệ thống chủ đích sử dụng |
| Dữ liệu trả về | Nội dung/metadata bí mật có bị lộ không? | Body, header, cookie, URL chuyển hướng, thông điệp lỗi không chứa dữ liệu của tài nguyên |
| Trạng thái lưu trữ | Có ghi trái phép dù đã từ chối không? | Bản ghi và các bản ghi liên quan giữ nguyên giá trị trước yêu cầu |
| Tác dụng phụ | Có email, event, job, upload hoặc lời gọi bên ngoài nào được thực thi không? | Không có tác vụ nghiệp vụ ngoài ý muốn; các bản ghi audit cho lần từ chối vẫn có thể được phép |
| Đối chứng dương | Người thực sự có quyền có sử dụng được chức năng không? | Cùng endpoint với danh tính được cấp quyền trả dữ liệu/ghi thành công |

**Nguyên tắc kiểm thử:** `status đúng` là một điều kiện; `không lộ dữ liệu` và `không đổi trạng thái` là các điều kiện độc lập. Một test chỉ kiểm tra `status().isForbidden()` có thể xanh trong khi lỗ hổng vẫn tồn tại.

### Các kiểu vượt quyền cần bao phủ

| Tình huống | Ví dụ | Kết quả cần chứng minh |
|---|---|---|
| Chưa đăng nhập | Gọi API không có danh tính | Bị chặn và không đọc/ghi |
| Vượt quyền ngang | `alice` truy cập ghi chú của `bob` | Không có nội dung của `bob`; không ghi vào ghi chú của `bob` |
| Vượt quyền dọc | `USER` gọi API chỉ dành cho `ADMIN` | Không thực hiện hành động quản trị |
| Thiếu scope | Token chỉ có `notes.read` gọi API ghi | Không được cập nhật dù token hợp lệ |
| Sai tenant | Người thuộc tổ chức A thử ID của tổ chức B | Không lộ hoặc sửa dữ liệu tổ chức B |
| Truy vấn danh sách | `GET /api/notes` lọc sai quyền sở hữu | Danh sách không chứa ID/nội dung của người khác |
| Ghi hàng loạt | Một request gửi ID được phép lẫn ID bị cấm | Không để lọt bất kỳ cập nhật trái phép nào; làm rõ chính sách atomic/partial success |
| Quyền theo trường | Người được xem hồ sơ nhưng không được xem trường nhạy cảm | DTO/JSON không chứa trường bị hạn chế |

Mã `404` đôi khi được dùng để che giấu sự tồn tại của tài nguyên. Nếu hợp đồng API chọn chính sách này, hãy assert `404`; không ép mọi trường hợp sai chủ sở hữu phải trả `403`. Bất kể chọn status nào, vẫn cần kiểm tra không rò rỉ thông tin và không phát sinh ghi trái phép.

## 2. Vì sao test chỉ kiểm tra status có thể tạo cảm giác an toàn giả

Xét một cách xử lý sai về thứ tự:

```java
@PatchMapping("/api/notes/{id}")
ResponseEntity<Void> edit(@PathVariable UUID id,
                          @RequestBody EditNoteRequest request) {
    noteRepository.updateText(id, request.text()); // Đã ghi trước
    if (!currentUserCanEdit(id)) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
    }
    return ResponseEntity.noContent().build();
}
```

Test sau có thể **PASS sai**:

```java
mockMvc.perform(patch("/api/notes/{id}", anotherUserNoteId)
        .with(user("alice"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"INJECTED\"}"))
    .andExpect(status().isForbidden());
```

Dù response là `403`, việc cập nhật đã xảy ra. Những lỗi tương tự có thể phát sinh khi:

- Controller hoặc service bắt `AccessDeniedException` sau khi đã gọi repository.
- Phân quyền được áp dụng cho endpoint lấy chi tiết nhưng bị quên ở endpoint cập nhật, xóa hoặc xuất tệp.
- DTO chứa trường bí mật trước khi bộ lọc phản hồi loại bỏ chúng; đường dẫn lỗi vẫn vô tình serialize DTO.
- Việc kiểm tra chỉ xét role `USER` mà không xét **chủ sở hữu tài nguyên** hoặc tenant.
- Mã nghiệp vụ phát thông báo, sự kiện hoặc gửi request ra ngoài trước khi xác minh quyền.

Sửa lỗi gốc bằng cách kiểm tra quyền trước thao tác nghiệp vụ cần bảo vệ và đồng thời giới hạn truy vấn theo quyền khi phù hợp. Sau đó viết test kiểm tra **đầu ra và trạng thái tồn tại thực sự**.

## 3. Dựng một ví dụ Servlet có phân quyền theo chủ sở hữu

Ví dụ dùng Spring Boot 3.x, Spring Security 6.x, `MockMvc` và JPA. Khi dùng phiên bản Boot khác, để Spring Boot quản lý phiên bản thư viện Security tương ứng.

### 3.1. Phụ thuộc cho dự án Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Tạo datasource kiểm thử riêng (ví dụ H2) để các ca ghi/đọc không đụng dữ liệu thật. `spring-security-test` cung cấp `@WithMockUser`, request post-processor `user()`, `csrf()`, `jwt()` và các công cụ giả lập ngữ cảnh bảo mật. Phụ thuộc này phải nằm trong phạm vi test.

### 3.2. Entity, repository và response DTO

Đoạn mã dưới đây bỏ qua package/import để tập trung vào quan hệ giữa các lớp; từng kiểu cần đặt trong file Java phù hợp.

```java
@Entity
@Table(name = "notes")
public class Note {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String text;

    protected Note() {}

    public Note(UUID id, String ownerUsername, String text) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.text = text;
    }

    public UUID getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }
}
```

```java
public interface NoteRepository extends JpaRepository<Note, UUID> {
    boolean existsByIdAndOwnerUsername(UUID id, String ownerUsername);
}

public record NoteResponse(UUID id, String text) {}

public record EditNoteRequest(String text) {}
```

API không trả entity JPA trực tiếp. `NoteResponse` chỉ có những trường client được phép nhận. Trong hệ thống thực tế, tránh để DTO lộ token, secret, địa chỉ riêng hoặc trường của tenant khác.

### 3.3. Chính sách bảo vệ request và phương thức nghiệp vụ

```java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class NoteSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/notes/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Ở cấu hình minh họa này, request cần đăng nhập mới qua được lớp HTTP. Phân quyền đối tượng được xử lý thêm ở service, nơi có thể đối chiếu danh tính với ID thật. Cấu hình giữ **CSRF mặc định**, vì vậy các bài test `PATCH` hợp lệ về mặt request phải gửi token CSRF bằng `.with(csrf())`. Với API dùng bearer token hoàn toàn không dựa trên cookie/session, dự án có thể thiết kế CSRF theo mô hình stateless của mình; không sao chép tùy tiện thao tác tắt CSRF sang ứng dụng web dùng session.

```java
@Component("noteOwnership")
public class NoteOwnership {

    private final NoteRepository repository;

    public NoteOwnership(NoteRepository repository) {
        this.repository = repository;
    }

    public boolean owns(Authentication authentication, UUID id) {
        return authentication != null
                && authentication.isAuthenticated()
                && repository.existsByIdAndOwnerUsername(
                        id, authentication.getName());
    }
}
```

```java
@Service
public class NoteService {

    private final NoteRepository repository;

    public NoteService(NoteRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@noteOwnership.owns(authentication, #id)")
    public NoteResponse read(@P("id") UUID id) {
        Note note = repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
        return new NoteResponse(note.getId(), note.getText());
    }

    @Transactional
    @PreAuthorize("@noteOwnership.owns(authentication, #id)")
    public void updateText(@P("id") UUID id, String text) {
        Note note = repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
        note.setText(text);
    }
}
```

`@P("id")` là annotation `org.springframework.security.core.parameters.P`; nó giúp SpEL đọc tên tham số `#id` ổn định cả khi cấu hình compiler không bật `-parameters`. Ở service, `@PreAuthorize` ngăn việc gọi thân phương thức với tài nguyên không thuộc quyền sở hữu. Với ứng dụng multi-tenant, phép kiểm tra phải xác thực **cả tenant và quyền trên đối tượng**, lấy tenant/membership từ ngữ cảnh tin cậy phía server thay vì tin hoàn toàn vào `tenantId` trong request.

```java
@RestController
@RequestMapping("/api/notes")
public class NoteController {

    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public NoteResponse read(@PathVariable UUID id) {
        return service.read(id);
    }

    @PatchMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void updateText(@PathVariable UUID id,
                           @RequestBody EditNoteRequest request) {
        service.updateText(id, request.text());
    }
}
```

Mẫu này dùng kiểm soát ở cả lớp HTTP và lớp nghiệp vụ. Nếu nghiệp vụ được gọi qua job, message consumer hoặc controller khác, chính sách ở service vẫn có cơ hội bảo vệ tài nguyên. Tránh gọi một phương thức `@PreAuthorize` qua `this.method()` trong cùng bean, vì lời gọi nội bộ có thể bỏ qua Spring AOP proxy.

## 4. Kiểm thử tích hợp: kiểm tra cả response và dữ liệu đã lưu

Với bài toán xác minh quyền trên đối tượng, ưu tiên nạp **SecurityFilterChain, controller, service, chính sách và repository thật**. `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` giúp bài test đi qua luồng Servlet Security và lưu dữ liệu vào database kiểm thử.

```java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class NoteAuthorizationIT {

    private static final UUID ALICE_ID =
            UUID.fromString("11111111-1111-4111-8111-111111111111");
    private static final UUID BOB_ID =
            UUID.fromString("22222222-2222-4222-8222-222222222222");

    @Autowired
    MockMvc mockMvc;

    @Autowired
    NoteRepository repository;

    @BeforeEach
    void setUp() {
        repository.deleteAll();
        repository.saveAll(List.of(
                new Note(ALICE_ID, "alice", "ALICE_PRIVATE"),
                new Note(BOB_ID, "bob", "BOB_SECRET_MARKER")
        ));
    }

    @Test
    void anonymousCannotRead() throws Exception {
        mockMvc.perform(get("/api/notes/{id}", BOB_ID))
                .andExpect(status().isUnauthorized())
                .andExpect(content().string(
                        not(containsString("BOB_SECRET_MARKER"))));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCannotReadBobsNoteEvenThoughBothAreUsers()
            throws Exception {
        mockMvc.perform(get("/api/notes/{id}", BOB_ID))
                .andExpect(status().isForbidden())
                .andExpect(content().string(
                        not(containsString("BOB_SECRET_MARKER"))));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCannotChangeBobsNoteEvenWhenCsrfIsValid()
            throws Exception {

        String before = repository.findById(BOB_ID)
                .orElseThrow().getText();

        mockMvc.perform(patch("/api/notes/{id}", BOB_ID)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"TAMPERED\"}"))
                .andExpect(status().isForbidden())
                .andExpect(content().string(
                        not(containsString("BOB_SECRET_MARKER"))));

        String after = repository.findById(BOB_ID)
                .orElseThrow().getText();

        assertThat(after).isEqualTo(before);
        assertThat(after).isEqualTo("BOB_SECRET_MARKER");
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCanReadHisOwnNote() throws Exception {
        mockMvc.perform(get("/api/notes/{id}", BOB_ID))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(BOB_ID.toString()))
                .andExpect(jsonPath("$.text").value("BOB_SECRET_MARKER"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCanUpdateHisOwnNote() throws Exception {
        mockMvc.perform(patch("/api/notes/{id}", BOB_ID)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"BOB_NEW_TEXT\"}"))
                .andExpect(status().isNoContent());

        assertThat(repository.findById(BOB_ID).orElseThrow().getText())
                .isEqualTo("BOB_NEW_TEXT");
    }
}
```

Các static import chính để đọc ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Những phần khác dùng import thông thường từ JUnit Jupiter, Spring Boot Test, Spring Test, Spring Security Test, JPA, `java.util.List` và `java.util.UUID`. Ví dụ giả định profile `test` có datasource test phù hợp, JPA tạo bảng hoặc migration đã chạy. Không đánh dấu toàn bộ lớp test là `@Transactional` nếu muốn quan sát rõ transaction và thời điểm ghi thực sự; khi dùng JPA có cache phiên lưu trữ, có thể cần `flush`, `clear` hoặc đọc ở một transaction mới để kiểm chứng trạng thái trong database.

Điểm mấu chốt nằm ở test `aliceCannotChangeBobsNoteEvenWhenCsrfIsValid`:

1. Lấy snapshot giá trị thật trước request.
2. Gửi một request **đủ điều kiện CSRF** để `403` phát sinh từ chính sách sở hữu, không phải từ việc thiếu CSRF.
3. Assert response bị từ chối và không chứa thông tin bí mật.
4. Đọc lại repository sau request; chứng minh giá trị không thay đổi.
5. Dùng test đối chứng với `bob` để xác minh endpoint vẫn hoạt động cho người được phép.

Một lỗi ghi trước rồi mới trả `403` sẽ làm bước 4 thất bại. Một lỗi chặn nhầm toàn bộ `PATCH` bằng CSRF có thể làm test âm tính xanh, nhưng sẽ bị test đối chứng dương phát hiện.

**Giới hạn của ví dụ:** H2/JPA và bảng `notes` chỉ minh họa một tài nguyên. Nếu ứng dụng dùng transaction phân tán, cache, storage, event bus hoặc dịch vụ ngoài, snapshot một cột là chưa đủ để kết luận toàn bộ nghiệp vụ không thay đổi.

## 5. Đo đúng tác dụng phụ: database, event, audit và dịch vụ ngoài

Với thao tác như `POST /orders/{id}/approve`, kiểm tra `status=403` và `orders.status` không đổi vẫn có thể bỏ sót email đã gửi hoặc message đã phát. Hãy mô tả trước **tất cả trạng thái quan trọng** mà thao tác hợp lệ được phép thay đổi:

| Hành động khi được phép | Điều phải bất biến khi bị từ chối | Cách đo |
|---|---|---|
| Sửa ghi chú | Nội dung và thời điểm cập nhật không đổi | Query lại bản ghi trong DB |
| Xóa tài liệu | Tài liệu và file object storage vẫn tồn tại | Kiểm tra DB và object storage giả lập |
| Duyệt đơn | Trạng thái, tồn kho, số dư không đổi | Snapshot các bảng liên quan |
| Phát sự kiện | Không có event nghiệp vụ `NoteUpdated` | Spy/mock tại cổng phát, hoặc kiểm tra outbox |
| Gửi email | Không gọi dịch vụ gửi email | Verify tương tác cổng ngoài |
| Xếp lịch tác vụ | Không có task nghiệp vụ ngoài ý muốn | Kiểm tra queue hoặc fake scheduler |

Ví dụ, nếu `NoteService` có thêm một cổng `NotificationGateway`, có thể dùng spy/mock cho **cổng bên ngoài** trong bài kiểm thử tích hợp:

```java
// Phần mở rộng minh họa: gateway được service gọi khi update thành công.
@MockitoBean
NotificationGateway notificationGateway;

@Test
@WithMockUser(username = "alice")
void deniedUpdateDoesNotNotify() throws Exception {
    mockMvc.perform(patch("/api/notes/{id}", BOB_ID)
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"text\":\"TAMPERED\"}"))
            .andExpect(status().isForbidden());

    verify(notificationGateway, never()).noteChanged(any());
}
```

`@MockitoBean` được dùng trong các bản Spring Framework/Spring Boot mới có annotation này; dự án Boot cũ có thể dùng `@MockBean` theo phiên bản hiện có. Cần thêm gateway vào ứng dụng trước khi chạy ví dụ mở rộng. **Đừng mock toàn bộ `NoteService` hoặc `NoteOwnership` rồi kết luận đã kiểm thử được chính sách thực**: việc mock mất cả logic phân quyền là nguyên nhân phổ biến gây test xanh giả.

Việc ghi audit cho yêu cầu bị từ chối (ví dụ `AccessDeniedAttempt`) có thể là hành vi **được mong đợi**. Vì vậy, khẳng định không có *tác dụng phụ nghiệp vụ bị cấm* thay vì khẳng định tuyệt đối không có bất kỳ ghi log, metric hoặc audit nào.

Đối với thao tác bất đồng bộ, chỉ xác minh ngay sau response có thể bỏ sót tác dụng phụ đến trễ. Hãy chờ một tín hiệu hoàn tất có giới hạn, dùng fake queue/clock hoặc kiểm chứng outbox. Không dựa vào `Thread.sleep` tùy ý để chứng minh không có message.

## 6. Từ chối đọc: không chỉ nhìn response body

Có ít nhất ba nguồn lộ thông tin cần phân biệt:

**Lộ dữ liệu trong response:** API trả `403` nhưng chứa phần JSON đã dựng trước đó hoặc phản hồi lỗi kèm object, stack trace, thông tin nội bộ. Kiểm tra body, header và cookie với các giá trị marker riêng của tài nguyên. `status=404` cũng không bảo đảm response trống an toàn.

**Lộ qua endpoint khác:** Endpoint chi tiết bị chặn, nhưng `/api/notes?owner=bob`, `/api/notes/export`, `/api/notes/{id}/history`, `/api/notes/{id}/attachments` hoặc tìm kiếm vẫn hiển thị dữ liệu. Kiểm thử ma trận endpoint, nhất là list/search/export/bulk.

**Lộ qua phân trang và metadata:** Danh sách có thể không chứa nội dung bản ghi của `bob` nhưng trả tổng số lượng toàn hệ thống, ID, tên file, thumbnail hoặc đường dẫn tải xuống. Hãy định nghĩa rõ phạm vi được lộ theo chính sách rồi assert những trường liên quan.

Ví dụ với endpoint danh sách, `200 OK` là hoàn toàn hợp lệ; điều quan trọng là **tập kết quả đã lọc đúng**:

```java
@Test
@WithMockUser(username = "alice")
void listContainsOnlyNotesVisibleToAlice() throws Exception {
    mockMvc.perform(get("/api/notes"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[*].id",
                    not(hasItem(BOB_ID.toString()))))
            .andExpect(content().string(
                    not(containsString("BOB_SECRET_MARKER"))));
}
```

Đoạn trên chỉ là biến thể khi ứng dụng có thêm `GET /api/notes`; endpoint này không nằm trong controller tối giản ở mục 3. Khi triển khai nó, lọc theo quyền **tại tầng truy vấn** (ví dụ `findByOwnerUsername(...)` kết hợp tenant) và phân trang trên tập được phép, thay vì nạp toàn bộ tài nguyên rồi lọc tùy tiện ở response.

Ngoài `containsString`, có thể parse JSON thành DTO/`JsonNode` để assert chính xác danh sách trường và giá trị. Kiểm tra marker bí mật là lớp kiểm thử bổ sung có ích, không thay thế việc kiểm tra schema dữ liệu được phép xuất.

## 7. Phân biệt lỗi xác thực, phân quyền và CSRF

Một `403` có nhiều nguồn gốc. Nếu yêu cầu `PATCH` không có CSRF trong ứng dụng dùng session, Spring Security có thể chặn ở `CsrfFilter` **trước khi logic phân quyền đối tượng được chạy**. Khi đó test `403` không chứng minh được `alice` bị ngăn sửa ghi chú của `bob`.

So sánh hai ca:

```java
// Kiểm tra CSRF: thiếu token nên request bị chặn.
mockMvc.perform(patch("/api/notes/{id}", BOB_ID)
        .with(user("bob"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"NEW\"}"))
    .andExpect(status().isForbidden());

// Kiểm tra quyền sở hữu: cung cấp CSRF hợp lệ.
mockMvc.perform(patch("/api/notes/{id}", BOB_ID)
        .with(user("alice"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"NEW\"}"))
    .andExpect(status().isForbidden());
```

Cả hai có thể trả `403`, nhưng đang chứng minh **hai cơ chế khác nhau**. Để kiểm chứng đúng chính sách sở hữu, test âm tính phải loại trừ rào cản không liên quan; test dương của `bob` phải thành công.

Các điểm cần quan sát:

- `401 Unauthorized` thường đại diện cho việc chưa được xác thực trong một REST API dùng HTTP Basic/Bearer; cấu hình form login có thể redirect `302`, nên kỳ vọng phải theo cấu hình entry point của ứng dụng.
- `403 Forbidden` thường đại diện cho đã được xác thực nhưng không đủ quyền hoặc thiếu CSRF; không suy diễn nguyên nhân chỉ từ status.
- `404 Not Found` có thể dùng cho tài nguyên không tồn tại **hoặc** tài nguyên bị cố ý che giấu. Kiểm tra thêm không lộ dữ liệu và không sửa tài nguyên.
- `@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN`; `@WithMockUser(authorities = "SCOPE_notes.write")` tạo authority **đúng chuỗi đó**. `hasRole("ADMIN")` và `hasAuthority("SCOPE_notes.write")` không tương đương.
- `@WithMockUser` đặt danh tính vào security context kiểm thử; nó không chứng minh password, HTTP Basic decoder, Bearer JWT decoder hoặc OIDC login thực sự vận hành đúng.

## 8. JWT, OAuth2 và OIDC: mô phỏng đúng loại danh tính

Nếu API thực dùng OAuth2 Resource Server, kiểm thử *phân quyền* có thể dùng `SecurityMockMvcRequestPostProcessors.jwt()` thay cho `@WithMockUser`. Điều này giúp xây dựng subject, scope và claims giống trường hợp thực tế.

```java
mockMvc.perform(get("/api/notes/{id}", BOB_ID)
        .with(jwt()
                .jwt(token -> token.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_notes.read"))))
    .andExpect(status().isForbidden())
    .andExpect(content().string(
            not(containsString("BOB_SECRET_MARKER"))));
```

Với access checker ở mục 3, `authentication.getName()` tương ứng với subject của `JwtAuthenticationToken` mặc định. Khi ứng dụng ánh xạ principal sang claim khác, test phải mô phỏng đúng mapping thực tế. Tránh giả định rằng claim `sub`, `preferred_username`, `user_id` và ID chủ sở hữu trong DB luôn trùng nhau.

Khi một endpoint yêu cầu scope, chính sách có thể biểu diễn như:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_notes.write') " +
    "and @noteOwnership.owns(authentication, #id)")
```

Với chính sách đó, cần kiểm thử hai tình huống **độc lập**: token của chủ sở hữu thiếu `SCOPE_notes.write` và token đủ scope nhưng dùng ID của người khác. Nếu chỉ thử một trường hợp, có thể bỏ sót lỗi ở điều kiện còn lại. Lưu ý: thay `@PreAuthorize` như trên là phần mở rộng minh họa, nên các test `@WithMockUser(roles="USER")` của mục 4 phải được cập nhật authority tương ứng.

`jwt()` dựng ngữ cảnh xác thực phục vụ kiểm thử authorization; nó **không xác minh chữ ký, expiry, issuer, audience hay đường đi của `JwtDecoder` thật**. Dùng một nhóm integration test riêng với cấu hình resource server thực tế hoặc decoder kiểm thử có chủ đích để chứng minh token không hợp lệ bị chặn **trước** khi nghiệp vụ chạy. Chỉ khi chạy được cả hai nhóm mới có bằng chứng về xác thực token và phân quyền đối tượng.

Với đăng nhập OAuth2/OIDC qua browser, Spring Security Test còn có `oauth2Login()` và `oidcLogin()`. Chúng tạo user/principal giả lập để test chính sách theo authorities và OIDC claims; chúng không mô phỏng toàn bộ lần chuyển hướng tới identity provider. Khi logic phân quyền đọc claim như `tenant_id`, `groups` hoặc `email_verified`, test phải đặt claim rõ ràng và kiểm chứng mapping mà ứng dụng thực sự dùng.

## 9. Reactive: cùng bất biến, khác cách thiết lập security context

Với Spring WebFlux, dùng `WebTestClient` đã được tích hợp Spring Security, thay vì `MockMvc`. Trên WebFlux, ngữ cảnh bảo mật lưu trong Reactor context; test nên dùng `SecurityMockServerConfigurers.mockUser()` hoặc `mockJwt()` cho request.

Ví dụ dưới đây giả định ứng dụng Reactive có endpoint tương tự, repository reactive và cấu hình `SecurityWebFilterChain`/`@EnableReactiveMethodSecurity` thích hợp:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveNoteAuthorizationIT {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveNoteRepository repository;

    private static final UUID BOB_ID =
            UUID.fromString("22222222-2222-4222-8222-222222222222");

    @Test
    void aliceCannotReadBobsNote() {
        var result = client.mutateWith(mockUser("alice"))
                .get()
                .uri("/api/notes/{id}", BOB_ID)
                .exchange()
                .expectStatus().isForbidden()
                .expectBody()
                .returnResult();

        byte[] bytes = result.getResponseBody();
        String body = bytes == null ? "" :
                new String(bytes, StandardCharsets.UTF_8);

        assertThat(body).doesNotContain("BOB_SECRET_MARKER");
    }

    @Test
    void aliceCannotModifyBobsNote() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .patch()
                .uri("/api/notes/{id}", BOB_ID)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"text\":\"TAMPERED\"}")
                .exchange()
                .expectStatus().isForbidden();

        StepVerifier.create(repository.findById(BOB_ID))
                .assertNext(note -> assertThat(note.getText())
                        .isEqualTo("BOB_SECRET_MARKER"))
                .verifyComplete();
    }
}
```

Các static import cho ví dụ Reactive:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Với token JWT giả lập trong WebFlux, thay `mockUser("alice")` bằng `mockJwt().jwt(jwt -> jwt.subject("alice"))` và thêm authorities/claims cần thiết. Chỉ sử dụng `.mutateWith(...)` như trên khi client được bind tới ứng dụng qua cơ chế test Spring WebFlux. Nếu `WebTestClient` gửi HTTP ra một máy chủ thực qua mạng, security context mock tại phía client không tự truyền tới server; khi đó phải gửi credentials/token thật trên HTTP.

Cần có fixture `bob` trong database reactive trước test và một ca đối chứng với chủ sở hữu thật. Nếu WebFlux tắt CSRF vì dùng token stateless, điều chỉnh ví dụ theo cấu hình đó; không để một `403` từ CSRF che mất lỗi kiểm tra quyền đối tượng. Đối với request ghi Reactive, sau khi response hoàn tất vẫn phải xác minh trạng thái bên dưới và các tác dụng phụ bất đồng bộ tương ứng.

## 10. Ma trận test không chỉ có “được phép” và “bị cấm”

Một bộ test đủ sức phát hiện lỗi thông thường nên ghép **danh tính**, **quyền chức năng**, **quyền đối tượng**, **loại thao tác** và **chứng cứ hậu điều kiện**. Ví dụ:

| Danh tính | Quyền chức năng | Tài nguyên | Request | Kỳ vọng và bằng chứng |
|---|---|---|---|---|
| Anonymous | Không có | Của Bob | `GET` | `401` theo cấu hình Basic; không lộ nội dung |
| Alice | `USER` | Của Bob | `GET` | `403` theo ví dụ; body không chứa marker của Bob |
| Alice | `USER` | Của Bob | `PATCH` + CSRF | `403`; DB của Bob giữ nguyên |
| Bob | `USER` | Của Bob | `GET` | `200`; chỉ trường được phép |
| Bob | `USER` | Của Bob | `PATCH` + CSRF | `204`; DB thay đổi đúng dự kiến |
| Alice | Thiếu scope ghi | Của Alice | `PATCH` | `403`; DB giữ nguyên, khi đã bật chính sách scope |
| Alice | Có scope ghi | Của Bob | `PATCH` | `403`; quyền đối tượng vẫn chặn |
| User tenant A | Đủ role | Của tenant B | `GET`/`PATCH` | Bị chặn; không rò rỉ/không thay đổi dữ liệu B |
| Alice | Đủ quyền đọc | Nhiều tài nguyên | `GET /api/notes` | `200`; chỉ trả tập tài nguyên Alice được xem |

Kiểm thử nên có thêm trường hợp **tài nguyên không tồn tại**, **ID được đoán**, **ID trong URL khác ID trong body**, **thay đổi chủ sở hữu giữa chừng**, **bulk API** và **tải tệp bằng URL** nếu sản phẩm hỗ trợ. Với nhiều tenant, tạo fixture có cùng tên người dùng ở các tenant khác nhau để phát hiện kiểm tra owner thiếu điều kiện tenant.

Đặc biệt, một request sửa nhiều bản ghi cần chính sách rõ ràng: từ chối toàn bộ theo transaction hay chấp nhận cập nhật từng bản ghi được phép. Test phải chứng minh chính xác quy tắc đã thiết kế, không mặc định status `207`/`403` bảo đảm tính nguyên tử.

## 11. Các dấu hiệu test xanh giả cần xử lý

| Dấu hiệu | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ assert `isForbidden()` | Không biết DB hoặc body có lộ/đổi không | Assert thêm body, trạng thái, event |
| `PATCH` bị `403` nhưng không gửi CSRF | Có thể đang test `CsrfFilter`, không phải object authorization | Gửi `.with(csrf())` rồi thử cả owner hợp lệ |
| Mock `NoteService` khi chính service giữ `@PreAuthorize` | Bỏ qua hoặc thay thế logic phân quyền thật | Dùng service thật; mock riêng cổng ngoài |
| Dùng `MockMvcBuilders.standaloneSetup(...)` không gắn Security | Bỏ qua SecurityFilterChain | Dùng `@AutoConfigureMockMvc` hoặc `.apply(springSecurity())` với cấu hình test phù hợp |
| Dùng `@WithMockUser` để kết luận JWT thật được xác minh | Không chạy token decoder/chữ ký | Tách test JWT authentication qua filter và test authorization |
| Gán sai `roles`/`authorities` | Test chạy với quyền khác production | Kiểm tra `ROLE_`, `SCOPE_` và claim mapping |
| Chỉ test request bị từ chối, không test request được phép | Endpoint luôn từ chối cũng cho test xanh | Thêm đối chứng dương với owner/quyền đúng |
| Test ghi chạy trong transaction test hoặc đọc entity còn trong cache | Dễ hiểu sai trạng thái DB thực sự sau request | Đọc lại qua transaction/persistence context độc lập |
| Kiểm tra response nhưng bỏ qua các endpoint tải tệp, search, export | Rò rỉ qua đường khác vẫn còn | Bao phủ toàn bộ đường đọc tới tài nguyên |
| Chỉ kiểm tra một cột của bản ghi | Có thể vẫn ghi bảng liên quan, gửi email/event | Liệt kê và đo mọi tác dụng phụ nghiệp vụ quan trọng |

Để đánh giá test có bắt được lỗi thật không, có thể cố tình tạo một thay đổi **chỉ trong nhánh kiểm thử cục bộ**: bỏ điều kiện ownership hoặc thực hiện ghi trước khi trả `403`. Test phù hợp phải chuyển sang đỏ vì dữ liệu bị lộ hoặc trạng thái bị thay đổi. Sau đó khôi phục code đúng. Đây là phép thử hữu ích để xác nhận assertion đang đo hành vi bảo mật, thay vì chỉ đo status hoặc mock.

## 12. Quy trình áp dụng vào một endpoint thực tế

Giả sử cần kiểm tra `DELETE /api/projects/{projectId}/members/{userId}`. Hãy làm lần lượt:

1. **Xác định chủ thể và quyền:** Ai được xóa thành viên? Quyền theo role, scope, tenant hay quan hệ trong project? Chủ thể bị xóa và người thực hiện có thể là hai người khác nhau.
2. **Thiết lập fixture có đối chứng:** Tạo project A và B; một user được phép thao tác ở A nhưng không được ở B. Lưu ID cụ thể, giá trị trước request và quyền của từng chủ thể.
3. **Gửi request bị cấm nhưng hợp lệ ở lớp khác:** Đăng nhập đúng, cung cấp CSRF nếu cần, gửi body/ID đúng định dạng để tránh trả `400` hoặc `403` vì một cơ chế không liên quan.
4. **Assert lớp HTTP và phản hồi:** Kỳ vọng `403`/`404` theo contract; kiểm tra body, header và URL không để lộ dữ liệu nhạy cảm.
5. **Assert bất biến nghiệp vụ:** Membership của B vẫn tồn tại; không đổi số thành viên, quyền người dùng, event, job hoặc email nghiệp vụ.
6. **Chạy đối chứng dương:** Một admin của B có thể xóa thành viên B; chỉ thay đổi đúng bản ghi và sự kiện dự kiến.
7. **Thử biến thể quyền:** Người cùng tenant nhưng không có role, người có role từ tenant khác, user bị khóa, request batch, target ID sai và tài nguyên không tồn tại.

Trong bộ kiểm thử CI, nên đặt tên test mô tả **hậu điều kiện**: `cannotReadForeignTenantDocument`, `deniedTransferDoesNotChangeBalance`, `forbiddenDeleteDoesNotPublishEvent`, thay vì chỉ `returns403`. Những tên này giúp người sửa code hiểu được hợp đồng bảo mật mà test đang bảo vệ.

Kết quả đáng tin cậy nhất là khi cùng một test chứng minh: yêu cầu trái phép bị từ chối, **không xuất hiện dữ liệu được bảo vệ trong kết quả**, **không có thay đổi nghiệp vụ ngoài ý muốn**, và một yêu cầu tương đương với quyền hợp lệ vẫn thành công. Khi đó kiểm thử đã bảo vệ hành vi truy cập tài nguyên thực tế, vượt ra ngoài một assertion về HTTP status.
