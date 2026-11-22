# XSS và những giới hạn của từng phương án lưu trữ token

## 1. XSS ảnh hưởng đến token như thế nào?

Cross-Site Scripting (XSS) xảy ra khi kẻ tấn công khiến mã JavaScript không được tin cậy chạy trong origin của ứng dụng. Mã độc khi chạy cùng origin thường có quyền tương tự JavaScript hợp lệ của trang: đọc DOM, truy cập dữ liệu mà trang có thể đọc, gọi API cùng origin và tương tác với các API trình duyệt được cấp cho trang.

Nếu access token hoặc refresh token được lưu ở nơi JavaScript truy cập được, XSS có thể đọc và gửi token ra ngoài. Nhưng ngay cả khi token được lưu trong cookie HttpOnly, XSS vẫn có thể thực hiện hành động dưới phiên hiện tại bằng cách gửi request từ trình duyệt. Vì vậy cần phân biệt hai rủi ro:

- **Token exfiltration:** mã độc đọc được giá trị token rồi gửi tới máy chủ của kẻ tấn công. Kẻ tấn công có thể tiếp tục sử dụng token bên ngoài trình duyệt cho tới khi token hết hạn hoặc bị thu hồi.
- **Authenticated action:** mã độc dùng chính trình duyệt của nạn nhân để gọi API bằng cookie/phiên hiện có. Dù không đọc được cookie HttpOnly, mã độc vẫn có thể gây ra hành động trái phép và đọc phản hồi mà JavaScript cùng origin được phép đọc.

JWT có chữ ký hợp lệ không ngăn việc đánh cắp hoặc phát lại token. Chữ ký chỉ giúp bên nhận xác minh tính toàn vẹn và nguồn gốc theo khóa tin cậy. Nếu kẻ tấn công lấy được bearer token, họ có thể sử dụng token đó trong phạm vi audience, scope và thời hạn mà token cho phép.

Do đó, không có lựa chọn lưu trữ nào tự biến một ứng dụng dễ bị XSS thành ứng dụng an toàn. Cần kết hợp phòng chống XSS, lựa chọn kiến trúc phiên/token, giới hạn quyền và quản lý vòng đời credential.

## 2. XSS có thể làm gì trong trình duyệt?

Khi JavaScript độc hại chạy trong origin của ứng dụng, nó có thể:

1. Đọc localStorage, sessionStorage, IndexedDB và dữ liệu JavaScript mà trang có thể truy cập.
2. Đọc token được giữ trong biến toàn cục, closure hoặc state của ứng dụng nếu tìm được đường truy cập; kể cả khi không đọc được trực tiếp, nó có thể gọi chức năng dùng token.
3. Gửi request cùng origin; trình duyệt tự đính kèm cookie phù hợp với request.
4. Đọc response từ API cùng origin hoặc từ origin khác nếu chính sách CORS cho phép.
5. Đọc dữ liệu DOM, form, nội dung hiển thị và những dữ liệu nhạy cảm khác mà trang đã tải.
6. Thay đổi giao diện, tạo form giả, đánh cắp thông tin người dùng hoặc thao túng thao tác trước khi gửi.
7. Duy trì hoạt động độc hại trong thời gian trang còn mở, hoặc cài persistence nếu ứng dụng cho phép các cơ chế lưu trữ/script phù hợp.

Một XSS có thể gây thiệt hại ngay cả khi token không thể bị trích xuất. Ví dụ, mã độc có thể gọi endpoint chuyển tiền bằng phiên hiện tại, thay đổi địa chỉ nhận hàng hoặc đọc dữ liệu cá nhân rồi gửi dữ liệu đó ra ngoài.

### Stored, reflected và DOM-based XSS

| Loại XSS | Cách xảy ra | Ví dụ |
| --- | --- | --- |
| Stored XSS | Payload độc hại được lưu ở máy chủ hoặc kho dữ liệu rồi hiển thị cho người dùng | Bình luận chứa HTML/script không được xử lý an toàn |
| Reflected XSS | Payload từ request được phản chiếu vào response mà không encode đúng ngữ cảnh | Giá trị query được chèn thẳng vào HTML |
| DOM-based XSS | JavaScript phía client đưa dữ liệu không tin cậy vào DOM sink nguy hiểm | Lấy location/hash rồi gán vào innerHTML |

Đối với token storage, cả ba loại đều có thể tạo cùng một kết quả: JavaScript chạy trong origin có thể truy cập dữ liệu và thực hiện request như ứng dụng.

## 3. So sánh các phương án lưu trữ token

Không nên chỉ hỏi “token nằm ở đâu là an toàn nhất?”. Cần xét token có thể bị đọc bởi JavaScript không, trình duyệt có tự gửi nó theo request không, dữ liệu tồn tại bao lâu và ứng dụng có thể giới hạn quyền ra sao.

| Phương án | JavaScript cùng origin đọc trực tiếp? | Trình duyệt tự gửi theo request? | Giới hạn chính |
| --- | --- | --- | --- |
| localStorage | Có | Không | XSS có thể đọc và exfiltrate token; dữ liệu tồn tại qua lần mở trình duyệt |
| sessionStorage | Có | Không | XSS có thể đọc token trong tab; phạm vi tồn tại ngắn hơn localStorage nhưng không tạo ranh giới chống XSS |
| IndexedDB | Có, qua API bất đồng bộ | Không | XSS cùng origin có thể truy cập database; không phải kho bí mật |
| JavaScript memory | Có thể truy cập hoặc sử dụng qua code của trang | Không | Giảm lưu trữ lâu dài, nhưng XSS đang chạy có thể dùng phiên hiện tại |
| Cookie HttpOnly | Không đọc bằng document.cookie | Có, theo domain/path/SameSite và điều kiện cookie | Giảm đánh cắp trực tiếp; tăng yêu cầu phòng CSRF |
| Backend-for-Frontend (BFF) | Browser không giữ access/refresh token của upstream | Browser gửi session cookie tới BFF | Giảm token exfiltration; XSS vẫn có thể gọi BFF dưới phiên người dùng |
| Web Worker/Service Worker | Không đọc trực tiếp state riêng của worker nếu thiết kế cô lập đúng | Worker có thể thực hiện request theo quyền được cấp | Không phải ranh giới chống XSS tuyệt đối; script độc hại có thể gọi API worker mà ứng dụng phơi bày |

### localStorage

localStorage lưu dữ liệu theo origin và tồn tại qua các lần đóng/mở tab hoặc trình duyệt cho tới khi bị xóa. Nó thuận tiện cho SPA cần giữ trạng thái đăng nhập sau reload, nhưng mọi JavaScript chạy cùng origin đều có thể đọc dữ liệu.

Nếu access token hoặc refresh token được lưu ở đây, XSS có thể đọc token và gửi ra ngoài. Refresh token thường có giá trị cao hơn vì có thể dùng để lấy access token mới; lưu refresh token dài hạn trong localStorage làm tăng hậu quả của XSS.

localStorage không tự gửi token theo request, nên không có cùng đặc tính CSRF tự động như cookie. Tuy nhiên, điều đó không bảo vệ khỏi XSS: script độc hại có thể đọc token rồi tự thêm Authorization header vào request, hoặc gọi API qua code ứng dụng.

### sessionStorage

sessionStorage thường gắn với một browsing context/tab và có vòng đời ngắn hơn localStorage. Đóng tab thường kết thúc phiên lưu trữ đó. Nhưng dữ liệu vẫn đọc được bởi JavaScript cùng origin, nên XSS trong tab có thể đánh cắp token hoặc dùng token để gọi API.

Việc token không tồn tại lâu sau khi đóng tab có thể giảm thời gian phơi nhiễm, nhưng không làm token an toàn trong thời gian trang đang hoạt động. sessionStorage không phải biện pháp phòng XSS.

### IndexedDB

IndexedDB là kho dữ liệu phía client hỗ trợ dữ liệu có cấu trúc và dung lượng lớn hơn Web Storage. Nó không phải secure storage. JavaScript cùng origin có thể mở database và đọc dữ liệu nếu biết schema hoặc tìm được object store.

Đưa token vào IndexedDB không ngăn XSS truy cập. Mã độc có thể enumerate database, gọi các API của ứng dụng để lấy dữ liệu hoặc chờ thao tác sử dụng token. IndexedDB phù hợp cho dữ liệu ứng dụng offline khi có kiểm soát, không phải nơi cất bearer credential để chống mã độc cùng origin.

### JavaScript memory

Giữ access token trong memory thay vì persistent storage giúp token biến mất khi trang/ứng dụng bị đóng hoặc reload, trừ khi token được lấy lại từ một cơ chế khác. Điều này giảm thời gian tồn tại của token trên thiết bị và tránh token nằm lâu trong localStorage/IndexedDB.

Tuy nhiên, memory không phải vùng bí mật chống XSS. Mã độc chạy trong cùng trang có thể gọi chức năng gửi request, hook API hoặc truy cập state nếu ứng dụng để lộ đường tham chiếu. Dù token được giữ trong closure, XSS vẫn có thể thao tác với ứng dụng trong thời gian phiên hoạt động.

Memory storage phù hợp hơn khi kết hợp access token ngắn hạn, Authorization Code + PKCE và một chiến lược refresh được thiết kế cẩn thận. Không nên cho rằng chỉ cần đưa token khỏi localStorage là đã giải quyết XSS.

### Cookie HttpOnly

Cookie có thuộc tính HttpOnly không thể được JavaScript đọc bằng document.cookie. Khi kết hợp Secure và SameSite phù hợp, cookie có thể giảm nguy cơ token/session identifier bị exfiltrate trực tiếp và hạn chế một số request cross-site.

Nhưng cookie được trình duyệt tự động gửi kèm request phù hợp. Nếu XSS chạy trong origin ứng dụng, nó vẫn có thể gửi request cùng origin bằng cookie phiên hiện tại. HttpOnly bảo vệ giá trị cookie khỏi việc đọc trực tiếp; nó không ngăn mã độc sử dụng phiên.

Cookie-based authentication còn phải phòng CSRF vì trình duyệt tự đính kèm cookie. Cần chọn SameSite, CSRF token, kiểm tra Origin/Referer và các biện pháp phù hợp với kiến trúc.

### Backend-for-Frontend (BFF)

Với BFF, browser giữ một session cookie (thường là opaque session identifier) còn access token/refresh token được lưu và sử dụng ở phía server. BFF gọi API downstream bằng access token tương ứng.

Lợi ích:

- JavaScript trong browser không có access token/refresh token của upstream để đọc trực tiếp.
- Token OAuth không phải đi qua Web Storage hoặc DOM.
- Server có thể quản lý refresh, rotation, revocation và token exchange tập trung.
- Browser chỉ cần cookie phiên với thuộc tính bảo vệ phù hợp.

Giới hạn:

- XSS vẫn có thể gửi request tới BFF bằng cookie HttpOnly đang hoạt động.
- Nếu BFF cho phép thao tác nhạy cảm mà không kiểm tra CSRF/ủy quyền, mã độc có thể thực hiện thao tác đó.
- BFF trở thành thành phần bảo mật quan trọng, cần quản lý session, CSRF, origin, rate limit và quyền downstream.
- Session cookie bị đánh cắp qua các kênh khác vẫn có thể bị lạm dụng cho tới khi hết hạn hoặc bị thu hồi.

BFF thường là lựa chọn mạnh khi muốn tránh để OAuth bearer token tồn tại trong JavaScript của browser, nhưng không thay thế việc phòng XSS.

## 4. HttpOnly giảm được điều gì và không giảm được điều gì?

HttpOnly là thuộc tính của cookie. Nó yêu cầu trình duyệt không cho script truy cập cookie qua các API như document.cookie. Đây là một biện pháp giảm khả năng đánh cắp giá trị cookie qua XSS.

Ví dụ cookie session:

~~~http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ý nghĩa:

- Secure: chỉ gửi cookie qua kết nối an toàn HTTPS, ngoại trừ các quy tắc đặc biệt của môi trường local được trình duyệt định nghĩa.
- HttpOnly: không cho JavaScript đọc cookie qua document.cookie.
- SameSite=Lax: hạn chế cookie được gửi trong một số ngữ cảnh cross-site; cần đánh giá luồng đăng nhập/redirect thực tế.
- Prefix __Host-: yêu cầu Secure, Path=/ và không có thuộc tính Domain, giúp cookie bị giới hạn theo host.

Cookie nên có thời hạn phù hợp với vòng đời session. Không dùng Max-Age/Expires quá dài chỉ để tránh đăng nhập lại; cần có idle timeout, absolute lifetime và cơ chế thu hồi session phía server.

### Kịch bản HttpOnly vẫn bị XSS lạm dụng

Giả sử ứng dụng có cookie HttpOnly và endpoint:

~~~http
POST /api/transfers HTTP/1.1
Host: app.example
Content-Type: application/json

{"to":"attacker-account","amount":1000}
~~~

Nếu XSS chạy trên app.example, script không thể đọc giá trị cookie nhưng có thể gửi fetch tới /api/transfers. Trình duyệt tự gửi cookie phù hợp. Nếu endpoint không có kiểm soát CSRF và kiểm tra quyền nghiệp vụ, giao dịch có thể được thực hiện.

HttpOnly vì vậy giúp giảm token theft, nhưng không ngăn authenticated action, data exfiltration từ response mà script có thể đọc, hoặc thao túng UI.

## 5. Cookie và CSRF: đánh đổi cần xử lý

CSRF xảy ra khi trình duyệt của người dùng bị dụ gửi request tới một site mà họ đã đăng nhập, và cookie xác thực tự động được đính kèm. Vì cookie tự gửi, API dựa vào cookie cần biện pháp chống CSRF.

### SameSite

| Giá trị | Hành vi khái quát | Lưu ý |
| --- | --- | --- |
| Strict | Cookie chỉ được gửi trong ngữ cảnh same-site | Bảo vệ mạnh hơn với một số luồng cross-site, nhưng có thể ảnh hưởng điều hướng từ site ngoài và luồng đăng nhập |
| Lax | Cookie được gửi trong phần lớn ngữ cảnh same-site và một số điều hướng top-level an toàn | Là lựa chọn cân bằng phổ biến; không thay thế toàn bộ CSRF defense |
| None | Cho phép cookie trong ngữ cảnh cross-site nếu đáp ứng yêu cầu Secure của trình duyệt | Cần thiết cho một số kiến trúc cross-site, nhưng yêu cầu CSRF defense chặt hơn |

SameSite dựa trên khái niệm site của trình duyệt, không hoàn toàn giống origin. Hai subdomain khác nhau có thể được xem là same-site; do đó không nên coi SameSite là biện pháp duy nhất để bảo vệ ứng dụng nhiều subdomain.

### CSRF defense bổ sung

Với cookie-authenticated state-changing request, cân nhắc kết hợp:

1. Synchronizer CSRF token hoặc signed double-submit token được ràng buộc với session.
2. Kiểm tra Origin; dùng Referer như phương án bổ sung khi phù hợp.
3. Fetch Metadata headers như Sec-Fetch-Site để từ chối request cross-site ngoài dự kiến.
4. Yêu cầu custom header cho API và cấu hình CORS chính xác; không cho phép origin tùy ý kết hợp credentials.
5. Không dùng GET cho thao tác thay đổi trạng thái.
6. Kiểm tra quyền và xác nhận bổ sung cho giao dịch nhạy cảm.

CORS không phải CSRF defense độc lập. CORS chủ yếu kiểm soát việc JavaScript ở origin khác có được đọc response hay không; một số request cross-site vẫn có thể được gửi mà không cần đọc response.

CSRF token cũng không phải cách phòng XSS. Nếu XSS chạy cùng origin, nó có thể thường đọc token CSRF từ DOM hoặc gọi endpoint lấy token rồi sử dụng nó. Phòng chống XSS và CSRF cần được triển khai song song.

## 6. BFF so với SPA giữ token trực tiếp

Hai kiến trúc thường gặp:

~~~mermaid
flowchart TD
    subgraph SPA["SPA giữ token trong browser"]
      A["Browser JavaScript"] --> B["localStorage / memory"]
      B --> C["Access token"]
      C --> D["Resource API"]
    end
    subgraph BFF["BFF giữ token phía server"]
      E["Browser"] --> F["HttpOnly session cookie"]
      F --> G["BFF server"]
      G --> H["Server-side token store"]
      H --> I["Access token"]
      I --> J["Resource API"]
    end
~~~

| Tiêu chí | SPA giữ token trực tiếp | BFF |
| --- | --- | --- |
| Token OAuth có trong JavaScript | Thường có nếu browser gọi API trực tiếp | Không cần đưa token upstream xuống browser |
| XSS đọc access token | Có thể nếu token ở Web Storage hoặc state có thể truy cập | Thường không đọc được token upstream |
| XSS thực hiện hành động | Có thể gọi API bằng token | Có thể gọi BFF bằng session cookie |
| CSRF | Bearer token trong Authorization header không tự gửi như cookie; vẫn cần đánh giá các endpoint khác | Cần CSRF defense cho cookie-authenticated request |
| Refresh token | Rất nhạy cảm nếu lưu trong browser; cần rotation và bảo vệ chặt | BFF có thể giữ và refresh ở server |
| Vận hành | Ít thành phần server hơn, nhưng browser chịu trách nhiệm quản lý token | Cần vận hành session store/BFF và bảo vệ server-side token |

BFF làm giảm khả năng lấy token OAuth thô từ browser, nhưng nếu ứng dụng có XSS, mã độc vẫn có thể hành động bằng phiên của người dùng. Với thao tác rủi ro cao, cần kiểm tra quyền phía server, re-authentication/step-up và xác nhận giao dịch theo policy.

## 7. Phòng chống XSS ở lớp ứng dụng

Lựa chọn nơi lưu token chỉ là một phần. Phòng XSS phải xử lý nơi dữ liệu không tin cậy đi vào HTML, DOM, script, URL và CSS.

### Encode theo đúng ngữ cảnh

- Khi đưa dữ liệu vào HTML text, dùng HTML text encoding.
- Khi đưa vào HTML attribute, dùng attribute encoding và tránh attribute nguy hiểm như event handler.
- Khi đưa vào JavaScript, CSS hoặc URL context, dùng quy tắc encoding riêng và tránh nối chuỗi động.
- Ưu tiên template/DOM API có auto-escaping.
- Không dùng một hàm encode chung cho mọi ngữ cảnh.

Input validation giúp kiểm tra dữ liệu theo schema, nhưng không thay thế output encoding. Dữ liệu hợp lệ về mặt nghiệp vụ vẫn có thể chứa ký tự cần encode khi hiển thị.

### Tránh DOM sink nguy hiểm

Không đưa dữ liệu không tin cậy trực tiếp vào:

- innerHTML, outerHTML hoặc document.write.
- eval, Function hoặc API thực thi chuỗi như mã.
- setTimeout/setInterval với chuỗi mã.
- URL điều hướng hoặc resource mà không kiểm tra scheme/host.
- Các thuộc tính event handler như onclick được tạo từ chuỗi.

Ưu tiên textContent, createElement, setAttribute với tên thuộc tính đã kiểm soát và các API DOM an toàn. Nếu phải hiển thị HTML giàu định dạng do người dùng tạo, dùng sanitizer được duy trì tốt với allowlist phần tử/thuộc tính; không tự viết bộ lọc bằng regex.

### Content Security Policy và Trusted Types

Content Security Policy (CSP) có thể giới hạn nguồn script, ưu tiên nonce/hash cho script được phép và giảm khả năng thực thi script inline tùy ý. CSP nên được triển khai theo từng giai đoạn: bắt đầu Report-Only, xử lý vi phạm hợp lệ, rồi chuyển sang enforce.

Tránh phụ thuộc vào unsafe-inline hoặc unsafe-eval nếu không có lý do đặc biệt. Trusted Types có thể giúp kiểm soát dữ liệu đi vào các DOM injection sink bằng cách yêu cầu tạo giá trị qua policy đã định nghĩa.

CSP và Trusted Types là lớp phòng thủ bổ sung. Chúng không bảo đảm ứng dụng không có XSS và không thay thế encode, sanitize, kiểm soát dependency hay review code.

### Kiểm soát script bên thứ ba

Script analytics, tag manager, quảng cáo, widget và dependency phía client chạy trong trang có thể có quyền đọc dữ liệu mà trang truy cập được. Giảm số lượng script bên thứ ba, pin phiên bản, dùng Subresource Integrity khi phù hợp, kiểm soát quyền cập nhật và giám sát thay đổi dependency.

Không đưa token vào global JavaScript object hoặc data attribute chỉ để nhiều script dễ truy cập. Giảm dữ liệu nhạy cảm có sẵn trong DOM và tránh đưa credential vào log, error report hoặc telemetry.

## 8. Quản lý vòng đời token để giảm tác động XSS

Ngay cả khi lựa chọn storage phù hợp, cần giảm giá trị và thời gian sử dụng của token:

- Access token có thời hạn ngắn, audience hẹp và scope tối thiểu.
- Refresh token cần được bảo vệ nghiêm ngặt; với public client, áp dụng refresh token rotation hoặc sender-constraining theo chính sách AS.
- Phát hiện refresh token reuse và thu hồi token family/session khi có dấu hiệu compromise theo chính sách.
- Có khả năng revoke session/token và vô hiệu hóa phiên ở server.
- Không cấp quyền quản trị chỉ dựa trên một claim chưa được kiểm tra theo profile.
- Yêu cầu step-up/re-authentication cho thao tác nhạy cảm.
- Không ghi access token, refresh token, cookie session hoặc Authorization header vào log.
- Không đặt token trong query string, URL fragment, analytics event hoặc browser history.

### DPoP và sender-constrained token

DPoP hoặc mTLS có thể giảm giá trị của token bị đánh cắp bằng cách ràng buộc token với khóa/chứng thư của client. Nhưng nếu XSS chạy trong browser, nó có thể cố gắng sử dụng chức năng ký proof mà ứng dụng cung cấp hoặc thực hiện request ngay trong trình duyệt.

Khóa WebCrypto không extractable có thể làm khó việc xuất private key thô, nhưng không tự ngăn mã độc cùng origin gọi API ký nếu ứng dụng phơi bày chức năng đó. Sender constraint giúp giảm replay từ môi trường khác; nó không phải biện pháp chữa XSS.

## 9. Các phương án lưu trữ theo từng bối cảnh

### SPA gọi API trực tiếp

Nếu browser trực tiếp gọi resource server:

1. Ưu tiên Authorization Code Flow với PKCE cho public client.
2. Giữ access token trong memory nếu có thể đáp ứng trải nghiệm và refresh strategy.
3. Tránh lưu refresh token dài hạn trong localStorage hoặc sessionStorage.
4. Nếu AS cấp refresh token cho public client, tuân thủ yêu cầu rotation hoặc sender-constraining và phát hiện reuse theo RFC 9700.
5. Giới hạn access token theo audience, scope và thời hạn.
6. Phòng XSS ở toàn bộ origin; không coi memory là ranh giới bảo mật.

### Ứng dụng browser dùng cookie session

Nếu server quản lý session:

1. Dùng cookie session với Secure, HttpOnly và SameSite phù hợp.
2. Ưu tiên cookie host-only; cân nhắc prefix __Host- với Path=/ và không có Domain.
3. Bảo vệ state-changing request bằng CSRF token và kiểm tra origin/Fetch Metadata.
4. Xoay session identifier sau đăng nhập hoặc thay đổi đặc quyền.
5. Đặt idle timeout, absolute lifetime và thu hồi session phía server.
6. Vẫn phòng XSS vì mã độc có thể thao tác qua session cookie.

### BFF

Nếu ứng dụng cần tránh đưa access/refresh token xuống browser:

1. Giữ OAuth token ở server-side token store.
2. Browser chỉ giữ session cookie bảo vệ bằng Secure, HttpOnly, SameSite.
3. BFF kiểm tra CSRF, Origin, quyền, audience và scope trước khi gọi downstream.
4. Không tạo endpoint proxy tùy ý cho browser truyền URL hoặc token đích.
5. Giới hạn token theo resource và scope; refresh/revoke ở server.
6. Xử lý XSS như nguy cơ thao tác trái phép dưới phiên, dù token thô không lộ.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi localStorage là nơi an toàn để giữ JWT | XSS có thể đọc và exfiltrate token | Dùng kiến trúc và storage theo threat model; giảm thời hạn và quyền |
| Chuyển token sang sessionStorage rồi cho rằng đã hết XSS | XSS trong tab vẫn đọc được token | Hiểu sessionStorage chỉ giới hạn vòng đời/phạm vi, không chống XSS |
| Cất token trong IndexedDB để “ẩn” khỏi JavaScript | Script cùng origin vẫn truy cập database | Không dùng IndexedDB như secure storage |
| Giữ token trong memory rồi cho rằng closure bảo vệ tuyệt đối | XSS vẫn có thể gọi chức năng sử dụng token hoặc đọc state có thể truy cập | Giảm token exposure và phòng XSS; cân nhắc BFF |
| Dùng HttpOnly nhưng không phòng CSRF | Cookie tự gửi theo request có thể bị lợi dụng | SameSite, CSRF token, Origin và Fetch Metadata |
| Nghĩ HttpOnly chặn mọi tác động của XSS | XSS vẫn có thể gọi API và đọc response cùng origin | Phòng XSS và kiểm tra quyền phía server |
| Dùng SameSite=None mà không có CSRF defense | Cookie được gửi trong ngữ cảnh cross-site | Bổ sung CSRF defense và cấu hình Secure |
| Cho phép CORS mọi origin cùng credentials | Origin không tin cậy có thể đọc response nhạy cảm | Allowlist origin chính xác; không dùng wildcard với credentials |
| Đặt access/refresh token trong URL | Token có thể lọt vào history, logs, referrer và telemetry | Truyền qua Authorization header hoặc cơ chế an toàn theo giao thức |
| Cho rằng DPoP tự ngăn XSS | XSS có thể dùng chức năng ký/request trong browser | Xem DPoP là giảm replay; vẫn phải phòng XSS |
| Chỉ encode input mà không encode output | Payload vẫn có thể trở thành script ở context khác | Encode theo đúng output context và sanitize HTML khi cần |
| Dùng regex tự lọc HTML | Bỏ sót cú pháp và parser edge cases | Dùng sanitizer đã được duy trì với allowlist |
| CSP có unsafe-inline/unsafe-eval rộng | Giảm hiệu quả hạn chế script injection | Dùng nonce/hash, report-only rồi enforce |
| Để script bên thứ ba đọc token toàn cục | Rò rỉ credential qua dependency hoặc tag manager | Giảm script, cô lập, kiểm soát supply chain và không phơi token |

## 11. Bộ ca kiểm thử

Giả sử ứng dụng có access token và session cookie, API có thao tác đọc/ghi dữ liệu và một endpoint chuyển tiền.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| XSS thử đọc localStorage có access token | Mô phỏng cho thấy token có thể bị đọc; đây là rủi ro cần loại bỏ hoặc giảm bằng kiến trúc |
| XSS thử đọc sessionStorage/IndexedDB | Dữ liệu cùng origin có thể bị đọc; không coi các kho này là ranh giới bảo mật |
| XSS chạy khi access token ở memory | Không giả định token an toàn; kiểm tra mã độc có thể gọi API qua code/state của ứng dụng |
| XSS gọi API cùng origin khi cookie HttpOnly tồn tại | Request có thể mang cookie; server phải áp dụng quyền và kiểm soát hành động |
| JavaScript đọc document.cookie với cookie HttpOnly | Không đọc được giá trị cookie HttpOnly |
| Request thay đổi trạng thái từ site cross-site với SameSite=Lax | Kiểm tra hành vi trình duyệt thực tế và CSRF defense bổ sung |
| Request cross-site với SameSite=None; Secure | Cookie có thể được gửi; CSRF defense phải chặn request không hợp lệ |
| Request không có CSRF token hợp lệ | Từ chối thao tác thay đổi trạng thái |
| Origin không nằm trong allowlist | Từ chối request theo policy |
| CORS wildcard kết hợp credentials | Không cho phép cấu hình này; kiểm tra cấu hình bị từ chối |
| Token xuất hiện trong query string hoặc log | Kiểm thử phải phát hiện và loại bỏ vị trí rò rỉ |
| CSP nonce không hợp lệ cho script inline | Trình duyệt chặn script theo policy |
| Payload người dùng được render bằng textContent | Hiển thị như văn bản, không thực thi HTML/script |
| Rich HTML qua sanitizer allowlist | Chỉ phần tử/thuộc tính được phép còn lại |
| Token downstream bị lộ nhưng đã hết hạn/thu hồi | Resource server từ chối token |
| Access token có audience/scope không phù hợp | Resource server từ chối dù chữ ký hợp lệ |
| DPoP token bị phát lại từ client không có khóa phù hợp | Proof-of-possession validation thất bại |

Kiểm thử XSS phải chạy trong môi trường kiểm thử được kiểm soát. Không dùng payload gây tác động tới tài khoản hoặc dữ liệu thật. Mục tiêu là xác nhận token không bị phơi bày, request trái phép bị chặn và không có quyền được cấp trước khi server kiểm tra đầy đủ.

## 12. Ghi nhớ

- XSS cho phép mã độc chạy cùng origin; nó có thể đọc Web Storage và dùng phiên hiện tại để gọi API.
- localStorage, sessionStorage và IndexedDB đều đọc được bởi JavaScript cùng origin; không phải secure storage chống XSS.
- Memory giảm lưu trữ lâu dài nhưng không ngăn XSS hoạt động trong phiên đang mở.
- HttpOnly ngăn JavaScript đọc trực tiếp cookie, nhưng browser vẫn tự gửi cookie; XSS có thể thực hiện authenticated action.
- Cookie authentication cần CSRF defense. SameSite hữu ích nhưng không thay thế CSRF token, kiểm tra Origin và policy server.
- BFF giữ access/refresh token phía server giúp giảm token exfiltration từ browser; XSS vẫn có thể gọi BFF dưới phiên hiện tại.
- Phòng XSS bằng output encoding theo ngữ cảnh, DOM API an toàn, sanitizer phù hợp, CSP, Trusted Types và kiểm soát script bên thứ ba.
- Access token ngắn hạn, scope/audience hẹp, refresh token rotation, sender constraint và khả năng revoke giúp giảm tác động khi credential bị lộ.
- Không đặt token trong URL, browser history, log hoặc telemetry.
- Không có lựa chọn lưu trữ nào thay thế việc phòng XSS và kiểm tra quyền ở server.

### Tài liệu tham khảo

- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): encode theo ngữ cảnh, sanitizer và các DOM sink.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): giới hạn bảo mật của localStorage và sessionStorage.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie flags và quản lý vòng đời session.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): SameSite, CSRF token, Origin và Fetch Metadata.
- [OWASP Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): triển khai CSP theo hướng defense in depth.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookie và thuộc tính quản lý cookie.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ OAuth token, refresh token rotation và sender-constrained token.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): PKCE cho OAuth public clients.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): ràng buộc access token với khóa của client.
