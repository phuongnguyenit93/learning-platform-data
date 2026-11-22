# Phối hợp ứng viên qua nhóm DeferredImportSelector và sắp xếp cấu hình

## 1. Bài toán: nhiều auto-configuration cùng được phát hiện thì ai được xử lý trước?

Trong một ứng dụng Spring Boot, nhiều thư viện có thể công bố hàng chục hoặc hàng trăm lớp **auto-configuration**. Khi ứng dụng bật **@EnableAutoConfiguration**, Spring Boot cần làm nhiều việc hơn là đọc một danh sách tên lớp: nó phải **tập hợp ứng viên**, áp dụng **loại trừ và lọc sơ bộ**, **sắp xếp những cấu hình có ràng buộc thứ tự**, rồi mới đưa chúng vào quy trình xử lý cấu hình của Spring.

Điểm mấu chốt nằm ở việc Spring Framework cung cấp **DeferredImportSelector** và cơ chế **DeferredImportSelector.Group**. Spring Boot dùng **AutoConfigurationImportSelector** và nhóm **AutoConfigurationImportSelector.AutoConfigurationGroup** để phối hợp nhiều ứng viên trong giai đoạn import trì hoãn. Sau khi có tập ứng viên hợp lệ, Boot áp dụng các quy tắc thứ tự như **@AutoConfiguration(before = ...)**, **@AutoConfiguration(after = ...)**, **beforeName**, **afterName**, và những khai báo thứ tự tương ứng.

Cần phân biệt ba câu hỏi:

1. **Ứng viên được tìm thấy bằng cách nào?** Từ các resource **AutoConfiguration.imports** trên runtime classpath.
2. **Ứng viên được phối hợp và xếp thứ tự bằng cách nào?** Nhờ nhóm của DeferredImportSelector, các bước hợp nhất/loại trừ và bộ sắp xếp auto-configuration của Boot.
3. **Bean nào thực sự được đăng ký và tạo ra?** Sau bước chọn/sắp xếp vẫn phải xét **@Conditional** trên lớp/phương thức **@Bean**, bean của ứng dụng, scope, dependency và các bước khởi tạo.

Việc một lớp được xếp trước lớp khác **không bảo đảm** constructor của bean thuộc lớp đó chạy trước. **Thứ tự xử lý auto-configuration** chủ yếu tác động thứ tự phân tích/đăng ký bean definition và do đó có thể ảnh hưởng các điều kiện phụ thuộc vào bean đã đăng ký.

## 2. Từ @EnableAutoConfiguration đến DeferredImportSelector

**@SpringBootApplication** bao gồm **@EnableAutoConfiguration**. Annotation sau sử dụng **@Import(AutoConfigurationImportSelector.class)**, bên cạnh cơ chế đăng ký auto-configuration package. Trong Spring Boot 3.x:

~~~text
@SpringBootApplication
         |
         v
@EnableAutoConfiguration
         |
         v
@Import(AutoConfigurationImportSelector.class)
         |
         v
AutoConfigurationImportSelector
     implements DeferredImportSelector
         |
         v
getImportGroup() -> AutoConfigurationGroup
         |
         v
Tập hợp / lọc / exclude / sắp xếp ứng viên
         |
         v
Trả danh sách import cho Spring xử lý
         |
         v
Đánh giá condition và đăng ký bean definition
         |
         v
Khởi tạo instance theo scope/lifecycle/dependency
~~~

Đây là mô hình giải thích, không phải thứ tự từng câu lệnh nội bộ. Spring Framework xử lý cấu hình qua nhiều lượt, và một số điều kiện được đánh giá ở các pha khác nhau.

### 2.1. ImportSelector thường và DeferredImportSelector

Một **ImportSelector** trả lại tên những lớp cần import qua phương thức **selectImports(AnnotationMetadata)**. Spring dùng danh sách này khi xử lý configuration class chứa **@Import** tương ứng.

**DeferredImportSelector** là một dạng ImportSelector được xử lý **trì hoãn cho đến khi các configuration class thông thường đã được phân tích ở giai đoạn tương ứng**. Điều này đặc biệt hữu ích cho auto-configuration: các cấu hình ứng dụng khai báo tường minh và bean definition của chúng có cơ hội được xử lý trước các cấu hình mặc định do Boot đề xuất.

“Deferred” **không có nghĩa** Spring đã tạo xong tất cả instance bean ứng dụng trước khi selector hoạt động. Nó nói về **giai đoạn chọn và xử lý import của configuration class**, không phải mốc kết thúc khởi tạo mọi object.

So sánh ngắn:

| Cơ chế | Đầu vào | Kết quả | Đặc điểm chính |
| --- | --- | --- | --- |
| **@Import(SomeConfiguration.class)** | Class được chỉ định | Đưa class đó vào xử lý cấu hình | Import tường minh |
| **ImportSelector** | Annotation metadata và logic selector | Danh sách tên class để import | Lựa chọn động |
| **DeferredImportSelector** | Metadata và logic selector | Danh sách import được xử lý ở giai đoạn trì hoãn | Có thể nhường cấu hình ứng dụng xử lý trước |
| **DeferredImportSelector.Group** | Nhiều selector/metadata trong một nhóm | Tập entry import được nhóm phối hợp rồi trả về | Có thể hợp nhất, lọc, khử trùng lặp, sắp xếp theo chiến lược |
| **AutoConfigurationImportSelector** | Runtime classpath, property, exclusions, metadata | Các auto-configuration ứng viên được Boot lựa chọn | DeferredImportSelector do Boot cung cấp |
| **AutoConfigurationGroup** | Các auto-configuration entries từ selector tương ứng | Các import sau hợp nhất, loại trừ và sắp xếp | Chiến lược phối hợp của Spring Boot |

**DeferredImportSelector** không tự động có mọi thuật toán “khử trùng lặp, loại trừ, sort”. Chúng là trách nhiệm của implementation và/hoặc **Group** cụ thể. Spring Boot hiện thực chiến lược cần thiết cho auto-configuration qua nhóm riêng.

## 3. DeferredImportSelector.Group phối hợp các lựa chọn như thế nào?

Trong Spring Framework, giao diện nhóm của DeferredImportSelector có hai thao tác quan trọng:

- **process(AnnotationMetadata metadata, DeferredImportSelector selector)**: đưa kết quả của một selector cùng metadata liên quan vào nhóm để xử lý/tích lũy.
- **selectImports()**: trả về các mục **Entry**, gồm metadata và tên lớp import, sau khi nhóm hoàn tất phối hợp.

Cấu trúc API rút gọn (để hiểu chữ ký, không phải mã nguồn độc lập):

~~~java
interface Group {
    void process(
        AnnotationMetadata metadata,
        DeferredImportSelector selector
    );

    Iterable<Entry> selectImports();
}
~~~

Nhóm có thể thu thập kết quả từ **các selector được xếp chung nhóm**, kết hợp/chỉnh thứ tự rồi trả danh sách cuối. Những selector có cơ chế nhóm khác nhau **không mặc nhiên bị trộn vào một nhóm toàn cục**. Việc nhóm được chọn như thế nào phụ thuộc **getImportGroup()** của DeferredImportSelector.

Ví dụ khái niệm: hai cấu hình đều kích hoạt những selector có cùng Group. Thay vì mỗi selector tự xuất import một cách độc lập và không biết quyết định của selector kia, nhóm có thể nhìn các lựa chọn liên quan, loại trùng, xét ràng buộc và trả một danh sách thống nhất. **Đây là khả năng của Group, không phải một lời hứa rằng mọi implementation đều làm y hệt.**

### 3.1. Những thành phần Boot dùng trong nhóm auto-configuration

Trong Spring Boot 3.x, **AutoConfigurationImportSelector** trả về nhóm **AutoConfigurationImportSelector.AutoConfigurationGroup**. Ở mức ý tưởng, chuỗi xử lý gồm:

1. **Đọc danh sách auto-configuration ứng viên** từ các resource trên classpath.
2. **Loại các tên trùng lặp** khi có nhiều nguồn khai báo cùng một ứng viên.
3. **Thu thập exclusion** theo annotation và property; loại những auto-configuration bị loại trừ.
4. **Dùng filter/metadata** để sàng lọc các ứng viên hiển nhiên không phù hợp khi có đủ thông tin, chẳng hạn điều kiện classpath.
5. **Hợp nhất các kết quả** mà nhóm đã thu nhận; đảm bảo exclusion có hiệu lực trong danh sách tổng hợp.
6. **Sắp xếp các auto-configuration còn lại** theo thông tin before/after/order bằng bộ sắp xếp nội bộ của Boot.
7. **Trả danh sách import** để Spring tiếp tục phân tích class cấu hình và đánh giá điều kiện.

Các bước có thể được tổ chức khác nhau giữa các phiên bản Boot; không nên coi danh sách trên là pseudocode sao chép một-một từ implementation. Ý nghĩa ổn định của bài học là **nhóm phối hợp ứng viên trước khi trả danh sách import**, còn **condition trên lớp và @Bean vẫn quyết định bean definition** cuối cùng.

### 3.2. Tại sao cần sắp xếp sau khi hợp nhất?

Giả sử một thư viện có:

- **EngineAutoConfiguration**: đăng ký bean Engine mặc định.
- **ReportAutoConfiguration**: chỉ đăng ký Report khi **@ConditionalOnBean(Engine.class)** nhận thấy đã có bean Engine.

Nếu ReportAutoConfiguration được xử lý trước khi definition Engine xuất hiện, điều kiện phụ thuộc Engine có thể không đạt. Vì vậy thư viện có thể công bố:

~~~java
@AutoConfiguration(after = EngineAutoConfiguration.class)
class ReportAutoConfiguration {
    // ...
}
~~~

Khai báo **after** nói với Boot rằng khi cả hai auto-configuration tham gia, **EngineAutoConfiguration cần được xử lý trước ReportAutoConfiguration**. Nhờ đó ReportAutoConfiguration có cơ hội nhìn thấy các bean definition được đăng ký từ EngineAutoConfiguration.

Đây là ràng buộc **thứ tự xử lý cấu hình**, không phải yêu cầu rằng phương thức tạo bean Engine phải chạy ngay trước phương thức tạo Report. Khi Report được tạo, dependency injection vẫn quyết định cách tạo hoặc tìm Engine instance.

### 3.3. Thứ tự trong AutoConfiguration.imports có được coi là thứ tự chạy không?

**Không.** File **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** là danh sách ứng viên; vị trí dòng **không phải contract thứ tự** giữa các cấu hình. Bộ sắp xếp của Boot dùng metadata/annotation, cùng những quy tắc áp dụng trong phiên bản Boot tương ứng.

Ví dụ, một file có thể cố tình ghi Report trước Engine:

~~~text
dev.study.autoconfig.ReportAutoConfiguration
dev.study.autoconfig.EngineAutoConfiguration
~~~

Nếu ReportAutoConfiguration khai báo **@AutoConfiguration(after = EngineAutoConfiguration.class)**, Boot có thông tin để sắp xếp Engine trước Report mặc dù file liệt kê theo chiều ngược. Cách làm này sẽ được kiểm chứng ở ví dụ chạy được bên dưới.

Không sửa thứ tự dòng trong imports để khắc phục một condition phụ thuộc bean nếu tác giả chưa công bố quan hệ thứ tự đúng. Tên lớp và annotation liên quan mới là nơi lưu contract sắp xếp ổn định.

## 4. Các cách khai báo thứ tự auto-configuration

### 4.1. @AutoConfiguration(before = ...) và after = ...

Spring Boot 3.x cung cấp các thuộc tính trên **@AutoConfiguration**:

~~~java
@AutoConfiguration(after = EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
}
~~~

Và chiều ngược:

~~~java
@AutoConfiguration(before = ReportAutoConfiguration.class)
public class EngineAutoConfiguration {
}
~~~

Hai đoạn trên chỉ minh họa annotation; không phải hai file chạy độc lập. Cần đặt chúng vào đúng file/package có các class tương ứng. Thông thường chỉ cần khai báo **một chiều quan hệ rõ ràng**, tránh tạo các ràng buộc lặp hoặc mâu thuẫn.

**after = X.class** có nghĩa *nếu cả hai cấu hình được xét*, cố gắng xử lý X trước cấu hình hiện tại. Nó **không** tự import X và **không** ép X match. Nếu X vắng mặt, bị exclude hoặc điều kiện của X không đạt, cấu hình Y vẫn phải có condition tự bảo vệ giả định của mình.

**before = X.class** có chiều ngược lại và cũng không tự làm X xuất hiện.

### 4.2. beforeName và afterName

Khi một auto-configuration có quan hệ thứ tự với class thuộc **dependency tùy chọn**, không phải lúc nào ta cũng muốn tham chiếu **Class literal** ở compile time:

~~~java
@AutoConfiguration(
    afterName = "dev.optional.autoconfig.OptionalEngineAutoConfiguration"
)
public class OptionalReportAutoConfiguration {
}
~~~

Đây là ví dụ annotation minh họa. **afterName** và **beforeName** khai báo quan hệ bằng **fully qualified class name**, hữu ích khi module hiện tại không phụ thuộc compile-time vào class kia. Tên chuỗi phải đúng; sai tên sẽ không tạo được ràng buộc mong muốn.

Không dùng afterName như cách “tự tạo dependency”: nó chỉ mô tả thứ tự **nếu ứng viên liên quan thực sự tham gia**.

### 4.3. @AutoConfigureBefore, @AutoConfigureAfter và @AutoConfigureOrder

Ngoài các thuộc tính của **@AutoConfiguration**, Spring Boot có các annotation được tài liệu hóa như **@AutoConfigureBefore**, **@AutoConfigureAfter** và **@AutoConfigureOrder** để biểu đạt thứ tự. Với mã Boot 3.x mới, **@AutoConfiguration(before/after)** thường dễ đọc và đủ dùng.

- **@AutoConfigureBefore(X.class)** và **@AutoConfigureAfter(X.class)** nêu quan hệ tương đối với lớp X.
- **@AutoConfigureOrder** cung cấp thông tin ưu tiên thứ tự cho auto-configuration theo mô hình order. Nó không phải chỉ dẫn khởi tạo singleton instance hay một sự bảo đảm thay thế mọi quan hệ before/after.
- **@Order** thông thường được dùng ở nhiều ngữ cảnh Spring khác; đừng giả định đặt **@Order** lên một @Bean sẽ thay thứ tự import auto-configuration.

Ưu tiên thể hiện **quan hệ phụ thuộc thực tế** bằng before/after. Dùng order số khi thật sự cần và hiểu rõ tác dụng của nó; tránh thiết kế phải dựa vào giá trị số “may mắn” của một thư viện khác.

### 4.4. Sắp xếp là một bài toán quan hệ, không phải một hàng đợi constructor

Một chuỗi hợp lệ:

~~~text
DatabaseAutoConfiguration
          |
          | before
          v
RepositoryAutoConfiguration
          |
          | before
          v
ServiceAutoConfiguration
~~~

Hãy đọc là **cấu hình database được xử lý trước cấu hình repository, rồi đến cấu hình service**, nếu chúng đều là ứng viên được chọn. Nó không hứa mọi connection pool đã sẵn sàng trước mọi constructor, không ép các class phụ thuộc phải tồn tại, và không thay thế dependency injection.

Các quan hệ **A after B, B after A** tự mâu thuẫn, cần sửa. Nếu có một vòng phụ thuộc thứ tự giữa nhiều auto-configuration, bộ sắp xếp không thể cung cấp thứ tự hợp lệ đáp ứng tất cả ràng buộc; đừng “chữa” bằng đổi thứ tự dòng imports.

## 5. Ba lớp quyết định khác nhau: candidate, condition, instance

Để phân tích đúng một log Spring Boot, hãy chia thành ba lớp:

| Lớp | Hỏi gì? | Ví dụ |
| --- | --- | --- |
| **Candidate discovery/group ordering** | Lớp auto-config có được tìm thấy, không bị loại trừ và được đặt vào thứ tự xử lý nào? | Report được sắp sau Engine |
| **Condition/bean definition registration** | Khi xử lý class hoặc @Bean, điều kiện có đạt để đăng ký definition không? | @ConditionalOnBean(Engine.class) trên method report |
| **Instance lifecycle** | Bean nào được tạo thật, vào lúc nào, lỗi gì khi init/inject? | Report cần Engine trong constructor/factory method |

**@ConditionalOnBean** và **@ConditionalOnMissingBean** đặc biệt nhạy với thứ tự vì chúng dựa trên **các bean definition đã được xử lý cho đến thời điểm đánh giá**. Các điều kiện này nên dùng trong auto-configuration, nơi framework cung cấp cơ chế xử lý sau cấu hình người dùng và cơ chế sắp xếp giữa các auto-configuration.

Ngược lại, condition **@ConditionalOnClass** tập trung vào classpath; condition **@ConditionalOnProperty** đọc Environment; chúng không biến thành đúng chỉ vì ta dùng before/after.

Đừng nhầm:

- **Có bean definition**: container biết một bean có thể tạo ra.
- **Có bean instance**: container đã tạo/nhận đối tượng theo scope tương ứng.
- **Bean mặc định back off**: nhánh có **@ConditionalOnMissingBean** không đăng ký default vì đã tồn tại một bean phù hợp; đối tượng của bean người dùng không nhất thiết đã khởi tạo.

## 6. Ví dụ Spring Boot hoàn chỉnh: sắp xếp ngược thứ tự file imports

Ví dụ dùng **JDK 21, Maven 3.9+, Spring Boot 3.3.13**. Một **EngineAutoConfiguration** cung cấp Engine mặc định, một **ReportAutoConfiguration** tạo Report **chỉ khi container đã biết bean Engine**. Lớp Report được liệt kê **trước** Engine trong file imports, nhưng khai báo **@AutoConfiguration(after = EngineAutoConfiguration.class)** nên Boot có thể xử lý đúng thứ tự.

Ta cũng chứng minh điều kiện có thể tắt bean mặc định, và bean người dùng có thể làm default back off.

### 6.1. Cấu trúc thư mục

~~~text
deferred-order-demo/
├── pom.xml
└── src/main/
    ├── java/dev/study/
    │   ├── api/
    │   │   ├── Engine.java
    │   │   └── Report.java
    │   ├── autoconfig/
    │   │   ├── EngineAutoConfiguration.java
    │   │   └── ReportAutoConfiguration.java
    │   └── app/
    │       └── DemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đặt package ứng dụng trong **dev.study.app**, các auto-configuration ở **dev.study.autoconfig**. Vùng component scan mặc định của @SpringBootApplication chỉ tìm trong dev.study.app và các package con. Vì vậy hai lớp auto-configuration trong project này đi vào ứng dụng **qua AutoConfiguration.imports**, không phải do @ComponentScan tình cờ phát hiện.

### 6.2. Dependency và build

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.study</groupId>
    <artifactId>deferred-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter cơ bản đã cung cấp Spring Boot/auto-config/Spring Context cần thiết. Dự án không cần servlet container, cơ sở dữ liệu hay API mạng.

### 6.3. Hai kiểu dữ liệu dùng để quan sát

**src/main/java/dev/study/api/Engine.java**

~~~java
package dev.study.api;

@FunctionalInterface
public interface Engine {
    String label();
}
~~~

**src/main/java/dev/study/api/Report.java**

~~~java
package dev.study.api;

public record Report(String summary) {
}
~~~

### 6.4. Auto-configuration tạo Engine trước

**src/main/java/dev/study/autoconfig/EngineAutoConfiguration.java**

~~~java
package dev.study.autoconfig;

import dev.study.api.Engine;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Engine.class)
public class EngineAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Engine.class)
    @ConditionalOnProperty(
        prefix = "demo.engine",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    Engine defaultEngine() {
        return () -> "default";
    }
}
~~~

Ở đây:

- **@ConditionalOnClass** đòi class Engine có trên classpath. Trong project mẫu nó luôn có mặt; thư viện thực có thể tham chiếu một API tùy chọn.
- **@ConditionalOnMissingBean(Engine.class)** giúp default Engine nhường chỗ cho bean Engine do người dùng khai báo.
- **@ConditionalOnProperty** cho phép tắt **defaultEngine** khi **demo.engine.enabled=false**.
- Nếu method được chọn, Spring đăng ký bean definition; bản thân việc chọn không có nghĩa lúc đó instance đã được tạo.

### 6.5. Auto-configuration phụ thuộc vào bean Engine

**src/main/java/dev/study/autoconfig/ReportAutoConfiguration.java**

~~~java
package dev.study.autoconfig;

import dev.study.api.Engine;
import dev.study.api.Report;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = EngineAutoConfiguration.class)
@ConditionalOnClass({Engine.class, Report.class})
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(Engine.class)
    @ConditionalOnMissingBean(Report.class)
    Report report(Engine engine) {
        return new Report("engine=" + engine.label());
    }
}
~~~

**after** điều khiển **thứ tự xử lý auto-configuration**. **@ConditionalOnBean(Engine.class)** mới là điều kiện thật quyết định Report có được đăng ký hay không. Nếu EngineAutoConfiguration bị exclude hoặc không đăng ký default, Report vẫn có thể được tạo **khi một cấu hình người dùng đã cung cấp bean Engine**. Do đó không suy rằng “after” nghĩa là “phụ thuộc tuyệt đối vào chính class EngineAutoConfiguration”.

**@ConditionalOnMissingBean(Report.class)** cho phép ứng dụng cung cấp Report riêng nếu muốn. Trong bản chạy bên dưới không có Report do người dùng tự định nghĩa.

### 6.6. File đăng ký ứng viên cố tình liệt kê ngược

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.study.autoconfig.ReportAutoConfiguration
dev.study.autoconfig.EngineAutoConfiguration
~~~

Đây là chủ đích của bài: **Report đứng trước Engine trong resource**, nhưng **@AutoConfiguration(after = EngineAutoConfiguration.class)** vẫn cung cấp thứ tự xử lý đúng ở mức cấu hình. Không thêm **@ComponentScan** để tìm các class trong package autoconfig.

### 6.7. Ứng dụng có bean người dùng tùy chọn

**src/main/java/dev/study/app/DemoApplication.java**

~~~java
package dev.study.app;

import dev.study.api.Engine;
import dev.study.api.Report;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @Profile("custom")
    Engine customEngine() {
        return () -> "custom";
    }

    @Bean
    ApplicationRunner showSelectedBeans(
            ObjectProvider<Engine> engines,
            ObjectProvider<Report> reports) {
        return args -> {
            Engine engine = engines.getIfAvailable();
            Report report = reports.getIfAvailable();

            System.out.println("engine=" +
                (engine == null ? "<none>" : engine.label()));
            System.out.println("report=" +
                (report == null ? "<none>" : report.summary()));
        };
    }
}
~~~

**@SpringBootApplication** kích hoạt auto-configuration qua @EnableAutoConfiguration. Profile **custom** chỉ bật một bean người dùng Engine; nó được xử lý cùng cấu hình ứng dụng trước các auto-configuration của Boot. **ObjectProvider** cho phép ứng dụng chạy cả khi bean Engine hoặc Report vắng mặt.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Cấu hình log giúp nhìn rõ hai dòng stdout do ví dụ tự in. Nếu muốn xem condition evaluation report, hãy ghi đè logging bằng tùy chọn ở phần chẩn đoán.

### 6.8. Chạy và đọc từng kết quả

Yêu cầu: JDK 21, Maven 3.9+, có thể tải dependency. Đứng trong thư mục dự án:

~~~bash
mvn -q -DskipTests package
~~~

**A. Không truyền property và không bật profile**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar
~~~

Hai dòng stdout do code in:

~~~text
engine=default
report=engine=default
~~~

Diễn giải: EngineAutoConfiguration được xử lý đủ sớm để method tạo Engine có definition; ReportAutoConfiguration được xếp sau Engine và condition **@ConditionalOnBean(Engine.class)** đạt. Report bean được tạo với Engine tương ứng.

**B. Tắt Engine mặc định bằng property**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --demo.engine.enabled=false
~~~

Stdout:

~~~text
engine=<none>
report=<none>
~~~

Lý do: **@ConditionalOnProperty** của method tạo Engine không đạt. Việc ReportAutoConfiguration được xếp sau Engine **không tự tạo ra** một bean Engine; vì container không có bean Engine nên **@ConditionalOnBean** của Report cũng không đạt.

**C. Bật bean Engine của người dùng**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Stdout:

~~~text
engine=custom
report=engine=custom
~~~

Lý do: customEngine do cấu hình ứng dụng khai báo, nên defaultEngine rút lui bởi **@ConditionalOnMissingBean(Engine.class)**. ReportAutoConfiguration vẫn được xử lý và tạo Report nhờ có bean Engine của người dùng.

**D. Tắt default bằng property nhưng vẫn bật bean custom**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom --demo.engine.enabled=false
~~~

Stdout:

~~~text
engine=custom
report=engine=custom
~~~

Property **demo.engine.enabled=false** chỉ tắt nhánh defaultEngine trong ví dụ. Nó không xóa bean do ứng dụng tự định nghĩa, nên Report vẫn được tạo.

**E. Exclude hẳn EngineAutoConfiguration**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.study.autoconfig.EngineAutoConfiguration
~~~

Stdout khi không bật profile custom:

~~~text
engine=<none>
report=<none>
~~~

Ở đây **EngineAutoConfiguration không tham gia auto-configuration**, nên không tạo defaultEngine. ReportAutoConfiguration vẫn có thể là ứng viên, nhưng thiếu Engine để thỏa condition. **after** không ép class bị exclude trở lại.

**F. Exclude riêng ReportAutoConfiguration**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.study.autoconfig.ReportAutoConfiguration
~~~

Stdout:

~~~text
engine=default
report=<none>
~~~

Đây là bằng chứng rằng **quy tắc after chỉ sắp xếp thứ tự nếu cấu hình có tham gia**; bỏ Report không làm Engine mặc định biến mất.

### 6.9. So sánh các kịch bản

| Kịch bản | Định nghĩa Engine nào được giữ? | Report condition có thể đạt? | Kết quả |
| --- | --- | --- | --- |
| Mặc định | defaultEngine | Có | default + report |
| demo.engine.enabled=false | Không có | Không | Không có cả hai |
| custom profile | customEngine | Có | custom + report |
| custom + enabled=false | customEngine | Có | custom + report |
| exclude EngineAutoConfiguration | Không có nếu không có custom | Không | Không có cả hai |
| exclude ReportAutoConfiguration | defaultEngine | Không xét method report của class bị exclude | Chỉ default Engine |

Bảng chỉ mô tả project ví dụ. Trong hệ thống khác, có thể có thêm các bean Engine/Report do nguồn khác đăng ký. Khi đó phải xem condition thật và không áp dụng máy móc kết quả.

## 7. Nhìn sâu vào thuật toán nhóm bằng một ví dụ khái niệm

Giả sử có ba selector trì hoãn cùng kiểu Group:

~~~text
Selector A -> ứng viên: [CacheAutoConfig, EngineAutoConfig]
Selector B -> ứng viên: [ReportAutoConfig, EngineAutoConfig]
Selector C -> exclude: [CacheAutoConfig]
~~~

Một **Group được thiết kế để tổng hợp** có thể xử lý như sau:

~~~text
Tập đầu vào: Cache, Engine, Report, Engine
Khử trùng lặp: Cache, Engine, Report
Loại trừ: Engine, Report
Ràng buộc: Report after Engine
Tập import cuối: Engine, Report
~~~

Đây là **ví dụ giả lập về tư duy của cơ chế nhóm**, không phải mô tả chính xác từng callback của **AutoConfigurationGroup** với ba selector trên: Spring Boot có quy tắc riêng để lấy candidates và exclusions từ auto-configuration metadata. Mục đích của ví dụ là thể hiện vì sao cần có điểm phối hợp **sau khi nhiều selector đã đóng góp dữ liệu nhưng trước khi xuất danh sách import**.

Trong thực tế, Boot dùng **AutoConfigurationImportSelector.AutoConfigurationGroup**, phối hợp các entries, exclusions và thông tin sắp xếp từ auto-configuration. **AutoConfigurationSorter** là thành phần triển khai nội bộ giúp xác lập thứ tự. Developer thư viện thông thường **không cần tự viết Group hoặc gọi AutoConfigurationSorter**: nên công bố class qua imports và mô tả quan hệ bằng annotation được hỗ trợ.

### 7.1. Khi nào tự triển khai DeferredImportSelector.Group?

Chỉ nên tạo Group của riêng bạn nếu đang thiết kế **cơ chế @Enable... tùy biến** mà nhiều selector cần thống nhất quyết định, chẳng hạn muốn xử lý xung đột module hoặc sắp xếp các import theo một contract chuyên biệt.

Khung API minh họa:

~~~java
// Minh họa chữ ký API, chưa phải một project có thể chạy độc lập.
final class FeatureImportSelector
        implements DeferredImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {"dev.study.features.FeatureConfiguration"};
    }

    @Override
    public Class<? extends Group> getImportGroup() {
        return FeatureGroup.class;
    }
}
~~~

Ở đoạn này, **FeatureGroup** chỉ là tên lớp sẽ cần được tự triển khai theo interface Group; snippet chỉ minh họa điểm liên kết selector với nhóm, **không phải code hoàn chỉnh**. Khi làm thật, Group phải xử lý **process(...)** và trả **Iterable<Entry>** từ **selectImports()**. Tránh xây một cơ chế riêng chỉ để thay thế chức năng auto-configuration mà Spring Boot đã cung cấp.

## 8. Phân tích tương tác giữa sorting và @ConditionalOnBean

### 8.1. Tại sao bean existence condition nhạy với thứ tự?

Khi Spring xét **@ConditionalOnBean(Engine.class)** ở một auto-configuration, nó làm việc với các bean definition **đã được xử lý đến lúc đó** theo phạm vi tìm kiếm của condition. Nếu một auto-configuration cung cấp Engine được xử lý quá muộn, nhánh phụ thuộc có thể không thấy Engine dù về sau engine definition mới xuất hiện.

Đây là lý do **@AutoConfiguration(after = EngineAutoConfiguration.class)** có giá trị thực tế trong ví dụ. Quy tắc thứ tự không “đánh thức” mọi bean; nó giúp condition được đánh giá tại thời điểm có thông tin đăng ký thích hợp.

**Các trường hợp cần phân biệt:**

- **Đã có Engine do ứng dụng khai báo:** condition có thể đạt ngay cả khi EngineAutoConfiguration bị exclude.
- **EngineAutoConfiguration là ứng viên nhưng không có bean Engine do property false:** condition không đạt.
- **Bean Engine được đăng ký dưới scope lazy:** condition vẫn có thể đạt vì definition tồn tại, dù instance chưa tạo.
- **Engine cần được tạo trước khi Report instance khởi tạo:** dependency injection qua tham số phương thức **report(Engine engine)** sẽ tìm/tạo instance cần thiết theo container; đây là một quan hệ lifecycle **khác** với sorting definition.
- **Bean Engine thuộc parent context hoặc được đăng ký bằng cơ chế đặc biệt:** cần xét search strategy và quy tắc nhận diện bean của condition, không khẳng định mọi bean trong mọi context đều được nhìn thấy.

### 8.2. Tại sao thứ tự import chưa đủ để bảo đảm mọi điều kiện?

Một nhánh auto-configuration chỉ nên đưa ra giả định dựa trên **condition kiểm chứng được**. Nếu Report phụ thuộc vào Engine, sử dụng condition như **@ConditionalOnBean(Engine.class)** và inject Engine. Nếu Report phải có một class tùy chọn, thêm **@ConditionalOnClass** thích hợp để bảo vệ việc xử lý. Nếu feature cần property bật, thêm **@ConditionalOnProperty** theo contract.

**@AutoConfiguration(after = ...)** chỉ giải quyết *khi xét điều kiện phụ thuộc bean nên xử lý cấu hình nào trước*, không chứng minh bean nguồn chắc chắn tồn tại.

### 8.3. Tránh chu trình thứ tự và phụ thuộc vòng

Đừng thiết kế cả **EngineAutoConfiguration(after = ReportAutoConfiguration.class)** và **ReportAutoConfiguration(after = EngineAutoConfiguration.class)**. Hai ràng buộc đối nghịch khiến không có thứ tự nào thỏa mãn. Cần thiết kế chiều phụ thuộc rõ ràng.

Cũng không nhầm **chu trình sắp xếp cấu hình** với **circular dependency giữa bean instances**. Trường hợp thứ nhất là quan hệ trước/sau trong registration; trường hợp thứ hai liên quan constructor/injection giữa các bean. Chúng có thể xuất hiện độc lập và cần giải quyết ở đúng tầng.

## 9. Các điều sorting không cam kết

| Hiểu nhầm | Sửa lại |
| --- | --- |
| “Dòng đầu trong AutoConfiguration.imports luôn chạy trước.” | Danh sách đó chỉ công bố ứng viên; Boot có cơ chế sort theo metadata và quan hệ before/after. |
| “after = X sẽ tự import X.” | Ràng buộc thứ tự chỉ có ý nghĩa khi X thực sự tham gia; không ép candidate bị thiếu/exclude quay lại. |
| “after = X khiến instance bean X được tạo trước.” | Nó điều khiển thứ tự xử lý cấu hình/đăng ký definition, không thay thế dependency/lifecycle. |
| “@ConditionalOnBean tìm mọi bean sẽ xuất hiện trong tương lai.” | Điều kiện dựa trên các bean đã được xử lý ở thời điểm xét; vì thế thứ tự quan trọng. |
| “Deferred nghĩa là các singleton ứng dụng đã khởi tạo.” | Deferred ở đây là deferred import trong quá trình xử lý configuration metadata. |
| “Group luôn tự khử trùng lặp và sắp xếp.” | Interface Group chỉ cung cấp hook; thuật toán phụ thuộc implementation. |
| “@AutoConfiguration tự đứng vào nhóm nhờ component scan.” | Ứng viên Boot 3.x được công bố qua AutoConfiguration.imports; không nên component-scan auto-config như component thông thường. |
| “@AutoConfigureOrder giống thứ tự @Bean init.” | Thứ tự auto-configuration không phải thứ tự constructor. |
| “Có positive match nghĩa là tạo bean thành công.” | Condition match khác với việc BeanDefinition và instance được tạo thành công. |
| “Đã xếp đúng thứ tự thì có thể bỏ @ConditionalOnBean.” | Sorting chỉ sắp xếp; condition vẫn cần xác minh sự tồn tại của bean phụ thuộc. |
| “Chỉ đổi thứ tự các dòng imports là sửa được condition.” | Khai báo quan hệ before/after trong auto-configuration, tránh dựa vào thứ tự file. |

## 10. Debug và xác minh thứ tự bằng công cụ có sẵn

### 10.1. Xem Condition Evaluation Report

Với project mẫu có **logging.level.root=OFF**, dùng:

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

Nhìn vào **CONDITIONS EVALUATION REPORT** và tìm **EngineAutoConfiguration** và **ReportAutoConfiguration**. Báo cáo cho biết lý do condition match/không match và những exclusion tương ứng. Khi Engine mặc định tắt, Report có thể là negative match vì thiếu Engine. Khi bật custom profile, điều kiện của defaultEngine không đạt do bean người dùng đã có, còn report có thể match.

**Giới hạn:** condition report không phải bảng liệt kê chắc chắn toàn bộ thứ tự xử lý từng configuration class; muốn chứng minh một thứ tự nội bộ cụ thể ở version cụ thể phải dùng mã chẩn đoán/thử nghiệm ở đúng giai đoạn xử lý hoặc đọc implementation của phiên bản đó. Báo cáo chỉ giúp xác nhận **hệ quả điều kiện**.

### 10.2. Khi không thấy Report bean

Kiểm tra theo trình tự:

1. **Classpath/resource:** JAR có chứa resource **AutoConfiguration.imports** và tên class chính xác không? Lệnh **mvn dependency:tree** giúp kiểm tra dependency nếu có thư viện ngoài.
2. **Loại trừ:** có dùng **spring.autoconfigure.exclude**, annotation exclude hoặc chế độ bật/tắt cấu hình khác không?
3. **Ordering metadata:** ReportAutoConfiguration có khai báo **after = EngineAutoConfiguration.class** không? Nếu dùng **afterName** thì tên đầy đủ có đúng không?
4. **Bean definition:** Engine có được đăng ký tại thời điểm condition của Report được đánh giá không?
5. **Property/condition:** **demo.engine.enabled** có giá trị gì sau khi xét các property source và profile? Engine và Report có class trên classpath không?
6. **Khởi tạo:** có lỗi **BeanCreationException**, factory method hoặc dependency resolution không?
7. **Tên/kiểu bean:** có bean Engine/Report khác do ứng dụng cung cấp và làm default back off không?

Dùng đúng loại bằng chứng: **condition report** cho lựa chọn cấu hình, **BeanFactory metadata** cho đăng ký definition, stack trace/log lifecycle cho việc tạo instance.

### 10.3. Vai trò của metadata tối ưu hóa

Spring Boot có thể sử dụng thông tin **spring-autoconfigure-metadata.properties** được tạo ở quá trình build thư viện để tối ưu lọc ứng viên và đọc một số thông tin liên quan. Với auto-configuration do bạn phát triển, có thể dùng **spring-boot-autoconfigure-processor** khi phù hợp theo tài liệu phiên bản.

Resource tối ưu hóa này **không thay thế** file **AutoConfiguration.imports** trong Spring Boot 3.x. Khi thiếu metadata tối ưu hóa, không suy rằng mọi before/after bị vô hiệu; các annotation cấu hình vẫn là nguồn thông tin cần được framework xử lý.

## 11. Câu hỏi thực hành có đáp án

**Câu 1.** ReportAutoConfiguration được ghi ở dòng đầu của imports, EngineAutoConfiguration ở dòng sau. Vì sao Report vẫn hoạt động ở kịch bản mặc định?

**Đáp án:** Report khai báo **@AutoConfiguration(after = EngineAutoConfiguration.class)**, để Boot xử lý Engine trước Report theo quan hệ đã công bố. Điều kiện **@ConditionalOnBean(Engine.class)** của Report nhờ đó có thể nhìn thấy bean Engine đã được đăng ký.

**Câu 2.** Exclude EngineAutoConfiguration, nhưng bật profile custom. Report có thể xuất hiện không?

**Đáp án:** Có. Report cần **bean Engine**, không đòi instance đó phải do EngineAutoConfiguration cung cấp. Bean custom có thể đáp ứng condition. Ràng buộc after không nhập lại class bị exclude.

**Câu 3.** Tại sao không nên dùng mỗi **@AutoConfiguration(after = EngineAutoConfiguration.class)** mà bỏ **@ConditionalOnBean(Engine.class)**?

**Đáp án:** after chỉ đảm bảo quan hệ thứ tự xử lý khi có hai candidate; nó không đảm bảo EngineAutoConfiguration match, không đảm bảo method defaultEngine được chọn, và không bảo đảm bean Engine tồn tại.

**Câu 4.** Tại sao Group khác một DeferredImportSelector đơn lẻ?

**Đáp án:** Selector chọn imports từ metadata của nó; **Group** cung cấp hook để tập hợp và phối hợp kết quả từ các selectors cùng nhóm, rồi trả danh sách import cuối. Việc nhóm sẽ khử trùng lặp/sắp xếp như thế nào do Group implementation quyết định.

**Câu 5.** Một Engine singleton có definition nhưng được đánh dấu lazy, chưa có instance. Report có thể match **@ConditionalOnBean(Engine.class)** không?

**Đáp án:** Có thể, vì điều kiện xét thông tin bean đã được đăng ký, không cần instance Engine đã được tạo. Nhưng khi Report thực sự khởi tạo và inject Engine, nó có thể buộc tạo Engine lúc đó.

**Câu 6.** Đổi hai dòng AutoConfiguration.imports nhưng không đổi annotation before/after có phải cách chuẩn sửa thứ tự không?

**Đáp án:** Không. File imports là danh sách ứng viên, không phải API thứ tự. Hãy thiết lập quan hệ trên annotation auto-configuration và kiểm tra kết quả.

**Câu 7.** Có thể tạo một DeferredImportSelector.Group khác hoàn toàn ngoài Spring Boot không?

**Đáp án:** Có. Đây là extension point của Spring Framework. Tuy nhiên khi viết thư viện Spring Boot chỉ muốn cung cấp mặc định theo classpath/condition, cách chuẩn thường là **@AutoConfiguration** cộng **AutoConfiguration.imports** và thứ tự before/after; không cần tái triển khai cơ chế nhóm.

**Câu 8.** Tại sao thứ tự khởi tạo object Report và Engine không thể suy trực tiếp từ annotation after?

**Đáp án:** Quan hệ after liên quan xử lý cấu hình/definition. Khi Report instance được tạo, phương thức **report(Engine engine)** biểu diễn dependency runtime, khiến container resolve Engine khi cần. Một bean lazy, proxy hoặc scope khác còn có hành vi vòng đời riêng.

## 12. Ghi nhớ khi xây dựng thư viện

Để phối hợp nhiều auto-configuration một cách dự đoán được, hãy:

1. Công bố **mỗi lớp auto-configuration** đúng format Spring Boot 3.x trong **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
2. Khai báo **@AutoConfiguration(after/before/afterName/beforeName)** theo quan hệ dependency thực tế giữa các cấu hình; không dựa vào thứ tự dòng imports.
3. Đặt điều kiện phù hợp, nhất là **@ConditionalOnClass**, **@ConditionalOnBean**, **@ConditionalOnMissingBean** và **@ConditionalOnProperty**, để mỗi nhánh có thể tự bảo vệ giả định của mình.
4. Nhường các bean mặc định cho bean người dùng khi muốn hỗ trợ tùy biến; không tạo trùng bean chỉ vì một auto-configuration được import.
5. Phân biệt **candidate discovery → Group phối hợp → ordering → condition/registration → instance lifecycle** khi debug.
6. Dùng **Condition Evaluation Report** để đọc lý do chọn/bỏ qua; nếu thấy lỗi tạo bean thì xem riêng BeanCreationException và dependency chain.

**DeferredImportSelector.Group** là điểm mở rộng giúp nhiều lựa chọn import trì hoãn có thể được xử lý tập thể. **AutoConfigurationGroup và cơ chế sort của Spring Boot** sử dụng điểm này để tạo danh sách auto-configuration hợp lệ, có thứ tự và có khả năng tôn trọng cấu hình người dùng. **before/after** giúp điều kiện dựa trên bean definition được xét theo quan hệ có chủ đích; bản thân nó không tạo bean, không ép điều kiện đạt và không thay thế dependency injection.

### Tài liệu tham khảo

- Spring Framework, **DeferredImportSelector** và **DeferredImportSelector.Group**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Spring Boot, **AutoConfigurationImportSelector**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot, **@AutoConfiguration**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
