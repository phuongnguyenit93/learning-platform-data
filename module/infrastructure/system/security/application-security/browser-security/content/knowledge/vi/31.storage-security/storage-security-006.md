# DevTools exposure: dữ liệu nào đang lộ trong browser và cách giảm rủi ro

## 1. DevTools exposure là gì?

**DevTools exposure** là việc dữ liệu, mã nguồn và trạng thái ứng dụng đã được đưa tới browser có thể được người đang kiểm soát browser quan sát thông qua công cụ dành cho nhà phát triển. DevTools thường cho phép xem request/response, JavaScript bundle, source map, DOM, cookie, Web Storage, IndexedDB, Cache Storage và hoạt động của service worker.

Ví dụ, người dùng đăng nhập vào:

~~~text
https://app.example.test
~~~

Ứng dụng tải hồ sơ bằng Fetch API, lưu một số preference trong localStorage và cache response cho chế độ offline. Người dùng mở DevTools có thể quan sát request, response, dữ liệu lưu trữ và code đang chạy. Đây là khả năng bình thường của browser: nếu dữ liệu đã được gửi hoặc lưu trên thiết bị, người kiểm soát thiết bị có thể tìm cách xem nó.

DevTools exposure không tự động có nghĩa website có lỗ hổng từ xa. Nó trở thành vấn đề bảo mật khi ứng dụng gửi secret, dữ liệu cá nhân hoặc quyền truy cập vượt quá nhu cầu tới client; ghi dữ liệu nhạy cảm vào log; để source map hoặc bundle tiết lộ thông tin nội bộ; hoặc dựa vào kiểm tra ở frontend để bảo vệ tài nguyên.

Nguyên tắc cốt lõi: **mọi dữ liệu mà browser cần xử lý đều có thể được người dùng kiểm tra và thay đổi trên thiết bị của họ**. Minify, obfuscate, ẩn nút giao diện hay chặn phím tắt mở DevTools không tạo ra ranh giới bảo mật.

Bài học thuộc chương **Storage security** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới giữa browser, origin, cookie và ứng dụng web, đồng thời thực hành Same-Origin Policy, CORS, XSS, CSRF, CSP, Trusted Types và security headers. Bài này tập trung vào việc dữ liệu lưu trong browser có thể bị quan sát qua DevTools, cách nhận diện nơi dữ liệu xuất hiện và biện pháp giảm phơi lộ trong môi trường production.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích threat model của DevTools exposure và phân biệt quan sát cục bộ với tấn công từ xa.
2. Kiểm tra request, response, headers và payload trong Network panel.
3. Nhận diện dữ liệu nhạy cảm trong Console, Sources, source map và frontend bundle.
4. Kiểm tra cookie, localStorage, sessionStorage, IndexedDB, Cache Storage và service worker.
5. Hiểu giới hạn của HttpOnly, Secure, SameSite và mã hóa dữ liệu phía client.
6. Nhận diện secret, token, PII và dữ liệu nội bộ bị đưa tới frontend.
7. Hiểu vì sao client-side validation và authorization không thể là lớp cưỡng chế duy nhất.
8. Thiết kế logging, redaction, source map và production build an toàn.
9. Đánh giá rủi ro từ XSS, browser extension, thiết bị dùng chung và profile bị truy cập.
10. Dùng DevTools để kiểm tra và xác minh biện pháp giảm phơi lộ.

## 2. Threat model: ai có thể xem dữ liệu trong DevTools?

DevTools là giao diện debug cục bộ do browser cung cấp. Người dùng có quyền điều khiển thiết bị và profile có thể mở DevTools, xem dữ liệu của trang và thực hiện các thao tác debug mà browser cho phép.

Các tình huống cần phân biệt:

| Tình huống | Khả năng quan sát | Ý nghĩa bảo mật |
| --- | --- | --- |
| Người dùng kiểm tra website của chính họ | Có thể xem code, request, response và storage phía client | Hành vi bình thường; không được xem dữ liệu đã gửi tới client là bí mật với chính người dùng. |
| Người khác dùng chung máy/profile đã đăng nhập | Có thể mở browser và xem dữ liệu còn lưu | Cần bảo vệ phiên, khóa thiết bị, logout và xóa dữ liệu theo user. |
| XSS chạy cùng origin | Script có thể đọc DOM và nhiều storage mà JavaScript được phép truy cập | Đây là rủi ro từ xa nghiêm trọng; giảm dữ liệu lưu client và phòng vệ XSS. |
| Browser extension có quyền rộng | Có thể đọc hoặc sửa nội dung trang tùy quyền extension | Giới hạn extension, quyền truy cập và chính sách thiết bị. |
| Malware hoặc người có quyền quản trị thiết bị | Có thể quan sát dữ liệu ở cấp thiết bị/browser | Website không thể bảo vệ tuyệt đối trước thiết bị đã bị kiểm soát. |
| Website bên ngoài không có quyền trên origin | Bị SOP/CORS và browser security boundaries giới hạn | Không mặc nhiên có thể mở DevTools hoặc đọc storage của origin khác. |

DevTools không phải một API web mà website khác có thể gọi để lấy dữ liệu. Một website không tin cậy không tự nhiên có quyền đọc panel DevTools của tab khác. Rủi ro cần đánh giá theo quyền của người kiểm soát browser, extension, malware hoặc script đã chạy được trong origin.

### 2.1. Dữ liệu đã gửi tới client không còn là bí mật với client

Nếu server gửi một JSON response chứa số dư, email, quyền quản trị hoặc thông tin hồ sơ, browser phải nhận được dữ liệu đó để ứng dụng sử dụng. Người dùng có thể xem response trong Network hoặc thông qua code đang chạy.

Không gửi dữ liệu chỉ để ẩn một trường trên giao diện. Nếu user không được phép xem dữ liệu đó, server không nên trả nó trong response của user đó.

### 2.2. DevTools không vượt qua mọi ranh giới origin

DevTools được mở bởi người điều khiển browser và có khả năng debug tab hiện tại. JavaScript chạy trên một origin khác vẫn chịu SOP và các giới hạn của browser. Không nhầm khả năng của giao diện debug cục bộ với quyền của một website từ xa.

## 3. Network panel: request và response có thể tiết lộ gì?

Network panel cho phép quan sát các request do trang tạo ra, bao gồm Fetch/XHR, document, script, image, font, WebSocket và các tài nguyên khác.

Một request API có thể để lộ:

- URL, path, query string và hostname nội bộ nếu frontend gọi sai endpoint.
- Request headers, bao gồm một số metadata xác thực.
- Request body như email, số điện thoại, nội dung form hoặc dữ liệu giao dịch.
- Response headers, cache policy, CORS và security headers.
- Response body như JSON hồ sơ, danh sách user, thông tin đơn hàng.
- Redirect chain, timing, initiator và trạng thái network.
- Cookie được gửi trong request và cookie được đặt qua response.

Ví dụ:

~~~js
const response = await fetch("/api/profile");
const profile = await response.json();
renderProfile(profile);
~~~

Nếu response trả:

~~~json
{
  "id": "user-123",
  "displayName": "An",
  "email": "an@example.test",
  "role": "admin",
  "internalFlags": ["manual-review"]
}
~~~

thì những trường này đã tới browser và có thể được kiểm tra trong Network. Ẩn `role` hoặc `internalFlags` bằng CSS không làm chúng bí mật.

### 3.1. Request body và query string

Dữ liệu nhạy cảm không nên được đặt trong URL query nếu không cần thiết. URL có thể xuất hiện trong browser history, server/proxy logs, analytics, referrer và Network panel.

Với dữ liệu nhạy cảm, dùng phương thức và body phù hợp, TLS và chính sách cache đúng. Tuy nhiên, POST body cũng hiển thị trong DevTools của người đang kiểm soát browser; đổi GET sang POST không làm dữ liệu bí mật với client.

### 3.2. Response tối thiểu theo quyền

API nên trả đúng những field mà màn hình và nghiệp vụ cần. Không trả toàn bộ record database rồi trông chờ frontend bỏ các field không dùng.

Ví dụ, endpoint danh sách user cho một vai trò không cần xem thông tin tài chính thì không nên gửi những trường tài chính trong response. Authorization phải được thực hiện ở server trên từng resource và action.

### 3.3. Headers và credential

Network panel có thể hiển thị header request/response theo browser và cấu hình. Tránh đặt access token dài hạn hoặc secret trong query string, custom debug header hay response header không cần thiết.

HttpOnly cookie không thể đọc bằng JavaScript trang qua document.cookie, nhưng người kiểm soát browser có thể xem cookie trong giao diện quản lý/debug của browser. HttpOnly bảo vệ khỏi một số đường đọc bằng script; nó không biến cookie thành bí mật với chủ thiết bị.

## 4. Console panel: log có thể trở thành kênh rò rỉ

Console hữu ích khi debug nhưng log production có thể chứa dữ liệu không nên lưu hoặc hiển thị.

Ví dụ nguy hiểm:

~~~js
console.log("Login response:", response);
console.log("Access token:", accessToken);
console.log("User profile:", profile);
console.error("Payment failed", {
  cardNumber,
  billingAddress,
  sessionId
});
~~~

Log có thể được nhìn thấy trong DevTools, được giữ lại khi điều hướng nếu Preserve log bật, được thu thập bởi công cụ quan sát hoặc xuất hiện trong screenshot/recording của đội hỗ trợ.

### 4.1. Không log secret hoặc toàn bộ object

Ưu tiên log mã sự kiện, trạng thái và identifier không nhạy cảm. Nếu cần correlation ID, tạo ID không mang quyền truy cập và không dùng token/session ID làm correlation key.

Ví dụ:

~~~js
console.info("payment.status", {
  orderReference: "ORD-TEST-42",
  state: "pending"
});
~~~

Không đưa access token, refresh token, cookie, password, OTP, private key hoặc dữ liệu thanh toán đầy đủ vào console.

### 4.2. Redaction phải diễn ra trước khi gửi log

Nếu log được chuyển tới monitoring/analytics, redaction cần thực hiện trước khi dữ liệu rời client hoặc trước khi collector lưu trữ. Không chỉ ẩn dữ liệu trong dashboard sau khi đã gửi.

Thiết kế allowlist field cho telemetry. Tránh serialize toàn bộ request/response object vì object có thể chứa headers, credentials hoặc dữ liệu cá nhân.

### 4.3. Stack trace và error message

Stack trace có thể tiết lộ tên module, đường dẫn source, route nội bộ hoặc cấu trúc ứng dụng. Error message quá chi tiết có thể để lộ SQL, tên bảng, endpoint nội bộ hoặc trạng thái xác thực.

Người dùng cần thông báo đủ để xử lý lỗi; thông tin chẩn đoán chi tiết nên được kiểm soát ở server log với quyền truy cập và retention phù hợp.

## 5. Sources panel: JavaScript bundle không phải nơi cất secret

Sources panel hiển thị các script và tài nguyên mà browser đã tải. Người dùng có thể xem bundle, tìm chuỗi, đặt breakpoint, step qua code và quan sát biến trong execution context.

Ví dụ frontend:

~~~js
const API_KEY = "sk_example_fake_value";
const INTERNAL_ENDPOINT = "https://internal.example.test/admin";
~~~

Các giá trị được đóng vào bundle có thể được tìm thấy bằng Sources, Search hoặc tải file JavaScript về. Minification chỉ làm code khó đọc hơn; nó không mã hóa hoặc bảo vệ secret.

### 5.1. Environment variable trong frontend build

Các biến môi trường có prefix dành cho frontend bundler thường được thay bằng literal trong lúc build. Ví dụ:

~~~js
const analyticsKey = import.meta.env.VITE_ANALYTICS_KEY;
~~~

hoặc:

~~~js
const apiUrl = process.env.NEXT_PUBLIC_API_URL;
~~~

Những biến được expose cho client là dữ liệu công khai đối với người tải bundle. Không đặt database password, private API key, service-role token hoặc signing secret vào biến build frontend.

Một số public key như publishable analytics/payment key được thiết kế để xuất hiện ở client; vẫn cần giới hạn domain, quota, scope và quyền phía server theo hướng dẫn của nhà cung cấp.

### 5.2. Minification và obfuscation không phải bảo mật

Minification giảm kích thước bundle; obfuscation làm code khó đọc hơn. Cả hai không ngăn người dùng lấy file, chạy debugger hoặc quan sát request/response.

Không đặt thuật toán kiểm soát quyền, business secret hoặc dữ liệu nhạy cảm vào client với giả định người dùng không hiểu code. Quyết định bảo mật phải được thực thi ở server.

## 6. Source map và thông tin nguồn

Source map ánh xạ code đã build/minify về file nguồn ban đầu để hỗ trợ debugging. Nếu source map được public, người dùng có thể đọc source gốc hoặc các đường dẫn file và comment tùy cách build.

Một bundle có thể chứa:

~~~js
//# sourceMappingURL=app.js.map
~~~

Nếu file map có `sourcesContent`, nó có thể nhúng nội dung source. Ngay cả khi không có sourcesContent, map vẫn có thể tiết lộ tên file, cấu trúc thư mục và vị trí mapping.

### 6.1. Source map không tự tạo secret

Source map chỉ tiết lộ những gì đã có trong source/build metadata. Nếu source có secret hard-code thì bundle thường đã có secret đó; gỡ map không sửa được lỗi gốc.

Rà soát cả bundle và map. Xóa secret khỏi source, build lại và rotate secret đã từng phát hành.

### 6.2. Các lựa chọn triển khai source map

| Cách triển khai | Tác động |
| --- | --- |
| Public source map | Dễ debug production; source map có thể được mọi người tải. |
| Private upload vào error monitoring | Debug tập trung; cần bảo vệ quyền truy cập và retention của dịch vụ. |
| Không phát hành map | Giảm khả năng đọc source gốc; vẫn không giấu được bundle đang chạy. |
| Hidden source map nhưng file map vẫn public | Không có comment tham chiếu trong bundle, nhưng file map vẫn có thể bị tải nếu biết URL. |

Không xem hidden-source-map là private nếu file .map vẫn được đưa lên CDN public. Nếu cần map riêng tư, không public file và upload tới hệ thống monitoring được kiểm soát.

### 6.3. Comment, path và metadata build

Source map hoặc bundle có thể chứa đường dẫn máy build, tên branch, tên package, feature flag, comment nội bộ và tên endpoint. Những thông tin này không phải lúc nào cũng là secret, nhưng có thể giúp người tấn công hiểu cấu trúc hệ thống.

Kiểm tra artifact production thực tế sau build và trước deploy, không chỉ xem cấu hình bundler.

## 7. Application panel: dữ liệu lưu phía client

Application panel trong browser DevTools thường cung cấp giao diện kiểm tra storage của origin. Tên và vị trí mục có thể thay đổi theo browser/version.

Các vùng thường có thể xem:

- Cookies.
- Local Storage.
- Session Storage.
- IndexedDB.
- Cache Storage.
- Service worker registrations.
- Storage usage và một số loại storage bổ sung mà browser hỗ trợ.

Người dùng kiểm soát browser có thể xem và trong nhiều trường hợp sửa hoặc xóa dữ liệu ở đây. Điều đó có nghĩa ứng dụng phải coi client storage là vùng không đáng tin cho quyết định bảo mật.

### 7.1. localStorage và sessionStorage

Ví dụ:

~~~js
localStorage.setItem("accessToken", "example-token");
sessionStorage.setItem("userRole", "admin");
~~~

Các giá trị này có thể được xem trong Application panel và đọc bởi JavaScript cùng origin. Nếu có XSS, script độc có thể lấy chúng.

Không lưu access/refresh token dài hạn hoặc dữ liệu nhạy cảm trong Web Storage chỉ để tiện truy cập. Không dùng userRole phía client để quyết định quyền; server phải xác minh role và authorization.

### 7.2. IndexedDB

IndexedDB có thể lưu record, blob, dữ liệu offline, queue đồng bộ và cache nghiệp vụ. Application panel cho phép kiểm tra database/object store ở browser hỗ trợ.

Nếu database chứa dữ liệu hồ sơ hoặc nội dung riêng tư, người dùng của profile có thể quan sát. XSS cùng origin cũng có thể đọc dữ liệu qua API IndexedDB theo quyền của origin.

Chỉ lưu dữ liệu cần thiết, phân vùng theo tài khoản và dọn đúng lúc logout/đổi user. Mã hóa dữ liệu trong IndexedDB bằng key mà JavaScript cùng origin có thể lấy được không chống lại XSS đang chạy trong origin.

### 7.3. Cache Storage và service worker

Cache Storage có thể chứa response API hoặc tài nguyên offline. Nếu cache response cá nhân, DevTools có thể giúp người kiểm soát browser kiểm tra nội dung và service worker code.

Không cache response nhạy cảm nếu không cần offline. Với dữ liệu cá nhân, cân nhắc Cache-Control phù hợp, cache namespace theo user và cleanup khi logout. Service worker không phải một vùng bí mật tách khỏi người dùng thiết bị.

### 7.4. OPFS và các storage API khác

OPFS là vùng file riêng cho origin, nhưng vẫn nằm trên thiết bị và thuộc quyền quản lý của browser/profile. Browser DevTools có thể cung cấp cách kiểm tra storage hoặc ứng dụng có thể truy cập qua API tương ứng.

Không coi OPFS là thư mục bí mật trước chủ thiết bị. Dữ liệu nhạy cảm vẫn cần tối thiểu hóa, kiểm soát vòng đời và bảo vệ bằng kiến trúc phù hợp.

## 8. Cookie trong DevTools: HttpOnly không có nghĩa ẩn khỏi chủ browser

Cookie có một số thuộc tính bảo mật:

| Thuộc tính | Bảo vệ chính |
| --- | --- |
| HttpOnly | Ngăn JavaScript trang đọc cookie qua document.cookie. |
| Secure | Giới hạn gửi cookie qua secure transport theo quy tắc browser. |
| SameSite | Hạn chế một số trường hợp gửi cookie cross-site. |
| Domain/Path | Xác định phạm vi host/path gửi cookie. |
| Max-Age/Expires | Điều khiển thời hạn lưu cookie. |

Ví dụ cookie session:

~~~http
Set-Cookie: session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

JavaScript trang không thể đọc cookie HttpOnly bằng document.cookie. Nhưng người dùng kiểm soát browser có thể xem cookie trong giao diện quản lý cookie/DevTools tùy browser. Đây là hành vi mong đợi vì browser phải quản lý cookie.

### 8.1. HttpOnly vẫn rất quan trọng

HttpOnly làm giảm khả năng XSS đánh cắp trực tiếp giá trị session cookie qua JavaScript. Tuy nhiên, XSS có thể vẫn gửi request cùng origin; browser tự đính kèm cookie phù hợp, và script độc có thể đọc response mà user được phép đọc.

Vì vậy HttpOnly giảm rủi ro đánh cắp cookie, nhưng không biến ứng dụng miễn nhiễm với XSS hoặc hành động trái phép.

### 8.2. Không đưa cookie vào log

Không log toàn bộ request headers nếu có Cookie hoặc Authorization. Redact ở middleware/observability pipeline và chỉ giữ metadata cần thiết. DevTools có thể hiển thị cookie trên máy người dùng; server log không nên nhân rộng việc lộ credential.

## 9. DOM và runtime state

Elements panel cho phép xem DOM sau khi JavaScript đã thay đổi. Sources/Debugger có thể dừng tại breakpoint và xem biến, closure hoặc call stack trong phạm vi debugger hỗ trợ.

Điều này cho thấy:

- Dữ liệu được render vào DOM có thể được người dùng quan sát.
- State frontend không phải nơi cưỡng chế authorization.
- Hidden field, disabled button và route guard phía client có thể bị thay đổi.
- Giá trị trong JavaScript memory không phải secret trước người kiểm soát browser.
- Validation phía client giúp UX nhưng server vẫn phải validate.

Ví dụ:

~~~js
if (currentUser.role === "admin") {
  showAdminButton();
}
~~~

Việc ẩn nút chỉ là điều khiển giao diện. API admin phải xác minh quyền ở server mỗi lần gọi, kể cả khi request được tạo thủ công từ Console hoặc một client khác.

### 9.1. Breakpoint và thay đổi state

Người dùng có thể pause JavaScript, thay biến trong debugger hoặc sửa DOM. Vì vậy không dùng biến như `isAdmin`, `canDelete` hoặc `paymentApproved` ở client làm bằng chứng cho server.

Server cần tự tính lại trạng thái từ dữ liệu tin cậy và kiểm tra quyền trước khi thay đổi tài nguyên.

### 9.2. Không gửi dữ liệu rồi chỉ ẩn bằng CSS

Nếu frontend nhận toàn bộ danh sách tài khoản nhưng chỉ hiển thị một phần, người dùng vẫn có thể xem response hoặc state. Hãy lọc dữ liệu ở API theo user, role và resource scope.

## 10. Network, TLS và khả năng xem payload

HTTPS bảo vệ dữ liệu trên đường truyền giữa client và endpoint theo TLS. Nhưng TLS kết thúc tại browser, nơi ứng dụng cần giải mã response để xử lý. DevTools hoạt động trong browser nên có thể xem request/response sau khi TLS đã được giải mã ở phía client.

Điều này không phải là TLS bị phá. TLS bảo vệ khỏi bên trung gian trên mạng; nó không giấu dữ liệu khỏi chính endpoint client đã nhận.

### 10.1. POST body vẫn hiển thị trong DevTools

Dùng POST thay GET có thể tránh một số rủi ro URL/history/referrer, nhưng request body vẫn được hiển thị trong Network panel. Không gửi secret cho client nếu client không cần nó.

### 10.2. TLS không thay authorization

Nếu user có thể gọi endpoint qua browser, server cần xác minh session, quyền và phạm vi dữ liệu. TLS chỉ bảo vệ kết nối và xác thực endpoint theo certificate; nó không quyết định user được phép xem record nào.

## 11. Client-side secret: những gì không nên đưa vào bundle

Không đặt các loại secret sau trong JavaScript, HTML, source map, JSON config công khai hoặc storage phía client:

- Database password hoặc connection string có credential.
- Private API key hoặc service account key.
- Signing key, private key hoặc HMAC secret.
- Service-role token có quyền vượt quá user.
- Access token/refresh token dài hạn nếu có thể dùng cơ chế session an toàn hơn.
- Secret của webhook, payment provider hoặc cloud account.
- Credential nội bộ dùng giữa backend services.

Một số giá trị được thiết kế công khai, ví dụ OAuth client ID hoặc publishable key. Chúng không phải secret; vẫn phải giới hạn scope và quyền trên server/provider.

### 11.1. Secret đã phát hành phải được rotate

Nếu secret từng xuất hiện trong bundle hoặc source map production, hãy coi nó đã bị lộ. Xóa khỏi source và build mới không làm bản cũ biến mất khỏi CDN cache, mirror, browser cache hoặc repository history.

Quy trình:
1. Thu hồi hoặc rotate credential ở provider/server.
2. Kiểm tra log sử dụng và phạm vi ảnh hưởng.
3. Loại bỏ secret khỏi frontend code/config.
4. Build và deploy artifact mới.
5. Purge CDN/cache nếu phù hợp.
6. Kiểm tra bundle/source map production không còn giá trị đó.
7. Rà soát repository history và nơi đã chia sẻ artifact.

Không chỉ đổi tên biến hoặc obfuscate chuỗi secret.

## 12. Dữ liệu cá nhân và data minimization

DevTools giúp xác định dữ liệu nào thật sự tới client. Hãy rà response theo nguyên tắc tối thiểu hóa:

- Chỉ trả field màn hình cần.
- Phân trang danh sách lớn.
- Không trả internal note, moderation flag hoặc metadata admin cho user không có quyền.
- Không gửi PII trong log hoặc telemetry nếu không cần.
- Không cache response cá nhân vào cache dùng chung.
- Đặt retention cho dữ liệu offline.
- Xóa dữ liệu cũ khi user logout hoặc đổi tài khoản.
- Không giữ bản sao của dữ liệu nhạy cảm trong nhiều storage API.

Dữ liệu ít hơn trên client làm giảm hậu quả khi thiết bị dùng chung, extension độc hoặc XSS xảy ra.

## 13. XSS và storage exposure

XSS chạy trong origin có thể sử dụng nhiều quyền mà ứng dụng đang có trong context đó. Nếu dữ liệu nằm trong localStorage, sessionStorage, IndexedDB hoặc DOM, script độc có thể đọc và gửi đi.

Ví dụ minh họa rủi ro trong lab:

~~~js
const profile = localStorage.getItem("profile");
console.log(profile);
~~~

Nếu XSS có thể chạy trong trang, nó có thể thực hiện thao tác tương tự. HttpOnly cookie giảm việc đọc cookie trực tiếp, nhưng XSS vẫn có thể gọi API cùng origin trong session của user.

### 13.1. Mã hóa client-side không tự giải quyết XSS

Nếu ứng dụng lưu ciphertext cùng key giải mã trong JavaScript hoặc có thể gọi API giải mã trong cùng origin, XSS có thể truy cập key hoặc yêu cầu ứng dụng giải mã. Mã hóa local storage có thể hữu ích cho một số threat model thiết bị, nhưng không bảo vệ khỏi script độc đang chạy với cùng quyền.

### 13.2. Các lớp giảm rủi ro

- Output encoding theo ngữ cảnh.
- Safe DOM APIs và tránh sink nguy hiểm.
- CSP phù hợp, nonce/hash và hạn chế script source.
- Trusted Types cho DOM injection sinks ở browser hỗ trợ.
- Kiểm soát dependency và third-party script.
- HttpOnly/Secure/SameSite cho session cookie.
- Authorization phía server và token scope tối thiểu.
- Giảm thời gian sống và phạm vi dữ liệu client.

Không một header nào thay thế việc sửa source-to-sink XSS.

## 14. Browser extension và thiết bị dùng chung

Extension có thể yêu cầu quyền đọc dữ liệu trang, tab hoặc request. Quyền thực tế phụ thuộc manifest, permission, browser và cách extension hoạt động. Extension đáng tin bị xâm nhập hoặc extension độc có thể đọc nội dung mà người dùng đang xem.

Trên thiết bị dùng chung:
- Không để session tồn tại khi người khác có thể truy cập profile.
- Dùng logout và server-side session revocation.
- Khóa thiết bị và profile bằng cơ chế hệ điều hành/browser phù hợp.
- Không lưu PII lâu dài trong local storage nếu không cần.
- Xóa site data theo chính sách khi kết thúc phiên dùng chung.
- Không bật DevTools remote debugging hoặc remote port không được kiểm soát trên máy dùng chung.

Website không thể ngăn chủ thiết bị cài extension hoặc mở DevTools. Tổ chức có thể quản lý browser extension bằng enterprise policy trên thiết bị do tổ chức quản lý.

### 14.1. Remote debugging và DevTools Protocol

Một số browser hỗ trợ remote debugging qua giao diện DevTools Protocol để công cụ bên ngoài điều khiển tab, đọc DOM, xem network và thực thi JavaScript. Endpoint debug có quyền rất rộng đối với browser profile được gắn vào.

Không mở cổng remote debugging ra mạng công cộng hoặc mạng dùng chung. Chỉ bật khi cần trong môi trường phát triển, giới hạn bind vào loopback, bảo vệ máy và profile, đồng thời tắt khi hoàn tất. Không gắn profile chứa session production vào automation hoặc debugging tool không được kiểm soát. Người có quyền truy cập endpoint debug có thể thao tác browser như người dùng đang điều khiển profile đó.

## 15. Production logging và telemetry

Logging giúp phát hiện lỗi nhưng có thể tạo một bản sao dữ liệu nhạy cảm ở nhiều nơi: Console, monitoring SDK, analytics, crash report và server logs.

Thiết kế logging an toàn:

1. Dùng schema field allowlist.
2. Redact Authorization, Cookie, Set-Cookie, token và dữ liệu cá nhân.
3. Không serialize toàn bộ object request/response.
4. Không log form body mặc định.
5. Giới hạn quyền truy cập log và đặt retention.
6. Tách debug logs khỏi audit events.
7. Không dùng secret làm trace ID.
8. Kiểm tra source map và stack trace trước khi gửi tới dịch vụ ngoài.

Ví dụ helper redaction phía client:

~~~js
function safeTelemetryEvent(event) {
  return {
    name: String(event.name).slice(0, 80),
    category: String(event.category || "ui").slice(0, 40),
    status: String(event.status || "unknown").slice(0, 40)
  };
}
~~~

Ví dụ chỉ giữ field được chọn. Với dữ liệu quan trọng, redaction cũng cần ở server/collector vì client có thể bị sửa hoặc bỏ qua helper.

## 16. Source map và production build checklist

Trước khi phát hành:

- Kiểm tra bundle JS/CSS và các file JSON runtime.
- Tìm secret patterns và giá trị test bị quên.
- Kiểm tra comment, path, feature flag và internal hostname.
- Xác định source map có được public hay chỉ upload riêng.
- Đảm bảo map private không nằm trong thư mục CDN public.
- Bảo vệ quyền truy cập hệ thống error monitoring.
- Xóa console.log/debug code không cần thiết.
- Không dựa vào minification/obfuscation để giấu dữ liệu.
- Kiểm tra service worker và cache version để tránh giữ bundle cũ.
- Rotate secret đã từng xuất hiện trong artifact.

### 16.1. Kiểm tra artifact sau build

Đừng chỉ tìm trong source. Một biến môi trường có thể được bundler thay thế thành literal, một package có thể đưa debug metadata vào bundle hoặc source map chứa sourceContent.

Kiểm tra chính artifact sẽ deploy, ví dụ thư mục dist/build, và thực hiện scan secret bằng công cụ phù hợp trong pipeline. Scanner có false positive; cần review kết quả và xử lý secret thật.

### 16.2. Source map riêng tư vẫn cần bảo vệ

Nếu upload source map lên error monitoring, giới hạn quyền truy cập, thời hạn lưu và chia sẻ dự án. Source map có thể tiết lộ logic nội bộ và cấu trúc code dù không có credential.

## 17. Không dùng anti-debugging làm biện pháp bảo mật

Một số website thử phát hiện DevTools bằng cách đo kích thước cửa sổ, dùng debugger statement, kiểm tra timing hoặc chặn menu chuột phải. Những kỹ thuật này dễ bị bypass và có thể làm hỏng accessibility/debugging.

Không dùng các biện pháp đó để bảo vệ secret hoặc authorization. Người dùng có thể tải bundle về, sửa JavaScript, tắt breakpoint hoặc chạy request bên ngoài browser.

Nếu cần bảo vệ nội dung, hãy kiểm tra quyền ở server và chỉ gửi dữ liệu mà user được phép nhận.

### 17.1. DevTools detection có thể gây false positive

Browser zoom, docked panels, màn hình nhỏ và công cụ hỗ trợ tiếp cận có thể làm thay đổi kích thước viewport. Timing cũng thay đổi theo CPU, tab background và thiết bị. Dựa vào các dấu hiệu này để chặn người dùng sẽ không tạo bảo đảm an ninh.

### 17.2. Không chặn người dùng xem dữ liệu của chính họ

DevTools là công cụ của browser. Một ứng dụng không nên xem hành động mở DevTools là bằng chứng tấn công. Tập trung bảo vệ dữ liệu và hành động ở server, đồng thời giữ trải nghiệm debug và hỗ trợ vận hành hợp lý.

## 18. Client-side validation và authorization

Client-side validation giúp người dùng nhập đúng dữ liệu và nhận lỗi sớm. Nhưng người dùng có thể sửa DOM, thay state, gọi API trực tiếp hoặc replay request.

Ví dụ không an toàn:

~~~js
if (form.role.value === "admin") {
  submitAdminChange();
}
~~~

Nếu server tin role do client gửi, user có thể sửa giá trị. Server phải lấy danh tính từ session/token đã xác thực, tra quyền ở phía server và kiểm tra resource/action cụ thể.

### 18.1. Hidden field không phải bằng chứng tin cậy

~~~html
<input type="hidden" name="price" value="100">
~~~

Người dùng có thể sửa hidden input trước khi submit. Server phải tính giá từ catalog/order state phía server và không tin amount/role/owner do client gửi nếu chúng quyết định quyền hoặc giá trị giao dịch.

### 18.2. Frontend route guard chỉ là UX

Một route guard có thể ẩn trang admin khỏi menu hoặc chuyển hướng user không có role. API và backend route vẫn cần kiểm tra authorization. Không coi việc URL khó đoán hoặc nút bị ẩn là lớp bảo vệ.

## 19. Cache, logout và dữ liệu còn sót

Dữ liệu có thể còn trong:
- HTTP cache.
- Cache Storage.
- IndexedDB.
- localStorage/sessionStorage.
- Service worker state.
- Console logs hoặc monitoring buffers.
- Browser history/downloads theo cách ứng dụng sử dụng.

Khi logout:
1. Revoke session/token phía server.
2. Hết hạn cookie với đúng Domain/Path; server xử lý HttpOnly cookie.
3. Xóa dữ liệu nhạy cảm trong Web Storage và IndexedDB theo user namespace.
4. Dọn Cache Storage chứa response cá nhân.
5. Đồng bộ trạng thái logout giữa tab nếu cần.
6. Không xóa dữ liệu offline chưa đồng bộ mà không cảnh báo hoặc có phương án phục hồi.
7. Cân nhắc Clear-Site-Data cho luồng reset site data nếu phạm vi xóa phù hợp.

Clear-Site-Data có thể xóa nhiều dữ liệu hơn một key cụ thể; cần đánh giá ảnh hưởng tới subdomain và các ứng dụng cùng site. Xóa phía client không thay server-side revocation.

## 20. DevTools và Clear-Site-Data

DevTools có thể giúp quan sát và xóa storage trong profile hiện tại. Application panel thường có mục Clear storage/Clear site data tùy browser. Thao tác này có thể xóa cookies, Web Storage, IndexedDB, Cache Storage và service worker data theo lựa chọn/browser.

Clear-Site-Data là response header do server gửi để yêu cầu browser xóa một số nhóm dữ liệu:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Nó không xóa dữ liệu trên thiết bị khác, database server, file người dùng đã tải về hoặc CDN cache. Browser support và phạm vi cụ thể phụ thuộc directive/version.

Khi debug DevTools exposure, dùng profile test và dữ liệu giả. Không bấm Clear site data trên profile production có dữ liệu quan trọng nếu chưa xác định phạm vi.

## 21. Kiểm tra dữ liệu nhạy cảm trong Network

Một quy trình review API:

1. Mở DevTools → Network.
2. Bật Preserve log nếu cần quan sát redirect/navigation.
3. Lọc Fetch/XHR.
4. Thực hiện một thao tác đại diện, ví dụ mở hồ sơ hoặc danh sách đơn.
5. Chọn request và kiểm tra Headers, Payload, Response, Cookies và Initiator.
6. Liệt kê field không cần thiết hoặc secret xuất hiện.
7. Kiểm tra cache headers và CORS.
8. Lặp lại với user role khác để xác minh server chỉ trả dữ liệu được phép.
9. Kiểm tra request khi gọi trực tiếp endpoint, không chỉ qua UI.
10. Ghi nhận kết quả bằng dữ liệu giả và không đưa credential vào báo cáo.

Đặc biệt kiểm tra response khi user không có quyền. Ẩn component trên UI nhưng response vẫn chứa dữ liệu admin là lỗi authorization/data minimization.

## 22. Kiểm tra storage trong Application panel

Trong profile test:

1. Mở DevTools → Application hoặc Storage.
2. Chọn đúng origin.
3. Kiểm tra Cookies và thuộc tính HttpOnly, Secure, SameSite, Domain, Path.
4. Kiểm tra localStorage và sessionStorage.
5. Mở IndexedDB và xem object store/record mẫu.
6. Kiểm tra Cache Storage và response được cache.
7. Kiểm tra Service Workers, scope, active worker và cache version.
8. Nếu browser hỗ trợ, kiểm tra storage usage/OPFS.
9. Đăng xuất và xác minh dữ liệu nhạy cảm được xóa theo thiết kế.
10. Dùng dữ liệu test; tránh sao chép PII hoặc token vào ticket/screenshot.

Không cần ghi lại toàn bộ giá trị cookie hoặc response trong báo cáo. Ghi tên field, loại storage và phát hiện ở mức đủ để sửa.

## 23. Thực hành A — Tìm dữ liệu bị gửi thừa trong API response

Tạo endpoint lab trả về một object hồ sơ có field công khai và field nội bộ giả lập:

~~~json
{
  "displayName": "Test User",
  "email": "test@example.test",
  "internalRiskNote": "LAB_ONLY",
  "adminFlag": true
}
~~~

Mở Network panel và gọi endpoint bằng user role thường. Xác định liệu internalRiskNote/adminFlag có được trả về dù UI không hiển thị không.

Sửa API để chỉ trả field được phép. Gọi lại endpoint trực tiếp và xác minh field nhạy cảm không còn trong response. Không dùng dữ liệu người dùng thật.

## 24. Thực hành B — Rà soát storage và cookie

Trong origin lab, lưu dữ liệu giả vào localStorage, IndexedDB và Cache Storage. Tạo cookie test có HttpOnly/Secure trên HTTPS staging.

Mở Application panel và ghi nhận:
- Loại storage nào giữ dữ liệu.
- Dữ liệu nào JavaScript đọc được.
- Cookie nào có HttpOnly.
- Dữ liệu nào còn sau reload.
- Dữ liệu nào bị xóa khi logout.

So sánh document.cookie với giao diện Cookies của DevTools để hiểu HttpOnly bảo vệ script như thế nào và không che cookie khỏi người kiểm soát browser.

## 25. Thực hành C — Source map và frontend bundle

Build một ứng dụng demo có source map trong môi trường staging. Mở Sources panel và kiểm tra:
- Bundle đã minify.
- Comment sourceMappingURL.
- File .map có truy cập được không.
- sourcesContent có nhúng source không.
- Environment variable nào xuất hiện dưới dạng literal.

Thử build production với source map private upload hoặc không public map. Kiểm tra artifact deploy thực tế, không chỉ config bundler. Dùng giá trị giả, không đưa secret thật vào bài lab.

## 26. Thực hành D — Kiểm tra log và client-side authorization

Trong trang demo:
1. Mở Console và rà log có chứa token/PII hay không.
2. Đặt breakpoint tại đoạn UI kiểm tra role.
3. Thử thay state giao diện hoặc hidden field bằng dữ liệu test.
4. Gửi request tới endpoint lab bằng UI và kiểm tra server response.
5. Gọi lại endpoint với user không có quyền.
6. Xác minh server trả 401/403 hoặc kết quả phù hợp và không trả dữ liệu nhạy cảm.

Mục tiêu là chứng minh việc sửa UI không thể cấp quyền ở backend. Không thử trên tài khoản hoặc hệ thống không được phép.

## 27. Checklist review DevTools exposure

- [ ] Xem Network response và chỉ trả field mà user hiện tại được phép nhận.
- [ ] Không đặt secret trong JavaScript, HTML, runtime config hoặc frontend environment variables.
- [ ] Phân biệt public key được thiết kế cho client với private credential.
- [ ] Kiểm tra production bundle và source map sau build.
- [ ] Không xem minification/obfuscation là bảo mật.
- [ ] Không public source map nếu source cần được giữ riêng; bảo vệ map ở error monitoring.
- [ ] Không log password, OTP, token, cookie, private key hoặc PII không cần thiết.
- [ ] Redact dữ liệu trước khi gửi telemetry/monitoring.
- [ ] Không serialize toàn bộ request/response vào log.
- [ ] Kiểm tra localStorage/sessionStorage và không lưu secret dài hạn.
- [ ] Kiểm tra IndexedDB, Cache Storage và OPFS có dữ liệu nhạy cảm không.
- [ ] Đánh giá cookie HttpOnly/Secure/SameSite; nhớ HttpOnly không giấu cookie khỏi chủ browser.
- [ ] Không dựa vào client state, hidden field, disabled button hoặc route guard để cấp quyền.
- [ ] Thực hiện authentication/authorization ở server cho mọi request.
- [ ] Phòng vệ XSS bằng output encoding, safe DOM, CSP và Trusted Types khi phù hợp.
- [ ] Hiểu HttpOnly giảm đọc cookie bằng script nhưng XSS vẫn có thể gọi API trong session.
- [ ] Tách dữ liệu theo user/tenant và cleanup khi logout/đổi tài khoản.
- [ ] Revoke session/token phía server; xóa cookie và storage phía client theo đúng scope.
- [ ] Kiểm tra service worker/cache không giữ response cá nhân ngoài retention.
- [ ] Quản lý browser extension trên thiết bị tổ chức khi phù hợp.
- [ ] Không dùng anti-debugging hoặc chặn DevTools làm lớp bảo mật.
- [ ] Dùng profile test và dữ liệu giả khi thực hành.
- [ ] Không đưa giá trị credential/PII vào screenshot hoặc báo cáo.

## 28. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Người dùng không mở được DevTools thì secret được an toàn.” | **Sai** | Bundle và request có thể được tải, lưu hoặc kiểm tra bằng cách khác. |
| “Minify JavaScript làm secret không thể bị lấy.” | **Sai** | Minification chỉ thay đổi cách biểu diễn code. |
| “Source map private nếu bundle không có link tới map.” | **Sai** | File map vẫn public nếu server/CDN cho tải trực tiếp. |
| “HttpOnly cookie không thể xem trong DevTools.” | **Sai** | HttpOnly chặn JavaScript trang; giao diện browser có thể quản lý/hiển thị cookie. |
| “HTTPS ngăn người dùng xem Network payload.” | **Sai** | TLS bảo vệ đường truyền; browser phải giải mã dữ liệu ở client. |
| “POST body bí mật hơn GET với người kiểm soát browser.” | **Sai** | POST body vẫn hiển thị trong Network panel. |
| “Ẩn field bằng CSS là đủ bảo vệ dữ liệu.” | **Sai** | Nếu response đã chứa field, client có thể xem nó. |
| “localStorage mã hóa hoặc bảo vệ token khỏi XSS.” | **Sai** | JavaScript cùng origin có thể đọc dữ liệu; XSS có thể làm tương tự. |
| “Mã hóa IndexedDB bằng key trong bundle chống được XSS.” | **Sai** | Script độc cùng origin có thể truy cập key hoặc yêu cầu ứng dụng giải mã. |
| “Server có thể tin role do frontend gửi.” | **Sai** | Client state có thể bị sửa; server phải xác minh quyền. |
| “DevTools exposure đồng nghĩa website bị hack từ xa.” | **Sai** | Quan sát cục bộ là khả năng bình thường của người kiểm soát browser. |
| “Một website khác có thể đọc mọi panel DevTools.” | **Sai** | Website khác vẫn chịu SOP và browser security boundaries. |
| “HttpOnly khiến XSS không thể thực hiện hành động.” | **Sai** | XSS có thể gọi API và browser tự gửi cookie phù hợp. |
| “Gỡ source map sẽ xóa secret đã phát hành.” | **Sai** | Secret có thể vẫn ở bundle, cache, mirror hoặc lịch sử repository. |
| “Chặn phím F12 hoặc debugger statement là anti-exfiltration.” | **Sai** | Người dùng có thể dùng công cụ khác hoặc lấy tài nguyên trực tiếp. |
| “Clear-Site-Data thu hồi session trên mọi thiết bị.” | **Sai** | Header chỉ tác động dữ liệu browser trong phạm vi xử lý; server phải revoke session. |

## 29. Tổng kết

DevTools cho thấy rõ dữ liệu mà ứng dụng đã đưa tới browser: request, response, code, DOM, cookie và storage. Đây là năng lực bình thường của người kiểm soát thiết bị. Rủi ro xuất hiện khi ứng dụng coi dữ liệu client là bí mật, gửi thừa field, để secret trong bundle/log/storage hoặc dựa vào kiểm tra frontend để bảo vệ quyền.

HttpOnly, Secure và SameSite có vai trò riêng nhưng không biến cookie thành bí mật với chủ browser. HTTPS bảo vệ dữ liệu trên đường truyền nhưng không giấu payload khỏi Network panel. Minification, obfuscation và anti-debugging không thay thế authorization phía server, data minimization và phòng vệ XSS.

Ba nguyên tắc cần nhớ:

1. **Coi client là vùng có thể kiểm tra:** không gửi secret hoặc dữ liệu user không được phép xem; rà Network response, bundle, source map và storage.
2. **Bảo vệ từng lớp dữ liệu:** redaction log, cookie đúng thuộc tính, storage tối thiểu, cache có retention và cleanup khi logout; HttpOnly giảm đọc cookie bằng script nhưng không chặn mọi hành động XSS.
3. **Cưỡng chế quyền ở server:** client-side validation và UI chỉ hỗ trợ trải nghiệm; server xác minh session, role, resource và action cho mọi request. Không dựa vào việc người dùng khó mở DevTools.

Khi review một ứng dụng, hãy hỏi: **Network response có field thừa không, bundle/source map có secret hoặc metadata nội bộ không, Console/telemetry có log PII/token không, storage còn dữ liệu sau logout không, cookie có được cấu hình đúng không, và backend có từ chối request khi client tự sửa state không?** Trả lời những câu hỏi này giúp giảm dữ liệu phơi lộ và giữ ranh giới bảo mật đúng ở phía server.
