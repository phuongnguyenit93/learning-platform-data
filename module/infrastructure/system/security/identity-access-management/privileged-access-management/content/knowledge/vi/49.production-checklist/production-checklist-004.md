# Checklist production: Đã bật least privilege

## 1. Mục đích của hạng mục nghiệm thu

**Least privilege** là nguyên tắc chỉ cấp cho một danh tính những quyền cần thiết để thực hiện nhiệm vụ đã được cho phép, trên đúng tài nguyên, trong đúng điều kiện và thời gian cần dùng. Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), nguyên tắc này phải áp dụng cả cho người quản trị, tài khoản dịch vụ, tác vụ tự động và các thành phần vận hành chính PAM.

Câu “đã bật least privilege” không có nghĩa chỉ cần bật một lựa chọn trong sản phẩm. Đây là kết luận cần có bằng chứng: công việc hợp lệ vẫn thực hiện được, các thao tác ngoài nhiệm vụ bị chặn và những đường cấp quyền có thể làm mất giới hạn đó đã được xem xét.

Một cấu hình có thể trông rất chặt nhưng vẫn không đạt yêu cầu. Ví dụ, tài khoản trực ca chỉ được phép khởi động lại một dịch vụ, nhưng lại có quyền sửa tệp cấu hình chạy bằng tài khoản quản trị. Người đó có thể biến quyền sửa cấu hình thành một đường thực thi với đặc quyền cao hơn. Vì vậy, nghiệm thu phải nhìn vào **khả năng thực tế mà danh tính có thể đạt được**, không chỉ tên vai trò hoặc số lượng quyền trong một màn hình.

Hạng mục này trả lời bốn câu hỏi:

1. Danh tính nào được làm công việc gì?
2. Quyền đó tác động đến tài nguyên và môi trường nào?
3. Quyền tồn tại bao lâu, được cấp và thu hồi bằng cách nào?
4. Bằng chứng nào cho thấy giới hạn thực sự được thực thi trên đường truy cập production?

Bài học tập trung vào kiểm tra và bàn giao trạng thái sẵn sàng của least privilege. Việc kiểm kê tài khoản, quản lý credential, JIT/JEA, giám sát phiên và ứng phó sự cố là các cơ chế hỗ trợ để kết luận này có thể duy trì trong vận hành.

## 2. Điều kiện PASS phải được thống nhất trước

### 2.1. Đơn vị kiểm tra không chỉ là tài khoản

Đơn vị kiểm tra hữu ích là một quan hệ:

> Danh tính → nhiệm vụ → quyền được phép → tài nguyên → điều kiện sử dụng → thời hạn → bằng chứng.

Ví dụ, “kỹ sư vận hành được xử lý sự cố” còn quá rộng. Một phát biểu có thể nghiệm thu được là:

> Nhóm trực ca của dịch vụ thanh toán được khởi động lại đúng dịch vụ đã chỉ định trên nhóm máy production được duyệt, trong cửa sổ kích hoạt đặc quyền có thời hạn, thông qua đường PAM được kiểm soát; không được sửa cấu hình thực thi, thay đổi chính sách cấp quyền hoặc truy cập dịch vụ khác.

Phát biểu này chưa thay thế cấu hình kỹ thuật, nhưng tạo được cơ sở để đối chiếu quyền và thiết kế kiểm thử.

### 2.2. Các điều kiện tối thiểu

| Điều kiện | Cần chứng minh | Ví dụ chưa đủ để kết luận |
|---|---|---|
| Đúng danh tính | Chủ sở hữu, mục đích và loại tài khoản rõ ràng | Tài khoản có tên “ops-limited” |
| Đúng nhiệm vụ | Mỗi quyền có liên hệ với một công việc được duyệt | Sao chép quyền từ một quản trị viên lâu năm |
| Đúng phạm vi | Quyền giới hạn theo tài nguyên, môi trường và đối tượng dữ liệu phù hợp | Chỉ kiểm tra tên nhóm mà bỏ qua tài nguyên thực tế |
| Đúng thời gian | Quyền tạm thời hết hạn và quyền thường trực có lý do | Ticket có ngày kết thúc nhưng quyền không bị thu hồi |
| Có thực thi | Thao tác ngoài phạm vi bị kiểm soát trên đường truy cập thực | Chỉ xem cấu hình mong muốn trong kho mã |
| Có bằng chứng | Kết quả kiểm thử và cấu hình hiệu lực có thể đối chiếu | Ảnh chụp không có phiên bản hoặc thời điểm |
| Có duy trì | Có người chịu trách nhiệm theo dõi thay đổi và ngoại lệ | Kiểm tra một lần rồi không rà soát lại |

Không phải mọi danh tính đều phù hợp với cơ chế cấp quyền giống nhau. Người quản trị có thể dùng JIT; một tiến trình chạy liên tục có thể cần quyền thường trực hẹp, danh tính workload và credential được quản lý. Điều cần nghiệm thu là mức quyền phù hợp với nhiệm vụ, thay vì ép mọi trường hợp dùng cùng một cách cấp quyền.

## 3. Chốt phạm vi và baseline quyền cần thiết

### 3.1. Kiểm kê những nhóm danh tính liên quan

Trong phạm vi triển khai, cần nhận diện tối thiểu:

- Người dùng thông thường có quyền quản trị cục bộ hoặc quyền nâng đặc quyền.
- Tài khoản quản trị cá nhân và tài khoản dùng chung còn tồn tại.
- Tài khoản dịch vụ, workload, agent, scheduler và job nền.
- Pipeline triển khai, công cụ tự động hóa và tích hợp qua API.
- Tài khoản của nhà cung cấp, nhà thầu và bên hỗ trợ từ xa.
- Danh tính quản trị PAM, vault, broker, connector và hệ thống lưu bằng chứng.
- Tài khoản khẩn cấp hoặc cơ chế break-glass được giữ lại.

Mỗi danh tính cần có chủ sở hữu chịu trách nhiệm về mục đích và quyền sử dụng. Với danh tính máy, chủ sở hữu thường là nhóm vận hành ứng dụng hoặc dịch vụ; không nên dùng việc “không có người đăng nhập trực tiếp” để bỏ qua trách nhiệm này.

Một tài khoản không xác định được chủ sở hữu không thể được mặc định là cần toàn bộ quyền hiện có. Cần đưa nó vào quy trình xác minh và quyết định xử lý, có xem xét phụ thuộc nghiệp vụ trước khi thay đổi.

### 3.2. Lập ma trận nhiệm vụ và quyền

Ví dụ dưới đây là ma trận thiết kế cho một phạm vi giả định, không phải bộ quyền dùng chung cho mọi hệ thống:

| Danh tính hoặc vai trò | Nhiệm vụ hợp lệ | Phạm vi cho phép | Quyền phải loại trừ | Cách cấp |
|---|---|---|---|---|
| Nhân viên trực ca | Khởi động lại dịch vụ được giao | Đúng dịch vụ và nhóm máy đã duyệt | Sửa cấu hình thực thi, tạo người dùng, thay đổi policy | Kích hoạt có thời hạn qua PAM |
| Người đọc báo cáo | Xem báo cáo vận hành | Tập dữ liệu báo cáo được chỉ định | Sửa dữ liệu nguồn, đọc credential, cấp quyền | Quyền đọc thường trực theo vai trò |
| Workload xử lý thanh toán | Đọc và cập nhật dữ liệu phục vụ luồng xử lý | Đúng cơ sở dữ liệu, bảng hoặc giao diện cần dùng | Quản trị schema, tạo role, truy cập dữ liệu dịch vụ khác | Danh tính dịch vụ có quyền hẹp |
| Pipeline triển khai | Triển khai bản phát hành đã duyệt | Đúng ứng dụng và môi trường đích | Sửa chính sách IAM chung, dùng quyền triển khai cho ứng dụng khác | Quyền triển khai theo ngữ cảnh và thời hạn phù hợp |
| Nhà cung cấp | Chẩn đoán thành phần được hỗ trợ | Đúng tài sản và cửa sổ hỗ trợ | Truy cập ngang hệ thống, duy trì tài khoản sau hợp đồng | Cấp tạm, phê duyệt và giám sát |
| Quản trị PAM | Vận hành thành phần PAM theo phân công | Thành phần và thao tác quản trị cần thiết | Tự duyệt mọi quyền, tự xóa toàn bộ bằng chứng giám sát | Phân tách trách nhiệm và quyền quản trị phù hợp |

Quyền trong ma trận cần được ánh xạ thành quyền thực tế của từng nền tảng. “Khởi động lại dịch vụ” phải được kiểm tra cùng những quyền phụ trợ như sửa script, thay binary, thay đường dẫn tải thư viện hoặc thay cấu hình. “Triển khai ứng dụng” cũng cần xét khả năng bản triển khai sử dụng danh tính chạy ứng dụng để tiếp cận tài nguyên khác.

### 3.3. Phân biệt baseline với quan sát sử dụng

Log sử dụng quyền giúp phát hiện quyền thừa, nhưng “không xuất hiện trong log gần đây” không tự động có nghĩa là không cần. Một quyền có thể chỉ dùng trong khôi phục sự cố, công việc theo tháng hoặc một nhánh nghiệp vụ ít xảy ra.

Ngược lại, quyền đang được dùng thường xuyên cũng không tự động là quyền hợp lệ. Có thể quy trình hiện tại đang phụ thuộc vào một quyền quá rộng hoặc một cách vận hành cần được thay đổi.

Baseline phải kết hợp yêu cầu nghiệp vụ, thiết kế kỹ thuật, lịch vận hành và bằng chứng quan sát. Mỗi quyền nhạy cảm cần có lý do đủ cụ thể để người khác có thể rà soát.

## 4. Kiểm tra quyền hiệu lực trên toàn bộ đường truy cập

### 4.1. Kiểm tra nhiều nguồn cấp quyền

Một danh tính có thể nhận quyền từ nhiều nơi:

- Gán trực tiếp cho tài khoản.
- Nhóm, nhóm lồng nhau hoặc vai trò được kế thừa.
- Vai trò liên kết từ hệ thống định danh.
- Chính sách gắn với tài nguyên.
- Cơ chế nâng quyền trên máy chủ hoặc trong ứng dụng.
- Khả năng nhận, kích hoạt hoặc ủy quyền một vai trò khác.
- Credential hoặc token của danh tính khác mà tài khoản có thể lấy được.
- Phiên hoặc token đã cấp trước khi policy được thu hẹp.

Không nên cộng hoặc giao các danh sách quyền bằng một công thức chung rồi coi đó là kết quả chính xác cho mọi nền tảng. Cách đánh giá policy, điều kiện và quy tắc từ chối phụ thuộc hệ thống thực thi. Khi nghiệm thu phải dùng cơ chế đánh giá phù hợp và kiểm tra hành vi trên đường truy cập liên quan.

Nếu đã gỡ quyền quản trị trực tiếp nhưng người dùng vẫn ở một nhóm có cùng quyền, kết quả thực tế chưa thay đổi. Nếu đã thu hẹp vai trò trên PAM nhưng vẫn có credential truy cập trực tiếp tới máy đích, giới hạn của PAM có thể chưa bao phủ đường đó.

### 4.2. Xem xét khả năng tăng quyền gián tiếp

Những quyền dưới đây có thể ảnh hưởng tới least privilege dù không mang tên “administrator”:

| Khả năng | Lý do cần xem xét |
|---|---|
| Sửa policy, gán role hoặc thay thành viên nhóm đặc quyền | Có thể tự tạo thêm quyền |
| Đọc credential, private key hoặc token của tài khoản khác | Có thể chuyển sang danh tính có quyền cao hơn |
| Sửa mã, script hoặc cấu hình được thực thi với đặc quyền cao | Có thể biến quyền ghi thành khả năng thực thi đặc quyền |
| Thay danh tính chạy workload hoặc cấp cho workload một role khác | Có thể mở rộng phạm vi truy cập của mã đang chạy |
| Chỉnh pipeline có quyền triển khai production | Có thể điều khiển nội dung được triển khai hoặc cách sử dụng credential |
| Chỉnh cơ chế phê duyệt, thời hạn hoặc nhóm được kích hoạt JIT | Có thể làm mất giới hạn cấp quyền |
| Thay hoặc xóa log mà chính danh tính đó tạo ra | Làm suy yếu khả năng phát hiện và truy vết lạm dụng |

Mục tiêu không phải coi mọi quyền ghi đều là đặc quyền quản trị. Mục tiêu là chỉ ra quan hệ giữa đối tượng được ghi, danh tính thực thi nó và tài nguyên mà danh tính đó có thể truy cập.

Ví dụ, quyền sửa một tệp tài liệu trong vùng riêng khác với quyền sửa script mà tác vụ hệ thống sẽ chạy. Cùng là quyền ghi, nhưng hậu quả đối với đặc quyền rất khác nhau.

### 4.3. Phân biệt quyền đủ điều kiện và quyền đang hoạt động

Với Just-in-Time access (JIT), một người có thể đủ điều kiện kích hoạt vai trò nhưng chưa có quyền thực hiện tác vụ nhạy cảm. Cần kiểm tra cả hai trạng thái:

1. Trước kích hoạt: tác vụ đặc quyền chưa được phép.
2. Khi yêu cầu: danh tính, lý do, phạm vi, thời hạn và yêu cầu phê duyệt được kiểm tra.
3. Sau kích hoạt: chỉ phạm vi đã duyệt được sử dụng.
4. Khi hết hạn hoặc bị thu hồi: khả năng thực hiện tác vụ không tiếp tục tồn tại ngoài giới hạn đã thống nhất.

Không kết luận PASS chỉ vì yêu cầu kích hoạt đã có người duyệt. Phải kiểm tra quyền được cấp xuống đích, thời hạn hiệu lực và hành vi của các phiên đang tồn tại.

Với Just Enough Administration (JEA), cần kiểm tra tập thao tác được ủy quyền và khả năng thoát khỏi giới hạn đó qua tham số, công cụ con, tệp thực thi hoặc những quyền phụ trợ. Một danh sách tên lệnh được phép chưa đủ nếu các lệnh đó có thể gọi thao tác tùy ý.

## 5. Các điểm cần kiểm tra theo loại danh tính

### 5.1. Người quản trị và nhân sự trực ca

Tài khoản dùng hằng ngày và hoạt động quản trị cần được tổ chức sao cho việc sử dụng đặc quyền có thể nhận diện, giới hạn và truy vết. Phương án cụ thể có thể dùng danh tính quản trị riêng hoặc cơ chế kích hoạt vai trò theo chính sách của tổ chức.

Trước nghiệm thu cần xác nhận:

- Không giữ quyền quản trị thường trực chỉ vì tài khoản từng tham gia triển khai.
- Vai trò được cấp phù hợp với trách nhiệm hiện tại, không tích lũy theo lịch sử chuyển nhóm.
- Quyền kích hoạt, quyền phê duyệt và quyền thay đổi chính sách có phân tách phù hợp.
- Người dùng không thể dùng một đường đăng nhập khác để nhận lại toàn bộ quyền đã gỡ.
- Tác vụ thường gặp được thực hiện bằng mức quyền dự kiến, tránh phát sinh thói quen dùng tài khoản khẩn cấp.
- Việc xác thực mạnh và kiểm soát phiên hỗ trợ truy cập, nhưng không được dùng thay cho giới hạn quyền.

MFA làm tăng độ tin cậy của xác thực; nó không làm cho một vai trò quá rộng trở thành vai trò tối thiểu. Tương tự, ghi hình phiên giúp quan sát thao tác nhưng không thay thế việc ngăn thao tác ngoài phạm vi.

### 5.2. Tài khoản dịch vụ và workload

Least privilege cho danh tính máy cần gắn với luồng nghiệp vụ cụ thể. Một workload chỉ cần đọc báo cáo không nên được cấp quyền quản trị cơ sở dữ liệu để tránh phải phân tích quyền.

Các điểm cần đối chiếu:

- Tài khoản chỉ phục vụ mục đích và phạm vi đã được xác định.
- Không dùng chung một danh tính quyền rộng cho nhiều ứng dụng có nhu cầu khác nhau mà không có lý do và kiểm soát được duyệt.
- Quyền lấy secret hoặc token được giới hạn tương ứng với workload cần dùng.
- Quyền đọc secret không bao gồm tùy ý đọc credential quản trị của dịch vụ khác.
- Credential không được phân phối rộng hơn phạm vi tiêu thụ hợp lệ.
- Các phụ thuộc như health check, job định kỳ, khởi động và khôi phục có trong kịch bản kiểm thử.
- Việc thay credential, cấp lại token và thu hồi danh tính có quy trình rõ ràng.

Luân chuyển credential và least privilege giải quyết hai khía cạnh khác nhau. Luân chuyển một mật khẩu của tài khoản toàn quyền không tự thu hẹp quyền của tài khoản đó. Thu hẹp quyền cũng không giải quyết việc credential đã bị sao chép trái phép.

### 5.3. Pipeline và tự động hóa

Pipeline có thể triển khai mã, cấp tài nguyên hoặc lấy credential; vì vậy nó thường là một đường ảnh hưởng lớn tới production.

Cần kiểm tra quyền theo từng giai đoạn và ngữ cảnh. Một job kiểm tra mã không nhất thiết cần quyền triển khai. Một job triển khai một ứng dụng không nên mặc nhiên có quyền thay chính sách IAM của toàn bộ môi trường.

Đồng thời, kiểm tra ai có thể sửa định nghĩa pipeline, thay biến chạy, đổi kho nguồn hoặc điều khiển artifact đầu vào. Nếu một người không có quyền quản trị trực tiếp nhưng có thể tùy ý thay job chạy với credential quản trị, quyền hiệu lực của người đó có thể rộng hơn ma trận ban đầu.

Không đưa credential production thật vào ví dụ, tài liệu nghiệm thu hoặc log của pipeline.

### 5.4. Nhà cung cấp và tài khoản khẩn cấp

Quyền nhà cung cấp cần có phạm vi hỗ trợ, người bảo trợ, cửa sổ truy cập và thời điểm kết thúc. Một phiên được giám sát nhưng truy cập được mọi máy trong mạng vẫn có thể vượt nhu cầu hỗ trợ.

Break-glass là ngoại lệ có chủ đích cho tình huống khẩn cấp, không phải cách bù cho vai trò thường ngày bị thiết kế thiếu. Khi nghiệm thu cần ghi rõ:

- Trường hợp nào được phép sử dụng.
- Ai có thể tiếp cận và ai được thông báo.
- Phạm vi đặc quyền được giữ lại cùng lý do.
- Cách ghi nhận sử dụng khi đường PAM thông thường không hoạt động.
- Cách đóng quyền, xử lý credential và rà soát sau sử dụng.

Sự tồn tại của một tài khoản khẩn cấp quyền cao không tự động làm mọi kiểm soát least privilege thất bại. Tuy nhiên, không thể bỏ tài khoản đó khỏi phạm vi kiểm kê hoặc gọi toàn bộ môi trường là “không còn đặc quyền thường trực” nếu thực tế vẫn còn ngoại lệ như vậy.

## 6. Thiết kế bộ kiểm thử nghiệm thu

### 6.1. Có cả kiểm thử cho phép và kiểm thử từ chối

Chỉ kiểm tra người dùng không làm được thao tác nguy hiểm có thể dẫn đến một cấu hình chặn luôn công việc hợp lệ. Chỉ kiểm tra công việc hợp lệ chạy thành công lại có thể bỏ sót quyền vượt phạm vi.

Bộ kiểm thử cần có hai phía:

- **Kiểm thử cho phép:** tác vụ đã được duyệt hoàn thành với đúng danh tính, đúng đường truy cập và mức quyền dự kiến.
- **Kiểm thử từ chối:** thao tác ngoài nhiệm vụ hoặc ngoài điều kiện không tạo ra thay đổi trái phép.

Kết quả bị từ chối phải được xác minh ở đúng lớp. Một yêu cầu lỗi vì sai mật khẩu, mất mạng hoặc sai tên tài nguyên không chứng minh được policy phân quyền đã chặn nó. Cần phân biệt lỗi xác thực, lỗi kết nối, lỗi tham số và quyết định cấp quyền.

### 6.2. Ví dụ bộ kiểm thử cho nhân viên trực ca

Giả sử vai trò trực ca được phép khởi động lại dịch vụ thanh toán A trong một nhóm máy đã duyệt, với phiên kích hoạt đặc quyền tạm thời.

| Mã | Kịch bản | Kết quả mong đợi | Bằng chứng cần giữ |
|---|---|---|---|
| LP-01 | Thực hiện thao tác trước khi kích hoạt | Không có quyền khởi động lại | Danh tính, trạng thái chưa kích hoạt, quyết định từ chối |
| LP-02 | Kích hoạt đúng vai trò qua quy trình được duyệt | Cấp đúng phạm vi và thời hạn | Yêu cầu, phê duyệt nếu áp dụng, role và thời điểm hiệu lực |
| LP-03 | Khởi động lại dịch vụ A trên máy thuộc phạm vi | Hoàn thành theo quy trình vận hành | Sự kiện thao tác, tài nguyên đích, kết quả dịch vụ |
| LP-04 | Thao tác với dịch vụ B ngoài phạm vi | Bị từ chối, không thay đổi dịch vụ B | Quyết định cấp quyền và trạng thái đích |
| LP-05 | Tạo người dùng hoặc gán thêm quyền | Bị từ chối | Sự kiện và kiểm tra không có đối tượng hoặc quyền mới |
| LP-06 | Sửa script hoặc cấu hình thực thi đặc quyền ngoài nhiệm vụ | Bị từ chối | Phạm vi tệp được kiểm tra và trạng thái sau thử |
| LP-07 | Kích hoạt hết hạn rồi thực hiện tác vụ mới | Không còn quyền thực hiện | Thời điểm hết hạn, thử lại, kết quả |
| LP-08 | Thu hồi sớm khi còn phiên đang hoạt động | Hành vi phù hợp yêu cầu thu hồi đã thống nhất | Thời điểm thu hồi, phiên/token liên quan, kết quả thử lại |
| LP-09 | Dùng đường truy cập trực tiếp ngoài PAM | Không đạt được đặc quyền bị giới hạn | Đường truy cập đã kiểm tra và kết quả tại đích |

Kịch bản cụ thể phải được thực hiện trong phạm vi kiểm thử đã được phép. Với thao tác có thể gây gián đoạn, ưu tiên môi trường tương đương để kiểm tra đầy đủ, sau đó xác minh trên production bằng phương thức phù hợp với quy trình thay đổi. Không thử phá hoại một tài nguyên thật chỉ để có bằng chứng “đã kiểm tra”.

Kết quả tại môi trường thử nghiệm không tự động đại diện cho production nếu cấu hình, gán nhóm, danh tính hoặc đường truy cập khác nhau. Hồ sơ nghiệm thu cần chỉ ra phần nào đã được kiểm tra ở đâu và cách xác nhận cấu hình tương ứng.

### 6.3. Kiểm thử danh tính dịch vụ

Với workload xử lý thanh toán, các kịch bản có thể gồm:

1. Chạy một luồng nghiệp vụ hợp lệ với dữ liệu thử đã được phép.
2. Xác nhận workload chỉ lấy được secret hoặc token cần thiết.
3. Thử truy cập đối tượng ngoài phạm vi bằng danh tính kiểm thử tương ứng.
4. Xác nhận không có quyền tạo role, cấp quyền hoặc quản trị cấu trúc ngoài nhiệm vụ.
5. Kiểm tra job định kỳ và đường khởi động lại để phát hiện phụ thuộc bị bỏ sót.
6. Kiểm tra hành vi khi quyền hoặc credential bị thu hồi theo quy trình.

Không dùng một tài khoản quản trị để chạy hộ luồng nghiệp vụ rồi ghi nhận workload đã PASS. Bằng chứng phải chỉ ra danh tính thực sự được sử dụng.

## 7. Xác minh hết hạn, thu hồi và phiên đang tồn tại

Đây là điểm thường bị bỏ sót khi đánh dấu checklist. Thu hẹp policy hoặc hết hạn một lần kích hoạt không luôn đồng nghĩa mọi khả năng truy cập hiện tại biến mất tức thì.

Cần xem xét riêng:

| Thành phần | Câu hỏi nghiệm thu |
|---|---|
| Quyền gán | Quyền hoặc tư cách kích hoạt đã được gỡ đúng nơi chưa? |
| Token đã cấp | Token có tiếp tục được chấp nhận không, trong bao lâu và với phạm vi nào? |
| Phiên đang mở | Phiên có còn thực hiện được thao tác đặc quyền sau thu hồi không? |
| Credential đã biết | Có cần thay credential hoặc chặn đường truy cập dùng credential cũ không? |
| Cache cấp quyền | Có độ trễ cập nhật quyền tại ứng dụng hoặc máy đích không? |
| Quyền tại đích | Có bản sao role, nhóm cục bộ hoặc cấu hình khác còn hiệu lực không? |

Thiết kế cần xác định yêu cầu thu hồi cho từng đường truy cập. Nếu một thành phần chỉ áp dụng quyền mới ở lần đăng nhập tiếp theo, phải ghi nhận điều đó và đánh giá xem có đáp ứng yêu cầu production hay không. Nếu cần kết thúc phiên hoặc vô hiệu hóa token bổ sung, đây phải là một phần của quy trình, không được giả định đã có.

Trong kiểm thử thu hồi, cần đo ít nhất thời điểm yêu cầu thu hồi và thời điểm thao tác thử lại không còn được phép. Phân biệt một yêu cầu đang thực thi với một yêu cầu mới sau thu hồi; khả năng hủy công việc đang chạy phụ thuộc hệ thống và thiết kế tác vụ.

Không tự đưa ra một cam kết chung như “mọi quyền bị thu hồi ngay lập tức”. Cam kết phải bám vào hành vi đã kiểm tra và giới hạn thực tế của từng thành phần.

## 8. Triển khai thu hẹp quyền có kiểm soát

### 8.1. Trình tự áp dụng

Một trình tự triển khai phù hợp có thể gồm:

1. Chốt danh tính, tài nguyên và phiên bản baseline.
2. Đối chiếu quyền hiện có với các nhiệm vụ đã được duyệt.
3. Thiết kế vai trò hẹp, cơ chế cấp tạm và các ngoại lệ cần giữ.
4. Kiểm thử trên môi trường phù hợp, gồm cả luồng ít xảy ra.
5. Áp dụng theo nhóm nhỏ hoặc từng phạm vi có thể theo dõi.
6. Xác minh quyền hiệu lực và vận hành nghiệp vụ sau thay đổi.
7. Gỡ các đường cấp quyền cũ khi đường mới đã sẵn sàng theo kế hoạch.
8. Hoàn tất bằng chứng và bàn giao trách nhiệm theo dõi.

Giai đoạn chuyển tiếp có thể tồn tại đồng thời quyền cũ và quyền mới. Khi đó, một kiểm thử từ chối có thể bị quyền cũ làm mất hiệu lực. Phải ghi rõ trạng thái chuyển tiếp và chỉ chốt hạng mục khi cấu hình cuối cùng đã được xác minh.

### 8.2. Theo dõi tác động nghiệp vụ

Các tín hiệu cần quan sát gồm lỗi cấp quyền của ứng dụng, tác vụ nền thất bại, hàng đợi chậm xử lý, job khôi phục không chạy được và yêu cầu hỗ trợ tăng bất thường.

Một lỗi sau thu hẹp quyền cần được phân tích theo thao tác, danh tính và tài nguyên. Không nên lập tức khôi phục vai trò quản trị rộng chỉ vì một tác vụ thất bại. Có thể nguyên nhân là thiếu một quyền hẹp hợp lệ, sai phạm vi tài nguyên hoặc ứng dụng đang dùng nhầm danh tính.

Nếu phải khôi phục quyền để bảo đảm dịch vụ, cần gắn thay đổi đó với sự cố, chủ sở hữu, thời hạn và kế hoạch khắc phục. Sau khi khôi phục, kết luận nghiệm thu trước đó phải được xem xét lại theo cấu hình mới.

### 8.3. Rollback không trở thành quyền vĩnh viễn

Kế hoạch rollback cần nêu rõ:

- Điều kiện kích hoạt và người quyết định.
- Cấu hình hoặc phạm vi quyền được khôi phục.
- Thời hạn và mức giám sát khi quyền rộng được mở lại.
- Cách xác minh dịch vụ phục hồi.
- Người chịu trách nhiệm thu hẹp lại quyền sau xử lý.
- Bằng chứng cần cập nhật trước khi chốt lại hạng mục.

Rollback một thay đổi cấp quyền không nhất thiết chỉ là phục hồi nguyên file policy. Có thể còn token, phiên, credential hoặc gán quyền tại đích cần được xử lý tương ứng.

## 9. Bộ bằng chứng bàn giao

Bằng chứng tốt phải giúp một người khác trả lời được: **ai đã có quyền gì, trên đâu, vào thời điểm nào, theo cấu hình nào và điều gì đã được kiểm thử**.

Một hồ sơ có thể gồm:

| Thành phần | Nội dung cần có |
|---|---|
| Phạm vi nghiệm thu | Dịch vụ, môi trường, nhóm tài nguyên, loại danh tính |
| Baseline | Phiên bản ma trận nhiệm vụ và quyền, chủ sở hữu phê duyệt |
| Cấu hình hiệu lực | Policy/role/gán nhóm liên quan, thời điểm trích xuất, nguồn đối chiếu |
| Kết quả kiểm thử | Kịch bản, danh tính sử dụng, kết quả mong đợi và thực tế |
| Bằng chứng thu hồi | Thời điểm hết hạn hoặc thu hồi, hành vi token/phiên và độ trễ quan sát |
| Ngoại lệ | Lý do, phạm vi, rủi ro, kiểm soát bổ sung, người duyệt, thời hạn |
| Bàn giao vận hành | Chủ sở hữu theo dõi, điều kiện rà soát lại và quy trình thay đổi |

Dấu thời gian nên có múi giờ rõ ràng; các hệ thống liên quan cần có cơ sở đối chiếu thời gian để ghép sự kiện. Mã sự kiện hoặc mã yêu cầu thường hữu ích hơn một ảnh chụp tách rời ngữ cảnh.

Không đưa mật khẩu, private key, token có thể sử dụng hoặc secret thật vào hồ sơ. Chỉ giữ định danh, phiên bản và bằng chứng đủ để kiểm tra; che hoặc loại bỏ dữ liệu nhạy cảm theo quy trình lưu trữ của tổ chức.

Bằng chứng không nên phụ thuộc hoàn toàn vào người vừa được cấp đặc quyền. Với các tài nguyên quan trọng, cần phân tách quyền chỉnh cấu hình, phê duyệt và bảo quản bằng chứng ở mức phù hợp. Một người tự cấp quyền rồi tự xóa được mọi dấu vết làm suy yếu khả năng kiểm chứng sau này.

## 10. Mẫu ghi nhận kết quả

Mẫu dưới đây chỉ minh họa nội dung hồ sơ nghiệm thu. Đây không phải schema cấu hình của một sản phẩm PAM hay một tệp có thể nạp trực tiếp để thực thi quyền.

```yaml
control: least-privilege
scope:
  environment: production
  service: payment-service-a
  resource_set: approved-payment-hosts
baseline:
  reference: LP-BASELINE-PAYMENT-A-v3
  owner: payment-operations
checks:
  identity_inventory: PASS
  effective_permissions: PASS
  allowed_operations: PASS
  denied_operations: PASS
  expiry_and_revocation: PASS
  alternate_access_paths: PASS
evidence:
  configuration_reference: CHANGE-EXAMPLE-104
  test_reference: LP-TEST-EXAMPLE-021
  observed_revocation_seconds: 45
  revocation_scope: new-privileged-operations
  existing_sessions: terminated-and-retested
exceptions:
  - id: LP-EXCEPTION-EXAMPLE-02
    purpose: emergency-recovery
    owner: platform-security
    review_due: before-next-production-release
decision:
  result: PASS_WITH_APPROVED_EXCEPTION
  approved_by: designated-risk-owner
  review_trigger: privilege-policy-or-access-path-change
```

Số 45 giây là dữ liệu giả định minh họa, không phải mục tiêu hoặc bảo đảm áp dụng cho mọi hệ thống. Mỗi phạm vi phải có yêu cầu thu hồi và phép đo riêng. Các nhãn PASS trong mẫu phải được thay bằng kết quả thực tế có bằng chứng trước khi sử dụng.

Trạng thái có ngoại lệ cần được hiển thị rõ, không đổi thành PASS thuần túy để làm đẹp checklist. Nếu quy trình phát hành không cho phép loại ngoại lệ đó, phải giữ hạng mục ở trạng thái chưa đạt.

## 11. Checklist nghiệm thu thực hành

### 11.1. Phạm vi và căn cứ cấp quyền

- [ ] Đã xác định danh tính người và máy trong phạm vi.
- [ ] Mỗi danh tính có chủ sở hữu và mục đích sử dụng rõ ràng.
- [ ] Đã thống nhất các nhiệm vụ hợp lệ cùng phạm vi tài nguyên.
- [ ] Mỗi quyền nhạy cảm có lý do phù hợp với nhiệm vụ.
- [ ] Đã xét tác vụ định kỳ, khôi phục và các luồng nghiệp vụ ít xảy ra.
- [ ] Các quyền thường trực và ngoại lệ có căn cứ riêng.

### 11.2. Quyền hiệu lực và giới hạn đặc quyền

- [ ] Đã đối chiếu gán trực tiếp, nhóm, kế thừa và vai trò liên kết.
- [ ] Đã kiểm tra khả năng kích hoạt hoặc nhận thêm vai trò.
- [ ] Đã xem xét đường lấy credential/token của danh tính khác.
- [ ] Đã xem xét quyền sửa mã, script, cấu hình và pipeline có thể làm tăng quyền.
- [ ] Phạm vi production được phân biệt rõ với môi trường khác.
- [ ] Quyền lấy secret giới hạn theo nhu cầu của từng workload.
- [ ] Những đường truy cập trực tiếp ngoài PAM đã được kiểm tra.
- [ ] Quyền quản trị PAM và bằng chứng có phân tách trách nhiệm phù hợp.

### 11.3. Cấp tạm, hết hạn và thu hồi

- [ ] JIT, nếu áp dụng, có phạm vi, điều kiện và thời hạn rõ ràng.
- [ ] Quyền trước và sau kích hoạt đã được kiểm tra.
- [ ] JEA hoặc cơ chế ủy quyền tương đương đã kiểm tra thao tác và tham số liên quan.
- [ ] Đã kiểm tra hết hạn và thu hồi sớm.
- [ ] Đã ghi nhận hành vi của token, cache và phiên đang hoạt động.
- [ ] Độ trễ và phạm vi thu hồi đáp ứng yêu cầu đã thống nhất.
- [ ] Break-glass có kiểm soát sử dụng và xử lý sau sử dụng.

### 11.4. Kiểm thử và bàn giao

- [ ] Tác vụ hợp lệ chạy bằng đúng danh tính dự kiến.
- [ ] Tác vụ ngoài phạm vi bị từ chối vì kiểm soát quyền thực sự.
- [ ] Các kiểm thử không tạo thay đổi trái phép hoặc ảnh hưởng ngoài phạm vi.
- [ ] Cấu hình cuối cùng khớp với phiên bản được kiểm thử.
- [ ] Có bằng chứng đủ thời gian, danh tính, tài nguyên và kết quả.
- [ ] Ngoại lệ có người duyệt, thời hạn và kế hoạch xử lý.
- [ ] Có kế hoạch rollback và thu hẹp lại quyền khi cần.
- [ ] Đã bàn giao người theo dõi thay đổi và điều kiện rà soát lại.

Không nên đánh dấu một ô nếu chỉ có lời xác nhận mà chưa có căn cứ phù hợp. Khi không áp dụng một mục, cần ghi rõ lý do; “không áp dụng” không phải cách bỏ qua một đường truy cập chưa được kiểm kê.

## 12. Quyết định PASS, có ngoại lệ hoặc chưa đạt

Có thể dùng ba kết luận vận hành sau, tùy quy trình nội bộ:

**PASS:** các điều kiện bắt buộc trong phạm vi đã đạt; công việc hợp lệ và giới hạn quyền được chứng minh; bằng chứng khớp cấu hình cuối cùng.

**PASS_WITH_APPROVED_EXCEPTION:** các điều kiện nền tảng đã được kiểm tra nhưng còn ngoại lệ được phép theo quy trình. Ngoại lệ phải chỉ rõ giới hạn, người chấp nhận, thời hạn, kiểm soát bổ sung và kế hoạch đóng. Quyết định chấp nhận thuộc người có thẩm quyền, không do người điền checklist tự suy diễn.

**NOT_READY:** thiếu bằng chứng quan trọng, còn đường tăng quyền chưa kiểm soát, công việc hợp lệ không chạy được hoặc hành vi thu hồi chưa đáp ứng yêu cầu. Cần ghi rõ điều kiện để kiểm tra lại.

Ví dụ các trường hợp chưa đủ để chốt PASS:

- Tài khoản trực ca chỉ có một role hẹp, nhưng vẫn thuộc nhóm quản trị cũ.
- Đã bật JIT nhưng sau hết hạn vẫn dùng được token cho các thao tác đặc quyền mới vượt yêu cầu.
- Workload chạy thành công nhờ credential của người quản trị được cài tạm.
- Các thao tác bị từ chối chỉ vì tài khoản thử không đăng nhập được.
- Cấu hình thử nghiệm đã PASS nhưng production có gán nhóm khác chưa được đối chiếu.
- Một ngoại lệ đã hết hạn nhưng quyền vẫn còn hiệu lực.
- Có log theo dõi nhưng không có bằng chứng thao tác ngoài nhiệm vụ bị giới hạn.

Một bộ kiểm thử hữu hạn không chứng minh tuyệt đối rằng không còn mọi đường tăng quyền. Kết luận phải nêu đúng phạm vi đã kiểm kê, cấu hình được xem xét và những kịch bản đã kiểm tra; các rủi ro còn lại cần được xử lý theo quy trình phù hợp.

## 13. Duy trì trạng thái sau go-live

Least privilege có thể suy giảm sau nghiệm thu khi thêm ứng dụng, thay người trực ca, mở quyền tạm trong sự cố hoặc thay pipeline. Vì vậy, bàn giao cần có các điều kiện kích hoạt rà soát lại:

- Thay đổi vai trò, nhóm hoặc chính sách liên quan tới production.
- Thay chủ sở hữu hoặc mục đích của danh tính dịch vụ.
- Thêm tài nguyên, môi trường hoặc đường truy cập mới.
- Thay thành phần PAM, vault, connector hoặc cơ chế định danh.
- Thay credential, token, cách cấp quyền hoặc cách thu hồi.
- Sự cố phải mở rộng quyền, dùng break-glass hoặc khôi phục quyền cũ.
- Ngoại lệ đến hạn hoặc phát hiện quyền vượt baseline.

Các chỉ số hỗ trợ theo dõi có thể gồm số danh tính chưa có chủ sở hữu, số quyền thường trực chưa có lý do, số ngoại lệ quá hạn và số thay đổi quyền chưa có rà soát. Các chỉ số cần có phạm vi và mẫu số rõ ràng; một con số đẹp không thay thế kiểm tra quyền hiệu lực.

Không tự động gỡ một quyền chỉ dựa vào việc không có log sử dụng trong một khoảng thời gian ngắn. Ngược lại, không giữ một quyền vô thời hạn chỉ vì từng có sự cố cần dùng nó. Chủ sở hữu phải đánh giá lại nhu cầu và chọn cách cấp phù hợp.

## 14. Tình huống tự kiểm tra

Một đội vận hành báo đã hoàn tất least privilege vì mọi người dùng đều đăng nhập qua PAM và phiên đều được ghi hình. Kiểm tra thêm cho thấy tài khoản trực ca vẫn đọc được credential quản trị chung trong vault, còn phiên máy đích vẫn thực hiện được tác vụ quản trị sau khi lần kích hoạt đã hết hạn.

Trong tình huống này, đường đăng nhập và khả năng quan sát đã được cải thiện, nhưng chưa đủ căn cứ chốt least privilege. Cần xác định mục đích và phạm vi quyền đọc credential, kiểm tra khả năng dùng credential đó ngoài phạm vi nhiệm vụ, đồng thời đối chiếu hành vi phiên với yêu cầu hết hạn và thu hồi.

Nếu nhu cầu hợp lệ chỉ là khởi động lại một dịch vụ, phương án khắc phục cần hướng tới đúng khả năng đó: thu hẹp quyền tại đích, giới hạn đường lấy credential, kiểm soát thời gian và xác minh lại cả thao tác được phép lẫn thao tác bị từ chối. Sau thay đổi, hồ sơ nghiệm thu phải thể hiện cấu hình mới, kết quả thực tế và mọi ngoại lệ còn được giữ lại.

Hạng mục “Đã bật least privilege” chỉ được chốt khi có thể nối liền nhiệm vụ được duyệt, quyền hiệu lực, kết quả kiểm thử và trách nhiệm vận hành trong cùng một phạm vi production rõ ràng.
