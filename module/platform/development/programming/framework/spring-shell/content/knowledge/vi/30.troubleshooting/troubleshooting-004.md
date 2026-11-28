# Dùng annotation đúng tên nhưng sai package hoặc thế hệ

Spring Shell có nhiều thế hệ annotation cùng tồn tại trong một số phiên bản. Vì vậy, một import có tên gần đúng vẫn có thể trỏ tới API khác. Ví dụ, Spring Shell 3.3 có `@Command` trong package `org.springframework.shell.command.annotation`, đồng thời có bộ annotation cũ `@ShellComponent`, `@ShellMethod`, `@ShellOption` trong `org.springframework.shell.standard`. Spring Shell 4 chuyển bộ annotation mới sang package `org.springframework.shell.core.command.annotation` và loại bỏ các annotation `@Shell...` cũ.

Lỗi thường xuất hiện theo hai dạng: mã không biên dịch vì annotation hoặc thuộc tính không tồn tại; hoặc mã biên dịch nhưng command không xuất hiện trong `help` vì annotation thuộc mô hình đăng ký khác. Cách chẩn đoán đúng là xác định phiên bản Spring Shell thực tế, kiểm tra fully qualified name của annotation rồi kiểm tra cơ chế đăng ký command.

Bài học tập trung vào Spring Shell 3.3.x và 4.0.x. Các ví dụ phải được dùng theo đúng thế hệ thư viện tương ứng.

## 1. Xác định phiên bản Spring Shell trước khi sửa import

Không suy ra phiên bản từ tên starter hoặc phiên bản Spring Boot trong file build. Phiên bản có thể bị ghi đè bởi BOM, dependency management hoặc một dependency bắc cầu. Hãy xem phiên bản thực tế mà build tool phân giải.

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
```

Trên Windows:

```powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.shell
```

Với Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-shell-core \
  --configuration runtimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat dependencyInsight --dependency spring-shell-core --configuration runtimeClasspath
```

Kiểm tra tất cả module Spring Shell đang được phân giải. Các module Spring Shell nên thuộc cùng một dòng phiên bản; tránh tình trạng `spring-shell-core` là 4.x nhưng một module khác vẫn là 3.x.

Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4+ khi dùng tích hợp Spring Boot. Nếu dự án vẫn ở Spring Boot 3, hãy dùng dòng Spring Shell 3.x tương thích hoặc lập kế hoạch nâng cấp nền tảng trước khi chuyển annotation sang 4.x.

## 2. Bản đồ package và annotation theo thế hệ

Có hai mô hình annotation khác nhau trong Spring Shell 3.3. Đến Spring Shell 4, mô hình annotation mới được giữ lại với package và một số thuộc tính thay đổi.

| Thế hệ | Annotation command | Annotation tham số | Package chính | Trạng thái |
|---|---|---|---|---|
| Spring Shell 3.3 — legacy | `@ShellComponent`, `@ShellMethod` | `@ShellOption` | `org.springframework.shell.standard` | Còn dùng được trong 3.x, đã bị deprecated trong quá trình chuyển đổi |
| Spring Shell 3.3 — mô hình mới | `@Command` | `@Option` | `org.springframework.shell.command.annotation` | Mô hình mới, cần đăng ký command rõ ràng |
| Spring Shell 4.x | `@Command`, `@CommandGroup` | `@Option`, `@Argument`, `@Arguments` | `org.springframework.shell.core.command.annotation` | Mô hình annotation hiện hành |

Các tên sau đây không thể thay thế cho nhau chỉ vì chúng có ý nghĩa tương tự:

- `@ShellMethod` và `@Command` là hai annotation khác nhau.
- `@ShellOption` và `@Option` là hai annotation khác nhau.
- `org.springframework.shell.command.annotation.Command` là package của mô hình mới trong Spring Shell 3.3.
- `org.springframework.shell.core.command.annotation.Command` là package của mô hình mới trong Spring Shell 4.

Khi IDE tự động import annotation, hãy đọc cả package chứ đừng chỉ nhìn tên ngắn hiển thị trên dòng code.

## 3. Spring Shell 3.3 có hai mô hình annotation

### 3.1. Mô hình legacy: ShellComponent, ShellMethod và ShellOption

Mô hình này dùng các annotation trong `org.springframework.shell.standard`.

Ví dụ:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class LegacyCatalogCommands {

    @ShellMethod(
        key = "catalog-show",
        value = "Hiển thị thông tin một mục trong catalog."
    )
    public String show(
            @ShellOption(value = "--id") String id) {
        return "Catalog item: " + id;
    }
}
```

Quy tắc đăng ký của mô hình legacy:

- Class phải mang `@ShellComponent`.
- Method command phải mang `@ShellMethod`.
- Tham số tùy chỉnh cách bind bằng `@ShellOption`.
- `@ShellComponent` là stereotype được meta-annotated bằng `@Component`, đồng thời giới hạn các bean được xét là command target.

Nếu chỉ thêm `@ShellMethod` vào một class `@Component` thông thường, mô hình legacy có thể không nhận class đó vì bộ đăng ký tìm các bean được đánh dấu `@ShellComponent`.

### 3.2. Mô hình mới: Command và Option

Spring Shell 3.3 cũng có mô hình annotation mới. Package của mô hình này là `org.springframework.shell.command.annotation`.

Ví dụ dùng command prefix ở cấp class:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@Command(command = "catalog")
public class CatalogCommands {

    @Command(command = "show")
    public String show(
            @Option(longNames = "id", required = true) String id) {
        return "Catalog item: " + id;
    }
}
```

Trong Spring Shell 3.3:

- `@Command` có thể đặt trên class hoặc method.
- Thuộc tính tên command là `command`.
- `@Command` ở class có thể cung cấp prefix và cấu hình chung cho method command.
- `@Option` đặt trên tham số và dùng `longNames` hoặc `shortNames`.
- Chỉ đặt `@Command` không tự động đăng ký command target.

Cần bật đăng ký bằng `@EnableCommand` hoặc `@CommandScan`. Ví dụ đăng ký class cụ thể:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.EnableCommand;

@Configuration
@EnableCommand(CatalogCommands.class)
public class ShellCommandConfiguration {
}
```

Hoặc quét package:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.CommandScan;

@Configuration
@CommandScan(basePackages = "com.example.catalog.shell")
public class ShellCommandConfiguration {
}
```

`@ComponentScan` và `@CommandScan` giải quyết hai nhiệm vụ khác nhau. `@ComponentScan` tìm Spring bean; `@CommandScan` tìm command target của mô hình annotation mới. Không nên mặc định rằng một annotation sẽ thay thế annotation còn lại.

## 4. Spring Shell 4 chuyển package và thay đổi cách khai báo

Trong Spring Shell 4, mô hình annotation mới chuyển sang package `org.springframework.shell.core.command.annotation`.

Ví dụ:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class CatalogCommands {

    @Command(name = "catalog show")
    public String show(
            @Option(longName = "id", shortName = 'i', required = true)
            String id) {
        return "Catalog item: " + id;
    }
}
```

Các điểm khác với mô hình mới trong 3.3:

- Import `Command` chuyển từ `org.springframework.shell.command.annotation` sang `org.springframework.shell.core.command.annotation`.
- `@Command` chỉ được đặt trên method; không dùng `@Command` trên class để làm prefix.
- Thuộc tính `command` đổi thành `name`.
- `@Option` dùng `longName` và `shortName` ở dạng đơn; không dùng `longNames` hoặc `shortNames`.
- Class chứa method command phải là Spring bean, ví dụ `@Component` hoặc `@Service`.

Nếu cần nhóm command theo prefix ở cấp class, Spring Shell 4.0.2+ cung cấp `@CommandGroup`:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(
    prefix = "catalog",
    name = "Catalog commands"
)
public class CatalogCommands {

    @Command(name = "show", description = "Hiển thị một mục catalog.")
    public String show(
            @Option(longName = "id", required = true) String id) {
        return "Catalog item: " + id;
    }
}
```

Khi chạy command, tên đầy đủ là `catalog show`. `@CommandGroup` thay vai trò gom command và prefix mà `@Command` cấp class từng đảm nhiệm trong mô hình 3.x.

### 4.1. Đăng ký command trong Spring Shell 4

Nếu dùng Spring Boot, Spring Shell 4 tự bật command scanning. Class command vẫn phải là Spring bean và không được loại khỏi component scan.

Nếu không dùng Spring Boot, bật đăng ký bằng `@EnableCommand`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration
@EnableCommand(CatalogCommands.class)
public class ShellCommandConfiguration {
}
```

`@CommandScan` thuộc mô hình 3.x đã bị loại bỏ trong Spring Shell 4. Không sao chép nguyên cấu hình scan từ dự án 3.3 sang dự án 4 mà không kiểm tra lại API.

## 5. Chuyển đổi các thuộc tính thường bị nhầm

Bảng sau giúp xác định lỗi khi tên annotation đúng nhưng thuộc tính không còn tồn tại:

| Spring Shell 3.3 — mô hình mới | Spring Shell 4.x | Ghi chú |
|---|---|---|
| `@Command(command = "catalog show")` | `@Command(name = "catalog show")` | Đổi `command` thành `name` |
| `@Command` trên class để đặt prefix | `@CommandGroup(prefix = "catalog")` | `@Command` 4.x chỉ dành cho method |
| `@Option(longNames = "id")` | `@Option(longName = "id")` | 4.x nhận một tên dài |
| `@Option(shortNames = 'i')` | `@Option(shortName = 'i')` | 4.x nhận một tên ngắn |
| `@Option(longNames = {"id", "item"})` | Chọn một `longName` | Mỗi option 4.x chỉ có một tên dài |
| `@CommandScan` | Không dùng trong Boot 4 | Boot tự bật scan; non-Boot dùng `@EnableCommand` |

Mô hình legacy của 3.3 có bảng thuộc tính riêng:

| Legacy annotation | Thuộc tính thường gặp |
|---|---|
| `@ShellMethod` | `key`, `value`, `group`, `prefix` |
| `@ShellOption` | `value`, `defaultValue`, `arity`, `help` |
| `@ShellComponent` | `value` |

Không thay tên thuộc tính theo cảm tính. Ví dụ, `key` của `@ShellMethod` không phải là `name` của `@Command`; chúng thuộc hai API khác nhau và được xử lý bởi hai bộ đăng ký khác nhau.

## 6. Vì sao annotation đúng tên nhưng command không xuất hiện?

Lỗi runtime thường không phải do cú pháp Java. Nguyên nhân thường là class hoặc method chưa được bộ đăng ký của mô hình đang dùng phát hiện.

### Trường hợp A: Dùng mô hình mới 3.3 nhưng quên EnableCommand hoặc CommandScan

Code biên dịch nhưng `help` không liệt kê command. Kiểm tra cấu hình có một trong hai annotation sau:

```java
@EnableCommand(CatalogCommands.class)
```

hoặc:

```java
@CommandScan(basePackages = "com.example.catalog.shell")
```

Nếu dùng Spring Boot 3.x với mô hình mới 3.3, vẫn cần khai báo đăng ký theo hướng dẫn của Spring Shell 3.3.

### Trường hợp B: Dùng ShellMethod trên class chỉ có Component

Với mô hình legacy, class cần `@ShellComponent`. `@Component` đơn thuần không thay thế điều kiện nhận diện legacy command target.

### Trường hợp C: Dùng Command 4.x trên class không phải Spring bean

Trong Spring Shell 4, method `@Command` phải nằm trong một class được đăng ký trong ApplicationContext. Kiểm tra `@Component`, `@Service` hoặc một cách khai báo bean tương đương và xác nhận package của class nằm trong phạm vi component scan.

### Trường hợp D: Component scan loại nhầm package

Nếu dự án dùng `@ComponentScan` với `excludeFilters`, kiểm tra xem package chứa class command có bị loại không. Một class bị loại khỏi ApplicationContext không thể trở thành command target trong mô hình 4.x.

### Trường hợp E: Dùng lẫn hai mô hình annotation

Ví dụ không nên ghép `@ShellComponent` trên class với `@Command` trên method rồi mong hai registrar phối hợp tự động. Chọn một mô hình cho nhóm command đó:

- Legacy 3.3: `@ShellComponent` + `@ShellMethod` + `@ShellOption`.
- Mô hình mới 3.3: `@Command` + `@Option` + `@EnableCommand` hoặc `@CommandScan`.
- Spring Shell 4: `@Component` + `@Command` + `@Option`, dùng `@CommandGroup` nếu cần prefix ở class.

## 7. Chẩn đoán theo thông báo lỗi

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
|---|---|---|
| `package ... does not exist` | Dependency không chứa package của thế hệ đang import | Kiểm tra phiên bản được resolve và starter/module |
| `cannot find symbol: ShellComponent` | Đang dùng Spring Shell 4, nơi legacy annotation đã bị loại | Chuyển sang `@Component` và `@Command` |
| `cannot find symbol: command()` | Import `@Command` 4.x nhưng dùng thuộc tính 3.3 | Đổi sang `name` |
| `cannot find symbol: name()` | Import `@Command` 3.3 nhưng viết cú pháp 4.x | Dùng `command` hoặc nâng cấp API/dependency đồng bộ |
| `cannot find symbol: longNames()` | Dùng `@Option` 4.x nhưng viết thuộc tính 3.3 | Đổi thành `longName` |
| `cannot find symbol: longName()` | Dùng `@Option` 3.3 nhưng viết thuộc tính 4.x | Dùng `longNames` |
| `annotation type not applicable to this kind of declaration` | Đặt annotation lên class hoặc method không được API thế hệ đó hỗ trợ | Kiểm tra `@Target` trong Javadoc của đúng version |
| Build thành công nhưng `help` không thấy command | Sai registrar, class không phải bean hoặc package bị loại khỏi scan | Kiểm tra cơ chế đăng ký theo mô hình |
| Có hai command cùng tên hoặc option bind sai | Hai mô hình hoặc hai registrar cùng đăng ký command | Tìm annotation trùng và giữ một cách khai báo nhất quán |

Thông báo compiler thường chỉ ra tên thuộc tính hoặc kiểu annotation bị sai. Với lỗi runtime, hãy kiểm tra đăng ký command và Spring bean trước khi đổi tên method.

## 8. Quy trình kiểm tra import trong IDE

Khi IDE tự thêm import, làm lần lượt:

1. Đặt con trỏ trên `@Command`, `@Option` hoặc `@ShellMethod`.
2. Dùng Go to Declaration/Go to Definition.
3. Đọc package đầy đủ của annotation được mở.
4. Kiểm tra Javadoc có đúng phiên bản dependency đang resolve không.
5. So sánh thuộc tính annotation với Javadoc của chính package đó.
6. Xóa import sai và thêm import đầy đủ đúng thế hệ.
7. Rebuild project để phát hiện lỗi compile còn lại.

Không dựa vào tên lớp hiển thị trong autocomplete. Một IDE có thể gợi ý annotation cùng tên từ module khác đang nằm trên classpath.

Tránh wildcard import cho các package annotation khi dự án có nhiều thư viện cùng định nghĩa `@Command`, `@Option` hoặc `@Argument`. Import tường minh giúp reviewer nhìn thấy ngay API đang sử dụng.

## 9. Quy trình kiểm tra dependency và classpath

Nếu package đúng theo tài liệu nhưng compiler vẫn không tìm thấy, kiểm tra classpath.

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
./mvnw -q -DskipTests compile
```

Với Gradle:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew compileJava
```

Các điểm cần xác minh:

- Starter hoặc module Spring Shell có trong dependency graph.
- Các module Spring Shell dùng cùng một phiên bản.
- BOM/parent không ghi đè phiên bản ngoài dự kiến.
- IDE đã refresh Maven/Gradle sau khi thay đổi build file.
- Không có dependency cũ được thêm thủ công khiến package từ hai thế hệ cùng xuất hiện.
- Spring Boot và Spring Shell thuộc dòng tương thích.

Nếu `dependency:tree` hoặc `dependencyInsight` cho thấy nhiều phiên bản, giải quyết dependency management trước rồi mới sửa import. Đổi import trong khi classpath còn trộn phiên bản thường chỉ tạo ra một lỗi khác.

## 10. Chuyển một command legacy 3.3 sang mô hình mới

Ví dụ legacy:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class LegacyCatalogCommands {

    @ShellMethod(
        key = "catalog-show",
        value = "Hiển thị một mục catalog."
    )
    public String show(
            @ShellOption(value = "--id") String id) {
        return "Catalog item: " + id;
    }
}
```

Chuyển sang mô hình annotation mới trong Spring Shell 3.3:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@Command(command = "catalog")
public class CatalogCommands {

    @Command(command = "show")
    public String show(
            @Option(longNames = "id", required = true) String id) {
        return "Catalog item: " + id;
    }
}
```

Sau khi chuyển, thêm `@EnableCommand(CatalogCommands.class)` hoặc `@CommandScan(...)` vào cấu hình 3.3. Command mới có tên `catalog show`; hãy cập nhật script, tài liệu và test nếu tên command cũ là `catalog-show`.

Chuyển sang Spring Shell 4:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(prefix = "catalog", name = "Catalog commands")
public class CatalogCommands {

    @Command(name = "show", description = "Hiển thị một mục catalog.")
    public String show(
            @Option(longName = "id", required = true) String id) {
        return "Catalog item: " + id;
    }
}
```

Khi chuyển lên 4.x, đồng thời cập nhật Spring Boot lên 4+ và kiểm tra dependency/module theo migration guide. Không chỉ thay import rồi giữ nguyên toàn bộ cấu hình 3.3.

## 11. Kiểm tra sau khi sửa

Sau khi build thành công, kiểm tra command có thật sự được đăng ký:

1. Khởi động ứng dụng bằng cấu hình tương ứng.
2. Chạy `help` và tìm command mới.
3. Chạy command với tham số hợp lệ.
4. Chạy command thiếu tham số bắt buộc để kiểm tra thông báo validation.
5. Chạy command với option dạng dài và dạng ngắn nếu có khai báo.
6. Kiểm tra alias hoặc prefix nếu command được nhóm.
7. Chạy test command registration hiện có.

Ví dụ với command trong phần trước:

```text
help
catalog show --id=42
catalog show -i 42
```

Nếu command không xuất hiện trong `help`, hãy quay lại kiểm tra registrar và bean discovery. Nếu command có trong `help` nhưng parse option sai, kiểm tra annotation tham số và tên option.

## 12. Những thay đổi cần chú ý khi nâng cấp lên Spring Shell 4

Ngoài package annotation, migration từ 3.x sang 4.x còn có các thay đổi ảnh hưởng tới command registration:

- Spring Shell 4 dựa trên Spring Framework 7 và Spring Boot 4+.
- `spring-shell-standard` và `spring-shell-standard-commands` được hợp nhất vào `spring-shell-core`.
- Các annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` và annotation liên quan đã bị loại bỏ.
- Package mô hình annotation mới chuyển sang `org.springframework.shell.core.command.annotation`.
- `@Command` chỉ áp dụng cho method; dùng `@CommandGroup` để gom command theo prefix từ Spring Shell 4.0.2+.
- `@Command(command = ...)` đổi thành `@Command(name = ...)`.
- `@Option(longNames = ..., shortNames = ...)` đổi thành `@Option(longName = ..., shortName = ...)`.
- Khi dùng Spring Boot, command scanning được bật tự động; `@CommandScan` bị loại bỏ. Với ứng dụng không dùng Boot, vẫn dùng `@EnableCommand`.
- Các API test cũ như `ShellWriteSequence` và một số annotation test cũng có thay đổi hoặc bị loại bỏ; cập nhật test theo API tương ứng.

Đọc migration guide theo đúng phiên bản đích trước khi chuyển toàn bộ dự án. Đừng trộn dependency 3.x với API 4.x trong cùng source set.

## 13. Các lỗi thường gặp và cách tránh

**Chỉ nhìn tên annotation mà bỏ qua package.** `@Command` ở 3.3 và 4.x có package khác nhau. Luôn kiểm tra import đầy đủ.

**Nghĩ Spring Shell 3.3 chỉ có một bộ annotation.** 3.3 có cả mô hình legacy `@Shell...` và mô hình mới `@Command`/`@Option`. Chọn một mô hình rõ ràng.

**Dùng `@Component` thay `@ShellComponent` trong legacy model.** Bộ đăng ký legacy tìm bean mang `@ShellComponent`. Nếu chuyển sang `@Component`, hãy chuyển hẳn sang mô hình mới và cấu hình đăng ký phù hợp.

**Quên `@EnableCommand` hoặc `@CommandScan` trong 3.3.** Mô hình mới không tự đăng ký chỉ vì method có `@Command`.

**Giữ `@Command` cấp class khi lên 4.x.** `@Command` 4.x chỉ dùng trên method. Dùng `@CommandGroup` cho prefix và tên nhóm.

**Giữ thuộc tính số nhiều của `@Option`.** `longNames` và `shortNames` là API 3.3; Spring Shell 4 dùng `longName` và `shortName`.

**Đổi `command` thành `name` nhưng quên đổi package.** Hai việc cần đi cùng nhau: dependency 4.x và import 4.x.

**Dùng `@CommandScan` trong Spring Shell 4.** Annotation này đã bị loại bỏ. Spring Boot tự scan; non-Boot dùng `@EnableCommand`.

**Cho rằng build thành công nghĩa là command đã đăng ký.** Compile chỉ xác nhận kiểu và annotation tồn tại. Hãy chạy `help` và gọi command thật.

**Chạy IDE với classpath cũ.** Sau khi thay BOM hoặc dependency, refresh build model và chạy compile từ command line để so sánh.

## 14. Checklist chẩn đoán

- [ ] Xác định phiên bản Spring Shell thực tế từ dependency graph.
- [ ] Xác nhận phiên bản Spring Boot tương thích với dòng Spring Shell.
- [ ] Kiểm tra fully qualified name của mọi annotation.
- [ ] Phân biệt legacy model và mô hình annotation mới trong Spring Shell 3.3.
- [ ] Không trộn `@ShellComponent/@ShellMethod/@ShellOption` với `@Command/@Option`.
- [ ] Trong 3.3 modern model, bật `@EnableCommand` hoặc `@CommandScan`.
- [ ] Trong 4.x, đặt method command trong Spring bean.
- [ ] Dùng `@CommandGroup` thay prefix class-level khi cần trên 4.0.2+.
- [ ] Đổi `command` thành `name` khi chuyển `@Command` từ 3.3 sang 4.x.
- [ ] Đổi `longNames/shortNames` thành `longName/shortName` khi chuyển `@Option`.
- [ ] Không dùng annotation legacy đã bị xóa trong 4.x.
- [ ] Refresh dependency model sau khi thay đổi build file.
- [ ] Build lại và kiểm tra `help`.
- [ ] Gọi command với input hợp lệ và không hợp lệ.
- [ ] Cập nhật test, script và tài liệu sau khi đổi command key hoặc prefix.

## 15. Tài liệu tham khảo chính thức

- [Spring Shell 3.3 — Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html): quy tắc sử dụng `@ShellComponent`, `@ShellMethod` và đăng ký command legacy.
- [Spring Shell 3.3 — Annotation Model](https://docs.spring.io/spring-shell/reference/3.3-SNAPSHOT/commands/registration/annotation.html): mô hình `@Command`, prefix cấp class và đăng ký bằng `@EnableCommand` hoặc `@CommandScan`.
- [Spring Shell 3.3 API — Package org.springframework.shell.standard](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/package-summary.html): danh sách annotation legacy.
- [Spring Shell 3.3 API — Command](https://docs.spring.io/spring-shell/docs/3.3.x/api/org/springframework/shell/command/annotation/Command.html) và [Option](https://docs.spring.io/spring-shell/docs/3.3.x/api/org/springframework/shell/command/annotation/Option.html): package và thuộc tính của mô hình annotation mới trong 3.3.
- [Spring Shell 3.3 API — CommandScan](https://docs.spring.io/spring-shell/docs/3.3.x/api/org/springframework/shell/command/annotation/CommandScan.html) và [EnableCommand](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/annotation/EnableCommand.html): cách bật đăng ký command.
- [Spring Shell 4 — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): annotation legacy bị loại bỏ, package mới, thay đổi thuộc tính, command grouping và command scanning.
- [Spring Shell 4 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html), [Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) và [CommandGroup](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html): API annotation trong Spring Shell 4.

Khi gặp annotation có tên đúng nhưng compiler hoặc shell vẫn báo lỗi, hãy xác minh phiên bản dependency, package đầy đủ, thuộc tính annotation và registrar đang dùng. Chỉ sau khi bốn điểm này cùng thuộc một thế hệ API mới tiếp tục sửa logic command.

