Câu 1. Muốn đọc chuỗi JSON thành một đối tượng Customer, lời gọi Jackson nào phù hợp?
A. mapper.writeValueAsString(json) để lấy tên đối tượng
B. mapper.readValue(json, Customer.class) để ánh xạ
C. mapper.valueToTree(json) để tạo một đối tượng Customer
D. mapper.convertValue(json, String.class) để ánh xạ
Đáp án đúng: B

Câu 2. Với ObjectMapper cấu hình cho JSON, cách nào tạo văn bản JSON từ một POJO?
A. readTree(pojo) để đổi đối tượng thành cây
B. readValue(pojo, String.class) để đọc dữ liệu
C. treeToValue(pojo, String.class) để chuyển đổi
D. writeValueAsString(pojo) để xuất chuỗi JSON
Đáp án đúng: D

Câu 3. JSON gửi trường first_name nhưng DTO Java dùng firstName; annotation nào ánh xạ tường minh?
A. @JsonIgnore trên field firstName của DTO
B. @JsonFormat trên field firstName của DTO
C. @JsonProperty("first_name") trên property
D. @JsonInclude trên property firstName của DTO
Đáp án đúng: C

Câu 4. Nếu cần loại trường internalToken khỏi JSON khi serialize, annotation nào thường được dùng?
A. @JsonAlias để đổi tên khi nhận dữ liệu
B. @JsonIgnore trên property internalToken
C. @JsonCreator trên constructor của DTO
D. @JsonSetter trên phương thức cập nhật
Đáp án đúng: B

Câu 5. Khi chỉ muốn bỏ các property null lúc ghi JSON, cấu hình nào phù hợp?
A. @JsonInclude(Include.NON_NULL) cho DTO
B. @JsonIgnoreProperties(ignoreUnknown=true)
C. @JsonFormat(shape=Shape.STRING) trên DTO
D. @JsonProperty(required=true) cho mọi field
Đáp án đúng: A

Câu 6. DTO bất biến chỉ có constructor nhận tham số; hướng deserialize nào phù hợp với Jackson?
A. Ép mọi trường thành public static để đọc
B. Bắt buộc bỏ final khỏi mọi thuộc tính DTO
C. Bỏ constructor và để JSON tự sinh đối tượng
D. Dùng @JsonCreator và @JsonProperty ở tham số
Đáp án đúng: D

Câu 7. Khi đọc JSON array thành List<Order>, vì sao TypeReference<List<Order>> hữu ích?
A. Giữ thông tin kiểu phần tử lúc deserialize
B. Loại bỏ tự động tất cả phần tử trùng nhau
C. Chuyển danh sách thành một Map có khóa Order
D. Đảm bảo mọi phần tử được nạp bằng đa luồng
Đáp án đúng: A

Câu 8. Khi dùng JsonNode.path("address") mà khóa address không tồn tại, kết quả thường là gì?
A. Một TextNode có nội dung chuỗi rỗng
B. Một NullNode cho giá trị null tường minh
C. Một MissingNode thể hiện đường dẫn thiếu
D. Một ObjectNode tự thêm khóa mới vào cây
Đáp án đúng: C

Câu 9. Cần phân biệt JSON {"x":null} với JSON {} khi dùng JsonNode; cách kiểm tra nào phù hợp?
A. Dựa vào độ dài chuỗi JSON sau khi parse
B. Dùng asText() cho mọi node và so chuỗi rỗng
C. Gọi isObject() trên root cho cả hai trường hợp
D. So isNull() và isMissingNode() của path("x")
Đáp án đúng: D

Câu 10. Khi phải đọc một tệp JSON array rất lớn, cách nào giúp tránh giữ toàn bộ cây trong RAM?
A. Gọi readTree() rồi xử lý từng phần tử sau
B. Dùng JsonParser để đọc từng token liên tiếp
C. Gọi writeValueAsString() trước khi bắt đầu
D. Dùng convertValue() trên toàn bộ mảng dữ liệu
Đáp án đúng: B

Câu 11. Trong Jackson Streaming API, công cụ nào ghi JSON theo từng token ra output?
A. JsonNode dùng để duy trì toàn bộ cây dữ liệu
B. ObjectReader dùng để đọc một kiểu đối tượng
C. JsonGenerator dùng để phát token JSON lần lượt
D. TypeFactory dùng để mô tả kiểu generic Java
Đáp án đúng: C

Câu 12. Khi dùng chung ObjectMapper trên nhiều thread, nguyên tắc cấu hình nào an toàn?
A. Thay cấu hình mapper ngay khi request đang chạy
B. Cấu hình hoàn tất trước khi dùng chung mapper
C. Thêm module mới trong mỗi lời gọi readValue()
D. Đổi naming strategy theo từng request đồng thời
Đáp án đúng: B

Câu 13. Khi ánh xạ java.time.LocalDate, module Jackson nào thường được đăng ký?
A. JavaTimeModule để hỗ trợ các kiểu java.time
B. Jdk8Module để hỗ trợ kiểu Optional trong Java
C. AfterburnerModule để tối ưu hiệu năng ánh xạ
D. ParameterNamesModule để đọc tên tham số tạo đối tượng
Đáp án đúng: A

Câu 14. Một property ngày giờ cần pattern JSON riêng; annotation nào thường tùy biến cách biểu diễn?
A. @JsonIgnore để loại khỏi cả đọc và ghi
B. @JsonAlias để thêm tên khác khi đọc JSON
C. @JsonUnwrapped để bỏ lớp bao của object
D. @JsonFormat để khai báo shape hoặc pattern
Đáp án đúng: D

Câu 15. API dùng snake_case ở mọi property, Java dùng camelCase; cách cấu hình tổng thể nào hợp lý?
A. Đặt PropertyNamingStrategies.SNAKE_CASE
B. Dùng @JsonIgnore cho các property có dấu gạch
C. Chuyển mọi giá trị JSON sang chữ hoa trước đọc
D. Tắt hoàn toàn introspection của ObjectMapper
Đáp án đúng: A

Câu 16. Muốn chấp nhận cả user_name và username lúc đọc nhưng vẫn ghi ra một tên chuẩn, dùng gì?
A. @JsonIgnoreProperties để bỏ qua hai tên
B. @JsonRawValue để giữ nguyên đầu vào JSON
C. @JsonAlias khai báo các tên thay thế khi đọc
D. @JsonValue để dùng cả đối tượng làm giá trị
Đáp án đúng: C

Câu 17. API yêu cầu từ chối JSON có trường lạ ngoài hợp đồng; cách nào phù hợp?
A. Bật ACCEPT_SINGLE_VALUE_AS_ARRAY khi đọc
B. Tắt mọi kiểm tra lỗi trong ObjectMapper
C. Bật FAIL_ON_UNKNOWN_PROPERTIES khi deserialize
D. Cho phép tự bỏ qua mọi thuộc tính chưa khai báo
Đáp án đúng: C

Câu 18. Khi một kiểu Money cần được xuất ra JSON theo cấu trúc riêng, thành phần nào tùy biến bước ghi?
A. JsonSerializer<Money> để định nghĩa cách ghi
B. JsonDeserializer<Money> để định nghĩa cách đọc
C. TypeReference<Money> để định nghĩa kiểu generic
D. JsonParser để kiểm tra token đầu vào đã ghi
Đáp án đúng: A

Câu 19. Muốn biến JSON đặc thù thành đối tượng Money theo quy tắc nghiệp vụ, thành phần nào phù hợp?
A. JsonGenerator để phát token ra output
B. JsonSerializer<Money> để điều khiển bước ghi
C. PropertyNamingStrategy để đổi tên trường JSON
D. JsonDeserializer<Money> để xử lý bước đọc
Đáp án đúng: D

Câu 20. JSON đa hình nhận trường type từ client không tin cậy; thiết kế nào giảm rủi ro?
A. Chỉ cho phép subtype được định nghĩa và tin cậy
B. Cho client nhập tên lớp Java bất kỳ để nạp
C. Bật default typing toàn cục cho mọi kiểu Object
D. Tự tải mọi class được nêu trong dữ liệu gửi đến
Đáp án đúng: A

Câu 21. Vì sao bật polymorphic default typing quá rộng với JSON không tin cậy là nguy hiểm?
A. Vì JSON không hỗ trợ bất kỳ object lồng nào
B. Vì type metadata có thể kích hoạt kiểu nguy hiểm
C. Vì Jackson không thể đọc các kiểu dữ liệu generic
D. Vì parser luôn đổi mọi property thành public
Đáp án đúng: B

Câu 22. Dùng readTree() cho tệp JSON rất lớn có đánh đổi tài nguyên nào?
A. Dữ liệu sẽ được ghi thẳng xuống ổ đĩa ngay
B. Parser sẽ không cần tạo bất kỳ node trong RAM
C. Cây JsonNode có thể chiếm nhiều bộ nhớ
D. Luồng JSON sẽ luôn được xử lý bằng số thread vô hạn
Đáp án đúng: C

Câu 23. JSON có trường "age":"abc" nhưng DTO yêu cầu int; lỗi thuộc nhóm nào?
A. Lỗi kết nối HTTP với máy chủ dữ liệu đầu vào
B. Lỗi tính checksum trước khi parse dữ liệu
C. Lỗi định dạng cú pháp dấu ngoặc trong JSON
D. Lỗi ánh xạ giá trị kiểu, như InvalidFormatException
Đáp án đúng: D

Câu 24. Để bảo vệ tính tương thích khi cập nhật DTO và cấu hình Jackson, kiểm thử nào hữu ích?
A. Chỉ so thời gian chạy với một object trống
B. Kiểm thử đọc/ghi gồm null, field lạ và generic
C. Chỉ so định dạng thụt lề của JSON đầu ra
D. Chỉ chạy bộ biên dịch mà không deserialize
Đáp án đúng: B
