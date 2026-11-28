# Zero Trust identity principle

## 1. Danh tính phải được xác minh, quyền phải có căn cứ

Một nhân viên đã kết nối VPN, dùng máy tính công ty và đăng nhập thành công có được truy cập mọi tài nguyên trong mạng nội bộ không? Theo tư duy Zero Trust, những thông tin đó chưa đủ để trả lời.

**Nguyên tắc danh tính trong Zero Trust** yêu cầu việc truy cập dựa trên danh tính đã được xác minh, quyền phù hợp với tài nguyên và điều kiện hiện tại. Hệ thống không mặc nhiên cho phép chỉ vì yêu cầu xuất phát từ mạng nội bộ, một thiết bị thuộc tổ chức hoặc một phiên từng được chấp nhận trước đó.

Ví dụ, Mai là nhân viên kế toán đã đăng nhập bằng MFA. Mai có thể được đọc các hóa đơn thuộc phạm vi công việc, nhưng không đương nhiên được sửa chính sách IAM, phê duyệt đề nghị của chính mình hoặc tải toàn bộ dữ liệu khách hàng. Mỗi hành động vẫn cần căn cứ phân quyền riêng.

Zero Trust không có nghĩa là không tin bất kỳ thành phần nào đến mức hệ thống không thể vận hành. Hệ thống vẫn cần các nguồn tin cậy, khóa, chính sách và thành phần thực thi. Điều thay đổi là **không trao sự tin cậy ngầm định, quá rộng hoặc kéo dài chỉ từ một bằng chứng ban đầu**.

Trong IAM, nguyên tắc này đi xuyên suốt từ quản lý vòng đời danh tính đến xác thực, cấp quyền, phiên, danh tính workload, đặc quyền và kiểm toán.

## 2. Ba hướng tư duy gắn với danh tính

### 2.1. Xác minh rõ ràng

Trước khi cấp quyền truy cập, hệ thống cần xác định chủ thể và kiểm tra các bằng chứng phù hợp với yêu cầu. Chủ thể có thể là con người, ứng dụng, dịch vụ hoặc một tác vụ tự động.

Các câu hỏi thường cần trả lời gồm:

- Danh tính đến từ nguồn nào và nguồn đó có được tin cậy trong phạm vi này không?
- Bằng chứng xác thực có hợp lệ, còn hiệu lực và dành cho bên nhận hiện tại không?
- Tài khoản hoặc workload còn hoạt động không?
- Chủ thể có quyền đối với hành động và tài nguyên được yêu cầu không?
- Các điều kiện bắt buộc về phiên, thiết bị hoặc ngữ cảnh có được đáp ứng không?

Một chuỗi tên người dùng trong header chưa phải danh tính đã xác thực. Một token có hình thức đúng chưa chắc là token hợp lệ. Một lần MFA thành công cũng chưa chứng minh người dùng có quyền làm mọi việc.

### 2.2. Cấp ít quyền nhất

Quyền cần phù hợp với nhiệm vụ, tài nguyên, hành động và thời gian sử dụng. Đăng nhập thành công không phải bước chuyển sang trạng thái “được tin cậy toàn bộ”.

Ví dụ, nhân viên hỗ trợ cần xem trạng thái yêu cầu của một khách hàng có thể chỉ được quyền đọc trong phạm vi khách hàng đó. Quyền sửa cấu hình hoặc xuất dữ liệu hàng loạt cần điều kiện riêng.

Với đặc quyền, có thể kết hợp tài khoản quản trị riêng, kích hoạt vai trò có thời hạn, phê duyệt khi cần và kết thúc phiên sau công việc. Quyền tạm thời vẫn phải được giới hạn về phạm vi; thời hạn ngắn không bù được một tập quyền quá rộng.

### 2.3. Thiết kế với giả định có thể đã xảy ra xâm nhập

Hệ thống cần tính đến khả năng tài khoản, thiết bị, token hoặc workload đã bị chiếm quyền. Một bằng chứng hợp lệ có thể đang được sử dụng bởi bên không mong muốn.

Giả định này dẫn đến các lựa chọn thiết kế như giới hạn phạm vi token, kiểm tra hành động tại tài nguyên, phân tách đặc quyền, ghi nhận hành vi và chuẩn bị khả năng thu hồi truy cập.

Mục tiêu không phải phát hiện được mọi cuộc tấn công trước khi chúng bắt đầu. Mục tiêu là giảm cơ hội lạm dụng, hạn chế phạm vi ảnh hưởng và có khả năng ứng phó khi bằng chứng hoặc điều kiện thay đổi.

## 3. Tách bốn câu hỏi thường bị gộp làm một

| Câu hỏi | Chức năng trong IAM | Ví dụ |
| --- | --- | --- |
| Chủ thể là ai? | Xác thực danh tính | Kiểm tra phiên đăng nhập của Mai |
| Chủ thể được làm gì? | Phân quyền | Mai được đọc hóa đơn của đơn vị mình |
| Quyền đó có được dùng ở lần truy cập này không? | Đánh giá chính sách và ngữ cảnh | Tài khoản còn hoạt động, phiên đáp ứng yêu cầu, đúng phạm vi dữ liệu |
| Điều kiện còn đúng trong quá trình sử dụng không? | Quản lý phiên và đánh giá lại | Thu hồi quyền khi Mai chuyển vị trí hoặc khi phát hiện sự cố |

Nhầm lẫn các câu hỏi này thường tạo ra lỗ hổng:

- “Token hợp lệ” bị hiểu thành “được truy cập mọi API”.
- “Đã MFA” bị hiểu thành “được phê duyệt mọi giao dịch”.
- “Đi từ mạng nội bộ” bị hiểu thành “không cần kiểm tra quyền”.
- “Có vai trò kế toán” bị hiểu thành “được xem mọi dữ liệu tài chính của mọi đơn vị”.

RBAC giúp biểu diễn quyền theo vai trò. ABAC có thể thêm điều kiện về chủ thể, tài nguyên và môi trường. Việc dùng RBAC hay ABAC không tự tạo ra Zero Trust; điều quyết định là các chính sách có phản ánh đúng ranh giới truy cập và được thực thi đầy đủ hay không.

## 4. Danh tính và ngữ cảnh phải đến từ nguồn đáng tin cậy

Một quyết định IAM có thể dựa trên nhiều loại tín hiệu, nhưng chúng không có cùng ý nghĩa hoặc độ tin cậy.

| Tín hiệu | Có thể hỗ trợ đánh giá điều gì? | Giới hạn cần hiểu |
| --- | --- | --- |
| Bằng chứng xác thực | Chủ thể kiểm soát phương thức xác thực theo cơ chế đã thiết kế | Không tự chứng minh quyền nghiệp vụ hoặc thiết bị không bị xâm nhập |
| Trạng thái tài khoản | Danh tính còn được phép hoạt động | Bản sao hoặc cache có thể chưa phản ánh thay đổi mới nhất |
| Vai trò, nhóm, thuộc tính | Phạm vi quyền được cấp | Có thể sai hoặc dư thừa nếu vòng đời quyền không được quản lý |
| Trạng thái thiết bị | Thiết bị có đáp ứng các điều kiện quản lý đã định nghĩa không | Không phải bảo đảm tuyệt đối rằng thiết bị an toàn |
| Vị trí mạng hoặc địa chỉ nguồn | Một yếu tố ngữ cảnh hoặc dấu hiệu bất thường | Không thay thế danh tính và quyền truy cập |
| Hành vi và sự kiện rủi ro | Có dấu hiệu cần đánh giá thêm không | Tín hiệu có thể thiếu, chậm hoặc có cảnh báo nhầm |
| Mức nhạy cảm của tài nguyên | Cần mức kiểm soát truy cập nào | Phụ thuộc dữ liệu phân loại được quản lý đúng |

Nếu client tự gửi `deviceCompliant=true`, hệ thống không thể chỉ tin giá trị đó. Thuộc tính thiết bị phải được xác lập qua nguồn và cơ chế mà tổ chức chấp nhận, rồi liên kết đúng với ngữ cảnh đang đánh giá.

Tương tự, một ứng dụng phía sau gateway chỉ nên sử dụng thông tin danh tính do gateway chuyển tiếp khi đường truyền, nguồn gửi và khả năng giả mạo header đã được kiểm soát. Nếu người gọi có thể bỏ qua gateway và gửi header giống hệt, ranh giới tin cậy chưa được bảo vệ.

Thiếu tín hiệu bắt buộc không nên bị diễn giải thành “điều kiện đã đạt”. Chính sách phải định nghĩa rõ trường hợp thiếu, lỗi hoặc quá cũ: từ chối, yêu cầu xác minh thêm hoặc chỉ cho phép một phạm vi hạn chế đã được thiết kế trước.

## 5. Một luồng truy cập theo nguyên tắc Zero Trust

Ví dụ sau xét hành động đọc hóa đơn trong một ứng dụng doanh nghiệp:

```text
Mai hoặc workload gửi yêu cầu
                |
                v
Kiểm tra bằng chứng xác thực và xác lập chủ thể
                |
                v
Xác định hành động, tài nguyên và phạm vi dữ liệu
                |
                v
Đọc quyền và tín hiệu ngữ cảnh từ nguồn tin cậy
                |
                v
Đánh giá chính sách
       |                    |
       v                    v
    Cho phép          Từ chối / xác minh thêm
       |
       v
Thực thi đúng phạm vi + ghi kết quả
       |
       v
Đánh giá lại khi có yêu cầu hoặc thay đổi liên quan
```

Một quyết định cho phép cần được thực thi tại điểm bảo vệ tài nguyên. Thành phần ra quyết định có thể tách khỏi thành phần chặn hoặc cho request đi qua, nhưng cả hai phải phối hợp để hành động thực tế không vượt quyết định đã đưa ra.

Không đủ nếu ứng dụng chỉ ẩn nút “Xuất dữ liệu” trên giao diện. API xuất dữ liệu vẫn phải kiểm tra quyền. Cũng không đủ nếu gateway chỉ xác thực rồi mọi service phía sau đều mặc định cho phép.

Quyền truy cập một ứng dụng không nhất thiết bao gồm quyền với mọi bản ghi trong ứng dụng đó. Với hệ thống nhiều tenant hoặc nhiều đơn vị, phạm vi tenant, đơn vị, chủ sở hữu và quan hệ với tài nguyên vẫn phải được đánh giá ở nơi phù hợp.

## 6. Ví dụ chính sách đọc và phê duyệt hóa đơn

Mai có vai trò `invoice-reviewer` tại đơn vị `branch-A`. Tổ chức muốn cho Mai đọc hóa đơn trong đơn vị đó, nhưng việc phê duyệt còn phải tuân theo giới hạn nghiệp vụ và quy tắc phân tách nhiệm vụ.

Mã giả dưới đây minh họa các lớp kiểm tra. Nó không phải cấu hình của một sản phẩm cụ thể:

```text
evaluate(subject, action, invoice, context):
    if not subject.authenticated:
        return DENY("AUTHENTICATION_REQUIRED")

    if not subject.active:
        return DENY("SUBJECT_INACTIVE")

    if not trustedContextIsFreshEnough(context):
        return DENY("REQUIRED_CONTEXT_UNAVAILABLE")

    if not hasActiveRole(subject, "invoice-reviewer", invoice.branch):
        return DENY("ROLE_OR_SCOPE_MISMATCH")

    if action == "invoice.read":
        return ALLOW

    if action == "invoice.approve":
        if invoice.createdBy == subject.id:
            return DENY("SELF_APPROVAL_FORBIDDEN")

        if not withinApprovalLimit(subject, invoice):
            return DENY("APPROVAL_LIMIT_EXCEEDED")

        if not context.meetsSensitiveActionAuthenticationPolicy:
            return STEP_UP_REQUIRED

        return ALLOW

    return DENY("ACTION_NOT_GRANTED")
```

`STEP_UP_REQUIRED` là kết quả trung gian: hệ thống chưa thực hiện hành động và cần hoàn tất bước xác thực bổ sung phù hợp trước khi đánh giá lại. Nó không phải một dạng cho phép có điều kiện mà ứng dụng có thể bỏ qua.

Các thuộc tính như đơn vị của hóa đơn, người tạo và hạn mức phải được lấy từ dữ liệu đáng tin cậy phía server. Vai trò có hiệu lực cũng phải được tra cứu hoặc xác minh theo cơ chế quyền của hệ thống. Không lấy những thông tin này trực tiếp từ body do client tùy ý khai báo.

MFA bổ sung có thể tăng độ chắc chắn về việc xác thực. Nó không biến một người thiếu vai trò thành người có vai trò, không mở rộng hạn mức và không vô hiệu hóa quy tắc cấm tự phê duyệt.

Ví dụ cũng cho thấy không nhất thiết phải yêu cầu cùng mức kiểm soát cho mọi hành động. Đọc một bản ghi và phê duyệt một khoản thanh toán có thể có mức rủi ro khác nhau, nên điều kiện truy cập được thiết kế tương ứng.

## 7. “Liên tục xác minh” không phải liên tục nhập lại mật khẩu

Nguyên tắc đánh giá lại không yêu cầu người dùng nhập mật khẩu hoặc làm MFA trước từng lần gọi API. Hệ thống có thể sử dụng phiên, token, trạng thái quyền, tín hiệu ngữ cảnh và các sự kiện để đưa ra quyết định theo yêu cầu bảo vệ tài nguyên.

Cần phân biệt:

- **Kiểm tra mỗi yêu cầu được bảo vệ:** xác định request có bằng chứng và quyền phù hợp với hành động hiện tại hay không.
- **Xác thực lại:** yêu cầu chủ thể chứng minh lại danh tính theo điều kiện đã định nghĩa.
- **Đánh giá lại phiên:** xem phiên còn được tiếp tục, cần hạn chế hay phải kết thúc sau một thay đổi.
- **Thu hồi quyền:** loại bỏ một quyền hoặc quan hệ cấp quyền; hiệu lực thực tế còn phụ thuộc cách hệ thống kiểm tra và lưu trạng thái.

Các sự kiện có thể dẫn đến đánh giá lại gồm tài khoản bị vô hiệu hóa, vai trò bị thu hồi, thiết bị không còn đáp ứng điều kiện, xuất hiện dấu hiệu chiếm phiên hoặc yêu cầu thực hiện hành động nhạy cảm hơn.

Không nên giả định khóa tài khoản sẽ làm mọi access token đã phát hành mất hiệu lực tức thì. Một token tự chứa có thể tiếp tục được chấp nhận trong thời gian còn hạn nếu bên nhận chỉ kiểm tra token và không có cơ chế cập nhật trạng thái bổ sung.

Thiết kế cần xác định yêu cầu về độ trễ thu hồi rồi lựa chọn cách đáp ứng: thời hạn token phù hợp, kiểm tra trạng thái, vô hiệu hóa phiên, cập nhật chính sách hoặc cơ chế phản ứng với sự kiện mà hệ thống hỗ trợ. Không có một thời hạn token duy nhất phù hợp cho mọi tài nguyên.

Cache quyết định cũng phải được giới hạn và vô hiệu hóa phù hợp. Nếu cache giữ một kết quả cho phép quá lâu sau khi quyền thay đổi, việc đánh giá lại trên lý thuyết sẽ không đạt hiệu quả trong thực tế.

## 8. Áp dụng cho danh tính con người và workload

### 8.1. Người dùng và tài khoản đặc quyền

Đối với người dùng, cần quản lý nguồn tạo danh tính, xác thực, phương thức khôi phục, membership, quyền và phiên. Một tài khoản không còn thuộc tổ chức nhưng vẫn hoạt động là đầu vào sai cho mọi chính sách phía sau.

Đối với quản trị viên, quyền càng nhạy cảm thì phạm vi, thời gian sử dụng và điều kiện phiên càng cần rõ ràng. Tài khoản đặc quyền không nên trở thành tài khoản dùng cho mọi hoạt động hằng ngày.

Nhân viên, đối tác và khách mời đều cần vòng đời truy cập. Một tài khoản khách đã được mời hợp lệ không nên giữ quyền vô thời hạn nếu quan hệ cộng tác đã kết thúc.

### 8.2. Dịch vụ, ứng dụng và tác vụ tự động

Workload cũng phải có danh tính và quyền riêng. Việc hai service ở cùng mạng hoặc cùng cụm triển khai không có nghĩa chúng được phép gọi mọi API của nhau.

Danh tính workload nên gắn với chức năng và phạm vi cần thiết. Ví dụ, dịch vụ tạo báo cáo có thể đọc dữ liệu đã được cho phép nhưng không có quyền sửa chính sách IAM hoặc quản lý tài khoản.

Một kết nối được xác thực bằng chứng thư có thể chứng minh danh tính của bên tham gia theo cơ chế đã thiết kế. Nó không tự xác định đầy đủ những thao tác nghiệp vụ mà bên đó được phép thực hiện. Xác thực kênh và phân quyền tài nguyên vẫn là hai trách nhiệm khác nhau.

Khi một service hành động thay người dùng, hệ thống còn phải phân biệt người dùng yêu cầu và workload thực thi. Quyền rộng của service không nên tự động cho phép người dùng yêu cầu bất kỳ hành động nào thông qua service đó. Chính sách cần thể hiện rõ mô hình ủy quyền và phạm vi tài nguyên.

Không dùng mật khẩu của tài khoản admin cá nhân làm danh tính chung cho tác vụ tự động. Cách làm này trộn quyền, trách nhiệm kiểm toán và vòng đời của con người với workload.

## 9. Vai trò của MFA, SSO và OAuth/OIDC

Các cơ chế IAM quen thuộc hỗ trợ Zero Trust nhưng không thay thế toàn bộ nguyên tắc:

| Cơ chế | Đóng góp | Điều vẫn cần kiểm soát |
| --- | --- | --- |
| MFA | Tăng độ chắc chắn của xác thực so với chỉ dựa vào một phương thức | Khôi phục, chiếm phiên, quyền nghiệp vụ và các giới hạn của phương thức MFA |
| SSO | Tập trung trải nghiệm đăng nhập và một phần chính sách phiên | Mỗi ứng dụng vẫn phải thực thi quyền của mình |
| OIDC | Hỗ trợ xác thực và truyền thông tin danh tính giữa các bên theo giao thức | Kiểm tra token, cấu hình tin cậy và liên kết tài khoản đúng |
| OAuth | Hỗ trợ cấp quyền truy cập được ủy quyền cho client | Scope, audience, tài nguyên, chính sách nghiệp vụ và vòng đời token |
| RBAC/ABAC | Biểu diễn quyền và điều kiện phân quyền | Chất lượng dữ liệu quyền, phạm vi và vị trí thực thi |
| Quản lý truy cập đặc quyền | Kiểm soát việc sử dụng quyền nhạy cảm | Vòng đời quyền, phạm vi tác vụ, phiên và kiểm toán thực tế |

Không nên kết luận một hệ thống đã đáp ứng Zero Trust chỉ vì bật MFA, triển khai SSO hoặc chuyển toàn bộ ứng dụng sang một giao thức đăng nhập. Một phiên SSO bị chiếm hoặc một service có quyền quá rộng vẫn có thể gây ảnh hưởng lớn nếu thiếu kiểm soát tại tài nguyên.

Zero Trust cũng không làm các lớp bảo vệ mạng mất vai trò. Phân đoạn mạng và kiểm soát kết nối vẫn giúp giảm bề mặt tiếp cận; chúng được kết hợp với xác thực và phân quyền thay vì được dùng làm bằng chứng duy nhất để cho phép truy cập.

## 10. Vận hành khi điều kiện hoặc thành phần gặp lỗi

Việc đánh giá quyền phụ thuộc vào các nguồn dữ liệu và thành phần thực thi. Vì vậy, cần thiết kế cả trường hợp một nguồn ngữ cảnh chậm cập nhật, không truy cập được hoặc trả lỗi.

Với hành động cần điều kiện bắt buộc, không thể xác minh điều kiện không được tự động biến thành cho phép. Ví dụ, hệ thống không thể lấy trạng thái tài khoản không có nghĩa tài khoản được coi là đang hoạt động.

Chính sách phục hồi có thể khác nhau theo tài nguyên: từ chối một thay đổi đặc quyền, duy trì một phạm vi đọc hạn chế đã được thiết kế hoặc sử dụng trạng thái đã xác minh trong một khoảng hiệu lực cho phép. Mọi trường hợp phải có giới hạn rõ, khả năng quan sát và căn cứ rủi ro; không âm thầm bỏ qua phân quyền khi dịch vụ chính sách lỗi.

Truy cập khẩn cấp cũng cần được thiết kế trước: ai được dùng, trong phạm vi nào, cách xác thực, cách ghi nhận và cách rà soát sau sự kiện. Nó không phải một nhánh bỏ kiểm tra dành cho mọi người dùng khi đăng nhập bình thường gặp khó khăn.

Nhật ký cần giúp liên kết chủ thể, phiên, hành động, tài nguyên, phạm vi, quyết định và kết quả. Không ghi mật khẩu, mã MFA hoặc token bí mật. Quyền đọc dữ liệu giám sát và thời gian lưu giữ cũng phải được quản lý phù hợp.

## 11. Những cách hiểu sai thường gặp

| Cách hiểu sai | Vì sao chưa đúng? | Cách nhìn phù hợp |
| --- | --- | --- |
| Trong mạng công ty thì được tin cậy | Mạng có thể chứa thiết bị hoặc workload đã bị chiếm quyền | Mạng là ngữ cảnh, truy cập vẫn cần danh tính và quyền |
| MFA thành công là đủ | Xác thực không xác lập toàn bộ quyền nghiệp vụ | Đánh giá quyền và điều kiện riêng cho tài nguyên, hành động |
| Zero Trust là một sản phẩm | Một công cụ không thể tự sửa mọi quan hệ quyền và đường truy cập | Là nguyên tắc được triển khai qua nhiều thành phần và quy trình |
| Phải MFA ở mọi API call | Gây nhầm lẫn giữa kiểm tra request và xác thực tương tác | Sử dụng phiên, bằng chứng và đánh giá lại theo chính sách |
| Token hợp lệ được phép gọi mọi service | Token có phạm vi và bên nhận dự kiến | Xác minh bằng chứng rồi đánh giá quyền tại tài nguyên |
| Xóa nhóm là thu hồi tức thì mọi nơi | Token, phiên và cache có thể còn giữ trạng thái cũ | Thiết kế và kiểm chứng thời gian thu hồi thực tế |
| Điểm rủi ro thay thế mọi quyền | Tín hiệu rủi ro không tạo ra quyền nghiệp vụ còn thiếu | Kết hợp rủi ro với quyền và các điều kiện bắt buộc |
| Chỉ cần bảo vệ người dùng | Workload cũng có thể bị lạm dụng hoặc mang quyền dư thừa | Quản lý cả danh tính con người và danh tính máy |

## 12. Bắt đầu từ một luồng truy cập cụ thể

Một cách triển khai có thể kiểm chứng là chọn một tài nguyên quan trọng và một luồng công việc, thay vì chỉ thay đổi khẩu hiệu đăng nhập của toàn tổ chức.

Trước tiên xác định chủ thể, nguồn danh tính, hành động, dữ liệu đích và nơi thực thi quyền. Sau đó xác định quyền tối thiểu cùng những điều kiện bắt buộc cho luồng đó. Cần làm rõ nguồn dữ liệu, độ mới chấp nhận được và hành vi khi thiếu bằng chứng.

Tiếp theo, kiểm chứng cả đường cho phép lẫn đường từ chối:

- Chủ thể hợp lệ và đủ quyền có thể hoàn thành công việc đúng phạm vi.
- Đăng nhập hợp lệ nhưng thiếu quyền vẫn bị từ chối.
- Đổi ID tài nguyên, đơn vị hoặc tenant không mở rộng được phạm vi.
- Thiếu tín hiệu bắt buộc không dẫn đến cấp quyền ngoài thiết kế.
- Thu hồi tài khoản hoặc quyền có hiệu lực theo yêu cầu đã xác định.
- Hành động đặc quyền và truy cập workload có thể được truy vết.
- Lỗi ở một thành phần không tạo ra đường bỏ kiểm tra không được kiểm soát.

Nguyên tắc danh tính trong Zero Trust được thể hiện qua những quyết định này: xác minh đủ bằng chứng, cấp đúng quyền cho đúng tài nguyên, thực thi giới hạn và điều chỉnh truy cập khi trạng thái không còn phù hợp.
