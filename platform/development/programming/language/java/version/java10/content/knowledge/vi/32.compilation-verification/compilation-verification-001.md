# Java 10 – Biên dịch và kiểm chứng: Xác định phiên bản công cụ java, javac và javap

> **Chủ đề:** Java 10 → **Biên dịch và kiểm chứng** → **Xác định phiên bản công cụ `java`, `javac` và `javap`**. Bài học trình bày cách kiểm đúng **phiên bản, đường dẫn và chức năng** của ba công cụ Java; cách phân biệt **JDK compiler, JVM runtime, disassembler, bytecode target**; và cách kiểm trong PowerShell, CMD, Linux, macOS, IDE, Maven, Gradle, Docker/CI. Cú pháp chính vẫn áp dụng trên **Java 17+ và các bản JDK hiện đại**. Các ví dụ đã được kiểm thử trên **Azul Zulu OpenJDK 24.0.2**; Java 10 là mốc của nội dung học, **không phải khuyến nghị triển khai JDK 10 đã hết vòng đời hỗ trợ**.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Nói chính xác `java`, `javac` và `javap` thực hiện những nhiệm vụ khác nhau.
2. Sử dụng đúng lệnh `java -version` hoặc `java --version` để kiểm phiên bản **runtime launcher**.
3. Sử dụng `javac -version` hoặc `javac --version` để kiểm phiên bản **compiler**.
4. Sử dụng đúng **`javap -version`** để kiểm phiên bản **class-file disassembler**.
5. Biết vì sao không thể mặc định `javap --version` hợp lệ: phiên bản JDK24 được thử đã từ chối option này.
6. Phân biệt output `java -version` trên **stderr** với `java --version` trên **stdout**.
7. Xác định executable thực bằng `Get-Command`/`where.exe` trên Windows, `command -v`/`type -a` trên Unix.
8. So sánh `JAVA_HOME`, `PATH`, alias, symlink và JDK toolchains để tìm trường hợp ba công cụ không cùng JDK.
9. Đọc `java.home`, `java.version`, `java.vendor` và `Runtime.version().feature()`.
10. Biên dịch và chạy ví dụ Java 17+, dùng `javap -verbose` kiểm `major version: 61`.
11. Giải thích vì sao Java 10 class file có **major version 54**, dù compiler được cài trên máy có thể là bản mới hơn.
12. Hiểu `javac --release` kiểm nguồn/API/bytecode target khác với `--source`, `--target`, nhưng không giả lập toàn bộ runtime.
13. Chẩn đoán `UnsupportedClassVersionError` và trường hợp tool không tồn tại.
14. Biết Maven/Gradle/IDE và container image có thể chọn JDK khác so với terminal.
15. Chuẩn hóa một checklist kiểm thử **tool versions + paths + artifact target + runtime thực** cho dự án.

**Kết luận:** `java -version`, `javac -version`, `javap -version` cho biết **công cụ nào được gọi**, còn `javap -verbose` cho biết **class file đã biên dịch ra định dạng nào**. Hai loại thông tin này không đồng nhất và không được sử dụng thay cho nhau.

## 2. Phân biệt ba công cụ và đầu ra

| Công cụ | Vai trò | Đầu vào thường gặp | Đầu ra | Cú pháp version được tài liệu hóa |
| --- | --- | --- | --- | --- |
| **`java`** | Java launcher khởi chạy JVM, class, JAR hoặc module | Main class, `-jar`, Java options | Chạy ứng dụng/VM information | `java -version`, `java --version` |
| **`javac`** | Java compiler | Source `.java`, class/module paths, compiler flags | `.class` và compiler diagnostics | `javac -version`, `javac --version` |
| **`javap`** | Class-file disassembler/inspector | Class name, `.class`, classpath | Fields, methods, bytecode, class metadata | **`javap -version`** |

Sơ đồ:

~~~text
Toolchain/JDK được chọn
   |
   +-- java  -> chạy Java program trên runtime được chọn
   |
   +-- javac -> biên dịch Source.java
   |                 |
   |                 v
   |              Source.class
   |              (major/minor version)
   |
   +-- javap -> đọc/giải mã Source.class
~~~

**Điểm dễ nhầm:** `javap -version` không “phân tích file .class”. Nó chỉ in release của chính `javap`. Để biết Java target của file class, dùng `javap -verbose` hoặc đọc đúng class-file header theo Java Virtual Machine Specification.

## 3. Năm lệnh kiểm phiên bản cơ bản

~~~bash
java -version
java --version
javac -version
javac --version
javap -version
~~~

Cả `java` và `javac` có thể dùng `-version` hoặc `--version` trên các JDK hiện đại theo Oracle manuals. Riêng manual `javap` công bố option **`-version`**, không phải mặc định `--version`. Trên **JDK 24.0.2** đã thử, lệnh:

~~~text
javap --version
Error: unknown option: --version
~~~

đã thất bại. Bởi vậy đoạn shell sau **không đúng** với tất cả các công cụ:

~~~bash
# Không nên áp cùng --version cho javap:
for tool in java javac javap; do
    "$tool" --version
done
~~~

Lệnh kiểm đúng:

~~~bash
java --version
javac --version
javap -version
~~~

Khi viết script CI, luôn kiểm **exit code**. Một công cụ in “unknown option” vẫn có output text, nhưng đó không phải kết quả thành công.

### 3.1. Kết quả thực tế từ JDK được thử

Trên Windows với Zulu OpenJDK 24.0.2:

~~~text
> java -version
openjdk version "24.0.2" 2025-07-15
OpenJDK Runtime Environment Zulu24.32+13-CA (build 24.0.2+12)
OpenJDK 64-Bit Server VM Zulu24.32+13-CA (build 24.0.2+12, mixed mode, sharing)

> javac -version
javac 24.0.2

> javap -version
24.0.2
~~~

Các dấu `>` ở đầu transcript là ký hiệu minh họa command prompt, **không phải ký tự nhập thêm**. Những dòng trên là **kết quả tại máy thử**, không phải version mới nhất hoặc expected value của mọi máy. Đọc output trên hệ thống của bạn thay vì sao chép chuỗi “24.0.2”.

### 3.2. Vì sao `javap` chỉ in số phiên bản?

Trong bản thử, `javap -version` chỉ in `24.0.2`, không có tiền tố `javap`. Đây là output hợp lệ: tài liệu chỉ cam kết tùy chọn này in release information. Một parser tự yêu cầu `^javap ` có thể báo lỗi dù lệnh thành công.

## 4. `java -version` và `java --version`: khác luồng stdout/stderr

Theo Java launcher manual hiện hành:

- `java -version`: in product version vào **stderr**, rồi thoát.
- `java --version`: in product version vào **stdout**, rồi thoát.
- `java -showversion` / `--show-version`: in version nhưng còn tiếp tục xử lý lệnh khởi chạy nếu có ứng dụng.

Ví dụ POSIX shell:

~~~bash
java --version > java-version.txt
~~~

thường ghi phần version vào file qua stdout. Nhưng:

~~~bash
java -version > java-version.txt
~~~

có thể tạo file rỗng bởi version được in vào stderr. Nếu bắt buộc ghi `-version` vào cùng file:

~~~bash
java -version > java-version.txt 2>&1
~~~

**Không suy một file log rỗng là không cài Java.** Trước tiên xem command exit code, stderr và hành vi redirection.

### 4.1. Version có thể được thêm dòng cảnh báo

Ví dụ các biến môi trường như `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` hoặc các launcher wrappers có thể tác động Java startup hoặc in thêm thông tin. Không parse version bằng cách giả định nó **luôn nằm ở đúng dòng thứ nhất** hoặc output chỉ gồm một dòng; thay vào đó kiểm đúng command, exit code và format theo JDK vendor/build được hỗ trợ.

### 4.2. “Java installed” không có nghĩa ba tools đều installed

Một **runtime-only**/custom `jlink` image có thể có `java` nhưng không cung cấp `javac`, `javap`. Đây là thiết kế hợp lệ khi môi trường chỉ chạy ứng dụng. Nếu build cần compiler, dùng JDK/toolchain phù hợp; không tự cài trình biên dịch vào production image chỉ để làm lệnh version.

## 5. Cách đọc version number và vendor information

Ví dụ:

~~~text
openjdk version "24.0.2" 2025-07-15
OpenJDK Runtime Environment Zulu24.32+13-CA (build 24.0.2+12)
~~~

- `24` là **feature version** của runtime được thử.
- `0.2` là phần phát hành/update của version string; đừng đọc thành một Java language feature riêng.
- `2025-07-15` là mốc release được runtime thử in.
- `Zulu...` là metadata của distribution/vendor build.
- `64-Bit Server VM` nói về triển khai VM/kiến trúc.
- Một distribution khác có thể in tên `java`, `openjdk`, vendor hoặc build string khác.

Java 9+ dùng version scheme hiện đại theo JEP 223; JEP 322 bổ sung time-based release versioning từ Java 10. Khi kiểm môi trường thật, thường cần **feature release + exact update/build/vendor**, chứ không chỉ “đây là Java 17”.

### 5.1. Runtime feature khác compiler target

Một JVM Java 24 có thể chạy một class file target Java 17 (major 61). Tương tự, một javac version 24 có thể biên dịch `--release 10` nếu compiler đó hỗ trợ release 10. **Compiler vẫn là 24**; `--release` không thay đổi tool version.

## 6. Công cụ `javac`: biết compiler version chưa đủ

~~~bash
javac -version
javac --version
javac --help
~~~

`--help` liệt kê các giá trị `--release`, `--source` và `--target` mà **JDK thực đang chạy** hỗ trợ. Không ghi cứng giả định rằng mọi JDK tương lai vẫn hỗ trợ compile tới Java 10.

### 6.1. `--release`, `--source`, `--target` khác nhau

| Option | Điều khiển | Giới hạn cần nhớ |
| --- | --- | --- |
| `--source N` | Quy tắc Java source/language syntax cho release N | Không tự hạn chế toàn bộ API tới N |
| `--target N` | Định dạng class file target N | Chỉ format không bảo đảm API compatibility |
| **`--release N`** | Source/target cùng API surface của release N mà compiler hỗ trợ | Không giả lập mọi behavior runtime, vẫn cần test |

Đối với mục tiêu chạy Java 17, ưu tiên:

~~~bash
javac --release 17 -encoding UTF-8 -d out ToolchainEvidence.java
~~~

thay vì chỉ:

~~~bash
javac --source 17 --target 17 -d out ToolchainEvidence.java
~~~

Với source/target, bạn vẫn có thể vô tình tham chiếu đến APIs chỉ có ở JDK mới hơn nếu không thiết lập system/boot platform phù hợp. `--release` giúp kiểm compile-time API compatibility với N; tuy nhiên **không thay thế integration tests chạy trên JVM N**. Không được kết hợp `--release` với `--source`/`--target` trong cùng lệnh như thể chúng cộng dồn.

### 6.2. `--release` không phải “phiên bản JDK đang chạy”

Ví dụ:

~~~text
javac executable version: 24.0.2
javac option:            --release 17
generated class major:   61
runtime used to test:    24.0.2
~~~

Bốn thông tin trên có thể cùng đúng. Biên dịch target 17 và chạy trên 24 **chưa chứng minh** ứng dụng chạy đúng trên 17; nếu dự án cần hỗ trợ Java 17, hãy kiểm trên runtime 17 thật. Đồng thời các dependencies phải hỗ trợ target runtime đó.

## 7. Công cụ `javap`: hai kiểu kiểm tra riêng

**Kiểm phiên bản công cụ:**

~~~bash
javap -version
~~~

**Kiểm metadata của class file:**

~~~bash
javap -verbose -classpath out ToolchainEvidence
~~~

Tùy output class, có các dòng:

~~~text
minor version: 0
major version: 61
~~~

Ý nghĩa: file có target **Java 17**, không phải “javap version 61”. Trong bài thử, `javap -version` in `24.0.2` và `javap -verbose` cho `major version: 61` — hoàn toàn bình thường.

### 7.1. Các option inspector hữu ích hiện nay

- `-verbose` hoặc `-v`: xem detailed class file info, constant pool và major/minor.
- `-c`: in disassembled Java bytecode instructions.
- `-p` hoặc `-private`: in các thành viên private.
- `-sysinfo`: thông tin path, size, date và SHA-256 hash khi hỗ trợ.
- `--class-path`/`-classpath`: chỉ định nơi tìm class, tránh đọc nhầm class cũ.
- `--multi-release`: chọn versioned entry khi đọc multi-release JAR theo đường tham chiếu tương ứng.

**Không dùng `javap` để tự tạo file class mới.** Nó là công cụ quan sát class đã biên dịch. Khi gặp bytecode lạ, phải kiểm **đúng file build output**, không vô thức chạy inspector ở thư mục khác.

### 7.2. Kiểm file class trực tiếp để tránh CLASSPATH sai

~~~bash
javap -verbose out/ToolchainEvidence.class
~~~

hoặc:

~~~bash
javap -verbose -classpath out ToolchainEvidence
~~~

Trên Windows, có thể dùng `out\ToolchainEvidence.class`. Nếu thư mục build chứa nhiều bản class khác nhau, lệnh thiếu `-classpath` có thể hiển thị một file từ CLASSPATH khác; khi debug hãy chọn artifact/path tường minh.

## 8. Đọc class-file major/minor theo Java Virtual Machine Specification

Theo JVMS, file `.class` bắt đầu bằng **magic 0xCAFEBABE**, rồi có `minor_version` và `major_version`. Một số bản Java hay gặp:

| Java SE | `major version` | Bối cảnh |
| --- | ---: | --- |
| Java 8 | 52 | Artifact cũ |
| Java 9 | 53 | Modules xuất hiện |
| **Java 10** | **54** | Nội dung module đang học |
| Java 11 | 55 | Target của nhiều hệ thống cũ |
| Java 17 | 61 | Target ví dụ trong bài |
| Java 21 | 65 | JDK 21 |
| Java 24 | 68 | Phiên bản compiler/inspector trong lần thử |
| Java 25 | 69 | Theo JVMS Java SE 25 |

Bảng này giúp **đọc artifact**, không phải khuyến nghị bắt đầu dự án mới bằng JDK 8/9/10. Chọn runtime có hỗ trợ bảo mật còn hiệu lực và phù hợp requirement của dự án.

### 8.1. `minor 65535` và preview features

Với class format Java 12+, theo JVMS, minor thường là **0** hoặc **65535**; 65535 gắn với preview-dependent class format và có điều kiện chạy trên **đúng Java release với preview enabled**, không tự cho chạy trên mọi JDK cao hơn. Vì vậy major version một mình là thông tin quan trọng nhưng chưa chứng minh được toàn bộ runtime compatibility.

### 8.2. Khi class mới hơn runtime

Một JVM cũ hơn class target có thể ném:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Đây là dạng thông báo điển hình **đã lược phần cụ thể tùy class/runtime**, không phải output chính xác của mọi JDK. Quy trình xử lý:

1. Xác định runtime thực: `java -version` **ở nơi chạy ứng dụng**.
2. Kiểm đúng file class: `javap -verbose`.
3. Đối chiếu major/minor với Java release đích.
4. Rebuild bằng `--release N` nếu compiler hỗ trợ và source/dependencies tương thích, hoặc nâng runtime lên bản phù hợp.
5. Chạy tests trên runtime target. **Không** sửa hai bytes class header để ép tương thích.

## 9. Ví dụ Java 17+ độc lập đã biên dịch và chạy

Chương trình `ToolchainEvidence.java` đọc class header của chính nó qua resource stream, kiểm magic, minor/major, runtime feature và compiler API có trong runtime image không. Đây là bài tập về **bytecode target**, bổ sung cho các lệnh CLI kiểm tool version.

~~~java
import java.io.DataInputStream;
import java.io.InputStream;
import javax.tools.ToolProvider;

public final class ToolchainEvidence {
    public static void main(String[] args) throws Exception {
        String self = "ToolchainEvidence.class";
        try (InputStream stream = ToolchainEvidence.class.getResourceAsStream(self)) {
            if (stream == null) {
                throw new IllegalStateException("No class resource");
            }
            try (DataInputStream in = new DataInputStream(stream)) {
                int magic = in.readInt();
                int minor = in.readUnsignedShort();
                int major = in.readUnsignedShort();
                System.out.println("class-magic-ok=" + (magic == 0xCAFEBABE));
                System.out.println("class-minor=" + minor);
                System.out.println("class-major=" + major);
                System.out.println("compiled-for-java-17=" + (major == 61));
                System.out.println("runtime-at-least-17=" +
                        (Runtime.version().feature() >= 17));
                System.out.println("compiler-in-image=" +
                        (ToolProvider.getSystemJavaCompiler() != null));
            }
        }
    }
}
~~~

### 9.1. Biên dịch và chạy trên Linux/macOS

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out ToolchainEvidence.java
java -cp out ToolchainEvidence
javap -verbose -classpath out ToolchainEvidence
~~~

### 9.2. Biên dịch và chạy trên PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out ToolchainEvidence.java
java -cp out ToolchainEvidence
javap -verbose -classpath out ToolchainEvidence
~~~

### 9.3. Stdout chính xác đã kiểm chứng trên OpenJDK 24

~~~text
class-magic-ok=true
class-minor=0
class-major=61
compiled-for-java-17=true
runtime-at-least-17=true
compiler-in-image=true
~~~

**Cơ sở:** code được biên dịch bằng `javac --release 17` và chạy trên bản **JDK đầy đủ OpenJDK 24.0.2**. Trong runtime-only image không chứa compiler API, dòng `compiler-in-image` có thể là `false`; trong runtime cũ hơn 17, file major 61 có thể bị từ chối tải trước khi chạy `main`.

### 9.4. Giải thích từng dòng

- `class-magic-ok=true`: đọc đúng magic bytes `CAFEBABE`.
- `class-minor=0`: file demo không sử dụng preview class marker.
- `class-major=61`: target class file Java 17.
- `compiled-for-java-17=true`: so đúng với constant 61 của Java 17.
- `runtime-at-least-17=true`: runtime thực có feature version ≥17.
- `compiler-in-image=true`: compiler API hiện diện trong runtime image thử; **không phải** chứng minh CLI `javac` từ PATH cùng installation.

### 9.5. Vì sao chương trình không in cứng `Runtime.version()`?

Exact version sẽ thay theo người chạy (17/21/24/25, update, vendor). Bài dùng điều kiện boolean để stdout ổn định trên JDK đầy đủ ≥17. Khi cần audit, có thể in:

~~~java
System.out.println(Runtime.version());
System.out.println(System.getProperty("java.home"));
System.out.println(System.getProperty("java.vendor"));
~~~

Đây chỉ là **snippet thêm vào method**, không phải chương trình chạy độc lập. Đừng lấy version string của môi trường người viết làm expected output của toàn bộ CI.

## 10. Ví dụ riêng: compiler mới tạo bytecode Java 10

Lưu source `TargetTen.java`:

~~~java
public class TargetTen {
    public static void main(String[] args) {
        System.out.println("release10-ok");
    }
}
~~~

Với một JDK **còn hỗ trợ target 10** (đã kiểm trên javac24):

~~~bash
mkdir -p out10
javac --release 10 -encoding UTF-8 -d out10 TargetTen.java
javap -verbose -classpath out10 TargetTen
java -cp out10 TargetTen
~~~

Kết quả class header đã thử:

~~~text
minor version: 0
major version: 54
~~~

Stdout chương trình:

~~~text
release10-ok
~~~

**Điều chứng minh:** `javac` 24 trong thí nghiệm đã tạo class target Java 10 với `--release 10`; `javap` báo major 54; Java 24 runtime chạy class thành công. **Chưa chứng minh** ứng dụng đã được test trên một runtime Java 10 thật. Để đảm bảo chạy trên target legacy khi dự án bắt buộc, cần test runtime đích và dependency compatibility theo chính sách, không khuyến khích dùng JDK 10 EOL cho môi trường mới.

Không phải mọi compiler bản mới hỗ trợ `--release 10`: Oracle `javac` chỉ cam kết tập release còn hỗ trợ được liệt kê trong `javac --help`.

## 11. Xác định đường dẫn trên Windows: PowerShell và CMD

Trong **PowerShell**:

~~~powershell
Get-Command java,javac,javap -All |
    Select-Object Name,CommandType,Source

where.exe java
where.exe javac
where.exe javap
~~~

`Get-Command -All` cho phép xem aliases/functions/applications và nguồn command; `where.exe` tìm executable theo PATH Windows. Trong PowerShell, `where` có thể là alias `Where-Object`, nên hãy gọi rõ **`where.exe`**. Trong CMD, `where java` cũng được.

Trên máy thử Zulu OpenJDK24, ba executables được tìm thấy tại cùng thư mục `bin` thuộc JDK 24.0.2. Đây là quan sát local, không phải bảo đảm người học cũng có cùng đường dẫn.

### 11.1. Vì sao PATH khác JAVA_HOME?

`JAVA_HOME` là một **environment variable** thường trỏ tới **thư mục gốc JDK**, còn `PATH` quyết định lệnh `java`/`javac`/`javap` nào được terminal resolve trước.

Giả sử `JAVA_HOME` trỏ JDK 17 nhưng PATH đưa `bin` của JDK 24 lên trước, `java --version` có thể in 24. Đây không tự là JVM bug. Một IDE/build plugin còn có thể chọn JDK thứ ba bằng cấu hình riêng.

### 11.2. Chạy trực tiếp công cụ từ JAVA_HOME

Với `JAVA_HOME` hợp lệ:

~~~powershell
$env:JAVA_HOME

& (Join-Path $env:JAVA_HOME 'bin\java.exe') --version
& (Join-Path $env:JAVA_HOME 'bin\javac.exe') --version
& (Join-Path $env:JAVA_HOME 'bin\javap.exe') -version
~~~

PowerShell call operator `&` quan trọng khi path có khoảng trắng. So sánh các kết quả này với lệnh gọi qua PATH; nếu khác, nguồn lệch là **resolution/configuration**, không phải “một chương trình Java có hai phiên bản”.

### 11.3. Khi PATH có nhiều candidates

Kiểm `Get-Command ... -All`, `where.exe`, sự tồn tại của shims, Windows App Execution Aliases khi có, shell đã mở trước khi sửa environment, Java home do IDE cấu hình. Đừng sửa system-wide PATH nếu chỉ một dự án cần chọn JDK cụ thể; ưu tiên project/toolchain selection.

## 12. Kiểm đường dẫn trên Linux

~~~bash
command -v java
command -v javac
command -v javap
type -a java javac javap
~~~

`command -v` cho cách shell resolve tên lệnh; `type -a` (trên shells hỗ trợ) liệt kê candidates. `which` là utility ngoài shell, không luôn phản ánh aliases/functions; dùng kèm chứ không coi là nguồn duy nhất.

Một Linux distribution có thể dùng symlinks/alternatives. Nếu có GNU coreutils:

~~~bash
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
readlink -f "$(command -v javap)"
~~~

`readlink -f` là tùy chọn phổ biến trên Linux/GNU, không coi nó là cú pháp di động mặc định cho mọi macOS. So sánh đích của cả ba symlinks để thấy có thuộc cùng JDK root hay không.

### 12.1. Xem biến môi trường

~~~bash
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
~~~

`JAVA_HOME` có thể rỗng dù Java được cài và tìm bằng PATH. Nếu đang sử dụng SDKMAN!, jenv, asdf hoặc công cụ quản lý phiên bản, shims có thể thay đổi JDK theo shell/project; kiểm kết quả thực thay vì chỉ nhìn file cấu hình.

## 13. Kiểm đường dẫn JDK trên macOS

~~~bash
/usr/libexec/java_home -V
~~~

Lệnh này giúp liệt kê JDK/JVM mà macOS utility nhận biết. Nếu JDK17 được cài phù hợp:

~~~bash
/usr/libexec/java_home -v 17
~~~

có thể trả đường dẫn JDK home được chọn. Không cam kết máy nào cũng cài JDK17 hoặc utility sẽ luôn trả phiên bản đó. Cũng cần chạy `command -v java` và `java --version` để biết terminal đang thực sự chọn executable nào; Homebrew/SDK managers có thể đặt symlink/shim trên PATH.

## 14. Kiểm runtime thật từ Java process

~~~bash
java -XshowSettings:properties -version
~~~

Trên JDK hỗ trợ, tìm những giá trị:

- `java.home`: nơi runtime thực thấy Java home, không nhất thiết giống `JAVA_HOME` trong shell.
- `java.version`: version string của runtime.
- `java.vendor`: nhà cung cấp.
- `java.vm.name`/`java.vm.version`: VM implementation/build.
- `os.arch`/`os.name`: nền tảng runtime.

Trong Java code:

~~~java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
System.out.println(System.getProperty("java.home"));
System.out.println(Runtime.version().feature());
~~~

Đây là **snippet cần đặt trong một method**. Nó xác minh JVM **đang chạy những dòng code đó**, không phải `javac`/`javap` CLI mà terminal hoặc build tool có thể chọn.

### 14.1. Đừng hiểu `java.home` là đường dẫn compiler

Runtime-only image có thể báo `java.home` hợp lệ mà thiếu compiler/disassembler. Chạy `javac --version`/`javap -version` hoặc kiểm toolchain image thực tế nếu cần biên dịch/disassemble; không tự suy từ property path.

## 15. Maven có thể chọn compiler khác JVM chạy Maven

~~~bash
mvn -version
~~~

Thông thường lệnh này cho **Maven version** và **Java runtime mà Maven process sử dụng**. Nhưng Maven Compiler Plugin có thể dùng toolchains hoặc external executable khác cho build task.

Ví dụ POM property:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây chỉ là **một đoạn cấu hình đặt trong POM hợp lệ**, không phải XML document đầy đủ. Giá trị release cần phản ánh target production/support matrix.

Khi nghi Maven dùng sai JDK, kiểm:

1. `mvn -version`: runtime của Maven.
2. Maven Compiler Plugin version/effective POM.
3. Maven toolchains settings khi có.
4. `maven.compiler.release`/plugin args được profile/CI override không.
5. Build logs và class files thực bằng `javap -verbose`.
6. Runtime chạy integration tests thực.

**Sai lầm:** kết luận “mvn -version in 21 nên mọi class là Java 21”. Toolchain có thể compile thành target17 hoặc dùng compiler khác; cuối cùng phải kiểm artifact.

## 16. Gradle có Java toolchains riêng

Trong project có Gradle Wrapper, trên Linux/macOS:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

Trên Windows PowerShell có thể dùng `.\gradlew.bat --version` và `.\gradlew.bat -q javaToolchains`. Lệnh `--version` nói về Gradle và JVM launcher/daemon, **không bảo đảm** compiler của mọi task là cùng JDK.

Ví dụ Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Với toolchain này, Gradle có thể chọn JDK17 cho compilation dù `javac --version` của terminal in JDK24. Đó có thể là lựa chọn đúng theo project target. Khi debug, xem `javaToolchains` và task/log/output artifact; không chỉ dựa `./gradlew --version`. Trường hợp test task dùng một JavaLauncher khác compiler cần được xác minh riêng.

Nguồn chính thức: Gradle User Guide – Toolchains for JVM Projects.

## 17. IDE có thể có nhiều Java versions đồng thời

IDE như IntelliJ IDEA, Eclipse hoặc VS Code Java thường có một số lựa chọn riêng:

- Project SDK/JDK.
- Module language level.
- Compiler bytecode target.
- Maven runner runtime.
- Gradle JVM/daemon.
- Gradle toolchain cho JavaCompile/Test tasks.
- Run/test configuration runtime.

Ví dụ tình huống hợp lệ:

~~~text
Terminal java --version:         Java 24
Terminal javac --version:        Java 24
Gradle Java compile toolchain:   Java 17
IDE run configuration:          Java 21
Compiled class major:           61 (Java 17)
~~~

Không có mâu thuẫn nếu dự án chủ đích compile target17 và run trên21; **nhưng** muốn cam kết chạy trên Java17, tests cần chạy trên Java17 thật. Đọc JDK selection của từng tác vụ, không lấy một ô “Project SDK 17” làm bằng chứng cho toàn hệ thống.

### 17.1. Vì sao clean/rebuild có lúc cần thiết?

Nếu `javap` đọc một class cũ còn nằm trong output directory, header major không phản ánh compiler flags mới nhất. Khi có quyền và muốn chẩn đoán, clean build rồi kiểm đường dẫn class output mới. Không tự xóa caches/prod artifacts nếu chỉ được yêu cầu kiểm version.

## 18. Docker: build stage và runtime stage có thể khác JDK

Một Dockerfile mô phỏng:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
COPY ToolchainEvidence.java .
RUN java --version && javac --version && javap -version
RUN mkdir -p out && javac --release 17 -d out ToolchainEvidence.java

FROM eclipse-temurin:21-jdk
WORKDIR /app
COPY --from=build /app/out /app/out
CMD ["java", "-cp", "out", "ToolchainEvidence"]
~~~

Đây là **mẫu kỹ thuật**, không phải một production Dockerfile tối ưu hoặc đã được chạy trong bài. Runtime stage vẫn dùng JDK đầy đủ để code sample `compiler-in-image=true` hoạt động. Trong production có thể dùng runtime-only image được hardened; lúc đó compiler có thể không tồn tại.

Đối chiếu versions bên trong đúng image:

~~~bash
docker run --rm eclipse-temurin:21-jdk java --version
docker run --rm eclipse-temurin:21-jdk javac --version
docker run --rm eclipse-temurin:21-jdk javap -version
~~~

Các lệnh trên phụ thuộc Docker/image availability và chính sách truy cập. Image tag có thể thay build theo thời gian; pin digest trong CI khi cần reproducibility. Không lấy `java -version` **của host** để kết luận container đang chạy Java nào.

### 18.1. Khi container không có shell/javap

Distroless hoặc image tối giản có thể không có `sh`, `javac`, `javap`. Đây chưa chắc là lỗi. Có thể ghi runtime metadata lúc startup, chạy inspection trong build stage hoặc dùng công cụ debug đã được phê duyệt. Không thêm full JDK vào runtime image chỉ để xem version nếu không cần.

## 19. CI: mẫu kiểm phiên bản không nhầm option

Một script POSIX chạy trong **build environment có JDK đầy đủ**:

~~~bash
set -eu
printf '%s\n' '=== java ==='
command -v java
java --version

printf '%s\n' '=== javac ==='
command -v javac
javac --version

printf '%s\n' '=== javap ==='
command -v javap
javap -version
~~~

Sử dụng `set -e` để dừng khi tool có exit code lỗi và `-u` để tránh biến chưa định nghĩa. Tránh vòng lặp dùng `--version` cho javap.

PowerShell:

~~~powershell
$ErrorActionPreference = 'Stop'

Get-Command java,javac,javap -All |
    Select-Object Name,CommandType,Source

& java --version
if ($LASTEXITCODE -ne 0) { throw 'java version failed' }

& javac --version
if ($LASTEXITCODE -ne 0) { throw 'javac version failed' }

& javap -version
if ($LASTEXITCODE -ne 0) { throw 'javap version failed' }
~~~

Báo cáo CI nên ghi **exact version strings, paths, target release, class major/minor, build JDK và runtime test JDK**. Không đưa secrets từ environment variables/command line vào public logs.

## 20. Các tình huống lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `java` chạy, `javac` không có | Runtime-only image, PATH thiếu compiler | Dùng JDK/build toolchain phù hợp |
| `javap --version` báo unknown option | `javap` không hỗ trợ long option đó | Dùng `javap -version` |
| `java -version` khác `javac -version` | PATH, toolchains, alias/shim, nhiều JDK | Resolve từng path, xác minh mục đích |
| `JAVA_HOME` khác `java --version` | JAVA_HOME không tự thay PATH | Kiểm PATH order, gọi explicit JDK bin |
| `javap` in class major mới hơn runtime | Artifact build target quá cao | Sửa target/build hoặc dùng runtime phù hợp |
| `UnsupportedClassVersionError` | Class version không được JVM hỗ trợ | Kiểm class major + Java runtime |
| `--release 10` không được javac chấp nhận | JDK không còn hỗ trợ target cũ | Xem `javac --help`, dùng compiler phù hợp nếu bắt buộc |
| IDE Java17 nhưng terminal Java24 | IDE cấu hình JVM riêng | Kiểm IDE project/build/run settings |
| Gradle/Maven build sai dù shell javac đúng | Plugin toolchain override | Kiểm toolchain/task/effective build |
| `javap -verbose` không cho major như dự kiến | Đọc class cũ hoặc sai classpath | Chỉ đúng compiled artifact, rebuild nếu cần |
| Class major 61 chạy trên Java21 | Compatibility hợp lệ | Nhưng vẫn test business behavior |
| Tool version text khác vendor | Distribution/update/build khác | Xác minh exact JDK, API target, runtime |
| Container image khác laptop | Isolated filesystem/PATH/runtime | Kiểm inside container/build stage |
| `java -version > file` tạo file rỗng | Version được in stderr | Dùng `java --version` hoặc `2>&1` |

### 20.1. Một compiler không nhất thiết “giống” một runtime là lỗi

Nếu compiler 24, runtime 17 và `--release 17`, setup có thể được thiết kế để giữ code compatible 17. Nhưng **phải** kiểm dependencies, release flags và tests trên runtime 17. Nếu dùng Java24 features mà compile target17 sẽ không được javac chấp nhận, đó là bảo vệ đúng.

### 20.2. “javap đọc được file” không đồng nghĩa runtime chạy được file

Inspector có thể hỗ trợ phân tích metadata/bytecode trong khi JVM đích không hỗ trợ class target, có dependency thiếu hoặc runtime behavior không tương thích. `javap` phục vụ chẩn đoán, còn **runtime test** là kiểm chứng thực thi.

### 20.3. Không chỉnh sửa raw major version bằng hex editor

Sửa 61 → 54 trong header chỉ thay **nhãn định dạng**, không làm Java17 bytecode, language features hoặc API references trở nên tương thích Java10. Hướng đúng là **biên dịch lại với target phù hợp** và chạy tests.

## 21. Quy trình kiểm chứng chuẩn trong dự án

1. Chạy `java --version`, `javac --version` và **`javap -version`**.
2. Ghi exit code của mỗi lệnh.
3. Resolve **đường dẫn executable** của cả ba tools.
4. Ghi `JAVA_HOME`, PATH order (đã loại secrets) và toolchain manager nếu dùng.
5. Kiểm `java.home`/`java.version` bằng runtime properties khi cần.
6. Xem `javac --help` để chắc target `--release N` được hỗ trợ.
7. Compile với `--release N` khi cần compatibility với N.
8. Dùng `javap -verbose` kiểm class major/minor từ **đúng output path**.
9. Đối chiếu dependencies/JAR class targets, không chỉ một class.
10. Kiểm Maven/Gradle compiler task/JDK toolchain nếu build không trực tiếp gọi javac CLI.
11. Kiểm runtime trong **image/pod/production environment** thật.
12. Chạy unit/integration tests trên runtime đích.
13. Ghi version/build/vendor/architecture, target release và test output.
14. Không dùng lỗi stdout/stderr để kết luận thiếu tool.
15. Giữ JDK được hỗ trợ, tránh dùng JDK10 EOL chỉ vì bài học nói về Java10.

### 21.1. Một định dạng báo cáo hữu ích

~~~text
java executable:       absolute path resolved by shell
java runtime version:  exact java --version output
javac executable:      absolute path resolved by shell
javac version:         exact javac --version output
javap executable:      absolute path resolved by shell
javap version:         exact javap -version output
JDK vendor/build:      from runtime/version properties
compiler target:       --release 17
class file minor:      0
class file major:      61
runtime used in tests: exact deployed/test JDK version
~~~

Các dòng là **tên trường cần điền từ dữ liệu thật**, không phải một bộ kết quả đã đo của mọi máy. Không log full file paths/usernames ra kênh công khai nếu chúng chứa thông tin nhạy cảm.

## 22. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `java` làm gì? — Khởi chạy Java application/JVM trong runtime được chọn.

**Câu 2.** `javac` làm gì? — Biên dịch Java source sang class files.

**Câu 3.** `javap` làm gì? — Phân tích/disassemble class files, không chạy hoặc compile source.

**Câu 4.** Lệnh kiểm javap version chuẩn là gì? — **`javap -version`**.

**Câu 5.** `javap --version` nên dùng mặc định? — Không; JDK24 thử báo unknown option, manual liệt kê `-version`.

**Câu 6.** `java -version` khác `java --version` về output stream? — `-version` stderr, `--version` stdout trên Java launcher hiện hành.

**Câu 7.** `javac --version` in 24 mà class major 61 có sai? — Không; compiler 24 có thể dùng `--release 17`.

**Câu 8.** Class major 54 nghĩa gì? — Target class file Java 10.

**Câu 9.** Class major 61 nghĩa gì? — Target class file Java 17.

**Câu 10.** Class major 65 nghĩa gì? — Target class file Java 21.

**Câu 11.** `javap -version` in 24 nghĩa class nó đọc target 24? — Không; tool version khác class target.

**Câu 12.** Vì sao `JAVA_HOME` có thể khác `java --version`? — Vì PATH/alias/shim/toolchain có thể chọn executable khác.

**Câu 13.** PowerShell dùng `where` hay `where.exe`? — Dùng **`where.exe`** để gọi Windows tool, tránh alias Where-Object.

**Câu 14.** Linux dùng gì để tìm Java executable? — `command -v java`, `type -a java`; khi cần resolve symlink bằng công cụ phù hợp OS.

**Câu 15.** `--release` tốt hơn `--target` đơn lẻ khi nào? — Khi cần kiểm cả language/API compatibility với release đích trong phạm vi javac hỗ trợ.

**Câu 16.** `--release 17` bảo đảm mọi behavior Java17? — Không; cần runtime17 integration tests/dependency checks.

**Câu 17.** JDK nào cũng hỗ trợ `--release 10`? — Không, xem supported releases của compiler thật; thử thành công trên JDK24 không phải cam kết cho mọi JDK.

**Câu 18.** Java run được nhưng javac không tồn tại có bất thường? — Không nhất thiết; có thể custom runtime image.

**Câu 19.** `ToolProvider.getSystemJavaCompiler()` true chứng minh shell javac cùng JDK? — Không; chỉ compiler API hiện diện trong runtime image.

**Câu 20.** `UnsupportedClassVersionError` xử lý thế nào? — So runtime version và class major, rebuild target phù hợp hoặc chạy runtime hỗ trợ, rồi test.

**Câu 21.** Maven `mvn -version` là compiler version? — Không, thường nói Maven process JVM; plugin/toolchains có thể chọn compiler khác.

**Câu 22.** Gradle `--version` là compiler target? — Không; kiểm Java toolchains, compiler task và artifact.

**Câu 23.** Docker build JDK21 và runtime JDK17 có thể đúng? — Có nếu target/dependencies tương thích và đã test runtime17.

**Câu 24.** Vì sao chỉ định `-classpath out` khi dùng javap? — Tránh đọc nhầm class cũ/khác từ classpath.

**Câu 25.** Có nên sửa major bytes thủ công để chạy trên JVM cũ? — Không; phải rebuild bằng target phù hợp.

**Câu 26.** `minor version 65535` có thể ám chỉ gì ở Java hiện đại? — Class phụ thuộc preview features, với ràng buộc runtime/release.

**Câu 27.** Tại sao cần ghi vendor/build? — Cùng feature release có thể khác update, security patches và implementation details.

**Câu 28.** Report toolchain đáng tin cần gì? — Tool versions, executable paths, compiler target, class major/minor và runtime test version.

## 23. Tài liệu chính thức, còn áp dụng

1. [Oracle Java SE 25 – The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `java -version` (stderr), `java --version` (stdout), Java launcher options.
2. [Oracle Java SE 25 – The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-version`/`--version`, `--release` và API compatibility.
3. [Oracle Java SE 25 – The javap Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): `-version`, `-verbose`, `-c` và classpath/inspection.
4. [Java SE 25 JVMS – Chapter 4, Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): magic, major/minor và class-file version compatibility.
5. [Java SE 17 JVMS – Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): bảng Java 10 major54 và Java 17 major61.
6. [Oracle Java SE 17 – java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): runtime launcher và version command trên Java17.
7. [Oracle Java SE 17 – javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `--source`, `--target`.
8. [Oracle Java SE 17 – javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): disassembler options còn áp dụng.
9. [Gradle User Guide – Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): phân biệt Gradle JVM với JavaCompiler/JavaLauncher.
10. [Apache Maven Compiler Plugin – Set Compiler Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): Maven property `maven.compiler.release`.
11. [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): chọn JDK toolchains.
12. [Oracle Java SE 17 – Runtime.Version API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): JVM runtime version/feature.
13. [Java SE 17 – ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): Java compiler availability trong runtime image.
14. [OpenJDK JEP 223 – New Version-String Scheme](https://openjdk.org/jeps/223): version strings từ Java 9.
15. [OpenJDK JEP 322 – Time-Based Release Versioning](https://openjdk.org/jeps/322): release versioning từ Java 10.
16. [Oracle Java SE 25 – JDK Tool Specifications](https://docs.oracle.com/en/java/javase/25/docs/specs/man/index.html): các công cụ JDK có vai trò riêng.

**Tóm tắt cuối:** Muốn xác định phiên bản các công cụ của một JDK, dùng **`java -version`/`java --version`**, **`javac -version`/`javac --version`** và **`javap -version`**. Để tìm chính xác công cụ nào đang được gọi, kiểm **PATH/JAVA_HOME/command resolution**; để xác minh target của artifact, đọc **`javap -verbose`** và so `major version`; để xác minh khả năng chạy thực, **test trên runtime đích**. JDK compiler mới hơn có thể tạo Java 10/17 bytecode khi `--release` còn hỗ trợ, nhưng điều đó không đổi version của `javac` hoặc `javap`. Với IDE, Maven, Gradle, Docker và CI, ba JDK tool versions của terminal **không tự đại diện** cho toàn bộ build/deploy toolchain.
