Câu 1: Composite Pattern giải quyết nhu cầu biểu diễn đối tượng nào?
A. Cấu trúc cây phần–toàn thể với API chung
B. Thay đổi thuật toán theo cấu hình của client
C. Dịch API cũ thành giao diện tương thích
D. Tách hai hệ phân cấp có biến thể độc lập
Đáp án đúng: A

Câu 2: Trong Composite, Component có vai trò quan trọng nào?
A. Giữ mọi thuật toán lưu dữ liệu trong repository
B. Quản lý riêng bộ nhớ của tất cả nút con
C. Hợp đồng chung cho Leaf và Composite
D. Chọn implementation phụ thuộc vào hệ điều hành
Đáp án đúng: C

Câu 3: Leaf trong Composite thường có đặc điểm gì?
A. Luôn điều phối nhiều Component theo trình tự
B. Xử lý tác vụ nhưng không quản lý children
C. Chỉ lưu danh sách con và không có hành vi
D. Luôn kế thừa trực tiếp từ concrete Composite
Đáp án đúng: B

Câu 4: Composite thường lưu thành phần con ở dạng nào?
A. Danh sách chỉ chứa một concrete Leaf riêng
B. Con trỏ tới singleton điều phối toàn hệ thống
C. Danh sách Component qua một interface chung
D. Bộ chọn thuật toán chỉ có đúng một implementation
Đáp án đúng: C

Câu 5: Khi client gọi operation() trên Composite, hành vi thường là gì?
A. Tự thay đổi mọi Leaf thành một kiểu mới
B. Bỏ qua toàn bộ node con để xử lý như Leaf
C. Thay interface Component bằng API nội bộ
D. Gọi các node con để phối hợp kết quả
Đáp án đúng: D

Câu 6: Trong cây menu, nút MenuGroup thường là thành phần nào?
A. Leaf chỉ thực hiện một command khi được chọn
B. Composite chứa các MenuItem và MenuGroup khác
C. Adapter chuyển dữ liệu menu từ thư viện ngoài
D. Strategy chọn giao diện điều hướng theo locale
Đáp án đúng: B

Câu 7: Trong cây menu, MenuItem thực hiện một hành động đơn lẻ là loại gì?
A. Leaf có hành động nhưng không chứa nút con
B. Composite luôn lưu ít nhất hai mục menu con
C. Decorator thay đổi giao diện cho cả menu
D. Factory Method khởi tạo toàn bộ cây menu
Đáp án đúng: A

Câu 8: Lợi ích của việc client chỉ biết Component là gì?
A. Buộc client nhận biết mọi loại concrete subclass
B. Cho phép client sửa trực tiếp collection con nội bộ
C. Thao tác thống nhất với node đơn và nhóm node
D. Loại bỏ mọi nhu cầu xử lý kết quả từ operation
Đáp án đúng: C

Câu 9: Trong Java, cách khai báo Component linh hoạt thường là gì?
A. Enum chứa mọi concrete node của cây
B. Class final chỉ dành cho một loại Leaf
C. Annotation gắn với từng phương thức thêm con
D. Interface với các thao tác có ý nghĩa chung
Đáp án đúng: D

Câu 10: Trong biến thể Composite an toàn, phương thức addChild thường đặt ở đâu?
A. Ở Component để mọi Leaf bắt buộc cài đặt add
B. Ở Composite để Leaf khỏi cài thao tác con
C. Trong mọi Leaf để tự chuyển thành Composite
D. Trong client để sửa thẳng danh sách con
Đáp án đúng: B

Câu 11: Trong biến thể Composite minh bạch, bất lợi khi đặt addChild ở Component là gì?
A. Client không còn gọi operation() được trên Composite
B. Mọi node đều bắt buộc chứa children thật
C. Leaf phải xử lý thao tác không phù hợp với mình
D. Composite không thể định nghĩa interface riêng
Đáp án đúng: C

Câu 12: Nếu Leaf không hỗ trợ addChild kế thừa từ Component, phương án nào có thể dùng?
A. Tự tạo node giả rồi gắn vào mọi Leaf
B. Trả thành công nhưng bỏ qua việc thêm con
C. Ném UnsupportedOperationException nếu không hỗ trợ
D. Đổi Leaf thành Composite mà không thông báo
Đáp án đúng: C

Câu 13: Với thư mục có các file dung lượng 3 MB và 5 MB, tổng size dạng Composite là bao nhiêu?
A. 5 MB vì Composite chỉ dùng child lớn nhất
B. 8 MB, là tổng dung lượng hai file con
C. 3 MB vì Composite chỉ dùng child đầu tiên
D. 15 MB vì tính cả số lượng node trong cây
Đáp án đúng: B

Câu 14: Trong Composite, nhóm không có phần tử con nên trả gì khi tính tổng size?
A. Giá trị null để biểu thị không có node con
B. Dung lượng của node cha gần nhất trong cây
C. Số âm để báo hiệu cấu trúc cây bị lỗi
D. Trả 0, phần tử trung hòa của phép cộng
Đáp án đúng: D

Câu 15: Khi duyệt cây theo pre-order, thứ tự xử lý được xác định thế nào?
A. Xử lý tất cả lá rồi mới tới node cha
B. Xử lý con trái rồi cha rồi con phải bắt buộc
C. Duyệt node cha rồi tiếp tục qua các node con
D. Xử lý từng mức nhưng không đi sâu nhánh
Đáp án đúng: C

Câu 16: Khi duyệt Composite rất sâu bằng đệ quy, rủi ro Java nào cần cân nhắc?
A. Mọi Leaf tự chuyển thành singleton toàn cục
B. Java luôn tạo thread mới cho mỗi node con
C. Trình biên dịch tự loại bỏ mọi node có size bằng 0
D. Tràn stack khi độ sâu vượt khả năng ngăn xếp
Đáp án đúng: D

Câu 17: Nếu muốn tránh đệ quy khi duyệt cây rất sâu, cách nào phù hợp?
A. Dùng stack hoặc queue để duyệt không đệ quy
B. Tạo thêm superclass cho từng mức của cây
C. Chuyển mọi Component thành String trước khi duyệt
D. Gọi operation() hai lần ở mỗi node rồi dừng
Đáp án đúng: A

Câu 18: Nếu vô tình thêm một node làm con của chính nó, hậu quả có thể là gì?
A. Cây tự nhân đôi các node rồi vẫn luôn hợp lệ
B. Java tự phát hiện chu trình trong List<Component>
C. Component tự chuyển chu trình thành một Leaf
D. Tạo chu trình khiến việc duyệt không kết thúc
Đáp án đúng: D

Câu 19: Khi thiết kế Composite bắt buộc là cây, điều kiện nào cần được kiểm tra khi add?
A. Chặn chu trình và giữ chính sách liên kết cha-con
B. Mọi Leaf đều phải chứa một danh sách con rỗng
C. Tên node con buộc phải bằng tên Composite cha
D. Mọi Composite chỉ được có chính xác hai con
Đáp án đúng: A

Câu 20: Khi di chuyển một node sang Composite khác, chính sách nào giữ tính nhất quán?
A. Gỡ liên kết cha cũ trước khi gắn cha mới
B. Giữ đồng thời hai cha dù cấu trúc yêu cầu cây
C. Chỉ đổi tên node mà không sửa danh sách con
D. Tạo vòng tham chiếu giữa hai nút cha
Đáp án đúng: A

Câu 21: Khi operation() cần tính tổng qua nhiều node con, cách xử lý lỗi nào hợp lý?
A. Bỏ qua mọi exception dù dữ liệu tổng bị sai
B. Luôn đổi exception thành kết quả 0 rồi tiếp tục
C. Mỗi Leaf tự thoát JVM khi phát hiện lỗi
D. Chọn fail-fast hay tổng hợp lỗi theo hợp đồng
Đáp án đúng: D

Câu 22: Khi cache tổng size ở Composite, trường hợp nào bắt buộc làm mới cache?
A. Khi client gọi hasNext của một Iterator độc lập
B. Khi thêm, xóa hoặc cập nhật size của node con
C. Khi đổi tên một class Java không chạy lại build
D. Khi đọc lại cùng giá trị cache không có thay đổi
Đáp án đúng: B

Câu 23: Nếu nhiều thread cùng sửa children của Composite, điều gì cần cân nhắc?
A. Đồng bộ truy cập hoặc dùng snapshot khi duyệt
B. List<Component> mặc định an toàn cho mọi thread
C. Duyệt đệ quy sẽ tự khóa danh sách children
D. Mỗi Leaf tự kiểm soát mọi sửa đổi của node cha
Đáp án đúng: A

Câu 24: Composite khác Decorator ở mục tiêu cốt lõi nào?
A. Composite bọc một object; Decorator quản lý nhiều con
B. Composite chuyển interface; Decorator chọn thuật toán
C. Composite tạo instance; Decorator điều phối request
D. Composite quản lý cây; Decorator bọc thêm hành vi
Đáp án đúng: D

Câu 25: Composite và Iterator có thể phối hợp như thế nào?
A. Iterator bắt buộc thay thế interface Component
B. Iterator che giấu cách đi qua các node trong cây
C. Composite buộc client truy cập mảng children trực tiếp
D. Iterator khiến cây không còn có nút Composite
Đáp án đúng: B

Câu 26: Trong UI, khi cần disable toàn bộ nhóm điều khiển, Composite giúp gì?
A. Gọi từng widget bằng tên class concrete đã biết
B. Gọi disable trên nhóm để tác động tới các node con
C. Chỉ disable widget đầu tiên được tạo trong nhóm
D. Chuyển tất cả widget thành một đối tượng Leaf
Đáp án đúng: B

Câu 27: Bộ test tính tổng ở Composite nên có những ca nào?
A. Test nhóm rỗng, một lá, lồng nhau và cập nhật
B. Chỉ một Leaf không có quan hệ với node khác
C. Chỉ trường hợp tất cả node đều có cùng tên
D. Chỉ xem số lượng class implements Component
Đáp án đúng: A

Câu 28: Khi số lượng thao tác khác nhau trên cây tăng mạnh, lựa chọn nào đáng cân nhắc?
A. Thêm mọi thao tác trực tiếp vào một Leaf duy nhất
B. Cho client sửa children qua public mutable field
C. Dùng Visitor khi cấu trúc node ít thay đổi
D. Bỏ interface Component và dùng reflection
Đáp án đúng: C
