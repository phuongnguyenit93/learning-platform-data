# Multi-person approval

## 1. Vì sao một quyết định cần nhiều người?

Multi-person approval là cơ chế yêu cầu nhiều người có thẩm quyền cùng tham gia quyết định trước khi một quyền hoặc thao tác nhạy cảm được cho phép. Trong quản lý truy cập đặc quyền (PAM), cơ chế này có thể áp dụng khi cấp vai trò quản trị production, cho đọc một credential nhạy cảm, mở phiên bảo trì hoặc thực hiện thay đổi có tác động lớn.

Mục đích là giảm khả năng một cá nhân tự đề nghị, tự chấp thuận và tự thực hiện toàn bộ một hành động rủi ro. Một người cũng có thể bỏ sót phạm vi tác động mà một bên chịu trách nhiệm khác nhìn thấy. Tuy vậy, có hai lần bấm duyệt không tự chứng minh hai người độc lập đã đánh giá công việc.

Ví dụ, kỹ sư cơ sở dữ liệu đề nghị mở phiên bảo trì production. Chính sách yêu cầu một người sở hữu dịch vụ đánh giá nhu cầu và tác động vận hành, cùng một người thuộc chức năng an ninh đánh giá phạm vi đặc quyền và điều kiện kiểm soát. Hai người phải khác nhau và không phải người sử dụng quyền trong yêu cầu đó.

Bài học thuộc chương Approval workflow. Trọng tâm là thiết kế quyết định nhiều người sao cho quyền được cấp vẫn tuân theo least privilege, JIT/JEA, quản lý credential qua vault, giám sát phiên và lưu bằng chứng kiểm toán. Các mô hình và dữ liệu bên dưới là ví dụ thiết kế, không phải cấu hình của một sản phẩm PAM cụ thể.

## 2. Phân biệt những cơ chế dễ nhầm

| Cơ chế | Nó bảo vệ điều gì? | Điều không được suy ra |
|---|---|---|
| Multi-person approval | Nhiều người có thẩm quyền tham gia quyết định | Quyền trên đích đã được giới hạn hoặc phiên đã được ghi |
| MFA | Tăng mức bảo đảm xác thực một chủ thể | Có nhiều người độc lập tham gia |
| Separation of duties — SoD | Phân tách những trách nhiệm không nên tập trung vào một chủ thể | Mọi thao tác đều bắt buộc có hai người duyệt |
| Dual control | Một hành động cần sự phối hợp hoặc kiểm soát của hai bên theo thiết kế | Luôn được thực hiện bằng một form có hai chữ ký |
| Split knowledge | Mỗi bên chỉ biết một phần thông tin bí mật | Mọi quyết định cấp quyền đều được đánh giá độc lập |
| Hai tài khoản | Có hai danh tính kỹ thuật | Có hai con người khác nhau |

Một người đăng nhập hai tài khoản rồi duyệt hai lần vẫn là một người. Hai yếu tố xác thực của cùng một người cũng không trở thành hai phiếu duyệt.

Multi-person approval và giới hạn quyền bổ sung cho nhau. Dù hai người chấp thuận một phiên chẩn đoán, điểm thực thi vẫn cần chặn những khả năng ngoài phạm vi. Quyết định nhiều người không thay thế kiểm soát tài khoản đích, vault, thời hạn hoặc recording.

Cơ chế này cũng không loại bỏ hoàn toàn thông đồng, tài khoản bị chiếm quyền hay đánh giá hình thức. Nó tạo thêm rào cản và trách nhiệm có thể kiểm tra; mức độ hữu ích phụ thuộc cách chọn người, cách xác thực và chất lượng thông tin họ xem.

## 3. Xác định mô hình quyết định trước khi xây giao diện

### 3.1. Hai người khác nhau cùng chấp thuận

Mô hình đơn giản nhất yêu cầu hai người đủ thẩm quyền:

```text
Có ít nhất 2 người duyệt hợp lệ
AND hai người là hai con người khác nhau
AND không vi phạm quy tắc xung đột lợi ích
```

Cần định nghĩa rõ “đủ thẩm quyền”. Nếu cả hai chỉ thuộc cùng một nhóm chung, mô hình chưa đảm bảo đã có góc nhìn từ chủ sở hữu tài nguyên hoặc chức năng an ninh.

### 3.2. K trong N người

Mô hình K-of-N yêu cầu ít nhất K người trong một tập N người đủ điều kiện chấp thuận. Ví dụ, hai trong bốn người thuộc danh sách trực được phép duyệt cùng loại yêu cầu.

Phải quy định tập N là danh sách nào, được xác định tại thời điểm nào và thay đổi membership ảnh hưởng ra sao. Một danh sách người nhận notification không tự trở thành tập có quyền bỏ phiếu.

K-of-N thường giúp duy trì khả năng xử lý khi một người vắng mặt. Nó không mặc nhiên bảo đảm tính độc lập về trách nhiệm. Hai người trong cùng một nhóm vẫn có thể cùng bỏ sót một loại rủi ro.

### 3.3. Đủ số người và đủ nhóm trách nhiệm

Một mô hình khác yêu cầu:

```text
1 người thuộc nhóm chủ sở hữu tài nguyên
AND 1 người thuộc nhóm an ninh
AND hai người phải khác nhau
```

Nếu Lan vừa là owner vừa thuộc nhóm an ninh, một quyết định của Lan không được đồng thời điền cả hai vị trí khi chính sách yêu cầu hai người.

Điều kiện cần kiểm tra không chỉ là có hai nhóm xuất hiện trong dữ liệu. Phải tìm được cách gán mỗi vị trí bắt buộc cho một người khác nhau và đủ thẩm quyền ở vị trí đó.

| Phiếu chấp thuận | Tư cách | Kết quả với chính sách owner + security, hai người |
|---|---|---|
| Lan | Owner và security | Chưa đủ; mới có một người |
| Lan và Minh | Lan thuộc cả hai nhóm, Minh chỉ là owner | Có thể đủ: Minh làm owner, Lan làm security |
| Lan và Hoa | Cả hai chỉ là owner | Chưa đủ người đáp ứng vị trí security |
| Lan và tài khoản phụ của Lan | Hai account nhưng cùng một người | Chưa đủ số người độc lập |

Khi có nhiều vị trí với nhóm chồng lấn, logic gán vị trí cần xử lý đầy đủ. Việc chọn người đầu tiên cho vị trí đầu tiên rồi dừng có thể báo thiếu quorum dù tồn tại một cách gán hợp lệ khác.

### 3.4. Theo tầng hoặc có điều kiện

Một yêu cầu có thể phải qua owner trước, sau đó mới tới an ninh; hoặc hai bên được đánh giá song song. Với thao tác rất nhạy cảm, có thể cần thêm một vai trò khác dựa trên môi trường, loại tài nguyên hoặc tác động.

Những điều kiện này phải do chính sách có thẩm quyền xác định. Người yêu cầu không được tự bỏ một tầng, chọn người dễ duyệt hoặc đổi nhãn rủi ro để làm giảm số người bắt buộc.

## 4. Tính độc lập phải gắn với con người và trách nhiệm

### 4.1. Nhận diện người duyệt thực tế

Quorum của quy trình nhiều người cần dựa trên danh tính con người đã được xác minh, không chỉ số account ID. Hệ thống phải có quan hệ đáng tin giữa tài khoản xác thực và chủ thể con người theo mô hình danh tính của tổ chức.

Không dùng tên hiển thị hoặc email do client khai để kết luận hai tài khoản thuộc hai người. Quan hệ hợp nhất danh tính cũng cần được quản trị, vì sai quan hệ có thể làm đếm thừa hoặc thiếu người.

Đối với tài khoản dịch vụ, một kết quả đánh giá policy tự động có thể là điều kiện bắt buộc trước khi duyệt. Tuy nhiên, không đếm nó thành một người nếu chính sách đòi hỏi người duyệt. Nếu quy trình cho phép một loại tác nhân tự động quyết định, cần mô tả đó là một lớp quyết định riêng, với thẩm quyền và bằng chứng riêng.

### 4.2. Tránh tự duyệt và xung đột lợi ích

Chính sách cần làm rõ người nào bị loại khỏi tập người duyệt. Tùy yêu cầu, tập loại trừ có thể gồm:

- Người gửi request.
- Người sẽ sử dụng grant.
- Người gửi thay cho chủ thể thụ hưởng.
- Người có quan hệ xung đột khác đã được tổ chức định nghĩa.

Nếu một quản lý gửi thay kỹ sư nhà cung cấp, việc loại trừ chỉ người gửi có thể vẫn cho kỹ sư tự duyệt quyền của mình. Cần giữ riêng các danh tính và áp dụng quy tắc đúng với từng vai trò.

Độc lập không chỉ là khác ID. Tổ chức có thể yêu cầu khác chức năng, khác nhóm trách nhiệm hoặc một mức phân tách khác theo rủi ro. Không nên tự kết luận rằng hai người thuộc hai nhóm trên giao diện chắc chắn độc lập về tổ chức; quan hệ đó phải đến từ nguồn và quy tắc được quản lý.

### 4.3. Ủy quyền không làm một người thành hai phiếu

Khi người trực vắng mặt, có thể cho người thay thế nhận trách nhiệm trong thời hạn và phạm vi cụ thể. Hệ thống cần xác minh quan hệ ủy quyền, quyền thực tế của người thay thế và giới hạn áp dụng.

Nếu Nam duyệt thay Lan, người thực sự ra quyết định là Nam. Không được tính cùng hành động đó thành một phiếu của Nam và một phiếu của Lan.

Nếu Nam đã duyệt ở một vị trí khác, việc nhận thêm ủy quyền không cho Nam chiếm hai vị trí khi chính sách yêu cầu hai người độc lập. Nếu không còn đủ người, request cần ở trạng thái chưa đủ điều kiện hoặc đi theo đường ngoại lệ đã được quy định.

## 5. Mọi người phải duyệt cùng một phạm vi

Hai người chấp thuận hai nội dung khác nhau không tạo thành một quyết định hợp lệ cho nội dung cuối cùng.

Mỗi phiếu cần ràng buộc với tối thiểu:

| Nhóm dữ liệu | Nội dung cần gắn |
|---|---|
| Yêu cầu | Request reference và revision |
| Chủ thể | Người gửi, chủ thể sử dụng và quan hệ gửi thay nếu có |
| Tài nguyên | Tập đích hoặc quy tắc nhóm động đã được quy định |
| Quyền | Hành động, role/account profile và phiên bản liên quan |
| Thời gian | Cửa sổ kích hoạt, hạn truy cập và giới hạn phiên |
| Đường thực thi | Broker, kênh truy cập và điều kiện bắt buộc |
| Kiểm soát | Recording, xác thực, thiết bị và điều kiện khác |
| Căn cứ quyết định | Policy reference, phiên bản hoặc ngữ cảnh chính sách cần lưu |

Nếu request đổi từ staging sang production sau phiếu thứ nhất, phiếu thứ nhất không được mặc nhiên cộng với phiếu thứ hai cho phạm vi production. Hệ thống cần tạo revision mới và xử lý lại theo chính sách.

Một bản tóm tắt hoặc digest có thể hỗ trợ phát hiện nội dung thay đổi, nhưng không tự chứng minh quyết định được tạo bởi đúng người hoặc bản ghi không thể bị sửa. Việc chuẩn hóa nội dung, lưu bằng chứng, xác thực actor và bảo vệ kho audit vẫn cần được thiết kế riêng.

Các chỉnh sửa thu hẹp quyền cũng phải có quy tắc rõ. Có thể cho phép cấp một tập con nếu chính sách hỗ trợ, nhưng bằng chứng phải thể hiện tập con nào được chấp thuận và grant nào thực sự được tạo. Không cho phép người dùng tăng lại phạm vi bằng cách khôi phục một revision cũ đã hết giá trị.

## 6. Người duyệt cần nhìn thấy điều gì?

Một nút “Approve” không cung cấp đủ cơ sở đánh giá. Mỗi người duyệt cần thấy thông tin phù hợp với trách nhiệm của mình:

- Chủ thể sẽ dùng quyền và bên gửi thay nếu có.
- Tác vụ cần làm, lý do và liên kết công việc đã được xác minh theo quy trình.
- Tài nguyên, môi trường, owner và phạm vi dữ liệu liên quan.
- Khả năng thực tế của profile được đề nghị, gồm quyền gián tiếp đáng kể.
- Cửa sổ kích hoạt, thời lượng phiên, hạn tuyệt đối và số lần sử dụng.
- Cách sử dụng credential, khả năng đọc secret và yêu cầu rotation nếu áp dụng.
- Kênh truy cập, recording và các điều kiện chưa đáp ứng.
- Revision đang xem, quyết định trước đó và việc phạm vi đã thay đổi hay chưa.

Owner có thể tập trung vào tính cần thiết và tác động vận hành. Người duyệt an ninh có thể tập trung vào mức quyền, đường truy cập và khả năng truy vết. Cả hai vẫn phải hiểu nội dung mình đang chấp thuận.

Không gửi mật khẩu, token hoặc toàn bộ secret trong email mời duyệt. Notification có thể chứa thông tin tối thiểu và dẫn tới một giao diện được kiểm tra quyền truy cập. Một đường dẫn từ email không tự trao thẩm quyền duyệt cho người bấm.

Trước khi ghi quyết định, máy chủ cần kiểm tra lại actor, thẩm quyền, request revision, trạng thái hiện hành và mức xác thực yêu cầu. Nếu phải xác thực tăng cường cho loại quyết định này, lần xác thực đó vẫn chỉ xác minh một người, không tạo thêm phiếu.

## 7. Tính quorum từ các quyết định còn hiệu lực

Quorum là tập điều kiện đủ để quy trình ra kết quả, không phải chỉ một bộ đếm số lần nhận thông báo “approve”.

### 7.1. Phiếu hợp lệ cần đồng thời đáp ứng các điều kiện

Một phiếu được tính khi:

1. Được ghi bởi actor đã xác thực và có thẩm quyền phù hợp.
2. Áp dụng đúng tenant, tài nguyên, request và revision.
3. Không vi phạm quy tắc tự duyệt, trùng người hoặc xung đột trách nhiệm.
4. Còn hiệu lực theo thời gian và quy tắc rút lại.
5. Không bị thay thế bởi một quyết định mới theo chính sách.
6. Thuộc một trạng thái request vẫn cho phép sử dụng quyết định đó.
7. Đáp ứng yêu cầu về tư cách hiện hành hoặc hiệu lực tư cách đã được quy định.

Một người bấm duyệt hai lần chỉ có một đóng góp hợp lệ theo quy tắc của vị trí tương ứng. Một sự kiện bị gửi lại không tạo phiếu mới.

### 7.2. Cần định nghĩa ý nghĩa của từ chối và không phản hồi

| Kết quả | Ví dụ về cách xử lý có thể áp dụng |
|---|---|
| Approve | Đóng góp một quyết định chấp thuận hợp lệ |
| Reject | Chấm dứt request hoặc chặn quorum theo quy tắc từ chối |
| Request changes | Trả yêu cầu để sửa, dẫn tới revision mới |
| Abstain | Không đóng góp phiếu chấp thuận |
| Timeout | Hết thời gian chờ; chưa đạt điều kiện |
| Withdraw | Rút phiếu và tính lại trạng thái theo chính sách |

Không có một ngữ nghĩa reject chung cho mọi hệ thống. Một chính sách có thể quy định bất kỳ người duyệt bắt buộc nào từ chối là request kết thúc. Chính sách khác có thể yêu cầu đánh giá lại hoặc chọn người thay thế theo quy trình có kiểm soát.

Điều quan trọng là không âm thầm coi im lặng, hết hạn hoặc vắng mặt thành chấp thuận. Nếu một phiếu từ chối có hiệu lực veto, các phiếu approve về sau không được vượt qua veto bằng phép cộng đơn thuần.

Không được bỏ qua người đã từ chối rồi tìm thêm người đồng ý cho tới khi đủ số, trừ khi chính sách có một cơ chế xem xét lại với thẩm quyền và bằng chứng rõ ràng.

### 7.3. Pseudocode đánh giá

```text
evaluate_request(request_ref):
    request = load_authoritative_request(request_ref)

    if request is cancelled, rejected, expired or revoked:
        return NOT_ELIGIBLE

    policy = resolve_applicable_policy(request)
    if request revision or policy conditions require reevaluation:
        return REEVALUATION_REQUIRED

    decisions = load_decisions_for_exact_revision(request)
    valid = validate_actor_authority_scope_time_and_conflicts(decisions)

    if policy_has_effective_veto(valid):
        return REJECTED

    approvals = keep_active_approvals_by_real_person(valid)

    assignment = find_distinct_people_for_required_slots(
        approvals,
        policy.required_slots,
        policy.conflict_rules
    )

    if assignment does not exist:
        return WAITING_FOR_QUORUM

    return QUORUM_SATISFIED_WITH_EVIDENCE
```

Đây là pseudocode mô tả ý nghĩa, không phải một implementation hoàn chỉnh. Hệ thống thực tế còn cần xử lý đồng thời, chống ghi trùng, giới hạn thời gian và liên kết việc ra quyết định với bước cấp grant.

Đủ quorum chưa đồng nghĩa grant đã tồn tại. Quá trình cấp quyền có thể thất bại hoặc phát hiện điều kiện mới không còn đáp ứng.

## 8. Thời hạn, thay đổi tư cách và rút phiếu

### 8.1. Phân biệt các loại thời hạn

Có thể cần nhiều giới hạn độc lập:

| Giới hạn | Mục đích |
|---|---|
| Hạn nhận quyết định | Không tiếp tục duyệt một request quá cũ |
| Thời hạn hiệu lực phiếu | Không dùng mãi một quyết định đã đưa ra từ lâu |
| Cửa sổ kích hoạt grant | Giới hạn lúc được bắt đầu sử dụng |
| Thời lượng phiên | Giới hạn một lần thực hiện |
| Hạn truy cập tuyệt đối | Chấm dứt quyền trong phạm vi đã quy định |

Ví dụ, phiếu thứ nhất hết hiệu lực trước khi phiếu thứ hai đến thì chưa có quorum đồng thời. Hệ thống không nên cộng mọi phiếu từng tồn tại trong lịch sử.

Đồng hồ máy chủ và múi giờ cần được xác định rõ. Client không được tự kéo dài hiệu lực bằng thời gian gửi hoặc giá trị đếm ngược trên trình duyệt.

### 8.2. Người duyệt mất tư cách

Một người có thể đã có thẩm quyền lúc duyệt nhưng sau đó rời nhóm hoặc bị vô hiệu hóa. Chính sách cần quy định quyết định cũ còn được dùng trong điều kiện nào.

Với các quyền nhạy cảm, một thiết kế thường cần kiểm tra lại những điều kiện bắt buộc trước khi cấp hoặc kích hoạt grant. Nếu policy yêu cầu người duyệt vẫn có tư cách hiện hành, phiếu của người đã mất tư cách không còn được tính tại bước đó.

Không âm thầm thay đổi ngữ nghĩa giữa các thành phần. Bộ phận workflow không thể coi tư cách là đã cố định tại lúc duyệt trong khi bộ phận cấp quyền lại giả định nó luôn hiện hành.

Việc vô hiệu hóa một người duyệt cũng cần được phân biệt với thu hồi toàn bộ những grant họ từng tham gia. Phạm vi ảnh hưởng phải dựa trên chính sách và quan hệ cụ thể, thay vì thao tác hàng loạt không có căn cứ.

### 8.3. Rút phiếu khi grant đã xuất hiện

Trước khi cấp grant, rút phiếu có thể làm request trở về chưa đủ quorum. Sau khi cấp, hệ thống phải xác định việc rút đó có thu hồi grant hay không và tác động tới phiên đang chạy.

Ví dụ, chính sách có thể quy định rằng mất một quyết định bắt buộc sẽ chặn kích hoạt mới và yêu cầu thu hồi các quyền chịu ảnh hưởng. Nếu vậy, cần thực thi tại grant, broker và đích theo khả năng tích hợp, không chỉ giảm bộ đếm trên trang request.

Một thao tác “withdraw” không được xóa lịch sử người đó từng duyệt. Audit cần giữ cả quyết định ban đầu và sự kiện rút lại.

## 9. Đồng thời, chống trùng và cấp grant đúng một ý định

### 9.1. Hai người duyệt gần như cùng lúc

Hai thao tác có thể cùng quan sát rằng “chỉ còn thiếu một phiếu”. Nếu mỗi thao tác tự tạo grant sau khi ghi phiếu, có thể phát sinh cấp trùng.

Hệ thống cần một cách chuyển trạng thái có điều kiện và cơ chế cấp grant chống trùng theo request revision hoặc định danh cấp quyền phù hợp. Kỹ thuật cụ thể có thể là transaction, kiểm soát phiên bản và một kênh xử lý sự kiện bền vững, tùy kiến trúc.

Điều cần giữ là cùng một ý định được chấp thuận không tạo thêm quyền ngoài giới hạn. Nếu request cho phép một lần sử dụng, hai grant độc lập có thể phá vỡ giới hạn đó dù nội dung giống nhau.

### 9.2. Hủy hoặc hết hạn trong lúc phiếu cuối đến

Máy chủ phải kiểm tra trạng thái có thẩm quyền khi ghi quyết định và khi chuyển sang cấp quyền. Nếu hủy đã có hiệu lực, phiếu cuối đến muộn không được hồi sinh request.

Nếu việc cấp grant đã xảy ra trước khi hủy, hệ thống cần xử lý grant theo quy tắc thu hồi. Chỉ đổi request sang “cancelled” chưa chứng minh quyền đã biến mất.

### 9.3. Sự kiện lặp hoặc sai thứ tự

Một consumer có thể nhận lại sự kiện approved sau khi đã nhận revoked. Trước khi cấp hoặc khôi phục quyền, consumer phải kiểm tra revision, trạng thái, hạn và quyết định hiện hành theo giao thức đã thiết kế.

Không dùng thứ tự đến của notification làm nguồn chân lý duy nhất. Sự kiện cần có định danh và quan hệ phiên bản đủ để phát hiện trùng hoặc cũ, nhưng vẫn phải thực thi những giới hạn quyền liên quan.

Khi kết quả cấp hoặc thu hồi chưa được xác nhận, giữ trạng thái đang xử lý hoặc chưa biết và tiếp tục đối soát. Không báo “quyền đã thu hồi” chỉ vì một lệnh đã được gửi tới broker.

## 10. Ví dụ: hai trách nhiệm cho một phiên bảo trì production

### 10.1. Chính sách minh họa

Một kỹ sư đề nghị thực hiện tác vụ bảo trì cơ sở dữ liệu đã được xác định, bằng profile giới hạn qua broker. Profile không phải tài khoản toàn quyền và khả năng thực tế phải phù hợp công việc.

```yaml
policy_ref: prod-db-maintenance-approval-v4
required_slots:
  - slot: resource_owner
    eligible_role_ref: payments-resource-owners
  - slot: security_reviewer
    eligible_role_ref: production-security-reviewers
distinct_human_per_slot: true
exclude_requester: true
exclude_beneficiary: true
request_revision_binding: required
rejection_behavior: terminate_request
approval_deadline: "2026-11-26T14:10:00+07:00"
grant_window:
  not_before: "2026-11-26T14:10:00+07:00"
  activate_before: "2026-11-26T14:20:00+07:00"
  absolute_access_until: "2026-11-26T14:40:00+07:00"
  session_max_seconds: 1200
  session_limit: 1
execution_conditions:
  channel_ref: database-maintenance-broker
  credential_delivery: broker_only
  recording_required: true
```

Đây là dữ liệu giả mô tả chính sách cho ví dụ. Các tham chiếu vai trò, giá trị thời gian và điều kiện phải do phía có thẩm quyền xác lập hoặc xác minh; không chấp nhận nguyên payload của người yêu cầu như một policy đã được duyệt.

### 10.2. Các bên tham gia

| Người | Tư cách | Có thể đóng góp gì? |
|---|---|---|
| An | Người gửi và người dùng grant | Không được duyệt request của mình |
| Bình | Owner của tài nguyên | Có thể đáp ứng vị trí resource owner |
| Chi | Security reviewer | Có thể đáp ứng vị trí security reviewer |
| Dũng | Có cả hai tư cách | Có thể đáp ứng một vị trí, không tự lấp cả hai |

Nếu chỉ Dũng chấp thuận thì thiếu người thứ hai. Nếu Bình và Dũng chấp thuận, có thể gán Bình làm owner và Dũng làm security. Nếu Bình và Chi chấp thuận, hai vị trí cũng được đáp ứng khi các điều kiện khác hợp lệ.

### 10.3. Diễn biến hợp lệ

1. Request R-731 revision 2 được gửi với tài nguyên, profile và thời gian đã xác định.
2. Lúc 14:05, Bình xem revision 2 và chấp thuận với tư cách owner.
3. Lúc 14:07, Chi xem cùng revision và chấp thuận với tư cách security reviewer.
4. Hệ thống xác minh hai con người khác nhau, thẩm quyền, không có từ chối và mọi phiếu còn hiệu lực.
5. Grant được tạo có tham chiếu R-731 revision 2 cùng bộ quyết định đã dùng.
6. Lúc 14:12, An kích hoạt bằng danh tính và điều kiện được phép.
7. Phiên có giới hạn 20 phút nên deadline là 14:32, vẫn trước hạn tuyệt đối 14:40.
8. Broker, quyền đích và đường credential thực thi phạm vi; bằng chứng phiên được liên kết với grant.

Nếu broker không thể bảo đảm một điều kiện bắt buộc, hệ thống không tự chuyển An sang một tài khoản quản trị trực tiếp. Đường thực thi khác cần được xem xét theo chính sách thích hợp.

### 10.4. Những nhánh làm mất điều kiện

- An đổi profile sau phiếu của Bình: cần revision và quyết định lại theo quy tắc thay đổi.
- Chi từ chối: request kết thúc theo chính sách ví dụ, không chờ thêm approve để vượt qua.
- Phiếu cuối tới sau 14:10: request chưa đáp ứng hạn quyết định; không tự dời lịch.
- An thử mở phiên mới từ 14:20 trở đi: cửa sổ kích hoạt đã đóng.
- Một sự kiện approve cũ được gửi lại sau thu hồi: không tạo grant mới.
- Một người dùng hai account để chiếm cả hai vị trí: không đáp ứng hai con người độc lập.

## 11. Từ quyết định tới vault, phiên và quyền đích

Quyết định nhiều người có thể kiểm soát các loại hành động khác nhau, cần phân biệt rõ:

### 11.1. Cho phép mở phiên

Grant cho phép người dùng mở đúng phiên, qua broker được chỉ định, với tài khoản hoặc profile đã chấp thuận. Vault có thể đưa credential cho broker theo tích hợp mà không tiết lộ cho người dùng.

Bằng chứng cần thể hiện chủ thể thực sự, tài nguyên, quyền được dùng, quyết định nguồn, session reference và kết quả kết thúc. Recording chỉ bao phủ những giao thức và kênh mà hệ thống thực sự hỗ trợ.

### 11.2. Cho phép đọc credential

Cho đọc credential có rủi ro khác với chỉ mở phiên. Sau khi nhận secret, người dùng có thể sao chép và dùng qua đường khác nếu hệ thống không chặn.

Vì vậy, quorum không đủ để bảo đảm phạm vi sử dụng sau tiết lộ. Cần xem loại credential, quyền thực tế, đường dùng được phép, thời hạn, khả năng thu hồi hoặc rotation và consumer phụ thuộc. Hết hạn grant trong PAM không tự làm một mật khẩu còn hiệu lực trên đích mất tác dụng.

### 11.3. Cho phép một tác vụ cụ thể

Một cơ chế có thể phê duyệt một thao tác được broker hoặc automation kiểm soát, thay vì cấp một shell rộng. Quyết định cần gắn với tham số và tác động quan trọng của tác vụ.

Ví dụ, duyệt bảo trì tài nguyên A không cho phép đổi sang B trong payload thực thi. Một tác vụ thất bại rồi được chạy lại cũng phải tuân theo giới hạn retry hoặc số lần dùng đã được định nghĩa.

Dù mô hình nào, grant cần có điểm thực thi và điểm kết thúc. Chữ “approved” trong cơ sở dữ liệu workflow không tự tạo least privilege trên máy đích.

## 12. Dự phòng người duyệt và xử lý khẩn cấp

### 12.1. Thiết kế khả năng xử lý khi có người vắng

Có thể có danh sách dự phòng, lịch trực hoặc cơ chế ủy quyền theo phạm vi. Chúng cần được chuẩn bị trước và kiểm tra đủ số người độc lập, thay vì chỉ đủ account.

Notification hoặc escalation có thể chuyển tới người đủ thẩm quyền khác. Nó không được tự làm giảm số vị trí hay loại bỏ một trách nhiệm bắt buộc. Người quản trị workflow thay chính sách để tự duyệt cũng là một đường đặc quyền cần được kiểm soát.

Nếu không có đủ người, trạng thái đúng có thể là chờ, hết hạn hoặc cần xử lý theo quy trình ngoại lệ. Không nên biến timeout thành approve tự động để làm cho hệ thống “luôn chạy được”.

### 12.2. Break-glass có ngữ nghĩa riêng

Trong tình huống khẩn cấp, tổ chức có thể có một đường được ủy quyền trước với yêu cầu khác: người được kích hoạt, phạm vi, thời hạn, cảnh báo, bằng chứng và hậu kiểm.

Nếu đường đó cho phép một người hành động trước rồi đánh giá sau, phải ghi đúng là sử dụng break-glass theo chính sách. Không ghi rằng multi-person approval đã hoàn thành khi người thứ hai chưa hề quyết định.

Hậu kiểm không tương đương với quyết định trước khi cấp quyền. Nó phục vụ trách nhiệm và xử lý sau sự kiện, còn kiểm soát phòng ngừa đã được thay đổi theo đường khẩn cấp.

## 13. Bằng chứng và bảo vệ chính hệ thống phê duyệt

Chuỗi bằng chứng cần liên kết:

```text
Request + revision + phạm vi
    -> Chính sách và các vị trí bắt buộc
    -> Danh tính thật, tư cách và quyết định từng người
    -> Cách gán người vào các vị trí để đạt quorum
    -> Grant được cấp cùng điều kiện và thời hạn
    -> Kích hoạt, phiên hoặc tác vụ thực tế
    -> Rút phiếu, thu hồi, hết hạn và kết quả đối soát
```

Nên giữ actor thực tế, người được đại diện nếu có, thời điểm máy chủ, decision reference, lý do, revision, policy context và kết quả. Nếu có xác thực tăng cường, giữ tham chiếu hoặc thuộc tính cần thiết mà không ghi secret xác thực.

Bằng chứng cần giải thích được tại sao hệ thống coi quorum là đủ lúc cấp quyền. Chỉ lưu một số đếm “2 approvals” sẽ khó kiểm tra trường hợp trùng người, sai vai trò hoặc một phiếu đã hết hạn.

Quyền thay thành viên nhóm duyệt, sửa policy, tạo ủy quyền, hợp nhất danh tính và sửa dữ liệu quyết định đều có thể ảnh hưởng trực tiếp tới quorum. Những khả năng này thuộc phạm vi đặc quyền của nền tảng và cần có phân quyền, dấu vết thay đổi cùng kiểm soát phù hợp.

Không cho người dùng sửa phiếu cũ để thay đổi lịch sử. Việc thay hoặc rút quyết định nên được biểu diễn bằng sự kiện mới theo quy tắc rõ. Kho bằng chứng cần được bảo vệ khỏi truy cập, thay đổi hoặc xóa trái phép; log có dữ liệu nhạy cảm cũng cần giới hạn người xem và xuất bản.

Đo lường có thể theo dõi thời gian chờ từng vị trí, tỷ lệ hết hạn, yêu cầu sửa lại, số lần tự duyệt bị chặn và thời gian xác nhận thu hồi. Không dùng tốc độ duyệt làm thước đo duy nhất, vì nó có thể khuyến khích chấp thuận hình thức.

## 14. Những lỗi cần tránh và thực hành áp dụng

| Lỗi | Vì sao không đủ? | Điều cần thiết kế |
|---|---|---|
| Đếm số sự kiện approve | Retry và tài khoản phụ có thể tăng số đếm | Phiếu còn hiệu lực theo con người, revision và vai trò |
| Một người đáp ứng hai nhóm | Có hai nhãn nhưng chỉ một người | Gán các vị trí cho người khác nhau |
| Loại trừ người gửi nhưng quên người thụ hưởng | Yêu cầu gửi thay vẫn có thể tự duyệt | Kiểm tra riêng cả hai danh tính |
| Giữ phiếu khi request đổi quyền | Người duyệt chưa xem phạm vi mới | Ràng buộc revision và xử lý thay đổi |
| Hết thời gian thì tự duyệt | Không có quyết định thực sự | Chờ, hết hạn hoặc ngoại lệ được quy định |
| Đạt quorum là lập tức báo truy cập thành công | Grant hoặc tích hợp thực thi có thể lỗi | Tách quyết định, cấp grant và kích hoạt |
| Rút phiếu chỉ đổi giao diện | Grant hoặc phiên có thể vẫn dùng được | Quy tắc tác động và xác nhận ở điểm thực thi |
| Cho đọc secret như mở phiên | Secret có thể tiếp tục được dùng ngoài broker | Xét tiết lộ, vòng đời credential và consumer |
| Hai người duyệt nên bỏ giới hạn quyền | Quyết định không hạn chế được khả năng trên đích | Thực thi least privilege, thời hạn và bằng chứng |

Để thực hành, chọn một tác vụ bảo trì trong lab và mô tả chính sách gồm hai vị trí bắt buộc. Tạo danh sách người có tư cách chồng lấn, trong đó có một người giữ cả hai vai trò và một người là chủ thể nhận quyền. Xác định những tổ hợp nào đủ quorum và vì sao.

Tiếp theo, mô tả các trường hợp request đổi revision, một người rút phiếu, phiếu cuối đến khi đã hủy và hai phiếu cuối được ghi đồng thời. Với mỗi trường hợp, chỉ rõ có được cấp grant hay không, grant đã tồn tại chịu tác động gì và bằng chứng nào giúp xác nhận kết quả.

Đầu ra cần thể hiện nhiều hơn một bộ đếm: phải xác định được những con người độc lập nào đã chấp thuận đúng nội dung, bằng thẩm quyền nào, trong thời hạn nào, và quyết định đó được chuyển thành quyền có kiểm soát ra sao.
