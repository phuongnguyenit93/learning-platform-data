Câu 1. Replication khác sharding ở mục tiêu phân bố dữ liệu như thế nào?
A. Replication chia theo khóa; sharding sao chép toàn bảng.
B. Replication tạo bản sao; sharding chia các phần dữ liệu.
C. Replication chỉ lưu log; sharding sao chép toàn bộ bảng.
D. Replication phân chia bảng; sharding nhân các bản sao.
Đáp án đúng: B

Câu 2. Trong single-leader replication, đường ghi phổ biến diễn ra như thế nào?
A. Ghi đến follower rồi được chuyển lại về leader.
B. Ghi đồng thời mọi replica rồi chọn giá trị mới nhất.
C. Ghi đến replica gần nhất và không qua leader.
D. Ghi đến leader rồi được truyền đến các follower.
Đáp án đúng: D

Câu 3. Khi sử dụng replication bất đồng bộ, leader có thể xác nhận ghi lúc nào?
A. Trước khi các follower nhận được cập nhật vừa ghi.
B. Chỉ sau khi mọi follower đã xác nhận cập nhật.
C. Sau khi mỗi follower đồng ý bỏ các bản ghi cũ.
D. Chỉ sau khi các follower được bầu làm leader.
Đáp án đúng: A

Câu 4. Đánh đổi chính khi yêu cầu follower xác nhận đồng bộ trước khi ack là gì?
A. Chờ replica xác nhận có thể tăng độ trễ ghi.
B. Độ trễ ghi giảm vì không chờ follower xác nhận.
C. Số shard tự giảm để tập trung các bản ghi mới.
D. Mọi đọc được xử lý từ cache và bỏ qua follower.
Đáp án đúng: A

Câu 5. Trong mô hình sao chép theo log, replica thường sử dụng log ra sao?
A. Tái sắp xếp log theo thời điểm nhận của từng client.
B. Bỏ mọi giao dịch ghi đã commit trên nguồn dữ liệu.
C. Chỉ sao chép các truy vấn SELECT đã trả về kết quả.
D. Áp dụng thay đổi theo thứ tự mà log đã ghi nhận.
Đáp án đúng: D

Câu 6. Nếu leader đã ack ghi bất đồng bộ rồi hỏng trước khi replica nhận ghi, rủi ro nào có thể xuất hiện?
A. Ghi đã ack có rủi ro mất nếu chưa được sao chép.
B. Ghi đã ack luôn có trên mọi replica dù chưa truyền.
C. Ghi đó tự trở thành giao dịch của leader đã hỏng.
D. Ghi bị khóa cho đến khi leader cũ trở lại hoạt động.
Đáp án đúng: A

Câu 7. Trong cơ chế bầu leader có số nhiệm kỳ tăng dần, fencing token dùng để làm gì?
A. Chặn yêu cầu ghi từ leader cũ có nhiệm kỳ thấp.
B. Cho phép leader cũ và mới ghi luân phiên cùng khóa.
C. Khóa toàn bộ dữ liệu trước khi một follower được bầu.
D. Giữ follower cũ làm nguồn chân lý ở mọi datacenter.
Đáp án đúng: A

Câu 8. Tình trạng split-brain trong single-leader có thể dẫn tới hệ quả nào?
A. Replica chỉ còn được đọc sau khi leader khởi động.
B. Mọi transaction tự chuyển sang chế độ hai pha.
C. Hai node cùng làm leader có thể tạo ghi xung đột.
D. Các bản sao tự hợp nhất theo một thứ tự toàn cục.
Đáp án đúng: C

Câu 9. Vì sao multi-leader replication có thể gặp xung đột ghi?
A. Nhiều leader có thể cập nhật cùng một khóa đồng thời.
B. Mỗi leader luôn chờ majority của các leader khác.
C. Mỗi leader chỉ cho phép một client đọc dữ liệu.
D. Mỗi leader luôn giữ bản sao giống hệt tại mọi thời điểm.
Đáp án đúng: A

Câu 10. Lợi ích của CRDT phù hợp với bài toán hợp nhất bản sao là gì?
A. Phép gộp luôn giữ được mọi cập nhật như các log riêng.
B. Phép gộp yêu cầu một leader phê duyệt mọi thao tác.
C. Phép gộp loại bỏ nhu cầu lưu dữ liệu trên các replica.
D. Phép gộp được thiết kế để các bản sao hội tụ.
Đáp án đúng: D

Câu 11. Rủi ro của chính sách last-write-wins khi có ghi đồng thời là gì?
A. Mọi cập nhật được lưu thành nhiều phiên bản hiển thị.
B. Mọi cập nhật được hòa giải theo quan hệ nhân quả.
C. Mọi cập nhật phải được hai-phase commit xác nhận.
D. Một cập nhật có thể bị ghi đè do thứ tự timestamp.
Đáp án đúng: D

Câu 12. Vector clock hữu ích cho việc phân tích phiên bản bản sao thế nào?
A. Buộc đồng hồ vật lý của mọi node chạy đồng bộ tuyệt đối.
B. Phân biệt quan hệ nhân quả với các cập nhật đồng thời.
C. Tạo một thứ tự thời gian thực cho mọi client toàn cầu.
D. Tự chọn phiên bản thắng khi các cập nhật bị xung đột.
Đáp án đúng: B

Câu 13. Trong leaderless replication, thành phần nhận request thường làm gì?
A. Chuyển mọi ghi đến leader cố định duy nhất của hệ.
B. Phối hợp đọc ghi với nhiều replica theo consistency.
C. Yêu cầu follower sao chép dữ liệu trước khi nhận ghi.
D. Chỉ gửi request đến node sở hữu token nhỏ nhất.
Đáp án đúng: B

Câu 14. Với N replica, điều kiện R + W > N có ý nghĩa cơ bản nào?
A. Mọi bản ghi được lưu tại tất cả replica cùng lúc.
B. Mọi yêu cầu đọc phải chờ đủ N replica mới trả lời.
C. Tập replica phản hồi đọc và ghi phải có giao nhau.
D. Không thể gặp sự cố khi coordinator mất kết nối.
Đáp án đúng: C

Câu 15. Nếu N = 5, R = 3 và W = 3 trên cùng nhóm replica cố định, giao nhau tối thiểu bao nhiêu?
A. Ít nhất hai replica thuộc cả tập đọc và tập ghi.
B. Cả năm replica phải thuộc cả tập đọc và tập ghi.
C. Không replica nào bắt buộc nằm trong cả hai tập.
D. Hai quorum có ít nhất một replica trùng nhau.
Đáp án đúng: D

Câu 16. Vì sao chỉ có R + W > N chưa đủ để khẳng định mọi đọc đều linearizable?
A. Giao giữa quorum đọc và ghi sẽ luôn rỗng về mặt dữ liệu.
B. Vì R + W > N bắt buộc mọi replica phải phản hồi.
C. Vẫn cần quy tắc phiên bản và điều phối ghi đồng thời.
D. Vì mọi quorum đều chỉ đảm bảo eventual consistency.
Đáp án đúng: C

Câu 17. Trong sloppy quorum, node ngoài tập replica ưu tiên có thể được dùng để làm gì?
A. Trở thành leader vĩnh viễn và đổi luôn shard key.
B. Nhận bản ghi tạm khi replica ưu tiên không thể liên lạc.
C. Xóa tất cả dữ liệu trên replica ưu tiên đang offline.
D. Chặn mọi yêu cầu ghi cho đến khi mạng được khôi phục.
Đáp án đúng: B

Câu 18. Anti-entropy repair giữa các replica chủ yếu có nhiệm vụ nào?
A. Giảm replication factor mỗi khi một replica bị lỗi.
B. Đối chiếu và đồng bộ các bản sao còn sai khác.
C. Chuyển mọi câu SELECT sang một leader tập trung.
D. Tạo lại shard key từ log client sau mỗi lần đọc.
Đáp án đúng: B

Câu 19. Trong hệ có read repair, khi đọc thấy các replica trả dữ liệu lệch nhau thì sao?
A. Bản sao mới nhất phải bị xóa trước khi trả kết quả.
B. Yêu cầu đọc luôn bị từ chối dù quorum đã thỏa mãn.
C. Replication factor lập tức tăng trên toàn bộ cluster.
D. Sửa replica cũ nếu đọc phát hiện các bản sao lệch.
Đáp án đúng: D

Câu 20. Khi xảy ra network partition, ưu tiên linearizability có thể buộc hệ thống làm gì?
A. Chấp nhận mọi ghi ở cả hai phía mà không cần giải quyết.
B. Chỉ tăng số kết nối client để xử lý phân vùng mạng.
C. Chuyển mọi transaction tự động sang eventual consistency.
D. Từ chối một số yêu cầu khi không thể xác nhận an toàn.
Đáp án đúng: D

Câu 21. Trong định lý CAP, chữ C thường nói đến thuộc tính nào?
A. Linearizability: mỗi thao tác có vẻ diễn ra tức thời.
B. Eventual consistency: các replica hội tụ sau một lúc.
C. Causal consistency: các tác vụ quan hệ giữ đúng thứ tự.
D. Session consistency: đọc thấy ghi của riêng mình.
Đáp án đúng: A

Câu 22. Mô hình PACELC bổ sung điều gì vào góc nhìn của CAP?
A. Khi không partition, mọi hệ đều có consistency mạnh miễn phí.
B. Khi gặp partition, hệ luôn phải chọn giảm latency thay vì bỏ đọc.
C. Ngay cả khi không partition, còn đánh đổi latency và consistency.
D. Khi gặp partition, chỉ cần tăng replication factor để không bị lỗi.
Đáp án đúng: C

Câu 23. Eventual consistency có lời hứa cơ bản nào khi không có ghi mới?
A. Mọi thao tác đọc luôn nhìn thấy bản ghi mới nhất ngay.
B. Mọi replica phải cập nhật đồng thời trước khi trả lời client.
C. Replica hội tụ khi không có ghi mới và có đồng bộ.
D. Mọi giao dịch nhiều shard luôn commit nguyên tử.
Đáp án đúng: C

Câu 24. Read-your-writes consistency bảo đảm điều gì cho một client?
A. Đọc tiếp theo thấy các ghi trước của chính client đó.
B. Mọi client khác luôn thấy bản ghi mới nhất tức thì.
C. Mọi replica được đồng bộ trước khi client đầu tiên đọc.
D. Mọi transaction trong hệ có cùng một thứ tự toàn cục.
Đáp án đúng: A

Câu 25. Monotonic reads bảo đảm điều gì cho chuỗi đọc của một client?
A. Mọi lần đọc sẽ thấy tất cả ghi của client khác ngay.
B. Mỗi lần đọc đều phải thực hiện trên cùng một node vật lý.
C. Sau khi thấy phiên bản mới, không đọc lùi về bản cũ.
D. Mọi đọc đều khóa dữ liệu cho đến khi client ngắt kết nối.
Đáp án đúng: C

Câu 26. Causal consistency bảo đảm điều gì với hai sự kiện B phụ thuộc A?
A. B luôn được xác nhận trước A trên tất cả replica.
B. Hai sự kiện đồng thời phải được xếp theo đồng hồ hệ.
C. Nơi quan sát B phải có khả năng quan sát A trước.
D. Mỗi sự kiện chỉ được lưu trên một leader toàn cầu.
Đáp án đúng: C

Câu 27. Linearizability yêu cầu quan sát mỗi thao tác theo cách nào?
A. Thao tác có một điểm hiệu lực giữa gọi và trả.
B. Như xảy ra ở cùng thời điểm cho mọi replica vật lý.
C. Như giao dịch luôn chạy trên một node duy nhất.
D. Như mọi thao tác luôn có độ trễ giống nhau.
Đáp án đúng: A

Câu 28. Sequential consistency khác linearizability ở điểm quan trọng nào?
A. Thứ tự chung giữ trình tự client, không buộc real-time.
B. Giữ mọi thứ tự thời gian thực như linearizability.
C. Cho phép đảo thứ tự thao tác của một client bất kỳ.
D. Chỉ đảm bảo bản sao hội tụ nếu không còn ghi mới.
Đáp án đúng: A

Câu 29. Sharding dựa trên hash của shard key thường có lợi ích gì?
A. Giữ các khóa liền nhau trên cùng shard để quét khoảng.
B. Phân phối khóa lên shard để cân bằng tải tương đối.
C. Đảm bảo mọi yêu cầu ghi đều chạy một transaction chung.
D. Ngăn tuyệt đối các shard có khối lượng truy cập lệch.
Đáp án đúng: B

Câu 30. Một shard liên tục quá tải vì vài khóa được truy cập rất nhiều là vấn đề gì?
A. Replication lag khiến mọi shard luôn có lượng đọc bằng nhau.
B. Read repair buộc dữ liệu tự chuyển qua leader khác.
C. Hot key khiến tải lệch giữa các shard hoặc partition.
D. Quorum intersection tạo index tự động trên mọi shard.
Đáp án đúng: C

Câu 31. Range sharding với khóa tăng dần có đánh đổi nào phổ biến?
A. Quét theo khoảng chậm vì mọi khóa bị hash ngẫu nhiên.
B. Hỗ trợ quét khoảng nhưng ghi tăng dần dễ dồn tải.
C. Ghi được phân đều tuyệt đối dù khóa luôn tăng.
D. Không thể mở rộng shard nếu dữ liệu đã được lưu.
Đáp án đúng: B

Câu 32. Khi bổ sung shard mới, hoạt động rebalance thường cần làm gì?
A. Chỉ thay replication factor và không chuyển dữ liệu nào.
B. Thay tất cả transaction đang chạy thành giao dịch 2PC.
C. Chỉ thay tên shard để tăng tốc độ ghi dữ liệu.
D. Chuyển dữ liệu một phần và cập nhật tuyến định vị khóa.
Đáp án đúng: D

Câu 33. Đặc điểm nào khiến transaction trải qua nhiều shard phức tạp hơn?
A. Chỉ cần commit trên một shard bất kỳ rồi coi tất cả thành công.
B. Không shard nào cần kiểm tra xung đột khi chạy transaction.
C. Cần phối hợp quyết định commit giữa các shard tham gia.
D. Mọi ghi phân tán luôn được rollback tự động bằng replication.
Đáp án đúng: C

Câu 34. Với two-phase commit, coordinator hỏng khi participant đã prepare có thể gây gì?
A. Participant tự commit ngay dù chưa có quyết định cuối.
B. Participant có thể phải chờ để biết quyết định commit.
C. Participant tự xóa log prepare rồi bắt đầu giao dịch mới.
D. Participant chuyển transaction thành saga mà không cần app.
Đáp án đúng: B

Câu 35. Saga trong giao dịch phân tán thường xử lý một bước đã commit rồi phát sinh lỗi như thế nào?
A. Rollback tự động mọi database về cùng một snapshot tức thời.
B. Thực hiện bước bù theo nghiệp vụ cho công đoạn đã hoàn tất.
C. Khóa tất cả shard đến khi toàn bộ giao dịch Saga hoàn tất.
D. Bỏ qua lỗi và xác nhận thành công mọi công đoạn còn lại.
Đáp án đúng: B

Câu 36. Transactional outbox giúp giảm nguy cơ mất sự kiện khi ghi dữ liệu như thế nào?
A. Commit database và publish event ở hai thao tác độc lập.
B. Chỉ ghi message broker rồi bỏ qua ghi cơ sở dữ liệu.
C. Ghi bản ghi outbox cùng dữ liệu trong một transaction.
D. Đợi tất cả consumer xác nhận trước khi thực hiện INSERT.
Đáp án đúng: C

Câu 37. Trong hệ phân tán có retry sau timeout, idempotency key giúp điều gì?
A. Đảm bảo toàn bộ message đi qua mạng đúng một lần duy nhất.
B. Thay thế mọi transaction cần thiết trên các database.
C. Chặn mọi request đến khi network partition được xử lý.
D. Dùng khóa để nhận ra retry và tránh tác dụng phụ lặp.
Đáp án đúng: D

Câu 38. Change Data Capture (CDC) thường lấy dữ liệu sự kiện từ đâu?
A. Lấy mọi câu SELECT của người dùng rồi phát thành sự kiện.
B. Đọc thay đổi đã commit từ log hay cơ chế CDC của DB.
C. Đọc trạng thái RAM từ mọi ứng dụng mà không truy cập DB.
D. Thay toàn bộ dữ liệu database bằng message broker.
Đáp án đúng: B

Câu 39. Để phát hiện replica tụt hậu ảnh hưởng đến đọc, nên theo dõi nhóm tín hiệu nào?
A. Chỉ số lượng bảng, không cần độ trễ của replica.
B. Chỉ dung lượng index, không cần quan sát trạng thái log.
C. Chỉ tốc độ client gửi request đến leader hiện tại.
D. Độ trễ replication, lỗi đồng bộ và độ tuổi bản sao.
Đáp án đúng: D

Câu 40. Trong kế hoạch disaster recovery, RPO và RTO khác nhau thế nào?
A. RPO giới hạn mất dữ liệu; RTO giới hạn thời gian khôi phục.
B. RPO chỉ độ trễ đọc; RTO chỉ số replica cần để ghi.
C. RPO là số shard; RTO là số partition trong một shard.
D. RPO là số leader; RTO là số lần bầu lại leader.
Đáp án đúng: A
