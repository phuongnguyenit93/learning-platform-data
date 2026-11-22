# Dùng jdeps trong CI

## 1. jdeps là gì và vì sao đưa vào CI?

`jdeps` là công cụ phân tích dependency tĩnh đi kèm JDK. Nó đọc bytecode trong file class, thư mục class hoặc JAR để xác định class/package/module nào được tham chiếu. Kết quả giúp phát hiện dependency bị thiếu, phụ thuộc vào API nội bộ của JDK, xác định module cần thiết và tạo dependency graph.

Đưa `jdeps` vào Continuous Integration (CI) giúp kiểm tra artifact sau compile/package, trước khi phát hành:

- Phát hiện class được tham chiếu nhưng không có trên classpath hoặc module path.
- Phát hiện ứng dụng dùng JDK internal API như `sun.misc.Unsafe`.
- Kiểm tra dependency giữa các Java module.
- Xác định tập module cần cho custom runtime image bằng `jlink`.
- Tạo graph để review kiến trúc hoặc điều tra dependency mới xuất hiện.
- Theo dõi API dependency riêng biệt với dependency chỉ xuất hiện trong method body.

`jdeps` phân tích bytecode đã biên dịch. Nó không thay thế compiler, unit test, integration test, dependency vulnerability scanner hay runtime smoke test. Một build nên chạy `jdeps` sau khi đã tạo artifact và có đủ dependency để phân giải.

## 2. Điều kiện và xác định đúng JDK

`jdeps` nằm trong thư mục `bin` của JDK:

~~~bash
java --version
javac --version
jdeps --version
jdeps --help
~~~

Ví dụ trên JDK 24.0.2:

~~~text
24.0.2
~~~

Build agent phải cài JDK, không chỉ JRE. Kiểm tra `jdeps` được gọi từ cùng JDK/toolchain mà pipeline định dùng. Nếu CI có nhiều JDK, hãy in version trước khi phân tích để log build có thể truy nguyên.

Trên Windows PowerShell:

~~~powershell
Get-Command java, javac, jdeps | Select-Object Name, Source
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
command -v jdeps
echo "$JAVA_HOME"
~~~

Có thể gọi trực tiếp executable trong `JAVA_HOME/bin` để tránh dùng nhầm phiên bản từ PATH. Trên Windows, executable thường có phần mở rộng `.exe`.

## 3. Những loại input jdeps phân tích

`jdeps` nhận một hoặc nhiều đường dẫn:

- Một file `.class`.
- Một thư mục chứa class file.
- Một JAR.
- Một module hoặc đường dẫn module phù hợp với các option module analysis.

Ví dụ:

~~~bash
# Phân tích một JAR
jdeps app.jar

# Phân tích thư mục class
jdeps build/classes

# Phân tích một class
jdeps build/classes/com/example/Main.class

# Phân tích nhiều artifact
jdeps service.jar shared-library.jar
~~~

Trong CI, nên phân tích artifact cuối cùng hoặc output class chính của build. Nếu chỉ phân tích một source file chưa đóng gói, có thể bỏ sót dependency do build process tạo ra, generated class hoặc cấu hình packaging.

Với multi-module project, chạy phân tích trên từng JAR phát hành hoặc truyền nhiều artifact vào cùng lệnh. Ghi rõ module/path tương ứng để kết quả dễ đối chiếu với build graph.

## 4. Hiểu các dạng dependency output

Ví dụ output summary:

~~~text
app.jar -> java.base
app.jar -> java.sql
~~~

Nó cho biết JAR tham chiếu tới các package thuộc hai module JDK. Với dependency chưa phân giải được, output có thể chứa:

~~~text
app.jar -> not found
   com.example.app.Main -> com.example.lib.TextHelper not found
~~~

Một dependency line mô tả quan hệ giữa class/package nguồn và class/package đích. Kết quả có thể được hiển thị ở nhiều mức:

| Mức | Mục đích |
|---|---|
| Module | Xem module Java mà artifact phụ thuộc. |
| Package | Xem dependency giữa package. |
| Class | Xem chính xác class nào tham chiếu class nào. |
| Summary | Xem tổng hợp dependency của archive. |

Dependency analysis mặc định lọc một số quan hệ nội bộ trong package/archive. Nếu cần xem chi tiết hơn, chọn verbose mode hoặc filter phù hợp.

## 5. Cú pháp và các option quan trọng

Cú pháp tổng quát:

~~~bash
jdeps [options] <path ...>
~~~

Các option thường dùng trong CI:

| Option | Ý nghĩa |
|---|---|
| `-s` / `-summary` | Chỉ in dependency summary. |
| `-v` / `-verbose` | In dependency ở mức class. |
| `-verbose:package` | In dependency ở mức package. |
| `-verbose:class` | In dependency ở mức class. |
| `--missing-deps` | Tìm dependency không phân giải được. |
| `--jdk-internals` | Tìm tham chiếu tới JDK internal API. |
| `--class-path` | Cung cấp classpath để tìm dependency. |
| `--module-path` | Cung cấp module path. |
| `--list-deps` | Liệt kê module dependency. |
| `--list-reduced-deps` | Liệt kê module dependency sau khi loại các cạnh đọc được suy ra. |
| `--print-module-deps` | In danh sách module phân cách bằng dấu phẩy, dùng được với `jlink`. |
| `--check` | Kiểm tra descriptor và dependency graph của module. |
| `--api-only` | Chỉ phân tích dependency xuất hiện trong public/protected API. |
| `--dot-output` | Xuất dependency graph dạng DOT. |
| `--multi-release` | Chọn version cần phân tích trong multi-release JAR. |
| `--generate-module-info` | Sinh module descriptor gợi ý cho JAR chưa modular hóa. |

Trong JDK 24, summary option viết ngắn là `-s` hoặc `-summary`; không dùng `--summary`.

Có thể xem toàn bộ option của đúng JDK bằng:

~~~bash
jdeps --help
~~~

Tên option và khả năng hỗ trợ có thể khác giữa các phiên bản JDK. Pipeline nên kiểm tra version trước khi gọi option mới.

## 6. Phân tích dependency tổng quan

Chạy summary:

~~~bash
jdeps -s target/app.jar
~~~

Ví dụ:

~~~text
app.jar -> java.base
app.jar -> java.sql
~~~

Xem dependency ở mức package:

~~~bash
jdeps -verbose:package target/app.jar
~~~

Xem dependency ở mức class:

~~~bash
jdeps -verbose:class target/app.jar
~~~

Không lọc dependency nội bộ khi cần xem đầy đủ:

~~~bash
jdeps -v target/app.jar
~~~

Verbose output hữu ích khi một dependency module xuất hiện bất ngờ và cần xác định class nào tạo ra tham chiếu. Với artifact lớn, output class-level có thể rất dài; hãy lưu thành file report hoặc chỉ lọc package/class liên quan.

## 7. Cung cấp classpath và module path

`jdeps` cần biết nơi tìm các dependency ngoài JDK.

### Classpath

~~~bash
jdeps --missing-deps --class-path "lib/*" target/app.jar
~~~

Có thể truyền nhiều thư mục và JAR bằng classpath separator của hệ điều hành:

- Windows: dấu chấm phẩy `;`.
- Linux/macOS: dấu hai chấm `:`.

Ví dụ:

~~~bash
# Windows
jdeps --class-path "target/classes;lib/*" target/app.jar

# Linux/macOS
jdeps --class-path "target/classes:lib/*" target/app.jar
~~~

Classpath phải chứa các dependency runtime cần phân tích. Nếu thiếu một JAR hợp lệ, `jdeps` có thể báo `not found` dù ứng dụng vẫn build được ở một bước khác.

### Module path

Với ứng dụng modular:

~~~bash
jdeps --module-path "mods:lib" --module com.example.app --list-deps
~~~

`--module-path` chỉ định nơi tìm module; `--module` chọn root module cần phân tích. Không dùng classpath thay cho module path khi cần kiểm tra module descriptor và module graph.

## 8. Tìm dependency bị thiếu với --missing-deps

Đây là kiểm tra quan trọng trong CI:

~~~bash
jdeps --missing-deps --class-path "target/dependency/*" target/app.jar
~~~

Khi dependency đầy đủ, output thường không có dòng missing. Nếu thiếu dependency, ví dụ:

~~~text
app.jar -> not found
   com.example.app.Main -> com.example.lib.TextHelper not found
~~~

**Lưu ý quan trọng về exit code:** trong JDK 24.0.2, `jdeps --missing-deps` có thể trả về exit code 0 ngay cả khi đã in dependency `not found`. Vì vậy, chỉ kiểm tra `$LASTEXITCODE` hoặc trạng thái process là chưa đủ để làm CI gate. Phải kiểm tra nội dung output và chủ động trả về mã lỗi khi có finding.

Không dùng `--ignore-missing-deps` trong bước quality gate thông thường. Option đó cho phép tiếp tục phân tích khi thiếu dependency và có thể che khuất lỗi mà pipeline cần phát hiện.

Trước khi kết luận artifact sai, xác nhận classpath/module path có đầy đủ dependency đúng scope. Nếu dependency được nạp động bằng reflection hoặc service configuration, static analysis có thể không thấy mọi quan hệ runtime.

## 9. Phát hiện JDK internal API

Chạy:

~~~bash
jdeps --jdk-internals target/app.jar
~~~

Ví dụ khi bytecode tham chiếu `sun.misc.Unsafe`:

~~~text
internal-api.jar -> jdk.unsupported
   com.example.InternalApi -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
~~~

JDK internal API không phải contract công khai ổn định. Chúng có thể bị đóng, thay đổi hoặc loại bỏ giữa các phiên bản JDK, làm ứng dụng không tương thích sau khi nâng cấp.

`jdeps --jdk-internals` thường in cảnh báo và gợi ý API thay thế. Trên JDK 24.0.2, command vẫn có thể trả về exit code 0 khi tìm thấy internal API. CI cần đọc output để áp dụng policy:

- Fail build khi phát hiện internal API trong code của ứng dụng.
- Hoặc cho phép ngoại lệ có lý do và thời hạn xử lý rõ ràng.
- Phân tích riêng dependency bên thứ ba nếu muốn kiểm soát cả thư viện.
- Không tự động bỏ qua tất cả cảnh báo chỉ vì dependency do vendor cung cấp.

Nếu truyền classpath chứa nhiều thư viện vào `--jdk-internals`, công cụ có thể phân tích cả class trên classpath. Hãy xác định rõ muốn kiểm tra code của ứng dụng hay toàn bộ dependency tree trước khi chọn input.

## 10. Tách API dependency khỏi implementation dependency

`--api-only` chỉ xem dependency xuất hiện trong public/protected API của public class, ví dụ:

- Kiểu tham số của public method.
- Kiểu trả về.
- Kiểu field public/protected.
- Checked exception trong method signature.
- Kiểu xuất hiện trong API signature khác.

Chạy:

~~~bash
jdeps --api-only target/app.jar
~~~

So sánh với class-level analysis:

~~~bash
jdeps -v target/app.jar
~~~

Một thư viện có thể được dùng bên trong method body nhưng không xuất hiện trong public API. `--api-only` giúp phát hiện dependency bị lộ ra ngoài contract của thư viện, hữu ích khi thiết kế API hoặc chia module.

Không dùng kết quả API-only thay cho dependency analysis đầy đủ. Nó cố ý bỏ qua nhiều dependency implementation.

## 11. Phân tích module dependency và tạo jlink input

Liệt kê module dependency:

~~~bash
jdeps --list-deps --module-path mods --module com.example.app
~~~

In dependency graph đã rút gọn:

~~~bash
jdeps --list-reduced-deps --module-path mods --module com.example.app
~~~

In danh sách module phân cách bằng dấu phẩy:

~~~bash
jdeps --print-module-deps --module-path mods --module com.example.app
~~~

Ví dụ:

~~~text
java.base,java.sql
~~~

Danh sách này có thể dùng làm đầu vào cho `jlink` để tạo custom runtime image:

~~~bash
jlink --add-modules java.base,java.sql --output build/runtime-image
~~~

`--print-module-deps` giúp lấy module dependency đã giảm cạnh suy ra. Với custom runtime, vẫn cần kiểm tra module được load động, service provider và module cần bởi ứng dụng ở runtime. Danh sách static không phải lúc nào cũng bao phủ mọi module được nạp qua reflection hoặc plugin.

## 12. Kiểm tra module descriptor với --check

Với JAR có `module-info.class`, có thể kiểm tra descriptor:

~~~bash
jdeps --check com.example.app --module-path target/modular-app.jar
~~~

Output gồm:

- Module descriptor hiện tại.
- Dependency module được đề xuất sau phân tích.
- Transitive reduced graph.
- Các qualified export không được dùng nếu có.

`--check` giúp review module descriptor sau khi thay đổi source hoặc dependency. Nếu module path chứa nhiều module, truyền đầy đủ path để công cụ phân giải được graph.

Option này dành cho module name, không dùng để kiểm tra một JAR classpath thông thường không có module descriptor.

## 13. Sinh module-info.java cho JAR chưa modular hóa

Với một JAR chưa có module descriptor:

~~~bash
jdeps --generate-module-info build/module-info target/library.jar
~~~

Công cụ tạo file `module-info.java` gợi ý trong thư mục đích. Ví dụ:

~~~java
module text.helper {
    exports com.example.lib;
}
~~~

Descriptor được sinh ra chỉ là điểm bắt đầu. Cần review:

- Tên module.
- Các package cần export.
- `requires` và `requires transitive`.
- Qualified exports.
- Reflection và service loading.
- Package split hoặc dependency không thể biểu diễn trực tiếp.

Không đưa descriptor do `jdeps` sinh thẳng vào production mà chưa review và compile thử. Với open module, công cụ có option `--generate-open-module`.

## 14. Xuất dependency graph để lưu làm CI artifact

Tạo DOT output:

~~~bash
jdeps --dot-output build/reports/jdeps --class-path "target/dependency/*" target/app.jar
~~~

Thư mục output có thể chứa:

~~~text
build/reports/jdeps/
├── app.jar.dot
└── summary.dot
~~~

Có thể lưu file DOT làm artifact của pipeline để reviewer mở bằng Graphviz hoặc công cụ hiển thị Mermaid/graph khác. Graph giúp nhận ra dependency mới, package coupling và module graph phức tạp.

Khi build nhiều JAR, tạo output directory riêng cho mỗi lần chạy hoặc clean report cũ trước khi ghi để tránh trộn graph từ artifact khác.

## 15. Multi-release JAR

Multi-release JAR có thể chứa class khác nhau cho các Java release trong cùng một archive. Dùng `--multi-release` để chọn version cần phân tích:

~~~bash
jdeps --multi-release 17 --list-deps target/multi-release-library.jar
~~~

Giá trị có thể là một số nguyên từ 9 trở lên hoặc `base`. Chọn đúng release mà ứng dụng production thực sự chạy. Nếu chỉ phân tích base version, có thể bỏ sót dependency trong class được đặt dưới `META-INF/versions/N`.

Không dùng `--multi-release 17` cho JAR thông thường không có multi-release layout. Trước tiên xác nhận manifest có `Multi-Release: true` và JAR chứa versioned class phù hợp.

## 16. Bộ lọc và phân tích dependency chuyên sâu

Một số option lọc hữu ích:

| Option | Công dụng |
|---|---|
| `--package` | Chỉ tìm dependency của package được chỉ định. |
| `--regex` | Lọc dependency bằng regular expression. |
| `--require` | Lọc theo module dependency. |
| `-include` | Giới hạn class được đưa vào phân tích. |
| `-filter:package` | Lọc dependency trong cùng package. |
| `-filter:archive` | Lọc dependency trong cùng archive. |
| `-filter:module` | Lọc dependency trong cùng module. |
| `-filter:none` | Không lọc dependency nội bộ theo package/archive mặc định. |
| `--recursive` | Duyệt dependency runtime theo cách đệ quy. |
| `--no-recursive` | Không duyệt dependency đệ quy. |
| `--inverse` | Tìm các artifact phụ thuộc trực tiếp/gián tiếp vào node được chọn. |

Ví dụ tìm dependency liên quan package:

~~~bash
jdeps --package com.example.lib -v target/app.jar
~~~

Tìm artifact phụ thuộc vào một module:

~~~bash
jdeps --inverse --require java.sql target/*.jar
~~~

Các bộ lọc `--package`, `--regex` và `--require` là lựa chọn loại trừ lẫn nhau trong một lần gọi. `--inverse` phải dùng với một trong các filter phù hợp. Hãy xem `jdeps --help` trước khi ghép option phức tạp.

## 17. Tạo Java 17 fixture để thực hành

Một dependency library:

`libsrc/com/example/lib/TextHelper.java`:

~~~java
package com.example.lib;

public final class TextHelper {
    private TextHelper() {
    }

    public static String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase();
    }
}
~~~

Ứng dụng sử dụng thư viện và JDBC API:

`appsrc/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.lib.TextHelper;
import java.sql.Connection;
import java.sql.DriverManager;

public class Main {
    public static void main(String[] args) throws Exception {
        String value = TextHelper.normalize(" CI ");
        System.out.println("jdeps CI ready: " + value);

        try (Connection ignored =
                 DriverManager.getConnection("jdbc:invalid:")) {
            System.out.println(ignored);
        } catch (java.sql.SQLException expected) {
            System.out.println("JDBC module resolved");
        }
    }
}
~~~

Biên dịch thư viện và đóng gói:

~~~bash
javac --release 17 -d build/lib libsrc/com/example/lib/TextHelper.java
jar --create --file lib/text-helper.jar -C build/lib .
~~~

Biên dịch ứng dụng với dependency:

~~~bash
javac --release 17 -cp lib/text-helper.jar -d build/app appsrc/com/example/app/Main.java
jar --create --file dist/app.jar --main-class com.example.app.Main -C build/app .
~~~

Chạy trên Windows:

~~~powershell
java -cp "dist/app.jar;lib/text-helper.jar" com.example.app.Main
~~~

Trên Linux/macOS:

~~~bash
java -cp "dist/app.jar:lib/text-helper.jar" com.example.app.Main
~~~

Stdout chính xác:

~~~text
jdeps CI ready: ci
JDBC module resolved
~~~

## 18. Kiểm tra dependency trên fixture

Liệt kê module:

~~~bash
jdeps --list-deps --class-path lib/text-helper.jar dist/app.jar
~~~

Output:

~~~text
java.base
java.sql
~~~

In danh sách module:

~~~bash
jdeps --print-module-deps --class-path lib/text-helper.jar dist/app.jar
~~~

Output:

~~~text
java.base,java.sql
~~~

Tìm dependency thiếu khi không truyền JAR thư viện:

~~~bash
jdeps --missing-deps dist/app.jar
~~~

Output có dòng:

~~~text
app.jar -> not found
com.example.app.Main -> com.example.lib.TextHelper not found
~~~

Thêm dependency vào classpath:

~~~bash
jdeps --missing-deps --class-path lib/text-helper.jar dist/app.jar
~~~

Không còn output missing. Trong lần chạy kiểm chứng trên JDK 24.0.2, lệnh này và lệnh missing đều trả exit code 0; khác biệt nằm ở output. Đây là lý do CI cần parse finding thay vì chỉ nhìn exit code.

Tạo graph:

~~~bash
jdeps --dot-output build/reports/jdeps --class-path lib/text-helper.jar dist/app.jar
~~~

Kiểm tra file `app.jar.dot` và `summary.dot` được tạo trong thư mục report.

## 19. Ví dụ kiểm tra module descriptor

Tạo source module:

`modulesrc/com.example.modapp/module-info.java`:

~~~java
module com.example.modapp {
    requires java.sql;
}
~~~

`modulesrc/com.example.modapp/com/example/modapp/Main.java`:

~~~java
package com.example.modapp;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class Main {
    public static void main(String[] args) {
        try (Connection ignored =
                 DriverManager.getConnection("jdbc:invalid:")) {
            System.out.println(ignored);
        } catch (SQLException expected) {
            System.out.println("module dependency ready");
        }
    }
}
~~~

Biên dịch và đóng gói module:

~~~bash
javac --release 17 --module-source-path modulesrc -d build/mods -m com.example.modapp
jar --create --file dist/modapp.jar --main-class com.example.modapp.Main -C build/mods/com.example.modapp .
~~~

Kiểm tra:

~~~bash
jdeps --check com.example.modapp --module-path dist/modapp.jar
jdeps --list-deps --module-path dist/modapp.jar --module com.example.modapp
~~~

Kết quả đã kiểm chứng trên JDK 24.0.2 cho thấy descriptor yêu cầu `java.base` và `java.sql`; danh sách module cũng gồm đúng hai module đó.

## 20. Tạo CI gate bằng PowerShell

Vì `jdeps` có thể trả exit code 0 dù output chứa finding, script cần kiểm tra cả process exit code và nội dung kết quả.

Ví dụ `scripts/check-jdeps.ps1`:

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,

    [string]$ClassPath = ""
)

$ErrorActionPreference = "Stop"

$missingArgs = @("--missing-deps")
if ($ClassPath) {
    $missingArgs += @("--class-path", $ClassPath)
}
$missingArgs += $Artifact

$missingOutput = & jdeps @missingArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "jdeps --missing-deps failed: $LASTEXITCODE"
}

$missingText = $missingOutput -join [Environment]::NewLine
if ($missingText -match "\bnot found\b") {
    Write-Error ("Missing bytecode dependencies:" +
        [Environment]::NewLine + $missingText)
    exit 1
}

$internalOutput = & jdeps --jdk-internals $Artifact 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "jdeps --jdk-internals failed: $LASTEXITCODE"
}

$internalText = $internalOutput -join [Environment]::NewLine
if ($internalText -match "JDK internal API") {
    Write-Error ("JDK internal API usage detected:" +
        [Environment]::NewLine + $internalText)
    exit 1
}

Write-Host "jdeps checks passed: $Artifact"
~~~

Chạy:

~~~powershell
.\scripts\check-jdeps.ps1 -Artifact target/app.jar -ClassPath (Get-Content target/runtime-classpath.txt -Raw)
~~~

Script này áp dụng policy fail khi có missing dependency hoặc JDK internal API. Nếu tổ chức cho phép một ngoại lệ, hãy tạo allowlist có owner, lý do và thời hạn; đừng xóa bước kiểm tra.

Trong thử nghiệm JDK 24.0.2:

- Artifact có đủ `text-helper.jar`: script in `jdeps checks passed` và exit code 0.
- Thiếu `text-helper.jar`: script in missing class và exit code 1.
- Artifact tham chiếu `sun.misc.Unsafe`: script phát hiện `JDK internal API` và exit code 1.

## 21. Tích hợp vào Gradle

Có thể tạo task chạy sau khi JAR được đóng gói:

~~~groovy
tasks.register('jdepsCheck') {
    dependsOn tasks.jar

    doLast {
        def exeName = System.getProperty('os.name')
            .toLowerCase().contains('windows') ? 'jdeps.exe' : 'jdeps'
        def jdepsExe = new File(
            System.getProperty('java.home'), "bin/" + exeName
        )
        def artifact = tasks.jar.archiveFile.get().asFile

        def runJdeps = { List<String> command ->
            def process = new ProcessBuilder(command)
                .redirectErrorStream(true).start()
            def output = process.inputStream.getText('UTF-8')
            def exitCode = process.waitFor()
            if (exitCode != 0) {
                throw new GradleException(
                    "jdeps exited " + exitCode + ":\n" + output
                )
            }
            return output
        }

        def missingOutput = runJdeps([
            jdepsExe.absolutePath,
            '--missing-deps',
            '--class-path',
            configurations.runtimeClasspath.asPath,
            artifact.absolutePath
        ])

        if (missingOutput.contains('not found')) {
            throw new GradleException(
                "Missing dependencies detected:\n" + missingOutput
            )
        }

        def internalOutput = runJdeps([
            jdepsExe.absolutePath,
            '--jdk-internals',
            artifact.absolutePath
        ])

        if (internalOutput.contains('JDK internal API')) {
            throw new GradleException(
                "JDK internal API usage detected:\n" + internalOutput
            )
        }

        logger.lifecycle("jdeps checks passed for " + artifact.name)
    }
}
~~~

Chạy:

~~~bash
gradle clean jdepsCheck
~~~

Task lấy classpath từ `runtimeClasspath`, kiểm tra missing dependency và internal API riêng biệt, sau đó làm build thất bại khi có finding. Trong project dùng Java toolchain khác JDK của Gradle daemon, hãy lấy executable `jdeps` từ đúng toolchain thay vì mặc định `java.home` của daemon.

Task này đã được kiểm chứng với Gradle 9.2.1 trên JDK 24.0.2: `clean jdepsCheck` build JAR, chạy hai phép phân tích và kết thúc `BUILD SUCCESSFUL` với fixture hợp lệ.

## 22. Tích hợp vào Maven và GitHub Actions

Maven có thể tạo runtime classpath bằng Dependency Plugin:

~~~bash
mvn -B clean package
mvn -B dependency:build-classpath -Dmdep.outputFile=target/runtime-classpath.txt
~~~

Sau đó chạy script kiểm tra trên JAR:

~~~powershell
.\scripts\check-jdeps.ps1 -Artifact target/app.jar -ClassPath (Get-Content target/runtime-classpath.txt -Raw)
~~~

Ví dụ GitHub Actions với Maven trên Linux:

~~~yaml
name: Java dependency analysis

on:
  pull_request:
  push:

jobs:
  jdeps:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build
        run: mvn -B clean package

      - name: Resolve runtime classpath
        run: mvn -B dependency:build-classpath -Dmdep.outputFile=target/runtime-classpath.txt

      - name: Check missing dependencies
        shell: bash
        run: |
          classpath="$(cat target/runtime-classpath.txt)"
          output="$(jdeps --missing-deps --class-path "$classpath" target/app.jar 2>&1)"
          printf '%s\n' "$output"
          if printf '%s\n' "$output" | grep -q 'not found'; then
            echo "Missing bytecode dependency detected"
            exit 1
          fi

      - name: Check JDK internal APIs
        shell: bash
        run: |
          output="$(jdeps --jdk-internals target/app.jar 2>&1)"
          printf '%s\n' "$output"
          if printf '%s\n' "$output" | grep -q 'JDK internal API'; then
            echo "JDK internal API usage detected"
            exit 1
          fi
~~~

Thay `target/app.jar` bằng artifact thực tế của dự án. Nếu build nhiều module, lặp qua các JAR cần phát hành hoặc tạo task cho từng module. Nếu dùng Gradle, gọi `gradle jdepsCheck` trong workflow sau bước build.

Pin JDK và build tool trong CI để output phân tích có thể so sánh giữa các lần chạy. Khi nâng JDK, review thay đổi dependency graph và cảnh báo internal API.

## 23. Giới hạn của static dependency analysis

`jdeps` đọc tham chiếu trong bytecode. Nó có thể không nhận diện đầy đủ:

- Class name được tạo động bằng reflection.
- Class được nạp từ plugin hoặc custom class loader.
- Service provider được chọn theo runtime configuration.
- Dependency ẩn trong script, JNI hoặc native library.
- Resource/configuration chỉ được nạp khi chạy.
- Dependency chỉ xuất hiện trên một code path chưa được phân tích đầy đủ.

Vì vậy, một kết quả `jdeps` sạch không chứng minh ứng dụng sẽ chạy thành công trong mọi môi trường. Kết hợp với test, startup smoke test, service checks và runtime observability.

Ngược lại, một finding `not found` có thể xuất hiện khi classpath truyền vào không đầy đủ hoặc dependency được phân phối theo cách riêng. Xác nhận packaging và runtime dependency trước khi sửa source.

`jdeps` cũng không đánh giá lỗ hổng bảo mật, license, phiên bản dependency hoặc chất lượng API. Dùng công cụ SCA/vulnerability scanning riêng cho các mục tiêu đó.

## 24. Lỗi thường gặp khi dùng jdeps trong CI

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `jdeps is not recognized` | Build agent chỉ cài JRE hoặc PATH sai. | Cài JDK và gọi đúng `JAVA_HOME/bin/jdeps`. |
| Dependency hiện `not found` | Classpath/module path thiếu JAR hoặc output. | Truyền runtime classpath/module path đầy đủ. |
| Finding nhưng CI vẫn pass | Chỉ kiểm tra exit code của jdeps. | Parse output và tự exit 1 khi có `not found` hoặc internal API. |
| Quá nhiều internal API warning | Phân tích cả dependency bên thứ ba. | Giới hạn input/`-include` hoặc đặt policy cho code nội bộ và thư viện riêng. |
| Không tìm thấy module | Dùng classpath thay module path hoặc thiếu root module. | Dùng `--module-path` và `--module` đúng cách. |
| `--check` báo module không tồn tại | Module path thiếu JAR hoặc tên module sai. | Kiểm tra module descriptor và module name. |
| Graph DOT rỗng hoặc thiếu file | Input hoặc output path không đúng. | Xác nhận artifact, quyền ghi và `--dot-output`. |
| JAR đa phiên bản cho kết quả khác | Chưa chọn release cần phân tích. | Dùng `--multi-release` phù hợp. |
| API-only không thấy dependency | Dependency chỉ nằm trong method body. | Dùng full dependency analysis thay cho `--api-only`. |
| Dependency runtime vẫn thiếu dù jdeps pass | Reflection, plugin, service loader hoặc native dependency. | Bổ sung integration/smoke test và runtime configuration check. |
| Pipeline khác máy cho output khác | JDK version hoặc dependency resolution khác. | Pin toolchain, dependency version và build image. |

## 25. Checklist triển khai jdeps trong CI

- Build agent có JDK và gọi đúng `jdeps`.
- Đã ghi lại JDK/toolchain version.
- Phân tích artifact sau compile/package.
- `--class-path` hoặc `--module-path` chứa dependency đúng scope.
- Có bước `--missing-deps` và kiểm tra output `not found`.
- Có policy cho `--jdk-internals`.
- Không nhầm exit code 0 với việc không có finding.
- Với modular JAR, kiểm tra `--check` và `--list-deps`.
- Với custom runtime, review `--print-module-deps` trước khi dùng `jlink`.
- Lưu DOT output nếu dependency graph cần review.
- Chọn đúng version cho multi-release JAR.
- Chạy test/smoke test để kiểm tra dependency động.
- Pin JDK, plugin và build tool trong CI.
- Xem lại finding mới trước khi merge hoặc release.

## 26. Tài liệu tham khảo

- [The jdeps Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [The jlink Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [Java Platform Module System — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/package-summary.html)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)

`jdeps` là một bước kiểm tra dependency tĩnh hữu ích trước khi phát hành Java artifact. Hãy cung cấp đúng classpath/module path, kiểm tra output missing và JDK internal API, rồi lưu dependency graph khi cần review kiến trúc. Vì các finding có thể không làm process trả mã lỗi khác 0, CI phải chủ động biến finding thành trạng thái thất bại và kết hợp phân tích tĩnh với test runtime.
