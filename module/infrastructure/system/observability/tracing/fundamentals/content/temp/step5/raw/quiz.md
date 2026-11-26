1. Trong distributed tracing, mô tả nào phân biệt trace và span chính xác nhất?
A. Trace gom các span của một request; span mô tả một đơn vị công việc.
B. Trace là một sự kiện đơn lẻ; span là bản ghi log được gắn với cùng request.
C. Trace lưu số liệu tổng hợp; span biểu diễn trạng thái hiện tại của một service.
D. Trace định danh một service; span là tên endpoint được gọi trong ứng dụng.
Đáp án đúng: A

2. Khi service con tạo span cho lời gọi nhận từ service cha, quan hệ nào cần được giữ?
A. Span con dùng cùng trace ID và tham chiếu span cha bằng parent span ID.
B. Span con tạo trace ID mới rồi ghi trace ID cha vào baggage của request.
C. Span con sao chép span ID của cha để backend tự suy ra quan hệ phân cấp.
D. Span con chỉ lưu tên service cha, không cần context định danh của lời gọi.
Đáp án đúng: A

3. Cách phổ biến để truyền trace context qua một lời gọi HTTP tới service tiếp theo là gì?
A. Ghi trace ID vào log và để service nhận ghép các request theo timestamp.
B. Đưa span ID vào query string để gateway tạo trace mới ở mỗi chặng.
C. Gửi trace context trong body JSON mà không cần inject vào request headers.
D. Inject và extract W3C Trace Context qua header traceparent của request.
Đáp án đúng: D

4. Phát biểu nào mô tả đúng vai trò của trace ID và span ID?
A. Trace ID thay đổi theo từng span; span ID được dùng chung trong cả trace.
B. Trace ID nhận diện service; span ID nhận diện request đi vào gateway.
C. Các span trong cùng trace dùng chung trace ID; mỗi span có span ID riêng.
D. Trace ID chỉ được tạo khi export; span ID chỉ được tạo tại backend nhận.
Đáp án đúng: C

5. Một tác vụ bất đồng bộ được kích hoạt bởi nhiều message độc lập cần liên kết với các context nguồn. Nên dùng cách nào?
A. Đặt tất cả message dưới span cha của message đầu tiên trong batch, bỏ các context còn lại.
B. Tạo một trace ID mới rồi bỏ các context đã được truyền từ message.
C. Sao chép span ID của message đầu tiên vào mọi span xử lý message.
D. Tạo span xử lý và thêm span link tới từng context nguồn liên quan.
Đáp án đúng: D

6. Khi dùng baggage để truyền metadata qua nhiều service, lựa chọn nào phù hợp nhất?
A. Đưa toàn bộ request body và credential vào baggage để downstream dùng lại.
B. Chỉ truyền metadata nhỏ, không nhạy cảm và thực sự cần cho downstream.
C. Dùng baggage thay trace ID và span ID để giảm số header cần gửi.
D. Lưu trạng thái nghiệp vụ dài hạn vào baggage để các service cùng cập nhật.
Đáp án đúng: B

7. Với ứng dụng có nhiều replica và pod thay đổi sau mỗi lần rollout, giá trị service.name nên đại diện cho điều gì?
A. Tên pod cụ thể đang xử lý request để phân biệt từng replica sau rollout.
B. Địa chỉ IP của instance để phân biệt các lần khởi động.
C. Tên logic ổn định của dịch vụ qua các replica và lần triển khai.
D. URL đầy đủ của route đang được gọi trong request hiện tại.
Đáp án đúng: C

8. Trong một lời gọi HTTP đồng bộ giữa hai service, cách gán span kind nào đúng?
A. Span phía nhận là CLIENT; span phía gọi là SERVER.
B. Span phía nhận là SERVER; span phía gọi là CLIENT.
C. Cả hai span đều là INTERNAL vì cùng thuộc một trace.
D. Span phía nhận là PRODUCER; span phía gọi là CONSUMER.
Đáp án đúng: B

9. Span event phù hợp nhất để biểu diễn loại thông tin nào?
A. Một công việc có start time và end time riêng trong trace.
B. Thuộc tính chung được kế thừa bởi mọi span của resource.
C. Một mẫu đo được tổng hợp vào histogram của service.
D. Một ghi chú có timestamp xảy ra bên trong vòng đời span.
Đáp án đúng: D

10. Một API trả HTTP 200 nhưng nghiệp vụ thất bại do không thể ghi giao dịch. Instrumentation nên xử lý thế nào?
A. Đánh giá kết quả nghiệp vụ và đặt span status ERROR cho thao tác thất bại.
B. Đặt mọi span có HTTP status 200 thành OK, ngay cả khi nghiệp vụ ghi giao dịch thất bại.
C. Chỉ đánh dấu ERROR khi transport trả về mã HTTP từ 500 trở lên.
D. Để backend suy luận trạng thái từ message log sau khi nhận trace.
Đáp án đúng: A

11. Một request tạo hai server span gần giống nhau sau khi bật cả Java agent và SDK instrumentation. Cách xử lý phù hợp là gì?
A. Tăng sampling rate để backend có thêm dữ liệu phân biệt hai span.
B. Đổi tên hai span theo service để dashboard không gộp chúng.
C. Loại bỏ instrumentation chồng lặp và chọn một nguồn tạo span.
D. Tắt exporter để backend chỉ nhận span do ứng dụng tự ghi.
Đáp án đúng: C

12. Khi nhiều team cần truy vấn HTTP spans nhất quán, nên chuẩn hóa dữ liệu theo cách nào?
A. Đưa mọi thuộc tính vào span name để truy vấn bằng một trường.
B. Tự đặt tên attribute riêng cho từng service để tránh trùng khóa giữa các team.
C. Áp dụng semantic conventions và thống nhất phiên bản thuộc tính.
D. Ghi metadata của service vào event cuối cùng trong mỗi trace.
Đáp án đúng: C

13. Đặc điểm chính của head sampling là gì?
A. Quyết định lấy mẫu sớm khi trace bắt đầu, trước khi biết kết quả cuối.
B. Chờ toàn bộ spans hoàn tất rồi mới chọn trace dựa trên lỗi hoặc độ trễ.
C. Đọc status cuối từ backend rồi xóa các trace không cần lưu.
D. Chỉ lấy mẫu những span có duration vượt ngưỡng sau khi export.
Đáp án đúng: A

14. Muốn tail sampling đánh giá đầy đủ các spans của cùng một trace, collector cần điều gì?
A. Phân phối ngẫu nhiên từng span tới các replica để tăng throughput.
B. Chia spans theo service name để mỗi service tự quyết định lấy mẫu.
C. Gửi bản sao của mọi span tới tất cả collector đang hoạt động.
D. Định tuyến các span cùng trace ID tới cùng một sampler instance.
Đáp án đúng: D

15. Trong tail sampling, decision_wait chủ yếu được dùng để làm gì?
A. Giữ trace đã lưu trong backend thêm một khoảng trước khi xóa.
B. Trì hoãn gửi request OTLP để giảm số kết nối mà collector phải xử lý.
C. Chờ ứng dụng gửi lại mọi span bị mất trước khi ghi vào queue.
D. Đệm spans theo trace một khoảng thời gian trước khi đánh giá policy.
Đáp án đúng: D

16. Hệ thống dùng head sampling 1% thường bỏ sót các lỗi hiếm. Cách nào giúp ưu tiên giữ trace lỗi?
A. Giảm tỷ lệ sampling tại SDK để dành thêm tài nguyên cho các request khác.
B. Bỏ head sampling loại sớm và dùng tail sampling sau khi Collector nhận đủ spans.
C. Chỉ lấy mẫu root span rồi suy ra lỗi của các service downstream.
D. Tăng thời gian lưu trace đã được lấy mẫu trong backend hiện tại.
Đáp án đúng: B

17. Parent-based sampler thường quyết định sampling cho trace mới như thế nào?
A. Dùng root sampler cho trace mới và tôn trọng sampled flag của parent.
B. Luôn lấy mẫu mọi span con dù parent context có sampled flag nào.
C. Chọn sampling độc lập cho từng span để tăng độ đa dạng dữ liệu.
D. Chờ backend xác nhận trace ID rồi mới áp dụng quyết định của parent.
Đáp án đúng: A

18. Một job Java chạy ngắn kết thúc ngay sau khi xử lý xong nhưng thiếu spans cuối. Biện pháp nào phù hợp?
A. Tắt BatchSpanProcessor để mọi span được giữ trong heap lâu hơn.
B. Flush hoặc shutdown SDK có kiểm soát trước khi tiến trình thoát.
C. Tăng sampling rate để exporter gửi nhiều bản sao của mỗi span.
D. Tạo trace ID mới trong shutdown hook để gửi phần dữ liệu còn lại.
Đáp án đúng: B

19. SDK gửi OTLP gRPC nhưng Collector chỉ mở receiver OTLP HTTP. Cách khắc phục đúng là gì?
A. Cấu hình cùng protocol và endpoint tương ứng ở SDK hoặc receiver.
B. Đổi trace ID sang định dạng khác để receiver nhận diện giao thức.
C. Tăng batch size để gộp request gRPC thành payload HTTP lớn hơn.
D. Bật sampling tại SDK để giảm số request tới receiver hiện tại.
Đáp án đúng: A

20. Exporter queue tăng liên tục khi backend tracing chậm. Cách xử lý nào phù hợp nhất?
A. Bỏ mọi giới hạn queue để giữ tất cả spans cho tới khi backend hồi phục.
B. Tắt retry để collector giải phóng tài nguyên ngay khi gặp lỗi đầu tiên.
C. Tăng sampling vô điều kiện để exporter gửi thêm dữ liệu dự phòng.
D. Dùng queue hữu hạn, retry có backoff và theo dõi dữ liệu bị drop.
Đáp án đúng: D

21. Một Collector có hai pipeline độc lập cùng export traces, cả hai đều phải loại bỏ dữ liệu nhạy cảm. Cấu hình nào đúng?
A. Chỉ đặt redaction trong pipeline đầu vì hai pipeline dùng chung receiver.
B. Áp dụng redaction trong từng pipeline trước khi dữ liệu tới exporter.
C. Chỉ che dữ liệu ở giao diện backend sau khi cả hai pipeline gửi xong.
D. Chỉ lọc trace ID tại receiver để backend không thể tìm span nhạy cảm.
Đáp án đúng: B

22. Trong pipeline Collector có memory_limiter, transform và batch processor, thứ tự nào thường phù hợp?
A. Đặt memory_limiter đầu pipeline, xử lý transform rồi batch gần cuối.
B. Đặt batch đầu pipeline, memory_limiter sau exporter và transform cuối.
C. Đặt transform sau exporter, batch trước receiver và bỏ memory_limiter.
D. Đặt memory_limiter cuối pipeline để chỉ kiểm tra sau khi gửi dữ liệu.
Đáp án đúng: A

23. Callback chạy trên ExecutorService riêng bị mất parent context. Cách khắc phục phù hợp là gì?
A. Lưu trace ID vào biến static để mọi worker cùng đọc một giá trị.
B. Tạo một trace độc lập cho mỗi callback và ghép theo timestamp sau đó.
C. Capture context khi submit task rồi khôi phục scope khi thực thi callback.
D. Chuyển mọi callback về thread gọi ban đầu để không cần truyền context.
Đáp án đúng: C

24. Ứng dụng dùng thread pool và MDC để đưa trace_id vào log. Làm gì để tránh context cũ lọt sang request kế tiếp?
A. Giữ MDC sau request để worker có thể tái sử dụng trace ID gần nhất.
B. Ghi trace_id vào tên thread để logger tự nhận diện request hiện tại.
C. Chỉ cập nhật MDC khi request có lỗi để giảm chi phí ghi log.
D. Đặt context theo request và dọn MDC trong khối finally khi kết thúc.
Đáp án đúng: D

25. Trong ứng dụng Reactor, cách nào phù hợp để giữ trace context qua scheduler switch?
A. Dựa hoàn toàn vào ThreadLocal vì mỗi signal luôn chạy trên một thread.
B. Tạo trace mới sau mỗi publishOn để context không cần được truyền.
C. Dùng cơ chế context propagation tương thích Reactor Context và instrumentation.
D. Chỉ truyền trace ID qua biến toàn cục để mọi operator cùng đọc.
Đáp án đúng: C

26. Producer gửi message Kafka và consumer cần tiếp tục cùng trace. Context nên được truyền ở đâu?
A. Inject trace context vào message headers và extract tại consumer.
B. Ghi trace ID vào tên topic để consumer tự suy ra parent span.
C. Đưa span ID vào partition key và dùng key đó làm trace ID mới.
D. Lưu trace context trong log producer rồi tìm lại bằng timestamp.
Đáp án đúng: A

27. Consumer nhận một batch gồm message thuộc nhiều trace khác nhau. Cách xử lý nào giữ đúng tương quan?
A. Giữ context riêng từng message và tạo span xử lý phù hợp cho từng message.
B. Dùng context của message đầu tiên làm parent cho toàn bộ batch.
C. Gán cùng một trace ID mới cho mọi message trong batch hiện tại.
D. Bỏ context của message và chỉ ghi batch ID vào resource attributes.
Đáp án đúng: A

28. Một HTTP client retry cùng thao tác nhiều lần trong một request. Cách instrumentation nào hữu ích nhất?
A. Gộp mọi lần thử vào một span và chỉ ghi thời gian của lần cuối.
B. Tạo span riêng cho từng attempt dưới operation span và ghi attempt metadata.
C. Tạo một trace mới cho mỗi attempt rồi bỏ liên kết với request ban đầu.
D. Ghi retry count vào service.name để có thể nhóm các request cùng loại.
Đáp án đúng: B

29. Span database chậm nhưng chưa rõ do chờ connection pool hay thực thi SQL. Nên bổ sung điều gì?
A. Ghi tổng thời gian request vào service.name để so sánh các lần gọi.
B. Đo số lượng trace được lấy mẫu trong khoảng thời gian query chạy.
C. Thêm toàn bộ SQL parameters vào span để backend tự suy ra thời gian.
D. Tách thời gian lấy connection khỏi thời gian thực thi câu truy vấn.
Đáp án đúng: D

30. Một service gọi song song ba backend và cần tìm dependency làm p99 tăng. Cách tạo spans nào phù hợp?
A. Dùng một span chung cho cả fan-out và chỉ ghi backend chậm nhất.
B. Tạo một root trace riêng cho mỗi backend rồi ghép bằng timestamp.
C. Tạo client span riêng cho từng lời gọi dưới cùng context request.
D. Ghi tên ba backend vào một event khi request đã hoàn tất.
Đáp án đúng: C

31. Cách nào liên kết một điểm đo latency trong histogram với trace mẫu mà không tạo label riêng cho mỗi request?
A. Đưa trace ID vào metric name để mỗi request có một metric mới.
B. Gắn span ID làm label thường trực cho mọi time series của histogram.
C. Dùng exemplar chứa trace context tham chiếu tới một trace mẫu.
D. Sao chép toàn bộ span attributes vào label của metric quan sát.
Đáp án đúng: C

32. Vì sao không nên dùng trace ID làm metric label cho từng request?
A. Trace ID chỉ hợp lệ trong log và không thể xuất hiện trong metric.
B. Mỗi trace ID tạo series riêng, làm cardinality tăng rất nhanh.
C. Metric backend tự thay trace ID bằng span ID khi scrape dữ liệu.
D. Trace ID làm mất timestamp của mẫu đo trong histogram hiện tại.
Đáp án đúng: B

33. Khi ước lượng p99 từ trace được lấy mẫu xác suất, cần lưu ý điều gì?
A. p99 từ trace luôn bằng p99 của toàn bộ request nếu trace ID hợp lệ.
B. Tăng retention sẽ tự loại bỏ sai lệch do các request hiếm bị bỏ.
C. Dùng span có duration lớn nhất thay cho phân phối request đầy đủ.
D. Mẫu có thể thiếu request hiếm; cần thận trọng khi suy ra percentile tổng thể.
Đáp án đúng: D

34. Span database cần hỗ trợ điều tra loại truy vấn nhưng có thể chứa dữ liệu cá nhân. Nên ghi gì?
A. Lưu nguyên SQL cùng mọi bind parameter để không mất ngữ cảnh.
B. Loại hoặc che literal nhạy cảm và giữ thông tin cấu trúc cần thiết.
C. Mã hóa SQL bằng Base64 rồi gửi nguyên chuỗi sang backend tracing.
D. Đưa query và dữ liệu khách hàng vào baggage để service khác tra cứu.
Đáp án đúng: B

35. Một Collector nhận tenant ID từ header do client tự gửi. Cách bảo vệ tenant isolation phù hợp là gì?
A. Tin tenant ID trong baggage vì trace context đã được chuẩn hóa.
B. Xác thực danh tính ở ranh giới tin cậy và gắn tenant từ nguồn đáng tin.
C. Cho phép client chọn tenant rồi chỉ ẩn tenant ID trong dashboard.
D. Dùng service.name thay tenant ID để backend tự phân chia dữ liệu.
Đáp án đúng: B

36. Muốn phát hiện sớm trace propagation bị đứt sau một lần deploy, nên kiểm tra gì?
A. Chỉ xác nhận process của ứng dụng và Collector đều đang chạy.
B. Đếm root span ở gateway mà không cần truy vấn backend tracing.
C. Gửi canary request xuyên các service và xác minh các span bắt buộc.
D. Kiểm tra số log ứng dụng tăng lên sau khi rollout phiên bản mới.
Đáp án đúng: C
