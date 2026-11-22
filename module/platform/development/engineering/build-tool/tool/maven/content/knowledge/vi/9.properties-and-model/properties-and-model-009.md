# Maven Properties và Model: Tránh tham chiếu vòng và phụ thuộc vào thông tin riêng của máy

## 1. Mục tiêu: POM dùng chung, build có thể tái lập

Trong Maven, `pom.xml` mô tả **mô hình dự án** (Project Object Model — POM). Bạn có thể khai báo `<properties>` và dùng biểu thức dạng `${property.name}` để tránh lặp lại giá trị như phiên bản Java, tên resource hoặc thư mục output. Maven cũng có thể lấy giá trị từ project model (`${project.version}`), Java system properties (`${java.home}`), biến môi trường (`${env.NAME}`), settings và các tham số lệnh.

Tính tiện lợi này đi kèm hai rủi ro lớn:

1. **Tham chiếu vòng (circular reference):** A dùng B, B lại dùng A; hoặc một thuộc tính tự định nghĩa bằng chính giá trị của nó. Chuỗi nội suy không có điểm kết thúc rõ ràng, có thể gây lỗi xây dựng model, biểu thức không được giải quyết đúng hoặc kết quả phụ thuộc plugin/cách đánh giá.
2. **Phụ thuộc thông tin riêng của máy (machine-specific configuration):** POM chứa đường dẫn như `C:\Users\Alice\...`, thư mục `/Users/alice/...`, Java home của một người, user name, credential, địa chỉ server riêng hoặc file chỉ có trên laptop. Build chạy ở máy tác giả nhưng lỗi trên CI/máy đồng đội.

Mục tiêu không phải cấm mọi biến môi trường hay property động. Mục tiêu là **phân biệt cấu hình chung cần cố định trong dự án** với **đầu vào của môi trường cần khai báo, cấp phát và kiểm tra rõ ràng**, đồng thời làm cho **đồ thị phụ thuộc giữa các properties không có chu trình**.

Sau bài học, bạn sẽ biết cách nhận diện vòng tham chiếu, thiết kế property một chiều, tránh đường dẫn tuyệt đối, tách secrets ra khỏi POM, sử dụng profile có chủ đích và kiểm tra bằng `effective-pom`, `help:evaluate` và build sạch.

## 2. Những nguồn giá trị Maven có thể nội suy

Trong một POM, Maven hỗ trợ nhiều loại biểu thức. Các ví dụ này là biểu thức đặt trong **vị trí cho phép nội suy**, không phải lệnh thực thi độc lập.

| Nguồn | Biểu thức ví dụ | Ý nghĩa và lưu ý |
| --- | --- | --- |
| Custom property trong `<properties>` | `${maven.compiler.release}`, `${app.message}` | Giá trị dùng chung của dự án; có thể được khai báo tại parent, child hoặc profile |
| Trường của project model | `${project.groupId}`, `${project.version}`, `${project.build.directory}` | Tham chiếu những thành phần của POM hiệu lực |
| Thư mục dự án | `${project.basedir}` hoặc `${basedir}` | Gắn với vị trí POM của module, không cố định đường dẫn máy lập trình viên |
| Java system property | `${java.home}`, `${user.home}` | Do JVM và môi trường chạy Maven cung cấp; có thể khác nhau giữa máy |
| Biến môi trường | `${env.JAVA_HOME}`, `${env.BUILD_MODE}` | Do hệ điều hành/CI cung cấp; có thể không tồn tại |
| Thông tin từ settings | `${settings.offline}` | Phụ thuộc nội dung settings hiệu lực và ngữ cảnh nội suy |
| User properties qua CLI | `-Dapp.message=CI_OK` | Đầu vào tùy biến của một lần chạy Maven; không nên bí mật hóa trong CLI |

**Phân biệt POM model với giá trị trong chương trình Java:** Maven thường nội suy các expression ở **build time**. Còn một dòng `System.getenv("APP_MODE")` trong Java chạy **runtime**. Nếu bạn muốn ứng dụng nhận giá trị lúc chạy, cần chọn cách truyền/cung cấp config runtime thay vì nhúng nhầm môi trường build vào artifact.

### 2.1. Nội suy xảy ra sau inheritance, nhưng vẫn có giới hạn

POM con có thể kế thừa properties từ parent; sau inheritance, các biến được dùng trong model theo quy tắc Maven. Ví dụ parent khai báo `<java.release>17</java.release>`, child có thể dùng `${java.release}` trong plugin configuration hoặc khai báo lại property với giá trị khác. Khi property dùng ở nhiều cấp parent/child/profile, phải xem **effective POM** thay vì suy đoán bằng mắt.

Không phải mọi vị trí trong POM đều cho phép mọi loại biểu thức hay được đánh giá ở cùng thời điểm. Những trường định danh mô hình như tọa độ `groupId:artifactId:version` và điều kiện kích hoạt profile có ràng buộc riêng; đừng cố “lách” bằng cách dùng biến tự tham chiếu. Đặc biệt, không lấy giá trị `${project.version}` để tự định nghĩa chính `<version>` của project.

### 2.2. Đừng nhầm ký pháp với shell

Trong POM:

~~~xml
<properties>
    <app.message>Hello from POM</app.message>
</properties>
~~~

Ở nơi được Maven/plugin hỗ trợ nội suy, biểu thức tương ứng là `${app.message}`. Trong terminal, `-Dapp.message=CI_OK` là tham số của Maven, không phải biến môi trường mang tên `app.message`. Biến môi trường do shell đặt có thể được Maven đọc qua tiền tố `env.` khi tên tương ứng tồn tại.

Trên Windows, tên biến môi trường thường được Maven chuẩn hóa thành chữ hoa. Vì vậy nên dùng `${env.JAVA_HOME}`, `${env.BUILD_MODE}` thống nhất, không tùy tiện đổi hoa/thường.

## 3. Tham chiếu vòng là gì?

Có thể mô tả các property như **đồ thị có hướng**: mỗi property là một nút, mỗi lần một property tham chiếu property khác là một cạnh. Một tập property lành mạnh có các giá trị nguồn cụ thể và các cạnh đi **một chiều**, không tạo chu trình.

### 3.1. Vòng trực tiếp: A tham chiếu chính A

Đây là **phản ví dụ**; không thêm vào POM thực tế:

~~~xml
<properties>
    <output.dir>${output.dir}/generated</output.dir>
</properties>
~~~

Ý định có thể là “lấy đường dẫn cũ rồi thêm `/generated`”, nhưng ở đây chưa có giá trị nguồn cho `output.dir`: công thức định nghĩa dùng chính tên đang được định nghĩa.

Không nên kỳ vọng Maven tự hiểu đây là phép cập nhật giá trị như trong một ngôn ngữ lập trình mệnh lệnh. Tùy vị trí nội suy và phiên bản/plugin, kết quả có thể là vòng không giải quyết được, model không hợp lệ hoặc biểu thức còn nguyên; **không có một thông báo lỗi duy nhất bảo đảm xuất hiện cho mọi trường hợp**.

Cách sửa: dùng một biến nguồn **không phụ thuộc ngược** vào `output.dir`:

~~~xml
<properties>
    <output.dir>${project.build.directory}/generated</output.dir>
</properties>
~~~

`project.build.directory` mặc định là thư mục `target` của module và không bị định nghĩa lại từ `output.dir` trong cấu hình này. Nếu Maven chạy từ nơi checkout khác, đường dẫn vẫn dựa trên build directory của project.

### 3.2. Vòng gián tiếp: A → B → A

**Phản ví dụ**:

~~~xml
<properties>
    <shared.dir>${generated.dir}</shared.dir>
    <generated.dir>${shared.dir}</generated.dir>
</properties>
~~~

`shared.dir` và `generated.dir` không có giá trị cuối cùng độc lập. Thêm property thứ ba cũng không giải quyết nếu sau cùng nó lại trỏ về property đầu.

**Bản sửa có hướng phụ thuộc rõ ràng:**

~~~xml
<properties>
    <workspace.dir>${project.build.directory}</workspace.dir>
    <generated.dir>${workspace.dir}/generated-sources</generated.dir>
    <shared.dir>${generated.dir}/shared</shared.dir>
</properties>
~~~

Chuỗi phụ thuộc là `project.build.directory → workspace.dir → generated.dir → shared.dir`. Không có cạnh quay trở lại nút cũ. Tuy nhiên **không kéo dài chuỗi alias khi không cần**: cấu hình ngắn hơn thường dễ kiểm tra hơn, chẳng hạn chỉ dùng `generated.dir=${project.build.directory}/generated-sources`.

### 3.3. Vòng gián tiếp qua parent, child hoặc profile

Một vòng tham chiếu không nhất thiết nằm trong cùng một đoạn `<properties>`. Ví dụ:

**POM cha (fragment):**

~~~xml
<properties>
    <output.dir>${base.dir}/outputs</output.dir>
</properties>
~~~

**POM con (fragment):**

~~~xml
<properties>
    <base.dir>${output.dir}</base.dir>
</properties>
~~~

Sau khi Maven kết hợp cấu hình kế thừa, hai property phụ thuộc ngược vào nhau. Khi profile chủ động thay một trong hai property, đồ thị phụ thuộc cũng có thể thay đổi theo lần build.

Sửa bằng cách thống nhất một “nguồn sự thật”:

~~~xml
<properties>
    <base.dir>${project.build.directory}</base.dir>
    <output.dir>${base.dir}/outputs</output.dir>
</properties>
~~~

Nếu muốn cho child thay đổi vị trí gốc, tốt hơn là đưa ra một biến cấu hình **không tham chiếu tới biến kết quả**, ví dụ `<base.dir>target</base.dir>` (nếu dự án thực sự cần) và xây các đường dẫn một chiều từ đó.

### 3.4. Vòng thông qua trường project model

**Phản ví dụ** khác:

~~~xml
<build>
    <directory>${project.build.directory}/custom</directory>
</build>
~~~

Đoạn trên dùng chính giá trị `project.build.directory` để định nghĩa **trường `build.directory`** đang được giải quyết. Khác với **đọc** `${project.build.directory}` trong một tham số plugin, đây là **tự định nghĩa lại** chính field bằng nó. Không làm vậy.

Nếu chỉ cần đường dẫn riêng cho một plugin, giữ build directory mặc định và dùng:

~~~xml
<configuration>
    <outputDirectory>${project.build.directory}/custom</outputDirectory>
</configuration>
~~~

Đây là fragment plugin, **chỉ** có ý nghĩa khi `<configuration>` thuộc một goal/plugin có tham số `outputDirectory` hợp lệ. Nếu thực sự muốn đổi `build.directory` cho toàn dự án, dùng giá trị riêng không quay về `project.build.directory`, ví dụ `<directory>build-output</directory>` và cân nhắc ảnh hưởng đến plugins/IDE/CI.

### 3.5. Kỹ thuật tìm vòng trước khi chạy build

Khi gặp một chuỗi properties dài:

1. Liệt kê tên các property **được định nghĩa** (trong parent, child, profiles và plugin config).
2. Với mỗi property, ghi rõ những property/trường model khác mà giá trị của nó tham chiếu.
3. Bắt đầu ở property nghi vấn, đi theo cạnh tham chiếu; nếu gặp lại một nút đã qua, bạn đã tìm thấy **chu trình**.
4. Thay nút gốc bằng một **giá trị nền tảng**: literal version, `project.build.directory` không bị ghi đè, hoặc đầu vào bên ngoài có quy ước rõ ràng.
5. Chạy lại `mvn validate`, đánh giá property và so sánh effective POM.

Ví dụ sơ đồ:

~~~text
Không tốt:
  output.dir ───> generated.dir
      ^                 |
      |_________________|

Tốt:
  project.build.directory
            |
            v
       generated.dir
            |
            v
         output.dir
~~~

Phần mềm hay plugin có thể xử lý một số expression khác nhau, nên **chỉ nhìn build SUCCESS chưa đủ**: kiểm tra giá trị cuối cùng của đường dẫn/plugin ở output thật.

## 4. Phụ thuộc máy cá nhân: các anti-pattern cần tránh

Một POM được commit vào Git là hợp đồng build của cả nhóm, không phải bản sao cấu hình máy người viết. Các ví dụ dưới đây **không nên có trong POM dùng chung**:

~~~xml
<properties>
    <custom.jdk.path>C:\Users\Alice\jdk-17</custom.jdk.path>
    <vendor.jar.path>/Users/alice/Downloads/vendor.jar</vendor.jar.path>
    <release.out>/home/alice/Desktop/releases</release.out>
    <local.server>http://localhost:8080</local.server>
</properties>
~~~

Những giá trị này có thể tồn tại trên một laptop nhưng không đúng trên Linux CI, máy Windows khác hoặc macOS. Tên người dùng, ổ đĩa, cấu trúc thư mục, shell, proxy, locale và các tool được cài đặt khác nhau. Hardcode đường dẫn còn có thể làm lộ cấu trúc nội bộ máy trong artifact/log.

| Dấu hiệu | Hậu quả trên máy khác | Hướng thay thế |
| --- | --- | --- |
| `C:\Users\Alice\...`, `/Users/alice/...`, `/home/alice/...` | File/thư mục không tồn tại | Đường dẫn project-relative qua `project.basedir`/`project.build.directory` |
| `C:\Program Files\Java\...` cho compiler | Sai OS, máy dùng JDK vị trí khác | Dùng JDK trong CI, `maven.compiler.release`, Maven Toolchains khi cần |
| `<scope>system</scope>` + `<systemPath>...` | Dependency chỉ có trên máy người viết | Publish dependency vào repository quản lý được và khai báo bằng GAV |
| Ghi trực tiếp password/token vào `pom.xml` | Lộ thông tin nhạy cảm trong Git/artifact/log | Secrets của CI hoặc `settings.xml` được quản lý quyền |
| Dựa vào `env.HOME` để tìm source code | HOME khác nhau giữa OS/user | Cấu trúc mã nguồn trong repo, dùng đường dẫn module |
| Profile kích hoạt bằng file chỉ có trên laptop | CI dùng cấu hình build khác | `-Pprofile-id` rõ ràng hoặc quy tắc activation nhất quán |
| Dùng `SNAPSHOT`/version range thay đổi không kiểm soát | Build hôm nay khác build hôm sau | Cố định/kiểm soát dependency và plugin versions |
| Sinh file chứa username/absolute path/current time | Artifact khác nhau giữa máy/lần chạy | Tránh lộ dữ liệu môi trường, cấu hình output reproducible |

**Một điểm cần phân biệt:** dùng `${user.home}` hoặc `${env.JAVA_HOME}` **không tự động làm build portable**. Nó chỉ giấu đường dẫn máy trong một biến. Nếu một bước build *bắt buộc* có thư mục tại vị trí ấy, các máy khác vẫn phải đáp ứng cùng một hợp đồng môi trường hoặc có cấu hình thay thế được kiểm chứng.

## 5. Đường dẫn portable: lấy theo dự án, không theo máy

### 5.1. Các thuộc tính nên dùng

| Biểu thức | Vai trò | Khi thích hợp |
| --- | --- | --- |
| `${project.basedir}` | Thư mục gốc của module đang xét | File config thuộc repository/module |
| `${project.build.directory}` | Thư mục output của module, mặc định `target` | Mã sinh, report, output tạm |
| `${project.build.outputDirectory}` | Output class chính, mặc định `target/classes` | Plugin xử lý class |
| `${project.build.testOutputDirectory}` | Output class test, mặc định `target/test-classes` | Plugin xử lý test |
| `${project.version}` | Phiên bản project hiệu lực | Manifest metadata, resource filtering |
| `${project.build.sourceEncoding}` | Encoding nội dung khi plugin hỗ trợ | Giữ UTF-8 nhất quán |

Một đoạn **hợp lệ** bên trong POM:

~~~xml
<properties>
    <generated.sources.dir>${project.build.directory}/generated-sources/mytool</generated.sources.dir>
    <report.dir>${project.build.directory}/reports/mytool</report.dir>
</properties>
~~~

Nếu plugin của bạn có tham số output tương ứng, lấy đường dẫn từ những property trên. Khi checkout project vào thư mục khác, Maven vẫn tính đường dẫn dựa trên module.

### 5.2. Đường dẫn tương đối không có nghĩa mọi build giống byte-for-byte

Một build có thể chạy thành công trên cả Windows/Linux nhưng tạo artifact khác nhau do xuống dòng (CRLF/LF), timestamp, thứ tự file trong archive, encoding, JDK, plugin, locale hoặc biến môi trường. **Portable build** nghĩa là chạy được theo cùng một quy trình; **reproducible build** theo nghĩa chặt hơn là từ cùng input/môi trường được kiểm soát có thể tạo ra artifact giống nhau đến từng byte.

Đừng ghi **absolute path** vào metadata của JAR, file resource hay mã sinh trừ khi đó là đầu ra runtime được thiết kế rõ ràng. Các file dưới `target` thường **không commit** vào Git vì chúng tái tạo được từ input và cấu hình.

### 5.3. Vấn đề với system-scope dependency

**Anti-pattern**:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>vendor-lib</artifactId>
    <version>1.0</version>
    <scope>system</scope>
    <systemPath>C:\Users\Alice\libs\vendor-lib.jar</systemPath>
</dependency>
~~~

Điều này bỏ qua cơ chế dependency resolution thông thường và phụ thuộc file chỉ có trên máy. Nó còn khó quản lý dependency transitive. Hướng đúng là đưa thư viện hợp pháp vào repository có quản lý và dùng:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>vendor-lib</artifactId>
    <version>1.0</version>
</dependency>
~~~

Đây là **fragment minh họa dependency**: artifact `org.example:vendor-lib:1.0` phải thực sự có trong repository mà build được phép truy cập. Không tự giả định nó có sẵn ở Maven Central.

## 6. Ví dụ Java 17 hoàn chỉnh: property một chiều, build không phụ thuộc username

Ví dụ này chứng minh một cách dùng property thực tế: định nghĩa **giá trị mặc định trong POM**, **filter resource trong build** và **cho phép override có chủ đích** qua Maven CLI. Project không chứa đường dẫn tuyệt đối hoặc secrets. Mọi file đều có thể đưa vào Git; Maven sinh output dưới `target`.

### 6.1. Cấu trúc project

~~~text
portable-maven/
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

### 6.2. POM đầy đủ

Tạo `portable-maven/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>portable-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <app.message>Portable Maven build</app.message>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>app.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
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

**Vì sao POM này portable?**

- Version Java mục tiêu được khai báo ở một nơi qua `maven.compiler.release=17`; máy build phải có **JDK hỗ trợ release 17**, không cần hardcode vị trí JDK.
- File `src/main/resources/app.properties` được filter ở phase `process-resources`, trước `compile` và `package`. Không có absolute path; Maven dùng cấu trúc thư mục tiêu chuẩn.
- Các plugin chính có version rõ ràng, làm giảm khác biệt khi nâng cấp toolchain.
- JAR Plugin khai báo `Main-Class` để chạy `java -jar`; ví dụ không có thư viện runtime ngoài.
- `app.message` là giá trị config **một chiều** dùng để tạo resource, không tham chiếu ngược vào nội dung resource hay chính nó.

**Giới hạn của ví dụ:** Nó minh họa một project không có dependency ngoài và một resource text đơn giản. Nếu bạn có resources nhạy cảm với ký hiệu `${...}` của framework, cần giới hạn filtering đúng file và delimiter; không được bật filtering bừa bãi cho binary hoặc mọi file cấu hình.

### 6.3. Mã Java: src/main/java/org/example/App.java

~~~java
package org.example;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream stream =
                     App.class.getResourceAsStream("/app.properties")) {
            if (stream == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(stream);
        }

        System.out.println(properties.getProperty("app.message"));
    }
}
~~~

Java đọc resource qua **classpath**. Dù chương trình chạy bên ngoài thư mục project, file cấu hình đã được đóng gói trong JAR vẫn đọc được. `Properties.load(InputStream)` sử dụng quy ước của Java properties; giá trị minh họa chỉ dùng ký tự ASCII để kết quả chính xác trên các môi trường.

### 6.4. Resource: src/main/resources/app.properties

~~~properties
app.message=@app.message@
~~~

Maven Resources Plugin hỗ trợ placeholder `@app.message@` khi bật filtering; lúc build, giá trị `<app.message>Portable Maven build</app.message>` từ POM được chèn vào resource. Tệp sau khi filter tại `target/classes/app.properties` sẽ chứa:

~~~properties
app.message=Portable Maven build
~~~

Chọn delimiter `@...@` để dễ phân biệt với nhiều placeholder runtime của các framework, nhưng vẫn cần kiểm tra cấu hình delimiter của plugin khi dự án có plugin/filter tùy biến.

### 6.5. Build và chạy thực tế

Tại thư mục chứa `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn clean package
java -jar target/portable-maven-1.0.0.jar
~~~

**Stdout chính xác của lệnh `java -jar`:**

~~~text
Portable Maven build
~~~

Maven có thể tải plugin từ repository ở lần đầu. Log Maven khi build không phải stdout của chương trình.

Thử override một giá trị **không nhạy cảm** ngay trên dòng lệnh:

~~~bash
mvn clean package -Dapp.message=CI_OK
java -jar target/portable-maven-1.0.0.jar
~~~

Stdout bây giờ là:

~~~text
CI_OK
~~~

Đây là **đầu vào có chủ đích** cho build, không phải đường dẫn/credential bí mật. File `target/classes/app.properties` hoặc nội dung của JAR sẽ thay đổi vì property được **nội suy khi đóng gói**. Đừng gọi hai artifact này là byte-for-byte reproducible khi đầu vào CLI khác nhau; đó là hai cấu hình build khác nhau.

Có thể xem archive:

~~~bash
jar tf target/portable-maven-1.0.0.jar
~~~

Cần tìm `org/example/App.class`, `app.properties` và `META-INF/MANIFEST.MF`. Để thấy giá trị đã filter, mở `target/classes/app.properties` bằng text editor/terminal. Nếu JAR báo thiếu Main-Class, kiểm tra manifest và phần cấu hình Maven JAR Plugin.

## 7. Profile: tùy biến có kiểm soát, không để môi trường kích hoạt bất ngờ

Maven profiles phù hợp khi **cùng POM cần các cấu hình build có chủ đích** như kiểm thử tích hợp, môi trường phát hành hoặc cấu hình CI. Chúng không nên làm người đọc khó biết lúc nào project đang sử dụng cấu hình nào.

Ví dụ fragment thêm bên trong `<project>` của POM mẫu (không phải một POM hoàn chỉnh mới):

~~~xml
<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <app.message>Portable Maven CI build</app.message>
        </properties>
    </profile>
</profiles>
~~~

Chạy:

~~~bash
mvn clean package -Pci
java -jar target/portable-maven-1.0.0.jar
~~~

Stdout:

~~~text
Portable Maven CI build
~~~

Đây là một **profile được bật tường minh**, dễ tái hiện trên CI và máy khác. Trong dự án thật, nếu profile CI làm thay đổi **artifact ứng dụng** chứ không chỉ cách kiểm tra, cần thiết kế lại việc phân biệt build-time và runtime config.

**Hạn chế lạm dụng profile tự kích hoạt:**

- `activeByDefault` có thể bị mất hiệu lực khi profile khác trong cùng POM được kích hoạt; đừng dựa vào nó như một hằng số không bao giờ đổi.
- Activation theo JDK, OS, biến môi trường hoặc **sự tồn tại của file trên ổ đĩa** có thể chọn bộ cấu hình khác nhau giữa máy dev và CI.
- Trong `activation.file` của profile, các biểu thức project model/properties không dùng được như trong cấu hình plugin thông thường; tài liệu Maven chỉ rõ có giới hạn riêng. Đừng nghĩ `${project.build.directory}` sẽ luôn nội suy ở vị trí kích hoạt file.
- Profile trong `settings.xml` thuộc môi trường cá nhân; profile trong POM thuộc cấu hình project. Không giả định profile cùng ID nhưng định nghĩa khác nhau sẽ cho build như mong muốn.

Nếu bắt buộc dùng activation theo OS/JDK (ví dụ plugin native), hãy tài liệu hóa ma trận hỗ trợ và có build trên từng hệ điều hành. Đối với lựa chọn như `ci`, `integration-test`, thường ưu tiên tên profile và lệnh kích hoạt rõ ràng.

### 7.1. Kiểm tra profile nào đang bật

~~~bash
mvn help:active-profiles
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Các lệnh sử dụng Maven Help Plugin; máy chưa cache plugin có thể cần tải lần đầu. File `effective-pom.xml` cho phép so sánh giá trị `app.message` và cấu hình plugin sau khi profile được áp dụng. Muốn kiểm tra khi CI profile bật, thêm `-Pci` vào lệnh Maven tương ứng.

**Đừng kiểm tra profile bằng cách chỉ mở POM gốc:** một giá trị có thể đến từ parent, profile, CLI hoặc settings; phải xem cấu hình **đã có hiệu lực** trong phiên build thực tế.

## 8. Phân biệt cấu hình project với thông tin riêng của môi trường

Đặt đúng loại thông tin vào đúng nơi:

| Loại thông tin | Vị trí ưu tiên | Có nên commit? |
| --- | --- | --- |
| Project coordinates, Java release, plugin versions | `pom.xml` và parent POM dùng chung | Có |
| Resource/mã nguồn cần build | `src/main/...` dưới version control | Có |
| Tham số không bí mật có giá trị mặc định | `<properties>` hoặc file config mẫu | Có, nếu giá trị chung |
| Định danh profile, tên server/mirror (không chứa secret) | POM hoặc tài liệu phù hợp | Có, nếu không nhạy cảm |
| Proxy, local repository riêng, mirror/credential người dùng | `~/.m2/settings.xml` hoặc global settings | Thông thường không commit settings cá nhân |
| Token/password deploy, signing secrets | Secret store của CI hoặc settings được bảo vệ | Không commit giá trị |
| Thư mục cài JDK của từng máy | Toolchain/settings môi trường, `JAVA_HOME` | Không hardcode trong POM |
| File build, report, generated source | `target/` | Thông thường không commit |

### 8.1. settings.xml dùng làm gì?

Maven có user settings ở `~/.m2/settings.xml`; global settings nằm trong cài đặt Maven. File này có thể chứa **proxy**, **mirror**, **localRepository**, **servers**, và **profiles** thuộc môi trường. Những thứ đó thường không nên được nhân bản trực tiếp vào POM chung.

Ví dụ **settings.xml** ở mức tối thiểu cho một server deploy có ID khớp cấu hình phát hành:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Hai biến `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` là **tên biến môi trường minh họa**, không có giá trị bí mật trong tài liệu. Muốn thực sự deploy, project còn phải có cấu hình repository/distributionManagement và một server với ID phù hợp; example chỉ minh họa cách tách thông tin xác thực khỏi POM.

**Bảo mật:** Dùng secret store của CI và cơ chế cung cấp secrets an toàn, hạn chế quyền đọc settings. Mã hóa password kiểu Maven 3 chỉ giúp giảm lộ tình cờ, **không thay thế secret manager**. Không in effective settings, log debug hoặc lệnh chứa token lên nơi công khai; một số công cụ có thể che mật khẩu nhưng bạn không nên coi việc che là bảo đảm tuyệt đối.

### 8.2. Maven Toolchains khi cần lựa chọn JDK

Dùng `<maven.compiler.release>17</maven.compiler.release>` chỉ quy định **đích biên dịch**, không tự tải hay chọn bản JDK trên ổ đĩa. Khi nhiều module cần JDK khác nhau hoặc Maven chạy bằng JDK riêng, **Maven Toolchains** có thể giúp plugin được hỗ trợ dùng JDK đáp ứng yêu cầu mà không hardcode `C:\...\jdk` trong POM.

Toolchain request thuộc project; đường dẫn JDK thực tế có thể đến từ toolchain setup trên máy/CI. Không phải plugin nào cũng hỗ trợ toolchain như nhau; cần xem tài liệu của plugin. Nếu không cần sự phức tạp này, chạy Maven bằng JDK hỗ trợ `release` mục tiêu thường đã đủ.

## 9. Phân tích một số vòng tham chiếu và sửa có chủ đích

### 9.1. Bản cấu hình sai do copy/paste

**Không dùng:**

~~~xml
<properties>
    <cache.dir>${work.dir}/cache</cache.dir>
    <work.dir>${cache.dir}/work</work.dir>
</properties>
~~~

Cấu trúc lặp: `cache.dir → work.dir → cache.dir`. Nói “nhưng tôi có khai báo cả hai rồi” không giải quyết được vì chúng **không có giá trị nguồn cuối**.

**Dùng:**

~~~xml
<properties>
    <work.dir>${project.build.directory}/work</work.dir>
    <cache.dir>${work.dir}/cache</cache.dir>
</properties>
~~~

Hai property bây giờ có thể được tính từ build directory và không tham chiếu ngược.

### 9.2. Cấu hình phụ thuộc chính username người build

**Không dùng:**

~~~xml
<properties>
    <generator.input>/home/developer/schema/api.yaml</generator.input>
</properties>
~~~

**Nên dùng nếu schema nằm trong repository:**

~~~xml
<properties>
    <generator.input>${project.basedir}/src/main/schema/api.yaml</generator.input>
</properties>
~~~

Đừng chỉ thay bằng `${user.home}/schema/api.yaml` rồi cho rằng build đã tái lập: schema đó vẫn có thể không tồn tại trong CI. Nếu input thực sự đến từ một hệ thống ngoài, cần có bước tải/đồng bộ rõ ràng, version/checksum và quyền truy cập phù hợp.

### 9.3. Cấu hình nhầm biến môi trường trong POM

**Rủi ro:**

~~~xml
<properties>
    <api.endpoint>${env.API_ENDPOINT}</api.endpoint>
</properties>
~~~

Nếu `API_ENDPOINT` không được đặt trên một máy, plugin có thể nhận chuỗi chưa được thay, giá trị rỗng hoặc lỗi ở bước sử dụng. Điều này phụ thuộc chỗ nội suy và plugin, nên **không dựa vào một thông báo Maven chung**.

**Lựa chọn có kiểm soát:**

- Với cấu hình **runtime**, để ứng dụng đọc env/config runtime thay vì bake endpoint production vào JAR ở build time.
- Với **build-time input bắt buộc**, đặt rõ hợp đồng CI cần cấp `API_ENDPOINT` và kiểm tra sự hiện diện/định dạng ngay ở bước build thích hợp.
- Với giá trị **không bí mật** có thể dùng mặc định chung, đặt default trong `<properties>` và cho phép thay thế chủ động qua profile hoặc `-D`, ghi rõ kết quả trên artifact.
- Với credentials, không đặt trực tiếp giá trị trong POM; dùng cơ chế secrets/settings.

Tránh tạo vòng như `<api.endpoint>${api.endpoint}</api.endpoint>` chỉ để “trông chờ biến ngoài override”. Một bản build không có override phải có trạng thái rõ: hoặc dùng default thực, hoặc dừng sớm với lỗi có ý nghĩa.

### 9.4. Khi parent, child và CLI cùng định nghĩa một property

Xem ví dụ ngữ cảnh:

- Parent định nghĩa `<app.message>Base</app.message>`.
- Child định nghĩa `<app.message>Child</app.message>`.
- Profile `ci` định nghĩa `<app.message>CI</app.message>`.
- Lệnh Maven có thể truyền `-Dapp.message=CLI_OK`.

Không nên suy đoán giá trị cuối cùng chỉ từ fragment POM đầu tiên bạn thấy. Hãy chạy **chính lệnh dự kiến** rồi dùng Maven Help Plugin và kiểm tra file đã filter. Đặc biệt, tránh chia nhỏ định nghĩa property vòng qua các cấp POM/profile; sự kết hợp sau inheritance có thể tạo chu trình mà từng file riêng lẻ không bộc lộ.

## 10. Cách kiểm tra giá trị đã nội suy và build thực tế

Trong thư mục có `pom.xml`, các lệnh chẩn đoán hữu ích:

~~~bash
mvn -version
mvn validate
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
mvn help:evaluate -Dexpression=app.message -q -DforceStdout
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
mvn clean verify
~~~

**Ý nghĩa:**

1. `mvn -version` xác nhận Maven, Java và Java home của process đang chạy; nếu build lỗi do JDK, kiểm tra đây trước.
2. `mvn validate` xem Maven có dựng được mô hình và thực hiện validate phase hay không. Nó không tự kiểm tra mọi property chỉ được dùng ở goal sau.
3. `help:evaluate` đánh giá **một expression** có ích để phát hiện giá trị còn placeholder `${...}` hoặc giá trị trỏ nhầm đường dẫn.
4. `help:effective-pom` xuất mô hình đã tính sau inheritance và profile. File output là **kết quả để điều tra**, không phải tự động đúng với mọi lần build nếu flags/profile khác.
5. `help:active-profiles` chỉ rõ profile đang có hiệu lực.
6. `mvn clean verify` kiểm chứng project từ output sạch, gồm compile/test/package và các goal đã được gắn đến verify.

Với project mẫu của phần 6, sau `mvn clean package` hãy kiểm tra:

~~~text
target/classes/app.properties
target/portable-maven-1.0.0.jar
~~~

File `app.properties` trong `target/classes` phải chứa đúng giá trị đã filter; nếu vẫn là `@app.message@`, kiểm tra resource filtering và phạm vi includes. Nếu giá trị chứa username/đường dẫn bất ngờ, truy ngược property và nguồn override.

### 10.1. Tìm source của property, không chỉ giá trị

`help:evaluate` trả giá trị cuối; nó không nhất thiết cho biết **ai đã đặt giá trị đó**. Khi nghi có override:

- Xem `pom.xml` hiện tại, các parent POM, profile đang active, và user properties `-D` của chính lệnh build.
- Xem `settings.xml` **của đúng user/CI process** khi thông tin được cấp từ settings.
- Xem env vars và JDK của process thực tế. Shell tích hợp của IDE, terminal bình thường và runner CI có thể nhận env khác nhau.
- Kiểm tra plugin goal dùng property, vì plugin có thể có default hoặc expression riêng.
- So sánh effective POM và artifact/output được tạo từ **cùng flags**; không dùng effective POM chạy với `-Pdev` để giải thích artifact build bằng `-Pci`.

Nếu model chưa dựng được do vòng tham chiếu, đôi khi `help:evaluate` cũng không chạy được. Khi đó đọc lỗi từ `mvn validate -e`, kiểm tra trực tiếp khai báo và vẽ đồ thị property trước; không cần nỗ lực chạy plugin giúp xem POM khi model vẫn bất hợp lệ.

### 10.2. Kiểm tra portablity trên môi trường sạch

Một cách làm thực tế: sau khi build tại máy phát triển, chạy lại trong **checkout sạch** hoặc môi trường CI/container với JDK/Maven đã xác định, local repository khác/ít cache và không có các file phụ ngoài Git. Nếu build chỉ thành công khi thư mục `/home/developer` tồn tại, đó là dấu hiệu rò rỉ phụ thuộc máy.

Lưu ý môi trường mới có thể cần Internet để tải dependencies/plugins và có cấu hình mirror/settings riêng. Điều đó **không tự động là bug của POM**; hãy phân biệt đầu vào mạng có quy trình (repository) với phụ thuộc vào file tình cờ trong home directory.

## 11. Checklist để tiến gần reproducible build

Một dự án Maven đáng tin nên có:

1. **Properties không có chu trình.** Mỗi chuỗi nội suy kết thúc ở literal hoặc giá trị model/đầu vào đã xác định; không dùng chính field để định nghĩa lại field đó.
2. **Nguồn dự án có thể version-control.** Schema, template, source và resource cần thiết nằm trong repo hoặc có cơ chế tải versioned rõ ràng.
3. **Đường dẫn gắn với project/module.** Ưu tiên `project.basedir`, `project.build.directory` và chuẩn directory layout thay vì home/Downloads/Desktop.
4. **Phiên bản có kiểm soát.** Ghim plugin/dependency versions phù hợp, hạn chế SNAPSHOT/version ranges không chủ đích.
5. **JDK và Maven được xác định.** Ghi rõ Java target, dùng Wrapper/CI toolchain khi phù hợp; tránh ngầm dựa vào JDK cài trên máy tác giả.
6. **Profile kích hoạt minh bạch.** Dùng `-Pci`, `-Pintegration-test` khi thực sự cần; tránh profile chỉ bật vì file/OS tình cờ.
7. **Secrets không nằm trong POM/Git.** Đưa credentials vào CI secret store hoặc settings được bảo vệ; tránh echo/log token.
8. **Build từ trạng thái sạch.** CI chạy `mvn clean verify`/bộ kiểm tra phù hợp trên checkout mới, không dựa vào generated files bỏ sót.
9. **Nguồn tạo artifact ổn định.** Tránh nhúng username, đường dẫn tuyệt đối, thời gian hiện tại hoặc danh sách file không có thứ tự xác định vào artifact.
10. **Reproducible artifacts khi cần byte-for-byte.** Dùng plugin hỗ trợ reproducible output, cấu hình `project.build.outputTimestamp` nếu cần/được hỗ trợ, và thực sự so sánh artifact ở hai môi trường khác nhau.

**Về outputTimestamp:** Tài liệu Maven hỗ trợ property `project.build.outputTimestamp` để điều khiển timestamp khi plugin đóng gói có hỗ trợ, ví dụ:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Đây là fragment minh họa bổ sung trong POM; chọn timestamp ổn định theo quy trình release thay vì tự gán `now()` mỗi lần chạy. Reproducible output **không chỉ là timestamp**: phụ thuộc version JDK, plugin, line endings, encoding và dữ liệu môi trường mà build đưa vào artifact. Trong các bản Maven mới, một số chế độ reproducible đã được bật mặc định; vẫn cần kiểm chứng artifact thực tế và không suy đoán behavior của mọi plugin.

## 12. Bảng lỗi và cách khắc phục

| Biểu hiện | Nguyên nhân có thể | Cách xử lý ưu tiên |
| --- | --- | --- |
| Build lỗi khi nội suy properties | Có property tự tham chiếu hoặc vòng qua nhiều property | Vẽ đồ thị phụ thuộc; đặt giá trị gốc độc lập; không tự định nghĩa field bằng chính field |
| Placeholder `${...}` còn trong effective output | Giá trị chưa được định nghĩa ở context đó hoặc vòng/không hỗ trợ interpolation | Kiểm tra tên property, POM/profile/CLI và chỗ dùng |
| `mvn validate` PASS nhưng plugin phase sau FAIL | Property chỉ được plugin đọc ở phase sau | Chạy phase thật, xem goal và cấu hình plugin |
| Build được trên laptop, CI báo file không tồn tại | Absolute path hoặc nguồn file nằm ngoài repo | Dùng project-relative path hoặc bước tạo/tải input có kiểm soát |
| Windows chạy được, Linux lỗi đường dẫn | Phụ thuộc drive letter/backslash, OS profile, shell tool hoặc tên file case-sensitive | Dùng plugin/cấu trúc Maven portable; kiểm thử trên các OS được hỗ trợ |
| `systemPath` trỏ tới thư viện trong Downloads | Dependency ngoài repository và ràng buộc máy | Publish library vào repo và dùng dependency GAV |
| Property `env.*` lúc có lúc không | Env khác giữa shell, IDE hoặc CI runner | Định nghĩa contract cho env, xác nhận biến trước build; tránh baking runtime secrets |
| Profile ngầm bật trên một số máy | `activeByDefault`, OS, JDK, property hoặc file activation | Dùng `help:active-profiles`; bật bằng `-P` rõ ràng |
| POM dùng credential plaintext | Cấu hình bí mật lẫn trong source control | Xóa khỏi POM, chuyển sang secret manager/settings; luân chuyển token đã lộ |
| Build dùng JDK khác dự kiến | `JAVA_HOME`/PATH/IDE Maven runner khác nhau | Xem `mvn -version`; dùng toolchain/CI setup nhất quán |
| Project đang ghi file vào `/Users/...` | Plugin `outputDirectory` hardcode | Dùng `project.build.directory` và kiểm tra quyền thư mục |
| Output JAR khác byte giữa hai máy | Timestamp, file ordering, JDK, plugin hoặc environment leak | Cấu hình reproducible output và dùng công cụ so sánh artifact |
| POM con thay property rồi parent/plugin chạy khác | Override sau inheritance/profile/CLI đổi kết quả nội suy | So sánh effective POM của chính lần build; thiết kế property ngắn, một chiều |
| `@app.message@` không được thay trong resource | Filtering chưa bật hoặc sai delimiter/resource path | Kiểm tra `<resources>`, plugin và file `target/classes/app.properties` |
| `java -jar` báo không có Main-Class | JAR Plugin chưa đặt entry point trong manifest | Kiểm tra `META-INF/MANIFEST.MF`, cấu hình plugin và build lại |

## 13. Bài tự kiểm tra

**Câu 1.** Trong `<properties>` có `<a>${b}</a>` và `<b>${a}</b>`. Điểm sai cốt lõi?  
**Đáp án:** Đồ thị property có vòng `a → b → a`, không có giá trị gốc; cần đặt một giá trị độc lập rồi dẫn xuất các property còn lại.

**Câu 2.** Dùng `${user.home}/lib/client.jar` thay cho `/Users/alice/lib/client.jar` đã portable chưa?  
**Đáp án:** Chưa chắc. Đường dẫn tuy đổi theo user nhưng file `client.jar` vẫn cần có ở mỗi máy. Cách bền vững hơn là đưa dependency vào repository và khai báo GAV.

**Câu 3.** `${project.build.directory}/generated` và `<build><directory>${project.build.directory}/generated</directory></build>` có giống nhau về ý nghĩa?  
**Đáp án:** Không. Cái đầu là *đọc* build directory để cấu hình output cho một mục khác. Cái sau là **định nghĩa lại chính build.directory bằng nó**, tạo nguy cơ tự tham chiếu.

**Câu 4.** App cần endpoint production lúc runtime. Có nên dùng Maven để filter `${env.PROD_URL}` vào JAR ở build time không?  
**Đáp án:** Thường không nên nếu cùng artifact sẽ được deploy qua nhiều môi trường. Nên phân tách runtime configuration khỏi build và cung cấp endpoint ở lúc chạy/deploy.

**Câu 5.** Build trên máy cá nhân OK nhưng CI lỗi `Could not find artifact` của một JAR `systemPath`. Xử lý?  
**Đáp án:** Tránh system-scoped file cá nhân, publish dependency vào repo Maven có quản lý, khai báo dependency theo GAV và cấu hình quyền truy cập cho CI.

**Câu 6.** Vì sao chỉ đọc file `pom.xml` chưa đủ để xác định `app.message` thực tế?  
**Đáp án:** Giá trị có thể bị thay bởi parent/child, profile hoặc `-D`; cần xem effective POM, tham số lệnh và file output sau filtering.

**Câu 7.** Một build chạy được trên Windows và Linux có chắc tạo cùng hash JAR?  
**Đáp án:** Không. Hash còn chịu ảnh hưởng timestamp, encoding/line endings, JDK, plugin và nội dung được nhúng vào artifact. Phải thiết kế và kiểm chứng reproducible build riêng.

**Câu 8.** Tại sao `<maven.compiler.release>17</maven.compiler.release>` không tự giải quyết chuyện cài JDK trên CI?  
**Đáp án:** Nó quy định target biên dịch, không tự cài JDK. CI cần JDK phù hợp, hoặc toolchain/plugin setup được quản lý.

## 14. Kết luận

Hai thói quen giúp các project Maven dễ bảo trì là **properties có hướng một chiều** và **POM không ràng buộc tình cờ vào máy tác giả**. Khi tham chiếu thuộc tính, hãy kiểm tra giá trị gốc và tránh chu trình dù nó nằm giữa nhiều POM/profile. Khi cấu hình đường dẫn, dùng thư mục dự án/build; khi cần biến môi trường, profile hay settings, phải phân biệt cái gì là cấu hình build chung, cái gì là đầu vào riêng của môi trường và cái gì là secret.

Bước kiểm chứng cuối cùng không chỉ là `mvn package` ở một laptop, mà còn là **đọc effective POM**, kiểm tra active profiles, build từ trạng thái sạch trên môi trường khác, và xác nhận output/đường dẫn/phiên bản thực tế.

## Tài liệu tham khảo chính thức

- [Apache Maven — POM Reference, Properties](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the POM, Interpolation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Apache Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — Password Encryption / Security Notes](https://maven.apache.org/guides/mini/guide-encryption.html)
