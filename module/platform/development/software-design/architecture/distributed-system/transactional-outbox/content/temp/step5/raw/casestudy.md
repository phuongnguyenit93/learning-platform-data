Ứng dụng bán hàng ghi đơn hàng thành công vào PostgreSQL rồi gọi broker để phát OrderCreated; broker mất kết nối ngay sau commit và kho vận không nhận được thông tin đơn mới.
Trong hệ thống thanh toán, sự kiện PaymentCaptured được phát trước khi transaction cập nhật hóa đơn commit; transaction bị rollback nhưng dịch vụ kế toán vẫn xử lý khoản thanh toán chưa tồn tại.
Nhóm bổ sung bảng outbox nhưng thao tác ghi đơn và thêm bản ghi sự kiện diễn ra trong hai transaction khác nhau; một lỗi giữa hai bước làm dữ liệu nghiệp vụ và sự kiện tiếp tục lệch nhau.
Một API tạo khách hàng ghi bản ghi nghiệp vụ và outbox qua hai kết nối database khác nhau; mã Java báo hoàn tất dù một kết nối commit còn kết nối kia bị timeout.
Service quản lý tồn kho cập nhật trạng thái sản phẩm bằng bulk SQL ngoài transaction tạo sự kiện outbox; những cập nhật này không có thông điệp tương ứng trên topic.
Trong hệ thống đặt phòng, transaction kiểm tra số chỗ rồi ghi BookingConfirmed cùng bản ghi outbox; hai yêu cầu song song cùng vượt kiểm tra số chỗ trước khi cập nhật dữ liệu.
Một bảng outbox lưu payload cho nhiều loại sự kiện nhưng thiếu eventId và aggregateId; relay gửi lại sau sự cố khiến consumer không phân biệt được bản tin lặp và bản tin mới.
Đội tích hợp outbox ghi JSON theo cấu trúc DTO giao diện hiện hành; khi DTO được đổi tên trường, các bản ghi cũ còn chờ phát không còn được consumer phiên bản mới hiểu đúng.
Nhóm ghi thời gian eventCreatedAt khi bắt đầu request, nhưng transaction thực tế chờ khóa nhiều phút; dashboard sử dụng timestamp này để suy ra thứ tự commit và hiển thị sai diễn biến.
Trong mô hình đa tenant, bảng outbox lưu cùng một mã đơn ở hai doanh nghiệp nhưng relay chỉ dùng orderId làm khóa phân vùng; consumer ghép nhầm sự kiện của hai tenant.
Ứng dụng cần phát đồng thời OrderCreated và InventoryReserved từ một transaction; hai bản ghi outbox được viết nhưng relay phân phối theo thứ tự khác với thứ tự nghiệp vụ mong đợi.
Một bản ghi giao dịch tạo sự kiện chứa thông tin cá nhân nhạy cảm không cần thiết cho consumer; bản sao outbox và log relay kéo dài thời gian tồn tại của dữ liệu đó.
Relay polling chọn các hàng chưa gửi nhưng đánh dấu đã gửi trước khi broker xác nhận; broker gặp lỗi và những hàng đó biến mất khỏi danh sách chờ dù chưa có consumer nhận.
Trong job polling, relay phát bản tin lên broker thành công rồi chết trước lúc cập nhật trạng thái hàng outbox; sau khi khởi động lại, chính bản tin đó được phát thêm lần nữa.
Đội vận hành tăng số instance relay để đẩy nhanh throughput; hai instance đồng thời đọc cùng một nhóm hàng chưa xử lý rồi cùng gửi các bản tin lên broker.
Relay dùng truy vấn polling có khóa kéo dài qua thao tác gửi mạng; broker chậm khiến transaction giữ khóa nhiều giây và các giao dịch nghiệp vụ ghi outbox bị ảnh hưởng.
Một relay quét toàn bộ bảng outbox theo mỗi vài giây; khi hệ thống có hàng triệu bản ghi đã gửi, thời gian quét tăng và độ trễ công bố sự kiện vượt mục tiêu.
Nhóm giảm chu kỳ polling xuống rất ngắn để giảm độ trễ; khi lưu lượng đơn hàng thấp, database vẫn nhận lượng lớn truy vấn rỗng làm tăng chi phí vận hành.
Service ghi outbox ở database có nhiều replica nhưng relay đọc từ replica bất đồng bộ; bản ghi vừa commit không xuất hiện ngay và một số đơn bị báo thiếu sự kiện tạm thời.
Một worker gặp payload lỗi định dạng ở hàng đầu tiên của batch outbox; mỗi lần chạy lại đều lỗi tại hàng đó, khiến hàng nghìn sự kiện hợp lệ phía sau không được công bố.
Trong lúc relay gửi hàng loạt sự kiện, broker chỉ xác nhận một phần batch; nhóm đang đánh dấu toàn bộ batch hoàn tất và làm mất những sự kiện chưa được nhận.
Đội chuyển từ polling sang Debezium để theo dõi thay đổi outbox qua CDC; kết nối CDC chưa được cấp quyền đọc log phù hợp và pipeline đứng ở trạng thái chưa có dữ liệu.
Hệ thống chạy CDC dựa trên WAL của PostgreSQL; một connector Debezium ngừng hoạt động nhiều ngày khiến vị trí replication không tiến và dung lượng log tăng nhanh.
Nhóm triển khai Debezium mới trên database đã có nhiều bản ghi outbox chưa gửi; quá trình snapshot ban đầu và luồng thay đổi sau snapshot tạo ra các bản tin có nguy cơ lặp ở ranh giới.
Trong hệ thống CDC, bảng outbox vừa thêm trường eventType nhưng cấu hình ánh xạ của connector vẫn đọc schema cũ; sự kiện mới được đưa lên topic mà thiếu thông tin phân loại.
Ứng dụng chuyển dữ liệu outbox giữa các vùng; connector CDC bị ngắt rồi nối lại ở offset trước đó, khiến một khoảng sự kiện được phát lại sau khi bên nhận đã xử lý.
Một phiên bản ứng dụng mới phát sự kiện theo schema v2, trong khi một số bản ghi outbox v1 vẫn tồn tại; relay chung xuất cả hai phiên bản khiến consumer xử lý được loại này nhưng lỗi với loại kia.
Trong nền tảng đặt hàng, nhiều thay đổi trạng thái của cùng một đơn xảy ra liên tiếp; relay được chạy song song khiến OrderShipped tới consumer trước OrderPaid.
Đội dùng thời điểm tạo hàng làm khóa sắp xếp toàn hệ thống outbox, nhưng hai transaction trên những đơn khác nhau commit không cùng thứ tự với thời điểm tạo sự kiện.
Một consumer tính doanh thu nhận sự kiện OrderPaid hai lần sau khi relay retry; doanh thu tăng gấp đôi dù hàng Order chỉ có một lần cập nhật trong database nguồn.
Service quản lý khách hàng gửi CustomerDeleted rồi CustomerUpdated với cùng aggregateId do message chậm; consumer khôi phục lại hồ sơ đã xóa bằng sự kiện cập nhật cũ.
Một sự kiện được broker tiếp nhận nhưng consumer xác nhận trước khi ghi dữ liệu của mình; consumer chết giữa hai thao tác và thông tin cập nhật không xuất hiện ở hệ đích.
Nhóm cho rằng Transactional Outbox bảo đảm mỗi consumer chỉ xử lý sự kiện đúng một lần; một sự cố làm consumer restart khiến cùng eventId được áp dụng lặp lên số dư khách hàng.
Trong service báo cáo, consumer đã xử lý một sự kiện nhưng ghi dấu kiểm tra trùng vào database khác sau đó; lỗi ghi dấu khiến sự kiện được xử lý lại khi có retry.
Relay liên tục thử lại một thông điệp bị broker từ chối do kích thước quá lớn; hàng đó chiếm toàn bộ lượt retry trong khi các hàng nhỏ hợp lệ bị trì hoãn.
Đội đặt quy tắc xóa hàng outbox ngay sau khi nhận broker ack; khi cần điều tra một sự kiện đã công bố, không còn bản ghi để đối chiếu nội dung và thời điểm gửi.
Một job dọn hàng outbox xóa dữ liệu chưa gửi do dùng thời gian tạo thay vì trạng thái phân phối; các đơn hàng cũ bị kẹt từ trước mất khả năng được phát lại.
Dashboard giám sát chỉ đo số bản tin relay gửi thành công; khi tốc độ ghi outbox cao hơn tốc độ gửi, backlog và tuổi bản tin cũ nhất tăng nhưng không có cảnh báo.
Trong đợt nâng cấp hệ thống, broker báo nhiều lỗi tạm thời; relay retry với tốc độ cao và đẩy tải ngược vào database, khiến cả API ghi đơn hàng chậm theo.
Nhóm kiểm thử end-to-end chạy khi database commit xong rồi lập tức tìm event trên broker; quá trình relay có độ trễ thay đổi nên bài test ngẫu nhiên thất bại dù các thao tác nghiệp vụ được lưu đúng.
