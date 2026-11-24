# First-party context: hiểu ngữ cảnh bên thứ nhất trong trình duyệt

**Chương:** Privacy  
**Mô-đun:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**First-party context** mô tả tình huống một website được truy cập trực tiếp ở vị trí website chính trong tab hoặc cửa sổ trình duyệt. Khi cùng website đó được nhúng trong trang của website khác, nó hoạt động trong third-party context. Trình duyệt dùng ngữ cảnh này để áp dụng một số quy tắc về cookie, storage, tracking prevention và quyền truy cập dữ liệu.

Khái niệm first-party không đồng nghĩa với same-origin. Hai subdomain có thể khác origin nhưng vẫn cùng site; một tài nguyên có thể cùng origin với một iframe nhưng iframe đó lại đang chạy trong third-party context vì top-level site là website khác. Đây là khác biệt quan trọng khi thiết kế session, đăng nhập nhúng, analytics, widget và các luồng xác thực.

First-party context cũng không phải nhãn chứng nhận một website an toàn hoặc riêng tư. Website được mở trực tiếp vẫn có thể theo dõi người dùng, thu thập quá mức, bị XSS hoặc làm lộ dữ liệu. Mục tiêu của bài học là hiểu browser phân loại ngữ cảnh thế nào, dữ liệu nào được chia sẻ giữa các ngữ cảnh, và cách thiết kế cookie/storage để giảm tracking ngoài ý muốn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt origin, site, top-level site, first-party context và third-party context.
2. Giải thích schemeful same-site và vì sao same-site không đồng nghĩa same-origin.
3. Phân tích cookie theo host, Domain, Path, Secure, HttpOnly, SameSite và Partitioned.
4. Phân biệt first-party cookie, third-party cookie và partitioned cookie (CHIPS).
5. Mô tả cách browser phân vùng storage theo top-level site và giới hạn của cơ chế này.
6. Hiểu vai trò của Storage Access API khi nội dung nhúng cần truy cập state không phân vùng.
7. Nhận diện tracking qua cookie, storage, URL decoration, redirect/bounce và fingerprinting.
8. Thiết kế session, embedded widget, analytics và đăng nhập theo nguyên tắc data minimization.
9. Kết hợp SOP, CORS, CSRF, CSP, Permissions Policy và Referrer Policy để bảo vệ ngữ cảnh nhúng.
10. Kiểm chứng hành vi cookie/storage trong browser bằng lab localhost và test matrix.

## 2. Các khái niệm cần tách biệt

### 2.1. Origin là bộ ba scheme, host và port

Origin được xác định bởi scheme, host và port. Ví dụ:

| URL | Origin | Quan hệ |
| --- | --- | --- |
| `https://shop.example.test` | `https://shop.example.test:443` (default port) | Origin A |
| `https://shop.example.test/account` | `https://shop.example.test:443` | Cùng origin A |
| `https://shop.example.test:8443` | `https://shop.example.test:8443` | Khác origin do port |
| `http://shop.example.test` | `http://shop.example.test:80` | Khác origin do scheme |
| `https://api.example.test` | `https://api.example.test:443` | Khác origin do host |

SOP dùng origin để giới hạn script truy cập DOM, storage và response của origin khác. CORS có thể cho phép JavaScript đọc một số HTTP response cross-origin; `postMessage` là API giao tiếp tường minh giữa browsing context và vẫn cần kiểm tra origin/source cùng schema message.

### 2.2. Site và schemeful same-site

Trong ngữ cảnh cookie và nhiều cơ chế privacy, browser còn xét **site**. Với hostname thông thường, site thường được xác định từ scheme và registrable domain (thường là eTLD+1 theo Public Suffix List). Port không tham gia vào site calculation.

Ví dụ với `https://example.test`:

- `https://shop.example.test` và `https://id.example.test` là cross-origin nhưng thường same-site.
- `https://example.test:8443` khác origin do port nhưng vẫn same-site.
- `http://shop.example.test` và `https://id.example.test` là khác schemeful site vì scheme khác.
- `https://other.test` là cross-site.

Đây là cách giải thích thực hành. Hostname đặc biệt như localhost, IP literal và public suffix có quy tắc riêng; không tự tính eTLD+1 bằng cách lấy hai nhãn cuối của hostname. Các browser cũng có thể áp dụng chi tiết policy khác nhau cho một số API.

### 2.3. Top-level site và browsing context

**Top-level site** là site của trang điều hướng chính đang được hiển thị trong tab. Một iframe hoặc subresource được xét trong quan hệ với top-level site này.

Ví dụ:

```text
Top-level page: https://news.example.test
  ├── script: https://news.example.test/app.js
  ├── iframe: https://login.identity.test/widget
  └── image: https://metrics.vendor.test/pixel

Top-level page: https://identity.test
  └── document: https://identity.test
```

Khi người dùng mở `identity.test` trực tiếp, identity site đang ở first-party context. Khi `identity.test` được nhúng bên trong `news.example.test`, nó là third-party context đối với top-level site đó. Một trang có thể chứa nhiều tài nguyên từ nhiều site; mỗi tài nguyên không tự trở thành first-party chỉ vì nó được tải bởi một website đáng tin.

### 2.4. First-party context không phải first-party data

Hai khái niệm thường bị trộn lẫn:

- **First-party context:** cách browser phân loại một site khi site đó là trang chính hoặc được truy cập trong ngữ cảnh cùng site.
- **First-party data:** dữ liệu tổ chức thu trực tiếp từ tương tác của người dùng với dịch vụ của mình, theo định nghĩa và chính sách sản phẩm.
- **Third-party context/data:** ngữ cảnh hoặc dữ liệu liên quan đến một site/bên khác trong quá trình nhúng, quảng cáo, analytics hay tích hợp.

Dữ liệu do chính website thu thập trong first-party context vẫn có thể nhạy cảm và cần mục đích, giới hạn truy cập, thời hạn lưu trữ và thông báo minh bạch. Browser không đánh giá tính hợp pháp hoặc đạo đức của hoạt động tracking chỉ dựa trên ngữ cảnh.

## 3. Phân biệt first-party và third-party context

### 3.1. Truy cập trực tiếp và nội dung được nhúng

Một site là first party khi người dùng điều hướng trực tiếp tới site đó và nó trở thành top-level site. Khi cùng site xuất hiện trong iframe, image, script hoặc request của một top-level site khác, nó có thể được xử lý trong third-party context.

Ví dụ:

| Hành động | Ngữ cảnh của `identity.test` |
| --- | --- |
| Người dùng mở `https://identity.test/login` trong tab | First-party |
| `shop.test` nhúng `https://identity.test/widget` trong iframe | Third-party |
| `shop.test` tải ảnh từ `identity.test` | Request third-party |
| `identity.test` chuyển hướng top-level tới `shop.test` | Sau điều hướng, `shop.test` là top-level site |

Điều hướng top-level tới một site khác làm thay đổi top-level site. Browser có thể xử lý cookie trong top-level navigation khác với cookie trong iframe/subresource request.

### 3.2. Same-site request không luôn là first-party context

`https://shop.example.test` và `https://id.example.test` thường là same-site nhưng khác origin. Một iframe từ `id.example.test` được nhúng trong `shop.example.test` vẫn có thể được coi là same-site theo cookie SameSite, nhưng SOP vẫn xem hai origin là khác nhau. Ngược lại, một iframe `https://identity.other.test` là cross-site với trang chính.

Do đó, khi debug một request, hãy hỏi riêng:

1. Hai URL có same-origin không?
2. Hai URL có same-site theo schemeful site không?
3. Resource đang là top-level document hay embedded subresource?
4. Cookie được gửi theo SameSite, partitioning và browser policy nào?
5. Storage đang được truy cập theo origin nào và top-level site nào?

Không dùng một câu trả lời “same-site” để suy ra CORS, DOM access, cookie scope và storage access đều giống nhau.

### 3.3. Redirect và bounce tracking

Một số hệ thống tracking điều hướng người dùng qua domain trung gian rồi quay lại trang đích. Domain trung gian có thể cố tạo hoặc đọc state trong thời gian nó trở thành top-level site, rồi liên kết thông tin qua URL parameter hoặc redirect chain. Đây thường được gọi là bounce tracking.

Browser có thể áp dụng tracking prevention, xóa hoặc giới hạn state của domain bị đánh giá có hành vi bounce. Cách xử lý phụ thuộc browser và phiên bản; ứng dụng không nên dựa vào redirect trung gian để duy trì định danh người dùng giữa các website.

Thiết kế an toàn: dùng redirect có mục đích rõ ràng, allowlist callback URI chính xác, loại bỏ parameter không cần thiết, không đưa token dài hạn vào URL và không tạo redirect chain qua nhiều tracker.

### 3.4. Ancestor chain trong iframe lồng nhau

Không chỉ frame trực tiếp mới ảnh hưởng ngữ cảnh. Với iframe lồng nhau, browser có thể xét chuỗi ancestor khi xác định site-for-cookies và một số quyền truy cập state. Ví dụ `widget.example.test` nằm trong iframe của `portal.example.test`, nhưng iframe đó lại được nhúng bên trong `host.other.test`; toàn bộ cây browsing context có thể khiến request được xem là cross-site. Đừng suy luận SameSite chỉ từ URL của iframe con và top-level URL mà bỏ qua ancestor ở giữa.

Khi debug, ghi lại toàn bộ chuỗi top-level document → iframe cha → iframe con, cùng scheme/site của từng node. Test cả nested iframe và top-level direct navigation; policy của ancestor, sandbox và Permissions Policy cũng có thể giới hạn quyền của frame con.

## 4. Cookie trong first-party và third-party context

### 4.1. Cookie được gửi theo domain, path và context

Cookie không được phân vùng theo port như origin. Cookie được chọn dựa trên domain/host, path, Secure, expiry và các quy tắc SameSite; browser còn áp dụng chính sách third-party cookie riêng. Vì vậy, hai ứng dụng khác port trên cùng host có thể chia sẻ cookie nếu domain/path phù hợp, dù chúng là hai origin khác nhau.

Nếu không khai báo thuộc tính `Domain`, cookie là host-only cookie và chỉ được gửi tới host đã tạo nó. Nếu khai báo `Domain=example.test`, cookie có thể được gửi tới các subdomain phù hợp. Thuộc tính `Path` giới hạn request path nhưng không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host.

Cookie first-party thường được tạo khi người dùng đang ở site phát hành cookie. Cookie third-party có thể được tạo/đọc khi site đó được nhúng trong top-level site khác. Browser có thể chặn, partition hoặc giới hạn cookie third-party theo cài đặt và tracking prevention.

### 4.2. SameSite và schemeful site

`SameSite` quyết định cookie có được gửi trong một số request cross-site hay không:

| Giá trị | Hành vi khái quát | Dùng khi |
| --- | --- | --- |
| `Strict` | Chỉ gửi trong same-site context | Session nhạy cảm không cần theo mọi navigation từ site khác |
| `Lax` | Gửi trong same-site và một số top-level safe navigation cross-site | Lựa chọn phổ biến cho session first-party |
| `None` | Cho phép gửi trong cross-site context nếu các điều kiện khác thỏa | Tích hợp nhúng thực sự cần cookie cross-site; phải kèm `Secure` |

SameSite được xét theo site, không phải origin. Subdomain cùng scheme và registrable domain có thể là same-site dù khác origin. Các chi tiết như top-level navigation, method và redirect chain ảnh hưởng kết quả; hãy kiểm tra browser thực tế thay vì suy đoán từ URL đơn lẻ.

`SameSite` là lớp giảm CSRF, không thay thế CSRF token và authorization. Một request same-site từ subdomain bị chiếm quyền vẫn có thể mang cookie tới ứng dụng chính. Cũng không nên đặt `SameSite=None` chỉ để sửa lỗi đăng nhập nhúng nếu không có nhu cầu cross-site rõ ràng.

### 4.3. Cookie session first-party

Với session ứng dụng chính, ưu tiên cookie host-only, `Secure`, `HttpOnly`, `Path=/` và SameSite phù hợp. Prefix `__Host-` buộc cookie phải có Secure, Path=/ và không có Domain trên browser hỗ trợ prefix này.

Ví dụ response header cho session:

```http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Server cần sinh session ID ngẫu nhiên, rotate sau login hoặc privilege change, hết hạn idle/absolute, revoke khi logout và bảo vệ session store. Không đưa access token dài hạn vào URL hoặc `localStorage` chỉ để chia sẻ giữa subdomain.

Nếu sản phẩm cần callback cross-site như một số luồng SSO hoặc payment, đánh giá chính xác request method và navigation. Chỉ dùng `SameSite=None; Secure` khi cần, kết hợp state/nonce chống login CSRF và redirect URI allowlist.

### 4.4. Domain rộng làm tăng phạm vi rủi ro

Cookie có `Domain=example.test` có thể được gửi tới nhiều subdomain. Nếu một subdomain cũ, tenant host hoặc dịch vụ marketing bị chiếm quyền, cookie domain-wide có thể mở rộng tác động. Với session chính, ưu tiên host-only và prefix `__Host-`.

Cookie không bị cô lập theo port. Nếu nhiều ứng dụng không cùng mức tin cậy chạy trên cùng hostname nhưng khác port, chúng có thể xung đột cookie cùng domain/path/name. Tách hostname/origin theo ranh giới tin cậy và không dùng cookie làm cơ chế phân quyền duy nhất.

### 4.5. First-party cookie vẫn cần bảo vệ

Cookie first-party có thể bị đánh cắp hoặc lạm dụng qua XSS, session fixation, CSRF, log leak, browser extension độc hại hoặc server compromise. `HttpOnly` giảm khả năng đọc cookie bằng JavaScript nhưng không ngăn XSS thực hiện request bằng session của người dùng. `Secure` bảo vệ việc gửi cookie qua transport không an toàn; `SameSite` giảm một số request cross-site; không thuộc tính nào thay thế authorization server-side.

Không dùng cookie để lưu dữ liệu nhạy cảm dạng plaintext. Lưu một opaque identifier và giữ state nhạy cảm ở server. Tránh nhét PII, role hoặc quyền có thể thay đổi trực tiếp vào cookie nếu không có cơ chế integrity/rotation thích hợp.

### 4.6. Third-party cookie và CHIPS/Partitioned cookie

Third-party cookie truyền thống có thể cho phép một provider nhận cùng định danh khi được nhúng trên nhiều top-level site. Đây là cơ chế phổ biến cho cross-site tracking. Browser hiện có chính sách khác nhau: chặn mặc định, giới hạn theo chế độ riêng tư, yêu cầu user choice hoặc áp dụng tracking prevention bổ sung. Không giả định mọi browser có cùng một lịch trình hay hành vi chặn cookie.

CHIPS (Cookies Having Independent Partitioned State) cho phép một số cookie cross-site được phân vùng theo top-level site. Cookie được đánh dấu `Partitioned` có thể có state riêng khi cùng một embedded provider xuất hiện trên từng website khác nhau. Ví dụ header:

```http
Set-Cookie: __Host-widget-session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
```

Cookie partitioned vẫn là cookie của embedded site nhưng state được tách theo top-level site. Nó hữu ích cho widget cần session riêng theo từng website nhúng, ví dụ giỏ hàng hoặc trạng thái hỗ trợ của một đối tác. Nó không tạo một định danh cross-site dùng chung; cũng không biến widget thành trusted code.

CHIPS cần browser support và policy phù hợp. `Partitioned` không phải cách mở lại unrestricted third-party cookie. Kiểm tra compatibility và fallback; nếu không hỗ trợ, thiết kế phải hoạt động an toàn khi cookie không được gửi.

### 4.7. `document.cookie` không cho biết toàn bộ cookie jar

JavaScript chỉ đọc được cookie không có `HttpOnly` và phù hợp host/path/context. Không thấy cookie trong `document.cookie` có thể do `HttpOnly`, SameSite, third-party blocking, partitioning, expiry hoặc domain/path mismatch. Không thấy cookie không đồng nghĩa server chắc chắn không nhận cookie; ngược lại, thấy cookie trong script không chứng minh server sẽ nhận nó ở mọi request.

Dùng DevTools → Application/Storage → Cookies và Network request headers để phân biệt cookie được lưu với cookie thực sự được gửi. Không log cookie value trong console hoặc gửi ảnh chụp chứa session ID.

## 5. Storage và phân vùng theo top-level site

### 5.1. Origin storage và top-level context

Các API như `localStorage`, IndexedDB, Cache Storage và Service Worker thường được mô tả theo origin. Tuy nhiên, trong third-party context, browser có thể phân vùng hoặc giới hạn state theo top-level site để một embedded origin không dùng cùng storage identifier trên mọi website nhúng nó.

Một cách hình dung thực hành là storage key có thể chứa origin của frame và top-level site của trang chính. Ví dụ cùng một `widget.vendor.test` được nhúng ở `shop.example.test` và `news.example.test` có thể nhận hai vùng storage riêng. Khi người dùng mở `widget.vendor.test` trực tiếp ở top-level, browser có thể dùng vùng first-party khác.

Đây là xu hướng privacy của browser, không phải một giả định tương thích phổ quát cho mọi API/browser/version. Chính sách partitioning, quota, eviction và persistence có thể khác nhau. Ứng dụng không được dựa vào third-party storage để giữ session hoặc đồng bộ state xuyên website.

### 5.2. Các loại state cần xem xét

| API/state | Dùng cho | Câu hỏi privacy/security |
| --- | --- | --- |
| `localStorage` | State key/value tồn tại qua session | Có cần lưu ở embedded context? Có thể bị XSS đọc không? |
| `sessionStorage` | State theo tab/session | Có bị dùng như định danh lâu dài không? |
| IndexedDB | Dữ liệu cấu trúc/offline | Có phân vùng theo top-level site? Có dữ liệu cá nhân cần purge không? |
| Cache Storage | Response do app quản lý | Có cache response theo user/tenant không? |
| Service Worker | Intercept request trong scope | Scope và storage context có phù hợp? Có cache nhạy cảm không? |
| HTTP cache/network state | Cache response và trạng thái kết nối | Browser có network partitioning theo top-level site không? |
| BroadcastChannel | Trao đổi giữa browsing context cùng origin/storage partition phù hợp | Có vô tình phát dữ liệu qua context không mong muốn không? |

Đừng gộp tất cả thành “browser storage”. Mỗi API có scope, partitioning và lifecycle riêng. Kiểm tra tài liệu API và browser support matrix trước khi dựa vào một hành vi cụ thể.

### 5.3. Storage partitioning giảm khả năng liên kết cross-site

Nếu browser phân vùng storage theo top-level site, cùng một embedded provider không dễ đọc cùng local state khi được nhúng trên nhiều website khác nhau. Điều này làm giảm một số dạng tracking dựa trên cookie/storage identifier dùng chung.

Partitioning không xóa mọi tracking vector. Provider vẫn có thể nhận request và thấy IP/network metadata, user agent hints, referrer (nếu policy cho phép), URL parameters, thời điểm truy cập hoặc các tín hiệu fingerprinting. Website first-party cũng có thể tự thu thập định danh và chia sẻ dữ liệu server-side. Partitioning là một lớp privacy, không phải ẩn danh.

### 5.4. Dữ liệu first-party vẫn có thể bị rò rỉ

State lưu ở first-party context có thể bị đọc bởi script cùng origin, extension, malware, người dùng dùng chung thiết bị hoặc backend bị compromise. XSS có thể đọc localStorage/IndexedDB và gọi API dưới session hiện tại. Cache Storage có thể chứa response cá nhân hóa nếu Service Worker cache sai.

Với session và dữ liệu nhạy cảm, ưu tiên server-side storage và cookie HttpOnly. Chỉ lưu client-side những dữ liệu cần thiết, không lưu secret dài hạn, đặt TTL và xóa khi logout/account switch. Bảo vệ DOM bằng CSP/Trusted Types và validate mọi input khi đưa vào giao diện.

## 6. Khi embedded content cần state: Storage Access API và FedCM

### 6.1. Không mặc định mở lại third-party state

Một widget nhúng có thể cần biết người dùng đã đăng nhập với provider hay chưa. Trước đây, nhiều hệ thống dựa vào third-party cookie dùng chung giữa các website. Browser tracking prevention và third-party cookie restrictions làm luồng này không còn đáng tin cậy.

Trước khi xin quyền truy cập state không phân vùng, hãy xem widget có thực sự cần nhận diện cùng một tài khoản trên nhiều top-level site không. Có thể thay bằng:

- Session riêng theo từng top-level site, dùng partitioned cookie (CHIPS).
- Luồng top-level redirect/popup có state và nonce được bảo vệ.
- Token capability ngắn hạn do backend cấp cho đúng mục đích.
- FedCM cho use case đăng nhập liên kết được browser hỗ trợ.
- API server-to-server cho dữ liệu không cần browser cookie.

Không xin quyền unpartitioned state chỉ để giữ analytics identifier hoặc nối lịch sử tracking xuyên website.

### 6.2. Storage Access API

Storage Access API cho phép một embedded document yêu cầu quyền truy cập một số state first-party, thường là unpartitioned cookies, theo policy của browser. Tên API phổ biến là `document.hasStorageAccess()` và `document.requestStorageAccess()`.

Yêu cầu truy cập có thể phụ thuộc user activation, lịch sử tương tác first-party với embedded site, browser settings, Permissions Policy, sandbox và quyết định của người dùng. API có thể bị từ chối hoặc không được hỗ trợ; ứng dụng phải có fallback hoạt động không cần quyền này.

Ví dụ minh họa:

```javascript
async function checkEmbeddedCookieAccess() {
  if (!document.hasStorageAccess) {
    return { supported: false, access: false };
  }

  return {
    supported: true,
    access: await document.hasStorageAccess()
  };
}

async function requestEmbeddedCookieAccess() {
  if (!document.requestStorageAccess) {
    throw new Error("Storage Access API is unavailable");
  }

  // Gọi từ handler của thao tác người dùng, ví dụ click nút.
  await document.requestStorageAccess();
  return document.hasStorageAccess();
}

document.querySelector("#enable-account-widget").addEventListener(
  "click",
  async () => {
    try {
      const access = await requestEmbeddedCookieAccess();
      document.querySelector("#status").textContent =
        access ? "Cookie access granted" : "Cookie access not available";
    } catch {
      document.querySelector("#status").textContent =
        "Cookie access was denied; continue in partitioned mode";
    }
  }
);
```

Đừng tự động gọi request khi iframe vừa tải. Hãy giải thích vì sao widget cần quyền, để người dùng chủ động nhấn nút, xử lý denial và không khóa chức năng chính khi quyền không được cấp. Nếu iframe có sandbox, cần kiểm tra token phù hợp như `allow-storage-access-by-user-activation`; không bỏ sandbox rộng chỉ để làm API chạy.

Storage Access API và các biến thể mở rộng thay đổi theo browser/spec. Kiểm tra tài liệu browser mục tiêu để biết loại state nào được cấp và điều kiện nào áp dụng; đừng suy rộng quyền cookie thành quyền đọc mọi storage của origin.

### 6.3. FedCM cho liên kết danh tính

Federated Credential Management (FedCM) là API browser-mediated cho một số luồng identity federation. Mục tiêu là giảm việc website relying party phải dựa vào third-party cookie để nhận diện phiên đăng nhập của identity provider. Browser tham gia điều phối giao diện và thông tin đăng nhập theo policy.

FedCM không phải API tổng quát để truy cập cookie third-party, không thay thế authorization của ứng dụng và không làm mọi identity provider tương thích tự động. Với use case SSO, đánh giá FedCM cùng redirect-based OAuth/OIDC flow, state/nonce, PKCE, issuer/audience và redirect URI allowlist.

### 6.4. Fallback phải bảo toàn ranh giới quyền

Nếu third-party cookie hoặc Storage Access API không khả dụng, widget nên hiển thị trạng thái chưa đăng nhập và yêu cầu người dùng mở provider ở top-level hoặc thực hiện luồng xác thực được hỗ trợ. Không dùng fingerprinting, URL decoration hoặc redirect bounce để lách browser privacy controls.

Nếu cấp token cho iframe, token nên có audience, scope, expiry và resource giới hạn; truyền qua cơ chế an toàn như postMessage với kiểm tra origin chính xác hoặc backend exchange, không gắn token dài hạn vào query string.

## 7. Tracking vectors trong first-party và third-party context

### 7.1. Cookie và storage identifier

Third-party cookie hoặc unpartitioned storage có thể cho phép một provider nhận diện cùng browser khi được nhúng trên nhiều top-level site. Partitioning và cookie restrictions giảm một số đường liên kết này.

First-party site vẫn có thể tạo ID riêng, liên kết tài khoản, ghi nhận hành vi và gửi dữ liệu lên backend. Khi nhiều website thuộc cùng một tổ chức chia sẻ backend hoặc login provider, dữ liệu có thể được liên kết server-side ngay cả khi browser partition storage. Privacy review phải xem cả luồng server-side, không chỉ cookie.

### 7.2. URL decoration và link decoration

Một site có thể thêm click ID hoặc tracking parameter vào link dẫn tới site khác. Site đích có thể đọc parameter rồi lưu nó trong cookie hoặc storage first-party. Ví dụ:

```text
https://shop.example.test/product?campaign_id=abc123&click_id=xyz789
```

Các parameter có thể cần cho attribution hoặc checkout, nhưng cũng có thể mang identifier để liên kết hoạt động cross-site. Giới hạn dữ liệu trong URL, dùng ID ngắn hạn theo mục đích, không đưa PII/token vào query, xóa parameter khỏi address bar sau khi xử lý nếu không cần và áp dụng retention phù hợp.

### 7.3. Referrer và network metadata

Request có thể gửi `Referer` chứa URL nguồn theo Referrer Policy. URL nguồn đôi khi chứa search term, user ID hoặc query nhạy cảm. IP address, TLS/network metadata, user agent và client hints cũng có thể hỗ trợ liên kết request.

Đặt `Referrer-Policy` phù hợp, ví dụ `strict-origin-when-cross-origin` hoặc chặt hơn cho trang có URL nhạy cảm. Tránh đưa secret vào URL; dùng POST body hoặc server-side state cho dữ liệu cần bảo mật. Không coi referrer policy là biện pháp ẩn danh mạng.

### 7.4. Fingerprinting

Fingerprinting kết hợp nhiều tín hiệu như font, screen size, timezone, locale, rendering, device capabilities, audio/video support và browser behavior để phân biệt browser. Một số API bị giảm entropy hoặc yêu cầu permission, nhưng fingerprinting vẫn có thể kết hợp nhiều nguồn.

Giảm thu thập device/browser detail nếu không cần cho chức năng. Không dùng device fingerprint làm yếu tố authentication duy nhất. Cung cấp lựa chọn privacy rõ ràng, giới hạn retention và tránh liên kết fingerprint với tài khoản ngoài mục đích đã công bố.

### 7.5. First-party tracking vẫn cần giới hạn

Khi site thu thập analytics ở first-party context, cần xác định mục đích cụ thể, event cần thiết, dữ liệu nhận dạng, thời gian lưu, đối tượng nhận dữ liệu và cách người dùng thực hiện lựa chọn. Tránh thu toàn bộ URL, form input, message, session replay hoặc thông tin thiết bị nếu không thực sự cần.

Đừng xem “first-party” là lý do để thu thập vô hạn. Giảm dữ liệu ngay tại client, loại bỏ field nhạy cảm trước khi gửi, áp dụng retention và access control ở backend, và không chia sẻ định danh với bên khác ngoài mục đích đã thông báo.

## 8. Thiết kế ứng dụng bảo vệ first-party context

### 8.1. Chọn đúng ranh giới host/origin

Đặt session và dữ liệu nhạy cảm trên hostname riêng có ranh giới tin cậy rõ. Ưu tiên host-only cookie cho ứng dụng đăng nhập. Tránh dùng Domain rộng để chia sẻ session giữa các subdomain không cùng mức tin cậy.

Nếu cần giao tiếp giữa origin, dùng API có authentication/authorization và CORS allowlist cụ thể. Không dùng `document.domain` để nới lỏng same-origin; API này đã deprecated và làm suy yếu ranh giới origin.

### 8.2. Cookie và CSRF

Với session cookie:

- Dùng Secure, HttpOnly và SameSite phù hợp.
- Ưu tiên host-only; dùng `__Host-` nếu đáp ứng điều kiện.
- Rotate session sau authentication/privilege change.
- Revoke server-side khi logout, account switch hoặc session compromise.
- Bảo vệ state-changing request bằng CSRF token và kiểm tra authorization.
- Không dựa riêng vào SameSite, vì same-site subdomain có thể vẫn không đáng tin.

Nếu cần cross-site cookie cho embedded widget, cân nhắc partitioned cookie trước. Chỉ yêu cầu unpartitioned access khi use case thực sự cần và có fallback.

### 8.3. CORS và postMessage

CORS cho phép JavaScript đọc response từ origin khác khi server trả policy phù hợp. CORS không cấp quyền truy cập cookie tùy ý, không xác thực peer và không thay thế authorization.

Với iframe/postMessage:

- Kiểm tra `event.origin` bằng so sánh chính xác với allowlist.
- Kiểm tra `event.source` nếu cần ràng buộc đúng iframe/window.
- Validate schema, size và message type.
- Không dùng `targetOrigin: "*"` khi gửi token hoặc dữ liệu nhạy cảm.
- Không coi origin là danh tính user; vẫn cần token/session và authorization.

Ví dụ:

```javascript
const trustedOrigin = "https://widget.partner.example";

window.addEventListener("message", event => {
  if (event.origin !== trustedOrigin) return;
  if (event.source !== widgetFrame.contentWindow) return;

  const data = event.data;
  if (
    data === null ||
    typeof data !== "object" ||
    data.type !== "widget.ready" ||
    data.version !== 1
  ) {
    return;
  }

  // Chỉ xử lý message đã qua origin, source và schema checks.
});
```

### 8.4. CSP, framing và Permissions Policy

Dùng CSP để giới hạn script và frame source. Nếu không cần nhúng, đặt `frame-ancestors 'none'`; nếu chỉ cho portal cụ thể, allowlist origin rõ ràng. Với iframe cần camera, microphone hoặc storage access, cấp feature tối thiểu qua Permissions Policy và thuộc tính allow; không dùng wildcard cho origin không kiểm soát.

Ví dụ header baseline cần điều chỉnh theo ứng dụng:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

CSP không thay thế cookie policy hoặc storage partitioning. Permissions Policy không tự cấp quyền người dùng. Kiểm tra response headers và behavior trong browser sau mỗi thay đổi.

### 8.5. Data minimization và retention

Lập inventory cho cookie, localStorage, IndexedDB, Cache Storage, URL parameter và analytics event. Với mỗi item, ghi rõ mục đích, data owner, thời hạn, cách xóa, bên nhận và cách người dùng kiểm soát. Xóa state theo account logout, tenant switch và permission revoke; lưu ý server-side identifier và browser storage cần cleanup riêng.

### 8.6. Fetch Metadata để phân biệt request context

Browser có thể gửi Fetch Metadata headers như `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` và `Sec-Fetch-User`. `Sec-Fetch-Site` thường cho biết request là `same-origin`, `same-site`, `cross-site` hoặc `none` (ví dụ một số user-initiated top-level navigation). Server có thể dùng các header này như tín hiệu bổ sung để từ chối request cross-site không phù hợp tới endpoint nhạy cảm.

Ví dụ policy ở server có thể từ chối `cross-site` request tới endpoint thay đổi trạng thái nếu endpoint không phục vụ luồng cross-site hợp lệ. Tuy nhiên, Fetch Metadata không thay thế authentication, authorization hoặc CSRF token; cần có fallback cho client không gửi header và allowlist riêng cho endpoint SSO/payment cần cross-site.

## 9. Ví dụ triển khai

### 9.1. Cookie session first-party

Server phát hành session cookie host-only:

```http
Set-Cookie: __Host-session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Không khai báo `Domain`, không lưu thông tin cá nhân trong cookie và không dùng session ID làm dữ liệu analytics. Backend cần kiểm tra session ở mỗi request, rotate ID khi quyền thay đổi và revoke khi logout.

### 9.2. Embedded widget với cookie partitioned

Một widget cần lưu trạng thái riêng theo website nhúng có thể dùng CHIPS nếu browser hỗ trợ:

```http
Set-Cookie: __Host-widget-state=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=None; Partitioned; Max-Age=3600
```

Khi cùng widget được nhúng trên hai top-level site khác nhau, browser có thể lưu hai giá trị riêng. Widget phải hoạt động an toàn khi cookie không được gửi hoặc browser không hỗ trợ partitioned cookies.

### 9.3. Fetch có credentials không mở khóa third-party cookie

```javascript
const response = await fetch("https://api.example.test/profile", {
  method: "GET",
  credentials: "include"
});
```

`credentials: "include"` cho phép fetch gửi credentials theo quy tắc browser và CORS. Nó không vượt qua SameSite, third-party cookie blocking, storage partitioning hoặc quyền của người dùng. Server cần trả CORS policy cụ thể, ví dụ `Access-Control-Allow-Origin` đúng origin và `Access-Control-Allow-Credentials: true`; không dùng wildcard origin với credentials.

### 9.4. CORS response cho một embedded origin cụ thể

```http
Access-Control-Allow-Origin: https://portal.partner.example
Access-Control-Allow-Credentials: true
Vary: Origin
```

Server phải kiểm tra Origin với allowlist trước khi phản hồi. CORS chỉ cho phép JavaScript đọc response; nó không tự cấp authorization tới dữ liệu account và không đảm bảo cookie third-party sẽ được browser gửi.

## 10. Lab localhost: quan sát first-party và third-party context

Lab dùng cùng một Node server nhưng truy cập qua hai hostname loopback khác nhau:

- Top-level page: `http://localhost:8080`
- Embedded provider: `http://127.0.0.1:8080`

Hai hostname có origin và site khác nhau trong lab. Iframe từ địa chỉ IP được nhúng trong trang localhost, tạo một third-party context. Khi mở địa chỉ IP trực tiếp ở top-level, provider trở thành first party. Hành vi cookie/storage còn phụ thuộc browser, phiên bản và cài đặt privacy.

### 10.1. Tạo file server

Tạo `server.mjs`:

```javascript
import { createServer } from "node:http";

const parentPage = [
  "<!doctype html>",
  '<html lang="vi"><head><meta charset="utf-8"><title>First-party context lab</title></head>',
  "<body>",
  "<h1>Top-level site: localhost</h1>",
  '<p id="cookie-state"></p>',
  '<iframe title="Cross-site embedded provider" src="http://127.0.0.1:8080/embed" width="700" height="420"></iframe>',
  '<p><a href="http://127.0.0.1:8080/check" target="_blank" rel="noopener">Open provider as top-level site</a></p>',
  "<script>",
  'document.querySelector("#cookie-state").textContent = "localhost document.cookie: " + document.cookie;',
  "</script>",
  "</body></html>"
].join("\n");

const embeddedPage = [
  "<!doctype html>",
  '<html lang="vi"><head><meta charset="utf-8"><title>Embedded provider</title></head>',
  "<body>",
  "<h2>Provider embedded under localhost</h2>",
  '<p id="cookie-state"></p><p id="storage-state"></p><p id="access-state"></p>',
  '<button id="request-access">Request storage access</button>',
  "<script>",
  'const cookieState = document.querySelector("#cookie-state");',
  'const storageState = document.querySelector("#storage-state");',
  'const accessState = document.querySelector("#access-state");',
  'localStorage.setItem("context-probe", "written-while-embedded");',
  'cookieState.textContent = "document.cookie: " + document.cookie;',
  'storageState.textContent = "localStorage probe: " + localStorage.getItem("context-probe");',
  "async function showAccess() {",
  '  if (!document.hasStorageAccess) { accessState.textContent = "Storage Access API unavailable"; return; }',
  '  accessState.textContent = "hasStorageAccess: " + await document.hasStorageAccess();',
  "}",
  "showAccess();",
  'document.querySelector("#request-access").addEventListener("click", async () => {',
  "  try {",
  '    if (!document.requestStorageAccess) throw new Error("requestStorageAccess unavailable");',
  "    await document.requestStorageAccess();",
  "    await showAccess();",
  "  } catch (error) {",
  '    accessState.textContent = "Access not granted: " + error.name;',
  "  }",
  "});",
  "</script>",
  "</body></html>"
].join("\n");

const checkPage = [
  "<!doctype html>",
  '<html lang="vi"><head><meta charset="utf-8"><title>Provider first-party check</title></head>',
  "<body>",
  "<h1>Provider as top-level site</h1>",
  '<p id="cookie-state"></p><p id="storage-state"></p>',
  "<script>",
  'document.querySelector("#cookie-state").textContent = "127.0.0.1 document.cookie: " + document.cookie;',
  'document.querySelector("#storage-state").textContent = "localStorage probe: " + (localStorage.getItem("context-probe") || "(no value in this context)");',
  "</script>",
  "</body></html>"
].join("\n");

const server = createServer((request, response) => {
  const url = new URL(request.url, "http://localhost:8080");

  if (request.method !== "GET") {
    response.writeHead(405);
    response.end("Method not allowed");
    return;
  }

  if (url.pathname === "/") {
    response.setHeader("Set-Cookie",
      "fp_probe=localhost-first-party; Path=/; SameSite=Lax; Max-Age=3600");
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(parentPage);
    return;
  }

  if (url.pathname === "/embed") {
    response.setHeader("Set-Cookie", [
      "tp_probe=unpartitioned-demo; Path=/; SameSite=None; Secure; Max-Age=3600",
      "__Host-chips_probe=partitioned-demo; Path=/; SameSite=None; Secure; Partitioned; Max-Age=3600"
    ]);
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(embeddedPage);
    return;
  }

  if (url.pathname === "/check") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(checkPage);
    return;
  }

  response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  response.end("Not found");
});

server.listen(8080, "0.0.0.0", () => {
  console.log("Open http://localhost:8080");
});
```

### 10.2. Chạy lab

Trong thư mục chứa file:

```bash
node server.mjs
```

Mở `http://localhost:8080`. Trang chính sẽ nhúng provider từ `http://127.0.0.1:8080/embed`. Hai URL có hostname khác nhau nên là cross-origin; địa chỉ IP và hostname localhost cũng là hai site khác nhau trong bài thử nghiệm.

### 10.3. Quan sát cookie và storage

1. Ghi lại cookie `fp_probe` trên trang top-level localhost.
2. Trong iframe, quan sát `document.cookie`, `localStorage probe` và trạng thái `hasStorageAccess`.
3. Nếu browser hỗ trợ, nhấn **Request storage access** và quan sát kết quả; browser có thể từ chối nếu điều kiện user interaction/policy chưa thỏa.
4. Mở link **Open provider as top-level site**. Provider hiện ở first-party context tại địa chỉ IP.
5. So sánh cookie và localStorage probe trong top-level provider với giá trị đã thấy khi embedded.
6. Mở DevTools → Application/Storage → Cookies và kiểm tra cookie `tp_probe`, `__Host-chips_probe`; quan sát cột Partition Key nếu browser hiển thị.
7. Mở Network và kiểm tra `Set-Cookie` response cũng như Cookie request header. Browser có thể lưu cookie nhưng không gửi nó trong third-party context.

### 10.4. Cách đọc kết quả

- Nếu `tp_probe` không xuất hiện trong iframe, browser có thể đã chặn unpartitioned third-party cookie.
- Nếu `__Host-chips_probe` xuất hiện, browser có thể hỗ trợ partitioned cookie; kiểm tra partition key để xác nhận context.
- Nếu localStorage probe ở top-level provider không có giá trị được ghi khi embedded, browser có thể đang partition storage theo top-level site.
- Nếu probe xuất hiện ở cả hai nơi, browser/configuration có thể không partition API đó trong trường hợp test; không suy ra mọi browser đều như vậy.
- Storage Access API có thể không được cấp trong lab nếu provider chưa có tương tác first-party hoặc browser yêu cầu điều kiện khác. Đây không phải lỗi của mọi third-party context.

Lab không chứng minh đầy đủ chính sách privacy của browser. Dùng nó để quan sát khác biệt giữa host/origin, top-level site, cookie và storage; kiểm tra thêm browser/version khác nhau.

### 10.5. Dọn lab

Dừng Node server bằng Ctrl+C. Xóa cookie và site data của localhost và 127.0.0.1 trong DevTools/site settings, sau đó đóng tab. Không dùng hostname loopback hoặc cookie demo trong production.

## 11. Ma trận kiểm thử first-party context

Chạy trên các browser và chế độ privacy nằm trong support matrix của sản phẩm. Ghi lại browser/version, top-level URL, embedded URL, cookie attributes, storage API, trạng thái permission và kết quả request. Không ghi cookie value, session ID hoặc identifier thật vào test report.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| FP-01 | Cùng URL mở trực tiếp ở top-level | Site hoạt động trong first-party context |
| FP-02 | Cùng site được nhúng trong iframe của site khác | Browser áp dụng third-party context policy |
| FP-03 | Hai subdomain cùng scheme và registrable domain | Có thể same-site nhưng vẫn cross-origin |
| FP-04 | Cùng hostname nhưng khác port | Khác origin; cookie không được phân vùng theo port |
| FP-05 | Cùng hostname nhưng khác scheme | Khác origin và khác schemeful site |
| FP-06 | Host-only cookie | Chỉ gửi tới host đã tạo cookie |
| FP-07 | Cookie khai báo Domain rộng | Được gửi tới subdomain phù hợp; đánh giá blast radius |
| FP-08 | Cookie SameSite=Strict trong cross-site navigation | Không gửi trong cross-site context |
| FP-09 | Cookie SameSite=Lax trong top-level safe navigation | Gửi theo quy tắc Lax của browser |
| FP-10 | Cookie SameSite=None; Secure trong iframe | Kết quả phụ thuộc third-party cookie policy |
| FP-11 | Session cookie có Secure, HttpOnly và __Host- | Script không đọc cookie; cookie host-only theo prefix |
| FP-12 | Third-party cookie bị browser chặn | Embedded widget fallback không phụ thuộc cookie |
| FP-13 | CHIPS/Partitioned cookie trên hai top-level site | State được phân vùng theo top-level site nếu browser hỗ trợ |
| FP-14 | localStorage ghi trong iframe cross-site | Kiểm tra state có bị partition theo top-level site |
| FP-15 | IndexedDB/Cache Storage trong embedded context | Kiểm tra partitioning, quota và persistence riêng |
| FP-16 | Storage Access API không được hỗ trợ | Widget chuyển sang fallback an toàn |
| FP-17 | Storage Access API bị từ chối | Không khóa chức năng chính hoặc lách policy |
| FP-18 | Storage Access API được gọi từ thao tác người dùng | Browser áp dụng user activation và policy hiện hành |
| FP-19 | iframe sandbox không có token storage access phù hợp | Request access bị giới hạn theo policy |
| FP-20 | CORS fetch credentials include | Chỉ đọc response khi CORS hợp lệ; cookie vẫn theo browser policy |
| FP-21 | postMessage từ origin ngoài allowlist | Message bị từ chối |
| FP-22 | URL chứa click ID hoặc token | Secret không xuất hiện; parameter tracking được giới hạn |
| FP-23 | Referrer từ trang có query nhạy cảm | Policy không làm lộ full URL ngoài dự kiến |
| FP-24 | Redirect qua domain trung gian | Callback allowlist, state/nonce và redirect chain được kiểm soát |
| FP-25 | Logout/account switch | Session server-side và browser state cần thiết được revoke/purge |
| FP-26 | XSS cùng origin | Threat model xác nhận script có thể truy cập state không HttpOnly |
| FP-27 | Browser bật chế độ chặn third-party cookies | Ứng dụng vẫn hoàn thành luồng chính |
| FP-28 | Browser tracking prevention xóa state | Ứng dụng xử lý session hết hạn và yêu cầu đăng nhập lại an toàn |
| FP-29 | Embedded widget nằm trong nested iframe có ancestor cross-site | Cookie/site context được đánh giá theo cây ancestor và browser policy |
| FP-30 | Endpoint nhạy cảm nhận Sec-Fetch-Site=cross-site | Server áp dụng Fetch Metadata policy và vẫn kiểm tra CSRF/authorization |

### 11.1. Kiểm tra trong DevTools

Trong Chromium DevTools:

1. Mở Application → Storage để xem cookie, localStorage, IndexedDB, Cache Storage và Service Worker theo origin.
2. Mở Cookies và kiểm tra Domain, Path, SameSite, Secure, HttpOnly, Partitioned và Partition Key nếu được hiển thị.
3. Mở Network và kiểm tra `Set-Cookie`, Cookie request header, `Origin`, `Referer` và response CORS.
4. Chọn iframe trong Elements/Console context selector để chạy kiểm tra trong đúng frame.
5. Dùng Clear site data để reset state trước mỗi lần test; nhớ xóa cả hai hostname trong lab.
6. Thử lại trong profile sạch và chế độ privacy khác nhau.

Tên cột, cảnh báo third-party cookie và cách hiển thị partition key thay đổi theo browser/version. Không kết luận từ một browser duy nhất.

### 11.2. Automation

Với Playwright, có thể mở top-level localhost, xác nhận iframe và quan sát DOM của frame:

```javascript
await page.goto("http://localhost:8080");

const providerFrame = page.frameLocator(
  'iframe[src="http://127.0.0.1:8080/embed"]'
);

await expect(providerFrame.locator("#storage-state"))
  .toContainText("written-while-embedded");

const cookieState = await providerFrame.locator("#cookie-state").innerText();
expect(cookieState).toContain("document.cookie");

const providerPagePromise = page.waitForEvent("popup");
await page.getByRole("link", {
  name: "Open provider as top-level site"
}).click();

const providerPage = await providerPagePromise;
await expect(providerPage).toHaveURL(/127\.0\.0\.1:8080\/check/);
```

Kết quả cookie/storage thay đổi theo browser engine và policy test. Không viết assertion rằng third-party cookie luôn bị chặn hoặc localStorage luôn partitioned nếu test suite hỗ trợ nhiều browser. Thay vào đó, ghi nhận capability/behavior và kiểm tra ứng dụng fallback đúng khi state không có.

## 12. Những ngộ nhận thường gặp

**“First-party context nghĩa là same-origin.”** Sai. Hai subdomain có thể khác origin nhưng same-site; first-party/third-party còn phụ thuộc top-level site và cách resource được nhúng.

**“Same-site cookie có nghĩa SOP cho phép đọc DOM.”** Sai. SameSite là quy tắc cookie; SOP dùng origin. Hai subdomain same-site vẫn có thể cross-origin.

**“Cookie được cô lập theo port.”** Sai. Cookie không có port scope như origin. Ứng dụng khác port trên cùng host có thể chia sẻ cookie phù hợp domain/path.

**“Cookie first-party luôn an toàn.”** Sai. Cookie vẫn chịu XSS, CSRF, session fixation, log leak và server compromise. Dùng Secure, HttpOnly, SameSite, host-only và authorization.

**“SameSite=Lax ngăn mọi CSRF.”** Sai. Nó giảm một số cross-site request; same-site subdomain bị chiếm quyền và một số flow vẫn cần CSRF token/authorization.

**“SameSite=None bảo đảm third-party cookie được gửi.”** Sai. Browser có thể chặn third-party cookie hoặc áp dụng tracking prevention dù cookie có SameSite=None; Secure.

**“Partitioned cookie là cookie cross-site dùng chung.”** Sai. CHIPS tách state theo top-level site để embedded provider không dùng một state identifier chung trên mọi website.

**“Storage partitioning làm người dùng ẩn danh.”** Sai. IP, URL parameter, referrer, fingerprinting và dữ liệu server-side vẫn có thể liên kết hoạt động.

**“Storage Access API luôn cấp quyền nếu người dùng nhấn nút.”** Sai. Browser có thể yêu cầu lịch sử tương tác first-party, permission, user activation hoặc điều kiện khác và vẫn từ chối.

**“CORS cho phép embedded site đọc cookie third-party.”** Sai. CORS điều khiển việc đọc HTTP response; cookie còn chịu SameSite, credentials mode, partitioning và browser privacy policy.

**“FedCM là cách mở lại mọi third-party cookie.”** Sai. FedCM hỗ trợ một số luồng identity federation do browser điều phối; nó không phải API truy cập cookie tổng quát.

**“First-party analytics không cần privacy review.”** Sai. Dữ liệu first-party vẫn có thể nhạy cảm; cần mục đích, data minimization, retention, access control và thông báo minh bạch.

## 13. Checklist triển khai

Trước khi phát hành, xác nhận:

1. **Context map:** xác định top-level site, embedded site, origin và schemeful site cho từng luồng.
2. **Trust boundary:** tách hostname/origin theo mức tin cậy; không coi subdomain cùng site là cùng security principal.
3. **Session cookie:** host-only, Secure, HttpOnly, SameSite phù hợp và prefix `__Host-` khi đáp ứng điều kiện.
4. **Domain scope:** không dùng Domain rộng nếu không có nhu cầu và threat model rõ.
5. **Cross-site cookie:** chỉ dùng `SameSite=None; Secure` khi flow thực sự cần.
6. **Partitioned state:** ưu tiên CHIPS cho widget cần state riêng theo top-level site.
7. **Browser compatibility:** kiểm tra third-party cookie restrictions và partitioning trên browser mục tiêu.
8. **Storage inventory:** liệt kê localStorage, IndexedDB, Cache Storage, Service Worker, HTTP cache và BroadcastChannel.
9. **Sensitive state:** không lưu secret dài hạn trong JavaScript-readable storage; dùng server-side session và HttpOnly cookie.
10. **Storage Access API:** giải thích mục đích, gọi từ user activation, xử lý denial và có fallback.
11. **Identity flow:** đánh giá FedCM/OIDC, state, nonce, PKCE, issuer/audience và redirect URI.
12. **CORS:** allowlist origin cụ thể; không wildcard với credentials; dùng Vary: Origin khi phản hồi động theo Origin.
13. **postMessage:** kiểm tra origin, source, schema và targetOrigin.
14. **CSRF:** dùng token và authorization server-side; không dựa riêng vào SameSite.
15. **XSS:** CSP, Trusted Types, safe DOM, output encoding và kiểm soát dependency.
16. **Framing:** frame-ancestors và sandbox chỉ cho origin/feature cần thiết.
17. **Referrer:** không đưa secret vào URL; đặt Referrer-Policy phù hợp.
18. **Tracking:** đánh giá cookie, URL decoration, bounce, referrer, fingerprinting và server-side linking.
19. **Data minimization:** chỉ thu event/field cần thiết; redaction trước khi gửi analytics.
20. **Retention:** đặt TTL, purge khi logout/account switch và kiểm soát bên nhận dữ liệu.
21. **Testing:** test first-party, third-party, same-site cross-origin, browser privacy mode và storage denial.
22. **Observability:** không log cookie value, token, raw URL có PII hoặc storage identifier không cần thiết.
23. **Fallback:** luồng chính vẫn hoạt động khi third-party cookie/storage bị chặn hoặc bị browser xóa.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** First-party context được xác định dựa trên điều gì?  
**Đáp án:** Site được truy cập trực tiếp ở vai trò top-level site; khi site đó được nhúng trong top-level site khác, nó có thể ở third-party context.

**Câu 2.** Origin gồm những thành phần nào?  
**Đáp án:** Scheme, host và port.

**Câu 3.** Site có giống origin không?  
**Đáp án:** Không. Site thường dựa trên scheme và registrable domain; origin còn phân biệt host và port đầy đủ.

**Câu 4.** Hai subdomain có thể same-site nhưng cross-origin không?  
**Đáp án:** Có, ví dụ shop.example.test và id.example.test cùng scheme.

**Câu 5.** Cookie có được cô lập theo port không?  
**Đáp án:** Không. Cookie scope dựa trên domain/host, path và các thuộc tính cookie; port không phải cookie boundary.

**Câu 6.** SameSite=None cần thuộc tính nào?  
**Đáp án:** Cookie phải có Secure theo yêu cầu hiện hành của browser.

**Câu 7.** CHIPS giải quyết vấn đề gì?  
**Đáp án:** Cho phép cookie embedded được phân vùng theo top-level site để mỗi website nhúng có state riêng.

**Câu 8.** Storage partitioning bảo vệ điều gì?  
**Đáp án:** Giảm khả năng một embedded origin dùng chung storage identifier để liên kết người dùng giữa nhiều top-level site.

**Câu 9.** Storage Access API dùng để làm gì?  
**Đáp án:** Cho embedded document yêu cầu quyền truy cập một số state first-party như unpartitioned cookies theo policy browser.

**Câu 10.** `credentials: include` có vượt third-party cookie blocking không?  
**Đáp án:** Không. Browser vẫn áp dụng SameSite, cookie policy, partitioning và permission.

**Câu 11.** FedCM có phải API truy cập cookie không?  
**Đáp án:** Không. Nó hỗ trợ một số luồng identity federation do browser điều phối.

**Câu 12.** First-party analytics có cần data minimization không?  
**Đáp án:** Có. First-party context không miễn trừ trách nhiệm bảo vệ dữ liệu và giới hạn mục đích.

**Câu 13.** CORS có xác thực người dùng không?  
**Đáp án:** Không. CORS chỉ điều khiển việc browser cho JavaScript đọc response cross-origin; authentication/authorization vẫn do ứng dụng xử lý.

**Câu 14.** Vì sao cần host-only cookie cho session?  
**Đáp án:** Để giới hạn cookie vào host phát hành, giảm rủi ro lộ session qua subdomain khác.

**Câu 15.** Khi browser chặn third-party cookie, widget nên làm gì?  
**Đáp án:** Hoạt động ở partitioned/unauthenticated mode hoặc dùng luồng top-level identity được hỗ trợ; không lách privacy controls bằng fingerprinting hay bounce tracking.

## 15. Ghi nhớ cốt lõi

First-party context phụ thuộc site đang là top-level site; third-party context xuất hiện khi một site được nhúng hoặc truy cập trong ngữ cảnh top-level site khác. Origin và site là hai khái niệm riêng: SOP dựa trên origin, trong khi SameSite và nhiều cơ chế privacy xét site/top-level context.

Cookie không được cô lập theo port. Session first-party nên dùng host-only, Secure, HttpOnly và SameSite phù hợp; CHIPS/Partitioned cookie có thể cấp state riêng theo top-level site cho widget. Storage partitioning giảm khả năng liên kết cross-site nhưng không tạo ẩn danh và không thay thế bảo vệ XSS, server-side authorization hoặc data minimization.

Storage Access API và FedCM hỗ trợ một số use case nhúng/identity có điều kiện; luôn cần fallback khi browser từ chối hoặc không hỗ trợ. CORS, SOP, CSRF, CSP, postMessage và Permissions Policy giải quyết các ranh giới khác nhau, không thể thay thế lẫn nhau.

**First-party context mô tả vị trí của site trong browsing context; quyền truy cập và mức độ riêng tư vẫn phải được thiết kế, kiểm tra và giới hạn ở từng lớp.**

### Tài liệu tham khảo

- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy).
- [MDN — SameSite cookies explained](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).
- [MDN — Cookies: HTTP state management](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).
- [MDN — CHIPS (Cookies Having Independent Partitioned State)](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies/CHIPS).
- [MDN — Storage Access API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_Access_API).
- [MDN — FedCM API](https://developer.mozilla.org/en-US/docs/Web/API/FedCM_API).
- [MDN — Fetch Metadata request headers](https://developer.mozilla.org/en-US/docs/Glossary/Fetch_metadata_request_header).
- [W3C — Storage Access API](https://privacycg.github.io/storage-access/).
- [W3C — Cookies: HTTP State Management Mechanism](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html).
- [WHATWG — HTML Standard: Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html).
- [Chrome for Developers — CHIPS](https://developers.google.com/privacy-sandbox/cookies/chips).
- [WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/).
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
