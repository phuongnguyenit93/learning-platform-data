Câu 1. Trong javac, thứ tự khái quát nào mô tả pipeline biên dịch Java?
A. Sinh file .class trước khi kiểm tra kiểu của nguồn
B. Kiểm tra luồng dữ liệu sau khi JVM đã nạp class
C. Parse nguồn, phân tích ngữ nghĩa rồi sinh bytecode
D. Sinh bytecode xong mới phân giải các symbol nguồn
Đáp án đúng: C

Câu 2. Với biểu thức Java thiếu dấu ngoặc đóng, giai đoạn nào thường báo lỗi?
A. Attribution phát hiện xung đột generic type của biểu thức
B. Bytecode generator báo thiếu StackMapTable trong class
C. Linker JVM phát hiện lỗi khi nạp class đã sinh
D. Parser phát hiện cú pháp không tạo thành cấu trúc hợp lệ
Đáp án đúng: D

Câu 3. Gán String vào biến int mà không có chuyển đổi hợp lệ bị chặn ở đâu?
A. Enter kiểm tra cú pháp của cặp dấu ngoặc trong source
B. Attribution thực hiện kiểm tra kiểu của biểu thức
C. Lowering quyết định local variable đã gán hay chưa
D. JVM linker quyết định kiểu khi chương trình đã chạy
Đáp án đúng: B

Câu 4. Giai đoạn enter trong javac thường thực hiện công việc nào?
A. Phát bytecode cho toàn bộ method ngay lúc đọc token
B. Ghi các khai báo vào symbol table để phân giải tên
C. Kiểm tra exception path và definite assignment
D. Chuyển enhanced for thành vòng lặp có iterator
Đáp án đúng: B

Câu 5. Lỗi local variable có nhánh sử dụng trước khi được gán liên quan tới gì?
A. Phân giải overload dựa trên kiểu đối số method call
B. Biến đổi generic type thành kiểu đã bị erasure
C. Chạy annotation processor để tạo class còn thiếu
D. Phân tích definite assignment trên control-flow
Đáp án đúng: D

Câu 6. Khi xử lý enhanced for, bước lowering trong compiler thường làm gì?
A. Giữ nguyên câu lệnh for-each dưới dạng Java source
B. Biên dịch toàn bộ collection thành một annotation
C. Gộp mọi vòng lặp thành method native của JVM
D. Hạ cú pháp for-each thành vòng lặp tương đương
Đáp án đúng: D

Câu 7. Với javac -d build/classes, tùy chọn -d kiểm soát điều gì?
A. Đường dẫn classpath của dependency JAR đầu vào
B. -d chọn thư mục lưu các file .class được tạo
C. Thư mục chứa source code của các module khác
D. Thư mục riêng tìm annotation processor trên disk
Đáp án đúng: B

Câu 8. Để javac tìm type trong JAR thông thường ở classpath, nên dùng gì?
A. Tùy chọn -cp hoặc -classpath trỏ tới JAR cần thiết
B. Tùy chọn -d trỏ tới JAR sẽ được tạo từ source
C. Tùy chọn -g trỏ tới JAR chứa thư viện của JDK
D. Tùy chọn -encoding trỏ tới JAR chứa class đã có
Đáp án đúng: A

Câu 9. Trong biên dịch module Java, --module-path được dùng nhằm mục đích nào?
A. Chỉ định đường tìm các module dependency đã có
B. Chỉ định nơi lưu source code được processor tạo ra
C. Chỉ định vị trí các file class được compiler xuất ra
D. Chỉ định module chứa implementation của javac
Đáp án đúng: A

Câu 10. Khi biên dịch cây nguồn gồm nhiều named module, option nào thường hữu ích?
A. --module-path trực tiếp liệt kê source của mỗi package
B. --processor-path chỉ định source tree của các module
C. --module-source-path xác định nơi đặt nguồn từng module
D. --release tạo các file module-info.java từ source
Đáp án đúng: C

Câu 11. Trong module-info.java, requires com.acme.lib mang ý nghĩa nào?
A. Module đang khai báo phụ thuộc đọc module com.acme.lib
B. Mọi public package trong module đều export ra bên ngoài
C. Module com.acme.lib tự có quyền reflection vào private
D. Compiler sinh artifact JAR mang tên com.acme.lib
Đáp án đúng: A

Câu 12. Trong module-info.java, exports com.acme.api thường cho phép điều gì?
A. Module khác reflection vào private field của toàn package
B. Module hiện tại đọc mọi dependency có cùng package name
C. JVM tự động mở toàn bộ package để deep reflection
D. Module khác truy cập public type trong package được export
Đáp án đúng: D

Câu 13. Muốn javac chạy trên JDK mới nhưng chỉ dùng API Java 17, option nào hợp lý?
A. --release 17 kiểm soát cả API và class file target
B. --target 17 kiểm soát API thư viện được javac nhìn thấy
C. -source 17 tự khóa boot class path vào Java 17
D. -parameters 17 giới hạn API theo phiên bản release
Đáp án đúng: A

Câu 14. Nếu chỉ dùng -source 11 -target 11 trên JDK mới, rủi ro chính là gì?
A. Bytecode luôn có major version mới nhất của JDK đang dùng
B. Java source 11 không thể compile cùng annotation processor
C. Có thể gọi nhầm API JDK mới mà runtime 11 không có
D. Module path mặc định sẽ bỏ qua mọi dependency JAR cũ
Đáp án đúng: C

Câu 15. Để ngăn dùng nhầm API mới khi target Java 11, nên cấu hình gì?
A. javac --release 11 thay vì chỉ source/target 11
B. javac -g:vars để ẩn các API chỉ có trên JDK mới
C. javac -d 11 để ghi compatibility metadata vào class
D. javac -parameters để Java reflection bỏ API mới
Đáp án đúng: A

Câu 16. Class file major version 61 được tạo cho phiên bản Java nào?
A. Java 17 tương ứng với class file major version 61
B. Java 11 tương ứng với class file major version 61
C. Java 8 tương ứng với class file major version 61
D. Java 21 tương ứng với class file major version 61
Đáp án đúng: A

Câu 17. Ở đầu file .class hợp lệ, magic number JVM là giá trị nào?
A. 0xDEADBEEF xác định định dạng Java class file
B. 0xCAFEBABE là magic number của file .class
C. 0xFEEDFACE xác định định dạng Java class file
D. 0x504B0304 xác định định dạng Java class file
Đáp án đúng: B

Câu 18. Tùy chọn javap nào trực tiếp disassemble bytecode instruction của method?
A. javap -c in bytecode instruction của method
B. javap -p chỉ hiển thị các annotation của method
C. javap -s chỉ in constant pool và access flags
D. javap -l chỉ chuyển bytecode thành Java source
Đáp án đúng: A

Câu 19. Để xem constant pool và thuộc tính chi tiết của class file, nên dùng gì?
A. javap -c chỉ cung cấp toàn bộ constant pool metadata
B. javap -p bật chế độ tạo WSDL từ public method
C. javap -v in constant pool và attribute chi tiết
D. javap -s xuất mọi method thành Java source hoàn chỉnh
Đáp án đúng: C

Câu 20. Khi dùng javac -g:none, thông tin gì thường bị lược bỏ trong class file?
A. Thông tin JVM method descriptor để runtime gọi được method
B. Metadata debug tùy chọn như line number và local variable
C. Thông tin constant pool dùng liên kết các symbolic reference
D. Các access flag cần để xác minh visibility của class
Đáp án đúng: B

Câu 21. Muốn reflection lấy tên parameter thực thay vì arg0 khi biên dịch, option nào phù hợp?
A. javac -g:none bắt buộc reflection đọc tên tham số source
B. javac -Xlint:all bật runtime lookup tên method parameter
C. javac -Werror tự bổ sung metadata tham số còn thiếu
D. javac -parameters ghi tên tham số method vào metadata
Đáp án đúng: D

Câu 22. javac -Xlint thường có tác dụng gì trong chẩn đoán build?
A. Bật thêm cảnh báo của compiler theo nhóm được chọn
B. Biến mọi warning thành compile error như -Werror
C. Chỉ xuất file class khi tất cả annotation đều runtime
D. Tắt annotation processing nhưng vẫn sinh bytecode
Đáp án đúng: A

Câu 23. Với javac -Werror, điều nào xảy ra khi có warning?
A. Warning được bỏ qua vì chỉ error mới chặn compilation
B. Warning được sửa tự động bằng code formatter của javac
C. Warning chỉ xuất ra khi chạy class bằng Java runtime
D. Warning có thể làm compilation thất bại theo chính sách
Đáp án đúng: D

Câu 24. Khi source lưu UTF-8 nhưng máy build dùng charset khác, option nào nên chỉ định?
A. javac -classpath UTF-8 để đổi encoding của JAR class
B. javac -g UTF-8 để chỉ định charset debug metadata
C. javac -encoding UTF-8 để đọc source đúng bảng mã
D. javac -d UTF-8 để đặt charset cho output directory
Đáp án đúng: C

Câu 25. Annotation processor theo chuẩn Java thường xử lý thời điểm nào?
A. Khi ClassLoader khởi tạo lần đầu một object đã chạy
B. Chỉ sau khi JarSigner hoàn tất ký artifact JAR
C. Annotation processor chạy trong lúc compile nguồn Java
D. Khi JIT biên dịch hot method tại thời điểm runtime
Đáp án đúng: C

Câu 26. Để chỉ định tên các processor được javac gọi, tùy chọn nào phù hợp?
A. javac -parameters nêu processor class dùng cho reflection
B. javac -processor nêu processor class muốn thực thi
C. javac -Xlint nêu processor class cần bật warning
D. javac -encoding nêu class đọc annotation metadata
Đáp án đúng: B

Câu 27. Để javac tìm annotation processor trong JAR riêng, dùng đường nào?
A. --processor-path khai nơi tìm processor trên classpath
B. --module-source-path khai vị trí bytecode processor JAR
C. --release chỉ định JAR dùng làm annotation processor
D. --add-exports tự tìm processor từ tất cả module JDK
Đáp án đúng: A

Câu 28. Muốn chạy annotation processor mà không tạo class output cho source, dùng gì?
A. javac -proc:none chỉ chạy processor và bỏ code generation
B. javac -g:none tắt sinh .class nhưng vẫn chạy processors
C. javac -Werror chuyển processor output sang file nguồn
D. javac -proc:only thực hiện riêng annotation processing
Đáp án đúng: D

Câu 29. Processor.process trả true cho annotation mà nó nhận xử lý có nghĩa gì?
A. Processor bảo đảm không còn round processing nào tiếp theo
B. Processor khẳng định đã tạo ít nhất một valid class file
C. Processor ngăn compiler phát mọi warning ở round hiện tại
D. Processor claim các annotation type tương ứng trong round
Đáp án đúng: D

Câu 30. Filer.createSourceFile được annotation processor dùng cho việc gì?
A. Tạo Java source mới để javac có thể xử lý round tiếp theo
B. Chỉnh trực tiếp method body của file Java source gốc
C. Tạo module descriptor bằng cách sửa file JAR đang có
D. Ghi đè class file của JDK bằng code processor tự sinh
Đáp án đúng: A

Câu 31. Tại sao compiler có thể cần nhiều round annotation processing?
A. Mỗi annotation buộc javac chạy lại toàn bộ JVM từ đầu
B. Source mới sinh có thể cần processing round tiếp
C. Mỗi round được dành cho một dependency JAR trong classpath
D. Mỗi round chỉ thực hiện tối ưu JVM bytecode ở runtime
Đáp án đúng: B

Câu 32. Nếu một processor tạo lặp cùng đường dẫn source trong một compilation, thường gặp gì?
A. ClassCastException vì source file được xem là Java class
B. NoSuchMethodError khi classloader tìm processor method
C. FilerException khi cố tạo một file trùng đã tạo trước đó
D. UnsupportedClassVersionError do JAR thiếu manifest version
Đáp án đúng: C

Câu 33. Annotation với RetentionPolicy.SOURCE thường tồn tại tới lúc nào?
A. Được lưu trong .class để reflection đọc được khi runtime
B. Được giữ trong class file nhưng runtime không thể đọc
C. Chỉ phục vụ compilation, không được lưu trong .class
D. Được đưa vào module-info.class với retention runtime
Đáp án đúng: C

Câu 34. Muốn reflection đọc annotation từ class ở runtime, nên khai retention nào?
A. RetentionPolicy.CLASS vì runtime reflection luôn thấy nó
B. RetentionPolicy.RUNTIME để annotation còn tồn tại khi chạy
C. RetentionPolicy.SOURCE vì javac tự sinh runtime proxy
D. RetentionPolicy.NONE để JVM tự giữ annotation metadata
Đáp án đúng: B

Câu 35. Trong JDK có công cụ biên dịch, lấy JavaCompiler qua API nào?
A. ClassLoader.getSystemClassLoader() trực tiếp trả compiler
B. ToolProvider.getSystemJavaCompiler() lấy compiler hệ thống
C. DiagnosticCollector.getJavaCompiler() tạo compiler object
D. StandardJavaFileManager.getSystemCompiler() tạo compiler
Đáp án đúng: B

Câu 36. Nếu runtime image không kèm jdk.compiler, ToolProvider.getSystemJavaCompiler() có thể trả gì?
A. Instance JavaCompiler tự tạo bằng JIT compiler trong JVM
B. DiagnosticCollector tự thay thế khi thiếu compiler module
C. Giá trị null khi không tìm thấy system JavaCompiler
D. JavaCompiler mặc định chỉ hỗ trợ Java source trên network
Đáp án đúng: C

Câu 37. Khi muốn đưa source code dạng chuỗi vào JavaCompiler API, giải pháp nào phù hợp?
A. DiagnosticCollector chứa source rồi đưa thẳng cho ClassLoader
B. SimpleJavaFileObject biểu diễn nội dung source trong bộ nhớ
C. ClassFileTransformer nhận source Java chưa parse để compile
D. JavaFileManager.getClassLoader sinh source từ file .class
Đáp án đúng: B

Câu 38. JavaCompiler.getTask dùng để tạo compilation task từ những gì?
A. Danh sách loaded Class<?> và bytecode do ClassLoader phát
B. Danh sách stack frame cùng đối số của main method
C. Tập Java module đã nạp và JVM runtime instrumentation
D. File manager, diagnostic listener, options và JavaFileObject
Đáp án đúng: D

Câu 39. Sau khi gọi CompilationTask.call(), kết quả thông thường cho biết điều gì?
A. Boolean thể hiện task biên dịch thành công hay thất bại
B. Class<?> của mọi class vừa được load vào JVM hiện tại
C. ByteBuffer có toàn bộ bytecode của chương trình
D. Danh sách diagnostic đã phân loại theo số error
Đáp án đúng: A

Câu 40. StandardJavaFileManager thường xử lý phần nào trong JavaCompiler API?
A. Ghi source và .class hoàn toàn trong RAM theo mặc định
B. Quản lý vòng đời custom ClassLoader để chạy code mới
C. Ánh xạ Java annotation sang JVM invokedynamic instruction
D. Input/output Java file theo mô hình filesystem tiêu chuẩn
Đáp án đúng: D

Câu 41. Để giữ output .class trong bộ nhớ, cách mở rộng nào phù hợp?
A. Chỉ dùng SimpleJavaFileObject làm input là đủ giữ output
B. Chỉ thêm -d vào task và cung cấp tên vùng nhớ JVM
C. Dùng DiagnosticCollector làm buffer lưu class output
D. Tùy biến JavaFileManager trả JavaFileObject ghi vào RAM
Đáp án đúng: D

Câu 42. Để thực thi class vừa compile thành công trong RAM, còn thiếu bước nào?
A. CompilationTask.call() tự tạo instance của main class
B. Dùng ClassLoader phù hợp định nghĩa class từ bytecode
C. DiagnosticCollector tự đưa class mới vào boot classpath
D. JavaFileObject tự gọi constructor nếu compile thành công
Đáp án đúng: B

Câu 43. DiagnosticCollector trong API biên dịch dùng để thu thập thông tin gì?
A. Diagnostic gồm lỗi, warning và vị trí source
B. Class bytecode đã được ghi bằng JavaFileManager
C. Danh sách type mà ClassLoader đã liên kết runtime
D. Đồ thị phụ thuộc module được tạo bằng jdeps
Đáp án đúng: A

Câu 44. Nếu CompilationTask.call() trả false nhưng không thấy nhiều output, bước chẩn đoán nào đúng?
A. Chạy javap -c trên một class file chưa được sinh
B. Tăng heap rồi bỏ qua kết quả false của CompilationTask
C. Đọc DiagnosticCollector để xem lỗi và vị trí được ghi
D. Đặt -parameters để tự giải quyết lỗi cú pháp Java
Đáp án đúng: C

Câu 45. JVM ném UnsupportedClassVersionError khi load .class thường do đâu?
A. Source có import thiếu trong giai đoạn compile thành công
B. Class được compile cho Java mới hơn JVM đang chạy
C. Compiler đã bật -Xlint nhưng gặp warning chưa xử lý
D. Classpath chứa hai tên package giống nhau khi parse
Đáp án đúng: B

Câu 46. Khi javac báo package ... does not exist, hướng chẩn đoán nào phù hợp?
A. Kiểm tra option -g để bật debug local variable table
B. Kiểm tra class file major version của class hiện tại
C. Kiểm tra module path, classpath và JAR dependency
D. Kiểm tra JIT compiler đang nạp package từ RAM
Đáp án đúng: C

Câu 47. Nếu incremental build dùng class cũ sau khi đổi interface, kiểm tra nào hữu ích?
A. Bật -g:none để JIT lấy lại interface từ source mới
B. Chạy javap -c nhưng giữ nguyên tất cả artifact cũ
C. Clean rebuild, soát cache và dependency graph
D. Chỉ tăng heap javac để tự loại bỏ mọi class bị stale
Đáp án đúng: C

Câu 48. Sau khi biên dịch, công cụ jdeps có thể hỗ trợ phân tích điều gì?
A. Cú pháp source Java trước khi javac chạy parser
B. Các lỗi definite assignment trong Java source mới
C. Các vòng annotation processing đang chờ compile
D. Phân tích dependency package/module từ bytecode
Đáp án đúng: D
