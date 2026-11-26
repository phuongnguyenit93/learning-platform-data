Trong pipeline doanh thu thương mại điện tử, ba nguồn dữ liệu gửi giá tiền theo định dạng 1.250,50, 1,250.50 và 1250.50; bước chuẩn hóa số hiện đọc nhầm một phần giao dịch từ thị trường châu Âu.
Nhóm tích hợp dữ liệu khách hàng từ CRM và ứng dụng di động; tên, số điện thoại và email có khoảng trắng, dấu và cách viết hoa khác nhau, khiến cùng một người xuất hiện thành nhiều bản ghi.
Ứng dụng thống kê đơn hàng lọc trạng thái CANCELLED sau khi đã cộng doanh thu; bảng cuối vẫn bao gồm tiền của đơn bị hủy dù bước lọc sau đó loại đúng số dòng.
Pipeline điểm thưởng dùng các bước lọc, ánh xạ và gom nhóm; nhóm đổi thứ tự hai phép biến đổi để tối ưu tốc độ nhưng chính sách điểm phụ thuộc vào trạng thái được tạo ở bước trước.
Đội nhập dữ liệu sản phẩm có ngày hết hạn để trống; hàm biến đổi mặc định thay bằng ngày hiện tại và dashboard cảnh báo sai hàng nghìn sản phẩm chưa được ghi hạn dùng.
Trong chương trình Java, các đối tượng Transaction được sửa trực tiếp trong một thao tác Stream.map; một collection khác cùng tham chiếu tới các đối tượng này nên số dư báo cáo bị thay đổi ngoài dự kiến.
Nhóm xử lý Stream từ file log một lần để tính tổng sự kiện và sau đó định dùng lại cùng Stream để đếm lỗi; bước thứ hai thất bại vì nguồn stream đã được tiêu thụ.
Một pipeline Java lọc giao dịch hợp lệ rồi dùng Stream.peek để lưu bản ghi kiểm toán; khi thay đổi terminal operation, một số tác dụng phụ không còn xuất hiện như nhóm kỳ vọng.
Báo cáo đơn hàng dùng Collectors.toMap với mã sản phẩm làm khóa; dữ liệu có hai dòng cùng mã do cập nhật giá theo thời điểm, khiến thao tác gom dữ liệu thất bại vì khóa trùng.
Nhóm sử dụng groupingBy để tính số đơn theo khách hàng, nhưng tập dữ liệu có nhiều triệu ID khách hàng hiếm; bản đồ nhóm tăng kích thước vượt giới hạn bộ nhớ của dịch vụ.
Hệ thống đánh giá bán hàng tính trung bình giá của các đơn hàng sau khi lấy trung bình riêng từng cửa hàng; những cửa hàng có một giao dịch lại được gán trọng số bằng cửa hàng có nghìn giao dịch.
Trong pipeline báo cáo doanh thu, phép tính tổng dùng kiểu số nguyên không đủ phạm vi cho các đơn lớn; con số âm xuất hiện sau khi xử lý hàng triệu dòng dù mọi khoản doanh thu đều dương.
Nhóm muốn xếp hạng khách hàng theo tổng mua hàng nhưng thu thập kết quả vào HashMap rồi mặc định thứ tự duyệt trùng với thứ tự đã sắp xếp trong Stream.
Một bộ làm sạch dữ liệu trong Java loại phần tử khỏi ArrayList ngay khi đang duyệt bằng vòng for-each; batch chỉ lỗi khi gặp bản ghi bị loại ở giữa danh sách.
Bộ xử lý song song sử dụng parallelStream để cộng số lượng sản phẩm vào một biến mutable dùng chung; cùng file đầu vào đôi lúc cho ra các tổng khác nhau tùy số luồng.
Nhóm dùng reduce với một accumulator sửa cùng đối tượng danh sách thay vì tạo kết quả phù hợp; phiên bản sequential chạy đúng nhưng kết quả parallel khác biệt và có dữ liệu trùng.
Bộ tổng hợp thời gian thực dùng collector tự viết để giữ top sản phẩm; hàm kết hợp hai kết quả trung gian không bảo toàn thứ tự xếp hạng, khiến báo cáo khác khi chạy song song.
Một chương trình join khách hàng với đơn hàng dựa trên customerId nhưng dữ liệu khách có ID cũ và ID mới sau khi hợp nhất; nhiều đơn không tìm được thông tin khách dù người dùng vẫn tồn tại.
Nhóm nối bảng giao dịch với bảng giá sản phẩm chỉ bằng productId; mỗi sản phẩm có nhiều phiên bản giá nên một giao dịch bị nhân thành nhiều dòng và tổng doanh thu phình ra.
Một báo cáo cần giữ tất cả đơn hàng kể cả khi thiếu địa chỉ giao nhận; đội dữ liệu đổi từ left join sang inner join và số đơn hàng toàn hệ thống giảm mà không có cảnh báo.
Trong hệ thống hoàn tiền, join giữa yêu cầu hoàn và hóa đơn dùng nhiều trường khóa ghép; một trường bị bỏ qua khiến hoàn tiền được ghép nhầm với hóa đơn của tenant khác.
Đội xây lịch sử trạng thái giao dịch và cần lấy giá hiệu lực đúng tại thời điểm thanh toán; phép join hiện tại chọn bản ghi giá mới nhất nên sửa đổi giá về sau làm thay đổi báo cáo quá khứ.
Pipeline batch hằng đêm đọc lại toàn bộ dữ liệu từ đầu sau khi thất bại ở 95 phần trăm tiến độ; chi phí chạy và thời gian hoàn thành tăng vượt cửa sổ xử lý cho phép.
Nhóm chuyển việc xử lý clickstream từ batch cuối ngày sang streaming; dashboard cập nhật nhanh hơn nhưng các giá trị chưa hoàn chỉnh vào giữa ngày bị hiểu như tổng kết chính thức.
Một luồng cảm biến nhận bản tin từ thiết bị theo thứ tự đến mạng, nhưng mỗi thiết bị có độ trễ khác nhau; việc tính thống kê theo processing time làm lệch khoảng đo so với event time.
Dịch vụ đếm lượt xem theo cửa sổ một phút nhận sự kiện tới muộn vài phút do mạng gián đoạn; số liệu ban đầu và số liệu cập nhật sau đó khác nhau khiến nhân viên kinh doanh nghi ngờ.
Đội phân tích truy cập muốn tính phiên người dùng không hoạt động quá 30 phút; cách dùng cửa sổ cố định 30 phút chia một phiên liên tục qua ranh giới thời gian thành hai phiên.
Trong job tổng hợp theo cửa sổ trượt, cùng một sự kiện được tính vào nhiều cửa sổ chồng lấp; dashboard cộng các tổng cửa sổ như thể chúng là những tập sự kiện rời nhau.
Nhóm giữ trạng thái đếm theo từng thiết bị trên luồng sự kiện chạy nhiều tháng; số thiết bị ngừng hoạt động vẫn chiếm chỗ trong state store và dung lượng lưu trữ tăng liên tục.
Một tác vụ streaming dùng checkpoint sau mỗi khoảng thời gian; container chết ngay sau khi ghi kết quả xuống kho dữ liệu nhưng trước checkpoint, khiến cùng sự kiện bị ghi lại khi phục hồi.
Hệ thống tiêu thụ sự kiện từ hàng đợi có khả năng gửi lại khi chưa nhận được xác nhận; tác vụ tính tiền khuyến mãi cộng thêm điểm hai lần cho cùng transactionId sau một đợt restart.
Trong pipeline hợp nhất dữ liệu, một sự kiện lỗi định dạng được thử lại vô hạn ngay trước phần lớn sự kiện hợp lệ, khiến throughput giảm mạnh dù nguồn vẫn gửi thêm dữ liệu.
Nguồn sự kiện gửi nhanh gấp ba khả năng xử lý của dịch vụ; hàng đợi đầu vào phình lên, độ trễ tăng dần và đội vận hành chưa thống nhất chiến lược điều tiết tải hoặc cắt giảm dữ liệu.
Job streaming phụ thuộc API xác thực bên ngoài; khi API chậm vài giây, nhiều worker đồng loạt chờ và áp lực lan sang các bước phía sau trong pipeline.
Nhóm chạy tính tổng theo customerId trên cụm phân tán, nhưng một khách hàng lớn tạo tới 40 phần trăm sự kiện; một partition bị quá tải trong khi các worker còn lại hầu như nhàn rỗi.
Pipeline join hai tập dữ liệu rất lớn bằng cách gửi mọi bản ghi qua mạng đến node tương ứng; thời gian shuffle lớn hơn thời gian xử lý nghiệp vụ và cửa sổ batch bị trễ.
Hệ thống phân tán gộp kết quả từ nhiều worker theo thứ tự không cố định; phép tổng dùng số thực khiến cùng dữ liệu đầu vào trả ra sai lệch nhỏ giữa các lần chạy.
Đội kiểm toán cần chạy lại báo cáo tháng trước nhưng dữ liệu danh mục đã thay đổi, bản ghi trễ mới bổ sung và thuật toán chuẩn hóa đã nâng phiên bản; kết quả chạy lại khác bản đã công bố.
Một batch loại bản ghi lỗi ra file riêng và tiếp tục xử lý thành công; cuối ngày số bản ghi đầu vào không bằng tổng số thành công và thất bại, nhưng dashboard vẫn báo pipeline PASS.
Nhóm nhập dữ liệu khách hàng vào kho phân tích muốn ẩn thông tin cá nhân trước khi chia sẻ; bước loại bỏ email đặt sau thao tác ghi dữ liệu tạm, khiến bản sao trung gian vẫn chứa thông tin nhạy cảm.
