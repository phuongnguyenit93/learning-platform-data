Câu 1. Trong Java, mối quan hệ giữa class và object được hiểu đúng như thế nào?
A. Class là instance riêng được tạo ra cho từng biến tham chiếu
B. Object định nghĩa bộ constructor của class tại thời gian biên dịch
C. Class mô tả kiểu; object là instance của class khi được tạo
D. Object là tên khác của file nguồn Java chứa nhiều class
Đáp án đúng: C

Câu 2. Khi thực thi new Customer(), điều gì thường diễn ra?
A. Chỉ một biến kiểu Customer được khai báo mà chưa tạo object
B. Class Customer được tạo lại dù trước đó đã được JVM nạp
C. Một bản sao của toàn bộ class file được gắn vào mỗi biến
D. Một object được cấp phát và constructor phù hợp được gọi
Đáp án đúng: D

Câu 3. Hai object cùng class đều có field instance int count; thay count của object A sẽ thế nào?
A. Thay field count của B vì cùng tham chiếu tới class
B. Đổi tất cả field static của B thành cùng giá trị count
C. Không tự làm thay đổi count ở object B khác A
D. Thay B ngay cả khi A và B là hai object riêng biệt
Đáp án đúng: C

Câu 4. Field instance kiểu int không gán tường minh được khởi tạo mặc định ra sao?
A. Nhận giá trị 0 khi một object mới được khởi tạo
B. Giữ trạng thái chưa xác định cho tới lần đọc đầu
C. Nhận giá trị null tương tự mọi field tham chiếu
D. Bắt buộc có initializer trong mọi khai báo field
Đáp án đúng: A

Câu 5. Vì sao javac không cho đọc local variable trước khi được gán chắc chắn?
A. Local variable luôn được mặc định gán 0 như instance field
B. JVM chỉ kiểm tra giá trị local sau khi gọi constructor
C. Trình biên dịch tự gọi setter khi local chưa có giá trị
D. Biến cục bộ phải thỏa kiểm tra definite assignment
Đáp án đúng: D

Câu 6. Khi khai báo constructor của class Invoice, đặc điểm nào đúng?
A. Tên có thể tùy ý miễn kiểu trả về là void hoặc Invoice
B. Tên là Invoice và không khai kiểu trả về trong khai báo
C. Constructor luôn là static method để cấp phát object
D. Constructor cần trả về reference mới khi chạy xong thân hàm
Đáp án đúng: B

Câu 7. Nếu class đã khai constructor Invoice(String id) nhưng không có constructor rỗng, new Invoice() thường thế nào?
A. Java tự sinh constructor mặc định bất chấp constructor đã khai
B. Compiler tự truyền null vào tham số id khi gọi constructor
C. JVM chọn mọi constructor có một tham số String và bỏ qua id
D. Không biên dịch vì không có constructor không tham số phù hợp
Đáp án đúng: D

Câu 8. Trong constructor có tham số name, câu this.name = name thường mang ý nghĩa nào?
A. Gán biến class name của mọi object thuộc cùng ClassLoader
B. Gán một local variable name khác vào static field mặc định
C. Gán tham số name cho instance field name của object hiện tại
D. Đổi tên tham số name trong danh sách tham số constructor
Đáp án đúng: C

Câu 9. Khi constructor dùng this(args) để gọi constructor khác trong cùng class, mục đích nào phù hợp?
A. Gọi constructor cùng class để dùng chung bước khởi tạo
B. Gọi constructor superclass theo quy tắc dispatch động
C. Tự tạo object thứ hai rồi trả về thay object hiện tại
D. Gọi method override trước khi tạo instance field
Đáp án đúng: A

Câu 10. Trong constructor của subclass, super(args) thường được dùng để làm gì?
A. Gọi lại constructor hiện tại để tăng depth khởi tạo
B. Bỏ qua mọi initializer của superclass khi tạo subclass
C. Tạo một object superclass độc lập không liên quan subclass
D. Chọn và gọi constructor của superclass với đối số phù hợp
Đáp án đúng: D

Câu 11. Một method nhận tham số Person p rồi gán p = new Person(); biến reference tại caller thay đổi không?
A. Có; mọi phép gán p trong method đổi biến tại caller
B. Có; Java truyền địa chỉ của biến caller để gán lại
C. Không; tham số p là một bản sao của reference
D. Không; vì constructor mới luôn trả về giá trị null
Đáp án đúng: C

Câu 12. Method nhận List<String> xs và gọi xs.add("x") có thể ảnh hưởng list của caller vì sao?
A. Java truyền biến xs của caller bằng cơ chế pass-by-reference
B. Hai reference cùng trỏ List mutable nên thấy thay đổi
C. Mọi List trong JVM chia sẻ chung buffer tĩnh mặc định
D. Gọi add luôn làm đổi reference caller sang list được sao chép
Đáp án đúng: B

Câu 13. Sau câu lệnh b = a với hai biến kiểu Node, nhận định nào đúng nếu a khác null?
A. b là bản sao sâu của object a do JVM tạo khi gán
B. b là object mới được clone mặc định ngay cả khi chưa có clone
C. b chỉ nhận cùng kiểu Node nhưng không nhận reference của a
D. b và a cùng tham chiếu object đó, không tự sao chép object
Đáp án đúng: D

Câu 14. Với hai biến tham chiếu a và b, toán tử a == b kiểm tra điều gì?
A. Nội dung object bằng nhau theo equals đã override
B. Hai biến chứa cùng reference, hoặc cùng null
C. Hai object có chung giá trị hashCode được tính
D. Hai object có các field primitive giống nhau
Đáp án đúng: B

Câu 15. Khi gọi obj.method() mà obj là null, lỗi điển hình khi chạy là gì?
A. ClassCastException vì method thuộc loại không phù hợp
B. NullPointerException khi dereference obj đang null
C. NoSuchMethodError vì class obj chưa có method đó
D. IllegalAccessException vì quyền truy cập obj bị thiếu
Đáp án đúng: B

Câu 16. Một instance field private của class Account có thể được truy cập trực tiếp từ đâu?
A. Trong mọi subclass Account bất kể package hoặc module
B. Trong mọi class cùng package mà không cần accessor
C. Trong mọi file source import được tên class Account
D. Code của chính class Account, kể cả instance khác
Đáp án đúng: D

Câu 17. Member không có access modifier trong một class top-level có phạm vi truy cập nào?
A. Protected, dùng cho mọi subclass trên module path
B. Public, vì không khai modifier nghĩa là tự export
C. Package-private, dùng trong cùng package theo quy tắc Java
D. Private, chỉ gọi được từ code ở cùng một instance
Đáp án đúng: C

Câu 18. Subclass ở package khác muốn truy cập protected field kế thừa, trường hợp nào hợp lệ?
A. Truy cập qua this hoặc reference kiểu subclass hợp lệ
B. Truy cập qua mọi instance superclass bất kể kiểu tham chiếu
C. Chỉ được truy cập sau khi gọi Class.forName với tên superclass
D. Chỉ được truy cập nếu field cũng được khai final trong class cha
Đáp án đúng: A

Câu 19. Nếu getter trả thẳng List mutable nội bộ của object, rủi ro đóng gói là gì?
A. Getter tự biến List thành unmodifiable collection khi trả về
B. Caller chỉ thấy bản copy của list do Java tự tạo ngầm
C. Trả List đồng nghĩa field bên trong phải có modifier static
D. Caller có thể sửa List nội bộ qua getter trả reference
Đáp án đúng: D

Câu 20. Với static int total trong class Order, cách hiểu đúng nhất là gì?
A. Mỗi object Order có một static field total riêng biệt
B. Một field thuộc class, dùng chung giữa các instance
C. Mỗi thread tự có total tương ứng ThreadLocal mặc định
D. Mỗi method tạo Order tự sinh một biến static mới
Đáp án đúng: B

Câu 21. Vì sao static method không thể trực tiếp dùng this trong thân method?
A. this chỉ được dùng trong class abstract hoặc record
B. this bị cấm vì JVM chưa nạp static constant pool
C. this chỉ hợp lệ khi static method khai public final
D. Static method không gắn instance hiện tại cho this
Đáp án đúng: D

Câu 22. Nếu subclass khai static method cùng signature với superclass, dispatch khi gọi thường thế nào?
A. Đó là overriding; JVM chọn theo runtime class của object
B. Đó là method overload; compiler chọn theo số instance field
C. Đó là interface default method; JVM chọn theo class loader
D. Đó là method hiding; chọn theo kiểu compile-time của biểu thức
Đáp án đúng: D

Câu 23. Khi khai báo final class Report, điều bị ngăn ở mức ngôn ngữ Java là gì?
A. Class Report không được phép bị class khác kế thừa
B. Không được tạo instance Report qua constructor public
C. Không được đặt field mutable trong bất kỳ object Report
D. Không được khai static method trong class Report
Đáp án đúng: A

Câu 24. Nếu instance method trong superclass được khai final, subclass được phép làm gì?
A. Override method nếu đánh dấu @Override ở subclass
B. Kế thừa method đó nhưng không override cùng signature
C. Chuyển method đó thành static để giữ nguyên signature
D. Thay return type covariant để override method final
Đáp án đúng: B

Câu 25. Blank final instance field được gán trong constructor thường phải đáp ứng gì?
A. Được gán lại bất cứ lúc nào qua setter của object
B. Phải gán đúng một lần khi constructor hoàn tất bình thường
C. Được bỏ chưa gán nếu field thuộc kiểu primitive
D. Phải khởi tạo bằng null dù constructor sẽ gán lại
Đáp án đúng: B

Câu 26. Với final List<String> items trỏ đến ArrayList, điều gì vẫn có thể hợp lệ?
A. items.add hợp lệ khi List mutable, không được gán lại items
B. Không thể thay đổi phần tử nào vì final làm List immutable
C. Có thể gán items sang ArrayList mới sau khi constructor chạy
D. Java tự đổi ArrayList thành List.of mỗi khi dùng final
Đáp án đúng: A

Câu 27. Với public static final int LIMIT = 20 là constant expression, thay đổi ở thư viện có rủi ro nào?
A. Client cũ có thể vẫn dùng hằng số 20 đã inline
B. Client luôn đọc giá trị LIMIT mới mà không cần build lại
C. JVM cấm load thư viện nếu constant được đổi thành 30
D. Mọi tham chiếu LIMIT được chuyển thành volatile access
Đáp án đúng: A

Câu 28. Khi khởi tạo subclass lần đầu làm superclass chưa được initialize, thứ tự static init thường thế nào?
A. Subclass initialize trước rồi mới chạy static block của superclass
B. Superclass được initialize trước subclass theo quy tắc JVM
C. Hai class static initializer luôn chạy song song ở hai thread
D. Superclass không chạy initializer nếu subclass có static method
Đáp án đúng: B

Câu 29. Khi tạo object Derived extends Base, thứ tự constructor body thường thế nào?
A. Constructor body Derived hoàn tất trước khi Base được gọi
B. Chỉ một constructor body chạy vì object có một địa chỉ
C. Body constructor Base chạy trước body constructor Derived
D. Hai constructor body được JVM chạy song song để tối ưu
Đáp án đúng: C

Câu 30. Trong một class, instance field initializer và instance initializer block thường chạy theo thứ tự nào?
A. Theo thứ tự khai báo source trước constructor body
B. Chạy tất cả initializer block trước mọi field initializer
C. Chạy cuối cùng sau khi constructor class đó đã return
D. Theo thứ tự tên field sắp xếp alphabet bởi compiler
Đáp án đúng: A

Câu 31. Vì sao gọi method có thể override từ constructor của superclass có rủi ro?
A. Vì method override luôn là static nên không có this
B. Vì superclass constructor tự sao chép object subclass
C. Subclass được dispatch khi chưa khởi tạo đủ field của nó
D. Vì Java bắt buộc gọi mọi setter trước khi vào constructor
Đáp án đúng: C

Câu 32. Khi gọi một instance method bị override qua biến kiểu Base trỏ tới Derived, method nào thường chạy?
A. Implementation ở Base luôn chạy vì biến khai kiểu Base
B. Cả Base và Derived được gọi tự động theo thứ tự
C. Không method nào chạy vì runtime class khác declared type
D. Chạy implementation Derived theo runtime type
Đáp án đúng: D

Câu 33. Nếu Base và Derived cùng khai field int code và biến Base x trỏ Derived, x.code tham chiếu field nào?
A. Field của Derived vì field được dispatch động như method
B. Cả hai field được cộng rồi trả về một giá trị mới
C. Field của Base vì truy cập field dùng kiểu compile-time
D. Không hợp lệ vì field name bị trùng giữa hai class
Đáp án đúng: C

Câu 34. Khi hai method overload có cùng tên nhưng khác kiểu tham số, Java chọn overload dựa chủ yếu vào gì?
A. Runtime type của object nhận được sau khi JVM thực thi
B. Giá trị hashCode của từng argument tại runtime
C. Compiler chọn overload từ kiểu đối số tại compile time
D. Số dòng source trong phần thân method của mỗi overload
Đáp án đúng: C

Câu 35. Nếu ghi @Override cho method không thực sự override hay implement method phù hợp, chuyện gì xảy ra?
A. Annotation được bỏ qua và luôn biên dịch bình thường
B. JVM tự sinh method adapter phù hợp khi nạp class
C. Method mặc nhiên bị chuyển thành overload của Object
D. javac báo lỗi nếu method không override đúng chữ ký
Đáp án đúng: D

Câu 36. Một abstract class trong Java có thể được sử dụng theo cách nào?
A. Không được định nghĩa constructor vì abstract class chưa có object
B. Abstract class có constructor nhưng không new trực tiếp
C. Chỉ được khai abstract method và cấm mọi instance field
D. Có thể new trực tiếp abstract class nếu constructor public
Đáp án đúng: B

Câu 37. Khi subclass override method protected từ superclass, quyền truy cập của method override phải như thế nào?
A. Giữ protected hoặc nới thành public, không thu hẹp thành private
B. Được đổi thành private vì subclass luôn có nhiều quyền hơn
C. Phải đổi thành package-private để JVM nhận method override
D. Bắt buộc đổi thành static để phù hợp quy tắc package
Đáp án đúng: A

Câu 38. Trong method override, gọi super.calculate() thường mang ý nghĩa nào?
A. Gọi lại constructor superclass và tạo object mới
B. Chọn overload calculate bất kỳ theo runtime type của object
C. Buộc bỏ qua interface contract khi thực thi calculate
D. Gọi method ở superclass thay cho override đang chạy
Đáp án đúng: D

Câu 39. Nếu muốn chỉ cho phép tạo object qua static factory, class nên thiết kế constructor thế nào?
A. Dùng protected constructor nhưng mọi package vẫn new được
B. Dùng abstract constructor để vô hiệu lời gọi new
C. Dùng private constructor, mở public static factory
D. Dùng final constructor để chặn mọi nơi khởi tạo
Đáp án đúng: C

Câu 40. Với immutable class giữ List đầu vào, cách phòng tránh caller sửa trạng thái sau constructor là gì?
A. Lưu List gốc nhưng gán field final là đủ bất biến
B. Tạo defensive copy của List đầu vào khi lưu field
C. Lưu reference List rồi chỉ đổi tên accessor trả về
D. Đặt field volatile để ngăn caller thay đổi phần tử
Đáp án đúng: B

Câu 41. Immutable class trả về một mảng byte[] nội bộ qua getter cần làm gì để tránh lộ trạng thái?
A. Trả defensive copy của mảng thay vì mảng gốc
B. Trả trực tiếp mảng vì khai final làm byte[] bất biến
C. Trả cùng mảng nhưng thêm synchronized vào getter
D. Trả mảng gốc cùng hashCode để caller không sửa
Đáp án đúng: A

Câu 42. Với record Point(int x, int y), accessor mặc định nào được tạo?
A. getX() và getY() thay cho accessor component
B. x() và y() trả về các giá trị component tương ứng
C. setX(int) và setY(int) để sửa component trực tiếp
D. x và y là public mutable fields truy cập không cần method
Đáp án đúng: B

Câu 43. Với record Point(int x, int y), equals được sinh tự động có tiêu chí nào?
A. Chỉ so object identity như toán tử == của reference
B. Chỉ so toString của hai object không xét component
C. So các component tương ứng theo quy tắc bằng nhau của record
D. Chỉ so hashCode rồi kết luận hai record bằng nhau
Đáp án đúng: C

Câu 44. Record chứa component List<String> items có bảo đảm bất biến sâu của phần tử không?
A. Không; List mutable vẫn có thể bị sửa nếu không defensive copy
B. Có; record tự chuyển mọi List component thành immutable list
C. Có; record chặn mọi lời gọi add của reference đã lưu
D. Không; vì record luôn bỏ qua equals của mọi component List
Đáp án đúng: A

Câu 45. Compact constructor của record thường được dùng hợp lý để làm gì?
A. Thêm instance field mutable ngoài các component record
B. Bỏ qua việc khởi tạo final field và để null vô hạn
C. Kiểm tra hoặc chuẩn hóa component trước khi được gán vào field
D. Cho phép record kế thừa class bất kỳ ngoài java.lang.Record
Đáp án đúng: C

Câu 46. Nếu record R được khai báo, ràng buộc thừa kế nào đúng với record class?
A. Record ngầm abstract và phải được subclass implements
B. Record ngầm final, extends java.lang.Record và không extends class tùy ý
C. Record có thể extends một record khác cùng package
D. Record phải extends Object trực tiếp và không implement interface
Đáp án đúng: B

Câu 47. Một direct subclass của sealed class thường cần đáp ứng gì?
A. Có trong tập permitted và khai final, sealed hoặc non-sealed
B. Chỉ cần private constructor, không cần nằm trong permits
C. Có thể kế thừa mà bỏ mọi modifier nếu package trùng
D. Phải luôn khai non-sealed dù không muốn cho lớp con
Đáp án đúng: A

Câu 48. Với sealed class trong named module, direct permitted subclass cần thỏa điều kiện vị trí nào?
A. Nằm trong cùng named module với sealed superclass
B. Nằm cùng package dù ở named module khác nhau
C. Nằm ở bất kỳ module nào có requires tới superclass
D. Bắt buộc là nested class bên trong sealed superclass
Đáp án đúng: A
