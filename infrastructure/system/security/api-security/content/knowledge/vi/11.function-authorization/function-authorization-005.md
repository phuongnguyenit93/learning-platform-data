# Kiểm tra cả horizontal và vertical escalation

Function authorization quyết định principal có được gọi một chức năng hoặc thực hiện một action của API hay không. Ví dụ, người dùng thông thường có thể xem đơn hàng, nhân viên hỗ trợ có thể chuyển ticket, còn quản lý tài chính có thể duyệt khoản chi. Việc người gọi đã đăng nhập không đồng nghĩa họ được phép gọi mọi endpoint.

Khi kiểm tra function authorization, cần tìm cả hai hướng leo thang quyền:

- **Horizontal privilege escalation:** một principal sử dụng chức năng hoặc phạm vi thao tác dành cho người dùng cùng cấp để thực hiện hành động trên tài nguyên, dữ liệu hoặc phạm vi thuộc về người khác mà họ không được cấp quyền.
- **Vertical privilege escalation:** một principal có quyền thấp gọi được chức năng dành cho role hoặc cấp quyền cao hơn, chẳng hạn người dùng thông thường gọi endpoint quản trị, duyệt giao dịch hoặc thay đổi phân quyền.

Hai loại lỗi có thể cùng xuất hiện trong một endpoint. Ví dụ, endpoint refund có thể chỉ được gọi bởi nhân viên tài chính, nhưng nhân viên đó vẫn không được hoàn tiền cho mọi merchant hoặc mọi payment. Function authorization phải kiểm tra quyền gọi action; object authorization phải kiểm tra quyền trên object cụ thể và điều kiện nghiệp vụ.

## 1. Phân biệt function authorization và object authorization

Hai lớp kiểm soát trả lời hai câu hỏi khác nhau:

| Lớp kiểm soát | Câu hỏi | Ví dụ |
|---|---|---|
| Function authorization | Principal có được gọi chức năng này không? | Chỉ người có permission ORDER_CANCEL mới gọi được thao tác hủy đơn |
| Object authorization | Principal có được thực hiện chức năng đó trên object này không? | Nhân viên chỉ hủy đơn thuộc merchant hoặc nhóm được giao |
| Field authorization | Principal có được xem hoặc thay đổi field này không? | Nhân viên hỗ trợ không được thay đổi refundAmount |
| Workflow/state authorization | Object đang ở trạng thái cho phép action không? | Chỉ hoàn tiền khi payment đã được capture và chưa refund |

Chỉ kiểm tra role ở gateway hoặc controller không đủ để bảo vệ dữ liệu theo từng object. Ngược lại, chỉ lọc object theo owner cũng không đủ nếu mọi người đều có thể gọi endpoint quản trị hoặc action nhạy cảm.

### 1.1. Ví dụ hai hướng leo thang quyền

Giả sử hệ thống quản lý đơn hàng có ba nhóm:

- Customer: xem và hủy đơn của chính mình khi đơn còn ở trạng thái cho phép.
- Support: xem đơn được phân công, cập nhật thông tin hỗ trợ và chuyển ticket.
- Finance: xem giao dịch thuộc phạm vi phụ trách và thực hiện refund theo hạn mức.

**Horizontal escalation:** Customer A đăng nhập hợp lệ, gọi GET /orders/{orderId} hoặc POST /orders/{orderId}/cancel với ID của Customer B. Hai người có cùng role, nhưng A không có quyền trên object của B. Một trường hợp khác là nhân viên Support A dùng chức năng chuyển ticket để thay đổi ticket của nhóm Support B dù không có assignment hoặc quyền chia sẻ.

**Vertical escalation:** Customer gọi POST /payments/{paymentId}/refund, GET /admin/users hoặc PATCH /users/{id}/roles dù các chức năng này chỉ dành cho Finance hoặc Administrator. Kẻ gọi có thể tự thêm role vào request, sửa claim phía client hoặc thử một HTTP method khác để vượt qua kiểm tra.

Horizontal escalation thường liên quan trực tiếp đến object scope và quan hệ giữa các principal. Vertical escalation thường liên quan đến quyền chức năng, role hoặc permission. Khi test API, cần kiểm tra cả route/action và object thay vì chỉ phân loại lỗi theo một lớp.

## 2. Xác định đầy đủ bề mặt chức năng

Trước khi viết test, cần lập danh sách chức năng mà API thực sự cung cấp. Không chỉ dựa vào menu giao diện hoặc tài liệu hướng dẫn người dùng, vì endpoint có thể tồn tại mà không được hiển thị trong UI.

Hãy thu thập các điểm vào:

- HTTP method và path của từng endpoint, bao gồm GET, POST, PUT, PATCH và DELETE.
- Endpoint quản trị, nội bộ, debug, export, import, bulk operation và chức năng hỗ trợ.
- Các phiên bản API đang được duy trì, ví dụ /v1 và /v2.
- GraphQL query, mutation, resolver và batch operation nếu hệ thống dùng GraphQL.
- WebSocket message, callback hoặc webhook có thể kích hoạt hành động.
- Job, message consumer và tác vụ bất đồng bộ có thể thực hiện thay đổi thay mặt người dùng.

Một chức năng có thể được truy cập qua nhiều route hoặc nhiều phương thức. Ví dụ DELETE /users/{id} bị bảo vệ nhưng một route POST /users/{id}/delete cũ lại thiếu kiểm tra. Việc ẩn endpoint khỏi OpenAPI hoặc UI không loại bỏ endpoint khỏi bề mặt tấn công.

### 2.1. Lập ma trận role-function

Ma trận cần thể hiện rõ principal nào được gọi action nào. Ví dụ:

| Chức năng | Anonymous | Customer | Support | Finance | Administrator |
|---|---:|---:|---:|---:|---:|
| Đọc đơn hàng | Từ chối | Có, theo object | Có, theo assignment | Theo phạm vi | Theo policy |
| Hủy đơn hàng | Từ chối | Có, theo điều kiện | Theo quyền được cấp | Từ chối mặc định | Theo policy |
| Chuyển ticket | Từ chối | Từ chối | Có, theo phạm vi | Từ chối | Theo policy |
| Hoàn tiền | Từ chối | Từ chối | Từ chối mặc định | Có, theo hạn mức và payment | Theo policy riêng |
| Thay đổi role người dùng | Từ chối | Từ chối | Từ chối | Từ chối | Có, theo quy trình quản trị |
| Xem audit log | Từ chối | Từ chối | Chỉ phần được phép | Theo phạm vi | Có, theo policy |

Các ô “theo policy” phải được cụ thể hóa bằng điều kiện có thể kiểm thử, chẳng hạn tenant, assignment, hạn mức, trạng thái hoặc phạm vi tổ chức. Không để ma trận chỉ là danh sách role chung chung.

### 2.2. Mặc định từ chối

Mỗi endpoint/action cần có chính sách cho phép rõ ràng. Nếu chưa có rule hoặc không xác định được permission, hệ thống nên từ chối. Cách này tránh việc endpoint mới được thêm vào tự động mở cho mọi người dùng đã đăng nhập.

Khi thêm chức năng, reviewer cần xác nhận:

- Permission nào bảo vệ chức năng?
- Principal nào được cấp permission đó và qua quy trình nào?
- Object scope và điều kiện nghiệp vụ nào còn phải kiểm tra?
- Endpoint có alias, method hoặc phiên bản khác không?
- Test âm nào chứng minh principal không đủ quyền bị từ chối?

## 3. Kiểm tra horizontal privilege escalation

Horizontal escalation xảy ra khi một principal sử dụng quyền ở cùng cấp để truy cập chức năng hoặc dữ liệu thuộc phạm vi của principal khác. Người gọi có thể có role hợp lệ và được phép gọi cùng endpoint, nhưng không có quan hệ hoặc phạm vi trên object mục tiêu.

### 3.1. Kiểm tra với hai principal cùng role

Tạo ít nhất hai tài khoản độc lập có cùng role và dữ liệu thuộc quyền sở hữu khác nhau:

- User A sở hữu object A.
- User B sở hữu object B.
- Cả hai có cùng permission chức năng, ví dụ ORDER_READ hoặc ORDER_CANCEL.

Test cần xác minh:

1. A gọi chức năng trên object A: được phép nếu trạng thái hợp lệ.
2. A gọi cùng chức năng trên object B: bị từ chối nếu không có quan hệ được cấp.
3. B gọi chức năng trên object B: được phép theo cùng policy.
4. A không thể đổi ownerId, tenantId hoặc ID lồng nhau để chuyển object vào phạm vi của mình.

Ví dụ test này quan trọng vì nếu chỉ test Customer không gọi được endpoint Finance, nhóm có thể bỏ sót việc Customer A đọc dữ liệu Customer B.

### 3.2. Kiểm tra tenant và phạm vi tổ chức

Với hệ thống multi-tenant, cần tạo hai tenant độc lập. Một người dùng thuộc tenant A không được truy cập dữ liệu tenant B chỉ bằng cách thay ID hoặc gửi tenant ID khác trong request.

Phải kiểm tra cả:

- Object chính và object lồng nhau.
- Parent-child relationship, ví dụ project và member, order và payment.
- Danh sách ID trong batch.
- Query filter, search, count, export và báo cáo.
- File, signed URL, cache và dữ liệu dẫn xuất.

Không coi việc user thuộc cùng tenant là quyền mặc định với mọi object. Một ticket có thể chỉ dành cho nhóm được phân công; một tài liệu có thể chỉ chia sẻ cho một số thành viên.

### 3.3. Kiểm tra các chức năng cùng cấp nhưng khác assignment

Trong nhiều hệ thống, hai nhân viên có cùng role nhưng chỉ được xử lý các hồ sơ được giao. Hãy kiểm tra:

- Nhân viên A xem hoặc cập nhật ticket được giao cho A.
- Nhân viên A truy cập ticket được giao cho B.
- Assignment bị thu hồi nhưng A vẫn sử dụng session hoặc token cũ.
- Ticket được chuyển nhóm trong lúc A đang thao tác.
- Batch action chứa cả ticket được giao và ticket ngoài phạm vi.

Policy cần dựa trên quan hệ assignment hiện tại hoặc snapshot có thời hạn theo thiết kế. Nếu quyền bị thu hồi, hệ thống phải áp dụng thời gian hiệu lực và cơ chế cập nhật quyền nhất quán.

### 3.4. Kiểm tra dữ liệu trả về và side channel

Horizontal escalation không chỉ là đọc được nội dung object. Endpoint có thể làm lộ thông tin qua:

- Tổng số bản ghi hoặc total count trong kết quả tìm kiếm.
- Khác biệt response giữa object tồn tại và không tồn tại.
- Tên file, thumbnail, URL download hoặc metadata.
- Thông báo lỗi tiết lộ owner, tenant hoặc trạng thái object.
- Cache dùng chung giữa các principal.

Áp dụng cùng phạm vi authorization cho response, metadata và dữ liệu dẫn xuất. Nếu dùng 404 để che giấu object ngoài phạm vi, giữ hành vi nhất quán và xem xét các khác biệt thời gian phản hồi hoặc kích thước response.

## 4. Kiểm tra vertical privilege escalation

Vertical escalation xảy ra khi principal có quyền thấp gọi được chức năng dành cho quyền cao hơn. Các mục tiêu thường gặp gồm endpoint quản trị, thay đổi role, xem audit log, export dữ liệu hàng loạt, cấu hình hệ thống, duyệt giao dịch và thao tác tài chính.

### 4.1. Kiểm tra endpoint dành cho role cao

Với từng endpoint nhạy cảm, tạo principal ở các cấp quyền thấp hơn và gọi trực tiếp endpoint. Ví dụ:

| Endpoint/action | Principal cần thử | Kỳ vọng |
|---|---|---|
| GET /admin/users | Customer, Support | Từ chối |
| PATCH /users/{id}/roles | Customer, Support, Finance | Từ chối nếu không có quyền quản trị role |
| POST /payments/{id}/refund | Customer, Support | Từ chối |
| POST /expenses/{id}/approve | Người tạo khoản chi hoặc nhân viên không có quyền duyệt | Từ chối |
| GET /audit-logs | Principal không có quyền audit | Từ chối |

Test phải gọi trực tiếp bằng HTTP client hoặc công cụ kiểm thử API. Việc nút quản trị không xuất hiện trên giao diện người dùng không chứng minh server đã chặn chức năng.

### 4.2. Kiểm tra method và route thay thế

Một endpoint có thể được bảo vệ theo method nhưng thiếu kiểm tra ở method khác. Cần thử các phương thức mà server hỗ trợ và xác minh method không được công bố sẽ bị từ chối:

- GET, POST, PUT, PATCH và DELETE.
- HEAD hoặc OPTIONS nếu framework và gateway xử lý riêng.
- Route alias, trailing slash, path encoding và route cũ.
- API version cũ còn hoạt động.
- Endpoint nội bộ có thể truy cập qua ingress hoặc network path khác.

Không phải mọi method đều phải trả cùng status code. Điều cần bảo đảm là chỉ method được thiết kế mới có thể thực hiện action, và mọi method có tác động đều đi qua cùng policy cần thiết.

### 4.3. Kiểm tra quyền được gửi từ client

Không tin role hoặc permission trong request body, query parameter hay header tùy ý. Các trường như role, isAdmin, permissions, approvedBy hoặc tenantId không được phép làm thay đổi security context.

Với JWT, server phải xác minh chữ ký, issuer, audience, thời hạn và các claim theo cấu hình. Client không thể tự sửa claim rồi yêu cầu server tin giá trị mới. Khi role hoặc permission thay đổi, cần có chiến lược thu hồi hoặc hết hạn quyền cũ phù hợp với yêu cầu bảo mật; token còn hiệu lực có thể tiếp tục mang claim cũ cho đến khi được kiểm tra lại.

Kiểm tra thêm:

- User thường không thể tự gán role Administrator.
- Support không thể thêm permission Finance vào profile của mình.
- Request không thể thay principal bằng userId khác.
- Claim hoặc group không rõ nguồn gốc không được dùng để cấp quyền.
- Session, refresh token và access token cũ tuân theo chính sách thu hồi hoặc thời hạn.

### 4.4. Kiểm tra role hierarchy và permission inheritance

Role hierarchy giúp kế thừa quyền nhưng có thể vô tình mở rộng phạm vi. Ví dụ role ADMIN kế thừa toàn bộ permission của SUPPORT, FINANCE và AUDITOR có thể tạo ra quyền vượt quá nhiệm vụ cần thiết.

Hãy kiểm tra:

- Role cha thực sự cần kế thừa permission nào?
- Role có quyền quản trị người dùng có mặc nhiên được quyền xem dữ liệu tài chính không?
- Quyền của service account hoặc support tool có bị dùng nhầm cho người dùng cuối không?
- Một role có thể được gán qua nhiều group hoặc tổ chức khác nhau không?
- Quyền được cấp tạm thời có hết hạn và được audit không?

Nên áp dụng least privilege: mỗi role chỉ nhận các permission cần cho nhiệm vụ. Quyền quản trị hệ thống, quản trị nghiệp vụ, kiểm toán và hỗ trợ khách hàng nên được tách theo trách nhiệm nếu rủi ro và quy trình yêu cầu.

## 5. Kiểm tra workflow và action nhạy cảm

Một người có thể được phép gọi endpoint nhưng không được thực hiện action ở mọi trạng thái. Ví dụ nhân viên Finance có permission refund nhưng chỉ được hoàn tiền khi payment đã capture, chưa refund và còn trong giới hạn được phê duyệt.

Các action cần test riêng:

- Approve và reject.
- Cancel, refund và reverse.
- Publish, unpublish và archive.
- Assign, reassign và transfer ownership.
- Grant, revoke và thay đổi role/permission.
- Export, bulk update và thao tác dữ liệu diện rộng.

Không nên cho client cập nhật trực tiếp một field trạng thái nhạy cảm để bỏ qua workflow. Hãy thiết kế action rõ ràng và kiểm tra principal, function permission, object permission, state transition, hạn mức và separation of duties.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('PAYMENT_REFUND')")
@Transactional
public void refund(String paymentId, Caller caller) {
    Payment payment = paymentRepository
        .findByIdAndTenantIdForUpdate(paymentId, caller.tenantId())
        .orElseThrow(NotFoundException::new);

    authorization.requireCanRefund(caller, payment);
    payment.requireCapturedAndNotRefunded();
    refundPolicy.requireWithinLimit(caller, payment.amount());

    payment.refund(clock.instant(), caller.userId());
    audit.recordRefund(payment, caller);
}
~~~

@PreAuthorize minh họa kiểm tra function permission. requireCanRefund kiểm tra quyền trên payment cụ thể; các điều kiện trạng thái và hạn mức kiểm soát nghiệp vụ. Cần cấu hình method security trong ứng dụng và bảo đảm Caller lấy từ security context đã xác thực.

## 6. Kiểm tra các bề mặt không phải REST controller

Function authorization có thể bị bỏ sót khi cùng nghiệp vụ được gọi qua một giao diện khác:

- **GraphQL:** query, mutation, nested resolver và batch loader phải kiểm tra permission; bảo vệ mutation không đồng nghĩa đã bảo vệ resolver đọc.
- **WebSocket:** kiểm tra quyền khi kết nối và ở từng message/action; không coi xác thực lúc handshake là quyền vĩnh viễn cho mọi message.
- **Webhook/callback:** xác minh nguồn gọi, chữ ký hoặc cơ chế xác thực phù hợp; giới hạn action mà callback có thể kích hoạt.
- **Message consumer:** xác định service principal, nguồn message và quyền nghiệp vụ; không tin message có field requestedBy hoặc role do producer không tin cậy cung cấp.
- **Scheduled job:** dùng service identity có permission tối thiểu và phạm vi dữ liệu được giới hạn.
- **Internal API:** mạng nội bộ không thay thế xác thực và authorization. Một service bị xâm nhập không nên có quyền gọi mọi chức năng trong hệ thống.

Nếu một action được thực hiện bởi cả HTTP request và message consumer, policy nghiệp vụ nên được đặt tại service/domain layer dùng chung hoặc được thực thi tương đương ở cả hai đường gọi.

## 7. Triển khai function authorization theo permission rõ ràng

Nên đặt tên permission theo action và phạm vi nghiệp vụ thay vì chỉ dựa vào tên role. Ví dụ:

- ORDER_READ
- ORDER_CANCEL
- TICKET_ASSIGN
- PAYMENT_REFUND
- EXPENSE_APPROVE
- USER_ROLE_MANAGE
- AUDIT_LOG_READ

Permission cần được gắn với endpoint/action cụ thể. Một permission ORDER_WRITE quá rộng có thể cho phép người dùng thực hiện nhiều thao tác khác nhau như sửa địa chỉ, đổi owner, hủy đơn hoặc hoàn tiền.

Ví dụ mapping ở Spring Security:

~~~java
@PreAuthorize("hasAuthority('TICKET_ASSIGN')")
@PostMapping("/tickets/{ticketId}/assign")
public TicketResponse assign(
        @PathVariable String ticketId,
        @Valid @RequestBody AssignTicketRequest request,
        Caller caller) {
    return ticketService.assign(ticketId, request, caller);
}
~~~

Ví dụ này chỉ minh họa annotation và method mapping; cách truyền Caller cần được triển khai bằng security principal hoặc argument resolver phù hợp của ứng dụng. Service vẫn phải xác minh object scope, tenant, assignment và trạng thái.

### 7.1. Tránh kiểm tra quyền rải rác và không nhất quán

Nếu mỗi controller tự viết điều kiện role khác nhau, một endpoint mới dễ bị quên. Nên dùng cơ chế policy hoặc permission mapping tập trung, đồng thời giữ object-specific rule tại service/domain.

Một cấu trúc dễ review:

- Khai báo permission cần cho từng function/action.
- Xác định principal và claim đáng tin cậy ở authentication layer.
- Dùng policy service cho các điều kiện theo object hoặc context.
- Dùng default deny cho endpoint/action chưa được khai báo.
- Có test xác nhận mapping endpoint-permission và test âm cho principal không đủ quyền.

Không nên tạo một annotation hoặc helper có tên isAdmin() rồi dùng nó cho mọi chức năng nhạy cảm. Những quyền như xem audit, quản lý role, refund và cấu hình hệ thống có thể cần các permission khác nhau.

## 8. Kiểm thử horizontal và vertical escalation

Một bộ kiểm thử tốt cần kết hợp ma trận principal, function, object và trạng thái. Test phải chứng minh cả đường được phép lẫn đường bị từ chối.

### 8.1. Chuẩn bị principal và dữ liệu

Tạo tối thiểu:

- Anonymous: không có credential.
- Customer A và Customer B: cùng role, khác owner.
- Customer thuộc tenant khác.
- Support A và Support B: cùng role, khác assignment.
- Finance: có quyền tài chính trong phạm vi xác định.
- Administrator: có quyền quản trị được cấp.
- Service account: chỉ có các permission cần cho tác vụ tự động.

Dữ liệu nên gồm object thuộc từng principal, object cùng tenant nhưng không chia sẻ, object thuộc tenant khác và object ở nhiều trạng thái nghiệp vụ.

### 8.2. Ma trận kiểm thử

| Test | Principal | Function | Object/context | Kỳ vọng |
|---|---|---|---|---|
| F01 | Anonymous | Đọc đơn hàng | Bất kỳ | Từ chối |
| F02 | Customer A | Đọc đơn hàng | Đơn của A | Cho phép theo policy |
| F03 | Customer A | Đọc đơn hàng | Đơn của B | Từ chối (horizontal) |
| F04 | Customer A | Hủy đơn | Đơn của A đang cho phép hủy | Cho phép |
| F05 | Customer A | Hủy đơn | Đơn của B | Từ chối (horizontal) |
| F06 | Customer A | Hoàn tiền | Payment hợp lệ | Từ chối (vertical) |
| F07 | Support A | Chuyển ticket | Ticket được giao cho A | Cho phép theo policy |
| F08 | Support A | Chuyển ticket | Ticket được giao cho B | Từ chối (horizontal) |
| F09 | Support A | Quản lý role | User bất kỳ | Từ chối (vertical) |
| F10 | Finance | Hoàn tiền | Payment ngoài tenant | Từ chối (object scope) |
| F11 | Finance | Hoàn tiền | Payment chưa capture | Từ chối (state) |
| F12 | Administrator | Quản lý role | Theo quy trình quản trị | Cho phép và audit |

Ma trận cần được mở rộng theo permission và trạng thái thực tế của sản phẩm. Không giả định Administrator luôn được phép bỏ qua mọi policy hoặc mọi yêu cầu audit.

### 8.3. Kiểm tra endpoint và phương thức thay thế

Với mỗi function nhạy cảm, thử:

1. Endpoint chính với method được công bố.
2. Method khác hoặc route alias nếu server có thể nhận.
3. API version cũ.
4. Batch endpoint hoặc nested route thực hiện cùng action.
5. GraphQL mutation hoặc message path tương đương nếu có.
6. Request chứa role, permission, owner hoặc tenant do client tự gửi.

Kết quả cần chứng minh không có đường vào thay thế bỏ qua cùng permission hoặc policy.

### 8.4. Ví dụ test vertical escalation

~~~java
@Test
@WithMockUser(authorities = "CUSTOMER")
void customerCannotCallRefundFunction() throws Exception {
    mockMvc.perform(post("/payments/payment-123/refund"))
        .andExpect(status().isForbidden());
}
~~~

Test trên minh họa một principal Customer bị từ chối ở function permission. Cần có thêm integration test với payment thuộc nhiều tenant và trạng thái khác nhau để kiểm tra object authorization và workflow. Cấu hình test phải tương ứng với security filter chain thật; mock principal đơn lẻ không chứng minh JWT validation đã hoạt động.

### 8.5. Ví dụ test horizontal escalation

~~~java
@Test
void customerCannotCancelAnotherCustomersOrder() {
    Caller callerA = caller("customer-a", "tenant-1");
    Order orderB = orderOwnedBy("customer-b", "tenant-1");

    when(orderRepository.findByIdAndTenantId(orderB.id(), "tenant-1"))
        .thenReturn(Optional.of(orderB));

    assertThrows(
        AccessDeniedException.class,
        () -> orderService.cancel(orderB.id(), callerA)
    );

    verify(orderRepository, never()).save(any());
}
~~~

Test này chứng minh hai principal cùng tenant và cùng role không tự động chia sẻ quyền trên object. Nếu policy dùng repository query đã lọc owner, test có thể xác minh truy vấn trả về kết quả rỗng thay vì gọi policy service; điều quan trọng là không có thay đổi trái phép.

### 8.6. Test hồi quy khi permission thay đổi

Khi thêm role hoặc permission mới, chạy lại ma trận endpoint-function để phát hiện quyền vô tình được kế thừa. Khi xóa hoặc thu hồi permission, test token/session cũ và các đường gọi bất đồng bộ theo chính sách hiệu lực. Những test này giúp phát hiện regression do thay đổi role hierarchy, cấu hình security hoặc route mới.

## 9. Phản hồi lỗi, audit và giám sát

Response khi từ chối cần nhất quán và không tiết lộ chi tiết về chức năng nội bộ:

| Tình huống | HTTP status thường dùng | Lưu ý |
|---|---:|---|
| Chưa xác thực hoặc credential không hợp lệ | 401 Unauthorized | Client cần xác thực hợp lệ |
| Đã xác thực nhưng không có function permission | 403 Forbidden | Không tiết lộ role hoặc permission nội bộ |
| Không có quyền trên object và hệ thống che giấu sự tồn tại | 404 Not Found | Giữ hành vi nhất quán theo policy |
| Request sai cấu trúc hoặc vi phạm contract | 400 Bad Request hoặc 422 theo contract | Không thay thế authorization |

Với action nhạy cảm, audit nên ghi:

- Principal hoặc service identity đã thực hiện.
- Permission/action được yêu cầu.
- Loại object và ID theo chính sách dữ liệu.
- Tenant hoặc phạm vi nghiệp vụ.
- Kết quả cho phép/từ chối, thời điểm và correlation ID.
- Lý do từ chối ở dạng mã nội bộ nếu cần điều tra.

Không ghi access token, secret hoặc toàn bộ payload vào log. Hạn chế quyền truy cập và thời gian lưu audit theo yêu cầu bảo vệ dữ liệu.

Metric hữu ích gồm số lần từ chối theo endpoint, action và nhóm principal; số lần truy cập chéo tenant; các request thử endpoint quản trị bằng role thấp; số lần thay đổi role; và tỷ lệ action nhạy cảm thất bại theo trạng thái. Tránh đưa user ID hoặc object ID tùy ý làm label có cardinality cao.

Một đợt tăng đột biến request bị từ chối trên endpoint quản trị, refund hoặc thay đổi role có thể báo hiệu dò tìm chức năng. Cảnh báo cần có ngữ cảnh về endpoint và principal nhưng không chứa dữ liệu bí mật. Nhóm vận hành cần có quy trình phân biệt hoạt động kiểm thử được ủy quyền, lỗi client và hành vi tấn công.

## 10. Những sai lầm thường gặp

- **Chỉ kiểm tra đăng nhập:** principal hợp lệ vẫn có thể gọi function không được cấp.
- **Chỉ ẩn chức năng ở UI:** endpoint vẫn có thể được gọi trực tiếp.
- **Chỉ test vertical escalation:** bỏ sót user cùng role truy cập dữ liệu của nhau.
- **Chỉ test horizontal escalation ở endpoint chi tiết:** bỏ sót list, search, export, batch và nested route.
- **Dùng một permission quá rộng:** quyền write có thể vô tình bao gồm approve, refund hoặc thay đổi role.
- **Tin role do client gửi:** request body hoặc header tùy ý không phải nguồn cấp quyền.
- **Chỉ bảo vệ một HTTP method:** route hoặc method khác có thể thực hiện cùng action.
- **Bỏ qua API version cũ:** endpoint legacy có thể còn thiếu policy mới.
- **Quên GraphQL và message consumer:** cùng chức năng có thể được gọi qua một đường khác.
- **Cho role Administrator quyền tuyệt đối:** làm mất phân tách nhiệm vụ và khả năng kiểm soát.
- **Không kiểm tra object và state:** function permission đúng nhưng action vẫn tác động lên object ngoài phạm vi hoặc sai trạng thái.
- **Không có test âm:** test chỉ xác nhận người có quyền thành công, không chứng minh người không có quyền bị chặn.
- **Không audit:** khó điều tra ai đã gọi chức năng nhạy cảm và kết quả ra sao.

## 11. Checklist trước khi phát hành

- [ ] Có danh sách endpoint, method, API version và các bề mặt gọi action tương đương.
- [ ] Có ma trận role/permission/function được review bởi chủ sở hữu nghiệp vụ.
- [ ] Endpoint/action chưa được cấp permission rõ ràng mặc định bị từ chối.
- [ ] Horizontal test dùng hai principal cùng role nhưng khác owner, tenant hoặc assignment.
- [ ] Vertical test dùng principal quyền thấp gọi endpoint dành cho quyền cao.
- [ ] Kiểm tra cả path, query, body, nested ID và batch request.
- [ ] Kiểm tra route alias, HTTP method và API version cũ.
- [ ] Role và permission chỉ lấy từ security context hoặc nguồn tin cậy đã xác minh.
- [ ] JWT/session có kiểm tra issuer, audience, expiry và chiến lược thu hồi quyền phù hợp.
- [ ] Role hierarchy và permission inheritance được review theo least privilege.
- [ ] Function permission kết hợp object authorization và state/workflow policy.
- [ ] GraphQL, WebSocket, webhook, job và message consumer có kiểm soát tương ứng nếu được sử dụng.
- [ ] Có test âm và test hồi quy khi thêm, sửa hoặc thu hồi permission.
- [ ] Response lỗi không tiết lộ chức năng nội bộ hoặc thông tin object.
- [ ] Audit và metric ghi nhận action nhạy cảm mà không lưu token hoặc payload nhạy cảm.

Kiểm tra horizontal và vertical escalation giúp xác minh rằng API chỉ cho phép đúng principal gọi đúng chức năng trong đúng phạm vi dữ liệu và trạng thái. Khi ma trận permission được gắn với endpoint thực tế, kết hợp test âm theo nhiều principal và kiểm tra object riêng biệt, nhóm có thể phát hiện sớm các đường leo thang quyền trước khi phát hành.
