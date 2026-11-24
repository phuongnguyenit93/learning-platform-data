# URL trong analytics: nhận diện và ngăn rò rỉ dữ liệu

## 1. URL trong analytics là gì?

Analytics thường ghi nhận trang mà người dùng xem, nguồn điều hướng và hành động xảy ra trên trang. Một event page view có thể chứa tên sự kiện, route, URL hiện tại, referrer, title, campaign parameter và các thuộc tính khác. Nếu gửi nguyên URL vào analytics, query string hoặc path có thể làm lộ dữ liệu mà ứng dụng không định gửi cho hệ thống đo lường.

Ví dụ một trang đặt lại mật khẩu có URL:

```text
https://app.example.com/account/reset?email=demo@example.test&token=FAKE-RESET-123
```

URL này chứa email và token giả lập. Nếu analytics SDK tự động ghi `location.href` hoặc ứng dụng gửi toàn bộ URL, dữ liệu có thể được chuyển tới analytics vendor, hệ thống log hoặc công cụ giám sát. Nếu trang còn tải script bên thứ ba, script đó thường có thể đọc URL hiện tại trong page context và gửi dữ liệu đi.

URL leak không chỉ xảy ra qua query string. Path có thể chứa account ID, email hoặc mã đơn hàng; fragment có thể chứa state phía client hoặc token; referrer có thể tiết lộ trang trước đó; redirect và link decoration có thể mang identifier sang website tiếp theo.

**Nguyên tắc:** URL là dữ liệu đầu vào có thể chứa thông tin nhạy cảm. Analytics nên nhận tên route và các thuộc tính đã allowlist, không mặc định nhận URL đầy đủ, query string, fragment hoặc referrer thô.

Bài viết thuộc chương **Referrer và URL leak** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung kết nối URL analytics với origin, Referrer-Policy, request metadata, third-party scripts, logging, redirect, browser history và bảo vệ dữ liệu trong ứng dụng web.

Sau bài học, bạn có thể:

- Nhận diện dữ liệu nhạy cảm trong path, query và fragment.
- Phân biệt dữ liệu URL mà server, browser và JavaScript có thể nhìn thấy.
- Giải thích cách URL đi vào analytics qua page-view tự động, SPA route, beacon và SDK tự động.
- Hiểu Referrer-Policy và giới hạn của header Referer.
- Nhận diện rò rỉ qua server log, CDN, APM, error reporting và redirect.
- Thiết kế analytics payload theo route allowlist và data minimization.
- Xử lý URL callback chứa authorization code hoặc reset token.
- Dùng replaceState để loại bỏ parameter nhạy cảm sau khi xử lý đúng cách.
- Kết hợp CSP, consent và kiểm soát script bên thứ ba.
- Thực hành so sánh raw URL với event đã lọc bằng lab local.

## 2. URL gồm những phần nào?

Một URL có thể gồm scheme, authority, path, query và fragment:

```text
https://app.example.com/orders/4821?email=demo%40example.test&tab=history#invoice
```

| Thành phần | Ví dụ | Có thể tiết lộ |
|---|---|---|
| Scheme | `https` | Giao thức được dùng |
| Host | `app.example.com` | Website/dịch vụ được truy cập |
| Port | `:8443` | Cấu hình endpoint |
| Path | `/orders/4821` | Account ID, order ID, loại trang hoặc dữ liệu định danh |
| Query | `?email=...&tab=history` | Email, search term, token, campaign ID, filter |
| Fragment | `#invoice` | Trạng thái điều hướng phía client, tab hoặc dữ liệu ứng dụng |

### 2.1. Path cũng có thể chứa dữ liệu nhạy cảm

Không phải chỉ query string mới cần lọc. Các route dạng sau có thể làm lộ định danh:

```text
https://app.example.com/users/alice@example.test
https://app.example.com/reset/FAKE-RESET-TOKEN
https://app.example.com/invoices/customer-93821/4821
```

Path được gửi trong request line tới server và thường xuất hiện trong access log, proxy log hoặc APM. Vì vậy, đưa ID người dùng vào path vẫn có thể làm lộ dữ liệu dù không có query string.

Hãy dùng route template hoặc tên trang đã định nghĩa trong analytics, ví dụ `user-profile` hoặc `invoice-detail`, thay vì gửi path thực tế.

### 2.2. Query string thường được ghi lại ở nhiều lớp

Query string được gửi cùng HTTP request tới server. Nó có thể xuất hiện trong:

- Browser developer tools và network logs.
- Web server access log.
- Reverse proxy, CDN, load balancer và WAF logs.
- APM, tracing và error monitoring.
- Analytics SDK hoặc tag manager.
- Link được copy, gửi qua chat hoặc lưu trong bookmark.
- Browser history và đồng bộ history giữa thiết bị.

Một URL có HTTPS vẫn có thể bị ghi lại ở endpoint, proxy hoặc browser. HTTPS bảo vệ dữ liệu trên đường truyền giữa các điểm kết nối; nó không tự động xóa query khỏi log hoặc analytics payload.

### 2.3. Fragment có hành vi khác query

Phần sau dấu `#` được gọi là fragment. Browser không gửi fragment trong HTTP request tới server và không đưa fragment vào header Referer theo quy tắc URL/referrer thông thường.

Tuy nhiên, JavaScript của trang có thể đọc fragment qua `location.hash` hoặc toàn bộ URL qua `location.href`. Vì vậy, nếu analytics SDK gửi nguyên URL từ JavaScript, fragment vẫn có thể bị thu thập.

Ví dụ:

```js
console.log(location.pathname); // /callback
console.log(location.search);   // ?code=...
console.log(location.hash);     // #state=...
console.log(location.href);     // Có cả query và fragment
```

Không suy luận rằng fragment an toàn chỉ vì server không nhận nó. Nó vẫn có thể xuất hiện trong browser history, screenshot, clipboard, log phía client hoặc event analytics.

### 2.4. Userinfo và các phần URL khác

URL có thể có userinfo trước host, nhưng không nên nhúng username/password vào URL. Các thành phần này có thể xuất hiện trong history, copy/paste hoặc công cụ xử lý URL và tạo rủi ro ngoài ý muốn.

Khi phân tích URL, dùng API `URL` và `URLSearchParams` thay vì tự tách chuỗi bằng regex. Nhưng parse đúng cú pháp không làm dữ liệu trở nên an toàn; ứng dụng vẫn cần quyết định trường nào được phép gửi.

## 3. URL đi vào analytics bằng cách nào?

### 3.1. Page view tự động

Nhiều analytics SDK có thể tự thu thập page view hoặc tự đính kèm các thuộc tính như page location, page title và referrer. Tên field và mặc định phụ thuộc sản phẩm, phiên bản và cấu hình.

Nếu URL hiện tại có token hoặc dữ liệu cá nhân, tính năng auto page view có thể gửi các giá trị đó trước khi ứng dụng kịp lọc. Cần kiểm tra cấu hình SDK và payload thực tế trong Network tab, không dựa vào tên gọi "ẩn danh" hoặc "analytics cơ bản".

### 3.2. Ứng dụng tự gửi location.href

Một pattern dễ gây rò rỉ:

```js
analytics.track("page_view", {
  url: location.href,
  referrer: document.referrer
});
```

Cả hai field đều có thể chứa dữ liệu không cần thiết. `location.href` có thể chứa path, query và fragment; `document.referrer` có thể chứa URL trang trước tùy Referrer-Policy và nguồn điều hướng.

Nếu vendor cần biết trang nào được xem, gửi page name hoặc route template thay vì URL thô.

### 3.3. Single-page application (SPA)

Trong SPA, điều hướng thường thay đổi bằng History API mà không tải document mới. Analytics có thể được gọi trong router hook hoặc listener cho `popstate`.

Các lỗi thường gặp:

- Gửi URL đầy đủ sau mỗi lần `pushState`.
- Gửi search term hoặc filter trong query.
- Gửi route chứa user ID hoặc order ID.
- Gửi cả URL cũ và URL mới khi transition.
- Gửi page view trước khi consent hoặc privacy preference được áp dụng.
- Gửi lại page view nhiều lần khi component mount/remount.

Hãy xây dựng một hàm tạo analytics event duy nhất, nhận route đã phân loại và chỉ xuất các field được phép.

### 3.4. Beacon và event khi rời trang

`navigator.sendBeacon()` thường được dùng để gửi analytics không chặn navigation. Nếu payload chứa `location.href`, query và fragment có thể bị gửi tới collector.

```js
const payload = {
  event: "page_exit",
  page_url: location.href
};

navigator.sendBeacon(
  "/analytics/collect",
  new Blob([JSON.stringify(payload)], {
    type: "text/plain"
  })
);
```

sendBeacon không phải cơ chế tự động ẩn dữ liệu. Nó chỉ là một cách gửi request; nội dung payload vẫn do ứng dụng quyết định. Không gửi URL thô chỉ vì request được gửi trong sự kiện pagehide hoặc navigation.

### 3.5. Referrer và analytics

Một analytics SDK có thể tự đọc `document.referrer` hoặc browser có thể gửi header `Referer` khi tải resource. Hai cơ chế này liên quan nhưng không đồng nhất:

- `document.referrer` là thuộc tính của document, phản ánh referrer mà browser cung cấp cho navigation hiện tại.
- Header `Referer` là request header được browser gửi tới server đích theo Referrer Policy.
- Analytics payload là dữ liệu JavaScript chủ động gửi; policy của Referer không tự lọc payload đó.

Vì vậy, đặt Referrer-Policy không đủ nếu code analytics vẫn gửi `location.href` hoặc `document.referrer`.

## 4. Những dữ liệu không nên đặt trong URL

URL có thể đi qua nhiều hệ thống và người nhận hơn dự kiến. Tránh đặt trực tiếp:

- Password, PIN hoặc OTP.
- Access token, refresh token hoặc session secret.
- Reset-password token hoặc invite token có quyền sử dụng.
- Email, số điện thoại hoặc địa chỉ cá nhân nếu không cần.
- Search term có thể chứa thông tin riêng tư.
- Dữ liệu sức khỏe, tài chính hoặc nội dung form.
- Session ID, account ID ổn định hoặc identifier có thể liên kết người dùng.
- Thông tin nội bộ về khách hàng, hợp đồng hoặc tài nguyên được bảo vệ.

Ngay cả khi parameter đã được URL-encode, dữ liệu vẫn là dữ liệu gốc sau khi decode. Encoding không phải encryption và không làm query string trở thành nơi lưu secret an toàn.

### 4.1. Token trong URL

Một URL reset password dạng:

```text
https://app.example.com/reset?token=ONE_TIME_SECRET
```

có thể làm token xuất hiện trong access log, analytics, history và referrer. Nếu trang tải script bên thứ ba trước khi xử lý token, script cùng page context có thể đọc URL.

Nếu kiến trúc bắt buộc dùng token trong link email:

1. Dùng token ngẫu nhiên, một lần và thời hạn ngắn.
2. Chỉ gửi token qua HTTPS.
3. Không tải analytics, quảng cáo hoặc script bên thứ ba trên trang callback/reset.
4. Đặt Referrer-Policy chặt, thường là `no-referrer` cho trang nhạy cảm.
5. Đổi token lấy một phiên xử lý phía server, xác minh và tiêu thụ token ngay.
6. Loại token khỏi URL/history sau khi đã xử lý bằng cách phù hợp.
7. Redact query trong access log, proxy, APM và error monitoring.
8. Không ghi token vào log ứng dụng hoặc telemetry.

`history.replaceState()` chỉ làm sạch URL hiển thị trong history hiện tại sau khi trang đã tải. Nó không xóa request ban đầu khỏi server log, CDN log hoặc các hệ thống đã nhận URL trước thời điểm cleanup.

### 4.2. OAuth/OIDC callback

Một số flow OAuth/OIDC trả authorization code và state trong query của callback URL. Authorization code là credential ngắn hạn, dùng một lần và cần được trao đổi đúng client/redirect URI; nó vẫn phải được bảo vệ cho tới khi exchange hoàn tất.

Khuyến nghị:

- Dùng Authorization Code Flow với PKCE cho public clients theo hướng dẫn hiện hành.
- Xác thực state và các tham số giao thức trước khi hoàn tất callback.
- Không gửi URL callback nguyên vẹn tới analytics hoặc third-party script.
- Hạn chế log query tại edge/server.
- Đổi code lấy token qua back channel theo đúng flow.
- Sau khi xử lý, dùng replaceState để loại code/state khỏi URL nếu không còn cần.
- Không dùng access token trong query string.

Không loại bỏ state trước khi ứng dụng đã xác minh nó. Không đưa code hoặc token vào event, exception message hoặc support log.

## 5. Referrer và Referrer-Policy

### 5.1. Header Referer

Khi browser điều hướng hoặc tải tài nguyên, nó có thể gửi header `Referer` để cho server biết nguồn điều hướng. Tên header được viết theo lịch sử là "Referer".

Giá trị có thể bao gồm origin, path và query của URL nguồn, tùy Referrer Policy. Fragment và userinfo không được gửi trong Referer thông thường.

Server nhận Referer có thể ghi nó vào access log, analytics hoặc fraud monitoring. Vì thế, URL nguồn nhạy cảm có thể rò rỉ sang một endpoint khác nếu policy cho phép.

### 5.2. Referrer-Policy

Referrer Policy quyết định lượng thông tin referrer browser gửi:

| Policy | Hành vi khái quát |
|---|---|
| `no-referrer` | Không gửi Referer |
| `same-origin` | Chỉ gửi Referer cho request same-origin |
| `origin` | Chỉ gửi origin |
| `strict-origin` | Chỉ gửi origin; không gửi khi downgrade từ HTTPS xuống HTTP |
| `origin-when-cross-origin` | Full URL same-origin, chỉ origin cross-origin |
| `strict-origin-when-cross-origin` | Full URL same-origin; chỉ origin cross-origin; bỏ referrer khi downgrade |
| `no-referrer-when-downgrade` | Gửi full URL trừ trường hợp downgrade |
| `unsafe-url` | Gửi full URL trong nhiều trường hợp, kể cả cross-origin; tránh dùng cho dữ liệu nhạy cảm |

Các browser hiện đại thường dùng `strict-origin-when-cross-origin` làm default nếu trang không đặt policy khác. Không nên dựa vào default vì header, meta tag hoặc thuộc tính element có thể thay đổi kết quả.

### 5.3. Đặt policy ở response header

Ví dụ:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Với trang chứa token hoặc thông tin nhạy cảm, có thể dùng policy chặt hơn:

```http
Referrer-Policy: no-referrer
```

Response header áp dụng cho document và các request phát sinh theo quy tắc của browser. Cần kiểm tra header trên response thực tế, kể cả trang callback, error page và route SPA được server fallback.

### 5.4. Meta tag và thuộc tính element

Có thể khai báo trong HTML:

```html
<meta name="referrer" content="no-referrer">
```

Hoặc giới hạn một link cụ thể:

```html
<a href="https://external.example.net/" rel="noreferrer">
  Mở website bên ngoài
</a>
```

Thuộc tính `referrerpolicy` cũng có thể áp dụng cho một số element tải resource. Tuy vậy, policy ở response header thường dễ quản lý tập trung hơn.

### 5.5. Referrer-Policy không lọc analytics payload

Nếu JavaScript chạy trong page gửi:

```js
analytics.track("page_view", {
  url: location.href
});
```

thì browser không tự loại query/fragment theo Referrer-Policy. Policy kiểm soát referrer metadata, không kiểm soát mọi dữ liệu mà script chủ động gửi.

Ngoài ra, third-party classic script thường chạy trong realm của page và có thể đọc `location.href`. Đặt `no-referrer` không ngăn script đó đọc URL hiện tại.

## 6. Các đường rò rỉ URL thường gặp

### 6.1. Browser history và đồng bộ

URL đầy đủ có thể lưu trong history, bookmark, session restore và cơ chế đồng bộ browser giữa thiết bị. Người dùng có thể copy link hoặc chia sẻ màn hình; ứng dụng không kiểm soát toàn bộ các nơi này.

Đừng coi URL query là nơi an toàn chỉ vì nó không hiển thị trong nội dung trang.

### 6.2. Server và infrastructure logs

HTTP request target thường gồm path và query. Các hệ thống có thể ghi lại:

- CDN/reverse proxy access log.
- Web server access log.
- WAF/security event.
- Load balancer log.
- APM trace/span URL.
- Error reporting và exception context.
- Audit log của backend.

Thiết lập log theo route template, redact các parameter nhạy cảm và giới hạn quyền truy cập/retention. Nếu cần query để xử lý request, backend vẫn có thể dùng query nhưng không nhất thiết phải ghi nguyên giá trị vào log.

### 6.3. Third-party resource request

Trang có URL nhạy cảm có thể tải image, font, script, iframe hoặc beacon từ bên thứ ba. Referer được gửi tùy policy. Ngoài ra, script bên thứ ba chạy trong page có thể đọc URL trực tiếp.

Đặc biệt, một script analytics được phép thực thi trong document có thể truy cập các thuộc tính JavaScript mà page có quyền đọc. Referrer-Policy chỉ giảm một kênh metadata; nó không sandbox script.

### 6.4. Redirect và link decoration

Một redirector có thể nhận URL chứa click ID hoặc query rồi chuyển tiếp sang site khác. Nếu ứng dụng chuyển tiếp toàn bộ query string không kiểm soát, secret hoặc identifier có thể đi qua nhiều domain.

Chỉ chuyển tiếp parameter đã allowlist. Không nối toàn bộ query vào redirect URL đích. Kiểm tra open redirect và không cho phép attacker tùy ý chọn host đích.

### 6.5. Error monitoring

Một số SDK ghi lại current URL khi xảy ra exception hoặc gửi breadcrumb navigation. Nếu query có token hoặc dữ liệu cá nhân, exception event có thể chứa dữ liệu đó dù analytics page view đã được lọc.

Cấu hình redaction ở error monitoring, không đính kèm URL thô mặc định và tránh đưa secret vào exception message.

### 6.6. Screenshot, support ticket và clipboard

URL có thể được copy vào ticket hỗ trợ, chat, email hoặc ảnh chụp màn hình. Nếu token nằm trong URL, việc chia sẻ link vô tình có thể trao quyền sử dụng token cho người nhận.

Dùng URL sạch trước khi người dùng được yêu cầu copy/chia sẻ. Hướng dẫn support không yêu cầu gửi URL chứa token; nếu cần điều tra, dùng request ID hoặc correlation ID không có quyền truy cập dữ liệu.

## 7. Thiết kế analytics an toàn

### 7.1. Ưu tiên route name thay URL

Thay vì gửi:

```js
analytics.track("page_view", {
  page_location: location.href,
  page_referrer: document.referrer
});
```

hãy gửi một tên trang do ứng dụng kiểm soát:

```js
const pageNames = new Map([
  ["/", "home"],
  ["/products", "product-list"],
  ["/checkout", "checkout"],
  ["/account/reset", "password-reset"]
]);

function getAnalyticsPageName(pathname) {
  return pageNames.get(pathname) || "other";
}

function trackPageView() {
  analytics.track("page_view", {
    page_name: getAnalyticsPageName(location.pathname)
  });
}
```

Nếu route có dynamic ID, không gửi nguyên path. Dùng route matcher để phân loại thành `product-detail` hoặc `order-detail` mà không đính kèm ID.

### 7.2. Allowlist parameter thực sự cần

Nếu cần đo campaign, chỉ cho phép các giá trị đã định dạng và không chứa identifier cá nhân:

```js
function getAllowedCampaign(url) {
  const value = url.searchParams.get("campaign");

  if (!value || !/^[a-z0-9_-]{1,32}$/i.test(value)) {
    return undefined;
  }

  return value;
}

const currentUrl = new URL(location.href);

analytics.track("page_view", {
  page_name: getAnalyticsPageName(currentUrl.pathname),
  campaign: getAllowedCampaign(currentUrl)
});
```

Allowlist cần gắn với mục đích cụ thể. Đừng cho phép toàn bộ query chỉ vì hiện tại ứng dụng "chưa dùng token". Một parameter tưởng như vô hại có thể được tái sử dụng cho email, account ID hoặc search term trong tương lai.

### 7.3. Referrer category thay referrer URL

Nếu analytics cần đo nguồn điều hướng, có thể chỉ gửi nhóm nguồn:

```js
function getReferrerCategory(referrerValue) {
  if (!referrerValue) return "direct";

  try {
    const referrer = new URL(referrerValue);

    if (referrer.origin === location.origin) {
      return "internal";
    }

    return "external";
  } catch {
    return "unknown";
  }
}

analytics.track("page_view", {
  page_name: getAnalyticsPageName(location.pathname),
  referrer_type: getReferrerCategory(document.referrer)
});
```

Nếu cần phân tích campaign/referral, dùng taxonomy rõ ràng và không gửi full path/query. Việc gửi origin/domain vẫn có thể tiết lộ nguồn truy cập; chỉ giữ khi metric thực sự cần.

### 7.4. Tắt auto page view và gửi event sau khi lọc

Với SDK hỗ trợ auto page view, hãy kiểm tra cách tắt hoặc cấu hình lại. Sau đó, ứng dụng tự gửi page view sau khi route đã được phân loại và consent đã được áp dụng.

Tên cấu hình khác nhau giữa vendor. Không copy một option cụ thể nếu chưa kiểm tra tài liệu SDK đang dùng. Hãy xác minh bằng Network payload rằng SDK không còn gửi page_location/page_referrer thô.

### 7.5. SPA route tracking

Tạo một hàm chung cho router:

```js
function onRouteChanged(route) {
  const pageName = route.analyticsName || "other";

  analytics.track("page_view", {
    page_name: pageName
  });
}

// Router gọi hàm này sau mỗi navigation thành công.
```

Không tự động gửi `location.href` trong listener `popstate` hoặc hook route. Đảm bảo page view không bị gửi trùng và trạng thái consent được kiểm tra trước mỗi event.

### 7.6. Data minimization và retention

Chỉ thu thập field cần thiết cho metric. Đặt thời hạn lưu, giới hạn quyền truy cập và xác định vendor/subprocessor nhận dữ liệu. Pseudonymous ID vẫn có thể liên kết hành vi và không tự động trở thành dữ liệu ẩn danh.

Không thu thập URL đầy đủ chỉ vì analytics SDK có field mặc định đó. Định nghĩa metric trước, sau đó chọn dữ liệu tối thiểu để tính metric.

## 8. Làm sạch URL nhạy cảm

### 8.1. Dùng replaceState sau khi đã xử lý

Khi ứng dụng buộc phải nhận một token hoặc code trong URL, có thể xóa parameter khỏi thanh địa chỉ/history sau khi xác minh và xử lý xong:

```js
function removeSensitiveParameters() {
  const url = new URL(location.href);

  for (const name of [
    "token",
    "access_token",
    "id_token",
    "code"
  ]) {
    url.searchParams.delete(name);
  }

  // Fragment có thể chứa state phía client; chỉ xóa sau khi đã xử lý.
  url.hash = "";

  history.replaceState(
    history.state,
    "",
    url.pathname + url.search
  );
}
```

Không chạy cleanup trước khi hoàn tất việc xác minh và exchange cần thiết. Với OAuth callback, server-side callback và code exchange thường là lựa chọn tốt hơn để giảm thời gian code nằm trong page context.

### 8.2. Cleanup không xóa log đã phát sinh

Khi browser yêu cầu trang, server/CDN đã nhận path và query trước khi JavaScript chạy. `replaceState` không thể thu hồi dữ liệu khỏi:

- Request log đã ghi.
- Proxy/CDN/WAF log.
- Analytics event đã gửi.
- Referrer đã được gửi tới request khác.
- Screenshot, clipboard hoặc history đã đồng bộ.

Do đó, cleanup là lớp giảm tiếp xúc tiếp theo. Biện pháp chính vẫn là không đặt secret trong URL hoặc redact tại nơi nhận request.

### 8.3. Tránh third-party code trước khi cleanup

Trang callback hoặc reset token nên là trang tối giản:

- Không tải analytics/ad/tag manager.
- Không nhúng widget bên ngoài.
- Đặt Referrer-Policy phù hợp, thường là no-referrer.
- Không ghi URL vào console hoặc error monitoring.
- Xử lý token/code ngay và loại bỏ khỏi URL.
- Điều hướng sang trang sạch sau khi hoàn tất.

Nếu script bên thứ ba đã chạy trước cleanup, nó có thể đọc URL nhạy cảm qua location.

### 8.4. Cache và response nhạy cảm

Với trang xử lý token hoặc thông tin cá nhân, cân nhắc:

```http
Cache-Control: no-store
Referrer-Policy: no-referrer
```

`no-store` hạn chế lưu response vào HTTP cache theo quy tắc caching. Nó không xóa browser history, server log hoặc analytics payload. Vẫn cần xử lý URL, script và log riêng.

## 9. Kiểm soát logging ở server

### 9.1. Log route template thay vì URL đầy đủ

Một access log có thể ghi:

```text
GET /orders/4821?email=demo@example.test 200
```

Thay vì lưu nguyên request target, log route template và request ID:

```text
GET /orders/:orderId 200 request_id=7f3a...
```

Nếu cần giữ query để điều tra, chỉ log tên parameter đã allowlist hoặc trạng thái có/không có, không log value nhạy cảm.

### 9.2. Redact ở mọi tầng

Redaction chỉ ở analytics SDK là chưa đủ. Kiểm tra:

- CDN và edge logs.
- Reverse proxy và ingress controller.
- Web server access logs.
- Application logs.
- APM/tracing.
- Error monitoring.
- Security/WAF event.
- Analytics collector.
- Data warehouse và export.

Một hệ thống có thể đã nhận URL trước khi ứng dụng lọc payload. Hãy áp dụng quy tắc redaction càng gần điểm thu nhận càng tốt và giới hạn quyền truy cập log.

### 9.3. Correlation ID thay URL chứa secret

Để debug, tạo request ID ngẫu nhiên không chứa quyền truy cập và liên kết log qua ID đó. Support hoặc developer có thể tra cứu trace bằng request ID theo quyền được cấp, thay vì yêu cầu người dùng gửi URL chứa token.

Không dùng email, access token hoặc session ID làm correlation ID.

### 9.4. Retention và access control

Log vẫn có thể chứa dữ liệu cá nhân ngay cả khi đã redact một số parameter. Cần:

- Thời hạn lưu phù hợp mục đích.
- Quyền truy cập theo vai trò.
- Audit việc truy cập log.
- Mã hóa storage log và backup.
- Quy trình xóa hoặc xử lý yêu cầu dữ liệu.
- Kiểm tra dữ liệu log được export sang vendor nào.

## 10. CSP và các lớp bảo vệ liên quan

### 10.1. CSP giới hạn nơi script gửi dữ liệu

`connect-src` giới hạn một số đích của fetch, XHR, WebSocket, EventSource và beacon. `img-src` giới hạn image/pixel; `script-src` giới hạn script; `frame-src` giới hạn iframe.

Ví dụ policy minh họa:

```http
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-random-value';
  connect-src 'self' https://analytics.example.net;
  img-src 'self' data:;
  frame-src 'self';
  object-src 'none';
  base-uri 'self'
```

Policy phải phù hợp ứng dụng và được kiểm thử. Nếu analytics endpoint được cho phép trong connect-src, script vẫn có thể gửi dữ liệu tới endpoint đó. CSP không tự lọc query hoặc payload.

### 10.2. CSP không thay thế data minimization

Một endpoint được allowlist vẫn có thể nhận dữ liệu quá mức. Hãy kết hợp:

- Route allowlist.
- Field allowlist.
- Consent gating.
- Script inventory.
- Review vendor.
- Server-side redaction.
- Kiểm tra payload thực tế.

### 10.3. SRI và third-party script

Subresource Integrity giúp browser xác minh nội dung script/style tĩnh khớp hash mong đợi. Nó giảm nguy cơ tài nguyên bị thay đổi ngoài ý muốn, nhưng script đã được xác minh vẫn có thể đọc URL nếu được thực thi trong page realm.

SRI là kiểm soát tính toàn vẹn, không phải bộ lọc privacy. Hãy giảm số script bên thứ ba và chỉ cấp dữ liệu cần thiết.

### 10.4. Consent và preference

Nếu analytics cần consent theo yêu cầu áp dụng, tag không cần thiết phải chờ lựa chọn phù hợp. Khi người dùng từ chối hoặc rút lại consent, ngăn event mới và áp dụng chính sách cho state đã lưu.

Consent banner không làm sạch URL, không xóa log và không ngăn script đã chạy đọc location. Hãy áp dụng consent trước khi khởi tạo analytics hoặc tag manager.

## 11. Lab local: so sánh URL thô và analytics event đã lọc

Lab dùng hai server loopback trên hai port:

- Ứng dụng: `http://127.0.0.1:8080`.
- Analytics collector giả lập: `http://127.0.0.1:8081`.

Trang demo sẽ được mở bằng URL có dữ liệu hoàn toàn giả. Server ứng dụng có thể nhìn thấy query trong request; fragment không được gửi tới server. Khi bấm nút, browser gửi một payload analytics tới collector để so sánh cách gửi URL thô với route name đã lọc.

Chỉ dùng dữ liệu giả trong lab. Không nhập token, email hoặc URL thật của tài khoản.

### 11.1. Tạo file index.html

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>URL analytics privacy lab</title>
</head>
<body>
  <h1>URL analytics privacy lab</h1>
  <p id="current-route"></p>
  <p id="status" aria-live="polite">Chưa gửi event.</p>

  <button id="send-raw">Gửi URL thô (demo rủi ro)</button>
  <button id="send-safe">Gửi event đã lọc</button>

  <h2>Payload chuẩn bị gửi</h2>
  <pre id="preview"></pre>

  <script>
    const collector = "http://127.0.0.1:8081/collect";
    const status = document.getElementById("status");
    const preview = document.getElementById("preview");

    const routeNames = new Map([
      ["/", "home"],
      ["/account/reset", "password-reset"],
      ["/products", "product-list"]
    ]);

    function getPageName(pathname) {
      return routeNames.get(pathname) || "other";
    }

    function sendPayload(payload) {
      const body = new Blob(
        [JSON.stringify(payload)],
        { type: "text/plain" }
      );

      const queued = navigator.sendBeacon(collector, body);
      status.textContent = queued
        ? "Browser đã xếp request vào hàng đợi. Xem terminal collector để xác nhận."
        : "Browser không xếp được request; thử lại.";
      preview.textContent = JSON.stringify(payload, null, 2);
    }

    document.getElementById("current-route").textContent =
      "Route hiện tại: " + getPageName(location.pathname);

    document.getElementById("send-raw").addEventListener("click", () => {
      // Chỉ dùng URL giả trong lab để thấy query và fragment có thể bị gửi.
      sendPayload({
        event: "page_view",
        page_url: location.href,
        page_referrer: document.referrer
      });
    });

    document.getElementById("send-safe").addEventListener("click", () => {
      // Payload production nên chỉ gồm route name và field đã allowlist.
      sendPayload({
        event: "page_view",
        page_name: getPageName(location.pathname)
      });
    });
  </script>
</body>
</html>
```

### 11.2. Tạo file server.mjs

```js
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";

const html = await readFile(
  new URL("./index.html", import.meta.url)
);

const appServer = createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:8080");

  if (url.pathname === "/favicon.ico") {
    res.writeHead(204).end();
    return;
  }

  // Lab cố ý hiển thị query giả để chứng minh server nhận query,
  // nhưng fragment không nằm trong HTTP request.
  console.log("APP REQUEST:", {
    path: url.pathname,
    query: url.search
  });

  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Referrer-Policy": "strict-origin-when-cross-origin"
  });
  res.end(html);
});

const analyticsServer = createServer(async (req, res) => {
  const origin = req.headers.origin || "";

  res.setHeader("Access-Control-Allow-Origin", "http://127.0.0.1:8080");
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");

  if (req.method === "OPTIONS") {
    res.writeHead(204).end();
    return;
  }

  if (req.method !== "POST" || req.url !== "/collect") {
    res.writeHead(404).end("Not found");
    return;
  }

  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }

  const rawBody = Buffer.concat(chunks).toString("utf8");

  console.log("ANALYTICS REQUEST:", {
    origin,
    referer: req.headers.referer || "(no Referer)",
    payload: rawBody
  });

  res.writeHead(204, {
    "Cache-Control": "no-store"
  });
  res.end();
});

appServer.listen(8080, "127.0.0.1", () => {
  console.log("App:       http://127.0.0.1:8080");
});

analyticsServer.listen(8081, "127.0.0.1", () => {
  console.log("Collector: http://127.0.0.1:8081");
});
```

### 11.3. Chạy lab

Trong thư mục chứa hai file, chạy:

```bash
node server.mjs
```

Mở URL giả sau trong browser:

```text
http://127.0.0.1:8080/account/reset?email=demo%40example.test&token=FAKE-RESET-123#access_token=FAKE-FRAGMENT-456
```

Các giá trị trên chỉ là chuỗi giả. Không thay bằng token hoặc email thật.

### 11.4. Quan sát kết quả

1. Xem terminal app server: request có path và query; không có fragment.
2. Trang hiển thị route name `password-reset`.
3. Mở DevTools → Network và bật Preserve log.
4. Bấm **Gửi URL thô**.
5. Xem terminal collector: payload chứa query và fragment vì JavaScript gửi `location.href`.
6. Xem header Referer của request collector: với policy strict-origin-when-cross-origin và hai port khác nhau, browser thường chỉ gửi origin, không gửi full path/query.
7. Bấm **Gửi event đã lọc**.
8. Xem terminal collector: payload chỉ có event và page name.
9. So sánh hai payload; request đã lọc không mang email/token giả.
10. Xóa query và fragment khỏi URL, reload và thử lại.

`sendBeacon()` trả về boolean cho biết browser đã chấp nhận xếp request vào hàng đợi; nó không chứng minh collector đã xử lý thành công. Terminal collector là nơi xác nhận request đã tới trong lab.

### 11.5. Thử Referrer-Policy

Thử thay response header trong lab thành `no-referrer` rồi reload. Khi bấm gửi event, kiểm tra header Referer ở collector không còn được gửi.

Sau đó thử `origin` để quan sát chỉ origin được gửi. Không thử `unsafe-url` trên dữ liệu thật; policy này có thể gửi full URL trong nhiều context và làm tăng rò rỉ.

Kết quả có thể khác theo browser và context. Hãy kiểm tra request headers thực tế thay vì suy luận từ cấu hình.

### 11.6. Giới hạn của lab

Lab minh họa sự khác biệt giữa request URL, fragment, Referer và analytics payload. Nó không mô phỏng toàn bộ analytics SDK, CDN, APM hoặc consent platform. Trong production, cần kiểm tra cả network payload, browser logs, server logs và vendor configuration.

## 12. Checklist review URL trong analytics

Trước khi phát hành analytics hoặc trang có URL callback:

1. **URL inventory:** Path/query/fragment có thể chứa ID, token, email hoặc search term không?
2. **Page view:** SDK có auto-collect page_location/page_referrer không?
3. **SPA:** Router có gửi URL thô sau pushState/popstate không?
4. **Beacon:** Payload khi pagehide có chứa location.href không?
5. **Referrer:** Response có Referrer-Policy phù hợp không?
6. **Third-party script:** Script bên ngoài có thể đọc URL trước khi cleanup không?
7. **OAuth/reset:** Code/token có ngắn hạn, một lần và được xử lý đúng flow không?
8. **Cleanup:** URL có được làm sạch sau khi xác minh/exchange hoàn tất không?
9. **Server logs:** CDN, proxy, web server, WAF và APM có redact query nhạy cảm không?
10. **Error monitoring:** SDK có ghi current URL hoặc breadcrumb chứa query không?
11. **Allowlist:** Analytics chỉ nhận route name và field đã được duyệt không?
12. **Consent:** Analytics có chỉ chạy sau lựa chọn phù hợp không?
13. **CSP:** connect-src/img-src/script-src có giới hạn theo vendor cần thiết không?
14. **Retention:** Payload và log có retention/access control rõ ràng không?
15. **Verification:** Đã kiểm tra Network payload và collector thực tế chưa?

## 13. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "HTTPS làm query string bí mật." | HTTPS bảo vệ trên đường truyền; endpoint và log vẫn có thể thấy query. |
| "Fragment không gửi lên server nên luôn an toàn." | JavaScript có thể đọc fragment và gửi nó trong analytics payload. |
| "Referrer-Policy no-referrer lọc mọi URL analytics." | Policy chỉ kiểm soát referrer metadata; script vẫn có thể gửi location.href. |
| "Không có CORS header thì analytics không nhận event." | CORS liên quan quyền đọc response; không nên dựa vào nó để lọc dữ liệu gửi. |
| "Chỉ query string mới nhạy cảm." | Path, fragment, referrer và redirect parameter cũng có thể chứa dữ liệu. |
| "Hash token không thể bị lộ." | Hash không được gửi trong request ban đầu nhưng có thể bị JavaScript, history hoặc analytics thu thập. |
| "replaceState xóa token khỏi mọi nơi." | Nó cập nhật URL/history hiện tại; server/CDN log và event đã gửi vẫn còn. |
| "Analytics vendor chỉ nhận field mình truyền thủ công." | SDK có thể tự thu page URL, title, referrer hoặc navigation event tùy cấu hình. |
| "Ẩn query trên UI là đủ." | Network request, log, SDK và script vẫn có thể nhìn thấy URL. |
| "Hash email là anonymous." | Hash có thể được đối chiếu và liên kết; thường chỉ là pseudonymous identifier. |
| "CSP tự loại parameter nhạy cảm." | CSP giới hạn nguồn request/script, không làm sạch payload. |
| "SRI ngăn analytics đọc URL." | SRI xác minh file; script đã chạy vẫn có quyền của page realm. |
| "Server-side analytics không thể rò rỉ URL." | Backend vẫn có thể gửi URL hoặc identifier nếu payload không được lọc. |
| "Consent banner làm sạch dữ liệu đã thu." | Consent điều khiển việc xử lý theo lựa chọn; không thu hồi log/event đã gửi trước đó. |

## 14. Câu hỏi ôn tập

1. URL có những thành phần nào và thành phần nào thường xuất hiện trong HTTP request?
2. Vì sao path có thể làm lộ thông tin cá nhân dù không có query?
3. Fragment khác query string ở điểm nào?
4. Vì sao JavaScript analytics có thể thu thập fragment?
5. Analytics SDK có thể tự động thu những thuộc tính page nào?
6. SPA có thể tạo URL leak qua những hook/navigation event nào?
7. sendBeacon có tự lọc URL không?
8. Referrer-Policy điều khiển thông tin gì?
9. strict-origin-when-cross-origin xử lý referrer same-origin và cross-origin ra sao?
10. Vì sao no-referrer không ngăn script đọc location.href?
11. Những hệ thống nào có thể log query string?
12. Vì sao token reset password không nên tồn tại lâu trong URL?
13. OAuth authorization code cần được bảo vệ như thế nào?
14. replaceState có giới hạn gì khi cleanup URL?
15. Vì sao route allowlist tốt hơn gửi URL đầy đủ?
16. Tại sao analytics cần kiểm soát cả client SDK và server collector?
17. CSP và SRI giúp giảm rủi ro nào, và không giải quyết rủi ro nào?
18. Những bước nào cần kiểm tra trong lab để chứng minh URL đã được lọc?

**Đáp án định hướng:** (1) Scheme, host, port, path, query và fragment; fragment không gửi trong request HTTP thông thường. (2) Path được gửi tới server và thường có trong log. (3) Query gửi tới server; fragment giữ phía client nhưng JavaScript có thể đọc. (4) Vì location.href/location.hash truy cập được trong page. (5) Page location, title, referrer và navigation event tùy SDK. (6) pushState, replaceState, popstate và router hook. (7) Không; payload do ứng dụng tạo. (8) Header Referer được gửi tới request đích. (9) Full URL same-origin, chỉ origin cross-origin và bỏ khi downgrade. (10) Nó không hạn chế JavaScript trong page. (11) CDN, proxy, server, WAF, APM, error monitoring và analytics. (12) URL có thể vào history, logs, referrer và third-party scripts. (13) Dùng code ngắn hạn, một lần, PKCE, xác minh state và exchange đúng flow. (14) Không xóa request/log/event đã phát sinh trước cleanup. (15) Route name tránh gửi ID, query và fragment không cần thiết. (16) Client có thể tự gửi dữ liệu; server/infrastructure đã nhận URL trước khi client lọc. (17) CSP giới hạn nguồn; SRI kiểm tra integrity; không tự redact dữ liệu. (18) So sánh request thô và safe payload, kiểm tra collector logs, Referer và app request query.

## 15. Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, Referer](https://www.rfc-editor.org/rfc/rfc9110#section-10.1.3): Ý nghĩa và quy tắc header Referer.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy): Các policy và cách cấu hình.
- [MDN — Referer header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referer): Thông tin referrer trong HTTP request.
- [MDN — URL API](https://developer.mozilla.org/en-US/docs/Web/API/URL): Parse và thao tác URL an toàn.
- [MDN — URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams): Đọc và sửa query parameter.
- [MDN — History.replaceState()](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState): Cập nhật URL/history mà không tải lại document.
- [MDN — Navigator.sendBeacon()](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon): Gửi dữ liệu nhỏ khi navigation/page lifecycle thay đổi.
- [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url): Rủi ro dữ liệu nhạy cảm trong query string.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): Quản lý log, dữ liệu nhạy cảm và retention.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): Khuyến nghị bảo vệ OAuth flow và authorization code.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP): Giới hạn nguồn script và kết nối.
- [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity): Kiểm tra tính toàn vẹn của script/style bên ngoài.

**Kết nối với mô hình bảo mật web:** URL có thể đi vào analytics qua page-view tự động, SPA navigation, beacon, referrer và log ở nhiều tầng. Query và path được gửi tới server; fragment không được gửi trong HTTP request thông thường nhưng JavaScript vẫn có thể đọc và chuyển tiếp. Referrer-Policy chỉ giới hạn header Referer, còn CSP chỉ giới hạn nguồn tài nguyên. Hãy ưu tiên route/field allowlist, không đặt secret trong URL, redact log tại edge và backend, kiểm tra SDK thực tế và làm sạch callback URL sau khi xử lý đúng flow.
