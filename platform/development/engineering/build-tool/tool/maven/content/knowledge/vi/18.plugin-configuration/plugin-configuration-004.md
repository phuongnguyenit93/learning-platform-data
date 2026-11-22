# Cấu hình chung của plugin so với cấu hình riêng một execution trong Maven

## 1. Cùng một plugin, nhiều cách thực thi

Một Maven plugin là công cụ đảm nhiệm các công việc trong quá trình build: biên dịch, xử lý tài nguyên, chạy kiểm thử, đóng gói JAR, tạo tài liệu hoặc xuất bản artifact. Mỗi plugin có thể cung cấp nhiều **goal**; mỗi lần Maven đưa một hoặc nhiều goal vào một vị trí thực thi trong build được mô tả bằng **execution**.

Có hai nơi phổ biến để đặt tham số của một build plugin trong `pom.xml`:

1. **Cấu hình chung ở cấp plugin**: phần `<configuration>` trực tiếp dưới `<plugin>`. Những tham số này thường là giá trị mặc định dùng chung cho các lần gọi goal của plugin đó.
2. **Cấu hình riêng ở cấp execution**: phần `<configuration>` bên trong `<executions><execution>`. Những tham số này áp dụng cho execution tương ứng, có thể bổ sung hoặc ghi đè các tham số chung.

Với một plugin có nhiều executions, cách cấu hình có thể diễn đạt ngắn:

> **Cái gì giống nhau cho mọi lần chạy thì để ở cấp plugin; cái gì chỉ khác ở một lần chạy thì đặt trong execution đó.**

Ví dụ một dự án tạo hai JAR ở phase `package`: JAR thông thường và JAR có classifier `audit`. Cả hai cần chung metadata của bản build, nhưng entry point (`Main-Class`) của JAR audit sẽ khác. Không cần lặp toàn bộ cấu hình ở cả hai executions.

```text
pom.xml
  |
  +-- build/plugins/plugin: maven-jar-plugin
        |
        +-- configuration (CHUNG)
        |     archive/manifest/Main-Class = dev.learn.App
        |     archive/manifestEntries/Built-For = Learning
        |
        +-- default-jar (execution có sẵn của packaging=jar)
        |     dùng cấu hình chung
        |     => plugin-execution-demo-1.0.0-SNAPSHOT.jar
        |
        +-- audit-jar (execution do POM khai báo)
              phase = package
              goal = jar
              configuration (RIÊNG)
                classifier = audit
                archive/manifest/Main-Class = dev.learn.AuditApp
                archive/manifestEntries/Build-Variant = audit
              => plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
```

Sơ đồ nêu **cách cấu hình được áp dụng và bổ sung**, không phải mặc định mọi plugin đều tạo hai artifact. Để có JAR thứ hai, bài thực hành sẽ khai báo execution mới cho JAR Plugin và một classifier rõ ràng.

Kết thúc bài này, bạn phải phân biệt được **plugin**, **goal**, **execution**, **phase**, **configuration**, **pluginManagement** và **cách chạy goal từ CLI**, đồng thời biết tìm lý do vì sao một tham số có hiệu lực ở execution này nhưng không ở execution khác.

## 2. Đọc đúng cấu trúc XML trong pom.xml

Mẫu cấu hình tối giản:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>

            <!-- Cấu hình chung cho các lần chạy phù hợp -->
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>dev.learn.App</mainClass>
                    </manifest>
                </archive>
            </configuration>

            <executions>
                <execution>
                    <id>audit-jar</id>
                    <phase>package</phase>
                    <goals>
                        <goal>jar</goal>
                    </goals>
                    <configuration>
                        <classifier>audit</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

**Đây chỉ là đoạn `<build>`**, không phải tệp POM hoàn chỉnh. Đặt nó cùng cấp với các thành phần dự án như `<dependencies>` dưới `<project>`.

Ý nghĩa các thẻ:

| Thẻ | Nơi đặt | Vai trò |
| --- | --- | --- |
| `<plugin>` | `build/plugins` | Chọn plugin bằng groupId, artifactId và version |
| `<configuration>` trực tiếp của plugin | `plugin/configuration` | Tham số dùng chung cho các lời gọi/goal tương ứng |
| `<executions>` | `plugin/executions` | Danh sách những executions được định nghĩa |
| `<execution>` | `executions/execution` | Một lịch/kiểu chạy goal, có ID và cấu hình riêng |
| `<id>` | `execution/id` | Nhận diện execution, quan trọng khi merge và debug |
| `<phase>` | `execution/phase` | Phase lifecycle gắn với execution |
| `<goals>` | `execution/goals` | Goal/nhóm goal chạy trong execution |
| `<configuration>` trong execution | `execution/configuration` | Cấu hình áp dụng riêng cho execution đó |
| `<version>` của plugin | `plugin/version` | Chọn phiên bản code của plugin, **khác** version của dependency ứng dụng |

Lưu ý tên thẻ `configuration` giống nhau nhưng **vị trí khác nhau làm thay đổi phạm vi**. Nếu một thẻ bị đặt nhầm ở `<execution>` hoặc ngoài `<plugin>`, Maven không có cùng cách diễn giải như cấu trúc đúng.

## 3. Plugin-level configuration: giá trị chung

Với một plugin, đặt `<configuration>` trực tiếp dưới `<plugin>` giúp tất cả lời gọi tương ứng của plugin có thể nhận các tham số mặc định giống nhau.

Ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>dev.learn.App</mainClass>
            </manifest>
            <manifestEntries>
                <Built-For>Learning</Built-For>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
```

Các thuộc tính dưới `archive` là tham số hợp lệ của goal `jar:jar` thông qua Maven Archiver. Cụ thể:

- `mainClass` là giá trị dùng để tạo manifest entry `Main-Class`; nó cho phép `java -jar` xác định lớp có phương thức `main`.
- `Built-For` là một manifest entry tùy biến do dự án đặt để minh họa cách chia sẻ metadata.
- Cả hai được dùng cho goal `jar:jar` nếu không bị cấu hình riêng ghi đè.

**Không phải mọi goal đều có cùng bộ tham số.** Một Maven plugin có thể chứa nhiều goals, nhưng một phần tử trong `<configuration>` chỉ có tác dụng nếu goal đang chạy có tham số tương ứng. Đừng cho rằng cấu hình chung được áp dụng máy móc cho mọi goal bất kể loại và tính hợp lệ của tham số.

Những giá trị thông dụng nên cân nhắc đưa vào plugin-level:

- Encoding hoặc đường dẫn dùng như nhau cho các executions liên quan.
- Quy tắc xử lý output giống nhau, miễn plugin hỗ trợ.
- Thông số bảo đảm tính ổn định của build mà toàn bộ các executions phải dùng.
- Một phần cấu hình cấu trúc chung và chỉ ghi đè đúng phần khác biệt ở execution cụ thể.

Nhưng nếu hai executions thực sự cần cấu hình khác hẳn nhau, có thể tách rõ cấu hình vào từng execution để tránh hiểu nhầm do cơ chế merge của XML.

## 4. Execution-level configuration: áp dụng cho một execution

Một execution có thể gắn một goal vào phase cụ thể, dùng ID để định danh và đưa cấu hình riêng cho lần chạy đó.

```xml
<executions>
    <execution>
        <id>audit-jar</id>
        <phase>package</phase>
        <goals>
            <goal>jar</goal>
        </goals>
        <configuration>
            <classifier>audit</classifier>
            <archive>
                <manifest>
                    <mainClass>dev.learn.AuditApp</mainClass>
                </manifest>
                <manifestEntries>
                    <Build-Variant>audit</Build-Variant>
                </manifestEntries>
            </archive>
        </configuration>
    </execution>
</executions>
```

**Đây là đoạn `<executions>` bên trong một plugin JAR đã khai báo**, không phải một POM hoàn chỉnh. Phần này sẽ được tích hợp vào ví dụ đầy đủ ở mục 8.

Đọc từng phần:

1. `id=audit-jar`: đặt tên dễ nhận diện; không phải tên file JAR và cũng không phải classifier.
2. `phase=package`: khi lifecycle chạy đến `package`, execution này được xét để chạy.
3. `goals/goal=jar`: chọn goal `jar:jar`.
4. `classifier=audit`: tạo artifact bổ sung có classifier thay vì cố thay JAR chính.
5. `mainClass=dev.learn.AuditApp`: thay **chỉ giá trị entry point** cho execution audit.
6. `Build-Variant=audit`: thêm metadata riêng của JAR audit.

Cấu hình plugin-level vẫn có giá trị ở những tham số không bị phần execution ghi đè theo cấu trúc merge. Ví dụ JAR audit có thể giữ `Built-For: Learning` đồng thời thêm `Build-Variant: audit`.

**Cảnh báo:** nếu bạn chỉ đặt `<configuration>` dưới `<execution>` nhưng không có cách để execution được gọi, cấu hình đó có thể **không bao giờ được sử dụng**. Cần hiểu phase/goal hoặc cơ chế gọi trực tiếp theo execution ID.

## 5. Mối quan hệ giữa phase, goal và execution

Maven xây dựng dự án theo các lifecycle phase (ví dụ):

```text
validate -> compile -> test -> package -> verify -> install -> deploy
```

Chuỗi trên chỉ liệt kê các phase chính; default lifecycle còn nhiều phase trung gian. Khi chạy `mvn package`, Maven xét những goals được gắn vào các phase từ đầu lifecycle đến `package`, bao gồm những execution mặc định của packaging và các execution bổ sung được cấu hình.

- **Goal:** tác vụ cụ thể của plugin, ví dụ `jar:jar`, `compiler:compile`.
- **Execution:** một lượt gọi goal hoặc nhóm goals trong ngữ cảnh cấu hình cụ thể; có thể gắn với phase.
- **Phase:** điểm trong lifecycle nơi Maven thực thi các goals đã gắn.
- **Plugin:** tập hợp một hoặc nhiều goals.

Một plugin có thể chạy nhiều lần:

```text
maven-jar-plugin
  ├── default-jar : jar:jar @ package  -> JAR chính
  └── audit-jar   : jar:jar @ package  -> JAR classifier audit
```

Cùng một goal nhưng **hai executions và hai kết quả cấu hình khác nhau**. Khi output có classifier khác, Maven có thể gắn artifact bổ sung với dự án.

Không phải mọi execution đều bắt buộc khai báo `<phase>`: một số goal có default phase đã được định nghĩa trong plugin descriptor. Nếu không có phase tường minh và goal không có default phase, execution có thể không được chạy trong lifecycle. Với bài học cần rõ ràng, execution audit ghi `<phase>package</phase>`.

### 5.1. Thứ tự nhiều executions

Khi nhiều executions được gắn vào cùng phase, chúng sẽ được thực thi theo thứ tự mà Maven xây dựng execution plan; thứ tự thường phụ thuộc default mapping, thứ tự khai báo plugin/execution và kế thừa POM. Tránh dựa vào thứ tự tình cờ nếu hai goal cùng ghi vào một tệp hoặc phụ thuộc đầu ra của nhau.

Trong ví dụ này JAR chính được tạo bởi default lifecycle mapping cho packaging `jar`, còn execution `audit-jar` được bổ sung vào phase `package`. Mỗi lượt tạo tên artifact khác nhau, nên không ghi đè cùng file.

## 6. Cấu hình được ghép như thế nào?

Không nên hiểu execution-level `<configuration>` là “thay thế hoàn toàn mọi thẻ” từ plugin-level. Maven thường **ghép các phần tử XML theo tên và vị trí**. Giá trị cụ thể ở phạm vi riêng có thể thắng ở nút trùng, trong khi các nút không trùng vẫn được giữ lại.

Ví dụ khái niệm của JAR Plugin:

**Cấp plugin**:

```xml
<configuration>
    <archive>
        <manifest>
            <mainClass>dev.learn.App</mainClass>
        </manifest>
        <manifestEntries>
            <Built-For>Learning</Built-For>
        </manifestEntries>
    </archive>
</configuration>
```

**Cấp execution audit**:

```xml
<configuration>
    <classifier>audit</classifier>
    <archive>
        <manifest>
            <mainClass>dev.learn.AuditApp</mainClass>
        </manifest>
        <manifestEntries>
            <Build-Variant>audit</Build-Variant>
        </manifestEntries>
    </archive>
</configuration>
```

Hiệu lực mong đợi cho execution audit, viết ở dạng **mô hình minh họa**:

```xml
<configuration>
    <classifier>audit</classifier>
    <archive>
        <manifest>
            <mainClass>dev.learn.AuditApp</mainClass>
        </manifest>
        <manifestEntries>
            <Built-For>Learning</Built-For>
            <Build-Variant>audit</Build-Variant>
        </manifestEntries>
    </archive>
</configuration>
```

Đây không phải XML được copy riêng vào POM; nó mô tả hiệu lực của phần cấu hình ghép. Nút `mainClass` bị ghi đè cho execution audit, còn `Built-For` vẫn được kế thừa và `Build-Variant` được thêm.

**Chú ý với danh sách và cấu trúc phức tạp:** cách Maven ghép collections, các phần tử lặp và cấu hình kế thừa có thể khác với trực giác “tất cả được cộng vào nhau”. Trong những tình huống nâng cao, Maven model có các thuộc tính hỗ trợ merge như `combine.self="override"` hoặc `combine.children="append"` ở các ngữ cảnh thích hợp. Không dùng chúng như cách chữa lỗi mặc định: trước hết cần hiểu chính xác XML nào Maven tạo cho execution và plugin goal sẽ diễn giải nó ra sao.

**Cách kiểm chứng chuẩn** là xem `mvn help:effective-pom` và, quan trọng hơn, **quan sát đầu ra của goal** (trong bài là hai tệp JAR và manifest của chúng). Effective POM mô tả mô hình tổng hợp, nhưng một số tham số hoặc property chỉ được plugin đánh giá lúc goal chạy.

## 7. Quy tắc ưu tiên và những giới hạn cần nhớ

Thường có nhiều tầng:

```text
POM cha / pluginManagement / profiles (nếu có)
                 |
          POM hiệu lực
                 |
        build/plugins/plugin
                 |
        configuration chung
                 |
        execution cụ thể
                 |
      tham số plugin goal thực thi
```

Có thể hiểu khi xây dựng cấu hình cho một goal:

- Cấu hình cấp plugin là giá trị chung cho những lần gọi tương ứng.
- Cấu hình của một execution có thể thêm hoặc ghi đè các nút tương ứng của cấu hình chung.
- Cấu hình được kế thừa từ parent hoặc profile có thể tham gia merge, với luật ưu tiên phụ thuộc mô hình Maven.
- Tham số mặc định của chính plugin goal được dùng nếu không có cấu hình phù hợp.
- Giá trị `-Dkey=value` chỉ ảnh hưởng khi Maven/plugin hỗ trợ property đó; không có quy tắc tổng quát rằng mọi `-D` đều ghi đè cấu hình XML viết cứng.

**Không có một phép gán duy nhất “execution luôn thắng tất cả”** trong mọi trường hợp. Một execution không thể tùy ý đổi identity của project, không thể thêm dependency project chỉ bằng một property vô danh, và không thể dùng tham số không tồn tại trong goal đang chạy.

Để tra cứu tên tham số thật, xem tài liệu goal hoặc dùng Maven Help Plugin:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-jar-plugin -Dgoal=jar -Ddetail
```

Tài liệu goal cho biết mô tả, kiểu dữ liệu, giá trị mặc định và **User Property** nếu có. Tên XML parameter không luôn giống tên CLI property.

## 8. Ví dụ hoàn chỉnh có thể chạy: tạo hai JAR bằng một plugin

Để thấy trực tiếp cấu hình chung và cấu hình riêng khác nhau, ta tạo dự án **Java 17**, Maven 3.9.x tương thích và JUnit Jupiter 5.

### 8.1. Cấu trúc thư mục

```text
plugin-execution-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/learn/
    │       ├── App.java
    │       ├── AuditApp.java
    │       └── ManifestInspector.java
    └── test/
        └── java/dev/learn/
            └── EntryPointTest.java
```

Trong bài này, hai JAR đều chứa các lớp chính từ cùng một nguồn. **Khác biệt nằm ở manifest (Main-Class và metadata) và classifier**, không phải mỗi JAR tự có một bộ source code riêng.

### 8.2. POM hoàn chỉnh

Tạo `plugin-execution-demo/pom.xml` với nội dung:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learn</groupId>
    <artifactId>plugin-execution-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <!-- Cung mot plugin, hai cach dong goi -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>

                <!-- Ap dung chung cho ca JAR chinh va audit -->
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.learn.App</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Built-For>Learning</Built-For>
                        </manifestEntries>
                    </archive>
                </configuration>

                <executions>
                    <execution>
                        <id>audit-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>

                        <!-- Chi ap dung cho audit-jar -->
                        <configuration>
                            <classifier>audit</classifier>
                            <archive>
                                <manifest>
                                    <mainClass>dev.learn.AuditApp</mainClass>
                                </manifest>
                                <manifestEntries>
                                    <Build-Variant>audit</Build-Variant>
                                </manifestEntries>
                            </archive>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM **độc lập**, không cần POM cha riêng và không có plugin được giả định từ một bài khác. Maven cần truy cập repository phù hợp để tải plugin và JUnit trong lần build đầu nếu local repository chưa có sẵn.

Phân tích những vị trí quan trọng:

- `maven-compiler-plugin` phiên bản được ghim; `maven.compiler.release=17` chọn Java release cho compile.
- `maven-surefire-plugin` chạy các test JUnit Jupiter theo cấu hình POM và lifecycle.
- `maven-jar-plugin` đã được khai báo với version cụ thể.
- **Cấu hình chung của JAR Plugin** đặt `Main-Class=dev.learn.App` và `Built-For=Learning`.
- **Execution audit** đặt `classifier=audit` và đổi `Main-Class=dev.learn.AuditApp`; manifest entry `Built-For` chung vẫn được dùng.
- Với `<packaging>jar</packaging>`, Maven đã có execution mặc định để tạo JAR chính. Execution `audit-jar` **bổ sung** một lượt chạy goal `jar:jar`, không phải thay execution mặc định.

### 8.3. Mã Java cho JAR thông thường

Tạo `src/main/java/dev/learn/App.java`:

```java
package dev.learn;

public final class App {
    private App() {
    }

    public static String message() {
        return "APP: main";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Tạo `src/main/java/dev/learn/AuditApp.java`:

```java
package dev.learn;

public final class AuditApp {
    private AuditApp() {
    }

    public static String message() {
        return "APP: audit";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Hai lớp đều có phương thức `public static void main(String[] args)` hợp lệ. Maven Jar Plugin chọn một trong hai làm điểm vào dựa trên manifest của từng JAR, **không dựa trên việc lớp nào được khai báo trước trong thư mục source**.

### 8.4. Java đọc manifest để kiểm chứng tham số plugin

Tạo `src/main/java/dev/learn/ManifestInspector.java`:

```java
package dev.learn;

import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ManifestInspector {
    private ManifestInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Cần đúng một đường dẫn JAR");
        }

        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("JAR không có manifest");
            }

            Attributes main = manifest.getMainAttributes();
            String variant = main.getValue("Build-Variant");

            System.out.println("Main-Class="
                    + main.getValue(Attributes.Name.MAIN_CLASS));
            System.out.println("Built-For="
                    + main.getValue("Built-For"));
            System.out.println("Build-Variant="
                    + (variant == null ? "(none)" : variant));
        }
    }
}
```

Đây là mã Java 17 chạy độc lập bằng JDK, không dùng thư viện ngoài. `JarFile` đọc trực tiếp metadata trong tệp JAR, vì vậy nó cho biết **đầu ra thực tế** của execution chứ không chỉ suy đoán từ POM.

### 8.5. Unit test dùng JUnit 5

Tạo `src/test/java/dev/learn/EntryPointTest.java`:

```java
package dev.learn;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EntryPointTest {
    @Test
    void mainEntryPointMessage() {
        assertEquals("APP: main", App.message());
    }

    @Test
    void auditEntryPointMessage() {
        assertEquals("APP: audit", AuditApp.message());
    }
}
```

Hai test kiểm tra phương thức thực tế của hai entry points. Chúng không phụ thuộc vào mạng, thời gian hoặc file JAR, giúp tách riêng việc **mã Java đúng** với việc **cấu hình plugin đóng gói đúng**.

### 8.6. Build một lần và quan sát hai artifact

Từ thư mục `plugin-execution-demo`, dùng Maven 3.9.x (hoặc bản tương thích) và JDK 17+:

```bash
mvn -version
mvn clean package
```

Nếu plugins/dependencies có thể phân giải và mã nguồn đúng, Maven biên dịch, chạy **2 tests** thành công, rồi tạo hai JAR:

```text
target/plugin-execution-demo-1.0.0-SNAPSHOT.jar
target/plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
```

**Vì sao có hai tệp?** Default lifecycle mapping của packaging `jar` tạo JAR chính, và execution `audit-jar` có goal `jar:jar` ở phase `package` với classifier `audit` nên tạo thêm artifact được đính kèm.

Maven sẽ báo `BUILD SUCCESS` khi quá trình package hoàn tất. Tên file theo `artifactId`, `version` và `classifier` do Jar Plugin áp dụng trong cấu hình mặc định của bài. Nếu thay `finalName`, `outputDirectory` hoặc plugin settings, tên/đường dẫn có thể khác.

### 8.7. Kiểm chứng hành vi lúc chạy

Chạy JAR chính:

```bash
java -jar target/plugin-execution-demo-1.0.0-SNAPSHOT.jar
```

**Stdout chính xác**:

```text
APP: main
```

Chạy JAR audit:

```bash
java -jar target/plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
```

**Stdout chính xác**:

```text
APP: audit
```

Ở đây không cần thêm dependency ngoài JDK khi chạy, vì hai entry points chỉ dùng API Java chuẩn. Nếu ứng dụng thật có thêm thư viện, cấu hình Main-Class không tự tạo fat JAR hoặc cung cấp runtime classpath cho các thư viện đó.

### 8.8. Kiểm chứng giá trị chung và giá trị riêng trong manifest

Không cần giải nén bằng tay: từ thư mục dự án đã build, chạy lớp kiểm tra manifest:

```bash
java -cp target/classes dev.learn.ManifestInspector target/plugin-execution-demo-1.0.0-SNAPSHOT.jar
```

**Đầu ra mong đợi**:

```text
Main-Class=dev.learn.App
Built-For=Learning
Build-Variant=(none)
```

Đối với artifact audit:

```bash
java -cp target/classes dev.learn.ManifestInspector target/plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
```

**Đầu ra mong đợi**:

```text
Main-Class=dev.learn.AuditApp
Built-For=Learning
Build-Variant=audit
```

Điều này kiểm chứng **ba quan sát khác nhau**:

1. Tham số plugin-level `Built-For=Learning` có trong **cả hai JAR**.
2. Tham số `mainClass` bị **ghi đè chỉ ở execution audit**.
3. Tham số riêng `Build-Variant=audit` chỉ xuất hiện ở JAR audit, trong khi JAR chính không có entry đó.

Bạn cũng có thể dùng:

```bash
jar tf target/plugin-execution-demo-1.0.0-SNAPSHOT.jar
jar tf target/plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
```

Cả hai JAR trong ví dụ thường chứa `dev/learn/App.class`, `dev/learn/AuditApp.class` và `dev/learn/ManifestInspector.class`, vì ta **không cấu hình lọc classes** cho execution audit. Classifier/manifest không tự tách mã nguồn thành hai nhóm khác nhau.

### 8.9. Trên Windows PowerShell

Không có yêu cầu shell Unix đặc biệt:

```powershell
mvn -version
mvn clean package
java -jar target/plugin-execution-demo-1.0.0-SNAPSHOT.jar
java -jar target/plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
java -cp target/classes dev.learn.ManifestInspector target/plugin-execution-demo-1.0.0-SNAPSHOT-audit.jar
```

Nếu Maven Wrapper đã được dự án cung cấp, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `mvnw.cmd` trên Windows. Bài ví dụ không cung cấp sẵn wrapper nên không yêu cầu người học phải chạy lệnh wrapper.

## 9. Execution mặc định: default-jar, default-compile và default-cli

Một số executions không được viết tường minh trong POM nhưng tồn tại do **default lifecycle mapping** của packaging.

Ví dụ với `<packaging>jar</packaging>`:

- Compiler Plugin có các executions mặc định gắn vào compile/test-compile theo lifecycle.
- Surefire Plugin thường được gọi ở phase `test`.
- Jar Plugin được gắn ở `package` với execution ID dạng **`default-jar`**.
- Khi người dùng gọi goal trực tiếp bằng CLI, Maven thường dùng execution ID **`default-cli`** cho lần gọi đó.

Nếu muốn cấu hình **riêng chính default JAR** mà không thay tất cả lời gọi `jar:jar`, bạn có thể nhắm ID `default-jar`.

Ví dụ **đoạn minh họa không dùng đồng thời với phần POM thực hành nếu chưa hiểu ý đồ**:

```xml
<executions>
    <execution>
        <id>default-jar</id>
        <configuration>
            <archive>
                <manifest>
                    <mainClass>dev.learn.App</mainClass>
                </manifest>
            </archive>
        </configuration>
    </execution>
</executions>
```

Execution có ID `default-jar` giúp bạn tác động lên execution mặc định tương ứng; không tạo thêm một execution `jar:jar` hoàn toàn độc lập như `audit-jar` trong ví dụ. **Không tự thêm `<goals><goal>jar</goal></goals>` lặp lại vào ID mặc định chỉ để có JAR chính**, nếu không biết cách nó ghép với lifecycle hiện tại.

### Gọi goal trực tiếp khác với chạy lifecycle

So sánh:

```bash
mvn clean package
mvn jar:jar
```

- `mvn clean package` chạy lifecycle cho đến `package`, bao gồm compile/test và execution mặc định, cùng executions bổ sung.
- `mvn jar:jar` gọi trực tiếp một plugin goal; **không đảm bảo trong chính lệnh ấy đã biên dịch/test mã nguồn**. Nếu không có `target/classes`, output có thể rỗng hoặc không đúng mong đợi.

Một lệnh gọi trực tiếp không tự chọn `audit-jar` chỉ vì ID đó tồn tại. Maven 3.3.1+ có cú pháp chọn execution đã khai báo theo ID:

```bash
mvn jar:jar@audit-jar
```

Lệnh này chỉ mang ý nghĩa khi execution `audit-jar` đã được khai báo trong POM và đầu vào plugin phù hợp tồn tại. Không dùng nó thay cho `mvn clean package` trong luồng build thông thường.

Để cho lời gọi CLI có cấu hình riêng, có thể khai báo một execution với ID `default-cli`; đó là trường hợp nâng cao khi cùng một goal cần cấu hình khác giữa build lifecycle và lệnh chạy thủ công. Nhưng với nhu cầu thông dụng, đặt giá trị chung ở plugin-level và giá trị khác biệt ở execution-level thường dễ bảo trì hơn.

## 10. Plugin-level khác với pluginManagement như thế nào?

Hai nơi này cũng dễ nhầm:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.learn.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là **đoạn POM dành cho việc quản lý plugin**, không phải POM hoàn chỉnh. Nó có thể định nghĩa version/configuration/executions được quản lý để những plugins liên quan dùng khi được kích hoạt hoặc đưa vào lifecycle.

Cần phân biệt:

| Nơi khai báo | Tác dụng điển hình |
| --- | --- |
| `build/plugins/plugin` | Khai báo plugin được dùng trong build; có thể khai báo executions/goal bindings |
| `build/plugins/plugin/configuration` | Cấu hình chung của plugin đang được dùng |
| `build/plugins/plugin/executions/execution/configuration` | Cấu hình cho đúng execution |
| `build/pluginManagement/plugins/plugin` | Cung cấp version/configuration/executions được quản lý; tự nó **không phải lệnh bắt Maven chạy một goal mới** |
| `reporting/plugins/plugin` | Cấu hình reporting plugin, phục vụ site/reporting thay vì execution build thông thường |

Chỉ thêm plugin vào `pluginManagement` **không tự tạo một execution bổ sung**. Nhưng một plugin đã được default lifecycle mapping sử dụng, hoặc được `build/plugins` khai báo phù hợp, có thể nhận cấu hình/version được quản lý từ pluginManagement.

Trong POM con kế thừa parent, `pluginManagement` thường là nơi hợp lý để ghim plugin versions và giá trị chuẩn chung, còn module con bật plugin hoặc thêm execution cần thiết theo nhu cầu.

## 11. Kế thừa từ parent và profile: execution ID quan trọng

Maven có cơ chế **inheritance và merge** cho plugin configuration:

- Plugin cấu hình ở parent có thể được kế thừa vào POM con theo luật Maven.
- Các executions cùng plugin nhưng **ID khác nhau** thường cùng tồn tại sau khi merge và có thể đều được chạy.
- Executions có **cùng ID** ở parent và child được ghép/override theo mô hình kế thừa; child có thể tùy chỉnh phần được kế thừa.
- `<inherited>false</inherited>` ở những nơi được Maven hỗ trợ có thể kiểm soát việc một plugin/execution được truyền xuống các POM con.

Ví dụ **hai đoạn riêng biệt**, không phải hai phần của cùng một POM:

Parent POM định nghĩa:

```xml
<execution>
    <id>generate-report</id>
    <phase>verify</phase>
    <goals>
        <goal>some-goal</goal>
    </goals>
</execution>
```

Child POM định nghĩa cùng plugin với execution có ID `generate-report` nhưng thay `<configuration>`. Khi model được hợp nhất, chúng không nhất thiết trở thành hai lượt chạy độc lập; Maven căn cứ ID để nhận diện execution tương ứng.

**`some-goal` ở trên là tên goal giả định để giải thích cấu trúc**, không phải một goal thật của JAR Plugin hay một ví dụ chạy được. Đừng copy đoạn này nguyên vào POM thực hành.

Không nên đặt ID giống nhau cho hai executions **trong cùng một plugin và cùng POM**. Đặt ID có nghĩa: `generate-api`, `run-unit-tests`, `create-audit-jar` thay vì `first`, `second`; điều này giúp đọc build log và tìm execution hiệu lực.

Profiles trong POM có thể thêm hoặc điều chỉnh plugin configuration/executions khi active. Vì thế nếu build local và CI khác nhau, hãy kiểm tra **profile thực sự đang active**, không chỉ đọc phần `build/plugins` ở POM gốc.

## 12. Có thể đặt configuration ở mọi plugin goal không?

**Không hoàn toàn.** Maven map các phần tử trong `configuration` tới tham số mà plugin goal hỗ trợ. Nếu một goal không có parameter `outputDirectory` hoặc `archive` như bạn dự đoán, việc đặt thẻ XML cùng tên không bảo đảm goal sẽ làm theo.

Để tìm thông tin đáng tin:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-jar-plugin -Dgoal=jar -Ddetail
mvn help:effective-pom
mvn help:active-profiles
```

Giải thích:

- `help:describe`: tìm goal, các tham số, default value và tên user property hỗ trợ.
- `help:effective-pom`: xem cấu hình sau khi Maven ghép parent và profiles.
- `help:active-profiles`: xác nhận profile nào đang tham gia model.

Khi cần xem execution nào được gọi và tham số cuối cùng:

```bash
mvn -X clean package
```

Log debug có thể hiển thị plugin execution ID, parameters và dấu vết tạo artifact. Nhưng log `-X` rất dài; có thể chứa đường dẫn nội bộ hoặc thông tin môi trường nhạy cảm. Không chia sẻ nguyên log công khai nếu chưa kiểm tra.

**Không sửa trực tiếp tệp POM chỉ dựa vào một đoạn trong log** khi kết quả được giải thích bởi default lifecycle execution hoặc một profile/parent đang active.

## 13. Vì sao cấu hình cấp execution không tác động tới lời gọi CLI?

Lỗi hay gặp:

1. Người học đặt tham số quan trọng **chỉ** trong `execution id=report`.
2. Sau đó chạy `mvn plugin:goal` từ terminal.
3. Kết quả không dùng các giá trị trong `report`, vì lời gọi trực tiếp thường không chọn execution ấy.

Trong Maven, **một lệnh gọi trực tiếp goal** không mặc định đồng nghĩa với **một execution đã gắn lifecycle**. Nếu cần chạy theo cấu hình của execution được đặt tên, dùng cú pháp `plugin:goal@execution-id` ở phiên bản Maven hỗ trợ; nếu cần giá trị chung cả CLI và lifecycle, cân nhắc đưa lên plugin-level.

Ví dụ:

```bash
mvn jar:jar@audit-jar
```

Chỉ gọi thử sau khi có đầu ra classes, và lưu ý việc chạy riêng goal `jar:jar` không tự kiểm thử. Bài học khuyến nghị `mvn clean package` để tạo cả hai JAR một cách nhất quán.

Một số plugins còn cung cấp user properties qua `-D`, nhưng **tên property không nhất thiết bằng tên tham số XML**. Nếu POM viết cứng một giá trị XML, việc đặt `-DsomeName=...` không bảo đảm override nó. Tra tài liệu plugin goal và xác nhận kết quả thực tế.

## 14. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Tham số chung chỉ xuất hiện ở JAR chính | Execution ghi đè cả một phần XML hoặc merge không như dự đoán | Xem hiệu lực XML và manifest từng JAR; tránh copy cấu hình một cách thiếu kiểm soát |
| Tham số riêng bị áp dụng cho mọi execution | Đặt nhầm `<configuration>` ở plugin-level | Chuyển tham số riêng vào `execution/configuration` |
| Goal không chạy khi `mvn verify` | Execution thiếu phase/goal phù hợp hoặc plugin không được bật | Xem `<phase>`, `<goals>`, goal default phase và build log |
| `mvn package` chỉ tạo một JAR | Chưa có execution `audit-jar` hoặc classifier/execution bị khai báo sai | Kiểm tra execution ID, phase package, goal jar, classifier |
| `You have to use a classifier ...` khi tạo JAR thứ hai | Gọi goal `jar:jar` lần nữa mà không có classifier | Đặt `<classifier>audit</classifier>` cho execution bổ sung |
| JAR không có `Main-Class` | Cấu hình manifest thiếu hoặc không có hiệu lực với execution | Kiểm tra POM, manifest thật và Jar Plugin goal |
| Chạy JAR audit nhưng in `APP: main` | Execution audit chưa ghi đè `mainClass` hoặc đang chạy nhầm JAR | Kiểm tra tên file, `Main-Class` và ID execution |
| JAR chính có `Build-Variant=audit` | Đặt metadata audit nhầm ở plugin-level | Đưa metadata chỉ dành audit xuống execution |
| Gọi `mvn jar:jar` không dùng cấu hình audit | Lời gọi CLI dùng execution mặc định `default-cli` | Chạy lifecycle, hoặc chọn `@audit-jar` khi phù hợp |
| Cấu hình ở `pluginManagement` không tự tạo artifact bổ sung | Quản lý plugin không tự thêm execution mới vào build | Khai báo plugin/execution trong `build/plugins` phù hợp |
| Cấu hình giữa local và CI khác | Profile, parent POM hoặc user property khác | Xem `help:effective-pom`, `help:active-profiles` |
| Dự án compile được nhưng `java -jar` báo thiếu thư viện | JAR chính không tự gộp dependencies | Xây runtime classpath hoặc packaging riêng; không nhầm với lỗi execution |
| Hai executions ghi cùng tệp output | Thiếu classifier hoặc outputDirectory khác nhau không rõ chủ đích | Thiết kế tên artifact/output an toàn, tránh ghi đè |
| Parent thay đổi và build con chạy thêm goal | Execution ID khác nhau được merge/kế thừa | Kiểm tra ID, `inherited` và execution plan |
| Tùy chọn `-D` không có tác dụng | Plugin goal không hỗ trợ property hoặc XML đã đặt giá trị cố định | Tra User Property của goal, kiểm chứng output |

**Chẩn đoán có chứng cứ:** xác nhận Maven/JDK, effective POM, execution ID trong log và artifact thật. Chỉ việc Maven in `BUILD SUCCESS` không chứng minh hai artifact có manifest đúng nếu bạn chưa đọc đầu ra.

## 15. Quy tắc thiết kế dễ bảo trì

Một nhóm phát triển có thể dùng những quy tắc sau:

1. **Ghim version plugin** trong POM hoặc parent/pluginManagement để giảm thay đổi ngoài ý muốn.
2. Đặt các giá trị dùng chung thật sự ở **plugin-level**.
3. Đặt thông số chỉ dành cho một lần chạy ở **execution-level**, với `id` rõ ràng.
4. Đặt `phase` và `goals` tường minh khi việc binding chưa hiển nhiên.
5. Không tạo lại một execution mà default lifecycle đã cung cấp nếu chỉ cần cấu hình nó; dùng ID mặc định thích hợp nếu cần điều chỉnh riêng.
6. Nếu một execution tạo **artifact bổ sung**, dùng classifier hoặc cách xuất bản hợp lệ để không ghi đè artifact chính.
7. Nếu cấu hình có nhiều lớp XML phức tạp, hãy xác nhận cách merge bằng output hoặc plugin log; đừng đoán mọi danh sách đều append.
8. Tách **dependencies của ứng dụng** khỏi **dependencies/configuration của build plugin**.
9. Khi cấu hình thay đổi theo môi trường, ưu tiên một POM dễ tái lập và dùng profiles/properties có chủ đích.
10. Viết kiểm thử hoặc bước kiểm chứng artifact cuối cùng nếu manifest, classifier hay nội dung gói có ý nghĩa đối với downstream consumers.

Với pipeline phát hành, không nên bỏ test và ép build chỉ để thấy hai file JAR. Kết quả đóng gói phải được kiểm tra trên đúng source, đúng plugin versions và đúng điều kiện runtime.

## 16. Bài tập thực hành và tự kiểm tra

1. Trong ví dụ `maven-jar-plugin`, hãy chỉ ra chính xác đâu là **plugin-level configuration** và đâu là **execution-level configuration**. Phần nào chứa `Built-For`? Phần nào chứa `classifier`?
2. Chạy `mvn clean package`. Giải thích vì sao Maven tạo JAR chính và JAR audit; tên classifier lấy từ đâu?
3. Dùng `ManifestInspector` kiểm tra hai JAR. Vì sao cả hai có `Built-For=Learning` nhưng chỉ JAR audit có `Build-Variant=audit`?
4. Chạy hai lệnh `java -jar ...`. Vì sao stdout lần một là `APP: main`, lần hai là `APP: audit` dù cùng source tree?
5. Thử đổi `Main-Class` chung thành `dev.learn.AuditApp` và quan sát JAR chính. JAR audit có tiếp tục dùng entry point riêng không?
6. Xóa riêng thẻ `<classifier>audit</classifier>` khỏi execution audit **trên một nhánh thử nghiệm**, chạy `mvn clean package` và giải thích lỗi nếu plugin cố tạo hai artifact chính. Khôi phục POM sau thí nghiệm.
7. So sánh `mvn clean package` với `mvn jar:jar`. Tại sao lệnh sau không đảm bảo compile/test?
8. Tìm execution ID mặc định khi Maven dùng Jar Plugin với packaging `jar`. Nếu muốn thay cấu hình chỉ của execution mặc định, bạn sẽ dùng ID nào?
9. Một parent POM có execution ID `generate-report` và child cũng khai báo execution cùng ID. Bạn kiểm tra merge/override bằng công cụ nào?
10. Nếu plugin có hai executions khác ID nhưng đều gắn vào `verify`, Maven có thể thực thi cả hai không? Tại sao?
11. Phân biệt `build/plugins` với `build/pluginManagement`. Vì sao khai báo plugin chỉ trong pluginManagement thường không tự tạo một execution mới?
12. Nếu một tham số đặt trong XML plugin không có tác dụng, bạn tra cứu **goal parameter** và **User Property** bằng lệnh nào?
13. Tự chọn một plugin khác (Resources/Compiler/Surefire) và mô tả một tình huống có hai executions cần khác cấu hình. Chỉ rõ giá trị chung và giá trị riêng, tránh bịa tên tham số không có trong tài liệu goal.
14. Cấu hình nào giúp cho lệnh CLI trực tiếp dùng riêng execution có ID `audit-jar` thay vì chỉ dùng `default-cli`?
15. Giải thích vì sao tạo một classifier JAR không tự đồng nghĩa tạo fat JAR, và khi nào cần quản lý runtime dependencies riêng.

## 17. Tổng kết

**Plugin-level `<configuration>`** giữ những giá trị dùng chung, còn **execution-level `<configuration>`** điều chỉnh riêng một lượt chạy goal. Maven tổng hợp các cấu hình theo model và tham số goal, nên các giá trị trùng nhau có thể bị ghi đè, còn những cấu hình không xung đột có thể tiếp tục được dùng.

Ba điều phải phân biệt khi đọc `pom.xml`:

- **Goal nào chạy?** Xác định trong `<goals>` hoặc default lifecycle mapping.
- **Chạy lúc nào và theo ID nào?** Xác định qua `<phase>` và `<id>`, bao gồm các ID mặc định như `default-jar`.
- **Dùng cấu hình nào?** Kết hợp plugin-level, execution-level, parent/profile/pluginManagement và tham số plugin goal có hiệu lực.

Đối với ví dụ Java 17, hai JAR có chung giá trị `Built-For` nhưng khác `Main-Class` và metadata audit. Kết quả build, stdout và manifest là bằng chứng trực tiếp để hiểu cơ chế này.

## 18. Tài liệu chính thức

- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven JAR Plugin — Additional Attached JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/attached-jar.html)
- [Maven JAR Plugin — Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html)
- [Maven JAR Plugin — jar:jar goal](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
