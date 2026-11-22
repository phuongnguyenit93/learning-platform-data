# Ba ngộ nhận về Spring Boot Auto-configuration

## Mục tiêu và bối cảnh

Trong Spring Boot, `auto-configuration` giúp đăng ký cấu hình và bean mặc định cho một ứng dụng Spring dựa trên những gì ứng dụng đang có: thư viện trên classpath, bean do lập trình viên khai báo, thuộc tính cấu hình, loại ứng dụng và các điều kiện khác. Nó giảm lượng cấu hình thủ công nhưng không hứa rằng mọi tính năng đều được bật.

Ba ngộ nhận dễ gặp:

1. **“Thêm starter là luôn có bean tương ứng.”** Sai: starter chủ yếu là gói dependency thuận tiện; bean chỉ được tạo khi cấu hình và các điều kiện phù hợp.
2. **“Tất cả auto-configuration đều được bật.”** Sai: các cấu hình là ứng viên để xét; nhiều cấu hình bị bỏ qua vì điều kiện không khớp hoặc vì có bean do ứng dụng tự cung cấp.
3. **“Spring Boot thay thế Spring Framework.”** Sai: Boot xây trên Spring Framework, dùng chính IoC container, dependency injection và các cơ chế nền tảng của Spring.

Điều cần phân biệt là **thư viện có mặt**, **lớp auto-configuration được phát hiện**, **điều kiện khớp**, và **bean thực sự được đăng ký**. Bốn trạng thái này không đồng nghĩa.

## 1. Hiểu đúng chuỗi từ dependency đến bean

Một chuỗi suy luận hữu ích:

~~~text
Thêm starter/dependency trong Maven hoặc Gradle
    ↓
Các thư viện và class xuất hiện trên classpath
    ↓
Spring Boot tìm các lớp auto-configuration đã đăng ký
    ↓
Đánh giá điều kiện tại cấu hình và/hoặc tại phương thức @Bean
    ↓
Điều kiện khớp → có thể đăng ký định nghĩa bean mặc định
Điều kiện không khớp → không đăng ký bean đó
    ↓
Spring IoC container quản lý và tiêm các bean thực sự được tạo
~~~

Trong ứng dụng điển hình, `@SpringBootApplication` bao gồm khả năng bật auto-configuration, quét component trong phạm vi package thích hợp và đánh dấu lớp cấu hình gốc. Đặc biệt, **component scanning** phát hiện `@Component`/`@Service`/`@Repository` của ứng dụng; **auto-configuration** dùng các lớp cấu hình đã đăng ký qua cơ chế riêng. Đây là hai cách đưa bean definition vào Spring context, có thể cùng hoạt động trong một ứng dụng.

Starter như `spring-boot-starter-data-jpa` giúp thêm nhóm dependency thường dùng cho JPA. Điều đó không tương đương với việc Spring Boot chắc chắn tạo được `DataSource`, `EntityManagerFactory` và mọi bean liên quan ở mọi môi trường. Ví dụ, ứng dụng thiếu thông tin kết nối và thiếu cơ sở dữ liệu nhúng có thể không khởi động được vì không thể cấu hình `DataSource`; một trường hợp khác có thể có sẵn bean do người dùng định nghĩa và Boot sẽ lùi bước ở một phần cấu hình. Không suy luận trạng thái bean chỉ từ tên starter trong `pom.xml`.

### Các loại điều kiện thường gặp

| Điều kiện | Câu hỏi được kiểm tra | Tác động điển hình |
| --- | --- | --- |
| `@ConditionalOnClass` | Có lớp/thư viện cần thiết trên classpath không? | Không có thư viện thì bỏ qua cấu hình liên quan. |
| `@ConditionalOnMissingBean` | Chưa có bean thích hợp trong context tại thời điểm đánh giá? | Cho phép dùng bean của ứng dụng thay vì mặc định. |
| `@ConditionalOnBean` | Có bean cần làm tiền đề hay chưa? | Chỉ thêm cấu hình khi tiền đề tồn tại. |
| `@ConditionalOnProperty` | Thuộc tính có giá trị phù hợp không? | Cho phép bật/tắt hoặc lựa chọn tính năng bằng cấu hình. |
| `@ConditionalOnWebApplication` | Có phải môi trường web phù hợp không? | Tránh đăng ký bean web trong ứng dụng không phải web. |

Điều kiện có thể nằm trên cả lớp cấu hình lẫn phương thức `@Bean`, có thể kết hợp nhiều điều kiện. `@ConditionalOnMissingBean` không phải quy tắc “bean nào trùng tên thì Boot luôn thắng/thua”: hành vi phụ thuộc **kiểu bean**, tên/qualifier nếu được chỉ rõ, phạm vi tìm kiếm và thứ tự đăng ký bean definition. Khi tự viết auto-configuration, nên đặt các điều kiện theo khuyến nghị của Spring Boot và để auto-configuration chạy sau bean definition do ứng dụng khai báo.

## 2. Ngộ nhận thứ nhất: “Thêm starter luôn tạo bean”

**Sự thật:** starter giải quyết việc chọn dependency; auto-configuration mới quyết định việc đăng ký bean mặc định và thường có điều kiện.

Giả sử muốn dùng một thành phần tích hợp:

- Thêm starter giúp đưa các API và implementation phù hợp lên classpath.
- Nếu thiếu một class bắt buộc, cấu hình bảo vệ bằng `@ConditionalOnClass` sẽ không áp dụng.
- Nếu property tắt tính năng, cấu hình bảo vệ bằng `@ConditionalOnProperty` sẽ không áp dụng.
- Nếu ứng dụng đã định nghĩa bean cùng loại và cấu hình mặc định dùng `@ConditionalOnMissingBean`, cấu hình mặc định có thể lùi bước.
- Nếu điều kiện đúng nhưng bean cần dependency khác không có, quá trình tạo context còn có thể thất bại; **điều kiện khớp không bảo đảm cả ứng dụng khởi động thành công**.

Ví dụ quen thuộc: thêm starter web giúp có dependency phục vụ Spring MVC và máy chủ nhúng trong cấu hình thích hợp, nhưng không tự tạo mọi controller nghiệp vụ; bạn vẫn phải viết controller hoặc đăng ký handler. Tương tự, thêm starter JPA không tạo entity hoặc repository nghiệp vụ từ hư không.

**Cách kiểm chứng:** xem dependency tree để biết thực sự có thư viện nào, sau đó xem condition evaluation report và danh sách bean trong `ApplicationContext` để biết cái gì đã được kích hoạt. Dependency tree chỉ trả lời câu hỏi về classpath, không chứng minh sự tồn tại của bean.

## 3. Ngộ nhận thứ hai: “Mọi auto-configuration đều được bật”

**Sự thật:** Boot phát hiện nhiều lớp auto-configuration *ứng viên* rồi lọc theo điều kiện. Việc một lớp có trong danh sách ứng viên không nói rằng lớp đó đã đăng ký bean.

Ví dụ, một ứng dụng chỉ chạy batch hoặc command-line thường không đáp ứng điều kiện dành riêng cho servlet web application. Ngay trong một ứng dụng web, một nhóm cấu hình có thể khớp còn nhóm khác không khớp vì thiếu dependency hoặc property. Một auto-configuration cũng có thể khớp ở cấp lớp nhưng một `@Bean` bên trong bị loại do điều kiện ở cấp phương thức.

Không nên diễn giải báo cáo `Negative matches` là lỗi: đó thường là kết quả bình thường của cơ chế chọn lọc. Cũng không nên xem `Positive matches` là bảo đảm mọi bean dự kiến đã khởi tạo thành công. Muốn kết luận về bean, cần kiểm tra context và lỗi khởi động nếu có.

Các cách điều khiển có chủ đích:

1. **Cấu hình property** khi auto-configuration hỗ trợ property bật/tắt cụ thể; tra đúng property trong tài liệu của phiên bản đang dùng.
2. **Cung cấp bean tùy chỉnh** để Boot lùi bước ở những điểm có điều kiện `@ConditionalOnMissingBean`. Không mặc định rằng mọi bean mặc định đều cho phép ghi đè theo cách này.
3. **Loại trừ một auto-configuration** bằng `@SpringBootApplication(exclude = ...)`, `excludeName` hoặc `spring.autoconfigure.exclude`. Chỉ dùng đúng tên lớp auto-configuration của phiên bản hiện tại và hiểu phạm vi loại trừ; đây không phải thao tác gỡ dependency khỏi classpath.

Ví dụ cấu hình loại trừ theo tên lớp khi thật sự cần:

~~~properties
# Ví dụ cú pháp; thay bằng fully qualified name có thật của phiên bản đang chạy.
spring.autoconfigure.exclude=com.example.autoconfigure.UnwantedAutoConfiguration
~~~

Đoạn trên chỉ minh họa cấu trúc property; `com.example.autoconfigure.UnwantedAutoConfiguration` không phải lớp mặc định có sẵn của Spring Boot. Với ứng dụng thực, hãy tìm lớp cần loại trừ trong condition report hoặc tài liệu tương ứng.

## 4. Thực hành Java 17+: mặc định, tùy chỉnh và không có bean

Ví dụ này tạo **một auto-configuration do chính ứng dụng mẫu cung cấp**, giúp nhìn trực tiếp ba khả năng mà không phụ thuộc dịch vụ bên ngoài. Sử dụng Spring Boot 4.1.2, Maven và Java 17+. Các API minh họa cũng thể hiện cơ chế auto-configuration hiện đại: đăng ký qua `AutoConfiguration.imports`, điều kiện property và khả năng lùi bước khi có bean của người dùng.

Tạo cấu trúc tệp:

~~~text
auto-config-myths/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── com/example/demo/DemoApplication.java
    │   ├── com/example/demo/GreetingService.java
    │   └── com/example/autoconfig/GreetingAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>auto-config-myths</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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

Tệp `src/main/java/com/example/demo/GreetingService.java`:

~~~java
package com.example.demo;

public interface GreetingService {
    String message();
}
~~~

Tệp `src/main/java/com/example/autoconfig/GreetingAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.demo.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return () -> "AUTO";
    }
}
~~~

Với `matchIfMissing = true`, không khai báo property `demo.greeting.enabled` vẫn cho phép xét cấu hình. Khi property là `false`, cả cấu hình này không khớp. Nếu người dùng đã đăng ký `GreetingService`, bean mặc định trong cấu hình sẽ lùi bước.

Đăng ký lớp auto-configuration trong tệp **đúng tên** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; nội dung tệp chỉ một dòng:

~~~text
com.example.autoconfig.GreetingAutoConfiguration
~~~

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.greeting",
            name = "custom",
            havingValue = "true"
    )
    GreetingService customGreetingService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner printGreeting(ObjectProvider<GreetingService> provider) {
        return args -> {
            GreetingService service = provider.getIfAvailable();
            System.out.println("GreetingService: " +
                    (service == null ? "ABSENT" : service.message()));
        };
    }
}
~~~

`ObjectProvider<GreetingService>` cho phép hỏi context về bean một cách an toàn ngay cả khi không có bean nào. Cách này giúp chạy tình huống “vắng bean” mà không tạo lỗi `NoSuchBeanDefinitionException` do tiêm bắt buộc.

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q -DskipTests package

java -jar target/auto-config-myths-1.0.0.jar
java -jar target/auto-config-myths-1.0.0.jar --demo.greeting.custom=true
java -jar target/auto-config-myths-1.0.0.jar --demo.greeting.enabled=false
~~~

Bỏ qua các dòng log khởi động (chúng phụ thuộc môi trường), dòng `System.out.println` của từng lệnh phải lần lượt là:

~~~text
GreetingService: AUTO
GreetingService: CUSTOM
GreetingService: ABSENT
~~~

Giải thích:

| Lần chạy | Điều kiện property | Có bean tùy chỉnh? | Kết quả |
| --- | --- | --- | --- |
| Mặc định | `enabled` không có, `matchIfMissing=true` | Không | Auto-configuration cung cấp `GreetingService` có giá trị `AUTO`. |
| `--demo.greeting.custom=true` | Cho phép auto-configuration | Có, giá trị `CUSTOM` | `@ConditionalOnMissingBean` làm bean mặc định lùi bước. |
| `--demo.greeting.enabled=false` | Không khớp | Không | Không có `GreetingService`, in `ABSENT`. |

**Vì sao đặt cấu hình ở package `com.example.autoconfig`?** `DemoApplication` nằm tại `com.example.demo`; component scan mặc định không quét package ngang hàng `com.example.autoconfig`. Lớp `GreetingAutoConfiguration` được nạp nhờ file `AutoConfiguration.imports`, minh họa đúng cơ chế auto-configuration. Nếu đặt nó trong package bị component scan quét, ví dụ có thể che mất sự khác biệt giữa hai cơ chế.

**Giới hạn của ví dụ:** Đây là auto-configuration mẫu do ta tự viết, không phải tuyên bố rằng Spring Boot có sẵn một bean tên `GreetingService`. Ứng dụng không cần starter web hay cơ sở dữ liệu; starter cốt lõi đủ cho ví dụ. Trong dự án thư viện thực tế, auto-configuration và starter thường nằm ở các module riêng để chia sẻ cho nhiều ứng dụng.

## 5. Ngộ nhận thứ ba: “Spring Boot thay thế Spring Framework”

**Sự thật:** Spring Boot sử dụng Spring Framework để chạy ứng dụng. Boot bổ sung các quy ước, tích hợp và cấu hình mặc định nhằm giảm công việc lặp lại.

| Trách nhiệm | Spring Framework | Spring Boot |
| --- | --- | --- |
| IoC container, bean lifecycle, dependency injection | Nền tảng trực tiếp | Dùng và tự cấu hình dựa trên nền tảng đó |
| `@Configuration`, `@Bean`, `@Component`, `@Autowired` | Cung cấp các cơ chế lõi | Vẫn sử dụng như bình thường |
| Spring MVC, xử lý giao dịch, AOP, tích hợp dữ liệu | Cung cấp hoặc làm nền cho hệ sinh thái liên quan | Cấu hình thuận tiện khi điều kiện phù hợp |
| Starter và quản lý phiên bản dependency được khuyến nghị | Không phải trọng tâm của Spring Framework | Cung cấp dependency descriptors và dependency management |
| Auto-configuration và trải nghiệm chạy ứng dụng | Có nền tảng configuration/condition/bean factory | Chọn lọc, phối hợp các auto-configuration theo môi trường |
| Các tiện ích vận hành như Actuator | Không phải chức năng lõi Spring Framework | Cung cấp qua dependency phù hợp, có cấu hình riêng |

`@SpringBootApplication` không xóa đi kiến thức về `@Configuration`, component scan, scope, proxy, bean lifecycle, bean qualification hoặc transaction. Khi gặp hai bean cùng kiểu, circular dependency, lỗi điều kiện hay component không được quét, cần phân tích theo quy tắc **Spring container** cùng với lớp cấu hình tự động của Boot.

Bạn hoàn toàn có thể viết cấu hình Spring thủ công trong một ứng dụng Boot. Ví dụ, khai báo `@Bean` cho thành phần cụ thể, thay đổi giá trị qua `@ConfigurationProperties`, dùng Spring Security, Spring Data hoặc cấu hình hạ tầng tùy chỉnh. Chỉ nên giữ mặc định Boot khi mặc định đó đáp ứng nhu cầu; nếu khác, điều chỉnh bằng cơ chế được hỗ trợ.

## 6. Chẩn đoán khi kết quả khác dự đoán

Khi “đã thêm starter nhưng bean vẫn thiếu” hoặc “tại sao bean mặc định không xuất hiện”, làm tuần tự:

1. **Xác định đúng loại bean và điều kiện kỳ vọng.** Kiểm tra bean bằng kiểu và tên cụ thể; đừng suy ra từ tên starter. Phân biệt bean không tồn tại với bean tồn tại nhưng tiêm sai qualifier.
2. **Kiểm tra dependency thực tế.** Chạy `mvn dependency:tree` hoặc `./gradlew dependencies`, xem classpath và các dependency bị loại trừ. Có starter không bảo đảm từng dependency cần thiết hiện diện nếu project đã override/exclude.
3. **Đọc condition evaluation report.** Chạy ứng dụng với tham số `--debug`; tìm tên auto-configuration và lý do positive/negative match. Chỉ đọc report từ đúng phiên bản và đúng môi trường chạy.
4. **Xem property/profile/environment.** Cấu hình ở `application.yml`, `application.properties`, profile, biến môi trường và command-line có thể làm thay đổi kết quả điều kiện. Một property sai tên hoặc không thuộc auto-configuration đang dùng sẽ không có tác dụng.
5. **Tìm bean đã khai báo thủ công.** `@Bean`, `@Component` hoặc auto-configuration khác có thể khiến `@ConditionalOnMissingBean` không khớp. Nếu dùng test slice hoặc context tùy biến, tập bean/auto-configuration cũng có thể khác ứng dụng chính.
6. **Phân biệt lý do bỏ qua với lỗi khởi tạo.** Nếu cấu hình bị loại do điều kiện không khớp, thường không có bean để tạo; nếu điều kiện khớp nhưng dependency lúc tạo bean lỗi, cần đọc exception chain và nguyên nhân gốc.
7. **Chỉ loại trừ khi hiểu hậu quả.** `spring.autoconfigure.exclude` loại lớp auto-configuration được chỉ định; nó không xóa thư viện khỏi classpath và không thay thế việc sửa property/bean cấu hình sai.

Nếu đã thêm Spring Boot Actuator và cho phép truy cập endpoint phù hợp, endpoint `conditions` cũng giúp xem báo cáo điều kiện. Việc endpoint có tồn tại, được expose hay được bảo vệ phụ thuộc cấu hình và phiên bản; không giả định nó luôn truy cập được.

Trong ví dụ ở trên, có thể chạy:

~~~bash
java -jar target/auto-config-myths-1.0.0.jar --debug
~~~

Tìm `GreetingAutoConfiguration` và `defaultGreetingService` trong báo cáo điều kiện. So sánh với các lần chạy bật `custom` hoặc tắt `enabled` để thấy điều kiện nào đổi từ khớp sang không khớp. Chi tiết log có thể thay đổi theo phiên bản Spring Boot.

## 7. Những sai lầm thực tế và cách sửa

**Sai lầm: “Thấy `spring-boot-starter-...` trong Maven là có thể `@Autowired` bất cứ interface nào của thư viện.”** Một interface trên classpath chưa phải một bean. Cần tìm lớp implementation hoặc cấu hình tạo bean, kiểm tra component scan và condition report.

**Sai lầm: “`Negative matches` nghĩa là auto-configuration hỏng.”** Các điều kiện không khớp là cơ chế bình thường để tránh bật các tích hợp không cần thiết. Chỉ coi là sự cố nếu ứng dụng yêu cầu chức năng đó.

**Sai lầm: “Có bean của tôi thì Boot luôn tự tắt mọi cấu hình cùng lĩnh vực.”** Boot thường chỉ lùi bước ở điểm có điều kiện phù hợp. Một bean tùy chỉnh có thể thay thế một mặc định nhưng những bean phụ trợ khác vẫn được đăng ký; phải xem điều kiện từng lớp/phương thức.

**Sai lầm: “Không cần học Spring nữa vì dùng Boot.”** Debug dependency injection, scopes, proxy, lifecycle, MVC và transaction vẫn cần hiểu Spring Framework. Auto-configuration chỉ giảm cấu hình lặp lại.

**Sai lầm: “Cứ exclude cả auto-configuration là giải quyết được.”** Exclude quá rộng có thể làm mất các bean mà chức năng khác cần. Ưu tiên điều chỉnh cấu hình được công bố, cung cấp bean riêng hoặc sửa dependency thực tế trước khi exclude.

## 8. Tự kiểm tra hiểu bài

1. Vì sao thêm starter không đủ để kết luận bean đã được tạo? — Vì starter trước hết bổ sung dependency; việc đăng ký bean phụ thuộc điều kiện và cấu hình của ứng dụng.
2. Khi nào `@ConditionalOnMissingBean` hữu ích? — Khi tác giả auto-configuration muốn cung cấp giá trị mặc định nhưng cho phép ứng dụng tự cung cấp bean phù hợp.
3. Report có nhiều `Negative matches` thì có bắt buộc là lỗi không? — Không. Đó có thể là kết quả bình thường của điều kiện lọc.
4. Vì sao `@SpringBootApplication` không thay thế kiến thức về IoC container? — Vì Boot vẫn dựa trên container và bean lifecycle của Spring Framework.
5. Cần quan sát gì để phân biệt “thiếu thư viện”, “property tắt”, “bean mặc định lùi bước”? — Dependency tree, condition evaluation report, nguồn property và bean trong context.

## Tài liệu tham khảo chính thức

- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Build Systems / Starters: https://docs.spring.io/spring-boot/reference/using/build-systems.html

**Ghi nhớ:** Starter đưa thư viện vào dự án; điều kiện auto-configuration quyết định cấu hình mặc định nào được áp dụng; Spring Framework vẫn là nền tảng tạo và quản lý bean bên dưới Spring Boot.