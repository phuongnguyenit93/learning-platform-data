Một ngân hàng chuyển quy trình đăng ký vay sáu màn hình sang Spring Web Flow; khách hàng quay lại sửa thu nhập ở bước đầu nhưng bước xác nhận cuối vẫn hiển thị hạn mức được tính từ dữ liệu cũ.
Một doanh nghiệp bảo hiểm có luồng khai báo bồi thường với các bước khác nhau cho tai nạn xe và thiệt hại tài sản; người dùng đổi loại yêu cầu giữa chừng nhưng luồng tiếp tục qua nhánh không còn phù hợp.
Một cổng đại học dùng view-state cho đăng ký nhập học, nhưng nút Tiếp tục ở màn hình chọn ngành gửi event không khớp với transition đã khai báo khiến hồ sơ đứng yên tại một bước.
Một nền tảng thương mại dùng Spring Web Flow cho checkout và cần xử lý việc người mua trở lại màn hình vận chuyển sau khi đã chọn phương thức thanh toán, trong khi phí giao hàng trên màn hình cuối bị sai.
Một hệ thống cấp phép xây dựng điều hướng qua nhiều bước dựa trên câu trả lời về loại công trình; một hồ sơ đặc biệt không đi vào nhánh thẩm định bắt buộc dù các hồ sơ thông thường vẫn chạy đúng.
Một ứng dụng mở tài khoản trực tuyến vừa lưu dữ liệu form khi chuyển bước vừa xử lý nút Quay lại; khi người dùng sửa địa chỉ cũ, giá trị mới biến mất sau khi quay về màn hình kế tiếp.
Một cổng phúc lợi nhân viên có biểu mẫu khai người phụ thuộc gồm các dòng thêm và xóa động; việc chuyển view-state làm lệch vị trí các phần tử được binding sau một lần xóa dòng ở giữa.
Một cổng đăng ký dịch vụ quốc tế tiếp nhận ngày sinh và số tiền theo nhiều ngôn ngữ; sau khi đổi locale ở bước hai, cùng một giá trị form được binding khác với dữ liệu người dùng đã nhập ở bước một.
Một luồng đăng ký bảo hiểm chỉ yêu cầu trường thông tin sức khỏe khi người mua chọn gói đặc biệt; các thông báo validation cho trường không còn hiển thị vẫn ngăn người dùng đi tiếp.
Một quy trình đăng ký học bổng kiểm tra tổng thu nhập từ nhiều thành viên gia đình; từng màn hình đều hợp lệ nhưng lỗi kiểm tra liên bước chỉ xuất hiện khi người dùng nhấn Nộp hồ sơ.
Một ứng dụng báo cáo thuế dùng validation khác nhau cho bản nháp và nộp chính thức; sau khi người dùng lưu nháp từ một view-state, luồng yêu cầu tất cả trường bắt buộc của bước nộp.
Một cổng tuyển dụng cho phép tải hồ sơ lên ở bước ba; sau khi người dùng quay lại cập nhật kỹ năng rồi tiến tới bước xác nhận, thông tin tệp đã tải lên không còn gắn với flow.
Một hệ thống đăng ký hội nghị có hành trình bốn bước; người dùng làm mới trình duyệt tại màn hình thanh toán và được yêu cầu bắt đầu lại dù phiên đăng nhập vào trang vẫn còn hiệu lực.
Một nền tảng ký hợp đồng trực tuyến mở flow bằng đường dẫn từ email; người dùng đi thẳng đến URL của bước xác nhận mà chưa hoàn thành các bước xem điều khoản và kiểm tra danh tính.
Một ứng dụng nộp đơn chuyển thông tin giữa các bước qua redirect của Spring MVC; sau redirect, dữ liệu chỉ tồn tại trong requestScope bị mất nên màn hình tiếp theo xuất hiện biểu mẫu trống.
Một trang đặt phòng hiển thị thông báo thành công sau event đặt chỗ, nhưng thông báo lưu trong flashScope biến mất khi người dùng tải lại màn hình kết thúc sau một lần chuyển hướng bổ sung.
Một cổng xử lý khiếu nại lưu dữ liệu nhập trong viewScope ở nhiều màn hình khác nhau; sau khi sang bước xác nhận, các trường đã nhập tại bước trước không còn khả dụng cho phần tổng hợp.
Một ứng dụng đặt lịch khám dùng flowScope cho lựa chọn chuyên khoa và bác sĩ; khi người dùng thay chuyên khoa, lịch của bác sĩ cũ vẫn tồn tại trong flow và tạo ra một lựa chọn không hợp lệ.
Một cổng đăng ký nhà cung cấp lưu ngữ cảnh công ty trong conversationScope; sau khi hoàn tất một flow và bắt đầu đăng ký công ty thứ hai, các giá trị của hồ sơ trước xuất hiện trở lại.
Một nền tảng thương mại có hai quy trình mua hàng mở trong hai tab của cùng trình duyệt; thao tác ở tab thứ hai làm thông tin giỏ hàng của tab đầu thay đổi trước khi người dùng xác nhận.
Một hệ thống vay tiêu dùng gửi cùng event Xác nhận hai lần khi khách hàng nhấn đúp nút trên đường truyền chậm; dịch vụ nghiệp vụ nhận hai yêu cầu tạo hợp đồng trong khi màn hình chỉ hiện một kết quả.
Một cổng cấp chứng chỉ cho phép người dùng quay lại bằng nút Back sau khi flow đã kết thúc; trình duyệt gửi event từ một view-state cũ và server không còn tìm thấy flow execution tương ứng.
Một hệ thống cấp phép có trang xác nhận chứa nhiều nút điều hướng; người dùng gửi event bị sửa thủ công từ trình duyệt và có thể yêu cầu transition dành riêng cho vai trò kiểm duyệt.
Một ứng dụng xử lý hồ sơ dùng form POST cho các bước thay đổi dữ liệu; sau khi bộ phận bảo mật bật CSRF protection ở Spring Security, chỉ các transition được kích hoạt từ biểu mẫu cũ bị từ chối.
Một trang dịch vụ công tích hợp Spring Web Flow với đăng nhập SSO; người dùng mất phiên ở lúc xác thực ngoài và sau khi quay lại có đăng nhập thành công nhưng không tiếp tục được flow đang làm.
Một trung tâm giao dịch chạy ứng dụng Spring MVC trên nhiều pod; lượt chuyển bước đầu thành công nhưng request tiếp theo được điều phối sang pod khác lại báo không tồn tại flow execution.
Một cổng đào tạo dùng kho phiên tập trung cho các flow đang mở; sau khi triển khai phiên bản ứng dụng mới, dữ liệu đối tượng lưu trong flow không còn tương thích khi các request quay về pod cũ.
Một ứng dụng du lịch đưa Spring Web Flow ra sau reverse proxy đổi prefix của URL; liên kết chuyển trạng thái và form action trên một số view-state quay về địa chỉ nội bộ thay vì URL công khai.
Một cổng khách hàng có luồng nhập thông tin kéo dài gần một giờ; session hết hạn khi người dùng đang xem bước cuối và toàn bộ dữ liệu chưa lưu biến mất sau lần nhấn Tiếp tục.
Một công ty điện lực phải giới hạn số flow dở dang trên mỗi phiên; người dùng mở nhiều hồ sơ mới rồi đóng trình duyệt mà không hoàn tất, khiến dung lượng lưu trạng thái tăng dần theo thời gian.
Một hệ thống tuyển sinh giữ ảnh và tệp đính kèm dung lượng lớn trong flowScope qua nhiều bước; khi chiến dịch tuyển sinh bắt đầu, bộ nhớ và thời gian lưu phiên tăng mạnh theo số người dùng.
Một dịch vụ đặt khám dùng action-state để kiểm tra lịch trống qua API bệnh viện; khi API mất kết nối, một số flow dừng ở trạng thái xử lý mà không hiển thị thông tin lỗi cho người dùng.
Một nền tảng cấp khoản vay gọi dịch vụ chấm điểm tín dụng trong transition; khi dịch vụ phản hồi chậm, trình duyệt gửi lại event và hai lượt kiểm tra trả về kết quả vào các thời điểm khác nhau.
Một ứng dụng quản lý sự kiện phải giữ lựa chọn ghế trong lúc người dùng nhập thông tin thanh toán; flow bị hủy hoặc hết hạn nhưng tài nguyên ghế đã giữ vẫn không được giải phóng.
Một trang bán vé hoàn tất thanh toán tại hệ thống ngoài trước khi vào end-state; trình duyệt ngắt kết nối làm người mua không biết giao dịch đã được ghi nhận hay cần thực hiện lại.
Một ngân hàng dùng decision-state để rẽ nhánh phê duyệt theo khoản vay; kết quả tính toán được lưu từ bước trước làm hồ sơ vừa sửa số tiền vẫn đi theo nhánh đánh giá cũ.
Một hệ thống khám bệnh tái sử dụng subflow xác nhận thông tin liên hệ trong cả đặt lịch và đăng ký bệnh nhân; một luồng cha nhận dữ liệu đúng còn luồng kia mất thông tin sau khi subflow kết thúc.
Một cổng dịch vụ công gọi subflow xác thực người đại diện trước khi nộp giấy phép; người dùng nhấn Hủy trong subflow nhưng luồng cha lại tiếp tục sang bước nộp hồ sơ.
Một nền tảng thương mại có subflow đổi địa chỉ giao hàng được dùng trong quy trình checkout; sau khi subflow trả về, phí vận chuyển tại luồng cha không còn phù hợp với địa chỉ mới.
Một ứng dụng đào tạo mở subflow thanh toán khóa học từ hai hành trình đăng ký khác nhau; hai flow cha xử lý event trả về của subflow khác nhau, khiến một hành trình không thể đi đến màn hình hoàn tất.
Một cổng bảo hiểm có các subflow lồng nhau để xác minh hồ sơ và chọn người thụ hưởng; khi người dùng quay lại một nhánh trước đó, màn hình hiển thị trạng thái của lượt chạy subflow cũ.
Một hệ thống hồ sơ bệnh án cần lưu lại ai đã đi qua mỗi transition phục vụ kiểm toán; nhật ký chỉ ghi request HTTP nên không phân biệt được event chuyển bước với lần tải lại cùng view-state.
Một ứng dụng học trực tuyến cho phép bỏ qua bước chọn lớp đối với học viên đã có quyền truy cập; sau khi quyền được cập nhật giữa phiên, flow vẫn điều hướng theo kết quả kiểm tra cũ.
Một nền tảng nghiệp vụ tích hợp Spring Web Flow trong Spring MVC nhưng mapping của một controller hiện có trùng với đường dẫn khởi tạo flow, khiến request đi vào cơ chế điều hướng khác nhau giữa các môi trường.
Một cổng đăng ký học phần dùng giao diện Thymeleaf cho một số view-state và JSP cho phần còn lại; sau đợt cập nhật UI, chỉ một nhóm form không gửi đúng event khi nhấn nút xác nhận.
Một ứng dụng thay đổi mật khẩu yêu cầu xác thực lại trước bước cuối; sau khi quyền đăng nhập của người dùng bị thu hồi giữa flow, màn hình xác nhận vẫn gửi yêu cầu lưu thay đổi.
Một quy trình phê duyệt chi tiêu yêu cầu người lập hồ sơ và người duyệt thao tác tại các thời điểm khác nhau; đội phát triển nhận thấy flow trong session của người lập không phù hợp khi người duyệt mở hồ sơ ở phiên riêng.
Một nền tảng quản trị kho có hai nhân viên cùng mở quy trình chỉnh sửa mặt hàng; người thứ hai lưu thay đổi trước khi người thứ nhất hoàn tất flow, khiến dữ liệu trên màn hình xác nhận của người thứ nhất đã lỗi thời.
Một cổng bảo hiểm dùng transition để ghi thông tin vào cơ sở dữ liệu giữa các bước; người dùng quay lại màn hình trước rồi gửi sự kiện xác nhận lần nữa khiến tác vụ ghi chạy lặp.
Một hệ thống tuyển dụng dùng flow để kiểm soát nhiều bước nhưng controller cũ vẫn nhận trực tiếp URL gửi hồ sơ; nhóm QA phát hiện hai đường hoàn tất có hành vi validation khác nhau.
Một ứng dụng cho thuê xe mở flow mới cho từng lần thuê; khi người dùng chọn Hủy ở bước cuối, thông tin hợp đồng nháp vẫn xuất hiện trong mục đơn hàng đang xử lý.
Một nhóm kiểm thử chỉ kiểm tra chuyển từ view-state đầu đến end-state bằng dữ liệu hợp lệ; khi triển khai, các event Hủy, Quay lại và validation thất bại ở giữa flow gây lỗi điều hướng chưa được phát hiện.
Một dự án Spring Web Flow có các subflow dùng chung giữa nhiều quy trình, nhưng bài kiểm thử chỉ chạy subflow độc lập và không phát hiện event kết thúc bị luồng cha diễn giải sai.
Một nhóm QA cần tái hiện trường hợp hết hạn session ngay trước transition cuối, song bộ kiểm thử hiện chỉ khởi chạy flow mới và chưa có kịch bản phục hồi khi flow execution không còn.
Một ứng dụng bán hàng có lượt chuyển bước phụ thuộc dữ liệu trả về từ API bên ngoài; bài kiểm thử luôn giả lập API thành công nên không phát hiện hành vi sau timeout hoặc lỗi nghiệp vụ.
Một hệ thống Spring MVC kết hợp Web Flow chuẩn bị nâng phiên bản thư viện và đổi template; bộ kiểm thử hồi quy chưa xác nhận lại binding form, scope, subflow, điều hướng và khả năng tiếp tục từ phiên đã mở.
