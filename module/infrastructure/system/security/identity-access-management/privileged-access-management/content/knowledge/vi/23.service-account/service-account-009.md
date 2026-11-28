# Service account interactive login

Một service account được tạo để chạy tác vụ xử lý hóa đơn. Sau vài lần xử lý sự cố, đội vận hành bắt đầu dùng chính account đó để đăng nhập máy chủ, mở terminal và sửa dữ liệu. Tài khoản dành cho workload dần trở thành một tài khoản dùng chung của cả đội.

Dịch vụ vẫn chạy, nhưng một truy vấn mang tên service account có thể đến từ chương trình, từ một kỹ sư hay từ người đã lấy được credential. Khả năng phân biệt các nguồn hành động bị suy giảm, quyền của ứng dụng trở thành quyền thao tác tùy ý của người đang cầm credential.

Trong quản lý truy cập đặc quyền — Privileged Access Management, viết tắt là PAM — **service account interactive login** là vấn đề kiểm soát việc con người hoặc phiên tương tác sử dụng danh tính dành cho dịch vụ. Thiết kế cần bảo vệ ranh giới đó mà không vô tình chặn các kiểu đăng nhập mà workload thực sự cần.

Bài học này tập trung vào việc nhận diện bề mặt đăng nhập, xây dựng chính sách, triển khai hạn chế theo nền tảng, kiểm thử và giữ bằng chứng vận hành. Tên account bắt đầu bằng `svc_` hay việc không có cửa sổ terminal đều chưa đủ chứng minh ranh giới đã được thực thi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt đăng nhập tương tác, xác thực của dịch vụ và thao tác của con người dưới danh tính dịch vụ.
- Lập ma trận đường truy cập được phép và bị cấm cho một service account.
- Giải thích vì sao khóa password, chặn một giao thức hoặc tắt terminal chưa đủ.
- Thiết kế đường chẩn đoán bằng danh tính cá nhân, quyền tối thiểu và bằng chứng truy vết.
- Xây dựng quy trình ngoại lệ có thời hạn khi thật sự phải sử dụng danh tính runtime.
- Kiểm tra cả việc truy cập bị từ chối và việc workload hợp lệ tiếp tục hoạt động.

## 2. Interactive login nghĩa là gì?

Đăng nhập tương tác thường là phiên trong đó một người xác thực rồi điều khiển môi trường theo từng thao tác: đăng nhập console, mở desktop từ xa hoặc mở shell.

Tuy nhiên, mục tiêu bảo vệ không nên dừng ở định nghĩa có màn hình hay có terminal. Điều cần kiểm soát rộng hơn là:

> Ai có thể trực tiếp thực hiện hành động tùy ý dưới danh tính service account, qua đường nào và với bằng chứng nào?

Một người chạy lệnh từ xa mà không yêu cầu terminal vẫn có thể sử dụng quyền của service account. Một người mở phiên database bằng credential của ứng dụng cũng đang sử dụng danh tính ứng dụng, dù không đăng nhập hệ điều hành.

Ngược lại, tiến trình dịch vụ xác thực tự động tới database không phải là phiên người dùng chỉ vì hệ thống đích tạo một phiên kết nối.

Cần phân biệt hai lớp:

| Lớp xem xét | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Kiểu đăng nhập do nền tảng phân loại | Đây là console, remote interactive, service, batch hay network? | Một dịch vụ được trình quản lý dịch vụ khởi động |
| Mục đích và khả năng điều khiển | Ai đang ra quyết định và có thể làm gì dưới principal đó? | Một kỹ sư dùng credential runtime để sửa bản ghi |

Kiểu đăng nhập là dữ liệu kỹ thuật quan trọng. Nó không tự giải thích toàn bộ ý định hoặc mức quyền của người đang sử dụng đường truy cập.

## 3. Bốn danh tính cần tách rõ

Giả sử ứng dụng `invoice-worker` chạy ở production:

1. **Người vận hành** có tài khoản cá nhân để được xác thực và quy trách nhiệm.
2. **Danh tính quản trị được nâng quyền** cho phép người đó thực hiện tác vụ đã được duyệt trong một khoảng thời gian.
3. **Danh tính hệ điều hành của service** xác định quyền cục bộ của tiến trình.
4. **Danh tính truy cập tài nguyên đích** xác định quyền với database, API hoặc kho lưu trữ.

Các lớp có thể liên quan nhưng không nên bị coi là một account duy nhất.

Một người được phép xem log không mặc nhiên được lấy credential runtime. Một account chạy service không mặc nhiên cần quyền RDP hoặc SSH. Một service không cần quyền quản trị máy chủ chỉ vì người vận hành đôi khi cần quyền đó để sửa sự cố.

Nếu workload phải truy cập nhiều hệ thống bằng nhiều principal, chính sách interactive login phải xem xét từng principal. Chặn shell của user hệ điều hành không chặn việc sử dụng một API key đã bị sao chép.

## 4. Vì sao hạn chế interactive login của service account?

### 4.1. Giữ khả năng quy trách nhiệm

Nếu ba người cùng đăng nhập bằng `svc_invoice_prod`, log hệ thống đích có thể chỉ ghi `svc_invoice_prod`.

Một cổng PAM có thể bổ sung bằng chứng về người mở phiên, phê duyệt và nội dung thao tác. Tuy nhiên, điều đó không có nghĩa mọi đường truy cập trực tiếp khác tự được kiểm soát. Nếu credential có thể được dùng ngoài cổng, chuỗi quy trách nhiệm vẫn có khoảng trống.

Ưu tiên để người vận hành sử dụng danh tính cá nhân và quyền phù hợp thay vì mượn danh tính của workload.

### 4.2. Giảm đường sử dụng credential bị lộ

Credential runtime bị lộ đã là sự cố cần xử lý. Nếu account còn được phép mở shell hoặc desktop, kẻ tấn công có thêm cách dùng credential đó để điều khiển môi trường.

Chặn những đường không cần thiết giúp giảm bề mặt sử dụng. Nó không làm credential bị lộ trở nên vô hại: quyền API, database hoặc các tài nguyên khác vẫn phải được đánh giá.

### 4.3. Tránh mở rộng quyền vì nhu cầu thao tác tay

Một service chỉ cần đọc hàng đợi và ghi kết quả. Khi con người dùng account đó để sửa cấu hình, họ có thể yêu cầu cấp thêm quyền ghi file, quyền sửa database hoặc quyền quản lý tiến trình.

Theo thời gian, phạm vi runtime tăng để phục vụ công việc của con người. Tách đường vận hành giúp quyền service bám sát nhiệm vụ tự động.

### 4.4. Giữ credential trong đường cấp phát dự kiến

Mỗi lần gửi password qua tin nhắn, sao chép key sang laptop hoặc lưu token vào công cụ cá nhân đều tạo thêm nơi cần kiểm soát.

Quản lý credential qua vault hoặc nền tảng danh tính chỉ có hiệu quả nếu quyền đọc và cách sử dụng credential cũng được giới hạn. Không nên coi nút “checkout password” là đường vận hành mặc định chỉ vì sản phẩm PAM hỗ trợ.

## 5. Chính sách mặc định và phạm vi áp dụng

Một chính sách hợp lý có thể diễn đạt như sau:

> Service account chỉ được sử dụng qua các đường thực thi đã xác định cho workload. Đăng nhập tương tác và sử dụng trực tiếp bởi con người bị hạn chế theo khả năng nền tảng. Mọi ngoại lệ phải có người chịu trách nhiệm, phạm vi, thời hạn và bằng chứng.

Chính sách cần nêu rõ:

- Account nào thuộc phạm vi service account.
- Workload, môi trường và máy nào được sử dụng account.
- Kiểu đăng nhập hoặc đường xác thực được phép.
- Kiểu đăng nhập hoặc đường xác thực bị cấm.
- Ai quản lý cấu hình và credential.
- Đường chẩn đoán thay thế cho người vận hành.
- Cách cấp và thu hồi ngoại lệ.
- Bằng chứng cần giữ và người kiểm tra kết quả.

Không áp dụng máy móc một cấu hình duy nhất cho mọi hệ thống. Một service chạy liên tục, một job theo lịch và một tích hợp chỉ gọi API có nhu cầu đăng nhập khác nhau.

Account cũng không nên được phép dùng trên mọi máy chỉ vì nó là account dịch vụ của tổ chức. Phạm vi máy và workload được sử dụng là một ranh giới riêng.

## 6. Xây dựng ma trận đường truy cập

Trước khi thay đổi cấu hình, lập ma trận cho từng account hoặc nhóm account có cùng đặc tính.

Ví dụ minh họa cho `svc_invoice_prod`:

| Đường sử dụng | Nhu cầu thực tế | Quyết định thiết kế | Bằng chứng cần có |
| --- | --- | --- | --- |
| Trình quản lý dịch vụ khởi động tiến trình | Có | Cho phép đúng máy và cấu hình đã duyệt | Log khởi động và principal của tiến trình |
| Bộ lập lịch chạy job dọn dẹp | Chưa rõ | Xác minh phụ thuộc trước khi quyết định | Hồ sơ job, quyền và chủ sở hữu |
| Console cục bộ | Không | Từ chối | Kết quả thử từ chối và chính sách hiệu lực |
| Desktop từ xa | Không | Từ chối | Log đường đăng nhập tương ứng |
| SSH shell | Không | Từ chối | Kiểm thử SSH và cấu hình đang áp dụng |
| SSH chạy lệnh không có terminal | Không | Từ chối nếu không thuộc tích hợp hợp lệ | Kiểm thử đúng đường lệnh từ xa |
| API nghiệp vụ từ runtime | Có | Cho phép quyền tối thiểu | Principal, tài nguyên và kết quả ở hệ thống đích |
| Công cụ cá nhân kết nối database bằng credential runtime | Không | Hạn chế bằng các lớp kiểm soát khả dụng | Quyền lấy credential, đường mạng và audit database |
| Người vận hành đọc log bằng account riêng | Có | Cho phép theo vai trò | Định danh người, quyền và phạm vi log |

“Chưa rõ” là kết quả cần điều tra, không phải lý do để cho phép mọi đường. Nhưng cũng không nên chặn ngay trên production trước khi biết tác động tới job hoặc dịch vụ liên quan.

Ma trận phải phản ánh cả đường chính và đường dự phòng, bao gồm host khôi phục, nút failover và tác vụ ít chạy.

## 7. Kiểm soát trên Windows: phân biệt quyền đăng nhập

Trên Windows, quyền đăng nhập cục bộ, đăng nhập qua Remote Desktop, chạy như dịch vụ, chạy dạng batch và truy cập qua mạng là các quyền khác nhau. Chính sách phải bám vào nhu cầu thực tế của workload.

Các tên quyền thường gặp gồm:

| Nhóm quyền | Mục đích cần phân biệt |
| --- | --- |
| Log on locally / Deny log on locally | Đăng nhập tương tác tại máy |
| Log on through Remote Desktop Services / quyền từ chối tương ứng | Phiên tương tác qua Remote Desktop |
| Log on as a service / quyền từ chối tương ứng | Khởi chạy dưới cơ chế dịch vụ |
| Log on as a batch job / quyền từ chối tương ứng | Thực thi qua cơ chế batch như tác vụ phù hợp |
| Access this computer from the network / quyền từ chối tương ứng | Truy cập máy qua cơ chế mạng tương ứng |

Bảng này giải thích sự khác biệt về phạm vi, không phải bộ cấu hình có thể áp dụng nguyên xi cho mọi máy.

### 7.1. Không đồng nhất “deny interactive” với vô hiệu hóa account

Vô hiệu hóa account hoặc thu hồi mọi quyền đăng nhập có thể làm service ngừng hoạt động.

Mục tiêu là từ chối những kiểu đăng nhập không cần thiết trong khi duy trì kiểu đăng nhập hợp lệ. Ví dụ, service cần quyền chạy như dịch vụ nhưng không cần quyền mở desktop.

Đối với job theo lịch, cần xác định cơ chế thực thi cụ thể. Không mặc định rằng mọi tác vụ tự động đều dùng cùng kiểu đăng nhập với service chạy liên tục.

### 7.2. Tính đến quyền hiệu lực và nhóm lồng nhau

Một account có thể nhận quyền thông qua nhiều nhóm, chính sách máy và chính sách tập trung. Các quyền từ chối có thể làm quyền cho phép tương ứng không còn hiệu lực.

Do đó, cần đánh giá kết quả cuối cùng trên máy đích thay vì chỉ nhìn một nhóm vừa thêm. Một thay đổi trên nhóm lớn có thể ảnh hưởng nhiều service ngoài phạm vi dự kiến.

Không dùng nhóm chứa toàn bộ người dùng hoặc toàn bộ account máy làm mục tiêu thay đổi nếu chưa xác định chính xác thành viên và hệ quả.

### 7.3. Quyền network không phải bản sao của quyền interactive

Một service có thể cần truy cập tài nguyên mạng. Từ chối đăng nhập tương tác không tự bao phủ mọi truy cập mạng; ngược lại, chặn quyền mạng quá rộng có thể làm workload mất truy cập hợp lệ.

Cần thử đúng giao thức và hệ thống đích trong ma trận. Nếu workload dùng cơ chế nhận dạng khác nhau giữa máy cục bộ và máy từ xa, phải ghi lại principal mà phía từ xa thực sự thấy.

### 7.4. Kiểm tra lại sau khi chính sách được áp dụng

Quy trình kiểm tra cần xác minh:

- Chính sách đã tới đúng máy.
- Account và nhóm nhận cấu hình đúng.
- Đăng nhập tương tác mới bị từ chối.
- Dịch vụ và job hợp lệ khởi động được.
- Các phiên hoặc tiến trình cũ được xử lý theo kế hoạch.

Một thay đổi chính sách không nhất thiết kết thúc mọi phiên đã tồn tại. Kế hoạch phải xem xét cả trạng thái mới và trạng thái đang chạy.

## 8. Kiểm soát trên Linux/Unix: shell, SSH và chuyển user

Ở môi trường Linux/Unix, nhiều lớp tham gia vào việc một người có thể thực hiện hành động dưới UID của service.

### 8.1. Shell không cho đăng nhập

Một account dịch vụ có thể được đặt shell từ chối đăng nhập nếu workload không cần shell đăng nhập. Tên và đường dẫn chương trình như `nologin` phụ thuộc hệ thống.

Điều đó không đồng nghĩa tiến trình không thể chạy dưới UID đó. Trình quản lý dịch vụ có thể khởi động một executable trực tiếp mà không cần phiên đăng nhập tương tác.

Cũng không được suy ngược rằng shell từ chối đăng nhập sẽ chặn mọi cơ chế thực thi. Một đường chạy tác vụ, subsystem hoặc công cụ quản trị có thể áp dụng cơ chế khác.

### 8.2. Khóa password không phải thu hồi mọi credential

Khóa khả năng xác thực bằng password không tự động chứng minh rằng SSH key, chứng thư, token, quan hệ tin cậy hoặc quyền chuyển user đã bị vô hiệu hóa.

Cần đánh giá từng đường mà host thực sự bật. Không coi trạng thái password là kết luận cho toàn bộ account.

### 8.3. SSH có nhiều chế độ sử dụng

Phân biệt:

- Shell tương tác.
- Thực thi lệnh từ xa không cấp terminal.
- Chuyển tiếp kết nối.
- Chuyển tệp hoặc subsystem.
- Các tích hợp tự động được cấu hình riêng.

Chỉ chặn cấp terminal không có nghĩa đã chặn lệnh từ xa. Chỉ chặn password không có nghĩa đã chặn key. Một luồng chuyển tệp tự động có thể cần thiết nhưng không nên vì thế được cấp shell tùy ý.

Cần đối chiếu cấu hình SSH hiệu lực, điều kiện theo account hoặc nguồn kết nối và cơ chế xác thực đang dùng. Nếu có ngoại lệ cho tích hợp, giới hạn đúng hành động và nguồn sử dụng mà nền tảng hỗ trợ.

### 8.4. Quyền chuyển sang UID service

Người có quyền phù hợp có thể dùng công cụ nâng quyền hoặc công cụ quản trị để chạy tiến trình dưới UID service mà không biết password của service.

Bởi vậy, phải xem xét:

- Ai được chuyển sang service account.
- Được chạy lệnh nào.
- Có được đưa tham số tùy ý hay biến môi trường nguy hiểm không.
- Lệnh được phép có thể gọi shell, sửa script hoặc nạp plugin không.
- Người đó có thể sửa executable hoặc file cấu hình mà service sẽ chạy không.

Một quyền “chỉ chạy script chẩn đoán” không còn hẹp nếu người được cấp quyền cũng sửa được script đó.

### 8.5. Quyền quản trị host là ranh giới mạnh hơn

Quản trị viên hệ thống có thể có khả năng điều khiển tiến trình, đọc bộ nhớ hoặc thực thi dưới danh tính service. Không nên tuyên bố shell từ chối đăng nhập sẽ ngăn được mọi quản trị viên của host.

Rủi ro này cần được kiểm soát bằng quản trị đặc quyền đối với host: danh tính cá nhân, nâng quyền đúng phạm vi, kiểm soát thay đổi, audit và cơ chế bảo vệ phù hợp.

Hạn chế interactive login của service là một lớp trong thiết kế, không thay thế việc quản lý người có quyền quản trị nền tảng.

## 9. Container, cloud và các bề mặt ngoài hệ điều hành

Trong môi trường container hoặc cloud, service account có thể là danh tính logic của workload chứ không phải user có password để đăng nhập máy.

Tuy vậy, một người có thể:

- Mở phiên thực thi bên trong container.
- Sửa workload để chạy mã khác dưới cùng danh tính.
- Gắn danh tính runtime vào một workload do họ kiểm soát.
- Đọc secret đã được cấp cho ứng dụng.
- Nhận token thông qua quyền sử dụng hoặc giả danh danh tính của workload.
- Truy cập database bằng credential lấy được từ runtime.

Những thao tác này không nhất thiết xuất hiện dưới nhãn “interactive login” truyền thống. Chúng vẫn có thể cho phép người sử dụng quyền của service.

Cần quản lý riêng quyền truy cập console quản trị, thực thi trong workload, sửa manifest hoặc cấu hình, đọc secret và sử dụng danh tính. Quyền xem trạng thái một workload không nên mặc nhiên bao gồm các quyền đó.

Nếu principal có thể sửa mã mà workload chạy, nó có thể tác động đến cách quyền runtime được dùng. Vì vậy, chỉ chặn quyền lấy token trực tiếp chưa đủ khi đường sửa workload vẫn mở quá rộng.

## 10. Đường vận hành thay thế cho đăng nhập bằng service account

Chính sách sẽ khó được duy trì nếu mọi sự cố đều buộc kỹ sư phải mượn credential runtime. Cần cung cấp công cụ phù hợp với các tác vụ thường gặp.

### 10.1. Quan sát trước khi can thiệp

Cung cấp khả năng xem:

- Trạng thái tiến trình và health check.
- Log ứng dụng đã loại bỏ secret.
- Hàng đợi, checkpoint và mã lỗi.
- Metadata về danh tính runtime, không phải giá trị token.
- Sự kiện từ chối truy cập tại hệ thống đích.

Quyền xem log phải xét dữ liệu nhạy cảm trong log, không mặc định cho phép toàn bộ người vận hành đọc mọi dữ liệu.

### 10.2. Hành động vận hành có phạm vi rõ

Ví dụ, một công cụ có thể cho phép:

```text
Người vận hành xác thực bằng danh tính cá nhân
    → yêu cầu restart invoice-worker
    → kiểm tra quyền với đúng service và môi trường
    → ghi người yêu cầu, lý do và mã thay đổi
    → thực hiện thao tác đã định nghĩa
    → ghi kết quả
```

Đây là luồng khái niệm, không phải cấu hình sản phẩm.

Quyền restart cần được đánh giá cùng quyền sửa cấu hình, đường dẫn executable và nội dung mà service nạp. Nếu người vận hành có thể thay file được service chạy, restart có thể trở thành đường thực thi mã tùy ý.

### 10.3. Chẩn đoán với danh tính riêng

Nếu cần truy vấn dữ liệu hoặc kiểm tra API, có thể cấp cho người chẩn đoán quyền tạm thời trên tập tài nguyên cần thiết bằng danh tính cá nhân.

Không mặc định cấp bản sao toàn bộ quyền runtime. Một câu hỏi như “service có đọc được bản ghi này không?” có thể cần phương pháp kiểm tra dưới đúng ngữ cảnh runtime, nhưng không nhất thiết cần một shell đầy đủ.

Có thể xây dựng endpoint chẩn đoán hoặc tác vụ kiểm tra được kiểm soát. Chức năng đó phải có xác thực, phân quyền, giới hạn đầu vào và audit; không biến nó thành cửa thực thi lệnh bất kỳ.

## 11. Khi cần chẩn đoán dưới đúng danh tính runtime

Một số lỗi chỉ xuất hiện khi ứng dụng chạy với đúng danh tính, host, mạng hoặc credential của nó. Thử bằng tài khoản quản trị có thể thành công và che khuất lỗi phân quyền thật.

Nhu cầu này cần được giải quyết bằng một quy trình cụ thể.

### 11.1. Bắt đầu bằng kiểm tra ít quyền hơn

Trước tiên, xác định thông tin cần biết:

- Principal thực tế là gì?
- Tài nguyên nào bị từ chối?
- Credential có đúng nguồn, phạm vi và thời hạn không?
- Yêu cầu được gửi từ đúng host hoặc workload không?
- Chính sách nào có hiệu lực tại hệ thống đích?
- Lỗi do xác thực, phân quyền hay kết nối?

Những câu hỏi này thường có thể trả lời bằng metadata và audit, không cần biết password.

### 11.2. Ưu tiên tác vụ kiểm tra có giới hạn

Một tác vụ được kiểm soát có thể thực hiện đúng một phép thử dưới ngữ cảnh runtime, chẳng hạn đọc metadata của tài nguyên đã chỉ định, rồi trả kết quả đã được lọc.

Cần giới hạn tài nguyên và thao tác; ghi nhận ai kích hoạt và bằng chứng thực thi; bảo đảm đầu vào không biến thành câu lệnh tùy ý hoặc đường đọc secret.

Mã giả minh họa:

```text
receive diagnostic_request from authenticated_operator

authorize(
    operator = diagnostic_request.operator,
    action = "check-invoice-read",
    environment = "production"
)

validate_target_against_approved_scope(diagnostic_request.target)

run_predefined_check_using_runtime_context()

record(
    operator_id,
    approval_reference,
    execution_id,
    runtime_principal_id,
    target_id,
    sanitized_result
)
```

Không truyền token runtime về cho người yêu cầu như một phần của kết quả kiểm tra.

### 11.3. Nếu vẫn phải mở phiên ngoại lệ

Chỉ cấp quyền cần cho mục đích đã nêu. Xác định trước thời hạn, đường vào, người phê duyệt, điều kiện dừng và cách khôi phục chính sách.

Một phiên qua cổng PAM có thể giúp gắn người với hoạt động và lưu bằng chứng theo khả năng sản phẩm. Cần đồng thời kiểm soát đường truy cập trực tiếp để ngoại lệ không tạo thêm đường sử dụng lâu dài.

Nếu credential đã được tiết lộ cho người, việc đóng phiên không có nghĩa giá trị credential đã mất hiệu lực. Cần đánh giá thay hoặc thu hồi credential, phiên và token liên quan.

## 12. Hồ sơ ngoại lệ có thời hạn

Ngoại lệ nên phục vụ một tình huống cụ thể, không trở thành quy trình đăng nhập chung hằng ngày.

Ví dụ hồ sơ dưới đây là **mẫu tài liệu**, không phải cú pháp cấu hình của hệ thống PAM:

```yaml
interactive_access_exception:
  workload: invoice-worker
  environment: production
  runtime_principal: svc_invoice_prod
  requester_identity: operator-example
  reason: "Chẩn đoán lỗi truy cập tài nguyên dưới đúng ngữ cảnh runtime"
  approval_reference: change-example-42
  allowed_entry_point: controlled-administration-path
  allowed_actions:
    - inspect-sanitized-runtime-metadata
    - execute-approved-diagnostic
  allowed_targets:
    - approved-invoice-resource
  start_time: approved-start-time
  expiry_time: approved-end-time
  credential_disclosure: prohibited-unless-explicitly-required
  evidence:
    - requester-and-approval-record
    - access-session-or-command-audit
    - target-system-events
    - restoration-result
  closure:
    - remove-temporary-access
    - verify-interactive-denial-restored
    - assess-credential-and-session-revocation
    - verify-service-health
```

Thời hạn trong tài liệu cần được thực thi bằng cơ chế phù hợp. Một ticket hết hạn không tự xóa nhóm quyền đã thêm hoặc kết thúc phiên còn sống.

Với break-glass, vẫn cần người sử dụng được nhận diện, phạm vi truy cập và hậu kiểm. Tình huống khẩn cấp có thể thay đổi trình tự phê duyệt theo chính sách, nhưng không làm mất yêu cầu xử lý quyền tạm thời và bằng chứng.

## 13. Quy trình triển khai hạn chế an toàn

### Bước 1: Xác định đúng account và chủ sở hữu

Ghi định danh ổn định của account, workload sử dụng, môi trường, host và người chịu trách nhiệm.

Không chỉ dựa vào tên hiển thị. Account trùng tên ở hai miền hoặc hai môi trường có thể là hai principal khác nhau.

### Bước 2: Kiểm kê đường sử dụng hiện tại

Kết hợp cấu hình và audit để nhận diện:

- Service đang chạy.
- Job theo lịch.
- Đăng nhập console, desktop hoặc shell.
- Lệnh từ xa và luồng chuyển tệp.
- Công cụ hỗ trợ, script bảo trì và tác vụ ít chạy.
- Quyền chuyển user hoặc sử dụng danh tính.
- Credential được phân phối tới đâu.

Không thu thập giá trị secret vào bảng kiểm kê. Chỉ cần thông tin vị trí quản lý, loại credential và chủ thể được phép sử dụng.

Việc không thấy log trong một khoảng thời gian ngắn không chứng minh đường truy cập không còn cần thiết. Đối chiếu lịch nghiệp vụ và tài liệu vận hành.

### Bước 3: Hoàn thiện ma trận cho phép và từ chối

Để chủ workload xác nhận nhu cầu chức năng; chủ tài nguyên và bên quản trị danh tính xác nhận phạm vi quyền.

Ghi rõ các phụ thuộc chưa được giải thích. Nếu tác vụ bảo trì đang dùng shell dưới service account, cần tạo đường thay thế hoặc xử lý ngoại lệ có phạm vi trước khi chặn.

### Bước 4: Thử nghiệm trên phạm vi đại diện

Áp dụng cấu hình trên môi trường hoặc nhóm máy thử nghiệm được phép. Kiểm tra cả:

- Khởi động mới, không chỉ tiến trình đã chạy sẵn.
- Kết nối lại sau khi hết phiên hoặc thay credential.
- Job theo lịch.
- Failover hoặc khởi động ở nút khác.
- Đăng nhập tương tác và các đường không có terminal.
- Đường vận hành thay thế bằng danh tính cá nhân.

Nếu chỉ thử khi connection pool cũ vẫn hoạt động, có thể bỏ sót lỗi sẽ xuất hiện sau lần khởi động kế tiếp.

### Bước 5: Triển khai theo đợt và quan sát

Ghi lại phiên bản chính sách, account và host đích, thời điểm hiệu lực, người thực hiện và điều kiện quay lui.

Không thay đổi đồng loạt nhiều lớp độc lập nếu điều đó làm khó xác định nguyên nhân khi service dừng. Chọn đợt triển khai phù hợp với khả năng quan sát và mức ảnh hưởng.

Quay lui phải có phạm vi và thời hạn. Nếu cần phục hồi một quyền tương tác để bảo đảm dịch vụ, ghi nhận đó là ngoại lệ còn mở, không coi việc quay lui là kết thúc công việc.

### Bước 6: Xác minh và đóng thay đổi

Xác nhận những đường không cần thiết đã bị từ chối, workload hợp lệ vẫn chạy và người vận hành sử dụng được công cụ thay thế.

Rà soát phiên tồn tại, credential đã từng được phân phối và quyền tạm thời. Cập nhật hồ sơ account và hướng dẫn xử lý sự cố.

## 14. Bộ kiểm thử nên có

Các phép thử phải được thực hiện trong phạm vi được phép và có kế hoạch tránh khóa nhầm account hoặc gây gián đoạn.

| Phép thử | Kỳ vọng | Điều cần lưu ý |
| --- | --- | --- |
| Đăng nhập console bằng service account | Bị từ chối nếu không có nhu cầu | Kiểm tra đúng máy và chính sách hiệu lực |
| Đăng nhập desktop từ xa | Bị từ chối nếu không có nhu cầu | Đây có thể là quyền khác với console |
| Mở shell SSH | Bị từ chối nếu không có nhu cầu | Thử cơ chế xác thực thực tế, không chỉ password |
| Chạy lệnh SSH không có terminal | Bị từ chối ngoài luồng được duyệt | Cấm terminal đơn thuần chưa đủ |
| Chuyển sang UID service qua công cụ nâng quyền | Bị từ chối hoặc chỉ cho phép tác vụ đã định nghĩa | Kiểm tra cả script, tham số và quyền sửa file |
| Khởi động lại service hợp lệ | Thành công dưới principal đúng | Không chỉ dựa vào tiến trình cũ |
| Chạy job theo lịch | Thành công nếu đây là nhu cầu được duyệt | Kiểm tra kiểu đăng nhập và nguồn credential |
| Lấy credential runtime bằng vai trò chỉ xem trạng thái | Bị từ chối | Quyền quan sát không nên bao gồm quyền đọc secret |
| Mở phiên thực thi hoặc sửa workload bằng vai trò chỉ xem | Bị từ chối | Quan trọng với container và cloud |
| Hết hạn ngoại lệ | Quyền mới bị từ chối và phiên cũ được xử lý theo thiết kế | Hết hạn ticket không đồng nghĩa hết phiên |
| Kích hoạt tác vụ chẩn đoán hợp lệ | Thành công, có danh tính người và runtime | Không trả credential trong kết quả |

Một phép thử “bị từ chối” cần ghi rõ đường truy cập, principal, phương thức và thời điểm. Không suy rộng một kết quả SSH password sang SSH key hoặc API token.

Nếu cơ chế cho phép xác thực nhưng từ chối tạo phiên hoặc từ chối thao tác, cần ghi đúng giai đoạn bị chặn. Điều đó giúp phân biệt kiểm soát nào thực sự có hiệu lực.

## 15. Giám sát và bằng chứng điều tra

Tối thiểu, cần liên kết được:

- Principal của service.
- Host hoặc workload liên quan.
- Kiểu đăng nhập hoặc đường truy cập.
- Nguồn kết nối khi hệ thống ghi nhận được.
- Kết quả và thời điểm.
- Người khởi tạo, nếu đi qua đường quản trị có nhận diện.
- Mã phiên, mã thực thi hoặc mã thay đổi dùng để tương quan.

Ví dụ sự kiện chuẩn hóa minh họa:

```json
{
  "event_type": "service_identity_access_attempt",
  "principal_id": "svc_invoice_prod",
  "workload": "invoice-worker",
  "environment": "production",
  "entry_point": "remote-shell",
  "interaction_mode": "human-operated",
  "source_host": "administration-host-example",
  "target_host": "invoice-runtime-example",
  "operator_id": "operator-example",
  "approval_reference": null,
  "result": "denied",
  "correlation_id": "access-attempt-example"
}
```

Không phải mọi nguồn log đều cung cấp đầy đủ trường trên. Đặc biệt, `operator_id` chỉ có ý nghĩa khi được nối từ nguồn xác thực đáng tin cậy; không được tự gán từ một chuỗi do người gọi nhập.

Các tín hiệu đáng điều tra gồm:

- Service account đăng nhập tương tác lần đầu hoặc ngoài ngoại lệ được duyệt.
- Đăng nhập từ máy quản trị cá nhân hoặc nguồn chưa được xác nhận.
- Thay đổi shell, quyền đăng nhập, nhóm quyền hoặc khóa xác thực.
- Người có quyền xem trạng thái bắt đầu đọc secret hoặc sử dụng danh tính runtime.
- Phiên ngoại lệ vẫn hoạt động sau thời hạn.
- Dịch vụ chuyển từ principal dự kiến sang principal khác.
- Nhiều lần đăng nhập thất bại sau khi triển khai chính sách.

Không tự kết luận mọi lần thất bại đều là tấn công. Có thể tồn tại job hợp lệ bị bỏ sót. Cần xác minh nguồn và mục đích; không tự mở lại quyền rộng chỉ để làm cảnh báo biến mất.

Log phiên hoặc bản ghi màn hình có thể chứa dữ liệu nhạy cảm. Cần kiểm soát quyền xem, thời gian lưu và việc xuất bằng chứng. Password, token và private key không nên xuất hiện trong bản ghi chẩn đoán.

## 16. Xử lý khi phát hiện đăng nhập bất thường

Khi service account xuất hiện trong một phiên không được duyệt, mục tiêu là xác định phạm vi sử dụng và ngăn tiếp tục lạm dụng mà vẫn kiểm soát tác động tới dịch vụ.

Quy trình cần phối hợp chủ workload, đội vận hành và người xử lý sự cố:

1. Xác định principal, đường vào, host, thời điểm và phiên liên quan.
2. Bảo toàn log và bằng chứng cần thiết trước khi chúng bị ghi đè.
3. Xác minh có ngoại lệ hợp lệ hay tác vụ tự động bị phân loại nhầm không.
4. Giới hạn hoặc kết thúc đường truy cập không được phép theo kế hoạch ứng phó.
5. Đánh giá credential nào đã bị lộ, quyền nào đã được sử dụng và tài nguyên nào bị tác động.
6. Xử lý password, key, token, phiên còn sống và quan hệ tin cậy theo từng cơ chế.
7. Kiểm tra sức khỏe workload và phục hồi qua đường được kiểm soát.
8. Loại bỏ nguyên nhân khiến đường truy cập được mở quá rộng.

Không giả định đổi password sẽ thu hồi mọi token hoặc kết thúc mọi kết nối. Không giả định khóa account là thao tác không ảnh hưởng service. Quyết định cô lập cần dựa trên mức khẩn cấp và kế hoạch ứng phó đã được phê duyệt.

Nếu một người đã được phép dùng credential nhưng sử dụng ngoài phạm vi, vấn đề còn bao gồm thiết kế cấp quyền, khả năng truy cập ngoài cổng kiểm soát và bằng chứng về hành động. Chỉ nhắc người đó “không làm nữa” không tạo ra ranh giới kỹ thuật.

## 17. Những lỗi thiết kế dễ gặp

### “Service account không có password nên không thể bị dùng tương tác”

Account có thể dùng key, token, chứng thư hoặc được một chủ thể khác sử dụng thông qua quyền quản trị nền tảng. Cần kiểm tra toàn bộ đường xác thực và thực thi.

### “Đã cấm terminal nên không chạy được lệnh”

Nhiều cơ chế thực thi không cần terminal. Phải kiểm tra khả năng chạy lệnh, chuyển tệp, sử dụng subsystem hoặc sửa workload theo đúng môi trường.

### “Đã khóa shell nên không cần kiểm soát sudo hoặc công cụ quản trị”

Người có quyền chạy tiến trình dưới UID service có thể không đi qua shell đăng nhập. Quyền nâng quyền và quyền sửa nội dung thực thi cần được đánh giá riêng.

### “Cho phép account đăng nhập để dễ bảo trì, rồi dựa vào cam kết của đội”

Cam kết không phân biệt được các phiên trong log và không ngăn credential bị dùng ngoài quy trình. Cần đường vận hành theo danh tính cá nhân và ngoại lệ được thực thi.

### “Cấm mọi kiểu đăng nhập là cách chắc chắn nhất”

Điều đó có thể chặn cả service hoặc job hợp lệ. Thiết kế đúng phải phân biệt đường không cần thiết với đường thực thi bắt buộc.

### “Có PAM ghi hình thì cho dùng chung credential lâu dài cũng đủ”

Bản ghi giúp điều tra trong đường được ghi nhận. Nếu credential được mang ra ngoài hoặc có đường truy cập trực tiếp, việc ghi hình không bao phủ hoạt động đó.

### “Một lần kiểm thử thành công chứng minh chính sách áp dụng toàn hệ thống”

Chính sách có thể khác giữa host, nhóm máy hoặc nút khôi phục. Phải xác định phạm vi kiểm chứng và xử lý sự khác biệt.

## 18. Bài tập tình huống

Một account `svc_reconciliation` chạy dịch vụ đối soát và một job tổng hợp cuối tuần. Khi có lỗi, kỹ sư dùng account đó để đăng nhập từ xa, mở công cụ database và sửa trạng thái giao dịch.

Account đang có quyền chạy dịch vụ, chạy job, mở phiên desktop và sửa nhiều bảng. Credential được lưu trong vault nhưng nhiều người được phép xem password. Hướng dẫn vận hành ghi: “Khi service lỗi, đăng nhập bằng account service để kiểm tra”.

### Yêu cầu

- Xác định những luồng nào là chức năng workload và những luồng nào là thao tác của người.
- Đề xuất ma trận đăng nhập cho dịch vụ, job và người vận hành.
- Thiết kế cách xem log, restart và chẩn đoán mà không mặc định cấp password runtime.
- Xác định thứ tự thay đổi để không làm hỏng job cuối tuần.
- Xây dựng ngoại lệ nếu có lỗi chỉ tái hiện được dưới đúng danh tính runtime.
- Nêu bằng chứng cần có trước khi đóng thay đổi.

### Hướng phân tích

Đầu tiên, tách quyền chạy dịch vụ và job khỏi quyền thao tác desktop. Việc sửa trạng thái giao dịch là một hành động nghiệp vụ hoặc quản trị dữ liệu riêng, cần được phê duyệt và truy vết bằng danh tính cá nhân. Nó không nên trở thành quyền mặc định của account đối soát chỉ để thuận tiện.

Tiếp theo, xác định dịch vụ và job có thực sự cần cùng principal không. Nếu phạm vi quyền hoặc vòng đời khác nhau đáng kể, cân nhắc tách danh tính. Nếu vẫn dùng chung theo thiết kế, phải kiểm chứng cả hai luồng trước khi thay quyền đăng nhập.

Đường vận hành mới cần cho phép xem log phù hợp, xem trạng thái và thực hiện thao tác giới hạn như restart. Những tác vụ sửa dữ liệu phải dùng quy trình riêng với quyền và bằng chứng rõ ràng.

Chỉ thu hồi quyền desktop sau khi đường thay thế được thử nghiệm và có kế hoạch xử lý job cuối tuần. Không dùng kết quả dịch vụ chạy tốt vào ngày thường để kết luận job ít chạy cũng không bị ảnh hưởng.

Nếu cần chẩn đoán dưới danh tính runtime, ưu tiên một phép thử có giới hạn. Khi bắt buộc mở phiên, cấp ngoại lệ có thời hạn, gắn người thực hiện, kiểm soát đường vào và xử lý credential hoặc phiên sau sử dụng.

Bằng chứng đóng thay đổi phải có cấu hình hiệu lực, thử từ chối các đường không cần thiết, kết quả dịch vụ và job chạy lại, việc thu hồi quyền xem credential không cần thiết, cùng hướng dẫn vận hành mới.

## 19. Tiêu chí hoàn thành

Hạn chế interactive login của service account đạt yêu cầu khi:

- Mỗi đường đăng nhập hoặc sử dụng danh tính đều có mục đích được giải thích.
- Console, desktop, shell và các đường thực thi tùy ý không cần thiết bị hạn chế bằng kiểm soát phù hợp.
- Dịch vụ, job và truy cập tài nguyên hợp lệ vẫn hoạt động sau khởi động hoặc kết nối mới.
- Người vận hành có đường làm việc bằng danh tính cá nhân và quyền đúng phạm vi.
- Quyền đọc credential, chuyển user, sử dụng danh tính và sửa workload đã được xét cùng nhau.
- Ngoại lệ có thời hạn được thực thi, được đóng và được kiểm chứng.
- Log đủ để phân biệt hành động của người với hoạt động của workload ở mức hệ thống hỗ trợ.
- Hồ sơ và thử nghiệm chỉ rõ giới hạn còn tồn tại, thay vì tuyên bố chặn toàn bộ từ một cấu hình đơn lẻ.

Service account cần quyền để thực hiện nhiệm vụ đã được giao. Con người cần một đường quản trị có danh tính, phạm vi và bằng chứng riêng. Kiểm soát interactive login giữ hai nhu cầu đó rõ ràng, đồng thời tạo nền tảng cho least privilege, quản lý credential và ứng phó sự cố trong PAM.
