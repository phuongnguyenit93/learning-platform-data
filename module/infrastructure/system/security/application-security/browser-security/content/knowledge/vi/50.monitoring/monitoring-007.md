# Browser error metric trong giám sát ứng dụng web

Browser error metric là chỉ số tổng hợp các lỗi mà người dùng gặp trong trình duyệt khi tải trang, chạy JavaScript, gọi API hoặc tải tài nguyên. Chỉ số này giúp nhóm vận hành biết lỗi xuất hiện ở route nào, trên nhóm trình duyệt nào, sau phiên bản phát hành nào và ảnh hưởng tới bao nhiêu lượt sử dụng.

Một API server có thể trả `200 OK` trong khi giao diện vẫn hỏng do JavaScript exception, CSP chặn script, CORS ngăn mã đọc response hoặc tài nguyên quan trọng không tải được. Ngược lại, một request trả `404` có thể là hành vi bình thường của một tính năng tùy chọn. Vì vậy, cần phân loại sự kiện và định nghĩa mẫu số rõ ràng trước khi dùng browser error metric làm tín hiệu vận hành.

Trong bảo mật ứng dụng trình duyệt, metric còn giúp phát hiện thay đổi bất thường sau khi triển khai CSP, Trusted Types, cookie policy, CORS, HSTS hoặc thay đổi luồng xác thực. Dữ liệu giám sát phải đủ để điều tra nhưng không được biến thành nơi lưu token, cookie, nội dung form hoặc dữ liệu cá nhân.

Sau bài học, bạn có thể:

- Phân loại JavaScript error, promise rejection, HTTP error, request failure và resource load failure.
- Định nghĩa numerator, denominator và đơn vị đo cho từng browser metric.
- Thu thập Real User Monitoring (RUM) từ trình duyệt với dữ liệu tối thiểu.
- Thiết kế dashboard theo route, browser, release và mức độ ảnh hưởng.
- Đặt SLI/SLO, ngưỡng cảnh báo và quy trình điều tra theo mức độ nghiêm trọng.
- Kiểm soát sampling, cardinality, quyền truy cập và thời hạn lưu telemetry.

## 1. Browser error metric đo điều gì?

Browser error metric phản ánh kết quả thực tế ở phía người dùng. Nó bổ sung cho log và metric phía server bằng cách quan sát những gì trình duyệt có thể nhìn thấy: JavaScript có chạy không, request có hoàn tất không, response có được phép đọc không và tài nguyên cần thiết có tải thành công không.

Các nhóm tín hiệu chính:

| Nhóm | Ví dụ | Nguồn quan sát |
|---|---|---|
| JavaScript runtime error | Exception không được xử lý trong script | `window` `error` event |
| Promise rejection | Promise bị reject nhưng không có handler phù hợp | `unhandledrejection` event |
| HTTP response error | API trả `4xx` hoặc `5xx` | Fetch/XHR client; Network diagnostics hỗ trợ điều tra |
| Request failure | DNS, TLS, CORS, offline, connection reset hoặc lỗi trình duyệt | Fetch/XHR rejection và browser diagnostics |
| Request cancellation | Điều hướng hoặc thao tác mới hủy request cũ | `AbortController`, ứng dụng và fetch wrapper |
| Resource load failure | Script, stylesheet, font, ảnh hoặc frame không tải được | Capturing `error` event và kiểm tra tài nguyên |
| Policy violation | CSP, Trusted Types hoặc một số chính sách nội dung từ chối hành vi | Browser Console và Reporting API |
| User-visible failure | Người dùng không hoàn tất được thao tác quan trọng | Business event hoặc luồng UI có định nghĩa rõ |

Không cộng tất cả nhóm thành một con số duy nhất rồi gọi đó là “tỷ lệ lỗi trình duyệt”. Một request bị hủy khi người dùng chuyển trang có ý nghĩa khác với API thanh toán trả `500`, và CSP report có thể là vi phạm bị chặn có chủ đích chứ không phải lỗi server.

### 1.1. Phân biệt lỗi trình duyệt và lỗi máy chủ

Một số tình huống thường gặp:

- API trả `500`: máy chủ hoặc gateway đã trả response lỗi. Đây là HTTP error.
- `fetch()` bị reject: có thể là lỗi mạng, lỗi CORS hoặc request bị abort. JavaScript không thể tự phân biệt chính xác mọi nguyên nhân từ exception chung.
- API trả `200`, nhưng `response.json()` lỗi: request thành công ở tầng HTTP nhưng response không đúng JSON mà ứng dụng mong đợi.
- Script bị CSP chặn: browser từ chối thực thi tài nguyên theo policy; máy chủ vẫn có thể trả `200` cho file script.
- Ảnh analytics không tải được sau khi người dùng rời trang: có thể là request bị hủy và không ảnh hưởng trải nghiệm chính.

Metric cần ghi nhận lớp quan sát và loại sự kiện. Nếu có request ID hoặc trace ID, dùng nó để đối chiếu với log server; đừng suy ra rằng không có server log đồng nghĩa trình duyệt không tạo request, vì proxy hoặc gateway có thể xử lý trước ứng dụng.

### 1.2. Real User Monitoring và synthetic monitoring

**Real User Monitoring (RUM)** thu thập dữ liệu từ các phiên trình duyệt thật. Nó phản ánh browser, thiết bị, mạng, vị trí và luồng sử dụng thực tế, nhưng phụ thuộc vào sampling, consent, ad blocker và khả năng gửi telemetry.

**Synthetic monitoring** chủ động chạy kịch bản kiểm tra từ môi trường đã định trước. Nó giúp phát hiện sự cố sớm và tái hiện luồng quan trọng, nhưng không đại diện cho mọi thiết bị hoặc mạng của người dùng.

Nên dùng cả hai khi phù hợp: synthetic probe kiểm tra tính sẵn sàng của các luồng quan trọng, còn RUM cho biết tác động thực tế theo nhóm người dùng. Không xem một probe chạy thành công từ một vùng mạng là bằng chứng toàn bộ browser traffic đang khỏe.

## 2. Định nghĩa metric và mẫu số

Một metric có thể gây hiểu nhầm nếu numerator và denominator không cùng phạm vi. Trước khi triển khai, ghi rõ sự kiện nào được đếm, đơn vị là request hay page view, cách loại trừ cancellation và cách khử trùng lặp.

### 2.1. Bộ metric cơ bản

| Metric | Công thức gợi ý | Ý nghĩa |
|---|---|---|
| `browser_js_error_rate` | Page view có ít nhất một uncaught JS error / tổng page view × 1.000 | Tỷ lệ lượt xem trang gặp lỗi JavaScript |
| `browser_unhandled_rejection_rate` | Page view có unhandled rejection / tổng page view × 1.000 | Mức độ lỗi Promise không được xử lý |
| `browser_api_http_5xx_rate` | API response `5xx` / tổng API response hợp lệ để tính × 100% | Tỷ lệ response lỗi phía server/gateway |
| `browser_api_http_4xx_rate` | API response `4xx` / tổng API response hợp lệ để tính × 100% | Theo dõi validation, auth, permission, rate limit và route |
| `browser_request_failure_rate` | Request thất bại ngoài cancellation / request được thử gửi × 100% | Tỷ lệ request không có response sử dụng được |
| `browser_resource_failure_rate` | Critical resource load failure / critical resource load attempt × 100% | Tỷ lệ tài nguyên quan trọng không tải được |
| `browser_action_failure_rate` | Thao tác nghiệp vụ thất bại / số lần thao tác được bắt đầu × 100% | Tác động trực tiếp tới công việc người dùng |
| `browser_error_affected_session_rate` | Session có ít nhất một lỗi thuộc nhóm / tổng session đủ điều kiện × 100% | Tỷ lệ phiên người dùng bị ảnh hưởng |

Ví dụ: trong 10.000 page view có 120 page view gặp ít nhất một uncaught JavaScript error. Khi đó:

\[
\text{browser\_js\_error\_rate}
= \frac{120}{10.000}\times 1.000
= 12 \text{ page view lỗi / 1.000 page view}
\]

Nếu có 40 request API `5xx` trên 2.000 API response, tỷ lệ HTTP 5xx là 2%. Không lấy 40 chia cho page view nếu mục tiêu là đo tỷ lệ request lỗi; hai metric trả lời hai câu hỏi khác nhau.

### 2.2. Chọn đơn vị đo

Các đơn vị thường dùng:

- **Per request:** phù hợp với API và resource load. Một page view có thể tạo nhiều request.
- **Per page view:** phù hợp để đo tỷ lệ lượt xem trang bị ảnh hưởng.
- **Per session:** phù hợp để ước lượng phạm vi người dùng gặp lỗi trong một phiên.
- **Per business action:** phù hợp với đăng nhập, lưu hồ sơ, thanh toán hoặc gửi biểu mẫu.

Không trộn số lượng event với số lượng người dùng. Một lỗi lặp lại 100 lần trong một vòng lặp có thể tạo 100 event nhưng chỉ ảnh hưởng một page view. Dashboard nên có cả số event và số đơn vị bị ảnh hưởng đã khử trùng lặp.

### 2.3. Định nghĩa điều kiện tính lỗi

Trước khi tính metric, hãy quy định:

1. Những route hoặc API nào nằm trong phạm vi.
2. Status nào là lỗi theo hợp đồng của endpoint.
3. `401`, `403`, `404` có phải lỗi hay kết quả nghiệp vụ được dự kiến.
4. Cancellation do điều hướng hoặc thao tác mới có bị loại khỏi request failure rate không.
5. Timeout được phân loại riêng hay tính vào request failure.
6. Retry được tính là một attempt hay một logical operation.
7. Một lỗi lặp lại trong cùng page view được tính một lần cho affected-page-view metric hay nhiều lần cho event metric.

Ví dụ, `404` trên endpoint tìm kiếm tùy chọn có thể là kết quả hợp lệ, trong khi `404` trên bundle JavaScript được tham chiếu từ HTML thường là lỗi triển khai. Metric cần biết loại request và hợp đồng của nó.

### 2.4. Ghi nhận mẫu số page view và session

Với ứng dụng nhiều trang, page view có thể tương ứng với mỗi lần tải document. Với SPA, cần phát một page view event sau khi router hoàn tất điều hướng tới route mới; không đếm mỗi lần component render như một page view.

Để khử trùng lặp, có thể tạo một `page_view_id` ngẫu nhiên cho mỗi lần điều hướng và gắn nó vào các event trong page view đó. Đây là ID kỹ thuật ngắn hạn để nối event, không phải user ID; không dùng nó làm label metric và không tái sử dụng để theo dõi người dùng qua nhiều phiên. Session denominator cần định nghĩa timeout/inactivity và chính sách consent rõ ràng.

Nếu lấy mẫu page view, hãy chọn mẫu trước khi ghi nhận cả page view denominator lẫn error event liên quan. Nếu chỉ sample error mà denominator vẫn lấy toàn bộ traffic, hoặc ngược lại, tỷ lệ tính ra sẽ bị lệch.

## 3. Phân loại lỗi trước khi đưa vào metric

Một taxonomy ổn định giúp dashboard không thay đổi ý nghĩa theo từng phiên bản ứng dụng.

| Mã phân loại | Điều kiện | Có nên tính vào request failure? |
|---|---|---|
| `http_5xx` | Response status từ 500 đến 599 | Có |
| `http_4xx_unexpected` | `4xx` ngoài các kết quả được hợp đồng cho phép | Theo endpoint |
| `network_or_policy_failure` | Fetch/XHR bị reject ngoài cancellation | Có, nhưng cần ghi rõ chưa phân biệt được nguyên nhân |
| `timeout` | Client hủy request vì deadline đã hết | Có trong timeout metric; có thể tính request failure theo SLI |
| `cancelled` | Người dùng, điều hướng hoặc luồng UI chủ động abort | Thường loại khỏi failure rate |
| `parse_or_schema_error` | Response nhận được nhưng không parse hoặc validate được | Tính vào application error metric |
| `resource_load_failure` | Critical resource không tải được | Theo mức độ quan trọng của resource |
| `js_uncaught` | Exception không được xử lý | Tính vào JS error metric |
| `unhandled_rejection` | Promise rejection không có handler | Theo dõi riêng, tránh đếm trùng với JS error |
| `policy_violation` | CSP/Trusted Types hoặc policy browser báo vi phạm | Theo dõi riêng và phân loại blocked/report-only |

### 3.1. `fetch()` và HTTP status

`fetch()` không tự reject chỉ vì server trả `404`, `429` hoặc `500`. Ứng dụng cần đọc `response.status` hoặc `response.ok` để phân loại HTTP error. Promise bị reject thường biểu thị lỗi khiến response không được cung cấp cho JavaScript, chẳng hạn lỗi mạng, CORS hoặc abort.

```javascript
const response = await fetch("/api/profile");

if (!response.ok) {
  // Đây là HTTP response error, không phải fetch rejection.
  recordHttpStatus(response.status);
}
```

Với XHR hoặc HTTP client library, kiểm tra hợp đồng callback/interceptor của thư viện vì nó có thể tự chuyển status không thành công thành exception.

### 3.2. Cancellation không phải lúc nào cũng là lỗi

Autocomplete thường hủy request tìm kiếm cũ khi người dùng nhập ký tự mới. SPA cũng có thể abort request khi route thay đổi. Những cancellation này thường là hành vi bình thường.

Nếu hệ thống tính mọi `AbortError` vào request failure, metric sẽ tăng khi người dùng thao tác nhanh dù backend và giao diện vẫn hoạt động tốt. Hãy phân biệt cancellation có chủ đích, timeout do client đặt và abort không rõ nguyên nhân.

### 3.3. CORS và lỗi mạng bị che

JavaScript thường không nhận được thông tin đủ chi tiết để phân biệt CORS với một số lỗi kết nối. Ví dụ, cả hai có thể xuất hiện dưới dạng `TypeError: Failed to fetch`. Vì vậy, đặt nhãn `network_or_policy_failure` ở client, rồi dùng browser Console, CSP/CORS report, RUM context và log server để điều tra sâu hơn.

Không tuyên bố metric client đã đo chính xác “CORS error rate” nếu instrumentation chỉ quan sát Promise rejection chung. Muốn đo CORS rõ hơn cần có bằng chứng bổ sung từ trình duyệt hoặc server-side policy telemetry.

## 4. Thu thập dữ liệu RUM trong trình duyệt

RUM nên ghi nhận sự kiện đã được phân loại và một tập context có giới hạn. Không gửi nguyên object Error, request body, toàn bộ URL hoặc cookie lên telemetry endpoint.

### 4.1. Theo dõi JavaScript error

`window` phát `error` event khi có một số lỗi script. Event listener ở capture phase cũng có thể quan sát lỗi tải tài nguyên như script, stylesheet hoặc ảnh. Hai loại này có cấu trúc event khác nhau.

Để giữ cardinality thấp, ánh xạ tên lỗi về một tập enum cho phép trước khi gửi:

```javascript
const knownErrorClasses = new Set([
  "Error", "TypeError", "ReferenceError", "RangeError",
  "SyntaxError", "URIError", "EvalError", "AbortError",
  "NetworkError", "SecurityError", "NonErrorRejection"
]);

function normalizeErrorClass(value) {
  return knownErrorClasses.has(value) ? value : "OtherError";
}
```

```javascript
window.addEventListener("error", event => {
  if (event instanceof ErrorEvent) {
    emitBrowserMetric("js_uncaught", {
      errorClass: normalizeErrorClass(event.error?.name || "Error"),
      route: window.APP_ROUTE_TEMPLATE || "unknown"
    });
    return;
  }

  const target = event.target;
  const tagName = target instanceof Element
    ? target.tagName.toLowerCase()
    : "unknown";

  emitBrowserMetric("resource_load_failure", {
    resourceType: tagName,
    route: window.APP_ROUTE_TEMPLATE || "unknown"
  });
}, true);
```

`APP_ROUTE_TEMPLATE` là route template do router cung cấp, ví dụ `/orders/:orderId`; không dùng pathname thực nếu nó có thể chứa email, ID tài khoản hoặc dữ liệu nhạy cảm. Ví dụ chỉ ghi loại tài nguyên và error class; không gửi message, stack hoặc URL đầy đủ.

Với script cross-origin không bật cơ chế chia sẻ phù hợp, browser có thể chỉ cung cấp thông tin lỗi tổng quát như `Script error.` và không cung cấp stack. Không cố vượt qua giới hạn này bằng cách thu thập nội dung nhạy cảm; cấu hình CORS cho script và `crossorigin` chỉ khi nguồn tài nguyên được tin cậy và cần chẩn đoán chi tiết.

### 4.2. Theo dõi unhandled promise rejection

```javascript
window.addEventListener("unhandledrejection", event => {
  const reason = event.reason;
  const errorClass = normalizeErrorClass(
    reason && typeof reason === "object" && reason.name
      ? String(reason.name)
      : "NonErrorRejection"
  );

  emitBrowserMetric("unhandled_rejection", {
    errorClass,
    route: window.APP_ROUTE_TEMPLATE || "unknown"
  });
});
```

Không mặc định gọi `event.preventDefault()` chỉ để metric không hiện lỗi trong Console; việc đó có thể làm mất tín hiệu debug của ứng dụng. Một số rejection cross-origin có thể bị browser giới hạn thông tin vì lý do bảo mật. Metric vì thế không thể bảo đảm quan sát mọi promise rejection.

### 4.3. Đo HTTP status và request failure

Nên instrument API client dùng chung để mỗi request được gắn tên operation ổn định. Tên operation như `profile.read` hoặc `orders.list` có cardinality thấp hơn URL tùy biến.

```javascript
async function measuredFetch(operation, input, init = {}) {
  const startedAt = performance.now();

  try {
    const response = await fetch(input, init);
    const responseHeadersMs = Math.round(performance.now() - startedAt);

    if (!response.ok) {
      emitBrowserMetric("api_http_error", {
        operation,
        status: response.status,
        responseHeadersMs
      });
    } else {
      emitBrowserMetric("api_request_success", {
        operation,
        status: response.status,
        responseHeadersMs
      });
    }

    return response;
  } catch (error) {
    const cancelled = error?.name === "AbortError";
    emitBrowserMetric(cancelled ? "api_request_cancelled" : "api_request_failed", {
      operation,
      errorClass: cancelled ? "AbortError" : "FetchRejected",
      elapsedUntilFailureMs: Math.round(performance.now() - startedAt)
    });
    throw error;
  }
}
```

Ví dụ này trả response về cho caller để caller tiếp tục parse và xử lý. Nếu caller parse JSON thất bại, hãy ghi một metric `api_response_parse_error` riêng ở lớp đó. Không coi một response `200` là thành công nghiệp vụ nếu body sai schema hoặc thao tác chưa hoàn tất.

`fetch()` resolve khi response headers sẵn sàng, trước khi ứng dụng đọc hết body. Vì vậy `responseHeadersMs` không phải tổng thời gian tải body hoặc thời gian hoàn tất business action; đo riêng thời gian parse/consume body nếu cần.

Không đưa URL tùy biến vào metric. Nếu cần điều tra endpoint cụ thể, dùng operation name đã được allowlist hoặc log/trace có kiểm soát. Với request có thể bị hủy, nên ghi riêng `cancelled`; chỉ tính vào SLI nếu định nghĩa dịch vụ coi cancellation đó là lỗi người dùng thực sự.

### 4.4. Gửi metric an toàn

Một hàm gửi telemetry có thể dùng `navigator.sendBeacon()` để giảm nguy cơ mất event khi trang unload. Endpoint nên cùng origin hoặc có CORS được cấu hình chặt chẽ.

```javascript
function emitBrowserMetric(name, fields = {}) {
  const payload = {
    name,
    timestamp: new Date().toISOString(),
    release: window.APP_RELEASE || "unknown",
    route: window.APP_ROUTE_TEMPLATE || "unknown",
    fields
  };

  const body = new Blob([JSON.stringify(payload)], {
    type: "application/json"
  });

  const queued = navigator.sendBeacon?.("/rum/browser-events", body);
  if (queued) return;

  // Fallback không dùng API client đã instrument để tránh vòng lặp telemetry.
  fetch("/rum/browser-events", {
    method: "POST",
    body,
    credentials: "same-origin",
    keepalive: true
  }).catch(() => {
    // Không tạo thêm error event khi chính telemetry endpoint thất bại.
  });
}
```

`sendBeacon()` trả về việc browser đã xếp dữ liệu vào hàng đợi gửi, không bảo đảm server đã nhận hoặc lưu thành công. Endpoint telemetry cần xác thực phù hợp, rate limit, giới hạn payload, kiểm tra schema và loại bỏ field ngoài allowlist. Nếu telemetry endpoint lỗi, không để lỗi gửi metric tạo thêm một vòng lặp event.

Timestamp từ client có thể lệch do đồng hồ thiết bị. Dùng thời điểm ingestion phía server làm mốc chuẩn để tổng hợp theo thời gian; giữ client timestamp chỉ khi cần phân tích thứ tự sự kiện và đã tính tới clock skew.

## 5. Resource Timing và hiệu năng tài nguyên

Resource Timing API cung cấp thời gian tải của tài nguyên như script, stylesheet, ảnh và fetch/XHR. Có thể dùng `PerformanceObserver` để thu thập dữ liệu mà không cần quét toàn bộ performance entries liên tục.

```javascript
const observer = new PerformanceObserver(list => {
  for (const entry of list.getEntries()) {
    if (entry.entryType !== "resource") continue;

    emitBrowserMetric("resource_timing", {
      resourceType: entry.initiatorType,
      durationMs: Math.round(entry.duration),
      transferBytes: entry.transferSize || 0
    });
  }
});

observer.observe({ type: "resource", buffered: true });
```

Đây là ví dụ đơn giản; trong production cần lọc loại tài nguyên quan trọng, sampling và giới hạn số event. Không gửi `entry.name` trực tiếp nếu URL có thể chứa query nhạy cảm hoặc định danh người dùng.

Một số giới hạn:

- Cross-origin timing chi tiết có thể bị giới hạn nếu response không có `Timing-Allow-Origin` phù hợp.
- `transferSize` bằng `0` không nhất thiết có nghĩa không có dữ liệu; tài nguyên có thể đến từ cache hoặc thông tin bị giới hạn.
- Resource Timing không thay thế error event hay fetch instrumentation; một số lỗi tải tài nguyên không tạo entry có thể sử dụng.
- Không dùng `duration` làm thay thế cho API latency ở server; đây là thời gian browser quan sát và có thể gồm nhiều thành phần.

Để đo trải nghiệm tổng thể, có thể theo dõi thêm Core Web Vitals như LCP, INP và CLS. Chúng là metric hiệu năng/trải nghiệm, không phải browser error metric; nên hiển thị riêng và phân tích tương quan với error rate.

## 6. Bối cảnh cần gắn với metric

Metric có ích khi nhóm vận hành biết lỗi xảy ra ở đâu và trong điều kiện nào. Chọn các dimension có giá trị điều tra nhưng giới hạn cardinality.

| Dimension | Ví dụ | Lưu ý |
|---|---|---|
| `environment` | production, staging | Không trộn dữ liệu staging với production |
| `release` | build version hoặc commit tag | Giúp so sánh trước/sau triển khai |
| `route_template` | `/login`, `/orders/:id` | Không gửi URL có ID hoặc query thực |
| `browser_family` | Chrome, Firefox, Safari, Edge | Nhóm version theo major nếu cần |
| `os_family` | Windows, macOS, Android, iOS | Không cần user agent đầy đủ cho metric cơ bản |
| `device_class` | desktop, mobile, tablet | Tránh fingerprint thiết bị chi tiết |
| `api_operation` | `profile.read`, `orders.list` | Chỉ dùng tên operation được định nghĩa trước |
| `error_category` | `http_5xx`, `js_uncaught`, `timeout` | Dùng enum ổn định |
| `region` | vùng địa lý tổng quát | Không lưu tọa độ chính xác nếu không cần |
| `connection_type` | effective type hoặc nhóm online/offline | Có thể thiếu hoặc không chính xác trên một số browser |

Không dùng các giá trị sau làm label metric:

- User ID, email, số điện thoại hoặc account ID.
- URL đầy đủ, query string, fragment hoặc route chứa định danh.
- Nội dung error message tùy biến, stack trace nguyên bản hoặc request ID có giá trị không giới hạn.
- Token, cookie, session ID, form value hoặc response body.
- IP đầy đủ hoặc thông tin thiết bị có thể tạo fingerprint khi không có nhu cầu rõ ràng.

Metric label có cardinality cao làm tăng chi phí lưu trữ và khiến dashboard khó đọc. Dùng log hoặc trace có kiểm soát cho chi tiết từng sự kiện; metric chỉ nên giữ các chiều phân nhóm ổn định.

## 7. Khử trùng lặp và fingerprint lỗi

Một exception có thể phát sinh nhiều lần do render loop, retry hoặc cùng một component xuất hiện trên nhiều route. Cần phân biệt số lần phát sinh với số lỗi duy nhất và số page view/session bị ảnh hưởng.

Một fingerprint có thể dựa trên các trường ổn định đã chuẩn hóa:

- Loại lỗi (`TypeError`, `ReferenceError`, `SyntaxError` hoặc mã ứng dụng).
- Tên operation hoặc component.
- Route template.
- Release version.
- Một mã lỗi nội bộ do ứng dụng định nghĩa.

Không dùng toàn bộ stack trace hoặc error message làm label metric. Nếu cần fingerprint chi tiết, có thể tính hash từ stack đã loại bỏ URL, query, dòng có dữ liệu nhạy cảm và các đoạn biến thiên; lưu hash trong event/log có giới hạn, không làm label không giới hạn trong time-series metric.

Nên có các phép tổng hợp khác nhau:

- `error_events`: tổng số event thô.
- `unique_error_fingerprints`: số fingerprint khác nhau trong cửa sổ.
- `affected_page_views`: số page view có ít nhất một lỗi.
- `affected_sessions`: số session có ít nhất một lỗi.

Nếu chỉ nhìn event count, một lỗi lặp liên tục có thể lấn át các lỗi mới nhưng ảnh hưởng tới nhiều người dùng hơn. Nếu chỉ nhìn unique fingerprint, một lỗi hiếm nhưng nghiêm trọng có thể bị xem nhẹ. Hãy xem cả tần suất và phạm vi tác động.

## 8. Privacy, consent và bảo vệ telemetry

RUM có thể thu thập thông tin liên quan tới hoạt động của người dùng. Hãy áp dụng data minimization ngay ở client, không chờ tới pipeline mới lọc.

### 8.1. Dữ liệu không nên thu thập

- Cookie, `Authorization`, access token, refresh token hoặc API key.
- Mật khẩu, mã OTP, nội dung form và dữ liệu thanh toán.
- Query string có chữ ký, reset token hoặc dữ liệu cá nhân.
- Response body hoặc request body nguyên bản.
- Stack trace chứa đường dẫn nội bộ hoặc dữ liệu người dùng nếu chưa được làm sạch.

Khi cần ghi nhận lỗi ở một form, chỉ gửi tên form/operation và mã validation đã định nghĩa. Không gửi giá trị trường người dùng nhập.

### 8.2. Consent và lựa chọn của người dùng

Xác định telemetry nào là cần thiết cho vận hành và telemetry nào cần consent theo chính sách, luật áp dụng và yêu cầu tổ chức. Tôn trọng lựa chọn từ chối, cấu hình DNT/GPC nếu chính sách sản phẩm yêu cầu và không tìm cách vượt qua ad blocker hoặc cơ chế bảo vệ của browser.

Nếu không thể gửi RUM do consent hoặc network policy, metric phải ghi nhận coverage/sampling context để tránh kết luận sai rằng không có lỗi. Không xem việc thiếu event là bằng chứng không xảy ra sự cố.

### 8.3. Kiểm soát endpoint telemetry

- Chỉ nhận schema và event name đã định nghĩa.
- Giới hạn kích thước payload và tần suất gửi.
- Chặn field không được phép và chuẩn hóa giá trị.
- Bảo vệ endpoint bằng HTTPS, xác thực phù hợp và rate limiting.
- Kiểm tra `Origin`/Fetch Metadata và chống giả mạo hoặc làm nhiễu telemetry; CORS không ngăn mọi cross-site request có thể gửi tới endpoint.
- Hạn chế quyền truy cập dashboard và raw event.
- Đặt retention và quy trình xóa theo chính sách dữ liệu.
- Theo dõi lỗi telemetry riêng để phân biệt pipeline mất dữ liệu với ứng dụng không phát sinh lỗi.

Telemetry endpoint không nên trở thành một API mở cho phép bất kỳ trang nào gửi dữ liệu tùy ý. Nếu nhận cross-origin, cấu hình CORS theo allowlist và đánh giá CSRF/abuse theo kiến trúc.

## 9. Dashboard browser error

Một dashboard vận hành nên trả lời được ba câu hỏi: lỗi có tăng không, ai/luồng nào bị ảnh hưởng và thay đổi nào có liên quan.

Các panel gợi ý:

| Panel | Nội dung | Mục đích |
|---|---|---|
| Error rate over time | JS error, API failure, resource failure theo thời gian | Phát hiện spike và xu hướng |
| Affected page views | Page view/session có lỗi | Đo phạm vi tác động |
| Top error fingerprints | Fingerprint, event count, affected sessions | Tìm nhóm lỗi nổi bật |
| Error by route | Route template và error category | Xác định luồng bị ảnh hưởng |
| Error by release | Release version và error rate | Phát hiện regression sau deploy |
| Browser/device breakdown | Browser family, OS, device class | Phát hiện lỗi tương thích |
| API operation status | 4xx/5xx, timeout và request failure | Phân biệt lỗi backend và client |
| Telemetry coverage | Session có RUM, sampling rate, dropped events | Đánh giá độ tin cậy dữ liệu |

Luôn hiển thị volume cùng rate. Một route có tỷ lệ lỗi 50% trên hai request không nhất thiết nghiêm trọng hơn route có tỷ lệ 2% trên một triệu request; ngược lại, route thanh toán có volume thấp vẫn có thể cần ưu tiên cao do tác động nghiệp vụ.

### 9.1. So sánh release

Khi triển khai phiên bản mới, so sánh error rate của release hiện tại với release trước trên cùng khoảng thời gian, route và nhóm browser. Chú ý:

- Traffic mix có thay đổi không?
- Sampling rate có thay đổi không?
- Có thay đổi browser support hoặc feature flag không?
- Lỗi có bắt đầu đúng thời điểm deploy không?
- Chỉ một browser/version hay tất cả người dùng bị ảnh hưởng?

Một đợt phát hành có thể trùng thời điểm với sự cố mạng của nhà cung cấp hoặc một extension phổ biến. Dùng release marker và correlation với server metrics để kiểm tra giả thuyết.

## 10. SLI, SLO và ngưỡng cảnh báo

SLI (Service Level Indicator) là chỉ số phản ánh chất lượng dịch vụ. SLO (Service Level Objective) là mục tiêu đặt cho SLI trong một cửa sổ thời gian. Browser error metric có thể làm SLI nếu định nghĩa rõ phạm vi người dùng và hành vi cần bảo vệ.

Ví dụ SLI cho page view:

\[
\text{Good page-view rate}
= \frac{\text{Page view không gặp lỗi nghiêm trọng}}{\text{Page view đủ điều kiện}}\times 100\%
\]

Ví dụ SLI cho API request:

\[
\text{Successful API rate}
= \frac{\text{Request có response hợp lệ theo hợp đồng}}{\text{Request đủ điều kiện}}
\times 100\%
\]

Không dùng một SLO chung cho mọi route. Luồng đăng nhập, thanh toán hoặc lưu dữ liệu có thể cần mục tiêu khác trang nội dung tĩnh. Định nghĩa “good” phải bao gồm cả status, response schema và điều kiện nghiệp vụ cần thiết.

### 10.1. Thiết kế alert

Alert nên kết hợp:

- Error rate vượt baseline hoặc SLO threshold.
- Số request/page view tối thiểu để tránh alert từ volume quá thấp.
- Thời gian kéo dài đủ để loại bỏ spike ngắn không đáng kể.
- Số affected session hoặc business action thất bại.
- Mức độ nghiêm trọng của route và error category.
- Thay đổi release hoặc cấu hình gần thời điểm phát sinh.

Ví dụ ngưỡng ban đầu cho một dịch vụ giả định:

| Điều kiện | Hành động |
|---|---|
| JS error rate tăng gấp đôi baseline trong 10 phút và có đủ page view | Tạo cảnh báo cho nhóm frontend |
| API 5xx vượt SLO burn threshold trong nhiều cửa sổ | Cảnh báo nhóm backend/on-call |
| Login action failure tăng đột ngột | Ưu tiên cao vì chặn người dùng truy cập |
| Một browser version có resource failure tăng mạnh | Kiểm tra compatibility và rollout |
| Telemetry ingestion giảm bất thường | Cảnh báo chất lượng dữ liệu giám sát |

Các con số thực tế cần được hiệu chỉnh theo traffic, độ biến động và mức độ quan trọng của sản phẩm. Không alert chỉ vì có một exception; ưu tiên tỷ lệ, volume và user impact.

### 10.2. Error budget

Nếu SLO quy định tỷ lệ page view tốt tối thiểu, phần còn lại là error budget. Tốc độ tiêu thụ error budget tăng nhanh có thể cho thấy một đợt regression hoặc sự cố. Dùng burn rate để ưu tiên xử lý khi chất lượng giảm nhanh, thay vì chỉ nhìn một ngưỡng cố định.

Error budget cần dựa trên SLI có mẫu số đáng tin cậy. Nếu RUM coverage giảm, consent hoặc sampling thay đổi mà không được ghi nhận, việc tính error budget sẽ sai lệch.

## 11. Điều tra browser error metric

Khi dashboard có spike, hãy điều tra theo thứ tự để xác định phạm vi và lớp lỗi.

1. **Xác minh dữ liệu:** sampling, event ingestion, release tag và denominator có thay đổi không?
2. **Xác định phạm vi:** route, browser, OS, device, region và release nào bị ảnh hưởng?
3. **Phân loại lỗi:** JS exception, HTTP status, request failure, cancellation, resource failure hay policy violation?
4. **Đối chiếu thời gian:** bắt đầu trước hay sau deploy, feature flag, thay đổi CDN hoặc cấu hình header?
5. **Tìm fingerprint:** lỗi nào tăng event count và affected session nhiều nhất?
6. **Đối chiếu server:** request ID/trace ID, 4xx/5xx, latency, gateway và dependency.
7. **Tái hiện có kiểm soát:** dùng browser/version và route phù hợp trên staging.
8. **Khắc phục và xác minh:** theo dõi metric sau sửa, kiểm tra regression và cập nhật incident timeline.

### 11.1. Ví dụ: JS error tăng sau deploy

Sau một lần release, `browser_js_error_rate` tăng từ 3 lên 25 lỗi trên 1.000 page view. Dashboard cho thấy lỗi tập trung ở route `/account` và browser family Chromium.

Quy trình:

1. So sánh release mới với release trước trên cùng route.
2. Kiểm tra fingerprint và error class tăng mạnh nhất.
3. Xác định component hoặc API response được dùng ở route đó.
4. Đối chiếu CSP/Trusted Types report nếu thay đổi policy cùng release.
5. Tái hiện trên browser tương ứng và kiểm tra Console.
6. Nếu có regression, rollback feature flag hoặc phát hành bản sửa.
7. Theo dõi affected page view rate trở về baseline.

Không kết luận CSP là nguyên nhân chỉ vì CSP thay đổi cùng thời điểm. Cần có blocked reason hoặc report tương ứng.

### 11.2. Ví dụ: request failure tăng nhưng server 5xx không đổi

RUM ghi nhận request failure tăng, trong khi server 5xx ổn định. Điều này có thể do CORS, DNS/TLS, extension, proxy hoặc mạng người dùng. Hãy so sánh browser family, region và route; xem Console, request timing và CORS report nếu có. Metric client không đủ để phân biệt mọi nguyên nhân nên cần telemetry bổ sung.

### 11.3. Ví dụ: metric giảm nhưng người dùng vẫn báo lỗi

Có thể RUM không được gửi do consent, ad blocker, CSP, DNS hoặc telemetry endpoint lỗi. Kiểm tra telemetry coverage, synthetic monitoring, server logs và kênh phản hồi người dùng. Không xem số event bằng 0 là bằng chứng ứng dụng không có lỗi.

## 12. CSP và browser policy reporting

CSP có thể gửi report khi browser quan sát vi phạm policy. Có thể dùng Reporting API với `Reporting-Endpoints` và `report-to` tùy browser support; `report-uri` là cơ chế cũ vẫn còn gặp trong hệ thống hiện hữu.

Ví dụ cấu hình minh họa:

```http
Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"
Content-Security-Policy: default-src 'self'; object-src 'none'; report-to csp-endpoint
```

Report có thể chứa document URL, blocked URL, directive, source file và vị trí dòng. Các giá trị này có thể tiết lộ đường dẫn nội bộ hoặc query nhạy cảm. Hãy lọc, giới hạn retention và quyền truy cập trước khi lưu.

Phân biệt:

- **Enforcing CSP violation:** browser chặn hành vi theo policy đang thực thi.
- **Report-Only violation:** browser ghi nhận vi phạm policy thử nghiệm nhưng không chặn theo policy đó.
- **Trusted Types violation:** browser từ chối dữ liệu không đúng kiểu tại sink được bảo vệ.
- **Network error:** request không hoàn tất; không phải mọi request failure đều là CSP violation.

Không cộng CSP report và JavaScript error thành cùng một numerator nếu chúng đo các sự kiện khác nhau. Một CSP report có thể xuất hiện nhiều lần cho cùng một trang hoặc do tài nguyên bên thứ ba.

## 13. Sampling và giới hạn tải

RUM có thể tạo lượng event lớn. Sampling giúp giảm tải nhưng phải được thiết kế để không làm méo metric.

- Giữ sampling rate ổn định trong cùng cửa sổ so sánh hoặc ghi rate vào telemetry context.
- Có thể lấy mẫu page view trước, sau đó ghi các event liên quan tới page view đã chọn.
- Giữ tỷ lệ cao hơn cho lỗi nghiêm trọng hoặc luồng quan trọng, nhưng ghi rõ sampling strategy.
- Giới hạn số event lặp từ cùng fingerprint trong một page view.
- Có cơ chế rate limit client-side để vòng lặp lỗi không làm tràn endpoint.
- Theo dõi dropped event, queue failure và ingestion delay.

Nếu sampling thay đổi từ 100% xuống 10%, số event thô có thể giảm khoảng 90% dù tỷ lệ lỗi thực không đổi. Dashboard cần dùng sampling-aware aggregation hoặc cân nhắc trọng số khi tính tỷ lệ.

## 14. Kiểm thử instrumentation và metric

Telemetry cần được kiểm thử giống một phần của ứng dụng. Dùng môi trường thử nghiệm và event giả, không cố ý tạo lỗi trên production để kiểm tra pipeline.

### Bài tập A: Phân loại lỗi

1. Tạo một trang thử nghiệm có uncaught exception.
2. Tạo một Promise rejection không có handler.
3. Gọi API trả `500`.
4. Gọi một endpoint thử nghiệm không truy cập được.
5. Abort một request khi người dùng thay route.
6. Tham chiếu một script thử nghiệm không tồn tại.

Kết quả cần đạt: các event được phân loại thành `js_uncaught`, `unhandled_rejection`, `http_5xx`, `network_or_policy_failure`, `cancelled` và `resource_load_failure` theo đúng ngữ cảnh.

### Bài tập B: Xác minh mẫu số

Tạo 100 page view thử nghiệm, trong đó 10 page view có ít nhất một JavaScript error và 15 event lỗi được phát ra. Xác minh:

- Event count là 15.
- Affected page view là 10.
- Error rate là 100 lỗi page view trên 1.000 page view.

Kết quả cần đạt: phân biệt event count với tỷ lệ page view bị ảnh hưởng.

### Bài tập C: Kiểm tra privacy

Tạo một event từ trang có query string giả lập chứa giá trị nhạy cảm. Xác minh payload telemetry chỉ có route template và operation name đã allowlist; không chứa query, cookie, token, form value hoặc response body.

Kết quả cần đạt: dữ liệu nhạy cảm được loại bỏ ngay tại client và tiếp tục được kiểm tra ở server ingestion.

### Bài tập D: Kiểm tra alert sau release

1. Ghi baseline error rate cho release thử nghiệm.
2. Phát hành bản build tạo một lỗi đã biết trong staging.
3. Quan sát metric theo route, release và browser.
4. Xác minh alert chỉ kích hoạt khi đủ volume và vượt điều kiện đã định nghĩa.
5. Khắc phục và xác minh metric trở về baseline.

Kết quả cần đạt: alert gắn với user impact và release, không kích hoạt chỉ bởi một event lẻ.

## 15. Những nhầm lẫn thường gặp

- **Không có event nghĩa là không có lỗi:** telemetry có thể bị chặn, sampling hoặc endpoint ingest gặp sự cố.
- **Mỗi exception là một người dùng bị ảnh hưởng:** một page view có thể phát ra nhiều event lặp.
- **Mọi `4xx` đều là lỗi:** một số `404`, `401` hoặc `409` là kết quả hợp lệ theo hợp đồng API.
- **`fetch` reject chứng minh API server down:** lỗi có thể do CORS, DNS, TLS, proxy hoặc abort.
- **Cancellation luôn là lỗi:** nhiều cancellation là hành vi bình thường của SPA.
- **HTTP `200` nghĩa là thao tác thành công:** response có thể sai schema hoặc nghiệp vụ chưa hoàn tất.
- **Metric có thể dùng URL và stack trace làm label:** cardinality cao và nguy cơ lộ dữ liệu khiến metric trở nên đắt và không an toàn.
- **CSP report là JavaScript error:** policy violation cần được phân loại riêng.
- **RUM thay thế synthetic monitoring:** RUM phản ánh người dùng thật; synthetic kiểm tra kịch bản có kiểm soát.
- **Số event thô đủ để đặt SLO:** cần numerator, denominator, sampling và phạm vi route rõ ràng.

## 16. Checklist vận hành Browser error metric

- [ ] Có taxonomy ổn định cho JS error, rejection, HTTP error, request failure, cancellation và resource failure.
- [ ] Mỗi metric có numerator, denominator, đơn vị đo và điều kiện loại trừ rõ ràng.
- [ ] Event count được phân biệt với affected page view và affected session.
- [ ] RUM gắn release, environment, route template và browser family cần thiết.
- [ ] Không gửi cookie, token, query nhạy cảm, form value hoặc response body.
- [ ] Metric label có cardinality giới hạn; chi tiết điều tra nằm trong log/trace được kiểm soát.
- [ ] Sampling rate, dropped event và telemetry coverage được theo dõi.
- [ ] CSP/Trusted Types report được phân loại riêng với runtime/network error.
- [ ] Dashboard có volume, rate, affected users, route, browser và release breakdown.
- [ ] Alert dựa trên SLO, volume tối thiểu và user impact.
- [ ] Có quy trình đối chiếu RUM với server log, trace và synthetic probe.
- [ ] Có retention, access control và kiểm thử privacy cho telemetry pipeline.

Browser error metric chỉ đáng tin khi định nghĩa lỗi và mẫu số nhất quán, dữ liệu được thu thập an toàn và dashboard thể hiện đúng phạm vi người dùng bị ảnh hưởng. Kết hợp RUM với metric server, browser policy report và synthetic monitoring giúp nhóm vận hành phát hiện regression sớm, xác định lớp phát sinh lỗi và bảo vệ trải nghiệm người dùng mà không thu thập quá mức dữ liệu trình duyệt.
