Một tổ chức tạo khóa mã hóa cho hệ thống thanh toán bằng bộ sinh số ngẫu nhiên không đủ entropy trong giai đoạn khởi động; nhiều khóa được tạo ra có mẫu lặp và khó chứng minh tính không thể dự đoán.
Đội vận hành tạo khóa AES thủ công trên máy trạm cá nhân rồi chuyển qua email nội bộ tới máy chủ production; không có quy trình xác minh người nhận, bảo vệ bản sao tạm hoặc ghi nhận bàn giao.
Một khóa ký số được tạo bởi nhóm phát triển nhưng không có chủ sở hữu nghiệp vụ và ngày hết hạn; khi người phụ trách rời công ty, không ai biết hệ thống nào còn phụ thuộc vào khóa đó.
Kho khóa tập trung lưu private key, DEK và khóa dùng cho MAC trong cùng một vùng nhưng không phân loại mục đích; một nhóm vận hành có quyền đọc mọi loại khóa dù chỉ quản lý một dịch vụ.
Một tổ chức dùng cùng một key cho mã hóa dữ liệu, ký thông điệp và tạo token; sự cố ở một giao thức buộc phải thu hồi khóa dùng chung và ảnh hưởng nhiều hệ thống.
Ứng dụng lưu khóa mã hóa trong file cấu hình cùng máy chủ với ciphertext; kẻ chiếm quyền đọc filesystem có thể lấy cả dữ liệu lẫn khóa để giải mã.
Nhóm triển khai đưa master key vào biến môi trường của container; giá trị xuất hiện trong diagnostic dump và metadata của tiến trình khi hệ thống gặp sự cố.
Một nhà cung cấp dịch vụ lưu bản sao khóa bí mật trong hệ thống ticket để tiện hỗ trợ; nhiều nhân viên và nhà thầu có thể truy cập nội dung vượt quá nhu cầu.
Private key được lưu trong HSM nhưng tài khoản quản trị có thể xuất hoặc backup khóa không cần phê duyệt kép; mô hình bảo vệ phần cứng không còn giới hạn được hành vi quản trị.
Quy trình chia sẻ quyền quản trị HSM dùng chung một tài khoản cho nhiều nhân viên; audit log ghi nhận cùng một danh tính nên không thể quy trách nhiệm thao tác nhạy cảm.
Một cụm HSM yêu cầu quorum nhiều người để kích hoạt thao tác nhạy cảm nhưng các smart card dự phòng được cất chung trong một két do một cá nhân kiểm soát.
Khóa được nhập vào KMS bằng cơ chế BYOK nhưng đội triển khai không xác minh nguồn gốc, checksum và quy trình vận chuyển key material từ bên tạo khóa.
Một doanh nghiệp dùng external key manager nhưng kết nối KMS bị gián đoạn; ứng dụng không có chính sách xử lý cache hoặc dự phòng nên không thể giải mã dữ liệu trong thời gian outage.
Chính sách IAM của KMS cho phép mọi workload trong cùng cloud account gọi decrypt trên tất cả key; một service bị xâm nhập có thể mở rộng sang dữ liệu của hệ thống khác.
Một khóa dùng chung cho nhiều tenant được lưu trong KMS; lỗi kiểm tra tenant context ở tầng ứng dụng có thể khiến một tenant yêu cầu giải mã dữ liệu của tenant khác.
DEK được bọc bởi KEK trong envelope encryption nhưng bản ghi dữ liệu không lưu key identifier và version; sau nhiều lần rotation, hệ thống không biết phải gọi khóa nào để unwrap.
Đội vận hành xoay KEK nhưng không kiểm kê các bản backup và bản sao wrapped DEK; một số dữ liệu cũ không thể giải mã sau khi key version trước bị vô hiệu hóa.
Khóa mới được tạo và kích hoạt trên một số node nhưng các node còn lại vẫn mã hóa bằng key cũ; dữ liệu ghi từ hai nhóm instance không thể đọc nhất quán khi request được định tuyến chéo.
Một cryptoperiod được đặt cố định cho mọi khóa trong tổ chức dù khóa ký, khóa mã hóa dữ liệu lưu trữ và khóa phiên có mức độ phơi nhiễm khác nhau.
Chính sách rotation chỉ dựa trên số tháng kể từ ngày tạo khóa và không xét lượng dữ liệu đã mã hóa, số lần sử dụng hoặc dấu hiệu key compromise.
Một khóa ký số có cryptoperiod kết thúc nhưng các tài liệu đã ký trước đó vẫn cần xác minh trong nhiều năm; nhóm vận hành chưa xác định cách giữ bằng chứng khóa và trạng thái chứng thư tại thời điểm ký.
Khóa mã hóa dữ liệu được xoay vòng bằng cách ghi dữ liệu mới bằng key mới nhưng hệ thống không có kế hoạch đọc và re-encrypt dữ liệu cũ.
Trong lúc rotation, hệ thống ngừng chấp nhận key cũ ngay khi key mới được tạo; các bản ghi đang dùng key cũ không thể giải mã và giao dịch bị gián đoạn.
Một API gọi KMS cho mỗi thao tác mã hóa với tần suất cao; giới hạn request và độ trễ KMS làm tăng latency, trong khi cache key material không có thời hạn hoặc ranh giới bảo vệ rõ ràng.
Khóa được phân phối tới nhiều region bằng bản sao thủ công; một region nhận key version mới chậm hơn nên các dịch vụ đa vùng ký và xác minh không thống nhất.
Ứng dụng sử dụng key cache trong bộ nhớ sau khi quyền truy cập KMS bị thu hồi; các instance đang chạy tiếp tục dùng khóa đã bị vô hiệu hóa cho đến khi restart.
Một nhân viên đổi vai trò nhưng quyền truy cập KMS cũ không bị thu hồi; người đó vẫn có thể gọi decrypt hoặc tạo key cho hệ thống trước đây quản lý.
Service account tạo khóa tạm cho workload nhưng không có cơ chế gắn owner, mục đích, thời hạn và tự động dọn dẹp; kho KMS tích lũy nhiều key không còn ai chịu trách nhiệm.
Một khóa API của hệ thống backup được lưu cùng credential truy cập kho backup; khi máy chủ backup bị xâm nhập, kẻ tấn công có cả quyền lấy ciphertext và giải mã.
Quy trình backup HSM chỉ sao lưu cấu hình thiết bị mà không kiểm tra khả năng phục hồi key material hoặc quorum cần thiết trên thiết bị thay thế.
Doanh nghiệp giữ bản escrow của khóa giải mã để phục hồi dữ liệu nhưng không kiểm soát người được quyền yêu cầu mở escrow và không định kỳ diễn tập quy trình khôi phục.
Một người giữ duy nhất thông tin cần thiết để khôi phục master key nghỉ việc đột xuất; tổ chức không có cơ chế succession hoặc recovery độc lập.
Thảm họa tại vùng cloud chính làm mất quyền truy cập KMS region đó; bản sao ciphertext ở region dự phòng vẫn còn nhưng key replica và quyền sử dụng chưa được chuẩn bị.
Khóa được đánh dấu disabled trong KMS nhưng ứng dụng vẫn giữ bản sao plaintext trong bộ nhớ và tiếp tục xử lý request; nhóm vận hành cho rằng trạng thái disabled đã lập tức dừng mọi hoạt động.
Một chứng thư ký bị thu hồi sau khi private key nghi bị lộ nhưng các hệ thống xác minh chữ ký ngoại tuyến không cập nhật CRL hoặc trạng thái thu hồi tương ứng.
Private key ký phát hành phần mềm bị lộ; tổ chức chưa xác định các artifact đã ký trong khoảng thời gian nào có thể bị giả mạo và chưa có kế hoạch tái ký.
Khóa mã hóa backup bị lộ nhưng đội ứng phó chỉ thay key cho backup mới; các bản backup cũ vẫn có thể bị giải mã bởi bên đã lấy được ciphertext và khóa.
Khi nghi ngờ khóa bị xâm phạm, tổ chức chưa có danh mục hệ thống, dữ liệu, chứng thư và bản sao lưu phụ thuộc để xác định phạm vi ảnh hưởng.
Một khóa bị nghi lộ được thu hồi ngay nhưng chưa có key thay thế phân phối tới các dịch vụ phụ thuộc; các API và job định kỳ ngừng hoạt động trên diện rộng.
Đội ứng phó sự cố vô hiệu hóa key version cũ trước khi kiểm tra bản backup, log điều tra và nhu cầu xác minh chữ ký lịch sử; dữ liệu phục hồi không còn khả dụng.
Khóa mã hóa hết cryptoperiod được giữ hoạt động vô thời hạn vì một số hệ thống cũ chưa hỗ trợ rotation; không có ngoại lệ được phê duyệt hoặc biện pháp giảm thiểu.
Doanh nghiệp muốn xóa dữ liệu theo yêu cầu pháp lý bằng crypto-erasure nhưng vẫn giữ wrapped DEK trong snapshot và bản backup ngoài hệ thống chính.
Một KEK được hủy trong KMS nhưng bản sao key material đã export trước đó vẫn tồn tại trên thiết bị lưu trữ ngoại tuyến không có danh mục quản lý.
Quy trình tiêu hủy khóa yêu cầu nhiều người xác nhận nhưng log chỉ ghi kết quả cuối cùng, không ghi người phê duyệt, thời điểm và bằng chứng hoàn tất.
Một khóa đã bị destroy nhưng hệ thống chưa kiểm tra các bản replica, backup, HSM dự phòng và vùng disaster recovery; tổ chức không chứng minh được việc tiêu hủy hoàn tất.
Đội kiểm toán phát hiện inventory khóa không có algorithm, key size, owner, purpose, status, creation date và cryptoperiod nên không thể đánh giá khóa nào đã lỗi thời.
Log KMS ghi lại thao tác tạo, sử dụng và xóa key nhưng không đưa về kho audit bất biến; quản trị viên có quyền sửa log sau khi thực hiện thao tác nhạy cảm.
Chính sách phân tách nhiệm vụ yêu cầu người tạo khóa không được tự phê duyệt kích hoạt nhưng hệ thống workflow cho phép cùng một tài khoản thực hiện cả hai bước.
Một tổ chức có nhiều KMS và HSM của các nhà cung cấp khác nhau; không có chuẩn metadata chung nên inventory, rotation và thu hồi khóa không đồng nhất.
Ứng dụng chuyển từ thuật toán cũ sang thuật toán mới nhưng không lưu algorithm identifier và version cùng ciphertext; hệ thống không thể chọn đúng bộ giải mã cho dữ liệu lịch sử.
Một khóa gốc được dùng để dẫn xuất nhiều khóa con nhưng không ghi nhận context và mục đích từng khóa; thay đổi một giao thức làm tăng nguy cơ dùng nhầm key material.
Đội vận hành không theo dõi tuổi khóa, số lần gọi, lỗi xác minh chữ ký và tỷ lệ decrypt thất bại; dấu hiệu suy giảm hoặc lạm dụng khóa chỉ được phát hiện sau khi dịch vụ gặp sự cố.
Nhà cung cấp KMS thông báo thay đổi API hoặc ngừng hỗ trợ thuật toán đang dùng; tổ chức không có kế hoạch migration và kiểm thử tương thích trước ngày hết hỗ trợ.
Một khóa được tạo cho môi trường thử nghiệm nhưng do cấu hình sai lại được workload production tham chiếu; dữ liệu production phụ thuộc vào key có quyền và vòng đời không phù hợp.
Một workload cần ký thông điệp liên tục nhưng private key được phân phối trực tiếp tới từng container; số bản sao tăng theo quy mô triển khai và khó thu hồi đồng loạt.
Một hệ thống dùng HSM để ký nhưng failover sang phần mềm khi HSM quá tải; private key dự phòng được lưu trên đĩa mà không có mức bảo vệ tương đương.
Một tổ chức chuyển dữ liệu sang nhà cung cấp cloud mới nhưng không xác định quyền sở hữu và khả năng export hoặc hủy khóa ở nhà cung cấp cũ, làm phát sinh phụ thuộc kéo dài.
Một khóa được giữ lại để xác minh chữ ký lịch sử sau khi hết cryptoperiod nhưng không có trạng thái chỉ-verify; một dịch vụ vẫn có thể dùng nó để ký tài liệu mới.
Một đợt rotation khẩn cấp được thực hiện sau sự cố nhưng không có kế hoạch theo dõi tỷ lệ sử dụng key cũ; một số client tiếp tục gửi request bằng khóa sắp bị thu hồi.
Một quy trình cấp phát khóa tự động không kiểm tra người yêu cầu và workload identity; bất kỳ workload nào trong mạng nội bộ cũng có thể yêu cầu tạo key có quyền cao.
Một tổ chức cần chứng minh khóa đã được tạo, phân phối, kích hoạt, xoay vòng và tiêu hủy đúng quy trình nhưng hồ sơ phê duyệt và audit log nằm rời rạc ở nhiều hệ thống.
