# Giới hạn giữ client secret trong ứng dụng chạy trên trình duyệt

Ứng dụng chạy trong trình duyệt không thể giữ bí mật một giá trị mà JavaScript cần đọc để thực hiện xác thực. Mã nguồn frontend, cấu hình được đóng gói, biến môi trường dùng lúc build và dữ liệu gửi tới trình duyệt đều có thể được người dùng kiểm tra. Vì vậy, một SPA hoặc ứng dụng JavaScript thuần chạy ở browser được xem là **public client** trong OAuth 2.0; client không thể chứng minh an toàn rằng nó đang giữ một client secret riêng tư.

Khi mô tả OAuth2/OIDC bằng springdoc-openapi, cần thể hiện đúng giới hạn này trong security scheme và cấu hình Swagger UI. Ứng dụng trình duyệt nên dùng Authorization Code với PKCE. Nếu hệ thống cần confidential client hoặc cần giữ access token/refresh token ở phía máy chủ, có thể đặt một backend-for-frontend (BFF) làm trung gian. Client secret chỉ được lưu và sử dụng ở môi trường backend có thể kiểm soát.

## 1. Client secret dùng để làm gì?

Trong OAuth 2.0, client là ứng dụng yêu cầu quyền truy cập tài nguyên. Authorization server có thể cấp một định danh client (client_id) và, với confidential client, một thông tin xác thực client như client_secret.

Hai giá trị này có mục đích khác nhau:

| Giá trị | Vai trò | Có thể công khai? |
|---|---|---|
| client_id | Định danh ứng dụng đã đăng ký với authorization server | Thường có; không phải mật khẩu |
| client_secret | Bằng chứng xác thực client với authorization server | Không; phải được giữ bí mật |

client_id thường xuất hiện trong authorization request để authorization server biết ứng dụng nào đang yêu cầu đăng nhập. Nó không chứng minh rằng người gửi request là ứng dụng đáng tin cậy.

client_secret là credential của client. Với confidential client, backend có thể dùng nó khi gọi token endpoint, chẳng hạn qua HTTP Basic hoặc phương thức xác thực client được authorization server hỗ trợ. Nếu secret bị lộ, người khác có thể giả mạo client trong những luồng mà secret đó được chấp nhận.

Không được nhầm client secret với access token, refresh token, ID token hoặc API key. Chúng là những loại credential khác nhau, có đối tượng sử dụng và vòng đời khác nhau.

## 2. Vì sao trình duyệt không thể giữ client secret?

Trình duyệt phải nhận được mã JavaScript và dữ liệu cần thiết để chạy ứng dụng. Người dùng có quyền kiểm soát môi trường trình duyệt của mình, vì vậy họ có thể xem những gì ứng dụng tải xuống và gửi đi.

Một client secret được nhúng trong ứng dụng có thể bị tìm thấy qua:

- Bundle JavaScript sau khi build, kể cả khi mã đã minify.
- Source map được phát hành cùng frontend.
- Biến môi trường được thay thế vào mã trong quá trình build.
- Request body, header hoặc network trace khi ứng dụng gửi secret.
- Developer Tools, debugger, browser extension hoặc proxy do người dùng kiểm soát.
- Bộ nhớ runtime khi JavaScript đọc secret để tạo request.
- Log frontend, báo cáo lỗi, file HAR hoặc telemetry ghi lại dữ liệu request.

Minify, obfuscate, mã hóa chuỗi trong bundle hoặc đổi tên biến không làm secret trở thành bí mật. Nếu ứng dụng cần giải mã hoặc sử dụng giá trị trong browser, người kiểm soát browser có thể quan sát được thao tác đó.

### 2.1. Biến môi trường frontend không phải kho bí mật

Trong backend, biến môi trường có thể được dùng để truyền cấu hình nhạy cảm vào tiến trình server. Với frontend, các biến được sử dụng trong lúc build thường trở thành một phần của file tĩnh được gửi tới trình duyệt.

Ví dụ các quy ước thường gặp:

| Công cụ frontend | Tiền tố biến công khai thường gặp |
|---|---|
| Vite | VITE_ |
| Create React App | REACT_APP_ |
| Next.js client bundle | NEXT_PUBLIC_ |
| Nuxt public runtime config | runtimeConfig.public |

Tên tiền tố cụ thể phụ thuộc công cụ và phiên bản, nhưng nguyên tắc không thay đổi: mọi giá trị được đưa vào client bundle phải được xem là công khai.

Ví dụ không an toàn:

~~~javascript
const clientSecret = import.meta.env.VITE_OAUTH_CLIENT_SECRET;

await fetch("https://id.example.com/oauth2/token", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: new URLSearchParams({
    grant_type: "client_credentials",
    client_id: import.meta.env.VITE_OAUTH_CLIENT_ID,
    client_secret: clientSecret
  })
});
~~~

Secret ở ví dụ trên sẽ được đưa vào bundle hoặc xuất hiện trong request từ browser. Việc đặt tên biến là SECRET, lưu trong file .env.production hay che nó khỏi giao diện không thay đổi rủi ro này.

## 3. Public client và confidential client

OAuth 2.0 phân biệt client dựa trên khả năng giữ credential bí mật trong môi trường triển khai.

| Đặc điểm | Public client | Confidential client |
|---|---|---|
| Môi trường điển hình | SPA, mobile app, ứng dụng desktop phân phối cho người dùng | Backend web, BFF, service chạy trên máy chủ được kiểm soát |
| Có thể giữ client secret? | Không | Có, nếu lưu trữ và vận hành đúng cách |
| Cơ chế thường dùng | Authorization Code + PKCE | Authorization Code, Client Credentials hoặc flow phù hợp |
| Nơi lưu credential | Không nhúng secret; có thể dùng client ID công khai | Secret manager, vault hoặc cấu hình server được bảo vệ |
| Mức kiểm soát | Người dùng kiểm soát runtime và có thể kiểm tra mã | Đơn vị vận hành kiểm soát máy chủ và quyền truy cập |

Một ứng dụng web có frontend và backend cần được phân biệt theo thành phần. JavaScript frontend là public client. Backend có thể là confidential client nếu credential được giữ hoàn toàn ở server và server có thể xác thực với authorization server.

Đăng ký ứng dụng dưới dạng confidential client không làm cho frontend trở nên an toàn để giữ secret. Kiểu client phải phản ánh nơi credential thực sự được sử dụng.

## 4. Không dùng Client Credentials trực tiếp từ browser

Client Credentials dành cho ứng dụng gọi API bằng danh tính của chính ứng dụng, không có người dùng cuối tham gia. Flow này thường yêu cầu client xác thực với token endpoint bằng client secret, private key hoặc một phương thức xác thực client khác.

Browser không thể giữ an toàn các credential đó. Nếu SPA gọi token endpoint với client secret, mọi người có quyền chạy ứng dụng đều có thể trích xuất secret và sử dụng ngoài ứng dụng.

Luồng không an toàn:

~~~text
Browser SPA
   |
   | client_id + client_secret
   v
Authorization Server
   |
   | access token
   v
Resource API
~~~

Luồng phù hợp cho service-to-service:

~~~text
Browser                 Backend / BFF             Authorization Server
   |                           |                            |
   |-- request user action --->|                            |
   |                           |-- client authentication -->|
   |                           |<-- access token ------------|
   |                           |                            |
   |                           |-- call protected API ------> Resource API
   |<-- application response --|                            |
~~~

Backend giữ client credential, xin access token và gọi resource API. Browser chỉ giao tiếp với backend qua phiên đăng nhập hoặc cơ chế được thiết kế cho ứng dụng.

## 5. Authorization Code với PKCE cho ứng dụng browser

Với SPA cần đăng nhập người dùng và gọi API trực tiếp từ browser, lựa chọn phổ biến là Authorization Code với Proof Key for Code Exchange (PKCE). Public client không cần client secret trong flow này.

PKCE tạo một cặp giá trị cho mỗi authorization request:

- code_verifier: chuỗi ngẫu nhiên có entropy cao, được client giữ tạm thời.
- code_challenge: giá trị dẫn xuất từ verifier, thường dùng phương thức S256.

Client gửi code challenge trong authorization request. Khi đổi authorization code lấy token, client gửi code verifier. Authorization server kiểm tra verifier có khớp challenge ban đầu không. Một bên khác chỉ đánh cắp được authorization code sẽ không có verifier để đổi code thành token.

Luồng khái quát:

~~~text
Browser SPA                 Authorization Server             Resource API
    |                                |                              |
    |-- authorize + code_challenge ->|                              |
    |<-- login / consent ------------|                              |
    |<-- authorization code ---------|                              |
    |                                |                              |
    |-- code + code_verifier ------->|                              |
    |<-- access token ---------------|                              |
    |                                                               |
    |---------------- access token ------------------------------->|
    |<--------------- protected resource --------------------------|
~~~

Các yêu cầu triển khai:

1. Đăng ký client dưới dạng public client.
2. Dùng Authorization Code flow và bật PKCE với S256.
3. Đăng ký redirect URI chính xác, tránh wildcard rộng.
4. Sinh code_verifier bằng bộ sinh số ngẫu nhiên mật mã an toàn.
5. Dùng state để liên kết authorization response với request đã bắt đầu.
6. Với OIDC, dùng nonce và xác minh ID token theo quy tắc OIDC.
7. Không gửi client secret từ browser.
8. Gửi access token tới resource API theo đúng audience và scope.

PKCE bảo vệ quá trình đổi authorization code. Nó không ngăn mã độc chạy trong trang lấy token sau khi đăng nhập, không thay thế bảo vệ XSS và không biến SPA thành confidential client.

## 6. Cấu hình OAuth2 trong OpenAPI cho public client

OpenAPI mô tả authorization flow và scope mà API hỗ trợ. Với ứng dụng browser, có thể mô tả Authorization Code flow mà không khai báo client secret.

Ví dụ annotation trong springdoc:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "browserOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Đọc thông tin sản phẩm."
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo đơn hàng."
                )
            }
        )
    )
)
public class BrowserOAuthConfiguration {
}
~~~

Scheme mô tả flow, URL và scope. OpenAPI không cần và không nên chứa client secret. client_id là giá trị công khai mà Swagger UI có thể cần để bắt đầu authorization flow; secret không được đưa vào tài liệu.

Nếu API hỗ trợ OIDC, có thể mô tả thêm scheme openIdConnect trỏ tới discovery document. Việc khai báo OIDC scheme không làm cho ID token trở thành token gọi API; resource server vẫn phải nhận và xác minh access token.

## 7. Cấu hình Swagger UI an toàn với PKCE

Swagger UI chạy trong browser nên cũng là một public client. Nếu người tích hợp cần dùng nút Authorize để thử API theo Authorization Code flow, có thể cấu hình client ID và bật PKCE:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      use-pkce-with-authorization-code-grant: true
~~~

store-swagger-ui là client ID công khai đã đăng ký với authorization server. Redirect URI của Swagger UI phải được đăng ký chính xác. Tùy context path và cấu hình triển khai, callback thường nằm ở đường dẫn swagger-ui/oauth2-redirect.html.

Không thêm thuộc tính client-secret vào cấu hình Swagger UI cho ứng dụng browser. Cũng không gọi hàm khởi tạo OAuth của Swagger UI với clientSecret chứa credential thật. Cấu hình được tải xuống browser và có thể bị đọc bởi người sử dụng.

Ví dụ cấu hình không an toàn:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      client-secret: do-not-put-a-real-secret-here
~~~

Ngay cả khi giá trị được thay thế từ biến môi trường server trong lúc khởi động, nếu Springdoc đưa nó vào cấu hình JavaScript được gửi tới browser thì secret vẫn bị lộ. Không có cách khắc phục bằng cách đổi tên property hoặc mã hóa secret trong file cấu hình.

Với Swagger UI, hãy xác nhận:

- Client đã đăng ký là public client nếu chạy trực tiếp trong browser.
- Authorization Code flow được khai báo đúng.
- PKCE được bật và authorization server chấp nhận S256.
- Redirect URI trùng chính xác với URI đã đăng ký.
- Chỉ client ID và scope cần thiết xuất hiện ở browser.
- Không có client secret trong cấu hình, source map, bundle hoặc network request.

## 8. Khi nào nên dùng Backend-for-Frontend (BFF)?

BFF là backend được thiết kế riêng để phục vụ một frontend. Browser gửi request đến BFF; BFF quản lý OAuth session và thực hiện các lời gọi đến authorization server hoặc resource API ở phía server.

Kiến trúc:

~~~text
Browser
   |
   | session cookie
   v
BFF (confidential client)
   |             \
   |              \ client authentication
   |               v
   |        Authorization Server
   |               |
   |<-------------- access / refresh token (server-side)
   |
   | bearer access token
   v
Resource API
~~~

BFF hữu ích khi:

- Không muốn access token hoặc refresh token xuất hiện trong JavaScript.
- Cần dùng confidential client authentication.
- Muốn tập trung quản lý refresh token, session, logout và thu hồi token.
- Muốn browser chỉ giữ cookie phiên đăng nhập.
- Muốn giới hạn API mà frontend có thể gọi thông qua một lớp backend.

Trong mô hình BFF, cookie phiên thường nên có các thuộc tính HttpOnly, Secure và SameSite phù hợp. Vì browser tự gửi cookie, BFF cần thiết kế chống CSRF, ví dụ kiểm tra Origin/Referer, dùng CSRF token khi cần và giới hạn các phương thức thay đổi dữ liệu.

BFF làm giảm việc lộ token cho JavaScript, nhưng không loại bỏ mọi rủi ro XSS. Script độc hại vẫn có thể gửi request thay mặt người dùng trong phiên đang mở. Cần kết hợp Content Security Policy, output encoding, kiểm soát dependency và bảo vệ session.

## 9. Lưu client secret ở backend

Nếu backend là confidential client, secret phải được nạp từ nguồn cấu hình được bảo vệ tại runtime. Có thể dùng secret manager của nền tảng, vault hoặc cơ chế quản lý credential tương đương.

Ví dụ cấu hình Spring Boot ở phía server:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            client-id: store-bff
            client-secret: ${OAUTH_PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - products.read
        provider:
          partner:
            issuer-uri: https://id.example.com
~~~

Placeholder OAUTH_PARTNER_CLIENT_SECRET được giải quyết trong tiến trình backend. Không đặt file cấu hình chứa secret vào thư mục static frontend, không copy giá trị đó vào bundle và không cung cấp endpoint trả lại toàn bộ cấu hình cho browser.

Trong production:

- Phân quyền đọc secret chỉ cho workload cần sử dụng.
- Không commit secret vào Git, Docker image hoặc artifact frontend.
- Không ghi secret vào log, exception, trace hoặc cấu hình Actuator có thể truy cập công khai.
- Có quy trình xoay vòng và thu hồi credential.
- Dùng credential riêng cho từng môi trường và từng ứng dụng.
- Hạn chế quyền của client theo scope và policy cần thiết.

Biến môi trường backend có thể là một cách inject secret, nhưng cần bảo vệ quyền đọc tiến trình, crash dump và hệ thống vận hành. Secret manager chuyên dụng thường phù hợp hơn cho hệ thống production.

## 10. Token trong browser: chọn mô hình lưu trữ

Không chỉ client secret mới cần bảo vệ. Access token và refresh token cũng là credential có thể bị lạm dụng nếu bị đánh cắp.

| Vị trí | JavaScript có thể đọc? | Rủi ro chính |
|---|---|---|
| Biến trong bộ nhớ ứng dụng | Có | XSS có thể đọc hoặc dùng token khi ứng dụng đang chạy |
| localStorage | Có | Token tồn tại lâu và script cùng origin có thể đọc |
| sessionStorage | Có | Script cùng origin có thể đọc; dữ liệu thường tồn tại trong phiên tab |
| IndexedDB | Có | Script cùng origin có thể đọc dữ liệu |
| Cookie HttpOnly | Không đọc trực tiếp bằng JavaScript | Browser tự gửi cookie; cần xử lý CSRF và cấu hình cookie đúng |
| Kho token phía server/BFF | Browser không truy cập trực tiếp | Cần bảo vệ backend, session và kênh kết nối |

Với SPA gọi API trực tiếp, nên giảm thời gian tồn tại của token trong browser và ưu tiên giữ access token trong bộ nhớ khi kiến trúc cho phép. Tránh lưu refresh token dài hạn trong localStorage. Nếu authorization server hỗ trợ refresh token cho public client, cần chính sách rotation hoặc sender-constrained token phù hợp và phát hiện việc tái sử dụng token đã bị xoay vòng.

Không có nơi lưu trữ phía browser nào làm cho token hoàn toàn an toàn trước XSS đang chạy trong origin của ứng dụng. Mục tiêu là giảm khả năng lấy cắp, giảm thời gian lạm dụng và giới hạn quyền token.

## 11. Bảo vệ ứng dụng khỏi XSS và CSRF

XSS cho phép mã độc chạy trong origin của ứng dụng. Khi đó, script có thể đọc dữ liệu JavaScript truy cập được, gọi API thay mặt người dùng và thao tác trên giao diện. PKCE không ngăn được loại tấn công này sau khi phiên đã được thiết lập.

Các biện pháp quan trọng:

- Escape hoặc encode dữ liệu không tin cậy theo đúng ngữ cảnh hiển thị.
- Tránh đưa chuỗi không tin cậy vào innerHTML hoặc API thực thi mã.
- Dùng Content Security Policy nghiêm ngặt, tránh unsafe-inline và unsafe-eval khi có thể.
- Giới hạn script bên thứ ba và rà soát dependency frontend.
- Cân nhắc Trusted Types khi nền tảng trình duyệt và ứng dụng hỗ trợ.
- Không lưu secret hoặc token trong log frontend, URL hay query parameter.
- Dùng HTTPS cho toàn bộ luồng đăng nhập và API.

CSRF chủ yếu cần được xem xét khi browser tự động gửi credential, đặc biệt là cookie phiên. BFF nên kiểm tra nguồn request và dùng cơ chế CSRF phù hợp. Cấu hình SameSite hỗ trợ giảm rủi ro nhưng không nên được xem là biện pháp duy nhất cho mọi mô hình triển khai.

## 12. So sánh SPA trực tiếp với BFF

Hai kiến trúc có thể hợp lệ tùy yêu cầu:

| Tiêu chí | SPA + Authorization Code + PKCE | BFF + confidential client |
|---|---|---|
| Client secret | Không sử dụng | Giữ ở backend |
| Nơi nhận access token | Browser | Backend |
| Browser gọi resource API | Trực tiếp, kèm access token | Thường gọi BFF |
| Quản lý refresh token | Phải thiết kế cẩn thận cho public client | Có thể giữ phía server |
| CSRF | Phụ thuộc credential và cách gửi request | Cần chú ý vì cookie phiên tự động được gửi |
| Hạ tầng | Ít thành phần backend hơn | Cần vận hành BFF và session |
| Phù hợp | SPA độc lập, API cho public client | Ứng dụng cần giữ token/credential phía server |

Chọn SPA trực tiếp khi có thể dùng public client với PKCE và chấp nhận quản lý token trong browser. Chọn BFF khi cần confidential client, không muốn token xuất hiện trong JavaScript hoặc cần tập trung hóa việc quản lý phiên và token.

## 13. Mô tả BFF và public client trong hợp đồng OpenAPI

OpenAPI nên phản ánh credential mà client thực sự dùng để gọi API.

Với SPA gọi resource API trực tiếp, có thể mô tả OAuth2 Authorization Code:

~~~yaml
components:
  securitySchemes:
    browserOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://id.example.com/oauth2/authorize
          tokenUrl: https://id.example.com/oauth2/token
          scopes:
            products.read: Đọc sản phẩm.
paths:
  /api/v1/products:
    get:
      security:
        - browserOAuth:
            - products.read
      responses:
        '200':
          description: Danh sách sản phẩm.
~~~

Không thêm client_secret vào components, securitySchemes, extension hoặc ví dụ request. OpenAPI mô tả flow và scope; thông tin xác thực cụ thể của client được quản lý theo môi trường đăng ký client.

Với BFF dùng cookie phiên, tài liệu dành cho browser có thể mô tả cookie/session authentication theo security scheme phù hợp hoặc mô tả cơ chế session ở cấp API. Confidential client authentication giữa BFF và authorization server là giao tiếp server-to-server, thường không phải credential mà browser cần biết.

## 14. Những cấu hình cần tránh trong springdoc và Swagger UI

Các cấu hình sau có nguy cơ làm lộ credential nếu được gửi tới browser:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      client-secret: do-not-put-a-real-secret-here
~~~

Không dùng client-secret trong Swagger UI khi UI chạy ở browser. Tương tự, tránh các cách làm sau:

- Đưa secret vào @Value rồi gán vào JavaScript config của Swagger UI.
- Đưa secret vào index.html, application.js hoặc file JSON frontend.
- Dùng customizer để thêm secret vào OpenAPI extension hoặc description.
- Trả secret từ backend qua endpoint cấu hình frontend.
- Đặt secret trong biến VITE_, REACT_APP_, NEXT_PUBLIC_ hoặc biến tương đương.
- Ghi secret trong ví dụ curl, Postman collection public hoặc file HAR.

Nếu Swagger UI cần đăng nhập để thử API, hãy đăng ký một public client riêng cho Swagger UI, bật Authorization Code + PKCE và giới hạn redirect URI. Nếu cần confidential client, hãy đặt luồng lấy token trong backend được kiểm soát.

## 15. CORS không làm client secret an toàn

CORS quyết định browser có được phép cho JavaScript đọc response từ một origin khác hay không. Nó không biến credential đã nhúng trong frontend thành bí mật.

Ngay cả khi authorization server chỉ cho phép một origin cụ thể qua CORS, người dùng vẫn có thể xem bundle và đọc secret. Họ cũng có thể gửi request từ một công cụ ngoài browser nếu đã lấy được credential.

CORS cần được cấu hình để cho phép đúng origin, method và header mà ứng dụng cần. Không dùng CORS như cơ chế xác thực client hoặc biện pháp bảo vệ client secret.

## 16. Nếu secret đã bị đưa vào frontend thì xử lý thế nào?

Khi một client secret đã xuất hiện trong bundle, repository công khai, source map hoặc request từ browser, hãy xem credential đó đã bị lộ.

Các bước xử lý:

1. Thu hồi hoặc rotate secret tại authorization server.
2. Phát hành credential mới cho backend hoặc confidential client hợp lệ.
3. Xóa secret khỏi frontend source và cấu hình build.
4. Kiểm tra bundle, source map, artifact, cache CDN, log và hệ thống giám sát để xác định phạm vi rò rỉ.
5. Kiểm tra log authorization server để tìm hoạt động bất thường nếu có.
6. Rà soát lịch sử Git và pipeline để ngăn secret tiếp tục xuất hiện.
7. Cập nhật quy trình phát hành và quét secret tự động.

Xóa secret khỏi commit mới không làm credential cũ mất hiệu lực. Cần thu hồi hoặc rotate tại nơi phát hành credential trước, sau đó mới làm sạch các bản sao và lịch sử lưu trữ theo chính sách tổ chức.

## 17. Ví dụ cấu hình hai mô hình

### 17.1. SPA public client dùng PKCE

Đăng ký client trên authorization server:

~~~text
Client type: Public
Grant: Authorization Code
PKCE: Required (S256)
Client ID: store-spa
Client secret: Không cấp
Redirect URI: https://app.example.com/auth/callback
Allowed scopes: openid, profile, products.read
~~~

Frontend chỉ sử dụng client ID:

~~~javascript
const oauthConfig = {
  clientId: "store-spa",
  authorizationUrl: "https://id.example.com/oauth2/authorize",
  tokenUrl: "https://id.example.com/oauth2/token",
  redirectUri: "https://app.example.com/auth/callback",
  scopes: ["openid", "profile", "products.read"]
};
~~~

Thư viện OIDC/OAuth2 phía browser nên tự sinh verifier, challenge, state và nonce theo chuẩn. Không tự viết thuật toán ngẫu nhiên bằng Math.random() hoặc tự xử lý token nếu thư viện đáng tin cậy đã cung cấp quy trình chuẩn.

### 17.2. BFF confidential client

Đăng ký ứng dụng backend:

~~~text
Client type: Confidential
Grant: Authorization Code
Client ID: store-bff
Client secret: Lưu ở secret manager phía server
Redirect URI: https://app.example.com/login/oauth2/code/partner
~~~

Backend nhận secret từ cấu hình runtime:

~~~yaml
app:
  oauth:
    client-id: store-bff
    client-secret: ${OAUTH_BFF_CLIENT_SECRET}
~~~

Frontend chỉ nhận cookie phiên do BFF phát hành. Không trả client-secret, access token hoặc refresh token về JavaScript. Cookie cần được cấu hình HttpOnly, Secure, SameSite và thời hạn phù hợp với mô hình session.

Các giá trị URL và client ID trong hai ví dụ chỉ minh họa. Khi triển khai, phải đăng ký đúng redirect URI, origin và scope theo authorization server thực tế.

## 18. Kiểm tra tài liệu OpenAPI và cấu hình frontend

Sau khi chạy ứng dụng, kiểm tra tài liệu được springdoc sinh ra:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra:

- Security scheme dùng đúng loại oauth2 và flow authorizationCode cho public browser client.
- Authorization URL, token URL và scope khớp cấu hình authorization server.
- Không có client secret trong OpenAPI JSON/YAML, extension hoặc description.
- Security requirement gắn đúng scope cho từng operation.
- Swagger UI chỉ có client ID công khai và bật PKCE.
- Redirect URI của Swagger UI đã được đăng ký chính xác.
- Không có secret trong static bundle, source map hoặc request từ browser.

Kiểm tra bundle frontend sau build bằng cách tìm các tên biến hoặc giá trị nhạy cảm đã biết. Việc tìm chuỗi chỉ là một lớp kiểm tra; cần rà soát cả source map, cấu hình runtime được tải về và request trong Network panel.

Kiểm tra backend:

- Client secret chỉ được đọc bởi tiến trình backend có thẩm quyền.
- Secret không xuất hiện trong log, exception hoặc endpoint cấu hình.
- Token được lưu và xử lý theo chính sách của BFF.
- Session cookie có thuộc tính bảo vệ phù hợp.
- CSRF được xử lý nếu browser tự động gửi cookie.
- Credential có quy trình rotate và revoke.

## 19. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Nhúng client secret vào JavaScript | Người dùng có thể trích xuất và giả mạo client | Dùng public client với PKCE hoặc BFF |
| Đặt secret trong biến môi trường frontend | Giá trị bị đóng gói vào client bundle | Chỉ đưa secret vào môi trường backend |
| Dùng Client Credentials từ SPA | Credential xác thực client bị lộ | Chuyển flow này sang backend/service |
| Nghĩ minify hoặc obfuscate bảo vệ secret | Secret vẫn có thể được tìm thấy lúc runtime | Không phát hành secret cho browser |
| Bật PKCE nhưng vẫn gửi client secret | Vẫn để lộ credential không cần thiết | Đăng ký public client và bỏ secret |
| Lưu refresh token lâu dài trong localStorage | XSS có thể lấy token và duy trì quyền truy cập | Dùng BFF hoặc chính sách token public-client phù hợp |
| Dùng CORS để bảo vệ secret | CORS không ngăn người dùng đọc bundle | Bảo vệ credential bằng kiến trúc server-side |
| Dùng ID token gọi resource API | Token có thể sai audience và mục đích | Dùng access token dành cho API |
| Chỉ xóa secret khỏi Git mà không rotate | Credential cũ vẫn có thể bị lạm dụng | Thu hồi/rotate trước, sau đó làm sạch bản sao |
| Cấu hình client secret cho Swagger UI | Secret được gửi tới browser | Dùng client ID + PKCE cho Swagger UI |

## 20. Ghi nhớ

- Browser SPA là public client vì người dùng có thể kiểm tra mã và runtime.
- client_id thường công khai; client_secret phải được giữ ở môi trường server có thể kiểm soát.
- Biến môi trường frontend và file .env được dùng khi build không phải kho bí mật.
- Không dùng Client Credentials trực tiếp từ browser.
- Authorization Code + PKCE là lựa chọn phù hợp cho public browser client.
- PKCE bảo vệ việc đổi authorization code, không thay thế phòng chống XSS.
- BFF có thể giữ client secret, access token và refresh token phía server.
- Cookie HttpOnly, Secure, SameSite cần đi cùng thiết kế session và CSRF phù hợp.
- Swagger UI chạy trong browser nên không được cấu hình client secret.
- CORS, minify và obfuscation không biến secret công khai thành bí mật.
- Nếu secret đã lộ, hãy thu hồi hoặc rotate credential; xóa khỏi bundle hay Git không đủ.
- OpenAPI mô tả flow và scope, còn backend/authorization server thực thi xác thực và ủy quyền.

Khi thiết kế OAuth2/OIDC cho ứng dụng chạy trên trình duyệt, hãy xem frontend là public client và không cấp cho nó client secret. Dùng Authorization Code với PKCE khi browser gọi API trực tiếp; dùng BFF khi cần confidential client hoặc muốn giữ token ở server. Tài liệu springdoc-openapi và Swagger UI phải phản ánh đúng kiến trúc đó, không công bố credential nhạy cảm.
