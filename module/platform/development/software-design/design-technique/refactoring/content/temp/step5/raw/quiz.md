Refactoring hướng đến mục tiêu nào?
A. Tăng tính năng và đồng thời đổi hành vi công khai
B. Tối ưu tốc độ trước khi xác định yêu cầu hiện tại
C. Chuẩn hóa thư viện bất kể ảnh hưởng đến client
D. Cải thiện nội bộ mà giữ hành vi quan sát được
Đáp án đúng: D

Tình huống nào gợi ý dùng Extract Method?
A. Nhiều lớp cùng implement một interface ổn định
B. Khối lệnh thể hiện một bước xử lý độc lập
C. Hàm có nhiều nơi gọi nhưng vẫn dễ đọc hiểu
D. Constructor chứa các dependency bắt buộc
Đáp án đúng: B

Tên method sau Extract Method nên ưu tiên điều gì?
A. Giữ tên các biến tạm bên trong đoạn code cũ
B. Liệt kê thứ tự từng lệnh được dùng trong thân hàm
C. Sử dụng tên tổng quát để hạn chế việc đổi tên
D. Diễn đạt ý định của bước xử lý được tách
Đáp án đúng: D

Mã legacy thiếu test nên được bảo vệ thế nào trước refactor?
A. Viết test ghi nhận hành vi ở nhánh quan trọng
B. Thay mô hình dữ liệu rồi tạo test theo mã mới
C. Xóa các nhánh lỗi để đơn giản hóa phần cần kiểm
D. Đổi API công khai rồi dùng test mới xác nhận
Đáp án đúng: A

Logic giống nhau ở ba nơi nên xử lý thế nào?
A. Xác minh cùng ngữ nghĩa rồi mới trích xuất
B. Gộp luôn các lớp dù phục vụ nghiệp vụ khác
C. Sao chép đoạn code sang thư viện dùng chung
D. Đưa toàn bộ module vào chung một package util
Đáp án đúng: A

Khi nào Move Method là lựa chọn có cơ sở?
A. Method chỉ gọi helper riêng và giữ ngữ nghĩa rõ
B. Method có nhiều unit test với độ bao phủ cao
C. Method chủ yếu thao tác dữ liệu của lớp khác
D. Method đã được đặt tên nhất quán trong dự án
Đáp án đúng: C

Nhiều tham số thường đi cùng nhau gợi ý kỹ thuật gì?
A. Inline Variable để xóa toàn bộ tham số hiện tại
B. Extract Interface cho mỗi kiểu dữ liệu tham số
C. Introduce Parameter Object cho nhóm liên quan
D. Replace Constructor bằng shared mutable global
Đáp án đúng: C

Một lớp vừa tính phí, gửi mail và truy vấn DB gợi ý gì?
A. Large Class đang trộn nhiều trách nhiệm
B. Lazy Class có quá ít hành vi đáng duy trì
C. Data Class chứa dữ liệu mà thiếu hành vi
D. Middle Man chủ yếu chuyển tiếp lời gọi
Đáp án đúng: A

Khi nào Inline Method có thể tăng độ rõ ràng?
A. Method chứa logic phức tạp và nhiều nhánh
B. Method được kế thừa bởi nhiều lớp khác
C. Method là điểm mở rộng công khai đã ổn định
D. Method trung gian không bổ sung ý nghĩa
Đáp án đúng: D

Vì sao nên thay số khó hiểu bằng hằng số có tên?
A. Bắt buộc JVM tối ưu mọi phép tính số học
B. Bảo đảm dữ liệu từ người dùng luôn hợp lệ
C. Khiến mỗi lần gọi tạo một giá trị mới
D. Diễn đạt rõ ý nghĩa của quy tắc kiểm tra
Đáp án đúng: D

Nhiều nhánh xử lý theo loại object lặp khắp nơi gợi ý gì?
A. Gộp mọi switch thành một static method lớn
B. Đưa tất cả điều kiện sang một lớp util chung
C. Cân nhắc thay điều kiện bằng đa hình
D. Đổi switch sang chuỗi toán tử ternary lồng
Đáp án đúng: C

Abstraction làm trước khi có nhu cầu thực thường là mùi gì?
A. Feature Envy do một hàm truy cập lớp ngoài
B. Primitive Obsession do nhiều kiểu nguyên thủy
C. Shotgun Surgery do sửa một chỗ lan nhiều lớp
D. Speculative Generality khiến thiết kế dư thừa
Đáp án đúng: D

Lợi ích chính của refactor từng bước nhỏ là gì?
A. Compiler tự tìm đủ mọi lỗi quy tắc nghiệp vụ
B. Khoanh vùng nhanh sai lệch hành vi phát sinh
C. Không còn cần người khác review thay đổi
D. Có thể đổi hợp đồng API mà không sửa client
Đáp án đúng: B

Khi baseline test đang đỏ trước refactor, nên làm gì?
A. Tìm nguyên nhân và lập baseline tin cậy
B. Sửa cấu trúc tiếp vì test cũ thường chưa chuẩn
C. Xóa assertion không khớp để suite luôn xanh
D. Đợi hoàn tất refactor rồi mới chạy lại test
Đáp án đúng: A

Điểm khác biệt chính giữa refactor và thêm tính năng là gì?
A. Refactor không chủ đích đổi hành vi ngoài
B. Refactor luôn tạo một quy tắc nghiệp vụ mới
C. Viết tính năng mới chỉ được đổi tên biến
D. Viết tính năng mới không cần test tự động
Đáp án đúng: A

Sau Rename Method bằng IDE, việc gì vẫn quan trọng?
A. Chỉ kiểm tra file chứa method được đổi tên
B. Chạy test và kiểm lại hợp đồng nơi gọi
C. Tin rằng mọi chuỗi cấu hình đã được cập nhật
D. Xóa test cũ vì method hiện có tên mới
Đáp án đúng: B

Thay đổi giúp code nhanh hơn nhưng cho kết quả khác được xem là gì?
A. Refactor hợp lệ nhờ đã tăng hiệu năng xử lý
B. Extract Method hợp lệ nếu không có exception
C. Thay đổi hành vi, không còn là refactor thuần
D. Rename Variable vì chỉ khác cách tính nội bộ
Đáp án đúng: C

Cách chia commit nào giúp review refactor hiệu quả?
A. Gộp mọi chỉnh sửa thành một commit thật lớn
B. Chỉ commit sau khi thay toàn bộ tầng lưu trữ
C. Tách thay đổi cấu trúc khỏi tính năng mới
D. Giữ cả code lỗi trong commit cho dễ so sánh
Đáp án đúng: C

Class trực tiếp tạo quá nhiều dependency bằng new gợi ý gì?
A. Tiêm dependency qua ranh giới rõ ràng
B. Chuyển dependency thành biến static dùng chung
C. Đưa mọi constructor vào một superclass chung
D. Đổi tên class phụ thuộc cho ngắn và dễ đọc
Đáp án đúng: A

Chuỗi điều kiện lỗi lồng sâu có thể được cải thiện bằng gì?
A. Gộp điều kiện thành một chuỗi ternary dài
B. Dùng guard clause cho nhánh thoát sớm
C. Lưu mọi kết quả kiểm tra vào static field
D. Đưa mọi câu lệnh điều kiện sang finally
Đáp án đúng: B

Field street, city và postalCode thường đi cùng nhau gợi ý gì?
A. Middle Man nên thêm lớp chuyển tiếp lời gọi
B. Data Clumps nên gom thành value object
C. Temporary Field cần xóa mọi trường dữ liệu
D. Divergent Change cần nhập các service với nhau
Đáp án đúng: B

Trước khi xóa dead code, cần xác minh gì?
A. Khối code ít dòng hơn giới hạn coding style
B. Method trùng tên với một method khác trong lớp
C. Code nằm ngoài package được chạy unit test
D. Không có đường dùng hợp lệ và test vẫn xanh
Đáp án đúng: D

Hai đoạn code giống nhau nhưng mang ý nghĩa khác nên làm gì?
A. Luôn gộp ngay vì cú pháp giống nhau là đủ
B. Xác nhận ngữ nghĩa trước khi quyết định gộp
C. Đưa vào superclass mà không cần xem context
D. Xóa đoạn thứ hai và gọi thẳng đoạn thứ nhất
Đáp án đúng: B

Một thay đổi nhỏ khiến sửa nhiều lớp rải rác là mùi gì?
A. Data Clumps với các tham số hay đi cùng
B. Lazy Class có số method quá ít so với lớp
C. Long Method chứa một khối xử lý phức tạp
D. Shotgun Surgery với trách nhiệm bị phân tán
Đáp án đúng: D

Đổi API nội bộ đang được nhiều module sử dụng nên tiến hành thế nào?
A. Xóa đường cũ ngay và xử lý lỗi ở production
B. Thêm đường mới rồi chuyển dần các nơi gọi
C. Tạo hai API khác nhau mà không mô tả nghĩa
D. Chuyển toàn bộ client sang dùng reflection
Đáp án đúng: B

Khi nào characterization test đặc biệt có giá trị?
A. Mọi tính năng đã có acceptance test ổn định
B. Hành vi legacy quan trọng nhưng thiếu đặc tả
C. Chỉ cần kiểm tra format và style của mã
D. Cần chứng minh tốc độ CPU cao hơn bản cũ
Đáp án đúng: B

Khi nào Replace Inheritance with Delegation phù hợp?
A. Lớp con thỏa mọi điều kiện thay thế lớp cha
B. Superclass biểu diễn abstraction rất ổn định
C. Các lớp con có cùng bất biến nghiệp vụ
D. Quan hệ is-a sai, chỉ muốn tái dùng hành vi
Đáp án đúng: D

Chuyển một field sang lớp khác nên dựa vào điều gì?
A. Đặt gần hành vi sở hữu và bất biến liên quan
B. Ưu tiên lớp đang chứa nhiều field nhất
C. Chuyển sang global util để mọi nơi cùng dùng
D. Ưu tiên package có ít import hơn các package
Đáp án đúng: A

Test kiểm tra số lời gọi nội bộ quá chặt có vấn đề gì?
A. Luôn phát hiện được tất cả sai lệch nghiệp vụ
B. Đo được chính xác thời gian CPU cho mỗi call
C. Dễ vỡ dù hành vi bên ngoài vẫn giữ nguyên
D. Tự bảo đảm hợp đồng API khi refactor
Đáp án đúng: C

Trong Extract Class, nguyên tắc chia nào cải thiện cohesion?
A. Dồn toàn bộ method public vào một lớp lớn
B. Gom dữ liệu với hành vi của cùng trách nhiệm
C. Chia đều tổng số dòng cho những lớp mới
D. Đưa mọi field vào lớp chỉ có getter setter
Đáp án đúng: B

Vì sao test flaky gây khó khăn khi refactor?
A. Khó phân biệt regression với thất bại ngẫu nhiên
B. Mọi refactor đều khiến flaky test chạy xanh
C. Flaky test luôn là lỗi từ code sản phẩm
D. Flaky test có thể thay thế review trên CI
Đáp án đúng: A

Refactor logic tính tiền cần bảo vệ điều gì?
A. Ca biên và bất biến của kết quả nghiệp vụ
B. Chỉ cần mã biên dịch bằng compiler Java
C. Chỉ cần số dòng sau refactor giảm đi
D. Chỉ cần kích thước tệp class không tăng
Đáp án đúng: A

Method thường xuyên lấy dữ liệu của object khác để tính toán có thể là gì?
A. Primitive Obsession vì quá nhiều kiểu dữ liệu
B. Data Clumps vì các biến trùng kiểu cơ bản
C. Feature Envy với hành vi đặt sai chủ sở hữu
D. Speculative Generality vì ít tham số đầu vào
Đáp án đúng: C

Đổi exception nghiệp vụ thành RuntimeException chung gây nguy cơ gì?
A. Chỉ đổi chi tiết triển khai nên luôn an toàn
B. Làm thay đổi hợp đồng lỗi mà client quan sát
C. Chỉ thay tên biến nên có thể bỏ chạy test
D. Chỉ đổi bố cục dòng mã, không ảnh hưởng API
Đáp án đúng: B

Khi chỉ có hai nhánh đơn giản ổn định, nên dùng State Pattern ngay không?
A. Luôn cần mỗi nhánh một lớp State độc lập
B. Đổi tất cả điều kiện thành callback không tên
C. Cân nhắc chi phí abstraction so với lợi ích
D. Đưa boolean trạng thái vào static shared field
Đáp án đúng: C

Refactor method có side effect cần test điều gì?
A. Chỉ kiểu dữ liệu trả về của method sau sửa
B. Chỉ thời gian chạy dưới số luồng lớn
C. Cả kết quả và thay đổi trạng thái liên quan
D. Chỉ số lượng dòng log in ra console
Đáp án đúng: C

Để tránh phá API được nhiều client dùng, nên làm gì?
A. Xác định hợp đồng và kiểm tra tính tương thích
B. Đổi tên mọi endpoint trước khi kiểm thử
C. Tắt kiểm tra compatibility trong pipeline
D. Chỉ chạy test helper mới được trích xuất
Đáp án đúng: A

Mã ngắn hơn nhưng khó hiểu hơn nên được đánh giá thế nào?
A. Chấp nhận ngay vì ít dòng ít khả năng lỗi
B. Chỉ dựa trên số class đã xóa khỏi dự án
C. Chọn cách có thời gian biên dịch ngắn hơn
D. Ưu tiên khả năng hiểu, không chỉ số dòng
Đáp án đúng: D

Cách giảm coupling sau refactor logic dùng chung là gì?
A. Dùng một utility toàn cục chứa mọi trạng thái
B. Cho module truy cập trực tiếp field của nhau
C. Đặt abstraction nhỏ tại ranh giới sở hữu rõ
D. Tạo một class nắm mọi quy tắc nghiệp vụ
Đáp án đúng: C

Dấu hiệu nào cho thấy cần dừng refactor để thêm test?
A. Đã đổi tên nhiều local variable trong lớp
B. Số dòng giảm nhưng build vẫn lâu như trước
C. IDE có thể rename toàn bộ package tự động
D. Chưa xác định hành vi đúng ở nhánh quan trọng
Đáp án đúng: D
