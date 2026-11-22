# Cache-Control và kiểm soát lưu đệm nội dung nhạy cảm trong Spring Security Servlet

## 1. Mục tiêu và phạm vi

HTTP cache giúp giảm độ trễ và lưu lượng: trình duyệt, reverse proxy hoặc CDN có thể giữ bản sao của một phản hồi để dùng lại. Điều đó hữu ích cho CSS, JavaScript và hình ảnh công khai; nhưng có thể làm **lộ nội dung cá nhân, thông tin đăng nhập, hóa đơn, dữ liệu tài khoản hoặc bản xuất báo cáo** nếu phản hồi được lưu và dùng lại sai ngữ cảnh.

Trong ứng dụng **Spring Security Servlet**, lớp bảo vệ HTTP cần trả chính sách cache rõ ràng cho tài nguyên nhạy cảm. Chủ đề này tập trung vào việc hiểu `Cache-Control`, cách Spring Security ghi các header mặc định, lúc nào cần `no-store` và khi nào có thể cache tài nguyên công khai để tối ưu hiệu năng.

Sau bài này, bạn có thể:
- Phân biệt `no-store`, `no-cache`, `private`, `public`, `max-age`, `s-maxage`, `must-revalidate` và `immutable` theo hành vi thực tế.
- Giải thích vì sao phản hồi có cookie, đã xác thực hoặc có thông tin người dùng không tự động an toàn với mọi cache.
- Dùng cấu hình `SecurityFilterChain`, Spring MVC và `ResponseEntity` để bảo vệ dữ liệu nhạy cảm mà vẫn cache đúng các static assets.
- Kiểm tra header trên phản hồi thật và trong `MockMvc`; tìm lỗi ở browser, reverse proxy/CDN và Service Worker.

## 2. Cache xuất hiện ở đâu và rủi ro là gì?

Một phản hồi từ ứng dụng Servlet có thể đi qua nhiều lớp:

```text
Browser
  |-- memory/disk HTTP cache
  |-- back/forward navigation history (bfcache có cơ chế riêng)
  |-- Service Worker + Cache API (nếu ứng dụng có đăng ký)
        |
        v
Reverse proxy / CDN / API gateway (shared cache, tùy cấu hình)
        |
        v
Spring Security Filter Chain -> Spring MVC controller -> response
```

Ví dụ: `GET /api/me` trả tên, email và quyền của Alice. Nếu CDN lưu bản phản hồi này bằng chính sách `public, max-age=3600` và cache key không phân biệt người dùng, yêu cầu sau có thể nhận nội dung của Alice dù thuộc Bob. Ngay cả khi cache key đã phân biệt, một browser dùng chung máy vẫn có thể giữ phản hồi nhạy cảm trong bộ nhớ/đĩa.

**Mục tiêu bảo vệ:** hạn chế hoặc ngăn cache HTTP lưu phản hồi nhạy cảm, đặc biệt tại shared cache; tránh cho dữ liệu của người dùng này xuất hiện khi người dùng khác dùng lại phiên/trình duyệt; bảo đảm phiên đã logout không để UI tùy tiện hiển thị dữ liệu đã cũ.

**Giới hạn:** `Cache-Control` là chỉ thị cho cache tuân thủ HTTP, **không phải công cụ xóa sạch dữ liệu**. Nó không bảo đảm xóa file người dùng tải về, log, ảnh chụp màn hình, bản sao ở backend, nội dung đã hiển thị trong RAM, hay mọi trạng thái của bfcache/Service Worker. Vẫn phải dùng xác thực, phân quyền, TLS, thiết kế cache key và cơ chế logout phù hợp.

## 3. Hiểu đúng các chỉ thị Cache-Control

| Chỉ thị | Cache được lưu không? | Ý nghĩa đối với nội dung nhạy cảm |
| --- | --- | --- |
| `no-store` | Cache tuân thủ không được lưu request/response theo chỉ thị | **Lựa chọn ưu tiên** cho trang/JSON/dữ liệu bí mật; ngăn cache HTTP lưu bản sao |
| `no-cache` | **Có thể lưu**, nhưng phải xác thực lại với server trước khi tái sử dụng | Không đủ nếu yêu cầu là “không lưu nội dung nhạy cảm” |
| `private` | Cho phép cache riêng của browser, cấm shared cache lưu phản hồi theo ngữ nghĩa chỉ thị | Giúp tránh shared cache, nhưng browser vẫn có thể lưu; không thay `no-store` |
| `public` | Cho phép shared cache lưu, kể cả một số trường hợp vốn bị giới hạn | Chỉ dùng cho tài nguyên thực sự công khai |
| `max-age=600` | Phản hồi được coi là fresh tối đa 600 giây sau mốc tuổi được tính | Phù hợp với nội dung cache được; không đặt cho JSON cá nhân |
| `s-maxage=600` | Đặt thời gian fresh dành cho **shared caches**, ưu tiên hơn `max-age` ở shared cache | Cần kiểm soát chặt CDN/reverse proxy; không dùng cho dữ liệu riêng tư |
| `must-revalidate` | Khi phản hồi stale, cache phải xác thực lại trước khi dùng | Không ngăn lần lưu ban đầu; thường đi với `no-cache` hoặc `max-age` |
| `immutable` | Báo tài nguyên được version hóa và không đổi trong thời gian còn fresh | Chỉ phù hợp asset công khai có hash/tên phiên bản |
| `max-age=0` | Thường lập tức stale, cần cơ chế revalidate trước khi dùng | **Không** đồng nghĩa với cấm lưu |
| `no-transform` | Yêu cầu trung gian không biến đổi nội dung | Không phải chỉ thị chống lưu cache |

Một số ví dụ:

```http
# Phản hồi nhạy cảm: không lưu ở HTTP cache.
Cache-Control: no-store

# Cache có thể lưu nhưng cần hỏi server trước khi tái sử dụng.
Cache-Control: no-cache

# Dữ liệu chỉ được cache tại browser, không ở shared proxy.
Cache-Control: private, max-age=60

# Asset công khai có fingerprint trong tên file.
Cache-Control: public, max-age=31536000, immutable
```

`Pragma: no-cache` và `Expires: 0` thường xuất hiện để hỗ trợ client HTTP cũ; trong hệ thống hiện đại, `Cache-Control` là chỉ thị chính. `Expires: 0` là mẫu tương thích cũ thường thấy trong Spring Security, không có nghĩa đã xóa mọi cache.

**Quy tắc thực hành:** với phản hồi chứa bí mật hoặc dữ liệu theo người dùng, dùng `no-store`; `private` đơn lẻ chỉ ngăn shared cache, còn `no-cache` đơn lẻ vẫn cho phép lưu để revalidate.

## 4. Mặc định của Spring Security Servlet

Khi bật HTTP headers mặc định trên `SecurityFilterChain`, Spring Security thêm các header chống cache cho phản hồi chưa có chính sách cache được ứng dụng thiết lập:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

Spring Security dùng `HeaderWriterFilter` và thành phần ghi cache header (thường là `CacheControlHeadersWriter`) để xử lý. Với cấu hình mặc định, những header này giúp các trang động được bảo vệ khỏi việc cache HTTP thông thường.

Hai điểm cần nhớ:

1. **Cấu hình mặc định không tự tạo policy cache tối ưu cho mọi loại tài nguyên.** Một ảnh công khai đã được version hóa có thể muốn cache lâu hơn, trong khi API cá nhân cần `no-store`. Cần xác định chính sách theo độ nhạy và vòng đời nội dung.
2. **Khi ứng dụng đã đặt `Cache-Control`, Spring Security không ghi đè vô điều kiện bằng header cache mặc định.** Vì thế controller, filter, Spring MVC resource handler, reverse proxy hoặc CDN có thể làm chính sách cuối cùng khác với suy nghĩ “Spring Security chắc chắn sẽ chặn cache”. Luôn kiểm tra header thực tế tại biên client.

Phân biệt `authorizeHttpRequests(...permitAll())` và `web.ignoring()`: `permitAll` vẫn đưa request qua security filter chain và các security headers; `web.ignoring()` bỏ qua toàn bộ chain, có thể làm mất header cần thiết và khiến hành vi kiểm tra khác đi. Với asset công khai, ưu tiên `permitAll` và thiết lập cache rõ ràng.

## 5. Chọn chính sách theo tài nguyên

| Loại phản hồi | Ví dụ | Chính sách gợi ý | Lý do |
| --- | --- | --- | --- |
| Trang tài khoản đã đăng nhập | `/account`, `/settings` | `no-store` | Dữ liệu riêng và trạng thái người dùng thay đổi |
| API trả dữ liệu cá nhân | `/api/me`, `/api/orders` | `no-store` | Tránh bản sao tại browser/shared cache |
| Login/logout/đổi mật khẩu | Trang form có token, phản hồi sau login/logout | `no-store` | Tránh lưu nội dung và state nhạy cảm |
| Token, mã khôi phục, OTP | `/api/session`, màn hình xác minh | `no-store` | Nội dung nhạy cảm, thời gian sống ngắn |
| Tệp xuất có dữ liệu khách hàng | PDF/CSV báo cáo, statement | `no-store` | `Content-Disposition: attachment` không thay chính sách cache |
| Ảnh/CSS/JS công khai có fingerprint | `/assets/app.a1b2c3.js` | `public, max-age=31536000`; cân nhắc `immutable` | Nội dung bất biến theo version, dễ cache an toàn |
| HTML shell của SPA có thể thay đổi | `/index.html` | `no-cache` hoặc TTL ngắn theo thiết kế | Cho browser revalidate khi deploy; không dùng TTL dài như asset hash |
| Dữ liệu công khai thay đổi theo thời gian | Catalog/FAQ không cá nhân | `public, max-age=<TTL phù hợp>` | Cache có lợi nếu chấp nhận độ cũ |
| Phản hồi lỗi chứa dữ liệu nhạy cảm | 401/403 và thông tin context, lỗi đã redacted | `no-store` khi có nội dung nhạy cảm | HTTP status lỗi không bảo đảm không bị cache |

Giải quyết theo **độ nhạy nội dung**, không chỉ theo URL hay việc controller có annotation `@PreAuthorize`. Một response 200 public có cookie `Set-Cookie` cần kiểm tra kỹ; một response 302 chuyển hướng cũng có thể mang thông tin nhạy cảm. Cookie hiện diện hoặc request chứa `Authorization` **không thay thế** chính sách `Cache-Control` rõ ràng. HTTP caching có quy tắc đặc biệt cho request mang `Authorization`, nhưng không nên dựa vào đó để bảo vệ mọi kiểu session/cookie hay cấu hình CDN.

## 6. Cấu hình Java 17+ trên Spring Boot 3 / Spring Security 6

Các ví dụ dưới đây là **mã đặt trong ứng dụng Spring Boot Servlet**, dùng `spring-boot-starter-web` và `spring-boot-starter-security`. Chúng không phải một file Java tự chạy bằng `javac` thuần; cần lớp chính `@SpringBootApplication`, các dependencies và Spring Boot runtime.

### 6.1. Giữ security headers cho trang động, ngoại lệ hẹp cho assets

File `SecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    // Chỉ các tệp asset công khai, version hóa.
    @Bean
    @Order(1)
    SecurityFilterChain assetChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/assets/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .headers(headers -> headers
                .cacheControl(cache -> cache.disable()));
        return http.build();
    }

    // Mọi đường dẫn khác, bao gồm nội dung cá nhân.
    @Bean
    @Order(2)
    SecurityFilterChain appChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults()));
        return http.build();
    }
}
```

Trong `appChain`, phần `cacheControl(Customizer.withDefaults())` chỉ làm rõ chính sách mặc định; các header bảo mật khác vẫn hoạt động. Trong `assetChain`, ta chỉ **tắt cache-control header writer cho đúng pattern `/assets/**`**, không tắt toàn bộ security headers hay security filter. Request chọn chain theo matcher và thứ tự `@Order`; cấu hình phải phù hợp các chain có sẵn trong dự án thật.

**Điều kiện bắt buộc:** `/assets/**` chỉ chứa tệp công khai, không chứa file tải lên cá nhân, dữ liệu sinh theo user hoặc HTML đăng nhập. Việc tắt cache writer ở chain này giao trách nhiệm phát cache policy cho static resource handler hoặc hạ tầng web.

### 6.2. Đặt cache dài cho asset có version/hash

File `AssetCacheConfig.java`:

```java
import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AssetCacheConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(Duration.ofDays(365)).cachePublic()
            );
    }
}
```

Ví dụ này phục vụ các file tại `src/main/resources/static/assets/` qua `/assets/**`. Header thường có `public` và `max-age=31536000`. Chỉ áp dụng TTL một năm nếu **tên asset có fingerprint và nội dung tại URL đó không bao giờ bị ghi đè**: ví dụ `app.a1b2c3.js`. Nếu tên file cố định như `app.js` và mỗi deploy thay nội dung, cache dài sẽ khiến client chạy phiên bản cũ; cần TTL ngắn hoặc yêu cầu revalidate. Có thể bổ sung `immutable` nếu hạ tầng và asset thật sự bất biến.

### 6.3. Ghi chính sách bảo mật tại endpoint nhạy cảm

File `AccountController.java`:

```java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {
    @GetMapping("/api/me")
    ResponseEntity<AccountView> me(Authentication authentication) {
        AccountView body = new AccountView(authentication.getName());

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    record AccountView(String username) {}
}
```

Vì `appChain` yêu cầu xác thực, `Authentication` có danh tính của người dùng đã đăng nhập; controller trả dữ liệu riêng của họ. `ResponseEntity.cacheControl(CacheControl.noStore())` chủ động đặt response header `Cache-Control: no-store`, cho thấy policy ngay tại nguồn. Spring Security mặc định cũng bảo vệ response động, nhưng đặt trực tiếp ở endpoint nhạy cảm giúp ý định rõ ràng nếu cấu hình header được thay đổi về sau.

Không nhầm `Content-Type`, `Content-Security-Policy`, `X-Content-Type-Options` với `Cache-Control`: chúng bảo vệ các mặt khác của HTTP response. Cũng không dựa vào `Content-Disposition: attachment` để ngăn PDF/CSV chứa thông tin cá nhân được lưu bởi HTTP cache.

## 7. Các tình huống thực tế cần xử lý

### 7.1. Logout và nút Back của trình duyệt

Giả sử người dùng mở `/account`, logout rồi nhấn Back. Nếu phản hồi cá nhân đã bị cache, browser có thể hiển thị bản cũ trong một số luồng điều hướng. Đặt `no-store` cho trang/API cá nhân là tuyến phòng thủ cần thiết, nhưng **HTTP cache khác với bfcache**, và hành vi khôi phục lịch sử tùy trình duyệt, phiên bản và điều kiện. Một số trình duyệt có thể khôi phục trạng thái trang trước mà không fetch ngay.

Ngoài header, ứng dụng nên:
- Làm invalid session, xóa/cập nhật trạng thái xác thực đúng cách khi logout.
- Xóa dữ liệu cá nhân đã giữ trong state của SPA khi logout hoặc đổi tài khoản.
- Khi trang được khôi phục (`pageshow`) hoặc ứng dụng quay về foreground, kiểm tra lại authentication trước khi hiển thị dữ liệu nhạy cảm; không coi `no-store` là cơ chế authorization.
- Không lưu profile/access token vào `localStorage` chỉ để “có cache nhanh” khi không có lý do và threat model phù hợp.

Ví dụ khung JavaScript cho SPA (chỉ minh họa, endpoint `/api/session` phải tồn tại trong ứng dụng):

```javascript
window.addEventListener("pageshow", async (event) => {
  if (!event.persisted) return;

  const response = await fetch("/api/session", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    // Xóa state cá nhân và điều hướng tới trang đăng nhập.
  }
});
```

`fetch(..., { cache: "no-store" })` kiểm soát yêu cầu **do client gửi**; server vẫn phải trả response header và kiểm tra quyền ở mỗi request. Event `pageshow` không bao phủ mọi thay đổi trạng thái phiên trong mọi trình duyệt, vì vậy đây chỉ là một phần của luồng phục hồi.

### 7.2. CDN, reverse proxy và API gateway

Khi có cache trung gian, hãy kiểm tra cùng một response ở **hai vị trí**: trực tiếp từ origin và qua edge/CDN. CDN có thể có cache rules, page rules hoặc policies riêng. Một response cuối cùng xuất hiện với `Cache-Control: no-store` là tín hiệu cần thiết nhưng chưa thay thế cho cấu hình bypass các đường dẫn authentication, account, private API.

Các việc cần xác nhận:
- Các route `/api/me`, `/account`, báo cáo cá nhân và download riêng tư không được cache ở edge.
- Không có rule ghi đè `no-store` thành `public` hoặc đặt TTL cưỡng bức.
- Không tạo cache key bỏ qua cookie/query/user scope rồi phục vụ lẫn dữ liệu các tài khoản.
- `Vary: Cookie` hoặc `Vary: Authorization` có thể giúp mô tả biến thể response, nhưng **không phải biện pháp thay `no-store`** cho dữ liệu nhạy cảm; `Vary: Cookie` còn làm cache key rất phân mảnh.
- Header quan sát được ở origin và edge phải nhất quán với chính sách; nếu có `Age`, `Via`, `X-Cache` hay header trace do CDN cung cấp thì dùng chúng để điều tra, không coi một tên header vendor-specific là chuẩn chung.

Ví dụ lỗi nghiêm trọng: endpoint `/api/me` sử dụng cookie phiên nhưng edge cache mọi `GET` với key chỉ gồm URL. Khi hai người lần lượt truy cập cùng URL, cache có thể tái sử dụng profile của người trước. Sửa ở **origin header + edge bypass**, đồng thời xác nhận server luôn authorize request; không chỉ thêm `Vary` rồi giả định hết rủi ro.

### 7.3. Service Worker và Cache API

Nếu ứng dụng là PWA, Service Worker có thể chủ động đưa response vào Cache API. Logic lập trình này không thể được thay thế bằng việc chỉ xem browser HTTP cache. Cần audit route matching: static assets công khai có thể `cache-first`, còn tài khoản/token/phiếu thanh toán nên `network-only` (và không gọi `cache.put`). Khi logout, xóa các dữ liệu nhạy cảm đã được cache bởi ứng dụng và xóa state phía client nếu cần.

**Không bao giờ** đưa `/api/me` hoặc response chứa thông tin cá nhân vào nhóm “cache tất cả GET” chỉ vì chúng là GET. Phân loại theo nội dung, không theo phương thức đơn thuần.

### 7.4. Tài liệu được tải xuống và phản hồi lỗi

Với hóa đơn PDF, sao kê CSV, kết quả xét nghiệm, tệp xuất quyền truy cập: đặt `Cache-Control: no-store` trên **chính response file**, đồng thời xác thực/authorize đường dẫn download. Dù server đặt `no-store`, người dùng bấm “Save” vẫn có thể lưu tệp ra đĩa; chính sách bảo mật dữ liệu tải về là bài toán khác.

Với 401/403/404/5xx, không mặc định rằng status lỗi đồng nghĩa “không cache”. Trả `no-store` nếu body hoặc redirect chứa dữ liệu nhạy cảm; tránh đưa token, session ID, stack trace và dữ liệu cá nhân vào body/log.

## 8. Kiểm thử và xác minh response headers

### 8.1. Kiểm thử Spring Security Servlet bằng MockMvc

Thêm test dependencies `spring-boot-starter-test` và `spring-security-test`. File `CacheControlTest.java` (trong đúng package test của Spring Boot application):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheControlTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void privateAccountMustNotBeStored() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL, containsString("no-store")));
    }
}
```

Test này cần cấu hình `SecurityConfig` và `AccountController` của mục 6. `@WithMockUser` mô phỏng authentication cho Servlet security filter chain; test kiểm tra **response thật** có `no-store`. Nếu đổi controller để trả `Cache-Control: public`, test sẽ phát hiện sai policy.

Có thể mở rộng thành integration test để kiểm tra asset thật `/assets/app.a1b2c3.js` trả `public`/`max-age` và response `/api/me` không bị CDN/shared cache lưu. Không giả định status/headers chỉ từ annotation controller; phản hồi cuối có thể bị thay đổi bởi servlet filters, gateway và reverse proxy.

### 8.2. Kiểm tra thủ công qua HTTP

Khi có một endpoint đã xác thực hợp lệ, xem response cuối bằng DevTools Network hoặc `curl -i`. Với URL nhạy cảm, truyền cookie/token xác thực qua cách an toàn phù hợp môi trường; **không** đưa credential thật vào ví dụ/ticket/log công khai.

```bash
# Phản hồi không cần đăng nhập của asset công khai có fingerprint:
curl -I http://localhost:8080/assets/app.a1b2c3.js

# Với endpoint cần đăng nhập, dùng phiên hợp lệ;
# -i để xem header + body thay vì chỉ status:
curl -i http://localhost:8080/api/me
```

Lệnh thứ hai khi **chưa** có phiên hợp lệ có thể trả 401, 403 hoặc redirect tùy `AuthenticationEntryPoint`; nó **không** chứng minh cache policy của body thành công `/api/me`. Để kiểm tra nội dung cá nhân, lặp lại bằng phiên đã xác thực rồi xác nhận response 200 có `Cache-Control: no-store`. Với asset, file mẫu phải thực sự tồn tại tại `src/main/resources/static/assets/app.a1b2c3.js` trước khi kỳ vọng status 200.

Header mong đợi khi ứng dụng chạy đúng cấu hình ở mục 6:

```http
# GET /api/me (đã đăng nhập, 200)
Cache-Control: no-store

# GET /assets/app.a1b2c3.js (tệp tồn tại, 200)
Cache-Control: max-age=31536000, public
```

Thứ tự các directive trong header có thể khác; kiểm tra **ý nghĩa và giá trị**, không phụ thuộc thứ tự chuỗi. Trong DevTools, xem `Response Headers`, `Size` / cache indicator và phân biệt “from memory cache”/“from disk cache” với network response. Khi xem nguồn gốc CDN, dùng thêm các chỉ báo của nhà cung cấp về HIT/MISS nếu có, nhưng không coi chúng thay việc kiểm chứng quyền truy cập.

### 8.3. Ma trận kiểm thử an toàn

| Thử nghiệm | Điều cần xác nhận |
| --- | --- |
| GET profile của Alice | `no-store`, body chỉ dữ liệu Alice, 200 khi đã authenticated |
| Logout rồi Back | Không lộ profile từ cache HTTP; UI kiểm tra auth trước khi hiển thị lại |
| Đăng nhập Bob trên cùng máy | Không tái sử dụng nội dung Alice từ UI state/Service Worker/CDN |
| Request không xác thực | Không thấy dữ liệu riêng; lỗi/redirect không lộ token, policy cache phù hợp |
| Asset công khai đã version hóa | `public` và TTL dài; nội dung đúng hash trong URL |
| HTML shell không version hóa | Có revalidation/TTL ngắn; không giữ bản HTML lỗi thời |
| Tệp tải xuống riêng tư | `no-store` và authorization đúng; không phục vụ cho tài khoản khác |
| Đi qua CDN/reverse proxy | Endpoint riêng tư bị bypass; không HIT xuyên người dùng |
| SPA/PWA có Service Worker | Không lưu response cá nhân vào Cache API |

## 9. Các sai lầm thường gặp

1. **Dùng `no-cache` để yêu cầu “không được lưu”.** Chỉ thị này vẫn cho phép lưu; dùng `no-store` khi mục tiêu là không lưu phản hồi nhạy cảm.
2. **Dùng `private` và nghĩ browser sẽ không giữ dữ liệu.** `private` cấm shared cache lưu theo chỉ thị; cache riêng vẫn có thể giữ.
3. **Tin rằng có cookie/session là đủ ngăn CDN.** Không phải mọi shared cache đều suy đoán đúng độ riêng tư; phải cấu hình response và edge rõ ràng.
4. **Đặt `public, max-age=31536000` lên tất cả GET.** Có thể rò rỉ profile/HTML có token, đồng thời làm bản HTML không cập nhật khi deploy.
5. **Tắt toàn bộ `headers()` hoặc bỏ qua security chain chỉ để cache assets.** Có thể làm mất các header bảo mật không liên quan. Chỉ thay cache policy của tập static assets thực sự công khai.
6. **Đặt cache policy ở controller nhưng không xem phản hồi ở edge.** Reverse proxy/CDN có thể ghi đè header hoặc có rule cache riêng.
7. **Cho Service Worker cache mọi GET.** Cache API do ứng dụng điều khiển có thể giữ dữ liệu riêng tư bất chấp các giả định về HTTP cache.
8. **Coi `no-store` là xóa sạch dữ liệu sau logout.** Browser UI state, bfcache, file đã download và các bản sao khác cần cơ chế riêng.
9. **Chỉ kiểm thử status 200, bỏ qua headers và chuyển tài khoản.** Lỗi cache có thể chỉ lộ khi nhiều người dùng chung URL hoặc sau logout/login.
10. **Cấu hình TTL lớn với file tên cố định.** Khi file thay đổi mà URL không đổi, client có thể giữ asset lỗi thời.

## 10. Checklist áp dụng

- [ ] API, trang và file chứa dữ liệu cá nhân/secret phát `Cache-Control: no-store`.
- [ ] Spring Security Servlet bật security headers mặc định cho luồng động; mọi ngoại lệ cache được giới hạn bằng matcher rõ ràng.
- [ ] Asset công khai cache dài chỉ khi có version/hash và không chứa thông tin người dùng.
- [ ] Các endpoint login, logout, đổi mật khẩu và response file nhạy cảm có policy phù hợp.
- [ ] Reverse proxy/CDN không ghi đè `no-store` hoặc cache lẫn người dùng; cache key/bypass được kiểm tra.
- [ ] Service Worker/PWA không giữ dữ liệu cá nhân trong Cache API; logout xóa state thích hợp.
- [ ] Đã kiểm thử response headers với `MockMvc`/DevTools/cURL bằng phiên đã xác thực, gồm kiểm tra sau logout/đổi tài khoản.
- [ ] Hiểu rõ giới hạn của HTTP cache directive với bfcache, file download, ảnh chụp và dữ liệu trong bộ nhớ.

**Ghi nhớ:** `no-store` mới là chỉ thị cốt lõi khi cần tránh lưu nội dung nhạy cảm ở HTTP cache; `no-cache` vẫn cho phép lưu để xác thực lại. Spring Security Servlet cung cấp các header chống cache mặc định, nhưng cache policy cuối cùng phải được kiểm tra trên phản hồi thực, kể cả qua CDN. Tối ưu cache cho asset công khai bằng đường dẫn/version rõ ràng, đồng thời luôn bảo vệ trang/API cá nhân bằng xác thực, phân quyền và policy không lưu.
