1. Mục đích chính của mẫu Builder khi tạo đối tượng phức tạp là gì?
A. Dùng một hàm tĩnh để che toàn bộ lớp sản phẩm cụ thể
B. Tách quy trình tạo khỏi biểu diễn của đối tượng
C. Chia sẻ duy nhất một instance sản phẩm ở mọi request
D. Sao chép đối tượng mẫu để tránh truyền tham số dài
Đáp án đúng: B

2. Builder thường giúp khắc phục vấn đề nào của nhiều constructor quá tải?
A. Khó đọc ý nghĩa khi truyền nhiều tham số tùy chọn
B. Khó tạo đa hình khi mỗi subclass override factory
C. Khó sao chép cấu trúc đối tượng có tham chiếu lồng nhau
D. Khó chia sẻ trạng thái duy nhất giữa nhiều luồng chạy
Đáp án đúng: A

3. Trong ví dụ Java `new Report.Builder().title("Q1").build()`, `build()` thường làm gì?
A. Trả đối tượng `Builder` để thiết lập lại các giá trị
B. Tự tìm subclass phù hợp theo factory method ảo
C. Sao chép toàn bộ cấu hình builder sang một registry
D. Hoàn tất kiểm tra và trả một `Report` đã xây dựng
Đáp án đúng: D

4. Vì sao các phương thức `title(...)`, `pages(...)` thường trả về builder?
A. Cho phép gọi nối tiếp các bước cấu hình cùng một đối tượng
B. Buộc tạo một builder mới sau mỗi lần gán thuộc tính
C. Giữ trạng thái của sản phẩm không thể thay đổi sau build
D. Bảo đảm tự động đồng bộ mọi thao tác giữa nhiều thread
Đáp án đúng: A

5. Với sản phẩm có trường bắt buộc, kiểm tra nào phù hợp trong `build()`?
A. Tự điền giá trị rỗng cho mọi tham số bắt buộc chưa có
B. Bỏ qua kiểm tra vì setter của builder đã chạy trước
C. Từ chối tạo đối tượng khi thiếu trường hoặc sai invariant
D. Để lớp controller sửa lại sản phẩm sau khi đã trả về
Đáp án đúng: C

6. Điểm khác biệt phổ biến giữa Builder và Factory Method là gì?
A. Builder chọn subclass trong override; Factory dùng nhiều bước
B. Builder buộc là singleton; Factory Method dùng registry
C. Builder sao chép prototype; Factory Method đổi trạng thái cũ
D. Builder cấu hình từng bước; Factory Method chọn cách tạo
Đáp án đúng: D

7. Trong biến thể GoF Builder, Director có vai trò điển hình nào?
A. Điều phối thứ tự các bước dựng một biểu diễn sản phẩm
B. Lưu tất cả instance được tạo vào một kho dùng chung
C. Quyết định subclass factory bằng cách override phương thức
D. Bảo đảm mọi sản phẩm dùng chung một vùng nhớ bất biến
Đáp án đúng: A

8. Một đối tượng Java bất biến được tạo qua Builder nên xử lý `List` mutable thế nào?
A. Lưu nguyên tham chiếu để client và product cùng thay đổi
B. Chuyển mọi List thành biến static của lớp sản phẩm
C. Sao chép phòng vệ vào sản phẩm khi gọi `build()`
D. Cho builder sửa trực tiếp List bên trong sau khi trả product
Đáp án đúng: C

9. Nếu cùng một builder mutable được tái dùng để tạo hai sản phẩm, rủi ro gì?
A. Hai sản phẩm luôn trỏ cùng instance mới được khởi tạo
B. Trình biên dịch sẽ tự xóa giá trị tùy chọn đã thiết lập
C. Trạng thái lần dựng trước có thể còn ở lần dựng sau
D. Mỗi lần gọi `build()` bắt buộc tạo một builder khác
Đáp án đúng: C

10. Để giá trị mặc định như `timeout=30s` có hiệu lực, nên làm thế nào?
A. Gán mọi tham số thiếu thành null tại cuối phương thức build
B. Để constructor sản phẩm tự đọc biến ngẫu nhiên của hệ thống
C. Để từng caller luôn phải truyền lại đúng mọi giá trị mặc định
D. Khởi tạo mặc định trong builder và chỉ ghi đè khi có cấu hình
Đáp án đúng: D

11. Với một lớp Java có constructor private, Builder lồng trong có thể làm gì?
A. Gọi constructor nội bộ để tạo đối tượng đã cấu hình
B. Mở rộng constructor private bằng override từ một subclass
C. Bỏ qua kiểm tra truy cập bằng phản chiếu ở mỗi lần build
D. Biến đối tượng sản phẩm thành một static singleton mặc định
Đáp án đúng: A

12. Khi thiết kế Builder cho `HttpRequest`, lựa chọn nào dễ hiểu và an toàn hơn?
A. Đặt tên bước theo miền như `header(...)`, `body(...)`
B. Dùng `set(int index, Object value)` cho tất cả field
C. Để client thay đổi trực tiếp mảng trạng thái bên trong
D. Bắt mỗi phương thức trả về một sản phẩm chưa hoàn tất
Đáp án đúng: A

13. Khi người dùng gọi `build()` hai lần mà chưa sửa builder, kết quả nào hợp lý?
A. Hai lần gọi luôn bắt buộc trả về đúng cùng một instance
B. Có thể tạo hai sản phẩm tương đương nhưng khác instance
C. Lần thứ hai bắt buộc ném lỗi trong mọi Builder chuẩn
D. Hai kết quả bắt buộc chia sẻ mọi tham chiếu mutable nội bộ
Đáp án đúng: B

14. Vì sao Builder phù hợp với đối tượng có nhiều tổ hợp tùy chọn?
A. Bắt mọi thuộc tính của sản phẩm phải có setter public
B. Tạo thêm subclass tương ứng với từng tổ hợp thuộc tính
C. Cho phép cấu hình theo tên mà không nổ số constructor
D. Thay thế toàn bộ quy tắc hợp lệ bằng chuỗi tham số bất kỳ
Đáp án đúng: C

15. Trong biến thể step builder, API phân các bước thành interface để làm gì?
A. Bảo đảm builder luôn dùng chung instance giữa nhiều thread
B. Cho phép sản phẩm thay đổi sau khi xây dựng thành công
C. Biến toàn bộ bước cấu hình thành event bất đồng bộ
D. Ép một số bước bắt buộc đúng thứ tự tại thời điểm compile
Đáp án đúng: D

16. Khi Builder duy trì trạng thái mutable, kết luận nào đúng về thread safety?
A. Mọi builder mặc định an toàn vì chỉ xây đối tượng mới
B. Không nên chia sẻ giữa các thread khi không đồng bộ phù hợp
C. Fluent API tự động làm mọi thao tác ghi thành atomic
D. Thread safety chỉ phụ thuộc kiểu trả về của hàm build
Đáp án đúng: B

17. Nếu `build()` trả về sản phẩm chứa tham chiếu đến cùng `Map` của Builder, lỗi nào dễ xảy ra?
A. Sản phẩm luôn độc lập vì Map là kiểu dữ liệu Java chuẩn
B. Sản phẩm sẽ tự sinh bản sao mỗi khi getter được gọi
C. Sửa cấu hình builder sau đó có thể làm đổi sản phẩm cũ
D. Compiler sẽ ngăn tất cả thay đổi Map sau khi return
Đáp án đúng: C

18. Một sản phẩm có invariant `min <= max`, nên xác nhận tại đâu?
A. Trong `build()` trước khi công bố sản phẩm hoàn chỉnh
B. Chỉ trong lớp UI ngay lúc người dùng nhập giá trị
C. Chỉ khi serializing sản phẩm sang JSON ở response
D. Chỉ khi đối tượng bị đưa vào garbage collector
Đáp án đúng: A

19. So với truyền một `Map<String,Object>`, Builder kiểu mạnh có ưu thế gì?
A. Cho phép bỏ kiểm tra mọi giá trị quan hệ trong miền
B. Bảo đảm serialization không bao giờ phát sinh lỗi
C. Phát hiện lỗi kiểu và gợi ý tên tham số ngay khi lập trình
D. Cho phép tự động chọn subclass mà không cần interface
Đáp án đúng: C

20. Điều gì thường khiến việc dùng Builder cho một lớp là quá mức cần thiết?
A. Đối tượng chứa rất nhiều trường tùy chọn dễ nhầm lẫn
B. Lớp có ít tham số rõ ràng và rất ít biến thể
C. Quy trình dựng cần các bước có thứ tự và kiểm tra
D. Sản phẩm cần bất biến và cấu hình có giá trị mặc định
Đáp án đúng: B

21. Khi xây `Order` từ các dòng hàng, vì sao không nên cho caller lấy List bên trong builder?
A. Caller sẽ bắt buộc phải tạo một immutable list trước
B. Caller có thể sửa trạng thái mà Builder không kiểm soát được
C. Caller không thể duyệt List nếu nó thuộc class nested
D. Caller tự động được phép sửa invariant khi build hoàn tất
Đáp án đúng: B

22. Trong GoF Builder, hai ConcreteBuilder khác nhau có thể mang lại lợi ích gì?
A. Cùng tạo một đối tượng duy nhất xuyên suốt mọi chương trình
B. Cùng override constructor của một abstract base product
C. Cùng sao chép trực tiếp mọi trạng thái từ một prototype
D. Cùng quy trình dựng nhưng tạo biểu diễn sản phẩm khác nhau
Đáp án đúng: D

23. Trong unit test, Builder dành cho dữ liệu thử thường hữu ích để làm gì?
A. Thay thế assertion kiểm chứng các quy tắc nghiệp vụ
B. Ẩn mọi dữ liệu đầu vào để test không cần đọc kết quả
C. Bỏ luôn các test ca thiếu trường bắt buộc của đối tượng
D. Tạo fixture mặc định và sửa vài trường theo ca kiểm thử
Đáp án đúng: D

24. Lựa chọn nào mô tả đúng giới hạn của Builder?
A. Tự thay thế validation nghiệp vụ trong mọi constructor
B. Giúp cấu hình dễ đọc nhưng không tự bảo đảm object đúng
C. Tự làm thread safe mọi trường có thể thay đổi của product
D. Tự giải quyết việc phân quyền trước khi tạo đối tượng
Đáp án đúng: B
