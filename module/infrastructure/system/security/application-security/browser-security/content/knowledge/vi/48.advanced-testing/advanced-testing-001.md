# Origin boundary test

Origin là ranh giới quan trọng trong mô hình bảo mật của trình duyệt. Nó xác định khi nào hai tài liệu hoặc ứng dụng web được xem là cùng một nguồn để áp dụng Same-Origin Policy (SOP), kiểm soát quyền đọc dữ liệu, truy cập DOM, storage và giao tiếp giữa các cửa sổ. Một lỗi trong việc xác định hoặc kiểm tra origin có thể làm lộ dữ liệu giữa các ứng dụng, cho phép trang không đáng tin cậy gửi thông điệp giả mạo hoặc mở rộng quyền truy cập ngoài dự kiến.

Origin boundary test là quá trình kiểm tra các ranh giới này bằng những trường hợp cùng origin, khác origin, cùng site nhưng khác origin và origin đặc biệt. Mục tiêu là xác nhận trình duyệt thực thi SOP đúng, ứng dụng chỉ cấp quyền cross-origin cho nguồn được cho phép và mã giao tiếp giữa các cửa sổ xác minh đúng bên gửi.

Bài học thuộc phạm vi bảo mật ứng dụng web: phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng để hiểu SOP, CORS cùng các cơ chế cách ly. Các thử nghiệm dùng website và tài khoản giả lập do bạn kiểm soát. Không kiểm tra hoặc truy cập dữ liệu của website bên ngoài khi chưa được phép.

## Mục tiêu

Sau bài học, bạn có thể:

- Xác định origin từ scheme, host và port; phân biệt origin với site, hostname và URL.
- Kiểm tra SOP đối với DOM, storage, JavaScript API và response cross-origin.
- Đánh giá CORS allowlist, preflight, credentials và hành vi khi redirect.
- Kiểm thử `postMessage`, iframe sandbox và các tài liệu có opaque origin.
- Phân biệt ranh giới origin với phạm vi cookie, `SameSite` và quyền truy cập của server.
- Xây dựng ma trận kiểm thử dương tính, âm tính và ghi nhận bằng chứng có thể tái hiện.

## Origin được xác định như thế nào?

Đối với URL web thông thường, origin là bộ ba gồm:

1. **Scheme:** giao thức, ví dụ `https` hoặc `http`.
2. **Host:** hostname hoặc địa chỉ host đã được chuẩn hóa.
3. **Port:** cổng hiệu lực của kết nối.

Hai URL có cùng origin khi cả ba thành phần này tương ứng. Path, query string và fragment không tham gia vào phép so sánh origin.

| URL A | URL B | Quan hệ origin | Lý do |
|---|---|---|---|
| `https://shop.example.test/a` | `https://shop.example.test/b` | Cùng origin | Khác path nhưng scheme, host và port giống nhau |
| `https://shop.example.test` | `http://shop.example.test` | Khác origin | Khác scheme |
| `https://shop.example.test` | `https://admin.example.test` | Khác origin | Khác host/subdomain |
| `https://shop.example.test` | `https://shop.example.test:8443` | Khác origin | Khác port |
| `https://shop.example.test` | `https://shop.example.test:443` | Cùng origin | Port 443 là port mặc định của HTTPS |
| `http://shop.example.test` | `http://shop.example.test:80` | Cùng origin | Port 80 là port mặc định của HTTP |

Khi so sánh, trình duyệt chuẩn hóa URL theo quy tắc của URL Standard. Không nên tự tách chuỗi URL bằng biểu thức đơn giản hoặc so sánh chuỗi con để quyết định quyền truy cập. Hãy parse URL bằng API chuẩn rồi so sánh các thành phần cần thiết.

```js
const target = new URL("https://shop.example.test:443/account?id=7");

console.log(target.origin); // https://shop.example.test
console.log(target.protocol); // https:
console.log(target.hostname); // shop.example.test
console.log(target.port); // chuỗi rỗng vì dùng port mặc định
```

Một số scheme và ngữ cảnh tạo ra opaque origin hoặc có hành vi riêng. Tài liệu `data:` và iframe sandbox không có `allow-same-origin` thường có opaque origin; khi được tuần tự hóa, origin có thể hiển thị là chuỗi `null`. Không được coi chuỗi `null` là một website đáng tin cậy. Origin của `file:` có khác biệt theo trình duyệt và không nên dùng làm nền tảng cho kết luận bảo mật của ứng dụng web production.

## Phân biệt origin, site và phạm vi cookie

Origin và site phục vụ những mục đích khác nhau. Origin dùng cho SOP và CORS. Site được trình duyệt dùng trong một số chính sách như `SameSite` cookie và Fetch Metadata; khái niệm schemeful site hiện xét scheme cùng registrable domain theo Public Suffix List. Vì vậy, hai subdomain HTTPS có thể khác origin nhưng cùng site.

Ví dụ:

- `https://app.example.test` và `https://evil.example.test` khác origin.
- Hai địa chỉ này thường cùng schemeful site vì cùng registrable domain `example.test`.
- `https://app.example.test` và `http://app.example.test` khác origin và khác schemeful site.
- `https://example.test` và `https://example.test.attacker.invalid` khác host và khác site.

Cookie cũng có phạm vi riêng. Cookie host-only chỉ được gửi tới host đã đặt cookie; cookie có thuộc tính `Domain=example.test` có thể được gửi tới các subdomain phù hợp. `Path`, `Secure`, `HttpOnly`, thời hạn và `SameSite` tiếp tục giới hạn hành vi. Cookie không bị ràng buộc theo port như origin. Vì vậy, hai ứng dụng chạy trên hai port khác nhau của cùng host có thể có origin khác nhau nhưng vẫn chia sẻ cookie phù hợp với host/path.

| Cơ chế | Ranh giới chính | Điều cần nhớ khi kiểm thử |
|---|---|---|
| SOP/CORS | Origin: scheme, host, port | Subdomain và port khác nhau là origin khác |
| SameSite | Site theo quy tắc trình duyệt | Subdomain có thể cùng site dù khác origin |
| Cookie Domain | Host/domain và path | Cookie Domain có thể được gửi tới nhiều subdomain; cookie không cô lập theo port |
| `localStorage` | Origin | Khác scheme, host hoặc port tạo vùng lưu trữ riêng |
| `sessionStorage` | Origin và browsing context/top-level context | Không suy luận phạm vi chỉ từ domain |

Không dùng cụm “cùng domain” thay cho “cùng origin”. Khi viết test, ghi đầy đủ scheme, host và port của từng trang để tránh nhầm lẫn.

## Same-Origin Policy cần bảo vệ điều gì?

SOP là tập hợp quy tắc trình duyệt giới hạn cách một tài liệu hoặc script từ origin này tương tác với tài nguyên của origin khác. Với tài liệu web, SOP ngăn trang ở origin khác đọc tùy ý DOM, dữ liệu lưu trữ và nhiều kết quả từ ứng dụng đích.

SOP không có nghĩa trình duyệt chặn mọi request cross-origin. Một trang có thể gửi một số request hoặc nhúng tài nguyên cross-origin, nhưng việc đọc response hoặc tương tác với nội dung thường bị giới hạn. Đây là lý do cần phân biệt ba hành vi:

- **Gửi request:** trình duyệt có thể gửi request cross-origin trong một số ngữ cảnh như form, image hoặc navigation.
- **Đọc response:** JavaScript chỉ đọc được response khi chính sách phù hợp, chẳng hạn CORS, cho phép.
- **Truy cập DOM hoặc storage:** script từ origin khác không được tùy ý đọc DOM, `localStorage` hoặc `sessionStorage` của trang đích. Cookie có cơ chế phạm vi riêng theo host/domain, path và thuộc tính cookie; cookie không được cô lập theo port như origin.

SOP cũng có ngoại lệ và API giao tiếp được thiết kế có chủ đích. Ví dụ, `postMessage` cho phép cửa sổ gửi thông điệp cho nhau; CORS cho phép server công bố một số response cho origin được chọn; các cơ chế embed và sandbox tạo ranh giới riêng. Origin boundary test phải kiểm tra cả đường bị cấm và đường được cho phép.

## Chuẩn bị môi trường kiểm thử

### Xây dựng các origin kiểm thử

Tạo các ứng dụng hoặc host giả lập trong môi trường local/QA:

| Vai trò | Origin ví dụ | Mục đích |
|---|---|---|
| Ứng dụng chính | `https://app.example.test` | Chứa trang, API và dữ liệu thử nghiệm |
| Ứng dụng tin cậy được cấp CORS | `https://portal.example.test` | Kiểm tra quyền đọc cross-origin hợp lệ |
| Origin cùng site nhưng khác origin | `https://untrusted.example.test` | Kiểm tra ranh giới giữa các subdomain |
| Origin hoàn toàn khác site | `https://attacker.test` | Kiểm tra request và truy cập cross-site |
| Origin khác port | `https://app.example.test:8443` | Kiểm tra cô lập theo port |

Các host cần được cấu hình để trỏ tới môi trường thử nghiệm và dùng HTTPS khi cần kiểm tra cookie `Secure` hoặc hành vi production-like. Có thể dùng chứng chỉ local được trình duyệt tin cậy. Không thay DNS, chứng chỉ hoặc cấu hình cookie của hệ thống thật để phục vụ bài thực hành.

Tạo dữ liệu giả lập như một hồ sơ người dùng và một giá trị bí mật chỉ dùng để xác nhận việc đọc bị chặn. Không đưa thông tin cá nhân, token hay secret thật vào trang thử nghiệm.

### Công cụ quan sát

- **DevTools Console:** kiểm tra lỗi SOP, CORS, `postMessage` và exception.
- **Network:** xem request, response, redirect, preflight, request initiator và header.
- **Application/Storage:** kiểm tra cookie và vùng lưu trữ theo origin.
- **Sources:** đặt breakpoint tại nơi gửi/nhận message hoặc gọi API.
- **Browser automation:** chạy lặp lại cùng một ma trận trên các browser engine được hỗ trợ.

Ghi lại phiên bản trình duyệt, URL đầy đủ, trạng thái đăng nhập giả lập, cấu hình cookie và cấu hình CORS. Kết quả có thể khác khi dùng browser engine, privacy mode hoặc chính sách chặn third-party cookie khác nhau.

## Kiểm thử Same-Origin Policy

### Kiểm tra truy cập DOM giữa hai origin

Tạo một trang `app.example.test` có nội dung giả lập:

```html
<p id="private-marker">APP-ONLY-TEST-DATA</p>
```

Từ trang `attacker.test`, mở ứng dụng trong iframe và thử đọc DOM:

```html
<iframe id="target" src="https://app.example.test/profile"></iframe>
<script>
  const frame = document.querySelector("#target");

  frame.addEventListener("load", () => {
    try {
      const marker = frame.contentWindow.document.querySelector("#private-marker");
      console.log("Marker:", marker?.textContent);
    } catch (error) {
      console.log("DOM access blocked:", error.name);
    }
  });
</script>
```

Kết quả mong đợi: script ở `attacker.test` không đọc được DOM của tài liệu `app.example.test`. Trình duyệt thường ném `SecurityError` khi truy cập thuộc tính hoặc phương thức bị SOP cấm. Việc iframe tải được trang không đồng nghĩa trang cha được quyền đọc nội dung của iframe.

Lặp lại với trang cùng origin để xác nhận ca dương tính. Nếu test chỉ chứng minh truy cập cross-origin bị chặn mà không xác nhận truy cập cùng origin hoạt động, có thể fixture hoặc selector đang sai.

### Kiểm tra localStorage và sessionStorage

Tại origin ứng dụng, lưu một giá trị giả lập:

```js
localStorage.setItem("origin-boundary-marker", "APP-ONLY-TEST-DATA");
sessionStorage.setItem("session-marker", "CURRENT-TAB-TEST");
```

Từ một origin khác, thử đọc cùng key:

```js
try {
  console.log(localStorage.getItem("origin-boundary-marker"));
} catch (error) {
  console.log("Storage access blocked:", error.name);
}
```

Không thể truy cập trực tiếp storage của origin khác qua đối tượng `localStorage` của trang hiện tại. Khi đọc cùng key từ origin khác, kết quả thường là `null` vì origin đó có vùng lưu trữ riêng; không nhất thiết phát sinh exception. Mỗi origin có vùng lưu trữ riêng theo quy tắc của trình duyệt. Kiểm tra cả biến thể đổi scheme, host và port. Sau thử nghiệm, xóa marker để tránh ảnh hưởng ca test tiếp theo.

### Kiểm tra truy cập window và location

Một cửa sổ có thể giữ tham chiếu tới `window` của cửa sổ khác, nhưng SOP giới hạn thuộc tính có thể đọc hoặc sửa. Một số thuộc tính điều hướng như `location` có quy tắc đặc biệt; không suy luận rằng truy cập được một thuộc tính có nghĩa là được đọc toàn bộ document.

Kiểm tra các trường hợp:

- Trang cha đọc `contentWindow.document` của iframe khác origin: phải bị chặn.
- Trang khác origin đọc `window.location.href` của cửa sổ đích: không được đọc tùy ý.
- Trang khác origin điều hướng cửa sổ theo các quy tắc được trình duyệt cho phép: có thể có hành vi khác với đọc URL.
- Cửa sổ cùng origin truy cập DOM: được phép trong điều kiện tài liệu và sandbox tương ứng.

Khi ghi nhận lỗi, lưu exception name và thao tác gây lỗi. Không chụp hoặc chia sẻ nội dung tài liệu riêng tư để chứng minh SOP hoạt động.

## Kiểm thử CORS và quyền đọc response

CORS là cơ chế server dùng để cho phép một origin khác đọc response thông qua trình duyệt. Đây là một lớp cho phép có kiểm soát bên cạnh SOP. CORS không thay thế xác thực, phân quyền hoặc CSRF protection.

### Simple request và preflight

Một số request cross-origin có thể được gửi mà không cần preflight, ví dụ form HTML truyền thống hoặc request đáp ứng điều kiện simple request. Các request dùng method/header/content type ngoài tập được phép có thể kích hoạt preflight `OPTIONS`.

Kiểm tra một API đọc dữ liệu từ `portal.example.test`:

```js
const response = await fetch("https://app.example.test/api/public-info", {
  mode: "cors",
  credentials: "omit"
});

console.log("status:", response.status);
console.log("body:", await response.json());
```

Nếu server cho phép origin, response có thể được JavaScript đọc. Từ `attacker.test`, cùng request phải bị trình duyệt chặn đọc khi origin đó không nằm trong allowlist. Hãy quan sát Network để phân biệt request đã gửi nhưng response không được expose với request bị dừng ở preflight.

### Kiểm tra preflight

Một request dùng custom header có thể kích hoạt preflight:

```js
await fetch("https://app.example.test/api/profile", {
  method: "PATCH",
  mode: "cors",
  headers: {
    "Content-Type": "application/json",
    "X-Test-Client": "origin-boundary-lab"
  },
  body: JSON.stringify({ displayName: "Test User" })
});
```

Trong Network, tìm request `OPTIONS` và kiểm tra:

- `Access-Control-Allow-Origin` có đúng origin thử nghiệm không.
- `Access-Control-Allow-Methods` có chứa method cần thiết không.
- `Access-Control-Allow-Headers` chỉ cho phép header cần thiết không.
- Server xử lý preflight nhất quán và không thực hiện tác dụng phụ trong `OPTIONS`.
- Khi origin không được phép, browser không gửi request chính nếu preflight thất bại.

Preflight không phải cơ chế xác thực. Một client không phải trình duyệt có thể tự tạo request; server vẫn phải xác thực và phân quyền. Ngoài ra, request đơn giản không cần preflight có thể tới server dù JavaScript của origin gửi request không đọc được response.

### Kiểm tra credentials

Nếu API cần cookie hoặc HTTP authentication, client có thể dùng `credentials: "include"` trong `fetch()`. Server phải trả `Access-Control-Allow-Credentials: true` và một `Access-Control-Allow-Origin` cụ thể; wildcard `*` không hợp lệ cho response credentialed.

Kiểm thử các trường hợp:

1. Origin được cho phép, credentials được bật và cookie phù hợp được gửi.
2. Origin không được phép, response không được expose cho script.
3. Server trả `Access-Control-Allow-Origin: *` cùng credentials: browser không chấp nhận cấu hình này.
4. Server phản chiếu mọi giá trị `Origin`: cấu hình phải bị xem là lỗi nếu không có allowlist và kiểm tra chính xác.
5. Cookie bị chặn do `SameSite` hoặc chính sách third-party cookie: phân biệt lỗi cookie với lỗi CORS.

Khi phản hồi thay đổi theo `Origin`, server nên trả `Vary: Origin` để cache không dùng nhầm response của origin này cho origin khác. Kiểm tra cache CDN hoặc reverse proxy nếu response CORS có thể được cache.

### Kiểm tra allowlist origin

Allowlist phải so sánh origin đầy đủ, không dùng phép so chuỗi con:

```js
const allowedOrigins = new Set([
  "https://portal.example.test",
  "https://admin.example.test"
]);

function isAllowedOrigin(value) {
  if (typeof value !== "string") return false;

  try {
    const parsed = new URL(value);
    return parsed.origin === value && allowedOrigins.has(parsed.origin);
  } catch {
    return false;
  }
}
```

Đây là ví dụ minh họa cho origin đã được parse thành dạng chuẩn; khi xử lý header `Origin`, cần xét trường hợp giá trị `null`, header thiếu và quy tắc chuẩn hóa của server/framework. Không cho phép origin bằng cách kiểm tra `includes("example.test")`, `endsWith("example.test")` hoặc regex không ràng buộc ranh giới host. Các chuỗi như `https://example.test.attacker.invalid` hoặc `https://example.test@attacker.invalid` không được xem là origin tin cậy.

Không xây dựng allowlist từ `Host`, `X-Forwarded-Host` hoặc `Origin` của request mà không có cấu hình proxy tin cậy và danh sách được quản trị. Origin là tín hiệu nguồn request, không phải danh tính người dùng và không phải bằng chứng xác thực.

## Kiểm tra cross-origin isolation headers

Một số response header bổ sung kiểm soát việc cửa sổ mở các trang khác, nhúng tài nguyên cross-origin và tạo môi trường cross-origin isolated. Chúng bổ sung cho SOP/CORS, nhưng mỗi header có mục đích riêng.

| Header | Mục đích | Điều cần kiểm thử |
|---|---|---|
| `Cross-Origin-Opener-Policy` (COOP) | Kiểm soát việc tài liệu chia sẻ browsing context group và quan hệ opener với cửa sổ khác origin | Popup cross-origin có còn giữ quan hệ `window.opener` hay không theo chính sách |
| `Cross-Origin-Embedder-Policy` (COEP) | Giới hạn tài nguyên cross-origin được nhúng nếu tài nguyên không được cấp quyền phù hợp qua CORS/CORP | Script, worker, image và tài nguyên phụ thuộc có đáp ứng chính sách không |
| `Cross-Origin-Resource-Policy` (CORP) | Cho phép chủ tài nguyên giới hạn nơi có thể nhúng response trong ngữ cảnh `no-cors` | Tài nguyên `same-origin`, `same-site` hoặc `cross-origin` có được tải đúng chính sách không |

COOP thường được cấu hình thành `same-origin` để tách browsing context khỏi trang cross-origin. Các giá trị khác như `same-origin-allow-popups` có hành vi khác và cần chọn theo yêu cầu tích hợp. COEP có các chế độ như `require-corp` và `credentialless`; tài nguyên cross-origin cần được tải qua CORS hoặc đáp ứng chính sách CORP tương ứng. CORP có các giá trị phổ biến `same-origin`, `same-site` và `cross-origin`.

Khi cần các tính năng yêu cầu cross-origin isolation, kiểm tra cả COOP và COEP cùng điều kiện secure context và hỗ trợ của trình duyệt. Có thể quan sát `window.crossOriginIsolated` trong Console:

```js
console.log("crossOriginIsolated:", window.crossOriginIsolated);
```

Kết quả `true` cho biết tài liệu đang ở môi trường cross-origin isolated theo điều kiện trình duyệt; nó không chứng minh mọi endpoint, cookie hoặc API đã được bảo vệ đúng. Kết quả `false` cần được điều tra qua response header của tài liệu chính, worker và tài nguyên nhúng.

Ma trận kiểm thử nên gồm:

- Popup cùng origin và khác origin khi COOP thay đổi; xác minh quan hệ opener và điều hướng theo chính sách.
- Tải script, worker, font và image cross-origin khi bật COEP; xác minh tài nguyên hợp lệ vẫn tải và tài nguyên không đáp ứng chính sách bị chặn.
- Nhúng tài nguyên với CORP `same-origin`, `same-site` và `cross-origin` từ từng nguồn tương ứng.
- Xác nhận response header có mặt trên mọi route và redirect cần thiết, không chỉ trang chủ.
- Kiểm tra log Console/Network để phân biệt lỗi CORS với lỗi COEP/CORP.

Không bật COOP/COEP một cách máy móc nếu ứng dụng phụ thuộc popup thanh toán, đăng nhập liên kết, iframe hoặc tài nguyên bên thứ ba. Kiểm tra các luồng tích hợp trong môi trường QA và chọn chính sách phù hợp với kiến trúc.

## Kiểm thử postMessage

`window.postMessage()` là API được thiết kế để trao đổi dữ liệu giữa các cửa sổ khác origin, chẳng hạn trang cha và iframe. Vì SOP hạn chế đọc DOM trực tiếp, `postMessage` tạo kênh giao tiếp có chủ đích. Cả bên gửi lẫn bên nhận phải xác minh đích, nguồn và cấu trúc thông điệp.

### Kiểm tra phía gửi

Dùng `targetOrigin` cụ thể thay vì ký tự `*` khi biết origin của cửa sổ nhận:

```js
const frame = document.querySelector("#trusted-frame");

frame.contentWindow.postMessage(
  { type: "REQUEST_STATUS", requestId: "test-001" },
  "https://portal.example.test"
);
```

`targetOrigin` yêu cầu trình duyệt chỉ gửi message khi cửa sổ đích có origin phù hợp tại thời điểm gửi. Dùng `*` có thể khiến dữ liệu được gửi tới cửa sổ đã bị điều hướng sang origin khác. Với dữ liệu nhạy cảm, phải dùng origin đích cụ thể và kiểm soát vòng đời cửa sổ.

### Kiểm tra phía nhận

Listener cần kiểm tra `event.origin`, `event.source` và schema của `event.data`:

```js
const trustedOrigin = "https://app.example.test";
const expectedWindow = window.parent;

window.addEventListener("message", (event) => {
  if (event.origin !== trustedOrigin) return;
  if (event.source !== expectedWindow) return;

  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  if (data.type !== "SET_THEME") return;
  if (data.theme !== "light" && data.theme !== "dark") return;

  applyTheme(data.theme);
});
```

Không chỉ kiểm tra `event.origin` mà bỏ qua `event.source` nếu ứng dụng cần giao tiếp với một iframe hoặc cửa sổ cụ thể. Không tin `event.data` chỉ vì origin đúng; validate kiểu dữ liệu, kích thước, các trường được phép và trạng thái nghiệp vụ. Không dùng message để cấp quyền vượt qua kiểm tra phía máy chủ.

### Ma trận kiểm thử message

- Message từ origin tin cậy và đúng cửa sổ: được xử lý nếu schema hợp lệ.
- Message từ origin khác: bị bỏ qua hoặc từ chối.
- Message từ một cửa sổ khác nhưng cùng origin: bị từ chối nếu không phải nguồn dự kiến.
- Message có `type` lạ, trường thiếu, kiểu dữ liệu sai hoặc payload quá lớn: bị từ chối.
- Message có chuỗi HTML/script: được xem là dữ liệu; không chèn vào DOM bằng HTML thô.
- Cửa sổ đích bị điều hướng trước khi gửi: dữ liệu nhạy cảm không được gửi tới origin mới.

Nếu phải giao tiếp với opaque origin, `event.origin` có thể là `"null"`. Không dùng riêng chuỗi này làm allowlist vì nhiều tài liệu opaque origin khác nhau có thể cùng được tuần tự hóa thành `null`. Cần thiết kế giao thức khác phù hợp với sandbox, xác minh `event.source`, giới hạn dữ liệu và dùng một kênh capability có vòng đời rõ ràng. Tránh gửi bí mật tới opaque origin chỉ dựa trên `targetOrigin: "*"`.

## Kiểm thử iframe sandbox và opaque origin

Iframe có thể dùng thuộc tính `sandbox` để giới hạn script, form, navigation và các khả năng khác. Nếu sandbox không có `allow-same-origin`, tài liệu bên trong thường được cấp opaque origin, ngay cả khi URL của nó thuộc cùng host với trang cha.

Ví dụ:

```html
<iframe
  id="isolated-preview"
  sandbox="allow-scripts"
  src="https://app.example.test/preview">
</iframe>
```

Kiểm thử các điểm sau:

- Script bên trong iframe không đọc DOM hoặc storage của trang cha.
- Trang cha không được tùy ý đọc DOM của tài liệu sandbox opaque origin.
- Form, popup, navigation và download tuân theo các quyền sandbox đã cấp.
- Bỏ `allow-same-origin` và thêm thuộc tính này tạo ra khác biệt origin cần được ghi nhận.
- Không kết hợp `allow-scripts` và `allow-same-origin` cho nội dung cùng origin không đáng tin cậy nếu mô hình đó cho phép nội dung phá bỏ sandbox theo cách không mong muốn.

`allow-same-origin` không tự làm iframe cùng origin với trang cha nếu URL thực tế khác origin; nó chỉ giữ origin thật của tài liệu thay vì biến nó thành opaque origin. Cần kiểm tra cả URL của iframe và tập token sandbox.

Với nội dung do người dùng tải lên hoặc preview HTML, ưu tiên origin riêng biệt và sandbox chặt chẽ. Không dựa vào một trang preview cùng origin với ứng dụng chính rồi kỳ vọng sandbox tự bảo vệ mọi dữ liệu.

## Các origin đặc biệt và trường hợp biên

Một ma trận origin boundary nên bao gồm các trường hợp không phải URL HTTPS thông thường:

| Trường hợp | Hành vi cần quan sát | Rủi ro khi thiết kế sai |
|---|---|---|
| `data:` document | Thường có opaque origin | Coi `null` là nguồn tin cậy |
| Iframe sandbox không `allow-same-origin` | Có opaque origin | Gửi dữ liệu nhạy cảm tới frame mà không xác minh kênh |
| `blob:` URL | Origin thường kế thừa từ môi trường tạo blob theo quy tắc trình duyệt | Giả định mọi blob URL đều có cùng quyền hoặc mọi blob đều opaque |
| `file:` URL | Hành vi origin có thể khác giữa trình duyệt | Dùng file local để kết luận thay cho HTTP(S) deployment |
| Redirect cross-origin | URL đích và hành vi request thay đổi theo redirect chain | Chỉ kiểm tra origin ban đầu, bỏ qua đích cuối |
| IDN/punycode | Host được chuẩn hóa theo quy tắc URL | So sánh hostname Unicode/ASCII không nhất quán |
| Port mặc định | Có thể được chuẩn hóa và lược bỏ | Tạo false positive do so chuỗi URL thô |

Với redirect, kiểm tra từng bước trong Network và xác định response cuối cùng có được expose hay không. Không giả định redirect làm mất mọi thông tin nguồn hoặc tự động cấp quyền cho origin đích. Không dựa vào `document.domain` để nới lỏng ranh giới giữa subdomain; API này đã bị deprecated và có tương tác phức tạp với các cơ chế cô lập hiện đại. Ưu tiên giao tiếp có chủ đích như `postMessage` với kiểm tra nguồn chặt chẽ. Với các trường hợp đặc biệt, dùng URL API của trình duyệt và test trên các browser engine mà sản phẩm hỗ trợ.

## Kiểm thử cookie và storage qua ranh giới origin

Origin boundary test cần xác nhận rằng các vùng dữ liệu được cô lập đúng và cookie chỉ được gửi theo phạm vi đã cấu hình.

1. Đặt marker trong `localStorage` ở `app.example.test` và thử đọc từ `portal.example.test`, `evil.example.test` và port khác.
2. Tạo cookie host-only ở `app.example.test`, sau đó kiểm tra request tới subdomain.
3. Tạo cookie với `Domain=example.test` trong lab và xác minh các subdomain nào nhận cookie.
4. So sánh cookie `SameSite` khi điều hướng cross-site và khi request same-site từ subdomain khác origin.
5. Xác minh cookie phiên có `Secure`, `HttpOnly` và `SameSite` theo yêu cầu.
6. Xóa dữ liệu thử nghiệm sau mỗi ca và xác nhận profile không còn marker.

Không đưa session cookie vào script kiểm thử hoặc log. DevTools có thể hiển thị cookie cho người có quyền truy cập profile; che giá trị khi chụp bằng chứng. Cần nhớ rằng cookie `HttpOnly` không đọc được qua `document.cookie`, nhưng vẫn có thể được trình duyệt gửi trong request phù hợp.

## Ma trận Origin boundary test

Ma trận dưới đây là bộ khung cho một ứng dụng có trang, API, iframe và thông điệp giữa cửa sổ:

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| ORIGIN-01 | Cùng scheme, host, port; khác path | SOP cho phép truy cập trong phạm vi origin |
| ORIGIN-02 | Khác scheme | SOP chặn truy cập DOM/storage trực tiếp |
| ORIGIN-03 | Khác subdomain | SOP chặn truy cập trực tiếp; CORS chỉ mở response theo allowlist |
| ORIGIN-04 | Khác port | SOP xem là origin khác |
| ORIGIN-05 | Port mặc định và URL không ghi port | URL được chuẩn hóa về cùng origin khi phù hợp |
| ORIGIN-06 | Origin không nằm trong CORS allowlist | Script không đọc được response cross-origin |
| ORIGIN-07 | Origin được allowlist và request hợp lệ | Chỉ response được phép mới được expose |
| ORIGIN-08 | CORS credentials cùng wildcard origin | Browser từ chối expose response theo quy tắc CORS |
| ORIGIN-09 | `postMessage` từ origin lạ | Listener bỏ qua hoặc từ chối |
| ORIGIN-10 | `postMessage` đúng origin nhưng sai `source` hoặc schema | Listener từ chối |
| ORIGIN-11 | Iframe sandbox opaque origin | Không truy cập DOM trực tiếp; không tin `event.origin === "null"` |
| ORIGIN-12 | Cookie Domain, SameSite và host-only | Cookie chỉ được gửi theo phạm vi và ngữ cảnh đã cấu hình |
| ORIGIN-13 | Redirect sang origin khác | Quyền đọc và hành vi cuối cùng tuân theo SOP/CORS của chuỗi redirect |
| ORIGIN-14 | `data:`, `blob:` hoặc `file:` | Hành vi đặc biệt được ghi nhận riêng theo browser |
| ORIGIN-15 | COOP/COEP/CORP | Quan hệ opener và tài nguyên nhúng tuân theo response policy |

Với mỗi ca, lưu URL nguồn và đích, origin kỳ vọng, request/response liên quan, exception hoặc kết quả đọc, cookie có được gửi hay không và trạng thái dữ liệu. Đánh dấu rõ ca nào là SOP, CORS, `postMessage`, sandbox, cookie hay storage để không gán nhầm nguyên nhân.

## Tự động hóa kiểm thử bằng Playwright

Browser automation giúp lặp lại ca kiểm thử với nhiều origin và browser engine. Ví dụ sau minh họa kiểm tra DOM cross-origin và cùng origin; thay host, route và marker theo lab:

```js
import { test, expect } from "@playwright/test";

test("trang khác origin không đọc được DOM của ứng dụng", async ({ page }) => {
  await page.goto("https://attacker.test/iframe-check");

  const result = await page.evaluate(async () => {
    const frame = document.createElement("iframe");
    frame.src = "https://app.example.test/profile";
    document.body.append(frame);

    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("iframe load timeout")), 5000);
      frame.addEventListener("load", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
    });

    try {
      return frame.contentWindow.document.querySelector("#private-marker")?.textContent ?? "missing";
    } catch (error) {
      return error.name;
    }
  });

  expect(result).toBe("SecurityError");
});
```

Khi viết suite thực tế, nên dùng `page.on("console")` và `page.on("pageerror")` để thu thập lỗi có liên quan, đồng thời kiểm tra rằng ca cùng origin có thể đọc marker. Chờ iframe load có timeout để test không treo nếu host thử nghiệm không phản hồi. Nếu browser engine biểu diễn exception khác nhau, xác nhận điều kiện bảo mật qua hành vi bị chặn và bổ sung assertion phù hợp với engine đó.

Đối với CORS, kiểm tra cả request `OPTIONS`, request chính và khả năng JavaScript đọc body. Đối với `postMessage`, kiểm tra thông điệp từ origin tin cậy và giả mạo. Đối với cookie, dùng browser context riêng và quan sát request thực tế thay vì chỉ đọc cookie jar.

## Đọc kết quả và báo cáo phát hiện

Một phát hiện có ý nghĩa khi chứng minh được dữ liệu hoặc quyền vượt qua ranh giới dự kiến. Ví dụ:

- Trang ở origin khác đọc được marker riêng tư trong DOM hoặc storage.
- CORS cho phép origin ngoài allowlist đọc response chứa dữ liệu theo phiên.
- CORS phản chiếu origin tùy ý và cho phép credentials.
- Listener `message` chấp nhận origin hoặc cửa sổ không đáng tin cậy, dẫn tới thao tác nhạy cảm.
- Iframe sandbox được cấp quyền vượt quá nhu cầu hoặc nội dung không tin cậy chạy trong origin chính.
- Cookie được chia sẻ tới subdomain không đáng tin cậy do cấu hình `Domain` quá rộng.

Khi báo cáo, nêu:

1. Origin nguồn và origin đích, bao gồm scheme, host và port.
2. Trạng thái xác thực và dữ liệu giả lập được dùng.
3. Hành động tái hiện cùng request, redirect hoặc message liên quan.
4. Quy tắc SOP/CORS/cookie/sandbox dự kiến và hành vi thực tế.
5. Dữ liệu có thể đọc, thao tác có thể thực hiện hoặc quyền bị vượt qua.
6. Bằng chứng đã che token, cookie và dữ liệu nhạy cảm.

Không báo cáo chỉ dựa trên một dòng Console hoặc header riêng lẻ. Kết luận cần chỉ ra tác động thực tế, khả năng tái hiện và điều kiện cần thiết. Nếu browser chặn một bước, xác định chính xác bước bị chặn: request không gửi, response không được expose hay DOM/storage access bị từ chối.

## Thực hành

Tạo ba origin trong môi trường thử nghiệm: `https://app.example.test`, `https://portal.example.test` và `https://evil.example.test`. Đặt một marker trong DOM và storage của ứng dụng chính. Cấu hình CORS chỉ cho `portal.example.test` đọc một endpoint dữ liệu giả lập.

Thực hiện các yêu cầu:

1. Xác nhận `portal.example.test` không đọc trực tiếp DOM của `app.example.test` dù được CORS cho phép đọc API.
2. Xác nhận `portal.example.test` đọc được endpoint API đã được allowlist.
3. Xác nhận `evil.example.test` không đọc được endpoint đó dù cùng site với ứng dụng chính.
4. Thử đổi port và scheme; kiểm tra SOP và vùng storage.
5. Gửi `postMessage` từ origin hợp lệ, origin lạ và cửa sổ sai; xác nhận listener chỉ xử lý đúng message.
6. Nhúng iframe sandbox không có `allow-same-origin`; quan sát opaque origin và kiểm tra quyền truy cập.
7. So sánh cookie host-only, cookie Domain và `SameSite` trong các ngữ cảnh khác nhau.

Hoàn thiện bảng kết quả gồm origin nguồn, origin đích, thao tác, kỳ vọng, thực tế và bằng chứng. Xóa marker, cookie thử nghiệm và dữ liệu trong browser context sau khi hoàn tất.

## Ghi nhớ

- Origin gồm scheme, host và port; path không tham gia so sánh.
- Cùng site không đồng nghĩa cùng origin. Subdomain có thể khác origin nhưng cùng site.
- SOP giới hạn việc đọc dữ liệu và truy cập DOM; nó không chặn mọi request cross-origin.
- CORS cho phép một số script đọc response theo chính sách server; nó không thay thế xác thực, phân quyền hoặc CSRF protection.
- `postMessage` cần xác minh `event.origin`, `event.source` và schema dữ liệu.
- Opaque origin có thể hiển thị thành `null`; không tin chuỗi này như một origin được allowlist.
- Cookie có phạm vi domain/path và thuộc tính riêng; cookie không được cô lập theo port như origin.
- Kiểm thử cả đường bị chặn và đường được cho phép, dùng bằng chứng về hành vi thực tế và dữ liệu giả lập.
