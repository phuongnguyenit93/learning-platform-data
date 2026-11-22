# Kiểm tra nội dung target và chạy artifact đã đóng gói bằng Maven

## 1. Mục tiêu và các khái niệm cần phân biệt

Sau khi hoàn tất dự án Java đầu tiên bằng Maven, bạn cần xác nhận **Maven đã tạo ra file gì**, **artifact chứa những gì** và **cách chạy nó trong terminal**, thay vì chỉ dừng ở dòng `BUILD SUCCESS`. Bài thực hành này đi theo luồng: build sạch → xem `target/` → kiểm tra JAR và manifest → chạy ứng dụng → xử lý lỗi.

- **`target/`:** thư mục output mặc định của Maven, nằm cạnh `pom.xml` của module.
- **`target/classes/`:** chứa bytecode `.class` đã biên dịch từ `src/main/java` và các resource lấy từ `src/main/resources`.
- **Artifact:** sản phẩm của phase `package`; với `<packaging>jar</packaging>` thường là file `.jar` trong `target/`. Dự án `war` thường tạo `.war`; loại `pom` không mặc định tạo JAR.
- **Manifest:** tập tin `META-INF/MANIFEST.MF` bên trong JAR, có thể khai báo `Main-Class` để `java -jar` biết class nào có hàm `main`.
- **Thin JAR và fat JAR:** JAR thông thường của Maven chứa class/resource của dự án nhưng không tự gom hết dependency vào trong; fat/uber JAR là sản phẩm đóng gói mở rộng khi ứng dụng có thư viện ngoài.

Các ví dụ dùng **JDK 17+**, Maven 3.x và Java tiêu chuẩn, không có dependency ngoài. Cú pháp `mvn`, `java`, `jar` hoạt động trên Windows, Linux và macOS nếu JDK/Maven đã được cài và có trong `PATH`. Riêng các lệnh xem thư mục sẽ được tách theo hệ điều hành.

## 2. Build đúng phase để có artifact

Mở terminal **tại thư mục chứa `pom.xml`**; kiểm tra công cụ rồi build:

~~~bash
java -version
javac -version
mvn -version
mvn clean package
~~~

`clean` thuộc clean lifecycle, thường xóa `target/` cũ. `package` chạy default lifecycle đến phase đóng gói: xử lý resource, compile code, compile/chạy test theo cấu hình, rồi đóng gói. Lệnh `mvn package` không tự chạy `clean`; với bài này, `mvn clean package` giúp tránh nhầm file còn sót từ lần build trước.

Trong log hãy tìm `BUILD SUCCESS` và thông tin plugin đóng gói artifact. Nếu là `BUILD FAILURE`, đọc nguyên nhân lỗi ở phase/plugin đang chạy trước khi xử lý file trong `target`; không mặc định rằng đã có JAR mới. Lần chạy đầu có thể cần mạng để Maven tải plugin/dependency.

Với Maven packaging `jar` và POM không sửa tên output, quy tắc thường là:

~~~text
target/<artifactId>-<version>.jar
~~~

Ví dụ `artifactId=demo-artifact`, `version=1.0.0` tạo `target/demo-artifact-1.0.0.jar`. Cấu hình `<build><finalName>...</finalName></build>` có thể đổi tên tệp. Với dự án đa module, mỗi module có thể có `target/` riêng; cần xác định đúng module tạo artifact.

**Đừng nhầm các phase:** `mvn compile` chỉ đủ để tạo output compile trong `target/classes`; `mvn test` chạy đến phase test nhưng chưa nhất thiết tạo JAR; `mvn package` mới thực hiện đóng gói; `mvn install` còn chép artifact vào Maven repository cục bộ sau khi hoàn tất các phase trước. Không cần `install` chỉ để chạy JAR từ `target`.

## 3. Ví dụ tự kiểm tra: một JAR ứng dụng hoàn chỉnh

Để có tên file, manifest và stdout nhất quán, hãy dùng ví dụ Java 17 sau.

### 3.1. Cấu trúc dự án trước khi build

~~~text
demo-artifact/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── org/
        │       └── example/
        │           └── App.java
        └── resources/
            └── app.properties
~~~

Đặt file `App.java` trong thư mục package tương ứng với `package org.example;`. File `app.properties` nằm ở root của `src/main/resources` nên được copy vào root của classpath trong bước `process-resources`.

### 3.2. Nội dung `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>demo-artifact</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`groupId`/`artifactId`/`version` xác định tọa độ artifact. `maven.compiler.release=17` nhắm tới Java 17 (cần JDK chạy build hỗ trợ release 17). Compiler Plugin biên dịch Java; JAR Plugin đóng gói và ghi `Main-Class: org.example.App` vào manifest. Ghim phiên bản plugin giúp build ổn định hơn giữa các máy; các phiên bản trong ví dụ là bản đã phát hành, không phải bắt buộc mọi dự án dùng giống hệt.

### 3.3. Nội dung `src/main/java/org/example/App.java`

~~~java
package org.example;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class App {
    public static void main(String[] args) throws IOException {
        try (InputStream stream =
                     App.class.getResourceAsStream("/app.properties")) {
            if (stream == null) {
                throw new IllegalStateException("Missing app.properties");
            }

            Properties properties = new Properties();
            properties.load(stream);
            System.out.println(properties.getProperty("message"));
        }
    }
}
~~~

Ứng dụng đọc resource từ **classpath**, nên khi file `app.properties` nằm trong JAR, chương trình vẫn tìm thấy resource mà không phụ thuộc vào thư mục đang đứng. `try-with-resources` đóng stream; kiểm tra `null` giúp phát hiện resource thiếu rõ ràng.

### 3.4. Nội dung `src/main/resources/app.properties`

~~~properties
message=Hello from packaged JAR!
~~~

### 3.5. Build và chạy

Tại root `demo-artifact/`:

~~~bash
mvn clean package
java -jar target/demo-artifact-1.0.0.jar
~~~

Kết quả **stdout từ ứng dụng** khi chạy thành công:

~~~text
Hello from packaged JAR!
~~~

Các log Maven khi build khác theo phiên bản và môi trường nên không coi chúng là stdout cố định của chương trình. `java -jar` sẽ dùng `Main-Class` đã cấu hình trong manifest. Trên Windows, dấu `/` trong đường dẫn tương đối trên vẫn được Java và Maven nhận; bạn cũng có thể dùng `target\demo-artifact-1.0.0.jar`.

Nếu dự án cung cấp Maven Wrapper, dùng `./mvnw clean package` trên Linux/macOS hoặc `.\mvnw.cmd clean package` trong PowerShell Windows để chạy bằng bản Maven mà dự án cấu hình. Wrapper không thay thế yêu cầu cài JDK phù hợp.

## 4. Phân tích cấu trúc `target/`

Sau build thành công, các mục tiêu biểu có dạng:

~~~text
target/
├── classes/
│   ├── app.properties
│   └── org/
│       └── example/
│           └── App.class
├── maven-archiver/
│   └── pom.properties
├── maven-status/                  # có thể có metadata compile
└── demo-artifact-1.0.0.jar        # artifact đã đóng gói
~~~

Maven có thể tạo thêm `generated-sources/`, `test-classes/`, `surefire-reports/` hay mục khác tùy plugin và bài test. Đây là cây **những mục cần hiểu**, không phải danh sách chắc chắn giống hệt trên mọi máy.

| Đường dẫn | Nguồn gốc / ý nghĩa | Cần xác minh |
| --- | --- | --- |
| `target/classes/org/example/App.class` | Bytecode sau compile của `App.java` | Có đúng package và class không? |
| `target/classes/app.properties` | Resource từ `src/main/resources` | Có resource mà chương trình cần không? |
| `target/demo-artifact-1.0.0.jar` | Artifact của phase package | Có tồn tại, không rỗng và mở được không? |
| `target/maven-archiver/` | Metadata Maven dùng khi đóng gói archive | Đây không phải file thực thi |
| `target/test-classes/` | Class/resource test nếu test được compile | Không có nếu ví dụ không tạo test |
| `target/surefire-reports/` | Kết quả unit test của Surefire khi có test chạy | Xem `.txt`, `.xml` nếu được tạo |
| `target/generated-sources/`, `target/maven-status/` | File phụ trợ của một số plugin | Không phải artifact phân phối chính |

Cách xem output trên **Linux/macOS (Bash/Zsh)**:

~~~bash
ls -la target
ls -R target/classes
ls -lh target/demo-artifact-1.0.0.jar
~~~

Trên **Windows PowerShell**:

~~~powershell
Get-ChildItem .\target
Get-ChildItem .\target\classes -Recurse
Get-Item .\target\demo-artifact-1.0.0.jar
~~~

Trên **Windows Command Prompt**:

~~~bat
dir target
dir target\classes /s
dir target\demo-artifact-1.0.0.jar
~~~

Nếu chỉ có `target/classes` mà chưa có `.jar`, có thể bạn mới chạy `compile`. Nếu không có `target`, kiểm tra vị trí `pom.xml` và tình trạng build. Nếu có nhiều file `.jar` (ví dụ plugin shade hoặc plugin của framework), kiểm tra log đóng gói và cấu hình plugin để chọn đúng artifact.

## 5. Kiểm tra file *bên trong* JAR và manifest

JAR là archive tương thích ZIP. JDK có lệnh `jar tf` liệt kê entry mà không giải nén. Trên cả ba hệ điều hành:

~~~bash
jar tf target/demo-artifact-1.0.0.jar
~~~

Trong danh sách, cần tìm ít nhất:

~~~text
META-INF/
META-INF/MANIFEST.MF
org/example/App.class
app.properties
~~~

Thứ tự entry và metadata khác có thể thay đổi. File `App.java` thường không nằm trong JAR ứng dụng thông thường: ở đây Maven đóng gói file `.class`, resource và metadata, không đóng gói mã nguồn Java theo mặc định.

Để đọc manifest trên **Linux/macOS** nếu có `unzip`:

~~~bash
unzip -p target/demo-artifact-1.0.0.jar META-INF/MANIFEST.MF
~~~

Trong nội dung cần có một dòng:

~~~text
Main-Class: org.example.App
~~~

Cấu hình `mainClass` của JAR Plugin đã tạo dòng này. `Main-Class` dùng **tên đầy đủ của class** (`org.example.App`), không dùng đường dẫn file `App.java`, `App.class` hoặc tên artifact. Nếu thiếu, `java -jar` sẽ báo `no main manifest attribute` dù JAR đã tạo thành công.

Trên **Windows**, ngoài `jar tf`, có thể trích riêng manifest ra thư mục kiểm tra để đọc bằng PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\manifest-check | Out-Null
Set-Location .\manifest-check
jar xf ..\target\demo-artifact-1.0.0.jar META-INF/MANIFEST.MF
Get-Content .\META-INF\MANIFEST.MF
Set-Location ..
~~~

`manifest-check` là thư mục kiểm tra thủ công, không phải một phần mặc định của `target`. Công cụ `jar` đi kèm JDK; nếu terminal không tìm thấy lệnh, kiểm tra JDK và `PATH`.

## 6. Chạy `java -jar`, `java -cp` và `target/classes` đúng mục đích

### 6.1. `java -jar`: thực thi theo manifest

~~~bash
java -jar target/demo-artifact-1.0.0.jar
~~~

JVM mở archive, đọc `META-INF/MANIFEST.MF`, lấy `Main-Class` và gọi `public static void main(String[] args)`. Với ví dụ trên, output là `Hello from packaged JAR!`. Một JAR **không có Main-Class** vẫn có thể là thư viện hợp lệ: không phải mọi artifact JAR đều chạy được bằng `java -jar`.

### 6.2. `java -cp`: tự chỉ định class có main

~~~bash
java -cp target/demo-artifact-1.0.0.jar org.example.App
~~~

Lệnh này cũng in:

~~~text
Hello from packaged JAR!
~~~

`-cp` (hay `-classpath`) cung cấp nơi JVM tìm class và resource, còn `org.example.App` là main class. Không cần khai báo `Main-Class` trong manifest. Vì ví dụ chỉ dùng JDK, classpath một JAR là đủ.

### 6.3. Chạy từ output compile để so sánh

~~~bash
mvn compile
java -cp target/classes org.example.App
~~~

Cách này chạy bytecode và resource **chưa đóng gói**, hữu ích để so sánh output trước/sau build. Nó **không chứng minh JAR chứa đủ file**, do đó phải dùng `jar tf` và chạy file JAR sau `mvn package`.

### 6.4. Nếu ứng dụng có thư viện dependency

Maven JAR Plugin bình thường tạo **thin JAR**: chứa code/resource của dự án, nhưng không tự đưa tất cả dependency vào archive. Ví dụ trong bài chạy được vì chỉ dùng class của JDK. Khi thêm thư viện runtime bên ngoài, build có thể `BUILD SUCCESS` nhưng chạy `java -jar` báo `NoClassDefFoundError`.

Các cách đúng tùy dự án: phân phối dependency cùng JAR và cấu hình classpath/manifest hợp lệ; dùng Maven Shade Plugin (hoặc plugin đóng gói tương ứng) tạo *fat/uber JAR* chứa dependency; hoặc dùng launcher riêng của framework (ví dụ Spring Boot repackaging). Không tự giả định rằng file `.jar` nào cũng là fat JAR.

Đừng viết `java -jar app.jar -cp library.jar` với kỳ vọng Java launcher thêm thư viện: sau `-jar`, phần sau là argument của ứng dụng. Nếu cần `java -cp` với nhiều thư viện, dấu phân cách classpath trên Windows là `;` và trên Linux/macOS là `:`; phải đảm bảo mọi thư viện cần thiết đều có mặt trong classpath hoặc manifest/packaging theo cách tương ứng.

## 7. Checklist xác minh artifact trước khi bàn giao

1. **Đúng chỗ:** đang ở thư mục/module chứa `pom.xml` cần build.
2. **Build thành công:** `mvn clean package` trả về `BUILD SUCCESS`; nếu có test, xác nhận test thực sự chạy và pass.
3. **Đúng file:** `target/demo-artifact-1.0.0.jar` tồn tại, có dung lượng và khớp tọa độ artifact/tên output thực tế.
4. **Đúng nội dung:** `jar tf` có `org/example/App.class`, `app.properties` và `META-INF/MANIFEST.MF`.
5. **Đúng entry point:** manifest có `Main-Class: org.example.App` nếu artifact cần chạy bằng `java -jar`.
6. **Đúng runtime:** `java -version` trên máy thực thi là 17+, phù hợp với `maven.compiler.release`.
7. **Chạy thành công:** lệnh `java -jar ...` hiển thị đúng `Hello from packaged JAR!` và thoát bình thường.
8. **Đúng dependency:** khi dự án có thư viện ngoài, đã xác minh chúng được phân phối/đóng gói và có trên runtime classpath.

Nếu cần bàn giao artifact cho máy khác, kiểm tra nguồn file và checksum/chữ ký theo quy trình nhóm. Không chạy JAR đến từ nguồn không đáng tin cậy chỉ để xem nó hoạt động hay không.

## 8. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có `target/` | Chạy Maven sai thư mục hoặc lệnh build chưa thành công | Đứng tại module chứa `pom.xml`, chạy `mvn clean package` và đọc log |
| Có `.class` nhưng không có JAR | Mới chạy `mvn compile`, packaging khác hoặc build dừng sớm | Chạy đến `package`; kiểm tra `packaging`, `finalName` và log |
| `Unable to access jarfile` | Sai tên JAR/đường dẫn hoặc file không tồn tại | Liệt kê `target`; dùng đường dẫn thực tế, đặt đường dẫn có khoảng trắng trong dấu nháy |
| `no main manifest attribute` | JAR thiếu `Main-Class` | Xem manifest; cấu hình JAR Plugin rồi build lại, hoặc dùng `java -cp ... MainClass` |
| `Could not find or load main class` | Tên package/class sai hoặc classpath không chứa class | So sánh tên class với `jar tf`; dùng `org.example.App` thay vì chỉ `App` |
| `NoClassDefFoundError` | Runtime thiếu dependency hoặc class | Kiểm tra JAR, thư viện kèm theo, manifest và chiến lược đóng gói |
| `UnsupportedClassVersionError` | Java runtime cũ hơn release dùng để compile | So sánh `mvn -version`, `java -version`, `maven.compiler.release`; dùng runtime đủ mới |
| `Invalid or corrupt jarfile` | Archive lỗi/hỏng, file truyền thiếu, build không hoàn tất | Thử `jar tf`, build sạch hoặc tải artifact lại kèm kiểm tra checksum |
| `Missing app.properties` | Resource không được copy vào archive hoặc đường dẫn resource sai | Xác nhận `src/main/resources/app.properties`, `target/classes/app.properties` và entry trong JAR |
| Chạy trong IDE được nhưng `java -jar` lỗi | IDE bổ sung classpath/dependency/config riêng | Kiểm tra manifest, dependency và phiên bản Java khi chạy ngoài IDE |
| Không thấy `surefire-reports` | Dự án chưa có test, test bị skip hoặc plugin test chưa chạy | Đọc log phase `test` và cấu hình plugin; không khẳng định test pass khi chưa có bằng chứng |

Khi `BUILD FAILURE`, kiểm tra plugin/phase ngay trước lỗi để phân biệt lỗi compile, unit test, package hoặc tải dependency. Có thể dùng `mvn -e clean package` để xem stack trace khi cần; `mvn -X` cung cấp log debug chi tiết hơn. Đừng mặc định dùng `-DskipTests` để bỏ qua lỗi test: `-DskipTests` thường skip chạy test nhưng vẫn compile test; `-Dmaven.test.skip=true` có thể skip cả compile và chạy test. Các lựa chọn này chỉ hữu ích để điều tra, không thay thế yêu cầu test pass khi nghiệm thu.

## 9. Điều `BUILD SUCCESS` chưa chứng minh

`BUILD SUCCESS` nghĩa là Maven hoàn thành các goal/phase đã được kích hoạt và không gặp lỗi làm build thất bại. Nó không tự chứng minh JAR có main class, dependency runtime được đóng gói đủ, ứng dụng chạy trên Java của máy đích hay hành vi runtime đúng. Quy trình kiểm tra chuẩn cho ví dụ:

~~~text
pom.xml + src/main/java + src/main/resources
                     |
                     v
            mvn clean package
                     |
                     v
      target/classes + target/*.jar
                     |
                     v
    jar tf <artifact>.jar + xem manifest
                     |
                     v
         java -jar <artifact>.jar
                     |
                     v
       xác minh stdout và exit status
~~~

Với dự án mẫu, bằng chứng thành công đầy đủ là: tồn tại `target/demo-artifact-1.0.0.jar`, archive có `App.class` và `app.properties`, manifest có `Main-Class: org.example.App`, và `java -jar` in chính xác `Hello from packaged JAR!`. Với dự án lớn hơn, bổ sung kiểm tra test, dependency, cấu hình môi trường và loại packaging cho đúng thực tế.

**Tài liệu tham khảo chính thức:** [Maven Getting Started](https://maven.apache.org/guides/getting-started/) · [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) · [Maven Java Version](https://maven.apache.org/guides/mini/guide-java-target.html) · [Maven JAR Plugin — Manifest](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html) · [Maven Archiver — Classpath/Main-Class](https://maven.apache.org/shared/maven-archiver/examples/classpath.html).
