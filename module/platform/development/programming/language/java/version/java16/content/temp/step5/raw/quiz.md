Câu 1: Khi nào record là lựa chọn phù hợp hơn một lớp JavaBean thông thường?
A. Với đối tượng cần nhiều setter để sửa trạng thái trong suốt vòng đời nghiệp vụ.
B. Với lớp cơ sở dự kiến cho nhiều implementation kế thừa trực tiếp về sau.
C. Với kiểu cần thêm trường instance vào object theo cấu hình từng request.
D. Với đối tượng mang dữ liệu có cấu trúc cố định và ngữ nghĩa dựa trên giá trị.
Đáp án đúng: D

Câu 2: Java tự sinh các phương thức nào cho một record không tự định nghĩa chúng?
A. compareTo, clone và finalize dựa trên thứ tự các record component khai báo.
B. equals, hashCode và toString dựa trên các record component đã khai báo.
C. getters dạng getX, setters dạng setX và constructor không tham số.
D. equals dựa trên tham chiếu và hashCode dựa trên địa chỉ lưu trong heap.
Đáp án đúng: B

Câu 3: Một record chứa component List<String> bảo đảm mức bất biến nào?
A. Các phần tử trong List cũng được đóng băng, kể cả object mutable.
B. Record tự sao chép sâu mọi List trước khi lưu vào field bên trong.
C. Record biến mọi List đầu vào thành collection bất biến lúc khởi tạo.
D. Tham chiếu component không đổi; nội dung List vẫn có thể bị sửa.
Đáp án đúng: D

Câu 4: Trong compact canonical constructor của record, cách kiểm tra dữ liệu nào phù hợp?
A. Gán trực tiếp lại các field final thay vì làm việc với tham số truyền vào.
B. Hoãn kiểm tra đến lần đầu accessor được gọi để tránh chi phí khởi tạo.
C. Xác thực hoặc chuẩn hóa tham số trước khi compiler gán chúng vào field.
D. Đưa mọi kiểm tra vào setter được Java tự sinh cho record component.
Đáp án đúng: C

Câu 5: Một record có được khai báo thêm field instance tùy ý bên ngoài components không?
A. Có; chỉ cần đánh dấu field thêm là final để compiler chấp nhận.
B. Không; record cũng cấm mọi static field dùng chung ở cấp class.
C. Có; field instance mới sẽ được thêm vào equals và hashCode tự động.
D. Không có field instance bổ sung; vẫn có thể khai báo field static.
Đáp án đúng: D

Câu 6: Record có thể tham gia quan hệ kiểu nào trong Java?
A. Chỉ có thể dùng độc lập, không tham gia bất kỳ interface nào.
B. Record có thể implements interface nhưng không extends class khác.
C. Có thể extends class nghiệp vụ nhưng không được implements interface.
D. Có thể kế thừa trực tiếp nhiều class nếu mọi component là final.
Đáp án đúng: B

Câu 7: Hai record cùng kiểu chứa hai mảng khác nhau nhưng cùng phần tử có chắc equals trả true không?
A. Có; record tự so sánh sâu từng phần tử mảng để xác định bằng nhau.
B. Có; chỉ cần mảng có cùng kích thước thì record được xem bằng nhau.
C. Không; các mảng vẫn dùng equality theo tham chiếu mặc định.
D. Không; record luôn so sánh object identity thay vì mọi component.
Đáp án đúng: C

Câu 8: Cách khai báo nào được Java 16 cho phép với một record mang dữ liệu tổng quát?
A. Record có thể khai báo tham số kiểu và được dùng như kiểu generic.
B. Record chỉ hỗ trợ generic cho method mà cấm tham số kiểu của record.
C. Record có thể khai báo type parameter nhưng không thể có component.
D. Record chỉ chấp nhận tham số kiểu khi có thêm superclass riêng.
Đáp án đúng: A

Câu 9: Ngoài những thành viên sinh tự động, record có thể khai báo thành viên nào?
A. Constructor không tham số mà không cần ủy quyền tới canonical constructor.
B. Setter cho từng component để tự cập nhật field final sau khởi tạo.
C. Method nghiệp vụ và thành viên static vẫn có thể khai báo.
D. Superclass tự chọn cùng các field instance bổ sung theo từng đối tượng.
Đáp án đúng: C

Câu 10: Khi chuẩn hóa một tham số trong compact constructor của record, điều gì xảy ra?
A. Compiler gán field trước phần thân rồi bỏ qua mọi thay đổi tham số.
B. Giá trị mới chỉ nằm trong biến cục bộ, còn field luôn giữ input ban đầu.
C. Compiler dùng tham số đã chuẩn hóa để gán vào component fields.
D. Record bắt buộc gọi một setter để lưu tham số đã thay đổi vào field.
Đáp án đúng: C

Câu 11: Accessor mặc định cho component tên total của record có tên nào?
A. isTotal(), bất kể total có phải là boolean hay không.
B. total(), cùng tên với component, không có tiền tố get.
C. readTotal(), theo chuẩn truy cập field bất biến của record.
D. getTotal(), theo chuẩn getter JavaBean được sinh tự động.
Đáp án đúng: B

Câu 12: Record component được thể hiện bằng field và accessor như thế nào?
A. Field private final và accessor public có tên tương ứng component.
B. Field package-private volatile và getter theo chuẩn JavaBean.
C. Field public mutable và accessor protected do compiler tạo sẵn.
D. Field protected final và setter public để cập nhật sau constructor.
Đáp án đúng: A

Câu 13: Mô tả nào đúng về quan hệ kế thừa của record?
A. Record trực tiếp kế thừa Object và có thể làm superclass tùy ý.
B. Record trực tiếp kế thừa java.lang.Record và bản thân là final.
C. Record kế thừa Enum để compiler tự quản lý tập component cố định.
D. Record kế thừa Serializable nên mặc định có thể ghi thành byte.
Đáp án đúng: B

Câu 14: Vì sao một entity cần thay đổi trạng thái thường không phù hợp với record?
A. Record không thể được truyền làm tham số của repository generic.
B. Record luôn phải được tạo trong một module Java hoàn toàn riêng.
C. Record không thể có method nào phục vụ logic nghiệp vụ của entity.
D. Record không cho cập nhật component trên cùng instance bằng setter.
Đáp án đúng: D

Câu 15: Khi record nhận component có thể null nhưng nghiệp vụ yêu cầu không null, cần lưu ý gì?
A. Đưa kiểm tra vào hashCode vì nó luôn chạy trước mọi accessor.
B. Không cần kiểm tra vì mọi component record mặc định non-null.
C. Cần tự xác thực invariant; record không cấm null theo mặc định.
D. Chỉ cần triển khai equals để constructor tự từ chối giá trị null.
Đáp án đúng: C

Câu 16: Khi dùng Java serialization chuẩn với record, phát biểu nào đúng?
A. Phải implements Serializable; khôi phục qua các component.
B. Record luôn implements Serializable dù không khai báo interface.
C. Record cấm mọi hình thức native serialization ngay từ Java 16.
D. Record chỉ được serialize sau khi khai báo constructor không tham số.
Đáp án đúng: A

Câu 17: Một constructor phụ không phải canonical của record phải bảo đảm điều gì?
A. Gọi constructor của một superclass nghiệp vụ trước khi đọc components.
B. Không được khai báo constructor phụ nếu record đã có compact constructor.
C. Tự gán các field final trực tiếp mà không cần gọi constructor nào.
D. Phải ủy quyền tới canonical constructor qua chuỗi constructor.
Đáp án đúng: D

Câu 18: Mốc phiên bản ổn định nào mô tả đúng hai tính năng record và sealed classes?
A. Cả record và sealed classes đều chính thức từ Java 21.
B. Record chính thức ở Java 16; sealed classes ở Java 17.
C. Record chính thức từ Java 17; sealed classes chính thức từ Java 16.
D. Cả record và sealed classes đều chính thức từ Java 16.
Đáp án đúng: B

Câu 19: Pattern matching cho instanceof trong Java 16 giúp xử lý tình huống nào?
A. Gộp kiểm tra kiểu và biến đã thu hẹp vào cùng biểu thức.
B. Tự chuyển mọi object sang kiểu đích ngay cả khi phép kiểm tra sai.
C. Thay kiểm tra kiểu runtime bằng so sánh chuỗi tên class.
D. Thay đổi kiểu thực tế của object khi biểu thức instanceof trả true.
Đáp án đúng: A

Câu 20: Khi operand của instanceof pattern nhận giá trị null, điều gì xảy ra?
A. Phép kiểm tra ném NullPointerException trước khi xét kiểu pattern.
B. Biến pattern nhận null và vẫn được dùng như instance của kiểu đích.
C. Phép kiểm tra trả true nếu pattern là một kiểu tham chiếu bất kỳ.
D. Trả false; biến pattern không được gắn trong nhánh thất bại.
Đáp án đúng: D

Câu 21: Trong điều kiện obj instanceof String s && s.isBlank(), tại sao vế phải hợp lệ?
A. Vế phải chỉ chạy khi instanceof thành công và s đã được gắn kiểu.
B. Biến s là biến cục bộ của cả method ngay khi điều kiện được khai báo.
C. Vế phải luôn chạy trước để Java quyết định kiểu của biến s.
D. Toán tử && tự chuyển obj thành String kể cả khi test kiểu sai.
Đáp án đúng: A

Câu 22: Vì sao obj instanceof String s || s.isBlank() không dùng được như mong đợi?
A. Vế phải luôn được bỏ qua nên compiler coi s là biến không sử dụng.
B. Vế phải có thể chạy khi kiểm tra kiểu thất bại, nên s chưa được gắn.
C. Toán tử || không hỗ trợ biểu thức instanceof trong Java 16.
D. instanceof String chỉ được kết hợp với toán tử && trong mọi ngữ cảnh.
Đáp án đúng: B

Câu 23: Sau kiểm tra !(obj instanceof String s) thì return ngay nếu đúng, điều gì đúng?
A. Biến s chỉ tồn tại nếu chương trình đang ở trong nhánh return.
B. Có thể dùng s sau if vì nhánh không match đã return.
C. Compiler luôn yêu cầu cast thủ công sau mọi instanceof phủ định.
D. Biến s chỉ được sử dụng ngay trong biểu thức phủ định ban đầu.
Đáp án đúng: B

Câu 24: Trong nhánh else của if (obj instanceof String s), biến s có dùng được không?
A. Không; nhánh else không bảo đảm obj đã khớp kiểu String.
B. Không; vì instanceof pattern chỉ dùng được trong biểu thức switch.
C. Có; s luôn được khai báo trước cả hai nhánh của lệnh if.
D. Có; s được gắn null khi đối tượng không khớp String.
Đáp án đúng: A

Câu 25: Biến s trong instanceof String s có mặc định là final từ Java 16 không?
A. Không; biến pattern không mặc định final và bị giới hạn scope.
B. Có; mọi biến pattern phải là final và không thể gán lại.
C. Không; biến pattern có thể được truy cập từ bất kỳ method nào.
D. Có; compiler tạo field final mới trên object đang được kiểm tra.
Đáp án đúng: A

Câu 26: Vì sao không thể kiểm tra runtime bằng instanceof List<String> cho object tùy ý?
A. Vì List<String> chỉ là kiểu hợp lệ bên trong khai báo record.
B. Do type erasure, List<String> không reifiable tại runtime.
C. Vì Java 16 chưa có cơ chế instanceof cho bất kỳ collection nào.
D. Vì instanceof chỉ hỗ trợ class, không hỗ trợ các interface generic.
Đáp án đúng: B

Câu 27: Nếu biến value đã có kiểu tĩnh String, pattern value instanceof String s gây gì?
A. Compiler cho phép nhưng tự động chuyển s thành biến static final.
B. Compiler luôn tạo s rồi trả true cho cả trường hợp value là null.
C. Compiler đổi value thành Object trước khi thực hiện phép kiểm tra.
D. Báo lỗi biên dịch vì String đã là subtype của pattern String.
Đáp án đúng: D

Câu 28: Sau if (obj instanceof String s), khi nào có thể gọi s.length() an toàn?
A. Ở mọi dòng sau if vì s được khai báo trong phạm vi method.
B. Trong cả else vì compiler gắn chuỗi rỗng cho biến không match.
C. Ở nhánh mà flow đã chứng minh instanceof match thành công.
D. Chỉ trước if vì biến pattern không tồn tại trong thân nhánh.
Đáp án đúng: C

Câu 29: Câu nào đúng về phạm vi biến pattern khi kết hợp điều kiện bằng toán tử AND?
A. Biến luôn tồn tại trong cả hai nhánh bất kể điều kiện kết hợp.
B. Biến được chuyển thành field của record nếu có một record operand.
C. Biến chỉ có ở đường chạy đã xác nhận match thành công.
D. Biến được gắn trước khi đánh giá các toán hạng khác của biểu thức.
Đáp án đúng: C

Câu 30: Khi hai nhánh instanceof dùng cùng tên biến pattern và có vùng scope chồng nhau, Java xử lý thế nào?
A. Compiler bỏ cả hai biến và tự thêm phép cast trong từng nhánh.
B. Báo xung đột khai báo nếu hai biến pattern có scope chồng.
C. Compiler tự đổi tên một biến pattern để tránh mọi xung đột.
D. Compiler hợp nhất hai biến thành Object để dùng ở cả hai nhánh.
Đáp án đúng: B

Câu 31: Pattern instanceof giải quyết được hạn chế nào của cast thủ công sau kiểm tra kiểu?
A. Tự bảo đảm mọi field bên trong object đều khác null.
B. Tự xác thực toàn bộ dữ liệu nghiệp vụ trước khi xử lý object.
C. Biến mọi interface thành sealed hierarchy để chặn subtype lạ.
D. Liên kết kết quả kiểm tra kiểu với biến cụ thể ngay trong nhánh.
Đáp án đúng: D

Câu 32: Trong if (!(obj instanceof String s) || s.length() == 0), vì sao truy cập s ở vế phải hợp lệ?
A. Toán tử || luôn gắn s bằng null nếu toán hạng đầu là true.
B. Java tự ép obj sang String trước khi áp dụng toán tử phủ định.
C. Vế phải chỉ được đánh giá khi phép instanceof bên trong đã match.
D. Vế phải được Java chạy trước để kiểm tra String có rỗng hay không.
Đáp án đúng: C

Câu 33: Khi dùng Java 16, tính năng nào được dùng ổn định mà không cần preview?
A. Pattern matching cho instanceof; pattern switch chỉ chuẩn hóa ở Java 21.
B. Unnamed patterns trong switch; pattern instanceof vẫn chỉ là incubator.
C. Pattern switch trên mọi kiểu; instanceof pattern chỉ chuẩn hóa ở Java 21.
D. Record patterns lồng nhau; instanceof pattern chỉ xuất hiện ở Java 21.
Đáp án đúng: A

Câu 34: Stream.toList() được bổ sung ở Java 16 trả về danh sách có thuộc tính gì?
A. Luôn trả ArrayList có thể thêm phần tử tùy ý sau khi kết thúc stream.
B. Luôn trả LinkedList có khả năng thay đổi cấu trúc qua ListIterator.
C. Không cho thay đổi cấu trúc bằng các thao tác thêm hoặc xóa phần tử.
D. Tự động làm mọi object phần tử trở thành bất biến sâu sau collect.
Đáp án đúng: C

Câu 35: Khi Stream.toList() nhận phần tử null, cách xử lý nào đúng?
A. Phần tử null luôn bị loại bỏ trước khi danh sách được tạo.
B. Danh sách chỉ chứa null nếu stream chạy ở chế độ parallel.
C. Chấp nhận phần tử null; danh sách vẫn không cho sửa cấu trúc.
D. Phương thức luôn ném NullPointerException ngay khi gặp null.
Đáp án đúng: C

Câu 36: Với Collectors.toList(), có bảo đảm danh sách kết quả luôn mutable không?
A. Không; API không cam kết lớp List hay khả năng sửa đổi.
B. Không; collector luôn tạo immutable list như List.of.
C. Có; luôn là ArrayList mutable để dùng với mọi stream.
D. Có; luôn là LinkedList mutable khi source đã có thứ tự.
Đáp án đúng: A

Câu 37: Stream.toList() xử lý thứ tự phần tử thế nào với stream có encounter order?
A. Tự sắp xếp phần tử theo thứ tự tự nhiên trước khi trả về.
B. Luôn đảo ngược thứ tự để tối ưu thao tác thêm phần tử.
C. Giữ encounter order của nguồn khi tạo danh sách kết quả.
D. Chỉ giữ thứ tự nếu stream được tạo từ một TreeSet.
Đáp án đúng: C

Câu 38: Có nên phụ thuộc lớp triển khai cụ thể của List do Stream.toList() trả về không?
A. Có; kết quả luôn dùng lớp triển khai của collection nguồn.
B. Không; API không cam kết một kiểu triển khai List cụ thể.
C. Không; vì List trả về không thể lưu bất kỳ phần tử nào.
D. Có; kết quả luôn được bảo đảm là java.util.ArrayList.
Đáp án đúng: B

Câu 39: Stream.mapMulti() phù hợp nhất với kiểu biến đổi nào?
A. Cho phép phát không, một hay nhiều đầu ra vào consumer.
B. Mỗi đầu vào luôn được gom vào Map theo key tự suy ra.
C. Mỗi đầu vào phải tạo đúng một đầu ra của cùng một kiểu dữ liệu.
D. Mỗi đầu vào phải sinh một Stream mới rồi nối bằng flatMap.
Đáp án đúng: A

Câu 40: Khi so mapMulti với flatMap, lợi ích tiềm năng của mapMulti là gì?
A. Bảo đảm tự sắp xếp đầu ra tăng dần mà không cần comparator.
B. Bỏ mọi bước kiểm tra kiểu generic nhờ thực hiện tại runtime.
C. Phát nhiều giá trị mà không cần tạo Stream con cho từng input.
D. Cam kết tăng tốc cho mọi pipeline bất kể loại workload.
Đáp án đúng: C

Câu 41: Một lời gọi mapMulti không phát phần tử nào qua consumer sẽ có kết quả gì?
A. Input đó khiến toàn bộ stream dừng như lệnh terminal.
B. Input đó được chuyển thành null trong danh sách kết quả.
C. Input đó tự động được giữ lại như một phần tử mặc định.
D. Input đó không đóng góp phần tử nào vào stream đầu ra.
Đáp án đúng: D

Câu 42: Khi cần sinh luồng int chuyên biệt từ mapMulti, phương thức nào phù hợp?
A. flatMapToLong, vì Java không hỗ trợ nhánh int của mapMulti.
B. mapToInt, bắt buộc mỗi đầu vào sinh nhiều giá trị int.
C. mapMultiToInt, để phát các giá trị int vào IntStream.
D. mapMulti, luôn trả IntStream nếu consumer phát Integer.
Đáp án đúng: C

Câu 43: Sau khi gọi toList() trên một Stream, có thể chạy tiếp một terminal operation trên chính Stream đó không?
A. Có; toList chỉ trả một view và không chạm vào stream.
B. Có; stream tự khởi động lại nếu source là một List.
C. Không; stream đã được tiêu thụ bởi terminal operation.
D. Không; vì toList luôn đóng cả collection nguồn bên ngoài.
Đáp án đúng: C

Câu 44: List từ Stream.toList() chứa các object mutable có tự khóa trạng thái object không?
A. Có; các object sẽ được JVM sao chép thành record tương ứng.
B. Không; vì toList thực chất trả một mảng chứ không phải List.
C. Có; List tạo deep copy và chuyển mọi field thành final.
D. Không; chỉ cấu trúc List cố định, object bên trong vẫn mutable.
Đáp án đúng: D

Câu 45: Khi dùng mapMulti với parallel stream, việc ghi vào một ArrayList dùng chung có rủi ro gì?
A. Java sẽ sao chép mọi state bên ngoài cho từng phần tử nguồn.
B. Có thể race nếu state bên ngoài không được đồng bộ đúng.
C. Không có rủi ro vì mọi callback mapMulti luôn chạy tuần tự.
D. Đầu ra tự chuyển thành synchronized list trước khi được phát.
Đáp án đúng: B

Câu 46: Tại sao gọi Stream.toList() vẫn có thể kích hoạt các phép map trước đó?
A. Vì toList là terminal operation làm pipeline lười được đánh giá.
B. Vì các phép map luôn chạy ngay lúc được khai báo trong pipeline.
C. Vì toList dùng reflection để đọc dữ liệu chưa được xử lý.
D. Vì mỗi stream luôn thực thi tất cả intermediate operation hai lần.
Đáp án đúng: A

Câu 47: Thay đổi đóng gói mặc định đáng chú ý của Java 16 ảnh hưởng điều gì?
A. Hạn chế truy cập phản chiếu vào các package nội bộ JDK.
B. Toàn bộ application package không cần module-info vẫn bị đóng kín.
C. Mọi class public từ JDK bị cấm truy cập khi dùng classpath.
D. Mọi package JDK đều tự được exports cho mọi module ngoài JVM.
Đáp án đúng: A

Câu 48: Khi framework cần deep reflection vào một package JDK bị đóng, --add-opens có vai trò gì?
A. Cho phép JVM bỏ qua mọi kiểm tra kiểu dữ liệu của native memory.
B. Xuất mọi package trong module thành public API để dùng khi compile.
C. Biến package thành một module độc lập có thể được tự động nạp.
D. Mở deep reflection cho package và bên nhận quyền đã chỉ định.
Đáp án đúng: D

Câu 49: --add-exports khác --add-opens chủ yếu ở điểm nào?
A. Luôn cho phép truy cập cả private field và private constructor qua reflection.
B. Cho truy cập kiểu public ở package được nêu, không tự mở private.
C. Chỉ dùng để đổi tên module trong runtime image được tạo bởi jlink.
D. Buộc mọi class được exports phải có constructor mặc định public.
Đáp án đúng: B

Câu 50: Khi module A requires module B nhưng package API của B chưa được exports, chuyện gì xảy ra?
A. B tự động mở toàn bộ package cho A khi Java phát hiện requires.
B. B chuyển mọi package bị đóng thành package-private trong A.
C. A được phép gọi mọi public class của B chỉ nhờ requires đã khai báo.
D. A đọc được B nhưng package chưa exports vẫn không truy cập được.
Đáp án đúng: D

Câu 51: Công cụ nào trong JDK có thể hỗ trợ tìm phụ thuộc đến JDK internal APIs?
A. javadoc, để phát hiện mọi reflective access tạo động tại runtime.
B. jshell, để mở mọi package private bằng một interactive session.
C. jpackage, để tự thay API nội bộ bằng API công khai tương ứng.
D. jdeps giúp phát hiện phụ thuộc vào các API nội bộ của JDK.
Đáp án đúng: D

Câu 52: Nếu unit test qua IDE chạy được nhưng bản Java 16 production báo InaccessibleObjectException, cần kiểm tra gì?
A. Đối chiếu VM options và reflective access của thư viện.
B. Sự khác biệt về tên biến cục bộ trong code đã biên dịch giống nhau.
C. Sự khác biệt về thứ tự package import vốn bị xóa ở runtime.
D. Sự khác biệt về cú pháp record accessor giữa IDE và production.
Đáp án đúng: A

Câu 53: Vì sao không nên xem --add-opens là giải pháp kiến trúc dài hạn cho thư viện cũ?
A. Nó bảo đảm mọi internal API vẫn giữ nguyên hành vi qua các JDK.
B. Đây là ngoại lệ truy cập, cần hướng tới API được hỗ trợ.
C. Nó thay thế việc kiểm tra binary compatibility của dependency.
D. Nó tự làm JVM chuyển về phiên bản Java thấp hơn để tương thích.
Đáp án đúng: B

Câu 54: Khi dùng JPMS, exports và opens đáp ứng hai nhu cầu nào khác nhau?
A. exports cung cấp quyền sửa field private; opens chỉ cho public methods.
B. exports chỉ dùng cho native libraries; opens chỉ dùng cho classpath.
C. exports cho API thông thường, opens cho deep reflection.
D. exports tự động tạo JAR; opens tự tạo module path cho ứng dụng.
Đáp án đúng: C

Câu 55: jpackage, chính thức trong Java 16, phục vụ mục đích nào?
A. Tạo application image hoặc native installer cho ứng dụng Java.
B. Biên dịch mọi source Java thành mã máy độc lập với JVM.
C. Tạo module descriptor từ tất cả class trên classpath.
D. Tự thay mọi thư viện native bằng bytecode Java thuần.
Đáp án đúng: A

Câu 56: jpackage khác với jlink chủ yếu ở chức năng nào?
A. jpackage chỉ kiểm tra dependency; jlink quản lý cửa sổ ứng dụng.
B. jpackage đóng gói ứng dụng; jlink tạo ảnh runtime tùy biến.
C. jpackage thay thế Java compiler; jlink thay thế garbage collector.
D. jpackage tối ưu method JIT; jlink tạo source code Java từ JAR.
Đáp án đúng: B

Câu 57: Muốn tạo bộ cài Windows và Linux bằng jpackage, giả định nào là phù hợp?
A. Bộ cài luôn độc lập với kiến trúc CPU nếu ứng dụng chỉ dùng Java.
B. Cần công cụ và môi trường build phù hợp với từng nền tảng.
C. Có thể tạo mọi bộ cài native trên mọi OS mà không cần công cụ khác.
D. Chỉ cần chạy jpackage trên bất kỳ JVM nào với cùng một tên file.
Đáp án đúng: B

Câu 58: Một ứng dụng đóng gói bằng jpackage không tìm thấy lớp main lúc khởi động; nên kiểm tra gì?
A. Chỉ cần tăng kích thước heap vì class main được tạo khi GC chạy.
B. Thay mọi record trong ứng dụng bằng JavaBean có constructor rỗng.
C. Tắt strong encapsulation vì lớp main luôn nằm trong JDK internals.
D. Kiểm tra cấu hình launcher, lớp main/module và các artifact.
Đáp án đúng: D

Câu 59: Khi phân phối runtime riêng kèm ứng dụng bằng jpackage, việc bảo trì nào vẫn cần?
A. Chỉ cần cập nhật mã nguồn; mọi runtime đã phát hành tự nhận vá.
B. Chỉ cần đổi version manifest mà không cần đóng gói runtime mới.
C. Không cần cập nhật JDK vì runtime bên trong bộ cài là bất biến.
D. Vẫn phải cập nhật JDK và phát hành lại bộ cài khi cần vá.
Đáp án đúng: D

Câu 60: Một gói cài được tạo thành công nhưng thiếu thư viện native khi chạy; điều gì cần rà soát?
A. Chỉ thuật toán ZGC vì thư viện native được GC tự tải khi cần.
B. Chỉ cách sắp xếp thứ tự import của lớp Java trong source code.
C. Rà soát tài nguyên và thư viện native đi kèm gói trên OS đích.
D. Chỉ số lượng thành viên được khai báo trong các record DTO.
Đáp án đúng: C

Câu 61: Elastic Metaspace được đưa vào Java 16 nhằm cải thiện điều gì?
A. Giúp hoàn trả bộ nhớ metadata lớp không dùng cho OS hiệu quả hơn.
B. Thay thế heap bằng Metaspace để lưu mọi instance ứng dụng Java.
C. Bỏ hoàn toàn nhu cầu class unloading khỏi vòng đời ứng dụng.
D. Cam kết mọi class metadata được giải phóng ngay sau mỗi method.
Đáp án đúng: A

Câu 62: ZGC concurrent thread-stack processing trong Java 16 chủ yếu hướng tới điều gì?
A. Tắt hoàn toàn garbage collection ở những ứng dụng nhiều thread.
B. Đưa thêm xử lý stack sang pha concurrent để giảm pause của ZGC.
C. Buộc các thread dừng cho đến khi toàn bộ heap được quét xong.
D. Chuyển mọi Java thread sang virtual thread để loại bỏ thread stacks.
Đáp án đúng: B

Câu 63: Unix-domain socket channels được bổ sung trong Java 16 phù hợp nhất cho việc nào?
A. Tự đồng bộ hóa dữ liệu socket giữa các container khác host.
B. Kết nối HTTP công khai giữa hai máy chủ qua địa chỉ IP Internet.
C. Gửi datagram UDP qua router để phát hiện máy trong cùng subnet.
D. IPC giữa các tiến trình cùng host qua socket địa chỉ cục bộ.
Đáp án đúng: D

Câu 64: Khi một ứng dụng Java dùng Unix-domain socket trong môi trường nhiều hệ điều hành, cần chú ý gì?
A. Hỗ trợ nền tảng, đường dẫn socket và quyền của tiến trình.
B. Chỉ cấu hình số cổng TCP vì mọi Unix socket đều gắn với cổng IP.
C. Chỉ phiên bản DNS vì socket luôn được xác định bằng tên miền.
D. Chỉ chu kỳ GC vì JVM tự quyết định đường dẫn socket khi kết nối.
Đáp án đúng: A
