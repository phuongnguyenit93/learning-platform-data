Câu 1: JEP 467 đưa điểm mới nào vào Javadoc từ JDK 23?
A. Hỗ trợ nội dung Markdown trong Javadoc.
B. Chuyển mọi comment thành file README.
C. Thay Javadoc truyền thống hoàn toàn bằng HTML.
D. Tự chạy mọi ví dụ mã trong Javadoc.
Đáp án đúng: A

Câu 2: Dòng Markdown documentation comment trong Java bắt đầu thế nào?
A. Dùng một dấu /* ở đầu mỗi dòng mã.
B. Dùng hai dấu // trước nội dung tài liệu.
C. Dùng dấu /// trước mỗi dòng tài liệu.
D. Dùng ba dấu ### trước mỗi dòng mã.
Đáp án đúng: C

Câu 3: Giữ một dòng trống trong cùng khối /// bằng cách nào?
A. Chèn dòng /** mở một comment riêng.
B. Chèn dòng hoàn toàn trống không có ///.
C. Chèn dòng /// không có nội dung theo sau.
D. Chèn dòng // giữa hai phần mô tả.
Đáp án đúng: C

Câu 4: Hai nhóm /// ngăn cách bởi dòng trống trước cùng method được xử lý sao?
A. Cả hai nhóm đều xuất hiện ở tài liệu method.
B. Nhóm gần method nhất là comment được chọn.
C. Nhóm ở xa method nhất được ưu tiên chọn.
D. Hai nhóm được ghép thành một comment chung.
Đáp án đúng: B

Câu 5: Javadoc truyền thống /** ... */ có còn dùng được ở JDK 23 không?
A. Có, vẫn được hỗ trợ bên cạnh kiểu ///.
B. Không, comment dạng /** chỉ dùng cho javac.
C. Không, bắt buộc chuyển sang /// từ JDK 23.
D. Có, nhưng chỉ chạy với tùy chọn preview.
Đáp án đúng: A

Câu 6: Một file Java có thể trộn hai kiểu comment Javadoc không?
A. Không, Markdown chỉ tồn tại ở file doc-files.
B. Có, kiểu /// và /** cùng tồn tại trong file.
C. Không, mỗi file phải chọn chính xác một kiểu.
D. Có, nhưng chỉ trong file package-info.java.
Đáp án đúng: B

Câu 7: Liên kết Markdown trong /// tới kiểu String dùng ký pháp nào?
A. Annotation tài liệu theo dạng @String.
B. Wildcard import theo dạng [java.lang.*].
C. Đường dẫn source theo dạng String.java.
D. Tham chiếu liên kết theo dạng [String].
Đáp án đúng: D

Câu 8: Tham chiếu tới String.length() từ Markdown Javadoc dùng gì?
A. Dùng link tới member dạng [String::length()].
B. Dùng link tới member dạng [String.length()].
C. Dùng link tới member dạng [String#length()].
D. Dùng link tới member dạng [String->length()].
Đáp án đúng: C

Câu 9: Các thẻ @param và @return trong Markdown Javadoc có còn hợp lệ không?
A. Có, vẫn là block tag được Javadoc nhận diện.
B. Có, nhưng được in nguyên văn mà không xử lý.
C. Không, phải thay thế bằng HTML table tương ứng.
D. Không, chỉ còn hỗ trợ trong comment /**.
Đáp án đúng: A

Câu 10: Nếu đặt {@link String} vào code span Markdown, Javadoc làm gì?
A. Tạo link API như khi nằm ngoài code span.
B. Bỏ nội dung code span khỏi trang được tạo.
C. Thay dòng code span bằng đường dẫn class.
D. Hiển thị mã nguyên văn, không tạo link API.
Đáp án đúng: D

Câu 11: Để hiển thị khối mã nhiều dòng trong ///, nên dùng cú pháp gì?
A. Dùng bảng HTML bắt buộc cho mọi code.
B. Dùng heading code với ba dấu #.
C. Dùng fenced code với ba dấu backtick.
D. Dùng comment với ba dấu gạch / trong mã.
Đáp án đúng: C

Câu 12: Kiểu bảng nào Javadoc Markdown hỗ trợ trực tiếp?
A. Bảng đơn giản theo GitHub Flavored Markdown.
B. Bảng YAML dạng object với dấu hai chấm.
C. Bảng XML dạng phần tử table và row.
D. Bảng SQL theo cú pháp CREATE TABLE nguyên bản.
Đáp án đúng: A

Câu 13: Một file .md bổ sung cho package nên đặt ở đâu?
A. Thư mục bin thuộc bộ cài đặt JDK.
B. Thư mục META-INF thuộc runtime classpath.
C. Thư mục build/classes chứa file .class.
D. Thư mục doc-files thuộc source package.
Đáp án đúng: D

Câu 14: Tệp doc-files/guide.md được standard doclet xử lý thế nào?
A. In nguyên văn mà không xử lý định dạng.
B. Biên dịch từng đoạn thành các class độc lập.
C. Đọc như nội dung của một tài liệu Markdown.
D. Lưu như dữ liệu constant pool của bytecode.
Đáp án đúng: C

Câu 15: Muốn khai báo API deprecated trong Markdown Javadoc, cần gì?
A. Chỉ thẻ @deprecated trong /// là đủ.
B. Chỉ hậu tố Deprecated trong tên method.
C. Dùng annotation @Deprecated trên API.
D. Chỉ heading Deprecated ở đầu comment.
Đáp án đúng: C

Câu 16: Có nhiều documentation comments trước cùng khai báo thì chọn gì?
A. Mọi comment đều bị từ chối vì trùng lặp.
B. Mọi comment luôn ghép thành một tài liệu.
C. Comment có số lượng dòng lớn nhất được dùng.
D. Comment sát khai báo nhất được dùng.
Đáp án đúng: D

Câu 17: Heading của Markdown Javadoc thường được viết thế nào?
A. Dùng :: kèm khoảng trắng trước tên tiêu đề.
B. Dùng @ kèm khoảng trắng trước tên tiêu đề.
C. Dùng # kèm khoảng trắng trước tên tiêu đề.
D. Dùng $ kèm khoảng trắng trước tên tiêu đề.
Đáp án đúng: C

Câu 18: Javadoc xử lý thụt lề chung sau /// thế nào?
A. Loại hết whitespace trong mọi code block.
B. Giữ nguyên toàn bộ thụt lề của các dòng.
C. Loại phần whitespace thụt lề phụ chung.
D. Thay mọi tab của source thành một dấu cách.
Đáp án đúng: C

Câu 19: Có thể dùng HTML xen vào Markdown Javadoc không?
A. Không, bất kỳ thẻ HTML nào cũng bị từ chối.
B. Có, nhưng chỉ trong module-info.java.
C. Không, chỉ Markdown văn bản được chấp nhận.
D. Có, HTML có thể xuất hiện trong Markdown.
Đáp án đúng: D

Câu 20: Inline tag nào tiếp tục tạo liên kết API trong kiểu comment ///?
A. Dùng {@attach ...} để chèn tên module.
B. Dùng {@import ...} thay cho liên kết.
C. Thẻ {@link ...} vẫn được Javadoc dùng.
D. Dùng {@execute ...} để mở URL của class.
Đáp án đúng: C

Câu 21: Phần tóm tắt API trong Javadoc thường xuất phát từ đâu?
A. Heading Markdown cuối cùng trong comment.
B. Câu tóm tắt đầu của phần mô tả chính.
C. Tên class file vừa được javac tạo ra.
D. Dòng @return cuối cùng trong comment.
Đáp án đúng: B

Câu 22: Mô tả tham số method trong /// bằng thẻ nào?
A. Dùng @module tương ứng với từng tham số.
B. Dùng @param tương ứng với từng tham số.
C. Dùng @import tương ứng với từng tham số.
D. Dùng @export tương ứng với từng tham số.
Đáp án đúng: B

Câu 23: Javadoc Markdown hỗ trợ thẻ {@snippet ...} không?
A. Có, thẻ inline Javadoc vẫn được xử lý.
B. Có, nhưng bắt buộc bật --enable-preview.
C. Không, snippet đã bị thay bằng file CSV.
D. Không, snippet chỉ hoạt động với /**.
Đáp án đúng: A

Câu 24: Liên kết tới website bên ngoài từ Markdown Javadoc nên dùng gì?
A. Lệnh requires trong module-info.java.
B. Tên file class trong javac classpath.
C. Annotation Java định nghĩa @WebLink ở class.
D. Liên kết Markdown có địa chỉ URL phù hợp.
Đáp án đúng: D

Câu 25: Dùng /// với javadoc JDK 22 gặp vấn đề nào?
A. Chỉ cần bật -Xmx thì Javadoc 22 hiểu ///.
B. Javadoc 22 chưa nhận Markdown kiểu ///.
C. Chỉ cần đổi tên file Java thành .md.
D. Javadoc 22 tự nhận /// như Java 23.
Đáp án đúng: B

Câu 26: Thư mục xuất tài liệu HTML của javadoc được chỉ bằng gì?
A. Tùy chọn -d kèm đường dẫn thư mục đích.
B. Tùy chọn -encoding kèm tên thư mục đích.
C. Tùy chọn -source kèm đường dẫn thư mục đích.
D. Tùy chọn -cp kèm đường dẫn thư mục đích.
Đáp án đúng: A

Câu 27: Tùy chọn nào dùng để kiểm tra vấn đề trong Javadoc?
A. Dùng -Xdoclint để kiểm tra lỗi tài liệu.
B. Dùng -Xmx để kiểm tra lỗi tài liệu.
C. Dùng -XX:+UseZGC để kiểm tra lỗi comment.
D. Dùng --module-path để kiểm tra lỗi comment.
Đáp án đúng: A

Câu 28: Muốn trỏ sang tài liệu API của thư viện khác, nên dùng gì?
A. Tùy chọn -source dẫn tới tài liệu API ngoài.
B. Tùy chọn -classpath dẫn tới tài liệu ngoài.
C. Tùy chọn -jar dẫn tới tài liệu API bên ngoài.
D. Tùy chọn -link dẫn tới tài liệu API bên ngoài.
Đáp án đúng: D

Câu 29: Muốn dùng tệp overview.md làm trang tổng quan Javadoc, dùng gì?
A. Dùng -verbose để chỉ đường dẫn tới file .md.
B. Dùng -overview để chỉ đường dẫn tới file .md.
C. Dùng -version để chỉ đường dẫn tới file .md.
D. Dùng -source để chỉ đường dẫn tới file .md.
Đáp án đúng: B

Câu 30: Một link Markdown tới method không tồn tại có thể kiểm tra qua đâu?
A. Kiểm tra chẩn đoán sau khi chạy javadoc.
B. Chỉ chạy chương trình chính của ứng dụng.
C. Chỉ đếm số dòng của các Java source file.
D. Chỉ so độ dài file README đã biên dịch.
Đáp án đúng: A

Câu 31: Khi dự án thay custom doclet cũ bằng ///, cần kiểm tra điều gì?
A. Doclet có hiểu dạng Markdown comment mới không.
B. Doclet có tự tối ưu bytecode Java khi build không.
C. Doclet có tự thay module-info khi build không.
D. Doclet có tự chạy code Java trong comment không.
Đáp án đúng: A

Câu 32: Với flag -XX:+UseZGC trên JDK 23, collector chọn mode nào?
A. Serial GC được bật vì mode ZGC bị bỏ.
B. ZGC phân thế hệ làm chế độ mặc định.
C. ZGC một thế hệ luôn được chọn mặc định.
D. Parallel GC được bật theo cấu hình code.
Đáp án đúng: B

Câu 33: Tuyên bố nào đúng về ZGC và collector mặc định trong JDK 23?
A. ZGC chỉ dùng được với các ứng dụng có JPMS.
B. ZGC chỉ dùng khi project bật mọi preview.
C. ZGC không tự là collector mặc định của JVM.
D. ZGC là collector mặc định trên mọi JVM JDK 23.
Đáp án đúng: C

Câu 34: Generational ZGC khai thác đặc tính nào của các đối tượng?
A. Tuổi thọ giữa các đối tượng thường khác nhau.
B. Mọi đối tượng đều có kích thước bằng nhau.
C. Mọi đối tượng đều phải nằm ngoài Java heap.
D. Mọi đối tượng đều tồn tại tới khi JVM dừng.
Đáp án đúng: A

Câu 35: Khi benchmark ZGC cho API production, nên đo gì?
A. GC pause, p99 latency và chi phí CPU.
B. Số class, tên module và tổng import.
C. Số heading Javadoc và file tài liệu.
D. Số dòng mã nguồn và số file .jar.
Đáp án đúng: A

Câu 36: Flag nào bật Unified Logging cho thông tin GC của JVM?
A. Dùng -Xdoclint khi khởi động tiến trình.
B. Dùng --module-path khi khởi động tiến trình.
C. Dùng -sourcepath khi khởi động tiến trình.
D. Dùng -Xlog:gc* khi khởi động tiến trình.
Đáp án đúng: D

Câu 37: Đánh giá đổi collector sang ZGC cần so sánh yếu tố nào?
A. Số lệnh trong file manifest của ứng dụng.
B. Độ trễ, throughput và chi phí tài nguyên.
C. Số lượng dòng comment Java của dự án.
D. Kích thước của mã nguồn chưa biên dịch.
Đáp án đúng: B

Câu 38: Khi container giới hạn bộ nhớ, nên quan sát gì với ZGC?
A. Tổng số các lệnh import trong project.
B. Heap, native memory và RSS của tiến trình.
C. Tên file, package và phiên bản thư viện.
D. Kích thước tài liệu HTML trong Javadoc.
Đáp án đúng: B

Câu 39: Stream Gatherers ở JDK 23 khi nào trở thành API chuẩn?
A. Được chuẩn hóa từ JDK 21 cùng virtual thread.
B. Được chuẩn hóa từ JDK 17 cùng sealed class.
C. Được chuẩn hóa từ JDK 24 sau các đợt preview.
D. Được chuẩn hóa ngay trong Java 23 preview.
Đáp án đúng: C

Câu 40: Phép biến đổi trung gian với Gatherer được gọi thế nào?
A. Dùng Stream.toList với ClassLoader tương ứng.
B. Dùng Stream.collect với ClassFile tương ứng.
C. Dùng Stream.concat với MethodHandle tương ứng.
D. Dùng Stream.gather với Gatherer tương ứng.
Đáp án đúng: D

Câu 41: Gatherers.windowFixed(3) trên 1,2,3,4,5,6,7 cho gì?
A. Các nhóm [1], [2], [3] và [4,5,6,7].
B. Các nhóm [1,2], [3,4] và [5,6,7].
C. Các nhóm [1,2,3], [4,5,6] và [7].
D. Các nhóm [1,2,3] và [4,5,6] thôi.
Đáp án đúng: C

Câu 42: Gatherers.windowSliding(3) trên 1,2,3,4 tạo cửa sổ gì?
A. Cửa sổ [1,2,3] và [2,3,4] giao nhau.
B. Cửa sổ [1,3,4] và [1,2,4] lệch nhau.
C. Cửa sổ [1,2] và [3,4] không giao nhau.
D. Cửa sổ [1,2,3] và [4] không giao nhau.
Đáp án đúng: A

Câu 43: Gatherers.scan áp dụng lên stream có thứ tự cho kết quả nào?
A. Một danh sách lệnh bytecode sau khi build.
B. Một giá trị tổng duy nhất khi luồng kết thúc.
C. Một danh sách phần tử đã xóa mọi bản sao.
D. Các giá trị tích lũy sau mỗi phần tử mới.
Đáp án đúng: D

Câu 44: Gatherers.fold khác scan ở điểm nào?
A. Phát bản sao của toàn bộ phần tử đầu vào.
B. Phát các cửa sổ trượt ở mỗi bước.
C. Phát kết quả tích lũy sau từng phần tử.
D. Phát một kết quả tổng hợp khi kết thúc.
Đáp án đúng: D

Câu 45: Gatherers.mapConcurrent bảo đảm đặc điểm nào?
A. Chạy mọi tác vụ tuần tự trên một thread cố định.
B. Chạy song song và đảo thứ tự kết quả đầu ra.
C. Giới hạn tác vụ đồng thời nhưng giữ thứ tự kết quả.
D. Chạy mọi tác vụ không giới hạn độ đồng thời.
Đáp án đúng: C

Câu 46: Gatherers.mapConcurrent(0, mapper) sẽ làm gì?
A. Ném IllegalArgumentException với mức 0.
B. Trả Stream rỗng mà không có ngoại lệ.
C. Tự đổi sang mức 1 rồi thực hiện tuần tự.
D. Tự chọn mức theo số CPU đang hoạt động.
Đáp án đúng: A

Câu 47: Custom Gatherer thích hợp với loại xử lý nào?
A. Cấp quyền deep reflection cho một package.
B. Biến đổi trung gian có trạng thái qua nhiều phần tử.
C. Sinh bảng cơ sở dữ liệu với chú thích Javadoc.
D. Thêm exports vào module-info của ứng dụng.
Đáp án đúng: B

Câu 48: Nếu Gatherer không có combiner có ích, cần lưu ý gì khi dùng parallel?
A. Luôn tạo thread mới cho mỗi bản ghi đầu vào.
B. Luôn tự chạy song song mọi integrator của gatherer.
C. Luôn phát sinh lỗi khi Stream có nhiều phần tử.
D. Không mặc định tối ưu song song việc gather dữ liệu.
Đáp án đúng: D

Câu 49: Class-File API từng preview ở Java 23 chuẩn hóa từ bản nào?
A. Được chuẩn hóa ngay tại JDK 23 preview.
B. Được chuẩn hóa từ JDK 17, cùng sealed class.
C. Được chuẩn hóa từ JDK 21, cùng record pattern.
D. Được chuẩn hóa từ JDK 24, dùng Class-File API.
Đáp án đúng: D

Câu 50: Package chuẩn của Class-File API trên JDK mới là gì?
A. Dùng java.nio.classloader của java.net.http.
B. Dùng java.lang.classfile thuộc module java.base.
C. Dùng java.util.bytecode thuộc module java.sql.
D. Dùng javax.classfile.parser của jdk.compiler.
Đáp án đúng: B

Câu 51: ClassFile.of().parse(bytes) tạo ra đối tượng kiểu gì?
A. ClassModel mô tả cấu trúc class file đã đọc.
B. ClassLoader có quyền tải bytecode của class.
C. MethodHandle có thể chạy method main của class.
D. Object instance được khởi tạo ngay từ bytecode.
Đáp án đúng: A

Câu 52: Mô hình ClassModel trên API hiện đại có thuộc tính nào?
A. Chỉ lưu tên class, không có metadata khác.
B. Mutable và ghi tự động vào class file gốc.
C. Bất biến và có thể đọc metadata theo nhu cầu.
D. Tự chuyển mọi bytecode thành Java source.
Đáp án đúng: C

Câu 53: ClassFile.build dùng cho mục đích nào?
A. Đổi file HTML thành tài liệu Markdown.
B. Sinh một class file thành dữ liệu mảng byte.
C. Chạy method main của class vừa được đọc.
D. Cho phép reflection vào các private member.
Đáp án đúng: B

Câu 54: ClassFile.transformClass làm việc gì cùng ClassTransform?
A. Tạo byte class file đã biến đổi theo quy tắc.
B. Biên dịch file nguồn chưa được tạo trên đĩa.
C. Đổi tên mọi package mà project đang dùng.
D. Chuyển object MethodHandle thành Java thread.
Đáp án đúng: A

Câu 55: Module import declarations có trạng thái nào ở JDK 25?
A. Vẫn là incubator không có cú pháp ổn định.
B. Chỉ còn thẻ @import của công cụ Javadoc.
C. Đã bị gỡ khỏi trình biên dịch Java hiện đại.
D. Đã thành tính năng ngôn ngữ chính thức ở JDK 25.
Đáp án đúng: D

Câu 56: import module java.base ở JDK 25 hỗ trợ điều gì?
A. Mở toàn bộ private package để reflection tùy ý.
B. Thêm requires vào module-info của mọi module.
C. Nhập tên kiểu public từ các package được export.
D. Tải trước mọi class của java.base khi chạy.
Đáp án đúng: C

Câu 57: import module và requires trong module-info khác nhau thế nào?
A. Một bên xóa package, một bên thay class loader.
B. Cả hai chỉ khai báo quyền reflection private.
C. Cả hai chỉ tác động khi chạy javadoc tạo HTML.
D. Một bên nhập tên kiểu, một bên nêu phụ thuộc module.
Đáp án đúng: D

Câu 58: Flexible Constructor Bodies ổn định từ JDK 25 cho phép điều gì?
A. Tự biến constructor thành phương thức static.
B. Kiểm tra dữ liệu trước super mà chưa truy cập this.
C. Dùng this tự do trước lời gọi super của lớp cha.
D. Bỏ mọi lời gọi superclass constructor trong Java.
Đáp án đúng: B

Câu 59: Compact Source Files and Instance Main Methods thành chuẩn ở JDK nào?
A. JDK 17, cùng tính năng sealed classes.
B. JDK 23, ngay lần công bố preview mới.
C. JDK 25, sau nhiều đợt thử nghiệm preview.
D. JDK 21, cùng tính năng virtual thread.
Đáp án đúng: C

Câu 60: Scoped Values trong JDK 25 giúp chia sẻ kiểu dữ liệu nào?
A. Tự gán volatile vào mọi field của object.
B. Ngữ cảnh bất biến trong phạm vi được ràng buộc.
C. Tự thay mọi List thành immutable collection.
D. Trạng thái global mutable cho mọi Java thread.
Đáp án đúng: B

Câu 61: Structured concurrency trên JDK 26 có trạng thái sử dụng nào?
A. Tự kích hoạt trong mọi ứng dụng virtual thread.
B. Chỉ là API nội bộ của công cụ javadoc.
C. Đã thành ngôn ngữ ổn định từ JDK 17.
D. Vẫn là API preview theo tài liệu JDK 26.
Đáp án đúng: D

Câu 62: Dùng --release 23 thì API chuẩn hóa ở JDK 24 có sẵn để biên dịch không?
A. Có, khi file source được lưu dưới UTF-8.
B. Không, vì API chưa có ở mức release 23.
C. Có, chỉ cần có file module-info.java.
D. Có, vì compiler mới mở mọi API hiện có.
Đáp án đúng: B

Câu 63: Khi một tính năng Java 23 ở preview, cần xác minh điều kiện nào?
A. Chỉ nội dung các comment Javadoc đã sinh.
B. Xác nhận JDK và cờ preview thích hợp.
C. Chỉ file manifest và tên class main.
D. Chỉ phiên bản IDE và số lượng Java source.
Đáp án đúng: B

Câu 64: Nâng code từ preview cũ sang API chuẩn hóa nên thực hiện cách nào?
A. Đối chiếu API JDK đích và chạy kiểm thử lại.
B. Chỉ dùng reflection để bỏ qua mọi lỗi API.
C. Giữ nguyên lời gọi cũ vì preview luôn tương thích.
D. Chỉ thay số phiên bản trong tài liệu README.
Đáp án đúng: A
