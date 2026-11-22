# Resource transformer và hợp nhất tệp dịch vụ META-INF/services bằng Maven Shade Plugin

## 1. Vấn đề: uber-JAR chứa đủ class nhưng ServiceLoader lại thiếu provider

Maven Shade Plugin có thể gom class và resource từ project cùng các dependency JAR thành một **uber-JAR** (còn gọi là shaded/fat JAR). Nhưng nhiều dependency có thể chứa **resource trùng đường dẫn**. Ví dụ, hai thư viện cùng triển khai một Java SPI có thể đều chứa:

~~~text
META-INF/services/org.example.spi.GreetingProvider
~~~

JAR A ghi tên provider:

~~~text
org.example.providers.alpha.AlphaGreetingProvider
~~~

JAR B ghi tên provider:

~~~text
org.example.providers.beta.BetaGreetingProvider
~~~

Khi chạy ứng dụng với **hai JAR riêng trên classpath**, `java.util.ServiceLoader` có thể đọc các provider-configuration files và tìm cả hai implementation. Nhưng trong một ZIP/JAR kết quả, **một entry path cụ thể chỉ nên có một bản resource hợp lệ**. Nếu quá trình đóng gói không hợp nhất nội dung có ý nghĩa, một descriptor có thể bị mất/ghi đè hoặc đóng gói không đúng mong đợi. Ứng dụng vẫn compile, Shade vẫn có thể tạo ra JAR, nhưng `ServiceLoader` có thể chỉ tìm thấy một provider, không thấy provider nào, hoặc báo lỗi cấu hình.

Cách giải quyết phù hợp với Maven Shade là:

~~~xml
<transformer implementation=
    "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
~~~

**`ServicesResourceTransformer`** chuyên xử lý các entry dưới `META-INF/services/`: nó **hợp nhất danh sách provider** của cùng service, đồng thời **đổi tên class trong service metadata khi Shade thực hiện relocation**. Tài liệu chính thức Maven Shade mô tả rõ hai trách nhiệm này.

> **Ghi nhớ:** Chỉ gộp các file `.class` vào một archive là chưa đủ. Với SPI dùng `ServiceLoader`, phải giữ và hợp nhất **resource đăng ký provider** trong `META-INF/services/`.

Bài này tập trung vào resource transformers, đặc biệt `ServicesResourceTransformer`, cơ chế `ServiceLoader` và ví dụ Java 17 gồm **hai provider JAR + một app** để xác minh uber-JAR sau Shade tìm đủ hai provider. Đồng thời phân biệt công việc của Shade với Maven Assembly Plugin, manifest và tình huống relocation/minimization.

## 2. Resource trong JAR là gì và tại sao có thể trùng tên?

Một JAR thông thường là ZIP archive chứa Java bytecode và nhiều resource. Cấu trúc ví dụ:

~~~text
some-library.jar
├── org/example/lib/SomeClass.class
├── META-INF/MANIFEST.MF
├── META-INF/services/org.example.spi.GreetingProvider
├── META-INF/spring.handlers
├── config/defaults.properties
└── META-INF/NOTICE
~~~

Các thành phần:

- `.class`: bytecode Java.
- `META-INF/MANIFEST.MF`: manifest metadata, có thể chứa `Main-Class`.
- `META-INF/services/<fully-qualified-service-name>`: một hoặc nhiều tên implementation để `ServiceLoader` tìm provider.
- `META-INF/spring.handlers`, `META-INF/spring.schemas`: metadata tích hợp của một số framework.
- `.properties`, XML, JSON, resource bundles: nội dung mà code hoặc framework đọc bằng classloader/resource APIs.
- `LICENSE`/`NOTICE`: tài liệu bản quyền/ghi nhận nguồn, cần xem xét khi phân phối.

Khi mỗi dependency còn nằm trong JAR riêng, hai file có cùng path `META-INF/services/org.example.spi.GreetingProvider` tồn tại ở **hai archive khác nhau**. Java classloader có thể tìm nhiều resource cùng tên trong classpath.

Khi xây dựng một uber-JAR, Shade cần **chọn cách xử lý collision**. Cách “lấy một file”, “nối byte vô điều kiện”, “merge XML” hoặc “merge Java SPI service descriptors” là **những hành vi khác nhau**. Không có một quy tắc “merge mọi resource” luôn chính xác.

Một lỗi phổ biến là chỉ xác minh rằng:

~~~text
AlphaGreetingProvider.class
BetaGreetingProvider.class
~~~

đều có trong uber-JAR, rồi kết luận ServiceLoader chắc chắn dùng được cả hai. **Class tồn tại không có nghĩa provider đã được đăng ký đúng**.

## 3. Java SPI và ServiceLoader hoạt động như thế nào?

Trong Java, **Service Provider Interface (SPI)** là interface/abstract class mà ứng dụng biết trước, còn provider là implementation có thể được phát hiện lúc chạy.

Ví dụ interface:

~~~java
package org.example.spi;

public interface GreetingProvider {
    String id();
    String greet(String name);
}
~~~

Provider A:

~~~java
package org.example.providers.alpha;

import org.example.spi.GreetingProvider;

public final class AlphaGreetingProvider implements GreetingProvider {
    public AlphaGreetingProvider() {
    }

    @Override
    public String id() {
        return "alpha";
    }

    @Override
    public String greet(String name) {
        return "Hello " + name + " from Alpha";
    }
}
~~~

Ứng dụng không nhất thiết gọi `new AlphaGreetingProvider()`. Nó có thể yêu cầu:

~~~java
ServiceLoader<GreetingProvider> loader =
        ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : loader) {
    System.out.println(provider.id());
}
~~~

Các đoạn Java ở mục này là **mảnh độc lập về ý tưởng**, chưa phải toàn bộ project; dự án runnable đầy đủ ở mục 9–13.

Với **service providers trên classpath**, `ServiceLoader` xác định provider thông qua các file trong `META-INF/services/`. Tên file là tên binary đầy đủ của **service type**, còn nội dung là tên class implementation.

Đối với interface `org.example.spi.GreetingProvider`:

~~~text
File:
META-INF/services/org.example.spi.GreetingProvider

Content:
org.example.providers.alpha.AlphaGreetingProvider
~~~

Tệp phải được mã hóa **UTF-8**. Một file có thể ghi nhiều implementation, mỗi tên trên một dòng; dòng rỗng và khoảng trắng phù hợp có thể được bỏ qua; ký tự `#` bắt đầu comment theo định dạng Java SPI.

**Điều kiện provider trong bài (classpath SPI):**

- Class implementation là một class cụ thể `public`.
- Implements/extends service type phù hợp.
- Có constructor không đối số `public` để Java tạo instance.
- Tên trong descriptor phải khớp đầy đủ package và class đã biên dịch.
- Provider class và dependency của nó phải nhìn thấy được từ classloader phù hợp.

Tài liệu Java 17 `ServiceLoader` cũng có những quy tắc khác cho **named JPMS modules**, được bàn riêng ở mục 19. Ví dụ runnable ở đây **không dùng `module-info.java`**, nên áp dụng cơ chế classpath descriptors.

## 4. Vì sao classpath nhiều JAR có thể hoạt động, còn fat JAR thì thất bại?

Giả sử:

~~~text
Provider Alpha JAR:
    org/example/providers/alpha/AlphaGreetingProvider.class
    META-INF/services/org.example.spi.GreetingProvider
        -> org.example.providers.alpha.AlphaGreetingProvider

Provider Beta JAR:
    org/example/providers/beta/BetaGreetingProvider.class
    META-INF/services/org.example.spi.GreetingProvider
        -> org.example.providers.beta.BetaGreetingProvider
~~~

Khi các archive tách rời:

~~~text
java -cp "app.jar:spi-api.jar:provider-alpha.jar:provider-beta.jar" \
    org.example.app.Main
~~~

Đây là lệnh **minh họa cho Linux/macOS**, chỉ chạy khi file thực sự tồn tại đúng tên và đường dẫn. Windows dùng dấu `;` phân cách classpath entries.

Classpath có thể chứa **hai resource cùng tên** ở các archive khác nhau; `ServiceLoader` xử lý service configuration files được tìm thấy. Khi Shade **unpack và gom** tất cả vào một JAR, nếu không có cách xử lý service metadata thích hợp, việc trùng path khiến **không thể tự giả định hai danh sách được giữ lại**.

Ví dụ một kết quả lỗi có thể là:

~~~text
META-INF/services/org.example.spi.GreetingProvider
    org.example.providers.alpha.AlphaGreetingProvider
~~~

trong khi JAR thật vẫn có cả:

~~~text
org/example/providers/alpha/AlphaGreetingProvider.class
org/example/providers/beta/BetaGreetingProvider.class
~~~

Beta class vẫn hiện diện, nhưng **ServiceLoader không tự quét toàn bộ class files để tìm class nào implements interface**. Nó chủ yếu dựa vào metadata đăng ký service với classpath providers.

**Không khẳng định Shade lúc không transformer sẽ luôn chọn Alpha hoặc luôn mất Beta**; hành vi khi resource collision phụ thuộc archive đầu vào/plugin/ordering. Bài học là **không có bảo đảm hợp nhất SPI đúng** nếu thiếu transformer có chức năng phù hợp.

## 5. ServicesResourceTransformer làm chính xác những việc gì?

Tên implementation đầy đủ:

~~~text
org.apache.maven.plugins.shade.resource.ServicesResourceTransformer
~~~

Nhiệm vụ theo Apache Maven Shade Plugin:

1. Nhận các entry `META-INF/services/...` xuất hiện trong project/dependencies.
2. Tập hợp các dòng provider tương ứng với **cùng service interface**.
3. Ghi một service descriptor thích hợp trong output shaded JAR.
4. Khi Shade có **class/package relocation**, cập nhật tên class provider trong descriptor và đường dẫn service descriptor khi service type cũng được relocate.

Ví dụ hai tệp đầu vào:

~~~text
# provider-alpha.jar
META-INF/services/org.example.spi.GreetingProvider
org.example.providers.alpha.AlphaGreetingProvider
~~~

~~~text
# provider-beta.jar
META-INF/services/org.example.spi.GreetingProvider
org.example.providers.beta.BetaGreetingProvider
~~~

Sau merge, nội dung output về mặt logic phải chứa **cả hai**:

~~~text
META-INF/services/org.example.spi.GreetingProvider
org.example.providers.alpha.AlphaGreetingProvider
org.example.providers.beta.BetaGreetingProvider
~~~

**Thứ tự dòng trong output không nên được coi là giao kèo nghiệp vụ.** Không thiết kế ứng dụng phụ thuộc vào việc Alpha hay Beta được phát hiện trước; nếu cần chọn provider, dùng `id`, priority rõ ràng hoặc thứ tự sort do chính ứng dụng định nghĩa.

**Không coi transformer là hệ thống kiểm thử semantic đầy đủ:** nếu tên provider trỏ class không tồn tại, constructor không hợp lệ, dependency thiếu hoặc provider bị hỏng khi relocation, `ServiceLoader` vẫn có thể ném `ServiceConfigurationError`. Transformer xử lý metadata khi đóng gói; ứng dụng vẫn phải kiểm tra runtime.

## 6. Cấu hình tối thiểu của Shade Plugin

Mảnh XML cơ bản cho project tạo uber-JAR:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>shade-package</id>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer
                        implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh cần đặt trong `<build><plugins>`** của POM, không phải POM độc lập.

- `version` là phiên bản **Maven Shade Plugin**, không phải version của Java SPI.
- `shade:shade` chạy ở phase `package` khi được bind như trên.
- `ServicesResourceTransformer` cần nằm trong `configuration/transformers` áp dụng cho goal Shade.
- Transformer **không tự được thêm** chỉ vì Maven biết dependency chứa `META-INF/services`.
- Không cần khai báo Java `ServiceLoader` như project dependency, vì nó thuộc JDK.

Chỉ mảnh trên **chưa tự làm JAR chạy được bằng `java -jar`**: muốn executable JAR cần **manifest Main-Class**. Mục 7 sẽ thêm transformer khác có nhiệm vụ riêng.

## 7. ManifestResourceTransformer không thay ServicesResourceTransformer

Để chạy:

~~~bash
java -jar target/service-app-1.0.0-all.jar
~~~

shaded JAR cần manifest chứa `Main-Class` trỏ tới class main hợp lệ. Shade có transformer:

~~~xml
<transformer
    implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
    <mainClass>org.example.app.Main</mainClass>
</transformer>
~~~

**`ManifestResourceTransformer`** đặt/cập nhật manifest entries trong output shaded JAR. Nó **không hợp nhất danh sách provider `META-INF/services`**. Ngược lại, `ServicesResourceTransformer` xử lý SPI entries nhưng **không tự viết `Main-Class`**.

Trong một build executable SPI-enabled, cần cả hai:

~~~xml
<transformers>
    <transformer
        implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
    <transformer
        implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>org.example.app.Main</mainClass>
    </transformer>
</transformers>
~~~

Hai transformer giải quyết **hai mục tiêu**:

| Transformer | Tệp/resource trọng tâm | Vai trò |
| --- | --- | --- |
| `ServicesResourceTransformer` | `META-INF/services/*` | Merge provider entries, cập nhật tên class khi relocation. |
| `ManifestResourceTransformer` | `META-INF/MANIFEST.MF` | Thiết lập `Main-Class` và manifest entries khác. |

**Không biến mọi resource duplicate thành manifest entries.** Resource transform là công việc phụ thuộc **định dạng và ý nghĩa của từng loại resource**.

## 8. Java SPI service descriptor: những chi tiết rất dễ sai

### 8.1. Tên file phải là tên service interface

Với service type:

~~~java
package org.example.spi;
public interface GreetingProvider {}
~~~

đường dẫn đăng ký đúng là:

~~~text
src/main/resources/META-INF/services/org.example.spi.GreetingProvider
~~~

Không được nhầm thành:

~~~text
src/main/resources/META-INF/services/org.example.providers.alpha.AlphaGreetingProvider
~~~

vì đó là **tên implementation**, không phải tên service type.

### 8.2. Nội dung ghi tên provider class, không thêm .class

Đúng:

~~~text
org.example.providers.alpha.AlphaGreetingProvider
~~~

Sai:

~~~text
org/example/providers/alpha/AlphaGreetingProvider.class
~~~

Không thêm Java source extension `.java`, không thêm `new`, không ghi Maven coordinates.

### 8.3. Phải nằm ở resources directory

Trong project Java Maven tiêu chuẩn:

~~~text
src/main/resources/META-INF/services/org.example.spi.GreetingProvider
~~~

được Maven Resources Plugin copy vào:

~~~text
target/classes/META-INF/services/org.example.spi.GreetingProvider
~~~

và Maven JAR Plugin đóng gói vào JAR. Nếu đặt file trong `src/test/resources`, nó thường chỉ nằm trong test output và **không trở thành runtime provider descriptor của main JAR**.

### 8.4. Dòng mới và encoding

Một descriptor UTF-8 hợp lệ có thể chứa:

~~~text
# Provider used by the Alpha library
org.example.providers.alpha.AlphaGreetingProvider

# Another provider, if packaged in the same archive:
org.example.providers.beta.BetaGreetingProvider
~~~

`ServiceLoader` bỏ qua comment và dòng trắng theo format. Với thư viện riêng, mỗi provider JAR chỉ cần ghi provider của nó. Trong kết quả uber-JAR, transformer hợp nhất hai nguồn.

### 8.5. Tên class phải trùng bytecode cuối

Nếu bạn đổi `package`, đổi tên class hoặc dùng Shade relocation, descriptor **phải phản ánh tên cuối cùng có trong output**. Một provider không thể được tìm chỉ vì tên source vẫn tồn tại trong Git; runtime đọc metadata **đã đóng gói**.

## 9. Project Java 17 hoàn chỉnh: hai provider JAR và một app

Dự án thực hành sau dùng **Maven reactor gồm bốn child projects**:

1. `spi-api`: công bố interface `GreetingProvider`.
2. `provider-alpha`: chứa `AlphaGreetingProvider` và file `META-INF/services`.
3. `provider-beta`: chứa `BetaGreetingProvider` và file `META-INF/services` cùng tên.
4. `service-app`: phụ thuộc ba project trên, chạy `ServiceLoader`; riêng module này tạo uber-JAR bằng Shade.

Parent `pom.xml` dùng packaging `pom`, quản lý Maven plugin versions. Dự án **không dùng `module-info.java`**, vì demo cần tập trung vào **ServiceLoader classpath + META-INF/services**.

Cây thư mục:

~~~text
shade-services-demo/
├── pom.xml
├── spi-api/
│   ├── pom.xml
│   └── src/main/java/org/example/spi/GreetingProvider.java
├── provider-alpha/
│   ├── pom.xml
│   └── src/main/
│       ├── java/org/example/providers/alpha/AlphaGreetingProvider.java
│       └── resources/META-INF/services/org.example.spi.GreetingProvider
├── provider-beta/
│   ├── pom.xml
│   └── src/main/
│       ├── java/org/example/providers/beta/BetaGreetingProvider.java
│       └── resources/META-INF/services/org.example.spi.GreetingProvider
└── service-app/
    ├── pom.xml
    └── src/
        ├── main/java/org/example/app/Main.java
        └── test/java/org/example/app/ServiceLoadingTest.java
~~~

Trong các ví dụ:

- JDK 17+ và Maven 3.9.x tương thích với plugin.
- Maven Shade Plugin `3.6.2`; Maven Compiler Plugin `3.13.0`; Maven Surefire `3.5.2`; JUnit Jupiter `5.11.4` cho một smoke test.
- Version `1.0.0` là version tự đặt để đào tạo, không phải artifact đã có trên Maven Central.
- Provider names được sắp xếp **trong ứng dụng** để stdout độc lập thứ tự discovery của Java.

## 10. Parent pom.xml và SPI API

### 10.1. Root shade-services-demo/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.shade</groupId>
    <artifactId>shade-services-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>spi-api</module>
        <module>provider-alpha</module>
        <module>provider-beta</module>
        <module>service-app</module>
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
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Đây là **POM hoàn chỉnh**. Root vừa làm aggregator (liệt kê child modules) vừa làm parent (các child sẽ khai báo `<parent>`), nhưng **không tự tạo một Java JAR** vì packaging `pom`.

`pluginManagement` quản lý phiên bản plugin khi lifecycle/plugin execution của child sử dụng chúng. Nó không tự chạy Shade trong parent; Shade sẽ được khai báo **chỉ trong `service-app/pom.xml`**. Điều này tránh cố đóng gói toàn reactor ở thời điểm các child artifacts chưa có.

### 10.2. spi-api/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.shade</groupId>
        <artifactId>shade-services-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>spi-api</artifactId>
    <packaging>jar</packaging>
</project>
~~~

### 10.3. spi-api/src/main/java/org/example/spi/GreetingProvider.java

~~~java
package org.example.spi;

public interface GreetingProvider {
    String id();
    String greet(String name);
}
~~~

Đây là interface chung mà hai provider classes implements. Giữ API trong module riêng giúp mỗi provider phụ thuộc **cùng một** Java type; nếu bạn vô tình đóng gói hai phiên bản khác nhau của SPI API ở runtime, có thể xảy ra class identity/compatibility errors.

## 11. Provider Alpha: POM, Java class và service descriptor

### 11.1. provider-alpha/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.shade</groupId>
        <artifactId>shade-services-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>provider-alpha</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.shade</groupId>
            <artifactId>spi-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Provider phụ thuộc `spi-api` để compile `implements GreetingProvider`. Đây là **Maven project dependency** thực sự, không phải chuỗi tên provider trong META-INF/services.

### 11.2. provider-alpha/src/main/java/org/example/providers/alpha/AlphaGreetingProvider.java

~~~java
package org.example.providers.alpha;

import org.example.spi.GreetingProvider;

public final class AlphaGreetingProvider implements GreetingProvider {
    public AlphaGreetingProvider() {
    }

    @Override
    public String id() {
        return "alpha";
    }

    @Override
    public String greet(String name) {
        return "Hello " + name + " from Alpha";
    }
}
~~~

Lớp có constructor public không đối số và implements đúng interface. Java `String` operations ở đây rất đơn giản để trọng tâm của bài không bị phân tán sang business logic.

### 11.3. provider-alpha/src/main/resources/META-INF/services/org.example.spi.GreetingProvider

**Nội dung chính xác của file resource**:

~~~text
org.example.providers.alpha.AlphaGreetingProvider
~~~

Tên file **là tên interface SPI**; dòng trong file là **tên provider implementation**. Không ghi dấu `;`, không thêm `.class` và không trộn XML vào đây.

Khi build provider-alpha, Resources Plugin copy file này vào `target/classes/META-INF/services/...`, sau đó JAR Plugin đóng gói nó vào `provider-alpha-1.0.0.jar`.

## 12. Provider Beta: file META-INF/services trùng đường dẫn

### 12.1. provider-beta/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.shade</groupId>
        <artifactId>shade-services-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>provider-beta</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.shade</groupId>
            <artifactId>spi-api</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

### 12.2. provider-beta/src/main/java/org/example/providers/beta/BetaGreetingProvider.java

~~~java
package org.example.providers.beta;

import org.example.spi.GreetingProvider;

public final class BetaGreetingProvider implements GreetingProvider {
    public BetaGreetingProvider() {
    }

    @Override
    public String id() {
        return "beta";
    }

    @Override
    public String greet(String name) {
        return "Hello " + name + " from Beta";
    }
}
~~~

### 12.3. provider-beta/src/main/resources/META-INF/services/org.example.spi.GreetingProvider

~~~text
org.example.providers.beta.BetaGreetingProvider
~~~

Đây là **đường dẫn giống hệt** file service resource của provider-alpha, nhưng **nội dung khác**. Điều này hoàn toàn bình thường ở hai JAR riêng, và chính là bài toán bắt buộc phải giải quyết khi đóng gói chúng chung vào một shaded JAR.

Để ý:

~~~text
provider-alpha.jar -> META-INF/services/org.example.spi.GreetingProvider
provider-beta.jar  -> META-INF/services/org.example.spi.GreetingProvider
~~~

Nếu bạn nhìn vào Maven local repository, mỗi JAR vẫn có descriptor riêng. Khi Shade tạo output JAR cuối, `ServicesResourceTransformer` hợp nhất các danh sách provider thành một descriptor thích hợp.

## 13. App POM: Shade Plugin + hai resource transformers

### 13.1. service-app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.shade</groupId>
        <artifactId>shade-services-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.shade</groupId>
            <artifactId>spi-api</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.example.shade</groupId>
            <artifactId>provider-alpha</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.example.shade</groupId>
            <artifactId>provider-beta</artifactId>
            <version>1.0.0</version>
        </dependency>

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
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>make-executable-uber-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <!-- Keep the ordinary thin JAR and attach a separate -all JAR. -->
                            <shadedArtifactAttached>true</shadedArtifactAttached>
                            <shadedClassifierName>all</shadedClassifierName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <minimizeJar>false</minimizeJar>

                            <!-- Remove signature files made invalid by repackaging.
                                 Do not remove service descriptors, LICENSE or NOTICE. -->
                            <filters>
                                <filter>
                                    <artifact>*:*</artifact>
                                    <excludes>
                                        <exclude>META-INF/*.SF</exclude>
                                        <exclude>META-INF/*.DSA</exclude>
                                        <exclude>META-INF/*.RSA</exclude>
                                    </excludes>
                                </filter>
                            </filters>

                            <transformers>
                                <transformer
                                    implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                                <transformer
                                    implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.example.app.Main</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **POM hoàn chỉnh** cho `service-app`. Giải thích từng phần quan trọng:

- Ba project dependencies `spi-api`, `provider-alpha`, `provider-beta` sẽ được Maven reactor xây dựng và cung cấp cho app. **Chỉ khai báo một provider JAR thì transformer không thể tự sáng tạo provider còn thiếu.**
- `junit-jupiter` nằm ở `scope=test`: phục vụ test `ServiceLoadingTest`, không là runtime provider.
- `shade:shade` được bind vào phase `package` của **service-app**, sau khi thin JAR được JAR Plugin tạo.
- `shadedArtifactAttached=true` và `shadedClassifierName=all` tạo thêm một JAR có classifier `all`, trong khi main artifact thông thường vẫn được giữ nguyên. Đây là lựa chọn có chủ đích để tránh nhầm *thin* và *uber* JAR.
- `createDependencyReducedPom=false` giữ cấu hình POM trong bài dễ theo dõi; với ứng dụng minh họa và một shaded classifier, ta không tạo dependency-reduced POM. Khi phát hành shaded library cho consumers, cần xem chiến lược dependency-reduced POM riêng.
- `minimizeJar=false` tránh tối giản dựa trên phân tích bytecode có thể bỏ sót provider chỉ được tìm qua reflection/service metadata.
- Bộ `filters` loại bỏ chữ ký JAR cũ như `.SF`, `.RSA`, `.DSA` có thể trở nên không hợp lệ sau khi JAR bị thay nội dung. **Không** loại `META-INF/services/**`.
- `ServicesResourceTransformer` merge SPI descriptors.
- `ManifestResourceTransformer` ghi `Main-Class` để Java launcher có thể khởi chạy `-all.jar`.

**Bảo mật:** loại signature metadata cũ là cách tránh lỗi “invalid signature digest” khi repackaging, **không có nghĩa shaded JAR đã được ký hoặc xác thực mới**. Nếu doanh nghiệp cần ký artifact cuối, phải ký output cuối bằng pipeline tin cậy và kiểm tra checksum/provenance. Không xóa `LICENSE`/`NOTICE` tùy tiện.

## 14. App Java source và JUnit test

### 14.1. service-app/src/main/java/org/example/app/Main.java

~~~java
package org.example.app;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ServiceLoader;

import org.example.spi.GreetingProvider;

public final class Main {
    private Main() {
    }

    public static List<String> describeProviders() {
        List<String> lines = new ArrayList<>();

        for (GreetingProvider provider : ServiceLoader.load(GreetingProvider.class)) {
            lines.add(provider.id() + "=" + provider.greet("Maven"));
        }

        // Service discovery order is not a business contract.
        Collections.sort(lines);
        return List.copyOf(lines);
    }

    public static void main(String[] args) {
        List<String> providers = describeProviders();
        if (providers.size() != 2) {
            throw new IllegalStateException(
                    "Expected 2 providers, found " + providers.size());
        }

        System.out.println("providers=" + providers.size());
        providers.forEach(System.out::println);
    }
}
~~~

Điểm quan trọng:

1. App **chỉ import interface** `GreetingProvider`, không import Alpha/Beta implementation classes.
2. `ServiceLoader.load(GreetingProvider.class)` tìm providers dựa vào đăng ký SPI.
3. Mã cố ý **sort** theo các chuỗi chứa ID nên stdout ổn định, không phụ thuộc discovery order.
4. Nếu sau Shade chỉ còn một provider, app ném `IllegalStateException` thay vì âm thầm chạy thiếu tính năng.
5. `List.copyOf` có trong Java 10+, hợp lệ trên Java 17.
6. Cách check `providers.size() == 2` chỉ dành cho demo có đúng hai implementations; trong ứng dụng thật số provider có thể thay đổi theo cấu hình.

### 14.2. service-app/src/test/java/org/example/app/ServiceLoadingTest.java

~~~java
package org.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class ServiceLoadingTest {
    @Test
    void findsBothImplementationsOnTestClasspath() {
        assertEquals(
                List.of(
                        "alpha=Hello Maven from Alpha",
                        "beta=Hello Maven from Beta"),
                Main.describeProviders());
    }
}
~~~

Test có tên `ServiceLoadingTest`, khớp quy tắc Surefire `*Test`. Nó chứng minh Maven test classpath đã thấy cả provider JARs và Java SPI descriptor **trước khi tạo shaded JAR**.

**Giới hạn quan trọng:** unit test chạy ở phase `test`, còn Shade chạy ở phase `package`. Vì vậy test này **không tự kiểm tra JAR `-all` sau khi merge**. Để bảo đảm transform thực sự hiệu quả, cần chạy `java -jar ...-all.jar` như smoke test ở mục 15/20.

## 15. Build toàn reactor và chạy executable shaded JAR

Tại root `shade-services-demo/`:

~~~bash
mvn -B -ntp clean package
~~~

Maven reactor thấy dependency giữa projects, sắp build thư viện API trước provider, rồi app. Trong `service-app`, Surefire chạy `ServiceLoadingTest` trước, sau đó Maven Shade Plugin tạo executable uber-JAR.

Output trọng tâm:

~~~text
spi-api/target/spi-api-1.0.0.jar
provider-alpha/target/provider-alpha-1.0.0.jar
provider-beta/target/provider-beta-1.0.0.jar

service-app/target/
  service-app-1.0.0.jar       # thin main JAR (không chứa các provider JARs)
  service-app-1.0.0-all.jar   # shaded attached artifact, classifier "all"
~~~

Đây là cây rút gọn. Một số plugin có thể tạo thêm metadata, `target/classes`, `target/test-classes` và reports.

Chạy từ **root của reactor**:

~~~bash
java -jar service-app/target/service-app-1.0.0-all.jar
~~~

**Stdout chính xác của riêng lệnh `java`**, với đúng các file mẫu và dependencies đã resolve:

~~~text
providers=2
alpha=Hello Maven from Alpha
beta=Hello Maven from Beta
~~~

Không coi ba dòng trên là toàn bộ log của Maven `clean package`. Maven có thể in logs tải plugins, compile, test, shade warnings và các mốc lifecycle.

**Vì sao phải chọn `-all.jar`?** Project cấu hình `shadedArtifactAttached=true`. JAR không classifier là thin JAR, không bảo đảm chứa runtime provider classes. Chạy nhầm:

~~~bash
java -jar service-app/target/service-app-1.0.0.jar
~~~

không phải phép thử hợp lệ cho shaded JAR của bài, và thin JAR còn **không có Main-Class** được thiết lập bởi Shade transformer theo mẫu này. Khi thấy `no main manifest attribute` hoặc thiếu class, hãy kiểm **bạn đang chạy đúng archive nào** trước khi đổ lỗi cho ServiceLoader.

### 15.1. Test classpath và shaded JAR kiểm chứng hai thứ khác nhau

| Phép thử | Giai đoạn | Xác minh điều gì? |
| --- | --- | --- |
| `ServiceLoadingTest` qua Surefire | Trước Shade (`test`) | Hai JAR dependencies có SPI descriptors đúng trên test classpath. |
| `java -jar ...-all.jar` | Sau Shade (`package`) | Uber-JAR đã giữ được các provider classes và service metadata. |
| Xem `META-INF/services` trong `-all.jar` | Sau Shade | Một merged descriptor chứa đúng provider lines. |
| `jar --list` | Sau Shade | Các class/resources cần thiết thực sự có trong archive. |

**Đây là hai lớp QA khác nhau.** Chạy pass JUnit trước Shade không loại bỏ rủi ro transformer/filter cấu hình sai làm hỏng output archive.

## 16. Đọc merged service descriptor trong JAR

Java JDK có lệnh `jar`. Để liệt kê entries:

~~~bash
jar --list --file service-app/target/service-app-1.0.0-all.jar
~~~

Trong kết quả (nhiều entries), cần xác minh có:

~~~text
META-INF/services/org.example.spi.GreetingProvider
org/example/spi/GreetingProvider.class
org/example/providers/alpha/AlphaGreetingProvider.class
org/example/providers/beta/BetaGreetingProvider.class
org/example/app/Main.class
META-INF/MANIFEST.MF
~~~

Danh sách trên là **những entry mong đợi**, không phải stdout toàn bộ và không cam kết thứ tự in.

### 16.1. Trích xuất chỉ file service để đọc

Trên Linux/macOS, nếu có `unzip`:

~~~bash
unzip -p service-app/target/service-app-1.0.0-all.jar \
  META-INF/services/org.example.spi.GreetingProvider
~~~

Nội dung về mặt logic cần có **cả hai** class names:

~~~text
org.example.providers.alpha.AlphaGreetingProvider
org.example.providers.beta.BetaGreetingProvider
~~~

**Không nên kiểm tra exact byte-for-byte thứ tự hai dòng** khi mục tiêu là ServiceLoader có thể phát hiện đủ providers. Kiểm tra theo tập tên provider hợp lệ hoặc kết quả runtime.

### 16.2. Chỉ dùng JDK jar tool khi không có unzip

Tại thư mục root, tạo một **thư mục kiểm tra riêng** (Linux/macOS):

~~~bash
mkdir -p inspect-service-jar
cd inspect-service-jar
jar --extract --file ../service-app/target/service-app-1.0.0-all.jar \
  META-INF/services/org.example.spi.GreetingProvider
cat META-INF/services/org.example.spi.GreetingProvider
~~~

Đoạn lệnh này **trích xuất file từ JAR vào thư mục `inspect-service-jar`**, không chỉnh sửa original JAR. Khi chạy đúng vị trí, bạn có thể xóa thư mục kiểm tra sau đó theo nhu cầu. Trên Windows PowerShell, dùng `New-Item`/`Get-Content` hoặc một ZIP viewer để xem resource, không dán lệnh `cat` như một lệnh CMD mặc định.

**Không giải nén JAR nhận từ nguồn không tin cậy** vào thư mục chứa dữ liệu nhạy cảm hoặc production workspace; kiểm tra nguồn và dùng thư mục tách biệt.

## 17. Điều gì xảy ra khi bỏ ServicesResourceTransformer?

Đây là thí nghiệm **chỉ nên thực hiện trên bản sao dự án** để hiểu lỗi, không phải cấu hình cuối:

1. Giữ `ManifestResourceTransformer` để JAR vẫn có entry point.
2. Xóa dòng khai báo `ServicesResourceTransformer` trong `service-app/pom.xml`.
3. Chạy lại `mvn clean package`.
4. Chạy `java -jar service-app/target/service-app-1.0.0-all.jar`.
5. Kiểm `META-INF/services/org.example.spi.GreetingProvider` trong archive mới.

Rủi ro: output archive vẫn chứa hai `.class` provider nhưng resource không được hợp nhất đúng, nên app có thể báo:

~~~text
java.lang.IllegalStateException: Expected 2 providers, found 1
~~~

Đây chỉ là **một lỗi có thể quan sát**, **không phải stdout/stack trace chắc chắn của mọi phiên bản**: tùy collision handling, có thể thấy 0, 1, 2 hoặc lỗi khác. Điểm cần chứng minh là **không thể dựa vào merge mặc định để đảm bảo correctness của Java SPI**.

**Sau thí nghiệm, khôi phục transformer** và chạy lại `mvn clean package`. Chỉ báo hoàn tất nếu smoke test `java -jar ...-all.jar` in đủ hai provider.

## 18. Relocation: đổi package thì META-INF/services phải đổi theo

Maven Shade hỗ trợ **class/package relocation**, ví dụ chuyển implementation classes sang một namespace nội bộ để tránh xung đột với thư viện khác.

Nếu ta thêm mảnh sau vào `configuration` của Shade trong app (không thay nguyên POM ví dụ):

~~~xml
<relocations>
    <relocation>
        <pattern>org.example.providers</pattern>
        <shadedPattern>org.example.internal.shaded.providers</shadedPattern>
    </relocation>
</relocations>
~~~

thì class implementation có thể trở thành:

~~~text
org/example/internal/shaded/providers/alpha/AlphaGreetingProvider.class
org/example/internal/shaded/providers/beta/BetaGreetingProvider.class
~~~

Trong trường hợp này service interface `org.example.spi.GreetingProvider` **không** được relocate, vì nó nằm ngoài pattern. Do đó **tên resource file** vẫn là:

~~~text
META-INF/services/org.example.spi.GreetingProvider
~~~

nhưng **nội dung provider names** phải được cập nhật:

~~~text
org.example.internal.shaded.providers.alpha.AlphaGreetingProvider
org.example.internal.shaded.providers.beta.BetaGreetingProvider
~~~

`ServicesResourceTransformer` có khả năng cập nhật những tên này khi Shade thực hiện relocation. Nếu chỉ copy/nối descriptor dạng text mà không đổi FQCN, ServiceLoader có thể cố tải các class **ở package cũ không còn tồn tại** và ném `ServiceConfigurationError`.

**Ranh giới:** nếu chính service interface cũng bị relocate, cả **tên file sau `META-INF/services/`** và provider class references có thể cần thay theo module/type names đã đổi. Vì vậy transformer chuyên biệt phù hợp hơn việc dùng một transformer chỉ nối text.

Trong thiết kế thư viện public, thường không nên relocate SPI API mà consumers dùng trực tiếp nếu chưa hiểu hậu quả binary compatibility. Ví dụ runnable **không bật relocation** để người học kiểm tra kết quả đầu tiên dễ dàng.

## 19. ServicesResourceTransformer khác AppendingTransformer ra sao?

Một số resource trùng path chỉ cần nối nội dung, nhưng **mỗi định dạng có semantics khác nhau**.

| Loại resource | Transformer thường phù hợp | Lý do |
| --- | --- | --- |
| `META-INF/services/<service-type>` | **`ServicesResourceTransformer`** | Merge tên provider, cập nhật class names khi relocation. |
| `META-INF/MANIFEST.MF` | `ManifestResourceTransformer` | Thay/thiết lập manifest attributes, `Main-Class`. |
| `META-INF/spring.handlers` | `AppendingTransformer` | Nối nội dung những resource có ý nghĩa append theo tài liệu framework. |
| `META-INF/spring.schemas` | `AppendingTransformer` | Tập hợp metadata có cùng path theo cơ chế append phù hợp. |
| Resource bundle `Messages.properties` | `ResourceBundleAppendingTransformer` | Hỗ trợ ghép resource bundles, bao gồm các locales. |
| XML descriptor đặc biệt | `XmlAppendingTransformer` hoặc transformer riêng | Cần hiểu cách nối/merge cấu trúc XML. |
| `META-INF/plexus/components.xml` | `ComponentsXmlResourceTransformer` | Merge Plexus component descriptors. |
| `LICENSE`, `NOTICE` | Transformer/treatment tương ứng giấy phép | Tránh mất ghi nhận nguồn; không xóa tùy tiện. |

Ví dụ `AppendingTransformer` cho một file cụ thể:

~~~xml
<transformer
    implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring.handlers</resource>
</transformer>
~~~

Đây chỉ là **mảnh thêm vào `transformers`**, không phải phần bắt buộc của demo. AppendingTransformer nối contents theo cách chung; nó **không có trách nhiệm chuyên biệt cập nhật tên class Java trong file SPI**. Với `META-INF/services/`, ưu tiên `ServicesResourceTransformer`.

**Không thêm mọi transformer cùng lúc vì “an toàn”**. Các transformer can thiệp vào cùng resource hoặc giả định sai định dạng có thể tạo output hỏng/khó tái lập. Chọn đúng transformer dựa trên file collision thực tế.

## 20. Maven Assembly jar-with-dependencies khác Shade trong bài toán này

Maven Assembly Plugin có predefined descriptor `jar-with-dependencies` để tạo một JAR chứa binary output và các dependencies được **unpack**. Nó hữu ích cho tình huống đóng gói đơn giản. Tuy nhiên tài liệu Apache Maven Assembly nói rõ rằng **jar-with-dependencies chỉ hỗ trợ uber-JAR ở mức cơ bản** và khuyên dùng Shade khi cần điều khiển tinh vi hơn.

So sánh:

| Tiêu chí | Assembly `jar-with-dependencies` | Shade + `ServicesResourceTransformer` |
| --- | --- | --- |
| Kết hợp project classes/dependencies | Có, theo assembly descriptor. | Có, theo Shade artifact selection. |
| Hợp nhất nhiều provider descriptors cùng tên có ý nghĩa Java SPI | **Không nên mặc định kỳ vọng** merge có ý thức SPI. | Có transformer chuyên biệt được thiết kế cho việc này. |
| Relocation Java package/classes | Không phải năng lực chính của built-in `jar-with-dependencies`. | Shade hỗ trợ relocation. |
| Cập nhật tên provider trong `META-INF/services` sau relocation | Không nên kỳ vọng tự động. | `ServicesResourceTransformer` xử lý tương ứng. |
| Manifest Main-Class | Có cách cấu hình archive/manifest theo assembly/archiver. | `ManifestResourceTransformer` cho shaded JAR. |
| Khi nên dùng | Distribution archive đơn giản hoặc có descriptor tổ chức rõ. | Uber-JAR yêu cầu SPI/service metadata merge và relocation. |

Đừng kết luận “Assembly luôn làm mất service descriptor” — cách xử lý collision có thể khác theo cấu hình, dependency order và plugin. Vấn đề là **mẫu jar-with-dependencies không cung cấp bảo đảm semantic merge SPI như transformer chuyên biệt của Shade**. Nếu ứng dụng dùng `ServiceLoader`, hãy kiểm output thật hoặc chọn Shade + transformer.

## 21. minimizeJar có thể làm hỏng provider discovery

Shade có tùy chọn:

~~~xml
<minimizeJar>true</minimizeJar>
~~~

Nó cố loại các class bị xem là không cần thiết theo phân tích phụ thuộc. Điều này có thể giảm dung lượng archive, nhưng code được tải **động** bằng `ServiceLoader`, reflection, annotations, dependency injection hoặc các cơ chế plugin động có thể **không hiển thị như một lời gọi class trực tiếp trong bytecode**.

Ví dụ:

~~~java
ServiceLoader.load(GreetingProvider.class)
~~~

không nhắc đích danh `AlphaGreetingProvider.class` hoặc `BetaGreetingProvider.class`. Một công cụ reachability không nhận diện đúng mô hình động có thể loại class provider hoặc phụ thuộc mà provider chỉ dùng lúc chạy.

Vì vậy demo đặt:

~~~xml
<minimizeJar>false</minimizeJar>
~~~

Đây là lựa chọn có chủ đích cho bài học. **ServicesResourceTransformer giữ descriptor, nhưng không được hiểu là bảo đảm mọi class provider sống sót nếu các công cụ tối giản/filters loại chúng.**

Nếu tổ chức cần minimize:

1. Xem tài liệu Shade version về `minimizeJar` và entry points.
2. Cấu hình exclusions/entryPoints cho các class dùng qua reflection/SPI theo khả năng plugin.
3. Kiểm cả class files và `META-INF/services` trong output.
4. Chạy smoke test `java -jar` thực tế và integration tests liên quan.
5. Cân nhắc ảnh hưởng của dynamic proxies, serializers, ServiceLoader providers và frameworks.

Một JAR nhỏ hơn nhưng làm mất provider sẽ **không phải output đúng** dù Maven báo BUILD SUCCESS.

## 22. Filters, signatures và tài nguyên pháp lý

Uber-JAR hợp nhất nhiều JAR có thể chứa những chữ ký số gắn với **nội dung archive gốc**. Sau khi package/relocate, chữ ký cũ không còn đại diện cho bytes cuối. Do đó nhiều ví dụ Shade loại các file chữ ký cũ dưới `META-INF`:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.RSA</exclude>
            <exclude>META-INF/*.DSA</exclude>
        </excludes>
    </filter>
</filters>
~~~

Điều này giúp tránh một số lỗi kiểu:

~~~text
java.lang.SecurityException: Invalid signature file digest for Manifest main attributes
~~~

nhưng chỉ áp dụng khi vấn đề thực sự là signature metadata cũ sau shading. Không được xem nó là cách loại bỏ rủi ro supply-chain; nguồn dependencies vẫn phải được xác minh và shaded artifact cuối cần integrity/provenance riêng.

**Không viết filter kiểu:**

~~~xml
<exclude>META-INF/**</exclude>
~~~

vì có thể làm mất `META-INF/services`, `META-INF/NOTICE`, `META-INF/LICENSE`, manifest và nhiều metadata quan trọng khác. Có những frameworks phụ thuộc metadata dưới META-INF để chạy.

**Giấy phép:** Khi gộp thư viện của bên thứ ba vào một file để phân phối, phải giữ license/notice đúng điều khoản tương ứng. Shade có transformers như Apache License/Notice transformers, nhưng cần xem project và license thực tế; không xóa file bản quyền chỉ để tránh duplicate warnings.

## 23. Classpath ServiceLoader và JPMS module path không phải cùng cơ chế

Java 9+ hỗ trợ **Java Platform Module System (JPMS)**. Khi chạy **explicit named modules** trên module path, provider có thể được công bố trong `module-info.java` bằng:

~~~java
module org.example.alpha {
    requires org.example.spi;
    provides org.example.spi.GreetingProvider
        with org.example.providers.alpha.AlphaGreetingProvider;
}
~~~

Và module consumer có thể khai báo:

~~~java
module org.example.app {
    requires org.example.spi;
    uses org.example.spi.GreetingProvider;
}
~~~

**Hai đoạn trên chỉ là mảnh minh họa JPMS**, **không phải file của demo chạy classpath ở mục 9–15**. Khi dùng explicit named modules, `uses` và `provides ... with ...` có semantics module-aware; không được giả định copy service files sẽ tái tạo toàn bộ module graph.

Những điểm cần tách:

- **Classpath service providers:** thường đăng ký bằng file `META-INF/services/<service-type>`.
- **Explicit named JPMS providers:** đăng ký bằng `provides ... with ...` trong `module-info.java`.
- **Automatic modules:** có quy tắc bridge/migration riêng, cần kiểm docs và manifest/module name.
- **Shading nhiều explicit modular JAR thành một file:** có thể gây collision `module-info.class`, split packages và mất semantics module graph. `ServicesResourceTransformer` **không phải công cụ merge các `module-info.class`**.
- Demo dùng `java -jar ...-all.jar` kiểu **classpath launcher**; không cam kết output là JPMS named module được khai báo đúng.

Nếu hệ thống thực sự cần modular runtime image `jlink` hoặc named modules, hãy thiết kế và kiểm thử chiến lược packaging JPMS riêng thay vì chỉ chèn ServicesResourceTransformer.

## 24. Quan hệ với Maven dependency scope và artifact filtering

Shade chỉ có thể xử lý những artifact được chọn vào shaded result theo config/effective dependency graph. Có `ServicesResourceTransformer` cũng **không bổ sung JAR dependency đang thiếu**.

Trong ví dụ app:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.shade</groupId>
        <artifactId>spi-api</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>org.example.shade</groupId>
        <artifactId>provider-alpha</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>org.example.shade</groupId>
        <artifactId>provider-beta</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Cả hai provider JARs là **compile/runtime dependencies** trong POM app. Vì vậy chúng được Maven resolve cùng project, và Shade có thể include chúng khi tạo uber-JAR.

Những sai sót thường gặp:

- Đặt provider dependency ở `scope=test`: test classpath có thể thấy provider, nhưng production shaded output không được bảo đảm chứa.
- Đặt provider là `provided` do nghĩ runtime JDK tự cung cấp: khi chạy fat JAR standalone, provider có thể thiếu.
- Dùng Shade `artifactSet/excludes` hoặc `filters` loại một provider JAR hoặc class.
- Dùng `minimizeJar` và provider class bị loại do dynamic loading.
- Dùng classifier sai: app chạy thin JAR thay vì `-all.jar`.
- Parent chỉ khai báo provider trong `dependencyManagement` nhưng app **không có dependency thật**.

Để debug, dùng:

~~~bash
mvn -pl :service-app -am org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Đây là lệnh cho **reactor demo đã tạo đủ files**. Nó giúp xem project dependency graph, **không** xác minh rằng Shade đã giữ đủ service metadata. Phải kiểm cả output JAR và chạy app.

## 25. Một lớp kiểm thử đủ mạnh: test classpath và smoke test sau Shade

Hãy coi chất lượng build có **hai cửa kiểm tra**:

### Cửa 1: unit test khi dependencies còn tách JAR

~~~bash
mvn -B -ntp clean test
~~~

Với cấu trúc mẫu, JUnit `ServiceLoadingTest` kỳ vọng danh sách:

~~~text
alpha=Hello Maven from Alpha
beta=Hello Maven from Beta
~~~

Đây là **giá trị Java List expected**, không phải stdout mặc định của Surefire. Chỉ khi Surefire thực thi test và assertions pass mới kết luận providers có mặt trên test classpath.

### Cửa 2: integration/smoke test với shaded output

~~~bash
mvn -B -ntp clean package
java -jar service-app/target/service-app-1.0.0-all.jar
~~~

App thực tế xác nhận:

~~~text
providers=2
alpha=Hello Maven from Alpha
beta=Hello Maven from Beta
~~~

Đây mới là **bằng chứng end-to-end** rằng output sau resource transformation hoạt động. Nếu cùng một JAR được gửi vào container/serverless/CI, smoke test nên được chạy trên chính artifact sẽ được triển khai.

Ví dụ shell Bash để CI tự kiểm tra output, khi đang ở root:

~~~bash
actual="$(java -jar service-app/target/service-app-1.0.0-all.jar)"
expected="$(printf 'providers=2\nalpha=Hello Maven from Alpha\nbeta=Hello Maven from Beta')"
test "$actual" = "$expected"
~~~

Đoạn trên dùng **Bash/Zsh style**; không phải cú pháp PowerShell hay CMD. `test` exit code 0 khi khớp, non-zero khi không khớp; job CI cần được cấu hình dừng khi exit code khác 0. Không sử dụng script này khi output app có thông tin động như timestamp/random provider order chưa được sort.

Trên Windows, có thể chạy riêng `java -jar ...` và đối chiếu stdout; hoặc viết assertions tương đương bằng PowerShell theo quy ước CI.

## 26. Troubleshooting: lỗi liên quan META-INF/services và Shade

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Trên classpath thấy 2 providers, trong fat JAR chỉ thấy 1. | Hai file service descriptor trùng path, không được merge đúng. | Thêm/kiểm `ServicesResourceTransformer`, đọc merged service file. |
| Provider `.class` tồn tại nhưng ServiceLoader không phát hiện. | Thiếu file `META-INF/services` hoặc thiếu tên provider trong file. | Xem resource file bên trong JAR, kiểm path và UTF-8. |
| `ServiceConfigurationError: Provider ... not found` | Descriptor trỏ tên class cũ sau relocation hoặc class bị filters/minimize bỏ. | So descriptor với class paths trong output. |
| `ServiceConfigurationError: ... not a subtype` | Provider không implements đúng SPI type hoặc classloader identity khác. | Kiểm interface version, package và dependency graph/runtime loader. |
| `ServiceConfigurationError: Unable to get public no-arg constructor` | Provider class không thỏa classpath provider constructor contract. | Dùng public concrete class + public no-arg constructor. |
| Shade tạo JAR thành công nhưng `java -jar` báo không có main manifest. | Thiếu `ManifestResourceTransformer` hoặc chạy nhầm thin JAR. | Kiểm `Main-Class` và đúng `-all.jar`. |
| `java -jar` lỗi `NoClassDefFoundError` dù service descriptor đủ. | Thiếu class/other runtime dependency được provider cần. | Kiểm included dependencies, filtering, scopes và compile/runtime graph. |
| App chạy provider theo thứ tự không ổn định. | Discovery order không phải hợp đồng nghiệp vụ. | Sort/priority ID trong code, không dựa thứ tự trong descriptor. |
| Mất provider chỉ khi bật `minimizeJar=true`. | Bytecode analysis không thấy dynamic ServiceLoader references. | Tắt minimize hoặc cấu hình entry points/retention; smoke test. |
| `META-INF/services` biến mất khỏi JAR sau filtering. | Filter quá rộng như `META-INF/**`. | Giới hạn filters, không loại service metadata. |
| Có `ServiceConfigurationError` sau relocation. | Metadata provider names không được rewrite đúng. | Dùng transformer chuyên biệt, xem relocated class names. |
| Assembly `jar-with-dependencies` không giữ đủ SPI providers. | Collision của unpacked service files không được merge semantic. | Dùng Shade với ServicesResourceTransformer hoặc phân phối JARs tách rời. |
| Có 2 provider names trong resource nhưng chỉ 1 provider thực sự nạp. | Provider thiếu constructor/API/deps hoặc filter/loader lỗi. | Chạy `java -jar`, xem full exception và JAR entries, không chỉ đếm dòng. |
| Lỗi signature digest sau shading. | Chữ ký archive cũ không hợp lệ sau khi đổi nội dung. | Xem signature metadata, dùng filters phù hợp và ký lại artifact cuối nếu chính sách yêu cầu. |
| Không thấy `-all.jar`. | `shadedArtifactAttached`/`shadedClassifierName` khác config, shade goal không được bind/skip. | Xem effective POM, logs shade:shade và output directory. |
| CI chỉ upload thin JAR. | Dùng wildcard hoặc path sai. | Upload đúng `service-app-1.0.0-all.jar` khi đó là target runtime. |
| Build reactor fail do provider artifacts chưa có. | Thiếu project dependencies hoặc chỉ build app module không `-am`. | Dùng root build hoặc `-pl :service-app -am`. |
| Không dùng được provider trong named module runtime. | JPMS `uses/provides`/module graph khác classpath mode. | Kiểm `module-info.java` và runtime launcher, không chữa mù bằng service append. |
| Duplicated provider names trong descriptor. | Multiple provider JARs đăng ký cùng implementation. | JDK ServiceLoader bỏ qua trùng tên khi đọc; tuy nhiên review duplicate versions/graph để tránh xung đột. |

**Chuỗi điều tra hiệu quả:** Maven dependency graph → JAR inputs → Shade transformer/filters/relocation/minimize → merged descriptor và class files → manifest/classloader → chạy `java -jar` → báo cáo smoke test. Không chỉ nhìn `BUILD SUCCESS` ở giai đoạn Maven package.

## 27. Những nguyên tắc bảo mật và độ tin cậy

Một uber-JAR chứa bytes của nhiều dependency, thường chạy với quyền của ứng dụng. Việc merge metadata thay đổi cách phát hiện và thực thi provider code; vì vậy cần kiểm soát:

1. **Nguồn dependency:** chỉ dùng Maven repository tin cậy và version được quản lý/pin.
2. **SPI implementation code:** ServiceLoader có thể tạo instance provider; provider có thể thực thi code trong constructor/static initializer, không được coi là sandbox.
3. **Không tin tên provider trong descriptor một cách mù quáng:** nếu xuất hiện implementation không mong muốn, phân tích dependency source và SBOM.
4. **Giữ LICENSE/NOTICE** và bảo đảm tuân thủ license khi repackaging.
5. **Không phát hành debug resources/secrets** vô tình nằm trong `src/main/resources`.
6. **Loại signature metadata lỗi thời có lý do**, và ký/provenance artifact cuối theo chính sách phát hành.
7. **Minimize với kiểm thử**, không chỉ dựa vào static analysis khi có reflection/SPI.
8. **Bật smoke tests sau Shade**, kiểm provider count hoặc provider IDs thực sự.
9. **Kiểm tra artifact classifier và đường dẫn** trước khi upload/triển khai.
10. **Đánh giá JPMS/classloader** riêng nếu ứng dụng dùng framework/container có plugin loaders khác application classloader.
11. **Ghi lại Shade/plugin versions** và lý do transformers/exclusions trong code review.
12. **Tránh tự ý sửa service descriptor bằng shell sau package** vì nó làm artifact diverge khỏi POM/reproducibility.
13. **Tách compile-time tests và packaged-artifact tests** trong CI; một test pass trước Shade chưa bảo đảm archive cuối đúng.
14. **Không giả định mọi provider nên được đưa vào một fat JAR:** một số provider cung cấp implementation tùy môi trường; hãy chọn dependencies có chủ đích và hiểu chiến lược discovery.

## 28. Checklist review trước khi giao executable shaded JAR

- [ ] Dự án có SPI interface rõ ràng và mỗi provider implements đúng API.
- [ ] Provider classes cụ thể, public, có public no-arg constructor khi dùng classpath descriptors.
- [ ] File resources đặt ở `src/main/resources/META-INF/services/<service-FQCN>`.
- [ ] Descriptor UTF-8, nội dung đúng fully qualified **provider class names**, không chứa `.class`/Java source syntax.
- [ ] Mọi provider artifacts cần thiết là Maven dependencies được include vào shaded output.
- [ ] Shade goal bind vào phase `package` trong đúng module.
- [ ] Có `ServicesResourceTransformer`, không chỉ `ManifestResourceTransformer`.
- [ ] Có manifest `Main-Class` khi cần chạy `java -jar`.
- [ ] Nếu attach classifier `all`, CI chạy/upload **`-all.jar`**, không nhầm thin JAR.
- [ ] Filters không loại `META-INF/services/**`; signature excludes được cân nhắc riêng.
- [ ] Nếu relocate class/packages, descriptor sau Shade tham chiếu tên class mới.
- [ ] `minimizeJar` không loại providers được load động; có smoke test kiểm chứng.
- [ ] Đã inspect JAR entries và merged service configuration file.
- [ ] Đã chạy app thực qua `java -jar`, xác nhận **đủ provider IDs**.
- [ ] Đã phân biệt classpath SPI descriptors và JPMS module declarations nếu dự án modular.
- [ ] Đã kiểm licensing/NOTICE/security của dependencies được gom.
- [ ] Parent/child Maven reactor dependencies đúng; không build Shade ở aggregator quá sớm.
- [ ] CI lưu output artifact đúng version/classifier và kiểm soát provenance.
- [ ] Thứ tự provider được ứng dụng xử lý có chủ đích, không phụ thuộc thứ tự merge metadata.

## 29. Tự kiểm tra kiến thức

1. **Tại sao hai provider JARs có cùng file `META-INF/services/org.example.spi.GreetingProvider` vẫn hoạt động khi chúng nằm riêng trên classpath?**  
   Bởi ServiceLoader có thể tìm nhiều service configuration resources của cùng service trong classloader context; mỗi file mô tả provider riêng.

2. **Chỉ unpack mọi JAR vào một archive có đủ để giữ cả hai provider không?**  
   Không bảo đảm. Descriptor cùng path cần được hợp nhất có ý nghĩa.

3. **Transformer nào xử lý `META-INF/services`?**  
   `org.apache.maven.plugins.shade.resource.ServicesResourceTransformer`.

4. **Transformer nào viết `Main-Class` cho executable shaded JAR?**  
   `ManifestResourceTransformer`; nó không thay thế transformer SPI.

5. **File service descriptor nên mang tên service hay implementation?**  
   Tên **service type**; bên trong ghi tên đầy đủ của provider implementations.

6. **Nội dung descriptor `org.example.providers.alpha.AlphaGreetingProvider.class` có đúng không?**  
   Không. Phải ghi tên class đầy đủ không có đuôi `.class`.

7. **Nếu bật relocation cho `org.example.providers`, cần lưu ý metadata nào?**  
   Tên class provider trong service descriptor phải đổi theo; `ServicesResourceTransformer` hỗ trợ việc đó.

8. **Vì sao JUnit `ServiceLoadingTest` pass nhưng executable `-all.jar` vẫn có thể lỗi?**  
   JUnit chạy **trước Shade** trên các JAR dependencies riêng, không kiểm output đã merge.

9. **Vì sao demo sort kết quả của ServiceLoader?**  
   Vì discovery order không nên được coi là hợp đồng nghiệp vụ; sort theo ID cho stdout xác định.

10. **`minimizeJar=true` có thể gây vấn đề gì?**  
    Provider được load động có thể bị loại nếu static analysis không nhận diện; cần giữ class hoặc kiểm nghiệm runtime.

11. **Có nên dùng `META-INF/**` làm filter exclude không?**  
    Không tùy tiện; nó có thể xóa service descriptors, manifest và license/notice.

12. **Assembly jar-with-dependencies có thay thế hoàn toàn Shade khi cần SPI merge/relocation không?**  
    Không. Assembly hỗ trợ uber-JAR cơ bản, còn Shade có transformers và relocation chuyên biệt.

13. **`shadedArtifactAttached=true` với `shadedClassifierName=all` tạo ra hai JAR có vai trò gì?**  
    Thin main JAR và attached shaded JAR classifier `all`; runtime smoke test phải chọn đúng `-all.jar`.

14. **Tại sao dùng `ServiceLoader` không có nghĩa phải viết `module-info.java`?**  
    ServiceLoader hỗ trợ service descriptors trên classpath; JPMS named modules là cơ chế khác.

15. **Một merged descriptor có đúng hai dòng provider đã bảo đảm app chạy được chưa?**  
    Chưa. Phải kiểm class tồn tại, constructor/API/dependencies/classloader đúng và chạy thực tế.

## 30. Tài liệu tham khảo chính thức

- [Apache Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html): `ServicesResourceTransformer`, `AppendingTransformer`, `ManifestResourceTransformer` và các loại resource khác.
- [Apache Maven Shade Plugin — Usage](https://maven.apache.org/plugins/maven-shade-plugin/usage.html): cấu hình goal `shade:shade` tại phase `package`.
- [Apache Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html): `Main-Class` với `ManifestResourceTransformer`.
- [Apache Maven Shade Plugin — shade:shade Goal](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html): `shadedArtifactAttached`, `shadedClassifierName`, `createDependencyReducedPom`, `minimizeJar`, `filters` và relocations.
- [Apache Maven Shade Plugin — Attaching the Shaded Artifact](https://maven.apache.org/plugins/maven-shade-plugin/examples/attached-artifact.html): main artifact so với classifier của shaded output.
- [Apache Maven Shade Plugin — Class Relocation](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html): đổi package/classes trong uber-JAR.
- [Apache Maven Assembly Plugin — Predefined Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html): built-in `jar-with-dependencies` có hỗ trợ uber-JAR cơ bản.
- [Oracle Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): SPI, file `META-INF/services`, provider constructor, ServiceConfigurationError và JPMS.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes và transitive dependencies.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor và project dependency sort order.
- [Apache Maven Surefire Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/usage.html): chạy JUnit test trước phase package.

**Kết luận:** Khi nhiều JAR cùng đăng ký provider cho một SPI, việc xây uber-JAR cần **hợp nhất `META-INF/services` theo đúng ngữ nghĩa Java ServiceLoader**. Với Maven Shade, dùng **`ServicesResourceTransformer`** để gộp và cập nhật provider class names, kết hợp **`ManifestResourceTransformer`** nếu muốn executable JAR. Đừng chỉ dựa vào `BUILD SUCCESS` hoặc sự tồn tại của `.class`: hãy kiểm merged descriptor và chạy chính file `-all.jar` để xác nhận ServiceLoader nhìn thấy đầy đủ providers.
