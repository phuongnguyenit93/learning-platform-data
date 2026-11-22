# Google Cloud libraries BOM và quản lý phụ thuộc Java

Một ứng dụng Java trên Google Cloud thường sử dụng nhiều client library cùng lúc: Cloud Storage để lưu file, Pub/Sub để trao đổi sự kiện, Secret Manager để lấy cấu hình nhạy cảm, BigQuery để phân tích dữ liệu và Cloud Logging/Monitoring để quan sát hoạt động. Những thư viện này lại phụ thuộc vào gRPC, Protobuf, Guava, Google Auth Library, GAX và nhiều thành phần nền tảng. Nếu mỗi thư viện được chọn một phiên bản độc lập, ứng dụng có thể biên dịch thành công nhưng lỗi khi chạy do các JAR không tương thích.

**Google Cloud Libraries Bill of Materials (BOM)** giải quyết phần lớn vấn đề đồng bộ phiên bản của các thư viện Google Cloud Java. BOM cung cấp một tập phiên bản đã được phối hợp để dùng chung. Maven hoặc Gradle đọc BOM khi giải quyết phụ thuộc, từ đó ứng dụng chỉ cần khai báo những thư viện trực tiếp đang dùng mà không phải tự chọn từng phiên bản.

Bài học thuộc chương **Java và Spring trên GCP** của module CLOUD_PROVIDERS_GCP. Trong hành trình từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, triển khai và theo dõi độ tin cậy, quản lý phụ thuộc Java là một điều kiện cơ bản để xây dựng, phát hành và vận hành ứng dụng ổn định.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích BOM là gì và BOM khác gì so với dependency, plugin hoặc starter.
- Sử dụng `com.google.cloud:libraries-bom` trong Maven và Gradle.
- Phân biệt BOM của Google Cloud client libraries với BOM của Spring Boot, Spring Cloud và Spring Cloud GCP.
- Quản lý dependency trực tiếp, dependency bắc cầu (transitive dependency) và phạm vi phụ thuộc.
- Điều tra `NoSuchMethodError`, `NoClassDefFoundError`, xung đột Protobuf, gRPC hoặc Guava.
- Chọn cách cập nhật, kiểm tra và khóa phiên bản phù hợp với ứng dụng production.
- Áp dụng nguyên tắc này cho API Java/Spring dùng Cloud Storage, Pub/Sub hoặc Secret Manager.

## 1. Vì sao nhiều thư viện Google Cloud dễ xảy ra xung đột?

Xem một API Java cần đọc object từ Cloud Storage và xuất sự kiện qua Pub/Sub:

~~~text
orders-api
├── google-cloud-storage
│   ├── google-cloud-core
│   ├── google-auth-library
│   └── các thư viện HTTP / gRPC liên quan
└── google-cloud-pubsub
    ├── gax
    ├── grpc-java
    ├── protobuf-java
    └── google-auth-library
~~~

Đây là sơ đồ khái quát, không phải dependency tree cố định của một release cụ thể. Những thành phần thực tế phụ thuộc vào phiên bản và cấu hình build.

Giả sử một thư viện gọi phương thức mới của Protobuf, nhưng classpath khi chạy lại chứa Protobuf cũ. Java có thể ném:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Một trường hợp khác là class mà thư viện đã được biên dịch dựa vào không có trong JAR đang được nạp:

~~~text
java.lang.NoClassDefFoundError: ...
~~~

Các lỗi này thường xuất phát từ **dependency resolution**: Maven hoặc Gradle chọn một phiên bản cuối cùng cho cùng một tọa độ dependency, trong khi các thư viện khác được phát hành với kỳ vọng về API hoặc ABI khác.

Một tình huống dễ gặp là:

1. Ứng dụng dùng phiên bản Cloud Storage mới nhưng Pub/Sub cũ.
2. Framework hoặc một thư viện khác kéo theo phiên bản Guava/gRPC/Protobuf riêng.
3. Build tool chọn phiên bản cuối cùng dựa vào quy tắc giải quyết dependency.
4. Một class bị thiếu hoặc chữ ký method không tương thích ở runtime.

BOM làm giảm rủi ro bằng cách cung cấp tập phiên bản mà nhà phát hành đã phối hợp. Tuy vậy, BOM không bảo đảm mọi thư viện bên thứ ba, mọi plugin hoặc mọi runtime ngoài ứng dụng đều tương thích.

## 2. BOM là gì và BOM làm được những gì?

**Bill of Materials** trong hệ sinh thái Maven là một POM chuyên quản lý phiên bản dependency. Nó chứa các khai báo `dependencyManagement` cho nhiều artifact. Ứng dụng nhập (import) BOM để sử dụng những phiên bản được quản lý đó.

Ví dụ BOM xác định phiên bản của:

- `com.google.cloud:google-cloud-storage`
- `com.google.cloud:google-cloud-pubsub`
- `com.google.cloud:google-cloud-secretmanager`
- Các thành phần nền tảng như gRPC, Protobuf, Guava, GAX và Google Auth Library

Khi ứng dụng khai báo `google-cloud-storage` mà không ghi `version`, Maven sử dụng phiên bản do BOM quản lý. Với Gradle, `platform` đưa các ràng buộc phiên bản của BOM vào quá trình giải quyết dependency.

| Khái niệm | Chức năng | Có tự thêm thư viện vào ứng dụng? |
|---|---|---|
| BOM | Quản lý tập phiên bản dependency | Không |
| Dependency trực tiếp | Thư viện ứng dụng sử dụng trực tiếp | Có |
| Transitive dependency | Thư viện mà dependency khác cần | Được kéo vào theo đồ thị phụ thuộc |
| Maven parent POM | Kế thừa cấu hình build, plugin và/hoặc dependency management | Không nhất thiết |
| Spring Boot starter | Bộ dependency phục vụ một khả năng như web, actuator hoặc storage | Có |
| Maven/Gradle plugin | Thực thi công việc build, test, đóng gói, deploy | Không giống dependency runtime |

BOM **không tự động thêm** Cloud Storage, Pub/Sub hoặc Secret Manager. BOM cũng không tự động cấp IAM, tạo project, bật API, thiết lập Application Default Credentials hay thay thế kiểm thử.

### BOM cần được đặt ở đúng vị trí

Với Maven, import BOM trong `dependencyManagement`, sau đó khai báo thư viện trong `dependencies`. Hai khu vực này có vai trò khác nhau.

Với Gradle, thêm `platform(...)` vào khối `dependencies`, sau đó thêm `implementation(...)` cho thư viện sử dụng. Nếu chỉ thêm platform mà không thêm dependency cụ thể, ứng dụng không có client library mới trong classpath.

## 3. Google Cloud Libraries BOM bao gồm gì?

Artifact chính thức:

~~~text
groupId:    com.google.cloud
artifactId: libraries-bom
type:       pom
~~~

BOM này chủ yếu quản lý hai nhóm:

1. **Google Cloud Java client libraries** như Cloud Storage, BigQuery, Pub/Sub hoặc Secret Manager.
2. **Thư viện nền tảng** được các client library sử dụng, ví dụ gRPC, Protobuf, Guava, GAX, Google Auth Library và các thư viện HTTP liên quan.

Các client library được phát hành độc lập, vì vậy các phiên bản riêng của chúng có thể khác nhau. Phiên bản BOM, ví dụ `26.90.0`, **không có nghĩa** mỗi client library phải mang phiên bản `26.90.0`.

Chú ý: tập artifact được BOM quản lý thay đổi giữa các release. Không nên đoán rằng một thư viện Java bất kỳ có tên bắt đầu bằng `google` đều đã nằm trong BOM. Hãy kiểm tra bảng artifact của release hoặc effective dependency tree.

### Khi nào nên dùng BOM này?

- Ứng dụng Java thuần sử dụng nhiều Google Cloud client libraries.
- API Spring Boot gọi trực tiếp các SDK Google Cloud.
- Module thư viện cần nhất quán các thành phần gRPC/Protobuf.
- Dự án có nhiều module nhưng muốn quản lý phiên bản Google Cloud tập trung.
- Nhóm cần quy trình nâng cấp phiên bản lặp lại được qua CI.

Có thể dùng BOM ngay cả khi ứng dụng chỉ phụ thuộc vào một Google Cloud client library. Điều này tạo đường nâng cấp nhất quán khi sau đó bổ sung dịch vụ khác.

### Phiên bản nên chọn

Các ví dụ dưới đây sử dụng **`26.90.0`**, phiên bản đang xuất hiện trong trang hướng dẫn BOM của Google Cloud khi biên soạn bài. Đây là **mốc minh họa**, không phải cam kết đó là phiên bản mới nhất trong tương lai. Khi tạo dự án, xác nhận bản phát hành được hỗ trợ và release notes tại:

- https://cloud.google.com/java/docs/bom
- https://github.com/googleapis/java-cloud-bom/releases

Giữ phiên bản BOM cố định trong mã nguồn; nâng cấp qua pull request có kiểm thử, thay vì tự động lấy phiên bản mới nhất mỗi lần build.

## 4. Thực hành Maven: một API Java dùng Storage và Pub/Sub

Đây là ví dụ đơn giản sử dụng Java 17, Maven và hai client library Google Cloud.

### Khai báo BOM trong pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example.gcp</groupId>
    <artifactId>orders-api</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.google.cloud</groupId>
                <artifactId>libraries-bom</artifactId>
                <version>26.90.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>google-cloud-storage</artifactId>
        </dependency>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>google-cloud-pubsub</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Điểm cần đọc trong cấu hình:

- `type=pom` và `scope=import` cho Maven biết đây là BOM được nhập để quản lý phiên bản.
- `dependencyManagement` chọn phiên bản nhưng không tự đưa JAR vào classpath.
- Hai dependency trực tiếp nằm trong `dependencies` và **không ghi phiên bản**.
- `maven.compiler.release` xác định mức Java source/bytecode muốn tạo, không thay thế việc kiểm tra JDK tối thiểu của các thư viện.
- Không đưa BOM vào `dependencies` với mục đích sử dụng như một JAR runtime.

### Thêm dịch vụ mới

Khi ứng dụng cần Secret Manager, thêm:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-secretmanager</artifactId>
</dependency>
~~~

Nếu artifact đó được release BOM quản lý, Maven sẽ cấp phiên bản tương ứng. Không cần copy phiên bản từ trang của một SDK riêng rồi cố gắng đồng bộ thủ công với các SDK còn lại.

### Kiểm tra Maven đã chọn phiên bản gì

Trong thư mục dự án, dùng:

~~~bash
mvn dependency:tree
~~~

Để tập trung vào các nhóm thường xung đột:

~~~bash
mvn dependency:tree -Dincludes=com.google.cloud,com.google.protobuf,io.grpc,com.google.guava
~~~

Để xem POM hiệu lực sau khi Maven xử lý parent và dependency management:

~~~bash
mvn help:effective-pom
~~~

Output có thể dài; khi điều tra một artifact, tìm artifact đó trong dependency tree và phần managed dependencies của effective POM. Không kết luận BOM có hiệu lực chỉ vì `pom.xml` chứa dòng import: một phiên bản trực tiếp hoặc BOM khác vẫn có thể tác động tới kết quả cuối.

### Tác dụng của dependencyManagement

Giả sử trước đây nhóm viết:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
    <version>VERSION_TU_CHON</version>
</dependency>
~~~

Sau khi nhập BOM, xóa dòng `version` của dependency này. Một phiên bản được khai báo trực tiếp thường có quyền ưu tiên đối với chính dependency đó, làm mất lợi ích của việc để BOM quản lý nhất quán.

## 5. Thực hành Gradle Groovy DSL

Với Gradle hỗ trợ BOM, sử dụng `platform` trong khối dependency.

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('com.google.cloud:libraries-bom:26.90.0')

    implementation 'com.google.cloud:google-cloud-storage'
    implementation 'com.google.cloud:google-cloud-pubsub'
    implementation 'com.google.cloud:google-cloud-secretmanager'
}
~~~

Dòng `platform(...)` đưa constraints của BOM vào cấu hình `implementation`. Các dependency trực tiếp không ghi phiên bản nếu đã được BOM quản lý.

### Kotlin DSL

Cấu hình tương đương trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(platform("com.google.cloud:libraries-bom:26.90.0"))

    implementation("com.google.cloud:google-cloud-storage")
    implementation("com.google.cloud:google-cloud-pubsub")
    implementation("com.google.cloud:google-cloud-secretmanager")
}
~~~

### platform và enforcedPlatform

Gradle hỗ trợ hai chế độ quan trọng:

| Chế độ | Ý nghĩa | Khi nào dùng |
|---|---|---|
| `platform` | Đưa constraints từ BOM vào giải quyết dependency; vẫn xét các ràng buộc khác | Lựa chọn mặc định cho ứng dụng |
| `enforcedPlatform` | Ép dùng phiên bản trong BOM, có thể ghi đè lựa chọn từ dependency khác | Chỉ cân nhắc khi đã hiểu toàn bộ xung đột |

Không dùng `enforcedPlatform` làm giải pháp đầu tiên cho `NoSuchMethodError`. Cách ép phiên bản này có thể phá vỡ một thư viện khác và còn được truyền tới các consumer khi cấu hình được công bố từ library. Hãy xem dependency tree và tìm nguyên nhân trước.

### Xem dependency graph trong Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Điều tra riêng Protobuf:

~~~bash
./gradlew dependencyInsight --dependency protobuf-java --configuration runtimeClasspath
~~~

Điều tra gRPC hoặc Guava:

~~~bash
./gradlew dependencyInsight --dependency grpc-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency guava --configuration runtimeClasspath
~~~

Trên Windows, có thể dùng `gradlew.bat` thay cho `./gradlew`. Kết quả dependencyInsight cho biết vì sao Gradle chọn một phiên bản, kể cả khi có nhiều nơi đưa ra constraint khác nhau.

## 6. Maven và Gradle giải quyết xung đột ra sao?

Hai build tool có mô hình khác nhau, vì vậy cùng một BOM chưa chắc cho ra classpath giống hệt nhau khi có nhiều framework hoặc thư viện bên ngoài.

### Maven

Maven sử dụng dependency mediation. Đối với dependency bắc cầu, quy tắc độ gần (nearest definition) có vai trò quyết định khi nhiều đường trong dependency tree yêu cầu những phiên bản khác nhau. `dependencyManagement` quản lý phiên bản cho các dependency tương ứng. Dependency trực tiếp khai báo `version` có thể ghi đè quản lý từ BOM.

Khi cùng import nhiều BOM trong một `dependencyManagement`, thứ tự khai báo có thể quyết định phiên bản của artifact trùng nhau: khai báo được nhập trước thường có ưu tiên đối với cùng artifact, nếu không có cấu hình khác ưu tiên hơn. Nếu sử dụng parent POM, quản lý phiên bản kế thừa cũng có thể ảnh hưởng đến kết quả.

Do đó, với Maven cần đọc **effective POM** và **dependency tree**, thay vì suy luận theo thứ tự file nhìn thấy mà không kiểm chứng.

### Gradle

Gradle giải quyết dependency theo graph và các ràng buộc phiên bản. `platform` cung cấp constraint, nhưng các dependency khác có thể đề xuất hoặc yêu cầu phiên bản cao hơn. `enforcedPlatform` cưỡng chế phiên bản và có hậu quả lớn hơn.

Để xây dựng có khả năng tái lập:

- Commit Gradle Wrapper.
- Cố định phiên bản platform và plugin.
- Cân nhắc dependency locking và dependency verification theo chính sách dự án.
- Kiểm tra dependencyInsight trong CI khi cần giải thích sự thay đổi phiên bản.

### Ba lỗi suy luận thường gặp

1. **“BOM đã import nên mọi JAR chắc chắn tương thích.”** Không đúng khi có thư viện ngoài phạm vi, dependency override hoặc runtime cung cấp JAR khác.
2. **“Thêm BOM sẽ tự có Cloud Storage client.”** Không đúng: phải thêm `google-cloud-storage` vào dependency.
3. **“BOM là phiên bản của tất cả thư viện.”** Không đúng: BOM có phiên bản riêng và quản lý các artifact với các phiên bản riêng.

## 7. Spring Boot: ba nhóm BOM cần phân biệt

Trong ứng dụng Spring, có thể xuất hiện ba hoặc bốn BOM khác nhau:

| BOM | Tọa độ Maven | Phạm vi |
|---|---|---|
| Spring Boot | `org.springframework.boot:spring-boot-dependencies` | Thư viện và dependency nền tảng của Spring Boot |
| Spring Cloud | `org.springframework.cloud:spring-cloud-dependencies` | Các module Spring Cloud theo release train |
| Spring Cloud GCP | `com.google.cloud:spring-cloud-gcp-dependencies` | Starter và module tích hợp Spring với Google Cloud |
| Google Cloud Libraries | `com.google.cloud:libraries-bom` | Các client library GCP và thư viện nền tảng Google |

**Spring Cloud GCP BOM và Google Cloud Libraries BOM không phải cùng một artifact.** Một bên quản lý starter/integration framework; bên kia quản lý các client SDK và core dependency.

### Kiểm tra tương thích Spring trước khi chọn BOM

Dòng Spring Cloud GCP phải phù hợp với Spring Boot và Spring Framework. Theo bảng tương thích được công bố trong repository Spring Cloud GCP:

- Spring Cloud GCP **8.x** dành cho Spring Boot **4.0.x/4.1.x** và Spring Cloud **2025.1.x**.
- Spring Cloud GCP **7.x** dành cho Spring Boot **3.5.x** và Spring Cloud **2025.0.x**.
- Spring Cloud GCP **6.x** dành cho Spring Boot **3.4.x** và Spring Cloud **2024.0.x**.

Đây là ánh xạ **major/minor**, không khẳng định bất kỳ patch release nào cũng tương thích với mọi dependency riêng của ứng dụng. Khi nâng cấp, đọc bảng chính thức, release notes và kiểm thử tại: https://github.com/GoogleCloudPlatform/spring-cloud-gcp

### Mẫu Maven cho Spring Boot + Spring Cloud GCP

Ví dụ sau tập trung vào BOM. Hai giá trị `SPRING_BOOT_VERSION` và `SPRING_CLOUD_GCP_VERSION` là placeholder: phải thay bằng cặp phát hành tương thích trước khi build.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>SPRING_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>example.gcp</groupId>
    <artifactId>orders-spring-api</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.google.cloud</groupId>
                <artifactId>spring-cloud-gcp-dependencies</artifactId>
                <version>SPRING_CLOUD_GCP_VERSION</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-starter-storage</artifactId>
        </dependency>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot parent quản lý nhiều thư viện nền tảng và plugin. Spring Cloud GCP BOM quản lý các starter tương ứng. Kiểm tra dependency tree của bản tương thích thay vì thêm một bản Google Cloud Libraries BOM khác theo thói quen.

Nếu API dùng trực tiếp `com.google.cloud:google-cloud-storage` ngoài các starter, hãy kiểm tra phiên bản SDK được Spring Cloud GCP/BOM hiện tại quản lý. Chỉ import thêm `libraries-bom` khi có nhu cầu cụ thể và đã phân tích tác động tới các dependency khác.

### Khi kết hợp nhiều BOM

Nhập nhiều BOM có thể tạo xung đột phiên bản ở các nhóm dùng chung như gRPC, Protobuf, Guava, Spring hoặc Netty. Quy trình an toàn:

1. Chọn Spring Boot và Spring Cloud GCP theo compatibility matrix.
2. Kiểm tra BOM nào đang quản lý từng artifact.
3. Thêm Google Cloud Libraries BOM nếu cần đồng bộ các SDK mà cấu hình hiện tại chưa giải quyết đúng.
4. Dùng `mvn help:effective-pom` và `mvn dependency:tree` để xem phiên bản thực sự.
5. Chạy integration tests với các dịch vụ GCP đang dùng.
6. Chỉ override một dependency có lý do cụ thể, có test chứng minh và có kế hoạch bỏ override.

Với Gradle, cần kiểm tra tương tác giữa `platform(...)`, Spring Boot plugin và plugin dependency-management nếu dự án sử dụng. Không sao chép nguyên cấu hình Maven sang Gradle và giả định thứ tự ưu tiên giống nhau.

## 8. Dùng client library trong mã Java

Khi BOM và dependency đã sẵn sàng, ứng dụng có thể tạo client theo cách thông thường. Ví dụ kiểm tra sự tồn tại của object trong Cloud Storage:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class StorageExample {
    public static boolean objectExists(String bucket, String objectName) {
        Storage storage = StorageOptions.getDefaultInstance().getService();
        Blob blob = storage.get(BlobId.of(bucket, objectName));
        return blob != null;
    }
}
~~~

`StorageOptions.getDefaultInstance()` thường sử dụng **Application Default Credentials (ADC)**. Đây là cơ chế xác thực riêng, không phải tính năng của BOM.

Trong môi trường phát triển:

~~~bash
gcloud auth application-default login
~~~

Trên Cloud Run, dùng service account của service. Trên GKE, ưu tiên Workload Identity Federation for GKE hoặc phương án nhận diện workload được hỗ trợ. Cấp quyền tối thiểu cho danh tính workload, ví dụ quyền đọc object ở bucket cần thiết; không commit JSON key của service account vào repository.

Ví dụ này minh họa sự liên hệ giữa dependency và runtime: BOM giúp chọn thư viện tương thích, nhưng quyền IAM, API enablement, network và credential quyết định API call có thành công hay không.

## 9. Quản lý dependency trong dự án nhiều module

Giả sử repository có cấu trúc:

~~~text
java-cloud-system/
├── pom.xml                (parent)
├── common-model/
│   └── pom.xml
├── order-service/
│   └── pom.xml
└── billing-worker/
    └── pom.xml
~~~

Để tránh mỗi module chọn một BOM khác nhau, parent POM có thể import một Google Cloud Libraries BOM. Các child module kế thừa `dependencyManagement` và khai báo dependency trực tiếp của chúng, không cần lặp lại phiên bản.

Ví dụ phần quan trọng trong parent POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>libraries-bom</artifactId>
            <version>26.90.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong module `order-service`:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-storage</artifactId>
    </dependency>
</dependencies>
~~~

Không thêm mọi client library vào parent `dependencies` nếu chỉ một số module sử dụng. Làm vậy có thể đưa các thư viện không cần thiết vào classpath của tất cả module. Đặt quản lý phiên bản ở parent, còn dependency thực tế ở module sử dụng.

Với Gradle multi-project, có thể tạo convention plugin hoặc một platform thống nhất, sau đó áp dụng cho các module cần GCP SDK. Chọn một đầu mối cập nhật BOM; tránh sao chép nhiều version string có nguy cơ lệch nhau.

## 10. Điều tra lỗi dependency trong thực tế

### Lỗi NoSuchMethodError hoặc NoClassDefFoundError

Triệu chứng thường gặp:

~~~text
java.lang.NoSuchMethodError: io.grpc....
java.lang.NoClassDefFoundError: com/google/protobuf/....
~~~

Quy trình điều tra:

1. Ghi lại stack trace đầy đủ và class/method thiếu.
2. Xác định lỗi xảy ra ở test, local JVM, Docker hay runtime trên Cloud Run/GKE.
3. Xem dependency tree của cấu hình **runtime**.
4. Kiểm tra có nhiều nguồn quản lý phiên bản hoặc dependency direct pin không.
5. Xem release notes BOM và các thay đổi lớn như Protobuf 4.x.
6. Nâng cấp BOM/framework hoặc loại bỏ override theo một nhánh kiểm thử riêng.
7. Chạy lại unit test, integration test và smoke test.
8. Kiểm tra JAR được đóng gói thực tế trong image hoặc artifact phát hành.

Nếu ứng dụng chỉ lỗi trên Hadoop, Spark hoặc một máy chủ Java riêng, có thể classpath runtime chứa Guava, Netty hoặc Protobuf do nền tảng đó cung cấp. BOM của ứng dụng không tự loại bỏ các JAR được runtime khác đưa vào.

### Lỗi xung đột Protobuf 3.x và 4.x

Các release Google Cloud Libraries BOM đã có thay đổi liên quan Protobuf 4.x. Nếu ứng dụng hoặc thư viện bên thứ ba vẫn dựa vào API cũ, việc nâng BOM có thể làm lộ lỗi liên kết.

Hãy đọc release notes của version BOM đang nâng cấp và xác định các thư viện phụ thuộc Protobuf. Không nên ngay lập tức ép `protobuf-java` về phiên bản cũ trong khi giữ các thư viện Google Cloud mới: điều đó có thể giải quyết một lỗi nhưng sinh lỗi khác.

### Lỗi Guava -jre và -android

Guava có các biến thể artifact như `-jre` và `-android` trong hệ sinh thái Maven. Nếu mã Java sử dụng method chỉ xuất hiện trong biến thể JRE, cần xem phiên bản Guava thực tế được resolve và các dependency constraints.

Không áp dụng một override Guava trên mọi dự án chỉ vì tài liệu cũ từng nêu ví dụ `-android`. BOM hiện hành đã thay đổi theo các release. Trước khi chỉnh, kiểm tra dependency tree và release notes tương ứng.

### Build thành công nhưng production vẫn lỗi

Cần kiểm tra:

- JDK runtime có đúng major version với bytecode đã build không.
- Docker image có dùng dependency/JAR mới nhất của build không.
- Có JAR cũ trong application server hoặc classpath ngoài không.
- Có xung đột `spring-boot-loader`, shading hoặc assembly không.
- CI có cache artifact cũ hoặc chạy nhầm image tag không.
- Các API được bật và ADC/IAM có chính xác không; lỗi `PERMISSION_DENIED` thường là lỗi quyền, không phải lỗi BOM.

## 11. Công cụ kiểm tra và chính sách CI

Quản lý dependency cần cả kiểm tra trước build lẫn kiểm tra runtime.

| Công cụ | Câu hỏi trả lời |
|---|---|
| `mvn dependency:tree` | Thư viện nào kéo phiên bản bắc cầu? |
| `mvn help:effective-pom` | Maven đang quản lý phiên bản nào sau khi kế thừa/import? |
| `./gradlew dependencies` | Đồ thị dependency của một configuration là gì? |
| `./gradlew dependencyInsight` | Vì sao Gradle chọn phiên bản này? |
| Maven Enforcer | Có vi phạm quy tắc build như upper bound hoặc dependency convergence không? |
| Linkage Checker | Có tham chiếu class/method không thể liên kết ở bytecode hay không? |
| SCA/dependency scanning | Có cảnh báo lỗ hổng hoặc giấy phép cần xử lý không? |
| Unit/integration/smoke tests | Ứng dụng có hoạt động với các JAR đã resolve không? |

Google cung cấp **Linkage Checker Enforcer Rule** để phát hiện một số lỗi linkage trong build. Đây là lớp kiểm tra hữu ích với hệ sinh thái gRPC, Protobuf và Guava; nó không thay thế kiểm thử integration.

Các bước CI gợi ý:

~~~text
Pull request
    |
    v
Dependency resolution
    |
    v
Dependency/tree & policy checks
    |
    v
Compile + unit tests
    |
    v
Linkage/security checks
    |
    v
Integration tests (test project)
    |
    v
Package container / artifact
    |
    v
Smoke test in staging
    |
    v
Review + deploy
~~~

Không cần bắt buộc mọi project nhỏ có đầy đủ công cụ ngay từ ngày đầu. Tối thiểu, hãy có một phiên bản BOM được kiểm soát, dependency tree có thể tái hiện, test chức năng quan trọng và kiểm tra bảo mật khi cập nhật.

## 12. Chiến lược nâng cấp BOM an toàn

Khi thấy một release BOM mới, không nên đổi tất cả phiên bản một cách thiếu kiểm soát.

1. **Kiểm tra release notes:** xác định thay đổi lớn của gRPC, Protobuf, Guava, Google Auth Library và các client library đang dùng.
2. **Xác định phạm vi:** liệt kê ứng dụng/module import BOM và những framework khác có BOM riêng.
3. **Nâng một version BOM:** tạo pull request riêng; tránh đồng thời đổi JDK, Spring Boot, Docker base image nếu không cần thiết.
4. **Kiểm tra dependency tree trước và sau:** lưu ý các artifact bị nâng major/minor.
5. **Chạy build và test:** bao gồm unit test, integration test cho Storage, Pub/Sub hoặc dịch vụ thực sự dùng.
6. **Kiểm tra security advisory:** BOM tương thích không có nghĩa tất cả dependency đều miễn nhiễm lỗ hổng.
7. **Thử trên staging:** chạy smoke test và quan sát lỗi runtime, latency, memory, startup.
8. **Phát hành theo từng bước:** dùng canary hoặc progressive rollout khi hệ thống có yêu cầu độ tin cậy cao.
9. **Giữ phương án rollback:** commit trước đó và image tag đã được xác minh.
10. **Cập nhật tài liệu:** ghi version BOM, lý do nâng, thay đổi đáng chú ý và kết quả kiểm thử.

Với Spring Boot, luôn ưu tiên **bảng tương thích của Spring Cloud GCP**. Nếu một release Google Cloud Libraries BOM mới gây xung đột với framework đang dùng, chưa chắc đó là lỗi của client library. Có thể cần nâng đồng bộ release train hoặc chờ phiên bản integration được hỗ trợ.

## 13. Tình huống thực hành: thêm Secret Manager vào Spring API

**Bối cảnh:** nhóm vận hành một API Spring Boot trên Cloud Run. Ứng dụng đang dùng Spring Cloud GCP Storage starter và cần đọc một bí mật từ Secret Manager. Một lập trình viên muốn copy phiên bản mới nhất của `google-cloud-secretmanager` vào `pom.xml`.

Hướng xử lý:

1. Kiểm tra Spring Boot và Spring Cloud GCP version đang dùng có tương thích không.
2. Xem effective POM để biết Secret Manager client đã được BOM nào quản lý.
3. Nếu dùng starter Spring Cloud GCP tương ứng, ưu tiên starter và cơ chế quản lý phiên bản của Spring Cloud GCP BOM.
4. Nếu cần client SDK trực tiếp, khai báo artifact cần dùng và để BOM phù hợp quản lý phiên bản.
5. Chạy dependency tree để xem các phiên bản Guava, Protobuf, gRPC.
6. Dùng ADC/service identity của Cloud Run; cấp IAM Secret Manager Secret Accessor trên secret cụ thể.
7. Kiểm thử đọc secret trong test project, không in giá trị secret ra log.
8. Đưa thay đổi qua CI và kiểm tra startup sau khi deploy staging.

**Câu hỏi đánh giá:** nếu runtime báo `NoClassDefFoundError` sau khi thêm Secret Manager thì có nên thêm phiên bản Protobuf thủ công không?

**Hướng giải quyết:** trước hết xem classpath thực tế và dependency tree, kiểm tra BOM đang quản lý gì, có override hoặc plugin đóng gói nào đưa JAR cũ vào hay không. Chỉ thay đổi phiên bản theo bằng chứng, kèm test chứng minh đã sửa lỗi. Đừng sửa bằng cách thêm một JAR ngẫu nhiên.

## 14. Checklist trước khi đưa ứng dụng vào production

- [ ] Java/JDK và phiên bản client libraries đáp ứng yêu cầu hỗ trợ của ứng dụng.
- [ ] Dự án import BOM Google Cloud hoặc BOM tích hợp framework phù hợp.
- [ ] Các client library trực tiếp không được pin version tùy tiện nếu BOM đã quản lý.
- [ ] Maven/Gradle dependency tree đã được kiểm tra.
- [ ] Với Spring Boot, đã xác nhận bảng tương thích Spring Cloud GCP.
- [ ] Không có override Guava, gRPC, Protobuf hoặc Netty thiếu lý do rõ ràng.
- [ ] CI có build và unit/integration test cho các dịch vụ GCP sử dụng.
- [ ] Có kiểm tra lỗ hổng dependency theo chính sách tổ chức.
- [ ] Image/artifact runtime chứa đúng JAR và JDK đã kiểm thử.
- [ ] ADC và IAM của workload được cấu hình độc lập với BOM.
- [ ] Mỗi lần nâng BOM có release notes, thử nghiệm và kế hoạch rollback.
- [ ] Không commit credential, private key hoặc secret vào source code.

## Câu hỏi ôn tập

1. Vì sao ứng dụng có thể gặp `NoSuchMethodError` dù Maven compile thành công?
2. Điều gì xảy ra nếu thêm BOM vào `dependencyManagement` nhưng không khai báo `google-cloud-storage` trong `dependencies`?
3. Khác biệt giữa `platform` và `enforcedPlatform` trong Gradle là gì?
4. Vì sao không nên tự động dùng bản Spring Cloud GCP mới nhất với một Spring Boot cũ?
5. Một dependency bị quản lý bởi hai BOM: nên dùng lệnh nào để biết Maven đã chọn phiên bản nào?
6. BOM có giải quyết lỗi `PERMISSION_DENIED` khi Cloud Run gọi Secret Manager không? Vì sao?

## Kết luận

Google Cloud Libraries BOM giúp ứng dụng Java sử dụng một tập phiên bản Google Cloud client libraries và thư viện nền tảng đã được phối hợp. Cách dùng chính là import `com.google.cloud:libraries-bom` trong Maven `dependencyManagement` hoặc dùng Gradle `platform`, rồi khai báo các client library trực tiếp mà không tự gán phiên bản.

Trong Spring Boot, cần phân biệt BOM của Spring Boot, Spring Cloud, Spring Cloud GCP và Google Cloud Libraries. Bảng tương thích framework và dependency tree thực tế quyết định cách kết hợp. BOM giảm xung đột nhưng không thay thế việc xem classpath, kiểm thử runtime, quét bảo mật, quản lý ADC/IAM hay quy trình phát hành có rollback.

Khi quản lý dependency theo một đầu mối, kiểm chứng trước mỗi nâng cấp và giới hạn override, đội phát triển có thể bổ sung dịch vụ GCP vào ứng dụng Java mà vẫn giữ quá trình build và vận hành có thể dự đoán.

## Tài liệu tham khảo

- [Google Cloud: Use Bill of Materials (BOM) with Cloud Client Libraries for Java](https://cloud.google.com/java/docs/bom)
- [Google Cloud: Set up a Java development environment](https://cloud.google.com/java/docs/setup)
- [Google Cloud: Troubleshoot Cloud Client Libraries for Java](https://cloud.google.com/java/docs/troubleshooting)
- [Google Cloud Libraries BOM repository và release notes](https://github.com/googleapis/java-cloud-bom)
- [Spring Cloud GCP project](https://spring.io/projects/spring-cloud-gcp/)
- [Spring Framework on Google Cloud: Compatibility và BOM](https://github.com/GoogleCloudPlatform/spring-cloud-gcp)
- [Spring Cloud release train](https://spring.io/projects/spring-cloud/)
- [Maven dependency mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle: Importing Maven BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Cloud Open Source Java: Linkage Checker](https://github.com/GoogleCloudPlatform/cloud-opensource-java)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)

