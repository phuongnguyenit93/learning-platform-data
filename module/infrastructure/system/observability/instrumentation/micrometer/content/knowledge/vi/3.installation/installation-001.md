# Chọn phiên bản Micrometer tương thích với JDK và framework

## Mục tiêu

Khi thêm Micrometer vào một ứng dụng Java, câu hỏi đầu tiên thường là nên dùng phiên bản Micrometer nào. Chọn phiên bản mới nhất theo số phiên bản chưa đủ để bảo đảm ứng dụng chạy được. Phiên bản đó còn phải phù hợp với JDK dùng để biên dịch và chạy ứng dụng, framework đang sử dụng, các thư viện tích hợp và registry xuất metrics.

Quyết định này có ảnh hưởng trực tiếp đến khả năng biên dịch, khởi động, tự cấu hình và nâng cấp về sau. Một phiên bản Micrometer có thể chạy độc lập trên một JDK nhất định nhưng vẫn không tương thích với bộ thư viện mà framework đang quản lý. Vì vậy, hãy kiểm tra toàn bộ dependency graph trước khi thêm hoặc nâng cấp dependency.

Sau bài này, bạn có thể:

- Xác định JDK tối thiểu của ứng dụng và của các module Micrometer cần dùng.
- Chọn phiên bản Micrometer theo phiên bản Spring Boot hoặc framework đang chạy.
- Dùng BOM để đồng bộ phiên bản core, registry và test module.
- Khai báo dependency bằng Maven hoặc Gradle.
- Kiểm tra phiên bản thực tế được resolve và xác minh ứng dụng sau khi nâng cấp.

## Ba lớp tương thích cần kiểm tra

Việc chọn phiên bản nên đi theo thứ tự sau:

1. **JDK của ứng dụng:** xác định phiên bản Java thấp nhất mà môi trường build, môi trường chạy và image triển khai phải hỗ trợ.
2. **Framework và nền tảng:** xác định phiên bản Spring Boot, Spring Framework hoặc framework khác; đọc yêu cầu JDK và bộ dependency được framework kiểm thử.
3. **Micrometer và registry:** chọn dòng Micrometer tương thích với framework, sau đó dùng đúng module registry cho backend metrics.

Micrometer core là thư viện Java tương đối độc lập với framework. Phần lớn artifact Micrometer hoạt động với Java 8 trở lên, nhưng một số artifact bổ sung có yêu cầu cao hơn, chẳng hạn module dành riêng cho Java 11 hoặc Jetty 11. Khi ứng dụng dùng Spring Boot, yêu cầu JDK của Spring Boot thường cao hơn yêu cầu cơ bản của Micrometer và trở thành giới hạn cần tuân thủ.

Ngoài JDK, hãy kiểm tra cả các thành phần liên quan:

- Phiên bản Spring Framework và Spring Boot.
- Phiên bản Kotlin hoặc Groovy nếu dự án sử dụng các ngôn ngữ này.
- Servlet container hoặc web server nếu có module tích hợp tương ứng.
- Phiên bản client của hệ thống giám sát và giao thức export.
- Các thư viện khác đang dùng chung Micrometer như Spring Integration, Reactor hoặc Hibernate.

Không nên xem hai dependency cùng biên dịch được là đủ tương thích. Chúng còn phải phối hợp được ở runtime và nằm trong các dòng phiên bản được nhà cung cấp hỗ trợ.

## Kiểm tra yêu cầu JDK

### Phân biệt JDK build và JDK runtime

Một dự án có thể được biên dịch trên JDK mới nhưng triển khai trên JRE hoặc JDK cũ hơn. Trong trường hợp đó, phiên bản Java của compiler không chứng minh rằng mọi dependency đều chạy được trên runtime.

Hãy kiểm tra ít nhất ba nơi:

- JDK chạy Maven hoặc Gradle trên máy phát triển và CI.
- Java toolchain hoặc cấu hình source/target/release của dự án.
- JDK có trong container image hoặc máy chủ triển khai.

Các lệnh sau giúp xác định môi trường hiện tại:

~~~bash
java -version
./mvnw -version
./gradlew --version
~~~

Trên Windows, có thể dùng các wrapper tương ứng:

~~~powershell
java -version
.\mvnw.cmd -version
.\gradlew.bat --version
~~~

Lệnh wrapper cho biết phiên bản Java mà Maven hoặc Gradle đang dùng. Cấu hình toolchain và runtime triển khai vẫn cần được kiểm tra riêng.

Ví dụ, dự án có thể khai báo Java toolchain 17 trong Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Toolchain giúp thống nhất compiler được dùng khi build. Nó không tự nâng JDK trong container production. Image triển khai vẫn phải chứa JDK/JRE đủ mới để nạp được bytecode của ứng dụng và các dependency.

### Yêu cầu JDK của Spring Boot

Spring Boot quy định baseline JDK cho toàn ứng dụng. Các con số sau là ví dụ từ các bản phát hành ổn định được công bố tại thời điểm tháng 11 năm 2026:

| Nền tảng | JDK tối thiểu | Dải JDK được công bố tương thích | Spring Framework tối thiểu |
|---|---:|---:|---|
| Spring Boot 3.5.16 | 17 | đến Java 25 | 6.2.19 |
| Spring Boot 4.2.0 | 17 | đến Java 27 | 7.1.0 |

Đây là yêu cầu của từng bản Spring Boot, không phải ma trận tương thích riêng của Micrometer. Một bản Spring Boot mới có thể hỗ trợ JDK mới hơn mà không có nghĩa mọi ứng dụng cũ đã sẵn sàng nâng cấp. Hãy kiểm tra phiên bản cụ thể mà dự án đang dùng trong tài liệu System Requirements của Spring Boot.

### Yêu cầu riêng của module Micrometer

Micrometer được chia thành nhiều artifact. Module core chứa API instrumentation và các loại meter phổ biến. Các module tích hợp bổ sung có thể sử dụng API hoặc lớp của JDK, web server hay framework cụ thể.

Ví dụ:

- micrometer-core cung cấp API metrics chung.
- micrometer-registry-prometheus cung cấp registry xuất metrics theo định dạng Prometheus.
- micrometer-test cung cấp tiện ích kiểm thử.
- micrometer-java11 hoặc micrometer-jetty11 là các module có yêu cầu JDK hoặc nền tảng riêng.
- micrometer-java21 bổ sung instrumentation dành cho các khả năng của Java 21, ví dụ quan sát virtual threads trong tích hợp phù hợp.

Khi chọn module có tên gắn với phiên bản JDK, hãy kiểm tra đúng tài liệu của artifact đó. Không suy ra rằng mọi module trong Micrometer đều có cùng baseline Java với micrometer-core.

## Chọn phiên bản theo framework

### Khi dùng Spring Boot

Spring Boot cung cấp một bộ dependency đã được chọn và kiểm thử cùng nhau thông qua BOM spring-boot-dependencies. Bộ này quản lý phiên bản Micrometer và các thư viện liên quan. Nếu dự án đã dùng Spring Boot dependency management, hãy để Spring Boot chọn phiên bản Micrometer.

Hai ví dụ dưới đây cho thấy phiên bản Micrometer được quản lý theo dòng Spring Boot tại thời điểm tháng 11 năm 2026:

| Spring Boot | Phiên bản Micrometer do BOM quản lý | Ghi chú |
|---|---:|---|
| 3.5.16 | 1.15.12 | Dòng Spring Boot 3.5, yêu cầu Java 17 trở lên |
| 4.2.0 | 1.18.0 | Dòng Spring Boot 4.2, yêu cầu Java 17 trở lên |

Các phiên bản trong bảng là ví dụ tham chiếu theo bản phát hành được nêu, không phải quy tắc cố định cho mọi bản vá của Spring Boot. Khi nâng cấp Spring Boot, hãy xem lại managed dependency coordinates của đúng phiên bản mới.

Một lợi ích quan trọng của BOM là các module Micrometer được giữ đồng bộ. Nếu registry Prometheus được khai báo mà không có version, Spring Boot sẽ chọn phiên bản phù hợp với bộ dependency của mình.

### Spring Boot 3.x

Với Spring Boot 3.x, Actuator cung cấp tích hợp và auto-configuration cho Micrometer. Ví dụ dưới đây thêm Actuator và registry Prometheus. Phiên bản của các dependency được Spring Boot quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Với Gradle Kotlin DSL, nếu dự án đã áp dụng Spring Boot plugin và cấu hình dependency management tương ứng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Không cần gắn một phiên bản Micrometer riêng vào từng dependency. Khi dùng Spring Boot parent hoặc BOM, hãy để dependency management cung cấp version.

### Spring Boot 4.x

Spring Boot 4 có cấu trúc module và starter được tách rõ hơn. Starter Micrometer Metrics có tên spring-boot-starter-micrometer-metrics. Với ứng dụng cần Actuator endpoint và Micrometer metrics, có thể khai báo các dependency sau:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-micrometer-metrics</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-micrometer-metrics")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Các dependency trên phải dùng cùng phiên bản Spring Boot BOM. Không tự gán version cho registry nếu BOM đã quản lý nó. Khi dùng một starter cấp cao hơn đã kéo Micrometer Metrics vào dependency graph, tránh khai báo trùng lặp không cần thiết; hãy kiểm tra dependency tree để biết thành phần nào đã được đưa vào.

### Khi không dùng Spring Boot

Với ứng dụng Java thuần hoặc ứng dụng dùng Spring Framework mà không dùng Spring Boot dependency management, có thể nhập Micrometer BOM để đồng bộ các artifact Micrometer.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation(platform("io.micrometer:micrometer-bom:1.18.0"))
    implementation("io.micrometer:micrometer-core")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    testImplementation("io.micrometer:micrometer-test")
}
~~~

Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-bom</artifactId>
            <version>1.18.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-core</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Phiên bản 1.18.0 trong ví dụ là phiên bản minh họa cho một bộ Micrometer BOM ở thời điểm bài viết được cập nhật. Khi bắt đầu dự án mới, hãy kiểm tra trang phát hành và chính sách hỗ trợ để chọn bản vá mới nhất còn được hỗ trợ, đồng thời xác nhận JDK của tất cả module cần dùng.

Nếu framework khác đã cung cấp BOM hoặc extension riêng cho Micrometer, hãy ưu tiên bộ dependency mà framework đó hỗ trợ. Chỉ nhập Micrometer BOM trực tiếp khi không có một dependency management phù hợp hơn.

## BOM và quản lý phiên bản

### BOM giải quyết vấn đề gì?

Micrometer có nhiều artifact được phát hành cùng một dòng phiên bản, chẳng hạn:

- micrometer-core.
- micrometer-commons.
- micrometer-observation.
- micrometer-registry-prometheus hoặc registry cho backend khác.
- micrometer-test.

Nếu mỗi artifact được gán một version độc lập, dự án có thể vô tình trộn các module từ những dòng phát hành khác nhau. Khi API nội bộ hoặc hành vi tích hợp thay đổi, việc trộn phiên bản có thể gây lỗi biên dịch hoặc lỗi runtime.

BOM (Bill of Materials) khai báo phiên bản được khuyến nghị cho một nhóm dependency. Sau khi import BOM, các dependency thuộc nhóm đó có thể được khai báo mà không cần lặp lại version.

Hãy chỉ dùng một nguồn quản lý phiên bản chính cho cùng một nhóm dependency:

| Loại dự án | Nguồn quản lý nên ưu tiên |
|---|---|
| Spring Boot có parent/BOM | Spring Boot dependency management |
| Spring Framework không dùng Boot | Micrometer BOM hoặc BOM nền tảng của tổ chức |
| Java thuần | Micrometer BOM |
| Framework khác có extension metrics | BOM/extension chính thức của framework |

Không nên vừa để Spring Boot BOM quản lý Micrometer, vừa import một Micrometer BOM khác mà không có lý do và kiểm tra rõ thứ tự ưu tiên. Hai BOM có thể đưa ra các version khác nhau; kết quả cuối cùng phụ thuộc quy tắc resolution của Maven hoặc Gradle.

### Không chỉ nâng riêng micrometer-core

Một lỗi thường gặp là nâng micrometer-core lên bản mới nhưng để micrometer-registry-prometheus hoặc micrometer-test ở bản cũ. Điều này làm dependency graph không đồng nhất.

Nếu cần ghi đè version do framework quản lý:

1. Xác định lỗi hoặc tính năng cụ thể cần giải quyết.
2. Kiểm tra phiên bản Micrometer được framework hỗ trợ.
3. Đọc release notes và compatibility notes của Micrometer.
4. Kiểm tra các artifact Micrometer liên quan có thể nâng cùng nhau hay không.
5. Chạy kiểm thử biên dịch, unit test, integration test và kiểm tra export.
6. Ghi lại lý do override để lần nâng cấp framework sau có thể đánh giá lại.

Không dùng một version override chỉ vì nó có số lớn hơn. Phiên bản mới có thể thay đổi API, module hoặc hành vi mà framework chưa tích hợp và kiểm thử.

## Xem chính sách hỗ trợ của Micrometer

Tương thích kỹ thuật và được hỗ trợ là hai tiêu chí khác nhau. Một dòng phiên bản cũ có thể vẫn chạy được nhưng đã hết thời hạn nhận bản sửa lỗi cộng đồng.

Trang chính sách hỗ trợ Micrometer công bố thời điểm phát hành và thời điểm kết thúc hỗ trợ cho từng dòng. Tại thời điểm tháng 11 năm 2026, thông tin được công bố gồm:

| Dòng Micrometer | Bắt đầu phát hành | Kết thúc OSS support |
|---|---|---|
| 1.18.x | 2026-11 | 2027-12 |
| 1.17.x | 2026-06 | 2027-07 |
| 1.16.x | 2025-11 | 2026-12 |
| 1.15.x | 2025-05 | 2026-06 |

OSS support là thời gian cộng đồng cung cấp các bản sửa lỗi và cập nhật bảo mật. Một số dòng có thể tiếp tục được hỗ trợ theo hợp đồng doanh nghiệp sau khi kết thúc OSS support. Hãy đọc chính sách hiện hành thay vì chỉ nhìn số phiên bản.

Ví dụ, Spring Boot 3.5.16 quản lý Micrometer 1.15.12. Theo lịch hỗ trợ Micrometer, dòng 1.15.x đã qua mốc kết thúc OSS support vào tháng 6 năm 2026, dù có thể còn chương trình hỗ trợ doanh nghiệp mở rộng. Nếu yêu cầu vận hành bắt buộc phải dùng dòng Micrometer còn OSS support, nhóm cần đánh giá lộ trình framework, chính sách hỗ trợ doanh nghiệp và compatibility trước khi thay đổi BOM.

Đối với production:

- Ưu tiên bản stable và bản vá mới nhất trong dòng được hỗ trợ.
- Tránh dùng SNAPSHOT, milestone hoặc release candidate làm dependency production nếu không có quy trình thử nghiệm riêng.
- Kiểm tra advisory bảo mật và release notes trước mỗi lần nâng cấp.
- Ghi nhận thời điểm kết thúc hỗ trợ của dependency quan trọng trong kế hoạch nâng cấp.

## Kiểm tra dependency đã được resolve

Khai báo trong build file chỉ mô tả yêu cầu. Maven hoặc Gradle mới là nơi quyết định phiên bản thực tế sau khi áp dụng BOM, dependency constraints và các dependency bắc cầu.

### Maven

Xem tất cả dependency Micrometer trong cây dependency:

~~~bash
./mvnw dependency:tree -Dincludes=io.micrometer
~~~

Nếu dùng Windows:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=io.micrometer
~~~

Có thể xuất effective POM để kiểm tra dependency management sau khi Maven áp dụng parent và các BOM:

~~~bash
./mvnw help:effective-pom
~~~

Trong kết quả, kiểm tra các artifact như micrometer-core, micrometer-commons, micrometer-observation và registry đang dùng có cùng dòng phiên bản hay không.

### Gradle

Xem dependency tree của runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do Gradle chọn một version cụ thể:

~~~bash
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
~~~

Lệnh dependencyInsight đặc biệt hữu ích khi một dependency bắc cầu yêu cầu phiên bản khác với phiên bản do BOM cung cấp. Kết quả cho biết đường dependency và quy tắc resolution dẫn đến version cuối cùng.

### Đọc kết quả

Giả sử dependency tree hiển thị:

~~~text
io.micrometer:micrometer-core:1.18.0
io.micrometer:micrometer-commons:1.18.0
io.micrometer:micrometer-observation:1.18.0
io.micrometer:micrometer-registry-prometheus:1.18.0
~~~

Đây là dấu hiệu các module chính đang dùng cùng một dòng. Nếu kết quả có cả 1.15.x và 1.18.x, hãy tìm dependency kéo phiên bản cũ vào, sau đó xác định cách xử lý ở BOM hoặc dependency constraints. Không loại trừ module một cách tùy tiện vì dependency bắc cầu có thể được một thư viện khác sử dụng.

## Quy trình chọn phiên bản trong một dự án mới

Hãy thực hiện theo trình tự:

1. **Chốt JDK production.** Xác định JDK nhỏ nhất mà ứng dụng phải chạy trên máy chủ hoặc container.
2. **Chọn framework.** Kiểm tra phiên bản framework còn được hỗ trợ và yêu cầu JDK tương ứng.
3. **Xác định dependency management.** Kiểm tra framework có BOM hoặc extension quản lý Micrometer hay không.
4. **Chọn registry.** Chọn đúng artifact cho Prometheus, OTLP, Datadog, Graphite hoặc backend đang sử dụng.
5. **Chọn dòng hỗ trợ.** Đối chiếu support policy và release notes của Micrometer.
6. **Để BOM quản lý version.** Không tự gán version riêng cho từng module nếu BOM đã quản lý.
7. **Kiểm tra dependency graph.** Dùng dependency:tree hoặc dependencyInsight để xác nhận kết quả resolve.
8. **Kiểm thử trên runtime mục tiêu.** Build, chạy test và khởi động ứng dụng bằng JDK tương ứng với production.

Một ví dụ quyết định:

| Bối cảnh | Cách chọn |
|---|---|
| Ứng dụng Spring Boot 3.5 đang chạy Java 17 | Giữ phiên bản Micrometer mà BOM của đúng bản Boot quản lý; đánh giá riêng tình trạng hỗ trợ của dòng đó |
| Ứng dụng Spring Boot 4.2 chạy Java 21 | Dùng BOM Spring Boot 4.2; thêm starter Micrometer Metrics và registry tương ứng |
| Ứng dụng Java thuần chạy Java 17 | Dùng Micrometer BOM cho dòng stable được hỗ trợ, sau khi xác nhận từng artifact tương thích với JDK 17 |
| Ứng dụng framework khác | Ưu tiên BOM hoặc extension chính thức của framework; chỉ tự quản lý Micrometer khi framework không cung cấp |

## Nâng cấp Micrometer an toàn

Nâng cấp Micrometer độc lập với framework có thể hữu ích khi cần bản vá bảo mật hoặc một tính năng mới. Tuy nhiên, thay đổi này tác động đến toàn bộ nhóm artifact liên quan và có thể làm thay đổi cách registry xuất dữ liệu.

Trước khi nâng cấp:

- Đọc release notes giữa version hiện tại và version đích.
- Kiểm tra các API đã deprecated hoặc bị loại bỏ.
- Kiểm tra thay đổi trong registry đang dùng, đặc biệt là định dạng metrics, tên metric và label.
- Kiểm tra yêu cầu JDK của module mới.
- Xác định các thư viện khác đang dùng chung Micrometer.

Sau khi nâng cấp:

- Chạy compile và toàn bộ unit test liên quan đến instrumentation.
- Chạy integration test để kiểm tra auto-configuration và endpoint export.
- Kiểm tra dependency tree để chắc chắn các artifact đã đồng bộ.
- Khởi động ứng dụng bằng đúng JDK của production.
- So sánh tên metric, tag, unit và histogram trước/sau nếu dashboard hoặc alert phụ thuộc vào chúng.

Nếu nâng cấp framework và Micrometer cùng lúc, hãy tách thay đổi theo từng bước khi có thể. Điều đó giúp xác định lỗi phát sinh từ framework, JDK hay registry dễ hơn.

## Những lỗi tương thích thường gặp

**Chọn Micrometer mới nhất cho một framework cũ.** Framework có thể chưa được kiểm thử với API hoặc module mới. Hãy bắt đầu từ BOM của framework.

**Chỉ kiểm tra JDK biên dịch.** Bytecode có thể được tạo trên JDK mới nhưng không chạy được trên runtime cũ. Kiểm tra Java toolchain và container image.

**Gán version riêng cho từng registry.** Registry có thể lệch dòng với micrometer-core. Hãy dùng BOM để đồng bộ.

**Import nhiều BOM có version xung đột.** Kết quả resolution có thể khác dự định. Xác định một nguồn quản lý version chính và kiểm tra dependency tree.

**Dùng artifact của module tích hợp không phù hợp.** Một module cho Jetty, Jakarta hoặc JDK cụ thể có thể có yêu cầu riêng. Kiểm tra tài liệu của đúng artifact.

**Bỏ qua support policy.** Phiên bản có thể còn chạy nhưng đã hết nhận bản sửa lỗi cộng đồng. Đối chiếu lịch hỗ trợ trước khi chọn cho production.

**Dùng bản preview trong production.** Milestone, release candidate và snapshot phục vụ thử nghiệm. Chỉ sử dụng trong production khi tổ chức có quy trình chấp nhận rủi ro rõ ràng.

## Tài liệu tham khảo

- [Micrometer - Installing](https://docs.micrometer.io/micrometer/reference/installing.html): cách thêm Micrometer BOM và registry dependency.
- [Micrometer - Support](https://micrometer.io/support/): lịch hỗ trợ của các dòng Micrometer.
- [Micrometer GitHub](https://github.com/micrometer-metrics/micrometer): yêu cầu Java của các artifact và thông tin phát hành.
- [Spring Boot 3.5 - System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): baseline JDK và Spring Framework của Boot 3.5.
- [Spring Boot 4.2 - System Requirements](https://docs.spring.io/spring-boot/4.2/system-requirements.html): baseline JDK và Spring Framework của Boot 4.2.
- [Spring Boot 3.5 - Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): phiên bản dependency do BOM Boot 3.5 quản lý.
- [Spring Boot 4.2 - Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.2/appendix/dependency-versions/coordinates.html): phiên bản dependency do BOM Boot 4.2 quản lý.
- [Spring Boot 4.2 - Metrics](https://docs.spring.io/spring-boot/4.2/reference/actuator/metrics.html): tích hợp Micrometer và registry.

## Kết luận

Để chọn phiên bản Micrometer, trước hết hãy xác định JDK production, sau đó xác định framework và BOM đang quản lý dependency. Với Spring Boot, ưu tiên phiên bản Micrometer do đúng dòng Spring Boot cung cấp; với ứng dụng độc lập, dùng Micrometer BOM để đồng bộ core, registry và test module. Cuối cùng, kiểm tra support policy, dependency graph và chạy ứng dụng trên đúng runtime mục tiêu. Quy trình này giúp chọn được bộ phiên bản tương thích, có thể kiểm chứng và thuận tiện bảo trì.
