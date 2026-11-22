# Kiểm tra phiên bản `java` và `javac`

> **Module:** Java core — language-basics  
> **Mục:** Công cụ và thực thi  
> **Mục tiêu:** Dùng terminal xác định đúng phiên bản **Java runtime đang chạy** và **trình biên dịch Java đang được gọi**, tìm nguyên nhân khi chúng khác nhau, kiểm tra khả năng chạy của file `.class` và biết khi nào dùng `javac --release`.

## 1. Hai lệnh giống tên nhưng khác chức năng

Khi học Java, bạn thường cần hai chương trình dòng lệnh:

- **`java`:** Java launcher, khởi động môi trường thực thi để chạy chương trình Java. Phiên bản được hiển thị bởi `java -version` cho biết launcher/runtime mà terminal hiện đang gọi.
- **`javac`:** Trình biên dịch trong **JDK**, chuyển mã nguồn Java (`.java`) thành bytecode (`.class`). Phiên bản trong `javac -version` cho biết compiler đang được gọi.

Chữ **JDK** (*Java Development Kit*) chỉ bộ công cụ phát triển, thông thường chứa **cả** `java` và `javac`. Máy chỉ có runtime để chạy ứng dụng có thể có lệnh `java` nhưng không có `javac`.

| Câu hỏi | Kiểm tra bằng | Ý nghĩa |
| --- | --- | --- |
| Terminal đang khởi động phiên bản Java nào? | `java -version` | Phiên bản launcher/runtime được tìm thấy qua môi trường hiện hành |
| Terminal đang chọn compiler Java nào? | `javac -version` | Phiên bản `javac` đang được tìm thấy |
| Có thể biên dịch `Hello.java` không? | `javac Hello.java` | Kiểm tra thực tế có compiler và mã nguồn hợp lệ |
| Có thể chạy `Hello.class` không? | `java Hello` | Kiểm tra JVM/runtime cùng classpath và entry point phù hợp |

**Lưu ý:** `java -version` **không** cho biết file `.class` được biên dịch bằng compiler nào. Ngược lại, `javac -version` **không** chứng minh máy sẽ dùng cùng JDK đó khi bạn gõ `java`. Hai lệnh có thể đến từ hai thư mục cài đặt khác nhau.

## 2. Chạy kiểm tra phiên bản ngay trên terminal

Mở Terminal (macOS/Linux), Command Prompt hoặc PowerShell (Windows), lần lượt chạy:

~~~bash
java -version
javac -version
~~~

Ví dụ minh họa **một môi trường JDK 17**, không phải kết quả cố định của mọi máy:

~~~text
openjdk version "17.0.x" ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...
javac 17.0.x
~~~

Trong kết quả thực tế, các dấu `...` và `x` được thay bằng thông tin phiên bản/build/vendor cụ thể. Bạn có thể thấy tên bản phân phối như Oracle, Eclipse Temurin, Microsoft, Amazon Corretto hoặc một bản dựng OpenJDK khác.

Cách đọc:

1. Tìm **phiên bản tính năng chính** (*feature version*): ví dụ `17` trong `17.0.x` hoặc `21` trong `21.0.x`.
2. Các phần còn lại thường cho biết cập nhật bảo trì và build. Hai máy cùng “Java 17” có thể có các patch/build khác nhau.
3. Ghi nhận **cả hai dòng kiểm tra**. Nếu chúng khác nhau, xác định nguyên nhân thay vì giả định Java đã hỏng.
4. Không suy ra bản mới nhất hoặc tình trạng bảo mật chỉ từ số phiên bản lớn: chính sách hỗ trợ/cập nhật tùy nhà cung cấp và thời điểm.

### `-version` hay `--version`?

Với Java hiện đại, có thể sử dụng:

~~~bash
java --version
javac --version
~~~

`--version` là cú pháp thông dụng từ **Java 9 trở lên**. Để kiểm tra trên cả nhiều cài đặt cũ, đặc biệt Java 8, `-version` là lựa chọn quen thuộc và tương thích hơn. Đừng vội kết luận “không có Java” nếu một bản cũ không hiểu `--version`: thử `-version`.

Với các bản Java 8, tên phiên bản đôi khi được in theo dạng `1.8.0_...`. **Java 8 ≈ 1.8**, không phải Java 1 theo cách gọi phiên bản hiện đại.

## 3. Đọc kết quả đúng: ví dụ ba tình huống

| `java -version` | `javac -version` | Kết luận bước đầu |
| --- | --- | --- |
| `17.0.x` | `17.0.x` | Runtime và compiler cùng dòng phiên bản 17; vẫn nên kiểm tra đường dẫn nếu có nhiều JDK |
| `11.0.x` | `17.0.x` | Compiler có thể tạo bytecode mới hơn JVM 11 hiểu được, trừ khi cấu hình target phù hợp |
| Có phiên bản, chạy được | “command not found”/“not recognized” | Có runtime được tìm thấy, nhưng `javac` không tìm được qua terminal hiện tại |

**Không bắt buộc** mọi hệ thống có cả hai số phiên bản giống hệt đến từng bản vá. Một compiler mới có thể được cấu hình tạo chương trình cho runtime cũ; tuy nhiên phải kiểm soát **phiên bản bytecode, API chuẩn và thư viện phụ thuộc**.

Ngược lại, `java` và `javac` cùng báo “17” **chưa đủ** để chứng minh chúng nằm trong một thư mục JDK. Ví dụ một lệnh có thể là alias, wrapper hoặc shim trỏ sang cài đặt khác. Đó là lúc cần xem **đường dẫn thực tế**.

## 4. Xác định terminal đang tìm `java` và `javac` ở đâu

### Windows — PowerShell

~~~powershell
where.exe java
where.exe javac
Get-Command java -All
Get-Command javac -All
$env:JAVA_HOME
~~~

- `where.exe` cho biết những executable trùng tên được tìm thấy trên `PATH` theo cơ chế tìm kiếm của Windows.
- `Get-Command ... -All` hữu ích trong PowerShell vì còn có thể phát hiện alias/function/command được PowerShell ưu tiên.
- `$env:JAVA_HOME` in giá trị biến môi trường trong **phiên PowerShell hiện tại** nếu có.

**Phải dùng `where.exe`**, không chỉ `where` trong PowerShell: `where` có thể là alias của `Where-Object`, không phải chương trình dò đường dẫn.

### macOS / Linux — shell

~~~bash
command -v java
command -v javac
type -a java
type -a javac
echo "$JAVA_HOME"
~~~

`command -v` cho thấy command nào được shell phân giải; `type -a` (với Bash và nhiều shell phổ biến) có thể liệt kê nhiều kết quả/alias/function.

Tham khảo thêm tùy hệ điều hành:

~~~bash
# Linux có công cụ readlink hỗ trợ -f:
readlink -f "$(command -v java)"
~~~

~~~bash
# macOS: liệt kê một số cài đặt JDK mà java_home biết:
 /usr/libexec/java_home -V
~~~

Lệnh macOS trên có **một khoảng trắng đầu dòng không cần thiết**; khi gõ hãy dùng `/usr/libexec/java_home -V`. `readlink -f` không phải tùy chọn portable trên mọi phiên bản macOS, vì vậy không áp dụng máy móc lệnh Linux.

### Vì sao các đường dẫn có thể không giống bạn nghĩ?

Giả sử máy cài JDK 11 và JDK 17. Khi gõ `java`, hệ điều hành/shell tìm lệnh theo môi trường hiện tại (thường là thứ tự trong `PATH`), không tự chọn bản JDK phù hợp với mã nguồn bạn định chạy.

Ngoài ra:

- IDE có thể được cấu hình sử dụng JDK khác với terminal.
- Maven/Gradle có thể được cấu hình JDK/toolchain riêng; các lệnh terminal trên chỉ mô tả môi trường bạn vừa kiểm tra, **không tự chứng minh mọi build tool dùng cùng JDK**.
- Trình khởi chạy qua wrapper, alias hay executable manager có thể chọn Java theo cấu hình riêng.
- Chạy chương trình trong container, CI hoặc SSH là **một môi trường khác** với terminal trên máy cá nhân.

## 5. `JAVA_HOME`, `PATH` và phiên bản Java: ba điều khác nhau

| Thành phần | Vai trò | Điều không nên giả định |
| --- | --- | --- |
| `JAVA_HOME` | Biến môi trường thường trỏ tới thư mục JDK cho build tool và script | Không bảo đảm lệnh `java` trong terminal đang dùng đúng thư mục ấy |
| `PATH` | Danh sách vị trí tìm executable khi gõ tên lệnh | Không bảo đảm chỉ có một bản Java hoặc không có wrapper |
| `java.home` (thuộc tính Java runtime) | Thư mục runtime của **tiến trình Java thực sự đang chạy** | Không nhất thiết bằng giá trị `JAVA_HOME` hoặc vị trí JDK dùng để biên dịch |

Một cách điều chỉnh **tạm thời trong phiên terminal hiện tại**:

**Windows PowerShell (đường dẫn chỉ là ví dụ, hãy thay bằng JDK thật):**

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
~~~

**macOS/Linux, Bash hoặc shell tương tự:**

~~~bash
export JAVA_HOME="/duong-dan/toi/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
~~~

Các lệnh này **không cài Java**, chỉ thay đổi cách phiên shell hiện tại tìm công cụ. Đừng sao chép đường dẫn ví dụ nếu thư mục ấy không tồn tại. Trên một số shell có cache đường dẫn command, có thể cần mở terminal mới hoặc chạy `hash -r` (Bash) sau khi đổi `PATH`.

**Quy tắc chẩn đoán:** kiểm tra phiên bản → kiểm tra đường dẫn → kiểm tra `JAVA_HOME` và cấu hình build tool. Không nên chỉnh sửa biến môi trường toàn hệ thống trước khi biết lỗi nằm ở đâu.

## 6. Ví dụ Java chạy được: xác nhận phiên bản từ bên trong chương trình

Lệnh `java -version` phản ánh Java mà terminal gọi. Ta cũng có thể hỏi **chính chương trình đang chạy** về runtime của nó.

Tạo tệp **VersionEnvironmentDemo.java**:

~~~java
public class VersionEnvironmentDemo {
    public static void main(String[] args) {
        System.out.println("Java version : "
                + System.getProperty("java.version"));
        System.out.println("Runtime name : "
                + System.getProperty("java.runtime.name"));
        System.out.println("Java vendor  : "
                + System.getProperty("java.vendor"));
        System.out.println("VM name      : "
                + System.getProperty("java.vm.name"));
        System.out.println("Runtime home : "
                + System.getProperty("java.home"));
        System.out.println("Feature      : "
                + Runtime.version().feature());
    }
}
~~~

Đây là mã **Java 9+** vì có `Runtime.version()`; để học trên môi trường phổ biến, hãy dùng **JDK 11 hoặc 17 trở lên**.

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac VersionEnvironmentDemo.java
java VersionEnvironmentDemo
~~~

Đầu ra minh họa:

~~~text
Java version : 17.0.x
Runtime name : OpenJDK Runtime Environment
Java vendor  : <vendor của runtime>
VM name      : OpenJDK 64-Bit Server VM
Runtime home : <đường dẫn runtime hiện tại>
Feature      : 17
~~~

Giá trị thực tế tùy môi trường; không phải mọi JVM đều in đúng tên ví dụ trên. Nếu chạy trong IDE, hãy so sánh đầu ra của ví dụ **ở terminal** và **trong IDE** để kiểm tra chúng có chọn runtime khác nhau không.

Điều quan trọng:

- `System.getProperty("java.version")` và `Runtime.version().feature()` đo runtime **đang thực thi mã**.
- `java.home` đo vị trí runtime đang dùng **bên trong tiến trình**, không phải vị trí JDK chắc chắn đã chạy `javac`.
- Chương trình không tự biết chính xác compiler `javac` nào đã tạo file class; muốn biết bạn đã gọi compiler nào cần xem lệnh build và cấu hình của nó.

### Điều gì xảy ra nếu chỉ có `java` mà không có `javac`?

Nếu `java -version` thành công nhưng `javac -version` báo không tìm thấy lệnh, có thể máy chỉ có runtime, hoặc compiler không nằm trên `PATH`. Khi cần học hoặc build từ `.java`, hãy cài/chọn một **JDK** tương thích, rồi xác minh lại cả hai lệnh.

Không sử dụng thông báo thành công của `java -version` để khẳng định chắc chắn đã có toàn bộ công cụ phát triển.

## 7. Phiên bản compiler khác với phiên bản class file

Đây là nguyên nhân quan trọng nhất của lỗi “Java trên máy chạy quá cũ”.

Khi biên dịch, `javac` tạo bytecode `.class` theo một **class-file version**. Runtime Java cũ hơn có thể không đọc được định dạng mới.

| Mức Java mục tiêu | Class-file major version thường gặp |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, chương trình đã build cho **Java 17 (major 61)** không thể được nạp bởi runtime chỉ hỗ trợ tối đa **Java 11 (major 55)**. Khi đó có thể nhận:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 61.0);
  this runtime only recognizes class file versions up to 55.0
~~~

Đây là **thông báo minh họa**, không nhất thiết giống hệt thông báo của mọi vendor.

### Kiểm tra file class bằng `javap`

Sau khi biên dịch `VersionEnvironmentDemo.java` bằng JDK:

~~~bash
javap -verbose VersionEnvironmentDemo
~~~

Tìm dòng như:

~~~text
major version: 61
~~~

`javap` là công cụ xem thông tin class/bytecode của JDK. **Dòng major version của file class** cho biết mức định dạng của class ấy, không trực tiếp chứng minh file đã được tạo bằng phiên bản compiler cụ thể nào.

### Biên dịch cho phiên bản runtime mục tiêu

Nếu dùng một compiler mới hơn, có thể yêu cầu nó build cho một mức Java cũ hơn mà compiler còn hỗ trợ. Ví dụ dùng **JDK 17** để nhắm **Java 11**:

~~~bash
javac --release 11 VersionEnvironmentDemo.java
javap -verbose VersionEnvironmentDemo
java VersionEnvironmentDemo
~~~

Với ví dụ này, major version dự kiến là **55**, vì mục tiêu được chọn là Java 11. Để chứng minh khả năng chạy trên Java 11, bạn vẫn phải **thực sự chạy chương trình bằng runtime Java 11**, không chỉ bằng runtime 17 trên máy build.

`--release` kiểm soát đồng thời mức ngôn ngữ, class-file target và các **API Java chuẩn** khả dụng ở release mục tiêu (trong giới hạn compiler hỗ trợ). Nó giúp tránh lỗi thường gặp khi dùng `-source`/`-target` nhưng vô tình gọi một API Java chuẩn chỉ có trong runtime mới.

**Giới hạn quan trọng:** `--release` không làm thư viện bên thứ ba tự tương thích với Java cũ, không xử lý native library hay môi trường runtime khác, và không thể yêu cầu compiler hỗ trợ release mà nó không biết. Ví dụ JDK 8 không hiểu `--release 11`.

### Kiểm tra đường build và runtime thực tế

Một kết quả đúng cần tối thiểu ba thông tin:

1. Phiên bản **compiler** dùng để build (`javac -version` hoặc thông tin build tool).
2. Mức target của file `.class` (`javap -verbose` hoặc cấu hình `--release`).
3. Phiên bản **runtime thực sự dùng khi chạy** (`java -version` tại máy đích).

Ba thông tin này có liên quan nhưng **không được đồng nhất**.

## 8. Các lỗi phiên bản và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra / hướng xử lý |
| --- | --- | --- |
| `java: command not found` hoặc “not recognized” | Không cài runtime/launcher, `PATH` sai, môi trường shell khác | Tìm executable Java; kiểm tra cài đặt và `PATH` |
| `javac: command not found` nhưng `java` chạy được | Chỉ có runtime hoặc `PATH` chưa trỏ tới JDK `bin` | Xác minh vị trí `javac`, chọn JDK phù hợp |
| `java` báo 11, `javac` báo 17 | Hai executable có thể được chọn từ các bản cài khác nhau | Kiểm tra đường dẫn từng lệnh và mục tiêu build/runtime |
| `UnsupportedClassVersionError` | Bytecode mới hơn runtime đang chạy | Dùng runtime phù hợp hoặc rebuild với `--release` đúng |
| `invalid flag: --release` | Compiler quá cũ hoặc không hỗ trợ flag | Xem `javac -version`, chọn compiler phù hợp |
| `error: release version 21 not supported` | Compiler hiện tại không hỗ trợ mục tiêu 21 | Không thể biên dịch Java 21 bằng compiler quá cũ; dùng JDK hỗ trợ |
| `NoSuchMethodError` sau khi đổi runtime/thư viện | Có thể chạy với API/thư viện không khớp phiên bản lúc build | Xem dependency/classpath, API runtime và bản thư viện thực sự được nạp |
| IDE chạy khác terminal | IDE chọn Project SDK/Run Configuration riêng | Kiểm tra cấu hình JDK trong IDE và terminal |
| Dùng Docker/CI nhưng máy cá nhân chạy tốt | Container/runner có runtime/JDK khác | Kiểm tra phiên bản **bên trong** container/runner, không chỉ máy chủ |

**Đừng chữa nhầm bệnh:** `Could not find or load main class` thường liên quan **classpath hoặc tên main class**, không nhất thiết là lỗi phiên bản. Mã nguồn sai cú pháp là lỗi biên dịch; `UnsupportedClassVersionError` là lỗi tương thích bytecode tại runtime.

## 9. Quy trình kiểm tra nhanh trước khi bắt đầu dự án

Lần đầu mở một dự án Java hoặc nhận một yêu cầu chạy code, hãy làm theo thứ tự:

~~~mermaid
flowchart TD
    A["Mở terminal tại môi trường cần kiểm tra"] --> B["java -version và javac -version"]
    B --> C{"Cả hai lệnh có mặt?"}
    C -->|Không| D["Kiểm tra JDK, PATH, alias/wrapper"]
    C -->|Có| E["Ghi nhận các phiên bản chính"]
    E --> F["Kiểm tra đường dẫn java/javac"]
    F --> G["Xác định target Java của dự án"]
    G --> H["Biên dịch với cấu hình phù hợp"]
    H --> I["Chạy bằng runtime mục tiêu"]
    I --> J{"Kết quả ổn?"}
    J -->|Không| K["Đọc lỗi: classpath, bytecode hay API"]
    K --> F
    J -->|Có| L["Môi trường đã được xác nhận"]
~~~

Checklist ngắn:

- [ ] `java -version` có kết quả và bạn biết đang dùng phiên bản nào.
- [ ] `javac -version` có kết quả nếu cần biên dịch mã Java.
- [ ] Đã kiểm tra vị trí executable, nhất là khi cài nhiều JDK.
- [ ] Biết dự án yêu cầu runtime Java nào; không chọn version ngẫu nhiên.
- [ ] Nếu có `--release`, biết mục tiêu biên dịch và giới hạn của nó.
- [ ] Chạy thử bằng **runtime đích**, không chỉ runtime trên máy phát triển.

## 10. Bài tập tự luyện

**Bài 1 — Đọc phiên bản:** Giả sử `java -version` cho `11.0.x` còn `javac -version` cho `17.0.x`. Có phải compiler Java 17 không thể dùng được không?

*Gợi ý:* Chưa thể kết luận như vậy. Compiler 17 có thể tạo class target 11 với `--release 11` nếu mã và API tương thích. Hãy xác minh lệnh build và thử chạy artifact trên runtime 11 thực.

**Bài 2 — Xác định đường dẫn:** Trên máy có hai JDK, hãy liệt kê vị trí `java` và `javac` bằng lệnh phù hợp hệ điều hành. So sánh với `JAVA_HOME` và giải thích vì sao khác nhau.

**Bài 3 — Kiểm tra file class:** Biên dịch `VersionEnvironmentDemo.java`, dùng `javap -verbose` xác định major version. Sau đó (nếu compiler hỗ trợ) build với `--release 11` và kiểm tra sự khác biệt.

**Bài 4 — Nhận diện lỗi:** Bạn đưa file `.class` target Java 17 lên máy Java 11, nhận `UnsupportedClassVersionError`. Hãy đề xuất **hai** cách giải quyết hợp lệ và mô tả rủi ro phụ thuộc thư viện nếu chọn build về Java 11.

**Bài 5 — IDE so với terminal:** Một ứng dụng chạy trong IDE nhưng thất bại khi chạy ở terminal. Hãy kiểm tra runtime được in từ `VersionEnvironmentDemo` ở cả hai nơi, đường dẫn `java` trong terminal và cấu hình Run/SDK của IDE.

## 11. Tự đánh giá

Bạn hiểu bài khi có thể giải thích:

1. Vì sao phải chạy **cả `java -version` lẫn `javac -version`** thay vì chỉ một lệnh.
2. Vì sao `JAVA_HOME` không tự động chứng minh lệnh `java` đang dùng đúng JDK đó.
3. Sự khác nhau giữa **phiên bản compiler**, **class-file target** và **phiên bản runtime**.
4. Khi gặp `UnsupportedClassVersionError`, vì sao cần xem `--release` và runtime đích thay vì chỉ đổi tên file.
5. Cách xác nhận trên Windows/macOS/Linux bằng lệnh đơn giản mà không làm thay đổi dữ liệu ứng dụng.

**Kết luận:** `java -version` kiểm tra môi trường **chạy**, `javac -version` kiểm tra công cụ **biên dịch**. Muốn chương trình Java chạy đúng, cần kết hợp cả hai với đường dẫn executable thực, cấu hình target và kiểm thử trên runtime mà ứng dụng sẽ sử dụng.
