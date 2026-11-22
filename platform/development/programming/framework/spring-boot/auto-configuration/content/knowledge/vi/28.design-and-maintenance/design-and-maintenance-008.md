# Rà soát thay đổi dependency để phát hiện kích hoạt tính năng ngoài dự kiến

## 1. Vì sao thêm một thư viện có thể làm ứng dụng đổi hành vi?

Trong Spring Boot, dependency không chỉ cung cấp class để code gọi trực tiếp. Các JAR trên runtime classpath còn có thể làm Spring Boot phát hiện thêm auto-configuration, thỏa điều kiện của cấu hình đã có, đăng ký bean mới hoặc khiến một cấu hình khác tự rút lui.

Vì vậy, một thay đổi nhỏ trong `pom.xml`, `build.gradle` hoặc BOM có thể làm ứng dụng thay đổi hành vi dù không có dòng Java nào được sửa.

Ví dụ:

- Thêm JDBC starter và H2 có thể làm Spring Boot tự cấu hình embedded `DataSource` khi chưa có `DataSource` do ứng dụng cung cấp.
- Thêm Web MVC starter có thể làm ứng dụng trở thành servlet web application và kích hoạt cấu hình MVC cùng embedded web server.
- Thêm Spring Security vào một ứng dụng web có thể kích hoạt security auto-configuration và cấu hình bảo vệ mặc định nếu ứng dụng chưa khai báo `SecurityFilterChain` riêng.
- Thêm Actuator có thể đăng ký management infrastructure và các endpoint tương ứng; việc endpoint nào được expose ra HTTP vẫn phụ thuộc cấu hình exposure.
- Thêm một thư viện có registry hoặc driver riêng có thể kích hoạt tích hợp metrics, database, messaging hoặc serialization nếu các điều kiện liên quan cùng match.

Điều cần rà soát là **tác động hành vi của dependency graph đã được resolve**, không chỉ danh sách dependency trực tiếp mà developer vừa thêm.

## 2. Hai cơ chế khiến dependency mới kích hoạt auto-configuration

### 2.1. JAR mới làm xuất hiện auto-configuration candidate

Một JAR có thể chứa resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File này liệt kê các auto-configuration class mà Spring Boot có thể xem xét. Khi dependency chứa file đó được thêm vào ứng dụng, các class cấu hình của thư viện có thể trở thành candidate trong quá trình khởi động.

Ví dụ resource của một thư viện:

~~~text
com.example.search.autoconfigure.SearchClientAutoConfiguration
com.example.search.autoconfigure.SearchMetricsAutoConfiguration
~~~

Spring Boot tìm resource này trong các JAR trên classpath. Mỗi class được khai báo có thể được áp dụng nếu các điều kiện của nó thỏa mãn.

Vì thế, thêm một starter có thể thay đổi cả tập auto-configuration candidate, dù ứng dụng không trực tiếp import class cấu hình đó.

### 2.2. JAR mới làm thỏa điều kiện của auto-configuration đã có

Một auto-configuration đã có trong ứng dụng có thể trước đây không match vì thiếu class, bean hoặc property. Khi dependency mới được thêm, điều kiện đó có thể chuyển từ false sang true.

Các điều kiện thường gặp:

| Điều kiện | Điều Spring Boot kiểm tra | Tác động của dependency |
|---|---|---|
| `@ConditionalOnClass` | Class được chỉ định có trên classpath không | JAR mới có thể cung cấp class còn thiếu |
| `@ConditionalOnMissingClass` | Class được chỉ định có vắng mặt không | Thêm JAR có thể làm cấu hình ngừng match |
| `@ConditionalOnBean` | Bean phù hợp đã được đăng ký chưa | Một integration có thể tạo bean mà cấu hình khác cần |
| `@ConditionalOnMissingBean` | Bean phù hợp chưa tồn tại | Bean mới từ thư viện khác có thể khiến default bean back off |
| `@ConditionalOnProperty` | Property có tồn tại và có giá trị phù hợp không | Dependency mới có thể mang theo cấu hình/default property hoặc làm lộ ra cấu hình đã có |
| `@ConditionalOnResource` | Resource cụ thể có tồn tại không | JAR mới có thể bổ sung resource làm điều kiện match |
| `@ConditionalOnWebApplication` | Context có phải web application không | Web starter có thể làm điều kiện web match |

Điểm quan trọng: **có class trên classpath không đồng nghĩa mọi bean của thư viện đó đều được tạo**. Auto-configuration còn có thể phụ thuộc bean, property, resource, loại application context, thứ tự cấu hình và điều kiện loại trừ.

### 2.3. Điều kiện match có thể làm cấu hình khác back off

Giả sử auto-configuration A tạo `SearchClient` nếu chưa có bean cùng kiểu. Một dependency mới đưa auto-configuration B vào context; B tạo `SearchClient` trước. Khi A được đánh giá, `@ConditionalOnMissingBean(SearchClient.class)` có thể không còn match.

Kết quả có thể là:

- Một bean mới xuất hiện.
- Một bean mặc định biến mất vì back off.
- Một implementation khác được sử dụng.
- Thứ tự hoặc cách khởi tạo integration thay đổi.

Do đó, khi rà soát thay đổi dependency, cần so sánh cả positive matches lẫn negative matches trong condition report.

## 3. Những thay đổi dependency cần đưa vào phạm vi review

Không chỉ review dòng dependency mới. Các thay đổi sau đều có thể tác động tới runtime:

1. **Thêm dependency trực tiếp:** thêm starter, driver, client hoặc integration.
2. **Thêm dependency bắc cầu:** một thư viện được nâng version và kéo thêm JAR mới.
3. **Nâng version:** phiên bản mới bổ sung class, auto-configuration imports, default property hoặc thay đổi condition.
4. **Thay starter:** starter mới có thể kéo theo một nhóm integration khác.
5. **Xóa hoặc exclude dependency:** class có thể biến mất, làm một auto-configuration không còn match hoặc làm code chuyển sang fallback.
6. **Thay BOM hoặc dependency constraint:** nhiều dependency được resolve sang version khác dù build file của module không đổi.
7. **Đổi scope/configuration:** thư viện chuyển từ test sang runtime, từ provided sang runtime, hoặc từ compileOnly sang implementation.
8. **Thay packaging hoặc deployment:** executable JAR, WAR, container hoặc application server có thể đưa thêm JAR ngoài dependency graph của module.
9. **Thay version plugin/build tool:** cách resolve variant, metadata hoặc dependency graph có thể thay đổi.
10. **Thay dependency lock:** các version bắc cầu được chọn có thể thay đổi dù khai báo trực tiếp không đổi.

Một pull request chỉ sửa version của một starter vẫn cần được xem như một thay đổi hành vi tiềm năng.

## 4. Ví dụ các tính năng có thể được kích hoạt ngoài dự kiến

| Dependency hoặc thay đổi | Tính năng có thể được kích hoạt | Điều kiện cần kiểm tra |
|---|---|---|
| JDBC starter + H2/HSQLDB | Embedded `DataSource` | Driver có trên classpath, không có `DataSource`/URL cấu hình khác phù hợp |
| Web MVC starter | MVC infrastructure và embedded web server | Servlet web context, classpath và các bean do ứng dụng cung cấp |
| Spring Security starter trong web app | Security filter chain mặc định | Không có cấu hình security do ứng dụng cung cấp |
| Actuator starter | Management/endpoint infrastructure | Endpoint có enabled và exposure theo cấu hình |
| Metrics registry | Registry/exporter cho hệ thống metrics | Micrometer và registry class có trên classpath, điều kiện cấu hình tương ứng |
| Mail starter | `JavaMailSender` infrastructure | Mail classes có trên classpath và auto-configuration match |
| Messaging client/starter | Connection factory, listener hoặc template | Client library, property và broker-related conditions |
| Validation provider | Validator infrastructure | Validation API/provider có trên classpath |

Các ví dụ mô tả khả năng theo điều kiện Spring Boot. Kết quả chính xác phụ thuộc dòng Boot, version dependency, property và các bean hiện có. Không kết luận một tính năng chắc chắn được bật chỉ từ tên starter.

### 4.1. Tình huống embedded database

Một ứng dụng ban đầu không có JDBC driver embedded. Sau khi thêm H2 để chạy một tiện ích nhỏ, Spring Boot có thể phát hiện H2 trên classpath. Nếu ứng dụng cũng có JDBC infrastructure và không cung cấp `DataSource` riêng, embedded database auto-configuration có thể tạo một `DataSource` trong bộ nhớ.

Điều này có thể làm ứng dụng khởi động thành công với database rỗng trong khi developer tưởng rằng ứng dụng đang kết nối tới database bên ngoài. Nếu property URL hoặc profile bị thiếu, embedded database có thể che giấu lỗi cấu hình môi trường.

Cần kiểm tra:

- `DataSource` bean thực tế được tạo từ loại database nào.
- JDBC URL hiệu lực.
- Profile và property source đang được sử dụng.
- Driver class và JAR runtime.
- Condition report của `DataSourceAutoConfiguration` và các cấu hình database liên quan.

Không chỉ kiểm tra rằng ứng dụng có một bean `DataSource`; phải kiểm tra bean đó trỏ tới database nào.

### 4.2. Tình huống thêm Security starter

Một ứng dụng MVC trước đây không có Spring Security. Khi thêm Security starter, classpath có thêm security classes và security auto-configuration có thể match.

Nếu ứng dụng chưa khai báo `SecurityFilterChain` riêng, cấu hình mặc định có thể thay đổi cách request được xử lý, yêu cầu xác thực hoặc ảnh hưởng test controller.

Review cần xác định:

- Security auto-configuration có match không.
- Có bao nhiêu `SecurityFilterChain` bean.
- Cấu hình mặc định có được tạo hay user configuration đã thay thế nó.
- Các endpoint health, actuator, API nội bộ và static resources có quy tắc truy cập mong muốn không.
- Integration test có còn kiểm tra đúng hành vi bảo mật không.

### 4.3. Tình huống thêm Actuator

Actuator starter có thể bổ sung management infrastructure và endpoint beans. Tuy nhiên, endpoint được tạo, được enable và được expose trên HTTP là các khái niệm khác nhau.

Không suy luận rằng thêm Actuator đồng nghĩa mọi endpoint đều công khai. Hãy kiểm tra:

- Endpoint nào được enable.
- Endpoint nào được expose qua web hoặc JMX.
- Management port/context có tách biệt không.
- Security rules bảo vệ endpoint ra sao.
- Cấu hình production có khác local/staging không.


## 5. Tạo regression test cho tính năng được kích hoạt bởi classpath

Khi một dependency có thể kích hoạt auto-configuration ngoài dự kiến, hãy viết test chứng minh hành vi ở cả hai trạng thái: class có mặt và class vắng mặt.

Ví dụ dưới đây dùng H2 làm class tùy chọn. Auto-configuration tạo một bean marker khi H2 driver có trên classpath. Marker giúp test tập trung vào điều kiện classpath; trong ứng dụng thật, bean integration có thể là service hoặc adapter sử dụng thư viện đó.

### 5.1. Auto-configuration mẫu

Tệp `src/main/java/com/example/demo/OptionalH2AutoConfiguration.java`:

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalH2AutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.h2.Driver")
    static class H2Configuration {

        @Bean
        @ConditionalOnMissingBean
        EmbeddedDatabaseCapability embeddedDatabaseCapability() {
            return new EmbeddedDatabaseCapability();
        }
    }
}
~~~

Tệp `src/main/java/com/example/demo/EmbeddedDatabaseCapability.java`:

~~~java
package com.example.demo;

public final class EmbeddedDatabaseCapability {
}
~~~

Nested configuration giúp cô lập các method và kiểu phụ thuộc thư viện tùy chọn. Khi H2 không có mặt, Spring Boot có thể loại nested configuration dựa trên metadata condition trước khi cần xử lý các thành phần phụ thuộc H2.

### 5.2. Test hai trạng thái classpath

Tệp `src/test/java/com/example/demo/OptionalH2AutoConfigurationTests.java`:

~~~java
package com.example.demo;

import org.h2.Driver;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalH2AutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(OptionalH2AutoConfiguration.class)
                    );

    @Test
    void activatesWhenH2IsOnTheClasspath() {
        runner.run(context ->
                assertThat(context)
                        .hasSingleBean(EmbeddedDatabaseCapability.class)
        );
    }

    @Test
    void backsOffWhenH2IsNotOnTheClasspath() {
        runner.withClassLoader(new FilteredClassLoader(Driver.class))
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(EmbeddedDatabaseCapability.class)
                );
    }
}
~~~

Test dependency cần có H2 trên test classpath và Spring Boot test support. Với Maven dùng Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Với Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.h2database:h2'
}
~~~

Chạy test:

~~~bash
./mvnw -Dtest=OptionalH2AutoConfigurationTests test
~~~

Hoặc:

~~~bash
./gradlew test --tests com.example.demo.OptionalH2AutoConfigurationTests
~~~

Kết quả mong đợi: cả hai test pass. Khi H2 có mặt, bean marker xuất hiện; khi `FilteredClassLoader` ẩn H2 khỏi context classloader, bean không được tạo.

Đây là regression test cho classpath condition. Trong dự án thật, nên bổ sung test cho bean hoặc endpoint có tác động tới người dùng để chứng minh tính năng ngoài dự kiến đã được kiểm soát.

### 5.3. Kiểm tra property condition rõ ràng

Một điều kiện property có thể làm tính năng bật ngoài dự kiến nếu code dùng `@ConditionalOnProperty` mà không chỉ định `havingValue`.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "northstar.search", name = "enabled")
public class SearchAutoConfiguration {
}
~~~

Mặc định, `@ConditionalOnProperty` match khi property tồn tại và giá trị không bằng chuỗi `false` (không phân biệt chữ hoa/thường). Vì vậy, các giá trị như `yes` hoặc `on` cũng có thể match.

Nếu yêu cầu chỉ bật với boolean true, viết rõ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "northstar.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchAutoConfiguration {
}
~~~

`matchIfMissing` mặc định là false. Khi thiết kế feature flag, hãy quyết định rõ hành vi nếu property bị thiếu, thay vì để default ngầm định gây bất ngờ.


## 6. Chụp dependency graph trước và sau thay đổi

Điều kiện đầu tiên để phát hiện feature activation ngoài dự kiến là biết chính xác runtime classpath đã thay đổi ra sao.

### 6.1. Maven

Lưu dependency tree của baseline trước khi merge:

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose -DoutputFile=target/runtime-dependencies-before.txt
~~~

Sau khi thay đổi dependency:

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose -DoutputFile=target/runtime-dependencies-after.txt
~~~

So sánh hai file để tìm:

- Artifact mới xuất hiện.
- Artifact bị loại bỏ.
- Version được nâng hoặc hạ.
- Đường dependency bắc cầu mới.
- Version bị omitted do conflict mediation.
- Thay đổi scope giữa compile, runtime và test.

Để điều tra một thư viện cụ thể:

~~~bash
./mvnw dependency:tree -Dverbose -Dincludes=com.h2database:h2
~~~

Xem POM sau khi áp dụng parent và BOM:

~~~bash
./mvnw help:effective-pom
~~~

`dependency:analyze` có thể hỗ trợ phát hiện dependency khai báo nhưng không dùng hoặc dependency được dùng gián tiếp mà chưa khai báo trực tiếp. Kết quả cần review vì reflection, annotation scanning, ServiceLoader và framework integration có thể khiến công cụ không nhìn thấy mọi cách sử dụng.

### 6.2. Gradle

Lưu đồ dependency runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Điều tra một artifact:

~~~bash
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
~~~

So sánh cả compile và runtime:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu feature chỉ xuất hiện trong test:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency h2 --configuration testRuntimeClasspath
~~~

`dependencies` cho thấy đồ thị đã resolve. `dependencyInsight` giải thích nguồn yêu cầu và lý do version được chọn, chẳng hạn conflict resolution, constraint hoặc rule.

### 6.3. Không chỉ so sánh dependency trực tiếp

Ví dụ build file chỉ thay:

~~~groovy
implementation 'com.example:report-client:4.1'
~~~

nhưng version mới của `report-client` kéo thêm:

~~~text
com.example:report-client:4.1
  |-- com.example:report-core:4.1
  |-- org.springframework:spring-context-support:...
  |-- com.example:metrics-exporter:...
  |-- com.h2database:h2:...
~~~

Những dependency bắc cầu này có thể bổ sung class hoặc auto-configuration candidate. Review chỉ nhìn một dòng `report-client` sẽ bỏ sót thay đổi thực tế.

### 6.4. Xác định thay đổi từ dependency metadata

Ngoài tọa độ artifact và version, kiểm tra nội dung JAR mới:

- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`
- `META-INF/spring.factories` đối với extension point còn sử dụng cơ chế này
- `META-INF/spring-configuration-metadata.json`
- `META-INF/services/`
- Các class mới có thể thỏa `@ConditionalOnClass`
- Resource được kiểm tra bởi `@ConditionalOnResource`

Một thư viện có thể thêm auto-configuration imports file trong bản nâng cấp, khiến candidate mới được phát hiện ngay cả khi ứng dụng không thay đổi component scan.

## 7. Đọc condition evaluation report để biết tính năng nào thực sự match

Dependency tree cho biết những JAR nào có mặt. Nó không cho biết auto-configuration nào cuối cùng được áp dụng. Để xác nhận tác động ở tầng Spring context, so sánh condition evaluation report trước và sau thay đổi.

### 7.1. Bật report khi khởi động

Chạy ứng dụng với:

~~~bash
java -jar application.jar --debug
~~~

Spring Boot ghi condition evaluation report ra log. Tìm:

- **Positive matches:** auto-configuration và condition đã match.
- **Negative matches:** cấu hình không match cùng lý do.
- **Exclusions:** auto-configuration đã bị loại.
- **Unconditional classes:** các cấu hình không phụ thuộc condition thông thường.

Chụp report ở baseline và sau khi thay dependency. Một auto-configuration mới trong positive matches là tín hiệu cần review, nhưng phải đọc lý do cụ thể trước khi kết luận đó là lỗi.

### 7.2. Dùng Actuator conditions endpoint

Nếu ứng dụng có Actuator, endpoint `conditions` cung cấp condition evaluation report dưới dạng dữ liệu có cấu trúc.

Ví dụ đường dẫn thường dùng:

~~~text
/actuator/conditions
~~~

Endpoint cần được enable/expose theo cấu hình Actuator và phải được bảo vệ bằng security policy phù hợp. Không expose report nội bộ công khai chỉ để tiện debug; report có thể tiết lộ class, property và cấu hình của ứng dụng.

### 7.3. So sánh bean definitions và hành vi

Một condition match không nhất thiết tạo bean mới: auto-configuration có thể back off ở một method khác hoặc bean có thể được thay thế bởi cấu hình người dùng.

Sau khi phát hiện positive match mới, xác nhận:

1. Bean nào thực sự được đăng ký.
2. Bean được tạo bởi class/method cấu hình nào.
3. Bean có bị `@ConditionalOnMissingBean` hoặc cấu hình khác làm back off không.
4. Property nào điều khiển feature.
5. Endpoint, filter, listener, scheduler hoặc client nào thực sự được khởi tạo.
6. Tính năng có tạo kết nối mạng, thread, consumer hoặc side effect khi startup không.

Không dừng ở câu hỏi "auto-configuration có match không?". Câu hỏi cuối cùng là "ứng dụng đã thay đổi hành vi nào?".

## 8. Kiểm tra theo môi trường và configuration

Cùng một dependency graph có thể tạo hành vi khác nhau theo profile, property và loại context.

### 8.1. So sánh property hiệu lực

Kiểm tra các nguồn:

- `application.properties` và `application.yml`.
- Profile-specific config.
- Environment variables.
- Command-line arguments.
- Config server hoặc Kubernetes ConfigMap/Secret.
- `@PropertySource` và custom `EnvironmentPostProcessor`.

Một dependency mới có thể làm property trước đây không được sử dụng trở thành property điều khiển auto-configuration. Vì vậy, cần so sánh giá trị property hiệu lực, không chỉ tìm tên property trong source.

### 8.2. Kiểm tra đúng classpath của từng môi trường

Tối thiểu so sánh:

| Môi trường | Classpath cần xem |
|---|---|
| Local development | `runtimeClasspath` hoặc lệnh chạy local |
| Unit/slice tests | `testRuntimeClasspath` |
| Integration tests | Configuration của integration test |
| Executable JAR | `BOOT-INF/lib/` trong artifact |
| WAR/application server | `WEB-INF/lib/` và shared libraries của server |
| Container/Kubernetes | Image digest, JAR thực tế và mount/runtime configuration |

Không dùng dependency tree local để kết luận runtime production có cùng JAR. Application server, plugin, mounted library hoặc image cũ có thể làm classpath thực tế khác.

### 8.3. Chú ý khác biệt do scope

Maven `test` dependency không đi vào production runtime, nhưng có thể làm test slice kích hoạt auto-configuration mà production không có.

Gradle `testImplementation` cũng chỉ dành cho test configurations. Một test có thể xanh nhờ H2 hoặc mock server trên test classpath trong khi runtime production không có dependency tương ứng.

Ngược lại, `runtimeOnly` có thể thêm driver hoặc provider vào runtime dù source code không import trực tiếp class đó. Đây là một lý do cần review runtime graph thay vì chỉ compile graph.


## 9. Kiểm soát dependency để tránh feature activation ngoài ý muốn

### 9.1. Chọn starter theo chức năng thực sự cần

Starter thường gom nhiều dependency liên quan để ứng dụng dễ bắt đầu. Điều đó thuận tiện, nhưng cũng có thể kéo theo tích hợp mà ứng dụng không cần.

Khi review starter:

- Đọc POM hoặc module metadata để biết các dependency bắc cầu.
- Kiểm tra runtime classpath sau khi resolve.
- Ưu tiên starter nhỏ theo đúng chức năng.
- Không thêm starter lớn chỉ để lấy một class tiện ích.
- Nếu chỉ cần một API, cân nhắc khai báo module tương ứng thay vì toàn bộ starter.
- Kiểm tra release notes khi starter đổi version hoặc thay tập dependency.

Không phải lúc nào thay starter bằng một dependency đơn cũng đúng: starter có thể cung cấp auto-configuration, version alignment và các thư viện hỗ trợ cần thiết. So sánh hành vi và test trước khi thu gọn.

### 9.2. Thiết kế library với dependency tùy chọn

Nếu đang phát triển thư viện dùng bởi nhiều ứng dụng, tránh kéo mọi integration vào consumer chỉ vì một thư viện core.

Một cấu trúc thường dễ kiểm soát:

~~~text
northstar-core
northstar-autoconfigure
northstar-starter
northstar-h2-integration
northstar-mail-integration
northstar-metrics-integration
~~~

Tách integration theo công nghệ để consumer chỉ thêm phần cần dùng. Trong Maven, dependency của một integration không bắt buộc có thể được khai báo `optional` trong module autoconfigure; consumer cần tính năng đó sẽ khai báo starter/integration tương ứng.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <optional>true</optional>
</dependency>
~~~

Dependency optional không tự truyền sang consumer như một transitive dependency thông thường. Consumer muốn dùng integration H2 phải thêm dependency cần thiết một cách tường minh.

Trong Gradle, thiết kế publication/variant và cấu hình dependency cần được chọn theo mục tiêu API/runtime của library; không coi `compileOnly` là phép thay thế phổ quát cho Maven optional. Kiểm tra metadata được publish và tạo consumer sample để xác nhận dependency nào thực sự được truyền xuống.

### 9.3. Dùng property để bật tính năng một cách chủ động

Nếu integration có side effect hoặc tạo kết nối ra ngoài, có thể yêu cầu property tường minh:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.search.SearchClient")
@ConditionalOnProperty(
        prefix = "northstar.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchAutoConfiguration {
}
~~~

Cách này yêu cầu đồng thời thư viện có trên classpath và property được bật rõ ràng. Việc thêm JAR không tự bật feature.

Dùng property condition khi đây là lựa chọn sản phẩm hợp lý. Không thêm cờ cấu hình cho mọi bean đơn giản; điều kiện thừa làm tăng độ phức tạp và có thể che giấu dependency không cần thiết.

### 9.4. Exclude auto-configuration có mục tiêu

Nếu một auto-configuration không bao giờ được phép chạy trong ứng dụng, có thể exclude bằng class hoặc tên class trong `@SpringBootApplication`, hoặc bằng property `spring.autoconfigure.exclude`.

Ví dụ dùng tên class:

~~~java
@SpringBootApplication(
        excludeName = "com.example.search.autoconfigure.SearchClientAutoConfiguration"
)
public class Application {
}
~~~

Tên class phải là auto-configuration candidate thực tế trong đúng version dependency. Exclude chỉ ngăn cấu hình đó được áp dụng; nó không loại JAR khỏi classpath và không sửa dependency graph.

Trước khi exclude, xác định vì sao dependency được kéo vào. Nếu ứng dụng không cần integration đó, loại dependency hoặc sửa starter có thể là cách kiểm soát đúng hơn. Chỉ exclude khi cần giữ JAR vì chức năng khác hoặc có lý do kiến trúc rõ ràng.

## 10. Giữ dependency graph ổn định và có thể tái lập

### 10.1. Dùng Spring Boot BOM

Mỗi release Spring Boot cung cấp BOM `spring-boot-dependencies` chứa một tập version được quản lý và kiểm thử cùng nhau.

- Dùng Spring Boot parent hoặc import BOM trong Maven.
- Dùng Spring Boot Gradle plugin/dependency management plugin hoặc Gradle platform.
- Hạn chế override version của thư viện nền tảng nếu không có lý do.
- Kiểm tra riêng thư viện không thuộc BOM, ví dụ Spring Cloud hoặc SDK của nhà cung cấp.
- Khi override version, ghi rõ lý do và thêm test tương ứng.

BOM không đảm bảo không có auto-configuration mới: một version thư viện được BOM nâng có thể thêm class hoặc metadata. Vì vậy, thay BOM cũng cần dependency diff và condition report.

### 10.2. Tránh version động trong build phát hành

Các khai báo như `1.+`, `latest.release` hoặc version range rộng có thể làm version resolve thay đổi theo thời gian dù source code không đổi.

Trong pipeline release:

- Dùng version rõ ràng.
- Review BOM/version catalog thay đổi như một phần của code review.
- Không để build production tự động lấy latest mà không có bước kiểm soát.
- Ghi lại resolved dependency graph cùng artifact build.

### 10.3. Dùng Gradle dependency locking

Gradle hỗ trợ dependency locking để lưu version đã resolve cho các configuration được khóa.

Ví dụ:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo/cập nhật lock state khi chủ động chấp nhận thay đổi dependency:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit lock file cùng thay đổi build. Khi dependency graph thay đổi, diff lock file giúp reviewer nhìn thấy version bắc cầu nào đã đổi.

Locking giúp build tái lập; nó không xác nhận các version đã khóa an toàn hoặc tương thích. Vẫn cần test và review condition report.

### 10.4. Dùng Maven Enforcer hoặc kiểm tra dependency tree

Maven có thể dùng Enforcer rules để phát hiện dependency convergence hoặc version policy không phù hợp. `dependency:tree -Dverbose` vẫn là công cụ quan trọng để hiểu đường dependency và version bị mediation.

Không bật một rule quá chặt mà không hiểu các ngoại lệ hợp lệ trong graph. Mục tiêu là phát hiện version conflict có rủi ro, không buộc mọi dependency bắc cầu phải có một version duy nhất khi thư viện được thiết kế để cách ly chúng.

## 11. Quy trình review dependency change trong pull request

Áp dụng cùng một trình tự cho thêm, xóa hoặc nâng version dependency.

1. **Ghi rõ mục đích:** dependency mới phục vụ tính năng nào, module nào cần nó và tại sao cần runtime scope.
2. **Chụp baseline:** lưu dependency tree của runtime và test trước thay đổi.
3. **Review diff:** xác định artifact mới/xóa/đổi version, dependency bắc cầu và scope thay đổi.
4. **Đọc metadata JAR:** kiểm tra auto-configuration imports, service loader và resource mới nếu integration có thể tự đăng ký.
5. **Dự đoán condition:** tìm `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnProperty` và các cấu hình liên quan.
6. **So sánh condition report:** chạy cùng profile/property trước và sau thay đổi; điều tra positive/negative match mới.
7. **So sánh bean behavior:** kiểm tra bean, filter, listener, scheduler, client, endpoint và connection được tạo.
8. **Kiểm thử hai trạng thái:** feature dependency có mặt và vắng mặt; property bật và tắt; user bean override nếu có.
9. **Kiểm tra packaging:** xác minh JAR/WAR/container chứa đúng dependency.
10. **Ghi quyết định:** dependency được chấp nhận, bị thu hẹp, exclude hoặc yêu cầu property opt-in; ghi lý do trong PR.
11. **Khóa version:** cập nhật BOM, version catalog hoặc lock file có chủ đích.
12. **Chạy regression:** unit, slice, integration và smoke test bằng artifact đã đóng gói.

Một pull request nên trả lời được câu hỏi: "Dependency này làm những auto-configuration và bean nào thay đổi so với baseline?"

## 12. Các lỗi thường gặp khi rà soát

1. **Chỉ nhìn dependency trực tiếp.** Feature có thể được kích hoạt bởi dependency bắc cầu.
2. **Chỉ nhìn compile classpath.** Auto-configuration trong production phụ thuộc runtime classpath thực tế.
3. **Cho rằng thêm class là auto-configuration chắc chắn match.** Các condition khác như bean, property và context vẫn có thể không đạt.
4. **Chỉ so sánh positive matches.** Một dependency mới có thể khiến cấu hình cũ back off hoặc chuyển sang negative match.
5. **Cho rằng Actuator starter làm mọi endpoint công khai.** Enablement, exposure và security là các lớp cấu hình riêng.
6. **Dùng `@ConditionalOnProperty` mà không chỉ rõ `havingValue`.** Giá trị tồn tại và khác `false` có thể match; dùng `havingValue="true"` nếu cần true rõ ràng.
7. **Đưa driver/test library vào runtime ngoài ý muốn.** Scope sai có thể kích hoạt auto-configuration trong production.
8. **Exclude để che dependency không cần thiết.** Cấu hình bị tắt nhưng JAR và các integration khác vẫn còn trên classpath.
9. **Nâng BOM mà không review graph.** Nhiều version bắc cầu có thể đổi dù build file module không sửa.
10. **Tin lock file đồng nghĩa dependency an toàn.** Locking chỉ làm version resolve ổn định, không kiểm tra hành vi.
11. **Chỉ test bằng `ApplicationContextRunner` với class đăng ký trực tiếp.** Cần consumer test nếu muốn xác nhận imports file và artifact publication.
12. **Không test profile production.** Profile hoặc property source khác có thể khiến cùng dependency graph tạo hành vi khác.

## 13. Checklist hoàn tất một lần rà soát

| Hạng mục | Tiêu chí đạt |
|---|---|
| Mục đích | Biết dependency mới phục vụ tính năng nào và scope nào cần thiết |
| Dependency graph | Đã so sánh runtime và test trước/sau |
| Transitives | Đã xác định dependency bắc cầu mới, bị xóa hoặc đổi version |
| Auto-configuration | Đã kiểm tra imports metadata và candidate mới |
| Conditions | Đã so sánh positive/negative matches cùng lý do |
| Beans | Đã xác minh bean mới, bean back off và cấu hình override |
| Properties | Đã kiểm tra property hiệu lực, default và profile |
| Side effects | Đã kiểm tra connection, thread, listener, scheduler và endpoint |
| Packaging | JAR/WAR/image chứa đúng dependency được duyệt |
| Scope | Không có test-only hoặc compile-only dependency lọt vào runtime |
| Stability | BOM/version catalog/lock file được cập nhật có chủ đích |
| Tests | Có regression test cho classpath/property state quan trọng |
| Review record | PR ghi rõ tính năng được kích hoạt và quyết định chấp nhận |

## 14. Ghi nhớ

- Spring Boot auto-configures dựa trên JAR dependency và các condition; thêm dependency có thể thay đổi cả candidate lẫn kết quả match.
- Một JAR có thể mang `AutoConfiguration.imports`, class để thỏa `@ConditionalOnClass`, bean hoặc resource cho các condition khác.
- Dependency mới cũng có thể làm cấu hình cũ back off qua `@ConditionalOnMissingBean`.
- Dependency tree cho biết graph đã resolve; condition report cho biết auto-configuration nào match và vì sao; bean inspection/test cho biết hành vi thực tế.
- Review cả runtime, test, artifact đóng gói và classpath của môi trường triển khai.
- Dùng BOM, lock file, dependency constraints và optional integration để kiểm soát thay đổi có chủ đích.
- Exclude chỉ ngăn auto-configuration được áp dụng; nó không xóa dependency khỏi classpath.
- Chỉ merge khi đã giải thích được tính năng nào thay đổi, lý do thay đổi và regression test bảo vệ hành vi đó.

### Tài liệu tham khảo chính thức

- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration và condition annotations: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Build Systems và dependency management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Spring Boot — Gradle dependency management và BOM: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
- Apache Maven — Introduction to the Dependency Mechanism, transitive/optional dependencies và exclusions: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
