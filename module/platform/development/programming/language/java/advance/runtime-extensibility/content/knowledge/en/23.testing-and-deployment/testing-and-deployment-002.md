# Chạy ứng dụng từ JAR và module path thật trong tiến trình kiểm thử riêng

## 1. Mục tiêu của artifact integration test

Trong hệ thống Java plugin, kiểm thử bằng `target/classes`, `build/classes` hoặc classpath của IDE không phản ánh hoàn toàn sản phẩm phát hành. Một JAR phân phối có thể thiếu `module-info.class`, `META-INF/services`, dependency hoặc chứa package xung đột. Module resolution và `ServiceLoader` cũng có thể hoạt động khác khi chuyển từ classpath sang module path. Vì vậy cần build các JAR thực tế, sau đó dùng Java launcher trong **tiến trình con mới** với đúng `--module-path` mà production sử dụng.

Điều cần xác minh: artifact contents, module descriptors, root/provider resolution, startup, exit code, stdout/stderr, timeout, và các tình huống cố tình thiếu module/provider. Forked JVM giảm ảnh hưởng của static state và boot module layer của test runner; nó không mặc nhiên là security sandbox cho mã độc.

```text
Compile -> Package modular JARs -> dist/
                                   |
Test runner -- ProcessBuilder ---> java --module-path dist --module host/main
                                   |
                    exit code + stdout + stderr + timeout
                                   |
                         Assertions / diagnostics
```

## 2. Ví dụ Java 17+: API, provider và host modular

Cấu trúc thư mục:

```text
demo/
  src/
    demo.api/
      module-info.java
      demo/api/Greeter.java
    demo.provider/
      module-info.java
      demo/provider/EnglishGreeter.java
    demo.host/
      module-info.java
      demo/host/Main.java
  dist/
```

`src/demo.api/module-info.java`:

```java
module demo.api {
    exports demo.api;
}
```

`src/demo.api/demo/api/Greeter.java`:

```java
package demo.api;
public interface Greeter {
    String greet(String name);
}
```

`src/demo.provider/module-info.java`:

```java
module demo.provider {
    requires demo.api;
    provides demo.api.Greeter with demo.provider.EnglishGreeter;
}
```

`src/demo.provider/demo/provider/EnglishGreeter.java`:

```java
package demo.provider;
import demo.api.Greeter;
public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {}
    @Override public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`src/demo.host/module-info.java`:

```java
module demo.host {
    requires demo.api;
    uses demo.api.Greeter;
}
```

`src/demo.host/demo/host/Main.java`:

```java
package demo.host;
import demo.api.Greeter;
import java.util.List;
import java.util.ServiceLoader;
public final class Main {
    public static void main(String[] args) {
        List<Greeter> providers = ServiceLoader.load(Greeter.class)
                .stream().map(ServiceLoader.Provider::get).toList();
        if (providers.size() != 1) {
            System.err.println("Expected one Greeter, got "
                    + providers.size());
            System.exit(3);
        }
        System.out.println(providers.get(0).greet("Java"));
    }
}
```

Host chỉ `requires demo.api` và `uses demo.api.Greeter`; provider khai báo `provides` và không cần export implementation package cho SPI. Đây là test nhỏ nhưng bao gồm các rủi ro module descriptor, service binding và phân phối.

## 3. Build đúng modular JAR cuối cùng

Trong thư mục `demo`, chạy trên JDK 17+:

```bash
mkdir -p mods dist
javac --module-source-path src -d mods --module demo.api,demo.provider,demo.host
jar --create --file dist/demo.api.jar -C mods/demo.api .
jar --create --file dist/demo.provider.jar -C mods/demo.provider .
jar --create --file dist/demo.host.jar -C mods/demo.host .
java --module-path dist --add-modules demo.provider --module demo.host/demo.host.Main
```

Output của chương trình:

```text
Hello, Java
```

Chỉ ra thư mục `dist` trong module path: không sử dụng `mods` trong lệnh chạy cuối. `--add-modules demo.provider` buộc provider được resolve một cách tường minh; các cấu hình khác có thể sử dụng service binding, nhưng test này cố tình đảm bảo sự hiện diện của provider.

Kiểm tra descriptors sau đóng gói:

```bash
jar --describe-module --file dist/demo.api.jar
jar --describe-module --file dist/demo.provider.jar
jar --describe-module --file dist/demo.host.jar
```

Xác nhận `exports demo.api`, `provides demo.api.Greeter with demo.provider.EnglishGreeter`, `uses demo.api.Greeter` và `requires demo.api` xuất hiện ở đúng module. Việc biên dịch thành công từ source không đảm bảo tooling sau đó giữ nguyên `module-info.class`.

## 4. Fork JVM bằng ProcessBuilder

Đặt `ForkedModuleTest.java` ở thư mục `demo`, ngoài cấu trúc source modules:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class ForkedModuleTest {
    public static void main(String[] args) throws Exception {
        String java = Path.of(System.getProperty("java.home"),
                "bin", "java").toString();
        Path dist = Path.of("dist").toAbsolutePath();
        List<String> command = List.of(
                java, "--module-path", dist.toString(),
                "--add-modules", "demo.provider",
                "--module", "demo.host/demo.host.Main");

        Process p = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();
        boolean exited = p.waitFor(10, TimeUnit.SECONDS);
        if (!exited) {
            p.destroyForcibly();
            p.waitFor();
            throw new AssertionError("Forked JVM timed out");
        }
        String combined = new String(
                p.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        if (p.exitValue() != 0) {
            throw new AssertionError("Exit=" + p.exitValue()
                    + "; output=" + combined);
        }
        if (!combined.strip().equals("Hello, Java")) {
            throw new AssertionError("Unexpected output=" + combined);
        }
        System.out.println("Forked module test PASS");
    }
}
```

Chạy:

```bash
javac --release 17 ForkedModuleTest.java
java ForkedModuleTest
```

Output thành công:

```text
Forked module test PASS
```

**Giới hạn của ví dụ:** phương pháp `waitFor()` trước khi drain stdout/stderr chỉ an toàn khi output nhỏ và được kiểm soát. Nếu child ghi nhiều hơn pipe buffer, nó có thể block khi ghi và `waitFor` timeout dù chương trình không lỗi. Trong test harness production hãy drain stdout và stderr **đồng thời trong lúc process chạy** bằng reader threads hoặc redirect ra file giới hạn kích thước. Nếu test cần phân biệt stderr, đừng đặt `redirectErrorStream(true)`: thu riêng hai streams. Mọi fork phải có timeout và cleanup child process.

## 5. Kiểm thử âm tính: provider không tồn tại

Tạo folder chỉ có host và API JAR, không có provider:

```bash
mkdir -p dist-no-provider
cp dist/demo.api.jar dist-no-provider/
cp dist/demo.host.jar dist-no-provider/
java --module-path dist-no-provider --module demo.host/demo.host.Main
```

Trên shell Unix/macOS, host in vào stderr:

```text
Expected one Greeter, got 0
```

Exit code là `3` theo chương trình host. Trên Windows, dùng `Copy-Item` thay cho `cp`. Đây là **negative test chủ đích**: test phải assert đúng lỗi và không được xem nonzero exit là thành công thông thường.

Test thêm việc thiếu `demo.api.jar`: launcher sẽ báo lỗi module không tìm thấy, trước `main`. Vì exit code của launcher tùy môi trường/JDK, chỉ assert **nonzero** và message nhắc tới module thiếu, không hard-code một exit code tùy ý.

## 6. Những trường hợp packaging dễ hỏng

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| IDE thấy provider nhưng JAR không thấy | Service registration file bị mất/ghi đè | JAR entries, `provides` và module resolution |
| `FindException` lúc startup | Dependency không nằm trong module path | Descriptor, module path thực |
| `ResolutionException` | Graph có split package/readability conflict | JAR packages, module graph |
| `NoClassDefFoundError` ở runtime | Thiếu class phụ thuộc, dependency chỉ compile scope | Artifact dependencies và actual path |
| `ClassCastException` giữa host/plugin | API bị nạp hai classloader | API identity, parent delegation |
| Automatic module name bất ngờ | Non-modular JAR suy ra tên từ filename | `jar --describe-module` |
| Test pass nhưng production fail | Khác JDK/flags/OS/working dir | Ghi command, env, JDK version |

Test artifacts sau shading/relocation, không chỉ JAR trước transform. Nếu có `META-INF/services`, phải bảo toàn/merge đúng service descriptors; JPMS explicit module dựa trên `provides` trong `module-info.class`.

## 7. Kết nối với Maven/Gradle và CI

Trong Maven có thể chạy integration test sau `package` ở pha `verify`; Gradle có thể cấu hình task phụ thuộc `jar`/distribution và chạy `Exec` với module path xây từ outputs. Nguyên tắc quyết định không phụ thuộc công cụ:

1. Clean build tạo JAR mới và test dùng đúng file đó, không dùng stale artifact.
2. Chạy Java executable/version đúng target; nếu dùng toolchain, ghi rõ child JDK.
3. Không tự thêm classpath IDE vào child nếu production không sử dụng.
4. Ghi command, exit, stdout/stderr có redaction để debug.
5. Áp timeout, giới hạn output và dọn child process tree.
6. Có happy path và negative paths cho missing provider/module, split package, bad descriptor.

Đường dẫn module path trên Windows phân cách bởi `;`, Unix/macOS bởi `:`. Trường hợp chỉ trỏ đến một thư mục `dist`, không cần quan tâm separator. Trong `ProcessBuilder`, truyền từng argument thành phần tử riêng, tránh ghép thành một chuỗi shell gây lỗi quoting.

## 8. Quản lý tính tái lập và cô lập

Forked JVM cung cấp boot layer, static caches và system properties mới cho mỗi test. Nếu plugin sử dụng ports, file locks hoặc external services, test vẫn có thể ảnh hưởng nhau; cần fixture names riêng, tempfile directories và cleanup. Đừng giả định forked JVM là sandbox an toàn: chạy mã chưa tin cậy cần OS user/container với quyền hạn riêng.

Để giảm flakiness, điều khiển working directory, locale, timezone và encoding khi output có liên quan. Không assert message compiler/launcher nguyên văn trên nhiều JDK nếu mục tiêu là tương thích xuyên nền tảng; ưu tiên assert exception class, module name và exit status.

## 9. Checklist triển khai

- [ ] Test dùng chính JAR phát hành và `--module-path`, không dùng thư mục classes.
- [ ] Module descriptor sau packaging đúng `requires`, `exports`, `uses`, `provides`.
- [ ] Provider được resolve vào runtime graph một cách có chủ đích.
- [ ] Fork JVM mới với Java executable đúng JDK target.
- [ ] Assert exit code, stdout/stderr, timeout và dọn process.
- [ ] Với output lớn, drain streams song song khi process chạy.
- [ ] Có negative tests cho thiếu provider, dependency, split package.
- [ ] Build sạch, ghi chính xác command line và environment.
- [ ] Không nhầm process isolation với security sandbox.

**Kết luận:** kiểm thử bằng modular JAR thật trong một tiến trình riêng phát hiện lỗi đóng gói, module resolution và SPI discovery mà test trong IDE có thể bỏ sót. Chỉ coi bản phân phối sẵn sàng khi forked tests dùng đúng artifact và launcher thực tế đều đạt.
