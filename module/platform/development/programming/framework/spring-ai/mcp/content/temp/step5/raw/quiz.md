Câu 1. Mục đích chính của Model Context Protocol (MCP) khi tích hợp AI là gì?
A. Thống nhất API dùng tools, resources và prompts
B. Chuẩn hóa định dạng trọng số giữa các mô hình AI
C. Chuẩn hóa cách huấn luyện mô hình trong Spring Boot
D. Chuẩn hóa lưu trữ mọi lịch sử chat trên MCP Server
Đáp án đúng: A

Câu 2. Trong kiến trúc MCP, ứng dụng AI giữ kết nối tới các server thường đóng vai trò gì?
A. Server cung cấp công cụ nghiệp vụ để host gọi
B. Resource cung cấp nội dung để provider tự tải
C. Transport cung cấp giao diện sinh response của model
D. Host quản lý kết nối MCP client và tương tác model
Đáp án đúng: D

Câu 3. Trong một kết nối MCP, thành phần nào cung cấp tools cho phía client?
A. MCP Host tự phát minh định nghĩa tool của server
B. MCP Transport tự dựng tool từ nội dung chat
C. MCP Server công bố và thực thi các tool của mình
D. MCP Client tự triển khai toàn bộ nghiệp vụ của server
Đáp án đúng: C

Câu 4. Khái niệm tool trong MCP thường đại diện cho điều gì?
A. Nguồn nội dung đọc bằng URI để đưa vào ngữ cảnh
B. Mẫu thông điệp tái sử dụng với biến truyền vào
C. Thông tin phiên bản protocol do hai bên thương lượng
D. Thao tác có thể gọi với tham số đã định nghĩa
Đáp án đúng: D

Câu 5. Resource trong MCP khác tool chủ yếu ở mục đích nào?
A. Yêu cầu thực thi nghiệp vụ với JSON arguments
B. Nội dung có URI để phía client truy cập và đọc
C. Thay đổi trạng thái nguồn dữ liệu bằng lệnh gọi
D. Chứa lời gọi function mà model đã chọn thực thi
Đáp án đúng: B

Câu 6. Prompt capability của MCP được dùng phổ biến để làm gì?
A. Mẫu message có tham số để client sử dụng
B. Tạo thông báo lỗi khi tool không chạy thành công
C. Định nghĩa chính sách xác thực của HTTP transport
D. Lưu khóa bí mật cho những phiên kết nối khác nhau
Đáp án đúng: A

Câu 7. Khi cần cho model tra cứu tài liệu có URI ổn định, capability nào phù hợp?
A. Tool buộc phải ghi kết quả tìm kiếm vào database
B. Resource đọc dữ liệu theo URI do server công bố
C. Prompt tự đăng ký kết nối dữ liệu với một broker
D. Sampling dùng để gửi tất cả nội dung về provider
Đáp án đúng: B

Câu 8. Khi cần thực hiện phép tính thuế với tham số đầu vào, nên chọn capability nào?
A. Resource chỉ lưu một văn bản mô tả thuế suất
B. Tool nhận đầu vào theo schema và tính kết quả
C. Prompt chỉ hiển thị câu hỏi cho người dùng tự tính
D. Transport chỉ chuyển văn bản giữa các tầng mạng
Đáp án đúng: B

Câu 9. Thông tin nào trong mô tả MCP tool giúp client tạo lời gọi hợp lệ?
A. URI của resource cùng MIME type đọc dữ liệu
B. Danh sách prompt mẫu cùng các message đã tạo
C. Tên, mô tả cùng input schema của tool
D. Tên provider AI và token quota của model nền
Đáp án đúng: C

Câu 10. Để khám phá các tool do MCP Server hỗ trợ, client thường dùng thao tác nào?
A. tools/call để lấy danh sách tool mà không cần tên
B. resources/read để tải các descriptor của tool
C. prompts/get để lấy thông số của tất cả tool
D. tools/list trả metadata của các tool đã công bố
Đáp án đúng: D

Câu 11. Khi đã biết tên tool và tham số, client gọi MCP tool bằng thao tác nào?
A. tools/call với tên tool và arguments tương ứng
B. tools/list kèm payload nghiệp vụ để chạy tool
C. resources/list kèm input JSON để thực thi tool
D. prompts/get kèm tên tool thay cho prompt name
Đáp án đúng: A

Câu 12. Đối với MCP tool, input schema có vai trò trực tiếp nào?
A. Mô tả kiểu và ràng buộc của tham số đầu vào
B. Định nghĩa toàn bộ cách xác thực mọi user trên server
C. Định nghĩa chính xác nội dung câu trả lời của model
D. Đặt số luồng HTTP mà server được phép sử dụng
Đáp án đúng: A

Câu 13. Khi input schema yêu cầu orderId nhưng caller không gửi, server nên làm gì?
A. Tự chọn một đơn hàng mặc định mà không xác nhận
B. Gọi tool với một chuỗi rỗng và coi đã hợp lệ
C. Dùng tên phiên kết nối làm orderId thay thế
D. Báo lỗi tham số trước khi chạy logic nghiệp vụ
Đáp án đúng: D

Câu 14. Trong Spring AI, @Tool trên phương thức Java thường nhằm mục đích gì?
A. Đánh dấu phương thức chỉ dùng để tạo embedding vector
B. Đánh dấu phương thức Java có thể làm AI tool
C. Đánh dấu Bean luôn chạy cùng transaction của ChatClient
D. Đánh dấu phương thức là endpoint REST theo HTTP GET
Đáp án đúng: B

Câu 15. Khi Spring AI MCP Server xuất các nghiệp vụ Java thành MCP tools, cách tiếp cận nào phù hợp?
A. Đăng ký ToolCallbackProvider để công bố các tool
B. Đưa logic nghiệp vụ vào mọi message role system
C. Chỉ tạo một ChatModel là server tự sinh các tool
D. Chỉ khai báo PromptTemplate mà bỏ qua tool callback
Đáp án đúng: A

Câu 16. Với Spring AI MCP Client, cách tích hợp công cụ MCP vào ChatClient là gì?
A. Chép toàn bộ kết quả tools/list vào nội dung system
B. Đưa tool callbacks của MCP client vào ChatClient
C. Gắn MCP Server vào ChatResponse sau khi call xong
D. Đổi kiểu output của ChatModel thành Resource response
Đáp án đúng: B

Câu 17. Vì sao tool discovery không đồng nghĩa với quyền được gọi mọi tool?
A. Một tool được liệt kê luôn phải chạy bằng tài khoản admin
B. MCP client tự kiểm chứng quyền trên mọi dữ liệu nghiệp vụ
C. Provider AI quyết định quyền thay vì server giữ dữ liệu
D. Tool được liệt kê vẫn cần kiểm tra quyền thực thi
Đáp án đúng: D

Câu 18. Khi model đề xuất gọi tool cập nhật dữ liệu, ai phải kiểm soát quyền?
A. Ứng dụng và MCP Server kiểm tra quyền người gọi
B. Chính model tự xác nhận quyền trong nội dung trả lời
C. MCP Transport tự đặt tài khoản đọc ghi phù hợp
D. Prompt mẫu được xem là chứng nhận quyền cập nhật
Đáp án đúng: A

Câu 19. Trong triển khai MCP local bằng STDIO, dữ liệu protocol đi qua đâu?
A. HTTP request và response trên cùng một cổng TCP
B. WebSocket nhị phân giữa hai Spring Boot instance
C. Một message broker lưu bền vững cho từng request
D. Luồng stdin/stdout giữa client và tiến trình server
Đáp án đúng: D

Câu 20. Trong STDIO transport, ghi log tùy ý ra stdout có thể gây lỗi gì?
A. Làm tool discovery tự chuyển thành resources/list
B. Làm mọi message trở thành yêu cầu HTTP POST
C. Trộn log vào luồng protocol và làm sai dữ liệu đọc
D. Làm JSON schema của tool bị sửa trong bộ nhớ
Đáp án đúng: C

Câu 21. Khi MCP Server chạy riêng trên máy khác, transport nào phù hợp hơn STDIO?
A. STDIO đọc trực tiếp file trên máy chủ ở xa
B. Streamable HTTP cho kết nối MCP client qua mạng
C. In-process call dùng chung một JVM cho cả hai phía
D. Local socket chỉ tồn tại trong tiến trình MCP Host
Đáp án đúng: B

Câu 22. Khi dùng transport MCP qua mạng, cấu hình nào giúp bảo vệ đường truyền?
A. Chỉ đặt tên tool khó đoán để tránh bị đọc trộm
B. Chỉ đổi tên trường JSON mà không mã hóa request
C. TLS và xác thực endpoint theo cấu hình phù hợp
D. Chỉ tăng timeout để tránh mất gói tin trên mạng
Đáp án đúng: C

Câu 23. Trong MCP, bước initialize ban đầu nhằm đạt mục đích gì?
A. Gọi toàn bộ tool để kiểm tra trước mỗi request
B. Nạp đầy đủ mọi resource vào prompt ngay khi kết nối
C. Xác nhận nội dung nghiệp vụ của từng lời gọi tool
D. Thương lượng phiên bản và capability được hỗ trợ
Đáp án đúng: D

Câu 24. Khi client và server không tương thích giao thức, cách xử lý phù hợp là gì?
A. Báo lỗi tương thích thay vì chạy method không hỗ trợ
B. Bỏ kiểm tra phiên bản và thực thi mọi request
C. Đổi tool name thành resource URI để tiếp tục
D. Gộp các method lạ thành một prompt mặc định
Đáp án đúng: A

Câu 25. Khi client muốn lấy danh sách resource, phương thức MCP nào liên quan?
A. resources/read để tìm tool callback của host
B. tools/list để tải dữ liệu từng resource đã đọc
C. resources/list để khám phá URI từ phía server
D. prompts/list để lấy URI của toàn bộ resource
Đáp án đúng: C

Câu 26. Sau khi biết URI resource, client cần làm gì để lấy nội dung?
A. Gọi tools/list và dùng URI làm tên tool
B. Gọi resources/read với URI được chọn từ server
C. Gọi prompts/get với URI làm tên prompt
D. Gọi initialize lại và gửi toàn bộ nội dung URI
Đáp án đúng: B

Câu 27. Khi MCP client muốn liệt kê các prompt mẫu, method nào phù hợp?
A. prompts/get để chạy toàn bộ prompt cùng lúc
B. resources/read để tải message của từng prompt
C. tools/call để lấy prompt name không có arguments
D. prompts/list lấy mô tả prompt được server công bố
Đáp án đúng: D

Câu 28. Khi lấy một MCP prompt có đối số cụ thể, phương thức nào phù hợp?
A. prompts/get kèm tên prompt và arguments tương ứng
B. prompts/list kèm JSON kết quả của model chat
C. tools/list với URI tương ứng của prompt
D. resources/list với tên prompt thay cho resource
Đáp án đúng: A

Câu 29. Nếu MCP Server cung cấp tool xóa đơn hàng, thiết kế input nào an toàn hơn?
A. Nhận yêu cầu trống rồi tự chọn đơn hàng gần nhất
B. Dựa vào lời giải thích do model tạo để xác nhận quyền
C. Yêu cầu ID xác định và xác minh quyền xóa
D. Gộp mọi đơn hàng người dùng vào một lần xóa
Đáp án đúng: C

Câu 30. Để hạn chế tác động của tool có quyền ghi, nên áp dụng gì?
A. Cấp quyền admin vì model có thể cần chạy mọi tool
B. Dùng một API key toàn quyền cho mọi tenant cùng nhau
C. Bỏ kiểm tra scope sau khi đã kết nối MCP thành công
D. Cấp quyền tối thiểu và xác nhận lệnh nhạy cảm
Đáp án đúng: D

Câu 31. Vì sao kết quả MCP tool không nên được coi là system instruction?
A. Mọi tool result đều được ký và có quyền ưu tiên cao
B. Tool output luôn được kiểm chứng bởi MCP transport
C. Tool output có thể chứa prompt injection không đáng tin
D. Model có thể bỏ qua mọi ràng buộc ứng dụng khi đọc tool
Đáp án đúng: C

Câu 32. Nếu resource chứa hướng dẫn yêu cầu tiết lộ secret, host nên xử lý ra sao?
A. Xem đó là dữ liệu không tin cậy, không làm theo
B. Nâng nội dung resource thành system message ưu tiên
C. Chuyển secret cho tool đó vì resource có URI hợp lệ
D. Xác nhận quyền dựa trên tên resource đã được liệt kê
Đáp án đúng: A

Câu 33. Khi dùng nhiều MCP Server có tool trùng tên, client nên làm gì?
A. Ưu tiên tool có mô tả dài hơn bất kể nguồn
B. Phân biệt tool theo server nguồn và tên riêng
C. Gộp input schema của các tool thành schema duy nhất
D. Gọi đồng thời mọi server rồi nhận kết quả đầu tiên
Đáp án đúng: B

Câu 34. Khi MCP tool thao tác tài khoản của người dùng, kiểm tra quan trọng nào cần có?
A. Chỉ kiểm tra tên tool đúng định dạng chữ thường
B. Kiểm tra quyền dữ liệu của principal ở server
C. Chỉ xác nhận model gọi tool qua một PromptTemplate
D. Chỉ kiểm tra URI server nằm trong cấu hình client
Đáp án đúng: B

Câu 35. Khi server nhận tham số tool do model tự sinh, điều nào cần thiết?
A. Validate schema và ràng buộc nghiệp vụ của tham số
B. Coi mọi tham số từ model là đã qua kiểm tra
C. Bỏ ràng buộc vì tool descriptor có JSON schema
D. Dùng temperature thấp để bảo đảm tham số đúng
Đáp án đúng: A

Câu 36. Nếu lệnh MCP tool đã ghi DB nhưng client mất phản hồi, rủi ro khi retry là gì?
A. Client tự rollback DB ngay khi mất kết nối
B. JSON-RPC luôn ngăn lệnh ghi được chạy thêm lần nữa
C. Thao tác có thể chạy lặp nếu tool thiếu idempotency
D. Schema của tool sẽ tự ngăn mọi lần gọi lặp
Đáp án đúng: C

Câu 37. Để retry an toàn thao tác tạo đơn, cách thiết kế nào hợp lý?
A. Đổi key ở mỗi lần thử để đảm bảo duy nhất
B. Tắt mọi bước xác thực để request không bị chậm
C. Giữ cùng idempotency key khi gọi lại một yêu cầu
D. Phát lại yêu cầu liên tục cho đến khi có phản hồi
Đáp án đúng: C

Câu 38. Khi tool bị timeout, client nên xử lý thế nào?
A. Giả định tool chắc chắn chưa có side effect nào
B. Xem kết quả chưa rõ và chỉ retry có kiểm soát
C. Đổi tên tool và gọi lại không giới hạn thời gian
D. Xóa trạng thái nghiệp vụ cũ để tránh kết quả chờ
Đáp án đúng: B

Câu 39. Với lệnh không thể đảo ngược, biện pháp nào thích hợp trước khi thực thi?
A. Cho model tự xác nhận thay người dùng của hành động
B. Bỏ ghi nhận audit vì tool đã có kết quả response
C. Chỉ dựa vào mô tả tool để biết người gọi được phép
D. Xác nhận và kiểm tra quyền trước khi chạy lệnh
Đáp án đúng: D

Câu 40. Khi nhận phản hồi tool với isError=true, nên hiểu thế nào?
A. Transport đã tự khôi phục và sẽ gửi bản sao request
B. Phản hồi công cụ báo lỗi trong quá trình thực thi
C. Prompt mà client đọc đã được dùng sai tên biến
D. Client phải xóa toàn bộ danh sách tool được khám phá
Đáp án đúng: B

Câu 41. Để kiểm thử MCP tool với input sai schema, kịch bản nào phù hợp?
A. Gửi thiếu tham số bắt buộc và kiểm tra báo lỗi
B. Gửi request hợp lệ và chỉ kiểm tra latency trung bình
C. Chạy tool bằng tài khoản admin để tránh lỗi input
D. Gọi tools/list rồi coi đó là test validation
Đáp án đúng: A

Câu 42. Integration test MCP Server qua transport nên xác minh điều gì?
A. Chỉ kiểm tra Spring context khởi tạo thành công
B. Chỉ kiểm tra các lớp Java có annotation @Tool
C. Chỉ đo số lượng bean ToolCallback được đăng ký
D. Test initialize, tools/list và tools/call qua transport
Đáp án đúng: D

Câu 43. Để test ChatClient gọi tool mà không cần provider AI thật, nên làm gì?
A. Gọi provider thật nhiều lần để tìm câu trả lời ổn định
B. Tắt test tool vì không thể dự đoán thời điểm model gọi
C. Dùng model giả lập với lời gọi tool xác định
D. Bật quyền ghi production cho tool của môi trường test
Đáp án đúng: C

Câu 44. Khi MCP Server trả dữ liệu nhạy cảm, nguyên tắc bảo mật nào quan trọng?
A. Trả đầy đủ dữ liệu để model tự quyết định phần cần dùng
B. Đưa token bí mật vào tool output để client tiện gọi
C. Giới hạn dữ liệu và che trường nhạy cảm trước khi trả
D. Ghi toàn bộ dữ liệu cá nhân vào log ở server
Đáp án đúng: C

Câu 45. Để theo dõi lỗi tool trong ứng dụng, thông tin log nào hữu ích?
A. Toàn bộ access token của client và server
B. Mọi payload có PII để debug không cần xác thực
C. Chỉ số thread khi server khởi động lần đầu
D. Tên tool, trace ID, độ trễ và mã lỗi đã làm sạch
Đáp án đúng: D

Câu 46. Khi tool output rất lớn, client nên xử lý thế nào trước khi đưa vào prompt?
A. Nạp trọn dữ liệu bất kể context window
B. Giới hạn output và chọn phần dữ liệu liên quan
C. Bỏ toàn bộ kiểm tra PII để tránh mất dữ liệu
D. Đổi mọi nội dung lớn thành system instruction
Đáp án đúng: B

Câu 47. Khi kết nối MCP Server bị ngắt, hành vi nào nên được triển khai?
A. Nối lại có giới hạn và báo lỗi khi gián đoạn
B. Giả định client vẫn có thể gọi mọi tool như trước
C. Dùng kết quả tools/list cũ làm bảo đảm tool vẫn hoạt động
D. Chạy mọi tool đã khám phá trên host để thay server
Đáp án đúng: A

Câu 48. Nếu server không công bố prompts capability, MCP client nên làm gì?
A. Gọi prompts/get liên tục để buộc server tạo prompt
B. Dùng tools/list thay cho cơ chế khai báo capability
C. Không gọi prompts/get khi capability chưa được hỗ trợ
D. Gộp resources/read thành prompt mặc định ở client
Đáp án đúng: C
