# Client-side trust

Client-side trust là cách xác định dữ liệu, trạng thái và hành động nào trong trình duyệt có thể được tin cậy, ở mức độ nào và trong phạm vi nào. Một ứng dụng web chạy trên thiết bị do người dùng kiểm soát: người dùng có thể mở DevTools, sửa JavaScript, thay đổi DOM, gọi API trực tiếp, phát lại request hoặc chỉnh dữ liệu trong storage. Extension, script bên thứ ba và nội dung từ website cũng có thể tác động đến trang.

Vì vậy, mọi dữ liệu đến từ browser phải được xem là đầu vào không tin cậy khi server dùng nó để quyết định quyền truy cập hoặc thay đổi dữ liệu. Giao diện có thể ẩn nút, kiểm tra form và hiển thị trạng thái để hỗ trợ trải nghiệm; quyết định bảo mật cuối cùng phải được xác minh ở thành phần server có thẩm quyền.

Trong module bảo mật trình duyệt, chủ đề này liên kết trực tiếp với origin, Same-Origin Policy, CORS, cookie, XSS, CSRF, CSP, Trusted Types, service worker và extension. Hiểu đúng ranh giới tin cậy giúp tránh hai lỗi phổ biến: tin rằng code phía client không thể bị sửa, hoặc cho rằng cùng origin đồng nghĩa mọi dữ liệu từ trang đều đáng tin.

## Mô hình tin cậy của ứng dụng web

Một ứng dụng web thường có nhiều vùng với quyền và trách nhiệm khác nhau:

~~~mermaid
flowchart LR
    U[Người dùng và thiết bị] --> B[Browser]
    E[Extension / script bên thứ ba] --> B
    B -->|HTTPS request| S[Application server]
    S --> A[Authentication và authorization]
    A --> D[(Database / dịch vụ nội bộ)]
    B -->|HTML, CSS, JavaScript| UI[DOM và giao diện]
    UI -->|Dữ liệu và thao tác| B
~~~

- **Người dùng và thiết bị:** người dùng kiểm soát thiết bị, browser profile, DevTools và các extension được cài. Thiết bị có thể bị malware hoặc phần mềm quản trị can thiệp.
- **Browser:** thực thi Same-Origin Policy, CORS, CSP, cookie rules và các cơ chế sandbox theo thiết kế. Browser tạo ranh giới hữu ích, nhưng không biến mọi dữ liệu trong page thành dữ liệu đáng tin.
- **JavaScript và DOM của ứng dụng:** code frontend có thể kiểm tra đầu vào và trạng thái để hỗ trợ UI. Người dùng có thể sửa code, gọi hàm khác hoặc bỏ qua các kiểm tra đó.
- **Extension và script bên thứ ba:** có thể có quyền khác với page, hoặc được tải vào trang theo cấu hình. Cần xem chúng là thành phần có rủi ro riêng.
- **Server:** xác thực danh tính, kiểm tra quyền, xác thực dữ liệu và quyết định thao tác có được phép hay không.
- **Database và dịch vụ nội bộ:** chỉ nhận các thao tác đã qua kiểm tra ở lớp server; không nên phụ thuộc vào một cờ do browser gửi lên.

Mô hình này không có nghĩa browser hoàn toàn không đáng tin trong mọi khía cạnh. Browser thực thi các chính sách bảo mật của nó, nhưng ứng dụng không thể giả định người dùng không thay đổi được trạng thái phía client. Hãy xác định chính xác ranh giới: điều gì do browser đảm bảo, điều gì do server phải xác minh và điều gì chỉ là tiện ích giao diện.

## Nguyên tắc: client có thể yêu cầu, server quyết định

Client có thể gửi yêu cầu như “xem hóa đơn”, “cập nhật hồ sơ”, “tạo giao dịch” hoặc “xóa tài khoản”. Server phải tự xác định người gọi là ai, có quyền thực hiện hành động đó trên tài nguyên cụ thể hay không và dữ liệu có hợp lệ không.

Ví dụ không an toàn: frontend gửi `isAdmin` và server tin vào giá trị đó.

~~~javascript
// Không an toàn: client tự khai báo quyền của mình.
await fetch('/api/users/123/delete', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ isAdmin: true })
});
~~~

Người dùng có thể sửa request thành `isAdmin: true`, gọi API bằng curl hoặc gửi request từ một script khác. Server không được dùng trường này để cấp quyền.

Thiết kế đúng là server lấy danh tính từ credential đã xác minh, tải quyền từ nguồn có thẩm quyền và kiểm tra quyền trên tài nguyên:

~~~javascript
app.delete('/api/users/:userId', requireAuthenticatedUser, async (req, res) => {
  const target = await users.findById(req.params.userId);
  if (!target) return res.sendStatus(404);

  const canDelete = await authorization.can(
    req.user,
    'user:delete',
    target
  );

  if (!canDelete) return res.sendStatus(403);

  await users.delete(target.id);
  return res.sendStatus(204);
});
~~~

`requireAuthenticatedUser`, `users` và `authorization` là các thành phần giả định của ứng dụng. Điểm quan trọng là route tự xác minh danh tính và quyền trên đối tượng đích trước khi thay đổi dữ liệu. Không dùng ID do client gửi để suy ra người dùng được phép truy cập; ID chỉ xác định tài nguyên cần kiểm tra.

Mọi API nhạy cảm cần có authorization ở server, kể cả khi nút tương ứng chỉ hiển thị cho quản trị viên. Ẩn nút giúp giao diện dễ dùng hơn, nhưng không ngăn người dùng tự gọi endpoint.

## Những gì client có thể và không thể chứng minh

| Thành phần phía client | Có thể dùng cho | Không được dùng làm bằng chứng duy nhất cho |
|---|---|---|
| Ẩn/hiện nút theo role | Điều chỉnh giao diện | Quyền truy cập API hoặc tài nguyên |
| Form validation | Phản hồi nhanh cho người dùng | Dữ liệu hợp lệ hoặc an toàn ở server |
| `localStorage` / `sessionStorage` | Lưu tùy chọn và trạng thái không nhạy cảm | Role, giá, quyền sở hữu, token dài hạn hoặc trạng thái đã được phê duyệt |
| JavaScript route guard | Điều hướng và UX | Kiểm soát truy cập thực tế |
| JWT decode ở browser | Đọc claim để hiển thị giao diện | Chữ ký hợp lệ, token chưa hết hạn hoặc quyền đã được server xác nhận |
| CORS | Giới hạn JavaScript ở origin khác đọc response | Xác thực, phân quyền hoặc ngăn mọi request cross-site |
| CSP | Giảm một số đường tải/thực thi nội dung | Thay thế encode đầu ra hoặc kiểm tra quyền server-side |
| HTTPS | Bảo vệ dữ liệu trên đường truyền và xác thực server theo TLS | Chứng minh client hoặc thiết bị không bị xâm nhập |

Các biện pháp client vẫn có giá trị. Chúng giảm lỗi vô ý, cải thiện UX, hạn chế một số payload và giảm bề mặt tấn công. Điều cần tránh là nâng một kiểm tra tiện ích thành ranh giới bảo mật.

## Origin, Same-Origin Policy và ranh giới của page

Origin được xác định bởi bộ ba scheme, host và port. Hai URL chỉ cùng origin khi cả ba thành phần khớp. Ví dụ, `https://app.example.com` và `https://api.example.com` khác origin dù có thể cùng site; `http://app.example.com` và `https://app.example.com` cũng khác origin.

Same-Origin Policy giới hạn cách một document hoặc script tương tác với tài nguyên ở origin khác. CORS cho phép server khai báo một số origin được đọc response cross-origin. Các cơ chế này bảo vệ ranh giới giữa website, nhưng không xác nhận dữ liệu do chính page tạo ra là an toàn.

Ví dụ, một ứng dụng có thể đọc giá trị `displayName` từ DOM. Giá trị đó có thể đến từ dữ liệu người dùng, một script bên thứ ba hoặc một extension. Việc page và API cùng origin không chứng minh giá trị đã được validate. Server vẫn phải kiểm tra dữ liệu theo schema và ngữ cảnh sử dụng.

### CORS không phải authorization

Giả sử API trả `Access-Control-Allow-Origin: https://app.example.com`. Điều đó cho phép JavaScript từ origin được chỉ định đọc response theo chính sách CORS. Nó không có nghĩa request chỉ có thể được gửi từ origin đó, cũng không có nghĩa người dùng đã được xác thực hoặc có quyền với tài nguyên.

Server phải kiểm tra credential, quyền và dữ liệu trên mọi request. Đặc biệt, CORS không thay thế CSRF protection đối với endpoint dùng cookie tự động đính kèm. Một request cross-site có thể tạo side effect ngay cả khi JavaScript của trang tấn công không đọc được response.

## Dữ liệu từ client là dữ liệu không tin cậy

Các nguồn dữ liệu phía client cần được xem xét gồm:

- Query string, path parameter, fragment và URL do người dùng điều khiển.
- Form field, contenteditable, file metadata và dữ liệu clipboard.
- DOM attribute, text node, dataset và giá trị do script khác thêm vào.
- `postMessage`, extension messaging, BroadcastChannel và event payload.
- `localStorage`, `sessionStorage`, IndexedDB, Cache Storage và service worker cache.
- Response từ API, kể cả API cùng origin, nếu dữ liệu ban đầu do người dùng hoặc hệ thống bên ngoài cung cấp.
- Dữ liệu từ analytics, tag manager, widget, CDN và script bên thứ ba.

Server cần kiểm tra kiểu, độ dài, miền giá trị, quan hệ giữa các trường và quyền trên đối tượng. Frontend cũng nên validate để phản hồi sớm, nhưng server phải lặp lại kiểm tra vì client có thể bị bỏ qua.

Không phải mọi dữ liệu đều cần loại bỏ ký tự đặc biệt. Validation xác định dữ liệu có hợp lệ với nghiệp vụ không; encoding xử lý dữ liệu an toàn trong ngữ cảnh đầu ra; sanitization chỉ phù hợp khi sản phẩm cần chấp nhận một tập HTML hoặc markup có giới hạn. Trộn lẫn ba nhiệm vụ này dễ tạo lỗ hổng.

## DOM và client-side trust

JavaScript có thể sửa DOM theo nhiều cách. Các sink nguy hiểm như `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function` và script URL có thể biến dữ liệu không tin cậy thành HTML hoặc mã thực thi.

Nếu chỉ hiển thị văn bản, dùng API văn bản:

~~~javascript
const output = document.querySelector('#message');
output.textContent = userSuppliedMessage;
~~~

Không đưa dữ liệu không tin cậy vào HTML bằng nối chuỗi:

~~~javascript
// Không an toàn nếu userSuppliedMessage có markup hoặc thuộc tính sự kiện.
output.innerHTML = `<p>${userSuppliedMessage}</p>`;
~~~

Nếu cần hiển thị rich text, dùng sanitizer được duy trì, cấu hình allowlist rõ ràng và kiểm thử theo ngữ cảnh. CSP và Trusted Types có thể bổ sung lớp bảo vệ: CSP giới hạn nguồn script và hành vi thực thi; Trusted Types giúp kiểm soát một số DOM sink. Cả hai không thay thế việc xử lý dữ liệu đúng ngay tại source và sink.

### Script bên thứ ba và extension

Script bên thứ ba chạy trong page thường có quyền JavaScript của page và có thể đọc DOM mà page cho phép. Nếu script được cấp quyền hoặc tải động từ nguồn rộng, một thay đổi ở nhà cung cấp có thể tác động đến ứng dụng. Hãy giới hạn script, kiểm tra nhà cung cấp, dùng Subresource Integrity khi phù hợp và tránh cấp quyền không cần thiết.

Extension có thể có quyền riêng thông qua manifest và API browser. Một content script trong isolated world không chia sẻ biến JavaScript với page, nhưng vẫn thao tác trên DOM chung. Dữ liệu DOM mà extension đọc vẫn có thể do page kiểm soát. Không gửi dữ liệu nhạy cảm vào DOM với giả định chỉ extension đáng tin mới đọc được.

## Storage phía client không phải kho tin cậy

`localStorage`, `sessionStorage`, IndexedDB và Cache Storage được lưu trên thiết bị người dùng. Chúng có thể bị sửa qua DevTools, đọc bởi script cùng origin khi có quyền, xóa bởi người dùng hoặc bị tác động bởi extension và malware.

Không lưu các giá trị dùng để cấp quyền như:

- `isAdmin`, `isPaid`, `canDelete` hoặc role do client tự đặt.
- Giá sản phẩm, số dư, hạn mức, trạng thái thanh toán hoặc trạng thái phê duyệt làm căn cứ quyết định ở server.
- Secret dài hạn, private key hoặc mật khẩu ở dạng có thể đọc được.
- Session identifier hoặc refresh token dài hạn trong storage JavaScript nếu có kiến trúc an toàn hơn.

Có thể lưu tùy chọn giao diện, theme, bộ lọc, trạng thái onboarding hoặc cache dữ liệu không nhạy cảm. Khi đọc lại, ứng dụng vẫn phải xử lý dữ liệu có thể bị sửa hoặc hỏng; không đưa thẳng nội dung storage vào HTML.

### Ví dụ về role trong storage

~~~javascript
// Chỉ dùng để hiển thị UI; không phải kiểm soát quyền.
const displayRole = localStorage.getItem('displayRole');
adminMenu.hidden = displayRole !== 'admin';
~~~

Ngay cả khi người dùng sửa `displayRole` thành `admin`, API quản trị phải tiếp tục trả `403` nếu danh tính đã xác thực không có quyền. Frontend nên lấy role hiển thị từ response đã xác thực để đồng bộ giao diện, nhưng server vẫn kiểm tra quyền cho từng hành động và tài nguyên.

## Token, cookie và session

Ứng dụng thường dùng cookie phiên hoặc token để gắn request với danh tính. Việc lưu và gửi credential cần cân bằng giữa khả năng chống XSS, CSRF, khả năng thu hồi và trải nghiệm.

### Cookie phiên

Cookie phiên thường nên có các thuộc tính phù hợp:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`Secure` yêu cầu gửi cookie qua kết nối bảo mật; `HttpOnly` ngăn JavaScript đọc cookie qua `document.cookie`; `SameSite` giới hạn một số ngữ cảnh gửi cookie cross-site. Prefix `__Host-` yêu cầu cookie Secure, Path `/` và không có Domain trong browser hỗ trợ quy tắc này.

Cookie `HttpOnly` giảm khả năng lấy trực tiếp session cookie qua JavaScript, nhưng XSS vẫn có thể thực hiện hành động trong phiên người dùng bằng cách gửi request từ page. Vì vậy, vẫn cần phòng XSS, CSRF protection, kiểm tra quyền và xác minh thao tác nhạy cảm.

### Token phía client

Không dùng việc decode JWT ở browser làm bằng chứng token hợp lệ. Decode chỉ đọc payload; server hoặc resource server phải xác minh chữ ký, issuer, audience, thời hạn, thuật toán và các claim cần thiết theo cấu hình tin cậy. Không tin role hoặc permission chỉ vì chúng xuất hiện trong một JWT do client tự gửi nếu token chưa được xác minh.

Nếu dùng access token, giới hạn thời gian sống và scope, bảo vệ kênh truyền, tránh ghi token vào log hoặc URL và có kế hoạch thu hồi/rotation. Với ứng dụng web, mô hình Backend for Frontend (BFF) có thể giữ access/refresh token ở server và dùng cookie phiên được bảo vệ để giảm việc JavaScript trực tiếp nắm token. BFF vẫn cần CSRF protection và authorization ở server.

## CSRF và request do browser tự gửi

Browser có thể tự đính kèm cookie phù hợp vào request. Vì vậy, một website khác có thể tìm cách khiến browser gửi request đến ứng dụng đang đăng nhập. Đây là nền tảng của CSRF.

Các lớp phòng vệ có thể gồm:

- Cookie `SameSite` được chọn phù hợp với luồng ứng dụng.
- CSRF token gắn với session hoặc một cơ chế xác thực request tương đương.
- Kiểm tra `Origin` và, khi cần, `Referer` ở server cho thao tác thay đổi trạng thái.
- Fetch Metadata như `Sec-Fetch-Site` để bổ sung tín hiệu về ngữ cảnh request.
- Không dùng GET cho thao tác thay đổi dữ liệu.
- Xác minh lại người dùng hoặc yêu cầu xác nhận bổ sung với hành động có tác động cao.

Không dựa vào CORS như biện pháp CSRF duy nhất. Request có thể được gửi dù response không được JavaScript của trang khác đọc. Server cần kiểm tra token, ngữ cảnh và quyền trước khi thay đổi dữ liệu.

## `postMessage` và giao tiếp giữa các origin

`window.postMessage` cho phép các browsing context trao đổi dữ liệu. Vì message có thể đến từ một frame hoặc cửa sổ khác, bên nhận phải kiểm tra origin, source và schema trước khi xử lý.

Ví dụ gửi message có đích cụ thể:

~~~javascript
const partnerWindow = document.querySelector('#partner-frame').contentWindow;
partnerWindow.postMessage(
  { type: 'REQUEST_STATUS', requestId: 'req-42' },
  'https://partner.example.com'
);
~~~

Ví dụ nhận message:

~~~javascript
window.addEventListener('message', (event) => {
  if (event.origin !== 'https://partner.example.com') return;
  if (event.source !== partnerWindow) return;

  const message = event.data;
  if (!message || typeof message !== 'object') return;
  if (message.type !== 'STATUS_RESULT') return;
  if (typeof message.requestId !== 'string') return;
  if (typeof message.status !== 'string') return;

  renderStatusAsText(message.status);
});
~~~

Origin phải được so sánh chính xác, không dùng `endsWith('example.com')` hoặc kiểm tra chuỗi con. Schema cần giới hạn độ dài và miền giá trị; dữ liệu hợp lệ về cấu trúc vẫn có thể là nội dung độc hại. Nếu message kích hoạt hành động nhạy cảm, server vẫn phải xác thực và phân quyền khi nhận request tương ứng.

Không dùng `'*'` làm `targetOrigin` khi gửi dữ liệu nhạy cảm. Với sandboxed iframe có opaque origin, cách xác minh có thể khác; thiết kế cần dựa trên cấu hình sandbox và giao thức được hỗ trợ, không bỏ qua kiểm tra chỉ để message chạy được.

## API và quyền ở server

Một API an toàn không dựa vào trạng thái giao diện. Mỗi request cần trải qua các bước:

1. Xác thực credential và xác định danh tính.
2. Kiểm tra session, token, issuer/audience/expiry hoặc trạng thái đăng nhập tương ứng.
3. Xác thực input theo schema, kiểu, độ dài và miền giá trị.
4. Tải tài nguyên từ nguồn dữ liệu có thẩm quyền.
5. Kiểm tra quyền trên đúng hành động và đúng tài nguyên.
6. Thực hiện thao tác theo nguyên tắc tối thiểu và nhất quán.
7. Ghi audit event phù hợp, không ghi secret hoặc dữ liệu thừa.

Ví dụ, request `POST /api/orders/123/refund` không được phép chỉ vì frontend hiển thị nút Refund. Server cần kiểm tra người dùng có quyền hoàn tiền cho đơn hàng `123`, trạng thái đơn có cho phép hoàn hay không, số tiền và currency có hợp lệ không, thao tác đã được xử lý trước đó chưa và có cần xác nhận bổ sung không.

Đây cũng là cách phòng chống IDOR/BOLA: không chỉ kiểm tra người dùng đã đăng nhập, mà phải xác minh họ có quyền trên object được chỉ định. Không tin `ownerId` hoặc `tenantId` do client gửi; lấy quan hệ sở hữu từ dữ liệu server hoặc so sánh với danh tính đã xác thực.

## Kiểm thử ranh giới tin cậy phía client

Kiểm thử cần chứng minh việc sửa client không vượt qua được kiểm soát server và dữ liệu không tin cậy không trở thành mã thực thi.

| Phép thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Sửa role trên storage | Đổi `displayRole` hoặc `isAdmin` trong DevTools | UI có thể thay đổi; API nhạy cảm vẫn từ chối nếu server không cấp quyền |
| Gọi API trực tiếp | Gửi request bằng curl hoặc DevTools bỏ qua UI | Server xác thực và phân quyền như request bình thường |
| Thay object ID | Đổi ID tài nguyên sang object của người dùng khác | Server trả kết quả không tiết lộ dữ liệu và không cho phép thao tác trái quyền |
| Sửa giá/số tiền | Thay amount, price hoặc discount trong request | Server tính lại từ dữ liệu có thẩm quyền và kiểm tra nghiệp vụ |
| Sửa form | Bỏ qua validation JavaScript, gửi trường sai kiểu hoặc vượt giới hạn | Server từ chối dữ liệu không hợp lệ |
| DOM injection | Đưa markup vô hại vào fixture và kiểm tra sink | Nội dung được hiển thị như text hoặc được sanitizer xử lý; không thực thi script |
| Message giả | Gửi `postMessage` từ origin khác hoặc sai schema | Handler bỏ qua hoặc từ chối message |
| CSRF | Tạo request cross-site trong môi trường test | Server từ chối thao tác thay đổi trạng thái khi thiếu CSRF protection hợp lệ |
| CORS | Thử đọc response từ origin không được phép | Browser không cho JavaScript đọc; server vẫn kiểm tra quyền và side effect |
| Storage bị xóa | Xóa local storage/cache hoặc mở profile mới | Ứng dụng khôi phục trạng thái từ server hoặc yêu cầu xác thực lại an toàn |

Kiểm thử trên môi trường được phép, dùng tài khoản và dữ liệu giả. Không thử sửa dữ liệu hoặc gọi API trên tài khoản người khác nếu không có phạm vi kiểm thử được phê duyệt.

### Ví dụ kiểm thử authorization bằng Playwright

Ví dụ dưới đây giả định có một người dùng thường đăng nhập và API quản trị được bảo vệ ở server:

~~~javascript
import { test, expect } from '@playwright/test';

test('client-side role changes do not grant server privileges', async ({ page }) => {
  await loginAsStandardUser(page);
  await page.goto('/account');

  await page.evaluate(() => {
    localStorage.setItem('displayRole', 'admin');
  });

  const response = await page.request.delete('/api/users/target-user');
  expect(response.status()).toBe(403);
});
~~~

`loginAsStandardUser` là helper test của ứng dụng. Trong hệ thống thực, dùng fixture và tài khoản test có quyền thường; API phải xác định session tương ứng và trả `403` khi user không có quyền. Test này chứng minh server authorization không phụ thuộc vào role lưu trong local storage. Cần có test riêng cho người có quyền hợp lệ để xác nhận chức năng được phép vẫn hoạt động.

## Thiết kế kiến trúc giảm niềm tin vào client

Một số mẫu kiến trúc giúp giữ quyết định nhạy cảm ở server:

- **Backend for Frontend (BFF):** browser giao tiếp với backend cùng origin; BFF quản lý token phía server và áp dụng authorization trước khi gọi dịch vụ nội bộ.
- **Session cookie bảo vệ:** dùng cookie Secure, HttpOnly, SameSite phù hợp; thêm CSRF protection cho request thay đổi trạng thái.
- **Server-side rendering có kiểm soát:** server chỉ đưa dữ liệu mà người dùng đã được phép xem vào HTML; không coi dữ liệu đã render là bí mật trước XSS hoặc extension.
- **API authorization theo object:** kiểm tra quyền trên từng tài nguyên và hành động, không chỉ dựa vào role tổng quát.
- **Allowlist hành động:** client gửi ý định nghiệp vụ có cấu trúc; server ánh xạ đến các thao tác được phép thay vì nhận tên hàm, URL hoặc câu lệnh tùy ý.
- **Audit và rate limit:** ghi nhận thao tác nhạy cảm, phát hiện lạm dụng và giới hạn request theo danh tính/tài nguyên.

Không có kiến trúc nào loại bỏ hoàn toàn rủi ro client. XSS có thể thực hiện hành động trong phiên người dùng; extension có thể quan sát page; thiết bị có thể bị malware. Vì vậy, với hành động quan trọng cần xác minh lại, hạn chế thời gian sống credential, thông báo hoạt động bất thường và có khả năng thu hồi session.

## Các hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Người dùng không thể sửa JavaScript production | Người dùng có thể sửa runtime, DOM, request và storage bằng công cụ phù hợp |
| Ẩn nút quản trị là đủ | API phải kiểm tra quyền ở server cho từng hành động |
| Dữ liệu trong localStorage là của ứng dụng | Dữ liệu nằm trên thiết bị và có thể bị người dùng hoặc script cùng origin sửa |
| CORS bảo vệ API khỏi mọi website khác | CORS chủ yếu kiểm soát việc đọc response bằng JavaScript; request và side effect cần bảo vệ riêng |
| JWT decode thành công nghĩa là token hợp lệ | Decode không xác minh chữ ký, issuer, audience, expiry hoặc quyền |
| HttpOnly loại bỏ XSS impact | XSS vẫn có thể thực hiện hành động trong phiên dù không đọc được cookie bằng JavaScript |
| Cùng origin nghĩa là dữ liệu đáng tin | Dữ liệu từ DOM, storage, API hoặc người dùng vẫn có thể không tin cậy |
| CSP thay thế output encoding | CSP là lớp phòng vệ bổ sung; encoding/sanitization theo ngữ cảnh vẫn cần thiết |
| Client validation ngăn request sai | Người dùng có thể bỏ qua JavaScript; server phải validate lại |

## Checklist thiết kế client-side trust

- [ ] Đã lập bản đồ dữ liệu đi vào browser từ URL, DOM, storage, API, message và script bên thứ ba.
- [ ] Không dùng trạng thái hoặc role phía client làm căn cứ authorization.
- [ ] Mọi API nhạy cảm xác thực danh tính và phân quyền ở server.
- [ ] Server kiểm tra quyền trên object cụ thể để chống IDOR/BOLA.
- [ ] Server validate schema, miền giá trị và ràng buộc nghiệp vụ cho mọi request.
- [ ] Giá trị không tin cậy được encode theo ngữ cảnh hoặc sanitizer phù hợp trước khi render.
- [ ] Hạn chế DOM sink nguy hiểm; CSP và Trusted Types được dùng như lớp bổ sung.
- [ ] Storage phía client không chứa secret dài hạn hoặc dữ liệu dùng để cấp quyền.
- [ ] Cookie có `Secure`, `HttpOnly`, `SameSite` và phạm vi phù hợp.
- [ ] Token được xác minh ở server; không dựa vào decode ở browser.
- [ ] CSRF protection được áp dụng cho request dùng cookie và thay đổi trạng thái.
- [ ] `postMessage` kiểm tra chính xác origin, source và schema; không dùng wildcard cho dữ liệu nhạy cảm.
- [ ] CORS được cấu hình theo origin cần thiết và không được coi là authorization.
- [ ] Extension, script bên thứ ba và service worker được đánh giá theo quyền và ranh giới riêng.
- [ ] Test bao gồm sửa storage/role, gọi API trực tiếp, đổi object ID, DOM injection và request cross-site.
- [ ] Có audit, rate limit, session revocation và xác minh bổ sung cho thao tác rủi ro cao.

## Câu hỏi tự kiểm tra

1. Vì sao server phải kiểm tra quyền dù frontend đã ẩn nút quản trị?
2. CORS khác authorization và CSRF protection ở điểm nào?
3. Những loại dữ liệu nào trong browser cần được xem là đầu vào không tin cậy?
4. Vì sao cookie HttpOnly vẫn không loại bỏ tác động của XSS?
5. Vì sao decode JWT ở browser không chứng minh token hợp lệ?
6. Khi nhận `postMessage`, cần kiểm tra những thuộc tính nào trước khi xử lý?
7. Một test có thể chứng minh authorization thực sự nằm ở server bằng cách nào?

Client-side trust là việc đặt đúng kỳ vọng vào browser và code frontend. Hãy dùng client để hỗ trợ trải nghiệm, kiểm tra dữ liệu sớm và giảm bề mặt tấn công; giữ xác thực, phân quyền và quyết định nghiệp vụ ở server. Khi thiết kế theo ranh giới này, việc người dùng sửa JavaScript, storage hoặc request không thể tự tạo ra quyền mà server chưa cấp.
