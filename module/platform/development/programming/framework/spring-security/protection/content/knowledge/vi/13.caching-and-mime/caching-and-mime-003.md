# Pragma, Expires và tương thích với hệ thống cũ

## Bối cảnh: vì sao một response có ba loại header chống cache?

Trong một hệ thống có đăng nhập, phản hồi HTTP chứa số dư tài khoản hoặc hồ sơ khách hàng có thể đi qua trình duyệt, proxy doanh nghiệp và CDN trước khi người dùng nhìn thấy. Không phải mọi thành phần đều hỗ trợ cùng một thế hệ giao thức và cùng các chỉ thị cache. Do đó, một response do Spring Security bảo vệ thường chứa đồng thời:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

Những dòng này có mục đích **liên quan nhưng không đồng nghĩa**. `Cache-Control` là cơ chế điều khiển cache chính theo HTTP hiện đại; `Pragma` xuất phát từ yêu cầu tương thích ngược trong HTTP/1.0; `Expires` cung cấp thời điểm hết hạn theo lịch. Nếu hiểu chúng như ba cách viết của cùng một lệnh “không lưu” thì rất dễ cấu hình sai, nhất là khi bật cache cho tài nguyên tĩnh hoặc đi qua gateway/CDN.

Bài này nằm trong chương **Bộ nhớ đệm và MIME** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**. Mục tiêu là dùng đúng các header HTTP trong các lớp phòng vệ của Spring Security, áp dụng được với **Servlet** và **Reactive**, đồng thời kiểm thử nguy cơ lộ dữ liệu và chẩn đoán xung đột giữa ứng dụng, trình duyệt và hệ thống trung gian. Đây là phần bảo vệ cache: các cơ chế CSRF, CORS, CSP, HSTS, HTTP firewall và kiểm tra MIME vẫn có mục đích riêng.

Sau khi học, bạn có thể:

- Giải thích nguồn gốc và giới hạn của `Pragma: no-cache`, đặc biệt sự khác biệt giữa **request** và **response**.
- Đọc `Expires` theo HTTP-date, xác định response còn fresh hay đã stale và giải thích `Expires: 0`.
- Xác định thứ tự áp dụng các chỉ thị khi có cả `Cache-Control`, `Expires` và `Pragma`.
- Hiểu vì sao Spring Security vẫn gửi bộ header chống cache tương thích với thành phần cũ.
- Đặt header có chủ đích cho endpoint nhạy cảm và tài nguyên tĩnh ở Spring MVC/WebFlux, rồi kiểm tra trên đường đi thực.

## 1. Lịch sử ngắn của HTTP caching

Ở những phiên bản HTTP cũ, cache thường dựa vào các header như `Date`, `Expires` và `Last-Modified`. Khi HTTP/1.1 bổ sung `Cache-Control`, ứng dụng có thể diễn đạt chính xác hơn việc **có được lưu response không**, **được lưu ở cache nào**, **bao lâu còn tươi** và **khi nào phải xác thực lại với máy chủ**.

Trong thực tế, một proxy cũ có thể hiểu `Expires` nhưng bỏ qua một số directive mới của `Cache-Control`. Một ứng dụng bảo vệ dữ liệu nhạy cảm vì thế có thể phát cả header hiện đại lẫn header mang tính tương thích. Tuy nhiên, **header tương thích không biến thành phần lỗi thời thành an toàn tuyệt đối**: nếu proxy bỏ qua tất cả chính sách cần thiết, phải sửa cấu hình mạng hoặc tránh cho proxy cache nội dung đó.

| Header | Xuất hiện ở đâu? | Ý nghĩa cốt lõi | Lưu ý về tương thích |
| --- | --- | --- | --- |
| `Cache-Control` | Request và response | Điều khiển lưu, dùng lại, freshness, revalidation; các directive có ngữ nghĩa tùy chiều truyền | Cơ chế ưu tiên trên HTTP hiện đại |
| `Pragma: no-cache` | **Request** có ngữ nghĩa chuẩn; response chỉ là thực hành lịch sử | Trong request, yêu cầu cache xác thực lại trước khi dùng bản lưu | Tồn tại cho cache HTTP/1.0; **không phải** lệnh response chuẩn để cấm lưu |
| `Expires` | Response | Thời điểm tuyệt đối mà response được xem là hết độ tươi | Hữu ích với cache cũ; **không** cấm lưu body |
| `Date` | Response | Thời điểm origin tạo message | Giúp tính freshness với `Expires` và `Age` |
| `Age` | Response do cache gửi (khi áp dụng) | Ước lượng thời gian response đã tồn tại từ lúc được tạo hoặc xác thực tại origin | Giúp đánh giá độ tuổi của bản lưu ở proxy/CDN |

Các khái niệm **fresh** (bản lưu còn thời gian dùng được), **stale** (đã hết độ tươi) và **revalidation** (hỏi origin xem bản lưu có còn hợp lệ) phải được phân biệt với việc **xác thực danh tính** của người dùng. Một cache có thể có bản lưu hợp lệ về nội dung nhưng người dùng hiện tại đã mất quyền xem.

## 2. `Pragma: no-cache`: giá trị chuẩn nằm ở request

### 2.1. Cách hoạt động của request Pragma

HTTP/1.0 không có `Cache-Control` như HTTP/1.1. Để một client tương tác với các proxy cache cũ, HTTP quy định:

```http
GET /reports/summary HTTP/1.0
Pragma: no-cache
```

Theo RFC 9111, request `Pragma: no-cache` được xử lý tương đương yêu cầu `Cache-Control: no-cache` **khi request không có `Cache-Control`**. Điều đó có nghĩa cache **không được sử dụng bản lưu để đáp ứng request đó trước khi xác thực lại thành công** với origin. Nó **không có nghĩa cache không được lưu** request hoặc response.

Client hiện đại thường có thể gửi:

```http
GET /reports/summary HTTP/1.1
Cache-Control: no-cache
```

Cách này diễn đạt trực tiếp mong muốn revalidate. Khi phải đi qua hệ thống cũ, một số client còn gửi đồng thời hai dòng:

```http
Cache-Control: no-cache
Pragma: no-cache
```

Không nên cho rằng chỉ thêm `Pragma` sẽ luôn buộc proxy cũ hoặc CDN bỏ qua cache. Bất kỳ thành phần không tuân thủ HTTP nào cũng cần được kiểm tra trên đường mạng thực tế.

### 2.2. `Pragma` trong response: có thể gặp, nhưng không được chuẩn hóa

Ví dụ Spring Security thường trả:

```http
HTTP/1.1 200 OK
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

`Pragma: no-cache` ở **response** là thực hành tương thích đã được triển khai rộng rãi. Tuy nhiên, RFC 9111 chỉ định ngữ nghĩa chuẩn cho `Pragma` **trong request**; ý nghĩa response `Pragma: no-cache` **không được định nghĩa để thay thế response `Cache-Control`**.

Vì vậy:

- **Không sử dụng chỉ `Pragma: no-cache`** để bảo vệ dữ liệu cá nhân hoặc bí mật.
- Nếu mục tiêu là ngăn HTTP cache lưu response, header chính phải là `Cache-Control: no-store`.
- Nếu mục tiêu là được lưu nhưng luôn phải hỏi origin trước khi dùng lại, dùng `Cache-Control: no-cache`; với dữ liệu theo người dùng có thể thêm `private` để cấm cache dùng chung lưu.
- Không suy luận một browser đã “không lưu” chỉ vì trong response có `Pragma`.

Cũng không nhầm `Pragma: no-cache` với `Clear-Site-Data` hay thao tác xóa bộ nhớ ứng dụng: nó **không dọn dữ liệu đã tồn tại trên thiết bị**.

## 3. `Expires`: thời điểm hết độ tươi theo lịch

`Expires` là header response có giá trị **thời gian tuyệt đối**, dùng định dạng HTTP-date. Một response ví dụ:

```http
HTTP/1.1 200 OK
Date: Thu, 26 Nov 2026 04:00:00 GMT
Expires: Thu, 26 Nov 2026 04:05:00 GMT
Content-Type: text/css
```

Khi không có chỉ thị freshness tương ứng ưu tiên hơn, cache có thể suy ra thời hạn tươi danh nghĩa là khoảng **5 phút** kể từ thời điểm response được tạo. Khi phản hồi đi qua proxy, các yếu tố như `Age` và thời gian truyền ảnh hưởng đến độ tươi còn lại; không đơn giản lấy đồng hồ người dùng trừ `Expires`.

Đây là công cụ cache hiệu năng: **`Expires` tương lai cho phép giữ response**, nên không phù hợp để vô tư dùng cho nội dung tài khoản.

### 3.1. Định dạng ngày hợp lệ

Ví dụ ngày theo dạng IMF-fixdate, dùng `GMT`:

```http
Expires: Thu, 26 Nov 2026 04:05:00 GMT
```

Hãy tránh gửi chuỗi theo định dạng địa phương như `26/11/2026 11:05` hoặc Unix timestamp số nguyên dưới dạng `Expires`: chúng không phải HTTP-date hợp lệ.

### 3.2. `Expires: 0` nghĩa là gì?

Spring Security thường dùng:

```http
Expires: 0
```

`0` **không phải một HTTP-date hợp lệ**. Theo quy tắc HTTP caching, cache phải coi giá trị ngày không hợp lệ (đặc biệt `0`) là **một thời điểm trong quá khứ**, tức phản hồi đã stale.

Hai hệ quả quan trọng:

1. `Expires: 0` **không cấm lưu response**; nó chỉ góp phần khiến cache phải xử lý response như đã hết độ tươi.
2. Nếu mục tiêu là **không lưu** body nhạy cảm, `Cache-Control: no-store` mới là directive cần có.

Một số ứng dụng sử dụng ngày quá khứ hợp lệ thay vì `0`:

```http
Expires: Wed, 21 Oct 2015 07:28:00 GMT
```

Nó cũng thể hiện thời điểm đã qua. Tuy vậy, với HTTP hiện đại, **nên dùng `Cache-Control` để thể hiện chính sách chính**, thay vì chỉ dựa vào `Expires`.

### 3.3. `Date` và `Age` ảnh hưởng thế nào?

Giả sử response từ origin:

```http
Date: Thu, 26 Nov 2026 04:00:00 GMT
Expires: Thu, 26 Nov 2026 04:10:00 GMT
```

Bản gốc có thời hạn tươi khoảng 10 phút. Nếu CDN trả lại với `Age: 360`, nó cho biết ước lượng tuổi của response đã đạt khoảng 6 phút. Vì vậy thời gian tươi **còn lại** có thể chỉ còn khoảng 4 phút, không phải 10 phút từ lúc browser vừa nhận.

Trong thực hành, các thuật toán xác định response age/freshness còn xét độ trễ mạng, `Date`, tuổi hiệu chỉnh và chỉ thị cache khác. Đừng dùng một phép trừ đơn giản để thay thế đánh giá theo RFC 9111.

## 4. Quy tắc ưu tiên khi nhiều header xuất hiện cùng lúc

HTTP caching không hoạt động theo kiểu “header nào đứng sau thì thắng”. Cache tuân thủ chuẩn diễn giải ý nghĩa từng chỉ thị theo RFC.

| Response mẫu | Cache hiện đại được hiểu như thế nào? |
| --- | --- |
| `Cache-Control: no-store` + `Expires` tương lai | `no-store` cấm HTTP cache lưu; ngày tương lai không mở lại quyền lưu. |
| `Cache-Control: no-cache` + `Expires` tương lai | Có thể lưu, nhưng mỗi lần dùng lại phải xác thực thành công; không được dùng “còn tươi” để bỏ revalidation. |
| `Cache-Control: max-age=60` + `Expires` tương lai hơn nhiều | Với cache hiểu HTTP/1.1+, `max-age` xác định freshness và **ưu tiên** hơn `Expires`. |
| `Cache-Control: s-maxage=30` + `Expires` tương lai | Với shared cache, `s-maxage` có quyền ưu tiên tương ứng khi tính freshness. |
| Chỉ `Expires` tương lai | Cache có thể dùng ngày đó làm thời điểm hết tươi nếu response đủ điều kiện lưu. |
| Chỉ `Expires: 0` | Được xem đã stale; không đồng nghĩa cấm lưu. |
| Chỉ `Pragma: no-cache` trong response | Không có ngữ nghĩa response chuẩn đủ để khẳng định cấm lưu hoặc luôn revalidate. |

**Ưu tiên cụ thể:** Khi response có `Cache-Control` với directive `max-age` hoặc `s-maxage` thích hợp, RFC 9111 yêu cầu cache bỏ qua `Expires` để xác định thời gian tươi. Với `no-store` và `no-cache`, các ràng buộc **không lưu** hoặc **phải revalidate trước khi dùng lại** vẫn chi phối hành vi, bất kể `Expires` cho biết thời điểm nào.

Không phát header mâu thuẫn rồi hy vọng cache “chọn cái an toàn hơn”. Ví dụ:

```http
Cache-Control: public, max-age=3600
Cache-Control: no-store
```

Các lớp proxy hoặc thư viện có thể hợp nhất trường, diễn giải hoặc ghi đè khác nhau; hai chính sách này không nên được cấu hình đồng thời. Hãy để **một tầng sở hữu chính sách cuối cùng** cho mỗi nhóm response, rồi kiểm tra header ở origin và edge. Với hai trường `Cache-Control` có cùng directive freshness khác giá trị, một số tổ hợp trở thành không hợp lệ và cache phải xử lý theo quy tắc tương ứng, không tùy tiện chọn tuổi lớn nhất.

## 5. Bộ header mặc định của Spring Security

Khi **security headers mặc định** được bật trong ứng dụng Servlet hoặc Reactive, Spring Security cung cấp các header chống cache:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

Ý nghĩa của từng phần:

| Phần | Tại sao có? |
| --- | --- |
| `no-store` | Ngăn HTTP cache tuân thủ chuẩn lưu phản hồi nhạy cảm. |
| `no-cache` | Nếu có bản lưu hợp lệ theo điều kiện khác, yêu cầu revalidate trước khi dùng lại; ở đây đi cùng `no-store` để tăng tính phòng vệ/tương thích. |
| `max-age=0` | Không cấp khoảng freshness dương. |
| `must-revalidate` | Với bản lưu stale, ràng buộc việc phải xác thực lại thành công trước khi dùng; không thay `no-store`. |
| `Pragma: no-cache` | Hỗ trợ tương thích với cách triển khai cache/trình duyệt cũ. |
| `Expires: 0` | Diễn đạt response đã hết độ tươi, hỗ trợ các cache cũ quan tâm `Expires`. |

Spring Security không mặc nhiên ghi đè một chính sách cache đã được ứng dụng chủ động đặt. Vì thế, một controller trả `Cache-Control: public` hoặc một gateway thêm cache header có thể làm thay đổi kết quả cuối cùng. Khi không rõ thứ tự áp dụng, hãy **đo response cuối**, thay vì chỉ nhìn cấu hình filter chain.

Điều quan trọng: **việc có cả ba header không bảo đảm chống mọi cache bị cấu hình sai**. Cookie, bearer token, `Vary`, CORS và HTTP security headers không thay thế việc vô hiệu cache dùng chung cho endpoint cá nhân hóa.

### Có nên tắt cache headers mặc định?

Thông thường **giữ mặc định** và đặt chính sách riêng cho tài nguyên công khai nếu cần. API tắt riêng cache header writer tồn tại ở hai DSL:

```java
// Servlet: cấu hình HttpSecurity
http.headers(headers -> headers
    .cacheControl(cache -> cache.disable())
);

// WebFlux: cấu hình ServerHttpSecurity
http.headers(headers -> headers
    .cache(cache -> cache.disable())
);
```

Đây là ví dụ để nhận diện cấu hình, **không phải khuyến nghị tắt**. Khi chủ động tắt, ứng dụng phải tự quản lý header thích hợp cho response thành công, lỗi, redirect, HTML và các nhánh xử lý khác; đừng mặc nhiên cho rằng controller nào cũng được chạy trước khi response trả về.

## 6. Cấu hình rõ ràng trong Spring MVC (Servlet)

Ví dụ một API thông tin tài khoản cần chống lưu ở cả cache hiện đại lẫn các hệ thống cũ còn đọc `Pragma`/`Expires`.

### 6.1. Bảo vệ endpoint trước khi tạo response

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/account/**").authenticated()
            .anyRequest().permitAll());
        // Giữ nguyên security headers mặc định của Spring Security.
        return http.build();
    }
}
```

Authentication và authorization là lớp kiểm soát **ai được xem dữ liệu**. Header cache điều khiển **nơi nào có thể giữ và phát lại response**. Hai lớp bảo vệ bổ trợ nhau.

### 6.2. Chủ động phát bộ header cho dữ liệu nhạy cảm

```java
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountServletController {

    @GetMapping("/api/account/me")
    ResponseEntity<Map<String, String>> me(Authentication authentication) {
        return ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL,
                "no-cache, no-store, max-age=0, must-revalidate")
            .header(HttpHeaders.PRAGMA, "no-cache")
            .header(HttpHeaders.EXPIRES, "0")
            .body(Map.of("user", authentication.getName()));
    }
}
```

Bộ header trên được viết rõ để minh họa cách giữ khả năng tương thích, nhưng **nếu không có yêu cầu riêng**, các security headers mặc định của Spring Security thường đã đáp ứng mục tiêu này. Không cần lặp lại chúng ở từng controller nếu filter chain đang áp dụng chính sách phù hợp và không có tầng nào ghi đè.

Với nhiều endpoint, cách an toàn hơn là có một chính sách chung tại tầng đáp ứng nhất quán cho nội dung nhạy cảm, đồng thời kiểm thử cả response lỗi. Nếu dùng một filter riêng, phải cẩn thận thứ tự trước/sau security filter, việc response đã commit và khả năng trùng lặp header.

### 6.3. Tài nguyên công khai: dùng `Cache-Control` và `Expires` nhất quán

Ví dụ CSS/JS có tên file chứa hash (như `main.f4c2d8.js`) có thể có cache dài hạn:

```http
HTTP/1.1 200 OK
Date: Thu, 26 Nov 2026 04:00:00 GMT
Cache-Control: public, max-age=31536000
Expires: Fri, 26 Nov 2027 04:00:00 GMT
Content-Type: application/javascript
```

Đây là **ví dụ minh họa một năm**, không phải header sinh tự động. Nếu phát `Expires` để tương thích cache cũ, hãy cho thời gian tương ứng với `max-age` ở cùng mốc. Không gửi `Pragma: no-cache` cho asset muốn cache lâu, vì các hệ thống cũ có thể diễn giải không thống nhất.

Với Spring MVC, cấu hình cache cho resource handler có thể như sau:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class PublicAssetConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(Duration.ofDays(365)).cachePublic());
    }
}
```

`setCacheControl` thiết lập chính sách HTTP hiện đại. Đoạn code **không tự cam kết tạo `Expires`**; nếu kiến trúc thực sự cần header này cho cache cũ, cấu hình thêm ở tầng resource response hoặc gateway theo cách bảo đảm thời hạn nhất quán. Chỉ áp dụng cache dài hạn cho asset bất biến, cập nhật bằng đường dẫn hoặc tên file mới.

## 7. Áp dụng trong Spring WebFlux (Reactive)

WebFlux dùng cùng HTTP headers. Ví dụ với `ServerHttpSecurity` và annotated controller:

```java
import java.security.Principal;
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain reactiveFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(auth -> auth
                .pathMatchers("/api/account/**").authenticated()
                .anyExchange().permitAll())
            .build();
    }
}

@RestController
class AccountReactiveController {

    @GetMapping("/api/account/me")
    Mono<ResponseEntity<Map<String, String>>> me(Mono<Principal> principal) {
        return principal.map(p -> ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL,
                "no-cache, no-store, max-age=0, must-revalidate")
            .header(HttpHeaders.PRAGMA, "no-cache")
            .header(HttpHeaders.EXPIRES, "0")
            .body(Map.of("user", p.getName())));
    }
}
```

Đây là **phương án thay thế** ví dụ Servlet, không đăng ký đồng thời cả hai controller trên cùng một đường dẫn. `Mono` không làm thay đổi ý nghĩa của `Cache-Control`, `Pragma` hay `Expires`.

Khi sử dụng functional endpoints, header có thể đặt trên `ServerResponse`. Khi viết trực tiếp vào `ServerHttpResponse`, phải đặt header **trước khi response được commit**. Dù dùng cách nào, quyền truy cập phải được xử lý trước khi tạo response nhạy cảm.

## 8. Tương thích hệ thống cũ: nhận biết chính xác giới hạn

### 8.1. Ma trận client/cache

| Thành phần | Chủ yếu hiểu gì? | Hướng triển khai |
| --- | --- | --- |
| Browser và proxy hỗ trợ HTTP/1.1 hiện đại | `Cache-Control`; validator, freshness và `Expires` khi phù hợp | Dùng `Cache-Control` làm chính sách chính; kiểm thử browser thật. |
| Proxy/cache đời cũ chỉ hiểu `Expires` | Thời điểm hết độ tươi | Phát `Expires` quá khứ/`0` để tránh response còn fresh, nhưng **không dựa vào nó để cấm lưu**. |
| Client HTTP/1.0 cần yêu cầu revalidation | `Pragma: no-cache` ở **request** | Gửi request directive tương thích khi thật sự cần hỗ trợ hệ thống cũ. |
| Cache xử lý `Pragma` ở response theo hành vi lịch sử | Khả năng không nhất quán, ngoài ngữ nghĩa response chuẩn | Giữ `Pragma` như phụ trợ; chính sách dựa vào `Cache-Control` và cấu hình cache. |
| CDN/gateway có quy tắc ép cache riêng | Có thể ghi đè/loại bỏ headers hoặc bắt cache theo URL | Cấu hình bypass cho endpoint nhạy cảm; đối chiếu response origin với response edge. |
| Cache nội bộ ứng dụng, Redis, PWA `CacheStorage` | Quy tắc lưu do ứng dụng viết | Kiểm soát riêng bằng khóa cache, vòng đời dữ liệu, phân quyền và xử lý logout. |

### 8.2. `Vary` và `Cookie` không phải phương án bảo vệ thay thế

Giả sử cùng URL:

```http
GET /api/account/me HTTP/1.1
Cookie: SESSION=alice
```

và

```http
GET /api/account/me HTTP/1.1
Cookie: SESSION=bob
```

có hai body khác nhau. Dù ứng dụng trả `Vary: Cookie`, điều đó chỉ hướng dẫn cache chọn biến thể theo request header, **không đảm bảo mọi proxy tuân thủ, không cấm lưu trên browser và không thực thi phân quyền**. Với dữ liệu nhạy cảm, `Cache-Control: no-store` và chính sách bypass tại CDN vẫn là lựa chọn phù hợp.

Yêu cầu có `Authorization` chịu quy tắc lưu riêng ở shared cache theo RFC 9111. Tuy vậy, một số directive response như `public`, `s-maxage` hoặc `must-revalidate` có thể mở ngoại lệ cho shared cache nếu đáp ứng điều kiện tương ứng. Đừng cho rằng việc có bearer token luôn loại bỏ toàn bộ rủi ro cache; không phát chính sách công khai cho response theo tài khoản.

### 8.3. Không nhầm những lớp bảo vệ khác

- **CORS** quy định việc JavaScript ở origin khác có được đọc response hay không; nó không ngăn một proxy phát sai response giữa hai người dùng.
- **CSRF** bảo vệ những thao tác dựa vào credential trình duyệt; không phải chính sách lưu response.
- **CSP, HSTS và `X-Content-Type-Options: nosniff`** giúp giảm rủi ro script injection, kết nối không an toàn hoặc MIME sniffing; chúng không thay `Cache-Control`.
- **Security headers** vẫn cần đi cùng xác thực, phân quyền, session invalidation và bảo vệ tại reverse proxy/gateway.

## 9. Kiểm thử bằng HTTP và Spring Security

### 9.1. Quan sát response từ origin và từ CDN

Với credential của **môi trường thử nghiệm**, gọi endpoint nhạy cảm:

```bash
curl -sS -i \
  -H 'Authorization: Bearer <test-token>' \
  'https://app.example.com/api/account/me'
```

Kiểm tra có các header chính sách mong đợi; trong bài này, ví dụ trả đầy đủ `Cache-Control`, `Pragma` và `Expires`. Không dùng token thật trong báo cáo/log công khai.

Kiểm tra cách server xử lý **request** yêu cầu revalidation:

```bash
curl -sS -i \
  -H 'Cache-Control: no-cache' \
  -H 'Pragma: no-cache' \
  'https://app.example.com/assets/catalog.json'
```

`curl` ở đây chỉ gửi các header; nó **không tự mô phỏng** thuật toán của browser cache. Nếu muốn khảo sát HTTP/1.0, `curl --http1.0` có thể thay đổi phiên bản request nhưng **không mô phỏng được proxy HTTP/1.0**. Cần kiểm thử thật với hệ thống trung gian mà sản phẩm hỗ trợ.

### 9.2. Kiểm thử tích hợp Servlet bằng MockMvc

Ví dụ này dùng `spring-security-test` và MockMvc đã được cấu hình cùng Spring Security; nó kiểm tra **header ở lớp ứng dụng**:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

class AccountHeaderAssertions {
    MockMvc mvc; // Khởi tạo với WebApplicationContext và springSecurity()

    @Test
    void personalResponseHasLegacyAndModernHeaders() throws Exception {
        mvc.perform(get("/api/account/me").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(header().string(HttpHeaders.PRAGMA, "no-cache"))
            .andExpect(header().string(HttpHeaders.EXPIRES, "0"));
    }
}
```

Đây là **trích đoạn kiểm thử**: trong dự án thật cần khởi tạo MockMvc với `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build()` hoặc bộ test tương đương; không thể chạy lớp này nguyên trạng khi biến `mvc` chưa được khởi tạo.

### 9.3. Kiểm thử Reactive bằng WebTestClient

`WebTestClient` đã bind application context và áp dụng Spring Security test support có thể kiểm tra tương tự:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

// client đã tạo từ WebTestClient.bindToApplicationContext(context)
//          .apply(springSecurity()).configureClient().build()
client.mutateWith(mockUser("alice"))
    .get().uri("/api/account/me")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches("Cache-Control", ".*no-store.*")
    .expectHeader().valueEquals("Pragma", "no-cache")
    .expectHeader().valueEquals("Expires", "0");
```

Đây cũng là **trích đoạn test**. Cần các dependency `spring-test`, `spring-security-test` và setup ứng dụng WebFlux tương ứng. Các kiểm thử này không chứng minh một CDN bên ngoài đã tuân thủ header.

### 9.4. Thử kịch bản rò rỉ qua cache dùng chung

Thiết kế thử nghiệm với hai tài khoản có response khác nhau:

1. Alice đăng nhập, gọi `GET /api/account/me` qua CDN và xác nhận body chứa dữ liệu Alice.
2. Bob đăng nhập riêng, gọi **cùng URL** qua cùng CDN; body chỉ được chứa dữ liệu Bob.
3. Đăng xuất Alice, lặp lại request cũ không có credential hoặc với session hết hiệu lực; server phải xử lý như người chưa đăng nhập, không trả lại body cũ từ cache.
4. Thử điều hướng Back/Forward, refresh, tab khác và service worker (nếu có). Kiểm tra cả state client; header HTTP một mình không đảm bảo xóa toàn bộ bản sao cũ.
5. So sánh `Cache-Control`, `Expires`, `Pragma`, `Age`, `Via` hoặc `X-Cache` (nếu hạ tầng cung cấp) tại origin và edge.

Nếu response cá nhân hóa bị phát lại giữa tài khoản, cần khắc phục cache key/bypass và xử lý các bản lưu bị ảnh hưởng; đây không chỉ là lỗi hiển thị.

## 10. Chẩn đoán xung đột trong triển khai

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra và xử lý |
| --- | --- | --- |
| Có `Pragma: no-cache` mà trình duyệt vẫn lưu response | Response `Pragma` không có nghĩa “cấm lưu” theo chuẩn | Thêm chính sách `Cache-Control: no-store` cho dữ liệu nhạy cảm. |
| Có `Expires: 0` mà vẫn thấy phản hồi được giữ | `Expires: 0` khiến stale, không cấm store | Dùng `no-store`; xác nhận proxy/CDN tuân thủ. |
| `Expires` nằm trong tương lai nhưng trình duyệt revalidate sớm | `Cache-Control: no-cache` hoặc `max-age` ngắn hơn chi phối | Đọc toàn bộ response, kể cả `Age` và `Cache-Control`. |
| `max-age` khác `Expires` | Tầng ứng dụng và gateway đặt thời hạn không khớp | Đồng bộ chính sách; với cache hiện đại, `max-age` ưu tiên khi tính freshness. |
| Controller trả `no-store`, CDN trả `public, max-age=600` | Gateway/CDN ghi đè hoặc ép cache | Sửa edge rules, loại route cá nhân hóa khỏi cache, đo lại sau sửa. |
| JavaScript/css bị tải lại liên tục sau khi bật Spring Security | Cache headers mặc định cũng tác động lên tài nguyên tĩnh | Cache dài hạn riêng cho asset có hash, tránh áp dụng chính sách đó cho HTML/API riêng. |
| Trang đã logout vẫn xuất hiện khi Back | Bản cũ, bfcache, state SPA hoặc service worker | Đảm bảo logout server, dọn state nhạy cảm, kiểm thử từng trình duyệt. |
| Chỉ request HTTP/1.0 có hành vi khác | Cache trung gian thiếu hỗ trợ directive mới, hoặc request/response header bị biến đổi | Kiểm tra theo đường thực tế; đừng xem `curl --http1.0` là đủ để tái hiện proxy cũ. |
| Response có nhiều dòng `Cache-Control` mâu thuẫn | Nhiều filter hoặc gateway cùng sở hữu chính sách | Gỡ trùng lặp, xác lập một nơi chịu trách nhiệm chính và kiểm tra response cuối. |

**Kỹ thuật khoanh vùng:** so sánh response trực tiếp từ origin với response sau proxy/CDN cùng request/danh tính thử nghiệm. Ghi lại status, `Date`, `Age`, `Cache-Control`, `Expires`, `Pragma`, `Vary`, `ETag` và các header liên quan. Sau đó xác định lớp nào thêm/bỏ/ghi đè header. Đừng ghi token hoặc cookie thật vào tài liệu điều tra.

## 11. Bài thực hành: phân biệt tương thích ngược và bảo mật

Một hệ thống quản trị chạy Spring Security có ba đường dẫn:

- `GET /api/payroll/me` chứa lương của người đang đăng nhập.
- `GET /api/settings/theme` chứa tùy chọn giao diện cá nhân, cho phép browser lưu nếu luôn revalidate.
- `GET /assets/site.a18d3f.css` là CSS công khai có hash nội dung.

Reverse proxy cũ có thể chỉ quan tâm `Expires`, còn CDN mới hiểu `Cache-Control`.

**Yêu cầu:**

1. Đặt response policy cho ba đường dẫn. Chỉ ra lúc nào nên phát thêm `Pragma`/`Expires`.
2. Giải thích vì sao `Expires: 0` hoặc chỉ `Pragma: no-cache` không đủ để ngăn lưu dữ liệu lương.
3. Nếu `/api/settings/theme` trả `Cache-Control: private, no-cache` và ETag, mô tả cách browser tái xác thực và điều kiện để origin trả `304`.
4. Nếu CDN ép `public, max-age=600` cho mọi GET, chỉ ra hậu quả có thể xảy ra với endpoint cá nhân và cách xác minh đã sửa.
5. Khi một proxy HTTP/1.0 không hiểu `Cache-Control`, giải thích vì sao không thể chỉ dựa vào việc thêm `Expires` để bảo đảm toàn bộ môi trường an toàn.

**Định hướng đáp án:** Đường lương dùng `Cache-Control: no-store`, có thể đi cùng `Pragma: no-cache`/`Expires: 0` để hỗ trợ hệ thống cũ; đường theme có thể dùng `private, no-cache` nếu chấp nhận lưu cục bộ và luôn phân quyền trước khi trả `304`; CSS hash dùng `public` với `max-age` dài, có thể phát `Expires` tương ứng khi cần. CDN phải bypass các route cá nhân hóa; thử hai người dùng qua cùng URL để bảo đảm không tái sử dụng body sai. Với proxy lỗi thời không tôn trọng chính sách cần thiết, biện pháp là thay đổi cấu hình/đường đi hoặc không cho cache tài nguyên nhạy cảm, thay vì tin một header cũ có thể ngăn mọi rò rỉ.

## Tài liệu tham khảo

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): `Pragma`, `Expires`, `Cache-Control`, freshness và revalidation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): định dạng ngày HTTP, `Date`, validator và phản hồi `304`.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): bộ header bảo vệ mặc định.
- [Spring Security — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cấu hình security headers cho Servlet.
- [Spring Security — Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): cấu hình security headers cho WebFlux.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): cấu hình HTTP caching trong MVC.
