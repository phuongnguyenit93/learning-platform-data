# Logout giữa các tab trình duyệt và quản lý phiên nhiều tab

Trong một ứng dụng web, người dùng có thể mở cùng một tài khoản ở nhiều tab: tab A xem hồ sơ, tab B thực hiện thanh toán, tab C mở trang quản trị. Khi người dùng chọn **Đăng xuất** ở tab A, yêu cầu bảo mật không chỉ là đổi giao diện tab A sang màn hình đăng nhập. Phiên đăng nhập phải được kết thúc ở nơi có quyền quyết định xác thực, đồng thời các tab còn lại phải ngừng sử dụng trạng thái và dữ liệu của phiên cũ.

Bài này thuộc **Browser security** trong phạm vi **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: mô hình tin cậy, vòng đời token, JWT/opaque token, access token/refresh token, claims, scope, audience, thu hồi token và phòng chống việc sử dụng token sau khi phiên kết thúc. Trọng tâm là cách logout hoạt động khi nhiều tab cùng dùng một phiên, đặc biệt trong ứng dụng dùng cookie phiên hoặc OAuth 2.0/OpenID Connect (OIDC).

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt **xóa trạng thái ở tab**, **hủy phiên tại backend**, **thu hồi token** và **đăng xuất tại nhà cung cấp danh tính (IdP/OP)**.
- Giải thích vì sao logout ở một tab không tự động xóa bộ nhớ JavaScript của những tab khác.
- Chọn cơ chế thông báo giữa các tab và hiểu giới hạn của nó.
- Thiết kế luồng logout an toàn trước request đang chạy, refresh token, tab ngủ và lỗi mạng.
- Kiểm chứng rằng backend từ chối yêu cầu sử dụng phiên đã đăng xuất, ngay cả khi giao diện chưa kịp cập nhật.

## 2. Vì sao nhiều tab tạo ra bài toán riêng?

Mỗi tab là một ngữ cảnh thực thi JavaScript riêng. Biến trong bộ nhớ, state của ứng dụng và cache dữ liệu của tab A không tự động đổi khi tab B thay đổi. Trong khi đó, các tab cùng origin thường dùng chung kho cookie và localStorage phù hợp với chính sách phân vùng lưu trữ của trình duyệt.

Ví dụ ban đầu:

1. Tab A và B đều gửi cookie phiên đến backend và được trả về dữ liệu của tài khoản An.
2. Tab A gọi API logout; backend hủy phiên và gửi lệnh xóa cookie.
3. Cookie có thể đã biến mất khỏi kho dùng chung, nhưng tab B vẫn có tên An, danh sách giao dịch hoặc cờ isAuthenticated trong bộ nhớ.
4. Nếu tab B tiếp tục gửi API, backend phải từ chối phiên cũ. Tab B cũng cần dọn giao diện và cache để không hiển thị dữ liệu nhạy cảm.

**Nguyên tắc cốt lõi:** tín hiệu liên tab giúp đồng bộ **trải nghiệm người dùng**; việc hủy phiên và kiểm tra token tại backend mới là **ranh giới bảo mật**.

### Những thành phần được chia sẻ đến đâu?

| Thành phần | Phạm vi thông thường | Ý nghĩa khi logout |
|---|---|---|
| Biến JavaScript, state của React/Vue, cache trong bộ nhớ | Riêng từng tab hoặc từng document | Tab khác phải tự dọn state khi nhận tín hiệu hoặc phát hiện phiên mất hiệu lực. |
| sessionStorage | Theo tab và origin; có một số hành vi sao chép ban đầu khi mở tab mới | Không thể dùng để đồng bộ logout tin cậy giữa các tab. |
| localStorage | Các document đủ điều kiện trong cùng origin và cùng phân vùng lưu trữ | Có sự kiện storage ở những document khác; không nên chứa access/refresh token nhạy cảm. |
| BroadcastChannel | Các ngữ cảnh cùng origin và cùng phân vùng lưu trữ được phép giao tiếp | Gửi thông điệp logout nhanh, nhưng không bảo đảm tab ngủ hoặc bị đóng đã nhận. |
| Cookie | Kho cookie dùng chung theo domain/path và chính sách của trình duyệt | Backend có thể hết phiên dù state của tab khác vẫn còn; cookie HttpOnly không đọc được bằng JavaScript. |
| Backend session hoặc trạng thái thu hồi | Phía server | Nguồn quyết định request mới còn được xác thực hay không. |

Các tab ở **origin khác nhau**, profile trình duyệt khác nhau hoặc phân vùng lưu trữ khác nhau không nhất thiết thấy cùng thông điệp. Vì vậy không thiết kế bảo mật dựa vào giả định rằng mọi tab đều được thông báo tức thì.

## 3. Hiểu chính xác bốn mức độ “đăng xuất”

### 3.1. Logout cục bộ trong một tab

Ứng dụng xóa auth state, dữ liệu cá nhân đã cache, thông tin hiển thị và chuyển sang trang đăng nhập. Nếu chỉ làm bước này, cookie hoặc refresh token còn hiệu lực vẫn có thể dùng để khôi phục đăng nhập. **Xóa UI không đồng nghĩa kết thúc phiên.**

### 3.2. Logout tại ứng dụng/backend

Backend đánh dấu phiên hiện tại hết hiệu lực (ví dụ xóa session trong kho phiên, đặt revokedAt hoặc tăng session version), thu hồi refresh token liên quan khi phù hợp và yêu cầu browser xóa cookie phiên. Mỗi request sau đó phải được kiểm tra với trạng thái mới; nếu không hợp lệ thì trả HTTP 401.

Trong kiến trúc dùng **BFF (Backend for Frontend)**, browser giữ cookie phiên với HttpOnly, Secure, SameSite và backend giữ token OAuth. Đây là một cách thuận lợi để tránh phải lưu refresh token trong JavaScript.

### 3.3. Thu hồi access token và refresh token

Hai loại token có đặc tính khác nhau:

- **Opaque access token**: resource server thường dựa vào introspection hoặc trạng thái do authorization server cung cấp. Token bị thu hồi có thể bị từ chối sớm, tùy cơ chế cache kết quả introspection.
- **JWT access token tự chứa**: chữ ký, iss, aud, exp và scope/role hợp lệ chưa có nghĩa token chưa bị thu hồi. Nếu resource server chỉ kiểm tra chữ ký và exp, JWT cũ có thể tiếp tục dùng đến khi hết hạn. Muốn vô hiệu hóa sớm cần cơ chế kiểm tra phiên, denylist theo jti, version hoặc cách khác do hệ thống thiết kế.
- **Refresh token**: có thể được thu hồi ở authorization server; với refresh token rotation, cần vô hiệu hóa token hiện tại và xử lý cả token family theo chính sách khi logout. Tránh để tab khác refresh rồi tái tạo phiên.

Logout an toàn phải xác định rõ **mức bảo đảm thu hồi**: ngay lập tức ở backend, hoặc chấp nhận access token có vòng đời ngắn tiếp tục hợp lệ trong một khoảng giới hạn. Không hứa “logout vô hiệu mọi JWT tức thì” nếu hệ thống chưa triển khai kiểm tra thu hồi.

### 3.4. Logout tại Identity Provider (OIDC)

Một ứng dụng (Relying Party, RP) có thể hủy phiên riêng nhưng phiên Single Sign-On tại OpenID Provider (OP/IdP) vẫn còn. Khi người dùng truy cập lại, OP có thể đăng nhập họ trở lại mà không yêu cầu mật khẩu. Nếu yêu cầu là đăng xuất khỏi phiên SSO, RP cần sử dụng cơ chế logout của OP được hỗ trợ, ví dụ **RP-Initiated Logout**, ngoài việc hủy phiên ứng dụng.

OIDC còn có **Front-Channel Logout** và **Back-Channel Logout** để OP thông báo cho các RP liên quan. Front-channel phụ thuộc browser nên có thể bị giới hạn bởi cookie bên thứ ba hoặc tab/iframe; back-channel là thông báo server-to-server và RP phải kiểm tra tính hợp lệ của logout token. Không nên coi BroadcastChannel nội bộ là cơ chế đăng xuất mọi ứng dụng SSO.

## 4. Luồng logout nhiều tab nên diễn ra thế nào?

Giả sử hệ thống dùng cookie phiên **__Host-session** (Secure, HttpOnly, Path=/, không có Domain) và một API logout dùng phương thức POST.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant A as Tab A
    participant S as Backend
    participant B as Tab B
    U->>A: Chọn Đăng xuất
    A->>S: POST /api/session/logout (cookie + CSRF)
    S->>S: Hủy session, thu hồi refresh token phù hợp
    S-->>A: 204 + Set-Cookie hết hạn
    A->>A: Xóa auth state, cache, hủy request
    A-->>B: BroadcastChannel / storage: LOGOUT
    B->>B: Xóa state, cache, hủy request
    B->>B: Chuyển sang màn hình đăng nhập
    B->>S: Request cũ hoặc request sau logout
    S-->>B: 401 vì session đã vô hiệu
~~~

Ở mức thiết kế, thứ tự trách nhiệm như sau:

1. **Backend là nơi chốt logout.** Endpoint nhận POST, xác thực quyền thao tác phiên và bảo vệ CSRF đối với xác thực bằng cookie; thao tác vô hiệu phiên nên idempotent để request lặp vẫn có kết quả nhất quán.
2. **Tab khởi tạo nhận xác nhận từ backend.** Nếu backend báo thành công, tab xóa state/cache, ngừng hành động dùng phiên cũ và phát sự kiện logout. Nếu mạng lỗi hoặc backend không xác nhận, UI phải thể hiện trạng thái chưa xác định và hỗ trợ thử lại, không giả vờ đã hủy phiên ở server.
3. **Các tab khác dọn trạng thái ngay khi nhận thông báo.** Tab đang ngủ hoặc bị bỏ lỡ sự kiện phải kiểm tra lại phiên khi được kích hoạt, khi có 401 hoặc trước thao tác nhạy cảm.
4. **Backend từ chối request đến muộn.** Sự kiện trong browser không thể thu hồi request đã gửi; quy tắc phân quyền và thời điểm hủy phiên trên server mới quyết định request nào được xử lý.

### Vì sao không chỉ gọi localStorage.clear()?

Lệnh này chỉ xử lý dữ liệu của origin trong localStorage và không hủy cookie HttpOnly, phiên backend hay token đã bị sao chép. Nó còn có thể xóa nhầm tùy chọn không liên quan. Thay vào đó, xóa **các khóa auth đã xác định** cùng cache dữ liệu nhạy cảm và thực hiện logout server.

### Vì sao phải chống CSRF?

Cookie được browser tự gửi kèm request hợp lệ, nên một endpoint thay đổi trạng thái như logout cần biện pháp chống CSRF phù hợp: ví dụ CSRF token gắn với phiên, kiểm tra Origin/Referer hợp lệ và cấu hình SameSite. SameSite hỗ trợ nhưng không nên được xem là biện pháp duy nhất trong mọi kiến trúc. Không thiết kế logout bằng GET có side effect.

## 5. Đồng bộ logout trong browser: BroadcastChannel, storage và revalidation

Một kiến trúc thực tế có thể sử dụng ba lớp bổ trợ nhau:

| Cơ chế | Dùng khi nào | Giới hạn |
|---|---|---|
| **BroadcastChannel** | Thông báo LOGOUT gần như ngay lập tức giữa các tab đủ điều kiện. | Không lưu lịch sử; tab mở sau, tab đóng hoặc bị cô lập lưu trữ có thể bỏ lỡ. |
| **storage event** | Phương án dự phòng: ghi một marker không nhạy cảm vào localStorage; tab khác nhận sự kiện. | Sự kiện không phát trên chính tab ghi; phụ thuộc quyền truy cập lưu trữ và cùng phân vùng. |
| **Kiểm tra lại phiên** | Khi load trang, tab focus, trở lại từ background, nhận 401 hoặc trước giao dịch quan trọng. | Có độ trễ và chi phí mạng; cần xử lý race condition và phản hồi backend. |

Không phát access token, refresh token, ID token hoặc dữ liệu tài khoản qua kênh liên tab. Một thông điệp dạng **{ type: "LOGOUT", version: 1 }** là đủ để yêu cầu các tab dọn state. Marker localStorage không phải bằng chứng xác thực và không được dùng thay thế backend session.

### Ví dụ TypeScript phía frontend

Ví dụ này minh họa cách phối hợp cho **ứng dụng dùng cookie phiên/BFF**. Các hàm dọn state/cache và cập nhật route là adapter cần nối với framework của ứng dụng. Chỉ gọi onLogoutConfirmed sau khi API server báo logout thành công.

~~~ts
type SessionEvent = {
  type: "LOGOUT";
  version: 1;
  id: string;
};

const CHANNEL_NAME = "app-session-events-v1";
const LOGOUT_MARKER = "app-session-last-logout-v1";

const channel =
  typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel(CHANNEL_NAME)
    : null;

let signedOut = false;
const inFlightControllers = new Set<AbortController>();

// Adapter ứng dụng: xóa auth state, dữ liệu cá nhân và cache của phiên cũ.
declare function clearAuthStateAndPrivateCaches(): void;
declare function showLoginScreen(): void;
declare function getCsrfToken(): string;
declare function showLogoutError(message: string): void;

function registerProtectedRequest(controller: AbortController): () => void {
  inFlightControllers.add(controller);
  return () => inFlightControllers.delete(controller);
}

function applySignedOutState(): void {
  if (signedOut) return;
  signedOut = true;

  for (const controller of inFlightControllers) controller.abort();
  inFlightControllers.clear();
  clearAuthStateAndPrivateCaches();
  showLoginScreen();
}

function onLogoutConfirmed(): void {
  const event: SessionEvent = {
    type: "LOGOUT",
    version: 1,
    id: crypto.randomUUID(),
  };

  // Hai kênh là best-effort; backend đã hủy phiên trước bước này.
  try {
    channel?.postMessage(event);
  } catch {
    // Tab khác vẫn phải kiểm tra lại phiên khi được kích hoạt.
  }
  try {
    localStorage.setItem(LOGOUT_MARKER, event.id);
  } catch {
    // Có thể bị chặn bởi thiết lập quyền riêng tư/lưu trữ.
  }
  applySignedOutState();
}

channel?.addEventListener("message", (message: MessageEvent<SessionEvent>) => {
  if (message.data?.type === "LOGOUT" && message.data.version === 1) {
    applySignedOutState();
  }
});

window.addEventListener("storage", (event: StorageEvent) => {
  if (event.key === LOGOUT_MARKER && event.newValue !== null) {
    applySignedOutState();
  }
});

async function logout(): Promise<void> {
  try {
    const response = await fetch("/api/session/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": getCsrfToken() },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Server chưa xác nhận logout");
    onLogoutConfirmed();
  } catch {
    showLogoutError("Không thể xác nhận đăng xuất. Hãy thử lại.");
  }
}
~~~

**Phạm vi của ví dụ:** Hàm registerProtectedRequest chỉ hữu ích khi mọi request nhạy cảm thực sự đăng ký AbortController của mình và hủy đăng ký sau khi hoàn thành. Việc abort ở browser không bảo đảm server chưa nhận hoặc chưa xử lý request. Trong hệ thống thực, cần thêm trạng thái đang logout để khóa thao tác mới, bảo vệ callback trả về muộn, tránh ghi cache của phiên cũ và đóng BroadcastChannel khi ứng dụng hủy context.

Hàm getCsrfToken ở trên đại diện cho cơ chế CSRF hiện có của ứng dụng; không nên tự đưa session secret vào localStorage. API dùng CSRF token theo hợp đồng backend, hoặc một cơ chế chống CSRF tương đương.

### Khôi phục tính nhất quán khi tab không nhận được sự kiện

Mỗi lần khởi tạo ứng dụng, cần gọi endpoint kiểm tra phiên (ví dụ GET /api/session/me) trước khi coi người dùng đã đăng nhập. Khi tab lấy lại focus hoặc trở về từ background, cũng nên revalidate, có debounce để tránh gọi quá nhiều. Nếu server trả 401, tab dọn state như khi nhận LOGOUT; nếu trả session khác, phải thay cache và trạng thái theo danh tính mới.

Lưu ý **401 không phải lúc nào cũng có nghĩa logout toàn bộ**: có thể access token hết hạn và phiên còn được refresh hợp lệ. Chỉ phát sự kiện hết phiên sau khi cơ chế refresh/kiểm tra phiên xác nhận không thể tiếp tục. HTTP 403 thường có nghĩa thiếu quyền đối với tài nguyên, không mặc nhiên là phiên đã hết.

Một marker localStorage chỉ là tín hiệu, không phải nguồn duy nhất để khôi phục trạng thái. Nếu tab mở mới sau khi đã logout, nó phải dựa vào kết quả xác thực của server.

## 6. Hợp đồng backend và các điểm dễ bị bỏ sót

Endpoint logout của ứng dụng dùng cookie có thể có hợp đồng:

~~~http
POST /api/session/logout HTTP/1.1
Cookie: __Host-session=...
X-CSRF-Token: ...

HTTP/1.1 204 No Content
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Trên server, quy trình điển hình:

1. Xác định phiên từ cookie và xác minh yêu cầu logout theo chính sách CSRF.
2. Vô hiệu hóa session trong kho trạng thái dùng chung; bảo đảm các node API khác đều nhìn thấy trạng thái thu hồi theo mức nhất quán đã cam kết.
3. Thu hồi refresh token hoặc phiên OAuth liên quan nếu đó là quyền và trách nhiệm của ứng dụng; xử lý an toàn các lần refresh đồng thời.
4. Gửi Set-Cookie hết hạn **khớp tên, Path và Domain** đã dùng khi tạo cookie. Với cookie __Host- không có Domain và Path=/.
5. Trả kết quả idempotent; ngăn response chứa dữ liệu phiên được cache ngoài ý muốn.

**Xóa cookie không hủy server session.** Nếu ID phiên còn hợp lệ trong backend, một bản sao cookie bị đánh cắp vẫn có thể truy cập. Ngược lại, nếu backend đã thu hồi phiên nhưng cookie còn ở browser do lỗi xóa cookie, server vẫn phải từ chối cookie đó.

**Race condition cần xử lý ở server:** Tab A đang logout trong khi tab B xin refresh token hoặc gửi request ghi dữ liệu. Cần xác định điểm tuyến tính hóa việc thu hồi phiên/token, bảo đảm refresh sau thời điểm đó bị từ chối; với thao tác quan trọng, kiểm tra phiên và quyền ở thời điểm xử lý/commit phù hợp. Khóa UI và AbortController ở frontend chỉ giảm khả năng phát thêm request, không thay thế kiểm tra này.

**Cache sau logout:** Cache dữ liệu cá nhân trong SPA, IndexedDB, service worker hoặc offline store phải được dọn theo phạm vi phiên. Các HTTP response nhạy cảm nên có Cache-Control phù hợp (thường no-store); không kỳ vọng việc đổi route tự xóa dữ liệu đã cache. Nếu dùng Clear-Site-Data, cần kiểm tra hỗ trợ trình duyệt và phạm vi xóa vì chỉ thị có thể xóa nhiều loại dữ liệu hơn dự kiến.

## 7. Khi ứng dụng dùng OAuth 2.0 / OIDC

### Access token ở browser

Nếu frontend trực tiếp giữ access token, nhiều tab có thể có **bản sao khác nhau**. Logout ở một tab cần yêu cầu server/authorization server xử lý thu hồi token theo mô hình đã chọn và thông báo các tab bỏ token cục bộ. Token không nên được gửi từ tab này sang tab khác qua BroadcastChannel để “đồng bộ” đăng nhập. Với JWT, những resource server chỉ kiểm tra JWT offline có thể tiếp tục nhận token còn hạn; giảm cửa sổ rủi ro bằng TTL ngắn và cơ chế thu hồi phù hợp yêu cầu hệ thống.

### Refresh token rotation giữa các tab

Nếu nhiều tab dùng chung một refresh token rồi đồng thời refresh, request đến sau có thể dùng lại token vừa bị rotation, dẫn đến lỗi hoặc bị phát hiện là replay. Cần có một cơ chế **single-flight hoặc điều phối refresh** và chính sách rotation rõ ràng. Điều phối trong browser chỉ là tối ưu: authorization server vẫn phải tự phát hiện và xử lý reuse/replay. Với ứng dụng BFF, đưa refresh token về server thường đơn giản hóa vấn đề đồng thời và hạn chế lộ token khỏi JavaScript.

Khi logout, các tác vụ refresh đang chờ phải bị hủy hoặc không được phép ghi trạng thái đăng nhập mới sau khi phiên bị kết thúc. Sự kiện LOGOUT nên có ưu tiên cao hơn phản hồi refresh đến muộn.

### OIDC logout khác đồng bộ tab

Với **RP-Initiated Logout**, RP chuyển người dùng đến end_session_endpoint được OP công bố nếu nhà cung cấp hỗ trợ; request có thể dùng id_token_hint, post_logout_redirect_uri và state theo quy định của OP. Khi browser trở lại ứng dụng, ứng dụng vẫn cần chắc chắn session cục bộ đã bị hủy.

Với **Back-Channel Logout**, RP tiếp nhận thông điệp logout server-to-server và xác minh đầy đủ chữ ký, issuer, audience, sự kiện logout, thời gian và định danh phiên/người dùng (sid hoặc sub theo quy định). Sau đó RP thu hồi các phiên liên quan. Với nhiều ứng dụng khác origin, mỗi ứng dụng có cơ chế quản lý phiên riêng; BroadcastChannel của một origin không có hiệu lực chung.

Đăng xuất “chỉ thiết bị này”, “mọi tab của trình duyệt này”, “mọi thiết bị” và “toàn bộ SSO” là **các phạm vi khác nhau**. UI và API phải diễn đạt rõ phạm vi, đồng thời server triển khai thu hồi phù hợp (theo session ID, token family, tài khoản hoặc phiên OP). Không suy ra phạm vi từ việc có bao nhiêu tab đang mở.

## 8. Các tình huống cạnh tranh và cách xử lý

| Tình huống | Hành vi mong muốn | Điểm kiểm chứng |
|---|---|---|
| Tab A logout, tab B vẫn mở | B dọn cache, đổi UI; API cũ trả 401 sau khi phiên vô hiệu. | BroadcastChannel/storage và kiểm tra backend. |
| Tab B đang ngủ khi A logout | Khi B hoạt động lại, trạng thái cũ bị loại bỏ. | Revalidate lúc focus/visibility hoặc khi có 401. |
| Tab B đang gửi request khi A logout | Không có thao tác trái phép nào được chấp nhận sau khi hiệu lực thu hồi được xác lập. | Kiểm tra session/authorization phía server; xem xét thời điểm commit. |
| Tab A mất mạng lúc bấm logout | Không khẳng định server đã hủy phiên nếu chưa có xác nhận. | Hiển thị lỗi, retry và bảo vệ UI khi chưa rõ kết quả. |
| Tab B nhận phản hồi refresh muộn | Không khôi phục phiên mà A vừa logout. | Kiểm tra generation/epoch của phiên trước khi ghi auth state. |
| Người dùng đăng nhập tài khoản B sau khi đã logout A | Cache và response của A không được xuất hiện trong phiên B. | Gắn cache/request với session hoặc user, loại response cũ. |
| Hai tab logout gần như đồng thời | Endpoint phản hồi nhất quán; state cuối cùng là đã logout. | Idempotency và cơ chế đồng bộ sự kiện. |
| Người dùng logout tại ứng dụng nhưng phiên IdP còn | Việc đăng nhập lại có thể diễn ra bằng SSO. | Phân biệt local logout và OP logout trong yêu cầu sản phẩm. |
| Người dùng giữ JWT đã sao chép trước logout | JWT không được chấp nhận quá thời gian/cơ chế thu hồi đã cam kết. | Thử lại token ở resource server, không chỉ kiểm tra UI. |

### Ví dụ race của refresh token

~~~text
T0: Tab A và B đều đang có phiên S1.
T1: Tab B bắt đầu refresh; request đang trên đường tới server.
T2: Tab A logout, server đặt S1 = REVOKED.
T3: Response refresh của B đến muộn.
T4: B không được ghi access token mới hoặc đổi UI thành "đã đăng nhập".
T5: Request dùng S1 vẫn phải bị từ chối tại server theo chính sách thu hồi.
~~~

Một cách triển khai ở frontend là dùng **session generation** hoặc cờ terminal cho phiên hiện tại. Mỗi request bất đồng bộ giữ generation lúc bắt đầu; khi logout tăng generation và đánh dấu phiên đã kết thúc. Callback chỉ ghi state nếu generation còn khớp và session chưa bị kết thúc. Cơ chế này chặn response muộn làm sống lại UI cũ; hiệu lực thật của token vẫn do server kiểm tra.

## 9. Những ngộ nhận dễ gây lỗ hổng

**“Đã xóa token khỏi localStorage nên token không còn dùng được.”** Sai: token bị sao chép trước đó vẫn tồn tại. Xóa phía client không thể thu hồi bản sao; token có thể cần revocation/introspection hoặc phải chờ exp.

**“Đã broadcast LOGOUT thì mọi tab đã đăng xuất.”** Không chắc: tab có thể ngủ, ngoại tuyến, thuộc origin hoặc phân vùng khác, hoặc mở sau sự kiện. Backend phải luôn kiểm tra phiên và browser cần revalidate.

**“Cookie HttpOnly giúp logout tự đồng bộ giao diện.”** HttpOnly ngăn JavaScript đọc cookie, nhưng không tự đặt lại auth state và cache trong các tab. Đồng bộ UX vẫn cần thiết.

**“Access token hết hạn thì logout đã hoàn tất.”** Một refresh token còn hiệu lực có thể cấp access token mới. Cần xét đầy đủ vòng đời token và phiên.

**“Nhận 403 thì phát LOGOUT cho toàn bộ tab.”** 403 có thể chỉ là thiếu scope hoặc quyền với tài nguyên. Không tự động biến một lỗi phân quyền thành logout.

**“Cứ kiểm tra JWT exp và chữ ký là biết phiên chưa bị logout.”** Sai nếu hệ thống cho phép thu hồi sớm. Cần thêm trạng thái thu hồi hoặc mô hình chấp nhận JWT đến hết TTL.

**“BroadcastChannel là kênh tin cậy để truyền token.”** Các script cùng origin có thể tham gia kênh; nếu origin bị XSS, thông điệp không còn bí mật. Chỉ truyền sự kiện tối thiểu và xử lý XSS bằng CSP, encoding, kiểm soát dependency và các biện pháp bảo vệ khác.

## 10. Checklist thiết kế và kiểm thử

Một giải pháp logout nhiều tab đạt yêu cầu nên trả lời được các câu hỏi:

- **Phạm vi:** logout một tab, một phiên trình duyệt, mọi thiết bị hay cả SSO? Có mô tả đúng cho người dùng không?
- **Server:** session và refresh token nào bị vô hiệu; access token còn sống được bao lâu; request đồng thời được xử lý theo nguyên tắc nào?
- **Browser:** có xóa state, cache, request đang chạy; thông báo liên tab; revalidate khi mở lại/focus/nhận 401 không?
- **Lưu trữ:** token có bị lộ qua localStorage, URL, log, BroadcastChannel hay cache không? Cookie có HttpOnly, Secure, SameSite, Path/Domain đúng không?
- **Phòng vệ:** logout POST có CSRF protection; dữ liệu riêng tư được trả với cache policy phù hợp; token được kiểm tra issuer, audience, expiry, scope và trạng thái thu hồi theo hợp đồng không?
- **Khả năng phục hồi:** khi mất mạng, thông báo thất bại, tab bị ngủ, refresh muộn hoặc logout đồng thời, hệ thống vẫn không tạo lại phiên đã hủy chứ?

Nên chạy một bài kiểm thử tích hợp thực sự bằng hai tab: mở một trang chứa dữ liệu riêng tư ở cả A và B; logout ở A; xác minh B dọn UI, request có cookie/token cũ bị backend từ chối, refresh không thể tái cấp quyền và một tab mở mới không phục hồi session cũ. Lặp lại với B ở background, mạng chậm, nhiều request đồng thời và trường hợp người dùng đăng nhập tài khoản khác.

## 11. Tự kiểm tra kiến thức

1. Tab A nhận HTTP 204 sau logout, nhưng tab B vẫn còn tên người dùng trên thanh điều hướng. Đây là lỗi UX hay lỗi bảo mật? Điều kiện nào biến nó thành rủi ro thực sự?
2. Vì sao sự kiện storage và BroadcastChannel không đủ để bảo đảm người dùng đã đăng xuất khỏi mọi tab và mọi thiết bị?
3. Nếu access token là JWT tự chứa còn 10 phút hạn, hệ thống cần cơ chế nào để chặn token bị đánh cắp ngay sau logout?
4. Refresh token rotation có thể gặp vấn đề gì khi hai tab refresh đồng thời, và khi logout xen vào?
5. Một ứng dụng dùng OIDC đã hủy session cục bộ nhưng người dùng nhấn Đăng nhập và được SSO tự động. Cần phân biệt hoặc bổ sung luồng logout nào?

**Ghi nhớ:** đồng bộ tab giải quyết sự nhất quán của giao diện, còn hủy phiên/token tại server giải quyết việc một credential cũ có tiếp tục được chấp nhận hay không. Thiết kế logout hoàn chỉnh cần cả hai, cộng với kiểm tra lại trạng thái khi tab bỏ lỡ thông báo.
