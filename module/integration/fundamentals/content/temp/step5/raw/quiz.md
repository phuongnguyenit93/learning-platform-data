Câu 1. Mục đích chính của hợp đồng tích hợp giữa hai hệ thống là gì?
A. Thống nhất lời gọi, dữ liệu và kết quả trả về
B. Thống nhất công nghệ lưu trữ dữ liệu của hai hệ thống
C. Thống nhất ngôn ngữ lập trình cho mọi thành phần
D. Thống nhất cấu trúc lớp nội bộ của từng ứng dụng
Đáp án đúng: A

Câu 2. Cách thiết kế nào giúp giảm phụ thuộc khi hai ứng dụng cần tích hợp?
A. Cho bên gọi truy cập trực tiếp các bảng dữ liệu lõi
B. Cho hai ứng dụng dùng chung các lớp nghiệp vụ nội bộ
C. Ẩn chi tiết xử lý sau một giao diện ổn định
D. Để bên gọi tự quyết định logic xử lý của bên nhận
Đáp án đúng: C

Câu 3. Đặc điểm của giao tiếp request-response đồng bộ là gì?
A. Bên gọi ghi message rồi xử lý tiếp không đợi kết quả
B. Bên gọi chờ phản hồi của bên nhận cho yêu cầu hiện tại
C. Bên nhận phát thông báo sau mọi thay đổi trạng thái
D. Bên nhận gửi dữ liệu định kỳ không cần lời gọi trước
Đáp án đúng: B

Câu 4. Đặc điểm của giao tiếp bất đồng bộ qua message là gì?
A. Bên gửi phải đợi bên nhận hoàn tất toàn bộ nghiệp vụ
B. Bên gửi có thể tiếp tục sau khi bàn giao message
C. Bên nhận cần mở kết nối đồng bộ với từng bên gửi
D. Bên nhận phải trả dữ liệu trong cùng một HTTP response
Đáp án đúng: B

Câu 5. Tình huống nào thường phù hợp với lời gọi API đồng bộ?
A. Xác nhận ngay số dư khả dụng trước khi phê duyệt
B. Gửi bản tổng hợp hoạt động để xử lý lúc nửa đêm
C. Phát thông báo đổi trạng thái cho nhiều hệ thống
D. Đưa hàng nghìn tác vụ hình ảnh vào hàng đợi nền
Đáp án đúng: A

Câu 6. Khi lưu lượng tạo tác vụ tăng đột biến, hàng đợi hỗ trợ điều gì?
A. Buộc worker xử lý mọi tác vụ trước khi phản hồi HTTP
B. Thay đổi hợp đồng để bên gửi không cần kiểm tra dữ liệu
C. Loại bỏ nhu cầu theo dõi độ trễ và số tác vụ tồn
D. Đệm công việc theo năng lực xử lý của các worker
Đáp án đúng: D

Câu 7. Trong mô hình API, request thường mang thông tin nào?
A. Kết quả xử lý cuối cùng của hệ thống được gọi
B. Vị trí message đang nằm trong hàng đợi của broker
C. Thao tác mong muốn cùng tham số và dữ liệu đầu vào
D. Cam kết rằng bên nhận đã hoàn tất mọi thao tác
Đáp án đúng: C

Câu 8. Sự kiện OrderPaid nên được hiểu theo cách nào?
A. Ra lệnh cho một thành phần thực hiện thanh toán
B. Yêu cầu lấy trạng thái mới nhất của đơn hàng
C. Yêu cầu hủy giao dịch đang chờ xác nhận
D. Thông báo một sự thật nghiệp vụ đã xảy ra
Đáp án đúng: D

Câu 9. Khác biệt thường gặp giữa command và event là gì?
A. Command ghi nhận sự kiện; event yêu cầu thực thi ngay
B. Command chỉ áp dụng cho API; event chỉ áp dụng cho SQL
C. Command phải gửi cho nhiều bên; event chỉ cho một bên
D. Command yêu cầu hành động; event báo việc đã xảy ra
Đáp án đúng: D

Câu 10. Với pub/sub, một sự kiện có nhiều subscriber được xử lý ra sao?
A. Mỗi subscriber đều phải xử lý chung một giao dịch DB
B. Chỉ subscriber đầu tiên đăng ký mới nhận được sự kiện
C. Mỗi subscription có thể nhận sự kiện để xử lý riêng
D. Mọi subscriber phải gọi lại API đồng bộ trước khi nhận
Đáp án đúng: C

Câu 11. Với hàng đợi có nhiều worker cạnh tranh trong cùng nhóm, điều gì thường xảy ra?
A. Mỗi message đều chuyển đồng thời cho mọi worker của nhóm
B. Mỗi message được phân phối cho một worker trong nhóm
C. Mỗi worker xử lý tất cả message theo cùng một thứ tự
D. Mỗi worker tự tạo bản sao message cho nhóm khác nhận
Đáp án đúng: B

Câu 12. Khi nào tích hợp theo lô (batch) thường là lựa chọn hợp lý?
A. Khi tổng hợp dữ liệu lớn theo lịch và chấp nhận độ trễ
B. Khi người dùng cần kết quả tức thì cho từng thao tác
C. Khi nhiều bên cần phản ứng ngay sau mỗi thay đổi
D. Khi giao dịch cần xác nhận trong vài mili giây
Đáp án đúng: A

Câu 13. Khi dữ liệu cảm biến phát sinh liên tục, stream processing phù hợp vì sao?
A. Chỉ xử lý được dữ liệu sau khi đóng toàn bộ tập tin
B. Yêu cầu phải chờ đủ dữ liệu cho một kỳ tổng hợp
C. Xử lý bản ghi ngay khi dòng dữ liệu tiếp tục đến
D. Chỉ hỗ trợ truy vấn đồng bộ một bản ghi tại một thời điểm
Đáp án đúng: C

Câu 14. Change Data Capture (CDC) thường thu thập thay đổi từ đâu?
A. Nhật ký thay đổi dữ liệu hoặc cơ chế ghi nhận tương tự
B. Bộ nhớ cache của trình duyệt gửi request đến API
C. Thông tin xác thực trong header của mọi HTTP request
D. Tập tin cấu hình triển khai của ứng dụng tiêu thụ
Đáp án đúng: A

Câu 15. Khi hai hệ thống đặt tên trường khác nhau, lớp mapping nên làm gì?
A. Chuyển tên và cấu trúc dữ liệu giữa hai hợp đồng
B. Buộc cả hai hệ thống đổi tên trường trong database
C. Thay đổi giao thức mạng để tự suy ra tên dữ liệu
D. Bỏ kiểm tra kiểu dữ liệu để tăng khả năng tương thích
Đáp án đúng: A

Câu 16. Một hợp đồng API cần mô tả nội dung nào để client tích hợp ổn định?
A. Cấu trúc bảng, chỉ mục và khóa ngoại của database
B. Danh sách luồng xử lý nội bộ và các private method
C. Địa chỉ máy phát triển và toàn bộ biến môi trường
D. Đường gọi, định dạng dữ liệu, quy tắc và mã lỗi
Đáp án đúng: D

Câu 17. Consumer-driven contract test chủ yếu xác minh điều gì?
A. Provider luôn đạt hiệu năng yêu cầu khi chịu tải lớn
B. Provider đáp ứng tương tác mà consumer kỳ vọng
C. Consumer có quyền truy cập tất cả endpoint của provider
D. Consumer và provider dùng cùng một phiên bản database
Đáp án đúng: B

Câu 18. Thay đổi nào thường tương thích ngược với client đọc JSON bỏ qua trường lạ?
A. Xóa trường response mà client đang đọc để hiển thị
B. Đổi kiểu trường định danh từ chuỗi thành đối tượng
C. Đổi tên một thuộc tính đang được client sử dụng
D. Thêm trường không bắt buộc vào response hiện hữu
Đáp án đúng: D

Câu 19. Thay đổi nào có nguy cơ phá vỡ hợp đồng dữ liệu đang dùng?
A. Đổi kiểu của trường hiện hữu từ số sang chuỗi
B. Thêm một trường tùy chọn mà client không sử dụng
C. Bổ sung ví dụ cho tài liệu của endpoint hiện hữu
D. Thêm endpoint độc lập chưa được client cũ gọi
Đáp án đúng: A

Câu 20. Khi phải triển khai phiên bản API mới có thay đổi phá vỡ, nên làm gì?
A. Chuyển mọi client sang bản mới ngay khi server triển khai
B. Giữ nguyên số phiên bản dù đã thay đổi hợp đồng dữ liệu
C. Ẩn thông tin thay đổi để client chỉ phát hiện khi lỗi
D. Công bố lịch chuyển đổi và thời gian duy trì bản cũ
Đáp án đúng: D

Câu 21. Trong một event schema, thêm trường bắt buộc có rủi ro gì?
A. Producer cũ luôn tự bổ sung giá trị mới mà không đổi mã
B. Producer cũ có thể thiếu trường bắt buộc theo schema mới
C. Consumer cũ sẽ không thể nhận bất kỳ message nào từ broker
D. Broker tự chuyển mọi payload cũ sang trường mới được thêm
Đáp án đúng: B

Câu 22. Schema registry có ích gì trong tích hợp thông điệp?
A. Tự chạy toàn bộ nghiệp vụ của consumer thay cho worker
B. Tự động đảm bảo mỗi event chỉ có đúng một bản sao
C. Thay thế hệ thống xác thực của mọi dịch vụ gửi sự kiện
D. Quản lý schema và kiểm tra quy tắc tương thích phiên bản
Đáp án đúng: D

Câu 23. Khi event có nhiều phiên bản hợp đồng, consumer nên xử lý ra sao?
A. Luôn coi mọi message có cùng cấu trúc như bản đầu
B. Bỏ qua dữ liệu kiểm tra hợp đồng vì broker đã lưu
C. Yêu cầu producer xóa mọi event cũ trước khi phát mới
D. Nhận diện phiên bản và giải mã theo schema phù hợp
Đáp án đúng: D

Câu 24. Correlation ID thường giúp ích gì trong luồng tích hợp đa dịch vụ?
A. Thay cho token xác thực trong tất cả lời gọi nội bộ
B. Thay cho phiên bản schema của các message gửi qua broker
C. Theo dấu các thao tác liên quan đến cùng một yêu cầu
D. Đảm bảo mọi transaction ở nhiều hệ thống được commit
Đáp án đúng: C

Câu 25. Với cơ chế at-least-once, consumer cần chuẩn bị cho tình huống nào?
A. Mọi message chắc chắn chỉ được chuyển đúng một lần
B. Cùng một message có thể được chuyển đến nhiều lần
C. Mọi message đều có thứ tự toàn cục giữa các topic
D. Mọi message không cần xác nhận sau khi được xử lý
Đáp án đúng: B

Câu 26. Với cơ chế at-most-once, đánh đổi quan trọng là gì?
A. Message chắc chắn sẽ được phát lại sau khi consumer lỗi
B. Message có thể mất nếu lỗi đến trước khi xử lý
C. Message luôn được xử lý đúng một lần ở database
D. Message luôn giữ thứ tự trên tất cả luồng xử lý
Đáp án đúng: B

Câu 27. Vì sao cần chống trùng dù broker hỗ trợ đảm bảo giao nhận mạnh?
A. Consumer luôn chỉ xử lý message khi kết nối TCP đang mở
B. Producer không bao giờ phát lại request sau khi bị timeout
C. Broker tự khóa toàn bộ bảng dữ liệu của từng consumer
D. Tác dụng phụ DB có thể nằm ngoài phạm vi đảm bảo
Đáp án đúng: D

Câu 28. Trong hệ thống phân vùng message, thứ tự thường được đảm bảo trong phạm vi nào?
A. Trong cùng một partition theo thứ tự message được ghi
B. Giữa mọi partition của nhiều topic và mọi broker
C. Giữa mọi consumer chạy ở các vùng mạng khác nhau
D. Giữa mọi message có cùng thời gian phát sinh nghiệp vụ
Đáp án đúng: A

Câu 29. Consumer group trong một hệ thống broker thường giúp điều gì?
A. Nhân mọi message cho tất cả thành viên của một nhóm
B. Bắt tất cả worker dùng cùng kết nối đến database
C. Phân chia tải xử lý các partition giữa thành viên nhóm
D. Bảo đảm nhóm khác không được đăng ký cùng một topic
Đáp án đúng: C

Câu 30. Consumer bị lỗi sau khi ghi DB nhưng trước khi ack có thể gây gì?
A. Message bị broker xóa vĩnh viễn ngay khi consumer lỗi
B. Message chắc chắn không bao giờ xuất hiện lại ở consumer
C. Message được đổi cấu trúc trước khi broker gửi lại
D. Message có thể được gửi lại và xử lý trùng
Đáp án đúng: D

Câu 31. Dead-letter queue thường phục vụ mục đích nào?
A. Lưu mọi phản hồi thành công để bỏ qua consumer chính
B. Lưu message lỗi để điều tra và xử lý lại
C. Lưu request đang chờ xác thực để tránh kiểm tra token
D. Lưu phiên bản API để không cần tài liệu hợp đồng
Đáp án đúng: B

Câu 32. Khi retry lỗi tạm thời, backoff kèm jitter hữu ích vì sao?
A. Gửi lại mọi request ngay lập tức sau mỗi lỗi phát sinh
B. Giãn các lần thử và giảm các đợt thử lại đồng loạt
C. Cho phép retry không giới hạn dù deadline đã kết thúc
D. Đảm bảo mọi lần thử đều chạy trên một backend cố định
Đáp án đúng: B

Câu 33. Khi dịch vụ A gọi tiếp B rồi C, nên quản lý timeout như thế nào?
A. Truyền phần deadline còn lại cho các lời gọi tiếp
B. Đặt timeout mới dài hơn cho từng lần gọi tiếp theo
C. Bỏ giới hạn timeout ở các lời gọi sau khi A xác thực
D. Chỉ đặt timeout khi dữ liệu đã được ghi vào database
Đáp án đúng: A

Câu 34. Circuit breaker giúp dịch vụ gọi hoạt động ra sao khi downstream lỗi liên tục?
A. Tạm từ chối lời gọi rồi thử khôi phục khi phù hợp
B. Tăng số request gửi xuống để kiểm tra tốc độ phục hồi
C. Thay mọi request mới bằng cách ghi trực tiếp database
D. Đảm bảo downstream không bao giờ trả lỗi trong tương lai
Đáp án đúng: A

Câu 35. Mục tiêu của bulkhead pattern khi tích hợp dịch vụ là gì?
A. Cho phép mọi tác vụ dùng chung một pool không giới hạn
B. Chuyển mọi xử lý đồng bộ sang một luồng duy nhất
C. Cô lập tài nguyên để lỗi một nhóm không làm cạn toàn bộ
D. Đảm bảo các hệ thống luôn chia sẻ cùng transaction
Đáp án đúng: C

Câu 36. Backpressure hữu ích khi consumer chậm hơn producer vì sao?
A. Tăng tốc độ phát message dù hàng đợi đã đầy bộ nhớ
B. Bỏ xác nhận xử lý để tránh mọi lần gửi trùng message
C. Điều tiết tốc độ nhận và lượng dữ liệu chờ xử lý
D. Gộp tất cả message chưa xử lý thành một phản hồi HTTP
Đáp án đúng: C

Câu 37. Idempotency key giúp xử lý retry của yêu cầu tạo giao dịch như thế nào?
A. Nhận biết yêu cầu lặp để tránh ghi tác dụng phụ
B. Đổi mỗi lần retry thành giao dịch mới với ID ngẫu nhiên
C. Cho phép client bỏ kiểm tra trạng thái phản hồi từ server
D. Đảm bảo message được gửi theo đúng thứ tự trên mọi queue
Đáp án đúng: A

Câu 38. Transactional outbox giải quyết nguy cơ nào khi phát sự kiện?
A. Dữ liệu đã commit nhưng event tương ứng chưa được ghi
B. Message được consumer xử lý xong nhưng chưa ghi access log
C. Client nhận phản hồi chậm do dịch vụ chưa bật nén payload
D. API dùng sai phiên bản schema khi đọc dữ liệu từ cache
Đáp án đúng: A

Câu 39. Vì sao cập nhật database rồi publish message bằng hai thao tác độc lập có rủi ro?
A. Broker luôn thực hiện rollback toàn bộ dữ liệu trong database
B. Việc publish luôn diễn ra trước khi commit tại database
C. Hai thao tác độc lập mặc định nằm trong cùng transaction ACID
D. Lỗi thao tác sau có thể khiến trạng thái bị lệch
Đáp án đúng: D

Câu 40. Eventual consistency mô tả trạng thái nào trong hệ thống phân tán?
A. Mọi bản sao phải giống nhau trước khi ghi nhận mỗi request
B. Mọi thành phần sẽ thấy dữ liệu mới ngay tại cùng thời điểm
C. Các bản sao có thể lệch tạm thời rồi hội tụ
D. Những dữ liệu đã sai ở một bản sao sẽ không bao giờ đồng bộ
Đáp án đúng: C

Câu 41. Khi Saga thất bại giữa chuỗi tác vụ phân tán, cơ chế nào thường được dùng?
A. Rollback một transaction ACID trên tất cả dịch vụ độc lập
B. Chạy lại toàn bộ tác vụ mà không kiểm tra tác dụng phụ
C. Xóa mọi message khỏi broker rồi cập nhật toàn bộ database
D. Dùng thao tác bù trừ cho bước đã thành công
Đáp án đúng: D

Câu 42. Optimistic concurrency với version field giúp ngăn tình huống nào?
A. Nhận trùng bản ghi do broker gửi lại một message cũ
B. Tránh ghi đè khi cập nhật theo phiên bản cũ
C. Mất kết nối mạng khi dịch vụ gọi vượt qua thời gian chờ
D. Không thể đọc response khi schema JSON có trường tùy chọn
Đáp án đúng: B

Câu 43. Trong đồng bộ dữ liệu nhiều hệ thống, reconciliation thường nhằm mục đích gì?
A. Tự động bỏ qua mọi bản ghi không có cùng thời điểm cập nhật
B. Phát hiện sai lệch và đồng bộ lại bản ghi
C. Buộc mọi hệ thống dùng chung một cơ sở dữ liệu trung tâm
D. Đổi giao tiếp bất đồng bộ thành gọi API đồng bộ liên tục
Đáp án đúng: B

Câu 44. Khi gọi API giữa các dịch vụ, TLS chủ yếu bảo vệ điều gì?
A. Xác minh quyền nghiệp vụ của người dùng trên từng đơn hàng
B. Đảm bảo mọi lệnh cập nhật đều có thể chạy lại an toàn
C. Mã hóa truyền dẫn và xác minh danh tính server
D. Bảo đảm mọi message ở broker có thứ tự xử lý toàn cục
Đáp án đúng: C

Câu 45. Cặp khái niệm xác thực và phân quyền trong tích hợp được hiểu đúng ra sao?
A. Xác thực định danh; phân quyền kiểm tra hành động
B. Xác thực quyết định quyền thao tác, phân quyền đối chiếu mật khẩu
C. Xác thực kiểm tra schema, phân quyền cấp phát ID cho message
D. Xác thực kiểm tra timeout, phân quyền chọn partition cho event
Đáp án đúng: A

Câu 46. Theo nguyên tắc least privilege, quyền của tài khoản tích hợp nên cấp thế nào?
A. Cấp quyền quản trị để tránh lỗi thiếu quyền khi retry
B. Cho mọi dịch vụ sử dụng một tài khoản dùng chung
C. Cấp quyền tối thiểu cho từng nhiệm vụ tích hợp
D. Cấp quyền đọc ghi toàn bộ dữ liệu cho các worker
Đáp án đúng: C

Câu 47. Trong contract testing giữa hai dịch vụ, điều gì cần được xác nhận?
A. Toàn bộ hạ tầng sản xuất chịu được tải cao điểm trong một test
B. Provider đáp ứng request và response consumer mong đợi
C. Database luôn đạt tính nhất quán tức thì ở mọi khu vực
D. Mọi message có thể truy cập dù consumer thiếu quyền đọc
Đáp án đúng: B

Câu 48. Một integration test muốn xác minh khả năng phục hồi sau lỗi broker nên làm gì?
A. Chỉ so sánh tên class Java với tên schema trong tài liệu
B. Chỉ chạy thử serialization mà không khởi động dịch vụ
C. Chủ động gây gián đoạn rồi kiểm tra retry và dữ liệu
D. Chỉ xác minh một request thành công khi hạ tầng bình thường
Đáp án đúng: C
