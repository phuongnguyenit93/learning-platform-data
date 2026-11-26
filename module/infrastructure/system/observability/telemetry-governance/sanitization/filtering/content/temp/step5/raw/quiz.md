Câu 1. OpenTelemetry Collector filter processor chủ yếu dùng để làm gì?
A. Lọc logs, metrics hoặc spans theo điều kiện OTTL.
B. Mã hóa toàn bộ telemetry trước khi gửi exporter.
C. Gộp các trace khác nhau thành một trace duy nhất.
D. Tạo dashboard từ telemetry đã lưu trong backend.
Đáp án đúng: A

Câu 2. Filter processor thường được đặt ở đâu trong Collector pipeline?
A. Sau exporter và trước receiver trong pipeline tín hiệu.
B. Sau receiver và trước exporter trong pipeline tín hiệu.
C. Ngoài pipeline, chạy độc lập với service configuration.
D. Bên trong ứng dụng nguồn trước khi SDK tạo telemetry.
Đáp án đúng: B

Câu 3. OTTL là tên viết tắt của thành phần nào?
A. OpenTelemetry Transport Layer dùng cho truyền dữ liệu.
B. OpenTelemetry Trace Linker dùng cho liên kết trace.
C. Ngôn ngữ biến đổi telemetry của OpenTelemetry.
D. OpenTelemetry Telemetry Loader dùng cho nạp cấu hình.
Đáp án đúng: C

Câu 4. Trong cấu hình filter kiểu context, `traces.span` áp dụng điều kiện lên đối tượng nào?
A. Resource cùng các span gắn với nó.
B. Mỗi event được gắn trong span.
C. Đánh giá riêng từng span trong trace.
D. Cả trace được xem như một đơn vị duy nhất.
Đáp án đúng: C

Câu 5. Khi điều kiện tham chiếu `resource.attributes`, dữ liệu nào được kiểm tra?
A. Thuộc tính riêng của từng span đang xét.
B. Thuộc tính chung của resource phát tín hiệu.
C. Nội dung body của từng log record.
D. Giá trị của từng metric datapoint.
Đáp án đúng: B

Câu 6. Điều kiện dùng `attributes["http.route"]` trong context span thường đọc gì?
A. Thuộc tính resource chung của process phát span.
B. Trường body của log record liên quan request.
C. Tên metric của pipeline đang nhận trace.
D. Thuộc tính của span đang được đánh giá.
Đáp án đúng: D

Câu 7. Context `traces.spanevent` phù hợp để lọc thành phần nào?
A. Toàn bộ span cha cùng tất cả span con.
B. Resource attribute của service phát trace.
C. Metric datapoint được tạo từ span event.
D. Event riêng được gắn vào span.
Đáp án đúng: D

Câu 8. Trong filter processor, `logs.log_record` cho phép đánh giá điều kiện trên gì?
A. Từng log record trong luồng logs.
B. Toàn bộ log resource và mọi record bên dưới.
C. Tên exporter đang gửi log tới backend.
D. File cấu hình logging của ứng dụng nguồn.
Đáp án đúng: A

Câu 9. Context `metrics.metric` đánh giá đối tượng ở mức nào?
A. Từng datapoint riêng lẻ trong một metric.
B. Resource phát metric và tất cả tín hiệu của resource.
C. Metric object, gồm tên và metadata của metric.
D. Toàn bộ metrics pipeline của Collector.
Đáp án đúng: C

Câu 10. Context `metrics.datapoint` phù hợp khi muốn lọc gì?
A. Các datapoint riêng trong metric.
B. Toàn bộ metric object theo tên metric.
C. Resource attribute chung của host phát metric.
D. Exporter nhận dữ liệu metric sau khi batch.
Đáp án đúng: A

Câu 11. Nếu cấu hình nhiều điều kiện lọc trong cùng context, khi nào telemetry bị loại?
A. Chỉ khi tất cả điều kiện cùng khớp.
B. Chỉ khi điều kiện cuối cùng trả về true.
C. Một điều kiện bất kỳ khớp là đủ.
D. Khi hai điều kiện đầu và cuối cùng khớp.
Đáp án đúng: C

Câu 12. Hàm OTTL `IsMatch(value, pattern)` thường dùng để làm gì?
A. So khớp giá trị chuỗi với biểu thức chính quy.
B. So sánh hai timestamp theo thứ tự thời gian.
C. Chuyển giá trị chuỗi thành một metric histogram.
D. Kiểm tra xem attribute có tồn tại trong resource.
Đáp án đúng: A

Câu 13. Muốn loại span có tên bắt đầu bằng `/health`, điều kiện nào phù hợp?
A. Dùng `IsMatch(resource, "^/health")` trong context span.
B. `IsMatch(name, "^/health")` trong span context.
C. Dùng `name == "health"` cho mọi log record.
D. Dùng `metric.name == "/health"` cho trace span.
Đáp án đúng: B

Câu 14. Khi một span không có attribute `user.id`, cách kiểm tra sự vắng mặt nào phù hợp?
A. So sánh `attributes["user.id"]` với chuỗi rỗng.
B. So sánh `resource.attributes` với số 0.
C. So sánh `attributes["user.id"]` với `nil`.
D. So sánh `span.name` với `nil` trong mọi context.
Đáp án đúng: C

Câu 15. Trong filter processor, `error_mode: ignore` thường nhằm mục đích nào?
A. Coi mọi lỗi OTTL là điều kiện khớp và drop telemetry.
B. Bỏ qua lỗi đánh giá OTTL để pipeline tiếp tục xử lý.
C. Dừng toàn bộ Collector ngay khi một biểu thức lỗi.
D. Tự sửa cú pháp OTTL sai rồi chạy lại biểu thức.
Đáp án đúng: B

Câu 16. Nếu chọn `error_mode: propagate`, hệ quả nào cần được dự liệu?
A. Lỗi đánh giá được truyền lên pipeline gọi processor.
B. Lỗi được bỏ qua và telemetry luôn đi tiếp bình thường.
C. Mọi record lỗi tự chuyển thành log severity ERROR.
D. Collector tự thay biểu thức lỗi bằng điều kiện true.
Đáp án đúng: A

Câu 17. Một điều kiện filter span khớp sẽ tác động ra sao trong context `traces.span`?
A. Loại span khớp điều kiện khỏi luồng xử lý.
B. Chỉ xóa một attribute khỏi span và giữ span lại.
C. Xóa mọi span của tất cả resource trong Collector.
D. Chỉ đánh dấu span là lỗi mà không loại span.
Đáp án đúng: A

Câu 18. Khi filter ở context `traces.spanevent`, điều gì xảy ra với span cha?
A. Span cha luôn bị loại cùng event tương ứng.
B. Span cha được chuyển thành root span mới.
C. Span cha tự động đổi status thành ERROR.
D. Span cha vẫn có thể được giữ lại sau khi event bị loại.
Đáp án đúng: D

Câu 19. Nếu lọc một số span con bằng filter processor, rủi ro điều tra nào có thể xuất hiện?
A. Trace ID của các span còn lại tự động được tạo lại.
B. Trace có thể thiếu span và mất ngữ cảnh.
C. Mọi log record cùng request tự động bị xóa theo.
D. Span cha luôn được chuyển thành metric datapoint.
Đáp án đúng: B

Câu 20. Muốn loại datapoint có attribute cụ thể nhưng giữ phần còn lại của metric, nên dùng gì?
A. Điều kiện trong context `metrics.metric` cho cả metric.
B. Điều kiện trong context `traces.resource` cho cả host.
C. Điều kiện trong context `logs.scope` cho mọi log.
D. Điều kiện trong context `metrics.datapoint`.
Đáp án đúng: D

Câu 21. Nếu muốn loại log record có severity thấp hơn WARN, cần xét trường nào?
A. `span.status.code` của span cha.
B. `severity_number` của log record.
C. `metric.type` của metric cùng resource.
D. `resource.schema_url` của log scope.
Đáp án đúng: B

Câu 22. Điều kiện resource trong filter có thể ảnh hưởng đến dữ liệu như thế nào?
A. Chỉ thay một thuộc tính của từng span trong resource.
B. Chỉ loại log record mới nhất của resource.
C. Chỉ thay tên exporter cho resource đó.
D. Drop subtree telemetry của resource khớp.
Đáp án đúng: D

Câu 23. Filter processor khác transform processor ở điểm chính nào?
A. Filter sửa thuộc tính; transform chỉ loại toàn bộ record.
B. Filter loại telemetry khớp; transform sửa dữ liệu được giữ lại.
C. Cả hai chỉ thay đổi resource attributes, không đụng span.
D. Transform chỉ chạy trên metrics, filter chỉ chạy trên logs.
Đáp án đúng: B

Câu 24. Khi cần xóa một attribute nhạy cảm nhưng giữ span, lựa chọn nào phù hợp?
A. Dùng filter processor để drop cả span chứa attribute.
B. Dùng batch processor để gộp span trước khi xóa.
C. Dùng exporter để đổi tên attribute sau khi lưu backend.
D. Dùng attributes hoặc transform để xóa attribute.
Đáp án đúng: D

Câu 25. Trong OTTL transform statement, thao tác `set` thường dùng để làm gì?
A. Loại toàn bộ telemetry thỏa điều kiện khỏi pipeline.
B. Chọn target mới cho service discovery của Collector.
C. Đặt lịch scrape cho Prometheus exporter.
D. Gán hoặc cập nhật giá trị cho trường telemetry.
Đáp án đúng: D

Câu 26. Vì sao filter không thay thế được redaction khi cần giữ record?
A. Filter drop record khớp thay vì che giá trị nhạy cảm.
B. Filter luôn hash mọi thuộc tính trước khi gửi.
C. Filter chỉ xóa giá trị secret và giữ nguyên record.
D. Filter tự động mask trường theo semantic convention.
Đáp án đúng: A

Câu 27. Thứ tự processor trong pipeline Collector có ý nghĩa gì?
A. Processor luôn chạy song song theo tên alphabet.
B. Exporter quyết định thứ tự processor khi nhận dữ liệu.
C. Thứ tự chỉ ảnh hưởng logs, không ảnh hưởng traces hay metrics.
D. Processor chạy theo thứ tự được khai báo trong pipeline.
Đáp án đúng: D

Câu 28. Vì sao memory_limiter thường được đặt sớm trong pipeline?
A. Giảm tải sớm khi Collector tiến gần giới hạn bộ nhớ.
B. Để gom batch trước mọi bước lọc và transform.
C. Để gửi telemetry trước khi receiver nhận dữ liệu.
D. Để chuyển OTTL thành cấu hình exporter tự động.
Đáp án đúng: A

Câu 29. Vì sao filtering thường được đặt trước batch processor?
A. Đảm bảo batch processor có thể khôi phục dữ liệu đã drop.
B. Để batch tự tạo điều kiện OTTL cho filter processor.
C. Để mọi exporter nhận cùng số record trước khi lọc.
D. Tránh gom batch cho dữ liệu sẽ bị loại bỏ sau đó.
Đáp án đúng: D

Câu 30. Khai báo processor trong phần `processors` đã đủ để kích hoạt nó chưa?
A. Đủ; Collector tự chạy mọi processor đã được khai báo.
B. Chỉ cần đặt tên processor giống receiver là tự kích hoạt.
C. Phải gắn processor vào pipeline trong `service`.
D. Chỉ cần restart exporter để processor bắt đầu chạy.
Đáp án đúng: C

Câu 31. Nếu cùng một Collector có nhiều pipeline, policy filter cần được quản lý thế nào?
A. Đảm bảo processor được gắn đúng vào từng pipeline cần lọc.
B. Khai báo một lần là mọi pipeline tự động dùng chung processor.
C. Chỉ gắn vào pipeline traces vì logs và metrics kế thừa.
D. Để exporter quyết định pipeline nào được áp dụng filter.
Đáp án đúng: A

Câu 32. Lọc metric theo `user.id` duy nhất cho từng người dùng có thể gây hậu quả nào?
A. Cardinality giảm vì mỗi user chỉ tạo một sample duy nhất.
B. Prometheus tự chuyển label thành resource attribute.
C. Cardinality tăng cao và chi phí TSDB hoặc truy vấn tăng.
D. Collector tự gộp mọi user ID thành một series.
Đáp án đúng: C

Câu 33. Loại bỏ health-check telemetry có thể mang lại lợi ích nào?
A. Giảm lưu lượng và chi phí nếu tín hiệu đó ít giá trị điều tra.
B. Bảo đảm trace của mọi request nghiệp vụ đầy đủ hơn.
C. Tăng độ chính xác của mọi metric latency tự động.
D. Loại bỏ nhu cầu theo dõi availability của dịch vụ.
Đáp án đúng: A

Câu 34. Vì sao không nên drop toàn bộ log ERROR theo mặc định?
A. Log ERROR luôn chứa dữ liệu sai định dạng nên phải drop.
B. Có thể mất bằng chứng quan trọng để phát hiện và điều tra sự cố.
C. Backend thường không thể lưu log có severity cao.
D. Collector tự chuyển log ERROR thành span khi bị loại.
Đáp án đúng: B

Câu 35. Nếu tail sampling cần giữ trace có lỗi, filter đặt trước tail sampling có rủi ro gì?
A. Tail sampler sẽ khôi phục mọi span đã bị filter loại.
B. Filter tự nâng sampling probability của trace lỗi lên 100%.
C. Span lỗi có thể bị drop trước khi tail sampler đánh giá trace.
D. Không có ảnh hưởng vì tail sampling chỉ đọc metrics.
Đáp án đúng: C

Câu 36. Làm thế nào kiểm thử chính sách filter trước khi áp dụng production?
A. Chỉ kiểm tra file YAML bằng mắt rồi triển khai thẳng.
B. Phát telemetry mẫu ở staging và so sánh dữ liệu trước/sau.
C. Chỉ đo CPU Collector khi không gửi telemetry thử nghiệm.
D. Tắt exporter để chắc chắn filter không gửi dữ liệu.
Đáp án đúng: B

Câu 37. Lệnh xác thực cấu hình Collector trước khi triển khai thường là gì?
A. `otelcol scrape --config=collector.yaml`.
B. `otelcol export --config=collector.yaml`.
C. `otelcol validate --config=collector.yaml`.
D. `otelcol filter --config=collector.yaml`.
Đáp án đúng: C

Câu 38. Khi một biểu thức OTTL có thể gặp attribute thiếu hoặc sai kiểu, nên làm gì?
A. Giả định mọi telemetry luôn có đủ attribute cùng kiểu.
B. Đổi mọi attribute thành chuỗi trước khi filter bất kể ngữ nghĩa.
C. Kiểm thử trường hợp nil, kiểu dữ liệu và error_mode.
D. Tắt kiểm tra lỗi để mọi biểu thức đều được coi là hợp lệ.
Đáp án đúng: C

Câu 39. Sau khi áp dụng filter, nhóm chỉ số nào nên so sánh để đánh giá tác động?
A. Chỉ số dashboard mở mỗi ngày của nhóm vận hành.
B. So dropped data, tải, chi phí và độ phủ debug.
C. Chỉ số lượng processor được khai báo trong YAML.
D. Chỉ số lượng exporter dù không có dữ liệu đi qua.
Đáp án đúng: B

Câu 40. Khi filter mới làm trace mất các span cần thiết để chẩn đoán, hành động nào phù hợp?
A. Tăng batch size để tự khôi phục các span đã bị loại.
B. Tăng retention backend để lấy lại dữ liệu chưa từng export.
C. Tắt mọi cảnh báo để giảm tác động của trace thiếu span.
D. Điều chỉnh hoặc rollback rule rồi kiểm thử lại bằng trace mẫu.
Đáp án đúng: D
