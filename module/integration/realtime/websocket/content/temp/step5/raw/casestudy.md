Một ứng dụng giao dịch chứng khoán mở WebSocket để nhận giá trực tiếp; trình duyệt gửi yêu cầu bắt tay nhưng gateway trả HTTP 200 thay vì chuyển giao thức, khiến kết nối không bao giờ hình thành.
Nền tảng chăm sóc khách hàng triển khai WebSocket sau reverse proxy; kết nối hoạt động khi gọi trực tiếp máy chủ nhưng yêu cầu qua proxy thất bại do các header Upgrade và Connection không được chuyển tiếp nhất quán.
Nhóm phát triển tích hợp WebSocket vào ứng dụng di động; máy chủ từ chối handshake vì giá trị Sec-WebSocket-Key bị client tùy biến sai, trong khi cùng endpoint hoạt động với trình duyệt.
Một hệ thống báo giá di chuyển từ ws sang wss; ứng dụng được mở bằng HTTPS nhưng vẫn cố kết nối WebSocket không mã hóa và chỉ một số môi trường phát sinh lỗi ngay ở trình duyệt.
Ứng dụng doanh nghiệp dùng chứng chỉ TLS mới cho cổng wss; trình duyệt kết nối được còn thiết bị di động cũ thất bại trước handshake WebSocket do chuỗi chứng chỉ không được tin cậy.
Gateway phục vụ đồng thời HTTP/1.1 và HTTP/2; một client cố dùng cơ chế Upgrade kiểu HTTP/1.1 trên kết nối HTTP/2 và kết nối WebSocket bị từ chối dù đường dẫn dịch vụ vẫn đúng.
Dịch vụ dữ liệu thị trường thương lượng subprotocol trong handshake; phiên bản client yêu cầu một giao thức ứng dụng cụ thể nhưng máy chủ trả giao thức khác khiến các bản tin sau kết nối không thể giải mã.
Ứng dụng chat nội bộ mở nhiều tab trình duyệt tới cùng endpoint; chỉ một số tab xác thực được vì cookie phiên không được gửi trong từng ngữ cảnh miền phụ như kỳ vọng.
Một trang web bên thứ ba cố mở WebSocket bằng trình duyệt người dùng đang đăng nhập hệ thống quản trị; máy chủ chấp nhận kết nối chỉ dựa vào cookie mà không phân biệt nguồn trang khởi tạo.
Cổng tư vấn trực tuyến kiểm tra đăng nhập ở handshake nhưng không xét quyền trong từng phòng chat; người dùng thay mã phòng trong thông điệp và xem được cuộc trò chuyện của khách khác.
Nền tảng học trực tuyến phát token truy cập có thời hạn ngắn; WebSocket được thiết lập khi token hợp lệ nhưng vẫn tồn tại lâu sau khi tài khoản người học bị khóa.
Ứng dụng tư vấn sức khỏe dùng STOMP CONNECT để gửi thông tin đăng nhập sau khi WebSocket đã mở; bộ lọc bảo mật hiện chỉ kiểm tra yêu cầu HTTP handshake nên phiên STOMP chưa xác thực vẫn đăng ký nhận bản tin.
Dịch vụ hỗ trợ khách hàng trả lỗi 401 tại handshake cho token hết hạn; client chỉ ghi nhận sự kiện kết nối thất bại và không phân biệt được trường hợp bị từ chối xác thực với lỗi mạng.
Ứng dụng bảng điều khiển không giới hạn tốc độ mở kết nối; một client bị lỗi liên tục handshake trong vòng lặp, khiến số phiên mới làm cạn tài nguyên máy chủ.
Trang chơi cờ gửi trạng thái bàn cờ bằng text frame WebSocket nhưng client di động kỳ vọng binary frame; cùng nội dung dữ liệu lại được đọc khác kiểu và cập nhật ván đấu thất bại.
Nền tảng video học trực tuyến truyền ảnh chụp bảng viết qua WebSocket; thông điệp lớn được phân thành nhiều frame và thư viện xử lý từng frame như một thông điệp độc lập khiến dữ liệu ảnh bị hỏng.
Ứng dụng đo chất lượng không khí gửi ký tự Unicode trong text message; một thiết bị truyền payload UTF-8 sai định dạng khiến kết nối bị đóng giữa phiên đo.
Hệ thống thu thập cảm biến cho phép mỗi WebSocket message mang dữ liệu rất lớn; một thiết bị lỗi liên tục gửi payload nhiều megabyte và làm bộ nhớ máy chủ tăng bất thường.
Một ứng dụng trình duyệt tự tạo frame client-to-server thay vì dùng thư viện chuẩn; máy chủ đóng kết nối do frame không tuân thủ yêu cầu masking của giao thức.
Ứng dụng giám sát thiết bị bật WebSocket compression trên kết nối lâu dài; mức sử dụng CPU và bộ nhớ tăng mạnh khi có nhiều thiết bị cùng gửi các bản tin gần giống nhau.
Khách hàng tải bảng giá realtime qua WebSocket nhưng đường truyền chậm; máy chủ tiếp tục gửi nhanh hơn khả năng nhận khiến vùng đệm thông điệp của phiên tăng không kiểm soát.
Trong hệ thống đặt vé, hai thông điệp đặt và hủy cùng ghế được gửi liên tiếp qua một WebSocket; phía server đẩy sang các worker chạy song song khiến trạng thái ghế cuối cùng bị đảo ngược.
Ứng dụng đặt lịch dùng một kết nối WebSocket cho thông báo và cập nhật lịch; bản tin thông báo lớn chiếm thời gian truyền khiến cập nhật lịch quan trọng đến client chậm dù cùng phiên vẫn hoạt động.
Một máy chủ WebSocket gửi Ping đều đặn nhưng client trên mạng di động không phản hồi Pong sau khi ứng dụng chuyển nền; server không biết nên giữ hay đóng session đang treo.
Ứng dụng chat dựa vào việc còn socket để hiển thị người dùng trực tuyến; máy khách bị mất mạng đột ngột mà không gửi Close frame nên danh sách hiện diện vẫn báo trực tuyến nhiều phút.
Nhân viên đóng tab chat và client gửi mã đóng WebSocket bình thường; máy chủ lại xử lý mọi kiểu đóng kết nối như lỗi hệ thống nên hệ thống giám sát liên tục cảnh báo nhầm.
Trong quá trình phân tích sự cố, nhóm vận hành thấy mã đóng 1006 ở phía trình duyệt; đội server tìm một Close frame mang mã này trên mạng nhưng không tìm thấy chứng cứ tương ứng.
Ứng dụng đấu giá cần đóng phiên khi quy trình kết thúc; server gửi Close frame nhưng vẫn tiếp tục phát giá trong lúc hai phía chưa hoàn tất bắt tay đóng, khiến client nhận trạng thái khó dự đoán.
Ứng dụng STOMP cho bảng thông báo đặt nhầm destination đăng ký; các client kết nối WebSocket thành công nhưng không nhận được dữ liệu từ nhánh /topic dự kiến.
Một hệ thống nhắn tin dùng Spring WebSocket và STOMP; thông điệp gửi tới /app/submit hoạt động trên môi trường thử nhưng gateway production chỉ cho phép một tập destination khác nên server không xử lý yêu cầu.
Nền tảng tư vấn trực tuyến cần gửi kết quả riêng cho từng người dùng qua STOMP; nhầm lẫn giữa /topic công khai và /user destination khiến thông báo cá nhân xuất hiện ở màn hình người khác.
Ứng dụng cộng tác tài liệu cho phép mọi client STOMP SUBSCRIBE đến một destination theo mã dự án; thành viên dự án A thay mã đăng ký và nhận được sự kiện sửa tài liệu của dự án B.
Một hệ thống sử dụng STOMP broker relay để chuyển thông điệp giữa nhiều instance Spring; khi broker ngoài tạm mất kết nối, WebSocket vẫn mở nhưng các bản tin đăng ký mới không còn được phân phối.
Nhóm phát triển kết nối nhiều client STOMP sử dụng heartbeat ở chu kỳ khác nhau; các kết nối bị đóng nhầm trong mạng có độ trễ cao dù bản tin nghiệp vụ vẫn truyền bình thường.
Ứng dụng trung tâm thông báo dùng STOMP ACK cho các thông điệp quan trọng; client hiển thị thông báo rồi thoát trước khi xác nhận nên cùng thông báo xuất hiện lại sau đăng nhập.
Hệ thống ghi nhận sự kiện hỗ trợ khách qua STOMP; client gửi ACK trước khi lưu dữ liệu cục bộ, ứng dụng bị đóng ngay sau đó và một số sự kiện không còn được tìm thấy.
Một client STOMP gửi nhiều thông điệp kèm receipt để biết broker đã nhận; ứng dụng lại coi receipt là bằng chứng dịch vụ nghiệp vụ đã xử lý xong nên hiển thị kết quả quá sớm.
Nhóm phát triển truyền JSON trong STOMP MESSAGE nhưng thiếu khai báo kiểu nội dung nhất quán; Spring message converter nhận dữ liệu thành chuỗi trong một môi trường và đối tượng trong môi trường khác.
Một ứng dụng dùng STOMP transaction để gom thao tác gửi nhiều bản tin; người dùng tin rằng transaction này cũng bao gồm thao tác ghi cơ sở dữ liệu riêng, nhưng hai hệ thống lại có trạng thái khác nhau sau sự cố.
Nền tảng quản lý lớp học tạo một STOMP subscription mới mỗi khi người học chuyển màn hình; subscription cũ không được hủy, khiến cùng thông báo đến nhiều lần và bộ nhớ phiên tăng dần.
Hệ thống trò chuyện nhóm triển khai Spring WebSocket với nhiều session trên cùng tài khoản; khi gửi sự kiện trực tiếp cho người dùng, có thiết bị nhận hai lần còn thiết bị khác không nhận.
Ứng dụng trò chơi nhiều người giữ thông tin phòng chơi trong bộ nhớ của từng node; sau khi load balancer chuyển kết nối mới sang node khác, người chơi nhìn thấy trạng thái phòng không khớp.
Phần mềm quản lý vận tải mở rộng từ một lên bốn node WebSocket; sự kiện vị trí gửi vào node A không đến được client đang kết nối node C dù cùng theo dõi một xe.
Hệ thống phân phối thông báo giả định client luôn kết nối lại cùng node; khi hết hạn phiên sticky tại load balancer, danh sách subscription giữ tại node cũ không được khôi phục.
Một hệ thống chat nâng cấp rolling các instance WebSocket; khi node bị rút khỏi cụm để bảo trì, hàng nghìn session bị đóng đồng thời khiến client cùng reconnect và tạo đỉnh tải lớn.
Ứng dụng báo giá realtime có hàng chục nghìn kết nối nhàn rỗi; load balancer đóng các kết nối lâu không có dữ liệu sớm hơn thời gian chờ mà backend sử dụng, gây mất kết nối không dự kiến.
Nền tảng thương mại điện tử phát một sự kiện giá sản phẩm tới các node WebSocket qua message broker; có thời điểm cùng client nhận giá hai lần sau khi broker hoặc publisher thử gửi lại.
Ứng dụng chat lưu lịch sử vào cơ sở dữ liệu rồi phát realtime; khi ghi thành công nhưng tiến trình chết trước lúc gửi WebSocket, người nhận chỉ thấy tin sau khi tải lại trang.
Người dùng gửi tin nhắn qua WebSocket rồi mất mạng trước khi nhận xác nhận; ứng dụng tự gửi lại sau reconnect và người nhận nhìn thấy hai tin nhắn cùng nội dung.
Một bảng điều khiển giao dịch mất WebSocket trong 30 giây; sau reconnect, client chỉ nhận các sự kiện mới mà thiếu mọi biến động đã xảy ra trong thời gian ngắt.
Ứng dụng đặt món theo dõi trạng thái đơn qua WebSocket; trong lúc chuyển từ Wi-Fi sang 4G, bản tin đang giao bị nhận trước bản tin đang chuẩn bị, khiến thanh tiến trình quay ngược.
Nền tảng chứng khoán gửi số thứ tự cập nhật trong từng message; khi reconnect, client nhận ảnh chụp trạng thái mới cùng những bản tin cũ còn trong hàng đợi khiến giá hiển thị lùi về trước.
Ứng dụng chat mobile bật reconnect tức thời mỗi khi mất kết nối; một lần mất mạng diện rộng khiến hàng chục nghìn thiết bị liên tục kết nối lại cùng lúc ngay khi mạng hồi phục.
Một thiết bị IoT nằm ngoài vùng phủ sóng nhiều giờ; token đăng nhập hết hạn trước khi WebSocket reconnect, nhưng client vẫn thử lại bằng token cũ vô hạn thay vì báo rõ trạng thái phiên.
Trình duyệt mở hai phiên WebSocket sau khi mạng chập chờn vì phiên cũ chưa được đóng; cùng người dùng nhận bản tin từ cả hai kết nối và số lượng người trực tuyến bị đếm trùng.
Một hệ thống báo động dùng kết nối WebSocket liên tục; khi người dùng khóa màn hình di động, hệ điều hành hạn chế hoạt động nền làm thông báo quan trọng đến muộn mà máy chủ vẫn tưởng phiên còn hoạt động.
Ứng dụng đào tạo có hàng nghìn học viên cùng tương tác qua WebSocket; nhiều client chậm đọc dữ liệu khiến hàng đợi gửi tăng và một số node hết bộ nhớ dù CPU chưa quá tải.
Máy chủ WebSocket Spring dùng callback xử lý message để gọi dịch vụ thanh toán bên ngoài; dịch vụ phản hồi chậm làm nhiều session cùng chờ và thời gian gửi nhận tăng đột ngột.
Ứng dụng khảo sát phát câu hỏi mới tới toàn bộ người tham gia qua STOMP; lớp học đông người khiến lượng message đồng loạt bùng lên và một số session bị giới hạn tốc độ gửi.
Nhóm vận hành đo số kết nối WebSocket còn mở nhưng không theo dõi tốc độ message, độ dài hàng đợi và mã Close; dashboard báo hệ thống khỏe dù người dùng liên tục bị trễ cập nhật.
Khi kiểm thử mạng di động với mất gói và dao động độ trễ, ứng dụng cộng tác vẫn duy trì socket ở một số lần thử nhưng tin nhắn không xuất hiện trên giao diện trong khoảng thời gian dài.
Trong kiểm thử đồng thời, hai người sửa cùng tài liệu qua WebSocket; cả hai nhận thông báo đã lưu nhưng dữ liệu cuối trong máy chủ chỉ chứa thay đổi của một người.
Ứng dụng theo dõi xe cần xử lý cả cập nhật vị trí tần suất cao và lệnh dừng xe quan trọng; hàng đợi một kết nối đầy bởi dữ liệu vị trí làm lệnh điều khiển đến muộn.
Đội hỗ trợ điều tra việc lộ thông tin phòng chat; log WebSocket ghi nguyên nội dung message và token xác thực trong nhiều ngày, khiến người không liên quan có thể xem dữ liệu nhạy cảm.
Ứng dụng thương mại điện tử phân quyền nhận tin theo người bán; phiên WebSocket được xác thực hợp lệ nhưng thông điệp gửi tới destination do client lựa chọn lại chứa đơn hàng thuộc người bán khác.
Một hệ thống vận hành triển khai lại backend trong khi client giữ các session WebSocket lâu dài; phiên bản message mới thay tên trường bắt buộc và client cũ không thể xử lý bản tin sau nâng cấp.
Trang web tương tác theo thời gian thực kết nối ổn định trong mạng nội bộ nhưng thất bại ở mạng doanh nghiệp dùng proxy lọc lưu lượng; phần giao diện không phân biệt được lỗi handshake, lỗi TLS và đóng phiên sau kết nối.
