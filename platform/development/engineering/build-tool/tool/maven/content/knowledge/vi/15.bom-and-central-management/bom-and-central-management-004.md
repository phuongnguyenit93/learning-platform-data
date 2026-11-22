# BOM là gì và cách nhập bằng type=pom, scope=import trong Maven

## 1. BOM giải quyết vấn đề gì?

Một dự án Java thường cần nhiều thư viện liên quan: chẳng hạn, Jackson Databind sử dụng Jackson Core/Annotations, còn JUnit Jupiter có các thành phần thuộc JUnit Platform. Khi mỗi module tự gõ version cho từng dependency, rất dễ xảy ra tình trạng các thư viện chung hệ sinh thái không tương thích nhau, đặc biệt khi nhóm nâng phiên bản từng phần.

**BOM (Bill of Materials)** trong Maven là một **artifact dạng POM** cung cấp tập các khai báo **dependency management** để các dự án chọn phiên bản phối hợp. Một BOM thông thường có `<packaging>pom</packaging>` và `<dependencyManagement>` chứa những phiên bản thư viện được quản lý.

Nó giống một danh mục:

> Khi dự án cần artifact X, hãy dùng version Y — nhưng chỉ khi dự án thật sự khai báo hoặc nhận X qua dependency graph.

Vì vậy, **import BOM không làm Maven tự đưa tất cả thư viện được BOM liệt kê vào classpath**. Nó quản lý phiên bản/cấu hình dependency, còn `<dependencies>` mới khai báo những thư viện mà dự án cần.

```text
                            pom.xml
                               |
             +-----------------+-----------------+
             |                                   |
     dependencyManagement                   dependencies
        import BOM                          (thực sử dụng)
             |                                   |
     Jackson BOM + JUnit BOM         jackson-databind, junit-jupiter
             |                                   |
      version được quản lý ----------------------+
                                                 |
                                        Maven dependency graph
                                                 |
                                 compile / test / runtime classpath
```

Trong bài này bạn sẽ biết BOM là gì, cú pháp **`<type>pom</type>` + `<scope>import</scope>`, sự khác nhau giữa BOM, parent POM và dependency thường, quy tắc ưu tiên, và cách kiểm tra bằng một dự án Java 17 dùng Jackson và JUnit 5.

## 2. BOM vẫn là artifact Maven có tọa độ

Maven xác định artifact bằng tọa độ cơ bản:

```text
groupId:artifactId:version
com.fasterxml.jackson:jackson-bom:2.18.2
org.junit:junit-bom:5.11.4
```

Hai dòng cuối là những BOM công khai thường dùng cho Jackson và JUnit. Một artifact BOM chứa **POM metadata**, không phải JAR chứa API để `import` trong Java.

Để hình dung, đây là ví dụ **POM BOM nội bộ hoàn chỉnh về cú pháp** (tọa độ `dev.example:example-bom:1.0.0` là giả định; cần tự cài/xuất bản mới dùng được):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>example-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.17.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

POM này **quản lý version Commons Lang**, nhưng không nói BOM cần tải Commons Lang để chạy. Trong BOM, danh sách ở `dependencyManagement` là quy tắc quản lý, không phải danh sách dependency runtime của chính BOM.

Một BOM có thể chứa nhiều managed dependencies với version, scope và những thuộc tính quản lý được Maven hỗ trợ. Từng BOM được phát hành ở một version xác định; để tăng tính tái lập, dự án tiêu thụ nên ghim BOM version có chủ đích.

## 3. Cú pháp đúng để nhập BOM

Đây là phần quan trọng nhất của bài. Trong POM ứng dụng, bạn phải đặt dependency **đại diện cho BOM** bên trong **`<dependencyManagement><dependencies>`**, không phải trong `<dependencies>` trực tiếp của ứng dụng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.18.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là đoạn nằm dưới `<project>`, không phải một tệp POM độc lập.

Các trường:

| Trường | Giá trị trong ví dụ | Tác dụng |
| --- | --- | --- |
| `groupId` | `com.fasterxml.jackson` | Nhóm phát hành BOM |
| `artifactId` | `jackson-bom` | Tên artifact BOM |
| `version` | `2.18.2` | Chọn phiên bản BOM |
| `type` | **`pom`** | Maven phân giải artifact kiểu POM |
| `scope` | **`import`** | Nhập các mục dependency management từ BOM |

**Giới hạn của scope import:** nó chỉ có ý nghĩa **trong `dependencyManagement`** và **cho dependency kiểu `pom`**. Không gắn `scope=import` vào một JAR thông thường trong `<dependencies>` rồi kỳ vọng Maven “thêm toàn bộ dependencies” vào dự án.

Maven xử lý BOM tại bước xây dựng mô hình dependency management. Khi sau đó gặp một dependency cùng key được quản lý, Maven có thể cung cấp version từ BOM mà dependency trực tiếp không cần lặp lại.

## 4. Import BOM không giống khai báo dependency thật

Giả sử bạn import Jackson BOM như trên và viết:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Khi đó dự án **thật sự dùng** `jackson-databind`. Vì version của artifact này đã được Jackson BOM quản lý, phần dependency trực tiếp có thể **bỏ `<version>`**.

Nếu **xóa** đoạn `<dependency>` trực tiếp đó mà **chỉ giữ import BOM**, mã gọi `com.fasterxml.jackson.databind.ObjectMapper` sẽ **không tự thấy Jackson Databind** trên compile classpath. BOM không phải cách thay một danh sách dependencies.

So sánh:

| Phần trong POM | Vai trò |
| --- | --- |
| `<dependencies>` | Khai báo artifact thực sự được đưa vào dependency graph |
| `<dependencyManagement>` | Quản lý version và thông tin mặc định cho dependencies |
| Imported BOM trong dependencyManagement | Nạp một tập managed dependencies từ POM bên ngoài |
| `<build><plugins>` | Khai báo công cụ build, không phải dependencies của mã Java |

Một BOM có thể quản lý hàng trăm artifact, nhưng Maven **không tải tất cả** chỉ vì bạn import BOM. Nó chỉ phân giải những artifact mà graph phụ thuộc thực sự yêu cầu.

## 5. Import nhiều BOM trong một POM

Một dự án có thể nhập **nhiều BOM** cùng lúc. Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.18.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Jackson BOM quản lý phiên bản hệ sinh thái Jackson, JUnit BOM quản lý phiên bản hệ sinh thái JUnit. Các managed entries được Maven đưa vào mô hình dependency management hiệu lực; sau đó module vẫn phải khai báo dependency muốn dùng.

Ví dụ:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Cả hai mục này không ghi version, nhưng **scope của JUnit là `test`** vì chỉ được dùng trong mã kiểm thử. Import BOM với `scope=import` không tự biến JUnit Jupiter thành dependency test; **scope import** và **scope test** là hai khái niệm khác nhau.

## 6. Dự án thực hành hoàn chỉnh: Java 17, Jackson và JUnit 5

Ta làm một chương trình tạo JSON để quan sát trực tiếp cách Maven nhận version từ BOM mà vẫn phân biệt dependencies phục vụ mã chính và test.

### 6.1. Cấu trúc thư mục

```text
bom-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/course/
    │       ├── JsonService.java
    │       └── App.java
    └── test/
        └── java/dev/course/
            └── JsonServiceTest.java
```

Điều kiện: JDK 17+, Maven 3.9.x hoặc bản Maven tương thích và quyền truy cập một repository chứa các artifact công khai. Các version trong ví dụ đã được cố định cho mục đích học, **không phải khẳng định phiên bản mới nhất**.

### 6.2. pom.xml đầy đủ

Tạo `bom-demo/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>bom-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson</groupId>
                <artifactId>jackson-bom</artifactId>
                <version>2.18.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
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
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
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

Những điểm cần tự tìm trong POM:

1. `jackson-bom` và `junit-bom` chỉ xuất hiện như **import entries trong dependencyManagement**.
2. `jackson-databind` là dependency trực tiếp scope `compile` mặc định, **không ghi version**.
3. `junit-jupiter` là dependency trực tiếp scope `test`, **không ghi version**.
4. Các Maven plugin vẫn **ghi version riêng**. Import BOM không dùng để nhập pluginManagement của BOM.

Nếu sửa `type` hoặc `scope` ở import thành giá trị khác, Maven có thể không quản lý version và báo lỗi thiếu version ở dependency trực tiếp.

### 6.3. Mã Java sử dụng Jackson Databind

Tạo `src/main/java/dev/course/JsonService.java`:

```java
package dev.course;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;
import java.util.TreeMap;

public final class JsonService {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonService() {
    }

    public static String toJson(String name)
            throws JsonProcessingException {
        Map<String, Object> values = new TreeMap<>();
        values.put("level", 17);
        values.put("name", name.strip());
        return MAPPER.writeValueAsString(values);
    }

    public static String readName(String json)
            throws JsonProcessingException {
        return MAPPER.readTree(json).path("name").asText();
    }
}
```

Ví dụ dùng `TreeMap` để các khóa JSON được sắp xếp có thể dự đoán: `level` đứng trước `name`. Nhờ vậy có thể so sánh stdout **chính xác**. `ObjectMapper` thuộc Jackson Databind, còn `JsonProcessingException` nằm trong Jackson Core; các artifact Jackson liên quan được phân giải qua graph dependency, với các version quản lý phù hợp.

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println(JsonService.toJson(" Lan "));
    }
}
```

Lớp `App` là điểm vào chương trình. Nó dùng Java 17 và gọi đúng phương thức của `JsonService`.

### 6.4. Mã kiểm thử JUnit Jupiter

Tạo `src/test/java/dev/course/JsonServiceTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JsonServiceTest {
    @Test
    void serializesStableJson() throws Exception {
        assertEquals(
                "{\"level\":17,\"name\":\"Lan\"}",
                JsonService.toJson(" Lan "));
    }

    @Test
    void readsNameFromJson() throws Exception {
        assertEquals(
                "Lan",
                JsonService.readName("{\"name\":\"Lan\"}"));
    }

    @Test
    void returnsEmptyForMissingName() throws Exception {
        assertEquals("", JsonService.readName("{}"));
    }
}
```

Ba test dùng API `@Test` và `assertEquals` từ JUnit Jupiter. Với `scope=test`, JUnit được đưa vào classpath kiểm thử, không trở thành dependency runtime thông thường của mã chính.

### 6.5. Build và kiểm tra đầu ra

Từ thư mục `bom-demo`:

```bash
mvn -version
mvn clean verify
mvn -q -Dexec.mainClass=dev.course.App exec:java
```

Khi Maven tải được dependencies/plugins và JDK tương thích, `clean verify` biên dịch mã, chạy **3 test** thành công và đóng gói dự án. Các đường dẫn điển hình:

```text
target/classes/dev/course/JsonService.class
target/classes/dev/course/App.class
target/test-classes/dev/course/JsonServiceTest.class
target/surefire-reports/
target/bom-demo-1.0.0-SNAPSHOT.jar
```

**Stdout do chương trình Java in ra chính xác:**

```json
{"level":17,"name":"Lan"}
```

Lệnh `exec:java` dùng runtime classpath của Maven. Nếu gọi `java -cp target/classes dev.course.App` mà thiếu Jackson JAR, bạn có thể gặp `NoClassDefFoundError`; đó là lỗi classpath khi khởi chạy JAR mỏng, không chứng minh BOM sai. Bài thực hành này không cấu hình fat JAR.

Trên Windows PowerShell, có thể chạy:

```powershell
mvn -version
mvn clean verify
mvn '-Dexec.mainClass=dev.course.App' -q exec:java
```

Nếu dự án có Maven Wrapper, dùng `./mvnw` hoặc `mvnw.cmd` tương ứng, nhưng chỉ khi wrapper thật sự được cung cấp.

## 7. Quan sát phiên bản hiệu lực và cây phụ thuộc

Hai công cụ Maven giúp bạn kiểm chứng BOM đã hoạt động:

### 7.1. Effective POM

```bash
mvn help:effective-pom
```

Help Plugin cho thấy model sau khi tổng hợp parent, profiles và dependency management. Trong mô hình hiệu lực, kiểm tra `jackson-databind` và `junit-jupiter` có nguồn version phù hợp từ imported BOM.

Lệnh này cần có Maven Help Plugin; nếu cache chưa có, Maven có thể phải tải về. Không xem việc một dòng XML xuất hiện trong effective POM là bằng chứng duy nhất về classpath chạy: hãy kết hợp kiểm tra graph thật.

### 7.2. Dependency tree

```bash
mvn dependency:tree
```

Các node trực tiếp quan trọng ở dự án mẫu sẽ có tọa độ như:

```text
dev.course:bom-demo:jar:1.0.0-SNAPSHOT
+- com.fasterxml.jackson.core:jackson-databind:jar:2.18.2:compile
\\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
```

**Cây trên chỉ là hình rút gọn**, không phải output đầy đủ của Maven: còn các dependencies bắc cầu từ Jackson và JUnit. Thứ tự in và ký tự hiển thị có thể phụ thuộc phiên bản plugin.

Có thể lọc:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
mvn dependency:tree -Dincludes=org.junit.jupiter
```

Lệnh lọc chỉ hiện một phần graph. Khi cần debug xung đột version, đọc thêm cây đầy đủ để thấy các nhánh khác và scope.

**Kết luận từ thực hành:** Jackson/JUnit BOM quản lý version; các dependency trực tiếp xác định thư viện thực tế. Build thành công và dependency tree phù hợp là bằng chứng thực tế hơn việc chỉ nhìn tên BOM trong POM.

## 8. Khi nào version trong dependency ghi đè BOM?

Một mục dependency trực tiếp có thể ghi rõ version:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.18.2</version>
</dependency>
```

Khi version được ghi tường minh như vậy, dự án yêu cầu version đó cho dependency trực tiếp. Không nên giả định imported BOM sẽ tự ghi đè version mà bạn vừa gõ.

Nếu muốn BOM là nguồn quản lý, **bỏ thẻ `<version>`** ở dependency tương ứng. Đó là cách dùng rõ ràng nhất.

Ngoài ra, có thể đặt một mục quản lý riêng tại POM hiện tại:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.18.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <!-- Ngoại lệ quản lý tường minh ở POM đang dùng -->
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn này chỉ là ví dụ về **cấu trúc override**, trong đó version minh họa trùng với BOM nên chưa tạo khác biệt thực tế. Khi có nhu cầu override, thay bằng một version hợp lệ **đã kiểm tra tương thích**. Không nên override riêng Databind rồi quên Jackson Core/Annotations nếu các phiên bản cần đồng bộ.

Nguyên tắc: dependency version trực tiếp, dependency management tường minh, parent và imported BOM đều có thể ảnh hưởng lựa chọn cuối. Chỉ kiểm chứng chính xác bằng **effective POM và dependency tree**, không bằng phỏng đoán.

## 9. Nếu import hai BOM quản lý cùng một artifact thì sao?

Một hệ thống lớn có thể import BOM A và BOM B; cả hai đều quản lý cùng dependency key, nhưng với phiên bản khác nhau. Trong Maven, **thứ tự import có ý nghĩa**: với các mục nhập trùng nhau không có override tường minh, BOM được import trước thường được dùng cho dependency key trùng.

Ví dụ minh họa cú pháp với **tọa độ giả định**, không phải BOM được cung cấp sẵn:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>bom-a</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>bom-b</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Giả sử cả hai cùng quản lý `com.example:shared-lib`. Thứ tự import có thể quyết định version được dùng nếu không khai báo override cụ thể. **Không chạy nguyên đoạn này** khi chưa có các artifact BOM giả định trên repository.

Cần hiểu thêm:

- Managed dependency key không chỉ dựa trên tên viết tắt GAV trong mọi tình huống: Maven còn xét `type` và `classifier` khi phân biệt các mục phù hợp.
- Một entry quản lý rõ ràng trong POM hiện tại có thể override thông tin nhập từ BOM cho cùng key.
- POM cha có thể cung cấp dependencyManagement; mô hình kế thừa giữa cha và con cũng có luật ưu tiên.
- Khi dependency graph có version xung đột, Maven áp dụng dependency mediation và những mục quản lý hiệu lực; không phải luôn chọn version lớn nhất.

Nếu gặp va chạm, hãy document quyết định phiên bản, kiểm tra cây dependency, chạy test và tránh âm thầm dựa vào thứ tự BOM không ai trong nhóm biết.

## 10. BOM và parent POM khác nhau ở đâu?

| Đặc điểm | Parent POM | Imported BOM |
| --- | --- | --- |
| Cách sử dụng | `<parent>...</parent>` | dependency import trong `dependencyManagement` |
| Số lượng | Một parent trực tiếp cho một dự án | Có thể import nhiều BOM |
| Dependency management | Có thể kế thừa từ parent | Mục đích chính |
| Plugin management/build | Có thể kế thừa/ghép theo luật Maven | **Không nhập toàn bộ** plugin/build từ BOM |
| Properties của dự án | Có thể kế thừa từ parent | Không nhập tự do toàn bộ properties như parent |
| Dùng cùng nhau | Có | Có |

Một POM có thể kế thừa parent của tổ chức để dùng compiler, test plugin và quy tắc build chung, đồng thời import Jackson và JUnit BOM để lấy versions của thư viện.

Ví dụ parent (đoạn minh họa, chỉ hợp lệ khi artifact parent tồn tại):

```xml
<parent>
    <groupId>dev.company</groupId>
    <artifactId>build-parent</artifactId>
    <version>1.0.0</version>
</parent>
```

Imported BOM không đồng nghĩa dự án đang kế thừa các profile, plugin executions, repositories hay properties từ POM nguồn. Đây là khác biệt thiết yếu để hiểu tại sao **nhập BOM của một framework không tự cấu hình toàn bộ công cụ build của framework đó**.

## 11. BOM không thay thế pluginManagement

Trong Maven, những artifact như `maven-compiler-plugin`, `maven-surefire-plugin` hoặc `maven-shade-plugin` thuộc hệ plugin. Một BOM import qua `dependencyManagement` **không tự quản lý version của các Maven plugins** trong `<build>`.

Ví dụ một plugin riêng trong POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
</plugin>
```

Đặt đoạn này trong `<build><plugins>`, không đặt trong danh sách dependency import. Nếu nhóm muốn quản lý plugin versions tập trung, thường sử dụng parent POM với `<pluginManagement>` hoặc cấu hình build tương ứng.

Tương tự, BOM không tự tạo một execution để chạy integration test, không chọn JDK đang chạy Maven và không thay `settings.xml`, local repository hoặc mirror.

## 12. BOM và các dependency bắc cầu

Các dependencies có thể kéo theo thư viện khác. Ví dụ khái niệm:

```text
bom-demo
  |
  +-- jackson-databind
  |      +-- jackson-core
  |      +-- jackson-annotations
  |
  +-- junit-jupiter [test]
         +-- JUnit Jupiter API/Engine và thành phần liên quan
```

Maven đọc metadata POM của dependencies để giải quyết graph. Khi artifact bắc cầu trùng một mục quản lý trong dependencyManagement đã nhập từ BOM, version được quản lý có thể ảnh hưởng kết quả.

Tuy nhiên, **BOM không phải lockfile tuyệt đối**. Kết quả còn phụ thuộc:

- Những dependencies thật sự được khai báo.
- Parent POM, profiles và quản lý version tường minh.
- Scope, optional và exclusions.
- Các phiên bản/metadata có trong repository.
- Luật dependency mediation của Maven.

Không nên mặc định một BOM giải quyết được mọi `NoSuchMethodError` do mismatch version, nhất là khi nhóm override một phần của hệ sinh thái. Muốn xác minh, hãy xem `dependency:tree` và chạy kiểm thử/integration tests với môi trường thực.

## 13. Ví dụ tổ chức nội bộ nhiều module

Giả sử một tổ chức có ba dự án `api-service`, `batch-worker` và `reporting-tool`. Nếu cả ba cần cùng phiên bản Jackson và JUnit, họ có thể tạo một **company BOM** để quản lý version chung.

Tên tọa độ minh họa:

```text
dev.company:company-bom:1.0.0
```

Trong company BOM, đặt những managed dependencies mà công ty cần thống nhất; sau đó cài/publish POM BOM vào repository phù hợp. Các dự án sử dụng:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.company</groupId>
            <artifactId>company-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Những ví dụ `dev.company` là **tọa độ giả định**, không có nghĩa repo công khai chứa artifact này. Nếu company BOM chưa được cài/xuất bản ở local/remote repository mà Maven truy cập được, import sẽ thất bại khi Maven tìm POM.

Mỗi dự án vẫn khai báo riêng các dependency nó cần. Khi nhóm phát hành version mới của company BOM, từng dự án nâng version BOM theo quy trình review và chạy tests; điều này cho phép các dự án cùng có một tập phiên bản được quản lý nhưng không buộc dùng mọi thư viện.

**Không sửa đè cùng một version release BOM đã được sử dụng rộng rãi.** Phát hành version mới giúp truy vết và rollback rõ ràng hơn.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Maven báo missing version ở `jackson-databind` | Chưa import BOM đúng, version BOM sai hoặc artifact không có mục được quản lý | Kiểm tra effective POM và GAV |
| Import BOM trong `<dependencies>` thường | Đặt sai vị trí `dependencyManagement` | Chuyển vào đúng khu vực, dùng `type=pom` + `scope=import` |
| Có `type=pom` nhưng vẫn thiếu version | Quên `scope=import` | Thêm đúng scope import |
| Mã không compile dù đã import Jackson BOM | Chỉ quản lý version nhưng chưa thêm dependency | Khai báo `jackson-databind` trong `<dependencies>` |
| Test không nhận được JUnit dù có JUnit BOM | Thiếu `junit-jupiter` hoặc scope sai | Thêm dependency với `scope=test` |
| JUnit bị đưa vào main runtime graph | Khai báo JUnit scope mặc định `compile` | Đổi scope về `test` khi chỉ dùng cho test |
| Version được chọn khác BOM | Có override trực tiếp, quản lý tường minh, nhiều BOM hoặc parent | Xem dependency tree và effective POM |
| Maven không tải được BOM | Sai artifact/version, mirror/repository hoặc quyền mạng | Kiểm tra repository và `settings.xml` |
| Maven plugin dùng version lạ | BOM không nhập pluginManagement | Ghim plugin trong POM/parent |
| Chạy Java thiếu Jackson dù build pass | JAR mỏng không tự chứa runtime dependencies | Dùng classpath đúng hoặc packaging phù hợp |
| Nâng BOM gây lỗi linkage khi chạy | Artifact liên quan không tương thích hoặc override thiếu kiểm soát | Xem graph, giữ version đồng bộ và chạy CI |
| Module con không nhận JUnit chỉ vì parent có BOM | `dependencyManagement` không tự thêm dependency | Khai báo JUnit tại module con nếu cần |

Khi gặp lỗi, đừng “chữa” bằng cách chép thêm version thủ công vào mọi dependency. Điều đó có thể che cấu hình import sai và làm mất lợi ích quản lý chung của BOM.

## 15. Checklist khi thêm hoặc nâng BOM

1. Xác định đúng GAV và packaging POM của BOM từ nguồn đáng tin.
2. Ghim version BOM cụ thể, không dựa vào version động khó tái lập.
3. Đặt nó **trong `dependencyManagement`** với **`type=pom`** và **`scope=import`**.
4. Khai báo đúng dependencies ứng dụng ở `<dependencies>`, bỏ version khi BOM quản lý và giữ scope phù hợp.
5. Ghim version plugins quan trọng ở POM hoặc parent.
6. Chạy `mvn clean verify`; xác nhận test thực sự chạy, không bị skip ngoài ý muốn.
7. Xem `mvn help:effective-pom` và `mvn dependency:tree` để phát hiện override, trùng version hoặc thiếu dependency.
8. Chạy ứng dụng bằng runtime classpath/packaging giống môi trường thật.
9. Kiểm tra bảo mật, license và tương thích trước khi nâng BOM hoặc publish artifact.
10. Review thay đổi POM và lưu lại version BOM được chọn để rollback khi cần.

## 16. Bài tập tự kiểm tra

1. Giải thích BOM (Bill of Materials) là gì và vì sao BOM khác với một dependency JAR thông thường.
2. Viết cú pháp import đúng cho `org.junit:junit-bom:5.11.4`; chỉ ra vị trí chính xác của `type=pom` và `scope=import`.
3. Với POM `bom-demo`, tại sao `jackson-databind` và `junit-jupiter` không cần viết version trực tiếp?
4. Chạy `mvn clean verify` và `mvn -q -Dexec.mainClass=dev.course.App exec:java`; kiểm chứng ba test và dòng JSON `{"level":17,"name":"Lan"}`.
5. Giữ JUnit BOM nhưng xóa dependency `junit-jupiter` khỏi `<dependencies>`. Vì sao JUnit tests không compile? Khôi phục dependency sau thí nghiệm.
6. Chạy `mvn dependency:tree` để tìm version thực của Jackson Databind, Jackson Core và JUnit Jupiter.
7. Một developer đặt BOM ngay trong `<dependencies>` với `type=pom` nhưng không có `scope=import`. Vì sao các dependencies khác vẫn báo thiếu version?
8. Phân biệt parent POM và imported BOM. Loại nào có thể quản lý plugins và build cấu hình thông qua kế thừa?
9. Nếu BOM A và BOM B quản lý cùng một artifact nhưng ở hai version, thứ tự import thường ảnh hưởng ra sao? Bạn xác minh lựa chọn cuối bằng lệnh nào?
10. Một dependency trực tiếp ghi version cụ thể khác version BOM. Khi nào cần giữ version tường minh, và nguy cơ không tương thích là gì?
11. Một module có company BOM nhưng không tìm thấy artifact company-bom. Bạn cần kiểm tra tọa độ, local repository, remote repository hay quyền truy cập nào?
12. Vì sao không nên phát hành lại BOM release version đã có nội dung khác? Phương án nâng version và rollback là gì?

## 17. Kết luận

**BOM giúp nhóm quản lý một tập phiên bản dependency nhất quán; nó không tự thêm thư viện và không tự cấu hình toàn bộ quá trình build.** Muốn sử dụng đúng, hãy import BOM **trong `dependencyManagement`** với **`<type>pom</type>` và `<scope>import</scope>`**, sau đó khai báo chính xác artifact cần dùng ở `<dependencies>`.

Một dự án có thể kết hợp parent POM, nhiều BOM và dependency management tường minh. Khi xung đột, đừng dựa vào suy đoán: đối chiếu **effective POM**, **dependency tree**, kết quả kiểm thử và runtime thật.

## 18. Tài liệu tham khảo

- [Apache Maven — Introduction to the Dependency Mechanism, Importing Dependencies](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html#importing-dependencies)
- [Apache Maven — POM Reference, Dependency Management](https://maven.apache.org/pom.html#dependency-management)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Apache Maven Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
- [JUnit User Guide, Maven Build Support](https://junit.org/junit5/docs/current/user-guide/#running-tests-build-maven)
