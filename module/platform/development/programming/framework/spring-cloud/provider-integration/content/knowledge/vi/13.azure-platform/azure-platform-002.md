# BOM Azure và ma trận tương thích Spring Boot

Một dự án Spring Boot tích hợp Azure thường phụ thuộc đồng thời vào Spring Boot, Spring Framework, Spring Cloud Azure và nhiều thư viện Azure SDK for Java. Nếu từng dependency được khai báo phiên bản riêng, ứng dụng có thể vẫn biên dịch nhưng lỗi khi khởi tạo Spring context hoặc khi gọi dịch vụ cloud. **Bill of Materials (BOM)** giúp quản lý một nhóm phiên bản đã được phát hành cùng nhau; **ma trận tương thích** giúp chọn đúng *dòng* BOM cho phiên bản Spring Boot, Java và các thành phần Spring khác.

Bài thuộc chương **Nền tảng Azure** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Trong bối cảnh thực hành Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, quản lý phiên bản là bước nền trước khi triển khai xác thực và phân quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và so sánh giữa các provider.

## 1. Mục tiêu

Sau bài học, người học có thể:

1. Phân biệt **Spring Boot BOM**, **Spring Cloud BOM**, **Spring Cloud Azure BOM** và **Azure SDK BOM**.
2. Đọc ma trận tương thích để lựa chọn tổ hợp Spring Boot, Spring Cloud Azure và Java hợp lệ.
3. Cấu hình Maven hoặc Gradle sao cho starter và các thư viện Azure SDK được quản lý phiên bản đồng bộ.
4. Phân tích dependency tree/effective dependency management và xử lý xung đột dependency.
5. Xây dựng quy trình nâng cấp có kiểm chứng, phân biệt lỗi tương thích thư viện với lỗi danh tính/RBAC hoặc mạng Azure.

## 2. BOM là gì và giải quyết vấn đề nào?

**BOM (Bill of Materials)** là một artifact kiểu POM công bố tập phiên bản dependency đã được lựa chọn. Khi ứng dụng import BOM, công cụ build có thể suy ra phiên bản cho những dependency nằm trong danh sách quản lý.

Ví dụ, thay vì đặt riêng phiên bản cho **azure-core**, **azure-identity**, **azure-storage-blob** và các thư viện liên quan, dự án có thể dùng BOM phù hợp và khai báo dependency không gắn version.

BOM giúp:

- Giảm khai báo version trùng lặp.
- Giữ tập SDK theo các phiên bản đã được nhà phát hành thử nghiệm cùng nhau.
- Đơn giản hóa nâng cấp theo một điểm điều khiển trung tâm.
- Tăng khả năng tái lập build giữa môi trường phát triển, CI và sản xuất.

Nhưng BOM có **giới hạn**:

- **Không tự thêm dependency** vào dự án. Chỉ những artifact được khai báo trực tiếp hoặc kéo theo gián tiếp mới xuất hiện trong build.
- **Không đảm bảo mọi tổ hợp đều chạy được.** Cần xem ma trận tương thích, Java version, API thay đổi, hành vi runtime và kiểm thử thực tế.
- **Không cấu hình danh tính, quyền RBAC, endpoint hoặc resource Azure.**
- **Không cập nhật plugin build** như Spring Boot Gradle plugin, Maven Compiler hay Surefire nếu không có cấu hình riêng thích hợp.
- **Không tự sửa lỗi bảo mật.** Phải theo dõi advisory và cập nhật BOM lên bản vá được hỗ trợ.

### Dependency management khác dependency declaration

~~~mermaid
flowchart TD
    A[Spring Boot application] -->|khai báo| B[Spring Cloud Azure starter Blob]
    A -->|import BOM| C[Spring Cloud Azure dependencies BOM]
    C -.->|quản lý phiên bản| B
    B -->|phụ thuộc bắc cầu| D[Azure Storage Blob SDK]
    D --> E[Azure Core / Identity]
    C -.->|quản lý tập phiên bản tương thích| D
    C -.->|quản lý tập phiên bản tương thích| E
~~~

Mũi tên nét đứt cho thấy BOM **chọn phiên bản**, còn các mũi tên liền biểu thị **dependency được đưa vào ứng dụng**. Import BOM không đồng nghĩa thêm tất cả starter Azure.

## 3. Bốn lớp quản lý phiên bản dễ nhầm lẫn

| Lớp | Artifact/thành phần thường gặp | Chịu trách nhiệm chính | Cần dùng khi nào |
| --- | --- | --- | --- |
| **Spring Boot** | **org.springframework.boot:spring-boot-dependencies** hoặc parent **spring-boot-starter-parent** | Phiên bản các thư viện do hệ sinh thái Spring Boot quản lý | Gần như mọi ứng dụng Spring Boot |
| **Spring Cloud** | **org.springframework.cloud:spring-cloud-dependencies** | Căn chỉnh phiên bản của nhiều project Spring Cloud theo release train | Khi ứng dụng dùng các thành phần Spring Cloud cần release train đó |
| **Spring Cloud Azure** | **com.azure.spring:spring-cloud-azure-dependencies** | Căn chỉnh Spring Cloud Azure starter và các dependency Azure liên quan | Khi tích hợp Azure qua Spring Cloud Azure |
| **Azure SDK for Java** | **com.azure:azure-sdk-bom** | Căn chỉnh phiên bản tập Azure SDK cho ứng dụng Java | Khi sử dụng Azure SDK trực tiếp, đặc biệt không thông qua Spring Cloud Azure |

**Spring Cloud Azure BOM và Azure SDK BOM không đồng nghĩa.** Cả hai có thể quản lý một số tọa độ Azure SDK giống nhau, nhưng Spring Cloud Azure BOM được phát hành nhằm hỗ trợ **bộ starter của Spring Cloud Azure** trong môi trường Spring. Azure SDK BOM hướng tới tập thư viện SDK nói chung.

### Khi nào cần cả Spring Cloud Azure BOM và Azure SDK BOM?

Với ứng dụng Spring Boot đã dùng **spring-cloud-azure-dependencies**, hãy bắt đầu bằng chính BOM này và chỉ khai báo các starter cần dùng. Nếu cần thêm một Azure SDK không nằm trong tập starter, trước tiên kiểm tra phiên bản mà Spring Cloud Azure BOM hiện quản lý. Chỉ cân nhắc bổ sung **azure-sdk-bom** sau khi xác minh tác động của các phiên bản chồng lấn.

Không nên import hai BOM rồi mặc định nghĩ Maven/Gradle sẽ tự chọn tổ hợp tốt nhất: mỗi công cụ có quy tắc hòa giải version khác nhau. BOM nhập sau hoặc dependency khai báo trực tiếp có thể làm thay đổi effective version tùy cơ chế quản lý; cần đọc **effective POM/dependency insight** để biết kết quả thật.

### Một starter có thể cần thêm thành phần Spring khác

Các starter tích hợp Spring Data, Spring Security, Spring Integration hoặc Spring Cloud Stream có quan hệ với các release train của Spring tương ứng. Bởi vậy việc thấy một starter có version hợp lệ chưa đủ để kết luận nó tương thích với mọi bản Spring Boot.

Ví dụ: khi nâng từ một dự án Spring Boot 2 lên 3, ngoài BOM còn có chuyển đổi Java 17, Spring Framework 6 và namespace **jakarta.***; những thay đổi này không được giải quyết chỉ bằng việc đổi số phiên bản BOM.

## 4. Ma trận tương thích Spring Boot – Spring Cloud Azure

### 4.1. Ma trận theo *dòng phát hành* để định hướng

Bảng dưới đây là **bản đồ theo dòng chính**, dùng để định hướng khi học. Nó **không phải bảng chứng nhận cho mọi bản minor/patch** và không thay thế tài liệu tương thích chính thức của phiên bản đang được sử dụng.

| Dòng ứng dụng | Dòng Spring Cloud Azure thường tương ứng | Nền tảng Java/Spring cần kiểm tra | Cảnh báo khi chọn |
| --- | --- | --- | --- |
| **Spring Boot 2.x** (đặc biệt 2.5–2.7) | **Spring Cloud Azure 4.x** | Java và Spring Framework thuộc thế hệ Boot 2 | Dòng cũ; kiểm tra trạng thái hỗ trợ và nhu cầu nâng cấp |
| **Spring Boot 3.x** | **Spring Cloud Azure 5.x** | **Java 17+**, Spring Framework 6, Jakarta namespace | Kiểm tra **từng Boot minor** và bản vá Azure 5.x cụ thể |
| **Spring Boot 4.x** | **Spring Cloud Azure 6.x** | Kiểm tra baseline Java của Boot 4, Spring Framework 7 và Spring Cloud release train thích hợp | Không giả định mọi starter hoặc API ở dòng 5.x đã tương thích với Boot 4 |

Các số dòng ở trên giúp khoanh vùng khảo sát. Một tài liệu chính thức có thể ghi phạm vi chính xác như **từ Boot phiên bản A đến B**, loại trừ một số bản hoặc yêu cầu release Azure mới hơn. Khi đề bài yêu cầu “nâng lên Spring Boot 3.5.x” hay “4.x”, **phải tra lại bảng theo release chính xác**, không chỉ nhìn chữ 3.x hoặc 4.x.

Trạng thái hỗ trợ thay đổi theo thời gian. Bản phát hành đã từng tương thích không đồng nghĩa còn được vá lỗi bảo mật hoặc được vendor hỗ trợ tại thời điểm triển khai.

### 4.2. Cách tra một tổ hợp được hỗ trợ

Khi chọn một bộ phiên bản, hãy thực hiện tuần tự:

1. **Chốt phiên bản Spring Boot** dự định sử dụng theo nhu cầu ứng dụng và chính sách hỗ trợ.
2. Từ **tài liệu Spring Cloud Azure**, tìm trang tổng quan, hướng dẫn dependency management, release notes và **Spring Boot compatibility** của release Azure tương ứng.
3. Xác minh bản Spring Boot đó nằm trong **khoảng được ghi rõ** của bản Spring Cloud Azure cụ thể, không chỉ cùng major.
4. Nếu dự án dùng Spring Cloud release train riêng, đối chiếu **Spring Cloud compatibility** với bản Boot đó.
5. Kiểm tra **Java baseline**, Spring Data/Security/Integration/Stream nếu sử dụng.
6. Ghi lại **phiên bản cụ thể** vào file build, kiểm tra cây phụ thuộc và chạy ứng dụng/integration test.

**Nguồn nên tra trước khi khóa version:**

- Microsoft Learn, hướng dẫn Spring Cloud Azure: https://learn.microsoft.com/azure/developer/java/spring-framework/
- Kho mã Spring Cloud Azure, tài liệu/release notes: https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/spring
- Spring Boot: https://spring.io/projects/spring-boot
- Spring Cloud và tương thích release train: https://spring.io/projects/spring-cloud
- Azure SDK for Java BOM: https://learn.microsoft.com/azure/developer/java/sdk/get-started#manage-dependencies

Một hướng dẫn cũ có thể dùng tên group/artifact của thế hệ trước. Với Spring Cloud Azure hiện đại, ưu tiên artifact **com.azure.spring** và BOM **spring-cloud-azure-dependencies** đúng phiên bản.

### 4.3. Phiếu quyết định phiên bản cho một dự án

Trước khi mở pull request nâng cấp, có thể điền bảng:

| Quyết định | Giá trị cần ghi |
| --- | --- |
| Spring Boot | Phiên bản **major.minor.patch** cụ thể |
| Spring Cloud Azure | Phiên bản **major.minor.patch** cụ thể, từ bảng tương thích |
| Spring Cloud release train | Phiên bản được Spring Cloud xác nhận (nếu dự án cần) |
| JDK build và JDK runtime | Phiên bản tối thiểu và phiên bản thực tế trong CI/production |
| Công cụ build | Maven/Gradle version và plugin Spring Boot |
| Starter Azure | Danh sách starter thực sự dùng, ví dụ Blob và Service Bus |
| Azure SDK trực tiếp | Các artifact riêng và effective version tương ứng |
| Chứng cứ tương thích | URL tài liệu + ngày kiểm tra + kết quả dependency tree/test |

Lưu bảng quyết định cùng ghi chú nâng cấp giúp nhận diện chính xác nguyên nhân khi một ứng dụng chỉ lỗi sau thay đổi dependency.

## 5. Maven: quản lý BOM theo Spring Boot

### 5.1. Tích hợp qua Spring Boot parent

Nếu POM đã kế thừa **spring-boot-starter-parent**, Spring Boot BOM được quản lý từ parent. Bổ sung BOM Spring Cloud Azure trong **dependencyManagement**:

~~~xml
<properties>
    <!-- Thay bằng release Spring Cloud Azure được xác minh
         tương thích với bản Spring Boot của dự án. -->
    <spring-cloud-azure.version>REPLACE_WITH_VERIFIED_VERSION</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **trích đoạn POM**, không phải file Maven hoàn chỉnh. Dự án cần parent/dependency management Spring Boot, plugin build phù hợp và thay **REPLACE_WITH_VERIFIED_VERSION** bằng phiên bản thực tế. Phần **version** ở starter Blob được bỏ trống có chủ đích: BOM quản lý nó.

Nếu dự án **không dùng parent Spring Boot**, có thể import **org.springframework.boot:spring-boot-dependencies** bằng BOM trong dependencyManagement. Khi ấy phải quản lý riêng các build plugin; import BOM không kế thừa cấu hình plugin từ parent.

### 5.2. Khi dự án sử dụng thêm Spring Cloud release train

Một hệ thống có Spring Cloud Gateway, Config hoặc các thành phần Spring Cloud khác có thể cần import BOM **spring-cloud-dependencies** phù hợp. Ví dụ dạng trích đoạn:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Chỉ thêm Spring Cloud BOM khi dự án cần các module
             Spring Cloud tương ứng; chọn version theo Spring Boot. -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Hai property ở đây phải được khai báo bằng **phiên bản đã chọn**, không phải cùng một giá trị. Khi BOM có dependency trùng tọa độ, **thứ tự import và quản lý dependency ở POM cha/con có thể ảnh hưởng** đến phiên bản hiệu lực trong Maven. Hãy dựa trên effective POM và dependency tree, thay vì đoán từ thứ tự trong bản trích đoạn.

Maven thường ưu tiên dependency management trong POM hiện tại hơn quản lý kế thừa; trong các BOM import cùng cấp và cùng quản lý một artifact, **khai báo đầu tiên thắng** theo quy tắc import Maven. Vì vậy thêm BOM Azure SDK chỉ để “đảm bảo mới nhất” có thể vô tình tạo các version không tương thích với starter.

### 5.3. Spring Cloud Azure BOM so với Azure SDK BOM

Hai cấu hình tiêu biểu:

**Ứng dụng Spring Boot dùng Spring Cloud Azure starter**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**Ứng dụng Java dùng Azure SDK trực tiếp, không cần starter**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure</groupId>
            <artifactId>azure-sdk-bom</artifactId>
            <version>${azure-sdk-bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
    </dependency>
</dependencies>
~~~

Ở cấu hình thứ hai, **azure-sdk-bom.version** cũng phải được cung cấp giá trị đã được kiểm chứng. Không dùng hai khối trên như một yêu cầu phải import cả hai BOM trong cùng POM.

## 6. Gradle: platform và dependency management

Trong Gradle, **platform** là một cách nhập ràng buộc phiên bản từ BOM. Ví dụ dùng **Gradle Kotlin DSL** trong dự án đã cấu hình plugin Spring Boot tương thích:

~~~kotlin
// build.gradle.kts, phần minh họa dependency
val springCloudAzureVersion = providers
    .gradleProperty("springCloudAzureVersion")
    .get()

dependencies {
    implementation(
        platform(
            "com.azure.spring:spring-cloud-azure-dependencies:$springCloudAzureVersion"
        )
    )

    implementation("com.azure.spring:spring-cloud-azure-starter-storage-blob")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Khai báo giá trị trong **gradle.properties**:

~~~properties
# Thay giá trị bằng bản đã đối chiếu ma trận Spring Boot.
springCloudAzureVersion=REPLACE_WITH_VERIFIED_VERSION
~~~

Với các dự án dùng plugin **io.spring.dependency-management**, cũng có thể import Maven BOM thông qua khối **dependencyManagement**. Đó là **một cơ chế khác** với Gradle native platform: cần chọn cách quản lý nhất quán và kiểm tra kết quả resolution khi kết hợp.

Trong Gradle, **platform** đưa ra constraints; version resolution có thể còn chịu tác động từ dependency constraints khác hoặc phiên bản trực tiếp. **enforcedPlatform** ép chặt version và có thể ảnh hưởng dependency graph của bên tiêu thụ; chỉ áp dụng nếu hiểu rõ phạm vi ảnh hưởng, không dùng như cách mặc định để “sửa” mọi xung đột.

**Lưu ý:** import BOM của Spring Cloud Azure không tự chọn version plugin **org.springframework.boot**, version Gradle wrapper, Java toolchain hoặc mọi artifact trong hệ Spring. Các thành phần đó phải được cấu hình rõ ràng theo ma trận tương thích.

## 7. Kiểm tra phiên bản thực sự được chọn

Một file build trông hợp lý vẫn có thể kéo sai phiên bản qua dependency bắc cầu hoặc override riêng. Cần kiểm tra kết quả **effective**, đặc biệt sau khi thêm starter mới hoặc nâng BOM.

### Maven

~~~bash
# Xem cây phụ thuộc và vị trí các thư viện Azure.
mvn dependency:tree -Dincludes=com.azure.spring,com.azure

# Xem effective POM, bao gồm dependencyManagement kế thừa/import.
mvn help:effective-pom

# Kiểm tra project có dependency conflict mà Maven hiển thị.
mvn dependency:tree -Dverbose
~~~

Lệnh **dependency:tree** có thể xuất hiện nhiều artifact khác nhau; hãy kiểm tra tối thiểu **azure-core**, **azure-identity**, SDK của dịch vụ được dùng, cùng các starter **com.azure.spring**. Một số thông tin omitted/conflict phụ thuộc phiên bản Maven Dependency Plugin.

### Gradle

~~~bash
# Linux/macOS; trên Windows dùng gradlew.bat.
./gradlew dependencies --configuration runtimeClasspath

# Xem vì sao một phiên bản azure-core được chọn.
./gradlew dependencyInsight --dependency azure-core --configuration runtimeClasspath

# Có thể lặp lại với azure-identity và một starter cụ thể.
./gradlew dependencyInsight --dependency azure-identity --configuration runtimeClasspath
~~~

Đọc các mục “selected by rule”, “by constraint” hoặc dependency path để biết dependency nào đang quyết định version. Đối với lỗi xảy ra chỉ lúc chạy, nên kiểm tra **runtimeClasspath** chứ không chỉ compile classpath.

### Một checklist kiểm tra cụ thể

| Cần quan sát | Vì sao |
| --- | --- |
| Version thực tế của Spring Boot và Spring Framework | Xác định baseline và các API runtime |
| Version của từng **spring-cloud-azure-*** | Tránh lẫn hai dòng starter |
| Version **azure-core** và **azure-identity** | Là dependency nền được nhiều SDK chia sẻ |
| Version **azure-storage-blob**, **azure-messaging-***, **azure-cosmos** | Đảm bảo đúng API và chức năng nghiệp vụ |
| Dependency trùng và các override thủ công | Có thể che khuất phiên bản do BOM quản lý |
| JDK dùng để build, test và chạy | Tránh compile với Java mới rồi deploy lên runtime cũ |

## 8. Các lỗi tương thích điển hình và cách phân biệt

| Biểu hiện | Nghi vấn chính | Cách xác minh |
| --- | --- | --- |
| **NoSuchMethodError** hoặc **NoClassDefFoundError** sau nâng cấp | API giữa các phiên bản thư viện không phù hợp, phiên bản bị override | Xem stack trace và dependency tree, kiểm tra class/method thuộc jar nào |
| **ClassNotFoundException** khi khởi tạo Spring | Thiếu dependency hoặc khác hệ Spring Framework / Jakarta | Xem starter, Java namespace và ma trận Boot |
| **BeanCreationException** / lỗi auto-configuration | Cấu hình, dependency hoặc API auto-configuration không còn tương thích | Đọc nguyên nhân gốc (root cause), conditions report và release notes |
| **UnsupportedClassVersionError** | Runtime Java cũ hơn bytecode của thư viện/ứng dụng | Kiểm tra Java runtime, toolchain và baseline Boot |
| Build báo không tìm được version của starter | BOM chưa import, import sai group/artifact hoặc property version thiếu | Kiểm tra dependencyManagement hoặc Gradle platform |
| **401** / **403** khi gọi Azure | Token, RBAC, scope hoặc chính sách truy cập chưa đúng | Kiểm tra principal, role data-plane, audience, firewall; không vội đổi BOM |
| Timeout/kết nối Azure thất bại | DNS, firewall, proxy/private endpoint hoặc retry | Kiểm tra network path, SDK diagnostics và Azure metrics |

Thông báo lỗi là **đầu mối**, không phải chẩn đoán cuối. Chẳng hạn **NoSuchMethodError** có thể xuất hiện do một dependency override cụ thể, còn **403** thường liên quan xác thực/ủy quyền hoặc policy mạng hơn là phiên bản BOM.

**Ví dụ tình huống:** ứng dụng đang dùng Spring Boot 3.x và starter Azure dòng 5.x. Một lập trình viên cập nhật riêng **azure-core** lên phiên bản cao hơn mà không đối chiếu BOM. Build vẫn thành công nhưng lúc chạy phát sinh **NoSuchMethodError** từ SDK. Cách xử lý là tìm effective version và đường dẫn bắc cầu, bỏ override nếu không có lý do xác thực, sau đó chạy lại test; không chữa bằng cách thay ngẫu nhiên từng artifact.

## 9. Quy trình nâng cấp có kiểm chứng

Nên nâng cấp theo các bước có thể kiểm tra và rollback:

1. **Chụp trạng thái hiện tại:** Java/Boot/Cloud/Azure versions, dependency tree, các API Azure đang dùng, test kết nối và môi trường triển khai.
2. **Chọn mục tiêu:** tra compatibility matrix của Spring Cloud Azure, Spring Cloud và baseline JDK; ghi chính xác các patch version được hỗ trợ.
3. **Nâng từ điểm quản lý trung tâm:** sửa BOM và version Spring Boot ở vị trí thích hợp; hạn chế ép riêng version cho từng Azure SDK. Với nâng cấp major, đọc migration guide.
4. **Build và kiểm tra dependency graph:** phát hiện lẫn starter cũ/mới, conflict, dependency bị bỏ hoặc thay package.
5. **Kiểm thử cục bộ:** unit test nghiệp vụ, Spring context smoke test, cấu hình profile và khả năng tạo client.
6. **Kiểm thử với dịch vụ managed:** dùng môi trường Azure test với danh tính thật, RBAC thực tế, endpoint/private network, Blob/Service Bus/Cosmos/Key Vault tương ứng.
7. **Quan sát khi rollout:** metrics, latency, error rate, retry, message redelivery và log không chứa secret; chuẩn bị cách quay lại BOM/Boot version trước đó.

Không nên ghép một lần nâng major Spring Boot, major Spring Cloud Azure và tái thiết kế messaging vào cùng một thay đổi quá lớn nếu có thể tách các bước kiểm chứng.

### Thiết kế test phù hợp

- **Unit test:** giả lập adapter/repository client Azure; chứng minh logic nghiệp vụ không phụ thuộc live cloud.
- **Integration test cục bộ:** với Blob, **Azurite** hỗ trợ một phần API Storage nhưng không đại diện đầy đủ cho Microsoft Entra ID, RBAC, private networking và mọi behavior của Azure thật.
- **Integration test trên Azure:** xác minh credential, role tối thiểu, thao tác dữ liệu, timeout/retry, quota và cleanup test resource.

**Ma trận tương thích của thư viện không thay thế ma trận môi trường:** một tổ hợp version hợp lệ vẫn có thể thất bại khi workload identity chưa được cấu hình, service principal thiếu role, private DNS sai hoặc resource Azure chưa tồn tại.

## 10. So sánh quản lý dependency giữa ba cloud

| Nền tảng | SDK Java | Thư viện tích hợp Spring | Nguyên tắc quản lý phiên bản |
| --- | --- | --- | --- |
| **Azure** | Azure SDK for Java, **azure-sdk-bom** | Spring Cloud Azure, **spring-cloud-azure-dependencies** | Ưu tiên BOM Spring Cloud Azure khi dùng starter; đối chiếu ma trận Boot/Java |
| **AWS** | AWS SDK for Java v2 và BOM của SDK | Spring Cloud AWS và BOM của dòng tương ứng | Chọn release Spring Cloud AWS phù hợp Boot; kiểm tra đồng bộ AWS SDK |
| **Google Cloud** | Google Cloud Java client libraries và BOM thích hợp | Spring Cloud GCP và bộ quản lý dependency của dự án | Đối chiếu line Spring Cloud GCP với Boot, Google Cloud SDK và Java |

Cùng tên “BOM” không có nghĩa ba provider dùng chung cách phát hành hoặc tương thích hoàn toàn. Khi đổi provider cần xem lại **starter catalog**, credential chain, RBAC/IAM, retry semantics, tài nguyên storage/messaging, consistency và cách kiểm thử. Các thư viện Spring giảm mã wiring, nhưng không làm các dịch vụ managed trở nên tương đương về hành vi.

## 11. Bài thực hành: chọn đúng BOM, phát hiện xung đột

**Bối cảnh:** đội phát triển có ứng dụng Spring Boot 3.x ghi file vào Azure Blob Storage và gửi sự kiện qua Service Bus. Một nhánh tính năng đề xuất thêm SDK mới với phiên bản hard-code.

Thực hiện:

1. Xác định **Spring Boot phiên bản cụ thể**, JDK runtime và Spring Cloud Azure release có tài liệu xác nhận tương thích với bản Boot đó.
2. Khai báo duy nhất BOM **spring-cloud-azure-dependencies** trong dependency management, thêm hai starter tương ứng và không ghi version trên starter.
3. Chạy Maven dependency:tree hoặc Gradle dependencyInsight để ghi lại phiên bản **azure-core**, **azure-identity**, **azure-storage-blob** và **azure-messaging-servicebus** thực tế.
4. Trong một nhánh thực nghiệm, thêm override version cho một Azure SDK; quan sát dependency graph thay đổi như thế nào rồi bỏ override.
5. Viết smoke test tạo Spring context, tiếp theo thực hiện upload blob và gửi/nhận message trên tài nguyên test được cấp quyền phù hợp.
6. Ghi một trang quyết định nâng cấp: source compatibility, versions đã chọn, lý do loại bỏ override và bằng chứng test.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ import BOM mà không khai báo starter thì ứng dụng chưa có Blob client?
2. Một dự án Spring Boot dùng starter Azure có nên import thêm **azure-sdk-bom** theo mặc định? Điều gì cần kiểm tra khi có hai BOM?
3. Vì sao bản Spring Cloud Azure cùng major chưa đủ để khẳng định tương thích với một Spring Boot minor mới?
4. Trường hợp nào nên xem **dependencyInsight/dependency:tree**, trường hợp nào nên kiểm tra **Azure RBAC**?
5. Nâng Spring Boot 2 lên 3 có thể đòi hỏi thay đổi gì ngoài version BOM?

## 12. Ghi nhớ

- **BOM quản lý phiên bản**, còn dependency declaration quyết định thư viện nào được thêm. BOM không cấp quyền Azure và không bảo đảm runtime tương thích.
- Với ứng dụng Spring Boot sử dụng **Spring Cloud Azure starter**, bắt đầu từ **com.azure.spring:spring-cloud-azure-dependencies**. Với ứng dụng Java dùng SDK trực tiếp, cân nhắc **com.azure:azure-sdk-bom**.
- Ma trận theo dòng **Boot 2 ↔ Azure 4**, **Boot 3 ↔ Azure 5**, **Boot 4 ↔ Azure 6** chỉ giúp định hướng; luôn tra **bản minor/patch chính xác**, tài liệu release và baseline Java trước khi quyết định.
- Kiểm tra **effective dependency versions**, tránh override tùy tiện và xác nhận bằng build, test Spring context, integration test trên tài nguyên cloud thực tế.
- Phân biệt lỗi dependency với vấn đề **identity, RBAC, endpoint, DNS, network và dịch vụ Azure** để xử lý đúng nguyên nhân.
