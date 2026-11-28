# Resource ownership

## 1. Quyền sở hữu tài nguyên trong yêu cầu phân quyền

**Resource ownership** là quan hệ giữa một tài nguyên và chủ thể được hệ thống xác định là chủ sở hữu theo chính sách của sản phẩm. Quan hệ này thường là một đầu vào quan trọng của quyết định phân quyền: ai được đọc, sửa, chia sẻ, chuyển giao hoặc xóa một tài nguyên cụ thể.

Ví dụ, một ứng dụng tài liệu có thể cho phép người dùng đọc tài liệu mình sở hữu nhưng không đọc tài liệu riêng tư của người khác. Trong khi đó, một hệ thống nghiệp vụ có thể coi tổ chức là chủ sở hữu tài nguyên và một nhân viên chỉ là người phụ trách. Vì vậy, từ “owner” phải được định nghĩa trong miền nghiệp vụ trước khi biến thành một trường dữ liệu hoặc một điều kiện kiểm tra quyền.

Trong bài này, sở hữu là quan hệ phục vụ chính sách truy cập của ứng dụng. Nó không tự đưa ra kết luận về quyền sở hữu pháp lý đối với dữ liệu. Mục tiêu thiết kế là xác định chính xác quan hệ nào được hệ thống công nhận và quan hệ đó cho phép những hành động nào.

Một yêu cầu như “người dùng chỉ được truy cập dữ liệu của mình” chưa đủ để triển khai. Cần trả lời:

- “Của mình” được xác định bằng trường nào hoặc quan hệ nào?
- Người tạo, người được giao việc và chủ sở hữu có phải cùng một người không?
- Chủ sở hữu được làm tất cả hay chỉ một tập hành động?
- Quan hệ sở hữu có bị giới hạn bởi tenant, trạng thái tài nguyên hoặc điều kiện nghiệp vụ không?
- Ai được thiết lập, thay đổi và thu hồi quan hệ đó?
- Thay đổi sở hữu phải có hiệu lực sau bao lâu trên API, cache và tệp đã xuất?

Trong thiết kế yêu cầu bảo mật, các câu trả lời cần trở thành cam kết có thể kiểm chứng, liên kết với rủi ro, thành phần kiến trúc và tiêu chí kiểm thử.

## 2. Phân biệt chủ sở hữu với các quan hệ gần giống

| Quan hệ | Ý nghĩa | Vì sao không tự thay thế ownership |
| --- | --- | --- |
| Người tạo — `created_by` | Chủ thể đã tạo tài nguyên ban đầu. | Sau chuyển giao, người tạo có thể không còn quyền sở hữu. |
| Người cập nhật cuối — `updated_by` | Chủ thể thực hiện thay đổi gần nhất. | Một người được chia sẻ quyền sửa không vì sửa nội dung mà thành chủ sở hữu. |
| Người phụ trách — `assignee` | Người được giao xử lý công việc. | Có thể chỉ được thực hiện một số thao tác trong quy trình. |
| Người được chia sẻ — `grantee` | Chủ thể có một hoặc nhiều quyền được cấp. | Quyền đọc hoặc sửa không mặc nhiên bao gồm chuyển giao hay cấp thêm quyền. |
| Tenant chứa tài nguyên | Phạm vi tổ chức hoặc khách hàng trong hệ thống dùng chung. | Là ranh giới dữ liệu; không tự chứng minh người dùng trong tenant đều có quyền như nhau. |
| Quản trị viên | Chủ thể có một tập quyền quản trị cụ thể. | Quyền quản lý tài khoản hoặc chuyển giao không nhất thiết bao gồm đọc nội dung. |
| Dịch vụ đang lưu hoặc xử lý | Thành phần kỹ thuật có khả năng truy cập dữ liệu. | Khả năng kỹ thuật không biến dịch vụ thành chủ sở hữu nghiệp vụ. |

Một hệ thống có thể kết hợp các quan hệ này, nhưng cần đặt tên và đặc tả riêng. Nếu `created_by` được giữ bất biến để kiểm toán, không nên sửa trường đó khi chuyển chủ sở hữu chỉ để tiếp tục tái sử dụng một câu truy vấn cũ.

### 2.1. Các kiểu sở hữu thường gặp

- **Sở hữu cá nhân:** tài nguyên có một tài khoản sở hữu theo chính sách, chẳng hạn bản nháp tài liệu riêng.
- **Sở hữu bởi nhóm:** tài nguyên gắn với một nhóm; quyền của từng người phụ thuộc tư cách thành viên và vai trò trong nhóm.
- **Sở hữu bởi tổ chức:** tài nguyên thuộc tenant hoặc tổ chức; cá nhân có thể là người quản lý hoặc người phụ trách.
- **Đồng sở hữu:** nhiều chủ thể cùng có quan hệ sở hữu, cần quy tắc về thêm, xóa và xử lý chủ sở hữu cuối cùng.

Không nên mặc định mọi loại đều dùng được cùng điều kiện `resource.ownerId == currentUser.id`. Với tài nguyên của nhóm, việc một người từng tạo nhóm hoặc đang quản trị nhóm chưa đủ để suy ra mọi quyền trên tài nguyên nếu chính sách không quy định.

## 3. Tình huống xuyên suốt và mô hình đe dọa

Giả sử một cổng tài liệu phục vụ nhiều tổ chức. Mỗi tổ chức là một tenant. Một tài liệu riêng tư có đúng một chủ sở hữu cá nhân đang được ghi nhận, có thể có người được chia sẻ quyền và có các phiên bản nội dung đi kèm.

Chính sách minh họa:

1. Người dùng chỉ thực hiện quyền cá nhân khi tài khoản và tư cách thành viên tenant còn hoạt động.
2. Chủ sở hữu có thể đọc, sửa, chia sẻ và đề nghị chuyển giao tài liệu trong cùng tenant, tùy trạng thái tài liệu.
3. Người được chia sẻ quyền sửa không có quyền chuyển giao, xóa hoặc chia sẻ tiếp nếu chưa có quyền riêng.
4. Tài liệu đã khóa lưu trữ không được sửa hoặc xóa chỉ vì người gọi là chủ sở hữu.
5. Quản trị viên có quyền khôi phục quyền quản lý bằng chuyển giao theo quy trình riêng, không mặc nhiên được đọc nội dung.

Đây là giả định thiết kế cho bài học. Các ngưỡng thời gian ở phần sau cũng là ví dụ cần điều chỉnh theo rủi ro và khả năng hệ thống, không phải giá trị chung bắt buộc.

### 3.1. Những kịch bản cần chuyển thành yêu cầu

| Mã rủi ro | Kịch bản | Hậu quả |
| --- | --- | --- |
| R-O01 | Người dùng đổi ID trên URL để mở tài liệu của người khác. | Lộ nội dung hoặc thao tác trái phép trên tài nguyên. |
| R-O02 | Client gửi `owner_user_id` của tài khoản khác khi tạo hoặc sửa. | Giả quan hệ sở hữu hoặc chuyển giao trái phép. |
| R-O03 | Vai trò ở tenant A được dùng với tài nguyên tenant B. | Vượt ranh giới tổ chức. |
| R-O04 | API đọc chi tiết được kiểm tra nhưng tìm kiếm, tệp hoặc job xuất bỏ sót quyền. | Lộ tài nguyên qua một đường truy cập khác. |
| R-O05 | Sau chuyển giao, chủ cũ còn quyền qua cache, chia sẻ hoặc URL tải. | Quyền sở hữu đã đổi nhưng khả năng truy cập không đổi như cam kết. |
| R-O06 | Hai yêu cầu chuyển giao hoặc cập nhật diễn ra đồng thời. | Chuyển nhầm, mất cập nhật hoặc vi phạm quy tắc sở hữu. |
| R-O07 | Chủ sở hữu rời tổ chức hoặc tài khoản bị vô hiệu hóa. | Tài nguyên bị bỏ quản lý hoặc quyền cũ vẫn được sử dụng. |
| R-O08 | Quản trị viên dùng đường phục hồi để vượt chính sách dữ liệu. | Mở rộng đặc quyền mà thiếu phê duyệt và bằng chứng. |

Ẩn nút, dùng UUID khó đoán hoặc mã hóa đường dẫn có thể hỗ trợ một số mục tiêu khác, nhưng không chứng minh người gọi có quyền trên tài nguyên. R-O01 phải được giảm bằng kiểm tra quan hệ và chính sách ở phía thực thi.

## 4. Biểu diễn ownership bằng dữ liệu có thẩm quyền

### 4.1. Mô hình minh họa

```text
Document
  id
  tenant_id
  owner_user_id
  created_by_user_id
  state
  version
  ownership_version

Membership
  tenant_id
  user_id
  status

DocumentGrant
  tenant_id
  document_id
  grantee_user_id
  permission

OwnershipTransfer
  id
  tenant_id
  document_id
  source_owner_id
  target_owner_id
  expected_ownership_version
  status
  expires_at
```

`owner_user_id` là chủ sở hữu hiện tại theo chính sách cá nhân. `created_by_user_id` giữ lịch sử người tạo. `version` giúp phát hiện thay đổi nội dung hoặc trạng thái theo thiết kế; `ownership_version` giúp nhận biết quyết định hoặc đề nghị chuyển giao dựa trên quan hệ sở hữu cũ.

Mô hình này dành cho một chủ sở hữu cá nhân. Nếu cho phép sở hữu bởi nhóm hoặc đồng sở hữu, cần mô hình quan hệ phù hợp, tập loại chủ thể hợp lệ và các bất biến tương ứng; không dùng chuỗi ID đa nghĩa mà thiếu cách phân biệt tài khoản với nhóm.

### 4.2. Bất biến dữ liệu cần nêu rõ

Với tình huống minh họa, yêu cầu có thể quy định:

- Mỗi tài liệu có đúng một giá trị chủ sở hữu được ghi nhận; việc không còn chủ hoạt động phải đi qua trạng thái xử lý đã định nghĩa.
- Chủ mới phải là tài khoản được phép nhận sở hữu và có tư cách thành viên hoạt động trong cùng tenant tại thời điểm chuyển giao được cam kết.
- Bản ghi chia sẻ, phiên bản và tệp con phải gắn đúng tài liệu và tenant, không được tham chiếu chéo tenant ngoài quy trình riêng.
- Quan hệ sở hữu chỉ thay đổi qua thao tác được phân quyền, không qua API sửa nội dung thông thường.
- Trường người tạo và lịch sử chuyển giao không bị viết lại để che nguồn gốc tài nguyên.

Cơ sở dữ liệu có thể hỗ trợ bằng khóa ngoại, khóa duy nhất và giao dịch phù hợp. Chẳng hạn, tham chiếu tổng hợp theo `(tenant_id, document_id)` giúp tránh một bản ghi chia sẻ vô tình gắn sang tài liệu tenant khác. Tuy nhiên, ràng buộc tham chiếu không tự chứng minh người gọi có quyền tạo chia sẻ đó.

Tư cách thành viên có thể thay đổi sau khi tài nguyên được tạo. Vì vậy, chỉ có khóa ngoại tới người dùng không đủ bảo đảm chủ sở hữu đang được phép truy cập. Chính sách đọc và chính sách xử lý tài nguyên khi thành viên rời tổ chức phải được thực thi riêng.

## 5. Thiết lập chủ sở hữu khi tạo tài nguyên

### 5.1. Chủ sở hữu không do client tự xác nhận

Với luồng tạo tài liệu cá nhân, máy chủ phải lấy người sở hữu từ principal đã được xác thực và kiểm tra quyền tạo trong tenant đã chọn. Principal là biểu diễn chủ thể được hệ thống chấp nhận sau khi kiểm tra bằng chứng; một trường `userId` tự gửi trong JSON không có giá trị tương đương.

Ví dụ yêu cầu:

> Khi một người dùng tạo tài liệu cá nhân, backend phải gán `owner_user_id` từ principal và gán tenant từ phạm vi đã được xác minh. API tạo thông thường phải từ chối các trường quản lý quyền như `owner_user_id`, `tenant_id` trong nội dung nếu giao thức của API không cho phép client đặt chúng. Client không được thay đổi chủ sở hữu bằng cách gửi thêm thuộc tính.

Tenant có thể xuất hiện trong đường dẫn hoặc trường chọn phạm vi, nhưng máy chủ vẫn phải kiểm tra tư cách thành viên và quyền tạo. Việc client chọn một tenant là yêu cầu sử dụng phạm vi đó, không phải bằng chứng có quyền trong phạm vi đó.

### 5.2. Tạo thay người khác là hành động riêng

Một số sản phẩm cần chức năng tạo tài liệu thay nhân viên khác. Khi đó, không mở tự do trường chủ sở hữu trong API cá nhân. Cần đặc tả hành động riêng, chẳng hạn `document.create_on_behalf`, với các điều kiện:

1. Chủ thể thực hiện có quyền tạo thay trong phạm vi tenant và loại tài liệu tương ứng.
2. Tài khoản nhận sở hữu là đối tượng hợp lệ, đang thuộc cùng tenant theo chính sách.
3. Người tạo thực tế và người sở hữu được ghi riêng.
4. Không tự sao chép quyền rộng của dịch vụ hoặc quản trị viên thành quyền của người nhận.
5. Có sự kiện kiểm toán về việc tạo thay, nhưng không ghi toàn bộ nội dung nhạy cảm vào log.

Luồng nhập dữ liệu, khôi phục và tác vụ nền cũng cần xác định nguồn của quan hệ sở hữu. Không gán toàn bộ dữ liệu nhập cho tài khoản dịch vụ rồi mặc định rằng sẽ sửa lại sau.

## 6. Dùng ownership trong quyết định phân quyền

### 6.1. Là chủ sở hữu vẫn phải đáp ứng điều kiện khác

Một mô hình quyết định đơn giản cho tài liệu có thể là:

```text
Cho phép hành động khi:
  principal hợp lệ và tài khoản còn được phép hoạt động
  AND thuộc phạm vi tenant đã được xác minh
  AND tài nguyên thuộc đúng tenant
  AND trạng thái tài nguyên cho phép hành động
  AND có ít nhất một quan hệ quyền phù hợp:
      chủ sở hữu được phép thực hiện hành động đó
      OR được chia sẻ đúng quyền
      OR có quyền quản trị cụ thể được chính sách cho phép
```

Các điều kiện tenant và trạng thái không được vô tình đặt trong một nhánh mà vai trò quản trị có thể bỏ qua. Ngoại lệ thật sự, nếu có, phải là quy tắc riêng với phạm vi và bằng chứng được định nghĩa.

Ví dụ, chủ sở hữu tài liệu đã khóa vẫn có thể đọc nhưng không sửa. Người được chia sẻ quyền sửa có thể sửa nội dung nhưng không đổi chủ. Quản trị viên được khôi phục người phụ trách không nhất thiết có quyền tải tệp gốc.

### 6.2. Mã giả cho API đọc tài liệu

```text
principal = authentication.requireValidPrincipal(request.credentials)
tenant = membership.requireActiveMembership(principal, request.tenantId)

document = documents.findWithinTenant(request.documentId, tenant.id)
if document is absent:
    return responseAccordingToDisclosurePolicy()

decision = policy.evaluate(
    subject = principal,
    action = "document.read",
    resource = document,
    context = trustedContext(tenant)
)

if decision is not PERMIT:
    return responseAccordingToDisclosurePolicy()

return permittedDocumentView(principal, document)
```

Trong tình huống này, chính sách kiểm tra quan hệ chủ sở hữu, các chia sẻ hợp lệ và trạng thái. Quyết định không dựa vào `owner_user_id` gửi kèm request. Bộ lọc tenant bảo vệ phạm vi tổ chức nhưng không thay thế quyền trên từng tài liệu bên trong tổ chức đó.

Đối với sửa hoặc xóa, kiểm tra phải gắn với phiên bản trạng thái được tác động. Chẳng hạn, một cập nhật có điều kiện có thể yêu cầu cả ID, tenant, owner và phiên bản mong đợi vẫn phù hợp. Nếu không có bản ghi đáp ứng, không được tự thử lại bằng một cập nhật chỉ dựa trên ID để “sửa lỗi”.

### 6.3. Chủ sở hữu của tài nguyên con

Phiên bản, bình luận, tệp đính kèm và bản xuất có thể được quản lý theo quyền của tài liệu cha hoặc có chính sách riêng. Phải chọn rõ mô hình cho từng loại.

Nếu tệp đính kèm kế thừa quyền từ tài liệu, backend phải xác minh cả quan hệ tệp–tài liệu và quyền trên tài liệu. Một người sở hữu tài liệu A không được gửi `attachmentId` thuộc B vào đường dẫn A để tải tệp. Nếu lưu một bản sao `owner_id` trên tệp, cần cơ chế giữ nhất quán khi chuyển chủ; việc suy ra từ cha có thể giảm một số dữ liệu trùng nhưng vẫn cần kiểm tra quan hệ thực tế.

## 7. Chuyển giao ownership là một quy trình bảo mật

### 7.1. Xác định chính xác điều gì được chuyển

Đổi `owner_user_id` không tự mô tả đầy đủ tác động. Yêu cầu chuyển giao phải chốt:

- Quyền của chủ cũ sau chuyển: bị thu hồi hoàn toàn hay giữ một quyền chia sẻ cụ thể?
- Các chia sẻ hiện có được giữ, hủy hay phải được chủ mới chấp thuận lại?
- Phiên bản, tệp, liên kết tải và bản xuất đang tồn tại có đi theo tài liệu không?
- Tài nguyên đang khóa, chờ duyệt hoặc có thao tác đang chạy có được chuyển không?
- Chủ mới có cần chấp nhận và có thể từ chối không?
- Khi yêu cầu hết hạn hoặc chuyển giao thất bại, trạng thái cũ được giữ thế nào?

Trong tình huống minh họa, chuyển giao chỉ diễn ra trong cùng tenant, chủ mới phải chấp nhận, đề nghị hết hạn sau 24 giờ. Khi hoàn tất, hệ thống hủy các chia sẻ trực tiếp hiện có và vô hiệu hóa liên kết tải đã cấp theo giới hạn công bố; chủ mới thiết lập lại chia sẻ nếu cần. Chủ cũ không tự trở thành người được chia sẻ. Đây là lựa chọn chính sách cho ví dụ, không phải quy tắc bắt buộc của mọi sản phẩm.

### 7.2. Trạng thái đề nghị khác trạng thái sở hữu

```text
Không có đề nghị
    -> Chủ hiện tại gửi đề nghị cho người nhận hợp lệ
    -> PENDING: tài liệu vẫn thuộc chủ hiện tại
       -> Người nhận từ chối: REJECTED, không đổi chủ
       -> Chủ hủy: CANCELLED, không đổi chủ
       -> Quá 24 giờ: EXPIRED, không đổi chủ
       -> Người nhận chấp nhận và đủ điều kiện: COMPLETED, đổi chủ
```

Một đề nghị chưa được chấp nhận không cấp quyền đọc nội dung cho người nhận. Thông tin hiển thị để chấp nhận phải giới hạn theo chính sách; không dùng chính cơ chế mời để lộ toàn bộ tài liệu riêng tư.

Khi hoàn tất, backend phải kiểm tra lại chủ hiện tại, phiên bản ownership, trạng thái tài liệu và tư cách nhận sở hữu. Không chỉ tin rằng các điều kiện từng đúng lúc tạo đề nghị. Nếu chủ hiện tại đã đổi hoặc người nhận đã rời tenant, đề nghị cũ không được thực hiện.

### 7.3. Tính nguyên tử và yêu cầu đồng thời

Đặc tả cần bảo đảm không tồn tại trạng thái đã đổi chủ nhưng các quyền cần thu hồi chưa được cập nhật theo giao dịch, hoặc hai đề nghị cùng hoàn tất dựa trên một phiên bản cũ.

Ví dụ yêu cầu:

> Mỗi lần hoàn tất chuyển giao phải đối chiếu `expected_ownership_version` với phiên bản hiện hành. Việc đổi chủ, tăng phiên bản, cập nhật các quyền trong cùng kho giao dịch và ghi sự kiện bền vững phải được cam kết nhất quán. Nếu điều kiện không còn đúng, thao tác phải thất bại hoặc yêu cầu tạo đề nghị mới; không ghi đè chuyển giao đã hoàn tất trước đó.

Có thể triển khai bằng giao dịch, khóa hoặc kiểm tra phiên bản phù hợp. Nếu quyền hoặc thành viên nằm ở hệ thống khác, cần xác định giao thức phối hợp và thời điểm nào được coi là hoàn tất; chỉ gọi các dịch vụ theo thứ tự không tự tạo ra tính nguyên tử.

Sự kiện gửi ra ngoài có thể dùng outbox bền vững cùng giao dịch và được truyền lại có kiểm soát. Thông báo cho người dùng không thay thế cập nhật quyền, và gửi thông báo thành công không phải bằng chứng chuyển giao đã cam kết.

### 7.4. Hiệu lực của quyền cũ và khả năng truy cập đã cấp

Trong ví dụ này, các yêu cầu ghi bắt đầu sau thời điểm cam kết phải được kiểm tra theo chủ hiện tại tại điểm cập nhật. Các đường đọc sử dụng cache được phép có độ trễ thu hồi tối đa 30 giây sau cam kết. Phải nêu riêng cách xử lý yêu cầu đang chạy, không suy từ quy tắc yêu cầu mới sang khả năng dừng mọi byte đang truyền.

Mốc 30 giây cần bao phủ các điểm thực thi trong phạm vi: API đọc, tìm kiếm, kiểm tra tải tệp và job chưa bắt đầu lấy dữ liệu. Token còn hạn hoặc cache còn dữ liệu không được kéo dài quyền chủ cũ quá giới hạn này.

Nếu URL tải trực tiếp không có kiểm tra thu hồi, thời hạn còn lại của URL có thể vượt cam kết. Khi đó phải thiết kế cổng kiểm tra, cơ chế thu hồi hoặc thời hạn cấp phù hợp; không chỉ xóa nút tải. Nội dung chủ cũ đã tải về trước chuyển giao thường không thể bị thu hồi bằng cách đổi quan hệ sở hữu trên máy chủ. Giới hạn đó cần được phản ánh trong mô hình đe dọa và phạm vi yêu cầu.

## 8. Bao phủ mọi đường truy cập và biến động vòng đời

### 8.1. Danh sách, tìm kiếm và thao tác hàng loạt

Một kiểm tra tốt ở `GET /documents/{id}` không bảo vệ đường tìm kiếm, bộ đếm, gợi ý gần đây hoặc tải tệp. Tập tài nguyên được trả về phải được giới hạn theo principal, tenant và quan hệ quyền phù hợp trước khi phân trang và tính tổng mà client nhìn thấy.

Ví dụ, danh sách “tài liệu của tôi” lọc theo chủ sở hữu hiện tại; danh sách “được chia sẻ với tôi” lọc theo các quyền chia sẻ còn hiệu lực. Không dùng `created_by` cho cả hai. Sau chuyển giao, một tài liệu có thể vẫn có người tạo là chủ cũ nhưng không còn nằm trong danh sách tài liệu họ sở hữu.

Thao tác hàng loạt cần kiểm tra từng đối tượng và quy định rõ tất cả hoặc từng phần. Nếu chọn tất cả, một ID không được phép phải ngăn toàn bộ tác động được yêu cầu theo hợp đồng. Nếu chọn từng phần, kết quả lỗi không được tiết lộ thông tin ngoài quyền. Không kiểm tra đối tượng đầu tiên rồi cho phép cả tập chỉ vì các ID có chung định dạng.

### 8.2. Tác vụ nền và bộ nhớ đệm

Job xuất tài liệu phải giữ chủ thể được đại diện, tenant, hành động và phạm vi tài nguyên. Danh tính mạnh của worker không thay thế quyền của người yêu cầu. Job phải kiểm tra lại trước khi lấy dữ liệu theo chính sách độ mới và thu hồi; việc được đưa vào hàng đợi lúc còn là chủ sở hữu không cấp quyền vô hạn.

Cache quyết định cần phân biệt ít nhất những chiều làm thay đổi kết quả như principal, tenant, tài nguyên, hành động và phiên bản chính sách hoặc quan hệ. Tuy nhiên, thêm `ownership_version` vào khóa không tự giúp cache biết phiên bản mới đã xuất hiện. Cần cơ chế tra cứu, vô hiệu hóa hoặc hết hạn có thể đáp ứng giới hạn thu hồi thực tế.

Khi nguồn quan hệ không khả dụng và cache không còn trong điều kiện được phép dùng, hệ thống không được mặc định cho phép chỉ vì người gọi từng là chủ. Hành vi lỗi và phạm vi sử dụng dữ liệu cũ phải được đặc tả theo mức rủi ro của hành động.

### 8.3. Chủ sở hữu bị vô hiệu hóa hoặc rời tenant

Nếu tài khoản chủ sở hữu bị đình chỉ, quan hệ lịch sử có thể vẫn được giữ để điều tra và phục hồi. Điều đó không có nghĩa tài khoản tiếp tục được dùng quyền cá nhân. Quyết định truy cập phải áp dụng điều kiện tài khoản và tư cách thành viên hoạt động.

Tài nguyên không có chủ đang hoạt động cần quy trình xử lý, chẳng hạn đánh dấu chờ phân công lại và đưa vào hàng đợi quản trị. Không tự gán cho người đầu tiên truy cập, không xóa dấu vết người sở hữu cũ và không tự chuyển toàn bộ tài liệu thành công khai.

Trong tình huống minh họa, chuyển giao cưỡng chế do chủ rời tổ chức dùng quyền `document.reassign_orphaned` riêng, có lý do và phê duyệt của một người khác có thẩm quyền. Người thực hiện không tự phê duyệt thao tác của mình. Quyền này chỉ cho phép quy trình chuyển giao trong phạm vi được giao; nó không tự cấp quyền đọc nội dung. Các điều kiện về người nhận và sự nhất quán vẫn phải được kiểm tra.

### 8.4. Xóa, khôi phục và thay đổi tenant

Khi khôi phục tài nguyên, hệ thống phải xác định lại chủ sở hữu hợp lệ và chính sách chia sẻ. Không tự phục hồi mọi quyền hoặc liên kết cũ nếu chính sách hiện hành không cho phép. Dữ liệu sao lưu mang quan hệ tại thời điểm sao lưu, có thể không còn phù hợp với thành viên và quyền hiện tại.

Đổi chủ trong cùng tenant khác với chuyển tài nguyên sang tenant khác. Chuyển tenant có thể ảnh hưởng người nhận, chia sẻ, tệp con, nhãn dữ liệu, khóa mã hóa và nghĩa vụ vận hành. Nếu sản phẩm không hỗ trợ, phải từ chối rõ ràng; không cho phép sửa `tenant_id` qua chức năng chuyển chủ. Nếu có hỗ trợ, cần một quy trình di chuyển riêng với yêu cầu và bằng chứng riêng.

## 9. Bộ yêu cầu liên kết với rủi ro

| Mã yêu cầu | Hành vi bắt buộc | Rủi ro | Điểm thực thi hoặc chủ sở hữu kỹ thuật | Bằng chứng tiêu biểu |
| --- | --- | --- | --- | --- |
| OWN-01 | API tạo cá nhân gán chủ từ principal và phạm vi tenant đã được kiểm tra; không chấp nhận client tự đặt trường sở hữu. | R-O02, R-O03 | Backend tạo tài liệu. | Gửi thêm hoặc sửa owner và tenant không tạo quan hệ trái phép. |
| OWN-02 | Mọi đường đọc, sửa, xóa và chia sẻ phải đánh giá quan hệ sở hữu cùng hành động, tenant và trạng thái tương ứng. | R-O01, R-O03 | Lớp thực thi nghiệp vụ và truy vấn. | Principal hợp lệ nhưng không có quyền bị từ chối trên chính tài nguyên được thử. |
| OWN-03 | API sửa nội dung không được đổi chủ, người tạo hoặc tenant; thay ownership dùng luồng riêng. | R-O02 | API cập nhật và ánh xạ dữ liệu. | Payload chèn thuộc tính quyền không làm thay đổi các trường được bảo vệ. |
| OWN-04 | Chuyển giao kiểm tra lại chủ, người nhận, trạng thái và phiên bản; cam kết thay đổi cùng quyền liên quan và sự kiện bền vững theo thiết kế. | R-O05, R-O06 | Dịch vụ chuyển giao và kho dữ liệu. | Hai đề nghị dựa trên cùng phiên bản không cùng hoàn tất; lỗi giữa chừng không để trạng thái nửa chừng. |
| OWN-05 | Sau chuyển giao, chủ cũ không có quyền từ ownership cũ; các đường đọc được quản lý mất hiệu lực trong tối đa 30 giây theo phạm vi đã chốt. | R-O05 | API, cache, tìm kiếm và tải tệp. | Thử bằng phiên cũ trên nhiều nút và kênh sau cửa sổ thu hồi. |
| OWN-06 | Tài nguyên con phải được đối chiếu đúng cha và tenant; quan hệ kế thừa quyền tuân thủ chủ hiện tại. | R-O01, R-O04 | API tệp, phiên bản và lưu trữ. | Ghép ID cha được phép với ID con ngoài quyền vẫn bị từ chối. |
| OWN-07 | Tìm kiếm, danh sách, bản xuất và job áp dụng cùng phạm vi quyền theo chính sách; số lượng trả về không lộ tài nguyên ngoài quyền. | R-O04, R-O05 | Truy vấn, chỉ mục và worker. | Kiểm tra dữ liệu trộn nhiều owner và tenant, kể cả gỡ quyền trước khi job chạy. |
| OWN-08 | Chủ rời tenant không tiếp tục dùng quyền cá nhân; tài nguyên có luồng phân công lại được kiểm soát. | R-O07, R-O08 | Quản lý thành viên và quy trình phục hồi. | Tài khoản cũ không truy cập được; người thiếu thẩm quyền không tự nhận tài nguyên. |
| OWN-09 | Sự kiện thay đổi ownership phải ghi chủ thể thực hiện, chủ cũ, chủ mới, tenant, phiên bản và kết quả, không kèm bí mật hoặc nội dung tài liệu. | R-O05, R-O08 | Producer kiểm toán và kho log. | Đối chiếu trạng thái cuối với sự kiện và kiểm tra quyền đọc bằng chứng. |

Các mã yêu cầu cần gắn với ca kiểm thử và thành phần triển khai. Chẳng hạn, OWN-05 không thể chỉ giao cho nhóm API nếu đường tải tệp trực tiếp do một nhóm khác vận hành và vẫn chấp nhận URL cũ lâu hơn 30 giây.

## 10. Ví dụ đặc tả đầy đủ cho quyền sửa của chủ sở hữu

### OWN-EDIT-01 — Sửa tài liệu cá nhân theo ownership hiện hành

**Mục tiêu:** ngăn người dùng đã đăng nhập sửa tài liệu ngoài phạm vi hoặc dùng quyền sở hữu đã bị chuyển giao.

**Phạm vi:** API sửa nội dung tài liệu cá nhân trong cổng minh họa. Người được chia sẻ quyền sửa dùng quy tắc quyền riêng; các ca dưới đây giả định không có chia sẻ hay quyền quản trị khác.

**Điều kiện bắt buộc:**

1. Principal hợp lệ, tài khoản đang được phép hoạt động và là thành viên hoạt động của tenant được yêu cầu.
2. Tài liệu thuộc tenant đó và principal trùng chủ sở hữu hiện hành theo nguồn dữ liệu có thẩm quyền.
3. Trạng thái tài liệu cho phép sửa; phiên bản dữ liệu còn phù hợp tại thời điểm cập nhật.
4. Payload chỉ gồm trường nội dung được phép. Các trường ownership, người tạo và tenant không được cập nhật qua đường này.
5. Việc kiểm tra và ghi phải ngăn một yêu cầu dùng ownership cũ để cập nhật sau khi chuyển giao đã cam kết. Nếu có tranh chấp phiên bản, thao tác thất bại hoặc được đánh giá lại với trạng thái mới; không tự bỏ điều kiện bảo vệ để thử lại.

**Hành vi khi từ chối:** không đổi nội dung, không đổi quan hệ quyền, không tạo bản xuất hoặc phát sự kiện nghiệp vụ thành công. Phản hồi tuân thủ chính sách công bố tài nguyên; không trả nội dung tài liệu của chủ khác để giải thích lỗi.

**Tiêu chí chấp nhận:**

| Ca | Thiết lập và thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Chủ hợp lệ | Đúng tenant, chủ hiện hành, tài liệu nháp, phiên bản đúng. | Nội dung được cập nhật một lần theo yêu cầu, ownership không đổi. |
| Người khác cùng tenant | Tài khoản hợp lệ nhưng không sở hữu và không có quyền bổ sung. | Từ chối; dữ liệu và các tác động ngoài không thay đổi. |
| Đổi owner trong payload | Chủ hợp lệ gửi thêm owner mới hoặc tenant khác. | Từ chối payload theo hợp đồng API; không chuyển giao và không sửa một phần. |
| Tài liệu tenant khác | Người gọi chọn tenant A nhưng gửi ID tài liệu B. | Không được sửa hoặc nhận nội dung tài liệu B. |
| Tài liệu đã khóa | Principal là chủ nhưng tài liệu không cho phép sửa. | Từ chối theo trạng thái, không coi ownership là ngoại lệ. |
| Chủ cũ sau chuyển giao | Dùng phiên còn hạn của chủ cũ gửi yêu cầu sửa mới. | Không được sửa bằng quyền ownership cũ. |
| Tranh chấp đồng thời | Yêu cầu sửa và chuyển giao cùng chạy trên phiên bản cũ. | Các giao dịch được sắp thứ tự nhất quán; yêu cầu không còn đủ điều kiện phải thất bại hoặc kiểm tra lại. |
| Thành viên bị đình chỉ | Owner vẫn được ghi nhận nhưng tài khoản hoặc thành viên không còn hoạt động. | Không được sửa dựa trên quan hệ sở hữu đơn lẻ. |
| Nguồn quyền lỗi | Không xác định được trạng thái cần thiết từ nguồn hoặc cache được phép dùng. | Không tự cho phép; dữ liệu giữ nguyên. |

**Bằng chứng nghiệm thu:** kết quả kiểm thử API, kiểm thử đồng thời, trạng thái trước–sau trong kho dữ liệu và sự kiện kiểm toán liên quan. Với trường hợp bị từ chối, phải kiểm tra cả không có tác động phụ, không chỉ mã HTTP.

**Trách nhiệm:** nhóm tài liệu sở hữu yêu cầu đầu cuối; nhóm dữ liệu hỗ trợ ràng buộc và giao dịch; nhóm kiểm thử cung cấp bằng chứng, nhóm vận hành theo dõi tranh chấp phiên bản và lỗi thu hồi.

## 11. Kiểm chứng và duy trì ownership trong vòng đời phát triển

### 11.1. Thiết kế dữ liệu kiểm thử có đối chứng

Bộ dữ liệu nên có ít nhất hai người dùng trong cùng tenant, một người dùng tenant khác, người được chia sẻ quyền đọc, người được chia sẻ quyền sửa và quản trị viên có quyền chuyển giao nhưng không có quyền đọc nội dung. Mỗi người có tài nguyên riêng, tệp con và một số tài nguyên có trạng thái khóa.

Các ca này giúp kiểm chứng khác biệt giữa danh tính hợp lệ và quan hệ quyền đúng. Dùng token sai cho mọi ca sẽ chỉ kiểm tra xác thực; không chứng minh kiểm soát ownership. Cũng cần ca được phép để tránh kết luận sai khi hệ thống từ chối tất cả.

Khi thử chuyển giao, tạo riêng dữ liệu cho đề nghị chờ chấp nhận, bị từ chối, hết hạn, bị hủy và hoàn tất. Thử đổi chủ lần nữa rồi phát lại đề nghị cũ; thử vô hiệu hóa người nhận trước khi chấp nhận; thử gọi hai lần hoàn tất đồng thời. Kết quả cần đối chiếu cả quyền, phiên bản, chia sẻ và tệp liên quan.

### 11.2. Đo thu hồi thay vì chỉ tải lại giao diện

Mốc đo của ví dụ là lúc giao dịch chuyển giao được cam kết. Dùng phiên cũ của chủ cũ để gọi các API, truy vấn tìm kiếm và đường tải trong phạm vi. Sau 30 giây, không đường đọc được quản lý nào được tiếp tục cho phép chỉ dựa trên ownership cũ. Các yêu cầu ghi mới tuân thủ điều kiện chủ hiện hành tại điểm cập nhật như đã đặc tả.

Đo trên nhiều nút có cache và cả job đang chờ; không chỉ thử một trình duyệt sau khi đăng xuất. Nếu một bản xuất hoặc liên kết nằm ngoài khả năng thu hồi đã chọn, phải công bố giới hạn và điều chỉnh thiết kế hoặc cam kết, không che bằng kết quả thử ở đường API chính.

### 11.3. Kiểm toán và phục hồi

Sự kiện thay đổi ownership cần phân biệt người thực hiện, chủ trước và chủ sau. Với chuyển giao cưỡng chế, lưu tham chiếu phê duyệt và lý do theo chính sách. Mã tương quan và phiên bản giúp liên kết đề nghị, cam kết, thu hồi và thông báo.

Không ghi token phiên, bí mật xác thực hoặc nội dung tài liệu vào log. Quyền đọc và xóa bằng chứng phải tách phù hợp với quyền chuyển giao; người thay chủ không mặc nhiên được xóa dấu vết của thao tác đó.

Một chuỗi truy vết minh họa:

```text
R-O05: Chủ cũ tiếp tục tải tệp sau chuyển giao
    -> OWN-05: Thu hồi các đường đọc được quản lý trong tối đa 30 giây
    -> Invalidation cache + kiểm tra tệp + giới hạn liên kết tải
    -> Kiểm thử bằng phiên và liên kết cũ trên các nút
    -> Theo dõi độ trễ thu hồi và người xử lý khi vượt ngưỡng
```

Khi khôi phục từ sao lưu, cần đối soát ownership, thành viên, chia sẻ và các phiên bản thu hồi theo kế hoạch phục hồi. Không giả định dữ liệu sở hữu cũ tự trở thành chính sách truy cập hiện tại. Khi thêm API, đổi mô hình sở hữu hoặc đưa xử lý sang job, phải cập nhật yêu cầu, điểm thực thi và bằng chứng tương ứng.

## 12. Bài tập áp dụng

Một nhóm mô tả chức năng: “Người tạo được toàn quyền với tài liệu; có thể chuyển `ownerId` bằng API cập nhật; tài liệu con dùng cùng quyền; tài khoản bị xóa thì quản trị viên xử lý.”

Hãy chuyển mô tả này thành bộ yêu cầu có thể nghiệm thu:

1. Tách người tạo, chủ sở hữu hiện tại, người được chia sẻ và quyền quản trị.
2. Chọn mô hình sở hữu cá nhân, nhóm hoặc tổ chức; xác định ranh giới tenant và các bất biến.
3. Viết yêu cầu cho tạo, sửa, chia sẻ, chuyển giao, rời tổ chức và khôi phục.
4. Chốt quyền của chủ cũ, số phận các chia sẻ và đường tải đã cấp sau chuyển giao.
5. Định nghĩa giới hạn thu hồi đo được và các trường hợp đồng thời cần kiểm chứng.
6. Viết ca thử thay ID tài nguyên, chèn owner vào payload, ghép ID cha–con sai và dùng phiên cũ sau chuyển giao.

Ví dụ một phần đáp án: API tạo cá nhân lấy chủ từ principal, còn `created_by` giữ người tạo ban đầu. API sửa nội dung không nhận trường đổi chủ. Chuyển giao là hành động riêng, kiểm tra chủ hiện hành, người nhận cùng tenant và phiên bản quan hệ; trạng thái chỉ đổi khi quy trình hoàn tất. Chủ cũ không tự giữ quyền, và mọi đường đọc được quản lý phải đáp ứng giới hạn thu hồi đã cam kết.

Một yêu cầu ownership đủ rõ phải chỉ ra ai có quan hệ gì với tài nguyên, quan hệ cho phép hành động nào, ai được thay đổi quan hệ và cách chứng minh quyền cũ không còn hiệu lực trong phạm vi đã xác định. Khi các phần này được gắn với rủi ro và kiểm thử, quyền sở hữu trở thành một kiểm soát bảo mật có thể thực thi và kiểm chứng.
