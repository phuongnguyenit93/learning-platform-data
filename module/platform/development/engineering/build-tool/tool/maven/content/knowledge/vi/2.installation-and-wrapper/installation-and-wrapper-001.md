# Chuẩn bị JDK và kiểm tra điều kiện tương thích với phiên bản Maven

> **Phạm vi:** Build Tool Maven → Cài đặt và Wrapper. Bài này tập trung chuẩn bị Java Development Kit (JDK), xác định JDK mà Maven thực sự sử dụng và đánh giá phiên bản Java có đáp ứng Maven, plugin cũng như dự án hay không. Các bước cài đặt Maven và Maven Wrapper đầy đủ thuộc các bài riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **JDK chạy Maven**, **JDK dùng để biên dịch mã nguồn**, **phiên bản Java mà dự án hướng đến** và **Java chạy ứng dụng sau khi đóng gói**.
2. Chọn JDK phù hợp với nhánh Maven đang sử dụng; hiểu vì sao Maven chạy được vẫn chưa bảo đảm dự án build thành công.
3. Kiểm tra `java`, `javac`, `JAVA_HOME`, `PATH`, `mvn -version` trên Windows, Linux và macOS.
4. Cấu hình môi trường, xử lý xung đột giữa nhiều bản JDK và nhận diện các lỗi tương thích phổ biến.
5. Dùng `maven.compiler.release` hoặc Maven Toolchains khi cần biên dịch cho một phiên bản Java xác định.

## 2. Bốn phiên bản phải phân biệt

**JDK** chứa JVM, thư viện nền tảng và công cụ phát triển như `javac`. **JVM** thực thi bytecode Java; `java` khởi chạy JVM, còn `javac` biên dịch mã nguồn. Chỉ có Java Runtime Environment (JRE) cũ hoặc một bản runtime tối giản không bảo đảm có `javac`.

Maven là công cụ điều phối build: Maven chạy trên **một JVM**, đọc `pom.xml`, sau đó gọi các plugin để biên dịch, kiểm thử, đóng gói và thực hiện các công việc khác. Trong trường hợp thông thường, Compiler Plugin dùng trình biên dịch từ JDK chạy Maven; Maven Toolchains hoặc cấu hình riêng của plugin có thể thay đổi JDK dùng để biên dịch.

```text
Terminal / CI
  ├─ java + JAVA_HOME + PATH ──> JVM chạy Maven
  │                               ├─ đọc pom.xml
  │                               └─ chạy các Maven plugin
  └─ JDK biên dịch (mặc định cùng JDK chạy Maven; có thể dùng Toolchains)
                                  └─ javac --release N ──> tệp .class
                                                           └─ JVM chạy ứng dụng
```

Bốn câu hỏi cần được trả lời riêng:

| Lớp | Câu hỏi | Cách kiểm tra hoặc cấu hình |
| --- | --- | --- |
| **Maven core** | Maven phiên bản này cần Java tối thiểu nào để khởi động? | Tài liệu phát hành Maven và `mvn -version` |
| **Maven plugin** | Compiler, Surefire, Spring Boot plugin… có yêu cầu Maven/JDK riêng không? | Tài liệu của từng plugin, phiên bản plugin trong `pom.xml`, lỗi khi chạy goal |
| **Biên dịch** | Dùng JDK nào và tạo mã tương thích với Java mấy? | `javac -version`, `maven.compiler.release`, Toolchains |
| **Chạy ứng dụng** | Môi trường chạy ứng dụng có JVM đủ mới không? | `java -version` trên máy chạy thực tế và yêu cầu của framework/thư viện |

Ví dụ: **Maven 3.9 + JDK 21 + `release=17`** là một cấu hình hợp lý: Maven chạy trên Java 21 và `javac` tạo mã nhắm đến Java 17. Ngược lại, **Maven 3.9 + JDK 11 + `release=17`** không thể biên dịch Java 17 bằng `javac` 11 mặc định; cần JDK biên dịch 17+.

**Quy tắc nền tảng:** JDK chạy Maven phải đạt mức tối thiểu của *Maven core* và plugin đang chạy; JDK biên dịch phải hỗ trợ phiên bản Java đích; JVM chạy sản phẩm phải hỗ trợ bytecode và thư viện được sử dụng. Ba điều kiện này độc lập.

## 3. Tra yêu cầu Java theo nhánh Maven

Theo lịch sử phát hành và hướng dẫn chính thức của Apache Maven:

| Nhánh Maven | Java tối thiểu để **chạy Maven** | Nhận xét |
| --- | --- | --- |
| Maven **3.8.x** và các bản 3.6.x phổ biến | Java **7** | Nhánh cũ đã hết hỗ trợ; không nên chọn cho dự án mới chỉ vì cần Java cũ. |
| Maven **3.9.x** | Java **8** | Phù hợp nhiều dự án hiện hành; plugin có thể đòi JDK cao hơn. |
| Maven **3.10.x** | Java **8** | Tương tự về mức Java tối thiểu của Maven core. |
| Maven **4.x** (nhánh ứng viên phát hành tại thời điểm viết) | Java **17** | Không thể chạy bằng JDK 8/11; cần đánh giá tương thích plugin, cấu hình dự án khi chuyển từ Maven 3. |

Đây là **mức để khởi chạy Maven**, không phải khuyến nghị chọn JDK thấp nhất cho mọi dự án. Ví dụ, Maven 3.9 có thể khởi động trên JDK 8 nhưng dự án Spring Boot hoặc một plugin cụ thể có thể yêu cầu JDK 17/21. Phiên bản Maven và plugin tiếp tục thay đổi; khi nâng cấp, kiểm tra trang [Maven Releases History](https://maven.apache.org/docs/history.html), [Maven Installation](https://maven.apache.org/install.html) và tài liệu của plugin thực sự dùng.

Một cách lựa chọn có thể bảo trì:

1. Xác định phiên bản Java mà **mã nguồn, framework và môi trường chạy** cần; ưu tiên một JDK đang được hỗ trợ, chẳng hạn JDK 17 hoặc 21 khi phù hợp với dự án.
2. Xác định Maven core được dự án/CI hỗ trợ; với dự án Maven 3, ưu tiên nhánh còn được bảo trì.
3. Kiểm tra yêu cầu Maven/JDK của plugin, đặc biệt khi nâng compiler, test, code generation hoặc framework plugin.
4. Chọn phiên bản JDK cụ thể cho máy cá nhân và CI; thống nhất cách chỉ định chúng để tránh tình trạng “máy tôi chạy được”.
5. Chỉ cân nhắc Maven 4 sau khi kiểm tra yêu cầu Java 17+ và khả năng tương thích của toàn bộ plugin.

## 4. Cài hoặc chọn một JDK hoàn chỉnh

Bạn có thể dùng bản phân phối JDK phù hợp chính sách dự án (ví dụ Eclipse Temurin, Oracle JDK, Amazon Corretto, Azul Zulu). Việc chọn nhà cung cấp không thay đổi cú pháp Java cơ bản, nhưng ảnh hưởng cách cài, đường dẫn, thời hạn cập nhật và chính sách hỗ trợ.

**Điểm kiểm tra sau khi cài:**

- Có thư mục gốc JDK chứa `bin/java` và `bin/javac` (Windows là `java.exe`, `javac.exe`).
- Có thể chạy `java -version` và `javac -version`, và số phiên bản đúng với JDK dự kiến.
- `JAVA_HOME`, nếu được đặt, trỏ vào **thư mục gốc JDK**, ví dụ `/opt/jdk-17` hoặc `C:\Program Files\Java\jdk-17`; **không** trỏ tới `bin`, `java.exe` hay một thư mục JRE.
- `PATH` cho phép terminal tìm thấy Java và Maven. Thứ tự các đường dẫn trong `PATH` có thể quyết định bản Java được gọi.
- Mở **terminal mới** sau khi sửa biến môi trường của hệ điều hành hoặc cấu hình của IDE.

Trong dự án có nhiều JDK, đừng chỉ nhìn danh sách JDK đã cài. Hãy kiểm tra chính **terminal/IDE/CI đang chạy build** đang dùng bản nào.

## 5. Bộ lệnh kiểm tra tối thiểu

### 5.1. Windows PowerShell

```powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java, javac, mvn | Select-Object Name, Source
where.exe java
where.exe javac
where.exe mvn
mvn -version
```

`java -version` thường ghi phiên bản ra luồng lỗi chuẩn (stderr); điều đó **không có nghĩa là lệnh thất bại**. `Get-Command` chỉ ra lệnh được PowerShell phân giải; `where.exe` cho biết các bản thực thi xuất hiện trong `PATH`. Nếu `mvn` chưa được cài hoặc chưa có trong `PATH`, riêng `mvn -version` có thể báo không tìm thấy lệnh.

### 5.2. Linux/macOS (Bash, Zsh)

```bash
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v java
command -v javac
command -v mvn
mvn -version
```

`command -v` cho biết vị trí lệnh đang được shell lựa chọn. Trên macOS, lệnh `/usr/libexec/java_home -V` thường giúp liệt kê JDK mà hệ thống nhận diện. Trên Linux, liên kết `/usr/bin/java` có thể trỏ qua cơ chế alternatives, nên vị trí thực tế có thể khác đường dẫn nhìn thấy ban đầu.

### 5.3. Đọc kết quả Maven

Ví dụ **minh họa** (số bản vá, vendor và đường dẫn thay đổi theo máy):

```text
Apache Maven 3.9.x
Maven home: /opt/apache-maven
Java version: 17.0.x, vendor: Eclipse Adoptium
Java home: /opt/jdk-17
Default locale: en_US, platform encoding: UTF-8
OS name: "linux", ...
```

Cần đọc đúng ba thông tin: **Maven version** (phiên bản Maven đang chạy), **Java version** (JVM đang chạy Maven) và **Java home** (đường dẫn Java mà Maven thực sự dùng). Nếu `java -version` hiển thị 21 nhưng `mvn -version` hiển thị 17, đó là tín hiệu cần kiểm tra `JAVA_HOME`, script khởi chạy Maven hoặc cấu hình IDE; đừng suy luận Maven đang chạy JDK 21.

Nếu dùng Maven Wrapper, đứng tại thư mục gốc dự án và chạy `./mvnw -version` trên Linux/macOS, hoặc `.\mvnw.cmd -version` trong Windows PowerShell. Wrapper chọn **bản phân phối Maven của dự án**, nhưng vẫn cần Java đáp ứng yêu cầu của bản Maven đó. Maven Wrapper không tự động thay thế việc chuẩn bị một JDK phù hợp.

## 6. Cấu hình JAVA_HOME và PATH đúng cách

### 6.1. Linux: cấu hình cho phiên terminal hiện tại

Thay `/opt/jdk-17` bằng thư mục JDK **có thật** trên máy:

```bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
mvn -version
```

Để duy trì cho phiên mới, có thể đặt hai lệnh `export` vào tệp cấu hình shell phù hợp như `~/.bashrc` hoặc `~/.zshrc`; với dịch vụ hoặc CI, đặt biến trong cấu hình của **tiến trình thực tế**, không phụ thuộc vào shell tương tác cá nhân. Đảm bảo đường dẫn đến JDK đúng với distro/hệ điều hành; không sao chép nguyên đường dẫn ví dụ.

### 6.2. macOS: chọn JDK đã cài

```bash
/usr/libexec/java_home -V
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
mvn -version
```

`java_home -v 17` chỉ có kết quả khi hệ thống nhận diện JDK 17 tương ứng. Nếu cần cố định phiên bản cho nhiều dự án, sử dụng cơ chế chọn JDK được cả nhóm thống nhất và kiểm tra lại Maven sau khi đổi.

### 6.3. Windows PowerShell: cấu hình cho phiên hiện tại

Thay đường dẫn dưới đây bằng thư mục cài JDK thật:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
mvn -version
```

Để cấu hình lâu dài, đặt `JAVA_HOME` trong **Environment Variables** của Windows rồi thêm `%JAVA_HOME%\bin` vào `Path` của User hoặc System theo chính sách máy. Đóng và mở lại terminal/IDE. Tránh ghi đè toàn bộ `Path` chỉ để thêm JDK; lệnh `setx PATH` dùng thiếu thận trọng có thể gây mất các mục đường dẫn đang có.

Nếu cài Maven thủ công, thư mục `bin` của Maven cũng phải có trong `PATH` để gọi `mvn`. Khi dùng Wrapper, có thể chạy `mvnw` trong dự án dù chưa cài Maven toàn cục, miễn môi trường Java hợp lệ.

## 7. Bằng chứng thực hành: JDK 17 + Maven 3.x + mã chạy được

Để tách rõ yêu cầu **JDK chạy Maven** và **Java đích khi biên dịch**, tạo dự án nhỏ sau đây bằng JDK 17+ và Maven 3.9/3.10. Cấu trúc:

```text
check-jdk-maven/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── App.java
```

Nội dung `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>check-jdk-maven</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/dev/example/App.java`:

```java
package dev.example;

public class App {
    public static void main(String[] args) {
        System.out.println("JDK 17 va Maven da san sang!");
    }
}
```

Từ thư mục chứa `pom.xml`, chạy:

```bash
java -version
javac -version
mvn -version
mvn -B -ntp compile
java -cp target/classes dev.example.App
```

Nếu các bước đều thành công, **stdout của lệnh Java cuối** chính xác là:

```text
JDK 17 va Maven da san sang!
```

`mvn compile` có thể tải compiler plugin và các dependency/plugin cần thiết từ repository trong lần chạy đầu; cần kết nối mạng hoặc cache Maven đã đầy đủ. Các dòng log `[INFO]` và thời gian build phụ thuộc môi trường, nên không cố định chúng trong ví dụ.

Ở đây:

- `mvn -version` chứng minh Maven đã **khởi động trên một JVM** cụ thể.
- `maven.compiler.release=17` yêu cầu compiler tạo class dùng mức ngôn ngữ, API Java SE và định dạng bytecode phù hợp Java 17 khi dùng `javac` hỗ trợ tùy chọn `--release`.
- Nếu đang chạy JDK 21 nhưng `release=17`, chương trình vẫn được biên dịch hướng đến Java 17; cần thử ứng dụng trên JVM 17 thật nếu bảo đảm tương thích vận hành là yêu cầu bắt buộc.
- `release=17` không làm cho Maven chạy được trên JDK không đáp ứng chính Maven core/plugin, và không cho phép `javac` 11 biên dịch các tính năng Java 17.

Tại sao ưu tiên `release` thay vì chỉ `source` và `target`? Cặp `source`/`target` kiểm soát cú pháp/bytecode, còn `--release` (từ JDK 9) cũng kiểm tra **bề mặt API của phiên bản Java đích**, giúp tránh vô tình gọi API mới rồi nhận lỗi khi chạy trên JVM cũ. Không phải mọi bản JDK đều hỗ trợ biên dịch ngược về mọi bản Java lịch sử; hãy kiểm tra hỗ trợ `--release` của JDK thực tế.

## 8. Đánh giá tình huống tương thích

| Tình huống | Kết luận | Cách xử lý |
| --- | --- | --- |
| Maven 3.9, JVM Maven là JDK 17, `release=17` | **Đạt** điều kiện cơ bản | Tiếp tục kiểm tra plugin, dependency, test và môi trường triển khai. |
| Maven 3.10, JVM Maven là JDK 21, `release=17` | **Đạt** điều kiện cơ bản | Dùng `--release 17` và kiểm thử thực tế trên Java 17. |
| Maven 4, JVM Maven là JDK 11 | **Không đạt** mức tối thiểu của Maven 4 | Chạy Maven 4 bằng JDK 17+ hoặc chọn bản Maven tương thích theo dự án. |
| Maven 3.9, JVM Maven là JDK 8, dự án yêu cầu Java 17 | **Không đủ** JDK biên dịch theo cấu hình mặc định | Nâng JDK biên dịch lên 17+; nếu cần khác JDK chạy Maven, xem Toolchains. |
| Maven 3.9, JVM Maven là JDK 17, `release=21` | **Không thể** biên dịch Java 21 với `javac` 17 mặc định | Dùng JDK 21+ cho compiler, có thể qua Toolchains. |
| Maven core chạy được nhưng plugin báo yêu cầu Java/Maven cao hơn | **Không đạt** yêu cầu plugin | Đọc thông báo phiên bản tối thiểu, cân nhắc nâng JDK/Maven hoặc chọn bản plugin được hỗ trợ. |

Những kết luận “đạt” ở bảng chỉ đánh giá **trục Maven–JDK–Java release**. Một dự án còn có thể lỗi do dependencies, plugin, hệ thống build, mạng hoặc mã nguồn.

## 9. Khi Maven chạy trên một JDK nhưng cần biên dịch bằng JDK khác

**Maven Toolchains** cho phép plugin hỗ trợ Toolchains chọn JDK khác với JVM đang chạy Maven. Ví dụ: máy có JDK 17 và JDK 21; Maven 3.9 chạy trên JDK 17 nhưng dự án cần biên dịch bằng JDK 21.

Khai báo `~/.m2/toolchains.xml` (Windows: `%USERPROFILE%\.m2\toolchains.xml`) trên **máy chạy build**, thay `/path/to/jdk-21` bằng đường dẫn thật:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Để **Compiler Plugin** chọn toolchain đã khai báo, có thể cấu hình plugin trong `pom.xml` như sau (đặt bên trong `<build><plugins>`):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.0</version>
    <configuration>
        <jdkToolchain>
            <version>21</version>
        </jdkToolchain>
        <release>21</release>
    </configuration>
</plugin>
```

Mỗi máy/CI phải có đường dẫn JDK tương ứng; `toolchains.xml` thường là cấu hình **cục bộ theo máy**. Nếu không tìm được toolchain phù hợp, build sẽ lỗi. Một số plugin khác cần cấu hình Toolchains riêng hoặc sử dụng `maven-toolchains-plugin` để chọn toolchain dùng chung; **không mặc định mọi plugin và bước test đều chuyển sang JDK 21**. Chẳng hạn, một class biên dịch cho Java 21 không chạy được trên JVM 17 chỉ vì Maven đã biên dịch thành công.

Chỉ dùng Toolchains khi có yêu cầu thực tế. Với dự án thông thường, cấu hình một JDK nhất quán cho Maven, compiler và CI dễ vận hành hơn.

## 10. IDE, Maven Wrapper và CI: kiểm tra cùng một nguồn sự thật

- **Terminal:** `mvn -version` (hoặc `./mvnw -version`) chứng minh JVM của chính tiến trình Maven vừa chạy.
- **IDE:** Project SDK, Java Compiler và Maven Runner/JDK có thể là **ba thiết lập khác nhau**. Mở phần cấu hình Maven Runner/JDK của IDE và kiểm tra log Maven, thay vì suy ra từ SDK hiển thị trong dự án.
- **Maven Wrapper:** `mvnw`/`mvnw.cmd` cố định hoặc chọn phiên bản Maven đã khai báo trong cấu hình Wrapper; nó **không tự bảo đảm JDK đúng**. Kiểm tra đầu ra của Wrapper `-version` trên mỗi môi trường.
- **CI:** Thiết lập JDK trước bước Maven, chọn đúng Wrapper nếu repo dùng Wrapper, và ghi `java -version`, `javac -version`, `./mvnw -version` vào log đầu job. Đảm bảo image/runner có cả JDK compiler cần thiết và toolchain nếu dự án dùng.
- **Ứng dụng sau build:** kiểm tra JDK/JRE trong image hoặc máy triển khai. Không kết luận ứng dụng chạy được trên Java 17 chỉ từ việc nó đã build trên Java 21.

Một nhóm nên ghi rõ trong tài liệu dự án: phiên bản Maven/Wrapper, JDK chạy Maven, `maven.compiler.release`, Java runtime đích và bất kỳ yêu cầu JDK của plugin/framework nào. Khi thay đổi một trong các giá trị đó, cập nhật CI cùng lúc.

## 11. Sửa lỗi theo triệu chứng

### `mvn` không được nhận diện

**Triệu chứng:** `mvn: command not found` (Unix) hoặc “The term 'mvn' is not recognized” (PowerShell).

**Nguyên nhân có thể:** chưa cài Maven toàn cục, chưa thêm `bin` của Maven vào `PATH`, hoặc shell chưa nạp biến môi trường mới.

**Kiểm tra:** `command -v mvn` (Unix) hoặc `Get-Command mvn` (PowerShell). Nếu dự án có Wrapper, chạy `./mvnw -version` / `.\mvnw.cmd -version` đúng hệ điều hành.

### `JAVA_HOME is not defined correctly` hoặc Maven dùng nhầm JDK

**Nguyên nhân có thể:** `JAVA_HOME` trỏ tới `bin`/JRE/thư mục đã bị chuyển, hoặc Maven ưu tiên `JAVA_HOME` khác bản `java` trong `PATH`.

**Kiểm tra:** in `JAVA_HOME`, xác nhận tồn tại `bin/java` và `bin/javac` trong thư mục đó, so sánh `java -version` với `mvn -version`, rồi sửa biến và mở terminal mới.

### `No compiler is provided in this environment`

**Ý nghĩa:** plugin không truy cập được Java compiler phù hợp; thường là đang dùng runtime thiếu `javac` hoặc cấu hình JDK sai.

**Khắc phục:** cài/chọn JDK hoàn chỉnh, chạy `javac -version`, xác minh `mvn -version` và cấu hình Toolchains nếu dự án dùng JDK khác để biên dịch.

### `release version 21 not supported` hoặc `invalid target release: 21`

**Ý nghĩa:** compiler được chọn quá cũ so với `release` mong muốn. Ví dụ `javac` 17 không biên dịch được mã đích Java 21.

**Khắc phục:** chọn JDK compiler 21+, hoặc hạ Java đích **chỉ khi yêu cầu chức năng của dự án cho phép**. Kiểm tra compiler thực sự được gọi, không chỉ JDK đã cài.

### `UnsupportedClassVersionError`

**Ý nghĩa:** JVM lúc chạy ứng dụng quá cũ so với class đã biên dịch. Ví dụ class file version **65** (Java 21) không thể chạy trên JVM chỉ hỗ trợ đến version **61** (Java 17).

**Khắc phục:** nâng JVM chạy ứng dụng hoặc biên dịch lại cho Java đích được hỗ trợ, đồng thời bảo đảm thư viện/framework tương thích. Không sửa lỗi này bằng cách chỉ đổi phiên bản Maven.

### Maven khởi động được nhưng plugin báo yêu cầu Java/Maven cao hơn

**Ý nghĩa:** Maven core và plugin có yêu cầu khác nhau. Plugin có thể được biên dịch cho JDK mới hơn hoặc yêu cầu API Maven mới hơn.

**Khắc phục:** đọc rõ tên plugin, phiên bản và yêu cầu trong log; kiểm tra tài liệu phiên bản plugin; đồng bộ `pom.xml` và CI. Hạ plugin tùy tiện có thể mất sửa lỗi hoặc tính năng cần thiết.

### Build chạy được trong IDE nhưng lỗi ở terminal/CI

**Nguyên nhân có thể:** IDE đang dùng Maven/JDK riêng, `JAVA_HOME` khác nhau, shell tải bản Java qua manager/alternatives, hoặc CI thiếu Toolchains.

**Khắc phục:** so sánh theo cùng thứ tự `java -version` → `javac -version` → `mvn -version` (hoặc Wrapper) → `release` trong `pom.xml` → JDK dùng khi test/chạy.

## 12. Bài thực hành và câu hỏi tự kiểm tra

**Bài 1 — xác nhận môi trường:** Trên máy của bạn, ghi lại bốn thông tin: (a) phiên bản `java`, (b) phiên bản `javac`, (c) dòng `Java version` trong `mvn -version` hoặc Wrapper `-version`, (d) Java đích của dự án. Nếu (a) và (c) khác nhau, tìm nguyên nhân ở `JAVA_HOME`, `PATH` hoặc Maven Runner.

**Bài 2 — build Java 17:** Dùng dự án ở mục 7. Chạy `mvn -B -ntp compile`, sau đó chạy class bằng `java -cp target/classes dev.example.App`. Xác nhận thông báo được in chính xác. Thử thay `maven.compiler.release` thành `21` khi compiler thực tế vẫn là JDK 17; phân tích vì sao bước compile lỗi. Trả lại `17` sau thực hành.

**Bài 3 — ra quyết định:** Một dự án đang dùng Maven 3.9, JDK 11 và phải chuyển lên Maven 4. Cần thay đổi gì? Đáp án: Maven 4 yêu cầu **JDK 17+ để chạy**; đồng thời kiểm tra tương thích plugin, yêu cầu Java của mã nguồn và cấu hình Wrapper/CI. Không được suy luận rằng chỉ nâng Maven là đã nâng Java đích của ứng dụng.

## 13. Checklist trước khi bắt đầu học Maven

- [ ] Đã xác định Java cần cho **Maven core**, **plugin/framework**, **mã nguồn** và **runtime**.
- [ ] `java -version`, `javac -version` trả kết quả đúng JDK đã chọn.
- [ ] `JAVA_HOME` (nếu dùng) trỏ đến **thư mục gốc JDK**, và `PATH` không trỏ nhầm bản Java.
- [ ] `mvn -version` hoặc Maven Wrapper `-version` xác nhận **Maven version**, **Java version** và **Java home** mong muốn.
- [ ] `pom.xml` khai báo mức Java đích phù hợp, ưu tiên `maven.compiler.release` với compiler hỗ trợ.
- [ ] IDE và CI dùng cấu hình JDK/Maven được dự án công bố.
- [ ] Đã chạy ít nhất một lần biên dịch và thử chương trình trên JVM thực tế mà ứng dụng sẽ sử dụng.

## 14. Tài liệu chính thức

1. [Apache Maven — Installation](https://maven.apache.org/install.html): yêu cầu JDK, `JAVA_HOME` và cài Maven.
2. [Apache Maven — Releases History](https://maven.apache.org/docs/history.html): phiên bản Maven và mức Java tối thiểu.
3. [Apache Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cách dùng `maven.compiler.release`.
4. [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): chọn JDK biên dịch khác JVM chạy Maven.
5. [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html): yêu cầu Java 17+ và các điểm cần kiểm tra khi nâng Maven 4.
