# Chọn phiên bản đích theo yêu cầu ứng dụng và hệ sinh thái

Khi lập kế hoạch chuyển đổi Java, việc chọn phiên bản đích là một quyết định kiến trúc và vận hành. Phiên bản mới nhất không tự động là lựa chọn phù hợp nhất; phiên bản cũ nhất mà ứng dụng còn chạy được cũng không phải lúc nào là lựa chọn an toàn. Phiên bản đích cần đáp ứng đồng thời yêu cầu của ứng dụng, thời gian hỗ trợ, framework, thư viện, công cụ build, nền tảng triển khai và năng lực vận hành của tổ chức.

Bài học này nằm trong chủ đề **Java Advance Compatibility Migration**, thuộc chương **Phiên bản và lộ trình**. Nội dung tập trung vào cách xác định một phiên bản Java mục tiêu có thể triển khai và duy trì lâu dài, cách đánh giá những giới hạn đến từ hệ sinh thái, và cách biến quyết định đó thành lộ trình chuyển đổi có thể kiểm chứng.

## 1. Vì sao không thể chọn phiên bản Java chỉ bằng một con số?

Một yêu cầu như “nâng ứng dụng lên Java 25” có thể đang nói đến nhiều mục tiêu khác nhau:

- Dùng JDK 25 để chạy Gradle hoặc Maven.
- Dùng compiler của JDK 25 để biên dịch mã nguồn.
- Biên dịch bytecode và giới hạn API theo Java 25.
- Chạy ứng dụng production trên JVM 25.
- Nâng framework, thư viện và công cụ để hỗ trợ nền tảng Java 25.
- Sử dụng một tính năng ngôn ngữ hoặc runtime chỉ có ở một phiên bản Java mới.

Các mục tiêu này có liên quan nhưng không bắt buộc phải thay đổi cùng lúc. Ví dụ, một nhóm có thể dùng JDK 25 trên CI để biên dịch ứng dụng theo release 21, sau đó triển khai artifact trên JVM 21. Một nhóm khác có thể giữ nguyên artifact Java 17 và chỉ thay runtime production lên Java 21.

Vì vậy, trước khi chọn con số đích, cần xác định chính xác thành phần nào phải thay đổi và hợp đồng tương thích nào phải được giữ.

Một ứng dụng Java chịu ảnh hưởng bởi nhiều lớp:

~~~text
Yêu cầu nghiệp vụ và tính năng ứng dụng
                 |
                 v
Mã nguồn + API Java được sử dụng
                 |
                 v
Compiler + build tool + annotation processor
                 |
                 v
Bytecode + framework + thư viện phụ thuộc
                 |
                 v
JVM + hệ điều hành + container + nền tảng triển khai
                 |
                 v
Giám sát, bảo mật, hỗ trợ và vận hành production
~~~

Phiên bản đích chỉ khả thi khi các lớp quan trọng đều tương thích. Một framework chưa hỗ trợ phiên bản mới, một JDBC driver chưa được kiểm chứng, hoặc một agent giám sát chưa hoạt động trên JVM mới đều có thể chặn migration dù mã nguồn biên dịch thành công.

## 2. Hiểu vòng đời phát hành và hỗ trợ Java

### 2.1. Feature release và LTS

Java phát hành theo nhịp khoảng sáu tháng. Các phiên bản feature release đưa vào thay đổi ngôn ngữ, API, JVM và thư viện nền tảng theo từng chu kỳ. Trong số đó, một số phiên bản được các nhà cung cấp đánh dấu là Long-Term Support (LTS) và cung cấp thời gian duy trì dài hơn theo chính sách của họ.

LTS thường phù hợp với hệ thống cần:

- Vận hành ổn định trong nhiều năm.
- Có kế hoạch vá bảo mật và cập nhật định kỳ.
- Hạn chế tần suất migration lớn.
- Có framework, thư viện và nhà cung cấp hỗ trợ rõ ràng.
- Có thời gian để kiểm thử, phê duyệt và triển khai qua nhiều môi trường.

Feature release không phải lựa chọn sai. Một số tổ chức chủ động cập nhật thường xuyên để tiếp cận cải tiến mới và tránh để khoảng cách phiên bản quá lớn. Tuy nhiên, chiến lược này đòi hỏi pipeline kiểm thử tự động tốt, khả năng triển khai nhanh và lịch nâng cấp đều đặn.

### 2.2. LTS không phải một cam kết hỗ trợ giống nhau cho mọi JDK

Nhãn LTS không tự động bảo đảm mọi bản phân phối Java đều được hỗ trợ trong cùng một khoảng thời gian. Cần kiểm tra chính sách của nhà cung cấp JDK đang sử dụng.

Các nhà cung cấp có thể khác nhau về:

- Thời điểm kết thúc cập nhật bảo mật miễn phí.
- Thời gian hỗ trợ thương mại.
- Phiên bản được nhận bản vá backport.
- Điều kiện sử dụng trong môi trường production.
- Mức độ hỗ trợ cho hệ điều hành và kiến trúc CPU.
- Cách phân phối bản cập nhật và thông báo lỗ hổng.
- Cam kết hỗ trợ kỹ thuật và thời gian phản hồi.

Do đó, quyết định “chọn Java 21 LTS” vẫn chưa đủ. Cần ghi rõ dùng bản phân phối nào, nguồn cập nhật nào, chính sách hỗ trợ nào và ai chịu trách nhiệm theo dõi vòng đời đó.

Một số ví dụ về bản phân phối JDK phổ biến gồm Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK và Red Hat build of OpenJDK. Mỗi bản phân phối có chính sách, phạm vi nền tảng và mô hình hỗ trợ riêng. Không nên suy luận thời hạn hỗ trợ của một bản phân phối từ thông tin của bản phân phối khác.

### 2.3. Cách đọc một lịch hỗ trợ

Khi đánh giá phiên bản, hãy phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| GA release | Thời điểm phiên bản được phát hành chính thức |
| Public update | Các bản cập nhật được phát hành rộng rãi |
| Security update | Bản vá bảo mật cho nhánh phiên bản |
| End of public updates | Mốc kết thúc cập nhật công khai theo chính sách nhà cung cấp |
| End of support | Mốc kết thúc hỗ trợ theo hợp đồng hoặc chính sách cụ thể |
| Extended support | Giai đoạn hỗ trợ bổ sung, có thể kèm điều kiện hoặc chi phí |
| Container image lifecycle | Vòng đời của image hệ điều hành và JDK được đóng gói |

Một phiên bản có thể vẫn chạy tốt nhưng đã không còn nhận bản vá trong kênh mà tổ chức đang sử dụng. Ngược lại, một phiên bản mới có thể đã GA nhưng một số thư viện hoặc nền tảng triển khai chưa có bản tương thích ổn định.

**Tại thời điểm cuối năm 2026**, Java 25 là một mốc LTS mới, còn Java 26 thuộc nhịp feature release. Đây là ví dụ về cách phân biệt loại phát hành; khi ra quyết định thực tế, vẫn phải xác nhận trạng thái hỗ trợ của đúng nhà cung cấp JDK và các nền tảng mà ứng dụng sử dụng.

## 3. Phân biệt bốn phiên bản trong pipeline

Một lỗi phổ biến khi lập kế hoạch là chỉ ghi một trường “Java Version”. Trong thực tế cần ghi nhận ít nhất bốn cấu hình.

| Thành phần | Vai trò | Câu hỏi cần trả lời |
|---|---|---|
| JDK chạy build tool | JVM chạy Gradle/Maven và plugin build | Gradle/Maven wrapper có hỗ trợ JDK này không? |
| Compiler toolchain | JDK cung cấp javac cho task compile | Compiler thực tế đến từ JDK nào? |
| Release đích | Giới hạn cú pháp, API nền tảng và bytecode | Artifact cần hỗ trợ từ Java nào? |
| Runtime production | JVM thực thi ứng dụng | Nền tảng triển khai có cung cấp và hỗ trợ JVM nào? |

Các phiên bản này có thể giống hoặc khác nhau.

Ví dụ:

~~~text
JDK chạy Gradle:       25
Compiler toolchain:    25
Release đích:          21
Production runtime:    21
~~~

Cấu hình trên có thể phù hợp nếu Gradle và toàn bộ plugin hỗ trợ chạy trên JDK 25, mã nguồn và dependency không vượt quá API Java 21, và artifact được kiểm thử trên JVM 21.

Nếu release đích là 25 thì bytecode có thể không chạy trên JVM 21. Nếu chỉ nâng runtime production lên 25 nhưng giữ artifact Java 21, ứng dụng vẫn cần kiểm thử vì hành vi JVM và thư viện nền tảng có thể thay đổi.

### 3.1. Release đích phải phản ánh mức Java thấp nhất cần hỗ trợ

Giả sử một thư viện được dùng bởi nhiều dịch vụ:

- Dịch vụ A vẫn chạy Java 17.
- Dịch vụ B chạy Java 21.
- Dịch vụ C đã chuyển sang Java 25.

Nếu thư viện công bố artifact chỉ tương thích Java 25, dịch vụ A và B không thể dùng artifact đó trên runtime hiện tại. Nếu thư viện giữ release đích Java 17, cả ba dịch vụ có thể dùng chung artifact khi dependency và API đều tương thích.

Điều này cho thấy phiên bản đích của thư viện thường chịu ảnh hưởng bởi consumer có yêu cầu runtime thấp nhất. Đối với một ứng dụng độc lập, nhóm có thể chọn mục tiêu khác dựa trên môi trường triển khai của chính ứng dụng đó.

### 3.2. Đừng nhầm source compatibility với runtime compatibility

Một dự án có thể biên dịch thành công với compiler mới nhưng không chạy được trên runtime cũ nếu sử dụng API mới hoặc tạo bytecode mới hơn.

Với JDK 9 trở lên, tùy chọn **--release** thường là cách rõ ràng để giới hạn đồng thời ngôn ngữ, API nền tảng và phiên bản class file theo release đích.

~~~bash
javac --release 21 -d out src/com/example/Main.java
~~~

Việc cấu hình release đúng vẫn chưa đủ để chứng minh mọi dependency đều tương thích. Các thư viện bên thứ ba có thể được biên dịch cho phiên bản Java cao hơn hoặc sử dụng API không có trong runtime đích.

## 4. Bắt đầu từ yêu cầu của ứng dụng

Phiên bản Java phù hợp phụ thuộc vào đặc điểm và mục tiêu của ứng dụng.

### 4.1. Ứng dụng cần tính năng nào?

Hãy xác định tính năng hoặc API nào thực sự thúc đẩy việc nâng cấp:

- Record để biểu diễn kiểu dữ liệu bất biến.
- Pattern matching hoặc switch expression để làm rõ logic.
- Virtual threads để xử lý nhiều tác vụ đồng thời theo mô hình blocking.
- Foreign Function & Memory API khi cần tương tác native theo hướng mới.
- Cải tiến garbage collector, JIT hoặc thời gian khởi động.
- API bảo mật, TLS hoặc thuật toán mới.
- API nền tảng phục vụ xử lý dữ liệu, thời gian hoặc I/O.

Không nên nâng phiên bản chỉ vì muốn “dùng cú pháp mới”. Cần xác định lợi ích có thể đo lường hoặc yêu cầu kỹ thuật cụ thể. Một tính năng mới có thể cần thay đổi thiết kế ứng dụng, giới hạn tài nguyên, cấu hình quan sát hoặc cách xử lý lỗi.

Ví dụ, virtual threads có thể giúp một ứng dụng I/O-bound xử lý nhiều tác vụ blocking với chi phí thread thấp hơn trong một số trường hợp. Nhưng việc chuyển sang virtual threads không tự động làm CPU-bound workload nhanh hơn, cũng không loại bỏ giới hạn của connection pool, database, API ngoài hoặc các vùng code có đồng bộ hóa không phù hợp.

### 4.2. Yêu cầu hiệu năng và tải

Khi mục tiêu là cải thiện hiệu năng, không nên chọn phiên bản chỉ dựa trên benchmark tổng quát. Hãy xác định workload thực tế:

- CPU-bound hay I/O-bound.
- Số request đồng thời.
- Kích thước heap và giới hạn bộ nhớ container.
- Tần suất và thời gian pause của garbage collector.
- Thời gian startup và warm-up.
- Throughput, p95/p99 latency và tỷ lệ lỗi.
- Chi phí CPU, RAM và hạ tầng trên mỗi request.

Một phiên bản mới có thể cải thiện một loại workload nhưng không cải thiện loại khác. Cần chạy benchmark với cùng dữ liệu, cấu hình, giới hạn tài nguyên và điều kiện tải để so sánh công bằng.

### 4.3. Yêu cầu bảo mật và tuân thủ

Hệ thống có thể bị buộc nâng phiên bản do:

- Nhánh JDK hiện tại hết thời gian nhận bản vá.
- Chính sách bảo mật nội bộ yêu cầu phiên bản còn được hỗ trợ.
- Tiêu chuẩn mã hóa hoặc TLS không còn chấp nhận cấu hình cũ.
- Quy định về nguồn gốc, chữ ký hoặc quy trình cập nhật runtime.
- Hệ điều hành hoặc container image hiện tại đã hết vòng đời.
- Đánh giá bảo mật yêu cầu loại bỏ API nội bộ hoặc thư viện dễ tổn thương.

Trong trường hợp này, phiên bản mục tiêu phải có kênh cập nhật bảo mật rõ ràng và đáp ứng yêu cầu kiểm toán. Chỉ chọn một số phiên bản mới hơn mà không xác định nhà cung cấp và chính sách vá lỗi sẽ để lại khoảng trống vận hành.

### 4.4. Thời gian tồn tại và tốc độ thay đổi của sản phẩm

Một dịch vụ nội bộ có thể triển khai thường xuyên và nâng JDK theo chu kỳ ngắn. Một hệ thống lõi, thiết bị tại khách hàng hoặc ứng dụng triển khai trong môi trường bị giới hạn có thể cần thời gian hỗ trợ dài hơn.

Hãy xem xét:

- Số năm dự kiến duy trì phiên bản.
- Tần suất release sản phẩm.
- Khả năng nâng runtime độc lập với release nghiệp vụ.
- Số lượng môi trường và khách hàng cần phối hợp.
- Thời gian phê duyệt thay đổi.
- Khả năng rollback và triển khai song song.
- Năng lực đội ngũ để theo dõi thay đổi Java mỗi sáu tháng.

Ứng dụng có vòng đời dài thường cần một baseline được hỗ trợ lâu dài và lịch rà soát định kỳ. Sản phẩm phát hành liên tục có thể theo kịp các feature release nếu tổ chức có đủ năng lực kiểm thử.

## 5. Đánh giá toàn bộ hệ sinh thái

Một phiên bản Java chỉ được xem là khả thi khi các thành phần quan trọng xung quanh ứng dụng hỗ trợ nó.

### 5.1. Framework và nền tảng ứng dụng

Kiểm tra framework chính và các thành phần mở rộng:

- Spring Framework và Spring Boot.
- Jakarta EE application server.
- Quarkus, Micronaut hoặc Helidon.
- Hibernate, JPA provider và các integration module.
- Framework bảo mật, serialization, validation và messaging.

Cần đọc compatibility matrix hoặc release notes chính thức để biết phiên bản framework nào hỗ trợ JDK mục tiêu. Không nên suy luận rằng framework hỗ trợ Java 21 thì mọi plugin và extension của nó cũng hỗ trợ Java 21.

Với framework có nhiều module, hãy kiểm tra cả phần runtime, build plugin, test support và integration. Một ứng dụng có thể chạy được ở local nhưng không build được trên CI vì plugin build chưa hỗ trợ JDK mới.

### 5.2. Build tool và plugin

Build tool cũng có yêu cầu phiên bản riêng. Cần xác nhận:

- Gradle wrapper hoặc Maven wrapper có thể chạy trên JDK mục tiêu.
- Compiler plugin hỗ trợ toolchain và release cần dùng.
- Annotation processor tương thích với compiler mới.
- Plugin kiểm thử, coverage, static analysis và đóng gói hoạt động đúng.
- Plugin tạo mã, bytecode enhancement hoặc instrumentation hỗ trợ class file mới.
- IDE và cấu hình phát triển thống nhất với CI.

Không nên nâng JDK trước khi kiểm tra khả năng chạy của chính build tool. Nếu Gradle wrapper không hỗ trợ chạy trên JDK mới, build có thể thất bại trước khi compiler được gọi.

### 5.3. Thư viện và dependency

Dependency có thể giới hạn phiên bản Java thấp nhất hoặc cao nhất đã được kiểm thử. Kiểm tra:

- Thư viện nội bộ và thư viện bên thứ ba.
- JDBC driver và database client.
- Kafka, AMQP, messaging client.
- HTTP client, SDK cloud và thư viện xác thực.
- JSON/XML serializer và thư viện định dạng dữ liệu.
- Logging, metrics, tracing và monitoring agent.
- Thư viện mã hóa, TLS và certificate.
- Native library và JNI binding.

Cần phân biệt thư viện **được biên dịch bằng JDK nào** với thư viện **yêu cầu runtime tối thiểu nào**. Một thư viện build bằng JDK mới nhưng dùng release cũ vẫn có thể chạy trên runtime cũ. Ngược lại, một thư viện build cho release mới có thể khiến toàn bộ ứng dụng phải nâng runtime.

Đọc metadata của artifact, tài liệu hỗ trợ và release notes. Khi thiếu thông tin, hãy tạo một kiểm thử nhỏ để xác nhận trên JDK mục tiêu thay vì suy đoán.

### 5.4. Agent và công cụ quan sát

Các agent thường can thiệp vào class loading, bytecode hoặc JVM startup. Ví dụ:

- APM agent.
- Java profiler.
- Code coverage agent.
- Security agent.
- OpenTelemetry Java agent.
- Agent giám sát hoặc chẩn đoán do tổ chức tự phát triển.

Agent có thể phụ thuộc vào API nội bộ, bytecode format, cơ chế attach hoặc tùy chọn JVM. Vì vậy, cần xác nhận phiên bản agent hỗ trợ JDK mục tiêu và kiểm tra cả startup lẫn hoạt động trong runtime thực tế.

Một ứng dụng chạy được khi không có agent chưa chứng minh được hệ thống production tương thích.

### 5.5. Hệ điều hành, container và hạ tầng

Kiểm tra môi trường triển khai thực tế:

- Linux distribution hoặc Windows Server.
- Kiến trúc x86-64, ARM64 và các kiến trúc được hỗ trợ.
- Container base image và chính sách cập nhật.
- Kubernetes, nền tảng PaaS hoặc application server.
- Serverless runtime và giới hạn phiên bản JDK do nhà cung cấp quy định.
- JNI, native executable và thư viện hệ thống.
- CA certificates, timezone database, locale và font.
- Memory limit, cgroup, file descriptor và quyền hệ thống.

Một JDK có thể tồn tại cho một hệ điều hành nhưng không được nhà cung cấp hỗ trợ trên kiến trúc hoặc nền tảng đang sử dụng. Container image cũng có vòng đời riêng; nâng JDK nhưng giữ base image đã hết hỗ trợ không giải quyết đầy đủ yêu cầu bảo mật.

### 5.6. Trường hợp Android và Native Image

Không phải mọi sản phẩm Java đều chạy trên JVM server thông thường.

Với Android, cần xem xét Android Gradle Plugin, D8/R8, mức API Android tối thiểu, desugaring và tập API Java được nền tảng Android hỗ trợ. Việc JDK trên máy build là Java 21 hoặc Java 25 không có nghĩa thiết bị Android chạy một JVM tương ứng.

Với GraalVM Native Image, cần kiểm tra phiên bản GraalVM, Native Image builder, framework integration, reachability metadata, reflection configuration và hỗ trợ của thư viện native. Một dependency hoạt động trên HotSpot JVM có thể cần cấu hình bổ sung hoặc chưa hoạt động trong native executable.

## 6. Xây dựng ma trận tương thích trước khi chọn phiên bản

Nên lập một bảng cho từng ứng dụng hoặc nhóm module. Mỗi thành phần phải có phiên bản hiện tại, yêu cầu của phiên bản đích và bằng chứng hỗ trợ.

| Thành phần | Hiện tại | Yêu cầu cần xác minh | Kết quả |
|---|---|---|---|
| JDK distribution | Bản đang dùng | Có bản phát hành và kênh vá cho target không? | Đạt/Chặn |
| Build tool | Gradle/Maven hiện tại | Có chạy được trên JDK build không? | Đạt/Chặn |
| Compiler | Toolchain hiện tại | Có hỗ trợ release đích không? | Đạt/Chặn |
| Framework | Spring/Jakarta/khác | Phiên bản framework nào hỗ trợ target? | Đạt/Chặn |
| Dependency | Các thư viện chính | Runtime tối thiểu và compatibility matrix? | Đạt/Chặn |
| Test tooling | JUnit, Mockito, coverage... | Có chạy với JDK và bytecode mới không? | Đạt/Chặn |
| Agent | APM, tracing, security | Có hỗ trợ JVM target không? | Đạt/Chặn |
| Native components | JNI, driver | Có binary đúng nền tảng không? | Đạt/Chặn |
| Deployment | OS, container, cloud | Có runtime được hỗ trợ không? | Đạt/Chặn |
| Operations | Monitoring, backup, rollback | Quy trình vận hành đã sẵn sàng chưa? | Đạt/Chặn |

Có thể dùng ba trạng thái:

- **Đạt:** đã có tài liệu hỗ trợ hoặc bằng chứng kiểm thử đủ tin cậy.
- **Chặn:** có thành phần không tương thích hoặc nền tảng không cung cấp runtime cần thiết.
- **Chưa xác minh:** chưa có đủ bằng chứng; cần kiểm tra trước khi cam kết lộ trình.

Không được coi “chưa xác minh” là “đạt”. Một bảng ma trận hữu ích phải lưu nguồn bằng chứng, phiên bản tài liệu, ngày kiểm tra và người chịu trách nhiệm xác nhận.

## 7. Chọn phiên bản theo mức ràng buộc của hệ thống

### 7.1. Ứng dụng độc lập, dễ triển khai

Một dịch vụ có container riêng, dependency được kiểm soát và pipeline CI/CD tự động thường có nhiều quyền lựa chọn hơn.

Có thể ưu tiên LTS mới nếu:

- Framework và dependency đã hỗ trợ.
- Container image có bản cập nhật phù hợp.
- Agent và công cụ vận hành đã được xác nhận.
- Có môi trường staging đại diện.
- Có thể triển khai theo từng instance hoặc từng nhóm dịch vụ.
- Có phương án quay lại image và artifact trước đó.

Trong trường hợp này, lựa chọn phiên bản mới hơn có thể kéo dài khoảng thời gian trước lần migration tiếp theo, nhưng vẫn phải cân nhắc chi phí nâng cấp hệ sinh thái.

### 7.2. Ứng dụng phụ thuộc nhiều hệ thống bên ngoài

Một ứng dụng tích hợp với application server, database, middleware, message broker, agent độc quyền hoặc SDK cloud có thể bị giới hạn bởi thành phần chậm cập nhật nhất.

Hãy chọn phiên bản mà toàn bộ chuỗi phụ thuộc có thể hỗ trợ. Nếu một thành phần chưa tương thích, cần xác định:

- Có bản nâng cấp thay thế không?
- Có thể thay thành phần đó độc lập không?
- Nhà cung cấp có roadmap hỗ trợ không?
- Có thể tạm giữ một module ở runtime cũ không?
- Việc giữ runtime cũ có vi phạm chính sách bảo mật không?

Nếu không có cách giải quyết, phiên bản đó chưa phải target khả thi cho đợt triển khai hiện tại.

### 7.3. Thư viện dùng chung cho nhiều ứng dụng

Thư viện được nhiều ứng dụng sử dụng cần cân nhắc mức runtime thấp nhất mà các consumer phải hỗ trợ.

Ví dụ:

~~~text
Consumer A: Java 17
Consumer B: Java 21
Consumer C: Java 25

Shared library:
  Release target: Java 17
~~~

Nếu thư viện không cần tính năng mới, giữ release đích Java 17 có thể duy trì khả năng dùng chung. Nếu cần tính năng chỉ có ở Java 21, nhóm phải thống nhất nâng baseline consumer hoặc cung cấp artifact/nhánh tương thích riêng.

Một lựa chọn nâng cao là Multi-Release JAR: giữ implementation cơ sở cho phiên bản Java thấp hơn và cung cấp class thay thế trong thư mục phiên bản tương ứng. Cách này chỉ nên dùng khi lợi ích rõ ràng vì nó làm tăng độ phức tạp đóng gói, kiểm thử và chẩn đoán. Cần kiểm tra đúng class mà từng runtime lựa chọn.

### 7.4. Hệ thống legacy

Ứng dụng legacy có thể đang phụ thuộc vào:

- API đã bị loại bỏ hoặc deprecated.
- Thư viện cũ không còn được duy trì.
- Framework chưa hỗ trợ JDK mới.
- Reflection vào package nội bộ.
- JVM options cũ.
- Native library hoặc agent đã ngừng phát triển.
- Build script không còn tương thích.

Trong trường hợp này, không nên mặc định nâng thẳng lên phiên bản mới nhất. Hãy xác định các rào cản theo từng lớp, ưu tiên thay dependency hoặc loại bỏ API nội bộ, sau đó thử trên một phiên bản đích có khả năng hỗ trợ tốt.

Nếu phải đi qua nhiều phiên bản trung gian, hãy ghi rõ lý do kỹ thuật của từng chặng. Không phải mọi phiên bản Java đều cần được triển khai production; một số chặng chỉ cần dùng để chuyển đổi framework hoặc build tool nếu có yêu cầu cụ thể.

## 8. Quy trình ra quyết định chọn target

### Bước 1 — Xác định baseline hiện tại

Ghi nhận:

- JDK distribution và phiên bản đang chạy.
- JDK chạy build tool.
- Compiler toolchain và release đích.
- Phiên bản bytecode của artifact.
- Framework và dependency chính.
- Hệ điều hành, container, cloud runtime và kiến trúc CPU.
- Agent, native library và công cụ vận hành.

Không chỉ lấy thông tin từ máy lập trình viên. Cần xác nhận cấu hình CI, staging và production.

### Bước 2 — Xác định mục tiêu kinh doanh và kỹ thuật

Ví dụ:

- Loại bỏ runtime đã hết hỗ trợ.
- Đáp ứng yêu cầu bảo mật.
- Giảm chi phí vận hành.
- Cải thiện throughput hoặc latency.
- Sử dụng một API mới.
- Chuẩn hóa runtime giữa các dịch vụ.
- Giảm khoảng cách giữa JDK của developer và CI.

Mỗi mục tiêu cần có tiêu chí đo lường. Nếu mục tiêu chỉ là “dùng Java mới hơn”, nhóm chưa có đủ căn cứ để đánh giá lợi ích và chi phí.

### Bước 3 — Xác định các ứng viên phiên bản

Thông thường nên so sánh một số lựa chọn có ý nghĩa:

- LTS hiện tại mà hệ sinh thái đang hỗ trợ tốt.
- LTS mới hơn nếu framework và dependency đã sẵn sàng.
- Một feature release nếu tổ chức có chiến lược cập nhật nhanh và cần tính năng cụ thể.
- Một baseline trung gian nếu hệ thống legacy chưa thể chuyển thẳng.

Không cần khảo sát mọi phiên bản từng phát hành. Chỉ đưa vào danh sách những lựa chọn có khả năng đáp ứng mục tiêu và có đường triển khai thực tế.

### Bước 4 — Kiểm tra compatibility matrix

Với từng ứng viên, kiểm tra:

1. JDK distribution có được tổ chức chấp thuận và còn được hỗ trợ không?
2. Gradle/Maven wrapper có chạy được trên JDK build không?
3. Framework và application server có hỗ trợ runtime đó không?
4. Dependency quan trọng có hỗ trợ runtime và bytecode đó không?
5. Agent, profiler và công cụ bảo mật có tương thích không?
6. Container, OS, CPU architecture và cloud platform có cung cấp runtime phù hợp không?
7. Test framework và plugin build có hoạt động không?
8. Có thể vá lỗi và duy trì phiên bản trong thời gian dự kiến không?

Bất kỳ câu trả lời nào chưa rõ phải được ghi thành hạng mục xác minh.

### Bước 5 — Đánh giá lợi ích và chi phí chuyển đổi

Không chỉ so sánh tính năng Java. Hãy ước lượng:

- Số dependency cần nâng.
- Số module phải sửa mã nguồn.
- Mức thay đổi framework hoặc cấu hình.
- Thời gian kiểm thử hồi quy.
- Chi phí cập nhật image và hạ tầng.
- Tác động đến khách hàng hoặc consumer.
- Rủi ro vận hành và rollback.
- Thời gian hỗ trợ còn lại của target.

Một phiên bản có nhiều tính năng hơn nhưng đòi hỏi nâng toàn bộ framework và middleware có thể có chi phí lớn hơn lợi ích trong giai đoạn hiện tại.

### Bước 6 — Thử nghiệm trên lát cắt đại diện

Chọn một module hoặc dịch vụ có dependency, lưu lượng và cách triển khai đại diện. Thực hiện:

- Build bằng toolchain dự kiến.
- Kiểm tra release đích và bytecode.
- Chạy unit test, integration test và contract test.
- Khởi động ứng dụng trên JVM mục tiêu.
- Kiểm tra database, messaging, HTTP, TLS và authentication.
- Chạy agent giám sát và công cụ bảo mật.
- Đo hiệu năng với workload đại diện.
- Thử deploy, restart, shutdown và rollback.

Một bài kiểm tra chỉ chạy một class Java đơn giản không đủ để chứng minh hệ sinh thái của ứng dụng tương thích.

### Bước 7 — Chốt target và ghi nhận điều kiện

Quyết định cuối cùng cần ghi:

- Phiên bản Java đích.
- Nhà cung cấp và bản phân phối JDK.
- JDK chạy build và compiler toolchain.
- Release đích của bytecode.
- Runtime tối thiểu của production.
- Framework và dependency phải nâng.
- Thành phần chưa được xác minh.
- Mốc hỗ trợ và thời điểm rà soát lại.
- Tiêu chí kiểm thử và phương án rollback.

Nếu còn blocker, quyết định nên ghi rõ điều kiện để được phê duyệt thay vì trình bày target như đã sẵn sàng.

## 9. Ví dụ cấu hình tách toolchain và release đích

Giả sử tổ chức muốn dùng JDK 25 để build, nhưng một số dịch vụ vẫn cần hỗ trợ Java 21. Có thể tách compiler toolchain và release đích.

### 9.1. Gradle

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Cấu hình trên thể hiện:

- Compiler toolchain sử dụng JDK 25.
- Mã nguồn được biên dịch theo giới hạn Java 21.
- Bytecode được tạo cho release 21.
- Runtime production tối thiểu cần hỗ trợ Java 21, với điều kiện dependency và thư viện cũng đáp ứng.

Cần kiểm tra thêm phiên bản Gradle wrapper có thể chạy trên JDK 25 hay không. JDK chạy Gradle daemon và toolchain compiler là hai lựa chọn có thể được cấu hình riêng.

### 9.2. Maven

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Cấu hình release không tự chọn JDK chạy Maven. Cần quản lý riêng JDK của môi trường build, phiên bản Maven, Compiler Plugin và các plugin khác.

### 9.3. Xác nhận artifact

Có thể kiểm tra class file bằng:

~~~bash
javap -verbose -classpath app.jar com.example.Main
~~~

Tìm major version của class. Ví dụ:

| Java release | Major version |
|---|---:|
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Kiểm tra một class đại diện chưa chắc đã chứng minh mọi class trong JAR đều cùng phiên bản. Dependency đóng gói kèm có thể được biên dịch theo release khác. Với ứng dụng có nhiều module hoặc nhiều JAR, cần kiểm tra toàn bộ artifact quan trọng.

## 10. Xây dựng lộ trình chuyển đổi theo rủi ro

Một lộ trình tốt chia thay đổi thành các chặng có thể kiểm chứng.

### Chặng A — Chuẩn bị

- Kiểm kê JDK, framework, dependency, agent và môi trường triển khai.
- Xác nhận thời hạn hỗ trợ của bản phân phối JDK.
- Chọn ứng viên target và lập ma trận tương thích.
- Bổ sung test còn thiếu cho luồng nghiệp vụ quan trọng.
- Chụp baseline hiệu năng và lỗi production.

### Chặng B — Chuẩn hóa môi trường build

- Nâng Gradle/Maven wrapper nếu cần.
- Cấu hình JDK build và compiler toolchain.
- Xác định release đích.
- Cập nhật plugin và annotation processor.
- Đảm bảo CI có thể tái tạo artifact nhất quán.

### Chặng C — Cập nhật hệ sinh thái

- Nâng framework và dependency theo compatibility matrix.
- Thay thư viện đã ngừng hỗ trợ.
- Cập nhật JDBC driver, messaging client và SDK.
- Cập nhật agent, profiler và công cụ bảo mật.
- Xử lý API nội bộ hoặc reflection không còn phù hợp.

### Chặng D — Chạy trên runtime mục tiêu

- Dùng artifact đã được build theo release đã chọn.
- Triển khai lên môi trường staging có cấu hình gần production.
- Kiểm tra startup, shutdown, health check và tích hợp.
- Chạy test nghiệp vụ, contract và hồi quy.
- Đo CPU, memory, GC, throughput và latency.

### Chặng E — Triển khai có kiểm soát

- Triển khai theo canary hoặc từng nhóm dịch vụ nếu kiến trúc cho phép.
- Theo dõi error rate, latency, saturation và log JVM.
- Xác nhận dashboard và alert vẫn hoạt động.
- Giữ artifact và image trước đó để rollback.
- Chỉ mở rộng sau khi tiêu chí ổn định được đáp ứng.

### Chặng F — Rà soát vòng đời

Sau khi migration hoàn tất, ghi lại baseline mới và lịch rà soát. Không nên chờ đến khi JDK hết hỗ trợ mới bắt đầu lập kế hoạch tiếp theo.

## 11. Các chiến lược lựa chọn thường gặp

| Chiến lược | Phù hợp khi | Điểm cần chú ý |
|---|---|---|
| Chọn LTS mới nhất đã được hệ sinh thái hỗ trợ | Ứng dụng cần vòng đời dài và framework đã sẵn sàng | Xác nhận support policy của đúng vendor |
| Giữ LTS hiện tại, nâng runtime trước | Cần giảm rủi ro và tách thay đổi runtime khỏi source | Có thể phải thực hiện thêm một đợt nâng sau đó |
| Nâng toolchain nhưng giữ release đích | Muốn chuẩn hóa CI mà vẫn hỗ trợ consumer cũ | Kiểm soát API và dependency theo release |
| Theo feature release định kỳ | Tổ chức có CI mạnh và triển khai thường xuyên | Cần lịch cập nhật và kiểm thử liên tục |
| Chọn baseline thấp nhất dùng chung | Thư viện được nhiều ứng dụng ở nhiều phiên bản tiêu thụ | Có thể hạn chế việc dùng API mới |
| Chuyển theo nhiều chặng | Legacy có nhiều dependency và ràng buộc | Cần quản lý rõ trạng thái trung gian |

Không có một chiến lược duy nhất phù hợp cho mọi hệ thống. Quyết định nên dựa trên mục tiêu, mức rủi ro chấp nhận được, khả năng hỗ trợ của hệ sinh thái và thời gian duy trì.

## 12. Những sai lầm thường gặp khi chọn phiên bản đích

### Chọn phiên bản mới nhất mà không kiểm tra framework

Compiler có thể chấp nhận mã nguồn nhưng framework hoặc plugin vẫn chưa hỗ trợ runtime mới. Cần kiểm tra compatibility matrix và thử nghiệm ứng dụng hoàn chỉnh.

### Chỉ xem nhãn LTS

LTS không tự động bảo đảm bản phân phối đang dùng còn nhận bản vá hoặc được hỗ trợ trên nền tảng triển khai. Phải kiểm tra đúng vendor, edition, OS và hợp đồng hỗ trợ.

### Nhầm JDK build với runtime production

JDK của CI không chứng minh production đang chạy cùng phiên bản. Hãy ghi nhận riêng build JVM, compiler toolchain, release đích và runtime.

### Bỏ qua dependency gián tiếp

Ứng dụng có thể không gọi trực tiếp một API cũ, nhưng dependency hoặc agent có thể dùng API nội bộ, native library hoặc bytecode không tương thích. Cần kiểm tra toàn bộ chuỗi dependency quan trọng.

### Chọn target theo tính năng mà không có nhu cầu thực tế

Tính năng mới chỉ có giá trị khi giải quyết một vấn đề cụ thể. Nếu không có yêu cầu về hiệu năng, bảo mật hoặc khả năng bảo trì, chi phí migration có thể vượt lợi ích.

### Chỉ kiểm thử trên máy developer

Máy developer có thể khác production về JDK vendor, OS, architecture, container, certificate, locale, agent và giới hạn bộ nhớ. Cần kiểm thử trên môi trường đại diện.

### Đợi đến sát ngày hết hỗ trợ mới nâng cấp

Migration thường cần cập nhật framework, dependency, image, test và quy trình triển khai. Bắt đầu quá muộn sẽ làm giảm thời gian xử lý blocker và tăng rủi ro gián đoạn.

### Nâng mọi module cùng một lúc

Các module có thể có mức độ phụ thuộc và tốc độ release khác nhau. Nên phân nhóm theo runtime, framework và mức độ rủi ro, sau đó chuyển từng nhóm theo lộ trình phù hợp.

## 13. Mẫu quyết định phiên bản đích

Có thể dùng mẫu sau trong tài liệu kỹ thuật hoặc đề xuất migration:

~~~text
APPLICATION
  Name:
  Business criticality:
  Deployment model:
  Expected maintenance horizon:

CURRENT BASELINE
  JDK distribution:
  Build JVM:
  Compiler toolchain:
  Compiler release:
  Production runtime:
  Framework:
  Main dependencies:
  OS / container / architecture:
  Agents / native components:

TARGET DECISION
  Target Java release:
  JDK distribution and vendor:
  Build JVM:
  Compiler toolchain:
  Compiler release:
  Minimum production runtime:
  Reason for selecting this target:

ECOSYSTEM COMPATIBILITY
  Build tool:
  Framework:
  Dependencies:
  Test tools:
  Agents:
  Native components:
  Deployment platform:
  Vendor support policy:

APPLICATION REQUIREMENTS
  Required Java features:
  Security requirements:
  Performance goals:
  Compatibility contract:
  Minimum supported consumer runtime:

VALIDATION
  Build and bytecode checks:
  Unit and integration tests:
  Contract and regression tests:
  Runtime smoke tests:
  Performance checks:
  Operational checks:

RISKS AND CONDITIONS
  Known blockers:
  Unverified components:
  Required upgrades:
  Owner and due date:

ROLLOUT
  Pilot module/service:
  Staging criteria:
  Production rollout:
  Monitoring window:
  Rollback artifact and runtime:

LIFECYCLE
  Support source:
  Support end date:
  Next review date:
  Upgrade owner:
~~~

Một quyết định tốt phải có thể giải thích tại sao chọn phiên bản này, tại sao các ứng viên khác chưa phù hợp, thành phần nào đã được xác minh và điều kiện nào còn phải hoàn thành.

## 14. Ghi nhớ khi chốt phiên bản Java

Trước khi phê duyệt target, hãy trả lời được các câu hỏi:

1. Ứng dụng cần tính năng hoặc yêu cầu kỹ thuật nào khiến phải nâng phiên bản?
2. Phiên bản đích là LTS hay feature release, và nhà cung cấp JDK cam kết hỗ trợ đến khi nào?
3. JDK chạy build, compiler toolchain, release đích và production runtime có được xác định riêng không?
4. Framework, build tool, dependency, test tooling, agent và native library đã hỗ trợ chưa?
5. OS, container, CPU architecture và nền tảng triển khai có cung cấp runtime phù hợp không?
6. Ứng dụng cần giữ tương thích với consumer hoặc môi trường cũ nào?
7. Có bằng chứng build, test, startup, tích hợp, hiệu năng và vận hành trên target chưa?
8. Ai theo dõi bản vá bảo mật và thời điểm bắt đầu migration tiếp theo?

Có thể tóm lược quyết định bằng ba nguyên tắc:

- **Đáp ứng ứng dụng:** phiên bản phải cung cấp API, hiệu năng và mức bảo mật cần thiết cho sản phẩm.
- **Được hệ sinh thái hỗ trợ:** framework, dependency, build tool, agent và nền tảng triển khai phải có đường tương thích rõ ràng.
- **Duy trì được trong thực tế:** nhà cung cấp có chính sách hỗ trợ phù hợp, tổ chức có khả năng cập nhật và lộ trình có thể kiểm thử, triển khai, rollback.

Khi ba điều kiện này được xác nhận bằng tài liệu và thử nghiệm, phiên bản đích mới thực sự sẵn sàng cho migration.
