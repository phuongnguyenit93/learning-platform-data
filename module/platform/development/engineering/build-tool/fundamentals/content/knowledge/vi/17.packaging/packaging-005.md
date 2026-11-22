# Thin JAR và cách cung cấp thư viện bên ngoài

Một tệp JAR Java có thể chứa các lớp và tài nguyên của chính ứng dụng mà không chứa toàn bộ thư viện mà ứng dụng sử dụng. Kiểu đóng gói này thường được gọi là **Thin JAR** (JAR mỏng). Khi chạy, JVM cần tìm được cả JAR ứng dụng lẫn các thư viện phụ thuộc ở bên ngoài.

Thin JAR giúp artifact gọn, tránh sao chép lại nội dung của nhiều thư viện và phù hợp với cách phân phối thư viện qua Maven repository. Tuy nhiên, nếu tạo một ứng dụng có thể chạy độc lập, bạn phải cung cấp dependency cùng với JAR và cấu hình classpath hoặc manifest để JVM nạp chúng.

Ví dụ cấu trúc phân phối:

```text
my-app/
├── bin/
│   └── my-app                 # Script khởi chạy
├── lib/
│   ├── my-app-1.0.0.jar       # Thin JAR của ứng dụng
│   ├── http-client.jar        # Thư viện bên ngoài
│   └── json-core.jar
└── conf/
    └── application.yml
```

Ở đây, `my-app-1.0.0.jar` chứa lớp và tài nguyên của ứng dụng. Các JAR phụ thuộc nằm riêng trong `lib/`. Script khởi chạy sẽ đưa chúng vào classpath khi gọi JVM, hoặc JAR ứng dụng có thể khai báo các thư viện tương đối trong thuộc tính `Class-Path` của manifest.

## 1. Thin JAR là gì?

JAR (Java Archive) là định dạng archive dựa trên ZIP. Một JAR có thể chứa:

- Các tệp `.class` đã biên dịch.
- Tài nguyên như properties, YAML, XML, ảnh hoặc template.
- Metadata trong `META-INF/`, chẳng hạn `MANIFEST.MF`.
- Các tệp bổ sung được cấu hình trong quá trình đóng gói.

Với Thin JAR, nội dung chính thường là output của ứng dụng hoặc thư viện. Các dependency bên ngoài không được giải nén và chép vào cùng archive. Chúng được phân phối riêng và cần có mặt trong runtime classpath.

Ví dụ:

```text
my-app-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/app/
    ├── Main.class
    └── UserService.class

lib/
├── http-client-4.2.jar
├── json-core-3.1.jar
└── logging-api-2.0.jar
```

`Main.class` có thể tham chiếu đến các lớp nằm trong `http-client`, `json-core` hoặc `logging-api`. Nếu JVM chỉ nạp `my-app-1.0.0.jar`, các lớp bên ngoài sẽ không được tìm thấy và ứng dụng có thể dừng với `NoClassDefFoundError` hoặc `ClassNotFoundException`.

### Thin JAR và Fat/Uber JAR

| Đặc điểm | Thin JAR | Fat/Uber JAR |
|---|---|---|
| Lớp của ứng dụng | Có trong JAR | Có trong JAR |
| Dependency bên ngoài | Nằm ở các JAR riêng | Thường được gom vào cùng archive hoặc được nạp qua cơ chế đóng gói đặc biệt |
| Cách chạy | Cần classpath hoặc manifest trỏ đến dependency | Thường có thể chạy bằng `java -jar` nếu đã cấu hình entry point/loader |
| Kích thước JAR ứng dụng | Thường nhỏ hơn | Thường lớn hơn |
| Cập nhật dependency | Có thể thay thư viện riêng trong gói phân phối nếu tương thích | Thường phải tạo lại artifact ứng dụng |
| Rủi ro | Thiếu JAR hoặc classpath sai | Xung đột tài nguyên, service descriptor hoặc lớp trùng khi gom archive |

Thin JAR không có nghĩa ứng dụng không có dependency. Nó chỉ có nghĩa dependency không được nhúng vào chính JAR ứng dụng. Người phát hành vẫn phải cung cấp chúng qua repository, thư mục `lib/`, container hoặc môi trường chạy.

## 2. JVM tìm lớp từ đâu?

JVM sử dụng classpath để tìm lớp và tài nguyên. Một mục classpath có thể là:

- Thư mục chứa cây package và tệp `.class`.
- Một tệp JAR.
- Một wildcard đại diện cho các JAR trực tiếp trong thư mục, khi cú pháp classpath hỗ trợ.

Ví dụ, nếu ứng dụng có lớp chính `com.example.app.Main` và các dependency nằm trong `lib/`, có thể chạy bằng classpath.

Trên Windows:

```powershell
java -cp "lib/my-app-1.0.0.jar;lib/*" com.example.app.Main
```

Trên Linux/macOS:

```shell
java -cp "lib/my-app-1.0.0.jar:lib/*" com.example.app.Main
```

Dấu phân cách giữa các mục classpath khác nhau theo hệ điều hành:

- Windows dùng dấu chấm phẩy `;`.
- Linux và macOS dùng dấu hai chấm `:`.

Wildcard `lib/*` đưa các tệp JAR trực tiếp trong thư mục `lib` vào classpath. Nó không tìm JAR đệ quy trong mọi thư mục con. Đặt cả JAR ứng dụng và dependency vào cùng classpath giúp JVM tìm được các lớp cần thiết.

### Vì sao cần dấu ngoặc kép?

Class path có thể chứa khoảng trắng hoặc ký tự đặc biệt. Dấu ngoặc kép giúp shell truyền toàn bộ chuỗi classpath thành một đối số cho `java`:

```powershell
java -cp "C:\Program Files\my-app\lib\*" com.example.app.Main
```

Trên Linux/macOS:

```shell
java -cp "/opt/my app/lib/*" com.example.app.Main
```

Dấu ngoặc kép là cú pháp của shell, không phải một phần của đường dẫn. Khi viết script, hãy trích dẫn biến chứa classpath để tránh tách đối số ngoài ý muốn.

### `-cp` và `-jar` khác nhau

Chạy lớp chính bằng classpath:

```shell
java -cp "app.jar:lib/*" com.example.app.Main
```

Chạy một JAR:

```shell
java -jar app.jar
```

Khi dùng `-jar`, JVM lấy lớp chính từ manifest và sử dụng `Class-Path` trong manifest nếu có. Các tùy chọn classpath khác như `-cp` không được dùng để bổ sung classpath cho chế độ `-jar`. Vì vậy, không nên chạy `java -jar app.jar -cp lib/*` với kỳ vọng `-cp` sẽ thêm dependency. Nếu muốn dùng `-jar`, hãy khai báo `Class-Path` phù hợp trong manifest hoặc dùng một cơ chế khởi chạy khác.

## 3. Dùng manifest `Class-Path` cho Thin JAR

Manifest của JAR nằm tại `META-INF/MANIFEST.MF`. Một manifest có thể khai báo lớp chính và classpath tương đối:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/http-client-4.2.jar lib/json-core-3.1.jar
```

Khi chạy:

```shell
java -jar my-app-1.0.0.jar
```

JVM đọc `Main-Class` để biết lớp có phương thức `main` cần khởi chạy. Các mục trong `Class-Path` được dùng để tìm thêm lớp và tài nguyên.

### Đường dẫn trong manifest được tính từ đâu?

Các mục trong thuộc tính `Class-Path` của manifest là URL tương đối hoặc tuyệt đối theo quy tắc manifest/JAR. Với đường dẫn tương đối, mốc là vị trí của JAR chứa manifest, không phải thư mục làm việc hiện tại của Terminal.

Ví dụ:

```text
dist/
├── my-app.jar
└── lib/
    ├── http-client.jar
    └── json-core.jar
```

Manifest trong `my-app.jar` có thể ghi:

```text
Class-Path: lib/http-client.jar lib/json-core.jar
```

Khi JVM mở `dist/my-app.jar`, nó tìm các dependency tương ứng trong `dist/lib/`. Nếu chuyển riêng JAR sang thư mục khác mà không chuyển `lib/` theo cùng cấu trúc, ứng dụng sẽ không tìm thấy dependency.

### Các quy tắc cần nhớ

- Các mục classpath trong manifest được phân tách bằng khoảng trắng.
- Mỗi mục nên là URL hợp lệ; đường dẫn có ký tự đặc biệt hoặc khoảng trắng phải được mã hóa theo quy tắc URL.
- Đường dẫn tương đối được giải quyết từ vị trí JAR chứa manifest.
- JAR phụ thuộc cũng có thể có manifest riêng, nhưng nên tránh dựa vào chuỗi manifest lồng nhau khó theo dõi.
- Manifest có giới hạn định dạng dòng; công cụ `jar` và plugin đóng gói thường tự xử lý việc xuống dòng tiếp nối khi ghi thuộc tính dài.

Không nên viết một dòng `Class-Path` rất dài bằng tay nếu có hàng chục dependency. Hãy để build tool tạo manifest từ danh sách dependency đã phân giải.

## 4. Tạo Thin JAR bằng Gradle

Gradle Java plugin tạo JAR từ output của source set `main`. Dependency được khai báo trong `implementation`, `api` hoặc `runtimeOnly` không tự động được đóng gói bên trong JAR thông thường.

Ví dụ `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

dependencies {
    implementation 'com.example:http-client:4.2.0'
    runtimeOnly 'com.example:json-core:3.1.0'
}

tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.app.Main'
        )
    }
}
```

Sau khi chạy task `jar`, artifact thường nằm tại:

```text
build/libs/<project-name>-1.0.0.jar
```

JAR chứa các lớp và tài nguyên của project. Các dependency được Gradle phân giải riêng trong `runtimeClasspath`, không được tự động chép vào JAR tiêu chuẩn.

### Chỉ khai báo `Main-Class` chưa đủ để chạy Thin JAR

Manifest trên có entry point nhưng chưa có `Class-Path`. Nếu `Main` tham chiếu đến `http-client` hoặc `json-core`, lệnh:

```shell
java -jar build/libs/my-app-1.0.0.jar
```

có thể thất bại vì JVM không tìm thấy các dependency. Bạn cần cung cấp chúng bằng một trong các cách:

- Tạo manifest `Class-Path` trỏ đến thư mục chứa dependency.
- Chạy lớp chính bằng `-cp` và đưa cả JAR ứng dụng lẫn dependency vào classpath.
- Tạo một distribution gồm JAR ứng dụng, thư viện và script khởi chạy.
- Dùng plugin đóng gói ứng dụng hoặc tạo executable/fat JAR nếu yêu cầu triển khai phù hợp.

## 5. Tạo manifest classpath từ dependency của Gradle

Với một ứng dụng nhỏ, có thể tạo manifest `Class-Path` từ các file trong `runtimeClasspath`. Ví dụ sau giả định JAR ứng dụng và thư mục `lib/` được phân phối cùng nhau:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.app.Main',
            'Class-Path': configurations.runtimeClasspath.files
                .collect { "lib/${it.name}" }
                .join(' ')
        )
    }
}
```

Đoạn cấu hình minh họa cách lấy các dependency runtime đã phân giải và tạo danh sách tên tương đối. Nó giả định các JAR đó sẽ được copy vào thư mục `lib/` bên cạnh JAR ứng dụng. Chỉ tạo manifest mà không phân phối các file dependency tương ứng thì ứng dụng vẫn không chạy được.

### Sao chép dependency vào thư mục phân phối

Có thể tạo task copy dependency runtime:

```groovy
tasks.register('copyRuntimeLibs', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('dist/lib')
}

tasks.register('stageThinDistribution', Copy) {
    dependsOn tasks.jar, tasks.named('copyRuntimeLibs')
    from tasks.jar
    into layout.buildDirectory.dir('dist')
}
```

Ví dụ trên tạo cấu trúc `build/dist/<app>.jar` và `build/dist/lib/<dependency>.jar`, khớp với manifest `Class-Path` có tiền tố `lib/`. Đây là ví dụ tối giản; với dự án nhiều loại artifact hoặc cần xử lý trùng tên, hãy cấu hình tên file và output của từng task một cách tường minh.

Một cách dễ bảo trì hơn cho ứng dụng là dùng Gradle Application plugin, vì plugin này cung cấp tác vụ tạo distribution gồm script khởi chạy, JAR ứng dụng và runtime dependencies.

## 6. Dùng Gradle Application plugin để phân phối Thin JAR

Application plugin là lựa chọn phù hợp khi cần đóng gói ứng dụng Java có thể chạy cùng các thư viện riêng. Plugin sử dụng application main class và runtime classpath để tạo thư mục phân phối.

Ví dụ:

```groovy
plugins {
    id 'application'
}

group = 'com.example'
version = '1.0.0'

dependencies {
    implementation 'com.example:http-client:4.2.0'
    runtimeOnly 'com.example:json-core:3.1.0'
}

application {
    mainClass = 'com.example.app.Main'
}
```

Tạo distribution:

```shell
./gradlew installDist
```

Trên Windows:

```powershell
.\gradlew.bat installDist
```

Output mặc định thường có dạng:

```text
build/install/<application-name>/
├── bin/
│   ├── <application-name>
│   └── <application-name>.bat
└── lib/
    ├── <application-name>-1.0.0.jar
    ├── http-client-4.2.0.jar
    └── json-core-3.1.0.jar
```

Script trong `bin/` được tạo để thiết lập classpath và khởi chạy lớp chính. Thư viện nằm riêng trong `lib/`, nên đây là một dạng phân phối Thin JAR. Người dùng có thể chạy script mà không phải tự ghép classpath bằng tay.

### Tạo gói ZIP hoặc TAR

Application plugin còn cung cấp các task archive distribution, thường gồm:

```shell
./gradlew distZip
./gradlew distTar
```

Các archive thường nằm trong `build/distributions/`. Người dùng giải nén gói rồi chạy script trong thư mục `bin/`.

Distribution là một đơn vị triển khai hoàn chỉnh hơn JAR đơn lẻ: nó mang theo JAR ứng dụng, các dependency runtime và script khởi chạy. Nếu cần thêm file cấu hình hoặc tài nguyên ngoài JAR, có thể mở rộng nội dung distribution theo cấu hình plugin.

## 7. Tạo Thin JAR và manifest classpath bằng Maven

Với Maven, Maven JAR Plugin tạo JAR ứng dụng. Để thêm `Main-Class` và `Class-Path` vào manifest, có thể cấu hình plugin như sau:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>com.example.app.Main</mainClass>
                        <addClasspath>true</addClasspath>
                        <classpathPrefix>lib/</classpathPrefix>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`mainClass` đặt entry point trong manifest. `addClasspath` yêu cầu plugin thêm các dependency được phân giải vào thuộc tính `Class-Path`. `classpathPrefix` thêm tiền tố `lib/` cho mỗi mục classpath.

Để JAR chạy được, dependency runtime cần được đặt trong thư mục `lib/` bên cạnh JAR ứng dụng. Maven JAR Plugin ghi danh sách đường dẫn; nó không tự copy toàn bộ dependency vào thư mục phân phối chỉ vì `addClasspath` được bật.

### Copy dependency runtime bằng Maven Dependency Plugin

Cấu hình plugin để copy dependency:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-dependency-plugin</artifactId>
    <version>3.6.1</version>
    <executions>
        <execution>
            <id>copy-runtime-dependencies</id>
            <phase>package</phase>
            <goals>
                <goal>copy-dependencies</goal>
            </goals>
            <configuration>
                <includeScope>runtime</includeScope>
                <outputDirectory>${project.build.directory}/lib</outputDirectory>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Goal `copy-dependencies` copy dependency đã phân giải vào `target/lib`. `includeScope` giới hạn tập dependency được copy theo scope; lựa chọn `runtime` bao gồm dependency cần cho runtime và các dependency compile phù hợp theo quy tắc scope của Maven. Nếu ứng dụng cần một tập dependency khác, hãy điều chỉnh scope và xác nhận nội dung thư mục.

Sau khi chạy:

```shell
mvn package
```

Bạn thường có:

```text
target/
├── my-app-1.0.0.jar
└── lib/
    ├── http-client-4.2.0.jar
    └── json-core-3.1.0.jar
```

Vì manifest dùng `classpathPrefix` là `lib/`, các đường dẫn tương đối sẽ trỏ đến `target/lib/` khi JAR nằm trong `target/`. Có thể chạy:

```shell
java -jar target/my-app-1.0.0.jar
```

Hãy xác nhận manifest và thư mục dependency được phân phối cùng nhau. Nếu copy JAR sang một thư mục khác mà bỏ lại `lib/`, classpath trong manifest sẽ không còn trỏ đúng vị trí.

## 8. Phân phối Maven bằng Assembly Plugin

Nếu muốn tạo một gói ZIP chứa JAR, dependency và script/config bổ sung, Maven Assembly Plugin có thể đóng gói distribution. Một cách thường dùng là tạo assembly descriptor riêng.

Ví dụ `src/assembly/distribution.xml`:

```xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0 https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>distribution</id>
    <formats>
        <format>zip</format>
    </formats>
    <includeBaseDirectory>true</includeBaseDirectory>

    <dependencySets>
        <dependencySet>
            <outputDirectory>lib</outputDirectory>
            <useProjectArtifact>true</useProjectArtifact>
            <unpack>false</unpack>
            <scope>runtime</scope>
        </dependencySet>
    </dependencySets>

    <fileSets>
        <fileSet>
            <directory>src/main/assembly/bin</directory>
            <outputDirectory>bin</outputDirectory>
            <fileMode>0755</fileMode>
        </fileSet>
    </fileSets>
</assembly>
```

Descriptor trên đặt project artifact và dependency runtime trong `lib/`, đồng thời copy script từ `src/main/assembly/bin`. Tên, đường dẫn và quyền file cần điều chỉnh cho dự án và hệ điều hành mục tiêu.

Kích hoạt plugin trong `pom.xml`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.7.1</version>
    <configuration>
        <descriptors>
            <descriptor>src/assembly/distribution.xml</descriptor>
        </descriptors>
    </configuration>
    <executions>
        <execution>
            <id>make-distribution</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Chạy:

```shell
mvn package
```

Archive ZIP thường được tạo trong `target/`. Khi giải nén, người dùng nhận được một thư mục ứng dụng có JAR và các dependency riêng. Script khởi chạy cần được viết để sử dụng classpath tương ứng.

Assembly descriptor có nhiều tùy chọn hơn ví dụ trên, bao gồm cách đặt base directory, file permissions, dependency scope, module và các file bổ sung. Hãy xem tài liệu plugin đúng phiên bản khi xây dựng gói triển khai thực tế.

## 9. Viết script khởi chạy cho Thin JAR

Một distribution thường đi kèm script để người dùng không phải tự nhập classpath. Script cần xác định thư mục cài đặt dựa trên vị trí của chính script, sau đó ghép JAR ứng dụng và các dependency.

### Script trên Linux/macOS

Ví dụ `bin/my-app`:

```sh
#!/bin/sh
set -eu

APP_HOME=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_JAR="$APP_HOME/lib/my-app-1.0.0.jar"
LIB_DIR="$APP_HOME/lib"

exec java -cp "$APP_JAR:$LIB_DIR/*" com.example.app.Main "$@"
```

Script tính `APP_HOME` từ vị trí file script, vì vậy người dùng có thể gọi nó từ thư mục làm việc bất kỳ. `exec` thay tiến trình shell bằng JVM. `"$@"` chuyển nguyên vẹn các đối số mà người dùng truyền vào ứng dụng.

Đặt quyền thực thi cho script trong gói phân phối hoặc khi cài đặt:

```shell
chmod +x bin/my-app
```

### Script trên Windows

Ví dụ `bin/my-app.bat`:

```bat
@echo off
set "APP_HOME=%~dp0.."
set "APP_JAR=%APP_HOME%\lib\my-app-1.0.0.jar"
set "LIB_DIR=%APP_HOME%\lib"

java -cp "%APP_JAR%;%LIB_DIR%\*" com.example.app.Main %*
```

`%~dp0` là thư mục chứa script batch. `%*` chuyển các đối số dòng lệnh cho ứng dụng. Dấu phân cách classpath trên Windows là `;`.

Các script thực tế nên kiểm tra Java có trong `PATH` không, hiển thị thông báo rõ ràng khi thiếu runtime và cho phép cấu hình JVM options. Nếu cần hỗ trợ đường dẫn có ký tự đặc biệt hoặc đối số phức tạp, hãy kiểm tra kỹ cách shell/batch truyền tham số.

## 10. Chọn đúng tập dependency cần phân phối

Không phải mọi dependency trong build đều cần đưa vào thư mục runtime. Build tool phân biệt dependency theo configuration hoặc scope.

### Gradle

Với Java plugin:

| Configuration khai báo | Vai trò khái quát | Có trong runtime classpath chính? |
|---|---|---|
| `implementation` | Dependency dùng trong implementation của ứng dụng. | Có. |
| `runtimeOnly` | Chỉ cần khi chạy. | Có. |
| `compileOnly` | Cần để biên dịch nhưng runtime được cung cấp bởi môi trường hoặc cơ chế khác. | Không theo mặc định. |
| `testImplementation` | Dependency dành cho mã kiểm thử. | Không trong runtime chính. |
| `testRuntimeOnly` | Dependency chỉ cần khi chạy test. | Không trong runtime chính. |

Vì vậy, khi copy dependency cho Thin JAR, `runtimeClasspath` thường là điểm xuất phát phù hợp. Nếu ứng dụng dựa vào một thư viện được môi trường cung cấp, chẳng hạn API của container, không nên copy nó như thư viện runtime thông thường nếu hợp đồng triển khai yêu cầu container cung cấp.

### Maven

Các scope Maven cũng ảnh hưởng tập dependency:

- `compile`: có trong compile classpath và thường được truyền bắc cầu.
- `runtime`: cần khi chạy nhưng không cần để biên dịch source của project hiện tại.
- `provided`: môi trường chạy dự kiến cung cấp; thường không nên đóng gói như dependency runtime riêng.
- `test`: chỉ phục vụ kiểm thử.
- `system`: tham chiếu file cục bộ và khó di chuyển; không phù hợp cho distribution dùng chung.

Với Maven Dependency Plugin, `includeScope` có thể chọn tập dependency để copy. Hãy kiểm tra kết quả thực tế trong `target/lib/` và đối chiếu với runtime requirements của ứng dụng.

### Dependency tùy chọn và loại trừ

Một dependency optional hoặc bị exclude có thể không được truyền bắc cầu theo cách bạn kỳ vọng. Nếu ứng dụng sử dụng trực tiếp một thư viện, hãy khai báo dependency trực tiếp để runtime distribution có thể chứa nó. Nếu thư viện cha cần một dependency optional cho một tính năng mà ứng dụng đang bật, hãy khai báo dependency đó theo cấu hình ứng dụng.

Đừng dùng số lượng JAR trong `lib/` làm bằng chứng duy nhất rằng distribution đầy đủ. Hãy kiểm tra chức năng ứng dụng trên môi trường sạch, nơi không có thư viện tình cờ trong classpath của máy phát triển.

## 11. Kiểm tra manifest và nội dung gói

Sau khi tạo JAR, dùng công cụ `jar` của JDK để xem manifest:

```shell
jar --list --file build/libs/my-app-1.0.0.jar
```

Giải nén riêng manifest hoặc đọc bằng công cụ ZIP để kiểm tra:

```text
META-INF/MANIFEST.MF
```

Manifest có thể chứa:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/http-client-4.2.jar lib/json-core-3.1.jar
```

Kiểm tra:

1. `Main-Class` có đúng tên đầy đủ của lớp có phương thức `main` không?
2. Mỗi mục trong `Class-Path` có trỏ đến file thực sự tồn tại không?
3. Các dependency có được đặt tương đối với JAR đúng như manifest không?
4. Các JAR cần thiết có bị thiếu do scope, optional dependency hoặc exclusion không?
5. Tài nguyên cấu hình mà ứng dụng cần có nằm trong JAR hoặc thư mục phân phối không?

Có thể kiểm tra nội dung distribution sau khi giải nén và chạy script từ một thư mục làm việc khác. Cách này xác nhận script không vô tình dựa vào thư mục hiện tại của Terminal.

## 12. Những lỗi thường gặp khi chạy Thin JAR

| Lỗi hoặc biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `NoClassDefFoundError` | Lớp có lúc compile nhưng không có trong runtime classpath. | Xác định JAR chứa lớp và thêm vào runtime distribution/classpath. |
| `ClassNotFoundException` | Class loader không tìm thấy tên lớp được yêu cầu. | Kiểm tra classpath, manifest `Class-Path` và vị trí JAR. |
| `java -jar` chạy được lớp chính nhưng lỗi khi gọi thư viện | Manifest có `Main-Class` nhưng thiếu hoặc sai `Class-Path`. | Thêm dependency tương đối hoặc dùng script `-cp`. |
| Copy JAR ứng dụng sang nơi khác thì không chạy | Thư mục `lib/` không được chuyển cùng hoặc đường dẫn manifest không còn hợp lệ. | Phân phối nguyên cấu trúc thư mục hoặc tạo lại manifest phù hợp. |
| Chạy được trên IDE nhưng không chạy từ distribution | IDE tự cấu hình dependency classpath. | Kiểm tra runtime dependency được copy và script khởi chạy. |
| Thiếu driver/database provider | Dependency có scope hoặc configuration không nằm trong runtime output. | Kiểm tra `runtimeClasspath` hoặc Maven scope và khai báo phù hợp. |
| Lớp trùng hoặc version thư viện xung đột | Nhiều JAR chứa cùng class hoặc API không tương thích. | Đọc dependency tree, quản lý version và loại bỏ dependency trùng có chủ đích. |
| Manifest classpath không tìm thấy file có khoảng trắng | Mục URL trong manifest chưa được mã hóa đúng. | Dùng build tool tạo manifest; tránh tự nối chuỗi URL thủ công. |
| Script hoạt động chỉ khi chạy từ thư mục cài đặt | Script dựa vào working directory thay vì vị trí của script. | Tính thư mục gốc từ đường dẫn script và dùng đường dẫn tuyệt đối sau khi xác định APP_HOME. |

### Phân biệt lỗi compile và lỗi runtime

Nếu compiler báo `package ... does not exist`, vấn đề nằm ở compile classpath hoặc dependency resolution khi biên dịch. Nếu compile thành công nhưng khi chạy báo `NoClassDefFoundError`, vấn đề thường nằm ở runtime classpath hoặc dependency bị thiếu trong distribution.

Một dependency có thể có trong `compileClasspath` nhưng không có trong `runtimeClasspath` nếu khai báo sai scope. Vì vậy, hãy xem cả hai graph thay vì chỉ kiểm tra compile thành công.

## 13. Thin JAR trong các tình huống phân phối khác nhau

Thin JAR phù hợp với một số cách sử dụng khác nhau:

### Thư viện được tiêu thụ qua Maven/Gradle repository

Nếu JAR là thư viện dùng bởi project khác, thông thường không cần nhúng dependency vào JAR. Build tool của project tiêu thụ đọc metadata publication/POM hoặc module metadata để phân giải dependency bắc cầu.

Ví dụ dependency:

```groovy
dependencies {
    implementation 'com.example:payment-core:1.0.0'
}
```

Repository cung cấp JAR của `payment-core` cùng metadata mô tả các dependency cần thiết. Gradle/Maven của project tiêu thụ tải các artifact và xây dựng classpath. Đây là mô hình thư viện tiêu chuẩn.

### Ứng dụng chạy độc lập trên máy người dùng

Nếu người dùng tải một gói ZIP/TAR và chạy ứng dụng, distribution nên chứa:

- Thin JAR của ứng dụng.
- Tất cả runtime dependency cần thiết.
- Script khởi chạy hoặc hướng dẫn classpath.
- Cấu hình mẫu và tài liệu cần thiết.

Gradle Application plugin hoặc Maven Assembly Plugin có thể hỗ trợ tạo gói như vậy.

### Ứng dụng chạy trong container

Một image container có thể chứa JAR ứng dụng và các dependency riêng trong image. Dockerfile hoặc entrypoint script thiết lập classpath khi container khởi chạy. Thin JAR vẫn có thể phù hợp nếu image chứa đầy đủ thư viện runtime và cấu trúc đường dẫn ổn định.

Nếu dùng một framework/plugin tạo executable JAR riêng, hãy hiểu định dạng archive và cách loader tìm dependency của framework đó. Một executable JAR của framework có thể không còn là JAR chuẩn chỉ chứa application classes và manifest classpath.

## 14. Lựa chọn giữa Thin JAR và Fat JAR

Không có một cách đóng gói phù hợp cho mọi ứng dụng. Hãy dựa trên cách artifact được phân phối và vận hành.

| Tiêu chí | Thin JAR + thư viện riêng | Fat/Uber JAR |
|---|---|---|
| Đơn vị phân phối | Một thư mục/gói gồm nhiều JAR | Thường một archive ứng dụng |
| Cách cập nhật thư viện | Có thể thay JAR riêng nếu tương thích và kiểm soát version | Thường build lại artifact ứng dụng |
| Classpath | Script hoặc manifest phải cấu hình đúng | Loader hoặc archive layout gom dependency |
| Debug dependency | Có thể nhìn từng JAR trong thư mục `lib/` | Cần xem nội dung archive hoặc metadata của plugin |
| Tính đơn giản khi gửi một file | Kém thuận tiện hơn | Thuận tiện hơn |
| Xung đột tài nguyên | Các JAR riêng vẫn giữ cấu trúc, nhưng classpath order có thể quan trọng | Quá trình merge có thể cần xử lý service files, license và resource trùng |

Thin JAR phù hợp với thư viện, distribution có cấu trúc rõ và môi trường đã quản lý classpath. Fat JAR thuận tiện khi muốn gửi một file ứng dụng, nhưng cần plugin/loader đóng gói đúng cách. Không nên tự giải nén mọi dependency vào JAR mà bỏ qua các file service descriptor hoặc tài nguyên có cùng đường dẫn.

## 15. Bảo mật và vận hành khi phân phối thư viện riêng

Thư mục `lib/` là một phần của runtime supply chain. Mỗi JAR trong đó có thể chứa code được thực thi trong tiến trình ứng dụng.

Các nguyên tắc nên áp dụng:

- Quản lý version dependency rõ ràng và ưu tiên version cụ thể cho distribution phát hành.
- Lấy dependency từ repository được kiểm soát và xác minh nguồn gốc theo chính sách tổ chức.
- Lưu checksum hoặc metadata truy vết cho gói phát hành khi quy trình yêu cầu.
- Quét lỗ hổng trên dependency trực tiếp lẫn bắc cầu.
- Không cho phép người dùng không đáng tin cậy ghi đè JAR trong thư mục `lib/` của ứng dụng đang chạy.
- Phân phối các file cần thiết cùng một gói có version rõ ràng để tránh trộn JAR từ nhiều lần phát hành.
- Không đưa secret, mật khẩu hoặc token vào manifest hay file cấu hình được đóng gói.

Việc thay một JAR riêng lẻ có thể thuận tiện nhưng cũng có thể làm thay đổi hành vi của ứng dụng. Nếu thay dependency, cần xác nhận tương thích API và kiểm thử lại distribution hoàn chỉnh.

## 16. Quy trình điều tra khi Thin JAR không chạy

Khi ứng dụng chạy trong IDE nhưng thất bại sau khi đóng gói, hãy kiểm tra theo thứ tự:

1. Xác định lớp gây lỗi từ exception đầu tiên, ví dụ `NoClassDefFoundError`.
2. Tìm JAR chứa lớp đó trong dependency graph của `runtimeClasspath` hoặc Maven runtime tree.
3. Xác nhận JAR có được copy vào thư mục phân phối không.
4. Nếu chạy bằng `java -cp`, xác nhận wildcard và dấu phân cách classpath đúng hệ điều hành.
5. Nếu chạy bằng `java -jar`, đọc manifest và xác nhận `Class-Path` trỏ đến đúng file tương đối với JAR ứng dụng.
6. Xác nhận `Main-Class` đúng và lớp có phương thức `main` hợp lệ.
7. Chạy script từ một thư mục làm việc khác để phát hiện giả định sai về current directory.
8. Kiểm tra các dependency bị thiếu do `provided`, `compileOnly`, `optional` hoặc exclusion.
9. Kiểm tra version và class trùng trong thư mục `lib/`.
10. Tạo lại distribution từ build sạch và thử trên môi trường không có IDE hoặc classpath phụ.

Ví dụ, nếu `NoClassDefFoundError: com/example/json/JsonReader` xuất hiện, tìm module cung cấp `JsonReader`, xem nó có trong runtime graph không, rồi kiểm tra JAR tương ứng trong `lib/`. Nếu JAR có mặt, kiểm tra classpath thực tế hoặc manifest. Nếu JAR không có mặt, kiểm tra cấu hình copy dependency và scope.

## 17. Bài thực hành

Thực hành trên một ứng dụng Java nhỏ có ít nhất hai dependency runtime:

1. Tạo ứng dụng có lớp chính `com.example.app.Main` và thêm hai thư viện bên ngoài.
2. Tạo Thin JAR bằng Gradle Java plugin hoặc Maven JAR Plugin.
3. Kiểm tra nội dung JAR và xác nhận các dependency bên ngoài không bị nhúng vào archive.
4. Thử chạy chỉ với JAR ứng dụng và quan sát lỗi khi thiếu dependency.
5. Copy runtime dependency vào thư mục `lib/` và chạy bằng `java -cp`, dùng đúng dấu phân cách của hệ điều hành.
6. Cấu hình `Main-Class` và `Class-Path` trong manifest, sau đó chạy bằng `java -jar`.
7. Chuyển cả JAR và thư mục `lib/` sang một vị trí khác, rồi chạy lại để xác nhận đường dẫn tương đối hoạt động.
8. Với Gradle, thử Application plugin và chạy `installDist`, `distZip` hoặc `distTar`. Với Maven, thử Dependency Plugin và Assembly Plugin.
9. Mở gói distribution và xác nhận tất cả runtime dependency, script và tài nguyên cần thiết đều có mặt.
10. Chạy script từ thư mục làm việc khác và kiểm tra rằng nó vẫn xác định đúng thư mục cài đặt.

Sau bài thực hành, bạn cần giải thích được Thin JAR khác Fat JAR thế nào, JVM tìm dependency từ classpath và manifest ra sao, vì sao `java -jar` không dùng tùy chọn `-cp` như chế độ chạy lớp, và cách tạo một distribution có đầy đủ thư viện bên ngoài. Đây là nền tảng để đóng gói ứng dụng Java gọn, dễ truy vết và chạy ổn định ngoài IDE.
