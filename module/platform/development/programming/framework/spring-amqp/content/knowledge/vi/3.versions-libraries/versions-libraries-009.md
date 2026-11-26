# Đọc tài liệu đúng phiên bản và theo dõi tính năng bị ngừng hỗ trợ

Khi học **SPRING_AMQP**, một ví dụ RabbitTemplate hoặc @RabbitListener có thể chạy trên dự án này nhưng không biên dịch, không có cùng cấu hình hoặc không hoạt động như mong đợi trên dự án khác. Nguyên nhân không nhất thiết nằm ở đoạn Java: phiên bản Spring Boot, Spring AMQP, RabbitMQ Java client, RabbitMQ broker và Java runtime có thể khác nhau. Tài liệu của nhánh mới nhất cũng không mặc nhiên mô tả chính xác ứng dụng đang chạy bản cũ.

Bài học thuộc chương **Phiên bản và thư viện**, hướng dẫn cách đối chiếu tài liệu với phiên bản thực tế, phát hiện API/cấu hình đã bị đánh dấu ngừng hỗ trợ, đánh giá thay đổi trước khi nâng cấp, và lưu lại bằng chứng để nhóm có thể bảo trì hệ thống dùng exchange, queue, binding, RabbitTemplate, @RabbitListener, retry, dead-letter, xác nhận giao nhận và các luồng bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Liệt kê những phiên bản ảnh hưởng đến một ứng dụng Spring AMQP và phân biệt phiên bản khai báo với phiên bản thực tế được giải quyết khi build/chạy.
2. Tìm đúng **Reference Guide**, **API Javadoc**, **release notes**, **migration guide** và tài liệu RabbitMQ cho phiên bản đang sử dụng.
3. Phân biệt **deprecated**, **scheduled for removal**, **removed**, **changed behavior**, **unsupported/EOL** và lỗ hổng bảo mật.
4. Đọc cảnh báo deprecation trong IDE/compiler, so sánh các API tương ứng và lập kế hoạch thay đổi có căn cứ.
5. Thiết kế kiểm tra hồi quy để bảo vệ đường đi của message, cấu hình listener, acknowledgements, retry/DLQ và khả năng tương thích producer–consumer sau nâng cấp.

## 2. “Phiên bản Spring AMQP” không phải một con số duy nhất

Một ứng dụng gửi message thường có nhiều lớp phụ thuộc:

~~~mermaid
flowchart TD
    APP["Ứng dụng Java"]
    BOOT["Spring Boot<br/>starter, auto-configuration, dependency management"]
    AMQP["Spring AMQP<br/>spring-rabbit / spring-amqp"]
    CLIENT["RabbitMQ Java Client<br/>com.rabbitmq:amqp-client"]
    BROKER["RabbitMQ Server<br/>exchange, queue, DLX, policy"]
    ERLANG["Erlang/OTP runtime của broker"]
    JVM["JDK/JRE của ứng dụng"]
    APP --> BOOT
    BOOT --> AMQP
    AMQP --> CLIENT
    CLIENT <-->|"AMQP 0-9-1, mạng"| BROKER
    BROKER --> ERLANG
    JVM -.-> APP
~~~

| Lớp | Tìm thông tin ở đâu | Vì sao cần kiểm tra |
|---|---|---|
| **Java/JDK** | Java runtime chạy ứng dụng; cấu hình toolchain/build | Phiên bản tối thiểu, cú pháp Java, thư viện và khả năng chạy |
| **Spring Boot** | Plugin, parent/BOM, dependency tree | Starter AMQP, auto-configuration, tên cấu hình và tập dependency được quản lý |
| **Spring Framework** | Dependency tree/BOM | Cơ sở tương thích cho các module Spring |
| **Spring AMQP** | spring-rabbit, spring-amqp trong dependency tree | RabbitTemplate, listener containers, annotation, converter, retry và các API |
| **RabbitMQ Java client** | com.rabbitmq:amqp-client trong dependency tree | Connection/channel, recovery, các API phía client |
| **RabbitMQ broker** | Thông tin cluster/node đang chạy | Kiểu queue, policies, dead-letter, plugin và hành vi phía server |
| **Erlang/OTP** | Thông tin cài đặt broker và bảng hỗ trợ RabbitMQ | Tính tương thích của runtime với phiên bản broker; khác JVM của ứng dụng |

**AMQP 0-9-1** là phiên bản giao thức được RabbitMQ Java client truyền thống sử dụng trong các trường hợp phổ biến với Spring AMQP. Đây là một thông số giao thức, **không** phải số phiên bản artifact `spring-amqp`. Một số hệ thống RabbitMQ còn có các giao thức và kiểu workload khác; cần xác nhận ứng dụng thật sự dùng stack nào trước khi lấy tài liệu.

### Ví dụ sai lệch dễ gặp

Giả sử ứng dụng đang dùng một nhánh Spring Boot A, có các Spring AMQP artifact được BOM quản lý, trong khi người phát triển mở trang “current” của Spring AMQP nhánh B mới hơn. Trang này có thể giới thiệu một class, property, signature hoặc hành vi chỉ tồn tại ở B. Việc đoạn mã đó có vẻ đúng về logic không chứng minh nó sử dụng được với artifact A.

Tương tự, một trang RabbitMQ mô tả tính năng hoặc tùy chọn của broker mới hơn không bảo đảm cụm RabbitMQ đang chạy đã hỗ trợ tính năng đó. Với quorum queue, dead-letter, policies hay plugin, phiên bản **server** rất quan trọng; với các lời gọi Channel/Connection, phiên bản **Java client** cũng quan trọng.

## 3. Xác định phiên bản thực tế trước khi tìm tài liệu

Thực hiện bước này trên **đúng branch, commit, profile, môi trường và artifact** bạn đang sửa. Một dự án có thể chạy khác nhau ở local, staging và production.

### 3.1. Nếu ứng dụng dùng Gradle

Với Spring Boot, thường có dependency như:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

Phiên bản của `spring-boot-starter-amqp` và các thư viện con thường được quyết định bởi Spring Boot BOM hoặc cơ chế quản lý dependency của build. Khai báo không có số phiên bản **không có nghĩa** là ứng dụng sử dụng bản mới nhất trên Internet.

Để xem phiên bản thật đã được giải quyết (ví dụ trên PowerShell/Windows):

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-rabbit --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-amqp --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency amqp-client --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-boot-starter-amqp --configuration runtimeClasspath
~~~

Ở Linux/macOS, đổi `.\gradlew.bat` thành `./gradlew`. Đối với module nhiều project, thêm đường dẫn task của module cần kiểm tra (ví dụ `:app:dependencyInsight`). Nếu classpath dùng tên khác, chọn đúng configuration được ứng dụng triển khai.

Khi đọc kết quả, chú ý:

- **Requested version:** yêu cầu ban đầu, có thể là khoảng phiên bản, version catalog, plugin hoặc dependency khác.
- **Selected/resolved version:** phiên bản Gradle cuối cùng chọn.
- **Selection reason:** ví dụ được ràng buộc bởi dependency constraints, BOM hoặc một conflict resolution.
- **Dependency origin:** thư viện nào kéo artifact đến; phiên bản được override trực tiếp hay do starter quản lý.

Nếu compileClasspath và runtimeClasspath có kết quả khác nhau, phải hiểu điểm khác biệt đó trước khi kết luận phiên bản đang chạy. `gradlew --version` cho biết phiên bản công cụ Gradle và JVM chạy Gradle, **không** tự nói lên phiên bản RabbitMQ client đang được đóng gói.

### 3.2. Nếu ứng dụng dùng Maven

Kiểm tra dependency được giải quyết:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.amqp:*,com.rabbitmq:amqp-client
./mvnw help:effective-pom
~~~

Trong Windows/PowerShell, dùng `mvnw.cmd` thay `./mvnw`; cần trích dẫn/escape đối số chứa `*` tùy shell. `dependency:tree` giúp nhìn bản thực tế và nguồn phụ thuộc; `effective-pom` cho biết dependency management/parent và các cấu hình Maven hợp thành. Hãy phân biệt phiên bản được parent/BOM định nghĩa với phiên bản bị override ở từng module.

### 3.3. Xác định Java runtime và RabbitMQ server

~~~bash
java -version
rabbitmqctl status
~~~

`java -version` phải được kiểm tra trong môi trường **chạy ứng dụng** (container hoặc máy chủ), vì JDK trên máy phát triển có thể khác. `rabbitmqctl status` chạy ở môi trường có quyền truy cập node RabbitMQ; tùy cách triển khai, thông tin phiên bản có thể xem qua RabbitMQ Management UI/API hoặc công cụ quản trị tương ứng. Với cluster, kiểm tra các node có liên quan và nhận biết giai đoạn rolling upgrade có thể có nhiều phiên bản.

Không cần chạy command trên production chỉ để học; điều cần ghi nhận là **kết quả có nguồn gốc rõ ràng**, bao gồm thời điểm, môi trường và cách thu thập.

### 3.4. Lập “bản chụp phiên bản”

Một bảng nhỏ giúp tránh tranh luận dựa trên giả định:

| Thành phần | Phiên bản xác minh | Nguồn chứng cứ | Môi trường |
|---|---|---|---|
| JDK | `<java-runtime-version>` | `java -version` của process/container | staging |
| Spring Boot | `<boot-version>` | parent/BOM + dependency tree | staging build |
| spring-rabbit | `<resolved-version>` | Gradle dependencyInsight / Maven dependency:tree | staging build |
| spring-amqp | `<resolved-version>` | Dependency tree | staging build |
| amqp-client | `<resolved-version>` | Dependency tree | staging build |
| RabbitMQ Server | `<broker-version>` | Node/management information | staging cluster |

Các giá trị trong dấu `<...>` chỉ là chỗ điền, không phải phiên bản khuyến nghị. Nếu hệ thống dùng Spring Boot BOM, vẫn phải kiểm tra dependency tree để phát hiện override hoặc phiên bản được chọn do xung đột.

## 4. Tìm đúng tài liệu: chọn sản phẩm, chọn nhánh, chọn thời điểm

Nguồn ưu tiên cho một câu hỏi kỹ thuật phụ thuộc vào loại câu hỏi:

| Cần trả lời điều gì? | Nguồn thích hợp nhất |
|---|---|
| RabbitTemplate, @RabbitListener, converter hoặc listener container hoạt động thế nào? | **Spring AMQP Reference Guide** cùng nhánh/version và API Javadoc tương ứng |
| Một API có mặt, bị deprecated hoặc bị xóa từ phiên bản nào? | **Javadoc/class source** của bản đang dùng; release notes/migration guide của bản đích |
| `spring.rabbitmq.*` cấu hình như thế nào? | **Spring Boot Reference** và configuration metadata của đúng Spring Boot version |
| BOM quản lý phiên bản nào? | **Spring Boot dependency versions** hoặc effective dependency graph của ứng dụng |
| DLX, queue TTL, quorum queue, exchange/binding được broker xử lý ra sao? | **RabbitMQ server documentation** đúng phiên bản/capability, cộng với cấu hình thực tế |
| Nâng cấp có breaking changes gì? | **Release notes, migration/upgrade guide, changelog** xuyên suốt các phiên bản bị bỏ qua |
| Có còn nhận bản vá bảo mật không? | **Chính sách hỗ trợ và thông báo bảo mật** chính thức của nhánh đó |

Các điểm bắt đầu từ nguồn chính thức:

- Spring AMQP Reference: <https://docs.spring.io/spring-amqp/reference/>
- Spring AMQP project/releases: <https://spring.io/projects/spring-amqp> và <https://github.com/spring-projects/spring-amqp/releases>
- Spring Boot Reference: <https://docs.spring.io/spring-boot/reference/>
- Spring Boot AMQP messaging: <https://docs.spring.io/spring-boot/reference/messaging/amqp.html>
- RabbitMQ documentation: <https://www.rabbitmq.com/docs>
- RabbitMQ upgrade guide: <https://www.rabbitmq.com/docs/upgrade>
- RabbitMQ Java client repository/releases: <https://github.com/rabbitmq/rabbitmq-java-client/releases>
- RabbitMQ ↔ Erlang/OTP compatibility: <https://www.rabbitmq.com/docs/which-erlang>

**Lưu ý:** Các đường dẫn “reference” không gắn phiên bản thường hướng đến tài liệu hiện hành. Trước khi dùng làm bằng chứng cho phiên bản cũ, hãy chọn phiên bản trong bộ chọn tài liệu hoặc truy cập bản lưu trữ đúng nhánh, kiểm tra số version trên trang và ghi lại URL chính xác. Không suy từ đường dẫn “current”, “stable” hay “latest” rằng trang đang xem phù hợp với artifact của dự án. Một số dự án thay đổi cấu trúc URL theo nhánh; sử dụng trình chọn phiên bản và liên kết được công bố trên trang dự án sẽ an toàn hơn việc tự đoán một URL.

### Quy trình đọc một vấn đề cụ thể

Ví dụ câu hỏi: *“Làm sao để listener dùng manual acknowledgement?”*

1. Xác định version `spring-rabbit`, Spring Boot, RabbitMQ Java client đang dùng.
2. Mở mục **listener containers/acknowledgement** của Spring AMQP Reference **đúng version**.
3. Nếu cấu hình bằng `spring.rabbitmq.listener.simple.*` hoặc `spring.rabbitmq.listener.direct.*`, đối chiếu **Spring Boot Reference** cùng version để xem tên property và kiểu listener container.
4. Đối chiếu Javadoc cho method/class đang gọi, ví dụ `AcknowledgeMode`, `SimpleRabbitListenerContainerFactory` hoặc các tham số listener.
5. Kiểm tra release notes của các phiên bản ở giữa nếu đang nâng cấp; cách sử dụng hợp lệ hôm nay có thể đã đổi default hoặc nhận cảnh báo deprecation.
6. Thử với message thành công, message lỗi, consumer restart và redelivery để xác minh **hành vi chạy thật**.

Trang Stack Overflow, blog và ví dụ GitHub có thể hữu ích để hiểu vấn đề, nhưng cần biết ngày đăng, phiên bản nguồn và cấu hình thực tế. Copy một đoạn code không có thông tin version là nguồn phổ biến của lỗi biên dịch hoặc lỗi hành vi.

## 5. Đọc thông tin deprecation và ngừng hỗ trợ cho đúng

Các từ khóa thường bị hiểu lẫn:

| Trạng thái | Diễn giải chính xác | Hành động |
|---|---|---|
| **Deprecated** | API vẫn có thể tồn tại nhưng tác giả khuyến nghị không dùng cho code mới | Đọc Javadoc về API thay thế; lập kế hoạch đổi |
| **Deprecated for removal** | Có chỉ báo dự định loại bỏ API trong tương lai; không tự khẳng định phiên bản xóa | Ưu tiên thay trước khi lên nhánh đích; kiểm tra release notes |
| **Removed** | API/cấu hình không còn hiện diện hoặc không còn được nhận trong một bản cụ thể | Phải migrate để build/chạy trên bản đó |
| **Changed behavior** | API còn tên nhưng default, semantics, error handling hoặc điều kiện hoạt động đã khác | Kiểm thử hành vi, không chỉ compile |
| **Unsupported / EOL** | Nhánh hoặc sản phẩm đã hết phạm vi hỗ trợ theo chính sách nhà cung cấp | Xem lựa chọn nâng cấp và rủi ro vận hành/bảo mật |
| **Vulnerable** | Một phiên bản có cảnh báo bảo mật cụ thể | Xác minh phạm vi ảnh hưởng, bản vá và biện pháp giảm thiểu |

Không thể kết luận một API bị xóa chỉ vì IDE gạch ngang nó. Ngược lại, code biên dịch thành công không chứng minh cấu hình cũ vẫn còn hiệu lực hoặc hành vi khi có lỗi vẫn giống trước.

### 5.1. Đọc @Deprecated của Java

Ví dụ **minh họa về cú pháp Java**, không phải tên API có thật trong Spring AMQP:

~~~java
public class ExampleApi {
    /**
     * @deprecated Prefer publish(Message) for new code.
     */
    @Deprecated(since = "2.0", forRemoval = true)
    public void sendOldStyle(String payload) {
        // ...
    }

    public void publish(byte[] messageBody) {
        // ...
    }
}
~~~

Ở đây:

- `@Deprecated` là tín hiệu của tác giả thư viện; compiler/IDE có thể cảnh báo khi code sử dụng API đó.
- `since` diễn đạt phiên bản bắt đầu đánh dấu deprecated **theo tác giả API**, không tự cho biết phiên bản xóa.
- `forRemoval = true` nói có kế hoạch loại bỏ, nhưng **không** cho biết ngày hoặc bản cụ thể.
- Phần Javadoc `@deprecated` có thể giải thích vì sao bỏ API và nên thay bằng gì. Nếu Javadoc không nêu cách thay, cần xem release notes, migration guide hoặc thay đổi source code tương ứng.

Khi kiểm tra Spring AMQP, phải đọc Javadoc **của đúng class/method trên đúng phiên bản**. Tên method giống nhau nhưng overload, kiểu trả về và khả năng xử lý ngoại lệ có thể đã khác.

### 5.2. Những dạng thay đổi không phát cảnh báo @Deprecated

Ví dụ một phiên bản mới có thể thay đổi:

- Giá trị mặc định của cấu hình listener, converter hoặc recovery.
- Property cấu hình Spring Boot bị đổi tên, chuyển scope hoặc không còn được bind.
- Định dạng/kiểu của message headers do converter hoặc framework tạo.
- Yêu cầu Java tối thiểu hoặc khả năng tương thích giữa các thế hệ Spring Framework.
- Tính năng RabbitMQ broker/policy khiến cùng message được xếp hàng, hết TTL hoặc dead-letter khác đi.

Đặc biệt, chuyển thế hệ Spring Boot/Spring Framework có thể kéo theo thay đổi nền tảng như Java baseline và hệ sinh thái `javax.*`/`jakarta.*`. Đây là những **điểm phải kiểm tra ở migration guide của nhánh cụ thể**; không suy ra mọi dự án hoặc mọi phiên bản đều gặp cùng thay đổi.

## 6. Theo dõi deprecation thành công việc thực tế

Một cảnh báo chỉ có ích khi nhóm biết **nó xuất hiện ở đâu, ảnh hưởng gì và cần thay trước mốc nào**. Hãy duy trì danh sách theo dõi theo các trường:

| Trường | Nội dung cần ghi |
|---|---|
| Component | `spring-rabbit`, `spring-amqp`, Spring Boot, `amqp-client`, RabbitMQ broker... |
| Current → target | Phiên bản thực tế hiện tại và phiên bản mục tiêu đã quyết định |
| API/property/feature | Tên đầy đủ, vị trí gọi, file và dòng trong code hoặc cấu hình |
| Thay đổi | Deprecated, removal, behavior change, EOL, security advisory |
| Nguồn chính thức | URL docs/Javadoc/release notes của đúng phiên bản |
| Giải pháp | API/property thay thế, thay đổi topology hay quy trình vận hành |
| Ảnh hưởng | Compile, runtime, routing, dữ liệu, khả năng tương thích, downtime |
| Xác minh | Test dự kiến/kết quả, người phụ trách, thời điểm triển khai |

Ví dụ bảng tiến độ **giả định** (không khẳng định một API Spring AMQP thật đang deprecated):

~~~text
Component: <artifact-and-version>
API: <fully-qualified-class-or-method>
Status: DEPRECATED (verified in version <x>)
Replacement: <replacement-from-that-version's-Javadoc>
Target: <chosen-version>
Risk: listener requeue or message conversion behavior
Evidence: <link-to-versioned-javadoc-and-release-note>
Validation: compile + integration tests with real RabbitMQ
Owner / Due date: <team> / <date>
~~~

Tránh tạo “danh sách deprecated toàn hệ thống” chỉ bằng tìm chuỗi trong source. Một trường hợp có thể thuộc API của Java, Spring Framework, Spring Boot, Spring AMQP, RabbitMQ Java client hoặc plugin của tổ chức; chính sách nâng cấp và nguồn chứng cứ khác nhau.

### Cách rà soát định kỳ

1. Khi nhận yêu cầu nâng cấp hoặc có bản vá bảo mật, chụp lại dependency graph và phiên bản broker.
2. Đọc **toàn bộ release notes/migration guide của các nhánh bị vượt qua**, không chỉ ghi chú của bản đích.
3. Kiểm tra các cảnh báo compiler/IDE và tài liệu chính thức của API đang gọi.
4. Kiểm tra thay đổi default hoặc cấu hình bị ngừng hỗ trợ ngay cả khi không có cảnh báo compile.
5. Đưa vấn đề thành công việc có chủ sở hữu, mức độ ưu tiên và tiêu chí kiểm thử.
6. Sau nâng cấp, ghi lại phiên bản thực tế, kết quả kiểm thử và các điểm còn phải theo dõi.

## 7. Quản lý thư viện để tránh đọc nhầm tài liệu

### 7.1. Ưu tiên hệ sinh thái phiên bản được quản lý

Trong ứng dụng Spring Boot, cách phổ biến là khai báo `spring-boot-starter-amqp` và cho phép **BOM tương ứng** quản lý bộ dependency tương thích. Không nên thêm phiên bản `spring-rabbit` hoặc `amqp-client` tùy ý chỉ để copy một ví dụ trên mạng. Một override có thể làm lệch quan hệ giữa starter, Spring Framework, converter, client và autoconfiguration.

Ví dụ build **minh họa**, cần thay placeholder bằng phiên bản có thật và phù hợp với dự án:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đoạn này thể hiện cơ chế dependency management, **không** phải mẫu có thể copy chạy ngay khi chưa thay placeholder và cấu hình repository/toolchain cần thiết. Nếu dùng Gradle native platforms/BOM hoặc version catalog, hãy kiểm tra cơ chế đang áp dụng thay vì thêm plugin mới theo thói quen.

Khi buộc phải override một dependency:

- Có lý do cụ thể (ví dụ bản vá bảo mật, lỗi được xác nhận, yêu cầu sản phẩm).
- Đã kiểm tra các ràng buộc tương thích do Spring Boot/Spring AMQP công bố.
- Có test integration đủ chứng minh luồng publish, consume, reconnect, retry và các loại queue đang dùng.
- Có ghi lại thay đổi dependency graph và cách rollback.

### 7.2. Khóa phiên bản hay luôn cập nhật latest?

Một build tái lập cần biết chính xác tập phiên bản được giải quyết. BOM, lockfile, artifact repository policy và container image digest là những công cụ hỗ trợ tính tái lập (tùy hệ thống). “Dùng latest” liên tục mà không khóa hoặc kiểm chứng có thể làm một build hôm nay khác build tuần sau.

Ngược lại, khóa mãi phiên bản đã hết hỗ trợ khiến ứng dụng lỡ bản vá và cải tiến. Quy trình tốt là **cập nhật có kiểm soát**: có ứng viên phiên bản cụ thể, kiểm tra release notes, xây dựng/test, triển khai từng môi trường và theo dõi trước khi áp dụng rộng.

## 8. Phân biệt các nguồn tài liệu khi nâng cấp Spring AMQP

Đọc tài liệu theo **câu hỏi**, tránh dùng một trang cho mọi vấn đề.

### 8.1. Spring Boot và Spring AMQP có vai trò khác nhau

Ví dụ bạn thấy:

~~~properties
spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.listener.simple.acknowledge-mode=auto
~~~

Các property `spring.rabbitmq.*` được Spring Boot bind theo tính năng/autoconfiguration của phiên bản Boot. Nhưng chi tiết `RabbitTemplate`, `MessageConverter`, `AcknowledgeMode` và cách listener container xử lý delivery nằm ở Spring AMQP. Vì vậy phải đọc **cả hai bộ tài liệu ở phiên bản phù hợp**, nhất là khi thay đổi chế độ ack, requeue, concurrency hoặc retry.

Lưu ý: `auto` ở đây là **AUTO acknowledgement mode theo Spring AMQP**, không đơn giản bằng “broker auto-ack ngay khi nhận”; cách container ack/nack phụ thuộc kết quả xử lý và cấu hình. Đừng tự suy luận semantics chỉ từ tên property.

### 8.2. RabbitMQ server có vòng đời riêng

Một cấu hình queue có arguments:

~~~java
Queue queue = QueueBuilder.durable("orders.created.q")
        .deadLetterExchange("orders.dlx")
        .build();
~~~

Code sử dụng API của Spring AMQP để khai báo queue. Tuy nhiên, việc dead-letter xảy ra thế nào, policy nào được áp dụng, queue đích tồn tại hay không, và giới hạn của từng loại queue là hành vi của RabbitMQ broker. Khi nâng cấp broker, phải đọc tài liệu server riêng.

Trong vận hành thực tế, RabbitMQ khuyến nghị cân nhắc policies cho các tham số vận hành có thể thay đổi, thay vì luôn hard-code `x-arguments` trong ứng dụng. Tuy nhiên, lựa chọn cụ thể phụ thuộc loại tham số và kiến trúc; một số tham số chỉ thiết lập được lúc khai báo queue. Nên kiểm tra tài liệu đúng broker version và thử sự tương tác giữa policy và client-declared arguments.

### 8.3. API tồn tại không đồng nghĩa tính năng hỗ trợ end-to-end

Khi muốn dùng một tính năng queue hoặc delivery mới, hãy kiểm tra tuần tự:

~~~mermaid
flowchart TD
    A["Tính năng định dùng"] --> B{"Broker version và plugin hỗ trợ?"}
    B -->|Không| R["Chọn giải pháp khác / kế hoạch nâng cấp broker"]
    B -->|Có| C{"Java client và Spring AMQP có API/phương thức phù hợp?"}
    C -->|Không| S["Kiểm tra library upgrade hoặc cách tích hợp khác"]
    C -->|Có| D{"Cấu hình ứng dụng và topology tương thích?"}
    D -->|Không| T["Sửa cấu hình, policy, binding, triển khai"]
    D -->|Có| E["Integration test với cùng đặc tính broker đích"]
~~~

Điều này quan trọng cho quorum queues, stream workload, dead-lettering, publisher confirms và consumer recovery: mỗi tính năng có tập điều kiện riêng. Không lập một “ma trận tất cả tương thích” bằng suy đoán từ số phiên bản major.

## 9. Quy trình nâng cấp có bằng chứng

Giả sử mục tiêu là nâng một hệ thống đang dùng RabbitTemplate gửi `OrderCreated` vào direct exchange, @RabbitListener nhận từ queue, có retry và dead-letter khi xử lý lỗi.

### Bước 1 — Chốt baseline

Ghi lại branch/commit, phiên bản Java, Spring Boot BOM, spring-amqp/spring-rabbit, amqp-client và RabbitMQ server. Giữ cấu hình liên quan: exchange, routing key, queue, binding, kiểu queue, durability, TTL, DLX, listener container, retry/requeue, concurrency, ack mode, publisher confirms/returns.

### Bước 2 — Chọn ứng viên nâng cấp rõ ràng

Nêu **phiên bản nguồn** và **phiên bản đích** của từng thành phần. Kiểm tra chính sách hỗ trợ và bảng tương thích do các dự án công bố. Nếu chỉ cần sửa lỗi ở client, cân nhắc mức thay đổi nhỏ nhất được hỗ trợ; nếu cần nâng major, chuẩn bị kiểm tra sâu hơn.

### Bước 3 — Đọc đầy đủ các thay đổi giữa hai điểm

Theo dõi release notes, migration guides, deprecated API, removal, behavior/default changes và yêu cầu nâng Java/Framework. Tách thay đổi bắt buộc để build khỏi thay đổi cần test runtime. Không bỏ qua các phiên bản trung gian khi thay đổi trải qua nhiều release.

### Bước 4 — Sửa code/cấu hình theo bản đích

Tìm các call sites của API bị deprecated/removed, cập nhật các method/class/configuration property bằng **hướng dẫn thay thế thực tế** của dự án. Sau khi sửa, compile và kiểm tra còn cảnh báo deprecation nào trong phần code mình sở hữu.

Không thay mọi tên có chứa “old” hoặc mọi property nghe có vẻ lỗi thời: một API có thể vẫn được hỗ trợ vì hợp đồng tương thích, còn một thay đổi khác không có cảnh báo compiler nhưng lại ảnh hưởng semantics.

### Bước 5 — Kiểm thử hành vi liên quan message

| Kịch bản | Điều cần chứng minh |
|---|---|
| Publish bình thường | Message vào đúng queue theo exchange, routing key và binding |
| Publish unroutable | Ứng dụng xử lý chính sách mandatory/returns và log đúng nếu được cấu hình |
| Payload/headers | JSON hoặc định dạng dùng thực tế, converter, contentType, schema version tương thích |
| Ack thành công | Listener xử lý message và xác nhận đúng theo ack mode |
| Exception tạm thời | Retry/backoff/requeue đúng giới hạn, tránh lặp vô hạn |
| Exception vĩnh viễn | Reject/dead-letter đúng theo policy/configuration, DLQ nhận được message mong đợi |
| Consumer mất kết nối | Recovery, redelivery và idempotency hoạt động như thiết kế |
| Broker restart/failover | Các cam kết về durability, confirms, reconnect và queue type được kiểm chứng |
| Producer/consumer phiên bản khác nhau | Các bên trao đổi được message khi rolling deploy |

Kiểm thử tích hợp cần sử dụng RabbitMQ có **phiên bản và cấu hình tương đương môi trường đích**; unit test với mock RabbitTemplate không đủ để chứng minh dead-letter, confirm hay redelivery từ broker. Có thể dùng môi trường test được quản lý hoặc container hóa với version cố định.

### Bước 6 — Triển khai theo giai đoạn và theo dõi

Với hệ thống bất đồng bộ, nên đo ít nhất: độ sâu queue, tỷ lệ lỗi listener, số message trong DLQ, số lần retry, độ trễ xử lý, tỷ lệ connection recovery, publisher confirm/return failure (nếu đã cấu hình). Kiểm tra cả **thời gian xử lý** và **khả năng xử lý trùng** sau rolling deploy.

Một bản nâng cấp thành công không chỉ là build xanh; nó cần bảo vệ trạng thái message và hợp đồng với những producer/consumer triển khai lệch phiên bản trong thời gian chuyển tiếp.

## 10. Tình huống phân tích: tài liệu mới làm mẫu code cũ không chạy

### Tình huống A — Ví dụ không có class hoặc method

**Dấu hiệu:** IDE báo `Cannot resolve symbol` hoặc `NoSuchMethodError` khi chạy.

**Kiểm tra:**

1. Đọc dependency tree: phiên bản nào thực sự chứa trong build/runtime?
2. Mở Javadoc/class source đúng artifact version, xem signature và overload.
3. So ngày/nhánh của trang ví dụ với bản đang dùng.
4. Kiểm tra conflict hoặc jar cũ xuất hiện lúc runtime dù compile dùng jar mới.
5. Chọn API phù hợp với phiên bản hiện tại hoặc nâng cấp theo migration guide.

`NoSuchMethodError` có thể xuất hiện do **binary incompatibility** hoặc classpath runtime không nhất quán. Không nên kết luận đơn giản rằng RabbitMQ server quá cũ khi lỗi thực tế nằm ở jar Java.

### Tình huống B — Cấu hình không tạo hành vi mong đợi

**Dấu hiệu:** Listener vẫn tự ack, retry không diễn ra, hoặc hàng đợi không dead-letter như bài hướng dẫn.

**Kiểm tra:**

- Property có được Spring Boot version này hỗ trợ và bind tới đúng listener container không?
- Có custom `RabbitListenerContainerFactory` nào override auto-configuration không?
- Retry là retry trong memory của listener hay dùng message/broker để trì hoãn?
- Queue có DLX, DLQ và binding phù hợp? Broker có quyền publish tới DLX và config policy tương ứng không?
- Các mặc định requeue/ack trong Spring AMQP version đang chạy là gì?

Đôi khi code hoàn toàn hợp lệ nhưng property đặt cho `simple` container trong khi ứng dụng tạo `direct` container, nên hành vi vẫn khác. Cần đọc cả tài liệu Boot và AMQP đúng phiên bản, kiểm tra cấu hình bean đang hoạt động.

### Tình huống C — Nâng cấp có cảnh báo deprecated nhưng vẫn chạy

**Dấu hiệu:** Application startup ổn, song IDE ghi cảnh báo từ một class hoặc setter.

**Xử lý:** tìm cảnh báo ở Javadoc/version đang dùng, đọc lý do và tên thay thế; xem release notes bản đích. Nếu chỉ có deprecation, thường chưa buộc sửa ngay để chạy phiên bản hiện tại. Tuy vậy, hãy ghi vào danh sách theo dõi vì bản đích tương lai có thể loại bỏ API hoặc đổi semantics.

### Tình huống D — Tài liệu RabbitMQ “current” khác cluster

**Dấu hiệu:** Server trả lỗi khai báo queue, policy hoặc unsupported argument.

**Kiểm tra:** version/node thực tế, loại queue, plugin và khả năng hỗ trợ của server; đọc tài liệu phù hợp; rà soát thay đổi trên các node đang rolling upgrade. Không suy từ version Spring AMQP rằng broker đã có tính năng tương ứng.

## 11. Bảng quyết định nhanh khi đọc một trang tài liệu

Với một trang nói về Spring AMQP/RabbitMQ, tự trả lời sáu câu:

| Câu hỏi | Nếu chưa biết, làm gì? |
|---|---|
| **Đây là tài liệu sản phẩm nào?** | Phân biệt Spring Boot, Spring AMQP, Java client và RabbitMQ broker |
| **Trang này mô tả phiên bản nào?** | Tìm version selector, banner và nguồn release |
| **Ứng dụng đang chạy bản nào?** | Kiểm tra resolved dependencies và broker/runtime thực tế |
| **Nội dung nói về API, config hay broker?** | Chọn Javadoc, Boot Reference hoặc RabbitMQ docs đúng loại |
| **Có cảnh báo deprecated/removed/changed behavior không?** | Tra Javadoc, migration guide và release notes các bản trung gian |
| **Điều này đã được kiểm thử trên stack mục tiêu chưa?** | Thêm kiểm thử thực tế với phiên bản/configuration tương ứng |

Nếu chưa xác nhận **cả trang đang đọc và phiên bản đang chạy**, đừng áp dụng thay đổi chỉ vì ví dụ trông quen thuộc.

## 12. Bài tập thực hành

### Bài 1 — Bắt lỗi “đọc nhầm bản”

Bạn thấy ví dụ `RabbitTemplate` dùng một overload mới trên tài liệu hiện hành nhưng IDE dự án báo không có method.

Hãy mô tả các bước cần làm **trước khi sửa code**. Đáp án mong đợi: xác nhận `spring-rabbit` đã resolved; mở Javadoc đúng version; kiểm tra overload/since và release notes; xác định có thể dùng API tương đương trên nhánh cũ hay phải nâng cấp cùng BOM.

### Bài 2 — Phân loại thông báo

Phân loại các tình huống sau thành deprecated, removal, behavior change hoặc unsupported:

1. Javadoc có `@Deprecated(since="X")` và method vẫn biên dịch.
2. Build lên phiên bản Y thì method không còn trong jar.
3. Method giữ nguyên chữ ký nhưng default requeue không phù hợp cấu hình trước đó.
4. Nhánh thư viện không còn được nhà cung cấp hỗ trợ.

Đáp án: lần lượt là **deprecated**, **removed**, **changed behavior** và **unsupported/EOL**. Trường hợp 3 phải xác minh thay đổi thực sự từ release notes/tests; ở đây chỉ là tình huống giả định.

### Bài 3 — Soạn bảng phiên bản môi trường

Lấy số phiên bản thực tế của JDK, Spring Boot, `spring-rabbit`, `spring-amqp`, `amqp-client`, RabbitMQ server trong môi trường thực hành. Ghi rõ nguồn, ngày thu thập và môi trường. Sau đó mở tài liệu của đúng nhánh để tìm cấu hình ack/retry.

### Bài 4 — Thiết kế regression test trước nâng cấp

Hệ thống dùng direct exchange, queue durable, publisher confirms và listener có DLQ. Hãy đề xuất ít nhất năm bài test nhằm kiểm tra routing, xác nhận publish, xử lý lỗi, dead-letter và redelivery sau broker/consumer restart. Với từng test, nêu kết quả mong đợi và bằng chứng quan sát (message trong queue, callback, DLQ, log, metrics).

### Bài 5 — Xử lý override dependency

Một nhóm override `com.rabbitmq:amqp-client` lên version khác với BOM chỉ vì nhìn thấy một ví dụ mới. Trước khi chấp nhận thay đổi, họ cần bằng chứng gì? Đáp án: lý do override, ma trận/ghi chú tương thích chính thức, resolved dependency graph, release notes và integration tests đúng luồng message. Không kết luận tương thích chỉ vì Maven/Gradle build thành công.

## 13. Ghi nhớ

- **Luôn xác minh phiên bản thực tế:** BOM/parent chỉ là điểm xuất phát; resolved dependency tree và runtime/broker mới phản ánh stack đang dùng.
- **Tài liệu “current/latest” không mặc định đúng với dự án:** chọn Reference, Javadoc, release notes và migration guide theo nhánh của artifact hoặc server.
- **Deprecated khác removed, và compile pass khác behavior pass:** phải xét cả thay đổi API, default, cấu hình, schema và vận hành.
- **Spring Boot, Spring AMQP, RabbitMQ Java client và RabbitMQ server có tài liệu/vòng đời riêng:** đọc đúng tầng đang gây vấn đề.
- **Theo dõi thay đổi bằng bằng chứng:** lưu API/property, version nguồn–đích, URL nguồn chính thức, mức ảnh hưởng và test xác minh.
- **Nâng cấp cần kiểm thử luồng message end-to-end:** routing, converter, ack, retry, DLQ, recovery, confirms, idempotency và khả năng trao đổi khi các service chạy phiên bản khác nhau.

Khả năng đọc đúng tài liệu theo phiên bản giúp bạn dùng RabbitTemplate và @RabbitListener một cách có căn cứ, tránh xây giải pháp trên những API đã đổi hoặc tính năng RabbitMQ broker chưa hỗ trợ, đồng thời giảm rủi ro khi duy trì hệ thống xử lý bất đồng bộ lâu dài.
