Bạn sẽ mô tả vòng đời xử lý một tệp không đáng tin cậy từ lúc upload đến khi lưu trữ và sử dụng như thế nào?
Bạn sẽ xác định các ranh giới tin cậy trong pipeline upload, giải nén, parse, quét và phân phối tệp ra sao?
Bạn sẽ phân biệt kiểm tra dữ liệu đầu vào với kiểm tra an toàn của parser và nội dung tệp như thế nào?
Bạn sẽ thiết kế quy trình upload theo các trạng thái quarantine, validation, scanning, approved và rejected ra sao?
Bạn sẽ xác định những loại tệp và thao tác nào cần parser riêng hoặc mức cô lập cao hơn như thế nào?
Bạn sẽ lựa chọn các kiểm soát tối thiểu trước khi một tệp được phép đi vào parser phức tạp ra sao?
Bạn sẽ phân biệt file extension, MIME type do client khai báo và định dạng thực tế được nhận diện từ nội dung như thế nào?
Bạn sẽ xác minh định dạng tệp bằng magic bytes hoặc signature mà không dựa riêng vào tên tệp ra sao?
Bạn sẽ xử lý tệp có extension, MIME type và nội dung không khớp nhau theo chính sách nào?
Bạn sẽ phát hiện polyglot file có thể được diễn giải thành nhiều định dạng khác nhau bằng cách nào?
Bạn sẽ xác định định dạng tệp được phép theo allowlist và mục đích nghiệp vụ thay vì chấp nhận mọi loại tệp như thế nào?
Bạn sẽ giới hạn kích thước upload, số lượng tệp, tốc độ gửi và tổng quota theo người dùng hoặc tenant ra sao?
Bạn sẽ kiểm soát tên tệp do người dùng cung cấp để tránh path traversal, ghi đè và lộ thông tin hệ thống như thế nào?
Bạn sẽ tạo tên lưu trữ ngẫu nhiên và giữ tên gốc như metadata an toàn để phục vụ hiển thị ra sao?
Bạn sẽ thiết kế lưu tệp ngoài webroot và kiểm soát quyền truy cập để tránh thực thi trực tiếp nội dung upload như thế nào?
Bạn sẽ ngăn tệp vừa upload bị truy cập trước khi hoàn tất validation và malware scanning ra sao?
Bạn sẽ xử lý upload bị ngắt giữa chừng hoặc nội dung chỉ được ghi một phần để tránh parser đọc dữ liệu chưa hoàn chỉnh như thế nào?
Bạn sẽ xác định cách kiểm tra checksum hoặc kích thước thực tế để phát hiện tệp bị thay đổi trong quá trình truyền như thế nào?
Bạn sẽ phân tích rủi ro khi backend tin vào Content-Type hoặc Content-Disposition do client gửi lên ra sao?
Bạn sẽ bảo vệ endpoint upload trước việc lạm dụng tài nguyên bằng nhiều request nhỏ hoặc nhiều upload đồng thời như thế nào?
Bạn sẽ giải thích zip bomb và các dạng archive bomb khác có thể làm cạn CPU, RAM hoặc dung lượng đĩa như thế nào?
Bạn sẽ thiết lập giới hạn kích thước giải nén tổng cộng, tỷ lệ nén và số lượng entry để giảm nguy cơ zip bomb ra sao?
Bạn sẽ kiểm soát archive lồng nhau nhiều tầng để tránh việc giải nén đệ quy không giới hạn như thế nào?
Bạn sẽ xử lý archive có entry khai báo kích thước nhỏ nhưng tạo ra dữ liệu giải nén lớn bất thường ra sao?
Bạn sẽ xác định cách giới hạn thời gian giải nén và hủy công việc khi vượt ngân sách CPU như thế nào?
Bạn sẽ phân biệt giới hạn kích thước archive nén với giới hạn tổng kích thước dữ liệu sau giải nén ra sao?
Bạn sẽ phát hiện archive chứa số lượng lớn file rỗng hoặc entry nhỏ nhằm gây quá tải metadata bằng cách nào?
Bạn sẽ ngăn archive entry ghi ra ngoài thư mục đích bằng cách chuẩn hóa đường dẫn và kiểm tra canonical path như thế nào?
Bạn sẽ xử lý tên entry chứa ../, đường dẫn tuyệt đối, drive letter hoặc UNC path khi giải nén trên các hệ điều hành khác nhau ra sao?
Bạn sẽ đánh giá rủi ro của symbolic link hoặc hard link bên trong archive đối với thư mục giải nén như thế nào?
Bạn sẽ phòng chống symlink race hoặc TOCTOU khi kiểm tra đường dẫn rồi mới ghi file bằng cách nào?
Bạn sẽ thiết kế giải nén vào thư mục staging riêng và chỉ publish kết quả sau khi toàn bộ entry đã được xác thực ra sao?
Bạn sẽ xác định cách xử lý entry trùng tên, khác biệt chữ hoa chữ thường hoặc tên file dành riêng trên Windows như thế nào?
Bạn sẽ quyết định từ chối archive có đường dẫn bất thường hay chỉ loại bỏ entry vi phạm theo mức độ rủi ro nào?
Bạn sẽ kiểm thử zip bomb, path traversal và archive hỏng bằng tập mẫu an toàn mà không gây cạn tài nguyên môi trường test như thế nào?
Bạn sẽ mô tả XXE và cách XML parser có thể bị lợi dụng để đọc file cục bộ hoặc truy cập dịch vụ nội bộ như thế nào?
Bạn sẽ cấu hình XML parser để vô hiệu hóa external general entities, external parameter entities và external DTD ra sao?
Bạn sẽ phân biệt việc tắt DTD với việc tắt XInclude và các cơ chế tải tài nguyên ngoài trong parser XML như thế nào?
Bạn sẽ ngăn SSRF phát sinh khi XML parser hoặc thư viện xử lý tài liệu cố tải external entity từ URL do tệp cung cấp ra sao?
Bạn sẽ đánh giá rủi ro entity expansion và recursive entity khi parser xử lý XML được tạo có chủ đích như thế nào?
Bạn sẽ xác minh cấu hình chống XXE của thư viện XML bằng các bài test đọc file giả lập và truy cập mạng bị chặn ra sao?
Bạn sẽ xử lý XML có namespace, schema hoặc external reference mà nghiệp vụ cần hỗ trợ nhưng vẫn phải giới hạn truy cập ngoài như thế nào?
Bạn sẽ lựa chọn cách parse XML an toàn cho tài liệu lớn để tránh giữ toàn bộ cây DOM trong bộ nhớ ra sao?
Bạn sẽ phân biệt parser XML dạng streaming với DOM về mức tiêu thụ bộ nhớ và bề mặt tấn công như thế nào?
Bạn sẽ mô tả nguy cơ của unsafe deserialization khi dữ liệu đầu vào có thể điều khiển kiểu object được khởi tạo như thế nào?
Bạn sẽ giải thích gadget chain có thể dẫn đến thực thi mã hoặc thao tác nguy hiểm trong quá trình deserialization ra sao?
Bạn sẽ lựa chọn định dạng dữ liệu thay thế ít phụ thuộc vào object graph tùy ý khi trao đổi dữ liệu giữa các hệ thống như thế nào?
Bạn sẽ áp dụng allowlist kiểu dữ liệu và giới hạn độ sâu, số object hoặc kích thước graph khi deserialization ra sao?
Bạn sẽ phân biệt kiểm tra chữ ký hoặc nguồn gửi với việc chứng minh nội dung serialized object an toàn để deserialize như thế nào?
Bạn sẽ xử lý dữ liệu serialized cũ khi ứng dụng cần tương thích nhưng không thể tin cậy nguồn tạo dữ liệu ra sao?
Bạn sẽ xác định các rủi ro parser đặc thù của YAML, JSON và CSV khi xử lý cấu trúc lồng sâu hoặc giá trị bất thường như thế nào?
Bạn sẽ giới hạn độ sâu nesting, số phần tử, độ dài chuỗi và kích thước token khi parse JSON hoặc YAML ra sao?
Bạn sẽ phân tích nguy cơ CSV formula injection khi tệp được parse rồi xuất lại cho người dùng mở bằng spreadsheet như thế nào?
Bạn sẽ kiểm tra parser có xử lý an toàn encoding sai, byte sequence không hợp lệ và Unicode normalization như thế nào?
Bạn sẽ xác định cách ngăn parser diễn giải một tệp nhị phân như văn bản hoặc ngược lại khi phát hiện định dạng không chắc chắn ra sao?
Bạn sẽ đánh giá rủi ro parser image với kích thước pixel khai báo cực lớn dù tệp nén có dung lượng nhỏ như thế nào?
Bạn sẽ giới hạn số pixel, frame, layer và thời gian giải mã khi xử lý ảnh động hoặc tài liệu nhiều trang ra sao?
Bạn sẽ kiểm soát việc parser PDF hoặc office document xử lý embedded object, macro, link ngoài và nội dung chủ động như thế nào?
Bạn sẽ lựa chọn khi nào cần antivirus scanning, sandbox scanning hoặc Content Disarm and Reconstruction trước khi phân phối tệp ra sao?
Bạn sẽ phân biệt phát hiện malware bằng chữ ký với phân tích hành vi trong sandbox về khả năng và giới hạn như thế nào?
Bạn sẽ thiết kế xử lý khi dịch vụ quét malware không khả dụng để tệp chưa được xác minh không bị phát hành như thế nào?
Bạn sẽ kiểm soát quyền thực thi, quyền đọc ghi và network access của tiến trình parser trong môi trường cô lập ra sao?
Bạn sẽ lựa chọn chạy parser trong process riêng, container hoặc sandbox theo mức độ tin cậy và yêu cầu hiệu năng nào?
Bạn sẽ giới hạn CPU, memory, file descriptor, process count và disk quota cho mỗi tác vụ parse như thế nào?
Bạn sẽ thiết kế timeout và cơ chế terminate parser bị treo mà không ảnh hưởng worker xử lý các tệp khác ra sao?
Bạn sẽ ngăn parser truy cập metadata service, loopback endpoint hoặc mạng nội bộ khi không có nhu cầu nghiệp vụ như thế nào?
Bạn sẽ sử dụng filesystem tạm thời, read-only root và thư mục output riêng để giảm tác động khi parser bị khai thác ra sao?
Bạn sẽ xác định cách xóa an toàn file tạm và dữ liệu trung gian sau khi tác vụ parse hoàn tất hoặc thất bại như thế nào?
Bạn sẽ giới hạn concurrency của parser dựa trên kích thước tệp và mức tiêu thụ tài nguyên thay vì chỉ dựa trên số request như thế nào?
Bạn sẽ thiết kế hàng đợi xử lý và backpressure để upload burst không làm cạn tài nguyên của parser worker ra sao?
Bạn sẽ phân biệt lỗi parser có thể retry với đầu vào độc hại hoặc không hợp lệ cần quarantine như thế nào?
Bạn sẽ xây dựng fuzzing harness cho parser bằng corpus mẫu hợp lệ, malformed và các trường hợp biên như thế nào?
Bạn sẽ lựa chọn coverage-guided fuzzing, mutation-based fuzzing hoặc property-based testing cho từng loại parser ra sao?
Bạn sẽ tạo seed corpus đại diện cho nhiều phiên bản định dạng mà không đưa dữ liệu khách hàng nhạy cảm vào bộ fuzzing như thế nào?
Bạn sẽ xác định cách giới hạn thời gian, bộ nhớ và số lần lặp để fuzzing không làm quá tải môi trường kiểm thử ra sao?
Bạn sẽ phân biệt crash, hang, out-of-memory và kết quả parse sai khi phân loại phát hiện từ fuzzing như thế nào?
Bạn sẽ rút gọn input gây lỗi thành test case tối thiểu để tái hiện và sửa lỗi parser bằng cách nào?
Bạn sẽ chuyển phát hiện từ fuzzing thành regression test để lỗi đã sửa không tái xuất hiện như thế nào?
Bạn sẽ thiết kế differential testing giữa hai phiên bản parser để phát hiện khác biệt diễn giải cùng một tệp ra sao?
Bạn sẽ kiểm thử giới hạn tài nguyên với archive bomb và tài liệu có cấu trúc sâu mà không gây ảnh hưởng hệ thống dùng chung như thế nào?
Bạn sẽ theo dõi những chỉ số nào như parse duration, queue wait, rejection rate, memory peak và decompressed bytes để phát hiện lạm dụng parser?
Bạn sẽ ghi log lý do từ chối và thông tin định dạng mà không lưu lại nội dung tệp nhạy cảm hoặc dữ liệu có thể kích hoạt parser lần nữa như thế nào?
Bạn sẽ thiết kế audit trail cho người upload, kết quả kiểm tra, phiên bản parser và quyết định cho phép hoặc từ chối tệp ra sao?
Bạn sẽ xử lý sự cố khi phát hiện parser đã xử lý một tệp độc hại và cần xác định phạm vi ảnh hưởng như thế nào?
Bạn sẽ xác định tiêu chí nghiệm thu về validation, giới hạn tài nguyên, sandbox, XXE, deserialization, archive safety và fuzzing trước khi đưa pipeline xử lý tệp vào production như thế nào?
