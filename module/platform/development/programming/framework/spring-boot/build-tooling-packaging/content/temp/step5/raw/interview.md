Bạn mô tả toàn bộ hành trình từ mã nguồn Spring Boot đến artifact có thể chạy trong production như thế nào?
Bạn phân biệt compile, test, package, publish và deploy trong vòng đời build của một ứng dụng Spring Boot ra sao?
Bạn chọn Maven hay Gradle cho một dự án Spring Boot mới dựa trên tiêu chí kỹ thuật và vận hành nào?
Bạn đánh giá tốc độ build, khả năng mở rộng và kinh nghiệm đội ngũ khi so sánh Maven với Gradle như thế nào?
Vì sao artifact đã build cần được giữ bất biến khi chuyển qua nhiều môi trường triển khai?
Bạn tổ chức ranh giới giữa build-time configuration và runtime configuration trong Spring Boot ra sao?
Bạn xác định thông tin nào cần cố định khi build và thông tin nào nên truyền bằng biến môi trường khi chạy?
Bạn phân biệt thư viện Java thông thường với ứng dụng Spring Boot tự khởi chạy trong cách đóng gói như thế nào?
Bạn đánh giá lựa chọn triển khai JAR, WAR hoặc container image theo môi trường chạy nào?
Bạn thiết kế quy trình build để nhà phát triển và CI nhận được kết quả nhất quán ra sao?
Bạn xác định các nguyên nhân phổ biến khiến build thành công trên máy cá nhân nhưng thất bại trong CI như thế nào?
Bạn xây dựng chính sách version cho artifact và source commit để truy vết một bản phát hành ra sao?
Bạn phân biệt build một lần rồi deploy nhiều môi trường với rebuild riêng cho từng môi trường như thế nào?
Bạn đặt các quality gate nào trước khi một artifact được công nhận đủ điều kiện phát hành?
Bạn tổ chức các project con khi một hệ thống có nhiều service Spring Boot và thư viện dùng chung ra sao?
Bạn lựa chọn chiến lược chia sẻ cấu hình build giữa các repository mà không khóa chặt việc nâng cấp như thế nào?
Bạn xác định trách nhiệm của build tool khác với trách nhiệm của CI pipeline ra sao?
Bạn kiểm soát những yếu tố nào có thể khiến cùng source code tạo ra các file artifact khác nhau?
Bạn quản lý vòng đời hỗ trợ JDK và Spring Boot khi nhiều dịch vụ dùng phiên bản khác nhau như thế nào?
Bạn đánh giá trade-off giữa build nhanh, bảo mật chuỗi cung ứng và khả năng truy xuất nguồn gốc artifact như thế nào?
Bạn mô tả vai trò của pom.xml trong một dự án Spring Boot dùng Maven như thế nào?
Bạn phân biệt dependency, plugin, property và profile trong một Maven POM ra sao?
Bạn phân biệt clean lifecycle với default lifecycle và các phase validate, compile, test, package, verify, install của Maven ra sao?
Bạn phân biệt Maven goal với Maven phase khi cấu hình build plugin ra sao?
Bạn xác định khi nào cần chạy mvn verify thay vì chỉ mvn package trong CI?
Bạn xử lý sự khác nhau giữa plugin version và dependency version trong Maven ra sao?
Bạn đánh giá lợi ích của spring-boot-starter-parent so với tự quản lý parent POM như thế nào?
Bạn tổ chức parent POM của công ty khi vẫn muốn dùng Spring Boot BOM ra sao?
Bạn phân biệt kế thừa parent POM với import BOM qua dependencyManagement như thế nào?
Bạn xác định vai trò của maven-compiler-plugin và Java release target trong quá trình build ra sao?
Bạn cấu hình Maven Toolchains để hạn chế lệch phiên bản JDK giữa các môi trường như thế nào?
Bạn tổ chức resource filtering mà không vô tình đưa password hoặc secret vào JAR ra sao?
Bạn phân biệt nguồn resource trong src/main/resources với tài nguyên chỉ phục vụ test như thế nào?
Bạn xử lý xung đột resource cùng tên từ nhiều dependency khi đóng gói như thế nào?
Bạn chọn test framework và Maven Surefire cho unit tests trong dự án Spring Boot theo yêu cầu nào?
Bạn dùng Maven Failsafe để chạy integration tests riêng với unit tests như thế nào?
Bạn đánh giá rủi ro dùng cờ bỏ qua test khi pipeline chuẩn bị xuất bản artifact như thế nào?
Bạn thiết kế Maven profile cho các biến thể build mà không biến profile thành runtime environment cố định ra sao?
Bạn kiểm tra profile nào đang có hiệu lực khi bản build thiếu dependency hoặc plugin cấu hình như thế nào?
Bạn xử lý dependency chỉ cần ở compile-time nhưng không được đưa vào runtime artifact ra sao?
Bạn phân biệt optional dependency và scope provided trong Maven với các ảnh hưởng transitives như thế nào?
Bạn chọn cách cấu hình annotation processor của Lombok hoặc MapStruct để build nhất quán như thế nào?
Bạn phát hiện Maven dependency resolution kéo về phiên bản khác dự kiến bằng những công cụ nào?
Bạn xác định cách dùng effective POM để chẩn đoán cấu hình bị ghi đè qua nhiều parent như thế nào?
Bạn kiểm soát cấu hình mirror và repository nội bộ trong Maven settings.xml theo nguyên tắc nào?
Bạn phân biệt repository dùng tải dependency với repository dùng deploy artifact như thế nào?
Bạn thiết kế cơ chế quản lý credentials của Maven repository mà không commit secret như thế nào?
Bạn đánh giá sự khác nhau giữa mvn install và mvn deploy trong quy trình phát hành ra sao?
Trong những trường hợp nào một module thư viện nên phát hành JAR thông thường thay vì Spring Boot executable JAR?
Bạn tổ chức build plugin executions trong dự án Maven nhiều module để tránh repackage nhầm thư viện ra sao?
Bạn dùng Maven dependency tree để phân tích xung đột phiên bản và loại trừ dependency như thế nào?
Bạn thiết kế chính sách cấm dependency bị lỗi bảo mật bằng Maven plugin hoặc quality gate như thế nào?
Bạn xử lý trường hợp Maven chỉ build thành công khi local repository còn artifact cũ như thế nào?
Bạn xác định nguyên nhân lệnh Maven chạy offline thất bại dù dự án đã từng build thành công ra sao?
Bạn kiểm soát Java toolchain và Maven wrapper để người khác tái hiện build trên máy mới như thế nào?
Bạn phân biệt build.gradle Groovy DSL với build.gradle.kts Kotlin DSL về khả năng bảo trì như thế nào?
Bạn giải thích vai trò của settings.gradle và project structure trong Gradle multi-project build ra sao?
Bạn tổ chức plugin Spring Boot trong Gradle và phân biệt với plugin Java ra sao?
Bạn xác định các task bootJar, jar và bootRun có mục đích khác nhau như thế nào?
Bạn lựa chọn dùng bootJar hay jar cho một module Spring Boot ứng dụng và một module thư viện ra sao?
Bạn sử dụng task dependencies để bảo đảm test và package chạy theo thứ tự hợp lệ như thế nào?
Bạn phân biệt task configuration với task execution trong Gradle và ảnh hưởng đến tốc độ build ra sao?
Bạn sử dụng Gradle Wrapper để khóa phiên bản build tool cho cả nhóm như thế nào?
Bạn quản lý Gradle plugins ở mức root hoặc convention plugins trong dự án nhiều module ra sao?
Bạn lựa chọn precompiled script plugin thay cho sao chép cấu hình Gradle giữa các module theo tiêu chí nào?
Bạn phân biệt api, implementation, compileOnly và runtimeOnly trong dependency configurations của Gradle ra sao?
Bạn xác định ảnh hưởng của annotationProcessor configuration tới compile classpath và artifact cuối như thế nào?
Bạn quản lý testImplementation, testRuntimeOnly và custom source sets trong kiểm thử ra sao?
Bạn sử dụng java toolchains trong Gradle để bảo đảm JDK dùng compile và test phù hợp như thế nào?
Bạn kiểm tra phiên bản Java thực tế của Gradle daemon khác gì Java toolchain dùng compile ra sao?
Bạn quyết định bật configuration cache trong Gradle dựa trên mức độ tương thích các plugin như thế nào?
Bạn đánh giá build cache khác configuration cache về dữ liệu tái sử dụng và rủi ro như thế nào?
Bạn xác định khi nào incremental compilation giúp ích và khi nào task vẫn phải chạy toàn bộ ra sao?
Bạn tìm nguyên nhân một Gradle task luôn ở trạng thái out-of-date bằng những dấu hiệu nào?
Bạn tối ưu Gradle daemon và parallel execution khi máy CI có CPU và RAM giới hạn như thế nào?
Bạn phát hiện dependency được resolve khác nhau giữa các Gradle configurations bằng cách nào?
Bạn sử dụng dependencyInsight để điều tra xung đột phiên bản trong Gradle như thế nào?
Bạn quản lý Gradle version catalog cho nhiều thư viện mà không nhầm nó với BOM của Spring Boot ra sao?
Bạn áp dụng dependency locking trong Gradle để tránh phiên bản transitives thay đổi bất ngờ như thế nào?
Bạn tổ chức Gradle dependency verification nhằm kiểm tra checksum hoặc chữ ký artifact như thế nào?
Bạn lựa chọn Gradle native platform BOM import thay cho plugin dependency-management theo những tiêu chí nào?
Bạn cấu hình bootWar cho ứng dụng Spring Boot cần triển khai lên servlet container ngoài như thế nào?
Bạn giải thích ảnh hưởng của việc tắt jar task nhưng giữ bootJar task trong Gradle ra sao?
Bạn thiết kế Gradle build scan hoặc profile để tìm điểm nghẽn build trong CI như thế nào?
Bạn kiểm tra Gradle build cache hit không tạo ra output không hợp lệ khi thay đổi build inputs như thế nào?
Bạn xử lý trường hợp Gradle plugin dùng API cũ không còn tương thích với Gradle phiên bản mới ra sao?
Bạn xác định những task cần thiết để phát hành artifact Gradle đến Maven-compatible repository như thế nào?
Bạn phân biệt dependency BOM, dependency constraints và lockfile theo mục đích quản lý phiên bản ra sao?
Bạn giải thích vai trò của spring-boot-dependencies BOM trong việc đồng bộ các phiên bản thư viện như thế nào?
Bạn lựa chọn khi nào nên tuân theo phiên bản dependency do Spring Boot quản lý thay vì tự override?
Bạn đánh giá rủi ro override một dependency cốt lõi khác phiên bản tương thích đã được kiểm thử ra sao?
Bạn dùng dependencyManagement của Maven để áp phiên bản mặc định mà không buộc mọi module phải phụ thuộc thư viện như thế nào?
Bạn giải thích vì sao import BOM không tự bổ sung dependency vào classpath ra sao?
Bạn xác định cách phối hợp nhiều BOM khi các thư viện có yêu cầu phiên bản xung đột như thế nào?
Bạn kiểm tra thứ tự và quy tắc ưu tiên dependency management khi nhiều BOM được import ra sao?
Bạn dùng Maven Enforcer để ngăn phụ thuộc trùng phiên bản hoặc Java version sai như thế nào?
Bạn phân biệt Maven nearest-wins dependency mediation với kiểm soát phiên bản qua dependencyManagement như thế nào?
Bạn xác định ảnh hưởng của exclude transitive dependency tới runtime khi thư viện cần một API phụ thuộc ra sao?
Bạn phát hiện lỗi NoSuchMethodError do phiên bản thư viện bị lệch qua các dependency như thế nào?
Bạn điều tra ClassNotFoundException khi dependency có mặt ở test scope nhưng thiếu ở runtime ra sao?
Bạn phân biệt SNAPSHOT dependency với immutable release dependency trong quản trị artifact như thế nào?
Bạn đặt chính sách không dùng dynamic version hoặc version range không kiểm soát trong release build như thế nào?
Bạn kiểm tra dependency graph khác nhau giữa máy dev và CI do cache hoặc repository như thế nào?
Bạn quyết định khi nào cần cập nhật Spring Boot BOM để vá bảo mật thay vì override từng thư viện?
Bạn tổ chức kiểm thử hồi quy sau khi nâng BOM để phát hiện thay đổi ABI hoặc hành vi transitive ra sao?
Bạn quản lý license của third-party dependencies và xuất báo cáo tuân thủ khi build như thế nào?
Bạn thiết kế cảnh báo dependency đã end-of-life hoặc bị bỏ bảo trì trong một ứng dụng Spring Boot ra sao?
Bạn kiểm tra nguồn gốc artifact tải về để giảm nguy cơ dependency confusion như thế nào?
Bạn phân biệt khóa phiên bản Maven Wrapper/Gradle Wrapper với khóa phiên bản JDK và dependencies như thế nào?
Bạn thiết kế cơ chế cập nhật dependency tự động nhưng vẫn có người review và kiểm thử như thế nào?
Bạn xác định bản build có cần repository mirror nội bộ khi dịch vụ public package registry bị lỗi như thế nào?
Bạn kiểm tra Maven dependency tree và Gradle dependencies có giải quyết ra cùng version khi di chuyển build tool hay không ra sao?
Bạn đánh giá rủi ro thay một thư viện qua shading mà không cập nhật thông tin license hoặc SBOM như thế nào?
Bạn giải thích mục đích của spring-boot-maven-plugin và khác biệt với compiler plugin ra sao?
Bạn mô tả tác dụng của Maven goal repackage lên JAR thông thường như thế nào?
Bạn phân biệt executable JAR Spring Boot với JAR chỉ chứa class và manifest thông thường như thế nào?
Vì sao executable JAR chứa các runtime dependencies có thể chạy mà không cần cài riêng những thư viện này?
Bạn xác định vai trò của BOOT-INF/classes và BOOT-INF/lib trong cấu trúc Spring Boot executable JAR như thế nào?
Bạn mô tả cách Spring Boot Loader tải lớp ứng dụng và nested dependency JAR ra sao?
Bạn phân biệt Main-Class của launcher với Start-Class chứa main method của ứng dụng như thế nào?
Bạn kiểm tra MANIFEST.MF để chẩn đoán executable JAR không tìm thấy entry point như thế nào?
Bạn đánh giá sự khác biệt giữa launcher trong các phiên bản Spring Boot và tác động tới việc tự viết packaging tool ra sao?
Bạn giải thích vì sao cách chạy java -jar khác việc thêm executable JAR trực tiếp vào classpath của một ứng dụng khác ra sao?
Bạn sử dụng java -jar để truyền Spring profiles hoặc application arguments mà không rebuild ra sao?
Bạn lựa chọn layout và launcher của executable archive dựa trên yêu cầu triển khai và khả năng hỗ trợ của phiên bản Spring Boot ra sao?
Bạn kiểm tra dependency nested trong executable JAR khi runtime báo class không tìm thấy như thế nào?
Bạn phân biệt spring-boot:run với chạy executable JAR đã được đóng gói về classpath và cấu hình như thế nào?
Bạn đánh giá ảnh hưởng của plugin repackage đối với artifact source và artifact dành cho module downstream ra sao?
Bạn lựa chọn classifier cho executable artifact khi cần giữ lại JAR gốc cho thư viện dùng chung như thế nào?
Bạn tổ chức dependency provided trong JAR và WAR để tránh đóng gói sai runtime dependencies như thế nào?
Bạn so sánh fat JAR, uber JAR và Spring Boot nested JAR theo cấu trúc bên trong như thế nào?
Bạn đánh giá rủi ro khi công cụ đóng gói hoặc giải nén không hiểu cấu trúc nested JAR của Spring Boot như thế nào?
Bạn lựa chọn đóng gói Spring Boot WAR thay vì JAR khi có servlet container được doanh nghiệp quản lý như thế nào?
Bạn xác định vai trò của SpringBootServletInitializer khi triển khai WAR trong servlet container ngoài ra sao?
Bạn phân biệt cấu trúc WEB-INF/classes, WEB-INF/lib và WEB-INF/lib-provided trong executable WAR ra sao?
Bạn phân tích ảnh hưởng của container servlet có sẵn và servlet API scope đến classpath của WAR như thế nào?
Bạn xây dựng executable WAR có thể khởi chạy độc lập và được deploy lên container ngoài theo những điều kiện nào?
Bạn kiểm tra lỗi xung đột embedded servlet container với container được cung cấp khi deploy WAR như thế nào?
Bạn lựa chọn hình thức WAR dựa trên yêu cầu app server, vận hành và khả năng mở rộng như thế nào?
Bạn xử lý trường hợp một servlet container chỉ hỗ trợ Jakarta API khác phiên bản ứng dụng ra sao?
Bạn xác định cách đóng gói startup scripts hoặc service configuration mà không làm lệch artifact chuẩn ra sao?
Bạn phân tích lý do artifact executable không nên chứa secrets hoặc application-production.yml nhạy cảm như thế nào?
Bạn kiểm tra các dependency runtime thực tế trong JAR và so sánh với dependency graph như thế nào?
Bạn phân biệt lỗi compile thành công với lỗi ứng dụng không khởi động do classpath hoặc auto-configuration ra sao?
Bạn tổ chức smoke test chạy JAR mới build trong môi trường cô lập trước khi publish như thế nào?
Bạn phát hiện sai phiên bản Java bytecode khiến executable JAR không khởi chạy trên JRE đích như thế nào?
Bạn thiết kế artifact metadata để liên kết JAR/WAR với source commit, build time và SBOM ra sao?
Bạn giải thích layered JAR được sử dụng để tối ưu việc xây container image như thế nào?
Bạn phân biệt application layer với dependencies layer trong cấu trúc layer của Spring Boot như thế nào?
Bạn xác định điều kiện nào khiến một thay đổi code ứng dụng không phải rebuild tất cả các lớp dependency ra sao?
Bạn kiểm tra thông tin layers.idx trong executable archive và ý nghĩa thứ tự lớp như thế nào?
Bạn tùy chỉnh layer phân loại một module hoặc dependency khi xây image theo nhu cầu nào?
Bạn đánh giá ảnh hưởng của snapshot dependencies đối với khả năng tái sử dụng cache layer ra sao?
Bạn phân biệt việc giải nén layers của archive với chạy trực tiếp java -jar trong container như thế nào?
Bạn kiểm tra cơ chế jarmode phù hợp theo phiên bản Spring Boot trước khi viết Dockerfile đa tầng như thế nào?
Bạn thiết kế Dockerfile multi-stage để tách môi trường build khỏi runtime image như thế nào?
Bạn lựa chọn base image có JRE phù hợp với Java target và kiến trúc CPU như thế nào?
Bạn đánh giá sự khác nhau giữa distroless runtime image và JRE image có shell cho chẩn đoán như thế nào?
Bạn phân tích rủi ro sử dụng tag latest cho base image trong quá trình build production ra sao?
Bạn sử dụng image digest để cố định base image trong một bản build có thể kiểm chứng như thế nào?
Bạn xử lý thay đổi base image digest khi cần cập nhật CVE mà vẫn giữ tính truy xuất nguồn gốc ra sao?
Bạn tổ chức Dockerfile COPY và RUN theo thứ tự nào để tận dụng cache cho dependency và source code?
Bạn viết .dockerignore để tránh đưa target, build cache, file .git hoặc credentials vào build context ra sao?
Bạn đánh giá rủi ro vô tình COPY private key hoặc file môi trường vào một image layer như thế nào?
Bạn lựa chọn chạy container dưới non-root user và cấu hình quyền file theo nguyên tắc nào?
Bạn phân biệt ENTRYPOINT và CMD trong cách khởi động ứng dụng Spring Boot ở container như thế nào?
Bạn giải thích ảnh hưởng của exec form ENTRYPOINT tới tín hiệu SIGTERM và graceful shutdown như thế nào?
Bạn cấu hình JVM memory limit dựa trên cgroup container và nhu cầu heap/direct memory ra sao?
Bạn xác định cách truyền JVM options cho container mà không ghi cố định trong artifact như thế nào?
Bạn cân nhắc việc dùng JVM CDS, AOT hoặc cách tối ưu startup phù hợp với workload nào?
Bạn tổ chức HTTP healthcheck cho image và phân biệt với Kubernetes readiness probe ra sao?
Bạn đánh giá khi nào cần cấu hình writable volume cho log hoặc file tạm trong container ra sao?
Bạn lựa chọn môi trường filesystem read-only và các thư mục ghi tạm cần thiết như thế nào?
Bạn xác định cổng được khai báo bằng EXPOSE khác gì cổng thực sự được publish khi chạy container ra sao?
Bạn dùng docker build multi-platform khi cần hỗ trợ amd64 và arm64 theo điều kiện nào?
Bạn xác định ảnh hưởng của kiến trúc CPU khác nhau tới native dependencies và base image ra sao?
Bạn thiết kế image tag theo immutable version và Git commit để tránh triển khai nhầm ra sao?
Bạn kiểm tra container image đã build thực sự khởi chạy đúng Spring profile và version như thế nào?
Bạn đo size của từng image layer để tìm nguyên nhân image Spring Boot quá lớn ra sao?
Bạn tối ưu cache cho multi-stage Docker build khi CI chạy trên runner dùng một lần như thế nào?
Bạn đánh giá nguy cơ chạy package manager trong runtime stage khiến image tăng bề mặt tấn công như thế nào?
Bạn phân biệt Dockerfile thủ công với Cloud Native Buildpacks về mức kiểm soát và trách nhiệm vận hành như thế nào?
Bạn giải thích vai trò của builder image và run image trong quy trình Cloud Native Buildpacks như thế nào?
Bạn mô tả các giai đoạn phát hiện, dựng môi trường và xuất image trong Buildpacks theo mục đích như thế nào?
Bạn lựa chọn buildpacks khi muốn giảm việc duy trì Dockerfile nhưng vẫn cần image tùy biến như thế nào?
Bạn dùng spring-boot:build-image hoặc bootBuildImage để tạo image cho ứng dụng Spring Boot theo điều kiện nào?
Bạn xác định những yêu cầu về container daemon hoặc registry khi chạy build-image trong CI như thế nào?
Bạn cấu hình tên image, tags và registry credentials cho Spring Boot build-image như thế nào?
Bạn so sánh việc chọn builder image khác nhau tới phiên bản JDK và runtime stack ra sao?
Bạn lựa chọn Buildpacks phù hợp với Java target và chính sách doanh nghiệp như thế nào?
Bạn đánh giá cách Buildpacks xác định phiên bản Java khi source và môi trường CI có nhiều JDK ra sao?
Bạn tổ chức cache volume cho Buildpacks để tăng tốc build lặp lại mà không làm rò secret ra sao?
Bạn xác định sự khác nhau giữa build environment và launch environment trong Buildpacks như thế nào?
Bạn truyền cấu hình build-time cần thiết vào Buildpacks mà không đưa secret vào image ra sao?
Bạn quản lý trust và provenance của builder/run images được tải từ registry bên ngoài như thế nào?
Bạn đánh giá rủi ro dùng builder được cập nhật tự động làm image thay đổi dù code không đổi ra sao?
Bạn kiểm tra phiên bản Buildpack lifecycle và builder có đáp ứng chính sách bảo mật như thế nào?
Bạn so sánh layers tạo bởi Buildpacks với layers từ Dockerfile tự thiết kế về cache và debug ra sao?
Bạn quyết định có thể rebase image để cập nhật run image mà không rebuild ứng dụng dựa trên điều kiện nào?
Bạn kiểm chứng điều kiện tương thích stack trước khi rebase một image Buildpacks ra sao?
Bạn thiết kế kiểm thử ứng dụng sau khi cập nhật run image qua rebase như thế nào?
Bạn sử dụng metadata hoặc labels của image Buildpacks để truy nguồn dependency runtime ra sao?
Bạn tổ chức quy trình Buildpacks trong môi trường bị hạn chế internet hoặc chỉ có registry nội bộ ra sao?
Bạn đánh giá ảnh hưởng của native image build khi sử dụng Buildpacks so với JVM image ra sao?
Bạn chọn tiêu chí để quyết định dùng Spring Boot AOT hoặc GraalVM native image thay vì JVM image?
Bạn phân biệt build-time AOT processing với runtime behavior của ứng dụng Spring Boot như thế nào?
Bạn xác định những giới hạn reflection và resource configuration cần chú ý khi build native image ra sao?
Bạn đo lợi ích startup, memory và trade-off thời gian build khi chuyển sang native image như thế nào?
Bạn kiểm thử khả năng tương thích của thư viện bên thứ ba trước khi phát hành native executable ra sao?
Bạn quyết định giữ artifact JVM song song trong giai đoạn thử native image theo những tiêu chí nào?
Bạn giải thích thế nào là reproducible build và những thuộc tính nào phải giống nhau giữa hai lần build?
Bạn xác định các nguồn không xác định như timestamp, thứ tự file và đường dẫn máy build gây sai khác artifact ra sao?
Bạn cấu hình archive reproducibility cho Maven/Gradle và kiểm tra timestamp metadata như thế nào?
Bạn tổ chức cách so sánh SHA-256 artifact được build độc lập từ cùng một commit như thế nào?
Bạn phân biệt byte-for-byte reproducibility với việc hai artifact có hành vi chạy tương đương như thế nào?
Bạn kiểm soát phiên bản JDK, compiler, build plugins và OS để giảm sai khác build như thế nào?
Bạn quyết định có sử dụng hermetic build và network isolation trong CI theo yêu cầu nào?
Bạn xử lý dependency SNAPSHOT hoặc dynamic version làm build không tái lập bằng cách nào?
Bạn xác định ảnh hưởng của việc build lại từ tag Git không được bảo vệ tới provenance ra sao?
Bạn khóa version và checksum của Maven Wrapper hoặc Gradle Wrapper để tránh bị thay đổi công cụ build như thế nào?
Bạn kiểm tra Gradle Wrapper JAR và distribution URL theo các kiểm soát tin cậy nào?
Bạn thiết kế cơ chế cache dependencies không chấp nhận artifact bị thay đổi sau khi xuất bản ra sao?
Bạn xác định cách pin plugin versions thay vì dùng latest động trong build configuration như thế nào?
Bạn đánh giá rủi ro remote build cache bị poisoning và cách cô lập quyền ghi ra sao?
Bạn xác định cách chứng minh một artifact được build từ commit, pipeline và dependencies cụ thể như thế nào?
Bạn phân biệt artifact checksum, digital signature và build attestation trong kiểm chứng nguồn gốc như thế nào?
Bạn lựa chọn chuẩn nội dung nào để tạo Software Bill of Materials cho một Spring Boot artifact?
Bạn phân biệt SBOM theo định dạng SPDX với CycloneDX về mục đích trao đổi dữ liệu như thế nào?
Bạn dùng công cụ nào trong quy trình build để lập danh mục thư viện transitives và phiên bản thực tế?
Bạn đánh giá hạn chế của SBOM khi dependencies được tải hoặc phát sinh trong runtime như thế nào?
Bạn gắn SBOM vào JAR hoặc container image theo phương thức nào để người vận hành có thể truy tìm?
Bạn phân biệt thông tin dependency trong pom.xml với các thành phần thực sự có mặt trong image như thế nào?
Bạn kiểm tra sự khác biệt giữa SBOM ứng dụng và SBOM base image trước khi phát hành ra sao?
Bạn thiết kế quy trình quét lỗ hổng cho source dependencies, executable JAR và container image như thế nào?
Bạn xác định trường hợp scanner báo CVE nhưng phiên bản thư viện đã backport bản vá như thế nào?
Bạn phân loại phát hiện bảo mật theo mức độ khai thác, độ nghiêm trọng và tác động nghiệp vụ như thế nào?
Bạn đánh giá nguy cơ làm ngừng CI vì mọi CVE mà không phân biệt khả năng khai thác ra sao?
Bạn quản lý exception có thời hạn cho một CVE chưa có bản vá theo cơ chế kiểm toán nào?
Bạn phân biệt static source scan với dependency scan và image vulnerability scan như thế nào?
Bạn ký container image sau khi build bằng cơ chế nào để tránh giả mạo artifact trong registry?
Bạn xác minh chữ ký và provenance của container image trước khi cho phép triển khai bằng cách nào?
Bạn giải thích mục đích của artifact attestation trong chuỗi cung ứng phần mềm như thế nào?
Bạn thiết kế policy chỉ chấp nhận image do pipeline được phê duyệt tạo ra như thế nào?
Bạn đánh giá mối liên hệ giữa SLSA controls và năng lực hiện tại của pipeline build ra sao?
Bạn giảm rủi ro dependency confusion khi private package và public package có cùng tọa độ tên như thế nào?
Bạn ngăn một dependency có post-install script hoặc Gradle plugin độc hại truy cập CI secrets như thế nào?
Bạn tổ chức quyền truy cập mạng của CI build runner để giới hạn rủi ro mã build không tin cậy ra sao?
Bạn xác định thời điểm cần tạo SBOM, ký artifact và lưu attestations trong một quy trình phát hành như thế nào?
Bạn thiết kế khả năng tra cứu những bản phát hành chứa một thư viện có CVE vừa công bố ra sao?
Bạn xây dựng lịch nâng cấp base image và dependencies trong khi giữ quy trình release kiểm soát được ra sao?
Bạn xác định cách thu hồi hoặc cách ly artifact đã phát hiện bị chỉnh sửa trái phép ra sao?
Bạn thiết kế pipeline CI từ checkout, dependency resolution, tests, package đến publish artifact như thế nào?
Bạn đặt điều kiện nào để một branch hoặc tag được phép kích hoạt pipeline phát hành production?
Bạn phân biệt pipeline kiểm tra pull request với pipeline tạo release artifact như thế nào?
Bạn quyết định chạy unit test, integration test và image security scan ở bước nào để cân bằng tốc độ ra sao?
Bạn sử dụng cache Maven hoặc Gradle trong CI mà không phụ thuộc vào trạng thái máy runner như thế nào?
Bạn giới hạn quyền của CI token khi pipeline chỉ cần tải dependency nhưng không xuất bản artifact ra sao?
Bạn quản lý credentials để upload Maven artifact hoặc container image theo nguyên tắc least privilege như thế nào?
Bạn thiết kế OIDC federation để giảm nhu cầu lưu registry credentials dài hạn theo khả năng nền tảng như thế nào?
Bạn quản lý môi trường build không có Docker daemon đặc quyền khi cần tạo container image như thế nào?
Bạn phân biệt các kỹ thuật build image cần daemon với lựa chọn hỗ trợ daemonless trong hạ tầng CI ra sao?
Bạn lựa chọn artifact repository cho JAR/WAR và image registry cho container theo nhu cầu nào?
Bạn xác định cách đặt version cho snapshot, prerelease và release để tránh trùng artifact như thế nào?
Bạn kiểm soát việc xuất bản lại cùng một version release gây thay đổi checksum như thế nào?
Bạn lưu lại build logs, test reports, provenance và SBOM cho một release trong bao lâu theo chính sách nào?
Bạn phân biệt CI artifact tạm thời với bản phát hành được lưu trong repository chính thức ra sao?
Bạn thiết kế release promotion từ staging sang production mà không rebuild lại JAR hoặc image ra sao?
Bạn xác định cách gắn digest của image thay vì dùng tag dễ bị di chuyển trong deployment manifest như thế nào?
Bạn tổ chức approval gate trước khi publish hoặc promote artifact đến môi trường nhạy cảm ra sao?
Bạn kiểm tra rollback sẽ dùng đúng artifact đã được xác minh trước đó như thế nào?
Bạn thiết kế thao tác retry publish khi kết nối repository ngắt giữa chừng mà không gây artifact trùng như thế nào?
Bạn quản lý lock hoặc concurrency của pipeline để hai release không cùng ghi một version như thế nào?
Bạn định nghĩa cơ chế hủy pipeline cũ khi có commit mới nhưng vẫn bảo toàn release đang xuất bản ra sao?
Bạn xây dựng matrix build cho nhiều JDK hoặc CPU architecture mà không tạo kết quả release mơ hồ như thế nào?
Bạn phân biệt chất lượng kiểm thử trước package với smoke test trên executable JAR hoặc container đã đóng gói như thế nào?
Bạn lựa chọn chạy migration database ở deployment stage thay vì build stage theo tiêu chí nào?
Bạn kiểm tra image startup và readiness sau khi build trước khi cho phép phát hành như thế nào?
Bạn thiết kế chính sách tự động tạo release notes dựa trên commit và dependency changes ra sao?
Bạn tổ chức rollback khi plugin build mới tạo JAR không tương thích với cấu hình runtime hiện tại ra sao?
Bạn quản lý artifact retention, quota và cleanup để repository không đầy dung lượng như thế nào?
Bạn sử dụng checksum và signature khi chuyển artifact từ CI sang môi trường triển khai như thế nào?
Bạn đánh giá các chỉ số build duration, failure rate, cache hit và lead time để cải thiện pipeline ra sao?
Bạn thiết kế quy trình phục hồi khi CI runner hoặc artifact registry bị outage trong giờ phát hành như thế nào?
Bạn xây dựng contract test kiểm chứng JAR chứa đủ resource và dependency trước khi phát hành ra sao?
Bạn kiểm tra manifest, entry point và Start-Class của một executable JAR bằng những thao tác nào?
Bạn thử chạy executable JAR với JRE tối thiểu để phát hiện thiếu module hoặc class như thế nào?
Bạn thiết kế thử nghiệm deploy WAR lên external servlet container thực thay vì chỉ chạy embedded mode ra sao?
Bạn kiểm tra lớp dependency và ứng dụng trong container image để đánh giá caching thực tế như thế nào?
Bạn so sánh size, startup time và memory consumption của Dockerfile image với Buildpacks image như thế nào?
Bạn kiểm tra source date và file timestamps khi hai build từ cùng commit có checksum khác nhau ra sao?
Bạn dùng dependency lock hoặc BOM report để điều tra bản build CI không nhất quán như thế nào?
Bạn mô phỏng network timeout khi tải dependency để kiểm tra retry và mirror cấu hình như thế nào?
Bạn xây dựng kiểm thử mất registry trong lúc publish để bảo đảm pipeline không báo thành công giả ra sao?
Bạn kiểm thử scanner báo CVE nghiêm trọng và xác minh pipeline chặn đúng theo chính sách như thế nào?
Bạn kiểm tra SBOM có ánh xạ chính xác JAR nested dependencies khi đóng gói Spring Boot như thế nào?
Bạn kiểm thử verify signature của image và từ chối image không có attestations hợp lệ ra sao?
Bạn thiết kế test với Dockerfile build context chứa secret giả để bảo đảm secret không xuất hiện trong image ra sao?
Bạn đo tác động của cache không có sẵn lên cold build time trong một CI runner mới như thế nào?
Bạn xác định mục tiêu pass/fail cho một thay đổi build plugin dựa trên độ đúng artifact, tốc độ, bảo mật và khả năng tái lập như thế nào?
Nếu chạy java -jar báo no main manifest attribute, bạn sẽ kiểm tra cấu hình packaging và repackage theo thứ tự nào?
Nếu executable JAR báo ClassNotFoundException dù Maven compile thành công, bạn sẽ kiểm tra scope và cấu trúc archive ra sao?
Nếu Gradle bootJar tạo artifact chạy được nhưng jar thông thường không chạy được, bạn sẽ giải thích và sửa cách phát hành như thế nào?
Nếu Spring Boot BOM bị override làm runtime phát sinh NoSuchMethodError, bạn sẽ tìm và sửa conflict bằng cách nào?
Nếu Maven build chỉ thành công trên laptop nhưng thất bại trên CI runner sạch, bạn sẽ kiểm tra toolchain, cache và repository ra sao?
Nếu build time tăng gấp đôi sau khi bật plugin mới, bạn sẽ profile phases hoặc tasks để xác định nguyên nhân như thế nào?
Nếu dependency plugin bị phát hiện lỗ hổng supply chain, bạn sẽ cô lập pipeline và truy vết artifact đã bị ảnh hưởng ra sao?
Nếu WAR chạy tốt bằng java -jar nhưng lỗi trên servlet container ngoài, bạn sẽ kiểm tra scope và API compatibility như thế nào?
Nếu Docker image khởi động thất bại vì Java version không phù hợp, bạn sẽ kiểm tra compile target và base image ra sao?
Nếu container image quá lớn vì dependencies bị COPY lặp, bạn sẽ thiết kế lại Dockerfile layers như thế nào?
Nếu Docker build cache không có hiệu quả dù chỉ sửa source code, bạn sẽ kiểm tra thứ tự COPY và cấu trúc JAR ra sao?
Nếu Buildpacks image thay đổi digest giữa hai lần build cùng commit, bạn sẽ điều tra builder, run image và metadata như thế nào?
Nếu một bản vá CVE trong run image xuất hiện nhưng application JAR không đổi, bạn sẽ quyết định rebase hay rebuild như thế nào?
Nếu image được publish đúng tag nhưng môi trường production chạy digest cũ, bạn sẽ kiểm tra deployment manifest và cache ra sao?
Nếu artifact registry chấp nhận overwrite một version đã phát hành, bạn sẽ bổ sung kiểm soát tính bất biến như thế nào?
Nếu SBOM không liệt kê một nested JAR quan trọng, bạn sẽ kiểm tra công cụ scan và phạm vi build như thế nào?
Nếu scanner báo một CVE trong dependency transitive, bạn sẽ quyết định nâng BOM, loại trừ hay thay library theo bước nào?
Nếu một runner CI bị lộ quyền publish, bạn sẽ thu hồi credentials và kiểm tra các artifact có khả năng giả mạo ra sao?
Nếu chữ ký container không xác minh được dù image vẫn chạy được, bạn sẽ lựa chọn chặn deploy hay xử lý ngoại lệ theo chính sách nào?
Nếu pipeline build release bằng mutable Git tag, bạn sẽ thay đổi quy trình nguồn và attestations để tránh nhầm lẫn như thế nào?
Nếu Gradle build cache trả output cũ sau khi thay environment, bạn sẽ kiểm tra task inputs và cấu hình cache như thế nào?
Nếu Maven Wrapper tải distribution từ địa chỉ không tin cậy, bạn sẽ xác minh và sửa chính sách wrapper ra sao?
Nếu một service cần chạy trên cả amd64 và arm64 nhưng có native dependency, bạn sẽ thiết kế matrix build và kiểm thử thế nào?
Nếu ứng dụng dùng secret đã được bake vào image, bạn sẽ tổ chức xử lý, rotate secret và ngăn lỗi lặp lại ra sao?
Nếu đổi từ Dockerfile sang Buildpacks làm startup time tăng mạnh, bạn sẽ đo phân bổ runtime và cấu hình build ra sao?
Nếu phải rollback release khi registry đang lỗi, bạn sẽ chuẩn bị artifact, digest và cơ chế phục hồi thế nào?
Bạn thiết kế runbook khi Maven registry, CI cache và container builder đồng thời suy giảm trước giờ phát hành như thế nào?
