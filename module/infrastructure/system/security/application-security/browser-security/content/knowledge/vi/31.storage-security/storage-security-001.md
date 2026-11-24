# Storage của same-origin

> **Chương:** Storage security  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Browser cung cấp nhiều cơ chế lưu trạng thái phía client: `localStorage`, `sessionStorage`, IndexedDB, Cache Storage, cookie và các kênh giao tiếp như BroadcastChannel. Các cơ chế này có phạm vi chia sẻ khác nhau. Một trang ở origin khác không thể tùy ý đọc dữ liệu `localStorage` của ứng dụng, nhưng ranh giới thực tế còn phụ thuộc loại storage, browsing context và chính sách partitioning của browser.

Điểm cần phân biệt là **origin**, **site** và **storage key**. Origin xác định ranh giới truy cập same-origin truyền thống; site được dùng trong các quyết định như SameSite và một số cơ chế chống theo dõi; storage key có thể bao gồm origin cùng top-level site để tách trạng thái của cùng một origin khi nó được nhúng dưới các website khác nhau. Vì vậy, hai tài liệu cùng origin chưa chắc luôn dùng chung một bucket storage trong mọi ngữ cảnh nhúng của browser hiện đại.

Bài học này tập trung vào phạm vi lưu trữ, sự khác nhau giữa same-origin và same-site, cách browser partition third-party state và cách kiểm thử các ranh giới đó. Các kết quả partitioning có thể khác nhau theo browser, phiên bản, chế độ riêng tư và quyền người dùng; cần đo trên browser mục tiêu thay vì giả định một hành vi đồng nhất.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích origin tuple và phân biệt origin với site.
2. Mô tả phạm vi của `localStorage`, `sessionStorage`, IndexedDB và Cache Storage.
3. Phân biệt storage của web origin với cookie scope.
4. Giải thích vì sao third-party storage có thể được partition theo top-level site.
5. Nhận diện khác biệt giữa partitioning, blocking và Storage Access API.
6. Kiểm thử storage giữa tab, iframe same-origin, iframe cross-origin và top-level site khác nhau.
7. Hiểu giới hạn của BroadcastChannel, worker và service worker trong ngữ cảnh partitioned storage.
8. Đánh giá rủi ro XSS khi lưu token hoặc dữ liệu nhạy cảm trong browser storage.
9. Phân biệt storage partitioning với cross-origin isolation (COOP/COEP).
10. Xây checklist và bộ kiểm thử bảo mật cho browser storage.

## 2. Ba khái niệm cần phân biệt: origin, site và storage key

**Origin** truyền thống là bộ ba scheme, host và port:

```text
scheme + host + port
```

Ví dụ, các URL sau không cùng origin:

| URL | Lý do |
| --- | --- |
| `https://app.example.test` | Origin cơ sở |
| `http://app.example.test` | Scheme khác |
| `https://app.example.test:8443` | Port khác |
| `https://widget.example.test` | Host khác |
| `https://other.test` | Site khác |

**Site** thường được hiểu theo schemeful site: scheme cộng với registrable domain (eTLD+1), theo Public Suffix List. Vì vậy `https://app.example.test` và `https://widget.example.test` là hai origin khác nhau nhưng có thể là cùng site; `http://app.example.test` và `https://app.example.test` khác schemeful site.

**Storage key** là khái niệm browser dùng để xác định bucket trạng thái được chia sẻ. Ngoài origin, browser có thể đưa top-level site hoặc thông tin ngữ cảnh khác vào key. Chi tiết chính xác là vấn đề của chuẩn và triển khai browser; ứng dụng không nên giả định storage key luôn chỉ gồm origin.

## 3. Same-origin không đồng nghĩa same-site

Hai trang same-origin có cùng scheme, host và port. Chúng thường được phép truy cập cùng vùng `localStorage` và IndexedDB nếu nằm trong cùng storage partition.

Hai trang same-site có thể khác subdomain hoặc port, nên vẫn cross-origin. Ví dụ:

- `https://app.example.test` và `https://widget.example.test`: khác origin, thường cùng site.
- `https://app.example.test` và `https://app.example.test:8443`: khác origin; schemeful site có thể vẫn cùng site vì port không thuộc định nghĩa site.
- `https://app.example.test` và `https://other.test`: khác origin và khác site.

SOP dùng origin để giới hạn truy cập DOM và nhiều API. SameSite cookie dùng khái niệm site. Storage partitioning có thể dùng top-level site cùng origin để tách trạng thái. Không dùng từ “same-site” để kết luận hai trang được đọc cùng `localStorage`.

## 4. Phạm vi của localStorage

`localStorage` lưu cặp key/value dạng chuỗi và tồn tại qua các lần đóng/mở tab, tùy chính sách lưu trữ và người dùng. Theo mô hình truyền thống, nó được gắn với origin:

- Cùng scheme, host và port có thể truy cập cùng storage area.
- Khác scheme, host hoặc port có storage area khác.
- Các tab cùng origin thường nhìn thấy thay đổi của nhau.
- Iframe cùng origin có thể dùng storage area của origin đó nếu browser cho phép truy cập trong partition hiện tại.

Ví dụ:

```js
localStorage.setItem("theme", "dark");
const theme = localStorage.getItem("theme");
console.log(theme);
```

`localStorage` là API đồng bộ. Không lưu dữ liệu lớn hoặc thực hiện nhiều thao tác nặng trong luồng UI vì có thể làm chậm trang. Trong browser có storage partitioning, localStorage của một origin khi được nhúng bên thứ ba có thể nằm trong partition khác với localStorage khi origin đó là top-level. Một số chế độ còn có thể chặn hoặc hạn chế third-party storage.

## 5. Phạm vi của sessionStorage

`sessionStorage` được phân vùng theo origin và top-level browsing context (thường tương ứng page session/tab). Các tài liệu cùng origin trong cùng tab, bao gồm iframe same-origin, có thể dùng chung vùng session storage của page session đó. Tab khác thường có vùng riêng.

```js
sessionStorage.setItem("checkout-step", "shipping");
console.log(sessionStorage.getItem("checkout-step"));
```

Khi mở cửa sổ mới có quan hệ opener, browser có thể khởi tạo sessionStorage của cửa sổ mới bằng một bản sao trạng thái từ cửa sổ mở nó. Sau khi tạo, hai page session độc lập; thay đổi ở cửa sổ này không tự đồng bộ sang cửa sổ kia.

Không dùng sessionStorage như một kho bí mật. JavaScript cùng origin có thể đọc dữ liệu, và XSS trong origin có thể lấy dữ liệu đó. “Session” ở tên API nói về vòng đời page session, không có nghĩa dữ liệu được bảo vệ như session cookie HttpOnly.

## 6. IndexedDB

IndexedDB là cơ sở dữ liệu bất đồng bộ phía client, phù hợp với dữ liệu có cấu trúc, chỉ mục và dung lượng lớn hơn localStorage. Database được gắn với storage key của context; theo mô hình truyền thống, phạm vi cơ bản là origin, còn partitioning hiện đại có thể tách dữ liệu third-party theo top-level site.

Ví dụ mở database:

```js
const request = indexedDB.open("app-data", 1);

request.onupgradeneeded = () => {
  const db = request.result;
  if (!db.objectStoreNames.contains("settings")) {
    db.createObjectStore("settings", { keyPath: "key" });
  }
};

request.onsuccess = () => {
  const db = request.result;
  const tx = db.transaction("settings", "readwrite");
  tx.objectStore("settings").put({ key: "theme", value: "dark" });
};
```

IndexedDB không phải vùng lưu trữ an toàn trước XSS. Script chạy trong origin có thể truy cập database theo quyền của context. Không lưu refresh token, private key không được bảo vệ hoặc dữ liệu nhạy cảm dài hạn chỉ vì IndexedDB có cấu trúc và API phức tạp hơn localStorage.

## 7. Cache Storage và Service Worker

Cache Storage là API cho phép ứng dụng lưu Request/Response để phục vụ offline hoặc tối ưu tải tài nguyên. Nó khác HTTP cache do browser tự quản lý: Cache Storage được thao tác bằng JavaScript và thường gắn với storage key của context.

```js
const cache = await caches.open("app-shell-v3");
await cache.put("/offline.html", new Response("<h1>Offline</h1>", {
  headers: { "Content-Type": "text/html; charset=utf-8" }
}));
```

Service Worker có registration và scope theo origin/path, nhưng việc dùng storage và worker trong third-party context còn chịu quy tắc storage key/partitioning của browser. Không giả định một service worker đăng ký trong top-level context sẽ có cùng trạng thái khi cùng origin được nhúng dưới một top-level site khác.

Cache Storage có thể chứa response nhạy cảm. Hãy tránh cache API response chứa dữ liệu tài khoản nếu không có chiến lược cache, logout và invalidation rõ ràng. Khi đăng xuất hoặc đổi user, cần xóa cache liên quan và không dựa vào browser tự dọn dữ liệu đúng lúc.

## 8. Cookie không tuân theo origin tuple như localStorage

Cookie là trường hợp cần phân biệt riêng. Cookie được gửi theo quy tắc domain/host, path, Secure, SameSite và các thuộc tính khác; port không tạo ranh giới cookie như origin.

| Thuộc tính | Phạm vi |
| --- | --- |
| Host-only cookie (không có Domain) | Chỉ host đã đặt cookie |
| `Domain=example.test` | Có thể gửi tới domain và các subdomain phù hợp |
| `Path=/account` | Giới hạn request path phù hợp; không phải ranh giới bảo mật mạnh |
| `Secure` | Chỉ gửi qua secure transport theo quy tắc cookie |
| `HttpOnly` | Không cho JavaScript đọc cookie qua `document.cookie` |
| `SameSite` | Kiểm soát gửi cookie theo ngữ cảnh site |

Hai ứng dụng ở hai port khác nhau trên cùng host có thể vẫn nhận cùng cookie phù hợp vì cookie không được partition theo port. Ngược lại, localStorage của hai port là hai vùng origin khác nhau. Đây là một ví dụ rõ ràng cho thấy cookie scope không phải origin scope.

## 9. Cookie partitioning và CHIPS

Cookie có thể được partition theo top-level site bằng cơ chế Partitioned Cookies (CHIPS), dùng thuộc tính `Partitioned` cùng `Secure`:

```http
Set-Cookie: widget_session=opaque; Secure; HttpOnly; SameSite=None; Partitioned; Path=/
```

Cookie partitioned được lưu theo ngữ cảnh top-level site bên cạnh thông tin cookie thông thường. Cùng một widget origin khi được nhúng dưới hai top-level site khác nhau có thể nhận hai partition cookie riêng. Điều này giúp widget duy trì một số trạng thái nhúng mà không chia sẻ cookie đó xuyên mọi website.

CHIPS không đồng nghĩa tất cả cookie đều tự động partition; nó là cơ chế cookie riêng với thuộc tính rõ ràng và hỗ trợ browser cần được kiểm tra. Cookie partitioned cũng không thay thế xác thực, authorization hoặc CSRF protection.

## 10. Third-party storage partitioning

Khi một origin được nhúng trong website khác, browser có thể xem nó là third-party context. Để hạn chế theo dõi người dùng qua nhiều website, browser có thể partition hoặc hạn chế state của context này.

Ví dụ, `https://widget.example.net` được nhúng trong:

- `https://shop.example.org`
- `https://news.example.com`

Nếu storage được partition theo top-level site, widget có bucket riêng trong từng trang cha. Giá trị tạo khi widget được nhúng trong shop không nhất thiết xuất hiện khi widget được nhúng trong news, dù URL iframe và origin của widget giống nhau.

Các browser có thể triển khai nhiều chiến lược: partition storage, chặn third-party access, yêu cầu user interaction/permission hoặc hỗ trợ API để xin quyền truy cập state không partition. Hành vi thay đổi theo browser, phiên bản, cài đặt, chế độ riêng tư và loại storage.

## 11. Mô hình storage key có top-level site

Để hình dung partitioning, có thể dùng mô hình khái niệm:

```text
Storage key ≈ origin + top-level site (+ các thành phần context khác)
```

Đây là mô hình giải thích, không phải công thức chuẩn duy nhất cho mọi browser/API. Nó giúp lý giải hai trường hợp:

1. Origin A mở top-level: bucket có origin A và top-level site A.
2. Origin A được nhúng trong top-level site B: bucket có origin A và top-level site B.

Nếu browser partition storage, hai bucket này khác nhau. Vì vậy, iframe có thể thấy storage riêng của nó thay vì dữ liệu được ghi khi A là top-level.

Partitioning theo top-level site khác với SOP. SOP trả lời liệu script origin này có thể truy cập tài liệu origin kia hay không; partitioning quyết định context hiện tại đang dùng bucket trạng thái nào.

## 12. Same-site cross-origin và cross-site iframe

Để kiểm thử partitioning, cần phân biệt:

| Top-level page | Embedded frame | Quan hệ |
| --- | --- | --- |
| `https://app.example.test` | `https://widget.example.test` | Cross-origin, thường same-site |
| `https://app.example.test` | `https://widget.other.test` | Cross-origin, cross-site |
| `https://app.example.test` | `http://app.example.test` | Khác origin và khác schemeful site |

Hai subdomain cùng registrable domain và cùng scheme thường là same-site, nhưng vẫn cross-origin. Một browser có thể partition third-party state theo top-level site, nên iframe same-site có thể được xử lý khác iframe cross-site. Không dùng thử nghiệm chỉ với hai port khác nhau để kết luận về third-party partitioning: khác port tạo cross-origin nhưng không tạo một top-level site khác.

## 13. BroadcastChannel và các kênh giao tiếp

BroadcastChannel cho phép các context đủ điều kiện giao tiếp theo tên channel mà không cần giữ tham chiếu trực tiếp tới nhau:

```js
const channel = new BroadcastChannel("app-events");
channel.postMessage({ type: "THEME_CHANGED", theme: "dark" });

channel.addEventListener("message", (event) => {
  console.log("Received:", event.data);
});
```

Việc tham gia channel bị giới hạn theo origin và trong browser có partitioning còn có thể bị giới hạn theo storage key. Vì vậy, hai context cùng origin nhưng được mở trong top-level site khác nhau không nhất thiết nhìn thấy cùng channel trong mọi browser.

Không xem BroadcastChannel là một bus bảo mật. Bất kỳ context nào đủ điều kiện cùng phạm vi có thể gửi message; luôn validate schema và không truyền token hoặc bí mật. Với giao tiếp parent/iframe cross-origin, dùng postMessage với kiểm tra origin/source và schema thay vì giả định BroadcastChannel vượt qua SOP.

## 14. Storage Access API

Một số dịch vụ nhúng cần truy cập cookie hoặc state first-party của chính mình khi chạy trong third-party context, ví dụ widget đăng nhập hoặc hệ thống bình luận. Storage Access API cung cấp cơ chế để frame yêu cầu quyền truy cập state không partition trong những điều kiện do browser quy định.

Ví dụ minh họa:

```js
async function requestUnpartitionedAccess() {
  if (!document.hasStorageAccess || !document.requestStorageAccess) {
    return { supported: false };
  }

  if (await document.hasStorageAccess()) {
    return { supported: true, granted: true };
  }

  try {
    await document.requestStorageAccess();
    return { supported: true, granted: true };
  } catch (error) {
    return { supported: true, granted: false, error: error.name };
  }
}
```

Trong thực tế, browser có thể yêu cầu user activation, tương tác trước đó với site ở top-level, permission hoặc điều kiện khác. Hãy gọi API sau hành động rõ ràng của người dùng và xử lý trường hợp bị từ chối. API không bảo đảm mọi browser sẽ cấp quyền, cũng không phải cách bỏ qua chính sách privacy.

Không yêu cầu Storage Access chỉ để tránh thiết kế partition-aware. Nếu widget có thể hoạt động với state partitioned, đó thường là lựa chọn ít phụ thuộc quyền riêng tư hơn.

## 15. Storage partitioning không phải CORS

CORS quyết định JavaScript cross-origin có được đọc response hay không. Storage partitioning quyết định context đang dùng bucket lưu trữ nào hoặc có được truy cập state bên thứ ba hay không.

| Cơ chế | Câu hỏi |
| --- | --- |
| SOP | Script có được truy cập DOM/dữ liệu của origin khác không? |
| CORS | Server có cho origin khác đọc response không? |
| SameSite | Cookie có được gửi trong ngữ cảnh site này không? |
| Storage partitioning | Context này đang dùng partition state nào? |
| Storage Access API | Frame có thể xin quyền truy cập một số state không partition không? |

Thêm `Access-Control-Allow-Origin: *` không làm localStorage của iframe được chia sẻ với top-level context. Ngược lại, việc hai context dùng chung một storage bucket cũng không tự cấp quyền đọc response API cross-origin.

## 16. Rủi ro bảo mật khi lưu dữ liệu phía client

Các API storage không phải secret vault. Script chạy trong origin có thể đọc dữ liệu mà origin đó được phép truy cập. Nếu ứng dụng có DOM XSS, attacker có thể đọc localStorage, sessionStorage và IndexedDB, rồi gửi dữ liệu ra ngoài.

Nguyên tắc:

- Không lưu access token/refresh token dài hạn trong localStorage nếu có thể dùng session cookie an toàn hơn.
- Cookie xác thực nên cân nhắc `Secure`, `HttpOnly`, `SameSite`, scope host-only và thời hạn phù hợp.
- Không lưu password, private key hoặc dữ liệu nhạy cảm chỉ vì storage có quota lớn.
- Xem dữ liệu trong IndexedDB/Cache Storage là dữ liệu mà script cùng origin có thể truy cập.
- Không tin dữ liệu storage khi đọc lại; validate schema và kiểm tra quyền ở server.
- Xóa dữ liệu liên quan khi logout, đổi tài khoản hoặc thu hồi session.

Mã hóa dữ liệu trong localStorage/IndexedDB bằng key mà JavaScript cùng origin có thể lấy được không bảo vệ dữ liệu trước XSS đang chạy trong origin đó. Encryption at rest có thể giúp trong một số threat model, nhưng không thay thế việc ngăn script độc hại truy cập runtime.

## 17. Dữ liệu lưu trữ có thể bị xóa hoặc giới hạn

Browser có thể giới hạn quota, evict dữ liệu khi thiếu dung lượng, xóa storage khi người dùng clear site data hoặc áp dụng chính sách riêng tư. Private browsing có thể có vòng đời và giới hạn khác. Không giả định dữ liệu client-side tồn tại vĩnh viễn hoặc luôn được ghi thành công.

Có thể kiểm tra dung lượng gần đúng:

```js
if (navigator.storage?.estimate) {
  const { usage, quota } = await navigator.storage.estimate();
  console.log({ usage, quota });
}
```

Ứng dụng nên xử lý quota error, transaction abort, dữ liệu thiếu và khả năng phải đồng bộ lại từ server. Storage client-side nên được xem là cache hoặc trạng thái tiện ích khi dữ liệu có thể khôi phục; dữ liệu nghiệp vụ quan trọng cần nguồn chuẩn ở server.

## 18. Cross-origin isolation không thay đổi storage boundary

Cross-origin isolation thường được thiết lập bằng COOP và COEP trong secure context để cô lập browsing context và cho phép một số capability như SharedArrayBuffer. Trạng thái có thể kiểm tra bằng:

```js
console.log({
  isolated: self.crossOriginIsolated,
  sharedArrayBuffer: typeof SharedArrayBuffer
});
```

`crossOriginIsolated === true` không làm SOP biến mất, không cho phép đọc localStorage của origin khác và không biến mọi storage partition thành một bucket chung. Nó cũng không tự tắt third-party storage partitioning.

Khi kiểm thử storage, hãy kiểm tra origin/partition độc lập với COOP/COEP. Có thể bật cross-origin isolation rồi lặp lại bài test; ranh giới storage vẫn phải tuân theo origin và storage partition mà browser áp dụng.

## 19. Kiểm tra storage trong DevTools

DevTools thường có mục Application hoặc Storage để quan sát:

- Local Storage theo origin.
- Session Storage theo tab/context.
- IndexedDB database và object store.
- Cache Storage entries.
- Cookies theo host/domain/path/partition key nếu browser hiển thị.
- Service Worker registration và cache liên quan.

Khi debug iframe, hãy chọn đúng frame execution context trong Console. Console của top-level page và Console của iframe có thể truy cập các storage area khác nhau. Ghi nhận URL, origin, top-level site, browser/version, chế độ riêng tư và trạng thái permission.

Không chỉ dựa vào giao diện DevTools để kết luận partitioning: một số browser hiển thị partition key hoặc third-party state không giống nhau. Hãy kết hợp quan sát DevTools với test JavaScript chạy trong từng context.

## 20. Lab A — Kiểm tra origin scoping

Chạy hai trang lab cùng hostname nhưng khác port, ví dụ:

- `http://localhost:8000`
- `http://localhost:8001`

Trên trang thứ nhất:

```js
localStorage.setItem("origin-probe", "from-port-8000");
console.log(localStorage.getItem("origin-probe"));
```

Trên trang thứ hai:

```js
console.log(localStorage.getItem("origin-probe"));
```

**Kỳ vọng:** Hai port là hai origin khác nhau nên localStorage không chia sẻ. Lặp lại với IndexedDB database cùng tên và quan sát mỗi origin có database riêng. Đổi scheme hoặc hostname cũng tạo origin khác.

## 21. Lab B — Same-origin iframe và sessionStorage

Tạo parent và child cùng origin, nhúng child bằng iframe. Từ parent ghi một key vào localStorage và sessionStorage; từ child đọc lại:

```js
// Parent
localStorage.setItem("frame-probe", "shared-origin");
sessionStorage.setItem("tab-probe", "same-page-session");
const frame = document.querySelector("#same-origin-frame");
frame.contentWindow.postMessage({ type: "READ_PROBE" }, location.origin);
```

Trong child, đọc hai key và gửi kết quả về parent bằng postMessage có targetOrigin chính xác. Sau đó mở cùng URL ở tab mới và so sánh sessionStorage.

**Kỳ vọng:** Same-origin frame trong cùng page session có thể dùng chung vùng localStorage và sessionStorage tương ứng. Tab mới có sessionStorage riêng; nếu được mở với opener, browser có thể khởi tạo bản sao ban đầu.

## 22. Lab C — Third-party storage partitioning

Chuẩn bị hai site lab khác nhau, ví dụ:

- Top-level A: `https://site-a.test`
- Top-level B: `https://site-b.test`
- Widget: `https://widget.test`

1. Mở widget.test trực tiếp ở top-level và ghi `localStorage.setItem("partition-probe", "top-level-A")`.
2. Mở site-b.test có iframe trỏ tới widget.test.
3. Trong iframe, đọc `partition-probe` và ghi một giá trị khác.
4. Mở lại widget.test ở top-level và kiểm tra giá trị top-level.
5. Lặp lại khi widget được nhúng dưới site-a.test và site-b.test.

**Kỳ vọng:** Browser có partitioning có thể cho iframe bucket riêng theo top-level site, hoặc chặn third-party storage. Một số môi trường/cấu hình có thể cho kết quả khác. Ghi rõ browser/version và phân biệt “bucket rỗng”, “partition riêng” với “API bị chặn”.

## 23. Lab D — Same-site cross-origin so với cross-site

Tạo `https://app.example.test` và `https://widget.example.test` cùng scheme/registrable domain; sau đó tạo một top-level site khác như `https://host.other.test`. Dùng cùng widget origin trong iframe dưới từng parent và đọc marker.

**Kỳ vọng:** App và widget là cross-origin nhưng thường same-site. Widget nhúng dưới other.test là third-party cross-site. So sánh kết quả để thấy origin boundary và top-level-site partitioning là hai trục khác nhau. Không dùng hai port khác nhau làm phép thử site partitioning.

## 24. Lab E — Cookie scope và Partitioned cookie

Trên widget server, thử hai cookie:

```http
Set-Cookie: host_session=one; Secure; HttpOnly; SameSite=None; Path=/
Set-Cookie: partition_session=two; Secure; HttpOnly; SameSite=None; Partitioned; Path=/
```

Nhúng widget dưới hai top-level site lab khác nhau. Kiểm tra cookie trong request tới widget server và quan sát DevTools.

**Kỳ vọng:** Cookie thường có thể bị chặn hoặc xử lý theo third-party cookie policy; cookie có Partitioned được thiết kế để tách theo top-level site trong browser hỗ trợ. Kết quả phụ thuộc browser và cài đặt. Không dùng cookie thật hoặc tài khoản thật trong lab.

## 25. Lab F — Cross-origin isolation không mở storage

Tạo hai origin lab và cấu hình response của một trang với:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Trong Console kiểm tra:

```js
console.log(self.crossOriginIsolated);
console.log(typeof SharedArrayBuffer);
console.log(localStorage.getItem("origin-probe"));
```

Lặp lại bài kiểm tra storage ở origin khác và iframe. **Kỳ vọng:** crossOriginIsolated có thể là true nếu toàn bộ điều kiện đáp ứng, nhưng nó không cấp quyền đọc storage cross-origin và không gộp các partition. Nếu false, kiểm tra secure context, COOP/COEP và tài nguyên bị chặn.

## 26. Storage Access API và trạng thái bị chặn

Trong lab third-party, kiểm tra hỗ trợ và trạng thái:

```js
const supported =
  typeof document.hasStorageAccess === "function" &&
  typeof document.requestStorageAccess === "function";

console.log({ supported });
if (supported) {
  console.log("Has access:", await document.hasStorageAccess());
}
```

Nếu thử request quyền, hãy gắn nó với một nút người dùng bấm và xử lý rejection. Không tự động gọi lặp lại trong vòng lặp hoặc khi page vừa tải. Browser có thể yêu cầu tương tác trước đó, user activation hoặc các điều kiện khác.

## 27. Các lỗi thiết kế thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng same-site nghĩa là same-origin | Subdomain/port có thể khác origin | So sánh scheme, host và port |
| Cho rằng localStorage luôn chỉ partition theo origin | Third-party context có thể được partition theo top-level site | Kiểm thử storage key trên browser mục tiêu |
| Dùng hai port để kiểm tra cross-site partitioning | Port tạo cross-origin nhưng không tạo site mới | Dùng hai registrable domain lab khác nhau |
| Cho rằng cookie tuân theo origin tuple | Cookie không partition theo port và có Domain/Path rules | Review cookie scope riêng |
| Lưu refresh token trong localStorage | XSS cùng origin có thể đọc token | Ưu tiên cookie HttpOnly/Secure phù hợp và thiết kế session an toàn |
| Xem IndexedDB là kho bí mật | Script cùng origin có thể truy cập database | Không lưu secret chỉ vì storage có cấu trúc |
| Dựa vào third-party cookie blocking làm kiểm soát truy cập | Browser policy thay đổi và không phải authorization | Xác thực/phân quyền ở server |
| Gọi Storage Access API tự động | Có thể bị browser từ chối và gây trải nghiệm xấu | Chỉ yêu cầu theo hành động có ý nghĩa của người dùng |
| Cho rằng crossOriginIsolated mở quyền storage | COOP/COEP không thay SOP/storage key | Kiểm tra isolation và storage như hai vấn đề riêng |
| Cache response nhạy cảm không có invalidation | Dữ liệu cũ có thể tồn tại sau logout/đổi user | Thiết kế cache lifecycle và xóa dữ liệu có chủ đích |

## 28. Checklist review browser storage

- [ ] Đã phân biệt origin, site và storage key trong thiết kế.
- [ ] Đã ghi rõ dữ liệu nào được lưu ở localStorage, sessionStorage, IndexedDB, Cache Storage và cookie.
- [ ] Không giả định hai context cùng origin luôn chia sẻ một bucket khi một context là third-party iframe.
- [ ] Đã kiểm tra localStorage và IndexedDB ở top-level và third-party context.
- [ ] Đã kiểm tra sessionStorage theo tab/page session và hành vi opener.
- [ ] Đã phân biệt same-site cross-origin với cross-site.
- [ ] Đã review cookie host-only, Domain, Path, Secure, HttpOnly và SameSite.
- [ ] Cookie partitioned chỉ dùng khi hiểu rõ top-level-site partition và browser support.
- [ ] Đã đánh giá BroadcastChannel/worker/service worker trong storage partition hiện hành.
- [ ] Storage Access API chỉ được dùng khi có nhu cầu, user interaction và fallback phù hợp.
- [ ] Không lưu credential dài hạn hoặc secret trong storage JavaScript-accessible.
- [ ] Có xử lý quota, eviction, transaction failure và private browsing.
- [ ] Cache chứa dữ liệu tài khoản có expiry, invalidation và logout cleanup.
- [ ] Cross-origin isolation được đánh giá riêng với storage partitioning.
- [ ] Có test trên browser/version và chế độ privacy mà sản phẩm hỗ trợ.
- [ ] Kết quả test ghi rõ top-level site, origin, frame tree và quyền người dùng.

## 29. Câu hỏi tự kiểm tra

1. Origin được tạo từ những thành phần nào?
2. Same-site khác same-origin ra sao?
3. localStorage khác sessionStorage về phạm vi và vòng đời thế nào?
4. IndexedDB và Cache Storage chịu tác động của storage key ra sao?
5. Vì sao cookie không phải một storage API theo origin tuple?
6. Third-party storage partitioning thay đổi điều gì khi cùng widget được nhúng dưới hai site?
7. Partitioning khác blocking như thế nào?
8. Storage Access API giải quyết nhu cầu gì và vì sao không phải lúc nào cũng được cấp?
9. Vì sao XSS có thể đọc localStorage và IndexedDB?
10. crossOriginIsolated có làm thay đổi quyền truy cập storage cross-origin không?
11. Vì sao cần dùng hai site khác registrable domain khi kiểm tra site partitioning?
12. Cần ghi nhận những thông tin nào để một bài kiểm thử storage có thể tái lập?

## 30. Ghi nhớ

Storage phía browser có nhiều phạm vi khác nhau. localStorage và IndexedDB truyền thống gắn với origin; sessionStorage còn gắn với page session/tab; Cache Storage và các API liên quan có thể chịu storage key của browser. Cookie dùng quy tắc host/domain/path và SameSite, không phải origin tuple. Trong third-party context, browser hiện đại có thể partition hoặc chặn state theo top-level site.

Hãy phân biệt same-origin với same-site, kiểm thử bằng các origin/site lab phù hợp và ghi rõ browser/version. Không lưu secret trong storage mà JavaScript cùng origin có thể đọc; thiết kế logout, cache invalidation và fallback cho storage bị chặn. **Cross-origin isolation không mở quyền storage cross-origin: SOP, storage partitioning, cookie policy và COOP/COEP giải quyết các ranh giới khác nhau.**
