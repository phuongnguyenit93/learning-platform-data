# Kiểm tra bộ phiên bản Spring Boot, Micrometer và thư viện xuất dữ liệu

Một ứng dụng có thể biên dịch thành công nhưng khi khởi động lại gặp lỗi thiếu lớp hoặc thiếu phương thức ở phần số đo. Có trường hợp ứng dụng vẫn chạy, nhưng thư viện xuất dữ liệu dùng khác nhánh so với mã mẫu. Muốn xử lý đúng, cần kiểm tra cả bộ dependency thay vì chỉ nhìn một dòng phiên bản.

Bài học hướng dẫn xác định **bộ phiên bản được quản lý**, **bộ phiên bản được công cụ build chọn** và **các thư viện thực sự được nạp khi chạy**. Ví dụ dùng Spring Boot 3.3.5 để tái lập; các con số trong ví dụ không phải đề nghị nâng hoặc hạ mọi dự án về phiên bản đó.

## 1. Những thành phần nào cần được phân biệt?

Trong một ứng dụng dùng Actuator và Prometheus, đường đi rút gọn của số đo là:

```text
Spring Boot + Actuator
       │ tích hợp và cấu hình
       ▼
Micrometer Core / Observation
       │ ghi nhận số đo
       ▼
Micrometer registry cho hệ thống đích
       │ dùng thư viện khách / định dạng tương ứng
       ▼
Đầu ra hoặc đường gửi dữ liệu
       │
       ▼
Hệ thống giám sát bên ngoài
```

| Thành phần | Vai trò khi kiểm tra phiên bản |
| --- | --- |
| Spring Boot | Cung cấp nền tích hợp và bộ dependency được quản lý |
| Micrometer Core | API và cơ chế ghi nhận số đo |
| Micrometer Observation | Cơ chế mô tả thao tác quan sát, khi ứng dụng sử dụng |
| Micrometer registry | Tích hợp số đo với một hệ thống đích |
| Thư viện khách bên dưới registry | Thành phần registry dùng để tạo hoặc xuất dữ liệu |
| Máy chủ giám sát bên ngoài | Hệ thống nhận/thu thập dữ liệu, có vòng đời phiên bản riêng |

Spring Boot Actuator tích hợp Micrometer và các registry tương ứng. Có registry trên runtime classpath là một phần của việc cấu hình, còn việc gửi/thu thập dữ liệu cần thiết lập đúng cho hệ thống đích. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 1.1. Các số phiên bản không phải bằng nhau

Ví dụ, `micrometer-registry-prometheus` thuộc nhóm artifact của Micrometer, trong khi `prometheus-metrics-core` thuộc Prometheus Java Client. Hai thư viện có thể cùng tham gia đường xuất số đo nhưng dùng hệ đánh số phiên bản khác nhau.

Tương tự, Micrometer Tracing là một nhóm thành phần riêng. Không lấy số phiên bản của `micrometer-core` rồi gán nguyên sang mọi artifact có tên bắt đầu bằng `micrometer`.

Một bộ phiên bản nhất quán nghĩa là các thành phần phù hợp với cơ chế quản lý dependency và yêu cầu tích hợp đã chọn. Nó không có nghĩa tất cả chuỗi phiên bản phải giống nhau.

### 1.2. Máy chủ Prometheus không phải Prometheus Java Client

JAR phía ứng dụng giúp tạo dữ liệu để Prometheus thu thập. Máy chủ Prometheus ở ngoài ứng dụng có nhiệm vụ riêng. Không suy ra rằng phiên bản máy chủ phải bằng phiên bản JAR Java Client.

Khi xem lỗi, luôn ghi đầy đủ tên thành phần. Câu “Prometheus đang là 1.2.1” chưa rõ đang nói đến thư viện Java, registry hay máy chủ.

## 2. Ba mức bằng chứng cần đối chiếu

| Mức | Câu hỏi | Nguồn bằng chứng |
| --- | --- | --- |
| Được quản lý | Nền Spring Boot này đưa ra bộ phiên bản nào? | BOM, bảng dependency đúng phiên bản |
| Được giải quyết | Build của ứng dụng cuối cùng chọn phiên bản nào? | Dependency graph, lý do chọn phiên bản |
| Được nạp khi chạy | Tiến trình hiện tại đang dùng JAR nào? | Nơi nạp lớp, artifact triển khai và runtime classpath |

**BOM (Bill of Materials)** là bảng quản lý phiên bản dependency. Nó giúp các khai báo có thể bỏ phiên bản riêng, nhưng việc nhập BOM không tự thêm tất cả thư viện trong bảng vào ứng dụng.

**Dependency trực tiếp** do dự án khai báo; **dependency chuyển tiếp** được đưa vào qua thư viện khác. Công cụ build cần giải quyết các yêu cầu phiên bản để tạo classpath cuối cùng.

### 2.1. Bộ phiên bản minh họa đã được kiểm chứng

Với Spring Boot 3.3.5 và không có thay đổi quản lý phiên bản liên quan, bộ dưới đây được đối chiếu từ BOM/POM của bản phát hành:

| Artifact hoặc nhóm | Phiên bản minh họa |
| --- | --- |
| `org.springframework.boot:spring-boot` | `3.3.5` |
| `io.micrometer:micrometer-core` | `1.13.6` |
| `io.micrometer:micrometer-observation` | `1.13.6` |
| `io.micrometer:micrometer-registry-prometheus` | `1.13.6` |
| `io.prometheus:prometheus-metrics-core` | `1.2.1` |
| Micrometer Tracing, nếu được sử dụng | `1.3.5` |

Các mốc Micrometer, Micrometer Tracing và Prometheus Client được khai báo trong [nguồn BOM Spring Boot v3.3.5](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-dependencies/build.gradle). Chương trình ở phần 6 còn kiểm tra trực tiếp các JAR của nhánh số đo Prometheus.

Không áp bộ này cho mọi bản Spring Boot 3.3.x. Khi đọc [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html), kiểm tra nhãn phiên bản của trang: đường tài liệu theo dòng `3.3` có thể hiển thị một bản vá khác bản ứng dụng đang dùng.

### 2.2. Sự khác nhau chưa tự chứng minh lỗi

Một dự án có thể chủ động thay phiên bản vì yêu cầu cụ thể. Khi đó cần biết thay ở đâu, vì sao thay và đã kiểm chứng phạm vi nào.

Ngược lại, thấy các phiên bản đúng như BOM chưa đủ để kết luận đường xuất dữ liệu hoạt động. Cấu hình đích, xác thực, công khai endpoint hoặc đường mạng vẫn có thể sai.

## 3. Xác định ai đang quản lý phiên bản trong Gradle

Spring Boot hỗ trợ dùng plugin `io.spring.dependency-management` hoặc cơ chế BOM gốc của Gradle. Hai cách có quy tắc tùy chỉnh khác nhau. Tham khảo [Spring Boot 3.3 — Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html).

### 3.1. Cách dùng platform của Gradle

Trong một dự án đã áp dụng plugin Java, một cấu hình rút gọn có thể là:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

BOM quản lý các phiên bản. Registry được khai báo `runtimeOnly` vì ví dụ này giả định mã ứng dụng không import trực tiếp kiểu riêng của registry.

Nếu mã Java có import `PrometheusMeterRegistry`, nó cần thư viện đó trên compile classpath, chẳng hạn khai báo bằng `implementation` trong thí nghiệm phần 6.

Trong Gradle, `platform` cung cấp các ràng buộc phiên bản và có thể bị ảnh hưởng bởi các yêu cầu/ràng buộc khác. Nó không phải bảo đảm mọi dependency cuối cùng luôn đúng bằng giá trị trong BOM. `enforcedPlatform` có tác dụng cưỡng chế mạnh hơn; không đổi sang cơ chế này chỉ để làm báo cáo hết khác biệt khi chưa hiểu tác động. Xem [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html).

### 3.2. Cách dùng plugin dependency-management

Nếu dự án dùng Spring Boot Gradle Plugin cùng `io.spring.dependency-management`, plugin Boot nhập BOM tương ứng theo cơ chế tích hợp. Khi ấy các dependency được quản lý thường không cần phiên bản riêng.

Tuy nhiên, phải xác minh plugin và cấu hình thật của project ứng dụng. Chỉ nhìn thấy một phiên bản plugin trong project gốc hoặc một version catalog chưa đủ để biết mọi project con đang được quản lý giống nhau.

Tài liệu [Dependency Management Plugin](https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/) mô tả cách nhập BOM và phạm vi áp dụng. Với cơ chế này, các thuộc tính quản lý phiên bản có thể được tùy chỉnh theo khả năng plugin hỗ trợ.

Không mặc định việc đặt một thuộc tính như `micrometer.version` sẽ có cùng hiệu lực khi chuyển sang native `platform`. Cần dùng đúng cơ chế và đọc lại kết quả giải quyết dependency.

### 3.3. Những nơi có thể làm bộ phiên bản thay đổi

Khi kết quả khác mong đợi, kiểm tra các vị trí liên quan:

- Phiên bản khai báo trực tiếp trên dependency.
- BOM khác hoặc platform khác cùng tham gia.
- Ràng buộc phiên bản và quy tắc giải quyết dependency.
- Các lệnh ép phiên bản như `resolutionStrategy.force`.
- Convention plugin hoặc cấu hình dùng chung.
- Version catalog, nơi cung cấp các khai báo được tham chiếu.
- Dependency lock đang áp dụng.
- Khác biệt giữa compile, runtime và test classpath.

Đây là danh sách nơi tìm bằng chứng, không phải đề nghị xóa hàng loạt cấu hình. Đặc biệt, lock file nhằm giữ kết quả giải quyết ổn định; cần cập nhật có chủ đích khi thay dependency. Xem [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html).

## 4. Đọc phiên bản đã được giải quyết

Với dự án Gradle, bắt đầu từ runtime classpath của đúng ứng dụng:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

Sau đó dùng báo cáo chi tiết cho các thành phần chính:

```powershell
.\gradlew.bat dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency prometheus-metrics-core --configuration runtimeClasspath
```

Nếu dùng registry khác, thay bộ lọc bằng tên artifact thật. Với dự án nhiều project, thêm đường project đã được đăng ký, ví dụ:

```powershell
.\gradlew.bat :service:dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

`:service` là tên project minh họa; dùng đường project thật của ứng dụng. Trên Linux/macOS, dùng wrapper `./gradlew` tương ứng.

### 4.1. Đừng chỉ tìm một chuỗi phiên bản

Cần đọc cả:

1. Dependency được yêu cầu theo đường nào.
2. Phiên bản cuối cùng được chọn.
3. Lý do chọn phiên bản.
4. Ràng buộc hoặc quy tắc nào tham gia.
5. Configuration đang được kiểm tra có đúng với tiến trình cần chạy không.

Ví dụ một dòng cây giả định:

```text
io.micrometer:micrometer-core:1.13.5 -> 1.13.6
```

Dòng này biểu diễn yêu cầu 1.13.5 đã được chọn thành 1.13.6 trong đồ thị đó. Nó không tự nói hai JAR cùng được đóng gói.

Ký hiệu `(c)` chỉ một ràng buộc, còn `(*)` cho biết cây chuyển tiếp đã được trình bày ở nơi khác. Các lý do như `By constraint`, `Selected by rule` hay `Forced` giúp lần ra tác động quản lý phiên bản. Xem [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

Đừng gọi việc một dependency được chọn khác yêu cầu ban đầu là “xung đột gây lỗi” trước khi đọc nguyên nhân và đánh giá bộ phiên bản cuối.

### 4.2. So sánh compile và runtime khi có dấu hiệu lệch

Nếu chương trình biên dịch nhưng lỗi khi chạy, có thể đọc thêm:

```powershell
.\gradlew.bat dependencyInsight --dependency micrometer-core --configuration compileClasspath
.\gradlew.bat dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

Hai báo cáo giúp xác định sự khác nhau ở các configuration. Chúng vẫn cần được đối chiếu với cách ứng dụng thực sự được đóng gói và khởi động.

Không lấy kết quả của project thư viện hoặc test classpath rồi coi đó là bằng chứng cho runtime của project ứng dụng khác.

## 5. Phân biệt nhánh registry và thư viện xuất dữ liệu

### 5.1. Hai nhánh Prometheus có tên gần nhau

Trong dòng Micrometer 1.13, hai lựa chọn sau dùng các thế hệ Prometheus Java Client khác nhau:

| Artifact registry | Nhánh client bên dưới | Package registry tiêu biểu |
| --- | --- | --- |
| `micrometer-registry-prometheus` | Prometheus Java Client 1.x | `io.micrometer.prometheusmetrics` |
| `micrometer-registry-prometheus-simpleclient` | Simpleclient 0.x | `io.micrometer.prometheus` |

Sự phân chia được mô tả trong [Micrometer 1.13 — Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

Đây không phải hai cách viết cùng tên artifact. Một đoạn mã import package của nhánh cũ có thể không biên dịch với dependency của nhánh mới.

Trước khi sửa import hoặc thêm dependency, xác định nhánh tích hợp mà ứng dụng định dùng và các yêu cầu của framework/thư viện cộng tác. Không thêm cả hai registry chỉ để làm mọi import đều được tìm thấy.

### 5.2. Không gán số phiên bản registry cho client

Trong ví dụ được kiểm chứng:

```text
micrometer-registry-prometheus 1.13.6
              ↓ sử dụng
prometheus-metrics-core 1.2.1
```

Số 1.13.6 thuộc Micrometer. Không có căn cứ để tự đổi `prometheus-metrics-core` thành 1.13.6 cho “đồng bộ”.

Tương tự, khi chỉ muốn bật số đo Prometheus qua Actuator, thường khai báo registry phù hợp và để dependency chuyển tiếp được quản lý. Chỉ khai báo client riêng khi mã hoặc thiết kế tích hợp thực sự cần, rồi kiểm tra đồ thị lại.

### 5.3. Số đo OTLP và xuất dấu vết là hai đường cần phân biệt

`micrometer-registry-otlp` phục vụ số đo theo OTLP. Cấu hình tương ứng trong Spring Boot dùng nhóm thuộc tính `management.otlp.metrics.export`. Xem [Micrometer 1.13 — OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html).

Với dấu vết, Spring Boot sử dụng Micrometer Tracing và các bridge/exporter tương ứng. Ví dụ tích hợp OpenTelemetry cần các thành phần dành cho tracing, không chỉ một registry số đo. Xem [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Vì vậy, tên “exporter” trong một lỗi chưa đủ để chọn dependency thay thế. Ghi rõ đang xuất loại dữ liệu gì, dùng artifact nào và giao thức/đích nào.

## 6. Thí nghiệm Java: kiểm tra JAR đã nạp và xuất thử một số đo

Thí nghiệm dùng một chương trình Java độc lập, không mở cổng HTTP và không kết nối máy chủ Prometheus. Nó kiểm tra nơi nạp các lớp rồi dùng registry tạo một mẫu số đo.

### 6.1. Chuẩn bị dự án nhỏ

Dùng JDK 17 trở lên cùng Gradle tương thích. Tạo một thư mục mới để tránh có các JAR cũ hoặc cấu hình khác ảnh hưởng.

Tạo `settings.gradle`:

```groovy
rootProject.name = 'version-set-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

Ở đây registry dùng `implementation` vì chương trình import trực tiếp API riêng của nó và của client chuyển tiếp. Chỉ nhập BOM là chưa đủ; các dependency sử dụng vẫn phải được khai báo.

### 6.2. Mã Java đầy đủ

Lưu vào `src/main/java/lab/versions/VersionSetDemo.java`:

```java
package lab.versions;

import java.nio.file.Path;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.springframework.boot.SpringBootVersion;

public class VersionSetDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("spring-boot=" + SpringBootVersion.getVersion());
        System.out.println("micrometer-core=" + jarName(MeterRegistry.class));
        System.out.println("registry=" + jarName(PrometheusMeterRegistry.class));
        System.out.println("prometheus-client="
                + jarName(io.prometheus.metrics.core.metrics.Counter.class));

        PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        try {
            Counter checks = registry.counter("version.checks");
            checks.increment();
            System.out.println("counter=" + checks.count());
            String sample = registry.scrape().lines()
                    .filter(line -> line.startsWith("version_checks_total "))
                    .findFirst().orElseThrow();
            System.out.println("sample=" + sample);
        } finally {
            registry.close();
        }
    }

    private static String jarName(Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain()
                .getCodeSource().getLocation().toURI())
                .getFileName().toString();
    }
}
```

Hàm `jarName` đọc vị trí mà JVM dùng để nạp lớp. Trong thí nghiệm chạy bằng các JAR thường trên classpath, tên tệp cho biết artifact và phiên bản của lớp được kiểm tra.

Không dùng cách này như một bộ kiểm chứng tuyệt đối cho mọi hình thức đóng gói. Khi thư viện được gộp, đổi tên, nạp bằng classloader riêng hoặc chạy native image, thông tin nơi nạp có thể khác hoặc không có theo dạng trên.

### 6.3. Lệnh biên dịch và chạy

Tại thư mục gốc của thí nghiệm, dùng PowerShell:

```powershell
gradle copyDemoLibraries
javac -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/versions/VersionSetDemo.java
java -cp "out;lib/*" lab.versions.VersionSetDemo
```

Nếu có wrapper trong dự án thử, dùng wrapper tương ứng thay cho `gradle`. Trên Linux/macOS, lệnh chạy dùng dấu `:`:

```bash
java -cp "out:lib/*" lab.versions.VersionSetDemo
```

Gradle cần truy cập kho thư viện nếu dependency chưa được lưu trong bộ nhớ đệm. Tác vụ copy không có mục đích xóa JAR cũ, nên dùng thư mục mới để tránh lẫn thư viện từ lần thử khác.

Stdout đã được kiểm chứng với bộ phiên bản của ví dụ:

```text
spring-boot=3.3.5
micrometer-core=micrometer-core-1.13.6.jar
registry=micrometer-registry-prometheus-1.13.6.jar
prometheus-client=prometheus-metrics-core-1.2.1.jar
counter=1.0
sample=version_checks_total 1.0
```

Thông báo tải hoặc thực thi Gradle không thuộc stdout của chương trình Java.

### 6.4. Kết quả chứng minh gì?

| Quan sát | Kết luận có thể rút ra trong thí nghiệm |
| --- | --- |
| Dòng Spring Boot | Phiên bản của lớp Boot đã nạp |
| Ba dòng tên JAR | Các lớp đại diện được nạp từ những artifact cụ thể |
| `counter=1.0` | Bộ đếm đã ghi nhận một lần tăng |
| `sample=...` | Registry tạo được mẫu số đo Prometheus cho bộ đếm đó |

Phần xuất thử có ích hơn việc chỉ in tên phiên bản: nó kiểm tra một đường thao tác thực tế từ API Micrometer tới dữ liệu đầu ra.

Tuy nhiên, đây là một phép kiểm tra nhỏ. Nó chưa xác nhận mọi loại meter, mọi cấu hình histogram, tracing, HTTP Actuator hay việc máy chủ bên ngoài thu thập thành công. Khi đánh giá một lần nâng phiên bản, bổ sung kiểm tra cho các khả năng mà ứng dụng thật sử dụng.

### 6.5. Đối chiếu với ứng dụng đang triển khai

Nếu IDE và gói triển khai cho kết quả khác, xem cách đóng gói và runtime thực tế. Chẳng hạn, với một executable JAR Spring Boot mang tên minh họa `order-service-1.0.0.jar`:

```powershell
jar --list --file "build/libs/order-service-1.0.0.jar" | Select-String "BOOT-INF/lib/.*(spring-boot|micrometer|prometheus)"
```

Thay tên tệp bằng artifact thật. Lệnh chỉ liệt kê, không sửa JAR. Nó dành cho executable JAR có bố cục Boot tương ứng, không phải đầu ra class của thí nghiệm console.

Danh sách JAR trong gói giúp kiểm tra việc đóng gói. Khi có nhiều nguồn nạp lớp hoặc classloader riêng, vẫn cần bằng chứng từ tiến trình để biết lớp nào được chọn.

## 7. Nếu dự án dùng Maven

Nguyên tắc kiểm tra vẫn giống nhau: xác định nguồn quản lý phiên bản, đọc đồ thị cuối cùng rồi đối chiếu runtime.

Một dự án Maven có thể kế thừa `spring-boot-starter-parent` hoặc nhập `spring-boot-dependencies` trong `dependencyManagement`. Chỉ khai báo phiên bản Maven plugin Spring Boot không tương đương đã nhập bộ quản lý dependency. Xem [Spring Boot 3.3 — Using the Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html).

Các lệnh đọc hữu ích tại đúng module ứng dụng:

```powershell
mvn dependency:tree "-Dincludes=org.springframework.boot:*,io.micrometer:*,io.prometheus:*"
mvn help:effective-pom
```

Nếu có Maven Wrapper, dùng wrapper của dự án. Trong `effective-pom`, tìm phần quản lý phiên bản và các khai báo trực tiếp; trong cây dependency, tìm phiên bản được chọn và đường đưa nó vào.

Bộ lọc của `dependency:tree` hỗ trợ group/artifact và ký tự đại diện. Nếu dùng exporter thuộc nhóm khác, thêm nhóm tương ứng vào bộ lọc thay vì cho rằng không thấy trong báo cáo là không có dependency. Xem [Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

Không chuyển nguyên quy tắc giải quyết xung đột của Gradle sang Maven. Dùng báo cáo và cơ chế quản lý của đúng công cụ đang build ứng dụng.

## 8. Đọc lỗi để chọn hướng kiểm tra phù hợp

| Dấu hiệu | Hướng kiểm tra đầu tiên | Điều chưa được kết luận ngay |
| --- | --- | --- |
| Import package registry không tồn tại | Artifact, nhánh client và compile classpath | Cần thêm cả hai nhánh registry |
| `NoSuchMethodError` | Lớp gọi, lớp được nạp và sự tương thích nhị phân | Mọi lỗi đều do thư viện mới nhất |
| `NoClassDefFoundError` | Lớp thiếu, runtime classpath và chuỗi nguyên nhân | Chỉ cần thêm một JAR tùy ý |
| `UnsupportedClassVersionError` | JDK chạy và phiên bản bytecode của lớp | Cấu hình endpoint Actuator đang sai |
| `/actuator/prometheus` không truy cập được | Dependency, điều kiện, công khai, bảo mật, đường dẫn | Bộ phiên bản chắc chắn không tương thích |
| Registry đã có dữ liệu nhưng hệ thống ngoài không thấy | Đường thu thập/đẩy, đích nhận và quyền | Phải nâng Micrometer |
| Số đo đã xuất nhưng biểu đồ trống | Tên, nhãn, truy vấn và thời gian lưu | Ứng dụng không có registry |

### 8.1. NoSuchMethodError: khác biệt ở định nghĩa phương thức

JVM báo lỗi này khi mã cố gọi một phương thức nhưng định nghĩa lớp được dùng lúc chạy không có phương thức tương ứng. Xem [Java 17 — NoSuchMethodError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html).

Ví dụ cách điều tra:

1. Ghi tên phương thức và lớp trong lỗi.
2. Xác định thư viện chứa lớp gọi và lớp được gọi.
3. Đọc phiên bản trên compile/runtime graph.
4. Kiểm tra JAR thực tế đã được đóng gói hoặc nạp.
5. Tìm quy tắc hoặc khai báo làm bộ thư viện khác mong đợi.

Biên dịch thành công không loại trừ lỗi này nếu runtime dùng một bộ lớp khác. Không sửa bằng cách thử lần lượt nhiều phiên bản mà không lưu bằng chứng.

### 8.2. NoClassDefFoundError: kiểm tra lớp và nguyên nhân gốc

Một khả năng là lớp cần dùng không còn có trên runtime classpath. Xem [Java 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html).

Cũng cần đọc toàn bộ chuỗi nguyên nhân: thông báo liên quan tới việc không khởi tạo được một lớp có thể cần truy về lỗi khởi tạo trước đó. Đừng chỉ lấy tên lớp ở dòng cuối rồi thêm một dependency trùng chức năng.

Đổi từ nhánh Prometheus Client cũ sang mới cũng đòi hỏi xem mã hoặc thư viện nào còn tham chiếu package cũ.

### 8.3. UnsupportedClassVersionError: kiểm tra JDK thực sự chạy

Lỗi này liên quan việc JVM không hỗ trợ phiên bản class file đang đọc. Xem [Java 17 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html).

Một kiểm tra đơn giản:

```powershell
java -version
javac -version
.\gradlew.bat --version
```

Các lệnh giúp nhận diện công cụ trên môi trường gọi lệnh. IDE, Gradle toolchain hoặc máy triển khai có thể dùng JDK khác; kiểm tra đúng tiến trình cần chẩn đoán.

Đây là vấn đề khác với việc các JAR Micrometer có cùng phiên bản hay không. Hai loại kiểm tra cần được ghi riêng.

## 9. Khi nào cần thay phiên bản và thay theo cách nào?

Bắt đầu từ bộ phiên bản được nền Spring Boot quản lý. Nếu cần thay, ghi mục tiêu cụ thể: yêu cầu API, bản sửa lỗi hoặc yêu cầu tương thích đã xác minh.

Một thay đổi có thể kiểm tra được nên gồm:

1. Bộ hiện tại và cơ chế quản lý hiện tại.
2. Bộ đích cùng tài liệu phù hợp.
3. Khai báo/ràng buộc nào sẽ thay đổi.
4. Những phần xuất số đo hoặc dấu vết cần kiểm tra lại.
5. Bằng chứng runtime và kết quả thử.
6. Cách quay về bộ đã xác minh nếu cần.

### 9.1. Tránh cập nhật riêng một mảnh mà không đọc các mảnh còn lại

Nếu tăng riêng `micrometer-core` nhưng registry vẫn ở một nhánh cũ, bạn đã tạo một bộ mới cần được đánh giá. Việc số phiên bản lớn hơn không tự bảo đảm kết hợp ấy phù hợp với Spring Boot đang dùng.

Ngược lại, nâng Spring Boot rồi giữ một `force` hoặc lock cũ có thể làm ứng dụng tiếp tục dùng một phần thư viện trước đây. Đọc lại đồ thị sau thay đổi; đừng chỉ kiểm tra dòng plugin.

### 9.2. Kiểm chứng theo khả năng thực sự sử dụng

Với Prometheus, kiểm tra các meter tiêu biểu, việc tạo dữ liệu đầu ra và đường HTTP nếu ứng dụng dùng Actuator web. Nếu ứng dụng có histogram, nhãn tùy chỉnh hoặc dữ liệu liên kết dấu vết, thử cả những phần đó.

Với đường đẩy dữ liệu, kiểm tra cấu hình xuất, phản hồi của nơi nhận và dữ liệu thật ở hệ thống đích. Chương trình console ở phần 6 không đại diện cho những đường này.

Nếu ứng dụng dùng tracing, kiểm tra riêng việc tạo và truyền ngữ cảnh, bộ xuất và nơi lưu dấu vết. Không suy ra đường tracing hoạt động chỉ từ một số đo Prometheus đã xuất thành công.

### 9.3. Đừng dùng thao tác làm sạch để thay cho chẩn đoán

`clean` thường xóa đầu ra build, không tự thay mọi quy tắc chọn dependency. Làm mới bộ nhớ đệm cũng không sửa được một khai báo ép phiên bản sai vẫn còn trong cấu hình.

Hãy sửa nguyên nhân đã xác định, tạo lại artifact khi cần, rồi đọc lại graph và runtime. Giữ thay đổi nhỏ đủ để giải thích được trước và sau.

## 10. Ghi một bản kiểm tra phiên bản có thể đối chiếu

Một ghi chép đã điền theo thí nghiệm:

```text
Nguồn quản lý: spring-boot-dependencies 3.3.5.
Cơ chế: Gradle native platform.
Micrometer Core: 1.13.6.
Registry: micrometer-registry-prometheus 1.13.6.
Client phía dưới: prometheus-metrics-core 1.2.1.
Nhánh package: io.micrometer.prometheusmetrics.
Runtime được kiểm tra: chương trình console trên classpath JAR riêng.
Bằng chứng: tên JAR đã nạp, counter=1.0 và mẫu Prometheus được tạo.
Chưa kiểm tra: HTTP Actuator, máy chủ Prometheus và tracing.
```

Với ứng dụng thật, bổ sung tên module build, configuration đã đọc, artifact triển khai, JDK và thời điểm kiểm tra. Nếu graph và runtime khác nhau, ghi rõ sự khác biệt thay vì chỉ đánh dấu “đúng BOM”.

### Tự kiểm tra qua tình huống

**Tình huống A:** Core và registry là 1.13.6, client là 1.2.1. Có cần đổi client cho cùng số không?

Không. Đây là các nhóm artifact có hệ phiên bản riêng. Cần đối chiếu bộ được quản lý và graph thực tế, không so chuỗi số bằng nhau.

**Tình huống B:** Build file không ghi phiên bản registry, nhưng runtime vẫn dùng phiên bản khác BOM mong đợi.

Kiểm tra cơ chế quản lý có áp dụng đúng configuration không, các ràng buộc/quy tắc khác, lock và artifact triển khai. Bỏ phiên bản ở một dòng không loại bỏ mọi nguồn ảnh hưởng khác.

**Tình huống C:** Mã import `io.micrometer.prometheus`, còn dependency dùng nhánh client 1.x.

Xác minh mã và dependency đang thuộc nhánh nào. Chọn cách tích hợp phù hợp rồi điều chỉnh có kiểm chứng, không tự thêm nhánh cũ song song chỉ để hết lỗi import.

**Tình huống D:** Registry xuất được một mẫu nhưng Prometheus không thu thập.

Phép thử đã xác nhận một phần phía ứng dụng. Tiếp tục kiểm tra đường cung cấp dữ liệu và bên thu thập; chưa có bằng chứng phải đổi phiên bản thư viện.

### Bài tập áp dụng

Chọn đúng một đường xuất dữ liệu của ứng dụng và lập bảng gồm: artifact, phiên bản được quản lý, phiên bản được chọn, nơi nạp lớp hoặc gói triển khai, cùng lý do chọn phiên bản.

Sau đó ghi một phép thử đại diện và giới hạn của phép thử. Bạn hoàn thành việc kiểm tra bộ phiên bản khi có thể giải thích **vì sao build chọn các thư viện đó, tiến trình dùng gì và đường dữ liệu đã được kiểm chứng tới đâu**.
