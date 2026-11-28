# HTTP method policy

## 1. Chính sách method phải gắn với tài nguyên và hành động

HTTP method thể hiện loại hành động mà client yêu cầu đối với một tài nguyên. Một hệ thống không nên chấp nhận mọi method chỉ vì request đã có token hợp lệ, cũng không nên cấm một method trên toàn nền tảng mà chưa xét chức năng thực sự cần nó.

**HTTP method policy** là chính sách xác định những method nào được hỗ trợ cho từng tài nguyên hoặc thao tác, ai được sử dụng và điều kiện nghiệp vụ nào phải thỏa. Chính sách còn cần kiểm soát cách method được hiểu qua proxy, filter và router để tránh hai tầng áp dụng hai quyết định khác nhau.

Yêu cầu chưa đủ rõ:

> Chỉ cho phép GET và POST để API an toàn.

Câu này không chứng minh GET không làm thay đổi dữ liệu, POST đã kiểm tra quyền hoặc một API hợp lệ dùng PATCH đã được hỗ trợ. Một cách diễn đạt cụ thể hơn:

> Mỗi route của API báo cáo phải có tập method được phê duyệt. Request chỉ được gọi handler khi method có hiệu lực khớp route và chủ thể có quyền thực hiện hành động tương ứng. Các method ngoài hợp đồng không được chuyển thành thao tác khác hoặc tạo tác dụng phụ nghiệp vụ.

Chính sách allowlist và kiểm tra quyền theo method, tài nguyên, hành động được thảo luận trong [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#restrict-http-methods). Trong thiết kế yêu cầu bảo mật, cần chuyển nguyên tắc đó thành một ma trận có thể triển khai và nghiệm thu.

## 2. Phân biệt ba câu hỏi thường bị gộp làm một

Một request cần đi qua những quyết định khác nhau:

| Câu hỏi | Ví dụ | Kết quả cần thiết |
| --- | --- | --- |
| Server có nhận diện và triển khai method này không? | Một token method không được hỗ trợ | Xử lý theo khả năng giao thức, không rơi vào handler mặc định |
| Tài nguyên này có hỗ trợ method đó không? | PUT tới tài nguyên chỉ có GET và PATCH | Từ chối theo hợp đồng method của tài nguyên |
| Người gọi có quyền thực hiện hành động không? | Viewer gửi PATCH tới route có hỗ trợ PATCH | Từ chối theo chính sách phân quyền |

Một method được hỗ trợ không đồng nghĩa mọi người đều có quyền dùng. Ngược lại, việc một người có quyền sửa dữ liệu không làm PUT trở thành method được hỗ trợ nếu API chỉ công bố PATCH cho thao tác đó.

Ví dụ, route `/v1/reports/{reportId}` có thể hỗ trợ GET, HEAD, PATCH và DELETE. Một viewer chỉ có quyền đọc; một editor có thể sửa báo cáo nháp trong dự án được phân công; quyền xóa có thể thuộc nhóm khác. Tập method của tài nguyên và tập hành động của chủ thể là hai dữ liệu khác nhau.

Phân biệt này giúp thiết kế mã lỗi, audit và kiểm thử đúng nguyên nhân. Không dùng `405 Method Not Allowed` làm mã chung cho mọi trường hợp người dùng không có quyền.

## 3. Safe và idempotent không đồng nghĩa “không cần bảo vệ”

### 3.1. Hai thuộc tính có ý nghĩa khác nhau

**Safe** mô tả semantics cơ bản chỉ đọc: client không yêu cầu một thay đổi trạng thái nghiệp vụ. **Idempotent** mô tả hiệu ứng mong muốn của nhiều request giống nhau tương đương một request.

| Method thường gặp | Safe theo semantics đăng ký | Idempotent theo semantics đăng ký |
| --- | --- | --- |
| GET | Có | Có |
| HEAD | Có | Có |
| OPTIONS | Có | Có |
| POST | Không | Không |
| PUT | Không | Có |
| DELETE | Không | Có |
| PATCH | Không | Không |
| TRACE | Có | Có |
| CONNECT | Không | Không |

Các thuộc tính đăng ký có thể tra cứu tại [IANA HTTP Method Registry](https://www.iana.org/assignments/http-methods). “Safe” không có nghĩa không có rủi ro: một GET vẫn có thể làm lộ dữ liệu hoặc tiêu thụ nhiều tài nguyên. TRACE có semantics safe cũng không có nghĩa ứng dụng cần mở nó.

Các tác dụng phụ vận hành như ghi access log không tự biến GET thành một hành động cập nhật nghiệp vụ. Điều cần ngăn là dùng một method chỉ đọc để thực hiện việc người dùng đang yêu cầu thay đổi trạng thái, chẳng hạn phê duyệt, xóa hoặc chuyển tiền.

### 3.2. Không giấu thao tác ghi trong GET

Thiết kế cần tránh:

```http
GET /v1/reports/report-A?action=approve
GET /v1/reports/report-A/delete
```

Một crawler, công cụ preview hoặc cơ chế prefetch có thể truy cập liên kết. Nếu GET làm thay đổi trạng thái, hệ thống đã đặt hành động nguy hiểm vào một đường vốn có thể được tự động đọc.

Yêu cầu nên nói:

> GET và HEAD không được yêu cầu hoặc thực hiện chuyển trạng thái nghiệp vụ của báo cáo. Tham số query hoặc tên route không được biến chúng thành đường phê duyệt hoặc xóa.

Đây là một bất biến phải kiểm tra tại nghiệp vụ, không chỉ bằng tên annotation. Một hàm được gắn `@GetMapping` vẫn có thể chứa logic cập nhật sai.

### 3.3. Idempotent không yêu cầu response giống nhau hoàn toàn

DELETE lần đầu có thể xóa một tài nguyên; lần tiếp theo có thể trả kết quả cho biết tài nguyên không còn. Điều quan trọng là hiệu ứng mong muốn của việc lặp lại không tiếp tục xóa thêm các đối tượng khác. Không bắt mọi lần phải có cùng status, body hoặc timestamp để chứng minh idempotency.

Ngược lại, không suy rằng một implementation bất kỳ đã đáp ứng semantics chỉ vì method có tên DELETE hoặc PUT. Nếu DELETE lặp lại tạo thêm một khoản phí ngoài hợp đồng, cần xem lại nghiệp vụ và cơ chế chống hiệu ứng trùng.

Một thao tác POST có thể được thiết kế chống trùng bằng khóa idempotency. Đó là hợp đồng ứng dụng cần đặc tả về phạm vi khóa, nội dung, thời hạn và cạnh tranh; không phải bảo đảm tự có của POST.

## 4. Lập ma trận method theo nghiệp vụ

### 4.1. Tình huống minh họa

Giả sử nền tảng có báo cáo theo tenant và dự án. Người dùng có quyền đọc, tạo, sửa nháp, xóa nháp hoặc phê duyệt theo phạm vi được cấp. Ma trận sau là lựa chọn thiết kế của ví dụ, không phải chuẩn bắt buộc cho mọi API.

| Route | Method hỗ trợ | Hành động | Điều kiện nghiệp vụ chính |
| --- | --- | --- | --- |
| `/v1/reports` | GET, HEAD | Đọc danh sách và metadata phù hợp | Chỉ dữ liệu trong phạm vi tenant/dự án được phép |
| `/v1/reports` | POST | Tạo báo cáo nháp | Có quyền tạo; tenant và owner được server xác lập |
| `/v1/reports/{reportId}` | GET, HEAD | Đọc báo cáo hoặc metadata | Có quyền đọc đúng đối tượng |
| `/v1/reports/{reportId}` | PATCH | Sửa tập trường cho phép | Có quyền sửa; báo cáo còn nháp |
| `/v1/reports/{reportId}` | DELETE | Xóa báo cáo nháp | Có quyền xóa; đúng tenant và trạng thái |
| `/v1/reports/{reportId}/approvals` | POST | Gửi quyết định phê duyệt | Có quyền approver; không tự duyệt nếu nghiệp vụ cấm |
| Các route cần preflight | OPTIONS theo profile CORS | Mô tả khả năng giao tiếp | Không thực hiện nghiệp vụ hoặc cấp quyền đối tượng |

PUT không có trong ma trận vì chức năng ví dụ không hỗ trợ thay thế toàn bộ biểu diễn báo cáo. Không cần mở PUT chỉ vì framework nhận diện nó. Nếu sau này có yêu cầu hợp lệ, việc thêm PUT phải cập nhật contract, quyền, validation và các ca nghiệm thu.

Các path có `{reportId}` không làm quyền tự phát sinh. Định danh khó đoán cũng không thay kiểm tra tenant và quan hệ dự án. Method policy chỉ xác định một phần của quyết định cho phép.

### 4.2. Tách hành động nhạy cảm khỏi cập nhật trường thông thường

Nếu PATCH cho sửa `title` và `description`, không để client gửi thêm:

```json
{
  "title": "Báo cáo đã sửa",
  "approvalStatus": "APPROVED"
}
```

rồi cập nhật trạng thái mà không đi qua chính sách phê duyệt. Tên method không chặn mass assignment hoặc vượt quy trình nghiệp vụ.

Yêu cầu cần liên kết method với tập trường và chuyển trạng thái được phép. Trong ví dụ, PATCH chỉ sửa phần nháp; POST tới `/approvals` mới đi qua quyền và điều kiện phê duyệt. Server vẫn phải thực thi chính sách tương ứng tại lớp nghiệp vụ.

### 4.3. Không dùng một allowlist toàn cục thay ma trận route

Gateway có thể cho phép một tập method cần thiết cho toàn dịch vụ, nhưng backend còn phải giới hạn theo từng tài nguyên. Việc gateway cho phép DELETE để phục vụ một route không có nghĩa DELETE được chấp nhận tại mọi URL.

Tương tự, chặn toàn bộ DELETE ở biên có thể làm hỏng một tính năng đã được phê duyệt mà không tăng bảo mật nếu còn một POST xóa tương đương chưa được kiểm soát. Cần đánh giá hành động thực tế, không chỉ số lượng method được mở.

## 5. Chuyển ma trận thành các yêu cầu cụ thể

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| METHOD-01 | Mỗi route phải có tập method được phê duyệt và owner | Đối chiếu contract, mapping và inventory |
| METHOD-02 | Request ngoài tập method không được gọi handler nghiệp vụ tương ứng | Gửi method khác và kiểm tra trạng thái, job, thông báo |
| METHOD-03 | GET/HEAD không thực hiện chuyển trạng thái nghiệp vụ | Ca đọc, preview, query chọn hành động và đối chiếu dữ liệu |
| METHOD-04 | Quyền được kiểm tra theo method có hiệu lực và hành động thực tế | Viewer gọi method ghi; thử khác biệt giữa các tầng |
| METHOD-05 | HEAD phải bảo vệ metadata theo quyền đọc của tài nguyên | Chủ thể không có quyền không suy ra metadata nhạy cảm |
| METHOD-06 | OPTIONS/CORS không mở quyền cho request nghiệp vụ tiếp theo | Preflight hợp lệ rồi request thực tế thiếu quyền |
| METHOD-07 | Method override chỉ được xử lý theo chính sách đã công bố | Header, form field và thứ tự filter |
| METHOD-08 | Gateway, server và router không diễn giải method thành các hành động không nhất quán | Kiểm tra qua đường public và đường nội bộ được phép |
| METHOD-09 | Từ chối phải dùng phản hồi, metadata và audit phù hợp nguyên nhân | Kiểm tra 405, Allow, lỗi quyền và telemetry |
| METHOD-10 | Thay đổi method hỗ trợ phải qua đánh giá yêu cầu và cập nhật kiểm chứng | Thêm một thao tác trong môi trường kiểm thử có kiểm soát |

Một yêu cầu có thể được ghi gọn:

> Với `/v1/reports/{reportId}`, chỉ GET, HEAD, PATCH, DELETE và OPTIONS theo profile đã phê duyệt được hỗ trợ. Method còn lại không được chuyển tới handler đọc hoặc ghi như một fallback. Việc cho phép một method không thay thế xác thực, quyền đối tượng, quyền trường dữ liệu và kiểm tra trạng thái nghiệp vụ.

Phần OPTIONS cần tham chiếu chính sách CORS và discovery cụ thể. Không biến một ghi chú “cho phép OPTIONS” thành việc mọi request OPTIONS được quyền gọi handler nghiệp vụ.

## 6. `HEAD` phải giữ kiểm soát của đường đọc

HEAD yêu cầu metadata tương ứng với GET nhưng không truyền response content. Một framework có thể hỗ trợ HEAD thông qua mapping GET; nhóm thiết kế cần biết hành vi đó khi lập ma trận và kiểm thử.

Nếu security rule chỉ khớp GET, còn HEAD rơi vào một nhánh dễ dãi hơn, metadata có thể bị lộ. Header có thể chứa kích thước, ETag, thời điểm sửa hoặc thông tin khác cho phép suy ra sự tồn tại và trạng thái tài nguyên.

Yêu cầu minh họa:

> HEAD trên báo cáo phải áp dụng điều kiện danh tính và quyền đọc đối tượng phù hợp với GET. Response không được có body; metadata trả cho chủ thể không có quyền không được tiết lộ thông tin ngoài chính sách công bố tồn tại.

Không cần bắt mọi header phải giống GET từng byte trong mọi tình huống, vì việc tạo metadata có thể có chi phí và semantics cho phép khác biệt nhất định. Điều cần kiểm chứng là hợp đồng của sản phẩm và quyền dữ liệu, không phải so sánh chuỗi phản hồi một cách máy móc.

Một điểm khác là hiệu quả tài nguyên. Nếu HEAD vẫn làm toàn bộ truy vấn nặng hoặc dựng một báo cáo lớn rồi chỉ bỏ body, nó có thể đúng về nội dung phản hồi nhưng vẫn không đáp ứng ngân sách vận hành. Cần liên kết với giới hạn truy vấn và tài nguyên nếu đây là rủi ro đáng kể.

## 7. `OPTIONS`, `Allow` và CORS là ba việc liên quan nhưng khác nhau

### 7.1. `Allow` không cấp quyền nghiệp vụ

Ví dụ phản hồi cho PUT trên một tài nguyên đã biết nhưng không hỗ trợ PUT:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, PATCH, DELETE, OPTIONS
Content-Type: application/json

{"code":"METHOD_NOT_ALLOWED"}
```

Tập `Allow` minh họa khả năng của tài nguyên theo trạng thái và hợp đồng đang áp dụng; nó không nói người gọi hiện tại có quyền xóa. Không lấy header này làm danh sách quyền để client tự thực thi thay server.

Việc dùng 405 khi method được nhận diện nhưng không được phép cho tài nguyên, cùng yêu cầu phát `Allow` trong response 405 của origin, được quy định trong [RFC 9110, mục 15.5.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.6).

Nếu đường dẫn không được nhận diện hoặc hệ thống có chính sách không công bố sự tồn tại, cần xác định thứ tự xử lý và phản hồi phù hợp. Không ép mọi request sai method đều trả cùng một mã mà bỏ qua semantics, quyền và chính sách công bố.

### 7.2. Preflight không phải request thực hiện hành động

Trình duyệt có thể gửi:

```http
OPTIONS /v1/reports/report-A
Origin: https://portal.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Đây là hỏi chính sách CORS cho request dự kiến. Nó không được sửa báo cáo hoặc trở thành bằng chứng rằng chủ thể được phép PATCH report-A.

Preflight không mang credential người dùng theo cách một request nghiệp vụ có credential được thực hiện; thiết kế không nên bắt preflight chứng minh quyền đối tượng bằng token mà trình duyệt chưa gửi ở bước đó. Request thực tế vẫn phải được xác thực và phân quyền. Cơ chế liên quan được mô tả trong [WHATWG Fetch, CORS protocol and credentials](https://fetch.spec.whatwg.org/#cors-protocol-and-credentials).

Một profile có thể cho preflight đúng origin, method và header đi qua lớp xử lý CORS trước yêu cầu xác thực ứng dụng. Điều này không đồng nghĩa mở anonymous cho mọi hành động trên route.

### 7.3. `Access-Control-Allow-Methods` không thay method policy server

Response preflight có thể khai báo:

```http
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Methods: GET, HEAD, PATCH, DELETE
```

Các giá trị này tham gia quyết định của trình duyệt. Một client ngoài trình duyệt vẫn có thể gửi method bất kỳ; backend phải từ chối theo ma trận và quyền hiện tại.

CORS còn có cửa sổ cache preflight. Vì vậy, thay đổi quyền hoặc method không được chỉ dựa vào việc browser sẽ hỏi lại ngay. Request nghiệp vụ luôn phải gặp chính sách có hiệu lực ở server, kể cả khi bước preflight đã được cache.

## 8. Method override phải có chính sách rõ ràng

### 8.1. Method trên đường truyền và method có hiệu lực có thể khác

Một số ứng dụng hỗ trợ mô phỏng method cho HTML form hoặc client cũ:

```http
POST /v1/reports/report-A
X-HTTP-Method-Override: DELETE
```

hoặc form có trường `_method=DELETE`. Nếu gateway kiểm tra POST nhưng một filter phía sau chuyển thành DELETE, quyết định bảo mật có thể không còn khớp hành động được thực hiện.

Khả năng thử method override được nêu trong [OWASP Web Security Testing Guide: Test HTTP Methods](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/06-Test_HTTP_Methods/). Không phải mọi framework tự hỗ trợ mọi tên header; cần kiểm kê cơ chế thực sự được bật.

### 8.2. Hai lựa chọn thiết kế hợp lệ

**Không hỗ trợ override:** profile API có thể yêu cầu client gửi method thực, đồng thời tắt các cơ chế override không cần thiết. Có thể từ chối đầu vào override hoặc bỏ qua nó theo hợp đồng, nhưng phải chứng minh nó không làm đổi hành động ở một tầng khác.

**Hỗ trợ override có giới hạn:** cần nêu nguồn override được chấp nhận, method gốc nào được phép dùng, tập method đích, route áp dụng và thứ tự xử lý. Danh tính, CSRF, quyền, hạn mức và audit phải dựa trên một cách hiểu thống nhất về hành động có hiệu lực.

Không để hai header override mâu thuẫn được các tầng chọn khác nhau. Cũng không để header nói DELETE nhưng form parameter nói PATCH mà mỗi thành phần tự lấy một giá trị thuận tiện.

Trong Spring Framework, `HiddenHttpMethodFilter` là một ví dụ cụ thể: nó đọc tham số method từ POST và thay giá trị mà request wrapper cung cấp qua `getMethod()`. Xem [Javadoc HiddenHttpMethodFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/HiddenHttpMethodFilter.html). Điều này không chứng minh filter đang được bật trong một dự án bất kỳ.

### 8.3. Audit phải phản ánh hành động đã quyết định

Nếu có override, có thể ghi cả method gốc và method có hiệu lực cùng route đã nhận diện. Nhờ đó, một sự kiện POST dẫn đến DELETE không bị ghi như một thao tác tạo mới bình thường.

Không log toàn bộ body hoặc credential chỉ để truy vết override. Trường telemetry phải có giới hạn và cách chuẩn hóa phù hợp; dữ liệu do client gửi không được làm nhiễu cấu trúc log.

## 9. Phối hợp gateway, router và lớp phân quyền

### 9.1. Một request cần một cách hiểu nhất quán

```text
HTTP server / gateway
  -> kiểm tra cú pháp và chính sách tại biên
  -> áp dụng quy tắc override được phê duyệt, nếu có
  -> xác định method có hiệu lực và route
  -> kiểm tra danh tính, quyền thao tác và quyền đối tượng
  -> validation trường / trạng thái nghiệp vụ
  -> handler và commit
```

Đây là mô hình khái niệm, không bắt mọi stack có cùng thứ tự filter. Điều cần thiết là những kiểm soát quyết định quyền không nhìn một method khác với method cuối cùng được router thực thi.

Method token có phân biệt hoa thường theo HTTP. Không tự chuyển `delete` thành `DELETE` tại một tầng trong khi tầng khác lại coi là một method khác. Với biến thể hoặc cú pháp không được hỗ trợ, cần chính sách xử lý nhất quán, không cho rơi vào một nhánh cho phép mặc định.

Path matching cũng liên quan: gateway và backend cần thống nhất route được bảo vệ. Alias, prefix, đường quản trị và phiên bản cũ phải được nhận diện trong inventory. Một allowlist đúng cho một path không chứng minh các đường khác tới cùng handler đã được bao phủ.

### 9.2. Không dùng method chỉ đọc làm dấu hiệu “được phép công khai”

Rule như “mọi GET đều permitAll” có thể mở dữ liệu báo cáo riêng tư. Rule như “mọi POST chỉ cần đăng nhập” có thể mở chức năng phê duyệt cho viewer. Mỗi rule cần dựa vào cả route và hành động, rồi kiểm tra đối tượng tại nơi có đủ dữ liệu.

Một quyền tổng quát `write` cũng chưa thể hiện toàn bộ nghiệp vụ. Tạo, sửa, xóa, phê duyệt và xuất dữ liệu có rủi ro khác nhau; có thể cần các quyền riêng hoặc điều kiện bổ sung.

### 9.3. Không mở method hạ tầng khi nghiệp vụ không cần

Đối với ứng dụng báo cáo thông thường, profile có thể không cho TRACE, CONNECT hoặc nhóm method WebDAV đi tới handler ứng dụng. Nếu một thành phần thực sự cung cấp proxy tunnel hoặc WebDAV, nó cần phạm vi, owner và kiểm soát riêng.

Không kết luận các method này luôn nguy hiểm trong mọi sản phẩm. Yêu cầu đúng là chỉ mở theo chức năng đã phê duyệt, kiểm soát việc phản chiếu dữ liệu, tunneling hoặc thao tác tài nguyên tương ứng, và kiểm chứng đường thực thi thực tế.

Với TRACE, không dựa vào các kịch bản trình duyệt cũ để tuyên bố mọi môi trường hiện tại đều cho phép lấy cookie qua cùng kỹ thuật. Việc không cần chức năng chẩn đoán và nguy cơ phản chiếu thông tin đã là cơ sở để hạn chế nó trong profile phù hợp.

## 10. Ví dụ Java: mapping cụ thể và quyền theo method

### 10.1. Mapping phải nêu method được hỗ trợ

Ví dụ một controller minh họa:

```java
@RestController
@RequestMapping("/v1/reports")
class ReportController {
    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/{reportId}")
    ReportView read(@PathVariable String reportId) {
        return reports.readAllowedReport(reportId);
    }

    @PatchMapping("/{reportId}")
    ReportView edit(@PathVariable String reportId,
                    @RequestBody EditReportRequest request) {
        return reports.editAllowedDraft(reportId, request);
    }

    @DeleteMapping("/{reportId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(@PathVariable String reportId) {
        reports.deleteAllowedDraft(reportId);
    }
}
```

Các type và service trên minh họa trách nhiệm, không phải một ứng dụng hoàn chỉnh. `ReportService` phải kiểm tra danh tính, tenant, quyền đối tượng và trạng thái; đặt tên `Allowed` không tự thực hiện những kiểm tra đó.

Trong Spring MVC, mapping theo method cụ thể giúp thu hẹp đường vào. `@RequestMapping` không giới hạn method theo mặc định có thể khớp nhiều method hơn dự kiến. Framework cũng có hành vi hỗ trợ HEAD/OPTIONS cần được tính tới. Xem [Spring Framework: Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).

### 10.2. Rule HTTP kết hợp method và path

Một trích đoạn Spring Security cho các route đọc và sửa minh họa:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(HttpMethod.GET, "/v1/reports/*")
            .hasAuthority("report:read")
        .requestMatchers(HttpMethod.HEAD, "/v1/reports/*")
            .hasAuthority("report:read")
        .requestMatchers(HttpMethod.PATCH, "/v1/reports/*")
            .hasAuthority("report:edit")
        .requestMatchers(HttpMethod.DELETE, "/v1/reports/*")
            .hasAuthority("report:delete")
        .anyRequest().denyAll());
```

Đây chỉ là trích đoạn minh họa một tập route, không phải cấu hình cho toàn nền tảng. Nó chưa khai báo đăng nhập, CORS, CSRF, route collection, approval, xử lý lỗi hoặc toàn bộ chain. Các chức năng đó phải được bổ sung theo profile riêng, không mở bằng một `permitAll` rộng để ví dụ chạy được.

Khả năng match theo HTTP method và default deny được mô tả trong [Spring Security: Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html#match-by-http-method). Cần đối chiếu phiên bản và path matcher của dự án thật.

Rule trên không tự xác minh `reportId` thuộc tenant hoặc dự án nào. Nó cũng có thể từ chối trước khi MVC trả 405; vì vậy không dùng kết quả của một security matcher thay cho toàn bộ hợp đồng lỗi method. Thiết kế phải xác định tầng quyết định và semantics response cuối cùng.

### 10.3. Không suy ra CSRF chỉ từ chữ POST

Với xác thực bằng cookie do trình duyệt tự gửi, các thao tác thay đổi trạng thái cần chính sách CSRF phù hợp. Đổi một GET ghi dữ liệu thành POST là cần thiết cho semantics nhưng không tự hoàn thành bảo vệ CSRF.

Ngược lại, không vô hiệu hóa CSRF toàn cục chỉ vì API dùng PATCH hoặc DELETE. Cần dựa vào cơ chế mang credential và loại client. Nếu hỗ trợ method override cho form, thứ tự xử lý và cách kiểm chứng CSRF phải được đánh giá trong cùng đường thực thi.

## 11. PUT, PATCH và kiểm soát trạng thái cập nhật

### 11.1. PUT không phải nhãn chung cho mọi sửa dữ liệu

Nếu hỗ trợ PUT, hợp đồng phải xác định biểu diễn thay thế, trường do server quản lý và hành vi khi trường bị bỏ đi. Không để một thao tác thay thế vô tình đặt lại owner, tenant hoặc trạng thái phê duyệt.

Quyền sửa vẫn phải áp dụng cho toàn bộ thay đổi mà request gây ra. Một người được đổi tiêu đề không mặc nhiên được thay thế mọi trường của đối tượng bằng PUT.

### 11.2. PATCH cần định dạng và tính nguyên tử rõ ràng

PATCH mang chỉ dẫn thay đổi theo định dạng đã chọn. Nó không tự có tính idempotent trong mọi trường hợp; một patch “đặt title thành X” khác một patch “tăng counter thêm 1”. Cần công bố media type, trường hoặc đường dẫn được phép sửa và điều kiện cạnh tranh.

Theo [RFC 5789, PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html#section-2), các thay đổi của patch phải được áp dụng nguyên tử; không để một phần thành công và một phần bị bỏ lại khi patch thất bại.

Nếu cần chống ghi đè do cạnh tranh, có thể dùng version hoặc điều kiện như `If-Match` theo thiết kế. Từ chối khi điều kiện không còn đúng phải xảy ra trước commit, không phải sau khi một số trường đã được thay đổi.

### 11.3. Method policy không kiểm soát toàn bộ tác dụng phụ

Một PATCH hợp lệ có thể tạo sự kiện, cập nhật chỉ mục hoặc gửi thông báo. Các hiệu ứng đó cần đồng bộ với kết quả commit theo hợp đồng. Khi request bị từ chối vì method, quyền hoặc trạng thái, không được còn thông báo “đã phê duyệt” trong queue.

Tương tự, retry một DELETE không nên tạo nhiều thông báo nghiệp vụ nếu hợp đồng chỉ cho một sự kiện khi thực sự chuyển trạng thái. Access log cho từng request vẫn có thể tồn tại riêng; không gộp audit request với hiệu ứng nghiệp vụ để đo idempotency sai.

## 12. Phản hồi từ chối và khả năng truy vết

### 12.1. Phân loại nguyên nhân thay vì một mã chung

| Nguyên nhân | Cách xử lý theo thiết kế |
| --- | --- |
| Method không được nhận diện hoặc không triển khai | Phản hồi theo khả năng HTTP của server, thường là 501 trong trường hợp phù hợp |
| Method được triển khai nhưng tài nguyên không hỗ trợ | 405 và metadata `Allow` phù hợp khi origin phát 405 |
| Thiếu hoặc sai danh tính | Lỗi xác thực theo profile |
| Có danh tính nhưng thiếu quyền hành động | Lỗi phân quyền hoặc chính sách che giấu tài nguyên |
| Trạng thái tài nguyên không cho thao tác | Lỗi xung đột hoặc điều kiện theo hợp đồng |
| Method token hoặc framing sai cú pháp | Lớp HTTP xử lý lỗi giao thức, không đưa tới nghiệp vụ |

Chính sách tại biên có thể từ chối trước router. Hợp đồng cần giải thích hành vi quan sát được ở đường đó, thay vì giả định mọi tầng đều trả giống nhau. Dù mã lỗi nào được chọn trong trường hợp hợp lệ, bất biến quan trọng là không thực hiện tác vụ không được phép và không tiết lộ thông tin ngoài chính sách.

Không để response 405 chứa một danh sách method sao chép cho mọi URL. Danh sách cần phản ánh tài nguyên được nhận diện và chính sách đang áp dụng. Cũng không dùng `Allow` làm bằng chứng duy nhất về method thực tế, vì cấu hình hoặc handler có thể lệch metadata.

### 12.2. Audit đủ ngữ cảnh, không chứa secret

Một sự kiện minh họa:

```json
{
  "eventType": "HTTP_METHOD_POLICY_DENIED",
  "routeTemplate": "/v1/reports/{reportId}",
  "originalMethod": "POST",
  "effectiveMethod": "POST",
  "requestedOverrideMethod": "DELETE",
  "overrideSource": "unsupported_header",
  "decision": "DENY",
  "reasonCode": "METHOD_OVERRIDE_NOT_ALLOWED",
  "requestId": "req-method-example-001"
}
```

Đây là ví dụ dữ liệu, không phải cấu trúc bắt buộc của mọi logger. Trong ví dụ, server phát hiện chỉ thị override nhưng không áp dụng nó: method vẫn là POST, còn DELETE chỉ là giá trị client đề nghị. Request bị từ chối trước handler. Nếu override thực sự được áp dụng theo một profile khác, `effectiveMethod` phải phản ánh giá trị đã xác lập.

Tách `requestedOverrideMethod` khỏi `effectiveMethod` giúp telemetry không mô tả một hành động chưa xảy ra như đã được router thực thi. Không tự ghi DELETE là method có hiệu lực chỉ vì chuỗi đó xuất hiện trong header của client.

Các trường lấy từ client cần được giới hạn, chuẩn hóa và ghi bằng API log có cấu trúc. Không log authorization header hoặc toàn bộ body để biết method nào bị từ chối. Tỷ lệ tăng lỗi method có thể báo hiệu client sai phiên bản hoặc dò bề mặt; cần đối chiếu route, release và nguồn trước khi kết luận.

## 13. Kế hoạch nghiệm thu theo ma trận

Các ca dưới đây là kế hoạch kiểm chứng cho nền tảng minh họa, không phải báo cáo đã chạy trên một ứng dụng cụ thể.

| Ca | Request hoặc điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Đọc đúng quyền | GET báo cáo trong phạm vi | Trả tập dữ liệu được phép, không chuyển trạng thái |
| HEAD đúng quyền | HEAD cùng tài nguyên | Không có body; metadata theo hợp đồng |
| HEAD ngoài quyền | Chủ thể không đọc được báo cáo | Không lộ metadata ngoài chính sách |
| Ghi qua GET | Query hoặc alias yêu cầu approve/delete | Không thực hiện hành động ghi |
| Method ngoài contract | PUT tới tài nguyên chỉ hỗ trợ PATCH | Không gọi handler sửa như fallback; lỗi theo policy |
| Sai quyền chức năng | Viewer gửi PATCH hoặc DELETE | Không cập nhật hoặc xóa dù method được tài nguyên hỗ trợ |
| Sai tenant | Editor đổi `reportId` sang tenant khác | Không thao tác tài nguyên ngoài phạm vi |
| Trạng thái sai | DELETE báo cáo đã phê duyệt | Từ chối theo quy tắc nghiệp vụ |
| Trường cấm | PATCH kèm `approvalStatus` | Không đi vòng qua quyền phê duyệt |
| Preflight hợp lệ | OPTIONS đúng origin, method và header | Chỉ xử lý CORS; không có hiệu ứng nghiệp vụ |
| Preflight rồi thiếu quyền | PATCH thực tế không có quyền | Vẫn bị từ chối ở request nghiệp vụ |
| Override không được hỗ trợ | POST cùng header hoặc `_method` | Không tạo hành động bị policy cấm |
| Override được hỗ trợ | Form hợp lệ theo profile riêng | Quyền, CSRF và router nhìn hành động thống nhất |
| Metadata override mâu thuẫn | Hai nguồn yêu cầu method khác nhau | Xử lý theo chính sách rõ ràng, không chọn khác nhau giữa các tầng |
| Biến thể method | Token khác hoa thường hoặc không được hỗ trợ | Không rơi vào nhánh cho phép mặc định |
| Route thay thế | Alias, route cũ hoặc đường nội bộ được phép | Cùng bất biến bảo mật cho cùng hành động |
| Retry và cạnh tranh | Lặp DELETE hoặc gửi patch đồng thời | Hiệu ứng theo semantics và hợp đồng chống trùng |
| Method hạ tầng | TRACE/CONNECT ở ứng dụng không có nhu cầu | Không mở chức năng phản chiếu hoặc tunnel ngoài profile |

### 13.1. Kiểm tra tác dụng phụ, không chỉ status

Một response từ chối có thể xuất hiện sau khi handler đã cập nhật dữ liệu rồi phát hiện lỗi. Vì vậy, ca âm cần kiểm tra trạng thái lưu trữ, queue, thông báo hoặc tích hợp ngoài có liên quan.

Với request GET/HEAD, nên xác minh các trường trạng thái nghiệp vụ không thay đổi. Không coi access log hoặc telemetry hợp lệ là vi phạm semantics chỉ đọc; cần phân loại đúng tác dụng phụ đang quan sát.

Ca dương phải có trong ma trận. Một cấu hình chặn mọi request có thể vượt nhiều ca âm nhưng không đáp ứng chức năng. Cần chứng minh các method được phê duyệt hoạt động đúng cho chủ thể được phép.

### 13.2. OPTIONS chỉ là một nguồn thông tin

Có thể đọc phản hồi OPTIONS để biết khả năng được công bố, nhưng phải đối chiếu bằng request thực trong môi trường kiểm thử được phép. Không thử một DELETE có tác dụng phá hủy trên dữ liệu thật chỉ để liệt kê method.

Nên dùng fixture hoặc tài nguyên dùng riêng cho kiểm chứng, có kiểm soát và khả năng phục hồi phù hợp. Các thử nghiệm method ghi, override và cạnh tranh phải nằm trong phạm vi được cho phép và không mở rộng sang hệ thống khác.

### 13.3. Kiểm tra qua các tầng và giao thức được hỗ trợ

Một ca chạy trực tiếp controller không chứng minh gateway, method override filter hoặc proxy không tạo cách diễn giải khác. Cần có bằng chứng tích hợp qua đường client thực tế và các đường nội bộ được kiến trúc cho phép.

Với nhiều phiên bản API hoặc nhiều security chain, mỗi phạm vi có thể có mapping và rule riêng. Tập kiểm tra cần liên kết với inventory và release để phát hiện thay đổi khi thêm method hoặc thay path matcher.

## 14. Quản lý thay đổi method như thay đổi bề mặt tấn công

Thêm PATCH vào một route không chỉ là thay annotation. Nó có thể tạo tập trường ghi mới, nhu cầu kiểm tra quyền mới, yêu cầu CSRF, CORS và giới hạn parser khác. Tương tự, thêm DELETE hoặc một POST hành động nhạy cảm cần đánh giá các hiệu ứng nghiệp vụ và cơ chế retry.

Một thay đổi nên cập nhật:

- Contract và inventory về method theo route/version.
- Ma trận quyền chức năng, đối tượng và trường dữ liệu.
- Chính sách override, CORS và bảo vệ client theo cơ chế credential.
- Kiểm soát trạng thái, cạnh tranh và tác dụng phụ.
- Gateway, router, security matcher và metadata phản hồi.
- Ca dương, ca âm và bằng chứng theo release.

Nếu phải giữ một method hoặc route cũ trong giai đoạn chuyển đổi, cần có owner, hạn hỗ trợ và kiểm soát tương ứng. Không mặc định phiên bản deprecated được phép giữ method rộng hơn hoặc quy tắc quyền yếu hơn.

Khi loại bỏ một method, cần kiểm chứng cả route trực tiếp, alias và cơ chế override liên quan. Xóa một mục khỏi tài liệu không tự vô hiệu hóa mapping runtime.

## 15. Một hồ sơ yêu cầu gọn để triển khai

```text
ID: HTTP-METHOD-REPORT-001
Phạm vi: các exposure được phê duyệt của Reporting API v1.

Chính sách:
  - Method hỗ trợ được xác định theo route và hành động nghiệp vụ.
  - Mặc định không cho hành động ngoài ma trận đã phê duyệt.
  - GET/HEAD không thực hiện chuyển trạng thái nghiệp vụ.
  - Quyền đọc, sửa, xóa và phê duyệt được kiểm tra riêng theo đối tượng.
  - OPTIONS phục vụ capability/CORS theo profile, không cấp quyền ghi.
  - Method override chỉ hoạt động nếu có contract và thứ tự kiểm soát rõ.

Từ chối:
  - Không gọi handler hoặc tạo hiệu ứng nghiệp vụ ngoài policy.
  - Phản hồi phân biệt lỗi method, danh tính, quyền và trạng thái.
  - Metadata và audit phản ánh route cùng hành động thực tế.

Kiểm chứng:
  - Ma trận method x route x chủ thể x trạng thái.
  - HEAD, OPTIONS, override, route thay thế và đường qua gateway.
  - Kiểm tra dữ liệu và tác dụng phụ bên cạnh status code.
```

Chính sách HTTP method có giá trị khi mọi tầng hiểu thống nhất hành động mà request yêu cầu và server chỉ thực hiện hành động được phê duyệt trong đúng phạm vi quyền. Một danh sách verb đơn thuần chưa đủ; cần nối method với tài nguyên, dữ liệu, trạng thái nghiệp vụ và bằng chứng nghiệm thu của toàn đường xử lý.
