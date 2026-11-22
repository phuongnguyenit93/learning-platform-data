# Giá trị thay thế, che trường và giới hạn an toàn khi quyền bị từ chối

Một hệ thống dùng **Spring Security Authorization** không chỉ cần biết lúc nào trả về `403 Forbidden`. Khi người gọi có quyền xem **một phần** dữ liệu nhưng không được xem các trường nhạy cảm, hệ thống còn phải xác định có nên **bỏ trường**, **che một phần**, hay trả **giá trị thay thế an toàn**. Tất cả lựa chọn này phải dựa trên chính sách quyền ở phía server; một chuỗi `"***"` trên giao diện không tự tạo ra bảo mật.

Bài học thuộc nhóm **Xử lý từ chối** trong module **Spring Security - authorization**. Trọng tâm là quyết định sau kiểm tra quyền, giới hạn dữ liệu được trả về và cách tránh rò rỉ khi cố tạo trải nghiệm thân thiện.

## 1. Phân biệt từ chối toàn bộ tài nguyên và giới hạn từng trường

Trước khi nghĩ đến masking hoặc fallback, hãy trả lời hai câu hỏi độc lập:

1. **Người gọi có quyền đọc đối tượng này không?** Ví dụ Alice được đọc hồ sơ của Alice; Bob không được đọc hồ sơ riêng của Alice.
2. **Nếu được đọc đối tượng, người gọi được đọc những thuộc tính nào?** Ví dụ nhân viên hỗ trợ có quyền xem tên và bốn số cuối điện thoại, nhưng không được đọc email nguyên bản hoặc ghi chú quản trị.

Nếu câu (1) bị từ chối, đừng tự trả HTTP 200 kèm dữ liệu giả như thể người gọi đã được truy cập. Hãy áp dụng chính sách từ chối, thường là `403`; hoặc `404` khi sản phẩm có chủ đích không tiết lộ sự tồn tại của đối tượng. Nếu câu (1) cho phép nhưng một trường bị hạn chế, trả về một **biểu diễn dữ liệu đã được giảm quyền (authorized projection)**: chỉ bao gồm thuộc tính được phép và những giá trị che/thay thế phù hợp với hợp đồng API.

~~~text
Request -> Xác thực danh tính -> Kiểm tra quyền trên tài nguyên
                                |
                        +-------+--------+
                        |                |
                    TỪ CHỐI          CHO PHÉP
                        |                |
                   403 hoặc 404     Kiểm tra quyền từng trường
                                         |
                                 DTO chỉ chứa dữ liệu an toàn
                                         |
                              Serialize JSON -> HTTP 200
~~~

Spring Security quản lý xác thực và các quy tắc request/method authorization. Cách che từng thuộc tính là một **quyết định chính sách nghiệp vụ** mà ứng dụng cần thực hiện tại service/DTO/serialization boundary. Cấu hình `authorizeHttpRequests` chỉ bảo vệ việc gọi endpoint; nó **không tự động bảo đảm** mọi thuộc tính trong entity được phép xuất hiện trong JSON.

Đây là hai lớp kiểm soát khác nhau, tương ứng với các rủi ro **Broken Object Level Authorization** và **Broken Object Property Level Authorization** (OWASP API1/API3).

## 2. Ý nghĩa của giá trị thay thế, che trường và ẩn trường

| Cách xử lý | Biểu diễn thường gặp | Khi nào dùng | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Từ chối toàn bộ** | HTTP `403` hoặc `404` | Không được truy cập đối tượng/hành động | Không đưa dữ liệu thật vào body, header hoặc thông báo lỗi |
| **Bỏ trường** | Không có key `internalNote` | Người gọi không có quyền biết trường này | Đảm bảo nested object, export và endpoint khác cũng không lộ |
| **Giá trị thay thế do thiếu dữ liệu** | `"Chưa cung cấp"` | Trường được phép xem nhưng nguồn thực sự trống | Không dùng thay thế này để che giấu việc từ chối quyền |
| **Giá trị thay thế do giới hạn quyền** | `"Không hiển thị"` | Được xem đối tượng nhưng không được xem giá trị trường | Chuỗi thay thế phải do server tạo, không chứa dữ liệu gốc |
| **Che một phần (mask)** | `"***4567"` | Chính sách **cho phép** xem đúng bốn chữ số cuối | Số cuối, định dạng, độ dài, miền email vẫn là dữ liệu bị tiết lộ |
| **Không có quyền đọc bí mật** | Không trả field/token | Password, refresh token, API secret, khóa riêng | Không dùng phương pháp "che vài ký tự" như lời hứa bảo mật |

Đặc biệt, các giá trị `null`, `""`, `"N/A"` và *không có thuộc tính* mang ý nghĩa khác nhau đối với client. Cần viết rõ trong hợp đồng API. Ví dụ `email: null` có thể bị hiểu là chưa có email, trong khi thực tế email tồn tại nhưng người gọi không được phép biết. Nếu phản hồi không được lộ cả **sự tồn tại** của email, một placeholder cố định hoặc một schema không có trường email là cách phù hợp hơn.

**Không bịa dữ liệu mặc định gây sai lệch nghiệp vụ.** Dùng `0` làm số dư khi người dùng không được xem số dư có thể khiến hệ thống hiển thị sai tình trạng tài chính; dùng `false` khi chưa được phép biết trạng thái kiểm duyệt có thể tạo kết luận không đúng. Nếu quyền bị từ chối cho một hành động, trả trạng thái từ chối theo hợp đồng, không trả `success: true` với dữ liệu giả.

### Nguyên tắc che một phần

Một phép mask chỉ an toàn khi những phần **được giữ lại đã được phê duyệt là có thể tiết lộ**. Những ví dụ như giữ bốn số cuối điện thoại, một phần email hoặc một phần mã định danh không mặc nhiên an toàn cho mọi tổ chức.

- Kiểm tra định dạng đầu vào trước khi áp dụng mask; dữ liệu quá ngắn hoặc không hợp lệ nên dùng placeholder cố định, tránh để lộ nguyên văn.
- Không lưu kết quả masking rồi coi đó là một hình thức mã hóa. Mask là cách giảm thông tin khi hiển thị; không phải encryption, hashing hay tokenization.
- Đừng lấy độ dài chuỗi thật làm độ dài dấu sao nếu chính sách không cho phép suy ra độ dài.
- Không dùng mask để biến mật khẩu, access token, refresh token, secret key hoặc recovery code thành giá trị an toàn để phát hành lại.
- Không đặt dữ liệu gốc trong thuộc tính HTML ẩn, state hydration, JSON debug, log, tooltip, URL hoặc HTTP header rồi chỉ che bằng CSS.

## 3. Chọn mã HTTP trước khi chọn biểu diễn

| Tình huống | Phản hồi điển hình | Cách hiểu |
| --- | --- | --- |
| Chưa xác thực mà gọi tài nguyên cần đăng nhập | `401 Unauthorized` với challenge theo cơ chế xác thực | Cần cung cấp thông tin xác thực hợp lệ |
| Đã xác thực nhưng không được đọc tài nguyên | `403 Forbidden` | Server từ chối tài nguyên/hành động |
| Không có đối tượng, hoặc chính sách có chủ đích che tồn tại đối tượng | `404 Not Found` | Client không được biết một tài nguyên truy cập được tồn tại |
| Được đọc tài nguyên nhưng chỉ một số trường | `200 OK` với DTO giới hạn trường | Dữ liệu trả về phải tuân thủ quyền trên **từng trường** |
| Được đọc trường nhưng giá trị thực tế chưa có | `200 OK` với placeholder đã định nghĩa | Đây là fallback dữ liệu, không phải ngoại lệ bảo mật |

`ExceptionTranslationFilter` cùng `AuthenticationEntryPoint`/`AccessDeniedHandler` xử lý các ngoại lệ bảo mật theo cấu hình của servlet filter chain. Nó không tự che email hay tự chuyển một entity thành DTO. Nếu service/controller ném `AccessDeniedException` và ngoại lệ được truyền ra qua security filter chain, Spring Security có thể chuyển thành phản hồi từ chối. Một authentication filter cũng có thể xử lý lỗi xác thực của chính nó trước khi ngoại lệ tới `ExceptionTranslationFilter`.

Chọn `404` để không lộ sự tồn tại của đối tượng chỉ có tác dụng nếu **chính sách áp dụng nhất quán**. Phản hồi khác nhau giữa ID có thật và ID không có thật vẫn có thể tạo lỗ hổng dò tài nguyên qua mã trạng thái, thông báo, kích thước body hoặc thời gian xử lý. Không dùng `404` như cách né kiểm tra quyền.

## 4. Thiết kế chính sách dựa trên danh tính và dữ liệu

Giả sử API trả hồ sơ cá nhân. Các chủ thể:

- **Owner**: xem hồ sơ của chính mình, gồm email và điện thoại.
- **SUPPORT**: được xem hồ sơ để hỗ trợ, nhưng email được thay bằng `"Không hiển thị"`, điện thoại chỉ có bốn số cuối.
- **ADMIN**: được xem cả thông tin liên hệ và ghi chú nội bộ.
- **Một USER khác**: không được xem hồ sơ của owner.

Ma trận quyền cho một hồ sơ bất kỳ:

| Trường | Owner | SUPPORT | ADMIN | USER khác |
| --- | --- | --- | --- | --- |
| `id`, `displayName` | Giá trị thật/giá trị mặc định nếu thiếu | Tương tự | Tương tự | Không trả hồ sơ |
| `email` | Email thật hoặc `"Chưa cung cấp"` | `"Không hiển thị"` | Email thật hoặc `"Chưa cung cấp"` | Không trả hồ sơ |
| `phone` | Số thật hoặc `"Chưa cung cấp"` | `"***4567"` nếu cho phép tiết lộ bốn số cuối, nếu không thì `"Không hiển thị"` | Số thật hoặc `"Chưa cung cấp"` | Không trả hồ sơ |
| `internalNote` | Bỏ trường | Bỏ trường | Ghi chú thật | Không trả hồ sơ |

Quyền này chỉ là **một chính sách ví dụ**. Đặc biệt, việc SUPPORT được xem tất cả hồ sơ, bốn số cuối điện thoại hoặc ADMIN được xem ghi chú cần được nghiệp vụ phê duyệt trong sản phẩm thật. Không mặc định role `SUPPORT` hoặc `ADMIN` có mọi quyền chỉ vì tên role.

Quy trình xử lý an toàn:

1. Lấy principal/authorities từ `Authentication` đã được Spring Security xác thực; không tin `role`, `ownerId`, `isAdmin` do client tự gửi.
2. Lấy bản ghi cần truy cập và kiểm tra quyền trên **bản ghi cụ thể**. Việc endpoint yêu cầu `authenticated()` chưa đủ để cho phép đọc bất kỳ ID nào.
3. Nếu không được xem bản ghi, dừng xử lý và trả 403/404 theo chính sách; không thực hiện mask để biến truy cập trái phép thành hợp lệ.
4. Nếu được xem, xác định quyền của **từng thuộc tính**. Tạo một response DTO từ danh sách trường được phép, thay thế hoặc bỏ trường theo hợp đồng.
5. Chỉ sau đó mới serialize và gửi qua network. Kiểm tra lại error path, cache, logging và tất cả endpoint liên quan.

## 5. Ví dụ Spring Boot Servlet 3.x + Spring Security 6.x + Java 17+

Trong một dự án Spring Boot đã cấu hình plugin, sử dụng hai starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Lưu chương trình đầy đủ tại `src/main/java/com/example/safeview/SafeViewApplication.java`. Mục tiêu: phân biệt **chặn truy cập tài nguyên** với **cấp phép xem hồ sơ ở dạng đã che trường**.

~~~java
package com.example.safeview;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@SpringBootApplication
@RestController
public class SafeViewApplication {

    private static final Map<String, Profile> PROFILES = Map.of(
            "p1", new Profile(
                    "p1", "alice", "An", "an@example.test",
                    "0901234567", "Ghi chú chỉ dành cho quản trị viên"),
            "p2", new Profile(
                    "p2", "bob", "", null,
                    null, "Thông tin kiểm soát nội bộ")
    );

    public static void main(String[] args) {
        SpringApplication.run(SafeViewApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/profiles/*")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .exceptionHandling(ex -> ex.accessDeniedHandler(
                        (request, response, error) ->
                                response.setStatus(
                                        HttpServletResponse.SC_FORBIDDEN)))
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice").password("{noop}pw")
                        .roles("USER").build(),
                User.withUsername("bob").password("{noop}pw")
                        .roles("USER").build(),
                User.withUsername("support").password("{noop}pw")
                        .roles("SUPPORT").build(),
                User.withUsername("admin").password("{noop}pw")
                        .roles("ADMIN").build()
        );
    }

    @GetMapping("/api/profiles/{id}")
    public ProfileView readProfile(@PathVariable String id,
                                   Authentication authentication,
                                   HttpServletResponse response) {
        Profile profile = PROFILES.get(id);
        if (profile == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        boolean owner = authentication.getName().equals(profile.owner());
        boolean support = hasAuthority(authentication, "ROLE_SUPPORT");
        boolean admin = hasAuthority(authentication, "ROLE_ADMIN");

        if (!owner && !support && !admin) {
            throw new AccessDeniedException("Profile access denied");
        }

        boolean fullContact = owner || admin;
        String safeName = fallback(profile.displayName(), "Chưa cập nhật");
        String safeEmail = fullContact
                ? fallback(profile.email(), "Chưa cung cấp")
                : "Không hiển thị";
        String safePhone = fullContact
                ? fallback(profile.phone(), "Chưa cung cấp")
                : maskLastFour(profile.phone());
        String safeInternalNote = admin ? profile.internalNote() : null;

        response.setHeader(HttpHeaders.CACHE_CONTROL, "private, no-store");
        return new ProfileView(
                profile.id(), safeName, safeEmail,
                safePhone, safeInternalNote);
    }

    private static boolean hasAuthority(
            Authentication authentication, String authority) {
        return authentication.getAuthorities().stream()
                .anyMatch(granted -> authority.equals(granted.getAuthority()));
    }

    private static String fallback(String raw, String substitute) {
        return raw == null || raw.isBlank() ? substitute : raw;
    }

    private static String maskLastFour(String raw) {
        if (raw == null) {
            return "Không hiển thị";
        }
        String digits = raw.replaceAll("[^0-9]", "");
        if (digits.length() < 4) {
            return "Không hiển thị";
        }
        return "***" + digits.substring(digits.length() - 4);
    }

    private record Profile(
            String id,
            String owner,
            String displayName,
            String email,
            String phone,
            String internalNote) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ProfileView(
            String id,
            String displayName,
            String email,
            String phone,
            String internalNote) {
    }
}
~~~

### Vì sao ví dụ này an toàn trong phạm vi minh họa?

- `authorizeHttpRequests` yêu cầu đăng nhập trước khi vào API. Với route không được cho phép, `denyAll()` là giá trị mặc định an toàn. `DispatcherType.ERROR` được cho qua để HTTP error dispatch của Servlet không bị một lần từ chối thứ hai che lấp.
- Kiểm tra **owner/support/admin được thực hiện trên bản ghi p1/p2**, không chỉ trên đường dẫn. Một USER đã đăng nhập không tự có quyền xem hồ sơ khác.
- Trong nhánh bị từ chối, phương thức ném `AccessDeniedException` trước khi tạo DTO; `AccessDeniedHandler` cấu hình trả `403`. Trong hệ thống thật, chính sách tài nguyên có thể nằm ở service/repository hoặc method authorization để mọi đường gọi đều tuân theo.
- `Profile` là dữ liệu nội bộ, **không bao giờ được trả thẳng** từ controller. `ProfileView` là một DTO có chủ đích; với owner/support, `internalNote` là `null` và `@JsonInclude(NON_NULL)` khiến key bị bỏ khỏi JSON.
- `maskLastFour` cố tình chỉ tiết lộ bốn số cuối cho SUPPORT; nếu dữ liệu ngắn/không có thì trả placeholder cố định. Đừng tái dùng hàm này cho dữ liệu mà bốn số cuối cũng bị cấm lộ.
- Các field bị giới hạn được xử lý **trước** khi Jackson serialize. Đổi chữ trên frontend sau khi nhận dữ liệu gốc sẽ không đạt mục tiêu bảo vệ.
- Response có `Cache-Control: private, no-store` để hạn chế lưu bản trả lời nhạy cảm. Cấu hình cache/CDN thực tế vẫn phải được kiểm tra.
- Mật khẩu `{noop}pw` và dữ liệu bộ nhớ chỉ phục vụ việc chạy thử local. Trong production phải dùng password hashing phù hợp, HTTPS, định danh từ hệ thống xác thực thực và chính sách phân quyền được quản trị riêng.

**Lưu ý về 404:** ví dụ trả `404` cho ID không tồn tại nhưng `403` khi Bob biết một ID có thật mà không có quyền. Đó là chính sách **có thể tiết lộ sự tồn tại** của hồ sơ. Nếu sản phẩm không cho phép tiết lộ điều này, cần thiết kế và kiểm thử một chính sách trả `404` nhất quán cho cả hai trường hợp, kết hợp giảm các kênh suy đoán khác. Ví dụ giữ `403` để minh họa rõ nhánh từ chối quyền.

### Chạy và quan sát kết quả

Trong thư mục dự án chứa Gradle wrapper và Spring Boot plugin:

~~~bash
./gradlew bootRun
# Trên Windows: gradlew.bat bootRun
~~~

Gọi lần lượt:

~~~bash
curl -i http://localhost:8080/api/profiles/p1
curl -i -u alice:pw http://localhost:8080/api/profiles/p1
curl -i -u support:pw http://localhost:8080/api/profiles/p1
curl -i -u admin:pw http://localhost:8080/api/profiles/p1
curl -i -u bob:pw http://localhost:8080/api/profiles/p1
curl -i -u bob:pw http://localhost:8080/api/profiles/p2
curl -i -u admin:pw http://localhost:8080/api/profiles/not-found
curl -i -u alice:wrong http://localhost:8080/api/profiles/p1
~~~

| Request | HTTP mong đợi | Quyết định quan trọng |
| --- | --- | --- |
| Anonymous -> `p1` | 401 | Bị yêu cầu xác thực; HTTP Basic có challenge |
| Alice -> `p1` | 200 | Owner: email/phone thật, không có `internalNote` |
| SUPPORT -> `p1` | 200 | Email placeholder, điện thoại chỉ còn bốn số cuối |
| ADMIN -> `p1` | 200 | Có email, điện thoại và `internalNote` |
| Bob -> `p1` | 403 | Không được xem cả tài nguyên; tuyệt đối không trả 200 với mask |
| Bob -> `p2` | 200 | Owner: field rỗng được thay bằng giá trị mặc định hợp lệ |
| ADMIN -> ID không có | 404 | Không tìm thấy tài nguyên |
| Alice với mật khẩu sai -> `p1` | 401 | Xác thực HTTP Basic thất bại |

Một phản hồi minh họa cho SUPPORT đọc `p1`:

~~~json
{
  "id": "p1",
  "displayName": "An",
  "email": "Không hiển thị",
  "phone": "***4567"
}
~~~

Một phản hồi minh họa cho Bob đọc hồ sơ `p2` của mình:

~~~json
{
  "id": "p2",
  "displayName": "Chưa cập nhật",
  "email": "Chưa cung cấp",
  "phone": "Chưa cung cấp"
}
~~~

Một phản hồi minh họa cho ADMIN đọc `p1`:

~~~json
{
  "id": "p1",
  "displayName": "An",
  "email": "an@example.test",
  "phone": "0901234567",
  "internalNote": "Ghi chú chỉ dành cho quản trị viên"
}
~~~

Thứ tự các key JSON và các header HTTP bổ sung có thể khác tùy phiên bản/framework. Các mã trạng thái và giá trị trường trong bảng là điều cần xác minh. Đặc biệt, mọi phản hồi cho SUPPORT và owner **không được chứa** chuỗi nội bộ `"Ghi chú chỉ dành cho quản trị viên"`, kể cả trong body lỗi hoặc metadata.

## 6. Khi nào dùng Spring Security method authorization?

`@EnableMethodSecurity` cho phép `@PreAuthorize` và `@PostAuthorize` kiểm soát lời gọi các method do Spring quản lý. Nó hữu ích khi cùng một service được dùng từ nhiều controller, tác vụ nền hoặc adapter khác. Ví dụ **minh họa ngắn, không phải chương trình độc lập**:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public ProfileAudit readAuditForAdmin(String profileId) {
    return repository.readAudit(profileId);
}
~~~

Nếu không bật `@EnableMethodSecurity`, annotation trên không tự được áp dụng chỉ nhờ `spring-boot-starter-security`. Bản thân `@PreAuthorize` cũng không tự tạo dữ liệu đã mask ở cấp trường. Với dữ liệu hỗn hợp public/private, vẫn cần kiểm tra quyền đối tượng và xây dựng DTO theo từng trường.

Ưu tiên **kiểm tra quyền trước khi thực hiện side effect**. `@PostAuthorize` có thể phù hợp cho một số phép đọc, nhưng không nên dựa vào kiểm tra sau khi method đã ghi dữ liệu để bảo vệ một hành động nguy hiểm. Khi danh sách lớn, lọc quyền ngay tại truy vấn/repository để số lượng, thứ tự và phân trang phản ánh các bản ghi được phép xem.

Nếu dùng nhiều `SecurityFilterChain`, cần kiểm tra request thực sự khớp chain nào: entry point, denied handler và các quy tắc endpoint có thể khác nhau. Các controller không phải ranh giới bảo vệ duy nhất nếu object/service còn được xuất qua GraphQL, WebSocket, message consumer hoặc job khác.

## 7. Giới hạn an toàn cần bảo vệ ngoài body JSON

**A. Không lộ dữ liệu gốc qua đường khác.** Một trường đã che ở endpoint chi tiết vẫn có thể rò qua: danh sách, search result, export CSV/Excel, API v2, GraphQL selection, file đính kèm, event payload, thông báo email, autocomplete, nested object, debug endpoint, hoặc serialization tự động của entity. Mỗi đường ra phải dùng chính sách và projection phù hợp.

**B. Không lộ cấu trúc nhạy cảm.** Những giá trị như `hasPrivateNote: true`, độ dài dữ liệu, số lượng phần tử, sự khác biệt giữa `null` và không có key, nội dung `ETag`, lỗi validate, thời gian phản hồi hoặc thứ tự sắp xếp có thể tiết lộ sự tồn tại/thuộc tính dù không trả giá trị trực tiếp. Mức độ chấp nhận phụ thuộc threat model và chính sách.

**C. Không lộ qua log và tracing.** Thông báo lỗi 403 có thể ghi request ID/correlation ID nhưng không chép email gốc, token, hồ sơ đầy đủ hoặc stack trace cho client. Cấu hình body logging, APM, reverse proxy và audit log với cùng mức bảo vệ. Hạn chế nội dung nhạy cảm trong `toString()` của entity.

**D. Không lộ qua cache.** Response theo danh tính không được đưa vào shared CDN cache nếu cache key không phân biệt đầy đủ quyền. Dùng `Cache-Control: private, no-store` khi nội dung nhạy cảm; kiểm tra cả browser, proxy, CDN và ứng dụng mobile. Một ETag hoặc một cache key gắn với dữ liệu gốc cũng có thể làm lộ thông tin ngoài ý muốn.

**E. Không lộ qua phân trang và thống kê.** Với `GET /profiles?owner=...`, không nên lấy toàn bộ danh sách rồi che field của các hàng bị từ chối hoặc trả tổng số hàng trước khi lọc quyền. Hãy thực hiện row-level filtering trong truy vấn trước `COUNT`, `OFFSET/LIMIT` và aggregation, tùy yêu cầu nghiệp vụ.

**F. Không biến đầu vào client thành policy.** Không để client chọn `fields=internalNote`, `includePrivate=true`, `role=ADMIN` hoặc tự đặt `ownerId` nhằm lấy dữ liệu nhạy cảm. Nếu API hỗ trợ chọn field, **giao** tập field được yêu cầu với tập field được phép bởi server, rồi mới truy vấn/serialize. Cũng cần chống mass assignment khi ghi: DTO input chỉ cho phép chỉnh những thuộc tính mà principal có quyền.

**G. Không để lỗi hệ thống mở quyền.** Timeout từ policy service, thiếu authority hoặc lỗi đọc cấu hình phải đi theo hành vi fail-closed thích hợp; không trả full entity để “giữ trải nghiệm”. Cần phân biệt lỗi hạ tầng thật (`5xx`) với trường hợp chính sách từ chối (`403`/`404`), tránh dùng 403 che mọi lỗi server.

## 8. Kiểm thử theo ma trận quyền và trường

Các bài test nên kiểm tra **sự vắng mặt của dữ liệu bị cấm**, không chỉ xem response có status 200/403:

| Trường hợp | Điều phải khẳng định |
| --- | --- |
| Chưa đăng nhập | 401/challenge phù hợp, không có PII |
| USER đúng owner | Full contact được phép, `internalNote` bị bỏ |
| USER khác owner | 403/404 theo policy, không có DTO/PII |
| SUPPORT | Email là placeholder, phone chỉ last-4, `internalNote` không tồn tại |
| ADMIN | Đúng trường được cấp phép, không có thuộc tính ngoài hợp đồng |
| Field nguồn null/trống | Placeholder đúng cho chủ thể có quyền, không phát sinh `null` sai nghĩa |
| Phone thiếu bốn chữ số | Không trả raw phone do lỗi mask |
| ID không tồn tại | 404 theo policy, không tạo dấu hiệu dò ID |
| Role/claims thiếu hoặc không hợp lệ | Không mở quyền như ADMIN/SUPPORT |
| Endpoint danh sách/export/search | Áp dụng cùng chính sách object và field |
| Cache giữa hai principal | Không dùng response đầy đủ của ADMIN phục vụ SUPPORT |
| Error/logging path | Không chứa dữ liệu thật, stack trace hoặc bí mật |

Ví dụ dạng kiểm thử Spring MVC (chỉ mang tính minh họa, không độc lập) có thể kiểm tra giá trị và **absence** cùng lúc:

~~~java
mockMvc.perform(get("/api/profiles/p1")
        .with(httpBasic("support", "pw")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.email").value("Không hiển thị"))
    .andExpect(jsonPath("$.phone").value("***4567"))
    .andExpect(jsonPath("$.internalNote").doesNotExist());
~~~

Snippet này giả định test đã có `MockMvc`, static imports từ `MockMvcRequestBuilders`, `SecurityMockMvcRequestPostProcessors` và `MockMvcResultMatchers`; cần thêm `spring-security-test` và `spring-boot-starter-test` khi xây dựng bộ test thực tế. Với thông tin nhạy cảm, có thể kết hợp assertion không tìm thấy chuỗi bí mật trong toàn bộ response.

## 9. Những sai lầm dễ gặp

1. **Che dữ liệu ở React/HTML sau khi API đã trả giá trị thật.** Bất kỳ ai mở Network tab vẫn nhìn thấy dữ liệu. Chuyển logic che dữ liệu về server và trả DTO an toàn.
2. **Trả `200` cùng chuỗi `"Không có quyền"` cho tài nguyên bị cấm.** Client và cache có thể hiểu đó là truy cập thành công. Giữ rõ ranh giới từ chối toàn bộ với biểu diễn giới hạn trường đã được cấp phép.
3. **Trả thẳng JPA entity hoặc domain object.** Jackson có thể serialize thêm thuộc tính mới hoặc quan hệ lồng nhau. Dùng response DTO với trường được chọn có chủ đích; không tùy thuộc blacklist ngầm.
4. **Coi `@JsonIgnore` hay `@JsonView` là quyết định authorization đầy đủ.** Chúng kiểm soát serialization tĩnh hoặc view được chọn, nhưng ứng dụng vẫn phải xác thực người gọi và áp dụng chính sách trên resource/field.
5. **Dùng placeholder khác nhau khi thiếu dữ liệu và khi bị cấm xem, vô tình lộ tồn tại.** Quyết định rõ có được biết field tồn tại hay không, rồi thống nhất biểu diễn.
6. **Mask điện thoại bằng substring mà không kiểm tra độ dài.** Có thể ném ngoại lệ hoặc trả lộ nguyên số ngắn. Xử lý thiếu/không hợp lệ bằng kết quả an toàn.
7. **Chỉ kiểm tra role, bỏ qua sở hữu đối tượng.** Người dùng thường chỉ được xem các ID của chính họ, dù cả hai đều có `ROLE_USER`.
8. **Chỉ kiểm tra endpoint GET, bỏ qua PATCH/PUT/POST.** Field không được đọc thường cũng cần chính sách riêng về sửa; chống mass assignment và ghi vượt quyền.
9. **Bật cache công khai cho response phụ thuộc principal.** Cache sai có thể trả bản đầy đủ của ADMIN cho người ít quyền hơn.
10. **Dùng log chi tiết, exception message hoặc debug response chứa cả entity.** Việc che JSON ở đường thành công chưa đủ nếu đường lỗi vẫn rò dữ liệu.

## 10. Checklist quyết định trước khi phát hành

- [ ] Đã định nghĩa quyền **trên đối tượng** và **trên từng thuộc tính** cho các actor thật.
- [ ] Những thao tác bị từ chối trả 401/403/404 theo một chính sách nhất quán; không âm thầm giả thành 200.
- [ ] Placeholder thể hiện đúng ý nghĩa: thiếu dữ liệu, bị giới hạn quyền, hoặc dữ liệu cố ý không được biết.
- [ ] Chỉ mask những phần được phép tiết lộ; mật khẩu/token/secret không được phát hành dưới dạng mask.
- [ ] Response DTO là allowlist; domain entity thô, nested objects và field mới không tự lọt ra ngoài.
- [ ] Cùng quyền được áp dụng ở detail/list/search/export/error path; count và pagination không vượt quyền.
- [ ] Đã thử ít nhất owner, người ngoài, support, admin, anonymous, missing field và malformed field.
- [ ] Đã kiểm tra log, cache, tracing, các bản API và sự khác biệt 403/404 có thể làm lộ thông tin.
- [ ] Khi policy không xác định hoặc có lỗi, hệ thống không tự nới quyền.

### Tài liệu tham khảo

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Servlet Architecture / ExceptionTranslationFilter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- OWASP API Security Top 10 2023 — API1/API3: https://api-security.owasp.org/editions/2023/en/0x11-t10/
- OWASP API3:2023 — Broken Object Property Level Authorization: https://github.com/OWASP/API-Security/blob/master/editions/2023/en/0xa3-broken-object-property-level-authorization.md
