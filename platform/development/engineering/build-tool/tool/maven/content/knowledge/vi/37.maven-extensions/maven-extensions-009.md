# Phân biệt build extension, core extension và plugin thông thường trong Apache Maven

## 1. Đặt vấn đề: ba cơ chế đều mở rộng Maven nhưng không thay thế nhau

Apache Maven là công cụ tổ chức project model, build lifecycles và thực thi **plugin goals**. Hầu hết công việc build Java — compile, unit test, đóng JAR, tạo Javadoc, chạy code generator hoặc deploy — chỉ cần Maven **plugin thông thường**. Khi cần thêm loại `packaging`, đăng ký Maven component/transport, hoặc thay đổi hành vi Maven từ lúc khởi tạo session, ta có thể cần **extension**.

Có ba cơ chế phải phân biệt:

1. **Ordinary Maven plugin**: JAR có một hoặc nhiều **Mojo goals**; Maven gọi goal trực tiếp từ CLI hoặc theo lifecycle phase. Ví dụ `maven-compiler-plugin:compile`, `maven-surefire-plugin:test`, `maven-jar-plugin:jar`.
2. **Build extension**: JAR được Maven nạp khi xử lý project/build context, muộn hơn core extension. Nó có thể đăng ký components, transports hoặc lifecycle mappings khi artifact thật sự triển khai các extension points. Hai cách POM: `<build><extensions><extension>` và `<build><plugins><plugin><extensions>true</extensions>`.
3. **Core extension**: JAR được Maven nạp **sớm trong bootstrap**, trước khi xây dựng đầy đủ project model/execution plan. Khai phổ biến tại `.mvn/extensions.xml`. Dùng cho những tính năng cần can thiệp Maven core/session đủ sớm; không chỉ là “plugin chạy sớm hơn”.

**Nguyên tắc:** đừng bật `<extensions>true</extensions>` cho mọi plugin; cũng đừng dùng core extension để giải quyết một task chỉ cần `@Mojo` chạy ở `verify`. Extensions thay thời điểm/phạm vi nạp code, có rủi ro classloading/tương thích/bảo mật lớn hơn ordinary plugin.

### Bạn sẽ học được

- So sánh chức năng, loading time, POM descriptors, classloaders, phạm vi tác động và khả năng triển khai.
- Phân biệt plugin goal/Mojo với lifecycle phase và custom packaging.
- Tạo plugin Java 17 với `maven-plugin-plugin:3.16.0`, `@Mojo` và descriptor `META-INF/maven/plugin.xml`.
- Gọi custom goal trực tiếp và bind nó vào `validate` trong một consumer POM.
- Hiểu Apache Felix Maven Bundle Plugin dùng `extensions=true` để cung cấp packaging `bundle`.
- So sánh **cùng Apache Maven Build Cache Extension 1.3.0** khi khai ở POM `build/extensions` và ở `.mvn/extensions.xml`.
- Hiểu Maven 3.9+, Maven 3.10+ và Maven 4 có khác biệt về extension descriptor, APIs và global locations.
- Chẩn đoán `Unknown packaging`, missing plugin descriptor, classloading conflicts, extension resolution, goals không chạy và bootstrap errors.
- Chọn cơ chế ít phạm vi tác động nhất; bảo vệ CI secrets, pinned versions và khả năng tái lập.

## 2. Bảng so sánh cốt lõi

| Tiêu chí | Plugin thông thường | Build extension | Core extension |
| --- | --- | --- | --- |
| Mục đích | Thực thi task/goal | Mở rộng Maven cho project/build | Can thiệp core/session lúc khởi tạo |
| Nạp khi nào | Khi cần thực thi goal / lập execution plan | Muộn, khi xử lý POM/project | Sớm, trước phần lớn project evaluation |
| Vị trí | `build/plugins/plugin` | `build/extensions/extension` hoặc plugin `extensions=true` | `.mvn/extensions.xml` hoặc các cơ chế core |
| Có Mojo goal? | Thường có | Có thể có hoặc không | Có thể không |
| Bản chất | Executable goal/plugin descriptor | Maven component/SPIs/lifecycle mappings | Core components/SPIs, early hooks |
| Ví dụ | Compiler, Surefire, custom `greet` | Felix Bundle Plugin, build cache khai trong POM | Build cache khai trong `.mvn/extensions.xml` |
| Classloading | Plugin realm riêng | Build extension realm, project realm liên quan | Core extension classloader/container |
| Phạm vi | Goal khi được gọi | Project/build context | Maven runtime/session sớm hơn |
| Dùng khi nào | Mặc định | Custom packaging hoặc build extension points | Early lifecycle, EventSpy/core behavior |
| Rủi ro | Cần pin plugin/deps | Thêm dependency-injection/lifecycle interactions | Có thể ảnh hưởng bootstrap và toàn build |

Từ `extension` còn là **đuôi file artifact** (`.jar`, `.pom`). Đừng nhầm artifact file extension với Maven build/core extension. Tương tự, thêm JAR vào `<dependencies>` chỉ để ứng dụng compile/runtime, không tự đăng ký JAR đó làm Maven plugin hoặc extension.

### 2.1. Sơ đồ loading

~~~text
mvn command + user/global settings + .mvn/
                     |
                     v
            Maven bootstrap/session
            CORE EXTENSIONS nạp sớm
                     |
                     v
          POM/project model processing
           BUILD EXTENSIONS nạp muộn
                     |
                     v
       Packaging lifecycle mappings, goals
                     |
                     v
       Ordinary PLUGIN MOJOS thực thi
       validate -> compile -> test -> package ...
                     |
                     v
              Output artifacts
~~~

Sơ đồ này **khái quát**, không phải mọi classloading step nội bộ của Maven. Điểm chính là một callback lúc session bắt đầu có thể đã đi qua trước khi Maven đọc `build/extensions` từ POM, còn `.mvn/extensions.xml` có thể đăng ký extension kịp thời.

## 3. Mojo, plugin, goal, phase, packaging: năm khái niệm không giống nhau

**Mojo** là một class thực thi Maven plugin action, thường `extends AbstractMojo` và có `execute()`. **Goal** là tên thao tác được Maven plugin descriptor công bố. Một plugin chứa một hoặc nhiều goals. **Phase** (`validate`, `compile`, `package`, `verify`, `install`, `deploy`) nằm trong Maven lifecycle. **Execution/binding** quyết định goal nào được chạy tại phase nào. **Packaging** (`jar`, `war`, `pom`, `bundle`...) ảnh hưởng tập goals mặc định được Maven bind.

Ví dụ Maven `jar` lifecycle thường gọi resources, compiler, surefire và jar goals ở những phases phù hợp. Vì vậy `mvn package` có thể compile/test/package dù POM không khai một execution thủ công cho từng goal.

Đối với custom plugin:

- `@Mojo(name="greet")` định nghĩa goal `greet`.
- `@Mojo(defaultPhase=VALIDATE)` chỉ định default phase cho goal **khi được binding theo cách có hiệu lực**, không tự khiến mọi `mvn validate` chạy goal đó.
- `<executions><execution><phase>validate</phase><goals><goal>greet</goal>` trong consumer POM mới là một cách rõ ràng để đăng ký execution.
- `pluginManagement` quản lý cấu hình/version cho plugin khi được dùng; không tạo custom execution mới chỉ vì có entry quản lý.
- `reporting/plugins` tạo reports cho Maven Site; reporting plugin không mặc nhiên là build/core extension.

### 3.1. Ví dụ plugin bình thường

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là một **POM fragment**, không phải toàn project. Compiler Plugin có `compile` và `testCompile` goals, không cần `extensions=true` để làm công việc thường ngày.

### 3.2. Plugin class realm không phải application classpath

Maven quản lý plugin realm riêng để nạp Mojo và plugin dependencies. Một dependency trong `project.dependencies` không tự xuất hiện trong plugin realm, và `plugin.dependencies` không mặc nhiên đóng vào runtime JAR của ứng dụng. Đừng dùng `extensions=true` để chữa tùy tiện một `ClassNotFoundException` do khai dependencies sai.

## 4. Lab 1: tự tạo một Maven plugin Java 17 với goal `greet`

Lab này hoàn toàn có thể chạy bằng Java 17/Maven 3.9.x khi máy tải được Maven Plugin Tools và APIs. **Không cần core/build extension**.

### 4.1. Cấu trúc

~~~text
maven-greeting-plugin/
├── pom.xml
└── src/main/java/dev/example/mojo/GreetMojo.java

greeting-consumer/
└── pom.xml
~~~

Đầu tiên build `maven-greeting-plugin` và install vào local repo; sau đó consumer dùng artifact `dev.example:maven-greeting-plugin:1.0.0`. Dùng phiên bản `maven-plugin-tools:3.16.0` đã được Maven Plugin Tools phát hành, `maven-plugin-api:3.9.16` (scope `provided`) và JDK 17; những phiên bản này minh họa Maven 3 API, không khẳng định tương thích với mọi Maven 4 prerelease.

### 4.2. POM đầy đủ của plugin project

Tạo `maven-greeting-plugin/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>maven-greeting-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <maven-plugin-tools.version>3.16.0</maven-plugin-tools.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.16</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${maven-plugin-tools.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${maven-plugin-tools.version}</version>
                <configuration>
                    <goalPrefix>greeting</goalPrefix>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`packaging=maven-plugin` kích hoạt lifecycle mapping cho **tạo Maven plugin** và quá trình sinh descriptor. Nó **không tự biến JAR này thành build extension**. `maven-plugin-api` và `maven-plugin-annotations` dùng `provided` vì Maven runtime cung cấp API tương ứng.

### 4.3. Code GreetMojo.java đầy đủ

Tạo `src/main/java/dev/example/mojo/GreetMojo.java`:

~~~java
package dev.example.mojo;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

@Mojo(
        name = "greet",
        defaultPhase = LifecyclePhase.VALIDATE,
        threadSafe = true
)
public final class GreetMojo extends AbstractMojo {

    @Parameter(
            property = "greeting.name",
            defaultValue = "Maven"
    )
    private String name;

    @Override
    public void execute() throws MojoExecutionException {
        String normalized = name == null || name.isBlank()
                ? "Maven"
                : name.trim();
        getLog().info(
                "Hello from Maven plugin, " + normalized + "!");
    }
}
~~~

Ý nghĩa:

- `@Mojo(name="greet")` tạo descriptor cho goal `greet`.
- `@Parameter` cho phép cấu hình bằng `-Dgreeting.name=Java` hoặc `<configuration>`.
- `execute()` là nơi thực thi code, log qua Maven.
- `threadSafe=true` chỉ phù hợp nếu Mojo thật sự an toàn khi chạy Maven parallel builds.
- `defaultPhase` không tự thêm goal vào mọi lifecycle không có execution.

### 4.4. Build và xem descriptor

Trong thư mục `maven-greeting-plugin`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean install
jar tf target/maven-greeting-plugin-1.0.0.jar
~~~

Sau khi thành công, JAR cần chứa `dev/example/mojo/GreetMojo.class` và `META-INF/maven/plugin.xml`. Đó là **descriptor** Maven dùng để biết goals/parameters. `jar tf` còn có những entries khác. Nếu descriptor thiếu, xem packaging `maven-plugin` và `maven-plugin-plugin`.

### 4.5. Gọi goal trực tiếp

Sau khi plugin đã `install`:

~~~bash
mvn -B -ntp dev.example:maven-greeting-plugin:1.0.0:greet -Dgreeting.name=Java
~~~

Dòng thông điệp do Mojo ghi ra trong Maven logs:

~~~text
Hello from Maven plugin, Java!
~~~

Đó là **dòng dự kiến từ code**, không phải toàn bộ stdout Maven. Không cần `.mvn/extensions.xml` và không cần `extensions=true`.

### 4.6. POM đầy đủ của consumer bind goal vào `validate`

Tạo `greeting-consumer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>greeting-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>dev.example</groupId>
                <artifactId>maven-greeting-plugin</artifactId>
                <version>1.0.0</version>
                <configuration>
                    <name>Team</name>
                </configuration>
                <executions>
                    <execution>
                        <id>say-hello</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>greet</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy từ `greeting-consumer`:

~~~bash
mvn -B -ntp validate
~~~

Dòng thông điệp dự kiến:

~~~text
Hello from Maven plugin, Team!
~~~

Maven thực thi goal vì `<execution>` đã bind `greet` vào `validate`. Nếu xóa execution, chỉ còn plugin declaration/ `@Mojo(defaultPhase)` thì `mvn validate` **không tự gọi** custom goal.

### 4.7. Cách kiểm plugin mà không gọi goal

~~~bash
mvn -B -ntp help:describe -Dplugin=dev.example:maven-greeting-plugin:1.0.0 -Dgoal=greet -Ddetail
~~~

Help Plugin đọc plugin descriptor và trình bày goals/parameters; **nó không chạy `GreetMojo.execute()`**. Nếu CLI prefix `greeting:greet` không resolve vì custom `groupId` chưa có trong pluginGroups metadata, dùng GAV goal đầy đủ như ví dụ bên trên.

## 5. Build extension: hai cơ chế đăng ký trong POM

### 5.1. Khai `<build><extensions>`

Ví dụ artifact chuyên cung cấp components:

~~~xml
<build>
    <extensions>
        <extension>
            <groupId>org.apache.maven.extensions</groupId>
            <artifactId>maven-build-cache-extension</artifactId>
            <version>1.3.0</version>
        </extension>
    </extensions>
</build>
~~~

Đây là POM fragment, không phải `<dependencies>`. Maven tải JAR extension để đăng ký components vào project/build context. Apache Maven Build Cache Extension **1.3.0** hỗ trợ cách này, nhưng docs **ưu tiên khai core extension** qua `.mvn/extensions.xml` do cần cơ hội tích hợp sâu hơn vào Maven runtime.

### 5.2. Khai plugin có `<extensions>true</extensions>`

Ví dụ plugin vừa cung cấp goals vừa cung cấp build extension components:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.felix</groupId>
            <artifactId>maven-bundle-plugin</artifactId>
            <version>6.2.0</version>
            <extensions>true</extensions>
            <configuration>
                <instructions>
                    <Bundle-SymbolicName>dev.example.osgi.demo</Bundle-SymbolicName>
                    <Export-Package>dev.example.osgi</Export-Package>
                </instructions>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Apache Felix Maven Bundle Plugin có goal `bundle` và hỗ trợ `packaging=bundle` thông qua extension/lifecycle mapping. Bản `6.2.0` xuất hiện trong Apache release catalog ngày 18/09/2026; dự án nên kiểm tương thích bản Maven/JDK thực tế.

**Sự khác nhau về XML:**
- `build/extensions/extension` khai artifact bằng `<extension>` số ít.
- `build/plugins/plugin/extensions` là cờ boolean `<extensions>true</extensions>` cho plugin.
- Không đặt `extensions=true` trên mọi compiler/test plugin. Chỉ bật khi docs của artifact yêu cầu.

### 5.3. Thời điểm nạp

Theo Maven Using Extensions Guide, build extensions được nạp **muộn** so với core extensions. Chúng tác động tới project realm và Maven components phù hợp, nhưng không thể quay ngược thời gian để nhận những callbacks đã chạy khi Maven khởi tạo session. Extension nào thật sự cần `afterSessionStart` hoặc early EventSpy phải xem xét core-loading.

## 6. Lab 2: build extension tạo custom packaging `bundle`

### 6.1. Thư mục và môi trường

~~~text
osgi-demo/
├── pom.xml
└── src/main/java/dev/example/osgi/GreetingService.java
~~~

Yêu cầu JDK 17+, Maven 3.9.x có thể resolve Felix Maven Bundle Plugin. Đoạn code sau chỉ minh họa packaging OSGi, không yêu cầu OSGi container/runtime.

### 6.2. Full POM

Tạo `osgi-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example.osgi</groupId>
    <artifactId>osgi-demo</artifactId>
    <version>1.0.0</version>
    <packaging>bundle</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.felix</groupId>
                <artifactId>maven-bundle-plugin</artifactId>
                <version>6.2.0</version>
                <extensions>true</extensions>
                <configuration>
                    <instructions>
                        <Bundle-SymbolicName>dev.example.osgi.demo</Bundle-SymbolicName>
                        <Export-Package>dev.example.osgi</Export-Package>
                    </instructions>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`bundle` không phải packaging Maven core mặc định như `jar` hoặc `war`. Felix build extension phải giúp Maven biết lifecycle mapping cho `bundle`. Nếu chỉ đổi `packaging=jar` thành `bundle` và không kích hoạt extension, có thể gặp `Unknown packaging: bundle`.

### 6.3. Java 17 source

Tạo `src/main/java/dev/example/osgi/GreetingService.java`:

~~~java
package dev.example.osgi;

public final class GreetingService {
    private GreetingService() {
    }

    public static String message() {
        return "OSGi build extension OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 6.4. Build, chạy Java và kiểm manifest

Trong `osgi-demo`:

~~~bash
mvn -B -ntp clean package
java -cp target/classes dev.example.osgi.GreetingService
jar tf target/osgi-demo-1.0.0.jar
~~~

Stdout của Java main:

~~~text
OSGi build extension OK
~~~

Các dấu hiệu cần tìm trong JAR gồm `dev/example/osgi/GreetingService.class` và `META-INF/MANIFEST.MF`. Có thể trích manifest ở thư mục `inspect` riêng:

~~~bash
mkdir -p inspect
cd inspect
jar xf ../target/osgi-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Lệnh `mkdir -p`, `cat` dành cho Linux/macOS; trên Windows PowerShell dùng `New-Item -ItemType Directory` và `Get-Content`. Manifest thường có OSGi headers như `Bundle-SymbolicName`, `Bundle-ManifestVersion`, `Export-Package`. Không khẳng định toàn bộ manifest bytes, vì Bnd/plugin có thể sinh thêm metadata.

### 6.5. Bỏ extension để thấy sự khác biệt

Nếu bạn xóa `<extensions>true</extensions>` nhưng giữ `<packaging>bundle</packaging>`, Maven có thể fail trước khi compile do không nhận loại packaging. Thêm lại `extensions=true` để khôi phục. Trong tình huống chỉ muốn tạo OSGi manifest mà vẫn giữ `jar` packaging, Felix docs có cách bind `bundle:manifest` và JAR plugin để đóng gói manifest, **không nhất thiết** phải đổi packaging sang `bundle`.

## 7. Core extension: được nạp khi Maven bootstrap

### 7.1. Cấu hình thông dụng `.mvn/extensions.xml`

Core extension project-level được Maven hỗ trợ từ **3.3.1**. File nằm trong directory `.mvn` tại root Maven project/multimodule.

Ví dụ dùng Apache Maven Build Cache Extension `1.3.0`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.0.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://maven.apache.org/EXTENSIONS/1.0.0
                                https://maven.apache.org/xsd/core-extensions-1.0.0.xsd">
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

`extensions.xml` là Maven **core descriptor**; không phải POM. `<extensions>` là root, `<extension>` có GAV; không cần `<executions>` hoặc `<extensions>true</extensions>`.

**Version caveat:** Maven 3.3.1 biết cơ chế core descriptor, nhưng **Build Cache Extension 1.3.0 yêu cầu Maven 3.9.0+** theo Apache docs. XML 1.0.0 chỉ dùng các fields cơ bản. Maven 3-LATEST có descriptor schema `EXTENSIONS/1.1.0` bổ sung `classLoadingStrategy`; Maven 4 có schema `1.2.0` và `configuration` — dùng đúng schema theo Maven runtime.

### 7.2. Lab 3: core cache extension trên project Java 17

Tạo thư mục:

~~~text
cache-core-demo/
├── pom.xml
├── .mvn/
│   └── extensions.xml
└── src/main/java/dev/example/cache/CacheDemo.java
~~~

File `.mvn/extensions.xml` có nội dung như mục 7.1. POM **đầy đủ**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example.cache</groupId>
    <artifactId>cache-core-demo</artifactId>
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
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/dev/example/cache/CacheDemo.java`:

~~~java
package dev.example.cache;

public final class CacheDemo {
    private CacheDemo() {
    }

    public static void main(String[] args) {
        System.out.println("CORE EXTENSION PROJECT OK");
    }
}
~~~

Dùng JDK 17/Maven 3.9.0+:

~~~bash
mvn -version
mvn -B -ntp clean package
java -cp target/classes dev.example.cache.CacheDemo
~~~

Java stdout:

~~~text
CORE EXTENSION PROJECT OK
~~~

Để xác nhận **extension đã được Maven nạp**, phải xem startup/cache-related logs, cache configuration và build-cache data theo docs. `BUILD SUCCESS` hoặc Java stdout trên đây **không tự chứng minh cache hit**. Cache extension 1.3.0 có thể tạo `build-cache` directory bên cạnh local Maven repo và thông tin `buildinfo.xml`. Có thể tắt cache trong một run để đối chiếu:

~~~bash
mvn -B -ntp -Dmaven.build.cache.enabled=false clean package
~~~

Cờ này chỉ có ý nghĩa với Build Cache Extension được nạp. Đừng tự suy Java main sẽ thay đổi output khi cache hit hay miss.

### 7.3. Cùng một artifact ở `build/extensions`: nạp khác thời điểm

Thay vì core descriptor, bạn có thể chọn **một** phương án khai trong `pom.xml`:

~~~xml
<build>
    <extensions>
        <extension>
            <groupId>org.apache.maven.extensions</groupId>
            <artifactId>maven-build-cache-extension</artifactId>
            <version>1.3.0</version>
        </extension>
    </extensions>
</build>
~~~

Apache Maven Build Cache docs xác nhận cả POM build extension và `.mvn/extensions.xml`, **ưu tiên core** vì cho phép tích hợp sâu/sớm hơn với Maven API. Không khai cùng cache extension **cả ở POM lẫn .mvn** rồi coi là tăng độ tin cậy; nạp lặp có thể gây behavior khó dự đoán.

### 7.4. Vì sao core extension nạp sớm cần thiết?

Một custom lifecycle participant có thể muốn nhận `afterSessionStart`; nếu chỉ được Maven đăng ký khi đọc POM build extension thì callback này đã xảy ra. Maven 3 lifecycle extension guide nêu đây là khác biệt thực tế của early/late loading.

Một số core extensions có thể tác động tới Maven dependency injection components hoặc resolver behavior. Vì vậy chúng dễ gặp API/classloader compatibility conflicts hơn một ordinary Mojo chỉ xử lý file sau phase compile.

## 8. Các phương pháp đăng ký core extension khác

Maven Guide to Using Extensions và Configuring Maven ghi nhận:

| Cách | Phạm vi | Lưu ý |
| --- | --- | --- |
| `.mvn/extensions.xml` | Project/multimodule | Phổ biến, có thể version control |
| `-Dmaven.ext.class.path=...` | Invocation/CLI Maven 3.x | Phụ thuộc JAR local và runtime support |
| `${maven.home}/lib/ext` | Maven installation | Global cho bản Maven đó, khó chuẩn hóa nếu mỗi máy khác |
| `${user.home}/.m2/extensions.xml` | User (Maven 3.10+) | Có thể ảnh hưởng nhiều dự án cùng user |
| `${maven.home}/conf/extensions.xml` | Installation (Maven 3.10+) | Scope rộng, cần quản trị |

Các settings/config đó không biến core extension thành `plugin goal`. `.mvn/maven.config` cũng là file **khác**: nó lưu CLI arguments, không thay `.mvn/extensions.xml`.

**Rủi ro quan trọng:** source repository từ người không tin cậy có thể chứa `.mvn/extensions.xml` khiến Maven tải/khởi chạy extension trước khi bạn tới `compile`. Không cấp token phát hành cho PR builds không được tin cậy; kiểm extension GAV, version, source provenance và quyền trước khi chạy.

## 9. Classloading và component registration

### 9.1. Plugin realm

Plugin goals chạy trong class realm được Maven chuẩn bị cho plugin. Trong consumer project, `build/plugins/plugin/dependencies` có thể bổ sung dependencies cho chính plugin, không mặc định đóng chúng vào main application artifact.

### 9.2. Build extension realms

Theo Maven Classloading Guide, mỗi build extension và mỗi plugin được đánh dấu `extensions=true` có extension realm riêng; các Sisu/Plexus components được discover/đăng ký trong Maven container. Project realm nhìn thấy APIs/classes được expose từ những build extensions áp dụng. Các extension realms không tự chia sẻ toàn bộ private dependency classes của nhau. Vì vậy “build extension A có JAR X thì plugin B chắc chắn import được X” là suy luận nguy hiểm.

### 9.3. Core extension realm

Core extension được nạp sớm vào core classloading/container phù hợp. Các APIs core của Maven 3 và Maven 4 có thể khác nhau, và một implementation cụ thể có thể dùng Sisu/JSR-330/Plexus SPIs. Đừng coi `NoClassDefFoundError` khi nâng Maven 4 là dấu hiệu chỉ thiếu library trong application POM; có thể là binary incompatibility của extension với Maven core.

### 9.4. classLoadingStrategy

Core descriptor schema mới có `classLoadingStrategy` như `self-first`, `parent-first` và `plugin` theo Maven 3-LATEST docs. Không chỉnh strategy tùy ý hoặc copy tag vào schema 1.0.0; cần xác nhận runtime và API cụ thể.

## 10. Viết một core/build extension tùy chỉnh khác viết Mojo

Trong Maven 3, các extension points có thể gồm:

- `org.apache.maven.AbstractMavenLifecycleParticipant` cho lifecycle callbacks.
- `org.apache.maven.eventspy.AbstractEventSpy` cho events.
- JSR-330/Sisu/Plexus components để Maven resolve bằng dependency injection.
- Components quản lý lifecycle/packaging mapping hoặc transport.

Một extension không tự được discover chỉ vì có Java class với method `execute()`. Nó cần **đúng Maven SPI và component metadata/index**.

### 10.1. Code minh họa Maven 3 lifecycle SPI

Đây là **fragment minh họa** chứ không phải một Java project runnable độc lập; để build thực tế cần POM Maven extension, `maven-core` scope `provided`, `javax.inject`/Sisu indexing và Maven 3 API version phù hợp:

~~~java
import javax.inject.Named;
import javax.inject.Singleton;
import org.apache.maven.AbstractMavenLifecycleParticipant;
import org.apache.maven.execution.MavenExecutionException;
import org.apache.maven.execution.MavenSession;

@Named("audit-lifecycle")
@Singleton
public final class AuditLifecycleExtension
        extends AbstractMavenLifecycleParticipant {

    @Override
    public void afterProjectsRead(MavenSession session)
            throws MavenExecutionException {
        System.out.println(
                "Projects loaded: " + session.getProjects().size());
    }
}
~~~

Không chạy class bằng `java AuditLifecycleExtension` và mong Maven tự gọi. Phải package, generate metadata và đăng ký extension. Với Maven 4, kiểm migration API/documentation thay vì dùng nguyên Maven 3 internals.

### 10.2. Cơ chế nào dùng cho policy check ở `verify`?

Một security/quality check chỉ cần đọc compiled classes và báo PASS/FAIL ở `verify` nên là **ordinary Mojo**. Viết core extension cho việc đó làm tăng coupling/khó debug mà không tạo giá trị. Core extension chỉ nên được chọn khi phải quan sát/thay đổi Maven **trước khi project execution plan được hình thành**.

## 11. Cây quyết định chọn đúng công cụ

~~~text
Có cần một task/goal ở build lifecycle?
       |
       +-- CÓ --> ordinary Maven plugin / Mojo
       |           -> bind goal vào phase bằng executions
       |
       +-- KHÔNG --> Cần packaging/lifecycle mapping mới,
                     component cho project/build?
                      |
                      +-- CÓ --> build extension
                      |           -> build/extensions
                      |           -> hoặc plugin extensions=true
                      |
                      +-- KHÔNG --> Cần hook Maven sớm hơn POM,
                                    core/session behavior?
                                     |
                                     +-- CÓ --> core extension
                                     |           -> .mvn/extensions.xml
                                     |
                                     +-- KHÔNG --> project dependency,
                                                 settings hoặc tool khác
~~~

Ví dụ chọn:

| Tình huống | Chọn gì? | Vì sao? |
| --- | --- | --- |
| Compile Java 17 | Compiler plugin | Goal đã có |
| Chạy JUnit | Surefire/Failsafe plugin | Test goal |
| Generate source | Codegen plugin ở `generate-sources` | Không cần core hook |
| Custom `greet` | Ordinary `@Mojo` | Một action với tham số |
| OSGi `bundle` packaging | Felix build extension | Đăng ký packaging mapping |
| Build cache Maven-level | Apache Maven Build Cache core extension | Docs khuyên early registration |
| Need `afterSessionStart` callback | Core extension | Build extension muộn |
| Download thư viện ứng dụng | `project.dependencies` | Không phải Maven extension |
| Maven plugin cần thư viện riêng | Plugin POM/dependencies | Đúng realm |
| Site report | Reporting plugin | Report goal, không phải core |
| Repo credential config | `settings.xml` | Không cần viết extension để có username |

## 12. Multi-module, inheritance và project boundaries

Trong reactor:

~~~text
company-parent/
├── pom.xml               packaging=pom
├── app/pom.xml           packaging=jar
└── osgi-module/pom.xml   packaging=bundle
~~~

- Parent có thể quản lý plugin versions trong `pluginManagement` nhưng không tự tạo execution mới.
- `app` không cần Felix extension chỉ vì `osgi-module` dùng `bundle` packaging.
- Build extensions chịu ảnh hưởng project POM/inheritance và extension realm của project; không giả định mọi child nhìn thấy mọi classes.
- Core `.mvn/extensions.xml` thường ở root project/multimodule directory Maven đang gọi, nên có thể ảnh hưởng toàn Maven session/reactor.
- Thay core extension có thể làm behavior của nhiều modules khác nhau; cần full build/regression tests.
- Parallel Maven `-T` đòi custom Mojo/extension quản lý shared state đúng, không chỉ đặt `threadSafe=true` rồi hy vọng.

## 13. Vấn đề tương thích Maven 3.9, 3.10 và Maven 4

### 13.1. Maven 3.9.x

`.mvn/extensions.xml` được hỗ trợ từ Maven 3.3.1, nhưng **Build Cache Extension 1.3.0** yêu cầu Maven 3.9+. Các ví dụ tự tạo plugin bên trên dùng `maven-plugin-api 3.9.16` và Plugin Tools 3.16.0; hãy kiểm exact Maven version/Java toolchain trong CI.

### 13.2. Maven 3.10+

Maven còn đọc `user.home/.m2/extensions.xml` và `maven.home/conf/extensions.xml`, ngoài project core descriptor. Các entries đó có thể gây khác biệt behavior giữa laptop và CI dù source POM giống nhau.

### 13.3. Maven 4

Maven 4 có APIs, descriptor schema và plugin tooling riêng, bao gồm core descriptor 1.2.0 với cấu hình mới. Các extensions dựa Maven 3 internals có thể cần nâng cấp/migration. Không chỉ đổi Maven Wrapper sang Maven 4 và tuyên bố compatibility mà chưa chạy integration tests. Những field `classLoadingStrategy`/ `configuration` phải dùng đúng model schema/version.

## 14. Chẩn đoán lỗi plugin và extensions

### 14.1. `Unknown packaging: bundle`

Maven chưa nhận lifecycle mapping; kiểm Felix Plugin version, `extensions=true` và repository resolution. Không sửa bằng cách thêm `<dependency>maven-bundle-plugin</dependency>` vào runtime project.

### 14.2. Custom goal không chạy

`@Mojo(defaultPhase)` không tự bind vào mọi POM. Kiểm `build/plugins/plugin/executions` và goals. `pluginManagement` có thể chỉ quản lý version. `mvn help:describe` để xem goal nhưng không chạy nó.

### 14.3. `No plugin descriptor found`

Kiểm `<packaging>maven-plugin</packaging>` trong plugin producer, Maven Plugin Tools `descriptor` goal, version, class annotations và `META-INF/maven/plugin.xml` trong JAR. Không thêm core extension để chữa.

### 14.4. `No plugin found for prefix`

Custom `groupId=dev.example` có thể không nằm trong default `pluginGroups`. Gọi fully qualified `dev.example:maven-greeting-plugin:1.0.0:greet` sau local install/remote deploy.

### 14.5. Core extension không nạp

Kiểm vị trí `.mvn/extensions.xml`, descriptor XML và GAV, Maven version, repository/mirror/credentials/TLS có tải extension artifact được trong bootstrap không. Khi early resolution fail, `help:effective-pom` thậm chí không chạy được.

### 14.6. Core extension nạp nhưng build vẫn `BUILD SUCCESS` không đổi

Một số extensions chỉ thay Maven runtime behavior (cache, listeners, metrics) chứ không sinh visible goal. Kiểm loading logs, cấu hình extension, cách xác nhận cache hits/events, và compare với disabled behavior.

### 14.7. Early callback không chạy với build extension

`afterSessionStart` có thể đã diễn ra trước khi build extension được đăng ký. Dùng core extension khi SPI yêu cầu, không giả định đổi `<phase>` ở plugin execution sẽ sửa.

### 14.8. `ClassNotFoundException`, `NoClassDefFoundError`

Kiểm realm chứa class, extension/plugin transitive dependency version, `provided` scopes, JDK/Maven API compatibility. Đừng đưa JAR tùy ý vào Maven `lib/ext` hoặc dựa project classpath để chữa mọi lỗi.

### 14.9. `NoSuchMethodError` sau nâng Maven

Extension compile với Maven APIs khác runtime, có thể vỡ binary compatibility. Pin Maven Wrapper, nâng extension version được hỗ trợ và chạy integration tests trước khi merge.

### 14.10. Extension bị khai hai lần

Nếu Build Cache Extension vừa có ở POM `build/extensions` vừa ở `.mvn/extensions.xml`, behavior có thể khó đoán. Chọn một mechanism theo docs; đừng dùng cả hai làm fallback.

### 14.11. Tài liệu plugin cũ gợi ý classloading flags mới

Maven 3/4 có schema/version khác; không copy `classLoadingStrategy` hoặc `configuration` vào descriptor cũ khi parser không hỗ trợ. Đọc Maven Embedder CoreExtensions Reference đúng phiên bản.

### 14.12. Local Maven cache che lỗi

`mvn -o` có thể chạy trên laptop nhưng extension/plugin mới chưa cache ở CI. Dùng `mvn -B -ntp -Dmaven.repo.local=./.m2-isolated clean package` để kiểm independent resolution khi được phép network; không xóa `~/.m2` vội.

### 14.13. Bootstrap extension làm lộ secrets

Core extension được nạp sớm và là executable code trong Maven process. Audit `.mvn/extensions.xml` từ PR, không cấp release token cho untrusted builds, pin artifacts và giữ credentials trong CI secrets manager.

### 14.14. Plugin test phase không cần early hook

Nếu plugin chỉ cần chạy tests hoặc generate report, sử dụng ordinary plugin goal là đủ. Chuyển thành extension làm mở rộng quyền và coupling không cần thiết.

## 15. Quy trình kiểm tra thực tế

### Bước 1 — phiên bản Maven/JDK

~~~bash
mvn -version
java -version
~~~

Trong project có Maven Wrapper dùng `./mvnw -version` hoặc `mvnw.cmd -version`. Cần biết runtime để chọn đúng plugin/extension APIs.

### Bước 2 — xem effective POM

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Xem `build/plugins`, `build/extensions`, pluginManagement, executions, packaging, profiles. Core descriptor `.mvn/extensions.xml` nằm ngoài effective POM, cần đọc file riêng.

### Bước 3 — xem Maven plugin goals

~~~bash
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.14.0 -Dgoal=compile -Ddetail
~~~

`help:describe` xem descriptor, không chạy `compile`. Để chạy goal, dùng `compiler:compile` hoặc `mvn compile` theo lifecycle.

### Bước 4 — kiểm JAR plugin descriptor

~~~bash
jar tf target/maven-greeting-plugin-1.0.0.jar
~~~

Tìm `META-INF/maven/plugin.xml`. Nếu JAR là ordinary application library không có descriptor, không gọi nó như Maven plugin.

### Bước 5 — kiểm build extension packaging

Với Felix, check `packaging=bundle` và `extensions=true`, sau đó xem manifest `Bundle-SymbolicName`. Nếu Maven fail từ model-building, debug `Unknown packaging` thay vì sửa Java source.

### Bước 6 — kiểm core extension startup

Xem `.mvn/extensions.xml`, Maven runtime, extension GAV, cache extension INFO logs và local cache data. Tránh in `-X` logs chứa corporate paths/URLs/secrets lên public issues.

### Bước 7 — so sánh trong CI

Chạy clean build từ independent workspace/cache; dùng pinned Maven/JDK/plugin versions, kiểm behavior khi extension enabled/disabled theo docs. Với build cache, so correctness của outputs, không chỉ thời gian nhanh/chậm.

## 16. Checklist chọn và triển khai

- [ ] Tác vụ chỉ cần goal hay thật sự cần Maven component/lifecycle hook?
- [ ] Đã ưu tiên ordinary plugin nếu đủ.
- [ ] Có POM plugin `packaging=maven-plugin` và `plugin.xml` descriptor nếu tự viết Mojo.
- [ ] Custom goal có `executions` hoặc được gọi trực tiếp; không dựa vào `defaultPhase` một mình.
- [ ] Đã pin plugin versions, Maven runtime và JDK.
- [ ] Biết `build/extensions/extension` khác plugin `extensions=true`.
- [ ] Không nhầm runtime dependencies với extension/plugin classpath.
- [ ] Custom `packaging` có provider/lifecycle mapping đúng.
- [ ] Core descriptor ở đúng `.mvn/extensions.xml` với schema phù hợp.
- [ ] Không double-load cùng extension ở POM và core descriptor.
- [ ] Có kiểm Maven 3.9/3.10/4 compatibility khi nâng version.
- [ ] Đã kiểm class realms, Sisu/Plexus registration nếu viết extension.
- [ ] Extension artifact được resolve qua repository/HTTPS/mirror hợp lệ.
- [ ] Không bật core extension toàn installation nếu chỉ cần một project.
- [ ] Có regression tests cho multi-module/parallel build.
- [ ] Có review/pin/audit extension artifacts như code thực thi.
- [ ] CI secrets không cấp cho PR builds không tin cậy.
- [ ] Core cache extension có correctness checks và không chỉ đo tốc độ.

## 17. Bài tập và đáp án

**1.** Maven Compiler Plugin có cần `<extensions>true</extensions>` không? — **Không:** là ordinary plugin với goal `compile`.

**2.** `@Mojo(defaultPhase=VALIDATE)` đã tự bind goal vào mọi project chưa? — **Chưa:** cần execution hoặc invocation.

**3.** Vì sao `<packaging>bundle</packaging>` có thể lỗi `Unknown packaging`? — **Vì** Maven chưa nhận lifecycle mapping từ Felix build extension.

**4.** Build Cache Extension 1.3.0 đặt trong `.mvn/extensions.xml` thuộc loại nào? — **Core extension registration**, nạp sớm.

**5.** Cùng JAR đặt trong `<build><extensions>` thuộc loại nào? — **Build extension registration**, nạp muộn hơn; docs hỗ trợ cả hai.

**6.** Project `dependencies` có thể tự thay Maven lifecycle mapping không? — **Không:** đó là classpath ứng dụng, không phải extension registration.

**7.** `mvn help:describe` có gọi `GreetMojo.execute()` không? — **Không:** chỉ đọc metadata/descriptor.

**8.** `pluginManagement` có tự tạo Mojo execution mới không? — **Không** nếu goal chưa được bind hay gọi.

**9.** Muốn bắt `afterSessionStart`, build extension trong POM đủ chưa? — **Thường chưa:** callback sớm đã qua, xem core extension.

**10.** `.mvn/extensions.xml` có yêu cầu artifact chứa Mojo goals không? — **Không**, nó có thể chỉ cung cấp components.

**11.** `maven-greeting-plugin-1.0.0.jar` thiếu `META-INF/maven/plugin.xml` thì sao? — **Maven không đọc được đúng plugin descriptor/goals**; sửa Plugin Tools packaging.

**12.** `mvn -o` chạy trên laptop nhưng core extension fail trên CI là Maven bug? — **Không nhất thiết:** CI chưa cache extension artifact hoặc settings khác.

**13.** User-level `.m2/extensions.xml` có trong Maven 3.10+ ảnh hưởng gì? — **Có thể** tác động nhiều builds của user, dù project POM không khai.

**14.** Maven 4 dùng nguyên Java extension internals Maven 3 mà không test được không? — **Không nên:** API/descriptor/classloader có thể thay.

**15.** Bật `extensions=true` làm Surefire nhanh hơn không? — **Không tự động:** đó là cơ chế load, không phải optimizer.

**16.** Plugin bình thường có thể làm việc nguy hiểm không? — **Có:** mọi build code cần trust; extensions còn có thể nạp sớm/rộng hơn.

**17.** Một extension JAR có phải được dùng ở cả core và build mode không? — **Không:** chỉ khi docs của artifact nói rõ hỗ trợ cả hai.

**18.** Không cần packaging mới mà vẫn muốn OSGi manifest thì sao? — **Có thể** dùng Felix goal tạo manifest và Maven JAR Plugin theo hướng dẫn Felix, giữ `jar` packaging.

## 18. Tài liệu chính thức

1. [Maven — Using Extensions](https://maven.apache.org/guides/mini/guide-using-extensions.html): định nghĩa core/build extension và đăng ký.
2. [Maven — Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html): class realms cho core/build/project/plugin.
3. [Maven — Configuring Maven](https://maven.apache.org/configure.html): `.mvn/extensions.xml` và user/global descriptors từ 3.10+.
4. [Maven — Core Extensions Descriptor](https://maven.apache.org/ref/3-LATEST/maven-embedder/core-extensions.html): core GAV, schema, classLoadingStrategy.
5. [Maven 4 — Core Extensions Descriptor](https://maven.apache.org/components/ref/4.0.0-rc-7/api/maven-api-cli/core-extensions.html): schema `1.2.0` và cấu hình mới.
6. [Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): lifecycle, phases, packaging mappings.
7. [Maven — Plugin Configuration](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): plugin versions, build/reporting plugins.
8. [Maven — Plugin Development](https://maven.apache.org/guides/plugin/guide-java-plugin-development): Java Maven plugin producer POM.
9. [Maven Plugin Tools — Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html): `@Mojo`, `@Parameter`, descriptor.
10. [Maven — Maven 3 Lifecycle Extensions](https://maven.apache.org/examples/maven-3-lifecycle-extensions.html): AbstractMavenLifecycleParticipant, early callbacks.
11. [Maven — Extension Demo Study](https://maven.apache.org/components/studies/extension-demo/): các cơ chế nạp extension.
12. [Maven Build Cache Extension 1.3.0](https://maven.apache.org/extensions/maven-build-cache-extension/): core/build loading options, Maven requirement.
13. [Maven Build Cache Usage](https://maven.apache.org/extensions/maven-build-cache-extension-1.3.0/usage.html): activation, cache config và disable.
14. [Apache Felix — Maven Bundle Plugin](https://felix.apache.org/documentation/subprojects/apache-felix-maven-bundle-plugin-bnd.html): `bundle` packaging, `extensions=true` và bnd manifest.
15. [Apache Felix Release Catalog](https://release-catalog.apache.org/felix-maven-bundle-plugin/index.html): version `6.2.0` released 18/09/2026.
16. [Maven — Artifact Coordinates](https://maven.apache.org/repositories/artifacts.html): build extension khác artifact file extension.
