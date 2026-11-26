Câu 01. Với Point-to-Point Channel và nhiều competing consumer, mỗi thông điệp thường được phân phối thế nào?
A. Thông điệp lần lượt đi qua mọi consumer trong nhóm
B. Một thông điệp được một consumer trong nhóm xử lý
C. Mọi consumer trong nhóm đều nhận cùng một bản sao
D. Mỗi consumer đọc bản sao độc lập của cả luồng
Đáp án đúng: B

Câu 02. Với Publish-Subscribe Channel, mỗi subscriber độc lập được phục vụ theo nguyên tắc nào?
A. Mỗi subscriber có thể nhận bản sao của cùng sự kiện
B. Chỉ subscriber đầu tiên được phép nhận sự kiện mới
C. Subscriber phải dùng chung một offset trên mọi topic
D. Sự kiện chỉ phát sau khi subscriber trước đã xử lý
Đáp án đúng: A

Câu 03. Lợi ích chính của Message Channel giữa hai hệ thống độc lập là gì?
A. Bảo đảm mọi thông điệp đều được xử lý đúng một lần
B. Loại bỏ nhu cầu kiểm tra lỗi nghiệp vụ của bên nhận
C. Tách sự hiện diện tức thời của bên gửi và bên nhận
D. Buộc hai hệ thống luôn cùng dùng một schema dữ liệu
Đáp án đúng: C

Câu 04. Một đối tác gửi trường `cust_no`, hệ thống đích dùng `customerId`; pattern nào phù hợp để đổi cấu trúc?
A. Aggregator gộp nhiều thông điệp thành một kết quả
B. Content-Based Router chọn kênh theo giá trị trường
C. Message Translator đổi schema giữa hai hệ thống
D. Wire Tap sao chép thông điệp sang hệ thống giám sát
Đáp án đúng: C

Câu 05. Đơn hàng có `region=EU` phải đi kênh EU, còn khu vực khác đi kênh mặc định; pattern nào phù hợp?
A. Recipient List gửi một message tới nhiều bên nhận
B. Content-Based Router chọn kênh theo nội dung
C. Message Filter bỏ mọi message không trùng điều kiện
D. Resequencer sắp thông điệp theo số thứ tự đã có
Đáp án đúng: B

Câu 06. Một sự kiện cần gửi đến cả kho báo cáo và dịch vụ cảnh báo theo danh sách cấu hình; pattern nào phù hợp?
A. Message Filter từ chối thông điệp theo predicate
B. Recipient List gửi thông điệp tới nhiều đích
C. Claim Check thay nội dung lớn bằng một token tra cứu
D. Content-Based Router chọn một kênh phù hợp duy nhất
Đáp án đúng: B

Câu 07. Hệ thống chỉ chuyển tiếp các event có `isValid=true`, còn event khác bị loại theo chính sách; dùng gì?
A. Aggregator nối các phản hồi thành một thông điệp chung
B. Content Enricher gọi nguồn ngoài để thêm dữ liệu vào
C. Splitter tách message lớn thành nhiều message nhỏ
D. Message Filter chỉ cho message thỏa điều kiện đi tiếp
Đáp án đúng: D

Câu 08. Cần sao chép thông điệp sang kênh audit mà không thay đổi tuyến xử lý chính; pattern nào phù hợp?
A. Recipient List thay thế kênh chính bằng nhiều kênh
B. Resequencer hoãn thông điệp để chỉnh lại thứ tự
C. Wire Tap tạo bản sao quan sát trên kênh phụ
D. Message Translator đổi tên trường trước khi gửi đi
Đáp án đúng: C

Câu 09. Thông điệp thiếu tên khách hàng, nhưng có ID để tra cứu từ CRM trước khi gửi tiếp; chọn pattern nào?
A. Aggregator ghép các response không cùng correlation ID
B. Content Enricher bổ sung dữ liệu tra cứu từ CRM
C. Routing Slip đặt danh sách bước xử lý trong header
D. Message Filter bỏ thông điệp thiếu trường tên khách
Đáp án đúng: B

Câu 10. Thông điệp mang payload lớn; muốn lưu payload riêng và luân chuyển mã tham chiếu để lấy lại sau, dùng gì?
A. Message Filter xóa các trường payload không cần thiết
B. Wire Tap nhân bản payload sang kênh quan sát phụ
C. Claim Check lưu nội dung rồi truyền tham chiếu tra cứu
D. Content-Based Router chọn tuyến theo kích thước payload
Đáp án đúng: C

Câu 11. Một đơn hàng chứa 20 dòng sản phẩm, cần xử lý song song từng dòng; pattern nào tách message?
A. Aggregator gom các dòng thành message của đơn hàng
B. Message Translator đổi schema của nguyên đơn hàng
C. Resequencer đổi thứ tự các message đã được nhận
D. Splitter tách đơn hàng thành message theo từng dòng
Đáp án đúng: D

Câu 12. Sau khi Splitter phát nhiều dòng đơn hàng, làm sao Aggregator gộp đúng kết quả cùng đơn?
A. Dùng correlation key và điều kiện hoàn tất theo đơn
B. Gộp mọi message nhận trong cùng một giây thành đơn
C. Gộp theo tên consumer đang xử lý từng dòng hàng
D. Dựa vào offset lớn nhất của cả topic để đóng đơn
Đáp án đúng: A

Câu 13. Aggregator mong 8 phản hồi nhưng mới có 7 trước hạn; xử lý nào tránh chờ vô hạn và minh bạch kết quả?
A. Gộp bảy phản hồi rồi ghi trạng thái là thành công đủ
B. Đợi vô thời hạn đến khi đủ tám phản hồi của đơn
C. Hết hạn chờ và báo kết quả còn thiếu phản hồi
D. Tự tạo phản hồi thứ tám rồi coi là đã xử lý đủ
Đáp án đúng: C

Câu 14. Các message có số thứ tự 1, 3, 2 đến kênh; pattern nào phục hồi thứ tự trước khi xử lý?
A. Resequencer giữ tạm và phát theo sequence hợp lệ
B. Wire Tap sao chép cả ba message sang kênh phụ
C. Message Filter loại message có sequence nhỏ hơn
D. Splitter chia mỗi message thành nhiều phần nhỏ hơn
Đáp án đúng: A

Câu 15. Gửi cùng một yêu cầu báo giá đến nhiều nhà cung cấp rồi tổng hợp các phản hồi; pattern nào phù hợp?
A. Message Filter chỉ cho phản hồi đầu tiên đi tiếp
B. Claim Check lưu phản hồi và chuyển token cho bên gửi
C. Resequencer đổi thứ tự phản hồi theo khóa message
D. Scatter-Gather phân phát và gom các câu trả lời
Đáp án đúng: D

Câu 16. Mỗi message mang danh sách bước `validate → enrich → publish` để đi lần lượt; pattern nào mô tả cách định tuyến?
A. Wire Tap tạo bản sao để phục vụ theo dõi luồng
B. Content-Based Router chỉ chọn kênh theo một rule
C. Routing Slip mang lộ trình xử lý qua các bước
D. Recipient List phát một lúc tới các đích độc lập
Đáp án đúng: C

Câu 17. Luồng cần chọn bước tiếp theo từ registry có thể đổi quy tắc khi chạy; pattern nào thích hợp?
A. Static Router buộc cấu hình tuyến được tạo lúc build
B. Dynamic Router tra cứu điểm đến tại thời điểm chạy
C. Splitter tách message ra trước khi biết điểm đến
D. Aggregator chọn điểm đến từ số phản hồi đã nhận
Đáp án đúng: B

Câu 18. Hai request bất đồng bộ trả lời không theo thứ tự gửi; dùng field nào để ghép từng reply đúng request?
A. Timestamp bên gửi để xác định duy nhất yêu cầu cũ
B. Tên consumer nhận reply để tìm request đã phát
C. Message ID mới của reply làm ID cho request bất kỳ
D. Correlation ID ghép reply với request tương ứng
Đáp án đúng: D

Câu 19. Một request bất đồng bộ phải chỉ nơi nhận phản hồi; metadata nào thường được truyền kèm?
A. Audit channel để broker tự xử lý kết quả nghiệp vụ
B. Dead-letter channel để mọi phản hồi trả về khi thành công
C. Wire-tap channel để client tự lấy mọi phản hồi mới
D. Reply-to channel để bên xử lý gửi phản hồi đúng nơi
Đáp án đúng: D

Câu 20. Client đã timeout request–reply nhưng reply cũ đến muộn; xử lý nào tránh áp vào request khác?
A. Dùng reply muộn để hoàn tất request mới nhất còn chờ
B. Dựa thứ tự nhận reply để ghép vào request gần nhất
C. Dựa correlation ID và trạng thái để bỏ reply muộn
D. Gửi lại reply cũ cho mọi request chưa có kết quả
Đáp án đúng: C

Câu 21. Một consumer có thể nhận lại cùng event sau retry; Idempotent Receiver nên thực hiện điều gì?
A. Tăng số worker để cùng xử lý mọi bản sao cùng lúc
B. Đổi channel mỗi lần retry để không gặp lại message
C. Tạo ID ngẫu nhiên mới cho mỗi lần nhận message cũ
D. Dedup theo ID ổn định trước khi ghi hiệu ứng nghiệp vụ
Đáp án đúng: D

Câu 22. Kênh cần chịu được consumer tạm offline mà không mất message đã được nhận; nên cấu hình gì?
A. Lưu message bền vững và xác nhận sau xử lý phù hợp
B. Tự đánh dấu đã xử lý khi consumer bắt đầu đọc message
C. Chỉ lưu message trong RAM và giảm thời gian retry
D. Xóa message khi producer vừa gửi vào kết nối mạng
Đáp án đúng: A

Câu 23. Service lưu đơn hàng và phát sự kiện `OrderCreated`; pattern nào tránh lỗi ghi DB thành công nhưng phát event thất bại?
A. Recipient List phát cùng event tới hai broker độc lập
B. Wire Tap nhân đôi event trước khi service lưu đơn
C. Transactional Outbox lưu đơn và event cùng transaction
D. Message Filter chỉ phát event có đủ dữ liệu đơn
Đáp án đúng: C

Câu 24. Publisher đọc outbox, gửi event rồi crash trước khi đánh dấu đã gửi; điều nào cần được dự liệu?
A. Broker tự hoàn tác event khi outbox chưa đổi trạng thái
B. Consumer luôn nhận đúng một lần nhờ outbox database
C. Event chắc chắn bị mất nên phải hủy đơn hàng vừa tạo
D. Event có thể phát lại nên consumer cần chống trùng
Đáp án đúng: D

Câu 25. Consumer vừa cập nhật số dư vừa cần ghi nhận event ID đã xử lý; cách nào hỗ trợ chống trùng an toàn?
A. Chỉ giữ inbox ID trong bộ nhớ của worker đang chạy
B. Lưu inbox ID sau khi gửi ACK, tách khỏi cập nhật số dư
C. Tạo inbox ID mới mỗi lần retry để dễ thống kê lần nhận
D. Lưu inbox ID cùng cập nhật trong một transaction
Đáp án đúng: D

Câu 26. Đích trả lỗi 503 do quá tải tạm thời; retry nào giảm thêm áp lực lên dịch vụ?
A. Bỏ thông điệp ngay vì lỗi 503 chắc chắn không phục hồi
B. Retry theo backoff có jitter, giới hạn số lần thử
C. Tăng đồng thời số request retry cho mọi consumer
D. Retry liên tục ngay lập tức để giảm hàng đợi tích lũy
Đáp án đúng: B

Câu 27. Một message có payload sai định dạng và không thể parse dù retry; cần xử lý thế nào để luồng tiếp tục?
A. Chuyển sang dead-letter channel kèm ngữ cảnh lỗi
B. Thử lại vô hạn trên cùng message mà không cách ly
C. Đánh dấu parse thành công để consumer tiếp tục
D. Bỏ qua message và không ghi bất kỳ dấu vết xử lý
Đáp án đúng: A

Câu 28. Message parse hợp lệ nhưng không đạt quy tắc dữ liệu đầu vào; pattern nào phù hợp để tách riêng?
A. Invalid Message Channel nhận thông điệp không hợp lệ
B. Reply Channel nhận mọi thông điệp chưa có phản hồi
C. Wire Tap thay đổi dữ liệu sai trước khi xử lý tiếp
D. Resequencer loại dữ liệu không đạt kiểm tra nghiệp vụ
Đáp án đúng: A

Câu 29. Consumer đã retry có giới hạn nhưng thông điệp vẫn lỗi; cách xử lý nào giúp khôi phục về sau?
A. Tiếp tục retry không hạn định trong luồng chính
B. Reset mọi consumer về đầu topic sau mỗi lần lỗi
C. Xóa message thất bại để offset luôn tăng nhanh
D. Đưa vào DLQ kèm lỗi để sửa xong rồi phát lại
Đáp án đúng: D

Câu 30. Một quy trình đặt hàng gồm giữ tồn kho, thu tiền và tạo vận đơn ở các service riêng; Saga xử lý giao dịch ra sao?
A. Đợi mọi service trả về rồi mới ghi từng thay đổi
B. Chỉ phát event khi toàn bộ service đã hoàn tất
C. Dùng local transaction và hành động bù khi bước lỗi
D. Khóa tất cả database bằng một transaction ACID chung
Đáp án đúng: C

Câu 31. Trong saga orchestration, thành phần nào điều phối bước tiếp theo và compensation?
A. Một coordinator phát lệnh và theo dõi trạng thái saga
B. Broker phân trang message rồi tự gọi compensation
C. Mỗi service chỉ phát event mà không có điều phối chung
D. Một consumer bất kỳ tự thay thứ tự bước của saga
Đáp án đúng: A

Câu 32. Trong saga choreography, các service phối hợp với nhau chủ yếu bằng cách nào?
A. Chờ một coordinator tập trung ra lệnh cho từng bước
B. Phát domain event và phản ứng với event liên quan
C. Giữ một transaction database chung xuyên các service
D. Chỉ cập nhật dữ liệu thông qua một API gateway
Đáp án đúng: B

Câu 33. Saga đã thu tiền thành công nhưng bước giữ hàng thất bại; hành động compensation phù hợp là gì?
A. Chỉ xóa event thanh toán trên broker là đủ hoàn tác
B. Tạo giao dịch hoàn tiền theo chính sách của dịch vụ
C. Khôi phục trực tiếp transaction đã commit tại ngân hàng
D. Đánh dấu thành công toàn saga dù không giữ được hàng
Đáp án đúng: B

Câu 34. So với distributed transaction dùng khóa đồng bộ, điểm đặc trưng của Saga là gì?
A. Mỗi bước commit riêng và có nghiệp vụ bù khi cần
B. Saga bảo đảm tác dụng bù luôn là rollback vật lý
C. Coordinator luôn giữ transaction SQL xuyên mọi service
D. Mọi bước phải giữ khóa database đến lúc saga kết thúc
Đáp án đúng: A

Câu 35. Cần giữ thứ tự các sự kiện cập nhật cùng `orderId` trên nhiều partition; nên phân vùng như thế nào?
A. Đổi key mỗi lần gửi để cân bằng các partition hơn
B. Đặt key bằng timestamp gửi để có thứ tự toàn cục
C. Chia sự kiện luân phiên giữa mọi partition đang có
D. Dùng orderId làm key để giữ cùng partition
Đáp án đúng: D

Câu 36. Mỗi event mang snapshot trạng thái đầy đủ với `version` tăng dần; nếu phiên bản 8 đến trước phiên bản 7 do retry, consumer nên bảo vệ state thế nào?
A. Ghi đè state theo event được nhận sau trên mạng
B. Chỉ áp dụng snapshot có version lớn hơn state đang lưu
C. Chọn event có kích thước payload lớn hơn để ghi
D. Chọn event được broker đặt offset thấp nhất để ghi
Đáp án đúng: B

Câu 37. Khi tăng số competing consumer trong cùng channel, điều gì cần cân nhắc về thứ tự xử lý?
A. Không bảo đảm thứ tự toàn cục giữa các key song song
B. Tăng consumer sẽ tự áp dụng transaction xuyên service
C. Mọi consumer tự đồng bộ để giữ thứ tự toàn hệ thống
D. Mỗi consumer luôn nhận tất cả thông điệp theo thứ tự
Đáp án đúng: A

Câu 38. Message ID và Correlation ID thường khác vai trò như thế nào?
A. Message ID định danh bản tin; Correlation ID ghép request/reply
B. Message ID gắn phiên consumer; Correlation ID là reply-to
C. Message ID chung mỗi luồng; Correlation ID đổi khi retry
D. Message ID ghép request/reply; Correlation ID định danh bản tin
Đáp án đúng: A

Câu 39. Một lệnh giữ chỗ chỉ còn hiệu lực trong 30 giây; khi message đến sau hạn nên làm gì?
A. Phát lại message cho mọi consumer để tăng cơ hội giữ
B. Bỏ thời hạn và thực hiện lệnh như khi mới phát
C. Ghi nhận lệnh đã hết hạn, không thực hiện thao tác giữ chỗ
D. Đổi thời điểm tạo message thành lúc consumer nhận
Đáp án đúng: C

Câu 40. Muốn theo dõi end-to-end một request qua splitter, nhiều service và aggregator, nên kết hợp tín hiệu nào?
A. Đo CPU broker, độ trễ từng consumer và số kết nối hoạt động
B. Gắn trace/correlation ID, theo dõi lag, retry và dòng vào DLQ
C. Đo throughput từng service, backlog và số worker đang thực thi
D. Đếm message vào/ra từng channel và thời gian xử lý trung bình
Đáp án đúng: B
