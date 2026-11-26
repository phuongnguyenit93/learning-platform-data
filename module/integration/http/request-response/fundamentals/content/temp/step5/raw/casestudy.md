Một trang thương mại điện tử tạo URL tìm sản phẩm với nhiều bộ lọc, dấu cách và ký tự tiếng Việt; liên kết hoạt động trên trình duyệt nhưng cho kết quả khác khi ứng dụng di động gửi cùng bộ lọc.
Ứng dụng quản lý tài liệu dùng mã tệp chứa dấu gạch chéo trong một thành phần đường dẫn URL; sau khi đi qua reverse proxy, máy chủ hiểu mã tệp thành hai phân đoạn tài nguyên.
Người dùng gửi cho bộ phận hỗ trợ đường dẫn có dấu thăng và tên tab chi tiết; nhật ký HTTP tại máy chủ không ghi nhận phần sau dấu thăng, khiến hai bên hiểu khác nhau về yêu cầu đã gửi.
Hai dịch vụ cùng gọi endpoint sản phẩm nhưng một bên thêm dấu gạch chéo cuối đường dẫn và bên kia thay chữ hoa thành chữ thường; quy tắc định tuyến và cache khiến các kết quả không nhất quán.
Trang đặt phòng dùng tham số truy vấn lặp lại để chọn nhiều tiện ích; một thư viện HTTP chỉ giữ giá trị cuối cùng trong khi thư viện khác giữ đủ các giá trị, làm kết quả tìm kiếm khác nhau.
Ứng dụng quản trị kích hoạt thao tác khóa tài khoản bằng liên kết GET; trình thu thập liên kết của hệ thống bảo mật truy cập trước đường dẫn và vô tình làm thay đổi trạng thái tài khoản.
Trình kiểm tra tình trạng dịch vụ gửi yêu cầu HEAD tới máy chủ chứa ảnh; máy chủ vẫn trả toàn bộ nội dung ảnh, làm tăng băng thông dù phía kiểm tra chỉ cần thông tin phản hồi.
Ứng dụng đặt hàng gửi POST tạo đơn rồi mất kết nối trước khi nhận phản hồi; người dùng bấm gửi lần nữa và phát hiện hai đơn có cùng giỏ hàng trong lịch sử.
Ứng dụng quản lý nhân sự chỉ truyền trường điện thoại trong yêu cầu PUT cập nhật hồ sơ; các trường tên và địa chỉ đã tồn tại biến mất khỏi bản ghi sau khi máy chủ xử lý.
Hai phiên bản ứng dụng cùng dùng PATCH cập nhật hồ sơ khách hàng; một phiên bản gửi trường bị bỏ qua còn phiên bản khác gửi giá trị null, khiến dữ liệu được giữ hoặc xóa theo cách khó dự đoán.
Dịch vụ đối tác gửi DELETE cho một tài nguyên đã bị xóa ở lần gọi trước; lần thử lại nhận lỗi máy chủ dù trạng thái đích đã đạt được, khiến bên đối tác tiếp tục gửi yêu cầu.
Giao diện web gọi API từ miền khác bằng phương thức có header tùy chỉnh; trình duyệt gửi OPTIONS trước, nhưng API gateway trả phản hồi không cho phép yêu cầu chính tiếp tục.
Một dịch vụ tìm kiếm gửi bộ điều kiện truy vấn dưới dạng body của GET; khi qua thiết bị trung gian, body không được chuyển tiếp như mong đợi và kết quả không còn khớp với truy vấn ban đầu.
Ứng dụng khách tạo mới hồ sơ bằng POST và nhận HTTP 200 với body rỗng; ứng dụng không biết URI của tài nguyên mới để hiển thị chi tiết vừa tạo.
Hệ thống xuất báo cáo nhận yêu cầu rồi xử lý trong vài phút; API trả HTTP 202 nhưng màn hình lại đánh dấu báo cáo đã hoàn thành ngay lúc tiếp nhận.
API cập nhật tùy chọn người dùng trả HTTP 204 cùng một chuỗi JSON xác nhận; một số thư viện khách bỏ qua body, còn thư viện khác báo lỗi khi cố đọc nội dung.
Một CDN trả HTTP 304 cho yêu cầu tải ảnh không kèm điều kiện tái xác thực; trình duyệt không có bản lưu phù hợp nên không thể hiển thị ảnh.
API đặt lịch trả cùng một mã lỗi cho dữ liệu ngày không hợp lệ và cuộc hẹn xung đột với lượt đặt khác; giao diện không phân biệt được lỗi đầu vào với lỗi trạng thái tài nguyên.
Ứng dụng gọi API bằng token đã hết hạn, còn nhân viên hợp lệ cố đọc bảng lương ngoài quyền hạn; hai yêu cầu đều nhận cùng phản hồi khiến ứng dụng xử lý đăng nhập và phân quyền sai.
Một bài viết bị chuyển sang trạng thái đã xóa vĩnh viễn, còn một đường dẫn khác chưa từng tồn tại; API trả kết quả không phân biệt khiến ứng dụng lưu trữ liên kết cũ không biết tài nguyên đã bị gỡ.
Một đối tác gửi quá nhiều yêu cầu tra cứu trong đợt cao điểm và nhận HTTP 429; các client tiếp tục thử lại tức thì vì không hiểu thông tin thời điểm được phép gọi tiếp.
Người dùng gặp lỗi khi API gateway không kết nối được với dịch vụ nguồn và khi dịch vụ nguồn phản hồi quá chậm; công cụ giám sát chỉ hiển thị lỗi HTTP chung nên khó xác định điểm lỗi.
Một reverse proxy phục vụ nhiều ứng dụng trên cùng địa chỉ IP; yêu cầu từ client thiếu hoặc mang giá trị Host không phù hợp và bị chuyển đến trang của ứng dụng khác.
Thiết bị IoT gửi body JSON nhưng khai báo Content-Type là dữ liệu biểu mẫu; ứng dụng server chọn bộ phân tích không phù hợp nên từ chối nội dung dù body nhìn có vẻ hợp lệ.
Một endpoint trả được JSON và XML theo khả năng client; hệ thống mobile gửi Accept chỉ cho phép JSON nhưng máy chủ vẫn gửi XML, làm quá trình giải mã phản hồi thất bại.
Cổng thông tin du lịch cho phép chọn tiếng Việt và tiếng Anh qua Accept-Language; bộ nhớ đệm trung gian phát lại phần mô tả tiếng Anh cho người dùng đã yêu cầu tiếng Việt.
Máy chủ bật nén gzip cho phản hồi danh sách sản phẩm, nhưng một thiết bị khách không khai báo hỗ trợ nén trong header Accept-Encoding; thiết bị nhận dữ liệu không thể giải mã thành nội dung ban đầu.
Ứng dụng gửi nội dung biểu mẫu tiếng Việt qua HTTP và máy chủ giải mã theo bộ ký tự khác; tên khách hàng hiển thị lỗi dấu trong cơ sở dữ liệu dù byte truyền tải không bị thiếu.
Người dùng đăng nhập tại miền cửa hàng rồi được chuyển hướng sang miền thanh toán; yêu cầu sau chuyển hướng không còn header Authorization, làm bước xác nhận đơn bị từ chối.
Một ứng dụng đặt vé lưu phiên trong cookie; sau khi chuyển ứng dụng sang tên miền phụ và thêm luồng thanh toán ngoài trang, trình duyệt ngừng gửi cookie ở một số yêu cầu dù phiên chưa hết hạn.
Đội tích hợp phát hiện một thiết bị trung gian xử lý khác nhau hai header chỉ khác chữ hoa và chữ thường; một số yêu cầu có giá trị header bị mất trước khi đến ứng dụng.
Cổng thông tin khách hàng gửi phản hồi chứa lịch sử giao dịch qua proxy dùng cache chung; sau khi người dùng đổi tài khoản, màn hình hiển thị nội dung của phiên đăng nhập trước.
Ứng dụng thương mại điện tử phát hành ảnh sản phẩm có cùng URL trong nhiều tháng; sau khi thay ảnh, các trình duyệt vẫn hiện phiên bản cũ vì chỉ dẫn cache còn hiệu lực.
Ứng dụng tải bảng tin kèm If-None-Match từ ETag đã lưu; sau khi nội dung thay đổi, máy chủ vẫn trả HTTP 304 khiến thiết bị không nhận bài viết mới.
Dịch vụ tài liệu dùng Last-Modified và If-Modified-Since để kiểm tra cập nhật; hai lần chỉnh sửa sát nhau trong một giây làm một số client bỏ lỡ phiên bản mới.
API hồ sơ trả các bản trình bày khác nhau tùy header Accept; cache chỉ dùng URL làm khóa nên đôi khi trả JSON cho client đã yêu cầu một định dạng khác.
Một đợt giảm giá kết thúc nhưng CDN tiếp tục phục vụ giá cũ trong khi API nguồn đã cập nhật; ứng dụng đặt hàng và trang sản phẩm hiển thị hai mức giá khác nhau.
Một trang tin đổi cấu trúc đường dẫn và trả chuyển hướng vĩnh viễn từ URL cũ; sau khi đội vận hành đổi đích thêm lần nữa, một số trình duyệt vẫn dùng địa chỉ chuyển hướng đã lưu.
Người dùng gửi biểu mẫu đăng nhập bằng POST và nhận chuyển hướng HTTP 302; các trình duyệt tiếp tục điều hướng bằng phương thức khác với yêu cầu ban đầu khiến bước sau xử lý thiếu dữ liệu.
Ứng dụng tải tệp bằng POST được chuyển hướng giữa hai cụm máy chủ; client tự đổi phương thức khi theo chuyển hướng và cụm đích không nhận được body tệp.
Một website có quy tắc chuyển từ HTTP sang HTTPS tại gateway, còn ứng dụng nguồn chuyển ngược về HTTP; trình duyệt lặp lại nhiều lượt chuyển hướng rồi dừng với lỗi.
Dịch vụ chia sẻ đường dẫn tải tệp có tham số chữ ký và thời hạn; sau chuyển hướng đến kho lưu trữ, một thành phần trung gian làm mất tham số truy vấn nên yêu cầu tải bị từ chối.
Client HTTP/1.1 dùng lại kết nối TCP cho nhiều yêu cầu liên tiếp; máy chủ đã đóng kết nối do không hoạt động, khiến yêu cầu kế tiếp đôi khi thất bại ngay trước khi nhận phản hồi.
Một ứng dụng gửi body có kích thước khác giá trị Content-Length trong yêu cầu HTTP/1.1; proxy và máy chủ không thống nhất điểm kết thúc thông điệp nên giao dịch sau trên cùng kết nối bị lỗi.
Máy chủ truyền báo cáo lớn bằng cơ chế chunked của HTTP/1.1; kết nối ngắt giữa chừng và client nhận được dữ liệu chưa đủ nhưng màn hình vẫn báo tải thành công.
Ứng dụng tải video lớn tới API qua kết nối mạng yếu; bước kiểm tra tải lên và phản hồi 100 Continue được proxy và máy chủ xử lý không nhất quán, khiến client chờ lâu trước khi gửi dữ liệu.
Trang phân tích chạy nhiều API đồng thời qua HTTP/2; một luồng phản hồi rất lớn làm client hoặc proxy quá tải, trong khi các luồng còn lại cũng chậm dù không cần cùng dữ liệu.
Trình duyệt giao tiếp với gateway bằng HTTP/2 nhưng gateway chuyển tiếp tới máy chủ HTTP/1.1; khi nhiều yêu cầu đồng thời, giới hạn kết nối ở chặng phía sau làm độ trễ tăng mạnh.
Ứng dụng hỗ trợ HTTP/3 hoạt động tốt trên Wi-Fi nhưng thường chậm lúc kết nối mạng cơ quan chặn UDP; client chuyển qua giao thức khác và thời gian tải ban đầu biến động.
Một ứng dụng di động truy cập API HTTPS sau khi hệ thống thay chứng chỉ máy chủ; kết nối TLS thất bại trước khi có phản hồi HTTP và phần ghi lỗi chung lại hiển thị là lỗi máy chủ.
Máy chủ vừa chuyển sang cụm IP mới nhưng các kết nối và bản ghi DNS được client giữ lại; một số người dùng vẫn gửi yêu cầu đến địa chỉ cũ trong thời gian chuyển đổi.
Ứng dụng gọi dịch vụ giao hàng qua mạng di động; có lần chưa thiết lập được kết nối, có lần đã gửi yêu cầu nhưng đợi phản hồi quá lâu, trong khi hệ thống ghi nhận cả hai dưới một loại timeout.
Thư viện HTTP tự động thử lại yêu cầu POST thanh toán khi kết nối bị ngắt sau khi gửi body; khách hàng nhìn thấy hai giao dịch dù thư viện chỉ báo một lần thử cuối thành công.
Khách đang tải tệp video lớn bằng header Range để tiếp tục phần còn thiếu; máy chủ trả toàn bộ tệp thay vì vùng byte cần thiết nên ứng dụng ghép tệp bị sai kích thước.
Ứng dụng quản lý kho nhận HTTP 200 và header phản hồi trước khi mạng đứt giữa lúc đọc JSON; client ghi giao dịch là thành công dù body phản hồi chưa được nhận đầy đủ.
Máy chủ báo kích thước body không được chấp nhận khi thiết bị tải ảnh quá lớn; ứng dụng khách chỉ thấy yêu cầu tải lên thất bại và lặp lại với cùng một tệp mà không hiểu phản hồi HTTP.
Một dashboard xây dựng trên miền khác gọi API bằng trình duyệt; cùng URL gọi thành công bằng công cụ dòng lệnh nhưng trình duyệt từ chối đọc phản hồi vì các header kiểm soát truy cập khác nguồn.
Ứng dụng thử nghiệm một API REST hỗ trợ cả HTTP/1.1 và HTTP/2; sau khi bật tính năng giao thức mới, một số client cũ chỉ hoạt động khi đi qua proxy và nhận thông điệp khác với mong đợi.
