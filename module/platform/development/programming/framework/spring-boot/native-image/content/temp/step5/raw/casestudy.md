Một API Spring Boot chạy theo mô hình scale-to-zero có thời gian khởi động JVM quá dài khi lượng truy cập tăng đột biến; nhóm triển khai native image nhưng chưa có phép đo cold start tương đương trên cùng phần cứng.
Ứng dụng nhận hàng nghìn yêu cầu ngắn mỗi phút chạy trong container giới hạn bộ nhớ; bản native khởi động nhanh hơn nhưng chỉ số RSS và CPU ở tải ổn định chưa được đối chiếu với bản JVM.
Một dịch vụ báo giá có nhiều bean chỉ dùng vào lần gọi đầu tiên; sau khi biên dịch Spring AOT, thời gian startup giảm nhưng request đầu tiên vẫn chậm vì còn phải khởi tạo kết nối đến nhà cung cấp.
Nhóm phát triển đánh giá lợi ích native bằng thời gian chạy lệnh trong máy cá nhân; số liệu khác đáng kể so với thời gian pod đạt readiness trên cụm Kubernetes có startup probe.
Ứng dụng Spring Boot sử dụng profile để bật các bean theo môi trường; bản native được build với cấu hình test nhưng khi triển khai production, các điều kiện build-time khiến một thành phần cần thiết không tồn tại.
Dịch vụ thanh toán đăng ký bean dựa vào một thuộc tính cấu hình được lấy từ secret lúc chạy; kết quả AOT analysis không phản ánh cách hệ thống thay đổi điều kiện tạo bean sau khi binary đã được biên dịch.
Nhóm tích hợp tự đăng ký BeanDefinition sau khi ApplicationContext đã bắt đầu làm mới; luồng JVM hoạt động bình thường nhưng bản native bỏ sót các thành phần được tạo động này.
Một thư viện nội bộ quét classpath lúc runtime để tìm processor mới; sau khi tạo native image, các processor chỉ được phát hiện khi tính năng tương ứng được kích hoạt mới bị thiếu.
Ứng dụng dùng Class.forName để tải bộ chuyển đổi dữ liệu dựa vào tên class trong file cấu hình ngoài; binary native chạy được cho kiểu mặc định nhưng lỗi khi khách dùng bộ chuyển đổi khác.
Một nền tảng cài plugin nghiệp vụ bằng tệp JAR sau khi ứng dụng đã triển khai; bản native không tìm thấy class plugin mới dù cơ chế nạp động hoạt động trên JVM.
Nhóm phát triển dùng BeanFactoryPostProcessor để thay đổi định nghĩa bean dựa trên một danh sách lấy từ database; kết quả khởi động native khác bản JVM vì thay đổi không nằm trong dữ liệu có thể phân tích trước khi build.
Một ứng dụng cấu hình điều kiện cho nhiều auto-configuration tùy thư viện có mặt trên classpath; sau khi đổi dependency, bản native được build lại nhưng báo thiếu bean ở một nhánh ít được sử dụng.
Dịch vụ Spring Boot có custom annotation làm dấu thành phần cần đăng ký; khi sử dụng Spring AOT, một số thành phần chỉ được tạo bằng reflective scanning và không còn xuất hiện trong context.
Một API dùng Jackson chuyển JSON thành DTO có constructor không công khai; bản JVM deserialize bình thường nhưng native image thất bại khi nhận loại payload ít gặp.
Trung tâm dữ liệu nhận nhiều kiểu message với thuộc tính phân biệt loại đối tượng; thư viện Jackson chọn subtype bằng tên class, nhưng native image chỉ đọc được các subtype được dùng trong bài test cơ bản.
Nhóm tích hợp dùng reflection để đọc các field private của đối tượng khi tạo báo cáo; chức năng hoạt động trong JVM nhưng native image ném lỗi truy cập field khi chạy báo cáo cuối tháng.
Ứng dụng có module serialization cho một đối tượng Java record được truyền qua nhiều dịch vụ; binary native chỉ gặp lỗi khi body chứa trường tùy chọn không xuất hiện trong dữ liệu kiểm thử.
Một dịch vụ Spring Boot dùng Hibernate Validator với constraint annotation do doanh nghiệp tự viết; quá trình validate object có cấu trúc lồng nhau lỗi trên native vì thư viện truy cập metadata động.
Trung tâm vận tải sử dụng mapper tạo instance qua constructor phản chiếu; một model mới được thêm vào sau khi tạo metadata Native Image nên chỉ endpoint dùng model mới phát sinh lỗi.
Nhóm phát triển bổ sung RuntimeHints cho một nhóm DTO nhưng bỏ quên lớp model được tạo qua thư viện bên thứ ba; bản native build thành công nhưng một tính năng hiếm gặp không deserialize được.
Ứng dụng sử dụng proxy động để thêm audit vào interface dịch vụ; khi chạy native, proxy cho một interface mới không được tạo vì loại proxy đó không nằm trong metadata lúc build.
Một thư viện RPC dùng JDK dynamic proxy cho các client dịch vụ bên ngoài; phương thức bình thường hoạt động nhưng client bổ sung sau nâng cấp không khởi tạo được trong native image.
Dịch vụ báo cáo dùng AOP để ghi thời gian thực thi các bean cụ thể; bản native hoạt động nhưng một lời gọi qua proxy tự tạo không được intercept như khi chạy JVM.
Một ứng dụng gọi một thư viện sử dụng bytecode generation tại runtime để dựng bộ lọc truy vấn; thao tác đầu tiên kích hoạt tạo bytecode gặp lỗi chỉ trên binary native.
Nhóm thanh toán dùng thư viện mock hoặc proxy tạo class động trong mã ứng dụng production; trên native image, đường chạy ít gặp kích hoạt cơ chế tạo class mà runtime không hỗ trợ như JVM.
Một dự án Kotlin Spring Boot dùng DTO có constructor mặc định và tham số nullable; JVM binding vẫn hoạt động nhưng native image lỗi khi gọi API nhận cấu trúc JSON phức tạp.
Ứng dụng dùng Spring Data JPA với Hibernate entity có quan hệ lazy; khi build native, một endpoint trả dữ liệu đầy đủ còn endpoint khác gặp vấn đề proxy hoặc truy cập entity liên quan.
Một hệ thống quản lý tài khoản tạo repository dựa vào interface Spring Data; lần chạy native chỉ lỗi ở một phương thức truy vấn đặc biệt được gọi khi đối soát cuối ngày.
Nhóm dùng JDBC driver của cơ sở dữ liệu ít phổ biến; binary native có thể kết nối tới DB mặc định nhưng thất bại khi chuyển sang driver dự phòng được chọn bằng property lúc chạy.
Một dịch vụ áp dụng Flyway migration khi khởi động; binary native không tìm thấy một số file SQL trong classpath dù chúng có trong JAR khi chạy bằng JVM.
Ứng dụng dùng Liquibase với changelog XML tham chiếu nhiều file include; khi đóng gói native, một nhánh changelog theo profile bị bỏ khỏi resource khiến database không được nâng schema đầy đủ.
Dịch vụ mail dùng template HTML trong resources để tạo hóa đơn; chương trình JVM tải được template còn bản native báo không có template khi gửi email thật.
Một ứng dụng sinh PDF dùng font nằm trong resources; bản native vẫn tạo file nhưng ký tự tiếng Việt biến thành hình vuông do tài nguyên font không được truy cập như JVM.
Nhóm triển khai ứng dụng đa ngôn ngữ qua ResourceBundle; bản native chỉ hiển thị tiếng Anh vì các bundle tiếng Việt và tiếng Nhật không có trong image.
Ứng dụng xử lý dữ liệu CSV từ nhiều quốc gia; binary native đọc sai ký tự hiếm khi locale hoặc charset được chọn lúc chạy khác cấu hình build.
Trợ lý hỗ trợ khách hàng xuất hình ảnh từ file SVG đặt trong resources; bản native chỉ gặp lỗi khi người dùng yêu cầu định dạng hình có bộ xử lý hoặc resource không có mặt trong image.
Một API Spring Boot phục vụ static resources từ classpath; trang HTML được trả về nhưng một bộ icon nằm trong thư mục ít dùng biến mất sau bước native compilation.
Nhóm thiết kế API tài liệu dùng giao diện web từ thư viện bên thứ ba; bản native khởi động tốt nhưng các file JavaScript của trang tài liệu không được tìm thấy trong container.
Ứng dụng sử dụng ServiceLoader để chọn implementation mã hóa từ nhiều JAR; một provider hoạt động trên JVM nhưng không xuất hiện trong binary native khi chọn cấu hình nâng cao.
Một thư viện tích hợp dùng SPI để đăng ký nhiều parser; native compilation chỉ giữ parser được tham chiếu tĩnh khiến định dạng đầu vào hiếm không còn được xử lý.
Nhóm nâng cấp thư viện phụ thuộc có metadata reachability mới; lần build Native Image sau nâng cấp báo lỗi reflection, còn JVM test không phát hiện khác biệt nào.
Một thư viện bên thứ ba chưa hỗ trợ native image và phụ thuộc vào resource bundle cùng dynamic proxy; bản native build được nhưng lỗi runtime ở chức năng được kích hoạt lần đầu tại production.
Ứng dụng dùng bản thư viện có thư mục native-image metadata mâu thuẫn với RuntimeHints của dự án; sau cập nhật dependency, reflection được đăng ký khác trước và một endpoint ngừng hoạt động.
Nhóm phát triển thay phiên bản Spring Boot nhưng giữ Spring AOT output cũ trong cache build; native binary tạo ra có hành vi khác với bản build sạch từ cùng commit.
Máy build Maven có JDK khác phiên bản được hỗ trợ bởi bộ GraalVM cài đặt; tác vụ native compile thất bại trong CI dù chạy ứng dụng trên JVM vẫn thành công.
Một nhóm dùng Maven native profile trên máy local nhưng cấu hình pipeline release lại chạy package thông thường; artifact được đưa lên container không phải native executable như tiêu chí triển khai.
Dự án Gradle có nhiều module dùng toolchain JDK khác nhau; lệnh nativeCompile ở một module thất bại vì plugin Native Build Tools không nhận đúng compiler trong runner CI.
Nhóm lập trình chạy unit test JVM thành công rồi phát hành native binary mà không chạy nativeTest; một lỗi serialization chỉ xuất hiện khi binary nhận payload thực tế.
Một dự án chuyển từ Maven sang Gradle để thống nhất build; hai đường build dùng cách xử lý resource metadata khác nhau khiến bản native được tạo ra không có cùng chức năng.
Pipeline biên dịch GraalVM Native Image của một ứng dụng lớn thường hết bộ nhớ trong worker CI; cùng commit đôi khi build thành công trên máy nhiều RAM nhưng bị kill trên máy ít RAM.
Đội phát triển tăng số worker song song để rút ngắn native compilation; máy CI hết bộ nhớ khi nhiều image được build đồng thời, làm thời gian pipeline tổng thể tăng.
Ứng dụng có hàng nghìn class và nhiều thư viện phụ thuộc; native build kéo dài quá thời gian giới hạn của CI dù artifact JVM hoàn tất nhanh và kiểm thử nghiệp vụ đều đạt.
Nhóm sử dụng build cache cho Spring AOT và Native Build Tools; sau khi đổi dependency, một phần metadata cũ được dùng lại khiến kết quả build khó tái hiện giữa các runner.
Một doanh nghiệp muốn so sánh bản native của cùng mã nguồn được build trong hai tháng; các bản khác nhau về kích thước và thời gian khởi động vì môi trường GraalVM và cấu hình compile đã đổi.
Đội phát hành cần truy nguồn gốc native executable; hiện chỉ lưu commit SHA mà không lưu phiên bản GraalVM, JDK và tham số build nên khó phân tích hồi quy hiệu năng.
Nhóm biên dịch native executable trên Windows rồi cố chạy trực tiếp trong container Linux; chương trình không khởi động vì binary được tạo cho hệ điều hành khác.
Một dịch vụ chạy trên cả máy chủ x86_64 và ARM64; pipeline chỉ sinh native executable cho một kiến trúc nên lần triển khai trên node ARM gặp lỗi thực thi.
Đội triển khai chạy native binary trong container Alpine dùng musl; executable được liên kết với libc không tương thích nên lỗi xảy ra trước khi ứng dụng bắt đầu.
Ứng dụng native được xây dựng bằng buildpacks thành OCI image; sau khi đổi builder image, kích thước và thành phần hệ điều hành của container khác bản phát hành trước.
Nhóm chuyển container native sang distroless để giảm bề mặt tấn công; ứng dụng không còn tìm thấy chứng chỉ CA và kết nối HTTPS đến dịch vụ thanh toán thất bại.
Một microservice dùng HTTPS đến đối tác có chứng chỉ nội bộ; JAR JVM tìm truststore ngoài thành công nhưng binary native trong container tối giản báo lỗi TLS handshake.
Ứng dụng Spring Boot bản native xử lý tên miền nội bộ; kết quả DNS trong container khác khi chạy JVM trên máy phát triển khiến API khởi động được nhưng không gọi tới backend.
Một hệ thống cần chuyển dữ liệu có dấu thời gian theo timezone địa phương; native executable chạy trong container thiếu timezone data nên báo cáo khác với kết quả JVM.
Nhóm bảo mật cấu hình thuật toán mã hóa hiếm dùng cho một đối tác cũ; native image chỉ phát hiện lỗi khi yêu cầu thực tế cần provider hoặc thuật toán không sẵn sàng.
Ứng dụng ký số dùng thư viện gọi JNI tới native library của nhà cung cấp; binary Native Image khởi động nhưng thao tác ký điện tử thất bại ở thiết bị đầu tiên.
Một dịch vụ xử lý ảnh gọi thư viện native phụ thuộc vào thư viện hệ thống; khi chuyển container từ JVM sang native, API trả lỗi cho tệp lớn dù các test không cần thư viện này vẫn đạt.
Ứng dụng quản lý kho có thư viện dùng JNA để truy vấn thiết bị ngoại vi; thao tác đọc trạng thái thiết bị chỉ lỗi ở native image do đường tải thư viện và metadata khác môi trường JVM.
Nhóm sử dụng một SDK tự tải tài nguyên theo đường dẫn tương đối với JAR; khi chạy native executable ngoài thư mục dự án, SDK không tìm được tệp cấu hình mà nó mong đợi.
Ứng dụng khởi tạo một singleton có giá trị lấy từ biến môi trường lúc class được initialize; khi build native image, giá trị của máy build bị giữ lại khiến binary production dùng endpoint sai.
Một thư viện tạo mã định danh khởi tạo bộ sinh số ngẫu nhiên trong static initializer; khi chuyển sang native, nhóm phát hiện trạng thái khởi tạo giữa bản build và bản chạy cần được kiểm chứng.
Dịch vụ phân phối tính ngày hết hạn bằng timezone đọc trong static field; native binary hoạt động khác giữa hai khu vực triển khai dù file cấu hình runtime giống nhau.
Nhóm thay đổi chiến lược class initialization của GraalVM để giảm startup time; một thư viện ghi log và mở socket ngay khi khởi tạo khiến native compilation hoặc startup phát sinh tác dụng ngoài ý muốn.
Ứng dụng tạo thread pool trong static initializer của một thư viện giám sát; quá trình phân tích build-time gặp lỗi vì trạng thái thread không thể chuyển an toàn vào executable.
Một ứng dụng native lấy Spring profile từ biến môi trường khi bắt đầu; một số bean được quyết định trong AOT processing khác với profile thực tế dùng khi chạy binary tại production.
Nhóm sử dụng cấu hình externalized để thay đổi địa chỉ database mà không build lại; một thư viện lại đóng cứng endpoint vào trạng thái khởi tạo lúc build khiến deployment tới vùng dự phòng lỗi.
Ứng dụng có feature flag điều khiển loại implementation được tạo bằng reflection; feature mới không thể kích hoạt trên native binary đã triển khai dù chỉ thay đổi file cấu hình.
Dịch vụ Spring Security dùng JWT với thuật toán khác nhau theo nhà cung cấp; một loại token production không được xác minh trong native image dù token test phổ biến vẫn hoạt động.
Một ứng dụng REST sử dụng custom authentication provider được nạp từ classpath; JVM nhận cấu hình nhưng native executable không phát hiện provider ở một môi trường có nhiều tổ chức đăng nhập.
Dịch vụ Kafka consumer trong ứng dụng Spring Boot native xử lý payload Avro; bản native nhận được message nhưng thất bại khi nạp schema hoặc tạo serializer cho một event type ít dùng.
Nhóm chạy Spring Batch dưới dạng native executable để giảm thời gian khởi động job; dữ liệu vẫn được xử lý nhưng một ItemReader tạo động không được khởi tạo ở bước import hiếm gặp.
Ứng dụng WebFlux chạy native có luồng HTTP dài và sử dụng Reactor scheduler; sau khi triển khai, giới hạn số thread và chi phí xử lý khác JVM khiến mức sử dụng CPU tăng ở tải ổn định.
Nhóm tích hợp một thư viện GraphQL tự quét schema resolver bằng reflection; native executable trả lời truy vấn đơn giản nhưng một mutation bị thiếu từ schema lúc chạy.
Một dự án dùng thư viện OpenAPI để sinh đặc tả từ annotation ở runtime; bản native trả 404 hoặc thiếu endpoint documentation dù các REST endpoint nghiệp vụ vẫn hoạt động.
Ứng dụng Spring Boot native ghi metrics qua Micrometer; dashboard hiển thị thời gian khởi động nhưng không có một số tag ứng dụng được tạo bởi bean chỉ được dùng khi request đầu tiên chạy.
Nhóm triển khai OpenTelemetry cho native executable; trace của request HTTP vẫn có nhưng span từ một thư viện instrument qua dynamic proxy biến mất sau chuyển từ JVM.
Đội vận hành bật Actuator health và readiness trên bản native; một health indicator dùng class được tạo phản chiếu chỉ lỗi ở môi trường production khi kết nối tới broker đang chậm.
Một hệ thống native khởi động rất nhanh nhưng kết nối pool database chưa có dữ liệu sẵn; readiness được báo UP trước khi request giao dịch đầu tiên có thể chạy đúng.
Nhóm đặt startup probe của Kubernetes theo tốc độ khởi động native mới; lần chạy đầu sau khi node khởi động lạnh vẫn thất bại vì phần khởi tạo mạng và database không nằm trong phép đo startup.
Ứng dụng native nhận SIGTERM khi rolling deployment; các tác vụ nền chưa flush hàng đợi nhưng termination grace period vẫn lấy từ cấu hình cũ của bản JVM.
Một dịch vụ gửi thông báo dùng graceful shutdown trên native executable; việc đóng client broker và flush message chậm hơn thời gian cho phép khiến một số thông báo bị phát lại.
Nhóm vận hành so thời gian startup của JVM và native theo log ghi 'Started Application'; số đo bỏ qua thời gian kéo image từ registry và bắt đầu container nên không phản ánh trễ phục vụ người dùng.
Một API native có footprint bộ nhớ thấp khi nhàn rỗi nhưng tiêu thụ CPU cao hơn JVM dưới tải liên tục; quyết định chuyển toàn bộ hệ thống dựa vào RSS lúc startup làm chi phí vận hành tăng.
Trung tâm dữ liệu đo heap được dùng trên JVM nhưng lấy RSS của tiến trình native để so sánh; báo cáo kết luận sai rằng cùng một loại bộ nhớ đang được giảm theo tỷ lệ tương ứng.
Một ứng dụng native có p95 latency tốt ở tải nhẹ nhưng p99 tăng khi chạy nhiều luồng ghi dữ liệu; nhóm vận hành chưa có bộ kiểm thử hiệu năng tương đương cả hai runtime.
Dịch vụ hỗ trợ khách hàng chạy native image và đặt giới hạn RAM thấp; khi nhiều người dùng mở kết nối đồng thời, tiến trình bị OOM kill dù số đo bộ nhớ nền nhỏ.
Nhóm phát hành tăng mức tối ưu native compiler để cải thiện throughput; binary lớn hơn nhiều và thời gian build tăng, trong khi tỷ lệ lỗi nghiệp vụ vẫn chưa được đánh giá lại.
Đội vận hành phát hiện một bản native mới có tốc độ xử lý chậm hơn; hệ thống chỉ lưu model CPU và kích thước binary mà không gắn kết số liệu với phiên bản compiler và tham số tối ưu.
Ứng dụng được đóng gói thành native container nhỏ; công cụ quét lỗ hổng chỉ liệt kê thư viện của hệ điều hành và nhóm bảo mật khó đối chiếu dependency Java đã được biên dịch vào binary.
Nhóm quản lý SBOM muốn biết thư viện nào nằm trong native executable; bản phát hành chỉ đính kèm dependency tree lúc build và không phản ánh các phần mã thực sự được giữ sau reachability analysis.
Một đội cập nhật thư viện do cảnh báo CVE rồi build lại native image; pipeline triển khai vẫn lấy executable cũ từ cache khiến bản chạy không chứa bản sửa đã được kiểm thử.
Dịch vụ native thiếu các công cụ shell và chẩn đoán JVM trong image tối giản; khi hệ thống gặp deadlock, nhóm vận hành không thể áp dụng cách lấy thread dump quen thuộc như trước.
Trong đợt production incident, một native process bị crash mà không có stack trace Java đầy đủ; nhóm phát triển chưa có ký hiệu debug và build metadata để đối chiếu với executable đã phát hành.
Nhóm triển khai dùng tracing agent khi chạy JVM để quan sát reflection và resource; bộ test ghi trace chỉ bao phủ API phổ biến, còn một luồng nghiệp vụ đặc biệt không được ghi lại trước native build.
Ứng dụng có tính năng chỉ chạy vào cuối tháng; các bài native integration test không gọi nhánh này nên thiếu metadata cho một kiểu DTO và lỗi chỉ xuất hiện tại đợt đối soát đầu tiên.
Đội kiểm thử bổ sung smoke test cho executable biên dịch bằng Spring AOT và GraalVM nhưng chỉ kiểm tiến trình mở cổng; một đường dẫn gọi converter tùy biến lỗi trên native dù readiness và HTTP health đều bình thường.
Nhóm phát triển dùng Testcontainers để kiểm tra ứng dụng native với PostgreSQL; môi trường CI không cấp quyền Docker nên các bài integration test thật bị bỏ qua ở nhánh phát hành.
Một hệ thống CI chạy nativeTest trên một kiến trúc x86_64; bản phát hành cho ARM64 được build ở pipeline khác nhưng chưa kiểm thử một thư viện JNI phụ thuộc kiến trúc.
Đội QA chạy cùng tập contract test trên JVM và native; chỉ bản native xử lý lỗi khác ở payload JSON thiếu field, nhưng báo cáo aggregate vẫn chỉ thể hiện tổng số case đạt.
Ứng dụng dùng thư viện bản địa có đường dẫn resource khác khi chạy container; các test native trên host đều qua nhưng bản OCI image production thất bại ở chức năng xuất báo cáo.
Nhóm vận hành rollback native image sau khi phát hiện lỗi reflection; chỉ đổi tag container trong khi schema database đã được nâng bởi bản mới khiến binary cũ không tương thích.
Doanh nghiệp chuẩn hóa một JAR và một native executable từ cùng commit; sau mỗi release, môi trường fallback JVM chạy tốt nhưng native được cấu hình khác khiến việc so sánh độ trễ và lỗi không còn công bằng.
Một nhóm triển khai native image cho nhiều dịch vụ Spring Boot; chi phí máy build tăng đột ngột do native compilation chiếm CPU và RAM cao, trong khi tiết kiệm bộ nhớ runtime chưa được đo theo tổng chi phí.
Ứng dụng quản lý hóa đơn chuyển sang native để tăng mật độ pod trên một node; số container chạy được nhiều hơn nhưng giới hạn file descriptor và kết nối database trở thành nút thắt mới.
Một service phải duy trì khả năng đọc cấu hình mật khẩu và chứng chỉ được mount lúc chạy; native build đã được ký và phát hành nhưng một thuộc tính được đọc ở build time khiến xoay vòng secret không có hiệu lực.
