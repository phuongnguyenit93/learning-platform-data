Một nhóm phát triển thêm cột trực tiếp bằng công cụ quản trị trên production, nhưng không ghi migration; khi dựng lại staging từ mã nguồn, ứng dụng lỗi vì cấu trúc bảng khác production.
Hệ thống có các môi trường dev, staging và production được chỉnh sửa thủ công theo thời điểm khác nhau; một bản phát hành mới chạy được ở dev nhưng gặp lỗi thiếu cột trên staging.
Đội phát triển đưa Flyway vào một cơ sở dữ liệu đã tồn tại nhiều năm với hàng trăm bảng; lịch sử migration mới bắt đầu từ bản đầu tiên khiến quá trình khởi tạo trên production không thể tiếp tục theo cách giống cơ sở dữ liệu trống.
Hai nhánh tính năng cùng tạo migration Flyway mang cùng số phiên bản; sau khi merge vào nhánh phát hành, pipeline không thể xác định chuỗi phiên bản hợp lệ.
Một migration đã chạy thành công ở staging được sửa nội dung SQL để bổ sung cột mới; khi triển khai lại, Flyway báo checksum của phiên bản đã áp dụng không khớp.
Đội phát triển đổi tên và di chuyển các file versioned migration trong repository; môi trường được dựng mới hoạt động nhưng một số môi trường cũ báo lịch sử migration không nhất quán.
Một changeset Liquibase đã được áp dụng ở production bị sửa điều kiện lọc dữ liệu; lần triển khai tiếp theo xuất hiện lỗi kiểm tra checksum dù người viết nghĩ đây chỉ là chỉnh sửa nhỏ.
Trong quá trình triển khai rolling deployment, phiên bản ứng dụng mới bắt đầu đọc cột địa chỉ mới nhưng vẫn còn nhiều pod phiên bản cũ chỉ ghi vào cột địa chỉ trước đây.
Nhóm đổi tên cột customer_name trong một migration rồi phát hành ứng dụng mới; các instance phiên bản cũ vẫn đang nhận request và bắt đầu lỗi SQL trong giai đoạn triển khai song song.
Sau khi giao diện chuyển sang đọc bảng đơn hàng mới, một job chạy nền thuộc phiên bản cũ tiếp tục ghi vào bảng cũ; dữ liệu hai bảng lệch nhau qua nhiều giờ.
Đội phát triển muốn bỏ một cột cũ ngay trong lần phát hành có mã nguồn ngừng sử dụng cột đó; một dịch vụ báo cáo độc lập chưa được nâng cấp vẫn truy vấn cột này mỗi đêm.
Một bảng giao dịch có hàng trăm triệu dòng được bổ sung cột bắt buộc, nhưng phần lớn bản ghi lịch sử chưa có giá trị tương ứng; thao tác áp dụng ràng buộc mới không hoàn tất như dự kiến.
Nền tảng quản lý tài khoản muốn áp dụng ràng buộc duy nhất cho email sau khi chuẩn hóa chữ hoa và khoảng trắng; dữ liệu cũ có nhiều tài khoản cùng email chuẩn hóa nên migration thất bại khi tạo ràng buộc.
Ứng dụng bổ sung khóa ngoại từ hóa đơn sang khách hàng; dữ liệu lịch sử có hóa đơn tham chiếu mã khách đã bị xóa, khiến bước kiểm tra toàn vẹn không vượt qua.
Nhóm triển khai thêm ràng buộc kiểm tra số dư không âm cho bảng ví điện tử; một số bản ghi cũ có giá trị âm vì lỗi nhập liệu trước đây, nên việc thay đổi schema bị chặn.
Đội phát triển thêm index cho bảng đơn hàng cực lớn ngay giữa giờ cao điểm; giao dịch ghi xếp hàng chờ khóa và thời gian phản hồi ứng dụng tăng mạnh cho đến khi thao tác kết thúc.
Trong môi trường dùng PostgreSQL, nhóm đóng gói thao tác tạo chỉ mục theo chế độ đồng thời vào một migration chạy bên trong transaction mặc định; lệnh DDL bị từ chối ở bước triển khai.
Một migration thay kiểu dữ liệu của cột mã khách trên bảng lớn; quá trình chuyển đổi kéo dài, sử dụng nhiều I/O và khiến các truy vấn nghiệp vụ chậm bất thường.
Đội phát triển đổi mã định danh từ chuỗi số sang UUID, nhưng dữ liệu cũ chứa các giá trị không thể chuyển đổi; migration dừng giữa quy trình phát hành.
Hệ thống chuyển cột số tiền từ kiểu số thực sang kiểu thập phân cố định; sau khi backfill, một số báo cáo đối soát phát hiện giá trị bị làm tròn khác với dữ liệu nguồn.
Ứng dụng đặt lịch chuyển timestamp không có múi giờ sang kiểu dữ liệu có múi giờ; dữ liệu lịch sử được ghi bởi nhiều chi nhánh ở các múi giờ khác nhau nên kết quả hiển thị lệch sau triển khai.
Nhóm tách trường họ tên thành hai cột riêng; dữ liệu cũ chứa họ tên nhiều thành phần và cả tài khoản chỉ có một từ, khiến kết quả chuyển đổi không thống nhất.
Đội sản phẩm tách địa chỉ giao hàng từ một cột văn bản thành nhiều cột tỉnh, quận và mã bưu điện; hàng triệu bản ghi thiếu định dạng chuẩn làm tiến trình backfill có tỷ lệ lỗi cao.
Một ứng dụng thay cột danh sách sản phẩm bằng bảng liên kết đơn hàng và sản phẩm; trong thời gian chuyển đổi, một số đơn mới chỉ có dữ liệu ở cấu trúc cũ nên báo cáo theo bảng mới thiếu đơn.
Nhóm tách một bảng người dùng lớn thành bảng hồ sơ và bảng thông tin xác thực; trong giai đoạn dữ liệu chưa được chuyển hết, một số phiên đăng nhập không tìm thấy bản ghi xác thực tương ứng.
Hệ thống bắt đầu lưu lịch sử trạng thái đơn hàng trong bảng riêng thay vì một cột hiện tại; API và worker cũ cập nhật trạng thái theo hai cách khác nhau khiến trình tự lịch sử không đầy đủ.
Một migration backfill ngày tạo đơn từ dữ liệu lịch sử; quá trình lấy thời gian hiện tại để điền các bản ghi thiếu làm báo cáo theo ngày không còn khớp với hồ sơ ban đầu.
Đội kỹ thuật chạy chuyển đổi dữ liệu theo lô 100 nghìn dòng mỗi transaction; trong lúc batch chạy, số lượng bản ghi bị khóa và dung lượng log giao dịch tăng mạnh.
Một job backfill dữ liệu mất nhiều giờ và bị ngắt khi đã xử lý khoảng một nửa bảng; lần chạy tiếp theo không phân biệt bản ghi đã chuyển đổi với bản ghi chưa chuyển đổi.
Nhóm viết migration cập nhật giá trị dựa trên các bảng liên quan; một số khách hàng có nhiều quan hệ phù hợp, khiến cùng bản ghi bị cập nhật theo kết quả ghép dữ liệu không xác định.
Trong thời gian backfill, ứng dụng vẫn nhận yêu cầu thay đổi địa chỉ; job chuyển dữ liệu đọc trạng thái cũ rồi ghi đè giá trị mới của người dùng ở cột đích.
Đội phát triển triển khai cơ chế ghi đồng thời vào cột cũ và cột mới; một nhánh xử lý lỗi chỉ cập nhật một cột nên hai giá trị bắt đầu lệch sau vài ngày.
Nhóm bật tính năng mới cho 10% người dùng để đọc cấu trúc bảng mới, nhưng migration chuyển dữ liệu chỉ chạy xong 70% bản ghi; nhóm người dùng được bật tính năng thấy nhiều giá trị trống.
Một migration dữ liệu chạy thành công trên bản sao nhỏ nhưng vượt thời gian triển khai trong production có vài trăm triệu bản ghi; pipeline bị timeout trong lúc cơ sở dữ liệu vẫn đang thực hiện thao tác.
Một giao dịch báo cáo kéo dài giữ khóa hoặc snapshot khi migration cố thay đổi cấu trúc bảng; tiến trình triển khai đứng chờ trong khi các request mới tiếp tục tích lũy.
Đội vận hành đặt giới hạn thời gian chờ khóa cho migration, nhưng lúc phát hành một giao dịch nền giữ khóa lâu hơn dự kiến; migration bị hủy và ứng dụng mới chuẩn bị khởi động.
Ba replica ứng dụng Spring Boot cùng khởi động và tự chạy migration Flyway; các instance cạnh tranh quyền thực thi schema change trong lúc hệ thống đang autoscale.
Nhóm tách migration thành một Kubernetes Job trước bước khởi động ứng dụng; job báo lỗi nhưng bước triển khai pod mới vẫn tiếp tục, khiến mã nguồn mới truy vấn bảng chưa được tạo.
Ứng dụng mới phụ thuộc vào một index và cột mới; pipeline CI/CD triển khai ứng dụng trước khi quá trình cập nhật schema hoàn tất trên cơ sở dữ liệu chung.
Một thay đổi schema được áp dụng đúng lên primary nhưng các bản sao đọc vẫn đang trễ; request từ ứng dụng mới đọc qua replica và gặp trạng thái dữ liệu chưa theo kịp.
Một khách hàng doanh nghiệp dùng database riêng với chuỗi migration bị chậm hơn các khách hàng khác; khi triển khai bản ứng dụng mới đồng loạt, chỉ nhóm khách hàng đó gặp lỗi thiếu bảng.
Hệ thống nhiều tenant dùng chung cơ sở dữ liệu nhưng tách schema theo tenant; migration chạy thành công cho schema mặc định nhưng bỏ sót nhiều schema không nằm trong cấu hình tìm kiếm.
Pipeline của nhóm sử dụng Flyway với đường dẫn thư mục migration khác nhau giữa dev và production; một số migration có trong repository nhưng không được phát hiện khi phát hành.
Đội phát triển dùng Liquibase contexts để phân biệt dữ liệu thử nghiệm và cấu trúc chung; một changeset chỉ dành cho staging lại được chọn khi chạy trên production.
Một changeset Liquibase được đánh dấu bằng label cho module báo cáo; pipeline production không truyền bộ lọc label như dự kiến nên schema báo cáo bị thiếu đối tượng phụ thuộc.
Nhóm sử dụng repeatable migration Flyway để định nghĩa lại một database view; sau thay đổi logic, một dịch vụ đang sử dụng tên cột cũ của view gặp lỗi lúc truy vấn.
Một đợt cập nhật stored procedure có nhiều phụ thuộc vào bảng mới; thứ tự changeset trong changelog khiến procedure được tạo trước khi cột cần thiết xuất hiện.
Migration chứa cú pháp chỉ được hệ quản trị thử nghiệm hỗ trợ; kiểm thử với database nhúng vượt qua nhưng triển khai lên hệ quản trị production thất bại.
Quy trình CI chỉ tạo cơ sở dữ liệu sạch rồi chạy toàn bộ migration; hệ thống production có dữ liệu không chuẩn và cấu trúc đã đổi qua nhiều năm nên nâng cấp từ phiên bản cũ gặp lỗi.
Nhóm triển khai kiểm thử migration với dữ liệu mẫu vài trăm dòng, nhưng cơ sở dữ liệu thật có giá trị NULL, khóa ngoại mồ côi và mã định danh trùng từ các lần nhập cũ.
Một pull request thêm migration hợp lệ khi đứng riêng nhưng xung đột với migration từ nhánh khác đã merge trước; kiểm thử CI chưa áp dụng chuỗi migration mới nhất trên cùng một database.
Một kỹ sư sửa cấu trúc bảng trực tiếp để xử lý sự cố production rồi quên bổ sung migration tương ứng; vài ngày sau pipeline báo đối tượng đã tồn tại khi chạy bản phát hành chính thức.
Đội phát triển thực hiện thao tác sửa thủ công bảng lịch sử migration của Flyway để vượt qua lỗi checksum; lần kiểm thử khôi phục không giải thích được thứ tự thay đổi thực tế.
Pipeline cho phép tài khoản ứng dụng thực hiện cả truy vấn nghiệp vụ và migration DDL; khi triển khai môi trường mới với quyền hạn chế hơn, bước tạo bảng bị từ chối.
Ứng dụng tự khởi tạo schema bằng cơ chế ORM trong khi Flyway cũng quản lý các bảng đó; sau một lần đổi phiên bản thư viện, cấu trúc thực tế khác với nội dung migration được lưu trong Git.
Đội phát triển tạo migration để xóa cột chứa dữ liệu nhạy cảm rồi dự định rollback bản phát hành nếu có lỗi; sau khi cột bị xóa, phiên bản ứng dụng cũ không còn dữ liệu để hoạt động như trước.
Một migration gộp và xóa nhiều bản ghi lịch sử thành dữ liệu tổng hợp; khi yêu cầu quay về phiên bản trước, nhóm phát hiện dữ liệu chi tiết không thể khôi phục bằng cách đảo chiều câu lệnh.
Quy trình phát hành dùng rollback script được viết trước nhưng chưa từng chạy với dữ liệu production; khi thử trên bản sao, một ràng buộc cũ không thể tạo lại do bản ghi mới không còn phù hợp.
Một hệ quản trị hỗ trợ giao dịch cho nhiều thao tác DDL, nhưng môi trường khác trong tổ chức lại có DDL tự commit; migration bị lỗi giữa chừng và các môi trường giữ trạng thái thay đổi khác nhau.
Một changeset Liquibase gồm nhiều bước cập nhật dữ liệu và thay đổi bảng; thao tác cuối thất bại trên một môi trường, để lại một số bước đã áp dụng vì đặc tính transaction của hệ quản trị đó.
Trong đợt phát hành khẩn cấp, migration thành công nhưng ứng dụng mới lỗi nghiệp vụ; đội vận hành phải quyết định cách đưa ứng dụng cũ trở lại khi schema đã được mở rộng và dữ liệu mới vẫn tiếp tục phát sinh.
Nhóm đặt tiêu chí phát hành dựa trên tỷ lệ lỗi HTTP nhưng không giám sát lock wait và thời gian truy vấn khi chạy migration; người dùng báo hệ thống chậm dù số lỗi ứng dụng chưa tăng.
Một pipeline đã kiểm thử migration chạy trơn tru nhưng không kiểm tra khả năng ứng dụng phiên bản trước tiếp tục đọc và ghi sau khi schema mới được áp dụng; rollback ứng dụng trở nên rủi ro.
Trong lần khôi phục dữ liệu từ backup vào staging, bảng ứng dụng được khôi phục ở thời điểm cũ nhưng bảng lưu lịch sử migration lại thuộc snapshot khác; công cụ báo đã áp dụng những phiên bản mà cấu trúc thật chưa có.
Đội vận hành chuẩn bị triển khai migration sang vùng dự phòng, nhưng thứ tự phát hành ứng dụng và thay đổi schema ở hai vùng khác nhau; khi chuyển lưu lượng, một vùng trả lỗi thiếu cột.
