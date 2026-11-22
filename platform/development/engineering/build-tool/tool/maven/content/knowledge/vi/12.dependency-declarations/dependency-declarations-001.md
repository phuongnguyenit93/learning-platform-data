# Maven dependencies và cấu trúc một khai báo dependency

## 1. Vì sao Maven cần dependencies?

Trong Java, ứng dụng thường dùng các thư viện do bên khác phát triển: xử lý chuỗi, JSON, kết nối cơ sở dữ liệu, logging, kiểm thử hoặc HTTP client. Khi dùng `javac` thủ công, bạn phải tự tải JAR và ghép đường dẫn classpath. Maven thay việc đó bằng các khai báo có cấu trúc trong `pom.xml`.

**Dependency (phụ thuộc)** là một artifact mà dự án cần để biên dịch, chạy hoặc kiểm thử. Bạn khai báo artifact bằng tọa độ Maven; Maven đọc metadata, tìm phiên bản phù hợp ở kho cục bộ/từ xa, tải những tệp cần thiết và đưa chúng vào classpath theo `scope`.

Trong POM, một phụ thuộc trực tiếp được khai báo **bên trong `<dependencies>`** dưới dạng **`<dependency>`**:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
</dependencies>
```

Đây là **đoạn POM**, không phải toàn bộ `pom.xml`. Sau khi được đặt bên trong phần tử `<project>` hợp lệ, nó nói rằng dự án cần thư viện `commons-lang3` phiên bản `3.17.0`. Vì không khai báo `scope` nên Maven dùng mặc định `compile`.

Dòng chảy điển hình:

```text
pom.xml: <dependencies>
      |
      v
Đọc groupId + artifactId + version + type/classifier/scope
      |
      v
Tra local Maven repository
      |
      +-- Có artifact và metadata phù hợp --> Dùng cache
      |
      +-- Còn thiếu --> Tra remote repositories / mirror --> Tải về
      |
      v
Đọc POM của artifact, xem phụ thuộc bắc cầu (transitive)
      |
      v
Tạo cây dependency và classpath theo scope
      |
      +-- compile --> biên dịch mã chính
      +-- test    --> biên dịch/chạy kiểm thử
      +-- runtime --> chạy ứng dụng
```

Maven **không tải và sử dụng mọi artifact trên Internet**: nó xử lý đúng graph phụ thuộc do POM hiệu lực, các khai báo bắc cầu, scope, exclusion và luật chọn phiên bản quyết định. Những điểm đó bắt đầu từ việc khai báo một dependency đúng cách.

## 2. Bộ ba tọa độ Maven: groupId, artifactId, version

Một artifact thông thường được nhận diện bằng:

```text
groupId:artifactId:version
org.apache.commons:commons-lang3:3.17.0
```

Ba trường quan trọng:

| Trường | Ý nghĩa | Giá trị trong ví dụ |
| --- | --- | --- |
| `groupId` | Nhóm/tổ chức xuất bản artifact; thường có dạng tên miền đảo | `org.apache.commons` |
| `artifactId` | Tên module/thư viện thuộc nhóm | `commons-lang3` |
| `version` | Phiên bản artifact muốn dùng | `3.17.0` |

Đường dẫn lưu trữ trong repository Maven thường phản ánh tọa độ, ví dụ:

```text
org/apache/commons/commons-lang3/3.17.0/
  commons-lang3-3.17.0.jar
  commons-lang3-3.17.0.pom
  (metadata/kiểm tra toàn vẹn khác nếu có)
```

`groupId` phân thành thư mục theo dấu chấm; `artifactId` và `version` xác định phần còn lại. Đây là cấu trúc của **artifact repository**, không phải cấu trúc thư mục mã nguồn `src/main/java`.

Tuy thường nói ngắn là GAV, một dependency cũng có thể phân biệt bằng **`type` và `classifier`**. Đừng nhầm tọa độ Maven với tên Java package: artifact `commons-lang3` có Java package `org.apache.commons.lang3`, nhưng không bắt buộc mọi thư viện tuân theo phép biến đổi đơn giản ấy.

### Version cố định và khả năng tái lập

Khai báo `<version>3.17.0</version>` giúp những máy khác nhau có cùng ý định chọn phiên bản. Không nên tùy tiện dùng các phiên bản động hoặc khoảng version trong một dự án cần build tái lập, bởi việc chọn artifact có thể thay đổi theo thời điểm và metadata ở repository.

Version `1.0.0-SNAPSHOT` chỉ một bản đang phát triển; nội dung của SNAPSHOT có thể được cập nhật theo repository policy. Version release như `3.17.0` thường được kỳ vọng ổn định hơn. Một bản phát hành chỉ nên được thay thế bằng version mới thay vì ghi đè cùng tọa độ.

## 3. Cấu trúc đầy đủ của phần tử dependency

Ngoài GAV, Maven hỗ trợ nhiều trường điều khiển cách sử dụng phụ thuộc:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-lib</artifactId>
    <version>1.2.3</version>
    <type>jar</type>
    <classifier>tests</classifier>
    <scope>test</scope>
    <optional>true</optional>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>old-helper</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

**Đoạn này chỉ minh họa tất cả trường, không phải một dependency sẵn có để copy và build.** Các tọa độ `com.example:example-lib:1.2.3`, classifier `tests` và artifact cần loại trừ đều là ví dụ; một classifier chỉ hoạt động khi nhà phát hành thực sự cung cấp artifact tương ứng.

| Thành phần | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `groupId` | Thông thường có | Nhóm xuất bản |
| `artifactId` | Thông thường có | Tên artifact |
| `version` | Cần có nguồn phiên bản | Có thể viết trực tiếp hoặc được cung cấp từ `dependencyManagement` |
| `type` | Không; mặc định `jar` | Kiểu artifact, ví dụ `jar`, `pom`, `test-jar` |
| `classifier` | Không | Phân loại biến thể artifact, ví dụ `sources` hoặc `tests` khi được xuất bản |
| `scope` | Không; mặc định `compile` | Xác định phụ thuộc có mặt ở classpath nào, và ảnh hưởng truyền phụ thuộc |
| `optional` | Không; mặc định `false` | Có nên truyền dependency này cho dự án tiêu thụ theo cách thông thường không |
| `exclusions` | Không | Loại một số dependency bắc cầu theo `groupId` + `artifactId` |
| `systemPath` | Chỉ dùng với `scope=system`; không khuyến nghị | Đường dẫn JAR trực tiếp trên máy, làm giảm khả năng tái lập |

Trong phần lớn dự án, **không cần viết đủ mọi trường**. Một khai báo chính xác thường chỉ cần `groupId`, `artifactId`, `version` hoặc version được quản lý, và `scope` nếu khác mặc định:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

`<optional>` và `<exclusions>` dành cho những nhu cầu có lý do cụ thể; đặt chúng theo thói quen có thể che mất thành phần thực sự cần.

## 4. Hiểu scope trước khi thêm dependency

`scope` quyết định các classpath liên quan tới một dependency. Những scope thường gặp:

| Scope | Mã chính lúc compile | Lúc runtime thông thường | Trong test | Ghi chú |
| --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | Phần lớn thư viện mà ứng dụng cần |
| `provided` | Có | Thường không được đưa vào runtime dependency classpath bởi Maven | Có | Môi trường chạy dự kiến tự cung cấp API/thư viện |
| `runtime` | Không trực tiếp ở compile của mã chính | Có | Có | Driver/implementation chỉ cần khi chạy |
| `test` | Không | Không | Có | JUnit, mocking và công cụ test |
| `system` | Gần với provided, nhưng lấy JAR từ `systemPath` | Không nên dựa vào Maven để phân phối | Tùy phạm vi tương ứng | Không khuyến nghị vì phụ thuộc đường dẫn máy |
| `import` | Không phải classpath scope thông thường | Không | Không | Chỉ dùng cho POM kiểu `pom` trong `dependencyManagement` |

Bảng mô tả classpath điển hình khi dùng các plugin/lifecycle chuẩn. Những plugin đóng gói đặc biệt, môi trường application server hoặc custom classloader có thể làm chi tiết runtime khác đi.

Ví dụ cách chọn:

- `commons-lang3` được gọi từ `src/main/java` → `compile` (không ghi scope cũng được).
- `junit-jupiter` chỉ xuất hiện trong `src/test/java` → `test`.
- JDBC driver chỉ được tải theo tên qua cơ chế runtime, trong khi mã chính chỉ compile với API phù hợp → có thể dùng `runtime` nếu thiết kế thực sự không import lớp driver khi compile.
- API do servlet container cung cấp → thường dùng `provided`; nếu chạy độc lập mà không có container, dependency này có thể thiếu.
- Một BOM (Bill of Materials) → `type=pom`, `scope=import` trong `dependencyManagement`; BOM không tạo ra dependency runtime.

**Lỗi phổ biến:** đặt JUnit scope `compile` khiến API kiểm thử xuất hiện không cần thiết trên classpath chính hoặc truyền tới dự án tiêu thụ. Đặt thư viện được mã chính trực tiếp import là `test` thì `mvn compile` có thể báo package/class không tồn tại.

## 5. Ví dụ Maven Java 17 thực sự sử dụng hai dependency

Tạo dự án sau để quan sát một thư viện phục vụ mã ứng dụng và một thư viện chỉ phục vụ kiểm thử.

```text
dependency-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/course/App.java
    └── test/
        └── java/dev/course/AppTest.java
```

### 5.1. POM hoàn chỉnh

Tạo `dependency-demo/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.course</groupId>
    <artifactId>dependency-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Thu vien duoc ma chinh su dung: scope compile mac dinh -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>

        <!-- Chi dung cho kiem thu: scope test -->
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây `<dependencies>` là khai báo **thư viện của dự án**; `<build><plugins>` là **công cụ mà Maven dùng để build/test/chạy ví dụ**. Hai khu vực có mục đích khác nhau. Maven Compiler Plugin với `maven.compiler.release=17` cần JDK hỗ trợ Java 17. Maven Surefire Plugin được ghim phiên bản để chạy JUnit Jupiter qua JUnit Platform; Exec Maven Plugin giúp khởi chạy chương trình cùng các dependency runtime của dự án mà không phải ghép classpath thủ công.

### 5.2. Mã Java sử dụng dependency compile

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String displayName(String input) {
        if (StringUtils.isBlank(input)) {
            return "Khách";
        }
        return StringUtils.capitalize(input.strip());
    }

    public static void main(String[] args) {
        System.out.println("Xin chào, " + displayName("maven") + "!");
    }
}
```

Trong đoạn mã trên, `StringUtils` thuộc JAR `commons-lang3`. `isBlank` kiểm tra `null`, chuỗi rỗng hoặc chỉ có khoảng trắng; `capitalize` viết hoa ký tự đầu của tên đã `strip`. Không cần tải file JAR bằng tay hoặc cấu hình classpath trong IDE: Maven đọc dependency để tạo classpath biên dịch.

### 5.3. Test dùng dependency test

Tạo `src/test/java/dev/course/AppTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void formatsNameFromDependency() {
        assertEquals("Maven", App.displayName("  maven  "));
    }

    @Test
    void usesFallbackForBlank() {
        assertEquals("Khách", App.displayName("   "));
    }

    @Test
    void usesFallbackForNull() {
        assertEquals("Khách", App.displayName(null));
    }
}
```

Test dùng `@Test` và `assertEquals` từ JUnit Jupiter. Ba phép thử không phụ thuộc mạng, thời gian hay dữ liệu bên ngoài. Đây là ví dụ **đầy đủ**, không cần chèn thêm mã vào lớp khác.

### 5.4. Chạy build và kiểm chứng kết quả

Trong thư mục `dependency-demo`, với JDK 17+ và Maven đã cài:

```bash
mvn -version
mvn clean verify
mvn -q -Dexec.mainClass=dev.course.App exec:java
```

Lệnh đầu xác định Maven/JDK. Lệnh `clean verify` biên dịch mã chính, mã kiểm thử, chạy ba test và tạo JAR của dự án. Khi cả ba test đều đúng, Maven báo `BUILD SUCCESS` (các dòng log còn tùy môi trường). Lệnh cuối dùng Exec Maven Plugin để khởi chạy với classpath gồm các dependency phù hợp.

**Stdout của chương trình Java** là:

```text
Xin chào, Maven!
```

Lệnh `mvn -q` có thể vẫn in cảnh báo hoặc thông báo lỗi từ launcher/plugin tùy môi trường; phần trên là dòng do `App.main` in ra khi chạy thành công. Nếu dùng Maven Wrapper thì thay `mvn` bằng `./mvnw` hoặc `mvnw.cmd` theo hệ điều hành.

Đầu ra build điển hình:

```text
target/classes/dev/course/App.class
target/test-classes/dev/course/AppTest.class
target/surefire-reports/
target/dependency-demo-1.0.0-SNAPSHOT.jar
```

Dependency JAR được Maven cache ở local repository, thường dưới `~/.m2/repository/org/apache/commons/commons-lang3/3.17.0/`, **không phải** trong `target/classes`. JAR thông thường do Maven Jar Plugin đóng gói **không tự gộp** commons-lang3 và JUnit thành một fat JAR. Vì thế:

```bash
java -cp target/classes dev.course.App
```

có thể báo `NoClassDefFoundError` đối với `StringUtils` nếu không có thư viện đó trên runtime classpath. Đừng coi đây là lỗi Maven không tải dependency: `java -cp target/classes` là lệnh gọi JVM độc lập, không nhờ Maven bổ sung các JAR. Chạy qua `exec:java` trong bài này để có classpath đúng; nếu muốn một executable/fat JAR, cần cấu hình plugin đóng gói phù hợp ở bài học riêng.

## 6. Direct dependency và transitive dependency

Nếu bạn khai báo `A`, còn POM của `A` khai báo `B`, Maven có thể cần `B` dù POM dự án của bạn không viết trực tiếp `B`. Đây là **phụ thuộc bắc cầu (transitive dependency)**.

```text
Ứng dụng (root)
   |
   +-- A (trực tiếp)
         |
         +-- B (bắc cầu)
                |
                +-- C (bắc cầu tiếp)
```

Maven phân giải graph theo metadata POM, scope, optional, exclusions và quy tắc xung đột phiên bản. Không phải mọi dependency trong POM của thư viện đều truyền qua: `test`, `provided`, `optional` và exclusions có thể khiến một cạnh graph không xuất hiện trong dự án tiêu thụ. Đây là lý do đôi khi chỉ nhìn `<dependencies>` của POM gốc chưa thấy hết các JAR có trong classpath.

Để xem cây thực tế của dự án ví dụ:

```bash
mvn dependency:tree
```

Hoặc lọc một dependency:

```bash
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Đây là các goal của Maven Dependency Plugin; lần chạy đầu có thể cần tải plugin. Kết quả liệt kê phụ thuộc đang được phân giải cùng scope và những nhánh bắc cầu. Tùy phiên bản plugin và flag, cách hiển thị node bị loại do xung đột/duplicate có thể khác; đọc log thực tế thay vì dự đoán mọi dòng.

### Khi có xung đột phiên bản

Giả sử hai nhánh transitive cùng đòi một artifact ở hai phiên bản khác nhau. Maven mặc định sử dụng quy tắc **dependency mediation**, tiêu biểu là lựa chọn định nghĩa “gần dự án gốc” hơn; nếu hai đường đi có cùng độ sâu, thứ tự khai báo có thể quyết định. Không nên coi “Maven luôn tự chọn phiên bản mới nhất”.

Khi version bị chọn không như mong muốn, có thể khai báo artifact đó trực tiếp trong `<dependencies>` hoặc quản lý version qua `<dependencyManagement>`. Hãy kiểm tra compatibility; ép một version khác có thể gây lỗi `NoSuchMethodError` khi chạy dù vẫn compile thành công.

## 7. dependencyManagement khác dependencies

Hai tên rất giống nhau nhưng chức năng khác nhau:

- **`<dependencies>`**: *thực sự yêu cầu* artifact tham gia vào dự án theo scope tương ứng.
- **`<dependencyManagement>`**: *quản lý cấu hình mặc định/phiên bản* khi một dependency được yêu cầu ở nơi thích hợp; **không tự thêm thư viện vào classpath** chỉ vì có phần tử quản lý.

Ví dụ **các đoạn con** để đặt dưới `<project>` của POM (cùng cấp, không phải POM đầy đủ):

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
```

Trong cấu hình này, khai báo trực tiếp `commons-lang3` ở `<dependencies>` **có thể bỏ `version`** vì version đã có nguồn từ `dependencyManagement`. Nếu xóa khối `<dependencies>` mà chỉ để lại `dependencyManagement`, dự án **không tự phụ thuộc** vào commons-lang3.

Mẫu này rất hữu ích cho POM cha/multi-module: một nơi quyết định version, các module chỉ khai báo những thư viện thực sự sử dụng. Không nên đặt mọi dependency trong parent `<dependencies>` chỉ để “quản lý version”, vì có thể vô tình làm các module con nhận phụ thuộc không cần thiết.

### Dùng BOM (Bill of Materials)

Một BOM là artifact kiểu POM chuyên cung cấp tập version đã phối hợp. Để nhập BOM, dùng **type `pom` và scope `import` trong `dependencyManagement`**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Ví dụ này dùng JUnit BOM cùng version với thư viện bài thực hành. BOM giúp quản lý version JUnit, nhưng **phần `junit-jupiter` trong `<dependencies>` vẫn cần** nếu dự án sử dụng JUnit Jupiter; BOM không tự bật test framework. Đừng dùng `scope=import` cho JAR thông thường ở `<dependencies>`.

## 8. Optional và exclusions: kiểm soát phụ thuộc truyền sang dự án khác

### 8.1. optional không giống test scope

Một thư viện có thể cung cấp nhiều tính năng, một số chỉ cần dependency khi người dùng bật tính năng ấy. Nhà phát triển thư viện có thể ghi:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>special-adapter</artifactId>
    <version>1.2.3</version>
    <optional>true</optional>
</dependency>
```

Đây là **một tọa độ minh họa**, không phải ví dụ để tải trực tiếp. `optional=true` nói rằng **dự án tiêu thụ thư viện này không tự động nhận special-adapter theo đường phụ thuộc bắc cầu thông thường**; dự án cần tính năng đó có thể phải khai báo adapter trực tiếp.

Với chính thư viện đang khai báo, dependency optional vẫn phục vụ build theo scope của nó. `optional` không phải cách bỏ qua dependency khi biên dịch chính thư viện, cũng không thay thế `scope=test`.

### 8.2. exclusions bỏ một nhánh phụ thuộc bắc cầu

Khi một thư viện đem theo dependency không phù hợp, có thể loại nó ở đúng cạnh:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-client</artifactId>
    <version>2.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>legacy-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đoạn trên chỉ giải thích cú pháp; các artifact `com.example` là **minh họa**, không có yêu cầu chúng tồn tại trên Maven Central. Một exclusion xác định artifact theo `groupId` và `artifactId`, không dựa trên version. Nó áp dụng cho đường phụ thuộc xuất phát từ dependency cụ thể đó; **không mặc định cấm artifact trên mọi đường khác**.

Đừng dùng exclusion chỉ để xóa cảnh báo khi chưa hiểu thư viện nào cần artifact ấy. Nếu loại một dependency mà mã runtime của thư viện vẫn gọi nó, chương trình có thể lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`.

## 9. type, classifier và phạm vi artifact

Một khai báo không có `type` mặc định nhắm tới artifact kiểu `jar`. Nhưng dự án có thể xuất bản nhiều kiểu/sản phẩm:

- `<type>pom</type>`: tham chiếu artifact POM, đặc biệt phổ biến với BOM ở `dependencyManagement`.
- `<type>test-jar</type>`: một kiểu artifact kiểm thử được tạo/công bố đặc biệt; cần xác minh nhà xuất bản có cung cấp nó.
- `<classifier>sources</classifier>`, `<classifier>tests</classifier>`: phân biệt biến thể của artifact khi nhà xuất bản đã tạo và upload biến thể đó.

Ví dụ cú pháp, **chỉ dùng khi nhà phát hành đã cung cấp tests JAR**:

```xml
<dependency>
    <groupId>dev.team</groupId>
    <artifactId>test-fixtures</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

Không nên tùy tiện thêm `classifier=sources` để dùng thư viện runtime: sources JAR thường chứa mã nguồn, không phải các class đã biên dịch để chạy. Nếu không tìm thấy artifact biến thể, kiểm tra tọa độ đầy đủ (gồm type/classifier) và tài liệu của nhà xuất bản trước khi cho rằng repository bị lỗi.

## 10. system scope và systemPath: vì sao nên tránh?

Maven còn hỗ trợ `scope=system` với `systemPath`:

```xml
<dependency>
    <groupId>dev.local</groupId>
    <artifactId>legacy-lib</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/libs/legacy-lib.jar</systemPath>
</dependency>
```

Đây là **đoạn minh họa cho một trường hợp không khuyến nghị**; nó chỉ hoạt động nếu JAR tồn tại đúng vị trí trên máy. Maven không tự tìm/tải file đó từ repository. Nó làm giảm khả năng build lại trên CI, trong repository khác hoặc khi file không được chia sẻ.

Hướng tốt hơn là xuất bản artifact hợp pháp vào repository nội bộ hoặc, để thử nghiệm cục bộ, cài một JAR thật bằng Maven Install Plugin với tọa độ thích hợp. Sau đó dùng `<dependency>` thông thường. Không dùng `systemPath` như cách lâu dài để lách quản lý phiên bản và kho.

## 11. Maven tìm dependency như thế nào?

Khi Maven gặp tọa độ artifact, nó:

1. Tạo yêu cầu dependency theo GAV và các thuộc tính phụ như type/classifier.
2. Dùng **local repository** của môi trường Maven (thường ở `~/.m2/repository`) để tra bản đã có.
3. Phân giải artifact/metadata còn thiếu từ remote repositories hiệu lực, có thể qua mirror được cấu hình trong `settings.xml`.
4. Đọc POM của artifact để phát hiện phụ thuộc bắc cầu, áp dụng scope/optional/exclusions và luật chọn version.
5. Thiết lập các classpath phù hợp cho compile, test, runtime và plugin/lifecycle.

**Lưu ý:** thư viện mã chính không nằm ở `target/` chỉ vì được tải. `target/` chứa đầu ra build của **dự án hiện tại**, còn thư viện bên ngoài thường được cache trong local repository; runtime classpath phải bao gồm chúng theo cách thích hợp.

Một dependency khai báo đúng tọa độ nhưng vẫn không tải được có thể do sai version, cấu hình repository/mirror, chính sách SNAPSHOT/release, mạng, quyền truy cập hoặc cache. Đừng tự đổi tọa độ chỉ để làm biến mất lỗi trong khi chưa xác minh artifact đúng là sản phẩm cần dùng.

Các bước kiểm tra:

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

- `mvn -version` kiểm tra Maven/JDK thực sự đang chạy.
- `help:effective-pom` cho thấy model sau khi kế thừa từ POM cha, profile và dependencyManagement.
- `dependency:tree` cho thấy graph phụ thuộc đã phân giải, hữu ích khi có nhiều artifact bắc cầu hoặc xung đột scope/version.

Một số Maven plugin như Help/Dependency Plugin có thể cần được tải về trong lần gọi đầu. Không suy luận rằng lệnh thất bại do mã Java khi log chỉ báo Maven chưa tải được plugin.

## 12. Các lỗi thường gặp khi khai báo dependency

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `package org.apache.commons.lang3 does not exist` | Chưa khai báo commons-lang3, scope không phù hợp hoặc phân giải thất bại | Đối chiếu GAV, scope, repository và POM |
| `Could not find artifact ...` | Sai tọa độ/version, repository không chứa artifact, offline/cache thiếu | Kiểm tra artifact ở kho thật và settings hiệu lực |
| `Missing version for dependency` | Bỏ `version` nhưng không có version tương ứng trong dependencyManagement | Thêm version hoặc quản lý nó ở đúng cấp |
| Test dùng JUnit không compile | Thiếu `junit-jupiter` hoặc test đặt nhầm ở `src/main/java` | Khai báo scope `test` và đặt test trong `src/test/java` |
| `java -cp target/classes ...` lỗi `NoClassDefFoundError` | JVM không nhận JAR bên ngoài khi chạy trực tiếp | Dùng `exec:java` hoặc runtime classpath đúng |
| Hai thư viện yêu cầu version khác nhau | Xung đột dependency bắc cầu và luật mediation | Xem `dependency:tree`, chọn version tương thích |
| Thêm `<dependencyManagement>` nhưng không có thư viện | Quản lý version không tự thêm dependency | Thêm khai báo vào `<dependencies>` |
| Bật `optional=true` rồi kỳ vọng thư viện không dùng dependency ấy | Hiểu nhầm optional với scope | Nhớ optional chủ yếu ảnh hưởng người tiêu thụ transitive |
| Exclusion làm runtime lỗi | Loại artifact thực sự cần hoặc nhánh khác vẫn đưa nó vào | Kiểm tra graph và nhu cầu runtime |
| Có `classifier=tests` nhưng Maven không tìm thấy artifact | Nhà phát hành không cung cấp artifact phân loại ấy | Kiểm tra artifact tồn tại và tọa độ đầy đủ |
| Dùng `systemPath` để chỉ JAR cá nhân | File không có trên máy khác/CI | Đưa artifact vào repository và quản lý version |
| Chỉ xem artifact đã có ở máy mình | Local repository chứa bản install/cache, CI không có | Thử môi trường/kho local sạch với remote repository phù hợp |

Ngoài ra, **đừng copy bừa một dependency tìm thấy trên Internet**. Kiểm tra nguồn xuất bản, phiên bản, giấy phép và rủi ro bảo mật. Khi cập nhật phiên bản, chạy kiểm thử và kiểm tra dependency tree trước khi đưa vào nhánh chính.

## 13. Quy trình thêm một dependency mới có kiểm chứng

Trong dự án thực tế, bạn có thể theo quy trình:

1. **Xác định nhu cầu**: thư viện cần cho mã chính, lúc chạy hay chỉ cho test?
2. **Xác định nguồn đáng tin** và tọa độ chính xác: `groupId`, `artifactId`, `version`; xem có cần classifier/type không.
3. **Chọn scope tối thiểu đúng**: mặc định compile khi mã chính sử dụng; test cho công cụ kiểm thử.
4. **Khai báo trong `<dependencies>`**. Nếu dự án có parent/BOM, ưu tiên version được quản lý nhất quán.
5. **Chạy build**: `mvn clean verify`; giải quyết lỗi tải artifact hoặc compiler/test nếu xuất hiện.
6. **Xem cây phụ thuộc**: `mvn dependency:tree`; kiểm tra version bắc cầu và sự trùng lặp.
7. **Chạy ứng dụng trong môi trường tương ứng**: kiểm tra runtime classpath, đặc biệt nếu dùng `provided`, `runtime` hoặc packaging riêng.
8. **Review thay đổi POM** trước khi commit và cập nhật tài liệu nếu phụ thuộc gây ảnh hưởng lớn tới cách phân phối.

Với những thư viện bắt buộc ở runtime, một build test thành công **chưa chắc đủ** nếu bạn đóng JAR thường rồi chạy trực tiếp không kèm dependencies. Cần kiểm chứng đúng cách ứng dụng sẽ được phân phối/chạy trong môi trường mục tiêu.

## 14. Bài tập tự kiểm tra

1. Viết một `<dependency>` dùng `org.apache.commons:commons-lang3:3.17.0` và giải thích chính xác ý nghĩa của GAV.
2. Với POM demo, hãy nêu hai dependency trực tiếp và scope của từng thư viện. Vì sao JUnit không nên xuất hiện trên main/runtime classpath của ứng dụng?
3. Chạy `mvn clean verify`. Phân biệt nơi lưu `App.class`, `AppTest.class` và JAR commons-lang3 mà Maven tải về.
4. Đổi `commons-lang3` từ scope mặc định sang `test` (chỉ trong nhánh thử nghiệm), chạy `mvn compile`, quan sát và giải thích lỗi; khôi phục lại.
5. Chạy `mvn dependency:tree` để tìm phụ thuộc trực tiếp và phụ thuộc bắc cầu của JUnit Jupiter.
6. Di chuyển version commons-lang3 vào `dependencyManagement` rồi bỏ version ở khai báo trực tiếp. Chứng minh vẫn build được. Sau đó xóa khai báo trực tiếp, giải thích vì sao mã ứng dụng không còn thấy `StringUtils`.
7. Giả sử một dependency trực tiếp A có nhánh bắc cầu B và bạn thêm exclusion B vào A. Nếu một nhánh trực tiếp C khác cũng phụ thuộc B, B có thể vẫn xuất hiện không? Vì sao?
8. So sánh `optional=true` với `scope=test` và giải thích chúng giải quyết hai bài toán khác nhau.
9. Một thành viên chỉ nhận được `commons-lang3-3.17.0-sources.jar` mà không biên dịch được mã. Họ đã hiểu sai về `classifier` và artifact ở điểm nào?
10. Khi cần một phiên bản ổn định trên CI, vì sao nên tránh những cách chọn version không kiểm soát và không để `systemPath` trỏ tới thư viện chỉ tồn tại trên máy cá nhân?

## 15. Kết luận và tài liệu chính thức

Một dependency Maven bình thường có cấu trúc `<dependencies><dependency>...`. Hãy ghi nhớ:

- **GAV** mô tả artifact cần lấy; **type/classifier** có thể phân biệt biến thể.
- **Scope** quyết định nơi dependency có mặt; **optional/exclusions** kiểm soát một phần hành vi bắc cầu.
- **dependencies** thực sự thêm thư viện; **dependencyManagement/BOM** giúp quản lý phiên bản, nhưng không tự thêm classpath.
- Maven dựa trên POM metadata, local/remote repositories và dependency graph để phân giải; kiểm tra `dependency:tree` khi kết quả không như kỳ vọng.
- Đừng coi một JAR trong `target/` đã tự chứa toàn bộ dependencies: đóng gói và tạo runtime classpath là trách nhiệm cần xác nhận riêng.

Tài liệu tham khảo:
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference, Dependencies](https://maven.apache.org/pom.html#dependencies)
- [Apache Maven — Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Apache Maven — Guide to Using BOMs](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html#importing-dependencies)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
