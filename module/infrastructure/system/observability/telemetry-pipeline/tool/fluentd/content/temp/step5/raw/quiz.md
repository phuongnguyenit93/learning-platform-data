1. Trong Fluentd, `pos_file` của input `tail` chủ yếu dùng để làm gì?
A. Lưu các chunk chưa gửi để output có thể retry khi backend lỗi.
B. Lưu tag đã gán cho từng record để match không phải tính lại.
C. Lưu schema parser đã tải để tránh đọc cấu hình mỗi lần.
D. Lưu offset đã đọc của file để tiếp tục tail sau restart.
Đáp án đúng: D

2. Một agent gửi event tới `<source @type forward>`. Mô tả nào đúng về luồng nhận này?
A. Forward chỉ nhận HTTP JSON, còn TCP phải dùng input riêng.
B. Forward đọc file từ agent qua shared volume và đồng bộ offset.
C. Dùng Fluent Forward qua TCP, có thể bật xác thực và TLS.
D. Forward dùng UDP để giảm độ trễ và không cần xác nhận từ receiver.
Đáp án đúng: C

3. Sau log rotation, Fluentd tail file mới nhưng bỏ sót một số dòng đầu. Cấu hình nào hỗ trợ theo dõi file theo inode?
A. Bật `read_from_head` mà không cần theo dõi vị trí file.
B. Bật `follow_inodes` và giữ `pos_file` ổn định cho input tail.
C. Tăng `flush_interval` để output đọc lại các dòng chưa gửi.
D. Đổi tag theo tên file để Fluentd nhận diện inode mới.
Đáp án đúng: B

4. Cách phù hợp để gom stack trace Java nhiều dòng từ file log bằng Fluentd là gì?
A. Dùng multiline parser ở tail input để nhận diện dòng đầu.
B. Dùng grep filter để nối mọi record có cùng severity ERROR.
C. Dùng JSON parser để tự ghép các dòng tiếp theo thành object.
D. Dùng rewrite_tag_filter để đưa từng dòng vào cùng một tag.
Đáp án đúng: A

5. Một filter parser giải mã trường `log` nhưng cần giữ lại `container_id` và `stream` ban đầu. Nên bật tùy chọn nào?
A. `reserve_time true` để tự động giữ mọi trường record ban đầu.
B. `emit_invalid_record_to_error false` để chặn việc xóa metadata.
C. `remove_key_name_field true` để bảo toàn metadata nguồn đầu vào.
D. Bật `reserve_data true` để giữ các trường gốc.
Đáp án đúng: D

6. Parser filter gặp một record JSON không hợp lệ. Cách nào giúp chuyển record lỗi sang luồng xử lý riêng?
A. Tăng `flush_thread_count` để parser thử lại record lỗi.
B. Bật `reserve_data` và gửi mọi record lỗi vào output chính.
C. Bật `emit_invalid_record_to_error` và route qua `@ERROR`.
D. Đổi tag của toàn bộ source sang `@ERROR` trước khi parse.
Đáp án đúng: C

7. Một pipeline cần chuẩn hóa trường `severity` trước khi lọc riêng event ERROR. Thứ tự filter nào hợp lý?
A. Lọc theo severity trước, sau đó mới tạo trường severity chuẩn.
B. Chuẩn hóa severity trước, rồi lọc theo giá trị chuẩn.
C. Gửi event tới output trước, rồi dùng filter sửa record đã gửi.
D. Đổi tag sau output để filter phía trước nhận lại record.
Đáp án đúng: B

8. Trong Fluentd, khi một event khớp nhiều `<match>` pattern, quy tắc cấu hình nào cần lưu ý?
A. Mọi match đều chạy theo thứ tự và tự động nhân bản event sang output.
B. Đặt match cụ thể trước pattern rộng vì rule đầu tiên được chọn.
C. Fluentd chọn match có số ký tự pattern dài nhất bất kể vị trí.
D. Match rộng nên đặt trước để Fluentd thử tất cả rule rồi chọn tốt nhất.
Đáp án đúng: B

9. Khi nào nên dùng `rewrite_tag_filter` trong pipeline Fluentd?
A. Đổi tag theo nội dung record để event đi vào route khác.
B. Lưu offset file tail sau mỗi lần flush thành công.
C. Đổi một field trong record nhưng giữ nguyên tag hiện tại.
D. Sao chép event sang nhiều output cùng lúc mà không đổi route.
Đáp án đúng: A

10. Vai trò chính của `<label>` trong cấu hình Fluentd là gì?
A. Tạo một parser dùng chung để giải mã mọi input trong tiến trình.
B. Tạo một buffer vật lý độc lập mà không cần cấu hình output.
C. Tạo một worker riêng cho mỗi tag mà không cần giới hạn tài nguyên.
D. Gom filter và output trong một vùng routing riêng.
Đáp án đúng: D

11. Một event cần được gửi đồng thời tới Elasticsearch và object storage. Plugin nào phù hợp?
A. Dùng filter `grep` để gửi cùng event tới các backend khác nhau.
B. Dùng output `copy` để fan-out event tới nhiều đích.
C. Dùng input `forward` để tự động ghi dữ liệu vào hai output.
D. Dùng output `null` để nhân bản event trước khi lưu trữ.
Đáp án đúng: B

12. Khi cần giữ chunk qua lần Fluentd restart, loại buffer nào thường phù hợp hơn?
A. File buffer trên volume bền vững có quyền ghi.
B. Buffer tạm trong filesystem container để khôi phục sau restart.
C. Memory buffer với giới hạn heap lớn hơn lượng log dự kiến.
D. Buffer không giới hạn trên RAM để tránh ghi dữ liệu ra đĩa.
Đáp án đúng: A

13. Vì sao dùng field có cardinality rất cao làm chunk key có thể gây vấn đề?
A. Nó buộc mọi event dùng chung một chunk lớn và giảm phân mảnh.
B. Nó tạo nhiều chunk nhỏ, tăng metadata và áp lực buffer.
C. Nó làm parser bỏ qua tag và không còn nhận diện được input.
D. Nó tự động chuyển file buffer thành memory buffer khi flush.
Đáp án đúng: B

14. Khi file buffer đạt giới hạn và mục tiêu là tạo backpressure lên nguồn gửi, lựa chọn nào phù hợp?
A. Dùng `overflow_action throw_exception` để bỏ qua trạng thái buffer.
B. Tăng `flush_interval` để buffer tự nhận thêm event khi đầy.
C. Dùng `overflow_action drop_oldest_chunk` để giữ mọi event mới.
D. Chọn `overflow_action block` để chặn thêm event khi đầy.
Đáp án đúng: D

15. Backend tạm thời trả 503 và nhiều agent cùng retry. Cấu hình nào giúp giảm retry storm?
A. Dùng exponential backoff kèm jitter để giãn thời điểm retry.
B. Tăng số worker retry mà không giới hạn số request đồng thời.
C. Dùng retry interval cố định rất ngắn để thử lại đồng thời.
D. Tắt retry và xóa chunk ngay khi output nhận lỗi kết nối.
Đáp án đúng: A

16. Trong output có cấu hình `secondary`, mục đích chính thường là gì?
A. Chia đều mọi event sang hai output để tăng gấp đôi throughput.
B. Parse lại record sau khi output chính đã ghi thành công vào backend.
C. Dùng đích dự phòng khi output chính hết thời hạn retry.
D. Thay thế buffer chính bằng bộ nhớ RAM khi backend chậm.
Đáp án đúng: C

17. Vì sao cơ chế retry có thể làm một event xuất hiện trùng ở backend?
A. Buffer file tự nhân đôi chunk sau mỗi lần flush thành công.
B. Backend ghi event nhưng ACK bị mất nên Fluentd gửi lại chunk.
C. Tag thay đổi sau output khiến backend tự sao chép document.
D. Fluentd luôn tạo event mới mỗi lần parser đọc lại cùng một dòng.
Đáp án đúng: B

18. Một Fluentd DaemonSet có nhiều input `tail`. Cách quản lý vị trí đọc nào an toàn hơn?
A. Lưu offset trong tag để output tự khôi phục vị trí file.
B. Dùng một `pos_file` chung cho mọi input để gom offset toàn node.
C. Không dùng `pos_file` và luôn đọc từ đầu sau mỗi lần restart.
D. Dùng `pos_file` riêng và ổn định cho mỗi tail input.
Đáp án đúng: D

19. Filter Kubernetes metadata cần truy vấn thông tin Pod từ API server. Quyền nào nên được cấp?
A. RBAC get/list/watch Pod và namespace cần enrichment.
B. Cluster-admin cho mọi Fluentd Pod để tránh lỗi truy vấn metadata.
C. Quyền sửa Deployment và Secret trên mọi namespace của cluster.
D. Quyền tạo Node và xóa Pod để đồng bộ metadata hai chiều.
Đáp án đúng: A

20. Log container có tiền tố CRI gồm timestamp, stream và flag trước payload ứng dụng. Nên xử lý thế nào?
A. Parse lớp CRI trước, rồi parse payload theo định dạng ứng dụng.
B. Dùng multiline để ghép tất cả stdout và stderr thành một record.
C. Bỏ tiền tố bằng grep rồi chuyển phần còn lại thẳng tới output.
D. Parse payload JSON trực tiếp và giữ nguyên tiền tố CRI trong message.
Đáp án đúng: A

21. Trong Fluentd, `monitor_agent` thường được dùng để làm gì?
A. Đẩy log đã chuẩn hóa tới Elasticsearch mà không cần output plugin.
B. Nhận log ứng dụng qua HTTP rồi tự ghi vào file buffer mặc định.
C. Cung cấp endpoint thông tin nội bộ về Fluentd và plugin.
D. Tự động phát hiện mọi lỗi parse và sửa cấu hình parser tương ứng.
Đáp án đúng: C

22. Chỉ số nào là dấu hiệu trực tiếp cho thấy output đang chậm và backlog tăng?
A. Queued chunks và buffer bytes tăng khi tốc độ flush hụt lại.
B. Số lượng tag ổn định và số worker không đổi qua các lần deploy.
C. CPU giảm nhẹ trong khi số record nhận vào vẫn giữ nguyên.
D. Số file cấu hình không đổi và tiến trình vẫn trả health check.
Đáp án đúng: A

23. Tăng `flush_thread_count` có tác động nào cần cân nhắc?
A. Làm tăng tốc độ đọc file tail nhưng không ảnh hưởng output plugin.
B. Thay thế retry policy và tự giải phóng các chunk đang bị kẹt.
C. Luôn giảm latency mà không làm thay đổi số request tới backend.
D. Tăng flush song song có thể tăng tải backend và tài nguyên.
Đáp án đúng: D

24. `flush_interval` và `timekey` trong buffer khác nhau chủ yếu ở điểm nào?
A. Flush interval xác định vị trí đọc file; timekey lưu offset của tail input.
B. Flush interval phân nhóm theo tag; timekey điều khiển số thread gửi output.
C. Flush interval đặt nhịp flush; timekey chia chunk theo thời gian.
D. Flush interval đặt thời gian retry; timekey đặt thời hạn kết nối tới backend.
Đáp án đúng: C

25. Kiến trúc nào phù hợp khi cần thu log file cục bộ trên từng Kubernetes node rồi gom về một nơi?
A. Dùng DaemonSet trên node và aggregator nhận Forward từ agent.
B. Một Pod đơn đọc trực tiếp mọi filesystem node mà không cần mount.
C. Một Deployment đọc log container qua API server thay cho node agent.
D. Một StatefulSet tạo một Fluentd process cho từng namespace ứng dụng.
Đáp án đúng: A

26. Fluentd aggregator trong Kubernetes cần giữ file buffer qua Pod replacement. Nên lưu buffer ở đâu?
A. Trong emptyDir để buffer luôn còn sau khi Pod bị xóa hoàn toàn.
B. Trong ConfigMap để chunk được đồng bộ như cấu hình bất biến.
C. Trong writable layer của container để Kubernetes tự phục hồi dữ liệu.
D. Trên volume bền vững được mount và cấp quyền ghi cho Fluentd.
Đáp án đúng: D

27. Backend output ngừng hoạt động tạm thời nhưng Fluentd vẫn nhận event và buffer còn chỗ. Probe nên được thiết kế thế nào?
A. Restart Fluentd theo chu kỳ ngắn để xóa retry state trước mỗi lần flush.
B. Không để liveness phụ thuộc backend lỗi tạm thời khi buffer còn chỗ.
C. Làm liveness thất bại ngay khi output retry để Kubernetes thay Pod.
D. Tắt readiness và liveness vĩnh viễn để giữ mọi Pod luôn Running.
Đáp án đúng: B

28. Hai nguồn log của ứng dụng lần lượt ghi JSON một dòng và stack trace nhiều dòng. Cách cấu hình nào hợp lý?
A. Dùng một multiline rule chung cho mọi dòng để giữ nguyên thứ tự.
B. Chuyển toàn bộ stdout thành text rồi bỏ parser JSON hiện có.
C. Dùng JSON parser cho nguồn dòng đơn, multiline parser cho stack trace.
D. Dùng rewrite tag để tự ghép các dòng có timestamp gần nhau.
Đáp án đúng: C

29. Một tail input không thu được log sau khi node nâng cấp container runtime. Bước kiểm tra đầu tiên phù hợp là gì?
A. Kiểm tra đường dẫn log thực tế và hostPath mount trên node.
B. Xóa pos_file để Fluentd tự tìm mọi file log trên toàn host.
C. Tăng retry của output vì runtime mới có thể làm backend chậm.
D. Tăng số worker để input tail quét thêm các thư mục mặc định.
Đáp án đúng: A

30. Fluentd báo parse error tăng sau khi ứng dụng thay schema JSON. Cách xử lý an toàn là gì?
A. Đổi tag lỗi thành tag production để backend tiếp tục nhận dữ liệu.
B. Drop toàn bộ record lỗi ngay để giữ output chính luôn sạch.
C. Nới regex tới mức chấp nhận mọi chuỗi và bỏ kiểm tra schema.
D. Đưa record lỗi vào luồng riêng, kiểm tra mẫu rồi sửa parser.
Đáp án đúng: D

31. Một filter cần che token trong JSON lồng nhau trước khi gửi tới nhiều output. Nguyên tắc nào quan trọng nhất?
A. Chỉ che trường hiển thị trên dashboard vì backend không truy cập raw.
B. Che token ở một output chính và giả định copy output dùng chung kết quả.
C. Chỉ lọc tên field cấp cao vì nested payload không được index.
D. Làm sạch record trước fan-out và kiểm tra mọi nhánh nhận dữ liệu.
Đáp án đúng: D

32. Khi output backend trả 429, cách nào giúp Fluentd phục hồi mà không khuếch đại tải?
A. Gửi lại chunk liên tục với số worker tối đa để vượt giới hạn rate.
B. Tắt buffer và gửi trực tiếp từ input để giảm độ trễ nội bộ.
C. Giữ chunk và retry theo backoff phù hợp với giới hạn backend.
D. Xóa chunk ngay để giảm queue và chờ backend tự đồng bộ dữ liệu.
Đáp án đúng: C

33. Một filter grep loại event không có trường `status`, vô tình làm mất audit log. Cách sửa nào hợp lý?
A. Chuyển toàn bộ audit log sang input khác mà không sửa điều kiện.
B. Chỉ lọc access log có trường status, giữ nguyên loại event khác.
C. Đổi điều kiện thành loại mọi record không có status để nhất quán.
D. Gán status mặc định 200 cho mọi record trước khi áp grep filter.
Đáp án đúng: B

34. Vì sao parser JSON thường phù hợp hơn regex tổng quát với log JSON có cấu trúc?
A. Regex luôn bỏ qua nested object nên không thể dùng cho bất kỳ log nào.
B. Parser JSON tự động sửa mọi schema sai và suy ra field bị thiếu.
C. JSON parser hiểu object lồng nhau và kiểu dữ liệu mà không cần tách field bằng regex.
D. Regex không hỗ trợ ký tự Unicode nên mọi JSON cần parser riêng.
Đáp án đúng: C

35. Sau restart Fluentd, một số log cũ bị gửi lại. Nguyên nhân nào cần kiểm tra trước?
A. Tag của record có chứa ngày giờ theo định dạng UTC hay không.
B. Số flush thread có lớn hơn số CPU trên node hay không.
C. Kiểm tra `pos_file` bền vững và offset được cập nhật đúng.
D. Số lượng output plugin có giảm trong lần khởi động trước hay không.
Đáp án đúng: C

36. Muốn xác định log bị mất ở input, filter, routing, buffer hay output, cách kiểm tra nào hữu ích nhất?
A. Xóa buffer hiện tại rồi xem liệu các event mới có tới backend không.
B. Đối chiếu số event và lỗi từ nguồn qua từng chặng tới backend.
C. Chỉ kiểm tra trạng thái process Fluentd và cổng health của Pod.
D. Chỉ so sánh CPU Fluentd trước và sau khi log không xuất hiện.
Đáp án đúng: B
