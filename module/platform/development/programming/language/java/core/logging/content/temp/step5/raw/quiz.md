Câu 1: Trong JUL, Logger có level null sử dụng ngưỡng hiệu lực nào?
A. Lấy level của Handler đầu tiên được gắn trực tiếp.
B. Tự chuyển về INFO dù các logger cha đặt mức khác.
C. Kế thừa level của logger tổ tiên đã cấu hình.
D. Lấy level của bản ghi được xuất gần nhất trên thread.
Đáp án đúng: C

Câu 2: LogRecord qua ngưỡng Logger nhưng không xuất hiện trong file JUL; cần xem xét gì?
A. Tên package của class chứa lời gọi logging hiện tại.
B. Ngưỡng level và Filter của Handler ghi ra file.
C. Thứ tự các class được JVM nạp khi bắt đầu chạy.
D. Độ ưu tiên của thread thực hiện câu lệnh ghi log.
Đáp án đúng: B

Câu 3: Filter gắn vào Handler của JUL có nhiệm vụ chính nào?
A. Tự chỉnh level của mọi Logger trong cùng package.
B. Thay thế message bằng tên class tạo LogRecord.
C. Tạo một Formatter mới cho mọi event đến Handler.
D. Chấp nhận hay loại từng LogRecord tại Handler.
Đáp án đúng: D

Câu 4: Vì sao một event JUL bị ghi hai lần khi Logger có Handler riêng?
A. Mức WARNING luôn làm JUL xuất cùng LogRecord hai lần.
B. Formatter mặc định phát dòng text và dòng JSON riêng.
C. Root Logger tự tạo bản sao khi gặp nhiều thread ghi.
D. Bản ghi còn được chuyển lên các Handler của logger cha.
Đáp án đúng: D

Câu 5: JUL Formatter có trách nhiệm chính nào trong pipeline logging?
A. Quyết định mở và đóng file cho tất cả các Handler.
B. Thiết lập level tối thiểu cho toàn bộ logger con.
C. Định dạng LogRecord thành biểu diễn đầu ra.
D. Quản lý permission của người dùng đọc bản ghi log.
Đáp án đúng: C

Câu 6: Cặp mức độ nghiêm trọng JUL nào được sắp theo đúng thứ tự tăng?
A. WARNING thấp hơn CONFIG, còn CONFIG thấp hơn FINE.
B. SEVERE thấp hơn INFO, còn INFO thấp hơn WARNING.
C. FINE cao hơn SEVERE, còn SEVERE cao hơn CONFIG.
D. INFO, WARNING, SEVERE theo mức độ tăng dần.
Đáp án đúng: D

Câu 7: Một Logger JUL có level INFO nhận lời gọi FINE; điều gì xảy ra?
A. Bản FINE bị logger chặn trước khi tới Handler.
B. FileHandler mức FINE vẫn bắt buộc nhận bản này.
C. Logger nâng FINE thành INFO rồi mới gửi xuống đích.
D. Event đợi trong bộ đệm tới khi level được giảm.
Đáp án đúng: A

Câu 8: Với JUL, Supplier<String> trong lời gọi log có lợi ích gì?
A. Trì hoãn dựng message khi mức log không bật.
B. Buộc message luôn được sinh trước khi xét level.
C. Chuyển mọi lần ghi log sang executor riêng.
D. Tự thử lại bản ghi nếu Handler gặp lỗi I/O.
Đáp án đúng: A

Câu 9: SLF4J đóng vai trò gì trong thiết kế logging Java?
A. Công cụ tạo file log không cần backend đi kèm.
B. Bộ Formatter thay thế mọi Handler của JUL trong JVM.
C. SLF4J cung cấp API, provider thực hiện việc ghi log.
D. Bộ quản lý appender và rolling policy chung cho mọi backend.
Đáp án đúng: C

Câu 10: SLF4J 2.x thường phát hiện backend triển khai bằng cơ chế nào?
A. Phân tích mục root Logger trong file logback.xml.
B. Lấy ConsoleHandler đầu tiên do JUL đã tạo.
C. ServiceLoader tìm provider trên runtime classpath.
D. Tìm lớp bất kỳ có tên tận cùng bằng LoggerFactory.
Đáp án đúng: C

Câu 11: Nếu ứng dụng SLF4J 2.x không có provider hợp lệ, hệ quả thường gặp?
A. JVM tự mở file log mặc định trong thư mục chạy.
B. Javac dừng biên dịch vì thiếu XML cấu hình.
C. Tự chuyển tất cả event tới syslog trên máy chủ.
D. Cảnh báo và chuyển các lời gọi log sang NOP logger.
Đáp án đúng: D

Câu 12: SLF4J parameterized logging thường dùng placeholder nào?
A. Ký hiệu %s được diễn giải bằng String.format.
B. Dấu hỏi ? dùng cơ chế giống JDBC PreparedStatement.
C. Cặp ngoặc nhọn {} cho các đối số theo thứ tự.
D. Biểu thức ${} được shell mở rộng khi runtime chạy.
Đáp án đúng: C

Câu 13: Đối số logger.debug tạo báo cáo tốn CPU dù DEBUG tắt; nguyên nhân nào?
A. SLF4J tính mọi đối số trong Formatter sau khi ghi file.
B. Appender tự gọi lại phương thức tạo đối số bằng reflection.
C. Biểu thức tạo đối số chạy trước khi gọi logger.debug.
D. Backend yêu cầu tạo thread mới cho mọi đối số phức tạp.
Đáp án đúng: C

Câu 14: Cách ghi exception nào giúp giữ stack trace để chẩn đoán?
A. Truyền Throwable tới Logger để giữ lại stack trace.
B. Chỉ truyền message của lỗi sau khi gọi getMessage.
C. Chỉ lưu tên class exception vào metadata context.
D. Chỉ ghi mã HTTP mà API liên quan đã trả về.
Đáp án đúng: A

Câu 15: Vì sao đặt tên logger theo class hoặc package giúp vận hành tốt?
A. Bảo đảm log đúng thứ tự các class được nạp vào JVM.
B. Cấu hình level theo package mà không sửa mã nguồn.
C. Bảo đảm backend khử trùng các event có cùng message.
D. Bắt buộc mọi Logger dùng chung mức INFO cố định.
Đáp án đúng: B

Câu 16: Với lỗi validation do request sai định dạng thường xuyên, nên chọn mức log ra sao?
A. Ghi mức ERROR cho mọi lần nhập sai để dễ thống kê.
B. Đánh giá tác động trước khi gán mức ERROR cho lỗi.
C. Ghi mức TRACE cho mọi lỗi và coi đó là audit đầy đủ.
D. Bỏ toàn bộ log request vì đều là dữ liệu khách gửi.
Đáp án đúng: B

Câu 17: Trong Logback, event xuất ở cả appender con và appender cha do cơ chế nào?
A. Encoder ghi event thành cả text và JSON theo mặc định.
B. Logback phát sinh hai lần mọi thông điệp có mức INFO.
C. Root Logger tự nhân event cho mỗi thread đang chạy.
D. Additivity khiến event tiếp tục qua các Logger cha.
Đáp án đúng: D

Câu 18: Appender và Encoder của Logback khác nhau chủ yếu ở vai trò nào?
A. Encoder chọn file đích, còn Appender chỉ tính level.
B. Appender chọn đích, Encoder tạo byte đầu ra.
C. Appender sửa message, còn Encoder quản lý tên logger.
D. Encoder tạo LogEvent, còn Appender cấp phát thread.
Đáp án đúng: B

Câu 19: PatternLayoutEncoder hỗ trợ nhu cầu nào trong Logback?
A. Sinh requestId giống nhau xuyên nhiều dịch vụ phân tán.
B. Định dạng thời gian, level, thread cùng message.
C. Đổi mức log dựa trên lượng CPU đang dùng trong JVM.
D. Phân quyền đọc file theo danh tính người gửi request.
Đáp án đúng: B

Câu 20: Logback cần xoay file mỗi ngày và giữ lịch sử giới hạn; nên cấu hình gì?
A. Rolling policy theo ngày và giới hạn file lưu giữ.
B. Một Logger mới được tạo mỗi ngày trong class nghiệp vụ.
C. Pattern encoder tự đổi tên file sau khi sinh timestamp.
D. Một MDC key chứa ngày để appender tự xóa file cũ.
Đáp án đúng: A

Câu 21: Muốn xoay file theo cả dung lượng và thời gian, cần xét gì?
A. Một Formatter khác nhau cho mỗi tên thread ứng dụng.
B. Một Logger mới khi request đầu ngày được xử lý.
C. Rolling policy gộp ngưỡng size và mốc thời gian.
D. Một MDC key ghi số byte đã truyền đến collector.
Đáp án đúng: C

Câu 22: Khi dùng Logback AsyncAppender, yếu tố nào quyết định hành vi dưới tải lớn?
A. Mọi Formatter luôn ghi trên chính thread gọi log.
B. Queue, cách phản ứng khi đầy và xả log lúc dừng.
C. MDC tự biến mất trước khi event được đẩy vào queue.
D. Mọi sự kiện được lưu bền dù process bị dừng đột ngột.
Đáp án đúng: B

Câu 23: Logger bật DEBUG nhưng appender chỉ nhận WARN; chuyện gì xảy ra với debug event?
A. Appender tự nâng DEBUG thành WARN để bảo toàn sự kiện.
B. Cấu hình Logger luôn bỏ qua mọi mức filter tại appender.
C. Appender có thể chặn DEBUG dù Logger đã bật mức đó.
D. Event sẽ chờ cho tới khi appender hạ ngưỡng xuống DEBUG.
Đáp án đúng: C

Câu 24: Logback có hai appender cùng nhận một event; kết quả thường là gì?
A. Chỉ appender nhanh nhất được phép ghi mỗi LogEvent.
B. Logback luôn báo lỗi nếu một Logger có hai đích ghi.
C. Các appender có thể ghi một bản cho cùng một event.
D. Hai appender bắt buộc dùng chung đúng một file đích.
Đáp án đúng: C

Câu 25: Log4j2 AsyncLogger đem lại đánh đổi vận hành nào?
A. Tách I/O khỏi caller nhưng vẫn phải quản lý queue.
B. Mọi event luôn bền vững ngay khi đã vào queue của logger.
C. Mọi bản ghi từ nhiều tiến trình được sắp xếp toàn cục.
D. Không còn cần cấu hình appender hoặc chính sách ghi.
Đáp án đúng: A

Câu 26: Log4j2 ThreadContext thường chứa dạng dữ liệu nào?
A. Mã bytecode của class đang gọi phương thức ghi log.
B. Metadata request như requestId được gắn vào LogEvent.
C. Danh sách FileHandler JUL được đăng ký trong JVM.
D. Chứng chỉ TLS được tự động sinh cho mỗi bản ghi log.
Đáp án đúng: B

Câu 27: Ứng dụng muốn log JSON truy vấn được bằng Log4j2; cách thiết kế nào phù hợp?
A. Ghép chuỗi tự do có dấu ngoặc rồi coi là JSON hợp lệ.
B. Structured layout và schema cho từng trường dữ liệu.
C. Đổi file .log thành .json và giữ nguyên formatter text.
D. Bỏ level và timestamp, chỉ xuất nội dung message.
Đáp án đúng: B

Câu 28: Log4j2 Filter gắn với một appender có thể thực hiện điều gì?
A. Thay tên class của method đang gọi logger trên JVM.
B. Buộc thay provider SLF4J cho toàn bộ classpath chạy.
C. Áp dụng một Layout JSON chung cho các appender đang chạy.
D. Cho phép hoặc chặn LogEvent tại appender đó.
Đáp án đúng: D

Câu 29: Marker trong SLF4J/Log4j2 có ích trong tình huống nào?
A. Thay thế Throwable bằng mã lỗi chỉ có trong MDC.
B. Tự tạo traceId hợp lệ và truyền qua mọi network hop.
C. Bảo đảm một sự kiện chỉ được ghi một lần trong JVM.
D. Nhãn giúp backend phân loại, lọc hoặc định tuyến event.
Đáp án đúng: D

Câu 30: Log4j2 ghi event ở appender logger con và logger cha; cần xem cơ chế nào?
A. Số placeholder trong message được cung cấp bởi caller.
B. Additivity và cấu hình appender của Logger cha.
C. Thời điểm bytecode class gọi Logger được JVM biên dịch.
D. Thứ tự ánh xạ placeholder vào message của lời gọi Logger.
Đáp án đúng: B

Câu 31: Khi chuyển bản ghi JUL vào SLF4J bằng bridge, cấu hình nào cần tránh?
A. Hai bridge ngược chiều có thể tạo vòng lặp log.
B. Bridge JUL sang SLF4J cùng một provider được hỗ trợ.
C. Kiểm tra ánh xạ mức log giữa JUL và backend đích.
D. Kiểm tra duplication khi các Handler cũ vẫn tồn tại.
Đáp án đúng: A

Câu 32: Ứng dụng vô tình có hai SLF4J 2.x provider trên classpath; nên xử lý ra sao?
A. Mặc định gửi mỗi event tới cả hai backend để tăng dự phòng.
B. Hạ mọi mức log xuống WARN để tự xử lý việc chọn provider.
C. Giữ một provider sau khi đã kiểm tra xung đột.
D. Xóa mọi appender vì facade tự chuyển sang System.out.
Đáp án đúng: C

Câu 33: Thread pool tái sử dụng thread và MDC còn userId từ request trước; cần làm gì?
A. Giữ nguyên MDC vì cùng thread phải phục vụ đúng một user.
B. Tạo Logger mới mỗi request để tự reset metadata thread.
C. Đưa userId vào tên file để không cần làm sạch MDC.
D. Xóa hoặc khôi phục MDC khi tác vụ kết thúc, kể cả lỗi.
Đáp án đúng: D

Câu 34: Khi CompletableFuture chuyển sang executor khác, MDC thường cần xử lý ra sao?
A. MDC tự đồng bộ mọi thread mà không cần thao tác nào.
B. Truyền context sang executor, khôi phục sau tác vụ.
C. Chỉ đổi tên thread để MDC hiện diện ở callback mới.
D. Gọi Thread.sleep cho tới khi metadata tự chuyển qua.
Đáp án đúng: B

Câu 35: Dùng MDC với virtual threads cần lưu ý điểm nào?
A. Mọi virtual thread tự chia sẻ context của request khác.
B. MDC bị vô hiệu hóa trên tất cả virtual threads.
C. Mỗi virtual thread tự tạo trace ID dùng xuyên mạng.
D. Thiết lập context cho đúng virtual thread và vòng đời tác vụ.
Đáp án đúng: D

Câu 36: Ứng dụng kết hợp JUL, SLF4J và Log4j2; giả định nào cần tránh?
A. Giả định cả ba thư viện có một MDC chung mặc định.
B. Mỗi hệ thống có cách ghi metadata ngữ cảnh riêng.
C. Cần kiểm tra bridge khi nhiều backend cùng được dùng.
D. Context được dọn khi vòng đời tác vụ kết thúc.
Đáp án đúng: A

Câu 37: Một request đi qua nhiều service; chính sách correlation ID nào tốt?
A. Giữ ID từ biên hoặc tạo mới, rồi chuyển tới các service.
B. Mỗi service tự tạo ID khác mà không cần quan hệ liên kết.
C. Dùng hashCode của Logger làm ID cho toàn hệ thống.
D. Ghép các log chỉ dựa trên timestamp phát sinh gần nhau.
Đáp án đúng: A

Câu 38: Khi đã có distributed tracing, trường nào thường nối log với trace?
A. Tên class Logger và số ký tự trong từng message.
B. Request ID cục bộ và tên Logger ở mỗi service.
C. Trace ID và span ID theo đúng context hiện hành của request.
D. Mức nghiêm trọng cao nhất được cấu hình ở backend.
Đáp án đúng: C

Câu 39: Schema structured logging nên quản lý tên trường ổn định vì sao?
A. Để không cần mức log hoặc filter ở bất kỳ backend nào.
B. Để collector tự giải mã mọi bí mật chứa trong message.
C. Để JVM tự ghi các request theo đúng thứ tự nghiệp vụ.
D. Để dashboard và truy vấn ổn định khi message thay đổi.
Đáp án đúng: D

Câu 40: Một trường latencyMs được ghi là chuỗi JSON; rủi ro chính là gì?
A. Collector chắc chắn chuyển chuỗi thành số millisecond.
B. Trường được tự động xem thành severity của sự kiện.
C. Mọi giá trị sẽ được sắp theo timestamp của request.
D. Tính toán và phân vị khó hoặc sai do mất kiểu số.
Đáp án đúng: D

Câu 41: Event phát sinh trước lúc collector nhận khá lâu; cần phân biệt gì?
A. Thời gian event xảy ra và thời gian ingest vào hệ log.
B. Thời gian ingest luôn chính là lúc nghiệp vụ kết thúc.
C. Thứ tự trong file thay thế được mọi trường timestamp.
D. Thread ID cho biết chính xác thời điểm event phát sinh.
Đáp án đúng: A

Câu 42: Log từ nhiều múi giờ cần chọn quy ước timestamp nào?
A. Bỏ timezone vì collector luôn đoán đúng theo vị trí host.
B. Ghi timezone rõ ràng và chuẩn hóa khi phân tích truy vấn.
C. Dùng giờ local không offset làm chuẩn chung của hệ thống.
D. Chỉ ghi ngày, bỏ giờ để tránh nhầm thời điểm trong ngày.
Đáp án đúng: B

Câu 43: Endpoint phát rất nhiều DEBUG event; giải pháp chi phí nào hợp lý?
A. Sampling tùy ý cả audit bắt buộc để giảm dung lượng.
B. Nâng DEBUG thành ERROR để hệ thống tự lọc bớt.
C. Ghi cùng event vào nhiều appender để không bỏ sót.
D. Lấy mẫu debug, giữ thống kê tổng hợp có ý nghĩa.
Đáp án đúng: D

Câu 44: Trường nào làm metrics label tăng cardinality mạnh nhất?
A. Dùng mã loại lỗi trong một tập hữu hạn làm nhãn.
B. Dùng tên môi trường dev hoặc prod làm nhãn.
C. Dùng requestId riêng từng request làm nhãn lâu dài.
D. Dùng tên service ổn định do cấu hình quản lý.
Đáp án đúng: C

Câu 45: Trước khi đưa event có token vào pipeline log, nên làm gì?
A. Đợi collector lưu rồi chỉ ẩn token trên dashboard.
B. Đưa token vào MDC vì JSON layout tự mã hóa mọi key.
C. Chỉ ghi token ở TRACE vì mức này không thể bị lưu.
D. Che hoặc giảm dữ liệu nhạy cảm trước khi ghi vào sink.
Đáp án đúng: D

Câu 46: Khi debug lỗi xác thực, chính sách với password/API key nào phù hợp?
A. Ghi nguyên secret trong TRACE rồi xóa MDC khi xong.
B. Không ghi giá trị gốc ngay cả khi DEBUG được bật.
C. Đổi secret thành Base64 để được xem là đã bảo mật.
D. Ghi secret vào file nhưng chỉ xoay file mỗi ngày.
Đáp án đúng: B

Câu 47: User input chứa CRLF được ghép vào text log; rủi ro nào cần kiểm soát?
A. Có thể chèn dòng giả hoặc làm parser nhật ký đọc sai.
B. Chỉ thay đổi hiển thị, không tác động đến quá trình parse file.
C. Mọi backend tự lọc toàn bộ CRLF không cần cấu hình.
D. Formatter text luôn tự escape newline của dữ liệu người dùng.
Đáp án đúng: A

Câu 48: Log có dữ liệu cá nhân cần chính sách vận hành nào?
A. Lưu vô hạn vì dung lượng lưu trữ có thể được mở rộng.
B. Ẩn dữ liệu trên dashboard, vẫn cho đọc file gốc tự do.
C. Giảm dữ liệu, hạn lưu trữ và quyền đọc theo mục đích.
D. Đổi log sang TRACE để thông tin tự được bảo mật.
Đáp án đúng: C

Câu 49: Audit log cho thao tác đổi quyền khác debug log ở yêu cầu nào?
A. Có thể bỏ tùy ý khi queue đầy như mọi debug event.
B. Cần toàn vẹn, truy vết và quyền đọc chặt chẽ hơn.
C. Không cần actor hoặc kết quả nếu đã có timestamp.
D. Phải dùng TRACE để giảm dung lượng dữ liệu ghi.
Đáp án đúng: B

Câu 50: Ứng dụng chuyển log tới collector qua mạng nên chú ý biện pháp nào?
A. Đổi phần mở rộng file từ .log thành .json trước khi gửi.
B. Xác thực collector và mã hóa kết nối vận chuyển log.
C. Giảm mức WARN xuống INFO để tránh bị đọc nội dung.
D. Chỉ dùng cổng TCP mặc định để xác nhận collector tin cậy.
Đáp án đúng: B

Câu 51: Khi collector tạm ngừng hoạt động, phương án nào phù hợp?
A. Giữ hàng đợi trong heap vô hạn đến khi collector quay lại.
B. Chặn mọi request vô thời hạn vì event DEBUG luôn bắt buộc.
C. Bỏ toàn bộ audit event khi mất kết nối mà không báo.
D. Bộ đệm hữu hạn, retry và chính sách ứng phó quá tải.
Đáp án đúng: D

Câu 52: Đội vận hành cần giảm chi phí logging tập trung; cách nào hợp lý?
A. Quản lý level, sampling, kích thước event và thời gian giữ.
B. Nhân bản cùng thông điệp vào nhiều index để tiện truy vấn.
C. Bật TRACE liên tục cho mọi thư viện trong production.
D. Chuyển các trường số thành chuỗi dài để giữ chi tiết.
Đáp án đúng: A

Câu 53: Vai trò của logs, metrics và traces khác nhau thế nào?
A. Logs chính xác tuyệt đối, metrics chỉ dành cho ứng dụng desktop.
B. Traces thay thế được mọi bản ghi audit có yêu cầu bảo toàn.
C. Metrics giữ từng event chi tiết, logs chỉ lưu số liệu tổng hợp.
D. Logs ghi event; metrics tổng hợp; traces liên kết luồng request.
Đáp án đúng: D

Câu 54: Cùng một exception bị log ở nhiều tầng rồi ném tiếp; tác động nào thường có?
A. JVM loại bản sao stack trace trước khi chuyển cho backend.
B. Backend tự khử trùng khi Throwable vẫn cùng instance.
C. Nhiều event trùng lỗi làm tăng nhiễu và chi phí điều tra.
D. Exception mất chuỗi nguyên nhân sau lần log thứ hai.
Đáp án đúng: C

Câu 55: Chỉ ghi exception.getMessage() khi có lỗi production dễ thiếu điều gì?
A. Thiếu loại exception, stack trace và chuỗi cause gốc.
B. Thiếu tên appender cùng thời điểm cuộn file gần nhất.
C. Thiếu số placeholder đã thay trong message của Logger.
D. Thiếu độ ưu tiên của thread ở thời điểm ghi event.
Đáp án đúng: A

Câu 56: Một service ghi ERROR rồi ném lại để API layer cũng ghi; nên rà điều gì?
A. Chọn điểm chịu trách nhiệm ghi lỗi để tránh log trùng nhau.
B. Ghi thêm ERROR tại mọi method để giữ thứ tự call stack.
C. Tắt stack trace vì hai tầng đã có bản tin cho cùng lỗi.
D. Đổi tên Logger để backend tự loại những bản ghi giống.
Đáp án đúng: A

Câu 57: Trong vòng lặp xử lý hàng triệu bản ghi, cách ghi log nào phù hợp?
A. Ghi TRACE cho từng phép gán rồi gửi toàn bộ lên collector.
B. Ghi một event vào nhiều appender để tăng độ tin cậy.
C. Gộp thống kê theo lô và ghi rõ những lỗi quan trọng.
D. Bỏ toàn bộ số liệu lỗi để không tốn CPU định dạng log.
Đáp án đúng: C

Câu 58: Một lỗi lặp lại hàng nghìn lần mỗi phút; cách xử lý nhiễu nào tốt?
A. Giới hạn tốc độ và đếm những sự kiện bị lược bỏ.
B. Đổi WARN thành INFO nhưng vẫn phát mọi bản log cũ.
C. Tạo Logger mới cho từng lần cảnh báo để chia đều tải.
D. Đính kèm exception giả để các event được ưu tiên hơn.
Đáp án đúng: A

Câu 59: Vì sao không suy thứ tự nghiệp vụ từ log của nhiều worker async?
A. Async logging tự sắp toàn bộ event theo timestamp gốc.
B. Backend luôn sắp theo tên Logger trước lúc xuất bất kỳ file.
C. Correlation ID tự khóa thứ tự ghi xuyên các máy chủ.
D. Lịch thread và queue có thể làm event tới đích lệch thứ tự.
Đáp án đúng: D

Câu 60: Trước khi shutdown ứng dụng dùng async logging, cần làm gì?
A. Dừng JVM ngay vì queue tự có khả năng phục hồi bền vững.
B. Gỡ mọi appender trước khi chờ xả để tránh log lặp.
C. Xử lý event còn trong queue và đóng backend đúng vòng đời.
D. Bật TRACE trong giai đoạn dừng để khôi phục event đã mất.
Đáp án đúng: C

Câu 61: File log chạy nhiều ngày cần cơ chế vận hành nào?
A. Rotation, nén, retention và giới hạn dung lượng lưu.
B. Một file duy nhất không giới hạn kích thước trong cả đời JVM.
C. Chỉ chuyển mức WARN thành INFO để tự xóa lịch sử.
D. Tăng số thread ghi đĩa để dữ liệu cũ được loại bỏ.
Đáp án đúng: A

Câu 62: Với container đã có công cụ thu stdout, định hướng nào thường phù hợp?
A. Bắt buộc ghi file vào filesystem tạm của container đang chạy.
B. Ghi stdout/stderr để nền tảng thu thập và quản lý log.
C. Tạo một file cho mỗi virtual thread và giữ tới khi deploy.
D. Chỉ giữ file log cục bộ, không cấu hình collector tập trung.
Đáp án đúng: B

Câu 63: Java Flight Recorder bổ sung gì cho application logging?
A. Thay thế hoàn toàn các audit log cần lưu vết có toàn vẹn.
B. Telemetry JVM chuyên sâu bên cạnh event nghiệp vụ từ log.
C. Tự ghi toàn bộ nghiệp vụ nếu ứng dụng bật mức TRACE.
D. JFR chỉ ghi những event nghiệp vụ đã qua Logger của ứng dụng.
Đáp án đúng: B

Câu 64: Muốn unit test level và structured fields của event, cách nào bền?
A. Dùng test appender để kiểm tra level và metadata thực tế.
B. So khớp toàn bộ stdout tới từng dấu cách và timestamp.
C. Kiểm tra số dòng xuất ra, không xác minh field trong event.
D. Bật TRACE mọi thư viện rồi coi không có lỗi là đủ.
Đáp án đúng: A
