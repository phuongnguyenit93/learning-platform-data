Câu 1: Trong hệ thống hướng sự kiện, thành phần nào thông báo sự việc đã xảy ra?
A. Dispatcher tự tạo sự việc thay cho các nguồn phát.
B. Handler luôn thay đổi trạng thái của nguồn phát.
C. Event loop tự lưu các giao dịch vào cơ sở dữ liệu.
D. Nguồn phát công bố event thông báo một sự việc đã xảy ra.
Đáp án đúng: D

Câu 2: Dispatcher có nhiều handler được đăng ký; trách nhiệm chính của nó là gì?
A. Ghi bền vững mọi sự kiện trước khi gọi handler.
B. Chuyển tất cả event thành truy vấn tới cơ sở dữ liệu.
C. Định tuyến event tới các handler đã đăng ký phù hợp.
D. Tự thực hiện toàn bộ nghiệp vụ của mọi handler.
Đáp án đúng: C

Câu 3: Trong event-driven design, event khác command như thế nào?
A. Event buộc có một đích; command buộc có nhiều đích.
B. Event yêu cầu thực hiện; command báo việc đã xảy ra.
C. Event báo việc đã xảy ra, command yêu cầu hành động.
D. Event cần phản hồi; command buộc phát tới mọi subscriber.
Đáp án đúng: C

Câu 4: Publisher không cần biết những subscriber nào đang nhận sự kiện; điều này giúp gì?
A. Buộc mọi subscriber chạy trên cùng một thread điều phối.
B. Giảm phụ thuộc trực tiếp giữa publisher và subscriber.
C. Loại bỏ nhu cầu quản lý hợp đồng dữ liệu giữa các bên.
D. Bảo đảm mọi handler hoàn tất đồng thời với publisher.
Đáp án đúng: B

Câu 5: Vì sao payload sự kiện thường được giữ bất biến sau khi phát đi?
A. Tránh các handler sửa chung dữ liệu trong lúc xử lý.
B. Cho phép handler sửa payload trên mọi consumer tiếp theo.
C. Loại bỏ yêu cầu quản lý phiên bản khi đổi schema.
D. Bảo đảm event chỉ tồn tại trong một instance ứng dụng.
Đáp án đúng: A

Câu 6: Khi thêm trường tùy chọn vào event schema, điều kiện nào giúp tương thích ngược?
A. Publisher đổi nghĩa trường cũ nhưng vẫn giữ tên trường.
B. Consumer cũ bỏ qua trường mới và giữ hành vi hợp lệ.
C. Consumer cũ phải hiểu trường mới trước khi nhận event.
D. Consumer cũ từ chối mọi payload có thêm thuộc tính.
Đáp án đúng: B

Câu 7: Trong publish-subscribe có hai subscription độc lập cùng khớp event, điều gì thường xảy ra?
A. Dispatcher gộp mọi handler vào một transaction chung.
B. Chỉ subscription đăng ký trước nhận, bên sau phải chờ.
C. Hai subscription luôn cạnh tranh xử lý một bản duy nhất.
D. Mỗi subscription đều nhận event theo hợp đồng pub/sub.
Đáp án đúng: D

Câu 8: Trong event envelope, tổ hợp thông tin nào giúp nhận diện và truy vết?
A. Tên thread, stack depth, source file và line number.
B. Tên hàm, module classpath, worker pool và địa chỉ file.
C. Event ID, loại event, thời điểm và mã correlation ID.
D. Địa chỉ máy, dung lượng heap, CPU và garbage collection.
Đáp án đúng: C

Câu 9: Handler chạy I/O chặn kéo dài ngay trên event loop gây ra hậu quả gì?
A. Event loop tự tăng số thread để chạy mọi callback song song.
B. Dispatcher tự bỏ qua handler chậm sau một vòng lặp.
C. Callback khác phải chờ đến khi event loop hết bị chặn.
D. Các callback khác không bị ảnh hưởng do có queue riêng.
Đáp án đúng: C

Câu 10: Muốn gọi dịch vụ đồng bộ chặn trong ứng dụng event loop, nên thiết kế ra sao?
A. Chuyển thao tác chặn qua executor hoặc API async.
B. Thêm vòng lặp bận để chờ dịch vụ trả kết quả nhanh.
C. Gọi dịch vụ chặn từ callback ưu tiên cao của loop.
D. Đặt sleep trước lệnh chặn để giảm số lần gọi dịch vụ.
Đáp án đúng: A

Câu 11: Lệnh publish bất đồng bộ trả về ngay; kết luận nào an toàn nhất?
A. Tất cả consumer đã trả được kết quả cuối cùng về nguồn.
B. Đã gửi yêu cầu phát event, chưa có xác nhận mọi handler hoàn tất.
C. Mọi subscriber đã nhận ACK cho mọi side effect liên quan.
D. Mọi handler đã thành công và ghi xong trạng thái nghiệp vụ.
Đáp án đúng: B

Câu 12: Hai handler trên worker khác nhau cùng ghi Map mutable; nguy cơ gì cần xử lý?
A. Timestamp trong event sẽ ngăn việc ghi chồng lẫn nhau.
B. Chỉ thêm sleep giữa các lần ghi là đủ để an toàn.
C. Cần đồng bộ hoặc trạng thái an toàn cho các worker.
D. Chỉ việc đổi thứ tự đăng ký là ngăn được mọi race.
Đáp án đúng: C

Câu 13: Event A phát trước B nhưng handler B hoàn tất trước A; vì sao có thể?
A. Mọi handler đều chạy đồng bộ trong đúng một thread.
B. Dispatcher đã bảo đảm thứ tự hoàn tất khớp thứ tự phát.
C. Hai event chắc chắn có timestamp bị đảo trong payload.
D. Handler chạy bất đồng bộ và thời lượng xử lý có thể khác nhau.
Đáp án đúng: D

Câu 14: Để lỗi một subscriber không làm gián đoạn các subscriber khác, nên làm gì?
A. Xóa lỗi khỏi mọi log để publisher không nhìn thấy.
B. Cô lập lỗi theo handler với chính sách báo cáo rõ.
C. Hủy đăng ký tất cả subscriber sau lỗi đầu tiên.
D. Lan truyền exception rồi dừng toàn bộ handler còn lại.
Đáp án đúng: B

Câu 15: Màn hình đăng ký listener mỗi lần mở nhưng không gỡ khi đóng dễ gây điều gì?
A. Event loop mở rộng hàng đợi nhưng không tốn thêm bộ nhớ.
B. Garbage collector chắc chắn gỡ cả listener còn đăng ký.
C. Giữ listener cũ dẫn đến rò rỉ và gọi callback trùng nhiều lần.
D. Payload tự được khóa để không thay đổi ở mọi callback.
Đáp án đúng: C

Câu 16: Khi hủy tác vụ async đã bắt đầu xử lý event, cần cơ chế phối hợp nào?
A. Dùng tín hiệu hủy và điểm kiểm tra dừng hợp tác.
B. Chỉ thay timestamp của event trước callback kế tiếp.
C. Chỉ hạ độ ưu tiên của message đã được giao xử lý.
D. Chỉ xóa tên sự kiện khỏi danh sách đăng ký nhận.
Đáp án đúng: A

Câu 17: Producer phát 500 event/giây, consumer xử lý 100/giây; queue vô hạn sẽ ra sao?
A. Dispatcher tự gộp mọi event mà không mất nội dung.
B. Consumer tự tăng tốc lên đúng 500 event/giây khi tải tăng.
C. Backlog tăng dần, có thể làm cạn bộ nhớ.
D. Queue tự ổn định vì producer có tốc độ cao hơn consumer.
Đáp án đúng: C

Câu 18: Bounded queue đã đầy; chính sách tiếp nhận hợp lệ nào có thể chọn?
A. Ghi đè ngẫu nhiên event đang xử lý trong mọi consumer.
B. Đánh dấu event mới đã thành công dù chưa được nhận.
C. Chờ, từ chối hoặc loại bỏ event theo chính sách quá tải đã công bố.
D. Tự mở rộng queue vô hạn nhưng vẫn giữ hạn mức bộ nhớ.
Đáp án đúng: C

Câu 19: Backpressure dựa trên demand của subscriber nhằm kiểm soát điều gì?
A. Số message được tự chuyển thành lời gọi đồng bộ.
B. Số event phát vượt năng lực downstream để giảm độ trễ.
C. Thứ tự event được đảo ngẫu nhiên để tránh tắc nghẽn.
D. Điều tiết số event theo sức tiếp nhận downstream.
Đáp án đúng: D

Câu 20: Vì sao không nên block event-loop thread để đợi queue còn chỗ trống?
A. Event loop kẹt khiến callback khác phải chờ.
B. Queue có giới hạn sẽ tự trở thành queue không giới hạn.
C. Event đang chờ sẽ tự động chuyển vào đĩa bền vững.
D. Event loop không bao giờ đọc được độ sâu hàng đợi.
Đáp án đúng: A

Câu 21: UI phát dồn resize event nhưng chỉ cần kích thước cuối; chiến lược nào thích hợp?
A. Tăng vô hạn số handler chạy đồng thời để xử lý nhanh.
B. Gộp các event gần nhau, chỉ xử lý trạng thái mới nhất.
C. Xử lý đủ mọi resize cũ trước mỗi lần vẽ lại màn hình.
D. Sinh một callback cho từng pixel cần render trên cửa sổ.
Đáp án đúng: B

Câu 22: Một buffer chứa được burst ngắn nhưng nghẽn kéo dài; kết luận đúng là gì?
A. Buffer hấp thụ burst nhưng không thay backpressure.
B. Buffer tự tối ưu handler dù lượng event tăng mãi.
C. Buffer cho phép bỏ qua xử lý toàn bộ event cũ.
D. Buffer giữ producer và consumer cùng thông lượng trong mọi tải.
Đáp án đúng: A

Câu 23: Hàng đợi có ưu tiên cao và thấp dễ có vấn đề công bằng nào?
A. Event thấp có thể bị đói khi nhóm cao đến liên tục.
B. Event ưu tiên cao bắt buộc phải xử lý sau nhóm thấp.
C. Mọi mức ưu tiên tự công bằng mà không cần chính sách.
D. Event ưu tiên thấp luôn được xử lý trước nhóm cao.
Đáp án đúng: A

Câu 24: Khi consumer lag và p99 latency cùng tăng liên tục, nên điều tra gì trước?
A. Toàn bộ event ID đã bị trùng trong lần publish này.
B. Schema chắc chắn đã bỏ một trường tùy chọn gần đây.
C. Múi giờ timestamp event chắc chắn đã cấu hình sai.
D. Event vào nhanh hơn năng lực xử lý downstream.
Đáp án đúng: D

Câu 25: Consumer commit DB thành công nhưng mất ACK, broker giao lại event; điều gì đúng?
A. At-least-once có thể gây xử lý trùng khi phát lại.
B. At-most-once luôn đảm bảo mọi event được phát lại đủ lần.
C. Exactly-once end-to-end đã được bảo đảm chỉ nhờ ACK.
D. Thứ tự event sẽ tự động chặn toàn bộ lần gửi lại.
Đáp án đúng: A

Câu 26: At-most-once delivery có rủi ro nào khi consumer gặp lỗi giữa chừng?
A. Message chắc chắn được gửi lại tới lúc xử lý thành công.
B. Message có thể mất mà không được gửi lại để xử lý tiếp.
C. Side effect tự rollback trên các hệ thống liên quan.
D. Mọi message buộc có ít nhất hai bản sao khi truyền.
Đáp án đúng: B

Câu 27: Vì sao exactly-once trong broker chưa đủ bảo đảm một giao dịch DB bên ngoài?
A. DB ngoài broker cần idempotency hay giao dịch điều phối.
B. Event ID tự chặn mọi lệnh INSERT trong DB ngoài broker.
C. Broker tự rollback mọi DB bên ngoài khi consumer thất bại.
D. ACK message tự chuyển thành commit của DB transaction.
Đáp án đúng: A

Câu 28: Consumer xử lý lại cùng event nhiều lần; khóa deduplication nào phù hợp?
A. ID mới được tạo riêng ở mỗi lần broker gửi lại message.
B. Timestamp lúc callback bắt đầu trên consumer đang chạy.
C. Tên thread đã nhận message ở lần retry gần nhất.
D. Giữ cùng event ID ổn định qua tất cả lần redelivery.
Đáp án đúng: D

Câu 29: Handler tạo charge khi nhận event thanh toán; làm sao hỗ trợ idempotency?
A. Dùng operation ID ổn định để tránh charge trùng.
B. Dùng timestamp mới để phân biệt các lần thanh toán lại.
C. Tạo request ID mới mỗi lần retry để không trùng tên.
D. Tạo thread khác cho mỗi retry để không dùng chung cache.
Đáp án đúng: A

Câu 30: Với retry khi gặp lỗi tạm thời, backoff kèm jitter giúp ích gì?
A. Không cần giới hạn retry vì backoff luôn đạt thành công.
B. Bảo đảm message chỉ thất bại tối đa hai lần xử lý.
C. Dàn đều thời điểm thử lại nhờ backoff có jitter phù hợp.
D. Buộc mọi consumer retry chính xác trong cùng một thời điểm.
Đáp án đúng: C

Câu 31: Message liên tục giải mã thất bại do payload không hợp lệ; nên xử lý ra sao?
A. Chuyển vào dead-letter kèm nguyên nhân xử lý lỗi.
B. ACK thành công như thể đã thực hiện đầy đủ nghiệp vụ.
C. Retry vô hạn trên cùng consumer với payload không đổi.
D. Tự sửa ngẫu nhiên nội dung payload rồi phát lại.
Đáp án đúng: A

Câu 32: Nếu ACK event trước khi DB commit rồi commit thất bại, rủi ro chính gì?
A. Broker chắc chắn retry vì đã phát hiện DB commit thất bại.
B. Consumer tự tái tạo mọi side effect nhờ dispatcher.
C. ACK tự trì hoãn tới lúc DB transaction được commit.
D. ACK rồi nhưng DB commit thất bại, dẫn tới mất cập nhật.
Đáp án đúng: D

Câu 33: Muốn deduplicate và ghi nghiệp vụ cùng một DB, nên dùng cách nào?
A. Kiểm tra inbox và ghi nghiệp vụ trong hai transaction riêng.
B. Ghi inbox ID và cập nhật nghiệp vụ cùng transaction.
C. Chỉ dùng một cờ volatile trong bộ nhớ của consumer.
D. Chỉ đợi thêm một khoảng cố định trước khi ACK event.
Đáp án đúng: B

Câu 34: Nếu yêu cầu thứ tự event theo tài khoản trên broker phân vùng, nên chọn key nào?
A. Dùng account ID cố định để phân vùng các event cùng tài khoản.
B. Loại event để mọi tài khoản được đưa vào một partition.
C. ID ngẫu nhiên khác nhau cho mọi event cùng tài khoản.
D. Timestamp nhận event tại các consumer đang hoạt động.
Đáp án đúng: A

Câu 35: Khi nhiều partition xử lý song song, thứ tự nào thường không được bảo đảm?
A. Thứ tự xử lý tuần tự trong một consumer của partition.
B. Thứ tự event ghi vào cùng một partition nhất định.
C. Thứ tự của cùng producer ghi vào một partition.
D. Không đảm bảo thứ tự tổng thể giữa các partition.
Đáp án đúng: D

Câu 36: Trong pipeline event-driven, event time khác processing time ở điểm nào?
A. Event time là ngày triển khai, processing time là version.
B. Event time đo CPU, processing time đo băng thông mạng.
C. Event time là lúc xảy ra, processing time là lúc xử lý event.
D. Hai mốc thời gian luôn bằng nhau trong mọi sự kiện đã lưu.
Đáp án đúng: C

Câu 37: Watermark trong xử lý event time chủ yếu dùng để làm gì?
A. Đếm số handler có thể đăng ký vào một nguồn phát.
B. Theo dõi tiến độ event time để xét event đến muộn.
C. Đo lượng CPU còn trống trước khi nhận batch tiếp.
D. Đếm số retry cần thực hiện với từng event thất bại.
Đáp án đúng: B

Câu 38: Event version cũ đến sau version mới khi cập nhật entity; cách xử lý nào đúng?
A. Xếp theo tên event thay vì version để xác định thứ tự.
B. Kiểm tra version trước khi ghi đè entity.
C. Ghi đè ngay vì event nhận sau luôn có dữ liệu mới hơn.
D. Đổi entity ID để giữ cả hai trạng thái hoàn toàn riêng.
Đáp án đúng: B

Câu 39: Khi replay event log để dựng projection, vấn đề nào cần phòng tránh?
A. Replay mặc định xóa mọi event ID khỏi payload cũ.
B. Projection tự được tái tạo mà không chạy handler.
C. Replay tự động chuyển event cũ thành command mới.
D. Side effect bên ngoài projection bị kích hoạt lại.
Đáp án đúng: D

Câu 40: Transactional outbox giúp giải quyết khoảng hở nào khi publish?
A. Bảo đảm gửi event qua mạng đúng một lần tuyệt đối.
B. Ghi dữ liệu nghiệp vụ và outbox trong một DB transaction.
C. Buộc mọi consumer chung một transaction DB phân tán.
D. Bảo đảm thứ tự toàn cục giữa mọi partition broker.
Đáp án đúng: B

Câu 41: Trong saga, thanh toán xong nhưng bước vận chuyển thất bại; hướng nào hợp lý?
A. Tin mọi side effect tự rollback trên các dịch vụ.
B. Xóa mọi event lịch sử để downstream không thấy lỗi.
C. Thực hiện bù trừ theo chính sách nghiệp vụ.
D. Đánh dấu cả saga thành công vì đã có thanh toán.
Đáp án đúng: C

Câu 42: Để unit test một handler có dependency bên ngoài, cách nào hữu ích?
A. Bắt buộc dùng broker production trong mọi bài test đơn vị.
B. Bỏ mọi assert nếu callback không ném ngoại lệ.
C. Chỉ đếm số thread được tạo ra khi handler hoạt động.
D. Dùng fake/stub, kiểm chứng kết quả và tương tác.
Đáp án đúng: D

Câu 43: Trong test handler async, nên chờ kết quả bằng cơ chế nào?
A. Sleep thật dài rồi cho test tự động pass khi hết giờ.
B. Chờ vô hạn dù tác vụ không bao giờ hoàn thành.
C. Assert ngay sau publish và không kiểm soát race.
D. Chờ tín hiệu hoàn thành với timeout và kiểm tra kết quả xử lý.
Đáp án đúng: D

Câu 44: Để truy vết event qua nhiều service và callback async, cần lan truyền gì?
A. Tên thread publisher làm định danh chung toàn hệ thống.
B. Số CPU core của service tại thời điểm publisher phát.
C. Lan truyền correlation/trace context qua async.
D. Địa chỉ IP client trong từng câu lệnh ghi của consumer.
Đáp án đúng: C

Câu 45: Metric nào thể hiện consumer đang tụt sau tốc độ phát event?
A. Quan sát consumer lag hoặc backlog theo thời gian.
B. Số class được load từ lúc tiến trình vừa khởi động.
C. Số lần gọi hashCode trong một request ứng dụng.
D. Dung lượng mã nguồn được build ở publisher.
Đáp án đúng: A

Câu 46: Khi dead-letter queue tăng nhanh, cách chẩn đoán nào hữu ích?
A. Phân loại lỗi theo schema và lịch sử các lần retry.
B. Xóa hết message lỗi trước khi đọc nội dung và lý do.
C. Đổi tên queue để mọi metric về mức bằng không.
D. Tăng retry vô hạn mà không cần quan sát log.
Đáp án đúng: A

Câu 47: Muốn kiểm chứng cơ chế dedup khi ACK bị mất, nên thử kịch bản nào?
A. Chỉ đo thời gian khi producer không phát message.
B. Đổi payload và chỉ kiểm thử nhánh xử lý thành công.
C. Sinh event ID mới mỗi khi message được gửi lại.
D. Mất ACK sau commit rồi phát lại đúng event ID đó.
Đáp án đúng: D

Câu 48: Consumer mới cần đọc event log có schema cũ; loại kiểm thử nào phù hợp?
A. Chỉ biên dịch mã mới rồi bỏ qua event cũ trong log.
B. Contract test với payload của các schema version cũ.
C. Chỉ đo heap của consumer trước khi mở subscription.
D. Chỉ đo throughput producer với schema mới nhất hiện có.
Đáp án đúng: B

Câu 49: Khi tắt service có queue đang xử lý, phương án nào giúp shutdown an toàn?
A. Ngắt mọi thread ngay lập tức mà không lưu tiến độ.
B. Dừng nhận mới, drain hoặc hủy có lưu tiến độ.
C. Tiếp tục nhận event mới dù đang đóng broker kết nối.
D. Xóa queue trong bộ nhớ rồi báo mọi event đã xử lý.
Đáp án đúng: B
