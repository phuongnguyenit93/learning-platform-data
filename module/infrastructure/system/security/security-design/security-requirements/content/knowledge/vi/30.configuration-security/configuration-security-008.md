# CORS configuration

## 1. CORS cần được đặc tả như một quan hệ tin cậy

Trong chương **Configuration security**, cấu hình Cross-Origin Resource Sharing (CORS) xác định website nào được trình duyệt cho phép đọc phản hồi từ một origin khác. Đối với API có dữ liệu nhạy cảm, cho phép một origin đồng nghĩa chấp nhận code chạy tại origin đó tiếp cận những phản hồi thuộc phạm vi được chia sẻ.

Câu “bật CORS để frontend gọi API” còn thiếu các quyết định quan trọng: frontend nào, API nào, dữ liệu nào, có cookie hay không, method và header nào cần thiết, ai được đổi policy và làm sao thu hồi quyền chia sẻ.

Trong module yêu cầu bảo mật, mục tiêu là chuyển những quyết định ấy thành hợp đồng có thể triển khai và kiểm chứng:

**Nhu cầu tích hợp trình duyệt → rủi ro chia sẻ dữ liệu → policy có phạm vi → yêu cầu quan sát được → kiểm thử qua trình duyệt và hệ thống thật.**

Sau bài học, người học có thể:

- Phân biệt origin với hostname, URL, site và danh tính người dùng.
- Giải thích vai trò của preflight và giới hạn bảo vệ của CORS.
- Đặc tả allowlist, credentials, method, request header và response header.
- Kiểm soát nguồn cấu hình, cache, proxy, thay đổi policy và thu hồi.
- Liên kết yêu cầu CORS với xác thực, phân quyền, bảo vệ dữ liệu, CSRF và bằng chứng vận hành.

Các route, domain, thời hạn, ID và schema trong bài là ví dụ thiết kế. Chúng không phải cấu hình của một framework cụ thể hoặc giá trị an toàn chung cho mọi hệ thống.

## 2. Hiểu đúng origin và ranh giới bảo vệ

### 2.1. Origin không phải chỉ là tên miền

Đối với URL HTTP(S), origin được xác định bởi scheme, hostname và port hiệu lực. Path không tạo origin mới. Ví dụ, `https://workspace.example.invalid/home` và `https://workspace.example.invalid/settings` cùng origin; đổi sang HTTP, hostname khác hoặc port 8443 tạo origin khác. Port mặc định được xử lý theo quy tắc URL, không bằng suy đoán chuỗi. [MDN: Origin](https://developer.mozilla.org/en-US/docs/Glossary/Origin)

Trong bài, origin frontend được biểu diễn chuẩn là:

```text
https://workspace.example.invalid
```

Hợp đồng allowlist của ví dụ chỉ nhận biểu diễn origin chuẩn, không nhận URL có path, query, fragment, user information hoặc dấu slash cuối. Dữ liệu cấu hình phải được parse và kiểm tra bằng quy tắc URL phù hợp; không dùng phép tìm chuỗi để quyết định tin cậy.

| Giá trị cấu hình hoặc đầu vào thử | Quyết định của baseline minh họa |
|---|---|
| `https://workspace.example.invalid` | Có thể chấp nhận nếu nằm trong policy của route |
| `https://workspace.example.invalid:8443` | Origin riêng, cần được cấp rõ |
| `http://workspace.example.invalid` | Không nằm trong baseline HTTPS production |
| `https://workspace.example.invalid/path` | Từ chối khi nhập allowlist vì có path |
| `https://workspace.example.invalid.attacker.invalid` | Không khớp origin được cấp |
| `https://attacker-workspace.example.invalid` | Không khớp origin được cấp |
| `null` | Không được cấp trong baseline này |

Một số ngữ cảnh có opaque origin được trình duyệt biểu diễn thành `null`; nó không định danh duy nhất một website đáng tin cậy. Vì thế, “cho phép null để hỗ trợ một trường hợp đặc biệt” có thể vô tình bao phủ những ngữ cảnh khác. [MDN: Opaque origin](https://developer.mozilla.org/en-US/docs/Glossary/Origin#opaque_origin)

Không dùng allowlist origin để phân chia quyền giữa hai ứng dụng cùng scheme, host và port nhưng khác path. Nếu cần ranh giới trình duyệt giữa chúng, kiến trúc phải xem xét origin riêng và các kiểm soát ứng dụng tương ứng.

### 2.2. CORS không thay thế kiểm soát truy cập của máy chủ

CORS được trình duyệt thực thi đối với việc chia sẻ phản hồi cho script. Client ngoài trình duyệt có thể tự đặt `Origin`; giá trị đó không chứng minh người dùng hay hệ thống gọi API đã được xác thực. Một form POST còn có thể được gửi mà không cần preflight, nên việc script không đọc được phản hồi không chứng minh thao tác chưa xảy ra. [OWASP: Phạm vi bảo vệ của CORS](https://cheatsheetseries.owasp.org/cheatsheets/CORS_Security_Cheat_Sheet.html#what-cors-does-and-doesnt-protect)

Do đó, đặc tả của API tài liệu trong bài phải tách bốn quyết định:

| Quyết định | Câu hỏi |
|---|---|
| Xác thực | Chủ thể gọi API là ai và bằng chứng có hợp lệ không? |
| Phân quyền | Chủ thể có quyền thực hiện hành động trên tài liệu và tenant này không? |
| Chống CSRF | Với quyền tự động đi kèm trình duyệt như cookie, request thay đổi trạng thái có đúng ý định được chấp nhận không? |
| Chia sẻ qua CORS | Script tại origin này có được đọc phản hồi của route không? |

Origin hợp lệ không tạo quyền đọc mọi tenant. Token hợp lệ cũng không đồng nghĩa mọi website đều được phép nhận phản hồi trong ngữ cảnh trình duyệt.

## 3. Hiểu luồng CORS để viết tiêu chí đúng

### 3.1. Request thực và preflight có trách nhiệm khác nhau

Với một số request, trình duyệt gửi preflight bằng `OPTIONS`, kèm `Origin`, `Access-Control-Request-Method` và có thể có `Access-Control-Request-Headers`. Theo Fetch, preflight không mang credentials của request cross-origin tiếp theo. Phản hồi preflight cung cấp thông tin CORS; nó không phải kết quả xác thực hay phân quyền cho thao tác nghiệp vụ. [Fetch Standard: CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol)

Ví dụ ứng dụng muốn tạo tài liệu bằng JSON và một CSRF token header:

```text
Trình duyệt tại origin frontend
    -> OPTIONS: có được POST với Content-Type và X-CSRF-Token không?
Máy chủ
    -> Trả quyết định CORS theo route và policy hiện hành
Trình duyệt
    -> Nếu preflight thành công, gửi POST thực
Máy chủ
    -> Kiểm tra session, quyền, CSRF và dữ liệu nghiệp vụ
    -> Trả phản hồi với CORS phù hợp
```

Một số request không cần preflight, và preflight đã thành công có thể được cache. Vì vậy không được đặt kiểm tra quyền hoặc chống tác dụng phụ chỉ trong bộ xử lý `OPTIONS`.

Không coi mọi request OPTIONS là preflight. Bộ xử lý cần nhận diện đúng Origin và Access-Control-Request-Method, kiểm tra tài nguyên đích và áp dụng cận tài nguyên thích hợp. Việc trả lời preflight không cần session không tạo một đường bỏ qua kiểm soát cho mọi request OPTIONS thông thường.

### 3.2. Credentials cần một quyết định riêng

Khi request có credentials mode `include`, để chia sẻ phản hồi, `Access-Control-Allow-Origin` phải là origin cụ thể và `Access-Control-Allow-Credentials` phải có giá trị `true`. Origin dạng `*` không đáp ứng trường hợp này; giá trị `true` phân biệt hoa thường. [Fetch Standard: CORS protocol and credentials](https://fetch.spec.whatwg.org/#cors-protocol-and-credentials)

Việc cookie có thực sự được gửi còn phụ thuộc chế độ request và chính sách cookie/trình duyệt. CORS không tự tạo cookie, không bỏ qua giới hạn cookie và không sửa một cấu hình session không phù hợp. Hai host khác origin cũng có thể vẫn cùng site, nên không suy ra mọi tích hợp CORS đều cần cùng một giá trị SameSite. [MDN: CORS và credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#requests_with_credentials)

Một bearer token do code gắn trong `Authorization` cần được phân tích riêng với cookie tự đi kèm. Không suy ra phải bật `allowCredentials` chỉ từ việc tên header này xuất hiện.

### 3.3. Các nhóm header giải quyết những việc khác nhau

| Nhóm | Ví dụ trong bài | Ý nghĩa cần đặc tả |
|---|---|---|
| Origin được chia sẻ | `Access-Control-Allow-Origin` | Một origin được chấp nhận, hoặc wildcard trong profile dữ liệu thật sự công khai |
| Chia sẻ khi credentials mode là include | `Access-Control-Allow-Credentials` | Chỉ bật cho profile cần thiết |
| Method được thông báo qua preflight | `Access-Control-Allow-Methods` | Những method cần cho route/profile; không thay phân quyền method tại server |
| Request header được thông báo qua preflight | `Access-Control-Allow-Headers` | Những header không thuộc phần được trình duyệt cho phép sẵn mà ứng dụng cần gửi |
| Response header được script đọc thêm | `Access-Control-Expose-Headers` | Những header ngoài nhóm được đọc mặc định mà frontend cần dùng |
| Thời gian cache kết quả preflight | `Access-Control-Max-Age` | Khoảng thời gian công bố cho thông tin preflight, tính bằng giây |

`Authorization` phải được liệt kê rõ khi cần cho CORS; wildcard của allow-headers không bao phủ nó. Trong baseline của bài, mọi request header bổ sung đều được liệt kê tường minh. [MDN: Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers)

`Access-Control-Expose-Headers` điều khiển header phản hồi nào script được đọc thêm; nó không điều khiển việc gửi request header. Ví dụ, có thể expose `X-Request-Id` để hỗ trợ đối chiếu lỗi mà không công bố header chẩn đoán nội bộ. [MDN: Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers)

## 4. Bắt đầu từ nhu cầu tích hợp và các rủi ro

Xét dịch vụ tài liệu đa tenant với các thành phần:

- Frontend người dùng: `https://workspace.example.invalid`.
- Frontend quản trị: `https://console.example.invalid`.
- API: `https://documents-api.example.invalid`.
- Một nhóm route công bố danh mục công khai, có cùng nội dung cho mọi người.
- Client ngoài trình duyệt dùng cơ chế xác thực riêng.

Các domain là dữ liệu minh họa. Kiểm thử thực tế phải cung cấp các origin kiểm soát được và kết nối HTTPS phù hợp.

| Mã rủi ro | Tình huống | Tác động cần ngăn |
|---|---|---|
| R-CORS-01 | Phản chiếu mọi Origin kết hợp chia sẻ có cookie | Website không được cấp đọc phản hồi nhạy cảm của người dùng |
| R-CORS-02 | So khớp origin bằng prefix, substring hoặc pattern quá rộng | Host do bên khác kiểm soát được nhận quyền chia sẻ |
| R-CORS-03 | Dùng kết quả CORS thay xác thực hoặc quyền tài nguyên | Truy cập trái phép bằng client trực tiếp hoặc sai tenant |
| R-CORS-04 | Chỉ dựa vào việc trình duyệt chặn phản hồi để chống CSRF | Thao tác vẫn xảy ra dù script không đọc được kết quả |
| R-CORS-05 | Proxy, cache và ứng dụng dùng policy khác nhau | Phản hồi hoặc header đi sai phạm vi, gây lộ dữ liệu hay gián đoạn |
| R-CORS-06 | Allowlist không được quản lý vòng đời | Domain hết quyền kiểm soát hoặc frontend bị xâm nhập vẫn được tin cậy |
| R-CORS-07 | Rollback hay instance cũ giữ policy đã thu hồi | Quyền chia sẻ tồn tại quá thời hạn được chấp nhận |

Mỗi origin được cấp nên có chủ sở hữu, mục đích, route cần dùng, dữ liệu được chia sẻ và bằng chứng quyền kiểm soát domain. Một host do đối tác vận hành cần được đánh giá như một quan hệ tin cậy riêng.

Ngay cả khi so khớp chính xác, website được cấp bị XSS hoặc mất quyền kiểm soát vẫn có thể gây rủi ro. CORS không đánh giá từng đoạn script tại origin đó; quản trị allowlist phải gắn với quản trị rủi ro frontend.

## 5. Định nghĩa policy theo route và mô hình xác thực

Một global policy rộng thường che khuất những luồng có mức tin cậy khác nhau. Ví dụ của bài dùng các profile sau:

| Nhóm route | Origin được đọc | Credentials mode của luồng dự kiến | Method nghiệp vụ | Kiểm soát bổ sung |
|---|---|---|---|---|
| Documents | Chỉ workspace | `include` với session cookie | GET, POST, DELETE | Xác thực, quyền theo tenant/tài liệu; thao tác thay đổi trạng thái cần kiểm tra Origin và CSRF token |
| Administration | Chỉ console | `include` với session cookie quản trị | GET, POST | Quyền quản trị riêng, chống CSRF, audit thao tác nhạy cảm |
| Public catalog | Mọi origin | `omit` | GET | Dữ liệu thật sự công khai, không cá nhân hóa theo session hoặc vị trí mạng |
| Operations | Không cấp CORS | Không có tích hợp script cross-origin trong ví dụ | Theo hợp đồng vận hành riêng | Xác thực và phân quyền vận hành, giới hạn đường truy cập |
| Native integration | Không cần cấp CORS cho client ngoài trình duyệt | Theo cơ chế client riêng | Theo API được cấp | Xác thực client và quyền nghiệp vụ độc lập với Origin |

Đây là quyết định thiết kế của tình huống minh họa. Chỉ dùng wildcard cho public catalog sau khi đã chứng minh mọi phản hồi thuộc profile, gồm đường lỗi, không mang dữ liệu theo người dùng hoặc quyền truy cập ngầm.

Frontend quản trị không tự được đọc nhóm Documents nếu không có nhu cầu đã duyệt. Nếu một frontend thật sự cần cả hai nhóm, quyền chia sẻ phải được thêm rõ theo phạm vi; không dùng suy luận “đều là domain của công ty”.

### 5.1. Phân biệt thiếu Origin, Origin không được cấp và null

Trong profile cookie của ví dụ:

- Origin được cấp: tiếp tục đánh giá các kiểm soát còn lại; có thể chia sẻ phản hồi hợp lệ.
- Origin không được cấp hoặc `null`: không cấp CORS; request tới nhóm nhạy cảm bị từ chối trước xử lý nghiệp vụ theo policy server của ví dụ.
- Không có Origin: không tự cấp CORS và không suy ra caller đáng tin; request đọc vẫn cần xác thực, phân quyền.
- Thao tác thay đổi trạng thái dùng cookie: yêu cầu Origin thuộc allowlist và CSRF token hợp lệ; thiếu một điều kiện thì từ chối.
- Client tích hợp có bearer token: đi theo hợp đồng API riêng, không dựa vào giả định rằng thiếu Origin đồng nghĩa client nội bộ.

CORS không bắt buộc mọi server phải trả cùng một HTTP status cho origin bị từ chối. Baseline này chọn `403` cho request có Origin không được cấp tới nhóm nhạy cảm; tiêu chí phải kiểm tra cả không có tác dụng phụ và không có header cho phép chia sẻ.

Với frontend được cấp nhưng session hết hạn, phản hồi `401` có thể mang CORS phù hợp để frontend đọc mã lỗi công khai. Điều đó không cấp quyền nghiệp vụ hoặc cho phép đưa thông tin lỗi nội bộ vào body.

### 5.2. CORS và CSRF phải có tiêu chí độc lập

Ví dụ quy định API thay đổi tài liệu dùng JSON, kiểm tra content type đúng hợp đồng và yêu cầu CSRF token gắn với session. Không nhận thêm dạng form hoặc text chỉ để né lỗi tích hợp.

SameSite và kiểm tra nguồn request có thể tham gia phòng vệ, nhưng cần được thiết kế cùng session và CSRF token. Không dùng câu “không bật CORS cho trang lạ” làm toàn bộ tiêu chí chống CSRF. [OWASP: CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

## 6. Bộ yêu cầu mẫu có thể đo và kiểm chứng

### 6.1. Một yêu cầu đầy đủ

**CORS-01 — Chia sẻ phản hồi Documents theo allowlist chính xác**

- **Rủi ro:** R-CORS-01, R-CORS-02 và R-CORS-06.
- **Phạm vi:** mọi đường phục vụ nhóm route Documents, gồm gateway và đường trực tiếp được hỗ trợ.
- **Đầu vào:** route đã được xác định, Origin hợp lệ về cú pháp và revision policy hiện hành.
- **Yêu cầu:** chỉ origin có trong allowlist của nhóm route mới được nhận quyết định chia sẻ phản hồi.
- **Cách khớp:** so sánh origin chuẩn theo hợp đồng; không khớp bằng substring hoặc tự mở rộng subdomain.
- **Đầu ra:** có tối đa một giá trị `Access-Control-Allow-Origin`, đúng origin đã được chấp nhận, không phải danh sách nhiều origin.
- **Khi không hợp lệ:** không phát sinh header cấp CORS; request nhạy cảm có Origin bị từ chối theo hợp đồng của mục 5.1.
- **Bằng chứng:** policy revision hiệu lực, route/profile được chọn và kiểm thử trình duyệt tại origin được cấp, không được cấp và host đánh lừa phép so khớp.

Không được phản chiếu Origin vào response trước rồi mới kiểm tra. Khi có nhiều origin hợp lệ, server chọn một origin khớp với request; không ghép chúng thành một chuỗi phân tách bằng dấu phẩy trong allow-origin.

### 6.2. Các yêu cầu bổ sung

| ID | Hành vi bắt buộc trong ví dụ | Tiêu chí chấp nhận chính |
|---|---|---|
| CORS-02 | Route chưa có policy chia sẻ không tự nhận policy cho phép toàn cục. | Route mới không có allow-origin; thêm route cần quyết định policy rõ ràng. |
| CORS-03 | Profile cookie chỉ chia sẻ cho origin cụ thể, với credentials được cấp tường minh; cấu hình wildcard kết hợp credentials bị từ chối. | Candidate không hợp lệ không được kích hoạt; request cookie không được chia sẻ qua wildcard. |
| CORS-04 | Preflight được đánh giá theo route, Origin, method dự kiến và tập header dự kiến; không thực hiện nghiệp vụ. | Chấp nhận tổ hợp hợp lệ; từ chối một method hoặc header ngoài policy; số tài liệu và quyền không thay đổi. |
| CORS-05 | Preflight không yêu cầu session cookie hoặc CSRF token của thao tác thực; request thực luôn kiểm tra các điều kiện tương ứng. | Preflight hợp lệ không cần đăng nhập; POST thiếu session, quyền hoặc CSRF vẫn bị từ chối. |
| CORS-06 | Allowed request headers và exposed response headers được liệt kê theo nhu cầu của từng profile. | Header không thuộc hợp đồng không được cấp; expose request ID không công bố header chẩn đoán nội bộ. |
| CORS-07 | Xác thực, quyền tài nguyên và tenant được thực thi độc lập với CORS. | Origin được cấp nhưng sai tenant bị từ chối; client trực tiếp giả Origin cũng không vượt quyền. |
| CORS-08 | Thao tác dùng cookie làm thay đổi trạng thái kiểm tra Origin và CSRF theo hợp đồng của profile. | Form POST từ trang không được cấp không làm thay đổi dữ liệu, bất kể script có đọc được phản hồi hay không. |
| CORS-09 | Header CORS của mọi lớp tạo phản hồi phải nhất quán với một policy có thẩm quyền. | Không có allow-origin trùng, không có wildcard do proxy bổ sung và không có đường lỗi tự mở rộng policy. |
| CORS-10 | Cache phải phân tách các biến thể cần thiết; dữ liệu tài liệu và quản trị trong ví dụ không được shared-cache. | Hai origin, hai session và hai tenant không nhận nhầm body hoặc header; phản hồi nhạy cảm dùng chính sách no-store đã chọn. |
| CORS-11 | Mọi thay đổi allowlist cần quyền quản lý, kiểm tra schema, audit và kích hoạt snapshot nhất quán. | Đầu vào sai hoặc vượt quyền không thay revision; audit có kết quả đã lọc và không chứa token. |
| CORS-12 | Sau thu hồi, mọi request mới vào nhóm bảo vệ sau thời hạn đã cam kết phải được đánh giá bằng policy còn hiệu lực. | Kiểm thử trên mọi điểm phục vụ, cả khi trình duyệt giữ preflight cũ và một instance mất kết nối. |

Các ID là định danh của bài học. Trong dự án, mỗi yêu cầu cần chủ sở hữu, phiên bản, phạm vi ngoại lệ và liên kết tới thiết kế, kiểm thử, bằng chứng vận hành.

## 7. Ví dụ hợp đồng cấu hình và trao đổi HTTP

### 7.1. Cấu hình có phạm vi rõ

Ví dụ dùng schema tự định nghĩa, trong đó route group được bộ định tuyến ánh xạ một cách xác định:

```yaml
schemaVersion: 1
revision: "cors-042"
targetEnvironment: production

cors:
  defaultPolicy: no-cross-origin-sharing
  rejectNullOrigin: true
  preflightMaxAgeSeconds: 300

  profiles:
    documents:
      allowedOrigins:
        - "https://workspace.example.invalid"
      allowCredentials: true
      allowedMethods: [GET, POST, DELETE]
      allowedRequestHeaders: [Content-Type, X-CSRF-Token]
      exposedResponseHeaders: [X-Request-Id]
      rejectUnlistedOriginBeforeBusiness: true
      sensitiveResponseCachePolicy: no-store

    administration:
      allowedOrigins:
        - "https://console.example.invalid"
      allowCredentials: true
      allowedMethods: [GET, POST]
      allowedRequestHeaders: [Content-Type, X-CSRF-Token]
      exposedResponseHeaders: [X-Request-Id]
      rejectUnlistedOriginBeforeBusiness: true
      sensitiveResponseCachePolicy: no-store

    publicCatalog:
      allowedOrigins: ["*"]
      allowCredentials: false
      allowedMethods: [GET]
      allowedRequestHeaders: []
      exposedResponseHeaders: []
      dataClassification: public-identical-for-all

  routeGroups:
    documentResources: documents
    administrationResources: administration
    publicCatalogResources: publicCatalog
    operationsResources: no-cross-origin-sharing
```

Hợp đồng cần quy định thêm:

- Môi trường được đối chiếu với ngữ cảnh deployment đáng tin cậy; đổi field environment không làm giảm baseline.
- Field không biết, khóa trùng, sai kiểu, origin không chuẩn và cận âm bị từ chối.
- `allowedOrigins` rỗng nghĩa là không cấp origin nào, không phải tất cả.
- Profile nhạy cảm thiếu allowlist không được phục vụ bằng một fallback rộng.
- Wildcard chỉ hợp lệ cho profile được phân loại public, không cá nhân hóa và không yêu cầu chia sẻ credentials.
- Cùng một route không được vô tình nhận nhiều profile với các quyền hợp nhất quá rộng.
- Bản cập nhật thay toàn bộ tập origin theo revision được duyệt, không âm thầm giữ lại origin đã bị xóa.
- `preflightMaxAgeSeconds` là cận công bố cho cache preflight, không phải thời hạn session hoặc quyền truy cập tài liệu.

Các policy xác thực, phân quyền và CSRF được đặc tả riêng và luôn áp dụng; file này không tự tạo những kiểm soát ấy.

### 7.2. Preflight hợp lệ

```http
OPTIONS /v1/documents HTTP/1.1
Host: documents-api.example.invalid
Origin: https://workspace.example.invalid
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Phản hồi của profile Documents:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://workspace.example.invalid
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, DELETE
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Max-Age: 300
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Trong ví dụ, proxy được cấu hình không HTTP-cache các phản hồi OPTIONS; trình duyệt vẫn có cơ chế cache preflight riêng theo giao thức. Việc có `Vary` không thay thế cấu hình cache của từng sản phẩm.

Không redirect preflight sang trang đăng nhập trong hợp đồng này. Nếu response không đáp ứng CORS, trình duyệt sẽ không cho luồng tiếp tục như mong muốn; frontend không thể sửa bằng cách tự thêm allow-origin vào request.

### 7.3. Request thực vẫn cần mọi kiểm soát nghiệp vụ

```http
POST /v1/documents HTTP/1.1
Host: documents-api.example.invalid
Origin: https://workspace.example.invalid
Content-Type: application/json
X-CSRF-Token: test-only-placeholder
Cookie: session=test-only-placeholder

{"title":"Báo cáo thử nghiệm"}
```

Sau khi session, CSRF, quyền tenant và dữ liệu đều hợp lệ, một phản hồi minh họa là:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store
Access-Control-Allow-Origin: https://workspace.example.invalid
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-Id
Vary: Origin
X-Request-Id: req-generated-123

{"id":"doc-example-01"}
```

Credential trong ví dụ là placeholder, không dùng để chạy trên hệ thống thật.

Nếu thiếu quyền tạo tài liệu, server vẫn trả lỗi và không tạo tài liệu. Có CORS hợp lệ chỉ làm frontend được cấp đọc phản hồi lỗi công khai đó.

### 7.4. Một profile bearer token có hợp đồng khác

Nếu thiết kế thêm một browser client dùng bearer token với `credentials: "omit"`, request header `Authorization` phải được cấp rõ khi cần. Token luôn được xác thực và kiểm tra quyền tại API.

Một policy có thể dùng origin tường minh, không bật credentials và chỉ cho các method cần thiết. Không tự thay nó bằng wildcard chỉ vì không dùng cookie: token vẫn có thể cho phép đọc dữ liệu nhạy cảm.

`mode: "no-cors"` không phải giải pháp để frontend đọc JSON từ API bị cấu hình sai. Nó tạo các hạn chế khác của Fetch và không cung cấp quyền đọc phản hồi mong muốn. [MDN: CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)

## 8. Cache, proxy và khả năng thu hồi

### 8.1. Phân biệt cache preflight với cache dữ liệu

`Access-Control-Max-Age` chỉ định thời gian cache kết quả preflight; trình duyệt có thể áp dụng cận riêng. Nó không điều khiển cache body tài liệu. [MDN: Access-Control-Max-Age](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Max-Age)

Khi response thay đổi theo Origin, cần phân biệt biến thể bằng `Vary: Origin` và bảo đảm cache thực sự tôn trọng nó. Nếu response preflight phụ thuộc method/header dự kiến và có một lớp HTTP cache được cho phép lưu nó, hợp đồng cache còn phải xét các header đầu vào tương ứng. `Vary` mô tả những phần request ảnh hưởng tới biến thể phản hồi. [MDN: Vary](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary)

CORS không bảo vệ khỏi việc một cache trả nhầm body của tenant A cho người dùng tenant B. Do đó cần kiểm thử độc lập nội dung, session, tenant và cách khóa cache được tạo.

Trong baseline minh họa:

- Phản hồi Documents và Administration dùng `Cache-Control: no-store`.
- Shared cache không lưu các response nhạy cảm đó.
- Public catalog chỉ được cache khi thực sự có cùng nội dung công khai cho mọi caller.
- Origin được cấp, Origin bị từ chối và request thiếu Origin đều được kiểm thử qua cùng đường proxy.
- Không ghi đè mất các giá trị Vary có sẵn như những field liên quan đến nén.

### 8.2. Chọn nơi chịu trách nhiệm phát sinh header

Một hệ thống có thể quyết định CORS ở gateway hoặc trong ứng dụng. Dù chọn đâu, phải chỉ rõ nguồn policy và cách các lớp khác bảo toàn quyết định.

Không để ứng dụng trả origin cụ thể còn CDN bổ sung `*`. Cũng không để handler lỗi hoặc rate limiter dùng policy mặc định rộng hơn handler nghiệp vụ.

Preflight thành công tại gateway không chứng minh request thực đã được áp dụng đúng policy. Mọi đường phục vụ được hỗ trợ, kể cả đường trực tiếp, phải có hành vi tương ứng hoặc bị chặn theo kiến trúc.

Nếu có redirect hợp lệ trong một luồng tích hợp, cần kiểm thử toàn bộ chuỗi trên các trình duyệt được hỗ trợ. Không suy ra header ở bước đầu tự cấp quyền chia sẻ cho đích chuyển hướng.

### 8.3. Thu hồi không thể chỉ dựa vào xóa cache preflight

Giả sử yêu cầu dự án chọn thời hạn 60 giây kể từ khi dịch vụ quản lý policy chấp nhận lệnh thu hồi. Hợp đồng của ví dụ áp dụng cho request mới đi vào nhóm bảo vệ sau mốc đó.

Các điểm phục vụ phải nhận revision mới hoặc ngừng phục vụ luồng bị ảnh hưởng trước thời hạn. Nếu một điểm mất liên lạc, cần cơ chế như lease có cận hoặc cô lập được thực thi để nó không giữ policy cũ vô hạn.

Trình duyệt có thể còn preflight cache và gửi request thực mà không hỏi OPTIONS lại. Server vẫn phải đánh giá Origin theo policy hiện hành trên request thực; không tiếp tục chia sẻ chỉ vì một preflight trước đây từng thành công.

Không thể dùng CORS để thu hồi dữ liệu mà một frontend đã đọc hoặc lưu trước đó. Request đang xử lý tại thời điểm đổi policy cần hợp đồng riêng: có chặn trước khi trả body hay cho hoàn tất trong cận nào. Không gộp nó vào cam kết cho request mới mà không nói rõ.

Một rollback cũng phải kiểm tra trạng thái thu hồi. Bản policy cũ từng hợp lệ không được tự động trở lại hiệu lực nếu nó chứa origin đã bị loại vì mất quyền kiểm soát.

## 9. Quản lý thay đổi, logging và phục hồi

### 9.1. Vòng đời một thay đổi allowlist

Một quy trình khái niệm có thể là:

1. Ghi nhu cầu tích hợp, chủ sở hữu origin, route và phân loại dữ liệu.
2. Xác minh nguồn đề nghị có quyền sửa policy đúng phạm vi.
3. Kiểm tra schema, origin, credentials, method, header và xung đột route.
4. Đánh giá thay đổi quan hệ tin cậy và xác nhận các yêu cầu xác thực, CSRF.
5. Ghi ý định thay đổi bền vững với revision trước/sau.
6. Kích hoạt snapshot nhất quán, theo dõi từng điểm phục vụ và ghi kết quả.
7. Kiểm thử hành vi được cấp, bị từ chối và khôi phục.

Khi reload nhận candidate không hợp lệ, giữ snapshot cũ chỉ khi nó còn được phép sử dụng. Khi startup không có snapshot hợp lệ, không tự mở CORS; nếu route nhạy cảm bắt buộc policy để hoạt động đúng, giữ route đó chưa sẵn sàng.

Audit không cần chứa toàn bộ request. Các field phù hợp gồm chủ thể quản lý, revision, profile, danh tính origin đã được kiểm tra, kết quả, mã lý do và thời gian.

### 9.2. Dữ liệu Origin cũng là đầu vào cần kiểm soát

Không serialize mọi header vào log để điều tra CORS. Origin do client ngoài trình duyệt gửi có thể không đáng tin; log cần giới hạn độ dài, định dạng và xử lý ký tự điều khiển.

Không ghi session cookie, Authorization hay CSRF token. Đếm từ chối nên có cơ chế hạn chế cardinality để dữ liệu tùy ý không làm phình hệ thống metric.

Bằng chứng vận hành nên cho biết policy revision có hiệu lực tại từng điểm phục vụ, số quyết định theo profile và tình trạng hội tụ. Một dòng log “đã deploy” không chứng minh proxy, ứng dụng và cache đang cùng dùng policy được chấp nhận.

### 9.3. Phục hồi khi đã cấp nhầm origin

Khi phát hiện origin không còn đáng tin, cần xác định:

- Route, dữ liệu và thời gian có thể đã chia sẻ.
- Các điểm đang phục vụ policy cũ, đường cache và kết nối liên quan.
- Khả năng origin đã đọc dữ liệu hoặc khai thác session trong thời gian được cấp.
- Hành động thu hồi policy, cô lập hoặc đổi thông tin xác thực nếu có bằng chứng ảnh hưởng.
- Bằng chứng kiểm thử lại sau khi sửa và kiểm soát ngăn tái diễn.

Không giả định xóa một dòng allowlist đã xóa dữ liệu ở bên nhận. Quy trình ứng phó phải xem xét hậu quả của dữ liệu có thể đã được truy cập.

## 10. Kế hoạch kiểm thử theo rủi ro

Kiểm tra header bằng HTTP client hữu ích cho server, nhưng client đó không mô phỏng đầy đủ việc trình duyệt cho script đọc phản hồi. Các tiêu chí chia sẻ cần được kiểm tra bằng trình duyệt thực trong các origin được kiểm soát.

| Ca | Đầu vào hoặc tác động | Kết quả chấp nhận |
|---|---|---|
| T01 | Workspace gọi Documents với session, quyền và CSRF hợp lệ | Luồng thành công; script đọc được dữ liệu đúng tenant và header được expose |
| T02 | Website không được cấp gọi nhóm nhạy cảm, gồm request có và không có preflight | Không có quyết định chia sẻ; policy server từ chối trước nghiệp vụ và không có tác dụng phụ |
| T03 | Dùng host có suffix, prefix đánh lừa, scheme khác hoặc port chưa cấp | Không khớp origin được cấp |
| T04 | Gửi `Origin: null`, Origin sai cú pháp và nhiều giá trị không hợp lệ | Từ chối theo hợp đồng; không phản chiếu đầu vào thành quyền chia sẻ |
| T05 | Candidate dùng wildcard cho profile cookie hoặc thêm field sai kiểu | Không kích hoạt; revision hiệu lực không đổi |
| T06 | Preflight hợp lệ không có session hoặc CSRF token | Có quyết định CORS phù hợp; không thực hiện nghiệp vụ và không tạo session mới để vượt kiểm tra |
| T07 | Preflight yêu cầu một method/header ngoài policy | Không cấp tổ hợp đó; trình duyệt không thực hiện request dự kiến qua luồng preflight này |
| T08 | Sau preflight hợp lệ, POST thiếu session, quyền hoặc CSRF token | Mỗi biến thể bị từ chối; không tạo tài liệu |
| T09 | Workspace hợp lệ nhưng chủ thể tenant A truy cập tài liệu tenant B | Từ chối theo policy tài nguyên; không lộ nội dung dù CORS hợp lệ |
| T10 | Client trực tiếp tự đặt Origin thuộc allowlist nhưng không có credential hợp lệ | Không vượt xác thực hoặc phân quyền |
| T11 | Form POST từ website không được cấp tới endpoint thay đổi trạng thái | Không có thay đổi; kết quả không dựa riêng vào việc script đọc được response |
| T12 | Phản hồi 401, 403, 404, lỗi validation, rate limit và lỗi phụ thuộc | Frontend được cấp nhận hợp đồng lỗi công khai phù hợp; origin khác không được cấp rộng hơn |
| T13 | Lặp request qua proxy với origin, session và tenant khác nhau | Không trả nhầm body, header hoặc policy; no-store được thực thi cho dữ liệu nhạy cảm |
| T14 | Public catalog từ origin bất kỳ với credentials mode omit | Đọc được dữ liệu thật sự công khai; không có nội dung cá nhân hóa hoặc dữ liệu nội bộ |
| T15 | Warm preflight cache, sau đó thu hồi origin và cô lập một điểm phục vụ | Request mới sau thời hạn bị xử lý bằng policy còn hiệu lực hoặc luồng bị ngừng phục vụ |
| T16 | Rollback về revision có origin đã bị thu hồi | Không khôi phục quan hệ tin cậy đã bị cấm |
| T17 | Đọc X-Request-Id và thử đọc header chẩn đoán ngoài hợp đồng từ frontend | Chỉ header được phép mới khả dụng cho script; response không chứa dữ liệu bí mật không cần thiết |
| T18 | Thử các đường vào trực tiếp được hỗ trợ và response do gateway tự tạo | Cùng ranh giới policy; không có allow-origin trùng hoặc wildcard do lớp phụ thêm |

Trong T02, với request không cần preflight, phải quan sát dữ liệu ở server để chứng minh không có tác dụng phụ. Console báo “CORS error” chỉ là một quan sát ở trình duyệt.

Trong T15, cần ghi mốc chấp nhận thu hồi, revision tại mỗi điểm phục vụ và thời điểm request mới bắt đầu. Giảm Max-Age hoặc xóa cache phía kiểm thử không thay thế biến thể trình duyệt còn giữ preflight cũ.

### 10.1. Ví dụ Given–When–Then

```gherkin
Given Documents chỉ cấp origin https://workspace.example.invalid
And request dùng session cookie của tenant A trong môi trường thử nghiệm
When trang tại https://workspace.example.invalid.attacker.invalid gửi POST
Then origin không khớp allowlist
And request thực, nếu tới server, bị chặn trước nghiệp vụ
And không có tài liệu mới được tạo
And phản hồi không cấp Access-Control-Allow-Origin cho origin đó
And sự kiện từ chối không chứa session cookie hoặc CSRF token
```

Cần thêm ca dương với origin được cấp để tránh một hệ thống chặn mọi thứ vẫn bị đánh giá là đạt. Thêm biến thể origin hợp lệ nhưng sai quyền để chứng minh CORS không thay thế phân quyền.

## 11. Những cách đặc tả dễ dẫn tới lỗi

| Cách viết hoặc cấu hình | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Cho phép domain công ty” | Không xác định scheme, host, port và chủ thể quản lý từng host | Liệt kê origin cụ thể cùng profile, mục đích và chủ sở hữu |
| “Origin có chứa example.invalid thì cho qua” | Không xác minh origin đầy đủ | Parse theo hợp đồng và so sánh với tập origin được cấp |
| “Cho phép mọi origin nhưng chỉ người đăng nhập mới đọc được” | Website khác có thể nhận dữ liệu theo phiên người dùng nếu policy chia sẻ sai | Tách session khỏi quyền chia sẻ; profile cookie dùng origin cụ thể |
| “OPTIONS qua là đã được cấp quyền” | Không kiểm tra request thực hoặc tài nguyên | Xác thực, phân quyền và CSRF ở thao tác thực |
| “CORS error nghĩa là request không chạy” | Một số request đã tới server và có thể tạo tác dụng phụ | Kiểm tra trạng thái dữ liệu và kiểm soát server độc lập |
| “Thêm tất cả header để khỏi lỗi” | Không biết dữ liệu và khả năng nào đang được cấp | Xác định request header và exposed header theo nhu cầu |
| “Đặt Max-Age thấp thì thu hồi ngay” | Không xử lý policy trên request thực và các điểm còn revision cũ | Cam kết thời hạn hội tụ/cô lập và kiểm thử cache cũ |
| “Cấu hình trong ứng dụng đúng là đủ” | Gateway, CDN và đường lỗi có thể sửa header | Xác định nơi có thẩm quyền và kiểm thử phản hồi tại biên thực tế |

## 12. Bài tập vận dụng và truy vết yêu cầu

Một dịch vụ đang dùng cấu hình mô tả như sau:

> Mọi origin được phản chiếu vào allow-origin. Credentials được bật toàn cục. OPTIONS không kiểm tra method/header. Frontend báo lỗi thì proxy thêm wildcard. Khi gỡ một đối tác, chỉ xóa domain trong repository.

Hãy viết lại đặc tả bằng cách:

1. Chia route thành nhóm cookie nhạy cảm, public và vận hành.
2. Chỉ rõ origin, credentials, method, request header và exposed header cho từng nhóm.
3. Nêu hành vi với Origin lạ, null, thiếu Origin và candidate không hợp lệ.
4. Đặt yêu cầu xác thực, phân quyền tenant và CSRF độc lập.
5. Chỉ định nguồn policy, nơi phát sinh header, cache và thời hạn thu hồi.
6. Tạo ca dương, ca âm, ca đường lỗi, ca qua proxy và ca thu hồi khi preflight đã được cache.

Một chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Rủi ro | R-CORS-01: website không được cấp đọc phản hồi theo session |
| Yêu cầu | CORS-01 giới hạn origin; CORS-03 giới hạn chia sẻ có credentials |
| Kiến trúc | Bộ chọn profile theo route và điểm quyết định CORS có thẩm quyền |
| Kiểm soát bổ sung | Xác thực session, phân quyền tài nguyên và chống CSRF |
| Kiểm thử | T01, T02, T05, T08 và T09 |
| Bằng chứng vận hành | Revision policy, trạng thái các điểm phục vụ và audit thay đổi allowlist |

Sản phẩm cần đạt là một hợp đồng triển khai được: website nào được đọc phản hồi nào, theo cơ chế xác thực nào, những thao tác nào vẫn phải bị chặn và cách chứng minh các quyết định đó còn đúng sau thay đổi, sự cố hoặc phục hồi.
