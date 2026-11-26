Câu 01. Trong Kafka, thứ tự các record được bảo đảm theo vị trí ghi ở phạm vi nào?
A. Giữa các topic mà cùng một producer gửi dữ liệu
B. Trên toàn cluster dựa vào timestamp của record
C. Trong từng partition theo thứ tự offset của log
D. Trên mọi partition của topic theo thời gian gửi
Đáp án đúng: C

Câu 02. Offset của record trong Kafka có ý nghĩa chính xác nhất là gì?
A. Vị trí của record trong log của một partition
B. Mã định danh duy nhất của message ở mọi topic
C. Số thứ tự toàn cluster của record vừa được nhận
D. Thời điểm producer gửi record tới broker leader
Đáp án đúng: A

Câu 03. Với một consumer group ổn định, một partition được gán xử lý ra sao?
A. Một consumer bất kỳ ở mọi group được độc quyền đọc
B. Mọi consumer trong group đọc partition đó cùng lúc
C. Leader partition trực tiếp quyết định consumer nhận
D. Tối đa một consumer trong group nhận partition đó
Đáp án đúng: D

Câu 04. Một group có 6 consumer nhưng topic chỉ có 4 partition; tình trạng nào có thể xảy ra?
A. Kafka tự tăng partition thành 6 để đủ consumer
B. Producer bị chặn ghi vì group có dư consumer
C. Có consumer không được gán partition của topic
D. Mỗi partition được gán đồng thời cho hai consumer
Đáp án đúng: C

Câu 05. Hai consumer group độc lập cùng subscribe một topic; cách đọc nào là đúng?
A. Group vào trước giữ độc quyền toàn bộ topic đó
B. Hai group chia chung một offset của từng partition
C. Group thứ hai chỉ đọc khi group thứ nhất dừng
D. Mỗi group quản lý offset và nhận dữ liệu độc lập
Đáp án đúng: D

Câu 06. Consumer đã xử lý xong record tại offset 12; muốn lần sau đọc từ record tiếp theo, cần commit gì?
A. Commit offset 0 để xác nhận đã xử lý một batch
B. Commit offset 13 là vị trí cần đọc tiếp theo
C. Commit offset 12 là record đã được xử lý xong
D. Commit offset -1 để đánh dấu record vừa kết thúc
Đáp án đúng: B

Câu 07. Khi group không có committed offset hợp lệ, `auto.offset.reset=earliest` có tác dụng gì?
A. Xóa tất cả committed offset của group hiện tại
B. Đọc từ record vừa đến sau lúc consumer khởi động
C. Bắt đầu đọc từ offset còn lưu sớm nhất
D. Bắt đầu ở offset 0 dù dữ liệu đã bị retention xóa
Đáp án đúng: C

Câu 08. Một consumer group đọc chậm hơn thời gian retention; Kafka có đợi group xử lý xong trước khi xóa log?
A. Có, broker giữ mọi record đến khi tất cả group commit
B. Không, nhưng offset đã commit sẽ tự khôi phục dữ liệu
C. Không, retention chạy độc lập với tiến độ đọc của group
D. Có, leader lưu log mãi nếu vẫn còn một group có lag
Đáp án đúng: C

Câu 09. Đối với topic có `cleanup.policy=compact`, mục tiêu chính của log compaction là gì?
A. Giữ duy nhất record của partition leader trong topic
B. Giữ trạng thái gần nhất theo key trong phần log còn lại
C. Chỉ giữ các record thuộc cửa sổ thời gian gần nhất
D. Xóa mọi record ngay sau khi consumer đã commit offset
Đáp án đúng: B

Câu 10. Producer muốn các record cùng `orderId` có thứ tự ổn định; nên chọn partition như thế nào?
A. Gửi cùng key `orderId` qua partitioner nhất quán
B. Đổi key ngẫu nhiên để cân bằng tải giữa các broker
C. Chia lần gửi xen kẽ giữa các partition của topic
D. Gắn timestamp hiện tại làm key cho mọi lần cập nhật
Đáp án đúng: A

Câu 11. Khi tăng số partition, điều gì cần lưu ý về cách hash key phân vùng?
A. Mọi record cũ tự động di chuyển sang partition mới
B. Offset cũ được đánh số lại để giữ thứ tự toàn topic
C. Partitioner vẫn tính key theo số partition trước khi tăng
D. Key cũ có thể ánh xạ sang partition khác sau thay đổi
Đáp án đúng: D

Câu 12. Nếu producer không idempotent và có nhiều request in-flight, retry có nguy cơ gì?
A. Record có thể đảo thứ tự khi batch trước được retry
B. Broker sẽ ghi batch retry trước mọi batch gửi sau đó
C. Retry chỉ có thể tạo bản ghi trùng, không đảo thứ tự
D. Offset luôn được giữ sẵn cho batch lỗi trước khi retry
Đáp án đúng: A

Câu 13. Với producer `acks=all`, điều kiện xác nhận ghi thành công phụ thuộc điều gì?
A. Leader nhận xác nhận cần thiết từ các replica thuộc ISR
B. Chỉ leader cần ghi vào cache là đủ cho mọi cấu hình
C. Tất cả replica kể cả replica tụt hậu đều phải xác nhận
D. Tất cả consumer group phải commit record mới ghi
Đáp án đúng: A

Câu 14. Khi producer dùng `acks=all`, cấu hình `min.insync.replicas=2` có vai trò gì?
A. Buộc mọi partition phải có đúng hai replica vật lý
B. Đảm bảo consumer không đọc lại record đã xử lý
C. Yêu cầu ít nhất hai replica trong ISR cho phép ghi
D. Bắt mỗi consumer group khởi chạy hai consumer
Đáp án đúng: C

Câu 15. Khái niệm ISR của partition trong Kafka chỉ tập replica nào?
A. Những replica đang là leader của các topic khác
B. Những replica được consumer nhóm làm offset storage
C. Những replica từng lưu dữ liệu nhưng hiện mất kết nối
D. Những replica đang theo kịp leader theo tiêu chí của broker
Đáp án đúng: D

Câu 16. Một partition có replication factor bằng 3; số bản sao dữ liệu cấu hình là bao nhiêu?
A. Một leader và một follower đang ở trạng thái ISR
B. Ba bản sao, gồm một leader và hai follower
C. Ba follower cùng với một leader của partition
D. Ba leader độc lập cùng ghi một log của partition
Đáp án đúng: B

Câu 17. Trong Kafka dùng KRaft, thành phần nào thay thế vai trò phối hợp metadata của ZooKeeper?
A. Các consumer group lưu metadata ở local disk
B. Các partition leader tự chọn client coordinator
C. Các task Kafka Connect lưu metadata riêng
D. Nhóm controller theo cơ chế Raft quorum
Đáp án đúng: D

Câu 18. Một KRaft controller quorum có ba voter; tối thiểu mấy voter cần hoạt động để có đa số?
A. Ba voter vì mọi thay đổi đều đòi đồng thuận tuyệt đối
B. Bốn voter vì còn phải tính thêm broker controller
C. Hai voter để đạt quorum và tiếp tục quyết định
D. Một voter vì chỉ cần controller leader còn sống
Đáp án đúng: C

Câu 19. Producer bật `enable.idempotence`; tác dụng cốt lõi trong phạm vi gửi Kafka là gì?
A. Bảo đảm mọi DB bên ngoài chỉ nhận mỗi record một lần
B. Bảo đảm consumer xử lý xong trước khi producer trả về
C. Tránh ghi trùng do retry cùng producer sequence
D. Ngăn mọi business event trùng giữa các lần triển khai
Đáp án đúng: C

Câu 20. Vì sao xử lý at-least-once có thể tạo tác động nghiệp vụ lặp?
A. Consumer luôn commit trước khi chạy mã xử lý nghiệp vụ
B. Producer chỉ gửi record sau khi consumer commit offset
C. Kafka tự xóa record khi có consumer group đọc một lần
D. Worker xử lý xong nhưng crash trước khi commit offset
Đáp án đúng: D

Câu 21. Muốn đạt exactly-once cho quy trình đọc Kafka rồi ghi Kafka, nên phối hợp cơ chế nào?
A. Transaction ghi output và commit offsets cùng một giao dịch
B. Gắn key duy nhất vào record và bỏ kiểm tra giao dịch
C. Tắt retry producer và chạy một consumer cho mỗi topic
D. Commit offsets trước rồi mới bắt đầu ghi record output
Đáp án đúng: A

Câu 22. Với Kafka transactional producer, `sendOffsetsToTransaction` được dùng để làm gì?
A. Xóa offsets cũ trước khi thực hiện transaction mới
B. Ghi offsets đầu tiên vào header của mỗi record
C. Gửi offsets tới tất cả consumer đang trong group
D. Gộp offsets đã xử lý vào transaction ghi output
Đáp án đúng: D

Câu 23. Với `isolation.level=read_committed`, consumer Kafka sẽ nhận những record nào?
A. Chỉ record thuộc transaction, bỏ record do producer thường
B. Record thường và transaction đã commit, không nhận aborted
C. Consumer tự chốt transaction đang mở của producer khi poll
D. Đọc cả record chưa commit và aborted để giảm độ trễ đọc
Đáp án đúng: B

Câu 24. Với Kafka transaction, dùng `transactional.id` nhất quán giúp xử lý producer cũ thế nào?
A. Producer mới có thể fence phiên producer cũ cùng ID
B. Mọi producer có cùng ID sẽ ghi song song an toàn
C. Broker chuyển transactional.id thành consumer group ID
D. Producer cũ giữ quyền ghi đến khi token tự hết hạn
Đáp án đúng: A

Câu 25. Khi tăng `linger.ms` cho producer, đánh đổi điển hình nào xảy ra?
A. Bắt broker đồng bộ thêm follower trước khi nhận data
B. Đổi retention topic để giữ record lâu hơn trên disk
C. Giảm dung lượng mỗi batch nhưng luôn giảm latency
D. Tăng cơ hội gom batch nhưng có thể tăng độ trễ gửi
Đáp án đúng: D

Câu 26. Producer bật nén record batch; đánh đổi tài nguyên nào thường gặp?
A. Giảm băng thông và dung lượng đổi lấy CPU nén/giải nén
B. Giảm số replica cần đồng bộ mà vẫn giữ độ bền
C. Giảm CPU trên cả hai phía nhưng luôn tăng băng thông
D. Giảm số partition topic mà không thay đổi throughput
Đáp án đúng: A

Câu 27. Consumer không gọi `poll()` trong thời gian vượt `max.poll.interval.ms`; hậu quả có thể là gì?
A. Broker nới giới hạn poll khi consumer lag tăng cao
B. Bị coi là không tiến triển và kích hoạt group rebalance
C. Consumer tự reset offset khi quá thời hạn xử lý một poll
D. Group tiếp tục chờ cho đến khi consumer commit batch cũ
Đáp án đúng: B

Câu 28. Trong classic consumer group protocol, `session.timeout.ms` liên quan trực tiếp đến điều gì?
A. Giới hạn thời gian phải xử lý mọi record trong một poll
B. Thời hạn record được giữ trong commit log của topic
C. Thời gian chờ heartbeat trước khi coi member đã mất
D. Thời gian broker chờ các follower xác nhận acks=all
Đáp án đúng: C

Câu 29. Khi cấu hình `group.instance.id` cho consumer, mục đích chính là gì?
A. Giữ danh tính thành viên tĩnh để hạn chế rebalance thừa
B. Cố định partition leader cho consumer được chỉ định
C. Ép tất cả consumer nhận chung một danh sách partition
D. Ghi offset vào instance local để không cần Kafka broker
Đáp án đúng: A

Câu 30. So với eager rebalance, cooperative rebalance nhằm giảm gián đoạn bằng cách nào?
A. Đồng bộ các producer transaction trước khi group chạy
B. Xóa toàn bộ offset và để mọi consumer đọc lại từ đầu
C. Không cho consumer mới tham gia khi có consumer cũ
D. Di chuyển dần partition cần đổi thay vì thu hồi tất cả
Đáp án đúng: D

Câu 31. Trong Spring Kafka, annotation nào khai báo topic subscribe trực tiếp trên method listener?
A. `@SendTo` đăng ký method làm listener trên topic
B. `@KafkaListener` gắn method nhận record của consumer
C. `@EnableKafka` chỉ định topic cho method xử lý record
D. `@KafkaHandler` khai báo trực tiếp topic mà method sẽ lắng nghe
Đáp án đúng: B

Câu 32. Khi dùng manual acknowledgement trong Spring Kafka, khi nào nên `acknowledge()` để giảm mất dữ liệu?
A. Ngay khi record được poll, trước khi xử lý nghiệp vụ
B. Sau khi xử lý record thành công và ghi kết quả cần thiết
C. Khi worker khởi động mà chưa đọc bất kỳ record nào
D. Trước khi ghi database để tăng throughput của consumer
Đáp án đúng: B

Câu 33. Một record luôn gây lỗi parse, dù consumer retry nhiều lần; chiến lược xử lý phù hợp là gì?
A. Retry hữu hạn, đẩy vào DLT kèm ngữ cảnh để điều tra
B. Retry vô hạn trên cùng offset và chặn toàn bộ partition
C. Tạo thêm consumer trong group để che đi lỗi dữ liệu
D. Commit bỏ record mà không ghi lại lý do thất bại
Đáp án đúng: A

Câu 34. Trong Spring Kafka, `DefaultErrorHandler` có thể phối hợp cơ chế nào để xử lý record lỗi?
A. `DeadLetterPublishingRecoverer` tự định lịch retry record
B. `CommonErrorHandler` tự commit giao dịch database ngoài Kafka
C. Backoff retry và recoverer chuyển record lỗi vào DLT
D. `FixedBackOff` tự xuất record lỗi sang DLT sau lần retry
Đáp án đúng: C

Câu 35. Kafka Connect Source connector và Sink connector khác nhau chủ yếu ở hướng dữ liệu nào?
A. Cả hai connector đều lấy dữ liệu ngoài để phát vào Kafka
B. Source đưa dữ liệu vào Kafka; Sink đưa dữ liệu ra ngoài
C. Source đọc Kafka để ghi DB; Sink đọc DB để ghi Kafka
D. Source và Sink trao đổi trực tiếp, không cần topic Kafka
Đáp án đúng: B

Câu 36. Trong Kafka Connect distributed mode, task được vận hành và phối hợp thế nào?
A. Mọi worker chỉ chạy một task dù topic nhiều partition
B. Mỗi task phải chạy trên broker đang giữ topic leader
C. Các task chia sẻ một offset trong RAM mà không lưu bền
D. Các worker phân công task và lưu trạng thái qua Kafka
Đáp án đúng: D

Câu 37. Kafka Connect SMT phù hợp nhất với nhu cầu biến đổi nào?
A. Thay thế toàn bộ engine SQL của data warehouse đích
B. Đổi tên hoặc lọc field trên từng record của connector
C. Chạy aggregate nhiều giờ với state store phân tán
D. Join nhiều topic có state lớn và window theo event time
Đáp án đúng: B

Câu 38. Trong Kafka Streams, KTable phù hợp với loại dữ liệu nào?
A. Danh sách broker controller đang được KRaft bầu chọn
B. Trạng thái mới nhất theo key khi có các bản cập nhật
C. Chuỗi event bất biến mà mỗi record đều độc lập
D. Nhật ký offset commit của tất cả consumer group
Đáp án đúng: B

Câu 39. Một Kafka Streams window đã hết thời gian grace; event đến quá muộn thường được xử lý thế nào?
A. Bị loại khỏi window đã đóng theo chính sách grace
B. Buộc các broker kéo dài retention trên toàn topic
C. Tự mở window mới ở cùng mốc thời gian của event
D. Tự lùi committed offset để phát lại mọi record cũ
Đáp án đúng: A

Câu 40. Dashboard vận hành Kafka muốn phát hiện consumer chậm và replication có vấn đề; nên theo dõi gì?
A. Consumer fetch rate cùng số broker đang hoạt động
B. Số thành viên consumer group cùng số partition có leader
C. Consumer lag cùng số under-replicated partitions
D. Producer throughput cùng tổng dung lượng log topic
Đáp án đúng: C
