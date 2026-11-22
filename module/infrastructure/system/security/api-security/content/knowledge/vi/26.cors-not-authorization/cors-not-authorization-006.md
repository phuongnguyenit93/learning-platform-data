# Test gọi trực tiếp origin bỏ qua browser

CORS (Cross-Origin Resource Sharing) là cơ chế mà **trình duyệt** dùng để quyết định JavaScript từ một origin có được phép đọc response của request cross-origin hay không. CORS không phải cơ chế xác thực người gọi và cũng không phải lớp phân quyền của API. Một client như `curl`, Postman, mobile app hoặc service backend có thể gửi HTTP request trực tiếp tới API mà không thực thi chính sách same-origin/CORS của browser.

Vì vậy, kiểm thử bảo mật phải gọi API trực tiếp để chứng minh server tự xác thực principal và kiểm tra quyền trên từng chức năng, object và tenant. Nếu API chỉ “an toàn” khi request đi qua frontend hoặc browser từ một origin quen thuộc, người gọi có thể bỏ qua giao diện và gọi thẳng endpoint. Allowlist CORS không thể ngăn điều đó.

Bài này tập trung vào cách kiểm tra API trực tiếp bằng HTTP client, cách thử header `Origin` giả mạo, cách xác minh authentication/authorization độc lập với browser và cách phân biệt kiểm thử CORS với kiểm thử CSRF. Trong thiết kế API security, từng endpoint, object và luồng nghiệp vụ phải tự thực thi policy ở server; browser chỉ là một trong nhiều loại client.

## 1. Hiểu đúng giới hạn của CORS

### 1.1. Browser thực thi CORS, API không dùng CORS để nhận diện người gọi

Khi JavaScript ở `https://app.example.test` gọi API tại `https://api.example.test`, browser xem đây là cross-origin request. Browser có thể gửi preflight `OPTIONS`, kiểm tra response headers như `Access-Control-Allow-Origin`, rồi quyết định có cho JavaScript đọc response hay không.

Một HTTP client không phải browser không áp dụng quy tắc đó. Ví dụ:

~~~bash
curl -i "https://api.example.test/api/profile"
~~~

`curl` sẽ hiển thị response HTTP mà server trả về, kể cả khi response không có `Access-Control-Allow-Origin`. Postman, ứng dụng mobile, script, backend service và một client tùy biến cũng có thể gọi API theo cách tương tự.

Điều này có nghĩa:

- CORS không yêu cầu client phải đến từ frontend được phê duyệt.
- CORS không chứng minh người gọi là user đã đăng nhập.
- CORS không kiểm tra user có quyền đọc hoặc sửa object cụ thể hay không.
- CORS không ngăn một client ngoài browser gọi endpoint trực tiếp.
- CORS không thay thế rate limit, validation, audit hoặc business rule.

Nếu endpoint cần bảo vệ dữ liệu, server phải yêu cầu credential phù hợp và kiểm tra quyền trên mọi request, bất kể request có `Origin` hay không.

### 1.2. Không có Access-Control-Allow-Origin không đồng nghĩa request bị server từ chối

Giả sử một website lạ gọi API bằng browser. Với request đơn giản, browser có thể gửi request tới server, server có thể thực hiện thao tác, nhưng browser không cho JavaScript đọc response vì CORS check thất bại.

Do đó, câu “browser báo CORS error” không chứng minh server chưa xử lý request. Với thao tác có side effect, cần kiểm tra trạng thái dữ liệu và audit log ở server để biết request có được thực thi hay không.

Với request cần preflight, nếu preflight thất bại thì browser thường không gửi actual request đó. Nhưng đây vẫn là cơ chế của browser. Một client trực tiếp có thể bỏ qua preflight và gửi actual request nếu biết endpoint, method, headers và payload.

### 1.3. Origin không phải credential

Browser thường tự tạo header `Origin` trong các request phù hợp và JavaScript không thể tùy ý đặt header này như một header thông thường. Nhưng client không phải browser có thể gửi bất kỳ giá trị nào:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

Một request từ `curl` có thể tự khai báo origin frontend hợp lệ. Vì vậy, server không được dùng `Origin` làm bằng chứng rằng request đến từ frontend đó hoặc cấp quyền dựa trên header này.

Có thể dùng Origin/Referer như tín hiệu bổ sung trong một số biện pháp CSRF, nhưng phải kết hợp với CSRF token và cơ chế session phù hợp. Không dùng Origin thay cho principal, token, scope, role hoặc object authorization.

## 2. Mục tiêu của kiểm thử gọi trực tiếp

Kiểm thử trực tiếp nhằm trả lời các câu hỏi:

1. Không có token/session, API có từ chối request cần đăng nhập không?
2. Token hợp lệ nhưng thiếu scope/permission có bị từ chối không?
3. User A có thể đọc, sửa hoặc xóa object của user B không?
4. Principal thuộc tenant A có thể truy cập dữ liệu tenant B không?
5. User có quyền đọc nhưng không có quyền cập nhật có thể gọi `PATCH` trực tiếp không?
6. API có tin header `Origin`, `X-User-ID`, `X-Tenant-ID` hoặc role do client gửi không?
7. Endpoint có thể bị gọi trực tiếp qua upstream/service address để bỏ qua policy ở gateway không?
8. Request không có Origin hoặc có Origin giả mạo có làm thay đổi quyết định authorization không?
9. Một request đơn lẻ có thể gây side effect dù browser không cho đọc response không?
10. Các endpoint public có thực sự chỉ trả dữ liệu công khai và vẫn chịu quota/giới hạn phù hợp không?

Một kết quả kiểm thử tốt phải chứng minh server từ chối hành động trái phép ở tầng API, không chỉ chứng minh browser không đọc được response.

## 3. Chuẩn bị môi trường và tài khoản kiểm thử

Thực hiện trên local, development hoặc staging được phép kiểm thử. Không thử trên dữ liệu khách hàng thật hoặc production nếu chưa có phạm vi kiểm thử được phê duyệt.

Chuẩn bị tối thiểu:

| Thành phần | Dữ liệu kiểm thử |
|---|---|
| User A | User đã xác thực, thuộc tenant A |
| User B | User khác, có object riêng |
| User C | User thuộc tenant B |
| Role reader | Chỉ có quyền đọc |
| Role editor | Có quyền đọc và cập nhật theo policy |
| Role admin | Quyền quản trị được giới hạn rõ |
| Token thiếu scope | Token hợp lệ nhưng thiếu permission cần thiết |
| Token hết hạn/thu hồi | Dùng để xác minh authentication failure |
| Object A/B | Bản ghi có owner hoặc tenant khác nhau |
| API base URL | Host API public hoặc test origin |
| Upstream URL (nếu có) | Service address chỉ dùng trong kiểm tra network path được phép |

Tạo fixture dễ nhận biết, ví dụ order `ORDER-A-100` thuộc user A/tenant A và `ORDER-B-200` thuộc user B/tenant B. Dùng dữ liệu giả và giá trị không gây side effect ngoài ý muốn.

Ghi lại ma trận quyền mong đợi trước khi chạy test. Ví dụ:

- User A được đọc và sửa `ORDER-A-100`.
- User A không được đọc, sửa hoặc xóa `ORDER-B-200`.
- User C không được truy cập object tenant A nếu không có cross-tenant permission.
- Reader được đọc object được phép nhưng không được gọi update/delete.
- Admin chỉ có quyền trong phạm vi được cấp; không mặc định là platform-wide.

Không dùng cùng một token cho nhiều vai trò trong test. Giữ token trong secret store hoặc biến môi trường của phiên terminal; không commit token vào repository, không chụp màn hình hoặc paste token vào ticket/log.

## 4. Gọi API trực tiếp bằng curl

`curl` hữu ích vì nó gửi HTTP request trực tiếp và không áp dụng CORS enforcement của browser. Có thể dùng để kiểm tra response status, headers, body và side effect.

### 4.1. Gọi không có Origin

Ví dụ endpoint cần xác thực:

~~~bash
curl -i "https://api.example.test/api/v1/orders/ORDER-A-100"
~~~

Nếu endpoint yêu cầu đăng nhập, request không có credential phải bị từ chối theo hợp đồng API, thường là `401 Unauthorized`. Không được trả dữ liệu riêng tư chỉ vì request không có Origin hoặc đến từ một host “quen thuộc”.

Không có Origin không đồng nghĩa request độc hại: mobile app, server-to-server client và một số same-origin flow có thể không gửi header này. Server cần xác thực theo credential và policy của endpoint, không yêu cầu Origin như một hình thức đăng nhập.

### 4.2. Gọi với token hợp lệ

~~~bash
curl -i "https://api.example.test/api/v1/orders/ORDER-A-100" -H "Authorization: Bearer $TOKEN_USER_A"
~~~

Nếu User A có quyền đọc object, API có thể trả `200 OK` và dữ liệu được phép. Đây là kiểm tra positive case để xác nhận luồng hợp lệ vẫn hoạt động.

Token phải được cấp bởi issuer tin cậy và đúng audience/client. Chỉ có chuỗi trông giống JWT không có nghĩa token hợp lệ. Server cần kiểm tra chữ ký, issuer, audience, expiry, not-before, token type và các claim cần thiết theo cấu hình xác thực.

### 4.3. Gọi với Origin được allowlist

~~~bash
curl -i "https://api.example.test/api/v1/orders/ORDER-A-100" -H "Authorization: Bearer $TOKEN_USER_A" -H "Origin: https://app.example.test"
~~~

Server có thể trả `Access-Control-Allow-Origin: https://app.example.test` vì origin nằm trong allowlist. Nhưng quyền đọc object vẫn phải xuất phát từ token và authorization policy.

### 4.4. Gọi với Origin không được phép

~~~bash
curl -i "https://api.example.test/api/v1/orders/ORDER-A-100" -H "Authorization: Bearer $TOKEN_USER_A" -H "Origin: https://attacker.example"
~~~

Có thể response không có `Access-Control-Allow-Origin`, nhưng `curl` vẫn hiển thị status và body. Nếu token của User A có quyền đọc object, API có thể trả dữ liệu cho client trực tiếp. Đây không tự động là lỗi authorization: bearer token là credential cho phép client gọi API. Câu hỏi bảo mật là token có bị lộ không, principal có quyền gì và API có trả đúng phạm vi dữ liệu không.

Nếu User A không có quyền trên object, API phải từ chối bất kể Origin là frontend hợp lệ hay website lạ.

### 4.5. Gọi với Origin giả mạo frontend tin cậy

~~~bash
curl -i "https://api.example.test/api/v1/admin/users" -H "Origin: https://app.example.test"
~~~

Không có token admin, request vẫn phải bị từ chối. Header Origin hợp lệ không được biến request thành request của admin.

Tương tự, gửi `Origin: https://admin.example.test` không được cấp role quản trị. Origin chỉ liên quan tới CORS response policy; danh tính và quyền phải lấy từ credential đã xác minh và policy server-side.

### 4.6. Không dùng -k để bỏ qua TLS trong kiểm thử

Không thêm `curl -k` hoặc `--insecure` vào test thông thường. Tùy chọn này tắt xác minh certificate và có thể che giấu lỗi TLS hoặc cấu hình hostname. Nếu môi trường test dùng CA nội bộ, cài CA test hoặc dùng tùy chọn CA bundle phù hợp để xác minh TLS đúng cách.

## 5. Thử Origin thiếu, giả mạo và không hợp lệ

Nên gửi cùng một request với nhiều biến thể Origin để xem CORS header thay đổi ra sao và authorization có giữ nguyên không.

| Trường hợp | Ví dụ | Điều cần xác minh |
|---|---|---|
| Không có Origin | Không gửi header | Authn/authz vẫn được thực thi |
| Origin được phép | `https://app.example.test` | Chỉ CORS headers được cấp theo policy |
| Origin không được phép | `https://attacker.example` | Không cấp CORS read permission |
| Origin giả frontend | Gửi origin admin từ curl | Không tăng danh tính hoặc quyền |
| Origin null | `Origin: null` | Không được tin nếu chưa có use case riêng |
| Origin giả suffix | `https://app.example.test.attacker.invalid` | Exact allowlist từ chối |
| Scheme khác | `http://app.example.test` | Không khớp origin HTTPS đã đăng ký |
| Port khác | `https://app.example.test:8443` | Không khớp origin mặc định nếu port chưa đăng ký |
| Nhiều giá trị/malformed | Header lặp hoặc origin sai cú pháp | Không tạo allow-origin mơ hồ |

Đối với cùng một principal, object và action, kết quả authorization không được thay đổi chỉ vì client thay đổi Origin. Header CORS có thể khác; status và side effect nghiệp vụ phải theo authentication/authorization policy.

Một ngoại lệ cần hiểu rõ: hệ thống có thể kiểm tra Origin/Referer như một lớp CSRF defense cho cookie session. Khi đó, Origin không hợp lệ có thể khiến request cookie-based bị từ chối theo CSRF policy. Điều này không biến Origin thành danh tính người dùng. Test CSRF phải chạy trong browser thật với cookie tự động được gửi và CSRF token tương ứng; `curl` giả Origin không mô phỏng đầy đủ hành vi browser.

## 6. Kiểm tra authentication độc lập với CORS

Thực hiện cùng một operation với các trạng thái credential khác nhau:

| Credential | Kết quả mong đợi |
|---|---|
| Không có token/session | `401` với endpoint yêu cầu xác thực |
| Token sai chữ ký hoặc không hợp lệ | `401` |
| Token hết hạn | `401` |
| Token sai issuer/audience | `401` |
| Token bị thu hồi hoặc session bị vô hiệu hóa | Từ chối theo cơ chế revoke/session policy |
| Token hợp lệ, principal active | Tiếp tục kiểm tra authorization |
| API key bị thu hồi | Từ chối, không dựa vào Origin |
| Service credential sai audience | Từ chối request service-to-service |

Không chỉ test `401` ở một endpoint. Kiểm tra route alias, version cũ, endpoint bulk/export, file download và API admin. Một filter chain hoặc route riêng có thể bỏ sót xác thực mà endpoint chính đã áp dụng.

Với API dùng JWT stateless, token đã phát hành có thể còn hiệu lực tới expiry nếu không có cơ chế revoke/introspection/versioning. Test cần phản ánh đúng thiết kế thu hồi thực tế, không giả định mọi JWT đều bị vô hiệu hóa ngay khi logout.

## 7. Kiểm tra function authorization

Principal đã đăng nhập không mặc nhiên có mọi quyền. Gọi trực tiếp từng method để xác minh quyền chức năng:

~~~http
GET /api/v1/orders/ORDER-A-100
Authorization: Bearer <reader-token>
~~~

~~~http
PATCH /api/v1/orders/ORDER-A-100
Authorization: Bearer <reader-token>
Content-Type: application/json

{"status":"CANCELLED"}
~~~

Reader có thể được phép GET nhưng không được PATCH. Nếu API chỉ ẩn nút Cancel ở frontend mà endpoint PATCH không kiểm tra permission, người dùng có thể gọi trực tiếp và thay đổi dữ liệu.

Test ít nhất:

- Reader gọi GET, POST, PATCH, DELETE theo từng permission.
- User thường gọi endpoint admin.
- Admin tenant A gọi quản trị tenant B.
- API key read-only gọi endpoint thay đổi dữ liệu.
- Service account chỉ có scope `orders:read` gọi endpoint `orders:write`.
- Method override hoặc route alias không làm bỏ qua permission.
- Batch endpoint không bỏ qua kiểm tra quyền cho từng item.

`403 Forbidden` thường phù hợp khi principal đã xác thực nhưng thiếu quyền. Một số API dùng `404` để che sự tồn tại của object ngoài phạm vi; cần tuân theo policy nhất quán và không tiết lộ dữ liệu qua response khác.

## 8. Kiểm tra object authorization và BOLA

BOLA (Broken Object Level Authorization) xảy ra khi API xác thực người gọi nhưng không kiểm tra quyền trên object ID được yêu cầu.

Giả sử User A có token hợp lệ và biết ID của order User B. Thử:

~~~bash
curl -i "https://api.example.test/api/v1/orders/ORDER-B-200" -H "Authorization: Bearer $TOKEN_USER_A"
~~~

Kết quả mong đợi là API không trả nội dung order B. Tùy policy, response có thể là `403` hoặc `404`.

Không dựa vào UUID khó đoán. ID có thể bị lộ từ email, log, URL, export, notification hoặc response khác. Authorization phải kiểm tra quan hệ giữa principal và object ở server.

Kiểm tra mọi thao tác:

- Read/detail: user A không xem được object B.
- Update: user A không thay đổi field của object B.
- Delete: user A không xóa object B.
- Download/export: user A không lấy file hoặc export của object B.
- Search/list: kết quả không chứa object ngoài phạm vi.
- Bulk: từng object trong batch đều được authorize.
- Nested resource: parent ID và child ID phải cùng thuộc phạm vi hợp lệ.

Với update, nên ràng buộc tenant/owner trong câu query hoặc câu lệnh ghi để tránh lỗi kiểm tra rồi ghi không nhất quán. Không chỉ kiểm tra object ở controller mà bỏ qua ở service/repository hoặc background job.

## 9. Kiểm tra tenant isolation

Nếu hệ thống multi-tenant, thử dùng token của tenant A nhưng gửi ID hoặc selector của tenant B.

Ví dụ:

~~~http
GET /api/tenants/TENANT-B/orders/ORDER-B-200 HTTP/1.1
Authorization: Bearer <token-user-a>
X-Tenant-ID: TENANT-B
~~~

Nếu User A chỉ thuộc tenant A, API phải từ chối. `X-Tenant-ID`, query parameter, path variable hoặc tenant ID trong JSON đều là selector do client gửi; server phải xác minh membership rồi tạo tenant context đáng tin cậy.

Kiểm tra:

- Thay `X-Tenant-ID` từ A sang B.
- Thay tenant ID trong path/query/body.
- Gửi đồng thời header và path chứa hai tenant khác nhau.
- Dùng object ID của B nhưng tenant selector A.
- Gọi export/search/bulk với tenant B.
- Truy cập cache key, file ID hoặc background job của tenant B.
- Dùng role admin của tenant A để thao tác tenant B.

Không để frontend quyết định tenant scope. CORS allowlist cũng không xác định tenant. Tenant context phải được tạo và kiểm tra phía server dựa trên principal, membership và policy.

## 10. Kiểm tra header và dữ liệu do client tự khai báo

Một API có thể vô tình tin các header mà frontend được kỳ vọng sẽ gửi đúng. Hãy thử sửa hoặc thêm:

| Header/field | Giá trị giả mạo | Điều cần xác minh |
|---|---|---|
| `Origin` | Origin frontend/admin tin cậy | Không cấp identity hoặc permission |
| `X-User-ID` | ID user quản trị | Server không thay principal đã xác thực |
| `X-Role` | `ADMIN` | Không nâng quyền bằng header |
| `X-Tenant-ID` | Tenant khác | Phải xác minh membership |
| `X-Forwarded-For` | IP được tin cậy giả | Chỉ tin header từ proxy đã cấu hình |
| `X-Forwarded-Host` | Host nội bộ hoặc host giả | Không thay đổi authority/routing ngoài policy |
| Body `userId`/`ownerId` | ID của người khác | Không cho mass assignment đổi owner |
| Body `tenantId` | Tenant khác | Tenant lấy từ context đã xác minh |
| Body `isAdmin`/`role` | `true` hoặc `ADMIN` | Field đặc quyền không được bind trực tiếp |

Không phải mọi header đều phải bị bỏ qua. Reverse proxy có thể thêm forwarded headers đáng tin cậy. Nhưng ứng dụng phải chỉ tin proxy nằm trong trust boundary, xóa giá trị do client gửi và ghi đè bằng metadata đã xác minh. Không để client gọi trực tiếp upstream và tự khai báo header nội bộ nếu mạng không bảo vệ ranh giới đó.

## 11. CORS test và authorization test là hai bộ kiểm thử riêng

Cần có cả hai vì chúng trả lời câu hỏi khác nhau.

| Kiểm thử | Công cụ phù hợp | Câu hỏi |
|---|---|---|
| CORS allowlist | Browser thật | JavaScript từ origin nào được đọc response? |
| Preflight | Browser hoặc HTTP client để quan sát response OPTIONS | Method/header nào được browser cho phép? |
| Direct API call | curl/Postman/HTTP client | Server có yêu cầu credential và authorize đúng không? |
| Origin spoofing | curl/Postman | Header Origin giả có nâng quyền không? |
| BOLA | Direct API call với nhiều token/object | Principal có truy cập object ngoài phạm vi không? |
| Tenant isolation | Direct API call với selector/object khác tenant | Server có giữ tenant context không? |
| CSRF | Browser thật với cookie session | Website khác có thể kích hoạt side effect bằng cookie tự động không? |
| Gateway bypass | Test từ network segment được phép | Upstream có bị truy cập trực tiếp để bỏ qua policy gateway không? |

### 11.1. CORS test trên browser

Tạo trang test ở một origin được allowlist và một origin không được phép. Gọi API bằng `fetch` và quan sát:

- Preflight có được trả đúng không?
- Browser có cho JavaScript đọc response không?
- Credential/cookie có được gửi theo fetch mode và cookie policy không?
- Header `Vary: Origin` và cache có hoạt động đúng không?
- Response từ origin không được phép có bị browser chặn đọc không?

Browser test cần dùng DevTools Network/Console để xem request có được gửi và response bị chặn ở bước nào. Không chỉ dựa vào thông báo lỗi tổng quát.

### 11.2. Direct API test bằng curl

Dùng cùng endpoint và cùng token, chạy các biến thể:

1. Không gửi Origin.
2. Gửi Origin hợp lệ.
3. Gửi Origin không hợp lệ.
4. Gửi Origin frontend/admin giả mạo.
5. Bỏ token.
6. Thay token bằng user khác.
7. Thay object ID và tenant selector.
8. Gọi method thay đổi dữ liệu trực tiếp.

So sánh status, body, response headers và side effect. Với cùng principal/object/action, quyết định authorization phải nhất quán. CORS headers có thể thay đổi theo Origin, nhưng không được cấp quyền dữ liệu hoặc chức năng.

### 11.3. CSRF test bằng browser

Nếu API dùng cookie/session, dựng một trang ở origin khác để thử gửi request thay đổi trạng thái trong môi trường test. Kiểm tra SameSite, CSRF token, Origin/Referer policy và trạng thái dữ liệu sau request.

Không kết luận “CSRF an toàn” chỉ vì `curl` không có cookie bị `401`. Trong browser, cookie có thể tự động được gửi. Cũng không kết luận “CSRF an toàn” chỉ vì JavaScript không đọc được response; thao tác có thể đã xảy ra.

## 12. Kiểm tra gọi trực tiếp upstream để bỏ qua gateway

Trong một số kiến trúc, API gateway thực hiện authentication, rate limit, request validation hoặc policy enforcement. Nếu service upstream vẫn có thể truy cập từ mạng ngoài hoặc từ client không đáng tin, người gọi có thể bỏ qua gateway.

Đây là kiểm tra network exposure và trust boundary, khác với CORS origin trong browser.

Nếu kiến trúc yêu cầu mọi request đi qua gateway, hãy xác minh:

- Upstream service không có public ingress ngoài dự kiến.
- Security group, firewall, Kubernetes NetworkPolicy hoặc service mesh chỉ cho phép gateway/identity được phê duyệt.
- Service xác thực workload identity hoặc credential giữa các service.
- Không tin `X-Authenticated-User`, `X-Role` hoặc header nội bộ nếu request có thể đến trực tiếp từ client.
- Gateway không phải nơi duy nhất kiểm tra object/tenant authorization nếu service có thể được gọi từ nhiều đường.
- Direct route, alternate hostname, load balancer và port quản trị không tạo đường vòng.

Có thể chạy test từ network segment kiểm thử được phê duyệt để xác nhận upstream bị chặn. Không quét dải IP hoặc thử truy cập hạ tầng ngoài phạm vi được giao. Nếu direct upstream được phép cho service-to-service, cần xác thực workload và authorization ở service đích.

## 13. Đánh giá response và side effect

Khi gọi trực tiếp, đừng chỉ nhìn status code. Kiểm tra:

- Response body có chứa field nhạy cảm hoặc dữ liệu ngoài phạm vi không?
- Header có lộ server, internal hostname, debug detail hoặc token không?
- Request bị từ chối có tạo record, gửi email, thanh toán hoặc enqueue job không?
- Retry có tạo side effect trùng lặp không?
- Audit log có ghi đúng principal, tenant, action và outcome không?
- Error message có tiết lộ object tồn tại hay không?
- Rate limit và quota có hoạt động khi client bỏ qua browser không?

Với request thay đổi trạng thái, kiểm tra dữ liệu sau test trong database/test fixture hoặc qua API quản trị được phép. Một response `403` nhưng side effect đã xảy ra vẫn là lỗi nghiêm trọng. Ngược lại, response `200` không nhất thiết là lỗi nếu endpoint được thiết kế public và chỉ trả dữ liệu công khai; cần đánh giá theo contract.

## 14. Tự động hóa kiểm thử trong CI

Có thể tạo test integration chạy trực tiếp tới API test server, không phụ thuộc browser:

- Token thiếu/invalid/expired.
- Token hợp lệ nhưng thiếu scope.
- User A truy cập object B.
- Tenant A gửi selector/object tenant B.
- Header Origin giả mạo.
- Header role/user/tenant giả mạo.
- Reader gọi write operation.
- Direct upstream bị chặn hoặc yêu cầu workload identity.
- Request bị từ chối không tạo side effect.
- Public endpoint vẫn áp quota và giới hạn dữ liệu.

Ví dụ test với Spring MockMvc có thể xác minh service authorization ở application layer:

~~~java
@Test
void readerCannotCancelOrder() throws Exception {
    mockMvc.perform(patch("/api/v1/orders/{id}", orderId)
            .with(jwt().authorities(
                    new SimpleGrantedAuthority("orders:read")))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"status":"CANCELLED"}
                """))
        .andExpect(status().isForbidden());
}
~~~

Test này xác minh policy trong application security chain; nó không thay thế integration test qua gateway, HTTP server, TLS, CORS hoặc browser. Cần thêm test gọi API bằng HTTP client thật để phát hiện cấu hình khác nhau giữa mock và deployment.

Không dùng test chỉ kiểm tra `Access-Control-Allow-Origin` để kết luận authorization đúng. Nên có test riêng cho authn/authz và test browser riêng cho CORS.

## 15. Cách diễn giải kết quả và lỗi thường gặp

| Kết quả quan sát | Kết luận đúng | Kết luận sai cần tránh |
|---|---|---|
| curl đọc được body dù thiếu ACAO | curl không áp dụng CORS | “CORS bị bypass nên API chắc chắn có lỗi” |
| Browser báo CORS error | Browser không expose response cho JavaScript | “Server chắc chắn không xử lý request” |
| Origin giả được phản chiếu | CORS allowlist có thể đang phản chiếu không an toàn | “Header Origin đã xác thực user” |
| Request không token trả dữ liệu riêng tư | Authentication/access control có thể bị thiếu | “Chỉ cần thêm CORS là sửa được” |
| User A đọc object B | Có thể là BOLA/object authorization failure | “Đổi UUID là đủ bảo vệ” |
| Upstream trả dữ liệu khi gọi trực tiếp | Có thể gateway bypass hoặc service được thiết kế internal nhưng expose sai | “CORS đang cấu hình sai” |
| Origin lạ không có ACAO nhưng request tạo giao dịch | Cần kiểm tra CSRF và side effect | “Browser CORS đã chặn thao tác” |
| Token hợp lệ truy cập API bằng curl | Hành vi bình thường của bearer credential | “API chỉ nên nhận request từ browser” |

Đừng yêu cầu mọi API từ chối request không có Origin. Làm vậy có thể phá vỡ mobile, server-to-server và automation hợp lệ, trong khi client độc hại vẫn có thể giả mạo Origin. Hãy bảo vệ theo credential, permission, object và network trust boundary.

## 16. Báo cáo kiểm thử

Một finding nên ghi rõ:

- Endpoint, method, version và environment.
- Thời gian, request ID và test case.
- Principal/client/tenant test, không ghi token thật.
- Origin gửi trong request (nếu có).
- Credential state: absent, invalid, expired hoặc valid.
- Object/tenant và permission dự kiến.
- Request tối thiểu tái hiện lỗi, đã redact secret.
- Status, response headers/body đã redact.
- Side effect quan sát được.
- Expected behavior, actual behavior và mức độ ảnh hưởng.
- Bằng chứng browser nếu finding liên quan CORS/CSRF.
- Bằng chứng direct HTTP client nếu finding liên quan authn/authz.

Phân loại finding đúng bản chất: CORS misconfiguration, missing authentication, broken function authorization, BOLA, tenant isolation failure, CSRF, gateway bypass hoặc information disclosure. Tránh gộp tất cả thành “CORS vulnerability” vì hướng khắc phục khác nhau.

## 17. Ma trận kiểm thử trước khi phát hành

| Nhóm | Request | Kết quả mong đợi |
|---|---|---|
| Direct unauthenticated | Gọi endpoint private không token, không Origin | `401`; không lộ dữ liệu và không có side effect |
| Fake trusted Origin | Gửi Origin frontend hợp lệ nhưng không token | Vẫn `401` |
| Unknown Origin | Token hợp lệ nhưng Origin lạ | Authorization theo principal; không cấp CORS read permission |
| Missing Origin | Token hợp lệ, không có Origin | Quyền dựa trên credential và policy, không tự động nâng/hạ quyền |
| Invalid credential | Token sai/hết hạn/sai audience | `401` |
| Missing permission | Token hợp lệ nhưng thiếu scope | `403` hoặc policy tương đương |
| Object access | User A lấy object B | Không đọc/sửa/xóa object B |
| Tenant tampering | User A đổi tenant selector sang B | Từ chối theo tenant policy |
| Role/header tampering | Gửi X-Role=ADMIN hoặc X-User-ID khác | Không thay principal hoặc role |
| Method tampering | Reader gọi PATCH/DELETE | Bị từ chối |
| Bulk access | Batch chứa object thuộc nhiều user/tenant | Authorize từng item, không xử lý item trái phép |
| CSRF | Browser gửi cookie cross-site tới endpoint có side effect | CSRF defense ngăn thao tác trái phép |
| Preflight | Browser gọi method/header cần preflight | Chỉ origin/method/header được duyệt mới qua |
| Gateway bypass | Gọi upstream trực tiếp từ mạng không được phép | Kết nối bị chặn hoặc service yêu cầu workload identity |
| Side effect | Request bị từ chối | Không tạo/cập nhật/xóa/gửi giao dịch ngoài ý muốn |
| Audit | Request thành công/thất bại | Log đúng principal, action, object, tenant và outcome; không log secret |

## 18. Checklist hoàn tất kiểm thử

- [ ] Đã gọi API trực tiếp bằng HTTP client không thực thi CORS.
- [ ] Đã thử request không có Origin và request có Origin hợp lệ/không hợp lệ/giả mạo.
- [ ] Đã xác minh Origin không được dùng làm identity hoặc cấp permission.
- [ ] Endpoint private từ chối request không có credential hợp lệ.
- [ ] Token được xác minh issuer, audience, expiry và trạng thái theo policy.
- [ ] Function authorization được kiểm tra cho từng method/operation.
- [ ] Object authorization được kiểm tra trên read, update, delete, download, search và bulk.
- [ ] Tenant context được xác minh phía server; header/body/path không thể đổi tenant tùy ý.
- [ ] Header user/role/forwarded do client tự khai báo không thể nâng quyền.
- [ ] Request bị từ chối không tạo side effect.
- [ ] CSRF được kiểm thử riêng trong browser với cookie session.
- [ ] CORS/preflight được kiểm thử riêng trong browser thật.
- [ ] Nếu gateway là trust boundary, upstream không bị expose ngoài policy.
- [ ] Audit log có đủ thông tin nhưng không chứa token/cookie/secret.
- [ ] Finding phân biệt đúng CORS, CSRF, authentication, authorization, BOLA và gateway bypass.

CORS chỉ kiểm soát browser có cho JavaScript đọc response cross-origin hay không. Một HTTP client trực tiếp có thể gọi API và tự đặt header Origin; do đó server phải tự xác thực credential và kiểm tra quyền cho từng function, object, tenant và side effect. Kiểm thử bằng curl/Postman giúp chứng minh lớp bảo vệ server-side hoạt động độc lập với browser, còn browser test vẫn cần thiết để xác minh CORS và CSRF. Hai bộ kiểm thử bổ sung cho nhau và không thể thay thế nhau.
