# Lệnh không được khám phá do package, bean hoặc thiếu cấu hình đăng ký

Một command Spring Shell có thể được viết đúng cú pháp nhưng không xuất hiện trong `help`, không được gọi tên trong shell hoặc trả về lỗi command không tồn tại. Nguyên nhân thường nằm ở một trong ba lớp: class chứa command không được Spring tạo thành bean, package không nằm trong vùng scan, hoặc ứng dụng chưa bật đúng cơ chế đăng ký command cho phiên bản Spring Shell đang dùng.

Khi chẩn đoán, cần xác định chính xác ứng dụng dùng Spring Shell 3.x legacy annotation, 3.x annotation model mới hay Spring Shell 4.x. Ba mô hình này có quy tắc discovery khác nhau. Đặc biệt, `@Command` trong annotation model 3.x cần cấu hình đăng ký tường minh; Spring Shell 4 dùng cơ chế tự động trong Spring Boot nhưng vẫn yêu cầu command class được Spring quản lý và không bị loại khỏi component scan.

## 1. Nhận diện đúng triệu chứng

Các triệu chứng thường gặp:

- Command không xuất hiện trong danh sách `help` hoặc `commands`.
- Gõ tên command nhận thông báo không tìm thấy command.
- Ứng dụng khởi động bình thường, nhưng chỉ có các command built-in như `help`, `quit` hoặc `version`.
- Một command class có thể inject service trong một test khác, nhưng khi chạy shell lại không thấy command.
- Command hoạt động ở máy developer nhưng biến mất khi chạy profile, module hoặc cấu hình đóng gói khác.
- Command programmatic được viết thành method nhưng không có bean `Command`/`CommandRegistration` tương ứng trong application context.

Trước tiên, phân biệt hai tình huống:

| Tình huống | Hướng kiểm tra |
|---|---|
| Command hoàn toàn không có trong help/registry | Package scan, Spring bean và command registration |
| Command có trong help nhưng không chạy được hoặc đang unavailable | Tên command, availability provider, argument/option, quyền và lỗi khi thực thi |

Đừng bắt đầu bằng cách sửa parser hoặc option nếu command còn chưa được đăng ký.

## 2. Xác định phiên bản và command model

Spring Shell có nhiều cách khai báo command. Hãy kiểm tra dependency đang được resolve và import thực tế trong source trước khi thay annotation.

| Mô hình | Class/method annotation | Cấu hình đăng ký |
|---|---|---|
| Spring Shell 3.x legacy | `@ShellComponent` trên class, `@ShellMethod` trên method | Component scan của Spring phát hiện `@ShellComponent` |
| Spring Shell 3.x annotation model mới | `@Command` trên method, có thể có `@Command` cấp class | `@EnableCommand` hoặc `@CommandScan`, kể cả khi dùng Spring Boot |
| Spring Shell 4.x với Spring Boot | `@Component`/`@Service` trên class, `@Command` trên method | Spring Boot auto-configuration tự bật command scanning |
| Spring Shell 4.x không dùng Spring Boot | Spring-managed command class, `@Command` trên method | `@EnableCommand` trên configuration class |
| Programmatic registration | Bean `Command` trong 4.x hoặc API registration tương ứng của 3.x | Command bean/registration phải được tạo trong application context |

Các import cũng khác nhau:

```java
// Spring Shell 3.x annotation model mới
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.EnableCommand;

// Spring Shell 4.x
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.EnableCommand;
```

Với Spring Shell 3.x legacy, import nằm trong `org.springframework.shell.standard`, ví dụ `ShellComponent` và `ShellMethod`. Không ghép annotation của một mô hình với registration configuration của mô hình khác.

## 3. Kiểm tra class command có phải Spring bean không

Với annotation model mới của Spring Shell 4, class chứa method `@Command` phải là Spring-managed bean. Dùng `@Component`, `@Service` hoặc một stereotype phù hợp:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(name = "project list", description = "List projects")
    public String list() {
        return "Project list";
    }
}
```

Nếu class chỉ là Java object thông thường, Spring không tạo bean và Spring Shell không thể tìm command method trong application context.

Ví dụ sai:

```java
// Không có stereotype và không được khai báo bằng @Bean.
public class ProjectCommands {

    @Command(name = "project list")
    public String list() {
        return "Project list";
    }
}
```

Nếu muốn khai báo command bằng `@Bean`, hãy dùng programmatic model với kiểu `Command` trong Spring Shell 4 như phần 10. Không tạo một object command annotation rồi giả định rằng chỉ cần khai báo bean là mọi cơ chế annotation discovery sẽ tự áp dụng.

### Trường hợp legacy 3.x

Với Spring Shell 3.3 legacy annotation, class cần `@ShellComponent` và method cần `@ShellMethod`:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(key = "project-list", value = "List projects")
    public String list() {
        return "Project list";
    }
}
```

`@ShellComponent` là stereotype được meta-annotate bằng `@Component`, vì vậy nó vừa đánh dấu bean vừa giới hạn những bean được xét để tạo shell command. Chỉ đặt `@ShellMethod` trên một class không được Spring phát hiện thì chưa đủ.

## 4. Kiểm tra package có nằm trong component scan không

`@SpringBootApplication` bao gồm component scanning bắt đầu từ package của class application và đi xuống các package con. Nếu command nằm ngoài cây package này, bean có thể không được tạo.

Ví dụ cấu trúc:

```text
com.acme.catalog
  CatalogApplication.java
  service/
  repository/

com.acme.cli.commands
  ProjectCommands.java
```

Nếu `CatalogApplication` nằm trong `com.acme.catalog`, package `com.acme.cli.commands` không phải package con nên không tự động được scan.

### Cách 1: Đặt application class ở package gốc chung

```text
com.acme
  CatalogApplication.java
  catalog/
  cli/commands/
```

Đây thường là cấu trúc đơn giản nhất khi các module thuộc cùng một ứng dụng.

### Cách 2: Khai báo base package tường minh

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(basePackages = {
        "com.acme.catalog",
        "com.acme.cli.commands"
})
public class CatalogApplication {
}
```

Để tránh lỗi do đổi package khi refactor, có thể dùng `basePackageClasses`:

```java
@SpringBootApplication
@ComponentScan(basePackageClasses = {
        CatalogApplication.class,
        ProjectCommands.class
})
public class CatalogApplication {
}
```

`basePackageClasses` lấy package từ các class marker nên an toàn hơn chuỗi package khi đổi tên package.

### Cách 3: Import một command class cụ thể

Khi chỉ có một số class nằm ngoài component scan, có thể dùng `@Import` để đưa class đó vào application context:

```java
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(ProjectCommands.class)
public class CatalogApplication {
}
```

`ProjectCommands` vẫn cần là class phù hợp để Spring tạo bean và các dependency constructor của nó phải được đáp ứng.

## 5. Kiểm tra component scan có loại command package không

Một cấu hình `@ComponentScan` có thể có `excludeFilters`. Nếu filter loại package hoặc stereotype của command, Spring không tạo bean dù class nằm dưới package gốc.

Ví dụ cần kiểm tra:

```java
@ComponentScan(
        basePackages = "com.acme",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com\\.acme\\.cli\\.commands\\..*"))
class ApplicationComponentScan {
}
```

Filter trên loại package command ra khỏi scan. Bỏ filter hoặc thu hẹp pattern để command class được phát hiện.

Rà soát các cấu hình sau:

- `@ComponentScan` trên application class hoặc configuration class.
- `excludeFilters` loại `@Component`, `@Service` hoặc package command.
- `useDefaultFilters = false` khiến stereotype mặc định không còn được quét.
- Các module cấu hình scan riêng trong test và production.
- `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnClass` hoặc condition khác khiến bean không được tạo ở profile hiện tại.

Nếu command bean chỉ biến mất ở một môi trường, so sánh active profiles và điều kiện tạo bean trước khi thay đổi code command.

## 6. Với annotation model 3.x, đừng quên EnableCommand hoặc CommandScan

Đây là nguyên nhân rất phổ biến khi dùng annotation model mới trong Spring Shell 3.x: `@Command` chỉ đánh dấu candidate method, nhưng bản thân nó không đăng ký target class.

### Đăng ký class tường minh bằng `@EnableCommand`

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.EnableCommand;

@Configuration(proxyBeanMethods = false)
@EnableCommand(ProjectCommands.class)
public class ShellCommandConfiguration {
}
```

Có thể truyền nhiều class:

```java
@EnableCommand({
        ProjectCommands.class,
        UserCommands.class,
        ReportCommands.class
})
@Configuration(proxyBeanMethods = false)
public class ShellCommandConfiguration {
}
```

Kiểm tra class command có nằm trong danh sách hay không. Nếu vừa tạo `BillingCommands` nhưng quên thêm vào `@EnableCommand`, các command khác vẫn hoạt động còn command mới thì không xuất hiện.

### Scan một package bằng `@CommandScan`

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.CommandScan;

@Configuration(proxyBeanMethods = false)
@CommandScan(basePackages = "com.acme.cli.commands")
public class ShellCommandConfiguration {
}
```

Có thể dùng `basePackageClasses` để tránh chuỗi package:

```java
@Configuration(proxyBeanMethods = false)
@CommandScan(basePackageClasses = ProjectCommands.class)
public class ShellCommandConfiguration {
}
```

Nếu không khai báo package rõ ràng, `@CommandScan` scan từ package của class mang annotation. Đặt configuration class ở package quá hẹp có thể khiến command package khác bị bỏ sót.

Trong Spring Shell 3.x annotation model mới, các cấu hình này vẫn cần thiết ngay cả khi ứng dụng dùng Spring Boot. Đừng nhầm với cơ chế Spring Shell 4.

## 7. Với Spring Shell 4, kiểm tra đúng cấu hình theo loại ứng dụng

### Ứng dụng Spring Boot

Spring Shell 4 tự bật command scanning thông qua auto-configuration khi dùng Spring Boot. Không cần thêm `@EnableCommand` hoặc `@CommandScan` chỉ để kích hoạt scanning.

Tuy nhiên, command class vẫn phải là Spring bean và phải nằm trong component scan:

```java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}

@Component
class ProjectCommands {
    @Command(name = "project list")
    public String list() {
        return "Project list";
    }
}
```

Nếu ứng dụng chỉ thêm `spring-shell-core` mà không có module auto-configuration hoặc starter tương ứng, Boot auto-configuration có thể không được nạp. Spring Shell 4 tách `spring-shell-core-autoconfigure` khỏi core; kiểm tra dependency tree và đảm bảo starter/module Boot phù hợp với phiên bản đang dùng.

### Ứng dụng Spring Framework không dùng Spring Boot

Với ứng dụng không dùng Boot, phải bật command discovery tường minh:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration(proxyBeanMethods = false)
@EnableCommand(ProjectCommands.class)
public class ShellCommandConfiguration {
}
```

Nếu thiếu `@EnableCommand`, method `@Command` có thể nằm trong một class hợp lệ nhưng không được đăng ký vào shell.

## 8. Đừng trộn package annotation giữa các phiên bản

Một dự án có thể compile nhờ dependency còn sót lại nhưng dùng annotation từ package khác phiên bản đang chạy. Hãy kiểm tra import ở command class và dependency tree.

| Phiên bản | Import `@Command` |
|---|---|
| Spring Shell 3.x annotation model | `org.springframework.shell.command.annotation.Command` |
| Spring Shell 4.x | `org.springframework.shell.core.command.annotation.Command` |
| Spring Shell 3.x legacy | `org.springframework.shell.standard.ShellMethod` (không dùng `@Command`) |

Spring Shell 4 đã loại bỏ annotation legacy `@ShellComponent`, `@ShellMethod` và `@ShellOption`. Khi nâng cấp, chuyển sang annotation model 4.x thay vì giữ import cũ rồi chỉ thay dependency.

Kiểm tra dependency đang được resolve:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
```

Hoặc với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-shell --configuration runtimeClasspath
```

Đảm bảo không có nhiều major version Spring Shell cùng xuất hiện do dependency bắc cầu hoặc module cũ còn được khai báo.

## 9. Kiểm tra bean có được tạo thành công không

Một command class có thể nằm trong package scan nhưng vẫn không xuất hiện nếu quá trình tạo bean thất bại. Các nguyên nhân thường gặp:

- Constructor injection thiếu service/repository bean.
- Dependency bị loại khỏi profile hiện tại.
- `@ConditionalOnProperty` không thỏa điều kiện.
- Bean phụ thuộc class không có trên runtime classpath.
- Hai bean cùng tên gây xung đột.
- Circular dependency làm context khởi tạo thất bại.

Tìm các lỗi startup như `BeanCreationException`, `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException` hoặc lỗi condition. Không bỏ qua lỗi khởi động chỉ vì ứng dụng vẫn có thể chạy một phần hoặc log shell đã xuất hiện.

Có thể kiểm tra bean bằng `ApplicationContext` trong test:

```java
@SpringBootTest
class ProjectCommandBeanTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void commandClassIsRegisteredAsBean() {
        assertThat(applicationContext.getBeansOfType(ProjectCommands.class))
                .hasSize(1);
    }
}
```

Nếu assertion thất bại, tập trung vào component scan, stereotype, profile và điều kiện bean. Chưa cần kiểm tra parser hoặc completion.

## 10. Nếu dùng programmatic registration, kiểm tra đúng bean registration

Không phải mọi ứng dụng đều dùng annotation. Spring Shell hỗ trợ khai báo command theo cách programmatic.

Trong Spring Shell 4, khai báo bean có kiểu `Command`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration(proxyBeanMethods = false)
public class ProgrammaticCommands {

    @Bean
    Command pingCommand() {
        return Command.builder()
                .name("system ping")
                .execute(context ->
                        context.outputWriter().println("PONG"));
    }
}
```

Spring Shell 4 tự nạp các bean `Command` trong application context vào `CommandRegistry`. Nếu command không xuất hiện, kiểm tra configuration class có được import/scan không và factory method có thực sự tạo bean hay không.

Với Spring Shell 3.x, programmatic model dùng API `CommandRegistration` và `CommandCatalog`. Đừng sao chép code `Command.builder()` của 4.x vào dự án 3.3; kiểm tra đúng API của version 3.x đang chạy và bảo đảm registration/catalog customizer được khai báo thành bean.

## 11. Xác nhận command có trong registry sau khi context khởi tạo

Trong Spring Shell 4, `CommandRegistry` là nơi giữ các command đã được biết đến. Có thể kiểm tra trực tiếp bằng integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.core.command.CommandRegistry;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ProjectCommandRegistrationTests {

    @Autowired
    CommandRegistry commandRegistry;

    @Test
    void projectListIsRegistered() {
        assertThat(commandRegistry.getCommandByName("project list"))
                .isNotNull();
    }
}
```

`CommandRegistry` cũng có `getCommands()` và `getCommandsByPrefix(...)` để kiểm tra danh sách command. Dùng registry test để phân biệt lỗi bean discovery với lỗi thực thi command.

Nếu bean class tồn tại nhưng `getCommandByName(...)` trả `null`, hãy kiểm tra annotation trên method, package import, command scanning và lỗi tạo command registration. Nếu registry có command nhưng `help` không hiển thị như mong đợi, kiểm tra trạng thái hidden/availability và group/help customization.

Trong Spring Shell 3.x, API registry/catalog khác với 4.x. Dùng `CommandCatalog` và API `CommandRegistration` đúng version thay vì import `CommandRegistry` từ package 4.x.

## 12. Kiểm tra tên command và trạng thái availability

Sau khi xác nhận command đã được đăng ký, kiểm tra tên thực tế:

- Với legacy `@ShellMethod`, command key có thể được suy ra từ tên method nếu không khai báo `key`.
- Với annotation model 3.x, kiểm tra thuộc tính `command` và alias.
- Với Spring Shell 4, kiểm tra `@Command(name = ...)` và `alias`.
- Với programmatic command, kiểm tra tên trong builder/registration.

Một command có tên `project-list` không thể gọi bằng `project list` nếu không khai báo tên hoặc alias tương ứng. Kiểm tra help output để lấy tên mà shell đã đăng ký.

Nếu command có trong registry nhưng không thể gọi, kiểm tra availability:

- Spring Shell 3.x có thể dùng `@CommandAvailability` hoặc cơ chế availability tương ứng.
- Spring Shell 4 dùng `availabilityProvider` trên `@Command`.

Availability thường khiến command không khả dụng theo trạng thái hiện tại. Hãy kiểm tra lý do availability và dependency mà provider cần trước khi kết luận command chưa được khám phá.

## 13. Checklist chẩn đoán theo thứ tự

Thực hiện lần lượt để tìm đúng lớp gây lỗi:

1. **Xác định version.** Kiểm tra Spring Shell 3.x hay 4.x và chọn đúng annotation model.
2. **Kiểm tra import.** Legacy 3.x, annotation 3.x và annotation 4.x dùng package khác nhau.
3. **Kiểm tra method annotation.** Method có `@ShellMethod` hoặc `@Command` đúng version không?
4. **Kiểm tra bean.** Class có `@ShellComponent`, `@Component`, `@Service` hoặc được khai báo bằng `@Bean` không?
5. **Kiểm tra package scan.** Package command có nằm trong component scan không?
6. **Kiểm tra exclude filters.** Có filter, profile hoặc condition loại bean không?
7. **Kiểm tra registration config.** Annotation model 3.x cần `@EnableCommand`/`@CommandScan`; Spring Shell 4 Boot auto-config; Spring Shell 4 non-Boot cần `@EnableCommand`.
8. **Kiểm tra dependency.** Có starter/autoconfigure module phù hợp không?
9. **Kiểm tra startup logs.** Bean có tạo thành công và dependency có được inject không?
10. **Kiểm tra registry/help.** Command đã có trong registry chưa và tên đăng ký là gì?
11. **Kiểm tra availability.** Nếu command đã đăng ký, xem provider có đang đánh dấu unavailable không.
12. **Kiểm tra programmatic path.** Nếu không dùng annotation, bean registration/catalog có được tạo không?

## 14. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ thấy built-in command | Command class không được scan hoặc registration chưa bật | Kiểm tra bean và cơ chế đăng ký theo version |
| `@Command` có nhưng command không xuất hiện trong 3.x | Thiếu `@EnableCommand` hoặc `@CommandScan` | Đăng ký target class hoặc package scan |
| Command 4.x không xuất hiện trong Spring Boot | Class không phải bean hoặc bị loại khỏi component scan | Dùng `@Component`, sửa scan base package/filter |
| Spring Shell 4 non-Boot không tìm command | Thiếu `@EnableCommand` | Thêm annotation vào configuration class |
| Command class nằm ngoài package application | Boot component scan không đi tới package đó | Dùng package gốc chung, `basePackageClasses` hoặc `@Import` |
| Bean không được tạo | Dependency injection hoặc condition thất bại | Đọc `BeanCreationException`, kiểm tra profile và dependency |
| Command mới không được phát hiện sau refactor | `excludeFilters` hoặc `useDefaultFilters=false` | Sửa component scan filters |
| Command không compile sau nâng version | Import annotation sai major version | Dùng package tương ứng Spring Shell đang dùng |
| Chỉ chạy được trên máy dev | Profile hoặc dependency runtime khác nhau | So sánh active profile và runtime dependency tree |
| Bean có nhưng registry không có command | Annotation/registration model không khớp | Kiểm tra `@Command`, `@EnableCommand`, auto-config hoặc programmatic bean |
| Registry có nhưng help không thấy | Hidden/availability/group/help customization | Kiểm tra metadata và availability provider |
| Command gọi sai tên | Tên method, command name và alias khác nhau | Dùng tên hiển thị trong help hoặc khai báo alias |
| Chỉ có một số command trong cùng package | `@EnableCommand` liệt kê thiếu class hoặc điều kiện bean khác nhau | Kiểm tra target list và từng bean condition |
| Programmatic command không xuất hiện | Factory method không được scan/import hoặc dùng sai API version | Kiểm tra bean `Command` (4.x) hoặc registration/catalog (3.x) |
| Spring Boot 4 không auto-discover | Chỉ có `spring-shell-core`, thiếu Boot integration | Thêm starter hoặc `spring-shell-core-autoconfigure` |

## 15. Checklist trước khi kết thúc xử lý

- [ ] Đã xác nhận version Spring Shell và command model.
- [ ] Đã dùng đúng package annotation cho version đó.
- [ ] Class command được tạo thành Spring bean.
- [ ] Method có annotation command đúng version.
- [ ] Package command nằm trong component scan hoặc được import rõ ràng.
- [ ] Không có `excludeFilters` loại command package/stereotype.
- [ ] Profile và condition cho phép bean được tạo.
- [ ] Annotation model 3.x có `@EnableCommand` hoặc `@CommandScan`.
- [ ] Spring Shell 4 Boot có auto-configuration/starter cần thiết.
- [ ] Spring Shell 4 non-Boot có `@EnableCommand`.
- [ ] Programmatic command được khai báo thành bean bằng API đúng version.
- [ ] Không có lỗi tạo bean hoặc dependency injection trong startup logs.
- [ ] Command xuất hiện trong registry/help với tên mong đợi.
- [ ] Availability provider không chặn command ngoài dự kiến.
- [ ] Integration test xác nhận command được đăng ký trong context thực tế.

## Tài liệu tham khảo

1. [Spring Shell 4.0.4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) – component scan, annotation registration, `@EnableCommand`, programmatic command bean và `CommandRegistry`.
2. [Spring Shell 3.3.4 – Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html) – điều kiện `@ShellComponent` và `@ShellMethod` để tạo command legacy.
3. [Spring Shell 3.3 – Annotation Model](https://docs.spring.io/spring-shell/reference/3.3-SNAPSHOT/commands/registration/annotation.html) – `@Command` cần `@EnableCommand` hoặc `@CommandScan` để đăng ký target.
4. [Spring Shell 4 – `@EnableCommand` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/EnableCommand.html) – khai báo candidate class cho command discovery ngoài Boot.
5. [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – khác biệt registration giữa 3.x và 4.x, module auto-configuration và component bean.
6. [Spring Boot – Using the `@SpringBootApplication` Annotation](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html) – component scan mặc định bắt đầu từ package của application class.
7. [Spring Framework – Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html) – stereotype, component scan filters và khai báo bean.

Khi một command không được khám phá, hãy lần theo chuỗi: đúng annotation và package, class có mặt trong application context, registration được bật theo đúng phiên bản, rồi xác nhận command xuất hiện trong registry. Cách kiểm tra theo từng lớp giúp xác định chính xác lỗi nằm ở source code, component scan, bean creation hay cấu hình Spring Shell.
