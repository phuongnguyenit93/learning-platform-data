1. Khi một request đi qua nhiều microservice, context propagation giúp ích chính ở điểm nào?
A. Dồn mọi span vào một process để tránh cần gửi dữ liệu mạng.
B. Tự đồng bộ clock của mọi server để không lệch timestamp.
C. Bỏ yêu cầu gắn ID khi gọi service qua giao thức HTTP.
D. Giữ trace và log liên kết giữa nhiều dịch vụ khi gọi nhau.
Đáp án đúng: D

2. Trong một trace gồm nhiều span, cặp trace ID và span ID được hiểu thế nào?
A. Span ID dùng chung cả trace; trace ID đổi ở mỗi bước gọi.
B. Cả hai ID đều đổi khi span gọi đến một hàm nội bộ.
C. Trace ID dùng chung; span ID là riêng cho mỗi span.
D. Cả hai ID chỉ đại diện cho tên service nhận request.
Đáp án đúng: C

3. Header traceparent phiên bản 00 của W3C gồm nhóm trường nào theo thứ tự?
A. Trace-id, service-name, session-id và sampling-priority.
B. Baggage, span-name, parent-service và timestamp của máy.
C. Version, trace-id, parent-id rồi trace-flags trong W3C.
D. Version, tracestate, correlation-id và latency của request.
Đáp án đúng: C

4. Trong traceparent W3C phiên bản 00, độ dài trace-id hợp lệ là bao nhiêu?
A. 16 ký tự hex để biểu diễn định danh trace 8 byte.
B. 32 ký tự hex để biểu diễn định danh trace 16 byte.
C. 64 ký tự hex để biểu diễn định danh trace 32 byte.
D. 8 ký tự hex để biểu diễn định danh trace 4 byte.
Đáp án đúng: B

5. Trong traceparent phiên bản 00, parent-id có định dạng độ dài nào?
A. 32 ký tự hex, đại diện trace ID dài 16 byte.
B. 8 ký tự hex, đại diện flags dài 4 byte.
C. 64 ký tự hex, đại diện span ID dài 32 byte.
D. 16 ký tự hex, đại diện span ID dài 8 byte.
Đáp án đúng: D

6. Bit sampled của trace-flags trong traceparent cho biết điều gì?
A. Cho biết gợi ý sampling upstream, không bảo đảm export.
B. Xác nhận toàn bộ downstream span chắc chắn đã được gửi đi.
C. Thể hiện HTTP response luôn có trạng thái thành công.
D. Quy định baggage phải được ghi đầy đủ vào access log.
Đáp án đúng: A

7. Header tracestate theo W3C được dùng chủ yếu để làm gì?
A. Chứa danh sách quyền truy cập của tài khoản ứng dụng.
B. Thay trace-id để định danh mọi span trong một request.
C. Mang payload JSON của thông điệp giữa hai microservice.
D. Metadata riêng của vendor trong cùng trace khi truyền.
Đáp án đúng: D

8. Header baggage của W3C thường mang loại thông tin nào?
A. Khóa riêng dùng để ký traceparent ở mọi service trong mesh.
B. Các cặp key-value được mang qua dịch vụ cùng trace.
C. Danh sách toàn bộ span đã xuất và duration từng span.
D. Chứng thư TLS của gateway nhận request từ client.
Đáp án đúng: B

9. Một nhóm muốn đưa email khách hàng vào baggage để thuận tiện tìm trace. Đánh giá nào đúng?
A. Đưa email vào baggage an toàn như lưu trong kho bí mật nội bộ.
B. Chỉ cần đổi tên key thành user để không còn lộ dữ liệu.
C. Baggage được TLS của mọi hệ thống lưu log tự động ẩn đi.
D. Cần tránh thông tin nhạy cảm vì baggage có thể lan qua dịch vụ.
Đáp án đúng: D

10. Một request có traceparent hợp lệ nhưng không có baggage header. Điều gì vẫn khả thi?
A. Không thể tạo child span vì baggage là bắt buộc của W3C.
B. Trace ID phải đổi khi request không kèm theo baggage.
C. Trace vẫn nối theo parent dù không có baggage header.
D. Server phải hủy request HTTP vì thiếu metadata của client.
Đáp án đúng: C

11. Một message có baggage business-region nhưng traceparent bị thiếu. Kết luận hợp lý là gì?
A. Baggage tự cung cấp trace-id hợp lệ cho mọi consumer.
B. Consumer phải giả định span-id bằng giá trị business-region.
C. Message broker luôn tạo lại traceparent từ baggage.
D. Có thể đọc baggage nhưng không có remote parent span.
Đáp án đúng: D

12. Khi nhận traceparent chứa toàn số 0 cho trace-id, xử lý hợp lệ là gì?
A. Bỏ remote parent không hợp lệ; áp chính sách tạo trace.
B. Tiếp tục dùng trace-id bằng không như một trace ID hợp lệ.
C. Gộp request vào trace gần nhất tìm thấy trong bộ nhớ đệm.
D. Suy ra trace ID từ địa chỉ IP nguồn của HTTP request.
Đáp án đúng: A

13. Trong OpenTelemetry Java, Context.current() thể hiện điều gì?
A. Tập mọi span từng được exporter gửi đi trong tiến trình.
B. Context đang gắn với luồng thực thi tại thời điểm gọi.
C. Context mặc định được đồng bộ toàn cục giữa mọi thread.
D. Danh sách HTTP header do server lưu cho request cuối.
Đáp án đúng: B

14. Khi Java gọi span.makeCurrent() và nhận một Scope, thao tác nào cần thực hiện?
A. Giữ Scope mở đến khi JVM kết thúc để trace không bị mất.
B. Chỉ gọi span.end() và để Scope tự đóng trong thread pool.
C. Đóng Context toàn cục thay vì Scope của vùng xử lý.
D. Đóng Scope khi ra khỏi khối để phục hồi Context trước.
Đáp án đúng: D

15. Tạo Span mới và muốn Span.current() trả về nó trong khối code. Cách nào đúng?
A. Gọi startSpan là đủ cho mọi thread nhận span hiện hành.
B. Dùng makeCurrent trong Scope bao quanh khối cần trace.
C. Chỉ đổi tên span bằng setAttribute trước khi ghi log.
D. Gọi export ngay để thay đổi span hiện hành của thread.
Đáp án đúng: B

16. Trong Java, muốn child span có parent đã biết nhưng không tự gắn parent làm current. Dùng gì?
A. Chọn setNoParent để mọi child vẫn dùng trace ID cũ.
B. Đổi span name thành traceparent trước khi startSpan.
C. Ghi parent span ID vào MDC thay cho Context của OTel.
D. Dùng SpanBuilder.setParent với Context chứa span cha.
Đáp án đúng: D

17. Đưa Runnable vào Executor từ thread request, điều gì xảy ra với Context của OpenTelemetry theo mặc định?
A. Context luôn tự đi theo Runnable nhờ Executor của JDK.
B. Mọi worker thread cùng nhìn Context.current của thread gửi.
C. Executor không tự giữ Context; cần tự capture/restore.
D. Context tự được lưu bền vào queue khi submit Runnable.
Đáp án đúng: C

18. Để giữ trace parent của một Runnable qua Executor, cách xử lý nào hợp lý?
A. Lấy Context.current lần đầu trong worker rồi coi là parent.
B. Gắn cùng một static Scope cho toàn bộ thread của Executor.
C. Chờ job hoàn tất mới đọc span hiện hành ở thread gọi.
D. Capture Context lúc submit rồi attach khi worker chạy.
Đáp án đúng: D

19. Một pool thread tái sử dụng thread giữa hai request. Quên đóng Scope có hậu quả nào?
A. Executor lập tức tạo thread mới nên Context không thể rò.
B. Trace ID của mọi request vẫn tách biệt nhờ HTTP port.
C. Task sau có thể dùng nhầm Context còn lại từ task trước.
D. MDC tự loại bỏ Context OpenTelemetry còn mở trong thread.
Đáp án đúng: C

20. Vì sao InheritableThreadLocal không giải quyết đáng tin cậy truyền trace context trong thread pool?
A. Thread pool tái sử dụng thread, không inherit mỗi lần submit.
B. Mọi task đều tạo thread con mới sau khi nhận parent context.
C. Thread pool bảo đảm inherit lại giá trị ở mỗi lần submit.
D. Context OpenTelemetry được lưu trong DNS thay vì thread.
Đáp án đúng: A

21. MDC trong ứng dụng Java thường phục vụ nhu cầu nào về observability?
A. Gắn metadata như trace_id vào log của thread xử lý.
B. Lưu cây span đầy đủ để collector xây lại trace sau lỗi.
C. Truyền baggage trực tiếp thành HTTP header cho client.
D. Tự thực thi sampling trên mọi span trước khi exporter gửi.
Đáp án đúng: A

22. MDC có tự động tương đương OpenTelemetry Context không?
A. Có; mọi thay đổi Context.current lập tức sửa MDC ở mọi JVM.
B. Cần bridge/instrumentation để map trace IDs vào MDC.
C. Có; MDC tự inject traceparent ra mọi HTTP request.
D. Không; MDC chỉ hoạt động khi đã bật một distributed tracer.
Đáp án đúng: B

23. Worker đặt MDC trace_id từ request A rồi xử lý request B trên cùng thread. Biện pháp nào tránh lẫn log?
A. Khôi phục MDC trong finally sau khi xử lý request.
B. Giữ MDC từ A để mọi request dùng cùng correlation ID.
C. Thay tên thread bằng trace ID nhưng không dọn MDC.
D. Tắt ghi log trong B thay cho phục hồi context.
Đáp án đúng: A

24. Trong một hàm lồng nhau tạm đặt thêm trường MDC, cách cleanup nào ít gây hỏng context cha?
A. MDC.clear vô điều kiện rồi mất hết field đang dùng của cha.
B. Tăng log level lên DEBUG để tự xóa các khóa dư thừa.
C. Thay toàn bộ context cha bằng map rỗng sau hàm lồng.
D. Lưu giá trị trước đó và khôi phục khi rời phạm vi lồng.
Đáp án đúng: D

25. CompletableFuture.supplyAsync dùng executor khác. Muốn span trong lambda liên kết request gốc, nên làm gì?
A. Capture Context trước submit, attach vào lambda khi chạy.
B. Lấy Span.current bên trong worker mà không truyền thêm gì.
C. Đợi Future hoàn thành rồi đổi parent của span đã export.
D. Ghi traceparent vào tên CompletableFuture để JDK tự đọc.
Đáp án đúng: A

26. Với thenApplyAsync trong chuỗi CompletableFuture, điều gì cần chú ý về context?
A. Callback luôn chạy trong thread tạo future và giữ Scope gốc.
B. CompletionStage sẽ tự gửi W3C header cho mọi callback.
C. Callback có thể đổi thread, cần propagate Context vào nó.
D. thenApplyAsync chỉ chạy sau khi parent span được exporter nhận.
Đáp án đúng: C

27. Khi wrapper Runnable capture Context, thời điểm nào thường đúng để chụp Context?
A. Lúc worker bắt đầu chạy và chưa attach bất kỳ parent nào.
B. Lúc đăng ký hoặc submit task ở luồng có parent hợp lệ.
C. Sau khi callback trả kết quả và Scope đã đóng hoàn toàn.
D. Khi ứng dụng shutdown rồi mới gắn trace-id vào Runnable.
Đáp án đúng: B

28. Trong Project Reactor, Reactor Context khác ThreadLocal chủ yếu ở đâu?
A. Nó luôn là một biến static chung giữa tất cả subscriber.
B. Nó tự lưu trong HTTP cookie của từng request đi qua WebFlux.
C. Context đi theo subscriber qua các operator Reactor.
D. Nó chỉ hoạt động với Mono và không hỗ trợ Flux.
Đáp án đúng: C

29. Operator contextWrite của Reactor dùng để làm gì?
A. Đổi biến môi trường JVM cho toàn bộ worker thread của pool.
B. Cập nhật Context mà upstream operators có thể thấy.
C. Tự export mọi Span ở mỗi lần onNext không cần instrument.
D. Thay tên topic Kafka cho tất cả publisher liên quan.
Đáp án đúng: B

30. Một luồng Reactor đổi scheduler qua publishOn. Vì sao dựa riêng vào ThreadLocal dễ sai?
A. publishOn luôn khóa toàn bộ chuỗi vào thread request gốc.
B. Scheduler khác thread khiến ThreadLocal không theo signal.
C. ThreadLocal tự di chuyển cùng tín hiệu onNext qua mọi thread.
D. Reactor Context bị xóa ngay khi publisher chuyển scheduler.
Đáp án đúng: B

31. Dùng Reactor với OpenTelemetry Java mà không cấu hình bridge/hook. Nhận định nào an toàn?
A. Reactor luôn đồng bộ MDC và Scope cho mọi onNext tự động.
B. Mọi span trở thành root span ngay khi gặp contextWrite.
C. Không mặc định lan truyền OTel Context qua mọi operator.
D. Gọi block() một lần đủ để mọi callback khôi phục Context.
Đáp án đúng: C

32. Client Java gọi HTTP service B từ span hiện hành. Khi nào cần inject trace context?
A. Ghi trace context vào outgoing headers bằng propagator.
B. Sau khi nhận HTTP response, ghi traceparent vào body.
C. Trước khi mở TCP socket, ghi span-id vào DNS cache.
D. Sau khi exporter xác nhận span đã lưu tại collector.
Đáp án đúng: A

33. Service B nhận HTTP headers có traceparent. Bước nào cho child/server span đúng parent?
A. Tạo root span mới và chỉ copy header vào MDC để đối chiếu.
B. Xóa traceparent để sampling của B luôn độc lập với A.
C. Dùng HTTP method làm trace ID của server span mới.
D. Extract headers rồi dùng Context ấy làm parent span.
Đáp án đúng: D

34. Trong OpenTelemetry Java, TextMapPropagator dùng chung với thành phần nào để inject qua HTTP?
A. Một carrier headers cùng setter ghi giá trị vào carrier.
B. Một SpanExporter và processor để sửa header sau khi gửi.
C. Một tracer provider để thay toàn bộ giá trị trên DNS.
D. Một reader của log file để chụp span trước mỗi request.
Đáp án đúng: A

35. Nếu phía B không nhận traceparent hợp lệ từ A, cách tạo trace phù hợp là gì?
A. Tạo child span với parent ID bằng toàn số 0 để nối trace.
B. Khởi tạo root span cho request theo chính sách instrumentation.
C. Lấy trace ID của request B trước đó từ MDC trong worker.
D. Bỏ ghi span vì không thể dựng trace mới khi thiếu header.
Đáp án đúng: B

36. Hai dịch vụ có trace ID khác nhau dù gọi HTTP liên tiếp. Đầu tiên nên kiểm tra gì?
A. Kiểm tra inject/extract header và propagator cả hai bên.
B. Đổi sampling rate trước khi kiểm tra các HTTP header.
C. Tăng retention collector để đồng nhất ID ở hai dịch vụ.
D. Đổi hostname của B để OpenTelemetry cấp lại trace ID cũ.
Đáp án đúng: A

37. Khi tạo OpenTelemetry SDK Java muốn hỗ trợ W3C Trace Context cùng Baggage. Cấu hình nào phù hợp?
A. Ghép W3CTraceContext với W3CBaggage qua composite.
B. Khai báo logger MDC rồi bỏ cấu hình propagator.
C. Bật SpanExporter rồi giả định nó inject mọi HTTP call.
D. Dùng một sampler ParentBased thay cho các propagator.
Đáp án đúng: A

38. Ứng dụng gRPC qua HTTP/2 cần truyền trace context qua đâu?
A. Qua tên file .proto mà hai phía đã biên dịch từ schema.
B. Qua cấu hình thread pool của server mà không kèm headers.
C. Qua DNS TXT record dùng chung cho toàn bộ lời gọi gRPC.
D. Qua metadata của lời gọi theo cơ chế propagator tương ứng.
Đáp án đúng: D

39. Producer đẩy message vào broker; muốn consumer tiếp tục trace. Nên làm gì?
A. Ghi trace ID vào log của producer rồi bỏ metadata.
B. Chờ consumer tự đọc Span.current của thread producer.
C. Inject trace context vào message headers/properties.
D. Gắn span-id vào tên topic để tất cả message cùng dùng.
Đáp án đúng: C

40. Consumer nhận message có trace headers. Muốn dựng context phù hợp, thao tác nào đúng?
A. Đọc HTTP response header của broker để lấy traceparent.
B. Extract metadata của message trước khi tạo processing span.
C. Tạo server root span rồi thay nó bằng trace của message sau.
D. Ghi trace ID vào MDC nhưng bỏ qua parent của processing span.
Đáp án đúng: B

41. Một consumer xử lý batch từ nhiều message thuộc các trace nguồn khác nhau. Cách biểu diễn quan hệ nào phù hợp?
A. Chọn một trace ID rồi ép mọi nguồn vào cùng trace đó.
B. Dùng một parent span giả cho các message từ mọi tenant.
C. Liên kết xử lý batch bằng span links tới từng nguồn.
D. Bỏ liên kết tới message vì batch không thể có tracing.
Đáp án đúng: C

42. Trong hệ thống queue có thời gian chờ dài, vì sao span links có thể hữu ích?
A. Liên kết nguồn bất đồng bộ nhưng không ép quan hệ parent.
B. Đảm bảo message luôn được xử lý đúng một lần ở broker.
C. Thay access control giữa consumer và queue theo trace ID.
D. Bỏ yêu cầu gửi context qua headers khi trace bị sampling.
Đáp án đúng: A

43. Trong distributed trace, log correlation tốt nhất dựa vào điều gì?
A. Log chỉ cần timestamp vì mọi server có cùng múi giờ.
B. Log dùng tên thread làm định danh duy nhất toàn hệ thống.
C. Log ghi trace_id và span_id từ context đang hoạt động.
D. Log gắn IP server thay cho mọi thông tin về span.
Đáp án đúng: C

44. Nếu parent span không được sample, kết luận nào về traceparent là đúng?
A. Traceparent không thể truyền khi sampled bit bằng số 0.
B. Mọi downstream span chắc chắn sẽ được exporter gửi đi.
C. Context có thể vẫn được truyền dù span không được export.
D. Trace ID phải lập tức đổi khi một child span không sample.
Đáp án đúng: C

45. Baggage chứa tenant_id được nhận từ request công cộng. Tại sao không nên dùng nó trực tiếp để phân quyền?
A. Baggage tự được CA ký nên phù hợp để xác định toàn bộ quyền.
B. Đổi tên baggage key có thể bảo đảm danh tính tenant hợp lệ.
C. Có trace ID hợp lệ thì tenant trong baggage đã được xác minh.
D. Baggage không được xác thực, cần kiểm quyền từ nguồn tin cậy.
Đáp án đúng: D

46. Khi chuyển tiếp request sang đối tác ngoài tổ chức, xử lý baggage nào an toàn hơn?
A. Chuyển mọi baggage nhận được để giữ đầy đủ log của người dùng.
B. Lọc baggage theo khóa cho phép trước khi qua đối tác.
C. Đưa JWT bearer token vào baggage để thuận tiện debug ở đối tác.
D. Copy cả MDC chứa mật khẩu để giữ quan hệ trace qua HTTP.
Đáp án đúng: B

47. Trong phép thử song song hai request A/B chạy chung thread pool, kết quả nào chứng tỏ propagation đúng?
A. Mọi tác vụ có cùng trace ID vì dùng chung executor và logger.
B. Log và child span của mỗi task giữ đúng trace ID, không lẫn A/B.
C. Cả A/B đều tạo root span mới khi chạy trong thread pool.
D. Các task có log timestamp gần nhau mà không cần trace ID.
Đáp án đúng: B

48. Ở OpenTelemetry Java, Span.end() khác với Scope.close() ở điểm nào?
A. Span.end kết thúc span; Scope.close khôi phục Context.
B. Span.end tự đóng mọi Scope của tất cả thread trong JVM.
C. Scope.close tự export và kết thúc mọi span đã tạo.
D. Hai phương thức đều xóa traceparent khỏi HTTP của client.
Đáp án đúng: A
