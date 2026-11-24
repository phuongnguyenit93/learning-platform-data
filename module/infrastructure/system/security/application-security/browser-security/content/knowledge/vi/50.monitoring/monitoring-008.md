# Client security telemetry

## Mục tiêu

Client security telemetry là dữ liệu quan sát được thu thập từ trình duyệt để giúp đội vận hành nhận biết lỗi cấu hình bảo mật, hành vi bị chính sách trình duyệt chặn và dấu hiệu bất thường trong ứng dụng web. Những tín hiệu này bổ sung cho log máy chủ, CDN, WAF và hệ thống giám sát tập trung.

Trong phạm vi bảo mật trình duyệt, telemetry thường tập trung vào các cơ chế như Content Security Policy (CSP), Trusted Types, tải tài nguyên, trạng thái phiên và kết quả của các thao tác bảo mật do ứng dụng thực hiện. Dữ liệu từ trình duyệt có giới hạn về độ tin cậy và có thể chứa thông tin nhạy cảm nếu thu thập thiếu kiểm soát.

Sau bài này, bạn có thể:

- Xác định những tín hiệu bảo mật nào có thể thu thập từ trình duyệt và giới hạn của từng tín hiệu.
- Cấu hình CSP Reporting và lắng nghe sự kiện vi phạm CSP.
- Thiết kế schema telemetry có giới hạn dữ liệu, có thể lọc, tổng hợp và đối chiếu với log máy chủ.
- Kiểm thử việc gửi, tiếp nhận, xác thực cấu trúc, giới hạn tốc độ và cảnh báo telemetry.
- Đánh giá dấu hiệu bất thường mà không xem dữ liệu do client gửi là bằng chứng xác thực tuyệt đối.

## 1. Vai trò và giới hạn của telemetry phía client

Trình duyệt thực thi nhiều chính sách bảo mật trước khi mã ứng dụng có thể tiếp tục hoạt động. Ví dụ, CSP có thể chặn script không được phép, Trusted Types có thể chặn chuỗi không an toàn đi vào một số DOM sink, và Same-Origin Policy giới hạn việc đọc dữ liệu giữa các origin. Các lần chặn này có thể tạo tín hiệu hữu ích để phát hiện cấu hình sai hoặc một luồng dữ liệu bất thường.

Telemetry phía client trả lời các câu hỏi như:

- Một bản phát hành mới có làm tăng số lần vi phạm `script-src` không?
- Trang nào đang tạo ra vi phạm `require-trusted-types-for`?
- Một tài nguyên hợp lệ có bị CSP chặn do cấu hình thiếu nguồn không?
- Tỷ lệ request bị từ chối do phiên hết hạn hoặc quyền truy cập thay đổi có tăng bất thường không?
- Service Worker hoặc mã giao diện có đang phát ra lỗi bảo mật sau khi triển khai phiên bản mới không?

Telemetry không thay thế cơ chế phòng vệ. CSP vẫn phải được cấu hình để trình duyệt thực thi chính sách; báo cáo CSP chỉ giúp quan sát các lần vi phạm. Tương tự, việc ghi nhận một request bị từ chối không thay thế việc kiểm tra quyền ở máy chủ.

Dữ liệu từ client cũng không phải nguồn sự thật tuyệt đối. Người dùng có thể tắt JavaScript, dùng tiện ích chặn request, sửa mã chạy trong trang hoặc gửi trực tiếp một POST giả đến endpoint telemetry. Trình duyệt và mạng có thể trì hoãn, gộp hoặc bỏ mất báo cáo. Vì vậy:

- Dùng telemetry client để phát hiện xu hướng, xác định khu vực cần điều tra và bổ sung ngữ cảnh.
- Đối chiếu với log máy chủ, CDN, WAF và sự kiện xác thực trước khi kết luận.
- Không dùng một báo cáo client đơn lẻ làm căn cứ duy nhất để khóa tài khoản, chặn địa chỉ IP hoặc cấp quyền.
- Không đưa quyết định phân quyền, xác thực hay chống gian lận quan trọng vào mã JavaScript chạy trên thiết bị người dùng.

## 2. Các nguồn tín hiệu bảo mật trong trình duyệt

| Nguồn tín hiệu | Dữ liệu có thể quan sát | Giới hạn cần hiểu |
|---|---|---|
| CSP Reporting | Directive bị vi phạm, chế độ enforce/report-only, tài nguyên bị chặn ở mức thông tin mà trình duyệt cung cấp, vị trí nguồn trong một số trường hợp | Báo cáo có thể bị giả mạo, thiếu hoặc bị gộp; URL và source sample có thể chứa dữ liệu nhạy cảm |
| Sự kiện `securitypolicyviolation` | Vi phạm CSP phát sinh trong tài liệu đang chạy | Chỉ ghi nhận các sự kiện mà trình duyệt phát ra và mã trang còn hoạt động để nhận; không bao phủ mọi lỗi mạng |
| Trusted Types | Vi phạm CSP liên quan đến sink yêu cầu Trusted Types | Hỗ trợ phụ thuộc trình duyệt; sự kiện vẫn cần được diễn giải cùng directive và phiên bản ứng dụng |
| Kết quả API của ứng dụng | HTTP status như 401, 403, 429; trạng thái đăng xuất; lỗi xác thực token do máy chủ trả | Không ghi token, body hoặc dữ liệu người dùng; một số lỗi mạng/CORS không cung cấp status cho JavaScript |
| Resource loading và runtime | Lỗi tải script, stylesheet hoặc tài nguyên; lỗi JavaScript không xử lý | Không thể kết luận nguyên nhân là tấn công chỉ từ một sự kiện `error`; thông tin có thể bị trình duyệt che hoặc rút gọn |
| Service Worker | Phiên bản worker, lỗi cập nhật, trạng thái điều khiển trang và lỗi trong luồng cache do ứng dụng ghi nhận | Worker có thể bị tắt, bị lỗi hoặc chưa điều khiển trang; dữ liệu quan sát không đại diện toàn bộ client |
| Server và edge logs | Quyết định xác thực, phân quyền, CSRF, rate limit, WAF, trạng thái upstream và cache | Đây không phải telemetry thuần client, nhưng là nguồn đối chiếu quan trọng để xác minh tín hiệu |

Một số giới hạn cần nhớ khi diễn giải:

- JavaScript không thể đọc tùy ý response header của mọi request. Với request cross-origin, header chỉ đọc được khi máy chủ cho phép bằng CORS và khai báo header cần expose. Không suy ra chính sách bảo mật của response từ những header mà trang không thể quan sát.
- Khi `fetch()` gặp lỗi CORS hoặc một số lỗi mạng, mã trang thường chỉ nhận lỗi chung như `TypeError`; không thể luôn phân biệt CORS, DNS, TLS, extension chặn request hay kết nối bị ngắt.
- Trình duyệt không cung cấp một sự kiện JavaScript tổng quát cho mọi quyết định nội bộ của bộ máy bảo mật. Dùng báo cáo chuyên biệt và log phía máy chủ thay vì suy diễn từ lỗi giao diện.
- Một người dùng có thể có nhiều tab, nhiều thiết bị hoặc nhiều phiên. Không coi một mã phiên client là danh tính người dùng đã được xác minh.

## 3. CSP Reporting

CSP có thể chạy ở chế độ thực thi hoặc chế độ chỉ báo cáo. Khi chính sách thực thi chặn một hành vi, trình duyệt có thể gửi báo cáo đến endpoint được cấu hình. Chế độ report-only cho phép quan sát vi phạm mà chưa chặn hành vi; chế độ này hữu ích khi triển khai chính sách mới và đánh giá ảnh hưởng trước khi enforce.

### 3.1. Khai báo endpoint báo cáo

Ví dụ cấu hình header cho một ứng dụng thử nghiệm:

```http
Reporting-Endpoints: csp="https://telemetry.example.test/reports/csp"
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; frame-ancestors 'none'; report-to csp; report-uri /reports/csp
```

Trong ví dụ:

- `Reporting-Endpoints` khai báo nhóm endpoint có tên `csp`.
- `report-to csp` liên kết chính sách CSP với nhóm báo cáo đó.
- `report-uri` được giữ làm phương án tương thích cho các trình duyệt cũ hơn; đây là cơ chế cũ và không nên là lựa chọn duy nhất cho triển khai mới.
- Nonce phải được sinh ngẫu nhiên cho từng response và phải khớp giữa header CSP với thẻ script được phép. Chuỗi `{RANDOM_PER_RESPONSE}` chỉ là ký hiệu thay thế trong ví dụ.

Trong giai đoạn đánh giá, có thể dùng chính sách report-only:

```http
Reporting-Endpoints: csp="https://telemetry.example.test/reports/csp"
Content-Security-Policy-Report-Only: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self'; report-to csp; report-uri /reports/csp
```

Khi dùng report-only, hành vi vi phạm được báo cáo nhưng không bị chính sách đó chặn. Vì vậy, cần kiểm thử riêng cả hai chế độ: report-only để đánh giá tác động và enforce để xác nhận trình duyệt thực sự chặn hành vi ngoài chính sách. Hỗ trợ `report-to` và định dạng báo cáo có thể khác nhau theo trình duyệt; kiểm tra các trình duyệt mục tiêu của ứng dụng và giữ phương án tương thích cần thiết.

### 3.2. Đọc báo cáo CSP

Báo cáo CSP có thể cung cấp các trường như:

| Trường | Cách sử dụng |
|---|---|
| `effective-directive` / `effectiveDirective` | Directive có hiệu lực tại thời điểm vi phạm, ví dụ `script-src-elem` hoặc `style-src` |
| `violated-directive` / `violatedDirective` | Directive được báo cáo là bị vi phạm |
| `blocked-uri` / `blockedURL` | Thông tin về tài nguyên bị chặn; cần chuẩn hóa trước khi lưu |
| `document-uri` / `documentURL` | Trang phát sinh vi phạm; nên ánh xạ thành route template thay vì lưu nguyên URL |
| `disposition` | Chính sách đang ở chế độ `enforce` hay `report` |
| `source-file` / `sourceFile` | Nguồn được trình duyệt cung cấp trong một số trường hợp; có thể chứa đường dẫn nhạy cảm |
| `line-number`, `column-number` | Vị trí trong nguồn, hữu ích khi tìm lỗi ở bản phát hành cụ thể |
| `original-policy` | Chính sách liên quan đến báo cáo; cần giới hạn độ dài và chuẩn hóa |
| `sample` | Một phần nội dung có liên quan khi chính sách dùng `report-sample`; có thể chứa mã hoặc dữ liệu người dùng, không nên thu thập mặc định |

Trình duyệt mới có thể gửi báo cáo theo định dạng Reporting API với phần metadata và `body`; các trình duyệt hoặc cơ chế cũ có thể dùng định dạng khác. Endpoint phải xử lý định dạng đã bật trong hệ thống và không giả định mọi trường luôn tồn tại.

### 3.3. Lắng nghe sự kiện vi phạm CSP trong trang

Có thể bổ sung listener để ghi nhận tín hiệu ngay trong ứng dụng. Ví dụ dưới đây chỉ gửi các trường đã chuẩn hóa, không gửi nguyên URL, nội dung bị chặn hay source sample:

```javascript
function classifyBlockedResource(value) {
  if (!value) return "unknown";

  const normalized = value.toLowerCase();
  if (normalized === "inline" || normalized === "eval") {
    return normalized;
  }

  try {
    const blocked = new URL(value, window.location.href);
    return blocked.origin === window.location.origin
      ? "same-origin"
      : "cross-origin";
  } catch {
    return "other";
  }
}

document.addEventListener("securitypolicyviolation", (event) => {
  const telemetryEvent = {
    schemaVersion: 1,
    type: "csp_violation",
    effectiveDirective: event.effectiveDirective,
    disposition: event.disposition,
    blockedResourceClass: classifyBlockedResource(event.blockedURI),
    routeId: window.appTelemetryRouteId || "unknown",
    appVersion: window.appVersion || "unknown",
  };

  sendSecurityTelemetry(telemetryEvent);
});
```

`securitypolicyviolation` là sự kiện do trình duyệt phát ra khi phát hiện vi phạm CSP. Thuộc tính `blockedURI` có thể là giá trị đặc biệt như `inline` hoặc `eval`, hoặc một URL. Ví dụ chỉ lưu phân loại cùng origin/cross-origin để giảm dữ liệu thu thập. Nếu cần điều tra sâu hơn, có thể bổ sung trường đã được cho phép và lọc theo chính sách dữ liệu; không mặc định lưu toàn bộ URL.

Listener trong trang là một nguồn quan sát bổ sung. Không nên dựa vào listener thay cho CSP Reporting do trình duyệt quản lý, vì listener có thể không chạy nếu script bị chặn, trang đóng hoặc mã ứng dụng gặp lỗi trước đó.

### 3.4. Theo dõi Trusted Types

Trusted Types giúp giới hạn việc truyền chuỗi không đáng tin cậy vào các DOM sink nhạy cảm. Có thể bật yêu cầu qua CSP:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app; report-to csp; report-uri /reports/csp
```

Trong cấu hình này, ứng dụng chỉ cho phép policy có tên `app` tạo các giá trị Trusted Types theo thiết kế. Khi mã cố gắng đưa chuỗi thông thường vào sink được bảo vệ, trình duyệt có thể chặn thao tác và phát báo cáo CSP tương ứng.

Khi triển khai, cần:

1. Dùng report-only hoặc môi trường staging để tìm các sink còn nhận chuỗi thông thường.
2. Xác định nguồn dữ liệu và nơi tạo HTML/script; sửa luồng xử lý để dùng Trusted Types phù hợp.
3. Giữ danh sách policy ở mức tối thiểu, kiểm tra nội dung policy và tránh tạo policy mặc định quá rộng.
4. Bật enforce sau khi đã xử lý các luồng hợp lệ.
5. Theo dõi báo cáo theo directive, route và phiên bản phát hành để phát hiện hồi quy.

Không coi mọi vi phạm Trusted Types là bằng chứng XSS thành công. Nó cho thấy một thao tác đã vi phạm ràng buộc; cần xem call path, dữ liệu đầu vào và kết quả thực tế để xác định nguyên nhân.

## 4. Thiết kế schema telemetry

Schema thống nhất giúp gom nhóm, loại bỏ trùng lặp và so sánh giữa các bản phát hành. Một event bảo mật phía client nên nhỏ, có phiên bản và chỉ chứa các trường thực sự cần cho điều tra.

Ví dụ schema ở mức khái niệm:

```json
{
  "schemaVersion": 1,
  "eventId": "random-event-id",
  "type": "csp_violation",
  "occurredAt": "2026-11-22T09:00:00.000Z",
  "appVersion": "web-2026.11.22.1",
  "environment": "production",
  "routeId": "account-profile",
  "effectiveDirective": "script-src-elem",
  "disposition": "enforce",
  "blockedResourceClass": "cross-origin",
  "correlationId": "short-lived-correlation-id"
}
```

Các trường nên cân nhắc:

- `schemaVersion`: cho phép thay đổi cấu trúc có kiểm soát.
- `eventId`: mã ngẫu nhiên để loại bỏ bản ghi trùng khi client gửi lại.
- `type`: loại sự kiện có danh sách cho phép, ví dụ `csp_violation`, `trusted_types_violation`, `auth_denied` hoặc `service_worker_update_error`.
- `occurredAt`: thời gian phía client ghi nhận; có thể sai lệch và không thay thế timestamp do máy chủ tiếp nhận.
- `appVersion` và `environment`: giúp gắn sự kiện với bản phát hành và môi trường.
- `routeId`: định danh route đã được ứng dụng định nghĩa, không phải URL tự do.
- Các trường riêng cho từng loại sự kiện: dùng enum hoặc giới hạn độ dài để tránh payload tùy ý.
- `correlationId`: mã tương quan ngắn hạn do máy chủ cấp hoặc cơ chế đáng tin cậy tạo, không dùng làm quyền truy cập.

Không phải mọi event đều cần mọi trường. Hãy xác định schema riêng cho từng loại sự kiện và từ chối trường lạ hoặc payload quá lớn ở phía máy chủ.

## 5. Giảm thiểu dữ liệu và bảo vệ quyền riêng tư

Telemetry bảo mật có thể vô tình thu thập dữ liệu nhạy cảm. URL có thể chứa email, mã đơn hàng hoặc token; stack trace có thể chứa tham số; thông báo lỗi có thể chứa nội dung form. Một báo cáo CSP có thể bao gồm đường dẫn tài nguyên hoặc source sample. Cần thiết kế lọc dữ liệu trước khi gửi và kiểm tra lại tại endpoint tiếp nhận.

**Không thu thập mặc định:**

- Cookie, session ID, access token, refresh token, authorization header hoặc CSRF token.
- Mật khẩu, nội dung form, dữ liệu thanh toán, nội dung chat hoặc dữ liệu cá nhân trong DOM.
- Toàn bộ query string, fragment hoặc URL có thể chứa mã định danh và token.
- Nội dung `sample` của CSP, HTML bị chặn, stack trace đầy đủ hoặc request/response body.
- Dấu vân tay thiết bị chi tiết, danh sách font, plugin, kích thước màn hình chính xác hoặc các thuộc tính không cần thiết để điều tra.

Ưu tiên:

- Route template hoặc route ID đã định nghĩa, ví dụ `account-profile` thay cho `/account/12345?token=...`.
- Phân loại tài nguyên như `same-origin`, `cross-origin`, `inline`, `eval` thay cho URL đầy đủ.
- Browser family và major version nếu thực sự cần phân nhóm lỗi tương thích.
- Mã tương quan ngắn hạn, được xoay vòng và không thể dùng để truy cập tài khoản.
- Thời gian lưu trữ ngắn theo mục đích, quyền truy cập hạn chế và nhật ký truy cập hệ thống telemetry.
- Sampling cho các event có tần suất cao, nhưng không bỏ qua hoàn toàn các tín hiệu có mức độ nghiêm trọng cao.

Lọc ở client giúp giảm dữ liệu trước khi truyền, nhưng không đủ để bảo đảm an toàn. Endpoint phải tiếp tục loại bỏ trường không được phép, chuẩn hóa URL và giới hạn kích thước. Nếu yêu cầu tuân thủ hoặc chính sách riêng tư cần thông báo/đồng ý, quy trình thu thập phải tuân theo quy định áp dụng cho sản phẩm và khu vực vận hành.

## 6. Gửi telemetry từ trình duyệt

Đối với event do ứng dụng tạo, có thể dùng `navigator.sendBeacon()` để gửi dữ liệu nhỏ khi trang sắp rời đi. API này được thiết kế cho việc gửi dữ liệu nền mà không giữ trang chờ response. Giá trị trả về `true` chỉ cho biết trình duyệt đã chấp nhận xếp dữ liệu vào hàng đợi gửi; nó không xác nhận máy chủ đã nhận hoặc lưu thành công.

Ví dụ gửi một event đã chuẩn hóa đến endpoint cùng origin:

```javascript
const SECURITY_TELEMETRY_ENDPOINT = "/_telemetry/security";

function sendSecurityTelemetry(event) {
  const payload = JSON.stringify({
    schemaVersion: 1,
    events: [event],
  });

  const body = new Blob([payload], {
    type: "application/json",
  });

  if (navigator.sendBeacon &&
      navigator.sendBeacon(SECURITY_TELEMETRY_ENDPOINT, body)) {
    return;
  }

  fetch(SECURITY_TELEMETRY_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: payload,
    credentials: "same-origin",
    keepalive: true,
  }).catch(() => {
    // Không làm gián đoạn thao tác chính nếu telemetry không gửi được.
  });
}
```

Trong triển khai thực tế, cần bổ sung hàng đợi có giới hạn, gộp event, sampling và xử lý lỗi. Không retry vô hạn vì điều đó có thể tạo vòng lặp gửi dữ liệu khi endpoint đang gặp sự cố. Tránh gửi telemetry trong mỗi lần render hoặc mỗi lần thay đổi DOM.

Endpoint cùng origin giúp đơn giản hóa CORS và giảm việc chia sẻ dữ liệu với bên thứ ba. Nếu dùng endpoint khác origin, phải xác định rõ chính sách CORS, credentials, quyền truy cập, lưu trữ và nhà cung cấp tiếp nhận.

## 7. Bảo vệ endpoint tiếp nhận

Endpoint telemetry là một bề mặt nhận dữ liệu công khai từ trình duyệt. Bất kỳ client nào cũng có thể gửi request giả, lặp lại hoặc tạo payload rất lớn. Máy chủ phải coi mọi trường do client gửi là dữ liệu không đáng tin cậy.

Các kiểm soát cần có:

1. **Xác thực cấu trúc:** chỉ chấp nhận content type và schema đã định nghĩa; từ chối JSON sai, trường lạ hoặc kiểu dữ liệu không hợp lệ.
2. **Giới hạn kích thước:** đặt giới hạn byte cho request và số event trong một batch.
3. **Giới hạn tốc độ:** rate limit theo các tín hiệu phù hợp ở edge; không phụ thuộc duy nhất vào IP vì nhiều người dùng có thể dùng chung NAT.
4. **Chống lạm dụng:** giới hạn độ dài chuỗi, số trường, tần suất và mức độ lặp; loại bỏ ký tự điều khiển không cần thiết trước khi ghi log.
5. **Kiểm soát nguồn:** ưu tiên endpoint cùng origin. CORS không phải cơ chế xác thực người gửi vì client ngoài trình duyệt vẫn có thể gửi HTTP request trực tiếp.
6. **Không thực thi nội dung:** không render HTML, không mở URL từ báo cáo, không chạy sample và không chèn dữ liệu telemetry vào câu lệnh truy vấn.
7. **Bảo vệ log:** escape dữ liệu khi hiển thị, chống log injection và giới hạn quyền truy cập dashboard.
8. **Quan sát endpoint:** theo dõi tỷ lệ 4xx/5xx, độ trễ, kích thước payload, số lượng bị rate limit và dung lượng lưu trữ.

Không yêu cầu người dùng gửi cookie phiên chỉ để chứng minh event telemetry là hợp lệ. Nếu cần liên kết sự kiện với phiên ứng dụng, dùng mã tương quan ngắn hạn do máy chủ cấp và đánh giá tác động quyền riêng tư. Endpoint vẫn phải chịu được các request giả mạo.

## 8. Phân tích và cảnh báo

Không nên cảnh báo theo từng event riêng lẻ nếu sự kiện có thể xảy ra thường xuyên trong hoạt động bình thường. Hãy nhóm theo ứng dụng, phiên bản, route, directive, browser family và khoảng thời gian.

| Tín hiệu | Cách phân tích | Hướng điều tra |
|---|---|---|
| Tăng `script-src` sau phát hành | So sánh tỷ lệ vi phạm theo phiên bản và route trước/sau deploy | Script mới, nonce không khớp, CDN cache HTML cũ hoặc dependency ngoài danh sách |
| Vi phạm `require-trusted-types-for` tập trung ở một route | Nhóm theo route và phiên bản | DOM sink còn nhận chuỗi, luồng nhập liệu mới hoặc policy Trusted Types quá hẹp |
| Nhiều `blocked-uri` từ cùng một domain | Dùng phân loại origin và đối chiếu danh sách nguồn hợp lệ | Cấu hình CSP thiếu domain cần thiết, dependency thay đổi hoặc request ngoài dự kiến |
| Tăng 401/403 ở API nhạy cảm | Đối chiếu client event với access log và auth log | Phiên hết hạn, thay đổi quyền, lỗi tích hợp hoặc hành vi dò endpoint |
| Lỗi cập nhật Service Worker tăng sau deploy | Nhóm theo phiên bản worker và browser family | File worker không tải được, lỗi cache version hoặc tài nguyên bị chặn |
| Lượng telemetry tăng đột biến | Đối chiếu số client, release, endpoint và rate limit | Vòng lặp gửi event, cấu hình sai, bot gửi giả hoặc một thay đổi tạo nhiều vi phạm |

Một cảnh báo hữu ích cần có ngưỡng và baseline. Ví dụ, cảnh báo khi tỷ lệ CSP enforce violation của `script-src` tăng đáng kể so với baseline của cùng route và phiên bản. Cần loại trừ các lần thử có chủ đích trong staging và kiểm tra việc sampling trước khi so sánh số lượng tuyệt đối.

Khi điều tra, hãy kết hợp:

- Telemetry phía client để biết trình duyệt quan sát điều gì.
- Log ứng dụng để xác định endpoint và quyết định xử lý.
- Log xác thực/phân quyền để xác minh trạng thái người dùng.
- Log CDN/WAF để biết request có được cache, chặn hoặc chuyển tiếp hay không.
- Metadata phát hành để liên kết thời điểm tăng bất thường với thay đổi code hoặc policy.

## 9. Quy trình kiểm thử telemetry

Thực hiện trong staging với tài khoản và dữ liệu giả. Không cố ý tạo lưu lượng lớn trên endpoint production.

### 9.1. Kiểm tra CSP report-only

1. Cấu hình một chính sách report-only có endpoint báo cáo.
2. Tạo trang thử nghiệm có một hành vi vi phạm đã kiểm soát, chẳng hạn script inline không có nonce trong khi policy chỉ cho phép nguồn hợp lệ.
3. Tải trang bằng các trình duyệt được hỗ trợ.
4. Kiểm tra endpoint nhận được báo cáo, trường directive và disposition phù hợp.
5. Xác nhận trang vẫn thực thi hành vi bị vi phạm trong chế độ report-only.

Kết quả đạt: báo cáo được tiếp nhận và phân loại đúng; chính sách report-only không chặn hành vi thử nghiệm. Không dùng payload XSS thật hoặc dữ liệu nhạy cảm để tạo vi phạm.

### 9.2. Kiểm tra CSP enforce

1. Chuyển chính sách thử nghiệm sang header enforce.
2. Lặp lại hành vi vi phạm đã kiểm soát.
3. Xác nhận trình duyệt chặn hành vi theo directive.
4. Kiểm tra báo cáo được gửi và có disposition là enforce nếu trình duyệt cung cấp trường này.
5. Xác nhận các script hợp lệ vẫn hoạt động.

Kết quả đạt: hành vi ngoài chính sách bị chặn và có tín hiệu quan sát; các luồng hợp lệ không bị chặn ngoài dự kiến.

### 9.3. Kiểm tra Trusted Types

Trong trang thử nghiệm có policy yêu cầu Trusted Types, thử gán một chuỗi thông thường vào sink được bảo vệ:

```javascript
const target = document.createElement("div");

try {
  target.innerHTML = "<b>test</b>";
} catch (error) {
  console.log("Trusted Types blocked the assignment");
}
```

Kết quả đạt: trình duyệt hỗ trợ Trusted Types từ chối thao tác không đáp ứng yêu cầu và báo cáo vi phạm nếu cơ chế báo cáo được cấu hình. Không đưa dữ liệu không tin cậy vào trang đang phục vụ người dùng thật để thử nghiệm.

### 9.4. Kiểm tra endpoint và độ bền

Gửi các request thử nghiệm với:

- JSON hợp lệ theo schema.
- JSON thiếu trường bắt buộc hoặc sai kiểu.
- Event type không nằm trong danh sách cho phép.
- Payload vượt giới hạn kích thước.
- Batch chứa quá nhiều event.
- Chuỗi dài bất thường hoặc có ký tự điều khiển.
- Event ID trùng lặp.
- Request không có Origin hoặc có Origin không mong đợi.

Kết quả đạt: endpoint chấp nhận dữ liệu hợp lệ, từ chối hoặc loại bỏ dữ liệu sai, áp dụng giới hạn tốc độ và không ghi nội dung độc hại như markup thực thi. Không xem header `Origin` là bằng chứng xác thực vì request ngoài trình duyệt có thể giả mạo hoặc bỏ header này.

### 9.5. Kiểm tra mất mạng và gửi lặp

1. Tắt mạng trong môi trường thử nghiệm, tạo một số event.
2. Quan sát hành vi khi endpoint không truy cập được.
3. Khôi phục mạng và xác định event nào được gửi, event nào bị bỏ.
4. Gửi lại cùng event ID để kiểm tra cơ chế loại trùng ở backend.
5. Đóng tab hoặc điều hướng nhanh để kiểm tra giới hạn thực tế của `sendBeacon`.

Kết quả đạt: lỗi telemetry không làm hỏng thao tác chính của ứng dụng; hàng đợi có giới hạn; backend xử lý event trùng theo chính sách; dashboard không đếm một sự kiện nhiều lần nếu event ID được dùng để loại trùng. Không giả định `sendBeacon` bảo đảm giao nhận.

## 10. Tình huống thực tế: CSP violation tăng sau bản phát hành

Sau một lần deploy, dashboard ghi nhận số vi phạm `script-src-elem` tăng mạnh ở trang thanh toán. Có thể phân tích theo thứ tự:

1. So sánh tỷ lệ vi phạm giữa phiên bản mới và phiên bản trước.
2. Kiểm tra route ID, browser family và disposition để xác định phạm vi ảnh hưởng.
3. Kiểm tra phân loại tài nguyên bị chặn; nếu là cross-origin, đối chiếu với danh sách script được phép của ứng dụng.
4. Kiểm tra thay đổi dependency, nonce, CSP header và HTML cache ở CDN.
5. Đối chiếu với log deploy và log CDN để xác định có trang HTML cũ đi cùng script mới hay không.
6. Sửa cấu hình hoặc bản phát hành, sau đó xác nhận tỷ lệ vi phạm trở về baseline.

Nếu event chỉ xuất hiện ở một browser family, cần tái hiện trên trình duyệt đó và kiểm tra khác biệt hỗ trợ CSP. Nếu báo cáo xuất hiện từ một nguồn bất thường nhưng không có request tương ứng trong log ứng dụng, hãy xem xét khả năng endpoint nhận report giả mạo.

## 11. Checklist triển khai

- [ ] Đã xác định mục tiêu và nguồn tín hiệu cần thu thập.
- [ ] Đã phân biệt CSP report-only với CSP enforce.
- [ ] Đã cấu hình Reporting endpoint và kiểm tra hỗ trợ của trình duyệt mục tiêu.
- [ ] Đã kiểm thử sự kiện `securitypolicyviolation` và Trusted Types nếu ứng dụng sử dụng.
- [ ] Schema có phiên bản, event type rõ ràng và giới hạn kích thước.
- [ ] URL, query string, token, cookie, form data và source sample được loại bỏ hoặc chuẩn hóa trước khi gửi.
- [ ] Endpoint kiểm tra schema, giới hạn tốc độ, chống payload quá lớn và chống log injection.
- [ ] Dashboard nhóm theo route, directive, browser family và phiên bản phát hành.
- [ ] Alert có baseline, ngưỡng và quy trình đối chiếu với log máy chủ.
- [ ] Đã kiểm thử mất mạng, gửi lặp và hành vi khi telemetry endpoint gặp lỗi.
- [ ] Đã quy định thời gian lưu trữ, quyền truy cập và mục đích sử dụng dữ liệu.

Client security telemetry giúp nhìn thấy những gì trình duyệt quan sát được trong quá trình thực thi chính sách bảo mật. Khi dữ liệu được giảm thiểu, xác thực cấu trúc, tổng hợp và đối chiếu với log phía máy chủ, đội vận hành có thể phát hiện hồi quy CSP, lỗi Trusted Types và bất thường trong luồng bảo mật sớm hơn mà vẫn kiểm soát được rủi ro riêng tư.
