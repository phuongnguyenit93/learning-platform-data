# Main-Class, Class-Path và điều kiện chạy java -jar

## 1. Vì sao Maven tạo JAR thành công nhưng `java -jar` vẫn thất bại?

Sau khi chạy `mvn package`, Maven có thể tạo một file như:

```text
target/manifest-classpath-demo-1.0.0.jar
```

Tuy nhiên, **tạo JAR thành công không đồng nghĩa JAR đó tự chạy được bằng `java -jar`**. Một JAR thông thường chỉ là ZIP có cấu trúc chuẩn, chứa class files, resources và metadata. Để Java launcher biết **điểm vào ứng dụng**, và để ứng dụng tìm được **các thư viện bên ngoài**, cần phân biệt:

1. **`Main-Class`** trong `META-INF/MANIFEST.MF`: chỉ định fully qualified name của lớp có phương thức `public static void main(String[] args)`.
2. **`Class-Path`** trong manifest: liệt kê **đường dẫn/URL tương đối** đến các JAR hoặc thư mục phụ thuộc mà application class loader cần.
3. **Runtime JDK, nội dung JAR, thư viện thực tế trên đĩa và cấu trúc phân phối**: phải phù hợp với các thông tin trên.

Điều kiện tối thiểu để `java -jar application.jar` chạy thành công phụ thuộc vào mã của ứng dụng, nhưng thường bao gồm:

- File JAR đọc được, có manifest hợp lệ.
- Manifest có `Main-Class` trỏ tới một lớp thực sự có thể load được.
- Lớp có main method với chữ ký được Java launcher hỗ trợ.
- Runtime Java hỗ trợ bytecode/API mà lớp và dependencies sử dụng.
- Các class/resources/thư viện cần khi chạy đều được tìm thấy trên **classpath hiệu lực của invocation `-jar`**.
- Cấu hình, files, environment và services mà ứng dụng cần tồn tại khi chạy.

**Một file `.jar` không tự trở thành fat/uber JAR** chỉ vì bạn thêm `Main-Class`. Các `<dependencies>` trong Maven POM được Maven dùng để dựng dependency graph; chúng **không tự được nhét vào JAR thường** do Maven Jar Plugin tạo.

## 2. Manifest là gì và nằm ở đâu?

JAR về bản chất là ZIP archive theo quy ước Java. File manifest nằm tại:

```text
META-INF/MANIFEST.MF
```

Một manifest tối giản cho ứng dụng:

```text
Manifest-Version: 1.0
Main-Class: dev.lesson.launcher.App

```

Dòng trống sau các main attributes kết thúc main section theo định dạng manifest. Các công cụ `jar`/Maven Archiver thường tạo đúng cú pháp và dấu xuống dòng, vì vậy nên **để chúng tạo manifest thay vì chỉnh tay file đóng gói**.

Với một thư viện phụ thuộc bên ngoài, có thể có thêm:

```text
Manifest-Version: 1.0
Main-Class: dev.lesson.launcher.App
Class-Path: lib/commons-lang3-3.14.0.jar

```

**Đây chỉ là ba thuộc tính quan trọng được rút gọn**. Manifest thật có thể có thêm `Created-By`, `Build-Jdk-Spec` hoặc entries khác; thứ tự dòng không cần trùng ví dụ. Các dòng dài trong manifest có thể được *fold* theo định dạng JAR manifest, nên phần hiển thị thực tế có thể xuống dòng kèm dấu cách mở đầu dòng tiếp theo.

### Ba điều không nên làm khi khai `Main-Class`

- Không viết `Main-Class: App.java` — manifest cần **tên lớp**, không phải file mã nguồn.
- Không viết `Main-Class: dev/lesson/launcher/App.class` — phải dùng **fully qualified binary class name** với dấu chấm, ví dụ `dev.lesson.launcher.App`.
- Không viết `Main-Class: target/classes/dev/lesson/launcher/App` — đường dẫn build không phải tên lớp.

Nếu một project có nhiều class chứa `main`, manifest chỉ chọn **một entry point chính** cho invocation `java -jar`. Các main class khác vẫn có thể được gọi qua `java -cp ... fully.qualified.OtherMain` khi classpath phù hợp.

## 3. `Main-Class` cho Java launcher biết điều gì?

Một Java 17 class có entry point hợp lệ:

```java
package dev.lesson.launcher;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("READY");
    }
}
```

Các chi tiết cần khớp:

- Package là `dev.lesson.launcher`.
- Class là `App`.
- Tên đầy đủ là `dev.lesson.launcher.App`.
- Trong JAR có entry `dev/lesson/launcher/App.class`.
- Phương thức `main` là `public static void`, nhận `String[]`; JVM launcher có thể gọi đúng chữ ký.
- `Main-Class` trong manifest là `dev.lesson.launcher.App`.

Nếu JAR có class này nhưng thiếu `Main-Class`, người dùng vẫn có thể chạy bằng `-cp` và chỉ định main class tường minh. Nhưng lệnh `java -jar` **không biết phải chọn lớp nào**.

**Phân biệt:**

```bash
java -cp app.jar dev.lesson.launcher.App
```

chỉ định tên main class **trên command line**, còn:

```bash
java -jar app.jar
```

lấy tên main class **từ manifest của `app.jar`**.

## 4. Khác biệt quan trọng giữa `-cp` và `-jar`

| Lệnh | Main class lấy từ đâu? | Classpath của ứng dụng lấy từ đâu? |
| --- | --- | --- |
| `java -cp "app.jar:lib/*" dev.lesson.launcher.App` | Đối số lớp sau `-cp` | Từ `-cp`, cộng cơ chế manifest classpath của JAR được load khi áp dụng |
| `java -jar app.jar` | `Main-Class` của `app.jar` | JAR được chỉ định và các manifest `Class-Path` entries hợp lệ |
| `java -cp "app.jar" dev.lesson.launcher.App` | Đối số lớp | `app.jar`, có thể mở rộng qua manifest của các JAR trong classpath |
| `java -jar app.jar first second` | Manifest | Tương tự `-jar`; `first second` chuyển vào `main(args)` |

**Mấu chốt:** với `java -jar`, **các thiết lập classpath khác từ `-cp`/`-classpath` hoặc biến môi trường `CLASSPATH` không được Java launcher sử dụng để bổ sung user classes**. Vì vậy lệnh sau **không phải cách đáng tin để thêm dependency vào một JAR đang chạy bằng `-jar`**:

```bash
java -cp "lib/*" -jar app.jar
```

Theo Java launcher documentation, khi chọn chế độ `-jar`, những classpath settings khác bị bỏ qua; phải sửa cách đóng gói, manifest `Class-Path` hoặc dùng `-cp` với main class tường minh.

### Classpath separator khác manifest `Class-Path` separator

Ở **Linux/macOS**, separator của option `-cp` là dấu hai chấm:

```bash
java -cp "app.jar:lib/*" dev.lesson.launcher.App
```

Ở **Windows**, separator của `-cp` là dấu chấm phẩy:

```powershell
java -cp "app.jar;lib/*" dev.lesson.launcher.App
```

Nhưng trong **manifest**:

```text
Class-Path: lib/a.jar lib/b.jar
```

các URL entries được phân tách bằng **khoảng trắng**, không phải dấu `:` hay `;`. `Class-Path` trong manifest là một format riêng, không phải chuỗi trực tiếp từ `java -cp`.

### Wildcard `*` không phải cú pháp manifest thông thường

Java launcher hỗ trợ `lib/*` trong option `-cp` để mở rộng các JAR trong thư mục. **Không dựa vào `Class-Path: lib/*` trong manifest như cách thay thế**; các manifest classpath entries cần chỉ đến các JAR/thư mục theo URL hợp lệ, và không được xử lý như wildcard launcher.

Khi dùng Maven Jar Plugin với `<addClasspath>true</addClasspath>`, Maven Archiver có thể ghi các JAR dependencies theo tên cụ thể:

```text
Class-Path: lib/commons-lang3-3.14.0.jar
```

Nếu có nhiều dependencies:

```text
Class-Path: lib/api-1.0.0.jar lib/util-2.0.0.jar
```

Đây là **hai ví dụ manifest độc lập**, không phải cùng một manifest có hai header `Class-Path`. Chỉ nên có **một header `Class-Path`** theo đặc tả JAR.

## 5. `Class-Path` trỏ tới file ở đâu?

Manifest `Class-Path` dùng các relative URLs **so với vị trí JAR chứa manifest**, không phải mặc định so với shell current working directory.

Giả sử bạn có:

```text
/opt/my-app/
├── manifest-classpath-demo-1.0.0.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

và manifest trong file app JAR:

```text
Main-Class: dev.lesson.launcher.App
Class-Path: lib/commons-lang3-3.14.0.jar
```

Java launcher có thể tìm thư viện ở:

```text
/opt/my-app/lib/commons-lang3-3.14.0.jar
```

Kể cả khi chạy từ thư mục khác:

```bash
cd /tmp
java -jar /opt/my-app/manifest-classpath-demo-1.0.0.jar
```

**Classpath entry vẫn được resolve từ context JAR**, không phải `/tmp/lib`. Điều kiện là runtime và file thực tế đều hợp lệ.

### Đổi vị trí hoặc chỉ copy JAR sẽ dẫn tới điều gì?

Nếu bạn chỉ đưa:

```text
/home/user/downloads/manifest-classpath-demo-1.0.0.jar
```

mà **không đưa theo thư mục `lib/`**, manifest vẫn trỏ tới `lib/commons-lang3-3.14.0.jar` tương ứng ở vị trí mới — lúc này file chưa tồn tại. Java có thể load main class nhưng đến lúc gọi `org.apache.commons.lang3.StringUtils` sẽ xảy ra `NoClassDefFoundError`.

Vì vậy hãy phân phối **JAR cùng các thư viện phụ thuộc theo đúng layout**, hoặc tạo artifact phân phối khác phù hợp như fat JAR. **Chỉ đổi `Class-Path` trong manifest không tạo ra thư viện và không tải chúng từ Maven repository vào runtime.**

### Đường dẫn tương đối và các lưu ý của JAR specification

- Các entries là **relative URLs** tới JARs/thư mục; JAR không phải script shell.
- Nên dùng dấu `/` trong URL path của manifest, kể cả trên Windows.
- Tránh các file paths có spaces/ký tự cần URL escaping nếu không kiểm soát quy tắc encode.
- Tránh dùng absolute/remote URL hoặc thao tác `../` vượt thư mục chứa JAR như một thiết kế phân phối mặc định; đặc tả có các ràng buộc và ngoại lệ theo code base.
- JAR entry không tồn tại/không resolve được có thể bị bỏ qua khi dựng classpath; lỗi class loading có thể chỉ xuất hiện khi code thực sự dùng dependency đó.
- Đặt đúng tên file, version và classifier. `commons-lang3-3.13.0.jar` **không thay thế** `commons-lang3-3.14.0.jar` nếu manifest đã ghi tên cụ thể của version 3.14.0.

## 6. Maven làm gì khi `mvn package`?

Với packaging `jar`, Maven lifecycle thường chạy các goals:

```text
process-resources  -> resources:resources
compile            -> compiler:compile
test-compile       -> compiler:testCompile
test               -> surefire:test
package            -> jar:jar
```

Maven Jar Plugin đóng gói `target/classes` và resources thành primary JAR. Nhưng **mặc định nó không phải plugin “đóng toàn bộ dependencies vào một executable JAR”**.

Ví dụ POM chỉ có:

```xml
<groupId>dev.lesson</groupId>
<artifactId>my-app</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
```

là **đoạn POM minh họa**, chưa phải POM đầy đủ. Nó có thể tạo `target/my-app-1.0.0.jar` nhưng không tự cung cấp `Main-Class`.

### Hai tầng cấu hình khác nhau

1. `maven-jar-plugin` (qua Maven Archiver): tạo/điều chỉnh **manifest** và đóng gói chính JAR.
2. `maven-dependency-plugin` hoặc công cụ phân phối tương đương: **sao chép/đặt các dependency JAR thực sự** vào vị trí mà manifest `Class-Path` tham chiếu.

Khai `<addClasspath>true</addClasspath>` ở Jar Plugin chỉ tạo danh sách đường dẫn. Nó **không tự copy các dependency vào `lib/`**. Ngược lại, chỉ chạy Dependency Plugin để copy JAR mà không tạo manifest classpath cũng chưa tự làm `java -jar` biết nơi tìm dependencies.

## 7. Thực hành Java 17 đầy đủ: executable JAR + thư mục `lib/`

Ví dụ này có một ứng dụng dùng **Apache Commons Lang**. Chúng ta sẽ tạo:

- Một JAR thông thường của ứng dụng, có `Main-Class` và `Class-Path`.
- Một thư mục `lib` chứa dependency JAR thực tế.
- Một command `java -jar` chạy thành công khi **hai phần được đặt đúng chỗ**.

**Yêu cầu:** JDK 17+, Maven tương thích Compiler Plugin 3.13.0 và các plugin versions trong POM, có thể tải Maven plugins và `commons-lang3:3.14.0` từ Maven Central hoặc repository mirror hợp lệ.

### 7.1. Cấu trúc trước và sau build

Chỉ tạo các file source:

```text
manifest-classpath-demo/
├── pom.xml
└── src/main/java/dev/lesson/launcher/App.java
```

Sau `mvn clean package`, Maven tạo:

```text
manifest-classpath-demo/
├── pom.xml
├── src/main/java/dev/lesson/launcher/App.java
└── target/
    ├── classes/
    │   └── dev/lesson/launcher/App.class
    ├── lib/
    │   └── commons-lang3-3.14.0.jar
    └── manifest-classpath-demo-1.0.0.jar
```

`target/lib` chứa JAR thực tế. `Class-Path` sẽ trỏ tới `lib/commons-lang3-3.14.0.jar` **tính từ vị trí file JAR trong `target`**.

### 7.2. POM hoàn chỉnh — `manifest-classpath-demo/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>manifest-classpath-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
                <executions>
                    <execution>
                        <id>copy-runtime-libraries</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <outputDirectory>${project.build.directory}/lib</outputDirectory>
                            <includeScope>runtime</includeScope>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.launcher.App</mainClass>
                            <addClasspath>true</addClasspath>
                            <classpathPrefix>lib/</classpathPrefix>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Từng thành phần có nhiệm vụ cụ thể:

- `commons-lang3:3.14.0` là dependency **runtime cần thiết**; scope mặc định là `compile`, nên nó được dùng ở compile và runtime classpath.
- `maven.compiler.release=17` chọn ngôn ngữ/API/bytecode đích Java 17.
- Dependency Plugin goal `copy-dependencies` chạy ở **`prepare-package`**, trước `package`, copy các runtime-relevant dependencies từ Maven repository sang `target/lib`. `includeScope=runtime` bao gồm các dependency có hiệu lực trên runtime classpath (thường cả compile và runtime), chứ không phải chỉ dependency khai chính xác `<scope>runtime</scope>`.
- Jar Plugin cấu hình `Main-Class` qua `<mainClass>`.
- `<addClasspath>true</addClasspath>` yêu cầu Maven Archiver sinh `Class-Path` từ dependency classpath được chọn.
- `<classpathPrefix>lib/</classpathPrefix>` thêm tiền tố `lib/` vào tên dependency trong manifest.
- Hai plugin phối hợp: **một plugin chuẩn bị file thư viện**, **một plugin ghi đường dẫn tham chiếu vào manifest**.

**Điểm thiết kế:** demo chỉ có một dependency compile/runtime và không có thư viện runtime bắc cầu cần copy; với nhiều dependencies, Dependency Plugin mặc định cũng xử lý transitives phù hợp. Khi dùng cấu hình flatten/rename/classifier khác, phải bảo đảm **tên file thư viện được copy khớp từng entry manifest**.

### 7.3. Java source — `src/main/java/dev/lesson/launcher/App.java`

```java
package dev.lesson.launcher;

import java.util.Arrays;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String message = StringUtils.capitalize("jar manifest works");
        System.out.println("MESSAGE=" + message);
        System.out.println("ARGS=" + Arrays.toString(args));
    }
}
```

Kiểm tra ngữ nghĩa:

1. Class được đóng gói thành `dev/lesson/launcher/App.class`.
2. Main method có chữ ký Java launcher chấp nhận.
3. `StringUtils.capitalize` thực sự đến từ **Commons Lang 3**; nếu Commons Lang JAR không có trên runtime classpath, chương trình lỗi khi cần nạp class phụ thuộc.
4. `Arrays.toString(args)` giúp thấy các đối số **sau tên JAR** được đưa vào `main`.

### 7.4. Build và kiểm tra các file tạo ra

Đứng tại thư mục `manifest-classpath-demo/`:

```bash
mvn -version
mvn -B -ntp clean package
```

Nếu quá trình resolve Maven plugin/dependency và compile/package thành công, tìm:

```text
target/manifest-classpath-demo-1.0.0.jar
target/lib/commons-lang3-3.14.0.jar
```

Đây là **đường dẫn file dự kiến**, không phải stdout của Maven. Nếu chỉ thấy app JAR mà không có `target/lib`, kiểm tra execution `copy-runtime-libraries`, phase `prepare-package` và log Dependency Plugin.

Kiểm tra nội dung app JAR:

```bash
jar tf target/manifest-classpath-demo-1.0.0.jar
```

Tìm các entry:

```text
META-INF/MANIFEST.MF
dev/lesson/launcher/App.class
```

Đây là những entry **cần tìm trong output dài**, không phải toàn bộ danh sách của `jar tf`.

**Không mong chờ entry `org/apache/commons/lang3/StringUtils.class` ở app JAR:** đó là class trong dependency JAR riêng `target/lib/commons-lang3-3.14.0.jar`. Nó không được Maven Jar Plugin nhét vào app JAR trong cách đóng gói skinny JAR này.

### 7.5. Đọc manifest thật

Trên Linux/macOS có cài `unzip`:

```bash
unzip -p target/manifest-classpath-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Trong output, tìm các thuộc tính quan trọng:

```text
Main-Class: dev.lesson.launcher.App
Class-Path: lib/commons-lang3-3.14.0.jar
```

Manifest thật có thể thêm `Manifest-Version`, `Created-By` hoặc các thuộc tính khác; thứ tự dòng cũng có thể khác.

Nếu không có `unzip`, bạn có thể dùng `jar xf` trong **thư mục thử nghiệm riêng** để tránh ghi đè files thuộc project:

```bash
mkdir -p inspect-jar
cd inspect-jar
jar xf ../target/manifest-classpath-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
```

Đoạn này là **Bash/Linux/macOS**. Trên Windows PowerShell, dùng một thư mục làm việc tạm và `jar xf` với đường dẫn phù hợp; không chạy `cat`/`mkdir -p` nguyên xi như giả định chúng là lệnh POSIX.

Nếu manifest có dòng dài bị wrap, phải đọc **các dòng continuation** theo đặc tả, không tưởng tên JAR bị cắt thành hai entries.

### 7.6. Chạy bằng `java -jar`: kết quả mong đợi

Tại project root, sau build:

```bash
java -jar target/manifest-classpath-demo-1.0.0.jar
```

**Stdout chính xác của chương trình Java:**

```text
MESSAGE=Jar manifest works
ARGS=[]
```

Chạy với hai đối số:

```bash
java -jar target/manifest-classpath-demo-1.0.0.jar alpha beta
```

**Stdout chính xác:**

```text
MESSAGE=Jar manifest works
ARGS=[alpha, beta]
```

Vì mã chỉ in kết quả của `StringUtils.capitalize` và `Arrays.toString(args)`, không có output phụ thuộc thời gian, môi trường hoặc hệ điều hành trong điều kiện runtime chuẩn.

**Lưu ý:** JVM có thể in lỗi/cảnh báo riêng ra stderr nếu cấu hình môi trường có vấn đề; hai khối output ở trên là stdout **của chương trình khi chạy thành công**, không phải cam kết mọi invocation Maven/JVM đều chỉ có những dòng đó.

### 7.7. Chạy bằng `-cp` để so sánh

Linux/macOS, đứng tại project root:

```bash
java -cp "target/manifest-classpath-demo-1.0.0.jar:target/lib/*" dev.lesson.launcher.App
```

Windows PowerShell:

```powershell
java -cp "target/manifest-classpath-demo-1.0.0.jar;target/lib/*" dev.lesson.launcher.App
```

Nếu thư viện tồn tại, stdout của `main` vẫn:

```text
MESSAGE=Jar manifest works
ARGS=[]
```

Ở đây tên main class được chỉ định **trực tiếp**; option `-cp` cũng cấp JAR ứng dụng và toàn bộ các `*.jar` trong `target/lib` qua wildcard mà Java launcher hỗ trợ. Dù app JAR có manifest, cách chạy `-cp` này **không cần dùng `Main-Class` để chọn điểm vào**.

### 7.8. Bước kiểm chứng thiếu thư viện — thực hiện trên bản sao

Sao chép cặp phân phối `app.jar + lib/` sang một thư mục thử nghiệm khác, rồi đổi tên/move `lib/` ra ngoài vị trí dự kiến **trên bản sao**. Đừng phá cấu trúc `target/` gốc nếu đang dùng làm output của CI.

Khi chạy:

```bash
java -jar manifest-classpath-demo-1.0.0.jar
```

và thư viện `lib/commons-lang3-3.14.0.jar` bị thiếu, chương trình sẽ **không hoàn tất thành công**. Lỗi điển hình:

```text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Stacktrace/prefix có thể khác theo Java version. Điều này chứng minh **`Main-Class` đúng nhưng điều kiện runtime dependency vẫn chưa được thỏa mãn**.

Đặt lại đúng thư mục `lib` bên cạnh file JAR, rồi chạy lại `java -jar`. Trình tự này minh họa rõ ràng **manifest chỉ tham chiếu file**, không chứa hoặc tải file hộ bạn.

## 8. Ví dụ thuần JDK: `Main-Class` không cần dependency ngoài

Để cô lập vai trò của `Main-Class`, có thể dùng Java 17 `jar` tool mà không cần Maven hoặc thư viện bên ngoài.

Tạo file `manual/src/demo/Hello.java`:

```java
package demo;

public final class Hello {
    private Hello() {
    }

    public static void main(String[] args) {
        System.out.println("HELLO=java -jar");
    }
}
```

Trên Linux/macOS (Bash), từ thư mục chứa `manual/`:

```bash
mkdir -p manual/classes
javac --release 17 -d manual/classes manual/src/demo/Hello.java
jar --create --file manual/hello.jar --main-class demo.Hello -C manual/classes .
java -jar manual/hello.jar
```

**Stdout chính xác:**

```text
HELLO=java -jar
```

`jar --main-class demo.Hello` ghi điểm vào manifest. Vì chương trình không dùng thư viện ngoài nên không cần manifest `Class-Path`.

Kiểm tra manifest bằng `unzip -p manual/hello.jar META-INF/MANIFEST.MF` nếu có `unzip`. Thường sẽ có `Main-Class: demo.Hello`.

Nếu bỏ option `--main-class demo.Hello` khi đóng gói, file `hello.jar` vẫn là JAR hợp lệ nhưng không có entry point. Khi đó `java -jar manual/hello.jar` có thể báo `no main manifest attribute`, còn:

```bash
java -cp manual/hello.jar demo.Hello
```

vẫn chạy nếu class `demo.Hello` có trong JAR.

**Windows:** `javac`, `jar` và `java` dùng cú pháp tương tự; sửa lệnh tạo thư mục phù hợp PowerShell và dùng đường dẫn Windows nếu cần. Các công cụ JDK 17 nhận cả nhiều đường dẫn có dấu `/` trong thực hành nhưng không phụ thuộc shell giống Bash.

## 9. Maven Jar Plugin: cách cấu hình `Main-Class` đúng nơi

Đoạn cốt lõi trong POM:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>dev.lesson.launcher.App</mainClass>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn POM**, cần đặt trong `<project>` hoàn chỉnh. Nó tạo `Main-Class` nhưng **chưa tự đảm bảo dependencies được tìm thấy**.

Muốn thêm đường dẫn dependency:

```xml
<configuration>
    <archive>
        <manifest>
            <mainClass>dev.lesson.launcher.App</mainClass>
            <addClasspath>true</addClasspath>
            <classpathPrefix>lib/</classpathPrefix>
        </manifest>
    </archive>
</configuration>
```

Nhớ rằng:

- `archive/manifest/mainClass` thuộc **Maven Jar Plugin / Maven Archiver**, không phải `maven-compiler-plugin`.
- `<addClasspath>true</addClasspath>` yêu cầu Maven Archiver liệt kê dependencies theo classpath layout.
- `<classpathPrefix>lib/</classpathPrefix>` điều chỉnh **tên đường dẫn trong manifest**, không đổi output directory của compiler và không tự tạo `lib/`.
- Cần một bước chuẩn bị **thư viện vật lý đúng tên, đúng layout** để chạy `java -jar` trên máy khác.

### Khi nào dùng `<manifestEntries>`?

Maven Archiver cũng cho phép thêm manifest attributes tùy ý:

```xml
<archive>
    <manifestEntries>
        <Implementation-Title>Manifest Classpath Demo</Implementation-Title>
        <Implementation-Version>1.0.0</Implementation-Version>
    </manifestEntries>
</archive>
```

Đây chỉ là **đoạn minh họa metadata**, không tạo `Main-Class` nếu thiếu cấu hình tương ứng. Khi cần những thuộc tính launcher chuẩn như `Main-Class`/`Class-Path`, thường ưu tiên API `<manifest>` của Archiver thay vì tự thêm duplicate headers bằng `manifestEntries`.

Tránh có nhiều header `Class-Path`, nhiều nguồn manifest xung đột hoặc sử dụng một manifest template cũ vô tình ghi đè Main-Class.

## 10. Phân biệt thin/skinny JAR, fat/uber JAR và launcher tùy biến

| Kiểu đóng gói | JAR chính chứa gì? | Cách chạy | Ghi chú |
| --- | --- | --- | --- |
| **Thường/skinny JAR** có manifest | App classes/resources, không gộp dependency classes | `java -jar app.jar` nếu `Class-Path` trỏ đúng JARs ngoài | Phải phân phối `app.jar + lib/` |
| **Fat/uber JAR** | App classes cộng nhiều dependency classes đã merge/transform | `java -jar all.jar` nếu có entry point | Cần plugin đóng gói như Shade/Assembly và xử lý tài nguyên trùng |
| **Executable framework JAR** | Có thể chứa nested JARs và launcher riêng | `java -jar app.jar` theo quy ước framework | `Main-Class` thường trỏ launcher, không nhất thiết class của người dùng |
| **Non-executable library JAR** | API/classes để dự án khác dùng | Thông thường **không** gọi `java -jar` | Không cần `Main-Class` |

**Maven Jar Plugin thường không tạo fat JAR.** Nếu bạn cần chỉ **một file** mang theo dependencies, cân nhắc Maven Shade Plugin hoặc framework packaging plugin phù hợp.

### Ví dụ về Maven Shade Plugin (đoạn cấu hình minh họa)

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>dev.lesson.launcher.App</mainClass>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây **không phải phần của POM demo skinny JAR ở mục 7**. Nếu chuyển sang Shade, phải chủ động thiết kế artifact phân phối mới, loại trừ duplicate metadata/signature files khi cần, merge service descriptors qua transformer thích hợp và chạy lại tests.

**Một JAR có các nested `lib/*.jar` entries không tự làm Java launcher tiêu chuẩn load những JAR lồng nhau.** Các framework như Spring Boot dùng launcher/class loader riêng để giải quyết vấn đề đó. Vì thế đừng tạo một ZIP chứa các JAR bên trong rồi mặc định `java -jar` sẽ tự load chúng.

### Fat JAR cũng có hạn chế

- Trùng file `META-INF/services`, license/notice, resources hoặc class có thể cần merge strategy.
- Signed JAR metadata có thể không còn hợp lệ khi gộp/transform.
- File lớn hơn, khó thay từng dependency độc lập.
- Native libraries và module metadata có thể đòi hỏi cách xử lý riêng.
- Không phải bất kỳ JAR “có Main-Class” nào cũng được coi là tự chứa toàn bộ dependencies.

Chọn kiểu đóng gói dựa trên cách vận hành/triển khai, không chỉ để sửa nhanh `NoClassDefFoundError`.

## 11. Các scope của Maven ảnh hưởng runtime `Class-Path` ra sao?

Khi Maven build dependency graph, mỗi dependency có scope. Trong ví dụ demo, `commons-lang3` mặc định là `compile`, vì vậy được dùng khi compile và khi chạy.

| Scope | Vai trò điển hình trong app | Có nên kỳ vọng trên runtime? |
| --- | --- | --- |
| `compile` | API thư viện mà code chính sử dụng | Có |
| `runtime` | Driver/implementation cần lúc chạy | Có |
| `provided` | API được container/JDK/môi trường cung cấp | Thông thường **không** được phân phối làm runtime dependency của app |
| `test` | JUnit, test utilities | **Không** cho app runtime thông thường |
| `system` | Đường file local đặc biệt, ít được khuyến nghị | Khó tái lập; tránh lạm dụng |
| `import` | Chỉ dùng bên trong dependencyManagement với type POM | Không phải runtime JAR |

Không phải mọi dependency trong `pom.xml` đều được liệt kê vào manifest `Class-Path`. Một bản `jar` độc lập muốn chạy đúng cần **toàn bộ runtime dependency closure phù hợp**, không có JAR dư hoặc thiếu do cấu hình copy/phân phối sai.

**Tình huống thường gặp:** ứng dụng dùng JDBC API nhưng driver thực tế cần ở runtime. Nếu dependency driver có scope `runtime`, Maven Jar Plugin/Maven Archiver và bước copy-dependencies phải bao gồm driver đó trong layout phân phối.

### Transitive dependencies

Nếu `client.jar` kéo theo `core.jar` qua dependency graph, chạy app có thể cần cả hai. Hãy dùng:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

để xem graph thực tế. Đừng nhìn chỉ những dependency khai trực tiếp trong POM rồi bỏ qua JAR bắc cầu. Với bố cục `lib/` chứa mọi resolved runtime JAR, có thể dùng một lệnh để kiểm tra danh sách nhưng **vẫn cần so manifest với file vật lý**.

### Trường hợp tên JAR xung đột

Hai artifacts khác nhau có thể có cùng tên file khi flatten vào `lib` (hiếm nhưng có thể nếu groupId khác, artifactId/version trùng). Khi đó copy-dependencies có thể ghi đè/tạo collision tùy config. Nên dùng layout có groupId hoặc một packaging/distribution plugin phù hợp, và **đồng bộ `classpathLayoutType` với tên file đã copy** thay vì ngầm tin flatten luôn an toàn.

## 12. Kiểm chứng một bộ phân phối hoàn chỉnh

Một build nội bộ chạy được chưa chắc artifact được copy sang máy khác vẫn hoạt động. Hãy kiểm tra một **distribution directory** riêng.

Giả sử sau build bạn đưa các file vào:

```text
release/
├── manifest-classpath-demo-1.0.0.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

Chạy từ vị trí bất kỳ bằng đường dẫn tới JAR:

```bash
java -jar release/manifest-classpath-demo-1.0.0.jar
```

Kỳ vọng nếu runtime Java đúng và library đủ:

```text
MESSAGE=Jar manifest works
ARGS=[]
```

Sau khi đóng gói `release/` thành ZIP, hãy **giải nén vào một thư mục sạch trên máy/runner khác** rồi chạy lại. Không dùng Maven local repository trên máy developer như một dependency runtime “vô hình”: `java -jar` **không tự đọc `~/.m2/repository` chỉ vì Maven từng build ở đó**.

### Câu hỏi cần trả lời trước khi giao ứng dụng

1. Đã có `META-INF/MANIFEST.MF` chưa?
2. Có đúng `Main-Class: dev.lesson.launcher.App` không?
3. JAR có `App.class` đúng đường dẫn package chưa?
4. `App.main(String[])` tồn tại và có đúng access modifier?
5. `Class-Path` liệt kê đúng những JAR thư viện cần thiết chưa?
6. Các JAR ngoài có thật và ở đúng đường dẫn tương đối so với app JAR chưa?
7. Runtime JDK trên máy đích có hỗ trợ major version của class files không?
8. Các biến môi trường, config files, native libs, certificates và service endpoints có đủ chưa?
9. Việc chạy từ thư mục khác có làm app sai do đọc **relative application config paths** riêng không? (Phân biệt đường dẫn config của app với manifest classpath.)
10. Build CI có smoke test với **artifact cuối và đúng layout phân phối**, không chỉ với `target/classes` không?

## 13. Chẩn đoán lỗi: từ manifest đến classpath

| Thông báo/triệu chứng | Nguyên nhân thường gặp | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| `no main manifest attribute` | Không có `Main-Class` phù hợp | Kiểm tra `META-INF/MANIFEST.MF`, cấu hình Maven Jar Plugin |
| `Could not find or load main class ...` | `Main-Class` trỏ sai class, class không nằm trong JAR, lỗi load dependency | Kiểm tra FQCN, `jar tf`, `Class-Path`, stacktrace |
| `Main method not found in class...` | Lớp không có `public static void main(String[] args)` hợp lệ | Sửa class/entry point; rebuild |
| `NoClassDefFoundError` | Dependency hoặc class runtime thiếu, đôi khi do initialization thất bại | Tìm missing class trong JARs thực tế; xem full cause chain |
| `ClassNotFoundException` | Code/class loader cố nạp class không tìm được | Kiểm tra tên class, dependency scope và runtime classpath |
| `UnsupportedClassVersionError` | JVM runtime quá cũ so với bytecode của app/dependency | Kiểm tra `java -version`, `javap -verbose`, release đích |
| `Invalid or corrupt jarfile` | JAR hỏng, định dạng không hợp lệ, file sai loại | Kiểm tra JAR thực tế, rebuild/checksum |
| Build success nhưng chạy sai thư viện version | Manifest tên file/`lib` layout khác version đã copy, duplicate classes | So manifest với file trong `lib` và dependency tree |
| `java -cp ... Main` chạy, `java -jar` lỗi | Thiếu Main-Class, manifest classpath sai, hoặc runtime layout khác | So sánh classpath tường minh với manifest |
| `java -jar` chạy local, lỗi máy production | Thiếu lib/config, runtime JDK khác, đường dẫn/permission khác | Test distribution giải nén sạch trên target runtime |
| `java -cp lib/* -jar ...` vẫn lỗi | `-jar` bỏ qua classpath settings khác | Sửa manifest/lib hoặc chạy `-cp` + main class |
| JAR có `lib/*.jar` bên trong nhưng không load | Nested JARs không tự được standard class loader mở | Dùng launcher/framework packaging hoặc Shade |
| Output đúng rồi bỗng lỗi khi đổi `cwd` | App đọc relative file config dựa vào working directory | Sửa config path resolution; đừng nhầm với manifest `Class-Path` |

### Thứ tự kiểm tra thực tế

**Bước 1 — file JAR và Java runtime:**

```bash
java -version
jar tf target/manifest-classpath-demo-1.0.0.jar
```

**Bước 2 — manifest:**

```bash
unzip -p target/manifest-classpath-demo-1.0.0.jar META-INF/MANIFEST.MF
```

**Bước 3 — thư viện runtime:**

```bash
jar tf target/lib/commons-lang3-3.14.0.jar
```

Tìm `org/apache/commons/lang3/StringUtils.class`.

**Bước 4 — thử invocation trực tiếp:**

```bash
java -cp "target/manifest-classpath-demo-1.0.0.jar:target/lib/*" dev.lesson.launcher.App
java -jar target/manifest-classpath-demo-1.0.0.jar
```

Hai lệnh trên dùng separator Bash; trên Windows dùng `;` với `-cp`. Nếu lệnh `-cp` chạy và `-jar` lỗi, so lại `Main-Class` và `Class-Path`. Nếu cả hai lỗi, tìm dependency thực tế/JDK/cause chain.

**Bước 5 — biết Maven đã resolve gì:**

```bash
mvn help:effective-pom
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Maven dependency tree giúp giải thích build-time graph; **không thay thế** việc xem file đã phát hành ra sao.

## 14. Các hiểu nhầm cần tránh

**“Có `Main-Class` nghĩa là tự chứa mọi thư viện.”** Sai. `Main-Class` chỉ chọn điểm vào. App demo cần `lib/commons-lang3-3.14.0.jar` ở bên ngoài.

**“Maven tự mang dependencies theo khi tôi copy app.jar.”** Sai với skinny JAR. Copy cả bộ phân phối hoặc dùng packaging khác.

**“`-DskipTests` làm JAR có Main-Class.”** Sai. Test skip không có vai trò cấu hình manifest. Maven Jar Plugin/Maven Archiver mới xử lý entry point của JAR ví dụ này.

**“Đặt `CLASSPATH` là đủ để `java -jar` thấy thư viện.”** Sai với launcher semantics của `-jar`: classpath settings khác bị bỏ qua. Dùng `Class-Path` manifest hoặc cách launch khác.

**“`Class-Path: lib/*` giống `java -cp lib/*`.”** Sai. Wildcard launcher `-cp` không phải cú pháp manifest `Class-Path` đáng tin.

**“Thư viện ở trong `~/.m2/repository` thì java -jar tự tìm ra.”** Sai. Maven local repository là cơ chế của Maven; standard Java launcher không tự suy ra runtime dependency graph từ POM.

**“Tôi chỉ cần `mvn package` để có executable JAR.”** Sai. Packaging `jar` mặc định tạo JAR, nhưng entry point/dependencies cần cấu hình theo mục tiêu phân phối.

**“Spring Boot JAR có nested dependencies nên mọi JAR làm vậy được.”** Sai. Boot launcher/packaging riêng giải quyết nested JAR class loading; standard `java -jar` không tự mở arbitrary nested JARs.

**“`Class-Path` trỏ từ thư mục đang mở terminal.”** Sai. Nó resolve tương đối tới **JAR chứa manifest**. Đường dẫn config riêng của ứng dụng có thể lại tính theo working directory; đừng đánh đồng.

**“Chỉ cần app classes target Java 17 thì mọi dependency chạy được trên Java 17.”** Không chắc. Runtime phải load được bytecode của **tất cả dependencies** thực sự sử dụng.

## 15. Khi nào nên dùng cách đóng gói nào?

### A. Công cụ dòng lệnh đơn giản, không dependency ngoài

Chỉ cần `Main-Class`. Dùng Maven Jar Plugin để tạo JAR hoặc `jar --create --main-class` của JDK. `Class-Path` không cần có nếu không có external libs và runtime JDK đã có APIs cần thiết.

### B. Ứng dụng nhỏ có vài thư viện, muốn dễ nâng từng JAR

Cấu trúc `app.jar + lib/` và manifest `Class-Path` là hợp lý. Dùng Maven Jar Plugin `mainClass/addClasspath/classpathPrefix` phối hợp Dependency Plugin hoặc distribution packaging. Có thể thay từng JAR một cách có kiểm soát **nhưng phải giữ version/tên/path khớp**.

### C. Chương trình phát hành “một file JAR duy nhất”

Cân nhắc Shade Plugin với manifest transformer. Kiểm thử kỹ resources/services/duplicated classes. Một file duy nhất tiện phân phối nhưng không tự bảo đảm mọi native/runtime dependency được gói hoàn toàn.

### D. Ứng dụng framework có launcher đặc thù

Dùng packaging plugin chính thức của framework (ví dụ Spring Boot). Manifest `Main-Class` có thể trỏ class launcher, còn application main class nằm ở attribute khác theo quy ước framework. Không chỉnh manifest kiểu skinny JAR làm hỏng launcher.

### E. Dịch vụ production trong container

Có thể dùng một app JAR cùng `lib`, fat JAR, module launch hoặc native image tùy quy trình vận hành. Điều quan trọng là **container image chứa JDK/JRE phù hợp, đúng artifact và đầy đủ dependencies**, đồng thời smoke test dùng **chính command** production sẽ chạy.

## 16. Bài tập tự kiểm tra

**Câu 1:** JAR có `dev/lesson/launcher/App.class` và `main` hợp lệ nhưng manifest không có `Main-Class`. `java -jar` chạy không?

**Đáp án:** Không theo launcher thông thường: cần entry point trong manifest. Có thể chạy `java -cp app.jar dev.lesson.launcher.App` nếu classpath đủ.

**Câu 2:** Manifest có `Main-Class` đúng và `Class-Path: lib/a.jar`. Nếu file thực tế nằm ở `libs/a.jar` thì sao?

**Đáp án:** Class-Path đang trỏ sai; nếu app dùng class từ `a.jar`, có thể gặp `NoClassDefFoundError`. Sửa layout hoặc manifest cho khớp.

**Câu 3:** Bạn chạy từ `/tmp` bằng `java -jar /opt/apps/app.jar`. `Class-Path: lib/a.jar` trỏ tới đâu?

**Đáp án:** Theo JAR file location: `/opt/apps/lib/a.jar`, không phải `/tmp/lib/a.jar`.

**Câu 4:** Bạn có `java -cp "app.jar:lib/*" demo.Main` chạy thành công nhưng `java -cp "lib/*" -jar app.jar` vẫn thiếu dependency. Vì sao?

**Đáp án:** Trong chế độ `-jar`, Java launcher bỏ qua các classpath settings khác. Cần manifest Class-Path đúng hoặc dùng `-cp` cùng main class tường minh.

**Câu 5:** `<addClasspath>true</addClasspath>` trong Maven Jar Plugin có tự copy JAR thư viện đến `target/lib` không?

**Đáp án:** Không. Nó ghi manifest Class-Path; việc copy do Dependency Plugin/distribution plugin hoặc bước packaging khác đảm nhiệm.

**Câu 6:** `java -jar` có cần manifest `Class-Path` cho ứng dụng không dùng thư viện ngoài không?

**Đáp án:** Không bắt buộc. Chỉ cần entry point hợp lệ cùng runtime phù hợp và đầy đủ nguồn lực của chương trình.

**Câu 7:** Cần “một file tự chạy” nhưng dependency đang nằm trong `lib` bên ngoài. Lựa chọn nào?

**Đáp án:** Dùng fat/uber JAR với công cụ như Maven Shade Plugin hoặc framework launcher, đồng thời kiểm tra merged resources và runtime compatibility; không giả định Jar Plugin thông thường tự làm việc này.

**Câu 8:** `jar tf` cho thấy `META-INF/MANIFEST.MF` nhưng `java -jar` báo no main manifest attribute. Vì sao?

**Đáp án:** Có manifest file không đồng nghĩa manifest có **Main-Class hợp lệ**. Phải đọc nội dung manifest, không chỉ kiểm tra sự tồn tại của file.

## 17. Checklist trước khi giao JAR để chạy bằng `java -jar`

- [ ] Có đầy đủ `META-INF/MANIFEST.MF` với `Main-Class` đúng tên class.
- [ ] Main class thật sự nằm trong JAR và có `public static void main(String[] args)`.
- [ ] Không nhầm tên file `.java`, `.class`, slash path với fully qualified class name.
- [ ] Xác định app là skinny JAR, fat JAR hay launcher đặc thù.
- [ ] Nếu skinny JAR có thư viện ngoài, manifest `Class-Path` có entries phù hợp.
- [ ] Các `Class-Path` entries dùng relative URL paths, space-separated, không lạm dụng wildcard.
- [ ] JARs thực tế được phân phối bên cạnh app JAR đúng layout, đúng tên/version.
- [ ] Runtime libraries đã bao gồm các transitives cần thiết, không có dependency `test` không đáng có.
- [ ] Maven build pin Compiler/Jar/Dependency plugin versions hợp lý.
- [ ] Không kỳ vọng `<addClasspath>` tự copy thư viện.
- [ ] Không kỳ vọng `-cp` hoặc `CLASSPATH` bổ sung classpath khi dùng `-jar`.
- [ ] Build thật và test `java -jar` từ một thư mục khác, bằng artifact phân phối cuối cùng.
- [ ] Đọc manifest thật bằng `unzip -p`/`jar xf` trong nơi an toàn.
- [ ] Dùng `jar tf` để đối chiếu `App.class` và dependency JAR entries.
- [ ] Kiểm tra JDK/JRE đích đủ mới cho bytecode của ứng dụng và dependencies.
- [ ] Giữ file cấu hình/secrets ở nơi phù hợp, không vô tình embed credentials vào JAR/manifest.
- [ ] CI có smoke test khi giải nén toàn bộ distribution và chạy command production dự kiến.

**Kết luận:** `Main-Class` xác định **lớp khởi chạy**, `Class-Path` trong manifest xác định **các thư viện/thư mục bên ngoài JAR cần tìm theo đường dẫn tương đối**, còn `java -jar` là **chế độ khởi chạy đọc manifest** và không dùng `-cp/CLASSPATH` như một classpath bổ sung. Với Maven, **Jar Plugin tạo manifest, Dependency Plugin (hoặc packaging khác) đặt thư viện thật vào đúng chỗ**. Chỉ khi manifest, class files, runtime libraries và JVM phù hợp, việc `java -jar` mới có thể chạy thành công.

## Tài liệu chính thức

- [Java 17 — java launcher command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Java 17 — JAR File Specification: Main-Class và Class-Path](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Apache Maven JAR Plugin — Manifest customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html)
- [Apache Maven Archiver — Set Up The Classpath](https://maven.apache.org/shared/maven-archiver/examples/classpath.html)
- [Apache Maven Dependency Plugin — Copy project dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/copying-project-dependencies.html)
- [Apache Maven Dependency Plugin — Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Shade Plugin](https://maven.apache.org/plugins/maven-shade-plugin/)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
