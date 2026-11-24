# Di chuyển từ Spring Native thử nghiệm cũ sang hỗ trợ AOT của Spring Boot phù hợp

## 1. Bối cảnh và mục tiêu migration

Spring Native là dự án thử nghiệm đưa ứng dụng Spring lên GraalVM Native Image. Bản 0.12.2 là một trong những bản cuối của dòng thử nghiệm, được kiểm thử với Spring Boot 2.7.7 và GraalVM 22.1. Sau quá trình thử nghiệm, Spring chuyển hỗ trợ native sang Spring Boot 3 chính thức. Kho Spring Native được lưu trữ và không còn phát hành bản mới.

Với Spring Boot 3, Spring AOT, Runtime Hints và tích hợp Native Build Tools trở thành một phần của hệ sinh thái Spring Boot/Spring Framework. Ứng dụng không cần giữ dependency Spring Native thử nghiệm hoặc plugin AOT riêng của dự án cũ.

Migration không chỉ là xóa một dependency rồi nâng version. Cần kiểm tra đồng thời:

- Phiên bản Spring Boot, Java, Spring Framework và thư viện liên quan.
- Dependency và plugin thử nghiệm cũ.
- Cách cấu hình AOT trong Maven hoặc Gradle.
- Native hints cho reflection, resource, proxy và serialization.
- Profile/condition được đánh giá ở build time.
- Tương thích Jakarta EE và các thay đổi lớn của Spring Boot 3.
- Kiểm thử AOT trên JVM, native test và native executable cuối cùng.

Bài này thuộc chương **Di chuyển và nâng cấp** của module **SPRING_BOOT_NATIVE_IMAGE**. Mục tiêu là đưa ứng dụng đang dùng Spring Native sang cơ chế AOT tích hợp trong Spring Boot phù hợp, có thể build và kiểm thử lại một cách lặp lại.

## 2. Hiểu khác biệt giữa Spring Native và Spring Boot Native support

| Thành phần | Spring Native thử nghiệm | Spring Boot tích hợp AOT |
| --- | --- | --- |
| Trạng thái | Dự án thử nghiệm, đã lưu trữ | Hỗ trợ native chính thức trong Spring Boot 3 trở lên |
| AOT engine | Plugin riêng org.springframework.experimental | Tích hợp trong Spring Boot và Spring Framework |
| Maven AOT | spring-aot-maven-plugin | spring-boot-maven-plugin với process-aot |
| Gradle AOT | org.springframework.experimental.aot | Spring Boot Gradle plugin phối hợp Native Build Tools |
| Native hints | @NativeHint, @TypeHint, NativeConfiguration | RuntimeHintsRegistrar, @ImportRuntimeHints, @RegisterReflectionForBinding |
| Native compiler | Native Build Tools hoặc Buildpacks với cấu hình cũ | Native Build Tools và Spring Boot Buildpacks integration |
| Test AOT/native | Cơ chế test plugin cũ | process-test-aot, nativeTest và Native Build Tools |
| Metadata bên thứ ba | Spring Native configuration modules | Reachability Metadata Repository và metadata do thư viện cung cấp |

Spring Native 0.12.2 chỉ xác nhận một phạm vi hỗ trợ beta cụ thể; tài liệu cũ nêu Spring Boot 2.7.7 và GraalVM 22.1. Không nên tiếp tục dùng các version đó như baseline cho dự án mới. Spring Boot 3 chuyển native support thành mục tiêu biên dịch chính thức và tích hợp sâu hơn với GraalVM tooling.

Tài liệu chuyển đổi của Spring: [From Spring Native to Spring Boot 3](https://spring.io/blog/2023/02/23/from-spring-native-to-spring-boot-3). Tài liệu Spring Native cũ cũng ghi rõ dự án đã được thay thế bởi native support chính thức của Spring Boot 3.

## 3. Kiểm kê dự án cũ trước khi nâng cấp

Trước khi sửa build file, hãy ghi lại trạng thái hiện tại để biết những gì cần chuyển đổi.

| Khu vực | Cần kiểm tra |
| --- | --- |
| Spring Boot | Version hiện tại, thường thuộc dòng 2.7.x nếu dùng Spring Native 0.12.x |
| Java/GraalVM | JDK, GraalVM distribution, edition và native-image version |
| Maven/Gradle | Wrapper version, plugin version và build profile |
| Spring Native dependencies | org.springframework.experimental:spring-native, spring-native-configuration |
| AOT plugin | spring-aot-maven-plugin hoặc org.springframework.experimental.aot |
| Native Build Tools | native-maven-plugin hoặc org.graalvm.buildtools.native |
| Hints | @NativeHint, @TypeHint, NativeConfiguration, spring.factories |
| Native JSON metadata | META-INF/native-image và các file reflect/resource/proxy |
| Buildpacks | BP_NATIVE_IMAGE, builder và buildpack version |
| Tests | JVM tests, AOT tests, native tests và test fixture |
| Dependencies | Thư viện có hỗ trợ Spring Boot 3, Jakarta và GraalVM hay không |

Lưu lại output của dependency tree và danh sách plugin đang được áp dụng. Nếu một dependency cũ đến từ module dùng chung hoặc plugin quản lý tập trung, hãy xác định nơi khai báo thực sự trước khi xóa.

Ví dụ kiểm tra dependency:

```bash
./mvnw dependency:tree
./gradlew dependencies
```

Với Gradle, có thể lọc dependency theo group/artifact bằng task hoặc báo cáo dependency phù hợp với build. Không xóa dependency chỉ vì tên có chữ native; cần biết nó đến từ Spring Native cũ, Native Build Tools hay một thư viện runtime khác.

## 4. Chọn đường nâng cấp Spring Boot

Nếu dự án đang ở Spring Boot 2.7, hãy ổn định ứng dụng trên bản maintenance mới nhất của dòng 2.7 trước khi chuyển sang Boot 3. Điều này giúp tách lỗi do nâng framework khỏi lỗi do thay đổi native build pipeline.

Spring Boot 3.0 yêu cầu Java 17 trở lên và Spring Framework 6.0. Nó cũng chuyển các API Java EE thuộc phạm vi Spring Boot sang Jakarta EE. Vì vậy, cần chuẩn bị cả migration nền tảng:

1. Nâng JDK/build tool lên mức được Spring Boot 3 hỗ trợ.
2. Kiểm tra dependency Spring Cloud, Spring Data, Spring Security và thư viện bên thứ ba tương thích.
3. Chuyển các API javax.* thuộc Jakarta EE sang jakarta.*.
4. Nâng Spring Boot và các plugin theo cùng release line.
5. Chạy ứng dụng JVM bình thường trước.
6. Sau khi ứng dụng ổn định trên Boot 3, mới chuyển native AOT build.

Không trộn nâng Spring Boot, thay database driver, đổi logging và chuyển native hints trong một thay đổi lớn nếu có thể tách thành các bước review độc lập.

Tham khảo [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide) và release notes tương ứng với version đích. Các yêu cầu cụ thể của Spring Boot 3.0 là mốc lịch sử; khi chọn bản Boot mới hơn, hãy kiểm tra system requirements và GraalVM compatibility của đúng bản đó.

## 5. Gỡ dependency Spring Native cũ

Với Maven, dependency thử nghiệm thường được khai báo như sau:

```xml
<dependency>
    <groupId>org.springframework.experimental</groupId>
    <artifactId>spring-native</artifactId>
    <version>0.12.2</version>
</dependency>
```

Xóa dependency này sau khi chuyển ứng dụng sang Spring Boot native support. Spring Boot 3 không yêu cầu spring-native để chạy native executable.

Với Gradle, Spring AOT plugin cũ có thể đã kéo spring-native transitively. Khi bỏ plugin cũ, kiểm tra dependency tree để bảo đảm dependency thử nghiệm không còn được thêm gián tiếp.

Nếu dự án có spring-native-configuration hoặc module cấu hình native tự viết, phân loại từng hint trước khi xóa. Không xóa metadata ứng dụng cần dùng chỉ vì module chứa hint được tạo trong thời kỳ Spring Native. Chuyển những hint còn cần sang Runtime Hints API hoặc metadata JSON phù hợp.

## 6. Chuyển cấu hình Maven

### 6.1. Cấu hình cũ

Một Maven project dùng Spring Native 0.12.x thường có hai phần riêng:

- org.springframework.experimental:spring-aot-maven-plugin để sinh source/AOT artifacts.
- org.graalvm.buildtools:native-maven-plugin để gọi native-image compiler.

Ví dụ plugin AOT cũ:

```xml
<plugin>
    <groupId>org.springframework.experimental</groupId>
    <artifactId>spring-aot-maven-plugin</artifactId>
    <version>0.12.2</version>
    <executions>
        <execution>
            <id>generate</id>
            <goals>
                <goal>generate</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Gỡ execution này cùng các cấu hình cũ chỉ dành cho plugin thử nghiệm. Không tiếp tục gọi goal spring-aot:generate sau khi đã chuyển sang Spring Boot AOT.

### 6.2. Cấu hình tích hợp mới

Nếu dùng spring-boot-starter-parent, profile native của Spring Boot Maven plugin có thể cấu hình việc chạy process-aot và các mặc định phù hợp cho Native Build Tools. Module ứng dụng cần khai báo Spring Boot plugin và Native Build Tools plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>

        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Build native executable:

```bash
./mvnw -Pnative native:compile
```

Hoặc tạo container image bằng Buildpacks nếu dự án đã cấu hình builder phù hợp:

```bash
./mvnw -Pnative spring-boot:build-image
```

Profile native do Spring Boot parent cung cấp có các thiết lập AOT và Native Build Tools hữu ích. Nếu dự án không dùng spring-boot-starter-parent, cần cấu hình execution process-aot cho Spring Boot Maven plugin và cấu hình Native Build Tools theo tài liệu của version đang dùng. Không giả định profile của parent tự tồn tại trong một POM chỉ import BOM.

### 6.3. Kiểm tra plugin version

Không sao chép nguyên version Native Build Tools từ project Spring Native cũ. Các ví dụ cũ có thể dùng plugin 0.9.x; Spring Boot 3.0 yêu cầu GraalVM 22.3 trở lên và Native Build Tools 0.9.17 trở lên. Các release Spring Boot mới có ma trận tương thích mới hơn.

Để chọn version:

- Dùng Spring Boot release line đang triển khai.
- Kiểm tra GraalVM distribution/version được release đó hỗ trợ.
- Kiểm tra Native Build Tools plugin tương thích.
- Ưu tiên dependency/plugin management do Spring Boot parent hoặc build convention quản lý.
- Ghi version thực tế vào build metadata để tái lập.

## 7. Chuyển cấu hình Gradle

### 7.1. Cấu hình cũ

Spring Native Gradle thường dùng plugin:

```groovy
plugins {
    id 'org.springframework.boot' version '2.7.x'
    id 'org.springframework.experimental.aot' version '0.12.2'
}
```

Plugin org.springframework.experimental.aot thuộc dự án thử nghiệm. Gỡ plugin này và các repository milestone/snapshot chỉ được thêm để tải plugin cũ nếu không còn dependency nào khác cần chúng.

### 7.2. Cấu hình mới

Thay bằng Spring Boot Gradle plugin và GraalVM Native Build Tools plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
    id 'org.graalvm.buildtools.native' version '<native-build-tools-version>'
}
```

Khi Native Image plugin được áp dụng, Spring Boot Gradle plugin tự cấu hình AOT processing và task dependencies cần thiết. Không cần giữ plugin org.springframework.experimental.aot.

Build native executable:

```bash
./gradlew nativeCompile
```

Native executable thường được tạo dưới build/native/nativeCompile/. Đường dẫn/tên file có thể thay đổi theo binary configuration và plugin version.

Nếu dùng Kotlin DSL, chuyển plugin block sang cú pháp plugins { id("...") version "..." } và kiểm tra các task do Gradle tạo ra bằng ./gradlew tasks.

## 8. Chuyển từ Buildpacks cấu hình cũ

Spring Native cũ thường yêu cầu bật buildpack bằng biến BP_NATIVE_IMAGE=true trong cấu hình bootBuildImage hoặc Maven plugin. Spring Boot tích hợp native support cung cấp cấu hình Buildpacks phù hợp khi dùng profile native và plugin tương ứng.

Sau migration:

1. Bỏ cấu hình cũ chỉ phục vụ plugin Spring Native.
2. Chọn builder/buildpack tương thích với GraalVM và Spring Boot version.
3. Kiểm tra log Buildpacks để xác nhận quá trình AOT và native compilation đã chạy.
4. Kiểm tra container image thực sự chứa native executable.
5. Chạy smoke test trong image cuối cùng.
6. Ghi lại builder digest, GraalVM version, architecture và build arguments.

Không trộn cấu hình BP_NATIVE_IMAGE cũ với cấu hình native mới mà không hiểu thứ tự và nơi tiêu thụ biến. Nếu cần custom buildpack arguments, dùng cơ chế được tài liệu Spring Boot/Buildpacks của version hiện tại hỗ trợ.

## 9. Chuyển Native Hints API

Đây là phần cần review kỹ nhất khi migration. Spring Native cũ có @TypeHint, @NativeHint, @JdkProxyHint và NativeConfiguration. Spring Boot/Spring Framework mới dùng Runtime Hints API với các loại hint rõ ràng hơn.

| API cũ | Hướng chuyển đổi |
| --- | --- |
| @TypeHint cho DTO cần JSON binding | @RegisterReflectionForBinding nếu mục đích là binding |
| @TypeHint cho reflection tổng quát | RuntimeHintsRegistrar và hints.reflection() |
| @NativeHint chứa resource pattern | hints.resources() |
| @JdkProxyHint | hints.proxies().registerJdkProxy(...) |
| @NativeHint chứa serialization metadata | hints.serialization() hoặc API tương ứng |
| NativeConfiguration | RuntimeHintsRegistrar được import bằng @ImportRuntimeHints |
| spring.factories liệt kê NativeConfiguration | Đăng ký registrar từ configuration class bằng @ImportRuntimeHints |
| Native image build options | Native Build Tools build arguments hoặc native-image.properties theo mục đích |

Không phải mọi annotation cũ đều có phép thay thế một-một. Đọc mục đích của từng hint rồi chuyển sang API mới tương ứng. @RegisterReflectionForBinding dành cho kiểu cần binding/serialization introspection; nó không thay thế mọi reflection, proxy, JNI hoặc class initialization hint.

### 9.1. DTO binding với RegisterReflectionForBinding

Ví dụ cũ:

```java
@TypeHint(types = PartnerResponse.class)
@SpringBootApplication
public class OrdersApplication {
}
```

Nếu mục đích của hint chỉ là cho Jackson bind DTO, có thể chuyển sang:

```java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@RegisterReflectionForBinding(PartnerResponse.class)
public class OrdersApplication {
}
```

Annotation này yêu cầu Spring đăng ký reflection metadata cần thiết cho binding. Nếu class được truy cập bằng reflection theo mục đích khác, hãy dùng Runtime Hints API với member access phù hợp.

### 9.2. Reflection và resource với RuntimeHintsRegistrar

Ví dụ registrar mới:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class PartnerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            PartnerPayload.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.resources().registerPattern("partner/*.json");
    }
}
```

Import registrar từ một configuration class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PartnerRuntimeHints.class)
class PartnerNativeConfiguration {
}
```

Chỉ đăng ký member mà runtime thực sự cần. Hint quá rộng làm tăng kích thước và giảm lợi ích static analysis; hint thiếu sẽ khiến lỗi chỉ xuất hiện khi chạy native.

### 9.3. Proxy và serialization

Nếu code cũ đăng ký JDK proxy, chuyển sang hints.proxies().registerJdkProxy(...) với đúng interface được proxy. Với Java serialization, dùng API serialization của RuntimeHints và test đúng loại object thực tế.

Không nhầm JDK dynamic proxy với CGLIB/AOT-generated proxy. Spring AOT có thể sinh một số proxy cần thiết cho bean và cấu hình; custom proxy hoặc thư viện tự tạo proxy vẫn cần đánh giá riêng.

### 9.4. Hint JSON tĩnh

Các file GraalVM JSON metadata trong META-INF/native-image vẫn có thể được dùng nếu schema và option còn tương thích với GraalVM version đích. Không xóa hàng loạt reflect-config.json, resource-config.json, proxy-config.json chỉ vì chuyển khỏi Spring Native.

Hãy kiểm tra:

- File thuộc dependency nào và ai sở hữu.
- Metadata có còn đúng với version thư viện mới không.
- Có bị trùng với hint được Spring AOT sinh ra không.
- Đường dẫn metadata có được GraalVM nhận diện không.
- Native integration test có chứng minh metadata còn cần thiết không.

Spring Boot AOT tạo một số hint dưới META-INF/native-image/{groupId}/{artifactId}/. Đặt hint bổ sung ở thư mục khác để tránh ghi đè hoặc va chạm với output được sinh.

## 10. Chuyển NativeConfiguration và spring.factories

Trong Spring Native, thư viện có thể triển khai NativeConfiguration, gắn @NativeHint và liệt kê implementation qua key riêng trong META-INF/spring.factories.

Trong Spring Framework mới, một registrar có thể triển khai RuntimeHintsRegistrar rồi được kích hoạt qua @ImportRuntimeHints trên configuration class hoặc application configuration phù hợp.

Ví dụ cấu trúc:

```text
src/main/java/
  com/example/partner/
    PartnerRuntimeHints.java
    PartnerNativeConfiguration.java
```

Nếu đang phát triển thư viện dùng chung, hãy thiết kế registrar để không phụ thuộc class chỉ có trong ứng dụng tiêu thụ. Kiểm thử registrar độc lập và kiểm thử tích hợp với ứng dụng mẫu.

Lưu ý: spring.factories không biến mất hoàn toàn khỏi Spring. Điều cần thay ở đây là cơ chế đăng ký NativeConfiguration riêng của Spring Native. Riêng đăng ký auto-configuration của Spring Boot 3 có thay đổi khác: thư viện nên dùng META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports theo hướng dẫn migration của Spring Boot.

## 11. Profile, condition và môi trường AOT

Spring AOT chuẩn bị BeanFactory và đánh giá điều kiện tại build time. Do đó, profile hoặc property làm thay đổi bean graph phải được cấu hình khi chạy AOT.

Ví dụ, nếu @ConditionalOnProperty quyết định adapter nào tồn tại, giá trị property dùng khi AOT phải đại diện cho cấu trúc mong muốn của native executable.

Với Maven, cấu hình profile cho process-aot thông qua Spring Boot Maven plugin. Với Gradle, cấu hình arguments/environment cho task processAot. Đừng giả định active profile ở container runtime sẽ thêm bean đã bị loại khi AOT.

Nếu một binary phải hỗ trợ nhiều lựa chọn runtime, hãy thiết kế bean graph để các implementation cần thiết đều có mặt trong image rồi chọn implementation bằng logic runtime. Điều này chỉ hoạt động nếu mọi class, dependency và hint cần thiết đã được đưa vào binary.

## 12. Xử lý thay đổi Jakarta và Spring Boot 3

Chuyển từ Spring Native 0.12.x thường đi cùng nâng cấp từ Spring Boot 2.7 lên 3.x. Một số thay đổi cần rà soát:

- Java 17 trở lên là baseline của Spring Boot 3.0.
- Spring Framework 6 yêu cầu tương thích Jakarta EE.
- Các import thuộc Jakarta EE chuyển từ javax.* sang jakarta.*, ví dụ Servlet, Persistence và Validation.
- Spring Security 6 có thay đổi cấu hình và behavior.
- Hibernate 6 và Spring Data version mới có thể thay đổi API, mapping hoặc query behavior.
- Spring Cloud cần chọn release train tương thích với Spring Boot đích.
- Một số property, auto-configuration và dependency đã đổi tên hoặc bị loại bỏ.

Không thay mọi javax trong source bằng jakarta một cách máy móc. Chỉ chuyển package thuộc Jakarta EE; các package Java SE như javax.crypto, javax.net.ssl hoặc javax.sql vẫn là namespace Java chuẩn.

Spring Boot cung cấp spring-boot-properties-migrator để phát hiện một số property đã đổi hoặc bị loại bỏ trong quá trình nâng cấp. Chỉ dùng tạm thời trong giai đoạn migration và gỡ dependency này sau khi đã xử lý hết cảnh báo.

## 13. Kiểm tra thư viện bên thứ ba và reachability metadata

Spring Native cũ có module spring-native-configuration cung cấp hint cho một số thư viện. Trong hệ sinh thái mới, Spring Boot không tự chứa hint cho mọi thư viện bên thứ ba; thư viện có thể cung cấp reachability metadata riêng hoặc được hỗ trợ qua GraalVM Reachability Metadata Repository.

Với mỗi dependency quan trọng:

1. Kiểm tra phiên bản có hỗ trợ Spring Boot 3 và Java 17+ không.
2. Kiểm tra thư viện có metadata native đi kèm hay không.
3. Tìm reflection, JNI, resource loading, serialization và proxy usage.
4. Xem log native-image để biết metadata nào được tải.
5. Chạy integration test trên native executable.
6. Chỉ thêm hint ứng dụng khi metadata từ thư viện chưa giải quyết được.

Không sao chép nguyên các hint từ module cũ vào ứng dụng mới mà không kiểm tra. Một số hint cũ có thể quá rộng, trùng với hint mới hoặc nhắm vào class đã đổi package/API.

## 14. Kiểm thử migration theo từng lớp

Nên tăng dần mức kiểm thử để phát hiện lỗi sớm và giảm số lần native build tốn thời gian.

### 14.1. JVM tests

Chạy unit và integration tests bình thường sau khi nâng Spring Boot. Đây là nơi xử lý các lỗi API, Jakarta, configuration và behavior trước khi thêm native-specific debugging.

### 14.2. AOT-processed JVM

Build artifact có AOT generated code rồi chạy với spring.aot.enabled=true:

```bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/orders-api.jar
```

Với Gradle, đảm bảo plugin org.graalvm.buildtools.native được áp dụng để AOT tasks được cấu hình:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/orders-api.jar
```

Bước này giúp kiểm tra AOT-generated initialization code mà không phải chờ native-image compilation. Nó không thay thế native test.

### 14.3. Native executable

Build và chạy binary thực tế:

```bash
./mvnw -Pnative native:compile
./target/orders-api
```

Với Gradle:

```bash
./gradlew nativeCompile
./build/native/nativeCompile/orders-api
```

Tên file và output directory phụ thuộc artifact name, OS và build configuration. Hãy chạy smoke test qua HTTP, database, messaging, serialization và TLS theo các luồng ứng dụng sử dụng.

### 14.4. Native tests

Spring Boot và Native Build Tools hỗ trợ test chạy trong native image. Với Maven dùng spring-boot-starter-parent, profile nativeTest có thể cấu hình AOT test processing và native test execution:

```bash
./mvnw -PnativeTest test
```

Với Gradle:

```bash
./gradlew nativeTest
```

Native tests có chi phí build cao hơn JVM tests. Nên giữ phần lớn test trên JVM, chạy native tests cho luồng có khác biệt reflection/resource/proxy và đưa chúng vào CI theo lịch hoặc release gate phù hợp.

## 15. Kiểm thử Runtime Hints

Runtime Hints có thể được kiểm tra bằng RuntimeHintsPredicates mà không cần tạo native image cho mỗi thay đổi.

Ví dụ kiểm tra resource hint:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class PartnerRuntimeHintsTests {

    @Test
    void registersPartnerSchema() {
        RuntimeHints hints = new RuntimeHints();

        new PartnerRuntimeHints()
            .registerHints(hints, getClass().getClassLoader());

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("partner/schema.json")
        ).accepts(hints);
    }
}
```

Thêm test tương ứng cho reflection, proxy hoặc serialization hint nếu ứng dụng có sử dụng. Test này xác minh registrar khai báo đúng metadata; native integration test vẫn cần thiết để xác nhận hành vi thực tế trong binary.

## 16. Kiểm tra output AOT và native metadata

Sau AOT processing, kiểm tra các thư mục generated output để biết Spring đã tạo gì.

Với Maven, AOT thường sinh source, class và resource dưới target/spring-aot/main/sources, target/spring-aot/main/classes và target/spring-aot/main/resources. Các hint native được đặt trong phần resources, thường dưới META-INF/native-image; khi đóng gói, chúng có thể xuất hiện trong classpath của artifact.

Với Gradle, output thường nằm dưới build/generated/aotSources, build/generated/aotClasses và build/generated/aotResources/META-INF/native-image tùy phiên bản plugin.

Hãy kiểm tra:

- Generated source có chứa bean initializer dự kiến không.
- Runtime hints có bao gồm DTO, resource và proxy cần thiết không.
- Static JSON metadata có được đóng gói không.
- Native compiler có nhận metadata từ dependency không.
- Không có output cũ từ Spring Native plugin bị đưa vào classpath.

Không chỉnh sửa generated source hoặc generated hint output trực tiếp. Sửa registrar, annotation, metadata source hoặc build configuration rồi chạy AOT lại.

## 17. Lỗi migration thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy org.springframework.experimental | Dependency/plugin cũ đã bị xóa nhưng source còn import | Chuyển API hint sang Runtime Hints hoặc xóa code không còn cần |
| spring-aot:generate không còn goal | Đang gọi plugin AOT cũ | Dùng process-aot hoặc task do Spring Boot plugin cấu hình |
| @NativeHint/@TypeHint không resolve | API Spring Native đã bị loại khỏi dependency mới | Chuyển theo mục đích sang @RegisterReflectionForBinding, RuntimeHintsRegistrar hoặc JSON metadata |
| Native executable thiếu DTO binding | Hint cũ không được chuyển hoặc chỉ có hint cho class khác | Đăng ký binding đúng DTO và test native |
| Resource không được tìm thấy | Resource hint thiếu hoặc pattern sai | Đăng ký hints.resources() và test resource predicate |
| Profile runtime không tạo bean | Condition đã được đánh giá trong AOT | Chọn profile khi AOT hoặc thiết kế bean graph hỗ trợ runtime choice |
| JVM test pass nhưng native fail | Reflection, proxy, JNI hoặc resource thiếu metadata | Đọc native-image diagnostics, thêm hint có mục tiêu và test lại |
| Dependency không tương thích Boot 3 | Thư viện còn dùng javax hoặc API cũ | Nâng version thư viện hoặc thay thế dependency |
| Buildpacks tạo JVM image thay vì native image | Builder/profile không được cấu hình native | Kiểm tra native profile, builder và log Buildpacks |
| Multi-module build không tạo AOT output | Plugin chỉ áp dụng ở module không phải application | Áp dụng plugin và native profile cho đúng application module |
| Hint bị đăng ký trùng | Giữ cả JSON hint cũ và registrar mới | Kiểm tra nguồn metadata và loại bỏ phần trùng sau khi test |
| Native tests không chạy | Chưa cấu hình nativeTest hoặc thiếu GraalVM toolchain | Kiểm tra plugin, profile và native test task |

## 18. Quy trình migration theo từng giai đoạn

Một kế hoạch migration có thể thực hiện theo trình tự:

1. **Đóng băng baseline:** lưu commit, dependency tree, plugin list, native build command và kết quả test cũ.
2. **Ổn định Spring Boot 2.7:** nâng lên bản maintenance phù hợp và sửa deprecation.
3. **Nâng nền tảng:** chuyển JDK lên 17+, chọn GraalVM và Native Build Tools tương thích.
4. **Nâng Spring Boot:** xử lý Jakarta, Spring Framework, Spring Security, Spring Data và Spring Cloud.
5. **Gỡ Spring Native:** xóa dependency, plugin AOT và build configuration thử nghiệm.
6. **Tích hợp AOT mới:** cấu hình Spring Boot Maven/Gradle plugin và Native Build Tools.
7. **Chuyển hints:** đổi từng @NativeHint, @TypeHint, NativeConfiguration và metadata cần thiết.
8. **Kiểm tra dependency:** xác minh thư viện có reachability metadata hoặc native support.
9. **Chạy JVM tests và AOT JVM:** xử lý lỗi trước native compilation.
10. **Build native và native tests:** kiểm tra endpoint, database, serialization, resources, proxy và TLS.
11. **Đóng gói container:** kiểm tra architecture, libc, environment và startup behavior.
12. **Canary và rollout:** so sánh startup, memory, latency, error rate và rollback image nếu có lỗi.

Giữ một bản artifact cũ đã xác nhận để rollback trong giai đoạn chuyển đổi. Không thay đổi đồng thời GraalVM version, builder image và optimization flags nếu mục tiêu của đợt migration là kiểm chứng việc chuyển Spring Native sang Spring Boot AOT.

## 19. Bài thực hành: chuyển ứng dụng Spring Native 0.12.x sang Spring Boot AOT

**Bối cảnh:** Một REST service dùng Spring Boot 2.7.x, Spring Native 0.12.2, Maven và một TypeHint cho DTO được deserialize qua HTTP client.

**Các bước:**

1. Lưu dependency tree, native build output và test baseline của ứng dụng cũ.
2. Nâng ứng dụng lên Spring Boot 2.7 maintenance phù hợp trước khi chuyển major version.
3. Nâng Java lên 17 và kiểm tra dependency tương thích với Jakarta EE.
4. Nâng Spring Boot lên release line 3.x đã chọn và xử lý các thay đổi javax/jakarta.
5. Xóa dependency org.springframework.experimental:spring-native.
6. Xóa plugin spring-aot-maven-plugin và các goal generate/test-generate.
7. Khai báo Spring Boot Maven plugin và Native Build Tools Maven plugin.
8. Chuyển TypeHint cho DTO sang RegisterReflectionForBinding nếu mục đích là JSON binding.
9. Chuyển custom reflection/resource/proxy hint sang RuntimeHintsRegistrar.
10. Chạy JVM tests, AOT-processed JVM và native compilation.
11. Gửi request tới native executable để xác nhận DTO binding, HTTP client và business behavior.
12. Chạy native tests, đóng gói container và xác minh artifact có thể triển khai.
13. So sánh startup, RSS, container size và latency với baseline cũ.

**Tiêu chí đạt:**

- Không còn dependency hoặc plugin Spring Native thử nghiệm.
- Build pipeline dùng Spring Boot AOT tích hợp.
- Runtime hints được chuyển theo đúng mục đích, không đăng ký reflection quá rộng.
- Jakarta và dependency tương thích với Spring Boot version đích.
- AOT-processed JVM khởi động thành công.
- Native executable xử lý được các luồng HTTP/serialization quan trọng.
- Native tests và container smoke tests pass.
- Build metadata ghi rõ Spring Boot, GraalVM, Native Build Tools và builder version.
- Có artifact cũ và quy trình rollback trong thời gian rollout.

## 20. Tổng kết

Spring Native 0.12.x là dự án thử nghiệm đã được thay thế bởi native support chính thức trong Spring Boot 3. Khi migration, hãy bỏ dependency spring-native, plugin spring-aot-maven-plugin hoặc Gradle plugin thử nghiệm, rồi chuyển sang Spring Boot AOT cùng GraalVM Native Build Tools.

Phần cần review kỹ là Runtime Hints: chuyển TypeHint theo mục đích binding hoặc reflection, chuyển NativeHint/NativeConfiguration sang RuntimeHintsRegistrar, giữ lại JSON metadata còn cần và kiểm tra thư viện bên thứ ba. Đồng thời xử lý Java 17, Jakarta EE và các thay đổi Spring Boot 3. Kiểm thử theo thứ tự JVM, AOT-processed JVM, native tests và native executable sẽ giúp phát hiện lỗi sớm trước khi phát hành artifact mới.

## Tài liệu tham khảo

- [From Spring Native to Spring Boot 3](https://spring.io/blog/2023/02/23/from-spring-native-to-spring-boot-3/)
- [Spring Native 0.12.x Reference Documentation](https://docs.spring.io/spring-native/docs/0.12.x/reference/htmlsingle/)
- [Spring Boot — Ahead-of-Time Processing with Maven](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot — Ahead-of-Time Processing with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/aot.html)
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/3.4/how-to/native-image/testing-native-applications.html)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)

