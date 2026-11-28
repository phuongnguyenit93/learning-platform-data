# Nhận diện API đã bỏ hoặc đổi package khi đọc ví dụ cũ

Khi tìm ví dụ Spring Shell trên blog, diễn đàn hoặc kho mã nguồn, bạn có thể gặp những import và annotation không còn xuất hiện trong dự án hiện tại. Một ví dụ dùng `@CliCommand`, ví dụ khác dùng `@ShellMethod`, còn tài liệu mới hơn lại dùng `@Command`. Có trường hợp lớp vẫn tồn tại nhưng đã chuyển package; có trường hợp tên API đã đổi; cũng có trường hợp API cũ đã bị loại bỏ hoàn toàn.

Muốn đánh giá một ví dụ có dùng được hay không, trước tiên phải xác định phiên bản Spring Shell mà ví dụ được viết cho và phiên bản thực tế mà dự án đang nạp. Sau đó mới phân loại khác biệt là API cũ, API bị deprecated, API được đổi tên, API chuyển package hay API bị xóa. Cách làm này giúp tránh sửa import theo cảm tính hoặc thêm một dependency cũ chỉ để làm cho ví dụ biên dịch được.

## 1. Phân biệt các dạng thay đổi API

Các thông báo lỗi khi đọc mã cũ thường giống nhau, nhưng nguyên nhân và cách xử lý khác nhau:

| Dạng thay đổi | Ý nghĩa | Cách nhận diện |
|---|---|---|
| Deprecated | API vẫn còn trong phiên bản hiện tại nhưng được đánh dấu không nên dùng và có thể bị xóa ở phiên bản sau | Javadoc hoặc trình biên dịch hiển thị `@Deprecated` và thường có hướng thay thế |
| Removed | API đã bị xóa khỏi phiên bản đang dùng | Không tìm thấy lớp hoặc phương thức trong Javadoc và JAR của phiên bản đó |
| Renamed | API được thay bằng tên khác | Tài liệu migration ghi rõ tên cũ và tên mới |
| Moved package | API vẫn có vai trò tương tự nhưng package đã thay đổi | Tên lớp cũ không resolve; Javadoc phiên bản mới cho thấy package khác |
| Moved module | API hoặc tính năng được chuyển sang artifact khác | Lớp có thể tồn tại trong tài liệu nhưng dependency hiện tại không chứa artifact cung cấp nó |
| Changed behavior or contract | Tên API còn đó nhưng thuộc tính, chữ ký, cách đăng ký hoặc hành vi đã đổi | Mã có thể biên dịch nhưng chạy khác hoặc không đăng ký command như mong đợi |

Không nên kết luận API đã bị xóa chỉ vì IDE báo `cannot find symbol`. Lỗi đó cũng có thể do dependency chưa được khai báo, dependency bị loại khỏi classpath, phiên bản xung đột hoặc import sai. Ngược lại, đổi package thành công cũng chưa chắc đủ nếu hợp đồng API đã thay đổi.

## 2. Nhận diện các thế hệ khai báo command

Spring Shell đã thay đổi mô hình khai báo command qua nhiều thế hệ. Nhìn vào annotation và package import thường giúp nhận diện nhanh tuổi của ví dụ.

### Spring Shell 1.x: CommandMarker và nhóm annotation Cli

Ví dụ thuộc thế hệ 1.x thường có các dấu hiệu:

- Lớp command triển khai `CommandMarker`.
- Dùng `@CliCommand` để khai báo command.
- Dùng `@CliOption` trên tham số để mô tả option, giá trị bắt buộc và giá trị mặc định.
- Dùng `@CliAvailabilityIndicator` để điều khiển command có khả dụng hay không.
- Các import thường nằm trong `org.springframework.shell.core` và `org.springframework.shell.core.annotation`.

Ví dụ theo Spring Shell 1.2:

```java
import org.springframework.shell.core.CommandMarker;
import org.springframework.shell.core.annotation.CliAvailabilityIndicator;
import org.springframework.shell.core.annotation.CliCommand;
import org.springframework.shell.core.annotation.CliOption;
import org.springframework.stereotype.Component;

@Component
public class StockCommands implements CommandMarker {

    @CliAvailabilityIndicator("stock show")
    public boolean isStockShowAvailable() {
        return true;
    }

    @CliCommand(value = "stock show", help = "Show stock for a product")
    public String show(
            @CliOption(key = { "sku" }, mandatory = true,
                    help = "Product SKU") String sku) {
        return "Stock for " + sku;
    }
}
```

Nếu gặp `CommandMarker`, `@CliCommand`, `@CliOption` hoặc `@CliAvailabilityIndicator`, hãy kiểm tra xem ví dụ có thực sự nhắm đến Spring Shell 1.x hay không. Đây là mô hình cũ; không thể giữ nguyên các import đó rồi chỉ thay phiên bản dependency lên 2.x, 3.x hoặc 4.x.

### Spring Shell 2.x: standard API với ShellComponent và ShellMethod

Spring Shell 2 là một lần viết lại lớn, sử dụng JLine 3, tổ chức module mới và tích hợp tốt hơn với Spring Boot. Mô hình command được khuyến nghị chuyển sang các annotation trong package `org.springframework.shell.standard`:

- `@ShellComponent` đánh dấu lớp chứa command.
- `@ShellMethod` đánh dấu phương thức command và cung cấp mô tả, tên command hoặc alias.
- `@ShellOption` mô tả option và giá trị mặc định của tham số.
- `@ShellMethodAvailability` kết hợp với `Availability` để biểu diễn trạng thái khả dụng.

Ví dụ theo standard API của Spring Shell 2.x:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class StockCommands {

    @ShellMethod(value = "Show stock for a product", key = "stock show")
    public String show(
            @ShellOption(value = "--sku") String sku) {
        return "Stock for " + sku;
    }
}
```

Ở thế hệ này, lớp command không cần triển khai `CommandMarker` như ví dụ 1.x. Các annotation `@CliCommand`, `@CliOption` và `@CliAvailabilityIndicator` cũng không còn là mô hình khai báo command tiêu chuẩn. Hãy đọc ví dụ 1.x như tài liệu lịch sử hoặc tài liệu tham khảo ý tưởng, rồi chuyển command sang standard API nếu dự án đang dùng 2.x.

Spring Shell 2.1 tiếp tục cải tổ phần nội bộ và giới thiệu `CommandRegistration` làm cách khai báo command bằng Java API. Blog phát hành 2.1 cho biết mô hình annotation hiện có được giữ tương thích trong thay đổi đó. Vì vậy, khi đọc mã 2.1, bạn có thể gặp cả standard annotation API lẫn cách đăng ký command bằng builder.

### Spring Shell 3.x: giai đoạn chuyển tiếp sang annotation model mới

Trong 3.x, cần phân biệt hai mô hình annotation. Tài liệu 3.1.x gọi `@ShellComponent`, `@ShellMethod` và `@ShellOption` là *legacy annotation model*. Mô hình mới dùng `@Command` và `@Option`, đồng thời hỗ trợ đăng ký command theo chương trình bằng `CommandRegistration`.

Ở các bản 3.1.x, package của mô hình mới có dạng:

```java
org.springframework.shell.command.annotation.Command
org.springframework.shell.command.annotation.Option
org.springframework.shell.command.annotation.EnableCommand
org.springframework.shell.command.annotation.CommandScan
org.springframework.shell.command.CommandRegistration
```

Ví dụ khai báo command theo mô hình mới trong Spring Shell 3.1.x:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

public class StockCommands {

    @Command(command = "stock show", description = "Show stock for a product")
    public String show(@Option(longNames = "sku") String sku) {
        return "Stock for " + sku;
    }
}
```

Lớp chứa command còn phải được đăng ký bằng cơ chế phù hợp, chẳng hạn `@EnableCommand` hoặc `@CommandScan`. Khi đọc tài liệu 3.x, hãy kiểm tra mục *Reading Docs* hoặc *Registration* để biết ví dụ đang dùng legacy annotation model, annotation model mới hay programmatic model. Hai đoạn mã cùng chạy trên một nhánh phiên bản nhưng không có nghĩa là chúng dùng cùng một bộ annotation.

### Spring Shell 4.x: mô hình mới và package core

Spring Shell 4 loại bỏ legacy annotation model đã deprecated trong 3.x. Các annotation `@ShellComponent`, `@ShellMethod`, `@ShellOption` và những annotation liên quan không còn được cung cấp. Mô hình mới dùng các annotation trong package `org.springframework.shell.core.command.annotation` của module `spring-shell-core`:

- `@Command` đánh dấu phương thức command.
- `@Option` mô tả tham số dạng option có tên.
- `@Argument` mô tả tham số vị trí; `@Arguments` nhận một tập argument.
- `@CommandGroup` nhóm các command có chung prefix.
- `@EnableCommand` bật đăng ký command trong cấu hình không dùng Spring Boot.

Spring Shell 4 dựa trên Spring Framework 7; khi dùng cùng Spring Boot, yêu cầu Spring Boot 4 trở lên. Kiểm tra yêu cầu nền tảng trước khi nâng dependency, vì chỉ thay version Spring Shell có thể chưa đủ để dự án khởi động.

Ví dụ theo mô hình mới của Spring Shell 4:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class StockCommands {

    @Command(name = "stock show", description = "Show stock for a product")
    public String show(
            @Argument(index = 0, description = "Product SKU") String sku,
            @Option(longName = "warehouse", description = "Warehouse code") String warehouse) {
        return "Stock for " + sku + " at " + warehouse;
    }
}
```

Trong ứng dụng Spring Boot, command scanning được bật tự động theo cách cấu hình của Spring Shell 4; không cần thêm `@CommandScan`. Nếu không dùng Spring Boot, dùng `@EnableCommand` để bật đăng ký command. Đây là khác biệt quan trọng khi một ví dụ cũ biên dịch được nhưng command không xuất hiện trong `help`.

Một số thuộc tính và cách nhóm command cũng thay đổi giữa 3.x và 4.x. Thuộc tính `command` của `@Command` trong 3.x được đổi thành `name` trong 4.x. Nếu 3.x dùng `@Command` ở cấp lớp để đặt prefix hoặc nhóm command, 4.x dùng `@CommandGroup` ở cấp lớp và giữ `@Command` trên từng phương thức.

## 3. Bảng nhận diện nhanh annotation và package

| Thế hệ | Dấu hiệu trong mã | Package tiêu biểu | Cách xử lý khi dự án dùng thế hệ mới hơn |
|---|---|---|---|
| 1.x | `CommandMarker`, `@CliCommand`, `@CliOption`, `@CliAvailabilityIndicator` | `org.springframework.shell.core`, `org.springframework.shell.core.annotation` | Chuyển sang mô hình command tương ứng của 2.x trở lên |
| 2.x | `@ShellComponent`, `@ShellMethod`, `@ShellOption`, `@ShellMethodAvailability` | `org.springframework.shell.standard`; `Availability` thuộc `org.springframework.shell` | Với 3.x có thể dùng legacy model trong giai đoạn chuyển tiếp; ưu tiên mô hình mới nếu dự án đã chọn nó |
| 3.1.x | `@Command(command = ...)`, `@Option(longNames = ...)`, `CommandRegistration` | `org.springframework.shell.command.annotation`, `org.springframework.shell.command` | Đối chiếu chữ ký và package với API 4.x; không chỉ thay prefix package |
| 4.x | `@Command(name = ...)`, `@Option`, `@Argument`, `@CommandGroup` | `org.springframework.shell.core.command.annotation` | Dùng API 4.x và module tương ứng; legacy annotation đã bị xóa |

Đây là các mốc nhận diện chính, không phải quy tắc rằng mọi phiên bản patch trong cùng nhánh đều có API giống hệt nhau. Khi cần kết luận về một lớp hoặc phương thức cụ thể, hãy mở Javadoc đúng phiên bản đang dùng.

## 4. Các thay đổi package và module đáng chú ý trong Spring Shell 4

Ngoài mô hình annotation, Spring Shell 4 còn tổ chức lại package và artifact. Một số ví dụ cũ có thể tham chiếu đúng chức năng nhưng sai package hoặc thiếu module.

| Thành phần ở 3.x | Thay đổi ở 4.x | Điều cần kiểm tra |
|---|---|---|
| API trong `org.springframework.shell` của `spring-shell-core` | Chuyển dưới package `org.springframework.shell.core` | Kiểm tra package mới của lớp core cụ thể, ví dụ `ShellRunner` |
| API trong `org.springframework.shell.standard` của `spring-shell-standard` | Chuyển vào package `org.springframework.shell.core` trong `spring-shell-core` | Một số annotation legacy đã bị xóa; không suy ra rằng chỉ cần đổi import |
| `org.springframework.shell.table` trong `spring-shell-table` | Chuyển thành `org.springframework.shell.jline.tui.table` trong `spring-shell-jline` | Thêm module JLine khi dùng bảng và các tính năng phụ thuộc JLine |
| `spring-shell-autoconfigure` | Đổi tên thành `spring-shell-core-autoconfigure` | Cập nhật dependency nếu khai báo artifact này trực tiếp |
| `spring-shell-standard`, `spring-shell-standard-commands` | Gộp vào `spring-shell-core` | Loại dependency cũ theo hướng dẫn migration và kiểm tra dependency tree |
| `spring-shell-table` | Gộp vào `spring-shell-jline` | Chỉ cần module JLine khi ứng dụng dùng chức năng đó |

Trong 4.x, `spring-shell-core` không còn phụ thuộc Spring Boot hoặc JLine. Nếu dùng Spring Boot, hãy thêm `spring-shell-core-autoconfigure` hoặc starter phù hợp. Nếu cần console dựa trên JLine, khai báo `spring-shell-jline`. Không nên thêm lại module `spring-shell-standard` chỉ để tìm `@ShellMethod`, vì annotation này đã bị loại bỏ trong 4.x.

Một số API cũng được đổi tên hoặc loại bỏ:

| API cũ | Thay đổi trong 4.x |
|---|---|
| `EnumValueProvider` | Đổi tên thành `EnumCompletionProvider` |
| `FileValueProvider` | Đổi tên thành `FileNameCompletionProvider` |
| `CommandExceptionResolver` | Thay bằng `ExitStatusExceptionMapper`; hợp đồng xử lý exception cũng thay đổi |
| `CommandHandlingResult` và các API exit code liên quan của 3.x | Dùng `ExitStatus` theo mô hình mới |
| `CommandRegistration` và cách đăng ký command bằng `CommandCatalog` của 3.x | Mô hình programmatic được thiết kế lại quanh `Command.Builder` và `CommandRegistry` |
| `InteractionMode` | Bị loại bỏ; chế độ tương tác được quyết định khi khởi động shell |
| `@OptionValues` | Bị loại bỏ; completion được cấu hình qua `CompletionProvider` ở cấp command |
| Lệnh tích hợp `stacktrace` | Bị loại bỏ; dùng chế độ debug để hiển thị stack trace |
| Lệnh tích hợp `completion` | Bị loại bỏ; cấu hình completion theo shell như Bash hoặc Zsh |

Các API kiểm thử cũ như `ShellWriteSequence`, `ShellTypeExcludeFilter`, `SpringShellTestProperties`, `@AutoConfigureShell` và `@AutoConfigureShellTestClient` cũng bị loại bỏ theo migration guide 4.x. Nếu gặp chúng trong ví dụ kiểm thử, cần tra API test hiện hành thay vì chỉ sửa import.

## 5. Ví dụ chuyển cùng một command qua các thế hệ

Giả sử cần khai báo command hiển thị tồn kho. Bốn đoạn sau minh họa cách tư duy về cùng một chức năng qua các thế hệ API; chúng là các ví dụ theo từng phiên bản và không thể trộn import hoặc annotation giữa các đoạn.

**Thế hệ 1.x**

```java
@Component
public class StockCommands implements CommandMarker {

    @CliCommand(value = "stock show", help = "Show stock")
    public String show(
            @CliOption(key = { "sku" }, mandatory = true) String sku) {
        return "Stock for " + sku;
    }
}
```

**Thế hệ 2.x**

```java
@ShellComponent
public class StockCommands {

    @ShellMethod(value = "Show stock", key = "stock show")
    public String show(@ShellOption(value = "--sku") String sku) {
        return "Stock for " + sku;
    }
}
```

**Mô hình annotation mới của 3.1.x**

```java
@Command(command = "stock show", description = "Show stock")
public String show(@Option(longNames = "sku") String sku) {
    return "Stock for " + sku;
}
```

**Mô hình annotation của 4.x**

```java
@Command(name = "stock show", description = "Show stock")
public String show(@Argument(index = 0, description = "Product SKU") String sku) {
    return "Stock for " + sku;
}
```

Điểm khác biệt cần chú ý là `CommandMarker` biến mất khi chuyển khỏi mô hình 1.x; `@ShellComponent` và `@ShellMethod` thuộc standard/legacy model; mô hình mới của 3.x dùng `command` và `longNames`; còn 4.x dùng `name`, `longName`/`shortName` cho option và annotation riêng cho argument. Ở 4.x, cách đăng ký command bằng chương trình cũng chuyển từ `CommandRegistration`/`CommandCatalog` sang `Command.Builder`/`CommandRegistry`. Khi migrate thật, cần kiểm tra cả cấu hình đăng ký command, validation, default value, completion và kết quả trả về.

## 6. Xác định phiên bản thật mà dự án đang sử dụng

Không nên chọn tài liệu dựa trên phiên bản Spring Boot được nhớ từ một bài blog. Spring Boot và Spring Shell có quan hệ tương thích, nhưng số phiên bản của hai dự án không giống nhau. Hãy kiểm tra dependency đã được build tool phân giải.

### Với Maven

Tìm khai báo starter, BOM và version trong `pom.xml`. Sau đó chạy:

```bash
mvn dependency:tree -Dincludes=org.springframework.shell
```

Lệnh này cho biết các artifact Spring Shell thực tế có mặt trong dependency graph, bao gồm dependency được kéo vào gián tiếp. Nếu dự án dùng BOM, kiểm tra version được quản lý bởi BOM thay vì chỉ nhìn vào dependency không ghi version.

### Với Gradle

Kiểm tra `dependencies`, version catalog và dependency management trong các file build. Sau đó chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Có thể thu hẹp kết quả bằng cách kiểm tra dependency cụ thể hoặc dùng `dependencyInsight` để biết thành phần nào đã chọn version cuối cùng và vì sao.

### Kiểm tra nội dung JAR

Khi đã biết JAR được resolve, có thể liệt kê class bên trong để xác nhận package thực tế. Ví dụ trên môi trường có JDK:

```bash
jar tf path/to/spring-shell-core.jar
```

Tìm class cần kiểm tra trong kết quả, rồi dùng `javap` để xem chữ ký public nếu cần:

```bash
javap -classpath path/to/spring-shell-core.jar \
  org.springframework.shell.core.ShellRunner
```

Đường dẫn JAR và tên class phải lấy từ dependency đã resolve của dự án. Ví dụ trên chỉ minh họa cách kiểm tra; package `ShellRunner` phải được đối chiếu với đúng nhánh Spring Shell đang dùng.

## 7. Quy trình xử lý khi ví dụ cũ không biên dịch

Thực hiện lần lượt các bước sau để khoanh vùng nguyên nhân:

1. **Ghi nhận phiên bản mục tiêu.** Xác định version Spring Shell trong dependency graph, không chỉ dựa vào version được ghi trong một file hoặc tài liệu hướng dẫn.
2. **Nhận diện thế hệ API.** Tìm import và annotation: `@CliCommand` thường chỉ 1.x; `@ShellMethod` chỉ standard/legacy model; `@Command` cần xác định package và thuộc tính để phân biệt 3.x với 4.x.
3. **Mở tài liệu đúng phiên bản.** Dùng reference documentation, Javadoc và migration guide của đúng nhánh. Không copy một ví dụ từ `current` hoặc `SNAPSHOT` vào dự án đang dùng bản phát hành cũ.
4. **Phân loại lỗi.** Xác định lớp bị deprecated, removed, renamed, moved package, moved module hay thay đổi hợp đồng.
5. **Chọn cách chuyển đổi.** Dùng API thay thế chính thức nếu có. Với API bị xóa, chuyển sang mô hình mới; không thêm lại artifact cũ nếu artifact đó không tương thích với phiên bản nền.
6. **Kiểm tra đăng ký command.** Nếu code biên dịch nhưng command không xuất hiện, kiểm tra `@EnableCommand`, `@CommandScan` ở 3.x hoặc quy tắc auto scanning của Spring Boot ở 4.x.
7. **Build và kiểm tra hành vi.** Xác nhận command xuất hiện trong `help`, tham số được bind đúng, validation và completion hoạt động, output và mã thoát phù hợp với cách chạy tương tác hoặc script.

Một số lỗi phổ biến có thể được diễn giải như sau:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| `package org.springframework.shell.core.annotation does not exist` | Ví dụ đang dùng API 1.x nhưng dự án dùng nhánh mới hơn |
| `cannot find symbol: ShellMethod` trong dự án 4.x | Legacy annotation đã bị loại bỏ; cần chuyển sang `@Command` và annotation tham số của 4.x |
| `package org.springframework.shell.standard does not exist` | Có thể thiếu module ở 3.x hoặc đang đọc code 3.x trong dự án 4.x; kiểm tra package move và API removal riêng biệt |
| `NoClassDefFoundError` khi chạy | Kiểm tra artifact bị thiếu, version xung đột hoặc thay đổi module/dependency |
| Ứng dụng khởi động nhưng command không xuất hiện | Kiểm tra annotation model và cơ chế đăng ký/scanning theo phiên bản |
| Không tìm thấy `stacktrace` hoặc `completion` | Hai built-in command này đã bị loại bỏ trong 4.x |

## 8. Những sai lầm cần tránh

- **Chỉ sửa dòng import.** Một API có thể đổi package nhưng cũng có thể đã bị xóa hoặc đổi hợp đồng. Luôn kiểm tra tên lớp, chữ ký và hướng dẫn migration.
- **Trộn hai annotation model.** Trong 3.x, legacy annotation và annotation model mới cùng tồn tại. Chọn một mô hình nhất quán cho command và đăng ký nó theo đúng cách.
- **Thêm dependency cũ để chữa lỗi compile.** Việc đưa module của 1.x hoặc 2.x vào dự án 4.x có thể tạo xung đột và không khôi phục API đã bị loại bỏ.
- **Dùng tài liệu `current` cho dự án cũ.** `current` thay đổi theo thời gian; hãy mở Javadoc và reference documentation gắn với version cụ thể.
- **Đồng nhất version Spring Boot với Spring Shell.** Hãy kiểm tra bảng tương thích và yêu cầu nền tảng trong tài liệu phát hành của Spring Shell.
- **Chỉ kiểm tra compile.** Một command vẫn có thể không được scan, không hiện trong `help`, bind sai tham số hoặc thay đổi hành vi khi chạy script.

## 9. Kết luận

Khi đọc ví dụ Spring Shell cũ, annotation và package là manh mối để nhận diện thế hệ API, còn dependency graph cho biết phiên bản thực tế mà dự án sử dụng. Spring Shell 1.x dùng `CommandMarker` và nhóm `@Cli*`; 2.x chuyển sang standard API với `@ShellComponent` và `@ShellMethod`; 3.x bổ sung mô hình `@Command` trong khi vẫn còn legacy model; 4.x loại bỏ legacy model, chuyển package core và tổ chức lại module.

Hãy phân biệt rõ API deprecated, API removed, API renamed, API moved package và API moved module. Sau khi xác định đúng loại thay đổi, dùng migration guide và Javadoc đúng phiên bản để chuyển đổi, rồi kiểm tra cả việc đăng ký command và hành vi lúc chạy.

## Tài liệu tham khảo

- [Spring Shell 1.2.0 Reference Documentation](https://docs.spring.io/spring-shell/docs/1.2.0.RELEASE/reference/pdf/spring-shell-reference.pdf) — mô hình `CommandMarker`, `@CliCommand`, `@CliOption` và `@CliAvailabilityIndicator`.
- [Spring Shell 2.0 Reference Documentation](https://docs.spring.io/spring-shell/docs/2.0.0.RELEASE/reference/htmlsingle/) — standard API với `@ShellComponent`, `@ShellMethod` và `@ShellOption`.
- [Spring Shell 2.1.0 release announcement](https://spring.io/blog/2022/07/25/spring-shell-2-1-0-is-now-available/) — `CommandRegistration`, thay đổi nội bộ và khả năng tương thích annotation hiện có.
- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — phân biệt legacy annotation model, annotation model mới và programmatic model.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — các API bị xóa, package/module được di chuyển, API đổi tên và thay đổi hành vi.
- [Spring Shell 4.x command annotation package](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/package-summary.html) — danh sách annotation mới như `@Command`, `@Option`, `@Argument`, `@Arguments` và `@CommandGroup`.
