Bạn giải thích sự khác nhau giữa một class definition và một object instance trong Java như thế nào?
Bạn phân biệt trạng thái, hành vi và danh tính của đối tượng khi thiết kế một Java class ra sao?
Bạn sẽ quyết định một khái niệm nghiệp vụ cần được mô hình hóa thành class độc lập theo tiêu chí nào?
Bạn giải thích vì sao hai đối tượng được tạo từ cùng một class có thể giữ trạng thái khác nhau như thế nào?
Bạn phân biệt object reference với object thực được JVM quản lý theo nghĩa gán biến như thế nào?
Bạn sẽ mô tả điều gì xảy ra khi khai báo một biến kiểu tham chiếu nhưng chưa tạo đối tượng bằng new ra sao?
Bạn phân biệt primitive variable với reference variable về cách lưu và truyền giá trị như thế nào?
Bạn giải thích vì sao gán một reference sang biến thứ hai không tự sao chép đối tượng như thế nào?
Bạn sẽ xác định tác động khi hai biến cùng tham chiếu đến một mutable object và một biến thay đổi field ra sao?
Bạn phân biệt null reference với một object có fields mang giá trị mặc định như thế nào?
Bạn sẽ đánh giá khi nào dùng factory method thay vì new trực tiếp khi tạo object theo yêu cầu nào?
Bạn mô tả các thành phần package, imports, class declaration và members trong một Java source file như thế nào?
Bạn phân biệt top-level class với nested class theo vị trí khai báo và giới hạn modifier ra sao?
Bạn sẽ xác định các quy tắc đặt tên package và public top-level class khi tổ chức mã nguồn Java như thế nào?
Bạn giải thích vai trò của this khi một instance method truy cập state của chính đối tượng như thế nào?
Bạn phân biệt this reference với tên biến local trùng tên instance field như thế nào?
Bạn sẽ dùng this.field để giải quyết shadowing khi constructor nhận parameter trùng tên field ra sao?
Bạn phân tích vì sao this không thể được dùng trong static context theo mô hình đối tượng như thế nào?
Bạn sẽ phân biệt object identity với giá trị nghiệp vụ khi hai reference trỏ tới hai instances độc lập ra sao?
Bạn mô tả tác dụng của instanceof trong kiểm tra kiểu đối tượng trước khi xử lý theo subtype ra sao?
Bạn phân biệt compile-time reference type với runtime object type trong một phép gán đa hình như thế nào?
Bạn sẽ thiết kế class thể hiện invariant nghiệp vụ mà không để các callers thao tác tùy ý với fields ra sao?
Bạn phân tích khi nào một class có quá nhiều trách nhiệm vi phạm nguyên tắc single responsibility theo dấu hiệu nào?
Bạn sẽ chọn class composition thay vì tạo hàng loạt utility methods để đóng gói hành vi gắn với state như thế nào?
Bạn giải thích instance field được tạo cùng object khác static field thuộc class về vòng đời và chia sẻ state ra sao?
Bạn phân biệt field initialization với local variable initialization theo những giá trị mặc định Java cung cấp như thế nào?
Bạn sẽ xác định mặc định của primitive fields và reference fields trước khi constructor gán giá trị ra sao?
Bạn mô tả field hiding xảy ra khi subclass khai báo field cùng tên với superclass như thế nào?
Bạn phân biệt việc truy cập field theo compile-time type với dispatch của instance method theo runtime type ra sao?
Bạn sẽ giải thích vì sao mutable public fields khiến việc duy trì invariant trở nên khó khăn như thế nào?
Bạn mô tả vai trò của getter và setter đối với đóng gói nhưng đánh giá khi nào không nên tạo setter cho mọi field ra sao?
Bạn sẽ đặt validation vào constructor, factory hay mutator method để giữ trạng thái hợp lệ như thế nào?
Bạn phân tích rủi ro setter cho phép đổi field A nhưng không đồng bộ field B vốn phụ thuộc vào nó như thế nào?
Bạn sẽ thiết kế một object trạng thái đơn giản với methods có ý nghĩa nghiệp vụ thay vì các setters tùy ý ra sao?
Bạn phân biệt direct reference assignment với shallow copy khi một class chứa field trỏ tới List như thế nào?
Bạn sẽ thiết kế copy constructor khi object có nested mutable references để tránh chia sẻ state ngoài ý muốn như thế nào?
Bạn mô tả cách Java garbage collector xác định object nào còn reachable qua các reference chains như thế nào?
Bạn phân biệt biến reference ra khỏi scope với việc object chắc chắn được thu gom ngay lập tức như thế nào?
Bạn sẽ nhận diện memory leak do static collection giữ references tới nhiều objects không còn được dùng ra sao?
Bạn phân tích rủi ro lưu instance vào cache lâu dài mà không có eviction hoặc giới hạn số lượng như thế nào?
Bạn sẽ lựa chọn strong, weak hoặc soft reference theo nhu cầu quan sát vòng đời object như thế nào?
Bạn mô tả WeakReference có thể hữu ích khi cache không được ngăn garbage collection của object như thế nào?
Bạn sẽ xác định vì sao finalize không phải cơ chế đáng tin cậy để đóng tài nguyên của một object như thế nào?
Bạn phân biệt garbage collection với việc giải phóng tài nguyên bên ngoài như file handle hoặc socket ra sao?
Bạn sẽ sử dụng AutoCloseable và try-with-resources để biểu diễn vòng đời tài nguyên thuộc object như thế nào?
Bạn phân tích nguy cơ object được dùng sau close dù Java reference vẫn khác null ra sao?
Bạn sẽ thiết kế idempotent close method cho class quản lý tài nguyên có thể được gọi cleanup nhiều lần ra sao?
Bạn phân biệt object graph được giữ bởi singleton với các objects chỉ tồn tại trong một request về nguy cơ retained memory ra sao?
Bạn sẽ kiểm tra một heap dump để xác định chuỗi references giữ object đáng lẽ đã được thu gom như thế nào?
Bạn giải thích instance method khác static method ở cách truy cập state và dispatch của JVM như thế nào?
Bạn phân biệt parameter, local variable và field trong phạm vi hiệu lực của một method ra sao?
Bạn sẽ thiết kế method signature rõ ý nghĩa bằng tên, kiểu tham số và return type theo nguyên tắc nào?
Bạn mô tả Java pass-by-value hoạt động thế nào khi method nhận một primitive argument?
Bạn phân biệt Java pass-by-value với việc truyền bản sao object reference khi method nhận đối tượng ra sao?
Bạn sẽ xác định vì sao method có thể thay đổi field của object được truyền vào nhưng không thay đổi biến reference của caller ra sao?
Bạn giải thích method overloading được compiler chọn dựa vào parameter types như thế nào?
Bạn phân biệt method overloading với method overriding theo thời điểm chọn implementation ra sao?
Bạn sẽ đánh giá ảnh hưởng của autoboxing, widening và varargs khi nhiều overloaded methods đều có vẻ phù hợp như thế nào?
Bạn phân tích rủi ro overload nhận các reference types khác nhau khi caller truyền null ra sao?
Bạn sẽ quyết định khi nào dùng phương thức có nhiều parameters và khi nào tạo một parameter object ra sao?
Bạn mô tả return statement với kiểu trả về reference không tự sao chép object như thế nào?
Bạn sẽ thiết kế method trả collection sao cho caller không vô ý sửa internal state của object ra sao?
Bạn phân biệt pure method với method thay đổi instance state theo khả năng kiểm thử và thread safety như thế nào?
Bạn phân tích vì sao getter trả về mutable Date hoặc List có thể làm hỏng encapsulation dù field là private ra sao?
Bạn sẽ xử lý unchecked runtime exceptions khác checked exceptions tại ranh giới method API như thế nào?
Bạn mô tả tác dụng của final parameter đối với việc gán lại biến parameter và giới hạn mà nó không tạo ra ra sao?
Bạn phân biệt final local variable với effectively final local variable khi được capture trong lambda như thế nào?
Bạn sẽ xác định vì sao Java method không thể overload chỉ bằng cách đổi return type ra sao?
Bạn phân tích rủi ro có quá nhiều overload với default-like parameters khiến API khó hiểu như thế nào?
Bạn sẽ thiết kế method phản ánh trạng thái chuyển đổi nghiệp vụ mà không để đối tượng rơi vào trạng thái nửa cập nhật ra sao?
Bạn mô tả sự khác biệt giữa instance initializer logic và logic thực thi khi một method được gọi sau khi construction hoàn tất như thế nào?
Bạn sẽ dùng Javadoc contracts để nêu preconditions, postconditions và side effects của public method ra sao?
Bạn phân tích khi nào nên trả immutable result object thay vì điền kết quả vào mutable out-parameter object như thế nào?
Bạn giải thích constructor thiết lập trạng thái ban đầu của object theo những bảo đảm nào?
Bạn phân biệt constructor với ordinary method về tên, return type và cách invocation ra sao?
Bạn sẽ xác định lúc nào compiler cung cấp implicit no-argument constructor cho một class như thế nào?
Bạn phân biệt implicit default constructor với constructor không tham số được viết tường minh ra sao?
Bạn sẽ thiết kế overloaded constructors mà không lặp logic khởi tạo hoặc validation giữa chúng ra sao?
Bạn mô tả constructor chaining bằng this(...) khác lời gọi super(...) như thế nào?
Bạn sẽ xác định ràng buộc về thứ tự explicit constructor invocation theo phiên bản Java đang dùng như thế nào?
Bạn phân biệt initialization của superclass và subclass khi tạo instance qua một subclass constructor ra sao?
Bạn sẽ giải thích vì sao constructor của superclass không được kế thừa bởi subclass như thế nào?
Bạn mô tả trách nhiệm của constructor khi nhận một reference nullable theo hợp đồng nào?
Bạn sẽ áp dụng Objects.requireNonNull trong constructor để báo lỗi cấu hình object theo cách nào?
Bạn phân tích nguy cơ gọi overridable method từ constructor trước khi subclass fields được khởi tạo xong như thế nào?
Bạn sẽ thiết kế một base constructor không thực thi logic phụ thuộc vào trạng thái của subclass ra sao?
Bạn giải thích this escape là gì khi constructor truyền tham chiếu đối tượng chưa hoàn tất ra ngoài như thế nào?
Bạn sẽ ngăn việc đăng ký listener nhận this trong constructor khiến callback chạy khi object chưa được khởi tạo đủ ra sao?
Bạn phân biệt factory method kiểm soát quá trình tạo object với public constructor trong việc quản lý invariant như thế nào?
Bạn sẽ áp dụng private constructor và static factory method để hạn chế đường tạo instance theo mục tiêu nào?
Bạn mô tả cách constructor ném exception ảnh hưởng việc object có thể được sử dụng sau đó ra sao?
Bạn sẽ xử lý tài nguyên đã cấp phát một phần nếu constructor không thể hoàn tất theo nguyên tắc nào?
Bạn phân tích rủi ro bắt lỗi constructor rồi trả về object với state chưa hợp lệ từ một factory như thế nào?
Bạn sẽ quyết định khi nào class nên có constructor injection thay vì cho phép set dependencies sau khi tạo ra sao?
Bạn phân biệt telescoping constructors với Builder pattern cho đối tượng có nhiều optional properties ra sao?
Bạn sẽ kiểm thử các trường hợp constructor nhận dữ liệu sai, null và boundary values để bảo vệ invariant ra sao?
Bạn mô tả cách subclass constructor buộc phải chọn một superclass constructor có thể truy cập như thế nào?
Bạn sẽ chẩn đoán lỗi compiler khi superclass không có no-arg constructor và subclass không gọi super đúng cách như thế nào?
Bạn phân tích khác nhau giữa construction thành công và object sẵn sàng sử dụng nếu còn bước initialize phụ thuộc external service như thế nào?
Bạn giải thích encapsulation giúp giới hạn cách external code thay đổi internal state như thế nào?
Bạn phân biệt public, protected, package-private và private access trong Java theo đối tượng được quyền truy cập ra sao?
Bạn sẽ xác định quyền truy cập một member package-private từ class cùng package nhưng khác module như thế nào?
Bạn phân tích vì sao protected member không đồng nghĩa có thể truy cập tự do từ mọi instance subclass ở package khác ra sao?
Bạn sẽ thiết kế API public tối thiểu mà vẫn giữ các helper methods nội bộ có thể tái cấu trúc như thế nào?
Bạn phân biệt private instance field với private static field về phạm vi truy cập và ý nghĩa state như thế nào?
Bạn mô tả Java package ảnh hưởng access control khác Java module exports theo những tầng nào?
Bạn sẽ xác định vì sao một public class trong non-exported package của named module không tự trở thành API cho module khác như thế nào?
Bạn phân tích rủi ro tạo setter public chỉ để unit tests có thể đặt arbitrary internal state như thế nào?
Bạn sẽ sử dụng package-private constructor hoặc factory để kiểm soát ai có thể tạo instance theo hoàn cảnh nào?
Bạn phân biệt getter trả view không thể sửa với getter tạo defensive copy của collection theo khả năng cách ly state ra sao?
Bạn sẽ quyết định khi nào expose behavior method thay vì expose raw field value để giảm coupling như thế nào?
Bạn mô tả nested class có thể truy cập private members của outer class theo quy tắc nào?
Bạn phân biệt non-static inner class với static nested class về tham chiếu implicit tới enclosing instance ra sao?
Bạn sẽ đánh giá rủi ro một inner class sống lâu giữ outer object không được garbage collected như thế nào?
Bạn sẽ sử dụng anonymous class khi cần một implementation ngắn có state so với lambda expression theo nhu cầu nào?
Bạn phân tích vì sao public mutable static field có thể trở thành global shared state khó kiểm soát trong test như thế nào?
Bạn sẽ tổ chức bất biến của một entity nghiệp vụ thông qua phương thức chuyển trạng thái thay vì public fields ra sao?
Bạn phân biệt encapsulation với data hiding và khả năng class vẫn tiết lộ mutable references dù field private ra sao?
Bạn sẽ chọn package boundaries để giảm sự phụ thuộc giữa các classes theo trách nhiệm nào?
Bạn mô tả khi nào cần expose interface thay vì concrete implementation trong public API của một class như thế nào?
Bạn sẽ quyết định modifier phù hợp cho một helper method mà không khóa chặt subclass extension points ra sao?
Bạn phân tích nguy cơ protected mutable field buộc subclass phải biết chi tiết thực thi của base class như thế nào?
Bạn sẽ kiểm thử access modifiers bằng compile-time checks thay vì chỉ nhìn method names như thế nào?
Bạn sẽ đánh giá một class anemic chứa getter/setter nhưng không đóng gói quy tắc nghiệp vụ theo tiêu chí nào?
Bạn giải thích static field thuộc class khác gì instance field thuộc object về số bản sao giá trị như thế nào?
Bạn mô tả static method được gọi không cần object instance nhưng có thể tương tác với static state ra sao?
Bạn sẽ phân biệt static method hiding với instance method overriding trong mô hình kế thừa như thế nào?
Bạn phân tích vì sao static methods không tham gia dynamic dispatch dựa vào runtime object type như thế nào?
Bạn sẽ xác định cách một static field thay đổi ảnh hưởng các instances của cùng class trong một ClassLoader như thế nào?
Bạn phân biệt static final compile-time constant với static final reference được gán một lần nhưng trỏ tới mutable object ra sao?
Bạn sẽ thiết kế class chứa constants để tránh public static mutable state ngoài ý muốn như thế nào?
Bạn mô tả tác động của static final primitive hoặc String constant tới constant inlining khi một library được biên dịch lại như thế nào?
Bạn sẽ nhận diện rủi ro thay đổi giá trị public static final constant nhưng client bytecode cũ vẫn giữ giá trị được inline ra sao?
Bạn phân biệt tác dụng của final đối với một reference field và khả năng thay đổi trạng thái của object mà field đó tham chiếu như thế nào?
Bạn sẽ xác định khi nào final method phù hợp để ngăn subclass thay đổi một behavior quan trọng ra sao?
Bạn mô tả final class giới hạn inheritance nhưng không tự làm tất cả objects của nó immutable như thế nào?
Bạn sẽ đánh giá dùng final cho reference fields trong một class bất biến theo bảo đảm nào của Java memory model?
Bạn phân tích vì sao một final field vẫn có thể trỏ tới List mà các elements thay đổi sau construction ra sao?
Bạn sẽ lựa chọn static factory method thay vì constructor khi cần cache hoặc tái sử dụng instances theo tiêu chí nào?
Bạn phân biệt class-level singleton instance với một giá trị immutable dùng chung về vấn đề concurrency như thế nào?
Bạn sẽ thiết kế lazy initialization của static resource mà không tạo race condition giữa các threads ra sao?
Bạn mô tả initialization-on-demand holder idiom dựa vào class initialization như thế nào?
Bạn phân biệt eager static initialization với lazy initialization theo startup cost và failure modes ra sao?
Bạn sẽ xác định vì sao static state có thể làm unit tests phụ thuộc thứ tự thực thi như thế nào?
Bạn phân tích rủi ro static mutable caches giữ ClassLoader khi một ứng dụng được redeploy như thế nào?
Bạn sẽ tổ chức dependency injection thay vì gọi static service locator để giảm coupling theo cách nào?
Bạn sẽ dùng static utility class cho hành vi thuần túy không cần object state theo điều kiện nào?
Bạn mô tả lý do một utility class thường có private constructor nhằm ngăn instantiation như thế nào?
Bạn phân biệt static nested class với top-level class trong thiết kế builder hoặc helper state như thế nào?
Bạn sẽ đánh giá khi nào dùng enum singleton thay vì tự tạo singleton mutable theo nhu cầu serialization nào?
Bạn mô tả thứ tự khởi tạo static fields và static initializer blocks của một class khi JVM khởi tạo class ra sao?
Bạn phân biệt class loading, linking và initialization theo các giai đoạn trước khi dùng static member như thế nào?
Bạn sẽ xác định những thao tác nào có thể kích hoạt initialization của class theo Java language rules như thế nào?
Bạn phân tích vì sao đọc compile-time constant qua một class có thể không khởi tạo class đó ra sao?
Bạn mô tả cách JVM thực hiện initialization của superclass trước subclass khi class được khởi tạo như thế nào?
Bạn sẽ xác định thứ tự thực thi instance field initializers, instance initializer blocks và constructor body như thế nào?
Bạn phân biệt default zero/null initialization của object với các field initializers do source code khai báo ra sao?
Bạn mô tả khi new một subclass, superclass constructor và subclass initializers phối hợp theo thứ tự nào?
Bạn phân tích vì sao một overridden method gọi từ superclass constructor có thể nhìn thấy subclass field ở giá trị mặc định ra sao?
Bạn sẽ chẩn đoán kết quả bất ngờ khi subclass field initializer chạy sau một lời gọi method từ superclass constructor như thế nào?
Bạn sẽ thiết kế test quan sát thứ tự gọi constructors trong chuỗi A extends B extends C mà không đưa logic nguy hiểm vào constructor ra sao?
Bạn giải thích tác động của static initialization error khi class initializer ném exception như thế nào?
Bạn phân biệt ExceptionInInitializerError lần đầu với NoClassDefFoundError ở lần dùng class sau khi khởi tạo thất bại ra sao?
Bạn sẽ lựa chọn xử lý lỗi external service từ static initializer hay khởi tạo dependency có thể retry theo nguyên tắc nào?
Bạn phân tích rủi ro cyclic initialization giữa hai classes có static fields tham chiếu nhau như thế nào?
Bạn sẽ kiểm tra class initialization deadlock khi nhiều threads đồng thời khởi tạo classes phụ thuộc vòng tròn như thế nào?
Bạn mô tả tại sao thứ tự khai báo instance fields và initializer blocks có thể ảnh hưởng giá trị cuối trong constructor ra sao?
Bạn sẽ xác định cách một explicit assignment trong constructor ghi đè giá trị từ instance field initializer như thế nào?
Bạn phân biệt class initializer với instance initializer về số lần và thời điểm thực thi ra sao?
Bạn sẽ thiết kế object được publish an toàn sang thread khác sau khi constructor đã hoàn tất theo yêu cầu nào?
Bạn phân tích vì sao this escape trong quá trình khởi tạo có thể làm thread khác thấy state chưa đầy đủ ra sao?
Bạn sẽ đánh giá vai trò của final fields và safe publication trong visibility giữa threads theo Java Memory Model như thế nào?
Bạn phân biệt constructor completion với việc một static factory thực hiện validation bổ sung trước khi trả object ra sao?
Bạn sẽ tìm nguyên nhân NullPointerException chỉ xuất hiện khi class được load theo thứ tự đặc biệt do static initialization như thế nào?
Bạn sẽ tránh logic có side effects khó đoán trong static initializer để làm application startup đáng tin cậy ra sao?
Bạn sẽ thiết kế unit tests xác minh initialization behavior mà không phụ thuộc việc JVM đã initialize class từ test trước như thế nào?
Bạn giải thích inheritance biểu diễn quan hệ is-a giữa superclass và subclass khi mô hình hóa nghiệp vụ như thế nào?
Bạn phân biệt extends class với implements interface theo khả năng tái sử dụng state và hành vi ra sao?
Bạn sẽ lựa chọn composition thay inheritance khi quan hệ giữa hai classes là has-a thay vì is-a như thế nào?
Bạn phân tích rủi ro dùng inheritance chỉ để chia sẻ vài helper methods làm hierarchy khó bảo trì ra sao?
Bạn mô tả super được sử dụng để gọi superclass constructor hoặc implementation đã bị override như thế nào?
Bạn sẽ xác định ranh giới override một method với cùng chữ ký và visibility phù hợp theo quy tắc nào?
Bạn phân biệt @Override với việc compiler tự phát hiện override khi annotation không được dùng ra sao?
Bạn giải thích covariant return type được Java cho phép khi overriding instance method như thế nào?
Bạn sẽ xác định vì sao overriding method không được thu hẹp access visibility so với superclass method ra sao?
Bạn phân tích giới hạn của checked exceptions trong overriding một method so với declaration ban đầu như thế nào?
Bạn mô tả dynamic dispatch chọn overridden instance method theo runtime object type như thế nào?
Bạn phân biệt field hiding, static method hiding và method overriding với một reference có static type là superclass ra sao?
Bạn sẽ giải thích khả năng gọi method override khi biến tham chiếu được upcast lên superclass như thế nào?
Bạn sẽ thiết kế subtype tuân thủ hợp đồng của superclass để không vi phạm Liskov Substitution Principle ra sao?
Bạn phân tích trường hợp subclass thắt chặt preconditions làm client dùng superclass API bị hỏng như thế nào?
Bạn sẽ quyết định khi nào một superclass method nên final để giữ bất biến của một thuật toán ra sao?
Bạn mô tả abstract class khác concrete class ở khả năng khởi tạo và nghĩa vụ implement methods như thế nào?
Bạn phân biệt abstract method với default method trong interface theo khả năng cung cấp implementation ra sao?
Bạn sẽ đánh giá template method pattern khi muốn base class kiểm soát workflow nhưng cho phép vài extension points như thế nào?
Bạn phân tích rủi ro public overridable method được gọi trong constructor hoặc method bảo vệ invariant ra sao?
Bạn sẽ sử dụng instanceof pattern matching để xử lý kiểu an toàn nhưng đánh giá khi nào cần đa hình thay if-else ra sao?
Bạn phân biệt downcast hợp lệ với ClassCastException khi runtime object không thuộc subtype mong đợi ra sao?
Bạn sẽ xác định cách Object.getClass và instanceof khác nhau trong kiểm tra exact runtime type như thế nào?
Bạn sẽ tổ chức hierarchy để tránh kiểm tra hàng loạt concrete subtypes trong mỗi business method ra sao?
Bạn phân tích rủi ro protected state làm subclass phụ thuộc quá mạnh vào cấu trúc internal superclass như thế nào?
Bạn sẽ kiểm thử một subtype thay thế base type trong nhiều workflows mà không làm sai business invariants ra sao?
Bạn giải thích Object.equals và toán tử == khác nhau như thế nào khi so sánh hai object references?
Bạn phân biệt mặc định Object.equals với một implementation so sánh value của domain objects ra sao?
Bạn sẽ xác định khi nào domain entity nên so sánh theo identity key thay vì toàn bộ mutable fields như thế nào?
Bạn mô tả hợp đồng reflexive, symmetric, transitive và consistent của equals như thế nào?
Bạn phân tích vì sao equals dùng instanceof không cẩn thận trong inheritance có thể phá tính đối xứng hoặc bắc cầu ra sao?
Bạn sẽ đánh giá dùng getClass so với instanceof trong equals khi class có subclasses theo yêu cầu nào?
Bạn giải thích vì sao override equals thường phải override hashCode theo hợp đồng nào?
Bạn sẽ xác định rủi ro hashCode dựa trên mutable field khi object đã nằm trong HashSet hoặc làm key HashMap ra sao?
Bạn mô tả Objects.equals và Objects.hash giúp xử lý null hoặc tổng hợp hash với giới hạn nào như thế nào?
Bạn phân biệt value equality với reference identity khi dùng Map keys theo đặc tính nào?
Bạn sẽ thiết kế equals/hashCode cho value object chứa collection mà vẫn giữ bất biến nội dung ra sao?
Bạn phân tích vì sao phương thức equals không nên có side effects hoặc phụ thuộc thời gian thực ra sao?
Bạn sẽ đánh giá cách Object.toString hỗ trợ logging mà không vô tình in password hoặc thông tin nhạy cảm như thế nào?
Bạn mô tả khi nào nên override toString để phản ánh state phục vụ debug thay vì cung cấp serialization format ra sao?
Bạn phân biệt Object.clone với copy constructor hoặc factory copy theo tính rõ ràng và khả năng kiểm soát ra sao?
Bạn sẽ giải thích vì sao default Object.clone thường tạo bản sao nông đối với nested mutable objects như thế nào?
Bạn phân tích nguy cơ Cloneable khiến API khó mô tả các invariants cần áp dụng sau sao chép như thế nào?
Bạn sẽ thiết kế deep copy cho object graph có cycles mà không lặp vô hạn hoặc làm mất shared references ra sao?
Bạn phân biệt identityHashCode với hashCode do class override theo ý nghĩa nào?
Bạn sẽ sử dụng IdentityHashMap trong tình huống cần key comparison dựa trên object identity thay vì equals như thế nào?
Bạn phân tích vì sao thứ tự hiển thị của HashMap không nên được coi là thuộc tính ổn định của một object model ra sao?
Bạn sẽ kiểm thử equals/hashCode bằng các instances độc lập, null và mutations phù hợp như thế nào?
Bạn sẽ đánh giá khi nào nên dùng record để có value-based equals/hashCode thay vì viết class nhiều boilerplate ra sao?
Bạn giải thích immutable object là gì và khác với biến final về khả năng thay đổi state sau construction như thế nào?
Bạn sẽ thiết kế immutable class bằng private final fields và kiểm soát constructor parameters như thế nào?
Bạn phân tích vì sao một class có mọi fields final vẫn chưa chắc immutable nếu chứa mutable references ra sao?
Bạn sẽ dùng defensive copy ở constructor và getters khi object chứa mutable List, Date hoặc byte array ra sao?
Bạn phân biệt Collections.unmodifiableList với List.copyOf về snapshot và chia sẻ dữ liệu nguồn như thế nào?
Bạn sẽ kiểm tra một immutable wrapper có thật sự cách ly nested mutable elements được giữ trong collection không ra sao?
Bạn phân tích vì sao trả trực tiếp byte[] nội bộ qua getter phá khả năng bất biến của class như thế nào?
Bạn sẽ chọn LocalDate và BigDecimal thay các mutable hoặc không chính xác types theo ngữ nghĩa dữ liệu nào?
Bạn sẽ tạo method withX để trả về instance mới khi cần thay đổi giá trị của một immutable object ra sao?
Bạn mô tả lợi ích và chi phí của immutable objects trong concurrent programming về thread safety và allocations như thế nào?
Bạn phân biệt shallow immutability với deep immutability trong object graph nhiều tầng như thế nào?
Bạn sẽ xác định các điều kiện để class được coi là effectively immutable dù có private cache field như thế nào?
Bạn phân tích vì sao lazy caching trong immutable-looking class vẫn cần thiết kế concurrency an toàn ra sao?
Bạn sẽ bảo vệ invariant của một Money value object khi currency và amount phải được kiểm tra cùng nhau như thế nào?
Bạn sẽ sử dụng constructor validation để đảm bảo immutable object không bao giờ tồn tại ở trạng thái không hợp lệ ra sao?
Bạn phân biệt immutable value object với mutable entity khi domain model cần identity và lifecycle khác nhau ra sao?
Bạn sẽ quyết định khi nào dùng builder để tạo immutable object nhiều fields thay constructor dài ra sao?
Bạn mô tả builder pattern có thể ngăn published object chưa hợp lệ bằng validate tại build như thế nào?
Bạn phân tích rủi ro builder giữ reference mutable rồi truyền nguyên nó vào immutable object ra sao?
Bạn sẽ kiểm thử tính bất biến bằng cách thay đổi arguments gốc sau construction và sửa dữ liệu nhận từ getter ra sao?
Bạn sẽ cân nhắc serialize/deserialize immutable class mà vẫn chạy validation như thế nào?
Bạn phân biệt thread-safe publication của immutable object với tình trạng chưa-safe của object thoát ra trước khi constructor kết thúc ra sao?
Bạn sẽ thiết kế immutable configuration snapshot để thay thế shared mutable settings giữa nhiều threads ra sao?
Bạn phân tích khi nào immutable class cần final để ngăn subclass đưa vào mutable state ngoài hợp đồng như thế nào?
Bạn sẽ đánh giá trade-off giữa immutable copies và memory pressure khi xử lý collection rất lớn ra sao?
Bạn giải thích record trong Java được thiết kế để biểu diễn nhóm dữ liệu có cấu trúc theo semantic nào?
Bạn phân biệt record declaration với một class thường tự khai báo fields, constructor, accessors và equals/hashCode ra sao?
Bạn mô tả record components được phản ánh trong canonical constructor và accessor methods như thế nào?
Bạn sẽ xác định khác biệt giữa canonical constructor và compact constructor khi validation record components ra sao?
Bạn sẽ thiết kế compact constructor kiểm tra invariants rồi chuẩn hóa dữ liệu trước khi record được tạo như thế nào?
Bạn phân tích vì sao record component chứa List mutable vẫn không làm record trở thành deeply immutable ra sao?
Bạn sẽ thực hiện defensive copy trong record constructor khi cần lưu collection snapshot theo cách nào?
Bạn phân biệt accessor method của record với getter theo quy ước JavaBeans trong thư viện reflection như thế nào?
Bạn sẽ xác định khi nào record có thể thêm static fields, instance methods hoặc custom methods theo ngữ nghĩa nào?
Bạn mô tả giới hạn record trong việc khai báo thêm instance fields ngoài record components như thế nào?
Bạn phân biệt record kế thừa java.lang.Record với khả năng implements interfaces theo quy tắc nào?
Bạn sẽ giải thích tại sao một record không thể extends một concrete superclass theo cơ chế Java nào?
Bạn phân tích rủi ro sử dụng record làm JPA entity khi framework mong đợi no-arg constructor, proxy hoặc mutable identity ra sao?
Bạn sẽ lựa chọn record cho DTO trả API hoặc event payload thay một domain entity có lifecycle dài theo tiêu chí nào?
Bạn sẽ thiết kế validation record constructor để tránh object mang giá trị null không hợp lệ như thế nào?
Bạn phân biệt generated equals/hashCode/toString của record với cách class thông thường tự triển khai ra sao?
Bạn sẽ xác định khi nào override một accessor của record là hợp lý nhưng không làm mất contract của component như thế nào?
Bạn phân tích vì sao custom implementation của equals trong record cần cân nhắc value semantics dự kiến như thế nào?
Bạn sẽ dùng pattern matching với record patterns ở phiên bản Java phù hợp theo yêu cầu compiler nào?
Bạn phân biệt destructuring record pattern với truy cập accessor thủ công về khả năng đọc và kiểm tra kiểu như thế nào?
Bạn sẽ kiểm thử serialize một record qua JSON framework và đánh giá hỗ trợ constructor binding của phiên bản framework ra sao?
Bạn giải thích sealed class giới hạn trực tiếp những subclasses hoặc implementors được phép theo quan hệ nào?
Bạn phân biệt sealed, non-sealed và final trong một class hierarchy theo quyền mở rộng ra sao?
Bạn sẽ dùng permits clause để công bố các direct permitted subclasses theo thiết kế nào?
Bạn mô tả các quy tắc về module hoặc package áp dụng cho permitted subclasses của sealed class như thế nào?
Bạn sẽ xác định vì sao một subclass trực tiếp của sealed class cần khai báo final, sealed hoặc non-sealed ra sao?
Bạn phân tích rủi ro dùng non-sealed mở lại hierarchy không kiểm soát khi đang muốn duy trì tập subtype hữu hạn ra sao?
Bạn sẽ thiết kế sealed interface cho các trạng thái kết quả nghiệp vụ mà vẫn cho phép mỗi case có fields riêng như thế nào?
Bạn phân biệt sealed interface kết hợp records với một class có enum field chứa trạng thái theo khả năng model hóa dữ liệu nào?
Bạn sẽ sử dụng pattern matching switch trên sealed hierarchy để kiểm tra exhaustiveness theo compiler version phù hợp như thế nào?
Bạn phân tích vì sao thêm một permitted subtype mới có thể làm switch exhaustive của client source cần được cập nhật ra sao?
Bạn sẽ đánh giá binary compatibility khi thay đổi permitted subclasses so với việc thêm một method vào base class như thế nào?
Bạn sẽ chọn sealed hierarchy, enum hoặc composition theo nhu cầu hạn chế trạng thái hợp lệ nào?
Bạn phân tích rủi ro sealed hierarchy khiến mô hình khó mở rộng bởi plugin bên ngoài theo yêu cầu sản phẩm như thế nào?
Bạn sẽ thiết kế test xác minh những subtype không được phép không thể kế thừa sealed class ở compile time ra sao?
Nếu hai variables cùng trỏ một mutable object và kết quả thay đổi bất ngờ, bạn sẽ phân tích aliasing và reference assignment như thế nào?
Nếu constructor nhận List rồi caller thay đổi nó sau khi tạo object, bạn sẽ chỉnh encapsulation để tránh mutable state leak ra sao?
Nếu getter trả mảng byte nội bộ khiến một test sửa được dữ liệu của object, bạn sẽ sửa API và test như thế nào?
Nếu subclass override method được gọi từ superclass constructor rồi nhận field null, bạn sẽ phân tích initialization order như thế nào?
Nếu class initializer lỗi lần đầu và lần sau nhận NoClassDefFoundError, bạn sẽ điều tra static initialization root cause ra sao?
Nếu constructor chain không compile do superclass thiếu no-arg constructor, bạn sẽ thiết kế explicit super invocation như thế nào?
Nếu public static mutable cache làm tests phụ thuộc thứ tự, bạn sẽ tách state hoặc thiết kế lifecycle rõ ràng ra sao?
Nếu method nhận object nhưng việc gán parameter sang object mới không ảnh hưởng caller, bạn sẽ giải thích pass-by-value như thế nào?
Nếu subclass che field của superclass và hai methods thấy giá trị khác nhau, bạn sẽ xác định field hiding và reference type ra sao?
Nếu Map lookup thất bại sau khi một mutable key bị chỉnh sửa, bạn sẽ phân tích equals/hashCode và tính bất biến của key như thế nào?
Nếu equals trên hai subclasses không đối xứng, bạn sẽ thiết kế lại chiến lược so sánh hoặc hierarchy như thế nào?
Nếu static final List vẫn bị thêm elements từ nhiều threads, bạn sẽ phân biệt final reference với immutable collection ra sao?
Nếu một inner class sống lâu hơn enclosing instance và gây heap leak, bạn sẽ cân nhắc static nested class như thế nào?
Nếu một object dùng file handle vẫn còn reachable sau close, bạn sẽ phân biệt lifecycle tài nguyên với garbage collection ra sao?
Nếu một class Money được xem là immutable nhưng vẫn cho cập nhật amount và currency rời rạc qua setters, bạn sẽ thiết kế lại value object như thế nào?
Nếu record chứa mutable List và hashCode thay đổi sau construction, bạn sẽ tạo snapshot và xử lý nested elements ra sao?
Nếu một record dùng làm entity bị framework từ chối vì thiếu default constructor, bạn sẽ phân biệt DTO/value object với entity ra sao?
Nếu sealed interface mới thêm subtype làm switch expression không compile, bạn sẽ đánh giá exhaustiveness và migration strategy ra sao?
Nếu module khác muốn extends sealed class nhưng không nằm trong permitted set, bạn sẽ thay đổi hierarchy hoặc extension API như thế nào?
Nếu cần mô hình hóa một domain gồm entity có identity, immutable value object, record DTO và sealed results, bạn sẽ phân chia class responsibilities, initialization và access control như thế nào?
