Một hệ thống nhân sự lưu quyền ROLE_HR_MANAGER trong GrantedAuthority nhưng endpoint duyệt bảng lương vẫn trả 403 cho trưởng phòng; hãy xây dựng tình huống xác minh sự nhất quán giữa tên quyền, role và quy tắc phân quyền.
Một ứng dụng thương mại điện tử gán authority ORDER_READ cho nhân viên chăm sóc khách hàng nhưng cấu hình HTTP chỉ nhận vai trò quản trị; hãy đặt bài toán kiểm tra khác biệt giữa role và authority tại điểm truy cập.
Cổng quản lý chi nhánh cho phép trưởng chi nhánh xem báo cáo của chi nhánh mình, còn tài khoản quản lý vùng xem nhiều chi nhánh; hãy thiết kế tình huống xác thực quyền theo phạm vi tổ chức thay vì chỉ theo tên role.
Sau khi đồng bộ quyền từ hệ thống IAM, danh sách GrantedAuthority của người dùng có tên role khác định dạng mà ứng dụng kỳ vọng; hãy đặt tình huống kiểm tra quyền thực tế trên request được bảo vệ.
Một người dùng đồng thời có quyền nhân viên và kiểm toán viên nhưng chính sách không cho kiểm toán viên duyệt giao dịch do chính mình tạo; hãy xây dựng ca kiểm chứng xung đột quyền ở thao tác duyệt.
Ứng dụng dùng phân cấp vai trò quản lý, nhưng sau đợt tái cấu trúc một vai trò cấp cao vô tình thừa hưởng quyền xóa dữ liệu; hãy yêu cầu đánh giá tác động quyền kế thừa tới các API nhạy cảm.
Nhân viên được chuyển phòng ban giữa phiên làm việc và không còn quyền phê duyệt hồ sơ cũ; hãy đặt bài toán kiểm tra hành vi phân quyền khi dữ liệu quyền thay đổi sau khi đăng nhập.
Nền tảng hỗ trợ người dùng được giao quyền tạm thời trong ngày xử lý sự cố, nhưng quyền vẫn hoạt động sau thời hạn; hãy xây dựng tình huống kiểm tra hạn hiệu lực ở thời điểm thực hiện tác vụ.
Một quản trị viên muốn cấp quyền đọc báo cáo mà không cấp quyền xuất dữ liệu khách hàng; hãy mô tả tình huống phân biệt quyền theo hành động trong cùng một màn hình.
Dịch vụ tài chính có một authority nghiệp vụ được gán cho cả tài khoản dịch vụ và tài khoản người dùng, nhưng thao tác ký duyệt chỉ dành cho con người; hãy đặt tình huống xác minh các điều kiện bổ sung của chính sách.
API quản lý hợp đồng cho phép GET công khai một số trường nhưng cấm PUT với mọi người trừ chủ sở hữu; hãy xây dựng tình huống kiểm tra phân quyền theo HTTP method trên cùng đường dẫn.
Sau khi thêm endpoint quản trị dưới đường dẫn API phiên bản mới, một quy tắc cho phép truy cập rộng hơn đã khớp trước quy tắc hạn chế; hãy đặt bài toán kiểm chứng độ ưu tiên của request matcher.
Một API có đường dẫn chứa mã khách hàng và cho phép người dùng nhập mã bất kỳ; hãy yêu cầu kiểm chứng quyền đọc khi request trỏ tới khách hàng của người khác.
Cổng đối tác có các endpoint công khai để tra cứu sản phẩm nhưng một đường dẫn nội bộ cùng tiền tố bị truy cập ẩn danh; hãy xây dựng ca kiểm tra ranh giới phân quyền theo URL.
Hệ thống xử lý đơn hàng phân biệt GET, POST và DELETE nhưng sau khi bổ sung phương thức PATCH lại dùng quyền mặc định quá rộng; hãy đặt tình huống phát hiện phương thức HTTP chưa được bao phủ.
Một API dành cho quản trị viên được tách sang SecurityFilterChain riêng, nhưng thứ tự chuỗi lọc khiến request đi vào cấu hình dành cho khách hàng; hãy mô tả tình huống đánh giá quyền truy cập thực tế.
Trang tài liệu API được mở công khai theo cấu hình mới, trong khi endpoint thử lệnh trên cùng đường dẫn vẫn thực thi thao tác quản trị; hãy xây dựng ca kiểm chứng từng request có tác dụng ghi.
Ứng dụng phục vụ cả web và mobile với đường dẫn có dấu gạch chéo cuối khác nhau; hãy đặt tình huống kiểm tra biến thể URL có dẫn đến quyền truy cập khác nhau hay không.
Một tài nguyên tĩnh chứa báo cáo nội bộ được đặt trong thư mục phục vụ file công khai sau thay đổi cấu hình; hãy xây dựng tình huống xác minh chính sách bảo vệ tài nguyên tải xuống.
Cổng quản trị dùng proxy đảo ngược để đổi tiền tố đường dẫn trước khi tới Spring Security, khiến một số URL bỏ qua quy tắc hạn chế; hãy yêu cầu kiểm thử request qua cả proxy và ứng dụng.
Một endpoint tải chứng từ hỗ trợ HTTP HEAD và GET nhưng chính sách chỉ kiểm tra GET; hãy đặt bài toán xác minh việc lộ thông tin từ các phương thức truy cập phụ.
Ứng dụng bật CORS cho cổng đối tác nhưng yêu cầu preflight OPTIONS bị từ chối, trong khi request nghiệp vụ phải tuân thủ quyền người dùng; hãy xây dựng tình huống đánh giá hai loại request này.
Một trang thống kê cần phục vụ khách chưa đăng nhập với dữ liệu tổng hợp, còn dữ liệu chi tiết chỉ dành cho nhân viên; hãy đặt bài toán kiểm chứng giới hạn dữ liệu của các endpoint tương ứng.
API xóa tài liệu yêu cầu quyền quản trị và mục đích xóa hợp lệ, nhưng cấu hình hiện chỉ kiểm tra role ở tầng HTTP; hãy xây dựng tình huống đánh giá các điều kiện ở tầng nghiệp vụ.
Một tài khoản bị chặn quyền sửa hồ sơ nhưng vẫn có thể gọi endpoint upload ảnh đại diện được triển khai ở controller khác; hãy yêu cầu xác minh chính sách bao phủ các đường thao tác tương đương.
Ứng dụng có một API cũ và một API mới cho cùng tác vụ duyệt đơn, nhưng chỉ API mới áp dụng quy tắc phân quyền chặt hơn; hãy xây dựng ca kiểm tra tính nhất quán giữa các phiên bản.
Một endpoint trả lỗi 404 cho hồ sơ không tồn tại và 403 cho hồ sơ có thật nhưng không thuộc người dùng; hãy đặt tình huống đánh giá nguy cơ tiết lộ sự tồn tại của tài nguyên qua phản hồi.
Sau khi nâng cấp Spring Security, đường dẫn lỗi và chuyển tiếp nội bộ được cấu hình khác trước, dẫn tới cách xử lý phân quyền không nhất quán; hãy đặt bài toán kiểm tra các kiểu dispatch liên quan.
Dịch vụ lưu trữ tài liệu kiểm tra quyền tại controller nhưng một tác vụ nền gọi thẳng service để tải cùng tài liệu; hãy xây dựng tình huống xác minh tầng bảo vệ dùng chung cho mọi đường gọi.
Một service thanh toán dùng kiểm tra quyền ở method, nhưng sau refactor controller gọi một method mới không có chính sách tương đương; hãy yêu cầu kiểm chứng quyền trên toàn bộ luồng thao tác.
Nhóm phát triển bật bảo vệ method trong một module nhưng các annotation phân quyền ở module khác không có hiệu lực; hãy đặt tình huống kiểm tra phạm vi cấu hình method security.
Một service xử lý đơn hàng tự gọi một method khác trong cùng bean có quy tắc phân quyền riêng; hãy đặt bài toán kiểm chứng hành vi khi lời gọi không đi qua cơ chế chặn method.
Chức năng duyệt chi phí chạy qua một bean được tạo thủ công thay vì bean do Spring quản lý, khiến kiểm tra quyền trên method không hoạt động; hãy xây dựng tình huống điều tra ranh giới thực thi.
Một phương thức đọc danh sách hóa đơn được nhiều controller gọi, trong đó một controller mở cho khách và controller kia dành cho nhân viên; hãy đặt tình huống xác minh quy tắc ở method không bị phụ thuộc vào đường HTTP.
Hệ thống áp dụng chính sách trước khi thực thi cho thao tác xóa tài khoản, nhưng dữ liệu cần kiểm tra quyền sở hữu chỉ có sau khi nạp bản ghi; hãy xây dựng tình huống đánh giá thời điểm kiểm chứng phù hợp.
Một method trả về thông tin hồ sơ cá nhân có chính sách kiểm tra kết quả, nhưng lời gọi gián tiếp qua một service khác có thể làm lộ dữ liệu; hãy đặt bài toán kiểm tra quyền đối với đối tượng trả về.
Dịch vụ quản lý vé xử lý một danh sách vé và lọc kết quả theo chủ sở hữu, nhưng một nhánh trả về toàn bộ danh sách chưa qua kiểm tra; hãy yêu cầu thiết kế ca phát hiện rò rỉ dữ liệu trong tập kết quả.
Ứng dụng có policy ở interface service, nhưng một implementation mới không thể hiện rõ quy tắc đã khai báo; hãy đặt tình huống kiểm tra hành vi bảo vệ khi gọi qua các kiểu tham chiếu khác nhau.
Một method được bảo vệ bằng biểu thức điều kiện theo tham số đầu vào nhưng đầu vào rỗng dẫn tới kết quả phân quyền không mong muốn; hãy xây dựng tình huống kiểm thử dữ liệu biên của biểu thức.
Khi xử lý yêu cầu bất đồng bộ, ngữ cảnh bảo mật tại luồng thực thi không có thông tin authority như trong HTTP request gốc; hãy đặt bài toán kiểm chứng chính sách ở bước xử lý nền.
Một tác vụ theo lịch gọi method bị giới hạn bởi quyền người dùng, nhưng không có request hay người dùng tương tác trong thời điểm chạy; hãy yêu cầu xác định tiêu chí kiểm thử phân quyền cho luồng hệ thống.
Một event listener gọi service tạo chứng từ với dữ liệu từ sự kiện nhưng không có Authentication của request gốc; hãy đặt tình huống đánh giá phân quyền method khi tác vụ được kích hoạt qua sự kiện.
Một method xử lý nhiều khoản chi trong một transaction và khoản cuối cùng không thuộc người phê duyệt; hãy xây dựng kịch bản kiểm chứng rằng kiểm tra quyền không bỏ sót một phần tử trong lô.
Một REST controller cho phép nhân viên cập nhật đơn của khách nhưng service nhận thêm tham số mã cửa hàng từ client; hãy đặt tình huống kiểm tra quyền trên đối tượng đích thay vì tin tham số.
Một khách hàng thay ID hợp đồng trong URL để xem file đính kèm của khách khác dù đã có quyền đọc hợp đồng của mình; hãy xây dựng ca kiểm thử truy cập trực tiếp tới đối tượng khác.
Người tạo bài đăng được phép sửa nội dung, còn người kiểm duyệt chỉ được ẩn bài; hãy đặt tình huống kiểm chứng chính sách theo vai trò, chủ sở hữu và từng hành động.
Trong ứng dụng bệnh viện, bác sĩ chỉ được xem hồ sơ bệnh nhân của ca điều trị được phân công, trừ bác sĩ trực cấp cứu có quyền theo ca; hãy xây dựng bài toán phân quyền theo quan hệ nghiệp vụ.
Nền tảng học trực tuyến cho giảng viên xem điểm học viên trong lớp mình, nhưng endpoint tải bảng điểm nhận mã lớp tùy ý; hãy yêu cầu xác minh quyền theo bản ghi và mối quan hệ giảng dạy.
Một trưởng nhóm được phép sửa tài liệu của nhóm khi tài liệu chưa khóa, còn tài liệu đã khóa chỉ được quản trị hệ thống mở lại; hãy xây dựng tình huống phân quyền theo trạng thái đối tượng.
Dịch vụ tuyển dụng giới hạn việc xem mức lương ứng viên theo dự án tuyển dụng, nhưng báo cáo tìm kiếm tổng hợp trả về trường lương của các dự án khác; hãy đặt bài toán kiểm tra phân quyền ở kết quả truy vấn.
Một tài khoản hỗ trợ được cấp quyền xem ticket cho khách trong phạm vi chi nhánh, nhưng chức năng gợi ý ticket liên quan trả về ticket từ chi nhánh khác; hãy xây dựng kịch bản kiểm chứng quyền ở dữ liệu liên kết.
Nhân viên bán hàng có quyền cập nhật cơ hội bán hàng của mình, nhưng sau khi chuyển chủ sở hữu trong cùng giao dịch, quyền ở bước kế tiếp vẫn dựa vào dữ liệu cũ; hãy đặt tình huống đánh giá thời điểm đọc trạng thái.
Một API cập nhật tài sản nhận danh sách ID và chỉ kiểm tra quyền với phần tử đầu tiên; hãy xây dựng tình huống kiểm chứng quyền của toàn bộ bản ghi trong yêu cầu hàng loạt.
Một báo cáo doanh số dùng phân trang và sắp xếp nhưng thông tin tổng số bản ghi bao gồm cả các đơn mà người dùng không được xem; hãy đặt bài toán kiểm tra rò rỉ thông tin qua metadata kết quả.
Hệ thống quản lý hồ sơ cho phép xem nội dung nhưng cấm tải xuống bản gốc đối với người dùng thuê ngoài; hãy xây dựng tình huống kiểm chứng phân quyền theo hình thức khai thác cùng một đối tượng.
Ứng dụng cho phép nhân viên thảo luận trong dự án đang tham gia, nhưng một WebSocket subscription vẫn nhận thông điệp sau khi họ bị xóa khỏi dự án; hãy yêu cầu đánh giá quyền truy cập theo thay đổi thành viên.
Một GraphQL endpoint có truy vấn công khai về sản phẩm và trường giá vốn chỉ dành cho quản lý, nhưng chính sách hiện chỉ bảo vệ toàn bộ endpoint HTTP; hãy đặt tình huống kiểm tra quyền tới dữ liệu cụ thể.
Khi một khách hàng chuyển sang tổ chức khác, các file được chia sẻ từ tổ chức cũ vẫn truy cập được qua đường dẫn lưu sẵn; hãy xây dựng tình huống xác minh thu hồi quyền theo quan hệ đối tượng.
Nền tảng đa tenant cho nhân viên công ty A gửi request với header tenant của công ty B và vẫn có quyền ROLE_MANAGER; hãy xây dựng ca kiểm chứng cách ly dữ liệu tenant.
Một người dùng là thành viên hai tenant với role khác nhau và thực hiện thao tác trên tenant phụ, nhưng quyền được chọn theo tenant mặc định; hãy đặt bài toán kiểm tra authority theo tenant đang xử lý.
API kế toán truyền tenant ID ở đường dẫn và tài khoản thanh toán ở body; hai giá trị thuộc tenant khác nhau nhưng request vẫn được chấp nhận; hãy xây dựng tình huống phát hiện truy cập chéo tenant.
Cổng SaaS nhận JWT có danh sách tenant mà người dùng tham gia, nhưng tài nguyên bị chuyển chủ tenant sau khi token được phát hành; hãy yêu cầu đánh giá quyền theo trạng thái dữ liệu hiện thời.
Quản trị viên tenant chỉ được thêm người trong tổ chức mình, nhưng thao tác mời qua email cho phép gán role ở tenant khác; hãy đặt tình huống kiểm chứng ranh giới quản trị.
Một endpoint thống kê nhóm bản ghi theo tenant nhưng lớp cache dùng cùng khóa cho mọi tenant, khiến quản lý công ty B nhận dữ liệu đã lưu của công ty A; hãy xây dựng tình huống đánh giá phân quyền khi trả kết quả cache.
Bộ lọc danh sách hóa đơn chỉ áp dụng tenant ở repository chính, còn truy vấn đếm sử dụng native SQL không ràng buộc tenant; hãy đặt bài toán kiểm chứng tính nhất quán dữ liệu hiển thị.
Một dịch vụ chia sẻ tài liệu có tài nguyên cha thuộc tenant A nhưng file đính kèm lại tham chiếu bản ghi ở tenant B; hãy xây dựng ca kiểm tra ranh giới tenant qua quan hệ tài nguyên.
Người dùng vừa được xóa khỏi một tenant nhưng kết nối HTTP dài vẫn còn authority cũ; hãy đặt tình huống đánh giá yêu cầu cập nhật quyền và độ trễ thu hồi cho thao tác nhạy cảm.
Ứng dụng cho phép nhân viên hỗ trợ truy cập nhiều tenant theo ca xử lý được cấp phép, nhưng nút chuyển tenant không ghi nhận phạm vi ca; hãy đặt bài toán kiểm tra quyền đặc biệt dựa trên ngữ cảnh.
Một batch job tổng hợp dữ liệu của các tenant chạy bằng tài khoản kỹ thuật, nhưng một API nội bộ cho phép người dùng kích hoạt job với tenant tùy ý; hãy xây dựng tình huống xác minh quyền kích hoạt và phạm vi dữ liệu.
Hệ thống phân quyền tài liệu bằng ACL có chủ sở hữu và người được chia sẻ quyền đọc, nhưng người được chia sẻ vẫn sửa được bản ghi sau khi cập nhật policy; hãy xây dựng ca kiểm chứng permission theo từng đối tượng.
Một thư mục dự án cấp quyền đọc cho thành viên, nhưng file nhạy cảm bên trong được đánh dấu riêng tư; hãy đặt tình huống kiểm tra tính kế thừa và ngoại lệ của ACL.
Một quản lý chuyển quyền sở hữu tài liệu cho nhân viên khác nhưng ACL cũ vẫn cho phép người quản lý chỉnh sửa; hãy yêu cầu đánh giá tính nhất quán giữa owner và các ACE đang lưu.
Ứng dụng cho phép chia sẻ file theo người dùng hoặc nhóm, nhưng khi người dùng rời nhóm cũ họ vẫn mở được file chỉ cấp cho nhóm; hãy xây dựng bài toán kiểm chứng thay đổi membership.
Một báo cáo dữ liệu áp dụng ACL cho từng bản ghi nhưng API xuất CSV bỏ qua danh sách bản ghi mà người gọi được quyền xem; hãy xây dựng tình huống kiểm tra phân quyền ở luồng xuất hàng loạt.
Kho lưu trữ hợp đồng có nhiều kiểu định danh đối tượng với giá trị ID trùng nhau, khiến việc tra cứu ACL đôi khi áp dụng quyền từ loại đối tượng khác; hãy đặt bài toán kiểm chứng việc định danh đối tượng được bảo vệ.
Một user được chia sẻ quyền đọc ảnh trong bộ sưu tập nhưng endpoint tạo liên kết tải ảnh lại chỉ xét quyền của bộ sưu tập; hãy xây dựng tình huống phát hiện bất nhất giữa quyền tài nguyên cha và con.
Đội bảo mật thay đổi chính sách ACL từ quyền nhóm sang quyền cá nhân, nhưng dữ liệu quyền cũ vẫn tồn tại sau migration; hãy đặt tình huống kiểm tra hiệu lực các bản ghi quyền sau chuyển đổi.
Người dùng có quyền đọc hồ sơ theo ACL, nhưng phương thức tra cứu trả cả thông tin người khác qua liên kết một-nhiều; hãy yêu cầu xây dựng ca kiểm tra từng đối tượng liên quan.
Một chức năng sao chép tài liệu tạo đối tượng mới nhưng sao chép luôn ACL của tài liệu nguồn thuộc khách hàng khác; hãy đặt tình huống đánh giá quyền truy cập vào bản sao và dữ liệu gốc.
Một quản trị viên cấp quyền xem tạm thời cho đối tác ngoài doanh nghiệp, nhưng việc thu hồi không ảnh hưởng tới bản sao tài liệu đã tạo trong ứng dụng; hãy xây dựng kịch bản xác định phạm vi thu hồi quyền.
Dịch vụ thương mại điện tử cần kiểm tra người mua chỉ được hủy đơn trước khi đóng gói, còn nhân viên kho có quyền hủy theo lý do cụ thể; hãy xây dựng tình huống thiết kế đầu vào ngữ cảnh cho AuthorizationManager.
Một chính sách AuthorizationManager tra cứu cơ sở dữ liệu để xác định quyền truy cập, nhưng khi dữ liệu quyền tạm thời không sẵn sàng hệ thống trả kết quả không nhất quán; hãy đặt bài toán kiểm thử hành vi khi thiếu bằng chứng phân quyền.
Ứng dụng bảo vệ thao tác hoàn tiền bằng quyền kế toán và hạn mức tùy cấp bậc, nhưng hạn mức có thể thay đổi trong ngày; hãy xây dựng tình huống xác minh quyết định quyền dựa trên ngữ cảnh cập nhật.
Một cửa hàng chỉ được điều chỉnh giá trong giờ vận hành, nhưng tài khoản quản trị khẩn cấp có phạm vi ngoại lệ hẹp; hãy đặt tình huống kiểm chứng chính sách kết hợp thời gian, role và ngoại lệ.
Chức năng phê duyệt giao dịch yêu cầu hai người khác nhau tạo và duyệt, trong khi cả hai đều có authority APPROVE_TRANSFER; hãy xây dựng bài toán kiểm chứng phân tách nhiệm vụ theo lịch sử giao dịch.
Một ứng dụng cho phép quyền tạm thời qua hệ thống phê duyệt bên ngoài, nhưng phản hồi quyền về chậm khiến request có thể được thực thi hai lần; hãy đặt tình huống đánh giá tính nhất quán của quyết định phân quyền.
Một API hỗ trợ thao tác thay mặt khách hàng khi có giấy ủy quyền còn hiệu lực, nhưng backend chỉ kiểm tra role nhân viên hỗ trợ; hãy yêu cầu kiểm chứng phạm vi, mục đích và thời hạn ủy quyền.
Một hệ thống cho phép giám sát viên duyệt lệnh khi trạng thái là WAITING_APPROVAL, nhưng trạng thái có thể đổi giữa lúc kiểm tra quyền và lúc cập nhật; hãy xây dựng tình huống kiểm tra thay đổi trạng thái đồng thời.
Một công cụ nội bộ áp dụng chính sách theo địa chỉ mạng của văn phòng, nhưng request đi qua proxy và có nhiều header chuyển tiếp; hãy đặt tình huống đánh giá nguồn dữ liệu ngữ cảnh đáng tin cậy.
Một nhân viên thuộc nhóm tài chính được phép xem báo cáo tổng hợp, nhưng việc xem chi tiết yêu cầu hồ sơ đã được kiểm duyệt; hãy xây dựng kịch bản kiểm chứng nhiều điều kiện trong cùng một quyết định phân quyền.
Ứng dụng chấp nhận quyền truy cập nếu một trong hai quy tắc kiểm tra đạt, nhưng một nghiệp vụ thanh toán thực tế cần đồng thời thỏa cả hai; hãy đặt bài toán kiểm tra cách kết hợp các quyết định của AuthorizationManager.
Khi cơ sở dữ liệu quyền quá tải, một bộ đệm quyết định phân quyền có thể dùng lại kết quả của người dùng trước do khóa cache thiếu thông tin đối tượng; hãy xây dựng tình huống kiểm chứng phạm vi quyết định và khóa cache.
Một endpoint quản trị bắt đầu sử dụng tính năng mới nhưng không có quy tắc phân quyền cụ thể, khiến request rơi vào nhánh mặc định; hãy yêu cầu đánh giá chính sách cho phép hay từ chối khi không khớp.
Một yêu cầu có đầy đủ quyền ghi nhưng đối tượng đã bị khóa theo quy định lưu trữ; hãy xây dựng tình huống phân biệt quyền người dùng và điều kiện nghiệp vụ mà quyết định cấp phép phải xét.
Một endpoint cần trả 401 khi chưa có danh tính và 403 khi đã đăng nhập nhưng không đủ quyền, nhưng các bài test hiện xem hai trường hợp là tương đương; hãy đặt tình huống kiểm tra phản hồi từ chối.
Một API sửa thông tin nhân viên bị truy cập bằng tài khoản không có quyền, nhưng thao tác ghi vẫn xảy ra trước khi phản hồi lỗi; hãy xây dựng ca kiểm chứng rằng việc từ chối không gây tác dụng phụ.
Nhóm triển khai kiểm thử HTTP bằng MockMvc với tài khoản có role quản trị, nhưng chưa có ca âm tính cho nhân viên thường; hãy xây dựng tình huống kiểm tra quyền được cấp và quyền bị từ chối.
Một test dùng @WithMockUser gán sẵn ROLE_ADMIN và luôn xanh, trong khi quyền thực tế từ JWT chỉ mang giá trị ADMIN không được ánh xạ tương đương; hãy đặt bài toán kiểm tra chênh lệch giữa mock và cấu hình thật.
Ứng dụng lưu tên nhóm quyền trong claim JWT tùy biến và xây dựng GrantedAuthority từ claim đó, nhưng sau đổi định dạng claim một số endpoint mở sai quyền; hãy xây dựng tình huống kiểm thử ánh xạ claim đến chính sách.
Một bài kiểm thử method security gọi trực tiếp vào đối tượng service tạo mới nên không quan sát được cơ chế chặn của Spring; hãy đặt tình huống xác minh phép kiểm thử thực sự đi qua bean được bảo vệ.
Một người dùng không có quyền xóa hợp đồng thử gọi DELETE bằng ID hợp đồng có thật và ID không tồn tại, nhưng hệ thống để lộ khác biệt qua body lỗi; hãy xây dựng ca kiểm tra nội dung phản hồi từ chối.
Cổng quản trị ghi log mọi request 403 nhưng log chứa toàn bộ dữ liệu hồ sơ mà người gọi không được quyền xem; hãy đặt tình huống đánh giá bảo mật thông tin trong cơ chế quan sát từ chối.
Một bộ kiểm thử chỉ kiểm tra status 403 khi bị chặn, nhưng không phát hiện các email thông báo và bản ghi audit được tạo ngoài ý muốn; hãy xây dựng tình huống xác minh không có tác dụng phụ sau từ chối.
Khi người dùng không còn thuộc nhóm dự án, API sửa task trả 403 nhưng API cập nhật hàng loạt vẫn thành công; hãy xây dựng ca kiểm tra hồi quy trên các lối vào tương đương.
Một pull request thêm controller cho chức năng quản lý người dùng, nhưng không bổ sung kiểm tra phân quyền vào tập test CI; hãy đặt tình huống xác định tiêu chí chặn merge khi thiếu ca từ chối.
Nhiều cấu hình SecurityFilterChain được thay đổi trong đợt nâng cấp framework, và chỉ test đơn lẻ từng controller còn xanh; hãy yêu cầu xây dựng kịch bản kiểm thử end-to-end các quy tắc HTTP quan trọng.
Sau khi tối ưu truy vấn ACL, API danh sách tài liệu trả dữ liệu nhanh hơn nhưng đồng thời xuất hiện tài liệu không có quyền đọc; hãy đặt bài toán kiểm chứng tính đúng của phân quyền sau thay đổi hiệu năng.
Một hệ thống đa tenant chạy kiểm thử với toàn bộ tài khoản mẫu thuộc một tenant, nên không phát hiện truy cập trái phép giữa tenant A và tenant B; hãy yêu cầu thiết kế bộ dữ liệu kiểm thử bao phủ trường hợp bị từ chối.
Trong kỳ kiểm toán, nhóm được yêu cầu chứng minh mọi API quản trị, method nhạy cảm và truy vấn dữ liệu đều có ca từ chối quyền; hãy xây dựng tình huống lập ma trận kiểm chứng và đánh giá mức độ bao phủ.
Khi hệ thống phân quyền từ chối một giao dịch hợp lệ do cache quyền cập nhật chậm, người dùng gửi lại nhiều lần; hãy đặt tình huống kiểm chứng quyết định quyền, dấu vết audit và khả năng tái hiện sự cố.
