# JDK, `javac`, `java` và `jar` trong chuỗi build Java

Khi phát triển một chương trình Java, mã nguồn phải đi qua một chuỗi bước trước khi có thể chạy được. Ta viết mã trong các tệp `.java`, dùng trình biên dịch để tạo bytecode `.class`, đóng gói các lớp và tài nguyên thành thư viện hoặc ứng dụng, rồi khởi chạy chương trình bằng Java Virtual Machine (JVM).

Trong chuỗi đó, **JDK** cung cấp bộ công cụ phát triển; **`javac`** biên dịch mã nguồn; **`jar`** đóng gói các tệp; và **`java`** khởi chạy ứng dụng. Công cụ build như Gradle hoặc Maven điều phối các bước này, quản lý dependency và giúp quy trình có thể lặp lại.

## 1. Nhìn tổng thể chuỗi build

Một quy trình Java cơ bản có thể hình dung như sau:

```text
Mã nguồn .java       Tài nguyên       Thư viện phụ thuộc
      |                  |                    |
      v                  v                    v
   javac            copy/process         dependency classpath
      |
      v
Bytecode .class  +  tài nguyên
      |
      v
     jar  ---------------------->  Tệp .jar
                                      |
                                      v
                                    java
                                      |
                                      v
                               JVM thực thi ứng dụng
```

Đây là cách mô tả rút gọn. Trong một dự án thực tế, build tool còn có thể biên dịch mã nguồn kiểm thử, chạy test, xử lý tài nguyên, tạo metadata, kiểm tra chất lượng và tạo nhiều loại artifact. Thứ tự cụ thể phụ thuộc vào build tool và cấu hình dự án.

| Thành phần | Vai trò chính | Đầu vào thường gặp | Kết quả |
|---|---|---|---|
| JDK | Bộ công cụ dùng để phát triển và build Java | Cài đặt trên máy hoặc build agent | Các công cụ như `javac`, `java`, `jar` và thư viện nền tảng |
| `javac` | Biên dịch mã nguồn Java | Tệp `.java`, classpath/module path | Bytecode `.class` |
| `jar` | Đóng gói lớp, tài nguyên và metadata | Các tệp đã được tạo trong thư mục build | Tệp lưu trữ `.jar` |
| `java` | Khởi chạy ứng dụng trên JVM | Tên lớp chính hoặc tệp JAR, classpath/module path | Tiến trình ứng dụng đang chạy |
| Gradle/Maven | Điều phối quy trình build | Mã nguồn, cấu hình build, dependency | Các artifact và kết quả kiểm tra |

## 2. JDK là gì?

**JDK (Java Development Kit)** là bộ công cụ phát triển Java. Khi cài JDK, ta có môi trường cần thiết để biên dịch, chạy, đóng gói và hỗ trợ phát triển chương trình Java.

Một JDK thường chứa:

- **Java compiler (`javac`)**: chuyển mã nguồn Java thành bytecode.
- **Java launcher (`java`)**: khởi chạy ứng dụng bằng JVM.
- **JAR tool (`jar`)**: tạo, xem và thao tác với tệp JAR.
- **Các công cụ hỗ trợ khác**: chẳng hạn `javadoc` để tạo tài liệu API, `jshell` để chạy thử biểu thức Java và các công cụ chẩn đoán JVM.
- **Các module/thư viện nền tảng Java**: những API tiêu chuẩn mà chương trình Java có thể sử dụng.

JDK là môi trường dành cho phát triển và build. Máy chỉ cần chạy một ứng dụng đã đóng gói có thể dùng một Java runtime phù hợp, nhưng máy build cần JDK vì phải có compiler và các công cụ phát triển. Với các bản Java hiện đại, runtime thường được cung cấp ngay trong JDK; cách phân phối JRE riêng phụ thuộc nhà cung cấp và phiên bản.

### Kiểm tra JDK đã cài

Mở terminal và chạy:

```bash
java -version
javac -version
jar --version
```

Các lệnh này cho biết những chương trình đang được shell tìm thấy. Nếu `java` chạy được nhưng `javac` không được nhận diện, có thể máy chỉ có runtime hoặc `PATH` chưa trỏ đến thư mục `bin` của JDK.

Hai biến môi trường thường gặp:

- `JAVA_HOME`: trỏ đến thư mục gốc của JDK, ví dụ `C:\Program Files\Java\jdk-21` trên Windows hoặc `/usr/lib/jvm/jdk-21` trên Linux (đường dẫn thực tế tùy cách cài).
- `PATH`: nên chứa thư mục `bin` của JDK để có thể gọi `java`, `javac` và `jar` từ mọi thư mục.

Trên Windows có thể kiểm tra vị trí lệnh bằng `where java`, `where javac`; trên Linux/macOS có thể dùng `which java` và `which javac`. Nếu các lệnh trỏ đến những bản cài khác nhau, kết quả build và lúc chạy có thể không như mong đợi.

Một dự án cũng có thể yêu cầu phiên bản JDK cụ thể. Ví dụ, dự án cấu hình Java 21 nên được build bằng JDK 21 tương thích, hoặc bằng JDK mới hơn có cấu hình biên dịch phù hợp. Cần phân biệt phiên bản JDK đang chạy build với phiên bản bytecode/API mà sản phẩm được yêu cầu hỗ trợ.

## 3. `javac`: biên dịch mã nguồn thành bytecode

`javac` là trình biên dịch Java. Nó đọc mã nguồn `.java`, kiểm tra cú pháp và kiểu dữ liệu, phân giải các kiểu được tham chiếu, rồi tạo bytecode trong các tệp `.class`.

Bytecode không phải mã máy dành riêng cho một CPU. JVM đọc bytecode, kiểm tra và thực thi nó; trong quá trình chạy, JVM có thể thông dịch hoặc biên dịch các đoạn mã thường dùng sang mã máy bằng JIT compiler.

### Ví dụ tối thiểu

Tạo tệp `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
```

Biên dịch:

```bash
javac Hello.java
```

Nếu biên dịch thành công, `javac` tạo `Hello.class` trong thư mục hiện tại. Lúc này chương trình đã có bytecode, nhưng chưa được đóng gói thành JAR.

### Biên dịch vào một thư mục riêng

Trong dự án có cấu trúc thư mục rõ ràng, nên đặt đầu ra biên dịch vào một thư mục build thay vì trộn `.class` với mã nguồn. Tùy chọn `-d` chỉ định nơi ghi các tệp lớp:

```bash
javac -d out src/Hello.java
```

Với lớp có khai báo package:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from com.example");
    }
}
```

Giả sử mã nguồn nằm ở `src/com/example/Hello.java`, có thể biên dịch như sau:

```bash
javac -d out src/com/example/Hello.java
```

Kết quả có đường dẫn `out/com/example/Hello.class`. Tên package quyết định tên đầy đủ của lớp (`com.example.Hello`) và cấu trúc thư mục tương ứng trong đầu ra.

### Các tùy chọn `javac` thường dùng

| Tùy chọn | Ý nghĩa |
|---|---|
| `-d <dir>` | Ghi các tệp `.class` vào thư mục đầu ra |
| `-cp` hoặc `-classpath` | Chỉ định nơi tìm các lớp và thư viện phụ thuộc |
| `--release <version>` | Biên dịch theo phiên bản Java mục tiêu, gồm quy tắc ngôn ngữ, bytecode và API nền tảng tương ứng |
| `-encoding <charset>` | Chỉ định encoding của tệp nguồn, ví dụ `UTF-8` |
| `-parameters` | Lưu tên tham số phương thức vào bytecode để công cụ/runtime có thể đọc qua reflection |
| `-g` | Tạo thông tin debug cho việc gỡ lỗi |

Ví dụ biên dịch bằng JDK 21, nhắm đến nền tảng Java 21 và dùng UTF-8:

```bash
javac --release 21 -encoding UTF-8 -d out src/com/example/Hello.java
```

`--release` thường là lựa chọn phù hợp khi cần kiểm soát phiên bản Java mà artifact hỗ trợ. Chỉ đặt `-source` và `-target` riêng lẻ không bảo đảm compiler chỉ cho phép sử dụng API của phiên bản mục tiêu; `--release` xử lý đồng bộ hơn phần này.

### Classpath khi biên dịch

Nếu mã nguồn tham chiếu một thư viện ngoài, compiler phải tìm thấy thư viện đó. Classpath (`-cp`) chỉ định thư mục chứa lớp hoặc các tệp JAR cần thiết.

Ví dụ:

```bash
javac -cp "lib/example-library.jar" -d out src/com/example/Hello.java
```

Classpath phân tách nhiều mục bằng dấu `;` trên Windows và dấu `:` trên Linux/macOS. Khi viết lệnh, cần đặt cả giá trị classpath trong dấu nháy nếu shell có thể diễn giải ký tự phân tách hoặc wildcard.

## 4. `java`: khởi chạy chương trình trên JVM

Sau khi biên dịch, dùng lệnh `java` để khởi chạy ứng dụng. Với ứng dụng dạng lớp thông thường, ta truyền tên đầy đủ của lớp có phương thức `main` và cung cấp nơi JVM có thể tìm thấy lớp đó.

Với ví dụ ở trên:

```bash
java -cp out com.example.Hello
```

Trong lệnh này:

- `-cp out` đưa thư mục `out` vào classpath.
- `com.example.Hello` là tên đầy đủ của lớp chính, gồm package và tên lớp.
- JVM nạp lớp, tìm điểm vào `public static void main(String[] args)` rồi bắt đầu thực thi.

Nếu chương trình dùng thư viện ngoài, thư viện đó cũng cần có trên classpath khi chạy:

```bash
# Windows
java -cp "out;lib/*" com.example.Hello

# Linux/macOS
java -cp "out:lib/*" com.example.Hello
```

Wildcard `lib/*` giúp JVM tìm các JAR nằm trực tiếp trong thư mục `lib`. Nó không tự tìm đệ quy trong mọi thư mục con.

### Những tùy chọn `java` thường gặp

| Tùy chọn | Ý nghĩa |
|---|---|
| `-cp` hoặc `-classpath` | Chỉ định classpath khi chạy lớp chính |
| `-jar <file>` | Chạy ứng dụng từ JAR có khai báo lớp chính trong manifest |
| `-Dname=value` | Đặt một system property cho tiến trình Java |
| `-Xms<size>` | Đặt kích thước heap ban đầu |
| `-Xmx<size>` | Đặt giới hạn heap tối đa |
| `--module-path` | Chỉ định nơi tìm các module khi chạy ứng dụng theo Java Module System |
| `-m` hoặc `--module` | Chạy module và lớp chính được chỉ định |

Ví dụ:

```bash
java -Xms256m -Xmx1g -Dapp.environment=dev -cp out com.example.Hello
```

Các tham số này cấu hình tiến trình JVM. Chúng không thay đổi bytecode đã được biên dịch.

### Chạy bằng tên lớp và chạy bằng JAR

Có hai cách phổ biến để chỉ điểm vào ứng dụng:

```bash
# Chạy lớp chính từ classpath
java -cp out com.example.Hello

# Chạy JAR có Main-Class trong manifest
java -jar app.jar
```

Khi dùng `-jar`, JVM lấy lớp chính từ thuộc tính `Main-Class` trong manifest. Tùy chọn classpath dòng lệnh không được dùng theo cách thông thường trong chế độ này; nếu ứng dụng cần JAR phụ thuộc, phải khai báo chúng theo cách đóng gói/phân phối phù hợp, chẳng hạn `Class-Path` trong manifest hoặc cơ chế đóng gói của build tool.

## 5. `jar`: đóng gói lớp và tài nguyên

JAR (Java Archive) là định dạng lưu trữ dựa trên ZIP, dùng để gom các tệp liên quan vào một tệp duy nhất. JAR thường chứa:

- Các tệp bytecode `.class`.
- Tài nguyên ứng dụng như `.properties`, `.xml`, ảnh hoặc tệp cấu hình được đóng gói.
- Thư mục `META-INF/`, trong đó có thể có manifest và metadata khác.

`jar` là công cụ đóng gói. Nó không biên dịch `.java` và cũng không tự thực thi chương trình.

### Tạo một JAR thông thường

Giả sử các lớp đã được biên dịch vào thư mục `out`. Tạo JAR:

```bash
jar --create --file hello-library.jar -C out .
```

Ý nghĩa:

- `--create` yêu cầu tạo archive mới.
- `--file hello-library.jar` đặt tên tệp đầu ra.
- `-C out .` chuyển vào thư mục `out` rồi thêm nội dung của thư mục đó vào archive.

Lệnh trên tạo một JAR chứa các tệp trong `out`. Nó chưa chắc là JAR có thể chạy trực tiếp bằng `java -jar`, vì chưa chỉ định lớp chính.

### Tạo executable JAR

Nếu ứng dụng có lớp chính `com.example.Hello`, có thể tạo JAR có manifest chỉ định điểm vào:

```bash
jar --create \
    --file hello-app.jar \
    --main-class com.example.Hello \
    -C out .
```

Tùy chọn `--main-class` ghi thuộc tính `Main-Class` vào manifest. Sau đó có thể chạy:

```bash
java -jar hello-app.jar
```

Trên Windows PowerShell hoặc Command Prompt, có thể viết lệnh trên một dòng hoặc dùng ký tự nối dòng tương ứng của shell.

Một JAR có `Main-Class` thường được gọi là executable JAR. Tên gọi này có nghĩa JVM biết lớp nào cần khởi chạy; nó không có nghĩa mọi dependency của ứng dụng đã tự động nằm trong JAR.

### Xem nội dung và manifest

Các lệnh thường dùng để kiểm tra JAR:

```bash
# Liệt kê các mục trong JAR
jar --list --file hello-app.jar

# Giải nén JAR vào thư mục hiện tại
jar --extract --file hello-app.jar

# Hiển thị thông tin module mà JAR cung cấp (nếu có)
jar --describe-module --file hello-app.jar
```

`--describe-module` hữu ích khi JAR có thông tin module. Nếu chỉ cần xem nội dung `META-INF/MANIFEST.MF`, có thể mở JAR bằng công cụ ZIP hoặc giải nén rồi đọc tệp manifest.

Một manifest tối thiểu của executable JAR có thể có dạng:

```text
Manifest-Version: 1.0
Main-Class: com.example.Hello
```

Nếu ứng dụng cần thư viện phụ thuộc ở bên ngoài, manifest có thể chứa `Class-Path` với đường dẫn tương đối đến các JAR đó. Đường dẫn phải phù hợp với vị trí triển khai thực tế. Một cách khác là dùng plugin build tạo archive chứa dependency hoặc archive thực thi theo định dạng riêng của framework.

### JAR thường và JAR chứa dependency

JAR tiêu chuẩn chỉ đóng gói những tệp được đưa vào lệnh tạo archive. Nếu ứng dụng tham chiếu `example-library.jar` nhưng JAR đó không được đưa vào archive hoặc classpath lúc chạy, JVM có thể báo lỗi như `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Vì vậy cần phân biệt:

- **JAR thư viện**: cung cấp các lớp để ứng dụng khác sử dụng; thường không cần `Main-Class`.
- **Executable JAR**: có `Main-Class` để JVM biết lớp bắt đầu chạy; dependency vẫn cần được cung cấp.
- **Fat JAR/Uber JAR hoặc executable archive của framework**: cách đóng gói do build tool/plugin thực hiện để gom hoặc tổ chức dependency phục vụ chạy độc lập. Cấu trúc và cách khởi chạy có thể khác JAR tiêu chuẩn.

## 6. Ghép các lệnh thành một quy trình thủ công

Ví dụ sau minh họa đầy đủ chuỗi biên dịch, đóng gói và chạy với một lớp chính. Giả sử mã nguồn nằm tại `src/com/example/Hello.java` và có khai báo `package com.example;`.

**Bước 1 — Kiểm tra công cụ**

```bash
java -version
javac -version
jar --version
```

**Bước 2 — Biên dịch mã nguồn**

```bash
javac --release 21 -encoding UTF-8 -d build/classes src/com/example/Hello.java
```

Sau bước này, lớp đã biên dịch nằm tại `build/classes/com/example/Hello.class`.

**Bước 3 — Đóng gói thành executable JAR**

```bash
jar --create \
    --file build/hello-app.jar \
    --main-class com.example.Hello \
    -C build/classes .
```

**Bước 4 — Chạy ứng dụng**

```bash
java -jar build/hello-app.jar
```

Quy trình này giúp nhìn rõ trách nhiệm của từng công cụ. Trong dự án thật, ta thường không gõ từng lệnh bằng tay mỗi lần build; build tool sẽ lưu các quy tắc đó trong cấu hình để cả nhóm và CI có thể thực hiện nhất quán.

## 7. Build tool như Gradle hoặc Maven điều phối các công cụ

Gradle và Maven không thay thế JDK. Chúng sử dụng JDK và các công cụ Java phù hợp để thực hiện những bước build theo cấu hình dự án.

Build tool thường đảm nhiệm các công việc sau:

1. Đọc cấu hình dự án và xác định phiên bản Java/toolchain cần dùng.
2. Tìm và tải dependency từ các repository đã cấu hình.
3. Xác định source set, thư mục mã nguồn và tài nguyên.
4. Gọi compiler với classpath, tùy chọn và thư mục đầu ra phù hợp.
5. Biên dịch và chạy kiểm thử.
6. Đóng gói lớp, tài nguyên và metadata thành artifact.
7. Quản lý thứ tự task, đầu vào/đầu ra và việc thực hiện lại khi cần.

Với Gradle Java plugin, các task quen thuộc gồm:

| Task | Công việc |
|---|---|
| `compileJava` | Biên dịch mã nguồn Java chính, thường thông qua `javac` |
| `processResources` | Sao chép/xử lý tài nguyên chính vào thư mục đầu ra |
| `classes` | Gom các bước tạo lớp chính, bao gồm biên dịch và xử lý tài nguyên |
| `compileTestJava` | Biên dịch mã nguồn kiểm thử |
| `test` | Chạy bộ kiểm thử đã cấu hình |
| `jar` | Đóng gói lớp và tài nguyên chính thành JAR |
| `assemble` | Tạo các artifact của dự án |
| `build` | Thực hiện các bước build tổng thể, thường bao gồm kiểm thử và assemble |

Có thể chạy build bằng Gradle Wrapper của dự án:

```bash
# Linux/macOS
./gradlew clean build

# Windows
gradlew.bat clean build
```

Wrapper giúp dự án sử dụng phiên bản Gradle đã được khai báo, giảm phụ thuộc vào Gradle cài toàn cục trên máy. Dù vậy, vẫn cần một JDK tương thích để chạy Gradle và biên dịch mã nguồn.

Trong dự án Spring Boot, task `bootJar` có thể tạo executable archive với cơ chế nạp dependency của Spring Boot. Artifact đó có thể có cấu trúc khác JAR chuẩn được tạo bởi task `jar`. Vì vậy, cần xem task và cấu hình thực tế của dự án trước khi giả định mọi tệp `.jar` đều có cùng cách chạy.

## 8. Phân biệt các lỗi theo đúng công đoạn

Khi build hoặc chạy Java thất bại, xác định công đoạn gây lỗi sẽ giúp tìm nguyên nhân nhanh hơn.

| Dấu hiệu | Công đoạn thường liên quan | Hướng kiểm tra |
|---|---|---|
| `javac` không được nhận diện | Cài đặt JDK hoặc `PATH` | Kiểm tra JDK, `JAVA_HOME`, `PATH`, `where javac`/`which javac` |
| `error: cannot find symbol` | Biên dịch | Kiểm tra tên lớp, package, import, dependency và classpath của compiler |
| `package ... does not exist` | Biên dịch | Kiểm tra dependency và classpath/module path |
| `Could not find or load main class` | Khởi chạy bằng tên lớp | Kiểm tra tên đầy đủ của lớp, classpath và cấu trúc thư mục `.class` |
| `no main manifest attribute` | Khởi chạy bằng `java -jar` | Kiểm tra manifest có `Main-Class` hay chưa |
| `ClassNotFoundException` | Nạp lớp lúc chạy | Kiểm tra classpath hoặc dependency có được phân phối cùng ứng dụng không |
| `NoClassDefFoundError` | Nạp lớp/phụ thuộc lúc chạy | Kiểm tra lớp hoặc thư viện cần thiết có trong môi trường runtime không |
| `UnsupportedClassVersionError` | Tương thích bytecode | Kiểm tra phiên bản JDK dùng để biên dịch và phiên bản Java dùng để chạy |

Một điểm cần nhớ: build thành công không bảo đảm ứng dụng chắc chắn chạy thành công. Compiler có thể tìm thấy dependency trong lúc biên dịch, nhưng môi trường chạy vẫn thiếu dependency nếu quy trình đóng gói/phân phối không đưa chúng đến đúng nơi.

## 9. Java Module System và module path

Ngoài classpath truyền thống, Java còn có Java Platform Module System (JPMS). Một module có thể khai báo tên, các package được export và các dependency module trong `module-info.java`.

Ví dụ khai báo module:

```java
module com.example.app {
    requires java.logging;
}
```

Khi dự án sử dụng module system, compiler và JVM có thể nhận module thông qua `--module-path`. Lúc đó cần phân biệt:

- **Classpath**: cơ chế tìm lớp truyền thống, nơi các JAR thường được xử lý như thành phần trên classpath.
- **Module path**: nơi JVM/compiler tìm các module có định danh và quy tắc phụ thuộc rõ ràng.

Không phải dự án Java nào cũng cần khai báo module. Phần lớn ví dụ nhập môn và nhiều ứng dụng vẫn sử dụng classpath. Chỉ dùng module path khi cấu trúc dự án thực sự áp dụng JPMS.

## 10. Những điều cần ghi nhớ

- JDK là bộ công cụ phát triển; cần kiểm tra đúng JDK mà terminal và build tool đang sử dụng.
- `javac` chuyển mã nguồn `.java` thành bytecode `.class`; nó cần tìm được các kiểu và thư viện được tham chiếu.
- `java` khởi chạy JVM và nạp lớp chính cùng các dependency từ classpath hoặc module path.
- `jar` đóng gói các lớp, tài nguyên và metadata. JAR có `Main-Class` có thể chạy bằng `java -jar`, nhưng dependency không tự động được bao gồm chỉ vì có thuộc tính này.
- Gradle/Maven điều phối việc biên dịch, xử lý tài nguyên, kiểm thử và đóng gói để quy trình build có thể lặp lại.
- Phiên bản JDK dùng để build, phiên bản bytecode/API mục tiêu và phiên bản Java dùng để chạy là các thông tin liên quan nhưng không đồng nghĩa.

Khi đọc một lệnh build Java, hãy lần lượt xác định công cụ nào đang được gọi, đầu vào của nó là gì, đầu ra được đặt ở đâu và công đoạn tiếp theo sử dụng đầu ra đó như thế nào. Cách đọc này giúp hiểu được cả quy trình build thủ công lẫn những task mà Gradle hoặc Maven tự động hóa.
