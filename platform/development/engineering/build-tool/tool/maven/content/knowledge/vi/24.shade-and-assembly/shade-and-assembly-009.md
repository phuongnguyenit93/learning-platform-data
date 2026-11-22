# Phân biệt artifact chính với artifact đính kèm có classifier trong Maven Shade và Assembly

## 1. Mục tiêu và câu hỏi quan trọng

Một Maven project có thể tạo nhiều file JAR ở cùng phiên bản:

~~~text
target/artifact-classifier-demo-1.0-SNAPSHOT.jar
target/artifact-classifier-demo-1.0-SNAPSHOT-all.jar
target/artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Nhưng khi project khác thêm dependency `com.example:artifact-classifier-demo:1.0-SNAPSHOT`, Maven sẽ chọn file nào? Khi chạy `mvn install`, file nào được cài dưới tọa độ **không classifier**, file nào chỉ được **đính kèm**? Một file nằm trong `target` có tự trở thành artifact trong repository không?

Đây là trọng tâm bài Knowledge thuộc nhóm **Shade và Assembly**: **main artifact** và **attached artifact with classifier** biểu diễn những biến thể khác nhau của cùng một Maven project, và việc phân biệt chúng ảnh hưởng trực tiếp đến repository, dependency resolution và runtime deployment.

Sau bài này, bạn sẽ:

1. Hiểu Maven coordinates `groupId`, `artifactId`, `version`, `type/extension` và `classifier`.
2. Phân biệt main artifact, attached artifact và file output không được attach.
3. Giải thích `shadedArtifactAttached`, `shadedClassifierName` và `createDependencyReducedPom` trong Shade Plugin.
4. Giải thích `appendAssemblyId` và assembly descriptor ID trong Assembly Plugin.
5. Build bằng Java 17 một project tạo đồng thời thin JAR, attached shaded JAR và attached assembly JAR.
6. Kiểm tra nội dung từng JAR, chạy hai executable variants và xác minh files được cài trong local Maven repository.
7. Viết dependency POM chọn đúng main hoặc classifier variant.
8. Nhận diện rủi ro về POM metadata, transitive dependencies, outputFile, finalName, duplicate classes và lifecycle execution.
9. Chọn chiến lược phát hành phù hợp cho thư viện, ứng dụng tự chạy hoặc gói phân phối.

Ví dụ dùng Maven 3.x, JDK 17, Maven Shade Plugin 3.6.2 và Maven Assembly Plugin 3.8.0. Đây là những phiên bản được ghi tường minh nhằm tái hiện bài học, không phải tuyên bố phiên bản mới nhất.

## 2. Artifact chính (main artifact) là gì?

Một project có POM:

~~~xml
<groupId>com.example</groupId>
<artifactId>artifact-classifier-demo</artifactId>
<version>1.0-SNAPSHOT</version>
<packaging>jar</packaging>
~~~

Với `packaging=jar`, lifecycle mặc định tạo JAR chính, thường là:

~~~text
target/artifact-classifier-demo-1.0-SNAPSHOT.jar
~~~

Main artifact biểu diễn artifact mặc định cho project, không cần classifier. Khi Maven install/deploy thành công, JAR chính được công bố dưới các coordinates của project.

Một consumer dùng:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-classifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
</dependency>
~~~

sẽ chọn **main JAR không có classifier** (với type mặc định `jar`). Maven **không tự động chọn JAR lớn nhất**, JAR có chữ `all`, hay JAR có hậu tố `jar-with-dependencies`.

### Main artifact không đồng nghĩa thin JAR

Trong một library project, main JAR thường là **thin JAR**: chứa classes/resources của chính project, còn external dependencies được Maven quản lý qua POM.

Nhưng với một project application, Shade Plugin có thể được cấu hình để **thay** main artifact bằng một uber-JAR chứa dependencies. Vì vậy “main” là vai trò trong project/repository, không phải mô tả kích thước hoặc thành phần file.

## 3. Artifact đính kèm và classifier

Một Maven project có thể có **một main artifact** và thêm những **attached artifacts**, ví dụ shaded JAR, assembly archive, sources JAR, Javadoc JAR hoặc tests JAR.

~~~text
com.example : artifact-classifier-demo : 1.0-SNAPSHOT
                  │
                  ├── Main:
                  │     classifier rỗng, extension jar
                  │     artifact-classifier-demo-1.0-SNAPSHOT.jar
                  │
                  ├── Attached Shade:
                  │     classifier all, extension jar
                  │     artifact-classifier-demo-1.0-SNAPSHOT-all.jar
                  │
                  └── Attached Assembly:
                        classifier jar-with-dependencies, extension jar
                        artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Classifier phân biệt những **biến thể của cùng groupId, artifactId và version**. Nó không tạo project mới hoặc tăng version. Tên file thường theo mẫu:

~~~text
artifactId-version[-classifier].extension
~~~

Dấu `[-classifier]` ở đây chỉ phần tùy chọn, không phải chuỗi cần ghi nguyên.

### Type, extension và classifier khác nhau

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `groupId` | `com.example` | Namespace của artifact. |
| `artifactId` | `artifact-classifier-demo` | Tên artifact/project. |
| `version` | `1.0-SNAPSHOT` | Phiên bản. |
| `type` | `jar` | Loại dependency, thường ánh xạ sang extension/artifact handler. |
| `extension` | `jar`, `zip` | Phần mở rộng của file repository. |
| `classifier` | `all`, `tests`, `sources` | Tên phân biệt biến thể. |

Ví dụ:

~~~text
app-2.0.jar               # main JAR
app-2.0-all.jar           # classifier=all, extension=jar
app-2.0-sources.jar       # classifier=sources, extension=jar
app-2.0-bin.zip           # classifier=bin, extension=zip
~~~

Không nên hiểu “classifier=all” nghĩa là một Maven scope. Scope như `compile`, `runtime` hay `test` điều khiển dependency classpath; classifier chọn **file cụ thể**.

Một type có thể có classifier ngầm định: `test-jar` thường ánh xạ sang JAR classifier `tests`. Tuy nhiên muốn bản `-all.jar` phải chọn classifier `all`, **không đổi type thành `test-jar`**.

### Tên file chưa đủ chứng minh attachment

Ba trường hợp:

| Vai trò | Có thể có file trong `target`? | `mvn install` tự cài? |
| --- | --- | --- |
| Main artifact | Có | Có, nếu lifecycle/install thành công. |
| Attached artifact | Có | Có, nếu plugin đã attach vào Maven project và install thành công. |
| File xuất ra tùy ý chưa attach | Có | **Không tự cài chỉ vì file tồn tại**. |

Do đó thấy `target/manual-fat.jar` không đủ chứng minh Maven đã công bố nó dưới classifier `fat`. Phải kiểm tra cơ chế attach và repository sau khi install.

## 4. Shade Plugin: thay main hoặc attach shaded JAR

Maven Shade Plugin tạo uber-JAR bằng việc gộp project và dependencies, có khả năng package relocation, resource transformers và lọc nội dung.

### 4.1. Shade thay artifact chính

Theo cấu hình thông thường, `shadedArtifactAttached=false` nghĩa là shaded JAR **thay main artifact**:

~~~xml
<shadedArtifactAttached>false</shadedArtifactAttached>
~~~

Sơ đồ:

~~~text
maven-jar-plugin tạo thin JAR
          │
          ▼
maven-shade-plugin:shade tạo uber-JAR
          │
          ▼
Main artifact của project được gán sang shaded JAR
          │
          ▼
mvn install/deploy công bố shaded JAR dưới tọa độ KHÔNG classifier
~~~

Trong `target` đôi khi còn file thin gốc được đổi tên `original-...jar`. File còn nằm trên đĩa **không có nghĩa đã được attach**.

### 4.2. Shade đính kèm một bản riêng

Khi muốn giữ thin main và thêm bản fat:

~~~xml
<shadedArtifactAttached>true</shadedArtifactAttached>
<shadedClassifierName>all</shadedClassifierName>
~~~

Khi đó Maven giữ:

~~~text
main     → artifact-classifier-demo-1.0-SNAPSHOT.jar
attached → artifact-classifier-demo-1.0-SNAPSHOT-all.jar
~~~

`all` là classifier do nhóm chọn, không phải bắt buộc. Giá trị mặc định của `shadedClassifierName` trong Shade thường là `shaded`. Tùy chọn `shadedClassifierName` chỉ quyết định tên classifier **khi attachment được bật**.

Nếu producer cần thư viện thin làm dependency mặc định và bản fat để chạy độc lập, **attach** thường là một lựa chọn rõ ràng.

### 4.3. `createDependencyReducedPom`: bẫy với main thin

Shade có thể tạo `dependency-reduced-pom.xml` và loại những dependencies đã gộp vào shaded JAR khỏi phần `<dependencies>` được công bố.

Trong mô hình **replace main**, reduced POM có thể phản ánh việc main artifact đã chứa dependency.

Trong mô hình **thin main + attached fat**, nếu POM metadata của main thin bị giảm dependencies, các consumer bình thường có thể không lấy được những thư viện thin JAR vẫn cần. Vì thế demo cấu hình:

~~~xml
<createDependencyReducedPom>false</createDependencyReducedPom>
~~~

Mục tiêu là **giữ dependency metadata phù hợp với main thin JAR**. Không có quy tắc mọi project luôn phải tắt reduced POM; quyết định cần dựa trên artifact nào là main và contract với consumer.

### 4.4. `outputFile` không phải attachment

Shade Plugin có tham số:

~~~xml
<outputFile>${project.build.directory}/manual-output.jar</outputFile>
~~~

Theo tài liệu `shade:shade`, nếu `outputFile` được chỉ định, archive được tạo **không thay main artifact và cũng không được attach**. Những tham số liên quan như `shadedArtifactAttached`, `shadedClassifierName` và reduced POM bị bỏ qua trong chế độ này.

Vì vậy nếu dùng `outputFile` rồi thấy JAR trong `target`, đừng mặc định `mvn install` sẽ cài file đó với classifier. Đây chỉ là **mảnh cấu hình thay thế**, không được chèn vào POM runnable nếu muốn có attached shaded JAR.

## 5. Assembly Plugin: assembly ID trở thành classifier

Maven Assembly Plugin tạo distribution hoặc archive từ một **assembly descriptor**. Ví dụ built-in descriptor:

~~~xml
<descriptorRefs>
    <descriptorRef>jar-with-dependencies</descriptorRef>
</descriptorRefs>
~~~

ID của assembly đó là `jar-with-dependencies`.

Khi:

~~~xml
<appendAssemblyId>true</appendAssemblyId>
~~~

Assembly Plugin gắn assembly ID vào filename và dùng nó làm **classifier cho attached artifact**. Với demo:

~~~text
artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Điểm mấu chốt:

- Project vẫn có `packaging=jar`.
- `jar-with-dependencies` là classifier của assembly output, không phải packaging mới.
- Main JAR không classifier vẫn tồn tại riêng.
- Nếu dùng một descriptor `bin` xuất ZIP, file thường có dạng `artifactId-version-bin.zip` khi được attach.

### Nếu đặt `appendAssemblyId=false`?

Khi:

~~~xml
<appendAssemblyId>false</appendAssemblyId>
~~~

Assembly Plugin bỏ assembly ID khỏi tên file và tạo artifact **không classifier** theo cơ chế này. Tài liệu plugin nêu rõ: nếu assembly output có **cùng format** với packaging hiện tại, nó có thể **thay file main artifact**.

Đó không chỉ là thay đổi tên file. Nếu cần đồng thời thin main và fat assembly JAR, hãy giữ `appendAssemblyId=true`. Đừng đặt hai plugin cùng cố gắng thay main artifact khi chưa thiết kế rõ thứ tự và publication contract.

### So sánh hai plugin

| | Shade Plugin | Assembly Plugin |
| --- | --- | --- |
| Goal | `shade:shade` | `assembly:single` |
| Công dụng điển hình | Uber-JAR, relocation, resource transformers. | JAR/ZIP/TAR distributions từ descriptor. |
| Attach classifier | `shadedArtifactAttached=true` và `shadedClassifierName`. | `appendAssemblyId=true`, classifier theo assembly ID. |
| Thay main | Thường khi `shadedArtifactAttached=false`. | Có thể khi `appendAssemblyId=false` và archive cùng format. |
| Gộp dependencies | Có, với xử lý shade/relocation. | Có, tùy descriptor như `jar-with-dependencies`. |
| Metadata khác biệt | Hỗ trợ `createDependencyReducedPom`. | Không tương đương Shade dependency reducer. |

Không coi `jar-with-dependencies` của Assembly là bản thay thế hoàn toàn cho Shade. Đặc biệt với `META-INF/services`, Spring resources, chữ ký JAR, relocation hoặc file trùng đường dẫn, cần test archive theo plugin thực tế.

## 6. Dự án Java 17 hoàn chỉnh tạo ba JAR

Ta xây project `artifact-classifier-demo` dùng thư viện ngoài `commons-lang3`. Khi build:

- Main JAR chứa mã project, **không đóng gói class của commons-lang3**.
- Attached Shade JAR classifier `all` gộp mã project và commons-lang3.
- Attached Assembly JAR classifier `jar-with-dependencies` cũng đóng gói dependencies theo assembly descriptor.

### 6.1. Cây thư mục

~~~text
artifact-classifier-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

Không cần Spring hay server. Bài dùng Maven 3.x và JDK 17, có thể tải plugins và commons-lang3 từ Maven repositories đã cấu hình.

### 6.2. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>artifact-classifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>demo.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>attach-shaded-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <shadedArtifactAttached>true</shadedArtifactAttached>
                            <shadedClassifierName>all</shadedClassifierName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>demo.Main</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-assembly-plugin</artifactId>
                <version>3.8.0</version>
                <configuration>
                    <descriptorRefs>
                        <descriptorRef>jar-with-dependencies</descriptorRef>
                    </descriptorRefs>
                    <appendAssemblyId>true</appendAssemblyId>
                    <archive>
                        <manifest>
                            <mainClass>demo.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
                <executions>
                    <execution>
                        <id>attach-assembly-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>single</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích cấu hình:**

- Compiler Plugin `3.13.0` và `maven.compiler.release=17` phục vụ Java 17.
- JAR Plugin `3.4.2` tạo thin main JAR, có manifest `Main-Class: demo.Main`.
- Shade Plugin `3.6.2` chạy ở phase `package`, có `shadedArtifactAttached=true` và classifier `all`.
- `createDependencyReducedPom=false` giữ POM metadata mô tả dependency `commons-lang3` cho thin main JAR.
- `ManifestResourceTransformer` thêm `Main-Class` vào shaded JAR.
- Assembly Plugin `3.8.0` dùng descriptor `jar-with-dependencies`, `appendAssemblyId=true` và manifest cho assembly JAR.
- Cả Shade và Assembly có `execution` bind vào `package` để tự chạy khi gọi Maven lifecycle, không đòi người học chạy goal riêng lẻ khi đầu vào chưa sẵn sàng.
- Mỗi plugin tạo biến thể tên khác nhau nên không cùng cố thay main artifact.

### 6.3. Java source runnable

Tạo `src/main/java/demo/Main.java`:

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = StringUtils.capitalize("maven");
        System.out.println("Hello " + name + " from commons-lang3");
    }
}
~~~

`StringUtils.capitalize("maven")` trả chuỗi `Maven`. Chương trình sử dụng class của dependency bên ngoài JDK; vì vậy thin JAR không có commons-lang3 ở runtime classpath sẽ không tự chạy thành công, còn hai fat JAR được chuẩn bị để có thể chạy độc lập.

**Stdout chính xác khi chạy thành công:**

~~~text
Hello Maven from commons-lang3
~~~

### 6.4. Build

Đứng trong thư mục chứa `pom.xml`:

~~~bash
mvn --version
java -version
mvn clean package
~~~

Nếu Maven/JDK và repository hoạt động, project tạo các file trọng tâm:

~~~text
target/
├── classes/
│   └── demo/Main.class
├── artifact-classifier-demo-1.0-SNAPSHOT.jar
├── artifact-classifier-demo-1.0-SNAPSHOT-all.jar
└── artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Đây là cây **rút gọn**, Maven có thể tạo thêm metadata, thư mục và file tạm.

## 7. Kiểm tra từng artifact bằng JDK

### 7.1. Main thin JAR

~~~bash
jar tf target/artifact-classifier-demo-1.0-SNAPSHOT.jar
~~~

Cần có:

~~~text
META-INF/MANIFEST.MF
demo/Main.class
~~~

Nhưng không nên có:

~~~text
org/apache/commons/lang3/StringUtils.class
~~~

vì JAR Plugin thông thường đóng gói output của project chứ không gộp toàn bộ dependency JAR.

Do POM có `Main-Class`, bạn có thể thử:

~~~bash
java -jar target/artifact-classifier-demo-1.0-SNAPSHOT.jar
~~~

và dự kiến **không chạy tới stdout thành công** vì chưa có `commons-lang3` trên runtime classpath. JVM thường báo `NoClassDefFoundError` liên quan `org/apache/commons/lang3/StringUtils`. Đây là phép thử minh họa; không cần cố tình gây lỗi khi triển khai thật.

### 7.2. Attached Shade JAR

~~~bash
jar tf target/artifact-classifier-demo-1.0-SNAPSHOT-all.jar
~~~

Cần thấy cả:

~~~text
demo/Main.class
org/apache/commons/lang3/StringUtils.class
~~~

Chạy:

~~~bash
java -jar target/artifact-classifier-demo-1.0-SNAPSHOT-all.jar
~~~

**Stdout chính xác:**

~~~text
Hello Maven from commons-lang3
~~~

### 7.3. Attached Assembly JAR

~~~bash
jar tf target/artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Cần thấy:

~~~text
demo/Main.class
org/apache/commons/lang3/StringUtils.class
~~~

Chạy:

~~~bash
java -jar target/artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

**Stdout chính xác:**

~~~text
Hello Maven from commons-lang3
~~~

Hai bản fat cho cùng kết quả trong ví dụ, nhưng không nhất thiết có binary bytes, manifest, resource merge behavior hay internal structure giống nhau. Shade và Assembly không thể được coi là các plugin hoàn toàn tương đương chỉ vì cả hai tạo uber-JAR.

### Bảng kiểm chứng nhanh

| File | Chứa `demo.Main` | Chứa `StringUtils.class` | Chạy `java -jar` độc lập | Vai trò |
| --- | :---: | :---: | :---: | --- |
| `...-1.0-SNAPSHOT.jar` | Có | Không | Không, thiếu external dependency | Main thin |
| `...-1.0-SNAPSHOT-all.jar` | Có | Có | Có | Attached Shade, classifier `all` |
| `...-1.0-SNAPSHOT-jar-with-dependencies.jar` | Có | Có | Có | Attached Assembly, classifier `jar-with-dependencies` |

Kết luận trong bảng dành cho **demo đã cấu hình manifests và dependency**. Với project khác, một fat JAR không có Main-Class sẽ không tự chạy bằng `java -jar` dù đã chứa tất cả classes.

## 8. `mvn package` khác `mvn install`

`mvn clean package` chỉ build artifacts trong `target`. Nó **không tự cài** artifacts vào local Maven repository.

Chạy:

~~~bash
mvn clean install
~~~

Maven hoàn thành lifecycle gồm `package` và `install`, cài main artifact, attached artifacts đã đăng ký và POM vào repository.

Với demo, local repository mặc định thường có dạng:

~~~text
~/.m2/repository/com/example/artifact-classifier-demo/1.0-SNAPSHOT/
├── artifact-classifier-demo-1.0-SNAPSHOT.pom
├── artifact-classifier-demo-1.0-SNAPSHOT.jar
├── artifact-classifier-demo-1.0-SNAPSHOT-all.jar
└── artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Có thể có thêm metadata và tracking files; ở Windows local repository thường nằm dưới thư mục người dùng `.m2\\repository`. Nếu cấu hình `settings.xml` hoặc `-Dmaven.repo.local` khác, kiểm tra đúng local repository thực tế.

**Vì sao cả ba JAR ở cùng directory?** Chúng chia sẻ:

~~~text
groupId   = com.example
artifactId= artifact-classifier-demo
version   = 1.0-SNAPSHOT
extension = jar
~~~

và phân biệt bằng classifier. Không có ba project hay ba POM độc lập.

### Remote repository và snapshots

`mvn deploy` có thể phát hành main và attached artifacts lên repository đã cấu hình khi có quyền và lifecycle thành công. Không cần thử deploy lên môi trường thật trong bài học.

Với SNAPSHOT remote repository, Maven có thể dùng timestamped filenames và metadata. Đừng đọc một tên snapshot timestamped rồi kết luận project đã thay `<version>1.0-SNAPSHOT</version>`. Phải phân biệt base version của POM với cách repository lưu từng snapshot build.

## 9. Consumer chọn JAR nào bằng `<dependency>`?

Giả sử producer đã được install hoặc deploy và consumer có quyền truy cập repository.

### 9.1. Không khai báo classifier: chọn main

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-classifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
</dependency>
~~~

Maven sẽ tìm JAR mặc định **không classifier**. Với POM demo, đó là thin JAR.

### 9.2. Chọn Shade attached variant

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-classifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <classifier>all</classifier>
    <type>jar</type>
</dependency>
~~~

Maven chọn:

~~~text
artifact-classifier-demo-1.0-SNAPSHOT-all.jar
~~~

`type=jar` là extension/type của artifact; `classifier=all` chỉ bản fat được attach.

### 9.3. Chọn Assembly attached variant

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-classifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <classifier>jar-with-dependencies</classifier>
    <type>jar</type>
</dependency>
~~~

Maven chọn:

~~~text
artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Ba snippet dependency trên là **ba lựa chọn thay thế**, không nên khai báo cả ba trong cùng một consumer để rồi kéo nhiều bản cùng classes vào classpath.

### Classifier không tạo POM dependency metadata riêng

Đây là bẫy quan trọng khi dùng shaded/assembly JAR như Maven dependency:

- Main thin JAR cần `commons-lang3` để hoạt động.
- POM producer khai báo dependency `commons-lang3` nhằm hỗ trợ consumer thin JAR.
- Shaded/assembly JAR có thể đã gộp `StringUtils.class` bên trong.
- Nhưng khi consumer chọn classifier `all`, Maven vẫn có thể đọc **cùng POM metadata của GAV** và kéo `commons-lang3` transitively.

Kết quả có thể có **duplicate classes**, trùng resources hoặc sự khác biệt classloader. Vì vậy fat JAR thường hợp lý cho **CLI/deployment distribution**, không phải dependency thư viện mặc định trong một ứng dụng khác.

Nếu muốn phân phối hai sản phẩm có dependency contract khác hẳn, cân nhắc tách Maven modules/artifactIds thay vì cố sử dụng cùng một POM với nhiều classifier.

## 10. `finalName` không phải classifier

Maven có:

~~~xml
<build>
    <finalName>demo-release</finalName>
</build>
~~~

Nó có thể đổi local build filename thành:

~~~text
target/demo-release.jar
~~~

Nhưng **không tạo classifier `release`** và không tự đổi GAV của project. Filename ở repository thường được đặt theo coordinates và extension, không phụ thuộc hoàn toàn vào tên file trong `target`.

Phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| `project.artifactId` | Tên artifact của Maven project. |
| `project.version` | Phiên bản. |
| `project.packaging` | Loại packaging/lifecycle, ví dụ JAR. |
| `build.finalName` | Tên file theo convention tại build directory. |
| `shadedClassifierName` | Classifier của Shade **khi** attached. |
| `appendAssemblyId` | Có đưa assembly ID thành classifier khi Assembly output được attach. |
| `outputFile` (Shade) | File output riêng; theo tài liệu không tự replace/attach. |

Nếu một script CI chỉ dựa vào tên `*-all.jar` mà không xác minh publication/attach, script có thể lấy đúng file vật lý nhưng vẫn không cho consumer Maven truy cập qua coordinates mong muốn.

## 11. Những cấu hình thay thế không được ghép bừa

### 11.1. Shade replace-main thay cho attach

Đây là **mảnh cấu hình thay thế** cho Shade Plugin trong project ứng dụng:

~~~xml
<configuration>
    <shadedArtifactAttached>false</shadedArtifactAttached>
    <transformers>
        <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
            <mainClass>demo.Main</mainClass>
        </transformer>
    </transformers>
</configuration>
~~~

Không chèn nó đồng thời vào execution đã bật `shadedArtifactAttached=true` ở POM runnable. Nếu build theo chiến lược replace-main, artifact không classifier được công bố là shaded JAR. Bản thin gốc có thể còn trên đĩa nhưng không tự thành attached artifact.

### 11.2. Assembly không classifier

~~~xml
<configuration>
    <descriptorRefs>
        <descriptorRef>jar-with-dependencies</descriptorRef>
    </descriptorRefs>
    <appendAssemblyId>false</appendAssemblyId>
</configuration>
~~~

Đây cũng chỉ là **mảnh thay thế**. Với assembly JAR có format trùng main JAR, việc tắt append có thể thay main. Nếu cùng lúc Shade cũng đang replace-main, kết quả dễ gây xung đột về artifact chính.

### 11.3. Shade `outputFile` không attach

~~~xml
<configuration>
    <outputFile>${project.build.directory}/private-copy.jar</outputFile>
</configuration>
~~~

Mảnh này tạo file vật lý mà không tự attach/thay main. Đừng kết hợp `outputFile` với mong đợi `shadedClassifierName` sẽ điều khiển file trong Maven repository.

### 11.4. Assembly không tự chạy nếu thiếu execution

Một mảnh execution:

~~~xml
<executions>
    <execution>
        <id>make-distribution</id>
        <phase>package</phase>
        <goals>
            <goal>single</goal>
        </goals>
    </execution>
</executions>
~~~

phải nằm trong đúng `maven-assembly-plugin`. Trong project Java JAR, `package` phù hợp vì classes và JAR đầu vào đã được tạo bởi các goals trước. Gọi trực tiếp `mvn assembly:single` trong project chưa build đúng input có thể gặp file thiếu hoặc archive thiếu classes.

## 12. Nên chọn main thin, main shaded hay attached JAR?

### Thư viện Java dùng bởi nhiều project Maven

Ưu tiên **main thin JAR** cùng POM dependency metadata chuẩn. Nếu thực sự cần shaded variant, **attach** với classifier, nhưng nói rõ nó chủ yếu phục vụ distribution hoặc một trường hợp classpath đặc biệt. Maven resolver và consumer nên tiếp tục quản lý dependencies khi dùng main.

### Ứng dụng CLI/service chỉ cần một executable

Có thể dùng Shade thay main để dependency không classifier chính là executable fat JAR, hoặc vẫn giữ thin main và phát hành executable attached `-all.jar`. Hãy chọn dựa vào cách deploy và liệu project còn có Maven consumers trực tiếp hay không.

### Gói phân phối ZIP/TAR có cấu trúc riêng

Assembly Plugin thích hợp để tạo archive chứa JAR, script, config, documentation và những file triển khai. Nếu ZIP có assembly ID `bin`, nó có thể được attach bằng classifier `bin`, extension `zip`. Khái niệm classifier vẫn tương tự dù output không phải JAR.

### Hai sản phẩm có release/dependency policies khác nhau

Nếu thin library và runnable server là hai sản phẩm riêng, hãy cân nhắc **hai Maven modules/artifactIds**. Classifier giúp có những biến thể của cùng một artifact, nhưng không thay thế thiết kế module khi dependency graphs và lifecycle khác hẳn nhau.

## 13. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `target` có `-all.jar` nhưng local repository không có. | Chưa chạy `install`, Shade dùng `outputFile` hoặc không attach. | Kiểm tra execution, `outputFile`, `shadedArtifactAttached` và install log. |
| Main JAR chứa dependencies ngoài dự tính. | Shade replace-main mặc định. | Bật attached mode nếu muốn thin main. |
| Không thấy `-all.jar` mà có `-shaded.jar`. | Dùng classifier mặc định thay vì `all`. | Cấu hình `shadedClassifierName>all` đúng trong Shade. |
| Assembly không tạo `-jar-with-dependencies.jar`. | Goal `single` chưa bind, chưa đến `package` hoặc thiếu descriptor. | Xem effective POM và lifecycle log. |
| Main JAR bị ghi đè bởi assembly. | `appendAssemblyId=false` với cùng archive format. | Giữ true khi muốn cả main và attached. |
| Consumer không lấy được classifier. | File chưa attach/deploy, typo classifier hoặc repo không đúng. | Kiểm tra local/remote repository, dependency POM. |
| Consumer lấy thin dù đã có shaded. | Consumer không khai báo classifier. | Thêm `<classifier>all</classifier>` đúng variant. |
| Consumer dùng fat vẫn kéo dependency gốc. | Các classifiers chia sẻ POM metadata. | Xem dependency graph; đừng mặc định fat JAR là library dependency sạch. |
| `java -jar` thin lỗi `NoClassDefFoundError`. | JAR không chứa runtime dependency. | Dùng classpath có dependency hoặc fat variant. |
| Fat JAR không có `Main-Class`. | Chưa cấu hình manifest transformer/archive. | Kiểm tra `META-INF/MANIFEST.MF` và plugin config. |
| Shaded JAR có ServiceLoader lỗi. | Resource/service descriptor trùng chưa được merge. | Dùng Shade transformers thích hợp, viết integration test. |
| `build.finalName` đổi nhưng tọa độ repository không đổi. | finalName không phải classifier/GAV. | Xác minh coordinates và file repository. |
| File `original-...jar` bị publish nhầm. | Script CI chọn file bằng wildcard rộng. | Chỉ định đúng artifact/classifier, kiểm tra install/deploy logs. |
| Hai plugin cùng cố thay main JAR. | Shade false và Assembly append false. | Chỉ một publisher chịu trách nhiệm main; attach các variant còn lại. |
| Thấy file cũ trong `target`. | Không chạy clean sau khi đổi configuration. | `mvn clean package`, xem timestamp/content. |
| Multi-module không thấy artifact. | Kiểm tra sai module hoặc plugin execution inherited khác. | Kiểm tra đúng POM/module, effective POM, output và install. |
| Artifact tồn tại nhưng thiếu class resource. | Shade filtering/minimization/relocation hoặc Assembly descriptor. | So `jar tf`, plugin logs và runtime tests. |

## 14. Kiểm tra trong CI và multi-module

Một reactor có thể gồm:

~~~text
parent/
├── pom.xml            # packaging=pom
├── core/pom.xml       # thin library
└── cli/pom.xml        # Shade/Assembly
~~~

Không phải module nào cũng có main JAR; parent packaging `pom` thường có POM artifact chính. Mỗi module có coordinates và build directory riêng, nên đừng kiểm tra mỗi `parent/target` rồi kết luận modules không tạo artifact.

Một số quy tắc CI:

1. Chốt module, version, mục đích: main library, attached `all` hay distribution archive.
2. Không dùng wildcard `target/*.jar` để lựa chọn production artifact nếu có nhiều variants.
3. Kiểm tra exact filename và file contents bằng `jar tf`.
4. Nếu cần Java executable, chạy `java -jar` trên đúng variant đã chọn.
5. Nếu publication qua Maven, chạy test `install` cục bộ hoặc deploy vào staging repository phù hợp rồi kiểm tra coordinates.
6. Đọc POM đã publish; một classifier không tự có POM dependency graph riêng.
7. Tránh đưa files nội bộ/secret hoặc dependencies có license không phù hợp vào shaded/assembly archive.
8. Ghi build ID, commit và checksum trong quy trình phát hành.
9. Không tái sử dụng release version cho nội dung artifact khác một cách tùy tiện.
10. Nếu snapshot repository dùng timestamp, phân biệt filename repository với base version trong POM.

### Lệnh kiểm chứng demo

~~~bash
mvn --batch-mode clean package
jar tf target/artifact-classifier-demo-1.0-SNAPSHOT.jar
jar tf target/artifact-classifier-demo-1.0-SNAPSHOT-all.jar
jar tf target/artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
java -jar target/artifact-classifier-demo-1.0-SNAPSHOT-all.jar
java -jar target/artifact-classifier-demo-1.0-SNAPSHOT-jar-with-dependencies.jar
~~~

Hai lệnh Java cuối **mỗi lệnh** phải in:

~~~text
Hello Maven from commons-lang3
~~~

Cả batch còn có Maven logs và listing `jar tf`, nên đoạn stdout trên chỉ là stdout của ứng dụng khi gọi `java -jar`, không phải toàn bộ stdout của batch.

## 15. Bài tập và đáp án

### Bài A — phân loại tọa độ

Cho các file được publish bởi project `org.example:demo-tool:2.1`:

~~~text
demo-tool-2.1.jar
demo-tool-2.1-all.jar
demo-tool-2.1-sources.jar
demo-tool-2.1-bin.zip
~~~

Hỏi:

1. JAR chính là file nào nếu packaging `jar` và các biến thể đã attach?
2. `all`, `sources` và `bin` là classifiers của các file nào?
3. `bin.zip` có extension gì?
4. Dependency không khai báo classifier sẽ lấy JAR nào?
5. File `-all.jar` tồn tại ở `target` nhưng chưa attach thì `mvn install` có tự cài không?

**Đáp án:** main là `demo-tool-2.1.jar`; ba variants có classifiers đúng theo hậu tố; ZIP có extension `zip`; dependency không classifier chọn main; file không attach không tự được cài chỉ vì có trong `target`.

### Bài B — thực hành Java 17

1. Tạo đầy đủ `pom.xml` và `Main.java` ở mục 6.
2. Chạy `mvn clean package`, xác nhận có ba JAR với tên đã dự đoán.
3. Dùng `jar tf`, kiểm tra main JAR không có `StringUtils.class`, hai fat JAR có.
4. Chạy hai fat JAR bằng `java -jar` và đối chiếu stdout.
5. Chạy `mvn clean install`, kiểm tra local Maven repository chứa main, `all`, `jar-with-dependencies` và POM.
6. Viết một dependency không classifier và một dependency classifier `all`.
7. Giải thích tại sao không nên dùng `type=test-jar` để chọn `-all.jar`.
8. Giải thích việc đặt `createDependencyReducedPom=false` khi giữ thin main.
9. Dự đoán điều gì xảy ra nếu đổi Shade thành `shadedArtifactAttached=false`.
10. Dự đoán điều gì xảy ra nếu đổi Assembly thành `appendAssemblyId=false`, cùng định dạng JAR.

### Bài C — tình huống phát hành

Một team phát hành `org.example:core-lib:1.0.0` là thin JAR. Sau khi thêm Shade, consumer bắt đầu bị thiếu dependency hoặc có duplicate classes. Hãy xác minh:

- Plugin có thay main hay attach bản shaded?
- Reduced POM có thay dependency metadata cần cho main?
- Consumer có khai báo đúng classifier không?
- Artifact ở repository dưới tọa độ không classifier có bytes của thin hay fat?
- CI có upload sai file `original-...jar` hoặc `outputFile` không attach không?
- Có cần tách module/artifactId cho application distribution thay vì classifier?

## 16. Checklist trước khi phát hành

- [ ] Biết groupId, artifactId, version, packaging và module đang build.
- [ ] Biết chính xác main artifact là thin hay fat sau mọi plugin executions.
- [ ] Ghi rõ classifier/type/extension của từng attached artifact.
- [ ] Shade: kiểm tra `shadedArtifactAttached`, `shadedClassifierName` và `outputFile`.
- [ ] Shade: quyết định `createDependencyReducedPom` theo main artifact contract.
- [ ] Assembly: kiểm tra descriptor ID và `appendAssemblyId`.
- [ ] Không có hai plugin cùng định thay main JAR cùng format.
- [ ] Các archive goals được bind vào lifecycle phase thích hợp.
- [ ] Đã kiểm tra từng JAR bằng `jar tf` và manifest `Main-Class`.
- [ ] Attached executable JAR đã được chạy thử bằng `java -jar`.
- [ ] Đã chạy `mvn install` và xác minh local repository có đúng variants.
- [ ] Consumer dependency chọn classifier tường minh khi cần.
- [ ] Đã cân nhắc duplicate classes/transitive dependencies khi tiêu thụ fat JAR.
- [ ] CI không dùng wildcard mơ hồ hoặc phát hành nhầm `original-` JAR.
- [ ] Đã kiểm tra security/licenses và nội dung bất ngờ trong shaded/assembly artifacts.

## 17. Kết luận

**Artifact chính** là file được Maven project công bố theo tọa độ mặc định **không classifier**. **Attached artifact** là một biến thể có classifier hoặc loại archive khác được plugin đăng ký để Maven có thể install/deploy cùng GAV.

Với Shade:

- `shadedArtifactAttached=false`: shaded JAR có thể **thay main artifact**.
- `shadedArtifactAttached=true`: shaded JAR **được attach**, classifier từ `shadedClassifierName`.
- `outputFile`: chỉ file output riêng; **không tự attach hoặc thay main** theo hành vi của Shade.

Với Assembly:

- `appendAssemblyId=true`: assembly ID (như `jar-with-dependencies`) trở thành classifier của attached archive.
- `appendAssemblyId=false`: bỏ classifier, có thể thay main khi archive format trùng packaging.

Khi consumer khai báo dependency không classifier, Maven chọn main. Khi có `<classifier>all</classifier>` hoặc `<classifier>jar-with-dependencies</classifier>`, Maven tìm variant tương ứng. Việc kiểm tra đúng phải xét **POM, plugin executions, nội dung JAR, local repository và consumer dependencies**, không chỉ tên file ở `target`.

## Tài liệu chính thức

- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Dependency Artifact Types: https://maven.apache.org/repositories/dependencies
- Maven Shade Plugin — Attaching the Shaded Artifact: https://maven.apache.org/plugins/maven-shade-plugin/examples/attached-artifact.html
- Maven Shade Plugin — `shade:shade`: https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html
- Maven Shade Plugin — Manifest Resource Transformers: https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html
- Maven Assembly Plugin — Usage and Executable JAR: https://maven.apache.org/plugins/maven-assembly-plugin/usage.html
- Maven Assembly Plugin — `assembly:single`: https://maven.apache.org/plugins/maven-assembly-plugin/single-mojo.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Guide to Using Attached Tests: https://maven.apache.org/guides/mini/guide-attached-tests.html
