# Service worker độc hại: phân tích sự cố và khôi phục an toàn

Service worker là một script chạy trong background của browser, có thể điều phối request của các trang thuộc phạm vi kiểm soát, phục vụ nội dung từ cache và xử lý sự kiện như push hoặc background sync. Cơ chế này hỗ trợ ứng dụng web hoạt động offline và cải thiện hiệu năng. Nếu service worker bị thay thế bằng mã độc, browser có thể tiếp tục sử dụng logic độc hại ngay cả sau khi server đã được sửa.

Case study này mô phỏng sự cố một service worker trên cổng khách hàng bị thay đổi sau một lần triển khai frontend. Worker mới kiểm soát các trang trong scope của ứng dụng, trả về nội dung đã bị sửa từ Cache Storage và quan sát một số request của người dùng. Nhóm ứng phó phải xác định worker nào đang kiểm soát browser, bảo toàn bằng chứng, ngăn mã độc tiếp tục được phân phối, thu hồi credential có khả năng bị lộ, làm sạch trạng thái browser và xác minh bản worker hợp lệ đã hoạt động.

Bài học đặt sự cố trong bối cảnh bảo mật browser: origin, cookie, Same-Origin Policy, CSP, cache, XSS, pipeline phát hành và quyền của service worker. Các bước thực hành chỉ dùng môi trường lab hoặc hệ thống bạn được phép kiểm thử.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích service worker, registration, scope, lifecycle và client control.
- Nhận diện cách một worker độc hại có thể tác động tới trang và request.
- Phân biệt service worker độc hại với extension, XSS và nội dung cache cũ.
- Xác định registration, script URL, scope, trạng thái và các client bị kiểm soát.
- Thu thập bằng chứng trước khi unregister hoặc xóa cache.
- Containment từ server, CDN, deployment pipeline và browser.
- Đánh giá token, session và dữ liệu có thể đã bị truy cập.
- Xử lý Cache Storage, IndexedDB, push subscription và background sync.
- Khôi phục worker sạch mà không để browser tiếp tục tải bản độc hại.
- Thiết kế kiểm soát triển khai, CSP, cache header và giám sát để ngăn tái diễn.

## 1. Bối cảnh case study

Một doanh nghiệp vận hành cổng khách hàng tại `https://portal.example.test`. Ứng dụng dùng service worker ở đường dẫn `/app/sw.js` với scope `/app/` để cache shell ứng dụng, ảnh, stylesheet và một số response phục vụ chế độ offline.

Sau một lần phát hành frontend, đội hỗ trợ nhận được nhiều báo cáo:

- Một số người dùng thấy biểu mẫu đăng nhập có nội dung và giao diện khác thường.
- Một số trang tiếp tục hiển thị JavaScript cũ dù CDN đã được cập nhật.
- DevTools cho thấy request tới `/app/` được trả từ service worker.
- Một vài người dùng báo tài khoản có hoạt động không do họ thực hiện.
- Browser trên thiết bị đã đóng mở lại vẫn tải nội dung bất thường.

Điều tra ban đầu cho thấy registration đang hoạt động tại scope `/app/`, nhưng script URL và nội dung script không khớp artifact của release đã phê duyệt. Cache Storage chứa một số entry không thuộc danh sách cache của ứng dụng. Nhóm ứng phó nghi ngờ worker đã bị thay thế thông qua pipeline frontend bị xâm nhập hoặc một script cùng origin có quyền đăng ký worker.

### 1.1 Kiến trúc trước sự cố

~~~text
Browser
  |
  | HTTPS
  v
https://portal.example.test
  |
  +-- /app/index.html
  |
  +-- /app/assets/*
  |
  +-- /app/sw.js
        |
        +-- scope: /app/
        +-- Cache Storage: app-shell-v12
        +-- fetch handler
        +-- offline fallback
~~~

Trang trong scope có thể được service worker kiểm soát sau khi registration được kích hoạt và client nhận quyền control. Khi một client đã được kiểm soát, worker có thể nhận các sự kiện fetch từ client đó và quyết định trả response từ network, cache hoặc logic fallback.

### 1.2 Giả thuyết sự cố

Nhóm đưa ra các giả thuyết cần kiểm chứng:

1. Pipeline hoặc tài khoản triển khai bị xâm nhập, khiến file worker bị thay đổi.
2. Một lỗ hổng XSS hoặc script bên thứ ba chạy cùng origin đã đăng ký worker ngoài dự kiến.
3. File worker hợp lệ bị thay thế tại CDN, static hosting hoặc object storage.
4. Một worker cũ vẫn hoạt động và tiếp tục phục vụ cache cũ sau khi server đã phát hành bản sửa.
5. Extension hoặc phần mềm trên endpoint can thiệp vào trang, khiến hiện tượng bị nhầm là service worker độc hại.

Không kết luận nguyên nhân chỉ từ việc thấy nội dung cũ hoặc request có nhãn “from ServiceWorker”. Cần đối chiếu registration, script thực tế, release artifact và log phân phối.

## 2. Service worker hoạt động như thế nào?

Service worker là một loại Web Worker gắn với một origin và một scope. Nó chạy trong môi trường riêng, không có quyền truy cập trực tiếp vào DOM của trang, nhưng có thể giao tiếp với các client qua message và xử lý những sự kiện được browser gửi tới.

Service worker thường được dùng cho:

- Intercept request từ các client đang được kiểm soát.
- Cache tài nguyên và response.
- Trả nội dung offline.
- Nhận push event.
- Xử lý background sync khi browser hỗ trợ.
- Quản lý trải nghiệm cài đặt ứng dụng web.

Service worker yêu cầu secure context, thông thường là HTTPS. `localhost` được browser xem là secure context cho mục đích phát triển. Script đăng ký phải cùng origin với document đăng ký.

### 2.1 Registration và scope

Trang đăng ký worker:

~~~javascript
navigator.serviceWorker.register("/app/sw.js", {
  scope: "/app/"
});
~~~

Registration liên kết một script URL với một scope. Scope xác định các document URL có thể được worker kiểm soát. Mặc định scope thường dựa trên thư mục chứa script; tùy chọn `scope` có thể thu hẹp phạm vi đó.

Response của script có thể dùng header `Service-Worker-Allowed` để cho phép scope rộng hơn thư mục mặc định. Vì vậy, cần kiểm tra cả URL script, scope được yêu cầu và header server trả về.

Ví dụ:

~~~http
Service-Worker-Allowed: /
~~~

Header này có thể cho phép script ở `/app/sw.js` đăng ký scope rộng hơn `/app/`, trong trường hợp ứng dụng chủ động thiết kế như vậy. Nếu header bị thêm ngoài dự kiến, phạm vi kiểm soát có thể lớn hơn dự định.

### 2.2 Lifecycle

Lifecycle cơ bản có các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **installing** | Browser đang cài worker mới |
| **installed / waiting** | Worker đã cài nhưng có thể phải chờ worker cũ và các client |
| **activating** | Worker đang kích hoạt |
| **activated** | Worker đã kích hoạt và có thể xử lý sự kiện |
| **redundant** | Worker không còn được dùng, ví dụ cài đặt thất bại hoặc bị thay thế |

Worker mới thường chờ worker cũ kết thúc vòng đời và các client cũ không còn bị kiểm soát. Code có thể gọi `skipWaiting()` để yêu cầu worker mới bỏ qua giai đoạn chờ. Sau khi activate, `clients.claim()` có thể yêu cầu worker nhận quyền kiểm soát các client phù hợp đang mở.

Hai API này hữu ích trong triển khai bình thường nhưng làm thay đổi thời điểm chuyển worker. Nếu mã độc gọi chúng, worker mới có thể nhanh chóng tiếp quản các trang đang mở.

### 2.3 Worker và client control

Một document có thể kiểm tra worker đang kiểm soát nó:

~~~javascript
const controller = navigator.serviceWorker.controller;

console.log(controller ? controller.scriptURL : "No controller");
~~~

`navigator.serviceWorker.controller` cho biết worker hiện đang kiểm soát document. Giá trị này có thể là `null` nếu trang chưa được kiểm soát.

Một registration có thể có `installing`, `waiting` và `active` worker. Cần kiểm tra cả ba, vì worker đáng ngờ có thể đang chờ kích hoạt hoặc worker cũ vẫn còn hoạt động.

### 2.4 Worker không có DOM nhưng vẫn có quyền đáng kể

Service worker không thể trực tiếp gọi `document.querySelector()` hoặc đọc DOM như script trong trang. Tuy nhiên, worker có thể:

- Quan sát request được gửi từ client đang bị kiểm soát.
- Thay đổi response mà client nhận được.
- Trả HTML, JavaScript hoặc JSON đã bị chỉnh sửa.
- Phục vụ nội dung từ cache do nó quản lý.
- Gửi request mạng trong giới hạn của browser và policy áp dụng.
- Giao tiếp với client bằng message.
- Xử lý push hoặc background sync nếu được cấu hình.

Một worker độc hại có thể làm trang tải script bị sửa hoặc làm thay đổi nội dung UI. Nếu trang thực thi nội dung đó, tác động có thể lan tới JavaScript context của trang.

### 2.5 Giới hạn của service worker

Không phóng đại quyền của worker:

- Worker không trực tiếp đọc DOM.
- Worker không thể đọc cookie `HttpOnly` bằng `document.cookie`.
- Worker chỉ kiểm soát các client thuộc registration và scope của nó.
- Worker không tự động vượt qua Same-Origin Policy hoặc CORS.
- CORS và request mode vẫn ảnh hưởng việc đọc response cross-origin.
- Worker không có quyền tùy ý đọc mọi dữ liệu của browser hoặc các origin khác.

Tuy nhiên, worker có thể tác động tới request do client được kiểm soát khởi tạo. Nếu client dùng session cookie để gọi API cùng origin, worker độc hại có thể quan sát hoặc thay đổi luồng request/response trong phạm vi browser cho phép. Vì vậy cookie `HttpOnly` không đủ để loại bỏ rủi ro từ worker độc hại.

## 3. Service worker độc hại có thể gây ra điều gì?

Mức độ ảnh hưởng phụ thuộc vào scope, client được kiểm soát, loại request, dữ liệu trong response và các quyền mà ứng dụng cấp cho worker.

### 3.1 Phục vụ nội dung đã bị sửa

Worker có thể trả response từ cache thay vì network hoặc sửa nội dung trước khi trả cho trang. Hậu quả có thể gồm:

- Trang đăng nhập giả mạo được hiển thị trong origin hợp lệ.
- JavaScript ứng dụng bị thay bằng phiên bản độc hại.
- Nội dung thông báo hoặc giao dịch bị thay đổi.
- Trang hiển thị dữ liệu cũ hoặc dữ liệu không chính xác.
- Một số request được trả về response giả để che giấu hoạt động.

Nếu worker trả nội dung từ cùng origin, browser có thể xem nội dung đó như nội dung của ứng dụng gốc. Đây là lý do worker độc hại có thể nguy hiểm ngay cả khi HTTPS vẫn hợp lệ.

### 3.2 Quan sát request và response

Fetch handler có thể nhận event cho request do client được kiểm soát khởi tạo. Worker có thể kiểm tra metadata request và, tùy loại response, xử lý dữ liệu response trước khi trả về client.

Phạm vi thực tế phụ thuộc request mode, credentials, CORS, response type và policy của browser. Không giả định worker có thể đọc mọi response cross-origin hoặc bỏ qua CORS.

### 3.3 Tác động tới session và token

Worker không đọc trực tiếp cookie `HttpOnly`, nhưng có thể ảnh hưởng luồng request được gửi từ trang có session. Ví dụ, nó có thể thay đổi form hoặc script được phục vụ để khiến trang thực hiện hành động không mong muốn.

Nếu access token nằm trong Web Storage hoặc biến JavaScript của trang, nội dung script độc hại được worker phân phối có thể tìm cách đọc token trong context trang. Vì vậy cần đánh giá XSS và nơi lưu token cùng lúc với điều tra worker.

### 3.4 Duy trì nội dung độc hại qua cache

Cache Storage tồn tại độc lập với việc một tab đã đóng. Worker có thể lưu shell hoặc asset đã bị sửa để phục vụ trong lần truy cập tiếp theo, kể cả khi server đã phát hành bản sạch.

Unregister worker không tự động chứng minh mọi cache, IndexedDB hoặc dữ liệu đã lưu đều được xóa. Phải kiểm kê và xử lý các vùng lưu trữ liên quan.

### 3.5 Push notification và background sync

Nếu ứng dụng có push subscription hoặc background sync, worker có thể nhận các event đó. Worker độc hại có thể hiển thị notification giả hoặc thực hiện tác vụ nền ngoài dự kiến.

Cần kiểm tra push subscription, endpoint liên quan, dữ liệu sync queue và permission notification. Thu hồi subscription ở server và browser khi cần; gỡ worker không thay thế việc thu hồi dữ liệu đăng ký ở backend.

## 4. Các con đường cài đặt worker độc hại

Service worker script phải được đăng ký từ cùng origin với trang đăng ký, nhưng một attacker có thể chiếm quyền phân phối nội dung của origin đó theo nhiều cách.

### 4.1 XSS trong origin

Nếu attacker thực thi JavaScript trong một trang cùng origin, script có thể gọi `navigator.serviceWorker.register()` với một file script cùng origin mà attacker có thể khiến server phân phối.

Điều kiện quan trọng là attacker phải có khả năng khiến browser tải script worker hợp lệ theo quy tắc same-origin. XSS đơn thuần không tự tạo ra quyền ghi file lên server, nhưng có thể tận dụng upload endpoint, file script sẵn có, cấu hình sai hoặc quyền triển khai bị lộ.

### 4.2 Pipeline CI/CD hoặc tài khoản triển khai bị xâm nhập

Attacker có quyền ghi static asset hoặc pipeline có thể thay `/app/sw.js`, thêm mã vào bundle hoặc thay đổi header `Service-Worker-Allowed`.

Dấu hiệu cần kiểm tra:

- Commit hoặc release không được phê duyệt.
- Artifact hash khác build đã ký.
- Tài khoản deploy đăng nhập bất thường.
- Workflow hoặc secret CI/CD bị thay đổi.
- Object storage/CDN có upload ngoài lịch.
- File worker được sửa mà không có thay đổi source tương ứng.

### 4.3 CDN, static hosting hoặc object storage bị cấu hình sai

Nếu origin phục vụ worker lấy file từ bucket hoặc CDN, người có quyền ghi vào vùng lưu trữ có thể thay nội dung worker. Cần kiểm tra ACL, upload token, deployment role, cache purge và lịch sử object version.

HTTPS chỉ bảo vệ đường truyền tới endpoint được tin cậy; nó không bảo đảm file được phục vụ từ endpoint đó là artifact đúng.

### 4.4 Dependency hoặc build plugin bị xâm nhập

Một dependency, plugin build hoặc script postinstall có thể chèn mã vào bundle hoặc file worker. Kiểm tra lockfile, dependency diff, provenance, build log và artifact output.

Nếu worker được tạo từ source code hoặc template trong pipeline, so sánh cả source lẫn artifact. Source sạch không chứng minh artifact sạch nếu build environment bị xâm nhập.

### 4.5 Scope quá rộng

Một worker được đăng ký ở scope `/` có thể kiểm soát nhiều trang hơn worker chỉ có scope `/app/`. Header `Service-Worker-Allowed` có thể mở rộng scope tối đa mà script được phép yêu cầu.

Nếu một ứng dụng nhỏ có worker scope rộng ở origin dùng chung, sự cố có thể ảnh hưởng các ứng dụng khác cùng origin. Kiến trúc nên giới hạn scope ở mức nhỏ nhất cần thiết và tránh chia sẻ origin giữa các ứng dụng có mức tin cậy khác nhau.

### 4.6 Extension hoặc phần mềm endpoint

Extension có thể inject script vào trang hoặc thay đổi hành vi browser. Một số dấu hiệu nhìn giống worker độc hại nhưng không có registration lạ.

Cần kiểm tra profile browser sạch, danh sách extension được phép và thiết bị khác. Nếu hiện tượng chỉ xảy ra trên một máy, không vội kết luận server hoặc worker bị xâm nhập.

## 5. Dựng timeline sự cố

Case study sử dụng timeline giả lập:

| Thời điểm | Sự kiện | Ý nghĩa |
|---|---|---|
| 09:00 | Release frontend được phê duyệt | Mốc artifact chuẩn |
| 09:18 | File /app/sw.js trên CDN thay đổi | Cần đối chiếu với release |
| 09:22 | Browser bắt đầu tải worker mới | Có thể phát sinh registration/update |
| 09:24 | Worker chuyển sang active | Client mới có thể bị kiểm soát |
| 09:40 | Người dùng báo UI bất thường | Dấu hiệu tác động |
| 10:05 | Đội vận hành phát hiện cache lạ | Mở rộng phạm vi điều tra |
| 10:12 | Incident được khai báo | Bắt đầu containment |
| 10:20 | CDN và static hosting bị khóa quyền ghi bất thường | Ngăn tái phân phối |
| 10:28 | Worker sạch được phát hành tại script URL | Cho browser cập nhật |
| 10:45 | Session và token có nguy cơ bị lộ được revoke | Giảm nguy cơ chiếm tài khoản |
| 11:10 | Client test xác nhận worker sạch | Kiểm tra khôi phục |
| Sau đó | Theo dõi các client còn dùng worker cũ | Xác minh phạm vi còn lại |

Các mốc trên chỉ phục vụ bài tập. Trong sự cố thực tế, phải dùng timestamp từ log và ghi rõ timezone, độ lệch đồng hồ và mức độ tin cậy của từng nguồn.

### 5.1 Câu hỏi điều tra

- Worker bắt đầu bị thay đổi từ thời điểm nào?
- File worker được phân phối từ server, CDN hay bucket nào?
- Registration có scope gì?
- Có bao nhiêu browser client đang bị kiểm soát?
- Worker gọi `skipWaiting()` hoặc `clients.claim()` không?
- Cache nào được tạo hoặc sửa?
- Request/API nào có thể đã bị quan sát hoặc thay đổi?
- Có token, session hoặc dữ liệu nhạy cảm trong luồng bị ảnh hưởng không?
- Worker có nhận push hoặc background sync không?
- Có ứng dụng nào khác cùng origin bị ảnh hưởng không?

## 6. Phát hiện worker đáng ngờ trong browser

Trước khi unregister hoặc xóa cache, cần thu thập thông tin đủ để xác định worker và phạm vi. Nếu có thể, dùng browser profile điều tra riêng hoặc bản sao profile để bảo toàn bằng chứng.

### 6.1 Kiểm tra worker đang kiểm soát trang

Trong DevTools Console:

~~~javascript
const controller = navigator.serviceWorker.controller;

({
  controlled: Boolean(controller),
  scriptURL: controller?.scriptURL ?? null
});
~~~

So sánh script URL với kiến trúc và release được phê duyệt. Một script URL lạ là tín hiệu điều tra, nhưng URL đúng cũng không chứng minh nội dung script an toàn.

### 6.2 Liệt kê registration

~~~javascript
const registrations = await navigator.serviceWorker.getRegistrations();

registrations.map((registration) => ({
  scope: registration.scope,
  active: registration.active?.scriptURL ?? null,
  activeState: registration.active?.state ?? null,
  waiting: registration.waiting?.scriptURL ?? null,
  installing: registration.installing?.scriptURL ?? null
}));
~~~

Đoạn này liệt kê registration của origin hiện tại. Không dùng output để suy ra registration ở origin khác; mỗi origin có storage và registration riêng.

### 6.3 Kiểm tra trong DevTools

Trong Chrome/Chromium DevTools, mở Application panel và xem Service Workers:

- Scope của registration.
- Script URL.
- Trạng thái worker.
- Client đang được kiểm soát.
- Console của worker.
- Nút update hoặc unregister trong môi trường điều tra.

Trong Cache Storage, kiểm tra tên cache và entry. Ghi lại URL, timestamp, response header và nội dung mẫu phù hợp với quy trình evidence. Không mở hoặc chia sẻ file chứa token raw nếu chưa redact.

Tên cache lạ có thể là dấu hiệu, nhưng ứng dụng có thể tạo cache động. Cần so sánh với danh sách cache dự kiến từ release.

### 6.4 Kiểm tra Network

Lọc request liên quan tới script worker và tài nguyên do worker trả về:

- Request tới script URL.
- Header response, ETag, Last-Modified và Cache-Control.
- Initiator và thông tin “from ServiceWorker”.
- Request bị trả về từ cache.
- Request outbound bất thường từ client.
- Response có hash hoặc nội dung khác release.

“From ServiceWorker” chỉ cho biết worker tham gia xử lý request; nó không tự chứng minh worker độc hại.

### 6.5 Phân biệt worker cũ với worker độc hại

Một worker cũ có thể tiếp tục hoạt động do lifecycle bình thường. So sánh:

- Script URL và scope.
- Hash nội dung script.
- Version cache.
- Release ID trong asset.
- Logic install/activate/fetch.
- Thay đổi so với artifact đã phê duyệt.
- Thời điểm browser cập nhật worker.

Nếu nội dung script đúng artifact nhưng cache chứa asset cũ, vấn đề có thể nằm ở chiến lược cache/versioning thay vì xâm nhập.

## 7. Bảo toàn bằng chứng

Không bắt đầu bằng thao tác unregister hoặc clear storage trên profile duy nhất có bằng chứng. Các thao tác đó có thể làm mất dữ liệu hữu ích.

### 7.1 Bằng chứng cần thu thập

- Origin và URL trang đang mở.
- Script URL và scope.
- Trạng thái installing, waiting và active.
- Script hash và bản script được lấy từ browser/server.
- Registration metadata.
- Danh sách cache và entry đáng ngờ.
- Console log của page và worker.
- Network log liên quan tới script và request bị ảnh hưởng.
- Response header của script worker.
- Release ID, commit và artifact hash chuẩn.
- Log CDN, object storage và CI/CD.
- Audit log của tài khoản deploy.
- Dữ liệu push subscription và background sync nếu liên quan.

### 7.2 Bảo vệ dữ liệu nhạy cảm

HAR, console log và cache entry có thể chứa cookie, Authorization header, URL có token hoặc dữ liệu cá nhân.

- Lưu bản gốc trong evidence store hạn chế quyền.
- Tạo bản phân tích đã redact.
- Không đính kèm token raw vào ticket hoặc chat.
- Ghi ai thu thập, thời gian và công cụ.
- Giữ hash của artifact để kiểm tra tính toàn vẹn.
- Áp dụng retention theo quy trình incident.

### 7.3 Không chỉ dựa vào ảnh chụp DevTools

Ảnh chụp giúp minh họa nhưng không đủ để chứng minh script content, registration scope hoặc thời điểm thay đổi. Cần giữ metadata và bản artifact có thể đối chiếu.

## 8. Đánh giá phạm vi ảnh hưởng

Phạm vi không chỉ là số registration. Cần xác định client, route, dữ liệu và credential mà worker có thể tác động.

### 8.1 Scope và client

Registration có scope `/app/` có thể kiểm soát document URL phù hợp trong `/app/`. Registration scope `/` có thể ảnh hưởng nhiều route hơn trên cùng origin.

Kiểm tra:

- Các route nằm trong scope.
- Các ứng dụng khác dùng chung origin.
- Các subpath được reverse proxy tới service khác.
- Các client đang mở và đã bị kiểm soát.
- Browser profile, thiết bị và phiên bản browser liên quan.

Không cộng tất cả người dùng đã tải trang thành người dùng bị compromise. Cần xác định trang đã thực sự được worker kiểm soát và thời điểm đó.

### 8.2 Request và dữ liệu

Xem xét loại request mà worker có thể nhận từ client:

- Navigation request.
- Script, stylesheet, image và font.
- API request cùng origin.
- Request tới dịch vụ ngoài do ứng dụng khởi tạo.
- Response được cache.
- Request gửi khi offline hoặc khi reconnect.

Xác định dữ liệu nào có thể xuất hiện trong URL, header, body hoặc response. Không giả định worker có thể đọc mọi cross-origin response; kiểm tra request mode, CORS, opaque response và browser policy.

### 8.3 Credential và session

Kiểm tra liệu các luồng sau có bị ảnh hưởng:

- Session cookie và request authenticated.
- Access token trong memory hoặc Web Storage.
- Refresh token.
- OAuth callback và authorization code.
- CSRF token.
- API key hoặc credential được nhúng vào frontend.
- Token gửi qua postMessage.
- Form đổi mật khẩu hoặc thay đổi MFA.

Nếu có khả năng token bị lộ, revoke theo loại credential và kiểm tra hành vi sau thời điểm worker độc hại có thể kiểm soát client.

### 8.4 Dữ liệu đã lưu cục bộ

Kiểm tra Cache Storage, IndexedDB và local storage liên quan. Service worker có thể tạo cache mới hoặc sửa cache hiện có. Dữ liệu trong cache có thể tồn tại sau khi worker bị unregister.

Không xóa toàn bộ origin storage ngay nếu chưa hiểu ứng dụng có dữ liệu offline hoặc bản nháp người dùng cần bảo toàn. Cân nhắc mức độ rủi ro và phạm vi dữ liệu.

## 9. Containment: chặn việc tiếp tục phân phối mã độc

Containment cần xử lý cả nguồn phát hành và trạng thái browser. Nếu chỉ sửa server nhưng browser vẫn dùng worker độc hại, client hiện tại có thể tiếp tục nhận nội dung sai. Nếu chỉ unregister trên một máy nhưng server vẫn phục vụ script độc hại, worker có thể được đăng ký lại.

### 9.1 Khóa nguồn phân phối

- Tạm khóa quyền ghi vào static hosting hoặc bucket bị nghi ngờ.
- Thu hồi credential CI/CD hoặc deploy token liên quan.
- Tạm dừng workflow phát hành bị xâm nhập.
- Khôi phục file worker từ artifact đã xác minh.
- Purge CDN cache sau khi origin đã có nội dung sạch.
- Kiểm tra replica, region và mirror.
- Giữ lại bản worker nghi vấn làm bằng chứng trong kho an toàn.

Không purge CDN trước khi xác định nguồn origin đã sạch; nếu không, CDN có thể lấy lại bản độc hại.

### 9.2 Phát hành worker sạch tại cùng script URL

Nếu worker độc hại được đăng ký tại `/app/sw.js`, một phương án khôi phục là triển khai script sạch tại chính URL đó sau khi đã kiểm soát nguồn phân phối.

Browser kiểm tra update của service worker bằng cơ chế riêng. Khi phát hiện script mới, browser có thể cài worker mới rồi chuyển trạng thái theo lifecycle. Cần xác nhận browser thực sự tải bản mới và worker sạch đã active.

Đảm bảo:

- Nội dung mới khớp artifact đã xác minh.
- CDN không còn trả script cũ.
- Response header của script cho phép browser kiểm tra update phù hợp.
- Worker sạch không tái tạo cache độc hại.
- Các import hoặc dependency của worker cũng sạch.

### 9.3 Gỡ registration ở browser

Trong browser profile bị ảnh hưởng, có thể tìm registration cụ thể rồi unregister:

~~~javascript
const expectedScope = new URL("/app/", location.origin).href;
const registrations = await navigator.serviceWorker.getRegistrations();

const target = registrations.find(
  (registration) => registration.scope === expectedScope
);

if (target) {
  const removed = await target.unregister();
  console.log({ scope: target.scope, removed });
}
~~~

Đây là thao tác trên origin hiện tại. Chỉ áp dụng scope đã xác định; không xóa registration của ứng dụng khác trên cùng origin nếu chưa đánh giá tác động.

Unregister không có nghĩa mọi tab đang mở lập tức mất quyền control. Client hiện tại có thể tiếp tục được kiểm soát cho tới khi đóng hoặc điều hướng; cần kiểm tra và yêu cầu reload/đóng mở lại theo quy trình khôi phục.

### 9.4 Điều hướng và reload client

Sau khi worker sạch đã được phát hành hoặc registration bị gỡ:

- Đóng các tab ứng dụng đang mở theo hướng dẫn vận hành.
- Mở lại trang từ network sau khi xác minh server/CDN.
- Kiểm tra `navigator.serviceWorker.controller`.
- Kiểm tra registration và active script URL.
- Kiểm tra nội dung trang và request không còn bị worker cũ xử lý.
- Theo dõi client chưa cập nhật.

Không yêu cầu người dùng reload trước khi nguồn script đã sạch; reload sớm có thể khiến browser tiếp tục tải nội dung độc hại.

### 9.5 Clear-Site-Data và dữ liệu origin

Response header `Clear-Site-Data` có thể được dùng trong một số browser để yêu cầu xóa dữ liệu thuộc origin, bao gồm storage hoặc cache theo directive được hỗ trợ.

Ví dụ:

~~~http
Clear-Site-Data: "storage"
~~~

Đây là biện pháp có phạm vi rộng: có thể xóa dữ liệu offline, đăng nhập và dữ liệu cục bộ của ứng dụng. Hỗ trợ và hành vi cần được kiểm tra trên browser mục tiêu. Không dùng header này như biện pháp duy nhất, và chỉ triển khai sau khi đã cân nhắc tác động tới người dùng và bảo toàn bằng chứng.

### 9.6 Thu hồi credential

Nếu worker có thể đã quan sát hoặc tác động tới luồng xác thực:

- Revoke session liên quan.
- Revoke refresh token và token family.
- Revoke access token nếu issuer hỗ trợ.
- Rotate API key hoặc secret frontend bị lộ.
- Yêu cầu người dùng đăng nhập lại.
- Kiểm tra hoạt động sau thời điểm compromise.
- Kiểm tra MFA, email và recovery setting có bị thay đổi không.

Unregister service worker không thu hồi token đã bị sao chép.

## 10. Làm sạch Cache Storage và dữ liệu liên quan

Cache Storage được quản lý theo origin và có thể được dùng bởi nhiều phần của ứng dụng. Không xóa tất cả cache chỉ dựa vào tên lạ; cần xác định cache do worker bị xâm nhập tạo ra và các ứng dụng cùng origin phụ thuộc vào nó.

### 10.1 Liệt kê cache

~~~javascript
const cacheNames = await caches.keys();
console.log(cacheNames);
~~~

Ghi lại danh sách trước khi xóa. So sánh với cache name/version đã được release phê duyệt.

### 10.2 Kiểm tra entry

~~~javascript
for (const cacheName of await caches.keys()) {
  const cache = await caches.open(cacheName);
  const requests = await cache.keys();

  console.log({
    cacheName,
    urls: requests.map((request) => request.url)
  });
}
~~~

URL trong cache có thể chứa query parameter hoặc dữ liệu nhạy cảm. Redact trước khi chia sẻ kết quả.

### 10.3 Xóa cache đã xác định

~~~javascript
const suspiciousCacheNames = [
  "portal-shell-compromised",
  "portal-runtime-compromised"
];

for (const cacheName of suspiciousCacheNames) {
  await caches.delete(cacheName);
}
~~~

Chỉ dùng danh sách cache đã được xác minh trong incident. Cache API không cung cấp quyền sở hữu độc quyền theo từng registration; xóa nhầm cache có thể làm hỏng offline mode của ứng dụng khác cùng origin.

### 10.4 IndexedDB và các vùng lưu trữ khác

Kiểm tra IndexedDB, localStorage, sessionStorage và dữ liệu offline. Service worker có thể phối hợp với page script để lưu dữ liệu ở các vùng này.

Xác định schema và owner trước khi xóa. Nếu cần xóa dữ liệu người dùng, thông báo tác động và bảo toàn dữ liệu cần thiết theo quy trình.

### 10.5 Push subscription và background sync

Kiểm tra push subscription của registration bị ảnh hưởng. Nếu subscription không còn hợp lệ hoặc có nguy cơ bị lạm dụng:

- Unsubscribe ở browser theo API phù hợp.
- Xóa hoặc đánh dấu subscription ở backend.
- Thu hồi endpoint/key liên quan nếu cần.
- Kiểm tra notification đã gửi.
- Xem xét các tác vụ background sync còn pending.

Không giả định unregister tự động xóa mọi dữ liệu phía push service hoặc backend.

## 11. Khôi phục worker và ứng dụng

Khôi phục cần bắt đầu từ một artifact sạch, được xác minh, rồi mới đưa browser trở lại trạng thái bình thường.

### 11.1 Xác minh artifact

- So sánh worker script với source code đã review.
- Xác minh commit và build provenance.
- Tạo hash của artifact.
- Kiểm tra dependency và import.
- Kiểm tra header scope.
- Kiểm tra file worker được phân phối từ mọi CDN region.
- Kiểm tra cache name và version.
- Xác nhận không có secret trong script hoặc bundle.

### 11.2 Chiến lược cache an toàn

Dùng cache name có version và xóa cache cũ có kiểm soát trong lifecycle. Ví dụ:

~~~javascript
const CACHE_NAME = "portal-shell-v13";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll([
        "/app/",
        "/app/assets/main.abc123.js",
        "/app/assets/main.def456.css"
      ])
    )
  );
});
~~~

Trong activate, chỉ xóa cache thuộc namespace ứng dụng và phiên bản đã biết:

~~~javascript
const CURRENT_CACHE = "portal-shell-v13";
const OWNED_CACHE_PREFIX = "portal-";

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) =>
            name.startsWith(OWNED_CACHE_PREFIX) &&
            name !== CURRENT_CACHE
          )
          .map((name) => caches.delete(name))
      )
    )
  );
});
~~~

Ví dụ này giả định ứng dụng sở hữu mọi cache có prefix `portal-`. Trong hệ thống thực tế, prefix phải là namespace riêng đã được thống nhất; không xóa cache của ứng dụng khác.

### 11.3 Không cache response nhạy cảm

Tránh cache response chứa:

- Session hoặc token.
- Dữ liệu tài khoản cá nhân.
- Kết quả API có quyền riêng tư.
- Nội dung phụ thuộc user/tenant.
- Response chứa CSRF token nếu vòng đời không phù hợp.

Nếu cần offline data, xác định rõ dữ liệu được phép lưu, thời gian lưu, mã hóa ở mức cần thiết và cách xóa khi logout hoặc revoke session.

### 11.4 Cập nhật script worker

Service worker script cần được cấu hình để browser có thể kiểm tra bản cập nhật phù hợp. Thường dùng `Cache-Control: no-cache` cho file script worker để browser có thể revalidate; asset có hash có thể dùng cache dài hạn và immutable.

Ví dụ:

~~~http
Cache-Control: no-cache
Content-Type: text/javascript; charset=utf-8
~~~

Kiểm tra thêm `updateViaCache` nếu ứng dụng dùng import script. Không dựa vào query string ngẫu nhiên hoặc một lần purge CDN để chứng minh mọi browser đã cập nhật.

### 11.5 Kiểm tra scope

Chỉ yêu cầu scope cần thiết. Nếu script nằm trong `/app/`, không mở rộng ra `/` trừ khi kiến trúc có lý do rõ ràng.

Review `Service-Worker-Allowed` và response header trên script. Đảm bảo header không bị thêm bởi cấu hình proxy dùng chung hoặc rule CDN.

## 12. CSP và các kiểm soát liên quan

CSP có thể giới hạn nguồn worker được phép tải thông qua directive `worker-src`. Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'
~~~

`worker-src 'self'` giới hạn nguồn worker theo origin hiện tại. Tuy nhiên, nếu origin đó đã bị xâm nhập và file worker cùng origin bị thay đổi, directive này vẫn có thể cho phép script độc hại. CSP kiểm soát nguồn được phép tải, không xác minh artifact có đúng bản phát hành hay không.

Các kiểm soát bổ sung:

- Giới hạn quyền ghi vào worker script.
- Dùng build artifact đã ký hoặc provenance có thể xác minh.
- Review mọi thay đổi tới file worker.
- Bảo vệ CI/CD secret và deploy role.
- Giám sát thay đổi script URL, scope và header.
- Giới hạn third-party script và xử lý XSS.
- Tách ứng dụng có mức tin cậy khác nhau sang origin riêng khi phù hợp.

### 12.1 Trusted Types và XSS

Trusted Types có thể giúp kiểm soát một số DOM sink nguy hiểm trong browser hỗ trợ. Nó không ngăn mọi cách đăng ký worker và không thay thế kiểm soát deployment.

Nếu XSS là con đường cài worker, cần sửa source/sink, output encoding, sanitizer và CSP. Sau khi sửa XSS, vẫn phải revoke token/session có thể đã bị truy cập.

### 12.2 CORS và Same-Origin Policy

Service worker không vô hiệu hóa SOP hoặc CORS. Một worker có thể tham gia xử lý request từ client được kiểm soát, nhưng quyền đọc response cross-origin vẫn phụ thuộc request mode, CORS và response type.

Không dùng CORS như biện pháp để ngăn worker độc hại cùng origin. Tập trung vào kiểm soát script, registration, scope, storage và quyền phát hành.

## 13. Kiểm thử sau khôi phục

Dùng browser profile sạch và profile đã bị ảnh hưởng để xác minh các trạng thái khác nhau.

### 13.1 Kiểm tra registration và controller

~~~javascript
const registrations = await navigator.serviceWorker.getRegistrations();

console.table(
  registrations.map((registration) => ({
    scope: registration.scope,
    activeScript: registration.active?.scriptURL ?? "",
    activeState: registration.active?.state ?? ""
  }))
);

console.log({
  controller: navigator.serviceWorker.controller?.scriptURL ?? null
});
~~~

Kết quả phải khớp registration và script URL đã phê duyệt. Nếu ứng dụng chủ động không dùng service worker, không còn registration thuộc scope đó.

### 13.2 Kiểm tra response từ network

Trong Network panel:

- Xác nhận worker script tải từ đúng origin và URL.
- Kiểm tra nội dung script hoặc hash so với artifact.
- Xác nhận request của app không còn nhận response cũ từ worker đáng ngờ.
- Kiểm tra cache version.
- Kiểm tra CDN và origin cùng trả nội dung sạch.
- Kiểm tra response header và scope.

### 13.3 Kiểm tra hành vi ứng dụng

Chạy lại các luồng:

- Đăng nhập và đăng xuất.
- Tải dashboard và dữ liệu tài khoản.
- Gửi form và gọi API.
- Refresh session.
- Hoạt động offline nếu được hỗ trợ.
- Push notification nếu được dùng.
- Background sync nếu được dùng.
- Điều hướng giữa các route trong scope.

Xác nhận không có response bị thay đổi, request lạ hoặc dữ liệu cũ được phục vụ.

### 13.4 Kiểm tra client cũ

Browser đang mở từ trước incident có thể tiếp tục chịu ảnh hưởng của worker cũ. Xác định quy trình thông báo reload/close tab, theo dõi tỷ lệ client cập nhật và xử lý thiết bị lâu ngày offline khi chúng quay lại.

Không chỉ test một browser mới cài. Phải có test profile đã từng đăng ký worker và có cache cũ.

## 14. Phòng ngừa tái diễn

### 14.1 Bảo vệ worker script như mã thực thi production

Worker script có quyền điều phối nội dung của client trong scope. Vì vậy:

- Review code owner và pull request.
- Bảo vệ branch và release approval.
- Hạn chế quyền deploy.
- Tách quyền ghi static asset khỏi quyền vận hành ứng dụng.
- Dùng artifact immutable hoặc versioned.
- Kiểm tra hash/provenance trước phát hành.
- Audit mọi thay đổi worker script.

### 14.2 Giới hạn scope

Chọn scope nhỏ nhất đáp ứng chức năng. Không dùng scope `/` chỉ vì thuận tiện. Review header `Service-Worker-Allowed` và cấu hình proxy/CDN.

### 14.3 Giảm bề mặt XSS

- Dùng output encoding theo context.
- Tránh DOM sink không cần thiết.
- Dùng sanitizer cho rich HTML.
- Triển khai CSP với nonce/hash.
- Dùng Trusted Types nếu phù hợp.
- Review third-party script và dependency.
- Không cho user upload file script có thể phục vụ cùng origin.

### 14.4 Bảo vệ upload và static hosting

Không để nội dung người dùng tải lên được phục vụ như JavaScript cùng origin của ứng dụng. Dùng domain tách biệt cho nội dung không tin cậy, với cookie và policy phù hợp.

Hạn chế quyền ghi bucket/CDN, dùng origin access control và audit log. Tách deployment credential theo môi trường và service.

### 14.5 Cache có namespace và version

Dùng cache name có prefix riêng, version rõ ràng và quy tắc dọn cache chỉ xóa namespace ứng dụng sở hữu. Không cache token hoặc response cá nhân nếu không có thiết kế rõ ràng.

### 14.6 Giám sát registration và artifact

Có thể theo dõi:

- Thay đổi hash worker script.
- Thay đổi scope và header `Service-Worker-Allowed`.
- Registration mới trên các route quan trọng qua telemetry phù hợp.
- Tên cache không thuộc namespace.
- Request worker script ngoài release window.
- Thay đổi quyền deploy và bucket.
- Tỷ lệ worker update thất bại hoặc client dùng version cũ.

Telemetry từ browser cũng là dữ liệu không đáng tin cậy; đối chiếu với log server và release pipeline.

## 15. Phân biệt service worker độc hại với các nguyên nhân khác

| Hiện tượng | Dấu hiệu phân biệt | Cách kiểm tra |
|---|---|---|
| Service worker độc hại | Registration/script hoặc nội dung worker khác artifact; response bị worker thay đổi | Kiểm tra Application, script hash, scope và Cache Storage |
| Cache CDN cũ | Response cũ nhưng registration/worker đúng hoặc không có worker | Kiểm tra CDN age, ETag, origin response và purge |
| Browser extension | Chỉ xảy ra ở profile có extension; registration có thể không thay đổi | Thử profile sạch, kiểm tra extension policy |
| XSS | Script lạ chạy trong page context; có thể đăng ký worker nếu cùng origin và có đường script | Kiểm tra DOM, CSP report, source/sink và script initiator |
| Build/dependency compromise | Artifact đầu ra khác source đã review hoặc dependency bất thường | So sánh lockfile, build log, provenance và artifact hash |
| Worker cũ hợp lệ | Script hash thuộc release cũ; cache version cũ; không có thay đổi trái phép | Kiểm tra lifecycle và update policy |

Một sự cố có thể có nhiều nguyên nhân đồng thời. Ví dụ XSS có thể là điểm xâm nhập ban đầu, còn worker độc hại giúp duy trì tác động sau khi trang bị reload.

## 16. Những lỗi xử lý thường gặp

### 16.1 Chỉ unregister mà không sửa nguồn phân phối

Nếu server vẫn phục vụ worker độc hại, browser có thể đăng ký lại. Phải khóa nguồn phân phối và phát hành bản sạch trước hoặc đồng thời với client cleanup.

### 16.2 Chỉ xóa Cache Storage

Worker vẫn có thể tiếp tục hoạt động và tạo cache mới. Xử lý registration, script và nguồn phát hành cùng lúc.

### 16.3 Chỉ purge CDN

Browser đã có worker active và cache local. Purge CDN không tự thu hồi registration hoặc cache trong từng profile.

### 16.4 Chỉ cập nhật server

Worker độc hại có thể tiếp tục kiểm soát client cũ. Cần xác minh browser update, unregister và trạng thái controller.

### 16.5 Xóa toàn bộ origin storage mà không đánh giá

Có thể làm mất dữ liệu offline, bản nháp hoặc trạng thái ứng dụng không liên quan. Bảo toàn bằng chứng và xác định cache namespace trước khi xóa.

### 16.6 Cho rằng worker đọc được HttpOnly cookie

Worker không dùng `document.cookie` để đọc cookie HttpOnly. Rủi ro nằm ở request được thực hiện trong browser có session và dữ liệu ứng dụng mà worker có thể xử lý.

### 16.7 Cho rằng worker vượt CORS

Service worker không vô hiệu hóa CORS. Đánh giá request mode, credentials và response type trước khi kết luận dữ liệu cross-origin đã bị đọc.

### 16.8 Bỏ qua scope và header

Một worker có scope rộng hơn dự kiến có thể ảnh hưởng nhiều route. Kiểm tra `Service-Worker-Allowed` và registration scope thực tế.

### 16.9 Không kiểm tra worker waiting

Worker độc hại có thể đang ở trạng thái waiting, chưa active. Nếu chỉ xem controller hiện tại, có thể bỏ sót bản script đang chờ kích hoạt.

### 16.10 Không xử lý credential

Xóa worker không thu hồi token đã bị sao chép. Revoke session và token có nguy cơ bị lộ, sau đó xác minh request cũ bị từ chối.

## 17. Checklist ứng phó Service worker độc hại

### Phát hiện và bảo toàn

- [ ] Ghi origin, route, thời điểm và browser profile.
- [ ] Thu thập script URL và registration scope.
- [ ] Ghi trạng thái installing, waiting và active.
- [ ] Ghi worker đang kiểm soát document.
- [ ] Bảo toàn script, hash, response header và release artifact.
- [ ] Ghi danh sách Cache Storage và entry liên quan.
- [ ] Thu thập Network/Console evidence đã bảo vệ dữ liệu nhạy cảm.
- [ ] Kiểm tra log CDN, storage và CI/CD.
- [ ] Không unregister hoặc clear storage trước khi bảo toàn bằng chứng cần thiết.

### Containment

- [ ] Khóa quyền ghi và pipeline bị nghi xâm nhập.
- [ ] Xác minh origin hosting đã sạch.
- [ ] Khôi phục script worker tại URL được đăng ký.
- [ ] Purge CDN sau khi origin đã sạch.
- [ ] Xác định client và scope bị ảnh hưởng.
- [ ] Cập nhật hoặc unregister registration cụ thể.
- [ ] Hướng dẫn reload/đóng mở client cũ.
- [ ] Revoke token/session có khả năng bị lộ.
- [ ] Kiểm tra push subscription và background sync.

### Khôi phục

- [ ] Xác minh artifact và hash của worker sạch.
- [ ] Xác minh mọi CDN region trả đúng script.
- [ ] Kiểm tra registration và controller trong browser.
- [ ] Xóa cache đáng ngờ theo namespace đã xác minh.
- [ ] Kiểm tra IndexedDB và storage liên quan.
- [ ] Kiểm tra luồng login, API, offline và push.
- [ ] Xác nhận token cũ bị từ chối.
- [ ] Theo dõi client cũ chưa cập nhật.

### Phòng ngừa

- [ ] Giới hạn scope nhỏ nhất cần thiết.
- [ ] Review header `Service-Worker-Allowed`.
- [ ] Bảo vệ CI/CD, bucket và static hosting.
- [ ] Kiểm tra provenance/hash artifact.
- [ ] Dùng cache namespace và version rõ ràng.
- [ ] Không cache token hoặc response nhạy cảm.
- [ ] Giảm XSS và third-party script.
- [ ] Triển khai CSP phù hợp, gồm `worker-src`.
- [ ] Giám sát thay đổi worker script và quyền deploy.
- [ ] Diễn tập quy trình unregister, update và revoke định kỳ.

## 18. Bài thực hành

Thực hiện trong local lab với hai phiên bản worker giả lập, không triển khai worker độc hại lên website công khai.

### Bài 1: Quan sát registration

Tạo một ứng dụng lab đăng ký worker trong scope `/app/`. Dùng DevTools và `getRegistrations()` để ghi script URL, scope, active state và controller.

### Bài 2: Kiểm tra lifecycle

Phát hành phiên bản worker mới và quan sát trạng thái installing, waiting, activating và activated. So sánh hành vi khi có và không có `skipWaiting()`/`clients.claim()`.

### Bài 3: Kiểm tra scope

Đăng ký worker với scope `/app/`, sau đó thử điều hướng tới `/admin/`. Xác nhận document ngoài scope không bị worker đó kiểm soát. Kiểm tra header `Service-Worker-Allowed` trong môi trường lab.

### Bài 4: Kiểm tra Cache Storage

Tạo cache có version, lưu một asset lab và liệt kê entry. Phát hành version mới rồi xác nhận activate cleanup chỉ xóa cache namespace của ứng dụng.

### Bài 5: Diễn tập worker không khớp artifact

Thay đổi nội dung worker lab, ghi lại hash và so sánh với artifact chuẩn. Quan sát browser phát hiện update. Không dùng script để thu thập credential hoặc gửi dữ liệu ra ngoài.

### Bài 6: Diễn tập containment

Trong profile test, ghi lại registration và cache trước. Phát hành worker sạch tại cùng script URL, xác nhận update, rồi unregister registration lab nếu kịch bản yêu cầu. Reload client và kiểm tra controller.

### Bài 7: Kiểm tra dữ liệu nhạy cảm

Đặt dữ liệu giả trong một API response lab. Kiểm tra ứng dụng không cache response chứa token hoặc dữ liệu cá nhân. Xác minh log không ghi cookie hoặc Authorization header.

### Bài 8: Kiểm tra Clear-Site-Data

Trong origin lab, gửi header `Clear-Site-Data: "storage"` và quan sát registration/storage theo browser mục tiêu. Ghi nhận dữ liệu bị xóa và tác động tới offline state.

### Bài 9: Kiểm tra CSP worker-src

Thử đăng ký worker từ các nguồn trong và ngoài allowlist ở lab. Xác nhận CSP báo hoặc chặn nguồn không được phép. Sau đó thử worker cùng origin có nội dung khác để hiểu giới hạn của source allowlist.

### Bài 10: Diễn tập incident

Dùng một worker test có script hash không khớp artifact. Lập timeline, bảo toàn evidence, khóa nguồn phân phối, phát hành worker sạch, revoke token giả và hoàn thành checklist.

## 19. Câu hỏi tự kiểm tra

**1. Service worker kiểm soát những trang nào?**

Các document URL phù hợp với scope của registration và được browser kiểm soát bởi worker đó.

**2. Worker có thể đọc DOM trực tiếp không?**

Không. Worker chạy trong global context riêng. Nó có thể giao tiếp với client và xử lý fetch event nhưng không có DOM API như document.

**3. Vì sao unregister không đủ?**

Server có thể vẫn phục vụ script độc hại khiến worker được đăng ký lại; client đang mở có thể còn bị kiểm soát; cache và credential bị lộ vẫn tồn tại.

**4. Cache Storage có tự bị xóa khi unregister không?**

Không nên giả định như vậy. Cache Storage là vùng lưu trữ theo origin và cần kiểm tra/xóa entry thuộc ứng dụng theo namespace.

**5. HttpOnly có bảo vệ hoàn toàn khỏi worker độc hại không?**

Không. Worker không đọc cookie qua JavaScript nhưng có thể ảnh hưởng request được gửi từ client có session và response mà ứng dụng xử lý.

**6. Worker có vượt qua CORS không?**

Không. SOP và CORS vẫn áp dụng. Khả năng đọc response phụ thuộc request mode, CORS và response type.

**7. Service-Worker-Allowed dùng để làm gì?**

Header này có thể cho phép registration yêu cầu scope rộng hơn thư mục mặc định của script. Cần giới hạn theo kiến trúc.

**8. skipWaiting và clients.claim có ý nghĩa gì?**

skipWaiting yêu cầu worker mới bỏ qua giai đoạn waiting; clients.claim yêu cầu worker active nhận control các client phù hợp. Chúng thay đổi thời điểm chuyển worker.

**9. Vì sao cần bảo toàn bằng chứng trước khi clear storage?**

Unregister và xóa cache có thể làm mất script, entry và trạng thái cần thiết để xác định nguyên nhân và phạm vi.

**10. Khi nào có thể kết luận đã khôi phục?**

Khi nguồn phân phối đã sạch, browser dùng worker đúng artifact hoặc không còn registration ngoài dự kiến, cache đã được xử lý, credential liên quan bị thu hồi và các luồng ứng dụng đã được kiểm thử.

## Ghi nhớ

Service worker có thể điều phối request và nội dung của các trang thuộc scope, nên worker bị thay thế có thể duy trì tác động ngay cả sau khi server đã sửa. Điều tra phải bắt đầu bằng việc xác định origin, scope, script URL, lifecycle, client và cache; bảo toàn bằng chứng trước khi unregister hoặc xóa storage. Containment cần khóa nguồn phát hành, triển khai script sạch, xử lý registration và cache ở browser, đồng thời revoke session/token có khả năng bị lộ. Unregister, purge CDN hoặc xóa cache riêng lẻ đều chưa chứng minh sự cố đã kết thúc. Chỉ khôi phục khi artifact, browser client, credential và luồng ứng dụng đều được xác minh.

## Tài liệu tham khảo

- [MDN: Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
- [MDN: ServiceWorkerContainer.register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register)
- [MDN: ServiceWorkerRegistration](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration)
- [MDN: ServiceWorkerGlobalScope](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope)
- [MDN: Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
- [MDN: CacheStorage](https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage)
- [MDN: Clear-Site-Data header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- [MDN: Content-Security-Policy worker-src directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/worker-src)
- [web.dev: Service worker lifecycle](https://web.dev/articles/service-worker-lifecycle)
- [OWASP: HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)
