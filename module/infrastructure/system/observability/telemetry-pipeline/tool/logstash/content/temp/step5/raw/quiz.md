Câu 1. Trong pipeline Logstash thông thường, ba giai đoạn chính được thực hiện theo thứ tự nào?
A. Filter, input, rồi output.
B. Output, input, rồi filter.
C. Input, filter, rồi output.
D. Input, output, rồi filter.
Đáp án đúng: C

Câu 2. Khối `input` trong cấu hình Logstash chịu trách nhiệm chính nào?
A. Phân tích message và chuẩn hóa các trường dữ liệu.
B. Nhận sự kiện từ nguồn như Beats, file hoặc TCP.
C. Chọn index đích và gửi sự kiện tới Elasticsearch.
D. Lưu sự kiện vào dashboard để người dùng truy vấn.
Đáp án đúng: B

Câu 3. Một filter plugin trong Logstash thường thực hiện công việc gì?
A. Nhận kết nối mạng từ shipper và tạo event mới.
B. Chuẩn hóa hoặc bổ sung dữ liệu cho event.
C. Gửi event đã xử lý tới hệ thống lưu trữ đích.
D. Quản lý lịch sử đăng nhập của người vận hành.
Đáp án đúng: B

Câu 4. Output block trong Logstash có thể làm gì với một event?
A. Gửi event tới một hoặc nhiều đích phù hợp.
B. Chỉ lưu event vào bộ nhớ trong cùng pipeline.
C. Chỉ thay đổi kiểu dữ liệu của các trường event.
D. Chỉ đọc cấu hình và không xử lý event runtime.
Đáp án đúng: A

Câu 5. Grok filter phù hợp nhất với loại dữ liệu đầu vào nào?
A. Dữ liệu có delimiter ổn định và vị trí trường cố định.
B. JSON hợp lệ đã được parse thành object trong event.
C. Log dạng văn bản có cấu trúc cần phân tích bằng pattern.
D. Metric số đã được chia thành bucket theo ngưỡng.
Đáp án đúng: C

Câu 6. Trong Grok, pattern `%{IP:client_ip}` có ý nghĩa gì?
A. Bắt địa chỉ IP và lưu vào field `client_ip`.
B. Kiểm tra field `client_ip` có tồn tại trong event.
C. Đổi địa chỉ IP thành tên host trước khi output.
D. Xóa field IP sau khi pattern được áp dụng.
Đáp án đúng: A

Câu 7. Dissect filter thường có lợi thế nào so với Grok?
A. Phân tích tốt hơn khi định dạng log thay đổi tùy ý.
B. Tự suy luận mọi trường mà không cần khai báo delimiter.
C. Tách trường nhanh khi cấu trúc và delimiter ổn định.
D. Tự chuyển event thành ECS mà không cần mapping.
Đáp án đúng: C

Câu 8. Khi log có cấu trúc thay đổi nhiều và cần pattern linh hoạt, nên ưu tiên gì?
A. Dissect với vị trí delimiter cố định cho mọi biến thể.
B. Date filter để tự nhận diện toàn bộ cấu trúc log.
C. Grok với pattern phù hợp cho các biến thể định dạng.
D. Mutate filter để trích xuất trường bằng regex.
Đáp án đúng: C

Câu 9. Date filter chủ yếu dùng để làm gì?
A. Đổi thời điểm scrape của mọi input plugin trong pipeline.
B. Thêm ngày hiện tại vào tên index Elasticsearch.
C. Sắp xếp event theo thứ tự trước khi chạy output.
D. Phân tích timestamp trong event và gán vào `@timestamp`.
Đáp án đúng: D

Câu 10. Mutate filter hỗ trợ thao tác nào với field?
A. Tạo kết nối Beats và nhận dữ liệu từ shipper.
B. Đổi tên, xóa, convert hoặc cập nhật field.
C. Chạy truy vấn Elasticsearch để cập nhật index mapping.
D. Nén queue và xác nhận event đã được output.
Đáp án đúng: B

Câu 11. JSON filter thường được dùng trong tình huống nào?
A. Ghép nhiều dòng log thành một event duy nhất.
B. Parse JSON trong field thành cấu trúc event.
C. Tách log theo delimiter mà không cần JSON parser.
D. Gửi JSON trực tiếp tới output mà không tạo event.
Đáp án đúng: B

Câu 12. Điều kiện `if [level] == "error"` trong Logstash dùng để làm gì?
A. Tạo field `level` mới nếu event chưa có field đó.
B. Đổi mọi giá trị `level` thành chuỗi error.
C. Dừng pipeline khi gặp event có severity error.
D. Điều kiện kiểm tra field `level` bằng error.
Đáp án đúng: D

Câu 13. Khi Grok không parse được message, tag mặc định thường được dùng là gì?
A. Tag `_grokparsefailure` cho event không parse được.
B. `_jsonparsefailure` để nhận diện event parse lỗi.
C. `_dateparsefailure` để nhận diện event parse lỗi.
D. `_elasticsearchfailure` để nhận diện event parse lỗi.
Đáp án đúng: A

Câu 14. ECS trong hệ sinh thái Elastic nhằm đạt mục tiêu nào?
A. Chuẩn hóa tên field để dữ liệu từ nguồn khác nhau nhất quán.
B. Mã hóa toàn bộ event trước khi gửi sang Elasticsearch.
C. Tăng tốc Grok bằng cách thay regex bằng delimiter.
D. Định nghĩa thứ tự chạy input, filter và output plugin.
Đáp án đúng: A

Câu 15. Field `event.original` theo ECS thường lưu loại dữ liệu nào?
A. Timestamp chuẩn hóa được gán sau date filter.
B. Tên index mà Elasticsearch output sẽ ghi event.
C. Danh sách tag được thêm khi Grok parse thất bại.
D. Giữ lại message nguyên bản trước khi parse.
Đáp án đúng: D

Câu 16. Tùy chọn `target` của Grok hoặc JSON filter có thể dùng để làm gì?
A. Chọn host Elasticsearch sẽ nhận event sau filter.
B. Đặt tên pipeline được Logstash khởi chạy.
C. Chuyển event sang Persistent Queue trước khi parse.
D. Đặt các field được parse vào một namespace đích.
Đáp án đúng: D

Câu 17. `pipeline.ecs_compatibility` trong Logstash chủ yếu kiểm soát điều gì?
A. Tên index Elasticsearch được tạo cho từng pipeline.
B. Mức độ nén event trước khi ghi vào Persistent Queue.
C. Thiết lập ECS mode mặc định cho plugin tương thích.
D. Thứ tự chạy các filter plugin trong pipeline.
Đáp án đúng: C

Câu 18. Nếu muốn route event lỗi parse sang index riêng, cách nào phù hợp?
A. Đổi `@timestamp` để Elasticsearch tự chọn index lỗi.
B. Tăng `pipeline.workers` để event lỗi chạy riêng.
C. Gắn tag khi parse lỗi rồi dùng conditional trong output.
D. Dùng Persistent Queue để tự phân loại event theo tag.
Đáp án đúng: C

Câu 19. Một Elasticsearch output cấu hình `hosts` thường chỉ định điều gì?
A. Danh sách node Elasticsearch nhận request.
B. Tên field chứa message gốc trước khi parse.
C. Pattern Grok dùng để tách dữ liệu từ event.
D. Thư mục lưu Persistent Queue của pipeline.
Đáp án đúng: A

Câu 20. Tham số `index` trong Elasticsearch output thường quyết định điều gì?
A. Tên input plugin dùng để nhận event.
B. Tên index đích mà event được ghi vào.
C. Tên filter plugin được áp dụng cuối pipeline.
D. Tên field dùng để parse timestamp.
Đáp án đúng: B

Câu 21. Vì sao Elasticsearch output thường gửi event theo bulk request?
A. Gửi nhiều document trong một request để giảm overhead.
B. Đảm bảo mỗi document được ghi đồng bộ riêng lẻ.
C. Tránh phải xử lý mapping của index đích.
D. Tự động loại bỏ event trùng lặp theo message.
Đáp án đúng: A

Câu 22. Persistent Queue trong Logstash cung cấp khả năng nào?
A. Lưu dashboard và lịch sử truy vấn của Kibana.
B. Lưu event trên đĩa để chịu được restart và gián đoạn ngắn.
C. Lưu riêng các event bị Elasticsearch từ chối vĩnh viễn.
D. Tự động sao chép event sang mọi output đã cấu hình.
Đáp án đúng: B

Câu 23. Để bật Persistent Queue cho Logstash, thiết lập nào thường được dùng?
A. Đặt `dead_letter_queue.enable: true` trong pipeline.
B. Đặt `queue.type: persisted` trong cấu hình Logstash.
C. Thêm `persistent => true` vào mọi input plugin.
D. Đặt `queue.type: memory` trong cấu hình Logstash.
Đáp án đúng: B

Câu 24. Khi Persistent Queue đầy, Logstash thường tạo ra hành vi nào?
A. Tự xóa event cũ nhất để luôn nhận event mới.
B. Chuyển mọi event mới sang Dead Letter Queue.
C. Queue đầy sẽ tạo backpressure lên input.
D. Tăng vô hạn dung lượng queue mà không cần cấu hình.
Đáp án đúng: C

Câu 25. Vì sao Persistent Queue không bảo đảm xử lý exactly-once end-to-end?
A. Queue chỉ lưu metadata, không lưu payload event.
B. Output plugin không bao giờ retry khi mất kết nối.
C. Event bị xóa ngay khi input plugin vừa nhận dữ liệu.
D. Có thể phát lại event sau lỗi và tạo duplicate.
Đáp án đúng: D

Câu 26. Dead Letter Queue thường lưu loại event nào?
A. Mọi event đã xử lý thành công và được index đầy đủ.
B. Event mới nhận nhưng chưa chạy qua filter plugin.
C. Mọi event bị drop có chủ đích bởi conditional filter.
D. Event lỗi output không retry được có thể vào DLQ.
Đáp án đúng: D

Câu 27. Một lỗi mapping kiểu dữ liệu khi ghi Elasticsearch thường có thể dẫn event vào đâu?
A. Persistent Queue của pipeline trước khi filter được chạy.
B. Grok pattern registry để tự sinh pattern mới.
C. Lỗi mapping không retry được có thể vào DLQ.
D. Index template để Elasticsearch tự sửa document.
Đáp án đúng: C

Câu 28. Lỗi kết nối Elasticsearch tạm thời hoặc HTTP 429 thường nên xử lý thế nào?
A. Retry lỗi tạm thời theo cơ chế output plugin.
B. Chuyển ngay mọi event liên quan sang DLQ.
C. Drop event để giải phóng worker và queue.
D. Đổi field mapping của event trước khi retry.
Đáp án đúng: A

Câu 29. Muốn xử lý lại event trong DLQ, plugin nào có thể đọc chúng?
A. Elasticsearch input plugin để đọc lại document.
B. Persistent Queue output plugin để nạp event từ disk.
C. Grok filter plugin để lấy record trong DLQ.
D. Dùng dead_letter_queue input plugin để đọc lại event.
Đáp án đúng: D

Câu 30. Vì sao cần giới hạn dung lượng và theo dõi DLQ?
A. DLQ có thể tăng liên tục và chiếm dung lượng đĩa.
B. DLQ tự xóa event ngay khi Elasticsearch phục hồi.
C. DLQ chỉ lưu tên event nên không tiêu tốn đĩa.
D. DLQ tự động nén toàn bộ event theo thời gian.
Đáp án đúng: A

Câu 31. `pipeline.workers` trong Logstash chủ yếu kiểm soát điều gì?
A. Số input plugin được phép khai báo trong một file.
B. Số index Elasticsearch mà một event có thể ghi.
C. Số worker thread xử lý batch trong pipeline.
D. Số ngày dữ liệu được giữ trong Persistent Queue.
Đáp án đúng: C

Câu 32. Tăng `pipeline.batch.size` có thể tạo ra trade-off nào?
A. Giảm bộ nhớ luôn luôn và không ảnh hưởng latency.
B. Tăng độ chính xác Grok mà không đổi tài nguyên.
C. Tắt retry của output để xử lý event nhanh hơn.
D. Throughput có thể tăng nhưng tốn thêm memory.
Đáp án đúng: D

Câu 33. `pipeline.batch.delay` ảnh hưởng chủ yếu đến điều gì?
A. Thời gian chờ gom batch và độ trễ xử lý event.
B. Thời gian giữ event trong DLQ trước khi xóa.
C. Khoảng thời gian Logstash reload file cấu hình.
D. Thời gian chờ Elasticsearch tạo index mới.
Đáp án đúng: A

Câu 34. Khi input nhận event nhanh hơn output xử lý, dấu hiệu nào cần theo dõi?
A. Grok pattern tự động giảm số capture group.
B. ECS tự đổi tên field để giảm tốc độ input.
C. Index Elasticsearch tự chuyển sang chế độ read-only ngay.
D. Queue tăng, backpressure và độ trễ event tăng.
Đáp án đúng: D

Câu 35. Multiline log nên được ghép ở đâu để tránh các dòng của nhiều event bị xen kẽ?
A. Trong output Elasticsearch sau khi document đã được ghi.
B. Trong Grok filter sau khi mọi worker đã xử lý riêng từng dòng.
C. Trong Kibana Discover sau khi người dùng mở dữ liệu.
D. Ở shipper hoặc input phù hợp trước khi xử lý song song.
Đáp án đúng: D

Câu 36. Cách nào phù hợp để giữ thông tin xác thực Elasticsearch khỏi file pipeline rõ?
A. Đặt username và password trực tiếp trong trường `message`.
B. Dùng Logstash keystore hoặc biến môi trường được quản lý.
C. Lưu mật khẩu trong tag để output plugin đọc khi cần.
D. Ghi credential vào comment trong file YAML triển khai.
Đáp án đúng: B

Câu 37. Khi bảo vệ luồng Beats đến Logstash và Logstash đến Elasticsearch, nên làm gì?
A. Chỉ đổi port mặc định và giữ kết nối không mã hóa.
B. Bật TLS và xác minh chứng chỉ ở các kết nối hỗ trợ.
C. Chỉ mã hóa Persistent Queue nhưng không bảo vệ mạng.
D. Tắt xác thực để shipper có thể gửi event liên tục.
Đáp án đúng: B

Câu 38. Lệnh nào giúp kiểm tra cấu hình Logstash trước khi chạy pipeline?
A. `bin/logstash --queue.verify -f pipeline.conf`.
B. `bin/logstash --grok.test_and_exit -f pipeline.conf`.
C. `bin/logstash --config.test_and_exit -f pipeline.conf`.
D. `bin/logstash --elasticsearch.check -f pipeline.conf`.
Đáp án đúng: C

Câu 39. Để kiểm tra event đã qua filter trông như thế nào trong lúc phát triển, output nào hữu ích?
A. `dead_letter_queue` để ghi mọi event parse thành công.
B. `stdout` với codec `rubydebug` để xem cấu trúc event.
C. `persistent_queue` để in từng field ra terminal.
D. `elasticsearch` với index production đang nhận dữ liệu.
Đáp án đúng: B

Câu 40. Khi Grok failure tăng sau một thay đổi ứng dụng nguồn, nên điều tra gì trước?
A. Mẫu log mới và Grok pattern đang dùng để parse.
B. Kích thước Persistent Queue và lịch checkpoint của nó.
C. TLS certificate của Elasticsearch output cluster.
D. Số lượng dashboard và refresh interval trong Kibana.
Đáp án đúng: A
