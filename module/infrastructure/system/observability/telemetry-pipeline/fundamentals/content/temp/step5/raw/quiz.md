1. Một pipeline traces trong OpenTelemetry Collector thực thi các thành phần theo thứ tự nào?
A. Receivers gửi thẳng tới exporters, còn processors chạy sau khi export.
B. Processors nhận dữ liệu trước, rồi receivers và exporters xử lý đầu ra.
C. Exporters nhận dữ liệu, receivers chuẩn hóa, rồi processors lưu trữ.
D. Receivers nhận dữ liệu, processors xử lý, rồi exporters gửi đi.
Đáp án đúng: D

2. Vai trò chính của receiver trong một pipeline Collector là gì?
A. Gom batch và retry khi backend đích tạm thời không sẵn sàng.
B. Nhận telemetry từ nguồn theo giao thức cấu hình.
C. Định tuyến telemetry sang pipeline khác theo thuộc tính của record.
D. Chuẩn hóa thuộc tính và loại bỏ những record không đáp ứng chính sách.
Đáp án đúng: B

3. Mô hình agent kết hợp gateway thường đem lại lợi ích kiến trúc nào?
A. Mọi ứng dụng gửi trực tiếp tới mọi backend để tránh điểm tập trung.
B. Gateway thay thế instrumentation nên ứng dụng không cần tạo telemetry.
C. Agent thu gần workload, gateway tập trung xử lý và định tuyến.
D. Agent chỉ lưu dữ liệu cục bộ, gateway chỉ phục vụ truy vấn dashboard.
Đáp án đúng: C

4. Vì sao filelog receiver nên lưu checkpoint bằng storage bền vững?
A. Để giữ thứ tự log toàn cụm khi nhiều agent cùng đọc một file.
B. Để tự động nén mọi log trước khi parser đọc nội dung.
C. Khôi phục offset sau restart để tránh đọc lại hoặc bỏ sót.
D. Để chuyển file log thành metric mà không cần processor bổ sung.
Đáp án đúng: C

5. Cổng mặc định thường dùng cho OTLP gRPC và OTLP HTTP lần lượt là gì?
A. 9411 cho gRPC và 4317 cho HTTP.
B. 55680 cho gRPC và 55681 cho HTTP.
C. 4318 cho gRPC và 4317 cho HTTP.
D. 4317 cho gRPC và 4318 cho HTTP.
Đáp án đúng: D

6. Batch processor chủ yếu cải thiện hiệu quả pipeline bằng cách nào?
A. Mã hóa từng record trước khi receiver chuyển vào pipeline.
B. Chọn trace cần giữ dựa trên lỗi và thời gian hoàn thành.
C. Lưu mọi record vào đĩa trước khi chuyển sang processor kế tiếp.
D. Gom nhiều record thành batch để giảm số lần gửi tới backend.
Đáp án đúng: D

7. Đặt memory_limiter sớm trong pipeline nhằm đạt mục tiêu nào?
A. Tự động nén payload trước khi đưa vào sending queue.
B. Giới hạn bộ nhớ trước khi processor sau giữ thêm dữ liệu.
C. Đảm bảo mọi record đều được export trước khi nhận thêm dữ liệu.
D. Thay thế garbage collector bằng cơ chế giới hạn bộ nhớ riêng.
Đáp án đúng: B

8. Khác biệt chính giữa filter processor và transform processor là gì?
A. Filter nhận metrics, transform chỉ hỗ trợ logs và traces.
B. Filter chỉ chạy ở gateway, transform chỉ chạy ở agent.
C. Filter loại record theo điều kiện, transform sửa nội dung record.
D. Filter chỉ đổi tên thuộc tính, transform chỉ thay đổi sampling rate.
Đáp án đúng: C

9. Khi viết OTTL condition, điều gì cần xác định trước để tránh truy cập sai dữ liệu?
A. Xác định context signal và vị trí thuộc tính cần đọc.
B. Tên exporter sẽ gửi record sau khi processor hoàn tất.
C. Kích thước batch tối đa mà backend có thể nhận.
D. Số replica gateway đang chạy trong mỗi availability zone.
Đáp án đúng: A

10. Resource attributes thường mô tả loại thông tin nào?
A. Trạng thái retry hiện tại của exporter trong pipeline.
B. Service, host hoặc container phát telemetry.
C. Nội dung riêng của một log event hoặc một span cụ thể.
D. Kết quả truy vấn được tạo ra bởi dashboard quan sát.
Đáp án đúng: B

11. Với Kubernetes attributes processor chạy theo mô hình agent, cách ghép pod thường dựa vào điều gì?
A. Pod IP hoặc metadata nguồn của workload.
B. Tên index backend nơi log của pod được lưu trữ.
C. Trace ID và span ID được truyền qua HTTP headers.
D. Tên dashboard và namespace đích của exporter.
Đáp án đúng: A

12. Để tail sampling đưa ra quyết định trên toàn bộ trace, cần bảo đảm điều gì?
A. Mỗi span được gửi tới một collector ngẫu nhiên để cân tải.
B. Gateway chỉ nhận root span và truy vấn child span từ backend.
C. Các span cùng trace ID được định tuyến tới cùng collector.
D. Mọi service phải tự quyết định sampling độc lập trước khi gửi.
Đáp án đúng: C

13. Giới hạn quan trọng của head sampling tại SDK là gì?
A. Nó luôn giữ toàn bộ trace nếu một child span gặp lỗi.
B. Nó chỉ hoạt động với logs và không hỗ trợ traces.
C. Span bị loại trước export không thể được tail sampler phục hồi.
D. Nó không thể dùng trace ID để liên kết span giữa dịch vụ.
Đáp án đúng: C

14. Một chính sách tail sampling muốn giữ trace chậm nên dựa vào dữ liệu nào?
A. Duration trace sau khi đã nhận đủ các span.
B. Số lượng resource attributes của service tạo root span.
C. Tỷ lệ batch thành công của logs pipeline trong cùng phút.
D. Kích thước queue của exporter ở thời điểm khởi tạo trace.
Đáp án đúng: A

15. Routing connector thường được dùng để làm gì trong Collector?
A. Nén payload và ghi checkpoint cho filelog receiver.
B. Tạo span mới cho mọi request đi qua gateway.
C. Đồng bộ đồng hồ giữa các node trước khi ingest.
D. Chọn pipeline đích theo điều kiện trên telemetry.
Đáp án đúng: D

16. Khi dùng spanmetrics connector, yếu tố nào dễ làm cardinality tăng đột biến?
A. Gộp metric theo service thay vì giữ từng instance.
B. Giảm số bucket histogram và bỏ nhãn môi trường.
C. Đặt tên metric ổn định theo quy ước của tổ chức.
D. Dùng user ID hoặc URL đầy đủ làm dimension.
Đáp án đúng: D

17. Sending queue của exporter giúp xử lý tình huống nào?
A. Backend chậm hoặc tạm ngừng, cần đệm dữ liệu trước khi gửi.
B. Processor cần tra cứu schema của từng resource trước khi chạy.
C. Receiver không mở đúng cổng giao thức để nhận telemetry.
D. Ứng dụng chưa tạo trace ID nên cần sinh context thay thế.
Đáp án đúng: A

18. Muốn queue của exporter tồn tại qua lần restart Collector, cần cấu hình gì?
A. Dùng batch processor với timeout dài hơn chu kỳ restart.
B. Dùng storage extension bền vững cho sending queue.
C. Tăng memory limiter để giữ queue trong heap lâu hơn.
D. Bật debug exporter để lưu bản sao record ra stdout.
Đáp án đúng: B

19. Khi backend tạm trả lỗi, retry policy phù hợp nên có đặc điểm nào?
A. Tạo pipeline mới cho từng lần retry để cô lập lỗi.
B. Retry có backoff và jitter để giãn các lần thử.
C. Retry liên tục không nghỉ để giảm thời gian gián đoạn.
D. Tắt queue và loại ngay mọi record chưa gửi thành công.
Đáp án đúng: B

20. Backend trả partial success cho một batch OTLP. Collector nên xử lý thế nào?
A. Đếm và theo dõi phần bị từ chối, rồi xử lý theo chính sách.
B. Retry nguyên batch vô hạn mà không xét số record bị từ chối.
C. Xóa queue hiện tại để tránh gửi trùng dữ liệu đã nhận.
D. Coi toàn bộ batch thành công vì HTTP status không báo lỗi.
Đáp án đúng: A

21. Vì sao cơ chế gửi at-least-once có thể tạo bản ghi trùng?
A. Collector luôn nhân đôi mọi record trước khi gọi exporter.
B. Backend đã ghi dữ liệu nhưng ACK bị mất nên sender gửi lại.
C. Batch processor gửi một record qua tất cả exporters cùng lúc.
D. Backend tự tạo thêm record khi nhận request có TLS.
Đáp án đúng: B

22. Khi downstream chậm, cách nào giúp giới hạn bộ nhớ và tạo tín hiệu quá tải rõ ràng?
A. Tăng batch size liên tục để không phải tạo thêm queue.
B. Dùng queue giới hạn cùng retry hoặc từ chối có kiểm soát.
C. Giữ toàn bộ record trong bộ nhớ cho tới khi backend phục hồi.
D. Tắt metric pipeline để dành bộ nhớ cho logs và traces.
Đáp án đúng: B

23. Khi sending queue đầy, quyết định vận hành nào phù hợp nhất?
A. Tắt retry để queue được giải phóng dù backend vẫn lỗi.
B. Xóa ngay các chunk cũ nhất mà không cần xem loại dữ liệu.
C. Đánh giá tải và chính sách drop hoặc block của queue.
D. Bỏ qua cảnh báo vì queue đầy chỉ ảnh hưởng dashboard.
Đáp án đúng: C

24. Trong Collector, logs, metrics và traces được tổ chức như thế nào?
A. Mọi signal bắt buộc dùng chung một receiver và exporter.
B. Chỉ traces có pipeline; logs và metrics được suy ra từ spans.
C. Mỗi signal có pipeline riêng với thành phần phù hợp.
D. Mỗi signal chạy ở một process riêng, không thể dùng chung.
Đáp án đúng: C

25. Khi cấu hình TLS cho exporter OTLP, kiểm soát nào bảo vệ danh tính backend?
A. Xác minh certificate chain và hostname của máy chủ đích.
B. Dùng cùng một certificate cho mọi service mà không xác thực.
C. Tắt hostname verification để chấp nhận mọi chứng chỉ.
D. Chỉ bật mã hóa nhưng bỏ qua kiểm tra CA và hostname.
Đáp án đúng: A

26. Authentication extension ở receiver thường đảm nhiệm việc gì?
A. Xác thực client trước khi nhận telemetry.
B. Ẩn các nhãn có cardinality cao khỏi metrics pipeline.
C. Tự động phát hiện service name từ nội dung span.
D. Mã hóa dữ liệu trong queue trước khi lưu xuống đĩa.
Đáp án đúng: A

27. Để tránh lộ secret qua debug exporter và các đích bên ngoài, nên làm gì?
A. Chỉ che dữ liệu sau khi exporter đã gửi tới backend.
B. Bật sampling thấp để giảm xác suất secret xuất hiện.
C. Chỉ xóa secret khỏi dashboard nhưng giữ nguyên record gốc.
D. Redact dữ liệu nhạy cảm trước khi phân nhánh export.
Đáp án đúng: D

28. Trong pipeline đa tenant, nguồn nào nên quyết định tenant identity dùng để route dữ liệu?
A. Tên exporter được chọn ngẫu nhiên theo từng request.
B. Danh tính đã xác thực hoặc metadata tin cậy do gateway gán.
C. Giá trị tenant do payload client tự khai báo mà không kiểm tra.
D. Tên namespace của Collector gateway nhận request.
Đáp án đúng: B

29. Thiết kế nhãn metrics nào giúp kiểm soát cardinality hiệu quả?
A. Dùng route template và nhãn hữu hạn thay cho ID động.
B. Tạo metric name mới cho từng tenant và từng request.
C. Dùng toàn bộ URL và query string làm dimension truy vấn.
D. Đưa user ID và request ID vào mọi metric để dễ tra cứu.
Đáp án đúng: A

30. Khi giám sát Collector, bộ số liệu nào giúp phân biệt nhận, từ chối và gửi telemetry?
A. CPU, heap và số thread của tiến trình Collector.
B. Dung lượng ổ đĩa và thời gian chạy của node exporter.
C. Bộ đếm nhận, từ chối, gửi và lỗi theo signal.
D. Số pod Ready cùng số lần container restart trong ngày.
Đáp án đúng: C

31. Ngoài queue size, chỉ số nào giúp nhận biết dữ liệu đang bị giữ quá lâu?
A. Tỷ lệ CPU idle của node chạy Collector gateway.
B. Tuổi của phần tử hoặc chunk cũ nhất đang chờ gửi.
C. Số lượng service name được ghi trong resource attributes.
D. Số dashboard đang truy vấn backend cùng thời điểm.
Đáp án đúng: B

32. Vì sao health endpoint trả 200 chưa đủ chứng minh telemetry pipeline khỏe mạnh?
A. HTTP 200 đồng nghĩa mọi record đã được lưu bền vững.
B. Health endpoint chỉ đo cardinality của metrics pipeline.
C. Endpoint chỉ hoạt động khi mọi exporter dùng chung TLS.
D. Process còn sống dù queue đầy hoặc export lỗi.
Đáp án đúng: D

33. Khi tail sampling chạy trên nhiều gateway replica, load balancing nên dựa vào gì?
A. Trace ID để các span của cùng trace tới một replica.
B. Tên pod nguồn để mọi span của một service cùng replica.
C. HTTP status để trace lỗi đi tới gateway riêng.
D. Kích thước batch để phân phối đều từng request.
Đáp án đúng: A

34. Agent cần tiếp tục gửi telemetry khi gateway tạm mất kết nối. Thiết kế nào phù hợp?
A. Bỏ mọi record trong outage và yêu cầu SDK gửi lại sau.
B. Chỉ dùng memory queue và giả định pod agent không restart.
C. Ghi queue bền vững cục bộ rồi retry khi gateway phục hồi.
D. Gửi thẳng tới backend cuối mà không qua chính sách gateway.
Đáp án đúng: C

35. Trước khi rollout cấu hình Collector mới trên toàn cụm, bước nào giảm rủi ro tốt nhất?
A. Tắt health checks và alert để rollout không bị gián đoạn.
B. Chỉ kiểm tra YAML parse được rồi bỏ qua component references.
C. Thay cấu hình đồng thời trên mọi node để tránh lệch phiên bản.
D. Validate, canary và theo dõi drop cùng lỗi export.
Đáp án đúng: D

36. Accepted tăng nhưng backend không có dữ liệu mới. Nên kiểm tra điều gì trước?
A. Chỉ tăng số receiver vì accepted chứng minh exporter khỏe.
B. Tắt processor để mọi record được gửi trực tiếp không kiểm soát.
C. Xóa queue để giải phóng bộ nhớ rồi kiểm tra lại dashboard.
D. Đối chiếu sent, failed, refused, queue và lỗi export.
Đáp án đúng: D
