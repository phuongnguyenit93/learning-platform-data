# Thiết lập `JAVA_HOME`, `PATH` và kiểm tra `java`, `javac` với Java 17

Để thực hành lập trình Java 17 trên máy cá nhân, bạn cần **JDK 17** và một terminal có thể tìm đúng bộ công cụ của JDK đó. Bài này hướng dẫn cấu hình môi trường trên **Windows, macOS và Linux**, sau đó tự kiểm tra bằng cả lệnh `java` (chạy chương trình) lẫn `javac` (biên dịch mã nguồn).

Kết quả mong muốn là:

- `JAVA_HOME` trỏ tới **thư mục gốc của JDK 17**.
- `PATH` cho phép terminal tìm thấy `java` và `javac` từ JDK mong muốn.
- `java --version` và `javac --version` đều báo phiên bản **17**.
- Bạn biên dịch và chạy được một tệp `.java` đơn giản.

> **Phạm vi:** Các ví dụ dùng Java 17. Nếu máy có nhiều JDK, hãy chọn bản **17.x** phù hợp thay vì mặc định dùng bản Java mới nhất. Đường dẫn cài đặt phụ thuộc hệ điều hành, nhà phân phối JDK và bản cập nhật; hãy dùng **đường dẫn thực tế trên máy** thay cho đường dẫn minh họa.

## 1. Hiểu đúng JDK, `JAVA_HOME` và `PATH`

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **JDK (Java Development Kit)** | Bộ công cụ phát triển, bao gồm chương trình chạy `java` và trình biên dịch `javac`. | JDK 17 của Eclipse Temurin, Oracle hoặc nhà phân phối tương thích khác. |
| **`JAVA_HOME`** | Biến môi trường chỉ tới **thư mục gốc** của JDK. Nhiều công cụ xây dựng dự án đọc biến này để tìm Java. | `C:\Program Files\Java\jdk-17` |
| **`PATH`** (Windows có thể hiển thị là `Path`) | Danh sách thư mục mà terminal tìm kiếm khi bạn gõ tên lệnh. | Mục `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên macOS/Linux. |
| **`java`** | Lệnh khởi chạy ứng dụng Java (JVM). | `java --version` |
| **`javac`** | Trình biên dịch chuyển tệp `.java` thành tệp `.class`. | `javac --version` |

Giả sử JDK được cài tại thư mục `jdk-17`:

```text
jdk-17/                   <-- JAVA_HOME trỏ vào đây
├── bin/
│   ├── java              <-- Windows: java.exe
│   └── javac             <-- Windows: javac.exe
├── conf/
├── legal/
└── lib/
```

**Không thêm `bin` vào giá trị `JAVA_HOME`**: nếu đặt `JAVA_HOME` thành `.../jdk-17/bin`, các công cụ ghép tiếp `/bin` có thể tìm nhầm thành `.../jdk-17/bin/bin`. Ngược lại, `PATH` cần chứa **thư mục `bin`** để terminal gọi được `java`, `javac` mà không ghi đường dẫn đầy đủ.

`java` và `javac` được chọn theo đường dẫn lệnh mà hệ điều hành phân giải (thường thông qua `PATH`), vì vậy **đặt `JAVA_HOME` đúng chưa bảo đảm hai lệnh sẽ dùng JDK đó**. Hai cấu hình phải được kiểm tra cùng nhau.

## 2. Xác định thư mục cài JDK 17

Trước khi chỉnh biến môi trường, hãy cài một **JDK 17** phù hợp với hệ điều hành và kiến trúc CPU (x64 hoặc ARM64 nếu có). Có thể dùng bản JDK 17 từ [Eclipse Adoptium](https://adoptium.net/temurin/releases/?version=17), [Oracle](https://www.oracle.com/java/technologies/downloads/archive/) hoặc nguồn phân phối JDK được dự án cho phép. Chỉ cài môi trường chạy Java mà thiếu bộ biên dịch sẽ không đáp ứng yêu cầu của bài thực hành.

**Windows:** Mở thư mục JDK bằng File Explorer, chẳng hạn `C:\Program Files\Java\jdk-17`. Xác nhận thư mục đó chứa `bin\java.exe` và `bin\javac.exe`. Tên thực tế có thể kèm số bản vá hoặc tên nhà phân phối, ví dụ thư mục của Eclipse Temurin.

**macOS:** Sau khi cài JDK 17, mở Terminal và chạy:

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
```

Lệnh đầu liệt kê các JDK mà macOS nhận diện; lệnh sau trả về thư mục gốc của một JDK phiên bản 17, thường có dạng `.../Contents/Home`. Nếu lệnh sau báo không tìm thấy JDK phù hợp, hãy kiểm tra hoặc cài lại JDK 17 trước khi cấu hình.

**Linux:** Đường dẫn phụ thuộc bản phân phối và cách cài. Chẳng hạn, một máy Ubuntu/Debian có thể cài JDK dưới `/usr/lib/jvm/java-17-openjdk-amd64`. Nếu `javac` đã có trong `PATH`, có thể tìm tệp thực mà liên kết tượng trưng trỏ tới:

```bash
readlink -f "$(command -v javac)"
```

Ví dụ kết quả là `/usr/lib/jvm/java-17-openjdk-amd64/bin/javac` thì thư mục gốc tương ứng là `/usr/lib/jvm/java-17-openjdk-amd64`. Nếu `javac` chưa có, hãy kiểm tra gói JDK 17 đã cài bằng trình quản lý gói của hệ điều hành; đừng suy đoán một đường dẫn không tồn tại.

## 3. Cấu hình trên Windows 10/11

### 3.1. Lưu cấu hình cho các terminal mở sau này

1. Nhấn **Start**, tìm **Edit the system environment variables** (hoặc **Chỉnh sửa biến môi trường hệ thống**), mở hộp thoại **System Properties** rồi chọn **Environment Variables…**.
2. Chọn phạm vi phù hợp: **User variables** chỉ áp dụng cho tài khoản của bạn; **System variables** áp dụng rộng hơn và thường cần quyền quản trị khi sửa. Ưu tiên **User variables** nếu chỉ thực hành trên tài khoản cá nhân.
3. Tạo hoặc sửa biến `JAVA_HOME`, đặt giá trị bằng **đường dẫn thực tế đến thư mục gốc JDK 17**, chẳng hạn:

   ```text
   JAVA_HOME = C:\Program Files\Java\jdk-17
   ```

   Trong ô giá trị của giao diện Windows, nhập đường dẫn thông thường, **không thêm dấu nháy kép bao quanh** và **không nối `\bin`**.

4. Trong danh sách biến **cùng phạm vi**, chọn `Path` → **Edit** → **New** và thêm một mục:

   ```text
   %JAVA_HOME%\bin
   ```

5. Nếu có đường dẫn JDK khác trong `Path`, sắp xếp để JDK 17 mong muốn được ưu tiên khi tìm lệnh. Chú ý thứ tự `Path` có hiệu lực có thể gồm cả mục từ biến hệ thống và biến người dùng; nếu phiên bản khác vẫn được chọn, dùng các lệnh chẩn đoán ở mục 6 để tìm mục đứng trước.
6. Chọn **OK** để lưu, **đóng terminal cũ và mở cửa sổ PowerShell/CMD mới**. Tiến trình đang chạy thường giữ bản sao biến môi trường từ lúc được khởi tạo.

### 3.2. Thử thay đổi tạm thời trong một cửa sổ PowerShell

Nếu muốn kiểm tra nhanh mà chưa sửa cấu hình lâu dài:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$($env:JAVA_HOME)\bin;$env:Path"

$env:JAVA_HOME
java --version
javac --version
```

Trong **Command Prompt (CMD)**, cú pháp tương đương cho phiên hiện tại là:

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-17"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo %JAVA_HOME%
java --version
javac --version
```

Hai đoạn trên chỉ thay đổi môi trường của cửa sổ terminal hiện tại và các tiến trình con của nó. Muốn giữ cấu hình khi mở terminal mới, làm theo **mục 3.1**.

## 4. Cấu hình trên macOS

macOS cung cấp `/usr/libexec/java_home` để tìm JDK đã cài. Với **zsh** (shell mặc định của nhiều bản macOS hiện nay), mở Terminal và chạy:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

printf '%s\n' "$JAVA_HOME"
java --version
javac --version
```

Để các phiên **zsh tương tác** sau cũng dùng JDK 17, thêm chính hai dòng `export` vào cuối tệp `~/.zshrc` rồi nạp lại:

```bash
source ~/.zshrc
```

Nếu bạn dùng **bash** thay cho zsh, hãy đặt hai dòng `export` vào tệp khởi tạo bash phù hợp với cách bạn mở shell (thường là `~/.bash_profile` cho login shell trên macOS) và mở terminal mới.

> **Lưu ý:** Đường dẫn JDK trên macOS thường kết thúc bằng `/Contents/Home`; không lấy thư mục `.jdk` bao ngoài làm `JAVA_HOME`. Nếu nhiều bản JDK cùng tồn tại, `/usr/libexec/java_home -v 17` giúp chọn nhánh phiên bản 17. Một IDE mở từ giao diện đồ họa có thể sử dụng cấu hình JDK riêng, nên cần kiểm tra thêm **Project SDK/JDK** trong IDE nếu IDE báo phiên bản khác.

## 5. Cấu hình trên Linux

Giả sử đã xác nhận JDK 17 có tại `/usr/lib/jvm/java-17-openjdk-amd64` trên máy Ubuntu/Debian. Trong **bash**, chạy:

```bash
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"

printf '%s\n' "$JAVA_HOME"
java --version
javac --version
```

Thay giá trị `JAVA_HOME` bằng thư mục JDK 17 **thực tế** nếu đường dẫn khác. Với bash tương tác, thêm hai dòng `export` vào `~/.bashrc` và nạp lại bằng:

```bash
source ~/.bashrc
```

Nếu sử dụng zsh, cấu hình tương tự trong `~/.zshrc`. Các shell hoặc phiên đăng nhập khác có thể đọc tệp cấu hình khác; hãy mở một terminal mới theo cách bạn thường sử dụng và kiểm tra lại.

Hệ thống Linux có thể đã quản lý `java` và `javac` qua liên kết hoặc cơ chế lựa chọn phiên bản của bản phân phối. Khi đó, thêm `$JAVA_HOME/bin` ở **đầu** `PATH` trong phiên thực hành giúp ưu tiên JDK được chỉ định, còn cấu hình mặc định toàn hệ thống có thể được quản lý riêng. Không chỉnh hoặc xóa liên kết hệ thống chỉ để làm xong bài học này.

## 6. Kiểm tra môi trường sau khi thiết lập

### 6.1. Kiểm tra hai phiên bản quan trọng

Mở **terminal mới** và chạy hai lệnh dưới đây (dùng trên cả ba hệ điều hành):

```text
java --version
javac --version
```

Ví dụ kết quả phù hợp với Java 17:

```text
openjdk 17.0.x ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...

javac 17.0.x
```

Các dòng mô tả, số bản vá và tên nhà phân phối có thể khác. Điều cần kiểm tra là **cả `java` lẫn `javac` đều thuộc nhánh 17**. Dấu `x` ở ví dụ là ký hiệu minh họa, không phải chuỗi đầu ra thực tế. Bạn cũng có thể dùng cú pháp `java -version` và `javac -version`, vẫn hoạt động trên JDK 17.

### 6.2. Kiểm tra `JAVA_HOME` và tệp thực thi

**PowerShell (Windows):**

```powershell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
Get-Command java -All | Select-Object -ExpandProperty Source
Get-Command javac -All | Select-Object -ExpandProperty Source
```

Hai lệnh `Test-Path` cần trả về `True`. `Get-Command ... -All` giúp nhìn thấy các vị trí lệnh có thể được chọn; mục đầu tiên thường là lệnh PowerShell sẽ chạy.

**CMD (Windows):**

```bat
echo %JAVA_HOME%
where java
where javac
```

Trong PowerShell, hãy dùng `where.exe java` nếu muốn gọi trực tiếp công cụ `where` của Windows; tên `where` không kèm `.exe` có thể được hiểu là lệnh khác của PowerShell.

**macOS/Linux (bash hoặc zsh):**

```bash
printf '%s\n' "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo "java: OK"
test -x "$JAVA_HOME/bin/javac" && echo "javac: OK"
command -v java
command -v javac
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
```

Hai phép thử `test -x` kiểm tra tệp thực thi trong JDK đã chọn. `command -v` cho biết tên lệnh đang được shell phân giải tới đâu; trên một số hệ điều hành, kết quả có thể là liên kết hoặc trình trung gian thay vì đường dẫn JDK trực tiếp. Vì vậy, hãy so sánh thêm phiên bản khi gọi lệnh thông qua `PATH` với phiên bản khi gọi trực tiếp `"$JAVA_HOME/bin/java"` và `"$JAVA_HOME/bin/javac"`.

### 6.3. Biên dịch và chạy chương trình đầu tiên

Tạo một thư mục thực hành, mở terminal **tại thư mục ấy**, rồi tạo file `HelloJava17.java` có nội dung:

```java
public class HelloJava17 {
    public static void main(String[] args) {
        System.out.println("Đang chạy Java " + Runtime.version().feature());
    }
}
```

Biên dịch và chạy (PowerShell, CMD, bash và zsh dùng cùng cú pháp):

```text
javac HelloJava17.java
java -cp . HelloJava17
```

Kết quả mong đợi:

```text
Đang chạy Java 17
```

Lệnh đầu tạo tệp `HelloJava17.class` nếu biên dịch thành công. Lệnh sau chạy lớp đã biên dịch, với `-cp .` chỉ thư mục hiện tại làm classpath. **Không thêm `.class` vào tên lớp khi chạy**. Nếu `javac` thành công nhưng `java` báo lỗi phiên bản tệp lớp, hãy kiểm tra xem hai lệnh có đang trỏ đến các phiên bản JDK khác nhau không.

## 7. Xử lý các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `java` hoặc `javac` không được nhận diện là lệnh | `PATH` chưa chứa thư mục `bin` thích hợp hoặc terminal chưa được mở lại. | Kiểm tra `JAVA_HOME`, mục `PATH` và mở terminal mới; trên Windows dùng `where.exe`, trên macOS/Linux dùng `command -v`. |
| `java` chạy được nhưng `javac` không có | Đang dùng môi trường chỉ có công cụ chạy, cài đặt JDK chưa đầy đủ hoặc `PATH` trỏ sang nơi khác. | Xác nhận có tệp `JAVA_HOME/bin/javac` (`javac.exe` trên Windows), cài đúng **JDK 17** và chỉnh lại đường dẫn lệnh. |
| `java --version` báo 21/25 hoặc phiên bản khác, dù `JAVA_HOME` là JDK 17 | Một thư mục Java khác đứng trước trong `PATH` hoặc shell/IDE dùng cơ chế chọn JDK riêng. | Xem thứ tự đường dẫn và đường dẫn lệnh thực tế, đưa `JAVA_HOME/bin` vào vị trí ưu tiên; kiểm tra JDK được IDE chọn nếu thao tác trong IDE. |
| `java` là 17 nhưng `javac` khác 17 | Hai lệnh đang được phân giải từ hai thư mục JDK khác nhau. | Kiểm tra cả **hai** đường dẫn lệnh; bảo đảm JDK 17 cung cấp cả `java` và `javac`. |
| Công cụ báo `JAVA_HOME` không hợp lệ | `JAVA_HOME` trỏ nhầm vào `bin`, vào thư mục JDK không tồn tại hoặc vào thư mục `.jdk` thay vì `Contents/Home` trên macOS. | Trỏ tới **thư mục gốc** thực tế chứa `bin/java` và `bin/javac`. |
| Vừa sửa biến môi trường nhưng terminal vẫn thấy giá trị cũ | Tiến trình terminal đã được mở trước thời điểm cấu hình thay đổi. | Đóng và mở lại terminal; nếu terminal chạy bên trong IDE, khởi động lại cửa sổ IDE khi cần. |
| Chương trình biên dịch được nhưng không chạy hoặc báo `UnsupportedClassVersionError` | Java dùng để chạy cũ hơn Java dùng để biên dịch, hoặc classpath/tên lớp chưa đúng. | So sánh phiên bản `java`, `javac`; chạy đúng `java -cp . TenLop` tại thư mục chứa `.class`. |

**Một điểm dễ nhầm:** `JAVA_HOME` là biến môi trường theo quy ước mà nhiều công cụ phát triển sử dụng; riêng việc gõ `java` trong terminal chủ yếu dựa vào cơ chế tìm lệnh của shell và `PATH`. Vì vậy, đọc `JAVA_HOME` thôi **chưa đủ** để khẳng định cấu hình đã đúng.

## 8. Tự xác nhận hoàn thành

Trước khi chuyển sang bài Java 17 tiếp theo, hãy tự trả lời được bốn câu hỏi:

1. `JAVA_HOME` đang trỏ tới thư mục JDK 17 nào? Trong thư mục đó có `bin/java` và `bin/javac` không?
2. `PATH` có cho phép tìm được hai lệnh từ đúng JDK không? Nếu có nhiều JDK, đường dẫn nào đang được ưu tiên?
3. `java --version` và `javac --version` có cùng thuộc nhánh **17** không?
4. `javac HelloJava17.java` và `java -cp . HelloJava17` có chạy thành công, in `Đang chạy Java 17` không?

Nếu cả bốn đều đạt, máy đã có môi trường terminal sẵn sàng cho các bài thực hành Java 17.

### Tài liệu chính thức để đối chiếu

- [Oracle JDK 17 — cài đặt trên Windows](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-microsoft-windows-platforms.html)
- [Oracle JDK 17 — cài đặt trên macOS](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-macos.html)
- [Microsoft Learn — thiết lập Java trên Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java/)
- [Microsoft Learn — PowerShell và biến môi trường](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_Environment_Variables)
- [Eclipse Adoptium — cài đặt Eclipse Temurin](https://adoptium.net/installation/)
