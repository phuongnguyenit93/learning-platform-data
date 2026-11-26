Câu 1. Mục đích cốt lõi của Abstract Factory là gì?
A. Tạo một đối tượng phức tạp theo từng bước cấu hình
B. Sao chép đối tượng từ instance mẫu có sẵn
C. Chỉ định class cụ thể bằng chuỗi tên lúc runtime
D. Tạo họ sản phẩm liên quan qua các interface chung
Đáp án đúng: D

Câu 2. Một hệ UI hỗ trợ Light/Dark với Button và Checkbox; interface AbstractFactory nên khai báo gì?
A. Các phép tạo Button và Checkbox theo hợp đồng
B. Một method render() trực tiếp vẽ toàn bộ giao diện
C. Một class LightButton chứa mọi thành phần UI
D. Hai constructor cụ thể cho từng màn hình của app
Đáp án đúng: A

Câu 3. Một DarkFactory cần cung cấp Button và Checkbox; triển khai nào giữ tính nhất quán họ sản phẩm?
A. DarkButton kết hợp LightCheckbox trong cùng factory
B. DarkButton và DarkCheckbox cùng biến thể giao diện
C. LightButton và DarkCheckbox trộn theo từng request
D. Chỉ trả Button, còn Checkbox do client tự tạo
Đáp án đúng: B

Câu 4. Vì sao nên cấp một ConcreteFactory phù hợp khi tạo nhiều widget cùng chủ đề?
A. Giữ các widget trong cùng họ để tương thích
B. Để bỏ hẳn nhu cầu dùng product interface
C. Để mỗi widget có thể tự khởi tạo toàn bộ UI
D. Để cho client biết tên class của mọi sản phẩm
Đáp án đúng: A

Câu 5. Code client dùng AbstractFactory tốt thường phụ thuộc vào điều gì?
A. Tên các concrete factory trong các nhánh if dài
B. Chi tiết constructor của từng concrete product
C. Factory interface và product interface chung
D. Thứ tự khởi tạo global singleton của mọi class
Đáp án đúng: C

Câu 6. Muốn thêm họ giao diện HighContrast, điều gì thường cần được bổ sung?
A. Sửa mọi client để gọi trực tiếp HighContrastButton
B. Loại bỏ contract của tất cả product hiện hữu
C. Thay interface Button bằng class cụ thể HighContrast
D. Các concrete product và factory của họ mới
Đáp án đúng: D

Câu 7. Thêm loại sản phẩm Slider vào AbstractFactory hiện tại tạo đánh đổi nào?
A. Chỉ cần thêm Slider vào một factory đã chọn
B. Phải mở rộng factory contract và các họ triển khai
C. Không ảnh hưởng mọi factory vì Slider luôn độc lập
D. Bắt buộc chuyển toàn bộ ứng dụng sang Factory Method
Đáp án đúng: B

Câu 8. So với Factory Method, Abstract Factory đặc trưng bởi điểm nào?
A. Chỉ hỗ trợ tạo đúng một đối tượng mỗi lần gọi
B. Luôn yêu cầu sử dụng static method và enum
C. Tạo một họ gồm nhiều loại product liên quan
D. Không sử dụng polymorphism ở bất kỳ bước nào
Đáp án đúng: C

Câu 9. Một ứng dụng chọn giao diện theo hệ điều hành ngay khi khởi động. Cách dùng factory hợp lý?
A. Tạo lại mọi concrete factory bên trong từng Button
B. Chọn factory theo cấu hình rồi tiêm vào client
C. Đặt switch theo OS vào mỗi product interface
D. Cho các component tự tra tên hệ điều hành liên tục
Đáp án đúng: B

Câu 10. Một client tạo Button từ WinFactory và Checkbox từ MacFactory; nguy cơ chính là gì?
A. Factory interface sẽ không thể được biên dịch
B. Mọi button được Java tự chuyển thành MacButton
C. Các sản phẩm sẽ luôn chia sẻ cùng state nội bộ
D. Widget từ hai họ có thể không tương thích
Đáp án đúng: D

Câu 11. Khi dùng dependency injection, lợi ích nào đến từ việc inject AbstractFactory?
A. Dễ thay họ sản phẩm mà không sửa mã client
B. Mọi concrete product sẽ tự động trở thành singleton
C. Factory không còn phải kiểm tra điều kiện đầu vào
D. Số lượng sản phẩm cần tạo được xác định lúc compile
Đáp án đúng: A

Câu 12. Muốn unit test client mà không dùng các widget UI thật, cách nào phù hợp?
A. Dùng một static factory chỉ trả widget production
B. Thay product interfaces bằng các lớp Java final
C. Dùng reflection để bỏ qua mọi lời gọi tạo widget
D. Tiêm fake factory để nhận test products
Đáp án đúng: D

Câu 13. Đâu là trách nhiệm phù hợp của ConcreteFactory trong thiết kế này?
A. Quyết định toàn bộ chính sách nghiệp vụ của hệ thống
B. Gọi trực tiếp mọi controller dùng các sản phẩm của họ
C. Tạo các concrete product thuộc một họ xác định
D. Duy trì database transaction cho tất cả product
Đáp án đúng: C

Câu 14. Vì sao các product interface quan trọng trong Abstract Factory?
A. Client dùng hợp đồng thay vì class sản phẩm cụ thể
B. Buộc mọi sản phẩm phải thừa kế một class duy nhất
C. Cho phép đổi tên method mỗi khi chuyển họ sản phẩm
D. Để mọi product tự quyết định factory nào tạo chúng
Đáp án đúng: A

Câu 15. Nếu method createButton() khai báo trả WinButton thay vì Button, hệ quả thiết kế nào xuất hiện?
A. Mọi factory đều có thể trả các class cùng interface
B. Client bị gắn chặt hơn vào một biến thể sản phẩm
C. Factory có thể thay đổi họ hoàn toàn không cần sửa
D. Sự tương thích giữa các product được bảo đảm hơn
Đáp án đúng: B

Câu 16. Component cần cả TextField và Button; thiết kế nào giảm phụ thuộc concrete classes?
A. Tạo trực tiếp new MacButton() trong component
B. Dùng if để kiểm tra tên class của từng product
C. Tiêm factory và tạo product qua các interface
D. Đưa mọi constructor cụ thể vào một global helper
Đáp án đúng: C

Câu 17. Abstract Factory có thể khiến số class tăng nhanh nhất khi nào?
A. Chỉ có một loại sản phẩm và một biến thể
B. Mọi sản phẩm được chia sẻ một implementation chung
C. Ứng dụng không cần chọn biến thể khi chạy
D. Có nhiều họ, mỗi họ có nhiều loại product riêng
Đáp án đúng: D

Câu 18. Ví dụ nào cho thấy Abstract Factory hợp lý hơn một constructor thông thường?
A. Ứng dụng chỉ tạo một số nguyên từ chuỗi input
B. Ứng dụng cần bộ UI tương thích cho từng hệ điều hành
C. Ứng dụng chỉ cần copy một đối tượng bất biến đơn giản
D. Ứng dụng chỉ tạo một file trống với tên cố định
Đáp án đúng: B

Câu 19. Abstract Factory giúp áp dụng Dependency Inversion ở điểm nào?
A. Phần điều phối phụ thuộc factory/product abstractions
B. Các interface luôn phụ thuộc vào implementation chi tiết
C. Concrete product được phép sửa hợp đồng tùy request
D. Mọi client chỉ được dùng một singleton factory toàn cục
Đáp án đúng: A

Câu 20. Một ConcreteFactory giữ bộ đếm tạo product dùng chung giữa nhiều thread; điều gì phải được cân nhắc?
A. Mọi factory luôn được JVM đồng bộ hóa tự động
B. State dùng chung có thể cần đồng bộ hoặc bỏ đi
C. Việc tạo product luôn thực hiện tuần tự trong Java
D. Chỉ lớp product mới được phép có trạng thái mutable
Đáp án đúng: B

Câu 21. Nếu cấu hình mới chỉ đổi màu nhưng mọi widget dùng chung hành vi, thiết kế nào giảm bùng nổ lớp?
A. Luôn tạo một factory class cho mỗi mã màu
B. Tách một product interface mới cho từng theme
C. Dùng style cấu hình thay vì nhân thêm class
D. Đặt màu được chọn vào logic xử lý nghiệp vụ
Đáp án đúng: C

Câu 22. Khi hai loại sản phẩm không cần đồng bộ theo họ, Abstract Factory có thể gây chi phí gì?
A. Giúp tăng khả năng kết hợp tùy ý không cần cấu hình
B. Tự động giảm mọi interface trong ứng dụng
C. Buộc thêm constructor cho cả các đối tượng không liên quan
D. Ràng buộc các biến thể không cần thiết vào một họ
Đáp án đúng: D

Câu 23. Ứng dụng phục vụ đồng thời Light và Dark theo từng request; cách cấp factory nào phù hợp?
A. Tiêm factory theo request, tránh global mutable
B. Ghi đè static factory toàn cục ở mỗi request
C. Sửa các constructor product trong runtime để đổi theme
D. Tạo một factory duy nhất và cố định toàn hệ thống
Đáp án đúng: A

Câu 24. Khi thêm một ConcreteFactory mới, test nào kiểm tra tốt hợp đồng họ sản phẩm?
A. Chỉ xác minh class mới có tên kết thúc bằng Factory
B. Chỉ đo kích thước JAR tăng sau khi thêm factory
C. Chạy bộ contract test cho từng product của họ mới
D. Chỉ gọi constructor factory và không tạo sản phẩm
Đáp án đúng: C
