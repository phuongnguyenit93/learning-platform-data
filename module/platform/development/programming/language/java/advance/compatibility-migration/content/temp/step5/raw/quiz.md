Câu 01. Khi nâng JDK, khái niệm tương thích nguồn (source compatibility) tập trung vào điều gì?
A. Ứng dụng cũ vẫn trả kết quả và lỗi giống bản trước nâng cấp
B. Dữ liệu serialized cũ vẫn đọc được sau khi đổi mô hình lớp
C. Bytecode cũ vẫn liên kết được với thư viện runtime đang triển khai
D. Mã Java cũ vẫn được biên dịch thành công với compiler mục tiêu
Đáp án đúng: D

Câu 02. Một thay đổi API khiến chương trình đã biên dịch không liên kết được ở runtime thường thuộc loại rủi ro nào?
A. Tương thích nhị phân giữa bytecode cũ và dependency mới
B. Tương thích ký tự khi ứng dụng đọc file UTF-8 trên đĩa
C. Tương thích cú pháp mã nguồn khi dùng Java compiler cũ
D. Tương thích kết quả nghiệp vụ giữa hai cấu hình timezone
Đáp án đúng: A

Câu 03. Ứng dụng vẫn compile và chạy nhưng thay đổi cách làm tròn số sau nâng JDK; đây là vấn đề gì?
A. Tương thích bytecode cần giải quyết bằng `--release` thấp
B. Tương thích source cần khôi phục cú pháp Java đời cũ
C. Tương thích module cần thêm `requires` cho các package mới
D. Tương thích hành vi cần kiểm bằng test kết quả thực tế
Đáp án đúng: D

Câu 04. Tác dụng chính của `javac --release 11` khi biên dịch với JDK mới hơn là gì?
A. Sinh bytecode JDK hiện tại nhưng kiểm cú pháp theo Java 11
B. Sinh bytecode và giới hạn Java SE API về mức Java 11
C. Chạy toàn bộ test trên runtime Java 11 sau khi biên dịch
D. Sinh bytecode Java 11 nhưng cho phép gọi API JDK mới
Đáp án đúng: B

Câu 05. Vì sao dùng `-source 11 -target 11` trên JDK mới chưa tương đương `--release 11`?
A. Bytecode được biên dịch thành class version của JDK mới
B. Code có thể gọi API mới dù bytecode target Java 11
C. Compiler chọn dependency Java 11 theo target bytecode của project
D. Compiler chạy ứng dụng trên JVM 11 trước khi xuất class file
Đáp án đúng: B

Câu 06. Nếu muốn xây artifact chạy trên Java 11 bằng JDK 21, lựa chọn compiler nào phù hợp hơn?
A. `javac --source 21` để cấp mã nguồn tương thích Java 11
B. `javac --target 21` để chạy trên JVM 11 không cần chuyển đổi
C. `javac --release 11` để khóa class format và API nền tảng
D. `javac --enable-preview` để bật tương thích ngược Java 11
Đáp án đúng: C

Câu 07. Class file của Java 17 có major version nào theo JVM specification?
A. Major version 65 tương ứng class được tạo cho Java 17
B. Major version 61 tương ứng class được tạo cho Java 17
C. Major version 52 tương ứng class được tạo cho Java 17
D. Major version 55 tương ứng class được tạo cho Java 17
Đáp án đúng: B

Câu 08. Class file với major version 65 thường yêu cầu JVM tối thiểu thuộc dòng nào?
A. Java 8 là runtime tương ứng với class file version 65
B. Java 21 là runtime tương ứng với class file version 65
C. Java 17 là runtime tương ứng với class file version 65
D. Java 11 là runtime tương ứng với class file version 65
Đáp án đúng: B

Câu 09. Khi JVM 11 tải class biên dịch cho Java 17 và báo version không hỗ trợ, exception nào phù hợp?
A. `UnsupportedClassVersionError` do class format vượt runtime
B. `ClassNotFoundException` báo loader không tìm ra tên class
C. `NoSuchMethodError` báo thiếu method lúc linkage runtime
D. `IllegalAccessError` báo truy cập member bị giới hạn
Đáp án đúng: A

Câu 10. Để xem major version và descriptor trong class file đã biên dịch, dùng công cụ nào?
A. `jdeprscan` biên dịch lại class với target JDK cũ
B. `jlink` hiển thị bytecode của các module phụ thuộc
C. `javap -verbose` xem major version và descriptor của class
D. `jdeps --jdk-internals` in thông tin major version class
Đáp án đúng: C

Câu 11. Công cụ JDK nào phân tích phụ thuộc tĩnh giữa package, class hoặc module của artifact?
A. `jdeps` khám phá phụ thuộc từ bytecode của JAR/class
B. `jpackage` phân tích đồ thị imports của class Java
C. `jdeprscan` phát hiện phụ thuộc tĩnh giữa module bất kỳ
D. `javap` xây dependency graph của toàn bộ JAR transitive
Đáp án đúng: A

Câu 12. Trong đánh giá di trú JDK, option nào của `jdeps` giúp tìm tham chiếu API nội bộ JDK?
A. `jdeps --release` liệt kê phụ thuộc internal APIs
B. `jdeps --summary` liệt kê tham chiếu internal APIs
C. `jdeps --check` liệt kê tham chiếu internal APIs
D. `jdeps --jdk-internals` tìm tham chiếu tới JDK internals
Đáp án đúng: D

Câu 13. Để phân tích Multi-Release JAR theo runtime Java 17, nên cấu hình `jdeps` ra sao?
A. Dùng `jdeps --module-path 17` để chọn versioned classes phù hợp
B. Dùng `jdeps --jdk-internals 17` để chọn versioned classes phù hợp
C. `jdeps --multi-release 17` xét classes theo Java 17
D. Dùng `jdeps --release 17` để lựa chọn versioned classes phù hợp
Đáp án đúng: C

Câu 14. Vì sao kết quả `jdeps` chưa đủ để kết luận ứng dụng không phụ thuộc API bị thay đổi?
A. Phân tích tĩnh có thể bỏ sót reflection và lớp nạp động
B. Phân tích tĩnh đo tương thích hành vi các nghiệp vụ
C. Phân tích tĩnh kiểm thử HTTP routing của production theo JDK
D. Phân tích tĩnh xác minh ServiceLoader providers của runtime
Đáp án đúng: A

Câu 15. Công cụ nào quét bytecode để tìm các API Java SE đã đánh dấu deprecated?
A. `jdeps` xác định chỗ dùng API JDK bị deprecate
B. `javac -g` xác định API JDK bị deprecate qua debug
C. `jlink` xác định API JDK bị deprecate qua module set
D. `jdeprscan` xác định chỗ dùng API JDK bị deprecate
Đáp án đúng: D

Câu 16. Khi `jdeprscan` không báo gì, kết luận nào thận trọng nhất khi nâng JDK?
A. Bỏ qua kiểm binary compatibility của dependency bên thứ ba
B. Không cần chạy kiểm thử reflection vì scan đã bao phủ đầy đủ
C. Scanner phát hiện các thay đổi hành vi của JDK ở runtime
D. Vẫn chạy hồi quy vì `jdeprscan` không kiểm hết thay đổi runtime
Đáp án đúng: D

Câu 17. Ứng dụng dùng `javax.xml.bind` trong JDK 8; nâng lên JDK 17 cần chú ý gì?
A. Thêm dependency JAXB tương thích vì module đã rời JDK
B. Thêm `--add-opens java.base` để khôi phục toàn bộ JAXB
C. Chỉ bật `--enable-preview` để dùng JAXB trong JDK 17
D. Đổi class-file version sang 61 sẽ tự bổ sung JAXB
Đáp án đúng: A

Câu 18. Trong dự án dùng Java Platform Module System, khai báo nào mô tả module phụ thuộc trực tiếp?
A. `exports` trong module-info.java để đọc module được yêu cầu
B. `opens` trong module-info.java để đọc module được yêu cầu
C. `requires` khai báo đọc module phụ thuộc trong module-info.java
D. `provides` trong module-info.java để đọc module được yêu cầu
Đáp án đúng: C

Câu 19. Nếu module cần cho các module khác gọi public API của package, directive nào thích hợp?
A. `exports` công bố public types của package cho module khác
B. `uses` cho phép module khác import toàn bộ type của package
C. `requires` cho phép public type hiển thị ra các module khác
D. `opens` cho phép các module khác gọi public API tại compile time
Đáp án đúng: A

Câu 20. Khi framework cần deep reflection lên non-public members của một package, directive nào phù hợp?
A. `opens` cấp quyền reflective access cho package liên quan
B. `uses` cấp reflective access cho private fields trong package
C. `exports` cấp deep reflection cho private members mặc định
D. `requires` cấp deep reflection cho private members mặc định
Đáp án đúng: A

Câu 21. Một thư viện phản chiếu lên JDK internals gặp InaccessibleObjectException; bước chuyển tiếp nào hợp lý?
A. Dùng `--add-reads` để mở private fields của JDK package
B. Dùng `--add-opens` có kiểm soát và ưu tiên nâng thư viện
C. Dùng `--add-modules` để cấp deep reflection vào JDK base
D. Dùng `--limit-modules` để cấp reflective access vào module
Đáp án đúng: B

Câu 22. Để truy cập public type thuộc package chưa được export bởi module, option tạm nào phù hợp hơn?
A. `--patch-module` tự sửa API source của JDK dependency
B. `--add-reads` xuất package cho các module khác trong layer
C. `--add-exports` cấp truy cập public type trong package chưa export
D. `--add-opens` chỉ định type sẽ được compiler tự import
Đáp án đúng: C

Câu 23. Khi hai named modules có cùng một package trên module path, vấn đề nào cần xử lý?
A. Split package xung đột trong cấu hình JPMS module graph
B. Compiler tự chuyển cả hai module về classpath chung
C. Versioned classes của Multi-Release JAR không thể giải mã
D. JAR signatures không còn được xác minh vì có hai packages
Đáp án đúng: A

Câu 24. Với ServiceLoader trên module path, cấu hình module-info nào hỗ trợ provider discovery?
A. Consumer khai báo `exports`, provider khai báo `opens`
B. Consumer khai báo `uses`, provider khai báo `provides ... with`
C. Consumer khai báo `requires transitive`, provider khai báo `opens`
D. Consumer khai báo `opens`, provider khai báo `uses`
Đáp án đúng: B

Câu 25. Một Java service cũ gọi method đã bị xóa trong JAR mới, lỗi linkage nào thường xuất hiện?
A. `UnsupportedClassVersionError` do class file quá mới với JVM
B. `NumberFormatException` do dữ liệu đầu vào không hợp lệ
C. `NoSuchMethodError` do descriptor method được gọi không còn
D. `ClassCastException` do kiểu object không cast được ở runtime
Đáp án đúng: C

Câu 26. Một class được tham chiếu trong bytecode nhưng dependency JAR của nó thiếu ở runtime, thường gặp lỗi nào?
A. `IllegalArgumentException` do giá trị đầu vào không hợp lệ
B. `NoSuchFieldError` khi bytecode tham chiếu field bị đổi tên
C. `AbstractMethodError` khi gọi method chưa triển khai
D. `NoClassDefFoundError` do JVM thiếu class lúc linkage
Đáp án đúng: D

Câu 27. Một interface thêm abstract method và old implementation chưa triển khai nhưng vẫn được load; khi invoke có thể gặp gì?
A. `AbstractMethodError` khi gọi method thiếu implementation
B. `NoSuchFieldError` khi JVM tìm không ra field mới
C. `ClassNotFoundException` khi reflection không tìm ra type
D. `StackOverflowError` khi recursive invocation không dừng
Đáp án đúng: A

Câu 28. Khi dependency đổi một class thành interface nhưng caller vẫn dùng bytecode cũ, lỗi nào có thể xảy ra?
A. `InvalidClassException` do serialized UID không trùng
B. `SecurityException` do missing runtime security policy
C. `UnsupportedEncodingException` do class metadata thay charset
D. `IncompatibleClassChangeError` do class/interface đổi dạng
Đáp án đúng: D

Câu 29. Một library xóa public static field được tham chiếu bởi bytecode cũ; lỗi nào đặc trưng?
A. `UnsupportedClassVersionError` do field thiếu version
B. `NoSuchMethodError` do field không có method getter
C. `NoSuchFieldError` do field được gọi không còn trong JAR
D. `AbstractMethodError` do field không có implementation
Đáp án đúng: C

Câu 30. Deserialization object cũ sau khi đổi `serialVersionUID` không tương thích thường dẫn đến lỗi nào?
A. `ClassFormatError` khi JSON payload thay đổi schema object
B. `NoSuchFieldError` khi stream thiếu field được thêm mới
C. `IllegalAccessException` khi class được annotate Serializable
D. `InvalidClassException` khi `serialVersionUID` khác giữa hai bản
Đáp án đúng: D

Câu 31. Vì sao lưu Java-serialized object lâu dài trong shared cache dễ gây khó khi nâng dependency?
A. Đổi tên class sẽ được loader tự ánh xạ sang type cùng trường
B. Đổi schema class có thể khiến state cũ không deserialize được
C. Java serialization duy trì schema đọc được qua các bản nâng
D. Serialization tự chuyển schema object mới theo API hiện tại
Đáp án đúng: B

Câu 32. Khi nâng từ JDK 17 lên JDK 21, cách nào giúp tránh khác biệt default charset giữa môi trường?
A. Dùng `javap -verbose` để ghi charset mong muốn vào class
B. Chỉ định `StandardCharsets.UTF_8` khi đọc và ghi text
C. Dùng `Charset.defaultCharset()` trong mỗi nơi cần text
D. Thêm `-source 17` để cố định default charset của JVM
Đáp án đúng: B

Câu 33. Khi migrate Spring application từ Java EE sang Jakarta EE, trở ngại source nào dễ thấy?
A. Tên package chuyển từ `java.util` sang `jakarta.util`
B. Tên package chuyển từ `org.springframework` sang `jakarta.spring`
C. Tên package chuyển từ `javax.servlet` sang `jakarta.servlet`
D. Tên package chuyển từ `javax.crypto` sang `jakarta.crypto`
Đáp án đúng: C

Câu 34. Khi hai dependency kéo theo các version khác nhau của cùng thư viện, bước điều tra nên làm gì?
A. Bỏ kiểm thử integration vì lỗi liên kết sẽ lộ ở unit test
B. Đổi `module-info` thành classpath để bỏ kiểm ABI của thư viện
C. Xem dependency tree để đối chiếu phiên bản đã resolve
D. Hạ `javac --release` để classpath tự chọn bản phụ thuộc phù hợp
Đáp án đúng: C

Câu 35. Nếu nâng JDK nhưng phải duy trì artifact chạy trên runtime Java 11, ma trận CI nào có giá trị?
A. Chạy `jdeps` trên jar mà không khởi chạy runtime Java 11
B. Biên dịch với target JVM mới, chạy test trên đúng JVM mới
C. Chạy unit tests trên JDK mới rồi xem như JVM 11 tương thích
D. Biên dịch `--release 11`, test trên JVM 11 và JVM mới
Đáp án đúng: D

Câu 36. Với thay đổi annotation processor khi nâng JDK, cần kiểm chứng điểm nào của build?
A. Runtime behavior sẽ không đổi nếu compile task thành công
B. Annotation processor nằm trong module graph của JVM production
C. Compiler plugin và processor chạy đúng trên toolchain JDK mới
D. Bytecode cần mang version mới hơn runtime để processor hoạt động
Đáp án đúng: C

Câu 37. Khi ứng dụng báo lỗi reflective access sau khi nâng JDK, ưu tiên sửa bền vững là gì?
A. Nâng library để bỏ truy cập JDK internals thay vì giữ flag
B. Đặt các package vào unnamed module để né cảnh báo reflection
C. Tắt các test có reflection và tiếp tục triển khai production
D. Thêm `--add-opens` vào startup rồi coi migration đã kết thúc
Đáp án đúng: A

Câu 38. Để giảm blast radius khi triển khai bản nâng JDK trên hệ thống nhiều node, kế hoạch nào hợp lý?
A. Chỉ kiểm class version rồi xóa cơ chế rollback của cluster
B. Canary ít traffic, theo dõi lỗi rồi mở rộng hoặc rollback
C. Thay đồng loạt các node trước khi so sánh telemetry
D. Triển khai build mới và bỏ monitoring vì API không thay đổi
Đáp án đúng: B

Câu 39. Khi migration thay đổi cả database schema, cách phát hành nào giảm nguy cơ rollback khó?
A. Đổi schema và xóa cột cũ trước khi triển khai bất kỳ node nào
B. Thực hiện expand-contract để bản cũ và mới chạy cùng giai đoạn
C. Chỉ nâng JDBC driver và bỏ kiểm tra truy vấn dữ liệu thực tế
D. Phát hành code mới với schema mới bất chấp bản cũ còn hoạt động
Đáp án đúng: B

Câu 40. Khi đánh giá bản nâng JDK đạt chất lượng trước rollout, bộ bằng chứng nào hữu ích nhất?
A. Đọc release notes rồi bỏ các bài test tính tương thích runtime
B. Chỉ chạy một smoke test khởi động, không đo HTTP hoặc latency
C. Biên dịch thành công là đủ để suy ra các nghiệp vụ còn đúng
D. Test hồi quy, contract, hiệu năng và telemetry runtime
Đáp án đúng: D
