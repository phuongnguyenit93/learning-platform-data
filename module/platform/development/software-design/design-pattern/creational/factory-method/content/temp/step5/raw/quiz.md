1. Ý tưởng cốt lõi của Factory Method trong GoF là gì?
A. Để một singleton cung cấp mọi sản phẩm cho toàn hệ thống
B. Để lớp con quyết định kiểu sản phẩm cụ thể được tạo
C. Để mỗi đối tượng mới được sao chép từ một mẫu đã có
D. Để client thiết lập từng trường qua một builder fluent
Đáp án đúng: B

2. Trong Factory Method, `Product` thường đóng vai trò nào?
A. Giao diện chung cho các sản phẩm do factory tạo
B. Bộ điều phối thứ tự các bước tạo sản phẩm phức tạp
C. Bản ghi lưu mọi instance đã tạo trong registry
D. Đối tượng giữ trạng thái dùng chung giữa các creator
Đáp án đúng: A

3. Trong GoF Factory Method, `Creator` thường định nghĩa gì?
A. Một bảng cấu hình duy nhất ánh xạ tên vào class
B. Một constructor public cho mọi sản phẩm triển khai
C. Một method sao chép object theo cùng dữ liệu đầu vào
D. Một phương thức tạo sản phẩm trả về kiểu Product chung
Đáp án đúng: D

4. Một `ConcreteCreator` thường tùy biến cách tạo sản phẩm bằng gì?
A. Override factory method để khởi tạo ConcreteProduct
B. Override tất cả constructor của lớp cha để thay sản phẩm
C. Thay đổi trực tiếp private field của Product từ client
D. Đưa mọi cấu hình sản phẩm vào biến static toàn cục
Đáp án đúng: A

5. Trong quy trình `export()`, vì sao Creator gọi `createWriter()` thay vì `new PdfWriter()`?
A. Buộc mọi lần export tái dùng đúng một Writer duy nhất
B. Cho phép client bỏ qua interface Writer và sửa trạng thái
C. Bảo đảm writer luôn chạy bất đồng bộ sau khi export
D. Cho phép thay Writer bằng đa hình mà không sửa quy trình
Đáp án đúng: D

6. Trong Java, lời gọi `createWriter()` được override sẽ chọn triển khai theo gì?
A. Kiểu tĩnh của biến `Writer` ở bên trái phép gán
B. Tên method xuất hiện trước trong file nguồn Java
C. Kiểu thực tế của đối tượng Creator tại thời điểm chạy
D. Thứ tự class con được biên dịch bởi build tool
Đáp án đúng: C

7. Điểm khác giữa Factory Method và Simple Factory dùng `switch(type)` là gì?
A. Factory Method luôn dùng `switch` trong một class chung
B. Simple Factory bắt buộc tạo một subclass cho mỗi creator
C. Simple Factory tự hỗ trợ đa hình chỉ bằng constructor
D. Factory Method mở rộng cách tạo thông qua kế thừa
Đáp án đúng: D

8. Trong Java, phương thức `static` có thể override như factory method ảo không?
A. Có, static chọn override theo runtime type của instance
B. Có, chỉ cần đánh dấu static method là `protected`
C. Không, vì Java không cho phép static tạo object mới
D. Không, static bị che tên chứ không dispatch đa hình
Đáp án đúng: D

9. Khi thêm định dạng ảnh PNG, cách mở rộng nào hợp Factory Method?
A. Tạo `PngCreator` trả về `PngImage` qua phương thức tạo
B. Sửa tất cả client để gọi trực tiếp `new PngImage()`
C. Bắt Product interface định nghĩa riêng constructor PNG
D. Đổi mọi Creator thành singleton để nhận sản phẩm PNG
Đáp án đúng: A

10. Factory Method tuân thủ Open/Closed Principle chủ yếu bằng cách nào?
A. Cho phép thêm creator mới thay vì sửa thuật toán dùng Product
B. Buộc module client tự kiểm tra mọi subclass bằng if-else
C. Bảo đảm không class nào cần sửa dù giao diện Product thay đổi
D. Chuyển mọi quy tắc tạo sản phẩm vào một database chung
Đáp án đúng: A

11. Vì sao Factory Method thường được đặt cạnh một phương thức xử lý của Creator?
A. Creator phải gọi trực tiếp tất cả constructor có sẵn
B. Product cần quyết định subclass của Creator để chạy
C. Thuật toán chung sử dụng Product mà không biết lớp cụ thể
D. Factory method bắt buộc trả về một chuỗi mô tả sản phẩm
Đáp án đúng: C

12. Khi viết unit test, subclass Creator có factory method giả giúp gì?
A. Bỏ hoàn toàn việc xác minh output trong test
B. Đảm bảo class được test không bao giờ cần interface
C. Thay Product bằng fake để thử thuật toán của Creator
D. Ép test chạy logic thật của mọi thư viện bên ngoài
Đáp án đúng: C

13. Factory Method khác Abstract Factory ở phạm vi tạo sản phẩm thế nào?
A. Factory Method chỉ tạo primitive; Abstract Factory tạo object
B. Một phương thức tạo Product; Abstract Factory tạo họ liên quan
C. Factory Method luôn tạo qua static; Abstract Factory qua clone
D. Factory Method không dùng kế thừa; Abstract Factory bắt buộc
Đáp án đúng: B

14. Trong ứng dụng nhiều theme, Abstract Factory hữu ích hơn Factory Method đơn lẻ khi nào?
A. Chỉ cần tạo một loại Parser có nhiều triển khai khác nhau
B. Cần tạo một Object với nhiều tham số cấu hình tùy chọn
C. Cần sao chép một cây object đã được cấu hình sẵn
D. Cần tạo đồng bộ nhiều thành phần thuộc một họ giao diện
Đáp án đúng: D

15. Factory Method khác Builder ở mục tiêu chính nào?
A. Builder chỉ chọn class bằng override còn Factory đi từng bước
B. Chọn sản phẩm qua điểm mở rộng thay vì cấu hình từng bước
C. Factory Method bắt buộc gọi nhiều setter trước khi trả Product
D. Builder sao chép mẫu còn Factory Method dùng event sourcing
Đáp án đúng: B

16. Factory Method khác Prototype khi tạo sản phẩm ra sao?
A. Factory Method phải có clone, Prototype phải gọi constructor ảo
B. Factory Method chỉ dùng một instance; Prototype tạo singleton
C. Tạo qua factory method; Prototype tạo bằng việc sao chép mẫu
D. Hai mẫu đều yêu cầu copy sâu mọi field trước khi tạo
Đáp án đúng: C

17. Trong framework có bước mở rộng `createHandler()`, lợi ích nào thiết thực?
A. Framework cần sửa code khi ứng dụng thêm Handler mới
B. Ứng dụng tùy biến Handler mà giữ logic điều phối chung
C. Mọi Handler phải cùng chia sẻ trạng thái singleton mutable
D. Client phải biết class Handler cụ thể trong mọi lời gọi
Đáp án đúng: B

18. Nếu lớp cha `Creator` có implementation mặc định cho factory method, điều đó có hợp lệ không?
A. Không, Factory Method bắt buộc là abstract ở mọi trường hợp
B. Có, lớp con có thể dùng mặc định hoặc override khi cần
C. Không, vì Java không cho method tạo trả về interface
D. Có, nhưng khi đó tất cả sản phẩm phải là một singleton
Đáp án đúng: B

19. Đối tượng trả về Factory Method có bắt buộc được tạo bằng `new` ngay tại method không?
A. Có, vì mọi factory method phải gọi trực tiếp constructor
B. Có, vì không được trả về object được truyền từ ngoài
C. Không, nhưng chỉ được sao chép một instance toàn cục
D. Không, method có thể lấy từ cache hay nguồn tạo khác
Đáp án đúng: D

20. Khi nào Factory Method có thể làm thiết kế nặng nề không cần thiết?
A. Có nhiều subclass cần chọn Product tùy từng triển khai
B. Có khung xử lý chung nhưng cách tạo đối tượng thay đổi
C. Chỉ có một loại Product và không cần mở rộng
D. Thư viện cần test thuật toán với Product thay thế
Đáp án đúng: C

21. Trong Java, kiểu trả về covariant giúp ConcreteCreator làm gì?
A. Override method trả subtype của Product mà vẫn hợp lệ
B. Override method static bằng instance method cùng tên
C. Dùng kiểu trả về không liên quan đến method của cha
D. Tạo instance mà không phải thỏa hợp đồng Product
Đáp án đúng: A

22. Lợi ích của việc để client làm việc với interface Product là gì?
A. Giảm phụ thuộc vào implementation cụ thể của sản phẩm
B. Bảo đảm Product không bao giờ có trạng thái mutable
C. Buộc mọi client phải biết tên ConcreteCreator đang chạy
D. Cho phép client truy cập trực tiếp field private của Product
Đáp án đúng: A

23. Nếu phải chọn sản phẩm theo chuỗi cấu hình lúc runtime, cần cân nhắc điều gì?
A. Bắt tạo một subclass mới cho từng giá trị input runtime
B. Dùng registry hoặc factory tham số nếu hợp hơn kế thừa
C. Chuyển mọi constructor thành private static không đối số
D. Dùng Factory Method mà không cần chọn ConcreteCreator
Đáp án đúng: B

24. Đánh đổi dễ gặp của Factory Method khi số biến thể tăng là gì?
A. Làm mọi Product mất khả năng triển khai qua interface
B. Buộc từng request phải mở kết nối database riêng
C. Tăng số subclass Creator cần duy trì và điều hướng
D. Làm các phương thức xử lý chung không thể tái sử dụng
Đáp án đúng: C
