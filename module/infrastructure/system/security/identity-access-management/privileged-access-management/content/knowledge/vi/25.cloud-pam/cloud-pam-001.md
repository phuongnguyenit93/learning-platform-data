# Cloud root account

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Phân biệt danh tính gốc của tài khoản cloud với tài khoản quản trị thông thường và quyền root trong máy ảo.
- Kiểm kê toàn bộ đường đăng nhập, khôi phục và sử dụng đặc quyền gốc.
- Thiết kế bảo quản credential, MFA, phê duyệt và truy cập khẩn cấp phù hợp.
- Giải thích khác biệt giữa bảo vệ credential gốc còn tồn tại và quản lý quyền gốc tập trung trên tài khoản thành viên.
- Xác định bằng chứng cần có trước, trong và sau một lần sử dụng quyền gốc.

## 1. Cloud root account là gì?

Trong phạm vi bài này, **cloud root account** chỉ danh tính gốc có đặc quyền rất cao gắn với một tài khoản cloud. Tên gọi và mô hình quyền không giống nhau giữa các nhà cung cấp. Không nên mặc định mọi nền tảng đều có một tài khoản tên root với hành vi giống nhau.

Ví dụ cụ thể là **AWS account root user**: danh tính đăng nhập ban đầu của một AWS account, có phạm vi quyền rất rộng trong account. AWS khuyến nghị chỉ sử dụng danh tính này cho công việc thực sự cần quyền gốc, thay vì công việc hằng ngày. [Tài liệu AWS về account root user](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_root-user.html).

Trong PAM, quyền gốc cần được xem là một tài sản đặc quyền trọng yếu. Giá trị cần bảo vệ không chỉ là mật khẩu, mà còn là khả năng:

- Đăng nhập hoặc nhận credential có quyền gốc.
- Khôi phục quyền truy cập khi mất mật khẩu hoặc MFA.
- Thay đổi người kiểm soát kênh khôi phục.
- Kích hoạt một luồng đặc quyền từ hệ thống quản lý tập trung.
- Duy trì quyền truy cập sau khi một phiên được coi là đã kết thúc.

### 1.1. Ba khái niệm dễ bị nhầm

| Khái niệm | Phạm vi | Ví dụ hậu quả |
|---|---|---|
| Danh tính gốc của account cloud | Quyền ở lớp tài khoản và quản lý dịch vụ | Thay đổi kiểm soát tài khoản hoặc tài nguyên cloud |
| Danh tính quản trị được cấp quyền | Những quyền được chính sách và phạm vi cho phép | Quản lý một nhóm dịch vụ hoặc môi trường |
| Root trong hệ điều hành máy ảo | Quyền bên trong hệ điều hành đó | Sửa tệp, tiến trình hoặc cấu hình máy ảo |

Chiếm được root trong một máy ảo không tự động có nghĩa đã chiếm account root của cloud. Tuy nhiên, nếu máy ảo chứa credential cloud hoặc có danh tính workload mạnh, kẻ tấn công có thể dùng chúng để di chuyển sang lớp quản lý cloud.

Ngược lại, quyền ở lớp cloud có thể cho phép thay đổi hạ tầng hoặc các thành phần liên quan đến máy ảo, nhưng đường tác động cụ thể phụ thuộc dịch vụ, chính sách và cấu hình. Không đồng nhất hai lớp quyền để rồi bỏ sót một lớp khi kiểm kê.

### 1.2. Quản lý gốc khác với tài khoản quản trị hằng ngày

Một người quản trị có thể thực hiện công việc thông thường bằng danh tính cá nhân và quyền có giới hạn. Danh tính gốc cần một quy trình khác vì hậu quả rộng, tần suất sử dụng thấp và khả năng quy trách nhiệm trực tiếp thường khó hơn khi nhiều người cùng có khả năng truy cập.

Thiết kế tốt làm giảm số công việc cần chạm tới quyền gốc. Việc dùng root thường xuyên vì “tiện hơn” thường phản ánh thiếu phân quyền, thiếu runbook hoặc công cụ vận hành chưa phù hợp.

## 2. Vì sao quyền gốc là điểm rủi ro đặc biệt?

### 2.1. Phạm vi ảnh hưởng có thể rất rộng

Một credential đặc quyền ở cấp account có thể tác động tới nhiều dịch vụ cùng lúc. Các hậu quả cần đánh giá gồm:

- Tăng quyền cho danh tính khác.
- Thay đổi cấu hình bảo vệ hoặc nguồn nhật ký.
- Tạo credential hoặc đường truy cập mới.
- Làm gián đoạn tài nguyên quan trọng.
- Tác động tới chi phí, dữ liệu hoặc khả năng khôi phục.
- Thay đổi thông tin tài khoản và kênh liên hệ.

Đây là các nhóm hậu quả cần khảo sát, không phải khẳng định rằng mọi nhà cung cấp đều cho root thực hiện mọi hành động. Quyền hiệu lực và ngoại lệ phải được kiểm tra theo nền tảng.

### 2.2. Khôi phục có thể trở thành một đường đăng nhập khác

Giả sử mật khẩu được bảo vệ trong vault và MFA do một người khác giữ. Nếu cùng một người vẫn có thể đọc email khôi phục, kiểm soát số điện thoại và thay người quản lý hộp thư, việc tách mật khẩu và MFA chưa giải quyết đầy đủ rủi ro.

Cần xem chuỗi khôi phục như một phần của hệ thống đặc quyền:

~~~text
Người quản trị kênh liên hệ
        ↓
Hộp thư / điện thoại / cơ chế xác minh
        ↓
Khôi phục khả năng đăng nhập
        ↓
Danh tính gốc của account cloud
        ↓
Tài nguyên và kiểm soát cấp account
~~~

Sơ đồ mô tả mối phụ thuộc cần đánh giá. Không hàm ý nhà cung cấp nào cũng dùng cùng một chuỗi khôi phục.

### 2.3. Danh tính chung làm giảm khả năng quy trách nhiệm

Nhật ký có thể cho biết quyền gốc đã được dùng nhưng không tự giải thích người nào đã được phê duyệt, ai lấy credential và ai thực hiện từng bước.

PAM cần liên kết danh tính cá nhân, yêu cầu truy cập, lần cấp quyền, phiên và hành động cloud. Không dùng một tài khoản vault chung cho cả đội rồi kỳ vọng nhật ký cloud sẽ khôi phục được danh tính người thực hiện.

## 3. Kiểm kê quyền gốc trước khi chọn biện pháp

Một bản kiểm kê nên tập trung vào metadata, không thu thập giá trị bí mật.

| Nhóm thông tin | Nội dung cần biết |
|---|---|
| Định danh tài khoản | Nhà cung cấp, account ID, môi trường và đơn vị sở hữu |
| Vai trò trong tổ chức | Độc lập, quản lý trung tâm hoặc thành viên |
| Trách nhiệm | Owner nghiệp vụ, owner bảo mật và người trực xử lý |
| Mô hình truy cập gốc | Credential trực tiếp còn tồn tại hay quản lý tập trung |
| Credential | Có mật khẩu, access key, chứng thư hoặc loại khác không |
| MFA | Loại yếu tố, người giữ, nơi lưu và phương án dự phòng |
| Khôi phục | Kênh liên hệ, người kiểm soát và phụ thuộc bên ngoài |
| Sử dụng | Lần dùng gần nhất, mục đích và bằng chứng liên quan |
| Giám sát | Nguồn audit, nơi lưu, người nhận cảnh báo và kiểm thử gần nhất |
| Khẩn cấp | Runbook, phê duyệt thay thế và mục tiêu thời gian tiếp cận |
| Ngoại lệ | Phạm vi, lý do, người chịu trách nhiệm và hạn xử lý |

### 3.1. Ghi nhận trạng thái rõ ràng

“Không có thông tin” khác với “đã xác minh không tồn tại credential”. Tương tự, “chưa thấy root được dùng” khác với “không có khả năng đăng nhập root”.

Nên phân biệt các trạng thái như:

- Chưa kiểm tra.
- Có credential đang hoạt động.
- Có credential nhưng trạng thái chưa xác minh.
- Đã loại bỏ credential theo cơ chế được hỗ trợ.
- Có khả năng khôi phục trực tiếp.
- Khôi phục chỉ được mở thông qua quản lý tập trung.

Tên trạng thái có thể khác trong triển khai thực tế; điều quan trọng là không biến thiếu dữ liệu thành kết luận an toàn.

### 3.2. Account cũ, thử nghiệm và mua lại đều nằm trong phạm vi

Một account thử nghiệm vẫn có thể giữ dữ liệu, kết nối hoặc phương thức thanh toán. Một account do nhân viên cũ tạo có thể gắn với email cá nhân. Account từ một thương vụ mua lại có thể chưa có owner hoặc quy trình khôi phục thống nhất.

Không nên chỉ kiểm kê account đang chạy sản xuất. Cần bao phủ vòng đời từ lúc tạo đến khi ngừng sử dụng.

## 4. Hai mô hình bảo vệ cần phân biệt

### 4.1. Mô hình A: credential gốc trực tiếp còn tồn tại

Tổ chức vẫn duy trì khả năng đăng nhập trực tiếp bằng cơ chế gốc của nền tảng. Khi đó phải bảo vệ credential, yếu tố bổ sung và các kênh khôi phục, đồng thời giới hạn việc sử dụng qua quy trình PAM.

Mô hình này có thể áp dụng khi nền tảng hoặc loại account chưa hỗ trợ cách quản lý khác. Không vì mục tiêu “không có root thường trực” mà tự ý xóa thành phần đăng nhập khi chưa có đường khôi phục được kiểm tra.

### 4.2. Mô hình B: quản lý quyền gốc tập trung cho account thành viên

AWS hỗ trợ tập trung quản lý root access cho member account trong AWS Organizations. Trong mô hình được cấu hình phù hợp, có thể loại bỏ credential gốc của member account và thực hiện một số công việc đặc quyền thông qua quản lý tập trung. Cơ chế bật lại khả năng khôi phục cũng cần được kiểm soát. [Tài liệu AWS về quản lý root access tập trung](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_root-enable-root-access.html).

Điểm thiết kế PAM ở đây là chuyển trọng tâm kiểm soát: từ bảo quản nhiều bộ credential gốc sang bảo vệ danh tính, quyền và quy trình tại lớp quản lý tập trung.

Không hiểu “đã xóa credential của member account” là “không còn đường đặc quyền”. Đường quản lý tập trung, người có thể thay đổi nó và khả năng mở lại khôi phục đều là tài sản đặc quyền cần kiểm kê.

### 4.3. Không áp dụng nhầm giữa các loại account

Trước khi thay đổi, xác định rõ:

1. Đây là account độc lập, account quản lý hay account thành viên?
2. Cơ chế quản lý tập trung có áp dụng cho loại account này không?
3. Những tác vụ cần thiết có được cơ chế đó hỗ trợ không?
4. Nếu lớp quản lý trung tâm lỗi, đường xử lý được phép là gì?
5. Ai có thể thay đổi tính năng hoặc quyền quản lý?

Một cấu hình hợp lý cho account thành viên không tự động là cấu hình hợp lý cho account quản lý.

## 5. Bảo vệ credential trực tiếp khi vẫn cần duy trì

Với AWS root user còn credential trực tiếp, tài liệu chính thức khuyến nghị bảo vệ mật khẩu, MFA, kênh khôi phục và tránh tạo root access key dài hạn. Tài liệu cũng nhấn mạnh khả năng phục hồi và phê duyệt nhiều người khi phù hợp. [Root user best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/root-user-best-practices.html).

Các mục dưới đây là cách triển khai kiểm soát PAM để vận hành những mục tiêu đó, không phải tính năng tự động có sẵn của mọi cloud.

### 5.1. Mật khẩu: bảo vệ cả giá trị và đường lấy giá trị

Mật khẩu cần đủ mạnh, riêng biệt và được lưu trong nơi quản lý bí mật đã được phê duyệt. Quan trọng không kém là:

- Ai được yêu cầu truy cập.
- Ai được phê duyệt.
- Ai có thể thay đổi chính sách của vault.
- Ai có thể xuất hoặc khôi phục dữ liệu vault.
- Hệ thống nào phụ thuộc vào credential đó để hoạt động.
- Có bằng chứng cho mỗi lần lấy hoặc sử dụng không.

Nếu phải cung cấp mật khẩu cho người vận hành, cần coi đó là một lần tiết lộ có kiểm soát. Thời hạn checkout trong vault không làm người đã biết mật khẩu tự quên giá trị. Khi cần chấm dứt khả năng tái sử dụng, phải xử lý credential theo chính sách và xác minh ở hệ thống đích.

Không ghi mật khẩu vào ticket hoặc bằng chứng phiên.

### 5.2. MFA: yếu tố xác thực không thay thế phê duyệt

MFA giúp chống việc đăng nhập chỉ bằng mật khẩu bị lộ. Nó không chứng minh thao tác được nghiệp vụ cho phép, không giới hạn đối tượng tác động và không xác định ai đã phê duyệt kế hoạch.

Khi nền tảng hỗ trợ, đánh giá yếu tố có khả năng chống phishing và bảo vệ tốt khóa xác thực. Đồng thời kiểm tra cách đăng ký, thay thế và khôi phục yếu tố, vì những thao tác đó có thể thay đổi người kiểm soát tài khoản.

Một người có quyền quản trị toàn bộ yếu tố MFA và toàn bộ đường khôi phục có thể có khả năng kiểm soát lớn hơn vẻ ngoài của một mô hình “hai người giữ hai phần”.

### 5.3. Dự phòng mà không tạo bản sao ngoài kiểm soát

Phương án dự phòng cần có chủ sở hữu, vị trí lưu, quyền tiếp cận và lịch kiểm tra. Nếu dùng nhiều thiết bị hoặc yếu tố dự phòng được nền tảng hỗ trợ, cần biết chính xác thiết bị nào còn hợp lệ và ai có thể sử dụng.

Tránh để bản dự phòng trở thành bản sao không được ghi nhận trong ngăn kéo cá nhân. Khi thay đổi người giữ, kiểm tra cả yếu tố dự phòng và các quyền quản lý kênh khôi phục.

### 5.4. Credential lập trình cần được xét riêng

Mật khẩu console, access key và credential tạm thời là các đường truy cập khác nhau. Bật MFA cho đăng nhập không tự chứng minh mọi yêu cầu API đều đòi xác nhận tương tác bằng MFA.

Không đưa credential root vào pipeline, mã nguồn, ảnh container hoặc cấu hình ứng dụng. Nếu một quy trình tự động đang dùng quyền gốc, cần xác định hành động thực sự cần thiết và chuyển sang danh tính workload có phạm vi phù hợp khi có thể.

Nếu có root access key lịch sử, cần kiểm kê phụ thuộc, lập kế hoạch loại bỏ, xác minh thu hồi và xử lý bản sao. Không chỉ xóa giá trị khỏi vault rồi kết luận key mất hiệu lực tại cloud.

## 6. Bảo vệ email, điện thoại và quyền sở hữu

Thông tin liên hệ của account không phải dữ liệu hành chính phụ. Nó có thể tham gia nhận cảnh báo, xác minh chủ sở hữu hoặc khôi phục.

### 6.1. Dùng trách nhiệm của tổ chức

Kênh liên hệ cần được tổ chức quản lý và duy trì khi nhân sự thay đổi. Nếu nhiều người cần xử lý thông báo, nên sử dụng quyền truy cập cá nhân có thể quy trách nhiệm thay vì chia sẻ một mật khẩu hộp thư.

Bản ghi owner cần nêu ai chịu trách nhiệm đảm bảo kênh còn hoạt động. Một địa chỉ email tồn tại nhưng không có người theo dõi không bảo đảm khả năng phản ứng.

### 6.2. Kiểm tra quyền thay đổi kênh

Cần khảo sát:

- Ai có thể đọc email nhận được?
- Ai có thể đổi luật chuyển tiếp?
- Ai có thể khôi phục hộp thư?
- Ai có thể cấp quyền đại diện cho hộp thư?
- Ai kiểm soát số điện thoại hoặc dịch vụ liên quan?
- Ai có thể sửa thông tin tài khoản tại nhà cung cấp cloud?

Nếu cùng một nhóm có thể đổi mọi kênh và tự phê duyệt sử dụng root, cần đánh giá lại phân tách trách nhiệm.

### 6.3. Tránh vòng phụ thuộc khi khẩn cấp

Ví dụ, credential gốc được lưu trong một vault mà việc mở khóa chỉ thực hiện được qua đúng account cloud đang bị khóa. Khi sự cố xảy ra, credential vẫn tồn tại nhưng không thể tiếp cận.

Cần vẽ mối phụ thuộc giữa cloud, vault, hệ thống danh tính, email và thiết bị xác thực. Phương án khẩn cấp phải tiếp cận được trong những tình huống đã chọn, đồng thời vẫn bảo vệ bí mật và bằng chứng.

Không giải quyết vòng phụ thuộc bằng cách gửi một bản mật khẩu cho nhiều người. Hãy thiết kế một đường dự phòng được kiểm soát và kiểm thử.

## 7. Quyền tối thiểu, JIT và giới hạn thực tế

### 7.1. Công việc thông thường nên có đường phân quyền riêng

Đội vận hành cần danh tính cá nhân hoặc danh tính workload tương ứng với nhiệm vụ. Quyền quản trị có thể được cấp tạm thời theo nhu cầu, giới hạn môi trường và hành động.

Một lỗi triển khai không nên tự động dẫn tới việc dùng root. Trước hết cần xác định quyền nào thiếu, chính sách nào từ chối và công việc có thực sự cần quyền gốc hay không.

### 7.2. Cửa sổ truy cập ngắn không làm root thành quyền hẹp

Nếu một người được lấy mật khẩu root trong mười phút, cửa sổ tiếp cận ngắn hơn nhưng quyền của lần đăng nhập đó không tự trở thành “chỉ được sửa một cấu hình”.

Phải phân biệt:

- **Giới hạn quy trình:** chỉ được yêu cầu và sử dụng trong một khoảng thời gian.
- **Giới hạn kỹ thuật:** hệ thống đích chỉ cho phép một tập hành động hoặc tài nguyên.
- **Phát hiện và xử lý:** quan sát, cảnh báo và phản ứng khi có sai lệch.

Một quy trình chỉ có phê duyệt và ghi hình vẫn có thể cho phép người thực hiện gây hậu quả trước khi bị phát hiện. Nên giảm phạm vi kỹ thuật ở nơi nền tảng hỗ trợ.

### 7.3. Phiên đặc quyền tập trung có phạm vi riêng

Trong AWS, một số tác vụ trên member account có thể dùng phiên đặc quyền ngắn hạn với phạm vi tác vụ. Tài liệu nêu việc gọi **sts:AssumeRoot** cần danh tính IAM được cấp quyền trong management account hoặc delegated administrator; không gọi bằng root credential. Đây không phải cơ chế thay thế mọi tác vụ root tùy ý. [Thực hiện privileged task trên member account](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_root-user-privileged-task.html).

Về thiết kế PAM, người phê duyệt vẫn cần biết account đích, loại tác vụ, đối tượng và giới hạn. “Phiên ngắn hạn” không tự động giải quyết phê duyệt, quy trách nhiệm hoặc xác minh kết quả.

## 8. Không coi quyền gốc là vượt mọi kiểm soát

Hai phát biểu cực đoan đều dễ dẫn đến thiết kế sai:

- “Root làm được mọi thứ nên không có biện pháp hạn chế nào.”
- “Đã có chính sách tổ chức nên root ở đâu cũng bị hạn chế giống nhau.”

Với AWS Organizations, SCP không cấp quyền; nó giới hạn phạm vi quyền trong các member account, bao gồm root user của member account, với các ngoại lệ được tài liệu nêu. SCP không tác động đến management account theo cùng cách đó. [Tài liệu AWS về SCP](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html).

Hệ quả thiết kế là phải kiểm tra đúng loại account và đúng cơ chế. Không lấy kết quả thử trên member account để khẳng định account quản lý có cùng hàng rào.

Cũng không nên kỳ vọng quyền gốc tự khôi phục được mọi thứ. Dữ liệu đã bị hủy không có bản phục hồi, khóa mật mã không còn khả dụng hoặc hậu quả đã xảy ra bên ngoài có thể không đảo ngược được bằng việc đăng nhập root.

## 9. Runbook cho một lần sử dụng quyền gốc

### Bước 1: Chứng minh nhu cầu

Yêu cầu cần ghi rõ hành động, account, môi trường, tài nguyên và lý do không dùng quyền được ủy quyền thông thường.

Nếu viện dẫn “root-only”, phải đối chiếu tài liệu của nhà cung cấp và loại account hiện tại. Không giữ một danh sách tác vụ bất biến trong nhiều năm mà bỏ qua khả năng ủy quyền mới.

### Bước 2: Chọn đường thực hiện

Xác định có thể dùng phiên đặc quyền tập trung có phạm vi hay phải đăng nhập trực tiếp. Chọn đường đáp ứng nhiệm vụ với ít quyền và ít credential tồn tại hơn khi điều kiện cho phép.

Không khôi phục credential dài hạn chỉ vì người vận hành quen với đăng nhập console.

### Bước 3: Phê duyệt kế hoạch cụ thể

Kế hoạch cần nêu:

- Account ID và tài nguyên đích.
- Các thao tác dự kiến.
- Người thực hiện và người xác minh.
- Cửa sổ sử dụng.
- Điều kiện dừng.
- Tác động và phương án phục hồi.
- Bằng chứng cần thu thập.
- Credential hoặc khả năng truy cập cần được xử lý sau đó.

Người phê duyệt phải có thẩm quyền và tính độc lập phù hợp. Quyền sửa quy trình phê duyệt cũng cần được kiểm soát.

### Bước 4: Chuẩn bị môi trường và bằng chứng

Dùng thiết bị, đường truy cập và công cụ đã được tổ chức chấp nhận. Kiểm tra nguồn audit, nơi lưu bằng chứng và người nhận cảnh báo.

Nếu có ghi hình phiên, tránh làm lộ mật khẩu, mã MFA, token hoặc dữ liệu nhạy cảm. Ghi hình không bảo đảm mọi lệnh API hoặc tác vụ nền đều được quan sát.

### Bước 5: Cấp và sử dụng truy cập

Liên kết lần cấp với danh tính cá nhân. Xác nhận lại account đích trước thao tác. Thực hiện đúng phạm vi đã duyệt và dừng khi điều kiện thay đổi.

Không dùng khoảng truy cập này để làm thêm các công việc “tiện tay”, kể cả khi chúng có vẻ hữu ích.

### Bước 6: Xác minh kết quả và đóng truy cập

Kiểm tra kết quả tại hệ thống đích, thay đổi quyền, credential mới và trạng thái các tác vụ nền. Thực hiện đóng phiên, thu hồi hoặc xử lý credential theo cơ chế phù hợp.

Hết hạn yêu cầu trong PAM không tự chứng minh phiên cloud hoặc mọi credential phát sinh đã mất hiệu lực. Cần biết khả năng thu hồi thực tế và xử lý phần còn tồn tại.

### Bước 7: Đóng hồ sơ sau khi đủ bằng chứng

Người xác minh đối chiếu thao tác thực tế với kế hoạch. Nếu còn điểm chưa rõ, giữ trạng thái chưa hoàn tất, nêu owner và thời hạn xử lý.

## 10. Giám sát và bằng chứng

### 10.1. Những sự kiện cần theo dõi

Thiết kế giám sát nên quan tâm:

- Đăng nhập và sử dụng quyền gốc.
- Cấp phiên đặc quyền từ hệ thống quản lý tập trung.
- Tạo, thay đổi hoặc xóa credential gốc.
- Thay đổi yếu tố xác thực và kênh khôi phục.
- Bật lại khả năng khôi phục đã bị đóng.
- Sửa chính sách, người phê duyệt hoặc quyền quản lý tập trung.
- Thay đổi nguồn audit và cấu hình bảo vệ log.
- Hành động đặc quyền không khớp một yêu cầu đã duyệt.

AWS có mô hình giám sát root activity bằng CloudTrail kết hợp xử lý sự kiện và thông báo tập trung. Đây là một ví dụ triển khai, cần kiểm tra cấu hình và độ bao phủ trong môi trường thực. [Mô hình AWS giám sát root user activity](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/monitor-iam-root-user-activity.html).

### 10.2. Phải kiểm thử cả đường trực tiếp lẫn đường tập trung

Một bộ lọc chỉ nhận dạng đăng nhập root trực tiếp có thể chưa bao phủ cách cấp phiên đặc quyền tập trung. Cần dùng sự kiện thực tế trong môi trường kiểm thử để xác nhận loại danh tính, account nguồn, account đích và cách liên kết phiên với hành động.

Không coi tên một trường hoặc một mẫu sự kiện là vĩnh viễn đúng cho mọi đường truy cập. Nội dung rule phải đi cùng phiên bản triển khai và kết quả kiểm thử.

### 10.3. Hồ sơ tối thiểu cho một lần sử dụng

| Giai đoạn | Bằng chứng cần liên kết |
|---|---|
| Yêu cầu | Người yêu cầu, lý do, account và phạm vi |
| Phê duyệt | Người duyệt, thẩm quyền, thời điểm và phiên bản kế hoạch |
| Cấp truy cập | Danh tính cá nhân, đường truy cập, thời hạn và mã liên kết |
| Thực thi | Phiên, hành động, tài nguyên và kết quả |
| Xác minh | Người kiểm tra, kết quả cuối và sai lệch |
| Kết thúc | Trạng thái credential, phiên và ngoại lệ còn mở |

Audit không cần chứa giá trị secret. Dùng định danh, metadata và tham chiếu bằng chứng được bảo vệ.

### 10.4. Bảo vệ đường giám sát khỏi cùng một điểm lỗi

Nếu người sử dụng root có thể thay đổi cả dữ liệu nguồn lẫn toàn bộ bản sao bằng chứng, việc quy trách nhiệm bị suy yếu. Cần thiết kế quyền nơi nhận log, lưu giữ và cảnh báo với mức độc lập phù hợp.

Không tuyên bố “không thể sửa log” chỉ vì log đã gửi sang một nơi khác. Cần kiểm tra ai quản trị nơi nhận, ai sửa thời hạn lưu và điều gì xảy ra khi việc gửi log dừng.

## 11. Tình huống: account thành viên và đường đặc quyền tập trung

Một tổ chức có nhiều account thành viên. Một account bị cấu hình sai chính sách tài nguyên, khiến đội vận hành không thể sửa theo đường quản trị thông thường.

### 11.1. Phản ứng dễ gây mở rộng đặc quyền

Đội vận hành đề nghị khôi phục mật khẩu root, gửi mật khẩu cho người trực rồi giữ lại để dùng cho các sự cố sau.

Cách xử lý này có thể tạo thêm credential dài hạn, mở lại đường khôi phục và làm việc quy trách nhiệm khó hơn. Nó cũng có thể không cần thiết nếu tác vụ đã có đường đặc quyền tập trung phù hợp.

### 11.2. Quy trình đánh giá phù hợp

1. Xác nhận account đích là member account và kiểm tra cơ chế quản lý đang bật.
2. Xác định nguyên nhân từ chối; không mặc định mọi lỗi quyền đều cần root.
3. Kiểm tra tác vụ có nằm trong tập được nền tảng hỗ trợ qua phiên đặc quyền tập trung không.
4. Lập kế hoạch cho đúng tài nguyên và hậu quả của việc gỡ cấu hình sai.
5. Phê duyệt, cấp phiên qua danh tính cá nhân được cho phép.
6. Thực hiện đúng tác vụ, sau đó khôi phục cấu hình mong muốn bằng đường quản trị thích hợp.
7. Xác minh quyền truy cập và mức công khai của tài nguyên sau thay đổi.
8. Đối chiếu audit và đóng khả năng truy cập theo thiết kế.

Đây là quy trình quyết định, không phải chỉ dẫn rằng mọi lỗi chính sách đều có thể sửa bằng cùng một tác vụ. Phải kiểm tra giới hạn của cơ chế và tài nguyên cụ thể.

### 11.3. Nếu buộc phải mở lại credential

Khi nhiệm vụ thực sự cần đăng nhập trực tiếp, việc khôi phục phải là một thay đổi có chủ sở hữu, phê duyệt và kế hoạch kết thúc.

Sau khi xong, kiểm tra xem trạng thái mong muốn là duy trì credential được bảo vệ hay quay lại mô hình không có credential trực tiếp. Không chỉ đóng ticket mà để lại một đường đăng nhập mới ngoài kiểm kê.

## 12. Mất khả năng truy cập và ứng phó sự cố

### 12.1. Mất một yếu tố xác thực

Dùng phương án dự phòng được hỗ trợ và đã kiểm thử. Ghi nhận yếu tố bị mất, đánh giá khả năng bị sử dụng trái phép và xử lý yếu tố đó theo runbook.

Không bỏ qua MFA vô thời hạn vì một lần mất thiết bị. Cũng không xóa toàn bộ yếu tố còn hoạt động trước khi xác nhận đường thay thế.

### 12.2. Mất hộp thư hoặc kênh liên hệ

Kiểm tra quyền sở hữu, các thay đổi gần đây và quy trình hỗ trợ chính thức của nhà cung cấp. Người xử lý cần đi qua kênh được xác minh; thông tin về sự cố tài khoản là mục tiêu hấp dẫn cho social engineering.

Một runbook chỉ ghi “gọi hỗ trợ” nhưng không có người chịu trách nhiệm, kênh liên hệ và điều kiện xác minh chưa đủ cho vận hành khẩn cấp.

### 12.3. Nghi credential gốc bị lộ

Không giới hạn xử lý ở việc đổi mật khẩu. Cần đánh giá:

- Đường nào đã bị lộ: mật khẩu, key, token, MFA hay kênh khôi phục?
- Có phiên đang hoạt động hoặc credential khác đã được tạo không?
- Có danh tính mới, quyền mới hoặc thay đổi trust không?
- Có thay đổi audit, bảo vệ dữ liệu hoặc cấu hình tài khoản không?
- Những tài nguyên và dữ liệu nào bị tác động?
- Có tài khoản hoặc hệ thống liên quan bị xâm nhập không?

Thực hiện thu hồi, cô lập và phục hồi theo khả năng nền tảng và kế hoạch ứng phó. Nếu chưa xác minh được truy cập tồn dư, báo cáo phải thể hiện điều đó.

### 12.4. Thay đổi credential không xóa hậu quả đã xảy ra

Credential mới có thể ngăn một số cách xác thực tiếp theo, nhưng không tự khôi phục dữ liệu đã bị lấy, gỡ quyền đã cấp cho danh tính khác hoặc đảo ngược tác vụ đã hoàn tất.

Phục hồi cần dựa trên trạng thái thực tế và bằng chứng, không chỉ dựa trên việc một bước đổi mật khẩu thành công.

## 13. Vòng đời và bàn giao

### 13.1. Khi tạo account

Gắn owner, kênh liên hệ, mô hình root access và giám sát ngay từ đầu. Công việc bootstrap phải có điểm kết thúc: hoàn tất đường truy cập quản trị thông thường rồi đóng những khả năng tạm thời không còn cần thiết.

### 13.2. Khi thay nhân sự

Rà soát quyền vault, quyền đọc hoặc quản trị hộp thư, người giữ thiết bị, quyền phê duyệt và quyền quản lý tập trung.

Nếu người rời đi từng biết secret, đánh giá việc thay secret. Nếu họ chỉ mất quyền vault nhưng vẫn biết mật khẩu và còn một đường đăng nhập khác, kiểm soát chưa hoàn tất.

### 13.3. Khi chuyển loại account hoặc thay tổ chức quản lý

Đánh giá lại hàng rào, delegated administration, khôi phục và audit. Một thay đổi trong quan hệ tổ chức có thể làm giả định cũ về đường quản lý tập trung không còn đúng.

### 13.4. Khi ngừng sử dụng

Xác minh dữ liệu, nghĩa vụ lưu giữ, billing và quy trình đóng theo nhà cung cấp. Giữ bằng chứng cần thiết; không để credential của account đã bỏ quên tiếp tục nằm trong kho bí mật không có owner.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng root cho triển khai hằng ngày | Mở rộng tác động của lỗi và credential bị lộ | Dùng danh tính có phạm vi theo nhiệm vụ |
| Chỉ đưa mật khẩu vào vault | Bỏ sót MFA, recovery và quyền quản lý vault | Kiểm kê toàn bộ đường kiểm soát |
| Gắn root với email cá nhân | Mất quyền sở hữu khi nhân sự rời đi | Dùng kênh do tổ chức quản lý |
| Một người kiểm soát mọi yếu tố và phê duyệt | Phân tách trách nhiệm chỉ mang tính hình thức | Đánh giá quyền thực tế và đường khôi phục |
| Đặt root key trong pipeline | Credential mạnh được sao chép rộng | Chuyển sang danh tính workload thích hợp |
| Xóa credential khỏi kho nhưng chưa thu hồi tại cloud | Bí mật cũ vẫn có thể dùng | Xác minh trạng thái tại hệ thống đích |
| Coi checkout hết hạn là phiên cloud đã đóng | Có thể còn truy cập tồn dư | Kiểm tra và xử lý theo cơ chế phiên |
| Áp dụng mô hình member account cho management account | Bỏ sót khác biệt quyền và hàng rào | Phân loại account trước khi thiết kế |
| Xóa MFA đơn lẻ với lý do “centralize” | Có thể làm yếu đường đăng nhập vẫn tồn tại | Chỉ thay đổi theo toàn bộ workflow được hỗ trợ |
| Chỉ cảnh báo đăng nhập trực tiếp | Bỏ sót đường đặc quyền khác | Kiểm thử từng mô hình truy cập |
| Khôi phục root rồi giữ lại ngoài kế hoạch | Tạo đặc quyền thường trực mới | Định nghĩa trạng thái kết thúc và xác minh |
| Không kiểm thử khẩn cấp | Credential có nhưng không thể lấy đúng lúc | Diễn tập phụ thuộc và đường dự phòng |

## 15. Thực hành

### Bài tập 1: Vẽ đồ thị khôi phục

Một account có mật khẩu trong vault, MFA do đội bảo mật giữ và email trong hệ thống doanh nghiệp. Đội hạ tầng có thể quản trị vault lẫn hệ thống email.

Hãy vẽ ai kiểm soát từng thành phần, ai có thể cấp lại quyền và một người có thể đi qua những đường nào để lấy quyền gốc. Chỉ ra ít nhất hai thay đổi giúp tăng phân tách trách nhiệm mà vẫn đáp ứng khẩn cấp.

### Bài tập 2: Phân loại account

Bạn có một account độc lập, một account quản lý tổ chức và mười account thành viên.

Hãy lập bảng mô hình root access mong muốn cho từng loại. Ghi rõ điều kiện phải xác minh trước khi loại bỏ credential và bằng chứng cho thấy đường đặc quyền tập trung đã hoạt động.

### Bài tập 3: Phân tích bằng chứng đóng truy cập

Báo cáo ghi:

> Yêu cầu đã hết hạn trong PAM. Người dùng đã đăng xuất khỏi trang vault. Đã đóng quyền root.

Hãy chỉ ra các kết luận chưa được chứng minh. Cần kiểm tra gì về phiên cloud, credential đã lộ cho người dùng, token và thay đổi quyền được tạo trong lần sử dụng?

### Bài tập 4: Diễn tập mất hệ thống danh tính

Giả sử hệ thống danh tính doanh nghiệp lỗi, đồng thời cần thực hiện một tác vụ thực sự đòi quyền đặc biệt.

Hãy xác định đường tiếp cận đã được phê duyệt, người xác minh, nơi lấy bằng chứng và điều kiện dừng. Phương án không được phụ thuộc vào cùng thành phần đang lỗi mà không có giải pháp dự phòng.

### Bài tập 5: Đánh giá cảnh báo

Thiết kế một ca kiểm thử cho truy cập trực tiếp và một ca cho phiên đặc quyền tập trung. Nêu bằng chứng cần dùng để xác nhận sự kiện đến nơi nhận, được liên kết đúng account và có người phản hồi.

## 16. Điểm cần ghi nhớ

Cloud root account cần được quản lý như một chuỗi quyền sở hữu, xác thực, khôi phục và thực thi. Bảo vệ mật khẩu chỉ giải quyết một phần của chuỗi đó.

Mục tiêu PAM là giảm nhu cầu sử dụng quyền gốc, bảo vệ mọi đường còn tồn tại, cấp truy cập có mục đích và kiểm tra kết quả đến khi đóng quyền. Mô hình credential trực tiếp và mô hình quản lý tập trung cần những kiểm soát khác nhau; cả hai đều phải quy trách nhiệm được cho con người và có bằng chứng đáng tin cậy.
