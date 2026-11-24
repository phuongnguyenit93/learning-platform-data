# Host permission

## 1. Host permission là gì?

**Host permission** là quyền mà browser cấp cho một extension để tương tác với các URL thuộc một host hoặc nhóm host được khai báo. Tùy API và loại extension, quyền này có thể cho phép extension đọc hoặc thay đổi nội dung trang, thực hiện request cross-origin từ extension context, truy cập cookie của host khi có thêm permission tương ứng, hoặc quan sát sự kiện liên quan đến URL.

Trong browser extension, quyền truy cập website là một ranh giới bảo mật quan trọng. Một extension có thể hữu ích khi đọc nội dung trang hiện tại để dịch, hỗ trợ điền form hoặc kiểm tra accessibility. Nhưng nếu extension được cấp quyền quá rộng, lỗi trong extension hoặc extension bị chiếm quyền có thể làm lộ dữ liệu từ nhiều website người dùng truy cập.

Với Chrome Manifest V3, manifest phân biệt quyền API trong trường `permissions`, host access được khai báo trong `host_permissions`, và host access có thể xin sau trong `optional_host_permissions`. Quyền được khai báo trong manifest chưa đồng nghĩa mọi website đều đang được người dùng cho phép truy cập: người dùng có thể giới hạn site access, và extension cần xử lý trạng thái bị từ chối hoặc bị thu hồi.

Host permission không phải một cơ chế xác thực cho website, không chứng minh người dùng có quyền trên tài khoản web, và không biến extension thành thành phần đáng tin tuyệt đối. Nó chỉ cho phép extension thực hiện một số thao tác browser trên phạm vi host đã được cấp; server vẫn phải xác thực và authorize mọi request như bình thường.

Bài học này tập trung vào cách khai báo và thu hẹp host permission, match patterns, quyền tĩnh và quyền tùy chọn, runtime permission request, content scripts, cross-origin fetch, permission warnings và kiểm thử theo nguyên tắc least privilege.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt API permission, host permission và content script match pattern.
2. Khai báo `host_permissions` và `optional_host_permissions` trong Manifest V3.
3. Đọc và giới hạn match pattern theo scheme, host và path.
4. Hiểu vì sao path trong host permission pattern không giới hạn quyền ở một endpoint.
5. Xin quyền theo thao tác người dùng bằng `chrome.permissions.request()`.
6. Kiểm tra và thu hồi quyền bằng Permissions API.
7. Phân biệt `activeTab` với host permission dài hạn.
8. Hiểu giới hạn của content script isolated world và cross-origin fetch.
9. Thiết kế message passing an toàn giữa content script và service worker.
10. Kiểm thử site access, file access, incognito và permission removal.

## 2. Các loại quyền trong extension

### 2.1. API permissions

API permission cho phép extension gọi một nhóm API của browser. Ví dụ:

- `storage`: dùng extension storage.
- `scripting`: chèn hoặc thực thi script thông qua scripting API.
- `tabs`: truy cập một số thông tin nhạy cảm của tab như URL/title khi được cấp quyền phù hợp.
- `cookies`: dùng Cookies API; để thao tác cookie của host còn cần host permission tương ứng.
- `webRequest`: quan sát một số network request theo API và permission model hiện hành.

API permission và host permission giải quyết hai câu hỏi khác nhau: extension được gọi API nào, và API đó được phép tác động lên host nào.

### 2.2. Host permissions

Host permission chỉ định host hoặc URL pattern mà extension được phép truy cập qua những API cần host access. Ví dụ:

```json
{
  "manifest_version": 3,
  "name": "Portal helper",
  "version": "1.0.0",
  "permissions": ["storage", "scripting"],
  "host_permissions": [
    "https://portal.example.com/*"
  ],
  "background": {
    "service_worker": "service-worker.js"
  },
  "action": {}
}
```

Ví dụ này khai báo quyền cho host HTTPS `portal.example.com`. Extension không được suy rộng quyền đó sang `admin.example.com`, `api.example.com` hoặc HTTP chỉ vì chúng có cùng registrable domain.

### 2.3. Optional host permissions

Nếu extension chỉ cần truy cập một website sau khi người dùng bật tính năng tương ứng, dùng `optional_host_permissions`:

```json
{
  "manifest_version": 3,
  "name": "Optional site helper",
  "version": "1.0.0",
  "permissions": ["storage"],
  "optional_host_permissions": [
    "https://docs.example.net/*"
  ],
  "action": {}
}
```

Extension có thể xin quyền lúc chạy sau một thao tác rõ ràng của người dùng. Người dùng có thể từ chối; extension phải tiếp tục hoạt động ở chế độ không có quyền đó.

### 2.4. Content script match patterns

`content_scripts.matches` xác định URL nào được browser xem xét để tự động chèn content script:

```json
{
  "content_scripts": [
    {
      "matches": [
        "https://portal.example.com/*"
      ],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ]
}
```

Match pattern trong `content_scripts` xác định nơi browser inject static content script và là phần khai báo site access cho hoạt động inject đó. `host_permissions` khai báo host access mà extension context và các API cần, chẳng hạn service worker thực hiện cross-origin fetch. Hai trường có vai trò khác nhau: chỉ khai báo `host_permissions` không tự chèn content script; chỉ khai báo `content_scripts.matches` cũng không thay thế host permission cần cho request từ extension service worker. Manifest ở trên có cả hai vì ví dụ vừa inject vào portal vừa cần host access cho extension context.

## 3. Match pattern: scheme, host và path

Match pattern của extension thường có dạng:

```text
<scheme>://<host>/<path>
```

Các phần xác định phạm vi:

- Scheme: ví dụ `http`, `https` hoặc `*` trong phạm vi scheme được hỗ trợ.
- Host: tên miền cụ thể, wildcard `*`, hoặc wildcard subdomain như `*.example.com`.
- Path: đường dẫn URL được mô tả trong pattern; ý nghĩa của path khác nhau giữa host permission và content script matching.

### 3.1. Ví dụ pattern

| Pattern | Phạm vi khái quát |
| --- | --- |
| `https://portal.example.com/*` | Host HTTPS cụ thể |
| `https://*.example.com/*` | HTTPS trên example.com và các subdomain phù hợp |
| `*://portal.example.com/*` | HTTP và HTTPS cho host đó |
| `http://portal.example.com/*` | Chỉ HTTP, không mã hóa |
| `<all_urls>` | Phạm vi URL rất rộng theo match-pattern support của browser |

Pattern `https://*.example.com/*` thường bao gồm cả `example.com` và các subdomain như `app.example.com`, `docs.example.com`. Đây là quyền rộng hơn một host cụ thể. Nếu chỉ cần `portal.example.com`, hãy khai báo đúng host đó.

### 3.2. Host permission path không phải giới hạn endpoint

Đây là điểm dễ gây lỗi bảo mật: với host permissions, phần path của match pattern không thu hẹp quyền xuống một route HTTP cụ thể. Ví dụ:

```json
{
  "host_permissions": [
    "https://portal.example.com/reports/*"
  ]
}
```

Không nên hiểu rằng extension chỉ có quyền với `/reports/`. Host permission áp dụng theo host; path được yêu cầu trong pattern nhưng không tạo một ranh giới authorization cho từng endpoint. Nếu cần giới hạn thao tác theo URL/path, phải tự kiểm tra URL trong code và thiết kế permission scope tương ứng.

Ngược lại, path trong `content_scripts.matches` có ý nghĩa đối với URL match để quyết định nơi chèn content script. Dù vậy, không xem path matching là kiểm soát quyền truy cập dữ liệu ở server.

### 3.3. Scheme wildcard

`*` trong scheme thường đại diện cho các scheme web được hỗ trợ như HTTP và HTTPS; không hiểu nó là mọi scheme tùy ý. Nếu extension xử lý dữ liệu đăng nhập hoặc trang nhạy cảm, ưu tiên HTTPS pattern cụ thể. Cho phép HTTP có thể làm extension hoạt động trên kết nối không mã hóa và tăng nguy cơ nội dung bị can thiệp.

### 3.4. Wildcard host và subdomain

Quyền `https://*.example.com/*` có thể bao gồm nhiều subdomain với mức tin cậy khác nhau. Một subdomain cũ, tenant do người dùng kiểm soát hoặc ứng dụng thử nghiệm có thể trở thành điểm yếu để tấn công extension. Không xin quyền trên cả domain cha nếu tính năng chỉ cần một host ổn định.

### 3.5. Port và URL scope

Match pattern không dùng port như một phần riêng trong host field giống tuple origin. Không thiết kế permission dựa trên giả định `https://example.com:8443/*` sẽ giới hạn host access vào đúng port đó. Nếu cần hỗ trợ local development hoặc nhiều môi trường, cấu hình pattern rõ ràng và kiểm tra trên browser mục tiêu.

### 3.6. File URL và browser-internal pages

Quyền với `file://` cần được xử lý riêng. Ngay cả khi extension khai báo file match pattern, người dùng thường phải bật tùy chọn cho phép extension truy cập file URL trong trang quản lý extension. Browser cũng chặn một số trang nội bộ như `chrome://`, trang cửa hàng extension và các trang đặc biệt khác; host permission không vượt qua những giới hạn này.

## 4. Host permission và quyền người dùng nhìn thấy

### 4.1. Permission warning

Khi cài hoặc cập nhật extension, browser có thể hiển thị cảnh báo quyền dựa trên API permission và host access. Host scope rộng có thể khiến người dùng thấy cảnh báo như đọc/thay đổi dữ liệu trên nhiều website.

Cảnh báo là thông tin để người dùng đánh giá quyền mà extension yêu cầu. Không nên tìm cách che giấu quyền hoặc thêm permission rộng chỉ để phòng trường hợp tương lai cần dùng.

### 4.2. Requested, granted và withheld

Cần phân biệt ba trạng thái:

- Requested: extension khai báo quyền trong manifest.
- Granted: browser/người dùng đã cấp quyền theo permission model.
- Withheld: quyền host được khai báo nhưng hiện chưa được bật cho một số site hoặc bị giới hạn bởi site access control.

Trong Chrome, người dùng có thể chọn cho extension truy cập khi nhấn icon, trên một số website cụ thể hoặc trên tất cả website. UI có thể thay đổi theo phiên bản. Extension không nên giả định manifest khai báo `host_permissions` đồng nghĩa luôn có quyền đọc trang hiện tại.

### 4.3. Quyền có thể bị thu hồi

Người dùng có thể thay đổi site access trong extension settings. Extension cũng có thể tự bỏ quyền tùy chọn. Do đó, thao tác cần host access phải kiểm tra khả năng thực hiện và xử lý lỗi/permission denial. Không giữ một cờ JavaScript kiểu `hasPermission=true` vô thời hạn rồi giả định quyền không thay đổi.

## 5. Static host permission và runtime request

### 5.1. Static permission

Dùng `host_permissions` khi extension cần host access ngay từ đầu để cung cấp chức năng cốt lõi. Giữ danh sách ngắn và giải thích rõ trong giao diện onboarding.

### 5.2. Xin optional permission bằng thao tác người dùng

Ví dụ người dùng bật tính năng hỗ trợ một trang tài liệu:

```js
async function enableDocsIntegration() {
  const originPattern = "https://docs.example.net/*";

  const granted = await chrome.permissions.request({
    origins: [originPattern]
  });

  if (!granted) {
    return { enabled: false, reason: "permission-denied" };
  }

  return { enabled: true };
}
```

`chrome.permissions.request()` phải được gọi trong user gesture phù hợp, chẳng hạn handler của nút bấm. Pattern xin quyền phải nằm trong `optional_host_permissions` đã khai báo. Không tự bật quyền trên mọi host khi extension khởi động.

### 5.3. Kiểm tra quyền trước thao tác

```js
async function canAccessDocsHost() {
  return chrome.permissions.contains({
    origins: ["https://docs.example.net/*"]
  });
}

async function openDocsFeature() {
  if (!(await canAccessDocsHost())) {
    return { ok: false, reason: "permission-required" };
  }

  return { ok: true };
}
```

Đây là kiểm tra tại thời điểm thao tác. API cụ thể có thể có điều kiện host access riêng; cần xử lý lỗi khi gọi API, vì quyền có thể bị thay đổi giữa lúc kiểm tra và lúc sử dụng.

### 5.4. Thu hồi quyền tùy chọn

```js
async function disableDocsIntegration() {
  const removed = await chrome.permissions.remove({
    origins: ["https://docs.example.net/*"]
  });

  return { removed };
}
```

Khi người dùng tắt tính năng, thu hồi optional host permission nếu không còn cần. Đồng thời dọn dữ liệu extension đã lưu cho tích hợp đó theo retention policy. Thu hồi host permission không tự xóa dữ liệu đã đọc hoặc lưu trong `chrome.storage`.

### 5.5. Liệt kê quyền hiện có

```js
async function getCurrentPermissions() {
  return chrome.permissions.getAll();
}
```

Không log toàn bộ danh sách quyền hoặc dữ liệu người dùng không cần thiết. Dùng kết quả để cập nhật UI, chẩn đoán lỗi quyền và kiểm tra cấu hình; vẫn phải xử lý API call thất bại.

## 6. activeTab: quyền tạm thời theo hành động người dùng

`activeTab` cho phép extension nhận quyền truy cập tạm thời vào tab hiện tại sau một hành động rõ ràng của người dùng, ví dụ nhấn action button hoặc gọi context menu extension. Quyền này thường tồn tại cho tới khi tab điều hướng sang origin khác hoặc đóng; chi tiết phụ thuộc API/browser.

Ví dụ manifest:

```json
{
  "manifest_version": 3,
  "name": "One-tab reader",
  "version": "1.0.0",
  "permissions": ["activeTab", "scripting"],
  "action": {}
}
```

Ví dụ chèn script sau khi người dùng nhấn extension:

```js
chrome.action.onClicked.addListener(async tab => {
  if (!tab.id) return;

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["read-current-page.js"]
  });
});
```

`activeTab` phù hợp cho chức năng chỉ thao tác trên trang mà người dùng chủ động chọn. Nó không phải quyền đọc mọi tab nền, không cấp quyền dài hạn cho mọi lần truy cập host và không thay thế `host_permissions` khi extension cần truy cập host thường xuyên hoặc dùng API cần quyền host cố định.

## 7. Host permission và content script

### 7.1. Content script chạy trong isolated world

Content script có JavaScript environment tách biệt với biến global của page script. Tuy nhiên content script vẫn tương tác với DOM của trang. Nó có thể đọc text, thuộc tính, form field và thay đổi node theo quyền được browser cho phép.

Isolated world không làm DOM trở thành dữ liệu đáng tin. Trang có thể thay đổi DOM bất kỳ lúc nào, tạo element giả, sửa attribute hoặc gửi message gây hiểu nhầm. Không dùng nội dung DOM làm bằng chứng xác thực danh tính hay quyền truy cập.

### 7.2. Static content script

```json
{
  "content_scripts": [
    {
      "matches": ["https://portal.example.com/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ]
}
```

Browser chỉ xem xét chèn script trên URL phù hợp với `matches` và theo site access/permission model hiện hành. Có thể dùng `exclude_matches`, `include_globs` hoặc `exclude_globs` để tinh chỉnh phạm vi inject; các bộ lọc này không thay authorization ở server.

### 7.3. Dynamic injection

Nếu cần chèn script sau một hành động hoặc theo tính năng bật/tắt, dùng `chrome.scripting`:

```js
async function injectReader(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["reader.js"]
  });
}
```

Dynamic injection cần `scripting` permission và host access hợp lệ hoặc `activeTab` grant tương ứng. Luôn xử lý lỗi khi tab không tồn tại, trang không thể inject hoặc người dùng chưa cấp site access.

### 7.4. Host permission không làm content script đáng tin hơn

Content script có thể đọc dữ liệu nhạy cảm trên trang mà nó được inject vào. Vì vậy, chỉ inject code đã review, giới hạn host và giảm dữ liệu thu thập. Không tải code thực thi từ server bên ngoài rồi eval trong content script. Không gửi toàn bộ DOM về backend nếu tính năng chỉ cần một trường cụ thể.

## 8. Cross-origin fetch từ extension

### 8.1. Extension service worker và extension page

Trong Chrome extension, extension service worker hoặc extension page có thể thực hiện một số cross-origin request tới host được cấp permission. Manifest cần có host permission tương ứng; request vẫn phải tuân theo HTTPS, server auth và các giới hạn network khác.

```js
async function fetchPortalSummary() {
  const response = await fetch(
    "https://portal.example.com/api/summary",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Không lấy được dữ liệu portal.");
  }

  return response.json();
}
```

Ví dụ này giả định extension có host permission cho portal và người dùng có session/cookie phù hợp. Không đưa cookie, access token hoặc response nhạy cảm vào log.

### 8.2. Content script fetch chịu ngữ cảnh của trang

`fetch()` từ content script chạy trong ngữ cảnh web của trang đối với origin/CORS. Không giả định host permission của extension tự động bỏ qua CORS cho fetch thực hiện trực tiếp từ content script.

Nếu cần extension-origin request, content script có thể gửi message tới service worker. Service worker phải xác minh sender và chỉ thực hiện thao tác được phép:

```js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "load-portal-summary") return;

  const senderUrl = sender.url ? new URL(sender.url) : null;
  if (
    !senderUrl ||
    senderUrl.origin !== "https://portal.example.com"
  ) {
    sendResponse({ ok: false, error: "untrusted-sender" });
    return;
  }

  fetch("https://portal.example.com/api/summary", {
    credentials: "include"
  })
    .then(response => {
      if (!response.ok) throw new Error("request-failed");
      return response.json();
    })
    .then(data => sendResponse({ ok: true, data }))
    .catch(() => sendResponse({ ok: false, error: "request-failed" }));

  return true;
});
```

Ví dụ minh họa cần điều chỉnh theo luồng message thực tế. `credentials: "include"` chỉ cần khi API dựa vào cookie của portal; browser vẫn áp dụng cookie policy như SameSite và third-party cookie restrictions. Không coi mọi message từ content script là đáng tin chỉ vì `sender.id` là extension ID; trang web có thể tác động DOM mà content script đọc, và message payload có thể chứa dữ liệu giả mạo.

## 9. Thiết kế message passing an toàn

### 9.1. Kiểm tra sender

Khi service worker nhận message, kiểm tra tối thiểu:

- `sender.id` có đúng extension ID nếu API/message channel có thể nhận nguồn ngoài.
- `sender.url` thuộc origin được phép.
- `sender.tab` và `frameId` có phù hợp với tính năng không.
- Message type nằm trong allowlist.
- Payload đúng schema, kích thước và kiểu dữ liệu.
- Thao tác yêu cầu user gesture có transaction/state phù hợp.

Không chỉ dựa vào `message.url` hoặc `message.origin` do content script gửi trong payload; những trường này do sender kiểm soát. Dùng metadata `sender` do browser cung cấp.

### 9.2. Không biến service worker thành confused deputy

Nếu service worker có host permission rộng và nhận message kiểu `{url: "https://any-host/..." }`, nó có thể trở thành proxy giúp content script hoặc trang web gửi request tới host tùy ý. Tránh API message tổng quát nhận URL tự do.

Thiết kế message theo capability cụ thể, ví dụ `getCurrentPortalSummary`, rồi service worker tự dựng URL cố định và xác minh sender. Nếu cần truyền ID hoặc path, validate theo grammar/allowlist và không cho phép điều khiển scheme/host.

### 9.3. Kiểm soát dữ liệu trả về

Chỉ trả các trường cần cho UI. Không gửi access token, cookie, internal headers hoặc toàn bộ response object nếu content script chỉ cần một giá trị. Không ghi response private vào console hoặc extension storage trừ khi tính năng yêu cầu và có retention/cleanup rõ.

## 10. Cookie API và host permission

Cookies API cần `cookies` permission cùng host permission tương ứng với URL cookie. Host permission không tự cấp quyền đọc cookie nếu thiếu API permission; ngược lại `cookies` permission không tự cho phép đọc cookie của mọi host.

```json
{
  "permissions": ["cookies"],
  "host_permissions": [
    "https://portal.example.com/*"
  ]
}
```

```js
async function readPortalCookies() {
  return chrome.cookies.getAll({
    url: "https://portal.example.com/"
  });
}
```

Cookie có thể chứa session identifier hoặc credential. Chỉ đọc cookie nếu tính năng thực sự cần; tránh đọc `HttpOnly` cookie chỉ vì có API kỹ thuật cho phép. Không gửi cookie về server extension hoặc ghi vào storage. Nếu mục tiêu chỉ là xác định trạng thái đăng nhập, ưu tiên API chính thức hoặc endpoint trạng thái do website cung cấp.

## 11. Quyền rộng và những vùng bị giới hạn

### 11.1. all_urls

`<all_urls>` là quyền rất rộng. Nó có thể khiến extension có khả năng tương tác với nhiều website không liên quan tới tính năng chính. Chỉ dùng khi chức năng thực sự cần trên mọi site, ví dụ công cụ accessibility toàn cục do người dùng chủ động bật; giải thích rõ lý do và cung cấp cơ chế tắt.

### 11.2. Subdomain wildcard

`https://*.example.com/*` có thể bao gồm subdomain do nhóm khác vận hành, môi trường thử nghiệm hoặc tenant do khách hàng kiểm soát. Hãy đánh giá ai có thể publish nội dung ở các subdomain đó và liệu extension có thể đọc dữ liệu nhạy cảm ở đó hay không.

### 11.3. Trang browser nội bộ

Host permission không cấp quyền truy cập mọi URL. Các trang browser nội bộ, trang cài đặt, Chrome Web Store và trang extension khác thường bị hạn chế. Không hướng dẫn người dùng tắt browser security để vượt các giới hạn này.

### 11.4. File URL

Nếu extension cần truy cập file local, cần pattern và sự cho phép riêng của người dùng qua setting “Allow access to file URLs” hoặc tương đương. Đây là quyền nhạy cảm vì file local có thể chứa tài liệu cá nhân. Chỉ yêu cầu khi use case không thể thực hiện bằng file picker hoặc luồng khác ít quyền hơn.

### 11.5. Incognito

Người dùng có thể phải bật extension cho incognito riêng. Không giả định host permission ở profile thường tự động có hiệu lực trong incognito. Nếu extension hỗ trợ incognito, chọn chế độ xử lý dữ liệu phù hợp, tránh lưu dữ liệu riêng tư vào storage dùng chung ngoài dự kiến và giải thích rõ cho người dùng.

## 12. Least privilege và permission UX

Một thiết kế tốt chỉ yêu cầu quyền khi tính năng cần nó.

### 12.1. Ưu tiên host cụ thể

Nếu tính năng chỉ hoạt động trên `portal.example.com`, hãy xin đúng host đó. Tránh khai báo `*://*/*` hoặc `<all_urls>` rồi lọc URL trong JavaScript; permission prompt vẫn phản ánh phạm vi rộng mà extension yêu cầu.

### 12.2. Xin quyền theo tính năng

Nếu extension có nhiều tích hợp độc lập, dùng optional host permission cho từng tích hợp. UI nên mô tả:

- Website nào sẽ được extension truy cập.
- Dữ liệu nào được đọc hoặc thay đổi.
- Vì sao tính năng cần quyền.
- Khi nào quyền được dùng.
- Cách tắt tính năng và thu hồi quyền.

Không xin quyền khi khởi động chỉ để tránh hỏi sau này. Hãy xin ngay trước hành động người dùng yêu cầu.

### 12.3. Xử lý từ chối một cách bình thường

Nếu người dùng từ chối, giữ nguyên phần extension không cần quyền đó. Hiển thị hướng dẫn ngắn và nút thử lại khi người dùng chủ động muốn bật tính năng. Không lặp prompt, gây áp lực hoặc vô hiệu hóa toàn bộ extension nếu một integration tùy chọn bị từ chối.

### 12.4. Thu hồi quyền và xóa dữ liệu

Khi người dùng tắt integration, thu hồi host permission và dọn dữ liệu extension không còn cần. Host permission removal không tự xóa dữ liệu đã lưu trong `chrome.storage`, IndexedDB của extension hoặc backend. Cần có chính sách retention và cleanup riêng.

## 13. Ví dụ manifest hoàn chỉnh theo nguyên tắc least privilege

```json
{
  "manifest_version": 3,
  "name": "Portal assistant",
  "version": "1.0.0",
  "permissions": [
    "storage",
    "scripting"
  ],
  "host_permissions": [
    "https://portal.example.com/*"
  ],
  "optional_host_permissions": [
    "https://docs.example.net/*"
  ],
  "background": {
    "service_worker": "service-worker.js"
  },
  "action": {
    "default_title": "Portal assistant"
  },
  "content_scripts": [
    {
      "matches": [
        "https://portal.example.com/*"
      ],
      "js": [
        "content.js"
      ],
      "run_at": "document_idle"
    }
  ]
}
```

Manifest này giới hạn quyền thường trực vào một host và khai báo một host tùy chọn cho tích hợp tài liệu. Nếu tính năng chỉ chạy sau khi người dùng bấm action trên tab hiện tại, có thể xem xét `activeTab` thay cho host permission thường trực, tùy API và vòng đời cần hỗ trợ.

## 14. Thực hành: xin quyền host theo thao tác người dùng

Lab dùng extension thử nghiệm Manifest V3. Không dùng tài khoản production hoặc cấp `<all_urls>` chỉ để hoàn thành bài.

### 14.1. Khai báo optional permission

Trong manifest, khai báo:

```json
{
  "manifest_version": 3,
  "name": "Optional docs access lab",
  "version": "1.0.0",
  "permissions": ["storage"],
  "optional_host_permissions": [
    "https://docs.example.net/*"
  ],
  "action": {}
}
```

### 14.2. Tạo nút bật tích hợp

```html
<button id="enable-docs">Bật tích hợp Docs</button>
<output id="status"></output>
<script src="popup.js"></script>
```

```js
const enableButton = document.querySelector("#enable-docs");
const status = document.querySelector("#status");

enableButton.addEventListener("click", async () => {
  try {
    const granted = await chrome.permissions.request({
      origins: ["https://docs.example.net/*"]
    });

    status.textContent = granted
      ? "Đã cấp quyền cho Docs."
      : "Bạn chưa cấp quyền cho Docs.";
  } catch {
    status.textContent = "Không thể yêu cầu quyền lúc này.";
  }
});
```

Request được gọi trực tiếp trong click handler. UI không được giả định quyền đã cấp cho tới khi API trả về `true`.

### 14.3. Kiểm tra và thu hồi

```js
async function checkDocsPermission() {
  return chrome.permissions.contains({
    origins: ["https://docs.example.net/*"]
  });
}

async function removeDocsPermission() {
  return chrome.permissions.remove({
    origins: ["https://docs.example.net/*"]
  });
}
```

Kiểm tra lại quyền ngay trước khi thực hiện thao tác. Sau khi remove, xác minh tính năng Docs chuyển sang trạng thái disabled và dữ liệu cache riêng của integration được dọn theo policy.

### 14.4. Quan sát permission UI

- Load extension unpacked trong browser profile thử nghiệm.
- Mở extension details và kiểm tra site access.
- Chọn chế độ truy cập khi nhấn extension hoặc trên site cụ thể nếu browser cung cấp.
- Thử bật tích hợp Docs và quan sát permission prompt.
- Từ chối quyền; xác minh phần chức năng khác vẫn hoạt động.
- Cấp quyền rồi thu hồi từ extension details; xác minh extension phát hiện trạng thái mới.

## 15. Ma trận kiểm thử Host permission

| Mã | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| HOST-01 | Host permission cho một HTTPS host | Chỉ host được khai báo được cấp access |
| HOST-02 | Request tới sibling subdomain | Không được suy rộng từ host cụ thể |
| HOST-03 | Pattern `https://*.example.com/*` | Phạm vi subdomain được hiểu và kiểm tra đúng |
| HOST-04 | Pattern có path `/reports/*` trong host_permissions | Không coi path là giới hạn endpoint |
| HOST-05 | Content script match path cụ thể | Chỉ inject trên URL match theo content script pattern |
| HOST-06 | Scheme `*` | Chỉ các scheme được match-pattern support |
| HOST-07 | HTTP thay vì HTTPS | Không được cấp nếu chỉ khai báo HTTPS |
| HOST-08 | `<all_urls>` | Permission review cảnh báo phạm vi rộng |
| HOST-09 | Optional host permission chưa cấp | Tính năng báo permission-required |
| HOST-10 | Người dùng cấp optional permission | Tính năng hoạt động trong phạm vi được cấp |
| HOST-11 | Người dùng từ chối request | Extension tiếp tục hoạt động không cần quyền |
| HOST-12 | Người dùng thu hồi quyền trong settings | Extension phát hiện và xử lý access bị mất |
| HOST-13 | `permissions.contains()` trước thao tác | Kết quả được kiểm tra nhưng API call vẫn xử lý lỗi |
| HOST-14 | `permissions.remove()` | Optional permission bị thu hồi |
| HOST-15 | Request permission ngoài user gesture | Browser từ chối hoặc không cho prompt theo API contract |
| HOST-16 | `activeTab` sau click action | Chỉ có quyền tạm thời trên tab được kích hoạt |
| HOST-17 | Tab điều hướng sang origin khác | Không giả định activeTab vẫn cho phép host mới |
| HOST-18 | Content script đọc DOM | Dữ liệu DOM vẫn được coi là không tin cậy |
| HOST-19 | Content script fetch cross-origin | Tuân theo page-origin/CORS context |
| HOST-20 | Service worker fetch host được cấp | Request dùng đúng extension host permission |
| HOST-21 | Message chứa URL tùy ý | Service worker từ chối host/scheme ngoài allowlist |
| HOST-22 | Message từ frame không mong đợi | Sender tab/frame/url được kiểm tra |
| HOST-23 | Cookies API thiếu host permission | Truy cập cookie host bị từ chối |
| HOST-24 | Cookies API có host permission nhưng thiếu cookies | API permission vẫn bị thiếu |
| HOST-25 | File URL access chưa bật | Extension không truy cập file URL |
| HOST-26 | Người dùng bật file URL access | Chỉ chức năng cần thiết được kiểm tra |
| HOST-27 | Browser internal page | Host permission không vượt giới hạn browser |
| HOST-28 | Incognito chưa bật extension | Extension không giả định được quyền ở incognito |
| HOST-29 | Host wildcard chứa tenant không tin cậy | Review phát hiện phạm vi trust quá rộng |
| HOST-30 | Tắt integration và thu hồi quyền | Dữ liệu extension theo integration được dọn theo retention policy |

## 16. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| Khai báo host permission nghĩa là người dùng đã cấp quyền | Site access có thể bị withheld hoặc giới hạn |
| Content script matches và host_permissions là cùng một trường | Chúng phục vụ vai trò manifest khác nhau |
| Path trong host permission giới hạn endpoint | Host permission áp dụng ở cấp host; path không phải authorization boundary |
| `*.example.com` chỉ cho www | Wildcard có thể bao gồm nhiều subdomain và host gốc |
| `<all_urls>` tiện nên luôn nên dùng | Đây là quyền rộng, tăng tác động nếu extension bị compromise |
| `activeTab` là quyền dài hạn | Nó là grant tạm thời theo hành động người dùng/tab |
| Content script fetch luôn dùng host permission của extension | Fetch trong content script chịu page-origin/CORS context |
| Isolated world khiến DOM đáng tin | Page vẫn kiểm soát DOM và có thể tạo dữ liệu giả |
| Service worker có host permission thì nhận URL nào cũng được | Message handler phải giới hạn capability và validate sender |
| Có `cookies` permission là đọc cookie mọi host | Cần host permission tương ứng |
| Có host permission là đọc cookie | Còn cần API permission `cookies` |
| Thu hồi permission xóa dữ liệu đã lưu | Phải cleanup storage/cache riêng |
| CORS cho phép extension đọc filesystem | CORS không cấp quyền filesystem |
| Extension có quyền file URL tự động | Người dùng thường phải bật file access riêng |
| Permission warning chỉ là UX | Nó phản ánh phạm vi quyền người dùng cần đánh giá |

## 17. Checklist triển khai

- [ ] Khai báo đúng API permissions và host permissions theo chức năng.
- [ ] Ưu tiên host cụ thể, HTTPS và phạm vi tối thiểu.
- [ ] Chỉ dùng `<all_urls>` khi có lý do sản phẩm rõ ràng.
- [ ] Hiểu wildcard subdomain bao gồm những host nào.
- [ ] Không coi path của host permission là giới hạn endpoint.
- [ ] Phân biệt `content_scripts.matches` với `host_permissions`.
- [ ] Dùng `optional_host_permissions` cho tích hợp có thể bật sau.
- [ ] Gọi `permissions.request()` từ thao tác người dùng.
- [ ] Kiểm tra quyền ngay trước API call và xử lý permission denial.
- [ ] Cung cấp cách thu hồi quyền và tắt integration.
- [ ] Xem xét `activeTab` cho thao tác chỉ trên tab người dùng chủ động chọn.
- [ ] Không giả định content script fetch có extension-origin CORS privileges.
- [ ] Relay request qua service worker bằng capability cố định và sender validation.
- [ ] Không tin dữ liệu DOM hoặc message payload do trang kiểm soát.
- [ ] Chỉ dùng Cookies API khi có nhu cầu rõ, cả `cookies` và host permission.
- [ ] Xử lý file URL access và incognito như các quyền riêng.
- [ ] Không cố vượt giới hạn browser-internal pages.
- [ ] Dọn dữ liệu đã lưu khi integration bị tắt/thu hồi quyền.
- [ ] Kiểm thử cả trạng thái granted, withheld, denied và removed.
- [ ] Kiểm tra permission prompt và site access trên browser mục tiêu.

### Ghi nhớ

**Host permission xác định website mà extension có thể tương tác; quyền đó cần hẹp, rõ và có thể thu hồi.** `host_permissions` phục vụ host access cho extension API, `optional_host_permissions` cho phép xin sau, còn `content_scripts.matches` xác định nơi inject content script. Path trong host permission không giới hạn endpoint. `activeTab` cung cấp quyền tạm thời sau hành động người dùng. Content script vẫn phải coi DOM là không tin cậy và fetch của nó chịu ngữ cảnh page-origin/CORS. Hãy xin quyền đúng lúc, kiểm tra trạng thái thực tế, validate sender trong message passing và dọn dữ liệu khi quyền bị thu hồi.
