# Lưu trạng thái xác thực trên giao diện và rủi ro trên máy dùng chung

Swagger UI có nút Authorize để người phát triển nhập API key, Basic credentials, Bearer token hoặc thực hiện OAuth flow trước khi gọi API bằng Try it out. Theo mặc định, trạng thái xác thực chỉ tồn tại trong phiên Swagger UI hiện tại. Khi bật tùy chọn persistAuthorization, Swagger UI giữ authorization data qua refresh và cả khi đóng rồi mở lại trình duyệt.

Tính năng này tiện cho máy phát triển cá nhân, nhưng có rủi ro rõ rệt trên máy dùng chung. Người tiếp theo mở Swagger UI trong cùng browser profile có thể nhìn thấy trạng thái Authorize còn hiệu lực và gửi request bằng quyền của người trước. Vì vậy, cần hiểu dữ liệu được giữ ở đâu, nó khác gì với cookie/session của server, và cách tắt hoặc dọn trạng thái đúng cách.

## 1. Authorize trong Swagger UI lưu những gì?

OpenAPI document mô tả security scheme mà API hỗ trợ. Swagger UI dùng metadata đó để hiển thị hộp thoại Authorize. Người dùng có thể nhập:

- API key được gửi qua header hoặc query parameter.
- HTTP Basic username/password.
- Bearer token, thường là access token dạng JWT hoặc opaque token.
- OAuth 2.0 authorization result.
- OpenID Connect authorization result.

Sau khi người dùng authorize, Swagger UI giữ authorization state để gắn credential phù hợp vào các request Try it out. Đây là trạng thái phía trình duyệt. Nó không phải phiên đăng nhập do Spring Security quản lý và cũng không thay thế authorization ở server.

~~~mermaid
flowchart TD
    A["Người dùng mở Swagger UI"] --> B["Authorize"]
    B --> C["Nhập API key / Basic / Bearer / OAuth"]
    C --> D["Swagger UI giữ authorization state"]
    D --> E{"persistAuthorization"}
    E -->|false| F["Chỉ giữ trong UI runtime"]
    E -->|true| G["Lưu trạng thái vào browser storage"]
    F --> H["Try it out gửi request"]
    G --> H
    H --> I["Spring Security / API kiểm tra credential"]
    I --> J["Cho phép hoặc từ chối request"]
~~~

Credential được Swagger UI gắn vào request không tự động được server tin cậy. Mỗi request vẫn phải qua authentication, authorization, scope/role check và các chính sách bảo mật của API.

## 2. persistAuthorization hoạt động thế nào?

Swagger UI cung cấp cấu hình:

~~~javascript
SwaggerUIBundle({
    url: "/v3/api-docs",
    dom_id: "#swagger-ui",
    persistAuthorization: false
});
~~~

Ý nghĩa:

| Giá trị | Hành vi |
|---|---|
| false | Không giữ authorization data qua lần tải lại giao diện; đây là mặc định |
| true | Giữ authorization data để không mất sau refresh hoặc đóng/mở lại trình duyệt |

springdoc chuyển tùy chọn Swagger UI thành Spring Boot property:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

Hoặc trong application.properties:

~~~properties
springdoc.swagger-ui.persistAuthorization=false
~~~

Khi bật:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: true
~~~

Tài liệu Swagger UI ghi rõ mặc định là false. springdoc cũng ghi cùng default và mô tả rằng authorization data sẽ không bị mất khi đóng hoặc refresh browser nếu bật true. Hãy kiểm tra property reference của đúng nhánh springdoc đang chạy nếu dự án dùng một phiên bản cũ.

## 3. Dữ liệu được lưu trong browser storage

Trong Swagger UI, persistAuthorization sử dụng cơ chế lưu trữ phía trình duyệt để khôi phục authorization state. Với triển khai Swagger UI hiện hành, trạng thái này được lưu bền qua browser session bằng localStorage.

localStorage có các đặc điểm:

- Dữ liệu gắn với origin, tức scheme, host và port.
- Các trang cùng origin có thể truy cập cùng vùng localStorage.
- Dữ liệu vẫn còn sau refresh, đóng tab và đóng/mở lại browser.
- Dữ liệu không tự hết hạn theo thời gian như access token.
- JavaScript chạy trong cùng origin có thể đọc dữ liệu.

Ví dụ, hai URL sau là hai origin khác nhau vì scheme khác nhau:

~~~text
http://docs.example.com
https://docs.example.com
~~~

Hai ứng dụng sau cùng origin nếu cùng scheme, host và port:

~~~text
https://tools.example.com/swagger-ui/
https://tools.example.com/admin/
~~~

Đường dẫn khác nhau không tạo vùng localStorage riêng. Nếu cùng origin, JavaScript của một ứng dụng có thể truy cập storage chung theo quy tắc same-origin.

localStorage không phải kho bí mật được mã hóa. Không nên giả định token đã được hash, mã hóa hoặc bảo vệ bằng mật khẩu máy tính. Bất kỳ script nào thực thi được trong origin đều có thể đọc dữ liệu mà origin đó được phép truy cập.

## 4. So sánh memory, localStorage, sessionStorage và cookie

| Cơ chế | Thời gian tồn tại | Phạm vi | JavaScript đọc được? |
|---|---|---|---|
| UI memory | Trong vòng đời trang hiện tại | Instance Swagger UI | Có, qua mã ứng dụng đang chạy |
| localStorage | Qua refresh và browser restart cho đến khi bị xóa | Cùng origin | Có |
| sessionStorage | Trong page session; thường bị xóa khi tab đóng | Cùng origin và tab | Có |
| Cookie HttpOnly | Theo expiry/session cookie | Domain/path và cookie policy | Không đọc trực tiếp bằng JavaScript |
| Session phía server | Theo timeout và chính sách server | Theo session identifier | Server quản lý trạng thái |

Không được nhầm persistAuthorization với sessionStorage. Tài liệu Swagger UI mô tả persistAuthorization là giữ authorization data qua browser close/refresh; cấu hình chuẩn của tính năng này không phải một tùy chọn chuyển sang sessionStorage.

springdoc có các property use-local-storage và use-session-storage cho CSRF token. Chúng điều khiển nơi Swagger UI lấy CSRF token; chúng không thay thế hoặc thay đổi cơ chế persistAuthorization cho credential.

## 5. Rủi ro trên máy dùng chung

Giả sử một kỹ sư authorize bằng access token có quyền quản trị trên máy ở phòng lab. Sau khi họ đóng tab, người khác đăng nhập vào cùng browser profile và mở lại Swagger UI trên cùng origin. Nếu persistAuthorization vẫn bật và dữ liệu chưa bị xóa, Swagger UI có thể khôi phục credential cũ.

Các rủi ro chính:

### Người dùng tiếp theo kế thừa quyền của người trước

Người dùng sau có thể gọi endpoint bằng token còn hiệu lực. Họ không cần biết mật khẩu hoặc token ban đầu nếu Swagger UI đã tự khôi phục authorization state.

### Token tồn tại lâu hơn thời gian người dùng nghĩ

Đóng tab hoặc đóng browser không xóa localStorage. Token có thể còn cho đến khi bị xóa, bị ghi đè hoặc bị giới hạn bởi chính sách browser/storage.

### XSS hoặc script cùng origin đọc credential

Nếu một lỗ hổng Cross-Site Scripting cho phép chạy JavaScript trong origin của Swagger UI, script độc hại có thể đọc authorization data trong localStorage rồi gửi ra ngoài. CSP và kiểm soát dependency giảm rủi ro XSS nhưng không biến localStorage thành kho bí mật.

### Người có quyền truy cập browser profile đọc dữ liệu

Máy dùng chung có thể cho nhiều người truy cập cùng profile hoặc tài khoản hệ điều hành. Người có quyền truy cập profile có thể đọc dữ liệu browser được lưu trên máy.

### Ứng dụng khác cùng origin dùng chung storage

Nếu Swagger UI và ứng dụng khác cùng scheme, host, port, một script trong cùng origin có thể truy cập cùng localStorage. Tách path không phải biện pháp cô lập storage.

### Credential còn quyền dù giao diện đã đóng

Swagger UI không kiểm soát thời hạn của token do authorization server cấp. Token vẫn có thể được sử dụng bởi bất kỳ client nào cho đến khi hết hạn hoặc bị server/authorization server từ chối.

## 6. Không nhầm trạng thái Swagger UI với cookie/session

persistAuthorization quản lý authorization data mà Swagger UI sử dụng cho các request của giao diện. Nó không tự động điều khiển mọi loại đăng nhập của browser.

Ví dụ, nếu API dùng cookie session:

- Browser có thể tự gửi session cookie theo domain, path, SameSite, Secure và credential mode.
- Cookie HttpOnly không thể được JavaScript đọc trực tiếp.
- Cookie session có thể vẫn tồn tại dù Swagger UI không giữ Bearer token.
- Tắt persistAuthorization không đồng nghĩa server đã logout hoặc browser đã xóa cookie.

Nếu hệ thống dùng Spring Security session login, cần có logout endpoint và timeout/invalidation phía server. Nếu dùng bearer token, cần có expiry/revocation/introspection policy phù hợp.

Tương tự, nút Logout trong hộp thoại Authorize của Swagger UI xóa authorization state khỏi giao diện và phần lưu trữ tương ứng của Swagger UI. Thao tác này không tự động gọi OAuth revocation endpoint, không vô hiệu hóa JWT đã phát hành và không kết thúc session ở hệ thống khác.

## 7. Chính sách khuyến nghị cho máy dùng chung

Với máy công cộng, máy phòng lab, máy demo, máy kiosk hoặc workstation dùng chung:

1. Giữ persistAuthorization ở false.
2. Không pre-authorize bằng token quản trị hoặc credential production.
3. Dùng tài khoản thử nghiệm có quyền tối thiểu.
4. Cấp access token ngắn hạn và scope hẹp.
5. Không lưu client secret trong cấu hình Swagger UI.
6. Khi kết thúc, dùng Logout trong hộp thoại Authorize.
7. Đăng xuất khỏi ứng dụng và identity provider nếu đã đăng nhập qua SSO.
8. Xóa site data của đúng origin nếu máy sẽ được bàn giao cho người khác.
9. Đóng browser profile hoặc đăng xuất tài khoản hệ điều hành theo quy trình của đơn vị.

Không coi việc đóng tab là thao tác xóa credential. Với localStorage, dữ liệu có thể vẫn còn sau khi tab và browser đóng.

### Bảng quyết định

| Môi trường | persistAuthorization | Chính sách |
|---|---|---|
| Máy công cộng/phòng lab | false | Bắt buộc tắt |
| Máy demo dùng chung | false | Tắt và dùng token thử nghiệm |
| Máy cá nhân của kỹ sư | false theo mặc định | Chỉ cân nhắc bật nếu có nhu cầu và kiểm soát được profile |
| Staging có nhiều người dùng | false | Không chia sẻ authorization state |
| Production | false | Thường nên tắt Swagger UI hoặc bảo vệ chặt |
| CI/export OpenAPI | Không cần | Tắt Swagger UI nếu pipeline chỉ cần document |

## 8. Cấu hình an toàn trong Spring Boot

### Cấu hình mặc định

Đặt false rõ ràng trong cấu hình chung để người đọc thấy chủ đích:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    persist-authorization: false
~~~

Việc khai báo tường minh giúp tránh một profile khác vô tình bật persistence mà không được review.

### Profile production

Nếu production không cần Swagger UI hoặc OpenAPI endpoint, có thể tắt riêng cả hai:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
    persist-authorization: false
~~~

Tắt Swagger UI không tự động tắt OpenAPI JSON/YAML endpoint. Tắt API docs cũng không thay thế security policy cho các REST endpoint nghiệp vụ. Xác minh cả hai đường dẫn sau khi deploy.

Nếu production cần tài liệu nội bộ, giữ UI và API docs trong vùng được bảo vệ bởi Spring Security hoặc gateway, giới hạn người dùng theo role và không bật persistence trên workstation dùng chung.

### Profile máy cá nhân riêng biệt

Nếu một nhóm kỹ sư thực sự cần giữ trạng thái qua refresh trên máy cá nhân được quản lý riêng, có thể bật trong profile riêng:

~~~yaml
# application-personal-dev.yml
springdoc:
  swagger-ui:
    persist-authorization: true
~~~

Chỉ dùng cấu hình này khi browser profile không được chia sẻ, máy được khóa khi rời chỗ, token có quyền tối thiểu và thời hạn ngắn, và người dùng hiểu cách logout/xóa site data. Không đưa profile này vào cấu hình mặc định hoặc profile dùng chung.

Không bật persistence chỉ để tránh nhập token thường xuyên. Hãy cân nhắc thời gian sống của token, quyền của token và mức độ nhạy cảm của API trước.

## 9. OAuth 2.0, OpenID Connect và client secret

Swagger UI chạy trong browser, vì vậy nó là một public client. Mọi cấu hình gửi tới browser đều có thể được người dùng xem.

### Không nhúng client secret production

springdoc có property cấu hình OAuth client secret, nhưng tài liệu cảnh báo không sử dụng nó trong production vì sẽ làm lộ thông tin bảo mật quan trọng.

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: swagger-ui-public-client
      # Không cấu hình client-secret production trong browser
      use-pkce-with-authorization-code-grant: true
~~~

Với OAuth authorization code flow cho public client, dùng Proof Key for Code Exchange (PKCE) khi authorization server hỗ trợ. PKCE bảo vệ authorization code exchange; nó không mã hóa token được lưu bởi persistAuthorization và không ngăn JavaScript cùng origin đọc token.

### Hạn chế token

- Chỉ yêu cầu scope cần cho thao tác thử nghiệm.
- Dùng access token có thời hạn ngắn.
- Không lưu refresh token trong Swagger UI nếu không có thiết kế bảo vệ rõ ràng.
- Không dùng token production có quyền rộng cho việc thử API.
- Không ghi token vào URL, query string, log, screenshot hoặc ticket.
- Cấu hình authorization server để thu hồi token/session khi cần.

Token ngắn hạn giảm khoảng thời gian bị lạm dụng nếu lộ, nhưng không thay thế việc xóa storage và thu hồi credential.

## 10. Logout và thu hồi token là hai thao tác khác nhau

Khi người dùng chọn Logout trong hộp thoại Authorize:

- Swagger UI bỏ authorization state của security scheme tương ứng.
- Nếu persistence đang bật, Swagger UI xử lý phần state được lưu để đăng nhập không tự khôi phục lại ở lần tải sau.
- Các request Try it out tiếp theo không còn dùng credential vừa logout trong UI.

Tuy nhiên:

- Access token đã phát hành có thể vẫn hợp lệ.
- Refresh token có thể vẫn hợp lệ nếu authorization server chưa thu hồi.
- Session SSO có thể vẫn đang hoạt động.
- Cookie session của ứng dụng có thể vẫn còn trong browser.

Quy trình kết thúc phiên đầy đủ tùy loại authentication:

| Loại xác thực | Thao tác cần làm |
|---|---|
| API key | Logout khỏi UI và thu hồi/rotate key ở hệ thống cấp key nếu bị lộ |
| Bearer access token | Logout khỏi UI; chờ expiry hoặc revoke theo cơ chế server |
| OAuth 2.0 | Logout khỏi UI; gọi revocation endpoint nếu cần thu hồi token; logout authorization server theo policy |
| OIDC SSO | Kết thúc phiên ứng dụng và thực hiện provider logout nếu cần |
| Cookie session | Gọi logout endpoint của ứng dụng để invalidate session; xóa cookie theo policy |

Đối với JWT stateless, xóa token khỏi browser không làm JWT mất hiệu lực trên server. Nếu cần thu hồi trước thời hạn, hệ thống phải có cơ chế như denylist, token introspection hoặc chiến lược key/session phù hợp.

## 11. Dọn authorization data trên máy dùng chung

Thực hiện theo thứ tự:

1. Trong Swagger UI, mở Authorize và chọn Logout cho từng security scheme đang được authorize.
2. Logout khỏi ứng dụng và identity provider nếu đã đăng nhập bằng SSO.
3. Mở cài đặt site data hoặc Developer Tools của browser.
4. Chọn đúng origin của Swagger UI.
5. Xóa site data/local storage theo quy trình quản trị browser của đơn vị.
6. Tải lại Swagger UI và xác minh nút Authorize không còn trạng thái đã xác thực.
7. Thử một request yêu cầu xác thực; request phải bị từ chối cho đến khi nhập credential mới.

Trong Chrome/Edge DevTools, có thể mở Application, xem Storage và Local Storage của đúng origin. Không copy giá trị token ra clipboard, ticket hoặc log để chứng minh đã xóa. Chỉ kiểm tra sự tồn tại của authorization record hoặc trạng thái UI.

Xóa toàn bộ site data của một origin có thể đồng thời xóa cookie, local storage, IndexedDB và dữ liệu khác của ứng dụng cùng origin. Nếu nhiều ứng dụng cùng origin, cần phối hợp với quản trị viên trước khi xóa toàn bộ dữ liệu.

Không dựa vào việc xóa một key localStorage có tên cố định nếu chưa kiểm tra đúng phiên bản Swagger UI. Chi tiết key và cấu trúc serialized state là implementation detail có thể thay đổi. Ưu tiên nút Logout và công cụ Clear site data theo đúng origin.

### Incognito/Private browsing

Private browsing có storage riêng với phiên duyệt riêng. Theo hành vi browser phổ biến, dữ liệu private localStorage bị xóa khi đóng tab private cuối cùng. Tuy nhiên, đây không phải lý do để bật persistAuthorization trên máy công cộng:

- Credential vẫn có thể bị đọc khi private window còn mở.
- Người dùng khác có thể dùng cùng phiên private đang mở nếu máy không được giám sát.
- Browser extension hoặc script độc hại trong phiên vẫn có thể đọc dữ liệu cùng origin.
- Private mode không thay thế logout và token revocation.

## 12. Không nhầm CSRF storage với authorization persistence

springdoc có các cấu hình CSRF riêng:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
      use-local-storage: false
      use-session-storage: false
      cookie-name: XSRF-TOKEN
      header-name: X-XSRF-TOKEN
~~~

Các property use-local-storage và use-session-storage nói về nơi lấy CSRF token để gắn vào request. Chúng không quyết định nơi Swagger UI lưu Bearer token, API key hoặc OAuth authorization state.

Ví dụ:

- persist-authorization: điều khiển việc giữ authorization data qua reload.
- csrf.use-session-storage: lấy CSRF token từ sessionStorage.
- csrf.use-local-storage: lấy CSRF token từ localStorage.

Không bật CSRF local storage với suy nghĩ rằng nó sẽ chuyển Bearer token sang sessionStorage.

## 13. Hạn chế Try it out không xóa credential

Có thể tắt các method Try it out:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

Điều này ngăn Swagger UI gửi request Try it out cho mọi HTTP method. Các operation vẫn có thể được hiển thị trong document. Tùy chọn này hữu ích cho tài liệu chỉ đọc, nhưng nó không xóa authorization data đã lưu và không thay thế việc tắt persistAuthorization.

Tương tự, tắt Swagger UI không đồng nghĩa tắt API docs endpoint. Nếu không cần tài liệu ở production, cấu hình riêng cả springdoc.swagger-ui.enabled và springdoc.api-docs.enabled.

## 14. Tránh override cấu hình qua URL

Swagger UI có cơ chế nhận cấu hình từ nhiều nguồn. Không bật queryConfigEnabled để cho phép URL query string ghi đè các cấu hình bảo mật như persistAuthorization.

queryConfigEnabled có mặc định false. springdoc đánh dấu chức năng override cấu hình qua URL query string là legacy và cảnh báo bảo mật liên quan. Giữ tùy chọn này ở false; không cho người dùng thay đổi security-sensitive configuration bằng query string.

Không đặt token trong URL query parameter. URL có thể xuất hiện trong browser history, proxy log, analytics, referrer hoặc screenshot.

## 15. Kiểm tra cấu hình và hành vi thực tế

Không chỉ đọc application.yml. Cần xác minh effective configuration sau khi Spring Boot nạp profile, environment variable và config server.

### Kiểm tra cấu hình

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

Nếu có nhiều profile, tìm các override của:

- springdoc.swagger-ui.persistAuthorization
- springdoc.swagger-ui.enabled
- springdoc.api-docs.enabled
- springdoc.swagger-ui.oauth.clientSecret
- springdoc.swagger-ui.queryConfigEnabled

Đảm bảo profile production và profile shared-workstation không bật persistence.

### Kiểm tra trên browser

Trong môi trường test với credential giả:

1. Mở Swagger UI và authorize.
2. Thử refresh trang.
3. Nếu persistAuthorization=false, trạng thái Authorize không nên được khôi phục từ local storage.
4. Nếu thử true trên máy kiểm thử riêng, trạng thái có thể được khôi phục sau refresh và browser restart.
5. Chọn Logout rồi refresh; authorization state phải không còn được khôi phục.
6. Kiểm tra token không xuất hiện trong URL, console log hoặc application log.

Không chạy thử bằng token production thật. Không chụp hoặc lưu giá trị token từ DevTools.

## 16. Kiểm tra bằng DevTools mà không làm lộ token

Developer Tools có thể giúp xác nhận storage behavior:

- Chọn đúng origin của Swagger UI.
- Mở Application hoặc Storage.
- Xem Local Storage và Session Storage.
- Chỉ xác minh có/không có authorization state hoặc thay đổi sau Logout.
- Không mở rộng hoặc copy giá trị nhạy cảm.
- Sau kiểm tra, xóa site data của môi trường test.

Nếu cần kiểm tra tự động, dùng token giả và browser profile dùng một lần. Test có thể xác nhận rằng sau khi reload với persistAuthorization=false, nút Authorize trở về trạng thái chưa xác thực; không cần đọc hoặc assert giá trị token thật trong storage.

## 17. Chính sách cho CI và môi trường triển khai

CI chỉ cần OpenAPI JSON/YAML để validate hoặc publish artifact thường không cần Swagger UI:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
    persist-authorization: false
~~~

Môi trường production không phục vụ docs:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
    persist-authorization: false
~~~

Môi trường nội bộ có Swagger UI:

- Bảo vệ UI và API docs bằng Spring Security hoặc gateway.
- Giới hạn người dùng theo role.
- Giữ persistence tắt trên máy dùng chung.
- Không cấu hình client secret production trong JavaScript/browser.
- Dùng access token ngắn hạn, scope hẹp.
- Bật audit ở server cho các thao tác thử nghiệm có tác động.

Swagger UI chỉ là client. Nó không tự cấp quyền và không thay thế việc bảo vệ API endpoint.

## 18. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mở lại Swagger UI vẫn thấy Authorized | persistAuthorization đang bật và storage còn dữ liệu | Tắt property, Logout và dọn site data đúng origin |
| Đóng browser nhưng token vẫn còn | localStorage tồn tại qua browser restart | Không dùng đóng browser như biện pháp xóa |
| Người dùng khác gọi được API trên máy lab | Dùng chung browser profile/origin và auth state còn lưu | Tắt persistence, logout, clear site data và dùng profile riêng |
| Tắt persistAuthorization nhưng request vẫn có cookie | Cookie/session do browser quản lý độc lập | Logout server session và xóa cookie theo policy |
| Bấm Logout nhưng token vẫn gọi API được bằng curl | UI logout không thu hồi access token | Revoke token hoặc chờ expiry; kiểm tra server policy |
| Bật CSRF use-session-storage nhưng Bearer token vẫn được lưu | Hai property phục vụ hai loại dữ liệu khác nhau | Tắt persistAuthorization riêng |
| Swagger UI tự authorize sau reload | Có config preauthorization hoặc custom plugin ngoài persistAuthorization | Kiểm tra configUrl, init script và custom JavaScript |
| Token bị lộ trong console/log | Custom interceptor hoặc logging ghi request header | Redact Authorization, không log token |
| Client secret xuất hiện trong page source | Cấu hình OAuth clientSecret được gửi tới browser | Gỡ client secret; dùng public client và PKCE |
| Clear site data làm ứng dụng khác logout | Nhiều ứng dụng cùng origin dùng storage/cookie chung | Tách origin hoặc phối hợp phạm vi dọn dữ liệu |

## 19. Checklist trước khi dùng persistAuthorization

- [ ] Hiểu rằng mặc định persistAuthorization là false.
- [ ] Đã xác định credential nào được Swagger UI giữ.
- [ ] Đã xác định browser storage và phạm vi origin.
- [ ] Không bật persistence trên máy công cộng, phòng lab hoặc profile dùng chung.
- [ ] Không lưu token production hoặc credential có quyền rộng.
- [ ] Access token có thời hạn ngắn và scope tối thiểu.
- [ ] Không nhúng client secret vào cấu hình browser.
- [ ] PKCE được bật cho public OAuth client khi phù hợp.
- [ ] Cookie/session server được quản lý riêng với Swagger UI authorization state.
- [ ] Logout UI không bị nhầm với token revocation/server logout.
- [ ] Có quy trình clear site data khi bàn giao máy.
- [ ] CSRF storage không bị nhầm với authorization persistence.
- [ ] queryConfigEnabled không được bật để override security config.
- [ ] CI chỉ bật API docs nếu không cần UI.
- [ ] Production tắt hoặc bảo vệ cả Swagger UI và API docs theo policy.
- [ ] Kiểm thử reload/logout bằng token giả trên browser profile riêng.

## 20. Tài liệu tham khảo chính thức

- [Swagger UI Configuration – Authorization](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): persistAuthorization, default false và hành vi giữ authorization qua browser close/refresh.
- [Swagger UI issue 8711](https://github.com/swagger-api/swagger-ui/issues/8711): thảo luận upstream về việc persistAuthorization lưu authorization state vào localStorage.
- [springdoc Swagger UI Properties](https://springdoc.org/ui-properties.html): property springdoc.swagger-ui.persistAuthorization và CSRF storage options.
- [springdoc Configuration Properties](https://springdoc.org/properties.html): các property Swagger UI, queryConfigEnabled và cảnh báo OAuth client secret.
- [Swagger UI OAuth 2.0](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/): cấu hình OAuth flow và PKCE.
- [MDN Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API): khác biệt localStorage và sessionStorage.
- [MDN Window.localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage): phạm vi origin và persistence qua browser sessions.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): rủi ro lưu thông tin nhạy cảm trong Web Storage và XSS.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): khuyến nghị không lưu token/session ID/JWT/refresh token trong localStorage hoặc sessionStorage.
- [Spring Security Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout và invalidation phiên phía server.

## Kết luận

persistAuthorization giúp Swagger UI giữ trạng thái Authorize qua refresh và browser restart, nhưng làm credential tồn tại lâu hơn trong browser profile. Trên máy dùng chung, hãy giữ tùy chọn này ở false, dùng token thử nghiệm có scope hẹp và thời hạn ngắn, Logout khỏi UI lẫn hệ thống đăng nhập, rồi dọn site data của đúng origin khi bàn giao máy. Luôn phân biệt authorization state của Swagger UI với cookie/session và token do server cấp: xóa trạng thái giao diện không tự thu hồi token hay kết thúc phiên server. localStorage có thể được JavaScript cùng origin đọc, nên không xem nó là kho bí mật an toàn cho credential.
