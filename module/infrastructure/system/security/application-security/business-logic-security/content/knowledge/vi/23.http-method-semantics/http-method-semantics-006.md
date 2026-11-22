# Method authorization matrix: ma trận phân quyền theo HTTP method và hành động

## 1. Mục tiêu bài học

Trong chương **HTTP Method Semantics** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **method authorization matrix** là ma trận mô tả ai được dùng phương thức HTTP nào trên route nào để thực hiện hành động nghiệp vụ nào.

Ma trận không chỉ là bảng “GET được đọc, POST được ghi”. Cùng một POST có thể tạo bản nháp, gửi duyệt, duyệt hoặc phát lệnh chi trả; các hành động đó có quyền và điều kiện khác nhau.

Nếu gateway, router và domain hiểu khác nhau về method hoặc action, caller có thể đổi cách gọi để bỏ qua kiểm soát dù nội dung nghiệp vụ vẫn giống nhau.

Sau bài học, bạn có thể:

- Xây dựng ma trận theo method, route, action và loại chủ thể.
- Phân biệt endpoint hỗ trợ một method với caller có quyền dùng nó.
- Giữ quyền theo đối tượng, tenant, field và trạng thái bên cạnh kiểm soát method.
- Xử lý HEAD, OPTIONS, method override và route thay thế nhất quán.
- Kiểm thử đổi method, gọi trực tiếp bước sau, gửi lại và tranh chấp trạng thái.
- Xác nhận request bị chặn không tạo thay đổi hoặc công việc ngoài ý định.

## 2. Method là một phần của hợp đồng, chưa phải quyết định quyền đầy đủ

Một request có thể được nhận diện bởi:

~~~text
method hiệu lực
+ route thực sự được match
+ hành động nghiệp vụ
+ actor
+ resource và tenant
+ tham số, trạng thái và policy
~~~

Ví dụ:

~~~text
POST /purchase-requests/{id}
POST /purchase-requests/{id}/approve
POST /purchase-requests/{id}/execute
~~~

Cùng là POST không có nghĩa quyền edit, approve và execute tương đương. Tên route cũng chưa chứng minh handler chỉ làm điều mà tên đó gợi ý.

### 2.1. Ba câu hỏi cần tách biệt

| Câu hỏi | Ví dụ | Kết luận chưa được phép suy ra |
|---|---|---|
| Route có hỗ trợ method này không? | Route approve hỗ trợ POST | Mọi người dùng được POST vào đó |
| Caller có quyền cho action trên đối tượng không? | Reviewer được approve hồ sơ này | Hồ sơ hiện còn có thể approve |
| Điều kiện thực hiện hiện tại có đúng không? | Hồ sơ đang SUBMITTED, revision khớp | Có thể bỏ các bất biến sau ghi |

Một ma trận tốt mô tả lớp quyền và tham chiếu các điều kiện bắt buộc; nó không thay thế state machine hoặc transaction.

### 2.2. Method không phân biệt đầy đủ rủi ro nghiệp vụ

Các thao tác cùng PATCH có thể là:

~~~text
sửa mô tả
sửa số tiền đề nghị
đổi owner
tự đặt trạng thái APPROVED
~~~

Chúng có mức quyền khác nhau. Nếu PATCH tổng quát cho cập nhật mọi field, việc ma trận chỉ cho “editor được PATCH” vẫn để mở đường nhảy phê duyệt.

Tương tự, quyền GET một hồ sơ không tự bao gồm export toàn tenant hoặc đọc mọi field nhạy cảm.

## 3. Ngữ nghĩa method ảnh hưởng thiết kế kiểm soát

| Method | Vai trò thường dùng | Yêu cầu cần chú ý |
|---|---|---|
| GET | Lấy biểu diễn tài nguyên | Không thiết kế như command thay đổi trạng thái nghiệp vụ đích |
| HEAD | Lấy thông tin tương ứng GET nhưng không có response body | Giữ kiểm soát truy cập và không tạo hiệu ứng ghi |
| OPTIONS | Mô tả khả năng giao tiếp theo hợp đồng | Không dùng kết quả như quyền thực hiện command |
| POST | Xử lý theo ngữ nghĩa endpoint, tạo tài nguyên hoặc command | Mỗi action cần quyền, tiền điều kiện và bảo vệ retry phù hợp |
| PUT | Tạo/thay thế trạng thái biểu diễn ở tài nguyên đích theo hợp đồng | Không được thay mọi field quyền hoặc trạng thái chỉ vì là replace |
| PATCH | Áp dụng thay đổi từng phần theo định dạng/hợp đồng | Kiểm tra operation, field, trạng thái cuối và quyền liên quan |
| DELETE | Yêu cầu xóa/bỏ liên kết tài nguyên theo hợp đồng | Kiểm tra quyền xóa, trạng thái, nghĩa vụ và lặp yêu cầu |

Bảng nêu vai trò thiết kế tổng quát. Payload và hiệu ứng cụ thể vẫn phải được đặc tả cho từng endpoint.

### 3.1. Safe không có nghĩa public

GET, HEAD và OPTIONS có ngữ nghĩa safe: caller không yêu cầu chúng tạo thay đổi nghiệp vụ đích như approve, thanh toán hoặc xóa hồ sơ.

Server vẫn có thể ghi log hoặc thực hiện hoạt động phụ trợ thích hợp. Điều này không cho phép đặt một command approve vào GET chỉ vì đó là “tác dụng phụ”.

Safe method vẫn có thể trả dữ liệu nhạy cảm và cần authentication, tenant isolation, object scope, projection hoặc giới hạn tài nguyên.

### 3.2. Idempotent không có nghĩa không cần authorization

PUT và DELETE được thiết kế có ngữ nghĩa idempotent: lặp cùng yêu cầu có cùng hiệu ứng dự định như thực hiện một lần. Điều đó không bắt buộc response phải giống nhau.

Ví dụ DELETE lần đầu có thể thành công, lần sau phản ánh tài nguyên không còn tồn tại theo hợp đồng.

Caller vẫn phải có quyền ở từng lần xử lý theo policy. Không được bỏ kiểm tra chỉ vì request là retry hoặc method được xem là idempotent.

POST có thể được bảo vệ replay bằng idempotency key ở tầng ứng dụng. PATCH có thể có hành vi lặp an toàn trong một hợp đồng cụ thể, nhưng không được mặc định mọi patch đều như vậy.

### 3.3. GET không được dùng làm đường vòng cho command

Các dạng sau cần được xem lại:

~~~text
GET /purchase-requests/{id}/approve
GET /purchase-requests/{id}?action=delete
HEAD /payments/{id}?confirm=true
~~~

Một URL đọc có thể bị mở lại, theo link, kiểm tra hoặc sử dụng theo cách mà caller không có ý định xác nhận một thay đổi nhạy cảm.

Nếu nghiệp vụ là approve/delete/confirm, dùng command và method phù hợp, đồng thời kiểm tra quyền và tiền điều kiện tại server.

Chuyển từ GET sang POST không tự hoàn tất bảo mật; nó chỉ sửa một phần hợp đồng giao tiếp.

## 4. Đơn vị của mỗi dòng ma trận

Một dòng nên chứa tối thiểu:

~~~text
route template
method hiệu lực được hỗ trợ
business action
quyền nền/capability
điều kiện tenant và object scope
trạng thái/revision và điều kiện nghiệp vụ
field/operation được phép
quy tắc concurrency, replay và audit
~~~

Không dùng một dòng rộng kiểu /api/** + POST = mọi người đã đăng nhập nếu phía dưới có cả approve và execute.

### 4.1. Actor category không chỉ là tên role

“Owner” phải là quan hệ được xác minh với chính đối tượng. “Reviewer” phải đủ thẩm quyền cho hồ sơ, hạn mức và assignment liên quan.

Không tin ownerId, role hoặc actionLabel do body gửi để chọn một ô cho phép.

Một actor có nhiều role có thể nhận nhiều nguồn quyền, nhưng action, scope và ràng buộc của từng nguồn phải đi cùng nhau. Không lấy quyền READ toàn tenant rồi mở rộng APPROVE từ một đơn vị sang mọi đối tượng.

### 4.2. Mặc định không có dòng khớp thì không tạo hiệu ứng

Nếu tổ hợp route/method/action không được hỗ trợ, không fallback sang một handler ghi tổng quát.

Nếu route có hỗ trợ nhưng actor không đủ quyền, không cho phép chỉ vì một dòng method khác cùng URL đã được cấp.

Cách trả lỗi và mức tiết lộ có thể khác theo hợp đồng; nguyên tắc chung là không tạo hiệu ứng từ một tổ hợp chưa được cho phép.

## 5. Ma trận mẫu cho hồ sơ mua hàng

Đây là chính sách minh họa, không phải mặc định của mọi hệ thống.

Các nhóm chức năng:

- **U**: caller chưa có xác thực được chấp nhận cho API nghiệp vụ.
- **V**: reader có phạm vi đọc xác định.
- **E**: requester/editor có quyền trên hồ sơ hoặc phạm vi tạo tương ứng.
- **R**: reviewer có thẩm quyền xét duyệt theo đối tượng.
- **W**: worker có danh tính dịch vụ và phạm vi thực thi operation.

Ký hiệu:

~~~text
C = ứng viên được phép nếu tất cả điều kiện bổ sung đúng.
— = nhóm chức năng này không cấp action đó.
~~~

Một actor có nhiều nguồn quyền được đánh giá theo policy; ô C không phải lời cho phép vô điều kiện.

### 5.1. Ánh xạ method và route tới action

| Method | Route template | Action |
|---|---|---|
| GET | /purchase-requests | REQUEST_LIST |
| POST | /purchase-requests | REQUEST_CREATE |
| GET | /purchase-requests/{id} | REQUEST_READ |
| HEAD | /purchase-requests/{id} | REQUEST_READ với response không có body |
| PATCH | /purchase-requests/{id} | REQUEST_EDIT_DRAFT |
| PUT | /purchase-requests/{id}/delivery-address | REQUEST_REPLACE_ADDRESS |
| DELETE | /purchase-requests/{id} | REQUEST_DELETE_DRAFT |
| POST | /purchase-requests/{id}/submit | REQUEST_SUBMIT |
| POST | /purchase-requests/{id}/approve | REQUEST_APPROVE |
| POST | /purchase-requests/{id}/reject | REQUEST_REJECT |
| POST | /purchase-requests/{id}/execute | REQUEST_EXECUTE |

OPTIONS được xử lý theo hợp đồng metadata/CORS riêng ở phần sau. Method hoặc tổ hợp route khác không được tự ánh xạ tới một command ghi mặc định.

### 5.2. Ma trận nhóm chức năng

| Action | U | V | E | R | W |
|---|---|---|---|---|---|
| REQUEST_LIST | — | C | C | C | — |
| REQUEST_READ, gồm HEAD | — | C | C | C | — |
| REQUEST_CREATE | — | — | C | — | — |
| REQUEST_EDIT_DRAFT | — | — | C | — | — |
| REQUEST_REPLACE_ADDRESS | — | — | C | — | — |
| REQUEST_DELETE_DRAFT | — | — | C | — | — |
| REQUEST_SUBMIT | — | — | C | — | — |
| REQUEST_APPROVE | — | — | — | C | — |
| REQUEST_REJECT | — | — | — | C | — |
| REQUEST_EXECUTE | — | — | — | — | C |

Ví dụ R có thể đọc nội dung được giao để review, nhưng không vì thế được sửa nội dung cần duyệt hoặc phát lệnh thanh toán.

W chỉ được action/phạm vi đã cấp. Việc là service account không tự cho quyền gọi mọi GET, POST hoặc thao tác trên mọi tenant.

### 5.3. Điều kiện bắt buộc của các ô C

| Nhóm action | Điều kiện minh họa |
|---|---|
| LIST/READ | Tenant, quan hệ/grant đọc, row/field scope; không có hiệu ứng ghi nghiệp vụ |
| CREATE | Quyền tạo trong phạm vi đích; owner/creator/tenant được xác lập đúng; liên kết ngân sách hợp lệ |
| EDIT_DRAFT | DRAFT, đúng revision, chỉ field cho phép; không đổi owner/approval/tenant bằng update chung |
| REPLACE_ADDRESS | Quyền sửa địa chỉ; DRAFT; snapshot địa chỉ mới hợp lệ; xử lý lại verification theo chính sách |
| DELETE_DRAFT | Quyền xóa đúng đối tượng; DRAFT; không có nghĩa vụ/tác vụ ngăn xóa |
| SUBMIT | Quyền gửi hồ sơ; DRAFT; nội dung đầy đủ; revision khớp |
| APPROVE | Reviewer đúng scope/hạn mức; SUBMITTED; không xung đột nhiệm vụ; nội dung và revision đúng |
| REJECT | Reviewer đủ quyền; SUBMITTED; lý do và trạng thái quyết định phù hợp |
| EXECUTE | Service authority đúng operation/tenant; approval hợp lệ cho snapshot; không thực thi trùng; các điều kiện nghiệp vụ còn đúng |

Không rút gọn các điều kiện thành một phép kiểm tra role duy nhất.

### 5.4. Ma trận quyền không tự bảo vệ field

Trong mẫu:

~~~text
PATCH item:
  chỉ sửa các field DRAFT được công bố.

PUT delivery-address:
  chỉ thay value object địa chỉ theo hợp đồng.

POST approve:
  tạo quyết định duyệt bằng danh tính server xác thực.
~~~

Không cho PATCH status=APPROVED hoặc PUT cả entity chứa approval để bỏ qua action REQUEST_APPROVE.

Payload của command và nested properties phải được giới hạn theo từng action.

## 6. HEAD, OPTIONS và các loại metadata

### 6.1. HEAD cần giữ biên truy cập của GET tương ứng

Không có body không có nghĩa không lộ thông tin. Status và các header có thể tiết lộ sự tồn tại, phiên bản hoặc đặc điểm tài nguyên.

Nếu GET của một đối tượng cần scope tenant/người dùng, HEAD tương ứng cũng không được mở rộng ngoài scope đó chỉ vì handler không trả body.

Nếu framework thực hiện HEAD thông qua đường xử lý GET, cần bảo đảm đường GET không có command ghi. Xóa body ở cuối response không hoàn tác một thay đổi đã diễn ra.

### 6.2. OPTIONS có hợp đồng riêng nhưng không mở quyền command

Ứng dụng có thể trả metadata method/CORS theo chính sách, đôi khi không yêu cầu cùng ngữ cảnh xác thực như một command nghiệp vụ.

Điều đó không cho phép actual request đi sau bỏ qua authentication, authorization hoặc state machine.

Nếu trả capability tĩnh cho một route template, không cần nạp object nhạy cảm chỉ để cho biết route hỗ trợ method nào. Nếu metadata phụ thuộc tài nguyên, phải kiểm soát việc tiết lộ phù hợp.

Không chặn mọi OPTIONS một cách máy móc rồi xem đó là phân quyền hoàn chỉnh; cũng không coi preflight thành công là bằng chứng caller được approve.

### 6.3. Phân biệt ba loại thông tin

| Thông tin | Ý nghĩa | Không chứng minh |
|---|---|---|
| Allow | Các method được tài nguyên/route hỗ trợ theo ngữ nghĩa response | Caller có quyền mọi action tương ứng |
| Access-Control-Allow-Methods | Chính sách method cho tương tác cross-origin của browser theo CORS | Một client bất kỳ được tạo hiệu ứng nghiệp vụ |
| allowedActions của ứng dụng | Kết quả/hướng dẫn action phù hợp trong ngữ cảnh được tính | Quyền còn nguyên khi command đến sau đó |

CORS không thay authentication hoặc quyền theo đối tượng. Một client không bị ràng buộc như browser vẫn có thể gửi request trực tiếp tới endpoint.

allowedActions giúp UI, nhưng command handler vẫn kiểm tra dữ liệu và quyền hiện tại.

### 6.4. Method không cần cho API nghiệp vụ

Trong ví dụ, các method ngoài tập được khai báo không có handler nghiệp vụ mặc định.

Nếu hạ tầng có các method phục vụ mục đích khác, phải quản lý ở phạm vi phù hợp. Không để chúng được router chuyển nhầm sang handler GET/POST chung rồi tạo hiệu ứng ngoài ma trận.

## 7. Method override phải được nhìn nhận nhất quán

Một số hệ thống hỗ trợ client gửi POST nhưng khai một method hiệu lực khác qua field/header được quy ước. Khả năng và cú pháp thực tế tùy stack/cấu hình.

### 7.1. Cuộc lệch giữa method trên đường truyền và method thực thi

~~~text
Gateway thấy POST và áp quyền POST.
Middleware đổi effective method thành DELETE.
Router gọi handler DELETE.
Handler tin gateway đã phân quyền đầy đủ.
~~~

Caller có thể chạm một hành động mà lớp kiểm soát trước đó chưa đánh giá.

Không giải quyết bằng cách chỉ thêm một tên header vào blocklist trong khi vẫn còn cơ chế override khác.

### 7.2. Chọn một hợp đồng rõ ràng

Nếu không cần override:

~~~text
Không bật cơ chế đổi method.
Field/header override không được làm thay method thực tế.
Input ngoài hợp đồng được xử lý rõ ràng.
~~~

Nếu cần cho một nhóm client/route:

~~~text
Chỉ nhận nguồn và giá trị được quy định.
Xác định effective method một lần theo pipeline tin cậy.
Routing và authorization dùng cùng effective method.
Áp đúng kiểm soát CSRF khi giao thức yêu cầu.
Từ chối mâu thuẫn hoặc dạng không hỗ trợ.
~~~

Wire method có thể được giữ để audit, nhưng quyền cuối phải khớp action thực sự được thực hiện.

### 7.3. Không tin một nhãn action khác với handler

Ví dụ body khai action=READ nhưng một field khác làm dispatcher gọi approve.

Policy phải dùng metadata/action đã được server ánh xạ tới handler thật, không nhãn do caller tự chọn để được vào một ô dễ hơn.

Tương tự, nếu một POST /commands phục vụ nhiều command type, ma trận cần thêm chiều command type/action. Chỉ có một dòng POST /commands = authenticated là quá rộng.

## 8. Biến ma trận thành kiểm soát thực thi

### 8.1. Dùng route đã match, không tự đoán từ chuỗi URL

Một policy resolver có thể nhận metadata từ router và method đã được giải quyết theo hợp đồng:

~~~java
EndpointPolicy resolvePolicy(
        MatchedRoute route, ResolvedMethod method) {
    return endpointPolicies.requireExact(
            route.id(), method.effectiveMethod());
}
~~~

EndpointPolicy là cấu hình phía server, không phải dữ liệu trong body. Nó có thể chỉ ra action, yêu cầu xác thực, decoder và các điều kiện endpoint tương ứng.

Không dùng các heuristic như:

~~~text
URL chứa "read" thì chỉ cần quyền xem.
Method bắt đầu bằng P thì là quyền write chung.
Không tìm thấy policy thì dùng policy GET.
~~~

Nếu framework có route alias hoặc middleware đặc biệt, metadata dùng để kiểm tra phải khớp handler thật sẽ chạy.

### 8.2. Các ràng buộc về thứ tự xử lý

Một pipeline logic có thể là:

~~~text
Xử lý thông tin proxy/override theo hợp đồng.
Xác định effective method và route thực sự.
Tìm đúng endpoint policy.
Xác thực và áp kiểm soát giao thức cần thiết.
Tạo actor/tenant context đã kiểm chứng.
Decode command đúng schema.
Nạp đối tượng trong đúng scope.
Kiểm tra action và các điều kiện nghiệp vụ.
Ghi transaction/ý định công việc.
Trả kết quả đúng mức độ hoàn tất.
~~~

Framework có thể tổ chức middleware khác nhau. Điều bắt buộc là không tạo hiệu ứng trước kiểm tra và không có sự lệch giữa method/action được authorize với handler được execute.

Các lookup nền phục vụ xác thực/resolve có thể xảy ra trước domain; chúng không phải quyền truy cập tự do vào dữ liệu nghiệp vụ.

### 8.3. Không để gateway trở thành lớp quyền cuối duy nhất

Gateway có thể kiểm tra token, route hoặc capability thô. Command handler có dữ liệu về object, state, revision và lịch sử nghiệp vụ.

Nếu chỉ kiểm tra gateway, các đường nội bộ, batch hoặc handler được tái sử dụng có thể bỏ qua điều kiện theo đối tượng.

Nên có một lớp kiểm soát action chung tại nơi thực hiện nghiệp vụ. Các route khác nhau trỏ tới cùng action đều phải đi qua lớp đó.

Một worker gọi trực tiếp application service vẫn cần thẩm quyền cho action tương ứng; không “được tin” chỉ vì không dùng HTTP.

## 9. Java minh họa action approve

Ví dụ này dùng repository và policy giả định. Actor/tenant đã được kiểm chứng, command chỉ chứa target và expected version; không nhận approvedBy, isApproved hoặc role.

~~~java
ApprovalResult approve(
        Actor actor, ApproveRequestCommand command) {
    return transactions.required(() -> {
        var request = requests.lockForUpdate(
                actor.tenantId(), command.requestId());

        var facts = policyFacts.requireFor(
                actor, REQUEST_APPROVE, request);

        authorization.requirePermit(
                actor, REQUEST_APPROVE, request, facts);

        requireVersion(request, command.expectedVersion());
        requireState(request, SUBMITTED);
        approvalRules.requireDecisionContext(
                actor, request, facts);

        var decision = ApprovalDecision.approved(
                decisionIds.next(),
                request.id(),
                request.contentRevision(),
                actor.personId(),
                facts.policyVersion(),
                clock.instant());

        decisions.insert(decision);
        request.approveAndAdvanceVersion(decision.id());
        requests.save(request);
        audit.insertApproval(actor, request, decision);
        outbox.insertApprovalGranted(request, decision);

        return ApprovalResult.from(request, decision);
    });
}
~~~

Mã là phác thảo, không phải chương trình độc lập. Các repository tham gia cùng transaction; exception bắt buộc làm rollback và kết quả thành công chỉ ra ngoài sau commit.

### 9.1. Kiểm tra nào bảo vệ điều gì?

| Lớp kiểm tra | Điều được bảo vệ |
|---|---|
| Method/route policy | Chỉ handler/action được công bố mới được gọi theo đường HTTP đó |
| REQUEST_APPROVE authorization | Actor có thẩm quyền cho chính action và đối tượng |
| Tenant/object lookup | Không nạp/ghi hồ sơ ngoài biên |
| State/version | Không duyệt nhầm trạng thái hoặc dữ liệu cũ |
| Approval rules | Hạn mức, assignment, phân tách nhiệm vụ và nội dung quyết định |
| Transaction/audit/outbox | Kết quả và bằng chứng cục bộ nhất quán |

Các hàm require phải là validation bắt buộc, không dùng Java assert làm kiểm soát bảo mật.

### 9.2. Event approved không phải quyền execute của caller

Outbox có thể thông báo hồ sơ đã được duyệt để một bước sau xử lý.

Worker thực thi vẫn phải có REQUEST_EXECUTE, đúng operation/snapshot và các điều kiện trước hiệu ứng. Caller R không có quyền gọi endpoint execute chỉ vì đã approve.

Nếu workflow tự động thực thi sau duyệt, đó là quyền của thành phần dịch vụ được cấp và giao thức đã thiết kế, không là một nhánh cho mọi POST đã đăng nhập.

### 9.3. Không giữ một setter status song song

Handler approve an toàn sẽ không có tác dụng nếu PATCH hoặc PUT chung vẫn cho:

~~~json
{
  "state": "APPROVED",
  "approvedBy": "another-person"
}
~~~

Đóng các đường cập nhật field trái action, gồm nested property, import và API cũ.

Tương tự, DELETE không được dùng để che một nghĩa vụ chi trả đã phát sinh; cần state machine hủy/khôi phục phù hợp thay vì chỉ xóa bản ghi.

## 10. Lỗi method, lỗi quyền và lỗi nghiệp vụ

Một hợp đồng có thể phân biệt:

| Trường hợp | Cách biểu đạt điển hình |
|---|---|
| Route không tồn tại | 404 |
| Method không được tài nguyên/route hỗ trợ | 405 theo hợp đồng và cách định tuyến |
| Endpoint yêu cầu xác thực nhưng chưa được chấp nhận | 401 theo cơ chế xác thực API |
| Đã xác thực nhưng không có quyền action/object | 403 hoặc chính sách che sự tồn tại bằng 404 |
| Có quyền nhưng trạng thái/version xung đột | Có thể dùng 409 |
| Command nhận xử lý bất đồng bộ | Có thể dùng 202 với trạng thái tra cứu phù hợp |

Nếu server tạo response 405, header Allow phải thể hiện các method được hỗ trợ theo hợp đồng của tài nguyên. Đây không phải danh sách quyền nghiệp vụ của caller.

Chi tiết thứ tự kiểm tra và mức tiết lộ phải được thiết kế nhất quán. Không bắt buộc mọi hệ thống để lộ sự khác nhau giữa “không tồn tại” và “không có quyền biết”.

### 10.1. Không dùng status code thay kiểm tra dữ liệu

Một request trả 405/403 nhưng trước đó đã đổi trạng thái hoặc enqueue job vẫn là lỗi.

Response 2xx cũng cần phản ánh đúng mức hoàn tất. 202 Accepted không chứng minh đã thanh toán; một command approve thành công không chứng minh worker đã execute.

### 10.2. Phân quyền và CSRF là hai trục

Với giao thức dùng thông tin xác thực tự được browser gửi, các command thay đổi trạng thái cần cơ chế chống CSRF phù hợp.

Không chỉ bảo vệ POST rồi quên PUT/PATCH/DELETE hoặc method hiệu lực qua override. Cũng không chuyển command sang GET để tránh xử lý một kiểm soát giao thức.

CSRF token hợp lệ không cấp quyền reviewer, không mở scope tenant và không chứng minh nội dung đã được duyệt. CORS không thay các lớp đó.

## 11. State machine, idempotency và concurrency nằm sau ô ma trận

### 11.1. Ô C không phải một lần cấp quyền vĩnh viễn

Reviewer được approve một hồ sơ hôm nay có thể mất quyền hoặc hồ sơ đổi revision trước request kế tiếp.

Mỗi lần thực thi phải dùng policy/facts đúng cam kết hiệu lực. Ma trận chỉ mô tả quy tắc, không lưu thay kết quả đánh giá.

### 11.2. Scope idempotency theo hành động nghiệp vụ

Cùng là POST nhưng submit, approve và execute không được chia sẻ một receipt như thể là cùng command.

Key/fingerprint cần gắn với tenant, caller/phạm vi được thiết kế, action, target và nội dung có ý nghĩa.

Nếu hai route hợp lệ thật sự là alias của cùng action, cần quyết định rõ cách nhận diện cùng ý định. Không để alias tạo hiệu ứng lặp hoặc làm receipt của action khác trở thành giấy phép.

Trước khi trả receipt, vẫn áp dụng kiểm tra truy cập kết quả hiện tại. Unsupported method không được đi tắt qua receipt để bỏ route policy.

### 11.3. Tính idempotent của method không bảo đảm toàn workflow đúng

Một DELETE được gọi lại có thể không xóa thêm bản ghi, nhưng nếu handler luôn phát một event hoàn tiền mới thì hiệu ứng nghiệp vụ vẫn bị lặp.

Một PUT cùng dữ liệu có thể giữ trạng thái cuối của resource, nhưng application phải quản lý việc ghi lịch sử, version và hiệu ứng liên quan theo hợp đồng.

Với POST có idempotency key, cần lưu receipt và thay đổi cục bộ nhất quán. Hiệu ứng ngoài hệ thống còn cần định danh ổn định, xử lý trùng và đối soát phù hợp.

### 11.4. Hai command hợp lệ vẫn có thể tranh chấp

Approve và reject hoặc approve và edit có thể cùng đọc một snapshot.

Các handler phải bảo vệ state/version và bất biến chung. Không được để mỗi endpoint có đúng ô quyền nhưng cả hai commit các quyết định mâu thuẫn.

Nếu edit thắng, approve phải xem revision mới hoặc bị chặn vì stale version. Nếu approve thắng, đường edit DRAFT không được ghi đè nội dung đã duyệt.

## 12. Audit cả method được gửi và action thực sự

Thông tin hữu ích có thể gồm:

~~~text
requestId / commandId
wire method và effective method
route template/routeId thực sự được match
business action
actor và tenant
object/revision/version
policy hoặc grant được sử dụng
override source nếu có và được chấp nhận
kết quả quyền, kết quả commit và operation liên quan
~~~

Nhãn action do client gửi, nếu cần ghi, phải được phân biệt với action có thẩm quyền phía server.

Không log toàn bộ token, raw form hoặc dữ liệu nhạy cảm chỉ để biết method. Thông tin hỗ trợ cần có quyền xem phù hợp.

Một log “POST allowed” quá rộng thường không đủ để giải thích vì sao một khoản chi hoặc quyết định duyệt đã được tạo.

## 13. Kiểm thử ma trận theo nhiều chiều

### 13.1. Chuẩn bị fixture có thể phân biệt scope

Tạo các chủ thể riêng:

~~~text
V: chỉ có quyền đọc trong một phạm vi.
E: có quyền sửa/gửi hồ sơ hợp lệ, không có quyền approve/execute.
R: reviewer đủ điều kiện trên hồ sơ được giao.
W: service principal được execute đúng operation.
U: chưa xác thực hợp lệ cho API nghiệp vụ.
~~~

Tạo hồ sơ cùng tenant nhưng ngoài scope, hồ sơ ở tenant khác, bản DRAFT, SUBMITTED và APPROVED. Reviewer dùng cho test approve thành công không phải người lập/sửa bị chính sách cấm.

Không chỉ dùng một tài khoản admin và một đối tượng sở hữu hoàn toàn; fixture đó ít phát hiện được lỗi ô quyền hoặc scope.

### 13.2. Ma trận tình huống lạm dụng

| Tình huống | Điều phải kiểm chứng |
|---|---|
| V GET/HEAD đối tượng được phép | Đúng read scope; HEAD không có body; không có hiệu ứng ghi nghiệp vụ |
| U GET và HEAD tài nguyên riêng tư | Không có đường HEAD mở hơn GET |
| V gửi POST approve | Không tạo decision hoặc đổi trạng thái |
| E gửi PATCH trạng thái APPROVED | Không biến quyền edit thành approve |
| E gọi POST execute | Không tạo operation/job thực thi chỉ nhờ quyền request |
| R gọi PATCH nội dung khi không có quyền edit | Không được sửa nội dung cần duyệt |
| W execute sai tenant/operation | Không thực hiện dù có service credential |
| Đổi GET thành POST trên route không hỗ trợ | Không fallback sang handler ghi |
| Đổi POST approve thành PUT/PATCH/DELETE | Không vào action khác để vượt quyền |
| GET/HEAD kèm action=approve hoặc delete | Không tạo command ghi |
| Body khai action=READ nhưng target là handler approve | Policy dùng action thực tế |
| OPTIONS/preflight kèm dữ liệu command | Không đổi trạng thái hoặc enqueue công việc |
| Preflight thành công nhưng caller thiếu quyền approve | Actual request vẫn bị chặn |
| Method override không được hỗ trợ | Không làm thay effective method theo ý caller |
| Override được hỗ trợ, effective DELETE nhưng caller thiếu DELETE | Đánh giá đúng quyền DELETE, không chỉ quyền wire POST |
| Hai nguồn override mâu thuẫn | Xử lý theo hợp đồng, không có hai cách hiểu giữa các lớp |
| Framework tự hỗ trợ HEAD từ GET | Vẫn có read policy và không thừa hưởng command ghi |
| Route alias/legacy trỏ cùng action | Cùng quyền, state và invariants được áp dụng |
| Path/query/body nêu các target khác nhau | Không authorize một đối tượng rồi thực hiện trên đối tượng khác |
| PUT replace chứa owner/approval/tenant | Không ghi field ngoài action |
| PATCH chứa path/nested field bị cấm | Không nhảy workflow hoặc thay quan hệ quyền |
| Lặp DELETE | Không tạo lại hiệu ứng tài chính/event trái hợp đồng |
| Retry POST cùng command | Không thêm decision/operation do mất response |
| Cùng key nhưng action hoặc target khác | Không chia sẻ receipt như cùng ý định |
| Approve và reject đồng thời | Chỉ có thứ tự hợp lệ hoặc xung đột |
| Lỗi sau mutation nhưng trước commit | Không trả lỗi trong khi hiệu ứng bắt buộc đã commit riêng lẻ |

Các route/method thực sự không được hỗ trợ cần được kiểm tra là không tạo hiệu ứng, nhưng không nên biến một status code duy nhất thành tiêu chí duy nhất của bảo mật.

### 13.3. Kiểm thử method variation trên cùng đối tượng

Với một hồ sơ SUBMITTED và actor E không có REQUEST_APPROVE:

~~~text
POST /purchase-requests/{id}/approve
PUT /purchase-requests/{id}/approve
PATCH /purchase-requests/{id}/approve
DELETE /purchase-requests/{id}/approve
GET /purchase-requests/{id}/approve
HEAD /purchase-requests/{id}/approve
~~~

Không tổ hợp nào được duyệt hồ sơ cho E.

Sau đó dùng R đủ thẩm quyền với POST chuẩn để xác nhận đường hợp lệ vẫn hoạt động. Một hệ thống từ chối mọi request không phải triển khai đúng ma trận nghiệp vụ.

Chạy các trường hợp quan trọng với object ngoài scope và tenant khác để tránh chỉ kiểm tra quyền action thô.

### 13.4. Quan sát trạng thái đã commit

Sau request bị chặn, đọc lại bằng transaction mới:

~~~text
state/version giữ đúng trạng thái trước lần thử
không có approval/rejection decision mới của lần bị chặn
không có reservation hoặc operation trái phép
không có outbox/job thực hiện action bị chặn
không có field protected bị thay qua PUT/PATCH
không có dữ liệu ngoài quyền trong response/header nhạy cảm
~~~

Security event về lần thử có thể được ghi. Nó khác với audit thành công của hành động.

Một HEAD không có body vẫn phải được kiểm tra phần metadata được phép tiết lộ. Một 405/403 không đủ nếu trước đó đã phát message.

### 13.5. Kiểm thử override qua pipeline thật

Unit test policy với effective method đúng chưa phát hiện middleware phía sau đổi method lần nữa.

Cần gửi request qua các lớp thực tế liên quan và đối chiếu:

~~~text
wire method
override được chấp nhận hay bị từ chối
effective method dùng để match route
method/action mà policy đánh giá
handler/action thực sự đã chạy
~~~

Các giá trị phải nhất quán theo hợp đồng. Không được có log “POST allowed” rồi một handler DELETE tạo hiệu ứng mà không có quyết định quyền tương ứng.

Nếu ứng dụng chỉ được gọi qua gateway, kiểm thử cả việc không thể tự giả ngữ cảnh tin cậy khi đi đường khác.

### 13.6. Kiểm thử approve và reject cạnh tranh

Dùng hai transaction/kết nối độc lập trên cùng request SUBMITTED và version ban đầu.

Cho một reviewer hợp lệ approve trong transaction A và một reviewer hợp lệ reject trong transaction B. Điều phối để chúng cạnh tranh tại điểm kiểm tra/ghi.

Đọc lại và xác nhận:

- Chỉ kết quả phù hợp với state machine được chấp nhận.
- Command thua không ghi decision thành công trái trạng thái.
- Version, trạng thái, audit và outbox nhất quán.
- Không có nhánh worker mở thực thi từ một kết quả đã rollback.

Không chỉ mock state=SUBMITTED cho cả hai hoặc gửi nối tiếp rồi kết luận concurrency an toàn.

## 14. Tình huống thực hành: ma trận ở gateway chỉ nhìn POST

Một hệ thống có quy tắc gateway:

~~~text
GET: tài khoản đã đăng nhập được đọc.
POST: nhân viên nghiệp vụ được ghi.
~~~

Application lại có:

~~~text
POST tạo bản nháp.
POST submit.
POST approve.
POST execute.
Một cơ chế POST override thành DELETE.
~~~

Nhân viên chỉ cần tạo bản nháp có thể bị gateway xem là đã đủ quyền cho mọi POST. Nếu handler tin cờ “đã authorize” chung, họ có thể chạm approve/execute hoặc handler DELETE sau override.

Vấn đề gồm:

1. Ma trận quá thô, không có route/action.
2. Không giữ scope và điều kiện theo đối tượng.
3. Gateway và application có thể nhìn method khác nhau.
4. Domain không có điểm kiểm tra action cuối.
5. Field/state có thể còn được cập nhật qua endpoint tổng quát.

Cách thiết kế phù hợp:

~~~text
Route + effective method → action xác định ở server.
Action + actor + resource + facts → quyết định quyền.
Quyền + state/version/invariants → hiệu ứng có kiểm soát.
~~~

Gateway vẫn có ích, nhưng quyền tạo bản nháp không trở thành quyền chi trả. Override hoặc alias cũng không thay đổi ngữ nghĩa quyền của hành động thực tế.

### 14.1. Token hợp lệ không sửa được ma trận quá rộng

Một token được xác thực đúng chỉ cung cấp danh tính/claims theo hợp đồng. Nó không làm một dòng “POST được ghi” trở nên đủ chi tiết cho mọi workflow.

Role trong token còn phải được ràng buộc đúng tenant, action, scope và hiệu lực. Field role hoặc action trong body không được tự chọn một policy thuận lợi hơn.

## 15. Giữ ma trận và triển khai không lệch nhau

Có thể dùng metadata endpoint để tạo tài liệu hoặc kiểm tra độ bao phủ. Cần phát hiện những route:

- Chưa có policy.
- Có method tự động nhưng chưa có cách kiểm soát tương ứng.
- Dùng wildcard quá rộng.
- Là alias/legacy nhưng không trỏ qua lớp quyền nghiệp vụ chung.
- Nhận field/command rộng hơn dòng ma trận mô tả.
- Có override hoặc dispatcher mà tài liệu không phản ánh.

Test sinh từ cấu hình giúp kiểm tra tính nhất quán, nhưng không tự chứng minh cấu hình đúng nghiệp vụ. Nếu expected result chỉ đọc lại chính policy sai, test vẫn có thể qua.

Giữ thêm những ca độc lập như “editor không approve”, “reviewer không execute”, “HEAD không lộ tài nguyên ngoài scope” và “không có GET ghi” để bảo vệ ý định nghiệp vụ.

Khi thêm một endpoint hoặc method mới, cần xác định action, input và điều kiện trước khi mở cho caller. Không fallback quyền từ method/route gần giống.

## 16. Khung đặc tả một dòng method authorization matrix

~~~text
Route template và routeId:
Method trên đường truyền được nhận:
Cách xác định effective method:
Business action và handler tương ứng:

Authentication/CSRF/CORS contract liên quan:
Chủ thể/capability được xét:
Tenant và object/field scope:
Trạng thái, version và facts cần thiết:
Payload/patch operation được phép:
Hiệu ứng được tạo và hiệu ứng bị cấm:

Quy tắc replay/idempotency:
Concurrency và ranh giới transaction:
Alias/legacy/dispatcher/override liên quan:
Response, metadata và mức tiết lộ:
Audit và ca kiểm thử positive/negative:
~~~

## 17. Câu hỏi tự kiểm tra

1. Vì sao một dòng “POST = write” không đủ cho workflow có submit, approve và execute?
2. Route hỗ trợ method khác gì caller có quyền thực hiện action?
3. HEAD có thể làm lộ dữ liệu gì dù không có response body?
4. Allow, CORS allow-methods và allowedActions khác nhau thế nào?
5. Lớp nào đang quyết định effective method, và policy có dùng cùng giá trị với router không?
6. PATCH/PUT có field nào có thể thay cho một command approve hoặc chuyển quyền không?
7. Nếu gọi application service không qua HTTP, action còn được kiểm tra ở đâu?
8. Các retry có thể giữ trạng thái resource nhưng vẫn lặp event/hiệu ứng nào?
9. Test nào chứng minh một request bị từ chối không tạo job hoặc thay đổi trước khi trả lỗi?

Một ma trận có thể thực thi phải giữ nguyên quan hệ giữa **method hiệu lực, route thực tế, action nghiệp vụ và quyền trên dữ liệu hiện tại**. Các alias, metadata request, override và lần gọi lại đều phải tôn trọng cùng ranh giới đó.
