Một ứng dụng bán hàng đã vận hành ba năm bắt đầu tính sai phí giao hàng cho đơn đúng ngưỡng 500.000 đồng; đội hỗ trợ nhận nhiều khiếu nại nhưng ticket thiếu phiên bản và dữ liệu đủ để tái hiện lỗi.
Hệ thống ngân hàng xảy ra lỗi chuyển khoản trùng sau một lần timeout; nhóm bảo trì chỉ sửa thông báo trên giao diện trong khi cơ chế gửi lại giao dịch vẫn có nguy cơ ghi nhận hai lần.
Ứng dụng quản lý kho gặp lỗi ở ca hiếm khi hai nhân viên xuất cùng mặt hàng; bản sửa được thử tuần tự trên máy lập trình nhưng chưa có kiểm thử đồng thời trước khi phát hành.
Dịch vụ tính thuế hoạt động đúng trong năm trước nhưng bắt đầu cho kết quả khác ở ngày đầu năm mới; đội vận hành không biết thay đổi do luật nghiệp vụ, dữ liệu hay lỗi lập trình.
Trong hệ thống đặt lịch, người dùng báo không thể đổi giờ hẹn sau khi điện thoại chuyển múi giờ; phiên bản production chưa từng ghi log múi giờ đầu vào nên đội bảo trì khó tái dựng sự cố.
Ứng dụng xuất hóa đơn cần thích ứng với quy định mới về mã định danh thuế; thay đổi tác động cả biểu mẫu, API và dữ liệu lịch sử nhưng yêu cầu được giao như một sửa lỗi đơn lẻ.
Nhà cung cấp thanh toán thông báo ngừng endpoint API cũ trong hai tháng; các phiên bản ứng dụng mobile không thể cập nhật đồng loạt và vẫn gửi request theo hợp đồng cũ.
Một hệ thống Java cũ chạy trên JDK 11, trong khi môi trường triển khai chuyển sang JDK 21; một số thư viện thao tác reflection và driver database không còn hoạt động như trước.
Đội bảo trì ứng dụng desktop phải hỗ trợ hệ điều hành phiên bản mới; chức năng chọn file chạy tốt trên bản cũ nhưng bị từ chối quyền truy cập thư mục theo chính sách mới.
Một đối tác giao vận đổi cấu trúc trạng thái kiện hàng; service hiện đại hóa parser response nhưng các bản tin đã lưu theo schema trước vẫn được phát lại từ hàng đợi.
Người dùng yêu cầu chức năng tìm kiếm phản hồi nhanh hơn khi dữ liệu tăng gấp mười; nhóm dự định tối ưu truy vấn nhưng chưa biết mức độ chậm xuất phát từ database hay tầng ứng dụng.
Trong phần mềm kế toán, màn hình tổng hợp doanh thu mất tám giây vì gọi nhiều query giống nhau; bản tối ưu cache kết quả khiến số liệu hiển thị chậm cập nhật khi có hoàn tiền.
Đội bảo trì cổng học tập muốn cải thiện trải nghiệm đăng nhập bằng một bước thay cho ba bước; các ca kiểm thử bảo mật hiện phụ thuộc chặt vào trình tự màn hình cũ.
Hệ thống lưu trữ tài liệu sử dụng một module xử lý file đã nhiều năm không cập nhật; lỗi mới đòi sửa sâu nhưng chỉ một lập trình viên nghỉ việc gần đây còn biết cấu trúc.
Một thư viện phụ thuộc của ứng dụng nhận cảnh báo lỗ hổng bảo mật nghiêm trọng; bản nâng cấp có thay đổi API và đội bảo trì chưa đánh giá những luồng nghiệp vụ sẽ bị ảnh hưởng.
Đội phát triển vừa vá chức năng đặt đơn nhưng không cập nhật bộ kiểm thử hồi quy; phiên bản kế tiếp đưa lại lỗi cũ khi chỉnh chung hàm tính tổng tiền.
Trong hệ thống tính lương, một lớp Java có hàng trăm nhánh quy tắc theo quốc gia; mọi sửa lỗi ở một nước đều buộc chạy lại kiểm thử thủ công cho tất cả thị trường.
Ứng dụng bảo hiểm có logic đối soát lặp lại ở ba service; sau một thay đổi quy tắc, hai service đã được sửa còn service thứ ba tiếp tục tạo báo cáo sai.
Nhóm muốn refactor các lớp truy cập database để dễ kiểm thử, nhưng các test hiện chỉ so sánh cấu trúc SQL cụ thể; thay đổi cách tổ chức mã làm suite thất bại dù hành vi nghiệp vụ chưa đổi.
Trong hệ thống quản lý đơn, kỹ sư dự định tách một lớp lớn thành nhiều thành phần nhưng không có kiểm thử mô tả hành vi ở các trường hợp hoàn tiền một phần.
Một service tồn tại nhiều cờ cấu hình để giữ tương thích với khách hàng cũ; các cờ đã hết hạn vẫn xuất hiện trong nhiều nhánh khiến mỗi lần sửa lỗi khó xác định tổ hợp nào cần hỗ trợ.
Đội bảo trì xác định lớp tích hợp SMTP là nợ kỹ thuật, nhưng backlog chỉ chứa nhãn 'refactor' mà không ghi nguy cơ gián đoạn gửi thư hay chi phí duy trì nếu không xử lý.
Nhóm dành toàn bộ sprint để giải quyết lỗi khẩn cấp, liên tục dời việc loại bỏ dependency cũ; sau sáu tháng, số lần sự cố tăng nhưng không có dữ liệu cho thấy phần nợ kỹ thuật nào đang gây ảnh hưởng.
Một ứng dụng giao hàng được xây từ một monolith lớn, nhóm muốn tách service định tuyến; cả giao diện và database hiện cùng phụ thuộc vào trạng thái nội bộ của module định tuyến.
Dự án chuyển từ filesystem cục bộ sang object storage; tệp mới đã ghi lên kho mới nhưng luồng tải tệp lịch sử vẫn giả định đường dẫn theo cấu trúc cũ.
Trong kế hoạch hiện đại hóa database, nhóm chạy schema mới song song schema cũ; một thao tác sửa địa chỉ cập nhật một bên thành công nhưng bên còn lại thiếu dữ liệu sau khi mất kết nối.
Ứng dụng đăng ký tài khoản từng cho phép username không phân biệt chữ hoa; migration mới áp unique constraint khác và từ chối một số hồ sơ hợp lệ đã tồn tại.
Đội dự định loại bỏ API v1 nhưng không có thống kê consumer nào vẫn gọi phiên bản đó; xóa endpoint trong release mới khiến nhiều đối tác bất ngờ mất dịch vụ.
Trong giai đoạn nâng cấp framework Java, lớp xác thực mới sử dụng cơ chế filter khác; unit test pass nhưng các request từ ứng dụng cũ nhận HTTP 401 ở production.
Một hệ thống cho phép rollback phiên bản ứng dụng sau deploy; schema dữ liệu mới đã chuyển timestamp sang định dạng khác và bản ứng dụng cũ không còn đọc được dữ liệu vừa ghi.
Đội phát hành hotfix bảo mật gấp vào cuối ngày; quy trình bỏ qua staging và một lỗi cấu hình khiến nhiều khách hàng không thể đăng nhập dù lỗ hổng đã được vá.
Trong dịch vụ thanh toán, thay đổi nhỏ về timeout được đẩy tới toàn bộ khu vực cùng lúc; số request retry tăng đột biến và không có ngưỡng cảnh báo trước khi lỗi lan rộng.
Một tính năng mới được bật bằng cấu hình cho một nhóm khách trước khi phát hành rộng; người vận hành không thể xác định khách nào đang dùng cách tính mới khi nhận ticket khiếu nại.
Ứng dụng quản lý bệnh viện cần cập nhật khi không thể dừng toàn bộ dịch vụ; quy trình migration hiện khóa bảng chính nhiều phút và gây gián đoạn đặt lịch khám.
Đội vận hành triển khai bản vá sửa rò rỉ bộ nhớ, nhưng sau nhiều giờ sử dụng vẫn thấy RAM tăng dần; hệ thống chỉ lưu log khởi động và không có dữ liệu so sánh theo phiên bản.
Một lỗi sản xuất xuất hiện sau khi cập nhật thư viện xử lý ngày; nhóm rollback thư viện nhưng không ghi nguyên nhân gốc, tới đợt cập nhật bảo mật sau sự cố lại lặp lại.
Trong quy trình triage, báo lỗi sai màu giao diện và lỗi mất giao dịch được xếp cùng độ ưu tiên; đội bảo trì xử lý theo thứ tự đến trước khiến lỗi nghiêm trọng kéo dài.
Đội phát hành phiên bản mới đã sửa lỗi và thêm chức năng cùng lúc; một chỉ số kinh doanh suy giảm nhưng không có cách xác định thay đổi nào gây ra tác động.
Ứng dụng báo cáo có hợp đồng hỗ trợ trong năm năm; nhiều phụ thuộc và nhân sự đã thay đổi nhưng tài liệu triển khai, danh sách rủi ro và kế hoạch sao lưu vẫn giữ từ ngày bàn giao.
Nhóm bảo trì tổng kết quý bằng số ticket đóng được mà không theo dõi lỗi tái phát, thời gian khôi phục hay tỉ lệ sự cố sau release; khách hàng vẫn cảm nhận chất lượng hệ thống ngày càng giảm.
