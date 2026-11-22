# finalName và sự khác nhau với tọa độ artifact trong Maven

## 1. Vì sao tên JAR trong target/ có thể khác tên artifact?

Khi làm việc với Maven, bạn có thể thấy hai đường dẫn cùng chỉ đến **một bản build** nhưng tên file khác nhau:

~~~text
Trong project sau mvn package:
target/inventory-cli.jar

Trong local Maven repository sau mvn install:
~/.m2/repository/org/example/build/cli-tool/2.4.0/cli-tool-2.4.0.jar
~~~

Điều này **không phải lỗi Maven**. Hai tên có hai trách nhiệm:

- `<build><finalName>inventory-cli</finalName>` điều khiển **tên cơ sở của file đóng gói trong thư mục build**, thông thường là `target/inventory-cli.jar` với Maven JAR Plugin.
- Các tọa độ `groupId:artifactId:version`, kết hợp loại/extension và classifier khi cần, định danh **artifact trong Maven repository**. Ở ví dụ là `org.example.build:cli-tool:2.4.0`.

**Cốt lõi:**

> **`finalName` là tên file build output, không phải một phần của tọa độ Maven. Đổi `finalName` không đổi `groupId`, `artifactId`, `version` hay tọa độ mà project khác khai báo trong `<dependency>`.**

Đây là kiến thức quan trọng khi viết CI/CD, tạo JAR chạy bằng `java -jar`, cấu hình artifact upload, phát hành library, hoặc quản lý Maven multi-module.

Bài này tập trung vào Maven 3.9.x và Java 17, với ví dụ JAR chạy được và một project consumer xác minh rằng `finalName` khác `artifactId` vẫn resolve dependency theo tọa độ bình thường.

## 2. Ba nhóm tên cần tách biệt

### 2.1. Maven coordinates: danh tính artifact

POM có:

~~~xml
<groupId>org.example.build</groupId>
<artifactId>cli-tool</artifactId>
<version>2.4.0</version>
<packaging>jar</packaging>
~~~

Ba trường chính `groupId`, `artifactId`, `version` thường được gọi là **GAV**. Khi cần mô tả chính xác một file artifact cụ thể còn xét thêm **classifier** (nếu có) và **type/extension**. Maven có thể định danh main JAR và `-sources.jar` cùng GAV nhưng classifier khác nhau.

Những giá trị trên trả lời:

- **Ai/phạm vi nào?** `org.example.build`
- **Artifact/module nào?** `cli-tool`
- **Phiên bản nào?** `2.4.0`
- **Loại kết quả chính?** `jar`

Consumer sẽ khai báo dựa trên các tọa độ này, không dựa vào `inventory-cli.jar`.

### 2.2. Build output filename: file nằm trong target/

POM có thêm:

~~~xml
<build>
    <finalName>inventory-cli</finalName>
</build>
~~~

Theo Maven POM Reference, `finalName` là **tên cơ sở, không gồm phần mở rộng** của sản phẩm đóng gói. Với Maven JAR Plugin trong thiết lập thông thường, output là:

~~~text
target/inventory-cli.jar
~~~

Nếu không cấu hình `finalName`, giá trị mặc định thường là:

~~~text
${project.artifactId}-${project.version}
~~~

nên cùng project sẽ tạo:

~~~text
target/cli-tool-2.4.0.jar
~~~

`finalName` không phải nơi nhập cả đường dẫn `target/...` hoặc đuôi `.jar`; đó là **tên cơ sở**. Để đổi output directory, dùng cơ chế build directory/plugin outputDirectory riêng, và phải xét plugin cụ thể.

### 2.3. Repository artifact filename: chuẩn hóa theo tọa độ

Khi `mvn install` hoặc `mvn deploy`, Maven đặt artifact và POM vào repository theo mô hình coordinates/layout:

~~~text
org/example/build/cli-tool/2.4.0/
    cli-tool-2.4.0.jar
    cli-tool-2.4.0.pom
~~~

Với một release version thông thường và Maven repository layout chuẩn, tên được chuẩn hóa từ **artifactId-version**, không lấy nguyên `finalName`. Đây là lý do một binary được tạo với tên `inventory-cli.jar` vẫn xuất hiện là `cli-tool-2.4.0.jar` khi được cài/công bố trong Maven repository.

Đừng nhầm **đổi tên file vật lý** với **đổi danh tính artifact**.

## 3. Bảng so sánh: cái gì thay đổi và cái gì không?

Giả sử tọa độ luôn là `org.example.build:cli-tool:2.4.0` và dùng Maven JAR Plugin bình thường.

| Cấu hình `finalName` | JAR sau `package` | Artifact chính sau `install` | Tọa độ consumer dùng |
| --- | --- | --- | --- |
| Không ghi `finalName` | `target/cli-tool-2.4.0.jar` | `cli-tool-2.4.0.jar` | `org.example.build:cli-tool:2.4.0` |
| `inventory-cli` | `target/inventory-cli.jar` | `cli-tool-2.4.0.jar` | Không đổi |
| `stable-cli` | `target/stable-cli.jar` | `cli-tool-2.4.0.jar` | Không đổi |
| `release-2_4` | `target/release-2_4.jar` | `cli-tool-2.4.0.jar` | Không đổi |

Nếu thay **`artifactId`** thành `inventory-cli` nhưng vẫn giữ `finalName` là `stable-cli`, repository path/name cũng thay đổi theo artifactId mới, trong khi output file vẫn là `target/stable-cli.jar`. Nếu thay **`version`** thành `2.5.0` mà không đổi `finalName`, đường dẫn repository sẽ đổi sang `.../2.5.0/cli-tool-2.5.0.jar` nhưng local build output có thể vẫn mang `stable-cli.jar`.

Đây là hai nhóm thay đổi độc lập, dù giá trị mặc định của `finalName` vốn sử dụng artifactId/version nên có vẻ liên quan.

**Giới hạn:** các Maven plugins khác có quyền tự tính tên file, thêm classifier, tiền tố/hậu tố hoặc tạo nhiều sản phẩm. Bảng nói về **main JAR thông thường** theo JAR Plugin; không cam kết mọi ZIP/WAR/uber-JAR hay custom build plugin luôn áp dụng y hệt.

## 4. Từ source đến JAR rồi đến Maven repository

Hãy hình dung đường đi của cùng một build:

~~~text
pom.xml
  groupId    = org.example.build
  artifactId = cli-tool
  version    = 2.4.0
  packaging  = jar
  finalName  = inventory-cli
            |
            v
mvn package
            |
            v
target/inventory-cli.jar   <-- tên do finalName ảnh hưởng
            |
            v
mvn install                <-- cài main artifact theo POM coordinates
            |
            v
~/.m2/repository/org/example/build/cli-tool/2.4.0/
  cli-tool-2.4.0.jar        <-- tên theo tọa độ
  cli-tool-2.4.0.pom
            |
            v
Maven consumer dependency:
  org.example.build:cli-tool:2.4.0
~~~

`mvn package` tạo file vật lý để bạn trực tiếp chạy hoặc phân phối bằng CI. `mvn install` là phase về sau trong lifecycle: cài artifact và POM vào **local repository** để các Maven projects khác trên cùng máy resolve. `mvn deploy` tiếp tục công bố artifact lên remote repository được cấu hình, khi được phép.

**Maven repository là kho theo tọa độ**, không phải thư mục mà consumer tùy tiện tìm file theo tên mà `finalName` đã đặt.

Điều này cũng giải thích vì sao đổi `finalName` **không tự đổi tên module** hiển thị trong `mvn dependency:tree` hoặc vị trí artifact được fetch từ repository.

## 5. Ví dụ thực hành hoàn chỉnh Java 17: JAR có tên inventory-cli.jar

Tạo một project **độc lập**:

~~~text
jar-finalname-demo/
├── pom.xml
└── src/main/java/org/example/buildtool/
    ├── Greeter.java
    └── Main.java
~~~

Mục tiêu:

1. `pom.xml` có artifact coordinates `org.example.build:cli-tool:2.4.0`.
2. `<finalName>inventory-cli</finalName>` đặt tên output build thành `target/inventory-cli.jar`.
3. Maven JAR Plugin ghi `Main-Class` vào manifest để lệnh `java -jar` hoạt động.
4. Maven Install Plugin cài cùng artifact vào repository dưới tọa độ `cli-tool:2.4.0`.
5. Một Maven consumer độc lập khai báo `<artifactId>cli-tool</artifactId>`, không khai báo `inventory-cli`.

Không có thư viện Java runtime bên ngoài JDK trong producer nên `java -jar` chạy trực tiếp mà không cần fat JAR hoặc thư viện phụ cạnh bên. Đây là điều kiện **cố ý** để tách câu chuyện tên file/manifest khỏi classpath phức tạp.

### 5.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <!-- Maven coordinates: the stable identity in repositories -->
    <groupId>org.example.build</groupId>
    <artifactId>cli-tool</artifactId>
    <version>2.4.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <!-- Only the local package's base filename, without .jar -->
        <finalName>inventory-cli</finalName>

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
                            <mainClass>org.example.buildtool.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM hoàn chỉnh**, không phải mảnh cấu hình. Lưu ý:

- `groupId/artifactId/version` xác định artifact `org.example.build:cli-tool:2.4.0`.
- `packaging=jar` sử dụng JAR lifecycle thông thường; goal `jar:jar` đóng gói ở phase `package`.
- `finalName=inventory-cli` chỉ định **tên cơ sở file trong `target/`** cho JAR Plugin khi dùng default naming.
- `maven-jar-plugin` có `archive/manifest/mainClass` để thêm `Main-Class`, một thông tin **khác hẳn `finalName`**.
- `maven-install-plugin` version được pin để minh họa install phase nhất quán, nhưng không cần tự bind goal `install` vì lifecycle của packaging jar đã thực hiện việc đó theo quy tắc chuẩn.
- `maven.compiler.release=17` yêu cầu bytecode/API Java 17 khi compiler phù hợp; máy vẫn phải có JDK thích hợp, nó không tự cài JDK.
- `project.build.sourceEncoding=UTF-8` điều khiển encoding source ở các plugin hỗ trợ.

Tọa độ `org.example.build:cli-tool:2.4.0` chỉ là ví dụ tự tạo. Không coi chúng là artifact đã tồn tại trên Maven Central.

### 5.2. Greeter.java

Tệp `src/main/java/org/example/buildtool/Greeter.java`:

~~~java
package org.example.buildtool;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String rawName) {
        String name = rawName.strip();
        if (name.isEmpty()) {
            name = "guest";
        }
        return "Hello, " + name + "!";
    }
}
~~~

`Greeter` cung cấp một API public độc lập để **Maven consumer** dùng ở phần sau. Mã sử dụng `String.strip()` của JDK 17, không có thư viện thứ ba. `rawName` trong demo không null; nếu đưa null vào method thì sẽ phát sinh `NullPointerException`, không phải tình huống được xử lý sẵn.

Kết quả method:

~~~text
Greeter.greet(" Maven ") -> "Hello, Maven!"
Greeter.greet("   ")     -> "Hello, guest!"
~~~

Đoạn trên là **minh họa giá trị trả về**, không phải stdout của Java source file. Chỉ file có `main` mới trực tiếp được chạy.

### 5.3. Main.java

Tệp `src/main/java/org/example/buildtool/Main.java`:

~~~java
package org.example.buildtool;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet(" Maven "));
        System.out.println("args=" + args.length);
    }
}
~~~

Đây là entry point cho `java -jar`. Nó có chính xác method `public static void main(String[] args)`, và fully qualified class là `org.example.buildtool.Main` — khớp `mainClass` trong POM. **Tên class này không phụ thuộc vào `finalName`**.

Trong ví dụ, truyền hai tham số bất kỳ cho `java -jar` thì `args.length=2`. Chúng không được dùng làm tên, chỉ dùng để kiểm tra argument handling.

## 6. Build, chạy JAR và stdout chính xác

Ở thư mục `jar-finalname-demo/`:

~~~bash
mvn -B -ntp clean package
~~~

Khi compile/package thành công, những file trọng tâm sẽ tương tự:

~~~text
target/
├── classes/
│   └── org/example/buildtool/
│       ├── Greeter.class
│       └── Main.class
└── inventory-cli.jar
~~~

Maven có thể sinh thêm metadata, thư mục compiler status và resource/plugin output khác. Cây trên **rút gọn**, nhưng file JAR chính cần tìm là **`target/inventory-cli.jar`**.

Chạy từ thư mục project:

~~~bash
java -jar target/inventory-cli.jar one two
~~~

**Stdout chính xác của riêng lệnh Java:**

~~~text
Hello, Maven!
args=2
~~~

Lệnh `mvn package` có log riêng (INFO, download, compile, jar creation...). Không trình bày hai dòng trên như stdout đầy đủ của Maven.

Nếu bạn đổi `<finalName>inventory-cli</finalName>` thành `<finalName>stable-cli</finalName>` rồi **chạy `mvn clean package`**, lệnh phù hợp mới là:

~~~bash
java -jar target/stable-cli.jar one two
~~~

**Output Java vẫn gồm đúng hai dòng**. Tên file đổi nhưng main class/logic/tọa độ Maven không đổi. Trong thực hành nên dùng `clean` khi so sánh hai tên để tránh JAR cũ còn trong `target/` dẫn tới hiểu nhầm.

### 6.1. Có thể chạy bằng classpath không?

Có. `java -jar` là chế độ dựa trên JAR manifest, còn lệnh dưới gọi thẳng class đã được compile:

~~~bash
java -cp target/classes org.example.buildtool.Main one two
~~~

Kết quả cũng là:

~~~text
Hello, Maven!
args=2
~~~

Trong lệnh thứ hai, tên `inventory-cli.jar` **không xuất hiện**, bởi JVM đang chạy từ `target/classes`. Điều đó giúp phân biệt **runtime class entry point** với **đường dẫn file JAR sản phẩm**. Với ứng dụng dùng third-party JAR, `-cp` cần bao gồm các runtime dependencies thích hợp, không phải chỉ `target/classes`.

## 7. Manifest: Main-Class là một khái niệm khác finalName

Một file JAR là ZIP archive có thể chứa `META-INF/MANIFEST.MF`. Khi chạy:

~~~bash
java -jar target/inventory-cli.jar
~~~

Java launcher tìm `Main-Class` trong manifest của JAR để biết cần chạy class nào. Nó **không** suy tên main class từ tên file `inventory-cli.jar`, `artifactId` hoặc `groupId`.

POM đã dùng:

~~~xml
<configuration>
    <archive>
        <manifest>
            <mainClass>org.example.buildtool.Main</mainClass>
        </manifest>
    </archive>
</configuration>
~~~

Đây là **mảnh cấu hình của Maven JAR Plugin**, không phải thuộc tính đặt ở root `<project>`. Nó tạo manifest có entry chính tương tự:

~~~text
Manifest-Version: 1.0
Main-Class: org.example.buildtool.Main
~~~

**Manifest thực tế có thể có những entries khác, versioned metadata hoặc thứ tự/line endings khác**. Đoạn trên chỉ minh họa hai entries quan trọng, không phải toàn bộ tệp manifest byte-for-byte.

Bốn giá trị không đồng nhất:

| Giá trị | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| `finalName` | `inventory-cli` | Tên file output trong target, không gồm `.jar`. |
| `artifactId` | `cli-tool` | Tên artifact trong Maven coordinates/repository. |
| `version` | `2.4.0` | Phiên bản artifact, ảnh hưởng repository path và dependency resolution. |
| `Main-Class` | `org.example.buildtool.Main` | Entry class mà `java -jar` khởi chạy. |

Nếu JAR không có `Main-Class` mà bạn gọi `java -jar`, Java có thể báo lỗi dạng `no main manifest attribute`, **dù tên JAR hoàn toàn đúng**. Khi đó cần cấu hình manifest, không phải đổi `finalName`.

## 8. Kiểm tra nội dung JAR bằng JDK tools

Lệnh:

~~~bash
jar --list --file target/inventory-cli.jar
~~~

thường liệt kê ít nhất:

~~~text
META-INF/
META-INF/MANIFEST.MF
org/example/buildtool/Greeter.class
org/example/buildtool/Main.class
~~~

Đây là **danh sách rút gọn** của những entries cần kiểm tra, không phải cam kết chính xác mọi entry/metadata/order của lệnh `jar --list` trên các JDK/plugin khác nhau.

Bạn có thể kiểm tra bằng cách giải nén vào **một thư mục tạm riêng** thay vì làm bẩn source root, hoặc dùng công cụ xem ZIP/JAR của IDE. Đối với bài này, `java -jar` chạy thành công là cách kiểm tra thực tế rằng **Main-Class** được khai báo đúng và class tồn tại.

Để kiểm tra JAR ở mức mã máy (khi cần debug), có thể dùng:

~~~bash
javap -classpath target/inventory-cli.jar org.example.buildtool.Main
~~~

Bạn sẽ thấy khai báo `main(java.lang.String[])` trong kết quả `javap`. Đây là công cụ JDK đọc class từ JAR, không cần Maven repository. Nó **không** cho biết project có được deploy lên remote repository hay chưa.

Với Java 17, kiểm phiên bản công cụ trên terminal:

~~~bash
java --version
javac --version
mvn --version
~~~

Maven có thể đang chạy trên JDK khác với lệnh `java` trong PATH nếu môi trường có toolchains/JAVA_HOME. Cần kiểm tra điều đó nếu JAR báo `UnsupportedClassVersionError`.

## 9. install: cùng artifact nhưng tên trong local repository theo tọa độ

Sau khi `package` chạy tốt, từ producer project:

~~~bash
mvn -B -ntp clean install
~~~

Lifecycle chạy tới `install` và cài main JAR/POM vào local Maven repository. Với tọa độ của ví dụ và repository mặc định, vị trí dự kiến:

~~~text
~/.m2/repository/
└── org/example/build/cli-tool/2.4.0/
    ├── cli-tool-2.4.0.jar
    └── cli-tool-2.4.0.pom
~~~

**Quan trọng:** Maven Install Plugin lấy thông tin `groupId/artifactId/version` của project để xác định path trong repository. Nó không lấy `finalName=inventory-cli` để tạo `.../inventory-cli/2.4.0/inventory-cli.jar`.

Điều này có nghĩa:

- Trong `target/`: vẫn là `inventory-cli.jar`.
- Trong local repository: main artifact ở chuẩn tên `cli-tool-2.4.0.jar`.
- Consumer dùng `org.example.build:cli-tool:2.4.0`.
- File JAR được install chứa cùng compiled classes và manifest do `package` tạo (giả định không có plugin sửa artifact giữa các phase). Maven có thể copy/đặt file vào local repository theo quy tắc của nó.
- Không cần consumer biết `inventory-cli.jar` khi resolve qua Maven.

Đường dẫn local repository mặc định có thể được thay bằng `~/.m2/settings.xml` hoặc `-Dmaven.repo.local=...`. **Đừng hard-code `~/.m2/repository` như một định luật** trong script production.

Một cách xác minh khác:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.build.finalName -q -DforceStdout
~~~

Với project mẫu và goal Help Plugin hỗ trợ, các giá trị biểu thức tương ứng là:

~~~text
cli-tool
inventory-cli
~~~

Đây là **hai kết quả riêng tương ứng với hai lệnh**, không phải cam kết output log nguyên văn, bởi `-q`, plugin resolution và environment có thể ảnh hưởng thông báo hiển thị. Chúng chứng minh Maven model hiểu hai trường khác nhau.

## 10. Project consumer: không dùng finalName để khai báo dependency

Đây là phép kiểm thực tế quan trọng nhất: một project thứ hai vẫn resolve artifact theo **tọa độ**, bất kể file trong `target/` của producer tên gì.

Sau khi đã chạy `mvn install` ở producer, tạo một project **độc lập** bên cạnh:

~~~text
finalname-workshop/
├── jar-finalname-demo/          # producer, đã install
│   └── ...
└── cli-consumer/
    ├── pom.xml
    └── src/main/java/org/example/consumer/ConsumerMain.java
~~~

Không cần thêm cả hai vào một Maven aggregator để consumer tìm artifact đã install; local repository dùng chung là đủ cho ví dụ này. Trong thực tế có thể dùng multi-module reactor nếu muốn build cùng nhau, nhưng Maven dependencies vẫn phải khai báo bằng coordinates.

### 10.1. Consumer pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.consumer</groupId>
    <artifactId>cli-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.build</groupId>
            <artifactId>cli-tool</artifactId>
            <version>2.4.0</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM hoàn chỉnh của consumer.** Hãy chú ý:

- Dependency có `artifactId=cli-tool`, vì producer tọa độ là `cli-tool`.
- Không có `<artifactId>inventory-cli</artifactId>`.
- Không có dependency `<finalName>`, vì `finalName` **không phải một trường trong tọa độ dependency**.
- Consumer có artifactId `cli-consumer` của riêng mình và dùng tên file build mặc định `cli-consumer-1.0.0.jar`, vì **POM consumer không cấu hình finalName**.

Nếu ghi nhầm:

~~~xml
<dependency>
    <groupId>org.example.build</groupId>
    <artifactId>inventory-cli</artifactId>
    <version>2.4.0</version>
</dependency>
~~~

thì đó là **tọa độ khác**, thường không resolve được từ artifact mà producer đã install. **Đoạn này chỉ là cấu hình sai minh họa**, không được dùng trong POM runnable của consumer.

### 10.2. ConsumerMain.java

Tệp `cli-consumer/src/main/java/org/example/consumer/ConsumerMain.java`:

~~~java
package org.example.consumer;

import org.example.buildtool.Greeter;

public final class ConsumerMain {
    private ConsumerMain() {
    }

    public static void main(String[] args) {
        System.out.println("consumer=" + Greeter.greet(" Maven "));
    }
}
~~~

Mã này import `Greeter` từ producer JAR. Nó không biết hay cần biết file `target/inventory-cli.jar` trong project producer.

### 10.3. Build consumer

Từ thư mục `cli-consumer/`, với producer `cli-tool:2.4.0` đã install trong cùng Maven local repository:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Lệnh `dependency:tree` hiển thị artifact được nhận diện bằng tọa độ như:

~~~text
org.example.build:cli-tool:jar:2.4.0:compile
~~~

Đây là **một dòng minh họa của phần dependency graph**, không phải output Maven toàn bộ. Bạn sẽ không thấy `inventory-cli` như artifactId của producer.

Tạo runtime dependency directory cho lệnh Java chạy ngoài Maven:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
~~~

Vì producer không có third-party runtime dependencies, file chính cần có trong thư mục này là:

~~~text
target/dependency/cli-tool-2.4.0.jar
~~~

Tên JAR **do plugin copy từ resolved artifact trong repository** theo convention; không phải `inventory-cli.jar` của producer build output. Đây là behavior minh họa khi dùng configuration/parameters mặc định của goal `copy-dependencies`; tùy chọn stripVersion/prependGroupId có thể đổi tên các bản copy.

Trên Linux/macOS:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.consumer.ConsumerMain
~~~

Trên Windows PowerShell/CMD:

~~~text
java -cp "target\classes;target\dependency\*" org.example.consumer.ConsumerMain
~~~

**Stdout chính xác của riêng lệnh Java** trong demo:

~~~text
consumer=Hello, Maven!
~~~

Consumer đã compile/run thành công **mà không cần biết finalName**. Đây là bằng chứng thực hành cho sự độc lập giữa build filename và Maven artifact coordinates.

## 11. deploy: remote repository cũng nhận artifact theo tọa độ

Với Maven Deploy Plugin, nếu producer POM được cấu hình `distributionManagement` và có quyền ghi vào remote repository, lệnh:

~~~bash
mvn -B -ntp clean deploy
~~~

sẽ build, install, deploy main artifact và POM theo tọa độ. Với một release artifact `2.4.0` trong repository layout chuẩn, đường dẫn thường là:

~~~text
<repository-base-url>/
  org/example/build/cli-tool/2.4.0/
    cli-tool-2.4.0.jar
    cli-tool-2.4.0.pom
~~~

`<repository-base-url>` ở trên **chỉ là ký hiệu tài liệu**, không phải địa chỉ có thể sử dụng trực tiếp. Một repository manager có thể hiển thị API/UI path khác với physical layout, nhưng Maven coordinates vẫn là định danh dùng để resolve.

Không chạy `mvn deploy` vào một repository thật chỉ để thử đổi tên file nếu chưa được phân quyền publish. Bạn có thể học đủ kiến thức `finalName` vs coordinates bằng `package`/`install` trên local machine.

**Không thể đổi identity của artifact trên Maven Central bằng cách chỉ đặt `finalName`.** Nếu muốn consumer thực sự dùng một tên artifact mới, bạn phải đổi **artifactId** ở POM, phát hành tọa độ mới và cập nhật consumers; đó là thay đổi dependency compatibility/release governance, không phải một tùy chỉnh đóng gói đơn giản.

## 12. finalName không tự đổi version và ngược lại

Giả sử producer có:

~~~xml
<artifactId>cli-tool</artifactId>
<version>2.4.0</version>
<build>
    <finalName>inventory-cli</finalName>
</build>
~~~

Trong một lần nâng version:

~~~xml
<artifactId>cli-tool</artifactId>
<version>2.5.0</version>
<build>
    <finalName>inventory-cli</finalName>
</build>
~~~

Output trong `target/` vẫn có thể là:

~~~text
target/inventory-cli.jar
~~~

nhưng artifact khi install đổi thành:

~~~text
org/example/build/cli-tool/2.5.0/cli-tool-2.5.0.jar
~~~

và consumer mới phải dùng `<version>2.5.0</version>` nếu muốn bản mới đó.

**Hệ quả thực hành:**

- Tên cố định `inventory-cli.jar` giúp deployment script đơn giản vì không cần sửa tên file mỗi version.
- Nhưng cũng dễ **ghi đè artifact build output của các version khác nhau** khi copy chung vào một thư mục.
- Trong CI, ngoài filename nên ghi **GAV, Git commit SHA, build job ID và checksum** vào release record/provenance.
- Khi upload qua file storage hoặc Docker build context, không coi `inventory-cli.jar` là bằng chứng file thuộc version nào. Cùng một filename có thể chứa bytecode của nhiều bản khác nhau ở các lần build.
- Nếu cần version hiện trong file name để dễ so sánh, giữ default `artifactId-version` hoặc sử dụng một convention phù hợp thay vì cưỡng ép tên cố định.

Ngược lại, nếu bạn bỏ `finalName` khỏi POM sau khi nâng version, giá trị default sẽ là `cli-tool-2.5.0` và target JAR sẽ mang tên `target/cli-tool-2.5.0.jar`. Maven coordinates vẫn xuất phát từ các trường POM, không phải từ tên file ấy.

## 13. finalName, directory, outputDirectory và tên tệp thực tế

Maven có nhiều thông số build liên quan đến đường dẫn:

| Cấu hình | Vai trò thông thường |
| --- | --- |
| `<build><directory>...` | Thư mục Maven build output, mặc định `target`. |
| `<build><finalName>...` | Tên cơ sở của artifact đóng gói, mặc định `artifactId-version`. |
| Maven JAR Plugin `<outputDirectory>...` | Thư mục JAR Plugin đặt file JAR, mặc định `${project.build.directory}`. |
| Maven JAR Plugin `<classifier>...` | Phân loại artifact bổ sung khi plugin được cấu hình tạo/attach. |
| `groupId/artifactId/version` | Tọa độ Maven trong repositories. |

Trong phần lớn project JAR:

~~~text
build.directory = target
build.finalName = inventory-cli
result          = target/inventory-cli.jar
~~~

Nếu một plugin chọn output directory khác hoặc bỏ qua `project.build.finalName`, kết quả có thể khác. **Không suy ra tên và đường dẫn của mọi plugin chỉ từ field finalName**; hãy xem tài liệu goal/plugin đúng phiên bản đang dùng.

Cẩn trọng khi dùng đường dẫn tương đối:

- `finalName` là **filename base**, không nên nhét dấu `/` hoặc `\` để giả lập thư mục.
- Trong CI, đường dẫn `target/inventory-cli.jar` là **relative to working directory của module**.
- Maven multi-module có nhiều `target/` khác nhau: `module-a/target/...` và `module-b/target/...`.
- Với builds trên Windows, shell path khác Linux; Maven property `project.build.directory`/`project.build.finalName` phù hợp để các plugin sử dụng, còn OS-level commands phải theo hệ điều hành.

## 14. Phân biệt finalName với JAR Plugin configuration riêng

Maven JAR Plugin có thể nhận cấu hình riêng cho một output archive, ví dụ ý tưởng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <finalName>special-jar-name</finalName>
    </configuration>
</plugin>
~~~

Đây là **mảnh plugin config minh họa**, không phải POM runnable chính ở mục 5. Với Maven JAR Plugin phiên bản có tham số `finalName`, cấu hình riêng có thể **chỉ ảnh hưởng output của plugin đó**. Tùy phiên bản plugin và setup, việc gán plugin-level `finalName` khác `project.build.finalName` có thể khiến các goal khác vẫn đọc giá trị `project.build.finalName` ban đầu.

Bởi vậy, để thay tên **sản phẩm chính của module** và giữ hành vi thông dụng dễ hiểu, `<build><finalName>...` thường là nơi rõ ràng hơn. Chỉ override `<plugin><configuration><finalName>...` khi bạn hiểu các goal, archive attachments và cross-plugin interactions đang dùng.

**Không tự động xem `-DfinalName=...` hoặc `-Dproject.build.finalName=...` là cách đổi tên output đáng tin trong mọi project.** Một user property có thể không tương đương thay đổi field của Maven model; plugin có thể expose property riêng hoặc POM đã khóa configuration. Nếu cần profile thay tên, hãy viết rõ field `<build><finalName>...` theo cấu hình được Maven model hỗ trợ, hoặc dùng property trung gian được bạn định nghĩa.

## 15. Cách dùng property trung gian nếu muốn tên file cấu hình được

Một pattern rõ ràng là tự định nghĩa property riêng rồi **tham chiếu từ `finalName`**:

~~~xml
<properties>
    <distribution.file.basename>inventory-cli</distribution.file.basename>
</properties>

<build>
    <finalName>${distribution.file.basename}</finalName>
</build>
~~~

Đây là **mảnh POM**, không phải POM đầy đủ. Bây giờ build field `finalName` thực sự tham chiếu một property do project sở hữu.

Có thể thiết kế profile cho từng môi trường:

~~~xml
<profiles>
    <profile>
        <id>portable</id>
        <properties>
            <distribution.file.basename>inventory-cli</distribution.file.basename>
        </properties>
    </profile>
    <profile>
        <id>descriptive</id>
        <properties>
            <distribution.file.basename>cli-tool-2.4.0</distribution.file.basename>
        </properties>
    </profile>
</profiles>
~~~

**Đoạn trên là phần minh họa profiles**, phải tích hợp đúng vào POM có property mặc định. Mục tiêu là để mọi cấu hình đều dễ kiểm soát. Trong production, tránh copy version string `2.4.0` thủ công nếu có thể dùng `${project.version}`, để không vô tình tạo output file có tên version cũ.

Ví dụ ổn định hơn cho profile:

~~~xml
<properties>
    <distribution.file.basename>${project.artifactId}-${project.version}</distribution.file.basename>
</properties>
~~~

Nhưng **đừng hiểu rằng profile đổi tên sẽ đổi GAV**. Ngay cả khi file output được gọi `inventory-cli.jar` trong profile portable, repository identity vẫn là `cli-tool:2.4.0`.

Một quy ước tốt: chỉ cho phép profile thay **artifact filename khi đóng gói**, không tự thay đổi groupId/artifactId/version bất ngờ trong từng môi trường. Nếu version được tính tự động bằng CI-friendly versions, cần kiểm tra Maven model/flatten plugin và release policy riêng; field `finalName` không tự giải quyết bài toán phiên bản publish.

## 16. finalName không phải classifier

Classifier là thành phần tùy chọn của tọa độ artifact dùng phân biệt nhiều artifacts **cùng groupId/artifactId/version/extension**.

Ví dụ một project có main artifact và source archive:

~~~text
org.example.build:cli-tool:2.4.0:jar           # main jar
org.example.build:cli-tool:2.4.0:jar:sources   # sources jar (ký hiệu mô tả)
~~~

Trong Maven dependency XML, classifier được khai báo riêng:

~~~xml
<dependency>
    <groupId>org.example.build</groupId>
    <artifactId>cli-tool</artifactId>
    <version>2.4.0</version>
    <classifier>sources</classifier>
    <type>jar</type>
</dependency>
~~~

Đây là **mảnh minh họa**; `sources` JAR chứa source, thông thường **không phù hợp làm dependency để compile class**, nên chỉ dùng khi thực sự cần artifact source. Project mẫu không tự sinh `-sources.jar` vì chưa cấu hình Maven Source Plugin.

Nếu Source Plugin attach archive, tên bản release trong Maven repository thường là:

~~~text
cli-tool-2.4.0.jar
cli-tool-2.4.0-sources.jar
~~~

Cả hai có GAV giống nhau, nhưng classifier khác. **`finalName` không tự thêm classifier vào tọa độ main artifact**. Tên output vật lý của classifier archive trong target có thể dùng `finalName` hoặc quy tắc riêng của plugin; không nên suy ra tên artifact trong repository chỉ từ tên target file.

Cần tránh một lỗi phổ biến: đổi `finalName` thành `cli-tool-2.4.0-sources` rồi nghĩ đã phát hành đúng sources artifact. Nếu plugin vẫn attach nó như main JAR, classifier thực sự **chưa được đặt**. Tọa độ cần classifier phải được khai báo bằng cơ chế plugin/attachment thích hợp.

## 17. finalName và packaging: JAR, WAR, EAR, ZIP

`finalName` là một field trong Maven `build`, không riêng cho JAR. Nhưng tên file cuối cùng còn do **packaging và plugin thực hiện**:

| Packaging/công cụ | Output thường gặp | Cần lưu ý |
| --- | --- | --- |
| `jar` + Maven JAR Plugin | `target/${finalName}.jar` | Có thể thêm classifier, attach artifacts. |
| `war` + Maven WAR Plugin | `target/${finalName}.war` | Tên WAR và context path deploy ở server là hai khái niệm khác, phụ thuộc container/config. |
| `ear` + Maven EAR Plugin | `target/${finalName}.ear` | EAR packaging có cấu hình và module descriptors riêng. |
| `pom` parent/aggregator | Không mặc nhiên tạo JAR/WAR cùng tên | Không dùng `finalName` để mong có một binary output từ parent packaging POM. |
| Maven Assembly Plugin | Có thể tạo `${finalName}-<descriptorId>.zip` hoặc tên khác | Final naming phụ thuộc plugin, descriptor, `appendAssemblyId`. |
| Maven Shade Plugin | Có thể thay main JAR hoặc attach shaded classifier | Đặc điểm tùy `shadedArtifactAttached`, `shadedClassifierName` và config. |

**Không xem bảng là cam kết cho mọi plugin version/config.** Với project đóng gói tùy biến, xem goal thực sự tạo artifact gì và nó được **attach** theo coordinates nào.

Ví dụ WAR tên `inventory-web.war` không làm artifactId tự đổi thành `inventory-web`. Maven dependency/repository vẫn theo `groupId:artifactId:version` của WAR artifact.

## 18. JAR chạy được không đồng nghĩa “fat JAR”

POM ví dụ có cấu hình:

~~~xml
<archive>
    <manifest>
        <mainClass>org.example.buildtool.Main</mainClass>
    </manifest>
</archive>
~~~

và `finalName=inventory-cli`. Kết quả là một JAR **có Main-Class**, nhưng **không có gì trong hai cấu hình này bảo đảm mọi third-party runtime dependencies đã được đóng gói vào một file duy nhất**.

Với demo, `java -jar target/inventory-cli.jar` hoạt động vì code chỉ dùng JDK. Nếu sau này `Main` import một library bên ngoài:

~~~java
import org.apache.commons.lang3.StringUtils;
~~~

thì chỉ thêm dependency compile trong Maven POM chưa đủ để `java -jar inventory-cli.jar` chạy độc lập trên máy không có những library đó ở runtime classpath. JAR Plugin thông thường **không tự biến main JAR thành uber-JAR**.

Các lựa chọn khi có dependencies bên ngoài:

- Phân phối các JAR phụ cùng một launcher có classpath phù hợp.
- Tạo manifest `Class-Path` phù hợp với layout phân phối, nếu ứng dụng và JDK launcher có thể truy cập các thư viện ở đường dẫn tương đối cần thiết.
- Sử dụng Maven Shade Plugin hoặc Assembly Plugin với cấu hình phù hợp để tạo bản bundle/fat JAR, có thể cần merge services/signatures/resources.
- Dùng packaging/container launcher phù hợp cho ứng dụng server, thay vì ép mọi thứ thành executable JAR.

**Maven `finalName` không cấu hình manifest `Class-Path` hoặc `Main-Class`.** Những thứ đó là vấn đề riêng của archive plugin/launcher. Đổi tên JAR mà runtime thiếu dependencies vẫn sẽ tiếp tục thiếu dependencies.

Khi Shade/Assembly thay main artifact hoặc attach classifier, **phải kiểm tra tọa độ cuối được install/deploy**. Không được mặc định bản fat JAR có cùng vai trò binary và classifier với main JAR nếu plugin configuration chưa được xác nhận.

## 19. SNAPSHOT và timestamped artifacts: trường hợp đặc biệt

Với:

~~~xml
<groupId>org.example.build</groupId>
<artifactId>cli-tool</artifactId>
<version>2.5-SNAPSHOT</version>
<build>
    <finalName>inventory-cli</finalName>
</build>
~~~

`mvn package` vẫn có thể tạo:

~~~text
target/inventory-cli.jar
~~~

`mvn install` thường cài snapshot trong local repository theo baseVersion `2.5-SNAPSHOT`, ví dụ:

~~~text
.../cli-tool/2.5-SNAPSHOT/cli-tool-2.5-SNAPSHOT.jar
~~~

Khi `mvn deploy` đến snapshot remote repository hỗ trợ unique timestamped snapshots, server có thể lưu:

~~~text
.../cli-tool/2.5-SNAPSHOT/
    cli-tool-2.5-20261110.120000-1.jar
    cli-tool-2.5-20261110.120000-1.pom
    maven-metadata.xml
~~~

**Timestamp và buildNumber trong ví dụ là minh họa**, không dự báo output thực tế của repository. Maven metadata giúp consumer resolve baseVersion `2.5-SNAPSHOT` thành file timestamped tương ứng.

Ngay cả với snapshot, `finalName` không phải source của groupId/artifactId/version. Tên remote được tính theo Maven repository layout/resolved snapshot version, không copy literal `inventory-cli.jar`.

Nếu bạn cần chốt một binary reproducible, hãy quản lý version, repository immutability, build provenance và checksum; chỉ chốt `finalName` không làm snapshot trở thành artifact bất biến.

## 20. Multi-module và parent POM: mỗi module có tọa độ riêng

Một aggregator có thể khai báo:

~~~xml
<modules>
    <module>core</module>
    <module>cli</module>
</modules>
~~~

Mỗi Maven child có `pom.xml` và artifactId riêng. Nếu parent định nghĩa:

~~~xml
<build>
    <finalName>shared-name</finalName>
</build>
~~~

và các child kế thừa setting này, **nhiều module có thể sinh file cùng tên `shared-name.jar` trong các thư mục `target/` khác nhau**. Chúng chưa chắc va chạm khi build trong reactor vì mỗi child có `target/` riêng, nhưng **sẽ dễ ghi đè nhau nếu CI gom tất cả JAR vào một deployment directory chung**.

Vì vậy:

1. Nếu muốn default filename duy nhất theo module, thường tốt hơn là sử dụng `${project.artifactId}-${project.version}` hoặc một convention có artifactId.
2. Nếu chỉ ứng dụng CLI cần tên ổn định, đặt `finalName` trong POM của **module CLI**, không ở parent dùng chung, trừ khi đó là chủ đích toàn tổ chức.
3. Không dùng `<modules>` để suy rằng project con kế thừa `finalName`; **parent inheritance** và **reactor aggregation** khác nhau. Child phải khai báo `<parent>` phù hợp để kế thừa cấu hình.
4. Với packaging `pom` của parent, thường không có main archive tương ứng với `finalName`.
5. Một Maven dependency giữa child modules vẫn cần tọa độ `groupId/artifactId/version`; trùng `finalName` không tạo một dependency.
6. Trong CI, lưu artifacts với đường dẫn tương ứng module, hoặc thêm thông tin coordinates/version để phân biệt thay vì chỉ upload tất cả `target/*.jar` vào cùng một thư mục.

Một cách an toàn để inspect output là dùng Maven Help Plugin **theo từng module**; đừng tự suy từ filename:

~~~bash
mvn -pl :cli help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
mvn -pl :cli help:evaluate -Dexpression=project.artifactId -q -DforceStdout
~~~

Các lệnh trên chỉ mang tính mẫu cho một reactor thực sự có artifactId `cli`. Trong project đơn-module ví dụ ở mục 5, `-pl :cli` không áp dụng.

## 21. CI/CD: chọn đúng file local mà vẫn phát hành theo coordinates

Trong pipeline, có thể cần copy JAR sang một Docker build context hoặc upload file sang release storage. Khi POM có `finalName=inventory-cli`:

~~~bash
mvn -B -ntp clean package
java -jar target/inventory-cli.jar one two
~~~

CI có thể upload **`target/inventory-cli.jar`**, vì đó là file build output được tạo. Nhưng nếu pipeline muốn publish vào Maven repository, nên dùng cơ chế `mvn deploy` hoặc công cụ repository chính thức để phát hành **theo tọa độ**.

**Tránh cấu hình nhầm như sau:**

- CI chờ `target/cli-tool-2.4.0.jar` trong khi POM đã đổi `finalName` thành `inventory-cli` → báo file not found.
- CI dùng tên `inventory-cli.jar` làm `artifactId` cho một lần `install:install-file` tùy biến → artifact được publish dưới tọa độ ngoài ý muốn.
- CI copy `target/*.jar` mà không phân biệt main, sources, javadoc, shaded hoặc tests JAR → có thể chọn nhầm artifact.
- CI build nhiều module với cùng finalName rồi flatten tất cả outputs vào một folder → file bị overwrite.
- CI dựa trên `finalName` để suy version, nhưng giá trị đã được cố định và không thay theo version → traceability kém.
- CI gắn `Main-Class` nhưng bỏ runtime dependencies → artifact upload thành công nhưng `java -jar` fail lúc chạy.

Cách an toàn là **xác minh cả hai lớp thông tin**: `target/` có file đúng để chạy/đóng gói, còn `groupId:artifactId:version` đúng để cài/resolve/release.

Một ví dụ GitHub Actions đơn giản cho project có Maven Wrapper đã commit:

~~~yaml
name: Build executable JAR
on:
  push:
  pull_request:

jobs:
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Build JAR
        run: ./mvnw -B -ntp clean package
      - name: Smoke test executable JAR
        run: java -jar target/inventory-cli.jar one two
      - uses: actions/upload-artifact@v4
        with:
          name: inventory-cli-build
          path: target/inventory-cli.jar
~~~

**Ví dụ workflow này giả định repository có Maven Wrapper `mvnw`**; demo ở mục 5 chưa tự tạo wrapper. Nếu chưa có wrapper, hãy cấu hình Maven version tương ứng trong runner và dùng `mvn`. Nó là ví dụ packaging/smoke test, **không** deploy lên Maven repository hoặc công bố artifact ra ngoài.

Nếu cần reproducibility, thêm kiểm tra checksum và ghi nguồn commit/CI run/version trong artifact provenance; `finalName` một mình không đủ để chứng minh provenance.

## 22. Điều gì xảy ra nếu chỉ rename một JAR bằng lệnh shell?

Giả sử bạn build theo default:

~~~text
target/cli-tool-2.4.0.jar
~~~

rồi thực hiện một lệnh copy/rename bên ngoài Maven thành:

~~~text
target/inventory-cli.jar
~~~

Đó là **một thao tác filesystem**, không tương đương thay Maven POM.

Những điều cần nhớ:

- Tọa độ Maven `org.example.build:cli-tool:2.4.0` **không đổi** chỉ vì file được copy/rename.
- `Main-Class` trong manifest **không tự xuất hiện** nếu JAR gốc không có.
- Nếu vẫn chạy `mvn install` theo lifecycle, Install Plugin dùng **main artifact đã được project gắn/packaged**, không được bảo đảm sẽ chọn file bạn tự copy/rename ngoài Maven.
- Một file ngẫu nhiên tên `inventory-cli.jar` **không phải Maven artifact đáng tin** nếu không có coordinates/POM hoặc chưa được attach/install đúng.
- Nếu cần publish một file được tạo bên ngoài Maven, có goal `install:install-file`/`deploy:deploy-file` với metadata/coordinates được chỉ định rõ. Đây là workflow khác, phải kiểm soát cho đúng POM và chính sách repository.

Đặc biệt đừng chạy `install-file` với coordinates **suy từ filename** khi file có tên tùy chỉnh; hãy cung cấp chính xác groupId/artifactId/version/type phù hợp với hợp đồng dependency mà consumers sẽ dùng.

## 23. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Sau `mvn package` không thấy `target/cli-tool-2.4.0.jar`. | `finalName=inventory-cli` đã thay tên output. | Xem `project.build.finalName` và `target/inventory-cli.jar`. |
| Sau `mvn install` repository không có file `inventory-cli.jar`. | Repository filename theo coordinates. | Tìm `cli-tool-2.4.0.jar` dưới `org/example/build/cli-tool/2.4.0`. |
| Consumer khai báo `inventory-cli:2.4.0` và không resolve. | Nhầm finalName thành artifactId. | Dùng `org.example.build:cli-tool:2.4.0`. |
| `java -jar target/inventory-cli.jar` báo thiếu Main-Class. | Manifest không cấu hình entry point. | Thêm JAR Plugin `archive/manifest/mainClass` phù hợp. |
| `java -jar` có Main-Class nhưng bị `NoClassDefFoundError`. | JAR thường không bundle runtime dependencies. | Kiểm project runtime graph, launcher/manifest Class-Path hoặc Shade/Assembly. |
| `java -cp target/classes ...` chạy, `java -jar` không chạy. | Hai chế độ launcher khác; manifest/path/dependencies chưa đúng. | Đọc manifest và kiểm packaging. |
| CI upload `target/*.jar` nhưng chọn nhầm sources/shaded JAR. | Nhiều JAR output hoặc classifier. | Dùng path cụ thể, kiểm attached artifact/classifier. |
| Đổi version nhưng `target/inventory-cli.jar` vẫn giữ tên. | finalName cố định. | Đây là behavior dự kiến; ghi version/provenance riêng hoặc dùng default naming. |
| Hai Maven child output cùng tên `shared-name.jar`. | Parent finalName được kế thừa hoặc module settings trùng. | Giữ module paths, dùng artifactId trong tên hoặc override theo module. |
| Đặt `<finalName>target/myapp.jar</finalName>`. | Nhầm base filename với path/extension. | Đặt `finalName=myapp`; cấu hình output directory riêng nếu thật sự cần. |
| `-DfinalName=xyz` không đổi file. | Property này không chắc map tới Maven model field. | Dùng `build/finalName` hoặc property trung gian tham chiếu rõ. |
| Repository chứa `cli-tool-2.4.0.jar` nhưng bytes khác file build mong đợi. | Artifact bị sửa giữa phase, repository mutable, chọn sai project/version. | So checksum, build log, main artifact attachments và release immutability. |
| Chạy `mvn install` trong consumer mà tìm không thấy producer artifact. | Producer chưa install/deploy hoặc local repos khác nhau. | Cài producer với đúng tọa độ hoặc build bằng reactor/remote repo. |
| SNAPSHOT remote file tên có timestamp. | Snapshot repository dùng timestamped naming/metadata. | Consumer vẫn resolve baseVersion `-SNAPSHOT` qua metadata; không dùng finalName để đoán file. |
| Build sản xuất fail vì JDK version. | `maven.compiler.release` không cài JDK. | Kiểm `mvn --version` và toolchain/JAVA_HOME, chọn JDK hợp lệ. |
| WAR đặt finalName nhưng server deploy context không đúng. | WAR filename và runtime context config có thể khác nhau. | Xem container/WAR plugin/server deployment settings. |

Một quy trình debug gọn:

~~~text
1. Xác nhận POM: groupId/artifactId/version/packaging
2. Xác nhận build.finalName và plugin jar/war/shade config
3. Chạy mvn clean package
4. Xem đúng file output trong target
5. Kiểm JAR manifest / Main-Class / runtime dependencies
6. Chạy mvn install nếu cần consumer bằng tọa độ
7. Xem repository path chuẩn hóa và dependency:tree
8. Kiểm release/CI artifact upload path, classifier, checksum
~~~

## 24. Checklist trước khi phát hành JAR

- [ ] `groupId/artifactId/version` phản ánh đúng **danh tính** public của artifact.
- [ ] `packaging` và extension/classifier của artifact chính đúng với loại binary.
- [ ] `finalName` chỉ được dùng để đặt tên local build output; không trông chờ nó đổi GAV.
- [ ] Có lý do rõ nếu bỏ default `artifactId-version`, ví dụ CLI launcher cần tên cố định.
- [ ] Tên main class `<mainClass>...` trùng fully qualified class có `public static void main`.
- [ ] `java -jar` smoke test thành công trên JDK runtime mục tiêu, với dependencies đã được phân phối đúng.
- [ ] Kiểm `jar --list` và manifest nếu thay archive plugin.
- [ ] `mvn install` tạo artifact theo đúng Maven coordinates; consumer khai báo `artifactId`, không khai báo `finalName`.
- [ ] Khi build multi-module, không flatten mọi `target/*.jar` thành tên xung đột.
- [ ] Không quên version/provenance khi `finalName` cố định qua nhiều lần release.
- [ ] Attached artifacts (sources, tests, javadoc, shaded) có classifier rõ, không dựa vào filename tự đặt.
- [ ] Không cố sử dụng `finalName` để cấu hình output directory, repository ID hay Main-Class.
- [ ] CI không chọn JAR bằng wildcard quá rộng; biết rõ file đang upload/chạy.
- [ ] Khi deploy, repository policy/credentials và tọa độ đúng; không thử trên production repository tùy tiện.
- [ ] POM và plugins được pin version hợp lý, thay đổi plugin nên kiểm tra output naming/attach behavior.
- [ ] Nếu dùng `-SNAPSHOT`, hiểu khác biệt giữa local filename và timestamped remote snapshot.

## 25. Câu hỏi tự kiểm tra

1. **POM có `artifactId=cli-tool`, `version=2.4.0`, `finalName=inventory-cli`. File JAR sau package ở đâu?**  
   Với layout và JAR Plugin mặc định như ví dụ: `target/inventory-cli.jar`.

2. **Sau install, artifact nào được consumer tìm trong local Maven repository?**  
   `org.example.build:cli-tool:2.4.0`, thường lưu file `cli-tool-2.4.0.jar` dưới `org/example/build/cli-tool/2.4.0/`.

3. **Đổi `finalName` thành `stable-cli` có buộc consumer đổi `artifactId` không?**  
   Không. Tọa độ không đổi; consumer tiếp tục khai báo `cli-tool`.

4. **Nếu đổi `artifactId` thành `stable-cli` nhưng giữ `finalName=inventory-cli` thì sao?**  
   Output target vẫn có thể là `inventory-cli.jar`, nhưng GAV và path repository thay đổi theo artifactId mới.

5. **`java -jar inventory-cli.jar` cần gì để biết main class?**  
   `Main-Class` trong `META-INF/MANIFEST.MF`; tên file không cung cấp thông tin đó.

6. **Cài artifact bằng `mvn install` có đổi nội dung compiled classes không?**  
   Không phải mục đích của install; nó dùng artifact đã được tạo và gắn trong lifecycle, trừ khi một plugin khác chủ động thay đổi file.

7. **Một JAR có Main-Class và finalName đẹp có tự chứa runtime dependencies không?**  
   Không. Muốn executable standalone với third-party libraries cần thiết kế runtime classpath/bundle phù hợp.

8. **`finalName` có tự tạo sources classifier không?**  
   Không. Classifier là thành phần tọa độ riêng và cần plugin attachment phù hợp.

9. **Nâng version từ `2.4.0` lên `2.5.0` mà finalName cố định có đổi tên file target không?**  
   Không nhất thiết; trong demo vẫn là `inventory-cli.jar`, nhưng repository path và dependency version thay đổi.

10. **Vì sao CI upload tên cố định cần provenance?**  
    Vì nhiều builds/versions có thể tạo ra cùng filename, nên phải gắn Git SHA, GAV, timestamp/checksum ở metadata bên ngoài để truy vết.

11. **Trong multi-module, hai JAR cùng finalName có tự xung đột khi build không?**  
    Thường không nếu mỗi module có build output directory riêng; chúng có thể xung đột khi gom chung một thư mục triển khai.

12. **Maven consumer có thể resolve trực tiếp bằng local path `target/inventory-cli.jar` mà không có dependency coordinates?**  
    Maven chuẩn dùng coordinates/repository; có cách nạp file ngoài Maven nhưng đó là workflow riêng, không phải `<dependency>` thông thường.

13. **Snapshot remote mang timestamped filename có dùng finalName không?**  
    Không. Filename versioned trong repository do Maven snapshot resolution/metadata điều khiển.

14. **Nếu đặt output filename là `my-tool.jar`, có phải class main cần tên `my.tool.Main` không?**  
    Không. Main class được khai báo độc lập trong manifest và Java source.

## 26. Tài liệu tham khảo chính thức

- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `build.directory`, `build.finalName`, default `artifactId-version` và các ngoại lệ plugin.
- [Apache Maven — Maven Artifacts](https://maven.apache.org/repositories/artifacts.html): coordinates `groupId/artifactId/version`, classifier, extension, repository identity.
- [Apache Maven — Naming Conventions](https://maven.apache.org/guides/mini/guide-naming-conventions.html): groupId, artifactId, version và nguyên tắc đặt tên.
- [Apache Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html): goal đóng gói, output directory, classifier và tùy chọn archiver.
- [Apache Maven JAR Plugin — Make the JAR Executable](https://maven.apache.org/plugins/maven-jar-plugin/examples/executable-jar.html): manifest `Main-Class` và các vấn đề classpath runtime.
- [Apache Maven Install Plugin — Introduction](https://maven.apache.org/plugins/maven-install-plugin/): cách install artifact theo coordinates vào local repository.
- [Apache Maven Install Plugin — install:install](https://maven.apache.org/plugins/maven-install-plugin/install-mojo.html): main artifact, POM và attachments được install.
- [Apache Maven Deploy Plugin — Introduction](https://maven.apache.org/plugins/maven-deploy-plugin/): công bố artifacts/POM tới remote repositories theo Maven lifecycle.
- [Apache Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): đánh giá các Maven model expressions `project.artifactId` và `project.build.finalName`.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): quan sát dependency coordinates khi một project dùng artifact.
- [Apache Maven Dependency Plugin — dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): tạo runtime dependency directory từ Maven resolution.

**Kết luận:** `<build><finalName>` quyết định **tên cơ sở của file đóng gói trong `target/`** (khi plugin áp dụng giá trị đó); Maven coordinates quyết định **danh tính và đường dẫn artifact trong repository**, còn manifest `Main-Class` quyết định **Java launcher chạy class nào**. Ba khái niệm này độc lập. Bạn có thể tạo `target/inventory-cli.jar`, install nó thành `cli-tool-2.4.0.jar` và để consumer sử dụng `org.example.build:cli-tool:2.4.0` mà không có mâu thuẫn nào. Hãy kiểm tra cả tên file trong `target/` lẫn dependency graph/repository layout để tránh nhầm giữa tiện ích đóng gói và hợp đồng phát hành.
