Một tổ chức lưu hồ sơ khách hàng, hợp đồng, giao dịch và log trong cùng kho dữ liệu nhưng chỉ áp dụng một thời hạn retention chung; kiểm toán phát hiện hồ sơ đã hết mục đích vẫn tồn tại nhiều năm, hãy xác định cách phân rã retention schedule theo loại dữ liệu và mục đích.
Một retention policy quy định giữ hồ sơ bảy năm nhưng không nêu thời điểm bắt đầu tính hạn; các hệ thống lần lượt tính từ ngày tạo, ngày đóng tài khoản hoặc ngày kết thúc hợp đồng nên kết quả xóa không nhất quán.
Một hồ sơ có nhiều mục đích xử lý với thời hạn khác nhau, trong đó bản ghi giao dịch cần lưu lâu hơn dữ liệu marketing; hệ thống chỉ hỗ trợ xóa toàn bộ record theo một ngày hết hạn.
Một thay đổi pháp lý làm thời hạn lưu giữ một nhóm hồ sơ thay đổi, nhưng policy engine chỉ áp dụng cho dữ liệu mới và bỏ sót các bản ghi đang tồn tại.
Một công ty hoạt động tại nhiều quốc gia dùng cùng một retention schedule toàn cầu dù nghĩa vụ lưu giữ và quyền yêu cầu xóa khác nhau theo khu vực; hãy xác định cách phân vùng policy và giải quyết xung đột.
Một bộ phận giữ log vô thời hạn với lý do có thể cần điều tra trong tương lai, dù log chứa định danh người dùng và không có mục đích lưu giữ đã phê duyệt; hãy đánh giá cơ chế giới hạn thời hạn và ngoại lệ.
Một hệ thống chỉ xóa bản ghi khi người dùng yêu cầu, không có job xử lý dữ liệu hết hạn theo lịch; lượng dữ liệu cũ tăng dần và chi phí lưu trữ vượt dự toán.
Một job retention tính hạn theo timestamp do client cung cấp, cho phép một số bản ghi bị giữ lâu hơn hoặc bị xóa sớm do đồng hồ và múi giờ không đáng tin cậy.
Một quy trình hợp nhất tài khoản chuyển dữ liệu sang record mới và cập nhật ngày tạo, vô tình khởi động lại retention period dù mục đích và tuổi dữ liệu không đổi.
Một legal hold được gửi qua email và thực hiện thủ công trên một database, trong khi dữ liệu liên quan còn ở object storage, warehouse và bản sao do nhà cung cấp nắm giữ.
Một legal hold chỉ áp dụng cho một tập hồ sơ và khoảng thời gian cụ thể nhưng quản trị viên đóng băng toàn bộ tenant, khiến dữ liệu không liên quan tiếp tục được giữ ngoài thời hạn.
Hai legal hold cùng áp dụng lên một tài liệu nhưng có người yêu cầu, phạm vi và ngày kết thúc khác nhau; hệ thống chỉ lưu một cờ hold nên không thể giải phóng đúng lúc.
Một legal hold được giải phóng nhưng không có sự kiện kích hoạt lại retention job, khiến dữ liệu được bảo toàn tiếp tục nằm ngoài lịch xóa thông thường.
Một người quản trị có thể tự tạo và tự giải phóng legal hold mà không cần phê duyệt hoặc audit độc lập; hãy phân tích rủi ro lạm dụng ngoại lệ lưu giữ.
Một yêu cầu xóa được tiếp nhận qua nhiều kênh với định danh khác nhau, dẫn đến một số hệ thống xử lý còn hệ thống khác không nhận được yêu cầu; hãy xác định cách quản lý trạng thái và correlation xuyên suốt.
Một yêu cầu xóa hợp lệ bị từ chối vì hệ thống không tìm được bản ghi theo email hiện tại, trong khi dữ liệu cũ còn gắn với alias, số điện thoại và mã khách hàng trước đây.
Một người yêu cầu xóa dữ liệu dùng tài khoản dùng chung với thành viên khác; xóa toàn bộ account sẽ ảnh hưởng hồ sơ của nhiều chủ thể, hãy xác định cách phân biệt dữ liệu chung và dữ liệu riêng.
Một phần hồ sơ phải được giữ do nghĩa vụ lưu trữ, nhưng ứng dụng vẫn cho phép dùng phần đó cho marketing và phân tích; hãy đánh giá cách hạn chế mục đích trong thời gian ngoại lệ.
Một quy trình xóa kiểm tra danh tính quá mức và yêu cầu người dùng gửi thêm giấy tờ nhạy cảm không cần thiết; hãy cân bằng xác minh đúng chủ thể với nguyên tắc tối thiểu hóa dữ liệu.
Một yêu cầu xóa được đánh dấu completed ngay khi database chính trả về thành công, dù hệ thống chưa xác nhận cache, replica, search index và bên nhận đã xử lý.
Một backup bất biến vẫn chứa bản ghi đã xóa và sẽ hết hạn sau 90 ngày; khi khôi phục thảm họa, bản ghi quay lại production vì không có danh sách tombstone để áp dụng lại.
Một quy trình restore backup phục hồi database cũ nhưng không replay deletion events phát sinh sau thời điểm backup, khiến dữ liệu đã xóa xuất hiện trở lại và có thể được truy cập.
Một bản backup được nhân bản qua nhiều vùng và tài khoản cloud khác nhau; nhà vận hành không có inventory về các bản sao nên không thể xác định khi nào dữ liệu thực sự hết hạn.
Một nhà cung cấp backup cam kết xóa theo lịch nhưng không cung cấp thông tin về immutable snapshot, bản sao phụ và quy trình xác minh; tổ chức cần xây dựng điều khoản và bằng chứng nào?
Một bảng dữ liệu đã bị xóa khỏi primary nhưng read replica bị lag vài giờ và API đọc từ replica tiếp tục trả về bản ghi; hãy xác định cách xử lý consistency và ngăn phục vụ dữ liệu đã xóa.
Một cache phân tán vẫn giữ profile sau khi database xóa thành công; TTL dài khiến dữ liệu nhạy cảm tiếp tục xuất hiện trong response cho đến khi cache tự hết hạn.
Một deletion event bị consumer xử lý hai lần và lần thứ hai làm lỗi workflow vì bản ghi không còn tồn tại; hãy xác định cách thiết kế consumer idempotent và trạng thái hoàn tất.
Một deletion event bị kẹt trong dead-letter queue do schema thay đổi, trong khi dashboard chỉ theo dõi queue chính; dữ liệu downstream tiếp tục tồn tại mà không có cảnh báo.
Một hệ thống dùng CDC để đồng bộ dữ liệu sang warehouse nhưng pipeline chỉ xử lý insert và update, không truyền delete marker; dữ liệu đã xóa vẫn được dùng trong báo cáo.
Một search index nhận lệnh xóa bất đồng bộ nhưng indexer có thể xử lý update cũ sau delete mới, làm tài liệu xuất hiện trở lại; hãy phân tích versioning và thứ tự sự kiện.
Một data lake lưu nhiều bản sao partitioned theo ngày và tenant; yêu cầu xóa chỉ tìm theo khóa ở bảng chính nên các file parquet dẫn xuất không được phát hiện.
Một message queue giữ payload có thông tin cá nhân trong retention window dài hơn thời hạn dữ liệu nghiệp vụ; hãy xác định cách giảm payload, xóa message hoặc giới hạn quyền truy cập sau khi hết mục đích.
Một event archive được thiết kế immutable để phục vụ replay nhưng payload chứa dữ liệu cá nhân có thể bị yêu cầu xóa; hãy đánh giá lựa chọn token hóa, tách payload và thiết kế event schema.
Một ứng dụng ghi dữ liệu cá nhân vào access log, trace và error report; deletion service chỉ quét database nghiệp vụ nên dữ liệu vẫn tồn tại trong observability platform.
Một export CSV được tải xuống thiết bị của nhân viên và sao chép vào thư mục chia sẻ; tổ chức đã xóa dữ liệu nguồn nhưng không thể thu hồi hoặc xác định các bản export ngoài hệ thống.
Một ứng dụng di động lưu dữ liệu offline nhiều tháng và chỉ đồng bộ khi người dùng mở lại app; yêu cầu xóa từ server không được truyền tới thiết bị đã ngắt kết nối.
Một tenant yêu cầu xóa dữ liệu nhưng một phần thông tin nằm trong bảng dùng chung và được nhiều tenant tham chiếu; thao tác xóa trực tiếp có nguy cơ làm hỏng dữ liệu của tenant khác.
Một quy trình crypto-erasure hủy khóa mã hóa chính nhưng bản sao của data encryption key vẫn còn trong backup KMS và snapshot cấu hình; dữ liệu vẫn có thể được giải mã.
Một hệ thống tái sử dụng cùng data encryption key cho nhiều khách hàng để giảm chi phí, khiến việc hủy khóa của một khách hàng có thể ảnh hưởng dữ liệu của các khách hàng khác.
Một thiết bị lưu trữ được thanh lý sau khi xóa file bằng thao tác thông thường; dữ liệu vẫn có thể khôi phục từ vùng chưa ghi đè hoặc snapshot của nhà cung cấp.
Một tổ chức cần xóa dữ liệu khỏi SSD, snapshot và object versioning nhưng quy trình sanitization chỉ dựa vào lệnh delete thông thường; hãy xác định bằng chứng phù hợp cho từng loại phương tiện.
Một job retention chạy đồng thời trên nhiều worker và hai worker cùng chọn một tập bản ghi hết hạn, gây xử lý lặp và tạo trạng thái audit mâu thuẫn.
Một deletion job bị timeout giữa chừng sau khi xóa một số partition; lần chạy tiếp theo bắt đầu từ đầu nhưng không có checkpoint, dẫn đến tải hệ thống cao và khó xác định phần còn lại.
Một đợt xóa hàng triệu bản ghi làm database lock kéo dài và ảnh hưởng giao dịch đang chạy; hãy đánh giá batching, throttling, partitioning và lịch thực thi.
Một retention rule mới có điều kiện sai khiến dữ liệu còn trong legal hold bị đưa vào danh sách xóa; quy trình hiện không có dry-run hoặc approval gate trước khi chạy.
Một hệ thống đánh dấu deletion request hoàn tất dù một số downstream không phản hồi; tổ chức cần định nghĩa trạng thái pending, partial, failed và completed như thế nào.
Một báo cáo chứng minh xóa chứa nguyên bản ghi và payload trước khi xóa, vô tình tạo thêm một kho lưu trữ dữ liệu nhạy cảm; hãy thiết kế deletion evidence tối thiểu nhưng vẫn kiểm toán được.
Một nhóm vận hành tự xác nhận việc xóa mà không có đối soát độc lập hoặc bằng chứng từ hệ thống đích; hãy xác định cách sampling và attestation để tăng độ tin cậy.
Một thay đổi retention policy được triển khai đồng thời trên nhiều hệ thống mà không có version hoặc effective date, khiến các job cũ và mới áp dụng hai thời hạn khác nhau.
Một yêu cầu xóa đến cùng lúc với giao dịch cập nhật hồ sơ; hệ thống có thể xóa bản ghi rồi nhận bản cập nhật đến muộn và tạo lại dữ liệu, hãy xác định cách giải quyết race condition.
Một import job chạy lại từ file cũ sau khi chủ thể đã được xóa, tạo lại hồ sơ và gửi dữ liệu sang các hệ thống downstream; hãy phân tích tombstone, suppression list và kiểm soát replay.
Một nhà cung cấp subprocessor đã kết thúc hợp đồng nhưng bản sao dữ liệu vẫn nằm trong tài khoản hỗ trợ và hệ thống backup của họ; tổ chức chưa có cơ chế thu hồi, xác nhận và kiểm tra xóa.
Một legal hold hết hiệu lực nhưng bộ phận pháp lý không phát thông báo giải phóng tới hệ thống tự động; dữ liệu tiếp tục được miễn retention job nhiều tháng.
Một dashboard chỉ đếm số deletion request đã đóng mà không đo tuổi backlog, tỷ lệ downstream thành công hoặc số bản ghi quá hạn; nhóm vận hành không phát hiện hệ thống xóa đang suy giảm.
Một cuộc kiểm toán yêu cầu chứng minh toàn bộ bản sao dữ liệu đã bị xóa theo thời hạn, nhưng inventory và data lineage không đầy đủ; hãy xác định cách khoanh vùng và nêu rõ giới hạn bằng chứng.
Một sự cố xóa nhầm hồ sơ đang có nghĩa vụ lưu giữ làm gián đoạn điều tra; hãy lập thứ tự ứng phó để bảo toàn chứng cứ, phục hồi nếu được phép và ngăn tái diễn.
