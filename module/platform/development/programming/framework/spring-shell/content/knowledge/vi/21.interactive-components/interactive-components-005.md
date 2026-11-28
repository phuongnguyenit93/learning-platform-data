# PathSearch cho trải nghiệm tìm kiếm đường dẫn

Khi command cần người dùng chọn một file hoặc thư mục, bắt họ nhập toàn bộ đường dẫn dễ dẫn đến lỗi chính tả và khó dùng khi cấu trúc thư mục lớn. Spring Shell 3.x cung cấp `PathSearch`, một interactive component cho phép nhập thư mục gốc, gõ biểu thức tìm kiếm và chọn một đường dẫn từ danh sách kết quả.

`PathSearch` trả về `java.nio.file.Path`. Component có cấu hình giới hạn số đường dẫn được quét và hiển thị, tùy chọn tìm kiếm phân biệt hoa thường, chuẩn hóa văn bản và hướng tìm kiếm. Có thể thay cách phân giải đường dẫn hoặc cung cấp bộ quét tùy chỉnh để giới hạn vùng tìm kiếm theo chính sách ứng dụng.

## 1. PathSearch giải quyết vấn đề gì?

Giả sử command `import-config` cần một file YAML. Người dùng có thể phải nhớ đường dẫn dài như:

```text
/workspace/customer-platform/config/environments/staging/application.yml
```

Với `PathSearch`, người dùng nhập thư mục gốc cần quét, thêm từ khóa tìm kiếm và chọn một kết quả. Component hiển thị kết quả trong danh sách chọn đơn, giúp người dùng tìm file theo tên mà không cần nhập chính xác toàn bộ đường dẫn.

Các tình huống phù hợp:

- Chọn file cấu hình để import hoặc validate.
- Chọn thư mục dự án để chạy build hoặc deploy.
- Tìm file log, báo cáo hoặc artifact trong workspace.
- Chọn thư mục đầu vào cho command xử lý hàng loạt.
- Tìm một file theo vài ký tự trong tên hoặc đường dẫn.

`PathSearch` là component tương tác trong terminal. Nó không phải API tìm kiếm file dùng cho batch job và không thay thế việc kiểm tra quyền đọc/ghi trong service nghiệp vụ.

## 2. Luồng nhập và chọn đường dẫn

Path search yêu cầu một base directory để quét và một search expression tùy chọn. Người dùng nhập base path, sau đó phân cách bằng dấu cách rồi nhập từ khóa tìm kiếm. Kết quả được hiển thị trong một danh sách chọn đơn.

Ví dụ về ý định nhập:

```text
/workspace/customer-platform config
```

Trong đó:

- `/workspace/customer-platform` là thư mục gốc cần quét.
- `config` là từ khóa để lọc kết quả.
- Người dùng chọn một đường dẫn trong danh sách kết quả.

Có thể bắt đầu chỉ với base directory rồi tìm tiếp bằng cách gõ biểu thức. Cú pháp chính xác của chuỗi nhập, đặc biệt khi tên thư mục có dấu cách, cần được thử với parser và phiên bản Spring Shell đang dùng. Không nên mặc định dấu nháy trong đường dẫn được xử lý như một command line shell thông thường.

## 3. Dùng PathSearch trong command Spring Shell 3.x

Trong Spring Shell 3.x, `PathSearch` thuộc package `org.springframework.shell.component`. Cách đơn giản là tạo component trong một `@ShellComponent` kế thừa `AbstractShellComponent`, sau đó dùng terminal, resource loader và template executor được lớp cha cung cấp.

```java
import java.nio.file.Path;

import org.springframework.shell.component.PathSearch;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ComponentCommands extends AbstractShellComponent {

    @ShellMethod(key = "component path search", value = "Tìm và chọn một đường dẫn")
    public String pathSearch() {
        PathSearch component = new PathSearch(getTerminal(), "Chọn đường dẫn");
        component.setResourceLoader(getResourceLoader());
        component.setTemplateExecutor(getTemplateExecutor());

        PathSearch.PathSearchContext context =
                component.run(PathSearch.PathSearchContext.empty());
        Path selected = context.getResultValue();

        if (selected == null) {
            return "Chưa chọn đường dẫn.";
        }
        return "Đường dẫn đã chọn: " + selected;
    }
}
```

`run(...)` chạy giao diện tìm kiếm và trả về context đã được cập nhật. `getResultValue()` trả về `Path` được chọn. Ví dụ kiểm tra `null` trước khi sử dụng kết quả để xử lý trường hợp người dùng thoát hoặc không chọn được mục nào.

`setResourceLoader(...)` và `setTemplateExecutor(...)` cung cấp các dịch vụ cần thiết để component tải và render template. Đây là cách dùng được tài liệu Spring Shell 3.4.3 minh họa. <Link url="https://docs.spring.io/spring-shell/reference/3.4/components/ui/pathsearch.html" title="Path Search — Spring Shell 3.4.3"/>.

## 4. Cấu hình số kết quả và cách tìm kiếm

`PathSearchConfig` điều khiển số lượng đường dẫn được tìm, số kết quả hiển thị và một số tùy chọn của thuật toán tìm kiếm.

```java
import org.springframework.shell.component.PathSearch;

PathSearch.PathSearchConfig config = new PathSearch.PathSearchConfig();
config.setMaxPathsShow(8);
config.setMaxPathsSearch(200);
config.setSearchForward(true);
config.setSearchCaseSensitive(false);
config.setSearchNormalize(false);

PathSearch component = new PathSearch(
        getTerminal(), "Chọn file cấu hình", config);
```

| Thuộc tính | Tác dụng | Gợi ý sử dụng |
| --- | --- | --- |
| `maxPathsShow` | Giới hạn số kết quả đưa lên danh sách hiển thị | Chọn số vừa đủ để người dùng dễ duyệt |
| `maxPathsSearch` | Giới hạn số đường dẫn được đưa vào quá trình tìm kiếm | Giảm chi phí khi cây thư mục lớn |
| `searchForward` | Cấu hình hướng tìm kiếm của thuật toán | Giữ mặc định nếu không có nhu cầu đặc biệt |
| `searchCaseSensitive` | Bật/tắt phân biệt chữ hoa và chữ thường | Thường để `false` cho tên file |
| `searchNormalize` | Bật/tắt chuẩn hóa văn bản trước khi so khớp | Hữu ích khi dữ liệu có biến thể ký tự Unicode |

Hai giới hạn `maxPathsSearch` và `maxPathsShow` có vai trò khác nhau. Giới hạn tìm kiếm kiểm soát số candidate được xử lý; giới hạn hiển thị kiểm soát số mục đưa ra danh sách. Tăng cả hai không phải lúc nào cũng làm trải nghiệm tốt hơn vì có thể tăng thời gian quét và khiến danh sách khó chọn.

Các thuộc tính này được cung cấp qua getter/setter trong `PathSearch.PathSearchConfig`. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathSearch.PathSearchConfig.html" title="PathSearchConfig API — Spring Shell 3.4.3"/>.

## 5. Tìm kiếm fuzzy và exact

Spring Shell dùng các thuật toán tìm kiếm lấy cảm hứng từ `fzf`. Tìm kiếm fuzzy cho phép các ký tự của từ khóa xuất hiện theo thứ tự trong tên cần tìm, dù không đứng liền nhau. Tìm kiếm exact phù hợp khi người dùng biết chính xác chuỗi cần xuất hiện.

Ví dụ cú pháp trong phần Search Algorithms:

| Biểu thức | Kiểu so khớp | Ý nghĩa |
| --- | --- | --- |
| `conf` | Fuzzy match | Có thể khớp `config.yml` |
| `apcfg` | Fuzzy match | Có thể khớp `application-config.yml` |
| `'application` | Exact match | Tìm mục có chứa chuỗi `application` |

`FuzzyMatchV2Search` là bản port thuật toán fuzzy của fzf, hướng đến tìm nhanh. `ExactMatchNaive` thực hiện so khớp chính xác đơn giản. Cú pháp và lựa chọn thuật toán được Spring Shell xử lý; người dùng không cần tự viết thuật toán cho trường hợp thông thường.

Khi dùng tìm kiếm fuzzy, kết quả có thể chứa các tên gần giống nhưng không phải chuỗi con liên tục. Nếu cần tên file phải chứa chính xác một đoạn văn bản, dùng cú pháp exact được tài liệu mô tả. <Link url="https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/searchalgorithm.html" title="Search Algorithms — Spring Shell 3.4.3"/>.

## 6. Tùy chỉnh cách phân giải base path

`PathSearch` có `setPathProvider(Function<String, Path>)`. Path provider nhận chuỗi đường dẫn thô do người dùng nhập và chuyển nó thành `Path`. Có thể dùng điểm mở rộng này để hỗ trợ alias hoặc chuẩn hóa đường dẫn theo quy ước của ứng dụng.

Ví dụ hỗ trợ ký hiệu `~/` để bắt đầu từ home directory:

```java
import java.nio.file.Path;

// component đã được tạo như ví dụ ở mục 3.
component.setPathProvider(rawPath -> {
    if (rawPath.startsWith("~/")) {
        return Path.of(System.getProperty("user.home"))
                .resolve(rawPath.substring(2))
                .toAbsolutePath()
                .normalize();
    }

    return Path.of(rawPath).toAbsolutePath().normalize();
});
```

Path provider chỉ giải quyết cách chuyển chuỗi thành `Path`. Nó không tự cấp quyền truy cập và không chứng minh file an toàn. Sau khi người dùng chọn kết quả, service vẫn phải kiểm tra file tồn tại, loại file và quyền sử dụng theo nghiệp vụ.

API `setPathProvider` nhận `Function<String, Path>` trên `PathSearch` 3.4.3. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathSearch.html" title="PathSearch API — Spring Shell 3.4.3"/>.

## 7. Tùy chỉnh bộ quét đường dẫn

Khi cách quét mặc định không phù hợp, `PathSearchConfig` có `setPathScanner(...)`. API nhận một `Supplier` cung cấp `BiFunction<String, PathSearchContext, PathScannerResult>`.

Điểm mở rộng này phù hợp khi ứng dụng cần:

- Chỉ tìm trong một số thư mục được phép.
- Bỏ qua thư mục build, cache hoặc thư mục ẩn.
- Chỉ đưa file có phần mở rộng nhất định vào kết quả.
- Giới hạn độ sâu quét hoặc số file được kiểm tra.
- Áp dụng cách lấy dữ liệu riêng thay cho filesystem scanner mặc định.

Scanner nhận biểu thức tìm kiếm và context, rồi trả về `PathScannerResult`. Kết quả có thể chứa danh sách `ScoredPath`, số thư mục, số file và cờ cho biết có filter hay không. Mỗi `ScoredPath` giữ một `Path` cùng `SearchMatchResult`, nhờ đó component có thể sắp xếp và hiển thị mức độ khớp.

Đây là API nâng cao. Nếu chỉ cần thay base path hoặc chuẩn hóa đường dẫn, `setPathProvider` đơn giản hơn. Chỉ triển khai scanner riêng khi cần thay đổi phạm vi hoặc thuật toán thu thập kết quả; khi đó cần tự kiểm thử cả tốc độ, thứ tự kết quả và hành vi khi không tìm thấy mục phù hợp.

## 8. Context của PathSearch

`PathSearchContext` là context riêng của component. Nó kế thừa `TextComponentContext<Path, ...>`, vì vậy có thể đọc input, message và giá trị kết quả kiểu `Path`.

Các thành phần quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `PathSearchContext.empty()` | Tạo context ban đầu |
| `getInput()` | Lấy nội dung người dùng đang nhập |
| `getResultValue()` | Lấy `Path` đã chọn |
| `getPathViewItems()` | Lấy các mục đang được dùng để render danh sách kết quả |
| `getPathSearchConfig()` | Lấy cấu hình tìm kiếm hiện tại |
| `getMessage()` / `getMessageLevel()` | Lấy thông báo và mức thông báo trong component |

Context cũng có `model` để kế thừa các biến template từ component cha. Tài liệu PathSearch mô tả `pathViewItems` và `model` là các template variables. Nếu tùy chỉnh renderer hoặc template, hãy đọc context thay vì tự duy trì một danh sách kết quả khác có thể lệch với lựa chọn hiện tại.

## 9. Tùy chỉnh cách hiển thị kết quả

`PathSearch` có constructor nhận renderer dạng `Function<PathSearchContext, List<AttributedString>>`; component cũng kế thừa `setRenderer(...)` từ `AbstractComponent`. Vì vậy, có thể thay đổi cách hiển thị tên file, thư mục hoặc thông tin phụ.

Một renderer tùy chỉnh có thể hiển thị:

- Tên đường dẫn và loại mục (file/thư mục).
- Đường dẫn tương đối so với base directory.
- Kích thước file hoặc thời gian sửa đổi nếu ứng dụng cần.
- Đánh dấu phần tên khớp với biểu thức tìm kiếm.
- Thông báo khi không có kết quả hoặc kết quả bị giới hạn.

Không nên thực hiện I/O nặng trong renderer vì renderer có thể được gọi nhiều lần khi người dùng thay đổi input hoặc di chuyển lựa chọn. Nếu cần metadata như kích thước hoặc thời gian sửa đổi, hãy lấy trong scanner và truyền cùng dữ liệu cần thiết qua context/model hoặc cache trong phạm vi lần chạy component.

## 10. Kiểm tra kết quả sau khi người dùng chọn

`PathSearch` giúp tìm và chọn một `Path`; command chịu trách nhiệm xác nhận lựa chọn phù hợp với thao tác tiếp theo.

Ví dụ chỉ chấp nhận file cấu hình YAML:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

private Path validateConfigFile(Path selected) throws IOException {
    if (selected == null) {
        throw new IllegalArgumentException("Bạn chưa chọn file cấu hình.");
    }

    Path realPath = selected.toRealPath();
    if (!Files.isRegularFile(realPath)) {
        throw new IllegalArgumentException("Đường dẫn đã chọn không phải file thường.");
    }
    if (!Files.isReadable(realPath)) {
        throw new IllegalArgumentException("Không có quyền đọc file đã chọn.");
    }
    if (!realPath.getFileName().toString().endsWith(".yml")
            && !realPath.getFileName().toString().endsWith(".yaml")) {
        throw new IllegalArgumentException("Chỉ chấp nhận file YAML.");
    }
    return realPath;
}
```

Nếu command chỉ cho phép file nằm dưới workspace, hãy xác minh đường dẫn thực sau khi resolve symbolic link:

```java
Path allowedRoot = Path.of("/workspace/config").toRealPath();
Path selectedRealPath = selected.toRealPath();

if (!selectedRealPath.startsWith(allowedRoot)) {
    throw new IllegalArgumentException("File nằm ngoài thư mục cấu hình cho phép.");
}
```

So sánh `Path` sau `toRealPath()` giúp phát hiện đường dẫn symbolic link trỏ ra ngoài thư mục gốc. Không dùng `String.startsWith` trên đường dẫn thô để làm kiểm soát bảo mật.

## 11. Chỉ cho chọn file hoặc chỉ cho chọn thư mục

PathSearch trả về `Path`; command có thể cần file, thư mục hoặc cả hai. Hãy kiểm tra loại mục sau khi chọn:

```java
import java.nio.file.Files;
import java.nio.file.Path;

if (Files.isDirectory(selected)) {
    // Xử lý thư mục
} else if (Files.isRegularFile(selected)) {
    // Xử lý file thường
} else {
    throw new IllegalArgumentException("Loại đường dẫn không được hỗ trợ.");
}
```

Nếu muốn danh sách gợi ý chỉ chứa file hoặc chỉ chứa thư mục, cấu hình scanner riêng để lọc từ đầu. Kiểm tra sau khi chọn vẫn cần thiết vì trạng thái file system có thể thay đổi giữa lúc quét và lúc command sử dụng kết quả.

## 12. Hiệu năng khi tìm trong cây thư mục lớn

Tìm kiếm đường dẫn có thể tốn thời gian khi base directory chứa nhiều file, nhiều tầng thư mục hoặc mount mạng. Một số nguyên tắc giúp trải nghiệm ổn định:

- Chọn base directory càng cụ thể càng tốt; không quét toàn bộ ổ đĩa nếu không cần.
- Đặt `maxPathsSearch` phù hợp với quy mô dữ liệu.
- Giữ `maxPathsShow` vừa đủ để danh sách dễ duyệt.
- Dùng scanner riêng để bỏ qua `target`, `build`, `.git`, cache và thư mục không liên quan.
- Tránh đọc nội dung từng file chỉ để tìm theo tên.
- Với filesystem mạng, đặt giới hạn thời gian hoặc phạm vi quét trong scanner riêng.
- Không thực hiện truy vấn mạng hoặc đọc metadata chậm trong renderer.

Giới hạn kết quả làm trải nghiệm nhanh hơn nhưng cũng có thể khiến file cần tìm không nằm trong số candidate được xử lý. Nếu người dùng không tìm thấy file, hướng dẫn họ chọn base directory hẹp hơn hoặc tăng giới hạn có kiểm soát.

## 13. PathSearch cần terminal tương tác

PathSearch là component giao diện tương tác dùng terminal/JLine. Nó phù hợp khi người dùng đang ở shell và có thể nhập, duyệt danh sách rồi chọn một mục.

Trong script, CI hoặc non-interactive mode, không nên gọi PathSearch và chờ người dùng chọn. Hãy cung cấp đường dẫn rõ ràng qua argument/option, ví dụ:

```text
import-config --file /workspace/config/staging.yml
```

Sau đó dùng cùng service validation như command tương tác. Cách này giữ cho command có thể chạy tự động mà không phụ thuộc vào bàn phím hoặc terminal.

## 14. Kiểm thử PathSearch

Kiểm thử nên bao gồm cấu hình, kết quả chọn và kiểm tra file sau khi chọn.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Base directory hợp lệ | Component quét đúng vùng đã chọn |
| Base directory không tồn tại | Hiển thị lỗi phù hợp và không làm command tiếp tục với Path rỗng |
| Không có search expression | Danh sách kết quả phù hợp với chính sách mặc định |
| Fuzzy expression | Tìm được tên có các ký tự khớp theo thứ tự |
| Exact expression | Chỉ trả kết quả chứa chuỗi cần tìm |
| Phân biệt hoa thường | Hành vi khớp `searchCaseSensitive` |
| Unicode normalization | Hành vi khớp `searchNormalize` |
| Kết quả vượt giới hạn | `maxPathsSearch` và `maxPathsShow` được áp dụng |
| Người dùng thoát | Command xử lý trường hợp không có `resultValue` |
| Chọn file sai loại | Service từ chối file/thư mục không phù hợp |
| Symbolic link thoát khỏi root | Kiểm tra `toRealPath()` từ chối đường dẫn |
| Terminal không tương tác | Command tự động dùng option đường dẫn thay vì mở PathSearch |

Có thể kiểm thử logic `PathProvider`, scanner và validation bằng unit test. Với trải nghiệm nhập và chọn thực tế, dùng integration test có pseudo-terminal hoặc terminal tương tác; kiểm tra thêm các đường dẫn có dấu cách, Unicode và quyền file khác nhau.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Danh sách không có file mong muốn | Base directory sai hoặc giới hạn search quá thấp | Chọn root cụ thể đúng và điều chỉnh `maxPathsSearch` |
| Từ khóa không tìm được tên gần giống | Đang dùng exact syntax hoặc cấu hình phân biệt hoa thường | Dùng fuzzy expression, kiểm tra `searchCaseSensitive` |
| Kết quả quá nhiều | Base directory quá rộng hoặc giới hạn hiển thị lớn | Thu hẹp root và giảm `maxPathsShow` |
| Đường dẫn `~/...` không hoạt động | Path provider chưa mở rộng home alias | Cấu hình `setPathProvider` |
| Chọn xong nhưng command báo lỗi | Path đã thay đổi, không tồn tại hoặc sai loại | Kiểm tra lại bằng `Files` trước khi xử lý |
| Người dùng chọn file ngoài workspace | Scanner không giới hạn vùng tìm kiếm | Giới hạn scanner và xác minh real path trong service |
| Component không chạy trong CI | Không có terminal tương tác | Nhận path qua argument/option |
| Tìm kiếm chậm | Quét cây thư mục quá lớn hoặc I/O trong renderer | Thu hẹp base path, giới hạn candidate và tối ưu scanner |

## 16. Bài thực hành tổng hợp

Xây dựng command `import-config` để người dùng chọn file YAML trong workspace:

1. Tạo command `component path search` dùng `PathSearch` và `AbstractShellComponent`.
2. Cấu hình `maxPathsShow=8`, `maxPathsSearch=200`, tìm không phân biệt hoa thường.
3. Cho phép người dùng tìm bằng tên gần đúng như `stg yml` hoặc exact expression khi biết chuỗi.
4. Dùng `setPathProvider` để hỗ trợ `~/` và chuẩn hóa đường dẫn tuyệt đối.
5. Giới hạn scanner trong thư mục `workspace/config` và bỏ qua thư mục build/cache.
6. Sau khi chọn, xác minh file tồn tại, đọc được, có đuôi `.yml` hoặc `.yaml` và nằm trong root được phép.
7. Nếu người dùng thoát mà không chọn, hiển thị thông báo và kết thúc command an toàn.
8. Thêm option `--file` để script/CI truyền đường dẫn trực tiếp mà không mở giao diện PathSearch.
9. Viết unit test cho path provider, scanner và validation; kiểm tra thêm trên terminal tương tác.

Sau bài thực hành, bạn cần giải thích được base path và search expression được kết hợp ra sao, fuzzy search khác exact search như thế nào, các giới hạn ảnh hưởng hiệu năng ra sao và vì sao phải xác minh `Path` sau khi người dùng chọn.

## 17. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Sử dụng component | Tạo và chạy `PathSearch` từ command Spring Shell 3.x |
| Kết quả | Đọc `Path` từ `PathSearchContext.getResultValue()` |
| Cấu hình | Điều chỉnh `maxPathsSearch`, `maxPathsShow` và tùy chọn search |
| Search syntax | Phân biệt fuzzy match và exact match |
| Path provider | Chuẩn hóa hoặc ánh xạ base path theo quy ước ứng dụng |
| Scanner | Biết khi nào cần custom path scanner |
| An toàn | Kiểm tra loại file, quyền và workspace root sau khi chọn |
| Hiệu năng | Giới hạn phạm vi và số candidate tìm kiếm |
| Automation | Cung cấp option đường dẫn cho script/non-interactive mode |
| Kiểm thử | Bao phủ kết quả, hủy, giới hạn và đường dẫn không hợp lệ |

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Path Search](https://docs.spring.io/spring-shell/reference/3.4/components/ui/pathsearch.html)
- [Spring Shell 3.4.3 — `PathSearch` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathSearch.html)
- [Spring Shell 3.4.3 — `PathSearchConfig` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathSearch.PathSearchConfig.html)
- [Spring Shell 3.4.3 — `PathSearchContext` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathSearch.PathSearchContext.html)
- [Spring Shell 3.4.3 — `PathScannerResult` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/PathSearch.PathScannerResult.html)
- [Spring Shell 3.4.3 — Search Algorithms](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/searchalgorithm.html)
- [Spring Shell 3.4.3 — `AbstractShellComponent` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/AbstractShellComponent.html)
