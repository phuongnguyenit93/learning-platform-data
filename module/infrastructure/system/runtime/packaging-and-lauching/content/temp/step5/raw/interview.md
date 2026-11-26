Bạn sẽ lựa chọn hình thức phân phối JAR, WAR, archive hay container image dựa trên môi trường triển khai và trách nhiệm vận hành như thế nào?
Bạn sẽ phân biệt executable JAR với thư viện JAR thông thường về cấu trúc và cách khởi chạy ra sao?
Bạn sẽ giải thích vai trò của Main-Class trong manifest khi chạy ứng dụng bằng lệnh java -jar như thế nào?
Bạn sẽ xác định khi nào cần khai báo Class-Path trong manifest và những giới hạn của cách tham chiếu dependency này ra sao?
Bạn sẽ phân biệt classpath và module path của Java Platform Module System khi đóng gói ứng dụng như thế nào?
Bạn sẽ xử lý xung đột phiên bản thư viện khi nhiều dependency cùng chứa một class hoặc resource như thế nào?
Bạn sẽ giải thích thứ tự classpath có thể ảnh hưởng đến class được nạp và cách chẩn đoán NoSuchMethodError ra sao?
Bạn sẽ so sánh thin JAR, fat JAR và shaded JAR về kích thước, dependency và khả năng phân phối như thế nào?
Bạn sẽ lựa chọn cách đóng gói dependency trong executable JAR để tránh xung đột tài nguyên và service loader ra sao?
Bạn sẽ mô tả cách cấu trúc WAR và vai trò của WEB-INF, web.xml cùng thư viện ứng dụng như thế nào?
Bạn sẽ phân biệt triển khai WAR lên servlet container với chạy executable JAR có embedded server ra sao?
Bạn sẽ xác định cách quản lý servlet API và dependency được container cung cấp để tránh đóng gói trùng lặp như thế nào?
Bạn sẽ thiết kế bản phân phối dạng archive gồm bin, lib, conf và thư mục dữ liệu sao cho dễ cài đặt và nâng cấp như thế nào?
Bạn sẽ phân biệt artifact dùng để triển khai với artifact dùng để tái sử dụng làm dependency trong dự án khác ra sao?
Bạn sẽ xác minh artifact có đầy đủ manifest, dependency và tài nguyên cần thiết trước khi phát hành như thế nào?
Bạn sẽ thiết kế quy ước version và tên artifact để xác định rõ ứng dụng, phiên bản và biến thể build ra sao?
Bạn sẽ xử lý tài nguyên cấu hình hoặc file mặc định khi đóng gói để không ghi đè dữ liệu vận hành của môi trường đích như thế nào?
Bạn sẽ giải thích layered executable JAR giúp tận dụng cache layer container và tác động của nó đến quy trình build ra sao?
Bạn sẽ đánh giá rủi ro khi shading hoặc relocation package làm thay đổi reflection, service loader và metadata thư viện như thế nào?
Bạn sẽ phân biệt lệnh java -jar với lệnh java -cp khi cần truyền main class và dependency như thế nào?
Bạn sẽ xác định nguyên nhân ứng dụng chạy được trong IDE nhưng lỗi ClassNotFoundException sau khi đóng gói ra sao?
Bạn sẽ chẩn đoán lỗi NoClassDefFoundError hoặc LinkageError xuất hiện chỉ trong môi trường production bằng cách kiểm tra artifact và classpath như thế nào?
Bạn sẽ giải thích sự khác nhau giữa JDK, JRE và custom runtime image trong lựa chọn môi trường chạy ứng dụng ra sao?
Bạn sẽ sử dụng jlink để tạo runtime image chỉ gồm các module Java cần thiết cho ứng dụng như thế nào?
Bạn sẽ xác định module cần đưa vào custom runtime khi ứng dụng sử dụng reflection, service loader hoặc thư viện native ra sao?
Bạn sẽ đánh giá trade-off giữa runtime image nhỏ gọn với khả năng tương thích và thuận tiện khi vận hành như thế nào?
Bạn sẽ phân biệt jlink và jpackage theo mục tiêu tạo runtime image và bộ cài ứng dụng ra sao?
Bạn sẽ đóng gói ứng dụng thành installer bằng jpackage cho các hệ điều hành khác nhau như thế nào?
Bạn sẽ quản lý native library phụ thuộc hệ điều hành và kiến trúc CPU trong custom runtime hoặc installer ra sao?
Bạn sẽ xác định cách kiểm tra runtime image sau khi tạo để bảo đảm ứng dụng khởi động được trên máy không cài JDK như thế nào?
Bạn sẽ thiết kế quy trình build riêng cho từng nền tảng khi artifact chứa native dependency hoặc installer đặc thù ra sao?
Bạn sẽ cấu hình classpath cho thư mục lib có nhiều JAR mà không phụ thuộc vào wildcard hoặc thứ tự không xác định như thế nào?
Bạn sẽ sử dụng argument file của Java để quản lý danh sách classpath và JVM options dài như thế nào?
Bạn sẽ phân biệt JVM options, tên main class và application arguments để bảo đảm launcher truyền đúng tham số như thế nào?
Bạn sẽ tổ chức launch script trên Linux và Windows để truyền đúng tham số, xử lý dấu cách và mã thoát như thế nào?
Bạn sẽ thiết kế script khởi chạy không phụ thuộc vào thư mục làm việc hiện tại của người gọi như thế nào?
Bạn sẽ phân biệt JAVA_OPTS là quy ước của launch script với JDK_JAVA_OPTIONS và JAVA_TOOL_OPTIONS do JDK hỗ trợ như thế nào?
Bạn sẽ xác định cách cấu hình heap size, GC và system properties theo từng môi trường mà không sửa artifact như thế nào?
Bạn sẽ xử lý khác biệt quoting và expansion biến môi trường giữa shell Linux, PowerShell và Windows batch khi chạy Java ra sao?
Bạn sẽ thiết kế file cấu hình ngoài artifact và quy tắc ưu tiên giữa default, environment variable và command-line arguments như thế nào?
Bạn sẽ quản lý secret và credential cho ứng dụng Java mà không ghi chúng vào JAR, script hoặc process arguments ra sao?
Bạn sẽ lựa chọn cách cung cấp truststore, keystore và certificate cho ứng dụng theo môi trường triển khai như thế nào?
Bạn sẽ xác định working directory, log directory và thư mục ghi dữ liệu cần được tạo hoặc cấp quyền trước khi service khởi chạy ra sao?
Bạn sẽ thiết kế launch script trả đúng exit code và chuyển tiếp signal đến JVM để supervisor quản lý vòng đời như thế nào?
Bạn sẽ xác định các JVM flags nào nên được cấu hình rõ ràng và những flags nào nên để JVM tự điều chỉnh theo runtime như thế nào?
Bạn sẽ tính toán Xms và Xmx phù hợp với memory limit của container mà vẫn chừa chỗ cho native memory và thread stacks ra sao?
Bạn sẽ kiểm tra ứng dụng có nhận đúng JVM options sau khi chạy qua script, systemd hoặc container entrypoint như thế nào?
Bạn sẽ thiết kế startup timeout và graceful shutdown để ứng dụng hoàn tất khởi tạo và xử lý request đang chạy ra sao?
Bạn sẽ xác định readiness, liveness và startup health check khác nhau về mục tiêu và thời điểm kiểm tra như thế nào?
Bạn sẽ phân biệt tiến trình JVM đang chạy với ứng dụng đã sẵn sàng nhận traffic bằng phép kiểm tra nào?
Bạn sẽ thiết kế cơ chế xử lý SIGTERM, shutdown hook và thời hạn chờ trước khi supervisor gửi SIGKILL như thế nào?
Bạn sẽ xác định cách chạy ứng dụng Java dưới systemd với user, working directory, environment và restart policy phù hợp ra sao?
Bạn sẽ cấu hình Windows service wrapper hoặc service manager để quản lý JVM process và log như thế nào?
Bạn sẽ thiết kế log startup để phân biệt lỗi nạp cấu hình, lỗi dependency, lỗi bind port và lỗi khởi tạo ứng dụng ra sao?
Bạn sẽ xác minh cổng lắng nghe, health endpoint và truy vấn nghiệp vụ sau khi khởi chạy một bản phân phối mới như thế nào?
Bạn sẽ tổ chức Maven hoặc Gradle build để khóa phiên bản plugin, dependency và toolchain nhằm tăng tính tái lập ra sao?
Bạn sẽ phân biệt dependency declaration, dependency locking và dependency verification trong quy trình build Java như thế nào?
Bạn sẽ cố định JDK, locale, timezone và các đầu vào môi trường để hai lần build cùng source tạo artifact nhất quán ra sao?
Bạn sẽ xử lý timestamp trong archive, thứ tự file và metadata build để tạo JAR reproducible như thế nào?
Bạn sẽ xác định nguyên nhân cùng một commit nhưng tạo ra artifact có checksum khác nhau bằng cách kiểm tra những đầu vào nào?
Bạn sẽ thiết kế build pipeline tách compile, test, package và publish để có thể truy nguyên artifact đã phát hành như thế nào?
Bạn sẽ sử dụng checksum, chữ ký số và artifact repository để xác minh tính toàn vẹn cùng nguồn gốc gói phát hành ra sao?
Bạn sẽ quản lý SBOM và rà soát dependency dễ bị lỗ hổng trước khi phát hành artifact như thế nào?
Bạn sẽ phân biệt build artifact một lần rồi promote qua các môi trường với build lại riêng cho từng môi trường về tính nhất quán ra sao?
Bạn sẽ thiết kế container image Java bằng multi-stage build để tách môi trường biên dịch khỏi runtime như thế nào?
Bạn sẽ lựa chọn base image JRE hoặc JDK theo yêu cầu kích thước, công cụ chẩn đoán và bề mặt tấn công ra sao?
Bạn sẽ cố định base image bằng digest và quản lý cập nhật bản vá mà vẫn bảo đảm build có thể tái lập như thế nào?
Bạn sẽ sắp xếp Dockerfile layers để tận dụng cache dependency mà không làm lộ secret trong build layer ra sao?
Bạn sẽ thiết kế container image chạy bằng non-root user và chỉ cấp quyền ghi cho các thư mục cần thiết như thế nào?
Bạn sẽ xác định ENTRYPOINT và CMD phù hợp để cho phép truyền tham số bổ sung mà vẫn giữ JVM là tiến trình chính ra sao?
Bạn sẽ giải thích exec form và shell form trong Dockerfile ảnh hưởng đến PID 1 và signal handling như thế nào?
Bạn sẽ cấu hình JVM container awareness để nhận biết CPU và memory limit của container như thế nào?
Bạn sẽ phân biệt Docker HEALTHCHECK với readiness và liveness probe của Kubernetes về mục đích và cách sử dụng ra sao?
Bạn sẽ thiết kế Kubernetes startup, readiness và liveness probes để không restart ứng dụng trong thời gian warm-up hợp lệ như thế nào?
Bạn sẽ cấu hình resource requests và limits cho Java container dựa trên heap, native memory, CPU và tải thực tế ra sao?
Bạn sẽ lựa chọn biến môi trường, ConfigMap và Secret để cung cấp cấu hình runtime trong Kubernetes như thế nào?
Bạn sẽ xác định dữ liệu nào nên đặt trong image, volume hoặc external storage để hỗ trợ nâng cấp và rollback an toàn ra sao?
Bạn sẽ tổ chức log container qua stdout và stderr để hệ thống thu thập tập trung mà không cần ghi log vào layer của image như thế nào?
Bạn sẽ quản lý image tag bất biến và tránh triển khai nhầm image mới khi cùng một tag bị ghi đè ra sao?
Bạn sẽ thiết kế quy trình rolling update, canary hoặc blue-green để nâng cấp ứng dụng Java với thời gian gián đoạn thấp như thế nào?
Bạn sẽ xác định điều kiện rollback dựa trên startup failure, readiness, error rate và latency sau khi phát hành như thế nào?
Bạn sẽ bảo đảm phiên bản ứng dụng cũ tương thích với schema dữ liệu trong giai đoạn triển khai nhiều phiên bản đồng thời ra sao?
Bạn sẽ thiết kế smoke test sau triển khai để xác nhận artifact, cấu hình, kết nối dependency và health endpoint hoạt động như thế nào?
Nếu ứng dụng chạy được trên máy phát triển nhưng container báo ClassNotFoundException, bạn sẽ kiểm tra packaging, classpath và layer image như thế nào?
Nếu container thoát ngay sau khi JVM nhận SIGTERM, bạn sẽ kiểm tra PID 1, exec form và shutdown hook ra sao?
Nếu JVM bị OOMKilled dù Xmx thấp hơn memory limit, bạn sẽ tính đến metaspace, direct buffer, thread stack và native memory như thế nào?
Nếu bản build từ cùng commit tạo checksum khác nhau, bạn sẽ kiểm tra dependency, toolchain, timestamp và metadata archive theo thứ tự nào?
Nếu nâng cấp JAR khiến service khởi động được nhưng health check thất bại, bạn sẽ phân biệt lỗi cấu hình, dependency và startup timeout như thế nào?
Nếu cần phát hành một runtime Java nhỏ gọn cho môi trường không cài JDK, bạn sẽ quyết định giữa JRE image, jlink và jpackage theo tiêu chí nào?
Nếu rollback phiên bản ứng dụng nhưng cấu hình hoặc schema đã thay đổi, bạn sẽ thiết kế tương thích ngược và quy trình phục hồi ra sao?
