# Access certification

## 1. Access certification là gì?

**Access certification** là quy trình xác nhận có trách nhiệm rằng những quyền truy cập đang tồn tại vẫn cần thiết, phù hợp với công việc hiện tại và tuân theo chính sách của tổ chức. Người được giao thẩm quyền xem xét bằng chứng rồi quyết định giữ quyền, thu hồi, điều chỉnh hoặc xử lý theo một ngoại lệ được quản lý.

Trong identity governance, câu hỏi không chỉ là “ai có quyền gì?” mà còn là:

- Quyền đó phục vụ nhu cầu nghiệp vụ nào ở thời điểm hiện tại?
- Ai chịu trách nhiệm xác nhận nhu cầu và hiểu tác động của quyền?
- Người dùng nhận quyền qua nguồn cấp nào?
- Nếu quyền không còn phù hợp, ai thực hiện thu hồi và bằng chứng hoàn tất là gì?
- Khi chưa đủ thông tin, vấn đề được chuyển cho ai và phải xử lý trước thời điểm nào?

Ví dụ, một nhân viên được cấp quyền duyệt hoàn tiền khi tham gia dự án sáu tháng. Dự án đã kết thúc nhưng quyền vẫn còn. Đăng nhập bằng MFA và dùng SSO không tự phát hiện rằng nhu cầu nghiệp vụ đã hết. Access certification cung cấp một điểm kiểm soát để rà soát và xử lý loại quyền tồn đọng này.

Đây là hoạt động quản trị quyền đang tồn tại, gắn với nguyên tắc ít quyền nhất và vòng đời danh tính. Nó không thay thế kiểm soát cấp quyền ban đầu, cập nhật quyền khi chuyển việc hoặc thu hồi ngay khi nghỉ việc.

## 2. Phân biệt review, attestation và certification

Các sản phẩm có thể dùng thuật ngữ khác nhau, nhưng có thể phân biệt về mặt chức năng như sau:

| Khái niệm | Trọng tâm | Kết quả cần có |
|---|---|---|
| Access review | Xem xét quyền cùng thông tin liên quan | Nhận định về tính phù hợp của quyền |
| Attestation | Người có trách nhiệm đưa ra xác nhận | Người xác nhận, thời điểm, đối tượng và nội dung xác nhận |
| Access certification | Tổ chức việc rà soát, quyết định, xử lý và lưu bằng chứng | Quyết định có trách nhiệm cùng kết quả thực thi và các vấn đề còn mở |
| Access request approval | Quyết định trước khi cấp hoặc thay đổi quyền | Cho phép hay từ chối yêu cầu mới |
| Access audit | Đánh giá bằng chứng về thiết kế hoặc vận hành kiểm soát | Phát hiện, nhận xét và yêu cầu khắc phục nếu có |

Không nên hiểu một lần nhấn “certify” là bằng chứng hệ thống đích đã thay đổi. Đó mới là bằng chứng về quyết định của người rà soát.

Tương tự, báo cáo hoàn tất chiến dịch không tự chứng minh mọi quyền đều phù hợp. Chất lượng còn phụ thuộc độ đầy đủ của dữ liệu, năng lực người rà soát, cách xử lý ngoại lệ và khả năng thực thi quyết định.

Trong bài này, “chứng nhận quyền” có nghĩa là xác nhận tính phù hợp của quyền truy cập. Nó không liên quan đến cấp chứng thư số cho giao thức TLS hoặc xác thực bằng certificate.

## 3. Đơn vị được chứng nhận phải đủ rõ

Một mục rà soát không nên chỉ chứa tên nhân viên và tên ứng dụng. Cần biết chính xác quyền nào, trên phạm vi nào và thông qua đường cấp nào.

Một mô hình khái niệm có thể gồm:

```text
Danh tính nguồn
    → Tài khoản tại hệ thống đích
    → Đường cấp quyền
    → Quyền hoặc vai trò
    → Tài nguyên và phạm vi tác động
    → Điều kiện, thời hạn và chính sách liên quan
```

Ví dụ:

```text
Danh tính: employee-284
Tài khoản đích: account-762
Ứng dụng: hệ thống quản lý hoàn tiền
Quyền: refund-approve
Phạm vi: đơn vị kinh doanh miền Nam
Nguồn cấp: nhóm refund-supervisors
Nguồn gán nhóm: vai trò business-role-17
Hiệu lực: chưa có ngày hết hạn
```

Quyền `refund-approve` trong một đơn vị kinh doanh không nhất thiết tương đương quyền cùng tên trên toàn tổ chức. Tên hiển thị giống nhau cũng không chứng minh hai quyền là một.

### Quyền gán và quyền có hiệu lực

**Quyền gán** là các quan hệ nhìn thấy trong dữ liệu quản trị: thành viên nhóm, vai trò được gán hoặc quyền trực tiếp.

**Quyền có hiệu lực** là khả năng truy cập thực tế sau khi xét đường kế thừa, nhóm lồng nhau, phạm vi tài nguyên, điều kiện chính sách và cơ chế thực thi của ứng dụng.

Một người có thể nhận cùng quyền qua nhiều đường:

```text
Người dùng → nhóm Finance → vai trò ReportReader
Người dùng → nhóm Project-A → vai trò ReportReader
Người dùng → gán trực tiếp vai trò ReportReader
```

Xóa một đường cấp không bảo đảm mất quyền nếu hai đường còn lại vẫn tồn tại. Do đó, báo cáo cần nói rõ đang chứng nhận một quan hệ gán, một vai trò nghiệp vụ hay khả năng truy cập có hiệu lực.

Với chính sách dựa trên thuộc tính, quyền có thể thay đổi theo thuộc tính và ngữ cảnh. Không nên trình bày một danh sách nhóm tĩnh như toàn bộ quyền thực tế nếu hệ thống còn áp dụng các điều kiện khác. Phạm vi có thể quan sát và giới hạn dữ liệu phải được nêu rõ.

### Danh tính phi con người

Tài khoản dịch vụ và danh tính workload cũng cần có chủ sở hữu hoặc người bảo trợ chịu trách nhiệm. Thông tin phục vụ rà soát thường gồm mục đích, ứng dụng sử dụng, môi trường, quyền được cấp và vòng đời dự kiến.

Việc không có người quản lý nhân sự cho một tài khoản dịch vụ không phải lý do bỏ nó khỏi quản trị. Ngược lại, tài khoản không có chủ sở hữu là một phát hiện cần xử lý. Cũng không nên vô hiệu hóa hàng loạt tài khoản workload chỉ vì không thấy lượt đăng nhập tương tác.

## 4. Dữ liệu đầu vào quyết định chất lượng chiến dịch

Người rà soát chỉ có thể đưa ra quyết định tốt khi dữ liệu đủ rõ và đủ mới.

| Nhóm thông tin | Mục đích |
|---|---|
| Danh tính và trạng thái vòng đời | Biết chủ thể đang làm việc, chuyển vai trò, tạm ngưng hay đã nghỉ |
| Tài khoản đích và liên kết danh tính | Tránh chứng nhận nhầm tài khoản hoặc nhầm người |
| Vai trò công việc, bộ phận và người quản lý | Hiểu nhu cầu hiện tại |
| Mô tả quyền và phạm vi tài nguyên | Hiểu hành động mà quyền cho phép |
| Nguồn cấp quyền và đường kế thừa | Biết phải thay đổi ở đâu để quyết định có hiệu lực |
| Nguồn phê duyệt và lý do cấp | Đối chiếu nhu cầu ban đầu với hoàn cảnh hiện tại |
| Thời hạn quyền hoặc ngoại lệ | Phát hiện quyền đã hết điều kiện tồn tại |
| Dữ liệu sử dụng và giới hạn quan sát | Bổ sung bằng chứng về nhu cầu, không thay thế đánh giá nghiệp vụ |
| Rủi ro, xung đột nhiệm vụ và mức nhạy cảm | Ưu tiên mức độ xem xét phù hợp |

Nếu tên quyền là một mã khó hiểu như `APP_ROLE_019`, cần có diễn giải nghiệp vụ và mô tả tác động. Người quản lý không thể chứng nhận có ý nghĩa nếu chỉ được xem danh sách mã kỹ thuật.

### Kiểm tra độ đầy đủ trước khi mở chiến dịch

Cần biết hệ thống nào đã được thu thập, nguồn nào còn thiếu, lần đồng bộ gần nhất là khi nào và có lỗi connector hay không.

Một nguồn không trả về quyền vì mất quyền đọc không đồng nghĩa người dùng không có quyền. Tương tự, người dùng không xuất hiện trong kết quả đồng bộ lỗi không có nghĩa họ đã nghỉ việc.

Các mục thiếu dữ liệu quan trọng phải được bổ sung, chuyển chủ sở hữu hoặc đánh dấu chưa đủ điều kiện kết luận. Không chuyển chúng thành “giữ quyền” chỉ để tăng tỷ lệ hoàn tất.

### Cách dùng dữ liệu sử dụng

“Không thấy sử dụng trong khoảng quan sát” là tín hiệu để hỏi thêm, không phải bằng chứng chắc chắn quyền vô ích. Quyền có thể phục vụ công việc theo quý, xử lý khẩn cấp hoặc một tác vụ tự động không nằm trong nguồn log đang xem.

Ngược lại, quyền được sử dụng thường xuyên vẫn có thể không được phép hoặc đã hết nhu cầu hợp lệ. Hoạt động sử dụng mô tả hành vi; nó không tự tạo ra thẩm quyền.

## 5. Ai có quyền chứng nhận?

Việc giao đúng người quan trọng hơn số lượng mục được duyệt.

| Vai trò | Trách nhiệm điển hình |
|---|---|
| Người quản lý trực tiếp | Xác nhận nhân sự, công việc và nhu cầu của thành viên trong nhóm |
| Chủ ứng dụng hoặc chủ tài nguyên | Giải thích ý nghĩa quyền, phạm vi và tác động trong hệ thống đích |
| Chủ vai trò nghiệp vụ | Xác nhận thành phần vai trò còn phù hợp với chức năng công việc |
| Chủ quyền hoặc chủ dữ liệu | Đánh giá điều kiện truy cập tài nguyên nhạy cảm thuộc trách nhiệm của mình |
| Đội IAM/IGA | Chuẩn bị dữ liệu, điều phối chiến dịch, theo dõi và thực thi thay đổi theo thẩm quyền |
| Đội bảo mật hoặc kiểm soát | Hỗ trợ đánh giá rủi ro, xung đột và ngoại lệ |
| Người bảo trợ danh tính workload | Xác nhận mục đích vận hành, hệ thống sử dụng và nhu cầu quyền của workload |

Một quyền nhạy cảm có thể cần nhiều góc nhìn. Người quản lý biết nhân viên đang làm công việc nào; chủ ứng dụng biết quyền đó thực sự cho phép làm gì. Chính sách có thể yêu cầu cả hai xem xét hoặc chuyển mục cho người phù hợp.

### Xung đột lợi ích và ủy quyền

Cần có quy tắc về tự chứng nhận quyền của chính mình, rà soát quyền của người có quan hệ lợi ích và người thay thế khi reviewer vắng mặt.

Nếu cho phép ủy quyền, cần xác định phạm vi, thời hạn, người nhận và dấu vết ủy quyền. Việc chuyển người rà soát không được làm mất lịch sử quyết định.

Chỉ việc gán mục cho một reviewer không chứng minh người đó hiểu quyền hoặc có thẩm quyền chấp nhận ngoại lệ. Hệ thống điều phối phải hỗ trợ chuyển giao và chuyển cấp đúng trách nhiệm.

## 6. Thiết kế một chiến dịch access certification

Một chiến dịch nên được định nghĩa trước khi gửi thông báo cho reviewer.

### Phạm vi và thời điểm

Phạm vi có thể theo ứng dụng, bộ phận, loại danh tính, vai trò hoặc mức độ nhạy cảm. Cần xác định cả các phần bị loại trừ và lý do, tránh tạo ấn tượng chiến dịch bao phủ toàn bộ IAM trong khi chỉ có một số ứng dụng được thu thập.

Rà soát có thể theo lịch hoặc được kích hoạt bởi sự kiện:

- Chuyển bộ phận hoặc thay đổi chức năng công việc.
- Thay đổi người quản lý hoặc chủ ứng dụng.
- Kết thúc dự án và hợp đồng.
- Phát hiện quyền nhạy cảm được gán ngoài quy trình.
- Thay đổi lớn trong vai trò nghiệp vụ hoặc cấu trúc quyền.

Tần suất phải dựa trên rủi ro và chính sách của tổ chức. Quyền đặc quyền, tài nguyên nhạy cảm và quyền thông thường không nhất thiết có cùng chu kỳ. Một đợt rà soát định kỳ không phải lý do trì hoãn thu hồi bắt buộc khi nghỉ việc.

### Các quyết định cấu hình cần rõ

Trước khi bắt đầu, cần xác định:

1. Dữ liệu gốc và mốc snapshot.
2. Đơn vị rà soát và cách xử lý nhiều đường cấp quyền.
3. Reviewer chính, người thay thế và tuyến chuyển cấp.
4. Loại quyết định được phép và bằng chứng bắt buộc.
5. Thời hạn ra quyết định và thời hạn thực thi sau quyết định.
6. Quy tắc khi không phản hồi hoặc thiếu dữ liệu.
7. Điều kiện ngoại lệ và người có thẩm quyền chấp nhận.
8. Cách xử lý thay đổi xảy ra trong thời gian chiến dịch.
9. Tiêu chí đóng chiến dịch và lưu bằng chứng.

Thời hạn ra quyết định khác thời hạn thực thi. Reviewer có thể quyết định thu hồi hôm nay nhưng connector chưa loại bỏ quyền. Chiến dịch cần thể hiện cả hai mốc.

### Snapshot và thay đổi đang diễn ra

Một snapshot giúp cố định dữ liệu được đưa ra rà soát và chứng minh reviewer đã nhìn thấy gì. Nhưng dữ liệu IAM không dừng thay đổi trong suốt chiến dịch.

Cần có cơ chế phát hiện những mục đã thay đổi: người dùng nghỉ việc, vai trò được thay định nghĩa, nguồn cấp bị thay thế hoặc quyền mới được cấp sau snapshot.

Các lựa chọn có thể gồm đưa mục thay đổi sang rà soát bổ sung, yêu cầu reviewer xác nhận lại hoặc đánh dấu quyết định cũ đã bị thay thế. Cách chọn phải rõ ngay từ đầu và phù hợp với mức độ rủi ro.

Không áp dụng mù quyết định trên bản snapshot cũ lên một quan hệ quyền khác ở thời điểm thực thi.

## 7. Reviewer cần quyết định điều gì?

Một quyết định có ý nghĩa gắn với đúng đối tượng, đúng quyền, đúng phạm vi và lý do.

| Quyết định | Ý nghĩa | Công việc tiếp theo |
|---|---|---|
| Giữ quyền | Nhu cầu hiện tại phù hợp chính sách | Lưu xác nhận, lý do theo yêu cầu và mốc rà soát tiếp theo |
| Thu hồi | Quyền không còn cần hoặc không phù hợp | Tạo hành động thu hồi và xác minh tại nguồn thực thi |
| Điều chỉnh | Chỉ cần một phần quyền hoặc phạm vi hẹp hơn | Chuyển thành thay đổi cụ thể, đánh giá rủi ro và xác minh kết quả |
| Đề nghị ngoại lệ | Có lý do tiếp tục quyền ngoài điều kiện thông thường | Xin đúng thẩm quyền, giới hạn phạm vi và thời hạn |
| Cần bổ sung thông tin/chuyển giao | Reviewer chưa đủ dữ liệu hoặc không có thẩm quyền | Giữ mục mở, gán chủ sở hữu và hạn xử lý |

Các tên quyết định trên là mô hình minh họa, không phải trạng thái cố định của mọi công cụ.

### Giữ quyền

“Vẫn là nhân viên” không đủ để giữ mọi quyền. Cần xác nhận quan hệ giữa công việc hiện tại và hành động mà quyền cho phép.

Một lý do tốt có thể là: “Cần quyền xem báo cáo tổng hợp của đơn vị A để thực hiện đối soát hằng tháng; không cần quyền sửa dữ liệu.” Lý do này rõ hơn “cần cho công việc” vì mô tả mục đích và giới hạn.

### Thu hồi hoặc điều chỉnh

Quyết định phải đủ cụ thể để thực hiện. “Giảm quyền của tài khoản này” chưa cho biết phải bỏ vai trò nào, giữ quyền nào và thay đổi ở cấp nhóm hay gán trực tiếp.

Điều chỉnh từ vai trò quản trị sang vai trò chỉ đọc có thể cần thay đổi nhiều quan hệ. Thứ tự thực hiện phải cân nhắc rủi ro dư quyền và gián đoạn nghiệp vụ, thay vì mặc định thêm hết quyền mới trước rồi mới xem xét quyền cũ.

### Không phản hồi

Không phản hồi không phải bằng chứng chấp thuận. Cơ chế xử lý có thể là nhắc hạn, chuyển cấp, gán người thay thế, giữ mục mở hoặc thực hiện hành động mặc định đã được phê duyệt.

Không có một mặc định an toàn cho mọi đối tượng. Giữ nguyên đặc quyền vô thời hạn làm kéo dài rủi ro; thu hồi tự động một tài khoản workload quan trọng mà không đánh giá tác động có thể gây gián đoạn. Chính sách phải xác định hành động, trách nhiệm và cách kiểm soát phù hợp trước khi chiến dịch bắt đầu.

### Tránh duyệt hàng loạt thiếu căn cứ

Chức năng duyệt nhiều mục giúp tiết kiệm thao tác nhưng có thể dẫn đến “rubber stamping”: reviewer xác nhận cả danh sách mà không hiểu từng loại quyền.

Cách hạn chế gồm nhóm các quyền có ý nghĩa nghiệp vụ rõ, làm nổi bật quyền nhạy cảm và thay đổi mới, yêu cầu lý do cho trường hợp cần thiết và chuyển quyền kỹ thuật cho chủ ứng dụng. Mục tiêu là nâng chất lượng quyết định, không chỉ giảm số lượt nhấn.

## 8. Ngoại lệ phải có vòng đời

Ngoại lệ là quyết định chấp nhận một tình huống có điều kiện, không phải cách đổi tên một quyền không phù hợp thành “đã chứng nhận”.

Một ngoại lệ cần thể hiện ít nhất:

```text
Đối tượng và quyền: ai, quyền gì, tài nguyên nào
Điều kiện thông thường chưa đáp ứng: điều gì đang khác chính sách
Lý do nghiệp vụ: tại sao chưa thể xử lý theo thông lệ
Người có thẩm quyền chấp nhận: ai chịu trách nhiệm
Biện pháp giảm rủi ro: áp dụng gì và ai kiểm tra
Ngày bắt đầu, ngày hết hạn: hiệu lực đến khi nào
Kế hoạch kết thúc: thu hồi hoặc chuyển về phương án chuẩn ra sao
Bằng chứng và lịch sử: quyết định đã dựa trên thông tin nào
```

Ví dụ, một chuyên viên chuyển nhóm vẫn cần quyền hỗ trợ dự án cũ trong thời gian bàn giao. Ngoại lệ có thể giới hạn tài nguyên, cấm thao tác phê duyệt và đặt ngày kết thúc cụ thể.

Khi ngoại lệ hết hạn, hệ thống cần thực thi việc kết thúc hoặc chuyển cấp đúng quy trình. Việc gia hạn phải là một quyết định mới có lý do và thẩm quyền phù hợp, không tự động kéo dài chỉ vì chiến dịch trước đã giữ quyền.

Reviewer chỉ được chứng nhận trong phạm vi quyền hạn. Nếu người quản lý không có quyền chấp nhận rủi ro của một loại đặc quyền, quyết định ngoại lệ phải được chuyển đúng người.

## 9. Từ quyết định đến thực thi: phần dễ bị bỏ sót

Luồng kiểm soát cần được nối liền:

```text
Thu thập và đối sánh
    → Rà soát
    → Quyết định có thẩm quyền
    → Tạo hành động thay đổi
    → Thực thi tại nguồn phù hợp
    → Đọc lại và đối chiếu
    → Lưu bằng chứng, đóng mục
```

Đánh dấu “revoke” trong công cụ IGA không tự xóa quyền tại ứng dụng. Thao tác còn phải đi qua connector, nhóm thư mục, vai trò hoặc quy trình thủ công của chủ ứng dụng.

### Thu hồi ở đúng nguồn

Nếu nhóm được cấp bởi một vai trò nghiệp vụ, việc xóa thành viên nhóm trực tiếp có thể chỉ có hiệu lực tạm thời. Lượt đồng bộ tiếp theo có thể thêm lại người dùng vì vai trò nghiệp vụ vẫn yêu cầu nhóm đó.

Cần xác định nguồn kiểm soát thực sự:

- Gán trực tiếp: loại bỏ quan hệ gán cụ thể.
- Nhóm được quản lý: sửa thành viên nhóm ở nguồn có thẩm quyền.
- Vai trò nghiệp vụ: điều chỉnh gán vai trò hoặc thành phần vai trò theo đúng thẩm quyền.
- Quy tắc tự động: sửa điều kiện đủ quyền hoặc xử lý ngoại lệ được quản lý.
- Nhiều đường cấp: xử lý đủ các đường khiến quyền không phù hợp vẫn có hiệu lực.

Thu hồi một quan hệ không phải lý do sửa định nghĩa vai trò dùng chung cho mọi người. Nếu phát hiện vai trò thiết kế sai, cần mở thay đổi riêng và đánh giá tác động đến các thành viên khác.

### Xác minh hậu điều kiện

Sau thực thi, cần đọc lại trạng thái ở nguồn phù hợp và đối chiếu với quyết định. Nếu quan sát chỉ chứng minh quan hệ nhóm đã bị xóa, bằng chứng nên nói đúng điều đó.

Quyền truy cập đang dùng có thể còn chịu ảnh hưởng của phiên, token, bộ nhớ đệm hoặc cơ chế đồng bộ của ứng dụng. Với quyền nhạy cảm, cần đánh giá liệu quyết định còn đòi hỏi kết thúc phiên hoặc xử lý các phương thức truy cập khác trong phạm vi chính sách.

Không mô tả “không còn mọi truy cập” nếu bằng chứng mới chỉ là “đã xóa một dòng gán vai trò”.

### Lỗi hoặc kết quả chưa xác định

Nếu lệnh thu hồi timeout, không biết chắc quyền đã bị xóa hay chưa. Cần kiểm tra đích, dùng thao tác có cơ chế chống lặp phù hợp và theo dõi hành động đến khi xác minh được kết quả.

Mục thu hồi thất bại cần chủ sở hữu, mức ưu tiên và tuyến chuyển cấp. Không đổi về “giữ quyền” để làm sạch dashboard. Một chiến dịch có thể hoàn tất phần quyết định nhưng vẫn còn việc khắc phục mở; báo cáo phải thể hiện sự khác biệt này.

## 10. Ví dụ: rà soát quyền sau khi chuyển bộ phận

Minh đã chuyển từ nhóm vận hành thanh toán sang nhóm phân tích. Chiến dịch rà soát hệ thống thanh toán ghi nhận các mục sau:

| Mục | Tình trạng và bằng chứng | Quyết định |
|---|---|---|
| Xem báo cáo tổng hợp | Phù hợp công việc phân tích, phạm vi đúng đơn vị | Giữ |
| Tạo lệnh thanh toán | Không còn thuộc nhiệm vụ hiện tại | Thu hồi |
| Phê duyệt thanh toán | Còn do nhóm dự án cũ và một gán trực tiếp | Thu hồi cả các đường cấp liên quan |
| Quản trị cấu hình kết nối | Reviewer không hiểu ý nghĩa, mô tả quyền thiếu | Chuyển chủ ứng dụng, chưa kết luận |
| Đọc dữ liệu bàn giao dự án cũ | Có nhu cầu giới hạn đến ngày kết thúc bàn giao | Đề nghị ngoại lệ có thời hạn theo đúng thẩm quyền |

Người quản lý xác nhận công việc hiện tại. Chủ ứng dụng giải thích quyền kỹ thuật và kiểm tra các đường cấp. Đội IAM điều phối hành động thu hồi theo quyết định.

Khi thực thi, connector xóa được gán trực tiếp quyền phê duyệt nhưng gặp lỗi khi bỏ Minh khỏi nhóm dự án cũ. Trạng thái lúc này là:

```text
Quyết định thu hồi: đã được ghi nhận
Gán trực tiếp: đã xóa và đọc lại thành công
Đường cấp qua nhóm dự án: chưa xử lý xong
Khả năng nhận quyền phê duyệt: còn tồn tại qua nhóm
Mục rà soát: chưa hoàn tất khắc phục
```

Sau khi connector hoạt động lại, nhóm được cập nhật tại nguồn quản lý chính thức, đọc lại xác nhận Minh không còn thuộc nhóm và kiểm tra không còn đường cấp liên quan trong phạm vi thu thập.

Trong thời gian xử lý, nếu Minh nghỉ việc, sự kiện vòng đời mới phải được ưu tiên xử lý theo chính sách thu hồi. Không chờ chiến dịch kết thúc, cũng không áp dụng lại quyết định giữ quyền dựa trên tình trạng nhân sự cũ.

Ví dụ này cho thấy một chứng nhận có thể chứa nhiều phần độc lập: xác nhận nhu cầu, giải quyết thiếu thông tin, quyết định ngoại lệ và kiểm chứng thực thi. Chỉ một cột “approved” không mô tả đủ chúng.

## 11. Bằng chứng và báo cáo cần trả lời được điều gì?

Bằng chứng phải giúp tái dựng một quyết định cụ thể, không chỉ chứng minh ai đã đăng nhập vào công cụ review.

Một hồ sơ có thể liên kết các thông tin sau:

```text
campaignId: cert-2026-project-close
reviewItemId: item-1842
subjectId: employee-284
targetAccountId: account-762
entitlementId: payment-approve
resourceScope: business-unit-south
assignmentPathId: path-92
snapshotRevision: snapshot-37
reviewerId: reviewer-51
decision: REVOKE
decisionReason: Không còn thuộc nhiệm vụ sau khi chuyển bộ phận
remediationId: remediation-620
remediationState: VERIFIED
verificationEvidenceId: evidence-310
```

Đây là ví dụ dữ liệu khái niệm, không phải schema của một công cụ cụ thể. Khi áp dụng thực tế cần có thời điểm, phiên bản, lịch sử và các định danh phù hợp với hệ thống.

Các nhóm bằng chứng cần phân biệt:

- **Bằng chứng phạm vi:** những nguồn, tài khoản và quyền nào đã được đưa vào chiến dịch.
- **Bằng chứng quyết định:** reviewer đã thấy dữ liệu gì, quyết định gì, lúc nào và theo thẩm quyền nào.
- **Bằng chứng thực thi:** hành động nào được gửi, kết quả và đối tượng bị thay đổi.
- **Bằng chứng xác minh:** trạng thái nào đã được quan sát lại, ở nguồn nào và thời điểm nào.
- **Bằng chứng ngoại lệ hoặc tồn đọng:** điều gì chưa đạt, ai sở hữu và hạn xử lý.

Không lưu mật khẩu, token, khóa bí mật hoặc payload nhạy cảm không cần thiết vào hồ sơ. Dữ liệu quyền có thể tiết lộ cấu trúc hệ thống và thông tin nhân sự, nên cần giới hạn người đọc, bảo vệ lịch sử thay đổi và áp dụng thời gian lưu giữ phù hợp chính sách.

Một báo cáo chính xác nên phân biệt “đã ra quyết định”, “đã gửi thay đổi” và “đã xác minh thay đổi”. Nếu còn mục chưa đủ dữ liệu hoặc ngoại lệ còn hiệu lực, phải thể hiện chúng thay vì che trong tỷ lệ hoàn tất chung.

## 12. Đo hiệu quả thay vì chỉ đo số lượt duyệt

Tỷ lệ reviewer phản hồi cao giúp theo dõi tiến độ nhưng chưa đủ phản ánh hiệu quả kiểm soát.

| Chỉ số | Ý nghĩa và giới hạn |
|---|---|
| Mức bao phủ | Những tài khoản, quyền và nguồn thuộc phạm vi dự kiến đã được thu thập đến đâu |
| Tỷ lệ quyết định đúng hạn | Tiến độ xử lý review, chưa chứng minh chất lượng |
| Tỷ lệ thu hồi được xác minh | Quyết định thu hồi đã có bằng chứng đạt hậu điều kiện đến đâu |
| Thời gian từ quyết định đến xác minh | Khoảng rủi ro khi quyền không phù hợp vẫn tồn tại |
| Mục chưa có chủ sở hữu hoặc thiếu mô tả | Chất lượng dữ liệu và trách nhiệm quản trị |
| Ngoại lệ quá hạn | Khả năng kiểm soát vòng đời ngoại lệ |
| Quyền tái xuất hiện sau thu hồi | Dấu hiệu sửa sai nguồn cấp hoặc cơ chế đồng bộ còn mâu thuẫn |
| Quyết định bị trả lại vì thiếu căn cứ | Chất lượng thông tin và khả năng giao đúng reviewer |

Mỗi tỷ lệ cần có mẫu số rõ. Ví dụ, “tỷ lệ thu hồi được xác minh” nên dựa trên tập quyết định thu hồi hợp lệ trong phạm vi và mốc báo cáo đã xác định, không dựa trên tổng số mục được giữ quyền.

Nếu có mục mới được bổ sung, bị loại vì ngoài phạm vi hoặc bị thay thế do thay đổi vòng đời, cần giữ lịch sử để giải thích biến động. Không giảm mẫu số bằng cách âm thầm xóa những mục khó xử lý.

Không đặt chỉ tiêu “phải thu hồi một tỷ lệ quyền cố định”. Một đợt rà soát không phát hiện quyền dư vẫn có thể có giá trị nếu dữ liệu và quyết định đáng tin cậy. Ngược lại, thu hồi nhiều quyền nhưng làm gián đoạn công việc hoặc bỏ sót đặc quyền quan trọng chưa phải kiểm soát tốt.

## 13. Các lỗi thiết kế thường gặp

**Dùng chứng nhận thay cho quy trình vòng đời:** chờ đến cuối quý mới thu hồi tài khoản nghỉ việc. Cần xử lý sự kiện vòng đời theo chính sách và dùng certification để phát hiện phần còn sót.

**Giao mọi quyền cho quản lý trực tiếp:** quản lý hiểu công việc nhưng có thể không hiểu mã quyền kỹ thuật. Cần mô tả rõ và kết hợp chủ ứng dụng khi cần.

**Chứng nhận một lần cho cả ứng dụng:** che khác biệt giữa xem dữ liệu, sửa dữ liệu và quản trị. Cần đơn vị rà soát đủ chi tiết để quyết định có ý nghĩa.

**Tự coi không phản hồi là chấp thuận:** bỏ mất trách nhiệm xác nhận. Cần chính sách quá hạn và tuyến chuyển cấp được xác định trước.

**Dùng lịch sử sử dụng làm quyết định duy nhất:** quyền ít dùng chưa chắc thừa, quyền dùng nhiều chưa chắc hợp lệ. Cần đối chiếu nhu cầu và chính sách.

**Đánh dấu hoàn tất ngay khi reviewer chọn thu hồi:** bỏ qua lỗi connector và nhiều đường cấp quyền. Cần theo dõi đến bước xác minh.

**Xóa ở đích nhưng để nguyên nguồn tự động cấp:** quyền có thể quay lại. Cần sửa đúng nguồn có thẩm quyền và kiểm tra sau đồng bộ.

**Ngoại lệ không có ngày kết thúc hoặc chủ sở hữu:** biến quyền tạm thời thành đặc quyền lâu dài. Cần vòng đời, biện pháp kiểm soát và quyết định gia hạn rõ ràng.

**Giữ snapshot cũ nhưng không quản lý thay đổi:** quyết định có thể không còn phù hợp với người dùng hoặc vai trò hiện tại. Cần cơ chế phát hiện và xử lý chênh lệch.

**Báo cáo chỉ có một tỷ lệ hoàn tất:** che mục chưa quyết định, chưa thực thi và chưa xác minh. Cần trình bày riêng từng giai đoạn cùng các tồn đọng.

Access certification có giá trị khi nối được người chịu trách nhiệm, nhu cầu nghiệp vụ, quyền thực tế và hành động đã xác minh. Một lần chứng nhận phản ánh điều đã được xem xét trong một phạm vi và thời điểm cụ thể; duy trì quyền phù hợp còn cần quy trình vòng đời, chính sách cấp quyền và đối soát hoạt động liên tục.
