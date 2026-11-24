# Unusual origin

Trong ứng dụng web, origin cho biết một tài liệu hoặc ứng dụng được phục vụ từ scheme, host và port nào. Origin là cơ sở để trình duyệt áp dụng Same-Origin Policy (SOP), CORS và một số cơ chế cách ly. Khi giám sát hệ thống, những origin xuất hiện trong request, báo cáo bảo mật hoặc luồng giao tiếp có thể cung cấp tín hiệu về hoạt động bình thường, cấu hình sai hoặc hành vi đáng ngờ.

Unusual origin là origin khác với nguồn đã được ứng dụng dự kiến hoặc khác với hành vi thông thường của một route, tenant hay nhóm người dùng. Một origin lạ có thể xuất hiện khi người dùng mở ứng dụng từ một trang tích hợp mới, hệ thống thanh toán chuyển hướng, một portal được triển khai hoặc một subdomain hợp lệ được thêm vào. Nó cũng có thể là dấu hiệu của cấu hình CORS quá rộng, request giả mạo, trang phishing, subdomain bị chiếm quyền hoặc một nỗ lực truy cập dữ liệu cross-origin.

Giám sát unusual origin cần kết hợp ngữ cảnh. Chỉ nhìn thấy `Origin` khác host của API không đủ để kết luận có tấn công. Cần xác định endpoint, phương thức, trạng thái xác thực, cookie/credentials, quyết định CORS và CSRF, Fetch Metadata, lịch sử origin hợp lệ cùng tác động của request. Đặc biệt, header `Origin` là dữ liệu do client gửi; nó là tín hiệu để phân tích chứ không phải bằng chứng xác thực danh tính.

Bài học thuộc phạm vi vận hành bảo mật ứng dụng web: phân tích ranh giới trình duyệt, origin, cookie và ứng dụng để hiểu SOP, CORS và các cơ chế cách ly. Nội dung tập trung vào cách thu thập telemetry, thiết lập baseline, phát hiện bất thường, xử lý cảnh báo và lưu bằng chứng an toàn.

## Mục tiêu

Sau bài học, bạn có thể:

- Xác định những nguồn telemetry có thể chứa thông tin origin và giới hạn của từng nguồn.
- Chuẩn hóa origin theo scheme, host và port trước khi phân tích.
- Xây dựng baseline theo ứng dụng, route, tenant và loại request.
- Phát hiện origin mới, origin không được phép, origin `null`, scheme/port bất thường và dấu hiệu CORS reflection.
- Kết hợp origin với cookie, Fetch Metadata, CSRF, xác thực và hành vi truy cập.
- Thiết kế dashboard, cảnh báo và quy trình triage có kiểm soát false positive.
- Bảo vệ log và báo cáo để tránh biến hệ thống giám sát thành nguồn rò rỉ dữ liệu.

## Origin và các tín hiệu cần giám sát

Origin web thông thường gồm ba thành phần: scheme, host và port. Ví dụ `https://portal.example.test` là một origin; path, query và fragment không thuộc origin. `https://portal.example.test:8443` và `http://portal.example.test` là các origin khác với địa chỉ HTTPS mặc định.

Trong request HTTP, header `Origin` thường được trình duyệt gửi trong các tình huống cross-origin và một số request thay đổi trạng thái. Header này có thể chứa một origin cụ thể hoặc giá trị `null` trong một số ngữ cảnh opaque origin. Header có thể không xuất hiện ở mọi request. Client không phải trình duyệt cũng có thể tự đặt header này, vì vậy không được dùng nó làm căn cứ duy nhất để cấp quyền.

Các tín hiệu bổ sung:

| Tín hiệu | Ý nghĩa | Giới hạn khi giám sát |
|---|---|---|
| `Origin` | Nguồn origin mà client khai báo cho request | Có thể thiếu, là `null` hoặc bị client không phải trình duyệt giả mạo |
| `Referer` | URL của trang giới thiệu request theo Referrer Policy | Có thể bị lược bỏ hoặc chỉ chứa origin; có thể chứa dữ liệu nhạy cảm nếu lưu cả URL |
| `Sec-Fetch-Site` | Quan hệ `same-origin`, `same-site`, `cross-site` hoặc `none` | Không phải mọi client đều gửi; client tùy ý có thể giả mạo header |
| `Sec-Fetch-Mode` | Ngữ cảnh fetch như `cors`, `no-cors`, `navigate` | Cần đọc cùng destination và route |
| `Sec-Fetch-Dest` | Loại đích như `document`, `iframe`, `script`, `image` | Chỉ là tín hiệu phân loại request |
| CORS decision | Server có cho phép origin đọc response hay không | Cần ghi quyết định thực tế tại middleware/server |
| CSRF decision | Token hoặc kiểm tra nguồn request có hợp lệ không | Không nên chỉ lưu một status HTTP chung |
| CSP report | Vi phạm policy, `blocked-uri`, directive và document liên quan | Report có thể chứa dữ liệu do client gửi, lặp nhiều hoặc giả mạo |
| Authentication context | Session, tenant, loại client và quyền của principal | Không ghi cookie, token hoặc thông tin xác thực thô |

`Host` và `:authority` xác định đích request ở tầng HTTP; chúng không phải origin nguồn. `X-Forwarded-Host` hoặc `Forwarded` có thể được proxy thêm vào nhưng chỉ đáng tin khi request đi qua proxy được cấu hình tin cậy và ứng dụng chỉ chấp nhận header từ proxy đó. Không lấy giá trị tùy ý từ client để xây dựng danh sách origin được phép.

## Nguồn telemetry

Giám sát tốt cần nối các sự kiện từ nhiều lớp. Mỗi nguồn chỉ quan sát được một phần của luồng request.

### Reverse proxy, gateway và WAF

Edge proxy có thể ghi nhận thời gian, địa chỉ đích, method, route, status, header nguồn được chọn và quyết định WAF. Đây là vị trí phù hợp để thấy request trước khi ứng dụng xử lý, nhưng cần cấu hình log có chủ đích để không lưu toàn bộ header hoặc query string nhạy cảm.

Ghi nhận origin ở edge có ích để phát hiện lưu lượng mới, nhưng quyết định CORS/CSRF thường nằm ở ứng dụng. Nếu proxy chỉ ghi response status, sẽ khó phân biệt request bị từ chối ở WAF, middleware CORS, middleware CSRF hay business logic.

### Application middleware

Middleware của ứng dụng biết route, tenant, trạng thái xác thực, CORS decision và CSRF decision. Đây thường là nguồn có ngữ cảnh tốt nhất để xác định một request có được phép thực hiện hay không.

Ghi sự kiện tại điểm quyết định: origin được phân loại, policy áp dụng, lý do cho phép/từ chối và mã tương quan. Tránh ghi token hoặc toàn bộ session object. Nếu ứng dụng có nhiều API gateway hoặc service, thống nhất tên trường và cách chuẩn hóa để có thể truy vấn xuyên hệ thống.

### Browser security reports

CSP Reporting API hoặc endpoint nhận báo cáo vi phạm có thể cho biết tài liệu đã cố tải script, style, image, frame hoặc kết nối tới một nguồn không phù hợp với policy. Báo cáo có thể giúp nhận diện một origin mới xuất hiện trong bundle hoặc một script không mong đợi.

CSP report không đồng nghĩa có khai thác thành công. Một report có thể do tính năng hợp lệ, extension trình duyệt, nội dung thử nghiệm, browser compatibility hoặc cấu hình policy chưa hoàn thiện. Endpoint nhận report phải giới hạn kích thước, rate limit, kiểm tra schema và xem mọi trường là dữ liệu không tin cậy. Không render trực tiếp nội dung report vào dashboard bằng HTML thô.

### Client-side telemetry

Ứng dụng có thể ghi lỗi CORS, `postMessage` bị từ chối, lỗi tải iframe hoặc trạng thái `crossOriginIsolated`. Client telemetry giúp phát hiện vấn đề người dùng gặp phải, nhưng không thay thế log server. Một script ở origin bị kiểm soát có thể sửa hoặc ngừng gửi telemetry; dữ liệu client cũng có thể bị giả mạo.

Chỉ gửi thông tin tối thiểu cần thiết. Không thu thập toàn bộ URL, DOM, cookie, localStorage hoặc nội dung biểu mẫu chỉ để điều tra origin bất thường.

## Chuẩn hóa và phân loại origin

Trước khi so sánh, chuẩn hóa origin thành tuple scheme, hostname và port hiệu lực. Hostname cần được xử lý theo quy tắc URL/IDN; port mặc định cần được chuẩn hóa. Không dùng phép so sánh chuỗi con như `includes("example.test")` hoặc `endsWith("example.test")` để quyết định một origin có đáng tin cậy hay không.

Một pipeline phân loại có thể dùng các nhóm:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Known allowed | Origin đã được phê duyệt cho ứng dụng/route | Theo dõi tần suất và thay đổi cấu hình |
| Known partner | Portal, payment provider hoặc identity provider đã đăng ký | So sánh với danh mục tích hợp và thời hạn phê duyệt |
| New observed | Origin chưa có trong baseline | Ghi nhận, đối chiếu release/tích hợp và theo dõi phạm vi |
| Explicitly denied | Origin nằm trong danh sách từ chối hoặc policy không cho phép | Ghi lý do từ chối và tăng mức cảnh báo theo tác động |
| Opaque/null | Header `Origin: null` hoặc báo cáo origin tuần tự hóa thành `null` | Giữ riêng nhóm; xác định ngữ cảnh sandbox/data/file và không tự động tin cậy |
| Missing | Request không có header origin | Đánh giá theo method, loại client và policy của endpoint |
| Malformed | Giá trị không parse được hoặc có định dạng không hợp lệ | Ghi sự kiện có kiểm soát, tránh parser crash và không đưa vào allowlist |
| Unsupported scheme | Origin parse được nhưng không dùng scheme web được endpoint hỗ trợ | Ghi riêng và đối chiếu hợp đồng endpoint; không tự động đưa vào allowlist |

Ví dụ minh họa chuẩn hóa ở phía server bằng JavaScript:

```js
function normalizeOrigin(value) {
  if (typeof value !== "string") return { kind: "missing" };
  if (value === "null") return { kind: "opaque" };

  try {
    const url = new URL(value);
    if (url.origin === "null") return { kind: "opaque" };
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { kind: "unsupported_scheme", scheme: url.protocol };
    }

    // Header Origin chuẩn chỉ biểu diễn origin, không có path/query/fragment.
    if (url.origin !== value) return { kind: "malformed" };

    return {
      kind: "origin",
      scheme: url.protocol.slice(0, -1),
      host: url.hostname.toLowerCase(),
      port: url.port || (url.protocol === "https:" ? "443" : "80"),
      canonical: url.origin
    };
  } catch {
    return { kind: "malformed" };
  }
}
```

Đây là ví dụ cho header `Origin` chuẩn trong môi trường server JavaScript. Nếu framework đã parse header, hãy dùng parser chuẩn của framework và kiểm tra cách nó xử lý nhiều giá trị, IPv6, IDN và port mặc định. Không chấp nhận chuỗi URL có path như một origin hợp lệ. Giá trị `null`, thiếu và sai định dạng phải là các trạng thái khác nhau trong telemetry.

Danh sách origin hợp lệ nên là cấu hình được quản trị theo môi trường, tenant và chức năng. Khi thêm partner, ghi nhận người phê duyệt, mục đích, route được phép, loại credentials, ngày bắt đầu và ngày hết hạn. Không tự động thêm origin mới vào allowlist chỉ vì nó xuất hiện nhiều lần trong log.

## Xây dựng baseline hành vi

Baseline mô tả nguồn và cách sử dụng origin bình thường. Baseline nên phân chia theo ứng dụng, môi trường, route, tenant, method và loại client; một danh sách toàn cục thường quá thô.

Ví dụ một ứng dụng có thể có:

- Trang quản trị chỉ được mở từ origin chính và portal nội bộ.
- API public được đọc từ một số website đối tác qua CORS không credentials.
- API tài khoản yêu cầu session cookie, CSRF token và chỉ chấp nhận request theo luồng ứng dụng đã đăng ký.
- Callback đăng nhập có thể đến từ identity provider đã được cấu hình.
- Webhook server-to-server không dùng browser origin làm cơ chế xác thực.

Với mỗi route, ghi nhận origin dự kiến, method, loại xác thực, yêu cầu credentials, CORS policy, CSRF policy và Fetch Metadata được mong đợi. Phân biệt endpoint dành cho browser với endpoint dành cho server-to-server. Không yêu cầu `Origin` phải tồn tại trên mọi request API vì một số client hợp lệ không gửi header này.

### Các chỉ số baseline

- Số origin duy nhất theo route và theo tenant trong một khoảng thời gian.
- Tỷ lệ request từ origin đã biết, mới, bị từ chối, `null`, thiếu hoặc sai định dạng.
- Tỷ lệ CORS allow/deny và số preflight `OPTIONS`.
- Tỷ lệ CSRF validation fail theo route và loại session.
- Phân bố `Sec-Fetch-Site`, `Sec-Fetch-Mode` và `Sec-Fetch-Dest`.
- Số CSP report theo directive và `blocked-uri` đã được chuẩn hóa.
- Số request có credentials từ origin ngoài danh sách đã phê duyệt.
- Tần suất origin mới theo thời gian, tenant và user-agent family.

Baseline cần được cập nhật có kiểm soát khi sản phẩm thêm portal, CDN, identity provider hoặc payment provider. Mỗi thay đổi phải có người chịu trách nhiệm và bằng chứng kiểm thử. Nếu tự động học baseline mà không review, kẻ tấn công có thể làm nhiễm baseline bằng cách tạo lưu lượng bất thường kéo dài.

## Dấu hiệu unusual origin cần theo dõi

### Origin mới trên endpoint nhạy cảm

Một origin chưa từng xuất hiện gửi request tới API tài khoản, quản trị, dữ liệu cá nhân hoặc thao tác thay đổi trạng thái cần được xem xét. Mức độ nghiêm trọng tăng khi request có session cookie, credentials, dữ liệu nhạy cảm hoặc được chấp nhận bởi CORS policy.

Origin mới trên endpoint public chỉ đọc dữ liệu có thể là tích hợp hợp lệ hoặc bot. Cần kiểm tra nội dung response và chính sách CORS trước khi nâng mức cảnh báo.

### Origin ngoài allowlist hoặc CORS reflection

Các dấu hiệu cần điều tra:

- Server phản chiếu nguyên giá trị `Origin` vào `Access-Control-Allow-Origin` mà không kiểm tra allowlist.
- Response chứa `Access-Control-Allow-Credentials: true` cho origin không được phê duyệt.
- Một origin mới được phép đọc response của endpoint trả dữ liệu theo session.
- Allowlist dùng wildcard hoặc kiểm tra chuỗi con dẫn tới chấp nhận host giả mạo.
- Cấu hình CORS thay đổi đột ngột sau một lần deploy hoặc thay đổi gateway.

Một request bị CORS từ chối vẫn có thể đã tới server và có thể đã được xử lý nếu endpoint có tác dụng phụ hoặc request không cần preflight. Vì vậy, hãy kiểm tra application log và trạng thái nghiệp vụ, không suy luận chỉ từ lỗi CORS ở Console.

### Origin `null` hoặc thiếu origin trong ngữ cảnh bất thường

`Origin: null` có thể xuất hiện từ opaque origin, tài liệu sandbox, `data:` hoặc một số ngữ cảnh đặc biệt. Nó không tự động là tấn công, nhưng cần được phân loại riêng. Nếu endpoint nhạy cảm nhận request có cookie và `Origin: null` mà vẫn thực hiện thay đổi trạng thái, hãy kiểm tra token, Fetch Metadata và policy server.

Header `Origin` bị thiếu cũng không tự động là đáng ngờ. Một số navigation, GET hoặc client API hợp lệ không gửi header này. Tập trung vào endpoint và loại request mà policy yêu cầu origin validation.

### Scheme, host hoặc port bất thường

Các mẫu cần theo dõi gồm:

- Request từ `http` tới ứng dụng yêu cầu HTTPS.
- Origin dùng port không thuộc danh mục triển khai.
- Hostname có dạng gần giống domain chính, ký tự Unicode/punycode gây nhầm lẫn hoặc subdomain mới.
- Origin trỏ tới môi trường staging/dev trong khi request mang session production.
- Origin thay đổi liên tục trong một session hoặc một tenant.

Không dùng danh sách port phổ biến để kết luận độc hại. Ứng dụng doanh nghiệp có thể dùng port tùy chỉnh. So sánh với cấu hình triển khai đã phê duyệt và xem xét cả proxy, reverse proxy cùng public URL thực tế.

### Mâu thuẫn giữa origin và Fetch Metadata

Một request khai báo origin lạ nhưng có `Sec-Fetch-Site: same-origin` có thể cho thấy parser, proxy hoặc telemetry đang ghi sai ngữ cảnh; cũng có thể là client không phải trình duyệt giả mạo header. Tương tự, request từ subdomain cùng site có thể có `Sec-Fetch-Site: same-site` dù origin khác nhau.

Hãy kiểm tra scheme/host/port, URL đích, route, redirect và các header cùng thời điểm. Không kỳ vọng `Origin`, `Referer` và Fetch Metadata luôn xuất hiện hoặc luôn giống nhau; mỗi header có quy tắc gửi riêng.

### Tăng đột biến và hành vi dò quét

Một origin mới gửi nhiều request tới nhiều route, nhiều tenant hoặc nhiều ID tài nguyên trong thời gian ngắn có thể là dấu hiệu quét hoặc tự động hóa. Tăng đột biến CORS deny, CSRF failure, preflight hoặc CSP violation cũng có thể phản ánh một release sai cấu hình.

Kết hợp số lượng với danh tính phiên đã được xác minh, rate, phân bố route, status, user-agent family và kết quả business. Tránh cảnh báo chỉ vì một IP có nhiều origin; NAT, proxy doanh nghiệp và privacy relay có thể khiến nhiều người dùng chia sẻ địa chỉ mạng.

## Thiết kế log sự kiện origin

Một sự kiện hữu ích nên có đủ ngữ cảnh để điều tra nhưng không lưu bí mật. Ví dụ schema:

```json
{
  "timestamp": "2026-11-22T09:00:00Z",
  "event": "origin_policy_decision",
  "request_id": "req-test-001",
  "service": "account-api",
  "environment": "production",
  "route": "/api/account/email",
  "method": "PATCH",
  "status": 403,
  "origin_kind": "origin",
  "origin": "https://portal.example.test",
  "origin_class": "new_observed",
  "fetch_site": "cross-site",
  "cors_decision": "deny",
  "csrf_decision": "missing_token",
  "auth_state": "authenticated",
  "tenant_ref": "tenant-pseudonymous-17"
}
```

Giá trị trong ví dụ là dữ liệu giả lập. `request_id` cần được tạo hoặc xác nhận theo quy tắc nội bộ; `tenant_ref` nên là định danh giả danh khi có thể. Không ghi `Cookie`, `Authorization`, CSRF token, request body, email, tên người dùng hoặc toàn bộ query string vào event này.

Nên ghi riêng:

- `origin_kind`: `origin`, `opaque`, `missing`, `malformed` hoặc `unsupported_scheme`.
- `origin_class`: `known_allowed`, `known_partner`, `new_observed`, `explicitly_denied`.
- `cors_decision` và `csrf_decision`: quyết định thực tế cùng lý do có kiểm soát.
- `fetch_site`, `fetch_mode`, `fetch_dest`: giá trị header nếu có.
- `route`: route template thay vì URL chứa ID hoặc dữ liệu người dùng.
- `auth_state`: trạng thái xác thực tổng quát, không phải credential.
- `request_id`/trace ID: dùng để nối event giữa proxy và ứng dụng.

Giới hạn độ dài của origin, route và header; chuẩn hóa ký tự điều khiển để ngăn log injection. Nếu cần lưu Referer, thường chỉ cần origin của nó; tránh lưu path/query trừ khi có nhu cầu điều tra được phê duyệt. Áp dụng quyền truy cập, mã hóa, retention và audit cho hệ thống log.

## Phát hiện và cảnh báo

Một cảnh báo nên dựa trên tổ hợp điều kiện, mức độ nhạy cảm của route và kết quả thực tế. Không phát cảnh báo nghiêm trọng cho mọi origin mới vì sẽ tạo quá nhiều false positive.

### Ví dụ quy tắc phát hiện

| Quy tắc | Điều kiện gợi ý | Mức ưu tiên ban đầu |
|---|---|---|
| New origin on sensitive route | Origin chưa biết truy cập route tài khoản/quản trị hoặc dữ liệu nhạy cảm | Cao |
| Unapproved credentialed CORS | Origin không được phê duyệt được trả response CORS có credentials và dữ liệu được expose | Nghiêm trọng |
| Origin null on state change | `Origin: null` trên request thay đổi trạng thái có session cookie, token thiếu hoặc policy bất thường | Cao |
| CORS reflection | `Access-Control-Allow-Origin` khớp tùy ý với origin request thay vì allowlist | Nghiêm trọng nếu có dữ liệu nhạy cảm/credentials |
| Scheme/port drift | Origin mới dùng HTTP hoặc port ngoài cấu hình | Trung bình đến cao tùy endpoint |
| Fetch Metadata mismatch | Tổ hợp origin và `Sec-Fetch-Site` không phù hợp với route/client đã biết | Trung bình; cần xác minh |
| Origin burst | Một origin mới tăng nhanh trên nhiều route hoặc tenant | Trung bình đến cao |
| CSP source spike | Nhiều report mới từ host không có trong policy hoặc không thuộc release | Trung bình; tăng nếu trùng với script execution bất thường |

Mức ưu tiên chỉ là điểm bắt đầu. Nếu phát hiện CORS misconfiguration nhưng response không chứa dữ liệu nhạy cảm và không dùng credentials, tác động có thể thấp hơn. Ngược lại, nếu origin lạ đọc được response chứa dữ liệu theo session, cần xử lý như sự cố bảo mật.

### Truy vấn phát hiện minh họa

Truy vấn giả định hệ thống log có bảng `origin_events` và các trường trong schema ví dụ:

```sql
SELECT
  service,
  route,
  origin,
  COUNT(*) AS request_count,
  COUNT(DISTINCT request_id) AS distinct_requests
FROM origin_events
WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
  AND origin_class IN ('new_observed', 'explicitly_denied')
  AND route IN ('/api/account/email', '/api/admin/settings')
GROUP BY service, route, origin
HAVING COUNT(*) >= 5
ORDER BY request_count DESC;
```

Đây là SQL tổng quát; cú pháp thời gian và tên bảng cần điều chỉnh theo nền tảng SIEM/data warehouse. Ngưỡng `5` chỉ minh họa. Trong production, hiệu chỉnh theo lưu lượng nền, tenant, route, thời gian và mức độ nhạy cảm. Với một request duy nhất có dấu hiệu CORS credential reflection, không nên đợi đủ ngưỡng số lượng mới điều tra.

### Giảm false positive

- Đăng ký origin hợp lệ của SSO, thanh toán, portal, CDN và môi trường preview theo từng route.
- Gắn thời gian hết hạn và chủ sở hữu cho ngoại lệ allowlist.
- Phân biệt request browser với service-to-service và webhook.
- Tách `same-site` khỏi `same-origin`; subdomain khác origin vẫn có thể là same-site.
- Không xem `Origin: null` hoặc header thiếu là độc hại nếu chưa xét ngữ cảnh.
- Nhóm cảnh báo theo request ID, session pseudonymous, route và cửa sổ thời gian để tránh lặp.
- Theo dõi release/deploy để nhận biết lỗi cấu hình mới xuất hiện.
- Review định kỳ các origin đã biết; gỡ quyền khi tích hợp ngừng sử dụng.

## Dashboard giám sát

Một dashboard hữu ích có thể gồm các phần:

1. **Origin inventory:** số origin đã biết, mới, bị từ chối, opaque và malformed theo service.
2. **Policy decisions:** CORS allow/deny và CSRF pass/fail theo route.
3. **Sensitive routes:** request từ origin mới tới API tài khoản, quản trị và thao tác thay đổi trạng thái.
4. **Fetch Metadata:** phân bố `same-origin`, `same-site`, `cross-site`, `none` và giá trị thiếu.
5. **CSP reports:** directive, blocked host đã chuẩn hóa và thay đổi theo release.
6. **Trend:** tần suất origin mới, port/scheme drift và đột biến theo tenant.
7. **Integration health:** lỗi của partner đã được phê duyệt và thời điểm hết hạn allowlist.

Dashboard nên cho phép drill down từ số liệu tổng hợp tới event có request ID, nhưng chỉ người có quyền mới xem được chi tiết. Không hiển thị cookie, token, body hoặc full Referer. Nếu origin chứa hostname nội bộ hoặc tenant-specific, giới hạn người xem theo phân loại dữ liệu.

## Quy trình triage cảnh báo unusual origin

Khi nhận cảnh báo, tiến hành theo thứ tự để xác định tín hiệu, phạm vi và tác động:

1. **Xác nhận event:** kiểm tra timestamp, service, route, method, request ID và dữ liệu đã được chuẩn hóa.
2. **Xác định origin:** so sánh scheme, host, port với danh mục tích hợp; kiểm tra IDN, port mặc định, `null`, thiếu hoặc malformed.
3. **Xem ngữ cảnh request:** xác định browser hay client khác, `Sec-Fetch-Site`, Referer origin, redirect chain và loại nội dung.
4. **Kiểm tra xác thực:** request có session hợp lệ không, có credentials không, principal/tenant nào bị ảnh hưởng; không đọc hoặc chia sẻ token thô.
5. **Đối chiếu policy:** CORS decision, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, CSRF decision, cookie `SameSite` và Fetch Metadata policy.
6. **Xác minh tác động:** request có tới application không, response có được expose không và trạng thái nghiệp vụ có thay đổi không.
7. **Tìm tương quan:** kiểm tra request cùng session pseudonymous, route liên quan, CSP report, WAF event và thay đổi cấu hình gần thời điểm đó.
8. **Phân loại:** tích hợp hợp lệ, cấu hình sai, hoạt động tự động, hành vi đáng ngờ hoặc sự cố đã xác nhận.
9. **Hành động:** sửa allowlist/CORS, chặn request theo policy, thu hồi tích hợp hoặc kích hoạt quy trình incident response tùy tác động.
10. **Ghi kết quả:** lưu bằng chứng tối thiểu, người xử lý, quyết định, phạm vi và bước theo dõi.

Không chặn toàn bộ cross-origin request chỉ vì có origin lạ. Một hành động chặn diện rộng có thể làm gián đoạn SSO, thanh toán hoặc tích hợp hợp lệ. Nếu có bằng chứng origin không được phép đọc dữ liệu nhạy cảm với credentials, ưu tiên vô hiệu hóa quyền CORS sai, thu hẹp allowlist và đánh giá dữ liệu có thể đã bị lộ.

## Ứng phó khi xác nhận sự cố

Khi xác nhận có origin không được phép truy cập dữ liệu hoặc thực hiện thao tác nhạy cảm:

- Thu hẹp hoặc gỡ origin khỏi CORS allowlist ở đúng service/route.
- Tắt credentialed CORS nếu chức năng không cần thiết; kiểm tra `Access-Control-Allow-Origin` không phản chiếu tùy ý.
- Đảm bảo endpoint thay đổi trạng thái có CSRF protection và kiểm tra quyền phía server.
- Nếu subdomain bị chiếm quyền, cô lập subdomain và đánh giá cookie `Domain`, session cùng các ứng dụng cùng site.
- Kiểm tra access log và audit log để xác định dữ liệu hoặc thao tác bị ảnh hưởng.
- Xoay vòng session/credential nếu có căn cứ rằng thông tin xác thực đã bị lộ; không xoay vòng đại trà khi chưa đánh giá tác động và quy trình.
- Lưu cấu hình trước/sau, thời điểm thay đổi, request ID và kết quả xác minh sau khắc phục.
- Theo dõi tái diễn và cập nhật baseline sau khi sự cố được xử lý.

Nếu phát hiện đến từ CSP report hoặc client telemetry, xác minh ở server trước khi kết luận có truy cập thành công. Report chỉ cho biết trình duyệt ghi nhận một hành vi vi phạm policy; nó không chứng minh dữ liệu đã bị đọc hoặc gửi ra ngoài.

## Kiểm thử giám sát trong môi trường lab

Tạo một ứng dụng thử nghiệm có các origin:

- `https://app.example.test`: API chính.
- `https://portal.example.test`: origin được cho phép đọc một endpoint public.
- `https://unknown.test`: origin chưa được đăng ký.
- `https://evil.example.test`: subdomain cùng site nhưng khác origin.

Thực hiện các tình huống sau bằng tài khoản giả lập:

1. Request cùng origin hợp lệ tới API tài khoản.
2. Request từ portal được phê duyệt tới endpoint public.
3. Request từ `unknown.test` tới endpoint public và endpoint nhạy cảm.
4. Request từ `evil.example.test` tới endpoint dùng session cookie.
5. Request có `Origin: null` hoặc thiếu header trong client test phù hợp.
6. Request với scheme/port không thuộc cấu hình.
7. Thử nghiệm CORS allowlist và xác minh server ghi đúng quyết định allow/deny.
8. Gửi CSP report giả lập có host mới và xác nhận endpoint report giới hạn kích thước, rate và schema.

Với mỗi ca, xác nhận event có route, method, origin class, Fetch Metadata, CORS/CSRF decision và request ID. Kiểm tra dashboard phân nhóm đúng và cảnh báo không bị lặp quá mức. Sau đó xóa dữ liệu thử nghiệm và hoàn nguyên cấu hình lab.

Ví dụ tạo request có header Origin tùy chỉnh bằng curl:

```bash
curl -i \
  -H "Origin: https://unknown.test" \
  https://app.example.test/api/public-info
```

Lệnh này chỉ mô phỏng header do client gửi; nó không tái tạo đầy đủ hành vi cookie, SOP, CORS hay Fetch Metadata của trình duyệt. Một client tùy ý có thể đặt header `Origin`, do đó kết quả phải được đối chiếu với log và browser test thật. Chỉ chạy trên host lab do bạn kiểm soát.

## Bảo vệ dữ liệu giám sát

Origin và Referer có thể tiết lộ tên tenant, hệ thống nội bộ, môi trường triển khai hoặc đối tác. Log cũng có thể trở thành mục tiêu để tìm cấu trúc ứng dụng. Áp dụng nguyên tắc tối thiểu:

- Chỉ thu thập header cần thiết cho quyết định và điều tra.
- Ưu tiên lưu origin của Referer thay vì toàn bộ URL; loại bỏ query và fragment.
- Không ghi cookie, `Authorization`, CSRF token, request body hoặc dữ liệu cá nhân.
- Giới hạn độ dài và chuẩn hóa ký tự điều khiển trước khi ghi log.
- Rate limit CSP/report endpoint và giới hạn kích thước body.
- Phân quyền dashboard, mã hóa log khi lưu/truyền và đặt thời hạn retention.
- Audit thao tác tìm kiếm, export và chia sẻ log.
- Dùng dữ liệu giả lập trong tài liệu, ticket và bài thực hành.

Nếu cần liên kết nhiều request của cùng một phiên, dùng mã tương quan hoặc định danh giả danh được quản lý. Không tạo fingerprint người dùng quá mức chỉ để phát hiện origin mới.

## Thực hành

Trong môi trường QA, lập baseline cho một API đọc hồ sơ và một API thay đổi email. Đăng ký `portal.example.test` làm origin được phép đọc API public; không cho origin này truy cập API thay đổi email nếu thiết kế không yêu cầu.

Thực hiện:

1. Gửi request hợp lệ từ ứng dụng chính và ghi nhận event chuẩn.
2. Gửi request từ portal tới API public; xác nhận CORS cho phép và event được phân loại `known_partner`.
3. Gửi request từ `unknown.test` tới hai endpoint; xác nhận log phân loại `new_observed` và ghi quyết định policy.
4. Gửi request từ subdomain cùng site nhưng khác origin; kiểm tra `Sec-Fetch-Site` và policy không nhầm `same-site` với `same-origin`.
5. Mô phỏng `Origin: null`, header thiếu và origin sai định dạng; xác nhận chúng được phân loại riêng.
6. Tạo một cảnh báo cho origin mới truy cập route nhạy cảm và kiểm tra quy trình triage.
7. Xác minh dashboard không hiển thị cookie, token, full Referer hoặc body.

Viết một báo cáo ngắn nêu baseline, rule phát hiện, ngưỡng đã chọn, false positive dự kiến, bằng chứng và hành động xử lý. Chỉ sử dụng tài khoản và dữ liệu giả lập.

## Ghi nhớ

- Origin lạ là tín hiệu cần ngữ cảnh, không tự động là một cuộc tấn công.
- Chuẩn hóa scheme, host và port; phân biệt origin cụ thể, `null`, thiếu và sai định dạng.
- Kết hợp Origin với route, method, xác thực, credentials, Fetch Metadata, CORS và CSRF decision.
- CORS deny không chứng minh request chưa tới server hoặc không gây tác dụng phụ.
- Header Origin có thể bị client không phải trình duyệt giả mạo; không dùng nó làm cơ chế xác thực.
- Baseline và allowlist cần có chủ sở hữu, phạm vi route và thời hạn review.
- Log đủ để điều tra nhưng không lưu cookie, token, body hoặc URL chứa dữ liệu nhạy cảm.
- Xác minh tác động thực tế trước khi chặn tích hợp hoặc xử lý như incident.
