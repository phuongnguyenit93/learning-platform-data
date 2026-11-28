# API inventory

## 1. Không thể bảo vệ đầy đủ một bề mặt chưa được nhận diện

Một dịch vụ có thể đã áp dụng xác thực, phân quyền và rate limit cho API chính thức nhưng vẫn còn hostname thử nghiệm, phiên bản cũ hoặc đường gọi trực tiếp tới backend. Nếu những đường đó không nằm trong danh mục, nhóm phát triển khó biết cần áp dụng yêu cầu bảo mật ở đâu; nhóm vận hành cũng khó xác định phạm vi ảnh hưởng khi có sự cố.

**API inventory** là danh mục có quản lý về các API, thao tác, phiên bản, nơi triển khai, đường truy cập và luồng dữ liệu liên quan. Trong thiết kế yêu cầu bảo mật, danh mục không chỉ trả lời “có những URL nào”, mà còn trả lời:

- Ai chịu trách nhiệm về thao tác và dữ liệu?
- API được triển khai ở môi trường và ranh giới mạng nào?
- Ai được phép gọi, bằng cơ chế danh tính nào?
- Dữ liệu nào đi vào, đi ra hoặc được chia sẻ với bên khác?
- Những yêu cầu bảo mật nào áp dụng, và bằng chứng thực thi ở đâu?
- Phiên bản nào đang được hỗ trợ, sắp ngừng hoặc đã ngừng?

Danh mục thiếu phiên bản cũ, host hoặc luồng dữ liệu nhạy cảm là một dạng khoảng trống được nêu trong [OWASP API9:2023 Improper Inventory Management](https://api-security.owasp.org/editions/2023/en/0xa9-improper-inventory-management/). Một danh sách đẹp trong tài liệu chưa chứng minh bề mặt triển khai đã được quản lý đầy đủ.

Mục tiêu của bài học là chuyển việc “có inventory” thành yêu cầu đo được: phạm vi nào phải có mặt, dữ liệu nào bắt buộc, cách đối chiếu với thực tế và hành vi khi phát hiện sai lệch. Inventory là đầu vào cho kiểm soát bảo mật, không tự thay thế các kiểm soát đó.

## 2. Phân biệt API logic, deployment và đường phơi lộ

### 2.1. Một thao tác có thể xuất hiện ở nhiều nơi

Giả sử dịch vụ báo cáo có thao tác đọc một báo cáo:

```text
GET /v1/reports/{reportId}
```

Thao tác này có thể xuất hiện qua:

```text
https://api.example.test/v1/reports/{reportId}
https://partner-api.example.test/v1/reports/{reportId}
https://beta-api.example.test/v1/reports/{reportId}
```

Các địa chỉ trên là ví dụ giả định. Dù cùng gọi một handler, từng đường có thể đi qua gateway, chính sách mạng hoặc cấu hình xác thực khác nhau. Gộp chúng thành một dòng chỉ ghi “read report API” sẽ làm mất thông tin cần để đánh giá bảo mật.

Ngược lại, một endpoint HTTP có thể phục vụ nhiều thao tác nghiệp vụ. Một đường GraphQL không đại diện cho toàn bộ quyền và dữ liệu của mọi field; một kết nối WebSocket có thể mang nhiều loại message. Mức kiểm kê phải phù hợp với giao thức và rủi ro.

### 2.2. Mô hình ba lớp

Một cách tổ chức hữu ích:

| Lớp | Mô tả | Ví dụ |
| --- | --- | --- |
| API hoặc hợp đồng logic | Chức năng, phiên bản hợp đồng, chủ sở hữu, mô hình dữ liệu | Reporting API v1 |
| Thao tác | Hành động cụ thể và yêu cầu bảo mật của hành động đó | Đọc báo cáo; phê duyệt; tạo job xuất |
| Deployment và exposure | Môi trường, host, route, đường mạng và thành phần thực thi | Production qua gateway đối tác |

Quan hệ thường là một thao tác logic có nhiều deployment hoặc exposure. Inventory cần giữ quan hệ này để trả lời một yêu cầu như “bản vá phân quyền đã bao phủ mọi đường gọi thao tác đọc báo cáo chưa?”.

Nếu cần một cấu trúc gọn, có thể lưu các lớp trong cùng một bản ghi hoặc tài liệu. Điều quan trọng là không làm mất phân biệt giữa chức năng và nơi nó được mở ra.

### 2.3. Định danh phải đủ ổn định và không làm lộ dữ liệu

Một bản ghi nên có ID nội bộ ổn định. Với HTTP, khóa đối chiếu exposure có thể bao gồm:

```text
Môi trường
+ giao thức / listener hoặc host
+ HTTP method
+ route template
+ điều kiện chọn phiên bản nếu có
```

Không phải API nào cũng đặt phiên bản trong URL. Phiên bản có thể được chọn bằng header hoặc media type; nếu hai hợp đồng dùng cùng method và path, thông tin lựa chọn đó phải nằm trong mô hình đối chiếu.

Lưu route template như `/reports/{reportId}`, thay vì biến mỗi `/reports/123` và `/reports/456` thành một API riêng. Việc chuẩn hóa nên dựa vào route đã được nhận diện, không chỉ thay mọi đoạn số bằng một placeholder: một đoạn số có thể là phiên bản hoặc một phần tên route cố định.

Không đưa token, query string chứa dữ liệu cá nhân hoặc body thực vào khóa inventory. Ví dụ chứng minh có thể được làm sạch và tham chiếu tới nơi có quyền truy cập phù hợp.

## 3. Xác định phạm vi: không chỉ các API công khai

Một yêu cầu kiểm kê nên ghi rõ các nhóm nằm trong phạm vi:

| Nhóm | Vì sao cần ghi nhận |
| --- | --- |
| API Internet-facing | Có bề mặt truy cập từ ngoài ranh giới mạng |
| API đối tác | Có danh tính, thỏa thuận và luồng dữ liệu riêng |
| API nội bộ giữa dịch vụ | Vẫn cần danh tính, quyền, chủ sở hữu và giới hạn |
| API quản trị | Có tác động cấu hình hoặc quyền cao |
| Health, debug, metrics, tài liệu tương tác | Có thể bộc lộ thông tin hoặc chức năng ngoài dự kiến |
| API thử nghiệm, staging, preview | Có thể vô tình liên kết dữ liệu thật hoặc cấu hình yếu hơn |
| Phiên bản cũ đang chạy | Vẫn là đường truy cập cho tới khi thực sự ngừng |
| Webhook và callback | Tạo bề mặt nhận dữ liệu hoặc đường gọi ra |
| API bên thứ ba được tích hợp | Có luồng chia sẻ dữ liệu và phụ thuộc cần quản lý |

“Public” cần được định nghĩa cẩn thận. Một API truy cập qua Internet có thể vẫn bắt buộc xác thực; “cho phép anonymous” là một quyết định khác. Inventory nên tách vị trí phơi lộ mạng khỏi yêu cầu danh tính để tránh kết luận sai.

Với endpoint quản trị, danh mục phải thể hiện mục đích, người được gọi và ranh giới bảo vệ. Việc hạn chế phơi lộ management endpoint được đề cập trong [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#management-endpoints).

Không phải mọi health probe đều phải dùng cùng profile xác thực như thao tác nghiệp vụ. Nếu cho phép một probe không xác thực, cần ghi rõ dữ liệu tối thiểu được trả, đường mạng được phép và người phê duyệt ngoại lệ đó. Một ngoại lệ có phạm vi không được lan sang các endpoint quản trị khác.

## 4. Metadata tối thiểu để hỗ trợ yêu cầu bảo mật

### 4.1. Những trường cần trả lời được

Không nên bắt đầu bằng hàng trăm trường ít ai cập nhật. Một tập tối thiểu có ý nghĩa:

| Nhóm metadata | Nội dung cần có |
| --- | --- |
| Định danh | API ID, operation ID nội bộ, service, phiên bản hợp đồng |
| Mục đích | Chức năng nghiệp vụ và loại tác động |
| Quyền sở hữu | Nhóm chịu trách nhiệm, đầu mối thay thế hoặc tuyến escalation |
| Deployment | Môi trường, release hoặc artifact, host và route |
| Exposure | Public network, partner network, internal hoặc management |
| Consumer | Loại chủ thể và nhóm tích hợp được phép |
| Danh tính | Profile xác thực và nơi kiểm chứng |
| Quyền | Tham chiếu yêu cầu chức năng, đối tượng và trường dữ liệu |
| Dữ liệu | Phân loại dữ liệu và hướng trao đổi |
| Tài nguyên | Tham chiếu giới hạn request, tần suất và công việc nền |
| Vòng đời | Trạng thái hỗ trợ, kế hoạch thay thế, điều kiện ngừng |
| Bằng chứng | Nguồn khai báo, nguồn quan sát, thời điểm và phạm vi |

Không lưu secret để làm bản ghi “đầy đủ”. Có thể tham chiếu profile credential hoặc secret manager, nhưng bản thân token, private key và mật khẩu không thuộc dữ liệu inventory thông thường.

### 4.2. Tách điều được yêu cầu khỏi điều đã được xác minh

Một trường `authentication: required` có thể chỉ là ý định trong thiết kế. Để tránh hiểu nhầm, tách các lớp:

```text
Declared: hợp đồng hoặc chủ sở hữu yêu cầu gì?
Deployed: cấu hình hoặc deployment đang khai báo gì?
Verified: bằng chứng nào đã xác minh hành vi nào?
```

Ví dụ, OpenAPI khai báo bearer authentication không đủ chứng minh route runtime từ chối request thiếu credential. Cấu hình gateway có kiểm tra token cũng chưa chứng minh phân quyền báo cáo theo tenant đã đúng.

`verified` nên có phạm vi, thời điểm, release và tham chiếu bằng chứng. Không dùng một boolean `secure: true` để đại diện cho mọi thuộc tính bảo mật. Một ca kiểm tra xác thực không tự kiểm chứng quyền đối tượng, hạn mức hoặc bảo vệ dữ liệu.

### 4.3. Trạng thái chưa biết phải được thể hiện thật

Nếu chưa biết owner hoặc chưa xác định được loại dữ liệu, ghi `unknown` hoặc trạng thái cần xử lý có chủ sở hữu theo dõi. Không tự gán “internal”, “non-sensitive” hoặc “approved” để vượt kiểm tra completeness.

Một bản ghi có nhiều thông tin chưa xác minh vẫn có ích nếu nó phản ánh đúng phát hiện. Điều nguy hiểm là làm sạch dashboard bằng cách biến thiếu bằng chứng thành đã đáp ứng.

## 5. Ví dụ bản ghi inventory phục vụ thiết kế

Đoạn YAML sau chỉ minh họa cấu trúc dữ liệu; tên hệ thống, định danh và bằng chứng đều giả định:

```yaml
apiId: reporting-api
operationId: report-read-v1
purpose: Đọc một báo cáo trong phạm vi được cấp
service: report-service
contractVersion: v1
owner:
  team: reporting-team
  escalationGroup: platform-oncall
data:
  classification: confidential
  tenantScoped: true
  categories:
    - business_report_content
    - report_author_identifier
requirements:
  identity: API-ID-01
  objectAuthorization: API-AZ-REPORT-01
  responseFields: API-DATA-REPORT-02
  requestLimits: API-SIZE-REPORT-01
  rateLimits: API-RATE-REPORT-01
exposures:
  - exposureId: report-read-prod-public-v1
    environment: production
    transport: HTTPS
    host: api.example.test
    method: GET
    routeTemplate: /v1/reports/{reportId}
    audience: internet_authenticated_clients
    networkBoundary: public_gateway
    release: report-release-example-A
    declaredAuthenticationProfile: customer-access-token
    deployedAuthenticationEvidence: gateway-snapshot-example-A
    behaviorEvidence:
      authentication: test-run-example-auth-A
      objectAuthorization: not_yet_verified
lifecycle:
  supportState: active
  approvalState: approved
  deploymentState: deployed
evidence:
  declaredSource: contract-example-A
  deploymentSource: deployment-snapshot-example-A
  snapshotState: complete_for_declared_scope
  collectedAt: '2026-11-27T09:00:00+07:00'
```

Giá trị `objectAuthorization: not_yet_verified` không phủ nhận yêu cầu phân quyền; nó cho biết chưa có bằng chứng được liên kết cho thuộc tính đó. Điều này giúp nhóm phân biệt việc đã thiết kế với việc đã kiểm chứng.

Nếu cùng thao tác có một exposure đối tác, cần thêm bản ghi exposure riêng với profile phù hợp. Không suy rằng mọi đường gọi đã được xác minh từ bằng chứng của đường public.

Các trạng thái cũng cần tách biệt. Một thao tác có thể được phê duyệt nhưng chưa deploy; một route có thể đang chạy nhưng chưa được phê duyệt; một phiên bản deprecated vẫn có thể đang phục vụ. Một trường trạng thái duy nhất khó biểu diễn đúng cả ba chiều này.

## 6. Thu thập inventory từ nhiều nguồn có giới hạn khác nhau

### 6.1. Nguồn khai báo và nguồn thực tế bổ sung cho nhau

| Nguồn | Điểm mạnh | Khoảng trống cần nhớ |
| --- | --- | --- |
| Hợp đồng OpenAPI hoặc tài liệu tương đương | Mục đích, schema, thao tác và security declaration | Có thể chưa deploy hoặc đã lỗi thời |
| Route trong ứng dụng | Thấy handler và thao tác được mã hỗ trợ | Không tự biết đường mạng nào phơi lộ |
| Gateway, ingress, load balancer | Thấy host, route và chính sách tại biên | Có thể không thấy đường gọi nội bộ khác |
| Hạ tầng và deployment manifest | Gắn môi trường, service và release | Cấu hình mong muốn có thể lệch thực tế |
| DNS và danh mục host thuộc tổ chức | Hỗ trợ tìm địa chỉ và alias cần đối chiếu | Có tên không đồng nghĩa có API đang chạy |
| Telemetry runtime | Có bằng chứng hoạt động trong cửa sổ quan sát | Không có traffic không chứng minh endpoint đã biến mất |
| Khai báo owner và hệ thống tích hợp | Cho biết mục đích, consumer và chia sẻ dữ liệu | Phụ thuộc chất lượng cập nhật và xác minh |

Không có nguồn đơn lẻ nào tự chứng minh inventory đã bao phủ mọi thứ. Một route trong source có thể không được build; một route tại gateway có thể trỏ tới backend đã ngừng; một đường truy cập trực tiếp có thể không xuất hiện trong hợp đồng public.

Việc thu thập cần diễn ra trong phạm vi hệ thống được phép và theo quy trình vận hành. Discovery không tự cho phép thử tải, gọi thao tác thay đổi dữ liệu hoặc mở rộng kiểm tra sang hệ thống bên ngoài không thuộc phạm vi.

### 6.2. Quan sát URL không đồng nghĩa phát hiện operation thật

Một access log có request tới `/admin/delete-everything` chưa chứng minh hệ thống có endpoint đó. Client có thể gửi đường dẫn tùy ý và nhận 404. Nếu tự động biến mọi URL quan sát thành API, inventory có thể bị làm nhiễu hoặc phình to theo đầu vào bên ngoài.

Nên ưu tiên route ID hoặc template do router/gateway xác định khi có thể. Những quan sát chưa khớp route được ghi thành ứng viên cần xác minh, có nguồn và độ tin cậy, thay vì tự chuyển thành operation được phê duyệt.

Tương tự, một HTTP status không chứng minh đầy đủ chức năng. `401` có thể do lớp bảo vệ mặc định; `200` có thể là trang fallback. Cần đối chiếu với deployment và cấu hình để xác định quan sát nói lên điều gì.

### 6.3. Thu thập tối thiểu dữ liệu cần thiết

Inventory thường không cần body thực, token hoặc giá trị query. Có thể lưu metadata đã chuẩn hóa và số liệu tổng hợp; bằng chứng chi tiết được giữ ở nơi có quyền truy cập thích hợp nếu thực sự cần.

Nếu route chứa định danh khách hàng hoặc dữ liệu nhạy cảm, quá trình chuẩn hóa và kiểm soát truy cập inventory là một phần của thiết kế. Không tạo một kho tập trung chứa đầy URL có secret chỉ để phục vụ quản lý bề mặt tấn công.

## 7. Đối chiếu khai báo, deployment và quan sát

### 7.1. Xác định rõ các tập dữ liệu

Giả sử trong một scope cụ thể:

```text
I = các exposure đã được ghi nhận trong inventory
A = các exposure đã được phê duyệt
D = các exposure được xác định là đang deploy qua nguồn triển khai
O = các operation đã nhận diện trong telemetry của cửa sổ quan sát
```

Các tập phải dùng cùng quy tắc định danh, môi trường và thời điểm hoặc cửa sổ phù hợp. Không so snapshot production hôm nay với danh mục staging tuần trước rồi gọi mọi chênh lệch là rủi ro.

Một số phép đối chiếu:

| Sai lệch | Diễn giải ban đầu |
| --- | --- |
| `D - I` | Có deployment chưa được ghi nhận trong danh mục |
| `D - A` | Có deployment chưa có phê duyệt tương ứng |
| `O - I` | Có hoạt động đã nhận diện chưa khớp danh mục; cần xác minh nguồn và route |
| `I - D` | Bản ghi chưa có deployment trong snapshot này; có thể là planned, retired hoặc thiếu dữ liệu |
| Cùng ID nhưng metadata khác | Có drift về host, version, auth profile, owner hoặc thuộc tính khác |

`I - D` không tự có nghĩa nên xóa bản ghi. Nó có thể mô tả API dự kiến triển khai hoặc API đã ngừng nhưng cần giữ lịch sử. Nó cũng có thể do collector chưa đọc được một cluster.

### 7.2. Snapshot phải có thông tin chất lượng

Mỗi lần thu thập nên ghi thời điểm, nguồn, phạm vi và kết quả hoàn tất. Nếu collector lỗi, không thay toàn bộ inventory bằng danh sách rỗng rồi kết luận không còn API.

Một yêu cầu minh họa:

> Khi nguồn gateway hoặc deployment không thu thập hoàn chỉnh, hệ thống phải giữ snapshot hợp lệ trước đó, đánh dấu độ mới và phần phạm vi chưa được xác minh. Không tự chuyển các exposure thiếu trong lần thu thập lỗi sang trạng thái retired.

Lưu cả thời điểm thu thập và thời điểm bằng chứng được quan sát nếu hai thời điểm khác nhau. Một lần import mới không làm cho dữ liệu quan sát cũ trở thành bằng chứng runtime mới.

### 7.3. Sai lệch cần một workflow xử lý

Một phát hiện nên có mã, mức ưu tiên theo rủi ro, nguồn bằng chứng, người chịu trách nhiệm và thời hạn phản hồi. Ví dụ, một route nội bộ mới chưa có mô tả không nhất thiết có cùng ưu tiên với một host Internet-facing chứa dữ liệu thật và không rõ owner.

Quy trình có thể là:

```text
Phát hiện ứng viên
    -> xác minh nguồn và phạm vi
    -> xác định owner / nhóm tiếp nhận
    -> đánh giá phơi lộ và dữ liệu
    -> phê duyệt, bổ sung kiểm soát hoặc thu hẹp bề mặt
    -> kiểm chứng kết quả và cập nhật bằng chứng
```

Không tự xóa endpoint chỉ vì nó chưa có trong danh mục. Việc ngừng một route có thể làm gián đoạn nghiệp vụ và cần theo quyền thay đổi đã có. Ngược lại, cập nhật inventory để ghi nhận một route không tự cấp phê duyệt cho route đó.

## 8. OpenAPI hỗ trợ inventory nhưng không phải bằng chứng thực thi

OpenAPI mô tả HTTP API với server, path, operation, parameter, schema và khai báo security. Tài liệu có thể là một nguồn quan trọng, nhưng cần hiểu đúng semantics của từng trường.

Ví dụ trích đoạn theo OpenAPI 3.1.1:

```yaml
openapi: 3.1.1
info:
  title: Reporting API
  version: 1.0.0
servers:
  - url: https://api.example.test
security:
  - customerToken: []
paths:
  /v1/reports/{reportId}:
    get:
      operationId: readReport
      deprecated: false
      parameters:
        - name: reportId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Báo cáo trong phạm vi được phép
components:
  securitySchemes:
    customerToken:
      type: http
      scheme: bearer
```

Đây là mô tả hợp đồng minh họa. Nó không triển khai middleware xác thực hoặc chính sách tenant. Đặc biệt:

- Operation có thể khai báo `security` để override cấp trên; một mảng rỗng có thể gỡ khai báo security cấp trên.
- Operation có thể override `servers`; không chỉ lấy danh sách server ở root rồi bỏ qua các cấp bên dưới.
- `deprecated: true` thông báo operation không còn được khuyến nghị sử dụng, không tự tắt route runtime.

Các quy tắc trên được nêu trong [OpenAPI Specification 3.1.1, Operation Object](https://spec.openapis.org/oas/v3.1.1.html#operation-object).

Vì vậy, công cụ lấy inventory từ OpenAPI cần xử lý kế thừa, override và tham chiếu đúng phiên bản đặc tả được dùng. Chỉ kiểm tra chuỗi `security` xuất hiện đâu đó trong tài liệu là không đủ để suy ra mọi operation đã được bảo vệ.

ID trong tài liệu cũng cần được đặt trong namespace phù hợp khi nhập danh mục toàn tổ chức. Hai dịch vụ khác nhau có thể cùng dùng tên `getStatus`; không nên coi chúng là một operation toàn cục chỉ vì tên giống nhau.

## 9. Giao thức khác và luồng dữ liệu ra ngoài

### 9.1. Chọn đơn vị kiểm kê theo giao thức

| Kiểu giao tiếp | Metadata bổ sung có ích |
| --- | --- |
| HTTP theo tài nguyên | Method, path template, host, điều kiện version |
| GraphQL | Endpoint, schema version, nhóm operation hoặc field nhạy cảm, policy tương ứng |
| gRPC | Service, method, package/version và deployment |
| WebSocket | Điểm thiết lập kết nối, loại message và quy tắc quyền theo message |
| Giao tiếp sự kiện | Broker/server, channel, message, producer/consumer và quyền send/receive |
| Webhook | Sự kiện, endpoint nhận, bên gửi, cách xác thực và chính sách đích |

Không nhất thiết tạo một bản ghi cho mọi query GraphQL do client gửi hoặc mọi giá trị topic động. Cần một mô hình hữu hạn, có cấu trúc và đủ chi tiết để gắn yêu cầu bảo mật; dữ liệu quan sát thô không nên trở thành khóa vô hạn của danh mục.

Với hệ thống sự kiện, AsyncAPI có thể là nguồn mô tả hợp đồng giữa sender và receiver, gồm message và các thành phần giao tiếp. Xem [AsyncAPI Document Introduction](https://www.asyncapi.com/docs/concepts/asyncapi-document). Inventory vẫn cần liên kết mô tả đó với deployment, quyền và consumer thực tế.

### 9.2. Inventory cả phụ thuộc và chia sẻ dữ liệu

Một thao tác tạo báo cáo có thể gọi dịch vụ phân tích bên ngoài. Danh mục cần cho biết vai trò của tích hợp, loại dữ liệu được trao đổi, mục đích được phép và nhóm chịu trách nhiệm khi có sự cố.

Ví dụ một liên kết luồng dữ liệu có thể mô tả:

```text
report-export-v1
  -> gọi dịch vụ render của đối tác
  -> gửi nội dung báo cáo đã được chọn theo quyền
  -> nhận artifact
  -> lưu artifact trong vùng storage của tenant
```

Cần phân biệt API do tổ chức cung cấp với API do bên ngoài cung cấp; chúng có owner kỹ thuật, khả năng quan sát và quyền thay đổi khác nhau. Một tham chiếu nhà cung cấp không có nghĩa nhóm nội bộ có quyền kiểm tra chủ động mọi endpoint của họ.

Khi có sự cố ở đối tác, inventory phải hỗ trợ tìm những thao tác và nhóm dữ liệu có liên quan. Nếu chỉ lưu URL tích hợp mà không biết dữ liệu gì được chia sẻ, danh mục chưa đủ để hỗ trợ đánh giá phạm vi ảnh hưởng.

## 10. Vòng đời: deprecated chưa phải retired

### 10.1. Phải có trạng thái và điều kiện chuyển trạng thái

Một mô hình vòng đời minh họa:

```text
Proposed -> Approved -> Deployed / Active -> Deprecated
                                            |
                                            v
                                  Retirement planned -> Retired
```

Trong mô hình dữ liệu thực tế, approval state và deployment state có thể tách riêng như ví dụ trước. Sơ đồ chỉ cho thấy các mốc cần quản lý, không bắt mọi sản phẩm dùng đúng một enum tuyến tính.

Một phiên bản deprecated vẫn phải được bảo vệ khi còn chạy. Không giảm mức xác thực hoặc bỏ vá lỗi chỉ vì client được khuyến nghị chuyển sang v2. Phiên bản mới và cũ có thể còn dùng chung dữ liệu; lỗ hổng của bản cũ vẫn ảnh hưởng tài sản hiện tại.

### 10.2. Ngừng API là một thay đổi có bằng chứng

Kế hoạch retirement nên xác định:

- Owner, lý do và phạm vi phiên bản hoặc exposure bị ngừng.
- Consumer đã biết và kế hoạch chuyển đổi.
- Mốc ngừng theo thời điểm rõ ràng, có múi giờ khi cần.
- Cách xử lý route, gateway, backend và credential dành riêng.
- Hành vi công khai sau khi ngừng theo hợp đồng.
- Bằng chứng không còn đường truy cập ngoài ý muốn.
- Điều kiện rollback và cách giữ kiểm soát nếu phải khôi phục.

Không chỉ xóa API khỏi tài liệu rồi đánh dấu retired. Một hostname cũ, đường gọi đối tác hoặc route trực tiếp có thể còn hoạt động. Việc ngừng cần kiểm chứng qua những đường đã nằm trong scope và lưu lại kết quả.

Ngược lại, không xóa lịch sử bản ghi chỉ để dashboard không còn API cũ. Có thể giữ tombstone hoặc trạng thái lịch sử theo chính sách lưu giữ để truy vết deployment, consumer và sự cố trước đây.

### 10.3. Không có traffic chưa đủ để ngừng

Một API báo cáo năm có thể ít được gọi; một endpoint phục hồi có thể chỉ dùng khi sự cố. Không quan sát thấy traffic trong một tuần không chứng minh không có consumer.

Quyết định ngừng nên kết hợp telemetry, khai báo tích hợp, owner xác nhận và chính sách chuyển đổi. Cửa sổ quan sát và giới hạn của nguồn dữ liệu phải được ghi rõ, đặc biệt khi log bị sampling hoặc chưa bao phủ tất cả đường vào.

## 11. Biến inventory thành yêu cầu đo được

Các yêu cầu dưới đây là mẫu cho một nền tảng giả định. Ngưỡng và thời hạn phải được thống nhất theo nhịp triển khai và mức rủi ro của hệ thống thật.

| Mã | Yêu cầu mẫu | Cách nghiệm thu |
| --- | --- | --- |
| INV-01 | Mỗi exposure production được phê duyệt phải có owner, môi trường, version, purpose và classification | Đối chiếu metadata bắt buộc với deployment snapshot trong scope |
| INV-02 | Thay đổi route hoặc profile danh tính phải tạo cập nhật inventory gắn release | Triển khai một thay đổi kiểm soát và kiểm tra bản ghi |
| INV-03 | Deployment chưa khớp bản ghi được phê duyệt phải tạo phát hiện có owner xử lý | Đưa một route thử nghiệm vào môi trường kiểm thử có kiểm soát |
| INV-04 | Snapshot lỗi không được làm biến mất exposure đã biết | Mô phỏng collector lỗi hoặc chỉ trả một phần dữ liệu |
| INV-05 | Mỗi phiên bản deprecated còn chạy phải có owner và kế hoạch hỗ trợ hoặc retirement | Rà soát tập deprecated đang deploy |
| INV-06 | Trạng thái retired phải có bằng chứng theo đường phơi lộ đã biết | Kiểm tra route, deployment và kết quả xác minh ngừng |
| INV-07 | Inventory không chứa credential hoặc payload nhạy cảm không cần thiết | Kiểm tra schema, nguồn nhập và quyền truy cập |
| INV-08 | Thuộc tính verified phải tham chiếu bằng chứng có phạm vi, release và thời điểm | Chọn mẫu và đối chiếu nội dung bằng chứng |
| INV-09 | Luồng chia sẻ dữ liệu với bên ngoài phải có mục đích và owner | Truy vết một tích hợp từ thao tác tới dữ liệu và đối tác |

Ví dụ một yêu cầu có thời hạn minh họa:

> Sau mỗi deployment production, thay đổi route phải được ghi nhận trong inventory trong vòng 15 phút. Nếu nguồn thu thập không hoàn tất, hệ thống phải hiển thị trạng thái chưa đồng bộ thay vì coi snapshot mới là đầy đủ. Exposure chưa được phê duyệt phải có phát hiện và tuyến tiếp nhận đã xác định.

Mốc 15 phút không phải chuẩn chung. Một hệ thống có kiểm soát trước deploy có thể yêu cầu bản ghi sẵn sàng trước khi mở route; một nền tảng discovery định kỳ có thể cần một thời hạn khác. Cần mô tả cả hành vi trước và sau khi phát hiện, không chỉ thời gian cập nhật giao diện.

## 12. Tích hợp vào thay đổi và triển khai

### 12.1. Trước khi mở thêm API

Một thay đổi thêm operation hoặc exposure nên cung cấp metadata tối thiểu và tham chiếu yêu cầu bảo mật. Các quyết định quan trọng gồm dữ liệu, consumer, profile danh tính, quyền, giới hạn và owner.

Có thể dùng quality gate để chặn thay đổi thiếu trường bắt buộc theo chính sách đã phê duyệt. Tuy nhiên, việc parse metadata thành công không chứng minh kiểm soát runtime đã hoạt động. Gate tài liệu và kiểm chứng hành vi là hai bằng chứng bổ sung.

Nếu có quy trình khẩn cấp, ngoại lệ cần có scope, owner, thời hạn và kiểm soát bù. Không điền một owner giả hoặc tự gán classification thấp để làm gate xanh.

### 12.2. Sau deployment

Đối chiếu deployment với inventory để xác nhận route, host, release và trạng thái phơi lộ mong đợi. Khi có canary, blue/green hoặc nhiều region, snapshot phải nhận diện các deployment cùng tồn tại; không gọi mọi instance cũ trong giai đoạn chuyển đổi là zombie API.

Nếu cùng một exposure chuyển backend trong một đợt phát hành, danh mục cần giữ được lịch sử đủ để hiểu bằng chứng kiểm thử áp dụng cho release nào. Không chuyển toàn bộ trạng thái verified từ release trước sang release mới mà không đánh giá thuộc tính đã thay đổi.

### 12.3. Khi đổi owner hoặc kết thúc một dự án

Owner nên là một nhóm hoặc chức năng có tuyến liên lạc duy trì được, thay vì chỉ một cá nhân có thể rời dự án. Chuyển owner phải có xác nhận tiếp nhận trách nhiệm đối với API, dữ liệu và các phát hiện chưa xử lý.

Khi một dự án kết thúc, cần rà các host, route, phiên bản, webhook, credential và tích hợp của nó. Việc lưu trữ repository không chứng minh mọi deployment ngoài repository đã dừng.

## 13. Đo lường đúng để tránh cảm giác đầy đủ giả tạo

### 13.1. Xác định mẫu số

Một chỉ số hữu ích có thể là:

```text
Tỷ lệ metadata đầy đủ
  = số exposure đang deploy đã biết có đủ metadata bắt buộc
    / tổng số exposure đang deploy đã biết trong scope đo
```

Từ “đã biết” và scope rất quan trọng. Chỉ số 100% không chứng minh không còn API chưa được phát hiện. Nó chỉ chứng minh tập đã được nguồn dữ liệu hiện tại nhận diện có metadata theo quy tắc đo.

Tương tự, tỷ lệ có tài liệu không đồng nghĩa tỷ lệ đã kiểm chứng xác thực hoặc phân quyền. Không gộp các thuộc tính đó thành một phần trăm chung rồi dùng nó như bằng chứng “API an toàn”.

### 13.2. Bộ chỉ số có ý nghĩa vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| Exposure chưa khớp inventory | Khoảng trống giữa deployment đã biết và danh mục |
| Exposure chưa được phê duyệt | Khoảng trống quản trị, khác với thiếu tài liệu |
| Bản ghi không có owner hợp lệ | Khó xử lý sự cố và yêu cầu thay đổi |
| Snapshot quá hạn hoặc nguồn thu thập lỗi | Mức độ tin cậy và độ mới của quan sát |
| Phiên bản deprecated quá hạn kế hoạch | Rủi ro vòng đời cần xử lý |
| Security metadata drift | Khác biệt giữa yêu cầu và cấu hình hoặc bằng chứng |
| Phát hiện chưa được tiếp nhận đúng hạn | Chất lượng workflow xử lý sai lệch |

Khi nguồn dữ liệu bị mất, dashboard phải thể hiện chất lượng đo giảm. Một số đếm endpoint giảm đột ngột không nên được chúc mừng như giảm bề mặt tấn công nếu collector đang lỗi.

Không dùng độ mới của bản ghi thay cho độ mới của bằng chứng. Chỉnh sửa tên owner hôm nay không làm ca kiểm tra phân quyền từ sáu tháng trước trở thành xác minh mới.

## 14. Kế hoạch nghiệm thu cho inventory

Các ca dưới đây là kế hoạch kiểm chứng cho hệ thống inventory giả định, chưa phải kết quả kiểm thử của một sản phẩm đã triển khai.

| Ca | Điều kiện tạo ra | Kết quả cần quan sát |
| --- | --- | --- |
| Route mới hợp lệ | Thêm operation có metadata và phê duyệt | Bản ghi đúng ID, owner, release và exposure |
| Route ngoài danh mục | Deployment có route chưa được ghi nhận | Phát hiện chênh lệch, không tự phê duyệt |
| Alias host | Cùng operation được mở thêm host | Ghi nhận exposure mới, giữ liên kết operation |
| Method mới | Thêm POST trên path đã có GET | Không gộp hai thao tác thành một |
| Version qua header | Cùng host/path nhưng hợp đồng khác | Giữ điều kiện chọn phiên bản trong mô hình |
| Override contract | Operation thay security hoặc server so với root | Công cụ lấy metadata đọc đúng giá trị có hiệu lực |
| URL giả trong log | Client gọi path không khớp handler | Chỉ ghi ứng viên theo chính sách, không tự tạo API được phê duyệt |
| Collector lỗi | Không đọc được một nguồn hoặc chỉ có snapshot một phần | Giữ dữ liệu trước, đánh dấu stale hoặc partial đúng phạm vi |
| Không có traffic | Một operation đã deploy không xuất hiện trong cửa sổ quan sát | Không tự chuyển sang retired |
| Retire trên tài liệu | Xóa operation khỏi tài liệu nhưng route còn chạy | Phát hiện deployment còn tồn tại |
| Đổi auth profile | Cấu hình thực tế lệch khai báo | Tạo drift và liên kết release gây thay đổi |
| Luồng đối tác | Thêm chia sẻ một nhóm dữ liệu nhạy cảm | Có mục đích, owner, classification và tham chiếu đánh giá |
| Chuyển owner | Nhóm cũ bàn giao cho nhóm mới | Có trách nhiệm mới rõ và lịch sử thay đổi |
| Dữ liệu nhạy cảm | Nguồn nhập chứa token hoặc query nhạy cảm | Không để secret trở thành dữ liệu inventory thông thường |

Nghiệm thu cần kiểm tra cả dữ liệu đầu ra và workflow. Một hệ thống tìm ra route lạ nhưng không có ai tiếp nhận phát hiện vẫn chưa đáp ứng yêu cầu quản lý sai lệch.

Các thao tác discovery hoặc kiểm chứng chủ động chỉ được thực hiện trong phạm vi đã cho phép, với phương thức phù hợp để không tạo tác dụng phụ nghiệp vụ. Bằng chứng một đường bị chặn cần mô tả vị trí và điều kiện quan sát; không suy từ một lần kết nối thất bại rằng API chắc chắn không còn ở mọi nơi.

## 15. Bảo vệ chính danh mục API

Inventory tập trung nhiều thông tin hữu ích: host nội bộ, phiên bản, dữ liệu, đường quản trị và khoảng trống kiểm soát. Cần phân quyền đọc và sửa theo mục đích, ghi lịch sử thay đổi và bảo vệ nguồn thu thập.

Một thay đổi từ `authentication required` sang `anonymous allowed` trong registry không được tự trở thành phê duyệt hợp lệ chỉ vì người gọi có quyền cập nhật một trường mô tả. Thiết kế cần phân biệt quyền sửa metadata với quyền chấp nhận rủi ro hoặc mở exposure.

Nguồn nhập cũng cần validation và kiểm soát dung lượng. Dữ liệu route hoặc mô tả có thể đến từ hệ thống khác; không để nội dung đó thành markup thực thi trên giao diện inventory. Việc bảo vệ đầu ra và giới hạn tài nguyên vẫn áp dụng cho chính công cụ quản lý bảo mật.

Nếu inventory không sẵn sàng, cần giữ khả năng vận hành theo chính sách đã thiết kế. Không tự tắt kiểm soát API vì không đọc được trang danh mục. Nếu pipeline deploy phụ thuộc registry, hành vi fail, ngoại lệ khẩn cấp và phục hồi phải được công bố rõ, tránh để nhóm vận hành phải ứng biến trong sự cố.

## 16. Từ danh mục đến yêu cầu bảo mật có thể truy vết

Một chuỗi sử dụng inventory hiệu quả:

```text
API / operation / exposure đã nhận diện
    -> owner và dữ liệu được xác định
    -> rủi ro theo chức năng, consumer và ranh giới mạng
    -> yêu cầu danh tính, quyền, dữ liệu, tài nguyên và audit
    -> thiết kế thực thi tại đúng thành phần
    -> bằng chứng gắn với release và đường gọi
    -> đối chiếu drift và quản lý vòng đời
```

Danh mục tốt không cần tuyên bố rằng đã biết tuyệt đối mọi API. Nó cần thể hiện trung thực phạm vi được quan sát, thông tin còn thiếu, người chịu trách nhiệm và cách xử lý thay đổi. Khi inventory nối được bề mặt triển khai với yêu cầu và bằng chứng, nhóm mới có cơ sở để biết kiểm soát nào còn thiếu, bản vá phải bao phủ đường nào và API nào thực sự đã được ngừng.
