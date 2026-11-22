# Xử lý an toàn khi cấu hình thiếu, dịch vụ ngoài lỗi hoặc dữ liệu không hợp lệ

Một ứng dụng an toàn phải trả lời đúng câu hỏi **“Nếu không đủ thông tin để xác nhận một hành động được phép, hệ thống sẽ làm gì?”**. Trong thực tế, lỗi không chỉ đến từ kẻ tấn công: một biến môi trường bị bỏ quên, hệ thống xác thực bên ngoài không phản hồi, dữ liệu đầu vào sai định dạng hoặc một cơ sở dữ liệu phân quyền bị gián đoạn đều có thể đưa ứng dụng tới trạng thái chưa xác định.

Nguyên tắc quan trọng là **không biến sự thiếu chắc chắn thành quyền truy cập**. Với thao tác nhạy cảm, hệ thống cần từ chối thực hiện hoặc tạm thời ngừng cung cấp thao tác đó cho đến khi xác minh được điều kiện an toàn. Đồng thời, phải xử lý lỗi có kiểm soát: phân biệt request không hợp lệ, thiếu quyền và dịch vụ chưa sẵn sàng; giữ dữ liệu nhất quán; ghi log hữu ích; không tiết lộ secret; và chỉ phục hồi khi đủ điều kiện.

Bài này thuộc tư duy bảo mật của Spring Security, tập trung vào cách thiết kế **safe defaults**, **fail closed**, **graceful degradation** và xử lý lỗi ở ranh giới cấu hình, phụ thuộc bên ngoài và dữ liệu người dùng.

## 1. Những nguyên tắc nền tảng

### 1.1. Fail closed, fail open và graceful degradation

| Cách ứng xử | Ý nghĩa | Ví dụ | Khi nào phù hợp |
| --- | --- | --- | --- |
| **Fail closed** | Không thể xác nhận được quyền hoặc điều kiện an toàn thì không thực hiện hành động được bảo vệ | Dịch vụ kiểm tra quyền hoàn tiền không phản hồi → không chuyển tiền | Hành động nhạy cảm, kiểm tra danh tính, quyền hoặc chính sách bảo mật |
| **Fail open** | Khi một kiểm tra thất bại, hệ thống vẫn cho hành động tiếp tục | Bỏ qua authorization vì policy server lỗi | Thường nguy hiểm đối với security gate; không chọn làm mặc định cho tác vụ nhạy cảm |
| **Fail fast** | Phát hiện cấu hình bắt buộc sai ngay lúc khởi động và báo lỗi rõ ràng | Thiếu signing key hoặc không có chính sách bảo vệ admin → ứng dụng không khởi động | Lỗi cấu hình phải được sửa trước khi nhận lưu lượng |
| **Graceful degradation** | Vẫn cung cấp phần chức năng thực sự an toàn khi một phụ thuộc khác gặp sự cố | Dịch vụ gợi ý sản phẩm lỗi → vẫn hiển thị danh mục cơ bản | Chức năng phụ không làm thay đổi quyền, tính toàn vẹn hoặc phạm vi dữ liệu |

**Fail closed không đồng nghĩa luôn trả 403.** Quyết định an toàn là *không cấp quyền hoặc không thực hiện thao tác*; thông điệp và HTTP status còn phải phản ánh tình huống. Khi dịch vụ cấp quyền bị gián đoạn, HTTP **503 Service Unavailable** thường mô tả vấn đề tốt hơn **403 Forbidden**, miễn là request vẫn không được đi tiếp để tạo tác dụng phụ.

**Fail fast không đồng nghĩa mọi trục trặc phải làm sập toàn bộ hệ thống.** Cấu hình bảo mật bắt buộc sai có thể khiến ứng dụng không được phép nhận traffic. Nhưng dịch vụ phụ trợ như recommendation lỗi có thể được xử lý ở ranh giới tính năng đó mà không ảnh hưởng đến các API quan trọng khác.

### 1.2. Phân biệt các loại kết quả

Một policy có thể trả về:

- **ALLOW**: đã kiểm tra và có bằng chứng đủ để thực hiện hành động.
- **DENY**: đã kiểm tra, kết quả cho thấy hành động không được phép.
- **UNAVAILABLE / ERROR**: chưa thể kiểm tra vì cấu hình hoặc phụ thuộc cần thiết không sẵn sàng; tuyệt đối không tự chuyển thành ALLOW.
- **INVALID_REQUEST**: dữ liệu đầu vào không đáp ứng điều kiện chấp nhận; cần từ chối và mô tả lỗi theo cách an toàn.

Không nên ép **DENY**, **UNAVAILABLE** và **INVALID_REQUEST** thành cùng một nguyên nhân nội bộ, vì cách khắc phục, retry, giám sát và HTTP response của chúng khác nhau. Tuy nhiên, cả ba đều phải ngăn thao tác được bảo vệ khi chưa có quyết định ALLOW hợp lệ.

### 1.3. Tư duy “bằng chứng cho phép”

Đối với một thao tác cần phân quyền, quy trình đơn giản là:

```text
Request đến
  |
  +-- Dữ liệu hợp lệ? -------------------- Không --> REJECT (4xx phù hợp)
  |
  +-- Cấu hình/chính sách sẵn sàng? ------ Không --> UNAVAILABLE (không thực thi)
  |
  +-- Xác thực danh tính hợp lệ? --------- Không --> UNAUTHENTICATED
  |
  +-- Kiểm tra quyền hoạt động? --------- Không --> UNAVAILABLE (không thực thi)
  |
  +-- Chính sách cho phép với tài nguyên? Không --> DENY
  |
  v
ALLOW -> thực hiện nghiệp vụ trong ranh giới an toàn
```

Đây là sơ đồ quyết định ở mức thiết kế, không phải thứ tự cố định của tất cả Spring Security filters. Một request có thể bị chặn sớm bởi CSRF hoặc một security filter khác. Mục tiêu là chỉ thực hiện thao tác sau khi **những điều kiện bắt buộc đối với thao tác đó** đã được kiểm tra thành công.

## 2. Khi thiếu hoặc sai cấu hình bảo mật

Cấu hình có thể đến từ `application.yml`, biến môi trường, secret manager, configuration server hoặc giá trị khởi tạo. Thiếu một thuộc tính không có nghĩa ứng dụng được phép tự ý bỏ chính sách bảo vệ.

### 2.1. Phân loại cấu hình theo mức độ bắt buộc

| Loại cấu hình | Ví dụ | Ứng xử an toàn khi thiếu/sai |
| --- | --- | --- |
| **Bắt buộc để xác minh tin cậy** | JWT issuer/audience, signing-key configuration, nguồn public key đáng tin cậy, secret cần thiết | Fail fast hoặc từ chối xác thực chịu ảnh hưởng; không bỏ kiểm tra chữ ký |
| **Bắt buộc để quyết định quyền** | Chính sách bảo vệ admin, danh sách permission hợp lệ, tenant boundary | Fail fast/deny; không tự chuyển thành `permitAll()` |
| **Bắt buộc để giữ dữ liệu nhất quán** | Kết nối kho dữ liệu quyền, tham số kiểm soát giao dịch | Ngừng thao tác phụ thuộc nếu không bảo đảm an toàn |
| **Tính năng tùy chọn** | Bật gợi ý, trang trí UI, telemetry không bắt buộc | Có thể dùng giá trị mặc định an toàn hoặc tắt riêng tính năng |
| **Cờ điều khiển bảo mật** | Bật bảo vệ thao tác admin, giới hạn export | Phải định nghĩa rõ chế độ mặc định; không mặc định tắt kiểm soát |

Ví dụ cấu hình **nguy hiểm**:

```java
// Ví dụ anti-pattern, không áp dụng:
if (adminAuthority == null) {
    http.authorizeHttpRequests(auth ->
        auth.requestMatchers("/api/admin/**").permitAll()
    );
}
```

Một lỗi triển khai khiến biến cấu hình trống đã trở thành **vượt quyền**. Cách sửa là yêu cầu cấu hình có giá trị hợp lệ hoặc từ chối cho ứng dụng/điểm vào nhạy cảm hoạt động.

### 2.2. Mẫu Spring Boot 3 / Spring Security 6: thiếu cấu hình thì lỗi khởi động

Với dự án Spring Boot 3 dùng `spring-boot-starter-web` và `spring-boot-starter-security`, lớp cấu hình bên dưới yêu cầu thuộc tính `app.security.admin-authority`:

```java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${app.security.admin-authority}") String adminAuthority
    ) throws Exception {
        if (adminAuthority == null || adminAuthority.isBlank()) {
            throw new IllegalStateException(
                "Required admin authority must be configured"
            );
        }

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
                .requestMatchers("/api/admin/**").hasAuthority(adminAuthority)
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Trong `application.yml`:

```yaml
app:
  security:
    admin-authority: "ROLE_ADMIN"
```

Ý nghĩa:

1. Khi thiếu thuộc tính bắt buộc, việc giải quyết placeholder của Spring không thành công; ứng dụng không tạo được security chain và không khởi động bình thường. Nếu thuộc tính là chuỗi rỗng/trắng, bước kiểm tra tường minh cũng từ chối cấu hình.
2. `/api/admin/**` chỉ chấp nhận principal có authority chính xác `ROLE_ADMIN`; mọi `/api/**` khác yêu cầu xác thực; các đường dẫn khác bị `denyAll()`.
3. `GET /public/status` được công khai theo chính sách truy cập. `permitAll()` vẫn đi qua cơ chế security filter phù hợp.
4. Ví dụ giả định ứng dụng có cơ chế cấp tài khoản/xác thực. Đây là một lớp cấu hình dành cho dự án Spring Boot, **không phải tệp Java chạy độc lập với `javac`**.
5. Trong production, endpoint health cần thiết kế phù hợp; không trả secret, nội dung cấu hình, danh sách quyền hoặc thông tin nội bộ nhạy cảm cho người gọi công khai.

Khi đổi hoặc nạp lại cấu hình bảo mật động, cần xác thực bản mới **trước khi áp dụng**. Không nên để hệ thống chuyển sang một chính sách trống trong khoảng thời gian giữa lúc xóa cấu hình cũ và tải cấu hình mới.

### 2.3. Giá trị mặc định phải an toàn theo ngữ nghĩa

Tránh các mẫu sau:

- `requiredPermission = ""` rồi xem chuỗi rỗng như quyền cho tất cả.
- `unknownRole -> ROLE_ADMIN` để “hệ thống vẫn chạy”.
- `security.enabled = false` khi thiếu biến môi trường.
- Bỏ qua xác thực token vì chưa tải được signing key.
- Tự động cấp anonymous access cho API nội bộ khi không tìm thấy user store.

Đối với policy hoặc role bắt buộc, **lỗi cấu hình nên gây sự cố khởi tạo hoặc vô hiệu hóa thao tác phụ thuộc theo cách có kiểm soát**. Đối với tùy chọn vô hại như tên hiển thị, có thể dùng giá trị mặc định để hệ thống tiếp tục hoạt động.

## 3. Khi hệ thống bên ngoài không sẵn sàng

Ứng dụng có thể phụ thuộc vào nhà cung cấp danh tính (IdP), dịch vụ cấp quyền (PDP), JWKS endpoint, Redis/session store, database, service quản lý tenant, cổng thanh toán hoặc dịch vụ nghiệp vụ khác. Cần phân biệt hai trường hợp:

- **Hệ thống ngoài trả lời hợp lệ rằng không có quyền:** đây là **DENY**.
- **Hệ thống ngoài không trả lời đáng tin cậy:** đây là **UNAVAILABLE**. Không suy đoán rằng đã được cấp quyền.

### 3.1. Ví dụ dịch vụ phân quyền ngoài bị lỗi

Giả sử `POST /api/orders/100/refund` phải xác nhận người gọi có quyền hoàn tiền và đơn hàng đáp ứng điều kiện. Khi permission service timeout:

```text
User -> API refund -> Permission service (timeout)
                         |
                         +--> Không có quyết định ALLOW đáng tin cậy
                                  |
                                  v
                            Không hoàn tiền
                                  |
                                  v
                        Phản hồi lỗi dịch vụ phù hợp
```

Không được:

```java
// Anti-pattern: timeout lại cho phép giao dịch.
try {
    return permissionClient.isAllowed(userId, orderId, "refund");
} catch (Exception ignored) {
    return true;
}
```

Thay vào đó, hãy **chặn hành động**, ghi nhận sự cố và trả lỗi có ý nghĩa. Nếu ứng dụng chọn quy đổi trạng thái phụ thuộc không sẵn sàng thành một ngoại lệ nghiệp vụ `DependencyUnavailableException` rồi trả 503, vẫn phải chắc chắn **chưa có thao tác hoàn tiền nào xảy ra**.

Phân biệt một số kết quả điển hình:

| Điều kiện | Quyết định an toàn | HTTP thường phù hợp |
| --- | --- | --- |
| Chưa cung cấp credentials / credentials sai | Không xác thực được | 401 đối với API kiểu Basic/Bearer |
| Đã xác thực nhưng policy từ chối | Không đủ quyền | 403 |
| Không tìm thấy tài nguyên | Không xử lý | 404; đôi khi dùng 404 để tránh lộ sự tồn tại tài nguyên ngoài quyền |
| Request thiếu/sai dữ liệu hợp lệ | Không xử lý | 400; một số API quy ước 422 cho lỗi ngữ nghĩa |
| Hệ thống cấp quyền hoặc dữ liệu bắt buộc đang lỗi | Không xử lý; có thể retry khi khắc phục | 503 hoặc 5xx phù hợp |
| Thao tác hợp lệ và có đủ bằng chứng cho phép | Cho xử lý | 2xx/3xx tùy API |

Mã HTTP phụ thuộc giao thức xác thực, ngữ cảnh và hợp đồng API. Ví dụ login form thường redirect tới trang đăng nhập thay vì trả 401 trực tiếp. Quan trọng hơn status là **không biến lỗi hệ thống thành ALLOW**.

### 3.2. IdP, OAuth2, JWT và JWKS: không có “đường tắt”

- **Đăng nhập mới khi IdP gián đoạn:** có thể chưa thực hiện được. Không tạo phiên đã đăng nhập chỉ dựa trên email hoặc tên do người dùng gửi.
- **JWT cần kiểm tra:** phải xác minh chữ ký, thuật toán cho phép, issuer, audience, thời hạn và các điều kiện liên quan theo kiểu token. Không thể tải khóa đáng tin cậy thì không được tự bỏ qua signature validation.
- **Khóa công khai đã được cache tin cậy:** trong phạm vi TTL và chính sách phù hợp, resource server có thể vẫn kiểm tra token cục bộ mà không cần truy cập IdP ở mỗi request. Cache có giới hạn và cần kế hoạch rotation/revocation; không kéo dài khóa hoặc quyền vô thời hạn để che lỗi.
- **Phiên đã được xác thực hợp lệ trước sự cố:** có thể tiếp tục trong giới hạn chính sách phiên và thời hạn. Tuy nhiên, nếu một thao tác đòi kiểm tra quyền mới nhất mà dịch vụ cấp quyền đang lỗi, thao tác đó vẫn phải bị chặn.
- **Identity token khác access token:** chỉ sử dụng đúng loại token và tiêu chí kiểm tra cho đúng mục đích. Không tin token chưa được xác minh hoặc token sai audience chỉ vì nó giải mã được.

Quy tắc là **chỉ tiếp tục khi đã có căn cứ xác thực và phân quyền hợp lệ theo chính sách hiện tại**. Hành vi “đã từng xác thực” không mặc định cho mọi yêu cầu tương lai.

### 3.3. Retry, timeout, circuit breaker và cache

Những kỹ thuật tăng độ bền chỉ an toàn khi không làm sai quyết định bảo mật:

1. **Timeout hữu hạn:** không treo request vô hạn. Timeout phải được coi là lỗi kiểm tra, không phải ALLOW.
2. **Retry có giới hạn:** chỉ retry thao tác an toàn khi phù hợp. Với hoàn tiền, chuyển tiền, tạo quyền hoặc cập nhật nhạy cảm, phải có idempotency key / transaction ID và logic chống xử lý lặp trước khi retry.
3. **Circuit breaker:** giảm gây quá tải dependency, nhưng trạng thái open circuit vẫn là **UNAVAILABLE**, không phải tín hiệu cho phép.
4. **Cache policy:** chỉ cache kết quả đúng phạm vi subject/action/resource/tenant, có TTL, cơ chế vô hiệu hóa và quy tắc xử lý khi quyền bị thu hồi. Cache quyết định ALLOW quá lâu có thể duy trì quyền đã bị thu hồi.
5. **Last known good:** có thể phù hợp với cấu hình đã xác minh, có phiên bản, thời hạn và chính sách quản lý. Tuyệt đối không suy diễn “bản cũ luôn an toàn”; cấu hình có thể đã bị thu hồi vì lỗ hổng hoặc thay đổi quyền.
6. **Graceful degradation:** dịch vụ gợi ý sản phẩm hoặc ảnh đại diện lỗi có thể ẩn tính năng phụ; sự cố dịch vụ phân quyền hoặc tenant isolation không được hạ tiêu chuẩn kiểm tra.

**Lưu ý giao dịch:** nếu một bước sau khi đã tạo tác dụng phụ mới phát hiện thiếu quyền hoặc phụ thuộc lỗi, chỉ trả 503 là chưa đủ. Cần thiết kế thứ tự kiểm tra, transaction/rollback, outbox, idempotency và reconciliation phù hợp để tránh trạng thái “đã làm nhưng trả lỗi”. Không nên đặt lời gọi mạng không đáng tin cậy bên trong transaction kéo dài mà không đánh giá timeout và khóa dữ liệu.

## 4. Khi dữ liệu đầu vào không hợp lệ

Dữ liệu từ request, header, path variable, query parameter, message queue và callback từ dịch vụ ngoài đều đi qua **trust boundary**. Dữ liệu có thể sai do lỗi người dùng hoặc do cố ý khai thác. Không được dùng dữ liệu chưa kiểm tra làm căn cứ cấp quyền hoặc thay đổi trạng thái.

### 4.1. Kiểm tra theo ba mức

1. **Cú pháp và kiểu dữ liệu:** JSON có hợp lệ không, trường số thực sự là số hay không, ID có đúng định dạng, trường bắt buộc có mặt không?
2. **Giới hạn và quy tắc nghiệp vụ:** amount có dương không, số lượng không vượt hạn mức, thời gian hợp lệ, trạng thái tài nguyên cho phép thao tác không?
3. **Ranh giới quyền và dữ liệu tin cậy:** người gọi có được sửa đối tượng này không, tenant có khớp nguồn đáng tin cậy không, người gọi có được gán role/price/ownerId này không?

Ví dụ request:

```json
{
  "orderId": "ORD-100",
  "amountCents": -500,
  "tenantId": "another-shop",
  "isAdmin": true
}
```

Dữ liệu trên có nhiều vấn đề độc lập. `amountCents` âm có thể vi phạm quy tắc nghiệp vụ; `tenantId` và `isAdmin` do client tự gửi không chứng minh quyền hoặc phạm vi. Kiểm tra `amountCents > 0` **không đủ** để biết người dùng có quyền hoàn tiền cho đơn hàng đó hay không.

### 4.2. Bean Validation trong Spring Boot 3

Với Spring Boot 3 dùng Spring MVC và dependency `spring-boot-starter-validation`, ta có thể khai báo DTO:

```java
package example.orders;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record RefundRequest(
    @NotBlank String orderId,
    @NotNull @Positive Long amountCents,
    @NotBlank String reason
) {}
```

Sử dụng trong controller:

```java
@PostMapping("/api/refunds")
public ResponseEntity<Void> refund(
        @Valid @RequestBody RefundRequest request,
        Authentication authentication
) {
    refundService.refund(
        authentication,
        request.orderId(),
        request.amountCents(),
        request.reason()
    );
    return ResponseEntity.noContent().build();
}
```

Đây là **hai đoạn code minh họa trong dự án Spring Boot**, không phải chương trình Java tự biên dịch bằng `javac`; controller cần các import `@PostMapping`, `@Valid`, `@RequestBody`, `ResponseEntity`, `Authentication` và một service triển khai thực. Với mặc định Spring MVC, một request body không vượt qua Bean Validation thường dẫn tới `MethodArgumentNotValidException` và HTTP 400 nếu chưa có handler tùy biến.

Điểm cần giữ: DTO **không nhận role, isAdmin hoặc tenantId như quyền đã được cấp**. Service phải lấy danh tính và quyền từ `Authentication` đã được xác thực; truy vấn đơn hàng theo tenant đáng tin cậy; kiểm tra quyền và trạng thái thực tế **trước khi hoàn tiền**. `@Valid` giải quyết kiểm tra dữ liệu đầu vào, **không thay thế authorization**.

Không nên chỉ dựa vào annotation để chống mọi lỗi: kiểu dữ liệu parse được không có nghĩa nghiệp vụ hợp lệ, và đầu vào đã hợp lệ vẫn có thể gây SQL injection/XSS nếu xử lý sai. Cần thêm truy vấn có tham số, output encoding, giới hạn độ dài, canonicalization phù hợp, kiểm soát đường dẫn/tệp và ràng buộc domain.

### 4.3. Khi dữ liệu đến từ dịch vụ ngoài

Một HTTP 200 từ hệ thống bên ngoài không chứng minh nội dung đáng tin cậy. Cần xác thực schema, các trường bắt buộc, định danh/tenant, chữ ký hoặc nguồn phát tin khi giao thức yêu cầu. Ví dụ:

- Payment webhook chưa kiểm tra chữ ký không được phép cập nhật trạng thái thanh toán.
- Event có `userId` không được tự động coi user đó là caller đã xác thực của API.
- Kết quả PDP trả một response không parse được không được diễn giải thành ALLOW.
- Nếu có trường `decision` mới hoặc lạ, mặc định từ chối / báo lỗi giao thức thay vì tự coi là true.
- Khi dữ liệu thiếu ownerId hoặc tenantId cần để kiểm tra quyền, không mặc định “không có owner nghĩa là ai cũng xem được”.

### 4.4. Không chữa dữ liệu sai bằng cách tự tăng quyền

Những anti-pattern nguy hiểm:

```java
// Không áp dụng các mẫu này.
boolean isAdmin = request.isAdmin();            // tin lời client
String tenantId = request.tenantId();           // tin phạm vi tự khai
String owner = order.ownerId() == null ? "*" : order.ownerId();
boolean canWrite = lookupPermission(user) == null; // null thành ALLOW
```

Thay vào đó, hãy xác minh principal và quyền qua cơ chế đáng tin cậy; kiểm tra owner/tenant từ dữ liệu server; và giữ yêu cầu thay đổi trạng thái ở trạng thái chưa thực hiện nếu thông tin quyết định không đầy đủ.

## 5. Mẫu Java 17 chạy độc lập: quyết định an toàn với bốn kết quả

Ví dụ mô phỏng một cổng kiểm tra quyền truy cập và hoàn tiền. Mục đích là thấy rõ **cấu hình thiếu**, **phụ thuộc không sẵn sàng**, **dữ liệu sai** và **thiếu quyền** khác nhau thế nào mà không trường hợp nào bị coi là ALLOW.

Tạo tệp **`SafeDecisionDemo.java`**:

```java
import java.util.Set;

public class SafeDecisionDemo {

    enum Action { READ_ORDER, REFUND }

    enum Decision { ALLOW, DENY, INVALID_REQUEST, UNAVAILABLE }

    record Config(boolean policyConfigured) {}

    record Principal(
        String userId,
        String tenantId,
        boolean authenticated,
        Set<String> permissions
    ) {}

    record Request(
        String orderId,
        String tenantId,
        Action action,
        long amountCents
    ) {}

    @FunctionalInterface
    interface OwnershipGateway {
        boolean isOwner(Principal principal, Request request)
            throws DependencyUnavailableException;
    }

    static class DependencyUnavailableException extends Exception {}

    static Decision decide(
        Config config,
        Principal principal,
        Request request,
        OwnershipGateway gateway
    ) {
        // Không đưa dữ liệu sai vào logic nghiệp vụ.
        if (request == null
                || request.orderId() == null
                || request.orderId().isBlank()
                || request.tenantId() == null
                || request.tenantId().isBlank()
                || request.action() == null
                || (request.action() == Action.REFUND
                    && request.amountCents() <= 0)) {
            return Decision.INVALID_REQUEST;
        }

        // Thiếu policy hoặc dependency cần thiết: không cấp quyền.
        if (config == null || !config.policyConfigured()
                || gateway == null) {
            return Decision.UNAVAILABLE;
        }

        if (principal == null || !principal.authenticated()
                || principal.userId() == null
                || principal.tenantId() == null
                || principal.permissions() == null) {
            return Decision.DENY;
        }

        // Tenant của principal đã được xác minh, không tự tin request.
        if (!principal.tenantId().equals(request.tenantId())) {
            return Decision.DENY;
        }

        String requiredPermission = switch (request.action()) {
            case READ_ORDER -> "order:read";
            case REFUND -> "order:refund";
        };

        if (!principal.permissions().contains(requiredPermission)) {
            return Decision.DENY;
        }

        try {
            return gateway.isOwner(principal, request)
                ? Decision.ALLOW : Decision.DENY;
        } catch (DependencyUnavailableException ex) {
            return Decision.UNAVAILABLE;
        }
    }

    public static void main(String[] args) {
        Config ready = new Config(true);
        Config missing = new Config(false);

        Principal alice = new Principal(
            "alice", "shop-a", true,
            Set.of("order:read", "order:refund")
        );
        Principal bob = new Principal(
            "bob", "shop-a", true, Set.of("order:read")
        );
        Principal anonymous = new Principal(
            "guest", "shop-a", false, Set.of("order:read")
        );

        Request read = new Request(
            "ORD-100", "shop-a", Action.READ_ORDER, 0
        );
        Request invalidRefund = new Request(
            "ORD-100", "shop-a", Action.REFUND, -100
        );

        OwnershipGateway ownerLookup = (subject, request) ->
            subject.userId().equals("alice")
                && request.orderId().equals("ORD-100");

        OwnershipGateway offline = (subject, request) -> {
            throw new DependencyUnavailableException();
        };

        System.out.println("Normal: "
            + decide(ready, alice, read, ownerLookup));
        System.out.println("Different owner: "
            + decide(ready, bob, read, ownerLookup));
        System.out.println("Anonymous: "
            + decide(ready, anonymous, read, ownerLookup));
        System.out.println("Invalid refund: "
            + decide(ready, alice, invalidRefund, ownerLookup));
        System.out.println("Missing config: "
            + decide(missing, alice, read, ownerLookup));
        System.out.println("Dependency down: "
            + decide(ready, alice, read, offline));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac SafeDecisionDemo.java
java SafeDecisionDemo
```

**Stdout chính xác:**

```text
Normal: ALLOW
Different owner: DENY
Anonymous: DENY
Invalid refund: INVALID_REQUEST
Missing config: UNAVAILABLE
Dependency down: UNAVAILABLE
```

Giải thích từng trường hợp:

- **Normal:** Alice có quyền `order:read`, cùng tenant và sở hữu đơn, nên được ALLOW.
- **Different owner:** Bob đã đăng nhập và có quyền đọc chung nhưng không sở hữu đúng đơn; gateway quyết định DENY.
- **Anonymous:** không có trạng thái authenticated, nên DENY mà không gọi gateway.
- **Invalid refund:** số tiền âm bị chặn trước khi kiểm tra quyền hay thực hiện tác dụng phụ.
- **Missing config:** không thể tin quyết định policy, nên trả UNAVAILABLE; không có nhánh mặc định cho ALLOW.
- **Dependency down:** ngoại lệ từ gateway được chuyển thành UNAVAILABLE, bảo toàn nguyên tắc không cấp quyền khi không có bằng chứng.

Ví dụ cố ý đơn giản hóa: principal, permission và tenant được thiết lập bằng code; trong ứng dụng thật phải lấy từ cơ chế xác thực/nguồn tin cậy. `OwnershipGateway` phải truy vấn dữ liệu thật với phạm vi tenant, kiểm tra trạng thái và các điều kiện nghiệp vụ. Kết quả `Decision.ALLOW` trong ví dụ chỉ là **quyết định**, chưa tự thực hiện hoàn tiền. Cách ánh xạ sang HTTP và thực thi transaction thuộc controller/service.

### 5.1. Ánh xạ trạng thái nội bộ sang kết quả API

| Decision | Hướng xử lý | Lưu ý |
| --- | --- | --- |
| `ALLOW` | Tiếp tục nghiệp vụ có kiểm soát | Vẫn cần transaction, kiểm tra trạng thái, chống xử lý lặp |
| `DENY` | Ngừng, thường 403 | Nếu chưa có identity hợp lệ, cơ chế xác thực có thể trả 401 |
| `INVALID_REQUEST` | Ngừng, trả 400/422 theo hợp đồng | Không gửi stack trace hoặc dữ liệu nhạy cảm |
| `UNAVAILABLE` | Ngừng, trả 503/5xx phù hợp | Giám sát, xử lý sự cố, retry an toàn nếu thích hợp |

Trong ví dụ học tập, ta dùng cùng kiểu `Decision` để dễ thấy mọi nhánh. Production có thể sử dụng exception hoặc kiểu kết quả phong phú hơn; điều bắt buộc là **không đánh đồng lỗi phụ thuộc với quyền truy cập được cấp**.

## 6. Áp dụng vào vòng đời request của Spring Security

Trong ứng dụng Servlet, các kiểm soát có thể được tổ chức như sau:

```text
HTTP request
    |
    v
SecurityFilterChain
    |-- CSRF / request protections (khi áp dụng)
    |-- Authentication filter: credentials/token/session
    |-- AuthorizationFilter: URL + HTTP method policy
    v
Controller / Bean Validation
    |
    v
Application Service
    |-- Đọc tài nguyên theo tenant đáng tin cậy
    |-- Quyền trên object + điều kiện nghiệp vụ
    |-- Xác minh dịch vụ phụ thuộc (nếu policy yêu cầu)
    v
Transaction / Side effect -> Response
```

Sơ đồ chỉ diễn tả **trách nhiệm**. Thứ tự filter thực tế phụ thuộc security chain và phiên bản/cấu hình; một số lỗi input có thể xảy ra trước controller và được Spring MVC xử lý.

### 6.1. Không biến lỗi thành quyền trong security filter

- Khi JWT không hợp lệ hoặc hết hạn, không tạo một `Authentication` đã xác thực một cách thủ công.
- Khi thiếu `SecurityContext`, không “tạm cho là ADMIN” để request đi tiếp.
- Khi rule chính sách không xác định, dùng deny/fail-safe thay vì fallback `permitAll()`.
- Khi CSRF token thiếu/sai trong bối cảnh cần CSRF, không bỏ kiểm tra chỉ vì endpoint có quyền `authenticated()`.
- Với resource server, chỉ chấp nhận token từ issuer/audience tin cậy và verify signature. Không decode base64 rồi coi claims là danh tính xác thực.

### 6.2. Xử lý ngoại lệ: đúng tầng, không rò rỉ

Spring Security thường dùng `AuthenticationEntryPoint` để khởi tạo yêu cầu xác thực và `AccessDeniedHandler` cho trường hợp bị từ chối truy cập. Ứng dụng cũng có thể dùng `@RestControllerAdvice` để biểu diễn lỗi validation hoặc dịch vụ nghiệp vụ theo hợp đồng API.

| Nhóm lỗi | Nơi thường xử lý | Cách phản hồi nên hướng tới |
| --- | --- | --- |
| Chưa đăng nhập / token không hợp lệ | Security authentication handlers | 401/challenge hoặc redirect, không xác thực giả |
| Có principal nhưng thiếu quyền | Security access-denied handling, method security | 403 hoặc chính sách che sự tồn tại tài nguyên |
| DTO sai format/constraint | Spring MVC validation/exception handling | 400, chỉ hiển thị thông tin field cần thiết |
| Policy service timeout | Service boundary + exception handler | 503 hoặc mã 5xx phù hợp, không thực hiện nghiệp vụ |
| Bug nội bộ không lường trước | Error handling chung | 500, log phục vụ điều tra, không trả stack trace/secret cho client |

Lưu ý: lỗi phân quyền có thể xảy ra trong filter chain hoặc method security; đừng giả định một `@ControllerAdvice` tự xử lý mọi loại exception trước khi security filters hoạt động. Cần kiểm tra hành vi thật bằng integration test.

### 6.3. Tránh lẫn lộn “giảm chất lượng dịch vụ” và “hạ chính sách bảo vệ”

Một chính sách giảm cấp hợp lý phải nói rõ **chức năng nào vẫn an toàn khi phụ thuộc lỗi**:

- Được phép: tạm ẩn gợi ý sản phẩm nếu recommendation engine offline.
- Có thể được phép: hiển thị dữ liệu công khai đã cache, nếu cache có nguồn và phạm vi an toàn.
- Không được phép: tiếp tục hoàn tiền khi service cấp quyền không phản hồi.
- Không được phép: trả dữ liệu tenant khác vì bộ lọc tenant bị timeout.
- Không được phép: bỏ qua xác minh token do IdP hoặc JWKS endpoint đang gián đoạn.

Nếu cần đường dự phòng cho nghiệp vụ nhạy cảm, đó phải là **một thiết kế được phê duyệt từ trước, có điều kiện xác thực/phân quyền tương đương hoặc chặt hơn, giới hạn thời gian và audit**; không được tự sinh một bypass trong catch block.

## 7. Dữ liệu và giao dịch phải nhất quán khi xảy ra lỗi

Không có quyền mà vẫn thực hiện tác dụng phụ là lỗi nghiêm trọng. Nhưng ngay cả khi quyền đúng, thất bại giữa các bước cũng có thể tạo trạng thái không nhất quán.

Ví dụ hoàn tiền:

```text
1. Validate số tiền và trạng thái đơn.
2. Authenticate principal, xác minh tenant, role/permission và quyền trên đơn.
3. Kiểm tra hạn mức, idempotency và điều kiện tài chính.
4. Gửi lệnh hoàn tiền tới payment provider.
5. Ghi nhận kết quả giao dịch và audit.
```

Nếu bước 4 timeout, không thể tự kết luận “chưa hoàn tiền” vì phía provider có thể đã nhận và xử lý yêu cầu. Cần lưu request ID/idempotency key, tra cứu trạng thái và reconcile an toàn. Nếu vội retry không có khóa idempotency, khách hàng có thể được hoàn tiền hai lần.

Một số quy tắc thực tế:

- **Kiểm tra điều kiện trước tác dụng phụ**; không gọi provider rồi mới kiểm tra authorization.
- **Transaction DB** giúp rollback thay đổi trong DB nhưng không tự rollback được yêu cầu mạng đã gửi ra ngoài.
- **Idempotency** là yêu cầu quan trọng khi retry tạo giao dịch, thay đổi quyền hoặc gửi thông báo có tác dụng phụ.
- **Không coi timeout là thành công hay thất bại chắc chắn** nếu phía đối tác có thể đã xử lý; sử dụng trạng thái PENDING/UNKNOWN khi cần và đối soát.
- **Dữ liệu có thể đổi giữa lúc check và lúc write**; với trạng thái đơn hoặc quyền có tính cạnh tranh, áp dụng transaction, version check, conditional update hoặc cơ chế đồng bộ thích hợp.
- **Giới hạn quyền của các worker bất đồng bộ**: job hay consumer không tự động sở hữu quyền của request gốc. Cần mô hình danh tính, phạm vi tenant và quyền thực thi rõ ràng.

## 8. Observability và phục hồi mà không tiết lộ dữ liệu

Khi fail closed, hệ thống vẫn phải giúp đội vận hành phân biệt “bị từ chối hợp lệ” với “không thể xác minh vì lỗi hạ tầng”.

### 8.1. Logging và metrics

Nên ghi có kiểm soát:

- Loại hành động, loại tài nguyên, thời điểm và correlation/request ID;
- Loại kết quả: `DENY`, `UNAVAILABLE`, `INVALID_REQUEST`;
- Lý do kỹ thuật ở dạng mã ổn định, ví dụ `AUTHZ_DEPENDENCY_TIMEOUT`, `CONFIG_MISSING`, `VALIDATION_ERROR`;
- Thời gian phản hồi, tên nhóm dependency và trạng thái circuit breaker;
- Định danh chủ thể hoặc tenant đã được làm sạch/giới hạn truy cập, theo yêu cầu riêng tư.

**Không ghi** password, access token, refresh token, secret, full Authorization header, giá trị nhạy cảm của request hoặc stack trace ra response công khai. Cần phân quyền đọc log vì bản thân log cũng là tài sản cần bảo vệ. Tránh đưa thông tin user/tenant vào nhãn metric làm cardinality bùng nổ.

### 8.2. Health và readiness

- **Liveness** nói tiến trình còn sống hay không.
- **Readiness** nói instance có sẵn sàng nhận traffic hay không.
- Nếu cấu hình bảo mật bắt buộc chưa có, instance không nên được đánh dấu ready chỉ vì HTTP server đã chạy.
- Nếu phụ thuộc chỉ ảnh hưởng một tính năng, có thể trả trạng thái lỗi tại tính năng đó thay vì khiến toàn bộ hệ thống ngừng phục vụ. Quyết định phụ thuộc phạm vi ứng dụng và yêu cầu vận hành.

Không công khai trạng thái cấu hình chi tiết, stack trace, secret hay phiên bản nội bộ qua health endpoint.

### 8.3. Phục hồi có điều kiện

Khi dịch vụ ngoài trở lại, cần kiểm tra các request mới theo chính sách đang có hiệu lực. Nếu quyết định cũ đã bị cache hoặc nếu có queue thao tác đang chờ, không giả định mọi yêu cầu vẫn được phép. Với tác vụ nhạy cảm được xử lý trễ, có thể cần xác thực lại hiệu lực ủy quyền hoặc quyền tại thời điểm thực thi theo chính sách nghiệp vụ.

## 9. Checklist kiểm thử thất bại theo nguyên nhân

| Tình huống thử | Kết quả phải kiểm tra | Điều không được xảy ra |
| --- | --- | --- |
| Thiếu security property bắt buộc | Startup lỗi rõ hoặc endpoint nhạy cảm không sẵn sàng | Tự chuyển endpoint sang public |
| Giá trị cấu hình là chuỗi trống/sai | Bị từ chối theo quy tắc validation | Mặc định role ADMIN hoặc authority trống được phép |
| JWT hết hạn hoặc chữ ký sai | Không thiết lập identity đã xác thực | Bỏ qua verify hoặc suy ra quyền từ claims chưa xác minh |
| Policy service timeout | Không thực hiện hành động; lỗi service được quan sát | Timeout được diễn giải thành ALLOW |
| Policy service trả DENY | Request bị chặn | Retry để “tìm một ALLOW khác” |
| User đã đăng nhập nhưng thiếu role | Bị từ chối theo authorization | Request vẫn tới thao tác nhạy cảm |
| Dữ liệu JSON sai kiểu hoặc trường bắt buộc thiếu | Trả 400/4xx, không gọi nghiệp vụ | Giá trị sai được thay bằng quyền cao hơn |
| Tenant trong request bị thay đổi | Từ chối truy cập ngoài phạm vi | Tin tenant do client khai |
| DB không trả kết quả owner | Không cho phép dựa trên dữ liệu thiếu | Coi owner null là public |
| Payment provider timeout sau khi gửi lệnh | Ghi trạng thái không chắc chắn và đối soát | Tự retry vô hạn hoặc hoàn tiền hai lần |
| Tính năng không nhạy cảm offline | Phần an toàn còn lại hoạt động phù hợp | Lỗi tính năng phụ làm bỏ kiểm soát bảo mật |
| CSRF token không hợp lệ trên request cần bảo vệ | Request bị chặn | Tự tắt CSRF để request thành công |

Các test nên chạy với tài khoản không có quyền, đúng quyền, sai tenant, request thiếu trường, service dependency trả 500, timeout và đáp ứng không đúng schema. Đặc biệt, **kiểm tra tác dụng phụ**: không chỉ assert status code mà còn assert không có dữ liệu bị sửa, không có sự kiện/giao dịch bị phát sinh, không có quyền được cấp.

Trong Spring Boot, có thể dùng MockMvc cho các request-level cases, integration test với dependency giả lập để tạo timeout và test ở service/DB để chứng minh side effects không xảy ra. Một test “được trả 403” chưa đủ nếu transaction thực ra đã commit.

## 10. Những sai lầm cần tránh

1. **Catch mọi exception rồi cho phép:** `catch (Exception e) { return true; }` biến lỗi hạ tầng thành vượt quyền.
2. **Bỏ policy khi config trống:** một deployment lỗi có thể trở thành lỗ hổng hệ thống.
3. **Gộp mọi lỗi thành “không có quyền”:** khó phân biệt sự cố vận hành với chủ thể thiếu quyền; dễ phát sinh retry sai.
4. **Tin header/body/query để lấy role và tenant:** dữ liệu do client tự khai chưa được xác minh.
5. **Dùng cache ALLOW không giới hạn:** quyền có thể đã bị thu hồi; cần TTL, scope và cập nhật chính sách.
6. **Tắt CSRF do POST trả 403:** phải phân tích cơ chế xác thực, token và threat model trước khi thay đổi.
7. **Retry giao dịch khi chưa biết kết quả:** gây tạo trùng tác dụng phụ, nhất là thanh toán/hoàn tiền.
8. **Trả nguyên stack trace cho client:** có thể tiết lộ đường dẫn nội bộ, cấu hình, thông tin user và secret.
9. **Chỉ kiểm thử status code:** cần chứng minh dữ liệu không thay đổi khi request không được phép hoặc dependency lỗi.
10. **Cho rằng mọi lỗi phải làm toàn bộ ứng dụng dừng:** chọn ranh giới ảnh hưởng đúng; giữ chức năng không phụ thuộc và an toàn khi có thể.

## 11. Câu hỏi tự kiểm tra

**1.** Một biến môi trường chứa authority admin bị thiếu. Nếu code fallback sang `permitAll()` cho `/api/admin/**`, hệ quả là gì?

**2.** Dịch vụ phân quyền timeout khi xử lý yêu cầu hoàn tiền. Hệ thống nên trả DENY hay UNAVAILABLE, và có được tiếp tục hoàn tiền không?

**3.** Khi IdP offline, resource server có bắt buộc bỏ qua xác minh JWT để giữ tính sẵn sàng không?

**4.** DTO hoàn tiền có amount hợp lệ. Tại sao vẫn phải kiểm tra principal, tenant, quyền trên order và trạng thái nghiệp vụ?

**5.** Vì sao HTTP 503 không có nghĩa “fail open”?

**6.** Một lệnh hoàn tiền gửi tới payment provider bị timeout. Vì sao không nên lập tức gọi lại mà không có idempotency key hoặc reconciliation?

**7.** Vì sao một giá trị ALLOW trong cache có thể trở nên không an toàn dù lúc đầu nó được tính đúng?

**Đáp án gợi ý:**

1. Endpoint quản trị có thể trở thành công khai khi cấu hình sai; phải fail fast hoặc từ chối đúng chức năng.
2. Đây là UNAVAILABLE nếu chưa có quyết định; tuyệt đối không tiếp tục hành động nhạy cảm.
3. Không. Có thể xác thực cục bộ bằng khóa còn tin cậy và chính sách cache hợp lệ; nếu không đủ bằng chứng kiểm tra, không chấp nhận token.
4. Validation chỉ kiểm tra dữ liệu đầu vào; authorization và domain invariants là điều kiện độc lập.
5. Fail closed nghĩa là hành động không được thực hiện khi không đủ căn cứ an toàn; 503 là cách diễn đạt phụ thuộc chưa sẵn sàng.
6. Đối tác có thể đã hoàn tiền; retry không kiểm soát có thể hoàn tiền lặp.
7. Quyền có thể bị thu hồi, tenant thay đổi, policy đổi hoặc TTL hết hạn; phải giới hạn thời gian và khả năng làm mới/thu hồi.

### Tài liệu tham khảo

- [Spring Security Reference – Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Security Reference – Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
