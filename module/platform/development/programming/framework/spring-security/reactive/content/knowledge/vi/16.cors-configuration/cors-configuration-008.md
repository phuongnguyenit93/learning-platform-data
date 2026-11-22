# Phân biệt lỗi CORS tại trình duyệt với lỗi 401 hoặc 403 của máy chủ

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Cấu hình CORS  
> **Trọng tâm:** Phân biệt ba tình huống rất khác nhau: **trình duyệt chặn quyền đọc phản hồi do CORS**, **máy chủ trả 401 do chưa xác thực**, và **máy chủ trả 403 do không đủ quyền, CSRF hoặc chính CORS filter từ chối**. Tự chẩn đoán bằng DevTools, `fetch()`, `curl` và test Spring Security WebFlux Java 17+.

## 1. Câu hỏi cốt lõi: tại sao Console báo CORS dù Network có 401?

Giả sử frontend chạy tại `http://localhost:5173`, gọi API Spring WebFlux tại `http://localhost:8080/api/profile`:

```javascript
const response = await fetch("http://localhost:8080/api/profile", {
  credentials: "include"
});
console.log(response.status);
```

Nếu server trả `HTTP/1.1 401 Unauthorized` **nhưng phản hồi không có CORS headers phù hợp**, trình duyệt có thể **không cho JavaScript đọc được response**. Thay vì chạy `console.log(401)`, promise của `fetch` có thể bị reject với `TypeError: Failed to fetch` hoặc thông điệp tương đương; Console hiển thị lỗi CORS. Tab **Network** đôi khi vẫn hiển thị status HTTP do server trả. Cả hai hiện tượng có thể xảy ra **trên cùng một request**.

Ngược lại, nếu server trả:

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
WWW-Authenticate: Basic realm="example"
```

và các điều kiện CORS khác đều thỏa, JavaScript **nhận được đối tượng `Response` với `status === 401`**. Khi đó đây là **HTTP authentication error**, không phải lỗi CORS browser. `fetch()` mặc định **không tự reject** khi server phản hồi 401 hoặc 403; nó resolve một `Response` có `ok === false`. Chỉ lỗi mạng, chặn CORS, TLS và một số lỗi thuộc tầng fetch mới khiến promise reject.

**Ba kết luận phải thuộc lòng:**

1. **CORS là chính sách truy cập phản hồi của browser**, không phải kiểm tra username, password hay role trong Spring Security.
2. **401/403 là HTTP status do server hoặc một thành phần trung gian trả**; JavaScript có đọc được status đó hay không còn phụ thuộc CORS.
3. **Một response 401/403 thiếu CORS headers có thể bị browser “che” dưới dạng CORS error**. Sửa Authentication/Authorization khác với sửa CORS; đôi khi phải sửa **cả hai**.

### Mục tiêu học tập

Bạn sẽ có khả năng:

- Nhận diện `fetch` bị reject do CORS/network so với `fetch` resolve status 401/403.
- Xác định đúng preflight `OPTIONS`, actual request, `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
- Phân biệt cấu hình CORS fail, authentication fail, authorization fail và CSRF fail.
- Cấu hình `ServerHttpSecurity.cors(...)` cùng `CorsConfigurationSource` đúng cho **Spring WebFlux reactive**.
- Kiểm thử CORS trên cả phản hồi thành công **và lỗi 401/403**, không chỉ test GET trả 200.
- Dùng DevTools/Console/Network và `curl -i` để điều tra theo luồng request.
- Hiểu giới hạn của CORS: `curl` không thực thi chính sách CORS, CORS không thay thế CSRF, không bảo vệ API khỏi non-browser clients.

## 2. Origin là gì? Tại sao chỉ khác port cũng là CORS?

Một **origin** gồm ba phần: **scheme + host + port**. Hai URL cùng origin chỉ khi cả ba phần tương ứng giống nhau.

| Frontend origin | API origin | Cùng origin? | Vì sao? |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:5173` | Có | Cùng scheme, host và port |
| `http://localhost:5173` | `http://localhost:8080` | **Không** | Port khác |
| `https://app.example.test` | `https://api.example.test` | **Không** | Host khác |
| `https://example.test` | `http://example.test` | **Không** | Scheme khác |
| `http://127.0.0.1:5173` | `http://localhost:5173` | **Không** | Host khác |
| `https://app.example.test` | `https://app.example.test:443` | Có | Port mặc định HTTPS là 443 |

CORS thường tác động tới những request cross-origin do script trong browser tạo, ví dụ `fetch` hoặc `XMLHttpRequest`. CORS **không** áp dụng giống vậy cho `curl`, Java HTTP client hay một service backend gọi trực tiếp sang backend khác. Cùng-site/cross-site (liên quan SameSite cookie) là khái niệm **khác** với same-origin/cross-origin; hai port localhost khác nhau là cross-origin, dù có thể được coi là same-site trong một số cơ chế cookie.

### 2.1. Origin request header

Với một request browser cross-origin:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
```

Browser báo origin của trang gọi API. Server xem origin này có nằm trong danh sách tin cậy không và quyết định có thêm CORS response headers. Một `Origin` header **không phải bằng chứng authentication**: non-browser HTTP clients như curl có thể tự tạo `Origin`, nên không dùng Origin như tên user, secret hay phương án bảo vệ API thay cho authentication.

### 2.2. Không nhầm Access-Control-Allow-Origin với URL đích

```http
Access-Control-Allow-Origin: http://localhost:5173
```

Đây là **response header** do server trả, chỉ định origin của client được phép đọc phản hồi. Nó **không phải** URL API đích `http://localhost:8080`. Nếu server trả `Access-Control-Allow-Origin: http://localhost:3000` nhưng trang chạy trên `:5173`, browser vẫn chặn vì không khớp origin.

Khi cần gửi credentials cross-origin, không thể dùng `Access-Control-Allow-Origin: *` cho credentialed request. Server phải trả **origin cụ thể** và `Access-Control-Allow-Credentials: true`, đồng thời browser phải được cấu hình gửi credentials phù hợp.

## 3. Phân loại chính xác các kết quả

Một request frontend có thể dẫn đến **ít nhất năm kiểu kết quả**:

| Tình huống | Điều browser thấy | Điều JavaScript thấy | Chẩn đoán |
| --- | --- | --- | --- |
| Server trả **200** và CORS hợp lệ | Network 200 | `Response(status=200, ok=true)` | Thành công |
| Server trả **401** và CORS hợp lệ | Network 401 | `Response(status=401, ok=false)` | Thiếu/sai authentication |
| Server trả **403** và CORS hợp lệ | Network 403 | `Response(status=403, ok=false)` | Thiếu quyền/CSRF/chính sách server |
| Server trả **401/403/200** nhưng CORS headers sai | Network có thể hiện status | `fetch` **reject**, script không đọc status/body | Browser chặn vì CORS, nhưng server **cũng có thể** đã trả status thực |
| DNS/TLS/mixed content/timeout khiến không có response HTTP hợp lệ | Network failed / canceled | `fetch` **reject** | Lỗi mạng/protocol, không tự kết luận là cấu hình CORS |

Có thêm trường hợp **preflight fail**: browser gửi `OPTIONS` trước, thấy response không chấp nhận origin/method/header hoặc bị 401/403/redirect, nên **không gửi actual request**. Khi đó API controller của `GET/POST` có thể **chưa chạy lần nào**.

**Điểm quyết định:** HTTP 401/403 là status thuộc giao thức; CORS failure là quyết định browser có cho JavaScript sử dụng response hay không. Hai trục này **không loại trừ nhau**.

### 3.1. fetch: status 401/403 không phải JavaScript exception

```javascript
async function callApi(url) {
  try {
    const response = await fetch(url, {
      mode: "cors",
      credentials: "include"
    });

    // Có Response nghĩa là request vượt qua CORS và lớp mạng
    // đủ để browser cho JS đọc phản hồi.
    console.log("HTTP status =", response.status);
    console.log("HTTP ok =", response.ok);

    if (response.status === 401) {
      console.log("Cần đăng nhập hoặc credentials đã sai/hết hạn");
      return;
    }
    if (response.status === 403) {
      console.log("Đã bị từ chối quyền, CSRF hoặc chính sách server");
      return;
    }
    if (!response.ok) {
      console.log("HTTP error khác:", response.status);
      return;
    }

    console.log("Body:", await response.text());
  } catch (error) {
    // Không có Response để đọc: không phải cứ catch là HTTP 401.
    console.error("Network / TLS / CORS / browser policy error:", error);
  }
}
```

Hãy gọi `callApi` từ một trang đang mở ở origin frontend thật, không dùng `file://` để rồi origin thành `null`. `fetch` có thể reject do nhiều nguyên nhân: CORS, network, DNS, TLS, CSP `connect-src`, mixed content, extension, request bị abort... Console + Network mới giúp phân biệt.

**Không viết:**

```javascript
try {
  await fetch(url);
} catch (error) {
  if (error.status === 401) {
    // Sai: 401 thường nằm ở Response, không phải catch.
  }
}
```

Một `TypeError: Failed to fetch` không chứng minh server trả 401, và không có thuộc tính `status` chuẩn trong exception này để đọc status của phản hồi bị CORS chặn.

### 3.2. no-cors không phải cách sửa

```javascript
fetch("http://localhost:8080/api/profile", {
  mode: "no-cors"
});
```

`no-cors` **không cấp quyền vượt CORS để đọc dữ liệu**. Với cross-origin fetch kiểu đó, browser thường trả một **opaque response**: `status === 0`, `type === "opaque"`, không cho đọc headers/body. Nó còn hạn chế method và request headers được gửi. Thấy không còn thông báo CORS không có nghĩa ứng dụng đã hoạt động đúng. Đừng dùng `no-cors` để né lỗi cho ứng dụng cần xử lý JSON/401/403.

## 4. Phân biệt preflight OPTIONS và actual request

Browser thực hiện **CORS preflight** cho nhiều request không thuộc loại simple/safelisted, ví dụ request có `Authorization` header do script tự đặt, `Content-Type: application/json`, custom `X-CSRF-TOKEN`, hoặc method như PUT/DELETE.

Một preflight thông thường:

```http
OPTIONS /api/admin HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Phản hồi cho phép:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
```

Các method/header được liệt kê trên response có thể khác cách viết hoa/thứ tự; ví dụ chỉ minh họa. Browser kiểm tra rồi **mới gửi actual GET**:

```http
GET /api/admin HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Authorization: Basic <base64-cua-demo-user-password>
```

Actual request có thể trả **200**, **401** hoặc **403** tùy authentication/authorization; việc preflight 200 **không đồng nghĩa** user được phép truy cập `/api/admin`.

### 4.1. Preflight cố ý không chứa credentials

Preflight `OPTIONS` của CORS **không có cookies hoặc HTTP auth credentials** như request thực. Vì vậy Spring Security tài liệu yêu cầu **CORS xử lý trước Spring Security authentication**, nếu không preflight có thể bị 401 vì “chưa đăng nhập” và browser dừng luôn actual request. <PRIVATE> hoặc `permitAll(OPTIONS)` đơn thuần không bảo đảm response có đủ CORS headers.

Trong WebFlux, hãy cấu hình `ServerHttpSecurity.cors(...)` với `CorsConfigurationSource`, để Spring Security đặt CORS WebFilter đúng thứ tự. Nếu preflight bị chặn ở CDN, API gateway, proxy hoặc load balancer **trước** khi tới WebFlux, chỉnh Spring Security thôi không đủ; phải sửa lớp đang trả response.

### 4.2. Khi nào không có preflight?

Một cross-origin GET đơn giản, không có custom/special headers, có thể **không cần preflight**; browser gửi actual GET ngay. Dù vậy, actual response **vẫn phải có CORS headers phù hợp** thì JavaScript mới được đọc. Vì vậy “không thấy OPTIONS” **không phải** bằng chứng request là same-origin hoặc CORS đã đúng.

Một POST `application/x-www-form-urlencoded` với các điều kiện safelisted cũng có thể được gửi trực tiếp. CORS không bảo đảm ngăn request nguy hiểm tới server trong trường hợp này; nếu dùng browser cookies/session, **CSRF protection** vẫn cần đánh giá riêng.

### 4.3. Preflight cache

Browser có thể cache kết quả preflight theo `Access-Control-Max-Age` và các ràng buộc nội bộ. Đôi khi test trên một tab không còn thấy OPTIONS dù frontend vẫn chạy cross-origin vì preflight cached. Khi điều tra, thử context/browser profile mới, chú ý cache và dùng `curl -i -X OPTIONS` để mô phỏng preflight độc lập. Không suy rằng filter bỏ qua preflight chỉ vì Network không thấy OPTIONS ở request tiếp theo.

## 5. Các header CORS phải đọc đúng chiều

| Header | Chiều | Vai trò |
| --- | --- | --- |
| `Origin` | Request | Nguồn gốc của trang web gọi API |
| `Access-Control-Request-Method` | Preflight request | Browser định gửi method nào trên actual request |
| `Access-Control-Request-Headers` | Preflight request | Browser muốn gửi các non-safelisted headers nào |
| `Access-Control-Allow-Origin` | Response | Origin nào được phép đọc response |
| `Access-Control-Allow-Methods` | Preflight response | HTTP methods được phép |
| `Access-Control-Allow-Headers` | Preflight response | Request headers được phép |
| `Access-Control-Allow-Credentials` | Response | Cho phép credentialed CORS request khi là `true` |
| `Access-Control-Max-Age` | Preflight response | Gợi ý thời hạn cache preflight |
| `Access-Control-Expose-Headers` | Actual response | Cho JavaScript đọc một số response headers không safelisted |
| `Vary: Origin` | Response/cache | Giúp cache không trộn phản hồi dành cho origin khác |
| `WWW-Authenticate` | HTTP 401 response | Authentication challenge, **không phải CORS header** |

**Đừng nhầm `Access-Control-Allow-Headers: Authorization` với `Access-Control-Expose-Headers: Authorization`.** Loại thứ nhất nói browser có thể **gửi request header** `Authorization`; loại thứ hai nói browser được đọc một **response header** có tên cụ thể nếu server trả. `Access-Control-Expose-Headers` không tự cấp quyền, không làm Basic/JWT hợp lệ.

### 5.1. Credentials và wildcard

Khi frontend gọi:

```javascript
fetch("http://localhost:8080/api/profile", {
  credentials: "include"
});
```

server cần response hợp lệ cho credentialed request, thường có:

```http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
```

**Không trả `Access-Control-Allow-Origin: *` khi dùng credentials include.** Spring Framework cũng từ chối `allowedOrigins("*")` kết hợp `allowCredentials(true)`; nếu cần origins động, có `allowedOriginPatterns` nhưng phải hạn chế pattern thật chặt, không dùng `*` vô điều kiện cho dữ liệu cá nhân.

`credentials: "include"` không có nghĩa browser sẽ bỏ qua SameSite, Secure, third-party-cookie restrictions hoặc CSRF; cookie thực sự có được gửi còn phụ thuộc chính sách cookie/browser. Ngay cả khi CORS cho phép credentials, server vẫn có thể trả 401 vì **không có cookie hợp lệ**.

### 5.2. Headers trên phản hồi lỗi cũng quan trọng

Nếu frontend cần đọc 401/403, các phản hồi lỗi đó cũng phải có CORS headers hợp lệ. Đừng chỉ thêm CORS headers ở controller khi trả 200 rồi bỏ qua `AuthenticationEntryPoint`, `AccessDeniedHandler`, error responses, reverse proxy 502... Một CORS WebFilter chạy đủ sớm có thể đặt headers trước authorization trong Spring chain. Nhưng nếu lỗi do gateway trả trước filter, gateway phải đảm bảo headers theo chính sách và không mở wildcard credentials.

## 6. Ma trận chẩn đoán: browser, server và nguyên nhân

| Quan sát | Nguồn lỗi khả dĩ | Điều cần kiểm tra |
| --- | --- | --- |
| Console báo thiếu `Access-Control-Allow-Origin`, Network actual GET = 401 | Authentication fail **và** 401 không có CORS headers hợp lệ | CORS config cho error responses, sau đó credentials |
| Network `OPTIONS` = 401, actual GET/POST không xuất hiện | Auth layer đã chặn preflight | Đặt CORS trước Spring Security; kiểm tra gateway |
| Network `OPTIONS` = 403, không actual request | Origin/method/headers không được CORS cho phép hoặc proxy/WAF chặn | Xem CORS preflight request/response và source của 403 |
| Network `OPTIONS` = 200 nhưng thiếu ACAO/ACAH/ACAM | CORS preflight không được browser chấp nhận | Sửa CORS headers, method/header/origin |
| Network actual = 401, `fetch` nhận `Response.status=401` | HTTP authentication | Basic/JWT/session đúng chưa? `WWW-Authenticate`? |
| Network actual = 403, `fetch` nhận `Response.status=403` | HTTP authorization/CSRF/another server policy | Role, scope, CSRF token, handler, matcher |
| Network actual = 403, JavaScript chỉ catch TypeError | CORS response sai **dù HTTP status là 403** | Sửa CORS ở response lỗi rồi mới điều tra 403 |
| Không có response HTTP và catch TypeError | DNS/TLS/mixed-content/CSP/connectivity | Tab Network/Security/Console, certificate, CSP |
| curl GET trả 200 nhưng browser bị CORS chặn | curl không thực thi CORS policy | Dùng curl với Origin để **xem headers**; test bằng browser |
| API trả 403 cho cross-origin disallowed | `CorsWebFilter` có thể chủ động reject | So sánh request có Origin hợp lệ/không hợp lệ |
| Same-origin hoạt động, cross-origin thất bại | CORS/credentials/cookie policy | Exact origin, ACAO/ACAC, preflight, SameSite |
| Network request trả redirect đến login | Browser fetch theo redirect sang page/host khác | Kiểm tra final URL, redirects và CORS trên từng bước |

CORS fail không cung cấp cho JavaScript chi tiết phản hồi vì đó là mục tiêu của same-origin policy. DevTools giúp nhà phát triển quan sát mạng, nhưng app code không được suy đoán status 401/403 từ `TypeError`.

## 7. Quy trình debug từng bước trong Chrome/Firefox DevTools

### 7.1. Tái hiện trong môi trường thật

1. Mở chính trang frontend tại origin `http://localhost:5173` (không `file://`).
2. Mở DevTools → **Network**, bật Preserve log nếu có redirects, lọc theo URL endpoint hoặc `Fetch/XHR`.
3. Mở Console, gọi `fetch` có `try/catch` và log `response.status` như mục 3.
4. Tìm request **OPTIONS** nếu có; ghi lại `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
5. Xem **response headers của OPTIONS**: ACAO, ACAM, ACAH, ACAC có chấp nhận các giá trị trên không?
6. Nếu OPTIONS pass, tìm **actual request**. Kiểm tra request có `Authorization`/Cookie cần thiết không, response 401/403/200 và CORS response headers.
7. Nếu không có OPTIONS, xác minh request là simple/safelisted hoặc preflight cache; vẫn kiểm tra CORS headers của actual.
8. Nếu Network không có response HTTP rõ ràng, kiểm tra certificate, mixed content, browser extension, CSP `connect-src`, DNS, reverse proxy.
9. So sánh với curl **có và không có Origin** để tách HTTP authentication khỏi CORS behavior.
10. Viết integration tests cho cả preflight và error responses, tránh chỉ sửa tạm config cho một endpoint.

### 7.2. Điều gì xảy ra nếu Console báo “blocked by CORS policy”?

Console có thể nói “No 'Access-Control-Allow-Origin' header…” hoặc “Response to preflight request doesn't pass access control check…”. Đây là thông báo về **lý do browser không cho JS dùng response**. Không tự thay lỗi đó bằng “API server xuống” hoặc “Spring Security luôn trả 403”.

Browser cũng có thể hiển thị `net::ERR_FAILED` hoặc TypeError cho lỗi không phải CORS cấu hình, ví dụ TLS/certificate/connection refused. Khi DevTools hiển thị lỗi network/protocol, xử lý hạ tầng trước khi chỉnh CORS allowlist.

### 7.3. Phân biệt URL backend và frontend

Nếu frontend origin là `http://localhost:5173`, trong CORS allowlist cần chính `http://localhost:5173`, **không phải** `http://localhost:8080`. Backend URL là đích request; origin được cho phép là trang **gọi** API.

Không tự thêm `Access-Control-Allow-Origin` từ frontend bằng JavaScript request header: header đó phải do **server trả về**. Dùng `fetch` với request header tự đặt tên `Access-Control-Allow-Origin` chỉ khiến request phức tạp hơn, có thể kích hoạt preflight và không giải quyết vấn đề.

## 8. Cấu hình đúng trong Spring Security WebFlux

Spring Security **reactive** dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `org.springframework.web.cors.reactive.CorsConfigurationSource`. **Không** copy `HttpSecurity`, `SecurityFilterChain`, `CorsFilter` Servlet vào Spring WebFlux.

Trong Spring Security 6.x, cấu hình mẫu:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        UrlBasedCorsConfigurationSource corsSource) {
    return http
        .cors(cors -> cors.configurationSource(corsSource))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .pathMatchers("/api/admin").hasRole("ADMIN")
            .pathMatchers("/api/profile").authenticated()
            .anyExchange().denyAll())
        .httpBasic(withDefaults())
        .build();
}
```

**Đây là snippet**, project hoàn chỉnh ở mục 10 có imports, authentication manager và repository. `cors -> cors.configurationSource(corsSource)` là API `ServerHttpSecurity.CorsSpec` chính thức, được Spring Security đặt ở thứ tự thích hợp. CORS preflight thường được xử lý **trước** authentication và không cần username/password.

Có ba hướng CORS phổ biến trong WebFlux: `CorsWebFilter` riêng, `WebFluxConfigurer.addCorsMappings` ở HandlerMapping hoặc `ServerHttpSecurity.cors(...)` tích hợp security. Không tự đăng ký **nhiều bộ CORS filter/chính sách trùng nhau** mà không hiểu thứ tự; điều đó có thể tạo header lặp, preflight bị xử lý ở thành phần khác hoặc policy khó debug. Bài chọn **một nguồn `UrlBasedCorsConfigurationSource` gắn trực tiếp vào Spring Security**.

### 8.1. CorsConfigurationSource và allowlist

```java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("http://localhost:5173"));
config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
config.setAllowedHeaders(List.of(
    "Authorization", "Content-Type", "X-CSRF-TOKEN"));
config.setAllowCredentials(true);
config.setMaxAge(3600L);

UrlBasedCorsConfigurationSource source =
    new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/**", config);
```

- `allowedOrigins` mô tả origin **frontend**, exact scheme/host/port.
- `allowedMethods` là methods mà CORS cho phép, **không phải** danh sách các controller Spring đã implement.
- `allowedHeaders` cho phép browser gửi `Authorization`, `Content-Type`, `X-CSRF-TOKEN` khi preflight cần. Nó không tự cấp quyền đăng nhập.
- `allowCredentials(true)` chỉ khi frontend thực sự cần credentialed cross-origin requests. Không ghép với wildcard `allowedOrigins("*")`.
- `maxAge` liên quan cache preflight, không phải TTL session/cookie/token.
- `registerCorsConfiguration("/api/**", ...)` giới hạn CORS ở API path; `/actuator`, `/admin-console`, `/internal` không tự được mở cross-origin.
- `Vary` headers và response ACAO thực tế do CORS processor quyết định; không cần hardcode manual headers ở mỗi controller.

### 8.2. Vì sao không chỉ permitAll OPTIONS?

```java
// Không đủ nếu đứng một mình:
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

Rule này chỉ nói Spring AuthorizationWebFilter không yêu cầu identity cho OPTIONS. Browser **vẫn** cần `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` thích hợp, và `Access-Control-Allow-Credentials` khi cần. Trả 200 trống CORS headers vẫn có thể khiến preflight thất bại. Một CORS integration đúng còn kiểm tra origin, method, headers chứ không chỉ mở mọi OPTIONS.

### 8.3. CORS không thay thế Authentication/Authorization/CSRF

```text
CORS allowlist quyết định JS của origin nào đọc được response.
Authentication quyết định request là ai.
Authorization quyết định người đó có được dùng tài nguyên.
CSRF protection quyết định unsafe browser request có token hợp lệ không.
```

Vì vậy:

- Preflight 200 **không bảo đảm** actual GET được 200.
- CORS 200 không thay thế Basic credentials/session/JWT.
- CORS có thể cho phép frontend đọc **401/403** mà không cho truy cập dữ liệu được bảo vệ.
- POST dùng cookie/session hoặc Basic browser có thể cần CSRF; một 403 sau preflight thành công có thể là **CSRF 403** chứ không phải CORS.
- CORS chỉ là browser gate, không ngăn client API không phải browser gọi endpoint; server vẫn phải xác thực và phân quyền.

## 9. Java 17 thuần: mô hình kết quả fetch mà không nhầm lỗi

Trước khi xem Spring Security, một ví dụ Java 17 mô tả logic phân loại bằng kết quả đã **quan sát được** (không kết nối mạng, không thay thế browser). Mục đích là phân biệt server status với browser visibility.

File `CorsVsHttpModel.java`:

```java
public final class CorsVsHttpModel {

    static String describe(boolean readable, int serverStatus) {
        if (!readable) {
            return "browser blocked response; JS status unavailable";
        }
        if (serverStatus == 401) {
            return "HTTP 401: authentication problem";
        }
        if (serverStatus == 403) {
            return "HTTP 403: denied by server policy";
        }
        if (serverStatus >= 200 && serverStatus < 300) {
            return "HTTP success";
        }
        return "other readable HTTP response";
    }

    public static void main(String[] args) {
        System.out.println(describe(true, 200));
        System.out.println(describe(true, 401));
        System.out.println(describe(true, 403));
        System.out.println(describe(false, 401));
    }
}
```

Chạy:

```bash
javac CorsVsHttpModel.java
java CorsVsHttpModel
```

**Stdout chính xác:**

```text
HTTP success
HTTP 401: authentication problem
HTTP 403: denied by server policy
browser blocked response; JS status unavailable
```

Dòng cuối minh họa: **server có thể đã trả 401, nhưng JavaScript không có `Response.status` để đọc** nếu browser chặn vì CORS. Đây chỉ là mô hình; trình duyệt thực thực thi Fetch/CORS standard, còn Java không có CORS guard khi dùng HTTP client thông thường.

## 10. Project runnable: WebFlux có CORS, 401, 403 và CSRF

Dự án minh họa **Spring Boot 3.5.16 + Java 17+ + Spring Security 6.x**. Đây là một phiên bản release xác định để học, **không phải đề xuất production mới** trong năm 2026 nếu nhánh đã kết thúc OSS support; với hệ thống mới, chọn nhánh Spring Boot/Security còn được hỗ trợ và chạy lại tests theo migration guide.

### 10.1. Mục tiêu project

- Frontend origin được phép: `http://localhost:5173`.
- Origin khác `http://localhost:5174` bị từ chối CORS.
- `GET /api/public`: public, 200.
- `GET /api/profile`: yêu cầu authentication, không credentials -> 401.
- `GET /api/admin`: yêu cầu `ROLE_ADMIN`, user `reader` -> 403, user `admin` -> 200.
- `POST /api/changes`: yêu cầu authentication **và CSRF token** nếu CSRF mặc định bật; preflight OPTIONS vẫn có thể được duyệt độc lập với authentication.
- Cross-origin response từ allowed origin, kể cả HTTP 401/403, có **CORS headers hợp lệ** để browser đọc status.
- `curl` không Origin vẫn gọi được theo policy HTTP; nó không bị browser CORS check.
- Bài có **integration tests** dùng WebTestClient gửi header `Origin`/`Access-Control-Request-*` thật; Java test không phải browser, nên phải xem CORS headers chứ không chỉ status.

Cây file:

```text
reactive-cors-diagnostics/
├── pom.xml
└── src/
    ├── main/java/demo/cors/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/demo/cors/
        └── CorsAndHttpStatusTests.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-cors-diagnostics</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-webflux` kéo theo WebFlux/Reactor/Netty, `spring-boot-starter-security` tích hợp WebFlux Security; `spring-security-test` có helper `csrf()` cho test. Không cần `spring-boot-starter-web` (Servlet MVC) cho bài reactive. Validation starter ở đây không bắt buộc cho CORS, nhưng minh họa ứng dụng API có input cần kiểm tra; có thể bỏ nếu tối giản.

### 10.3. src/main/java/demo/cors/Application.java

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 10.4. src/main/java/demo/cors/SecurityConfiguration.java

```java
package demo.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Tài khoản dùng riêng localhost/test. Không hardcode secrets thật.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo123"))
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo123"))
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {

        return http
            // CORS được xử lý đúng thứ tự trong Spring Security.
            .cors(cors -> cors.configurationSource(corsConfigurationSource))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/profile", "/api/changes").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic ->
                basic.authenticationManager(authenticationManager))
            .formLogin(form -> form.disable())
            // CSRF mặc định bật; không disable chỉ vì POST gặp 403.
            .build();
    }
}
```

**Giải thích theo thứ tự:**

1. `CorsConfigurationSource` gán **allowlist origin frontend**, methods, request headers và credentialed mode. `UrlBasedCorsConfigurationSource` nằm ở **`org.springframework.web.cors.reactive`**, không dùng Servlet class.
2. `.cors(cors -> cors.configurationSource(corsConfigurationSource))` dùng tích hợp CORS của `ServerHttpSecurity`, xử lý preflight trước authentication theo đúng WebFlux filter order.
3. `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`; `reader` đăng nhập đúng vẫn 403 ở `/api/admin`.
4. `httpBasic` dùng để tạo tình huống authentication 401 rõ ràng và test được bằng `setBasicAuth`.
5. CSRF **không bị tắt**. Vì `/api/changes` là POST, nếu Basic đúng mà CSRF token thiếu, request có thể bị 403. Đây là một nguyên nhân 403 **không liên quan** CORS/role.
6. `cors.setAllowCredentials(true)` phản ánh frontend dùng `fetch(..., {credentials:"include"})`, nhưng không cấp cookie hay user; nó chỉ cho phép browser đọc credentialed response từ origin được chấp thuận.
7. Không khai báo thêm `@CrossOrigin("*")` ở controller, tránh có hai cấu hình mâu thuẫn.
8. Chính sách giới hạn CORS ở `/api/**`. Nếu ứng dụng có auth/login/logout/CSRF endpoint ngoài path này, hãy thiết kế allowlist cho những path đó theo nhu cầu thực tế.

**Lưu ý thực tế:** Nếu ứng dụng dùng session cookie cross-site trên hai site khác nhau, cần cấu hình `SameSite=None; Secure` khi phù hợp, HTTPS và bảo vệ CSRF; CORS đúng **không ép browser gửi cookie bị chính sách của nó từ chối**.

### 10.5. src/main/java/demo/cors/ApiController.java

```java
package demo.cors;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record ChangeRequest(String value) {}

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("profile OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }

    @PostMapping(value = "/api/changes",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<String> changes(@RequestBody Mono<ChangeRequest> body) {
        return body.map(request -> "changed:" + request.value());
    }
}
```

Endpoint `POST /api/changes` không tự tạo hoặc kiểm tra CSRF token trong controller; Spring Security `CsrfWebFilter` kiểm tra trước. Đây là ví dụ cô lập: **CORS preflight có thể thành công rồi POST vẫn bị 403 do thiếu CSRF**, chứng minh CORS success không phải authorization success.

## 11. Integration test: cùng một origin vẫn có thể 200, 401 hoặc 403

Vì Java HTTP client **không phải browser** và không chặn response dựa trên CORS, `WebTestClient` tests phải kiểm tra cả **status lẫn CORS response headers**. Nếu chỉ assert `status=401` thì không thể kết luận browser sẽ đọc được 401.

### 11.1. src/test/java/demo/cors/CorsAndHttpStatusTests.java

```java
package demo.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsAndHttpStatusTests {

    private static final String ALLOWED = "http://localhost:5173";
    private static final String DENIED = "http://localhost:5174";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec getWithOrigin(
            String uri, String username) {
        return client.get().uri(uri)
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(headers -> {
                if (username != null) {
                    headers.setBasicAuth(username, "demo123");
                }
            })
            .exchange();
    }

    @Test
    void allowedGetPreflightDoesNotRequireAuthentication() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void allowedPostPreflightHasNoPasswordOrSession() {
        client.options().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void rejectedOriginPreflightGetsCors403NotAuth401() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, DENIED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void preflightWithUnsupportedMethodIsRejected() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightWithUnsupportedRequestHeaderIsRejected() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "x-evil-header")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void publicGetWithAllowedOriginHasReadable200() {
        getWithOrigin("/api/public", null)
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void missingAuthenticationHasReadable401() {
        getWithOrigin("/api/profile", null)
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void wrongBasicPasswordHasReadable401() {
        client.get().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }

    @Test
    void correctReaderHasReadable200() {
        getWithOrigin("/api/profile", "reader")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("profile OK");
    }

    @Test
    void authenticatedReaderLackingRoleHasReadable403() {
        getWithOrigin("/api/admin", "reader")
            .expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }

    @Test
    void authorizedAdminHasReadable200() {
        getWithOrigin("/api/admin", "admin")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void disallowedOriginActualGetIsRejectedByCors() {
        client.get().uri("/api/public")
            .header(HttpHeaders.ORIGIN, DENIED)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void requestWithoutOriginIsNotSubjectToCorsHeaders() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void postWithoutCsrfIs403EvenThoughCorsAllowsOrigin() {
        client.post().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }

    @Test
    void postWithValidTestCsrfAndAuthenticationIs200() {
        client.mutateWith(csrf())
            .post().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("changed:hello");
    }

    @Test
    void postWithValidTestCsrfButNoAuthenticationIs401() {
        client.mutateWith(csrf())
            .post().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }
}
```

Bộ test có **16 phương thức `@Test`**. Trong đó:

- Năm test đầu kiểm tra **preflight**: không credentials, allowed origin/method/headers hay CORS 403 khi từ chối.
- Nhóm sau chứng minh **actual request 200, 401 hoặc 403 đều có ACAO hợp lệ** khi frontend origin được phép.
- Request có origin bị từ chối có thể nhận **HTTP 403 do CORS processor**, khác với 403 do `hasRole`.
- Request không có `Origin` hoạt động theo policy HTTP mà không cần ACAO.
- POST không CSRF bị **403 dù CORS hợp lệ**.
- `mutateWith(csrf())` là helper dành cho test, cung cấp token/attributes phù hợp để **cô lập tầng CSRF**. Nó không phải quy trình frontend production lấy/lưu token; với browser thật cần CSRF token từ server và cookie/session đúng.

**CORS test không giống browser test:** `WebTestClient` nhìn thấy tất cả status/headers do server trả dù browser có thể chặn chúng. Do đó test CORS phải assert `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials` khi có credentials, không chỉ `expectStatus().isOk()`.

### 11.2. Ma trận test tự kiểm tra nhanh

| Request | Expected HTTP | CORS headers | Điều chứng minh |
| --- | --- | --- | --- |
| OPTIONS /api/profile, origin allowed, yêu cầu Authorization | **200** | ACAO=allowed | Preflight không cần auth |
| OPTIONS /api/changes, origin allowed, POST/JSON/auth | **200** | ACAO, ACAC=true | Browser có thể gửi actual |
| OPTIONS origin not allowed | **403** | Không ACAO | CORS processor chặn |
| OPTIONS yêu cầu DELETE (không allowed) | **403** | Không chấp nhận method | Preflight fail |
| GET /api/public, allowed Origin | **200** | ACAO | Public readable |
| GET /api/profile, không Basic, allowed Origin | **401** | ACAO | HTTP auth error readable |
| GET /api/profile, sai Basic, allowed Origin | **401** | ACAO | Password/auth error readable |
| GET /api/admin, reader Basic, allowed Origin | **403** | ACAO | HTTP authz error readable |
| GET /api/admin, admin Basic, allowed Origin | **200** | ACAO | Authn + authz success |
| GET /api/public, denied Origin | **403** | Không ACAO | CORS failure |
| GET /api/public, không Origin | **200** | Không cần ACAO | Không có browser CORS check |
| POST /api/changes, Basic đúng, thiếu CSRF | **403** | ACAO | CSRF failure không đồng nghĩa CORS |
| POST /api/changes, Basic đúng, CSRF test hợp lệ | **200** | ACAO | Đã qua CSRF + authentication |
| POST /api/changes, CSRF test hợp lệ, thiếu Basic | **401** | ACAO | CSRF không thay authentication |

Nếu response 401/403 thiếu ACAO trong môi trường thật dù test qua Spring context pass, hãy kiểm tra **reverse proxy, gateway, error page handler, security chain khác hoặc HTTP server ngoài context**. Test nên có một tầng chạy qua gateway nếu hạ tầng có nhiều điểm trả lỗi.

## 12. Thực hành bằng curl: thấy HTTP thật, không giả vờ browser

### 12.1. Chạy project

Yêu cầu Java 17+ và Maven tương thích. Đặt file đúng package `demo.cors`, chạy:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Theo mã có **16 tests**; kỳ vọng Surefire thống kê `Tests run: 16, Failures: 0, Errors: 0` cùng `BUILD SUCCESS` khi chạy trên môi trường tương thích. Đây là **kết quả dự kiến từ mã**, không phải khẳng định đã được thực thi trên máy người đọc.

### 12.2. Mô phỏng preflight allowed origin

```bash
curl -i -X OPTIONS http://localhost:8080/api/profile \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Dự kiến HTTP **200** và có `Access-Control-Allow-Origin: http://localhost:5173`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` cùng `Access-Control-Allow-Credentials: true`. Không cần `-u` ở preflight vì browser preflight **không mang credentials**.

### 12.3. Mô phỏng preflight denied origin

```bash
curl -i -X OPTIONS http://localhost:8080/api/profile \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Dự kiến HTTP **403 Invalid CORS request**, không có ACAO cho origin bị từ chối. **Đây là 403 do CORS processor**, không phải user đã đăng nhập nhưng thiếu role; request còn chưa đến controller logic.

### 12.4. Actual 401 với CORS hợp lệ

```bash
curl -i http://localhost:8080/api/profile \
  -H "Origin: http://localhost:5173"
```

Dự kiến HTTP **401** với `WWW-Authenticate` và `Access-Control-Allow-Origin: http://localhost:5173`. Nếu trình duyệt gửi GET mà không có authentication hợp lệ (dù CORS pass), JavaScript sẽ thấy status 401.

### 12.5. Actual 403 do thiếu role

```bash
curl -i -u reader:demo123 http://localhost:8080/api/admin \
  -H "Origin: http://localhost:5173"
```

Dự kiến HTTP **403** và ACAO đúng frontend origin. User `reader` đã đăng nhập nhưng không có `ROLE_ADMIN`. Đây là 403 của **authorization**, không phải lỗi CORS.

### 12.6. Actual 200 với role ADMIN

```bash
curl -i -u admin:demo123 http://localhost:8080/api/admin \
  -H "Origin: http://localhost:5173"
```

Dự kiến HTTP **200** có body `admin OK` cùng ACAO. Nếu frontend JS vẫn không đọc được response, kiểm tra headers thực từ browser, redirect/proxy, credentials mode và origin chính xác.

### 12.7. Không có Origin cũng có thể nhận 200 từ curl

```bash
curl -i http://localhost:8080/api/public
```

Dự kiến HTTP **200** với `public OK`, không cần ACAO. Đây là minh họa: CORS **không khóa URL khỏi non-browser clients**, chỉ điều khiển khả năng đọc cross-origin của browser.

**Bảo mật shell:** Credentials `reader:demo123` và `admin:demo123` là test fixture công khai; với tài khoản thật không ghi password vào command history hoặc logs. Trên PowerShell có thể dùng `curl.exe`; cú pháp nối dòng `\` dành cho shell kiểu Bash và phải được điều chỉnh theo PowerShell.

## 13. Thực hành browser fetch để thấy hai loại lỗi

Hãy mở một trang frontend thực tại `http://localhost:5173` (ví dụ Vite dev server) và chạy đoạn này trong DevTools Console; **đừng chạy từ `file://`** vì origin có thể là `null`.

```javascript
const api = "http://localhost:8080";

async function inspect(path, username, password) {
  const headers = {};
  if (username) {
    // Chỉ dùng credentials demo US-ASCII. Không ghi password thật vào JS.
    headers.Authorization = "Basic " + btoa(username + ":" + password);
  }

  try {
    const response = await fetch(api + path, {
      method: "GET",
      mode: "cors",
      credentials: "include",
      headers
    });

    console.log({
      path,
      status: response.status,
      ok: response.ok,
      type: response.type
    });

    if (response.status === 401) {
      console.log("Đây là HTTP 401 có thể đọc được");
    } else if (response.status === 403) {
      console.log("Đây là HTTP 403 có thể đọc được");
    } else {
      console.log("Body:", await response.text());
    }
  } catch (error) {
    console.error("Fetch rejected (network/CORS/etc):", error);
  }
}

await inspect("/api/public");
await inspect("/api/profile");
await inspect("/api/profile", "reader", "wrong");
await inspect("/api/profile", "reader", "demo123");
await inspect("/api/admin", "reader", "demo123");
await inspect("/api/admin", "admin", "demo123");
```

Với CORS policy của project, các kết quả dự kiến:

```text
GET /api/public                    -> Response.status 200
GET /api/profile, no credentials  -> Response.status 401
GET /api/profile, wrong password  -> Response.status 401
GET /api/profile, valid reader    -> Response.status 200
GET /api/admin, reader            -> Response.status 403
GET /api/admin, admin             -> Response.status 200
```

Với request có `Authorization` header từ script, browser có thể gửi preflight OPTIONS trước. Dù preflight 200, actual GET vẫn có thể 401/403. Các lệnh từ console cũng cần server đang chạy, đúng frontend origin `:5173`, và không có proxy nào thay đổi request/headers.

**Thử sai origin:** nếu frontend chạy tại `http://localhost:5174` mà backend chỉ cho `:5173`, script thường nhận `TypeError`/CORS error thay vì status. Nếu request là simple GET, backend CORS filter có thể trả HTTP 403 cho actual GET; nếu request gửi Authorization thì preflight thường đã 403 và actual GET không được gửi.

### 13.1. Không hardcode password thật trong JavaScript

`btoa("reader:demo123")` chỉ là **mẫu cho demo localhost**. Base64 của Basic **không mã hóa an toàn**, người dùng có thể xem source/DevTools. Với ứng dụng browser production, sử dụng flow đăng nhập/credential handling phù hợp (session, OIDC/OAuth2...) và HTTPS, không đưa secret dùng chung vào frontend bundle.

## 14. Khi không phải CORS mà vẫn giống CORS

### 14.1. Authentication redirect sang login page

Ứng dụng có form login có thể redirect `302` đến `/login` thay vì 401. Browser `fetch` mặc định có thể follow redirect; nếu trang cuối khác origin hoặc response cuối thiếu CORS headers, Console báo CORS. Khi điều tra hãy bật **Preserve log** và kiểm tra chuỗi redirect, URL cuối, request headers và policy ở **mỗi chặng**. Đừng chỉ thêm ACAO vào endpoint gốc nếu response bị chặn đến từ redirect target.

### 14.2. Reverse proxy/WAF trả 401/403/502 trước Spring

Một API gateway có thể yêu cầu API key, WAF có thể chặn nguồn IP, hoặc load balancer trả lỗi khi upstream hỏng. Khi đó controller và `SecurityWebFilterChain` **chưa chắc đã được gọi**. Nếu lỗi gateway không mang ACAO, browser báo CORS và nhà phát triển dễ sửa nhầm ở Spring.

Chẩn đoán bằng request ID, access logs đã redact, upstream status, response `Server`/proxy headers khi an toàn và đường request qua hạ tầng. CORS policy của proxy phải thống nhất với backend; không trả `*` với credentials để “cứu” lỗi cho nhanh.

### 14.3. TLS, mixed content, DNS, firewall, CSP

Một trang HTTPS gọi API HTTP có thể bị **mixed content** chặn trước khi có HTTP response. Certificate không hợp lệ, DNS lỗi, connection refused, CSP `connect-src`, extension hoặc ad blocker cũng có thể tạo `Failed to fetch`. Không thay CORS config để chữa certificate, reverse proxy unreachable hay CSP.

### 14.4. Cookie không đi theo request

CORS response hợp lệ nhưng server 401 vì session cookie không được gửi. Kiểm tra `credentials: "include"`, `SameSite`, `Secure`, cookie domain/path, browser privacy settings và URL có dùng `localhost` hay `127.0.0.1`. **Chỉ thêm `Access-Control-Allow-Credentials: true` không tạo ra cookie** và không ghi đè chính sách SameSite/third-party cookies.

### 14.5. CSRF chặn POST sau khi preflight pass

Một request POST có `Authorization`, `Content-Type: application/json` hoặc `X-CSRF-TOKEN` có thể preflight thành công, rồi actual request bị Spring Security `CsrfWebFilter` trả **403** vì thiếu/hết hạn CSRF token. Nếu CORS headers đúng, JavaScript nhận `Response.status=403`; muốn sửa phải giải quyết CSRF token/session, **không** tắt CORS và **không** tắt CSRF theo phản xạ.

### 14.6. Browser chặn ACAO wildcard khi credentials include

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Đây **không** phải cấu hình hợp lệ để browser cho đọc credentialed response. Từ frontend có `credentials:"include"`, browser sẽ không cho JavaScript truy cập, dù request server đã trả 200. Sửa bằng origin cụ thể được tin cậy và chính sách cookie/authn đúng.

## 15. Thói quen kiểm thử hệ thống phân tán

Khi triển khai thực tế có CDN, ingress, API gateway, Spring WebFlux và identity provider, cần test các lớp:

| Lớp | Kiểm tra | Mục tiêu |
| --- | --- | --- |
| Unit/config | Allowed origins, methods, headers, credentials | Không wildcard nhầm, không mở origin tùy ý |
| WebFlux integration | `OPTIONS` và actual responses 200/401/403 | CORS integration trước authentication |
| Authentication | Không/sai/đúng credentials | 401 rõ, độc lập CORS |
| Authorization | Role/scopes/tenant/object | 403 rõ, độc lập CORS |
| CSRF | Unsafe methods có/thiếu/expired CSRF | Không nhầm 403 CSRF với 403 role |
| Browser E2E | `fetch` actual frontend origin, cookie behavior | JavaScript đọc được 401/403 hợp lệ |
| Gateway E2E | Error responses từ gateway/WAF và redirects | Không bị mất CORS headers ở lớp trung gian |
| Security | Wildcard + credentials, Origin reflection, XSS/CSRF | Không mở API dữ liệu nhạy cảm cho origin xấu |
| Observability | Request ID, CORS/preflight metrics, redaction | Điều tra được mà không lộ token/password |

**Cẩn trọng với "reflect any Origin":** Một middleware tự lấy `Origin` trong request rồi trả lại `Access-Control-Allow-Origin` bất kể giá trị và đồng thời `Allow-Credentials: true` có thể cho website độc hại đọc dữ liệu nhạy cảm của user. CORS allowlist là một **quyết định tin cậy**, không phải chỉ để hết lỗi Console.

## 16. Các lỗi lập trình thường gặp

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Cho `allowedOrigins("http://localhost:8080")` thay vì origin frontend `:5173` | Browser bị chặn | Dùng origin của **trang gọi** API |
| `Access-Control-Allow-Origin` chỉ thêm ở controller 200 | JS không đọc được 401/403 | Dùng CORS filter/source ở trước security/errors |
| `OPTIONS` yêu cầu session cookie | Preflight 401 | Để CORS processor xử lý trước auth |
| Chỉ `permitAll(OPTIONS)` | Preflight 200 nhưng thiếu CORS headers | Cấu hình CORS source thật |
| Dùng Servlet `CorsFilter` trong WebFlux | Sai stack hoặc thứ tự | Dùng reactive `CorsWebFilter`/`ServerHttpSecurity.cors` |
| `allowedOrigins("*")` + `allowCredentials(true)` | Không hợp lệ/không được browser chấp nhận | Chỉ định trusted origins |
| Quên `Authorization` trong allowed headers | Preflight bị từ chối | Thêm đúng request headers cần |
| Cho `Access-Control-Expose-Headers` thay vì `Allow-Headers` | Không giải quyết preflight | Phân biệt request header và response header |
| Nhận `TypeError` rồi đọc `error.status` | Không phát hiện được 401/403 | Dùng `response.status` khi fetch resolve |
| Bật `mode: "no-cors"` | Opaque response, status 0, không đọc body | Sửa server CORS config |
| `curl` trả 200, kết luận browser được phép | curl không enforce CORS | Kiểm tra response headers, test browser |
| CORS pass, POST 403, tắt CSRF | Tạo lỗ hổng CSRF | Gửi CSRF token hợp lệ và cùng session |
| CORS pass nhưng thiếu cookie, 401 | Cookie policy/credentials mode sai | Kiểm tra credentials, SameSite, Secure, domain |
| Giả `Origin` là danh tính user | Bypass authentication | Authenticate riêng bằng session/JWT/Basic |
| Reflect `Origin` tùy ý + credentials | Lộ dữ liệu cho origin xấu | Allowlist chặt |
| Preflight không thấy trong Network | Simple request hoặc preflight cached | Kiểm tra request headers/cache |
| API server trả 502 không ACAO từ gateway | Browser báo CORS, app không chạy | Sửa gateway/upstream và error handling |
| Tắt CORS ở Spring để “tắt lỗi CORS” | Browser vẫn áp same-origin policy | Bật hỗ trợ CORS đúng |
| Có hai CORS configurations mâu thuẫn | Headers không nhất quán, khó debug | Chọn một source/policy rõ ràng |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `fetch()` nhận server 401 nhưng CORS hợp lệ có bị reject không?  
**Trả lời:** Theo Fetch thông thường, **không**. Promise resolve `Response`; `response.status === 401`, `response.ok === false`.

**Câu 2.** Server trả 401 nhưng thiếu ACAO, JavaScript có đọc được status 401 không?  
**Trả lời:** Với cross-origin request cần CORS, browser có thể chặn response và reject `fetch`; JavaScript không nhận được status 401 dù DevTools Network có thể hiển thị HTTP 401.

**Câu 3.** OPTIONS preflight 200 có bảo đảm actual GET /api/admin 200 không?  
**Trả lời:** Không. Preflight chỉ kiểm tra CORS permission, không xác thực user/role. Actual GET có thể 401 hoặc 403.

**Câu 4.** Browser gửi credentials trong preflight OPTIONS không?  
**Trả lời:** Preflight CORS không mang cookies/HTTP auth credentials như actual request. CORS xử lý trước authentication là điều quan trọng.

**Câu 5.** User reader có password đúng nhưng thiếu ROLE_ADMIN, server trả gì?  
**Trả lời:** Thường **403 Forbidden**; nếu ACAO hợp lệ, JS thấy status 403. Đây là authorization, không phải CORS.

**Câu 6.** Vậy 403 của request OPTIONS có thể do cái gì khác?  
**Trả lời:** CORS processor có thể trả 403 khi origin, requested method hoặc requested headers không được allow; WAF/gateway cũng có thể trả 403. Không tự gán cho role.

**Câu 7.** Khác nhau giữa `Access-Control-Allow-Headers` và `Access-Control-Expose-Headers`?  
**Trả lời:** `Allow-Headers` cho request headers browser muốn **gửi**; `Expose-Headers` cho JS đọc thêm response headers được server **trả**.

**Câu 8.** Tại sao origin frontend `http://localhost:5173` không thể thay bằng `http://localhost:8080` trong ACAO?  
**Trả lời:** ACAO phải cho phép **origin của trang gọi**, còn `:8080` là API destination.

**Câu 9.** Thêm `mode:"no-cors"` là sửa lỗi đúng không?  
**Trả lời:** Không. Cross-origin response thành opaque, JS không đọc body/status; nó không cấp quyền vượt CORS.

**Câu 10.** `curl` không có Origin nhận 200, vậy frontend browser cũng được đọc 200?  
**Trả lời:** Không. curl không áp dụng CORS. Browser cần CORS headers phù hợp khi cross-origin.

**Câu 11.** POST Basic đúng nhưng thiếu CSRF token trả 403 có đồng nghĩa CORS sai?  
**Trả lời:** Không. CSRF là chốt khác; nếu CORS headers có đủ, JavaScript nhận status 403 để xử lý.

**Câu 12.** `credentials:"include"` có ép cookie cross-site luôn được gửi không?  
**Trả lời:** Không. Cookie vẫn chịu SameSite, Secure, domain/path và chính sách browser.

**Câu 13.** Nếu gateway trả 401 không ACAO trước khi request vào Spring Security, sửa `CorsConfigurationSource` trong app đã đủ chưa?  
**Trả lời:** Chưa. Phải sửa chính gateway/error response path; filter ở Spring không thể thêm header vào response do gateway đã trả trước đó.

**Câu 14.** Chỉ thêm `permitAll(OPTIONS)` có phải một giải pháp CORS đầy đủ?  
**Trả lời:** Không. Browser vẫn cần ACAO, ACAM, ACAH và ACAC khi cần, theo origin/method/header thực tế.

**Câu 15.** Nếu Console báo CORS nhưng Network không có HTTP response, có nên chỉnh allowedOrigins ngay?  
**Trả lời:** Không vội. Kiểm tra DNS/TLS/mixed content/CSP/timeout/extension trước; không phải mọi `Failed to fetch` là CORS configuration.

## 18. Checklist production

- [ ] Frontend và backend origins được xác định đúng bằng scheme/host/port.
- [ ] CORS source cho phép **trusted origins**, không reflect Origin tùy ý.
- [ ] `allowedMethods`/`allowedHeaders` đúng với preflight thực tế; không mở rộng vô cớ.
- [ ] Nếu credentials include, ACAO là origin cụ thể và ACAC=true; cookie policy hợp lệ.
- [ ] Preflight OPTIONS không bị authentication/gateway chặn vô tình; CORS chạy trước auth.
- [ ] Response **401/403** từ Spring **và gateway** có CORS headers hợp lệ khi frontend được phép.
- [ ] CORS không thay thế authentication, authorization, CSRF hoặc server-side permission checks.
- [ ] Không dùng `mode:"no-cors"` để làm im lỗi.
- [ ] `fetch` xử lý `response.status` sau resolve và `catch` riêng cho network/CORS.
- [ ] DevTools xem OPTIONS + actual, requests, responses, redirects, cache và cookie.
- [ ] Có integration tests preflight, actual 200, auth 401, role 403, CSRF 403, denied origin.
- [ ] Có browser E2E thực ở frontend origin thật, không chỉ curl/WebTestClient.
- [ ] Không dùng JavaScript credentials thật trong source; HTTPS, secret management và CSRF chuẩn.
- [ ] Không leak Authorization/Cookie/CSRF token vào logs/traces.
- [ ] Có runbook cho gateway/WAF/IdP errors, CORS policy theo từng service/chain.
- [ ] Tuân chuẩn `Vary: Origin`/cache behavior khi ACAO phụ thuộc Origin.

## 19. Tổng kết và tài liệu tham khảo

**Quy tắc nhanh nhất:**

```text
fetch RESOLVE + response.status = 401
    -> HTTP Authentication fail, CORS cho JS đọc response.

fetch RESOLVE + response.status = 403
    -> HTTP server policy deny (role, CSRF, ...), CORS cho JS đọc.

fetch REJECT + TypeError / CORS error
    -> JS không có Response. Xem DevTools OPTIONS/actual/TLS/network.
       Server vẫn CÓ THỂ đã gửi HTTP 200/401/403 bị CORS chặn.

OPTIONS 200
    -> CORS preflight được chấp nhận; actual request vẫn có thể 401/403.

curl 200
    -> Không chứng minh browser CORS pass.
```

Bản chất: **CORS không phải cơ chế xác thực hay phân quyền**. Hãy kiểm tra *hai trục độc lập*: (1) browser có được quyền đọc HTTP response không, (2) server có chấp nhận credentials/role/CSRF và trả status gì. Đừng sửa CORS bằng cách tắt Spring Security hoặc mở mọi origin; đừng sửa 401/403 bằng cách đổi `fetch` sang `no-cors`.

**Tài liệu chính thức đã đối chiếu:**

- Spring Security – Reactive CORS integration (xử lý preflight trước authentication): https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security 6.5 – `ServerHttpSecurity.CorsSpec` (configurationSource): https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Security 6.5 – `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Framework – WebFlux CORS (HandlerMapping và CorsWebFilter): https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- MDN – Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN – Using Fetch API, response vs network error: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch
- MDN – CORS Errors (console/network/preflight): https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors
- MDN – Credentials và ACAO wildcard: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials
- MDN – Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- OWASP – CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
