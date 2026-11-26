Một ứng dụng bán vé gửi sự kiện xác nhận đơn hàng tới broker; kết nối mạng đứt sau khi gửi nhưng trước khi producer nhận phản hồi, khiến hệ thống không biết bản tin đã được lưu hay chưa.
Dịch vụ thanh toán trả kết quả thành công cho người dùng ngay sau khi đưa thông điệp vào bộ đệm producer; khi tiến trình bị dừng đột ngột, một số giao dịch không xuất hiện ở hệ thống kế toán.
Trong đợt mở bán, broker phản hồi chậm và producer liên tục thử gửi lại; hàng đợi chờ gửi trong ứng dụng tăng nhanh đến mức các yêu cầu đặt hàng mới bị hết thời gian chờ.
Một cửa hàng phát thông điệp thay đổi tồn kho từ nhiều instance producer; các cập nhật của cùng sản phẩm đến broker với thứ tự khác lúc nhân viên thao tác.
Ứng dụng bảo hiểm gửi nhiều bản tin cùng lúc rồi thử lại các lần gửi thất bại; thông điệp cập nhật trạng thái đến nơi nhận trước thông điệp tạo hồ sơ ban đầu.
Nhóm vận hành nâng số partition của topic xử lý đơn hàng; cùng một mã đơn có bản tin mới được đặt ở partition khác, khiến consumer quan sát thứ tự chuyển trạng thái không còn liên tục.
Cụm broker chỉ có một bản sao chứa dữ liệu mới nhất khi máy chủ dẫn đầu gặp sự cố; các ứng dụng vẫn gửi thành công trước đó nhưng vài sự kiện không có mặt sau khi khôi phục.
Hệ thống truyền sự kiện giao nhận vẫn cho producer ghi khi số replica đang đồng bộ xuống thấp; sau sự cố mất thêm một broker, đội vận hành không xác định được phạm vi dữ liệu còn bền vững.
Một broker hết dung lượng ổ đĩa lúc nhận thông điệp mới; producer nhận timeout xen kẽ với xác nhận thành công khiến số lượng sự kiện vận chuyển ở đích không khớp số lệnh đã phát.
Doanh nghiệp gửi thông điệp phục vụ tính lương qua hàng đợi không được cấu hình tồn tại qua lần khởi động lại; sau bảo trì broker, một phần yêu cầu đã chấp nhận không còn được xử lý.
API tạo hóa đơn ghi nhận yêu cầu đã nhận nhưng chưa nhận được xác nhận publisher confirm từ broker; đợt khởi động lại ứng dụng làm trạng thái hóa đơn và sự kiện phát đi không thống nhất.
Một cổng tích hợp thay đổi cấu hình ghi nhận thông điệp để giảm độ trễ; khi broker mất máy giữa quá trình sao chép, hệ thống phát hiện mức bảo đảm lưu bền thấp hơn nhu cầu kiểm toán.
Dịch vụ gửi email tiêu thụ thông điệp rồi xác nhận acknowledgement trước khi gọi nhà cung cấp; nếu nhà cung cấp trả lỗi, thông điệp không quay lại và người dùng không nhận được thư.
Consumer cập nhật thành công trạng thái giao dịch trong cơ sở dữ liệu nhưng mất kết nối trước khi gửi acknowledgement; bản tin được giao lại và trạng thái tiền thưởng bị cập nhật hai lần.
Nhóm phát triển dùng consumer tự động xác nhận khi nhận bản tin, sau đó đưa công việc vào hàng đợi xử lý nội bộ; ứng dụng chết khi công việc còn nằm trong bộ nhớ và dữ liệu bị thiếu ở đích.
Một consumer gọi API đối tác trong vài phút cho mỗi yêu cầu; trong lúc không gửi tín hiệu hoạt động phù hợp, broker hoặc consumer group cho rằng nó đã ngừng hoạt động và giao công việc cho instance khác.
Dịch vụ xử lý nhiều thông điệp song song trên một consumer và xác nhận theo nhóm; một công việc cuối lô thất bại trong khi các công việc trước đã tạo tác động nghiệp vụ, làm việc xử lý lại khó phân biệt.
Một consumer nhận hai thông điệp về cùng một tài khoản và xử lý bằng hai luồng độc lập; cả hai đều đọc số dư cũ rồi ghi kết quả mới khiến số dư cuối không phản ánh đủ giao dịch.
Hệ thống chăm sóc khách hàng ghi acknowledgement ngay sau khi ghi yêu cầu vào cache tạm; cache bị xóa khi triển khai lại nên yêu cầu đã được báo xử lý nhưng không còn tìm thấy.
Ứng dụng vận tải dùng lại một kết nối broker cho nhiều tác vụ; sau khi kết nối đứt và được tạo lại, mã xác nhận cũ không còn tương ứng với các bản tin trên kết nối mới.
Nhóm kế toán xử lý thông điệp hoàn tiền với cơ chế phát lại khi consumer lỗi; một lần hoàn tiền đã thành công ở cổng thanh toán nhưng sự kiện được xử lý thêm lần nữa sau khi ứng dụng khởi động lại.
API gateway và dịch vụ thanh toán tự tạo mã yêu cầu riêng cho cùng một lệnh chuyển tiền; cùng thao tác do người dùng gửi lại được xem thành hai giao dịch độc lập ở hệ thống nhận.
Một hệ thống dùng mã idempotency của khách hàng để chặn tạo đơn trùng; khách hàng cố tình gửi cùng mã với nội dung giỏ hàng khác và hai ứng dụng xử lý đưa ra kết quả không nhất quán.
Trung tâm bán vé chỉ lưu khóa chống xử lý trùng trong vài giờ, trong khi broker có thể giao lại thông điệp sau nhiều ngày; một sự kiện cũ quay lại làm phát sinh vé thứ hai.
Dịch vụ cộng điểm nhận hai thông điệp khác mã kỹ thuật nhưng cùng đại diện cho một lần thanh toán; hệ thống chống trùng dựa vào mã thông điệp không phát hiện được tác động nghiệp vụ lặp.
Một ứng dụng giao nhận xử lý việc đặt lại trạng thái thành đã giao tương đối an toàn, nhưng khi nhận lại thông điệp cộng thêm số kiện vận chuyển thì tổng kiện bị tăng sai.
Nhóm quản lý đơn hàng triển khai nhiều consumer cùng lưu dấu đã xử lý vào một bảng; hai instance nhận bản tin trùng gần như đồng thời và đều tạo tác động trước khi một bản ghi dấu thành công.
Một tiến trình đọc sự kiện từ broker và ghi sang hệ thống tìm kiếm; sau khi ghi xong, tiến trình chết trước lúc lưu offset khiến cùng tài liệu được tạo thêm bản sao trong chỉ mục.
Dịch vụ cập nhật điểm thưởng xử lý xong thông điệp nhưng lưu offset trước khi giao dịch cơ sở dữ liệu được xác nhận; sự cố mất điện khiến broker và số dư thưởng không còn khớp.
Một hệ thống luân chuyển hồ sơ nhận một thông điệp JSON không thể giải mã tại đầu partition; mỗi lần consumer khởi động lại đều dừng tại cùng offset và các hồ sơ hợp lệ phía sau bị chậm.
Ứng dụng xử lý hợp đồng thử lại vô hạn với bản tin thiếu trường bắt buộc; số lượng lần thử tăng nhưng nội dung thông điệp không đổi và các hợp đồng mới không được xử lý.
Dịch vụ gửi thông báo nhận lỗi tạm thời từ nhà cung cấp SMS; hàng nghìn consumer thử lại tức thì khiến đối tác giới hạn truy cập và thời gian phục hồi kéo dài.
Hệ thống định giá bảo hiểm xử lý chung lỗi mạng tạm thời và lỗi quy tắc nghiệp vụ vĩnh viễn; cả hai được đưa vào cùng chu kỳ retry, làm các hồ sơ sai dữ liệu chiếm hết tài nguyên.
Một hàng đợi xử lý giao dịch sử dụng các khoảng chờ retry ngày càng dài; thông điệp quan trọng có thể đến sau thời hạn hiệu lực của đơn hàng mà phía nhận vẫn cố thực hiện.
Ứng dụng đơn hàng yêu cầu cập nhật trạng thái theo thứ tự; bản tin chuyển sang đang giao bị retry trong hàng đợi riêng, còn bản tin đã giao xử lý trước và màn hình quay ngược khi lần retry đến.
Hệ thống thu tiền giới hạn mỗi thông điệp được thử một số lần; một sự cố ngắn của nhà cung cấp khiến nhiều yêu cầu hợp lệ bị đưa sang hàng đợi lỗi ngay trước khi nhà cung cấp hoạt động lại.
Nhóm hỗ trợ đưa bản tin lỗi sang dead-letter queue nhưng không kèm lý do và lịch sử số lần xử lý; khi điều tra sự cố, họ không biết nên phân biệt lỗi dữ liệu với lỗi hệ thống thế nào.
Một dead-letter queue nhận cả sự kiện hóa đơn và thông tin cá nhân nhạy cảm; đội hỗ trợ kỹ thuật có quyền xem nguyên payload dù chỉ cần đọc dấu vết và mã lỗi.
Sau khi khắc phục lỗi giải mã, kỹ sư chuyển toàn bộ bản tin từ dead-letter queue về luồng chính; một số bản tin trước đó đã tạo tác động thành công nên số liệu doanh thu bị cộng trùng.
Đội vận hành theo dõi trạng thái consumer vẫn chạy nhưng không cảnh báo khi dead-letter queue tăng liên tục; báo cáo ngày hôm sau thiếu hàng nghìn giao dịch dù không có tiến trình nào báo lỗi.
Một hệ thống phân loại thư điện tử đánh dấu bản tin hết hạn sau hai giờ; dịch vụ nhận bị ngừng hoạt động qua đêm và những thư quan trọng biến mất trước khi được gửi.
Ứng dụng thanh toán chuyển thông điệp không xử lý được sang hàng đợi lỗi nhưng xóa nó khỏi hàng đợi gốc; khi người dùng hỏi về khoản thanh toán, hệ thống nghiệp vụ vẫn hiển thị trạng thái đang chờ vô hạn.
Hệ thống đặt vé có hàng đợi lỗi riêng cho từng đối tác; sau khi áp dụng quy trình phát lại chung, một sự kiện sai định dạng của đối tác A bị đưa vào bộ xử lý của đối tác B.
Nhà bán lẻ gửi yêu cầu đặt hàng tới broker ngay sau khi lưu đơn vào cơ sở dữ liệu; tiến trình dừng giữa hai thao tác khiến đơn đã có trong hệ thống bán hàng nhưng kho chưa nhận được yêu cầu.
Một dịch vụ thanh toán phát thông điệp thành công trước khi transaction cập nhật cơ sở dữ liệu được commit; giao dịch bị rollback nhưng hệ thống giao vận đã nhận sự kiện đã thanh toán.
Nhóm phát triển ghi dòng dữ liệu nghiệp vụ và dòng transactional outbox trong hai giao dịch khác nhau; lần ghi thứ hai thất bại khiến chỉ một phía được lưu thành công.
Một publisher của transactional outbox gửi thông điệp tới broker rồi chết trước khi đánh dấu bản ghi đã phát; khi chạy lại, cùng thông điệp được gửi thêm lần nữa tới hệ thống bên nhận.
Bảng outbox của một hệ thống thương mại điện tử tăng hàng triệu bản ghi trong giờ cao điểm; tiến trình phát sự kiện không theo kịp tốc độ ghi dù API tạo đơn vẫn trả thành công.
Một tác vụ dọn dẹp outbox xóa các bản ghi quá cũ dựa vào thời điểm tạo; sau khi broker gián đoạn nhiều giờ, một số sự kiện chưa phát đã bị xóa trước khi tiến trình gửi hoạt động lại.
Ứng dụng gửi thay đổi trạng thái đơn hàng thông qua nhiều worker đọc outbox song song; bản tin trạng thái mới của cùng đơn đến broker trước bản tin cũ do các worker hoàn thành khác nhau.
Đội dữ liệu đọc outbox bằng cơ chế CDC nhưng kết nối ngừng hoạt động lâu hơn thời gian giữ nhật ký thay đổi của cơ sở dữ liệu; các đơn phát sinh trong khoảng gián đoạn không được chuyển sang broker.
Trong một hệ thống nhiều tenant, relay outbox dùng cùng một khóa định tuyến cho mọi khách hàng; khi tải tăng, một partition bị nghẽn và sự kiện của tenant nhỏ bị trễ theo khách hàng lớn.
Dịch vụ hạch toán bật cơ chế xử lý đúng một lần bên trong hệ thống streaming; sau khi gọi API ngân hàng ngoài giao dịch streaming, ứng dụng chết và cùng lệnh chuyển tiền được gọi lại.
Một doanh nghiệp dùng giao dịch tại cơ sở dữ liệu để lưu đơn hàng nhưng cho rằng acknowledgement từ broker cũng nằm trong transaction đó; khi transaction database rollback, offset vẫn tiến và sự kiện biến mất khỏi luồng xử lý.
Nền tảng đặt phòng ghi thanh toán, giữ phòng và phát sự kiện sang ba hệ thống riêng; một hệ thống thất bại sau khi hai hệ thống trước đã xác nhận, khiến khách đã bị trừ tiền nhưng không có phòng.
Quy trình hoàn tiền cho khách sau khi đơn hàng bị hủy yêu cầu nhiều dịch vụ phối hợp; tác vụ bù trừ ở cổng thanh toán thất bại tạm thời trong khi kho đã trả hàng về số lượng có thể bán.
Đơn hàng bị khách hủy nhưng thông điệp giao hàng vẫn nằm trong hàng đợi retry và đến dịch vụ vận chuyển sau vài giờ; tài xế nhận yêu cầu cho một đơn không còn hiệu lực.
Dịch vụ quản lý tồn kho phát một sự kiện xuất hàng khi đã xác nhận đơn; sau khi thông điệp bị xử lý lại, lượng tồn bị trừ hai lần và kế toán phát hiện lệch khi đối soát cuối ngày.
Một nền tảng cho vay nhận bản tin phê duyệt và từ chối từ hai bước kiểm tra độc lập; hệ thống xử lý bản tin đến sau như quyết định cuối cùng dù yêu cầu đã hoàn tất trước đó.
Ứng dụng khách phát các cập nhật địa chỉ giao hàng từ hai phiên đăng nhập; thông điệp cũ đến chậm sau bản sửa cuối và ghi đè địa chỉ mới đã xác nhận với người mua.
Nhóm logistics bổ sung consumer thứ hai vào cùng luồng sự kiện đơn hàng; tốc độ tăng nhưng các thông điệp của một vận đơn bị xử lý ở hai worker khác nhau và trạng thái cuối không nhất quán.
Một hệ thống nhận bản tin từ hai topic vận chuyển và thanh toán rồi yêu cầu so sánh trạng thái; mỗi topic giữ đúng thứ tự riêng nhưng thứ tự tổng thể giữa hai nguồn không xác định.
Trong đợt chuyển vùng dự phòng, nhóm vận hành phục hồi broker từ bản sao lưu và cơ sở dữ liệu từ thời điểm khác; một số sự kiện đã có tác động ở cơ sở dữ liệu nhưng xuất hiện lại trong hàng đợi.
Ứng dụng đa vùng chuyển producer sang broker dự phòng sau sự cố mạng; một số bản tin còn chờ xác nhận trên vùng chính rồi tiếp tục xuất hiện khi kết nối hồi phục, gây trùng tại vùng nhận.
Một consumer group mất kết nối lâu hơn thời gian lưu giữ message; khi hoạt động trở lại, các offset cũ không còn dữ liệu tương ứng và báo cáo giao dịch bị thiếu theo khoảng thời gian.
Nhóm xử lý đơn hàng có tốc độ tiêu thụ chậm hơn producer vào giờ cao điểm; hàng đợi tích lũy hàng triệu thông điệp và khách nhận xác nhận giao hàng sau khi đơn đã bị hủy.
Nhân viên vận hành triển khai bản cập nhật consumer khiến nhiều instance restart cùng lúc; việc giành lại phân vùng và khởi tạo tài nguyên liên tục làm thông điệp bị thử xử lý lại nhiều hơn bình thường.
Một dịch vụ gửi tin nhắn xử lý nhiều lần retry qua các tầng gateway, broker và consumer; mỗi tầng ghi số lần thử riêng nên rất khó xác định tổng số lần khách thực sự được gửi SMS.
Ứng dụng ngân hàng phát hiện một khoản chuyển tiền bị ghi hai lần nhưng log producer, broker và consumer dùng mã tương quan khác nhau; đội điều tra không nối được các lần giao và xác nhận.
Trong hệ thống thanh toán có giám sát producer throughput và độ trễ consumer, nhưng thiếu số liệu thông điệp đã ack, retry và vào DLQ; dashboard vẫn báo khỏe trong khi nhiều lệnh không tới đích.
Một nhóm phát triển thử nghiệm lỗi mạng ngẫu nhiên giữa producer và broker; khi đưa vào môi trường có giao dịch thật, họ phát hiện client coi timeout là thất bại chắc chắn và tự phát lệnh nghiệp vụ mới.
Hệ thống tích hợp bảo hiểm nâng cấp định dạng sự kiện giữa producer và consumer; consumer cũ không đọc được message mới và đẩy chúng vào DLQ dù dữ liệu nghiệp vụ ở nguồn vẫn hợp lệ.
Ứng dụng xử lý yêu cầu cấp quyền gửi thông điệp có thời hạn hiệu lực; sau sự cố kéo dài, một loạt lệnh cấp quyền cũ được phát lại dù chủ tài khoản đã thu hồi yêu cầu.
Một đội vận hành cần kiểm tra khả năng phục hồi khi broker bị dừng đúng lúc consumer ghi dữ liệu sang cơ sở dữ liệu; bài kiểm thử hiện chỉ đo hệ thống khởi động lại mà không đối soát tác động nghiệp vụ.
Nhóm tính cước điện thoại đối soát số message đầu vào với số bản ghi đã tính tiền; tổng số lượng bằng nhau nhưng có bản ghi tính trùng và bản ghi mất nên tổng tiền vẫn chênh lệch.
Một hệ thống xuất hóa đơn có consumer lưu dấu xử lý trùng dựa trên mã bản tin; khi cùng sự kiện đến qua các cầu nối broker khác nhau với mã mới, hai bản hóa đơn được tạo cho một đơn hàng.
