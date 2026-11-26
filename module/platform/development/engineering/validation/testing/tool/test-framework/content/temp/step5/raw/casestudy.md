Đội Java chuyển từ JUnit 4 sang JUnit Jupiter, nhưng phương thức khởi tạo dữ liệu vẫn dùng annotation của JUnit 4; khi chạy với Jupiter, dữ liệu chưa được chuẩn bị và test thất bại trước assertion.
Một lớp JUnit Jupiter dùng @BeforeAll không phải static trong cấu hình vòng đời mặc định; nhóm chỉ thấy lỗi thiết lập lớp trên CI dù logic test của từng phương thức không thay đổi.
Nhóm cấu hình @TestInstance(PER_CLASS) để chia sẻ fixture tốn chi phí; một test sửa trường danh sách thành viên và test tiếp theo nhận lại dữ liệu đã bị thay đổi.
Ứng dụng ngân hàng có nhiều test tạo account trong @BeforeEach, nhưng phương thức cleanup thất bại khi test ném exception giữa chừng; bản ghi từ test lỗi xuất hiện trong lượt chạy sau.
Một kiểm thử JUnit sử dụng assertEquals trên hai đối tượng OrderDto không định nghĩa so sánh giá trị; các trường giống nhau nhưng assertion vẫn báo khác vì đang so sánh tham chiếu.
Nhóm kiểm tra danh sách giao dịch bằng cách chỉ so sánh kích thước hai collection; hệ thống trả nhầm giao dịch của khách hàng khác nhưng bài test vẫn PASS.
Trong kiểm thử tính tiền, kỹ sư dùng một assertion cho tổng, phí và giảm giá theo thứ tự; khi tổng sai, báo cáo không cho biết hai giá trị còn lại cũng sai trong cùng dữ liệu đầu vào.
Đội kiểm thử phương thức chuyển tiền kỳ vọng một ngoại lệ cụ thể khi số dư thiếu; code sửa lại bắt exception và trả giá trị mặc định nhưng test chỉ xác minh không bị crash.
Phương thức gửi email có tác dụng phụ ngoài và chạy bất đồng bộ; bài JUnit kết thúc trước khi nhiệm vụ hoàn thành nên các assertion về kết quả được kiểm tra quá sớm.
Một thuật toán tìm đường có yêu cầu giới hạn thời gian; bộ test dùng timeout quá ngắn trên laptop nhanh, khiến CI nhiều lúc thất bại khi máy chịu tải nặng.
Nhóm viết kiểm thử cho mã số nguyên từ 1 đến 100 bằng một vòng lặp duy nhất trong một @Test; khi trường hợp 73 sai, báo cáo chỉ ghi một test fail và không chỉ ra bộ dữ liệu nào tạo lỗi.
Trong JUnit Jupiter, nguồn dữ liệu @CsvSource chứa dấu phẩy trong tên sản phẩm; bộ dữ liệu bị chia thành nhiều tham số và ca test hỏng ở giai đoạn chuyển đối số.
Một lớp kiểm thử tham số có nguồn @MethodSource trả dữ liệu gồm null và chuỗi rỗng; các case bị xử lý giống nhau dù logic nghiệp vụ yêu cầu phân biệt giá trị không có và giá trị rỗng.
Nhóm dùng @ValueSource để thử các hạn mức thanh toán nhưng chỉ chọn giá trị thông thường; cùng test framework vẫn bỏ sót các số ngay dưới và trên mức cho phép.
Một bài @ParameterizedTest dùng tham số enum mới được bổ sung nhưng bộ @EnumSource chỉ liệt kê các giá trị cũ; nhóm nghĩ mọi trạng thái đã được kiểm tra vì phương thức test có tên bao quát.
Đội khai báo test với @RepeatedTest để phát hiện lỗi ngẫu nhiên, nhưng việc chạy lại trên cùng dữ liệu và thứ tự cố định khiến lỗi đồng thời chỉ xuất hiện ở production.
Ứng dụng xử lý file nhiều định dạng dùng @TestFactory tạo dynamic tests; một lỗi xảy ra trước khi danh sách dynamic test được sinh ra nên báo cáo không còn hiển thị các ca kiểm tra dự kiến.
Một nhóm tổ chức @Nested tests cho quy trình đặt hàng theo trạng thái; logic fixture lớp ngoài và lớp trong cùng thay đổi giỏ hàng khiến kết quả khó dự đoán với một số ca.
Dự án Java dùng JUnit assertions và một thư viện assertion fluent; quy tắc kiểm tra lỗi bị viết khác nhau giữa các lớp, khiến reviewer khó đọc thông điệp thất bại.
Trong kiểm thử truy cập API, một test bị bỏ qua qua assumption khi token test không có; pipeline vẫn báo xanh dù không chạy bất kỳ ca bảo mật nào trong môi trường vừa triển khai.
Nhóm tạm @Disabled một kiểm thử thanh toán do bên thứ ba lỗi; sau vài tháng không ai nhớ khi nào cần bật lại và pipeline xanh dù quy tắc quan trọng chưa được kiểm tra.
Đội gắn tag integration cho các ca có database, nhưng job Maven chỉ chọn tag unit; báo cáo release vẫn mô tả đã chạy toàn bộ regression dù integration suite bị loại.
Trong ứng dụng lớn, nhóm tạo JUnit extension để khởi tạo container cho các test cần database; extension tạo container riêng quá nhiều lần và làm suite tăng thời gian đáng kể.
Một extension JUnit tiêm tham số kết nối thử nghiệm cho test, nhưng hai bộ resolver đều nhận cùng kiểu tham số; test không chạy vì framework không quyết định được resolver phù hợp.
Nhóm dùng TestWatcher extension để ghi thông tin lỗi, nhưng test thất bại trong giai đoạn setup trước khi callback mong đợi có đủ dữ liệu; báo cáo CI thiếu ngữ cảnh quan trọng.
Trong một lớp JUnit, @BeforeEach đặt lại mock nhưng một phương thức helper tạo thêm mock riêng ở từng test; assertion tương tác với mock không trùng instance mà service thực sự sử dụng.
Ứng dụng tính lãi có test phụ thuộc vào ngày hiện tại; chạy sáng thứ Hai PASS và chạy cuối tháng FAIL, nhưng framework không cung cấp đồng hồ giả cho các ca đã viết.
Nhóm chuyển suite TestNG sang JUnit Jupiter; các phương thức trước đây phụ thuộc test khác chạy trước nên khi bỏ thứ tự chạy cố định, một số test bắt đầu từ trạng thái không hợp lệ.
Một bộ test TestNG dùng @DataProvider trả về cấu trúc nhiều cột; sau khi thêm trường dữ liệu mới, một số case bị lệch tham số và báo lỗi runtime thay vì kiểm tra nghiệp vụ.
Đội dùng TestNG groups để phân biệt smoke và regression, nhưng cấu hình suite XML bỏ nhóm regression ở pipeline release; ứng dụng lên production dù các ca đó chưa chạy.
Trong TestNG, một test khai báo phụ thuộc vào phương thức tạo đơn trước đó; khi test tạo đơn bị skip, hàng loạt test khác cũng skip dù có thể dùng fixture độc lập.
Nhóm bật thực thi song song cho các lớp JUnit Jupiter, trong khi tất cả test cùng dùng một file kết quả cố định; lần chạy này ghi đè file của lần chạy khác và assertion thất bại ngẫu nhiên.
Một suite TestNG xử lý dữ liệu đồng thời thông qua DataProvider chạy song song; các case sửa chung một Map cấu hình khiến kết quả thay đổi theo lịch của thread.
Đội kiểm thử sử dụng @TestMethodOrder để cố định thứ tự các bước nghiệp vụ trong một lớp; khi chạy riêng test thứ ba từ IDE, dữ liệu phụ thuộc các bước đầu không tồn tại.
Trong Maven, các test JUnit Jupiter được biên dịch nhưng Surefire không chạy chúng vì thiếu engine hoặc cấu hình phù hợp; bản báo cáo hiển thị không có test nào trong khi build vẫn thành công.
Dự án Gradle có test class dùng TestNG và test class dùng JUnit Jupiter; cấu hình test task chỉ bật một engine nên một phần suite không được thực thi dù cả hai vẫn biên dịch được.
Đội đổi quy ước tên lớp test từ hậu tố Test sang Spec, nhưng cấu hình chọn test của build tool vẫn theo mẫu cũ; CI chạy số lượng test thấp hơn mà không có lỗi compile.
Trong pipeline nhiều module Maven, test unit chạy ở module dịch vụ còn test tích hợp nằm trong module riêng; lệnh CI chỉ chọn module thay đổi nên phần test phụ thuộc giữa module không được chạy.
Nhóm xuất kết quả kiểm thử dạng XML cho hệ thống CI, nhưng nhiều lần chạy song song ghi đè file cùng tên; dashboard báo thiếu ca thất bại mặc dù log console có thông tin đầy đủ.
Một lớp kiểm thử có tên phương thức và thông điệp assertion quá chung chung; khi CI báo lỗi ở bộ dữ liệu thứ 19, người trực sự cố không xác định được chức năng hay điều kiện nghiệp vụ cần kiểm tra.
