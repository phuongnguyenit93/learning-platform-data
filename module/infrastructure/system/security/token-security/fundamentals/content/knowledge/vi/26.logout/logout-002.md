# Xóa token phía client

## Mục tiêu học tập

Trong chương **Logout** thuộc học phần **Token Security Fundamentals**, **xóa token phía client** là việc loại bỏ những bản sao credential mà ứng dụng đang nắm giữ khi người dùng đăng xuất, ngắt kết nối tài khoản hoặc khi phiên hết hiệu lực. Những credential đó có thể là **access token**, **refresh token**, **ID token**, session cookie hoặc dữ liệu nằm trong memory, browser storage, service worker, mobile secure storage hay kho token phía **Backend for Frontend (BFF)**.

Điều cần hiểu ngay: **xóa một bản sao token khỏi thiết bị không đồng nghĩa token đã bị vô hiệu hóa ở Authorization Server (AS) hoặc Resource Server (RS)**. Nếu attacker đã sao chép bearer token còn hiệu lực, việc gọi `localStorage.removeItem()` chỉ làm ứng dụng hiện tại không còn token; bản sao bên ngoài vẫn có thể được dùng. Ngược lại, một yêu cầu **revoke token** thành công tại AS chưa bảo đảm browser đã xóa token khỏi memory, các tab hoặc cache.

Sau bài này, bạn có thể:

1. Xây dựng **danh mục token và nơi lưu** để quyết định phải xóa gì khi logout.
2. Phân biệt **local token deletion**, **server session invalidation**, **OAuth token revocation (RFC 7009)**, **OIDC logout** và **access-token expiration**.
3. Xử lý token trong **SPA/browser**: memory, `sessionStorage`, `localStorage`, IndexedDB, service worker, cache và nhiều tab.
4. Giải thích vì sao cookie `HttpOnly` phải được **server hết hạn đúng thuộc tính** và session server phải bị hủy; JavaScript không được/không thể xóa cookie đó trực tiếp.
5. Thiết kế logout cho **BFF, web backend, native/mobile, desktop và thiết bị offline**, kể cả refresh token rotation và network failure.
6. Ngăn **silent reauthentication, race với refresh request, callback cũ, request đang chạy**, cùng các lỗi logout CSRF/XSS.
7. Viết ví dụ HTTP/Java/Spring Security/JavaScript, kiểm thử hậu logout và nêu đúng giới hạn thu hồi JWT/opaque token.

## 1. “Xóa token” là hành động ở đâu?

Trước hết phân biệt **vị trí lưu bản sao** và **nơi quyết định hiệu lực**:

~~~mermaid
flowchart LR
    U["User chọn Logout"] --> C["Client xóa token/session reference local"]
    U --> B["BFF/backend vô hiệu session và xóa token store"]
    B --> A["AS revoke refresh/access token hoặc grant theo policy"]
    C --> A
    A --> S["AS token/grant state thay đổi"]
    S --> R["RS biết state qua introspection/denylist/cache invalidation nếu có"]
    C --> X["UI chuyển về Logged out"]
    B --> X
~~~

Đường từ Client đến AS chỉ thực hiện được khi Client được phép gọi **revocation endpoint** và vẫn có credential cần thu hồi. Không phải mọi ứng dụng có BFF, và cũng không phải mọi AS hỗ trợ revoke từng access token.

| Hoạt động | Ai thực hiện? | Điều bảo đảm trực tiếp | Điều **không** tự bảo đảm |
|---|---|---|---|
| **Xóa token local** | SPA/mobile/backend token store. | Bản sao trong kho được xóa không còn sẵn cho đường sử dụng thông thường. | Các bản sao ở attacker, tab khác, backup hoặc log đã biến mất. |
| **Hủy local session** | BFF/web server/browser cookie handling. | Session ID không được backend tiếp tục công nhận theo state đã hủy. | OAuth refresh token tại AS đã bị revoke. |
| **Revoke token** | Client gọi AS RFC 7009, hoặc AS thực thi revoke theo quyền user/admin. | AS xử lý vô hiệu hóa token/grant theo policy. | JWT còn trong RS cache/offline lập tức bị từ chối. |
| **Logout tại OP/SSO** | OP và RP theo OIDC profile. | Phiên đăng nhập tại OP/RP liên quan được xử lý theo giao thức. | Tất cả OAuth grants và tokens bị thu hồi. |
| **Token tự hết hạn** | AS phát TTL, RS xác minh `exp`. | Sau hạn token không còn hợp lệ theo kiểm tra thời gian. | Token bị đánh cắp không bị dùng trước hạn. |

**Kết luận:** Logout đầy đủ có thể là **một chuỗi thao tác nhiều hệ thống**. Bài này lấy **xóa token phía Client** làm trung tâm, đồng thời giải thích rõ các thao tác bên ngoài cần phối hợp.

## 2. Phân biệt các loại token trước khi xóa

| Credential | Thường được dùng ở đâu? | Có thể xuất hiện trong Client không? | Khi logout cần nghĩ gì? |
|---|---|---|---|
| **Access token** | Client → Resource Server qua `Authorization: Bearer` hoặc cơ chế sender-constrained. | Có, hoặc chỉ ở BFF. | Xóa bản sao, hủy tác vụ API; nếu cần chặn ngay, thiết kế revocation/RS enforcement. |
| **Refresh token** | Client → AS token endpoint để xin token mới. | Có ở native/SPA theo mô hình, hoặc chỉ BFF. | Ưu tiên bảo vệ và revoke/rotate theo grant; xóa đúng kho chứa. |
| **OIDC ID token** | Relying Party/Client kiểm tra kết quả xác thực user. | Có thể lưu tạm theo profile. | Không dùng làm access token; có thể cần `id_token_hint` cho RP-Initiated Logout, nhưng không nên lưu dài chỉ để tiện. |
| **Authorization code** | Client đổi tại token endpoint. | Tồn tại ngắn trong callback/giao dịch. | Hủy transaction còn chờ; code vốn cần short TTL và one-time exchange. |
| **PKCE `code_verifier`** | Client đưa tới token endpoint khi đổi authorization code. | Thường nằm trong transaction/session store. | Xóa pending login transactions/verifiers, tránh callback cũ tái đăng nhập. |
| **Session cookie** | Browser → BFF/web server. | Browser giữ cookie; `HttpOnly` ngăn JS đọc. | Server invalidate session; gửi cookie hết hạn đúng tên/Path/Domain. |
| **CSRF token/nonce/state** | Ràng buộc request hoặc transaction bảo mật. | Có thể nằm ở client/session. | Hủy hoặc xoay theo phiên, không để giá trị cũ được tái sử dụng. |
| **DPoP private key/mTLS key** | Chứng minh người gửi theo profile. | Khóa có thể nằm ở keystore hoặc workload. | Không luôn xóa key toàn cục: xét binding, owner, scope và vòng đời key. |

**Client secret** là credential của **confidential Client**, không phải token phiên của user. Một lần user logout **không nên xóa/rotate client secret dùng chung cho cả service**. Chỉ rotate/revoke client credential khi secret bị lộ, service bị chiếm hoặc chính sách vận hành yêu cầu.

### Bối cảnh ví dụ xuyên suốt

~~~text
Browser:               https://shop.example.test
BFF:                   Shop Backend for Frontend
Authorization Server:  https://auth.example.test
Resource Server:       Orders API, aud=orders-api
User:                  user-123, tenant-a
Scope:                 orders:read

Browser có:
  __Host-shop_session=<RANDOM_SESSION_REFERENCE>

BFF có:
  access token A + refresh token R của user-123

User nhấn Logout:
  Hủy session tại BFF, xóa token store, gửi Set-Cookie expire;
  yêu cầu AS revoke R theo policy và xử lý lỗi;
  API vẫn phải phân quyền trên từng request.
~~~

## 3. Threat model của thao tác xóa

### Những nơi token có thể còn tồn tại

~~~text
Ứng dụng đang chạy:
  JavaScript memory / component state / closure
  localStorage, sessionStorage, IndexedDB
  Service Worker memory hoặc storage do nó điều khiển
  request queue, in-flight fetch, HTTP client interceptors
  cookie / web session
  native secure storage, memory, process snapshots
  backend token database/cache

Bản sao bên ngoài:
  browser extension, malware, XSS
  access logs, traces, crash dumps, backups
  bản sao token attacker đã lấy
  proxy hoặc service khác lưu credential trái policy
~~~

Một phương thức `clearTokens()` có thể làm sạch **những kho mà ứng dụng kiểm soát**. Nó **không thể bảo đảm secure erasure trên phần cứng, sao lưu, bộ nhớ đã giải phóng hoặc môi trường đã bị chiếm**.

### Ba cấp độ hậu logout

1. **Không dùng lại trong UI hiện tại:** ứng dụng đã xóa reference, hủy cache nhạy cảm và không gửi request bằng credential cũ.
2. **Không dùng lại qua chính phiên Client:** session local/backend invalid, refresh bị chặn hoặc revocation thành công theo thiết kế.
3. **Không thể dùng từ bất kỳ bản sao nào tại RS:** cần revocation propagation/sender-binding/denylist/TTL phù hợp; điều này **không thể chứng minh chỉ bằng xóa local storage**.

Khi mô tả trạng thái với user và audit, cần nói rõ **cấp độ nào thực sự được kiểm chứng**.

## 4. Browser SPA: token có thể nằm ở nhiều kho

### So sánh các cách lưu thường gặp

| Nơi lưu | Điều xảy ra khi reload/đóng tab | Rủi ro chính | Xóa như thế nào? |
|---|---|---|---|
| **JavaScript memory** | Mất khi context thực sự bị hủy; có thể còn trong tab chưa đóng. | XSS có thể dùng token hoặc gọi API trong phiên. | Hủy reference, state, interceptor, request queue; reload nếu cần. |
| **`sessionStorage`** | Thường theo từng tab/top-level browsing context; hành vi restore/duplicate tab có khác biệt. | Script cùng origin có thể đọc; dữ liệu có thể tồn tại trong tab khác. | `removeItem`/`clear` đúng key trong **từng tab**. |
| **`localStorage`** | Bền qua restart trong điều kiện thông thường và chia sẻ giữa các tab cùng origin. | XSS, extension, dữ liệu lưu quá lâu. | `removeItem` đúng key; đồng bộ trạng thái giữa tab. |
| **IndexedDB** | Lưu lâu dài theo origin/partition. | Token có thể nằm trong object store/cache mà UI quên xóa. | Xóa đúng record/store/database; chờ transaction hoàn tất. |
| **Service Worker** | Có vòng đời độc lập với trang; có thể dùng Cache API/IndexedDB. | Token và response nhạy cảm tồn tại ngoài component state. | Gửi thông điệp purge được xác minh, xóa storage thuộc service worker và xét unregister khi cần. |
| **Cache API / HTTP cache** | Có thể giữ bản sao response/dữ liệu. | Thông tin đơn hàng vẫn hiển thị sau logout, kể cả khi token đã mất. | Cache policy `no-store` và purge dữ liệu thuộc phiên. |
| **Cookie không HttpOnly** | Browser gửi theo domain/path/attrs. | Script cùng origin có thể đọc; cookie đi kèm request. | `document.cookie` chỉ tác động những cookie JS được phép truy cập. |
| **Cookie HttpOnly** | Browser tự gửi trong scope; JS không truy cập giá trị. | CSRF/session hijack, nếu server vẫn công nhận cookie. | **Server Set-Cookie expire** và **server invalidate session**. |

### Vì sao memory thường giảm lưu trữ bền?

Giữ access token **chỉ trong memory** có thể giảm nguy cơ token bị lấy từ storage bền sau khi đóng trang. Nhưng memory **không phải vùng bí mật tuyệt đối**: XSS đang chạy trong origin có thể đọc hoặc sử dụng token tùy cách lưu, cũng có thể thực hiện hành động trong phiên mà không cần lấy token.

### `localStorage` có phải luôn bị cấm?

Đánh giá phụ thuộc threat model, nhưng lưu **access/refresh token nhạy cảm** trong `localStorage` thường làm tăng tác động của XSS vì dữ liệu có thể được đọc và tồn tại lâu. Các khuyến nghị bảo mật hiện đại ưu tiên thiết kế **BFF hoặc token handler** khi khả thi. Nếu SPA trực tiếp giữ token, cần hiểu rủi ro và kiểm soát XSS/CSP, vòng đời lưu, session isolation, logout và token rotation/sender-binding theo profile.

**Xóa sau logout là biện pháp vệ sinh phiên, không làm an toàn một thiết kế lưu token sai từ đầu.**

## 5. Trình tự logout an toàn cho SPA

Một thứ tự hợp lý khi user bấm logout:

1. **Chuyển trạng thái sang `logging_out` ngay**, chặn UI tạo tác vụ cần authentication mới.
2. **Đánh dấu phiên/epoch cũ không hợp lệ** trong state quản lý của app.
3. **Ngắt hoặc bỏ qua kết quả API đang chạy**; hủy refresh timer và silent renewal.
4. Nếu Client sở hữu token để revoke, gửi **revocation request** an toàn khi còn credential cần dùng, hoặc gọi backend logout/BFF theo kiến trúc.
5. **Xóa bản sao credential** trong memory và các kho đã kiểm kê.
6. **Dọn dữ liệu ứng dụng theo user/tenant**: cache, draft riêng tư, query results, service worker stores.
7. **Thông báo các tab cùng origin** rằng phiên đã kết thúc; mỗi tab tự dọn state riêng.
8. Chuyển về màn hình chưa đăng nhập, tránh redirect lập tức qua silent SSO khiến UI bật lại.
9. Nếu remote revoke thất bại/timeout, ghi nhận **trạng thái không chắc chắn**; không tiếp tục dùng credential chỉ vì chưa được xác nhận.

~~~mermaid
flowchart TD
    A["User chọn Logout"] --> B["Đặt session epoch là invalid/logging_out"]
    B --> C["Chặn requests/refresh mới, hủy in-flight"]
    C --> D["Gọi remote logout/revoke nếu architecture yêu cầu"]
    D --> E["Xóa credential khỏi memory và local stores"]
    E --> F["Purge cache/dữ liệu riêng tư"]
    F --> G["Broadcast logout, các tab tự xóa memory"]
    G --> H["UI logged out; không silent relogin"]
    D --> I{"Remote revoke lỗi?"}
    I -- Có --> J["Ghi pending/error an toàn, không dùng token"]
    I -- Không --> H
~~~

Việc “revoke rồi mới xóa” có thể cần thiết khi chính Client chỉ có một bản token và không thể truy xuất lại; nhưng **không chờ network vô hạn trước khi vô hiệu trạng thái local**. Một BFF có thể ghi công việc revoke được kiểm soát rồi dọn phiên local, với quy trình xử lý retry và bí mật thích hợp.

## 6. JavaScript: xóa credential theo whitelist của ứng dụng

Đoạn sau minh họa logic SPA đang dùng **memory + một số key storage đã biết**. Nó **không phải OAuth Client hoàn chỉnh**, không tự thêm cơ chế remote revocation hay chống XSS.

~~~javascript
// Những key này CHỈ là ví dụ cho ứng dụng này.
const AUTH_LOCAL_KEYS = [
  "shop.accessToken",
  "shop.refreshToken",
  "shop.oauthTransaction"
];
const AUTH_SESSION_KEYS = [
  "shop.accessToken",
  "shop.pkceVerifier",
  "shop.pendingState"
];

const authState = {
  accessToken: null,
  refreshToken: null,
  identity: null,
  epoch: 0,
  loggedOut: false
};

function clearLocalCredentials() {
  // Chặn consumer dùng các reference cũ trước khi dọn storage.
  authState.loggedOut = true;
  authState.epoch += 1;
  authState.accessToken = null;
  authState.refreshToken = null;
  authState.identity = null;

  for (const key of AUTH_LOCAL_KEYS) {
    localStorage.removeItem(key);
  }
  for (const key of AUTH_SESSION_KEYS) {
    sessionStorage.removeItem(key);
  }
}
~~~

### Vì sao dùng whitelist?

`localStorage.clear()` sẽ xóa **mọi key cùng origin**, có thể ảnh hưởng các module/ứng dụng khác, tùy cách triển khai. Với logout riêng một tài khoản, cần biết **key nào chứa credential/PII của tài khoản đó**, và key nào là cấu hình không nhạy cảm dùng chung.

**Không bỏ qua IndexedDB, cache và service worker** chỉ vì ví dụ mới xóa local/sessionStorage. Không tin rằng `removeItem` sẽ xóa bản sao token còn nằm trong một closure, memory snapshot hoặc HTTP request đã được gửi đi.

### Không có “secure erase” bảo đảm trong JavaScript

JavaScript runtime có garbage collector; gán `null` loại reference, **không bảo đảm overwrite bytes trước đây trong heap**. Với browser storage, ứng dụng cũng không kiểm soát flash wear leveling, browser backups hoặc snapshot. Mục tiêu thực tế là **loại bỏ khả năng truy xuất thông thường và không dùng lại credential**, đồng thời thu hồi remote nếu cần.

## 7. Gọi logout ở BFF từ JavaScript

Nếu browser **chỉ giữ session cookie HttpOnly** và BFF giữ OAuth token phía server, frontend không cần — và không nên — đọc access/refresh token để gọi RFC 7009.

~~~javascript
async function logoutFromBff(csrfToken) {
  // Đánh dấu UI local logged-out trước để ngăn tác vụ mới.
  clearLocalCredentials();

  try {
    const response = await fetch("/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-TOKEN": csrfToken },
      cache: "no-store",
      redirect: "manual"
    });
    if (!response.ok && response.status !== 204) {
      // Không log cookie, CSRF token hoặc token (nếu có).
      throw new Error("Logout request not confirmed");
    }
  } catch {
    // Phải báo rõ trạng thái server chưa chắc đã logout.
    // Có thể cho retry hoặc hướng user đóng phiên/tìm session management.
    showLogoutServerUncertainWarning();
  }

  // Chỉ thực hiện chuyển trang khi local UI đã ngừng dùng credential.
  showSignedOutScreen();
}
~~~

**Đây là đoạn minh họa cho mô hình BFF**, không là thư viện UI chạy độc lập: các hàm `clearLocalCredentials`, `showLogoutServerUncertainWarning`, `showSignedOutScreen` do ứng dụng định nghĩa. CSRF header name, token acquisition, cookie policy và logout endpoint phụ thuộc framework. Không in `csrfToken` vào log.

### Một lỗi trong thứ tự cleanup

Nếu ứng dụng xóa CSRF token **trước** khi gửi logout POST, request có thể bị 403. Khi triển khai cần **giữ giá trị CSRF cần thiết trong memory trong thời gian gửi request**, đồng thời vô hiệu hóa các API/refresh hoạt động khác. Sau response/timeout thì xóa reference còn lại. Mục tiêu là không để credential tiếp tục được sử dụng nghiệp vụ trong lúc logout đang tiến hành.

### UI có thể báo "đã đăng xuất" khi server lỗi không?

Có thể báo **đã rời phiên ở giao diện hiện tại**, nhưng nếu server không xác nhận đã invalidate session/revoke tokens, nên có thông báo chính xác rằng **trạng thái remote chưa chắc chắn**. Không gắn nhãn “thu hồi toàn bộ access token thành công” chỉ vì local storage đã trống.

## 8. Nhiều tab: xóa một tab chưa đủ

Browser có nhiều tab cùng origin:

~~~text
Tab A: memory access token A, refresh timer A
Tab B: memory access token A, refresh timer B
Tab C: pending OIDC callback/PKCE transaction

User logout ở Tab A.

Nếu chỉ Tab A dọn:
  Tab B có thể tiếp tục gọi API;
  Tab C có thể hoàn tất callback và tạo session mới.
~~~

### `BroadcastChannel` như tín hiệu trạng thái

~~~javascript
const logoutChannel = new BroadcastChannel("shop-auth-events");

logoutChannel.onmessage = (event) => {
  if (event.data?.type !== "LOGOUT") return;
  clearLocalCredentials();
  cancelRefreshTimersAndAuthenticatedRequests();
  showSignedOutScreen();
};

function announceLogout() {
  logoutChannel.postMessage({ type: "LOGOUT" });
}
~~~

**Không gửi access token, refresh token, client secret hoặc session cookie qua channel**. Đây chỉ là **thông điệp phối hợp UI**, không phải bằng chứng bảo mật: JavaScript cùng origin hoặc XSS có thể phát thông điệp giả. Bên server vẫn phải từ chối session/token đã bị vô hiệu hóa.

### `storage` event và `sessionStorage`

- `localStorage` thường phát **`storage` event** cho các context khác cùng origin khi một key được thay; tab gây sự kiện không nhận event của chính nó.
- `sessionStorage` được phân tách theo top-level context; xóa ở tab A **không tự xóa sessionStorage ở tab B**.
- `BroadcastChannel` cũng cần code chạy trong các tab, không bảo đảm một tab đang ngủ/offline xử lý ngay.
- Khi một tab thức dậy hoặc nhận focus, nó nên **kiểm tra lại trạng thái session phía server hoặc epoch tin cậy** trước khi hiển thị dữ liệu nhạy cảm.

### Dùng “auth epoch” để tránh UI cũ ghi đè

~~~javascript
const requestEpoch = authState.epoch;
const response = await fetch("/api/orders", { credentials: "include" });

if (authState.loggedOut || requestEpoch !== authState.epoch) {
  // Bỏ kết quả response thuộc phiên trước.
  return;
}
renderOrders(await response.json());
~~~

Ví dụ chỉ minh họa check phiên cho một request. Trên thực tế nên **check lại sau thao tác bất đồng bộ cuối cùng** trước khi ghi state/UI, quản lý AbortController và cache theo user/tenant. Nếu không, response chậm từ phiên cũ có thể vẽ lại dữ liệu sau logout.

## 9. Service Worker, IndexedDB và cache nhạy cảm

Một PWA có thể lưu dữ liệu auth hoặc API response trong:

- IndexedDB record store.
- Cache Storage (`caches.open(...)`).
- Memory của service worker hoặc worker được khởi động lại.
- Offline request queue, background sync tasks.
- HTTP caching hoặc application query cache.

**Không nên cache response chứa Bearer token hoặc dữ liệu người dùng nhạy cảm bằng chính sách cache rộng**; nếu phải hỗ trợ offline, cần phân vùng theo user/tenant, encryption/expiry phù hợp và cơ chế xóa rõ.

### Pseudocode purge theo namespace

~~~javascript
async function purgeShopUserCache() {
  const names = await caches.keys();
  const owned = names.filter((name) =>
    name.startsWith("shop-private-"));
  await Promise.all(owned.map((name) => caches.delete(name)));

  // Các IndexedDB object stores chứa token/private data
  // phải được xóa bằng transaction riêng; xem DB schema thật.
}
~~~

**`caches` có thể không khả dụng trong mọi browser/context**; code production cần feature detection, error handling và không giả định xóa Cache API là đã xóa IndexedDB. Không xóa bừa **mọi cache cùng origin** nếu một origin phục vụ nhiều ứng dụng.

### Thông báo service worker

~~~text
Page:
  phát thông điệp PURGE_USER_DATA tới service worker được quản lý
  chờ ACK có định danh request/epoch khi có thể
  đánh dấu logout ở state đáng tin

Service Worker:
  từ chối queue task mới cho phiên cũ
  xóa credential / private caches thuộc user/tenant
  trả ACK trạng thái đã thực hiện
~~~

**Không coi thông điệp ACK của worker là bằng chứng remote token đã revoked.** Một service worker hoặc tab cũ bị lỗi có thể giữ dữ liệu; cần cơ chế server session invalidation và hạn token đủ phù hợp. Với dữ liệu nhạy cảm, thiết kế PWA offline cần được đánh giá riêng.

### `Clear-Site-Data`

Browser hỗ trợ có thể xử lý response header:

~~~http
Clear-Site-Data: "cache", "storage"
~~~

Header này có phạm vi ảnh hưởng và mức hỗ trợ theo browser. `"cookies"` có thể xóa rộng hơn dự kiến (tùy domain/browser), `"executionContexts"` ảnh hưởng contexts đang mở. **Không dùng Clear-Site-Data làm giải pháp mặc định duy nhất** cho logout của một user nếu cùng origin có nhiều ứng dụng hoặc cần giữ dữ liệu offline khác; kiểm tra hỗ trợ, phạm vi và side effects.

## 10. Cookie HttpOnly: JavaScript không tự xóa được

Một thiết kế BFF tốt thường chỉ đặt **opaque session reference** vào cookie:

~~~http
Set-Cookie: __Host-shop_session=<RANDOM_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Với prefix `__Host-`, cookie phải được tạo trong ngữ cảnh bảo mật phù hợp, có `Secure`, `Path=/` và **không có `Domain`**. `HttpOnly` giúp JavaScript không đọc cookie qua `document.cookie`; không ngăn browser tự gửi cookie theo cookie policy.

### Tại sao `document.cookie = "...; Max-Age=0"` không đủ?

Script không thể ghi đè/xóa cookie **HttpOnly** bằng `document.cookie` trong những browser tuân thủ quy tắc cookie. Client cần gọi **backend logout endpoint**, để server:

1. **Invalidate session server-side** hoặc xóa session record khỏi store.
2. Xóa server-side OAuth authorized client/tokens theo kiến trúc và remote revocation policy.
3. Trả **`Set-Cookie` hết hạn** cho **đúng tên, Path và Domain/host-only context**.

~~~http
HTTP/1.1 204 No Content
Set-Cookie: __Host-shop_session=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Ví dụ dùng cookie **host-only** và `Path=/`. Nếu cookie ban đầu có `Domain` khác (không phải `__Host-`), phải hết hạn cookie theo đúng **name/domain/path** mà browser dùng; chỉ đổi `SameSite` không tạo cookie khác, nhưng cần giữ thuộc tính bảo mật phù hợp và kiểm thử browser thực tế.

### Xóa cookie không đồng nghĩa hủy session

Nếu server chỉ gửi cookie hết hạn mà **không vô hiệu hóa session ID trong database/cache**, attacker có bản sao cookie cũ vẫn có thể trình lại session ID tới server. Backend **phải invalidate session** để cả bản sao bên ngoài cũng không còn được công nhận.

### Những cookie dễ bị bỏ quên

| Cookie | Vị trí | Cần xử lý |
|---|---|---|
| BFF session cookie | Browser ↔ BFF. | Invalidate session + expire cookie. |
| AS/OP SSO session cookie | Browser ↔ Authorization Server. | Không bị BFF xóa do khác origin; dùng OP logout theo profile nếu cần. |
| CSRF cookie (nếu có) | Origin ứng dụng. | Xoay/xóa theo session, tránh tái sử dụng ở phiên mới. |
| Legacy session cookie ở Path khác | Cùng host hoặc subpath. | Inventory và expire đúng Path/Domain; không bỏ sót. |
| Third-party analytics cookie | Không phải OAuth credential. | Theo chính sách quyền riêng tư, không tự xóa tùy tiện mọi cookie. |

## 11. BFF logout: xóa reference, hủy session và xử lý token store

**Backend for Frontend** giữ access/refresh token trong server-side token store, còn browser dùng session cookie. Một quy trình phù hợp:

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant F as BFF
    participant Store as Session / Token Store
    participant AS as Authorization Server
    participant RS as Orders API
    U->>B: Logout
    B->>F: POST /logout (session cookie + CSRF proof)
    F->>Store: Mark session closing, stop token refresh
    F->>Store: Lấy token thuộc đúng session/grant để xử lý revoke
    F->>AS: POST /revoke refresh token (nếu policy/capability cho phép)
    AS-->>F: HTTP 200 hoặc lỗi/timeout
    F->>Store: Invalidate session + local token references
    F-->>B: 204 + Set-Cookie Max-Age=0
    B->>B: Clear UI state/cache, notify other tabs
    Note over F,RS: Stolen access JWT có thể sống tới exp nếu RS không kiểm tra revoke state
~~~

### Vì sao phải khóa phiên trước?

Nếu user bấm logout trong lúc refresh timer chuẩn bị gửi `grant_type=refresh_token`, quy trình không kiểm soát có thể:

~~~text
T0: Logout bắt đầu.
T1: BFF revoke refresh token R1.
T2: Một worker vẫn đọc token R2 trong cache và refresh thành công.
T3: Local state bị ghi lại access token mới sau khi logout.
~~~

Hệ thống nên dùng **session state/epoch và cập nhật nguyên tử** để ngăn token mới được tái gắn vào session đã logout, đồng thời đánh giá token family/grant được revoke ở AS.

### Token store cần có key ngữ cảnh

~~~text
authorized_client_record:
  principal_id = user-123
  tenant_id    = tenant-a
  client_id    = shop-web
  issuer       = https://auth.example.test
  grant_ref    = grant-42
  access_ref   = encrypted-or-protected-value
  refresh_ref  = encrypted-or-protected-value
  session_ref  = opaque-session-A
~~~

Ví dụ chỉ là **schema khái niệm**. Trước khi xóa, phải chắc record thuộc đúng **user/tenant/client/issuer/session**, không dùng một biến `currentToken` toàn cục có thể gây xóa nhầm token của người dùng khác.

### Khi remote revocation thất bại

Không giữ session hợp lệ chỉ để chờ AS hết lỗi. Một lựa chọn thiết kế:

1. Chặn sử dụng credential tại BFF ngay.
2. Ghi một **retry job được bảo vệ/TTL ngắn** chứa reference hoặc credential được mã hóa nếu thật sự cần, không in raw token ra log.
3. Invalidate session/authorized client local.
4. Retry revocation có giới hạn theo policy; nếu không thể hoàn tất, cảnh báo vận hành và user theo mức rủi ro.

**Không có chiến lược retry vô hạn phù hợp cho mọi hệ thống.** Cần tính đến retention, quyền truy cập queue và nguy cơ giữ refresh token lâu ngoài ý muốn.

## 12. Java/Spring Security: invalidate session và expire cookie

Spring Security thường cung cấp logout handling cho session authentication. Ví dụ sau tập trung vào **server session và cookie cleanup**; nó **không tự gọi AS revocation endpoint**.

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SessionLogoutSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .csrf(csrf -> {}) // Giữ CSRF cho POST /logout.
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler((request, response, auth) -> {
                    ResponseCookie deleteCookie = ResponseCookie
                            .from("__Host-shop_session", "")
                            .path("/")
                            .secure(true)
                            .httpOnly(true)
                            .sameSite("Lax")
                            .maxAge(Duration.ZERO)
                            .build();
                    response.addHeader(HttpHeaders.SET_COOKIE,
                            deleteCookie.toString());
                    response.setHeader(HttpHeaders.CACHE_CONTROL,
                            "no-store");
                    response.setStatus(204);
                }));
        return http.build();
    }
}
~~~

**Giới hạn của ví dụ:** `__Host-shop_session` là **cookie giả định do ứng dụng cấu hình**, không phải tên mặc định của Spring `JSESSIONID`. Nếu ứng dụng dùng `JSESSIONID` hoặc Spring Session với cookie name/path khác, cần hết hạn **cookie thật**. Phải kiểm tra các filter chain, session store và các authentication mechanism khác để bảo đảm logout handler thực sự chạy.

### Không chỉ một dòng `invalidateHttpSession(true)`

Ví dụ này giúp hủy phiên servlet hiện hành và hết hạn cookie do mẫu quy định. Trong hệ thống sử dụng **Spring OAuth2AuthorizedClientService/Repository**, cần thêm logic **xóa token record local và remote revoke** cho grant tương ứng theo chính sách. Không suy rằng xóa `SecurityContext` sẽ thu hồi access/refresh token tại AS.

### Không thêm disable CSRF chỉ để logout “cho tiện”

~~~java
// ANTI-PATTERN:
// http.csrf(AbstractHttpConfigurer::disable);
// rồi tạo GET /logout để không phải gửi CSRF.
~~~

Logout POST dựa trên browser session cần CSRF defense phù hợp. Forced logout CSRF có thể làm gián đoạn phiên; ở hệ thống có SSO và callback tự động, nó còn tạo các rủi ro nhầm trạng thái. Đăng xuất không phải thao tác đọc **an toàn với GET**.

### Cookie deletion là một side effect

Một Client gửi `POST /logout` rồi nhận 204 nhưng cookie vẫn còn vì server expire sai `Path`/`Domain`. Browser vẫn có thể gửi cookie đó, dù session record đã bị invalid. **Kiểm thử phải xem cả Set-Cookie và request sau logout**, không chỉ HTTP status.

## 13. Spring Security: local authorized-client cleanup khác revocation

Trong Spring Security OAuth2 Client, một số ứng dụng lưu OAuth tokens thông qua `OAuth2AuthorizedClientService`. Một thao tác xóa record local có thể như:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

final class AuthorizedClientCleanup {
    private final OAuth2AuthorizedClientService authorizedClients;

    AuthorizedClientCleanup(OAuth2AuthorizedClientService service) {
        this.authorizedClients = service;
    }

    void removeLocal(String registrationId, String principalName) {
        authorizedClients.removeAuthorizedClient(
                registrationId, principalName);
    }
}
~~~

**`removeAuthorizedClient` không tự gọi RFC 7009.** Phải biết ứng dụng dùng service hay repository nào, và dữ liệu được gắn với principal/registration ID nào. Nếu người dùng kết nối nhiều IdP/Client/tenant, không gọi xóa tất cả record bằng một tên principal chung khi logout chỉ một kết nối.

### Lập thứ tự theo architecture

~~~text
1. Lookup đúng grant/tokens trước khi mất quyền truy cập token store.
2. Mark session/connection closing; chặn refresh/token usage mới.
3. Attempt AS revocation hoặc schedule protected retry.
4. Invalidate session và remove authorized-client record local.
5. Clear cookie ở browser; purge caches/notify tabs.
6. Verify RS behavior và audit theo yêu cầu rủi ro.
~~~

Nếu token bị lộ, **thao tác thứ ba không phải tùy chọn nghiệp vụ không đáng kể**. Nhưng nó cũng không nên khiến bước (4) bị trì hoãn vô hạn trong lúc mạng/AS lỗi.

### Bảo mật Client secret trong logout

Confidential BFF dùng `client_secret_basic`, `private_key_jwt` hoặc mTLS để gọi AS nếu registration yêu cầu. Client secret/private key phải được bảo vệ trong secret manager/keystore. **Không gửi client secret xuống SPA** chỉ để nó “tự revoke”.

## 14. OAuth token revocation: xóa phía client chưa đủ

Theo **RFC 7009**, OAuth Client có thể gửi request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<URL_FORM_ENCODED_REFRESH_TOKEN>&token_type_hint=refresh_token
~~~

**Điều kiện:** endpoint của trusted AS, HTTPS/TLS, client authentication theo đăng ký, token thuộc Client/authorization grant được phép. `token_type_hint` là gợi ý lookup; không phải quyền chứng minh token là loại ấy.

### Kết quả 200 không có nghĩa mọi access token chết ngay

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

RFC 7009 dùng phản hồi thành công tương tự cả khi token đã bị revoke hoặc token không hợp lệ (sau các kiểm tra phù hợp), để giảm token enumeration. Client không thể suy từ `200` rằng AS đã tìm thấy token hay **tất cả RS đã biết trạng thái revoke**.

### Refresh và access token có vòng đời khác nhau

| Hành động | Hệ quả chính | Cần kiểm tra thêm |
|---|---|---|
| **Revoke refresh token R** | R không còn xin access token mới sau khi hiệu lực. | AS có cascade sang access token và token family không? |
| **Revoke access token A** (nếu hỗ trợ) | A bị AS vô hiệu theo cơ chế. | RS biết revocation qua introspection/denylist/cache không? |
| **Revoke grant** | Hủy ủy quyền Client theo scope/resource/user. | Refresh token family, pending request, multiple sessions. |
| **Disable Client credential** | Chặn Client chứng minh danh tính để xin token mới. | Token đã phát hành vẫn có thể còn hạn. |

Theo RFC 7009, AS phải hỗ trợ **refresh token revocation**; hỗ trợ access token revocation là một khuyến nghị `SHOULD`. Đối với refresh token được revoke, AS được khuyến nghị có thể vô hiệu access token thuộc cùng grant nếu có hỗ trợ. Mức cascade cụ thể cần được xác định theo AS.

**Xóa local token sau khi remote revoke không thay thế xác minh rằng RS thực sự từ chối token đã bị đánh cắp.**

## 15. JWT, opaque token và cửa sổ sau logout

### Opaque access token

RS có thể hỏi AS qua **RFC 7662 Token Introspection**:

~~~json
{
  "active": false
}
~~~

AS trả `active=false` khi token không còn active theo hợp đồng introspection, nhưng RS có thể cache `active=true` trước đó. **Revocation propagation latency** phụ thuộc cache TTL, replication và network. Nếu API cần chặn ngay, phải đặt cache policy và invalidation phù hợp.

### JWT access token

Một JWT có thể mang:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "jti": "token-a1",
  "iat": 1893456000,
  "exp": 1893456600
}
~~~

Đây là **payload minh họa**, không phải JWT hợp lệ để triển khai. Nếu RS chỉ kiểm tra **chữ ký/JWKS, issuer, audience, thời hạn và scope**, JWT A vẫn có thể được chấp nhận tới `exp` **dù browser đã xóa bản sao token và AS đã revoke refresh token**.

### Các lựa chọn kiểm soát

| Cách | Tác dụng | Đánh đổi |
|---|---|---|
| **Short-lived JWT** | Giới hạn thời gian access token bị lạm dụng sau logout. | Không chặn ngay khi token còn hạn. |
| **JWT denylist theo `(issuer,jti)` hoặc token fingerprint** | RS có thể từ chối token trước `exp`. | Phải quản lý cache, TTL và trạng thái phân tán. |
| **Grant/session version check** | Từ chối token mang version cũ sau khi grant bị revoke. | Cần lookup trạng thái ở RS, chống race và tenant confusion. |
| **Opaque token + introspection** | AS quyết định `active` tập trung. | RS phụ thuộc AS/network, cache có độ trễ. |
| **DPoP/mTLS-bound token** | Giảm khả năng bản sao token bị dùng nếu thiếu khóa/chứng chỉ. | Không thay revocation, máy/khóa bị chiếm vẫn nguy hiểm. |

**Không tự xóa `kid` hoặc khóa JWKS chỉ để logout một user.** Signing key rotation ảnh hưởng nhiều token và là vấn đề quản trị key; user logout thường xử lý grant/token/session riêng biệt.

## 16. OIDC logout và SSO: hai phiên khác nhau

Một ứng dụng OIDC có thể quản lý:

~~~text
RP/Client local session:
  shop.example.test

OP/SSO browser session:
  auth.example.test

OAuth grant:
  user-123 -> shop-web -> orders:read
~~~

Hủy session của **Relying Party (RP)** không mặc định hủy session tại **OpenID Provider (OP)**. Nếu OP session vẫn còn, một lần login mới có thể **tự động xác thực lại** bằng session SSO mà không hiện form mật khẩu. Điều đó không có nghĩa RP logout bị lỗi, mà là **đăng xuất local và SSO logout khác phạm vi**.

### RP-Initiated Logout

Nếu OP hỗ trợ **OpenID Connect RP-Initiated Logout 1.0**, RP có thể đưa browser tới **`end_session_endpoint`** đã được OP công bố:

~~~http
GET /oidc/logout?id_token_hint=<ID_TOKEN_HINT>&post_logout_redirect_uri=https%3A%2F%2Fshop.example.test%2Fsigned-out&state=<RANDOM_LOGOUT_STATE> HTTP/1.1
Host: auth.example.test
~~~

Request là **minh họa**. Việc dùng `id_token_hint`, `post_logout_redirect_uri` và `state` tùy OP/profile. **`post_logout_redirect_uri` cần được đăng ký/chấp nhận theo cơ chế OP**, không là open redirect. Nếu URL chứa `id_token_hint`, phải cân nhắc bảo mật URL/log/browser history/referrer và ưu tiên luồng/profile an toàn được OP hỗ trợ; không đưa access/refresh token vào query để logout.

### Phân biệt các tín hiệu

| Tín hiệu | Ý nghĩa |
|---|---|
| **RP local logout** | Ứng dụng đã ngừng công nhận session của user. |
| **OP logout** | Provider đã xử lý session SSO của user theo chính sách. |
| **Front-channel/Back-channel logout** | Cơ chế phối hợp logout tới các RP theo profile nếu hỗ trợ; cần xác minh message/issuer/audience khi tương ứng. |
| **OAuth revocation** | Thu hồi token/grant tại AS, không mặc định xảy ra vì RP/OP logout. |

**OIDC `id_token` không phải access token**, và không được dùng thay token revoke hoặc credential RS. Client cần quản lý ID token theo OIDC và session state của mình.

## 17. Ngăn silent relogin và “token sống lại”

Một trải nghiệm gây hiểu nhầm:

~~~text
T0: User bấm Logout.
T1: SPA xóa access token.
T2: Auth guard thấy chưa có token -> tự start OIDC login.
T3: OP vẫn có SSO session.
T4: OP hoàn thành nhanh -> Client nhận token mới.
T5: UI lại hiện đã đăng nhập.
~~~

Đây có thể là **silent reauthentication**, không nhất thiết là việc “xóa token thất bại”. Khi logout:

- Cập nhật **user-initiated logout flag/epoch** ở trạng thái ứng dụng phù hợp.
- Tắt **automatic token renewal**, iframe silent check hoặc login redirect ngay trong luồng signed-out.
- Hủy pending OAuth/PKCE transactions, `state`/`nonce` của phiên cũ theo policy.
- Không xử lý callback từ trước logout như một phiên đăng nhập hợp lệ; kiểm tra transaction/session/issuer.
- Nếu user thực sự muốn **SSO logout**, dùng OP logout profile, không tự xóa cookie khác origin bằng JavaScript.
- Khi user chủ động đăng nhập lại, tạo transaction/state/nonce/PKCE verifier **mới**.

### State machine gợi ý

~~~mermaid
stateDiagram-v2
    [*] --> Authenticated
    Authenticated --> LoggingOut: User click Logout
    LoggingOut --> SignedOutLocal: Local session/tokens cleared
    SignedOutLocal --> SignedOutRemote: AS revocation / OP logout confirmed (nếu yêu cầu)
    SignedOutLocal --> RevocationUncertain: Network/AS failure
    RevocationUncertain --> SignedOutRemote: Retry/verification succeeds
    SignedOutLocal --> LoginRequested: User explicitly starts login
    SignedOutRemote --> LoginRequested: User explicitly starts login
    RevocationUncertain --> LoginRequested: Chính sách cho phép login lại
    LoginRequested --> Authenticated: New valid transaction completed
~~~

**Không cần chờ OP logout mới có thể kết thúc phiên local**. Một số hệ thống chỉ thực hiện RP-local logout theo yêu cầu sản phẩm; phải nói rõ phạm vi đó.

## 18. Race conditions và request đang chạy

### Logout vs refresh-token rotation

~~~mermaid
sequenceDiagram
    participant UI as Browser/Client
    participant W as Refresh Worker
    participant AS as Authorization Server
    UI->>W: Refresh timer đã lên lịch
    UI->>UI: User logout, session epoch tăng
    W->>AS: refresh R1 (đang chạy từ trước)
    AS-->>W: Access token A2 + refresh R2
    W->>W: Kiểm tra epoch/session đã invalid
    W-->>UI: Không lưu A2/R2 vào session đã logout
    W->>AS: Revoke R2/grant nếu hợp đồng và policy yêu cầu
    UI->>UI: UI vẫn Signed Out
~~~

**Hủy request bằng AbortController chỉ hủy việc chờ/transport ở phía Client**; nếu request đã tới AS, AS vẫn có thể xử lý refresh. Vì vậy cần **guard ở bước ghi state** và quy tắc xử lý token R2 phát hành sau khi logout bắt đầu.

### Race với API response

Nếu một request đọc Orders được gửi trước logout, response đến sau:

- Không ghi kết quả vào cache/user state của phiên đã bị hủy.
- Không hiển thị dữ liệu user cũ khi account mới đăng nhập.
- Dọn query cache theo **principal/tenant**, không dùng cache key `orders` chung cho mọi user.
- Không gửi retry của API cũ bằng token mới của user khác.

### Race với callback login cũ

Nếu user bắt đầu đăng nhập rồi bấm Cancel/Logout trước khi callback đến, callback cần kiểm tra **state/PKCE transaction đã còn hợp lệ**. Một code cũ không được tạo session mới sau khi transaction bị hủy. AS vẫn phải enforce short-lived one-time code, redirect/client binding và PKCE.

## 19. Thiết bị mobile/native: xóa token khỏi kho hệ điều hành

Ứng dụng native có thể giữ token ở:

- **iOS Keychain**, khi app chọn thuộc tính protection/accessibility phù hợp.
- **Android Keystore** (giữ key), kết hợp nơi lưu **dữ liệu token được mã hóa** theo kiến trúc.
- Keychain/credential store của desktop OS.
- Database ứng dụng, preferences, file offline cache hoặc process memory.

**Android Keystore thường lưu khóa mật mã**, không phải một kho chung để lưu raw OAuth token như object đơn giản; token có thể nằm ở Encrypted DataStore/preferences/file được bảo vệ bằng key. Phải xóa cả **entry token** và những key riêng phiên khi phù hợp.

### Quy trình native logout

1. Chặn tạo request và refresh timer.
2. Nếu có network, yêu cầu AS revoke refresh token/grant theo registration (public Client không có shared client secret đáng tin).
3. Xóa token đã lưu trong protected storage và memory.
4. Xóa data cache, background job, pending sync và notification chứa dữ liệu riêng tư.
5. Nếu có Web SSO, quyết định có gọi OP logout qua system browser hay chỉ kết thúc phiên của app.
6. Với device unlink, revoke device/session/grant ở backend theo profile.
7. Hỗ trợ offline logout: đánh dấu phiên local invalid ngay, retry remote revoke khi kết nối trở lại nếu khả thi và policy cho phép.

### Keychain có thể tồn tại khác kỳ vọng

Tùy hệ điều hành, backup, nhóm keychain và thuộc tính item, một credential có thể còn sau **uninstall/reinstall** hoặc khi khôi phục dữ liệu. Không coi uninstall là bằng chứng bảo mật rằng token đã biến mất và grant AS đã bị thu hồi. Ứng dụng nên đánh giá retention/backup/exclusion và các trường hợp chuyển thiết bị, mất thiết bị.

### Không ghi raw token vào log mobile

Mobile debug log, crash reporter, analytics, screenshot và share sheet có thể giữ token/PII ngoài kho secure storage. Logout không xóa được bản sao đã được thu thập từ trước; cần **ngăn lộ từ đầu** và xử lý sự cố khi phát hiện.

## 20. Thiết bị offline và quá trình đồng bộ

Một thiết bị có thể offline khi user chọn logout:

~~~text
T0: Device đang offline.
T1: User chọn Logout.
T2: Device xóa local token/cache và đánh dấu session closed.
T3: Không thể gọi AS revocation.
T4: Device lên mạng.
T5: Nếu có cơ chế bảo vệ phù hợp, đồng bộ yêu cầu revoke
    hoặc backend đã quản lý grant/device và tiếp tục xử lý.
~~~

### Hai mục tiêu cần phân biệt

- **Local privacy:** người đang cầm thiết bị không được tiếp tục xem dữ liệu đã lưu sau logout.
- **Remote invalidation:** token/grant tại AS/RS không còn sử dụng được.

Nếu ứng dụng xóa refresh token trước khi có cách chuyển remote revoke, có thể **không còn token để gửi RFC 7009** sau khi online. Một thiết kế phù hợp có thể dùng server-managed grant/device identifier và endpoint được xác thực cho unlink, hoặc một **protected pending-revocation record** với TTL/retry. Không giữ raw refresh token không mã hóa trong hàng đợi offline chỉ để “thu hồi sau”.

### Không tự cấp quyền offline sau logout

- Không để cached `isAuthenticated=true` mở lại dữ liệu riêng tư.
- Không tiếp tục replay offline mutation queue dưới danh tính phiên cũ.
- Không cho background sync “tự login” chỉ vì còn refresh token ở storage khác.
- Khi có connectivity trở lại, revalidate session/grant hoặc yêu cầu login mới trước khi lấy dữ liệu.

## 21. Đăng xuất không chữa được XSS hay token bị đánh cắp

### Trường hợp token bị exfiltrate

~~~text
T0: SPA giữ bearer access token A trong localStorage.
T1: XSS sao chép A tới attacker.
T2: User logout; localStorage.removeItem("accessToken") thành công.
T3: Attacker vẫn giữ A và gọi Orders API.
T4: Nếu A chưa exp và RS không biết revoke, request có thể được chấp nhận.
~~~

**Xóa local storage không thu hồi bản sao ngoài tầm kiểm soát.** Cần incident response, revoke grant/refresh token, access-token state, TTL/sender proof và sửa XSS.

### Những lớp cần kết hợp

| Lớp | Giảm rủi ro nào? |
|---|---|
| **CSP, escaping, tránh XSS** | Giảm khả năng script độc hại đọc token hoặc hành động trong phiên. |
| **BFF + HttpOnly session cookie** | Giảm nhu cầu đưa OAuth token vào JavaScript. |
| **HTTPS/TLS và log redaction** | Giảm lộ token qua transport, telemetry và support. |
| **PKCE cho Authorization Code** | Giảm lạm dụng authorization code bị chặn/cấy vào callback. |
| **Refresh-token rotation/reuse detection** | Giảm khả năng dùng refresh token bị sao chép kéo dài. |
| **Revocation + RS state** | Chặn token/grant đã mất hiệu lực trước TTL theo thiết kế. |
| **DPoP/mTLS-bound token** | Giảm replay bearer token khi chỉ có bản sao token, không có key. |
| **Audience, scope, object authorization** | Hạn chế sai API/action, tenant và quyền trên dữ liệu. |

**PKCE không bảo vệ access token đã phát hành khỏi replay.** **HttpOnly không ngăn XSS điều khiển UI/gửi request**. **CSP không tự vô hiệu token đã lộ**. Các biện pháp là những lớp kiểm soát khác nhau.

## 22. Logout CSRF, cookie policy và redirect an toàn

### Logout CSRF

Một trang attacker có thể cố gửi form hoặc request tới endpoint logout trên origin ứng dụng của nạn nhân. Nếu endpoint chỉ dựa vào session cookie và không có CSRF defense, attacker có thể khiến user bị **đăng xuất ngoài ý muốn**, gây gián đoạn hoặc phối hợp các kiểu login CSRF/session confusion trong ứng dụng thiết kế yếu.

### Quy tắc thực hành

1. Dùng **POST** cho hành động logout thay đổi session, không dùng GET cho endpoint mutation trong ứng dụng.
2. Bảo vệ bằng **CSRF token hoặc cơ chế tương đương phù hợp** theo framework; kiểm tra Origin/Fetch Metadata bổ sung khi có.
3. Đặt session cookie `Secure; HttpOnly; SameSite` phù hợp với luồng login/redirect; **SameSite không thay CSRF token**.
4. Chống open redirect ở tham số `return_to`/`post_logout_redirect_uri`.
5. Không đặt raw access/refresh token trong URL của logout, `Location` header hoặc query `next`.
6. Không chỉ ẩn nút Logout bằng CSS và cho rằng session đã kết thúc.

### Phân biệt CSRF và CORS

**CORS không phải authorization**; chặn JavaScript đọc response cross-origin không luôn chặn browser gửi request mang cookie theo policy. Nếu browser dùng cookie để đăng xuất qua BFF, **CSRF protection** cần được phân tích riêng.

### Cookie SameSite và OIDC logout

Một số luồng OIDC front-channel hoặc callback có các hành vi cookie khác nhau giữa **same-origin, same-site và cross-site**. `SameSite=Strict` có thể chặn cookie trong ngữ cảnh redirect không phù hợp; `SameSite=None` đòi `Secure` trong browser hiện đại và tăng CSRF surface. **Không đổi bừa SameSite** để logout “hết lỗi”; cần kiểm thử toàn bộ SSO/logout flow theo profile.

## 23. Tránh lộ dữ liệu sau logout qua cache và lịch sử trình duyệt

Ngay cả khi token đã biến mất, browser có thể còn:

- Dữ liệu Orders trong component state/query cache.
- HTML/API response đã được cache.
- Trang được khôi phục bằng **back-forward cache (bfcache)** với DOM/state cũ.
- Download, export file và clipboard mà user đã tạo.
- Tab/iframe vẫn hiển thị dữ liệu cho tới khi được cập nhật.

### Chính sách response dữ liệu nhạy cảm

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "orders": ["<REDACTED_FOR_EXAMPLE>"]
}
~~~

`Cache-Control: no-store` giúp giảm caching của response phù hợp nhưng **không chứng minh mọi bản sao UI/download/backups đều được xóa**, và hành vi bfcache thay đổi theo browser. Ứng dụng vẫn phải dọn UI state khi logout, kiểm tra lại session khi page được phục hồi/focus và không hiển thị dữ liệu từ account trước sau khi chuyển account.

### Back/Forward navigation

~~~javascript
window.addEventListener("pageshow", async (event) => {
  if (event.persisted) {
    // Trang có thể được phục hồi từ bfcache.
    // Không render dữ liệu nhạy cảm từ phiên cũ trước khi
    // xác nhận auth state với hệ thống tin cậy.
    hideSensitiveContentUntilSessionChecked();
    await checkCurrentServerSession();
  }
});
~~~

Đây là ví dụ minh họa; các hàm do ứng dụng định nghĩa. Không dựa **chỉ vào `pageshow`** để chặn dữ liệu đã hiện trước đó trong một DOM được restore; kiến trúc có dữ liệu nhạy cảm cần ngăn lộ bằng policy/thiết kế phù hợp.

### Download và clipboard

Logout không thu hồi được file PDF/CSV đã tải về, ảnh chụp màn hình hoặc dữ liệu đã sao chép vào clipboard của user/attacker. Nếu có dữ liệu cần kiểm soát sau phiên, đó là yêu cầu **data protection/DRM/data lifecycle** riêng, không giải quyết bằng xóa token.

## 24. Chuyển tài khoản và nhiều tenant

Chuyển từ user A sang user B **không chỉ là đổi `displayName`**. Cần xóa state thuộc A trước khi dùng token B:

~~~text
User A, tenant-a:
  token A
  cache key = orders:tenant-a:user-A
  refresh timer A

Switch to user B, tenant-b:
  stop timer A
  clear A tokens/session references as architecture requires
  purge/cache-partition user A data
  start new login/grant transaction for B
  verify issuer/audience/tenant in new token
~~~

### Ba nguy cơ chính

1. **Cross-account leakage:** query cache không có user/tenant key làm B thấy danh sách đơn của A.
2. **Wrong-token request:** HTTP interceptor vẫn giữ Authorization header của A sau switch.
3. **Wrong-grant revoke:** cleanup code của B xóa refresh token/grant A hoặc ngược lại do cache key thiếu Client/issuer/tenant.

### Token store key nên có đủ ngữ cảnh

~~~text
(trusted_issuer, oauth_client_registration_id,
 authenticated_principal, tenant, grant_id, session_id)
~~~

Đây là tuple khái niệm; triển khai có thể khác. Không dùng `user_id` hiển thị đơn lẻ như định danh toàn cầu trong hệ thống multi-issuer/multi-tenant.

### Khi account B đăng nhập ngay sau A logout

Một callback hoặc API response của A đến muộn **không được ghi vào state của B**. Sử dụng epoch/session identity và revalidate đối tượng trước khi cập nhật cache, trong khi backend/RS vẫn thực thi authorization thực sự.

## 25. Kiểm thử sau logout: kiểm chứng từng lớp

Khi kiểm thử, đừng chỉ xác minh “nút Logout chuyển sang màn hình login”. Phải kiểm tra:

1. **Browser:** credential references, storage keys, cookie, cache và tab khác.
2. **BFF/session store:** session ID cũ bị invalid, OAuth token record không còn sử dụng.
3. **AS:** refresh token/grant không còn dùng được theo hợp đồng, nếu đã yêu cầu revoke.
4. **RS:** token cũ còn/không còn được chấp nhận theo **SLA/TTL thực tế**; audience/scope/object checks không bị bỏ.
5. **Telemetry:** không log secrets, có trạng thái cleanup/revoke/errors không nhạy cảm.

### Ma trận kiểm thử end-to-end

| Trường hợp | Kết quả kỳ vọng | Rủi ro được kiểm tra |
|---|---|---|
| SPA xóa access token memory khi logout | UI/API interceptor không còn dùng token đó. | Local memory cleanup. |
| SPA xóa `localStorage` auth keys | Keys đã biết không còn; không xóa dữ liệu unrelated. | Persistent storage. |
| SPA xóa `sessionStorage` tab A | Tab A sạch; tab B được yêu cầu tự cleanup. | Per-tab isolation. |
| SPA có token trong IndexedDB nhưng chỉ `removeItem` localStorage | Test phát hiện token tồn dư. | Incomplete inventory. |
| Service worker cache chứa dữ liệu user A | Purge per-user/private caches và background jobs. | PWA stale data. |
| Logout tab A trong khi tab B còn memory token | Tab B nhận signal và dừng; server invalidate session khi phù hợp. | Multi-tab race. |
| BroadcastChannel bị script giả gửi LOGOUT | UI có thể logout, nhưng không cấp quyền/token; không tin message làm bằng chứng auth. | Channel trust. |
| BFF có `HttpOnly` cookie, JS dùng `document.cookie` để xóa | Test đánh dấu sai thiết kế; phải gọi backend logout. | HttpOnly semantics. |
| BFF trả Set-Cookie expire đúng name/path/domain | Browser không còn gửi cookie tương ứng. | Cookie scope. |
| BFF expire cookie nhưng không invalidate server session | Bản sao cookie cũ vẫn được chấp nhận: **FAIL**. | Server-side session security. |
| Server invalidate session nhưng trả cookie sai Path | Browser có thể còn gửi cookie cũ, nhưng backend phải từ chối. | Cookie deletion completeness. |
| Logout POST thiếu CSRF token hợp lệ | Backend từ chối theo CSRF policy. | Logout CSRF. |
| Logout GET làm thay đổi session | Kiểm thử đánh dấu anti-pattern, sửa dùng POST. | Safe method semantics. |
| BFF xoá OAuth token store nhưng không remote revoke R | Không được khẳng định AS revoke xong. | Local vs remote. |
| AS trả HTTP 200 khi revoke R | R không dùng refresh lại được nếu revoke có hiệu lực. | RFC 7009. |
| AS revoke timeout nhưng Client đã xóa local | UI không dùng token; trạng thái remote chưa chắc chắn được xử lý. | Network uncertainty. |
| AS chỉ hỗ trợ refresh-token revocation | Không tuyên bố đã revoke từng access token nếu unsupported. | Capability honesty. |
| Access JWT còn 8 phút, RS kiểm tra offline | Có thể được chấp nhận đến `exp`; test ghi nhận. | JWT revocation gap. |
| Access JWT nằm trong denylist đúng namespace | RS từ chối dù signature còn hợp lệ. | Revocation state. |
| Opaque token RS cache `active=true` | Đo khoảng delay sau AS revoke, đánh giá SLA. | Introspection cache. |
| Logout trong lúc refresh R1 → R2 | Không lưu R2 vào session đã logout; xử lý family policy. | Token resurrection race. |
| Logout khi API response đang chạy | Không render/cache response thuộc phiên cũ. | In-flight request race. |
| Logout khi pending OIDC callback cũ | Callback cũ không tự tạo session mới. | State/PKCE lifecycle. |
| Logout RP nhưng OP SSO session còn | Auto reauth có thể xảy ra nếu tự start login; UI phải phản ánh đúng phạm vi. | SSO semantics. |
| RP-Initiated Logout dùng redirect URI chưa đăng ký | OP từ chối hoặc không redirect tới URI đó. | Open redirect prevention. |
| Browser Back button sau logout | Không hiện dữ liệu nhạy cảm từ cache/DOM cũ theo policy. | Browser state cleanup. |
| PWA offline logout | Local tokens/data bị dọn, remote revoke được đánh dấu pending theo policy. | Offline privacy. |
| Native logout xóa token trong secure storage | Token không còn truy xuất qua API lưu trữ bình thường. | Mobile credential cleanup. |
| Native app uninstall/reinstall | Test xác định keychain/backup persistence và chính sách account linking. | Device lifecycle. |
| User A logout, B login | Không nhận token/cache/dữ liệu A trong phiên B. | Cross-account isolation. |
| Client gửi access token `aud=billing-api` tới Orders | Orders từ chối dù token chưa revoke. | Audience validation. |
| Token thiếu `orders:read` được dùng đọc đơn | Orders từ chối theo scope/authority policy. | Least privilege. |
| Token đúng scope nhưng order tenant khác | Orders từ chối theo object/tenant policy. | BOLA prevention. |
| Attacker có bản sao bearer token trước logout | Test chứng minh local deletion không đủ chặn attacker; cần remote/TTL/sender binding. | Token theft response. |
| DPoP token bị copy nhưng attacker thiếu key | RS từ chối khi sender proof bắt buộc. | Sender-constrained token. |
| Client secret bị lộ, user logout | Secret vẫn cần rotate/disable riêng; logout không giải quyết compromise. | Client credential lifecycle. |
| Logging HTTP client chứa Authorization header | Kiểm thử thất bại; sanitize/redact. | Secret exfiltration. |
| Multi-tenant authorized-client store dùng key chung | Test phát hiện revoke/xóa nhầm Client/tenant. | Isolation. |

**Kiểm chứng phải phù hợp mô hình token thực sự.** Không thể dùng test `RS từ chối JWT ngay` để kết luận lỗi nếu thiết kế đã công khai chỉ dùng JWT TTL ngắn và không có revocation state; nhưng không được hứa “chặn tức thời” khi kiểm thử chứng minh điều ngược lại.

## 26. Các ngộ nhận điển hình

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “`localStorage.removeItem` là đã revoke token.” | Nó chỉ xóa một bản local. | Remote revocation/state là cơ chế riêng. |
| “Có `HttpOnly` thì JS có thể xóa cookie khi logout.” | HttpOnly ngăn JS truy cập/ghi đè cookie. | Server expire cookie và invalidate session. |
| “Xóa cookie đủ để attacker không dùng session ID cũ.” | Attacker có thể giữ bản sao cookie. | Invalidate session ở backend. |
| “Logout BFF tự xóa mọi OAuth grant.” | Local session/token store và AS grant khác nhau. | Revoke/grant disconnect theo policy. |
| “AS trả 200 revoke nên RS chắc chắn không nhận JWT nữa.” | RS có thể verify JWT offline/cache trạng thái. | TTL/denylist/introspection/propagation. |
| “ID token là token để gọi API sau login.” | ID token dành cho RP. | RS dùng access token đúng audience. |
| “Xóa localStorage là đã xóa IndexedDB và service worker.” | Các kho độc lập. | Inventory và purge từng nơi. |
| “`sessionStorage` được xóa ở một tab là xóa ở tất cả tab.” | Session storage thường theo tab. | Cross-tab notification + per-tab cleanup. |
| “Reload luôn xóa hết token memory.” | Một số state vẫn được lưu hoặc tab khác chưa reload. | Xóa state, đồng bộ tab, backend invalidate. |
| “Đã dùng memory-only thì XSS không lấy token được.” | XSS có thể dùng token/request trong origin. | XSS defense + BFF/short TTL khi phù hợp. |
| “Có SSO nên RP logout không bao giờ có ý nghĩa.” | RP local session vẫn có thể kết thúc. | Trình bày rõ RP logout vs OP logout. |
| “OIDC logout đương nhiên revoke refresh token.” | Logout và RFC 7009 độc lập. | Chính sách tích hợp riêng. |
| “Bỏ qua CSRF vì logout không nguy hiểm.” | Forced logout và session confusion gây rủi ro. | POST + CSRF defense thích hợp. |
| “AbortController hủy refresh request tại AS.” | Request có thể đã tới AS và cấp R2. | Guard state epoch và token-family handling. |
| “Keychain luôn bị xóa khi uninstall.” | Hành vi phụ thuộc OS/item/backup. | Xác minh lưu trữ và vòng đời device. |
| “Bấm logout là xóa mọi dữ liệu user từng tải.” | File/export/screenshot/log đã nằm ngoài app. | Data lifecycle policy riêng. |
| “Xóa token giúp RS bỏ qua `aud`/scope.” | RS authorization vẫn bắt buộc. | Issuer/audience/type/scope/object checks. |

## 27. Tình huống tự luyện

**Tình huống A — LocalStorage đã trống.** User logout, code gọi `localStorage.clear()` thành công. Attacker có access token đã sao chép 2 phút trước. Token còn hạn 10 phút. Có thể gọi API không?

**Giải thích:** Có thể nếu bearer token còn hiệu lực và RS không có sender binding/revocation state. Local deletion không chạm bản sao của attacker; cần revocation/TTL/DPoP/mTLS tùy thiết kế.

**Tình huống B — Cookie HttpOnly.** Developer viết `document.cookie="__Host-shop_session=; Max-Age=0; Path=/; Secure"` và báo đã logout. Có đủ không?

**Giải thích:** Không. JS không được xóa/ghi đè cookie HttpOnly; server phải expire cookie và invalidate session ID. Nếu không invalidate, cookie ID bị sao chép vẫn có thể được sử dụng.

**Tình huống C — Một tab logout, tab khác vẫn mở.** Tab A xóa memory token và gửi thông điệp logout, nhưng tab B bị treo, chưa xử lý thông điệp. Làm sao chặn dùng session?

**Giải thích:** Cần server-side invalidation/revocation và tab B kiểm tra trạng thái khi hoạt động lại. BroadcastChannel chỉ đồng bộ UI, không là cơ chế bảo đảm bảo mật.

**Tình huống D — R2 “sống lại”.** User logout và revoke R1. Một refresh request đồng thời đã dùng R1, nhận R2 sau đó rồi lưu vào client store. Sai ở đâu?

**Giải thích:** Thiếu session epoch/atomicity và policy family revocation. Không được ghi token mới vào session đã logout; AS cần xử lý race refresh vs revoke theo grant.

**Tình huống E — BFF remote revoke lỗi.** Browser đã nhận thông báo logout nhưng AS timeout. Có nên giữ cookie/session active để retry?

**Giải thích:** Không nên cho phiên tiếp tục sử dụng token chỉ vì remote revoke chưa chắc chắn. Invalidate local session, ghi trạng thái chưa xác nhận và retry có kiểm soát theo threat model.

**Tình huống F — OIDC OP session còn.** User logout Shop, ấn Login lại và lập tức vào app không nhập mật khẩu. Tại sao?

**Giải thích:** Shop RP session đã kết thúc nhưng OP/SSO session còn. Nếu muốn logout SSO, cần dùng luồng OP logout phù hợp; không thể JS xóa cookie khác origin.

**Tình huống G — Quay lại bằng nút Back.** Sau logout, browser Back phục hồi trang Orders với dữ liệu cũ trong DOM. Access token đã mất. Đây có phải lỗi?

**Giải thích:** Có thể là **dữ liệu riêng tư còn lưu trong UI/bfcache**, không phải token chưa xóa. Cần data/cache cleanup, no-store và revalidation khi phục hồi, phù hợp browser policy.

**Tình huống H — Offline logout.** Mobile offline xóa refresh token trong keystore/storage ngay. Sau đó muốn revoke token ở AS nhưng không còn chuỗi. Cần thiết kế gì?

**Giải thích:** Có thể dùng server-managed grant/device unlink hoặc protected pending-revocation mechanism, không lưu token thô trong queue kém bảo mật. Quan trọng là dừng local access ngay và không tuyên bố remote revoke đã xong.

**Tình huống I — Tenant switch.** User A logout, B login, nhưng query cache `orders` chung vẫn hiển thị đơn A. Vì sao?

**Giải thích:** Token cleanup không tự purge application data. Cache key/cleanup phải gắn user/tenant và bỏ response cũ sau epoch thay đổi.

**Tình huống J — Logout Client Credentials.** Worker có client secret dùng chung, muốn “logout” service bằng cách revoke một access token. Nó có thể xin token mới không?

**Giải thích:** Có, nếu credential Client còn hợp lệ và AS vẫn cho grant. Muốn ngăn xin token mới cần disable/rotate credential hoặc thay policy. Không xóa credential toàn service chỉ vì một user logout.

**Tình huống K — Rút consent.** User disconnect OAuth Client ở AS, nhưng SPA chưa nhận thông báo và còn refresh token cũ. Sẽ thế nào?

**Giải thích:** Nếu grant/refresh token đã bị AS vô hiệu, refresh tiếp theo phải thất bại; SPA phải xử lý `invalid_grant` hoặc trạng thái tương ứng, xóa local token và chuyển về signed-out thay vì retry vô hạn.

**Tình huống L — Logout request là GET.** Attacker nhúng ảnh trỏ `https://shop.example.test/logout`, khiến user logout ngoài ý muốn. Cần sửa?

**Giải thích:** Không dùng GET cho hành động thay đổi session. Chuyển sang POST cùng CSRF defense/Origin checks theo framework, bảo vệ cookie và redirect.

**Tình huống M — Xóa key DPoP.** Client xóa private key DPoP ngay khi logout nhưng vẫn giữ refresh token DPoP-bound trong token store. Có thể làm gì?

**Giải thích:** Refresh token bị ràng buộc có thể không còn dùng được khi thiếu key nhưng vẫn là credential cần quản lý. Xóa token, revoke grant/family theo policy, xem key có được dùng cho phiên khác không trước khi phá hủy.

**Tình huống N — Account bị đánh cắp token.** User báo access token đã bị lộ. UI logout và xóa local storage thành công. Điều tra còn cần gì?

**Giải thích:** Revoke refresh/grant/token, kiểm tra RS replay window, audit cấp token/API access, bảo vệ client secret/key nếu có, sửa nguồn lộ và đánh giá dữ liệu đã bị truy cập. Xóa local chỉ là một phần.

## Checklist triển khai xóa token phía client

1. **Lập inventory token:** access, refresh, ID, code/verifier, cookie/session, DPoP key; phân biệt loại token và audience.
2. **Xác định architecture:** SPA direct token, BFF HttpOnly cookie, native secure storage hay service backend; mỗi nơi có trách nhiệm khác nhau.
3. **Định nghĩa logout scope:** chỉ local RP session, toàn SSO, một thiết bị, toàn grant hay Client connection; không gộp tên các thao tác.
4. **Đặt state logged-out sớm:** chặn request/refresh mới, dùng auth epoch, cancel timers và bỏ kết quả từ request cũ.
5. **Dọn browser credential:** memory, known `localStorage`/`sessionStorage` keys, IndexedDB/Cache API/service worker theo kiểm kê, không xóa bừa unrelated storage.
6. **Đồng bộ nhiều tab:** BroadcastChannel/storage event chỉ là tín hiệu; tab phải tự purge và revalidate với backend khi thức dậy.
7. **Với BFF:** invalidate session server-side, xóa OAuth authorized-client/token records, expire HttpOnly cookie đúng name/path/domain.
8. **Dùng HTTPS/CSRF:** logout mutation bằng POST và CSRF policy phù hợp, không dùng GET hoặc redirect URL không kiểm soát.
9. **Revoke remote khi cần:** RFC 7009 qua trusted endpoint, client authentication/association đúng, xử lý timeout và token family.
10. **Đánh giá JWT/opaque revocation:** RS cache/introspection/denylist/TTL, không khẳng định chặn tức thời nếu JWT offline còn hạn.
11. **Xử lý refresh rotation race:** atomically stop session, không lưu token mới vào session cũ, revoke family theo policy.
12. **Ngăn silent relogin:** hủy pending state/PKCE, disable auto renew và quyết định RP logout hay OP logout đúng nhu cầu.
13. **Mobile/offline:** secure storage, backup/reinstall, queued jobs, protected pending revocation và device unlink.
14. **Dọn dữ liệu riêng tư:** API caches, offline content, bfcache/Back, tab khác, downloads theo quyền có thể quản lý.
15. **Chống token theft:** XSS/CSRF defense, log redaction, secure transport, refresh rotation, sender-binding nếu cần.
16. **Kiểm tra RS authorization:** trusted issuer, signature/introspection, audience, token type, exp/nbf, scope, tenant và owner/object checks.
17. **Telemetry trung thực:** audit local cleanup, remote revoke, AS/RS propagation, lỗi và retry không ghi raw credentials.
18. **Test failure/race:** many tabs, multiple accounts, offline logout, AS timeout, concurrent refresh, delayed callback, cookie Path mismatch, token replay.

## Ghi nhớ

**Xóa token phía client là một phần bắt buộc của logout, nhưng không phải toàn bộ logout.** SPA phải dọn **memory, browser storage, cache/service worker và các tab**; BFF phải **invalidate server session, xóa token store và hết hạn cookie HttpOnly từ server**; native app phải xóa credential khỏi secure storage và kiểm soát offline cache. Trong mọi kiến trúc, cần **chặn refresh/token usage mới, xử lý race với request/callback và không silent relogin ngoài ý muốn**. **RFC 7009 revocation**, **OIDC RP/OP logout**, **token expiration** và **RS denylist/introspection** là các cơ chế khác nhau, phải phối hợp theo SLA và threat model. **Xóa bản sao local không vô hiệu bearer token đã bị sao chép**; RS vẫn cần issuer, audience, scope, trạng thái thu hồi khi được yêu cầu và **object/tenant authorization**. Chỉ tuyên bố mức độ logout/thu hồi đã thực sự xác minh.

### Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MDN — Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API)
- [MDN — Broadcast Channel API](https://developer.mozilla.org/en-US/docs/Web/API/Broadcast_Channel_API)
- [MDN — Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Clear-Site-Data)
- [Spring Security Reference — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
