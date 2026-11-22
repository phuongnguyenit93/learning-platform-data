# Kiểm tra JDK và xác định đúng javac đang được gọi

Trong một máy có thể tồn tại nhiều JDK: một bản phục vụ dự án cũ, một bản mới cho dự án hiện tại và bản JDK do IDE hay công cụ build sử dụng. Lệnh `javac` mà terminal thực sự gọi có thể khác bản bạn nghĩ đang chọn; thậm chí `java` và `javac` có thể đến từ hai thư mục cài đặt khác nhau.

Mục tiêu của bài: **xác minh JDK đã có**, **biết chính xác phiên bản và tệp thực thi `javac` được shell chọn**, **đối chiếu `java` với `javac`**, sau đó **chạy thử một lần biên dịch**. Đây là bước chẩn đoán nền tảng trước khi tìm lỗi của mã nguồn hay classpath.

## 1. Phân biệt JDK, javac, java và môi trường shell

| Thành phần | Công dụng | Điều cần kiểm chứng |
| --- | --- | --- |
| JDK (Java Development Kit) | Bộ công cụ phát triển, gồm các công cụ như `javac` và `java` | JDK được cài ở đâu, là bản nào? |
| `javac` | Trình biên dịch từ mã nguồn `.java` sang `.class` | Lệnh `javac` đang gọi bản nào, qua đường dẫn nào? |
| `java` | Công cụ khởi chạy JVM và ứng dụng Java | Runtime đến từ JDK nào? Có khớp bản dự định không? |
| `JAVA_HOME` | Biến môi trường thường dùng để chỉ thư mục gốc một JDK | Giá trị có đúng không? Công cụ nào thực sự đọc biến này? |
| `PATH` | Danh sách thư mục được shell/hệ điều hành tìm khi chạy lệnh không kèm đường dẫn | Có nhiều thư mục `bin`? Thứ tự ưu tiên thế nào? |
| IDE/build tool | Có thể chọn JDK riêng hoặc Java toolchain khác với terminal | Cấu hình của công cụ có khác shell không? |

**Lưu ý cốt lõi:** `JAVA_HOME` không phải lệnh chọn `javac` của mọi shell. Thông thường, khi gõ `javac` không kèm đường dẫn, shell tìm ứng viên thông qua cơ chế phân giải lệnh của nó và `PATH`; alias, function, wrapper hay shim cũng có thể tham gia. Một số công cụ build/IDE đọc `JAVA_HOME` hoặc có thiết lập JDK riêng, vì vậy phải kiểm tra đúng nơi phát sinh lỗi.

Thư mục gốc JDK thường chứa `bin/java` và `bin/javac` (Windows: `bin\java.exe`, `bin\javac.exe`). `JAVA_HOME` trỏ đến **gốc JDK**, không trỏ đến `bin`, `java.exe` hay `javac.exe`.

## 2. Ba phép kiểm tra đầu tiên

Mở một terminal mới tại chính môi trường bạn định biên dịch rồi chạy:

```text
java -version
javac -version
javac --version
```

`javac --version` dùng được trên các JDK hiện đại (Java 9+); với JDK 17 trở lên, cả hai lựa chọn `-version` và `--version` đều dùng được. `java -version` cho biết phiên bản runtime của công cụ `java` tìm thấy, còn `javac -version` cho biết phiên bản trình biên dịch được tìm thấy. **Không dùng kết quả của một lệnh để suy ra kết quả của lệnh kia.**

Ví dụ **minh họa**, kết quả thực tế tùy máy:

```text
$ javac -version
javac 21.0.5
```

Một runtime OpenJDK có thể in thêm thông tin build, VM và vendor khi chạy `java -version`. Các bản cập nhật có thể khác số patch; không nên so từng ký tự với output minh họa.

Kết quả cần đối chiếu:

- Cả `java` và `javac` đều chạy thành công, và phiên bản phù hợp với dự án: tốt, nhưng **chưa đủ** để chắc chắn chúng thuộc cùng bản cài đặt.
- `java` chạy được nhưng `javac` không tìm thấy: có thể chỉ cài runtime, thiếu compiler, hoặc `PATH` trỏ tới một runtime/JDK không có `javac` trong đường dẫn hiện tại.
- `javac` cho ra phiên bản 21, `java` cho ra 17: có **mismatch giữa compiler và runtime**. Có thể chủ động hỗ trợ phiên bản cũ qua `--release`, nhưng trước hết cần xác minh đó có phải cấu hình mong muốn.
- `javac` trả về lỗi quyền truy cập, shim hoặc đường dẫn không tồn tại: phải truy tìm tệp thực thi trước khi đụng tới mã Java.

Các thông báo “command not found”, “not recognized”, “No such file or directory”, “Access is denied” có thể khác nhau theo hệ điều hành và shell. Đọc **nội dung và mã thoát (exit code)**, không chỉ nhìn tên lỗi.

## 3. Xác định chính xác javac trên Windows PowerShell

Trong **PowerShell**, dùng các lệnh:

```powershell
Get-Command javac
Get-Command javac -All
Get-Command java -All
where.exe javac
where.exe java
$env:JAVA_HOME
$env:Path -split ';'
```

Cách hiểu:

1. `Get-Command javac` cho biết **lệnh được PowerShell phân giải** trong phiên hiện tại, bao gồm loại lệnh: `Application`, `Alias`, `Function` hoặc loại khác. Đọc `Source`/`Definition` để xác định đích phù hợp với loại lệnh.
2. `Get-Command javac -All` liệt kê các ứng viên mà PowerShell phát hiện theo cách phân giải của nó. Dòng đầu thường thể hiện lựa chọn được ưu tiên; nếu có alias/function, phải xem nguồn của chúng.
3. `where.exe javac` tìm ứng viên thực thi theo đường dẫn tìm kiếm của Windows và liệt kê kết quả, rất hữu ích khi có nhiều bản cài. Nó **không thay thế** `Get-Command` nếu PowerShell có alias hoặc function cùng tên.
4. `$env:JAVA_HOME` xem cấu hình JDK trong *process terminal hiện tại*. `$env:Path -split ';'` cho thấy thứ tự các mục `PATH`.
5. Nếu `where.exe javac` in nhiều đường dẫn, đối chiếu đường dẫn đang được chọn với thư mục `bin` của JDK mong muốn. Hãy chú ý các thư mục shim, Java launcher trung gian hoặc công cụ quản lý phiên bản.

Để xem rõ đối tượng lệnh:

```powershell
Get-Command javac -All | Format-Table CommandType, Name, Source, Definition -AutoSize
Get-Command java -All | Format-Table CommandType, Name, Source, Definition -AutoSize
```

Đây là **lệnh PowerShell**. Trong PowerShell, `where` không có hậu tố `.exe` có thể là alias của `Where-Object`; vì vậy dùng rõ `where.exe` để chạy công cụ tìm đường dẫn của Windows.

### Windows Command Prompt (cmd.exe)

Nếu bạn làm việc trong **cmd**, cú pháp khác PowerShell:

```bat
where javac
where java
echo %JAVA_HOME%
echo %PATH%
javac -version
java -version
```

Đừng gõ `$env:JAVA_HOME` trong cmd, hoặc gõ `echo %JAVA_HOME%` trong PowerShell rồi suy diễn kết quả. Hai shell có cú pháp và phạm vi cấu hình khác nhau.

### Chạy compiler trực tiếp bằng đường dẫn tuyệt đối

Khi đã biết JDK muốn dùng, trong PowerShell:

```powershell
& "C:\Program Files\Java\jdk-21\bin\javac.exe" -version
& "C:\Program Files\Java\jdk-21\bin\java.exe" -version
```

Đường dẫn chỉ là **ví dụ**: thay bằng vị trí thật. `&` là call operator của PowerShell, cho phép thực thi file ở đường dẫn có khoảng trắng. Dấu ngoặc kép chỉ bao đường dẫn; chúng **không tự thực thi** chuỗi trong PowerShell. Trong cmd, đặt đường dẫn EXE trong dấu ngoặc kép rồi gọi trực tiếp.

So sánh phiên bản của cặp công cụ **gọi bằng đường dẫn tuyệt đối** với cặp công cụ **gọi bằng tên ngắn**. Nếu khác nhau, vấn đề nằm ở việc chọn lệnh của shell, không nằm trong chương trình Java.

## 4. Xác định javac trên Linux

Trong shell Bash/zsh (hoặc shell POSIX tương thích), bắt đầu bằng:

```bash
command -v javac
command -v java
type -a javac
type -a java
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH" | tr ':' '\n'
javac -version
java -version
```

- `command -v` cho biết shell phân giải tên lệnh như thế nào; nếu tên là alias/function, đầu ra không nhất thiết là đường dẫn tới EXE.
- `type -a` trong Bash và zsh hữu ích để nhìn các định nghĩa hoặc ứng viên có thể bị che bởi thứ tự `PATH`. Trên một số shell khác, tùy chọn `-a` có thể không tồn tại.
- `PATH` trên Linux/macOS phân cách thư mục bằng dấu hai chấm `:`.
- `JAVA_HOME` chỉ phản ánh giá trị trong shell hiện tại; giá trị rỗng không tự chứng minh JDK chưa cài.

Trên Linux có `readlink -f` (GNU/coreutils hoặc môi trường hỗ trợ), có thể truy vết một symlink:

```bash
readlink -f "$(command -v javac)"
readlink -f "$(command -v java)"
```

Chỉ dùng `readlink -f` khi `command -v` thực sự trả về **đường dẫn tệp**. Nếu nó trả về alias/function hay shell builtin, hãy xem `type -a` trước. Trên nhiều bản phân phối Linux, `/usr/bin/javac` có thể là symlink qua hệ thống quản lý `alternatives` tới JDK thực tế. Trên hệ điều hành không có `readlink -f`, dùng công cụ hoặc cú pháp tương ứng thay vì giả định lệnh luôn có sẵn.

Ví dụ **minh họa**, không phải kết quả cố định:

```text
/usr/bin/javac
/usr/lib/jvm/java-21-openjdk-amd64/bin/javac
```

Dòng đầu có thể là đường dẫn shell tìm được, dòng sau là đích sau khi phân giải liên kết. Tên thư mục phụ thuộc bản phân phối và kiến trúc.

## 5. Xác định javac trên macOS

Bắt đầu bằng các lệnh shell thông thường:

```bash
command -v javac
command -v java
type -a javac
type -a java
javac -version
java -version
echo "$JAVA_HOME"
```

macOS có công cụ hệ thống để nhận diện JDK cài đặt theo cơ chế của hệ điều hành:

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17 --exec javac -version
```

- `/usr/libexec/java_home -V` liệt kê các Java runtime/JDK mà công cụ macOS nhận biết, kèm phiên bản và đường dẫn; danh sách này **không phải bảo đảm bao gồm mọi bản Java** được cài qua mọi trình quản lý.
- `-v 17 --exec javac -version` yêu cầu chọn bản tương thích theo bộ chọn `17` của công cụ rồi chạy `javac`. Nó không sửa `PATH` cho mọi terminal.
- `/usr/bin/javac` trên macOS có thể là launcher/stub hệ thống, không phải file compiler nằm trong thư mục JDK đang dùng. Vì vậy `command -v javac` trả về `/usr/bin/javac` **chưa đủ** để biết JDK cuối cùng.

Nếu `java_home` không tìm được JDK mong muốn, kiểm tra cách bản JDK đó được cài và được công cụ quản lý JDK tích hợp trên macOS nhận diện. Không kết luận rằng `javac` đang dùng đúng phiên bản chỉ từ việc thấy một JDK trong thư mục ứng dụng.

## 6. JAVA_HOME và PATH: vì sao dễ chọn sai JDK?

Giả sử máy có hai thư mục JDK:

```text
C:\Java\jdk-17\bin\
C:\Java\jdk-21\bin\
```

Với một shell dùng `PATH` để tìm ứng dụng, nếu `C:\Java\jdk-17\bin` đứng trước `C:\Java\jdk-21\bin` và không có alias/shim khác can thiệp, gõ `javac` sẽ thường chọn bản trong thư mục đứng trước. Đổi `JAVA_HOME` sang JDK 21 mà **không cập nhật `PATH`** không buộc lệnh `javac` vừa gõ chuyển theo.

Tương tự trên Linux/macOS, ví dụ:

```text
/usr/local/jdk-17/bin:/usr/local/jdk-21/bin:/usr/bin
```

`PATH` được tìm theo thứ tự, song thực tế còn có alias, function, cơ chế cache lệnh của shell và các shim. Vì thế cần **xem cả tên lệnh, đường dẫn và phiên bản**.

### Đổi JDK chỉ trong PowerShell hiện tại

Khi thực sự cần thử một bản khác, có thể đặt biến cho **phiên shell đang mở**:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
Get-Command javac
javac -version
java -version
```

Thay đường dẫn mẫu bằng **gốc JDK thật**. Dòng cập nhật `Path` đặt `bin` của JDK lên đầu biến `PATH` trong phiên hiện tại; không chỉnh thiết lập toàn hệ thống. Nếu vẫn thấy alias/function được ưu tiên, xem lại `Get-Command -All`. Khi đóng terminal, các thay đổi phiên shell này thường không còn; shell mới nhận môi trường từ tiến trình cha/cấu hình hệ thống.

### Đổi JDK chỉ trong cmd hiện tại

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-21"
set "PATH=%JAVA_HOME%\bin;%PATH%"
where javac
javac -version
java -version
```

Dấu ngoặc kép của cú pháp `set "NAME=value"` bảo vệ giá trị khỏi khoảng trắng ở mép và không trở thành một phần của giá trị. Lệnh `set` chỉ áp dụng cho process cmd hiện tại và process con.

### Đổi JDK chỉ trong Bash/zsh hiện tại

```bash
export JAVA_HOME="/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"
hash -r
command -v javac
javac -version
java -version
```

`/opt/jdk-21` chỉ là ví dụ, thay bằng thư mục JDK có thật. `hash -r` xóa bảng nhớ đường dẫn của một số shell, giúp lần phân giải mới không dựa vào đường dẫn cũ đã cache. Trên zsh có thể dùng `rehash` nếu cần. Không lưu vĩnh viễn `PATH` trong file cấu hình shell trước khi bạn xác minh kết quả tạm thời.

**Quan trọng:** Những lệnh đổi môi trường trên đây là **các cách thay thế theo hệ điều hành/shell**, không chạy tất cả trên cùng máy. Đối với môi trường doanh nghiệp hoặc CI, nên quản lý phiên bản JDK qua toolchain và cấu hình được kiểm soát thay vì sửa `PATH` tùy tiện trong nhiều profile.

## 7. Cách xác minh không phụ thuộc PATH

Để loại bỏ nghi ngờ về thứ tự tìm kiếm, gọi trực tiếp công cụ trong `JAVA_HOME` và so với lệnh ngắn.

PowerShell:

```powershell
& "$env:JAVA_HOME\bin\javac.exe" -version
& "$env:JAVA_HOME\bin\java.exe" -version
javac -version
java -version
```

Bash/zsh:

```bash
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/java" -version
javac -version
java -version
```

Chỉ chạy các lệnh trên nếu `JAVA_HOME` đã được thiết lập đúng và tệp đó thực sự tồn tại. Đây là cách kiểm tra trực tiếp **hai nhóm đường dẫn**:

1. `$JAVA_HOME/bin/javac` (hoặc `$env:JAVA_HOME\bin\javac.exe`) — compiler trong JDK bạn chỉ định.
2. `javac` — compiler shell chọn từ alias/function/`PATH`/shim.

Nếu hai kết quả khác nhau, hãy kiểm tra `Get-Command -All` hoặc `type -a` và sửa đúng cơ chế chọn lệnh. Nếu hai kết quả cùng phiên bản, vẫn cần kiểm tra đường dẫn: **hai JDK riêng biệt có thể cùng một version string**.

### Không nhầm java.home của JVM với JAVA_HOME của shell

Lệnh sau in **cấu hình runtime Java** và có thể hỗ trợ phân tích:

```bash
java -XshowSettings:properties -version
```

Trong output, tìm thuộc tính `java.home`. Giá trị đó phản ánh vị trí runtime Java **đã khởi chạy** (thông thường là phần runtime của JDK), không phải tự động là biến môi trường `JAVA_HOME` và cũng không tự nói chính xác compiler `javac` nào được shell chọn. Output `-XshowSettings` có nhiều dòng, thứ tự/định dạng có thể khác nhau giữa phiên bản JVM.

Trên PowerShell hay cmd cũng có thể gọi lệnh `java -XshowSettings:properties -version` và tìm `java.home` trong output. Khi sao chép log, tránh công bố thông tin đường dẫn cá nhân hoặc thông tin nội bộ không cần thiết.

## 8. Thử biên dịch thật để chứng minh công cụ hoạt động

Phiên bản và đường dẫn đúng chỉ là bước đầu. Tạo file `CompilerSmoke.java` ở thư mục làm việc hiện tại với nội dung Java 17+ sau:

```java
public class CompilerSmoke {
    public static void main(String[] args) {
        System.out.println("javac works");
    }
}
```

Dùng compiler mà bạn vừa kiểm chứng; với lệnh ngắn:

```bash
javac -encoding UTF-8 -d out CompilerSmoke.java
java -cp out CompilerSmoke
```

Lệnh `javac` thành công sẽ tạo `out/CompilerSmoke.class`; từ JDK hiện đại, thư mục đích được tạo khi cần. Đây là ví dụ không dùng `package`. Lệnh `java` sẽ tải class từ thư mục `out` và in **stdout chính xác**:

```text
javac works
```

`javac` thường không in gì ra stdout nếu biên dịch thành công. Tệp Java phải được lưu tên đúng `CompilerSmoke.java` vì khai báo `public class CompilerSmoke`. Nếu chỉ chạy `java CompilerSmoke` mà không đặt `out` trong classpath, có thể gặp lỗi không tìm thấy lớp. Nếu có tệp class cũ từ lần chạy trước, hãy kiểm tra thời điểm sinh file và exit code của `javac` để không nhầm thành công của lần này với kết quả cũ.

Trên Windows PowerShell, có thể xác nhận file và chạy:

```powershell
Test-Path .\out\CompilerSmoke.class
java -cp out CompilerSmoke
```

Nếu class file có mặt, `Test-Path` trả `True`. Kết quả `False` cho biết tệp không ở vị trí kỳ vọng; rà lại working directory, tên file và lỗi biên dịch.

Trên Linux/macOS:

```bash
test -f out/CompilerSmoke.class
echo $?
java -cp out CompilerSmoke
```

`echo $?` ngay sau `test` là `0` khi file tồn tại, khác `0` khi không tồn tại. Không chèn lệnh khác trước khi kiểm tra `$?` nếu muốn đọc trạng thái của `test`.

### Muốn chắc chắn dùng cặp java/javac cùng JDK khi thử nghiệm

PowerShell:

```powershell
& "$env:JAVA_HOME\bin\javac.exe" -encoding UTF-8 -d out .\CompilerSmoke.java
& "$env:JAVA_HOME\bin\java.exe" -cp out CompilerSmoke
```

Bash/zsh:

```bash
"$JAVA_HOME/bin/javac" -encoding UTF-8 -d out CompilerSmoke.java
"$JAVA_HOME/bin/java" -cp out CompilerSmoke
```

Cả hai ví dụ yêu cầu `JAVA_HOME` trỏ đến JDK hợp lệ. Việc dùng **cùng gốc JDK** cho hai chương trình giúp tránh vô tình biên dịch bằng bản mới rồi chạy bằng bản cũ. Bản thân một lần smoke test thành công chưa kiểm chứng mọi thư viện hay API mà dự án lớn sẽ cần.

## 9. Khi java và javac khác phiên bản: xử lý thế nào?

Giả sử sau khi kiểm tra, bạn có:

```text
javac 21.0.5
java version "17.0.12" ...
```

Đây là **ví dụ mismatch**, không phải output chắc chắn trên máy bạn. Khi Java 21 biên dịch theo mặc định, class file có thể yêu cầu runtime Java 21, trong khi lệnh `java` đang chạy bằng Java 17. Lúc nạp class, JVM cũ có thể báo `UnsupportedClassVersionError`.

Nếu dự án thực sự cần chạy trên Java 17 mà compiler là JDK 21, một lựa chọn là:

```bash
javac --release 17 -encoding UTF-8 -d out CompilerSmoke.java
```

`--release 17` hướng trình biên dịch tới mức ngôn ngữ, bytecode và API Java SE của bản mục tiêu 17 được công cụ hỗ trợ. Nó không đảm bảo các **thư viện bên thứ ba**, native dependency hay cấu hình triển khai đều tương thích. `--release` khác việc chỉ đổi tên file hoặc đổi `JAVA_HOME`, và không thể nhắm tới một release mới hơn khả năng hỗ trợ của compiler đang dùng.

Nếu dự án yêu cầu JDK 21 ở cả build và runtime, hãy chọn JDK 21 cho cả hai, đối chiếu lại đường dẫn và phiên bản. Nếu dự án quy định build bằng 21 nhưng runtime bằng 17, xác minh thiết lập `--release`/toolchain một cách rõ ràng. **Phiên bản giống nhau là tín hiệu hữu ích, không phải bằng chứng duy nhất:** vendor, bản cập nhật, kiến trúc và cấu hình JDK cũng có thể quan trọng.

## 10. Máy có nhiều JDK và IDE hoặc build tool

Một số tình huống thường gặp:

- Bạn gõ `javac -version` trong terminal ra JDK 21, nhưng IDE hiển thị JDK 17 cho project: IDE có thể cấu hình SDK hoặc compiler riêng.
- `java -version` ở terminal là JDK 17, còn Gradle build dùng Java toolchain 21: Gradle có thể chạy bằng một JVM và giao nhiệm vụ biên dịch cho compiler từ JDK khác.
- Một trình quản lý SDK như SDKMAN!, jenv, asdf hoặc các shim khác đặt một executable/wrapper trước thư mục JDK trong `PATH`: cần xem công cụ quản lý đó đang chọn phiên bản gì tại thư mục hiện tại.
- Shell đã mở **trước khi** thay đổi môi trường: phiên cũ có thể giữ `PATH`/`JAVA_HOME` cũ. Đóng terminal, mở lại và kiểm tra để đối chiếu.
- CI chạy trong container hoặc runner riêng: JDK trên máy cá nhân không quyết định JDK trong job CI.

Để kiểm tra Java dùng để **chạy Gradle**, có thể dùng `./gradlew -version` trên Linux/macOS hoặc `.\gradlew.bat -version` trên PowerShell khi dự án có Gradle Wrapper. Tuy nhiên, phiên bản JVM hiển thị ở đó **không mặc nhiên xác định compiler của mọi tác vụ** nếu dự án dùng Java toolchains. Cần đối chiếu cấu hình toolchain, IDE SDK, môi trường runner và log tác vụ đúng mục tiêu.

Nếu đang giải quyết lỗi ở một nơi cụ thể, hãy chạy lệnh kiểm tra **trong đúng terminal/process context** của nơi đó. Tránh sửa cấu hình toàn hệ thống khi chỉ một project cần bản JDK khác.

## 11. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Khả năng | Cách kiểm tra tiếp |
| --- | --- | --- |
| `javac: command not found` hoặc “javac is not recognized” | Chưa cài JDK, hoặc `bin` không có trên `PATH` | Tìm JDK hợp lệ; kiểm tra `PATH` và gọi thẳng `bin/javac` |
| `java -version` có, `javac -version` lỗi | Runtime đã cài nhưng compiler không sẵn hoặc không được chọn | Kiểm tra thư mục JDK, `Get-Command`/`type -a` |
| `JAVA_HOME` đúng nhưng `javac` vẫn ra bản cũ | `PATH` ưu tiên bản khác, alias/shim/cache | Đối chiếu `javac` ngắn với đường dẫn tuyệt đối |
| `java` và `javac` khác phiên bản | Compiler và runtime được phân giải riêng | Tìm cả hai đường dẫn, chọn cặp phù hợp |
| Terminal mới đúng, terminal cũ sai | Biến môi trường được kế thừa khi tạo process, phiên cũ chưa cập nhật | Mở terminal mới; so sánh giá trị biến trong hai process |
| `/usr/bin/javac` hoặc shim không trỏ trực tiếp đến JDK | Symlink, wrapper, launcher hoặc alternatives | Truy vết symlink/launcher và đối chiếu version |
| IDE build sai dù terminal đúng | IDE/toolchain chỉ định JDK riêng | Xem Project SDK, Gradle/Maven runner và compiler settings |
| Biên dịch được nhưng JVM báo `UnsupportedClassVersionError` | Class file mới hơn runtime | Kiểm tra `java -version`, `javac -version`, `--release` |
| `Access denied` / `Permission denied` | Quyền thực thi hoặc chính sách hệ thống | Kiểm tra quyền và đường dẫn file thật |
| `Could not find or load main class` | Compile thành công nhưng chạy sai classpath/tên lớp | Kiểm tra `-d`, `-cp`, package, vị trí `.class` |

Không nên xử lý mọi lỗi bằng cách cài thêm JDK. Việc cần làm là xác định **lệnh nào được gọi, ở đâu, với phiên bản nào và bởi process nào**, rồi thay đổi tối thiểu đúng lớp cấu hình.

## 12. Quy trình chẩn đoán ngắn áp dụng được ngay

1. **Chạy hai lệnh phiên bản:** `java -version` và `javac -version` ngay trong terminal gặp lỗi.
2. **Liệt kê đường dẫn được chọn và các ứng viên:** Windows PowerShell `Get-Command javac -All`, `where.exe javac`; Linux/macOS `command -v javac`, `type -a javac`. Lặp lại cho `java`.
3. **Kiểm tra `JAVA_HOME` và `PATH`:** so với **gốc JDK cần dùng**; đừng giả định hai biến luôn đồng bộ.
4. **Chạy trực tiếp `bin/javac` và `bin/java` từ JDK đích:** nếu lệnh tuyệt đối đúng mà lệnh ngắn sai, tập trung vào alias/function/shim/`PATH`.
5. **Biên dịch `CompilerSmoke.java` và chạy từ `out`:** kiểm chứng compiler, thư mục output, classpath và runtime hoạt động cùng nhau.
6. **Đối chiếu cấu hình build/IDE/CI** nếu lỗi chỉ xảy ra bên ngoài terminal đang kiểm tra.
7. **Sau khi xác minh mới thay đổi cấu hình bền vững:** vị trí cài JDK, toolchain hoặc thứ tự `PATH` cần được điều chỉnh theo quy định của dự án.

### Tự kiểm tra

**1. Nếu `JAVA_HOME` trỏ JDK 21 nhưng `where.exe javac` cho thấy JDK 17 ở vị trí ưu tiên, có thể kết luận gì?**

Lệnh `javac` dạng ngắn có thể vẫn chạy JDK 17, trừ khi cơ chế phân giải lệnh khác can thiệp. Cần xác minh bằng `Get-Command javac` và `javac -version`.

**2. Nếu `javac -version` và `java -version` đều ghi 21, đã chứng minh hai công cụ cùng thư mục?**

Chưa. Hai bản cài riêng có thể cùng major/patch version. Hãy truy đường dẫn từng tệp thực thi.

**3. Vì sao `java.home` in từ JVM khác với `JAVA_HOME` trong shell?**

`java.home` là thuộc tính của runtime thực sự đang chạy, còn `JAVA_HOME` là biến môi trường. Hai giá trị có thể trỏ khác nhau; `java.home` không tự nhận diện bản `javac`.

**4. Vì sao lỗi chỉ xuất hiện trong Gradle dù gõ `javac` ở terminal vẫn đúng?**

Gradle có thể chạy JVM khác hoặc chọn compiler qua toolchain. Hãy kiểm tra chính cấu hình và môi trường của tác vụ Gradle.

**5. Vì sao `javac --release 17` hữu ích khi build bằng JDK 21 để chạy trên Java 17?**

Nó yêu cầu dùng mức ngôn ngữ, API nền tảng và bytecode tương thích với Java 17 mà compiler hỗ trợ. Nó không giải quyết thư viện ngoài không tương thích hoặc cấu hình runtime thiếu.

## Tài liệu tham khảo

- [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): tùy chọn trình biên dịch như `-version`, `-d`, `--release`.
- [Oracle JDK 21 — Installation on macOS](https://docs.oracle.com/en/java/javase/21/install/installation-jdk-macos.html): cách dùng `java_home` để xác định và chọn JDK.
- [Microsoft Learn — Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java/): cấu hình, kiểm tra `JAVA_HOME` và các công cụ Java trên Windows.

Kiểm tra Java toolchain đáng tin cậy phải có **phiên bản**, **đường dẫn thực thi thực tế** và **một lần biên dịch/chạy thành công**, tất cả trong đúng môi trường đang gặp vấn đề.