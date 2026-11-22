# Method behavior testing — Kiểm thử hành vi theo HTTP method

## 1. Mục tiêu: chứng minh tác động nghiệp vụ của từng method

Trong chương **HTTP Method Semantics**, kiểm thử hành vi theo HTTP method là việc gửi cùng một đường dẫn với những method, danh tính và điều kiện khác nhau, rồi kiểm tra cả phản hồi lẫn tác động đã xảy ra. Một endpoint mang tên `approve` chưa chứng minh rằng nó chỉ chấp nhận lệnh phê duyệt hợp lệ. Một phản hồi `403` cũng chưa chứng minh rằng dữ liệu chưa bị ghi trước khi lỗi được trả về.

Trong phạm vi Business Logic Security, mục tiêu là bảo vệ quy tắc nghiệp vụ trước việc đổi method để bỏ qua bước phê duyệt, sửa giá, vượt quyền theo đối tượng hoặc gửi lại lệnh. Ta cần trả lời bốn câu hỏi:

- Method nào thực sự đi tới mỗi thao tác, kể cả method do framework hoặc proxy xử lý?
- Mỗi đường đi có kiểm tra đúng người, tenant, đối tượng, trạng thái và phiên bản không?
- Yêu cầu đọc, yêu cầu bị từ chối và yêu cầu gửi lại có gây thêm tác động nghiệp vụ không?
- Hai yêu cầu đồng thời có phá vỡ invariant dù từng yêu cầu riêng lẻ đều trông hợp lệ không?

Sau bài học, người học có thể xây ma trận method–hành vi, viết kiểm thử tích hợp Java và xác định phần nào cần kiểm tra qua máy chủ, proxy hoặc trình duyệt thật.

## 2. Chuyển ngữ nghĩa HTTP thành oracle kiểm thử

**Safe** nói về yêu cầu đọc, không chủ đích thay đổi nghiệp vụ; ghi log phụ trợ vẫn có thể xảy ra. **Idempotent** nói về tác động dự định khi lặp lại, không đòi mọi phản hồi giống nhau. GET và HEAD là safe; PUT và DELETE là idempotent. POST không mặc nhiên có tính chất đó. HEAD không trả body. Khi trả `405`, server phải có `Allow`. Đây là những điểm nền để thiết kế oracle, theo [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).

Trong bài này, **oracle** là tiêu chí đúng được xác định trước khi chạy test. Ví dụ, oracle của `GET /orders/O-101` là “đọc được bản chiếu được cấp quyền, không tạo quyết định phê duyệt”, thay vì “bất cứ thứ gì controller hiện trả về”.

Tách ba lớp quan sát:

| Lớp | Quan sát ví dụ | Điều cần chứng minh |
| --- | --- | --- |
| Giao thức | Status, `Allow`, body, header cache, redirect nếu có | Phản hồi đúng hợp đồng của API |
| Dữ liệu nghiệp vụ | Trạng thái đơn, giá đã chốt, người duyệt, lượng giữ kho | Invariant vẫn đúng sau commit |
| Tác động tiếp theo | Outbox, công việc thanh toán, thông báo phê duyệt | Không sinh hoặc thực thi thêm lệnh trái phép |

Một access log mới sau GET thường không làm hỏng oracle. Một bản ghi `ApprovalGranted` mới sau GET thì có. Vì vậy, so sánh “toàn bộ database không thay đổi” thường quá rộng; chỉ so status lại quá hẹp.

Với PATCH, tính idempotent phụ thuộc phép sửa được thiết kế. Việc áp dụng một patch phải nguyên tử: không để lại phần sửa dở khi toàn bộ patch thất bại. Những tính chất này được mô tả trong [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html).

## 3. Viết hợp đồng method trước khi viết test

Xét một ứng dụng quản lý đơn mua hàng trong Java. Đây là hợp đồng minh họa do ứng dụng lựa chọn, không phải quy tắc rằng mọi hệ thống phải dùng đúng các URL hoặc mã lỗi này.

| Endpoint | Method thuộc hợp đồng | Hành vi nghiệp vụ |
| --- | --- | --- |
| `/orders/{id}` | GET, HEAD | Đọc bản chiếu được cấp quyền; không gửi duyệt, giữ kho hoặc chốt giá |
| `/orders/{id}/draft-content` | PUT | Thay toàn bộ phần nội dung được phép sửa của bản nháp |
| `/orders/{id}/draft-content` | PATCH, nếu tính năng được bật | Sửa một phần bản nháp theo định dạng và danh sách đường dẫn được cho phép |
| `/orders/{id}/submit` | POST | Chuyển DRAFT sang PENDING_APPROVAL sau khi kiểm tra điều kiện gửi |
| `/orders/{id}/approve` | POST | Ghi một quyết định hợp lệ của người duyệt độc lập |
| `/orders/{id}` | DELETE | Xóa bản nháp theo chính sách, giải phóng giữ chỗ liên quan nếu có |
| Các URL trên | OPTIONS theo cấu hình triển khai | Mô tả khả năng hoặc xử lý preflight, không thực hiện lệnh nghiệp vụ |

`draft-content` là tài nguyên con chỉ chứa phần khách hàng được phép thay thế, chẳng hạn danh sách mã hàng, số lượng và ghi chú. `tenantId`, chủ sở hữu, trạng thái phê duyệt và giá được chốt không thuộc biểu diễn mà khách được PUT. Cách giới hạn này giúp định nghĩa rõ ý nghĩa “thay thế” mà không cho phép mass assignment vào toàn bộ entity.

Các invariant của ví dụ:

1. Chỉ chủ đơn trong cùng tenant được sửa hoặc xóa khi đơn còn DRAFT.
2. Chỉ người có quyền duyệt đối tượng cụ thể, khác người tạo, mới được phê duyệt đơn đang chờ.
3. Giá có hiệu lực do server xác định; thay method không biến giá khách gửi thành giá đã chốt.
4. Mỗi quyết định hợp lệ chỉ tạo một chuyển trạng thái và một sự kiện nghiệp vụ tương ứng.
5. Giải phóng một lần giữ kho không làm lượng khả dụng tăng hai lần khi DELETE bị gửi lại.
6. Một yêu cầu bị từ chối không được để lại thay đổi nghiệp vụ hoặc công việc sẽ thực thi thay đổi đó.

Đơn đã được duyệt không tự nhiên trở thành đối tượng được xóa chỉ vì người gọi dùng DELETE. Nếu nghiệp vụ cho phép hủy đơn đã duyệt, cần mô hình hóa một lệnh hủy với điều kiện, quyền và bút toán bù riêng.

### 3.1. Đừng lấy `Allow` làm bằng chứng phân quyền

`Allow` phục vụ mô tả method của tài nguyên; nó không chứng minh người gọi được duyệt đơn. Hãy kiểm tra cả method được quảng bá lẫn việc gửi yêu cầu thực tế với từng danh tính. Header CORS `Access-Control-Allow-Methods` cũng cần được kiểm tra riêng với `Allow`.

Với ứng dụng này, một người duyệt hợp lệ gọi GET vào `/approve` sẽ nhận `405` kèm `Allow` phù hợp. Người chưa đăng nhập có thể bị lớp xác thực chặn trước đó. Hai test phục vụ hai mục tiêu khác nhau; không ép mọi danh tính đều phải nhận cùng một mã lỗi.

Method không được server nhận biết hoặc triển khai có thể dẫn tới `501`; chính sách ở gateway cũng có thể chặn trước. Không tổng quát hóa rằng mọi chuỗi method lạ đều phải trả `405`. Phân biệt này theo [RFC 9110, phần Method Definitions](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.1).

## 4. Dựng fixture và ma trận bao phủ có chủ đích

Tạo dữ liệu kiểm thử độc lập, chẳng hạn:

- Tenant A có Lan là người tạo đơn, Minh là người duyệt được phân công, Chi chỉ có quyền đọc.
- Tenant B có Đức; Đức có vai trò duyệt trong tenant B nhưng không được truy cập đơn của tenant A.
- Mỗi test nhận một đơn riêng ở DRAFT, PENDING_APPROVAL hoặc APPROVED theo mục tiêu.
- Giá tham chiếu, phiên bản, giữ kho và số quyết định ban đầu được thiết lập rõ ràng.

Không dùng một tài khoản quản trị toàn quyền để thay cho mọi actor. Quyền đó có thể che lỗi thiếu kiểm tra chủ sở hữu hoặc tách biệt nhiệm vụ.

Ma trận tối thiểu cần kết hợp **method × đường dẫn × actor × tenant × trạng thái × điều kiện yêu cầu**. Có thể chọn các tổ hợp rủi ro cao trước:

| Ca | Thay đổi có chủ đích | Kỳ vọng trong ứng dụng ví dụ |
| --- | --- | --- |
| M01 | Minh POST duyệt một đơn đang chờ hợp lệ | Thành công, đúng một quyết định |
| M02 | Minh đổi POST ở M01 thành GET hoặc HEAD trên fixture mới | Không phê duyệt; bị chặn theo hợp đồng method |
| M03 | Chi dùng POST vào `/approve` | Bị từ chối vì không có quyền duyệt |
| M04 | Lan tự duyệt đơn do mình tạo | Bị từ chối vì vi phạm tách biệt nhiệm vụ |
| M05 | Đức dùng ID đơn tenant A qua từng method được hỗ trợ | Không đọc, sửa hoặc suy ra dữ liệu ngoài phạm vi cho phép |
| M06 | Lan PUT nội dung một đơn đã được duyệt | Không sửa được nội dung đã khóa |
| M07 | GET có query `action=approve` | Không tạo quyết định dù query có được chấp nhận hay bị từ chối |
| M08 | POST có tín hiệu override sang DELETE | Chỉ có hành vi override được cấu hình; vẫn đủ kiểm tra quyền và trạng thái |
| M09 | Gửi lại cùng lệnh đã hoàn tất | Không tạo tác động nghiệp vụ thứ hai |
| M10 | Hai lệnh cạnh tranh trên cùng phiên bản | Chỉ những thay đổi phù hợp chính sách đồng thời mới commit |
| M11 | PATCH có phần đầu hợp lệ, phần sau bị cấm | Không còn phần thay đổi đã ghi dở |
| M12 | OPTIONS preflight thành công rồi POST bằng Chi | POST vẫn bị từ chối theo quyền thực tế |

Mỗi nhóm test âm cần một **positive control**: cùng cách đăng nhập, cùng định dạng body và cùng cấu hình, nhưng dùng method, actor và trạng thái hợp lệ trên đối tượng riêng thì thao tác thành công. Nếu cả ca đúng cũng thất bại vì session hỏng, ca âm chưa chứng minh được cơ chế cần kiểm tra.

## 5. Kiểm thử đường đọc: GET, HEAD và OPTIONS

### 5.1. Đo tác động trên trạng thái đã commit

Chụp `BusinessView` trước yêu cầu, gửi yêu cầu, rồi đọc lại bằng transaction mới. Bản chụp nên là dữ liệu bất biến, có thể gồm:

```text
BusinessView
  order: id, tenantId, ownerId, status, approvedBy, committedPrice
  draft: editable fields, version used by business updates
  approvals: immutable list of decision IDs and actors
  reservations: reservation ID, quantity, release state
  businessOutbox: immutable list of event IDs, types and payload fingerprints
  businessJobs: commands pending for this order
```

Không dùng cùng một entity JPA đang được quản lý làm cả `before` và `after`: nó có thể đã đổi trong persistence context, khiến hai biến cùng trỏ vào dữ liệu mới. Không bọc toàn bộ test tích hợp trong một transaction tự rollback rồi xem đó là bằng chứng không có thay đổi đã commit.

Đối với tác vụ bất đồng bộ, quan sát ít nhất cả lệnh được enqueue và tác động khi consumer xử lý. Một GET chưa làm đổi `status` ngay nhưng đã đưa `ApproveOrder` vào queue vẫn là lỗi.

### 5.2. Các biến thể cần chạy

Với mỗi đường đọc quan trọng, chạy trên fixture độc lập hoặc theo chuỗi đã định nghĩa:

1. Đọc lần đầu khi cache chưa có dữ liệu.
2. Đọc lại khi cache đã có dữ liệu.
3. HEAD cùng đường dẫn bằng actor có quyền đọc.
4. HEAD bằng actor khác tenant hoặc không được đọc đối tượng.
5. GET có query gợi ý lệnh như `action=approve`, `submit=true`, `price=1`.
6. GET hoặc HEAD tới đường dẫn vốn chỉ nhận lệnh phê duyệt.
7. OPTIONS tới đường đọc và đường ghi.

Kiểm tra trực tiếp phản hồi HEAD qua máy chủ HTTP: không có body; metadata nhạy cảm không được lộ cho actor bị cấm. Không bắt buộc mọi header phải giống hệt GET, vì một số header phụ thuộc việc tạo nội dung. Điều quan trọng của test bảo mật là HEAD không mở đường truy cập rộng hơn và không làm phát sinh lệnh nghiệp vụ.

Trong Spring MVC, GET có thể được hỗ trợ HEAD tự động; OPTIONS cũng có thể được framework xử lý từ mapping. Vì vậy, thiếu một phương thức Java có tên `head` không có nghĩa là URL không nhận HEAD. Đây là hành vi được mô tả trong [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#ann-requestmapping-head-options).

Giả sử controller đọc gọi `ensureReservation()` rồi mới trả DTO. Cả lần đọc đầu, HEAD hoặc cache miss có thể đi tới đoạn giữ kho đó. Oracle nên bắt việc tạo reservation, thay vì chỉ đếm số lần gọi `repository.save()`; tác động có thể đến từ service khác hoặc hàng đợi.

OPTIONS thành công chỉ chứng minh lớp xử lý khả năng/preflight chấp nhận yêu cầu đó. Sau preflight, hãy gửi lệnh thật bằng actor không được duyệt và kiểm tra rằng quyết định nghiệp vụ vẫn bị từ chối. CORS không thay thế việc kiểm tra quyền đối tượng trong service.

## 6. Đổi method để tìm đường vượt quyền

### 6.1. Giữ mọi yếu tố khác hợp lệ

Để kiểm tra `/approve` có bị gọi bằng PUT hay không, dùng session còn hiệu lực của Minh, đơn đang chờ, phiên bản đúng và body phê duyệt hợp lệ. Thay duy nhất method. Nếu dùng body sai JSON hoặc thiếu CSRF, yêu cầu có thể bị chặn sớm và không chạm tới lỗi mapping cần phát hiện.

Với Spring Security có bật CSRF, test dùng method cần bảo vệ phải cung cấp token hợp lệ khi mục tiêu là mapping hoặc phân quyền. Các ca thiếu/sai CSRF thuộc nhóm riêng. Cách đưa token vào MockMvc được nêu trong [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html).

Lặp lại kiểm tra trên các đường đi thực sự được hỗ trợ:

- PUT/PATCH không được nới quyền sửa so với quy tắc đối tượng đã định nghĩa.
- DELETE không được bỏ qua tenant hoặc trạng thái chỉ vì body rỗng.
- HEAD không được dùng cấu hình bảo mật rộng hơn GET để tiết lộ header của đơn bị cấm.
- POST không được dựa vào việc “đây là method ghi” để suy ra actor có quyền thực hiện mọi lệnh.

Một cấu hình như “cho tất cả GET đi qua, chỉ kiểm tra quyền cho POST” đặc biệt nguy hiểm nếu endpoint lệnh vô tình nhận GET. Cần kiểm thử cả hai lỗi kết hợp: mapping mở quá rộng và quyết định phân quyền dựa trên method không phản ánh tác động thực.

### 6.2. Kiểm tra input có ý nghĩa nghiệp vụ qua từng đường đi

Thử đưa `approvedBy`, `status`, `tenantId` hoặc `unitPrice` vào phần dữ liệu khách gửi cho các operation tương ứng. Trong hợp đồng ví dụ, chúng không được trở thành giá trị có thẩm quyền chỉ nhờ đổi từ PATCH sang PUT hoặc từ POST sang method override.

Không yêu cầu mọi endpoint xử lý field lạ giống nhau. Ứng dụng có thể chọn từ chối hoặc bỏ qua theo hợp đồng. Oracle chung là các field được bảo vệ không đổi và không có tác động phụ được tạo từ chúng. Nếu chính sách là từ chối, test cũng phải kiểm tra đúng mã lỗi và nội dung lỗi theo hợp đồng đó.

## 7. Kiểm thử gửi lại: PUT, DELETE, PATCH và POST

### 7.1. PUT: đo kết quả thay thế, không chỉ phản hồi

Tạo bản nháp có hai dòng hàng. PUT một biểu diễn `draft-content` đầy đủ, sau đó gửi lại cùng yêu cầu. Kiểm tra nội dung cuối đúng biểu diễn được phép và không có hai lần giữ thêm cùng lượng hàng hoặc hai sự kiện “nội dung thay đổi” đại diện cùng một thay đổi.

Nếu API dùng điều kiện phiên bản, yêu cầu lặp có thể bị chặn vì điều kiện đã cũ. Đó không phải thất bại của tính idempotent. Với ca này, hãy xác nhận không có tác động nghiệp vụ thứ hai; không ép cả hai lần đều thành công.

Cần một ca riêng kiểm tra ý nghĩa thay thế: bỏ một dòng khỏi biểu diễn mới phải có kết quả đúng hợp đồng, thay vì âm thầm giữ dòng cũ như một phép merge. Danh sách field được PUT vẫn phải giới hạn ở nội dung bản nháp.

### 7.2. DELETE: không giải phóng hoặc hoàn tác hai lần

Giả sử bản nháp có reservation R-9 giữ ba sản phẩm. Sau DELETE hợp lệ, R-9 đã được giải phóng một lần. Gửi DELETE lần nữa và kiểm tra số lượng khả dụng không tăng thêm ba sản phẩm.

Ứng dụng có thể quy định lần sau trả `204`, `404` hoặc `410` tùy mô hình tài nguyên. Test phải dùng lựa chọn cụ thể của API, đồng thời kiểm tra sổ giữ kho. Việc chỉ nhận hai mã `204` không chứng minh xử lý lặp đúng.

Thêm ca hai DELETE đồng thời trên cùng reservation. Một câu lệnh tăng tồn kho chạy độc lập với việc đánh dấu reservation có thể gây giải phóng kép, dù luồng tuần tự luôn qua test. Lượng cần giải phóng phải lấy từ dữ liệu giữ chỗ có thẩm quyền, không lấy từ query hoặc body mà người gọi tự gửi.

### 7.3. PATCH: xét phép sửa và tính nguyên tử

Với JSON Patch, có thể thử chuỗi thao tác sau trên bản nháp:

```http
PATCH /orders/O-101/draft-content HTTP/1.1
Content-Type: application/json-patch+json

[
  { "op": "replace", "path": "/note", "value": "Giao buổi sáng" },
  { "op": "replace", "path": "/approvedBy", "value": "attacker" }
]
```

Trong mô hình này, `/note` được sửa nhưng `/approvedBy` không thuộc biểu diễn được phép. Toàn bộ yêu cầu phải thất bại theo hợp đồng; ghi chú cũ, người duyệt, trạng thái và outbox đều giữ nguyên. Không ghi từng operation ra database rồi trả lỗi khi gặp operation bị cấm.

JSON Patch định nghĩa các operation và đường dẫn trong tài liệu patch; ứng dụng vẫn phải áp dụng phạm vi field và điều kiện nghiệp vụ của mình. Tham khảo [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902.html).

Thêm hai ca riêng: gán số lượng thành `3` lặp lại và thêm một phần tử vào mảng lặp lại. Kết quả dự kiến phải theo phép sửa được công bố. Không gắn nhãn “mọi PATCH đều idempotent” hoặc “không PATCH nào có thể idempotent”.

### 7.4. POST: idempotency là một phần hợp đồng ứng dụng

Với lệnh duyệt có `Idempotency-Key`, gửi lại đúng key và đúng nội dung. Kỳ vọng của ví dụ là trả lại kết quả lệnh đã ghi nhận, không thêm quyết định, outbox hoặc tác vụ tiếp theo.

Các ca cần tách riêng:

| Biến thể | Oracle nghiệp vụ |
| --- | --- |
| Cùng key, cùng nội dung, cùng phạm vi được cấp quyền | Không thực thi quyết định lần hai |
| Cùng key, nội dung khác | Bị từ chối theo hợp đồng xung đột key; không sửa lệnh cũ |
| Cùng chuỗi key nhưng khác tenant hoặc actor | Không đọc nhầm kết quả lệnh của người khác |
| Key mới cho đơn đã duyệt | State machine và quy tắc một quyết định vẫn ngăn tác động lặp |
| Hai yêu cầu cùng key đến đồng thời | Chỉ một kết quả lệnh được ghi nhận và phát sự kiện nghiệp vụ |

Phạm vi key cần gắn với tenant, actor có thẩm quyền, thao tác và dấu vân tay nội dung phù hợp. Cơ chế lưu kết quả lệnh không được trở thành đường đọc vượt quyền. Kiểm tra cả trường hợp quyền đối tượng đã bị thu hồi theo chính sách truy xuất kết quả của hệ thống.

Không suy từ idempotency của API ra bảo đảm giao nhận đúng một lần cho hàng đợi. Nếu consumer có thể nhận lại thông điệp, cần thử gửi lại cùng event và kiểm tra nó không thực hiện lần hai tác động đang được bảo vệ.

## 8. Điều kiện phiên bản và cạnh tranh phải được kiểm tra tại chỗ ghi

Với API sử dụng `If-Match`, kiểm tra điều kiện trên phiên bản hiện hành trước khi sửa; dùng so sánh strong ETag. Điều kiện không thỏa thường dẫn đến `412`, thay vì tự đổi sang một mã xung đột tùy ý. Chi tiết nằm trong [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Trong ví dụ, body `expectedVersion` là lựa chọn khác do ứng dụng định nghĩa và có thể dùng `409` theo hợp đồng. Không trộn hai cơ chế trong test mà không xác định cơ chế nào đang được kiểm tra.

Kịch bản cạnh tranh cho PUT hoặc PATCH:

1. Hai client được cấp quyền cùng đọc nội dung ở phiên bản V7.
2. Client A đề nghị đổi số lượng thành 4; client B đề nghị đổi thành 8.
3. Cho hai request đi tới điểm cạnh tranh bằng barrier hoặc latch trong test harness.
4. Với chính sách “mỗi lần ghi đều tăng phiên bản, chỉ chấp nhận V7 một lần”, đúng một thay đổi được commit.
5. Request còn lại nhận lỗi điều kiện/xung đột đúng hợp đồng; đọc transaction mới cho thấy một kết quả nhất quán.
6. Không có reservation, giá hoặc outbox từ thay đổi thua cuộc bị ghi ra ngoài.

Không dùng `Thread.sleep()` rồi suy ra đã tạo được race. Cũng không ghi đè phiên bản khách gửi bằng phiên bản vừa đọc từ database trước khi so sánh: cách đó làm mất ý nghĩa kiểm tra stale update.

Với POST duyệt, một test tương tự phải kiểm tra quyết định được ghi cùng chuyển trạng thái và outbox trong ranh giới transaction phù hợp. Nếu có dịch vụ ngoài không cùng transaction, test cả cơ chế outbox, khử trùng và phục hồi được thiết kế cho dịch vụ đó; rollback database không tự thu hồi một lời gọi ngoài đã thành công.

## 9. Method override: kiểm tra method trên đường truyền và method hiệu lực

Một hệ thống có thể nhận POST từ form rồi chuyển thành DELETE hoặc PATCH. Gọi **method trên đường truyền** là giá trị client thực gửi; **method hiệu lực** là giá trị sau bước xử lý override mà ứng dụng dùng để dispatch.

Nguy cơ xuất hiện khi gateway đánh giá một method, lớp bảo mật đánh giá method khác và router lại thực hiện thao tác thứ ba. Các dạng tín hiệu thường cần khảo sát gồm `_method`, `X-HTTP-Method-Override`, `X-HTTP-Method` và `X-Method-Override`. Việc khảo sát method hỗ trợ, vượt kiểm soát truy cập và override thuộc phạm vi [OWASP WSTG — HTTP Methods](https://wstg.owasp.org/latest/06-Configuration_and_Deployment_Management/05-HTTP_Methods/).

Đừng giả định mọi tín hiệu trên đều hoạt động. Chúng chỉ có ý nghĩa nếu proxy, framework hoặc mã ứng dụng thực sự triển khai. Chẳng hạn, `HiddenHttpMethodFilter` của Spring đọc tham số form từ POST và có tập method đích được giới hạn; cần đối chiếu phiên bản và cấu hình đang dùng. Nó không chứng minh các header override đều được hỗ trợ. Xem [Spring — HiddenHttpMethodFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/HiddenHttpMethodFilter.html).

Ma trận kiểm thử override của ứng dụng cần bao gồm:

| Yêu cầu | Điều phải xác minh |
| --- | --- |
| POST kèm `_method=DELETE` khi tính năng được bật | Đi vào đúng lệnh DELETE, vẫn kiểm tra chủ sở hữu, tenant, trạng thái và CSRF |
| POST kèm một header override không được hỗ trợ | Header bị bỏ qua hoặc yêu cầu bị từ chối theo cấu hình; không âm thầm đổi nghĩa |
| GET kèm tín hiệu override sang thao tác ghi | Không thực hiện lệnh ghi trong chính sách của ứng dụng ví dụ |
| Header nói PATCH nhưng form nói DELETE | Có quy tắc xử lý mâu thuẫn rõ ràng; không để các lớp chọn khác nhau |
| Tham số override xuất hiện nhiều lần | Không có chênh lệch cách chọn giá trị giữa lớp bảo mật và router |
| Method ghi qua override nhưng thiếu CSRF | Bị chặn theo chính sách CSRF như đường ghi trực tiếp |
| Actor chỉ đọc dùng override để xóa | Vẫn bị từ chối theo quyền đối tượng |

Với hệ thống dùng override, chuẩn hóa tại một vị trí xác định và bảo đảm các quyết định an ninh phía sau dựa trên cùng method hiệu lực. Ở biên mạng, kiểm tra rằng policy dành cho method trên đường truyền không tạo một lối đi rộng hơn khi request được diễn giải lại bên trong.

Gửi các ca qua gateway triển khai thực tế và qua origin trong môi trường kiểm thử được phép truy cập. So sánh correlation ID, route, method trên đường truyền, method hiệu lực và quyết định cuối. Không ghi token, cookie hoặc toàn bộ body nhạy cảm chỉ để phục vụ việc đối chiếu này.

Method có phân biệt hoa/thường theo [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.1). Nếu kiểm tra biến thể như `post`, hãy ghi rõ phản hồi ở từng lớp; đừng tự động coi đó là POST rồi kết luận hệ thống đã kiểm tra cùng một đường đi.

## 10. Khung kiểm thử tích hợp Java với Spring MVC

### 10.1. Giới hạn mapping rõ ràng

Một mapping như sau có phạm vi quá rộng nếu ý định chỉ là nhận POST:

```java
@RequestMapping("/orders/{id}/approve")
ApprovalReceipt approve(@PathVariable UUID id, @RequestBody ApprovalInput input) {
    return approvalService.approve(id, input);
}
```

Nên khai báo method cụ thể và vẫn giữ kiểm tra nghiệp vụ trong application service:

```java
@PostMapping("/orders/{id}/approve")
ApprovalReceipt approve(@PathVariable UUID id, @RequestBody ApprovalInput input) {
    return approvalService.approve(id, input);
}
```

Spring mô tả `@RequestMapping` không giới hạn method là mapping cho mọi method, còn các annotation như `@PostMapping` giúp giới hạn rõ hơn. Hành vi mapping cần được xác minh cùng cấu hình lớp và filter thực tế, theo [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).

Đổi annotation chưa đủ chứng minh bản sửa hoàn tất. Service phải xác định actor từ ngữ cảnh tin cậy, kiểm tra tenant, quyền theo đối tượng, tách biệt nhiệm vụ, trạng thái và phiên bản ngay trong luồng thực thi lệnh.

### 10.2. Ca sai method và positive control

Khung dưới dùng JUnit Jupiter, MockMvc, Spring Security Test và AssertJ. `CommittedFixtures`, `BusinessProbe`, `TestSessions`, `ApprovalFixture` và `BusinessView` là các thành phần test cần tự hiện thực cho mô hình dữ liệu của ứng dụng. Đây là ví dụ cấu trúc, không phải một lớp có thể chép vào mọi dự án để chạy ngay.

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApprovalMethodIT {
    @Autowired MockMvc mvc;
    @Autowired CommittedFixtures fixtures;
    @Autowired BusinessProbe probe;
    @Autowired TestSessions sessions;

    @ParameterizedTest
    @ValueSource(strings = {"GET", "HEAD", "PUT", "PATCH", "DELETE"})
    void anotherMethodCannotApprove(String method) throws Exception {
        ApprovalFixture f = fixtures.pendingOrderForIndependentReviewer();
        BusinessView before = probe.readInNewTransaction(f.orderId());

        MvcResult result = mvc.perform(request(
                    HttpMethod.valueOf(method),
                    "/orders/{id}/approve", f.orderId())
                .session(sessions.forActor(f.reviewerId()))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"expectedVersion\":" + f.version() + "}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().exists(HttpHeaders.ALLOW))
            .andReturn();

        String allowHeader = result.getResponse().getHeader(HttpHeaders.ALLOW);
        Set<String> allow = Arrays.stream(allowHeader.split(","))
            .map(String::trim)
            .collect(Collectors.toSet());
        assertThat(allow).contains("POST");
        assertThat(allow).doesNotContain(method);

        BusinessView after = probe.readInNewTransaction(f.orderId());
        assertThat(after).isEqualTo(before);
    }

    @Test
    void validPostApprovesExactlyOneDecision() throws Exception {
        ApprovalFixture f = fixtures.pendingOrderForIndependentReviewer();
        BusinessView before = probe.readInNewTransaction(f.orderId());

        mvc.perform(post("/orders/{id}/approve", f.orderId())
                .session(sessions.forActor(f.reviewerId()))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"expectedVersion\":" + f.version() + "}"))
            .andExpect(status().isOk());

        BusinessView after = probe.readInNewTransaction(f.orderId());
        assertThat(after.status()).isEqualTo("APPROVED");
        assertThat(after.approvedBy()).isEqualTo(f.reviewerId());
        assertThat(after.approvalCount()).isEqualTo(before.approvalCount() + 1);
        assertThat(after.approvalEventCount())
            .isEqualTo(before.approvalEventCount() + 1);
    }
}
```

Các static import được dùng là `MockMvcRequestBuilders.request/post`, `MockMvcResultMatchers.status/header`, `SecurityMockMvcRequestPostProcessors.csrf` và `Assertions.assertThat` của AssertJ. Các kiểu còn lại thuộc Java, JUnit Jupiter và Spring Test tương ứng.

Điều kiện để khung test có ý nghĩa:

- Test profile dùng chuỗi filter và mapping của ứng dụng; không tắt bảo mật để dễ nhận `405`.
- Fixture được commit trước request. Phiên đăng nhập thuộc actor cụ thể, có đúng quyền duyệt đối tượng và không phải người tạo đơn.
- `BusinessProbe` đọc database bằng transaction mới và trả snapshot bất biến; không truy vấn thông qua chính endpoint đang được kiểm tra.
- Snapshot bao phủ quyết định, trạng thái, giá, reservation, outbox và công việc nghiệp vụ liên quan; không bao gồm log truy cập được phép phát sinh.
- Các service nghiệp vụ thật và persistence thật tham gia test. Nếu mock `approvalService`, việc không ghi database chỉ phản ánh mock không có tác động.
- Mỗi lần gọi test tham số có dữ liệu riêng. Positive control dùng đơn khác để không làm ca âm thất bại chỉ vì đơn đã được duyệt.

Mã minh họa giả định ứng dụng cho actor hợp lệ đi tới lớp mapping và dùng `200` khi POST duyệt thành công. Với API chọn hợp đồng khác, thay expectation theo hợp đồng đã phê duyệt, đồng thời giữ nguyên oracle nghiệp vụ. Không sửa assertion theo phản hồi hiện tại chỉ để test xanh.

`Allow` được phân tích thành tập vì thứ tự liệt kê không phải mục tiêu. Thêm một test riêng đối chiếu đầy đủ tập method được công bố cho từng URL theo cấu hình ứng dụng, bao gồm OPTIONS nếu được hỗ trợ. Đừng dùng các assertion tối thiểu của ví dụ để thay cho kiểm thử hợp đồng hoàn chỉnh.

### 10.3. Ranh giới của MockMvc

MockMvc phù hợp để đi qua mapping và filter chain trong môi trường test, nhưng không tự kiểm tra cấu hình reverse proxy, parser của servlet container đang chạy, TLS, cache biên hoặc hành vi CORS của trình duyệt.

Do đó, bổ sung kiểm thử qua máy chủ thật cho các vấn đề phụ thuộc đường truyền: HEAD không có body, method override, nhiều tham số trùng tên, khác biệt hoa/thường, header bị proxy đổi và hành vi ở cache. Với case CORS, dùng trình duyệt khi cần chứng minh preflight và việc gửi request thực tế theo chính sách browser.

Khi kiểm tra field trùng, tạo request giữ nguyên thứ tự và số lần xuất hiện. Một `Map<String, String>` làm mất giá trị trùng trước khi gửi sẽ không kiểm tra được tình huống dự kiến.

## 11. Cache, yêu cầu tự động và xử lý bất đồng bộ

Một URL đọc có thể được gọi bởi trang xem trước liên kết, công cụ giám sát hoặc quá trình tải dữ liệu trước. Nếu URL đó thực hiện duyệt hoặc giữ kho, tác động sẽ phụ thuộc việc ai đã vô tình đọc liên kết. Tạo một chuỗi thử cụ thể: GET, HEAD, GET lại; sau mỗi bước, xác nhận không có lệnh nghiệp vụ mới.

Đối với dữ liệu cần phân quyền, kiểm tra cache theo thứ tự actor: Minh đọc đơn, rồi Chi hoặc Đức yêu cầu cùng URL. Kết quả phải phù hợp quyền và bản chiếu của từng người. Cache key chỉ có ID đơn có thể trả dữ liệu mà bỏ qua tenant hoặc quyền xem từng field.

Chính sách lưu và dùng lại phản hồi còn phụ thuộc method, trạng thái và header cache; không dùng nhận định “mọi POST đều không thể được cache” để bỏ qua kiểm tra triển khai. Các quy tắc cache được trình bày trong [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html).

Nếu có conditional GET, thêm ca actor đã mất quyền mang lại ETag từng được nhận. Trong ứng dụng ví dụ, yêu cầu phải qua quyết định cấp quyền hiện hành; ETag cũ không phải bằng chứng sở hữu đối tượng. Kiểm tra cả đường tới origin và đường cache có thể trả lời mà không đi tới origin.

Với queue/outbox, một test có thể thất bại muộn. Ví dụ, POST sai quyền trả `403` nhưng interceptor đã enqueue `ReserveStock`. Hãy dùng consumer kiểm soát được trong test để xử lý hết tập thông điệp liên quan, rồi xác nhận không có giữ kho ngoài ý muốn. Đặt thời hạn chờ rõ ràng theo cơ chế test; một lần đọc ngay sau response không chứng minh không có tác động bất đồng bộ.

Nếu thay dịch vụ thanh toán hoặc kho bằng fake, fake phải ghi nhận lệnh và hỗ trợ kiểm tra trùng. `verifyNoInteractions()` trên một mock tại controller không bao phủ một worker khác đang xử lý outbox.

## 12. Đọc kết quả và tránh kết luận sai

| Quan sát | Kết luận chưa đủ | Bằng chứng cần thêm |
| --- | --- | --- |
| PUT tới `/approve` trả `403` | “Mapping POST đã đúng” | Gửi lại với auth và CSRF hợp lệ; xác định lớp từ chối |
| GET trả `200` và đúng JSON | “GET an toàn” | Snapshot nghiệp vụ và outbox không đổi |
| HEAD không trả body | “HEAD không lộ dữ liệu” | Header, mã lỗi và quyền đối tượng vẫn đúng chính sách |
| OPTIONS có POST trong danh sách | “Người gọi được duyệt” | Lệnh POST thật với actor và đối tượng cụ thể |
| Hai DELETE đều được chấp nhận | “DELETE idempotent” | Reservation chỉ giải phóng một lần |
| PATCH báo lỗi | “Không có gì được ghi” | Ghi chú và tác động liên quan đều giữ nguyên sau commit |
| Test dùng mock service xanh | “Database được bảo vệ” | Luồng tích hợp với service và persistence thật |
| Gateway chặn GET nhưng origin chưa thử | “Không thể đổi method” | Cấu hình đường đi thực tế và chuẩn hóa method ở các lớp |
| Gửi đồng thời nhưng chỉ thấy một response lỗi | “Race đã được xử lý” | Snapshot sau commit, số quyết định, outbox và tác động ngoài |

Báo cáo một lỗi nên nêu rõ:

```text
Test: M02-HEAD-APPROVE
Contract: /approve chỉ thực hiện quyết định qua POST hợp lệ
Actor: reviewer thuộc tenant A, khác người tạo
Fixture: đơn mới ở PENDING_APPROVAL, version đúng
Request: method trên đường truyền = HEAD, override = không
Observed response: 405, Allow có POST
Observed committed effect: thêm 1 ApprovalGranted trong outbox
Conclusion: FAIL — phản hồi từ chối nhưng đã tạo tác động nghiệp vụ
Layer exercised: server tích hợp; chưa qua gateway
```

Ở đây, lỗi nằm ở tác động đã ghi dù mã trạng thái có vẻ đúng. Báo cáo giúp người sửa truy tìm đoạn tạo sự kiện trước khi quyết định chấp nhận request hoàn tất.

Khi đưa vào CI, giữ một tập ca hợp đồng cho endpoint rủi ro cao và một tập ca chạy qua hạ tầng triển khai. Thêm route hoặc đổi filter phải kéo theo cập nhật có chủ đích về method được nhận, quyền cần thiết và oracle dữ liệu. Danh sách annotation hoặc tài liệu OpenAPI là đầu vào đối chiếu, không thay thế việc gửi request thật.

## 13. Bài tập thực hành

Một ứng dụng có bốn vấn đề:

```text
A. GET /orders/{id}?submit=true gọi submitService.
B. /orders/{id}/approve dùng @RequestMapping không giới hạn method.
C. DELETE /orders/{id} tăng availableStock trước khi đánh dấu reservation released.
D. PATCH cập nhật từng field rồi mới kiểm tra có field bị cấm.
```

Hãy thiết kế bốn nhóm test với fixture riêng:

1. Với A, thử GET, HEAD và đọc lại sau cache miss. Xác định cách chứng minh không sinh quyết định gửi duyệt hoặc công việc nền.
2. Với B, tạo positive control POST, sau đó thay từng method. Tách test mapping khỏi test thiếu quyền, tự duyệt và khác tenant.
3. Với C, thử tuần tự rồi đồng thời trên cùng reservation. Oracle phải đo lượng đã giải phóng và tồn kho sau commit.
4. Với D, đặt field hợp lệ trước field bị cấm. Xác nhận toàn bộ patch không để lại thay đổi hoặc sự kiện nào.

Với mỗi nhóm, ghi rõ dữ liệu trước, request, phản hồi mong đợi, trạng thái sau và cách quan sát tác động bất đồng bộ. Không dùng một yêu cầu thiếu xác thực để chứng minh mọi quy tắc bên trong đều an toàn.

Một bộ kiểm thử method có giá trị khi nó chứng minh được mối liên hệ giữa đường đi HTTP và invariant nghiệp vụ: thao tác đọc giữ đúng ý nghĩa đọc, lệnh ghi chỉ chạy khi đủ điều kiện, còn việc gửi lại hoặc cạnh tranh không tạo thêm quyền hay tác động ngoài hợp đồng.
