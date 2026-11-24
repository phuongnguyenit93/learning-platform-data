# Lưu access token trong memory

Khi một ứng dụng nhận **access token** từ authorization server, nó cần giữ token ở đâu đó đủ lâu để gọi API. Với ứng dụng web chạy trong trình duyệt, một lựa chọn là giữ token **chỉ trong bộ nhớ của JavaScript đang chạy** (*in-memory access token storage*), thay vì ghi vào `localStorage`, `sessionStorage`, `IndexedDB` hoặc cookie có thể tồn tại qua lần tải trang. Đây là một cách **giảm thời gian và phạm vi tồn tại của bearer credential**, nhưng không biến token thành bất khả xâm phạm: mã JavaScript độc hại chạy trong cùng ngữ cảnh vẫn có thể lợi dụng phiên đang hoạt động.

Trong chương **Token storage** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này đặt in-memory storage vào vòng đời OAuth 2.0/OpenID Connect (OIDC): phát hành access token, lưu tạm, gửi cho đúng API, xử lý hết hạn/làm mới, đăng xuất, thu hồi và phòng chống token bị đánh cắp hoặc phát lại. Ta cũng phân biệt **memory của SPA**, **memory của server Java** và kiến trúc **Backend for Frontend (BFF)**, vì ba mô hình có các ranh giới tin cậy rất khác nhau.

> **Ý chính:** Giữ access token trong memory giúp tránh lưu token bền vững trong trình duyệt, nhưng **không phải cơ chế chống XSS, không thay kiểm tra token ở API và không tự chống replay**.

## 1. “Memory” là bộ nhớ nào?

Không phải mọi hệ thống nói “lưu token trong memory” đều có cùng ý nghĩa:

| Môi trường | Memory đang nói đến | Ai có thể truy cập? | Độ bền của token |
| --- | --- | --- | --- |
| **SPA trong trình duyệt** | Biến/closure/module trong JavaScript của trang | JavaScript có khả năng chạy trong cùng ngữ cảnh; DevTools; rủi ro extension/malware | Thường mất khi reload, đóng tab hoặc document bị hủy |
| **Dedicated Web Worker** | Biến thuộc Worker riêng | Worker trực tiếp; trang có thể gửi message yêu cầu Worker thực hiện hành động | Theo vòng đời Worker, không bền vững |
| **Service Worker** | Biến của Service Worker process | Service Worker và các luồng message/fetch được hỗ trợ | Có thể bị trình duyệt dừng bất kỳ lúc nào; không phải kho lưu tin cậy |
| **Java backend/BFF** | Heap JVM, cache theo session/request | Mã server có quyền truy cập, heap dump, công cụ vận hành nếu không bảo vệ | Mất khi process khởi động lại, trừ khi có cơ chế phục hồi riêng |
| **Redis/In-memory database** | Bộ nhớ của một dịch vụ lưu trữ riêng | Các client có credential mạng, người quản trị, cơ chế snapshot/replication | Có thể được ghi ra đĩa hoặc nhân bản; **không** đồng nghĩa “chỉ sống trong RAM” |

Trong bài này, khi nói **SPA lưu access token trong memory**, ta chủ yếu chỉ **biến nội bộ không được ghi xuống storage bền vững**. Với web, cần hiểu chính xác rằng:

- Reload/navigate tạo document mới thường làm mất biến JavaScript của document cũ.
- **Back-forward cache (bfcache)** có thể giữ lại trạng thái document khi người dùng quay lại trang; không nên coi bấm Back là bảo đảm token đã bị xóa.
- Trình duyệt có thể suspend trang hoặc chấm dứt Worker; ứng dụng phải khôi phục trạng thái an toàn, không giả định token luôn có mặt.
- Xóa tham chiếu trong JavaScript **không bảo đảm byte token đã bị ghi đè trong RAM** vì chuỗi bất biến, garbage collector, snapshot và bản sao tạm thời.

### 1.1. Access token là credential, không phải dữ liệu hồ sơ

Access token dành cho **resource server/API** và thường được gửi dưới dạng:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Nó có thể là **JWT** hoặc **opaque token**. JWT đã ký có thể đọc được các claims như `sub`, `scope`, `aud`, `exp` nhưng không có nghĩa chúng được mã hóa bí mật. Opaque token thường không mang cấu trúc mà client cần diễn giải. Cả hai đều có thể là **Bearer credential**: bản sao token có thể được dùng lại nếu API không có sender constraint hoặc thu hồi phù hợp.

**ID token** trong OIDC dùng để client xác minh sự kiện đăng nhập, không thay access token tại API. **Refresh token** dùng ở token endpoint để xin access token mới, không được gửi tới API. Một lựa chọn lưu access token trong memory **không tự quyết định** nơi lưu refresh token hoặc cookie phiên.

## 2. So sánh với các vị trí lưu token khác

| Cách lưu | Tồn tại sau reload? | JavaScript của trang có đọc trực tiếp? | Nguy cơ đáng chú ý |
| --- | --- | --- | --- |
| **Biến/closure trong SPA** | Thường **không** | Có thể bị mã độc cùng ngữ cảnh lợi dụng; không nhất thiết có biến global dễ đọc | XSS có thể gửi request hoặc tìm đường lấy token; mất trạng thái khi reload |
| **`sessionStorage`** | Có qua reload trong cùng tab theo mô hình browser | **Có**, với script cùng origin và quyền tương ứng | XSS đọc được; dữ liệu có thể được giữ trong vòng đời tab |
| **`localStorage`** | **Có** qua reload và lần mở sau | **Có**, với script cùng origin | Credential bị lộ lâu dài nếu XSS/trình duyệt bị xâm nhập |
| **`IndexedDB`** | **Có**, cho đến khi bị xóa | **Có**, trong origin có quyền | Bền vững, dữ liệu có thể bị truy xuất qua script bị chiếm |
| **Cookie không `HttpOnly` chứa token** | Tùy `Expires`/`Max-Age` | **Có** | XSS đọc token, cookie tự động gửi trong phạm vi phù hợp |
| **Cookie `HttpOnly` chứa session ID** | Tùy tuổi cookie | **Không đọc trực tiếp** bằng `document.cookie` | XSS vẫn có thể thực hiện request trong phiên; cần CSRF/session protection |
| **Backend/BFF giữ access token** | Tùy session/token store phía server | JavaScript browser **không nhận token** | Phải bảo vệ backend, cookie, session, token store và CSRF |

**Không có một cột “an toàn tuyệt đối”.** In-memory storage giảm rủi ro khi cần tránh để token tồn tại sau khi tab bị đóng, hoặc bị một script chạy **sau lần reload** đọc lại từ storage bền vững. Nhưng nếu attacker đã có khả năng thực thi JavaScript trong phiên đang hoạt động, việc token nằm trong memory **không đủ để ngăn lạm dụng phiên**.

Đặc biệt, **`sessionStorage` không đồng nghĩa “in-memory access token”** theo nghĩa volatile JS variable. Browser có thể duy trì session storage qua reload và một số hoạt động khôi phục tab, nên nó có hồ sơ rủi ro khác.

## 3. Mô hình đe dọa: memory bảo vệ được gì, không bảo vệ được gì?

### 3.1. Điều memory giúp giảm

1. **Giảm tồn tại của credential:** token không được cố ý ghi vào Web Storage hoặc cơ sở dữ liệu client để chờ lần mở trang tiếp theo.
2. **Giảm khả năng đọc token cũ sau reload:** nếu token chỉ là biến trong document đã hủy, một script chạy về sau không thể đơn giản gọi `localStorage.getItem("access_token")` để lấy lại bản sao bền vững.
3. **Tách luồng UI khỏi dữ liệu nhạy cảm:** lưu token trong closure/module riêng thay vì trộn vào state/log giúp giảm các đường lộ ngoài ý muốn.
4. **Hỗ trợ vòng đời ngắn:** khi document chết hoặc ứng dụng chủ động xóa tham chiếu, token không còn được ứng dụng chủ động sử dụng.

### 3.2. Điều memory không giải quyết

- **Cross-Site Scripting (XSS):** script độc hại trong origin có thể gọi các API được phép, gắn hook vào `fetch`, đọc dữ liệu phản hồi hoặc khai thác các interface ứng dụng để thực hiện hành động. Closure không tạo ranh giới bảo mật chống XSS có cùng quyền thực thi.
- **Malicious third-party script:** analytics/widget/script bên thứ ba chạy trong document có thể được trao quá nhiều quyền nếu tích hợp không kiểm soát.
- **Phần mở rộng trình duyệt/malware:** tùy quyền và môi trường, chúng có thể quan sát hoặc can thiệp ứng dụng; lưu in-memory không bảo đảm bảo mật trước thiết bị bị chiếm.
- **Token replay:** nếu bản sao bearer token bị lộ qua request/log hoặc nguồn khác, API có thể chấp nhận lại cho đến khi hết hạn hoặc bị thu hồi.
- **Phân quyền sai:** token đúng chữ ký và scope không cấp quyền đọc tài nguyên của user/tenant khác.
- **Data exfiltration khi phiên đang mở:** ngay cả khi attacker không lấy trực tiếp bytes của token, họ có thể khiến ứng dụng gửi request hợp lệ và đọc dữ liệu.

~~~mermaid
flowchart LR
    OP["Authorization server"] -->|"Access token"| SPA["SPA: biến riêng trong memory"]
    SPA -->|"Bearer token"| API["Resource server / API"]
    XSS["XSS trong document"] -.->|"Gọi hàm/app API,\ncan thiệp fetch hoặc đọc response"| SPA
    SPA -->|"Không ghi token"| DB["localStorage / IndexedDB"]
    API -->|"Chữ ký/introspection,\niss, aud, exp, scope, ownership"| CHECK["API authorization"]
~~~

Đường nét đứt biểu diễn rủi ro XSS; mũi tên tới Web Storage trong sơ đồ diễn tả **quy tắc không ghi**, không phải một request thật. Dùng **Content Security Policy (CSP)**, **Trusted Types** khi phù hợp, tránh DOM XSS, kiểm soát dependencies và xử lý dữ liệu đầu vào là các biện pháp cần thiết **song song** với chiến lược lưu token.

## 4. Access token được đưa vào memory từ đâu?

Với **SPA public client**, luồng hiện đại phổ biến là **OAuth 2.0 Authorization Code + PKCE**; nếu cần thông tin đăng nhập người dùng thì dùng **OIDC** với `scope=openid`. Không nên chọn implicit flow chỉ để nhận access token trong URL rồi lưu vào memory.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser / SPA
    participant AS as Authorization server / OP
    participant API as Resource server
    U->>B: Đăng nhập
    B->>B: Tạo state, PKCE verifier/challenge
    B->>AS: Authorization request (code + PKCE)
    AS->>U: Xác thực, consent/chính sách
    U-->>AS: Hoàn thành
    AS-->>B: Redirect về callback với code + state
    B->>B: Kiểm tra state, lấy code_verifier tương ứng
    B->>AS: Đổi code với code_verifier
    AS-->>B: Access token (và ID token nếu OIDC)
    B->>B: Giữ access token trong memory
    B->>API: Bearer access token cho đúng API
    API->>API: Validate token + quyền
    API-->>B: Dữ liệu hoặc 401/403
~~~

### 4.1. Chú ý PKCE và lần redirect làm mất memory

Khi browser điều hướng sang OP rồi quay về callback, **document SPA cũ thường đã bị hủy**. Điều đó dẫn tới một câu hỏi thực tế: `code_verifier` và `state` cần được đối chiếu qua redirect thì giữ ở đâu?

Một số thư viện OIDC cho SPA dùng **`sessionStorage` cho trạng thái authorization request ngắn hạn**, gồm `state`/PKCE transaction data. Điều này **khác với lưu access token bền vững**. Dữ liệu PKCE cũng nhạy cảm trong thời gian chờ callback và phải được bảo vệ, ràng buộc với đúng flow, có TTL và xóa sau sử dụng. Lựa chọn khác là dùng **backend/BFF** giữ giao dịch PKCE trên server.

Không cần tuyên bố “mọi byte liên quan OAuth đều ở RAM” mới được gọi là **access token in-memory**: vấn đề chính là **bản thân access token** không được ghi vào storage bền vững. Tuy vậy, các bí mật khác (như refresh token và PKCE verifier) vẫn cần đánh giá riêng.

### 4.2. Những kiểm tra không được bỏ qua

- `redirect_uri` phải phù hợp với đăng ký client; không nhận callback từ địa chỉ tùy ý.
- `state` liên kết authorization response với yêu cầu đã khởi tạo, giúp giảm login CSRF và nhầm phiên.
- `code_verifier` phải tương ứng `code_challenge` của PKCE; dùng `S256` theo chính sách hiện đại.
- Nếu dùng OIDC `nonce`, client phải đối chiếu `nonce` nhận được trong **ID token** sau khi kiểm tra ID token.
- Access token phải dành cho **đúng API** theo audience/resource, không lấy ID token thay làm Bearer credential.
- Client không được tin các claims JWT tự giải mã để cấp quyền nội bộ nếu chưa có cơ chế xác minh thích hợp; **resource server luôn tự xác minh access token**.

## 5. Mẫu JavaScript: giữ token trong closure riêng

Không đặt token vào `window.accessToken`, React Redux store có persistence, URL hoặc Web Storage. Với SPA nhỏ, có thể tạo một **module client** quản lý token trong closure, chỉ cung cấp các thao tác API cụ thể và phương thức xóa credential.

Ví dụ JavaScript thuần (giản lược để học, token là dữ liệu trả về từ một luồng OAuth hợp lệ):

~~~javascript
export function createOrdersApiClient() {
  let accessToken = null;
  let expiresAtMillis = 0;

  // Chỉ gọi từ callback/token handler đã thực thi giao thức OAuth.
  function acceptTokenResponse(tokenResponse) {
    if (
      tokenResponse?.token_type?.toLowerCase() !== "bearer" ||
      typeof tokenResponse.access_token !== "string" ||
      !tokenResponse.access_token ||
      !Number.isFinite(tokenResponse.expires_in) ||
      tokenResponse.expires_in <= 0
    ) {
      throw new Error("Invalid access token response");
    }

    accessToken = tokenResponse.access_token;
    // Dự phòng 30 giây để tránh dùng token sát giờ hết hạn.
    expiresAtMillis =
      Date.now() + Math.max(0, tokenResponse.expires_in - 30) * 1000;
  }

  function clear() {
    accessToken = null;
    expiresAtMillis = 0;
  }

  async function listOrders({ signal } = {}) {
    if (!accessToken || Date.now() >= expiresAtMillis) {
      throw new Error("Access token absent or expiring");
    }

    const response = await fetch("https://api.example.com/orders", {
      method: "GET",
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      },
      // Cấu hình CORS tại API theo origin được phép.
      credentials: "omit",
      cache: "no-store",
      signal
    });

    if (response.status === 401) {
      clear();
      throw new Error("Access token rejected; reauthorization required");
    }
    if (response.status === 403) {
      throw new Error("Insufficient permission");
    }
    if (!response.ok) {
      throw new Error("API request failed");
    }
    return response.json();
  }

  return Object.freeze({
    acceptTokenResponse,
    listOrders,
    clear
  });
}
~~~

**Điểm có chủ đích trong ví dụ:**

1. `accessToken` là biến closure, không được xuất ra qua `getToken()` hoặc lưu trong `localStorage`.
2. URL API là **hằng số tin cậy**, không nhận URL tùy ý từ input để tránh gửi `Authorization` sang host do attacker kiểm soát.
3. Client không tự giải mã JWT rồi tin `exp`/scope; thời lượng dùng cục bộ chỉ hỗ trợ **UX/refresh scheduling**, quyết định cuối cùng thuộc API.
4. `credentials: "omit"` là lựa chọn cho **API dùng Bearer header mà không cần cookie**. Với BFF dùng session cookie, **không sao chép cấu hình này**; browser cần chính sách cookie/CSRF khác.
5. `Object.freeze` chỉ làm đối tượng API khó bị thay đổi vô ý, **không phải ranh giới bảo mật chống script độc hại trong origin**.
6. Không tự retry request ghi dữ liệu khi gặp 401: có thể gây thao tác lặp nếu server đã thực thi một phần; cần idempotency và retry policy riêng.

### 5.1. Không đưa token vào state có thể bị serialize

Trong React/Vue/Angular, có thể đặt **metadata không nhạy cảm** như `isAuthenticated`, thời gian dự kiến hết hạn hoặc trạng thái user ở UI state. Access token nên được giữ trong module/vault chuyên dụng, tránh:

- Redux Persist, Zustand persist, Pinia persisted state, lưu nguyên state vào `localStorage` hoặc devtools history.
- Gắn token vào DOM, `data-*` attribute, hidden input, HTML template hoặc URL query/hash.
- `console.log(tokenResponse)`, log middleware toàn bộ response, exception có token hoặc Sentry breadcrumb không lọc.
- Query cache lưu cả `Authorization` header hoặc dữ liệu credential.
- Đưa token vào React component props rồi truyền qua nhiều tầng không cần thiết.

Lưu token trong `useRef` hoặc React context **cũng là memory**, nhưng dễ bị lộ thông qua debug props, devtools, serialization hoặc mã ứng dụng. Tùy kiến trúc, closure/service riêng có thể giảm số nơi cần chạm token hơn việc đưa token vào state UI toàn cục.

### 5.2. Memory vault không phải “kho khóa an toàn”

Một script XSS vẫn có thể gọi `listOrders()`, đọc response và exfiltrate dữ liệu, dù nó không được cung cấp trực tiếp getter trả access token. Nếu script kiểm soát `fetch` trước khi module chạy hoặc can thiệp môi trường, việc giấu biến closure không bảo đảm ngăn lộ token. Do đó, **không quảng bá “không lấy được token qua XSS”** như thuộc tính tuyệt đối của cách cài đặt này.

## 6. Lifecycle: tải trang, reload, tab mới và quay lại trang

| Sự kiện | Access token trong JS memory | Ứng dụng cần làm gì? |
| --- | --- | --- |
| Route change trong SPA, không reload document | Thường còn | Dùng token theo đúng hạn và audience |
| Reload (`F5`) | Thường mất | Chuyển sang trạng thái chưa có token; có quy trình khởi tạo lại phiên |
| Mở tab mới | Memory độc lập | Không kỳ vọng tab mới tự có token của tab cũ |
| Đóng tab/document thực sự bị hủy | Biến không còn sống trong document | Không dựa vào việc này như giải pháp thu hồi phía server |
| Điều hướng Back/Forward có bfcache | Có thể giữ document và memory | Kiểm tra lại hạn, trạng thái bảo mật và quyền khi trang được khôi phục |
| Browser suspend/kill Worker | Token trong Worker có thể biến mất | Khởi tạo lại qua flow được phép; không dựa vào Worker như store bền |
| Logout | Ứng dụng có thể clear tham chiếu | Đồng thời xử lý session, refresh token/grant và token thu hồi theo thiết kế |

### 6.1. Khởi tạo lại sau reload

In-memory storage làm người dùng có vẻ “mất đăng nhập” sau reload nếu ứng dụng không có một **cơ chế phiên độc lập**. Có ba cách xử lý thường gặp:

1. **Đăng nhập/ủy quyền lại qua Authorization Code + PKCE**, có thể được OP hỗ trợ bằng SSO session và không bắt nhập mật khẩu nếu chính sách cho phép.
2. **BFF/session cookie:** trình duyệt chỉ giữ session ID, backend giữ credential API; reload không khiến user mất session khi cookie còn hợp lệ.
3. **Refresh token phía client** trong một thiết kế cho phép và bảo vệ tương ứng; nếu refresh token cũng chỉ giữ trong memory, nó cũng thường mất khi reload. Nếu quyết định lưu refresh token bền hơn, cần đánh giá rủi ro cao hơn và các yêu cầu rotation/sender constraint.

Không dùng **implicit flow**, token trong URL hoặc `localStorage` như lối tắt mặc định chỉ vì reload gây phiền. Cũng không dựa vào silent iframe authentication như một biện pháp phục hồi chắc chắn: cookie bên thứ ba có thể bị trình duyệt chặn và OP có thể yêu cầu user interaction.

### 6.2. Nhiều tab và BroadcastChannel

Hai tab có thể có hai phiên bộ nhớ, hai access token và lịch refresh riêng. Nếu cần đồng bộ **trạng thái** logout hoặc “token cần cập nhật”, có thể dùng `BroadcastChannel` hay một kênh trao đổi nội bộ phù hợp, nhưng **không gửi raw access/refresh token qua broadcast** trừ khi đã đánh giá threat model kỹ.

~~~javascript
// Chỉ đồng bộ tín hiệu; KHÔNG gửi access token.
const channel = new BroadcastChannel("auth-state");

function announceLogout() {
  channel.postMessage({ type: "LOGOUT" });
}

channel.onmessage = ({ data }) => {
  if (data?.type === "LOGOUT") {
    ordersClient.clear(); // ordersClient là instance vault của tab này
  }
};
~~~

Mẫu trên chỉ hỗ trợ UI/client phối hợp; **không thay thu hồi token/session ở backend**. Đối với các kênh `postMessage` giữa window/iframe, phải kiểm tra `origin`, `source` và cấu trúc message; không dùng `targetOrigin="*"` để truyền credential nhạy cảm.

## 7. Refresh token: bảo vệ mạnh hơn access token

Access token thường có hạn tương đối ngắn và chỉ dùng ở resource API; refresh token có thể xin **nhiều access token mới** trong suốt grant. Vì vậy, **lưu access token trong memory không có nghĩa mọi token đều có mức rủi ro giống nhau**.

| Cách khôi phục access token | Ưu điểm | Điều phải đánh giá |
| --- | --- | --- |
| **Authorization Code + PKCE lại khi cần** | Không cần giữ refresh token lâu ở SPA | Hành trình redirect, state/PKCE, SSO session và chính sách OP |
| **Refresh token cũng giữ trong JS memory** | Không cố ý ghi refresh token xuống Web Storage | Mất qua reload, XSS vẫn có thể dùng/trộm; cần rotation hoặc ràng buộc bên gửi theo profile |
| **Refresh token bền ở client** | Có thể duy trì phiên qua reload | Tăng cửa sổ credential bị lộ, cần biện pháp phù hợp môi trường và chuẩn bảo mật |
| **BFF giữ refresh token phía server** | Browser không nhận OAuth access/refresh token | Cần session bảo mật, CSRF, token store, phân quyền và vận hành BFF |

Theo OAuth 2.0 Security Best Current Practice, refresh token cho **public client** phải được bảo vệ chống replay bằng phương án phù hợp như **refresh token rotation** hoặc **sender-constrained refresh token**. Việc dùng refresh token phải tuân chính sách AS, grant, thời hạn, quyền và khả năng thu hồi. **PKCE không tự thay thế bảo vệ refresh token** sau khi token đã được cấp.

### 7.1. Single-flight refresh để tránh reuse do đua luồng

Nếu refresh token được rotation, hai API requests đồng thời phát hiện access token hết hạn có thể cùng gửi refresh token hiện hành. Request thứ nhất thành công và làm token cũ thành `USED`; request thứ hai có thể bị phát hiện là **reuse**, dẫn tới thu hồi token family theo policy.

Giải pháp client là **chỉ một refresh request cho mỗi grant đang thực hiện**, còn request khác dùng chung kết quả. Pseudocode:

~~~javascript
let refreshInFlight = null;

async function refreshOnce() {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    // refreshWithApprovedGrant() thuộc OAuth client library/BFF:
    // nó phải dùng flow, client auth/binding và token store đúng policy.
    return refreshWithApprovedGrant();
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}
~~~

Đây **chỉ là mẫu đồng bộ promise**, không phải cài đặt OAuth refresh hoàn chỉnh. Với nhiều tab, nhiều worker hoặc nhiều backend instances, cần cơ chế điều phối tương ứng; mutex trong **một** JS module không tự đồng bộ mọi tab/process. Khi refresh request timeout hoặc response bị mất, **không retry vô hạn bằng refresh token cũ**.

### 7.2. Khi API trả 401 và 403

- **401 / `invalid_token`**: token có thể hết hạn, sai hoặc bị từ chối. Client có thể cố gắng lấy credential mới **theo policy có giới hạn**, nhưng không tự kết luận rằng refresh luôn khắc phục được.
- **403 / `insufficient_scope`**: token đã được chấp nhận trong ngữ cảnh thông thường nhưng thiếu quyền; **refresh access token không tự thêm scope**.
- **401 / `insufficient_user_authentication`** theo step-up challenge thích hợp: cần user authentication mạnh/mới hơn; refresh token không tự thực hiện MFA hoặc làm mới `auth_time`.

Request POST/DELETE có side effect cần được xử lý **có idempotency/transaction safeguards** khi retry. Không tự replay mọi request chỉ vì vừa nhận token mới.

## 8. Web Worker: giảm lộ token qua API của trang, không xóa rủi ro XSS

Một **Dedicated Worker** có execution context riêng và không truy cập trực tiếp DOM. Có thể cho Worker giữ access token trong private variable, nhận message mô tả **hành động API được phép**, tự gắn token và trả kết quả đã lọc về trang:

~~~mermaid
flowchart LR
    UI["SPA UI / main thread"] -->|"Message: loadOrders"| W["Dedicated Worker\naccess token trong memory"]
    W -->|"Bearer + request tới API cố định"| API["Resource server"]
    API -->|"Kết quả"| W
    W -->|"Dữ liệu đã lọc"| UI
    X["Script XSS ở main thread"] -.->|"Có thể gửi message\nnhư ứng dụng"| W
~~~

Điểm cần thiết kế:

1. Worker không nên có API kiểu `GET_TOKEN` trả raw token cho main thread.
2. Hạn chế **tập lệnh được phép** và endpoint đích; không chấp nhận một URL bất kỳ từ message để gửi Authorization header.
3. Validate cấu trúc message, origin/source khi liên quan và response data; tránh vô tình biến Worker thành **authenticated open proxy**.
4. Xem xét lifecycle Worker bị terminate; không có cam kết giữ token qua reload.
5. Hiểu rằng XSS trên main thread **vẫn có thể yêu cầu Worker thực hiện những hành động mà Worker cho phép**. Worker giảm quyền truy cập trực tiếp tới bytes token ở một số trường hợp, nhưng không thay authorization tại API.

**Service Worker** có thể chặn request/đóng vai trò proxy nhưng browser được phép dừng nó bất kỳ lúc nào; không dựa vào global variables của Service Worker làm nơi lưu token bền vững. IndexedDB mà Service Worker dùng lại có đặc tính **persistent storage**, không còn là access token “chỉ trong memory”.

## 9. BFF: phương án không đưa OAuth access token xuống browser

Với ứng dụng Java/Spring, một kiến trúc thường đáng cân nhắc là **Backend for Frontend (BFF)**:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser / SPA
    participant F as Java BFF
    participant AS as Authorization server
    participant API as Resource API
    U->>B: Đăng nhập
    B->>F: Yêu cầu /login
    F->>AS: Authorization Code + PKCE theo cấu hình
    AS-->>F: Callback/code rồi token exchange
    F->>F: Giữ token server-side; tạo session
    F-->>B: Cookie session Secure, HttpOnly, SameSite
    B->>F: GET /orders kèm cookie phiên
    F->>F: Kiểm tra session + CSRF/authorization
    F->>API: Bearer access token từ token store server
    API->>API: Validate token + quyền resource
    API-->>F: Kết quả
    F-->>B: Dữ liệu cần thiết
~~~

Trong mô hình này, **browser không cần nhận access token hoặc refresh token**, nên tránh một lớp exfiltration qua Web Storage và nhiều đoạn JS. Backend vẫn cần bảo vệ token khỏi log/heap dump, session fixation, token store bị truy cập trái phép và API calls vượt quyền.

Cookie session ví dụ:

~~~http
HTTP/1.1 302 Found
Location: /dashboard
Set-Cookie: __Host-app-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

**Cookie `HttpOnly` không có nghĩa ứng dụng miễn nhiễm XSS**: một script độc hại có thể gửi request dùng cookie đang có, dù không đọc được giá trị cookie. Vì cookie được browser tự động gửi, phải có thiết kế **CSRF protection**, kiểm soát `Origin`/`Referer` khi phù hợp, `SameSite`, quyền trên từng endpoint và bảo vệ XSS. Dùng `SameSite=Strict` hay `Lax` cần xét đúng luồng login/redirect và nhu cầu sản phẩm.

### 9.1. Spring Security xử lý OAuth client như thế nào?

Trong ứng dụng Spring, có thể dùng **Spring Security OAuth2 Client** và cơ chế `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService` để lưu credentials của OAuth client theo phiên/chủ thể với triển khai phù hợp.

Không mặc định rằng framework luôn lưu token **chỉ trong memory của process**. Vị trí lưu có thể là session, một service/store riêng hoặc một implementation persistent được cấu hình. Với production nhiều node, cần thiết kế persistence, encryption/at-rest controls, cache và revocation phù hợp. **Không đặt access token của mọi user vào một biến `static String` dùng chung.**

### 9.2. Khi nào nên chọn BFF thay vì SPA giữ token?

BFF đáng cân nhắc khi:

- Ứng dụng xử lý dữ liệu tài chính, nhân sự, quản trị hoặc quyền ghi nguy hiểm.
- Cần duy trì đăng nhập qua reload mà không đặt OAuth refresh token trong JavaScript.
- Có hạ tầng Java backend sẵn và đủ khả năng bảo vệ session, cookie, CSRF và token store.
- Muốn gom logic refresh/revocation ở một điểm kiểm soát thay vì từng tab.

Đổi lại BFF có chi phí vận hành, độ trễ hop trung gian và yêu cầu capacity/availability. **Không có kiến trúc nào loại bỏ nhu cầu validation ở resource server**.

## 10. “Memory” phía Java backend: dùng đúng phạm vi phiên

Một backend có thể chủ ý cache access token trong **heap JVM**, ví dụ để BFF gọi API trong thời hạn ngắn. Nhưng memory cache phía server có các rủi ro riêng:

- Nếu cache key chỉ là `client_id` mà token thực tế đại diện **từng user/tenant**, có thể gửi nhầm token của người khác.
- Nếu token bị log trong exception, heap dump hoặc APM instrumentation, việc không ghi database **không ngăn lộ token**.
- Khi process restart, token mất; trong cụm nhiều nodes, node khác không thấy cache của node này.
- `ConcurrentHashMap` không tự cung cấp TTL eviction; nếu không dọn, token hết hạn vẫn chiếm bộ nhớ.
- Các chuỗi Java là immutable; xóa map entry **không bảo đảm xóa bytes khỏi heap tức thì**.

### 10.1. Ví dụ Java: cache tạm token theo server session

Ví dụ học tập Java 17, cố ý chỉ cung cấp `put/get/remove` theo **session key do server tạo**, không chấp nhận user tự gửi session key như bằng chứng xác thực:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class EphemeralAccessTokenStore {
    private final ConcurrentMap<String, Entry> bySession =
        new ConcurrentHashMap<>();
    private final Clock clock;

    public EphemeralAccessTokenStore(Clock clock) {
        this.clock = clock;
    }

    public void put(String trustedSessionKey, String token, Instant expiresAt) {
        if (trustedSessionKey == null || trustedSessionKey.isBlank()
                || token == null || token.isBlank()
                || !expiresAt.isAfter(clock.instant())) {
            throw new IllegalArgumentException("Invalid token cache entry");
        }
        bySession.put(trustedSessionKey, new Entry(token, expiresAt));
    }

    public Optional<String> get(String trustedSessionKey) {
        Entry entry = bySession.get(trustedSessionKey);
        if (entry == null) return Optional.empty();

        // Chừa 30 giây để tránh gửi credential sát giờ hết hạn.
        if (!clock.instant().isBefore(entry.expiresAt().minusSeconds(30))) {
            bySession.remove(trustedSessionKey, entry);
            return Optional.empty();
        }
        return Optional.of(entry.token());
    }

    public void remove(String trustedSessionKey) {
        bySession.remove(trustedSessionKey);
    }

    private record Entry(String token, Instant expiresAt) {}
}
~~~

**Giới hạn của ví dụ:**

1. `trustedSessionKey` phải được lấy từ **session đã xác thực và kiểm tra CSRF/authorization**, không lấy từ `X-Session-Key` do client tự khai.
2. Store chỉ phù hợp **minh họa hoặc một process với yêu cầu đặc biệt**. Production cần xử lý memory pressure, eviction, cluster routing, secret protection và xử lý shutdown.
3. Chỉ `expiresAt` cục bộ **không thay API token validation**; `exp`/scope/audience/revocation vẫn được API xử lý.
4. Hàm `get` trả chuỗi token cho **mã backend đáng tin**; không expose nó thành API trả token về browser.
5. Token có thể ràng buộc thêm với **issuer, audience, client registration, subject và tenant**. Trong hệ thống nhiều OAuth grants, một session có thể cần nhiều entries; không ghi đè token của API A bằng token của API B.
6. Cần đường xử lý **logout** và thu hồi grant, cùng dọn cache định kỳ: xóa entry trong memory không tự revoke token ở authorization server.

Trên Spring Security, thay vì tự viết một token store production đơn giản hóa, thường nên dựa vào các abstraction OAuth2 Authorized Client và session/token-store phù hợp. Ví dụ trên nhằm phân tích **vòng đời và bảo vệ token trong bộ nhớ JVM**, không phải khuyến nghị tự thay thế thư viện OAuth.

## 11. XSS, CSP và các đường rò token ngoài storage

Khi đánh giá in-memory storage, cần nhìn toàn bộ đường đi của token:

~~~text
Authorization server → token response → OAuth client code
→ memory vault → request header Authorization → gateway → resource server
                         ↘ logs / errors / monitoring?  (PHẢI LỌC)
~~~

### 11.1. Giảm nguy cơ XSS

1. Không chèn input chưa được sanitize/escape vào `innerHTML`, `eval`, `new Function` hoặc HTML template động.
2. Thiết lập **CSP** có chủ đích, ưu tiên nonce/hash cho script và hạn chế script không tin cậy; kiểm thử với thư viện thực tế.
3. Sử dụng **Trusted Types** ở môi trường hỗ trợ để hạn chế một số DOM XSS sinks; không xem đây là thay thế xử lý input/output.
4. Kiểm soát third-party scripts, npm dependencies và việc script tải từ CDN; áp dụng supply-chain controls phù hợp.
5. Tránh lưu token trong global object, DOM, URL hoặc serialized state để giảm đường đọc trực tiếp.

**CSP không ngăn mọi XSS**, và `HttpOnly` cũng không chặn script độc hại gửi request trong phiên. Defense-in-depth cần kết hợp từ frontend, BFF, AS đến API.

### 11.2. CORS không phải công cụ bảo vệ token lưu trong memory

CORS kiểm soát việc **trình duyệt cho phép script đọc response cross-origin** trong một số tình huống; nó không chứng minh ai sở hữu access token, không chống gửi request từ bên ngoài trình duyệt và không thay xác minh Bearer token. API cần cấu hình allowed origins đúng client nhưng **không cấp quyền chỉ dựa trên header `Origin`**.

Một request `fetch` có `Authorization` header qua origin khác thường kích hoạt CORS preflight; API phải xử lý `OPTIONS` phù hợp, tránh trả lỗi xác thực cho preflight không mang access token, đồng thời không nới CORS thành `*` khi dùng cookie credentials.

### 11.3. Log và HTTP caching

- Không ghi `Authorization`, raw token response, refresh token, PKCE verifier hoặc session cookie vào logs, tracing spans, crash reports và browser analytics.
- Giới hạn cache đối với dữ liệu nhạy cảm; dùng `Cache-Control: no-store` khi cần để tránh token response hoặc nội dung riêng tư bị cache ngoài ý muốn.
- Khi dùng proxy/gateway, xóa hoặc mask `Authorization` trước khi log request; kiểm tra cả access logs của ingress và APM.
- Tránh gửi token qua URL query, fragment hoặc referrer. Một bearer token bị lộ trong URL vẫn có giá trị dù client chính đã xóa biến memory.

## 12. Logout, thu hồi và xử lý token bị đánh cắp

**Xóa token khỏi memory là thao tác cục bộ, không phải lệnh thu hồi từ authorization server.** Một access token JWT còn hạn có thể vẫn được API chấp nhận sau khi user đã đóng tab hoặc logout nếu attacker đã lấy được bản sao.

Quy trình logout an toàn có thể gồm:

1. **Ngăn request mới**, hủy các thao tác đang chờ khi thích hợp; không tạo request mới với credential cũ.
2. **Xóa tham chiếu** access token/refresh token trong JS memory hoặc backend store và xóa UI/cache dữ liệu nhạy cảm.
3. **Vô hiệu hóa session phía server** nếu ứng dụng có BFF/server-side session; hết hạn cookie phù hợp.
4. **Thu hồi refresh token/grant** tại AS nếu cơ chế revocation được hỗ trợ và phù hợp chính sách.
5. Với yêu cầu vô hiệu hóa access token ngay, dùng **opaque introspection**, denylist/token version hoặc policy check tương ứng; JWT validation offline không tự biết mọi sự kiện logout.
6. Nếu phát hiện token leak, điều tra nguồn lộ (XSS, log, extension, server), đánh giá token đã phát và thông báo/reauthentication khi cần.

### 12.1. Khi token gần hết hạn

Không đợi đến đúng `exp` mới xử lý. Client có thể đặt **skew buffer nhỏ** trước hạn theo `expires_in`, nhưng không nên tạo vòng lặp refresh liên tục. Nếu API vẫn trả `401`, cần dừng và làm lại authorization flow theo policy thay vì vô hạn retry.

### 12.2. Khi token bị replay

Một bản sao access token Bearer bị đánh cắp có thể sử dụng từ một thiết bị khác. In-memory storage chỉ giảm một số đường lộ; nó **không ràng buộc token với sender**.

Các cách giảm tác động:

- Access token TTL ngắn, scope/audience tối thiểu, quyền trên từng resource.
- Theo dõi anomaly theo session/client/grant với telemetry không chứa credential.
- Thu hồi token/grant, introspection/denylist theo mức rủi ro.
- **DPoP (RFC 9449)** hoặc **mTLS-bound tokens (RFC 8705)** nếu client, AS và RS đều hỗ trợ đúng binding. DPoP cũng cần kiểm tra proof `jti`, `htm`, `htu`, `ath` và key binding; không đơn thuần là “để token trong memory”.

## 13. Khi nào nên chọn memory, khi nào nên chọn BFF?

| Tình huống | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| SPA nhỏ, token ngắn hạn, chấp nhận làm lại authorization khi reload | Access token trong JS memory + Authorization Code/PKCE | Tránh lưu bền vững credential trong browser |
| SPA có access token cần dùng trên mỗi route nhưng reload hiếm | Closure/service vault; tránh Redux Persist/Web Storage | Giảm đường lộ và serialization không cần thiết |
| Ứng dụng web giao dịch nhạy cảm, cần duy trì session qua reload | **BFF giữ OAuth token phía server**, browser có session cookie | Tránh phát OAuth token cho JavaScript và gom refresh ở backend |
| Frontend cần isolation mạnh hơn giữa UI và token bytes | Dedicated Worker có API hành động giới hạn | Giảm một số đường truy cập trực tiếp, nhưng không chặn mọi XSS abuse |
| Native mobile app | Token ngắn hạn trong process memory; refresh credential trong secure OS storage khi cần | Môi trường và cơ chế bảo vệ khác trình duyệt |
| Java service-to-service | Token cache theo client/resource/tenant trong backend memory hoặc managed store | Không trộn user tokens, quản lý TTL và key riêng |
| Cần revoke gần thời gian thực cho dữ liệu quan trọng | Token introspection/denylist hoặc kiểm tra quyền hiện hành | Chỗ lưu client không quyết định tốc độ revoke của API |

Không có câu trả lời duy nhất “memory luôn tốt hơn cookie”. **Cookie `HttpOnly` chứa session ID cho BFF** có thể giúp browser **không thấy OAuth token**, còn cookie chứa nguyên JWT làm bearer credential có thiết kế khác với các yêu cầu CSRF/lifetime riêng. Quyết định phải dựa trên **người giữ token, loại ứng dụng, khả năng vận hành backend và threat model**.

## 14. Các lỗi triển khai thường gặp

### 14.1. “Access token nằm trong memory nên đã chống được XSS”

**Sai.** XSS vẫn có thể điều khiển ứng dụng, gửi các API calls trong phiên, đọc response và đôi khi tiếp cận token qua instrumentation. **Đúng:** ưu tiên phòng ngừa XSS, giảm token exposure và kiểm tra quyền tại backend.

### 14.2. “`sessionStorage` cũng là memory, vậy không có gì khác”

**Sai.** `sessionStorage` là Web Storage và tồn tại qua reload của cùng tab; script cùng origin có thể đọc. Memory closure không được cố ý persist vào storage.

### 14.3. “Gắn token vào Redux rồi tắt persist là an toàn”

**Chưa đủ.** State có thể xuất hiện trong devtools, middleware log, snapshot/error reports hoặc bị nhiều component dùng. Nên giới hạn nơi xử lý credential và không serialize token.

### 14.4. “Đóng tab là revoke access token”

**Sai.** Token có thể còn hợp lệ ở AS/RS. Xóa local reference không làm bản sao bị đánh cắp mất quyền dùng.

### 14.5. “Refresh token lưu vào localStorage để khôi phục memory nhanh”

**Rủi ro lớn.** Refresh token có thể sống lâu và cấp access token mới. Nếu muốn duy trì phiên, cân nhắc BFF; nếu public client được phép nhận refresh token, cần rotation/sender constraint và đánh giá storage/threat model cẩn thận.

### 14.6. “BFF có `HttpOnly` nên khỏi cần CSRF”

**Sai.** Browser vẫn tự gửi cookie, kể cả khi JavaScript không đọc được giá trị. BFF phải có CSRF policy phù hợp, `SameSite`, Origin checks và authorization.

### 14.7. “Lưu access token trong `static` Java field cho tất cả user”

**Sai.** Một token có thể bị gửi nhầm dưới danh nghĩa user/tenant khác; đa node còn khó đồng bộ. Token store backend phải gắn đúng session, principal, client, resource, scope và có TTL.

### 14.8. “CORS chặn request xấu nên API khỏi kiểm tra scope/audience”

**Sai.** CORS không phải cơ chế authentication; non-browser clients không bị giới hạn tương tự. API luôn phải kiểm tra credential, issuer/audience, thời gian, quyền và tài nguyên.

### 14.9. “ID token có user info nên gửi tới API thay access token”

**Sai.** ID token dành cho OIDC client. Resource API yêu cầu **access token** đúng audience/profile; lưu ID token ở đâu cũng không làm nó trở thành access token.

## 15. Bộ kiểm thử cho in-memory token storage

| Trường hợp | Kỳ vọng |
| --- | --- |
| Nhận token response hợp lệ | Access token chỉ tồn tại trong vault/runtime theo thiết kế |
| Kiểm tra `localStorage`, `sessionStorage`, `IndexedDB` | Không có bản sao access token do ứng dụng ghi |
| Chuyển route trong cùng SPA document | Token còn nếu chưa hết hạn |
| Reload trang | Token JS memory cũ mất; có flow khởi tạo lại an toàn |
| Đóng/mở tab | Không khôi phục access token chỉ từ memory cũ |
| Khôi phục bằng bfcache | Kiểm tra lại thời hạn/trạng thái, không suy ra đã logout |
| Tab A logout và Tab B còn mở | Theo chính sách: thông báo/clear cục bộ; backend revoke session/grant khi cần |
| API trả 401 | Không retry vô hạn; xóa token bị từ chối và khởi động flow phù hợp |
| API trả 403 | Không tự refresh để “xin thêm quyền” mà bỏ qua authorization |
| Hai API requests đồng thời cần refresh | Có single-flight/coordination; không reuse refresh token cũ ngoài ý muốn |
| Refresh request timeout sau rotation | Không tự gửi lại vô hạn credential cũ |
| Bị chèn script XSS trong test có kiểm soát | Đánh giá API abuse/exfiltration; memory không được coi là đủ bảo vệ |
| Token xuất hiện trong logs/errors | Test thất bại; phải redact ở client, gateway và server |
| Token Bearer bị gửi tới domain lạ | Không thể xảy ra qua URL injection/redirect chưa được kiểm soát |
| Access token có sai `aud`/`iss`, hết `exp` | Resource server từ chối bất kể nơi lưu ở client |
| JWT có scope phù hợp nhưng tài nguyên khác tenant | API từ chối theo object authorization |
| Backend Java restart hoặc scale thêm instance | Session/token strategy hoạt động theo thiết kế; không dùng cache local như shared store |
| Logout với JWT vẫn còn hạn | Local token clear; nếu cần revoke ngay phải có cơ chế tại AS/RS |
| Worker bị terminate hoặc tab bị suspend | Ứng dụng xử lý mất memory mà không cấp quyền mặc định |

### 15.1. Kiểm thử không được tạo thêm rủi ro

Khi test logs, browser storage và network requests, dùng **token thử nghiệm, tài khoản test và môi trường kiểm soát**. Không dán access token thật vào bug report, screenshot, chat, URL hay fixture lưu trong Git. Với test XSS có chủ đích, chỉ chạy trong môi trường được cấp phép và ghi nhận kết quả tổng quát thay vì exfiltrate credential thật.

## 16. Checklist triển khai production

1. **Xác định loại ứng dụng:** SPA, Worker, BFF, native hay Java service; “memory” phải được định nghĩa theo vòng đời/process cụ thể.
2. **Lấy token bằng flow đúng:** Authorization Code + PKCE cho browser public client, OIDC khi cần login; quản lý `state`, `nonce`, redirect URI và PKCE transaction.
3. **Giữ access token trong vùng hẹp nhất:** closure/vault/worker, tránh DOM, URL, Redux Persist, Web Storage và logs.
4. **Không giả định memory chống XSS:** kiểm soát injection, CSP, Trusted Types và third-party scripts; giới hạn các API actions.
5. **Giới hạn token:** TTL ngắn, audience/scope tối thiểu và không nhúng dữ liệu riêng tư thừa trong JWT.
6. **Thiết kế phục hồi sau reload:** reauthorization/SSO hợp lệ hoặc BFF session; không dùng refresh token bền vững một cách vô thức.
7. **Bảo vệ refresh token riêng:** rotation hoặc sender constraint cho public client theo chuẩn áp dụng, token family, thu hồi và single-flight refresh.
8. **Ngăn credential gửi sai nơi:** API origin cố định/allowlist, HTTPS, CORS đúng thiết kế; không đưa Bearer token vào URL.
9. **Kiểm soát multi-tab/Worker:** không broadcast raw token; đánh giá bfcache, timeout, process termination và race.
10. **Xây logout đúng nghĩa:** clear local token/cache, invalidate session, revoke grant và access token khi policy đòi.
11. **Giữ server-side authorization:** kiểm tra JWT chữ ký/issuer/audience/`exp`/`nbf` hoặc opaque introspection, scope, principal và ownership.
12. **Với Java backend:** token store theo session/client/resource, TTL/eviction, bảo vệ heap/logs, multi-instance và session/cookie/CSRF.
13. **Thử nghiệm và quan sát:** leak tests, refresh race, 401/403, bfcache, restart, replay và event logs không chứa credential.

## 17. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access/refresh token, grant, response và phân biệt authorization server với resource server.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): bảo vệ authorization code qua `code_verifier` và `code_challenge`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer semantics, `Authorization`, `invalid_token` và rủi ro credential bị lộ.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): hướng dẫn về token, public clients, refresh token rotation và giảm replay.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token bằng bằng chứng khóa theo request.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS-bound tokens và ràng buộc chứng chỉ.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): validation JWT access token tại resource server.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, authorization code flow, nonce và login.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): rủi ro lưu dữ liệu nhạy cảm trong browser storage.
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): phòng chống XSS song song với thiết kế token storage.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): quản lý OAuth2 authorized clients ở backend Java/Spring.

**Ghi nhớ:** **Lưu access token trong memory** là chiến lược giảm **sự tồn tại bền vững** của bearer credential tại client, không phải phương pháp bảo đảm token không thể bị đánh cắp. SPA cần chấp nhận việc reload làm mất token, có luồng PKCE/refresh phù hợp và phòng chống XSS. BFF có thể giữ OAuth token phía Java backend để browser chỉ dùng session cookie, nhưng cần bảo vệ CSRF/session. Bất kể token nằm ở memory nào, **resource server luôn phải xác minh token đúng issuer, audience, thời hạn, scope và quyền trên tài nguyên; logout/thu hồi và chống replay phải được thiết kế riêng**.
