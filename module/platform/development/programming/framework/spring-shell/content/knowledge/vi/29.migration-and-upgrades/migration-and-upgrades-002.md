# Đọc hướng dẫn nâng cấp theo từng nhánh trung gian

Khi nâng cấp một ứng dụng Spring Shell qua nhiều phiên bản, chỉ đọc tài liệu của phiên bản đích thường không đủ. Một thay đổi có thể xuất hiện ở nhánh trung gian, một API có thể bị đánh dấu deprecated trước khi bị xóa ở major release tiếp theo, và phiên bản Spring Boot tương thích có thể thay đổi theo từng nhánh Spring Shell.

Hãy xem quá trình nâng cấp như một chuỗi các chặng có thể kiểm chứng. Với mỗi chặng, xác định phiên bản nguồn, phiên bản đích, tài liệu cần đọc, thay đổi cần xử lý và bằng chứng cho thấy ứng dụng vẫn hoạt động. Nếu đi từ Spring Shell 3.x lên 4.x, hướng dẫn chính thức yêu cầu nâng ứng dụng lên Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x. Spring Boot cũng khuyến nghị nâng lên 3.5.x mới nhất trước khi chuyển sang 4.0.

Bài này giúp bạn:

- Xác định chính xác phiên bản Spring Boot, Spring Framework và Spring Shell hiện tại.
- Đọc compatibility matrix để chọn các phiên bản có thể kết hợp.
- Tìm migration guide và release notes của từng nhánh trung gian.
- Phân biệt hướng dẫn nâng cấp, release notes, tài liệu API và thông báo deprecated.
- Lập lộ trình nâng cấp theo từng chặng nhỏ.
- Nhận diện thay đổi có thể ảnh hưởng đến command, option, runner, dependency và test.
- Ghi lại việc cần sửa và cách xác nhận sau mỗi chặng.
- Biết khi nào cần đọc migration guide của Spring Boot cùng với Spring Shell.

> Ví dụ sử dụng các nhánh Spring Shell 3.x và 4.x, Spring Boot 3.x và 4.x. Các phiên bản phát hành thay đổi theo thời gian; hãy kiểm tra release page và compatibility matrix tại thời điểm thực hiện dự án.

## 1. Phân biệt version, release line và migration guide

Một phiên bản đầy đủ thường có dạng `major.minor.patch`, ví dụ `3.3.4`:

| Thành phần | Ý nghĩa thực tế khi nâng cấp |
|---|---|
| Major (`3` hoặc `4`) | Có thể chứa thay đổi lớn về API, dependency baseline hoặc hành vi |
| Minor (`3.2`, `3.3`, `3.4`) | Một release line có thể bổ sung tính năng và thay đổi hành vi; cần đọc release notes |
| Patch (`3.3.1`, `3.3.2`) | Thường tập trung sửa lỗi và cập nhật dependency; vẫn cần xem ghi chú phát hành |

Không nên tự suy ra rằng mọi dự án Spring đều áp dụng SemVer một cách tuyệt đối. Hãy dùng tên nhánh, compatibility matrix và tài liệu chính thức của chính dự án để xác định cách nâng cấp.

Các loại tài liệu có mục đích khác nhau:

| Tài liệu | Câu hỏi cần trả lời |
|---|---|
| Migration guide / upgrading guide | Cần thay đổi gì để chuyển từ phiên bản nguồn sang phiên bản đích? |
| Release notes | Nhánh này thêm tính năng, sửa lỗi, thay đổi hành vi hoặc dependency nào? |
| Compatibility matrix | Phiên bản Spring Shell nào được hỗ trợ với Spring Boot nào? |
| API/Javadoc | API mới có chữ ký, tham số và hợp đồng ra sao? |
| Deprecation notice | API nào đã bị khuyến nghị thay thế và có thể bị xóa ở nhánh sau? |
| Dependency management/BOM | Các phiên bản thư viện nào được quản lý và tương thích với nhau? |

Migration guide thường mô tả các thay đổi quan trọng nhất. Release notes bổ sung thông tin theo từng nhánh hoặc từng lần phát hành. Đọc cả hai giúp tránh bỏ qua thay đổi nhỏ nhưng có ảnh hưởng đến ứng dụng.

## 2. Bắt đầu từ phiên bản thực tế của ứng dụng

Trước khi mở migration guide, hãy ghi nhận những gì dự án đang dùng. Không chỉ xem version trong file build vì version hiệu lực có thể đến từ BOM, plugin hoặc dependency management ở cấp parent.

Với Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency spring-shell
./gradlew dependencyInsight --dependency spring-boot
~~~

Kiểm tra tối thiểu:

- Phiên bản Spring Boot plugin hoặc parent/BOM.
- Phiên bản Spring Shell starter và các module Spring Shell được khai báo trực tiếp.
- Phiên bản Spring Framework hiệu lực.
- Java toolchain hoặc source/target compatibility.
- Các thư viện liên quan như JLine, Reactor, Jackson, validation và test support.
- Plugin build, plugin đóng gói và plugin kiểm thử.
- Các dependency không do Spring Boot quản lý, ví dụ Spring Cloud hoặc thư viện của bên thứ ba.

Ghi cả dependency được khai báo trực tiếp và dependency bắc cầu. Một module có thể được kéo vào bởi starter; khi module được đổi tên hoặc gộp trong phiên bản mới, chỉ sửa một dòng dependency có thể chưa đủ.

Mẫu ghi nhận phiên bản nguồn:

| Thành phần | Phiên bản hiệu lực | Nguồn khai báo |
|---|---|---|
| Java | `17` | Maven toolchain / Gradle toolchain |
| Spring Boot | `3.3.x` | Parent hoặc BOM |
| Spring Framework | Do Boot BOM quản lý | Dependency management |
| Spring Shell | `3.3.x` | Starter hoặc BOM |
| JLine | Phiên bản hiệu lực trong dependency tree | Dependency bắc cầu hoặc khai báo trực tiếp |

Các giá trị trên chỉ là ví dụ. Hãy thay bằng kết quả thực tế của dự án trước khi chọn lộ trình.

## 3. Đọc compatibility matrix trước khi chọn phiên bản đích

Spring Shell phụ thuộc vào nền tảng Spring Boot và Spring Framework. Không chọn phiên bản Spring Shell chỉ vì đó là số mới nhất trên Maven Central. Trước hết, kiểm tra phiên bản Boot hiện tại và phiên bản Boot mà nhánh Shell đích hỗ trợ.

Ví dụ, compatibility matrix chính thức liệt kê các cặp phiên bản đang được hỗ trợ như sau:

| Spring Boot | Spring Shell |
|---|---|
| `4.1.x` | `4.0.x` |
| `4.0.x` | `4.0.x` |
| `3.5.x` | `3.4.x` |
| `3.4.x` | `3.4.x` |
| `2.7.x` | `2.1.x` |

Đây là danh sách phiên bản được hỗ trợ tại thời điểm tài liệu được kiểm tra, không phải danh sách mọi cặp từng tồn tại. Việc một nhánh cũ không còn xuất hiện trong bảng không chứng minh rằng phiên bản đó chưa từng tương thích; nó cho biết không nên xem nó là một cặp được hỗ trợ hiện tại.

Tại thời điểm biên soạn ngày 26/11/2026, trang release liệt kê Spring Shell `4.0.4` và nhánh `3.4.3`. Hãy kiểm tra lại release page khi bắt đầu dự án nâng cấp, vì patch mới có thể được phát hành sau thời điểm này.

### Không ghép phiên bản bằng cách đoán

Ví dụ, không nên tự chọn Spring Shell 4.x với Spring Boot 3.5.x chỉ vì cả hai đều chạy trên Java 17. Compatibility matrix hiện tại yêu cầu Spring Shell 4.0.x đi cùng Spring Boot 4.0.x hoặc 4.1.x. Spring Shell 3.4.x là nhánh tương thích với Spring Boot 3.4.x và 3.5.x.

Nếu ứng dụng dùng Spring Boot, Spring Framework hoặc thư viện tích hợp khác, hãy đọc tài liệu nâng cấp của các thành phần đó nữa. Spring Shell migration guide không bao quát mọi thay đổi trong Spring Boot, Spring Framework, JLine hoặc thư viện bên thứ ba.

## 4. Lập chuỗi nhánh trung gian

Sau khi xác định phiên bản nguồn và đích, liệt kê các release line nằm giữa chúng. Mỗi nhánh cần có điểm kiểm tra riêng. Không nhất thiết phải triển khai production ở mọi patch, nhưng cần đọc ghi chú của các nhánh bị đi qua và xác nhận tương thích ở từng chặng.

Ví dụ ứng dụng đang dùng Spring Boot 3.2.x và Spring Shell 3.2.x, mục tiêu là Spring Boot 4.0.x và Spring Shell 4.0.x:

~~~text
Boot 3.2 / Shell 3.2
        |
        v
Boot 3.3 / Shell 3.3
        |
        v
Boot 3.4 / Shell 3.4
        |
        v
Boot 3.5 / Shell 3.4
        |
        v
Boot 4.0 / Shell 4.0
~~~

Sơ đồ minh họa thứ tự đọc tài liệu và các release line. Với mỗi cặp phiên bản cụ thể, hãy kiểm tra compatibility matrix và release notes tương ứng trước khi thay version. Nhánh Spring Shell 3.4.x có thể đi cùng Boot 3.4.x hoặc 3.5.x; không cần tạo một phiên bản Spring Shell 3.5 chỉ vì Spring Boot có nhánh 3.5.

Nếu dự án đang ở Boot 2.7.x và Spring Shell 2.1.x, khoảng cách dài hơn. Hãy đọc các hướng dẫn nâng cấp Spring Boot từ 2.x qua từng release line 3.x đến 3.5.x, đồng thời đọc release notes của các nhánh Spring Shell mà dự án đi qua. Không tự giả định mọi phiên bản trung gian đều có cùng cặp tương thích.

### Quy tắc chọn điểm dừng

- Dừng ở bản patch mới nhất của release line nguồn trước khi bắt đầu thay đổi lớn.
- Hoàn tất các migration cần thiết của release line hiện tại.
- Nâng lên release line tiếp theo có cặp dependency được hỗ trợ.
- Xác nhận compile, test và hành vi CLI trước khi sang chặng tiếp.
- Trước major release, nâng lên nhánh cuối cùng được migration guide yêu cầu.

Hướng dẫn Spring Shell 4 yêu cầu nâng ứng dụng lên Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x. Hướng dẫn Spring Boot 4 yêu cầu nâng ứng dụng lên Spring Boot 3.5.x mới nhất trước khi chuyển sang 4.0. Hai yêu cầu này cần được thực hiện song song trong kế hoạch nâng cấp.

## 5. Đọc từng migration guide theo một thứ tự cố định

Khi mở migration guide của nhánh đích, đọc theo thứ tự sau:

1. **Before you start:** xác định phiên bản nguồn mà hướng dẫn giả định và bản patch mới nhất cần nâng lên.
2. **System requirements:** kiểm tra Java, Kotlin, Gradle/Maven, Spring Framework và runtime.
3. **Dependency upgrades:** so sánh BOM, starter, module đã đổi tên hoặc bị gộp.
4. **Deprecations and removals:** tìm API đã deprecated ở nhánh trước và bị xóa ở nhánh đích.
5. **Configuration changes:** tìm property bị đổi tên, đổi mặc định hoặc bị xóa.
6. **API and programming model:** kiểm tra annotation, interface, package và chữ ký method.
7. **Runtime behavior:** kiểm tra runner, command parsing, completion, history, exception và exit code.
8. **Testing changes:** kiểm tra test annotation, test client, mock support và yêu cầu runtime mới.
9. **Release notes:** đọc các thay đổi bổ sung của từng release line và patch liên quan.

Với mỗi mục, ghi lại một trong ba trạng thái:

- **Không áp dụng:** dự án không dùng tính năng/API đó; ghi rõ lý do.
- **Cần thay đổi:** xác định file, class hoặc cấu hình cần sửa.
- **Cần xác minh:** chưa đủ thông tin; tạo test hoặc spike nhỏ để kiểm tra.

Không đánh dấu một mục là “không áp dụng” chỉ vì chưa tìm thấy từ khóa trong một file. Một API có thể được gọi từ module khác, dependency bắc cầu hoặc cấu hình runtime.

## 6. Ví dụ đọc release notes Spring Shell 3.2 lên 3.3

Release notes Spring Shell 3.3 có mục “Upgrading From Spring Shell 3.2”. Thay đổi nổi bật là mặc định của runner:

- Các phiên bản đến 3.2.x bật tất cả runner theo mặc định.
- Từ 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định.
- Nếu cần interactive shell hoặc script runner, phải bật rõ ràng.

Ví dụ cấu hình:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    script:
      enabled: true
~~~

Nếu ứng dụng đang dựa vào mặc định cũ, sau khi nâng cấp nó có thể chỉ chạy command non-interactive rồi thoát, thay vì mở REPL hoặc xử lý script như trước. Đây là thay đổi hành vi dù source code command có thể không cần sửa.

Khi đọc release notes này, hãy tìm tất cả điểm mà ứng dụng đang sử dụng:

- Có cần REPL cho người vận hành không?
- Có chạy script từ file không?
- Có pipeline gọi command qua startup argument không?
- Có test phụ thuộc runner mặc định không?
- Profile production và development có cần cấu hình runner khác nhau không?

Ghi thay đổi vào file cấu hình phù hợp và tạo smoke test cho từng mode. Không chỉ xác nhận ứng dụng compile thành công.

## 7. Ví dụ đọc migration guide Spring Shell 3.x lên 4.x

Spring Shell 4 là major release với thay đổi lớn về dependency baseline, command model, module và hành vi shell. Migration guide chính thức yêu cầu nâng lên bản Spring Shell 3.4.x mới nhất trước khi thực hiện bước này.

### Dependency và module

Một số thay đổi cần đối chiếu:

| Trong Spring Shell 3 | Trong Spring Shell 4 |
|---|---|
| `spring-shell-core` phụ thuộc Spring Boot | `spring-shell-core` không còn phụ thuộc Spring Boot |
| Core phụ thuộc JLine | Core không còn phụ thuộc JLine; thêm `spring-shell-jline` nếu cần JLine |
| `spring-shell-autoconfigure` | Đổi tên thành `spring-shell-core-autoconfigure` |
| `spring-shell-standard` và `spring-shell-standard-commands` | Được gộp vào `spring-shell-core` |
| `spring-shell-table` | Được gộp vào `spring-shell-jline` |

Nếu ứng dụng dùng Spring Boot, hãy kiểm tra starter hoặc thêm module auto-configuration phù hợp. Nếu ứng dụng cần history, tab completion hoặc rich text của JLine, xác nhận dependency JLine vẫn được cung cấp qua starter hay phải khai báo trực tiếp.

### Command annotation

Các annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` và những annotation liên quan đã deprecated trong v3 bị loại bỏ ở v4. Hãy chuyển sang mô hình `@Command`, `@Option`, `@Argument` của package mới.

Ví dụ v3 dùng legacy annotation:

~~~java
@ShellComponent
public class GreetingCommands {

    @ShellMethod(key = "greet", value = "Chào một người.")
    public String greet(
            @ShellOption("--name") String name) {
        return "Xin chào " + name;
    }
}
~~~

Ví dụ v4:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "greet", description = "Chào một người.")
    public String greet(
            @Option(longName = "name") String name) {
        return "Xin chào " + name;
    }
}
~~~

Đây là ví dụ chuyển đổi cấu trúc cơ bản. Khi migration thật, kiểm tra đầy đủ cách khai báo required/default value, short name, long name, arity, validation và completion trong API v4. Không chỉ đổi tên annotation rồi cho rằng mọi option vẫn giữ hành vi cũ.

### Command grouping và registration

Trong v3, có thể dùng `@Command` trên class để nhóm các command. Trong v4, `@Command` dùng trên method; dùng `@CommandGroup` để đặt prefix và tên group cho các command trong class.

Ngoài ra, Spring Boot tự động bật command scanning trong Spring Shell 4. `@CommandScan` đã bị loại bỏ. Ứng dụng không dùng Spring Boot vẫn cần cơ chế `@EnableCommand` theo hướng dẫn.

### Completion và option

Spring Shell 4 chuyển completion sang `CompletionProvider` ở cấp command, cho phép completion phụ thuộc vào các option khác. `@OptionValues` bị loại bỏ. Option trong v4 chỉ có một short name và một long name; option labels không còn được hỗ trợ.

Nếu ứng dụng dùng completer riêng cho từng option, cần thiết kế lại thành provider ở cấp command và kiểm thử tình huống cross-option. Kiểm tra cả help text và hành vi tab completion sau khi chuyển đổi.

### Runner và interactivity

Trong v4, ứng dụng chọn một `ShellRunner` khi khởi động; không dùng nhiều runner cùng lúc như mô hình v3. Các lựa chọn có sẵn gồm:

- `SystemShellRunner`: interactive shell dùng Java Console, không cần JLine.
- `JLineShellRunner`: interactive shell dùng JLine.
- `NonInteractiveShellRunner`: chạy command theo kiểu script/automation.

Spring Shell 4 mặc định interactive. Để chạy non-interactive, đặt `spring.shell.interactive.enabled=false`. Các command không còn được đánh dấu riêng là interactive hoặc non-interactive bằng `InteractionMode`; mode được chọn khi shell khởi động.

Điều này khác cả mặc định của Spring Shell 3.3, nơi chỉ non-interactive runner được bật mặc định. Vì vậy, phải đọc release notes theo từng nhánh để không áp dụng cấu hình của một phiên bản cho phiên bản khác.

### Exception, exit status và built-in command

Spring Shell 4 thay đổi API xử lý exception và mã thoát:

| Trong v3 | Trong v4 |
|---|---|
| `CommandExceptionResolver` và `CommandHandlingResult` | `ExitStatusExceptionMapper` và `ExitStatus` |
| Tùy chỉnh command availability qua annotation riêng | Thuộc tính `availabilityProvider` trong `@Command` |
| Built-in `stacktrace` command | Debug mode hiển thị stack trace khi lỗi xảy ra |
| Built-in `completion` command | Cấu hình completion cho shell người dùng chọn |

Nếu script hoặc hệ thống CI dựa vào exit code, phải kiểm tra mapping exception và mã thoát thực tế. Nếu tài liệu vận hành yêu cầu người dùng chạy `stacktrace` hoặc `completion`, hãy cập nhật quy trình tương ứng.

### Native image và test API

Migration guide v4 nêu rõ declarative annotation-based command registration chưa được hỗ trợ cho GraalVM native compilation ở v4.0.0; programmatic command definition là hướng được hỗ trợ tại thời điểm hướng dẫn đó. Nếu ứng dụng phát hành native image, đây là mục phải xác minh trước khi nâng cấp.

Một số test API và annotation của v3 cũng bị loại bỏ, gồm `@AutoConfigureShell`, `@AutoConfigureShellTestClient` và các kiểu hỗ trợ liên quan. Kiểm tra migration guide và tài liệu testing của đúng phiên bản đích để chuyển test sang API mới.

## 8. Đọc migration guide của Spring Boot cùng Spring Shell

Spring Shell dùng Spring Boot để quản lý dependency, auto-configuration, profile và nhiều thuộc tính. Vì vậy, nâng Spring Shell có thể buộc nâng Spring Boot, còn nâng Spring Boot có thể ảnh hưởng đến toàn bộ ứng dụng.

Khi chuyển lên Spring Boot 4.0, migration guide yêu cầu:

- Nâng lên Spring Boot 3.5.x mới nhất trước.
- Xử lý các API đã deprecated trong Spring Boot 3.x vì chúng bị xóa trong 4.0.
- Kiểm tra dependency management giữa Boot 3.5 và 4.0.
- Dùng Spring Framework 7.x khi quản lý dependency trực tiếp.
- Kiểm tra baseline Java và công cụ build.

Spring Boot 4.0 yêu cầu Java 17 trở lên. Nếu dùng Kotlin, kiểm tra baseline Kotlin của Boot 4; nếu dùng GraalVM native image, kiểm tra phiên bản GraalVM yêu cầu. Nếu ứng dụng có web server, kiểm tra yêu cầu Jakarta EE/Servlet tương ứng; một ứng dụng CLI thuần không nên tự thêm yêu cầu Servlet khi không dùng web stack.

Boot 4 cũng thay đổi một số configuration property. `spring-boot-properties-migrator` có thể giúp phát hiện và tạm thời chuyển một số property trong lúc nâng cấp. Nếu dùng công cụ này, chỉ giữ nó trong giai đoạn migration và gỡ dependency sau khi đã sửa cấu hình chính thức.

Không dùng Spring Boot migration guide để thay thế Spring Shell migration guide. Hãy tạo hai danh sách thay đổi, sau đó hợp nhất theo dependency và thứ tự thực hiện.

## 9. Lập bảng theo dõi thay đổi cho từng chặng

Mỗi migration guide nên được chuyển thành danh sách việc làm cụ thể. Một bảng theo dõi đơn giản:

| Nhánh nguồn → đích | Tài liệu đã đọc | Thay đổi cần xử lý | Kiểm tra | Trạng thái |
|---|---|---|---|---|
| Shell 3.2 → 3.3 | Shell 3.3 release notes | Runner mặc định | REPL, script, non-interactive | Chưa làm |
| Shell 3.3 → 3.4 | Release notes 3.4 và compatibility matrix | Kiểm tra dependency và deprecation | Compile, command tests | Chưa làm |
| Shell 3.4 → 4.0 | v4 migration guide | Annotation, modules, runner, completion, exit status | Integration và smoke tests | Chưa làm |
| Boot 3.5 → 4.0 | Boot 4 migration guide | Framework baseline, dependency, property, deprecated API | Full test suite, startup | Chưa làm |

Với mỗi dòng, ghi thêm:

- Link đến đúng tài liệu và phiên bản.
- File hoặc class bị ảnh hưởng.
- Người phụ trách và commit chứa thay đổi.
- Lệnh build/test đã chạy.
- Kết quả test thủ công cho command quan trọng.
- Vấn đề còn tồn tại và quyết định chấp nhận rủi ro.

Không đánh dấu hoàn thành chỉ vì đã đọc tài liệu. Một mục chỉ hoàn tất khi code/config đã được cập nhật và có kiểm chứng phù hợp.

## 10. Thực hiện từng chặng và giữ điểm quay lại

Một chu trình nâng cấp an toàn có thể tổ chức như sau:

1. Tạo nhánh hoặc worktree riêng cho chặng nâng cấp.
2. Ghi baseline: version, build result, test result và một số command smoke test.
3. Nâng dependency lên patch mới nhất của release line hiện tại.
4. Xử lý warning/deprecation có liên quan và bảo đảm test xanh.
5. Đọc migration guide và release notes của release line kế tiếp.
6. Thay BOM/plugin/dependency theo cặp phiên bản được hỗ trợ.
7. Sửa compile error, configuration và API đã thay đổi.
8. Chạy unit test, integration test, command test và smoke test.
9. Kiểm tra các mode interactive, non-interactive, script, help, completion và exit code nếu ứng dụng sử dụng chúng.
10. Commit một checkpoint có thể khôi phục.
11. Chỉ chuyển sang nhánh tiếp theo khi chặng hiện tại đã được xác nhận.

Nếu có lỗi, so sánh với baseline và xác định lỗi đến từ thay đổi code, dependency hay cấu hình. Một chặng nhỏ giúp khoanh vùng nguyên nhân dễ hơn nhiều so với thay đồng thời nhiều major dependency.

## 11. Kiểm tra sau mỗi chặng nâng cấp

Không chỉ chạy compile. Spring Shell là giao diện người dùng nên cần xác nhận hành vi CLI thực tế.

| Khu vực | Câu hỏi kiểm tra |
|---|---|
| Build | Dependency tree có phiên bản xung đột hoặc module trùng lặp không? |
| Startup | Application context có khởi động đúng profile không? |
| Registration | Tất cả command cần thiết có được đăng ký không? |
| Parsing | Tên command, argument, option, default và arity còn đúng không? |
| Validation | Giá trị không hợp lệ có bị từ chối với thông báo phù hợp không? |
| Availability | Command bị khóa theo trạng thái có còn hoạt động đúng không? |
| Completion | Tab completion có đề xuất đúng theo input hiện tại không? |
| Help | Synopsis, option và mô tả có còn chính xác không? |
| Output | Bảng, màu ANSI và encoding có còn đúng không? |
| Execution mode | Interactive, non-interactive và script có chạy đúng mode không? |
| Exit status | Script/CI nhận được mã thoát đúng khi thành công và thất bại không? |
| Packaging | JAR hoặc native image có chứa đúng dependency runtime không? |

Với một ứng dụng quản trị, hãy chọn một số command có rủi ro cao để chạy smoke test thực tế: đọc dữ liệu, cập nhật dữ liệu, thao tác file và command được gọi từ script. Nếu command thay đổi dữ liệu, dùng môi trường test hoặc dữ liệu có thể khôi phục.

## 12. Những lỗi thường gặp khi đọc tài liệu nâng cấp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ đọc guide của phiên bản đích | Bỏ sót thay đổi ở nhánh trung gian | Lập danh sách release line và đọc release notes từng nhánh |
| Chọn Shell version mới nhất mà không kiểm tra Boot | Dependency không tương thích | Đối chiếu compatibility matrix trước khi sửa version |
| Bỏ qua patch release | Không nhận được bug fix hoặc dependency update quan trọng | Nâng lên patch mới nhất của nhánh nguồn trước |
| Bỏ qua deprecation ở nhánh trước | API bị xóa ở major release gây nhiều lỗi cùng lúc | Xử lý warning và deprecated API trước khi nâng major |
| Chỉ cập nhật Spring Shell | Spring Boot/Framework hoặc BOM vẫn ở baseline cũ | Đọc migration guide của cả Spring Boot và Shell |
| Chỉ sửa compile error | Command có thể parse, runner hoặc exit code sai lúc chạy | Thêm command integration và smoke tests |
| Giữ dependency module cũ sau khi module đã gộp | Dependency dư thừa hoặc class trùng | Đối chiếu module migration và dependency tree |
| Đổi annotation nhưng không đổi option semantics | Help, default, validation hoặc completion sai | Kiểm thử từng option và đọc API của phiên bản đích |
| Dùng migration tool mãi trong production | Cấu hình tạm che giấu property cũ | Sửa property chính thức và gỡ migrator |
| Không ghi lại tài liệu đã đọc | Người khác không biết cơ sở của quyết định | Lưu link, version, thay đổi và bằng chứng test trong migration log |

## 13. Checklist đọc migration guide

- Ghi nhận phiên bản hiệu lực của Java, Boot, Framework, Shell và dependency liên quan.
- Xác định release line nguồn và release line đích.
- Đọc compatibility matrix trước khi chọn cặp dependency.
- Tìm hướng dẫn “Upgrading from” hoặc “Migration guide” cho từng nhánh.
- Đọc release notes của các nhánh trung gian, không chỉ major release.
- Kiểm tra system requirements và build tool.
- Kiểm tra BOM, starter, module đổi tên, module gộp hoặc module bị loại bỏ.
- Tìm API deprecated và API đã bị xóa.
- Tìm property đổi tên, đổi mặc định hoặc bị xóa.
- Kiểm tra command annotation, option, argument, completion và registration.
- Kiểm tra runner, interactive mode, exception mapping và exit code.
- Kiểm tra test API, native image và packaging nếu ứng dụng sử dụng.
- Ghi từng thay đổi thành task có file ảnh hưởng và cách xác nhận.
- Nâng từng chặng, chạy test và tạo checkpoint trước khi sang chặng sau.
- Gỡ dependency/tool migration tạm thời sau khi hoàn tất.

## 14. Bài tập thực hành

Giả sử một ứng dụng đang dùng Spring Boot 3.2.x và Spring Shell 3.2.x, mục tiêu là Spring Boot 4.0.x và Spring Shell 4.0.x:

1. Ghi nhận phiên bản Java, Boot, Framework, Shell và toàn bộ module Shell trong dependency tree.
2. Đọc compatibility matrix và xác định các cặp release line trung gian.
3. Đọc Spring Shell 3.3 release notes; ghi lại thay đổi runner mặc định.
4. Tạo test hoặc smoke test cho interactive, script và non-interactive mode.
5. Chuyển lên nhánh Shell 3.3 cùng Boot 3.3 tương thích; xác nhận hành vi runner.
6. Đọc tài liệu và release notes của Boot 3.4/3.5 cùng Shell 3.4; xác định patch mới nhất của nhánh đích trung gian.
7. Xử lý deprecated API và xác nhận build/test trước khi chuyển sang Boot 4.
8. Đọc toàn bộ Spring Shell v4 migration guide; lập danh sách annotation, module, runner, completion và exit-status cần sửa.
9. Đọc Spring Boot 4 migration guide; kiểm tra Java, Spring Framework, BOM và property.
10. Chuyển dependency sang cặp Boot 4.0.x/Shell 4.0.x được hỗ trợ.
11. Chuyển một command từ `@ShellComponent`/`@ShellMethod`/`@ShellOption` sang `@Command`/`@Option`; kiểm tra help và parsing.
12. Kiểm tra command grouping, completion provider và exception-to-exit-status mapping.
13. Chạy full test suite và smoke test command trong môi trường không có terminal tương tác.
14. Ghi lại tài liệu đã đọc, commit checkpoint và các vấn đề còn lại.

Khi hoàn thành, hãy giải thích vì sao bước từ Shell 3.4.x lên 4.x cần được chuẩn bị riêng, và vì sao thay đổi mặc định runner ở 3.3 phải được xử lý trước khi nâng tiếp.

## Tài liệu tham khảo

- [Spring Shell – Upgrading](https://docs.spring.io/spring-shell/reference/upgrading.html): trang chính thức dẫn đến hướng dẫn nâng cấp và release notes.
- [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): các thay đổi từ Spring Shell 3.x lên 4.x, dependency, command model, runner và API.
- [Spring Shell – 3.3 Release Notes](https://github.com/spring-projects/spring-shell/wiki/Spring-Shell-3.3-Release-Notes): thay đổi khi nâng từ 3.2 lên 3.3, bao gồm runner defaults.
- [Spring Shell – Spring Boot Compatibility](https://github.com/spring-projects/spring-shell/wiki/Spring-Boot-compatibility): các cặp phiên bản Boot và Shell được hỗ trợ.
- [Spring Shell – Releases](https://github.com/spring-projects/spring-shell/releases): release notes, patch updates và dependency upgrades của từng bản.
- [Spring Boot – Upgrading](https://docs.spring.io/spring-boot/upgrading.html): hướng dẫn nâng cấp và liên kết đến migration guide theo phiên bản.
- [Spring Boot – 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): điều kiện trước khi nâng, dependency baseline, deprecations và configuration changes.
- [Spring Boot – Older Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Older-Release-Notes): tìm release notes của các nhánh Boot cũ để đọc thay đổi trung gian.
