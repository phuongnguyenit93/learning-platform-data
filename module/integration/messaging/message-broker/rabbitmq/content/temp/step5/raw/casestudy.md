Trong giờ cao điểm, dịch vụ checkout phát sự kiện tạo đơn qua direct exchange nhưng queue của kho luôn trống dù publisher ghi log gửi thành công; nhóm cần truy vết routing key, binding và đường đi của thông điệp.
Nền tảng vận chuyển dùng topic exchange cho sự kiện có routing key nhiều cấp như shipment.vn.hcm.created; một số chi nhánh nhận sự kiện quá rộng, số khác không nhận được thông báo cần thiết sau khi đổi mẫu binding.
Hệ thống bán vé phát thông báo qua fanout exchange cho email, SMS và phân tích; chỉ hai dịch vụ có dữ liệu sau lần triển khai mới dù cả ba consumer đều báo đang hoạt động.
Cổng xử lý hồ sơ phân phối thông điệp theo tiêu chí vùng, loại khách hàng và mức ưu tiên qua headers exchange; một yêu cầu thuộc nhiều tiêu chí bị chuyển nhầm bộ phận sau khi thay đổi thuộc tính binding.
Dịch vụ kiểm kê gửi trực tiếp tới tên queue qua default exchange; sau khi đổi tên queue trong môi trường production, một số thông điệp không đến nơi nhưng phía gửi vẫn không phát hiện lỗi.
Hai ứng dụng kế toán vô tình tạo hai queue khác nhau cùng nhận sự kiện thanh toán từ một exchange; mỗi giao dịch bắt đầu được ghi sổ hai lần dù hệ thống nguồn chỉ phát một sự kiện.
Ứng dụng hỗ trợ trực tuyến tạo queue tạm thời độc quyền cho từng phiên người dùng; khi kết nối RabbitMQ chập chờn, phiên vẫn hiển thị hoạt động nhưng các phản hồi đang chờ biến mất.
Sau khi RabbitMQ khởi động lại, queue lưu đơn hàng vẫn tồn tại nhưng một phần thông điệp trước sự cố đã mất; nhóm cần phân tích toàn bộ thiết lập lưu bền từ publisher đến broker.
Exchange phục vụ sự kiện khuyến mãi biến mất sau lần bảo trì broker, trong khi các queue liên quan vẫn còn; dịch vụ Java tiếp tục gửi mà không nhận được kết quả xử lý mong đợi.
Một ứng dụng Spring AMQP không thể khởi động sau đợt chuyển đổi queue sang quorum; log broker báo lỗi khi ứng dụng khai báo lại queue đã tồn tại với tập tham số khác.
Service A và Service B cùng khai báo một queue nhưng đặt tham số dead-letter khác nhau; bản triển khai thứ hai liên tục bị đóng channel dù cấu hình listener và tên queue đều hợp lệ.
Trong quá trình khởi động, Spring listener cố đăng ký tiêu thụ một queue do hệ thống hạ tầng tạo sẵn; có lúc queue chưa tồn tại, khiến pod khởi động thất bại và khó phục hồi khi tài nguyên xuất hiện muộn.
Ứng dụng giao hàng gửi sự kiện tới exchange bằng routing key chưa được binding nào tiếp nhận; publisher confirm vẫn báo thành công, nhưng không có bản ghi giao hàng nào được tạo.
Hệ thống publisher bật cơ chế trả về thông điệp không định tuyến được; callback đã ghi nhận thông điệp bị trả về nhưng API đặt hàng vẫn trả trạng thái thành công cho khách.
Trong một đợt mất kết nối ngắn, publisher Java hết thời gian chờ publisher confirm và gửi lại cùng một sự kiện; sau đó bên nhận thấy hai thông điệp hợp lệ cho cùng một đơn hàng.
Ứng dụng xuất hóa đơn đợi publisher confirm riêng lẻ cho từng sự kiện; khi lưu lượng tăng lên hàng chục nghìn hóa đơn mỗi phút, độ trễ gửi tăng vọt dù broker và mạng còn dư tài nguyên.
Trong đợt broker chịu áp lực tài nguyên, một số thông điệp nhận publisher nack hoặc không nhận xác nhận đúng hạn; hệ thống bán vé không phân biệt được giao dịch nào cần xử lý lại.
Checkout gửi sự kiện xác nhận đơn trước khi transaction cơ sở dữ liệu hoàn tất; đôi lúc consumer xử lý đơn mà phía checkout sau đó đã rollback vì lỗi thanh toán.
Dịch vụ thanh toán ghi giao dịch vào cơ sở dữ liệu thành công nhưng mất kết nối broker trước khi phát sự kiện; đơn hàng ở dịch vụ khác treo ở trạng thái chờ dù tiền đã được thu.
Sau khi nâng phiên bản DTO của ứng dụng Java, consumer Spring AMQP cũ không đọc được một phần thông điệp JSON từ publisher mới; backlog tăng trong khi những loại sự kiện khác vẫn chạy bình thường.
Hai dịch vụ Java dùng bộ chuyển đổi thông điệp khác nhau; thông điệp mang body JSON nhưng content type và metadata không nhất quán khiến listener từ chối một nhóm sự kiện.
Ứng dụng gửi toàn bộ tệp đính kèm dung lượng lớn trong payload RabbitMQ; vào mùa cao điểm, độ trễ, mức sử dụng RAM và thời gian phục hồi của broker đều tăng mạnh.
Consumer thông báo sử dụng chế độ xác nhận tự động; pod bị dừng giữa lúc gọi nhà cung cấp SMS, và thông điệp tương ứng không xuất hiện lại dù SMS chưa được gửi.
Consumer trừ tồn kho xác nhận thông điệp ngay khi nhận rồi mới lưu kết quả vào cơ sở dữ liệu; một lần lỗi ghi dữ liệu khiến hệ thống đánh dấu đơn đã xử lý nhưng kho thực tế không thay đổi.
Dịch vụ Java xử lý đa luồng và phát acknowledgement trên một channel khác với channel nhận thông điệp; broker đóng channel với lỗi delivery tag không hợp lệ khi lưu lượng tăng.
Một tác vụ tạo báo cáo cần hơn một giờ cho mỗi thông điệp; trong lúc chạy, channel của consumer bị đóng vì không xác nhận kịp, và cùng tác vụ xuất hiện trở lại ở một worker khác.
Queue ảnh xử lý có nhiều consumer nhưng một worker giữ hàng trăm thông điệp đang chờ ACK, trong khi các worker khác rảnh; thời gian hoàn tất tác vụ chênh lệch lớn theo kích thước ảnh.
Nhóm tăng đồng thời số consumer Spring AMQP để giảm backlog, nhưng pool kết nối cơ sở dữ liệu nhanh chóng cạn và tỷ lệ lỗi nghiệp vụ tăng cao hơn trước.
Ba dịch vụ email, analytics và audit cùng tiêu thụ một queue vì muốn nhận tất cả sự kiện đăng ký; mỗi dịch vụ chỉ thấy một phần thông điệp, khiến báo cáo giữa các hệ thống không khớp.
Consumer gọi API đối tác bị lỗi tạm thời và liên tục từ chối rồi đưa lại cùng thông điệp vào queue; CPU broker tăng cao, log lặp vô hạn và các đơn bình thường bị chậm.
Nhà cung cấp vận chuyển có thể lỗi vài phút, nhưng SLA yêu cầu xử lý lại trong vòng một giờ và không gửi yêu cầu vô hạn; đội cần đánh giá hành vi retry đối với các thông điệp có thời hạn nghiệp vụ.
Sau khi đổi tên routing key dùng cho dead-letter exchange, các thông điệp thất bại biến mất khỏi queue chính nhưng không xuất hiện trong queue xử lý lỗi mà đội vận hành đang theo dõi.
Một thông điệp dữ liệu sai luôn khiến listener ném lỗi; nó quay lại queue nhiều lần, chiếm phần lớn công suất consumer và đẩy số thông điệp cần điều tra lên nhanh chóng.
Đội hỗ trợ chuẩn bị phát lại hàng nghìn thông điệp từ dead-letter queue sau khi sửa lỗi; một số giao dịch trong đó có thể đã hoàn thành ở hệ thống đích trước khi bị đánh dấu thất bại.
Consumer thanh toán nhận lại thông điệp sau khi ghi nhận khoản thu nhưng trước khi gửi ACK; hệ thống có nguy cơ ghi nhận thanh toán hai lần khi broker chuyển việc xử lý sang pod khác.
Ứng dụng quản lý điểm thưởng có bốn consumer cùng đọc một queue; sự kiện cộng điểm và hủy điểm của cùng tài khoản hoàn tất sai thứ tự, khiến số dư cuối ngày không khớp lịch sử.
Hệ thống tài khoản phát các sự kiện khóa, mở và cập nhật hồ sơ qua những queue riêng; trong lúc một dịch vụ chậm, màn hình khách hàng hiển thị trạng thái mâu thuẫn giữa các hệ thống.
Giữa hàng triệu thông điệp đồng bộ dữ liệu thông thường, các yêu cầu chống gian lận khẩn cấp bị chờ nhiều phút; nhóm cần xác định chính sách xử lý ưu tiên phù hợp với giới hạn của broker.
Một queue chứa thông điệp giữ chỗ có thời hạn sử dụng ngắn; khi consumer ngừng hoạt động 20 phút, nhiều thông điệp hết hạn trước khi được xử lý nhưng quy trình nghiệp vụ vẫn chờ kết quả.
Hệ thống đặt lịch trì hoãn xử lý một nhóm sự kiện theo thời điểm hết hạn; khi số lượng lịch hẹn tăng cao, các thông điệp không được kích hoạt gần thời điểm dự kiến và độ trễ khác nhau khó giải thích.
Trong đợt flash sale, queue đạt giới hạn chiều dài và bắt đầu loại bỏ thông điệp; một số đơn hàng bị bỏ qua âm thầm trong khi dashboard chỉ cho thấy tốc độ nhận sự kiện vẫn ổn định.
Queue quorum lưu yêu cầu giao dịch có leader trên một node; khi node đó tắt đột ngột, consumer thấy một số thông điệp được giao lại và publisher có những xác nhận chưa rõ kết quả.
Cụm ba node dùng quorum queue mất hai node cùng lúc do sự cố mạng; những node còn sống vẫn phục vụ được kết nối nhưng không thể tiếp tục một số thao tác trên queue quan trọng.
Đội triển khai chuyển dần một queue nghiệp vụ từ classic sang quorum; các phiên bản ứng dụng còn chạy đồng thời khai báo loại queue khác nhau và gây lỗi trong quá trình nâng cấp.
Cụm RabbitMQ trải trên ba vùng mạng có độ trễ khác nhau; sau khi leader của quorum queue chuyển sang vùng xa nhất, thời gian xác nhận publish tăng mạnh dù số message mỗi giây không đổi.
Trong lúc nâng cấp lần lượt các node RabbitMQ, một số worker Java bị ngắt kết nối và số thông điệp chưa ACK tăng; đội phải đánh giá khả năng tiếp tục xử lý đơn trong suốt quá trình bảo trì.
Broker kích hoạt cảnh báo bộ nhớ giữa giờ cao điểm; publisher Spring AMQP đột nhiên bị chặn gửi, khiến request HTTP chờ lâu và lan lỗi sang dịch vụ đặt hàng.
Dung lượng đĩa trống của node RabbitMQ giảm dưới ngưỡng vận hành; hệ thống ngừng nhận lưu lượng mới dù CPU thấp và queue chưa đạt giới hạn số lượng thông điệp.
Dịch vụ xuất hóa đơn xử lý chậm hơn tốc độ phát sự kiện trong nhiều giờ, làm queue tăng tới vài triệu thông điệp; tài nguyên broker tiếp tục leo thang và doanh nghiệp cần đánh giá giới hạn tải an toàn.
Ứng dụng SaaS tạo một queue và nhiều binding cho từng khách hàng mới; sau khi tăng lên hàng chục nghìn tenant, thời gian khởi động broker và mức tiêu thụ bộ nhớ tăng bất thường.
Dịch vụ Java mở thêm connection hoặc channel RabbitMQ cho mỗi request và không giải phóng ổn định; sau vài giờ hoạt động, broker chạm giới hạn tài nguyên dù số request không tăng.
Chứng chỉ TLS ở một node RabbitMQ hết hạn sau lần luân chuyển; một nhóm publisher kết nối được qua node khác nhưng các consumer bắt đầu lỗi bắt tay bảo mật theo từng đợt.
Ứng dụng đã chuyển sang virtual host riêng nhưng tài khoản dịch vụ chỉ có quyền ở virtual host cũ; kết nối thành công ở vài môi trường nhưng việc khai báo queue và binding thất bại ở production.
Nhóm vận hành giới hạn quyền configure, write và read cho từng vai trò; sau khi áp dụng chính sách, consumer đọc được queue nhưng chức năng tạo topology tự động của Spring AMQP bị từ chối.
Doanh nghiệp xoay vòng mật khẩu tài khoản RabbitMQ trong giờ làm việc; một số kết nối cũ còn tồn tại, trong khi phiên kết nối mới từ các pod Java bị từ chối và năng lực tiêu thụ giảm dần.
Kết nối AMQP đi qua load balancer có cơ chế cắt kết nối nhàn rỗi; cứ sau một khoảng thời gian ít sự kiện, consumer phải kết nối lại và phát sinh các bản ghi xử lý trùng.
Sau khi broker chuyển node trong cụm, ứng dụng Spring AMQP vẫn báo tiến trình khỏe mạnh nhưng listener không tiếp tục nhận thông điệp; backlog tăng mà cảnh báo ứng dụng không kích hoạt.
Hệ thống giám sát chỉ nhìn số messages ready nên báo queue gần như trống; thực tế nhiều thông điệp nằm ở trạng thái unacknowledged trong các consumer bị treo và không có kết quả nghiệp vụ mới.
Khi đơn hàng đi qua Java publisher, RabbitMQ và ba microservice, một sự kiện bị thất lạc giữa các lần retry; log không có correlation ID chung nên đội trực vận hành không tìm được điểm xử lý cuối cùng.
Trong kế hoạch phục hồi thảm họa, đội thử khôi phục cấu hình exchange, queue và binding sang cụm RabbitMQ mới; hệ thống kết nối được nhưng các thông điệp đang chờ trước sự cố không xuất hiện.
Ứng dụng Java dùng mô hình request/reply qua RabbitMQ để hỏi trạng thái giao dịch; dưới tải cao, reply đến sau timeout và các queue hoặc consumer nhận phản hồi tồn tại lâu hơn dự kiến.
Dashboard ghi nhận publisher confirm thành công cho sự kiện hoàn tiền, nhưng consumer liên tục thất bại khi gọi dịch vụ ngân hàng; bộ phận hỗ trợ hiểu nhầm xác nhận của broker là bằng chứng hoàn tiền đã hoàn tất.
