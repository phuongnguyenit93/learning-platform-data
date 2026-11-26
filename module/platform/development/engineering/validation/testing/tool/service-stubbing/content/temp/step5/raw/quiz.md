Câu 1. Khi stub GET /users/{id}, matcher nào giúp không trả nhầm dữ liệu giữa hai người dùng?
A. Ghép tất cả GET bất kể đường dẫn và query
B. Chỉ so HTTP method rồi trả response mặc định
C. Khớp phương thức, đường dẫn và tham số cần thiết
D. Chỉ so độ dài của body trong mỗi request GET
Đáp án đúng: C

Câu 2. Hai stub WireMock cùng khớp một request; cách nào giúp quy định stub cụ thể được ưu tiên?
A. Gán priority rõ ràng cho các stub có thể chồng nhau
B. Để thứ tự khởi chạy test quyết định stub được chọn
C. Tăng timeout của client cho đến khi hết trùng khớp
D. Dùng một response giống nhau cho mọi endpoint
Đáp án đúng: A

Câu 3. Request JSON có thứ tự property thay đổi; kiểm tra body nào phù hợp với nội dung JSON?
A. So chuỗi body từng ký tự kể cả dấu cách
B. Chỉ kiểm tra tổng số byte của payload JSON
C. Chỉ xét Content-Length của request gửi đến
D. So cấu trúc JSON theo trường và giá trị cần có
Đáp án đúng: D

Câu 4. Phân biệt stub response và verify request interaction như thế nào?
A. Stub định nghĩa phản hồi, verify xác nhận lời gọi
B. Stub chỉ đếm request, verify tự tạo body phản hồi
C. Stub luôn gọi API thật, verify thay thế phía server
D. Stub thiết lập JDK, verify khởi động Docker image
Đáp án đúng: A

Câu 5. Khi test cho phép mọi request không khớp nhận HTTP 200 mặc định, rủi ro chính là gì?
A. Mọi test đều tự động phát hiện endpoint viết sai
B. Sai phương thức hoặc URL có thể bị che giấu
C. HTTP client luôn bỏ qua nội dung response mới
D. Stub không còn hỗ trợ kịch bản trả về lỗi 500
Đáp án đúng: B

Câu 6. Để kiểm tra client có timeout khi dịch vụ chậm, stub nên mô phỏng yếu tố nào?
A. Thay đổi tên host của dịch vụ ở mỗi request
B. Tăng số trường JSON mà không thay đổi thời gian
C. Độ trễ phản hồi vượt cấu hình timeout của client
D. Giảm status code từ 200 xuống 201 khi gọi
Đáp án đúng: C

Câu 7. Muốn phân biệt xử lý HTTP 503 với lỗi kết nối bị ngắt, test cần gì?
A. Chỉ trả HTTP 200 với một body thông báo lỗi
B. Tạo kịch bản status 503 và fault mạng tách biệt
C. Dùng chung response JSON và bỏ kiểm tra retry
D. Thay tên endpoint nhưng giữ kết quả mặc định
Đáp án đúng: B

Câu 8. Trong test retry khi kết nối bị đóng trước phản hồi, stub cần hành vi nào?
A. Trả HTTP 201 với mã giao dịch vừa được tạo
B. Trả HTTP 400 với dữ liệu xác thực không hợp lệ
C. Trả HTTP 200 sau khi ghi một bản log mới
D. Mô phỏng lỗi truyền tải thay vì response HTTP
Đáp án đúng: D

Câu 9. Request có nhiều trường động, nhưng test chỉ cần xác nhận accountId; cách ghép nào phù hợp?
A. Dùng JSONPath hoặc matcher cho trường quan trọng
B. So nguyên body với timestamp cố định của lần trước
C. Chỉ khớp độ lớn request mà bỏ qua toàn bộ giá trị
D. So đúng thứ tự mọi trường trong chuỗi JSON đầu vào
Đáp án đúng: A

Câu 10. Trong MockServer, expectation thường ghép những thành phần nào?
A. Chỉ số lần JVM thực hiện garbage collection
B. Điều kiện request và phản hồi hoặc hành động dự kiến
C. Tên lớp Java nội bộ của hệ thống được kiểm thử
D. Số câu lệnh SQL có trong ứng dụng gọi tới
Đáp án đúng: B

Câu 11. Với luồng trả 202 ở lần gọi đầu và 200 ở lần sau, công cụ stub cần khả năng nào?
A. Trả ngẫu nhiên status từ danh sách đã định
B. Giữ chung response bất kể số lần client gọi
C. Theo dõi trạng thái kịch bản giữa các request
D. Chỉ xác minh body của request đầu tiên
Đáp án đúng: C

Câu 12. Test dùng kịch bản stub có trạng thái; điều gì giúp lần chạy sau độc lập?
A. Dùng cổng mạng ngẫu nhiên nhưng giữ state cũ
B. Reset trạng thái kịch bản và lịch sử lời gọi
C. Chỉ kiểm tra status cuối mà không reset request
D. Tái sử dụng mọi expectation từ test trước
Đáp án đúng: B

Câu 13. Khi giả lập hệ thống thanh toán bên ngoài, điều gì cần lưu ý về kết quả test?
A. Stub bảo đảm toàn bộ API thật đáp ứng mọi hợp đồng
B. Stub thay thế hoàn toàn kiểm thử tích hợp với đối tác
C. Stub kiểm chứng được cấu hình sản xuất của đối tác
D. Stub kiểm tra logic client theo phản hồi mô phỏng
Đáp án đúng: D

Câu 14. Client chỉ được gọi POST /payments một lần; cách xác minh tương tác phù hợp là gì?
A. Kiểm tra số lời gọi POST khớp đúng bằng một
B. Chỉ kiểm tra stub đã được khai báo trước test
C. Kiểm tra số lần GET dù endpoint cần kiểm là POST
D. Chỉ so mã HTTP cuối cùng của ứng dụng client
Đáp án đúng: A

Câu 15. Stub chạy cổng động trên CI; ứng dụng đang kiểm thử nên biết địa chỉ stub thế nào?
A. Ghi cứng cổng 8080 trong mọi file cấu hình
B. Chỉ đổi DNS ở hệ điều hành của máy chạy test
C. Tự tìm cổng bằng cách thử toàn bộ các cổng TCP
D. Tiêm base URL thực tế qua cấu hình lúc chạy
Đáp án đúng: D

Câu 16. Muốn test không vô tình gọi hệ thống ngoài thật, nên thiết kế dependency HTTP ra sao?
A. Luôn gọi URL production rồi chặn ở trình duyệt
B. Tạo HTTP client trong từng method không có cấu hình
C. Cho phép thay endpoint hoặc client bằng cấu hình
D. Chỉ chuyển toàn bộ test sang môi trường production
Đáp án đúng: C

Câu 17. Để stub phản ánh contract của provider, lựa chọn nào là phù hợp?
A. Chỉ dùng response 200 mà không có body cho mọi ca
B. Mô phỏng status, header và cấu trúc dữ liệu đã cam kết
C. Chỉ ghi log request nhưng không trả trường bắt buộc
D. Trả dữ liệu ngẫu nhiên để mọi test thay đổi mỗi lần
Đáp án đúng: B

Câu 18. Request cần Bearer token; matcher nào giảm nguy cơ chấp nhận sai request?
A. Kiểm tra header Authorization theo mẫu mong đợi
B. Chỉ so Content-Type của body mà không xét token
C. Chỉ xác nhận rằng URL có chứa chữ authentication
D. Để stub luôn chấp nhận mọi giá trị header gửi lên
Đáp án đúng: A

Câu 19. Stub có quy tắc fallback quá rộng; test nhầm endpoint vẫn nhận phản hồi hợp lệ. Cách sửa nào phù hợp?
A. Tăng thời gian đợi response cho cả bộ test
B. Giữ fallback vì mã 200 giúp tránh flaky test
C. Thu hẹp matcher và kiểm tra unmatched requests
D. Cho phép lặp request nhiều lần cho đến khi thành công
Đáp án đúng: C

Câu 20. Hai test chạy song song dùng chung một stub server có state; rủi ro nào cần giải quyết?
A. Các expectation và nhật ký lời gọi có thể ảnh hưởng nhau
B. Port của server luôn tự động tăng sau mỗi request
C. Thread test không thể đọc được JSON từ stub server
D. Tên package của các class Java sẽ thay đổi khi chạy
Đáp án đúng: A

Câu 21. Khi response stub có transactionId tạo ngẫu nhiên, cách giúp assertion ổn định là gì?
A. Để response thay đổi rồi chỉ assert có HTTP 200
B. Sinh lại transactionId cho mỗi lần replay kịch bản
C. Chỉ dùng dữ liệu từ giao dịch thật trong production
D. Dùng dữ liệu kiểm thử cố định hoặc matcher phù hợp
Đáp án đúng: D

Câu 22. Trong CI, test cần dùng stub server chạy riêng; điều kiện nào nên được kiểm tra trước?
A. Kết quả chạy build giao diện của ứng dụng đối tác
B. Server stub đã lắng nghe và sẵn sàng nhận request
C. Mọi request đã được gửi trước khi server khởi động
D. Tất cả test phụ thuộc đều đã chạy một lượt thành công
Đáp án đúng: B

Câu 23. Vì sao nên có kiểm thử với provider thật dù unit/integration test dùng stubs đều đạt?
A. Stub kiểm tra được cấu hình TLS và schema thực ở mọi lúc
B. Stub luôn phát hiện thay đổi provider ngay sau khi triển khai
C. Stub có thể lệch hành vi thực tế khi contract thay đổi
D. Stub chứng minh được chất lượng mạng của bên thứ ba
Đáp án đúng: C

Câu 24. Client gọi lại khi gặp 503; test nào xác minh đúng retry policy?
A. Gửi một request 200 rồi chỉ kiểm tra payload trả về
B. Để stub trả 503 mãi và không kiểm số lần gọi
C. Bỏ kiểm tra thời gian chờ giữa những lần thử lại
D. Trả 503 rồi 200, xác minh số lần và kết quả cuối
Đáp án đúng: D
