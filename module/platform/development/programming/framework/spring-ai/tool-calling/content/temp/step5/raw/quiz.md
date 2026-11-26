Câu 1. Trong Spring AI, muốn khai báo một phương thức Java làm công cụ cho model, nên dùng gì?
A. Đánh dấu phương thức bằng annotation @Tool
B. Đánh dấu phương thức bằng annotation @ToolParam
C. Đánh dấu phương thức bằng annotation @Bean
D. Đánh dấu phương thức bằng annotation @JsonProperty
Đáp án đúng: A

Câu 2. Mô tả trong annotation @Tool giúp ích điều gì cho quá trình gọi công cụ?
A. Quy định thời gian chờ HTTP cho công cụ được gọi
B. Đặt quyền truy cập theo vai trò của từng tài khoản
C. Giúp model chọn công cụ phù hợp với yêu cầu
D. Xác thực dữ liệu đầu ra trước khi lưu vào database
Đáp án đúng: C

Câu 3. Trong phương thức được gắn @Tool, @ToolParam thường hỗ trợ mục đích nào?
A. Đăng ký tên công cụ cho mọi ChatClient trong JVM
B. Mô tả ý nghĩa tham số để model tạo arguments
C. Thêm chính sách retry cho tool bị lỗi thời gian
D. Cấp quyền truy cập dữ liệu cho tài khoản đang gọi
Đáp án đúng: B

Câu 4. Spring AI thường xây input schema của tool Java dựa vào đâu?
A. Cấu trúc bảng lưu lịch sử hội thoại trong database
B. Kiểu phản hồi ChatResponse của provider được chọn
C. Trạng thái token usage ở lần gọi model trước đó
D. Kiểu tham số và metadata khai báo ở phương thức
Đáp án đúng: D

Câu 5. Trong Spring AI, ToolCallback đại diện cho trách nhiệm nào?
A. Chỉ tạo nội dung system message cho ChatClient
B. Chỉ lưu các biến thay thế của PromptTemplate
C. Cung cấp định nghĩa và cơ chế gọi một công cụ
D. Chỉ ghi token usage của mỗi yêu cầu gọi model
Đáp án đúng: C

Câu 6. ToolDefinition của một callback chủ yếu mô tả điều gì?
A. Tên, mô tả và schema tham số của tool
B. Trạng thái transaction sau khi tool đã chạy xong
C. Nội dung trả lời cuối cùng do model tạo ra
D. Thông tin session của mọi người dùng ứng dụng
Đáp án đúng: A

Câu 7. Một ToolCallbackProvider trong Spring AI phù hợp để làm gì?
A. Chạy trước mọi callback để tạo dữ liệu embedding
B. Tự cấp quyền quản trị cho toàn bộ tool đăng ký
C. Cung cấp nhóm ToolCallback cho thành phần gọi
D. Lưu kết quả mỗi callback vào PromptTemplate
Đáp án đúng: C

Câu 8. Khi muốn dùng các phương thức @Tool trên một object Java, hướng tiếp cận nào phù hợp?
A. Đưa class vào danh sách response DTO của model
B. Đưa method name vào khóa API của nhà cung cấp
C. Đưa object vào biến temperature của ChatOptions
D. Đưa object vào cơ chế tạo callback từ method
Đáp án đúng: D

Câu 9. Khi dùng ChatClient với tool object đã định nghĩa, cần cấu hình gì?
A. Đăng ký tool object hoặc callback cho ChatClient
B. Chỉ đặt PromptTemplate là model sẽ thấy mọi method
C. Chỉ bật stream để model tự nạp tất cả method
D. Đưa tên tool vào nội dung user prompt là đủ dùng
Đáp án đúng: A

Câu 10. Khi model trả về một yêu cầu tool call, ai thực sự chạy mã nghiệp vụ?
A. Mô hình trực tiếp chạy mã Java trong provider AI
B. Ứng dụng thực thi tool qua callback được cấu hình
C. Input schema tự thực thi nghiệp vụ tại máy client
D. PromptTemplate tự gửi giao dịch đến hệ thống ngoài
Đáp án đúng: B

Câu 11. Vì sao arguments của tool call vẫn cần được kiểm tra ở server?
A. Schema đảm bảo toàn bộ quyền nghiệp vụ đã được cấp
B. Tool call luôn mang dữ liệu từ cơ sở dữ liệu nội bộ
C. Model có thể tự ký xác nhận danh tính người dùng
D. Nội dung do model sinh không phải đầu vào đáng tin
Đáp án đúng: D

Câu 12. Trong chu trình tool calling tự động, kết quả của callback thường được dùng thế nào?
A. Đưa trở lại ngữ cảnh model để tiếp tục câu trả lời
B. Thay đổi định nghĩa JSON schema của những tool khác
C. Trực tiếp cấp một access token mới cho model
D. Ghi đè system prompt của mọi lượt hội thoại
Đáp án đúng: A

Câu 13. Khi cần phê duyệt từng tool call trước khi thực thi, hướng nào phù hợp?
A. Bỏ callback để provider tự ghi dữ liệu vào database
B. Tăng temperature để model tự hỏi lại người dùng
C. Bỏ thông tin tool khỏi request rồi tự suy ra tên
D. Điều phối gọi tool thủ công với bước kiểm tra riêng
Đáp án đúng: D

Câu 14. Để tránh chuỗi tool call nối tiếp kéo dài không kiểm soát, nên làm gì?
A. Tăng số tool được đăng ký để rút ngắn luồng
B. Giới hạn số vòng gọi tool trong mỗi yêu cầu
C. Đặt giới hạn token đầu vào bằng kích thước file
D. Bỏ mọi timeout để model tự kết thúc vòng lặp
Đáp án đúng: B

Câu 15. Khi model yêu cầu nhiều tool có quan hệ phụ thuộc, nên xử lý ra sao?
A. Xác định phụ thuộc trước khi chọn chạy song song
B. Cho mọi callback chạy đồng thời không cần thứ tự
C. Bỏ kết quả tool đầu để dùng kết quả tool cuối
D. Thay thứ tự theo độ dài tên công cụ được gọi
Đáp án đúng: A

Câu 16. Nếu thiếu tham số bắt buộc trong arguments, tool nên làm gì?
A. Thêm giá trị bất kỳ để đủ trường trong input schema
B. Xóa phần required của schema sau khi đã nhận call
C. Tự lấy tham số từ một yêu cầu user khác gần nhất
D. Báo lỗi validation trước khi thực thi nghiệp vụ
Đáp án đúng: D

Câu 17. Nếu model truyền chuỗi vào tham số khai báo kiểu số, điều gì hợp lý?
A. Ghi trực tiếp chuỗi vào DB vì model đã sinh dữ liệu
B. Đổi toàn bộ input schema sang string ngay trong call
C. Bỏ qua trường sai kiểu nhưng vẫn báo tool thành công
D. Kiểm tra kiểu, chỉ chuyển đổi khi quy tắc cho phép
Đáp án đúng: D

Câu 18. Mô tả tool nào giúp model chọn đúng phương thức hơn?
A. Dùng một tên viết tắt khó hiểu để rút ngắn token
B. Dùng mô tả giống nhau cho những tool có hiệu ứng khác
C. Nêu rõ công dụng, tình huống dùng và nghĩa tham số
D. Chỉ mô tả kiểu trả về và bỏ mục đích nghiệp vụ
Đáp án đúng: C

Câu 19. Nếu có hai tool trùng tên trong tập đăng ký, nên ưu tiên biện pháp nào?
A. Ghép hai phương thức thành một schema không kiểm tra
B. Đặt tên phân biệt để tránh chọn nhầm callback
C. Chỉ đổi description rồi giữ nguyên tên công cụ
D. Cho model gọi ngẫu nhiên một công cụ cùng tên
Đáp án đúng: B

Câu 20. Khác biệt chính giữa tool Java và PromptTemplate trong Spring AI là gì?
A. Tool có thể chạy logic; template tạo nội dung prompt
B. Tool chỉ thay biến; template thực thi code nghiệp vụ
C. Tool chỉ lưu history; template truy cập database
D. Tool chỉ tạo embedding; template tự gọi dịch vụ ngoài
Đáp án đúng: A

Câu 21. Tool calling và structured output khác nhau ở mục đích nào?
A. Tool chỉ định dạng DTO; structured output thực thi lệnh
B. Tool thực thi; structured output định dạng kết quả
C. Tool lưu câu hỏi; structured output cấp quyền API
D. Tool chạy mô hình; structured output quản lý scheduler
Đáp án đúng: B

Câu 22. ToolContext trong Spring AI chủ yếu mang thông tin nào?
A. Tham số JSON mà model cần tự sinh theo input schema
B. Dữ liệu ngữ cảnh ứng dụng gửi kèm lúc chạy tool
C. Thông điệp assistant đã được dùng để huấn luyện model
D. Định nghĩa toàn bộ phương thức REST của ứng dụng
Đáp án đúng: B

Câu 23. Vì sao nên dùng ToolContext cho dữ liệu nhạy cảm như principal?
A. Để model tự đặt vai trò quản trị trong arguments tool
B. Để tool bỏ qua kiểm tra quyền khi Context đã được tạo
C. Truyền metadata tin cậy mà không đưa vào schema model
D. Để provider tự lưu principal vào mọi câu trả lời
Đáp án đúng: C

Câu 24. Khi tool cần tenantId để truy cập dữ liệu, cách lấy nào an toàn hơn?
A. Tin tenantId do model tự điền trong arguments
B. Lấy từ ngữ cảnh xác thực do ứng dụng quản lý
C. Dùng tenantId trong mô tả tool làm giá trị mặc định
D. Chọn tenantId đầu tiên từ danh sách kết quả query
Đáp án đúng: B

Câu 25. Khi tool nhận orderId hợp lệ về kiểu nhưng thuộc tài khoản khác, phải làm gì?
A. Kiểm tra quyền sở hữu đơn hàng trước khi đọc
B. Đọc vì tham số đã đúng JSON schema công bố
C. Đọc vì model đã được mô tả quyền truy cập
D. Đổi tên tool để che số định danh của đơn hàng
Đáp án đúng: A

Câu 26. Khi một ChatClient dùng nhiều công cụ, nguyên tắc đăng ký nào an toàn hơn?
A. Cho mọi yêu cầu thấy cùng danh sách công cụ admin
B. Cho model tự bổ sung tool mới sau khi đọc prompt
C. Chỉ đưa tool cần thiết và hợp quyền vào ChatClient
D. Bật tất cả tool để giảm số lượt gọi provider
Đáp án đúng: C

Câu 27. Với tool chuyển tiền, bước bảo vệ nào nên có trước khi thực thi?
A. Chỉ kiểm tra tên method là transferMoney hợp lệ
B. Kiểm tra quyền và xác nhận trước khi chuyển tiền
C. Chỉ xem model đã sinh đủ tham số JSON hay chưa
D. Cho phép model tự xác nhận bằng nội dung phản hồi
Đáp án đúng: B

Câu 28. Credential gọi hệ thống nghiệp vụ nên được quản lý như thế nào?
A. Đưa vào mô tả @Tool để model biết khi yêu cầu
B. Đưa vào ToolContext do model tự điền các trường
C. Trả trong kết quả tool để ChatClient dùng lại sau
D. Giữ ở phía server trong cơ chế secret phù hợp
Đáp án đúng: D

Câu 29. Khi callback trả về văn bản chứa chỉ dẫn trái chính sách, nên coi nó là gì?
A. System instruction được nâng ưu tiên vì do tool trả
B. Bằng chứng người dùng đã đồng ý gọi tool tiếp
C. Dữ liệu có thể độc hại, không phải chỉ dẫn tin cậy
D. Định nghĩa mới để thay thế các tool đã đăng ký
Đáp án đúng: C

Câu 30. Khi kết quả tool rất dài, trước khi gửi về model nên xử lý thế nào?
A. Gửi toàn bộ dữ liệu để model tự chọn mức ưu tiên
B. Tự chuyển tất cả nội dung thành role system mới
C. Bỏ mô tả công cụ để dành token cho dữ liệu trả
D. Lọc bớt dữ liệu, giữ phần liên quan đến yêu cầu
Đáp án đúng: D

Câu 31. Khi tool xử lý dữ liệu cá nhân, cách kiểm soát đầu ra nào phù hợp?
A. Trả bản ghi đầy đủ rồi tin model không tiết lộ
B. Ghi toàn bộ payload vào trace để dễ đối chiếu
C. Dùng output schema thay cho kiểm tra quyền dữ liệu
D. Lọc trường nhạy cảm theo quyền của người gọi
Đáp án đúng: D

Câu 32. Nếu tool nhận URL từ model và dùng nó để gọi HTTP, nên phòng tránh điều gì?
A. Cho mọi URL nội bộ được gọi để tăng hiệu năng
B. Chặn SSRF bằng kiểm tra đích URL trước khi gọi
C. Chỉ đổi URL sang chữ thường trước khi mở kết nối
D. Chỉ giới hạn số token trong phản hồi HTTP
Đáp án đúng: B

Câu 33. Khi tool cần truy vấn DB theo bộ lọc do model sinh, nên ưu tiên gì?
A. Ghép trực tiếp câu SQL do model tạo thành lệnh DB
B. Ghi query model vào log rồi thực thi không kiểm tra
C. Dùng query tham số hóa và kiểm tra quyền truy cập
D. Chuyển cả câu SQL sang system prompt để chạy hộ
Đáp án đúng: C

Câu 34. Khi callback ném exception, cách phản hồi nào phù hợp hơn?
A. Trả stack trace cùng API key cho model để sửa
B. Đổi exception thành kết quả thành công bất kể lỗi
C. Tự xóa toàn bộ nội dung history của phiên chat
D. Báo lỗi có kiểm soát và ghi log không chứa secret
Đáp án đúng: D

Câu 35. Khi gọi tool tới dịch vụ ngoài có deadline, cần thiết lập điều gì?
A. Chờ vô hạn vì nhà cung cấp sẽ trả lời sau cùng
B. Giảm temperature để kết nối mạng có độ trễ thấp
C. Timeout và cách xử lý lỗi phù hợp với yêu cầu
D. Bỏ cơ chế hủy vì model có thể gọi lại sau
Đáp án đúng: C

Câu 36. Nếu tool ghi dữ liệu bị retry, điều gì cần để tránh ghi lặp?
A. Dùng cùng idempotency key cho một yêu cầu ghi
B. Sinh một key mới ở mỗi lần gọi lại để phân biệt
C. Tăng số thread ghi DB để giảm trùng giao dịch
D. Giảm maxTokens vì retry sẽ ngừng tác dụng phụ
Đáp án đúng: A

Câu 37. Tool đã commit DB nhưng client mất phản hồi; điều nào có thể xảy ra?
A. Lệnh có thể chạy lại nếu thiếu cơ chế chống trùng
B. DB tự rollback do phản hồi callback không được nhận
C. JSON schema ngăn mọi request trùng ở tầng provider
D. ChatClient tự đảo ngược giao dịch đã commit
Đáp án đúng: A

Câu 38. Khi lỗi gọi model khác với lỗi thực thi tool, ứng dụng nên làm gì?
A. Coi mọi lỗi là do model rồi tăng temperature
B. Phân biệt lỗi model và lỗi tool trước khi phục hồi
C. Coi mọi lỗi là do tool rồi xóa metadata response
D. Tự retry cả workflow vô hạn dù lỗi không tạm thời
Đáp án đúng: B

Câu 39. Khi stream phản hồi có yêu cầu gọi tool ở giữa, điều gì cần lưu ý?
A. Mọi chunk được phát đã hoàn thành các side effect
B. Stream đã phát text thì callback không thể chạy nữa
C. Chưa thể xem phần text đầu là kết quả cuối cùng
D. Mỗi chunk luôn là một JSON tool call độc lập
Đáp án đúng: C

Câu 40. Để quan sát lỗi trong chu trình tool calling, metric/log nào hữu ích?
A. Chỉ số class Java được tạo cho mỗi ChatClient
B. Chỉ số lượng tool có annotation được khai báo
C. Token bí mật và toàn bộ dữ liệu user đã gửi
D. Tên tool, trace ID, thời gian và trạng thái lỗi
Đáp án đúng: D

Câu 41. Unit test ToolCallback nên tập trung kiểm tra gì?
A. Gọi với arguments cố định và xác minh tác dụng phụ
B. Gọi model thật rồi so nội dung câu trả lời từng chữ
C. Chỉ kiểm tra số lượng bean khi Spring context khởi tạo
D. Chỉ kiểm tra tên package của phương thức gắn @Tool
Đáp án đúng: A

Câu 42. Khi kiểm thử input schema của tool, kịch bản nào hữu ích?
A. Thử thiếu trường required và sai kiểu dữ liệu
B. Chỉ truyền JSON hợp lệ với mọi trường bắt buộc
C. Chỉ so thời gian sinh nội dung của ChatModel
D. Chỉ đếm số ký tự trong description của công cụ
Đáp án đúng: A

Câu 43. Để kiểm tra vòng model -> tool -> model mà không dùng provider thật, nên làm gì?
A. Chỉ mock callback mà không mô phỏng lần gọi model
B. Để test gửi request thật rồi chấp nhận output bất kỳ
C. Giả lập model phát tool call và xác minh kết quả xử lý
D. Thay mọi tool thành system prompt và bỏ bước thực thi
Đáp án đúng: C

Câu 44. Khi người gọi không có quyền, bài test bảo mật nên kỳ vọng điều gì?
A. Tool vẫn chạy nhưng chỉ bỏ thông tin lỗi trả về
B. Model tự chỉnh quyền sau khi nhận từ chối
C. Ứng dụng cấp quyền tạm cho cùng tool request
D. Tool từ chối và không tạo side effect nghiệp vụ
Đáp án đúng: D

Câu 45. Để kiểm tra prompt injection từ tool output, test nên làm gì?
A. Chỉ kiểm tra khả năng đổi nhiệt độ của model
B. Cho output chứa chỉ dẫn injection để kiểm tra
C. Chỉ kiểm tra tên phương thức có annotation @Tool
D. Bỏ mọi kiểm tra role khi có dữ liệu từ callback
Đáp án đúng: B

Câu 46. Integration test tool calling nên kiểm tra chuỗi thao tác nào?
A. Chỉ kiểm tra ChatClient có thể khởi tạo bean
B. Chỉ kiểm tra PromptTemplate tạo đúng chuỗi text
C. Kiểm tra model gọi tool và nhận lại kết quả callback
D. Chỉ đo số lần ChatModel được khởi tạo lúc boot
Đáp án đúng: C

Câu 47. Khi thay đổi tên hay schema tham số tool đang dùng, cần lưu ý gì?
A. Cách đặt nhiệt độ để model sinh nhanh hơn
B. Kiểm tra tương thích caller và tool definition
C. Tên cột dùng để lưu embedding của người dùng
D. Số lượng TCP connection tới nhà cung cấp AI
Đáp án đúng: B

Câu 48. Khi nhiều user gọi cùng tool tốn tài nguyên, cần cơ chế nào?
A. Giới hạn tốc độ và mức đồng thời theo người gọi
B. Cho phép mọi request chạy hết mà không đặt hạn mức
C. Chỉ ẩn tên tool khỏi mô tả để giảm số request
D. Tăng số vòng model gọi tool để dàn bớt tải
Đáp án đúng: A
