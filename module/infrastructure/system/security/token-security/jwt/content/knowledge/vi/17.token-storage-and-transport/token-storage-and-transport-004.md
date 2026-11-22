# Token trong bộ nhớ và giới hạn trước mã độc chạy trong ứng dụng

## 1. Vì sao nơi lưu token quan trọng?

Trong module **SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)**, token là thông tin xác thực có thể cho phép bên sở hữu thực hiện hành động thay người dùng. Vì vậy, cách lưu token ảnh hưởng trực tiếp đến khả năng kẻ tấn công lấy cắp hoặc sử dụng token.

Với ứng dụng chạy trong trình duyệt, các lựa chọn phổ biến gồm:

- **Bộ nhớ của ứng dụng (in-memory):** giữ token trong biến, closure hoặc cấu trúc dữ liệu chỉ tồn tại khi ứng dụng đang chạy.
- **Web Storage:** lưu trong localStorage hoặc sessionStorage.
- **IndexedDB:** lưu dữ liệu bền vững theo origin.
- **Cookie:** trình duyệt quản lý và tự gửi cookie theo quy tắc domain/path/SameSite.
- **Backend-for-Frontend (BFF):** trình duyệt giữ session cookie; backend lưu và sử dụng access token thay cho JavaScript phía trình duyệt.

Không có lựa chọn nào loại bỏ mọi rủi ro. Lưu token trong bộ nhớ giúp giảm thời gian token tồn tại trong kho lưu trữ bền vững và giảm khả năng lấy lại token sau khi trình duyệt khởi động lại. Tuy nhiên, nếu mã độc chạy được trong cùng ứng dụng hoặc cùng origin, nó có thể sử dụng quyền của ứng dụng trong lúc token còn hiệu lực.

**Memory-only là một biện pháp giảm thiểu rủi ro lưu trữ, không phải ranh giới bảo mật chống XSS.** Cần kết hợp với ngăn chặn injection, kiểm soát script, giới hạn quyền token, thời hạn ngắn và thiết kế phiên phù hợp.

## 2. Token trong bộ nhớ là gì?

Token trong bộ nhớ là token được giữ trong vùng nhớ runtime của ứng dụng thay vì ghi vào kho lưu trữ bền vững như localStorage, sessionStorage hoặc IndexedDB.

Ví dụ khái niệm:

```text
application starts
    -> authenticate user
    -> receive access token
    -> keep token in application memory
    -> attach token to API request
    -> clear token when session ends or application context is discarded
```

Trong ứng dụng trình duyệt, bộ nhớ có thể là:

- Biến trong module hoặc application state.
- Closure giữ tham chiếu tới token.
- Một service quản lý phiên trong JavaScript runtime.
- Bộ nhớ riêng của Web Worker, nếu ứng dụng chuyển thao tác giữ token vào worker.

Các lựa chọn này khác nhau về khả năng truy cập từ các phần của ứng dụng, nhưng **không tự tạo ra một vùng tin cậy độc lập với mọi mã JavaScript cùng origin**. Mã độc chạy cùng quyền của ứng dụng vẫn có thể gọi chức năng hợp lệ, can thiệp request hoặc lạm dụng giao diện để hành động thay người dùng.

### 2.1. So sánh bộ nhớ và các kho lưu trữ phía trình duyệt

| Nơi lưu | Tồn tại qua reload? | JavaScript cùng origin đọc trực tiếp? | Rủi ro chính |
| --- | --- | --- | --- |
| Biến/closure trong memory | Thông thường không | Có thể truy cập nếu có tham chiếu hoặc can thiệp runtime | XSS có thể sử dụng token khi ứng dụng đang chạy |
| Web Worker memory | Không, worker bị kết thúc thì mất | Không đọc trực tiếp heap của worker, nhưng có thể gọi message/API mà worker cung cấp | Script độc hại có thể lạm dụng giao diện worker hoặc request |
| localStorage | Có | Có | XSS có thể đọc và lấy token; dữ liệu tồn tại lâu |
| sessionStorage | Qua reload trong cùng tab | Có | XSS trong tab có thể đọc; thường bị mất khi tab/session kết thúc |
| IndexedDB | Có | Có | XSS có thể truy vấn dữ liệu theo quyền origin |
| Cookie HttpOnly | Có theo expiry/session | Không đọc bằng JavaScript thông thường | Trình duyệt tự gửi; cần kiểm soát CSRF và cấu hình cookie |
| BFF với session cookie | Session được quản lý phía server | Cookie HttpOnly không đọc trực tiếp | Cần bảo vệ session cookie, CSRF và backend session |

Không nên xem sessionStorage là memory-only: dữ liệu vẫn tồn tại qua reload và được lưu trong kho của trình duyệt. Tương tự, việc một token không xuất hiện trong localStorage không có nghĩa token không thể bị lấy cắp trong thời gian runtime.

## 3. Vòng đời của token trong bộ nhớ

Một thiết kế memory-only cần xác định rõ token được tạo, sử dụng, thay thế và xóa ở thời điểm nào.

### 3.1. Khi đăng nhập

1. Ứng dụng xác thực người dùng qua giao thức đã chọn.
2. Bên phát hành trả access token và có thể trả refresh token/session credential theo thiết kế.
3. Ứng dụng nhận access token qua kênh bảo vệ bằng TLS.
4. Access token được giữ trong memory và chỉ cung cấp cho thành phần cần gọi API.
5. Mọi API request gửi token trong header Authorization theo profile, ví dụ Bearer token.

Không đưa token vào URL, query string hoặc fragment nếu giao thức không yêu cầu. URL có thể bị lưu trong history, log, analytics, proxy hoặc gửi qua Referer tùy chính sách trình duyệt.

### 3.2. Khi reload hoặc mở tab mới

Token trong memory thường mất khi document/runtime bị hủy, ví dụ reload trang, đóng tab hoặc điều hướng làm ứng dụng bị unload. Điều này giảm khả năng lấy lại access token từ kho bền vững sau khi runtime kết thúc.

Đổi lại, ứng dụng phải có cách khôi phục phiên:

- Người dùng đăng nhập lại.
- Ứng dụng gọi BFF để kiểm tra session cookie và lấy trạng thái phiên.
- Ứng dụng dùng cơ chế refresh được thiết kế an toàn, ví dụ refresh token trong cookie HttpOnly hoặc quy trình xác thực lại.

Không nên tự động chuyển access token sang localStorage chỉ để tiện duy trì trạng thái qua reload mà không đánh giá lại rủi ro.

### 3.3. Khi token hết hạn hoặc refresh

Access token nên có thời hạn phù hợp với rủi ro và thời gian sử dụng. Khi hết hạn:

1. Dừng dùng access token cũ cho request mới.
2. Thực hiện refresh hoặc xác thực lại theo giao thức.
3. Chỉ thay token trong memory sau khi refresh thành công.
4. Tránh nhiều request đồng thời cùng refresh và gây race condition.
5. Nếu refresh thất bại hoặc phiên bị thu hồi, xóa trạng thái xác thực cục bộ và yêu cầu đăng nhập lại.

Nếu nhiều request đồng thời nhận lỗi hết hạn, nên gom refresh thành một thao tác chung trong ứng dụng. Các request còn lại chờ kết quả thay vì gửi nhiều refresh request.

### 3.4. Khi logout

Khi logout:

- Xóa access token khỏi state/memory của ứng dụng.
- Hủy hoặc vô hiệu hóa timer, callback và tác vụ refresh đang chờ.
- Xóa dữ liệu phiên liên quan khỏi bộ nhớ.
- Gọi endpoint kết thúc session/revoke nếu giao thức hỗ trợ.
- Nếu dùng cookie session, yêu cầu server hết hạn hoặc thu hồi session và xóa cookie bằng thuộc tính phù hợp.

Xóa tham chiếu JavaScript không đảm bảo ghi đè ngay bytes token trong RAM. Garbage collector và runtime quyết định thời điểm thu hồi bộ nhớ; các bản sao tạm thời có thể vẫn tồn tại. Vì vậy, không thể cam kết zeroization đáng tin cậy đối với chuỗi token trong môi trường JavaScript thông thường.

## 4. Mã độc chạy trong ứng dụng có thể làm gì?

Trong trình duyệt, mã JavaScript chạy trong cùng origin thường có quyền tương tác với dữ liệu và API mà ứng dụng được phép sử dụng. Nếu kẻ tấn công thực thi được script trong trang, chẳng hạn qua XSS hoặc script dependency bị xâm nhập, nó có thể:

- Đọc token từ biến/state nếu tìm được đường truy cập.
- Gọi hàm hợp lệ của ứng dụng để lấy dữ liệu hoặc thực hiện hành động.
- Gọi API bằng token hiện có, ngay cả khi không lấy được chuỗi token.
- Thay thế hoặc can thiệp fetch, XMLHttpRequest hoặc wrapper API để quan sát request/response.
- Đọc nội dung DOM mà người dùng có quyền xem và gửi dữ liệu ra ngoài.
- Thay đổi giao diện để lừa người dùng xác nhận thao tác.
- Chờ đến lúc token được làm mới rồi tiếp tục lạm dụng phiên.

Điểm quan trọng là **kẻ tấn công không nhất thiết phải đánh cắp token để lạm dụng phiên**. Nếu script độc hại có thể gọi API qua ứng dụng, nó có thể thực hiện hành động với quyền của người dùng trong thời gian mã độc chạy.

### 4.1. Vì sao memory-only không ngăn được XSS?

Giả sử access token chỉ nằm trong closure:

```text
const api = createApiClient(accessToken);

function loadProfile() {
  return api.get("/profile");
}
```

Một script khác không nhất thiết đọc được biến accessToken. Nhưng nếu nó có thể gọi loadProfile, gọi các action khác hoặc thao tác DOM, nó vẫn có thể lấy dữ liệu trả về hoặc thực hiện hành động dưới phiên người dùng.

Closure giảm khả năng truy cập trực tiếp vào chuỗi token nếu được thiết kế tốt, nhưng không biến toàn bộ ứng dụng thành một sandbox bảo mật trước script cùng origin.

### 4.2. Script bên thứ ba và dependency bị xâm nhập

Một ứng dụng có thể nạp analytics, quảng cáo, chat widget, tag manager hoặc thư viện bên thứ ba. Script chạy trực tiếp trong trang thường có quyền gần với script ứng dụng.

Nếu một dependency bị chiếm quyền hoặc bị phát hành phiên bản độc hại, nó có thể:

- Quan sát dữ liệu mà ứng dụng truyền qua API của nó.
- Đọc DOM hoặc dữ liệu hiển thị.
- Gọi endpoint bằng quyền của trang.
- Lấy token nếu có đường truy cập tới state hoặc storage.

Không nên giả định script bên thứ ba vô hại chỉ vì nó đến từ nhà cung cấp phổ biến. Cần giới hạn số lượng script, nguồn tải và quyền truy cập dữ liệu.

## 5. Mức độ bảo vệ của các kỹ thuật giữ token trong memory

### 5.1. Module scope và closure

Giữ token trong module hoặc closure thay vì gắn lên window giúp tránh việc token bị lộ qua một biến global dễ đoán. Đây là biện pháp giảm bề mặt truy cập trực tiếp.

Giới hạn:

- Mã độc cùng origin có thể gọi API công khai của module.
- Runtime có thể bị hook hoặc instrument.
- Token có thể xuất hiện trong request interceptor, error object hoặc log nếu thiết kế không cẩn thận.
- Dữ liệu response mà script độc hại có thể đọc vẫn có thể bị lấy đi.

### 5.2. Web Worker

Có thể giữ token trong worker và để worker thực hiện request thay cho trang. Worker có global scope riêng và không truy cập trực tiếp DOM; heap của worker không phải heap của window.

Tuy nhiên, worker không phải ranh giới chống XSS tuyệt đối:

- Script độc hại trong trang có thể gửi message tới worker nếu biết giao diện.
- Worker có thể trở thành confused deputy nếu nhận URL, method, header hoặc body tùy ý.
- Nếu worker trả dữ liệu nhạy cảm cho trang, mã độc có thể đọc dữ liệu đó.
- Nếu worker cung cấp hàm ký hoặc gọi API quá rộng, mã độc có thể lạm dụng hàm đó.

Nếu dùng worker, cần thiết kế API hẹp: giới hạn endpoint, method, loại dữ liệu và thao tác được phép; không nhận URL tùy ý hoặc yêu cầu ký tùy ý. Worker giúp cô lập nơi giữ token, nhưng không ngăn mã độc điều khiển các hành động mà worker cho phép.

### 5.3. Non-extractable key và proof-of-possession

Một số thiết kế dùng khóa mật mã không thể export từ Web Crypto để tạo chữ ký proof-of-possession hoặc DPoP proof thay vì gửi một bearer token thuần túy.

Điều này có thể làm khó việc lấy bản sao khóa riêng. Tuy nhiên:

- Mã độc chạy cùng quyền ứng dụng có thể gọi API ký nếu ứng dụng cho phép.
- Non-extractable không đồng nghĩa không thể sử dụng khóa.
- DPoP cần xác minh proof, ràng buộc token với khóa và kiểm tra các trường như method, URI, thời gian, định danh proof theo profile.
- Cần chống replay và bảo vệ quy trình cấp/đăng ký khóa.

Vì vậy, sender-constrained token có thể giảm rủi ro token bị lấy rồi sử dụng từ thiết bị khác, nhưng không tự ngăn script độc hại thực hiện request ngay trong phiên đang bị kiểm soát.

## 6. Lựa chọn lưu trữ: memory, cookie hay BFF?

### 6.1. Memory-only access token

Phù hợp khi ứng dụng cần SPA gọi API trực tiếp và chấp nhận việc đăng nhập/khôi phục phiên sau reload theo một cơ chế khác.

Ưu điểm:

- Access token không được lưu trong kho bền vững có thể đọc bằng JavaScript.
- Giảm khả năng token còn lại sau khi đóng tab hoặc runtime bị hủy.
- Có thể giới hạn phạm vi truy cập trực tiếp bằng module/closure hoặc worker.

Hạn chế:

- XSS vẫn có thể lạm dụng phiên khi ứng dụng đang chạy.
- Reload/tab mới làm mất access token.
- Cần thiết kế refresh/session recovery cẩn thận.
- Không bảo vệ token nếu nó bị ghi vào log, telemetry hoặc request trace.

### 6.2. Cookie HttpOnly

Cookie có các thuộc tính quan trọng:

- **HttpOnly:** JavaScript không đọc cookie qua document.cookie.
- **Secure:** chỉ gửi cookie qua kết nối HTTPS.
- **SameSite:** kiểm soát khi cookie được gửi trong một số ngữ cảnh cross-site.
- **Path** và **Domain:** giới hạn phạm vi gửi cookie; nên thu hẹp theo nhu cầu.
- **Max-Age** hoặc **Expires:** giới hạn thời gian tồn tại.

HttpOnly làm giảm khả năng script đọc và lấy giá trị cookie. Tuy nhiên, nếu XSS chạy trong origin ứng dụng, script vẫn có thể gửi request cùng origin và trình duyệt có thể tự đính kèm cookie. HttpOnly **giảm nguy cơ đánh cắp cookie**, nhưng không ngăn mã độc sử dụng phiên qua request.

Vì cookie được trình duyệt tự động gửi, cần đánh giá CSRF. SameSite hữu ích nhưng không thay thế hoàn toàn kiểm tra Origin/Referer, CSRF token hoặc các biện pháp phù hợp với mô hình ứng dụng.

### 6.3. Backend-for-Frontend (BFF)

Với BFF, browser giữ một session cookie; access token và refresh token được lưu phía server. Trình duyệt gửi request tới BFF, BFF gọi API phía sau bằng token.

Ưu điểm:

- JavaScript không cần đọc access token hoặc refresh token.
- Token OAuth/JWT không bị đưa trực tiếp vào browser storage.
- BFF có thể tập trung quản lý refresh, revoke, audience và quyền gọi API.

Hạn chế:

- XSS vẫn có thể gọi endpoint BFF và đọc dữ liệu mà người dùng được phép xem.
- Cookie session tự động được gửi nên cần chống CSRF.
- BFF trở thành thành phần cần bảo vệ, mở rộng và vận hành an toàn.
- Cần kiểm soát session fixation, timeout, logout và quyền giữa các endpoint.

### 6.4. Bảng so sánh lựa chọn

| Tiêu chí | Memory-only access token | HttpOnly session/token cookie | BFF |
| --- | --- | --- | --- |
| JavaScript đọc token | Có thể, tùy nơi giữ | Không đọc được cookie HttpOnly | Không cần tiếp xúc access token |
| Token bền vững trong browser | Không, nếu chỉ memory | Cookie tồn tại theo expiry/session | Chỉ session cookie phía browser |
| XSS lấy token trực tiếp | Có thể nếu truy cập được runtime/state | Khó đọc giá trị cookie | Không lấy access token từ browser |
| XSS thực hiện hành động | Có thể qua API client/request | Có thể qua request cùng origin | Có thể gọi endpoint BFF |
| CSRF | Thường ít hơn với bearer header do JS tự gắn | Cần đánh giá vì cookie tự gửi | Cần bảo vệ BFF |
| Khả năng duy trì qua reload | Cần khôi phục phiên | Có theo cookie | Có theo session cookie |
| Độ phức tạp | Trung bình | Trung bình | Cao hơn, cần backend |

Không có lựa chọn lưu trữ nào thay thế được việc ngăn mã độc thực thi trong origin.

## 7. Giảm khả năng mã độc chạy trong ứng dụng

Vì memory-only không ngăn được mã độc đang chạy, lớp phòng thủ quan trọng là giảm xác suất script độc hại được thực thi và giới hạn quyền của script.

### 7.1. Ngăn XSS bằng xử lý dữ liệu đúng ngữ cảnh

- Escape/encode output theo đúng ngữ cảnh HTML, attribute, URL hoặc JavaScript.
- Ưu tiên API cập nhật text an toàn thay vì đưa dữ liệu không tin cậy vào HTML.
- Tránh eval, Function, inline script và các API thực thi chuỗi nếu không thực sự cần.
- Sanitize HTML nếu nghiệp vụ bắt buộc cho phép nội dung HTML do người dùng cung cấp; dùng sanitizer được duy trì và cấu hình đúng.
- Kiểm tra đầu vào là hữu ích nhưng không thay thế output encoding.

### 7.2. Content Security Policy (CSP)

CSP giúp giới hạn nguồn script và một số hành vi nguy hiểm. Nên:

- Dùng nonce hoặc hash cho script được phép thay vì cho phép inline script rộng rãi.
- Tránh unsafe-eval nếu không có lý do bắt buộc.
- Hạn chế script-src theo nguồn tối thiểu.
- Dùng object-src 'none', base-uri 'self' và các directive phù hợp với ứng dụng.
- Triển khai report-only để đánh giá vi phạm trước khi enforcement.
- Theo dõi và xử lý CSP reports; tránh đưa dữ liệu nhạy cảm vào report.

CSP là một lớp phòng thủ bổ sung. Cấu hình sai, allowlist quá rộng hoặc script hợp lệ bị xâm nhập vẫn có thể dẫn đến XSS.

### 7.3. Trusted Types

Trusted Types có thể giúp kiểm soát việc đưa chuỗi vào các DOM injection sink như innerHTML trong những trình duyệt hỗ trợ. Chính sách Trusted Types nên tập trung vào các hàm tạo nội dung đã được sanitize và tránh policy mặc định quá rộng.

Trusted Types giảm các đường DOM XSS phổ biến, nhưng không thay thế kiểm soát script, kiểm tra dependency hoặc xử lý dữ liệu đúng ngữ cảnh.

### 7.4. Quản lý dependency và script bên thứ ba

- Giảm số lượng script bên thứ ba và chỉ giữ thành phần thực sự cần.
- Pin phiên bản dependency, theo dõi advisory và cập nhật bản vá.
- Dùng lockfile và quy trình review thay đổi dependency.
- Dùng Subresource Integrity (SRI) cho tài nguyên tĩnh bên ngoài khi phù hợp.
- Kiểm soát tag manager, analytics và quyền phát hành script.
- Không cấp dữ liệu nhạy cảm hoặc token cho SDK bên thứ ba nếu không cần thiết.
- Tách nội dung không tin cậy sang origin riêng khi kiến trúc cho phép.

SRI giúp phát hiện tài nguyên không khớp hash đã khai báo; nó không bảo vệ trước mã độc được phát hành hợp lệ trong chính phiên bản mà ứng dụng đã tin cậy.

### 7.5. Cô lập nội dung không tin cậy

Nếu phải hiển thị nội dung do người dùng hoặc bên ngoài kiểm soát:

- Ưu tiên render dưới dạng text.
- Dùng iframe sandbox với quyền tối thiểu nếu cần hiển thị HTML phức tạp.
- Cân nhắc đặt nội dung trên origin riêng, không chia sẻ cookie/session với ứng dụng chính.
- Không cấp allow-same-origin hoặc allow-scripts cùng lúc cho iframe không tin cậy nếu không hiểu rõ hệ quả.
- Không để nội dung không tin cậy truy cập bridge/API có quyền rộng.

## 8. Giới hạn quyền và tác động nếu token bị lạm dụng

Giả định rằng token có thể bị sử dụng trong lúc ứng dụng đang chạy giúp thiết kế các giới hạn phù hợp:

- **Access token ngắn hạn:** giảm khoảng thời gian token bị lạm dụng sau khi bị lộ, nhưng không thay thế revoke hoặc session control.
- **Audience hẹp:** chỉ cấp token cho API cần thiết.
- **Scope tối thiểu:** chỉ cấp quyền cần thiết cho tác vụ.
- **Tách token theo mục đích:** không dùng một token đa năng cho nhiều API/ngữ cảnh không liên quan.
- **Refresh token rotation:** phát hiện việc sử dụng lại refresh token cũ theo chính sách của authorization server.
- **Revoke/session termination:** có quy trình chấm dứt phiên và thu hồi credential khi phát hiện xâm nhập.
- **Step-up authentication:** yêu cầu xác thực bổ sung cho thao tác rủi ro cao.
- **Rate limit và anomaly detection:** phát hiện hành vi API bất thường theo tài khoản, phiên và thiết bị.

Access token ngắn hạn có thể giảm cửa sổ sử dụng token đã bị đánh cắp, nhưng nếu mã độc vẫn chạy trong ứng dụng và có thể refresh, nó có thể tiếp tục lạm dụng phiên. Cần bảo vệ cả refresh/session credential và quy trình refresh.

## 9. Các sai lầm thường gặp

### 9.1. Cho rằng memory-only ngăn XSS

Mã độc không nhất thiết phải đọc token; nó có thể gọi API hoặc lạm dụng chức năng của ứng dụng.

**Cách xử lý:** xem memory-only là biện pháp giảm rủi ro persistence; tập trung ngăn script độc hại và giới hạn quyền phiên.

### 9.2. Đưa token lên biến global để tiện dùng

Một biến global dễ bị script khác cùng trang truy cập và làm lộ token trực tiếp.

**Cách xử lý:** giới hạn phạm vi tham chiếu token, tránh expose qua global, DOM, debug interface hoặc event không cần thiết.

### 9.3. Ghi token vào log hoặc telemetry

Token có thể bị lộ qua console log, error report, analytics, crash report, request tracing hoặc ảnh chụp màn hình hỗ trợ.

**Cách xử lý:** redact Authorization header, không log token/refresh token, kiểm soát dữ liệu telemetry và quyền truy cập log.

### 9.4. Nghĩ rằng Web Worker giải quyết hoàn toàn XSS

Worker cô lập heap và không truy cập DOM, nhưng trang vẫn có thể gọi message/API mà worker cung cấp.

**Cách xử lý:** thiết kế giao diện worker hẹp, xác thực message và giới hạn URL/method/operation; vẫn phải ngăn XSS.

### 9.5. Chỉ xóa token ở client khi logout

Xóa token trong memory không thu hồi token đã bị sao chép trước đó và không kết thúc session phía server.

**Cách xử lý:** kết hợp xóa state cục bộ với revoke/terminate session khi giao thức hỗ trợ; giới hạn lifetime và quyền token.

### 9.6. Chuyển token sang localStorage để duy trì đăng nhập

Điều này tăng persistence nhưng cũng khiến token dễ bị đọc bởi mọi script cùng origin.

**Cách xử lý:** cân nhắc BFF hoặc session cookie HttpOnly; nếu vẫn dùng browser storage, cần chấp nhận rõ threat model và tăng cường phòng thủ XSS.

### 9.7. Coi HttpOnly là biện pháp chống mọi tác động XSS

HttpOnly ngăn JavaScript đọc giá trị cookie, nhưng browser vẫn gửi cookie trong request phù hợp. XSS có thể gọi API bằng session hiện tại.

**Cách xử lý:** kết hợp HttpOnly/Secure/SameSite với CSRF protection, CSP, output encoding và quyền tối thiểu.

## 10. Mô hình lựa chọn theo threat model

| Bối cảnh | Hướng tiếp cận có thể cân nhắc | Rủi ro còn lại |
| --- | --- | --- |
| SPA gọi API trực tiếp, cần tránh lưu access token bền vững | Access token trong memory, thời hạn ngắn | XSS đang chạy vẫn có thể lạm dụng request |
| Ứng dụng cần session qua reload và muốn JS không đọc token | Cookie HttpOnly hoặc BFF | CSRF và XSS điều khiển request vẫn cần xử lý |
| Ứng dụng có nhiều script bên thứ ba | Giảm script, CSP, SRI, tách origin; cân nhắc BFF | Script được tin cậy nhưng bị xâm nhập vẫn có thể tác động |
| Nội dung người dùng có thể chứa HTML | Render text, sanitizer, Trusted Types, iframe sandbox/origin riêng | Lỗi sanitizer hoặc cấu hình sandbox vẫn có rủi ro |
| Yêu cầu giảm khả năng token bị dùng từ thiết bị khác | Sender-constrained token/DPoP theo profile | Script độc hại cùng ứng dụng có thể yêu cầu tạo proof |
| Thao tác có tác động cao | Step-up authentication, xác nhận phía server, scope hẹp | XSS có thể lừa người dùng hoặc gọi chức năng được cấp |

Không nên chọn nơi lưu chỉ theo sự tiện lợi của frontend. Cần xác định kẻ tấn công có thể thực thi script ở đâu, token có quyền gì, phiên tồn tại bao lâu và hệ thống có khả năng thu hồi ra sao.

## 11. Quy trình triển khai memory-only access token

Một quy trình tham khảo:

1. Xác định rõ access token chỉ dùng cho API nào và đặt lifetime ngắn theo rủi ro.
2. Nhận token qua TLS và kiểm tra kết quả xác thực theo giao thức.
3. Lưu token trong module/state riêng; không gắn vào window, DOM, URL hoặc log.
4. Chỉ cung cấp API client có chức năng hẹp; không expose getter trả token cho mọi thành phần.
5. Gắn token vào Authorization header ngay trước request tới API đích đã được cho phép.
6. Không chuyển tiếp token tới domain không nằm trong allowlist.
7. Gom các refresh request đồng thời; cập nhật token mới một cách nguyên tử.
8. Nếu refresh thất bại, phiên hết hạn hoặc bị thu hồi, xóa state và yêu cầu xác thực lại.
9. Khi logout, xóa state, dừng tác vụ đang chờ và kết thúc session/revoke phía server nếu có.
10. Kết hợp CSP, Trusted Types, output encoding, dependency control và kiểm soát script bên thứ ba.
11. Kiểm tra log, telemetry và error reporting để chắc chắn token không bị ghi lại.
12. Kiểm thử XSS theo threat model: thử truy cập state, gọi API client, gửi message tới worker và đọc response.

### 11.1. Mã giả quản lý token trong memory

```text
createSessionManager():
    private accessToken = null
    private refreshInFlight = null
    private sessionActive = false

    function setAccessToken(token):
        require token is valid response data
        accessToken = token
        sessionActive = true

    function authorizedRequest(allowedApi, request):
        require sessionActive
        require request.url belongs to allowedApi

        if accessToken is expired or near expiry:
            await refreshOnce()

        return sendRequest(
            request,
            Authorization = "Bearer " + accessToken
        )

    function refreshOnce():
        if refreshInFlight exists:
            return await refreshInFlight

        refreshInFlight = performConfiguredRefresh()
        try:
            newToken = await refreshInFlight
            accessToken = newToken
        catch error:
            clearSession()
            throw error
        finally:
            refreshInFlight = null

    function clearSession():
        accessToken = null
        sessionActive = false
        cancelPendingSessionWork()

    return only {
        authorizedRequest,
        clearSession
    }
```

Đây là mã giả mô tả nguyên tắc, không phải thư viện hoàn chỉnh. Một implementation thực tế phải xử lý lỗi mạng, refresh token rotation, đồng bộ nhiều tab, hủy request, race condition, kiểm tra token response và session termination. Việc giữ token trong closure giảm khả năng truy cập trực tiếp nhưng không ngăn script độc hại gọi authorizedRequest nếu script đó có thể truy cập đối tượng được expose.

## 12. Checklist bảo mật

- [ ] Đã xác định rõ token nào được giữ trong memory và token nào được lưu phía server/cookie.
- [ ] Access token không được lưu vào localStorage/IndexedDB nếu mục tiêu là memory-only.
- [ ] Token không xuất hiện trong URL, DOM, log, telemetry hoặc error report.
- [ ] Token chỉ được expose qua API hẹp, không đặt trong global state dễ truy cập.
- [ ] Request chỉ gửi token tới API/domain đã được cho phép.
- [ ] Access token có lifetime và scope tối thiểu.
- [ ] Refresh được gom để tránh nhiều request đồng thời; refresh token được bảo vệ và rotation được xử lý.
- [ ] Logout xóa state cục bộ và kết thúc/revoke session phía server nếu hỗ trợ.
- [ ] XSS được phòng thủ bằng output encoding, sanitizer phù hợp và tránh DOM injection sink nguy hiểm.
- [ ] CSP có policy cụ thể, không allowlist script quá rộng; Trusted Types được dùng khi phù hợp.
- [ ] Dependency và script bên thứ ba được giảm thiểu, review, pin phiên bản và kiểm soát nguồn.
- [ ] Web Worker (nếu dùng) có message/API hẹp và không hoạt động như confused deputy.
- [ ] Cookie HttpOnly (nếu dùng) có Secure, SameSite, Path/Domain phù hợp và CSRF protection.
- [ ] Có quy trình xử lý phiên bị xâm nhập, thu hồi token và xác thực bổ sung cho thao tác rủi ro cao.
- [ ] Đã kiểm thử tình huống mã độc cùng origin có thể gọi API dù không đọc được token.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Token trong memory có tồn tại qua reload trang không?

**Đáp án:** Thông thường không. Khi document/runtime bị hủy, state trong memory mất; ứng dụng cần quy trình khôi phục phiên riêng.

**Câu 2.** Vì sao memory-only không ngăn được XSS?

**Đáp án:** Script độc hại cùng origin có thể lạm dụng API hoặc dữ liệu mà ứng dụng truy cập được, ngay cả khi không đọc trực tiếp chuỗi token.

**Câu 3.** Web Worker có phải sandbox tuyệt đối trước XSS không?

**Đáp án:** Không. Worker cô lập global scope/heap nhưng script trang vẫn có thể gửi message và lạm dụng chức năng worker cung cấp.

**Câu 4.** HttpOnly cookie ngăn được điều gì và không ngăn được điều gì?

**Đáp án:** Ngăn JavaScript thông thường đọc giá trị cookie; không ngăn XSS gửi request cùng origin mà trình duyệt tự đính kèm cookie.

**Câu 5.** Vì sao cookie cần CSRF protection?

**Đáp án:** Vì trình duyệt tự động gửi cookie trong những ngữ cảnh phù hợp; một trang khác có thể tìm cách khiến trình duyệt gửi request mang session nếu hệ thống không kiểm tra nguồn và ý định request.

**Câu 6.** Xóa biến token khi logout có thu hồi token đã bị sao chép không?

**Đáp án:** Không. Cần cơ chế revoke/session termination phía server nếu được hỗ trợ; token đã sao chép vẫn có thể dùng cho tới khi hết hạn hoặc bị vô hiệu hóa.

**Câu 7.** Non-extractable Web Crypto key có ngăn mã độc sử dụng khóa không?

**Đáp án:** Không hoàn toàn. Nó hạn chế export key material, nhưng script có quyền gọi API ký vẫn có thể yêu cầu khóa thực hiện thao tác.

**Câu 8.** Memory-only nên được xem là lớp phòng thủ nào?

**Đáp án:** Là biện pháp giảm persistence và giảm khả năng lấy lại token từ storage sau khi runtime kết thúc; cần kết hợp phòng chống XSS, kiểm soát script, scope và lifetime.

## 14. Tài liệu tham khảo

- [OWASP Cheat Sheet Series — Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): quản lý session identifier, vòng đời phiên và bảo vệ session.
- [OWASP Cheat Sheet Series — HTML5 Security](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): lưu trữ phía trình duyệt và các lưu ý bảo mật HTML5.
- [OWASP Cheat Sheet Series — Cross Site Scripting Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): phòng chống XSS và output encoding.
- [OWASP Cheat Sheet Series — Content Security Policy](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): triển khai CSP.
- [OWASP Cheat Sheet Series — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): bảo vệ request sử dụng cookie/session.
- [W3C — Content Security Policy](https://www.w3.org/TR/CSP3/): đặc tả Content Security Policy.
- [W3C — Trusted Types](https://www.w3.org/TR/trusted-types/): kiểm soát dữ liệu đưa vào DOM injection sinks.
- [W3C — Web Cryptography API](https://www.w3.org/TR/WebCryptoAPI/): API mật mã trong trình duyệt và quản lý CryptoKey.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách truyền bearer token và các lưu ý bảo mật.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0, token và bảo vệ luồng cấp quyền.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): ràng buộc access token với khóa và proof-of-possession.

**Ghi nhớ:** Giữ access token trong memory làm giảm persistence trong browser storage, nhưng không ngăn mã độc đang chạy cùng origin sử dụng phiên. Web Worker và closure có thể giảm truy cập trực tiếp nhưng không tạo ranh giới tuyệt đối. Cần ngăn XSS, giảm script bên thứ ba, giới hạn token theo thời hạn/audience/scope, bảo vệ refresh/session credential và kết hợp CSRF protection khi dùng cookie.
