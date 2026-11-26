Bạn mô tả các trạng thái chính trong vòng đời khóa mật mã từ khởi tạo, kích hoạt, sử dụng, tạm ngưng, thu hồi đến tiêu hủy như thế nào?
Bạn xây dựng kho kiểm kê khóa tập trung để theo dõi chủ sở hữu, mục đích, thuật toán, phiên bản, vị trí lưu trữ và trạng thái của từng khóa như thế nào?
Bạn phân biệt khóa mã hóa dữ liệu, khóa bọc khóa, khóa ký, khóa xác thực thông điệp và khóa dẫn xuất theo mục đích sử dụng như thế nào?
Bạn xác định cryptoperiod phù hợp dựa trên thuật toán, độ dài khóa, khối lượng dữ liệu, tần suất sử dụng và mô hình đe dọa như thế nào?
Bạn phân biệt thời hạn hiệu lực của khóa với giới hạn sử dụng theo số lần mã hóa, số lượng khối hoặc tổng lượng dữ liệu xử lý như thế nào?
Bạn thiết kế quy trình sinh khóa bằng nguồn entropy và bộ sinh số giả ngẫu nhiên mật mã an toàn như thế nào?
Bạn đánh giá chất lượng nguồn entropy và xử lý tình huống thiết bị khởi động khi entropy pool chưa đủ như thế nào?
Bạn xác định khi nào DRBG cần reseed và cách kiểm soát trạng thái generator trong hệ thống phân tán như thế nào?
Bạn lựa chọn thuật toán và độ dài khóa đối xứng theo yêu cầu bảo mật, hiệu năng, khả năng tương thích và thời gian bảo vệ dữ liệu như thế nào?
Bạn đánh giá lựa chọn RSA, elliptic-curve và các thuật toán hậu lượng tử cho mục đích ký hoặc trao đổi khóa như thế nào?
Bạn thiết kế chính sách tách biệt khóa theo môi trường, tenant, loại dữ liệu và mục đích mật mã để hạn chế key reuse như thế nào?
Bạn xác định metadata tối thiểu cần gắn với một khóa để tránh dùng nhầm thuật toán, mục đích, tenant hoặc phiên bản như thế nào?
Bạn tổ chức key ceremony cho việc tạo hoặc kích hoạt khóa gốc có mức độ quan trọng cao như thế nào?
Bạn kiểm soát quá trình sinh khóa bên trong HSM để bảo đảm khóa riêng tư không xuất hiện ở dạng plaintext bên ngoài thiết bị như thế nào?
Bạn đánh giá trade-off giữa sinh khóa trực tiếp trong HSM và import khóa đã sinh từ một nguồn tin cậy như thế nào?
Bạn xác định vai trò key owner, key custodian, administrator và operator để phân tách trách nhiệm trong quản trị khóa như thế nào?
Bạn áp dụng dual control và split knowledge trong các thao tác nhạy cảm như tạo, khôi phục hoặc tiêu hủy khóa như thế nào?
Bạn thiết kế ngưỡng quorum hoặc M-of-N approval cho thao tác khóa quan trọng để vừa bảo đảm kiểm soát vừa duy trì khả năng vận hành như thế nào?
Bạn phân biệt chức năng của KMS với HSM và xác định ranh giới trách nhiệm giữa quản lý chính sách khóa và bảo vệ thao tác mật mã như thế nào?
Bạn đánh giá mô hình shared responsibility khi sử dụng cloud KMS, bao gồm trách nhiệm của nhà cung cấp và khách hàng đối với khóa như thế nào?
Bạn thiết kế phân cấp khóa với root key, key-encryption key và data-encryption key để giảm số khóa phải bảo vệ trực tiếp như thế nào?
Bạn giải thích envelope encryption và cách dùng một KEK để bọc nhiều DEK nhằm mã hóa dữ liệu ở quy mô lớn như thế nào?
Bạn phân biệt key wrapping với mã hóa dữ liệu thông thường và xác định khi nào cần dùng cơ chế wrapping chuyên biệt như thế nào?
Bạn lựa chọn chuẩn key-wrapping và xác minh tính toàn vẹn của wrapped key khi di chuyển khóa giữa các hệ thống như thế nào?
Bạn sử dụng KDF như HKDF để dẫn xuất các khóa con riêng biệt từ một khóa gốc theo context và mục đích như thế nào?
Bạn phân biệt key derivation với key wrapping và giải thích vì sao hai thao tác này giải quyết các bài toán khác nhau như thế nào?
Bạn quản lý cặp khóa bất đối xứng để private key chỉ dùng cho ký hoặc giải mã theo đúng mục đích được phê duyệt như thế nào?
Bạn phân phối public key tới các bên xác minh và bảo đảm tính xác thực của binding giữa khóa công khai với chủ thể như thế nào?
Bạn quản lý khóa dùng trong key agreement và bảo đảm khóa phiên tạm thời được tạo, sử dụng và xóa đúng vòng đời như thế nào?
Bạn thiết kế kênh phân phối khóa đối xứng giữa các hệ thống để chống nghe lén, sửa đổi và thay thế khóa như thế nào?
Bạn xác thực nguồn gốc và tính toàn vẹn của khóa khi import từ hệ thống hoặc nhà cung cấp khác như thế nào?
Bạn xây dựng chính sách truy cập KMS theo nguyên tắc ít quyền nhất cho người dùng, workload và dịch vụ tự động như thế nào?
Bạn ràng buộc quyền sử dụng khóa với operation cụ thể như encrypt, decrypt, sign, verify hoặc unwrap thay vì cấp quyền quản trị khóa chung như thế nào?
Bạn xác thực workload trước khi cho phép gọi KMS và tránh phụ thuộc vào API key tĩnh có vòng đời dài như thế nào?
Bạn phân tách quyền quản trị policy khỏi quyền sử dụng khóa để một operator không thể tự cấp quyền truy cập dữ liệu cho chính mình như thế nào?
Bạn bảo vệ private key không thể export trong HSM hoặc secure enclave và xác minh rằng policy không vô tình cho phép trích xuất khóa như thế nào?
Bạn giảm nguy cơ khóa xuất hiện trong bộ nhớ tiến trình, crash dump, swap hoặc core dump khi ứng dụng thực hiện thao tác mật mã như thế nào?
Bạn ngăn secret hoặc key material bị ghi vào application log, tracing, telemetry và hệ thống hỗ trợ khi xảy ra lỗi như thế nào?
Bạn đánh giá rủi ro side-channel như timing, cache hoặc power analysis đối với thao tác sử dụng khóa và lựa chọn biện pháp giảm thiểu như thế nào?
Bạn thiết kế backup cho khóa và metadata liên quan sao cho bản sao được bảo vệ bằng cơ chế mật mã và quyền truy cập độc lập như thế nào?
Bạn phân biệt backup, escrow và archival key storage theo mục đích khôi phục, lưu giữ dài hạn và yêu cầu kiểm soát như thế nào?
Bạn thiết kế quy trình escrow cho khóa cần phục hồi dữ liệu nhưng tránh tạo thêm một bản sao có quyền truy cập quá rộng như thế nào?
Bạn kiểm tra tính toàn vẹn và khả năng sử dụng của backup khóa mà không làm lộ key material trong quá trình kiểm tra như thế nào?
Bạn xây dựng bài diễn tập khôi phục khóa từ backup để xác minh thời gian phục hồi, tính đầy đủ và khả năng giải mã dữ liệu thực tế như thế nào?
Bạn lập kế hoạch disaster recovery cho KMS hoặc HSM khi mất thiết bị, mất vùng triển khai hoặc mất toàn bộ thông tin quản trị như thế nào?
Bạn thiết kế tính sẵn sàng cao cho HSM cluster mà vẫn giữ được kiểm soát truy cập, đồng bộ trạng thái và tính nhất quán của khóa như thế nào?
Bạn đánh giá rủi ro khi sao chép hoặc nhân bản khóa giữa nhiều vùng địa lý và cách giới hạn phạm vi ảnh hưởng khi một vùng bị xâm nhập như thế nào?
Bạn xử lý tình huống một vùng KMS chưa nhận phiên bản khóa mới nhưng workload đã bắt đầu ghi dữ liệu bằng phiên bản đó như thế nào?
Bạn quản lý cache của plaintext DEK trong ứng dụng để giảm độ trễ mà vẫn giới hạn thời gian tồn tại và khả năng truy cập trái phép như thế nào?
Bạn xác định hành vi fail-open hoặc fail-closed khi KMS tạm thời không khả dụng và cách lựa chọn theo độ nhạy của thao tác như thế nào?
Bạn theo dõi latency, quota, throttling và lỗi KMS để phát hiện sớm nguy cơ ảnh hưởng đến dịch vụ sử dụng khóa như thế nào?
Bạn định nghĩa trạng thái pending, active, disabled, compromised, revoked và destroyed để các hệ thống tiêu thụ khóa xử lý nhất quán như thế nào?
Bạn thiết kế quy trình phê duyệt và kích hoạt khóa mới để bảo đảm khóa chỉ được dùng sau khi metadata, policy và kiểm tra an toàn hoàn tất như thế nào?
Bạn tạm ngưng một khóa khi nghi ngờ bị lộ nhưng chưa đủ bằng chứng compromise và đánh giá tác động tới dữ liệu cùng dịch vụ phụ thuộc như thế nào?
Bạn lập lịch xoay vòng khóa theo cryptoperiod và mức độ sử dụng để không làm gián đoạn các workload đang chạy như thế nào?
Bạn xác định các sự kiện ngoài lịch như nhân sự thay đổi, thuật toán suy yếu hoặc dấu hiệu lộ khóa cần kích hoạt rotation khẩn cấp như thế nào?
Bạn phân biệt rotation của KEK với rotation của DEK và đánh giá trường hợp nào chỉ cần rewrap còn trường hợp nào phải mã hóa lại dữ liệu như thế nào?
Bạn triển khai rewrapping hàng triệu DEK bằng KEK mới mà không phải đọc và mã hóa lại toàn bộ payload dữ liệu như thế nào?
Bạn lập kế hoạch re-encryption dữ liệu khi DEK bị compromise và cân bằng giữa tính toàn vẹn, chi phí I/O và thời gian hoàn thành như thế nào?
Bạn thiết kế giai đoạn dual-read hoặc dual-write trong quá trình chuyển phiên bản khóa để các ứng dụng cũ và mới cùng hoạt động an toàn như thế nào?
Bạn quản lý dữ liệu lịch sử vẫn được mã hóa bằng khóa cũ sau rotation để giải mã có kiểm soát mà không tiếp tục dùng khóa cũ cho dữ liệu mới như thế nào?
Bạn xử lý migration bị gián đoạn giữa chừng khi một phần dữ liệu đã dùng khóa mới còn phần khác vẫn dùng khóa cũ như thế nào?
Bạn thiết kế rollback cho một đợt rotation thất bại mà không kích hoạt lại khóa đã bị thu hồi hoặc làm mất khả năng giải mã dữ liệu như thế nào?
Bạn xây dựng cryptographic agility để thay thuật toán, độ dài khóa hoặc nhà cung cấp KMS khi tiêu chuẩn an toàn thay đổi như thế nào?
Bạn lập kế hoạch loại bỏ thuật toán yếu đang được dùng trên nhiều hệ thống mà vẫn duy trì khả năng đọc dữ liệu lịch sử như thế nào?
Bạn phản ứng khi phát hiện private key ký hoặc KEK có dấu hiệu bị sao chép ra ngoài vùng bảo vệ như thế nào?
Bạn phân biệt sự cố lộ key material với việc lộ quyền gọi KMS nhưng không thể export khóa và đánh giá mức độ ảnh hưởng của từng trường hợp như thế nào?
Bạn cô lập và thu hồi khóa bị compromise đồng thời xác định những dữ liệu, token, chữ ký hoặc dịch vụ đã phụ thuộc vào khóa đó như thế nào?
Bạn xác định có cần tái mã hóa dữ liệu, tái ký artifact hoặc cấp lại credential sau sự cố lộ khóa dựa trên loại khóa và phạm vi sử dụng như thế nào?
Bạn phối hợp thông báo cho các hệ thống downstream về key revocation để chúng ngừng chấp nhận khóa cũ trong thời gian phù hợp như thế nào?
Bạn phát hiện hành vi sử dụng khóa bất thường qua audit log như decrypt hàng loạt, sign ngoài giờ hoặc truy cập từ workload lạ như thế nào?
Bạn thiết kế audit trail bất biến cho các thao tác tạo, import, activate, use, rotate, disable và destroy khóa như thế nào?
Bạn xây dựng cảnh báo khi quyền truy cập KMS thay đổi, policy bị nới lỏng hoặc một khóa nhạy cảm được sử dụng ngoài baseline như thế nào?
Bạn quản lý khóa riêng cho từng tenant để một tenant không thể yêu cầu KMS giải mã dữ liệu của tenant khác như thế nào?
Bạn lựa chọn giữa khóa dùng chung theo dịch vụ và khóa riêng theo khách hàng dựa trên yêu cầu cách ly, chi phí và khả năng vận hành như thế nào?
Bạn kiểm soát việc chuyển dữ liệu và khóa giữa nhiều cloud provider để tránh phụ thuộc độc quyền và giữ được khả năng khôi phục như thế nào?
Bạn xác minh rằng xóa một khóa khỏi KMS thực sự làm mất khả năng giải mã các bản sao dữ liệu, backup và replica liên quan như thế nào?
Bạn phân biệt key revocation, key disable và key destruction về khả năng đảo ngược và tác động tới dữ liệu đã được bảo vệ như thế nào?
Bạn thiết kế quy trình tiêu hủy khóa có dual approval, xác nhận phạm vi và bằng chứng hoàn tất có thể kiểm toán như thế nào?
Bạn xử lý khóa nằm trong backup bất biến hoặc bản lưu trữ dài hạn khi chính sách yêu cầu tiêu hủy nhưng vẫn có nghĩa vụ lưu giữ dữ liệu như thế nào?
Bạn đánh giá khả năng dùng cryptographic erasure để xóa dữ liệu bằng cách tiêu hủy khóa và những điều kiện cần có để phương pháp này đáng tin cậy như thế nào?
Bạn bảo đảm khóa hết vòng đời được xóa khỏi HSM, cache, bản sao, thiết bị dự phòng và hệ thống quản lý metadata như thế nào?
Bạn lưu giữ khóa xác minh chữ ký đã hết thời hạn ký để kiểm chứng tài liệu hoặc artifact lịch sử trong thời gian dài như thế nào?
Bạn phân biệt thời điểm ngừng ký bằng khóa cũ với thời điểm ngừng xác minh chữ ký lịch sử bằng khóa đó như thế nào?
Bạn quản lý khóa gốc và thông tin phục hồi khi nhân sự giữ vai trò custodian rời tổ chức hoặc mất khả năng thực hiện nhiệm vụ như thế nào?
Bạn thiết kế access review định kỳ cho quyền sử dụng và quản trị khóa để loại bỏ principal không còn nhu cầu như thế nào?
Bạn đo lường hiệu quả chương trình key management bằng các chỉ số về inventory coverage, rotation compliance, orphaned keys, recovery test và thời gian thu hồi như thế nào?
Bạn xây dựng quy trình đánh giá nhà cung cấp KMS/HSM về chứng nhận, mô hình quản trị, khả năng xuất/nhập khóa, audit và kế hoạch thoát nhà cung cấp như thế nào?
Bạn kiểm thử toàn bộ vòng đời khóa bằng các tình huống mất khóa, lộ khóa, hết cryptoperiod, KMS outage, rotation lỗi và destruction như thế nào?
