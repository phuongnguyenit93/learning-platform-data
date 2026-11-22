# Test method khác nhau trên cùng resource

Trong REST API, cùng một URI có thể hỗ trợ nhiều HTTP method và mỗi method đại diện cho một hành động khác nhau trên cùng resource. Ví dụ, `GET /api/orders/ORD-42` đọc đơn hàng, `PATCH /api/orders/ORD-42` sửa một phần thông tin, `PUT /api/orders/ORD-42` thay thế representation và `DELETE /api/orders/ORD-42` xóa hoặc vô hiệu hóa đơn hàng. Việc người dùng có quyền đọc resource không có nghĩa họ được quyền sửa hoặc xóa resource đó.

Kiểm thử bảo mật vì vậy phải thay đổi HTTP method trong khi giữ nguyên resource, danh tính, token và dữ liệu đầu vào để xác minh từng hành động được kiểm soát độc lập. Nếu chỉ kiểm tra một request `GET` thành công hoặc chỉ thử một method bị từ chối, có thể bỏ sót endpoint ghi dữ liệu, method phụ, route alias hoặc cách framework chuyển đổi method.

## 1. Vì sao phải kiểm thử nhiều method trên cùng resource?

Một resource thường có nhiều thao tác với mức rủi ro khác nhau. Nếu API chỉ kiểm tra quyền theo path, tất cả method trên cùng path có thể vô tình nhận cùng một mức quyền.

Ví dụ:

```http
GET /api/orders/ORD-42
```

```http
PATCH /api/orders/ORD-42
Content-Type: application/json

{"deliveryNote":"Giao tại quầy lễ tân"}
```

```http
DELETE /api/orders/ORD-42
```

Ba request tác động đến cùng đơn hàng nhưng có ý nghĩa khác nhau. Một khách hàng có thể được xem đơn hàng của mình, được cập nhật ghi chú giao hàng trước khi xử lý, nhưng không được xóa đơn sau khi đã thanh toán hoặc gửi hàng. Một nhân viên hỗ trợ có thể xem đơn hàng của khách theo nhiệm vụ nhưng không được hoàn tiền. Một quản lý có thể thực hiện thao tác hủy trong phạm vi được giao.

Nếu backend chỉ xác thực token hoặc kiểm tra `orders:access`, quyền đó quá rộng để phân biệt các hành động. Cần có permission và policy tương ứng cho từng method hoặc từng hành động nghiệp vụ.

## 2. Hiểu semantics của HTTP method

Trước khi lập test case, cần hiểu method mà API công bố và hành động thực tế mà server thực hiện.

| Method | Ý nghĩa HTTP phổ biến | Rủi ro bảo mật cần kiểm tra |
|---|---|---|
| `GET` | Lấy representation của resource; được thiết kế là safe | Rò rỉ dữ liệu, BOLA, truy vấn quá rộng hoặc tác dụng phụ ngoài ý muốn |
| `HEAD` | Tương tự `GET` nhưng không trả response body | Lộ sự tồn tại, kích thước, ETag hoặc metadata của resource |
| `OPTIONS` | Hỏi các phương thức hoặc khả năng được hỗ trợ | Công bố bề mặt API; nhầm lẫn giữa CORS và quyền thực thi |
| `POST` | Gửi dữ liệu để xử lý hoặc tạo resource phụ thuộc | Tạo dữ liệu, kích hoạt workflow, thanh toán hoặc hành động lặp |
| `PUT` | Tạo hoặc thay thế representation tại URI đích theo hợp đồng | Ghi đè trường ngoài quyền, thay đổi owner hoặc tenant |
| `PATCH` | Thay đổi một phần resource | Mass assignment, cập nhật trường nhạy cảm, nested path bypass |
| `DELETE` | Yêu cầu xóa resource | Xóa trái phép, xóa nhầm tenant, phá hủy dữ liệu hoặc vượt trạng thái nghiệp vụ |

`GET` và `HEAD` được thiết kế là safe; `PUT` và `DELETE` được định nghĩa là idempotent theo semantics HTTP. Điều đó không có nghĩa chúng an toàn về bảo mật. Một request `DELETE` có thể lặp lại mà không tạo thêm hiệu ứng, nhưng lần xóa đầu tiên vẫn cần authorization. Tương tự, `PUT` idempotent không cho phép người dùng thay thế dữ liệu ngoài phạm vi quyền.

`PATCH` không mặc nhiên idempotent; tính chất này phụ thuộc loại patch và cách server triển khai. `POST` thường không idempotent, nên các thao tác có hiệu ứng phụ cần thêm kiểm soát retry và idempotency khi phù hợp.

## 3. Xây dựng ma trận quyền theo method

Với mỗi resource, hãy liệt kê method được hỗ trợ, permission cần có, chủ thể được phép và điều kiện bổ sung. Ma trận này là nguồn để thiết kế test case.

Ví dụ resource `orders/{id}`:

| Method | Hành động | Permission chức năng | Điều kiện bổ sung |
|---|---|---|---|
| `GET` | Xem đơn hàng | `orders:read` | Chủ thể thuộc tenant hoặc có quan hệ truy cập hợp lệ |
| `HEAD` | Kiểm tra metadata đơn hàng | `orders:read` | Không tiết lộ metadata của resource ngoài phạm vi |
| `OPTIONS` | Xem method được hỗ trợ | Theo chính sách công bố API | CORS preflight phải được xử lý riêng với authorization |
| `POST` | Thực hiện command nếu API định nghĩa trên URI này | `orders:execute` | Kiểm tra trạng thái và chống xử lý lặp |
| `PUT` | Thay thế representation | `orders:replace` | Chỉ cho phép các trường và trạng thái phù hợp |
| `PATCH` | Cập nhật một phần | `orders:update` | Kiểm tra từng trường được thay đổi |
| `DELETE` | Hủy hoặc xóa đơn hàng | `orders:cancel` | Đơn chưa được gửi; actor có quyền hủy đúng đơn |

Các permission trên chỉ là ví dụ. Một API có thể không hỗ trợ `PUT`, `HEAD` hoặc `DELETE`; điều quan trọng là method không được hỗ trợ phải bị từ chối theo hợp đồng, còn method được hỗ trợ phải có policy rõ ràng.

### 3.1. Phân biệt quyền chức năng và quyền trên resource

Kiểm tra method trả lời câu hỏi “actor có được thực hiện hành động loại này không?”. Kiểm tra object-level authorization trả lời “actor có được thực hiện hành động đó trên resource cụ thể này không?”.

Ví dụ, người dùng có `orders:cancel` vẫn chỉ được hủy đơn thuộc phạm vi của họ. Nếu API chỉ kiểm tra permission mà không kiểm tra `tenant_id`, owner hoặc quan hệ được chia sẻ, lỗi Broken Object Level Authorization (BOLA) vẫn có thể xảy ra.

Một quyết định đầy đủ có thể kết hợp:

- Danh tính đã xác thực của user hoặc client.
- Permission tương ứng với method/hành động.
- Tenant, owner hoặc quan hệ truy cập của resource.
- Trạng thái nghiệp vụ hiện tại.
- Quyền trên từng thuộc tính được gửi hoặc trả về.

## 4. Chuẩn bị test case có kiểm soát

Để xác định chính xác lỗi nằm ở method authorization, hãy thay đổi từng yếu tố một. Khi so sánh hai method trên cùng resource, giữ nguyên:

- URI và resource ID.
- Token hoặc danh tính caller.
- Tenant và phạm vi dữ liệu.
- Header liên quan đến content negotiation.
- Payload hợp lệ khi method cần body.
- Trạng thái resource trước mỗi lần thử.

Sau đó chỉ thay HTTP method hoặc quyền của actor. Nếu dùng cùng một resource cho test ghi, phải khôi phục dữ liệu hoặc tạo fixture mới để trạng thái của lần thử trước không làm sai kết quả lần sau.

### 4.1. Chọn các nhóm danh tính

Ít nhất nên có các nhóm đại diện:

| Chủ thể | Quyền mẫu | Mục tiêu kiểm thử |
|---|---|---|
| Không xác thực | Không có token | Xác minh endpoint nghiệp vụ không public ngoài dự kiến |
| User chỉ đọc | `orders:read` | Đọc được nhưng không tự có quyền ghi hoặc xóa |
| User cập nhật | `orders:read`, `orders:update` | Chỉ cập nhật các trường và resource được phép |
| User hủy đơn | `orders:read`, `orders:cancel` | Có quyền hủy nhưng vẫn phải thỏa điều kiện object và state |
| Admin hoặc operator | Permission quản trị được cấp rõ | Kiểm tra quyền đặc biệt và phạm vi quản trị |
| Client/service account | Scope theo tích hợp | Xác minh quyền theo client, tenant và API audience |

Không dùng một token admin duy nhất cho toàn bộ test. Nếu mọi test đều chạy bằng danh tính có quyền cao, các lỗi thiếu kiểm tra permission sẽ bị che khuất.

### 4.2. Ghi lại kỳ vọng trước khi gửi request

Mỗi test nên có method, URI, actor, permission cần có, trạng thái resource, kết quả HTTP mong đợi và hiệu ứng dữ liệu cần kiểm tra. Ví dụ:

| Test | Method | Actor | Kỳ vọng |
|---|---|---|---|
| T01 | `GET` | User chỉ đọc, đúng owner | `200` và chỉ trả dữ liệu được phép |
| T02 | `PATCH` | User chỉ đọc | `403`, dữ liệu không đổi |
| T03 | `PUT` | User chỉ đọc | `403`, dữ liệu không đổi |
| T04 | `DELETE` | User chỉ đọc | `403`, resource vẫn tồn tại |
| T05 | `PATCH` | User cập nhật, đúng owner | Thành công với trường được phép |
| T06 | `DELETE` | User có quyền hủy, đơn đã shipped | Bị từ chối theo business rule |
| T07 | Method không được API hỗ trợ | User có quyền đọc | `405 Method Not Allowed` theo hợp đồng |

Mã trạng thái có thể khác theo hợp đồng API và chính sách che giấu resource. Điều cần xác minh là request bị từ chối đúng lý do, không có side effect và không rò rỉ dữ liệu.

## 5. Kiểm thử method khác nhau trên cùng URI

Giả sử API quản lý đơn hàng có URI:

```text
/api/orders/ORD-42
```

### 5.1. Kiểm tra quyền đọc và quyền ghi

Với user chỉ có `orders:read`, gửi:

```http
GET /api/orders/ORD-42 HTTP/1.1
Authorization: Bearer <read-only-token>
```

Kỳ vọng: request đọc được phép nếu user có quyền trên đơn hàng. Sau đó giữ nguyên URI và token, đổi sang:

```http
PATCH /api/orders/ORD-42 HTTP/1.1
Authorization: Bearer <read-only-token>
Content-Type: application/json

{"deliveryNote":"Leave at reception"}
```

Kỳ vọng: bị từ chối vì caller không có `orders:update`; dữ liệu đơn hàng không thay đổi. Tiếp tục thử `PUT` và `DELETE` để bảo đảm quyền đọc không bị nâng thành quyền thay thế hoặc xóa.

### 5.2. Kiểm tra method được cấp quyền riêng

Dùng user có `orders:update` nhưng không có `orders:cancel`. Request `PATCH` có thể thành công trong phạm vi trường được phép; request `DELETE` phải bị từ chối. Không nên dùng một permission tổng quát như `orders:write` nếu nghiệp vụ cần phân biệt cập nhật và hủy đơn.

Nếu API hỗ trợ cả `PUT` và `PATCH`, kiểm thử chúng riêng. `PUT` có thể thay thế toàn bộ representation trong khi `PATCH` chỉ thay đổi một phần; quyền và validation của hai method có thể khác nhau. Không giả định rule cho `PATCH` tự động bảo vệ `PUT`.

### 5.3. Kiểm tra HEAD và OPTIONS

`HEAD` có thể được framework ánh xạ hoặc xử lý gần giống `GET`. Kiểm thử xem user không có quyền đọc có thể dùng `HEAD` để dò resource tồn tại, ETag, Content-Length hoặc Last-Modified hay không. Nếu `GET` bị từ chối do quyền, `HEAD` không được tiết lộ dữ liệu hoặc metadata nhạy cảm ngoài chính sách.

`OPTIONS` thường được dùng để công bố method được hỗ trợ và phục vụ CORS preflight. Việc server trả `Allow: GET, PATCH` hoặc `Access-Control-Allow-Methods` không có nghĩa caller được phép thực hiện các method đó. Request thực tế vẫn phải qua authentication và authorization.

## 6. Phân biệt 401, 403 và 405

Ba mã trạng thái thường gặp có ý nghĩa khác nhau:

| Status | Ý nghĩa thường dùng | Khi kiểm thử |
|---|---|---|
| `401 Unauthorized` | Thiếu hoặc không có thông tin xác thực hợp lệ | Token thiếu, sai chữ ký, hết hạn hoặc không được chấp nhận |
| `403 Forbidden` | Request được hiểu nhưng caller không có quyền thực hiện | Method được hỗ trợ nhưng actor thiếu permission |
| `405 Method Not Allowed` | Server biết method nhưng resource/route không hỗ trợ method đó | Method không nằm trong hợp đồng endpoint; response thường có `Allow` |

Không dùng `405` để che một lỗi thiếu permission nếu API cần phân biệt rõ method được hỗ trợ. Ngược lại, không trả `403` cho một method không tồn tại chỉ vì route matcher chung đã chặn request. Cần thống nhất cách xử lý giữa gateway, framework và backend.

Một số hệ thống chủ động dùng `404` để che giấu sự tồn tại của resource hoặc route. Đây có thể là lựa chọn hợp lệ nếu được áp dụng nhất quán, nhưng test vẫn phải xác minh dữ liệu không bị đọc hoặc thay đổi.

## 7. Kiểm tra method override và các đường vòng

Một số framework hoặc proxy hỗ trợ method override để client gửi `POST` nhưng chỉ định method hiệu lực qua header hoặc tham số, ví dụ:

```http
POST /api/orders/ORD-42 HTTP/1.1
X-HTTP-Method-Override: DELETE
Authorization: Bearer <token>
```

Hoặc một số ứng dụng hỗ trợ tham số `_method` trong form. Nếu gateway kiểm tra `POST` nhưng ứng dụng phía sau chuyển request thành `DELETE`, hai lớp có thể áp dụng permission khác nhau. Đây là lỗi lệch chính sách giữa các tầng.

Hãy kiểm thử:

- `X-HTTP-Method-Override` và các header override khác nếu framework hỗ trợ.
- Tham số `_method` trong query hoặc form nếu được bật.
- Method tunneling qua `POST`.
- Header trùng lặp hoặc giá trị method không hợp lệ.
- Request được gửi trực tiếp tới origin/backend, bỏ qua gateway.
- Các alias route, trailing slash, path encoding và API version cũ.

Nếu không có nhu cầu tương thích, nên tắt method override. Nếu bắt buộc hỗ trợ, hãy xác định method hiệu lực trước khi authorization và bảo đảm gateway cùng backend sử dụng cùng kết quả chuẩn hóa.

Không để proxy kiểm tra một method trong khi framework xử lý method khác. Log kiểm thử nên ghi method ban đầu, method hiệu lực sau chuẩn hóa và policy được áp dụng, nhưng không ghi token hoặc secret.

## 8. Kiểm tra CORS và OPTIONS đúng cách

CORS là cơ chế để trình duyệt quyết định JavaScript ở origin nào được đọc response. CORS không thay thế authorization và không ngăn mọi client ngoài trình duyệt gọi API.

Một preflight request có thể trông như sau:

```http
OPTIONS /api/orders/ORD-42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization,content-type
```

Server có thể trả thông tin CORS cho origin và method được phép. Nhưng khi trình duyệt gửi request `DELETE` thực tế, backend vẫn phải kiểm tra token và permission `orders:cancel` hoặc quyền tương ứng. Chỉ vì `DELETE` xuất hiện trong `Access-Control-Allow-Methods` không có nghĩa mọi user được phép xóa đơn hàng.

Kiểm thử cả trường hợp origin được phép, origin không được phép, preflight hợp lệ và request thực tế thiếu permission. Không dùng cấu hình CORS rộng như `*` để thay thế quyết định ai có thể thực hiện chức năng.

## 9. Ánh xạ method vào authorization ở server

Rule cần xét cả HTTP method và path. Ví dụ Spring Security:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("orders:read")
            .requestMatchers(HttpMethod.HEAD, "/api/orders/**")
                .hasAuthority("orders:read")
            .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                .hasAuthority("orders:update")
            .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("orders:replace")
            .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("orders:cancel")
            .anyRequest().denyAll()
        )
        .build();
}
```

Đây là ví dụ minh họa; cần kiểm tra cách framework xử lý `HEAD`, `OPTIONS`, path matcher và CORS trong phiên bản đang sử dụng. Nếu preflight được xử lý trước filter authorization, điều đó chỉ cho phép trình duyệt tiếp tục quy trình CORS; request thực tế vẫn phải được bảo vệ.

Không nên chỉ kiểm tra ở gateway. Backend có thể được gọi trực tiếp từ mạng nội bộ, service khác hoặc một route chưa được gateway quản lý. Lớp thực hiện nghiệp vụ cần bảo đảm permission được kiểm tra trước side effect.

## 10. Kiểm thử thứ tự xử lý và side effect

Khi method bị từ chối, chỉ kiểm tra status code là chưa đủ. Cần xác minh không có thay đổi dữ liệu, không có message được phát ra và không có tác vụ nền được khởi tạo.

Với mỗi request ghi bị từ chối, kiểm tra:

- Giá trị resource trong database trước và sau request.
- Version hoặc `updated_at` không thay đổi ngoài dự kiến.
- Không có event hoặc message nghiệp vụ được publish.
- Không có webhook, email, thanh toán hoặc tác vụ nền bị kích hoạt.
- Audit log ghi nhận quyết định từ chối mà không lưu dữ liệu bí mật.
- Retry cùng request không tạo hiệu ứng phụ bất ngờ.

Đặc biệt, authorization phải diễn ra trước khi gọi hệ thống bên ngoài hoặc ghi dữ liệu. Nếu API đã gửi lệnh hoàn tiền rồi mới kiểm tra quyền, trả `403` sau đó không thể hoàn tác side effect đã xảy ra.

## 11. Các tình huống biên cần đưa vào test matrix

Ngoài method chính, kiểm tra các trường hợp dễ tạo khác biệt giữa router và policy:

| Tình huống | Rủi ro cần loại trừ |
|---|---|
| Method không viết hoa chuẩn hoặc method token lạ | Parser và proxy xử lý không nhất quán |
| `HEAD` được tự động chuyển sang `GET` | Bỏ qua hoặc áp dụng sai quyền đọc |
| Trailing slash hoặc path alias | Route phụ không được bảo vệ |
| URL encoded path segment | Gateway và backend định tuyến khác nhau |
| API version cũ | Chính sách cũ vẫn cho phép method nhạy cảm |
| Method override | Gateway kiểm tra method khác với backend thực thi |
| Content-Type khác nhau | Một parser khác được kích hoạt với validation yếu hơn |
| Bulk endpoint | Quyền được kiểm tra cho endpoint nhưng không cho từng resource trong batch |
| Request song song | Trạng thái thay đổi giữa lúc kiểm tra quyền và lúc ghi |
| Backend gọi trực tiếp | Bỏ qua policy tại gateway |
| CORS preflight | Nhầm danh sách method được phép với quyền của caller |
| OPTIONS/Allow header | Metadata làm lộ bề mặt API vượt mức dự kiến |

Các method như `TRACE` hoặc `CONNECT` thường không cần thiết cho API nghiệp vụ. Nếu không sử dụng, hãy tắt ở web server, proxy và framework; đưa chúng vào test âm để xác nhận không thể kích hoạt chức năng ngoài dự kiến.

## 12. Bộ ví dụ request để kiểm thử

Có thể dùng curl để gửi cùng URI với các method khác nhau. Thay token bằng fixture của môi trường kiểm thử và dùng resource thử nghiệm có thể khôi phục.

```bash
API="https://api.example.test/api/orders/ORD-42"

# Quyền đọc
curl -i -X GET "$API" \
  -H "Authorization: Bearer $READ_ONLY_TOKEN"

# Thử ghi bằng token chỉ đọc
curl -i -X PATCH "$API" \
  -H "Authorization: Bearer $READ_ONLY_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"deliveryNote":"Test note"}'

# Thử xóa bằng token chỉ đọc
curl -i -X DELETE "$API" \
  -H "Authorization: Bearer $READ_ONLY_TOKEN"

# Kiểm tra method được hỗ trợ
curl -i -X OPTIONS "$API"
```

Trong script kiểm thử, không lưu token production vào shell history, file mẫu hoặc log CI. Dùng secret fixture của môi trường test, giới hạn quyền và làm sạch dữ liệu sau khi chạy.

## 13. Kiểm thử tự động và bảo trì ma trận method

Nên biến ma trận quyền thành test tự động để mỗi lần thêm method hoặc route mới đều có thể phát hiện thiếu policy. Một test tích hợp có thể lặp qua các method, principal và kỳ vọng đã định nghĩa, nhưng cần xác nhận side effect bằng cách đọc lại resource sau request.

Ví dụ cấu trúc dữ liệu kiểm thử:

```java
record MethodCase(
        HttpMethod method,
        String path,
        String authority,
        int expectedStatus) {}
```

Mỗi case cần xác định fixture riêng hoặc reset resource giữa các thao tác ghi. Không chạy `DELETE` trước rồi tiếp tục test `GET` trên cùng fixture đã bị xóa nếu mục tiêu là so sánh quyền trên cùng trạng thái ban đầu.

Các nhóm test nên bao gồm:

1. Authentication: token thiếu, sai, hết hạn và token đúng.
2. Function authorization: mỗi method với permission có và không có.
3. Object authorization: cùng method nhưng resource thuộc owner hoặc tenant khác.
4. State authorization: cùng method nhưng resource ở trạng thái khác nhau.
5. Routing: alias, API version, path normalization và method override.
6. Side effect: dữ liệu, event và tác vụ nền không đổi khi bị từ chối.
7. Regression: endpoint mới không làm quyền của method cũ rộng hơn.

## 14. Checklist kiểm thử method trên cùng resource

Trước khi xác nhận endpoint an toàn, hãy kiểm tra:

- [ ] Đã liệt kê mọi HTTP method mà resource hỗ trợ.
- [ ] Mỗi method được gắn với hành động và permission rõ ràng.
- [ ] Quyền `GET` không tự động cấp `PUT`, `PATCH`, `POST` hoặc `DELETE`.
- [ ] `HEAD` không làm lộ dữ liệu hoặc metadata mà `GET` không được phép trả.
- [ ] `OPTIONS` và CORS không bị hiểu nhầm là authorization.
- [ ] Method không hỗ trợ được xử lý nhất quán theo hợp đồng, thường là `405`.
- [ ] Method override bị tắt hoặc được chuẩn hóa trước khi authorization.
- [ ] Gateway và backend áp dụng cùng method và policy.
- [ ] Các route alias và API version cũ không bỏ qua kiểm tra.
- [ ] Kiểm tra object, tenant, property và trạng thái sau khi kiểm tra quyền chức năng.
- [ ] Request bị từ chối không tạo side effect.
- [ ] Có test tự động cho cả quyền được phép và bị từ chối.

## 15. Nguyên tắc thiết kế

Kiểm thử method khác nhau trên cùng resource là cách trực tiếp để phát hiện API đang áp dụng quyền quá rộng theo path hoặc chỉ bảo vệ một số thao tác. Hãy giữ nguyên URI và danh tính caller, lần lượt thay method, permission và trạng thái resource; ghi rõ status code mong đợi cùng hiệu ứng dữ liệu cần kiểm tra.

Phân quyền phải được thực thi theo method và hành động nghiệp vụ ở phía server. `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH` và `DELETE` có semantics khác nhau; mỗi method được hỗ trợ cần có policy phù hợp, còn method không được hỗ trợ phải bị từ chối rõ ràng. **Một resource chỉ được bảo vệ đúng khi mọi method và mọi đường định tuyến tới resource đó đều được kiểm tra quyền độc lập, nhất quán và không tạo side effect khi bị từ chối.**
