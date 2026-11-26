Bạn phân biệt JDK, JRE và JVM theo mục đích phát triển, đóng gói và thực thi Java như thế nào?
Bạn sẽ kiểm tra java -version và javac -version khi nghi ngờ môi trường dùng hai JDK khác nhau ra sao?
Bạn mô tả cách JAVA_HOME và PATH ảnh hưởng executable Java được tìm thấy bởi terminal như thế nào?
Bạn sẽ xác định compiler mà IDE hoặc CI đang gọi bằng bằng chứng nào thay vì dựa vào JAVA_HOME?
Bạn phân biệt JDK vendor với Java release version và patch version về compatibility ra sao?
Bạn sẽ chọn JDK toolchain phù hợp khi project cần chạy trên cả runtime cũ và mới như thế nào?
Bạn phân tích nguy cơ Maven hoặc Gradle dùng JDK khác với terminal khi build và chạy unit test ra sao?
Bạn sẽ tổ chức nhiều JDK installations trên cùng máy developer để chuyển đổi có kiểm soát như thế nào?
Bạn mô tả class file major version được liên hệ với mức Java runtime cần thiết ra sao?
Bạn sẽ xác định nguyên nhân UnsupportedClassVersionError khi artifact chạy không được trên máy đích như thế nào?
Bạn phân biệt custom runtime image với JDK đầy đủ về những modules và công cụ có sẵn ra sao?
Bạn sẽ kiểm tra một JDK installation có đủ javac, jar và các diagnostic tools mà CI cần như thế nào?
Bạn phân biệt công cụ JDK cung cấp với công cụ build bên ngoài như Maven hay Gradle theo trách nhiệm nào?
Bạn sẽ thiết kế CI matrix chạy test trên nhiều JDK releases với dependencies được khóa phiên bản ra sao?
Bạn mô tả lợi ích và giới hạn của việc chọn JDK bản hỗ trợ dài hạn cho production như thế nào?
Bạn phân tích vì sao nâng JDK patch version vẫn cần chạy regression tests ra sao?
Bạn sẽ xây một environment report gồm OS, architecture, compiler flags, classpath và JDK version như thế nào?
Bạn sẽ quyết định lúc nào dùng javac --release từ JDK mới hơn thay vì build trực tiếp trên JDK cũ ra sao?
Bạn phân biệt source-level compatibility với binary compatibility khi phát hành thư viện Java như thế nào?
Bạn sẽ phân tích một incident chỉ xảy ra trên custom Java runtime image theo các bước nào?
Bạn giải thích pipeline javac từ source parsing tới sinh file .class gồm các công đoạn nào?
Bạn sẽ dùng javac -d để ghi class files ra một output directory đúng package structure như thế nào?
Bạn phân biệt javac -cp và --module-path khi xử lý thư viện classpath và named modules ra sao?
Bạn sẽ tìm nguyên nhân package does not exist dù dependency JAR đã được tải về máy như thế nào?
Bạn mô tả javac --release kiểm soát language syntax, class file version và public platform APIs ra sao?
Bạn phân biệt các tùy chọn -source, -target và --release khi cần hỗ trợ runtime Java cũ như thế nào?
Bạn phân tích vì sao -target không tự ngăn gọi các JDK APIs không có trên runtime đích ra sao?
Bạn sẽ dùng javac -encoding UTF-8 để tránh lỗi nguồn chứa tiếng Việt khi build đa hệ điều hành như thế nào?
Bạn mô tả -parameters giúp giữ tên method parameters trong class file theo nhu cầu reflection nào?
Bạn phân biệt -g và -g:none về metadata được giữ lại cho debugger như thế nào?
Bạn sẽ bật javac -Xlint và chọn những warnings nên làm CI fail theo chính sách nào?
Bạn phân biệt -Werror với chỉ ghi cảnh báo trong log khi tăng tiêu chuẩn chất lượng build như thế nào?
Bạn sẽ dùng -Xdiags:verbose để điều tra type inference hoặc overload ambiguity như thế nào?
Bạn mô tả javac @argument-file có thể giúp lệnh compile nhiều files tránh giới hạn độ dài command line ra sao?
Bạn sẽ kiểm tra cách quote đường dẫn có dấu cách trong arguments file khi build trên Windows như thế nào?
Bạn phân tích vì sao annotation processor không chạy có thể dẫn đến lỗi cannot find symbol như thế nào?
Bạn sẽ dùng -processorpath để khai báo processors độc lập với runtime dependencies như thế nào?
Bạn phân biệt javac -proc:only và -proc:none khi muốn cô lập lỗi annotation processing ra sao?
Bạn sẽ kiểm tra cách bật annotation processor tường minh khi default behavior thay đổi giữa các JDK versions ra sao?
Bạn mô tả -s option trong javac chọn thư mục generated sources theo quy tắc nào?
Bạn sẽ dùng --enable-preview khi biên dịch preview feature và xác minh các yêu cầu khi chạy như thế nào?
Bạn sẽ xác định lỗi module not found từ requires declaration hoặc module source path theo những bước nào?
Bạn phân tích vì sao dùng --add-exports để truy cập JDK internal classes khiến việc nâng JDK rủi ro như thế nào?
Bạn sẽ so sánh clean build và incremental build để phát hiện stale .class hoặc generated sources ra sao?
Bạn sẽ xây một lệnh javac tối giản để tách lỗi compiler khỏi lỗi cấu hình build tool như thế nào?
Bạn giải thích java launcher chọn main class, executable JAR hoặc module main theo những chế độ nào?
Bạn phân biệt java -cp với java -jar về cách xác định main method và dependencies ra sao?
Bạn sẽ xác định vì sao một ứng dụng chạy bằng classpath nhưng lỗi khi chuyển sang java -jar như thế nào?
Bạn mô tả Main-Class attribute của JAR manifest có vai trò gì trong quá trình launch như thế nào?
Bạn sẽ dùng java --module-path và --module để chạy ứng dụng modular theo cú pháp nào?
Bạn phân biệt program arguments với JVM startup options và system properties -D như thế nào?
Bạn sẽ sử dụng source-file mode để chạy một Java source file mà không cần tự gọi javac theo điều kiện nào?
Bạn mô tả java --source hỗ trợ chọn source language version trong source-file mode như thế nào?
Bạn phân tích vì sao thành công trong source-file mode không thay thế integration test của JAR production ra sao?
Bạn sẽ kiểm tra module availability trên runtime qua java --list-modules như thế nào?
Bạn phân biệt -Xms và -Xmx trong cấu hình Java heap theo giới hạn RAM nào?
Bạn sẽ chẩn đoán tiến trình bị container OOM kill dù -Xmx vẫn còn dung lượng như thế nào?
Bạn sẽ chọn cấu hình -Xlog để quan sát GC hoặc class-loading trên JDK hiện đại như thế nào?
Bạn mô tả cách bật Java Flight Recorder lúc khởi động bằng -XX:StartFlightRecording ra sao?
Bạn sẽ sử dụng java -ea trong test nhưng tránh dựa vào assert để validate đầu vào production như thế nào?
Bạn sẽ phân tích lỗi NoClassDefFoundError và ClassNotFoundException theo thời điểm thiếu dependency nào?
Bạn sẽ xác định NoSuchMethodError có thể đến từ binary mismatch giữa compile và runtime như thế nào?
Bạn sẽ đọc exit status của ứng dụng sau startup smoke test để phân biệt lỗi process và lỗi business response ra sao?
Bạn phân tích vì sao đặt credentials trong system properties trên command line có thể gây lộ secrets như thế nào?
Bạn sẽ kiểm tra process JVM thực tế đang chạy với flags nào bằng jcmd thay vì chỉ xem startup script ra sao?
Bạn giải thích lệnh jar tạo archive đóng gói classes và resources cho Java runtime như thế nào?
Bạn sẽ dùng jar --create, --file và --main-class để đóng gói executable artifact như thế nào?
Bạn phân biệt jar --list và jar --extract trong việc kiểm tra hoặc lấy dữ liệu từ archive ra sao?
Bạn sẽ dùng jar --update khi cần sửa một resource nhưng tránh giữ stale entries như thế nào?
Bạn mô tả META-INF/MANIFEST.MF chứa những thông tin nào cho Java launcher như thế nào?
Bạn sẽ điều tra lỗi no main manifest attribute bằng cách xem cấu trúc JAR ra sao?
Bạn phân biệt Class-Path trong manifest với --module-path khi phân phối dependencies như thế nào?
Bạn sẽ chọn thin JAR kèm thư viện hay archive được build tool gộp dependencies theo kịch bản nào?
Bạn phân tích vì sao jar tool không tự tạo executable fat JAR chứa toàn bộ third-party dependencies như thế nào?
Bạn sẽ dùng jar --describe-module để kiểm tra module descriptor trong một JAR như thế nào?
Bạn mô tả module-info.class trong archive ảnh hưởng quyền truy cập package ra sao?
Bạn phân biệt automatic module với explicit module khi một thư viện đưa lên module path như thế nào?
Bạn sẽ kiểm tra artifact không chứa test classes hoặc secret config files bằng cách nào?
Bạn phân tích vì sao timestamps và thứ tự archive entries khiến hai JAR có hash khác nhau như thế nào?
Bạn sẽ chuẩn hóa archive metadata để tạo reproducible JAR từ cùng source và dependencies ra sao?
Bạn mô tả multi-release JAR chọn class implementation theo runtime Java version ra sao?
Bạn sẽ dùng jar --release ở bản JDK hỗ trợ để tạo phiên bản class bổ sung như thế nào?
Bạn phân biệt Multi-Release: true với sự tồn tại của META-INF/versions trong archive ra sao?
Bạn sẽ kiểm tra public API compatibility giữa các phiên bản class của multi-release JAR ra sao?
Bạn sẽ xác minh resource paths có thể được ClassLoader tìm thấy sau khi đóng JAR như thế nào?
Bạn sẽ dùng SHA-256 so sánh archive đã test và artifact được release ra sao?
Bạn phân tích vì sao build thành công nhưng java -jar vẫn lỗi do manifest hoặc resource thiếu như thế nào?
Bạn sẽ xây smoke test cho cấu trúc JAR và main entry point theo tiêu chí nào?
Bạn giải thích JPMS dùng module-info.java để thể hiện module dependencies và public packages như thế nào?
Bạn phân biệt requires, requires transitive và requires static theo compile-time và runtime module graph ra sao?
Bạn sẽ giải thích exports khác opens theo quyền truy cập public types và reflection như thế nào?
Bạn sẽ kiểm tra lỗi module not found khi một dependency chưa hiện diện trên --module-path ra sao?
Bạn phân tích vì sao public class trong non-exported package vẫn không thể được module khác import như thế nào?
Bạn sẽ xử lý split package khi chuyển dự án từ classpath mode sang module path ra sao?
Bạn mô tả uses và provides cho phép ServiceLoader tìm implementation trong JPMS như thế nào?
Bạn sẽ dùng jdeps để liệt kê static dependencies giữa Java packages hoặc modules ra sao?
Bạn giải thích jdeps --print-module-deps giúp chuẩn bị thông tin cho jlink như thế nào?
Bạn sẽ dùng jdeps --multi-release để phân tích phiên bản phù hợp trong multi-release JAR ra sao?
Bạn phân biệt jdeps --ignore-missing-deps với việc thực sự cung cấp dependency bị thiếu như thế nào?
Bạn sẽ sử dụng jdeps --jdk-internals để nhận diện thư viện gọi JDK internal APIs ra sao?
Bạn phân tích vì sao jdeps không nhận diện đầy đủ dependencies được tải qua reflection như thế nào?
Bạn sẽ dùng jdeps --generate-module-info để hỗ trợ chuyển một library legacy thành modular như thế nào?
Bạn phân biệt kết quả static analysis từ jdeps với modules thực sự được load tại runtime ra sao?
Bạn sẽ lập kế hoạch migrate từng bước từ classpath sang module path mà vẫn chạy được tests ra sao?
Bạn phân tích rủi ro duy trì --add-opens hoặc --add-exports như workaround lâu dài ra sao?
Bạn mô tả JMOD archive khác JAR ở mục đích link modules và phân phối như thế nào?
Bạn sẽ dùng jmod --list để xem nội dung module archive như thế nào?
Bạn phân biệt jmod với executable JAR về cách chạy trực tiếp qua java launcher ra sao?
Bạn sẽ kiểm tra automatic module name sau khi thư viện thay file name ở release mới ra sao?
Bạn sẽ kết hợp jdeps với integration tests để phát hiện runtime modules bị thiếu do reflection hoặc services ra sao?
Bạn sẽ xây checklist kiểm thử module graph trước khi tạo custom runtime image ra sao?
Bạn giải thích jlink liên kết JDK modules thành custom runtime image khác với đóng JAR như thế nào?
Bạn sẽ dùng jlink --module-path, --add-modules và --output tạo runtime theo yêu cầu nào?
Bạn phân biệt custom runtime image với full JDK theo modules và diagnostic tools còn hiện diện ra sao?
Bạn sẽ dùng jdeps xác định root modules cho một image trước khi link như thế nào?
Bạn mô tả jlink --launcher tạo application command trong runtime image ra sao?
Bạn sẽ kiểm tra danh sách modules trong custom image bằng java --list-modules của image như thế nào?
Bạn phân tích vì sao image thiếu java.sql làm một chức năng JDBC chạy lỗi như thế nào?
Bạn sẽ cân nhắc jlink --bind-services khi runtime cần service provider modules ra sao?
Bạn phân biệt jlink --strip-debug với loại bỏ modules không cần thiết theo tác động nào?
Bạn sẽ dùng jlink --no-header-files và --no-man-pages khi muốn giảm artifact size như thế nào?
Bạn sẽ kiểm tra compression options của jlink theo bản JDK thực tế thay vì giả định flags giống nhau ra sao?
Bạn sẽ test custom runtime image với những đường thực thi có reflection hoặc service loading theo cách nào?
Bạn phân tích vì sao jlink không tự động chuyển mọi thư viện classpath thành named modules như thế nào?
Bạn sẽ quyết định phân phối runtime image riêng hay application launcher kèm JAR theo tiêu chí nào?
Bạn mô tả jpackage tạo app-image hoặc native installer từ ứng dụng Java như thế nào?
Bạn sẽ dùng jpackage --input, --main-jar và --name để đóng gói nonmodular app ra sao?
Bạn phân biệt jpackage --module với --main-jar khi đóng gói modular application như thế nào?
Bạn sẽ dùng jpackage --runtime-image khi có image đã tạo sẵn bằng jlink ra sao?
Bạn sẽ chọn jpackage --type phù hợp loại installer mà OS hỗ trợ như thế nào?
Bạn phân tích vì sao native installer build thường phải chạy trên hệ điều hành đích như thế nào?
Bạn sẽ chẩn đoán jpackage tạo app-image được nhưng không tạo installer do thiếu packaging tools ra sao?
Bạn sẽ thiết kế CI matrix tạo packages trên Windows, macOS và Linux theo giới hạn nào?
Bạn sẽ kiểm tra yêu cầu signing và notarization của hệ điều hành khi phát hành installer như thế nào?
Bạn sẽ smoke test ứng dụng từ installer trên máy không cài sẵn JDK ra sao?
Bạn sẽ tránh đưa công cụ debug không cần thiết vào runtime image production như thế nào?
Bạn giải thích jshell phù hợp cho việc thăm dò API JDK nhanh trong trường hợp nào?
Bạn sẽ tạo biến, method hoặc class snippets trong jshell để kiểm tra hành vi API ra sao?
Bạn phân biệt jshell session với Java source file tham gia quy trình build như thế nào?
Bạn sẽ dùng jshell /help để tìm commands khả dụng trên JDK đang chạy ra sao?
Bạn mô tả jshell /vars, /methods và /types liệt kê state của session như thế nào?
Bạn sẽ sử dụng jshell /imports khi một snippet thiếu imports ra sao?
Bạn phân biệt jshell /open với /save khi quản lý snippets thử nghiệm như thế nào?
Bạn sẽ dùng jshell /reset để loại bỏ ảnh hưởng của khai báo cũ trong một thí nghiệm ra sao?
Bạn sẽ chỉ định classpath hoặc module path cho jshell khi cần dùng JAR bên ngoài như thế nào?
Bạn phân tích vì sao jshell chạy thành công không chứng minh bản runtime target có cùng API như thế nào?
Bạn sẽ tránh nhập production credentials vào session history của jshell bằng chính sách nào?
Bạn sẽ chuyển một thí nghiệm jshell có giá trị thành unit test tự động như thế nào?
Bạn mô tả javap kiểm tra class metadata và bytecode khi không có source như thế nào?
Bạn sẽ dùng javap -c để xem bytecode instructions của một method ra sao?
Bạn phân biệt javap -p với javap -v về private members và verbose class attributes như thế nào?
Bạn sẽ dùng javap -verbose kiểm tra major version để điều tra lỗi runtime ra sao?
Bạn phân tích vì sao javap liệt kê bridge hoặc synthetic methods không xuất hiện trong source như thế nào?
Bạn sẽ kiểm tra debug attributes hoặc MethodParameters bằng javap khi đổi compiler flags ra sao?
Bạn phân biệt output javac với machine code được JIT sinh để tránh kết luận sai về optimization như thế nào?
Bạn mô tả javadoc tạo tài liệu từ API declarations và comments ra sao?
Bạn sẽ dùng javadoc -d để chọn output directory của tài liệu theo cấu hình nào?
Bạn sẽ tích hợp Javadoc warnings và output vào CI nhưng phân biệt chúng với compiler errors ra sao?
Bạn giải thích keytool hỗ trợ quản lý certificates và keystore trong JDK như thế nào?
Bạn phân biệt keystore chứa private key entries và truststore chứa certificates được tin cậy ra sao?
Bạn sẽ dùng keytool -list kiểm tra alias và certificate validity theo quy trình nào?
Bạn mô tả keytool -genkeypair tạo cặp khóa cùng certificate entry ra sao?
Bạn sẽ chọn PKCS12 thay JKS khi cần tương thích với hệ thống khác như thế nào?
Bạn phân biệt keytool -importcert và -exportcert theo thao tác với certificates ra sao?
Bạn sẽ dùng keytool -certreq tạo CSR để gửi CA theo các bước nào?
Bạn mô tả keytool -printcert giúp kiểm tra subject, issuer và SAN như thế nào?
Bạn phân tích rủi ro import CA không tin cậy vào JVM-wide cacerts như thế nào?
Bạn sẽ thiết kế truststore riêng cho ứng dụng thay vì sửa global truststore trong production ra sao?
Bạn sẽ quản lý storepass và keypass để không lộ secrets trong command history và CI logs như thế nào?
Bạn phân biệt xem public certificate bằng keytool với xuất private key khỏi HSM như thế nào?
Bạn sẽ dùng keytool kiểm tra certificate chain thiếu intermediate khi TLS handshake lỗi ra sao?
Bạn phân tích vì sao certificate được tin cậy vẫn có thể bị từ chối do hostname không thuộc SAN như thế nào?
Bạn sẽ lên kế hoạch certificate rotation có trust overlap khi nhiều clients cần chuyển đổi ra sao?
Bạn sẽ sử dụng jarsigner để ký hoặc xác minh một JAR artifact theo chính sách nào?
Bạn phân biệt chữ ký JAR bằng jarsigner với TLS server authentication ra sao?
Bạn sẽ dùng SHA-256 file checksum cùng signature validation trong release integrity như thế nào?
Bạn sẽ tạo test certificates cho CI mà không dùng private keys production theo cách nào?
Bạn giải thích jcmd truy vấn diagnostic information của JVM đang chạy theo điều kiện quyền nào?
Bạn sẽ dùng jps hoặc jcmd -l để tìm PID JVM cần chẩn đoán theo giới hạn nào?
Bạn mô tả jcmd <pid> help cho biết command availability trên JVM thực tế như thế nào?
Bạn sẽ dùng jcmd VM.version và VM.command_line để xác minh runtime và launcher flags ra sao?
Bạn phân biệt jcmd VM.flags với việc xem startup shell script khi kiểm tra JVM options như thế nào?
Bạn sẽ dùng jcmd Thread.print để quan sát Java thread stacks và monitors như thế nào?
Bạn mô tả jstack tạo thread dump hỗ trợ điều tra deadlock và lock contention ra sao?
Bạn phân biệt jstack với jcmd Thread.print tùy khả năng của JDK và môi trường ra sao?
Bạn sẽ đọc BLOCKED, WAITING, TIMED_WAITING và RUNNABLE từ thread dump theo những giả thuyết nào?
Bạn phân tích vì sao một thread dump snapshot không đủ chứng minh vấn đề kéo dài như thế nào?
Bạn sẽ chọn khoảng cách lấy nhiều thread dumps để xem trạng thái có lặp lại ra sao?
Bạn sẽ dùng jcmd GC.heap_info kiểm tra tổng quan heap state theo cách nào?
Bạn mô tả jcmd GC.class_histogram cho biết số lượng và kích thước objects theo class như thế nào?
Bạn phân biệt class histogram với heap dump về khả năng xác định retained references như thế nào?
Bạn sẽ dùng jcmd GC.heap_dump theo kế hoạch bảo vệ production performance và disk space ra sao?
Bạn phân tích vì sao heap dump có thể chứa user tokens hoặc passwords dù không nằm trong log như thế nào?
Bạn sẽ phân quyền và định retention cho heap dump khi cần chia sẻ phục vụ incident như thế nào?
Bạn phân biệt jmap với jcmd theo các thao tác heap analysis được JDK hỗ trợ ra sao?
Bạn sẽ sử dụng jstat -gc quan sát GC counters theo thời gian ra sao?
Bạn phân tích vì sao GC tăng nhiều không tự chứng minh một memory leak ra sao?
Bạn sẽ kết hợp jstat, heap histogram và Java Flight Recorder để phân tích allocation pressure như thế nào?
Bạn sẽ kiểm tra quyền OS và PID namespace khi jcmd attach không thành công như thế nào?
Bạn mô tả jhsdb hỗ trợ điều tra core dump hoặc JVM process bị treo trong điều kiện nào?
Bạn phân biệt jhsdb và jcmd về tác động lên process và yêu cầu quyền truy cập như thế nào?
Bạn sẽ dùng jdb để đặt breakpoint và step through Java code trong test environment ra sao?
Bạn phân tích vì sao remote debugging không được bảo vệ trên production gây rủi ro như thế nào?
Bạn sẽ thiết kế runbook thu jstack và JFR trước khi restart JVM bị treo như thế nào?
Bạn giải thích Java Flight Recorder (JFR) ghi events từ JVM và ứng dụng để làm gì?
Bạn phân biệt JFR recording với thread dump hoặc heap dump về loại thông tin và time span ra sao?
Bạn sẽ bật JFR tại startup bằng -XX:StartFlightRecording khi cần thu startup events như thế nào?
Bạn mô tả jcmd JFR.start cho phép bật recording cho một JVM đang chạy ra sao?
Bạn sẽ đặt duration, maxsize và maxage nhằm kiểm soát tài nguyên mà recording dùng như thế nào?
Bạn sẽ dùng jcmd JFR.check quan sát trạng thái recordings hiện có ra sao?
Bạn phân biệt jcmd JFR.dump và JFR.stop theo thao tác lưu hoặc kết thúc recording ra sao?
Bạn sẽ dùng jfr summary để xem các event types xuất hiện trong file như thế nào?
Bạn phân biệt jfr print và JDK Mission Control trong phân tích event stream ra sao?
Bạn sẽ sử dụng jfr print --events lọc dữ liệu theo loại sự kiện như thế nào?
Bạn mô tả CPU sampling của JFR giúp tìm hotspots nhưng có giới hạn thống kê nào?
Bạn sẽ dùng allocation events tìm classes tạo nhiều objects theo workload ra sao?
Bạn phân tích vì sao stack trace sample không thể coi là toàn bộ timeline của một request như thế nào?
Bạn sẽ xem JFR monitor hoặc thread park events khi một ứng dụng có latency cao như thế nào?
Bạn phân biệt GC pause và lock contention từ timeline events theo cách nào?
Bạn sẽ thiết kế custom JFR Event để đo một business operation theo mục đích nào?
Bạn phân tích rủi ro custom events vô tình ghi PII hoặc secrets vào recording như thế nào?
Bạn sẽ chọn JFR settings default hoặc profile theo chi phí và độ chi tiết nào?
Bạn sẽ so sánh hai recordings khi JIT warmup hoặc tải thay đổi ra sao?
Bạn sẽ kết hợp JFR với GC logs và thread dumps để lập incident timeline như thế nào?
Bạn sẽ kiểm tra JFR event settings có khả dụng trên runtime version đích như thế nào?
Bạn sẽ xây cơ chế dump recording khi phát hiện ngưỡng bất thường nhưng không ghi file vô hạn ra sao?
Bạn giải thích reproducible build có nghĩa gì đối với cùng source, toolchain và dependencies?
Bạn phân biệt deterministic class bytes với JAR metadata có timestamps gây sai lệch hashes như thế nào?
Bạn sẽ cố định JDK và dependency versions trong CI để giảm môi trường không tái lập ra sao?
Bạn phân tích vì sao annotation processor đọc clock hoặc filesystem không khai báo khiến build nondeterministic như thế nào?
Bạn sẽ chuẩn hóa source encoding và line endings giữa Windows và Linux theo cách nào?
Bạn phân biệt clean build với incremental build khi cần phát hiện stale generated source như thế nào?
Bạn sẽ thiết kế compile cache key theo compiler version, flags, source và dependency hashes như thế nào?
Bạn phân tích vì sao đổi annotation processor version phải invalidate build cache ra sao?
Bạn sẽ chuẩn hóa archive timestamps, entry order và manifest fields khi tạo reproducible JAR như thế nào?
Bạn sẽ xác minh jar --date có được JDK đích hỗ trợ trước khi dùng để cố định timestamps như thế nào?
Bạn sẽ so sánh SHA-256 của hai JAR từ hai CI runners để khoanh vùng khác biệt ra sao?
Bạn phân biệt kết quả jdeps với software bill of materials về phạm vi dependencies như thế nào?
Bạn phân tích vì sao jdeps không thay cho kiểm tra security vulnerabilities của third-party packages ra sao?
Bạn sẽ thiết kế pipeline compile, test, jar, jdeps, jlink, jpackage và smoke test ra sao?
Bạn phân biệt release provenance với chữ ký của jarsigner theo bảo đảm nguồn gốc nào?
Bạn sẽ kiểm tra output logs không chứa credentials hoặc private filesystem paths trước khi lưu artifact ra sao?
Bạn sẽ điều tra khi cùng commit sinh hai JAR khác hash bằng các bước nào?
Bạn sẽ tạo CI matrix build native installers trên OS tương ứng thay vì cross-compiling không được hỗ trợ ra sao?
Bạn phân tích vì sao một API có vẻ tương thích nhưng class version của dependency vẫn chặn runtime cũ như thế nào?
Bạn sẽ thiết kế release gate xác minh target JDK, class file versions và module dependencies ra sao?
Bạn sẽ định nghĩa build metadata phục vụ audit mà không đưa build timestamp ngẫu nhiên vào artifact ra sao?
Bạn sẽ kiểm tra manifest entry point và runtime resources sau khi build báo thành công như thế nào?
Bạn phân biệt ứng dụng chạy được trên full JDK với chạy được trên stripped custom runtime image như thế nào?
Bạn sẽ xây checklist phát hành gồm artifact hash, signature, certificate checks và runtime smoke tests ra sao?
Nếu javac báo package does not exist dù JAR trên đĩa, bạn sẽ kiểm tra -cp và --module-path như thế nào?
Nếu java báo UnsupportedClassVersionError, bạn sẽ xem javac --release và class major version ra sao?
Nếu CI dùng Java khác developer, bạn sẽ kiểm tra JAVA_HOME, PATH và Maven/Gradle toolchains như thế nào?
Nếu source chứa tiếng Việt bị compile lỗi trên một máy, bạn sẽ kiểm tra -encoding và source bytes ra sao?
Nếu generated source biến mất sau nâng JDK, bạn sẽ kiểm tra processor discovery và -processorpath như thế nào?
Nếu java -jar báo no main manifest attribute, bạn sẽ xem JAR manifest và jar --main-class ra sao?
Nếu java -cp chạy đúng nhưng java -jar thiếu dependency, bạn sẽ kiểm tra manifest Class-Path như thế nào?
Nếu JAR hash khác nhau sau clean builds, bạn sẽ điều tra timestamps, entry order và build metadata ra sao?
Nếu module not found khi chuyển sang JPMS, bạn sẽ dùng jdeps và module-info.java chẩn đoán như thế nào?
Nếu jdeps không thấy library được tải qua reflection, bạn sẽ bổ sung runtime integration test ra sao?
Nếu image jlink thiếu java.sql, bạn sẽ đánh giá module roots và runtime tests như thế nào?
Nếu jpackage tạo app-image nhưng không tạo installer, bạn sẽ kiểm tra native packaging tools theo OS ra sao?
Nếu jshell chạy code đúng nhưng project build không được, bạn sẽ so sánh imports, compiler flags và classpath như thế nào?
Nếu javap cho thấy major version quá cao, bạn sẽ điều tra toolchain và compiler --release như thế nào?
Nếu keytool liệt kê certificate trusted nhưng HTTPS lỗi hostname, bạn sẽ kiểm tra SAN và validation ra sao?
Nếu jcmd không attach được JVM trong container, bạn sẽ kiểm tra user permissions và PID namespace ra sao?
Nếu thread dump chứa nhiều threads BLOCKED trên một lock, bạn sẽ tìm owner và thu nhiều samples như thế nào?
Nếu heap tăng trong khi GC liên tục chạy, bạn sẽ phối hợp jstat, class histogram và heap dump ra sao?
Nếu cần heap dump production chứa PII, bạn sẽ thiết kế disk quota và access control như thế nào?
Nếu JFR báo allocation rate tăng nhưng CPU không cao, bạn sẽ phân tích GC và latency như thế nào?
Nếu file JFR thiếu event kỳ vọng, bạn sẽ kiểm tra recording settings và event types như thế nào?
Nếu cùng commit sinh artifact khác nhau trong hai CI jobs, bạn sẽ kiểm tra JDK, dependencies và JAR metadata ra sao?
Nếu phải phát hành app không yêu cầu người dùng cài JDK, bạn sẽ dùng jlink và jpackage theo bước nào?
Nếu một dependency gọi internal JDK API không còn được hỗ trợ, bạn sẽ dùng jdeps để xác định hướng thay thế như thế nào?
Nếu xây toolchain Java từ đầu, bạn sẽ kết hợp javac, jar, jdeps, jlink, jpackage, keytool, jcmd và JFR theo quy trình QA nào?
