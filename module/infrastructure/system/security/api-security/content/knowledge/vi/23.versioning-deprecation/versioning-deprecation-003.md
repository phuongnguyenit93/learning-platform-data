# Lịch deprecation và thông báo client

Trong chương **Version và deprecation** của module `SECURITY_API_SECURITY`, việc ngừng hỗ trợ một phiên bản API cần được quản lý như một thay đổi có ảnh hưởng đến bảo mật và luồng nghiệp vụ. Một endpoint cũ có thể tiếp tục tồn tại vì client chưa nâng cấp, nhưng kéo dài hỗ trợ vô thời hạn làm tăng chi phí vận hành, giữ lại cơ chế xác thực yếu hoặc parser lỗi thời và khiến đội ngũ khó loại bỏ hành vi không an toàn.

**Deprecation** là thông báo rằng một API, phiên bản, endpoint, field hoặc hành vi sẽ không còn được khuyến nghị và có thể bị loại bỏ trong tương lai. **Sunset** là thời điểm một API hoặc tài nguyên dự kiến ngừng hoạt động. Hai khái niệm này cần được phân biệt: deprecation bắt đầu giai đoạn chuyển đổi; sunset đánh dấu hạn cuối để client hoàn tất chuyển đổi.

Một lịch deprecation tốt phải trả lời được: thành phần nào bị ảnh hưởng, client nào đang sử dụng, cần chuyển sang lựa chọn nào, thời gian còn lại là bao lâu, ai chịu trách nhiệm hỗ trợ và hệ thống sẽ phản ứng thế nào sau ngày sunset. Mục tiêu là cho client đủ thông tin để nâng cấp có kế hoạch, đồng thời giúp tổ chức loại bỏ phiên bản cũ đúng hạn và giảm bề mặt tấn công.

## Vì sao deprecation là một phần của API security?

API cũ có thể chứa các rủi ro mà phiên bản mới đã khắc phục:

- Cơ chế xác thực cũ chấp nhận token yếu, thuật toán lỗi thời hoặc cách truyền credential không an toàn.
- Endpoint cũ thiếu object-level authorization, kiểm tra tenant hoặc validation nhất quán.
- Schema cũ cho phép field nhạy cảm bị ghi đè, trả quá nhiều dữ liệu hoặc dùng kiểu dữ liệu không còn phù hợp.
- Parser, thư viện TLS, thuật toán ký hoặc dependency đã hết hỗ trợ bảo mật.
- Giới hạn body, pagination, timeout hoặc rate limit không đủ để chống lạm dụng tài nguyên.
- Cấu trúc URL hoặc hành vi tương thích ngược khiến hệ thống phải giữ một nhánh code không còn được kiểm thử đầy đủ.

Ví dụ, `POST /v1/transfers` có thể cho phép client truyền `ownerId` trong body và server tin giá trị đó. Phiên bản `v2` lấy chủ sở hữu từ principal đã xác thực và kiểm tra quyền trên tài khoản nguồn. Nếu tiếp tục duy trì `v1` vô thời hạn, lỗ hổng phân quyền vẫn tồn tại dù `v2` đã an toàn hơn.

Không nên xem deprecation chỉ là việc đổi URL. Một thay đổi có thể ảnh hưởng đến semantics, quyền truy cập, dữ liệu trả về, retry, idempotency, trạng thái lỗi, giới hạn tài nguyên hoặc yêu cầu lưu trữ. Những khác biệt đó phải được ghi rõ trong hướng dẫn chuyển đổi và thông báo cho client.

## Phân biệt các mốc vòng đời

Một chính sách vòng đời API nên định nghĩa rõ các trạng thái và điều kiện chuyển tiếp:

| Trạng thái | Ý nghĩa | Hành động với client |
|---|---|---|
| Active | Phiên bản đang được hỗ trợ bình thường | Có thể tích hợp mới theo tài liệu hiện hành |
| Deprecated | Đã công bố kế hoạch ngừng hỗ trợ | Không khuyến khích tích hợp mới; client hiện tại bắt đầu migration |
| Sunset announced | Đã xác định ngày ngừng hoạt động | Hoàn tất nâng cấp trước hạn; theo dõi thông báo và usage |
| Read-only / restricted (nếu có) | Giai đoạn hạn chế được công bố trước | Chỉ cho phép thao tác được nêu rõ, ví dụ đọc dữ liệu để đối soát |
| Retired | Đã ngừng cung cấp | Request tới API cũ bị từ chối theo chính sách đã công bố |

`Deprecated` và `Sunset announced` có thể được gộp trong một quy trình nếu ngày sunset đã biết ngay khi công bố. Điều quan trọng là trạng thái phải nhất quán giữa tài liệu, portal, response header, dashboard và thông tin hỗ trợ.

Các mốc không nhất thiết giống nhau cho mọi loại API. API public có nhiều client không kiểm soát được thường cần cửa sổ dài hơn API nội bộ có owner rõ ràng. Endpoint xử lý dữ liệu nhạy cảm hoặc có lỗ hổng đang bị khai thác có thể cần lịch rút ngắn và biện pháp giảm thiểu ngay lập tức. Thời gian chuyển đổi phải dựa trên rủi ro, mức độ ảnh hưởng, hợp đồng dịch vụ và khả năng liên hệ client.

## Xây dựng chính sách deprecation

### 1. Xác định chính xác phạm vi bị ngừng hỗ trợ

Thông báo phải xác định được một hoặc nhiều đối tượng sau:

- Phiên bản API: ví dụ `/v1` hoặc một version được chọn qua media type.
- Endpoint và HTTP method cụ thể: ví dụ `POST /v1/transfers`.
- Field hoặc parameter: ví dụ `legacyAccountNumber` trong request.
- Giá trị enum hoặc trạng thái: ví dụ trạng thái `PENDING_REVIEW` cũ được thay bằng một state machine mới.
- Cơ chế xác thực hoặc chữ ký: ví dụ một loại API key hoặc thuật toán ký sắp bị loại bỏ.
- Hành vi: ví dụ server không còn tự động retry một thao tác ghi.
- SDK, webhook schema hoặc phiên bản callback.

Không nên ghi chung chung “API v1 sắp bị xóa” nếu chỉ một số endpoint bị ảnh hưởng. Phạm vi mơ hồ khiến client không biết phải thay đổi gì và dễ dẫn đến việc nâng cấp thiếu sót.

### 2. Chọn phiên bản thay thế và mô tả khác biệt

Mỗi thông báo cần có đích chuyển đổi cụ thể: version mới, endpoint thay thế, SDK tương ứng hoặc quy trình thay thế. Nếu chưa có phương án thay thế, phải nói rõ client cần làm gì và đội phụ trách nào có thể hỗ trợ.

Migration guide nên liệt kê khác biệt theo nhóm:

| Nhóm thay đổi | Nội dung cần mô tả |
|---|---|
| URL và method | Route mới, method mới hoặc cách chọn API version |
| Authentication | Scope, audience, token claim, key rotation hoặc chữ ký mới |
| Authorization | Quyền mới, điều kiện tenant/owner và quyền trên từng đối tượng |
| Request schema | Field bị xóa/đổi tên, field bắt buộc, kiểu và giới hạn mới |
| Response schema | Field mới/mất đi, enum, pagination và error format |
| Business semantics | Thay đổi trạng thái, thứ tự xử lý, tính toán hoặc side effect |
| Reliability | Timeout, retry, idempotency, rate limit và consistency |
| Data handling | Thời hạn lưu, masking, encryption hoặc dữ liệu không còn trả về |

Với thay đổi bảo mật, giải thích hành vi mới và lý do ở mức client cần biết. Không công bố chi tiết khai thác, secret, cấu hình nội bộ hoặc thông tin có thể giúp tấn công phiên bản cũ.

### 3. Đặt thời gian chuyển đổi có căn cứ

Lịch deprecation phải có ngày công bố, ngày bắt đầu deprecation, ngày sunset, các mốc nhắc nhở và ngày ngừng hỗ trợ thực tế. Một lịch mẫu cho API public có thể như sau:

| Mốc tham khảo | Hoạt động |
|---|---|
| T-180 ngày | Công bố deprecation, migration guide và version thay thế; mở kênh hỗ trợ |
| T-120 ngày | Gửi thông báo trực tiếp cho client có usage; cung cấp SDK và ví dụ chuyển đổi |
| T-90 ngày | Nhắc client chưa migration; chia sẻ dashboard hoặc báo cáo endpoint đang dùng |
| T-30 ngày | Thông báo hạn cuối; xác nhận kế hoạch với client có lưu lượng hoặc nghiệp vụ quan trọng |
| T-7 ngày | Nhắc lần cuối và kiểm tra readiness, exception đã được phê duyệt |
| T0 | Ngừng phục vụ theo kế hoạch; trả response lỗi nhất quán và ghi nhận metric |

Đây là lịch tham khảo, không phải thời hạn bắt buộc cho mọi API. Với API nội bộ, có thể dùng cửa sổ ngắn hơn nếu từng consumer có owner và lịch release rõ ràng. Với client bên ngoài có chu kỳ chứng nhận, procurement hoặc triển khai dài, cần tính các phụ thuộc đó vào thời gian thông báo.

Tránh thay đổi ngày sunset nhiều lần mà không có lý do. Nếu buộc phải gia hạn, công bố ngày mới, nguyên nhân, client bị ảnh hưởng và tác động đến kế hoạch hỗ trợ. Nếu phải rút ngắn do sự cố bảo mật, cần nêu rõ hành động khẩn cấp và biện pháp tạm thời client phải thực hiện.

### 4. Quy định exception

Một số client có thể không kịp chuyển đổi vì phụ thuộc bên thứ ba hoặc yêu cầu vận hành. Exception chỉ nên được chấp nhận khi có:

- Tên client, application/client ID và owner chịu trách nhiệm.
- Endpoint, version và luồng dữ liệu nằm trong phạm vi ngoại lệ.
- Lý do, rủi ro còn lại và biện pháp giảm thiểu.
- Ngày hết hạn, mốc migration và người phê duyệt.
- Cách thu hồi quyền hoặc chặn truy cập nếu exception hết hạn.

Không tạo ngoại lệ vô thời hạn chỉ vì client có lưu lượng lớn. Client quan trọng cần kế hoạch chuyển đổi rõ hơn, không phải quyền sử dụng phiên bản lỗi thời vĩnh viễn. Nếu phiên bản cũ có lỗ hổng nghiêm trọng đang bị khai thác, exception không được phép làm mất biện pháp khắc phục bắt buộc.

## Thông báo cho client

### 1. Duy trì danh sách client có thể liên hệ

Để thông báo đến đúng người, hệ thống cần biết ai đang gọi API và ai chịu trách nhiệm cho tích hợp đó. Tùy mô hình, có thể dùng:

- OAuth `client_id`, API key ID hoặc credential ID (chỉ lưu định danh, không lưu secret để làm báo cáo).
- Tên ứng dụng, tổ chức/tenant, môi trường và owner kỹ thuật.
- Email hoặc contact đã đăng ký cho thông báo vận hành.
- Endpoint/version được sử dụng và thời điểm request gần nhất.
- Mức độ quan trọng của nghiệp vụ và kênh hỗ trợ đã thỏa thuận.

Không nên dựa riêng vào `User-Agent`, IP hoặc chuỗi tự khai báo để xác định client vì các giá trị này có thể thiếu, thay đổi hoặc bị giả mạo. Nếu không thể xác định client, cần cải thiện onboarding và đăng ký ứng dụng; không thu thập thêm dữ liệu cá nhân quá mức cần thiết chỉ để gửi thông báo.

### 2. Dùng nhiều kênh thông báo

Thông tin deprecation nên xuất hiện tại nơi client có khả năng nhìn thấy:

- Developer portal và trang trạng thái API.
- Changelog, release notes và tài liệu OpenAPI.
- Email đến contact đã đăng ký của application owner.
- Dashboard hiển thị usage theo version và endpoint.
- SDK warning hoặc thông báo trong công cụ quản trị, nếu có cơ chế phù hợp.
- Kênh hỗ trợ hoặc account manager cho client có hợp đồng và luồng nghiệp vụ quan trọng.
- HTTP response header trong giai đoạn deprecation, nếu giao thức và hạ tầng hỗ trợ.

Không gửi thông tin nhạy cảm của một client cho client khác. Dashboard hoặc email cần giới hạn dữ liệu theo quyền của application owner và tenant. Không đưa token, request body hoặc dữ liệu cá nhân vào báo cáo deprecation.

### 3. Nội dung thông báo cần có

Một thông báo có thể hành động được nên bao gồm:

1. Tên API/version/endpoint hoặc field bị deprecate.
2. Ngày bắt đầu deprecation và ngày sunset có timezone rõ ràng (ưu tiên UTC trong tài liệu kỹ thuật).
3. Lý do ở mức phù hợp, ví dụ nâng cấp bảo mật, thay đổi hợp đồng hoặc hợp nhất endpoint.
4. Phiên bản thay thế và link migration guide.
5. Những thay đổi cụ thể trong request, response, quyền và semantics.
6. Cách kiểm tra ứng dụng có đang sử dụng API cũ không.
7. Hướng dẫn kiểm thử và xác nhận migration thành công.
8. Contact hỗ trợ, quy trình xin exception và hạn chót gửi yêu cầu.
9. Tác động sau sunset, gồm status/error response và khả năng khôi phục (nếu có).

Tránh dùng câu “hãy nâng cấp sớm” mà không nêu thời hạn và bước tiếp theo. Client cần biết chính xác việc nào phải hoàn thành và làm thế nào để xác nhận.

### 4. HTTP response header hỗ trợ thông báo

Hai chuẩn HTTP hữu ích là `Deprecation` và `Sunset`:

- **Deprecation** được định nghĩa trong RFC 9745. Giá trị là Structured Field Date, biểu diễn thời điểm tài nguyên bị deprecate dưới dạng Unix timestamp có tiền tố `@`.
- **Sunset** được định nghĩa trong RFC 8594. Giá trị là HTTP-date cho thời điểm tài nguyên dự kiến không còn khả dụng.
- Có thể dùng `Link` với relation `deprecation` để trỏ tới tài liệu giải thích và hướng dẫn migration.

Ví dụ response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1798675200
Sunset: Thu, 31 Dec 2026 00:00:00 GMT
Link: <https://developer.example.com/deprecations/transfers-v1>; rel="deprecation"
Cache-Control: no-store
```

Timestamp và ngày trong ví dụ chỉ minh họa cú pháp; khi triển khai phải thay bằng thời điểm đã được phê duyệt và bảo đảm hai header cùng chỉ đến đúng lịch thực tế. `Deprecation` thông báo trạng thái deprecate, còn `Sunset` thông báo thời điểm dự kiến ngừng hoạt động. Nếu chưa xác định được ngày sunset, không tự tạo một ngày giả chỉ để điền header.

Header là tín hiệu bổ sung. Proxy, cache hoặc client có thể không hiển thị hay xử lý chúng, vì vậy vẫn cần portal, email, changelog và dashboard. Không dựa vào header để thay thế nghĩa vụ thông báo đã cam kết trong hợp đồng.

## Đo lường mức độ sử dụng và readiness

Không thể quyết định an toàn thời điểm sunset nếu không biết client nào còn sử dụng API cũ. Telemetry nên được thiết kế từ trước khi công bố deprecation.

### 1. Thu thập usage có kiểm soát

Các metric hữu ích gồm:

- Request count theo version, endpoint, method và client ID.
- Thời điểm request thành công gần nhất của từng client.
- Tỷ lệ lỗi và retry sau khi client bắt đầu migration.
- Tỷ lệ request còn dùng field hoặc behavior sắp bị loại bỏ.
- Số client đã xác nhận migration, đang migration hoặc chưa phản hồi.
- Lưu lượng từ client không xác định được owner.

Dùng định danh client ổn định, pseudonymous khi phù hợp và áp dụng retention phù hợp. Tránh ghi toàn bộ URL có thể chứa ID nhạy cảm, request body, token hoặc thông tin cá nhân vào metric label. Cardinality cao từ client ID tùy ý cũng có thể làm tăng chi phí telemetry; cần giới hạn và dùng hệ thống báo cáo phù hợp.

### 2. Phân biệt không có traffic và không quan sát được traffic

Client không phát sinh request trong 30 ngày chưa chắc đã ngừng sử dụng API. Có thể đó là tích hợp theo mùa, batch hàng quý hoặc luồng dự phòng chỉ chạy khi có sự cố. Cần kết hợp:

- Khoảng thời gian quan sát đủ dài so với chu kỳ nghiệp vụ.
- Xác nhận trực tiếp từ application owner.
- Lịch batch, sự kiện mùa vụ và dependency đã đăng ký.
- Log gateway, service mesh và ứng dụng để xác định điểm mù.
- Test synthetic cho các luồng quan trọng, nếu phù hợp.

Không xem metric thiếu dữ liệu là bằng chứng rằng client đã migration. Dashboard nên phân biệt `no observed usage`, `unknown client` và `confirmed migrated`.

### 3. Định nghĩa điều kiện sẵn sàng sunset

Trước ngày sunset, xác nhận các điều kiện phù hợp:

- Các client có owner đã được thông báo và có đủ thời gian chuyển đổi.
- Client trọng yếu đã xác nhận migration hoặc có exception còn hiệu lực.
- Version thay thế đã ổn định, tài liệu và SDK có thể sử dụng.
- Contract test, security test và production smoke test đã đạt.
- Không còn traffic hợp lệ hoặc traffic còn lại đã được đánh giá và xử lý theo exception.
- Support team, on-call, dashboard và runbook đã chuẩn bị cho thời điểm ngừng dịch vụ.
- Có kế hoạch rollback hoặc khôi phục trong giới hạn kỹ thuật và chính sách dữ liệu.

Không đặt tiêu chí “traffic bằng 0 trong 24 giờ” cho mọi API. Cửa sổ quan sát phải phản ánh chu kỳ nghiệp vụ và mức độ rủi ro của endpoint.

## Ví dụ migration từ API v1 sang v2

Giả sử API cũ nhận chủ sở hữu tài khoản từ body:

```http
POST /v1/transfers
Authorization: Bearer <token>
Content-Type: application/json

{
  "ownerId": "user-123",
  "sourceAccountId": "acc-100",
  "destinationAccountId": "acc-200",
  "amount": "250000.00"
}
```

API v2 lấy chủ sở hữu từ danh tính đã xác thực và kiểm tra quyền trên tài khoản:

```http
POST /v2/transfers
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: 7a13f9a2-8d21-4a3f-a2b1-6f32e1d40a10

{
  "sourceAccountId": "acc-100",
  "destinationAccountId": "acc-200",
  "amount": "250000.00",
  "currency": "VND"
}
```

Migration guide cần nói rõ `ownerId` đã bị loại bỏ và server lấy principal từ token đã xác thực; client phải có quyền chuyển tiền trên tài khoản nguồn; `currency` trở thành field bắt buộc; request ghi cần idempotency key theo quy tắc mới. Nếu response hoặc error schema cũng đổi, phải có ví dụ tương ứng.

Client nên kiểm thử ít nhất các trường hợp: token hợp lệ nhưng không có quyền với tài khoản nguồn, tài khoản thuộc tenant khác, số tiền ngoài giới hạn, idempotency key bị gửi lại và timeout xảy ra sau khi server đã nhận request. Những test này giúp xác nhận migration không làm thay đổi ngoài ý muốn semantics tài chính hoặc mở lại lỗi phân quyền.

## Hành vi tại và sau ngày sunset

Trước ngày sunset, server có thể tiếp tục phục vụ API cũ trong giới hạn chính sách đã công bố và thêm header deprecation/sunset. Có thể bổ sung warning có cấu trúc trong response, nhưng không nên thay đổi schema hiện tại theo cách khiến client cũ parse thất bại.

Tại ngày sunset:

- Từ chối request tới endpoint/version đã retired theo một hành vi nhất quán.
- Có thể trả `410 Gone` khi tài nguyên đã bị loại bỏ vĩnh viễn và muốn diễn đạt rõ trạng thái đó; dùng error body machine-readable với mã lỗi và link tài liệu migration.
- Không trả stack trace, cấu hình nội bộ, thông tin credential hoặc chi tiết về hệ thống phía sau.
- Không tự động chuyển request ghi từ v1 sang v2 nếu semantics, authorization hoặc idempotency khác nhau. Proxy chuyển tiếp âm thầm có thể làm thay đổi side effect và gây lỗi nghiệp vụ.
- Ghi metric số request bị từ chối theo client ID và endpoint để hỗ trợ điều tra, nhưng không log payload nhạy cảm.

Ví dụ lỗi sau sunset:

```http
HTTP/1.1 410 Gone
Content-Type: application/problem+json
Link: <https://developer.example.com/migrations/transfers-v2>; rel="deprecation"
Cache-Control: no-store

{
  "type": "https://developer.example.com/problems/api-retired",
  "title": "API version retired",
  "status": 410,
  "code": "API_VERSION_RETIRED",
  "detail": "This API version is no longer available. Migrate to v2."
}
```

Thông báo lỗi cần đủ thông tin để client xử lý tự động và tìm tài liệu, nhưng không tiết lộ lý do bảo mật nội bộ. `410 Gone` là lựa chọn phù hợp khi muốn thể hiện endpoint đã bị gỡ; tổ chức vẫn phải định nghĩa rõ hành vi theo hợp đồng API và cân nhắc gateway, cache, client retry. Không để client retry vô hạn một request đã bị retire.

## Kiểm thử và vận hành lịch deprecation

Lịch deprecation cũng cần được kiểm thử như một thay đổi sản phẩm:

| Tình huống | Kết quả mong đợi |
|---|---|
| Client gọi version đang deprecated | Request vẫn theo chính sách hỗ trợ; response có header và link deprecation chính xác |
| Ngày sunset chưa được công bố | Không phát ra ngày sunset giả hoặc không nhất quán |
| Client không có contact đã đăng ký | Dashboard đánh dấu owner chưa xác định và tạo công việc bổ sung inventory |
| Client có traffic theo mùa | Không kết luận đã migration chỉ vì khoảng quan sát ngắn không có request |
| Client dùng endpoint cũ sau sunset | Nhận lỗi machine-readable đã công bố, không phát sinh side effect |
| Client gửi request ghi có retry | Idempotency và semantics được giữ đúng; không tự chuyển route ngoài hợp đồng |
| Exception hết hạn | Cảnh báo và thực thi chính sách thu hồi đã phê duyệt |
| Ngày sunset thay đổi | Portal, header, email, dashboard và tài liệu cùng được cập nhật |
| Metric chứa client ID không hợp lệ hoặc cardinality cao | Hệ thống telemetry giới hạn và xử lý an toàn |
| API cũ có lỗ hổng nghiêm trọng | Kích hoạt quy trình rút ngắn, giảm thiểu hoặc chặn khẩn cấp |

Theo dõi các chỉ số: số client còn dùng version cũ, tỷ lệ migration theo tuần, request volume còn lại, số exception, số client chưa xác định owner, số lỗi sau sunset và thời gian xử lý yêu cầu hỗ trợ. Dashboard phải hỗ trợ lọc theo client, tenant, version, endpoint và môi trường mà không làm lộ dữ liệu của client khác.

## Những sai lầm thường gặp

- Chỉ đăng changelog công khai nhưng không gửi thông báo tới application owner đã đăng ký.
- Công bố ngày sunset mà chưa có version thay thế hoặc migration guide.
- Dùng `User-Agent` hoặc IP làm định danh client duy nhất.
- Xem không có traffic trong thời gian ngắn là bằng chứng client đã ngừng sử dụng.
- Gửi cảnh báo deprecation bằng cách thêm field tùy ý vào response đang được client parse nghiêm ngặt.
- Thay đổi ngày sunset ở một nơi nhưng quên cập nhật header, portal hoặc dashboard.
- Gia hạn exception liên tục mà không có owner, biện pháp giảm thiểu và ngày hết hạn.
- Tự động chuyển request ghi sang version mới dù semantics hoặc quyền truy cập đã thay đổi.
- Tiếp tục giữ API có lỗ hổng nghiêm trọng chỉ vì lịch thông báo thông thường chưa kết thúc.
- Log request đầy đủ để tìm client, vô tình lưu token, thông tin cá nhân hoặc dữ liệu giao dịch.

## Checklist trước khi công bố và sunset

- [ ] Phạm vi deprecation xác định rõ version, endpoint, method, field hoặc behavior.
- [ ] Có version thay thế và migration guide với ví dụ request/response.
- [ ] Khác biệt về authentication, authorization, dữ liệu và semantics được mô tả.
- [ ] Có ngày công bố, ngày deprecation, ngày sunset, timezone và các mốc nhắc nhở.
- [ ] Client registry có application ID, owner và contact phù hợp.
- [ ] Portal, changelog, email và dashboard dùng cùng một nguồn lịch.
- [ ] Header `Deprecation`, `Sunset` và link tài liệu được phát ra chính xác khi áp dụng.
- [ ] Telemetry phân biệt client đã migration, còn usage, không quan sát được và chưa xác định owner.
- [ ] Exception có phạm vi, owner, biện pháp giảm thiểu, phê duyệt và ngày hết hạn.
- [ ] Contract/security test và smoke test của version thay thế đã đạt.
- [ ] Runbook sunset định nghĩa status/error body, metric, retry và hỗ trợ.
- [ ] Quy trình khẩn cấp cho lỗ hổng nghiêm trọng có thể rút ngắn lịch thông báo an toàn.

Deprecation là một quy trình quản lý thay đổi có thời hạn và có bằng chứng. Khi tổ chức xác định đúng phạm vi, công bố lịch nhất quán, thông báo tới đúng client, đo lường mức độ sử dụng và kiểm thử hành vi sau sunset, việc loại bỏ API cũ sẽ ít gây gián đoạn hơn và giúp hệ thống loại bỏ dần các cơ chế không còn đáp ứng yêu cầu bảo mật.
