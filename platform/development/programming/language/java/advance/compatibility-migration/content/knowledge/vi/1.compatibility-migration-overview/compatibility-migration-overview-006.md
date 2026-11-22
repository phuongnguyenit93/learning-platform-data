# Phạm vi chuyển đổi: JDK, công cụ build, dependency và framework

## 1. Hiểu đúng phạm vi của một đợt chuyển đổi tương thích Java

Chuyển đổi tương thích Java là quá trình đưa một ứng dụng hoặc một hệ thống module từ nền tảng Java hiện tại sang một nền tảng mục tiêu, đồng thời giữ cho mã nguồn, quá trình build, thư viện, framework và môi trường chạy tiếp tục hoạt động đúng.

Phạm vi chuyển đổi vì vậy không dừng ở việc thay phiên bản JDK. Một ứng dụng có thể biên dịch bằng JDK mới nhưng vẫn không build được vì plugin Gradle hoặc Maven chưa tương thích; build thành công nhưng không khởi động vì framework yêu cầu phiên bản thư viện khác; hoặc khởi động bình thường nhưng thay đổi hành vi khi xử lý HTTP, transaction, JSON, ngày giờ hay cấu hình.

Khi xác định phạm vi, cần nhìn hệ thống theo các lớp có quan hệ với nhau:

```text
Mã nguồn và bytecode Java
          │
          ▼
JDK, compiler và JVM
          │
          ▼
Công cụ build, plugin và quy trình đóng gói
          │
          ▼
Dependency trực tiếp và dependency bắc cầu
          │
          ▼
Framework, adapter và thư viện tích hợp
          │
          ▼
Môi trường triển khai và vận hành
```

Các lớp này không độc lập. Phiên bản framework thường giới hạn phiên bản JDK tối thiểu; framework lại quản lý phiên bản của nhiều dependency; plugin build có thể yêu cầu một JDK khác với JDK mà ứng dụng dùng lúc chạy. Vì vậy, phạm vi cần bao gồm cả những thành phần bị ảnh hưởng trực tiếp lẫn các thành phần phụ thuộc vào thay đổi đó.

## 2. JDK: phiên bản Java, compiler và JVM

JDK là một phần trung tâm của phạm vi chuyển đổi, nhưng cần phân biệt ba khái niệm thường bị gộp chung:

- **JDK dùng để chạy công cụ build:** JVM khởi chạy Gradle, Maven, compiler plugin và các công cụ build khác.
- **Java toolchain dùng để biên dịch:** JDK cung cấp `javac`, `javadoc` và các công cụ tương ứng để tạo bytecode.
- **JRE/JVM dùng để chạy ứng dụng:** môi trường thực tế thực thi bytecode đã đóng gói.

Ba vai trò này có thể dùng cùng một phiên bản, nhưng không bắt buộc phải giống nhau trong mọi cấu hình. Một build có thể chạy bằng JDK mới trong khi toolchain biên dịch nhắm đến một phiên bản Java thấp hơn. Ngược lại, việc build thành công bằng JDK mới không chứng minh máy chủ production đã có runtime phù hợp.

### 2.1. Mức tương thích của mã nguồn và bytecode

Khi đổi JDK, cần xác định rõ ứng dụng có thay đổi ngôn ngữ Java hay chỉ thay đổi môi trường biên dịch và chạy.

| Thành phần | Câu hỏi cần xác định |
|---|---|
| Source compatibility | Mã nguồn hiện tại có còn hợp lệ với compiler mục tiêu không? Có cú pháp, annotation hoặc API cần thay đổi không? |
| Language level | Dự án có chủ động sử dụng tính năng của phiên bản Java mới không? |
| Bytecode target | Bytecode được tạo ra có chạy được trên phiên bản JVM tối thiểu đã cam kết không? |
| JDK API | Các API đang dùng còn tồn tại, còn được hỗ trợ và giữ hành vi mong muốn không? |
| Runtime behavior | JVM mới có làm thay đổi hành vi liên quan đến encoding, reflection, class loading, garbage collection, thread hoặc security không? |

Ví dụ, `--release` của `javac` giúp giới hạn cả mức bytecode lẫn tập API Java được phép sử dụng theo phiên bản đích. Chỉ đặt `sourceCompatibility` và `targetCompatibility` không phải lúc nào cũng thay thế đầy đủ ý nghĩa của `--release`. Với Gradle, nên cấu hình Java toolchain và mức release một cách nhất quán; với Maven, cần kiểm tra cấu hình compiler plugin và JDK thực tế mà Maven đang chạy.

Ví dụ cấu hình Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Ví dụ cấu hình Maven Compiler Plugin:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Các con số trong ví dụ chỉ minh họa cách khai báo. Phiên bản thực tế phải lấy từ baseline và mục tiêu đã được dự án lựa chọn.

### 2.2. API, module system và hành vi JVM

Ngoài cú pháp ngôn ngữ, phạm vi JDK cần rà soát các API đã bị loại bỏ, API nội bộ từng được truy cập trực tiếp, thay đổi quyền truy cập do Java Platform Module System, cơ chế reflection và các tùy chọn JVM cũ.

Một số dấu hiệu cần điều tra gồm:

- Mã nguồn hoặc thư viện truy cập lớp trong các package nội bộ như `sun.*` hoặc `com.sun.*`.
- Ứng dụng phụ thuộc vào reflection để truy cập thành viên không public.
- JVM arguments cũ không còn được nhận diện hoặc có ý nghĩa khác.
- Thư viện sử dụng cơ chế class loading, instrumentation, proxy hoặc serialization nhạy cảm với phiên bản runtime.
- Thay đổi về TLS, chứng thư, thuật toán mật mã hoặc chính sách bảo mật làm ảnh hưởng kết nối ra ngoài.

Không nên tự động thêm các tùy chọn mở module hoặc hạ mức bảo mật chỉ để làm lỗi biến mất. Mỗi tùy chọn tương thích tạm thời cần có lý do, phạm vi áp dụng và kế hoạch loại bỏ.

### 2.3. Môi trường chạy

Phạm vi JDK còn bao gồm cách phân phối và cài đặt runtime: bản JDK/JRE được dùng, nhà cung cấp, hệ điều hành, kiến trúc CPU, image container, cấu hình heap, giới hạn bộ nhớ và các JVM flags. Nếu production chạy trong container, cần kiểm tra cả base image và cách container cấp tài nguyên cho JVM. Máy local có JDK mới không chứng minh image production đã được cập nhật.

## 3. Công cụ build: Gradle, Maven và toàn bộ chuỗi build

Công cụ build chịu trách nhiệm biến mã nguồn thành artifact có thể kiểm tra và triển khai. Chuyển đổi JDK có thể làm lộ ra giới hạn tương thích của wrapper, plugin, task tùy chỉnh hoặc công cụ phụ trợ.

Phạm vi công cụ build cần kiểm tra ít nhất các thành phần sau:

| Thành phần | Nội dung cần kiểm tra |
|---|---|
| Gradle Wrapper / Maven Wrapper | Phiên bản wrapper được khóa trong repository, khả năng chạy trên JDK mục tiêu và cách tải distribution. |
| Build tool runtime | Phiên bản JDK dùng để khởi chạy Gradle hoặc Maven. |
| Compiler plugin | Khả năng gọi compiler mục tiêu và thiết lập source/release/target. |
| Plugin bên ngoài | Plugin Spring Boot, Kotlin, Checkstyle, SpotBugs, JaCoCo, code coverage, packaging, publishing và các plugin khác. |
| Annotation processor | Khả năng chạy trên JDK mục tiêu và tương thích với compiler mới. |
| Task tùy chỉnh | API Gradle/Maven được sử dụng, cách truy cập file, process, configuration và task graph. |
| Test engine | JUnit Platform, test framework, mock framework và plugin chạy test. |
| Code generation | OpenAPI, protobuf, QueryDSL, MapStruct hoặc công cụ sinh mã khác. |
| Đóng gói và phát hành | JAR/WAR, executable archive, metadata, manifest, signing và publication. |

### 3.1. Phân biệt JDK chạy Gradle với toolchain của dự án

Gradle Wrapper khóa phiên bản Gradle của dự án, nhưng không tự động đồng nghĩa với việc mọi task đều biên dịch bằng cùng một JDK. Gradle daemon cần một JVM tương thích để chạy; Java toolchain có thể chọn JDK riêng cho compile, test hoặc javadoc.

Do đó, khi chuyển đổi cần kiểm tra cả hai phía:

1. Phiên bản Gradle có thể khởi chạy trên JDK được chọn cho build hay không.
2. Các task compile/test có dùng đúng toolchain và đúng mức bytecode mục tiêu hay không.

Với Maven, cần kiểm tra JDK đang chạy Maven, Maven Wrapper, Maven Compiler Plugin, Surefire/Failsafe và các plugin tham gia đóng gói. `maven.compiler.release` chỉ điều khiển mức biên dịch; nó không tự thay đổi JDK đang khởi chạy Maven.

### 3.2. Plugin và task là một phần của phạm vi

Build có thể thất bại trước khi biên dịch mã nguồn nếu một plugin không tương thích với phiên bản Gradle, Maven hoặc JDK mới. Những plugin ít được chú ý như plugin kiểm tra chất lượng, tạo báo cáo, sinh mã, đóng gói image và publish artifact cũng có thể chặn pipeline.

Không nên chỉ kiểm tra file build chính. Cần lần theo plugin được khai báo trong `plugins`, `buildscript`, parent POM, profile Maven, convention plugin, build logic dùng chung và script được áp dụng gián tiếp. Nếu repository có nhiều module, cần xác định module nào dùng plugin hoặc toolchain riêng.

### 3.3. Build phải tái lập được

Một đợt chuyển đổi chỉ đáng tin cậy khi kết quả build có thể tái tạo trong môi trường CI và môi trường phát triển được hỗ trợ. Vì vậy, phạm vi nên ghi nhận wrapper, toolchain, repository dependency, biến môi trường cần thiết và lệnh build chuẩn. Tránh phụ thuộc vào JDK cài ngầm trên một máy cá nhân hoặc phiên bản plugin không được khóa rõ ràng.

## 4. Dependency: thư viện trực tiếp, bắc cầu và quản lý phiên bản

Dependency là các thư viện và artifact mà dự án cần để biên dịch, kiểm thử, chạy hoặc đóng gói. Phạm vi chuyển đổi phải bao gồm dependency trực tiếp do dự án khai báo và dependency bắc cầu được kéo vào thông qua các thư viện khác.

Ví dụ, ứng dụng khai báo một starter của framework có thể không khai báo trực tiếp HTTP client, JSON mapper, logging implementation hoặc thư viện validation. Tuy nhiên, các thư viện đó vẫn nằm trong runtime classpath và có thể chịu ảnh hưởng của thay đổi JDK hoặc framework.

### 4.1. Phân loại dependency

Nên phân loại dependency theo mục đích sử dụng để tránh bỏ sót thành phần:

- **Compile/API:** thư viện xuất hiện trong kiểu dữ liệu, chữ ký public hoặc mã nguồn biên dịch.
- **Runtime:** thư viện cần khi ứng dụng khởi động hoặc xử lý nghiệp vụ.
- **Test:** JUnit, Mockito, AssertJ, test container và các thư viện hỗ trợ kiểm thử.
- **Build-time:** annotation processor, plugin, generator và công cụ được gọi trong quá trình build.
- **Provided/Container:** thư viện được môi trường triển khai cung cấp, ví dụ API servlet trong một số mô hình WAR.
- **Optional/Feature-specific:** thư viện chỉ được dùng khi bật một tính năng hoặc module nhất định.

Phân loại này giúp xác định lỗi xảy ra ở giai đoạn compile, test, startup hay runtime; đồng thời giúp tránh đóng gói nhầm thư viện mà container đã cung cấp.

### 4.2. Dependency bắc cầu và xung đột phiên bản

Một thư viện có thể kéo theo nhiều dependency khác. Hai nhánh dependency có thể yêu cầu các phiên bản khác nhau của cùng một artifact. Build tool sẽ áp dụng quy tắc phân giải phiên bản, nhưng việc resolve thành công không bảo đảm các thư viện tương thích về binary hoặc hành vi.

Khi chuyển đổi, cần:

1. Xuất dependency tree hoặc dependency insight cho các configuration quan trọng.
2. Xác định thư viện cũ, thư viện trùng chức năng, dependency bị thay thế và dependency chỉ còn được kéo vào gián tiếp.
3. Kiểm tra dependency nào có giới hạn JDK, framework hoặc API nền tảng.
4. Đối chiếu phiên bản thực tế sau khi áp dụng BOM, constraint, dependency management, exclusion và version catalog.
5. Kiểm tra cả compile classpath, runtime classpath và test classpath.

Không nên giải quyết mọi xung đột bằng cách ép phiên bản mới nhất. Phiên bản mới có thể yêu cầu API khác, thay đổi hành vi hoặc không nằm trong bộ phiên bản đã được framework hỗ trợ.

### 4.3. BOM và nguồn quản lý phiên bản

Bill of Materials (BOM) định nghĩa một tập phiên bản dependency được thiết kế để phối hợp với nhau. Framework thường cung cấp BOM hoặc dependency management riêng. Khi nâng framework, cần xem xét bộ phiên bản được framework quản lý trước khi ghi đè từng dependency.

Nếu dự án tự khai báo phiên bản cho một thư viện mà BOM đang quản lý, cần xác định rõ lý do. Override không phù hợp có thể tạo ra tổ hợp phiên bản chưa được kiểm chứng. Với repository nhiều module, nên thống nhất nơi quản lý phiên bản để tránh mỗi module tự chọn một phiên bản khác nhau mà không có chủ đích.

### 4.4. API, license và bảo mật

Phạm vi dependency còn bao gồm thay đổi package, class, method, generic signature, annotation, serialization format, license và lỗ hổng bảo mật. Một dependency thay phiên bản có thể làm thay đổi API mà mã nguồn dự án đang gọi, hoặc thay đổi dữ liệu được ghi/đọc giữa các phiên bản ứng dụng.

Với các thư viện ảnh hưởng đến giao thức hoặc dữ liệu bền vững, cần xác định khả năng tương thích ngược và xuôi: phiên bản mới có đọc được dữ liệu cũ không, các service khác có tiếp tục hiểu payload mới không, và rollback có còn khả thi không.

## 5. Framework: nền tảng ứng dụng và các tích hợp liên quan

Framework cung cấp cấu trúc và cơ chế thực thi cho ứng dụng. Chuyển đổi framework thường có phạm vi rộng hơn thay đổi dependency đơn lẻ vì framework định nghĩa nhiều hợp đồng chung: cấu hình, lifecycle, dependency injection, transaction, web stack, persistence, security và quan sát hệ thống.

Trong một ứng dụng Java, các nhóm framework và thư viện nền tảng có thể gồm:

- Framework ứng dụng như Spring Framework và Spring Boot.
- Web stack như Servlet API, Spring MVC, WebFlux hoặc framework HTTP khác.
- Persistence như Jakarta Persistence/JPA, Hibernate và JDBC.
- Serialization như Jackson, JSON-B hoặc thư viện XML.
- Security như Spring Security, OAuth/OIDC client và thư viện mật mã.
- Validation như Jakarta Bean Validation và implementation tương ứng.
- Messaging và integration như Kafka, AMQP, JMS hoặc HTTP client.
- Logging, metrics, tracing và health check.
- Framework kiểm thử và test integration.

Không phải dự án nào cũng dùng tất cả các nhóm này. Phạm vi thực tế phải dựa trên những thành phần đang có trong dependency graph, cấu hình và mã nguồn của dự án.

### 5.1. Tương thích giữa framework và JDK

Mỗi phiên bản framework thường quy định phiên bản Java tối thiểu, phiên bản thư viện nền tảng được hỗ trợ và phiên bản của các integration module. Khi chọn JDK mục tiêu, phải đối chiếu với phiên bản framework dự kiến sử dụng.

Nếu JDK mục tiêu mới hơn mức tối thiểu của framework, điều đó chỉ chứng minh framework có thể chấp nhận mức Java đó theo chính sách hỗ trợ; vẫn cần kiểm tra các thư viện tích hợp, plugin và tính năng cụ thể. Ngược lại, nâng framework có thể buộc phải nâng JDK trước hoặc đồng thời.

### 5.2. Thay đổi namespace và API nền tảng

Một ví dụ quan trọng là quá trình chuyển từ Java EE namespace `javax.*` sang Jakarta EE namespace `jakarta.*` trong các thế hệ nền tảng tương ứng. Đây là thay đổi ở tên package và hệ sinh thái API, không đơn thuần là thay một phiên bản dependency.

Khi một framework mục tiêu yêu cầu Jakarta namespace, cần kiểm tra đồng bộ:

- Import và annotation trong mã nguồn.
- API Servlet, Persistence, Validation và các API Jakarta khác.
- Implementation runtime tương ứng.
- Dependency bắc cầu và thư viện tích hợp còn dùng namespace cũ.
- Cấu hình, XML descriptor, generated source và test fixture.

Không thể thay toàn bộ chuỗi `javax` thành `jakarta` một cách máy móc, vì không phải mọi package bắt đầu bằng `javax` đều thuộc nhóm API chuyển sang Jakarta. Cần dựa trên API cụ thể và phiên bản framework mục tiêu.

### 5.3. Thay đổi mặc định và hành vi

Framework mới có thể giữ nguyên tên API nhưng thay đổi hành vi mặc định. Các vùng thường cần chú ý gồm:

- Cách đăng ký bean, component scan, auto-configuration và thứ tự cấu hình.
- Điều kiện kích hoạt cấu hình theo classpath hoặc property.
- Transaction boundary, propagation, rollback và cách xử lý exception.
- Quy tắc mapping HTTP, content negotiation, validation và error response.
- Cơ chế xác thực, phân quyền, CSRF, CORS và filter chain.
- Mapping entity, lazy loading, query generation và schema handling.
- JSON naming, date/time format, null handling và polymorphic serialization.
- Logging level, metric name, tracing propagation và health endpoint.

Vì vậy, kiểm tra compile chỉ xác nhận một phần tương thích. Cần có kiểm thử tập trung vào hợp đồng mà ứng dụng đang cung cấp và tiêu thụ.

### 5.4. Cấu hình và tích hợp ngoài framework

Framework thường đọc cấu hình từ YAML, properties, environment variable, command-line argument hoặc secret store. Khi nâng phiên bản, tên property, kiểu dữ liệu, giá trị mặc định và vị trí cấu hình có thể thay đổi. Cần rà soát cấu hình theo môi trường, profile, biến môi trường trong CI/CD, cấu hình container và cấu hình do nền tảng triển khai cung cấp.

Các integration module cũng cần được xem như một phần của framework: database driver, migration tool, cache provider, message broker client, observability agent, application server và thư viện cloud. Một framework core tương thích không bảo đảm mọi adapter bên ngoài cũng tương thích.

## 6. Môi trường triển khai và chuỗi cung ứng phần mềm

Phạm vi chuyển đổi nên theo ứng dụng đến nơi nó thực sự chạy. Nếu chỉ cập nhật source và build script nhưng giữ nguyên môi trường triển khai cũ, ứng dụng có thể tiếp tục chạy bằng runtime không được hỗ trợ.

Các điểm cần đưa vào phạm vi khi có liên quan:

- Dockerfile, base image, image JRE/JDK và kiến trúc CPU.
- Máy chủ ứng dụng hoặc servlet container nếu ứng dụng không tự đóng gói runtime.
- Kubernetes manifest, startup command, readiness/liveness probe và resource limit.
- CI workflow, runner image, cache Gradle/Maven và cấu hình JDK.
- Script shell/PowerShell, công cụ migration database và công cụ vận hành.
- Certificate store, TLS, proxy, timezone, locale và encoding của môi trường.
- Quy trình build, scan, sign, publish, deploy, rollback và lưu trữ artifact.

Không phải mọi thay đổi môi trường đều thuộc mọi đợt migration. Chỉ đưa vào phạm vi các thành phần cần thay đổi hoặc cần xác minh để bảo đảm mục tiêu tương thích. Tuy nhiên, phải ghi nhận rõ thành phần nào được giữ nguyên và bằng chứng cho thấy nó vẫn hỗ trợ nền tảng mục tiêu.

## 7. Xác định ranh giới: điều gì thuộc và không thuộc đợt chuyển đổi?

Một phạm vi tốt phải đủ rộng để bao phủ tác động kỹ thuật, đồng thời đủ rõ để tránh biến migration thành một dự án viết lại toàn bộ ứng dụng.

**Thông thường thuộc phạm vi:**

- Nâng hoặc thay JDK, compiler, JVM runtime và cấu hình toolchain.
- Nâng wrapper, build tool, plugin và task cần thiết để build/test trên nền tảng mục tiêu.
- Điều chỉnh dependency trực tiếp, bắc cầu, BOM, constraint và version alignment.
- Nâng framework hoặc adapter bắt buộc để hỗ trợ JDK/dependency mục tiêu.
- Sửa mã nguồn, cấu hình và test bị ảnh hưởng bởi API hoặc hành vi thay đổi.
- Cập nhật image, CI và cấu hình triển khai cần thiết để chạy artifact mới.
- Bổ sung kiểm chứng tương thích và tài liệu hóa quyết định phiên bản.

**Chỉ thuộc phạm vi khi có yêu cầu hoặc bằng chứng riêng:**

- Thiết kế lại kiến trúc hoặc thay đổi cách phân chia module.
- Viết lại nghiệp vụ không liên quan đến tương thích.
- Thay database, message broker hoặc nhà cung cấp cloud chỉ vì muốn hiện đại hóa.
- Thay giao thức hoặc hợp đồng public không bắt buộc bởi nền tảng mục tiêu.
- Tối ưu hiệu năng diện rộng không có liên hệ với thay đổi JDK/framework.
- Thay đổi giao diện người dùng hoặc quy trình sản phẩm không liên quan đến migration.

Nếu trong quá trình chuyển đổi phát hiện một cải tiến khác có giá trị, cần ghi nhận thành hạng mục riêng và nêu rõ mối liên hệ. Không gộp thay đổi nghiệp vụ vào migration nếu nó làm khó việc xác định nguyên nhân lỗi hoặc đánh giá khả năng rollback.

## 8. Lập bản đồ tương thích trước khi thay đổi

Trước khi cập nhật phiên bản, cần lập bản đồ cho trạng thái hiện tại và trạng thái mục tiêu. Bản đồ này giúp phát hiện ràng buộc trước khi thực hiện thay đổi hàng loạt.

Một ma trận tối thiểu có thể có dạng:

| Lớp | Baseline hiện tại | Mục tiêu | Ràng buộc cần xác minh |
|---|---|---|---|
| JDK chạy build | Phiên bản đang dùng trong CI/local | JDK mục tiêu | Gradle/Maven và plugin có chạy được không? |
| Java toolchain | Compiler hiện tại | Compiler mục tiêu | Source level, release và API có phù hợp không? |
| Runtime | JDK/JRE production | Runtime mục tiêu | Image, server và JVM options có hỗ trợ không? |
| Build tool | Wrapper hiện tại | Wrapper mục tiêu | Build logic và plugin có tương thích không? |
| Dependency | BOM và cây dependency hiện tại | Bộ dependency mục tiêu | Có xung đột, API bị loại bỏ hoặc thư viện không còn hỗ trợ không? |
| Framework | Framework và adapter hiện tại | Framework mục tiêu | Có breaking change, namespace hoặc thay đổi mặc định nào không? |
| Triển khai | CI, container, server hiện tại | Môi trường sau chuyển đổi | Artifact mới có build, deploy và rollback được không? |

Không nhất thiết mọi phiên bản đều phải được nâng cùng lúc. Có thể tồn tại một giai đoạn trung gian để nâng build tool, xử lý cảnh báo hoặc chuyển dependency trước khi nâng framework. Tuy nhiên, mỗi trạng thái trung gian phải là tổ hợp có thể build và kiểm chứng được, thay vì một tập phiên bản được chọn tùy ý.

### 8.1. Thu thập hiện trạng

Thông tin hiện trạng nên lấy từ cấu hình có hiệu lực và môi trường thực thi, không chỉ từ ghi chú của dự án. Các nguồn thường cần xem gồm:

- `java -version` và `javac -version` trong môi trường liên quan.
- `./gradlew --version` hoặc `mvn -version` để xác định JVM chạy build.
- Wrapper, build script, parent POM, plugin và convention build logic.
- Dependency report cho compile, runtime và test.
- BOM, version catalog, dependency constraint và exclusion.
- Framework configuration, application properties/YAML và profile.
- Dockerfile, CI workflow, startup script và manifest triển khai.

Với dự án nhiều module, cần ghi nhận module dùng chung nền tảng và module có cấu hình riêng. Một module có thể dùng Java toolchain khác, plugin khác hoặc runtime dependency riêng; không nên suy ra cấu hình của toàn repository từ một module đại diện duy nhất.

### 8.2. Phân loại rủi ro và thứ tự xử lý

Mỗi khác biệt giữa baseline và mục tiêu nên được phân loại theo mức ảnh hưởng:

- **Không tương thích trực tiếp:** thành phần không thể chạy, build hoặc biên dịch với phiên bản mục tiêu.
- **Cần thay đổi mã nguồn/cấu hình:** API hoặc property đã đổi, package đã chuyển hoặc cấu hình cũ không còn hiệu lực.
- **Có nguy cơ thay đổi hành vi:** build được nhưng runtime semantics hoặc hợp đồng bên ngoài có thể khác.
- **Cần xác minh môi trường:** chưa có bằng chứng về container, server, CI hoặc hệ điều hành.
- **Không bị ảnh hưởng:** thành phần được giữ nguyên và có căn cứ xác nhận vẫn tương thích.

Thứ tự xử lý nên dựa trên quan hệ phụ thuộc. Ví dụ, cần chốt phiên bản JDK mục tiêu trước khi chọn wrapper; chốt framework mục tiêu trước khi khóa bộ dependency do framework quản lý; và xác định runtime cuối cùng trước khi cập nhật image production.

## 9. Kiểm chứng phạm vi sau chuyển đổi

Kiểm chứng phải bao phủ từng lớp đã đưa vào phạm vi. Một lệnh build thành công là tín hiệu cần thiết nhưng chưa đủ.

| Lớp | Bằng chứng kiểm chứng phù hợp |
|---|---|
| JDK/compiler | Build với toolchain mục tiêu; xác nhận release/bytecode; kiểm tra các API và JVM option liên quan. |
| Build tool | Chạy wrapper chuẩn trong môi trường CI; thực thi các task compile, test, package và publish cần thiết. |
| Dependency | Resolve dependency graph; kiểm tra xung đột; chạy test với runtime classpath thực tế. |
| Framework | Kiểm thử khởi động context, web endpoint, transaction, persistence, security, serialization và integration đang được dùng. |
| Môi trường chạy | Chạy artifact trong image/server mục tiêu; kiểm tra startup, health, kết nối ngoài và giới hạn tài nguyên. |
| Hợp đồng ứng dụng | So sánh request/response, event, dữ liệu lưu trữ và hành vi public trước/sau. |

Nên giữ một tập kiểm thử đại diện cho các luồng quan trọng của ứng dụng. Nếu migration ảnh hưởng đến schema, serialization hoặc message format, cần kiểm tra khả năng đọc dữ liệu cũ và tương tác với các service chưa được nâng cấp. Nếu triển khai theo từng phần, phải xác định rõ các phiên bản có thể cùng tồn tại trong giai đoạn chuyển tiếp.

## 10. Ví dụ về phạm vi của một đợt migration

Giả sử một ứng dụng đang chạy trên một JDK cũ, sử dụng Gradle, một framework web, ORM, JSON mapper và database driver. Mục tiêu là chuyển sang JDK mới và phiên bản framework được hỗ trợ trên JDK đó.

Phạm vi có thể được diễn đạt thành các nhóm công việc sau:

1. **JDK:** chọn runtime mục tiêu, cấu hình toolchain/compiler, xử lý API bị loại bỏ và kiểm tra JVM options.
2. **Build:** chọn Gradle Wrapper tương thích, cập nhật plugin và annotation processor, xác nhận build/test chạy được trong CI.
3. **Dependency:** cập nhật BOM hoặc dependency management, kiểm tra dependency bắc cầu, xử lý thư viện không còn hỗ trợ và xác minh classpath.
4. **Framework:** nâng framework web và các adapter liên quan, cập nhật API/namespace/configuration bị ảnh hưởng, kiểm tra hành vi mặc định.
5. **Vận hành:** cập nhật JDK base image, pipeline và startup configuration; chạy thử artifact trong môi trường mục tiêu.
6. **Tương thích dữ liệu và giao tiếp:** kiểm tra JSON, HTTP contract, schema và message format nếu các thành phần này bị ảnh hưởng.

Những việc như thay đổi nghiệp vụ, tách service, đổi database hoặc thiết kế lại API không tự động được đưa vào phạm vi. Chúng chỉ được thêm khi có yêu cầu độc lập hoặc khi một ràng buộc tương thích cụ thể chứng minh rằng thay đổi đó là cần thiết.

## 11. Đầu ra cần có khi chốt phạm vi

Khi phạm vi chuyển đổi được thống nhất, nhóm thực hiện nên có các đầu ra đủ rõ để người khác có thể tiếp tục công việc và kiểm tra kết quả:

- **Baseline:** danh sách phiên bản và cấu hình hiện tại của JDK, build tool, dependency, framework và môi trường chạy.
- **Target:** phiên bản mục tiêu cùng lý do lựa chọn và các ràng buộc hỗ trợ.
- **Compatibility matrix:** các tổ hợp phiên bản được chấp nhận, tổ hợp trung gian và tổ hợp không được hỗ trợ.
- **Dependency inventory:** dependency trực tiếp/bắc cầu, BOM, plugin và thư viện cần thay đổi.
- **Migration items:** các thay đổi mã nguồn, cấu hình, build và triển khai gắn với nguyên nhân cụ thể.
- **Verification evidence:** lệnh build/test, kết quả kiểm thử và bằng chứng chạy trên runtime mục tiêu.
- **Known limitations:** vấn đề chưa giải quyết, workaround còn tồn tại và điều kiện cần theo dõi.
- **Rollback considerations:** artifact, cấu hình và khả năng tương thích dữ liệu cần thiết để quay lại phiên bản trước.

Phạm vi càng rõ thì việc chia nhỏ migration càng an toàn. Mỗi thay đổi nên liên hệ được với một ràng buộc tương thích hoặc một mục tiêu đã thống nhất; mỗi ràng buộc quan trọng cần có cách kiểm chứng tương ứng. Nhờ đó, nhóm có thể phân biệt lỗi do JDK, build tool, dependency, framework hay môi trường triển khai, đồng thời biết chính xác phần nào đã được chuyển đổi và phần nào vẫn cần xử lý.
