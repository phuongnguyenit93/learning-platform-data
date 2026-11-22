# Kiểm thử IDOR bằng cách thay định danh tài nguyên

## 1. Mục tiêu và phạm vi

**IDOR (Insecure Direct Object Reference)** là lỗi kiểm soát truy cập ở mức đối tượng: ứng dụng nhận một định danh tài nguyên từ request rồi truy xuất hoặc thay đổi đối tượng mà không xác minh người gọi có quyền với **chính đối tượng đó**. Trong API hiện đại, lỗi này thường được gọi là **BOLA (Broken Object Level Authorization)**. Điểm cần kiểm thử là quyết định ủy quyền cho từng đối tượng, không chỉ là việc người dùng đã đăng nhập hoặc đã có một vai trò hợp lệ.

Sau bài này, bạn cần biết cách:
- Nhận diện nơi client cung cấp định danh tài nguyên: đường dẫn, query, JSON body, tham số của tài nguyên con và lệnh cập nhật hàng loạt.
- Giữ nguyên danh tính người gọi, thay **chỉ định danh đối tượng** để thử truy cập dữ liệu thuộc tài khoản/nhóm/tenant khác trong môi trường được phép kiểm thử.
- Phân biệt kết quả hợp lệ theo chính sách (200/204, 403, 404) với lỗi bảo mật thực sự; kiểm chứng cả **nội dung dữ liệu lẫn tác động lưu trữ**.
- Viết automated test cho Spring Security, xác nhận chặn truy cập ngang hàng (horizontal), vượt vai trò (vertical) và vượt ranh giới tenant khi ứng dụng có đa thuê bao.

Chỉ dùng tài khoản và dữ liệu kiểm thử do bạn quản lý hoặc được chủ hệ thống cho phép. Không dò ID, lấy nội dung hay sửa dữ liệu của người dùng thật.

## 2. Mô hình lỗi: xác thực khác với ủy quyền đối tượng

Giả sử API quản lý tài liệu:

- Alice có tài liệu **101** thuộc tenant T1.
- Bob có tài liệu **202** thuộc tenant T1.
- Carol có tài liệu **303** thuộc tenant T2.
- Alice đang đăng nhập, gửi **GET /api/documents/101** và nhận tài liệu của mình.
- Alice đổi URL thành **GET /api/documents/202**; nếu nhận tài liệu của Bob dù không được chia sẻ quyền thì đã xảy ra IDOR/BOLA.

Việc bảo vệ tuyến **/api/documents/** bằng **authenticated()** chỉ bảo đảm request có danh tính hợp lệ. Kiểm tra **hasRole("USER")** cũng chưa đủ: Alice và Bob đều có thể mang vai trò USER, trong khi quyền đọc từng tài liệu khác nhau. Quyết định đúng thường cần đồng thời xét **subject** (người gọi), **action** (read/update/delete), **resource** (đối tượng) và **context** (tenant, trạng thái, quan hệ chia sẻ, thời điểm).

Có ba góc kiểm thử thường gặp:

| Góc kiểm thử | Câu hỏi bảo mật | Ví dụ |
| --- | --- | --- |
| Horizontal authorization | Hai người cùng vai trò có thể xem/sửa đối tượng của nhau không? | Alice dùng ID tài liệu 202 của Bob |
| Vertical authorization | Người ít quyền có thể tác động đối tượng/chức năng dành cho vai trò cao hơn không? | USER thử đổi ID một yêu cầu chỉ ADMIN được phê duyệt |
| Tenant isolation | Người thuộc tenant T1 có thể truy cập đối tượng của T2 không? | Alice dùng ID tài liệu 303 của Carol |

**ID khó đoán không thay thế authorization.** UUID, ULID, token giống ngẫu nhiên hoặc ID được mã hóa chỉ làm việc đoán khó hơn; khi định danh bị lộ qua link, log, response hoặc chia sẻ, quyền truy cập vẫn phải được kiểm tra tại server.

## 3. Thiết kế dữ liệu kiểm thử và ma trận kỳ vọng

Tạo fixture có chủ sở hữu và tenant rõ ràng. Mọi ID trong bảng là dữ liệu giả lập của môi trường kiểm thử:

| Người gọi | ID yêu cầu | Quan hệ | Kỳ vọng theo chính sách chỉ chủ sở hữu được đọc |
| --- | --- | --- | --- |
| Alice (T1) | 101 | Chính chủ | 200 và đúng nội dung tài liệu 101 |
| Alice (T1) | 202 | Cùng tenant, khác chủ | 403 **hoặc** 404; không có dữ liệu Bob |
| Alice (T1) | 303 | Khác tenant | 403 **hoặc** 404; không có dữ liệu Carol |
| Bob (T1) | 202 | Chính chủ | 200 và đúng nội dung tài liệu 202 |
| Chưa đăng nhập | 101 | Không có danh tính | 401 nếu API dùng HTTP authentication; có thể redirect nếu login dạng web |
| Alice (T1) | 999 | Tài nguyên không tồn tại | 404 |
| Admin (được cấp quyền) | 202 | Quyền theo chính sách quản trị | Chỉ thành công nếu chính sách thực sự cho phép |

**403** biểu thị server biết người gọi không được phép; **404** có thể là lựa chọn có chủ đích để không tiết lộ sự tồn tại của đối tượng. Không kết luận IDOR chỉ từ mã trạng thái. Cần kiểm tra response body, mã lỗi, log và trạng thái dữ liệu sau request. Ngược lại, một request trả 403 nhưng đã cập nhật dữ liệu trước khi kiểm tra quyền vẫn là lỗi nghiêm trọng.

Trước khi chạy, xác nhận rõ các trường hợp chia sẻ hợp lệ, quyền admin, quyền tác giả, quy tắc thừa kế, trạng thái tài liệu và ranh giới tenant. Không mặc định rằng “khác chủ” luôn bị cấm nếu nghiệp vụ có chia sẻ tài nguyên.

## 4. Quy trình kiểm thử thay định danh

1. **Chọn điểm vào.** Xác định endpoint đọc một đối tượng, sửa, xóa, tải file, đọc tài nguyên con hoặc thao tác hàng loạt. Ghi nhận nơi chứa ID và nguồn tạo ra ID (response danh sách, đường dẫn do UI sinh, trường JSON).
2. **Tạo baseline hợp lệ.** Đăng nhập Alice; gọi đúng tài liệu 101; lưu method, path, request body, response status, JSON và trạng thái lưu trữ. Điều này xác nhận test setup hoạt động.
3. **Đổi duy nhất định danh tài nguyên.** Giữ nguyên token/cookie, method, payload và role Alice; thay 101 bằng 202. Lặp với 303 nếu có tenant. Tách riêng thí nghiệm thay ID ở path, query và body để biết tham số nào thực sự quyết định đối tượng.
4. **Kiểm tra phản hồi và tác động.** Không được trả nội dung ngoài quyền. Với PATCH/PUT/DELETE, kiểm tra dữ liệu trước/sau bằng tài khoản sở hữu hoặc truy vấn test DB; không chỉ dựa vào HTTP status.
5. **Thử chiều ngược lại.** Đăng nhập Bob, xác nhận Bob đọc được 202 nhưng bị ngăn với 101. Việc này phát hiện rule gắn cứng một ID hoặc một user.
6. **Lặp qua các action và quan hệ.** Với mỗi action (read/update/delete/download/approve) và mỗi vai trò/tenant liên quan, chạy ma trận tối thiểu tương tự. Lưu kết quả “expected vs observed” để có test hồi quy.

Ví dụ HTTP trong môi trường thử nghiệm có Bearer token; hai request dùng **cùng token Alice**, chỉ khác ID:

~~~http
GET /api/documents/101 HTTP/1.1
Host: localhost:8080
Authorization: Bearer <alice-test-token>
Accept: application/json
~~~

~~~http
GET /api/documents/202 HTTP/1.1
Host: localhost:8080
Authorization: Bearer <alice-test-token>
Accept: application/json
~~~

Nếu chính sách chỉ chủ sở hữu được đọc, request thứ hai phải bị từ chối (403 hoặc 404) và tuyệt đối không trả nội dung tài liệu 202. Đây là request minh họa giao thức; ví dụ ứng dụng runnable ở phần sau dùng HTTP Basic và MockMvc thay cho Bearer token.

**Các vị trí ID hay bị bỏ sót:**
- Path: **/api/orders/{orderId}**, **/api/orders/{orderId}/items/{itemId}**. Phải bảo đảm item thực sự thuộc order và người gọi được phép với cả quan hệ đó.
- Query: **GET /api/reports?accountId=202**. Server không được tin accountId do client gửi như bằng chứng quyền sở hữu.
- Body: trường **documentId**, **ownerId**, **tenantId**, **targetUserId** của PATCH/POST; nhất là khi request cho phép đổi quan hệ sở hữu.
- Hàng loạt: **POST /api/documents/bulk-delete** với danh sách ID gồm tài nguyên của nhiều người. Cần kiểm tra quyền **từng ID** và chính sách giao dịch khi một phần không hợp lệ.
- Download/export, preview, ảnh đính kèm, phiên bản lịch sử, search/list và endpoint nội bộ do frontend gọi. Quyền truy cập phải thống nhất giữa cách liệt kê và cách đọc trực tiếp.
- GraphQL resolver, gRPC service hoặc truy cập qua WebSocket nếu có: ranh giới object authorization vẫn như HTTP.

## 5. Minh họa lỗi và cách kiểm soát trong Spring Security

### 5.1. Đoạn dễ lỗi (minh họa, không dùng cho production)

~~~java
@GetMapping("/{id}")
public DocumentView read(@PathVariable long id) {
    return repository.findById(id)
            .map(DocumentView::from)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
}
~~~

Đoạn trên chỉ xác định **đối tượng có tồn tại**, chưa kiểm tra **người gọi có quyền đọc hay không**. Kể cả endpoint đã được cấu hình **authenticated()**, bất kỳ user đã đăng nhập nào cũng có thể thử ID khác nếu không có kiểm tra tại service/repository. Đoạn này là pseudo-snippet: các kiểu repository/DocumentView cần định nghĩa theo ứng dụng thực tế.

### 5.2. Ví dụ Spring Boot tối thiểu có thể chạy test

Ví dụ dùng Java 21, Spring Boot 3.3, Spring Security 6 và hai tài liệu trong bộ nhớ để cô lập lỗi quyền truy cập. Dữ liệu nằm trong bộ nhớ chỉ để học và kiểm thử; ứng dụng thật nên truy vấn DB theo principal/tenant và xử lý giao dịch phù hợp.

Tạo các file sau trong một project Gradle:

**settings.gradle**

~~~groovy
rootProject.name = 'idor-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/idor/IdorDemoApplication.java**

~~~java
package demo.idor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdorDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/idor/SecurityConfig.java**

~~~java
package demo.idor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**src/main/java/demo/idor/DocumentView.java**

~~~java
package demo.idor;

public record DocumentView(long id, String owner, String title) {
}
~~~

**src/main/java/demo/idor/DocumentStore.java**

~~~java
package demo.idor;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
class DocumentStore {
    private final Map<Long, DocumentView> documents = Map.of(
            101L, new DocumentView(101L, "alice", "Tài liệu Alice"),
            202L, new DocumentView(202L, "bob", "Tài liệu Bob")
    );

    Optional<DocumentView> findOwnedBy(long id, String username) {
        return Optional.ofNullable(documents.get(id))
                .filter(document -> document.owner().equals(username));
    }
}
~~~

**src/main/java/demo/idor/DocumentController.java**

~~~java
package demo.idor;

import java.security.Principal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentStore store;

    DocumentController(DocumentStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    DocumentView read(@PathVariable long id, Principal principal) {
        return store.findOwnedBy(id, principal.getName())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Điểm quyết định nằm ở **findOwnedBy(id, principal.getName())**. Principal do Spring Security cung cấp từ phiên đã xác thực; client không thể giành quyền đơn giản bằng cách sửa **ownerId** trong request. Store chỉ trả tài liệu khi **ID khớp và người gọi là owner**. Tài liệu không tồn tại và tài liệu thuộc user khác đều trả 404 theo chính sách che giấu sự tồn tại của ví dụ.

Trong ứng dụng có DB và tenant, thiết kế truy vấn thường cần ràng buộc **id + tenantId + ownerId/quyền chia sẻ** ngay tại data access. Ví dụ signature repository JPA (minh họa, không phải class độc lập biên dịch):

~~~java
Optional<Document> findByIdAndTenantIdAndOwnerId(
        Long documentId, Long tenantId, Long ownerId);
~~~

**tenantId** và **ownerId** để kiểm tra quyền phải được suy ra từ principal/ngữ cảnh đã xác thực hoặc mapping đáng tin của server, không lấy thẳng từ input client. Nếu chính sách có quyền chia sẻ, kiểm tra ACL hoặc policy service tương ứng; nếu có ADMIN bypass, đặc tả rõ admin nào, tenant nào và action nào được phép. Với thao tác ghi, thực thi quyền trong cùng luồng service/giao dịch để tránh tình trạng kiểm tra một đối tượng nhưng cập nhật đối tượng khác hoặc kiểm tra rồi dữ liệu đổi trước khi ghi.

Spring Security hỗ trợ **@EnableMethodSecurity** với **@PreAuthorize** cho policy ở tầng service. Ví dụ biểu thức **@PreAuthorize("@documentPolicy.canRead(#p0, authentication)")** có thể kiểm tra quyền cho tham số ID đầu tiên, nhưng bean **documentPolicy** phải được định nghĩa và thực hiện kiểm tra chủ sở hữu/tenant trên dữ liệu đáng tin. Annotation không tự biết owner của một đối tượng. Nếu dùng check ở controller, vẫn bảo đảm mọi đường vào service khác đều áp dụng cùng policy.

### 5.3. Kiểm thử tự động bằng MockMvc

**src/test/java/demo/idor/DocumentAuthorizationTest.java**

~~~java
package demo.idor;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "alice")
    void changingOnlyIdCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "bob")
    void bobCanReadHisOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    @WithMockUser(username = "bob")
    void accessDeniedInReverseDirectionToo() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice")
    void missingDocumentIsNotFound() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void anonymousUserMustAuthenticate() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy từ thư mục project với JDK 21 và Gradle 8.5 (hoặc Gradle wrapper tương thích):

~~~bash
gradle test
~~~

Kỳ vọng: **6 phép thử đều PASS** trên ví dụ đã nêu; không cần database, tài khoản production hoặc token thật. Nếu thay logic **findOwnedBy(...)** bằng tìm theo ID thuần túy, hai test đổi ID sẽ phát hiện lộ dữ liệu vì nhận 200 thay vì 404. **@WithMockUser** chỉ giả lập principal cho test security; test tích hợp thực tế còn cần kiểm tra token/session, tenant resolver và repository/DB mà hệ thống sử dụng.

## 6. Với thao tác sửa/xóa, phải xác minh hậu quả

GET giúp phát hiện rò rỉ dữ liệu; IDOR của **PATCH/PUT/DELETE/POST action** có thể nguy hiểm hơn vì làm biến đổi tài nguyên. Ví dụ ma trận bổ sung cho Alice:

| Thao tác | Định danh | Kết quả cần xác nhận |
| --- | --- | --- |
| PATCH /api/documents/101 | Tài liệu Alice | Thành công nếu Alice có quyền sửa; thay đổi được lưu |
| PATCH /api/documents/202 | Tài liệu Bob | Bị từ chối; **nội dung Bob giữ nguyên** |
| DELETE /api/documents/202 | Tài liệu Bob | Bị từ chối; **tài liệu vẫn tồn tại** |
| POST /api/documents/202/approve | Tài liệu Bob | Chỉ thành công nếu policy cho vai trò/action ấy |
| GET /api/documents/202/download | Tài liệu Bob | Không trả file, URL tải đã ký hoặc metadata nhạy cảm |

Với các request thay đổi trạng thái trong ứng dụng dùng session/cookie, cung cấp CSRF token hợp lệ khi cần; **403 do thiếu CSRF token** không chứng minh object authorization đã hoạt động. Đối với API Bearer stateless, cấu hình CSRF phải dựa vào mô hình xác thực thực tế, không tắt bừa chỉ để test xanh. Kiểm tra cả response, trạng thái sau request, event/audit và các đối tượng liên quan.

Nếu API trả danh sách chỉ gồm tài liệu được phép nhưng endpoint **GET /{id}** lại trả bất kỳ ID nào, việc lọc danh sách không bảo vệ truy cập trực tiếp. Ngược lại, nếu endpoint chi tiết bảo vệ đúng nhưng search/export/bulk action bỏ qua policy, vẫn có lỗ hổng.

## 7. Các bẫy thường gặp khi phân tích kết quả

- **401 vs 403/404:** 401 là chưa xác thực; 403/404 cho request đã xác thực thường liên quan authorization hoặc sự tồn tại. Không dùng một request thiếu token để kết luận rằng đổi ID đã bị chặn.
- **Nhầm ownership với role:** Có vai trò USER không có nghĩa được phép đọc mọi document của USER khác. Ngược lại, quyền được chia sẻ hợp lệ có thể cho người không phải owner truy cập.
- **Chỉ kiểm tra status:** API có thể trả 200 kèm dữ liệu nhạy cảm trong JSON, error detail hoặc cache; API ghi có thể đã có side effect rồi mới trả lỗi. Luôn đối chiếu dữ liệu thật.
- **Tin tenantId/ownerId do client gửi:** Nếu service lấy tenantId từ JSON/query, kẻ tấn công có thể sửa cả ID lẫn tenantId. Tenant context phải xuất phát từ identity đáng tin và được đối chiếu với resource.
- **Chỉ dùng UUID:** Độ khó đoán không tạo ra quyền. Tài liệu bị lộ link vẫn cần kiểm tra chủ sở hữu/quyền chia sẻ.
- **Chỉ bảo vệ controller:** Một luồng khác như batch job, GraphQL resolver hoặc phương thức service có thể gọi repository mà bỏ qua check; đưa policy tới tầng service/data access phù hợp.
- **Cache và file storage:** Cache key cần phân biệt đối tượng và quyền/tenant khi phù hợp; URL download, object storage và response cache không được vô tình chia sẻ dữ liệu giữa người dùng.
- **Check rồi mới update theo ID khác:** Với mutation, tránh kiểm quyền ở một bản ghi rồi cập nhật bằng ID do client gửi không ràng buộc; xét tính nhất quán của giao dịch và race condition.
- **Chỉ test ID liền nhau:** Sử dụng các ID fixture có chủ/tenant/role khác nhau thay vì chỉ 101, 102; mục tiêu là kiểm chính sách, không phải đoán ID.

## 8. Ghi nhận lỗi và tiêu chí hoàn thành

Một báo cáo tái hiện IDOR nên chứa: endpoint/method, actor/role/tenant kiểm thử, ID đối tượng hợp lệ, ID đối tượng khác quyền, policy kỳ vọng, hai request đã ẩn token, status/body quan sát được, chứng cứ side effect (nếu có), tác động bảo mật và test hồi quy. Không đưa token truy cập, thông tin nhạy cảm hoặc dữ liệu cá nhân thật vào báo cáo.

**Tiêu chí PASS của kiểm thử:** các thao tác hợp lệ vẫn hoạt động; đổi sang ID ngoài quyền bị từ chối nhất quán ở mọi đường vào; không lộ dữ liệu qua body/file/cache; không có side effect trái phép; ranh giới tenant được giữ; các hành vi được bảo vệ bằng automated test và được chạy lại sau thay đổi policy.

**Ghi nhớ:** Spring Security xác thực người gọi và cung cấp cơ chế authorization; chính ứng dụng phải định nghĩa và thực thi quyền theo **resource cụ thể**. Thay định danh trong cùng phiên là cách trực tiếp để chứng minh policy có được áp dụng cho từng đối tượng hay chưa.
