# PathInput cho đường dẫn và điều kiện hợp lệ

Nhiều command cần người dùng chọn một file nguồn, một thư mục làm việc hoặc đường dẫn đích. Nếu chỉ yêu cầu nhập chuỗi, ứng dụng phải tự chuyển chuỗi thành `Path` và giải thích lỗi khi đường dẫn sai. Spring Shell 3.x có component `PathInput` để hỏi đường dẫn trong terminal và trả về đối tượng `java.nio.file.Path`.

`PathInput` giúp thu thập đường dẫn theo giao diện tương tác và hiển thị thông tin liên quan đến path. Sau khi nhận kết quả, ứng dụng vẫn cần xác định điều kiện hợp lệ theo nghiệp vụ: file có tồn tại không, có phải file thường không, có đọc được không, thư mục đích có ghi được không hoặc path có nằm trong vùng được phép truy cập không.

## 1. PathInput là gì?

`PathInput` là một built-in component thuộc package `org.springframework.shell.component`. Component này kế thừa `AbstractTextComponent<Path, PathInput.PathInputContext>`, vì vậy giá trị kết quả của nó có kiểu `Path` thay vì `String`.

Các thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `PathInput` | Hiển thị prompt và nhận đường dẫn |
| `PathInput.PathInputContext` | Lưu input, kết quả `Path` và thông báo của component |
| `setPathProvider(Function<String, Path>)` | Cấu hình cách chuyển chuỗi đầu vào thành `Path` |
| `ResourceLoader` | Cung cấp tài nguyên và template cho component |
| `TemplateExecutor` | Thực thi template hiển thị của component |

`PathInput` phù hợp khi cần yêu cầu người dùng nhập một đường dẫn. Nếu cần quét một thư mục, tìm theo biểu thức và chọn một kết quả từ danh sách, hãy xem component `PathSearch`.

## 2. Tạo PathInput trong command

Trong mô hình command annotation của Spring Shell 3.x, có thể kế thừa `AbstractShellComponent` để truy cập terminal, resource loader và template executor:

~~~java
import java.nio.file.Path;

import org.springframework.shell.component.PathInput;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class PathCommands extends AbstractShellComponent {

    @ShellMethod(key = "component path input", value = "Nhập một đường dẫn")
    public String pathInput() {
        PathInput component = new PathInput(getTerminal(), "Nhập đường dẫn");
        component.setResourceLoader(getResourceLoader());
        component.setTemplateExecutor(getTemplateExecutor());

        PathInput.PathInputContext context =
                component.run(PathInput.PathInputContext.empty());

        Path path = context.getResultValue();
        return "Đường dẫn đã nhập: " + path;
    }
}
~~~

Quy trình cơ bản:

1. Tạo component với terminal hiện tại và tên prompt.
2. Gắn `ResourceLoader` và `TemplateExecutor` của Spring Shell.
3. Tạo context rỗng bằng `PathInputContext.empty()`.
4. Gọi `run(context)` để hiển thị prompt và nhận đầu vào.
5. Lấy đường dẫn bằng `context.getResultValue()`.

Kết quả là một đối tượng `Path`. Có thể dùng trực tiếp với Java NIO như `Files.exists(path)`, `Files.isDirectory(path)` hoặc `Files.isReadable(path)`.

## 3. Đọc dữ liệu từ PathInputContext

`PathInputContext` kế thừa `AbstractTextComponent.TextComponentContext<Path, PathInputContext>`. Những thuộc tính quan trọng gồm:

| Phương thức | Ý nghĩa |
|---|---|
| `getInput()` | Chuỗi người dùng đang hoặc đã nhập |
| `getResultValue()` | Kết quả kiểu `Path` |
| `getName()` | Tên prompt |
| `getMessage()` | Thông báo hiện tại |
| `getMessageLevel()` | Mức thông báo: INFO, WARN hoặc ERROR |
| `setMessage(message, level)` | Gắn thông báo và mức hiển thị |

Ví dụ đọc kết quả và xử lý trường hợp không có path:

~~~java
PathInput.PathInputContext context =
        component.run(PathInput.PathInputContext.empty());

Path path = context.getResultValue();
if (path == null) {
    return "Chưa chọn đường dẫn.";
}

return "Đã nhận: " + path.toAbsolutePath().normalize();
~~~

`getInput()` hữu ích khi cần xem chuỗi thô, còn `getResultValue()` là giá trị đã được component chuyển thành `Path`. Trong phần xử lý nghiệp vụ, ưu tiên dùng kết quả kiểu `Path`.

## 4. Tùy chỉnh cách phân giải đường dẫn

`PathInput` cung cấp `setPathProvider(Function<String, Path>)` để ứng dụng thay đổi cách chuyển chuỗi thô thành đối tượng `Path`. Ví dụ, ứng dụng muốn hỗ trợ ký hiệu `~` ở đầu đường dẫn để biểu diễn thư mục home:

~~~java
import java.nio.file.Path;
import java.nio.file.Paths;

PathInput component = new PathInput(getTerminal(), "File nguồn");
component.setResourceLoader(getResourceLoader());
component.setTemplateExecutor(getTemplateExecutor());
component.setPathProvider(rawPath -> {
    String expanded = rawPath;
    if (rawPath.startsWith("~")) {
        expanded = System.getProperty("user.home")
                + rawPath.substring(1);
    }
    return Paths.get(expanded).toAbsolutePath().normalize();
});
~~~

`setPathProvider` là điểm tùy chỉnh việc phân giải path. Nó không tự xác nhận file tồn tại, không kiểm tra quyền đọc/ghi và không áp dụng quy tắc bảo mật của ứng dụng. Những điều kiện đó phải được kiểm tra sau khi nhận kết quả.

Nếu ứng dụng không cần quy tắc phân giải riêng, hãy dùng cách phân giải mặc định. Không nên chuẩn hóa hoặc viết lại path theo một quy tắc riêng nếu người dùng cần giữ nguyên đường dẫn tương đối.

## 5. Kiểm tra file nguồn có tồn tại và đọc được

`PathInput` nhận đường dẫn; Java NIO cung cấp các phép kiểm tra thực tế. Ví dụ, command cần một file CSV có sẵn và đọc được:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

private boolean isReadableRegularFile(Path path) {
    return path != null
            && Files.isRegularFile(path)
            && Files.isReadable(path);
}
~~~

Ý nghĩa của từng điều kiện:

- `Files.exists(path)` kiểm tra path có tồn tại tại thời điểm kiểm tra.
- `Files.isRegularFile(path)` xác nhận path trỏ tới file thường.
- `Files.isDirectory(path)` xác nhận path trỏ tới thư mục.
- `Files.isReadable(path)` kiểm tra tiến trình hiện tại có thể đọc.
- `Files.isWritable(path)` kiểm tra tiến trình hiện tại có thể ghi.
- `Files.isExecutable(path)` kiểm tra tiến trình hiện tại có thể thực thi.

`Files.isRegularFile` và các phương thức kiểm tra tương tự thường trả về `false` khi path không tồn tại hoặc không thể xác định thuộc tính. Nếu cần biết nguyên nhân I/O chi tiết, dùng thao tác như `Files.readAttributes` hoặc mở file và xử lý `IOException`.

## 6. Yêu cầu file nguồn và thư mục đích khác nhau

Điều kiện hợp lệ phụ thuộc mục đích sử dụng path. Không nên dùng cùng một phép kiểm tra cho mọi trường hợp.

| Mục đích | Điều kiện cần kiểm tra |
|---|---|
| Đọc file nguồn | File tồn tại, là file thường và đọc được |
| Đọc thư mục | Tồn tại, là thư mục và có thể liệt kê nội dung nếu cần |
| Ghi file mới | Thư mục cha tồn tại và ghi được |
| Ghi đè file | File đích nếu tồn tại phải đúng loại và có thể ghi; thư mục cha cũng phải ghi được |
| Chạy chương trình | File tồn tại, là file phù hợp và có quyền thực thi |

Ví dụ kiểm tra file nguồn:

~~~java
private Path requireReadableFile(Path input) {
    Path path = input.toAbsolutePath().normalize();

    if (!Files.isRegularFile(path)) {
        throw new IllegalArgumentException(
                "Đường dẫn không phải file thường: " + path);
    }
    if (!Files.isReadable(path)) {
        throw new IllegalArgumentException(
                "Không có quyền đọc file: " + path);
    }
    return path;
}
~~~

Ví dụ kiểm tra thư mục đích:

~~~java
private Path requireWritableDirectory(Path input) {
    Path path = input.toAbsolutePath().normalize();

    if (!Files.isDirectory(path)) {
        throw new IllegalArgumentException(
                "Thư mục đích không tồn tại: " + path);
    }
    if (!Files.isWritable(path)) {
        throw new IllegalArgumentException(
                "Không có quyền ghi vào thư mục: " + path);
    }
    return path;
}
~~~

`Files.isWritable` là phép kiểm tra tại thời điểm gọi. Nó không bảo đảm thao tác ghi sau đó chắc chắn thành công; ổ đĩa có thể đầy, quyền có thể thay đổi hoặc file có thể bị tiến trình khác thay thế.

## 7. Yêu cầu đường dẫn file đầu ra

File đầu ra có thể chưa tồn tại. Vì vậy, không thể bắt buộc `Files.exists(output)` như với file nguồn.

Một cách kiểm tra thường dùng:

~~~java
private Path requireWritableOutput(Path input) {
    Path output = input.toAbsolutePath().normalize();
    Path parent = output.getParent();

    if (parent == null || !Files.isDirectory(parent)) {
        throw new IllegalArgumentException(
                "Thư mục cha của file đầu ra không tồn tại.");
    }
    if (!Files.isWritable(parent)) {
        throw new IllegalArgumentException(
                "Không có quyền ghi vào thư mục đích.");
    }
    if (Files.exists(output)
            && (!Files.isRegularFile(output) || !Files.isWritable(output))) {
        throw new IllegalArgumentException(
                "File đầu ra hiện có không thể ghi: " + output);
    }
    return output;
}
~~~

Sau bước kiểm tra, vẫn phải bắt `IOException` khi thực sự tạo hoặc ghi file:

~~~java
try (var writer = Files.newBufferedWriter(output)) {
    writer.write("report content");
} catch (IOException ex) {
    throw new IllegalStateException(
            "Không thể ghi file đầu ra: " + output, ex);
}
~~~

Kiểm tra trước giúp đưa ra thông báo thân thiện. Thao tác mở file mới là bước xác nhận cuối cùng rằng hệ điều hành cho phép ghi.

## 8. Yêu cầu người dùng nhập lại khi path không hợp lệ

`PathInput` không khai báo một thuộc tính validator chuyên biệt như một số form framework. Cách đơn giản là chạy component, kiểm tra kết quả và hiển thị thông báo trước khi yêu cầu nhập lại:

~~~java
private Path askForReadableFile() {
    PathInput component = new PathInput(
            getTerminal(), "Nhập file nguồn");
    component.setResourceLoader(getResourceLoader());
    component.setTemplateExecutor(getTemplateExecutor());

    while (true) {
        PathInput.PathInputContext context =
                component.run(PathInput.PathInputContext.empty());
        Path path = context.getResultValue();

        if (path == null) {
            return null;
        }
        if (Files.isRegularFile(path) && Files.isReadable(path)) {
            return path.toAbsolutePath().normalize();
        }

        System.out.println(
                "File không tồn tại, không phải file thường hoặc không đọc được. Hãy thử lại.");
    }
}
~~~

Vòng lặp giữ cho quy tắc kiểm tra nằm trong ứng dụng. Nếu người dùng thoát component hoặc không có kết quả, command có thể kết thúc theo nhánh riêng thay vì tiếp tục với giá trị null.

Với thông báo cần hiển thị ngay trong giao diện component, context hỗ trợ `setMessage(message, MessageLevel)`. Có thể dùng renderer hoặc template riêng để trình bày thông báo và trạng thái. Tuy nhiên, logic kiểm tra vẫn do ứng dụng định nghĩa.

## 9. Dùng ComponentFlow cho nhiều đường dẫn

Khi cần nhập file nguồn và thư mục đích trong cùng một wizard, `ComponentFlow` giúp nối nhiều component thành một luồng. `ComponentFlow.Builder` cung cấp `withPathInput(id)`; `PathInputSpec` hỗ trợ tên, giá trị mặc định, renderer, handler trước/sau và hàm `next` để chọn component tiếp theo.

Ví dụ luồng hỏi file nguồn, kiểm tra điều kiện rồi hỏi thư mục đích:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.support.AbstractTextComponent.TextComponentContext.MessageLevel;

class ImportWizard {

    @Autowired
    private ComponentFlow.Builder componentFlowBuilder;

    public void run() {
        ComponentFlow flow = componentFlowBuilder.clone().reset()
                .withPathInput("source")
                    .name("File nguồn")
                    .next(context -> {
                        Path path = context.getResultValue();
                        if (path != null
                                && Files.isRegularFile(path)
                                && Files.isReadable(path)) {
                            return "destination";
                        }
                        context.setMessage(
                                "Chọn file thường đang tồn tại và có thể đọc.",
                                MessageLevel.ERROR);
                        return "source";
                    })
                    .and()
                .withPathInput("destination")
                    .name("Thư mục đích")
                    .next(context -> {
                        Path path = context.getResultValue();
                        if (path != null
                                && Files.isDirectory(path)
                                && Files.isWritable(path)) {
                            return null;
                        }
                        context.setMessage(
                                "Chọn thư mục tồn tại và có thể ghi.",
                                MessageLevel.ERROR);
                        return "destination";
                    })
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        Path source = result.getContext().get("source", Path.class);
        Path destination = result.getContext().get("destination", Path.class);

        // Tiếp tục xử lý import sau khi cả hai path đã hợp lệ.
    }
}
~~~

Trong ví dụ, `next` nhận context của PathInput vừa chạy:

- Nếu file nguồn hợp lệ, trả về id `destination` để chuyển sang bước tiếp theo.
- Nếu không hợp lệ, gắn thông báo mức ERROR và trả về id `source` để yêu cầu nhập lại.
- Với thư mục đích, chỉ kết thúc flow khi thư mục tồn tại và có thể ghi.
- Trả về `null` làm flow dừng.

`ComponentFlowResult.getContext()` trả về context chung. Mỗi component lưu kết quả theo id của nó; có thể lấy kiểu tường minh bằng `get("source", Path.class)`. Việc lưu kết quả được bật mặc định trong `PathInputSpec`, nhưng có thể điều chỉnh bằng `storeResult(boolean)`.

## 10. Chọn PathInput hay PathSearch?

Spring Shell 3.x có hai component liên quan đến đường dẫn:

| Component | Cách tương tác | Trường hợp phù hợp |
|---|---|---|
| `PathInput` | Người dùng nhập một đường dẫn | Nhập file hoặc thư mục đã biết |
| `PathSearch` | Quét thư mục gốc, tìm theo biểu thức và chọn từ danh sách kết quả | Người dùng chưa biết chính xác tên file hoặc muốn duyệt kết quả |

`PathSearch` nhận base directory và biểu thức tìm kiếm tùy chọn. `PathSearchConfig` cho phép giới hạn số path được tìm/hiển thị và cấu hình hướng tìm, phân biệt chữ hoa/chữ thường hoặc chuẩn hóa chuỗi.

Ví dụ:

~~~java
import org.springframework.shell.component.PathSearch;

PathSearch.PathSearchConfig config =
        new PathSearch.PathSearchConfig();
config.setMaxPathsShow(5);
config.setMaxPathsSearch(100);
config.setSearchForward(true);
config.setSearchCaseSensitive(false);
config.setSearchNormalize(false);

PathSearch component =
        new PathSearch(getTerminal(), "Tìm file", config);
component.setResourceLoader(getResourceLoader());
component.setTemplateExecutor(getTemplateExecutor());

PathSearch.PathSearchContext context =
        component.run(PathSearch.PathSearchContext.empty());
Path selected = context.getResultValue();
~~~

`PathSearch` phù hợp cho thao tác khám phá và chọn kết quả. Sau khi chọn, vẫn cần kiểm tra quyền truy cập và điều kiện nghiệp vụ giống như với `PathInput`.

## 11. Giới hạn và bảo vệ đường dẫn

Chuyển một chuỗi thành `Path` không có nghĩa đường dẫn đó an toàn. Khi command chỉ cho phép thao tác trong một thư mục gốc, cần kiểm tra path sau khi chuẩn hóa và xử lý symbolic link.

Ví dụ, với file nguồn đã tồn tại:

~~~java
Path allowedRoot = configuredRoot.toRealPath();
Path candidate = input.toRealPath();

if (!candidate.startsWith(allowedRoot)) {
    throw new SecurityException(
            "Đường dẫn nằm ngoài thư mục được phép.");
}
~~~

`normalize()` chỉ loại bỏ các đoạn dư như `.` và `..` trong biểu diễn path. Nó không tự giải quyết symbolic link. `toRealPath()` yêu cầu đường dẫn tồn tại và trả về đường dẫn đã phân giải theo hệ thống file, vì vậy phù hợp để kiểm tra file nguồn.

Với file đầu ra chưa tồn tại, hãy xác minh thư mục cha bằng `toRealPath()` và bảo đảm thư mục đó nằm dưới thư mục gốc được phép. Nếu file đích đã tồn tại, kiểm tra cả đường dẫn thực của file để tránh symbolic link trỏ ra ngoài vùng cho phép.

Không dựa vào một lần kiểm tra `Files.isWritable` để bảo đảm thao tác sau đó thành công. Quyền và trạng thái file có thể thay đổi giữa lúc kiểm tra và lúc mở file. Luôn bắt lỗi I/O tại thời điểm đọc hoặc ghi.

## 12. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getResultValue()` trả về `null` | Người dùng thoát hoặc không hoàn tất nhập | Xử lý nhánh hủy trước khi gọi API file |
| Path chuyển đổi được nhưng file không tồn tại | Chỉ mới phân giải chuỗi thành `Path` | Kiểm tra `Files.exists` hoặc phép kiểm tra chuyên biệt |
| Chọn nhầm thư mục thay vì file | Chỉ kiểm tra tồn tại | Dùng `Files.isRegularFile` |
| Có file nhưng không đọc được | Quyền của tiến trình không cho phép đọc | Kiểm tra `Files.isReadable` và xử lý `IOException` |
| Thư mục đích tồn tại nhưng không ghi được | Quyền ghi hoặc chính sách hệ thống file không cho phép | Kiểm tra `Files.isWritable` và bắt lỗi khi tạo file |
| Đường dẫn tương đối trỏ sai nơi | Thư mục làm việc hiện tại khác dự kiến | Hiển thị path tuyệt đối và chuẩn hóa khi phù hợp |
| Path thoát khỏi thư mục gốc | Dùng `..` hoặc symbolic link | Kiểm tra `toRealPath` và quan hệ `startsWith` với root |
| Flow không chuyển sang bước tiếp theo | `next` trả về sai id hoặc id không tồn tại | Dùng id trùng với tên khai báo trong `withPathInput` |
| Flow dừng sớm | `next` trả về `null` hoặc id không hợp lệ | Chỉ trả `null` khi muốn kết thúc wizard |
| Component không hiển thị đúng trong test | Test không cung cấp terminal tương tác phù hợp | Dùng terminal test của Spring Shell và kiểm tra TTY |

## 13. Bài tập thực hành

Xây dựng command `import-data` với hai đầu vào:

- File CSV nguồn phải tồn tại, là file thường và đọc được.
- Thư mục đích phải tồn tại và có thể ghi.

Yêu cầu:

1. Tạo `PathInput` cho file nguồn và thư mục đích.
2. Gắn `ResourceLoader` và `TemplateExecutor` cho từng component.
3. Lấy kết quả kiểu `Path` từ `PathInputContext`.
4. Kiểm tra file nguồn bằng `Files.isRegularFile` và `Files.isReadable`.
5. Kiểm tra thư mục đích bằng `Files.isDirectory` và `Files.isWritable`.
6. Nếu đầu vào sai, thông báo rõ điều kiện chưa đạt và yêu cầu nhập lại.
7. Thực hiện import chỉ sau khi cả hai đường dẫn hợp lệ.
8. Thêm kiểm tra đường dẫn thực nếu ứng dụng giới hạn truy cập trong một thư mục gốc.

Thử các trường hợp:

| Đầu vào | Kết quả mong đợi |
|---|---|
| File CSV hợp lệ và thư mục có thể ghi | Tiếp tục import |
| File không tồn tại | Yêu cầu nhập lại file nguồn |
| Path trỏ tới thư mục thay vì file | Báo file nguồn phải là file thường |
| File không đọc được | Báo lỗi quyền đọc |
| Thư mục đích không tồn tại | Yêu cầu nhập lại thư mục |
| Thư mục đích không ghi được | Báo lỗi quyền ghi |
| Path nằm ngoài root được phép | Từ chối thao tác |

Sau khi hoàn thành, hãy giải thích được sự khác nhau giữa việc phân giải một chuỗi thành `Path` và việc xác nhận path đáp ứng điều kiện nghiệp vụ.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Path Input](https://docs.spring.io/spring-shell/reference/3.4/components/ui/pathinput.html)
- [Spring Shell 3.4 API – PathInput](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathInput.html)
- [Spring Shell 3.4 API – PathInput.PathInputContext](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathInput.PathInputContext.html)
- [Spring Shell 3.4 – Path Search](https://docs.spring.io/spring-shell/reference/3.4/components/ui/pathsearch.html)
- [Spring Shell 3.4 – Flow Components](https://docs.spring.io/spring-shell/reference/3.4/components/ui/)
- [Spring Shell 3.4 API – PathInputSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/PathInputSpec.html)
- [Spring Shell 3.4 API – ComponentFlow.ComponentFlowResult](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [Java API – Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Java API – Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html)
