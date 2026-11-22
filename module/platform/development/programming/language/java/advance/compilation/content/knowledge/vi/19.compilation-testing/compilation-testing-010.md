# Bài thực hành: từ cấu hình `javac` đến kiểm chứng tự động bản build

> **Phạm vi:** Java Advance – compilation → Kiểm thử biên dịch. Bài lab hướng dẫn xây một dự án Java nhỏ bằng **`javac` thuần**, kiểm thử đầu ra chạy thật, kiểm tra lỗi biên dịch bằng **Java Compiler API**, so sánh **bytecode/JAR** giữa hai lượt build và nối toàn bộ quy trình vào CI. Mọi ví dụ Java sử dụng cú pháp/API Java 17; cần **JDK 17 trở lên** để chạy.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Chọn compiler và cố định `--release`, encoding, annotation processing, classpath và output directory.
2. Tạo **positive fixture** chạy đúng và **negative fixture** cố ý sai kiểu; không nhầm “biên dịch lỗi” với “test thành công”.
3. Tự động xác minh **class-file major version 61** (Java 17), kết quả chạy, loại/vị trí diagnostic.
4. Biên dịch hai lần ra **hai thư mục độc lập** để đối chiếu byte của `.class`.
5. Đóng gói một JAR thử nghiệm với metadata cố định, so sánh nội dung JAR theo byte và nêu đúng giới hạn của phép kiểm chứng.
6. Chạy toàn bộ trong một script và đưa vào CI; một điều kiện sai làm job thất bại.

**Tiêu chí nghiệm thu:** lệnh chạy kiểm thử xuất ra `BUILD AUDIT: PASS` với exit code `0`; sửa source để vi phạm một giả định thì script phải dừng hoặc báo `AssertionError`. Chỉ khi kiểm tra được cả hai chiều pass/fail mới tin được bài kiểm thử.

### 1.1. Vì sao phải kiểm chứng cả build lẫn hành vi?

`javac` trả mã thoát `0` nghĩa là biên dịch thành công, nhưng chưa chứng minh rằng lớp Java có đúng bytecode target, in đúng stdout hoặc JAR tái lập. Ngược lại, một source cố ý không hợp lệ phải biên dịch lỗi **đúng nguyên nhân**. Ta dùng nhiều lớp kiểm chứng vì không có phép đo đơn lẻ nào bao phủ tất cả.

```text
Nguồn / phiên bản JDK / cấu hình
                 │
         javac --release 17
                 │
        ┌────────┴─────────┐
        ▼                  ▼
   build/a/classes    build/b/classes
        │                  │
        └───── byte equality ─────┐
                                  │
          chạy demo.Hello ────────┤
                                  ├─► BuildAudit ─► PASS / FAIL
         class version = 61 ──────┤
                                  │
       JAR cố định metadata ───────┤
                                  │
       negative compile ERROR ────┘
```

Đây là **bài kiểm chứng cục bộ**: hai build cùng JDK trên một máy đạt cùng byte là bằng chứng tốt cho fixture nhỏ. Tính tái lập độc lập trên máy khác còn đòi hỏi pin compiler, dependency và mọi generator.

## 2. Chuẩn bị môi trường

Cần một **JDK đầy đủ**, có các lệnh `java`, `javac` và module `jdk.compiler`; không chỉ có Java runtime tối giản. Kiểm tra:

```bash
java -version
javac -version
```

Lệnh in ra phiên bản thực tế của máy, **không có stdout cố định** trong bài. Hãy bảo đảm `java` và `javac` cùng toolchain dự định; IDE, shell và CI có thể chọn JDK khác nhau.

Trong lab dùng:

- `--release 17`: hạn chế ngôn ngữ, class-file target và Java platform API theo Java 17.
- `-encoding UTF-8`: giải thích byte file `.java` đúng charset.
- `-proc:none`: tắt annotation processors để không có codegen bất ngờ; phù hợp vì bài không dùng processor.
- `-Xlint:all`: bật các nhóm cảnh báo của `javac` cho positive source. Nếu cần chính sách “warning là lỗi”, có thể thêm `-Werror` sau khi kiểm tra fixture.
- `-d <dir>`: tách class files khỏi source và giữa các lượt build.

**Giới hạn quan trọng:** `--release 17` **không đảm bảo** hai compiler JDK 17/21/24 sẽ luôn sinh byte giống nhau; nó cố định mức tương thích ngôn ngữ/API, không pin implementation/patch của compiler. Đối với build phát hành, pin cả distribution/vendor/patch JDK và build tool.

## 3. Tạo project tối giản

Cấu trúc cần tạo bằng tay:

```text
javac-build-lab/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── Hello.java
│   └── test/
│       ├── java/
│       │   └── BuildAudit.java
│       └── fixtures/
│           └── demo/
│               └── BadHello.java
├── verify.sh
└── build/                         # Sinh ra khi chạy, không commit
```

Tất cả file `.java` được lưu **UTF-8 không BOM**. File `BuildAudit.java` đặt ở default package cho dễ chạy bài lab; trong ứng dụng thực tế, nên dùng package rõ ràng cho mã test. `build/` là thư mục output, không phải source of truth.

### 3.1. Positive source

Tạo **`src/main/java/demo/Hello.java`**:

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        // Dòng bình luận có dấu: tiếng Việt, cà phê.
        System.out.println("Hello from Java 17");
    }
}
```

Chuỗi stdout cố ý dùng ASCII để dễ đối chiếu trên Windows, Linux và CI; comment có tiếng Việt buộc việc lưu/đọc source đúng UTF-8. Source có package `demo`, vì vậy class output phải là `demo/Hello.class` bên dưới `-d`.

### 3.2. Negative source: lỗi có chủ đích

Tạo **`src/test/fixtures/demo/BadHello.java`**:

```java
package demo;
public class BadHello {
    public static void main(String[] args) {
        int count = "not a number";
    }
}
```

Dòng 4 gán `String` cho `int` nên phải bị `javac` từ chối. Bài test không khẳng định nguyên văn thông báo lỗi (điều này có thể đổi theo compiler và locale), mà kiểm tra `Diagnostic.Kind.ERROR` ở dòng 4, cột có giá trị và đúng source.

**Không** đặt `BadHello.java` trong `src/main/java`: nếu compile toàn bộ source thông thường thì negative fixture sẽ phá hỏng cả positive build, khiến bài lab không phân biệt được hai nhánh.

## 4. Chạy `javac` thủ công và hiểu từng cờ

Từ thư mục gốc `javac-build-lab/`, trong Bash:

```bash
mkdir -p build/a/classes build/b/classes
javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/a/classes src/main/java/demo/Hello.java

java -cp build/a/classes demo.Hello
```

**Stdout của lệnh `java`:**

```text
Hello from Java 17
```

Nếu thành công, `javac` thường không in nội dung và trả exit code `0`. Khi source bị lỗi, `javac` thông thường in diagnostics ra stderr và trả exit code khác `0`. Không viết script dựa vào việc grep nguyên văn stderr nếu có thể dựa vào exit code và Compiler API.

Tạo output độc lập lần hai:

```bash
javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/b/classes src/main/java/demo/Hello.java
```

Hai lần biên dịch **không dùng chung output directory**; như vậy một lượt không vô tình đọc class còn sót của lượt khác. Trong lab chỉ có một source, dễ xác định toàn bộ inputs. Dự án lớn cần clean output, xử lý generated sources và classpath đầy đủ.

### 4.1. Nhìn cấu trúc bytecode

Có thể xác minh class-file major version qua công cụ chuẩn:

```bash
javap -verbose -classpath build/a/classes demo.Hello
```

Trong output dài sẽ có dòng:

```text
major version: 61
```

Class-file major **61** tương ứng Java 17. Nếu dùng `--release 21`, target thành major 65. Kiểm tra major version không đủ để xác minh toàn bộ semantics/API mà chương trình sử dụng; `--release` và chạy test là lớp kiểm chứng bổ sung.

### 4.2. Vì sao chưa đóng gói `jar` ngay?

JAR là ZIP archive: thời gian của entries, thứ tự entries, manifest và thông tin đóng gói có thể làm **SHA-256 JAR khác** dù `.class` có byte giống nhau. Thay vì dựa vào timestamp hệ thống, ở bước sau ta tạo **một JAR chỉ chứa một class** và cố định timestamp của entry bằng API Java 17.

Trên những JDK mới, tool `jar` hỗ trợ `--date=TIMESTAMP`, nhưng **không nên giả định cờ này có trên JDK 17**. Vì bài lab yêu cầu chạy từ JDK 17, cách đóng gói bằng `JarOutputStream` sẽ khả dụng nhất quán.

## 5. Viết bộ kiểm chứng tự động `BuildAudit`

Tạo **`src/test/java/BuildAudit.java`** sau đây. Đây là **chương trình Java độc lập đầy đủ** chạy từ thư mục gốc project sau khi positive source đã được biên dịch ở `build/a/classes` và `build/b/classes`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class BuildAudit {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void packageClass(Path classes, Path jar)
            throws IOException {
        try (JarOutputStream output =
                 new JarOutputStream(Files.newOutputStream(jar))) {
            JarEntry entry = new JarEntry("demo/Hello.class");
            entry.setTime(1704067200000L); // 2024-01-01 UTC
            output.putNextEntry(entry);
            Files.copy(classes.resolve("demo/Hello.class"), output);
            output.closeEntry();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] firstClass = Files.readAllBytes(
                Path.of("build/a/classes/demo/Hello.class"));
        byte[] secondClass = Files.readAllBytes(
                Path.of("build/b/classes/demo/Hello.class"));
        require(Arrays.equals(firstClass, secondClass),
                "Class files differ");
        int major = ((firstClass[6] & 0xff) << 8)
                | (firstClass[7] & 0xff);
        require(major == 61, "Expected Java 17 class-file version 61");

        packageClass(Path.of("build/a/classes"), Path.of("build/a/app.jar"));
        packageClass(Path.of("build/b/classes"), Path.of("build/b/app.jar"));
        byte[] firstJar = Files.readAllBytes(Path.of("build/a/app.jar"));
        byte[] secondJar = Files.readAllBytes(Path.of("build/b/app.jar"));
        require(Arrays.equals(firstJar, secondJar), "JAR files differ");

        String javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java").toString();
        Process process = new ProcessBuilder(
                javaExecutable, "-cp", "build/a/classes", "demo.Hello")
                .redirectErrorStream(true)
                .start();
        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();
        int exit = process.waitFor();
        require(exit == 0, "Application exited with " + exit);
        require(output.equals("Hello from Java 17"),
                "Unexpected stdout: " + output);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        require(compiler != null, "System Java compiler is unavailable");
        Files.createDirectories(Path.of("build/negative/classes"));
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean compiled;
        try (StandardJavaFileManager fileManager =
                 compiler.getStandardFileManager(
                         null, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> files =
                    fileManager.getJavaFileObjectsFromPaths(
                            List.of(Path.of(
                                    "src/test/fixtures/demo/BadHello.java")));
            compiled = Boolean.TRUE.equals(compiler.getTask(
                    null, fileManager, diagnostics,
                    List.of("--release", "17", "-encoding", "UTF-8",
                            "-proc:none", "-d", "build/negative/classes"),
                    null, files).call());
        }

        require(!compiled, "Invalid source unexpectedly compiled");
        boolean expectedError = diagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR
                        && d.getLineNumber() == 4
                        && d.getColumnNumber() > 0
                        && d.getSource() != null
                        && d.getSource().toUri().getPath()
                                .endsWith("/BadHello.java"));
        require(expectedError, "Expected ERROR at BadHello.java:4");

        System.out.println("Class bytes: MATCH");
        System.out.println("Java 17 class version: 61");
        System.out.println("JAR bytes: MATCH");
        System.out.println("Application stdout: PASS");
        System.out.println("Negative compilation diagnostic: PASS");
        System.out.println("BUILD AUDIT: PASS");
    }
}
```

**Giải thích những phép kiểm tra chính:**

- `Arrays.equals(firstClass, secondClass)` so sánh từng byte của hai file `.class`, không chỉ tên hoặc kích thước file. `major` đọc hai byte ở offset 6–7 của header class file, thứ tự big-endian; class format bắt đầu bằng magic `CAFEBABE`. Trong fixture này bytecode cần tương thích Java 17.
- `packageClass` tạo JAR với một `JarEntry` cố định, tên `demo/Hello.class` và timestamp `1704067200000L` (2024-01-01T00:00:00Z), không thêm manifest động. Cùng một byte input và JAR packer trong cùng môi trường, nội dung JAR phải giống nhau.
- `ProcessBuilder` chạy ứng dụng **thật** bằng executable `java` của JDK hiện tại; kiểm tra exit code `0` và stdout chính xác. Mã ví dụ in ASCII để tránh sai khác giữa charset console và pipe trên một số hệ thống.
- `ToolProvider.getSystemJavaCompiler()` lấy compiler nội bộ. `DiagnosticCollector` giữ lỗi của **negative fixture** thay vì parse stderr. Điều kiện `!compiled` cộng với `ERROR` tại `BadHello.java:4` ngăn trường hợp “biên dịch thất bại vì lỗi setup nhưng test vẫn pass”.
- `getSource()` có thể là `null` và `getLineNumber()/getColumnNumber()` có thể trả `Diagnostic.NOPOS` cho lỗi không gắn vị trí. Vì thế chỉ so sánh vị trí sau khi lọc kind/source và kiểm tra cột dương.
- `require(...)` ném `AssertionError` khi phát hiện sai; Java process sẽ kết thúc khác `0`, khiến script CI fail. Một vài dòng `println` **không thay thế** assertions.
- `StandardJavaFileManager` được đóng sau lượt compile. Negative fixture có thư mục output riêng và không chạy annotation processors.

Trong ứng dụng lớn, so sánh toàn bộ danh sách `.class`/resources bằng thứ tự chuẩn hóa và hash của mỗi file, không chỉ một class như bài lab.

### 5.1. Compile và chạy bộ kiểm chứng

```bash
mkdir -p build/tools
javac --release 17 -encoding UTF-8 -proc:none \
  -d build/tools src/test/java/BuildAudit.java

java -cp build/tools BuildAudit
```

**Stdout chính xác khi dự án và môi trường được thiết lập đúng:**

```text
Class bytes: MATCH
Java 17 class version: 61
JAR bytes: MATCH
Application stdout: PASS
Negative compilation diagnostic: PASS
BUILD AUDIT: PASS
```

Ví dụ đã được chạy và nhận đúng sáu dòng trên với OpenJDK 24.0.2, compiler target Java 17. Khi assertion thất bại, lỗi được in qua stack trace và exit code khác `0`; đừng đọc chữ `PASS` từ một build trước đó hoặc bỏ qua exit code.

## 6. Tự động hóa toàn bộ bằng `verify.sh`

Tạo **`verify.sh`** ở thư mục gốc; script này biên dịch mới hai bộ class, biên dịch `BuildAudit` và chạy test. Nó dùng Bash (Linux/macOS hoặc môi trường có Bash):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p build/a/classes build/b/classes build/tools

javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/a/classes src/main/java/demo/Hello.java

javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/b/classes src/main/java/demo/Hello.java

javac --release 17 -encoding UTF-8 -proc:none \
  -d build/tools src/test/java/BuildAudit.java

java -cp build/tools BuildAudit
```

Chạy:

```bash
bash verify.sh
```

`set -e` dừng khi một lệnh biên dịch hoặc chạy Java trả mã khác `0`; `-u` báo biến chưa khai báo; `pipefail` không che lỗi trong pipeline. Script `cd` về vị trí script để các đường dẫn tương đối trong harness ổn định.

**Lưu ý về build sạch:** ví dụ chỉ tạo ba file `.class`/JAR với tên cố định, mỗi lượt biên dịch ghi lại lớp `Hello`; nhưng đây vẫn là **smoke test** trong workspace hiện tại. Để kiểm chứng tính tái lập nghiêm ngặt, chạy hai lượt từ **hai checkout sạch** của cùng commit hoặc hai container mới, không tái dùng output và cache. Trong một repo thực tế, nên dành riêng workspace cho bài lab và đặt `build/` trong `.gitignore`.

### 6.1. Chạy tương đương trên Windows PowerShell

Ở PowerShell, chạy từng dòng sau từ project root:

```powershell
New-Item -ItemType Directory -Force build/a/classes,build/b/classes,build/tools | Out-Null
javac --release 17 -encoding UTF-8 -proc:none -Xlint:all -d build/a/classes src/main/java/demo/Hello.java
if ($LASTEXITCODE -ne 0) { throw "compile a failed" }

javac --release 17 -encoding UTF-8 -proc:none -Xlint:all -d build/b/classes src/main/java/demo/Hello.java
if ($LASTEXITCODE -ne 0) { throw "compile b failed" }

javac --release 17 -encoding UTF-8 -proc:none -d build/tools src/test/java/BuildAudit.java
if ($LASTEXITCODE -ne 0) { throw "compile audit failed" }

java -cp build/tools BuildAudit
if ($LASTEXITCODE -ne 0) { throw "build audit failed" }
```

Đây là lệnh chạy tương đương, không phải file `verify.ps1` riêng. Với **Windows PowerShell 5.1**, thao tác lưu Java source từ `Set-Content -Encoding UTF8` có thể thêm UTF-8 BOM; nên dùng editor UTF-8 without BOM hoặc `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))` để tránh lỗi `illegal character: '\ufeff'`.

### 6.2. Hash để đối chiếu hoặc công bố bằng chứng

Harness so sánh byte bằng `Arrays.equals`; khi xuất bản artifact, nên ghi thêm SHA-256:

```bash
sha256sum build/a/app.jar build/b/app.jar
```

Trên PowerShell:

```powershell
Get-FileHash build/a/app.jar -Algorithm SHA256
Get-FileHash build/b/app.jar -Algorithm SHA256
```

Hai giá trị hash **phải trùng nhau trong lần chạy đạt PASS**, nhưng không có một hash cố định phổ quát cho mọi JDK và môi trường. Hash một mình không chứng minh nguồn/thư viện tin cậy; cần biết rõ commit, toolchain và các đầu vào tương ứng.

## 7. Tích hợp CI: build sai phải làm job thất bại

Ví dụ workflow GitHub Actions, đặt tại **`.github/workflows/verify-javac.yml`** khi đưa bài lab vào repo GitHub:

```yaml
name: Verify javac build

on:
  push:
  pull_request:

jobs:
  build-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Compile, run, verify diagnostics and artifacts
        run: bash verify.sh
```

Workflow là **ví dụ cấu hình**, chưa được thực thi trên GitHub Actions trong bài này. Nếu repository yêu cầu bảo vệ chuỗi cung ứng, pin actions theo **commit SHA** đã phê duyệt, sử dụng runner image/toolchain có provenance và tránh phụ thuộc tag trôi. `java-version: '17'` chọn dòng Java 17 nhưng chưa cố định chính xác patch/vendor artifact; muốn so sánh byte giữa nhiều runner, pin distribution/version và kiểm tra chúng.

Bổ sung cho CI thực tế:

- Chạy workflow từ checkout sạch, không dùng output artifacts từ lần build trước.
- Lưu `java -version`, `javac -version`, mã commit, options, checksum đầu ra và report failure.
- Với dependency bên thứ ba, pin version/lockfile và checksum, kiểm soát repository, classpath và annotation processors.
- Nếu test có yêu cầu cross-platform, chạy thêm Windows/macOS matrix nhưng **không vội kết luận rằng JAR từ mọi OS/JDK đều bit-identical**; mỗi môi trường khác có thể để lộ nguồn không tái lập.
- Kiểm tra PR bằng cùng lệnh `bash verify.sh` như local để hạn chế sai khác giữa developer và CI.

## 8. Thử làm cho test thất bại: kiểm tra test có “răng”

Một test chỉ chạy màu xanh chưa chắc có tác dụng. Hãy thay đổi **một đầu vào mỗi lần**, quan sát failure có liên quan và hoàn tác thay đổi.

| Thí nghiệm | Thay đổi duy nhất | Kỳ vọng chính xác |
| --- | --- | --- |
| Class-file target | Sửa một trong hai lệnh compile từ `--release 17` sang `--release 21` (compiler hỗ trợ 21) | Byte class khác hoặc assertion `major == 61` thất bại |
| Runtime output | Sửa `Hello.java` in `"Unexpected"` | `Unexpected stdout`, exit code khác `0` |
| Lỗi negative bị “sửa” | Sửa `int count = "not a number";` thành `int count = 1;` | `Invalid source unexpectedly compiled` |
| Vị trí lỗi đổi | Chèn một dòng thực vào phía trước dòng gán sai của `BadHello.java` | `Expected ERROR at BadHello.java:4` |
| So sánh artifact | Sửa byte một bản `app.jar` **sau khi được tạo** trong môi trường test hoặc bổ sung step kiểm tra sau đóng gói | So sánh byte JAR phải thất bại nếu mutation xảy ra trước assertion |
| Kiểm tra cờ compile | Xóa `--release 17` và chạy trên JDK mới | Major không còn bảo đảm là 61, assertion nên phát hiện nếu compiler sinh target hiện hành |

**Cảnh báo kỹ thuật về thử nghiệm cuối:** `BuildAudit` tự tạo lại `app.jar` trước khi so sánh, vì vậy thay đổi file JAR **trước khi chạy harness** sẽ bị ghi đè và không phải mutation test hợp lệ. Muốn kiểm tra khả năng phát hiện JAR khác byte, hãy thay đổi một input/logic packager giữa hai lượt, hoặc tách bước package và bước audit thành hai chương trình riêng. Mục tiêu là thử **đúng bước đang kiểm chứng**, tránh “test đèn xanh” do sửa nhầm một file bị dựng lại.

### 8.1. Vì sao phải kiểm tra diagnostic theo vị trí?

Nếu chỉ kiểm tra `compiled == false` thì source lỗi vì **thiếu classpath** cũng khiến test pass. Trong bài này yêu cầu thêm:

```java
d.getKind() == Diagnostic.Kind.ERROR
    && d.getLineNumber() == 4
    && d.getColumnNumber() > 0
    && d.getSource() != null
```

Đó là **snippet trích từ phương thức kiểm tra ở phần 5**, không phải chương trình độc lập. Cần thêm kiểm tra source URI như code hoàn chỉnh vì nhiều file khác nhau có thể cùng báo lỗi ở dòng 4. Khi kiểm thử **annotation processor**, thay `-proc:none` bằng processor path/selection được pin và thêm assertion cho diagnostics của processor; bài lab hiện tại cố ý không làm việc đó.

## 9. Phân tích độ tin cậy và giới hạn kỹ thuật

### 9.1. Repeatable trong một máy và reproducible độc lập

Đạt `Class bytes: MATCH` giữa hai lần trên một máy chứng minh fixture đang tạo bytecode nhất quán trong điều kiện ấy. Đạt `JAR bytes: MATCH` chứng minh phương pháp package trong cùng environment cho byte archive bằng nhau. Để nâng lên **reproducible build** thực sự, cần tái tạo từ cùng source/đầu vào được chứng minh trên môi trường độc lập, không dựa vào cache ẩn.

Các đầu vào thường bị bỏ sót:

| Đầu vào | Rủi ro không được test nhỏ phát hiện | Cách kiểm soát trong dự án lớn |
| --- | --- | --- |
| `javac` vendor/patch | Cùng `--release` nhưng bytecode/diagnostics có thể khác | Pin JDK distribution, patch, image digest |
| JDK module/toolchain | CI chọn `java`/`javac` khác developer | Dùng toolchain và in phiên bản |
| Compile classpath | Phiên bản transitives, thứ tự và nội dung file thay đổi | Dependency locks/checksums và classpath explicit |
| Annotation processors | Sinh code có timestamp, option hoặc processor version khác | Processor path/version/options được pin |
| Sources/resources | Encoding, newline, line ending khác | UTF-8, `.gitattributes`, resource plugin chuẩn |
| Packaging | ZIP timestamp/order, manifest, resource hash khác | Timestamp cố định, thứ tự ổn định, packager được pin |
| Generated files | Clock, random UUID, hostname, absolute path | Inject input có nguồn gốc hoặc bỏ metadata động |
| Runtime/integration tests | Locale/time zone, environment, test order | Cô lập process, locale/time zone cố định khi cần |
| Build cache | Chứa output cũ, làm test pass giả | Chạy cold build ở CI, verify task inputs |
| Native dependencies | File nhị phân phụ thuộc OS/architecture | Môi trường/toolchain native riêng, lưu provenance |

### 9.2. Điều gì được cố định trong JAR demo?

`packageClass` ghi **đúng một entry** với tên cố định, dữ liệu từ `Hello.class` và timestamp cố định. Nó không tự động giải quyết mọi trường hợp JAR phức tạp:

- Nếu đóng gói nhiều entry, phải **sort tên trước** khi gọi `putNextEntry`.
- Không nhúng manifest chứa current build time, tên máy, username, absolute path hoặc random UUID.
- Các entry/resources phải có bytes ổn định; class bytes giống nhau không nói được gì về JSON/config sinh động.
- Cần dùng cùng implementation/phiên bản ZIP compressor khi đòi hỏi byte-identical qua nhiều môi trường. Hai JDK khác nhau có thể dùng thành phần nén khác nhau.
- Việc dùng fixed timestamp từ bài lab là lựa chọn minh họa; build phát hành có thể dùng một release timestamp xác định, `SOURCE_DATE_EPOCH` hoặc metadata từ commit, miễn là đầu vào đã được quy định.
- Test này so hai file `app.jar` có entry `demo/Hello.class`; không phải hướng dẫn thay thế Maven/Gradle JAR packaging của project nhiều module.

### 9.3. Không đồng nhất các loại kiểm chứng

| Cách kiểm tra | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `javac` exit code `0` | Compilation task thành công | App chạy đúng |
| `javap` major = 61 | Class file target Java 17 | Không dùng API không phù hợp ở mọi dependency |
| App stdout/exit | Tình huống chạy cụ thể đúng | Toàn bộ logic ứng dụng đúng |
| Negative `Diagnostic` | Compiler bắt đúng loại và source/line của fixture | Tất cả lỗi tiềm năng được bắt |
| `Arrays.equals` của hai `.class` | Hai class byte-identical | Tất cả resource/JAR metadata giống |
| `Arrays.equals` của hai JAR | Hai JAR byte-identical | Artifact được tạo từ nguồn đáng tin hoặc độc lập |
| `sha256sum` | Dấu vân tay artifact để lưu/đối chiếu | Một mình xác thực nguồn gốc/reproducibility |

## 10. Khi đưa bài lab lên Maven hoặc Gradle

Ở project lớn, không nên dùng script `javac` tùy tiện để bỏ qua dependency graph và plugins thật; giữ tư duy kiểm chứng của bài lab nhưng đưa các bước compile/test/package vào build system:

**Maven:**

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Đây là **đoạn POM minh họa**, cần Maven Compiler/JAR/Resources Plugin phiên bản hỗ trợ thích hợp, wrapper và dependencies đã pin; `project.build.outputTimestamp` không tự xử lý mọi generator. Kiểm tra cả file JAR bằng hash trong CI.

**Gradle Kotlin DSL:**

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Đây cũng là **đoạn cấu hình**, không phải `build.gradle.kts` độc lập. Gradle `Jar` còn có manifest, resources, plugins và dependency graph cần kiểm soát. Annotation processors phải có configuration riêng và chạy khi cần; không áp `-proc:none` cho module có codegen.

**Tư duy chung:** wrapper + JDK/toolchain + compile flags + reproducible archives + tests/diagnostics + cross-environment hash comparison. Chỉ nên tuyên bố tái lập hoàn toàn sau khi kiểm chứng **artifact thật** từ các môi trường độc lập đã định danh.

## 11. Chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `invalid target release: 17` | `javac` cũ hơn Java 17 | Dùng JDK 17+, xác minh `javac -version` |
| `error: package ... does not exist` | Classpath chưa khai báo hoặc sai nguồn | Pin dependency và `-classpath`/module path thích hợp |
| `Could not find or load main class demo.Hello` | `-d` sai, sai package hoặc `-cp` | Kiểm tra `build/a/classes/demo/Hello.class` |
| Java source bắt đầu bằng ký tự lạ `\ufeff` | UTF-8 BOM do editor/PowerShell cũ | Lưu UTF-8 không BOM |
| `Class files differ` | Hai compile không dùng cùng source/options/toolchain hoặc generator nondeterministic | Diff bytecode, kiểm tra `javac` và inputs |
| `Expected Java 17 class-file version 61` | Quên `--release 17` hoặc build dùng target khác | Dùng `--release` đúng ở mọi lượt |
| `JAR files differ` | Entry timestamp/order, manifest, resources, compressor khác | Cố định metadata/entry order và packager |
| `Application stdout: PASS` thất bại | Ứng dụng in sai, newline/charset hoặc runtime khác | Xem stdout/exit, cố định encoding |
| `Invalid source unexpectedly compiled` | Negative fixture bị sửa thành hợp lệ | Khôi phục phép gán sai kiểu |
| `Expected ERROR at BadHello.java:4` | Diagnostic lỗi khác/line shift/source sai | Kiểm tra đúng source và dòng trong fixture |
| `System Java compiler is unavailable` | Runtime image không chứa compiler | Chạy test bằng JDK đầy đủ |
| Local pass nhưng CI fail | Khác Java version, charset, working directory hoặc environment | Log toolchain và chạy cùng verify script |

## 12. Bài tập mở rộng theo mức độ

**Mức 1 – compiler flags:** thêm `-Werror` vào positive compile, viết một source cố ý phát warning bằng `-Xlint:deprecation` và quan sát exit code. Phân biệt `WARNING`/`MANDATORY_WARNING` với `ERROR`; không giả định mọi warning chuyển thành diagnostic `ERROR` ở cùng dòng.

**Mức 2 – compiler API:** thay `BadHello.java` bằng hai source, một source hợp lệ và một source lỗi. Assert đúng URI/dòng/cột của lỗi; xử lý trường hợp `getSource() == null` hoặc `getLineNumber() == Diagnostic.NOPOS` cho diagnostics không có location. Test không nên phụ thuộc nguyên văn `getMessage(Locale)`.

**Mức 3 – nhiều artifact:** thêm `demo/Maths.java` và một resource UTF-8. Sắp xếp tên entry theo thứ tự xác định, đóng gói chúng vào JAR và so sánh từng byte giữa hai checkout. Chỉ sau khi đã thay đổi code `packageClass` để thêm entry, mới kiểm tra hash toàn artifact.

**Mức 4 – độc lập môi trường:** tạo hai container sạch với **cùng JDK image digest**, cùng source commit và lệnh build, lưu SHA-256 và đối chiếu. Sau đó cố ý đổi JDK patch hoặc timezone để đánh giá liệu artifact có giữ nguyên hay không; ghi kết quả thực nghiệm, không đoán.

**Mức 5 – dự án có dependencies:** thêm một thư viện thật, pin version/checksum, thiết lập compiler classpath explicit, rồi giải thích vì sao biên dịch dựa vào classpath ngẫu nhiên từ IDE không phải test reproducibility đáng tin.

## 13. Checklist nghiệm thu và câu hỏi tự đánh giá

- [ ] `src/main/java/demo/Hello.java` chạy và in chính xác `Hello from Java 17`.
- [ ] Hai lần compile dùng cùng `--release 17 -encoding UTF-8 -proc:none`, output ở `build/a` và `build/b`.
- [ ] `BuildAudit.java` được biên dịch, cho **sáu dòng PASS/MATCH** như mẫu.
- [ ] `BadHello.java` cố ý lỗi ở dòng 4 và diagnostic đúng kind/source/line; sửa lỗi sẽ khiến test fail.
- [ ] Thay stdout hoặc thay compile target sẽ làm bộ kiểm chứng không đạt.
- [ ] Script trả exit code khác `0` khi một assertion thất bại.
- [ ] Không nhầm “hai lần cùng máy giống nhau” với chứng minh reproducibility trên môi trường độc lập.
- [ ] Không đưa `build/`, file JAR sinh ra hoặc source fixture có lỗi vào danh sách source production.
- [ ] Đã đọc log JDK, compiler, hash khi chạy CI và hiểu giới hạn timestamp/metadata của JAR.

**Tự hỏi:** Vì sao `--release 17` cần thiết dù bạn đang dùng JDK 24? Vì sao chỉ so `.class` không đủ cho artifact JAR? Vì sao test nguồn lỗi phải kiểm tra `Diagnostic.Kind`, source URI và vị trí, thay vì chỉ kiểm tra `call() == false`? Cần thay đổi gì để kết luận hai CI runners thực sự dựng lại cùng artifact?

## Tài liệu tham khảo

- Java SE 17 – `javac` options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java SE 17 – Java Compiler API: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17 – `Diagnostic`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Java SE 17 – `JarOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html
- Java SE 17 – class file format (JVMS): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17 – `jar` tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Apache Maven – Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Gradle – Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Reproducible Builds – SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
