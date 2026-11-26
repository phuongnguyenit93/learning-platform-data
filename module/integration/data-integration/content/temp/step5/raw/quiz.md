Câu 01. Pipeline muốn dùng khả năng SQL của data warehouse để biến đổi sau khi nạp dữ liệu; mô hình nào phù hợp?
A. CDC: thu log giao dịch rồi bỏ qua biến đổi
B. Batch: gom dữ liệu theo lịch trước khi nạp vào kho
C. ETL: biến đổi tại nguồn rồi mới chuyển sang kho đích
D. ELT: nạp dữ liệu trước, biến đổi trong kho đích
Đáp án đúng: D

Câu 02. Nguồn là cơ sở dữ liệu giao dịch đang chịu tải cao; rủi ro chính khi liên tục quét toàn bảng để đồng bộ là gì?
A. Tăng nguy cơ ghi trùng khi chưa có khóa idempotent
B. Làm khó bảo toàn thứ tự event khi nạp song song
C. Tăng độ trễ truyền dữ liệu từ kho đích tới báo cáo
D. Tăng tải đọc ở nguồn, ảnh hưởng truy vấn giao dịch
Đáp án đúng: D

Câu 03. Báo cáo tài chính chỉ cần cập nhật sau giờ chốt sổ mỗi ngày; cách xử lý nào phù hợp với yêu cầu này?
A. Stream từng sự kiện với thời gian phản hồi mili giây
B. Đồng bộ toàn bộ bảng sau mỗi request của dashboard
C. Chạy batch theo lịch trên một khoảng dữ liệu rõ ràng
D. Đọc log CDC riêng cho từng ô trong báo cáo tổng hợp
Đáp án đúng: C

Câu 04. Dashboard vận hành cần thấy giao dịch mới trong vài giây; cách tích hợp nào đáp ứng trực tiếp?
A. Xử lý sự kiện gần thời gian thực qua streaming
B. Chạy full snapshot định kỳ vào cuối mỗi ngày
C. Làm mới báo cáo thủ công mỗi khi người dùng mở
D. Lấy dữ liệu từ bản xuất CSV của ca trước
Đáp án đúng: A

Câu 05. Trong đồng bộ cơ sở dữ liệu, đặc điểm chính của CDC dựa trên transaction log là gì?
A. Quét mọi dòng có created_at mới hơn lần đồng bộ
B. So sánh checksum cả bảng ở hai lần xuất dữ liệu
C. Đọc bản backup hàng ngày để tìm các bản ghi mới
D. Đọc các thay đổi đã ghi vào log giao dịch nguồn
Đáp án đúng: D

Câu 06. Khi kết hợp snapshot ban đầu và CDC, cách nào hạn chế bỏ sót thay đổi xảy ra lúc chụp snapshot?
A. Đặt watermark bằng giờ máy chạy sau khi chụp xong
B. Gắn snapshot nhất quán với vị trí log để nối luồng
C. Bỏ các event CDC có khóa xuất hiện trong snapshot
D. Đọc log từ lúc snapshot đã ghi xong vào kho đích
Đáp án đúng: B

Câu 07. Pipeline incremental nạp xong dữ liệu nhưng chưa cập nhật checkpoint thì bị dừng; quy tắc an toàn nhất là gì?
A. Cập nhật checkpoint ngay khi bắt đầu đọc nguồn mới
B. Xóa checkpoint khi worker bị tắt đột ngột giữa batch
C. Xác nhận checkpoint sau khi ghi đích thành công
D. Lấy thời điểm chạy job làm checkpoint trước khi nạp
Đáp án đúng: C

Câu 08. Nhiều bản ghi có cùng updated_at; muốn lấy incremental không bỏ sót, nên đặt bookmark thế nào?
A. Lưu cặp updated_at và khóa duy nhất theo thứ tự
B. Chỉ lưu thời gian job chạy gần nhất ở máy worker
C. Chỉ lưu updated_at rồi truy vấn với điều kiện lớn hơn
D. Lưu số lượng bản ghi đọc thay cho định danh nguồn
Đáp án đúng: A

Câu 09. Sink đồng bộ bảng khách hàng nhận sự kiện delete từ CDC; xử lý nào giữ trạng thái đích phù hợp nguồn?
A. Đổi delete thành update timestamp của bản ghi cũ
B. Chỉ phát sinh bản ghi audit mà giữ nguyên bản đích
C. Áp dụng xóa hoặc cờ xóa tương ứng tại bảng đích
D. Chuyển delete thành insert mới với khóa hiện tại
Đáp án đúng: C

Câu 10. Một connector có ngữ nghĩa at-least-once, vì sao sink cần thiết kế idempotent?
A. Việc tăng số consumer sẽ làm các sự kiện trùng biến mất
B. Checkpoint của connector tự loại bỏ trùng ở mọi kho
C. Một sự kiện có thể gửi lại nên ghi lặp phải an toàn
D. Mọi sự kiện đều đến đúng một lần theo thứ tự toàn cục
Đáp án đúng: C

Câu 11. Nạp lại sự kiện cập nhật khách hàng nhiều lần; thiết kế nào phù hợp để hạn chế tạo bản ghi trùng?
A. Upsert theo khóa nghiệp vụ cùng phiên bản từ nguồn
B. Insert thêm dòng với ID tự tăng mỗi khi nhận event
C. Gắn UUID ngẫu nhiên mới cho từng lần ghi lại event
D. Chọn bản ghi có giờ xử lý mới hơn làm bản có hiệu lực
Đáp án đúng: A

Câu 12. Muốn tránh kết quả ghi trùng khi consumer crash giữa ghi sink và commit offset, cần cơ chế nào?
A. Tiến offset trước khi ghi để tránh nhận event lần nữa
B. Phối hợp checkpoint với sink transaction hoặc idempotent
C. Tăng concurrency consumer để bù lại các lần đọc lặp
D. Chỉ bật tính năng chống trùng tại broker là đủ cho sink
Đáp án đúng: B

Câu 13. Sự kiện cảm biến đến trễ 20 phút; muốn tính theo lúc đo thực tế, loại thời gian nào cần dùng?
A. Processing time khi worker bắt đầu xử lý sự kiện
B. Event time lấy từ lúc sự kiện được tạo tại nguồn
C. Ingestion time khi hệ thống đích ghi dữ liệu vào kho
D. Deployment time của phiên bản worker đang nhận sự kiện
Đáp án đúng: B

Câu 14. Một event đến sau watermark đã đóng cửa sổ tổng hợp; cơ chế nào xử lý được dữ liệu muộn?
A. Cho phép late update hoặc ghi sang luồng xử lý bù
B. Gán event time bằng processing time khi nhận muộn
C. Reset toàn bộ checkpoint mỗi khi phát hiện event trễ
D. Tăng số partition để cửa sổ cũ tự mở lại khi có dữ liệu
Đáp án đúng: A

Câu 15. Yêu cầu tổng hợp mỗi sự kiện vào đúng một khoảng 10 phút không chồng lấp; dùng loại window nào?
A. Session window với khoảng im lặng 10 phút
B. Global window gom toàn bộ event của một luồng
C. Tumbling window 10 phút theo event time
D. Sliding window 10 phút bước trượt 1 phút
Đáp án đúng: C

Câu 16. Sự kiện cập nhật cùng customer_id phải được xử lý theo thứ tự ở Kafka; nên chọn partition key nào?
A. Dùng số lần retry của message để quyết định partition
B. Dùng UUID ngẫu nhiên làm key để phân tải đều event
C. Dùng thời gian xử lý worker làm key cho mọi message
D. Dùng customer_id làm key để giữ thứ tự trong partition
Đáp án đúng: D

Câu 17. Nguồn bổ sung một trường nullable mà client cũ không dùng; cách quản lý schema nào phù hợp?
A. Thay kiểu dữ liệu cột cũ mà không kiểm tra downstream
B. Đổi khóa chính từ chuỗi sang object trong cùng schema
C. Thêm trường tùy chọn theo quy tắc tương thích schema
D. Xóa trường bắt buộc trước khi cập nhật các consumer
Đáp án đúng: C

Câu 18. Cần đổi tên trường amount đang được nhiều consumer sử dụng; cách phát hành nào giảm rủi ro nhất?
A. Sửa producer trước rồi đợi consumer tự phát hiện tên mới
B. Hỗ trợ cả tên cũ và mới trong một giai đoạn chuyển tiếp
C. Chỉ sửa mapping ở sink mà không thông báo consumer khác
D. Đổi tên trực tiếp và giữ nguyên schema version của luồng
Đáp án đúng: B

Câu 19. Cột customer_id là bắt buộc nhưng một số hàng nguồn để trống; cách nạp phù hợp khi có quy tắc quarantine?
A. Xóa cả batch và bỏ mọi bản ghi kiểm tra lỗi
B. Tạo customer_id ngẫu nhiên rồi cho qua validation
C. Nạp cả dòng lỗi vào bảng chính rồi xử lý sau
D. Cách ly dòng lỗi kèm lý do để xử lý và phát lại
Đáp án đúng: D

Câu 20. Tổng số dòng nguồn và đích bằng nhau nhưng dữ liệu vẫn có thể sai; cách đối soát nào mạnh hơn?
A. Đọc mã thoát job để xác nhận mọi giá trị đều đúng
B. So khóa và checksum nội dung theo phạm vi đối soát
C. Đo tốc độ xử lý rồi suy ra dữ liệu đã khớp nhau
D. Dùng tổng số dòng làm tiêu chí duy nhất cho batch
Đáp án đúng: B

Câu 21. Muốn phát hiện cùng một hóa đơn bị nạp nhiều lần vào bảng đích, phép kiểm tra nào trực tiếp nhất?
A. Đo độ trễ trung bình giữa hai lần nạp dữ liệu
B. Đếm trùng theo khóa nghiệp vụ của hóa đơn ở đích
C. So tốc độ đọc từ nguồn với tốc độ ghi ra kho
D. Kiểm tra số partition đang hoạt động trong broker
Đáp án đúng: B

Câu 22. Kho phân tích cần giữ lịch sử thay đổi địa chỉ khách hàng; mô hình SCD nào phù hợp?
A. Xóa phiên bản cũ sau khi ghi giá trị địa chỉ mới
B. SCD Type 1 ghi đè để chỉ giữ trạng thái mới nhất
C. SCD Type 2 tạo phiên bản có khoảng thời gian hiệu lực
D. Dùng partition mới cho mỗi lần chạy job nhập liệu
Đáp án đúng: C

Câu 23. Event CDC đến không đúng thứ tự vì retry; quy tắc nào tránh bản ghi cũ ghi đè bản mới?
A. Chọn event được gửi nhiều lần hơn để quyết định
B. Chọn event từ worker có độ trễ mạng thấp nhất
C. Chọn event có thời gian đến sink gần nhất để ghi
D. So phiên bản hoặc sequence nguồn trước khi upsert
Đáp án đúng: D

Câu 24. Phải nạp bù dữ liệu thiếu trong 2 giờ mà không tạo bản ghi trùng; cách thực hiện nào phù hợp?
A. Chạy lại toàn bộ lịch sử bằng thao tác insert thuần
B. Phát lại khoảng dữ liệu xác định qua sink idempotent
C. Đổi toàn bộ khóa đích rồi phát lại từng bản ghi
D. Lấy giờ hiện tại làm checkpoint và chạy lại job
Đáp án đúng: B

Câu 25. Một message luôn gây lỗi parse, làm consumer dừng tại cùng offset; cần xử lý thế nào?
A. Tăng số replica consumer để lỗi parse biến mất
B. Retry vô hạn trên cùng offset cho đến khi hết lỗi
C. Commit offset rồi xóa event mà không lưu bằng chứng
D. Retry hữu hạn rồi chuyển DLQ kèm ngữ cảnh lỗi
Đáp án đúng: D

Câu 26. API nguồn trả HTTP 429 kèm Retry-After trong lúc trích xuất; chiến lược retry phù hợp là gì?
A. Gửi lại lập tức bằng nhiều worker để tăng throughput
B. Reset checkpoint về đầu bảng mỗi khi gặp giới hạn
C. Tuân theo Retry-After và backoff có jitter, giới hạn
D. Đổi token mỗi lần retry nhằm bỏ qua quota của nguồn
Đáp án đúng: C

Câu 27. Pipeline đọc thông tin đăng nhập từ nhiều connector; cách quản lý credential nào phù hợp?
A. Dùng một tài khoản tích hợp toàn quyền trên mọi nguồn
B. Mã hóa mật khẩu trong file cấu hình thuộc repository
C. Chia sẻ một biến môi trường có token cho mọi connector
D. Lưu trong secret manager và cấp quyền theo nhiệm vụ
Đáp án đúng: D

Câu 28. Nguồn có PII nhưng kho đích chỉ cần thống kê vùng; thiết kế extraction nào giảm rủi ro?
A. Chỉ lấy trường cần dùng và ẩn danh dữ liệu nhạy cảm
B. Sao chép PII đầy đủ để dễ đối soát khi cần sửa lỗi
C. Ghi payload chứa PII vào log của từng job đồng bộ
D. Lưu bản raw không phân quyền để tiện tái xử lý dữ liệu
Đáp án đúng: A

Câu 29. Khi một KPI sai, cần truy ra nguồn và bước biến đổi tạo nên KPI; hệ thống cần lưu gì?
A. Data lineage thể hiện nguồn, phép biến đổi và đích
B. Log truy vấn cuối và thời gian chạy mỗi job định kỳ
C. Ảnh chụp schema kho dữ liệu vào cuối mỗi ngày
D. Bảng phân quyền kết nối giữa nguồn và từng worker
Đáp án đúng: A

Câu 30. SLA yêu cầu dữ liệu đơn hàng xuất hiện trong kho sau không quá 5 phút; metric nào đo trực tiếp?
A. Số bản ghi còn chờ trong hàng đợi của worker
B. Thời lượng chạy batch gần nhất của từng nguồn
C. Tỷ lệ job theo lịch kết thúc thành công mỗi ngày
D. Độ trễ từ cập nhật nguồn tới khi kho có dữ liệu
Đáp án đúng: D

Câu 31. CDC lag tăng liên tục dù nguồn vẫn phát event đều; nên đo nhóm tín hiệu nào để tìm nghẽn?
A. Consumer lag, throughput từng bước và latency sink
B. Số bản ghi tại nguồn, kích thước schema và RAM broker
C. Số worker hoạt động, số slot scheduler và giờ chạy
D. Dung lượng file staging, số lần rotate log và số batch
Đáp án đúng: A

Câu 32. Worker chết sau khi sink đã ghi một phần batch; cách phục hồi nào đáng tin cậy?
A. Phát lại batch bằng insert mới mà không kiểm tra khóa
B. Khôi phục từ checkpoint bền vững với sink idempotent
C. Bắt đầu từ thời điểm worker khởi động lại lần tiếp
D. Bật auto-commit offset ngay khi nhận một batch mới
Đáp án đúng: B

Câu 33. Job nạp một bảng phân tích không được để người đọc thấy dữ liệu nửa chừng; phương án nào phù hợp?
A. Đổi giờ chạy job để ít người truy cập trong lúc nạp
B. Ghi trực tiếp từng dòng rồi cập nhật dashboard liên tục
C. Chia dữ liệu thành nhiều file rồi công bố từng phần
D. Nạp vào staging và publish atomically sau kiểm tra
Đáp án đúng: D

Câu 34. Nguồn lưu thời gian có timezone khác kho đích; cách chuyển đổi nào giúp phép join chính xác?
A. Chuẩn hóa timezone theo quy tắc trước khi đối chiếu
B. Bỏ phần timezone trong chuỗi timestamp trước khi ghi
C. Dùng thời điểm load thay thế thời điểm giao dịch nguồn
D. Dùng giờ địa phương của worker cho mọi event nhập vào
Đáp án đúng: A

Câu 35. Join hai luồng event có thể đến lệch nhau vài phút; việc quản lý state nào là cần thiết?
A. Xóa state ngay khi thấy bản ghi đầu tiên của khóa
B. Giữ mọi state vĩnh viễn dù dữ liệu có giới hạn thời gian
C. Giữ state đủ lâu và xử lý trường hợp event đến trễ
D. Bỏ event time và join tất cả theo giờ nhận của worker
Đáp án đúng: C

Câu 36. Bảng danh mục nhỏ, thiếu CDC, thay đổi ít và có thể nạp lại theo ngày; cách tích hợp nào hợp lý?
A. Full snapshot batch với so sánh và đối soát ở đích
B. Dùng log-based CDC dù nguồn không xuất transaction log
C. Chọn incremental theo một cột không ghi nhận thay đổi
D. Stream sự kiện theo giây dù nguồn chỉ cho tải CSV
Đáp án đúng: A

Câu 37. API nguồn trả next_cursor trong phân trang; để trích xuất đủ dữ liệu, worker nên làm gì?
A. Theo next_cursor và lưu checkpoint sau khi nạp trang
B. Dừng ở trang đầu khi server trả HTTP status 200
C. Cập nhật cursor trước khi dữ liệu trang được lưu xong
D. Tăng offset cố định thay cho token trả từ server
Đáp án đúng: A

Câu 38. Hai hệ thống cùng gửi customer_id nhưng namespace của ID khác nhau; khi hợp nhất nên dùng gì?
A. Gộp khách theo thời gian update để tránh trùng khóa
B. Ánh xạ khóa theo nguồn và quy tắc nhận diện thực thể
C. Đánh lại ID theo thứ tự event đến tại consumer hiện tại
D. Dùng nguyên customer_id và giả định là duy nhất chung
Đáp án đúng: B

Câu 39. Tỷ lệ giá trị null tăng đột biến dù job vẫn hoàn tất; giám sát nào phát hiện chất lượng suy giảm?
A. Đếm số worker đang hoạt động và bỏ thống kê cột
B. Quan sát số request API thành công rồi suy ra null-rate
C. Đo null-rate theo cột và cảnh báo khi lệch ngưỡng
D. Đo tổng thời gian chạy job rồi coi như chất lượng
Đáp án đúng: C

Câu 40. Producer đổi schema bất ngờ và bước transform bắt đầu sai; kiểm thử nào phát hiện sớm nhất?
A. Đối soát checksum của bảng đích vào cuối ngày
B. Đối chiếu schema contract với payload mẫu từ nguồn
C. Tăng code coverage của phép mapping trong unit test
D. Chạy hồi quy dashboard sau khi dữ liệu đã được nạp
Đáp án đúng: B
