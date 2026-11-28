# Quản lý phiên bản bằng Spring Cloud BOM trong Maven và Gradle

Một ứng dụng Spring Boot sử dụng Spring Cloud Config thường kéo theo nhiều thư viện Spring Cloud và các thư viện nền tảng liên quan. Nếu mỗi dependency tự khai báo một phiên bản, dự án có thể vô tình kết hợp những module được phát hành cho các thế hệ Spring Boot khác nhau. Lỗi tương thích đôi khi chỉ xuất hiện lúc khởi động, khi auto-configuration được nạp hoặc khi các API nội bộ không còn khớp nhau.

Spring Cloud cung cấp một BOM (Bill of Materials) có tên `spring-cloud-dependencies` để quản lý phiên bản của các module thuộc cùng một release train. Maven và Gradle có thể nhập BOM này để các dependency Spring Cloud dùng một tập phiên bản đã được phối hợp. Nhờ vậy, nhóm chỉ cần chọn release train tương thích với Spring Boot đang dùng và để công cụ build áp dụng các phiên bản thành phần tương ứng.

## 1. BOM giải quyết vấn đề gì?

BOM là một POM Maven có `packaging` là `pom`, chứa các quy tắc quản lý dependency. BOM thường khai báo phiên bản cho nhiều thư viện trong phần `dependencyManagement`. Khi một dự án nhập BOM, dự án có thể khai báo các dependency thuộc BOM mà không phải lặp lại phiên bản ở từng dòng.

Ví dụ, một dịch vụ có thể cần Config Client, service discovery và load balancing. Các module này có chu kỳ phát hành riêng, nhưng được phát hành theo một Spring Cloud release train. BOM mô tả bộ phiên bản được khuyến nghị cho release train đó.

Nếu không dùng BOM, cấu hình có thể trở nên rời rạc:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
        <version>...</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        <version>...</version>
    </dependency>
</dependencies>
```

Khi dùng BOM, dự án khai báo phiên bản release train một lần trong dependency management; các starter chỉ cần tọa độ dependency. BOM quản lý phiên bản, còn dependency trong `<dependencies>` mới đưa thư viện vào classpath. Chỉ nhập BOM không tự động thêm Config Client hoặc Config Server vào ứng dụng.

## 2. Chọn release train tương thích với Spring Boot

Spring Boot và Spring Cloud có ma trận tương thích giữa các dòng phát hành. Không nên chọn phiên bản Spring Cloud chỉ vì đó là phiên bản mới nhất hoặc vì nó biên dịch được trên máy cá nhân. Trước khi cập nhật, hãy xác định phiên bản Spring Boot của dự án, tra ma trận tương thích và chọn release train Spring Cloud được hỗ trợ cho phiên bản đó.

Các nguyên tắc lựa chọn:

- Dùng một release train Spring Cloud thống nhất cho các module trong cùng ứng dụng hoặc cùng hệ thống build.
- Chọn bản service release/patch được hỗ trợ trong release train đã chọn, theo khuyến nghị hiện hành của dự án Spring Cloud.
- Đọc ghi chú phát hành khi nâng release train vì có thể có thay đổi tương thích, dependency hoặc cấu hình.
- Tránh trộn starter từ nhiều release train, phiên bản milestone, snapshot và bản GA trong cùng classpath nếu không có một lý do thử nghiệm rõ ràng.
- Khi nâng Spring Boot, kiểm tra lại release train Spring Cloud tương thích; không mặc định BOM hiện tại vẫn phù hợp.

Spring Boot BOM và Spring Cloud BOM có phạm vi quản lý khác nhau. Spring Boot parent hoặc `spring-boot-dependencies` quản lý phiên bản Spring Boot và nhiều dependency nền tảng. `spring-cloud-dependencies` quản lý các module Spring Cloud cùng những dependency liên quan trong release train. Một dự án Spring Boot thường sử dụng cả hai: Boot parent/BOM cho nền tảng Boot và Cloud BOM cho hệ sinh thái Spring Cloud.

Không có một cặp phiên bản phù hợp cho mọi dự án. Phiên bản cụ thể cần được lấy từ ma trận tương thích và tài liệu phát hành tại thời điểm nâng cấp. Các ví dụ bên dưới dùng placeholder `SPRING_CLOUD_RELEASE_TRAIN_VERSION`; hãy thay bằng phiên bản release train đã được xác nhận trước khi build.

## 3. Nhập Spring Cloud BOM trong Maven

Với Maven, nhập BOM trong phần `<dependencyManagement>` bằng `type` là `pom` và `scope` là `import`:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>SPRING_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN_VERSION</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-config</artifactId>
        </dependency>
    </dependencies>
</project>
```

`SPRING_BOOT_VERSION` và `SPRING_CLOUD_RELEASE_TRAIN_VERSION` là placeholder trong ví dụ, không phải phiên bản Maven có thể tải xuống. Hãy thay chúng bằng các phiên bản cụ thể mà dự án đã chọn. Nếu dự án không dùng `spring-boot-starter-parent`, có thể nhập `spring-boot-dependencies` bằng BOM trong `dependencyManagement` và vẫn nhập Spring Cloud BOM theo cùng cách.

Sau khi BOM được nhập, Maven tra phiên bản của `spring-cloud-starter-config` trong dependency management. Vì thế dependency trong `<dependencies>` không cần phần `<version>`. Cách làm tương tự áp dụng cho các starter Spring Cloud khác thuộc release train.

### BOM không phải dependency runtime

Đặt BOM trong `<dependencyManagement>` với `scope=import` chỉ đưa các quy tắc quản lý phiên bản vào mô hình Maven. Nó không đưa các lớp của Config Client vào classpath. Muốn ứng dụng dùng Config Client, vẫn cần khai báo `spring-cloud-starter-config` trong `<dependencies>`. Ứng dụng Config Server cần khai báo dependency `spring-cloud-config-server` tương ứng.

### Khi dự án có nhiều module Maven

Với dự án multi-module, nên quản lý phiên bản release train ở parent POM hoặc một POM nền tảng dùng chung. Các module con kế thừa dependency management và chỉ khai báo starter mà module đó thực sự sử dụng. Điều này giúp tránh tình trạng module A dùng một patch release còn module B dùng một patch release khác.

Ví dụ parent POM có thể chứa `<properties>` và `<dependencyManagement>` như ở trên; các module con chỉ cần:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>
```

Không cần khai báo lại BOM trong từng module nếu module đã kế thừa parent có cấu hình đó. Nếu một module không kế thừa đúng parent hoặc nằm ngoài cây module, nó sẽ không tự nhận dependency management này.

## 4. Nhập Spring Cloud BOM trong Gradle

Gradle hỗ trợ Maven BOM thông qua dependency platform. Cách native này không đòi hỏi thêm plugin quản lý dependency riêng.

Ví dụ với Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
val springCloudVersion = providers.gradleProperty("springCloudVersion").get()

dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))

    implementation("org.springframework.cloud:spring-cloud-starter-config")
}
```

Đặt phiên bản trong `gradle.properties` ở root của dự án:

```properties
springCloudVersion=SPRING_CLOUD_RELEASE_TRAIN_VERSION
```

Với Gradle Groovy DSL (`build.gradle`), cú pháp tương ứng là:

```groovy
def springCloudVersion = providers.gradleProperty('springCloudVersion').get()

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")

    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Thay placeholder trong `gradle.properties` bằng release train tương thích. `platform(...)` nhập các constraint phiên bản từ BOM để Gradle tham gia giải quyết phiên bản dependency. Các dependency Spring Cloud được quản lý bởi platform có thể bỏ phiên bản riêng trong khai báo.

### Dùng dependency management plugin

Một số dự án Gradle hiện có plugin `io.spring.dependency-management`, thường được dùng cùng Spring Boot Gradle plugin. Khi dự án đã chuẩn hóa theo cách này, có thể nhập BOM bằng DSL của plugin:

```groovy
ext {
    set('springCloudVersion', 'SPRING_CLOUD_RELEASE_TRAIN_VERSION')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Không cần đồng thời áp dụng cả native platform và plugin dependency management cho cùng một BOM nếu không có mục tiêu rõ ràng. Hãy theo một cách quản lý nhất quán trong dự án để tránh khó hiểu khi Gradle giải quyết các constraint.

### `platform` và `enforcedPlatform`

Gradle `platform(...)` nhập các dependency constraint từ BOM. Nếu có nhiều constraint hoặc dependency khác tham gia giải quyết phiên bản, Gradle vẫn thực hiện quy tắc conflict resolution của nó.

`enforcedPlatform(...)` áp dụng phiên bản trong platform như các phiên bản bắt buộc và có thể ảnh hưởng đến dependency graph của các project phụ thuộc. Chỉ dùng khi nhóm thật sự muốn ép các phiên bản đó và hiểu tác động khi project được tiêu thụ như thư viện. Với ứng dụng thông thường, `platform(...)` thường là lựa chọn phù hợp hơn.

## 5. Khai báo Config Client và Config Server

Sau khi nhập BOM, mỗi module khai báo dependency theo vai trò của nó. Ví dụ Maven:

```xml
<dependencies>
    <!-- Ứng dụng lấy cấu hình từ Config Server -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>
```

Module triển khai Config Server dùng dependency server:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
```

Với Gradle, khai báo tương ứng là:

```kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-config-server")
}
```

Không thêm phiên bản riêng cho các artifact Spring Cloud nếu BOM đã quản lý chúng. Nếu một dependency không được BOM quản lý, cần xác định phiên bản theo tài liệu của chính dependency đó hoặc một BOM phù hợp khác; không tự suy ra phiên bản bằng cách sao chép số phiên bản release train.

## 6. Kiểm tra phiên bản thực tế mà build đang chọn

Việc import BOM thành công chưa đủ để khẳng định toàn bộ dependency graph đúng như mong muốn. Một dependency khai báo phiên bản tường minh, một BOM khác hoặc một rule resolution có thể làm kết quả khác với dự kiến. Sau khi thay đổi BOM, hãy kiểm tra mô hình và dependency graph.

### Maven

Xem dependency tree:

```bash
mvn dependency:tree
```

Lọc các dependency Spring Cloud:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

Xem POM hiệu lực để kiểm tra BOM và dependency management sau khi Maven hợp nhất parent, profile và cấu hình hiện hành:

```bash
mvn help:effective-pom
```

Nếu dependency có phiên bản không mong đợi, kiểm tra dependency tree để tìm đường dẫn kéo nó vào và kiểm tra POM hiệu lực để tìm khai báo management hoặc phiên bản tường minh. Đừng sửa bằng cách thêm một phiên bản tùy ý ở module con trước khi xác định nguồn xung đột.

### Gradle

Xem dependency graph của runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Kiểm tra lý do Gradle chọn phiên bản của một module cụ thể:

```bash
./gradlew dependencyInsight --dependency spring-cloud-starter-config --configuration runtimeClasspath
```

Trên Windows, có thể dùng `gradlew.bat` thay cho `./gradlew`. Tên configuration có thể khác tùy loại module và plugin; hãy chọn classpath phù hợp với ứng dụng cần kiểm tra.

Kết quả `dependencyInsight` giúp xác định constraint từ platform, phiên bản được yêu cầu trực tiếp và lý do Gradle nâng hoặc chọn một phiên bản. Đây là bước hữu ích khi nhiều BOM hoặc dependency transitive cùng tác động đến một artifact.

## 7. Các lỗi thường gặp khi quản lý BOM

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Maven báo thiếu version cho starter | BOM chưa được nhập đúng trong `dependencyManagement`, sai tọa độ hoặc property version chưa được đặt | Kiểm tra POM hiệu lực, vị trí BOM và giá trị property |
| Gradle không tìm thấy version cho dependency | Platform chưa được khai báo trong configuration phù hợp hoặc property phiên bản không có | Kiểm tra `platform(...)`, `gradle.properties` và dependency graph |
| Ứng dụng lỗi tương thích lúc khởi động | Spring Boot và Spring Cloud release train không nằm trong cặp tương thích | Tra ma trận tương thích, chọn lại release train và kiểm tra ghi chú phát hành |
| Một module dùng phiên bản khác dự kiến | Có version tường minh, BOM khác hoặc rule resolution can thiệp | Dùng `dependency:tree`, `effective-pom` hoặc `dependencyInsight` để tìm nguồn |
| Module con không nhận BOM | Module không kế thừa parent Maven hoặc không áp dụng platform trong Gradle | Đưa quản lý phiên bản về cấu hình gốc hoặc áp dụng platform đúng module |
| Nâng BOM làm xuất hiện lỗi biên dịch | Có thay đổi API hoặc dependency đi kèm release train mới | Đọc release notes, nâng mã tương thích và chạy kiểm thử liên quan |

Một lỗi dễ mắc là thêm phiên bản trực tiếp vào từng starter để làm build hết báo lỗi. Cách này có thể che khuất nguyên nhân BOM chưa được nhập hoặc phiên bản release train không phù hợp, đồng thời tạo ra một classpath khó tái lập. Hãy sửa nguồn quản lý phiên bản ở parent hoặc platform trước, rồi chỉ override riêng khi có lý do được ghi nhận.

## 8. Quy trình nâng phiên bản có kiểm soát

Khi cập nhật Spring Boot hoặc Spring Cloud, nên thực hiện theo một quy trình có thể review:

1. Ghi nhận phiên bản Spring Boot, Java và Spring Cloud release train hiện tại.
2. Tra ma trận tương thích và chọn release train được hỗ trợ cho phiên bản Boot mục tiêu.
3. Cập nhật một property tập trung trong parent POM hoặc `gradle.properties`/version catalog.
4. Kiểm tra dependency graph để phát hiện phiên bản bị override và dependency xung đột.
5. Đọc ghi chú phát hành của Spring Boot, Spring Cloud và các module được nâng.
6. Build toàn bộ module liên quan, chạy kiểm thử tự động và kiểm tra hành vi khởi động/kết nối Config Server.
7. Ghi lại phiên bản artifact đã được xác minh để các môi trường dùng cùng bộ dependency.

Trong dự án nhiều module, nên có một nơi duy nhất quản lý release train. Với Gradle, có thể tập trung property trong `gradle.properties` hoặc version catalog; với Maven, dùng property ở parent POM. Tránh để mỗi module tự đặt một số phiên bản Cloud riêng.

Nếu hệ thống cần tái lập build, có thể kết hợp BOM với dependency locking hoặc cơ chế lưu trữ kết quả build đã được kiểm chứng. BOM xác định bộ constraint được quản lý, còn dependency locking giúp ghi nhận phiên bản thực tế đã được giải quyết trong một lần build. Hai cơ chế phục vụ mục đích liên quan nhưng không thay thế nhau.

## 9. Nguyên tắc cần ghi nhớ

- Dùng `spring-cloud-dependencies` để đồng bộ phiên bản các module thuộc một Spring Cloud release train.
- Chọn release train dựa trên ma trận tương thích Spring Boot và Spring Cloud tại thời điểm nâng cấp.
- Với Maven, nhập BOM trong `<dependencyManagement>` bằng `type=pom` và `scope=import`.
- Với Gradle, dùng `platform(...)` hoặc cách quản lý BOM mà dự án đã chuẩn hóa.
- BOM quản lý phiên bản; vẫn phải khai báo starter cần dùng trong dependencies.
- Tránh phiên bản tường minh trên từng starter khi BOM đã quản lý, trừ khi override được chủ đích và kiểm chứng.
- Kiểm tra dependency tree và phiên bản được giải quyết sau mỗi lần nâng BOM.
- Quản lý release train tập trung trong dự án nhiều module để các dịch vụ build nhất quán.

Spring Cloud BOM giúp Maven và Gradle sử dụng một tập phiên bản Spring Cloud đã được phối hợp. Khi kết hợp BOM với ma trận tương thích Spring Boot, cấu hình dependency tập trung và kiểm tra dependency graph, nhóm có thể chuẩn bị môi trường build ổn định cho Config Server, Config Client và các thành phần Spring Cloud khác.
