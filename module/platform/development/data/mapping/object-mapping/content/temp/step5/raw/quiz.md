Câu 1: Vì sao API Java nên trả Response DTO thay vì đưa JPA Entity trực tiếp?
A. Giữ nguyên mọi field entity để client tự quyết định truy cập
B. Kiểm soát field công khai và tách API khỏi mô hình lưu trữ
C. Bỏ bước phân quyền do DTO không còn tham chiếu entity
D. Tự động ngăn mọi truy vấn N+1 khi serial hóa response
Đáp án đúng: B

Câu 2: Khi viết mapper thủ công, lợi ích chính là gì?
A. Tự phát sinh implementation qua annotation processor
B. Tự cập nhật mapping mỗi khi entity đổi tên field
C. Kiểm soát tường minh từng phép gán và chuyển đổi giá trị
D. Tự động hỗ trợ mọi kiểu dữ liệu không cần logic thêm
Đáp án đúng: C

Câu 3: MapStruct tạo implementation cho mapper Java chủ yếu khi nào?
A. Khi ứng dụng xử lý request đầu tiên ở runtime
B. Khi biên dịch thông qua Java annotation processor
C. Khi reflection quét mọi object mỗi lần mapping
D. Khi hệ thống ORM gọi flush tại cuối transaction
Đáp án đúng: B

Câu 4: Muốn inject mapper MapStruct bằng Spring, khai báo thông dụng là gì?
A. @Mapper(componentModel = "spring") trên interface mapper
B. @Mapper(componentModel = "default") trên entity
C. @Mapping(componentModel = "spring") trên field DTO
D. @BeanMapping(componentModel = "spring") trên service
Đáp án đúng: A

Câu 5: Khi tên field nguồn và đích khác nhau trong MapStruct, dùng gì?
A. @Mapper với source và target tương ứng
B. @BeanMapping với source và target tương ứng
C. @Mapping với source và target tương ứng
D. @Context với source và target tương ứng
Đáp án đúng: C

Câu 6: Khi lấy field lồng nhau trong MapStruct, cơ chế nào phù hợp?
A. Dùng source như tên lớp rồi reflection mọi field
B. Dùng target là tên database table của quan hệ
C. Dùng source dạng đường dẫn như customer.address.city
D. Dùng target là khóa JSON Pointer khi đọc entity
Đáp án đúng: C

Câu 7: Với List<Entity> sang List<DTO>, MapStruct thường làm gì nếu có mapper phần tử?
A. Sinh vòng lặp và gọi ánh xạ cho từng phần tử
B. Trả về List gốc bằng cách đổi kiểu generic
C. Serialize List thành JSON rồi parse từng phần tử
D. Cập nhật trực tiếp List nguồn để cùng trỏ tới DTO
Đáp án đúng: A

Câu 8: Trong MapStruct, cách cập nhật entity đã có thay vì tạo entity mới là gì?
A. Nhận entity đích qua tham số gắn @MappingTarget
B. Truyền entity đích vào tham số gắn @Context
C. Đánh dấu entity đích bằng annotation @Target
D. Khai báo mapper chỉ có tham số DTO đầu vào
Đáp án đúng: A

Câu 9: Khi patch chỉ sửa field đã gửi, làm gì với field không xuất hiện?
A. Tự gán null cho tất cả field không gửi trong request
B. Tự gán giá trị mặc định của Java cho field không gửi
C. Tự copy từ entity khác có cùng loại và cùng phiên bản
D. Giữ nguyên giá trị cũ theo hợp đồng update từng phần
Đáp án đúng: D

Câu 10: MapStruct thường xử lý null source property trong update bằng gì để bỏ qua?
A. Cấu hình NullValueCheckStrategy.ALWAYS để bỏ qua mọi null
B. Cấu hình NullValuePropertyMappingStrategy.IGNORE
C. Cấu hình CollectionMappingStrategy.ADDER_PREFERRED để bỏ qua
D. Cấu hình ReportingPolicy.WARN để giữ toàn bộ giá trị đích
Đáp án đúng: B

Câu 11: Vì sao PATCH cần phân biệt field vắng mặt với field gửi null?
A. Để luôn coi null là không được phép cập nhật
B. Để luôn thay null thành chuỗi rỗng trên mọi field
C. Để mặc định ghi đè cả những field không truyền
D. Để phân biệt giữ nguyên và chủ động xóa giá trị
Đáp án đúng: D

Câu 12: Khi DTO dùng int nguyên thủy nhưng API có thể gửi null, rủi ro gì?
A. Không thể dùng JSON để truyền giá trị int bằng 0
B. Không biểu diễn được null và dễ lẫn với giá trị 0
C. Không thể biên dịch DTO có field kiểu int trong Java
D. Không thể lưu field int vào database có cột số nguyên
Đáp án đúng: B

Câu 13: Để ngăn mass assignment khi nhận request DTO, cách nào an toàn?
A. Cho mapper copy mọi field trùng tên từ request sang entity
B. Cho client đặt cả quyền hạn và khóa chính để tiện mapping
C. Chỉ whitelist các field được phép ánh xạ vào domain
D. Cho mapping runtime tự quyết quyền sửa từ tên field
Đáp án đúng: C

Câu 14: Khi ánh xạ graph hai chiều Entity A↔B, cần lưu ý điều gì?
A. Chu trình tham chiếu luôn làm MapStruct lỗi biên dịch
B. Chu trình tham chiếu luôn tự được bỏ qua trong Java
C. Chu trình tham chiếu luôn bị ORM xóa khi gọi mapper
D. Chu trình tham chiếu có thể gây đệ quy vô hạn
Đáp án đúng: D

Câu 15: Với quan hệ JPA lazy, map DTO có thể gây vấn đề nào?
A. N+1 query hoặc truy cập dữ liệu ngoài phiên làm việc
B. Tự tạo transaction mới cho mỗi field primitive
C. Tự thay đổi khóa chính của entity ở mọi lần ánh xạ
D. Tự làm mất tất cả index của bảng cơ sở dữ liệu
Đáp án đúng: A

Câu 16: Nếu DTO chỉ cần vài field quan hệ, cách giảm N+1 thích hợp là gì?
A. Thiết kế fetch plan hoặc projection theo dữ liệu cần dùng
B. Luôn chuyển quan hệ sang EAGER cho toàn bộ entity
C. Luôn đóng persistence context trước khi chạy mapper
D. Luôn gọi mapping hai lần để cache giá trị lần đầu
Đáp án đúng: A

Câu 17: Khi cần sửa kết quả mapping sau bước tạo object, MapStruct hỗ trợ gì?
A. Dùng phương thức @BeforeEach trên interface mapper
B. Dùng phương thức @PrePersist trên class DTO đích
C. Dùng phương thức @Transactional trên field nguồn
D. Dùng phương thức @AfterMapping với chữ ký phù hợp
Đáp án đúng: D

Câu 18: Khi có nhiều converter String→Enum, MapStruct chọn converter cụ thể bằng gì?
A. Dùng @Named và qualifiedByName để chọn phương thức
B. Dùng @Primary trên từng property của đối tượng DTO
C. Dùng @Order trên danh sách toàn bộ field trong entity
D. Dùng @Autowired trên từng tham số của phương thức
Đáp án đúng: A

Câu 19: ModelMapper khác MapStruct điển hình ở điểm nào?
A. Dựa trên quy ước và cấu hình mapping tại runtime
B. Luôn phát sinh Java source qua annotation processor
C. Luôn sinh SQL query để đọc mọi quan hệ entity
D. Luôn yêu cầu interface mapper có componentModel
Đáp án đúng: A

Câu 20: Khi ModelMapper đoán sai tên field, nên điều chỉnh gì?
A. Tăng mức logging để tự đổi tên field lúc runtime
B. Khai báo TypeMap với quy tắc ánh xạ tường minh
C. Thêm constructor mặc định vào mọi entity để đổi tên
D. Ép tất cả property sang public để bỏ kiểm tra tên
Đáp án đúng: B

Câu 21: Khi source có mã enum mới mà DTO chưa hỗ trợ, cần xử lý gì?
A. Ép giá trị enum mới thành phần tử đầu tiên bất kỳ
B. Luôn chuyển mọi enum mới sang null mà không cảnh báo
C. Giữ nguyên ordinal vì thứ tự enum không bao giờ đổi
D. Đặt chính sách chuyển đổi và báo lỗi hoặc fallback rõ
Đáp án đúng: D

Câu 22: Khi chuyển BigDecimal sang chuỗi trong DTO, quy tắc nào nên xác định?
A. Dựa vào locale của host để client tự suy đoán số
B. Đổi BigDecimal sang float để giảm dung lượng trước
C. Loại bỏ mọi chữ số thập phân để response dễ parse
D. Định dạng, dấu thập phân và locale theo hợp đồng API
Đáp án đúng: D

Câu 23: Với collection nullable, mapper cần xác định điều gì?
A. Luôn coi null list và list rỗng là cùng một hành vi
B. Luôn loại phần tử null khỏi collection không cần ghi rõ
C. Quy tắc null, list rỗng và phần tử null theo hợp đồng
D. Luôn tạo collection mutable kể cả đích là bất biến
Đáp án đúng: C

Câu 24: Khi DTO bất biến không có setter, chiến lược mapping nào phù hợp?
A. Bắt buộc sửa field private bằng reflection không giới hạn
B. Bắt buộc sửa field final sau khi khởi tạo object đích
C. Bắt buộc đổi DTO thành entity mutable để có setter
D. Sử dụng constructor hoặc builder được mapper hỗ trợ
Đáp án đúng: D

Câu 25: Kiểm thử mapper chứa dữ liệu nhạy cảm nên xác nhận điều gì?
A. Các field private đều được copy sang response để so sánh
B. Các field chỉ đọc được mapping trở lại entity khi update
C. Các field không cho phép không xuất hiện ở DTO phản hồi
D. Các field quyền hạn luôn được client thay đổi qua DTO
Đáp án đúng: C

Câu 26: Khi cập nhật Entity đã quản lý bởi JPA, vì sao cần giữ identity?
A. Để MapStruct luôn tự phát sinh id mới cho entity đã tồn tại
B. Tránh mất quan hệ và trạng thái theo dõi của persistence context
C. Để mọi thay đổi đều bỏ qua dirty checking của JPA
D. Để DTO có thể giữ phiên làm việc JDBC sau mapping
Đáp án đúng: B

Câu 27: Khi đổi ZonedDateTime sang Instant cho DTO, điều gì phải được bảo toàn?
A. Cùng chuỗi giờ địa phương dù offset đã bị thay đổi
B. Cùng thời điểm thực tế, không chỉ cùng giờ hiển thị
C. Cùng tên múi giờ ban đầu dù phải đổi sang UTC
D. Cùng định dạng văn bản của object nguồn khi serialize
Đáp án đúng: B

Câu 28: Để build thất bại khi có field DTO chưa map, MapStruct cấu hình gì?
A. Đặt componentModel thành ReportingPolicy.ERROR
B. Đặt nullValueCheckStrategy thành ReportingPolicy.ERROR
C. Đặt unmappedTargetPolicy thành ReportingPolicy.ERROR
D. Đặt injectionStrategy thành ReportingPolicy.ERROR
Đáp án đúng: C
