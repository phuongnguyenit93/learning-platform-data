Một nhóm phát triển Spring Boot dùng Maven chạy ứng dụng từ IDE bình thường, nhưng file JAR do pipeline đóng gói không khởi động được bằng Java vì bước repackage chưa được áp dụng.
Dịch vụ quản lý đơn hàng khai báo spring-boot-maven-plugin trong hồ sơ build Maven chỉ dành cho local, khiến artifact ở CI là JAR thông thường không có cấu trúc thực thi mong đợi.
Một dự án Maven kế thừa cấu hình từ parent nội bộ nhưng quên ràng buộc execution của repackage, làm bản phát hành mới thiếu Boot Loader dù lệnh package báo thành công.
Nhóm lập trình dùng Maven với nhiều plugin tạo JAR, nhưng thứ tự thực thi trong lifecycle làm một plugin ghi đè artifact đã được Spring Boot đóng gói.
Một service Maven đóng gói được trên máy lập trình viên nhưng thất bại khi chạy clean package tại CI, vì quá trình build vô tình phụ thuộc vào file được tạo ở lần biên dịch trước.
Đội triển khai dùng Maven profile để chọn cấu hình đóng gói cho từng môi trường, nhưng profile production không được kích hoạt khi chạy pipeline và artifact chứa tài nguyên thử nghiệm.
Một hệ thống Maven có nhiều module, nhưng module thư viện cũng bị cấu hình repackage như ứng dụng Spring Boot, dẫn đến artifact thư viện không còn được service khác sử dụng như trước.
Nhóm quản lý dự án nhiều module tạo executable JAR ở aggregator thay vì module có main class, khiến plugin không thể xác định entry point phù hợp.
Một dự án Maven có hai lớp chứa main method, nhưng khi đóng gói Spring Boot plugin chọn điểm khởi động khác với ý định và service chạy sai chế độ nghiệp vụ.
Ứng dụng được Maven đóng gói với classifier dành cho môi trường kiểm thử, nhưng job triển khai lấy artifact không có classifier và container thiếu các thư viện runtime cần thiết.
Đội phát triển dùng Maven skipTests để rút ngắn thời gian dựng bản khẩn, nhưng lỗi tương thích bean chỉ xuất hiện trong integration test và lọt tới bản triển khai.
Một dự án bật Maven test song song trên cùng tài nguyên cơ sở dữ liệu giả lập, khiến kết quả build không ổn định dù mã nguồn và dependency không thay đổi.
Maven build của ứng dụng thanh toán cần truy cập repository nội bộ, nhưng CI runner không có mirror và credentials tương ứng nên không thể tải plugin ở bước package.
Nhóm phát hành Maven dùng snapshot dependency từ một repository đối tác; hai pipeline cùng commit chạy vào hai thời điểm lại đóng gói các phiên bản bytecode khác nhau.
Đội xây dựng ứng dụng Maven trên máy có JDK 21 nhưng môi trường runtime dùng Java 17, khiến JAR phát hành không khởi động được dù build báo thành công.
Ứng dụng sử dụng Maven compiler configuration không nhất quán với JDK thực tế ở CI, khiến một số module tạo class file có version khác phần còn lại.
Một dự án Maven bật annotation processing cho Lombok ở máy cá nhân, nhưng CI không cấu hình đường dẫn processor tương ứng và báo thiếu getter khi biên dịch.
Nhóm đóng gói Spring Boot service bằng Maven trên Windows và Linux; bước xử lý resource không thống nhất line ending làm checksum artifact khác nhau giữa runner.
Ứng dụng Maven có bước lọc resource để thay placeholder cấu hình, nhưng tệp chứng chỉ nhị phân bị xử lý như văn bản và không dùng được sau đóng gói.
Đội phát triển cho Maven copy tất cả tệp từ thư mục cấu hình local vào artifact, vô tình đưa thông tin kết nối môi trường thử nghiệm vào bản phát hành.
Một dự án Maven đổi tên finalName của artifact theo version, nhưng script triển khai vẫn tham chiếu tên cũ và chọn JAR còn sót trong workspace của runner.
Nhóm sử dụng Maven wrapper đã được kiểm thử trên laptop nhưng CI gọi Maven phiên bản cài sẵn, khiến dependency resolution và kết quả plugin khác nhau giữa hai môi trường.
Ứng dụng Spring Boot build Maven có integration test yêu cầu Docker, nhưng runner không hỗ trợ container và pipeline chỉ thất bại ở giai đoạn verify sau khi đã tạo artifact.
Nhóm phát triển dùng Maven dependency plugin để sao chép các thư viện bên ngoài, nhưng Dockerfile chỉ chép JAR ứng dụng và không mang theo các dependency vốn không được bundle.
Đội đóng gói nhiều biến thể sản phẩm bằng Maven profiles, nhưng artifact repository dùng cùng tên file cho mọi biến thể và bản phát hành của khách A bị ghi đè bởi khách B.
Một dự án Gradle chạy bootRun thành công trong máy lập trình viên, nhưng tác vụ build trong pipeline chỉ xuất JAR thường thay vì bootJar nên container không khởi động.
Nhóm nâng Spring Boot Gradle plugin giữa các dự án nhưng script CI tiếp tục gọi task đã được cấu hình khác trước, tạo artifact không còn đúng tên và vị trí.
Dịch vụ Gradle có cả task jar và bootJar, nhưng job xuất bản chọn tệp đầu tiên trong thư mục build/libs và đẩy artifact không thực thi lên registry.
Một dự án Gradle cấu hình bootJar cùng với lớp main mặc định của một công cụ vận hành, khiến container khởi động tác vụ bảo trì thay vì ứng dụng web.
Nhóm triển khai Gradle multi-project áp dụng Spring Boot plugin cho mọi subproject, làm những module chỉ cung cấp thư viện tạo thêm executable archive không mong muốn.
Đội xây dựng Gradle dùng configuration cache để tăng tốc, nhưng một plugin tự viết truy cập trực tiếp trạng thái dự án khi thực thi và job build bắt đầu thất bại.
Một dự án Gradle phụ thuộc vào tác vụ sinh mã từ OpenAPI, nhưng bootJar không khai báo đầy đủ quan hệ task khiến bản dựng song song đôi khi thiếu class được sinh.
Nhóm đưa kết quả test và artifact Gradle vào cùng thư mục tạm của nhiều job chạy đồng thời, gây ghi đè file và bản dựng chứa tài nguyên từ pipeline khác.
Ứng dụng Gradle sử dụng toolchain Java 21 trong build, nhưng CI runner không tải được toolchain tương ứng và dừng ở bước compile dù máy local chạy tốt.
Một đội phát triển nâng Gradle wrapper nhưng quên cập nhật plugin tương thích, khiến service Spring Boot build được trên nhánh cũ và lỗi ngay khi chạy nhánh phát hành.
Nhóm quản lý dependency Gradle bằng dynamic version để tự nhận bản vá, nhưng cùng commit tạo ra hai executable JAR không giống nhau sau một tuần.
Ứng dụng Gradle dùng plugin phát hành của tổ chức để thêm metadata vào manifest, nhưng plugin gắn thời điểm hiện tại làm checksum thay đổi ở mỗi lần build.
Đội muốn tái sử dụng cache Gradle giữa các runner nhưng cache lưu output chứa đường dẫn tuyệt đối của máy trước, khiến build mới dùng tài nguyên không đúng môi trường.
Nhóm viết test cho Gradle bootJar nhưng pipeline bỏ qua integrationTest task trong task graph, khiến bản phát hành không phát hiện lỗi kết nối tới PostgreSQL.
Một ứng dụng Gradle chuyển sang cấu hình publishing nhưng thành phần được publish là java component thông thường, còn môi trường triển khai mong executable Spring Boot archive.
Đội quản lý dự án Gradle composite build với thư viện nội bộ, nhưng bản phát hành thiếu dependency từ một included build do cách xuất bản module chưa được kiểm chứng.
Một nhóm triển khai Gradle song song trên runner ít bộ nhớ; quá nhiều worker JVM và quá trình test khiến build bị hệ điều hành kết thúc trước bước bootJar.
Nhóm phát triển dùng Gradle offline mode trên CI để giảm phụ thuộc mạng, nhưng cache không chứa phiên bản BOM mới nên một số job không thể resolve dependency.
Ứng dụng Gradle tạo hai biến thể bootJar cho hai kiến trúc nhưng cùng output filename, khiến job đóng gói container đôi khi lấy nhầm artifact của kiến trúc còn lại.
Đội chuyển build từ Maven sang Gradle nhưng không đối chiếu resources filtering, khiến file cấu hình được đóng gói khác và ứng dụng khởi động với profile sai.
Nhóm chuyển từ Gradle dependency-management plugin sang native platform BOM mà không kiểm tra version resolution, khiến một số starter kéo về thư viện không đúng bản dự kiến.
Ứng dụng Spring Boot không dùng spring-boot-starter-parent mà chỉ import BOM vào Maven, nhưng đội nghĩ BOM cũng quản lý phiên bản mọi Maven plugin và build bị lệch giữa máy.
Một nhóm ghi đè phiên bản Jackson trong dependencyManagement để sửa lỗi, nhưng starter khác sử dụng tập thư viện Jackson không đồng bộ và runtime gặp lỗi phương thức.
Đội nâng Spring Boot BOM nhưng giữ phiên bản cũ của Spring Framework bằng khai báo trực tiếp, khiến ứng dụng biên dịch thành công mà lỗi tương thích xuất hiện lúc startup.
Ứng dụng khai báo cùng một thư viện qua dependency trực tiếp và starter bắc cầu, làm phiên bản thực tế khác với giá trị đội bảo mật đã duyệt.
Nhóm sử dụng hai BOM cho Spring Boot và nền tảng cloud nội bộ, nhưng thứ tự và quy tắc quản lý version khiến cùng module resolve khác nhau giữa các dịch vụ.
Một dependency của service dùng version range trong Maven, khiến runner ở hai thời điểm lấy các bản vá khác nhau mà không có thay đổi mã nguồn.
Đội phát hành khóa phiên bản Spring Boot starter nhưng bỏ trống phiên bản của một thư viện ngoài BOM; pipeline tải bản mới nhất theo cơ chế cấu hình riêng và sinh lỗi sản xuất.
Một dịch vụ nhận bản vá bảo mật cho thư viện HTTP bằng cách ép phiên bản trực tiếp, nhưng nhóm không kiểm tra API binary compatibility với starter đang dùng.
Nhóm quản lý dependency cho ứng dụng bằng Maven BOM nhưng quên rằng thư viện dùng trong test cũng có version resolution riêng, làm bộ kiểm thử CI khác máy cá nhân.
Một repository artifact nội bộ trả metadata phiên bản cũ từ cache, khiến cùng tọa độ dependency có nội dung khác với bản do nhóm phát hành công bố.
Đội bảo mật cấm một thư viện logging có lỗ hổng nhưng dependency tree của ứng dụng Spring Boot vẫn chứa nó qua starter không được rà soát.
Một nhóm loại trừ dependency bắc cầu để loại bỏ lỗ hổng nhưng không kiểm tra classpath runtime, khiến ứng dụng lỗi khi khởi tạo bộ chuyển đổi dữ liệu.
Ứng dụng khai báo một driver database chỉ ở compile classpath, nhưng JAR triển khai thiếu thư viện runtime vì cấu hình scope không phù hợp.
Nhóm phát triển dùng dependency có scope provided trong ứng dụng chạy executable JAR, khiến runtime không tìm thấy thư viện vốn chỉ tồn tại ở servlet container ngoài.
Một service dùng cùng artifact dependency cho Maven và Gradle nhưng phiên bản thực tế được resolve khác nhau do hai hệ thống áp constraint theo cách riêng.
Đội nâng BOM để nhận bản vá CVE nhưng chưa chạy regression test cho converter JSON; dữ liệu từ producer cũ không còn được đọc đúng sau deploy.
Một ứng dụng sử dụng plugin để kiểm tra dependency updates, nhưng báo cáo đề xuất các bản major không tương thích với Spring Boot release train hiện hành.
Nhóm phát hiện version conflict giữa hai nhánh dependency qua dependency tree, nhưng test hiện tại không bao phủ đường gọi sử dụng API đã bị thay đổi.
Dự án khóa dependency ở bản snapshot nội bộ, nhưng artifact snapshot bị repository thay thế sau khi kiểm thử thành công, khiến bản release build lại không giống bản đã thử.
Đội phát hành cố định version của starter nhưng không cố định Docker base image, làm môi trường runtime có thư viện native khác sau khi build lại cùng commit.
Nhóm kiểm tra license của các dependency trực tiếp nhưng bỏ qua thư viện bắc cầu nằm trong executable JAR, gây rủi ro tuân thủ khi phát hành sản phẩm cho khách.
Ứng dụng Spring Boot được đóng gói bằng repackage nhưng khi chạy Java -jar nhận thông báo thiếu main manifest attribute, vì một tác vụ đóng gói sau đó thay thế manifest.
Một service tạo executable JAR thành công nhưng manifest trỏ tới lớp khởi động không tồn tại sau khi đổi tên package, khiến bản triển khai lỗi ngay khi start.
Nhóm phát triển nghĩ executable Spring Boot JAR phải bung toàn bộ thư viện vào classpath thông thường, nên script kiểm thử mở JAR theo giả định sai và báo thiếu class.
Một ứng dụng dùng thư viện đọc tài nguyên bằng đường dẫn tệp vật lý, nhưng tài nguyên được đóng trong nested JAR của Spring Boot Loader nên chức năng chỉ lỗi khi chạy artifact phát hành.
Đội chuyển ứng dụng chạy từ IDE sang executable JAR và thấy thư viện tải file cấu hình từ thư mục làm việc không còn tìm đúng đường dẫn của tài nguyên trong classpath.
Một service Spring Boot chứa các dependency có tên file trùng nhau sau khi đóng gói lại, khiến nhóm tích hợp khó xác nhận bản thư viện nào thực sự nằm trong BOOT-INF/lib.
Nhóm sử dụng lệnh giải nén JAR và đóng gói lại để thêm một file cấu hình sau build, nhưng vô tình thay manifest và làm hỏng cấu trúc mà Boot Loader mong đợi.
Một thư viện native yêu cầu truy cập file hệ điều hành thực, nhưng bản phát hành lưu dependency trong nested archive nên chức năng native chỉ lỗi trong container.
Đội nâng Spring Boot và Boot Loader lên phiên bản mới nhưng một công cụ kiểm tra JAR tự viết vẫn giả định đường dẫn launcher cũ, dẫn đến cảnh báo sai về entry point.
Ứng dụng đóng gói executable JAR bao gồm cả thư viện chỉ dùng cho test do cấu hình dependency bị nhầm, làm artifact lớn và kéo theo rủi ro bảo mật không cần thiết.
Nhóm triển khai ứng dụng bằng WAR vào servlet container ngoài, nhưng cấu hình bootstrap chỉ được thử bằng Java -jar nên container không khởi tạo đúng ứng dụng.
Một dự án được đóng gói executable WAR cho chạy độc lập, nhưng cấu hình thư viện servlet và phạm vi provided không được kiểm chứng trên Tomcat ngoài nên cách chạy thứ hai gặp lỗi.
Đội di chuyển ứng dụng Spring Boot từ JAR sang WAR để đáp ứng quy định hosting, nhưng giữ lại kỳ vọng đường dẫn tệp và session storage như môi trường embedded server.
Nhóm đóng gói WAR có hai nguồn thư viện servlet phiên bản khác nhau, khiến ứng dụng triển khai được nhưng lỗi khi xử lý request đầu tiên trên container của khách.
Một service nhiều module xuất bản WAR nhưng module web không chứa tài nguyên static từ module giao diện, làm trang quản trị hoạt động trong IDE nhưng thiếu file ở production.
Ứng dụng chuyển từ embedded server sang servlet container ngoài mà không thống nhất phiên bản Jakarta Servlet API, khiến việc deploy WAR thất bại ngay ở giai đoạn khởi tạo.
Một nhóm tạo JAR và WAR từ cùng nguồn trong hai pipeline riêng, nhưng mỗi pipeline dùng BOM khác nên hành vi nghiệp vụ thay đổi theo hình thức đóng gói.
Nhóm vận hành phân phối executable archive trực tiếp cho khách nhưng không lưu checksum và thông tin phiên bản Loader, làm việc xác minh tệp cài đặt sau truyền tải khó khăn.
Ứng dụng Java cần dữ liệu địa lý lớn để khởi động, nhưng JAR được thêm toàn bộ bộ dữ liệu vào resources khiến mỗi lần phát hành phải chuyển hàng GB artifact.
Đội triển khai application.properties vào bên trong executable JAR theo từng môi trường, khiến cùng commit phải build lại cho staging và production và không thể đối chiếu artifact.
Nhóm chạy ứng dụng bằng classpath thủ công để thử lỗi ở local, nhưng classpath khác cách Boot Loader nạp nested JAR nên kết quả không tái hiện lỗi của bản production.
Trong quá trình điều tra CVE, đội bảo mật scan thư viện nằm trong BOOT-INF/lib bằng công cụ chỉ đọc dependency ở cấp thư mục ngoài và bỏ sót một thư viện bị ảnh hưởng.
Nhóm tách một executable archive theo layer để tối ưu container caching, nhưng bản cập nhật resource nhỏ vẫn làm layer chứa dependency bị thay đổi và image phải tải lại lớn.
Một ứng dụng Spring Boot chạy trong container Docker được tạo bằng cách copy JAR từ target, nhưng workspace có cả file original và file repackaged nên Dockerfile đôi khi lấy bản không thực thi.
Đội viết Dockerfile chỉ dùng một stage có Maven và JDK đầy đủ, khiến image production chứa công cụ build không cần thiết và dung lượng lớn hơn ngân sách triển khai.
Nhóm sử dụng multi-stage Dockerfile nhưng stage chạy cuối vẫn sao chép toàn bộ thư mục build vào image, làm tăng kích thước và vô tình mang theo báo cáo test chứa dữ liệu nội bộ.
Ứng dụng build container từ JAR tạo ở máy lập trình viên nhưng CI không kiểm chứng checksum của artifact, nên hai người cùng tag release tạo ra hai image có mã khác nhau.
Một service đóng image với runtime Java 17 dù source dùng class Java 21, khiến container crash ngay khi khởi động trên cluster mà bước docker build vẫn thành công.
Nhóm triển khai base image Docker được tham chiếu theo tag mới nhất thay vì digest, khiến rebuild cùng commit vào tháng sau tạo ra runtime khác sau khi nhà cung cấp đổi tag.
Đội copy các tệp cấu hình chứa secret từ thư mục local vào Docker build context, khiến thông tin nhạy cảm có nguy cơ nằm trong các layer của image đã phát hành.
Một Dockerfile đặt giá trị mật khẩu qua build argument rồi ghi vào environment của image; bản triển khai bị kiểm toán vì bí mật có thể xuất hiện trong metadata hoặc lịch sử layer.
Ứng dụng triển khai Dockerfile có USER root mặc định, khiến container chạy với quyền cao hơn tiêu chuẩn bảo mật của cụm Kubernetes.
Nhóm chuyển sang runtime image distroless để giảm lỗ hổng nhưng quy trình hỗ trợ vẫn dựa vào shell và công cụ gỡ lỗi trong container, làm việc điều tra production bị gián đoạn.
Ứng dụng ghi file báo cáo vào thư mục chỉ root có quyền trong image, nhưng cluster chạy với UID không đặc quyền và thao tác ghi thất bại sau khi triển khai.
Một container chạy trên hạ tầng ARM64 nhưng image Spring Boot chỉ được build cho AMD64; tiến trình gặp lỗi kiến trúc dù manifest phát hành đã được upload thành công.
Đội tạo multi-platform image nhưng một thư viện JNI trong ứng dụng chỉ có binary cho x86_64, khiến phiên bản ARM64 tải lên registry nhưng lỗi lúc sử dụng chức năng mã hóa.
Nhóm tối ưu Docker cache bằng cách copy toàn bộ source trước bước resolve Maven dependency, khiến một thay đổi README cũng làm tải lại tất cả dependency và kéo dài pipeline.
Một Dockerfile dùng lệnh tải dependency qua mạng trong bước cuối mà không cố định checksum, khiến build không tái lập khi máy chủ bên thứ ba thay nội dung gói.
Ứng dụng cấu hình Docker HEALTHCHECK gọi HTTP endpoint trên cổng quản trị đã bị đổi, khiến container bị đánh dấu unhealthy dù cổng ứng dụng vẫn hoạt động.
Nhóm khai báo EXPOSE một cổng HTTP nhưng ứng dụng Spring Boot thực tế lắng nghe cổng khác do cấu hình môi trường; bộ công cụ deploy ánh xạ sai dẫn đến timeout.
Đội cấu hình JVM heap cho môi trường bare metal rồi đưa nguyên vào container có memory limit nhỏ, khiến pod bị OOMKilled khi chưa đạt tải nghiệp vụ.
Ứng dụng có image Docker lớn vì nhúng compiler và cache Maven vào runtime layer, khiến mỗi lần autoscale phải tải nhiều dữ liệu từ registry và pod khởi động chậm.
Nhóm đóng gói layer phụ thuộc và layer ứng dụng trong cùng một tar không có thứ tự ổn định, làm container image đổi digest dù code business không thay đổi.
Trong đợt triển khai, Docker image được tag theo tên branch nhưng tag bị ghi đè giữa hai build; staging và production kéo cùng tên tag nhưng nhận bytecode khác nhau.
Đội muốn giảm bề mặt tấn công bằng minimal base image nhưng vẫn chép các chứng chỉ CA từ image khác không đầy đủ; HTTP client HTTPS không còn tin cậy endpoint đối tác.
Ứng dụng dùng thông tin timezone mặc định của build host để định dạng thời gian, nhưng container runtime không có dữ liệu timezone tương ứng và kết quả khác giữa môi trường.
Nhóm khởi động Spring Boot bằng shell script trong image nhưng script không truyền tín hiệu dừng đúng tới tiến trình Java, khiến rolling deployment ngắt request đang xử lý.
Một container thiếu thiết lập file permission cho executable startup script do bản build chạy trên Windows, khiến image chỉ lỗi khi chạy trên node Linux.
Đội xây image bằng Spring Boot Maven plugin build-image, nhưng CI runner không có quyền truy cập container daemon phù hợp và job thất bại dù Maven package đã PASS.
Nhóm dùng Gradle bootBuildImage trên laptop nhưng pipeline không cấu hình builder image tương thích Java version đang dùng, khiến quá trình tạo image thất bại trong môi trường CI.
Một ứng dụng sử dụng Cloud Native Buildpacks với builder tag không cố định; cùng nguồn được build lại sau khi buildpack cập nhật và digest container thay đổi ngoài dự kiến.
Đội chọn Buildpacks builder cho Java nhưng run image dùng hệ điều hành không tương thích với các lớp native, khiến container khởi động thất bại dù bước phát hiện buildpack thành công.
Nhóm phát triển cấu hình build-image với môi trường build khác runtime, khiến ứng dụng chọn không đúng phiên bản JVM hoặc thư viện hệ thống cần thiết khi chạy.
Ứng dụng tạo OCI image qua Buildpacks nhưng đội bảo mật chưa kiểm tra các artifact SBOM do buildpack tạo, khiến báo cáo dependency bỏ qua một số package hệ điều hành.
Nhóm triển khai Buildpacks tạo image có nhiều layer được tái sử dụng, nhưng mỗi pipeline xóa hoàn toàn cache build nên thời gian tạo image tăng đáng kể.
Đội vận hành build image bằng Boot plugin nhưng registry nội bộ yêu cầu xác thực khác giữa builder và nơi publish; image được tạo thành công nhưng push thất bại.
Một dự án Java có dependency native yêu cầu bộ công cụ hệ thống ở build phase, nhưng Buildpacks builder thiếu môi trường tương ứng và lỗi chỉ xảy ra sau khi deploy nguồn mới.
Ứng dụng Spring Boot chạy dưới cơ chế memory calculator của Buildpacks, nhưng giới hạn container và cấu hình JVM trực tiếp xung đột làm pod hết bộ nhớ trong giờ cao điểm.
Nhóm sử dụng build-image tạo image chứa metadata về source revision nhưng pipeline không ghi commit chính xác, làm đội vận hành không đối chiếu được image với nhánh phát hành.
Đội nâng Buildpacks stack từ một bộ image nền sang bộ khác nhưng chưa kiểm tra tương thích native library, khiến ứng dụng chỉ lỗi ở một đường xử lý ít được thử nghiệm.
Một service cần đưa certificate bundle riêng vào image xây bằng Buildpacks, nhưng quy trình hiện tại chỉ thử trong Dockerfile và không đảm bảo chứng chỉ có mặt ở runtime mới.
Nhóm tạo image từ executable JAR có layered archive, nhưng một thay đổi nhỏ ở application resources làm container không tận dụng được lớp dependency ổn định như mong đợi.
Đội chuyển từ Dockerfile thủ công sang Buildpacks để giảm công bảo trì, nhưng dashboard hiện thiếu thông tin về các phiên bản base image và buildpack dùng trong mỗi release.
Ứng dụng Spring Boot dùng image tạo bởi Buildpacks trên runner AMD64 nhưng cluster có node ARM64; nhóm chưa xác nhận kiến trúc của OCI image được đẩy vào registry.
Nhóm triển khai bản dựng từ Buildpacks nhưng không có quy trình cập nhật base runtime khi có CVE; container đang chạy vẫn dùng những lớp hệ điều hành đã lỗi thời.
Đội phát hành phân biệt image dùng cho môi trường thử và production bằng buildpack khác nhau, khiến bài kiểm thử đã PASS không phản ánh runtime cuối cùng của sản phẩm.
Một service chạy bằng Dockerfile và cùng service chạy bằng Buildpacks cho hai khách hàng, nhưng CA certificates và timezone trong hai image khác nhau làm lỗi chỉ xuất hiện ở một khách.
Nhóm dùng lifecycle Buildpacks mới trong CI nhưng chính sách mạng nội bộ chặn tải các dependency cần thiết khi build, khiến pipeline phụ thuộc vào cache cũ và khó tái tạo trên runner sạch.
Đội kiểm thử tính tái lập bằng cách chạy Maven package hai lần với cùng commit nhưng timestamp trong ZIP entry của JAR khác nhau, làm checksum artifact không trùng.
Ứng dụng thêm build-info vào JAR từ thời điểm build hiện tại mà không chuẩn hóa metadata, khiến hệ thống ký số nhận hai digest khác nhau cho cùng nguồn và dependency.
Một nhóm tạo artifact trên hai hệ điều hành và nhận checksum khác nhau do thứ tự file resources trong archive không ổn định, dù toàn bộ test nghiệp vụ đều PASS.
Đội build dùng một file dependency lock của Gradle nhưng không cập nhật nó khi nâng BOM, khiến việc resolve tập thư viện thất bại trên runner sạch.
Một dự án Maven chỉ khóa version trực tiếp của dependency nhưng không kiểm tra dependency bắc cầu và plugin, khiến rebuild cùng tag mã nguồn nhận những artifact khác nhau.
Nhóm kiểm tra reproducible build bằng Maven nhưng quá trình sinh mã nhúng hostname của runner vào class, làm output không khớp giữa hai máy trong cùng pipeline.
Đội kiểm thử Gradle trên máy cá nhân có cache đầy đủ, nhưng pipeline sạch không tìm thấy plugin từng được lưu thủ công và bản dựng không thể tái tạo độc lập.
Ứng dụng tạo container image dùng cùng JAR và Dockerfile nhưng base image upstream thay đổi tag, khiến image digest khác dù lớp ứng dụng không đổi.
Nhóm xây artifact không cố định locale và encoding của bước xử lý resource, làm bản build của runner có ngôn ngữ hệ thống khác tạo metadata và văn bản khác.
Đội phát hành muốn chứng minh artifact được tạo từ nguồn đã kiểm thử, nhưng giai đoạn deploy rebuild source thêm một lần thay vì dùng artifact đã PASS ở CI.
Một pipeline CI dùng mutable Maven snapshot repository và không lưu manifest dependency đã resolve, nên khó chứng minh một bản dựng cũ dùng tập thư viện nào.
Đội bảo mật quét dependency Maven trước khi đóng gói nhưng không quét các thư viện lồng trong executable JAR và các package ở runtime container.
Một ứng dụng bị cảnh báo CVE từ dependency bắc cầu, nhưng đội chỉ cập nhật base image Docker và nghĩ rằng đã loại bỏ lỗ hổng trong Spring Boot artifact.
Nhóm áp dụng policy chặn license không phù hợp nhưng chỉ kiểm tra thư viện trực tiếp; khi một starter mới được thêm, artifact phát hành có thành phần không được phép.
Đội cấp credential registry cho tất cả job CI từ nhánh pull request, khiến một thay đổi chưa được kiểm duyệt có khả năng truy cập nơi xuất bản production.
Một pipeline cài công cụ build bằng script tải từ mạng công khai mà không kiểm tra checksum, khiến quy trình phát hành phụ thuộc vào nội dung ngoài quyền kiểm soát.
Nhóm phát hành image container đã scan vào buổi sáng nhưng đến tối cùng tag được push lại từ pipeline khác mà không scan, khiến kết quả kiểm toán không còn khớp artifact đang chạy.
Đội bảo mật yêu cầu SBOM cho mỗi release nhưng bộ tạo danh mục chỉ đọc pom.xml, không ghi nhận các package thực tế trong container image cuối cùng.
Ứng dụng Spring Boot có thành phần native từ một nhà cung cấp, nhưng SBOM chỉ ghi dependency Java nên đội ứng cứu không xác định được ảnh hưởng của CVE hệ điều hành.
Nhóm ký image ở registry nhưng triển khai dựa trên tag không bất biến; sau khi tag bị chuyển sang digest khác, chữ ký và artifact đang chạy không được đối chiếu đúng.
Đội kiểm toán cần provenance của executable JAR nhưng pipeline chỉ lưu tên artifact và thời gian, không có dấu vết commit, build runner và nguồn dependency.
Nhóm triển khai quy tắc xác minh chữ ký container image ở cluster, nhưng các image được build thủ công cho bản vá khẩn không có thông tin ký nên release bị chặn.
Một pipeline CI tải Maven credentials qua biến môi trường rồi in toàn bộ lệnh debug trong log, vô tình tiết lộ token repository cho người có quyền xem job.
Đội dùng shared runner cho nhiều dự án và tái sử dụng cache dependency không kiểm soát nguồn, khiến bản build có nguy cơ lấy artifact bị thay thế từ dự án khác.
Ứng dụng container chạy với image nền đã hết hỗ trợ và không có quy trình cập nhật, làm số lỗ hổng nghiêm trọng tăng dù mã Java không thay đổi.
Nhóm cấu hình pipeline cho phép bỏ qua kiểm tra bảo mật khi scan service lỗi, nhưng báo cáo release vẫn hiển thị trạng thái PASS và artifact được tự động publish.
Đội phát triển nhận bản vá CVE trong Spring Boot BOM nhưng không tái tạo và ký lại image đã xuất bản; các pod production tiếp tục dùng dependency dễ bị tấn công.
Một công ty cần xác minh file executable JAR tải từ registry không bị thay đổi, nhưng công cụ deploy chỉ kiểm tra tên và version mà không đối chiếu checksum.
Đội phát hành lưu artifact trong registry không có retention policy rõ ràng; sau vài tháng bản cũ dùng để rollback đã bị dọn và không thể tái triển khai.
Nhóm CI chạy unit test trên JDK 21 nhưng đóng image runtime Java 17 mà không có test khởi động image, khiến bản phát hành thất bại sau khi đã được phê duyệt.
Đội phát triển chạy Maven verify và Docker build ở hai job song song, nhưng Docker build lấy JAR từ cache trước khi test job hoàn tất; image không gắn với artifact đã kiểm thử.
Nhóm phát hành dùng cùng một version Maven cho nhiều commit hotfix và push lại repository release vốn cho phép ghi đè, làm khó truy vết lỗi theo version.
Ứng dụng Gradle publish artifact rồi tạo image từ nguồn được checkout lại, nhưng hai bước dùng revision khác do nhánh chính có commit mới trong khoảng thời gian đó.
Đội triển khai một pipeline chung cho nhiều Spring Boot service, nhưng một service cần executable WAR còn bước artifact packaging mặc định luôn chọn bootJar.
Nhóm CI dùng biến môi trường để điền version vào Docker tag, nhưng giá trị version rỗng ở build theo lịch và image bị đẩy dưới tag dùng chung không mong muốn.
Đội phát triển xây Docker image và xuất bản lên registry trước khi chạy integration test, khiến bản có lỗi tương thích database đã tồn tại trong kho phát hành chính thức.
Một pipeline dùng ephemeral runner không có Maven cache trong đợt nhà cung cấp repository bị gián đoạn; tất cả job phát hành thất bại dù source không đổi.
Nhóm CI tạo artifact theo cách tự động tải bản mới nhất của một plugin, khiến pipeline chạy lại từ tag cũ có thể dùng phiên bản plugin khác bản đã phát hành trước.
Ứng dụng Spring Boot cần build trên cả Linux AMD64 và ARM64, nhưng pipeline chỉ chạy test trên AMD64 trước khi đẩy multi-platform image nên lỗi JNI trên ARM không được phát hiện.
Đội phát triển dùng tag latest cho container staging và production; khi chạy canary release, pod mới và cũ có cùng nhãn image nên không rõ bản nào đang phục vụ.
Nhóm muốn triển khai chỉ sau khi artifact được ký, nhưng pipeline publish image và chạy deploy đồng thời làm cluster có lúc kéo về image chưa kèm chữ ký hợp lệ.
Ứng dụng được đóng gói từ nhánh release nhưng build-info không ghi mã commit, khiến khi phát hiện lỗi production nhóm không thể xác định chính xác nguồn đã tạo JAR.
Đội tạo SBOM ở bước Maven package nhưng không gắn nó với digest image trong registry, làm báo cáo scan và container production không thể liên kết một cách chắc chắn.
Nhóm triển khai rollback bằng cách build lại version trước từ source thay vì lấy image lưu trữ, nhưng dependency repository đã thay đổi nên bản rollback có hành vi khác trước.
Trong một bài diễn tập khôi phục, artifact repository nội bộ mất kết nối; nhóm không thể redeploy bản đã ký vì pipeline bắt buộc phải resolve lại dependency từ đầu.
Một bộ test Spring Boot chạy trên máy phát triển có timezone cụ thể nhưng CI dùng UTC, khiến các bài test ngày giờ không ổn định và build release bị chặn ngẫu nhiên.
Đội phát hành tối ưu CI bằng cách bỏ giai đoạn thử khởi động executable JAR, nhưng lỗi thiếu Main-Class chỉ lộ ra khi container đầu tiên được triển khai.
Nhóm xây pipeline tạo image multi-stage nhưng không có smoke test thực thi image đã push, khiến việc phát hiện thiếu chứng chỉ CA và cấu hình cổng xảy ra sau deployment.
Ứng dụng Spring Boot bị lỗi tạo OCI image khi runner hết dung lượng disk do các layer cũ, nhưng job pipeline không thu thập chỉ số tài nguyên để tìm nguyên nhân.
Đội phát hành muốn chia artifact giữa nhiều môi trường nhưng quy trình đóng gói bake hostname và thông tin nhạy cảm vào JAR, khiến mỗi môi trường dùng một bộ byte khác nhau.
Nhóm quản lý artifact kiểm tra tên file JAR và tag Docker nhưng không lưu bản ánh xạ digest giữa chúng; khi cần điều tra incident không biết image chứa chính xác JAR nào.
Một ứng dụng triển khai bằng Buildpacks được kiểm thử sau khi tạo image, nhưng khi chuyển sang registry khác image bị gắn lại tag mà không giữ log provenance, làm mất dấu chuỗi phát hành.
Đội vận hành yêu cầu có bản dựng tái lập khi kiểm toán, nhưng các bước Maven, Gradle, Docker và CI chạy bằng toolchain không được chốt version nên không tái tạo được checksum.
Nhóm kết hợp build Spring Boot với publish image trong một job dùng token có quyền ghi production; khi bài test cuối cùng thất bại, image vẫn đã được phát hành rộng rãi.
Một doanh nghiệp muốn phát hành bản vá Spring Boot ngay khi dependency chứa CVE, nhưng pipeline chỉ lưu báo cáo scan theo tên version chứ không theo digest và không biết image nào cần thu hồi.
