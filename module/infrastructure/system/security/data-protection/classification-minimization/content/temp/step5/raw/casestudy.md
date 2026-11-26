Một doanh nghiệp triển khai nhiều nền tảng SaaS và kho object theo từng phòng ban, nhưng không có danh mục tập trung; một cuộc điều tra phát hiện bảng tính chứa thông tin khách hàng nằm trong thư mục chia sẻ cá nhân mà bộ phận an ninh chưa từng kiểm kê.
Một data lake tiếp nhận dữ liệu từ ứng dụng, đối tác và thiết bị IoT; metadata nguồn cùng owner bị mất trong pipeline ingest nên nhóm phân tích không biết tập dữ liệu nào chứa thông tin cá nhân hoặc bí mật kinh doanh.
Công cụ tự động gắn nhãn dữ liệu đánh dấu một số trường định danh là Public do confidence thấp, trong khi chủ sở hữu dữ liệu phân loại chúng là Confidential; các hệ thống downstream đã áp dụng nhãn sai.
Một file CSV được xuất từ hệ thống có nhãn Restricted nhưng khi tải lên kho cộng tác nhãn bị mất, khiến người dùng ngoài nhóm được phép có thể xem và chia sẻ file.
Một bảng chứa mã bưu chính và ngày sinh không được xem là nhạy cảm riêng lẻ, nhưng khi kết hợp với dữ liệu công khai có thể nhận diện một cá nhân cụ thể; chính sách phân loại hiện chỉ đánh giá từng cột riêng.
Một pipeline làm giàu hồ sơ khách hàng bằng dữ liệu vị trí và lịch sử giao dịch nhưng không kích hoạt đánh giá lại classification label, khiến tập dữ liệu kết hợp vẫn mang nhãn thấp của nguồn ban đầu.
Một hệ thống cũ lưu dữ liệu nhạy cảm nhưng không còn data owner sau khi tái cơ cấu tổ chức; các nhóm vận hành tiếp tục cấp quyền truy cập dựa trên giả định từ nhiều năm trước.
Hai nguồn dữ liệu cùng được hợp nhất nhưng một nguồn gắn nhãn Internal và nguồn kia gắn nhãn Restricted; quy tắc ưu tiên nhãn không được định nghĩa nên kết quả phân loại thay đổi theo thứ tự ingest.
Một form đăng ký yêu cầu ngày sinh đầy đủ, địa chỉ nhà và số điện thoại phụ dù dịch vụ chỉ cần xác minh người dùng đủ tuổi; nhóm sản phẩm chưa có bằng chứng cho nhu cầu của từng trường.
Một ứng dụng theo dõi hành vi thu thập vị trí chính xác liên tục dù tính năng chỉ cần biết người dùng có ở trong một khu vực rộng hay không; dữ liệu được giữ vô thời hạn cho mục đích có thể hữu ích sau này.
Một SDK analytics mặc định ghi email, device identifier và nội dung màn hình vào telemetry; đội sản phẩm không nhận ra dữ liệu cá nhân được gửi tới nhà cung cấp phân tích bên ngoài.
Một thay đổi schema bổ sung nhiều thuộc tính hồ sơ để phục vụ chiến dịch marketing nhưng không có bước review mục đích, tính cần thiết hoặc tác động tới phân loại dữ liệu trước khi phát hành.
Một API trả toàn bộ entity khách hàng gồm số định danh, địa chỉ và ghi chú nội bộ trong khi client chỉ cần tên hiển thị và trạng thái tài khoản; các ứng dụng tiêu thụ tự chọn bỏ qua field nhạy cảm.
Một dashboard vận hành hiển thị dữ liệu chi tiết theo từng khách hàng cho mọi nhân viên hỗ trợ dù phần lớn tác vụ chỉ cần số liệu tổng hợp theo ngày và khu vực.
Một nhóm phân tích muốn tái sử dụng dữ liệu thu thập cho chăm sóc khách hàng để huấn luyện mô hình dự đoán hành vi, nhưng mục đích mới chưa được đánh giá về tính tương thích và giới hạn sử dụng.
Người dùng rút lại sự đồng ý cho một mục đích marketing nhưng dữ liệu của họ vẫn còn trong hệ thống chiến dịch, bản sao CRM và danh sách xuất định kỳ do quy trình đồng bộ không truyền trạng thái thay đổi.
Một nhà cung cấp nhận dữ liệu khách hàng để gửi thông báo rồi chuyển tiếp một phần cho subprocessor khác mà tổ chức không có danh sách bên nhận hoặc điều kiện xóa tương ứng.
Một tập dữ liệu được chuyển sang khu vực địa lý khác để giảm chi phí lưu trữ nhưng metadata về nơi xử lý và các hạn chế chia sẻ theo hợp đồng không đi theo dữ liệu.
Một đối tác yêu cầu bản dump toàn bộ bảng khách hàng để đối soát trong khi chỉ cần mã giao dịch và trạng thái; hợp đồng chia sẻ không giới hạn trường dữ liệu hoặc thời hạn lưu bản sao.
Một tổ chức chưa xác định retention period cho từng loại dữ liệu nên bản ghi khách hàng, log, export và cache đều tồn tại nhiều năm sau khi mục đích nghiệp vụ kết thúc.
Một yêu cầu xóa dữ liệu cá nhân đã hoàn tất ở database chính nhưng dữ liệu vẫn còn trong replica, search index, cache và kho báo cáo; hệ thống chỉ ghi nhận thành công từ một dịch vụ.
Một backup bất biến không thể chỉnh sửa trước thời hạn lưu giữ, và khi được restore để khôi phục thảm họa, các bản ghi đã có yêu cầu xóa trước đó xuất hiện trở lại trong môi trường hoạt động.
Một legal hold được áp dụng cho toàn bộ tài khoản lưu trữ thay vì tập hồ sơ liên quan, khiến dữ liệu của nhiều cá nhân tiếp tục được giữ dù không thuộc phạm vi điều tra.
Một job xóa dữ liệu báo trạng thái completed dù một số partition và object storage bucket bị timeout; không có đối soát độc lập để phát hiện các bản sao còn sót.
Một yêu cầu truy cập và xóa dữ liệu chỉ cung cấp email hiện tại, trong khi hồ sơ cũ được lưu dưới alias, số điện thoại và mã khách hàng khác nhau ở các hệ thống; quy trình tìm kiếm bỏ sót một phần dữ liệu.
Một nhóm QA sao chép production database sang môi trường kiểm thử để tái hiện lỗi hiếm, nhưng bản dump chứa dữ liệu liên hệ thật và được nhiều nhà thầu truy cập.
Dữ liệu kiểm thử được masking bằng cách thay từng giá trị độc lập, làm hỏng quan hệ khóa ngoại và phân bố dữ liệu; nhóm phát triển sau đó xin dùng lại bản production để kiểm thử tích hợp.
Một bộ dữ liệu đã masking vẫn giữ nguyên ngày sinh, mã vùng và thời điểm giao dịch hiếm, khiến một người có thể được nhận diện khi kết hợp với nguồn dữ liệu công khai.
Nhóm hỗ trợ cần xem một phần số tài khoản để đối chiếu nhưng giao diện chỉ có chế độ hiển thị toàn bộ hoặc che toàn bộ; nhân viên thường tải file đầy đủ về máy để xử lý.
Một tokenization service tạo token ổn định cho cùng số định danh nhưng bảng ánh xạ token được cấp quyền đọc rộng, khiến nhiều nhóm có thể khôi phục dữ liệu gốc ngoài mục đích.
Khóa dùng để tái liên kết dữ liệu pseudonymized bị lưu chung với tập dữ liệu đã thay thế định danh; một sự cố quyền truy cập làm cả dữ liệu và khóa ánh xạ cùng bị lộ.
Một tập dữ liệu được gọi là anonymized sau khi xóa tên và email, nhưng vẫn giữ nghề nghiệp hiếm, khu vực nhỏ và ngày tham gia chính xác; một bên nhận đã liên kết được nhiều bản ghi với cá nhân.
Một báo cáo tổng hợp hiển thị kết quả cho nhóm chỉ có hai người, khiến người xem suy ra thuộc tính của một cá nhân dù dữ liệu đã bỏ định danh trực tiếp.
Một dashboard cho phép chạy nhiều truy vấn tổng hợp với bộ lọc gần giống nhau; người dùng so sánh chênh lệch kết quả để suy ra giá trị của một cá nhân trong nhóm nhỏ.
Log ứng dụng ghi nguyên query string chứa email và số hồ sơ, sau đó được sao chép sang hệ thống log tập trung có nhiều nhóm vận hành được cấp quyền đọc.
Distributed trace tự động thu thập toàn bộ request header và body attribute, khiến access token, email và dữ liệu biểu mẫu xuất hiện trong trace backend.
Một exception message chứa số định danh và nội dung request được gửi tới dịch vụ theo dõi lỗi bên ngoài; nhóm phát triển không có quy tắc redaction trước khi export.
Crash dump và heap dump được tạo khi xử lý sự cố có thể chứa token, thông tin cá nhân và nội dung giao dịch, nhưng file được lưu trong thư mục chia sẻ mà không có retention hoặc access review.
Nhân viên xuất CSV chứa hồ sơ khách hàng để gửi qua email cho đối tác, trong khi kênh chia sẻ được phê duyệt chỉ hỗ trợ tập con đã masking và có thời hạn.
Một bản sao dữ liệu production được đồng bộ tự động vào laptop của nhà phân tích qua thư mục cloud cá nhân; chính sách endpoint không phát hiện dữ liệu nhạy cảm rời khỏi vùng kiểm soát.
Môi trường staging có cùng quyền truy cập với production và chứa dữ liệu thật đã masking một phần; tài khoản của nhà cung cấp vẫn hoạt động sau khi hợp đồng hỗ trợ kết thúc.
Một nhà cung cấp SaaS xác nhận đã xóa dữ liệu khỏi tenant chính nhưng không cung cấp bằng chứng về backup, log, subprocessor và các bản export mà họ đã tạo.
Data lineage chỉ ghi nhận bảng nguồn và bảng đích, không lưu transformation hoặc danh sách người nhận; khi phát hiện rò rỉ, tổ chức không thể xác định các báo cáo chứa trường nhạy cảm.
Một dự án migration chuyển dữ liệu sang kho mới nhưng không chuyển classification label, purpose tag và retention metadata; dữ liệu Restricted được nhập vào vùng mặc định Internal.
Một nhóm muốn đưa lịch sử hỗ trợ khách hàng vào tập dữ liệu huấn luyện AI; bản ghi chứa thông tin sức khỏe, tài chính và nội dung riêng tư không được phân loại hoặc loại bỏ trước ingest.
Một retention policy được cấu hình theo ngày tạo bản ghi nhưng dữ liệu được sao chép sang kho khác với timestamp mới, khiến thời hạn lưu giữ bị kéo dài sau mỗi lần migration.
Job retention chạy thành công theo lịch nhưng không có metric về số bản ghi đã xóa, số lỗi theo partition hoặc tuổi dữ liệu còn tồn tại; các lỗi âm thầm kéo dài nhiều tháng.
Một hệ thống cho phép người dùng tải dữ liệu đã hết hạn từ kho archive vì quyền truy cập không kiểm tra retention state, dù giao diện chính đã ẩn bản ghi.
Một quy trình xóa dùng cryptographic erasure nhưng data encryption key được backup và tái sử dụng cho nhiều tập dữ liệu; việc hủy một khóa có thể ảnh hưởng ngoài phạm vi dự kiến.
Một tổ chức ghi audit log chi tiết mọi lần đọc dữ liệu để đáp ứng điều tra, nhưng log audit lại chứa nguyên giá trị nhạy cảm và được lưu lâu hơn dữ liệu nghiệp vụ.
Một tính năng phát hiện gian lận cần dữ liệu chi tiết trong thời gian ngắn, nhưng nhóm vận hành muốn giữ toàn bộ bản ghi vô thời hạn để phục vụ phân tích tương lai; chưa có cơ chế tách mục đích và thời hạn.
Một DPIA được thực hiện trước khi ra mắt tính năng nhưng thiết kế sau đó bổ sung nguồn dữ liệu, bên nhận và mục đích mới mà không kích hoạt đánh giá lại.
Một chính sách classification và minimization được mô tả trong tài liệu nhưng không có kiểm tra trong schema review hoặc pipeline, nên các trường nhạy cảm mới liên tục được thêm mà không có owner hay purpose tag.
Một sự cố rò rỉ xuất phát từ bản export cũ trong thư mục cộng tác; tổ chức không biết ai đã tải file, bản sao nào còn tồn tại và bên nhận nào cần được thông báo hoặc yêu cầu xóa.
