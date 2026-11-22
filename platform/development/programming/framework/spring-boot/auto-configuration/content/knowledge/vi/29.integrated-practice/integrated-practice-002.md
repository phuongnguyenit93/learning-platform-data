# Thay đổi dependency và ghi nhận khác biệt trong bean cùng báo cáo điều kiện

Khi thêm hoặc bỏ một dependency trong Spring Boot, thay đổi không dừng ở danh sách JAR. Dependency mới có thể đưa thêm class vào runtime classpath; các auto-configuration dùng **@ConditionalOnClass**, **@ConditionalOnBean**, **@ConditionalOnProperty** hoặc **@ConditionalOnWebApplication** sẽ được đánh giá lại. Kết quả có thể là bean mới xuất hiện, bean mặc định back off, một configuration không còn được áp dụng hoặc ứng dụng khởi động thất bại vì thiếu dependency bắt buộc.

Một phép thực hành có thể giải thích được cần ghi nhận ba lớp bằng chứng:

1. **Dependency graph:** artifact trực tiếp và bắc cầu nào được thêm, bỏ, đổi version hoặc đổi scope?
2. **Bean inventory:** sau khi ApplicationContext refresh, những bean definition nào được đăng ký thêm, mất đi hoặc đổi type/factory method?
3. **Condition Evaluation Report:** condition nào chuyển từ **NO_MATCH** sang **MATCH**, hoặc ngược lại; message cho biết lý do gì?

Không suy ra bean thay đổi chỉ từ dependency tree. Dependency mới có thể không kích hoạt auto-configuration nào; ngược lại, một class đã có sẵn trong dependency bắc cầu có thể làm condition match dù POM không khai báo trực tiếp class đó.

## 1. Hiểu chuỗi tác động từ dependency đến bean

Spring Boot auto-configuration dựa trên classpath và Environment tại thời điểm khởi động. Một thay đổi dependency có thể tạo chuỗi:

```text
pom.xml thay đổi
      |
      v
Maven resolve dependency graph
      |
      v
Runtime classpath thay đổi
      |
      v
Auto-configuration candidates và class conditions thay đổi
      |
      v
Bean conditions / property conditions được đánh giá
      |
      v
Bean definitions trong ApplicationContext thay đổi
      |
      v
Ứng dụng có thể có hành vi hoặc lỗi khởi động khác
```

Ví dụ, thêm **spring-boot-starter-actuator** đưa Actuator API và auto-configuration vào classpath. Spring Boot có thể đăng ký thêm endpoint infrastructure như health và condition report. Một cấu hình riêng của ứng dụng dùng **@ConditionalOnClass** để tích hợp với **HealthEndpoint** cũng có thể bắt đầu match.

Ngược lại, bỏ một thư viện tùy chọn có thể khiến các auto-configuration phụ thuộc thư viện đó không còn được nạp. Nếu code ứng dụng vẫn tham chiếu trực tiếp class đã bị bỏ, lỗi có thể xảy ra trước hoặc trong lúc refresh context. Vì vậy phải đọc cả dependency diff, condition diff và bean diff.

## 2. Phân biệt dependency trực tiếp, bắc cầu và classpath thực tế

Trong Maven:

- **Direct dependency:** khai báo trực tiếp trong phần dependencies của module.
- **Transitive dependency:** được kéo vào bởi một dependency khác.
- **Dependency management:** quản lý version và metadata; tự nó không nhất thiết đưa artifact vào classpath.
- **Scope:** quyết định dependency có mặt ở compile, test hay runtime.
- **Optional dependency:** không tự động truyền tiếp tới consumer theo cách dependency thông thường.
- **Exclusion:** loại một dependency bắc cầu khỏi nhánh resolve cụ thể.

Lệnh **mvn dependency:tree** hiển thị cây dependency đã được Maven resolve cho lần build đó. Cây này giúp thấy nguồn kéo một artifact vào, version được chọn và nhánh nào tạo ra dependency. Khi điều tra xung đột version, có thể thêm **-Dverbose** để thấy cả những node bị loại do conflict mediation.

Lưu ý: một dependency có mặt trong cây chưa chắc sẽ tạo bean. Spring Boot chỉ đăng ký bean nếu các điều kiện tương ứng match. Một dependency cũng có thể chỉ cung cấp API được code gọi trực tiếp, không có auto-configuration nào liên quan.

## 3. Thiết kế thí nghiệm trước/sau chỉ thay một dependency

Ta dùng một ứng dụng Java 17 / Spring Boot 3.3.5 có dependency nền là **spring-boot-starter**. Bản baseline không có Actuator. Bản thứ hai bật Maven profile **with-actuator**, profile này chỉ thêm **spring-boot-starter-actuator**.

Giữ nguyên giữa hai lần build:

- Source code và commit.
- Spring Boot parent/version và Java version.
- Profile mặc định, properties, environment variables và command-line arguments.
- Cấu hình ứng dụng và cách chạy JAR.
- Cùng lệnh tạo dependency tree và bean/condition snapshot.

Biến duy nhất của thí nghiệm là profile Maven có thêm Actuator. Vì hai artifact dùng cùng source, khác biệt trong bean inventory và report có thể liên hệ trực tiếp với dependency được thêm vào.

### 3.1. Cấu trúc dự án

```text
dependency-audit-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DependencyAuditApplication.java
```

Nội dung **pom.xml**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>dependency-audit-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <profiles>
        <profile>
            <id>with-actuator</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-actuator</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Profile **with-actuator** bổ sung dependency mà không sửa source code. Không cần khai báo version riêng cho starter Actuator vì Spring Boot parent quản lý version đồng bộ với 3.3.5.

## 4. Ghi bean inventory và Condition Evaluation Report từ cùng một ứng dụng

Để so sánh công bằng, ta xuất hai snapshot bằng code chạy trong cả hai artifact. Cách này không cần Actuator endpoint nên baseline cũng có thể tạo condition report.

Chương trình sẽ:

- Lấy tên các bean definition từ **ConfigurableListableBeanFactory**.
- Ghi type metadata, factory bean và factory method mà không gọi **getBean()** cho từng bean.
- Đọc **ConditionEvaluationReport** do Spring Boot ghi trong quá trình xử lý auto-configuration.
- In từng condition source, kết quả **MATCH/NO_MATCH**, loại condition và message.

Tạo **src/main/java/demo/DependencyAuditApplication.java**:

```java
package demo;

import java.util.Arrays;
import java.util.Map;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(DependencyAuditApplication.OptionalActuatorConfiguration.class)
public class DependencyAuditApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DependencyAuditApplication.class, args)) {
            printBeanInventory(context);
            printConditionReport(context);
        }
    }

    private static void printBeanInventory(
            ConfigurableApplicationContext context) {

        ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();

        System.out.println("=== BEAN INVENTORY ===");

        Arrays.stream(beanFactory.getBeanDefinitionNames())
                .sorted()
                .forEach(beanName -> {
                    BeanDefinition definition =
                            beanFactory.getBeanDefinition(beanName);

                    System.out.printf(
                            "BEAN|%s|%s|%s|%s%n",
                            beanName,
                            definition.getResolvableType(),
                            valueOrDash(definition.getFactoryBeanName()),
                            valueOrDash(definition.getFactoryMethodName())
                    );
                });
    }

    private static void printConditionReport(
            ConfigurableApplicationContext context) {

        ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();
        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(beanFactory);

        System.out.println("=== CONDITION REPORT ===");

        report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    for (ConditionEvaluationReport.ConditionAndOutcome item
                            : entry.getValue()) {

                        ConditionOutcome outcome = item.getOutcome();
                        String message = String.valueOf(outcome.getMessage())
                                .replace('\r', ' ')
                                .replace('\n', ' ');

                        System.out.printf(
                                "CONDITION|%s|%s|%s|%s%n",
                                entry.getKey(),
                                outcome.isMatch() ? "MATCH" : "NO_MATCH",
                                item.getCondition().getClass().getSimpleName(),
                                message
                        );
                    }
                });

        report.getExclusions().stream()
                .sorted()
                .forEach(name -> System.out.println("EXCLUSION|" + name));
    }

    private static String valueOrDash(String value) {
        return value == null ? "-" : value;
    }

    public record ActuatorIntegrationMarker(String source) {
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "org.springframework.boot.actuate.health.HealthEndpoint"
    )
    static class OptionalActuatorConfiguration {

        @Bean
        ActuatorIntegrationMarker actuatorIntegrationMarker() {
            return new ActuatorIntegrationMarker("actuator-on-classpath");
        }
    }
}
```

### 4.1. Vì sao dùng @ConditionalOnClass(name = "...")?

**HealthEndpoint** chỉ có trong classpath sau khi thêm Actuator. Nếu import class này trực tiếp vào source, bản baseline sẽ không biên dịch vì dependency chưa có.

Dùng thuộc tính **name** với chuỗi class name cho phép điều kiện kiểm tra sự hiện diện của class mà không tạo compile-time reference. Cấu hình tùy chọn được đặt trong một nested **@Configuration** riêng để cô lập tham chiếu tới thư viện tùy chọn.

Khi baseline không có Actuator, **OptionalActuatorConfiguration** được đánh giá **NO_MATCH** và bean **actuatorIntegrationMarker** không được đăng ký. Khi profile **with-actuator** được bật, class có mặt trên classpath, condition chuyển sang **MATCH** và marker xuất hiện.

Đây là bean marker của thí nghiệm, giúp thấy rõ một classpath change tác động tới condition. Các bean Actuator thực tế cũng có thể xuất hiện trong inventory; tên và số lượng cụ thể phụ thuộc cấu hình, phiên bản và loại ứng dụng.

## 5. Build và lưu hai artifact cùng dependency tree

Chạy trong PowerShell tại thư mục **dependency-audit-lab**. Lưu artifact baseline trước khi build profile thứ hai để **mvn clean** không ghi đè file cần so sánh.

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null

# Baseline: không bật profile with-actuator
mvn clean package
mvn dependency:tree -DoutputFile=artifacts/dependencies-before.txt

Copy-Item target/dependency-audit-lab-1.0.0.jar artifacts/before.jar

java -jar artifacts/before.jar *> artifacts/before-report.txt

# Sau thay đổi: thêm spring-boot-starter-actuator
mvn -Pwith-actuator clean package
mvn -Pwith-actuator dependency:tree -DoutputFile=artifacts/dependencies-after.txt

Copy-Item target/dependency-audit-lab-1.0.0.jar artifacts/after.jar

java -jar artifacts/after.jar *> artifacts/after-report.txt
```

Ứng dụng mẫu không có web starter nên chạy ở chế độ non-web; sau khi in hai snapshot, process kết thúc. Nếu áp dụng cách này vào một ứng dụng web đang chạy server, hãy dùng một profile audit có **spring.main.web-application-type=none** khi điều đó phù hợp, hoặc lấy snapshot từ một lần khởi động riêng.

Kiểm tra môi trường trước khi kết luận:

```powershell
java -version
mvn -version
mvn -Pwith-actuator help:active-profiles
```

Nếu dùng profile Maven khác ngoài **with-actuator**, phải giữ nguyên profile đó ở cả hai lượt. Không để profile ứng dụng hoặc biến môi trường vô tình bật thêm cấu hình ở chỉ một artifact.

## 6. So sánh dependency tree

Dùng **Compare-Object** để xem những dòng được thêm hoặc mất:

```powershell
Compare-Object (Get-Content artifacts/dependencies-before.txt) (Get-Content artifacts/dependencies-after.txt)
```

**<=** là dòng chỉ có ở bản baseline; **=>** là dòng chỉ có ở bản sau. Với thí nghiệm thêm Actuator, dự kiến bản sau có thêm **spring-boot-starter-actuator**, **spring-boot-actuator**, **spring-boot-actuator-autoconfigure** và các dependency bắc cầu liên quan như Micrometer.

Danh sách thực tế phụ thuộc dependency management và version được Maven resolve. Đừng chép một danh sách dự kiến vào báo cáo như thể đó là kết quả đo. Hãy lưu nguyên dependency tree của hai lần chạy và đọc version được chọn trong output.

Nếu dependency tree khác ngoài phần Actuator dự kiến, điều tra trước khi tiếp tục. Ví dụ:

- Một dependency bắc cầu đổi version do conflict mediation.
- Profile khác kéo thêm driver hoặc adapter.
- Exclusion bị thêm/bỏ.
- Scope thay đổi khiến dependency xuất hiện hoặc biến mất ở runtime.

Có thể dùng **-Dverbose** khi cần xem các node bị Maven loại do xung đột version:

```powershell
mvn -Pwith-actuator dependency:tree -Dverbose -DoutputFile=artifacts/dependencies-after-verbose.txt
```

## 7. So sánh bean inventory

Mỗi dòng **BEAN|...** trong snapshot đại diện cho một bean definition. Lọc và so sánh:

```powershell
$beforeBeans = Get-Content artifacts/before-report.txt |
    Where-Object { $_.StartsWith("BEAN|") }

$afterBeans = Get-Content artifacts/after-report.txt |
    Where-Object { $_.StartsWith("BEAN|") }

Compare-Object $beforeBeans $afterBeans
```

Kết quả chỉ có ở bản sau thường có **=>**; dòng chỉ có ở baseline có **<=**. Với thí nghiệm này, hãy tìm:

- **actuatorIntegrationMarker:** chỉ xuất hiện khi Actuator có mặt.
- Các bean definition thuộc package Actuator.
- Bean hạ tầng mới mà auto-configuration của Actuator đăng ký.
- Bean có cùng tên nhưng metadata type/factory method thay đổi, nếu có.

Không chỉ so sánh tổng số bean. Hai bản có thể có cùng số lượng nhưng một bean mất đi và một bean khác được thêm vào. So sánh từng dòng giúp phát hiện thay đổi thay thế, không chỉ thay đổi số lượng.

Chương trình đọc metadata từ **BeanDefinition**, không gọi **getBean()** cho toàn bộ danh sách. Vì vậy inventory không chủ động khởi tạo các lazy bean chỉ để kiểm kê. **getResolvableType()** có thể chưa giải quyết đầy đủ ở một số definition; hãy dùng factory method, bean class và resource metadata khi cần truy nguyên nguồn đăng ký.

## 8. So sánh Condition Evaluation Report

Lọc các dòng condition và so sánh:

```powershell
$beforeConditions = Get-Content artifacts/before-report.txt |
    Where-Object { $_.StartsWith("CONDITION|") }

$afterConditions = Get-Content artifacts/after-report.txt |
    Where-Object { $_.StartsWith("CONDITION|") }

Compare-Object $beforeConditions $afterConditions
```

Để xem riêng condition marker của thí nghiệm:

```powershell
Get-Content artifacts/before-report.txt |
    Where-Object { $_ -like "*OptionalActuatorConfiguration*" }

Get-Content artifacts/after-report.txt |
    Where-Object { $_ -like "*OptionalActuatorConfiguration*" }
```

Dạng output minh họa:

```text
# Baseline: class HealthEndpoint không có trên classpath
CONDITION|demo.DependencyAuditApplication$OptionalActuatorConfiguration|NO_MATCH|OnClassCondition|...

# Có profile with-actuator
CONDITION|demo.DependencyAuditApplication$OptionalActuatorConfiguration|MATCH|OnClassCondition|...
```

Message cụ thể do Spring Boot tạo và có thể khác theo phiên bản. Điều quan trọng là đọc cả source, loại condition, trạng thái match và message. Ví dụ:

- **OnClassCondition:** class bắt buộc có hoặc không có trên classpath.
- **OnBeanCondition:** bean type/name đã tồn tại hay chưa tại thời điểm condition được đánh giá.
- **OnPropertyCondition:** property có giá trị phù hợp hay không.
- **OnWebApplicationCondition:** context có phải servlet/reactive web application không.

**MATCH** nghĩa là condition đó thỏa mãn. Nó không tự đảm bảo toàn bộ context sẽ khởi động thành công; một bean vẫn có thể thất bại khi khởi tạo vì dependency hoặc cấu hình khác. Với configuration có nhiều condition, cần đọc toàn bộ outcomes của source đó.

### 8.1. Report không phải danh sách tất cả auto-configuration có thể tồn tại

**ConditionEvaluationReport** ghi những condition thực sự được đánh giá. Khi dependency bị bỏ khỏi classpath, một auto-configuration class cũng có thể biến mất khỏi tập candidate; khi đó source tương ứng không nhất thiết xuất hiện dưới dạng **NO_MATCH**. Nó có thể hoàn toàn vắng khỏi report.

Đó là lý do phải đọc report cùng dependency tree. Dependency tree cho biết class/artifact nào có mặt; report cho biết những condition đã được đánh giá và kết quả. Bean inventory cho biết cuối cùng definition nào được đăng ký.

Trong ví dụ, **OptionalActuatorConfiguration** được import rõ ràng trong source ở cả hai bản. Vì vậy condition classpath của nó có thể cho thấy **NO_MATCH** ở baseline và **MATCH** sau khi thêm dependency. Đây là một tín hiệu minh họa có kiểm soát; auto-configuration bên trong thư viện có thể có hành vi candidate khác.

## 9. Đọc kết quả theo ba lớp bằng chứng

Sau khi có ba diff, lập bảng kết luận:

| Bằng chứng | Bản baseline | Bản có Actuator | Diễn giải |
| --- | --- | --- | --- |
| Dependency tree | Không có starter Actuator | Có starter và các dependency bắc cầu | Classpath đã thay đổi đúng theo thí nghiệm. |
| Condition marker | **NO_MATCH** vì thiếu HealthEndpoint | **MATCH** vì class đã có | Classpath condition chuyển trạng thái. |
| Bean marker | Không có actuatorIntegrationMarker | Có actuatorIntegrationMarker | Condition match đã dẫn đến bean definition mới. |
| Actuator infrastructure | Không có các bean thuộc Actuator | Có thêm các bean phù hợp với auto-configuration | Dependency mới kích hoạt các cấu hình có điều kiện tương ứng. |

Nếu dependency tree có thay đổi nhưng bean inventory không đổi, có thể dependency chỉ bổ sung class/library chưa được ứng dụng sử dụng hoặc condition không match. Đây vẫn là một kết quả hợp lệ; không nên cố tạo bean chỉ để chứng minh dependency có tác dụng.

Nếu condition chuyển sang **MATCH** nhưng bean không xuất hiện, kiểm tra condition trên bean method, **@ConditionalOnMissingBean**, tên bean, thứ tự auto-configuration và lỗi tạo bean. Nếu bean mới xuất hiện nhưng report không có condition tương ứng, có thể bean đến từ cấu hình không dùng Spring Boot condition, hoặc source condition nằm ở một phần report khác.

Nếu context fail trước khi in snapshot, giữ log startup và xem nguyên nhân. Một dependency bị loại có thể gây **NoClassDefFoundError**, **ClassNotFoundException**, **NoSuchMethodError** hoặc **BeanCreationException**; đó là bằng chứng runtime khác với một condition đơn giản không match.

## 10. Các cách lấy report khác trong ứng dụng thật

### 10.1. Dùng --debug

Spring Boot có thể in auto-configuration condition report khi khởi chạy với **--debug**:

```bash
java -jar target/application.jar --debug
```

Cách này nhanh khi cần điều tra một lần khởi động. Giữ cùng log level và debug setting giữa hai bản nếu dùng output đó để so sánh. Trong ví dụ thực hành, code gọi API trực tiếp để có dòng snapshot ổn định và dễ lọc bằng PowerShell.

### 10.2. Dùng ConditionEvaluationReportLoggingListener

Khi viết test với **ApplicationContextRunner**, có thể gắn listener để ghi report:

```java
ApplicationContextRunner runner = new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        );
```

**ConditionEvaluationReportLoggingListener** là **ApplicationContextInitializer** ghi report vào log. Không chia sẻ cùng một listener instance cho nhiều context; tạo initializer mới cho mỗi runner/context theo hướng dẫn API.

### 10.3. Dùng Actuator conditions và beans endpoint

Khi ứng dụng có Actuator và là web application, có thể dùng:

- **/actuator/conditions:** condition evaluation report.
- **/actuator/beans:** danh sách bean trong ApplicationContext.

Mặc định chỉ **health** được expose qua HTTP. Nếu cần xem hai endpoint trong môi trường local, có thể cấu hình:

```properties
management.endpoints.web.exposure.include=health,conditions,beans
```

Chỉ expose endpoint chẩn đoán trong môi trường kiểm soát và bảo vệ chúng bằng security/network policy phù hợp. Condition report và bean inventory có thể tiết lộ class, cấu hình và cấu trúc nội bộ của ứng dụng. Với baseline chưa có Actuator, API **ConditionEvaluationReport** trong ví dụ vẫn cho phép tạo report mà không phải thêm Actuator chỉ để quan sát.

## 11. Lưu ý khi thêm hoặc bỏ dependency

Một thay đổi dependency có thể tác động rộng hơn artifact được thêm trực tiếp:

- Thêm một starter thường kéo nhiều starter con và thư viện bắc cầu.
- Bỏ dependency trực tiếp chưa chắc loại được class nếu một dependency khác vẫn kéo nó vào.
- Exclusion chỉ loại dependency khỏi nhánh khai báo cụ thể; cùng artifact vẫn có thể xuất hiện qua nhánh khác.
- Dependency scope **test** có thể làm test pass nhưng ứng dụng đóng gói không có class ở runtime.
- Dependency **optional** của thư viện không tự động trở thành dependency bắt buộc cho consumer.
- BOM/parent có thể đổi version được resolve dù không sửa version tại dependency line.
- Auto-configuration có thể yêu cầu đồng thời classpath, bean, property và web context; chỉ thêm class chưa chắc đủ để bean xuất hiện.

Khi gỡ một dependency, hãy kiểm tra lại **dependency:tree** để xác nhận class thật sự biến mất. Nếu class còn được một dependency khác cung cấp, **@ConditionalOnClass** vẫn có thể match và bean vẫn tồn tại.

Khi thêm dependency cho starter/library, kiểm tra cả consumer thực tế. Một project test có dependency trong test scope không chứng minh ứng dụng dùng starter sẽ nhận được dependency đó ở runtime. Nếu library yêu cầu consumer tự thêm optional integration, tài liệu phải nêu rõ dependency cần khai báo.

## 12. Các lỗi thường gặp khi so sánh

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dependency tree khác nhiều hơn dự kiến | Profile, BOM, exclusion hoặc version mediation cũng thay đổi | So sánh POM/effective profile và giải thích từng nhánh bắc cầu. |
| Dependency có trong tree nhưng không có bean mới | Không có auto-configuration phù hợp hoặc condition không match | Đọc condition report và xác nhận bean có thực sự được thiết kế để tự đăng ký. |
| Bean mới xuất hiện nhưng không tìm thấy source condition | Bean đến từ cấu hình thông thường, import, scan hoặc source khác | Tìm bean definition resource/factory method; không quy mọi bean cho auto-configuration. |
| Condition MATCH nhưng bean không tồn tại | Condition khác trên method không match hoặc context refresh thất bại | Đọc mọi outcome của source và startup exception. |
| Bean mất sau khi bỏ dependency | Dependency cung cấp class hoặc bean infrastructure mà feature cần | Kiểm tra direct/transitive dependency và điều kiện class/bean. |
| Report không liệt kê auto-configuration đã bị bỏ | Class không còn là candidate để đánh giá | Đối chiếu dependency tree và AutoConfiguration.imports trong artifact. |
| Kết quả hai lần chạy khác dù POM giống nhau | Profile, property, environment, JDK hoặc cách chạy khác | Cố định toàn bộ đầu vào và lưu lệnh chạy. |
| Số bean bằng nhau nhưng bean khác | Một bean bị thay thế bởi bean khác | Diff từng dòng inventory, không chỉ so tổng số. |
| Actuator endpoint trả 404 | Endpoint chưa được expose hoặc ứng dụng không phải web application | Kiểm tra dependency, endpoint access/exposure và management server. |

## 13. Quy trình thực hành có thể lặp lại

1. Chọn đúng một dependency cần thêm hoặc bỏ và ghi rõ giả thuyết về class/auto-configuration liên quan.
2. Lưu source revision, POM, Java/Maven version và cấu hình baseline.
3. Build baseline, lưu JAR và dependency tree.
4. Chạy baseline, lưu bean inventory và condition report.
5. Thay đúng dependency đã chọn, build lại với cùng công cụ và cấu hình.
6. Lưu JAR thứ hai, dependency tree, bean inventory và condition report.
7. Diff dependency trước, rồi condition, sau cùng bean inventory.
8. Truy nguyên mọi bean thêm/mất tới dependency, condition source và bean definition.
9. Chạy test chức năng liên quan để xác nhận bean mới thực sự hoạt động.
10. Ghi kết luận, giới hạn và artifact dùng để tái hiện.

Đối với thí nghiệm thêm Actuator ở trên, bằng chứng mong đợi là dependency graph có Actuator, classpath condition chuyển sang match và marker bean xuất hiện. Khi làm trên một starter thực tế, thay marker bằng bean/auto-configuration thật của starter và kiểm tra behavior mà consumer cần.

## 14. Checklist trước khi chốt kết quả

- [ ] Chỉ có một dependency/profile được thay đổi có chủ đích.
- [ ] Cùng JDK, Maven, Spring Boot parent và source code.
- [ ] Đã lưu cả hai dependency tree, không chỉ chụp màn hình POM.
- [ ] Đã kiểm tra dependency trực tiếp, bắc cầu, scope và version conflict.
- [ ] Đã xuất bean inventory từ cả hai ApplicationContext.
- [ ] Đã xuất Condition Evaluation Report từ cả hai lần chạy bằng cùng cách.
- [ ] Đã phân biệt MATCH, NO_MATCH và source không còn là candidate.
- [ ] Đã truy nguyên bean mới/mất tới điều kiện và dependency tương ứng.
- [ ] Đã kiểm tra startup failure và lỗi classpath nếu có.
- [ ] Đã chạy test chức năng cho integration bị ảnh hưởng.
- [ ] Đã lưu JAR, logs, snapshots và lệnh build để tái hiện kết quả.

**Ghi nhớ:** dependency graph giải thích class nào được đưa vào runtime; Condition Evaluation Report giải thích vì sao cấu hình được hoặc không được áp dụng; bean inventory xác nhận definition nào cuối cùng có mặt trong context. Chỉ khi ba lớp bằng chứng khớp nhau, ta mới có thể giải thích rõ tác động của một thay đổi dependency.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration, class conditions và bean conditions: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — ConditionEvaluationReport: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — ConditionEvaluationReportLoggingListener: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot 3.3 Actuator API — Conditions endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 Actuator API — Beans endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html
- Apache Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Spring Framework 6.1 API — BeanDefinition: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html