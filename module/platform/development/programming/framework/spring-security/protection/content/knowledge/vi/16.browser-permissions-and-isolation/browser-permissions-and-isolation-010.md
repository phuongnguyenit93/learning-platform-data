# Khả năng hỗ trợ trên trình duyệt và kiểm thử suy giảm chức năng

## 1. Bài toán: cùng một security header, nhiều trình duyệt và nhiều kết quả

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, người học triển khai các lớp bảo vệ HTTP và trình duyệt trong Spring Security: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session. Ở chương **Quyền và cô lập trình duyệt**, bài này tập trung vào hai nhiệm vụ thường bị bỏ sót sau khi cấu hình header: **xác nhận trình duyệt thực sự hỗ trợ chính sách** và **kiểm thử ứng dụng suy giảm chức năng an toàn** khi một khả năng không có sẵn.

Một nền tảng đào tạo tại `https://learn.example.com` có:

- Trang mô phỏng `/isolated/simulator` dùng khả năng xử lý song song, có thể yêu cầu `SharedArrayBuffer` và **cross-origin isolation**.
- Trang `/auth/popup-launcher` mở popup đăng nhập với nhà cung cấp danh tính bên ngoài.
- Trang `/classroom/live` dùng iframe của đối tác để truyền hình ảnh/âm thanh.
- Trang nội dung `/courses/42` có ảnh và video từ CDN.
- API riêng `/api/me` yêu cầu session hợp lệ và kiểm tra quyền server.

Nhóm kỹ thuật bật:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Permissions-Policy: camera=(), microphone=(), geolocation=()
Referrer-Policy: strict-origin-when-cross-origin
```

Sau đó, một số máy dùng trình duyệt mới chạy mô phỏng đa luồng, một số máy chỉ chạy phiên bản cơ bản, popup OAuth không nhận callback, còn iframe phòng học có thể hiển thị nhưng không lấy được microphone. Điều đó **không thể được giải thích chỉ bằng việc header có hay không**.

Ta phải phân biệt:

1. **Server có gửi chính sách đúng không?**
2. **Browser/phiên bản/ngữ cảnh có hiểu và áp dụng chính sách không?**
3. **Các tiền điều kiện của tính năng có đủ không?** Ví dụ HTTPS, origin phù hợp, user permission, thiết bị, cookie, policy của ancestor.
4. **Ứng dụng xử lý được trường hợp thiếu tính năng không?** Trường hợp nào có thể giảm cấp hợp lệ và trường hợp nào phải từ chối?
5. **Kiểm thử có chứng minh kết quả thực tế không**, hay chỉ kiểm tra chuỗi response header?

### Mục tiêu học tập

Sau bài, bạn có thể:

- Lập **ma trận hỗ trợ và hợp đồng hành vi** cho browser mục tiêu, không dựa vào một câu “đã hỗ trợ từ phiên bản X” thiếu kiểm chứng.
- Đặt ranh giới giữa **graceful degradation**, **progressive enhancement** và **fail closed**.
- Viết JavaScript **feature detection** đúng cho isolation và browser APIs; xử lý trường hợp không thể kiểm tra policy.
- Cấu hình header theo route bằng **Spring Security Servlet và Reactive/WebFlux**.
- Xây dựng kiểm thử hai lớp: **MockMvc/WebTestClient** cho HTTP và **browser E2E** cho hành vi.
- Thiết kế rollout, telemetry và rollback có giới hạn khi thay đổi COOP/COEP/CORP/CORS, Permissions-Policy và Referrer-Policy.

## 2. “Được hỗ trợ” có ít nhất bốn nghĩa

Không nên viết trong báo cáo bảo mật: “Header `Cross-Origin-Embedder-Policy` được hỗ trợ nên hệ thống đã an toàn” mà không chỉ rõ **hỗ trợ điều gì**.

| Cấp độ | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Phát header** | Spring Security/proxy có gửi giá trị mong muốn trên response đúng không? | MockMvc, WebTestClient, DevTools Network, HTTP response cuối. |
| **Nhận biết cú pháp** | Browser có hiểu tên header, giá trị và directive này không? | Tài liệu tương thích theo browser/version; phép thử tại browser mục tiêu. |
| **Thực thi trong ngữ cảnh** | Browser có áp policy với loại tài nguyên, iframe, popup, origin và request mode cụ thể không? | Thử nghiệm browser có đối chứng dương/âm, Console và Network. |
| **Ứng dụng vẫn dùng được** | UI/flow có chuyển sang đường dự phòng đúng, không làm mất bảo mật hoặc dữ liệu không? | E2E, kiểm thử nghiệp vụ, accessibility, error handling và telemetry. |

Ví dụ, `Permissions-Policy: camera=()` có thể được gửi chính xác nhưng một trình duyệt cũ **không thực thi directive**. Đây là **khoảng trống kiểm soát phía client**, không phải bằng chứng policy hoạt động. Mặt khác, một browser hiểu `camera` vẫn có thể không cho mở camera vì người dùng từ chối, OS tắt thiết bị hoặc trang không phải secure context.

Tương tự, COOP `same-origin` có thể được browser thực thi rất tốt, nhưng **làm hỏng callback OAuth** do ứng dụng phụ thuộc `window.opener`. Đó là vấn đề **tương thích hành vi**, không phải chứng cứ header không được hỗ trợ.

### Một quy tắc phân loại kết quả

```text
Header xuất hiện?
  ├─ Không → lỗi cấu hình / chain / proxy / response
  └─ Có
      ├─ Browser không hỗ trợ → mất hiệu lực phòng vệ phía browser
      │                         hoặc cần UI fallback / fail closed
      └─ Browser hỗ trợ
          ├─ Tiền điều kiện không đạt → lỗi HTTPS / permission /
          │                            origin / CORP / CORS / iframe
          └─ Điều kiện đạt
              ├─ Chức năng hoạt động → PASS
              └─ Chức năng hỏng → kiểm tra app logic / SDK /
                                  session / redirect / chính sách khác
```

**Không coi tất cả nhánh “không hoạt động” đều là kết quả tốt của chính sách bảo mật.** Một ảnh không tải vì `404` không chứng minh CORP đang chặn; popup không mở vì popup blocker không chứng minh COOP đã tách opener.

## 3. Ma trận tương thích: đừng nhầm hỗ trợ header với hỗ trợ tính năng

Mức hỗ trợ còn phụ thuộc **browser engine**, phiên bản cụ thể, cấu hình người dùng, mobile/desktop, chế độ riêng tư và ngữ cảnh nhúng. Không nên hard-code một bảng `Chrome = có`, `Safari = không` cho mọi thời điểm; chính sách và API thay đổi độc lập.

| Cơ chế | Những điểm phải kiểm tra trên client thực tế | Hậu quả nếu thiếu / khác hành vi |
| --- | --- | --- |
| **`Referrer-Policy`** | Header có được áp khi điều hướng, tải subresource và downgrade HTTPS không? Giá trị dùng có được nhận không? | URL nguồn có thể bị gửi rộng hơn dự kiến, hoặc analytics thiếu dữ liệu. |
| **`Permissions-Policy`** | Hỗ trợ từng directive như `camera`/`microphone`; header, iframe `allow`, policy inheritance. | Có thể thiếu lớp chặn tính năng; hoặc iframe hợp lệ không dùng được API. |
| **`X-Permitted-Cross-Domain-Policies`** | Chỉ liên quan một số client/plugin Adobe legacy; không được xem là cơ chế browser web hiện đại. | Không có tác dụng kiểm soát `fetch`/CORS hiện đại; rủi ro file policy legacy cần xử lý riêng. |
| **COOP** | `same-origin`, `same-origin-allow-popups`, hành vi popup/redirect/opener. | Có thể giữ quan hệ cửa sổ ngoài ý muốn hoặc làm hỏng popup đăng nhập. |
| **COEP** | `require-corp`; `credentialless` nếu sử dụng; worker/iframe/resource graph. | Tài nguyên ngoài origin bị chặn, hoặc browser không đạt isolation. |
| **CORP** | `same-origin`/`same-site`/`cross-origin` trong request `no-cors`; phân biệt schemeful site. | Tài nguyên bị lộ khả năng nhúng ngoài dự kiến hoặc bị chặn nhầm. |
| **CORS** | Preflight, response ACAO, credentials, cache `Vary: Origin`, request mode. | API cross-origin không đọc được; hoặc policy quá rộng dẫn đến lộ dữ liệu nếu backend sai quyền. |
| **CSP / frame policies** | `script-src`, `connect-src`, `frame-src`, `frame-ancestors`, XFO; mức hỗ trợ directive. | Widget, SDK hoặc iframe lỗi; script không tin cậy có thể không bị giới hạn như thiết kế. |
| **`SharedArrayBuffer`/cross-origin isolation** | `isSecureContext`, `crossOriginIsolated`, sự tồn tại API và môi trường frame. | Phiên bản mô phỏng đa luồng không chạy; cần phiên bản cơ bản hoặc từ chối tính năng. |

### Nguồn dữ liệu và cách ghi nhận

Trước release, tra tài liệu **MDN Browser Compatibility Data**, tài liệu vendor/browser và compatibility notes của SDK; nhưng xem đó là **điểm khởi đầu**, không thay việc kiểm tra trên phiên bản browser nằm trong danh sách hỗ trợ của sản phẩm.

Một bản ghi kiểm chứng nên gồm:

```text
Feature: COEP require-corp + cross-origin isolation
Browser engine: Chromium / Firefox / WebKit / browser khác
Browser version: <phiên bản test thật>
OS/device: <môi trường test thật>
Context: top-level HTTPS, iframe, private browsing... (nếu có)
Expected policy: COOP same-origin; COEP require-corp
Expected behavior: basic mode hoặc parallel mode theo năng lực thật
Observed headers: <đúng response>
Observed behavior: <PASS/FAIL và bằng chứng>
Owner/date: <người phụ trách / ngày kiểm tra>
```

**Không gán phiên bản cụ thể nếu chưa xác minh.** Đặc biệt, Playwright chạy WebKit **không đồng nghĩa** đã thử chính xác Safari trên mọi phiên bản macOS/iOS; vẫn cần kiểm thử Safari thật nếu sản phẩm cam kết hỗ trợ.

## 4. Progressive enhancement, graceful degradation và fail closed

Ba chiến lược này **không tương đương**.

### 4.1. Progressive enhancement — chức năng cơ bản trước

Ứng dụng được thiết kế với đường hoạt động **cơ bản, an toàn**; tính năng nâng cao chỉ xuất hiện khi browser đạt điều kiện.

Ví dụ trang mô phỏng:

- **Basic mode:** xử lý tuần tự hoặc dùng worker không chia sẻ bộ nhớ theo thuật toán phù hợp.
- **Parallel mode:** dùng thuật toán đa luồng yêu cầu `SharedArrayBuffer` khi ngữ cảnh đáp ứng cross-origin isolation.

Người dùng vẫn hoàn thành bài học với basic mode nếu thiếu khả năng nâng cao, nhưng không được báo sai rằng engine đa luồng đã hoạt động.

### 4.2. Graceful degradation — giảm cấp có kiểm soát

Nếu một thành phần tùy chọn (analytics, biểu đồ nâng cao, camera trên trang học thông thường) không sẵn có, ứng dụng có thể:

- Giữ nội dung/chức năng chính.
- Hiển thị thông báo rõ ràng về tính năng không dùng được.
- Tạo hướng thay thế đã kiểm chứng, ví dụ tải bảng dữ liệu thay biểu đồ tương tác.
- Ghi telemetry không chứa token/dữ liệu nhạy cảm để đội vận hành nhận biết tác động.

**Giảm cấp không có nghĩa tắt biện pháp bảo mật** chỉ để UI ngừng báo lỗi.

### 4.3. Fail closed — khi thiếu kiểm soát thì không tiếp tục

Một số chức năng **không có đường dự phòng an toàn**:

- Endpoint có dữ liệu cá nhân không được phép bỏ xác thực/phân quyền nếu browser không hỗ trợ CORP.
- API thay đổi trạng thái không được bỏ CSRF chỉ vì client không gửi preflight đúng.
- Tính năng yêu cầu isolation vì ràng buộc bảo mật không được âm thầm bật lại khi `crossOriginIsolated` là `false`.
- Trang yêu cầu quyền microphone không được cố mở thiết bị bằng thủ thuật vượt policy/browser permission.

Khi đó, **chặn riêng chức năng**, giải thích lý do và hướng người dùng tới môi trường được hỗ trợ hoặc một quy trình thay thế an toàn.

| Khả năng thiếu | Giảm cấp chấp nhận được | Không được làm |
| --- | --- | --- |
| `SharedArrayBuffer` cho mô phỏng nâng cao | Chạy thuật toán basic mode **không cần** SharedArrayBuffer nếu có và đúng kết quả. | Giả vờ chạy parallel mode; bật API nhạy cảm bằng cách bỏ điều kiện an toàn. |
| Camera/microphone được user từ chối | Cho phép xem nội dung, chat hoặc nghe thụ động nếu nghiệp vụ cho phép. | Tự động xin lại liên tục; bỏ kiểm soát permission. |
| Popup OAuth không giữ opener | Dùng top-level redirect hoặc server-side completion đã bảo vệ. | Bỏ `state`/PKCE, gửi token bằng `postMessage("*")`. |
| Ảnh hoặc biểu đồ tùy chọn từ CDN bị COEP chặn | Dùng ảnh/tài nguyên cùng origin hoặc bản tĩnh đã được phê duyệt. | Đặt `CORP: cross-origin` cho mọi API riêng tư. |
| Analytics bên thứ ba lỗi | Tắt riêng analytics mà chức năng học tập vẫn chạy. | Tắt toàn bộ CSP/COEP trên các trang nhạy cảm. |
| Browser không hiểu một security directive bắt buộc | Chặn flow nhạy cảm hoặc giới hạn client hỗ trợ; giữ quyền server. | Dựa vào header không được thực thi như bằng chứng bảo vệ. |

## 5. Chuẩn hóa “hợp đồng hành vi” theo tính năng

Mỗi tính năng cần một **behavior contract** có thể kiểm thử. Ví dụ:

| Tính năng | Tiền điều kiện | Khi đầy đủ | Khi thiếu | An toàn phải giữ |
| --- | --- | --- | --- | --- |
| Mô phỏng song song | Secure context, cross-origin isolation, API thích hợp | Parallel mode; kết quả chính xác | Basic mode nếu thuật toán thay thế hợp lệ | Không dùng tính năng yêu cầu isolation ở ngữ cảnh không cô lập. |
| Đăng nhập OAuth | IdP hoạt động, callback, cookie, `state`/PKCE | Session được backend xác thực | Redirect top-level hoặc thông báo thử lại | Không tự tin payload popup; không lộ mã/token. |
| Họp video | HTTPS, policy camera/mic phù hợp, quyền người dùng, thiết bị | Truyền thông media với user consent | Audio-only/chat/view-only nếu sản phẩm hỗ trợ | Không tự vượt chính sách thiết bị. |
| Biểu đồ từ CDN | CSP, COEP, CORP/CORS phù hợp | Biểu đồ tương tác | Bảng/text/asset same-origin | Không mở rộng policy cho dữ liệu riêng. |
| API cross-origin | CORS hợp lệ, session/quyền server | Response đọc được bởi origin được cấp phép | Hiển thị lỗi/kịch bản dự phòng | Không đổi `fetch` thành `no-cors` để lấy JSON; không nới ACAO tùy tiện. |
| Referrer của link ngoài | Browser hiểu policy và link metadata | Thông tin `Referer` theo chính sách | Thiết kế URL không chứa secrets; dùng `rel=noreferrer` nơi phù hợp | Không đặt token trong URL. |

Trong tiêu chí chấp nhận, ghi rõ **cái gì có thể suy giảm** (mức hiệu năng, biểu đồ, tùy chọn video) và **cái gì không được suy giảm** (ủy quyền, CSRF, tính bí mật của session, xác thực OAuth).

## 6. Feature detection cho cross-origin isolation

Không dùng `User-Agent` để đoán liệu code có được phép dùng `SharedArrayBuffer`. Phải **kiểm tra năng lực và ngữ cảnh hiện tại**.

Ví dụ JavaScript có thể chạy trong trang `/isolated/simulator`:

```javascript
function detectParallelCapability() {
  const secureContext = window.isSecureContext === true;
  const isolated = window.crossOriginIsolated === true;
  const sabAvailable = typeof SharedArrayBuffer === "function";
  const workerAvailable = typeof Worker === "function";

  return {
    secureContext,
    isolated,
    sabAvailable,
    workerAvailable,
    parallelReady:
      secureContext && isolated && sabAvailable && workerAvailable
  };
}

const capabilities = detectParallelCapability();
console.table(capabilities);
```

**Không suy luận sai:**

- Có `COOP: same-origin` trên response **không đủ** để kết luận isolation đã đạt.
- `crossOriginIsolated === true` là tín hiệu cần quan sát trong ngữ cảnh thật; còn phải kiểm tra API cụ thể và yêu cầu của engine.
- `SharedArrayBuffer` không phải một thay thế kiểu dữ liệu trực tiếp cho `ArrayBuffer` trong mọi thuật toán; fallback phải là **đường xử lý được thiết kế riêng**.
- Worker có thể bị CSP `worker-src`, URL/script mode hoặc browser policy chặn ngay cả khi constructor `Worker` tồn tại.

### Chọn đường chạy rõ ràng

```javascript
const cap = detectParallelCapability();

async function startSimulation(input) {
  if (cap.parallelReady) {
    return startParallelEngine(input); // Hàm do ứng dụng triển khai.
  }

  return startBasicEngine(input);      // Thuật toán fallback độc lập.
}

const mode = cap.parallelReady ? "parallel" : "basic";
document.getElementById("engine-mode").textContent = mode;
```

Đoạn mã **minh họa điểm chọn đường thực thi**, không tự triển khai hai engine. Hai hàm `startParallelEngine` và `startBasicEngine` cần có thực, được test về **tính đúng của kết quả** và được giám sát hiệu năng.

Nếu không thể xây dựng basic mode an toàn/tương đương, ứng dụng nên hiển thị trạng thái:

```text
Mô phỏng nâng cao không khả dụng trong trình duyệt hoặc ngữ cảnh này.
Vui lòng dùng phiên bản trình duyệt được hỗ trợ hoặc chọn bài học thay thế.
```

Không âm thầm chạy engine có yêu cầu isolation trong ngữ cảnh thiếu điều kiện.

## 7. Không nhầm kiểm tra permission với quyền được cấp thực tế

Đối với camera/microphone, có ít nhất ba lớp:

1. **Permissions-Policy** cho phép tính năng trong tài liệu/iframe ở mức policy.
2. **API và ngữ cảnh** đủ điều kiện: `navigator.mediaDevices`, secure context, điều kiện browser.
3. **Quyền người dùng, OS và thiết bị** chấp thuận và khả dụng.

Một số browser cung cấp:

```javascript
const policy = document.permissionsPolicy ?? document.featurePolicy;

function policyAllows(featureName) {
  if (policy && typeof policy.allowsFeature === "function") {
    return policy.allowsFeature(featureName);
  }
  return null; // Không xác định được bằng API kiểm tra này.
}

console.log("camera policy:", policyAllows("camera"));
console.log("microphone policy:", policyAllows("microphone"));
```

**`null` không nghĩa là “được phép” hay “bị chặn”.** Nó có nghĩa API introspection đang dùng **không khả dụng hoặc không kết luận được** trên browser này. Thậm chí `true` chỉ cho biết policy **không chặn**, không chứng minh permission của user đã cấp.

### Cách suy giảm chức năng an toàn

Nếu lớp học có video tùy chọn:

- Chỉ yêu cầu `getUserMedia` sau thao tác chủ động của người dùng.
- Kiểm tra browser có API hay không; nếu thiếu, hiển thị lựa chọn chat/view-only.
- Khi `NotAllowedError` xảy ra, không tự quy nó là lỗi policy: user có thể từ chối, OS chặn hoặc browser đã có quyết định lưu.
- Nếu có stream thành công, dừng các track khi rời phòng hoặc kết thúc kiểm tra; không giữ mic/camera chạy nền ngoài ý định.
- Không cần bật camera/mic thật để kiểm thử **response header** trong CI.

Ví dụ guard:

```javascript
async function requestLocalMedia() {
  if (!window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia) {
    return { ok: false, reason: "unsupported-or-insecure" };
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: true
    });
    return { ok: true, stream };
  } catch (error) {
    return { ok: false, reason: error.name };
  }
}

// Chỉ gọi requestLocalMedia() từ sự kiện người dùng đã đồng ý.
// Khi không còn dùng: stream.getTracks().forEach(track => track.stop()).
```

Khi tính năng không hỗ trợ, **không thử vượt qua browser permission bằng request khác**. Hiển thị trạng thái thiếu thiết bị/quyền một cách dễ hiểu và để người dùng quyết định tiếp tục bằng một chế độ được hỗ trợ.

## 8. Popup, COOP và suy giảm luồng đăng nhập

Một ứng dụng có thể cần COOP `same-origin` để giảm quan hệ giữa các cửa sổ cấp cao. Nhưng các SDK OAuth popup cũ thường dùng `window.opener` hoặc `WindowProxy.closed` để nhận biết khi đăng nhập hoàn tất.

Ví dụ trang mở popup:

```javascript
let authPopup = null;

function openLogin() {
  authPopup = window.open(
    "/oauth2/authorization/partner",
    "partnerLogin",
    "width=520,height=660"
  );
  return authPopup !== null;
}
```

Khi trang gửi:

```http
Cross-Origin-Opener-Policy: same-origin
```

browser hỗ trợ có thể **tách browsing context group** với IdP khác origin. Popup có thể thấy `window.opener === null`; tham chiếu của opener có thể phản ánh tình trạng tách dù popup vẫn mở. Lưu ý `window.open()` trả `null` còn có thể do **popup blocker** hoặc tùy chọn `noopener`.

### Hai lộ trình thay thế

**Phương án 1 — Đổi sang top-level redirect.** Trình duyệt rời trang chính để hoàn tất OAuth/OIDC và quay về callback, không cần truyền tin qua `window.opener`. Vẫn phải bảo vệ `state`, PKCE, redirect URI, phiên và quyền backend.

**Phương án 2 — Giữ popup nhưng không phụ thuộc opener.** Popup hoàn tất xác thực tại backend; trang chính hỏi endpoint cùng origin về trạng thái giao dịch có thời hạn, ràng buộc session, chống đoán và giới hạn tần suất. Có thể dùng cơ chế sự kiện cùng origin khi thích hợp, nhưng **không coi tín hiệu client là bằng chứng đăng nhập**.

Nếu bắt buộc giữ callback qua opener, cân nhắc:

```http
Cross-Origin-Opener-Policy: same-origin-allow-popups
```

**chỉ trên trang thực sự làm opener** và chỉ khi IdP/popup có policy tương thích. Một IdP tự phát COOP `same-origin` vẫn có thể làm tham chiếu bị cắt. Không nới COOP ở toàn bộ `/admin/**` hoặc `/account/**` chỉ để một popup hoạt động.

### Kiểm tra tin nhắn popup

Khi `postMessage` được dùng, kiểm tra `event.origin`, `event.source` (khi còn xác định được), schema, trạng thái giao dịch và session phía server. Không đưa access/refresh token vào thông điệp tùy tiện; không dùng `targetOrigin: "*"` cho dữ liệu nhạy cảm.

**Hợp đồng fallback:** khi popup mất opener hoặc bị chặn, người dùng vẫn có một nút **Đăng nhập bằng chuyển hướng**. Ứng dụng **không** bỏ kiểm tra OAuth/CSRF để “giữ trải nghiệm”.

## 9. COEP/CORP/CORS: suy giảm đúng khi tài nguyên không tải

Trang `/isolated/simulator` gửi:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Nó tải ảnh CDN:

```html
<img
  src="https://cdn.partner.example/public/chart.png"
  alt="Biểu đồ"
  id="chart-image">
```

Ảnh cross-origin thường được tải theo `no-cors`. Với `COEP: require-corp`, response ảnh có thể cần:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Nếu CDN không phát CORP, ảnh có thể bị chặn dù request trả `200 OK`. Một giải pháp khác, nếu loại tài nguyên hỗ trợ, là yêu cầu CORS mode:

```html
<img
  src="https://cdn.partner.example/public/chart.png"
  crossorigin="anonymous"
  alt="Biểu đồ"
  id="chart-image">
```

với response CDN:

```http
Access-Control-Allow-Origin: https://learn.example.com
```

**Không có phép màu khi thay đổi mode:** nếu ảnh vẫn `no-cors`, chỉ thêm ACAO không tự thay CORP; nếu chuyển sang `cors` mà CDN không cho phép CORS, ảnh vẫn lỗi. `CORP: cross-origin` trên HTML **không thay thế** CORP trên response ảnh.

### Ma trận chẩn đoán cho ảnh

| COEP trang | Response ảnh cross-origin | `<img>` no-cors | `<img crossorigin="anonymous">` |
| --- | --- | --- | --- |
| `require-corp` | Không CORP, không ACAO | Bị chặn theo COEP | Bị chặn CORS. |
| `require-corp` | `CORP: cross-origin` | Có thể tải | Vẫn cần CORS. |
| `require-corp` | ACAO hợp lệ, không CORP | Có thể bị COEP chặn | Có thể tải. |
| `credentialless` | Public asset không CORP/ACAO | Có thể tải **không credentials** ở browser hỗ trợ | Vẫn cần CORS. |
| `unsafe-none` hoặc thiếu COEP chặt | Không CORP/ACAO | Ảnh thường có thể tải nếu chính sách khác cho phép | Vẫn cần CORS. |

**Tài nguyên CORP hạn chế vẫn phải được tôn trọng.** Không dùng `COEP: credentialless` như phương pháp vượt `CORP: same-origin` tường minh trên resource; kiểm tra thêm tác động khi request không mang cookie.

### Graceful degradation có giá trị ở đâu?

Với logo, biểu đồ hoặc tài liệu minh họa:

- Thử resource public ở **cùng origin** hoặc bản đã phân phối qua pipeline hợp lệ.
- Có thể hiển thị bảng dữ liệu/text thay biểu đồ tương tác.
- Không được lén mở `CORP: cross-origin` cho **API tài khoản hoặc tài liệu riêng**.
- Nếu tài nguyên bắt buộc cho quyết định có rủi ro cao, nên **hiển thị lỗi rõ ràng**, tránh đưa ra kết quả thiếu dữ liệu.

### Worker, font, module, iframe không giống `<img>`

Module scripts/font thường có yêu cầu CORS riêng; worker chịu policy/URL/worker-src liên quan; iframe có chính sách của **tài liệu con**, CSP `frame-ancestors`/XFO, cookie, sandbox và điều kiện COEP. Không suy một đường tải ảnh thành toàn bộ thuật toán tải tài nguyên.

## 10. Iframe và quyền camera: ma trận ba tầng

Một widget họp được nhúng:

```html
<iframe
  src="https://meeting.partner.example/room/42"
  title="Lớp học trực tuyến"
  allow="camera; microphone; fullscreen"
  width="960"
  height="600">
</iframe>
```

Nó có thể gặp ba nhóm lỗi khác nhau:

| Tầng | Kiểm tra | Dấu hiệu |
| --- | --- | --- |
| **Nhúng được tài liệu?** | CSP `frame-src` của cha; `frame-ancestors`/XFO của con; redirect, sandbox. | Iframe trắng hoặc bị browser từ chối hiển thị. |
| **Tải được tài nguyên con?** | COEP, CORP/CORS của script/ảnh/font/worker; CSP của widget. | Iframe có HTML nhưng thiếu script/UI, lỗi Console/Network. |
| **Dùng được thiết bị?** | Permissions-Policy cha/con, iframe `allow`, HTTPS, user consent, OS và thiết bị. | UI họp có nhưng không bật được camera/mic. |

Nếu policy của trang cha `camera=()`, **iframe `allow="camera"` không thể tự mở khả năng đã bị cấm ở ancestor**. Nếu cha cho phép origin đối tác, frame vẫn có thể bị hạn chế bởi policy của tài liệu con hoặc quyền người dùng.

Ví dụ khi có ngoại lệ được phê duyệt:

```http
Permissions-Policy: camera=(self "https://meeting.partner.example"), microphone=(self "https://meeting.partner.example"), geolocation=()
```

**Header này chỉ đưa origin vào phạm vi policy**, không tự cấp quyền user. Mức hỗ trợ directive/iframe inheritance của từng browser phải được kiểm thử; nếu không hỗ trợ bảo vệ bắt buộc thì không tự coi trang đã an toàn.

## 11. Referrer-Policy và header legacy: không phải mọi suy giảm đều là UI

### 11.1. Referrer-Policy cần quan sát việc gửi dữ liệu thật

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Đối với đường dẫn chuyển ra ngoài, policy có thể giảm mức chi tiết của `Referer`. Tuy nhiên một browser cũ/giá trị không được hỗ trợ có thể áp chính sách khác, khiến thông tin URL nguồn được gửi theo hành vi không như mong đợi.

**Phòng vệ không được dựa hoàn toàn vào header**:

- Không đưa access token, mã bí mật hoặc thông tin nhạy cảm vào URL/query nếu tránh được.
- Dùng `rel="noreferrer"` trên liên kết ra ngoài khi cần bảo vệ referrer theo thao tác cụ thể.
- Kiểm tra cả navigation, image/script requests và HTTPS-to-HTTP downgrade khi phù hợp.
- Dùng endpoint nhận request do chính bạn sở hữu để **ghi nhận header `Referer`** cho phép thử; không gửi dữ liệu thật ra dịch vụ bên ngoài.

Một phép thử `curl` chỉ đọc `Referrer-Policy` trên response HTML **không chứng minh** browser đã gửi `Referer` như thiết kế.

### 11.2. X-Permitted-Cross-Domain-Policies không phải fallback cho browser hiện đại

```http
X-Permitted-Cross-Domain-Policies: none
```

Header này liên quan đến meta-policy của một số **client Adobe legacy** với các file như `crossdomain.xml`. Nó không thay cho CORS của `fetch` và không trực tiếp bảo vệ camera/iframe của browser hiện đại.

Trong sản phẩm không còn client legacy:

1. Không giả định header được browser hiện đại thực thi trong mô hình CORS.
2. Kiểm kê/loại bỏ `crossdomain.xml` và `clientaccesspolicy.xml` không còn cần thiết; chính sách Silverlight cần xem riêng.
3. Giữ `X-Permitted-Cross-Domain-Policies: none` như defense in depth khi phù hợp.
4. Đánh giá CORS, CSRF và quyền server độc lập.

Đây là ví dụ quan trọng về **khác nhau giữa header tồn tại ở HTTP và header có tác dụng trong browser đang dùng**.

## 12. Thiết kế ma trận kiểm thử theo engine, phiên bản và chức năng

Tối thiểu nên có ba nhóm browser engine được sản phẩm hỗ trợ, ví dụ:

- **Chromium** (Chrome/Edge tương ứng).
- **Firefox** (Gecko).
- **WebKit**, kết hợp kiểm thử **Safari thực tế** trên những macOS/iOS được hỗ trợ.

Đây là **đề xuất coverage**, không phải cam kết rằng mọi ứng dụng phải hỗ trợ tất cả browser/version hoặc rằng Playwright WebKit tương đương toàn bộ Safari.

### Ma trận chức năng và môi trường

| Test case | Chromium | Firefox | WebKit | Safari/iOS thực |
| --- | --- | --- | --- | --- |
| Header COOP/COEP/CORP nhận đúng | HTTP smoke | HTTP smoke | HTTP smoke | Network/remote inspector khi phù hợp |
| `crossOriginIsolated` và basic/parallel mode | E2E + fallback | E2E + fallback | E2E + fallback | E2E/manual trên thiết bị |
| Popup OAuth/opener/callback | E2E | E2E | E2E | Test IdP và redirect thật |
| `no-cors` image với CORP | Dương + âm | Dương + âm | Dương + âm | Quan sát asset/Console |
| CORS API/preflight/credentials | E2E + HTTP | E2E + HTTP | E2E + HTTP | Cookie/tracking rules |
| Permissions-Policy camera/mic | API/policy + simulated | API/policy + simulated | API/policy + simulated | User consent/hardware |
| Referrer-Policy theo link | Server ghi `Referer` | Server ghi `Referer` | Server ghi `Referer` | Kiểm tra HTTPS/site thật |
| Iframe + third-party cookies | E2E | E2E | E2E | Trọng điểm khác biệt platform |

“Smoke” không phải nhãn PASS; phải ghi **kết quả thực của từng bản chạy**. Nếu một browser không nằm trong danh sách hỗ trợ chính thức, vẫn cần xác định cách ứng dụng thông báo **trình duyệt không hỗ trợ** hoặc fallback hợp lệ.

### Ba chiều thử nghiệm bổ sung

1. **Top-level vs iframe:** khả năng trong iframe phụ thuộc sandbox, permissions inheritance, COEP của ancestor và cookie.
2. **HTTPS vs local:** `localhost` thường được coi là potentially trustworthy, không thay cho kiểm thử HTTPS production với scheme/host/port thật.
3. **Browser thường vs riêng tư/giới hạn tracking:** cookie partitioning, third-party cookie blocking và permission prompts có thể khác.

Không dùng chỉ một máy local và một browser để tuyên bố “tương thích đa nền tảng”.

## 13. Spring Security Servlet: chính sách theo đúng nhóm trang

Để giảm tác động không cần thiết, ví dụ Servlet dưới đây chỉ phát **COOP+COEP chặt** cho `/isolated/**`; trang mở OAuth popup có COOP khác; phần còn lại giữ policy cơ bản. Code minh họa **Spring Security hiện đại dùng component-based `SecurityFilterChain`**; cần đối chiếu phiên bản dependency thực tế.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.StaticHeadersWriter;

@Configuration
@EnableWebSecurity
public class BrowserCompatibilitySecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain isolated(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/isolated/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Opener-Policy", "same-origin"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Embedder-Policy", "require-corp"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin")))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain loginLauncher(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/auth/popup-launcher")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Opener-Policy",
                    "same-origin-allow-popups"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin")))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain remaining(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()")))
            .build();
    }
}
```

### Những giới hạn của ví dụ

1. `securityMatcher` chọn **chain phát header**; `@Order` phải đặt matcher cụ thể trước fallback.
2. `authorizeHttpRequests` điều khiển quyền server, **không tự đổi COOP/COEP**.
3. `authenticated()` chỉ minh họa yêu cầu đăng nhập. Dự án thật phải có `oauth2Login`/login, role/tenant authorization, CSRF, session và entrypoint phù hợp.
4. Trang `/auth/popup-launcher` `permitAll()` **không tự triển khai OAuth**, cũng không bảo đảm IdP giữ opener. Nếu chỉ copy cấu hình này, OAuth authorization/callback vẫn cần được xử lý trong security infrastructure của ứng dụng.
5. Chain isolated **không tự có Permissions-Policy** từ `remaining`. Các chain không cộng dồn header của nhau; nếu cần một baseline trên mọi HTML, phải thêm phù hợp vào mỗi chain hoặc một tầng chung được thiết kế rõ.
6. Header COEP ở HTML **không thay** CORP/CORS trên **response tài nguyên** do CDN phục vụ.
7. Không vô hiệu hóa mọi header chỉ để sửa lỗi browser: `headers(headers -> headers.disable())` có thể làm mất XFO, HSTS, nosniff và những phòng vệ khác.

### Tài nguyên public/private cần CORP riêng

Nếu ứng dụng **thực sự phục vụ** ảnh/script ở `/assets/public/**`, có thể thêm một chain có thứ tự trước fallback và dùng:

```java
// Bên trong .headers(...) của chain public assets.
.addHeaderWriter(new StaticHeadersWriter(
    "Cross-Origin-Resource-Policy", "cross-origin"))
```

Chỉ áp cho **asset công khai được thiết kế để nhúng cross-origin**. Đối với resource cá nhân hóa, `CORP: same-origin` có thể là defense in depth nhưng **vẫn bắt buộc** authorization, cache-control, session và chống lộ dữ liệu. Nếu CDN hoặc proxy phục vụ ảnh trực tiếp, phải sửa **response của CDN** chứ không chỉ ứng dụng HTML.

## 14. Spring Security Reactive/WebFlux: cùng chính sách, writer khác

Với Reactive, sử dụng `ServerHttpSecurity`, `SecurityWebFilterChain`, `StaticServerHttpHeadersWriter` và matcher dành cho `ServerWebExchange`. Ví dụ **thay thế** cho cấu hình Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.StaticServerHttpHeadersWriter;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class ReactiveBrowserCompatibilityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain isolated(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/isolated/**"))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Opener-Policy", "same-origin"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Embedder-Policy", "require-corp"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin")))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain loginLauncher(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/auth/popup-launcher"))
            .authorizeExchange(auth -> auth
                .anyExchange().permitAll())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Opener-Policy",
                    "same-origin-allow-popups"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin")))
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain remaining(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()")))
            .build();
    }
}
```

**Các khác biệt cần nhớ:**

- `StaticHeadersWriter` của Servlet và `StaticServerHttpHeadersWriter` của WebFlux **không tráo đổi cho nhau**.
- Một DSL cho header cụ thể có thể có hoặc không trên từng phiên bản Spring Security; static writer chỉ phát chuỗi đúng yêu cầu khi API cho phép.
- CORS cần cấu hình processor/`CorsConfigurationSource` phù hợp với Servlet hoặc Reactive; **không sửa CORS bằng cách chỉ viết ACAO tĩnh**.
- Một route không khớp chain sẽ không nhận header mong đợi; cần test matcher và `@Order`.
- Browser **không biết** response đến từ Servlet hay WebFlux; nó chỉ nhận HTTP headers và áp dụng theo ngữ cảnh.

## 15. Kiểm thử HTTP bằng MockMvc: chỉ xác minh phía server

Giả sử các endpoint thử nghiệm trả `200 OK` theo fixture, user `learner` có quyền truy cập:

```java
mockMvc.perform(get("/isolated/simulator").with(user("learner")))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cross-Origin-Opener-Policy", "same-origin"))
    .andExpect(header().string(
        "Cross-Origin-Embedder-Policy", "require-corp"))
    .andExpect(header().string(
        "Referrer-Policy", "strict-origin-when-cross-origin"));

mockMvc.perform(get("/auth/popup-launcher"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cross-Origin-Opener-Policy", "same-origin-allow-popups"))
    .andExpect(header().doesNotExist(
        "Cross-Origin-Embedder-Policy"));

mockMvc.perform(get("/courses/42").with(user("learner")))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()"));
```

Đây là phần thân test minh họa; cần `MockMvc`, controller/handler fixture, `spring-security-test` và static imports `get`, `user`, `status`, `header`.

### Test phạm vi và header mặc định

Một endpoint ngoài `/isolated/**` không nên vô tình nhận `COEP: require-corp` theo thiết kế trên:

```java
mockMvc.perform(get("/courses/42").with(user("learner")))
    .andExpect(header().doesNotExist(
        "Cross-Origin-Embedder-Policy"))
    .andExpect(header().string(
        "X-Content-Type-Options", "nosniff"));
```

Assertion `nosniff` yêu cầu header mặc định còn được bật trong cấu hình/test version thực tế. Nếu proxy thêm COEP ngoài Spring, MockMvc **không nhìn thấy proxy**; cần thêm test hạ tầng.

### Không lấy HTTP test làm bằng chứng browser enforcement

Các test trên có thể PASS kể cả khi browser:

- Không hỗ trợ một directive Permissions-Policy.
- Không đạt `crossOriginIsolated`.
- Làm hỏng popup OAuth do COOP.
- Chặn CDN bởi COEP/CORP.
- Từ chối cookie third-party khiến iframe mất phiên.

Vì vậy MockMvc chỉ là **lớp kiểm tra hợp đồng response**, không phải toàn bộ kiểm chứng chức năng.

## 16. WebTestClient: kiểm tra tương đương cho Reactive

```java
webTestClient.mutateWith(mockUser("learner"))
    .get().uri("/isolated/simulator")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Cross-Origin-Opener-Policy", "same-origin")
    .expectHeader().valueEquals(
        "Cross-Origin-Embedder-Policy", "require-corp");

webTestClient.get().uri("/auth/popup-launcher")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    .expectHeader().doesNotExist(
        "Cross-Origin-Embedder-Policy");

webTestClient.mutateWith(mockUser("learner"))
    .get().uri("/courses/42")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()");
```

`mockUser` có thể được import từ `SecurityMockServerConfigurers` của `spring-security-test`. Khi response thực tế là redirect đăng nhập, lỗi hoặc URL không có handler, test phải phản ánh chính xác flow thay vì cưỡng ép `200 OK`.

**Không chạy cả ví dụ Servlet và Reactive trong cùng một ứng dụng chỉ vì muốn tăng coverage.** Dùng cấu hình khớp kiến trúc, cùng với browser E2E và các test nghiệp vụ.

## 17. Playwright: kiểm thử ba engine và đường fallback

Playwright có thể chạy kiểm thử browser trên **Chromium, Firefox và WebKit**. Đây là công cụ tốt cho regression nhưng **không thay** kiểm thử Safari/iOS thực tế khi sản phẩm cam kết hỗ trợ các môi trường đó.

### 17.1. Cấu hình projects

Ví dụ `playwright.config.ts` trong **dự án thử nghiệm riêng do người học quản lý**:

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://localhost:8080",
    trace: "retain-on-failure"
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } }
  ]
});
```

Tên `Desktop Safari` ở đây chọn **profile thiết bị/browser WebKit do Playwright cung cấp**, không chứng minh đây là bản Safari phát hành trên mọi OS. Cần ghi **Playwright version, browser binaries/version và CI image** khi tổng hợp kết quả.

### 17.2. E2E khẳng định app chọn mode đúng theo năng lực

Giả sử trang `/isolated/simulator` đặt `#engine-mode` thành `parallel` hoặc `basic` theo ví dụ phát hiện năng lực ở mục 6:

```typescript
import { test, expect } from "@playwright/test";

test("chọn engine đúng theo năng lực thực", async ({ page }) => {
  await page.goto("/isolated/simulator");

  const cap = await page.evaluate(() => {
    const secure = window.isSecureContext === true;
    const isolated = window.crossOriginIsolated === true;
    const sab = typeof SharedArrayBuffer === "function";
    const worker = typeof Worker === "function";

    return { secure, isolated, sab, worker };
  });

  const expectedMode =
    cap.secure && cap.isolated && cap.sab && cap.worker
      ? "parallel"
      : "basic";

  await expect(page.locator("#engine-mode")).toHaveText(expectedMode);
});
```

Test này chỉ xác minh **chọn mode nhất quán với capability**; nó **chưa chứng minh** cấu hình isolation ở staging đã đúng hoặc cả hai thuật toán cho kết quả tương đương.

### 17.3. Thêm test ràng buộc cho môi trường phải có isolation

Nếu hợp đồng của môi trường staging tuyên bố một browser cụ thể bắt buộc có isolation, viết test riêng:

```typescript
test("môi trường isolated trả đúng response policy", async ({ page }) => {
  const response = await page.goto("/isolated/simulator");
  expect(response).not.toBeNull();
  expect(response!.headers()["cross-origin-opener-policy"])
    .toBe("same-origin");
  expect(response!.headers()["cross-origin-embedder-policy"])
    .toBe("require-corp");
});
```

Nếu browser và môi trường test **được cam kết hỗ trợ isolation**, còn phải có assertion `crossOriginIsolated === true` trong test cùng ngữ cảnh; khi không đạt, test phải **FAIL**, không âm thầm coi fallback basic là đủ. Với browser **không cam kết** tính năng nâng cao, test lại phải xác minh fallback an toàn.

**Tránh test “nếu thiếu feature thì skip” toàn bộ**: skip khiến nhánh fallback không được kiểm tra và có thể che một lỗi cấu hình. Ghi rõ lý do một browser không thuộc tập hỗ trợ, nhưng vẫn test UI suy giảm tương ứng.

### 17.4. Kiểm thử trường hợp bắt buộc fallback

Để thử fallback mà không phụ thuộc một phiên bản browser cũ khó quản lý, ứng dụng thử nghiệm có thể có **feature flag chỉ trong môi trường test** ép chọn basic mode:

```typescript
test("basic mode vẫn hoàn thành bài mô phỏng", async ({ page }) => {
  await page.goto("/isolated/simulator?testMode=basic");
  await expect(page.locator("#engine-mode")).toHaveText("basic");

  await page.locator("#run").click();
  await expect(page.locator("#simulation-result"))
    .toContainText("Hoàn thành");
});
```

**Cảnh báo:** `testMode=basic` chỉ là một ví dụ về interface test giả định, **không có sẵn trong Spring Security**. Nếu triển khai, tham số này chỉ được **giảm năng lực thuật toán**, không được thay đổi xác thực, quyền truy cập, chính sách headers hoặc bật tính năng cần isolation. Không để test flag vượt cơ chế bảo mật trong production.

Trong test thật, nên so sánh **kết quả nghiệp vụ/đầu ra** của basic và parallel mode, không chỉ thông điệp `Hoàn thành`.

## 18. Lab COEP/CORP/CORS: test có đối chứng dương và âm

Để kiểm thử tác động của security headers trên browser, tạo hai origin **do bạn sở hữu**:

- Trang A `http://localhost:8080/isolated/lab`.
- Server ảnh/API B `http://localhost:9090`.

Hai port khác nhau là **khác origin**. `localhost` thường được browser coi là potentially trustworthy cho nhiều API, nhưng **production phải kiểm thử HTTPS thật** và origin thực tế.

Trang A:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Cross-origin fallback lab</title></head>
<body>
  <img id="plain" src="http://localhost:9090/public/logo.png"
       alt="Ảnh no-cors">
  <img id="cors" src="http://localhost:9090/public/logo.png"
       crossorigin="anonymous" alt="Ảnh CORS">
  <button id="fetchApi" type="button">Gọi API</button>
  <pre id="result"></pre>
  <script>
    document.getElementById("fetchApi").addEventListener("click", async () => {
      const output = document.getElementById("result");
      try {
        const response = await fetch(
          "http://localhost:9090/api/public/catalog");
        if (!response.ok) throw new Error("HTTP " + response.status);
        output.textContent = JSON.stringify(await response.json());
      } catch {
        output.textContent = "Không lấy được dữ liệu API";
      }
    });
  </script>
</body>
</html>
```

Response của trang A:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Kịch bản:

| Trường hợp ở server B | `plain` (no-cors) | `cors` (cors) | `fetch` API |
| --- | --- | --- | --- |
| PNG và JSON hợp lệ nhưng thiếu CORP/CORS | Bị chặn theo COEP | Bị chặn CORS | Bị chặn CORS |
| PNG có `CORP: cross-origin`; không có ACAO | Có thể tải | Bị chặn CORS | Bị chặn CORS |
| PNG/API chỉ có ACAO hợp lệ | Bị chặn theo COEP nếu `plain` vẫn no-cors | Có thể tải | Có thể đọc JSON |
| PNG có CORP và ACAO; API có ACAO | Có thể tải | Có thể tải | Có thể đọc JSON |

**Bằng chứng âm tính phải có đối chứng dương:**

1. Xác nhận server B đang chạy và URL ảnh trả **PNG hợp lệ**, không phải `404`.
2. Ghi `Content-Type`, HTTP status và **response headers thực** của ảnh và API.
3. Kiểm tra **Network/Console** để phân biệt COEP, CORP, CORS, CSP và lỗi mạng.
4. Chạy ít nhất một biến thể **cho phép tải thành công** cùng tài nguyên, tránh kết luận từ UI trắng.
5. Không coi `curl` là browser: curl không áp CORS/COEP/CORP như trình duyệt.

### Credentialless là một nhánh test riêng

Nếu dùng `COEP: credentialless` trên browser hỗ trợ, kiểm tra tình huống public `no-cors` asset **không gửi credentials** và xem nó có tải được không. Với tài nguyên cần cookie, có thể trả dữ liệu khác hoặc bị từ chối. Request `cors` vẫn cần CORS; `credentialless` không được dùng như đường vượt CORP hạn chế tường minh.

## 19. Kiểm thử popup, iframe và quyền thiết bị theo kết quả quan sát

### 19.1. Popup OAuth

Ở trang A `http://localhost:8080/auth/popup-launcher`, tạo nút `window.open("http://localhost:9090/popup.html")` theo thao tác click người dùng. Popup B in `window.opener === null`.

| COOP của A | COOP của B | Kỳ vọng |
| --- | --- | --- |
| `same-origin` | `unsafe-none` | Có thể bị tách opener. |
| `same-origin-allow-popups` | `unsafe-none` | Có thể giữ opener khi policy tương thích. |
| `same-origin-allow-popups` | `same-origin` | Không được mặc định giữ opener; B có thể buộc tách. |

Đảm bảo popup thực sự mở, response B đúng và không bị `noopener`. `window.open()` trả `null` không tự chứng minh COOP. Với OAuth thật, kiểm tra redirect và callback cuối, `state`/PKCE, phiên và quyền server.

### 19.2. Iframe

Test riêng:

1. Iframe có **được render**? Nếu không, xem CSP `frame-src` của cha, `frame-ancestors`/XFO của con.
2. Iframe có **tải script/ảnh/font**? Nếu không, xem COEP/CORP/CORS/CSP và redirect.
3. Iframe có **dùng camera/mic**? Nếu không, xem Permissions-Policy của cha/con, `allow`, HTTPS, permission user và OS.

Một iframe trắng vì XFO không phải bằng chứng `Permissions-Policy` chặn microphone. Một microphone từ chối do user không phải bằng chứng COEP sai.

### 19.3. Không tự bật thiết bị thật trong CI

CI nên kiểm tra header, policy introspection (nếu được hỗ trợ) và fallback UI. Nếu muốn test media flow sâu hơn, dùng **thiết bị media giả/cấu hình browser test** trong môi trường cô lập, có kiểm soát; tránh phụ thuộc phần cứng thật hoặc xin permission trên máy người dùng ngoài ý định.

## 20. Kiểm thử accessibility, trải nghiệm và tính đúng của fallback

Graceful degradation không chỉ là **không crash**. Một hệ thống suy giảm đúng phải cho người dùng biết tính năng nào không có và vẫn hoàn thành mục tiêu chính nếu có đường thay thế.

| Trường hợp | Tiêu chí UX và accessibility |
| --- | --- |
| Parallel engine không khả dụng | Thông báo basic mode bằng text; kết quả mô phỏng vẫn đúng, không chỉ đổi nhãn. |
| Video không được cấp phép | Nêu quyền cần thiết, có nút thử lại **do người dùng kích hoạt**; cung cấp chat/view-only nếu có. |
| Popup OAuth không hoạt động | Có nút redirect login, không vòng lặp popup; giữ trạng thái đăng nhập rõ ràng. |
| Biểu đồ CDN lỗi | Có tiêu đề/alt text, bảng dữ liệu hoặc thông báo thiếu dữ liệu, không ra quyết định dựa trên biểu đồ rỗng. |
| Iframe không hỗ trợ | Có link mở dịch vụ hợp lệ ở tab mới nếu nhà cung cấp cho phép; nêu yêu cầu trình duyệt/phiên. |
| Browser không được hỗ trợ | Thông báo tương thích dễ hiểu, không đổ lỗi chung chung cho người dùng. |

Kiểm tra keyboard navigation, focus sau popup/login, screen reader thông báo bằng vùng `aria-live` khi nội dung thay đổi, và việc tải lại trang không làm mất dữ liệu người dùng đang nhập.

**Một fallback sai có thể nguy hiểm hơn lỗi hiển thị:** ví dụ kết quả mô phỏng thiếu một bước quan trọng mà UI vẫn ghi “thành công”, hoặc đăng nhập được gắn nhãn thành công trước khi server xác thực phiên.

## 21. Telemetry, phát hành theo giai đoạn và rollback hẹp

### 21.1. Thu thập tín hiệu mà không làm lộ dữ liệu

Những thông số có thể hữu ích:

- Browser engine/version, OS, route **ở mức tổng hợp**.
- `crossOriginIsolated`, `isSecureContext`, `SharedArrayBuffer` có sẵn hay không.
- Số lượt chọn **basic/parallel mode**, lỗi tài nguyên bởi COEP/CORP/CORS/CSP.
- Số lượt popup không mở được, callback lỗi và chuyển sang redirect.
- Tỷ lệ iframe render thành công, media permission bị từ chối **không kèm nội dung âm thanh/hình ảnh**.
- Tỷ lệ fallback thành công/thất bại theo browser, phiên bản và release.

**Không ghi token OAuth, cookie, mã xác thực, thông tin camera/microphone hay URL có query nhạy cảm** vào telemetry. Khi báo cáo tham số URL, cần loại bỏ hoặc giảm dữ liệu có thể nhận diện người dùng.

### 21.2. Report-Only hỗ trợ nhưng không thay browser test

Trong một số browser, có các header theo dõi như:

```http
Cross-Origin-Embedder-Policy-Report-Only: require-corp
```

COEP Report-Only **không tương đương** với enforced COEP, và báo cáo còn phụ thuộc Reporting API, endpoint, browser support và cấu hình. CSP cũng có cơ chế Report-Only riêng cho những policy thích hợp.

Không coi “không có report” là “không có vi phạm”: có thể browser không hỗ trợ reporting, endpoint lỗi hoặc mẫu sử dụng chưa đi qua tài nguyên bị ảnh hưởng.

### 21.3. Quy trình rollout

1. **Chốt tập browser hỗ trợ:** nêu cụ thể engine/version tối thiểu và môi trường mobile, không dùng giả định chung “browser hiện đại”.
2. **Lập inventory route + dependency:** popup, iframe, CDN, API, worker, font, camera/mic, redirect và cookie.
3. **Định nghĩa hợp đồng fallback:** chỗ nào basic mode hợp lệ, chỗ nào phải chặn và thông báo.
4. **Viết HTTP regression:** header ở đúng response và chain, không trùng, không vô hiệu hóa các default headers.
5. **Thử browser matrix:** Chromium/Firefox/WebKit và Safari/device thật nếu nằm trong phạm vi sản phẩm; có ca dương/âm.
6. **Theo dõi policy trước khi enforce** nếu browser hỗ trợ và phù hợp, nhưng vẫn thử staging với enforced header.
7. **Canary theo route/nhóm người dùng** khi có hạ tầng hỗ trợ; theo dõi lỗi chức năng và dữ liệu.
8. **Rollback đúng phạm vi:** sửa `/isolated/**` hoặc resource CDN có lỗi, không tắt toàn bộ COOP/COEP/CSP/HSTS toàn site.
9. **Khóa kết quả theo phiên bản** và chạy lại khi nâng cấp Spring Security, browser hoặc SDK bên thứ ba.

### Quy tắc rollback

Nếu một CDN chưa đáp ứng COEP `require-corp`:

- Có thể bổ sung **CORP hợp lệ trên public asset** hoặc chuyển request sang **CORS mode** có CORS phù hợp.
- Nếu không thể, tạm đưa **trang không cần isolation** về chính sách cũ ở đúng scope sau phê duyệt.
- Nếu **tính năng bắt buộc có isolation**, không rollback bằng cách bỏ COEP rồi vẫn bật tính năng đó; hãy tắt **tính năng nâng cao** và dùng fallback an toàn hoặc thông báo không hỗ trợ.

## 22. Những anti-pattern thường gặp

### “Header đúng thì browser nào cũng bảo vệ như nhau”

Sai. Header phải được browser hỗ trợ, đúng ngữ cảnh và đúng response. Chẳng hạn `X-Permitted-Cross-Domain-Policies` không thay CORS hiện đại; một Permissions-Policy directive có thể chưa được mọi browser implement.

### “Thấy `window.crossOriginIsolated === false` thì bật thêm CORP trên mọi URL”

Sai. Cần kiểm tra COOP/COEP, secure context, browser, frame/ancestor, capability và tài nguyên cụ thể. `CORP: cross-origin` trên dữ liệu private còn có thể mở bề mặt nhúng không cần thiết.

### “Có CORS lỗi thì đổi `fetch` thành `mode: no-cors`”

Sai. Response thường opaque; JavaScript không đọc được JSON. Phải cấu hình CORS đúng ở API và giữ xác thực/authorization/CSRF.

### “Widget không có camera thì vô hiệu hóa Permissions-Policy”

Sai. Xác minh iframe có được render, origin có trong allowlist, `allow` đúng, secure context, user/OS permission và thiết bị. Mở camera toàn site không phải giải pháp.

### “Popup hỏng thì đặt `COOP: unsafe-none` cho mọi trang”

Không phù hợp. Tách trang opener hoặc bỏ phụ thuộc `window.opener`; các trang có nhu cầu isolation vẫn nên giữ chính sách phù hợp.

### “CI bỏ qua browser không hỗ trợ nên tất cả test PASS”

Một báo cáo toàn `skip` không chứng minh fallback. Test ít nhất đường **basic mode và thông báo suy giảm**, đồng thời đặt test fail khi một browser trong tập bắt buộc không đạt capability đã cam kết.

### “Ảnh không hiện tức CORP đã chặn”

Có thể là `404`, `401`, MIME, CSP, mixed content, redirect, CORS hoặc mạng lỗi. Muốn chứng minh enforcement cần **resource hợp lệ, response headers và ca đối chứng tải thành công**.

### “WebKit trong Playwright chính là Safari iOS”

Không chính xác. Playwright WebKit hữu ích cho kiểm thử engine, nhưng môi trường Safari thật, phiên bản OS và các quy tắc permission/cookie trên iOS có thể khác; thêm kiểm thử thiết bị khi phạm vi sản phẩm yêu cầu.

## 23. Bài tập tình huống

**Bài A — Browser không có isolation.** Trang mô phỏng chỉ có thể dùng `SharedArrayBuffer` ở môi trường cô lập. Hãy viết điều kiện feature detection và mô tả fallback basic mode. Khi nào cần fail closed thay vì fallback?

**Bài B — Browser matrix.** Nhóm phát triển chỉ thử trên một Chrome desktop. Hãy thiết kế ma trận có Chromium, Firefox, WebKit và Safari/iOS, thêm biến top-level/iframe, HTTPS và private browsing. Nêu bằng chứng cần lưu cho mỗi ô test.

**Bài C — Camera và policy introspection.** Trình duyệt trả `document.permissionsPolicy === undefined`. Có được kết luận camera bị chặn không? Nếu tính năng video là tùy chọn, cần cung cấp đường giảm cấp nào mà không bật thiết bị ngoài ý muốn?

**Bài D — OAuth popup.** Sau khi bật COOP `same-origin`, popup vẫn mở nhưng callback không tìm thấy `window.opener`. Phân biệt lỗi popup blocker, COOP và `noopener`. Đề xuất hai phương án giữ khả năng đăng nhập mà không bỏ `state`/PKCE.

**Bài E — COEP/CORP/CORS.** Trang isolated tải ảnh `<img src="...">` từ CDN chỉ có ACAO, không có CORP. Giải thích vì sao ảnh `no-cors` có thể bị chặn và đề xuất cách sửa ở đúng response hoặc request mode.

**Bài F — CI false positive.** Một test assert `naturalWidth === 0` rồi kết luận CORP đang hoạt động. Hãy bổ sung bằng chứng HTTP/Console và ca dương tính để tránh lỗi URL/404 gây PASS giả.

**Bài G — Hạ tầng.** MockMvc khẳng định `COEP: require-corp` tại `/isolated/**`, nhưng production còn thấy header này trên trang popup OAuth. Hãy kiểm tra chain, proxy/CDN, cache, redirect và đưa ra rollback hẹp.

**Bài H — Fail-closed security.** Một browser không hỗ trợ Permissions-Policy directive cần thiết cho một workflow nhạy cảm. Có thể coi CORS hay CSP đã thay thế chính sách đó không? Hãy xác định khi nào phải hạn chế workflow và những kiểm tra server nào không được nới lỏng.

**Bài I — Referrer privacy.** Một browser cũ không tuân theo `strict-origin-when-cross-origin` như kỳ vọng. Bạn sẽ kiểm tra `Referer` bằng cách nào, sửa thiết kế URL ra sao và dùng `rel="noreferrer"` trong trường hợp nào?

### Gợi ý lời giải

- **A:** kiểm tra `isSecureContext`, `crossOriginIsolated`, `SharedArrayBuffer` và API phụ trợ; fallback bằng thuật toán riêng đúng kết quả hoặc fail closed khi tính năng bắt buộc isolation.
- **B:** kiểm thử theo engine/version/OS, HTTP headers, popup, iframe, resource requests và khả năng suy giảm; Safari thực tế cần kiểm chứng riêng.
- **C:** `undefined` chỉ là **không xác định bằng API đó**; có thể dùng kênh chat/view-only, yêu cầu user consent khi cần media.
- **D:** COOP điều khiển BCG; `noopener` là lựa chọn khi mở; popup blocker chặn trước; cân nhắc redirect hoặc completion qua backend.
- **E:** ảnh `no-cors` dưới `require-corp` cần CORP phù hợp trên **response ảnh**, hoặc `crossorigin` và CORS hợp lệ.
- **F:** xác minh resource tồn tại/PNG hợp lệ, status, header, Console và một kịch bản được phép tải.
- **G:** MockMvc không thấy proxy; kiểm tra response cuối và sửa policy ở đúng route/tầng, không tắt header bảo vệ hàng loạt.
- **H:** bảo vệ phía browser không tương đương nhau; authorization, CSRF, session vẫn bắt buộc, workflow có thể phải ngừng hỗ trợ trong môi trường không đạt.
- **I:** dùng endpoint do bạn kiểm soát để quan sát `Referer` của navigation thật; không đặt secrets trong URL; dùng `noreferrer` khi cần.

## 24. Checklist vận hành trước khi phát hành

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Browser support có căn cứ không? | Danh sách engine/version/OS và kết quả test thật, không chỉ User-Agent suy đoán. |
| Header đặt đúng response? | COOP/COEP ở tài liệu; CORP ở resource; CORS ở API/resource đích. |
| HTTP tests có bảo vệ scope? | MockMvc/WebTestClient assert header đúng route, vắng mặt nơi không áp, default headers còn nguyên. |
| Browser test có đo behavior? | Popup opener, iframe, `crossOriginIsolated`, camera policy, resource load và API CORS. |
| Có test fallback? | Basic engine, redirect OAuth, UI không camera, dữ liệu dự phòng hoạt động theo hợp đồng. |
| Có kiểm tra tính đúng? | Kết quả basic mode/parallel mode và trạng thái đăng nhập được backend xác minh. |
| Có fail-closed ở chỗ bắt buộc? | Không sử dụng tính năng nhạy cảm khi thiếu isolation hoặc quyền cần thiết. |
| Có phân biệt nguyên nhân lỗi? | Ca âm tính có chứng cứ Network/Console và ca dương tính đối chứng. |
| Có coverage trên mobile/Safari nếu cần? | Đã thử trên thiết bị/browser thực sự nằm trong phạm vi hỗ trợ. |
| Proxy/CDN có nhất quán? | Response cuối không có header mâu thuẫn, cache/redirect không phát sai policy. |
| Không rò dữ liệu qua telemetry? | Không log token, cookie, URL/query nhạy cảm hoặc nội dung media. |
| Có kế hoạch rollback? | Giới hạn theo route/feature, không tắt CSRF/CSP/HSTS/authorization toàn hệ thống. |

## 25. Kết luận

**Khả năng hỗ trợ trình duyệt và suy giảm chức năng là hai phần bắt buộc của thiết kế security headers, không phải bước kiểm tra phụ sau khi deploy.** Một response có COOP, COEP, CORP, Permissions-Policy, Referrer-Policy hoặc CORS đúng cú pháp mới chỉ chứng minh server **đã gửi chính sách**; cần kiểm tra browser có hiểu, có thực thi theo đúng ngữ cảnh và ứng dụng có hành vi an toàn khi điều kiện không đạt.

Với **Spring Security Servlet và Reactive/WebFlux**, cách làm bền vững là **phát header theo đúng route/response → kiểm tra qua MockMvc/WebTestClient → thử trên browser engine/version mục tiêu → phát hiện năng lực thay vì đoán User-Agent → kiểm thử fallback và fail closed → quan sát sản xuất và rollback hẹp**.

Ở bất cứ mức hỗ trợ nào, **không hạ xác thực, phân quyền, CSRF, session và yêu cầu bảo mật dữ liệu chỉ để một popup, iframe hoặc thư viện CDN chạy được**. Chức năng có thể giảm từ parallel sang basic, video sang chat, biểu đồ tương tác sang bảng dữ liệu; nhưng quyền truy cập và tính đúng của nghiệp vụ phải được giữ nguyên.

### Tài liệu đối chiếu khi triển khai và bảo trì

- [MDN — Browser compatibility tables](https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Page_structures/Compatibility_tables): cách đọc và đối chiếu dữ liệu tương thích theo browser/phiên bản.
- [MDN — Cross-Origin-Opener-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy): COOP, popup và browsing context groups.
- [MDN — Cross-Origin-Embedder-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy): `require-corp`, `credentialless` và điều kiện nhúng.
- [MDN — Cross-Origin-Resource-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Resource-Policy): phạm vi sử dụng tài nguyên `no-cors`.
- [MDN — Permissions-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy): các directive, cú pháp và khả năng hỗ trợ.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): hành vi gửi `Referer` theo policy.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): request mode, preflight và credentials.
- [MDN — Window.crossOriginIsolated](https://developer.mozilla.org/en-US/docs/Web/API/Window/crossOriginIsolated): xác nhận trạng thái isolation trong context đang chạy.
- [Playwright — Projects](https://playwright.dev/docs/test-projects): chạy cùng bộ test trên nhiều browser engine/profile.
- [Spring Security — Servlet HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cấu hình security headers cho Servlet.
- [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): cấu hình tương ứng với WebFlux.
