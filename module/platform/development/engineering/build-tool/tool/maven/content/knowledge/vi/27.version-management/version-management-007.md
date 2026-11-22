# Phiên bản nội suy và yêu cầu của POM đem xuất bản trong Maven

> **Build Tool Maven · Quản lý phiên bản**  
> Trọng tâm: **CI-friendly versions** trong **Maven 3.x** (`${revision}`, `${sha1}`, `${changelist}`), khác biệt giữa **POM nguồn**, **effective POM**, **flattened POM** và **POM đã `install`/`deploy`**, cùng yêu cầu để một người dùng độc lập có thể tải và giải quyết dependency. Ví dụ dùng **Java 17**, **Maven Flatten Plugin 1.8.0** và một reactor ba module.

## 1. Tình huống: project build được nhưng người khác không dùng được JAR đã phát hành

Giả sử một project có POM nguồn:

```xml
<groupId>org.example.versioning</groupId>
<artifactId>api</artifactId>
<version>${revision}</version>
<properties>
    <revision>1.2.0-SNAPSHOT</revision>
</properties>
```

Khi chạy trong checkout chứa POM, Maven 3 phiên bản hỗ trợ **CI-friendly versions** có thể hiểu phiên bản hiệu lực là:

```text
org.example.versioning:api:1.2.0-SNAPSHOT
```

và tạo JAR:

```text
api-1.2.0-SNAPSHOT.jar
```

Tuy nhiên, **một JAR có tên đúng không chứng minh POM đã phát hành đúng**. Khi `install` vào local repository hoặc `deploy` lên remote repository, Maven còn cung cấp một **POM artifact** để các project tiêu thụ biết cách resolve parent, dependencies, transitive dependencies và metadata cần thiết.

Nếu POM được công bố giữ nguyên:

```xml
<version>${revision}</version>
```

nhưng người dùng khác **không có giá trị `revision`** từ checkout gốc, Maven của họ có thể không dựng được dependency model như mong đợi. Trong multi-module, tình huống còn phức tạp vì các `parent` references và dependencies giữa modules cũng chứa các biểu thức phiên bản.

**Bài học quan trọng:**

- **Phiên bản hiệu lực trong quá trình build** khác với **chuỗi literal nằm trong POM đã lưu ở repository**.
- **`mvn package` thành công** khác với **`mvn install`/`mvn deploy` đã xuất bản một POM người khác tiêu thụ được**.
- **`help:effective-pom` có nội suy thành công** không tự bảo đảm remote/local published `.pom` cũng đã được viết lại.
- Với **Maven 3 CI-friendly versions**, tài liệu Apache Maven khuyến nghị dùng **Flatten Maven Plugin** để POM được cài đặt/phát hành có các version expressions cần thiết đã được giải quyết.

### 1.1. Bốn loại POM cần phân biệt

| Loại | Ở đâu | Đặc điểm | Mục đích |
| --- | --- | --- | --- |
| **Source `pom.xml`** | Repository code | Có thể chứa `${revision}` và cấu hình build | Developer sửa, Maven đọc để xây project |
| **Effective POM** | Model hiệu lực trong Maven; có thể xuất bằng Help Plugin | Đã kết hợp inheritance, profiles, plugin management và nhiều giá trị nội suy | Debug Maven nhìn thấy gì khi build |
| **`.flattened-pom.xml`** | Thường ở thư mục module, do Flatten Plugin tạo | Có thể giải quyết các CI-friendly expressions, tùy `flattenMode` | Là POM được plugin chỉ định cho quá trình install/deploy |
| **Published `.pom`** | Local `~/.m2/repository` hoặc remote repository | **Artifact descriptor mà người tiêu thụ thật sự tải** | Resolve dependency graph, parent, versions |

**Nguồn xác thực cuối cùng cho khả năng tiêu thụ là published POM**, không phải chỉ source POM hay effective POM của nhà phát triển.

## 2. Maven cho phép nội suy version như thế nào?

### 2.1. Vì sao Maven 3 không khuyến khích property tùy ý trong `<version>`?

Một cách viết tưởng như tiện:

```xml
<version>${appVersion}</version>
<properties>
    <appVersion>1.2.0-SNAPSHOT</appVersion>
</properties>
```

không phải kiểu CI-friendly project version được Maven 3 thiết kế hỗ trợ. Model builder cần tọa độ version ở những thời điểm quan trọng như parent resolution và reactor collection; dùng property tùy ý ở `<project><version>` hoặc `<parent><version>` có thể dẫn đến cảnh báo hoặc hành vi resolution khó dự đoán.

Theo hướng dẫn Apache Maven, với **Maven 3.5.0-beta-1 trở lên** các **placeholder đặc biệt** được hỗ trợ trong vị trí CI-friendly version là:

```text
${revision}
${sha1}
${changelist}
```

Chúng **không phải** cơ chế cấp phép dùng mọi tên property trong project version.

### 2.2. Ý nghĩa của ba placeholder

| Placeholder | Công dụng thường thấy | Ghi chú |
| --- | --- | --- |
| `${revision}` | Phần version chính, ví dụ `1.2.0` | Thường đặt ở POM hoặc `-Drevision=...` |
| `${sha1}` | Phần hậu tố do CI cung cấp, có thể trống | **Không tự đọc Git commit** chỉ vì tên là `sha1` |
| `${changelist}` | Hậu tố như `-SNAPSHOT`, hoặc trống khi release | Không tự xóa `-SNAPSHOT` nếu người dùng chưa đặt giá trị phù hợp |

Ví dụ:

```xml
<version>${revision}${sha1}${changelist}</version>
<properties>
    <revision>1.2.0</revision>
    <sha1></sha1>
    <changelist>-SNAPSHOT</changelist>
</properties>
```

**Version hiệu lực của cấu hình này:**

```text
1.2.0-SNAPSHOT
```

Chạy lệnh:

```bash
mvn -Drevision=1.3.0 clean package
```

trong cùng mô hình ấy sẽ tạo version `1.3.0-SNAPSHOT`, vì `changelist` vẫn là `-SNAPSHOT`.

Còn:

```bash
mvn -Drevision=1.3.0 -Dchangelist= clean package
```

cho phiên bản hiệu lực:

```text
1.3.0
```

nếu không có `sha1` và các overrides khác. **Không đồng nghĩa với việc release an toàn chỉ nhờ bỏ hậu tố**: cần kiểm thử, kiểm tra version uniqueness, chữ ký/artifacts và chính sách repository.

### 2.3. `${sha1}` không tự sinh commit hash

Tên `sha1` dễ gây ngộ nhận. Maven **không tự chạy Git** để tính SHA-1 của commit mỗi khi thấy `${sha1}`. Nếu muốn dùng Git identifier làm phần version, pipeline phải cung cấp giá trị:

```bash
mvn -Drevision=1.2.0 -Dsha1=-gabc123 -Dchangelist=-SNAPSHOT clean package
```

Ví dụ sinh:

```text
1.2.0-gabc123-SNAPSHOT
```

Đây chỉ là **version string minh họa**, không phải bằng chứng mã nguồn thật của artifact đã được xác minh. Cần cân nhắc chính sách Maven version, snapshot repository và reproducibility trước khi nhúng commit identifier vào tọa độ.

### 2.4. Không lồng property tùy ý để tính CI-friendly version

Ví dụ phản mẫu:

```xml
<properties>
    <revision>1.2.0-${buildNumber}</revision>
</properties>
<version>${revision}</version>
```

Apache Maven CI Friendly Versions Guide cảnh báo cách **lồng placeholder ngoài ba tên được hỗ trợ** vào phần CI-friendly version này không hoạt động như người viết kỳ vọng. Nên đặt **giá trị revision cuối cùng** trực tiếp từ CLI/CI hoặc cấu hình rõ bằng ba placeholder được hỗ trợ.

Không xem việc POM hiện tại tình cờ build được là hợp đồng tương thích lâu dài với Maven 3 consumers.

## 3. Đặt giá trị CI-friendly version ở đâu?

### 3.1. Khai báo property trong root POM

Cách dễ học nhất:

```xml
<version>${revision}</version>
<properties>
    <revision>1.2.0-SNAPSHOT</revision>
</properties>
```

Mọi lần `mvn clean package` trong checkout sẽ có default version từ POM.

### 3.2. Ghi đè bằng CLI `-D`

```bash
mvn -Drevision=1.2.0-SNAPSHOT clean package
mvn -Drevision=1.2.0 clean package
```

User property `-Drevision=...` được áp dụng cho invocation; không cần chỉnh sửa source POM mỗi lần build. Dùng giá trị **nhất quán trong toàn reactor** để parent/children/dependencies cùng phiên bản.

### 3.3. Đặt trong `.mvn/maven.config`

File có thể chứa dòng:

```text
-Drevision=1.2.0-SNAPSHOT
```

Đây là **file cấu hình Maven CLI**, không phải POM published artifact. Với Maven 3.9.x, tùy chọn được ghi mỗi dòng trong `.mvn/maven.config` theo conventions của Maven version đó; kiểm tra version thật khi dùng cú pháp nhiều flags.

**Không nghĩ rằng người tiêu thụ dependency sẽ nhận `.mvn/maven.config` của nhà phát triển.** Khi một project khác tải `api` từ repository, nó chỉ có các artifacts và metadata đã phát hành, không tự copy file `.mvn` của project nguồn.

### 3.4. Biến môi trường trong CI không tự thành Maven property

CI có thể có `RELEASE_VERSION=1.2.0`. Nếu muốn Maven dùng phiên bản đó, pipeline cần chuyển nó thành user property, ví dụ:

```bash
mvn -Drevision=1.2.0 clean verify
```

hoặc tùy shell/pipeline triển khai giá trị biến môi trường một cách có kiểm soát. Không dựa vào việc tên biến `REVISION` ở shell tự được Maven map thành `${revision}`.

## 4. POM nguồn, effective POM và POM được phát hành khác nhau ở đâu?

Hãy hình dung luồng:

```text
pom.xml (source, có version ${revision})
        |
        | Maven model building / interpolation
        v
Effective project model (version 1.2.0-SNAPSHOT)
        |
        | Compiler/JAR/Tests
        v
target/api-1.2.0-SNAPSHOT.jar
        |
        | Flatten Maven Plugin: flatten
        v
.flattened-pom.xml (version được giải quyết)
        |
        | Install/Deploy dùng POM được plugin chỉ định
        v
Maven repository: api-1.2.0-SNAPSHOT.pom
        |
        | Consumer resolve artifact descriptor
        v
Dependency graph hợp lệ ở project độc lập
```

Mũi tên **flatten → install/deploy** chỉ đúng nếu plugin được bind vào lifecycle trước `install`/`deploy` và `updatePomFile`/cấu hình thích hợp có hiệu lực. Chỉ thêm một plugin trong `<pluginManagement>` mà không có execution không bảo đảm POM published được thay thế.

### 4.1. `effective-pom` giúp debug nhưng không phải published artifact

Lệnh:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

xuất model hiệu lực của Maven tại thời điểm chạy. Nó hữu ích để xem project version, parent, dependencies và active profiles sau nội suy. Nhưng **không tự cài đặt `effective-pom.xml` vào repository thay cho `pom.xml` nguồn**.

Để biết artifact descriptor đã phát hành đúng hay chưa, cần xem **file `.pom` thực sự trong repository** và thử một **consumer độc lập**.

### 4.2. `install` và `deploy` phát hành cả POM

Theo Maven repository layout, một Maven artifact dạng JAR thông thường có:

```text
org/example/versioning/api/1.2.0-SNAPSHOT/
    api-1.2.0-SNAPSHOT.jar
    api-1.2.0-SNAPSHOT.pom
```

`install` đưa các artifacts vào **local repository** của người build. `deploy` đưa artifacts/metadata lên **remote repository** theo cấu hình và quyền truy cập.

Khi một project khác dùng:

```xml
<dependency>
    <groupId>org.example.versioning</groupId>
    <artifactId>api</artifactId>
    <version>1.2.0-SNAPSHOT</version>
</dependency>
```

Maven không chỉ cần bytes của JAR. Nó cần đọc **POM** để biết parent, dependencies, transitives và các quy tắc resolution. Một `.pom` không thể đánh giá được có thể gây lỗi `Failed to read artifact descriptor`, `Non-resolvable parent POM`, hay biểu thức version không giải quyết được.

**Đừng xem việc `jar tf` thành công là chứng cứ về dependency resolution của consumers.**

## 5. Flatten Maven Plugin: giải quyết CI-friendly versions khi xuất bản

### 5.1. Plugin làm gì?

**`org.codehaus.mojo:flatten-maven-plugin`** tạo một POM **dẫn xuất từ source POM**. Nó có nhiều modes với mức độ giữ/bỏ model elements khác nhau.

Dùng cho Maven 3 CI-friendly versions:

```xml
<flattenMode>resolveCiFriendliesOnly</flattenMode>
```

Theo tài liệu MojoHaus, mode này **chỉ giải quyết các CI-friendly version variables** (`revision`, `sha1`, `changelist`) và **giữ các phần POM khác**. Nó khác `defaults`, `clean`, `oss` hay `bom`, vốn có quy tắc giữ/bỏ dependency/build/parent metadata khác nhau.

Đặc biệt, `resolveCiFriendliesOnly` phù hợp khi bạn **chỉ cần POM publish có tọa độ version đã giải quyết**, còn cấu trúc model cho consumers (parent, dependencies, dependencyManagement) vẫn phải được giữ.

### 5.2. `updatePomFile` là phần quan trọng

Cấu hình:

```xml
<updatePomFile>true</updatePomFile>
```

yêu cầu Flatten Plugin đặt **generated POM** làm POM file của `MavenProject` hiện tại, để các goals sau như `install`/`deploy` có thể dùng nó làm artifact descriptor thay vì source POM.

Điểm khó: theo tài liệu plugin, **mặc định** việc chuyển project POM file sang flattened POM thường xảy ra cho packaging **khác `pom`**. Với parent/aggregator/BOM có `<packaging>pom</packaging>`, bạn cần đặc biệt xem xét `updatePomFile=true` để **parent POM xuất bản cũng được chuẩn hóa**.

**Không** đặt `updatePomFile=false` rồi nghĩ rằng chỉ cần tạo `.flattened-pom.xml` là đủ. File được sinh ra nhưng install/deploy có thể vẫn dùng POM nguồn.

### 5.3. Bind plugin vào lifecycle đúng thứ tự

Một cách cấu hình:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>flatten-maven-plugin</artifactId>
    <version>1.8.0</version>
    <configuration>
        <updatePomFile>true</updatePomFile>
        <flattenMode>resolveCiFriendliesOnly</flattenMode>
    </configuration>
    <executions>
        <execution>
            <id>flatten</id>
            <phase>process-resources</phase>
            <goals>
                <goal>flatten</goal>
            </goals>
        </execution>
        <execution>
            <id>flatten.clean</id>
            <phase>clean</phase>
            <goals>
                <goal>clean</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **fragment**, đặt bên trong `<build><plugins>` của parent/root POM nếu muốn plugin **được kế thừa và chạy tại từng child module**. Không chỉ đặt trong `<pluginManagement>` rồi tưởng execution tự được bind.

- `flatten:flatten` tại `process-resources` chạy **trước** các phases `package`, `install`, `deploy`.
- `flatten:clean` tại lifecycle `clean` giúp xóa flattened outputs của lần trước.
- `updatePomFile=true` bảo đảm cả packaging `pom` module (như root parent) cũng trỏ tới generated POM khi lifecycle gọi `install`/`deploy`.
- Generated file mặc định thường là **`.flattened-pom.xml` trong thư mục module**, không ghi đè source `pom.xml`.

**Không sửa source POM chỉ để xóa `${revision}` mỗi lần phát hành.** Source POM vẫn giữ expression để CI có thể tái sử dụng; generated/published POM mới cần chuẩn hóa cho consumers.

### 5.4. `flattenMode` cần chọn theo artifact

| Mode | Ý nghĩa tóm tắt | Cảnh báo |
| --- | --- | --- |
| `resolveCiFriendliesOnly` | Chỉ giải quyết CI-friendly expressions, giữ phần khác | Tốt cho parent và child POMs dùng `${revision}` |
| `defaults` | Tạo consumer-oriented flattened POM theo mặc định plugin | Có thể bỏ build/parent/profiles/metadata mà project phát hành cần |
| `oss` | Giữ nhiều thông tin dự án open source | Vẫn cần xem chính xác model được giữ |
| `bom` | Phù hợp POM Bill of Materials | Giữ dependencyManagement/properties theo semantics BOM |
| `fatjar` | Mode dành cho artifact đã gộp dependencies | Không dùng cho library thin JAR cần công bố transitive dependencies |

Trong ví dụ chính dùng `resolveCiFriendliesOnly`. Với **BOM** hoặc parent POM đặc biệt, phải kiểm tra consumer import/inheritance sau flatten thay vì tự suy từ tên mode.

## 6. Ví dụ thực hành đầy đủ: reactor Java 17 có `parent`, `api` và `app`

### 6.1. Cấu trúc thư mục

```text
ci-version-demo/
├── pom.xml
├── api/
│   ├── pom.xml
│   └── src/main/java/org/example/api/Message.java
└── app/
    ├── pom.xml
    └── src/main/java/org/example/app/Main.java
```

Root vừa là **aggregator** (có `<modules>`) vừa là **parent** (các child có `<parent>`). `api` có một utility method; `app` phụ thuộc trực tiếp `api`. Không cần third-party Java runtime library hay kết nối mạng khi chạy app; Maven vẫn có thể cần network lúc đầu để tải plugins.

Ba module Maven projects được xử lý:

```text
org.example.versioning:versioning-parent:pom:1.2.0-SNAPSHOT
org.example.versioning:api:jar:1.2.0-SNAPSHOT
org.example.versioning:app:jar:1.2.0-SNAPSHOT
```

Đây là **tọa độ sau nội suy**; source POM dùng `${revision}`.

### 6.2. `ci-version-demo/pom.xml` — hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.versioning</groupId>
    <artifactId>versioning-parent</artifactId>
    <version>${revision}</version>
    <packaging>pom</packaging>

    <modules>
        <module>api</module>
        <module>app</module>
    </modules>

    <properties>
        <revision>1.2.0-SNAPSHOT</revision>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.5.1</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>flatten-maven-plugin</artifactId>
                <version>1.8.0</version>
                <configuration>
                    <updatePomFile>true</updatePomFile>
                    <flattenMode>resolveCiFriendliesOnly</flattenMode>
                </configuration>
                <executions>
                    <execution>
                        <id>flatten</id>
                        <phase>process-resources</phase>
                        <goals>
                            <goal>flatten</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>flatten.clean</id>
                        <phase>clean</phase>
                        <goals>
                            <goal>clean</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao cấu hình này quan trọng?**

1. `version=${revision}` là CI-friendly project version cho root.
2. `revision=1.2.0-SNAPSHOT` cung cấp version mặc định ngay trong checkout.
3. `<modules>` thu thập `api`, `app`; không phải danh sách artifactIds bất kỳ.
4. `pluginManagement` ghim Compiler/JAR Plugin versions để Java 17 build nhất quán.
5. Flatten Plugin đặt trong `<build><plugins>` thay vì chỉ `<pluginManagement>` để execution chạy cho parent và children.
6. `flattenMode=resolveCiFriendliesOnly` giải quyết các CI-friendly version values trong flattened POM.
7. `updatePomFile=true` đặc biệt quan trọng do **parent có packaging `pom`**.
8. `project.build.outputTimestamp` hỗ trợ timestamps ổn định cho các packaging plugins hỗ trợ; nó **không tự bảo đảm mọi artifact có byte-identical output**.

### 6.3. `api/pom.xml` — hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.versioning</groupId>
        <artifactId>versioning-parent</artifactId>
        <version>${revision}</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>api</artifactId>
    <packaging>jar</packaging>
</project>
```

Child không tự khai báo `<version>`, nên **kế thừa** project version từ parent. Trong quá trình build Maven 3 có hỗ trợ CI-friendly, parent reference `<version>${revision}</version>` được giải quyết cùng tập properties.

Nếu child nằm ở `api/`, `relativePath=../pom.xml` trỏ về parent POM gốc. `relativePath` hỗ trợ **build trong checkout**, không thay thế một published parent POM hợp lệ cho consumer ở repository.

### 6.4. `api/src/main/java/org/example/api/Message.java`

```java
package org.example.api;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "POM publish OK";
    }
}
```

Class này chỉ dùng Java standard library; không cần framework hoặc config riêng.

### 6.5. `app/pom.xml` — hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.versioning</groupId>
        <artifactId>versioning-parent</artifactId>
        <version>${revision}</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.versioning</groupId>
            <artifactId>api</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

**Chú ý điểm cực quan trọng của Maven 3:**

- Parent `<version>${revision}</version>` là cách CI-friendly được hỗ trợ.
- Dependency **giữa modules** dùng `<version>${project.version}</version>`, **không** thay bằng `${revision}`.
- Tài liệu chính thức Apache Maven CI Friendly Versions đặc biệt nhấn mạnh điều này và cảnh báo việc dùng `${revision}` cho inter-module dependency version trong thiết lập ấy có thể làm build thất bại.

Đây không phải hai biểu thức tương đương về cơ chế build. `${project.version}` trỏ tới **version hiệu lực của project hiện tại**, sau khi Maven đã xây model. Trong demo parent/children đồng bộ version, nên dependency từ app tới api có đúng `1.2.0-SNAPSHOT`.

Nếu một project có nhiều modules với **version khác nhau**, không tự dùng `${project.version}` cho mọi dependency: khi ấy dependency đến module có version riêng cần được quản lý rõ bằng tọa độ tương ứng.

### 6.6. `app/src/main/java/org/example/app/Main.java`

```java
package org.example.app;

import org.example.api.Message;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

`Message` được lấy từ module `api` qua dependency khai báo trong `app/pom.xml`.

## 7. Build Java 17 và kiểm chứng Maven version hiệu lực

Từ thư mục root `ci-version-demo/`:

```bash
java -version
javac -version
mvn -version
mvn -B clean package
```

**Kỳ vọng:**

- Parent POM project được xây trước child projects.
- `api` biên dịch `Message.class` và tạo JAR.
- `app` biên dịch `Main.class`, resolve dependency api cùng reactor và tạo JAR.
- Flatten Plugin tạo `.flattened-pom.xml` cho các modules khi đi tới `process-resources`.
- Artifact version của root, api và app được nội suy từ `revision` mặc định.

Các JAR outputs:

```text
api/target/api-1.2.0-SNAPSHOT.jar
app/target/app-1.2.0-SNAPSHOT.jar
```

**Đây là hai JAR mỏng**, chưa có `Main-Class` do bài không cấu hình executable JAR manifest. Vì thế **không** dùng `java -jar app/target/app-1.2.0-SNAPSHOT.jar` để chứng minh app runnable.

Chạy trực tiếp từ các compiled classes với đủ classpath:

**Linux/macOS:**

```bash
java -cp "app/target/classes:api/target/classes" org.example.app.Main
```

**Windows PowerShell/cmd:**

```powershell
java -cp "app/target/classes;api/target/classes" org.example.app.Main
```

**Stdout chính xác:**

```text
POM publish OK
```

Đây là stdout của `Main`, không phải toàn bộ Maven logs. Nó xác nhận dependency nội bộ được compile và load, nhưng **chưa xác nhận published POM**. Kiểm chứng POM thuộc mục tiếp theo.

### 7.1. Kiểm tra root project version

Trong root:

```bash
mvn -N help:evaluate -Dexpression=project.version -q -DforceStdout
```

Khi Maven Help Plugin thực thi và `revision` có giá trị mặc định, version trả về:

```text
1.2.0-SNAPSHOT
```

Đây là **giá trị cần đối chiếu**, không đảm bảo chỉ có đúng một dòng stdout trên mọi Maven/Help Plugin version nếu có plugin logs hoặc thông điệp bổ sung. `-N` tránh recurse vào children để xem root version.

Ghi đè:

```bash
mvn -N -Drevision=1.2.0 help:evaluate -Dexpression=project.version -q -DforceStdout
```

sẽ trả version hiệu lực:

```text
1.2.0
```

**Kết quả đọc version hiệu lực không phải bằng chứng rằng POM đã cài trong repository được normalized.** Tiếp tục bước cài đặt.

## 8. Kiểm chứng `.flattened-pom.xml` trước khi phát hành

Sau:

```bash
mvn -B clean package
```

các files thường có:

```text
ci-version-demo/.flattened-pom.xml
ci-version-demo/api/.flattened-pom.xml
ci-version-demo/app/.flattened-pom.xml
```

Mỗi file nằm trong thư mục module tương ứng. `.flattened-pom.xml` được plugin sinh ra, khác `target/...jar`; nó là một **POM XML file**. Không chỉnh tay, commit hoặc dùng file này thay source POM trong normal development workflow trừ khi có quy trình riêng.

### 8.1. Điều gì cần kiểm tra?

Với `flattenMode=resolveCiFriendliesOnly`, các vùng version quan trọng dự kiến có:

**Root flattened POM — đoạn chính:**

```xml
<groupId>org.example.versioning</groupId>
<artifactId>versioning-parent</artifactId>
<version>1.2.0-SNAPSHOT</version>
<packaging>pom</packaging>
```

**App flattened POM — parent reference:**

```xml
<parent>
    <groupId>org.example.versioning</groupId>
    <artifactId>versioning-parent</artifactId>
    <version>1.2.0-SNAPSHOT</version>
</parent>
```

Phần dependencies có thể vẫn giữ:

```xml
<version>${project.version}</version>
```

đối với `api`, bởi vì `resolveCiFriendliesOnly` chủ đích **chỉ** giải quyết ba CI-friendly placeholders; `${project.version}` là **biểu thức Maven model chuẩn** có thể được giải quyết trong ngữ cảnh POM của consumer.

**Không đặt tiêu chí sai là “không được có bất kỳ `${...}` nào trong flattened POM”.** Điều kiện quan trọng hơn là **các tọa độ version phải tiêu thụ được**, và các CI-friendly expressions không còn nằm ở những vị trí mà người tiêu thụ không thể nội suy.

### 8.2. `resolveCiFriendliesOnly` không phải mode “xóa mọi property”

Mode này được thiết kế giữ lại phần lớn model: parent, dependencies, build, plugin config... Nó không bảo đảm loại sạch mọi build-time-only content, cũng không phải SBOM generator hoặc tool quét secrets.

Nếu POM vẫn chứa sensitive repository credentials, URLs riêng, hoặc plugins có version/property expressions chỉ tồn tại ở CI, cần có kiểm soát phù hợp **trước khi publish**. Không lấy flattened POM làm bằng chứng rằng mọi nội dung đã an toàn để chia sẻ công khai.

### 8.3. Vì sao `updatePomFile=true` phải hoạt động ở root?

Root là `<packaging>pom</packaging>`, đồng thời là published parent của `api` và `app`. Nếu flatten chỉ tạo file ở root nhưng **không khiến install/deploy sử dụng nó**, repository có thể chứa parent POM vẫn có `<version>${revision}</version>`. Child published POM trỏ parent version literal nhưng repository descriptor của parent lại sai — consumer có thể gặp lỗi parent resolution.

Cách đúng là kiểm chứng **cả root parent POM và hai JAR module POMs** trong repository.

## 9. `mvn install`: đây mới là phép thử published POM trên local repository

Chạy từ root:

```bash
mvn -B clean install
```

Nếu build và flatten thành công, Maven cài JARs **và** POM artifacts trong local Maven repository. Với default local repository là `~/.m2/repository` trên Linux/macOS, các đường dẫn dự kiến:

```text
~/.m2/repository/org/example/versioning/
├── versioning-parent/1.2.0-SNAPSHOT/
│   └── versioning-parent-1.2.0-SNAPSHOT.pom
├── api/1.2.0-SNAPSHOT/
│   ├── api-1.2.0-SNAPSHOT.jar
│   └── api-1.2.0-SNAPSHOT.pom
└── app/1.2.0-SNAPSHOT/
    ├── app-1.2.0-SNAPSHOT.jar
    └── app-1.2.0-SNAPSHOT.pom
```

Có thể có file metadata/checksum/tracking bổ sung, và local repository có thể bị đổi bằng cấu hình `settings.xml`/`maven.repo.local`. Vì vậy đây là **layout minh họa theo default**, không phải đường dẫn cố định cho mọi máy.

**Quan trọng:** đọc `.pom` tại repository **sau install**. Đừng chỉ nhìn `ci-version-demo/pom.xml`, vì source POM đúng chủ đích vẫn có `${revision}`.

### 9.1. Các kiểm tra ở published parent POM

Mở POM đã cài:

```text
versioning-parent-1.2.0-SNAPSHOT.pom
```

Kiểm tra:

- `<groupId>org.example.versioning</groupId>`.
- `<artifactId>versioning-parent</artifactId>`.
- `<version>1.2.0-SNAPSHOT</version>`, không còn `${revision}` ở project version.
- `<packaging>pom</packaging>`.
- Nếu child published POM giữ `<parent>`, parent POM thật sự được cài tại đúng GAV.

Có thể dùng XML parser để kiểm chứng thay vì `grep` theo string thuần, vì POM có thể có whitespace, namespaces và XML comments khác nhau.

### 9.2. Các kiểm tra ở published child POM

Với `api-1.2.0-SNAPSHOT.pom` và `app-1.2.0-SNAPSHOT.pom`, kiểm tra:

- Parent `<version>` đã thành literal `1.2.0-SNAPSHOT`.
- Artifact ID đúng: `api` hoặc `app`.
- Version hiệu lực khớp artifact path trong repository.
- App dependency tới `org.example.versioning:api` với version có thể resolve được (`${project.version}` là hợp lệ trong ngữ cảnh version đồng bộ).
- Không còn `revision`, `sha1`, `changelist` chưa được giải quyết ở các **critical coordinates**.

**Không đòi hỏi child POM phải chứa một `<version>` riêng** nếu nó kế thừa parent version. Parent reference literal và published parent artifact phải đủ để consumer resolve model.

### 9.3. Nếu bỏ Flatten Plugin thì sao?

Trong Maven 3 CI-friendly setups, Apache Maven Guide cảnh báo nếu install/deploy mà **không flatten**, repository có thể nhận source POM với CI-friendly placeholders chưa giải quyết, khiến người dùng khác **không tiêu thụ được**.

Đây là một lỗi **publication metadata**, không phải bug của Java compiler. Maven có thể compile/running code hoàn toàn bình thường trong checkout, vì tại đó revision property có sẵn.

**Khắc phục**: sửa quy trình publication để xuất bản normalized POM, không sửa từng JAR hoặc hướng dẫn consumers tự truyền `-Drevision` bằng tay.

## 10. Kiểm chứng với consumer nằm ngoài reactor — bằng chứng thuyết phục nhất

Chỉ test trong chính reactor có thể che vấn đề, vì source parent POM và user properties vẫn hiện diện. Nên tạo một **project khác** ngoài `ci-version-demo/`, không kế thừa source parent của demo.

Bố cục:

```text
workspace/
├── ci-version-demo/           # reactor nhà cung cấp
└── pom-consumer-check/
    └── pom.xml                # độc lập, không là module của supplier
```

Sau khi supplier chạy thành công:

```bash
mvn -B clean install
```

tạo **`pom-consumer-check/pom.xml` đầy đủ**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.consumer</groupId>
    <artifactId>pom-consumer-check</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.example.versioning</groupId>
            <artifactId>app</artifactId>
            <version>1.2.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
```

Trong `pom-consumer-check/`, chạy:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

**Phần dependency tree cần thấy** (định dạng tiền tố/bản plugin có thể khác):

```text
org.example.consumer:pom-consumer-check:jar:1.0.0
\- org.example.versioning:app:jar:1.2.0-SNAPSHOT:compile
   \- org.example.versioning:api:jar:1.2.0-SNAPSHOT:compile
```

Điều này kiểm tra một **consumer độc lập** có thể resolve published app POM và nhìn thấy `api` là transitive dependency. Nó không tự kiểm chứng runtime Java hoặc mọi nghĩa vụ publish lên remote repository, nhưng là bằng chứng mạnh cho **POM consumability**.

### 10.1. Vì sao không đặt consumer dưới `<modules>` của supplier?

Nếu consumer trở thành một module trong cùng reactor, Maven có thể dùng **reactor workspace** thay vì thông tin đã publish, khiến lỗi POM artifact ở repository bị che đi. Đặt consumer **ngoài reactor**, không chia sẻ parent source POM, không truyền `-Drevision` của supplier.

### 10.2. Cẩn thận cache của local repository

Đôi khi consumer resolution thành công do đã có POM/artifact **từ lần install cũ**. Khi QA publication, có thể dùng **local repository cách ly** cho phép thử, hoặc kiểm tra timestamps/hashes của `.pom` đã cài. Nhưng đừng xóa toàn bộ `~/.m2/repository` của người khác để làm sạch.

Một lựa chọn an toàn ở CI là tạo Maven local repository tạm cho job và chạy supplier `install` rồi consumer `dependency:tree` **trong cùng local repository tạm**. Khi đó không phụ thuộc artifact version cũ trong cache thường ngày.

### 10.3. Remote deploy còn phải kiểm tra thêm gì?

Một `install` thành công chứng minh các artifacts được cài vào local repository, **chưa chứng minh** deploy lên remote thành công. Với remote repository:

- Kiểm tra POM/JAR uploads và metadata thực tế.
- Parent POM được publish trước/đúng version để child POM resolve.
- Repository có khả năng truy cập với credential/chính sách phù hợp.
- Release version không bị ghi đè tùy tiện, SNAPSHOT phù hợp repository snapshots.
- Kiểm tra checksum/signature theo yêu cầu.
- Dùng một consumer không có supplier checkout để resolve **từ remote**.
- Tránh coi `BUILD SUCCESS` của job build nội bộ là bằng chứng đã publish đủ artifacts.

## 11. CI-friendly version trong multi-module: các quy tắc cần giữ

### 11.1. Root project version

```xml
<version>${revision}</version>
```

Được Maven 3 hỗ trợ khi đặt `revision` hợp lệ.

### 11.2. Child parent version

```xml
<parent>
    <groupId>org.example.versioning</groupId>
    <artifactId>versioning-parent</artifactId>
    <version>${revision}</version>
</parent>
```

Đây là pattern được Apache Maven minh họa cho Maven 3 CI-friendly multi-module. Sau flatten, published child POM cần tham chiếu **parent version có thể resolve**.

### 11.3. Inter-module dependency version

```xml
<dependency>
    <groupId>org.example.versioning</groupId>
    <artifactId>api</artifactId>
    <version>${project.version}</version>
</dependency>
```

Đây là cách đúng được Maven Guide khuyến nghị cho dependencies giữa modules cùng version. **Không tự thay** bằng:

```xml
<version>${revision}</version>
```

vì ở mô hình Maven 3 multi-module CI-friendly, `${revision}` ở **dependency version** không được Maven xử lý như `${project.version}` và có thể khiến reactor dependency resolution thất bại.

**Không dùng `${project.parent.version}` khi app có version riêng khác parent** nếu muốn phụ thuộc API có version không trùng parent mà chưa xác định mô hình versioning. Chọn chính xác version của artifact được tiêu thụ.

### 11.4. Parent/aggregator phải được xuất bản khi child references phụ thuộc nó

Nếu published child POM còn:

```xml
<parent>
    <groupId>org.example.versioning</groupId>
    <artifactId>versioning-parent</artifactId>
    <version>1.2.0-SNAPSHOT</version>
</parent>
```

thì Maven consumer cần **resolve parent POM** theo GAV đó. Flatten `resolveCiFriendliesOnly` **giữ parent relation**, không biến child thành POM hoàn toàn độc lập.

Nếu muốn phát hành artifact mà không yêu cầu consumer tải internal parent, cần một **publication-specific flattening strategy** khác có kiểm tra kỹ dependencyManagement, properties, licenses, BOM imports và scopes. Đừng đơn giản xóa `<parent>` khỏi POM đã publish mà không giữ những thông tin cần cho transitive resolution.

### 11.5. DependencyManagement/BOM có requirements riêng

Đối với thư viện/BOM:

- POM publish cần lưu chính xác dependency versions được consumers dùng.
- Import-scoped BOM phải tham chiếu BOM có GAV resolve được.
- Nếu BOM sử dụng CI-friendly placeholder ở `<version>`, nó cũng phải được normalized phù hợp trước deploy.
- Các flatten modes như `bom` có quy tắc giữ dependencyManagement khác `resolveCiFriendliesOnly`; phải thử consumer **import BOM** từ repository độc lập.
- Đừng dựa vào project properties **chỉ nằm trong môi trường CI nhà cung cấp** mà consumer không có.

POM publish là **hợp đồng của dependency graph**, không chỉ manifest nói phiên bản của JAR.

## 12. Release version: đổi `SNAPSHOT` thành phiên bản phát hành

Với root demo:

```xml
<properties>
    <revision>1.2.0-SNAPSHOT</revision>
</properties>
```

build release-like invocation:

```bash
mvn -B -Drevision=1.2.0 clean verify
```

Các tọa độ trong invocation này sẽ là `1.2.0` (không có `-SNAPSHOT`). Nếu cần `install` để kiểm tra POM:

```bash
mvn -B -Drevision=1.2.0 clean install
```

Kiểm tra:

```text
versioning-parent/1.2.0/versioning-parent-1.2.0.pom
api/1.2.0/api-1.2.0.pom
app/1.2.0/app-1.2.0.pom
```

**Đừng chỉ đổi tên JAR từ `-SNAPSHOT.jar` thành `.jar`**. Consumer sẽ tìm artifacts theo Maven GAV và repository metadata; phiên bản POM, JAR, local/remote paths và dependency references đều phải nhất quán.

### 12.1. Với `${revision}${sha1}${changelist}`

Nếu dùng:

```xml
<version>${revision}${sha1}${changelist}</version>
<properties>
    <revision>1.2.0</revision>
    <sha1></sha1>
    <changelist>-SNAPSHOT</changelist>
</properties>
```

để tạo release `1.2.0`, invocation có thể đặt:

```bash
mvn -Dchangelist= clean verify
```

Nếu cần release version khác:

```bash
mvn -Drevision=1.3.0 -Dchangelist= clean verify
```

Ở một pipeline production, **pin revision từ một nguồn duy nhất**, đừng cho hai jobs tự suy ra versions khác nhau. Nếu `sha1` có giá trị không rỗng, version string vẫn chứa phần ấy; cần đặt rõ theo chính sách.

### 12.2. Version không chỉ là marketing label

Snapshot và release có ý nghĩa khác nhau với Maven repository:

- `1.2.0-SNAPSHOT` có thể được cập nhật theo metadata snapshot của repository.
- `1.2.0` là release version; nhiều repositories có chính sách không cho overwrite release.
- Artifact coordinates dùng trong dependencies và parent POM phải khớp đúng version đã publish.
- Khi phát hành version mới, consumer phải chọn version hợp lệ; Maven không tự biến `SNAPSHOT` thành release.

Đừng cho CI deploy release vào snapshot repository hoặc ngược lại chỉ vì profile settings tình cờ cho phép.

## 13. Không nhầm `${project.version}` với CI-friendly placeholder

### 13.1. `${project.version}` là biểu thức Maven model

`project.version` là thuộc tính sau khi Maven model đã được xác định. Nó hợp lý trong các phần như:

```xml
<dependencies>
    <dependency>
        <groupId>org.example.versioning</groupId>
        <artifactId>api</artifactId>
        <version>${project.version}</version>
    </dependency>
</dependencies>
```

đối với modules có cùng version.

### 13.2. `${revision}` dành cho những vị trí được Maven CI-friendly versioning hỗ trợ

Dùng trong project/parent version như Maven Guide. Không suy ra nó là alias của `project.version` ở **mọi ngữ cảnh**. Tài liệu chính thức còn cảnh báo cụ thể rằng dùng `${revision}` cho dependency giữa modules trong multi-module Maven 3 setup có thể fail.

### 13.3. `${project.parent.version}` có thể khác `${project.version}`

Nếu child tự có version `2.0.0` còn parent `1.2.0`, thì hai properties khác nhau. `api` và `app` trong demo có cùng inherited version nên dùng `${project.version}` hợp lý. Đừng dùng một mẫu dependency version chung cho toàn repository nếu các modules có lịch phát hành riêng.

### 13.4. `${pom.version}` không phải bản sao của mọi biểu thức mới

Trong Maven hiện đại, codebase nên ưu tiên các expressions được tài liệu chính thức cho Maven version của mình hỗ trợ. Không xây chiến lược phát hành dựa trên những alias hoặc dynamic property interpolation cũ nếu chưa kiểm tra compatibility. Với bài này, **cặp quy tắc cần nhớ là CI-friendly `${revision}` cho version của project/parent và `${project.version}` cho inter-module dependencies**.

## 14. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mvn package` thành công nhưng consumer không resolve artifact | Published `.pom` còn `${revision}` hoặc parent POM không có | Cấu hình Flatten Plugin, xem installed/deployed `.pom` |
| Source POM vẫn có `${revision}` sau `install` | Đúng mục đích CI-friendly source | Đọc `.flattened-pom.xml` và published `.pom`, không sửa source tùy tiện |
| `.flattened-pom.xml` có nhưng repository `.pom` chưa normalized | Chưa có `updatePomFile` hiệu lực hoặc goal chạy sau install | Bind `flatten` trước `install`, dùng `updatePomFile=true` |
| Child published POM không resolve parent | Parent POM không publish hoặc parent version còn expression | Normalize và publish parent đúng GAV |
| CLI `-Drevision` thay output nhưng POM từ repository vẫn sai | Build-time interpolation khác publication | Kiểm tra `flatten`/`install`/`deploy` lifecycle |
| Maven cảnh báo expression trong `<version>` | Dùng `${myVersion}` tùy ý hoặc Maven cũ | Dùng đúng CI-friendly placeholders và version được hỗ trợ |
| Reactor dependency không resolve dù child version đúng | Dùng `${revision}` trong dependency version thay `${project.version}` | Theo Apache Maven Maven3 guide, dùng `${project.version}` |
| Published POM còn `${project.version}` trong dependency | Không nhất thiết lỗi với resolveCiFriendliesOnly | Test độc lập để xác nhận Maven consumer resolve đúng |
| Consumer `dependency:tree` không thấy `api` | App dependency bị xóa/sai scope/sai version khi flatten | Kiểm tra published app POM và dependency graph |
| Dùng `flattenMode=defaults` mất thông tin cần thiết | Chọn mode không hợp mục tiêu publish | Dùng `resolveCiFriendliesOnly` hoặc mode phù hợp, verify |
| Root packaging `pom` không publish flattened POM | `updatePomFile` mặc định chưa bật cho packaging `pom` | Đặt `<updatePomFile>true</updatePomFile>` |
| Plugin đặt trong `pluginManagement` nhưng không chạy | Chưa có execution thực sự | Đặt trong `<build><plugins>`/execution phù hợp |
| Test consumer thành công do bản cũ trong `.m2` | Local cache chứa version cũ | Dùng test repository riêng hoặc xác minh POM timestamps/hashes |
| CI release mang `-SNAPSHOT` ngoài ý muốn | `changelist` còn `-SNAPSHOT` hoặc `revision` sai | Ghim tham số CI và đọc version hiệu lực |
| Build release `1.2.0` nhưng dependency vẫn `1.2.0-SNAPSHOT` | POM dùng version hardcoded hoặc property riêng | Dùng version model đúng và kiểm tra published descriptor |
| `-Dsha1` không được tạo tự động | Maven không tự lấy Git hash | CI tự cung cấp giá trị có kiểm soát |
| Import BOM thất bại | BOM POM không normalized hoặc mode flatten bỏ dependencyManagement | Chọn BOM mode phù hợp và thử consumer import |
| `help:effective-pom` đúng nhưng deploy lỗi | Effective model không phải remote artifact descriptor | Kiểm tra published remote POM và logs |
| Consumer thiếu dependencyManagement từ parent | Parent chưa publish/không resolve hoặc flatten mode bỏ metadata | Kiểm tra parent/BOM chain và consumability |
| Plugin build được nhưng `deploy` nhận HTTP 401/403 | Credential/quyền repository khác lỗi nội suy | Sửa repository auth và không sửa mù source version |
| POM published chứa secret/token | Build POM giữ thông tin nhạy cảm | Xóa secrets khỏi POM/publication, rotate nếu đã lộ |
| Maven 4 behavior khác Maven 3 | Model 4.1.0 có automatic version resolution | Dùng docs đúng major version; không copy hướng dẫn Maven 3 máy móc |

### 14.1. Quy trình chẩn đoán chuẩn

1. Xem Maven version:

   ```bash
   mvn -version
   ```

2. Xác nhận root project version hiệu lực:

   ```bash
   mvn -N help:evaluate -Dexpression=project.version -q -DforceStdout
   ```

3. Chạy build sạch và flatten:

   ```bash
   mvn -B clean package
   ```

4. Mở `.flattened-pom.xml` của parent và children, kiểm tra critical version expressions.

5. Cài vào repository:

   ```bash
   mvn -B clean install
   ```

6. Mở **published `.pom` trong local repository**, không chỉ xem source POM.

7. Tạo consumer độc lập, chạy `dependency:tree`, kiểm tra cả parent và transitives.

8. Khi deploy, kiểm tra remote POM/JAR metadata và chạy consumer với remote repository.

9. Nếu lỗi phụ thuộc nội bộ, kiểm tra `${project.version}` ở inter-module dependencies, parent version và module inclusion.

10. Đừng ghi `QA PASS` cho khả năng publication chỉ vì JAR có tên version đúng.

### 14.2. Có thể làm gì khi `flatten` không chạy?

Kiểm tra:

```bash
mvn -X clean install
```

Tìm execution `flatten:flatten` trong logs, phase `process-resources`, generated POM path và install plugin POM source được chọn. Nếu chỉ có plugin declaration trong `pluginManagement`, hoặc invocation dừng ở `validate`, flatten goal sẽ chưa được kích hoạt.

**Cẩn thận với logs `-X`:** chúng có thể chứa repository URLs, đường dẫn cá nhân và build configuration nhạy cảm. Kiểm tra trước khi đăng công khai.

## 15. Trách nhiệm của POM đối với người tiêu thụ

POM đã xuất bản là một phần của **API packaging** đối với các Maven consumers. Nó không chỉ ghi GAV của artifact chính.

### 15.1. Các nhóm thông tin cần giữ đúng

- **Tọa độ artifact**: `groupId`, `artifactId`, `version`, `packaging`.
- **Parent POM**: nếu published POM còn `<parent>`, artifact parent phải resolve được ở version đúng.
- **Dependencies**: GAV, scope, optional, classifier/type, exclusions theo semantics sản phẩm.
- **dependencyManagement / BOM imports**: version policies cần thiết cho graph phải tồn tại ở published model hoặc parent/BOM resolvable.
- **Metadata giấy phép/SCM** theo quy định repository và tổ chức.
- **Repositories/credentials**: không leak secrets hay phụ thuộc internal endpoints không dành cho consumer.
- **Version consistency**: JAR filename, POM path, parent version và dependency references không mâu thuẫn.

### 15.2. Những điều không chứng minh consumability

- Chỉ `mvn validate` chạy được trong supplier checkout.
- Chỉ `mvn package` tạo JAR đúng.
- Chỉ `java -cp` chạy ứng dụng đúng.
- Chỉ `help:effective-pom` hiển thị version resolved.
- Chỉ thấy `.flattened-pom.xml` được sinh ra, nhưng chưa biết install/deploy có dùng nó không.
- Chỉ `mvn install` trả BUILD SUCCESS nhưng không đọc POM đã cài hoặc thử consumer.
- Chỉ scan file `.pom` không còn `${revision}`, nhưng `parent` hoặc dependencies khác không resolve.

**Kiểm tra tiêu thụ độc lập mới cho tín hiệu end-to-end**.

### 15.3. Không biến Flatten Plugin thành phép chữa mọi lỗi publish

Flatten Plugin giúp quản lý nội dung POM được công bố, nhưng không sửa:

- API binary compatibility giữa versions.
- Dependency thiếu class/resource ở runtime.
- Thư viện dùng internal repositories không truy cập được.
- Release artifacts thiếu checksum/signature theo policy.
- Publish sai snapshot/release repository.
- Maven consumer dùng version khác với artifact đã được install/deploy.
- Build không reproducible do dynamic/generated files hoặc unpinned plugins.

Vì vậy hoàn tất publication QA cần cả model validation, dependency resolution và runtime tests phù hợp.

## 16. Maven 3 và Maven 4: đọc đúng tài liệu phiên bản

Bài này **ưu tiên Maven 3.x**, vốn cần đặc biệt lưu ý CI-friendly placeholders và flattened published POM trong hướng dẫn chính thức.

Apache Maven nêu: với **Maven 4 + model version 4.1.0**, có hỗ trợ **automatic version resolution** cho parent/subproject và dependency cùng reactor trong một số ngữ cảnh mới, và có thể **không cần Flatten Maven Plugin** theo workflow Maven 3.

Tuy nhiên:

- Không suy rằng một project Maven 3 POM model `4.0.0` tự có mọi Maven 4 behavior.
- Không thay toàn bộ published POM strategy sang Maven 4 chỉ vì máy developer cài Maven 4.
- Plugin versions và consumer Maven versions cũng phải tương thích với artifacts/POM model được publish.
- Khi nâng cấp, làm consumer test từ repository riêng thay vì chỉ build trong reactor.

**Đừng trộn Maven 3 và Maven 4 recipes trong cùng pipeline mà không kiểm tra POM model/version compatibility.**

## 17. Tự kiểm tra kiến thức

**Câu 1.** Trong Maven 3, ba CI-friendly version placeholders được hỗ trợ là gì?  
**Đáp án:** `${revision}`, `${sha1}`, `${changelist}`.

**Câu 2.** `${sha1}` có tự lấy Git SHA của commit hiện tại không?  
**Đáp án:** Không. CI hoặc property configuration phải cung cấp giá trị.

**Câu 3.** `${revision}` trong source POM đã bị “quên nội suy” chỉ vì source POM vẫn giữ expression sau build?  
**Đáp án:** Không. Source POM chủ đích dùng placeholder; phải xem flattened/published POM.

**Câu 4.** Vì sao `mvn package` không đủ để khẳng định published POM tốt?  
**Đáp án:** Vì package tạo JAR nhưng không chứng minh POM install/deploy có metadata consumable.

**Câu 5.** Plugin nào được Apache Maven Guide dùng để normalized POM trước `install`/`deploy`?  
**Đáp án:** Flatten Maven Plugin.

**Câu 6.** Vì sao `updatePomFile=true` quan trọng cho root packaging `pom`?  
**Đáp án:** Nó khiến generated flattened POM được sử dụng như project POM khi install/deploy, thay vì có nguy cơ dùng source POM.

**Câu 7.** Mode nào thích hợp nếu chỉ muốn xử lý CI-friendly version expressions?  
**Đáp án:** `resolveCiFriendliesOnly`.

**Câu 8.** Trong demo, `<parent><version>${revision}</version>` có chủ đích gì?  
**Đáp án:** Child tham chiếu cùng CI-friendly parent version trong reactor.

**Câu 9.** Tại sao dependency app → api dùng `${project.version}` thay vì `${revision}`?  
**Đáp án:** Đây là pattern Maven 3 multi-module chính thức khuyến nghị cho inter-module dependency resolution.

**Câu 10.** Published POM còn `${project.version}` có nhất thiết sai không?  
**Đáp án:** Không; trong model có đủ project version, đây là expression chuẩn, tùy flatten mode có thể được giữ.

**Câu 11.** POM child đã normalized version nhưng parent POM không publish thì sao?  
**Đáp án:** Consumer có thể không resolve được parent; cần publish parent đúng GAV hoặc chiến lược POM độc lập thích hợp.

**Câu 12.** `mvn help:effective-pom` có tự cài effective POM thành artifact descriptor không?  
**Đáp án:** Không. Nó chỉ tạo view model hiệu lực.

**Câu 13.** Làm sao phát hiện POM installed thiếu dependency transitive?  
**Đáp án:** Tạo consumer ngoài reactor và chạy `dependency:tree` với artifact installed.

**Câu 14.** Có nên đặt consumer test trong chính reactor supplier không?  
**Đáp án:** Không nếu mục tiêu là test published metadata; reactor có thể che lỗi bằng source project references.

**Câu 15.** `-Drevision=1.2.0` có tự đảm bảo release lên đúng repository không?  
**Đáp án:** Không; deploy configuration, credentials, repository policy và QA cần kiểm tra riêng.

**Câu 16.** Nếu `revision` là `1.2.0`, `changelist` là `-SNAPSHOT`, version `${revision}${changelist}` bằng gì?  
**Đáp án:** `1.2.0-SNAPSHOT`.

**Câu 17.** Muốn version `1.2.0` với `changelist=-SNAPSHOT` mặc định, có thể ghi đè thế nào?  
**Đáp án:** `-Dchangelist=` (nếu version POM có dùng `${changelist}`).

**Câu 18.** Vì sao Flatten Plugin không được dùng như một bộ lọc secrets tự động?  
**Đáp án:** Vì flatten mode và POM element selection chủ yếu phục vụ build/publish metadata; không bảo đảm phát hiện thông tin nhạy cảm.

## 18. Checklist trước khi `install` hoặc `deploy`

- [ ] Maven major version đúng với chiến lược version interpolation.
- [ ] Dùng các CI-friendly placeholders hỗ trợ cho project/parent version ở Maven 3.
- [ ] Giá trị `revision`, `sha1`, `changelist` (nếu có) được xác định trước build.
- [ ] Không tự lồng arbitrary property vào CI-friendly version string.
- [ ] Dùng `${project.version}` cho inter-module dependencies cùng version theo Maven 3 guide.
- [ ] Parent và child version nhất quán qua toàn reactor.
- [ ] Flatten Plugin phiên bản được ghim.
- [ ] `<flattenMode>resolveCiFriendliesOnly</flattenMode>` hoặc mode khác có lý do rõ.
- [ ] `<updatePomFile>true</updatePomFile>` khi cần publish flattened parent packaging `pom`.
- [ ] Flatten goal chạy đủ sớm trước install/deploy.
- [ ] Không đặt plugin chỉ trong pluginManagement rồi quên execution.
- [ ] Các `.flattened-pom.xml` thực sự được sinh.
- [ ] Đã kiểm tra published `.pom` trong local/remote repository, không chỉ source `pom.xml`.
- [ ] Các GAV, parent references và dependency versions có thể resolve.
- [ ] Nếu child còn parent reference, parent POM đã được publish với version tương ứng.
- [ ] Các BOM/dependencyManagement references cần cho consumer còn đầy đủ.
- [ ] Không leak tokens, passwords hoặc thông tin CI riêng vào published POM.
- [ ] Đã chạy một consumer độc lập ngoài reactor để resolve artifact và transitives.
- [ ] Phân biệt rõ SNAPSHOT và release repository policies.
- [ ] Đã chạy tests thích hợp; `package`/`install` xanh không thay thế test/report QA.
- [ ] Chỉ `deploy` sau khi kiểm chứng Maven artifact metadata và release constraints.

## 19. Nguồn tham khảo chính thức

1. [Apache Maven — Maven CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html) — ba placeholder hợp lệ, multi-module parent, `${project.version}` cho dependencies, yêu cầu flatten khi `install`/`deploy`.
2. [MojoHaus Flatten Maven Plugin — Usage](https://www.mojohaus.org/flatten-maven-plugin/usage.html) — bind goals, `updatePomFile` và `resolveCiFriendliesOnly`.
3. [MojoHaus Flatten Maven Plugin — flatten:flatten parameters](https://www.mojohaus.org/flatten-maven-plugin/flatten-mojo.html) — flatten modes, generated POM file và package `pom` behavior.
4. [MojoHaus Flatten Maven Plugin — flatten:clean](https://www.mojohaus.org/flatten-maven-plugin/clean-mojo.html) — cleanup generated flattened POM.
5. [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html) — parent, modules, dependencies và project model.
6. [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — các trường `groupId`, `artifactId`, `version`, `parent`, dependencyManagement.
7. [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — dependency scopes và transitive resolution.
8. [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — reactor vs external artifact resolution.
9. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — `package`, `verify`, `install`, `deploy`.
10. [Apache Maven — Guide to Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html) — `.mvn/maven.config` và Maven config.
11. [Apache Maven — Maven 4 Multi-Subproject Guide](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html) — những khác biệt khi dùng model version `4.1.0`.

**Kết luận:** Với Maven 3, dùng **CI-friendly placeholders đúng vị trí**, giữ dependency giữa modules bằng **`${project.version}`**, và tạo **published POM đã giải quyết các critical version references** thông qua Flatten Maven Plugin trước `install`/`deploy`. Một build **trong checkout** thành công chưa đủ; hãy mở **POM thực tế ở repository** và thử một **Maven consumer độc lập** để chứng minh artifact thực sự dùng được.
