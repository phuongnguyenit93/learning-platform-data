# Phân biệt xung đột phiên bản với xung đột lớp hoặc tài nguyên trong Maven

Khi ứng dụng Java báo lỗi phụ thuộc, rất dễ gọi chung mọi vấn đề là **“dependency conflict”**. Thực tế, cần phân biệt ít nhất ba hiện tượng khác nhau:

1. **Xung đột phiên bản (version conflict):** nhiều đường trong đồ thị Maven yêu cầu **các phiên bản khác nhau của cùng một artifact**; Maven phải phân giải để chọn một phiên bản hiệu lực.
2. **Xung đột lớp (duplicate class / class collision):** hai hoặc nhiều artifact hoặc classpath entries **chứa cùng tên lớp Java đầy đủ** (fully qualified class name, FQCN), chẳng hạn `vn.example.api.User`. Maven có thể chọn phiên bản của mỗi artifact hoàn toàn hợp lệ mà JVM vẫn gặp lớp trùng.
3. **Xung đột tài nguyên (duplicate resource / resource collision):** hai hoặc nhiều JAR, thư mục classes hoặc classloaders **cùng cung cấp một resource path**, chẳng hạn `config.properties` hay `META-INF/services/javax.annotation.processing.Processor`. Resource nào được nhìn thấy hoặc cách chúng được hợp nhất phụ thuộc API và công cụ đóng gói.

**Điểm quan trọng:** Maven thường giải quyết xung đột **tọa độ artifact/phiên bản** ở dependency graph. Maven core **không tự bảo đảm** rằng tập JAR sau khi resolve không chứa các lớp hoặc tài nguyên trùng tên. Ngược lại, chỉ thấy `NoSuchMethodError` cũng chưa đủ để kết luận có duplicate class: lỗi tương thích nhị phân có thể xuất phát từ một phiên bản đã được Maven chọn khác với phiên bản mã được biên dịch.

## 1. Bảng nhận diện ba loại xung đột

| Góc nhìn | Xung đột phiên bản | Xung đột lớp | Xung đột tài nguyên |
| --- | --- | --- | --- |
| Đối tượng trùng/đụng | **Cùng dependency artifact** nhưng nhiều version được yêu cầu | **Cùng FQCN** được đóng trong nhiều classpath entries/artifacts | **Cùng resource path** có nhiều bản |
| Ví dụ | `com.example:api:1.0` và `com.example:api:2.0` | `alpha.jar` và `beta.jar` cùng có `vn/demo/Shared.class` | Hai JAR đều có `banner.txt` |
| Maven mediation có xử lý? | **Có**, theo dependency graph và dependency management | **Không tự phát hiện/giải quyết theo tên class** | **Không tự hợp nhất đúng ý nghĩa** |
| Dấu hiệu chính | Dependency tree thể hiện version được chọn hoặc version bị loại vì conflict | Hai JAR chứa class giống nhau; runtime có thể dùng bản không mong muốn | `getResource` chọn một bản, `getResources` có thể thấy nhiều bản; merge có thể mất dữ liệu |
| Lỗi có thể thấy | `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` do khác phiên bản/thiếu API | `NoSuchMethodError`, hành vi khác, `LinkageError` hoặc lỗi tùy classloader | Sai cấu hình, thiếu provider `ServiceLoader`, metadata bị ghi đè |
| Cách điều tra | `dependency:tree`, `dependencyManagement`, BOM, effective POM | `jar tf`, classpath thật, vị trí class được load, duplicate-class scanner | `jar tf`, `ClassLoader.getResources`, cấu hình shade/assembly |
| Hướng sửa | Chốt phiên bản tương thích, BOM/management, loại bỏ đường sai | Loại bớt/đổi dependency, sửa packaging, relocation nếu thật sự cần | Đổi tên resource, hợp nhất có chủ đích, transformer cho metadata đặc biệt |

**Một build có thể gặp đồng thời cả ba vấn đề.** Ví dụ Maven chọn `api:2.0`, nhưng hai vendor JAR khác tọa độ lại nhúng riêng lớp `com.example.api.Client` cũ, đồng thời cùng chứa `META-INF/services/...`. Sửa dependency version chưa chắc sửa được duplicate class hoặc service metadata.

## 2. Hiểu xung đột phiên bản theo Maven Resolver

Maven đọc `<dependencies>` của project và các POM bắc cầu để xây dựng dependency graph. Xung đột phiên bản thường xảy ra khi **cùng một artifact identity** được các nhánh yêu cầu ở version khác nhau.

Trong phạm vi dependency Java thông thường, artifact được xác định bởi các thành phần như `groupId`, `artifactId`, `type` và `classifier`; **version** là phần Maven cần chọn khi có nhiều ứng viên xung đột. Hai artifact có `groupId:artifactId` khác nhau **không** bị Maven xem là hai phiên bản của cùng artifact chỉ vì chúng cùng chứa lớp Java tên giống nhau.

### 2.1. Nearest definition: đường gần nhất thường thắng

Đồ thị ví dụ khái niệm (các tên `lib-a`/`lib-b`/`shared-api` là artifact giả định):

```text
my-app
├── lib-a:1.0
│   └── shared-api:1.0
└── lib-b:1.0
    └── shared-api:2.0
```

`shared-api` được yêu cầu tại hai nhánh có **cùng độ sâu**. Theo dependency mediation, Maven ưu tiên khai báo được gặp trước ở mức sâu bằng nhau (thường theo thứ tự dependency branch trong POM). Trong hình trên, nếu `lib-a` được khai báo trước, `shared-api:1.0` có thể được chọn.

Nếu đồ thị là:

```text
my-app
├── lib-a:1.0
│   └── lib-c:1.0
│       └── shared-api:1.0
└── lib-b:1.0
    └── shared-api:2.0
```

`shared-api:2.0` gần root hơn và sẽ được ưu tiên trong trường hợp mediation thông thường. Đây là quy tắc **độ sâu**, không phải “version mới nhất luôn thắng”. Scope, exclusions, optional dependencies, dependency management, graph transformation và những yếu tố khác cũng ảnh hưởng tập dependencies thực tế.

### 2.2. Kiểm soát version bằng dependencyManagement

Trong POM của ứng dụng, có thể chủ động quản lý version:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-api</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn POM**, không phải file XML độc lập; tên tọa độ chỉ mang tính minh họa. Management giúp kiểm soát phiên bản khi dependency tương ứng được sử dụng; nó **không tự thêm** dependency đó vào graph. Có thể import BOM phù hợp để quản lý một tập version nhất quán.

Cũng có thể khai báo dependency trực tiếp với version cụ thể trong `<dependencies>` để đường đi ở root rõ ràng. Nhưng **không nên ép phiên bản chỉ vì số version lớn hơn**: nếu `lib-a` được biên dịch dựa trên API cũ đã bị xóa trong bản mới, build/runtime vẫn có thể lỗi. Quản lý version giải quyết **lựa chọn artifact**, không bảo đảm tương thích nhị phân hay hành vi.

### 2.3. Xung đột version không nhất thiết tạo hai JAR trùng

Với dependency mediation thông thường, Maven chọn một phiên bản hiệu lực cho cùng artifact identity trong classpath được resolve; hai nhánh yêu cầu khác version **không mặc nhiên** làm cả hai JAR cùng nằm trên classpath. Đây là lý do dùng dependency tree để xem **bản được chọn**, thay vì chỉ tìm mọi version nhắc đến trong POM của các dependency.

Có ngoại lệ ở môi trường **không chỉ dùng một Maven classpath duy nhất**: plugin classloader riêng, ứng dụng server, deployment WAR/EAR, classpath tự lắp, shading hoặc Java module layer. Phải phân tích classpath/classloader của đúng tiến trình gặp lỗi, không suy từ một dependency tree duy nhất cho mọi bối cảnh.

## 3. Duplicate class: tọa độ khác, tên lớp vẫn trùng

Giả sử project phụ thuộc:

```xml
<dependencies>
    <dependency>
        <groupId>vn.example</groupId>
        <artifactId>alpha-library</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>vn.example</groupId>
        <artifactId>beta-library</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Hai artifact có **artifactId khác nhau**, Maven có thể đưa cả hai vào dependency tree. Nhưng nếu **mỗi JAR cùng chứa**:

```text
demo/shared/Message.class
```

thì có duplicate class. Maven không hiểu ngữ nghĩa bytecode để “chọn bản class đúng nhất” theo tên lớp.

### 3.1. Hậu quả tùy classloader, không luôn là lỗi build

Khi cả hai JAR nằm trong **cùng application classloader**, lớp có cùng binary name thường được lấy từ một classpath entry theo cơ chế tìm kiếm của classloader; bản còn lại có thể không được sử dụng. Thứ tự classpath có thể làm thay đổi lựa chọn trong ví dụ command-line Java tiêu chuẩn.

Một số tình huống:

- Lớp ở `alpha.jar` có method `run()` nhưng bản ở `beta.jar` không có: code biên dịch dựa vào alpha, runtime nạp beta có thể báo `NoSuchMethodError` khi gọi method.
- Hai bản có cùng signature nhưng cách xử lý khác: chương trình **không báo lỗi** mà chạy sai hành vi.
- Hai classloader khác nhau nạp lớp cùng tên: JVM xem identity của class theo **binary name + defining classloader**, nên cast/bridge có thể gặp `ClassCastException` hoặc `LinkageError` dù tên class in ra giống nhau.
- Nếu lập trình dùng Java module path với module declarations, có thể phát sinh vấn đề split package/module resolution **khác** với cách classpath truyền thống xử lý duplicate class. Không nên trộn hai mô hình để kết luận.

**Không phải cứ có duplicate class thì Maven/Javac sẽ tự fail.** Việc compiler chọn lớp nào và runtime chọn lớp nào cần được kiểm chứng theo classpath, classloader và công cụ đóng gói sử dụng.

### 3.2. Các nguồn duplicate class thường gặp

- Hai dependency khác tọa độ nhưng cùng bundle một thư viện nguồn.
- Một thư viện vendor **nhúng (repackage)** các class của dependency khác mà không relocate package.
- JAR “all-in-one”/“fat” và JAR thư viện gốc **cùng** xuất hiện trên classpath.
- Thư mục `target/classes` và JAR cũ đồng thời xuất hiện qua script chạy thủ công.
- Container/app server cung cấp một thư viện riêng, trong khi ứng dụng WAR chứa bản khác.
- Một plugin shading ghép các JAR và cho duplicate entry bị ghi đè hoặc giữ bản không mong muốn.

Trong trường hợp duplicate class, **không có ý nghĩa gì khi chỉ đổi version của một artifact nếu cả hai artifact vẫn chứa tên lớp trùng**. Cần xác định chính xác những file JAR nào mang lớp đó.

## 4. Duplicate resource: cùng đường dẫn file, không nhất thiết trùng class

Resource trong Java có thể là `.properties`, `.xml`, `.json`, template, dữ liệu nội bộ, file license, metadata `META-INF` hoặc mô tả Java service provider.

Ví dụ hai JAR đều chứa:

```text
greeting.txt
META-INF/services/com.example.spi.PaymentProvider
```

Hai file `greeting.txt` có thể hợp lệ nhưng chứa **giá trị khác nhau**. Hai file `META-INF/services/...` lại có thể cần được **tổng hợp danh sách provider**, không thể tùy tiện chọn một rồi bỏ file còn lại.

Trong classpath kiểu truyền thống:

- `ClassLoader.getResource("greeting.txt")` thường trả về URL đầu tiên tìm thấy theo cơ chế classloader, hoặc `null` nếu không có.
- `ClassLoader.getResources("greeting.txt")` có thể trả về **nhiều URL** nếu nhiều JAR cung cấp đường dẫn ấy.
- `Class.getResource("/greeting.txt")` tìm tại root classpath nếu có dấu `/` đầu; không có dấu `/` thì tìm tương đối với package của class.
- Khi JAR được merge bằng Shade/Assembly, policy xử lý resource duplicates **khác** với việc để nhiều JAR độc lập trên runtime classpath.

Các hệ quả thực tế:

| Resource | Rủi ro khi trùng | Hướng xử lý |
| --- | --- | --- |
| `application.properties` hoặc `config.properties` | Ứng dụng lấy nhầm config; từng framework có thứ tự ưu tiên riêng | Đặt namespace/đường dẫn riêng, tài liệu hóa thứ tự nạp, test cấu hình |
| `META-INF/services/<interface>` | ServiceLoader không phát hiện đủ provider sau fat-JAR merge | Merge service descriptors bằng transformer phù hợp, test ServiceLoader |
| `META-INF/spring.factories` hoặc metadata framework | Một phần cấu hình auto-discovery bị mất | Dùng transformer/merge thích hợp với phiên bản framework |
| File i18n cùng tên | Thông điệp locale bị lấy từ JAR không mong muốn | Đặt resource trong namespace module/package |
| `META-INF/LICENSE`, `NOTICE` | Đóng gói mất thông tin bản quyền cần thiết | Xử lý resource metadata đúng chính sách license, không xóa bừa |

**Lưu ý:** Maven dependency mediation không dùng tên resource để quyết định chọn JAR. Hai artifact khác tọa độ với resource trùng vẫn có thể cùng được resolve hoàn toàn hợp lệ.

## 5. Ví dụ đa module Java 17: Maven không giải quyết lớp/resource trùng

Ví dụ sau **chạy được**, không cần thư viện Java bên thứ ba. Nó tạo **hai JAR có tọa độ Maven khác nhau**, mỗi JAR có một lớp cùng FQCN và một resource cùng path. Consumer phụ thuộc cả hai. Sau đó ta tự chọn thứ tự JAR trên classpath lúc chạy để thấy kết quả.

### 5.1. Cấu trúc thư mục

```text
collision-lab/
├── pom.xml
├── alpha-library/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/shared/Message.java
│       └── resources/greeting.txt
├── beta-library/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/shared/Message.java
│       └── resources/greeting.txt
└── consumer/
    ├── pom.xml
    └── src/main/java/demo/app/Main.java
```

### 5.2. POM root: `collision-lab/pom.xml`

Root vừa là parent chung vừa là **aggregator** cho ba module. Không phải mọi parent POM đều là aggregator; ở đây nó kiêm hai vai trò để ví dụ chạy bằng một lệnh.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>collision-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>alpha-library</module>
        <module>beta-library</module>
        <module>consumer</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.3.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

### 5.3. Hai POM library

File `alpha-library/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>collision-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>alpha-library</artifactId>
    <packaging>jar</packaging>
</project>
```

File `beta-library/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>collision-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>beta-library</artifactId>
    <packaging>jar</packaging>
</project>
```

Như vậy alpha và beta khác `artifactId`, dù cùng `groupId` và `version`. Maven xem chúng là **hai dependency khác nhau**; không có “xung đột phiên bản của cùng artifact” để mediation loại bớt một trong hai.

### 5.4. Hai class có cùng FQCN nhưng nội dung khác

File `alpha-library/src/main/java/demo/shared/Message.java`:

```java
package demo.shared;

public final class Message {
    private Message() {
    }

    public static String origin() {
        return "alpha-library";
    }
}
```

File `beta-library/src/main/java/demo/shared/Message.java`:

```java
package demo.shared;

public final class Message {
    private Message() {
    }

    public static String origin() {
        return "beta-library";
    }
}
```

Hai file mã nguồn tồn tại trong **hai Maven module riêng**, nên mỗi module compile thành công. Nhưng hai JAR cùng chứa `demo/shared/Message.class`. Nếu đặt cả hai JAR vào **cùng classpath**, chỉ một định nghĩa `demo.shared.Message` được classloader ứng dụng tiêu chuẩn dùng cho tên lớp đó.

Hai resource:

File `alpha-library/src/main/resources/greeting.txt`:

```text
alpha-resource
```

File `beta-library/src/main/resources/greeting.txt`:

```text
beta-resource
```

Tên đường dẫn root classpath là `greeting.txt` trong **cả hai** JAR. Maven không từ chối hai JAR chỉ vì điều này.

### 5.5. Consumer POM và code đọc lớp/resource

File `consumer/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>collision-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>consumer</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>alpha-library</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>beta-library</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

File `consumer/src/main/java/demo/app/Main.java`:

```java
package demo.app;

import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("demo.shared.Message");
        String source = (String) type.getMethod("origin").invoke(null);
        System.out.println("Class: " + source);

        ClassLoader loader = Main.class.getClassLoader();
        Enumeration<URL> found = loader.getResources("greeting.txt");

        int count = 0;
        while (found.hasMoreElements()) {
            URL url = found.nextElement();
            try (InputStream in = url.openStream()) {
                String value = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8
                ).strip();
                System.out.println("Resource[" + (++count) + "]: " + value);
            }
        }
    }
}
```

`Class.forName` dùng reflection nên code consumer không cần biên dịch tham chiếu trực tiếp tới class `Message` lấy từ alpha hay beta. Code dùng các API Java 17 sẵn có; `getResources` cho phép quan sát nhiều bản resource cùng tên.

### 5.6. Build với Maven, kiểm tra dependency tree và JAR

Từ thư mục `collision-lab`, với JDK 17+, Maven 3.9.x tương thích và các Maven plugins được tải sẵn hoặc có mạng:

```bash
java -version
mvn --version
mvn -B clean install
mvn -pl consumer dependency:tree -Dincludes=vn.example
```

`mvn clean install` build reactor theo phụ thuộc module và cài artifacts vào **local repository** để lệnh kiểm tra riêng consumer có thể resolve dễ dàng. Lệnh `dependency:tree` có thể phải tải Maven Dependency Plugin trong lần đầu. Thông thường cây phụ thuộc của consumer sẽ chứa **cả** `vn.example:alpha-library:jar:1.0.0` và `vn.example:beta-library:jar:1.0.0`.

Kiểm tra file JAR:

```bash
jar tf alpha-library/target/alpha-library-1.0.0.jar
jar tf beta-library/target/beta-library-1.0.0.jar
```

Trong output của **cả hai** lệnh phải có ít nhất:

```text
demo/shared/Message.class
greeting.txt
```

Hai dòng trên là mục cần tìm, **không** phải toàn bộ stdout hay cam kết thứ tự của `jar tf`. Mỗi JAR còn chứa metadata `META-INF`.

### 5.7. Chạy với thứ tự classpath alpha trước

Linux/macOS, đứng ở `collision-lab`:

```bash
java -cp "consumer/target/consumer-1.0.0.jar:alpha-library/target/alpha-library-1.0.0.jar:beta-library/target/beta-library-1.0.0.jar" demo.app.Main
```

Windows PowerShell, dấu phân cách classpath là `;`:

```powershell
java.exe -cp "consumer/target/consumer-1.0.0.jar;alpha-library/target/alpha-library-1.0.0.jar;beta-library/target/beta-library-1.0.0.jar" demo.app.Main
```

Với **standard application classloader**, không có lớp/resource trùng ở classloader cha và đúng thứ tự JAR đã chỉ định, stdout sẽ là:

```text
Class: alpha-library
Resource[1]: alpha-resource
Resource[2]: beta-resource
```

Maven không “chọn class alpha” ở đây. **Lệnh Java và classloader** quyết định thứ tự classpath; Maven đã tạo hai artifacts hợp lệ và consumer đã phụ thuộc cả hai.

### 5.8. Đổi thứ tự JAR: beta trước

Linux/macOS:

```bash
java -cp "consumer/target/consumer-1.0.0.jar:beta-library/target/beta-library-1.0.0.jar:alpha-library/target/alpha-library-1.0.0.jar" demo.app.Main
```

Windows PowerShell:

```powershell
java.exe -cp "consumer/target/consumer-1.0.0.jar;beta-library/target/beta-library-1.0.0.jar;alpha-library/target/alpha-library-1.0.0.jar" demo.app.Main
```

Stdout tương ứng:

```text
Class: beta-library
Resource[1]: beta-resource
Resource[2]: alpha-resource
```

**Điểm chứng minh:** không sửa POM, không sửa version, không build lại, nhưng **lớp được nạp và thứ tự resource thay đổi**. Đây là xung đột ở **classpath contents**, không phải dependency version conflict.

Ví dụ này cố ý dùng classloader ứng dụng command-line đơn giản. Trong WAR/app server, servlet container, Spring Boot launcher, OSGi hoặc custom classloader, thứ tự/delegation có thể khác. Khi chẩn đoán hệ thống thực, quan sát chính classloader đã nạp lớp và runtime packaging tương ứng.

## 6. Tại sao NoSuchMethodError không tự động đồng nghĩa duplicate class?

Xét thư viện `util-api` version 1.0 có `String format(String)`; code ứng dụng được compile theo version 2.0 có method mới `String format(String, int)`. Nếu runtime thực tế chỉ có version 1.0 do dependency mediation, có thể gặp `NoSuchMethodError` khi gọi method mới.

Đây là **mismatch phiên bản/binary compatibility** dù classpath chỉ có **một** JAR `util-api` chứa lớp đó. Không cần duplicate class để phát sinh lỗi.

Ngược lại, nếu một vendor JAR khác tọa độ cũng chứa lớp `util.api.Formatter` version cũ, rồi đứng trước JAR đúng trên classpath, lỗi có thể giống hệt `NoSuchMethodError` nhưng **nguyên nhân là duplicate class**, không phải resolver đã chọn sai version của artifact `util-api`.

Vì vậy, chẩn đoán đúng phải trả lời **hai câu độc lập**:

1. Maven đã chọn **artifact version nào**, theo dependency tree/effective POM?
2. JVM thực sự **nạp class từ JAR nào**, theo classloader và code source/log?

Chỉ giải được câu (1) là chưa đủ.

### Quan sát nguồn class JVM đang dùng

Đối với một class bạn có thể tham chiếu hợp lệ trong ứng dụng:

```java
System.out.println(
    demo.shared.Message.class.getProtectionDomain()
        .getCodeSource().getLocation()
);
```

Đây là **đoạn Java minh họa**, không phải chương trình hoàn chỉnh. Trong một số classloader/security/module environments, code source có thể là `null`, bị bao bọc bởi launcher hoặc không cho thấy file JAR theo cách đơn giản. Với Java command line thông thường, nó thường hiện đường dẫn nguồn JAR.

Có thể bật log class loading trên Java 17:

```bash
java -Xlog:class+load=info -cp "<classpath-thực-tế>" demo.app.Main
```

Ở đây `<classpath-thực-tế>` là placeholder: phải thay bằng chuỗi JAR có thật. Log khá dài và format tùy JVM; tìm tên FQCN cần chẩn đoán và nguồn class được load. Nếu log đi vào hệ thống giám sát, lọc đường dẫn/metadata nhạy cảm trước khi chia sẻ.

## 7. Đọc đúng dependency tree: giải quyết được gì và không được gì?

Tại project ứng dụng:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=vn.example
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom -Doutput=effective-pom.xml
```

- `dependency:tree` hiển thị dependency graph đã resolve, hữu ích để thấy version hiện hành và đường đi.
- `-Dincludes=...` giúp lọc một group/artifact cần xem. Thay `vn.example` bằng groupId thực tế.
- `-Dscope=runtime` lọc graph theo scope phục vụ runtime; cần nhớ classpath compile/test có thể khác.
- `help:effective-pom` giúp kiểm tra management, BOM, exclusions, profiles và cấu hình project sau inheritance.

Một số phiên bản Maven Dependency Plugin hỗ trợ `-Dverbose` để hiển thị các node bị bỏ qua khi resolve xung đột. **Phải kiểm tra tài liệu phiên bản plugin đang chạy**: hành vi verbose đã thay đổi giữa các phiên bản, nên không dùng việc “không thấy omitted for conflict” làm bằng chứng rằng không hề có version conflict. Trong trường hợp cần kết luận chính xác, xem output thực và plugin version hoặc dùng dependency graph ở định dạng hỗ trợ.

**Giới hạn:** `dependency:tree` không quét nội dung file `.class` và không hợp nhất resource paths. Nếu tree chứa alpha và beta, Maven chỉ đang nói cả hai tọa độ là dependency hợp lệ, **không nói chúng không có class trùng nhau**.

Một số goal/tính năng cũng dễ bị hiểu nhầm:

- `dependency:analyze` chủ yếu xem dependency khai báo và sử dụng/không sử dụng theo phân tích bytecode, **không phải** bộ quét duplicate class/resource tổng quát.
- `dependency:analyze-duplicate` phát hiện **khai báo dependency trùng trong POM**, khác với hai artifact khác tọa độ cùng chứa FQCN.
- Maven Enforcer với các rule như **dependencyConvergence** hay **requireUpperBoundDeps** giúp kiểm soát **sự nhất quán version**; chúng không mặc nhiên quét tất cả duplicate classes.
- Có các extension/rule của bên thứ ba, ví dụ **BanDuplicateClasses** trong Extra Enforcer Rules, dùng khi cần phát hiện lớp trùng; phải quản lý phiên bản, cấu hình và kiểm tra tương thích plugin.

## 8. Điều tra duplicate class và duplicate resource bằng JDK tools

### 8.1. Xác minh file cụ thể có chứa lớp không

Khi đã biết JAR nghi vấn:

```bash
jar tf path/to/alpha.jar
jar tf path/to/beta.jar
```

Tìm đường dẫn `demo/shared/Message.class` hoặc package tương ứng. `jar tf` đọc **nội dung JAR**, còn `dependency:tree` đọc **quan hệ Maven artifacts**; hai góc nhìn bổ sung cho nhau.

Với Unix, có thể lọc:

```bash
jar tf path/to/alpha.jar | grep 'demo/shared/Message.class'
jar tf path/to/beta.jar | grep 'demo/shared/Message.class'
```

Windows PowerShell:

```powershell
jar.exe tf path/to/alpha.jar | Select-String "demo/shared/Message.class"
jar.exe tf path/to/beta.jar | Select-String "demo/shared/Message.class"
```

Đây là lệnh **tìm class trong từng JAR đã biết**, không phải scanner toàn bộ mọi artifact. Nếu có hàng trăm JAR, dùng duplicate-class scanner hoặc script inventory phù hợp thay vì kiểm thủ công.

### 8.2. So sánh bytecode API

`javap` có thể hiển thị method/field của class trong từng JAR:

```bash
javap -classpath path/to/alpha.jar demo.shared.Message
javap -classpath path/to/beta.jar demo.shared.Message
```

Khi cả hai JAR có cùng FQCN, **đừng** đưa hai JAR vào cùng `-classpath` nếu mục tiêu là so sánh: cách đó lại có thể nạp một bản theo thứ tự classpath và che khuất bản còn lại.

`javap` giúp tìm mismatch signature/API; không chứng minh bản nào được load lúc runtime trong một container phức tạp.

### 8.3. Kiểm tra resource có nhiều bản

Java API:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
var urls = loader.getResources("config.properties");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

Đây là **đoạn Java bên trong method có khai báo `throws IOException` hoặc xử lý exception**, không phải file Java chạy độc lập. `getResources` tìm nhiều URL theo classloader và delegation. Tên `config.properties` là ví dụ; thay resource path đúng với ứng dụng. Với frameworks, context classloader có thể khác classloader nạp lớp, nên nên kiểm tra cả hai khi cần.

Nếu chạy fat JAR đã merge và chỉ còn **một** resource, `getResources` không thể tự hồi phục các bản metadata đã bị loại trong quá trình đóng gói. Cần kiểm tra cấu hình Shade/Assembly và file sản phẩm cuối.

## 9. Cách sửa xung đột phiên bản

Quy trình an toàn:

1. Chạy `dependency:tree` cho đúng module, profile và scope.
2. Xác định **tọa độ artifact** có các version cạnh tranh và đường bắc cầu đưa chúng vào graph.
3. Đối chiếu API/binary compatibility thực tế, không chỉ version cao/thấp.
4. Sử dụng `dependencyManagement`/BOM hoặc direct dependency có version được kiểm thử để chốt version phù hợp.
5. Nếu một nhánh đưa artifact thừa/sai, dùng `<exclusions>` có chủ đích tại dependency tương ứng.
6. Test lại compile, unit test, integration test và runtime để kiểm tra tương thích.
7. Ghim version trong parent/BOM, CI và theo dõi dependency graph để giảm lệch giữa module.

Ví dụ exclusion một dependency bắc cầu không mong muốn (đoạn POM minh họa):

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-sdk</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>shared-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion **loại một đường dependency**, không sửa API của `legacy-sdk`. Nếu SDK thật sự cần `shared-api` trong runtime và không có bản thay thế phù hợp, loại bỏ nó có thể khiến `ClassNotFoundException`/`NoClassDefFoundError` hoặc lỗi khác. Phải kiểm tra test và document lý do loại.

Với nhiều dependency cùng do một nền tảng quản lý, import BOM phù hợp thường đáng tin hơn tự chọn từng version rời rạc. Nhưng BOM cũng không sửa được việc hai artifact khác tọa độ nhúng cùng class.

## 10. Cách sửa duplicate class

**Nguyên tắc:** xác định **tất cả owner của FQCN** rồi chọn chiến lược giữ một nguồn đáng tin hoặc cách ly chủ động.

- **Loại một JAR khỏi classpath** nếu nó là bản đóng gói thừa; sửa direct/transitive dependency, WAR classpath hoặc script khởi chạy.
- Nếu hai vendor SDK có class trùng do bundle sai, **nâng/sửa SDK** để không nhúng bản sao không kiểm soát, hoặc liên hệ nhà cung cấp.
- Khi bắt buộc dùng hai thư viện có private implementation trùng package/class, cân nhắc **relocation bằng Maven Shade Plugin** ở một module đóng gói được kiểm soát. Relocation đổi tên package bytecode và có những giới hạn với reflection, serialization, service descriptors và resource names; không phải thuốc chữa mọi trường hợp.
- Trong app server/framework dùng nhiều classloaders, phân biệt parent-first/child-first và classloader isolation; **không** cố ý đảo classpath để che lỗi trùng như một chiến lược dài hạn.
- Thêm công cụ kiểm thử phát hiện duplicate classes nếu chính sách dự án yêu cầu. Phải loại trừ các tình huống duplicate class hợp lệ có lý do (nếu có) bằng danh sách minh bạch và kiểm chứng.

**Đừng chỉ thêm `dependencyManagement` cho alpha và beta trong ví dụ.** Hai artifact có ID khác nhau, mỗi artifact giữ một class `demo.shared.Message`. Management có thể chọn version của từng artifact nhưng không chỉ định JVM nên lấy class nào.

## 11. Cách sửa duplicate resource

Chiến lược phụ thuộc ý nghĩa resource:

1. **Cấu hình ứng dụng:** đặt resource vào đường dẫn namespaced như `vn/example/alpha/config.properties` hoặc đặt tên rõ ràng, không dùng `config.properties` chung khi không có mục tiêu override.
2. **Tập hợp provider metadata:** khi build fat JAR, dùng transformer phù hợp để **merge `META-INF/services/...`** nếu muốn `ServiceLoader` thấy tất cả provider. Maven Shade Plugin có `ServicesResourceTransformer` cho mục đích này.
3. **Resource cố ý override:** tài liệu hóa thứ tự classpath/classloader hoặc quy tắc priority của framework, rồi có test; không dựa vào trùng tên ngẫu nhiên.
4. **Một resource bị đóng gói hai lần:** sửa `maven-resources-plugin`, Shade/Assembly packaging hoặc exclude hợp lý; tránh loại file mà framework/license yêu cầu.
5. **License/notice files:** tuân theo nghĩa vụ pháp lý khi hợp nhất thay vì xóa các file trùng một cách mù quáng.

Với `getResource`, “được một URL” không có nghĩa chỉ tồn tại một resource. Dùng `getResources` và kiểm tra nội dung/JAR để xác định số bản. Với metadata `META-INF/services`, việc một service provider không được phát hiện có thể do file service descriptor bị mất khi packaging, do class không tồn tại, hoặc do classloader/module layer khác — phải điều tra từng khả năng.

## 12. Cách phân biệt lỗi theo triệu chứng

| Triệu chứng | Khả năng cần điều tra | Bằng chứng nên thu |
| --- | --- | --- |
| Maven hiển thị các version khác nhau của cùng artifact trong đường phụ thuộc | **Version conflict** | Dependency tree, effective POM, BOM/management |
| `NoSuchMethodError` sau khi update thư viện | Version/API mismatch **hoặc** duplicate class | Version Maven chọn **và** nguồn class JVM nạp |
| `ClassNotFoundException` | Artifact thiếu, scope/runtime path sai, classloader isolation | Dependency runtime tree, JAR contents, launch classpath |
| `NoClassDefFoundError` | Class không có hoặc không khởi tạo/resolve được đúng cách | Full stack trace và nguyên nhân gốc, runtime classpath |
| Hai JAR khác tọa độ có cùng `com/acme/Foo.class` | **Duplicate class** | `jar tf` từng JAR, class-loading log |
| Ứng dụng dùng nhầm config dù Maven build PASS | **Resource collision** hoặc precedence framework | `getResources`, resource paths, config-loading rules |
| Fat JAR thiếu service provider | Có thể descriptor `META-INF/services` bị ghi đè | Nội dung JAR cuối, shade transformers, ServiceLoader |
| Build pass, chạy trong server lỗi nhưng chạy `java -cp` bình thường | Container classloader/packaging/scope khác | Runtime launcher, WAR contents, server libraries |

Một dấu hiệu không nên kết luận vội: **thấy nhiều phiên bản trong local repository `~/.m2/repository`** chỉ cho biết máy từng tải nhiều artifact. Nó **không chứng minh** Maven đưa tất cả phiên bản ấy vào classpath của ứng dụng hiện tại. Hãy quan sát cây phụ thuộc và process runtime thực.

## 13. Checklist chẩn đoán theo đúng thứ tự

1. **Ghi triệu chứng:** lỗi compile, test, runtime, framework config hay fat-JAR packaging; lấy stack trace và FQCN/resource path cụ thể.
2. **Xác định phạm vi:** module nào, phase/profile nào, compile/test/runtime, Java `-cp`, WAR/container hay Spring Boot launcher.
3. **Kiểm tra đồ thị Maven:** `dependency:tree` để biết tọa độ và version thật được resolve; xem management, exclusions, optional và BOM nếu nghi version conflict.
4. **Kiểm tra vật lý JAR:** dùng `jar tf` để thấy class/resource có trùng path ở nhiều artifact không.
5. **Kiểm tra runtime:** classloading log, code source, `getResources` hoặc công cụ đặc thù của framework/container.
6. **Chọn đúng biện pháp:** version management/BOM cho version mismatch; loại/relocate JAR cho duplicate class; rename/merge/transform resource cho collision tài nguyên.
7. **Kiểm thử lại trên artifact cuối cùng:** không chỉ compile; chạy unit/integration tests, `java -cp`/`java -jar` hoặc deployment server thực.
8. **Ngăn tái diễn:** pin versions, dependency convergence rule, duplicate-class scan, kiểm tra service metadata và giữ BOM/packaging configuration có review.

**Tóm lại:** giải quyết đúng phụ thuộc Maven là điều kiện cần, nhưng chưa phải bảo đảm classpath không trùng lớp hoặc tài nguyên. Maven resolver trả lời **“artifact nào, phiên bản nào?”**; việc kiểm tra JAR/classloader trả lời **“lớp hoặc tài nguyên nào thực sự được dùng?”**. Chẩn đoán cả hai tầng mới xử lý được lỗi không ổn định giữa build và runtime.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Common Misconceptions About Dependency Resolution](https://maven.apache.org/repositories/dependency-resolution-misconceptions.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Dependency Plugin — dependency:analyze-duplicate](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-duplicate-mojo.html)
- [Maven Enforcer Plugin — Dependency Convergence Rule](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Maven Enforcer Plugin — Require Upper Bound Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html)
- [Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html)
- [Java SE 17 — ClassLoader#getResources](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getResources(java.lang.String))
